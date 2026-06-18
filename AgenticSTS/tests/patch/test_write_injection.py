"""Test that RuntimeVersion provenance is injected at all persist write paths.

Tests CombatMemoryStore as the canonical example; the same pattern applies
to CardBuildStore, RouteMemoryStore, GuideStore, CardMemoryStore, and
RunHistoryStore.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode


# ── Helpers ────────────────────────────────────────────────────

def _make_minimal_version_file(path: Path) -> None:
    """Write a minimal version_compatibility.json so from_file() doesn't crash."""
    path.write_text(
        json.dumps({
            "current": {
                "game_version": "v-file",
                "mod_version": "m-file",
                "verified_date": "2026-01-01",
            },
            "history": [],
        }),
        encoding="utf-8",
    )


def _minimal_episode() -> CombatEpisode:
    return CombatEpisode(
        run_id="test-run",
        floor=1,
        enemy_key="Toadpole",
        character="the silent",
        combat_type="monster",
    )


# ── Tests ──────────────────────────────────────────────────────

class TestCombatStoreVersionInjection:
    def test_game_and_mod_version_written_to_jsonl(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """Env-var versions must appear in the JSONL output after save()."""
        # Arrange: point _DEFAULT_PATH at a valid temp file so from_file() works
        version_file = tmp_path / "version_compatibility.json"
        _make_minimal_version_file(version_file)

        monkeypatch.setenv("STS2_GAME_VERSION", "v-test")
        monkeypatch.setenv("STS2_MOD_VERSION", "m-test")
        import src.patch.version as _ver_mod
        monkeypatch.setattr(_ver_mod, "_DEFAULT_PATH", version_file)

        store = CombatMemoryStore()
        store.add(_minimal_episode())

        out = tmp_path / "combat.jsonl"
        store.save(out)

        # Act: read back
        lines = [
            line.strip()
            for line in out.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        # Skip any _meta header line (Task 7 may add it later)
        data_lines = [l for l in lines if not json.loads(l).get("_meta")]
        assert data_lines, "No data lines found in JSONL"

        record = json.loads(data_lines[0])

        # Assert
        assert record.get("game_version") == "v-test", (
            f"Expected game_version='v-test', got {record.get('game_version')!r}"
        )
        assert record.get("mod_version") == "m-test", (
            f"Expected mod_version='m-test', got {record.get('mod_version')!r}"
        )

    def test_explicit_version_not_overwritten(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """A record that already has game_version set must keep its own value."""
        version_file = tmp_path / "version_compatibility.json"
        _make_minimal_version_file(version_file)

        monkeypatch.setenv("STS2_GAME_VERSION", "v-runtime")
        monkeypatch.setenv("STS2_MOD_VERSION", "m-runtime")
        import src.patch.version as _ver_mod
        monkeypatch.setattr(_ver_mod, "_DEFAULT_PATH", version_file)

        episode = CombatEpisode(
            run_id="test-run-2",
            floor=2,
            enemy_key="Cultist",
            character="the silent",
            combat_type="monster",
            game_version="v-explicit",
            mod_version="m-explicit",
        )

        store = CombatMemoryStore()
        store.add(episode)

        out = tmp_path / "combat2.jsonl"
        store.save(out)

        lines = [l.strip() for l in out.read_text(encoding="utf-8").splitlines() if l.strip()]
        record = json.loads(lines[0])

        assert record.get("game_version") == "v-explicit"
        assert record.get("mod_version") == "m-explicit"
