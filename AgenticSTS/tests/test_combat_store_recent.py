import time

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode


def _ep(
    *,
    run_id="r",
    act=1,
    combat_type="monster",
    character="silent",
    enemy_key="Anything",
    ts=None,
):
    return CombatEpisode(
        run_id=run_id,
        act=act,
        combat_type=combat_type,
        character=character,
        enemy_key=enemy_key,
        timestamp=ts if ts is not None else time.time(),
    )


def test_recent_by_act_type_filters_all_three_keys():
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", act=1, combat_type="monster", character="silent"),
        _ep(run_id="r2", act=2, combat_type="monster", character="silent"),  # wrong act
        _ep(run_id="r3", act=1, combat_type="elite", character="silent"),     # wrong type
        _ep(run_id="r4", act=1, combat_type="monster", character="regent"),   # wrong character
        _ep(run_id="r5", act=1, combat_type="monster", character="silent"),
    ])
    result = store.recent_by_act_type(act=1, combat_type="monster", character="silent", limit=10)
    assert len(result) == 2
    assert {ep.run_id for ep in result} == {"r1", "r5"}


def test_recent_by_act_type_respects_limit_and_recency():
    store = CombatMemoryStore()
    base = time.time()
    for i in range(15):
        store.add_batch([_ep(run_id=f"r{i}", act=1, combat_type="monster", character="silent", ts=base + i)])
    result = store.recent_by_act_type(act=1, combat_type="monster", character="silent", limit=10)
    assert len(result) == 10
    # Most recent first — r14 ... r5
    assert result[0].run_id == "r14"
    assert result[-1].run_id == "r5"


def test_recent_by_act_type_excludes_run_id():
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="current"),
        _ep(run_id="r1"),
        _ep(run_id="r2"),
    ])
    result = store.recent_by_act_type(
        act=1, combat_type="monster", character="silent",
        limit=10, exclude_run_id="current",
    )
    assert {ep.run_id for ep in result} == {"r1", "r2"}


def test_query_requires_enemy_match_when_enemy_key_provided():
    """Without an enemy match, character + combat_type alone (0.5 + 0.3) used
    to clear the relevance threshold and surface unrelated past fights as
    "patterns" for the current encounter (Corpse Slug vs Doormaker, etc.).
    """
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", enemy_key="doormaker", character="silent",
            combat_type="monster"),
        _ep(run_id="r2", enemy_key="crusher", character="silent",
            combat_type="monster"),
        _ep(run_id="r3", enemy_key="kin_priest", character="silent",
            combat_type="monster"),
    ])

    result = store.query(
        enemy_key="multi:corpse_slug+corpse_slug",
        character="silent",
        combat_type="monster",
        limit=5,
    )
    assert result == []


def test_query_returns_matching_enemy_only():
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", enemy_key="corpse_slug", character="silent",
            combat_type="monster"),
        _ep(run_id="r2", enemy_key="doormaker", character="silent",
            combat_type="monster"),
    ])
    result = store.query(
        enemy_key="corpse_slug",
        character="silent",
        combat_type="monster",
        limit=5,
    )
    assert {ep.run_id for ep in result} == {"r1"}


def test_query_substring_enemy_match_still_passes():
    """The 0.7-weighted substring fallback still counts as a positive match."""
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", enemy_key="multi:corpse_slug+corpse_slug",
            character="silent", combat_type="monster"),
    ])
    result = store.query(
        enemy_key="corpse_slug",
        character="silent",
        combat_type="monster",
        limit=5,
    )
    assert len(result) == 1


def test_query_without_enemy_key_still_returns_character_matches():
    """Empty enemy_key keeps the legacy character/combat_type filter behavior
    (used for some retrieval paths that don't have a specific enemy yet).
    """
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", enemy_key="doormaker", character="silent",
            combat_type="monster"),
    ])
    result = store.query(
        enemy_key="",
        character="silent",
        combat_type="monster",
        limit=5,
    )
    assert len(result) == 1
