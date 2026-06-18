"""Monster knowledge lookup — HP ranges + move patterns from decompiled source."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.parser import parse_md_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class MonsterKnowledge:
    """Combined monster metadata + behavior."""
    name: str
    min_hp: int | None = None
    max_hp: int | None = None
    moves: str = ""
    passive: str = ""
    # New fields from upstream JSON:
    monster_type: str = ""  # "Normal" / "Elite" / "Boss"
    damage_values: tuple[tuple[str, int, int], ...] = ()  # (move_name, normal_dmg, ascension_dmg)
    block_values: tuple[tuple[str, int], ...] = ()  # (move_name, block)


class MonsterLookup:
    """O(1) monster lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._monsters: dict[str, MonsterKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        meta_path = data_dir / "monsters.md"
        behav_path = data_dir / "monster-behaviors.md"

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

            min_hp = _parse_int(m.get("MinHp", ""))
            max_hp = _parse_int(m.get("MaxHp", ""))

            self._monsters[name_lower] = MonsterKnowledge(
                name=display_name,
                min_hp=min_hp,
                max_hp=max_hp,
                moves=b.get("Moves", ""),
                passive=b.get("Passive", ""),
            )

        # Enrich with upstream JSON
        json_path = data_dir / "upstream" / "monsters.json"
        if json_path.exists():
            import json as json_mod
            try:
                with open(json_path, encoding="utf-8") as f:
                    upstream = json_mod.load(f)
            except (json_mod.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load upstream monsters: %s", exc)
                return
            # Build ID-to-our-key map for fuzzy matching
            # Our keys: "assassinrubyraider" (no separators). Upstream ID: "ASSASSIN_RUBY_RAIDER"
            id_to_key: dict[str, str] = {}
            for our_key in self._monsters:
                id_to_key[our_key.replace("_", "").replace(" ", "")] = our_key
            enriched = 0
            for entry in upstream:
                uname = entry.get("name", "")
                uid = entry.get("id", "")
                # Try display name first, then normalized ID match
                key = uname.lower()
                existing = self._monsters.get(key)
                if existing is None and uid:
                    norm_id = uid.lower().replace("_", "")
                    key = id_to_key.get(norm_id, "")
                    existing = self._monsters.get(key) if key else None
                if existing is None:
                    continue
                dv_raw = entry.get("damage_values") or {}
                dv = tuple(
                    (move, vals.get("normal", 0), vals.get("ascension", 0))
                    for move, vals in dv_raw.items()
                    if isinstance(vals, dict)
                )
                bv_raw = entry.get("block_values") or {}
                bv = tuple(
                    (move, val) for move, val in bv_raw.items()
                    if isinstance(val, int)
                )
                self._monsters[key] = MonsterKnowledge(
                    name=existing.name,
                    min_hp=existing.min_hp,
                    max_hp=existing.max_hp,
                    moves=existing.moves,
                    passive=existing.passive,
                    monster_type=entry.get("type", ""),
                    damage_values=dv,
                    block_values=bv,
                )
                enriched += 1
            logger.info("Enriched %d monsters with upstream damage values", enriched)

    def get(self, monster_name: str) -> MonsterKnowledge | None:
        """Lookup by monster name (case-insensitive)."""
        return self._monsters.get(monster_name.lower())

    def get_combat_summary(self, monster_name: str) -> str | None:
        """Get a compact combat-relevant summary for prompt injection."""
        monster = self.get(monster_name)
        if not monster:
            return None
        parts = [f"{monster.name}:"]
        if monster.min_hp is not None or monster.max_hp is not None:
            lo = monster.min_hp
            hi = monster.max_hp
            if lo is not None and hi is not None and lo != hi:
                parts.append(f"HP({lo}-{hi})")
            else:
                parts.append(f"HP({lo if lo is not None else hi})")
        if monster.monster_type:
            parts.append(f"[{monster.monster_type}]")
        if monster.damage_values:
            dmg_parts = [f"{mv}={n}" for mv, n, _ in monster.damage_values]
            parts.append(f"Damage=[{', '.join(dmg_parts)}]")
        if monster.block_values:
            blk_parts = [f"{mv}={b}" for mv, b in monster.block_values]
            parts.append(f"Block=[{', '.join(blk_parts)}]")
        if monster.moves:
            parts.append(f"Moves=[{monster.moves}]")
        if monster.passive:
            parts.append(f"Passive=[{monster.passive}]")
        if not monster.moves and not monster.passive:
            return None
        return " ".join(parts)

    @property
    def count(self) -> int:
        return len(self._monsters)


def _parse_int(s: str) -> int | None:
    try:
        return int(s)
    except (ValueError, TypeError):
        return None
