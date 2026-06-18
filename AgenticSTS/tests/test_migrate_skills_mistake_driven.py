import json
from pathlib import Path
from scripts.migrate_skills_mistake_driven import migrate


def _skill(source, category, name="s"):
    return {
        "skill_id": f"id_{name}", "name": name, "source": source, "category": category,
        "trigger": {
            "state_types": ["monster"], "enemy_names": [], "character": [],
            "min_act": 0, "max_act": 99, "min_deck_size": 0, "max_deck_size": 999,
            "requires_cards": [], "requires_hand_capabilities": [],
            "threat_levels": ["high"], "intent_classes": ["attack"],
            "deck_stages": ["scaling"], "tags": ["x"],
            "any_of_relics": [], "requires_enemy_powers": [],
            "hp_below": 1.0, "hp_above": 0.0,
        },
        "content": f"content {name}", "tier": "specific",
        "priority": 50, "confidence": 0.7, "usage_count": 0,
        "success_count": 0, "failure_count": 0, "verified": True,
        "status": "active", "active": True, "version": 1,
    }


def test_migration_keeps_seeds(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([
        _skill("seed", "combat", "seed_combat"),
        _skill("discovered", "combat", "disc_combat"),
        _skill("discovered", "map", "disc_map"),
    ]))
    migrate(src)
    kept = json.loads(src.read_text())
    names = {s["name"] for s in kept}
    assert "seed_combat" in names
    assert "disc_map" in names
    assert "disc_combat" not in names  # dropped


def test_migration_keeps_noncombat_discovery_categories(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([
        _skill("discovered", "map", "disc_map"),
        _skill("discovered", "event", "disc_event"),
        _skill("discovered", "rest", "disc_rest"),
        _skill("discovered", "deck_building", "disc_deckbuild"),
        _skill("discovered", "shop", "disc_shop"),
        _skill("discovered", "boss", "disc_boss"),  # combat-adjacent — dropped
    ]))
    migrate(src)
    kept = json.loads(src.read_text())
    names = {s["name"] for s in kept}
    assert names == {"disc_map", "disc_event", "disc_rest", "disc_deckbuild", "disc_shop"}


def test_migration_writes_backup(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([_skill("seed", "combat")]))
    migrate(src)
    bak = src.with_suffix(".json.pre-mistake-driven.bak")
    assert bak.exists()


def test_migration_strips_legacy_trigger_fields(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([_skill("seed", "combat")]))
    migrate(src)
    kept = json.loads(src.read_text())
    assert kept
    trig = kept[0]["trigger"]
    assert "threat_levels" not in trig
    assert "intent_classes" not in trig
    assert "deck_stages" not in trig
    assert "tags" not in trig


def test_migration_dict_wrapper_format(tmp_path):
    """Support skills.json with {"skills": [...]} envelope format."""
    src = tmp_path / "skills.json"
    src.write_text(json.dumps({"skills": [
        _skill("seed", "combat", "keep_me"),
        _skill("discovered", "combat", "drop_me"),
    ]}))
    migrate(src)
    loaded = json.loads(src.read_text())
    # Envelope format preserved
    assert "skills" in loaded
    names = {s["name"] for s in loaded["skills"]}
    assert names == {"keep_me"}
