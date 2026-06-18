"""Act knowledge lookup — act metadata from upstream acts.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class ActKnowledge:
    """Act metadata from upstream JSON."""
    id: str
    name: str
    bosses: tuple[str, ...] = ()
    encounters: tuple[str, ...] = ()
    events: tuple[str, ...] = ()


class ActLookup:
    """O(1) act lookup by id or name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._by_id: dict[str, ActKnowledge] = {}
        self._by_name: dict[str, ActKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        path = data_dir / "upstream" / "acts.json"
        if not path.exists():
            logger.warning("Acts data file not found: %s", path)
            return

        try:
            with path.open(encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse acts JSON: %s", exc)
            return

        for entry in raw:
            act_id: str = entry.get("id", "")
            name: str = entry.get("name", "")
            if not act_id:
                continue
            act = ActKnowledge(
                id=act_id,
                name=name,
                bosses=tuple(entry.get("bosses") or []),
                encounters=tuple(entry.get("encounters") or []),
                events=tuple(entry.get("events") or []),
            )
            self._by_id[act_id.lower()] = act
            if name:
                self._by_name[name.lower()] = act

        logger.info("Loaded %d acts", len(self._by_id))

    def get(self, key: str) -> ActKnowledge | None:
        """Lookup by act id or name (case-insensitive)."""
        lower = key.lower()
        return self._by_id.get(lower) or self._by_name.get(lower)

    @property
    def count(self) -> int:
        return len(self._by_id)
