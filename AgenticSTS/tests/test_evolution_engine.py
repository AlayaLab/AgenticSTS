"""Tests for Step 3: EvolutionEngine + write tools.

Covers:
- Write tool schemas: valid Anthropic format
- EvolutionEngine: tool dispatch, write tool handlers
- build_evolution_context: formats run data correctly
- Integration: evolution wired into post-run flow
"""
from __future__ import annotations

import copy
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

import config
from src.brain.evolution_engine import (
    EvolutionAction,
    EvolutionEngine,
    build_evolution_context,
)
from src.brain.write_tools import WRITE_TOOL_NAMES, WRITE_TOOLS
from src.memory.models_v2 import CombatDelta, CombatEpisode, CombatRound

# ── Write tool schemas ──────────────────────────────────────────


class TestWriteToolSchemas:
    """Verify write tool schemas are valid Anthropic format."""

    def test_all_tools_have_name(self):
        for tool in WRITE_TOOLS:
            assert "name" in tool
            assert isinstance(tool["name"], str)

    def test_all_tools_have_schema(self):
        for tool in WRITE_TOOLS:
            assert "input_schema" in tool
            assert tool["input_schema"]["type"] == "object"

    def test_tool_count(self):
        assert len(WRITE_TOOLS) == 3

    def test_tool_names_set(self):
        assert WRITE_TOOL_NAMES == frozenset({
            "author_tool", "write_skill",
            "get_performance_stats",
        })


# ── EvolutionEngine handlers ────────────────────────────────────


