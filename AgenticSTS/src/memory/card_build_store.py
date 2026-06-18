"""Card build memory store: domain-specific storage for CardBuildMemories.

Keyed by (character, archetype). Uses relevance × fitness × recency scoring.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import replace
from pathlib import Path

from src.memory.models_v2 import CardBuildMemory
from src.patch.version import get_runtime_version

logger = logging.getLogger(__name__)

_EXACT_MATCH_WEIGHT = 3.0
_SAME_CHARACTER_WEIGHT = 1.0
_RECENCY_HALF_LIFE_HOURS = 72.0


def _recency_score(timestamp: float, now: float) -> float:
    age_hours = (now - timestamp) / 3600.0
    return math.exp(-0.693 * age_hours / _RECENCY_HALF_LIFE_HOURS)


class CardBuildStore:
    """Thread-safe store for card build memories."""

    def __init__(self) -> None:
        self._memories: list[CardBuildMemory] = []
        self._lock = threading.Lock()

    @staticmethod
    def _memory_key(memory: CardBuildMemory) -> str:
        return memory.run_id

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    def add(self, memory: CardBuildMemory) -> None:
        with self._lock:
            key = self._memory_key(memory)
            if any(self._memory_key(existing) == key for existing in self._memories):
                return
            self._memories.append(memory)

    def replace(self, run_id: str, updated: CardBuildMemory) -> None:
        """Replace a memory entry by run_id (for LLM analysis backfill)."""
        with self._lock:
            for i, mem in enumerate(self._memories):
                if mem.run_id == run_id:
                    self._memories[i] = updated
                    return
        logger.warning("replace: run_id %s not found in store", run_id)

    def add_batch(self, memories: list[CardBuildMemory]) -> None:
        with self._lock:
            seen = {self._memory_key(existing) for existing in self._memories}
            for memory in memories:
                key = self._memory_key(memory)
                if key in seen:
                    continue
                seen.add(key)
                self._memories.append(memory)

    def query(
        self,
        character: str = "",
        archetype: str = "",
        limit: int = 3,
    ) -> list[CardBuildMemory]:
        """Retrieve card build memories by relevance scoring."""
        with self._lock:
            candidates = list(self._memories)

        now = time.time()
        scored: list[tuple[float, CardBuildMemory]] = []

        for mem in candidates:
            relevance = 0.0
            if character and mem.character.lower() == character.lower():
                archetype_lower = archetype.lower() if archetype else ""
                if archetype_lower and mem.archetype.lower() == archetype_lower:
                    # Legacy exact archetype match
                    relevance += _EXACT_MATCH_WEIGHT
                elif archetype_lower and mem.build_tags:
                    # New: build_tags overlap scoring
                    matching = sum(1 for t in mem.build_tags if t == archetype_lower)
                    relevance += matching * 2.0 if matching else _SAME_CHARACTER_WEIGHT
                else:
                    relevance += _SAME_CHARACTER_WEIGHT

            if relevance < 0.1:
                continue

            # Fitness weighting: better runs are more relevant
            importance = max(0.5, min(2.0, mem.fitness / 60.0))

            score = relevance * importance * _recency_score(mem.timestamp, now)
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def get_by_character(self, character: str) -> list[CardBuildMemory]:
        """Get all memories for a character (for consolidation)."""
        with self._lock:
            return [
                m for m in self._memories
                if m.character.lower() == character.lower()
            ]

    def get_all(self) -> list[CardBuildMemory]:
        with self._lock:
            return list(self._memories)

    def save(self, path: Path) -> None:
        with self._lock:
            snapshot = list(self._memories)

        rv = get_runtime_version()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for mem in snapshot:
                mem = replace(
                    mem,
                    game_version=mem.game_version or rv.game_version,
                    mod_version=mem.mod_version or rv.mod_version,
                    data_schema_version=mem.data_schema_version or rv.data_schema_version,
                )
                f.write(json.dumps(mem.to_dict()) + "\n")

        logger.debug("Saved %d card build memories to %s", len(snapshot), path)

    @classmethod
    def load(cls, path: Path) -> CardBuildStore:
        store = cls()
        if not path.exists():
            return store

        try:
            seen: set[str] = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        memory = CardBuildMemory.from_dict(json.loads(line))
                        key = cls._memory_key(memory)
                        if key in seen:
                            continue
                        seen.add(key)
                        store._memories.append(memory)
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning("Skipping malformed card build memory: %s", exc)

            logger.info("Loaded %d card build memories from %s", len(store._memories), path)
        except Exception as exc:
            logger.warning("Failed to load card build store from %s: %s", path, exc)

        return store
