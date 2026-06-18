"""Replay logged JSONL runs to extract states and decisions."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path
from typing import Iterator


class LogReplayClient:
    """Reads a JSONL log and yields state snapshots / decisions in order."""

    def __init__(self, log_path: Path):
        self.log_path = log_path

    def _iter_rows(self) -> Iterator[dict]:
        for ln in self.log_path.read_text(encoding="utf-8").splitlines():
            if not ln.strip():
                continue
            try:
                row = json.loads(ln)
            except json.JSONDecodeError:
                continue
            if "_meta" in row:
                continue
            yield row

    def iter_states(self) -> Iterator[dict]:
        for row in self._iter_rows():
            if row.get("event") == "state_snapshot" and "state" in row:
                yield row["state"]

    def iter_decisions(self) -> Iterator[dict]:
        for row in self._iter_rows():
            if row.get("event") == "decision":
                yield row


def compute_fingerprint(decisions: list[dict]) -> dict:
    """Compress a decision stream into a stable summary.

    Fields:
    - num_decisions: total count
    - decision_types: Counter by state_type
    - source_distribution: Counter by source (engine tier)
    - error_count: decisions with `error` key or source="error"
    """
    types = Counter()
    sources = Counter()
    errors = 0
    for d in decisions:
        types[d.get("state_type", "unknown")] += 1
        sources[d.get("source", "unknown")] += 1
        if d.get("error") or d.get("source") == "error":
            errors += 1
    return {
        "num_decisions": len(decisions),
        "decision_types": dict(types),
        "source_distribution": dict(sources),
        "error_count": errors,
    }
