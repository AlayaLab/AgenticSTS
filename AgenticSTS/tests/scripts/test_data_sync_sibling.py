"""Tests for `data_sync.sibling_available()` env-var resolution.

Regression coverage for a bug where ablation self-evolve runs short-circuited
all sync to ``"disabled"`` because ``STS2_DATA_REPO`` pointed at an isolated
(non-git) subdir like ``experiments/<tag>/<condition>/``. With sync disabled,
``runs/history.jsonl`` writes piled up uncommitted in the working tree until
a later non-experiment session's ``pull()`` quarantined them to an
``orphan/<machine>/<ts>-precrash`` branch, losing them from main.

The fix prefers ``STS2_RUNS_HISTORY_REPO`` (the orchestrator's explicit
handle to the shared git root) when set, falling back to ``data_root()`` for
the common single-machine case.
"""
from __future__ import annotations

import importlib

import pytest

from scripts import data_sync
from src.storage import paths


@pytest.fixture(autouse=True)
def _clear_env(monkeypatch):
    """Each test starts with a clean env so previous runs don't leak."""
    for k in ("STS2_DATA_REPO", "STS2_DATA_DIR", "STS2_RUNS_HISTORY_REPO"):
        monkeypatch.delenv(k, raising=False)
    # paths/data_sync read env at import-call time, so reload to pick up
    # monkeypatched env on each test.
    importlib.reload(paths)
    importlib.reload(data_sync)


def _fake_git_repo(path):
    """Create a directory that ``sibling_available()`` will recognize as a
    git repo (it only checks ``.git`` is a directory, not a real repo)."""
    path.mkdir(parents=True, exist_ok=True)
    (path / ".git").mkdir()
    return path


def test_ablation_experiment_resolves_git_root_via_history_repo(monkeypatch, tmp_path):
    """The bug case: STS2_DATA_REPO points at a non-git subdir, but
    STS2_RUNS_HISTORY_REPO points at the actual git root.

    Pre-fix this returned None (sync disabled, run records lost). Post-fix it
    returns the shared git root so push_run/pull commit normally.
    """
    sibling_root = _fake_git_repo(tmp_path / "AgenticSTS-Data")
    isolated = sibling_root / "experiments" / "gem-b" / "gemini-self-evolve"
    isolated.mkdir(parents=True)
    monkeypatch.setenv("STS2_DATA_REPO", str(isolated))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(sibling_root))

    assert data_sync.sibling_available() == sibling_root.resolve()


def test_personal_play_resolves_data_repo_when_it_is_git_root(monkeypatch, tmp_path):
    """Common single-machine case: STS2_DATA_REPO points at the sibling clone
    root (which is itself a git repo). No STS2_RUNS_HISTORY_REPO override."""
    sibling_root = _fake_git_repo(tmp_path / "AgenticSTS-Data")
    monkeypatch.setenv("STS2_DATA_REPO", str(sibling_root))

    assert data_sync.sibling_available() == sibling_root.resolve()


def test_history_repo_takes_precedence_over_data_repo(monkeypatch, tmp_path):
    """When both env vars are set and both happen to resolve to git repos,
    STS2_RUNS_HISTORY_REPO wins. This matters when an orchestrator
    intentionally points STS2_DATA_REPO at a subdir for isolation but a
    nested ``.git`` happens to exist (e.g., a leftover submodule)."""
    history_root = _fake_git_repo(tmp_path / "shared")
    isolated = _fake_git_repo(tmp_path / "shared" / "experiments" / "iso")
    monkeypatch.setenv("STS2_DATA_REPO", str(isolated))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_root))

    assert data_sync.sibling_available() == history_root.resolve()


def test_returns_none_when_unconfigured(monkeypatch, tmp_path):
    """No env vars set → falls back to project_root/data, which is not a git
    repo on a fresh checkout → degraded mode (None).

    We pin ``data_root`` to a non-git tmp dir directly: on a dev machine that
    already cloned ``AgenticSTS-Data`` at the default sibling location,
    ``paths._DEFAULT_SIBLING`` resolves to a real git repo and the previous
    ``_PROJECT_ROOT``-only patch was insufficient to make ``data_root()``
    return a non-git path.
    """
    fake_data = tmp_path / "code" / "data"
    fake_data.mkdir(parents=True)
    monkeypatch.setattr(paths, "_PROJECT_ROOT", tmp_path / "code")
    monkeypatch.setattr(paths, "data_root", lambda: fake_data)
    monkeypatch.setattr(data_sync.paths, "data_root", lambda: fake_data)

    assert data_sync.sibling_available() is None


def test_does_not_walk_up_to_code_repo(monkeypatch, tmp_path):
    """Regression: never return the *code* repo as sibling.

    A naive 'walk parents looking for .git' implementation would find the
    code repo itself when ``STS2_DATA_REPO=<project>/data`` is unset,
    incorrectly committing run data into the wrong repository.
    """
    code_repo = _fake_git_repo(tmp_path / "code")
    fake_data = code_repo / "data"
    fake_data.mkdir()
    monkeypatch.setattr(paths, "_PROJECT_ROOT", code_repo)
    # Same rationale as ``test_returns_none_when_unconfigured``: pin
    # data_root to the synthetic non-git ``code/data`` so a real sibling
    # clone on disk doesn't accidentally satisfy the lookup.
    monkeypatch.setattr(paths, "data_root", lambda: fake_data)
    monkeypatch.setattr(data_sync.paths, "data_root", lambda: fake_data)

    assert data_sync.sibling_available() is None


def test_history_repo_set_but_not_git_falls_back_to_data_repo(monkeypatch, tmp_path):
    """If STS2_RUNS_HISTORY_REPO is set but does not contain ``.git``, fall
    back to STS2_DATA_REPO. This tolerates misconfigured env without losing
    sync entirely when data_root is a valid git repo."""
    history_root = tmp_path / "not-a-repo"
    history_root.mkdir()
    sibling_root = _fake_git_repo(tmp_path / "AgenticSTS-Data")
    monkeypatch.setenv("STS2_DATA_REPO", str(sibling_root))
    monkeypatch.setenv("STS2_RUNS_HISTORY_REPO", str(history_root))

    assert data_sync.sibling_available() == sibling_root.resolve()


def test_disabled_when_data_repo_is_non_git_and_no_history_override(
    monkeypatch, tmp_path,
):
    """Pre-fix bug case without the orchestrator setting STS2_RUNS_HISTORY_REPO.
    The function correctly returns None — we don't silently fall through to
    a parent dir that might be the wrong repo."""
    isolated = tmp_path / "experiments" / "iso"
    isolated.mkdir(parents=True)
    monkeypatch.setenv("STS2_DATA_REPO", str(isolated))

    assert data_sync.sibling_available() is None