class TestEvolutionHandlers:
    """Test write tool handlers in isolation."""

    def _make_engine(self, tools_dir=None, skill_library=None):
        """Create an EvolutionEngine with mocked backend."""
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.skills.library import SkillLibrary

        if tools_dir is None:
            tools_dir = tempfile.mkdtemp()

        registry = DynamicToolRegistry(tools_dir)
        lib = skill_library or SkillLibrary()

        engine = EvolutionEngine(
            backend=MagicMock(),
            tool_executor=MagicMock(),
            dynamic_registry=registry,
            skill_library=lib,
        )
        return engine, registry, lib

    def test_author_tool_valid(self):
        with tempfile.TemporaryDirectory() as td:
            engine, registry, _ = self._make_engine(tools_dir=td)

            code = '''
SCHEMA = {
    "name": "add_numbers",
    "description": "Add two numbers.",
    "input_schema": {
        "type": "object",
        "properties": {"a": {"type": "integer"}, "b": {"type": "integer"}},
        "required": ["a", "b"]
    }
}

APPLICABLE_STATES = ["monster"]

def execute(a: int, b: int, **kwargs) -> str:
    return f"Result: {a + b}"

TEST_CASES = [
    {"input": {"a": 1, "b": 2}, "expected_contains": "3"},
    {"input": {"a": 10, "b": 20}, "expected_contains": "30"},
]
'''
            result = engine._handle_author_tool({
                "tool_name": "add_numbers",
                "code": code,
                "motivation": "test",
            })
            assert "SUCCESS" in result
            assert registry.has("add_numbers")

    def test_author_tool_rejected_forbidden_import(self):
        with tempfile.TemporaryDirectory() as td:
            engine, registry, _ = self._make_engine(tools_dir=td)

            code = '''
import os
SCHEMA = {"name": "bad", "description": "bad", "input_schema": {"type": "object", "properties": {}}}
def execute(**kwargs): return os.getcwd()
'''
            result = engine._handle_author_tool({
                "tool_name": "bad",
                "code": code,
                "motivation": "test",
            })
            assert "REJECTED" in result
            assert not registry.has("bad")

    def test_write_skill(self):
        with tempfile.TemporaryDirectory() as td:
            engine, _, lib = self._make_engine(tools_dir=td)

            # Patch config.SKILLS_DIR to temp dir
            with patch("config.SKILLS_DIR", td):
                result = engine._handle_write_skill({
                    "skill_name": "Poison timing",
                    "category": "combat",
                    "content": "Check poison lethal before playing attack cards.",
                    "motivation": "Lost a fight where poison would have killed enemy.",
                    "trigger_state_types": ["combat"],
                    "trigger_enemy_names": [],
                    "evidence": {
                        "run_ids": ["run_a", "run_b"],
                        "stat_basis": "win rate 22% vs 45% baseline across 20 runs",
                        "anchor_episode": "run_a:combat_3",
                    },
                    "rationale": (
                        "Pattern spans 20+ runs against poison-capable enemies; "
                        "single-run mistake_discovery lacks the cross-run win-rate comparator."
                    ),
                })

            assert "SUCCESS" in result
            assert lib.count == 1

    def test_write_skill_missing_fields(self):
        """With new gates firing first, missing rationale is rejected before skill_name check."""
        engine, _, _ = self._make_engine()
        result = engine._handle_write_skill({
            "skill_name": "",
            "category": "combat",
            "content": "",
            "motivation": "test",
        })
        assert "REJECTED" in result
        # New gates fire first — rationale missing produces the first rejection
        assert "rationale" in result.lower()

    def test_extract_relevant_replay_requires_enemy_or_card_anchor(self):
        engine, _, _ = self._make_engine()
        engine._run_context = "## Combat Replay: vs Goblin\nR1: Strike"

        trigger = SimpleNamespace(
            enemy_names=frozenset(),
            requires_cards=frozenset(),
            state_types=frozenset({"rest_site"}),
        )

        assert engine._extract_relevant_replay(trigger) == ""

    def test_extract_relevant_replay_no_first_replay_fallback_on_miss(self):
        engine, _, _ = self._make_engine()
        engine._run_context = "## Combat Replay: vs Goblin\nR1: Strike"

        trigger = SimpleNamespace(
            enemy_names=frozenset({"Lagavulin"}),
            requires_cards=frozenset(),
            state_types=frozenset({"monster"}),
        )

        assert engine._extract_relevant_replay(trigger) == ""

    def test_validate_skill_facts_skips_noncombat_skill_without_backend_call(self):
        engine, _, _ = self._make_engine()
        engine._run_context = "## Combat Replay: vs Goblin\nR1: Strike"

        trigger = SimpleNamespace(
            enemy_names=frozenset(),
            requires_cards=frozenset(),
            state_types=frozenset({"rest_site"}),
        )

        result = engine._validate_skill_facts(
            "Rest before boss",
            "Rest when boss HP buffer matters more than a small smith.",
            "Recent boss deaths came from greed.",
            trigger,
            "rest",
        )

        assert result is None
        engine._backend.call.assert_not_called()

    def test_validate_skill_injection_builds_snapshot_summary_from_gamestate_shims(self):
        from src.brain.state_snapshot_store import StateSnapshotStore

        mock_response = SimpleNamespace(content=[SimpleNamespace(text="HELPFUL: relevant advice.")])
        mock_backend = MagicMock()
        mock_backend.call.return_value = mock_response
        mock_backend.extract_text.return_value = "HELPFUL: relevant advice."

        with tempfile.TemporaryDirectory() as tmpdir:
            snap_store = StateSnapshotStore(persist_path=Path(tmpdir) / "snaps.jsonl")
            snap_store.capture(
                "monster",
                {
                    "screen": "COMBAT",
                    "in_combat": True,
                    "turn": 1,
                    "available_actions": ["play_card", "end_turn"],
                    "combat": {
                        "player": {
                            "current_hp": 50,
                            "max_hp": 75,
                            "block": 5,
                            "energy": 3,
                        },
                        "enemies": [
                            {
                                "name": "Jaw Worm",
                                "current_hp": 40,
                                "max_hp": 40,
                                "is_alive": True,
                                "intents": [
                                    {
                                        "damage": 11,
                                        "hits": 1,
                                        "total_damage": 11,
                                        "intent_type": "ATTACK",
                                    }
                                ],
                            }
                        ],
                        "hand": [
                            {
                                "index": 0,
                                "card_id": "survivor",
                                "name": "Survivor",
                                "card_type": "Skill",
                                "target_type": "none",
                                "energy_cost": 1,
                                "playable": True,
                            }
                        ],
                    },
                    "run": {
                        "character_id": "silent",
                        "character_name": "Silent",
                        "floor": 6,
                        "current_hp": 50,
                        "max_hp": 75,
                        "gold": 99,
                        "max_energy": 3,
                        "deck": [],
                        "relics": [],
                        "players": [],
                        "potions": [],
                    },
                },
            )

            engine = EvolutionEngine(
                backend=mock_backend,
                tool_executor=MagicMock(),
                dynamic_registry=MagicMock(),
                skill_library=MagicMock(),
                snapshot_store=snap_store,
            )

            trigger = SimpleNamespace(
                state_types=frozenset({"monster"}),
                enemy_names=frozenset(),
                requires_cards=frozenset(),
            )

            result = engine._validate_skill_injection(
                "Act 1 Silent elite readiness threshold",
                "Take elites only when current HP buffer and potions cover likely incoming damage.",
                trigger,
            )

        assert result is None
        mock_backend.call.assert_called_once()
        prompt = mock_backend.call.call_args.kwargs["messages"][0]["content"]
        assert "Energy: 3/3" in prompt
        assert "Block: 5" in prompt
        assert "Hand: [Survivor]" in prompt
        assert "Enemies: [Jaw Worm HP=40/40 intent=11dmg]" in prompt

    def test_performance_stats_tool_usage(self):
        registry = MagicMock()
        registry.stats.return_value = {}
        engine = EvolutionEngine(
            backend=MagicMock(),
            tool_executor=MagicMock(),
            dynamic_registry=registry,
            skill_library=MagicMock(),
        )
        result = engine._handle_performance_stats({"metric": "tool_usage"})
        assert "No dynamic tools" in result or "no" in result.lower()

    def test_performance_stats_skill_usage(self):
        from src.skills.library import SkillLibrary
        lib = SkillLibrary()
        engine = EvolutionEngine(
            backend=MagicMock(),
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=lib,
        )
        result = engine._handle_performance_stats({"metric": "skill_usage"})
        assert "Skills:" in result


