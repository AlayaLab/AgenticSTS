"""Tests for _select_combat_keys_for_refresh helper in guide_consolidator.

Covers the combat-guide refresh selection policy (2026-04-23 spec):
- All boss + elite fights from the current run always refresh.
- Per (act, character), one small-monster fight with max HP loss refreshes
  (tie → first-encountered).
- Episodes from other runs or marked aborted are ignored.
"""

from dataclasses import replace

from src.memory.guide_consolidator import _select_combat_keys_for_refresh
from src.memory.models_v2 import CombatEpisode


def _make_ep(
    *,
    run_id: str = "run-a",
    enemy_key: str = "jaw_worm",
    character: str = "the ironclad",
    act: int = 1,
    combat_type: str = "monster",
    hp_before: int = 70,
    hp_after: int = 70,
) -> CombatEpisode:
    return CombatEpisode(
        run_id=run_id,
        enemy_key=enemy_key,
        character=character,
        act=act,
        combat_type=combat_type,
        hp_before=hp_before,
        hp_after=hp_after,
    )


def test_selects_all_bosses_and_elites_from_this_run():
    episodes = [
        _make_ep(enemy_key="boss_a", act=3, combat_type="boss",
                 hp_before=80, hp_after=20),
        _make_ep(enemy_key="elite_a", act=1, combat_type="elite",
                 hp_before=70, hp_after=50),
        _make_ep(enemy_key="elite_b", act=2, combat_type="elite",
                 hp_before=65, hp_after=40),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("boss a", "the ironclad"),
        ("elite a", "the ironclad"),
        ("elite b", "the ironclad"),
    }


def test_selects_per_act_max_hp_loss_monster_only():
    episodes = [
        _make_ep(enemy_key="cultist", act=1, hp_before=70, hp_after=65),
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50),
        _make_ep(enemy_key="louses", act=1, hp_before=70, hp_after=60),
        _make_ep(enemy_key="slaver", act=2, hp_before=60, hp_after=50),
        _make_ep(enemy_key="byrds", act=2, hp_before=55, hp_after=30),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("jaw worm", "the ironclad"),
        ("byrds", "the ironclad"),
    }


def test_combines_boss_elite_and_per_act_worst_monster():
    episodes = [
        _make_ep(enemy_key="boss_a", act=3, combat_type="boss",
                 hp_before=70, hp_after=10),
        _make_ep(enemy_key="elite_a", act=2, combat_type="elite",
                 hp_before=70, hp_after=40),
        _make_ep(enemy_key="cultist", act=1, hp_before=70, hp_after=65),
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("boss a", "the ironclad"),
        ("elite a", "the ironclad"),
        ("jaw worm", "the ironclad"),
    }


def test_ignores_episodes_from_other_runs():
    episodes = [
        _make_ep(run_id="run-a", enemy_key="jaw_worm", act=1,
                 hp_before=70, hp_after=50),
        _make_ep(run_id="run-b", enemy_key="byrds", act=1,
                 hp_before=70, hp_after=30),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {("jaw worm", "the ironclad")}


def test_ignores_episodes_from_other_characters_grouping_is_perrun():
    episodes = [
        _make_ep(run_id="run-a", enemy_key="jaw_worm",
                 character="the silent", act=1,
                 hp_before=70, hp_after=50),
        _make_ep(run_id="run-a", enemy_key="louses",
                 character="the ironclad", act=1,
                 hp_before=70, hp_after=60),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("jaw worm", "the silent"),
        ("louses", "the ironclad"),
    }


def test_empty_run_produces_no_keys():
    keys = _select_combat_keys_for_refresh([], "run-a")
    assert keys == set()


def test_tie_picks_first_encountered():
    episodes = [
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50),
        _make_ep(enemy_key="louses", act=1, hp_before=70, hp_after=50),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {("jaw worm", "the ironclad")}


def test_skips_aborted_episodes():
    normal = _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50)
    aborted = _make_ep(enemy_key="byrds", act=1, hp_before=70, hp_after=20)
    aborted = replace(aborted, terminal_reason="abort")
    keys = _select_combat_keys_for_refresh([normal, aborted], "run-a")
    assert keys == {("jaw worm", "the ironclad")}
