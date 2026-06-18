"""Tests for experiment-tag isolation of ascension_stats.

When --experiment-tag is set, run_agent uses a session-local AscensionStats
rebuilt from runs/history.jsonl filtered by tag — never reading or writing
the global runs/ascension_stats.json. This gives experiments three properties
that are tested below:

1. Isolation from personal play (prior wins under default profile_hash do
   not bleed into experiments).
2. Multi-agent parallel safety (the global cache is never read or written).
3. Resume correctness (a second session with the same tag picks up where
   the first session left off).

All tests target `scripts.run_agent::_load_ascension_stats_for_session`,
the helper called from main() before any MCP connection.
"""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from scripts.run_agent import _load_ascension_stats_for_session
from src.runs.history import RunHistoryStore, RunRecord


def _make_record(
    *,
    profile_hash: str = "abc",
    character: str = "Silent",
    actual_ascension: int = 0,
    victory: bool = False,
    outcome: str = "defeat",
    final_floor: int = 30,
    experiment_tag: str = "",
    run_id: str | None = None,
) -> RunRecord:
    return RunRecord(
        run_id=run_id or f"r{int(time.time()*1000)}",
        started_at=time.time() - 1000,
        ended_at=time.time(),
        profile_hash=profile_hash,
        profile_label=profile_hash,
        model_profile={},
        character=character,
        target_ascension=actual_ascension,
        actual_ascension=actual_ascension,
        outcome=outcome,
        victory=victory,
        final_floor=final_floor,
        final_hp=0,
        final_max_hp=80,
        final_gold=0,
        fitness=0.0,
        score=0,
        duration_seconds=1000.0,
        steps=500,
        llm_calls=100,
        total_actions=500,
        combats_won=5,
        combats_total=10,
        completion_reason="completed",
        end_reason="defeat",
        use_llm=True,
        memory_enabled=False,
        skills_enabled=False,
        experiment_tag=experiment_tag,
    )


def _make_store(records: list[RunRecord]) -> RunHistoryStore:
    """Build an in-memory RunHistoryStore (no disk I/O)."""
    store = RunHistoryStore(Path("/tmp/nonexistent_test_history.jsonl"))
    store._records = list(records)
    return store


# ── No experiment tag → loads global cache ───────────────────────


def test_no_experiment_tag_loads_global_cache(tmp_path, monkeypatch):
    """Personal play (empty tag) loads runs/ascension_stats.json from disk."""
    # Point the global cache at a tmp file with one synthetic record so we
    # can verify the loaded stats include it.
    cache_path = tmp_path / "ascension_stats.json"
    cache_path.write_text(
        '{"records": [{"profile_hash": "personal", "character": "Silent", '
        '"ascension": 5, "wins": 3, "losses": 1, "aborts": 0, '
        '"best_floor": 48, "avg_floor": 45.0, "total_runs": 4}]}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "scripts.run_agent.paths.ascension_stats_file",
        lambda: cache_path,
    )

    store = _make_store([])
    stats = _load_ascension_stats_for_session(store, experiment_tag="")
    rec = stats.get("personal", "Silent", 5)
    assert rec.wins == 3
    assert rec.total_runs == 4


# ── Experiment tag with empty history → fresh empty stats ────────


def test_experiment_tag_with_no_matching_history_returns_empty_stats():
    store = _make_store([])
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-X")
    # next_ascension on empty stats returns 0 (no clears)
    assert stats.next_ascension("any-hash", "Silent") == 0
    assert stats.highest_cleared("any-hash", "Silent") == -1


# ── Experiment tag rebuilds stats from matching records ──────────


def test_experiment_tag_rebuilds_from_matching_records():
    records = [
        _make_record(
            profile_hash="hash-baseline", actual_ascension=0,
            victory=True, outcome="victory", final_floor=48,
            experiment_tag="pilot-A0",
        ),
        _make_record(
            profile_hash="hash-baseline", actual_ascension=0,
            victory=False, outcome="defeat", final_floor=33,
            experiment_tag="pilot-A0",
        ),
    ]
    store = _make_store(records)
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-A0")
    rec = stats.get("hash-baseline", "Silent", 0)
    assert rec.wins == 1
    assert rec.losses == 1
    assert rec.total_runs == 2
    # Auto-progression: highest cleared is A0, next is A1
    assert stats.next_ascension("hash-baseline", "Silent") == 1


# ── Experiment tag isolates from records under a different tag ───


def test_experiment_tag_excludes_other_tags_records():
    records = [
        _make_record(
            profile_hash="hash-x", actual_ascension=3,
            victory=True, outcome="victory",
            experiment_tag="other-experiment",
        ),
        _make_record(
            profile_hash="hash-x", actual_ascension=0,
            victory=False, outcome="defeat",
            experiment_tag="pilot-A0",
        ),
    ]
    store = _make_store(records)
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-A0")
    # The A3 victory under "other-experiment" must NOT bleed in
    assert stats.get("hash-x", "Silent", 3).wins == 0
    assert stats.next_ascension("hash-x", "Silent") == 0  # fresh start at A0


# ── Experiment tag excludes records from personal play ───────────


def test_experiment_tag_excludes_personal_play_records():
    """Personal play records (empty experiment_tag) are isolated from any
    experiment tag's session-local stats."""
    records = [
        _make_record(
            profile_hash="hash-personal", actual_ascension=10,
            victory=True, outcome="victory",
            experiment_tag="",  # personal play
        ),
    ]
    store = _make_store(records)
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-A0")
    # Personal A10 win must not affect the experiment session
    assert stats.next_ascension("hash-personal", "Silent") == 0


# ── Resume correctness ──────────────────────────────────────────


def test_resume_session_picks_up_from_history():
    """Simulating a 'session 2' where session 1 already wrote 1 win at A0.

    The new session should rebuild stats from history and start session 2's
    next run at A1.
    """
    session_1_records = [
        _make_record(
            profile_hash="full", actual_ascension=0,
            victory=True, outcome="victory", final_floor=48,
            experiment_tag="pilot-2026-04-27",
        ),
    ]
    store = _make_store(session_1_records)
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-2026-04-27")
    assert stats.next_ascension("full", "Silent") == 1


# ── Aborts do not advance ascension ──────────────────────────────


def test_aborts_under_experiment_tag_do_not_advance():
    """An agent_abort outcome must not be counted as a win for progression."""
    records = [
        _make_record(
            profile_hash="full", actual_ascension=0,
            victory=False, outcome="agent_abort", final_floor=15,
            experiment_tag="pilot-X",
        ),
    ]
    store = _make_store(records)
    stats = _load_ascension_stats_for_session(store, experiment_tag="pilot-X")
    rec = stats.get("full", "Silent", 0)
    assert rec.wins == 0
    assert rec.aborts == 1
    assert stats.next_ascension("full", "Silent") == 0
