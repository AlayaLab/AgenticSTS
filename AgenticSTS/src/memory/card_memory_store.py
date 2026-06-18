"""Card memory store: per-card longitudinal memory keyed by (character, card_name).

Stores seed knowledge + deterministic run evidence per card.
JSON persistence (not JSONL) because entries are updated in place.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from pathlib import Path

from src.memory.models_v2 import CardMemory
from src.patch.version import get_runtime_version

logger = logging.getLogger(__name__)


def _canonical_card_name(card_name: str) -> str:
    """Lowercase + trimmed + ``+``/``++`` upgrade suffix removed.

    Upgraded and non-upgraded variants of the same card share one note and
    one set of stats (decision made 2026-04-25). Strip the suffix at the
    storage boundary so all read/write paths converge on one slot.
    """
    return card_name.lower().strip().rstrip("+").strip()


def _key(character: str, card_name: str) -> str:
    """Canonical lookup key: lowercase character + base card_name."""
    return f"{character.lower().strip()}::{_canonical_card_name(card_name)}"


class CardMemoryStore:
    """Thread-safe store for per-card memories."""

    def __init__(self) -> None:
        self._memories: dict[str, CardMemory] = {}
        self._lock = threading.Lock()

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    def get(self, character: str, card_name: str) -> CardMemory | None:
        """Get a single card memory by (character, card_name)."""
        with self._lock:
            return self._memories.get(_key(character, card_name))

    def put(self, memory: CardMemory) -> None:
        """Insert or replace a card memory.

        ``memory.card_name`` is canonicalized (lowercase, ``+``/``++`` suffix
        stripped) on the way in so the stored ``card_name`` field always
        matches the slot key.
        """
        canonical = _canonical_card_name(memory.card_name)
        if memory.card_name != canonical:
            memory = replace(memory, card_name=canonical)
        with self._lock:
            self._memories[_key(memory.character, memory.card_name)] = memory

    def query_cards(
        self,
        character: str,
        card_names: list[str],
    ) -> list[CardMemory]:
        """Retrieve card memories for a list of offered card names.

        Only returns memories that have useful content (non-empty note).
        """
        with self._lock:
            results: list[CardMemory] = []
            seen_keys: set[str] = set()
            char_lower = character.lower().strip()
            for name in card_names:
                k = f"{char_lower}::{_canonical_card_name(name)}"
                if k in seen_keys:
                    continue
                mem = self._memories.get(k)
                if mem is not None and mem.has_content:
                    results.append(mem)
                    seen_keys.add(k)
            return results

    def get_all_for_character(self, character: str) -> list[CardMemory]:
        """Get all card memories for a character."""
        with self._lock:
            prefix = f"{character.lower().strip()}::"
            return [m for k, m in self._memories.items() if k.startswith(prefix)]

    def get_all(self) -> list[CardMemory]:
        with self._lock:
            return list(self._memories.values())

    def load_seeds(self, seeds: list[CardMemory]) -> int:
        """Load seed memories without overwriting live data.

        If a memory already exists with a note or sample_count > 0,
        only the note is updated (preserving live stats).
        Returns the number of seeds loaded.
        """
        loaded = 0
        with self._lock:
            for seed in seeds:
                k = _key(seed.character, seed.card_name)
                existing = self._memories.get(k)
                if existing is None:
                    self._memories[k] = seed
                    loaded += 1
                elif not existing.note and seed.note:
                    # Update note only, preserve all live stats via replace()
                    # so new fields (e.g. core_engine_observations) are not
                    # silently dropped by an out-of-date field list.
                    self._memories[k] = replace(existing, note=seed.note)
                    loaded += 1
        return loaded

    def save(self, path: Path) -> None:
        with self._lock:
            snapshot = list(self._memories.values())

        rv = get_runtime_version()
        injected = [
            replace(
                m,
                game_version=m.game_version or rv.game_version,
                mod_version=m.mod_version or rv.mod_version,
                data_schema_version=m.data_schema_version or rv.data_schema_version,
            )
            for m in snapshot
        ]
        path.parent.mkdir(parents=True, exist_ok=True)
        data = [m.to_dict() for m in injected]
        path.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        logger.debug("Saved %d card memories to %s", len(data), path)

    @classmethod
    def load(cls, path: Path) -> CardMemoryStore:
        store = cls()
        if not path.exists():
            return store
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            merged = 0
            for d in data:
                mem = CardMemory.from_dict(d)
                canonical = _canonical_card_name(mem.card_name)
                if mem.card_name != canonical:
                    mem = replace(mem, card_name=canonical)
                k = _key(mem.character, mem.card_name)
                existing = store._memories.get(k)
                if existing is None:
                    store._memories[k] = mem
                else:
                    store._memories[k] = existing.merge_with(mem)
                    merged += 1
            if merged:
                logger.info(
                    "Loaded %d card memories from %s (collapsed %d upgrade-variant duplicates)",
                    len(store._memories), path, merged,
                )
            else:
                logger.info("Loaded %d card memories from %s", len(store._memories), path)
        except Exception as exc:
            logger.warning("Failed to load card memory store from %s: %s", path, exc)
        return store
