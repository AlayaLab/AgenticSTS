"""Unit tests for V2Engine, helper functions, CombatPlan, and RunState.

Covers:
  - V2Engine: decision parsing, combat plan generation, backend calls
  - V2Engine helpers: _clean_params, _is_transient_llm_error, _should_retry_llm_error
  - CombatPlan / PlannedAction: construction and parsing
  - RunState: decision tracking, fitness scoring
  - format_power_with_description: power text formatting
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import config
import src.brain.v2_engine as v2_engine_module
from src.brain.conversation import CombatConversation
from src.brain.planner import CombatPlan, PlannedAction, parse_combat_plan
from src.brain.tool_executor import ToolExecutor
from src.brain.v2_engine import (
    V2Engine,
    _clean_params,
    _is_transient_llm_error,
    _should_retry_llm_error,
)
from src.knowledge.power_lookup import format_power_with_description
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState
from src.state.run_state import Decision, FloorSnapshot, RunState


# ── Mock helpers ─────────────────────────────────────────────────


class MockUsage:
    def __init__(self, input_tokens: int = 100, output_tokens: int = 50):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens
        self.cache_read_input_tokens = 0
        self.cache_creation_input_tokens = 0


class MockTextBlock:
    def __init__(self, text: str):
        self.type = "text"
        self.text = text


class MockToolUseBlock:
    def __init__(self, tool_id: str, name: str, tool_input: dict):
        self.type = "tool_use"
        self.id = tool_id
        self.name = name
        self.input = tool_input


class MockMessage:
    """Mimics anthropic.Message for V2Backend response."""

    def __init__(
        self,
        content: list[Any],
        stop_reason: str = "end_turn",
        usage: MockUsage | None = None,
    ):
        self.content = content
        self.stop_reason = stop_reason
        self.usage = usage or MockUsage()


async def _immediate_sleep(_delay: float) -> None:
    return None


# ── Local GameState helpers ──────────────────────────────────────


def _make_enemy(
    name: str = "Test Louse",
    index: int = 0,
    hp: int = 30,
    max_hp: int = 30,
    is_alive: bool = True,
) -> RawCombatEnemyPayload:
    return RawCombatEnemyPayload(
        index=index,
        enemy_id=name.lower().replace(" ", "_"),
        name=name,
        current_hp=hp,
        max_hp=max_hp,
        block=0,
        is_alive=is_alive,
    )


def _make_hand_card(
    name: str = "Strike",
    index: int = 0,
    energy_cost: int = 1,
    playable: bool = True,
    damage: int | None = 6,
    rules_text: str = "Deal 6 damage.",
    requires_target: bool = True,
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        playable=playable,
        damage=damage,
        rules_text=rules_text,
        requires_target=requires_target,
        target_index_space="enemies" if requires_target else None,
    )


def _make_deck_card(
    name: str = "Strike",
    index: int = 0,
    card_type: str = "Attack",
    energy_cost: int = 1,
    rarity: str = "Starter",
) -> RawDeckCardPayload:
    return RawDeckCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        card_type=card_type,
        energy_cost=energy_cost,
        rarity=rarity,
        rules_text=f"{name} description.",
    )


def _make_combat_gs(
    enemies: list[RawCombatEnemyPayload] | None = None,
    hand: list[RawCombatHandCardPayload] | None = None,
    player_hp: int = 60,
    player_max_hp: int = 80,
    energy: int = 3,
    floor: int = 6,
    state_type_hint: str = "boss",
    turn: int = 1,
    deck: list[RawDeckCardPayload] | None = None,
) -> GameState:
    """Build a GameState suitable for combat tests."""
    if enemies is None:
        enemies = [_make_enemy()]
    if hand is None:
        hand = [
            _make_hand_card("Strike", 0),
            _make_hand_card(
                "Defend", 1, damage=None, rules_text="Gain 5 block.", requires_target=False
            ),
        ]
    if deck is None:
        deck = [_make_deck_card("Strike", 0), _make_deck_card("Defend", 1, card_type="Skill")]

    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(
            current_hp=player_hp,
            max_hp=player_max_hp,
            energy=energy,
        ),
        hand=hand,
        enemies=enemies,
    )

    run = RawRunPayload(
        character_id="ironclad",
        character_name="Ironclad",
        floor=floor,
        current_hp=player_hp,
        max_hp=player_max_hp,
        gold=120,
        max_energy=3,
        deck=deck,
        potions=[],
    )

    raw = UpstreamGameState(
        screen=state_type_hint.upper(),
        in_combat=True,
        turn=turn,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )

    return GameState(raw=raw, state_type=state_type_hint)


def _make_noncombat_gs(
    state_type: str = "map",
    floor: int = 6,
    hp: int = 60,
    max_hp: int = 80,
) -> GameState:
    """Build a non-combat GameState for map/rest/event/etc. tests."""
    run = RawRunPayload(
        character_id="ironclad",
        character_name="Ironclad",
        floor=floor,
        current_hp=hp,
        max_hp=max_hp,
        gold=120,
        max_energy=3,
        deck=[_make_deck_card()],
    )
    raw = UpstreamGameState(
        screen=state_type.upper(),
        run=run,
        available_actions=["choose_map_node"],
    )
    return GameState(raw=raw, state_type=state_type)


# ═══════════════════════════════════════════════════════════════
# V2Engine tests
# ═══════════════════════════════════════════════════════════════


class TestV2Engine:
    """Tests for V2Engine with mocked backend."""

    def _make_engine(self) -> tuple[V2Engine, MagicMock, ToolExecutor]:
        """Create a V2Engine with mocked dependencies."""
        mock_backend = MagicMock()
        # Wire up extract_text to pull text from MockMessage
        mock_backend.extract_text = MagicMock(side_effect=self._extract_text)
        mock_backend._is_openai_failover_error = MagicMock(return_value=False)

        executor = ToolExecutor()  # All deps None, but handlers never raise

        engine = V2Engine(
            backend=mock_backend,
            tool_executor=executor,
        )
        return engine, mock_backend, executor

    @staticmethod
    def _extract_text(response: MockMessage) -> str:
        """Mimics V2Backend.extract_text -- returns text from first text block."""
        for block in response.content:
            if getattr(block, "type", None) == "text":
                return block.text.strip()
        return ""

    @staticmethod
    def _decision_text(decision_dict: dict) -> str:
        """Wrap a decision dict in a <decision> block as the new engine expects."""
        import json as _json
        return f"<decision>{_json.dumps(decision_dict)}</decision>"

    def test_decide_noncombat_calls_backend(self):
        """decide_noncombat should call backend and return LLMDecision when decision tag used."""
        engine, mock_backend, _ = self._make_engine()

        # Backend returns text with <decision> block
        decision_json = {"action": "choose_map_node", "option_index": 2, "reasoning": "best path"}
        decision_response = MockMessage(
            content=[MockTextBlock(self._decision_text(decision_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=decision_response)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        assert result.action_name == "choose_map_node"
        assert result.params["option_index"] == 2
        assert result.reasoning == "best path"

    def test_decide_noncombat_prepends_extra_context(self):
        """decide_noncombat should include computed insights in the user prompt."""
        engine, mock_backend, _ = self._make_engine()

        decision_json = {"action": "choose_map_node", "option_index": 1, "reasoning": "best path"}
        decision_response = MockMessage(
            content=[MockTextBlock(self._decision_text(decision_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=decision_response)

        extra = "## Computed Insights\n**route_check**: Prefer more combats."

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(
                gs,
                "Choose a map node.",
                extra_context=extra,
            )

        result = asyncio.run(run())

        assert result is not None
        sent_messages = mock_backend.acall.await_args.kwargs["messages"]
        user_content = sent_messages[0]["content"]
        assert extra in user_content
        assert user_content.index(extra) < user_content.index("Choose a map node.")

    def test_decide_noncombat_routes_provider_and_model_by_tier(self, monkeypatch):
        """decide_noncombat should pass the configured tier provider/model to the backend."""
        engine, mock_backend, _ = self._make_engine()

        decision_json = {"action": "choose_map_node", "option_index": 1, "reasoning": "best path"}
        decision_response = MockMessage(
            content=[MockTextBlock(self._decision_text(decision_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=decision_response)

        monkeypatch.setattr(config, "LLM_FAST_PROVIDER", "openai_compatible")
        monkeypatch.setattr(config, "LLM_FAST_MODEL", "kimi-k2.5")
        # Rebuild router chains so it picks up the monkeypatched model
        from src.brain.llm_router import get_router, reset_router
        reset_router()
        get_router().rebuild_chains()

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        sent_kwargs = mock_backend.acall.await_args.kwargs
        assert sent_kwargs["provider"] == "openai_compatible"
        assert sent_kwargs["model"] == "kimi-k2.5"
        # Clean up: reset router for subsequent tests
        reset_router()

    def test_decide_noncombat_passes_first_chunk_callback_when_logger_attached(self):
        """decide_noncombat should wire first-chunk telemetry into backend calls."""
        engine, mock_backend, _ = self._make_engine()

        decision_json = {"action": "choose_map_node", "option_index": 1, "reasoning": "best path"}
        decision_response = MockMessage(
            content=[MockTextBlock(self._decision_text(decision_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=decision_response)
        mock_logger = MagicMock()
        engine.set_session_logger(mock_logger)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        sent_kwargs = mock_backend.acall.await_args.kwargs
        callback = sent_kwargs["on_first_chunk"]
        assert callable(callback)
        callback({"transport": "openai_stream"})
        mock_logger.log_llm_first_chunk.assert_called_once()

    def test_decide_noncombat_returns_none_on_empty(self):
        """decide_noncombat should return None when backend produces no decision."""
        engine, mock_backend, _ = self._make_engine()

        # Backend returns text-only response with no parseable JSON
        text_response = MockMessage(
            content=[MockTextBlock("I'm not sure what to do.")],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=text_response)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())
        assert result is None

    def test_decide_noncombat_retries_on_timeout(self, monkeypatch):
        """decide_noncombat should retry transient timeout errors before failing."""
        engine, mock_backend, _ = self._make_engine()

        decision_json = {
            "action": "choose_map_node",
            "option_index": 1,
            "reasoning": "retry worked",
        }
        decision_response = MockMessage(
            content=[MockTextBlock(self._decision_text(decision_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(
            side_effect=[
                Exception("The read operation timed out"),
                decision_response,
            ]
        )
        monkeypatch.setattr(v2_engine_module.asyncio, "sleep", _immediate_sleep)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        assert result.action_name == "choose_map_node"
        assert mock_backend.acall.await_count == 2

    def test_decide_noncombat_keeps_retrying_until_upstream_error_recovers(self, monkeypatch):
        """Retryable upstream failures should not stop after the old two-attempt limit."""
        engine, mock_backend, _ = self._make_engine()

        response = MockMessage(
            content=[MockTextBlock(self._decision_text({
                "action": "choose_map_node",
                "option_index": 1,
                "reasoning": "eventually worked",
            }))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(
            side_effect=[
                Exception("The read operation timed out"),
                Exception("The read operation timed out"),
                Exception("The read operation timed out"),
                response,
            ]
        )
        monkeypatch.setattr(v2_engine_module.asyncio, "sleep", _immediate_sleep)
        monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)
        monkeypatch.setattr(config, "LLM_RETRY_BASE_DELAY_SEC", 0.01)
        monkeypatch.setattr(config, "LLM_RETRY_MAX_DELAY_SEC", 0.02)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        assert result.action_name == "choose_map_node"
        assert mock_backend.acall.await_count == 4

    def test_decide_noncombat_retries_on_openai_upstream_400(self, monkeypatch):
        """OpenAI-compatible upstream 400s should be retried when backend marks them retryable."""
        engine, mock_backend, _ = self._make_engine()

        request = httpx.Request("POST", "https://relay.example/v1/chat/completions")
        response = httpx.Response(
            400,
            request=request,
            text='{"error":{"message":"Invalid project resource name","type":"upstream_error"}}',
        )
        exc = httpx.HTTPStatusError("400 upstream", request=request, response=response)
        mock_backend.acall = AsyncMock(side_effect=[exc, MockMessage(
            content=[MockTextBlock(self._decision_text({
                "action": "choose_map_node",
                "option_index": 2,
                "reasoning": "retried after upstream 400",
            }))],
            stop_reason="end_turn",
        )])
        mock_backend._is_openai_failover_error.return_value = True
        monkeypatch.setattr(v2_engine_module.asyncio, "sleep", _immediate_sleep)
        monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)
        monkeypatch.setattr(config, "LLM_RETRY_BASE_DELAY_SEC", 0.01)
        monkeypatch.setattr(config, "LLM_RETRY_MAX_DELAY_SEC", 0.02)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        assert result.params["option_index"] == 2
        assert mock_backend.acall.await_count == 2

    def test_decide_noncombat_retries_repair_turn_on_upstream_timeout(self, monkeypatch):
        """Repair-turn upstream timeouts should stay on the same paced retry path."""
        engine, mock_backend, _ = self._make_engine()

        invalid_response = MockMessage(
            content=[MockTextBlock("I forgot the decision tag.")],
            stop_reason="end_turn",
        )
        repaired_response = MockMessage(
            content=[MockTextBlock(self._decision_text({
                "action": "choose_map_node",
                "option_index": 0,
                "reasoning": "repair eventually worked",
            }))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(
            side_effect=[
                invalid_response,
                Exception("The read operation timed out"),
                repaired_response,
            ]
        )
        monkeypatch.setattr(v2_engine_module.asyncio, "sleep", _immediate_sleep)
        monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)
        monkeypatch.setattr(config, "LLM_RETRY_BASE_DELAY_SEC", 0.01)
        monkeypatch.setattr(config, "LLM_RETRY_MAX_DELAY_SEC", 0.02)

        async def run():
            gs = _make_noncombat_gs("map")
            return await engine.decide_noncombat(gs, "Choose a map node.")

        result = asyncio.run(run())

        assert result is not None
        assert result.params["option_index"] == 0
        assert mock_backend.acall.await_count == 3

    def test_generate_combat_plan(self):
        """generate_combat_plan should return a CombatPlan from text <decision> response."""
        engine, mock_backend, _ = self._make_engine()

        plan_json = {
            "plan": [
                {"type": "card", "card": "Strike", "target_index": 0},
                {"type": "card", "card": "Defend", "target_index": -1},
            ],
            "end_turn": True,
            "reasoning": "kill the louse",
            "analysis": {
                "problem": "Must deal damage.",
                "key_observations": ["Strike kills.", "Defend blocks."],
                "candidate_lines": ["Strike then Defend", "Defend then Strike"],
                "chosen_line": "Strike first for lethal.",
            },
        }
        plan_response = MockMessage(
            content=[MockTextBlock(self._decision_text(plan_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=plan_response)

        conv = CombatConversation(system_prompt="test combat")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)

        async def run():
            return await engine.generate_combat_plan(conv)

        plan = asyncio.run(run())

        assert plan is not None
        assert isinstance(plan, CombatPlan)
        assert len(plan.actions) == 2
        assert plan.actions[0].card_name == "Strike"
        assert plan.actions[0].target_index == 0
        assert plan.actions[1].card_name == "Defend"
        assert plan.end_turn is True

    def test_generate_combat_plan_sends_only_anchor_and_current_round(self):
        """Combat planning should trim prior-round detailed history before the LLM call."""
        engine, mock_backend, _ = self._make_engine()

        plan_json = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "end_turn": True,
            "reasoning": "finish the turn",
        }
        plan_response = MockMessage(
            content=[MockTextBlock(self._decision_text(plan_json))],
            stop_reason="end_turn",
        )
        mock_backend.acall = AsyncMock(return_value=plan_response)

        conv = CombatConversation(system_prompt="test combat")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)
        conv.add_assistant_plan([{"type": "text", "text": "round 1 plan"}])
        conv.add_execution_result(["Played Strike -> Louse[0]"], gs)
        conv.record_strategic_note(1, "Block first next round.")

        gs_round_2 = _make_combat_gs(turn=2)
        conv.add_round_state(gs_round_2)

        async def run():
            return await engine.generate_combat_plan(conv)

        plan = asyncio.run(run())

        assert plan is not None
        sent_messages = mock_backend.acall.await_args.kwargs["messages"]
        assert len(sent_messages) == 3
        assert sent_messages[0]["role"] == "user"
        assert sent_messages[1]["role"] == "assistant"
        assert sent_messages[2]["role"] == "user"

        latest_user = sent_messages[2]["content"]
        assert "## Strategic Thread" in latest_user
        assert "R1: Block first next round." in latest_user
        assert "round 1 plan" not in latest_user
        assert "Executed:" not in latest_user

    def test_generate_combat_plan_returns_none_on_failure(self):
        """generate_combat_plan should return None when backend fails."""
        engine, mock_backend, _ = self._make_engine()

        mock_backend.acall = AsyncMock(side_effect=Exception("API error"))

        conv = CombatConversation(system_prompt="test")
        gs = _make_combat_gs()
        conv.add_combat_start(gs)
        conv.add_round_state(gs)

        async def run():
            return await engine.generate_combat_plan(conv)

        plan = asyncio.run(run())
        assert plan is None

    def test_set_session_logger(self):
        """set_session_logger should update the logger reference."""
        engine, _, _ = self._make_engine()
        assert engine._session_logger is None

        mock_logger = MagicMock()
        engine.set_session_logger(mock_logger)
        assert engine._session_logger is mock_logger


# ═══════════════════════════════════════════════════════════════
# V2Engine helper function tests
# ═══════════════════════════════════════════════════════════════


class TestV2EngineHelpers:
    """Tests for module-level helper functions in v2_engine."""

    def test_clean_params_removes_sentinels(self):
        """_clean_params should strip -1 and '' sentinel values."""
        params = {"option_index": 2, "target_index": -1, "reasoning": ""}
        cleaned = _clean_params(params)
        assert cleaned == {"option_index": 2}

    def test_is_transient_llm_error_treats_timeouts_as_retryable(self):
        """Timeout-style transport errors should be treated as transient."""
        assert _is_transient_llm_error("The read operation timed out") is True

    def test_should_retry_llm_error_uses_backend_marker_for_openai_400(self):
        """Retry helper should honor backend upstream classification for OpenAI relays."""
        request = httpx.Request("POST", "https://relay.example/v1/chat/completions")
        response = httpx.Response(400, request=request, text='{"error":{"type":"upstream_error"}}')
        exc = httpx.HTTPStatusError("400 upstream", request=request, response=response)
        backend = MagicMock()
        backend._is_openai_failover_error.return_value = True

        assert _should_retry_llm_error(
            exc,
            provider="openai_compatible",
            backend=backend,
        ) is True

    def test_clean_params_preserves_valid(self):
        """_clean_params should keep non-sentinel values."""
        params = {"action": "play_card", "card_index": 0, "target_index": 0}
        cleaned = _clean_params(params)
        assert cleaned == params

    def test_parse_decision_valid(self):
        """_parse_decision should produce an LLMDecision from valid input."""
        decision_input = {
            "action": "choose_map_node",
            "option_index": 2,
            "reasoning": "safest path",
        }
        result = V2Engine._parse_decision(decision_input, prompt_text="test prompt")

        assert result is not None
        assert result.action_name == "choose_map_node"
        assert result.params == {"option_index": 2}
        assert result.reasoning == "safest path"

    def test_parse_decision_no_action(self):
        """_parse_decision should return None when 'action' is missing."""
        result = V2Engine._parse_decision({"option_index": 1})
        assert result is None

    def test_parse_decision_strips_sentinels(self):
        """_parse_decision should strip sentinel values from params."""
        decision_input = {
            "action": "choose_event_option",
            "option_index": 0,
            "target_index": -1,
            "reasoning": "best option",
        }
        result = V2Engine._parse_decision(decision_input)
        assert result is not None
        assert "target_index" not in result.params

    def test_parse_combat_plan_valid(self):
        """_parse_combat_plan should produce a CombatPlan from valid input."""
        plan_input = {
            "plan": [
                {"type": "card", "card": "Strike", "target_index": 0},
                {"type": "potion", "potion_index": 0, "target_index": 0},
            ],
            "end_turn": True,
            "reasoning": "kill it",
            "analysis": {
                "problem": "Need to reduce incoming while preserving damage.",
                "key_observations": [
                    "Incoming is manageable with one block card.",
                    "Potion secures faster lethal.",
                ],
                "candidate_lines": [
                    "Strike then potion",
                    "Potion then Strike",
                ],
                "chosen_line": "Strike first keeps the potion flexible.",
            },
        }
        result = V2Engine._parse_combat_plan(plan_input)

        assert result is not None
        assert isinstance(result, CombatPlan)
        assert len(result.actions) == 2
        assert result.actions[0].card_name == "Strike"
        assert result.actions[1].is_potion is True
        assert result.end_turn is True
        assert result.analysis is not None
        assert result.analysis["chosen_line"] == "Strike first keeps the potion flexible."

    def test_parse_combat_plan_empty(self):
        """_parse_combat_plan with empty plan should produce an empty CombatPlan."""
        plan_input = {
            "plan": [],
            "end_turn": True,
            "reasoning": "nothing to play",
            "analysis": {
                "problem": "No legal plays.",
                "key_observations": [
                    "Hand is exhausted.",
                    "Ending turn is forced.",
                ],
                "candidate_lines": [
                    "End turn now",
                    "End turn after rechecking hand",
                ],
                "chosen_line": "End turn now because no actions exist.",
            },
        }
        result = V2Engine._parse_combat_plan(plan_input)

        assert result is not None
        assert result.is_empty is True
        assert result.end_turn is True
        assert result.analysis is not None
        assert result.analysis["problem"] == "No legal plays."

    def test_parse_combat_plan_empty_preserves_false_end_turn(self):
        """Parser should preserve end_turn=False for empty plans so callers can fall back."""
        plan_input = {
            "plan": [],
            "end_turn": False,
            "reasoning": "need a replan",
        }
        result = V2Engine._parse_combat_plan(plan_input)

        assert result is not None
        assert result.is_empty is True
        assert result.end_turn is False

    def test_parse_combat_plan_defaults_end_turn_and_stringifies_reasoning(self):
        """Parser should recover omitted end_turn and list-style reasoning."""
        plan_input = {
            "plan": [
                {"type": "card", "card": "Strike", "target_index": 0},
            ],
            "reasoning": [
                "Preserve tempo.",
                "Take the free damage line.",
            ],
        }
        result = V2Engine._parse_combat_plan(plan_input)

        assert result is not None
        assert result.end_turn is True
        assert result.reasoning == "Preserve tempo. Take the free damage line."

    def test_content_to_dicts_text_block(self):
        """_content_to_dicts should convert text blocks."""
        blocks = [MockTextBlock("hello")]
        result = V2Engine._content_to_dicts(blocks)
        assert result == [{"type": "text", "text": "hello"}]

    def test_content_to_dicts_tool_use_block(self):
        """_content_to_dicts should convert tool_use blocks."""
        blocks = [MockToolUseBlock("id1", "read_guide", {"topic": "combat"})]
        result = V2Engine._content_to_dicts(blocks)
        assert result == [
            {
                "type": "tool_use",
                "id": "id1",
                "name": "read_guide",
                "input": {"topic": "combat"},
            }
        ]

    def test_extract_thinking(self):
        """_extract_thinking should return thinking text when present."""

        class MockThinkingBlock:
            type = "thinking"
            thinking = "deep analysis of the situation"

        response = MockMessage(
            content=[MockThinkingBlock(), MockTextBlock("final answer")],
        )
        result = V2Engine._extract_thinking(response)
        assert result == "deep analysis of the situation"

    def test_extract_thinking_no_thinking(self):
        """_extract_thinking should return '' when no thinking block."""
        response = MockMessage(content=[MockTextBlock("just text")])
        result = V2Engine._extract_thinking(response)
        assert result == ""

    def test_select_prompt_text_for_logging_prefers_latest_round_state(self):
        """Logging should prefer the most recent round-state user message."""
        messages = [
            {"role": "user", "content": "## Combat Start\n...\n\n## Round 1 State\nHP: 70/70"},
            {"role": "assistant", "content": [{"type": "text", "text": "plan 1"}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}],
            },
            {"role": "assistant", "content": [{"type": "text", "text": "plan 2"}]},
            {"role": "user", "content": "## Round 2 State\nHP: 65/70\n## Hand\n- Strike"},
        ]

        result = V2Engine._select_prompt_text_for_logging(messages)
        assert result.startswith("## Round 2 State")

    def test_select_prompt_text_for_logging_skips_tool_results_and_nudges(self):
        """Logging should ignore tool_result-only user messages and internal nudges."""
        messages = [
            {"role": "user", "content": "Choose a map node.\nOption A\nOption B"},
            {"role": "assistant", "content": [{"type": "text", "text": "let me research"}]},
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "enemy info"}],
            },
            {
                "role": "user",
                "content": (
                    "You have used all your research rounds. "
                    "You MUST now call `map_action` to commit your decision."
                ),
            },
        ]

        result = V2Engine._select_prompt_text_for_logging(messages)
        assert result == "Choose a map node.\nOption A\nOption B"

    def test_select_prompt_text_for_logging_extracts_text_from_multipart_user_content(self):
        """Logging should extract text blocks from multipart user content."""
        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "## Round 3 State\nEnergy: 2/3"},
                    {"type": "tool_result", "tool_use_id": "t2", "content": "ignored"},
                ],
            },
        ]

        result = V2Engine._select_prompt_text_for_logging(messages)
        assert result == "## Round 3 State\nEnergy: 2/3"

    def test_select_prompt_text_for_logging_returns_empty_when_no_textual_user_message(self):
        """Logging should return '' when user messages contain no text."""
        messages = [
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "only tools"}],
            },
        ]

        result = V2Engine._select_prompt_text_for_logging(messages)
        assert result == ""


# ═══════════════════════════════════════════════════════════════
# CombatPlan / PlannedAction tests
# ═══════════════════════════════════════════════════════════════


class TestCombatPlan:
    """Tests for CombatPlan and parse_combat_plan."""

    def test_planned_action_card(self):
        """PlannedAction for a card should have correct properties."""
        action = PlannedAction(action_type="card", card_name="Bash", target_index=0)
        assert action.is_potion is False
        assert action.card_name == "Bash"
        assert action.target_index == 0

    def test_planned_action_potion(self):
        """PlannedAction for a potion should flag is_potion."""
        action = PlannedAction(action_type="potion", potion_index=1, target_index=0)
        assert action.is_potion is True
        assert action.potion_index == 1

    def test_combat_plan_is_empty(self):
        """CombatPlan with no actions should be empty."""
        plan = CombatPlan(actions=(), end_turn=True)
        assert plan.is_empty is True

    def test_combat_plan_not_empty(self):
        """CombatPlan with actions should not be empty."""
        plan = CombatPlan(
            actions=(PlannedAction(card_name="Strike", target_index=0),),
            end_turn=True,
        )
        assert plan.is_empty is False

    def test_parse_combat_plan_from_json(self):
        """parse_combat_plan should handle standard JSON plan."""
        raw = json.dumps(
            {
                "plan": [
                    {"type": "card", "card": "Bash", "target_index": 0},
                    {"type": "card", "card": "Strike", "target_index": 0},
                ],
                "end_turn": True,
                "reasoning": "apply vulnerable then strike",
                "analysis": {
                    "problem": "Maximize frontload this turn.",
                    "key_observations": [
                        "Bash adds Vulnerable for follow-up damage.",
                        "Energy allows both attacks.",
                    ],
                    "candidate_lines": [
                        "Bash then Strike",
                        "Strike then Bash",
                    ],
                    "chosen_line": "Bash first improves the Strike.",
                },
            }
        )
        plan = parse_combat_plan(raw)
        assert plan is not None
        assert len(plan.actions) == 2
        assert plan.actions[0].card_name == "Bash"
        assert plan.actions[1].card_name == "Strike"
        assert plan.end_turn is True
        assert plan.analysis is not None
        assert plan.analysis["chosen_line"] == "Bash first improves the Strike."

    def test_parse_combat_plan_accepts_potion_name_without_index(self):
        """Potion plans should survive parsing when the model omits the slot index."""
        raw = json.dumps(
            {
                "plan": [
                    {"type": "potion", "potion": "Attack Potion", "target_index": -1},
                ],
                "end_turn": False,
                "reasoning": "use the potion first",
            }
        )

        plan = parse_combat_plan(raw)

        assert plan is not None
        assert len(plan.actions) == 1
        assert plan.actions[0].is_potion is True
        assert plan.actions[0].potion_index is None
        assert plan.actions[0].potion_name == "Attack Potion"
        assert plan.end_turn is False

    def test_parse_combat_plan_accepts_multi_discard_list(self):
        """Multi-discard effects should preserve all requested discard targets."""
        raw = json.dumps(
            {
                "plan": [
                    {
                        "type": "card",
                        "card": "Prepared+",
                        "target_index": -1,
                        "discard": ["Abrasive", "Untouchable+"],
                    },
                ],
                "end_turn": False,
                "reasoning": "Discard the two Sly cards for free value",
            }
        )

        plan = parse_combat_plan(raw)

        assert plan is not None
        assert len(plan.actions) == 1
        assert plan.actions[0].card_name == "Prepared+"
        assert plan.actions[0].discard == ("Abrasive", "Untouchable+")
        assert plan.end_turn is False


# ═══════════════════════════════════════════════════════════════
# Standalone power formatting tests
# ═══════════════════════════════════════════════════════════════


def test_format_power_with_description_clarifies_poison_timing():
    """Poison description should explicitly say it resolves before the target acts."""
    formatted = format_power_with_description("Poison", 7, "Poison")
    assert "before it acts (attack or buff)" in formatted


def test_format_power_with_description_prefers_dynamic_description():
    """Runtime-rendered power text should override stale static knowledge text."""
    formatted = format_power_with_description(
        "Skittish",
        6,
        "SkittishPower",
        "The first time this creature is hit each turn, it gains 6 Block.",
    )
    assert formatted == "Skittish(6): The first time this creature is hit each turn, it gains 6 Block."


# ═══════════════════════════════════════════════════════════════
# RunState tests
# ═══════════════════════════════════════════════════════════════


class TestRunState:
    """Tests for RunState accumulator."""

    def test_record_decision(self):
        """record_decision should append and track counts."""
        rs = RunState()
        d = Decision(floor=5, state_type="combat", action={"name": "play"}, source="llm")
        rs.record_decision(d)

        assert len(rs.decisions) == 1
        assert rs.total_actions == 1
        assert rs.llm_calls == 1

    def test_record_decision_random(self):
        """Random decisions should increment total_actions but not llm_calls."""
        rs = RunState()
        d = Decision(floor=3, state_type="map", action={"name": "node"}, source="random")
        rs.record_decision(d)

        assert rs.total_actions == 1
        assert rs.llm_calls == 0

    def test_llm_ratio(self):
        """llm_ratio should compute fraction of LLM decisions."""
        rs = RunState()
        rs.record_decision(Decision(floor=1, state_type="c", action={}, source="llm"))
        rs.record_decision(Decision(floor=2, state_type="c", action={}, source="random"))
        rs.record_decision(Decision(floor=3, state_type="c", action={}, source="llm"))
        rs.record_decision(Decision(floor=4, state_type="c", action={}, source="random"))

        assert rs.llm_ratio == pytest.approx(0.5)

    def test_llm_ratio_zero_actions(self):
        """llm_ratio with zero actions should return 0.0."""
        rs = RunState()
        assert rs.llm_ratio == 0.0

    def test_record_combat_result(self):
        """record_combat_result should track wins and total."""
        rs = RunState()
        rs.record_combat_result(won=True)
        rs.record_combat_result(won=False)
        rs.record_combat_result(won=True)

        assert rs.combats_won == 2
        assert rs.combats_total == 3

    def test_fitness_victory(self):
        """Victory should add 100 to fitness score."""
        rs = RunState(victory=True, final_floor=17, final_gold=100)
        rs.floor_snapshots.append(
            FloorSnapshot(floor=17, act=1, state_type="boss", hp=50, max_hp=80, gold=100)
        )
        score = rs.fitness()
        assert score >= 100.0  # 100 from victory alone

    def test_fitness_defeat(self):
        """Defeat should not add the 100-point victory bonus."""
        rs = RunState(victory=False, final_floor=5)
        rs.floor_snapshots.append(
            FloorSnapshot(floor=5, act=1, state_type="monster", hp=0, max_hp=80, gold=50)
        )
        score = rs.fitness()
        assert score < 100.0
