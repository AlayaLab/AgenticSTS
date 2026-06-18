"""Tests for ToolPreprocessor: state-derived tool preprocessing.

Covers:
- Parameter binding from GameState
- State applicability inference
- Tool execution and hint formatting
- Telemetry recording
- Integration with real tools from data/evolution/tools/
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.brain.dynamic_tools import DynamicToolRegistry

# ── Fixtures ──────────────────────────────────────────────────

STATE_DERIVED_TOOL = '''
SCHEMA = {
    "name": "test_survival_check",
    "description": "Check if player survives incoming damage in combat.",
    "parameters": {
        "current_hp": {"type": "int", "description": "Player HP"},
        "incoming_damage": {"type": "int", "description": "Total incoming damage"},
        "current_block": {"type": "int", "description": "Current block"},
    },
}

def execute(current_hp: int = 0, incoming_damage: int = 0, current_block: int = 0, **kwargs) -> str:
    net = max(0, incoming_damage - current_block)
    if net >= current_hp:
        return f"LETHAL: net damage {net} >= HP {current_hp}"
    return f"SAFE: net damage {net} < HP {current_hp}"
'''

DECK_TOOL = '''
SCHEMA = {
    "name": "test_deck_size_check",
    "description": "Check deck bloat based on deck_size and floor.",
    "parameters": {
        "deck_size": {"type": "int", "description": "Deck size"},
        "floor": {"type": "int", "description": "Current floor"},
    },
}

def execute(deck_size: int = 0, floor: int = 0, **kwargs) -> str:
    if deck_size > 20 + floor:
        return f"BLOATED: {deck_size} cards at floor {floor}"
    return f"OK: {deck_size} cards at floor {floor}"
'''

PLAN_EVALUATOR_TOOL = '''
SCHEMA = {
    "name": "test_plan_eval",
    "description": "Needs planned_block — should be skipped.",
    "parameters": {
        "planned_block": {"type": "int", "description": "Block from plan"},
        "current_hp": {"type": "int", "description": "Player HP"},
    },
}

def execute(planned_block: int = 0, current_hp: int = 0, **kwargs) -> str:
    return "should not run"
'''


def _make_gs(
    state_type: str = "monster",
    player_hp: int = 50,
    player_max_hp: int = 80,
    floor: int = 10,
    act: int = 1,
    gold: int = 100,
    energy: int = 3,
    block: int = 0,
    enemies: list | None = None,
    deck: list | None = None,
) -> SimpleNamespace:
    """Build a minimal GameState-like namespace for testing."""
    if enemies is None:
        enemies = [SimpleNamespace(
            index=0,
            name="Gremlin",
            current_hp=20,
            max_hp=20,
            block=0,
            powers=[],
            intent="Attack 8",
            intents=[SimpleNamespace(
                index=0,
                intent_type="Attack",
                label="Attack 8",
                damage=8,
                hits=1,
                total_damage=8,
                status_card_count=None,
            )],
            is_alive=True,
        )]

    if deck is None:
        deck = [SimpleNamespace(
            name="Strike", card_type="attack", rarity="Basic",
            energy_cost=1,
        )] * 5 + [SimpleNamespace(
            name="Defend", card_type="skill", rarity="Basic",
            energy_cost=1,
        )] * 5

    player = SimpleNamespace(
        block=block,
        energy=energy,
        stars=0,
        focus=0,
        powers=[],
        orbs=[],
        current_hp=player_hp,
        max_hp=player_max_hp,
    )

    combat = SimpleNamespace(
        player=player,
        enemies=enemies,
        hand=[],
    )

    run = SimpleNamespace(
        max_energy=3,
        current_hp=player_hp,
        max_hp=player_max_hp,
    )

    raw = SimpleNamespace(
        combat=combat if state_type in ("monster", "elite", "boss") else None,
        run=run,
        map=None,
        event=None,
        rest=None,
        shop=None,
        reward=None,
        selection=None,
        chest=None,
        game_over=None,
    )

    gs = SimpleNamespace(
        state_type=state_type,
        is_combat=state_type in ("monster", "elite", "boss"),
        player_hp=player_hp,
        player_max_hp=player_max_hp,
        hp_ratio=player_hp / player_max_hp if player_max_hp > 0 else 0,
        energy=energy,
        floor=floor,
        act=act,
        gold=gold,
        deck=deck,
        deck_size=len(deck),
        relics=[],
        potions=[],
        enemies=enemies,
        hand=[],
        playable_cards=[],
        raw=raw,
        character="Ironclad",
    )
    return gs


# ── Test classes ───────────────────────────────────────────────


class TestParameterBinding:
    """Verify parameter binding from GameState."""

    def test_bind_combat_params(self):
        from src.brain.tool_preprocessor import bind_params

        gs = _make_gs(state_type="monster", player_hp=50, block=5)
        params = {"current_hp": {}, "incoming_damage": {}, "current_block": {}}
        bound = bind_params(params, gs)

        assert bound is not None
        assert bound["current_hp"] == 50
        assert bound["current_block"] == 5
        assert bound["incoming_damage"] == 8  # From test enemy intent

    def test_bind_run_params(self):
        from src.brain.tool_preprocessor import bind_params

        gs = _make_gs(state_type="map", floor=15, gold=200)
        params = {"floor": {}, "current_gold": {}, "deck_size": {}}
        bound = bind_params(params, gs)

        assert bound is not None
        assert bound["floor"] == 15
        assert bound["current_gold"] == 200
        assert bound["deck_size"] == 10

    def test_unbindable_param_returns_none(self):
        from src.brain.tool_preprocessor import bind_params

        gs = _make_gs()
        params = {"planned_block": {}, "current_hp": {}}
        bound = bind_params(params, gs)

        assert bound is None


class TestToolPreprocessor:
    """Verify ToolPreprocessor runs applicable tools and produces hints."""

    def test_runs_state_derived_tools(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "survival.py").write_text(STATE_DERIVED_TOOL, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry)
            gs = _make_gs(state_type="monster", player_hp=50, block=0)

            hints = preprocessor.run_applicable("monster", gs)
            assert len(hints) >= 1
            assert any("SAFE" in h.result for h in hints)

    def test_skips_plan_evaluator_tools(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "plan_eval.py").write_text(PLAN_EVALUATOR_TOOL, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry)
            gs = _make_gs(state_type="monster", player_hp=50)

            hints = preprocessor.run_applicable("monster", gs)
            # Plan evaluator should be skipped
            assert len(hints) == 0

    def test_format_hints_output(self):
        from src.brain.tool_preprocessor import ToolHint, ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            preprocessor = ToolPreprocessor(DynamicToolRegistry(td))

            hints = [
                ToolHint(tool_name="survival_check", result="SAFE: 42 HP remaining", latency_ms=1.0),
                ToolHint(tool_name="deck_check", result="OK: 12 cards", latency_ms=0.5),
            ]
            text = preprocessor.format_hints(hints)

            assert "## Computed Insights" in text
            assert "survival_check" in text
            assert "deck_check" in text

    def test_format_hints_empty(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            preprocessor = ToolPreprocessor(DynamicToolRegistry(td))
            text = preprocessor.format_hints([])
            assert text == ""

    def test_telemetry_recorded(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "survival.py").write_text(STATE_DERIVED_TOOL, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry)
            gs = _make_gs(state_type="monster", player_hp=50)

            preprocessor.run_applicable("monster", gs)

            summary = preprocessor.get_telemetry_summary()
            assert "test_survival_check" in summary
            assert summary["test_survival_check"]["runs"] >= 1
            assert summary["test_survival_check"]["successes"] >= 1

    def test_telemetry_reset_clears_records(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "survival.py").write_text(STATE_DERIVED_TOOL, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry)
            gs = _make_gs(state_type="monster", player_hp=50)

            preprocessor.run_applicable("monster", gs)
            assert len(preprocessor.usage_records) > 0

            # Reset clears records for new run
            preprocessor.reset()
            assert len(preprocessor.usage_records) == 0
            assert preprocessor.get_telemetry_summary() == {}

    def test_vague_tool_skipped_when_no_keywords_match(self):
        """Tools with vague descriptions are skipped, not run everywhere."""
        from src.brain.tool_preprocessor import ToolPreprocessor

        vague_tool = '''
SCHEMA = {
    "name": "test_vague",
    "description": "A generic helper utility.",
    "parameters": {
        "current_hp": {"type": "int", "description": "HP"},
    },
}

def execute(current_hp: int = 0, **kwargs) -> str:
    return f"HP={current_hp}"
'''
        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            (tools_dir / "vague.py").write_text(vague_tool, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry)
            gs = _make_gs(state_type="monster", player_hp=50)

            hints = preprocessor.run_applicable("monster", gs)
            # Vague tool should be skipped (no keyword match for monster)
            assert len(hints) == 0

    def test_max_tools_limit(self):
        from src.brain.tool_preprocessor import ToolPreprocessor

        with tempfile.TemporaryDirectory() as td:
            tools_dir = Path(td)
            # Create 8 state-derived tools (more than max_tools=5)
            # Description must have 2+ combat keywords to pass applicability
            for i in range(8):
                code = f'''
SCHEMA = {{
    "name": "tool_{i}",
    "description": "Check combat damage survival for enemy turn {i}.",
    "parameters": {{
        "current_hp": {{"type": "int", "description": "HP"}},
    }},
}}

def execute(current_hp: int = 0, **kwargs) -> str:
    return f"tool_{i}: HP={{current_hp}}"
'''
                (tools_dir / f"tool_{i}.py").write_text(code, encoding="utf-8")

            registry = DynamicToolRegistry(tools_dir)
            registry.load_all()

            preprocessor = ToolPreprocessor(registry, max_tools=5)
            gs = _make_gs(state_type="monster", player_hp=50)

            hints = preprocessor.run_applicable("monster", gs)
            assert len(hints) <= 5


class TestRealToolsIntegration:
    """Verify preprocessor works with real tools from data/evolution/tools/."""

    def test_real_tools_produce_hints(self):
        from src.brain.tool_preprocessor import ToolPreprocessor
        from src.storage import paths

        real_dir = paths.evolution_tools_dir()
        if not real_dir.exists():
            return  # Skip if no real tools

        registry = DynamicToolRegistry(real_dir)
        loaded = registry.load_all()
        if loaded == 0:
            return

        preprocessor = ToolPreprocessor(registry)
        gs = _make_gs(
            state_type="monster",
            player_hp=30,
            block=0,
        )

        hints = preprocessor.run_applicable("monster", gs)
        # Should produce at least some hints from the 9 state_derived tools
        assert len(hints) > 0, (
            f"Expected hints from state_derived tools, got 0 from {loaded} loaded tools"
        )

        text = preprocessor.format_hints(hints)
        assert "## Computed Insights" in text
