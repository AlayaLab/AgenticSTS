"""Thread-safe combat episode store with relevance-scored retrieval.

Stores all combat episodes without capacity limits. Warns when store
grows large and may benefit from deduplication.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

from src.memory.enemy_keys import enemy_key_lookup
from src.memory.models_v2 import CombatEpisode
from src.patch.version import get_runtime_version

logger = logging.getLogger(__name__)

# Retrieval scoring weights
_ENEMY_MATCH_WEIGHT = 1.0
_CHARACTER_MATCH_WEIGHT = 0.5
_COMBAT_TYPE_MATCH_WEIGHT = 0.3

# Thresholds for warnings
_WARN_EPISODE_COUNT = 1000
_WARN_DUPLICATE_RATIO = 0.3


def _importance_score(ep: CombatEpisode) -> float:
    if ep.is_aborted:
        return 0.0
    base = {"boss": 1.0, "elite": 0.8}.get(ep.combat_type, 0.3)
    if ep.won:
        base *= 1.5
    return base


def _recency_score(ts: float, now: float, half_life: float = 72 * 3600) -> float:
    age = max(0, now - ts)
    return 0.5 ** (age / half_life)


class CombatMemoryStore:
    """Thread-safe store for combat episodes with relevance-scored retrieval."""

    def __init__(self) -> None:
        self._episodes: list[CombatEpisode] = []
        self._lock = threading.Lock()

    @staticmethod
    def _episode_key(episode: CombatEpisode) -> tuple[str, int]:
        return (episode.run_id, episode.floor)

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._episodes)

    def add(self, episode: CombatEpisode) -> None:
        with self._lock:
            key = self._episode_key(episode)
            if any(self._episode_key(existing) == key for existing in self._episodes):
                return
            self._episodes.append(episode)
            self._check_health()

    def add_batch(self, episodes: list[CombatEpisode]) -> None:
        with self._lock:
            seen = {self._episode_key(existing) for existing in self._episodes}
            for episode in episodes:
                key = self._episode_key(episode)
                if key in seen:
                    continue
                seen.add(key)
                self._episodes.append(episode)
            self._check_health()

    def query(
        self,
        enemy_key: str = "",
        character: str = "",
        combat_type: str = "",
        limit: int = 3,
    ) -> list[CombatEpisode]:
        """Retrieve combat episodes by relevance scoring.

        Score = relevance(key_match) x importance(outcome) x recency(decay)
        """
        with self._lock:
            candidates = list(self._episodes)

        now = time.time()
        scored: list[tuple[float, CombatEpisode]] = []
        query_enemy = enemy_key_lookup(enemy_key) if enemy_key else ""

        for ep in candidates:
            if ep.is_aborted:
                continue
            relevance = 0.0
            enemy_match = 0.0
            if query_enemy:
                ep_lookup = enemy_key_lookup(ep.enemy_key)
                if ep_lookup == query_enemy:
                    enemy_match = _ENEMY_MATCH_WEIGHT
                elif query_enemy in ep_lookup or ep_lookup in query_enemy:
                    enemy_match = _ENEMY_MATCH_WEIGHT * 0.7
                relevance += enemy_match
            if character and ep.character.lower() == character.lower():
                relevance += _CHARACTER_MATCH_WEIGHT
            if combat_type and ep.combat_type == combat_type:
                relevance += _COMBAT_TYPE_MATCH_WEIGHT

            # When the caller provided an enemy key, require an actual enemy
            # match — otherwise character + combat_type alone (0.5 + 0.3 = 0.8)
            # would clear the relevance threshold and return unrelated past
            # fights as "patterns" for the current encounter.
            if query_enemy and enemy_match <= 0:
                continue
            if relevance < 0.1:
                continue

            score = relevance * _importance_score(ep) * _recency_score(ep.timestamp, now)
            scored.append((score, ep))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [ep for _, ep in scored[:limit]]

    def recent_by_act_type(
        self,
        *,
        act: int,
        combat_type: str,
        character: str,
        limit: int = 10,
        exclude_run_id: str | None = None,
    ) -> list[CombatEpisode]:
        """Most-recent episodes at same act × combat_type × character.

        Used by mistake-driven discovery for Baseline B (§2.1 of spec
        2026-04-19-mistake-driven-skill-discovery-design.md).
        Sorted by timestamp desc. Caller computes aggregates (mean/median).
        """
        with self._lock:
            pool = [
                ep for ep in self._episodes
                if ep.act == act
                and ep.combat_type == combat_type
                and ep.character.lower() == character.lower()
                and (exclude_run_id is None or ep.run_id != exclude_run_id)
                and not ep.is_aborted
            ]
        pool.sort(key=lambda e: e.timestamp, reverse=True)
        return pool[:limit]

    def get_by_enemy(self, enemy_key: str) -> list[CombatEpisode]:
        """Get all episodes for a specific enemy (for consolidation)."""
        query_enemy = enemy_key_lookup(enemy_key)
        with self._lock:
            return [
                ep for ep in self._episodes
                if enemy_key_lookup(ep.enemy_key) == query_enemy and not ep.is_aborted
            ]

    def get_all(self) -> list[CombatEpisode]:
        with self._lock:
            return list(self._episodes)

    def enemy_keys(self) -> set[str]:
        """Return all unique enemy keys in the store."""
        with self._lock:
            return {ep.enemy_key for ep in self._episodes}

    def _check_health(self) -> None:
        """Warn if store is large or has many duplicates."""
        n = len(self._episodes)
        if n > _WARN_EPISODE_COUNT and n % 200 == 0:
            # Check duplicate ratio (same run_id + floor)
            keys = [(ep.run_id, ep.floor) for ep in self._episodes]
            unique = len(set(keys))
            dup_ratio = 1.0 - unique / n if n > 0 else 0.0
            if dup_ratio > _WARN_DUPLICATE_RATIO:
                logger.warning(
                    "CombatStore health: %d episodes, %.0f%% duplicates. "
                    "Consider running deduplication.",
                    n, dup_ratio * 100,
                )
            else:
                logger.info("CombatStore: %d episodes (%d unique encounters)", n, unique)

    def deduplicate(self) -> int:
        """Remove duplicate episodes (same run_id + floor). Returns count removed."""
        with self._lock:
            seen: set[tuple[str, int]] = set()
            unique: list[CombatEpisode] = []
            for ep in self._episodes:
                key = (ep.run_id, ep.floor)
                if key not in seen:
                    seen.add(key)
                    unique.append(ep)
            removed = len(self._episodes) - len(unique)
            self._episodes = unique
            if removed > 0:
                logger.info(
                    "Deduplicated: removed %d duplicates, %d remaining",
                    removed,
                    len(unique),
                )
            return removed

    def save(self, path: Path) -> None:
        with self._lock:
            snapshot = list(self._episodes)

        rv = get_runtime_version()
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for ep in snapshot:
                ep = replace(
                    ep,
                    game_version=ep.game_version or rv.game_version,
                    mod_version=ep.mod_version or rv.mod_version,
                    data_schema_version=ep.data_schema_version or rv.data_schema_version,
                )
                f.write(json.dumps(ep.to_dict()) + "\n")

        logger.debug("Saved %d combat episodes to %s", len(snapshot), path)

    @classmethod
    def load(cls, path: Path) -> CombatMemoryStore:
        store = cls()
        if not path.exists():
            return store

        count = 0
        seen: set[tuple[str, int]] = set()
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    d = json.loads(line)
                    ep = CombatEpisode.from_dict(d)
                    key = cls._episode_key(ep)
                    if key in seen:
                        continue
                    seen.add(key)
                    store._episodes.append(ep)
                    count += 1
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.debug("Skipped malformed episode line: %s", exc)

        logger.info("Loaded %d combat episodes from %s", count, path)
        return store
