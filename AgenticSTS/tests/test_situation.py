"""Tests for hand capability tagging.

Legacy classifier tests (classify_threat / classify_intent / classify_deck_stage),
SituationTag legacy-field serialization, hand_capability_similarity, and the
format_round_exemplar / format_upcoming_with_confidence helpers were removed
when cohort discovery was deleted in Phase H of the mistake-driven migration.
Only hand-capabilities coverage is retained — those primitives are still used
by the live combat pipeline.
"""

from src.memory.situation import (
    HandCapabilityTag,
    compute_hand_capabilities,
)

# ── compute_hand_capabilities ────────────────────────────────

def _make_card(
    name: str = "Strike",
    damage: int | None = None,
    block: int | None = None,
    energy_cost: int = 1,
    rules_text: str = "",
    playable: bool = True,
    hits: int | None = None,
    total_damage: int | None = None,
) -> dict:
    """Minimal card dict that mirrors RawCombatHandCardPayload fields."""
    return {
        "name": name,
        "damage": damage,
        "block": block,
        "energy_cost": energy_cost,
        "rules_text": rules_text,
        "playable": playable,
        "hits": hits,
        "total_damage": total_damage,
        "costs_x": False,
    }


class TestComputeHandCapabilities:
    def test_attack_hand(self):
        hand = [
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
            _make_card("Dagger Spray", damage=4, hits=2, total_damage=8),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=10, enemy_hp_lowest=25, energy=3)
        assert tag.attack_count == 3
        assert tag.block_count == 0
        assert tag.total_damage == 20  # 6 + 6 + 4*2
        assert tag.can_deal_12_plus is True
        assert tag.can_kill_this_turn is False  # 20 < 25
        assert tag.has_setup_only is False

    def test_defensive_hand_with_weak(self):
        hand = [
            _make_card("Neutralize", damage=3, rules_text="Apply 1 Weak", energy_cost=0),
            _make_card("Defend", block=5),
            _make_card("Defend+", block=8),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=12, enemy_hp_lowest=40, energy=3)
        assert tag.can_apply_weak is True
        assert tag.can_block_8_plus is True  # 5 + 8 = 13
        assert tag.can_block_full_incoming is True  # 13 >= 12
        assert tag.total_block == 13
        assert tag.zero_cost_count == 1

    def test_setup_only_hand(self):
        hand = [
            _make_card("Footwork", rules_text="Gain 2 Dexterity"),
            _make_card("Accuracy", rules_text="Gain 3 Shiv damage"),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=6, enemy_hp_lowest=40, energy=3)
        assert tag.has_setup_only is True
        assert tag.attack_count == 0
        assert tag.block_count == 0

    def test_draw_detection(self):
        hand = [_make_card("Backflip", block=5, rules_text="Draw 2 cards")]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=20, energy=3)
        assert tag.has_draw_or_retain is True

    def test_aoe_detection(self):
        hand = [_make_card("Dagger Spray", damage=4, hits=2,
                           rules_text="Deal damage to ALL enemies twice")]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=20, energy=3)
        assert tag.has_aoe is True

    def test_can_kill_this_turn(self):
        hand = [
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=15, energy=3)
        assert tag.can_kill_this_turn is True
        assert tag.can_deal_12_plus is True

    def test_vulnerable_detection(self):
        hand = [_make_card("Bash", damage=8, rules_text="Apply 2 Vulnerable")]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=30, energy=3)
        assert tag.can_apply_vulnerable is True

    def test_playable_count(self):
        hand = [
            _make_card("Strike", damage=6, energy_cost=1, playable=True),
            _make_card("Strike", damage=6, energy_cost=1, playable=True),
            _make_card("Carnage", damage=20, energy_cost=2, playable=True),
            _make_card("Bludgeon", damage=32, energy_cost=3, playable=False),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=50, energy=3)
        assert tag.total_playable == 3  # Bludgeon not playable

    def test_energy_constrains_kill_capability(self):
        """3 Strikes (6 dmg each = 18 total) but only 2 energy → feasible 12 dmg."""
        hand = [
            _make_card("Strike", damage=6, energy_cost=1),
            _make_card("Strike", damage=6, energy_cost=1),
            _make_card("Strike", damage=6, energy_cost=1),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=15, energy=2)
        assert tag.total_damage == 18  # raw total unchanged
        assert tag.can_kill_this_turn is False  # feasible 12 < 15
        assert tag.can_deal_12_plus is True  # feasible 12 >= 12

    def test_energy_constrains_block_capability(self):
        """3 Defends (5 block each = 15 total) but only 1 energy → feasible 5 block."""
        hand = [
            _make_card("Defend", block=5, energy_cost=1),
            _make_card("Defend", block=5, energy_cost=1),
            _make_card("Defend", block=5, energy_cost=1),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=12, enemy_hp_lowest=40, energy=1)
        assert tag.total_block == 15  # raw total unchanged
        assert tag.can_block_full_incoming is False  # feasible 5 < 12
        assert tag.can_block_8_plus is False  # feasible 5 < 8

    def test_expensive_high_value_card_preferred(self):
        """2-cost 20-dmg card should be preferred over 1-cost 6-dmg for lethal check."""
        hand = [
            _make_card("Bludgeon", damage=20, energy_cost=2),
            _make_card("Strike", damage=6, energy_cost=1),
        ]
        # 2 energy: greedy-by-value picks Bludgeon (20 dmg) over Strike (6 dmg)
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=18, energy=2)
        assert tag.can_kill_this_turn is True  # 20 >= 18

    def test_exact_knapsack_beats_greedy(self):
        """Case where greedy-by-value fails but exact DP succeeds.

        Hand: 3-cost 10-dmg + 2-cost 7-dmg + 2-cost 7-dmg, energy=4.
        Greedy-by-value picks 10-dmg first (cost 3), leaving 1 energy → total 10.
        Optimal: two 7-dmg cards (cost 2+2=4) → total 14.
        """
        hand = [
            _make_card("Big Strike", damage=10, energy_cost=3),
            _make_card("Medium Strike", damage=7, energy_cost=2),
            _make_card("Medium Strike", damage=7, energy_cost=2),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=13, energy=4)
        assert tag.can_deal_12_plus is True   # 14 >= 12 (exact DP finds 7+7)
        assert tag.can_kill_this_turn is True  # 14 >= 13

    def test_mixed_damage_block_independent(self):
        """Damage and block feasibility use separate energy budgets."""
        hand = [
            _make_card("Strike", damage=15, energy_cost=2),
            _make_card("Defend", block=10, energy_cost=1),
        ]
        # 2 energy: can play Strike(2) for 15 dmg OR Defend(1) for 10 block — not both
        tag = compute_hand_capabilities(hand, total_incoming=8, enemy_hp_lowest=15, energy=2)
        assert tag.can_kill_this_turn is True   # 15 >= 15 (damage pass picks Strike)
        assert tag.can_block_full_incoming is True  # 10 >= 8 (block pass picks Defend)

    def test_zero_cost_cards_always_feasible(self):
        """0-cost cards don't consume energy → always contribute to feasible totals."""
        hand = [
            _make_card("Neutralize", damage=3, energy_cost=0, rules_text="Apply 1 Weak"),
            _make_card("Defend", block=5, energy_cost=1),
            _make_card("Defend", block=5, energy_cost=1),
            _make_card("Defend", block=5, energy_cost=1),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=14, enemy_hp_lowest=40, energy=2)
        # Feasible: Neutralize(0) + 2 Defends(1+1) = 10 block
        assert tag.can_block_8_plus is True  # feasible 10 >= 8
        assert tag.can_block_full_incoming is False  # feasible 10 < 14


# ── HandCapabilityTag defaults / construction ────────────────

class TestHandCapabilityTagDefaults:
    def test_default_all_false(self):
        tag = HandCapabilityTag()
        assert tag.can_apply_weak is False
        assert tag.can_block_8_plus is False
        assert tag.can_kill_this_turn is False
        assert tag.total_damage == 0
        assert tag.total_block == 0
