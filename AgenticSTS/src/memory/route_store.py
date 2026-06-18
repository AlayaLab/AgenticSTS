"""Route memory store: domain-specific storage for RouteMemories.

Keyed by (act, character). Uses relevance × importance × recency scoring.
"""

from __future__ import annotations

import json
import logging
import math
import threading
import time
from dataclasses import replace
from pathlib import Path

from src.memory.models_v2 import RouteMemory
from src.patch.version import get_runtime_version

logger = logging.getLogger(__name__)

_EXACT_MATCH_WEIGHT = 3.0
_SAME_ACT_WEIGHT = 1.0
_VICTORY_BONUS = 1.5
_RECENCY_HALF_LIFE_HOURS = 72.0


def _recency_score(timestamp: float, now: float) -> float:
    age_hours = (now - timestamp) / 3600.0
    return math.exp(-0.693 * age_hours / _RECENCY_HALF_LIFE_HOURS)


class RouteMemoryStore:
    """Thread-safe store for route memories with act-based retrieval."""

    def __init__(self) -> None:
        self._memories: list[RouteMemory] = []
        self._lock = threading.Lock()

    @staticmethod
    def _memory_key(memory: RouteMemory) -> tuple[str, int]:
        return (memory.run_id, memory.act)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    def add(self, memory: RouteMemory) -> None:
        with self._lock:
            key = self._memory_key(memory)
            if any(self._memory_key(existing) == key for existing in self._memories):
                return
            self._memories.append(memory)

    def add_batch(self, memories: list[RouteMemory]) -> None:
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
        act: int = 1,
        character: str = "",
        limit: int = 3,
    ) -> list[RouteMemory]:
        """Retrieve route memories by relevance scoring."""
        with self._lock:
            candidates = list(self._memories)

        now = time.time()
        scored: list[tuple[float, RouteMemory]] = []

        for mem in candidates:
            if mem.boss_result == "aborted" or any(node.is_aborted for node in mem.nodes):
                continue
            relevance = 0.0
            if mem.act == act:
                if character and mem.character.lower() == character.lower():
                    relevance += _EXACT_MATCH_WEIGHT
                else:
                    relevance += _SAME_ACT_WEIGHT

            if relevance < 0.1:
                continue

            importance = 1.0
            if mem.victory_run:
                importance *= _VICTORY_BONUS
            # Fitness weighting
            importance *= max(0.5, min(2.0, mem.fitness / 60.0))

            score = relevance * importance * _recency_score(mem.timestamp, now)
            scored.append((score, mem))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [m for _, m in scored[:limit]]

    def get_by_act(self, act: int) -> list[RouteMemory]:
        """Get all memories for a specific act (for consolidation)."""
        with self._lock:
            return [
                m for m in self._memories
                if m.act == act
                and m.boss_result != "aborted"
                and not any(node.is_aborted for node in m.nodes)
            ]

    def get_all(self) -> list[RouteMemory]:
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

        logger.debug("Saved %d route memories to %s", len(snapshot), path)

    @classmethod
    def load(cls, path: Path) -> RouteMemoryStore:
        store = cls()
        if not path.exists():
            return store

        try:
            seen: set[tuple[str, int]] = set()
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        memory = RouteMemory.from_dict(json.loads(line))
                        key = cls._memory_key(memory)
                        if key in seen:
                            continue
                        seen.add(key)
                        store._memories.append(memory)
                    except (json.JSONDecodeError, KeyError, TypeError) as exc:
                        logger.warning("Skipping malformed route memory: %s", exc)

            logger.info("Loaded %d route memories from %s", len(store._memories), path)
        except Exception as exc:
            logger.warning("Failed to load route store from %s: %s", path, exc)

        return store
