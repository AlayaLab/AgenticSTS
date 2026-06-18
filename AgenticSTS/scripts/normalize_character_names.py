"""Normalize character names across all memory stores and guides.

Fixes the "The Silent" vs "the silent" vs "铁甲战士" inconsistency
by applying normalize_character() to all stored records.

Run: python -m scripts.normalize_character_names [--dry-run]
"""

from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

# Add project root to path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src.memory.models_v2 import normalize_character  # noqa: E402

MEMORY_V2 = ROOT / "data" / "memory" / "v2"
GUIDES_PATH = MEMORY_V2 / "guides.json"


def fix_jsonl(path: Path, dry_run: bool) -> dict[str, int]:
    """Normalize character field in a JSONL file. Returns change counts."""
    if not path.exists():
        print(f"  SKIP (not found): {path.name}")
        return {}

    changes: Counter[str] = Counter()
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            old = record.get("character", "")
            new = normalize_character(old) if old else old
            if old != new:
                changes[f"{old!r} -> {new!r}"] += 1
                record["character"] = new
            records.append(record)

    if changes and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")

    return dict(changes)


def fix_guides(path: Path, dry_run: bool) -> dict[str, int]:
    """Normalize character field in guides.json. Returns change counts.

    guides.json structure: {"combat_guides": {key: guide}, "route_guides": {...}, "deck_guides": {...}}
    Keys are like "enemy:character" or "act:character" or "character:archetype".
    """
    if not path.exists():
        print(f"  SKIP (not found): {path.name}")
        return {}

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    changes: Counter[str] = Counter()

    for guide_type in ("combat_guides", "route_guides", "deck_guides"):
        guides = data.get(guide_type, {})
        if not isinstance(guides, dict):
            continue

        # Normalize character field in each guide value
        new_guides: dict[str, dict] = {}
        for old_key, guide in guides.items():
            old_char = guide.get("character", "")
            new_char = normalize_character(old_char) if old_char else old_char
            if old_char != new_char:
                changes[f"{guide_type}: {old_char!r} -> {new_char!r}"] += 1
                guide["character"] = new_char

            # Recompute the key with normalized character
            if guide_type == "combat_guides":
                new_key = f"{guide.get('enemy_key', '').lower()}:{new_char}"
            elif guide_type == "route_guides":
                new_key = f"{guide.get('act', 0)}:{new_char}"
            else:
                new_key = f"{new_char}:{guide.get('archetype', '').lower()}"

            if new_key in new_guides:
                # Duplicate after normalization — keep higher version
                existing = new_guides[new_key]
                if guide.get("version", 0) > existing.get("version", 0):
                    new_guides[new_key] = guide
                    changes[f"dedup {guide_type}: replaced older at {new_key}"] += 1
                else:
                    changes[f"dedup {guide_type}: skipped dup at {new_key}"] += 1
            else:
                new_guides[new_key] = guide

        before = len(guides)
        after = len(new_guides)
        data[guide_type] = new_guides
        if before != after:
            changes[f"dedup {guide_type}: {before} -> {after} guides"] += 1

    if changes and not dry_run:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return dict(changes)


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    mode = "DRY RUN" if dry_run else "APPLYING CHANGES"
    print(f"=== Character Name Normalization ({mode}) ===\n")

    # JSONL stores
    jsonl_files = [
        MEMORY_V2 / "combat_episodes.jsonl",
        MEMORY_V2 / "route_memories.jsonl",
        MEMORY_V2 / "card_builds.jsonl",
    ]

    total_changes = 0
    for path in jsonl_files:
        print(f"Processing {path.name}...")
        changes = fix_jsonl(path, dry_run)
        if changes:
            for desc, count in changes.items():
                print(f"  {desc}: {count}")
                total_changes += count
        else:
            print("  (no changes needed)")

    # Guides
    print("\nProcessing guides.json...")
    guide_changes = fix_guides(GUIDES_PATH, dry_run)
    if guide_changes:
        for desc, count in guide_changes.items():
            print(f"  {desc}: {count}")
            total_changes += count
    else:
        print("  (no changes needed)")

    print(f"\nTotal changes: {total_changes}")
    if dry_run and total_changes > 0:
        print("Run without --dry-run to apply changes.")


if __name__ == "__main__":
    main()
