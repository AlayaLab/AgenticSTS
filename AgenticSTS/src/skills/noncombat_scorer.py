"""Non-combat skill scoring — one score per run at run end.

Progress (final floor + boss kill bonuses) is the primary signal (0-111).
HP efficiency (HP at last boss entry minus healing that act) is a ±5 adjustment.
If agent never reached a boss, HP adjustment is minimum (-5).
"""
from __future__ import annotations

# Bonus points for defeating each act's boss (cumulative)
_BOSS_KILL_BONUSES: dict[int, int] = {1: 10, 2: 20, 3: 30}


def compute_noncombat_score(
    final_floor: int,
    bosses_killed: list[int],
    last_boss_entry_hp: int | None,
    max_hp: int,
    last_act_heal_total: int,
) -> float:
    """Compute non-combat skill score at run end.

    Args:
        final_floor: highest floor reached this run
        bosses_killed: act numbers of bosses defeated [1], [1,2], [1,2,3]
        last_boss_entry_hp: HP when entering the last boss fight (None if never reached boss)
        max_hp: player max HP
        last_act_heal_total: total HP healed via rest in the act of the last boss fight

    Returns:
        Score where:
        - Dead floor 8, no boss: ~3
        - Beat Act 1 boss: ~22-32
        - Beat Act 2 boss: ~59-69
        - Beat Act 3 boss (victory): ~106-116
    """
    # Progress: floor + cumulative boss kill bonuses
    boss_bonus = sum(_BOSS_KILL_BONUSES.get(a, 0) for a in bosses_killed)
    progress = final_floor + boss_bonus

    # HP efficiency: penalize heavy healing, reward entering boss with high HP
    if last_boss_entry_hp is None:
        # Never reached a boss — worst HP score
        hp_adjustment = -5.0
    else:
        hp_eff = (last_boss_entry_hp - last_act_heal_total) / max(max_hp, 1)
        hp_eff_clamped = max(-1.0, min(1.0, hp_eff))
        hp_adjustment = hp_eff_clamped * 5

    return progress + hp_adjustment
