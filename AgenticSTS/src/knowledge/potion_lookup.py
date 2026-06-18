"""Potion knowledge lookup — metadata + behaviors from decompiled source."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.parser import parse_md_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class PotionKnowledge:
    """Combined potion metadata + behavior."""
    name: str
    id: str = ""
    description: str = ""
    rarity: str = ""
    usage: str = ""
    target: str = ""
    on_use: str = ""
    vars: str = ""
    pool: str = ""


class PotionLookup:
    """O(1) potion lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._potions: dict[str, PotionKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        meta_path = data_dir / "potions.md"
        behav_path = data_dir / "potion-behaviors.md"

        meta_by_name: dict[str, dict[str, str]] = {}
        if meta_path.exists():
            for row in parse_md_table(meta_path):
                meta_by_name[row["Name"].lower()] = row

        behav_by_name: dict[str, dict[str, str]] = {}
        if behav_path.exists():
            for row in parse_md_table(behav_path):
                behav_by_name[row["Name"].lower()] = row

        all_names = set(meta_by_name.keys()) | set(behav_by_name.keys())
        for name_lower in all_names:
            m = meta_by_name.get(name_lower, {})
            b = behav_by_name.get(name_lower, {})
            display_name = m.get("Name") or b.get("Name", name_lower)

            self._potions[name_lower] = PotionKnowledge(
                name=display_name,
                rarity=m.get("Rarity", ""),
                usage=m.get("Usage", ""),
                target=m.get("Target", ""),
                on_use=b.get("OnUse", ""),
                vars=b.get("Vars", ""),
            )

        json_path = data_dir / "upstream" / "potions_dll.json"
        if not json_path.exists():
            json_path = data_dir / "upstream" / "potions.json"
        if not json_path.exists():
            return

        try:
            with json_path.open(encoding="utf-8") as f:
                raw: list[dict] = json.load(f)
        except Exception as exc:
            logger.warning("Failed to parse potions JSON: %s", exc)
            return

        for entry in raw:
            name = entry.get("name", "")
            if not name:
                continue
            key = name.lower()
            existing = self._potions.get(key)
            self._potions[key] = PotionKnowledge(
                name=name,
                id=entry.get("id", ""),
                description=entry.get("description", ""),
                rarity=entry.get("rarity", "") or (existing.rarity if existing else ""),
                usage=entry.get("usage", "") or (existing.usage if existing else ""),
                target=entry.get("target", "") or (existing.target if existing else ""),
                on_use=existing.on_use if existing else "",
                vars=", ".join(
                    f"{k}={v}" for k, v in (entry.get("vars") or {}).items()
                ) or (existing.vars if existing else ""),
                pool=entry.get("pool", ""),
            )

    def get(self, potion_name: str) -> PotionKnowledge | None:
        """Lookup by potion name (case-insensitive)."""
        return self._potions.get(potion_name.lower())

    @property
    def count(self) -> int:
        return len(self._potions)
