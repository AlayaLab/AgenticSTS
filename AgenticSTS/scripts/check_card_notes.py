"""Check card note coverage and staleness.

Scans data/memory/v2/card_memories.json and reports:
- Cards with play_count >= PLAY_THRESHOLD that have no note (coverage gap)
- Cards whose note was written against an older game_version (staleness)

Excluded from both checks: Token, Status, Event rarity cards (generated/transient).

Exit codes:
  0 — all clear
  1 — coverage gap (missing_high_play > GAP_THRESHOLD) or staleness found

Usage::

    python -m scripts.check_card_notes            # human-readable
    python -m scripts.check_card_notes --json      # machine-readable JSON
    python -m scripts.check_card_notes --threshold 5  # custom play_count threshold
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))
from src.storage import paths  # noqa: E402

MEMORIES_PATH = paths.card_memories_file()
COMPAT_PATH = ROOT / "data" / "version_compatibility.json"

EXCLUDED_RARITIES = {"token", "status", "event", "curse"}
DEFAULT_PLAY_THRESHOLD = 3
DEFAULT_GAP_THRESHOLD = 10  # flag if this many high-play cards lack notes


def _load_current_game_version() -> str:
    if not COMPAT_PATH.exists():
        return ""
    compat = json.loads(COMPAT_PATH.read_text(encoding="utf-8"))
    return compat.get("current", {}).get("game_version", "")


def _load_card_rarities() -> dict[str, str]:
    """Return {card_name_lower: rarity_lower} from knowledge/cards.md via simple JSON parse."""
    cards_json = ROOT / "data" / "knowledge" / "cards.json"
    if not cards_json.exists():
        return {}
    try:
        data = json.loads(cards_json.read_text(encoding="utf-8"))
        return {entry["name"].lower(): entry.get("rarity", "").lower() for entry in data}
    except Exception:
        return {}


def _is_excluded(card_name: str, rarities: dict[str, str]) -> bool:
    key = card_name.lower()
    rarity = rarities.get(key, "")
    if rarity in EXCLUDED_RARITIES:
        return True
    # Fallback heuristic: well-known generated/status card names
    _KNOWN_GENERATED = {
        "shiv", "slimed", "wound", "burn", "dazed", "void", "toxic",
        "beckon", "peck", "status", "curse of the bell",
    }
    return key in _KNOWN_GENERATED


def run_check(play_threshold: int = DEFAULT_PLAY_THRESHOLD) -> dict:
    if not MEMORIES_PATH.exists():
        return {
            "error": f"card_memories.json not found at {MEMORIES_PATH}",
            "current_game_version": _load_current_game_version(),
            "play_threshold": play_threshold,
            "missing_high_play": [],
            "stale_notes": [],
            "by_character": {},
            "summary": {
                "missing_high_play_count": 0,
                "stale_notes_count": 0,
                "total_cards": 0,
                "cards_with_note": 0,
            },
        }

    memories: list[dict] = json.loads(MEMORIES_PATH.read_text(encoding="utf-8"))
    current_version = _load_current_game_version()
    rarities = _load_card_rarities()

    missing_high_play: list[dict] = []
    stale_notes: list[dict] = []

    by_char: dict[str, dict] = {}

    for m in memories:
        char = m.get("character", "unknown")
        card = m.get("card_name", "unknown")
        note = m.get("note", "").strip()
        play_count = m.get("play_count", 0)
        note_version = m.get("game_version", "")

        if char not in by_char:
            by_char[char] = {"total": 0, "with_note": 0, "high_play": 0, "missing": 0}
        by_char[char]["total"] += 1
        if note:
            by_char[char]["with_note"] += 1

        excluded = _is_excluded(card, rarities)
        if excluded:
            continue

        if play_count >= play_threshold:
            by_char[char]["high_play"] += 1
            if not note:
                by_char[char]["missing"] += 1
                missing_high_play.append({
                    "character": char,
                    "card_name": card,
                    "play_count": play_count,
                })

        if note and current_version and note_version and note_version != current_version:
            stale_notes.append({
                "character": char,
                "card_name": card,
                "note_version": note_version,
                "current_version": current_version,
                "play_count": play_count,
            })

    missing_high_play.sort(key=lambda x: -x["play_count"])
    stale_notes.sort(key=lambda x: -x["play_count"])

    return {
        "current_game_version": current_version,
        "play_threshold": play_threshold,
        "missing_high_play": missing_high_play,
        "stale_notes": stale_notes,
        "by_character": by_char,
        "summary": {
            "missing_high_play_count": len(missing_high_play),
            "stale_notes_count": len(stale_notes),
            "total_cards": len(memories),
            "cards_with_note": sum(v["with_note"] for v in by_char.values()),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Check card note coverage and staleness")
    parser.add_argument("--json", action="store_true", help="Output JSON")
    parser.add_argument("--threshold", type=int, default=DEFAULT_PLAY_THRESHOLD,
                        help=f"Min play_count to require a note (default {DEFAULT_PLAY_THRESHOLD})")
    parser.add_argument("--gap-threshold", type=int, default=DEFAULT_GAP_THRESHOLD,
                        help=f"Missing-note count that triggers exit code 1 (default {DEFAULT_GAP_THRESHOLD})")
    args = parser.parse_args()

    result = run_check(play_threshold=args.threshold)

    if args.json:
        print(json.dumps(result, indent=2))
    else:
        s = result["summary"]
        print(f"Card note check  (game: {result['current_game_version']}, play_threshold: {args.threshold})")
        print(f"  Total tracked: {s['total_cards']}  |  With note: {s['cards_with_note']}")
        print(f"  High-play missing note: {s['missing_high_play_count']}  |  Stale notes: {s['stale_notes_count']}")
        print()
        if result["missing_high_play"]:
            print(f"Top missing (play >= {args.threshold}, non-generated):")
            for entry in result["missing_high_play"][:15]:
                print(f"  [{entry['character']}] {entry['card_name']}: {entry['play_count']} plays")
        if result["stale_notes"]:
            print(f"\nStale notes (written on {result['stale_notes'][0]['note_version']}, now {result['current_game_version']}):")
            for entry in result["stale_notes"][:10]:
                print(f"  [{entry['character']}] {entry['card_name']}: {entry['note_version']}")
        if not result["missing_high_play"] and not result["stale_notes"]:
            print("  OK — no gaps or staleness found.")

    has_gap = result["summary"]["missing_high_play_count"] > args.gap_threshold
    has_stale = result["summary"]["stale_notes_count"] > 0
    return 1 if (has_gap or has_stale) else 0


if __name__ == "__main__":
    sys.exit(main())
