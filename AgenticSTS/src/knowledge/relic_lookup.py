"""Relic knowledge lookup — metadata from upstream relics.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RelicKnowledge:
    """Relic metadata from upstream JSON."""
    name: str
    id: str = ""
    description: str = ""
    rarity: str = ""
    pool: str = ""
    flavor: str = ""


class RelicLookup:
    """O(1) relic lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._relics: dict[str, RelicKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        relics_path = data_dir / "upstream" / "relics_dll.json"
        if not relics_path.exists():
            relics_path = data_dir / "upstream" / "relics.json"
        if not relics_path.exists():
            logger.warning("Relics data file not found: %s", relics_path)
            return

        try:
            with relics_path.open(encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse relics JSON: %s", exc)
            return

        for entry in raw:
            name: str = entry.get("name", "")
            if not name:
                continue
            self._relics[name.lower()] = RelicKnowledge(
                name=name,
                id=entry.get("id", ""),
                description=entry.get("description", ""),
                rarity=entry.get("rarity", ""),
                pool=entry.get("pool", ""),
                flavor=entry.get("flavor", ""),
            )

        logger.info("Loaded %d relics", len(self._relics))

    def get(self, relic_name: str) -> RelicKnowledge | None:
        """Lookup by relic name (case-insensitive)."""
        return self._relics.get(relic_name.lower())

    @property
    def count(self) -> int:
        return len(self._relics)