class TestEvolutionLoop:
    """Test provider-agnostic evolution loop message handling."""

    def test_run_evolution_preserves_reasoning_content_in_tool_loop(self):
        responses = [
            SimpleNamespace(
                content=[
                    SimpleNamespace(type="thinking", thinking="hidden"),
                    SimpleNamespace(
                        type="tool_use",
                        id="tool_1",
                        name="get_performance_stats",
                        input={"metric": "tool_usage"},
                    ),
                ],
                _reasoning_content="prior reasoning",
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="done")],
            ),
        ]

        class FakeBackend:
            def __init__(self, scripted):
                self._scripted = list(scripted)
                self.calls = []

            def call(self, **kwargs):
                self.calls.append(copy.deepcopy(kwargs))
                return self._scripted[len(self.calls) - 1]

            @staticmethod
            def extract_tool_uses(response):
                results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        results.append({
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                return results

            @staticmethod
            def build_tool_result(tool_use_id, content, *, is_error=False):
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }

        registry = MagicMock()
        registry.get_normalized_schemas.return_value = []
        registry.stats.return_value = {}
        backend = FakeBackend(responses)
        engine = EvolutionEngine(
            backend=backend,
            tool_executor=MagicMock(),
            dynamic_registry=registry,
            skill_library=MagicMock(),
        )

        actions = engine.run_evolution(
            "ctx",
            min_rounds=2,
            max_rounds=2,
            read_only_rounds=1,
            target_input_tokens=0,
        )

        assert len(actions) == 0
        assert len(backend.calls) == 2
        assert backend.calls[0]["openai_relay_profile"] == "postrun"
        assert backend.calls[1]["openai_relay_profile"] == "postrun"
        assert backend.calls[0]["tool_choice"] == {"type": "any"}
        # Round 2 is the final write round with 0 actions taken so far.
        # Bug A1 safety net (2026-04-30) restricts tools to writes only and
        # forces tool_choice=any; previously this was tool_choice=None.
        assert backend.calls[1]["tool_choice"] == {"type": "any"}
        second_messages = backend.calls[1]["messages"]
        assert second_messages[1]["role"] == "assistant"
        assert len(second_messages[1]["content"]) == 1
        assert second_messages[1]["content"][0].type == "tool_use"
        assert second_messages[1]["content"][0].name == "get_performance_stats"
        assert second_messages[1]["_reasoning_content"] == "prior reasoning"
        assert engine._last_session_summary["target_reached"] is True

    def test_read_phase_continuation_switches_to_write_instruction(self):
        responses = [
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="tool_1",
                        name="get_performance_stats",
                        input={"metric": "tool_usage"},
                    ),
                ],
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="diagnosis complete")],
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="still no write")],
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            ),
        ]

        class FakeBackend:
            def __init__(self, scripted):
                self._scripted = list(scripted)
                self.calls = []

            def call(self, **kwargs):
                self.calls.append(copy.deepcopy(kwargs))
                return self._scripted[len(self.calls) - 1]

            @staticmethod
            def extract_tool_uses(response):
                results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        results.append({
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                return results

            @staticmethod
            def build_tool_result(tool_use_id, content, *, is_error=False):
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }

        registry = MagicMock()
        registry.get_normalized_schemas.return_value = []
        registry.stats.return_value = {}
        backend = FakeBackend(responses)
        engine = EvolutionEngine(
            backend=backend,
            tool_executor=MagicMock(),
            dynamic_registry=registry,
            skill_library=MagicMock(),
        )

        engine.run_evolution(
            "ctx",
            min_rounds=3,
            max_rounds=3,
            read_only_rounds=2,
            target_input_tokens=0,
        )

        third_call_messages = backend.calls[2]["messages"]
        assert "Move to execution now" in third_call_messages[-1]["content"]
        assert backend.calls[2]["tool_choice"] == {"type": "any"}

    def test_write_phase_noop_without_actions_continues_until_next_round(self):
        responses = [
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="tool_1",
                        name="get_performance_stats",
                        input={"metric": "tool_usage"},
                    ),
                ],
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="diagnosis complete")],
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            ),
            SimpleNamespace(
                content=[
                    SimpleNamespace(
                        type="tool_use",
                        id="tool_2",
                        name="get_performance_stats",
                        input={"metric": "recent_runs"},
                    ),
                ],
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="proposed changes but no tool call")],
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            ),
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="final no-op")],
                usage=SimpleNamespace(input_tokens=100, output_tokens=10),
            ),
        ]

        class FakeBackend:
            def __init__(self, scripted):
                self._scripted = list(scripted)
                self.calls = []

            def call(self, **kwargs):
                self.calls.append(copy.deepcopy(kwargs))
                return self._scripted[len(self.calls) - 1]

            @staticmethod
            def extract_tool_uses(response):
                results = []
                for block in response.content:
                    if getattr(block, "type", None) == "tool_use":
                        results.append({
                            "id": block.id,
                            "name": block.name,
                            "input": block.input,
                        })
                return results

            @staticmethod
            def build_tool_result(tool_use_id, content, *, is_error=False):
                return {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": content,
                    "is_error": is_error,
                }

        registry = MagicMock()
        registry.get_normalized_schemas.return_value = []
        registry.stats.return_value = {}
        backend = FakeBackend(responses)
        engine = EvolutionEngine(
            backend=backend,
            tool_executor=MagicMock(),
            dynamic_registry=registry,
            skill_library=MagicMock(),
        )

        actions = engine.run_evolution(
            "ctx",
            min_rounds=4,
            max_rounds=5,
            read_only_rounds=2,
            target_input_tokens=0,
        )

        assert actions == []
        assert len(backend.calls) == 5
        assert backend.calls[4]["tool_choice"] == {"type": "any"}

    def test_round_1_prompt_artifact_uses_actual_phase_system_prompt(self):
        responses = [
            SimpleNamespace(
                content=[SimpleNamespace(type="text", text="done")],
                usage=SimpleNamespace(input_tokens=10, output_tokens=5),
            ),
        ]

        class FakeBackend:
            def __init__(self, scripted):
                self._scripted = list(scripted)

            def call(self, **kwargs):
                return self._scripted.pop(0)

            @staticmethod
            def extract_tool_uses(_response):
                return []

        with tempfile.TemporaryDirectory() as td:
            engine = EvolutionEngine(
                backend=FakeBackend(responses),
                tool_executor=MagicMock(),
                dynamic_registry=MagicMock(),
                skill_library=MagicMock(),
            )

            engine.run_evolution(
                "ctx",
                artifact_dir=Path(td),
                min_rounds=1,
                max_rounds=1,
                read_only_rounds=1,
                target_input_tokens=0,
            )

            prompt_path = Path(td) / "round_1_prompt.md"
            prompt_text = prompt_path.read_text(encoding="utf-8")
            # System prompt is now static across phases for cache stability
            assert "You are a self-evolving Slay the Spire 2 agent" in prompt_text
            assert "# Round 1 User Context\n\nctx" in prompt_text

    def test_validate_tool_quality_uses_evolution_model_and_postrun_profile(self):
        backend = MagicMock()
        backend.call.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="HELPFUL: good signal")]
        )
        engine = EvolutionEngine(
            backend=backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=MagicMock(),
        )
        engine._last_validation_success = (
            SimpleNamespace(
                player_hp=50,
                player_max_hp=80,
                energy=3,
                block=0,
                hand=[SimpleNamespace(name="Strike")],
                enemies=[
                    SimpleNamespace(
                        name="Cultist",
                        current_hp=40,
                        max_hp=48,
                        block=0,
                        powers=[],
                        intents=[],
                    )
                ],
            ),
            {"advice": "attack"},
        )

        result = engine._validate_tool_quality(SimpleNamespace(name="judge_me"))

        assert result is None
        kwargs = backend.call.call_args.kwargs
        assert kwargs["provider"] == config.EVOLUTION_PROVIDER
        assert kwargs["model"] == config.EVOLUTION_MODEL
        assert kwargs["openai_relay_profile"] == "postrun"

    def test_compress_skill_content_uses_postrun_profile(self):
        backend = MagicMock()
        backend.call.return_value = SimpleNamespace(
            content=[SimpleNamespace(text="Short but useful skill text.")]
        )
        engine = EvolutionEngine(
            backend=backend,
            tool_executor=MagicMock(),
            dynamic_registry=MagicMock(),
            skill_library=MagicMock(),
        )

        compressed = engine._compress_skill_content("Very long skill content", "Test Skill")

        assert compressed == "Short but useful skill text."
        assert backend.call.call_args.kwargs["openai_relay_profile"] == "postrun"


