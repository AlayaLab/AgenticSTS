"""Tests for RunRecord and RunHistoryStore."""
import time
from pathlib import Path

from src.runs.history import RunRecord, RunHistoryStore


def _make_record(**overrides) -> RunRecord:
    defaults = dict(
        run_id="test_001",
        started_at=time.time() - 300,
        ended_at=time.time(),
        profile_hash="a1b2c3d4",
        profile_label="gemini-pro / flash-lite",
        model_profile={"strategic_model": "gemini-pro", "fast_model": "flash-lite"},
        character="the silent",
        target_ascension=3,
        actual_ascension=3,
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


def test_run_record_is_frozen():
    rec = _make_record()
    try:
        rec.victory = False
        assert False, "should raise"
    except AttributeError:
        pass


def test_run_record_roundtrip():
    rec = _make_record()
    d = rec.to_dict()
    restored = RunRecord.from_dict(d)
    assert restored.run_id == rec.run_id
    assert restored.victory == rec.victory
    assert restored.profile_hash == rec.profile_hash
    assert restored.actual_ascension == rec.actual_ascension
    assert restored.model_profile == rec.model_profile


def test_history_store_append_and_load(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    r1 = _make_record(run_id="run_001", victory=True)
    r2 = _make_record(run_id="run_002", victory=False, outcome="defeat")
    store.append(r1)
    store.append(r2)
    assert store.count == 2

    reloaded = RunHistoryStore.load(path)
    assert reloaded.count == 2
    all_records = reloaded.load_all()
    assert all_records[0].run_id == "run_001"
    assert all_records[1].run_id == "run_002"


def test_history_store_query_filters(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    store.append(_make_record(run_id="r1", character="the silent", profile_hash="aaa"))
    store.append(_make_record(run_id="r2", character="the ironclad", profile_hash="aaa"))
    store.append(_make_record(run_id="r3", character="the silent", profile_hash="bbb"))

    silent_only = store.query(character="the silent")
    assert len(silent_only) == 2

    aaa_only = store.query(profile_hash="aaa")
    assert len(aaa_only) == 2

    combined = store.query(character="the silent", profile_hash="aaa")
    assert len(combined) == 1
    assert combined[0].run_id == "r1"


def test_history_store_empty_path(tmp_path: Path):
    path = tmp_path / "nonexistent.jsonl"
    store = RunHistoryStore.load(path)
    assert store.count == 0
