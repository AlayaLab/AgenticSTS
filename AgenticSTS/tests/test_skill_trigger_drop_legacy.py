from src.skills.models import SkillTrigger


def test_legacy_trigger_dict_with_removed_fields_loads():
    """Skills persisted before removal must still load — removed fields ignored."""
    legacy = {
        "state_types": ["monster"],
        "enemy_names": ["Sewer Clam"],
        "threat_levels": ["high"],
        "intent_classes": ["attack"],
        "deck_stages": ["scaling"],
        "tags": ["alternating"],
        "character": ["silent"],
    }
    t = SkillTrigger.from_dict(legacy)
    assert "monster" in t.state_types
    assert "Sewer Clam" in t.enemy_names
    assert "silent" in t.character
    # Removed fields must not exist as attributes:
    assert not hasattr(t, "threat_levels")
    assert not hasattr(t, "intent_classes")
    assert not hasattr(t, "deck_stages")
    assert not hasattr(t, "tags")
