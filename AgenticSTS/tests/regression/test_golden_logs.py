import json
from pathlib import Path

import pytest

from src.regression.log_replay import LogReplayClient, compute_fingerprint


GOLDEN_DIR = Path("tests/fixtures/golden_logs/v0.5.3")


def _available_golden_logs() -> list[Path]:
    if not GOLDEN_DIR.exists():
        return []
    return [p for p in GOLDEN_DIR.iterdir() if p.suffix == ".jsonl"]


@pytest.mark.parametrize("log_path", _available_golden_logs(),
                         ids=[p.stem for p in _available_golden_logs()])
def test_golden_log_fingerprint_matches(log_path: Path):
    """Each golden log must have a sibling .fingerprint.json with expected values."""
    fp_file = log_path.with_suffix(".fingerprint.json")
    if not fp_file.exists():
        pytest.skip(f"No fingerprint file at {fp_file}; run scripts.freeze_golden_log.")
    expected = json.loads(fp_file.read_text(encoding="utf-8"))
    client = LogReplayClient(log_path)
    actual = compute_fingerprint(list(client.iter_decisions()))
    assert actual["error_count"] == expected["error_count"]
    assert set(actual["decision_types"]) == set(expected["decision_types"])
    assert abs(actual["num_decisions"] - expected["num_decisions"]) <= max(5, expected["num_decisions"] * 0.05)
