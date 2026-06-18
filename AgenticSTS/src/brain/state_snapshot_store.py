"""StateSnapshotStore: capture and retrieve real GameState snapshots for tool validation.

Captures raw MCP ``/state`` payloads during gameplay so the EvolutionEngine
can replay them against newly authored tools — verifying that parameter
binding succeeds and the tool produces useful output on real data.

Storage:
  - In-memory ring buffer (20 most recent combat states, cleared per run)
  - Persistent JSONL on disk (up to 100 entries, FIFO eviction)
"""

from __future__ import annotations

import json
import logging
import time
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

_MEMORY_LIMIT = 20
_DISK_LIMIT = 100

# Only capture combat states — tools overwhelmingly target combat
_CAPTURABLE_STATES = frozenset({"monster", "elite", "boss"})


@dataclass(frozen=True)
class StateSnapshot:
    """A single captured game state snapshot."""

    state_type: str
    timestamp: float
    raw_state: dict[str, Any]


class StateSnapshotStore:
    """Ring-buffered state snapshot store for tool validation."""

    def __init__(self, persist_path: str | Path | None = None) -> None:
        self._buffer: deque[StateSnapshot] = deque(maxlen=_MEMORY_LIMIT)
        if persist_path is None:
            from src.storage import paths
            persist_path = paths.state_snapshots_file()
        self._persist_path = Path(persist_path)

    def capture(self, state_type: str, raw_state: dict[str, Any]) -> None:
        """Capture a state snapshot if it's a combat state."""
        if state_type not in _CAPTURABLE_STATES:
            return
        snap = StateSnapshot(
            state_type=state_type,
            timestamp=time.time(),
            raw_state=raw_state,
        )
        self._buffer.append(snap)

    def get_snapshots(
        self,
        state_types: list[str] | None = None,
        n: int = 5,
    ) -> list[StateSnapshot]:
        """Return up to *n* snapshots matching any of *state_types*.

        Checks in-memory buffer first, falls back to disk if needed.
        Most recent snapshots are returned first.
        """
        candidates: list[StateSnapshot] = []

        # In-memory first (most recent)
        for snap in reversed(self._buffer):
            if state_types and snap.state_type not in state_types:
                continue
            candidates.append(snap)
            if len(candidates) >= n:
                return candidates

        # Fall back to disk
        disk_snaps = self._load_from_disk(state_types, n - len(candidates))
        candidates.extend(disk_snaps)
        return candidates[:n]

    def flush_to_disk(self) -> None:
        """Persist in-memory snapshots to JSONL, enforcing FIFO disk limit."""
        if not self._buffer:
            return

        self._persist_path.parent.mkdir(parents=True, exist_ok=True)

        # Load existing disk entries
        existing: list[dict] = []
        if self._persist_path.exists():
            try:
                with open(self._persist_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line:
                            existing.append(json.loads(line))
            except Exception as exc:
                logger.warning("Failed to read snapshot file: %s", exc)

        # Append new entries
        for snap in self._buffer:
            existing.append({
                "state_type": snap.state_type,
                "timestamp": snap.timestamp,
                "raw_state": snap.raw_state,
            })

        # FIFO eviction: keep only the most recent _DISK_LIMIT entries
        if len(existing) > _DISK_LIMIT:
            existing = existing[-_DISK_LIMIT:]

        # Write all at once
        try:
            with open(self._persist_path, "w", encoding="utf-8") as f:
                for entry in existing:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
            logger.debug(
                "Flushed %d snapshots to disk (%d total)",
                len(self._buffer),
                len(existing),
            )
        except Exception as exc:
            logger.warning("Failed to flush snapshots to disk: %s", exc)

    def clear_memory(self) -> None:
        """Clear in-memory buffer (keep disk snapshots). Called at run start."""
        self._buffer.clear()

    def _load_from_disk(
        self,
        state_types: list[str] | None,
        n: int,
    ) -> list[StateSnapshot]:
        """Load matching snapshots from JSONL file, most recent first."""
        if n <= 0 or not self._persist_path.exists():
            return []

        results: list[StateSnapshot] = []
        try:
            with open(self._persist_path, "r", encoding="utf-8") as f:
                lines = f.readlines()

            # Iterate in reverse (most recent last in file)
            for line in reversed(lines):
                line = line.strip()
                if not line:
                    continue
                entry = json.loads(line)
                st = entry.get("state_type", "")
                if state_types and st not in state_types:
                    continue
                results.append(StateSnapshot(
                    state_type=st,
                    timestamp=entry.get("timestamp", 0.0),
                    raw_state=entry.get("raw_state", {}),
                ))
                if len(results) >= n:
                    break
        except Exception as exc:
            logger.warning("Failed to load snapshots from disk: %s", exc)

        return results
