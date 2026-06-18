"""Star-budget verification for Regent CombatPlans.

The PlanVerifier must flag plans that overspend Stars (the Regent's persistent
second resource) so the agent re-plans before executing a sequence that would
fail mid-turn. Energy is spent and reset each turn, but Stars carry across
turns and into deck-building, so a star miscount has higher blast radius.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.planner import CombatPlan, PlannedAction
from src.brain.plan_verifier import PlanVerifier, _check_regent_star_budget
from src.mcp_client.upstream_models import (
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState


def _hand_card(
    name: str,
    index: int,
    *,
    star_cost: int = 0,
    star_costs_x: bool = False,
    energy_cost: int = 1,
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        star_cost=star_cost,
        star_costs_x=star_costs_x,
        playable=True,
        damage=6,
        requires_target=True,
        target_index_space="enemies",
    )


def _regent_combat_gs(
    hand: list[RawCombatHandCardPayload],
    *,
    stars: int,
    character_name: str = "The Regent",
) -> GameState:
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(current_hp=70, max_hp=80, energy=3, stars=stars),
        hand=hand,
        enemies=[],
    )
    run = RawRunPayload(
        character_id="the_regent",
        character_name=character_name,
        floor=4,
        current_hp=70,
        max_hp=80,
        gold=99,
        max_energy=3,
        deck=[],
    )
    raw = UpstreamGameState(
        screen="MONSTER",
        in_combat=True,
        turn=1,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )
    return GameState(raw=raw, state_type="monster")


# ── Direct-call tests on the rule ─────────────────────────────────


def test_overspend_with_zero_stars_warns_high():
    hand = [_hand_card("Stardust", 0, star_cost=2)]
    gs = _regent_combat_gs(hand, stars=0)
    plan = CombatPlan(
        actions=(PlannedAction(action_type="card", card_name="Stardust", target_index=0),),
        end_turn=True,
    )

    result = _check_regent_star_budget(plan, gs)

    assert result is not None
    assert result["severity"] == "high"
    assert "Stardust" in result["warning"]
    assert "short by 2" in result["warning"]


def test_within_budget_returns_none():
    hand = [_hand_card("Stardust", 0, star_cost=2)]
    gs = _regent_combat_gs(hand, stars=2)
    plan = CombatPlan(
        actions=(PlannedAction(action_type="card", card_name="Stardust", target_index=0),),
        end_turn=True,
    )

    assert _check_regent_star_budget(plan, gs) is None


def test_provider_credits_funds_later_consumer():
    """Venerate (provider, +1) then Stardust (cost 2) starting from 1 Star: net 0, valid."""
    hand = [
        _hand_card("Venerate", 0, star_cost=0),
        _hand_card("Stardust", 1, star_cost=2),
    ]
    gs = _regent_combat_gs(hand, stars=1)
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Venerate", target_index=-1),
            PlannedAction(action_type="card", card_name="Stardust", target_index=0),
        ),
        end_turn=True,
    )

    assert _check_regent_star_budget(plan, gs) is None


def test_provider_after_consumer_does_not_save_overspend():
    """Sequence matters: spending before the provider arrives is still invalid."""
    hand = [
        _hand_card("Stardust", 0, star_cost=2),
        _hand_card("Venerate", 1, star_cost=0),
    ]
    gs = _regent_combat_gs(hand, stars=1)
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Stardust", target_index=0),
            PlannedAction(action_type="card", card_name="Venerate", target_index=-1),
        ),
        end_turn=True,
    )

    result = _check_regent_star_budget(plan, gs)

    assert result is not None
    assert result["severity"] == "high"


def test_x_cost_with_zero_stars_warns():
    hand = [_hand_card("Radiate", 0, star_cost=0, star_costs_x=True)]
    gs = _regent_combat_gs(hand, stars=0)
    plan = CombatPlan(
        actions=(PlannedAction(action_type="card", card_name="Radiate", target_index=0),),
        end_turn=True,
    )

    result = _check_regent_star_budget(plan, gs)

    assert result is not None
    assert result["severity"] == "high"


def test_non_regent_skipped():
    """Silent / Ironclad runs must not trigger the rule."""
    hand = [_hand_card("Stardust", 0, star_cost=2)]
    gs = _regent_combat_gs(hand, stars=0, character_name="The Silent")
    plan = CombatPlan(
        actions=(PlannedAction(action_type="card", card_name="Stardust", target_index=0),),
        end_turn=True,
    )

    assert _check_regent_star_budget(plan, gs) is None


def test_empty_plan_is_safe():
    gs = _regent_combat_gs([], stars=0)
    plan = CombatPlan(actions=(), end_turn=True)

    assert _check_regent_star_budget(plan, gs) is None


# ── Integration via PlanVerifier.verify() ─────────────────────────


def test_verify_propagates_star_overspend_to_needs_replan():
    hand = [_hand_card("Stardust", 0, star_cost=2)]
    gs = _regent_combat_gs(hand, stars=0)
    plan = CombatPlan(
        actions=(PlannedAction(action_type="card", card_name="Stardust", target_index=0),),
        end_turn=True,
    )

    registry = MagicMock()
    registry.names.return_value = []
    verifier = PlanVerifier(registry)

    result = verifier.verify(plan, gs, combat_state_type="monster")

    assert result.needs_replan is True
    assert any("star_check" in w for w in result.warnings)
