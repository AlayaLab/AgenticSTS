"""Fix combat_type misclassification in memory data.

Bug: _infer_combat_type() hardcoded floor (8, 16, 24) as boss floors.
Actual STS2 boss floors: 17 (Act 1), 33 (Act 2), 43+ (Act 3).

This script corrects:
1. combat_episodes.jsonl: floor 8/16/24 "boss" → "monster", floor 17/33/43+ "elite" → "boss"
2. guides.json: clears contaminated guides so consolidation regenerates them

Usage:
    python -m scripts.fix_combat_type [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime
from pathlib import Path

MEMORY_DIR = Path(__file__).resolve().parent.parent / "data" / "memory" / "v2"
BACKUP_DIR = MEMORY_DIR / "_backups"

# Known boss enemies (from log analysis + strategy guide verification)
KNOWN_BOSSES = {
    # Act 1 bosses (floor 17)
    "kin priest",
    # Act 2 bosses (floor 33)
    "knowledge demon",
    "the insatiable",
    # Act 3 bosses (floor 48+) — Queen is the Act 3 boss
    "queen",
    # Note: Doormaker, Test Subject C10 are also Act 3 bosses (from strategy guide)
    "doormaker",
    "test subject",
}

# Known Act 1 boss floor enemies — floor 17 has varied enemies that can be boss
# These appear at floor 17 as boss encounters (confirmed from run data)
KNOWN_ACT1_BOSS_ENEMIES = {
    "lagavulin matriarch",
    "waterfall giant",
    "kin priest",
    "soul fysh",
    "ceremonial beast",
    "vantom",
}

# Known Act 3 elites — NOT bosses (confirmed by strategy guide section 5.4)
KNOWN_ACT3_ELITES = {
    "mecha knight",
    "owl magistrate",
    "frog knight",
    "knight trio",
    "soul nexus",
}

# Boss floors (approximate — used as hint combined with enemy name)
BOSS_FLOORS = {17, 33, 48, 49, 50}

# Floors that were incorrectly hardcoded as boss
WRONG_BOSS_FLOORS = {8, 16, 24}


def _is_boss_enemy(enemy_key: str, floor: int = 0) -> bool:
    """Check if an enemy_key is a known boss based on name + floor context."""
    ek_lower = enemy_key.lower()
    # Direct boss match (Act 2/3 bosses have unique names)
    if any(boss in ek_lower for boss in KNOWN_BOSSES):
        return True
    # Act 1 floor 17: varied enemies that serve as boss encounters
    if floor == 17 and any(boss in ek_lower for boss in KNOWN_ACT1_BOSS_ENEMIES):
        return True
    return False


def _is_act3_elite(enemy_key: str) -> bool:
    """Check if an enemy is a known Act 3 elite (NOT boss)."""
    ek_lower = enemy_key.lower()
    return any(elite in ek_lower for elite in KNOWN_ACT3_ELITES)


def fix_combat_episodes(dry_run: bool = False) -> dict:
    """Fix combat_type in combat_episodes.jsonl."""
    episodes_path = MEMORY_DIR / "combat_episodes.jsonl"
    if not episodes_path.exists():
        print("  No combat_episodes.jsonl found, skipping.")
        return {"fixed_to_monster": 0, "fixed_to_boss": 0}

    lines = episodes_path.read_text(encoding="utf-8").strip().split("\n")
    fixed_to_monster = 0
    fixed_to_boss = 0
    fixed_to_elite = 0
    new_lines = []

    for line in lines:
        if not line.strip():
            continue
        ep = json.loads(line)
        floor = ep.get("floor", 0)
        ct = ep.get("combat_type", "")
        ek = ep.get("enemy_key", "")

        original_ct = ct

        # Fix 1: Wrong boss floors → monster (unless enemy is actually a boss)
        if ct == "boss" and floor in WRONG_BOSS_FLOORS and not _is_boss_enemy(ek, floor):
            ep["combat_type"] = "monster"
            fixed_to_monster += 1

        # Fix 2: Act 3 elites incorrectly labeled as boss → elite
        if ct == "boss" and _is_act3_elite(ek):
            ep["combat_type"] = "elite"
            fixed_to_elite += 1

        # Fix 3: Real boss floors with elite → boss (if enemy IS a boss)
        if ct == "elite" and _is_boss_enemy(ek, floor):
            ep["combat_type"] = "boss"
            fixed_to_boss += 1

        # Fix 4: Floor 17 boss enemies incorrectly labeled as elite → boss
        if ct == "elite" and floor == 17 and any(b in ek.lower() for b in KNOWN_ACT1_BOSS_ENEMIES):
            ep["combat_type"] = "boss"
            fixed_to_boss += 1

        if ep["combat_type"] != original_ct:
            print(f"  Floor {floor:2d}: {ek:50s} {original_ct:8s} → {ep['combat_type']}")

        new_lines.append(json.dumps(ep, ensure_ascii=False))

    if not dry_run and (fixed_to_monster > 0 or fixed_to_boss > 0 or fixed_to_elite > 0):
        episodes_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    return {"fixed_to_monster": fixed_to_monster, "fixed_to_boss": fixed_to_boss, "fixed_to_elite": fixed_to_elite}


def fix_guides(dry_run: bool = False) -> int:
    """Clear contaminated guide entries in guides.json.

    Rather than trying to surgically fix LLM-generated guide text,
    we clear guides that were built from misclassified episodes.
    The consolidation pipeline will regenerate them on next run.
    """
    guides_path = MEMORY_DIR / "guides.json"
    if not guides_path.exists():
        print("  No guides.json found, skipping.")
        return 0

    guides = json.loads(guides_path.read_text(encoding="utf-8"))
    cleared = 0

    # Combat guides are keyed by enemy_key — clear any that reference
    # non-boss enemies that were incorrectly in boss context
    combat_guides = guides.get("combat_guides", {})
    keys_to_clear = []
    for key, guide in combat_guides.items():
        guide_text = json.dumps(guide).lower()
        # If a guide for a non-boss enemy mentions "boss" context, it's contaminated
        if not _is_boss_enemy(key) and "boss" in guide_text and ("floor 8" in guide_text or "floor 16" in guide_text or "floor 24" in guide_text):
            keys_to_clear.append(key)

    for key in keys_to_clear:
        print(f"  Clearing contaminated combat guide: {key}")
        del combat_guides[key]
        cleared += 1

    if not dry_run and cleared > 0:
        guides_path.write_text(json.dumps(guides, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return cleared


def backup_files():
    """Create timestamped backup of memory files."""
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = BACKUP_DIR / f"pre_combat_type_fix_{ts}"
    backup_path.mkdir(parents=True, exist_ok=True)

    for fname in ("combat_episodes.jsonl", "guides.json", "route_memories.jsonl"):
        src = MEMORY_DIR / fname
        if src.exists():
            shutil.copy2(src, backup_path / fname)
            print(f"  Backed up {fname}")

    return backup_path


def main():
    parser = argparse.ArgumentParser(description="Fix combat_type misclassification in memory data")
    parser.add_argument("--dry-run", action="store_true", help="Show changes without writing")
    args = parser.parse_args()

    print("=" * 60)
    print("COMBAT TYPE REPAIR")
    print("=" * 60)

    if not args.dry_run:
        print("\n[Backup]")
        backup_path = backup_files()
        print(f"  Backup saved to: {backup_path}")

    print("\n[Combat Episodes]")
    ep_stats = fix_combat_episodes(dry_run=args.dry_run)

    print("\n[Guides]")
    guides_cleared = fix_guides(dry_run=args.dry_run)

    print("\n" + "-" * 60)
    print("SUMMARY")
    print("-" * 60)
    print(f"  Episodes fixed (boss → monster): {ep_stats['fixed_to_monster']}")
    print(f"  Episodes fixed (boss → elite):   {ep_stats['fixed_to_elite']}")
    print(f"  Episodes fixed (elite → boss):   {ep_stats['fixed_to_boss']}")
    print(f"  Guides cleared for regeneration:  {guides_cleared}")
    if args.dry_run:
        print("\n  [DRY RUN — no files modified]")
    else:
        print("\n  Done. Memory data corrected.")


if __name__ == "__main__":
    main()
