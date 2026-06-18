import datetime

from src.patch.manifest import Manifest, load_manifest

def test_load_manifest(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    assert m.game_version == "v0.103.1"
    assert m.previous_version == "v0.100.0"
    assert len(m.removed_cards) == 1
    assert m.removed_cards[0].name == "Grapple"
    assert len(m.reworked_cards) == 2

def test_changed_entities_includes_major_and_removed(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    entities = m.changed_entities()
    assert "grapple" in entities            # removed
    assert "blade of ink" in entities       # major rework
    assert "doormaker" in entities          # major enemy rework
    assert "stoke" not in entities          # minor severity excluded

def test_prompt_review_targets_superset(minimal_manifest_path):
    m = load_manifest(minimal_manifest_path)
    targets = m.prompt_review_targets()
    changed = m.changed_entities()
    assert changed <= targets  # superset
    # minor entities still appear in prompt review
    assert "stoke" in targets

def test_manifest_roundtrip(minimal_manifest_path, tmp_path):
    m = load_manifest(minimal_manifest_path)
    out = tmp_path / "out.yaml"
    m.dump_yaml(out)
    m2 = load_manifest(out)
    assert m2.changed_entities() == m.changed_entities()

def test_related_enemies_propagate_when_parent_is_major(tmp_path):
    # Encounter-mate of a major reworked enemy should be invalidated too —
    # stored episodes/guides reflect the now-stale fight context.
    yaml_text = """
game_version: v1
previous_version: v0
patch_date: 2026-04-17
reworked_enemies:
  - name: Doormaker
    severity: major
    related_enemies:
      - Door
  - name: Skulking Colony
    severity: minor
    related_enemies:
      - Skulker
"""
    p = tmp_path / "m.yaml"
    p.write_text(yaml_text)
    m = load_manifest(p)
    changed = m.changed_entities()
    assert "doormaker" in changed
    assert "door" in changed              # related of major → purged
    assert "skulking colony" not in changed  # parent is minor
    assert "skulker" not in changed          # related of minor → not purged
    # Prompt review targets include related of both major and minor parents
    targets = m.prompt_review_targets()
    assert "door" in targets
    assert "skulker" in targets


def test_related_enemies_flow_to_major_enemy_slug_set(tmp_path):
    # Orchestrator uses its own helper for the enemy_key slug set driving
    # episode purge — related_enemies must propagate through that path too.
    from src.patch.orchestrator import _compute_major_enemies

    yaml_text = """
game_version: v1
previous_version: v0
patch_date: 2026-04-17
reworked_enemies:
  - name: Doormaker
    severity: major
    related_enemies:
      - Door
"""
    p = tmp_path / "m.yaml"
    p.write_text(yaml_text)
    m = load_manifest(p)
    assert _compute_major_enemies(m) == {"doormaker", "door"}


def test_patch_date_coerces_yaml_date_to_str():
    # Simulate YAML's auto-parsed datetime.date (what yaml.safe_load produces for unquoted dates)
    m = Manifest.model_validate({
        "game_version": "v1",
        "previous_version": "v0",
        "patch_date": datetime.date(2026, 4, 17),
    })
    assert m.patch_date == "2026-04-17"
    assert isinstance(m.patch_date, str)
