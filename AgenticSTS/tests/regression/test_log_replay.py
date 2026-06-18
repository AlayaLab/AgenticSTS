import json
from pathlib import Path

from src.regression.log_replay import LogReplayClient


def test_log_replay_iterates_states(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join([
        json.dumps({"_meta": {"game_version": "v-test"}}),
        json.dumps({"event": "state_snapshot", "state": {"floor": 1, "hp": 70}}),
        json.dumps({"event": "decision", "source": "v2_engine_fast"}),
        json.dumps({"event": "state_snapshot", "state": {"floor": 1, "hp": 60}}),
    ]) + "\n")

    client = LogReplayClient(log)
    states = list(client.iter_states())
    assert len(states) == 2
    assert states[0]["floor"] == 1
    assert states[0]["hp"] == 70
    assert states[1]["hp"] == 60


def test_log_replay_decisions(tmp_path: Path):
    log = tmp_path / "run.jsonl"
    log.write_text("\n".join([
        json.dumps({"event": "decision", "source": "v2_engine_fast", "state_type": "combat"}),
        json.dumps({"event": "decision", "source": "v2_engine_strategic", "state_type": "shop"}),
    ]) + "\n")
    client = LogReplayClient(log)
    decisions = list(client.iter_decisions())
    assert len(decisions) == 2
    assert decisions[0]["source"] == "v2_engine_fast"
