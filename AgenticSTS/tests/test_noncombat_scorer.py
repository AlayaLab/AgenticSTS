"""Tests for non-combat skill scoring — one score per run at run end."""

from src.skills.noncombat_scorer import compute_noncombat_score


def test_act1_boss_kill():
    score = compute_noncombat_score(
        final_floor=17, bosses_killed=[1], last_boss_entry_hp=50,
        max_hp=70, last_act_heal_total=0,
    )
    # progress = 17 + 10 = 27, hp_eff = 50/70 ~ 0.71, adj ~ +3.6
    assert 29 < score < 32


def test_act1_boss_kill_healed_a_lot():
    score = compute_noncombat_score(
        final_floor=17, bosses_killed=[1], last_boss_entry_hp=50,
        max_hp=70, last_act_heal_total=40,
    )
    # progress = 27, hp_eff = (50-40)/70 ~ 0.14, adj ~ +0.7
    assert 27 < score < 29


def test_died_early_no_boss():
    score = compute_noncombat_score(
        final_floor=8, bosses_killed=[], last_boss_entry_hp=None,
        max_hp=70, last_act_heal_total=20,
    )
    # progress = 8, never reached boss → adj = -5
    assert score == 8 + (-5)  # = 3.0


def test_victory():
    score = compute_noncombat_score(
        final_floor=51, bosses_killed=[1, 2, 3], last_boss_entry_hp=40,
        max_hp=80, last_act_heal_total=10,
    )
    # progress = 51+10+20+30 = 111, hp_eff = (40-10)/80 = 0.375, adj ~ +1.9
    assert 112 < score < 114


def test_healed_more_than_current_hp():
    """HP efficiency can go negative (healed a lot but still low HP = bad)."""
    score = compute_noncombat_score(
        final_floor=17, bosses_killed=[1], last_boss_entry_hp=20,
        max_hp=70, last_act_heal_total=50,
    )
    # progress = 27, hp_eff = (20-50)/70 ~ -0.43, adj ~ -2.1
    assert 24 < score < 26


def test_hp_efficiency_clamped_lower():
    """HP efficiency is clamped to -1.0 at the lower bound."""
    score = compute_noncombat_score(
        final_floor=17, bosses_killed=[1], last_boss_entry_hp=5,
        max_hp=70, last_act_heal_total=200,
    )
    # progress = 17+10 = 27, hp_eff = (5-200)/70 = -2.78, clamped to -1.0, adj = -5
    assert score == 27 + (-5)  # = 22.0


def test_hp_efficiency_clamped_upper():
    """HP efficiency is clamped to 1.0 at the upper bound."""
    score = compute_noncombat_score(
        final_floor=17, bosses_killed=[1], last_boss_entry_hp=100,
        max_hp=70, last_act_heal_total=0,
    )
    # progress = 27, hp_eff = 100/70 = 1.43, clamped to 1.0, adj = +5
    assert score == 27 + 5  # = 32.0


def test_no_boss_reached_gets_worst_hp():
    """Never reaching a boss gives minimum HP adjustment."""
    score_no_boss = compute_noncombat_score(
        final_floor=15, bosses_killed=[], last_boss_entry_hp=None,
        max_hp=70, last_act_heal_total=0,
    )
    score_with_boss = compute_noncombat_score(
        final_floor=15, bosses_killed=[], last_boss_entry_hp=70,
        max_hp=70, last_act_heal_total=0,
    )
    # No boss = -5 adj, full HP boss entry = +5 adj
    assert score_no_boss == 15 - 5  # 10
    assert score_with_boss == 15 + 5  # 20
    assert score_with_boss > score_no_boss
