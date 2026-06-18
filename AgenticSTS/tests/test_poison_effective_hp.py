"""Tests for poison effective HP calculation and prompt annotation."""

from __future__ import annotations

from src.brain.prompts._intent_fmt import (
    _get_power_amount,
    compute_poison_effective_hp,
    format_poison_hint,
)
from src.mcp_client.upstream_models import RawCombatPowerPayload


def _pw(power_id: str, amount: int) -> RawCombatPowerPayload:
    return RawCombatPowerPayload(power_id=power_id, name=power_id.title(), amount=amount)


# --- compute_poison_effective_hp ---


class TestComputePoisonEffectiveHp:
    def test_no_poison(self):
        assert compute_poison_effective_hp(100, 0) is None

    def test_negative_poison(self):
        assert compute_poison_effective_hp(100, -5) is None

    def test_basic_poison(self):
        # Rocket example: HP 34, Poison 28 → 34 - 28 = 6
        assert compute_poison_effective_hp(34, 28) == 6

    def test_poison_kills(self):
        # Poison >= HP → dies
        assert compute_poison_effective_hp(10, 15) == 0
        assert compute_poison_effective_hp(10, 10) == 0

    def test_poison_exact_kill(self):
        assert compute_poison_effective_hp(20, 20) == 0

    def test_with_accelerant_1(self):
        # HP 100, Poison 19, Accelerant 1
        # Tick 1: 19 damage (poison→18), Tick 2: 18 damage (poison→17)
        # Total: 37 damage → 100 - 37 = 63
        assert compute_poison_effective_hp(100, 19, accelerant_stacks=1) == 63

    def test_with_accelerant_2(self):
        # HP 100, Poison 19, Accelerant 2
        # Tick 1: 19, Tick 2: 18, Tick 3: 17 → total 54
        # 100 - 54 = 46
        assert compute_poison_effective_hp(100, 19, accelerant_stacks=2) == 46

    def test_accelerant_kills(self):
        # HP 40, Poison 19, Accelerant 1 → 19 + 18 = 37 damage → 3 HP
        assert compute_poison_effective_hp(40, 19, accelerant_stacks=1) == 3
        # HP 30, Poison 19, Accelerant 1 → 37 damage → dies
        assert compute_poison_effective_hp(30, 19, accelerant_stacks=1) == 0

    def test_accelerant_more_than_poison(self):
        # Poison 2, Accelerant 5 → ticks: 2, 1, 0 (stops) → total 3
        assert compute_poison_effective_hp(100, 2, accelerant_stacks=5) == 97

    def test_large_poison(self):
        # HP 199, Poison 100 → 99
        assert compute_poison_effective_hp(199, 100) == 99

    def test_card_notes_example(self):
        # From silent_card_notes.json: "enemy has 20 Poison → with Accelerant takes 20+19=39"
        # So effective HP from 50: 50 - 39 = 11
        assert compute_poison_effective_hp(50, 20, accelerant_stacks=1) == 11


# --- _get_power_amount ---


class TestGetPowerAmount:
    def test_found(self):
        powers = [_pw("POISON", 15), _pw("STRENGTH", 2)]
        assert _get_power_amount(powers, "POISON") == 15

    def test_not_found(self):
        powers = [_pw("STRENGTH", 2)]
        assert _get_power_amount(powers, "POISON") == 0

    def test_empty(self):
        assert _get_power_amount([], "POISON") == 0

    def test_none_amount(self):
        pw = RawCombatPowerPayload(power_id="POISON", name="Poison", amount=None)
        assert _get_power_amount([pw], "POISON") == 0


# --- format_poison_hint ---


class TestFormatPoisonHint:
    def test_no_poison(self):
        powers = [_pw("STRENGTH", 2)]
        assert format_poison_hint(powers, 100) == ""

    def test_basic_hint(self):
        powers = [_pw("POISON", 28)]
        assert format_poison_hint(powers, 34) == " (→6 after poison)"

    def test_lethal_hint(self):
        powers = [_pw("POISON", 50)]
        assert format_poison_hint(powers, 30) == " (dies to poison)"

    def test_with_accelerant(self):
        enemy_powers = [_pw("POISON", 20)]
        player_powers = [_pw("ACCELERANT", 1)]
        # 20 + 19 = 39 damage → 50 - 39 = 11
        assert format_poison_hint(enemy_powers, 50, player_powers) == " (→11 after poison)"

    def test_accelerant_lethal(self):
        enemy_powers = [_pw("POISON", 20)]
        player_powers = [_pw("ACCELERANT", 1)]
        # 20 + 19 = 39 → 30 - 39 → dies
        assert format_poison_hint(enemy_powers, 30, player_powers) == " (dies to poison)"

    def test_no_player_powers(self):
        enemy_powers = [_pw("POISON", 10)]
        assert format_poison_hint(enemy_powers, 50, None) == " (→40 after poison)"

    def test_empty_powers(self):
        assert format_poison_hint([], 100) == ""
