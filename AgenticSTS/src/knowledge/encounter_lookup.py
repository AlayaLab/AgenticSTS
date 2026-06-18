"""Encounter knowledge lookup — fight compositions from decompiled source."""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EncounterKnowledge:
    """Fight composition metadata."""
    name: str
    id: str = ""
    room_type: str = ""  # "Monster" / "Elite" / "Boss"
    act: str = ""
    monsters: tuple[str, ...] = ()
    is_weak: bool = False
    tags: tuple[str, ...] = ()


class EncounterLookup:
    """Encounter lookup by ID or by monster set."""

    def __init__(self, data_dir: Path) -> None:
        self._by_id: dict[str, EncounterKnowledge] = {}
        self._by_monster_set: dict[frozenset[str], EncounterKnowledge] = {}
        self._by_name_set: dict[frozenset[str], EncounterKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        path = data_dir / "upstream" / "encounters.json"
        try:
            with path.open(encoding="utf-8") as f:
                entries = json.load(f)
        except Exception as exc:
            logger.warning("Failed to load encounters.json: %s", exc)
            return

        for entry in entries:
            enc_id = entry.get("id", "")
            raw_monsters = entry.get("monsters") or []
            monster_ids = tuple(m["id"] for m in raw_monsters if "id" in m)
            monster_names = tuple(m["name"] for m in raw_monsters if "name" in m)
            raw_tags = entry.get("tags") or []

            enc = EncounterKnowledge(
                name=entry.get("name", ""),
                id=enc_id,
                room_type=entry.get("room_type", ""),
                act=entry.get("act") or "",
                monsters=monster_names,
                is_weak=bool(entry.get("is_weak", False)),
                tags=tuple(raw_tags),
            )

            if enc_id:
                self._by_id[enc_id] = enc

            id_key = frozenset(monster_ids)
            if id_key:
                self._by_monster_set.setdefault(id_key, enc)

            name_key = frozenset(n.lower() for n in monster_names)
            if name_key:
                self._by_name_set.setdefault(name_key, enc)

    def get_by_id(self, encounter_id: str) -> EncounterKnowledge | None:
        """Lookup by encounter ID."""
        return self._by_id.get(encounter_id)

    def get_by_enemy_ids(self, enemy_ids: set[str]) -> EncounterKnowledge | None:
        """Primary lookup by frozenset of enemy IDs."""
        return self._by_monster_set.get(frozenset(enemy_ids))

    def get_by_enemy_names(self, names: set[str]) -> EncounterKnowledge | None:
        """Fallback lookup by frozenset of lowercased display names."""
        return self._by_name_set.get(frozenset(n.lower() for n in names))

    @property
    def count(self) -> int:
        return len(self._by_id)

    def resolve_encounter_enemy_key(self, encounter_id: str) -> str | None:
        """Build the enemy_key used by memory.combat_extractor._build_enemy_key
        for the given encounter, so CombatGuide lookups match the stored key.

        Rules (identical to combat_extractor):
        - exactly one monster: normalize_enemy_key(monster_name)
        - multiple monsters:   normalize_enemy_key("multi:" + "+".join(sorted(names)))
        - unknown or empty:    None
        """
        from src.memory.enemy_keys import normalize_enemy_key

        if not encounter_id:
            return None
        enc = self._by_id.get(encounter_id)
        if enc is None or not enc.monsters:
            return None
        names = list(enc.monsters)
        if len(names) == 1:
            return normalize_enemy_key(names[0])
        return normalize_enemy_key("multi:" + "+".join(sorted(names)))
