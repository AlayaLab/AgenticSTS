"""Tests for STS2_RUNS_HISTORY_REPO override in paths.py.

This env var lets ablation experiments isolate L4/L5 stores (memory, skills,
evolution) per-condition while sharing runs/history.jsonl + ascension_stats.json
across conditions for post-hoc aggregation by experiment_tag.
"""
from __future__ import annotations

import pytest

from src.storage import paths


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Ensure each test starts with a clean slate."""
    for k in ("STS2_DATA_REPO", "STS2_DATA_DIR", "STS2_RUNS_HISTORY_REPO"):
        monkeypatch.delenv(k, raising=False)


def test_runs_history_file_falls_back_to_data_root_when_unset(monkeypatch, tmp_path):
    monkeypatch.setenv("STS2_DATA_REPO", str(tmp_path))
    expected = (tmp_path / "runs" / "history.jsonl").resolve()
    assert paths.runs_history_file() == expected


def test_runs_history_file_uses_override_when_set(monkeypatch, tmp_path):
    data_dir = tmp_path / "experiments" / "tag-a" / "cond-1"
    history_dir = tmp_path  # parent shared dir
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    expected = (history_dir / "runs" / "history.jsonl").resolve()
    assert paths.runs_history_file() == expected


def test_ascension_stats_file_uses_override_when_set(monkeypatch, tmp_path):
    data_dir = tmp_path / "experiments" / "tag-a" / "cond-1"
    history_dir = tmp_path
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    expected = (history_dir / "runs" / "ascension_stats.json").resolve()
    assert paths.ascension_stats_file() == expected


def test_other_paths_unaffected_by_override(monkeypatch, tmp_path):
    """STS2_RUNS_HISTORY_REPO must NOT redirect memory/skills/evolution."""
    data_dir = tmp_path / "data"
    history_dir = tmp_path / "shared"
    monkeypatch.setenv("STS2_DATA_REPO", str(data_dir))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_dir))

    assert paths.skills_file() == (data_dir / "skills" / "skills.json").resolve()
    assert paths.memory_dir() == (data_dir / "memory").resolve()
    assert paths.evolution_dir() == (data_dir / "evolution").resolve()
