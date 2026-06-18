"""Tests for AscensionRecord and AscensionStats."""
import time
from pathlib import Path

from src.runs.ascension_stats import AscensionRecord, AscensionStats
from src.runs.history import RunRecord


def _make_record(**overrides) -> RunRecord:
    defaults = dict(
        run_id="test_001",
        started_at=time.time() - 300,
        ended_at=time.time(),
        profile_hash="a1b2c3d4",
        profile_label="gemini-pro / flash-lite",
        model_profile={},
        character="the silent",
        target_ascension=0,
        actual_ascension=0,
        outcome="victory",
        victory=True,
        final_floor=51,
        final_hp=45,
        final_max_hp=72,
        final_gold=320,
        fitness=185.0,
        score=185,
        duration_seconds=300.0,
        steps=450,
        llm_calls=120,
        total_actions=200,
        combats_won=15,
        combats_total=15,
        completion_reason="completed",
        end_reason="victory",
        use_llm=True,
        memory_enabled=True,
        skills_enabled=True,
    )
    defaults.update(overrides)
    return RunRecord(**defaults)


def test_ascension_record_is_frozen():
    rec = AscensionRecord(profile_hash="abc", character="the silent", ascension=0)
    try:
        rec.wins = 5
        assert False, "should raise"
    except AttributeError:
        pass


def test_stats_record_and_query():
    stats = AscensionStats()
    r1 = _make_record(run_id="r1", actual_ascension=0, victory=True, final_floor=51)
    r2 = _make_record(run_id="r2", actual_ascension=0, victory=False, final_floor=30, outcome="defeat")
    stats.record_run(r1)
    stats.record_run(r2)

    rec = stats.get("a1b2c3d4", "the silent", 0)
    assert rec.wins == 1
    assert rec.losses == 1
    assert rec.aborts == 0
    assert rec.total_runs == 2
    assert rec.best_floor == 51


def test_stats_aborts_tracked_separately():
    stats = AscensionStats()
    r = _make_record(run_id="r1", outcome="agent_abort", victory=False, completion_reason="aborted")
    stats.record_run(r)

    rec = stats.get("a1b2c3d4", "the silent", 0)
    assert rec.losses == 0
    assert rec.aborts == 1
    assert rec.total_runs == 1


def test_highest_cleared_and_next():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", actual_ascension=1, victory=True))
    stats.record_run(_make_record(run_id="r3", actual_ascension=2, victory=False, outcome="defeat"))

    assert stats.highest_cleared("a1b2c3d4", "the silent") == 1
    assert stats.next_ascension("a1b2c3d4", "the silent", max_asc=20) == 2


def test_highest_cleared_no_wins():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=False, outcome="defeat"))
    assert stats.highest_cleared("a1b2c3d4", "the silent") == -1
    assert stats.next_ascension("a1b2c3d4", "the silent") == 0


def test_next_ascension_capped():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=20, victory=True))
    assert stats.next_ascension("a1b2c3d4", "the silent", max_asc=20) == 20


def test_profile_isolation():
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", profile_hash="aaa", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", profile_hash="bbb", actual_ascension=0, victory=False, outcome="defeat"))

    assert stats.highest_cleared("aaa", "the silent") == 0
    assert stats.highest_cleared("bbb", "the silent") == -1


def test_save_and_load_roundtrip(tmp_path: Path):
    path = tmp_path / "stats.json"
    stats = AscensionStats()
    stats.record_run(_make_record(run_id="r1", actual_ascension=0, victory=True))
    stats.record_run(_make_record(run_id="r2", actual_ascension=1, victory=False, outcome="defeat"))
    stats.save(path)

    reloaded = AscensionStats.load(path)
    rec = reloaded.get("a1b2c3d4", "the silent", 0)
    assert rec.wins == 1
    assert rec.total_runs == 1


def test_rebuild_from_history():
    records = [
        _make_record(run_id="r1", actual_ascension=0, victory=True),
        _make_record(run_id="r2", actual_ascension=0, victory=False, outcome="defeat"),
        _make_record(run_id="r3", actual_ascension=1, victory=True),
    ]
    stats = AscensionStats.rebuild_from_history(records)
    a0 = stats.get("a1b2c3d4", "the silent", 0)
    assert a0.wins == 1
    assert a0.losses == 1
    a1 = stats.get("a1b2c3d4", "the silent", 1)
    assert a1.wins == 1