# ── build_evolution_context ─────────────────────────────────────


class TestBuildEvolutionContext:
    """Test evolution context builder."""

    def test_victory_context(self):
        from src.state.run_state import RunState

        rs = RunState(
            run_id="test-run-1",
            character="Ironclad",
            victory=True,
            final_floor=51,
        )
        context = build_evolution_context(rs)
        assert "Ironclad" in context
        assert "VICTORY" in context
        assert "fitness" in context

    def test_defeat_context(self):
        from src.state.run_state import RunState

        rs = RunState(
            run_id="test-run-2",
            character="Silent",
            victory=False,
            final_floor=15,
        )
        context = build_evolution_context(rs)
        assert "Silent" in context
        assert "DEFEAT" in context
        assert "15" in context

    def test_dynamic_tool_stats_included(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.state.run_state import RunState

        rs = RunState(run_id="test", character="Defect", victory=False, final_floor=10)
        registry = MagicMock(spec=DynamicToolRegistry)
        registry.stats.return_value = {
            "poison_check": {"usage_count": 5, "success_count": 4, "motivation": "test"}
        }

        context = build_evolution_context(rs, registry)
        assert "poison_check" in context
        assert "5 calls" in context

    def test_no_registry(self):
        from src.state.run_state import RunState
        rs = RunState(run_id="test", character="Regent", final_floor=20)
        context = build_evolution_context(rs, None)
        assert "None yet" in context

    def test_smart_selection_includes_boss_and_elite(self):
        """Smart selection includes all boss/elite combats."""
        from src.state.run_state import RunState

        rs = RunState(run_id="test-smart", character="Silent", final_floor=40)
        _ev = (CombatDelta(event_type="card_play", source="Strike"),)
        episodes = [
            CombatEpisode(
                run_id="test-smart", enemy_key="Boss1", combat_type="boss",
                floor=30, won=True, hp_before=60, hp_after=40,
                rounds=(CombatRound(round_num=1, events=_ev, cards_played=("Strike",)),),
            ),
            CombatEpisode(
                run_id="test-smart", enemy_key="Elite1", combat_type="elite",
                floor=15, won=True, hp_before=70, hp_after=55,
                rounds=(CombatRound(round_num=1, events=_ev, cards_played=("Defend",)),),
            ),
            CombatEpisode(
                run_id="test-smart", enemy_key="Monster1", combat_type="monster",
                floor=5, won=True, hp_before=80, hp_after=78,
                rounds=(CombatRound(round_num=1, events=_ev, cards_played=("Strike",)),),
            ),
        ]
        combat_store = MagicMock()
        combat_store.get_all.return_value = episodes
        memory_manager = SimpleNamespace(
            combat_store=combat_store,
            guide_store=None,
            card_memory_store=None,
        )

        context = build_evolution_context(rs, None, memory_manager)
        # Boss and elite replays included, monster skipped (not anomalous)
        assert "Boss1" in context
        assert "Elite1" in context

    def test_skill_triggers_included(self):
        """Skill trigger log formatted into evolution context."""
        from src.state.run_state import RunState

        rs = RunState(run_id="test-skills", character="Silent", final_floor=30)
        triggers = [
            {"skill_name": "Core Combat", "floor": 10, "enemy": "Goblin", "result": "WIN"},
            {"skill_name": "Core Combat", "floor": 20, "enemy": "Elite", "result": "LOSS"},
        ]
        context = build_evolution_context(rs, None, None, skill_triggers=triggers)
        assert "Triggered Skills This Run" in context
        assert "Core Combat" in context
        assert "F10(Goblin: WIN)" in context



# ── EvolutionAction ─────────────────────────────────────────────


class TestEvolutionAction:
    """Test EvolutionAction dataclass."""

    def test_basic_creation(self):
        action = EvolutionAction(
            tool="author_tool",
            tool_input={"tool_name": "test"},
            result="SUCCESS",
        )
        assert action.tool == "author_tool"
        assert action.tool_input == {"tool_name": "test"}
        assert action.result == "SUCCESS"
        assert action.timestamp > 0

    def test_frozen(self):
        """EvolutionAction should be immutable."""
        action = EvolutionAction(tool="test", tool_input={}, result="ok")
        with pytest.raises(AttributeError):
            action.result = "modified"


# ── Integration: loop.py wiring ─────────────────────────────────


class TestEvolutionIntegration:
    """Verify evolution is wired into the post-run flow."""

    def test_post_run_evolution_method_exists(self):
        """AgentLoop should have _post_run_evolution method."""
        from src.agent.loop import AgentLoop
        assert hasattr(AgentLoop, "_post_run_evolution")

    def test_write_evolution_log_method_exists(self):
        from src.agent.loop import AgentLoop
        assert hasattr(AgentLoop, "_write_evolution_log")

    def test_evolution_enabled_config(self):
        """Config should have EVOLUTION_ENABLED."""
        import config
        assert hasattr(config, "EVOLUTION_ENABLED")
        assert hasattr(config, "EVOLUTION_DIR")
        assert hasattr(config, "EVOLUTION_TOOLS_DIR")
        assert hasattr(config, "EVOLUTION_MAX_ROUNDS")

    def test_evolution_max_rounds_default_is_five(self):
        """Bug A1 (2026-04-30): default 3 led to 100% noop rate over 5 sessions
        because net write rounds (max - read_only = 1) starved out diagnostic-
        biased LLMs. Default raised to 5 (net 3 write rounds) plus a final-round
        force-write safety net.

        Empirical: with max_rounds=6 (pre-spec), avg actions_taken=3.6/session.
        With max_rounds=3 (post-spec), 0/5 sessions produced any action."""
        import importlib
        import os

        if "STS2_EVOLUTION_MAX_ROUNDS" in os.environ:
            del os.environ["STS2_EVOLUTION_MAX_ROUNDS"]
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.EVOLUTION_MAX_ROUNDS == 5

    def test_evolution_config_invariant_net_write_rounds(self):
        """Bug A1 invariant: net write rounds (max - read_only) must be >= 2
        so the LLM can both diagnose and write. Catches future config drift
        like the 2026-04-25 spec change that lowered max without lowering
        read_only or min_rounds."""
        import config
        net_write_rounds = (
            config.EVOLUTION_MAX_ROUNDS - config.EVOLUTION_READ_ONLY_ROUNDS
        )
        assert net_write_rounds >= 2, (
            f"Need >=2 net write rounds; got max={config.EVOLUTION_MAX_ROUNDS}, "
            f"read_only={config.EVOLUTION_READ_ONLY_ROUNDS}, "
            f"net={net_write_rounds}"
        )


class TestFinalForceWriteRound:
    """Bug A1 safety-net predicate: identify the round that must restrict
    tools to writes only. Triggered when LLM has burned all rounds on
    diagnostic queries and no actions have been taken yet.
    """

    def test_final_round_no_actions_triggers_force_write(self):
        """Last round + write phase + zero actions → must force write."""
        from src.brain.evolution_engine import EvolutionEngine
        assert EvolutionEngine._is_final_force_write_round(
            round_idx=4, max_rounds=5, read_only_rounds=2, actions_taken_count=0,
        ) is True

    def test_final_round_with_prior_actions_does_not_force(self):
        """Last round + actions already written → let LLM finish naturally."""
        from src.brain.evolution_engine import EvolutionEngine
        assert EvolutionEngine._is_final_force_write_round(
            round_idx=4, max_rounds=5, read_only_rounds=2, actions_taken_count=2,
        ) is False

    def test_non_final_round_does_not_force(self):
        """Mid-loop round → don't force write even if no actions yet."""
        from src.brain.evolution_engine import EvolutionEngine
        assert EvolutionEngine._is_final_force_write_round(
            round_idx=2, max_rounds=5, read_only_rounds=2, actions_taken_count=0,
        ) is False

    def test_final_round_in_read_phase_does_not_force(self):
        """Pure read-only mode (read_only_rounds == max_rounds) → never force.
        E.g. dry-run mode where max=2, read_only=2."""
        from src.brain.evolution_engine import EvolutionEngine
        assert EvolutionEngine._is_final_force_write_round(
            round_idx=1, max_rounds=2, read_only_rounds=2, actions_taken_count=0,
        ) is False

    def test_legacy_broken_config_repro(self):
        """Regression repro: with the bugged max=3, read_only=2 config, the
        only write round (round_idx=2) WAS the final round and DID need
        force-write. This documents the bug shape so the fix's logic stays
        consistent if the config gets temporarily reduced again."""
        from src.brain.evolution_engine import EvolutionEngine
        assert EvolutionEngine._is_final_force_write_round(
            round_idx=2, max_rounds=3, read_only_rounds=2, actions_taken_count=0,
        ) is True


class TestPhaseSystemPrompt:
    """Test that system prompt is static across phases for cache stability."""

    def test_phase_system_prompt_returns_same_text_in_both_phases(self):
        """Spec #3 §3.3: the system prompt should be byte-stable across phases
        so that the prompt cache hits within a single postrun. Phase signaling
        moves to user-message land (tool_choice + continuation_prompt)."""

        read_only = EvolutionEngine._phase_system_prompt(is_read_phase=True)
        write_phase = EvolutionEngine._phase_system_prompt(is_read_phase=False)
        assert read_only == write_phase, (
            "System prompt MUST be invariant across phases for cache stability."
        )


def test_run_evolution_accepts_combat_trace_text_kwarg():
    """Spec #3 §3.4: evolution shares the same cached trace prefix that
    Turn 1/2 produce. The first user message becomes a multi-block
    content list with the trace as a cache_control: ephemeral block."""
    import inspect
    from src.brain.evolution_engine import EvolutionEngine

    sig = inspect.signature(EvolutionEngine.run_evolution)
    assert "combat_trace_text" in sig.parameters, (
        "run_evolution must accept combat_trace_text kwarg per Spec #3 §3.4"
    )
    # Default should be None so callers without trace continue to work
    assert sig.parameters["combat_trace_text"].default is None


def test_run_evolution_first_user_message_has_cached_trace_prefix(monkeypatch):
    """When combat_trace_text is provided, the first user message must be
    a multi-block content list whose first block carries
    cache_control: ephemeral and matches the trace verbatim."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine

    # Build a minimal engine with a fake backend that captures the messages
    fake_backend = MagicMock()
    captured = {}
    def _spy_call(**kwargs):
        captured["messages"] = kwargs["messages"]
        # Stop the loop on first round by returning end_turn with no tool_use
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )
    fake_backend.call.side_effect = _spy_call

    engine = EvolutionEngine(
        backend=fake_backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=MagicMock(),
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    trace = "TRACE_BYTES_HERE_FOR_CACHE_KEY"
    engine.run_evolution(
        run_context="## Cross-run summary\n...",
        character="silent",
        max_rounds=1,
        read_only_rounds=0,
        min_rounds=0,
        target_input_tokens=0,
        combat_trace_text=trace,
    )

    msgs = captured.get("messages")
    assert msgs is not None and msgs, "Backend must have been called"
    first = msgs[0]
    assert first["role"] == "user"
    content = first["content"]
    assert isinstance(content, list), "Trace path must use multi-block content"
    assert len(content) >= 2
    assert content[0].get("type") == "text"
    assert content[0].get("text") == trace
    assert content[0].get("cache_control") == {"type": "ephemeral"}


def test_run_evolution_without_trace_uses_string_content():
    """When combat_trace_text is None / empty, first user message remains
    a plain string (backwards compatible)."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine

    fake_backend = MagicMock()
    captured = {}
    def _spy_call(**kwargs):
        captured["messages"] = kwargs["messages"]
        from types import SimpleNamespace
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text="done")],
            stop_reason="end_turn",
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
        )
    fake_backend.call.side_effect = _spy_call

    engine = EvolutionEngine(
        backend=fake_backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=MagicMock(),
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    engine.run_evolution(
        run_context="## Cross-run summary\n...",
        character="silent",
        max_rounds=1,
        read_only_rounds=0,
        min_rounds=0,
        target_input_tokens=0,
        # combat_trace_text omitted
    )
    msgs = captured.get("messages")
    first = msgs[0]
    assert isinstance(first["content"], str)


# ── write_skill cross-run evidence gates ────────────────────────


def _make_engine_for_skill_test(tools_dir):
    """Helper: minimal EvolutionEngine for write_skill tests."""
    from unittest.mock import MagicMock
    from src.brain.evolution_engine import EvolutionEngine
    from src.skills.library import SkillLibrary

    backend = MagicMock()
    lib = SkillLibrary()
    engine = EvolutionEngine(
        backend=backend,
        tool_executor=MagicMock(),
        dynamic_registry=None,
        skill_library=lib,
        memory_manager=None,
        tool_preprocessor=None,
        plan_verifier=None,
        snapshot_store=None,
        session_logger=None,
    )
    engine._run_context = "(no run context)"
    return engine, backend, lib


def test_write_skill_rejects_missing_rationale():
    """Spec #3 §3.2: write_skill MUST have a rationale explaining why
    mistake_discovery couldn't catch this from a single trace. Missing
    rationale is a hard reject."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "win rate 18% vs 42% baseline across 30 silent runs",
                    "anchor_episode": "r1:c3",
                },
                # rationale missing
            })
    assert "rationale" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_short_rationale():
    """Rationale below 30 chars (after stripping) → reject as 'too thin'."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "win rate 18% vs 42% baseline",
                    "anchor_episode": "r1:c3",
                },
                "rationale": "obvious",  # 7 chars — too short
            })
    assert "rationale" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_too_few_run_ids():
    """evidence.run_ids must contain >=2 distinct ids (cross-run)."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1"],  # only 1 run
                    "stat_basis": "win rate 18% vs 42% baseline across silent runs",
                    "anchor_episode": "r1:c3",
                },
                "rationale": (
                    "Pattern emerges only across multiple knowledge_demon "
                    "encounters; single run trace lacks the comparator."
                ),
            })
    assert "run_ids" in result.lower() or "cross-run" in result.lower()
    assert "REJECTED" in result


def test_write_skill_rejects_stat_basis_without_numbers():
    """evidence.stat_basis must reference numeric data
    (heuristic: contains a digit AND comparator phrase)."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "the player loses sometimes against this enemy",  # no numbers
                    "anchor_episode": "r1:c3",
                },
                "rationale": (
                    "Pattern emerges only across multiple runs; single trace "
                    "lacks the comparator. mistake_discovery wouldn't catch it."
                ),
            })
    assert "stat_basis" in result.lower() or "numeric" in result.lower()
    assert "REJECTED" in result


