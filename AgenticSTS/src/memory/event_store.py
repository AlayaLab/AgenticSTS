"""Thread-safe event memory store with JSONL persistence.

Stores raw event decisions — per-encounter state diff plus the eventual
run outcome — for retrieval during future event encounters.
"""

from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from src.memory.models_v2 import normalize_character
from src.memory.event_models import EventMemory

logger = logging.getLogger(__name__)


class EventMemoryStore:
    """Thread-safe store for event memories with JSONL persistence."""

    def __init__(self) -> None:
        self._memories: list[EventMemory] = []
        self._lock = threading.Lock()

    def add(self, memory: EventMemory) -> None:
        with self._lock:
            self._memories.append(memory)

    def add_batch(self, memories: list[EventMemory]) -> None:
        with self._lock:
            self._memories.extend(memories)

    def get_all(self) -> list[EventMemory]:
        """Return all stored memories (snapshot)."""
        with self._lock:
            return list(self._memories)

    def query(
        self,
        event_id: str = "",
        character: str = "",
        act: int = 0,
        limit: int = 3,
    ) -> list[EventMemory]:
        """Retrieve event memories by event_id, character, and/or act.

        Priority: exact event_id match > character-preferred sort > recency.
        When event_id is given, character acts as a ranking signal (not a
        hard filter) so that legacy records with character="" are still
        retrievable.
        """
        with self._lock:
            candidates = list(self._memories)

        # event_id is the primary key for event-specific retrieval
        if event_id:
            exact = [m for m in candidates if m.event_id.upper() == event_id.upper()]
            if exact:
                candidates = exact

        # When no event_id, character IS a hard filter (browsing by character)
        if not event_id and character:
            norm_char = normalize_character(character)
            candidates = [m for m in candidates if normalize_character(m.character) == norm_char]

        if act > 0 and not event_id:
            act_match = [m for m in candidates if m.act == act]
            if act_match:
                candidates = act_match

        # Sort: same-character first (when event_id given), then by recency
        if event_id and character:
            norm = normalize_character(character)
            candidates.sort(key=lambda m: (
                normalize_character(m.character) != norm,
                -m.timestamp,
            ))
        else:
            candidates.sort(key=lambda m: -m.timestamp)

        return candidates[:limit]

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    def save(self, path: Path) -> None:
        with self._lock:
            snapshot = list(self._memories)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for mem in snapshot:
                f.write(json.dumps(mem.to_dict()) + "\n")
        logger.debug("Saved %d event memories to %s", len(snapshot), path)

    @classmethod
    def load(cls, path: Path) -> EventMemoryStore:
        store = cls()
        if not path.exists():
            return store
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        store._memories.append(EventMemory.from_dict(json.loads(line)))
            logger.info("Loaded %d event memories from %s", store.count, path)
        except Exception as exc:
            logger.warning("Failed to load event store from %s: %s", path, exc)
        return store
