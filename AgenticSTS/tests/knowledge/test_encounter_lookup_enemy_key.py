from pathlib import Path

from src.knowledge.encounter_lookup import EncounterLookup


def _lookup() -> EncounterLookup:
    return EncounterLookup(Path("data/knowledge"))


def test_resolve_enemy_key_single_monster():
    lk = _lookup()
    # CEREMONIAL_BEAST_BOSS ships with monsters=[{"name": "Ceremonial Beast"}]
    assert lk.resolve_encounter_enemy_key("CEREMONIAL_BEAST_BOSS") == "Ceremonial Beast"


def test_resolve_enemy_key_multi_monster_sorted():
    lk = _lookup()
    # DOORMAKER_BOSS ships with monsters=[{"name": "Door"}, {"name": "Doormaker"}]
    assert lk.resolve_encounter_enemy_key("DOORMAKER_BOSS") == "multi:Door+Doormaker"


def test_resolve_enemy_key_multi_monster_with_duplicates_sorted():
    lk = _lookup()
    # KAISER_CRAB_BOSS ships with monsters=[{"name": "Crusher"}, {"name": "Rocket"}]
    assert lk.resolve_encounter_enemy_key("KAISER_CRAB_BOSS") == "multi:Crusher+Rocket"


def test_resolve_enemy_key_unknown_returns_none():
    lk = _lookup()
    assert lk.resolve_encounter_enemy_key("NOT_A_REAL_ENCOUNTER") is None


def test_resolve_enemy_key_empty_string_returns_none():
    lk = _lookup()
    assert lk.resolve_encounter_enemy_key("") is None
