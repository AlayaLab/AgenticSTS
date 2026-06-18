"""Backfill event memories from historical JSONL run logs.

Parses logs for event state+decision pairs, computes deck/relic/potion diffs,
and appends new EventMemory entries to event_memories.jsonl.

Usage:
    python -m scripts.backfill_event_memories [--dry-run] [--run-id RUN_ID]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

LOGS_DIR = Path("logs")
EVENT_MEMORIES_PATH = paths.event_memories_file()


def _card_name(card: dict) -> str:
    name = card.get("name", "")
    if card.get("upgraded"):
        name += "+"
    return name


def _multiset_diff(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    """Return (added, removed) between two multisets."""
    from collections import Counter
    cb, ca = Counter(before), Counter(after)
    added = list((ca - cb).elements())
    removed = list((cb - ca).elements())
    return added, removed


def _extract_character(log_entries: list[dict]) -> str:
    """Extract character name from run_start or first state entry."""
    for entry in log_entries:
        if entry.get("event") == "run_start":
            return entry.get("character", "")
        if entry.get("event") == "state":
            summary = entry.get("summary", "")
            # e.g. "[event] | F18 | The Silent | HP:70/70 G:128"
            parts = summary.split("|")
            if len(parts) >= 3:
                return parts[2].strip()
    return ""


def _parse_run_id_from_filename(path: Path) -> str:
    """Extract run_id from filename like run_20260321_172325_9e626be7.jsonl."""
    name = path.stem  # run_20260321_172325_9e626be7
    if name.startswith("run_"):
        return name[4:]  # 20260321_172325_9e626be7
    return name


def _make_memory_id(run_id: str, event_id: str, floor: int, stage: int) -> str:
    """Deterministic memory_id from run+event+floor+stage."""
    key = f"{run_id}:{event_id}:{floor}:{stage}"
    return hashlib.md5(key.encode()).hexdigest()[:12]


def parse_event_memories_from_log(
    log_path: Path,
    run_outcomes: dict[str, tuple[bool, int]] | None = None,
) -> list[dict]:
    """Parse a single log file and extract event memories.

    Returns list of EventMemory-compatible dicts. When ``run_outcomes`` maps
    ``run_id → (victory, final_floor)`` (built from ``runs/history.jsonl``
    upstream), each memory is stamped with the correct run anchor so guide
    consolidation has the same signal as live extraction.
    """
    entries: list[dict] = []
    with open(log_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    continue

    if not entries:
        return []

    run_id = _parse_run_id_from_filename(log_path)
    character = _extract_character(entries)
    run_victory, run_final_floor = (run_outcomes or {}).get(run_id, (False, 0))

    # Collect all event states and decisions in order
    event_states: list[tuple[int, dict]] = []  # (index, entry)
    event_decisions: list[tuple[int, dict]] = []

    for i, entry in enumerate(entries):
        if entry.get("event") == "state" and entry.get("state_type") == "event":
            event_states.append((i, entry))
        elif (
            entry.get("event") == "decision"
            and entry.get("state_type") == "event"
        ):
            event_decisions.append((i, entry))

    if not event_states:
        return []

    memories: list[dict] = []

    # Group event states by (event_id, floor)
    # Each group may have multiple stages (real choice → Proceed)
    groups: dict[tuple[str, int], list[tuple[int, dict]]] = {}
    for idx, entry in event_states:
        ed = entry.get("event_details", {})
        key = (ed.get("event_id", ""), entry.get("floor", 0))
        groups.setdefault(key, []).append((idx, entry))

    for (event_id, floor), state_entries in groups.items():
        stage = 0
        for state_idx, state_entry in state_entries:
            ed = state_entry.get("event_details", {})
            options = ed.get("options", [])
            is_finished = ed.get("is_finished", False)
            option_titles = [o.get("title", "") for o in options]
            is_proceed_only = (
                len(options) == 1
                and options[0].get("is_proceed", False)
            )

            # Skip Proceed-only stages — low information value
            if is_proceed_only:
                continue

            # Find the decision that follows this state
            chosen_index = -1
            chosen_text = ""
            reasoning = ""
            for dec_idx, dec_entry in event_decisions:
                if dec_idx > state_idx:
                    action = dec_entry.get("action", {})
                    if action.get("action") == "choose_event_option":
                        chosen_index = action.get("option_index", -1)
                        reasoning = dec_entry.get("reasoning", "")
                        if 0 <= chosen_index < len(option_titles):
                            chosen_text = option_titles[chosen_index]
                        break

            if chosen_index < 0:
                # No decision found for this event state — skip
                continue

            # Compute diffs: find the next state entry (any type) after decision
            hp_before = state_entry.get("hp", 0)
            hp_max = state_entry.get("hp_max", 0)
            gold_before = state_entry.get("player", {}).get("gold", 0)
            deck_before = [_card_name(c) for c in state_entry.get("deck", [])]
            relics_before = [
                r.get("name", "") for r in state_entry.get("relics", [])
                if r.get("name")
            ]
            potions_before = [
                p.get("name", "") for p in state_entry.get("potions", [])
                if p.get("name") and p.get("name") != "Empty"
            ]

            # Find next state after this event for diff computation
            hp_after = hp_before
            gold_after = gold_before
            cards_gained: list[str] = []
            cards_lost: list[str] = []
            relics_gained: list[str] = []
            potions_gained: list[str] = []

            for future_entry in entries[state_idx + 1:]:
                if future_entry.get("event") == "state":
                    hp_after = future_entry.get("hp", hp_before)
                    gold_after = future_entry.get("player", {}).get("gold", gold_before)
                    deck_after = [_card_name(c) for c in future_entry.get("deck", [])]
                    relics_after = [
                        r.get("name", "") for r in future_entry.get("relics", [])
                        if r.get("name")
                    ]
                    potions_after = [
                        p.get("name", "") for p in future_entry.get("potions", [])
                        if p.get("name") and p.get("name") != "Empty"
                    ]
                    cards_gained, cards_lost = _multiset_diff(deck_before, deck_after)
                    relics_gained, _ = _multiset_diff(relics_before, relics_after)
                    potions_gained, _ = _multiset_diff(potions_before, potions_after)
                    break

            act = state_entry.get("act", 0)
            if act == 0:
                # Infer act from floor
                f = state_entry.get("floor", 0)
                act = 1 if f <= 17 else (2 if f <= 34 else 3)

            memory = {
                "memory_id": _make_memory_id(run_id, event_id, floor, stage),
                "run_id": run_id,
                "floor": floor,
                "act": act,
                "event_id": event_id,
                "event_title": ed.get("event_name", ed.get("title", event_id)),
                "character": character.lower() if character else "",
                "chosen_option_index": chosen_index,
                "chosen_option_text": chosen_text,
                "all_options": option_titles,
                "hp_before": hp_before,
                "hp_after": hp_after,
                "gold_before": gold_before,
                "gold_after": gold_after,
                "cards_gained": cards_gained,
                "cards_lost": cards_lost,
                "relics_gained": relics_gained,
                "potions_gained": potions_gained,
                "run_victory": run_victory,
                "run_final_floor": run_final_floor,
                "timestamp": state_entry.get("ts", time.time()),
            }
            memories.append(memory)
            stage += 1

    return memories


def _load_run_outcomes() -> dict[str, tuple[bool, int]]:
    """Build ``run_id → (victory, final_floor)`` from runs/history.jsonl.

    Guide consolidation relies on this outcome anchor to score past event
    decisions; missing entries fall back to ``(False, 0)`` which the
    consuming prompt treats as "outcome unknown".
    """
    try:
        from src.runs.history import RunHistoryStore
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("Could not import RunHistoryStore: %s", exc)
        return {}

    history_path = paths.runs_history_file()
    if not history_path.exists():
        logger.warning("No run history at %s — outcomes will be blank", history_path)
        return {}

    store = RunHistoryStore.load(history_path)
    return {
        rec.run_id: (bool(rec.victory), int(rec.final_floor))
        for rec in store.load_all()
        if rec.run_id
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill event memories from logs")
    parser.add_argument("--dry-run", action="store_true", help="Print without writing")
    parser.add_argument("--run-id", type=str, help="Only process a specific run_id")
    args = parser.parse_args()

    run_outcomes = _load_run_outcomes()
    logger.info("Loaded %d run outcomes from history", len(run_outcomes))

    # Load existing memory IDs to avoid duplicates
    existing_ids: set[str] = set()
    existing_run_ids: set[str] = set()
    if EVENT_MEMORIES_PATH.exists():
        with open(EVENT_MEMORIES_PATH, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    existing_ids.add(d.get("memory_id", ""))
                    existing_run_ids.add(d.get("run_id", ""))

    log_files = sorted(LOGS_DIR.glob("run_*.jsonl"))
    logger.info("Found %d log files, %d runs already in event_memories", len(log_files), len(existing_run_ids))

    all_new: list[dict] = []
    processed = 0
    skipped_existing = 0

    for log_path in log_files:
        run_id = _parse_run_id_from_filename(log_path)

        if args.run_id and run_id != args.run_id:
            continue

        # Skip runs that already have event memories (unless specific run requested)
        if not args.run_id and run_id in existing_run_ids:
            skipped_existing += 1
            continue

        try:
            memories = parse_event_memories_from_log(log_path, run_outcomes)
        except Exception as exc:
            logger.warning("Failed to parse %s: %s", log_path.name, exc)
            continue

        new_memories = [m for m in memories if m["memory_id"] not in existing_ids]
        if new_memories:
            all_new.extend(new_memories)
            logger.info(
                "%s: extracted %d event memories (%d new)",
                log_path.name, len(memories), len(new_memories),
            )
        processed += 1

    logger.info(
        "Processed %d logs (skipped %d existing), found %d new event memories",
        processed, skipped_existing, len(all_new),
    )

    if args.dry_run:
        for m in all_new[:20]:
            print(
                f"  {m['event_id']:30s} F{m['floor']:2d} "
                f"→ {m['chosen_option_text']:30s} "
                f"relics={m['relics_gained']} cards_g={len(m['cards_gained'])} "
                f"HP:{m['hp_before']}→{m['hp_after']} "
                f"[{m['run_id'][:8]}]"
            )
        if len(all_new) > 20:
            print(f"  ... and {len(all_new) - 20} more")
        return

    if not all_new:
        logger.info("Nothing to backfill.")
        return

    # Append to event_memories.jsonl
    EVENT_MEMORIES_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(EVENT_MEMORIES_PATH, "a", encoding="utf-8") as f:
        for m in all_new:
            f.write(json.dumps(m) + "\n")

    logger.info("Appended %d new event memories to %s", len(all_new), EVENT_MEMORIES_PATH)


if __name__ == "__main__":
    main()
