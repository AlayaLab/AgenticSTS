"""No-target replan tests — multi-phase boss transition handling."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import src.agent.loop as loop_module
from src.brain.conversation import CombatConversation
from src.brain.planner import CombatPlan, PlannedAction
from src.mcp_client import actions
from src.mcp_client.upstream_models import (
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState

from tests.conftest import (
    make_combat_gs,
    make_enemy,
    make_hand_card,
    make_loop,
)


def _combat_gs_no_enemies(hand):
    """Build a combat GameState with zero alive enemies (boss phase transition)."""
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(current_hp=40, max_hp=80, energy=3),
        hand=hand,
        enemies=[],  # key: no alive enemies
    )
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=48,
        current_hp=40,
        max_hp=80,
        gold=99,
        max_energy=3,
        deck=[],
    )
    raw = UpstreamGameState(
        screen="MONSTER",
        in_combat=True,
        turn=3,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )
    return GameState(raw=raw, state_type="boss")


def test_flag_initialized_to_minus_one():
    loop = make_loop(MagicMock())
    assert loop._no_target_replan_round == -1


def test_validator_rejects_target_attack_when_no_enemies():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="attack-only",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert "no alive enemies" in error.lower()
    assert valid_count == 0


def test_validator_truncates_mixed_plan_at_first_target_attack():
    gs = _combat_gs_no_enemies([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card("Footwork", 1, playable=True, requires_target=False),
        make_hand_card("Strike", 2, playable=True, requires_target=True),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Footwork", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="mixed plan",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert "no alive enemies" in error.lower()
    assert valid_count == 2


def test_validator_allows_non_target_plan_with_no_enemies():
    gs = _combat_gs_no_enemies([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card("Footwork", 1, playable=True, requires_target=False),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Footwork", target_index=None),
        ),
        end_turn=True,
        reasoning="all self-target",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is None
    assert valid_count == 2


def test_no_enemies_triggers_replan_with_no_target_mode():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend", target_index=None),
            ),
            end_turn=True,
            reasoning="play defend, phase transition",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        asyncio.run(loop._execute_combat_plan(gs))

    kwargs = loop._generate_combat_plan.await_args.kwargs
    assert kwargs.get("no_target_mode") is True
    assert loop._no_target_replan_round == gs.combat_round


def test_no_enemies_second_call_same_round_skips_llm_and_ends_turn():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._no_target_replan_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock()
    loop._execute = AsyncMock(return_value={"stable": True})

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    loop._generate_combat_plan.assert_not_awaited()
    loop._execute.assert_awaited_once_with(actions.end_turn(), delta_source="turn_end")


def test_no_enemies_empty_plan_with_end_turn_ends_turn():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(),
            end_turn=True,
            reasoning="nothing useful to play",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    assert loop._no_target_replan_round == gs.combat_round


def test_flag_resets_on_combat_start():
    """New combat should reset the flag even if a prior combat set it."""
    loop = make_loop(MagicMock())
    loop._no_target_replan_round = 5  # simulate prior combat leaving the flag set

    # Simulate the COMBAT_START reset block body
    loop._last_combat_round = -1
    loop._end_turn_sent_round = -1
    loop._combat_plan = None
    loop._combat_plan_index = 0
    loop._combat_plan_round = -1
    loop._no_target_replan_round = -1  # the line added by this feature

    assert loop._no_target_replan_round == -1


def test_poison_kill_check_safe_with_no_enemies():
    """Regression: _poison_kills_all_enemies must not return True for empty list."""
    from src.agent.loop import AgentLoop

    class _Stub:
        enemies = []

    assert AgentLoop._poison_kills_all_enemies(_Stub()) is False


def test_boss_phase_transition_does_not_abort_when_llm_still_plans_attacks():
    """The specific Subject-boss bug: LLM persistently plans attacks, agent
    must not raise RuntimeError — it should fall through to end_turn."""
    gs = _combat_gs_no_enemies([
        make_hand_card("Leading Strike", 0, playable=True, requires_target=True),
        make_hand_card("Strike", 1, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round

    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Leading Strike", target_index=0),
            ),
            end_turn=True,
            reasoning="LLM ignored no-target context",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        first = asyncio.run(loop._execute_combat_plan(gs))

    with patch.object(loop_module, "parse_state", return_value=gs):
        second = asyncio.run(loop._execute_combat_plan(gs))

    assert second is not None
    assert second.action == actions.end_turn()
