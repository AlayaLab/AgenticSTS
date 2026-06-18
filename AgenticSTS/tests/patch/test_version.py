import json
import os
from pathlib import Path

import pytest

from src.patch.version import RuntimeVersion, load_version_state, VersionState


def test_load_version_state(tmp_path: Path):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.103.1", "mod_version": "v0.5.4-xc", "verified_date": "2026-04-18"},
        "history": []
    }))
    state = load_version_state(f)
    assert state.current.game_version == "v0.103.1"
    assert state.current.mod_version == "v0.5.4-xc"


def test_runtime_version_env_override(tmp_path: Path, monkeypatch):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "v0.5.3-chartyr", "verified_date": "2026-03-30"},
        "history": []
    }))
    monkeypatch.setenv("STS2_GAME_VERSION", "v-override")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-override")
    rv = RuntimeVersion.from_file(f)
    assert rv.game_version == "v-override"
    assert rv.mod_version == "m-override"


def test_runtime_version_bump(tmp_path: Path):
    f = tmp_path / "vc.json"
    f.write_text(json.dumps({
        "current": {"game_version": "v0.5.3", "mod_version": "v0.5.3-chartyr", "verified_date": "2026-03-30"},
        "history": []
    }))
    state = load_version_state(f)
    state.bump(new_game_version="v0.103.1", new_mod_version="v0.5.4-xc", verified_date="2026-04-18",
               snapshot_path="data.snapshots/v0.5.3-pre-v0.103.1/")
    state.save(f)
    reloaded = load_version_state(f)
    assert reloaded.current.game_version == "v0.103.1"
    assert len(reloaded.history) == 1
    assert reloaded.history[0].game_version == "v0.5.3"
    assert reloaded.history[0].snapshot_path.endswith("pre-v0.103.1/")
