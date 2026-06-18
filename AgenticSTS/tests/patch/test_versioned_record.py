from src.memory.models_v2 import CombatEpisode, CardBuildMemory, RouteMemory


def test_combat_episode_has_provenance_defaults():
    fields = {f.name for f in CombatEpisode.__dataclass_fields__.values()}
    assert "game_version" in fields
    assert "mod_version" in fields
    assert "data_schema_version" in fields


def test_provenance_fields_present_on_all_domain_models():
    for cls in (CombatEpisode, CardBuildMemory, RouteMemory):
        fields = {f.name for f in cls.__dataclass_fields__.values()}
        assert "game_version" in fields, f"{cls.__name__} missing game_version"
        assert "mod_version" in fields, f"{cls.__name__} missing mod_version"
        assert "data_schema_version" in fields, f"{cls.__name__} missing data_schema_version"


def test_skill_has_provenance_fields():
    from src.skills.models import Skill
    fields = {f.name for f in Skill.__dataclass_fields__.values()}
    assert "game_version" in fields
    assert "mod_version" in fields
    assert "data_schema_version" in fields
