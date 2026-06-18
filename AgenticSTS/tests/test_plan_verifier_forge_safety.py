"""Sovereign Blade safety check for Regent CombatPlans.

The Regent's Sovereign Blade is a token attack that gains permanent damage
from every Forge play in the same combat. Exhausting or transforming a
*Forged* Blade (damage > 10) wipes all that investment. The PlanVerifier
must catch plans where the LLM's discard target lands on a Forged Blade
and force a re-plan before the play executes. An *unbuffed* Blade
(damage == 10) is fair game to exhaust, since fresh stacks can reapply.
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.planner import CombatPlan, PlannedAction
from src.brain.plan_verifier import (
    PlanVerifier,
    _check_regent_forge_safety,
)
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
    card_id: str | None = None,
    damage: int | None = None,
    energy_cost: int = 1,
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=card_id or name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        playable=True,
        damage=damage,
        requires_target=True,
        target_index_space="enemies",
    )


def _regent_combat_gs(
    hand: list[RawCombatHandCardPayload],
    *,
    character_name: str = "The Regent",
) -> GameState:
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(current_hp=70, max_hp=80, energy=3, stars=2),
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


def test_exhaust_forged_blade_warns_high():
    """Sovereign Blade at 14 dmg + plan exhausts it → severity=high warning."""
    hand = [
        _hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=14),
        _hand_card("Survivor", 1, energy_cost=1),
    ]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Survivor",
                target_index=-1,
                discard="Sovereign Blade",
            ),
        ),
        end_turn=True,
    )

    result = _check_regent_forge_safety(plan, gs)

    assert result is not None
    assert result["severity"] == "high"
    assert "Sovereign Blade" in result["warning"]
    assert "14" in result["warning"]
    assert "Survivor" in result["warning"]


def test_unbuffed_blade_exhaust_is_allowed():
    """Sovereign Blade at base 10 dmg → exhausting is a valid strategy, no warning."""
    hand = [
        _hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=10),
        _hand_card("Survivor", 1, energy_cost=1),
    ]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Survivor",
                target_index=-1,
                discard="Sovereign Blade",
            ),
        ),
        end_turn=True,
    )

    assert _check_regent_forge_safety(plan, gs) is None


def test_blade_in_hand_but_not_targeted_is_safe():
    """Blade is Forged but plan exhausts a different card → no warning."""
    hand = [
        _hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=14),
        _hand_card("Strike", 1),
        _hand_card("Survivor", 2, energy_cost=1),
    ]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Survivor",
                target_index=-1,
                discard="Strike",
            ),
        ),
        end_turn=True,
    )

    assert _check_regent_forge_safety(plan, gs) is None


def test_no_blade_in_hand_skipped():
    """No Sovereign Blade present → rule cannot apply."""
    hand = [_hand_card("Strike", 0)]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Strike",
                target_index=0,
                discard="Sovereign Blade",  # nonsense, but should not crash
            ),
        ),
        end_turn=True,
    )

    assert _check_regent_forge_safety(plan, gs) is None


def test_non_regent_skipped():
    hand = [_hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=14)]
    gs = _regent_combat_gs(hand, character_name="The Silent")
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Survivor",
                target_index=-1,
                discard="Sovereign Blade",
            ),
        ),
        end_turn=True,
    )

    assert _check_regent_forge_safety(plan, gs) is None


def test_tuple_discard_targets_blade():
    """Multi-target discards (Prepared+ etc.) flagged when Blade is in the tuple."""
    hand = [
        _hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=18),
        _hand_card("Prepared+", 1),
    ]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Prepared+",
                target_index=-1,
                discard=("Strike", "Sovereign Blade"),
            ),
        ),
        end_turn=True,
    )

    result = _check_regent_forge_safety(plan, gs)
    assert result is not None
    assert result["severity"] == "high"


# ── Integration via PlanVerifier.verify() ─────────────────────────


def test_verify_propagates_forge_unsafe_to_needs_replan():
    hand = [
        _hand_card("Sovereign Blade", 0, card_id="sovereign_blade", damage=16),
        _hand_card("Survivor", 1, energy_cost=1),
    ]
    gs = _regent_combat_gs(hand)
    plan = CombatPlan(
        actions=(
            PlannedAction(
                action_type="card",
                card_name="Survivor",
                target_index=-1,
                discard="Sovereign Blade",
            ),
        ),
        end_turn=True,
    )

    registry = MagicMock()
    registry.names.return_value = []
    verifier = PlanVerifier(registry)

    result = verifier.verify(plan, gs, combat_state_type="monster")

    assert result.needs_replan is True
    assert any("forge_safety_check" in w for w in result.warnings)
