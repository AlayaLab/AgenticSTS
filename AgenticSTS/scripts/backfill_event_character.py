"""One-time backfill: populate empty character fields in event_memories.jsonl.

Reads character from combat_episodes.jsonl (same run_id), falling back
to log file grep when no combat episode exists for the run.

Strategy for run_id matching:
- Event memories use full format: 20260404_184934_8274fa40
- Older combat episodes use short hex: 8274fa40a1de (starts with same 8-char hash)
- Log files are named: run_20260404_184934_8274fa40.jsonl (direct match)
- Character in logs appears in 'summary' field: '[event] | F1 | The Silent | HP:...'
"""

from __future__ import annotations

import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402

EVENT_PATH = paths.event_memories_file()
COMBAT_PATH = paths.combat_episodes_file()
LOG_DIR = Path("logs")
BACKUP_DIR = paths.memory_v2_dir() / "_backups"


def _hash_from_run_id(run_id: str) -> str:
    """Extract 8-char hex hash from a full run_id like 20260404_184934_8274fa40."""
    parts = run_id.split("_")
    if len(parts) >= 3:
        return parts[-1]
    return run_id


def _build_run_character_map() -> dict[str, str]:
    """Build run_id -> character map from combat episodes.

    Handles both full run_ids (20260408_011715_12ee2542) and short hex
    run_ids (8274fa40a1de). Index by both the full id and the 8-char
    hash prefix so event run_ids can match either format.
    """
    mapping: dict[str, str] = {}
    if not COMBAT_PATH.exists():
        return mapping
    with open(COMBAT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            run_id = d.get("run_id", "")
            character = d.get("character", "")
            if not (run_id and character):
                continue
            # Store by full run_id
            if run_id not in mapping:
                mapping[run_id] = character
            # Also index by first 8 chars (hash prefix of short hex ids)
            if len(run_id) >= 8:
                prefix = run_id[:8]
                if prefix not in mapping:
                    mapping[prefix] = character
    return mapping


def _parse_character_from_summary(summary: str) -> str:
    """Extract character from log summary like '[event] | F1 | The Silent | HP:70/70'.

    Returns lowercased character name or empty string.
    """
    parts = [p.strip() for p in summary.split("|")]
    # Format: [state_type] | F{floor} | {Character Name} | HP:...
    if len(parts) >= 3:
        candidate = parts[2].strip()
        # Validate it looks like a character name (not HP/gold/etc)
        if candidate and not candidate.startswith("HP") and not candidate.startswith("G:"):
            return candidate.lower()
    return ""


def _grep_character_from_log(run_id: str) -> str:
    """Try to find character from the run's log file.

    Checks both direct key lookup and summary-field parsing.
    """
    candidates = list(LOG_DIR.glob(f"run_{run_id}*.jsonl"))
    if not candidates:
        short = run_id[:8] if len(run_id) > 8 else run_id
        candidates = list(LOG_DIR.glob(f"run_*{short}*.jsonl"))
    if not candidates:
        return ""
    log_path = candidates[0]
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                # Fast pre-filter before JSON parse
                has_char_key = '"character"' in line
                has_summary = '"summary"' in line
                if not (has_char_key or has_summary):
                    continue
                try:
                    d = json.loads(line)
                except json.JSONDecodeError:
                    continue
                # Try direct character keys first
                if has_char_key:
                    for key in ("character", "player_character"):
                        val = d.get(key, "")
                        if val and isinstance(val, str):
                            return val.lower().strip()
                    player = d.get("player", {})
                    if isinstance(player, dict):
                        val = player.get("character", "")
                        if val and isinstance(val, str):
                            return val.lower().strip()
                # Try parsing from summary field
                if has_summary:
                    summary = d.get("summary", "")
                    if summary:
                        char = _parse_character_from_summary(summary)
                        if char:
                            return char
    except Exception:
        pass
    return ""


def main() -> None:
    if not EVENT_PATH.exists():
        print(f"No event memories file at {EVENT_PATH}")
        sys.exit(1)

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_DIR / f"pre_character_backfill_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EVENT_PATH, backup_dir / EVENT_PATH.name)
    print(f"Backup saved to {backup_dir}")

    # Build run -> character map (full ids + 8-char hash prefixes)
    run_char_map = _build_run_character_map()
    print(f"Loaded {len(run_char_map)} run->character mappings from combat episodes")

    # Process entries
    entries: list[dict] = []
    with open(EVENT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    updated_combat = 0
    updated_log = 0
    unresolved = 0
    log_cache: dict[str, str] = {}  # run_id -> character cache for log lookups

    for entry in entries:
        if entry.get("character", ""):
            continue
        run_id = entry.get("run_id", "")

        # Try direct match
        character = run_char_map.get(run_id, "")

        # Try 8-char hash prefix match against combat episodes
        if not character:
            hash_prefix = _hash_from_run_id(run_id)
            character = run_char_map.get(hash_prefix, "")

        if character:
            entry["character"] = character
            updated_combat += 1
            continue

        # Fall back to log file grep (with per-run caching)
        if run_id not in log_cache:
            log_cache[run_id] = _grep_character_from_log(run_id)
        character = log_cache[run_id]

        if character:
            entry["character"] = character
            updated_log += 1
        else:
            unresolved += 1

    # Write back
    with open(EVENT_PATH, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    total = len(entries)
    already = total - updated_combat - updated_log - unresolved
    print(f"\nResults: {total} total entries")
    print(f"  Already had character: {already}")
    print(f"  Updated via combat episodes: {updated_combat}")
    print(f"  Updated via log files: {updated_log}")
    print(f"  Unresolved: {unresolved}")


if __name__ == "__main__":
    main()