def test_write_skill_accepts_complete_proposal():
    """Happy path: all required fields present and valid."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, lib = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Knowledge demon stall",
                "category": "combat",
                "content": "Against knowledge_demon, prioritize block over damage when HP < 30.",
                "motivation": "Multiple low-HP losses on knowledge_demon",
                "trigger_state_types": ["combat"],
                "trigger_enemy_names": ["knowledge_demon"],
                "evidence": {
                    "run_ids": ["r_alpha", "r_beta", "r_gamma"],
                    "stat_basis": "win rate 18% vs knowledge_demon (30 runs) vs 42% baseline",
                    "anchor_episode": "r_alpha:combat_4",
                },
                "rationale": (
                    "Pattern emerges across 30+ knowledge_demon runs; single-run "
                    "mistake_discovery cannot see the cross-run win-rate gap."
                ),
            })
    assert "REJECTED" not in result
    assert "SUCCESS" in result or "MERGED" in result


def test_write_skill_rejects_malformed_anchor_episode():
    """Spec #3 §3.2: anchor_episode must follow `<run_id>:<combat_id>`
    format. Plain strings without a colon should be rejected."""
    with tempfile.TemporaryDirectory() as td:
        engine, _, _ = _make_engine_for_skill_test(tools_dir=td)
        with patch("config.SKILLS_DIR", td):
            result = engine._handle_write_skill({
                "skill_name": "Test skill",
                "category": "combat",
                "content": "Test content.",
                "motivation": "test",
                "trigger_state_types": ["combat"],
                "evidence": {
                    "run_ids": ["r1", "r2"],
                    "stat_basis": "win rate 18% vs 42% baseline across silent runs",
                    "anchor_episode": "garbage",  # missing colon
                },
                "rationale": (
                    "Pattern emerges only across multiple runs; single trace "
                    "lacks the comparator. mistake_discovery wouldn't catch."
                ),
            })
    assert "anchor_episode" in result.lower()
    assert "REJECTED" in result
