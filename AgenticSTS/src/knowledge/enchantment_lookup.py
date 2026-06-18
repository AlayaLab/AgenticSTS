"""Enchantment knowledge lookup — enchantment metadata from upstream enchantments.json."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EnchantmentKnowledge:
    """Enchantment metadata from upstream JSON."""
    id: str
    name: str
    description: str = ""
    card_type: str = ""
    is_stackable: bool = False


class EnchantmentLookup:
    """O(1) enchantment lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._lookup: dict[str, EnchantmentKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        path = data_dir / "upstream" / "enchantments.json"
        if not path.exists():
            logger.warning("Enchantments data file not found: %s", path)
            return

        try:
            with path.open(encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse enchantments JSON: %s", exc)
            return

        for entry in raw:
            name: str = entry.get("name", "")
            if not name:
                continue
            self._lookup[name.lower()] = EnchantmentKnowledge(
                id=entry.get("id", ""),
                name=name,
                description=entry.get("description", "") or "",
                card_type=entry.get("card_type", "") or "",
                is_stackable=bool(entry.get("is_stackable", False)),
            )

        logger.info("Loaded %d enchantments", len(self._lookup))

    def get(self, name: str) -> EnchantmentKnowledge | None:
        """Lookup by enchantment name (case-insensitive)."""
        return self._lookup.get(name.lower())

    @property
    def count(self) -> int:
        return len(self._lookup)
