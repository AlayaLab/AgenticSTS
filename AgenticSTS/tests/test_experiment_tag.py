from pathlib import Path
from src.runs.history import RunRecord, RunHistoryStore


def test_experiment_tag_round_trip(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    rec = RunRecord(run_id="r1", experiment_tag="ablation-2026-04-21")
    store.append(rec)

    loaded = RunHistoryStore.load(path)
    assert loaded.count == 1
    assert loaded.load_all()[0].experiment_tag == "ablation-2026-04-21"


def test_experiment_tag_default_empty():
    rec = RunRecord(run_id="r2")
    assert rec.experiment_tag == ""
    d = rec.to_dict()
    assert d["experiment_tag"] == ""


def test_query_by_tag(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    store.append(RunRecord(run_id="a", experiment_tag="batch-1"))
    store.append(RunRecord(run_id="b", experiment_tag="batch-2"))
    store.append(RunRecord(run_id="c", experiment_tag=""))

    loaded = RunHistoryStore.load(path)
    hits = loaded.query(experiment_tag="batch-1")
    assert len(hits) == 1
    assert hits[0].run_id == "a"


def test_query_empty_tag_returns_untagged_only(tmp_path: Path):
    path = tmp_path / "history.jsonl"
    store = RunHistoryStore(path)
    store.append(RunRecord(run_id="a", experiment_tag="batch-1"))
    store.append(RunRecord(run_id="b", experiment_tag=""))

    loaded = RunHistoryStore.load(path)
    hits = loaded.query(experiment_tag="")
    assert len(hits) == 1
    assert hits[0].run_id == "b"
