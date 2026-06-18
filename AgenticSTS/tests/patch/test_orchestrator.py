import json
from pathlib import Path

from src.patch.orchestrator import ApplyPatchOptions, apply_patch


def test_apply_patch_auto_apply_skips_confirmation(tmp_path: Path, monkeypatch):
    """auto_apply=True should not attempt input(); should write prompt rewrites directly."""
    _build_fixture_data(tmp_path)
    # Create a prompts dir with a file that references "doormaker"
    prompts = tmp_path / "prompts"
    prompts.mkdir()
    (prompts / "combat.py").write_text('TEXT = "Beware Doormaker"')

    (tmp_path / "version_compatibility.json").write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "m", "verified_date": "2026-03-30"},
        "history": []
    }))

    class RewriteBackend:
        def complete(self, *, system, user):
            # Return modified content
            return 'TEXT = "Beware the reworked Doormaker"'

    options = ApplyPatchOptions(
        manifest_path=tmp_path / "patches/v0.103.1.yaml",
        data_root=tmp_path,
        prompts_root=prompts,
        version_file=tmp_path / "version_compatibility.json",
        snapshot_root=tmp_path / "snapshots",
        seeds_root=tmp_path / "seeds",
        dry_run=False,
        backend=RewriteBackend(),
        auto_apply=True,
    )
    # Should not attempt input() — if it did, test would hang
    report = apply_patch(options)
    assert report.rewrite_files_touched == 1
    assert "reworked Doormaker" in (prompts / "combat.py").read_text()


class StubBackend:
    """Backend that returns the original content unchanged (for offline tests)."""
    def complete(self, *, system: str, user: str) -> str:
        marker = "# Current file content\n"
        if marker in user:
            return user.split(marker, 1)[1]
        return ""


def _build_fixture_data(root: Path) -> None:
    (root / "memory/v2").mkdir(parents=True)
    (root / "skills").mkdir(parents=True)
    (root / "evolution").mkdir(parents=True)
    (root / "patches").mkdir(parents=True)

    (root / "memory/v2/card_memories.json").write_text(json.dumps({
        "the silent::blade of ink": {"play_count": 45},
        "the silent::strike": {"play_count": 100},
    }))
    (root / "memory/v2/combat_episodes.jsonl").write_text(json.dumps(
        {"enemy_key": "Doormaker", "cards_played": ["Strike"]}) + "\n")
    (root / "memory/v2/guides.json").write_text(json.dumps({"combat_guides": [{"enemy_key": "Doormaker"}]}))
    (root / "memory/v2/card_builds.jsonl").write_text("")
    (root / "memory/v2/event_memories.jsonl").write_text("")
    (root / "skills/skills.json").write_text(json.dumps({"skills": []}))

    (root / "patches/v0.103.1.yaml").write_text("""
game_version: v0.103.1
previous_version: v0.5.3
patch_date: 2026-04-17
source: test
summary: test
removed_cards: []
reworked_cards:
  - name: Blade of Ink
    character: the silent
    severity: major
    change: test
reworked_enemies:
  - name: Doormaker
    severity: major
reworked_relics: []
rarity_changed_cards: []
new_cards: []
new_relics: []
ascension_changes: []
shop_changes: []
writing_clarifications: []
new_systems: []
""")


def test_apply_patch_dry_run_does_not_modify(tmp_path: Path):
    _build_fixture_data(tmp_path)
    (tmp_path / "version_compatibility.json").write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "m", "verified_date": "2026-03-30"},
        "history": []
    }))
    options = ApplyPatchOptions(
        manifest_path=tmp_path / "patches/v0.103.1.yaml",
        data_root=tmp_path,
        prompts_root=tmp_path / "empty_prompts",
        version_file=tmp_path / "version_compatibility.json",
        snapshot_root=tmp_path / "snapshots",
        seeds_root=tmp_path / "seeds",
        dry_run=True,
        backend=StubBackend(),
    )
    report = apply_patch(options)
    # In dry-run, card_memories.json is unchanged
    data = json.loads((tmp_path / "memory/v2/card_memories.json").read_text())
    assert "the silent::blade of ink" in data
    assert report.total_deleted > 0


def test_apply_patch_full_run_modifies(tmp_path: Path):
    _build_fixture_data(tmp_path)
    (tmp_path / "version_compatibility.json").write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "m", "verified_date": "2026-03-30"},
        "history": []
    }))

    options = ApplyPatchOptions(
        manifest_path=tmp_path / "patches/v0.103.1.yaml",
        data_root=tmp_path,
        prompts_root=tmp_path / "empty_prompts",
        version_file=tmp_path / "version_compatibility.json",
        snapshot_root=tmp_path / "snapshots",
        seeds_root=tmp_path / "seeds",
        dry_run=False,
        backend=StubBackend(),
    )
    report = apply_patch(options)

    # card_memories: Blade of Ink gone
    data = json.loads((tmp_path / "memory/v2/card_memories.json").read_text())
    assert "the silent::blade of ink" not in data
    assert "the silent::strike" in data

    # combat_episodes: Doormaker row gone
    lines = [ln for ln in (tmp_path / "memory/v2/combat_episodes.jsonl").read_text().splitlines() if ln]
    assert len(lines) == 0

    # guides: wiped
    guides = json.loads((tmp_path / "memory/v2/guides.json").read_text())
    assert guides["combat_guides"] == []

    # version bumped
    vc = json.loads((tmp_path / "version_compatibility.json").read_text())
    assert vc["current"]["game_version"] == "v0.103.1"
    assert len(vc["history"]) == 1
    assert vc["history"][0]["game_version"] == "v0.5.3"

    # snapshot created
    snaps = list((tmp_path / "snapshots").iterdir())
    assert len(snaps) == 1
