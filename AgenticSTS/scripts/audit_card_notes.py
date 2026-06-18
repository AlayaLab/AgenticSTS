"""Audit per-card notes in the shared CardMemoryStore for suspect lineage.

Three buckets are flagged:

1. **manual-apply lineage** — any ``note_history`` entry whose ``reason``
   matches a "manual apply" / "dry-run" / "dry_run" pattern. These were
   written by one-off seeding scripts rather than the regular postrun
   ``card_note_updater`` path, so they bypassed the trace-grounded
   validation.
2. **orphan notes** — non-empty ``note`` field with empty ``note_history``.
   The note has no audit trail, meaning it was inserted directly into the
   JSON (seed bootstrap or manual edit) and was never produced by a
   ``with_new_note`` call.
3. **manual-apply still-served** — manual-apply lineage entries where the
   *current* ``note`` text equals the manual-apply payload (i.e., the
   suspect note is still what the agent reads at decision time).

Reads ``<STS2_DATA_REPO>/memory/v2/card_memories.json`` (or the project's
``data/memory/v2/card_memories.json`` fallback). Read-only — never writes.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import re
import shutil
import sys
from pathlib import Path

from src.storage import paths


_SUSPECT_REASON = re.compile(r"manual\s*apply|dry[\s_-]*run", re.IGNORECASE)


def audit(card_memories_path: Path) -> dict:
    if not card_memories_path.exists():
        raise FileNotFoundError(card_memories_path)
    with card_memories_path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    entries = data if isinstance(data, list) else data.get("cards", [])

    total = len(entries)
    manual_apply: list[dict] = []
    orphan: list[dict] = []

    for e in entries:
        history = e.get("note_history") or []
        current_note = (e.get("note") or "").strip()

        suspect = [
            h for h in history
            if isinstance(h, dict) and _SUSPECT_REASON.search(str(h.get("reason", "")))
        ]
        if suspect:
            still_served = any(
                (h.get("note") or "").strip() == current_note and current_note
                for h in suspect
            )
            manual_apply.append({
                "character": e.get("character"),
                "card_name": e.get("card_name"),
                "current_note": current_note,
                "manual_apply_history": [
                    {
                        "run_id": h.get("run_id"),
                        "reason": h.get("reason"),
                        "note": h.get("note"),
                    }
                    for h in suspect
                ],
                "still_served": still_served,
            })

        if current_note and not history:
            orphan.append({
                "character": e.get("character"),
                "card_name": e.get("card_name"),
                "play_count": e.get("play_count", 0),
                "sample_count": e.get("sample_count", 0),
                "current_note": current_note,
            })

    return {
        "path": str(card_memories_path),
        "total_entries": total,
        "manual_apply": manual_apply,
        "orphan": orphan,
    }


def render(report: dict, *, verbose: bool) -> None:
    print(f"# Card-note audit: {report['path']}")
    print(f"Total entries: {report['total_entries']}")
    ma = report["manual_apply"]
    op = report["orphan"]
    still_served = sum(1 for x in ma if x["still_served"])
    print(f"Manual-apply lineage: {len(ma)} (still-served: {still_served})")
    print(f"Orphan notes (no history, non-empty note): {len(op)}")
    print()

    print("## Manual-apply lineage")
    if not ma:
        print("(none)")
    for x in sorted(ma, key=lambda r: (not r["still_served"], r["card_name"] or "")):
        flag = "STILL-SERVED" if x["still_served"] else "superseded"
        print(f"- [{flag}] {x['character']} :: {x['card_name']}")
        if verbose:
            print(f"    current_note: {x['current_note']!r}")
            for h in x["manual_apply_history"]:
                print(f"    history     : run={h['run_id']} reason={h['reason']!r}")
                print(f"                  note={h['note']!r}")
    print()

    print("## Orphan notes (no note_history, non-empty current note)")
    if not op:
        print("(none)")
    for x in sorted(op, key=lambda r: (-(r["sample_count"] or 0), r["card_name"] or "")):
        print(
            f"- {x['character']} :: {x['card_name']}  "
            f"(plays={x['play_count']}, sample={x['sample_count']})"
        )
        if verbose:
            print(f"    note: {x['current_note']!r}")


def purge_orphans(card_memories_path: Path, *, apply: bool) -> dict:
    """Clear ``note`` on entries with empty ``note_history`` and non-empty note.

    Stats fields (play_count / total_damage / sample_count / etc.) are
    preserved — only the ``note`` text is reset to ``""``. The next postrun
    ``card_note_updater`` MANDATORY-first-note rule will then re-populate
    with trace-grounded content.

    When ``apply=False``, returns the would-be changes without writing.
    When ``apply=True``, snapshots the original to a sibling
    ``card_memories.<UTC>.bak.json`` before overwriting in place.

    Manual-apply lineage entries are deliberately untouched: the audit
    showed all five are already superseded by regular postrun writes, so
    their ``note`` field is no longer the suspect text.
    """
    if not card_memories_path.exists():
        raise FileNotFoundError(card_memories_path)

    with card_memories_path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    is_list = isinstance(data, list)
    entries = data if is_list else data.get("cards", [])

    cleared: list[dict] = []
    for e in entries:
        history = e.get("note_history") or []
        current_note = (e.get("note") or "").strip()
        if current_note and not history:
            cleared.append({
                "character": e.get("character"),
                "card_name": e.get("card_name"),
                "old_note": current_note,
            })
            if apply:
                e["note"] = ""

    result = {
        "path": str(card_memories_path),
        "cleared_count": len(cleared),
        "cleared": cleared,
        "applied": apply,
        "snapshot_path": None,
    }

    if apply and cleared:
        ts = _dt.datetime.now(_dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        snap = card_memories_path.with_name(
            f"{card_memories_path.stem}.{ts}.bak.json"
        )
        shutil.copy2(card_memories_path, snap)
        result["snapshot_path"] = str(snap)
        with card_memories_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    return result


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "--path", type=Path, default=None,
        help="Override card_memories.json path. Default: paths.card_memories_file()",
    )
    p.add_argument(
        "--json", action="store_true",
        help="Emit JSON report to stdout instead of human-readable summary.",
    )
    p.add_argument(
        "-v", "--verbose", action="store_true",
        help="Include note text and history detail in summary mode.",
    )
    p.add_argument(
        "--purge-orphans", action="store_true",
        help=(
            "Clear `note` on entries with empty `note_history` and non-empty "
            "note. Default is dry-run (preview only). Pair with --apply to "
            "actually write. Stats fields are preserved — only the note text "
            "resets. A timestamped snapshot is saved next to the JSON before "
            "overwrite."
        ),
    )
    p.add_argument(
        "--apply", action="store_true",
        help="With --purge-orphans, actually write changes (default is dry-run).",
    )
    args = p.parse_args(argv)

    target = args.path or paths.card_memories_file()

    if args.purge_orphans:
        result = purge_orphans(target, apply=args.apply)
        if args.json:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
            return 0
        verb = "Cleared" if args.apply else "Would clear"
        print(f"# Purge orphans @ {result['path']}")
        print(f"{verb} note on {result['cleared_count']} orphan entries.")
        if result["snapshot_path"]:
            print(f"Snapshot: {result['snapshot_path']}")
        if args.verbose:
            for x in result["cleared"]:
                print(f"- {x['character']} :: {x['card_name']}")
                print(f"    {x['old_note'][:200]}")
        if not args.apply and result["cleared_count"]:
            print()
            print("(dry-run — pass --apply to write)")
        return 0

    report = audit(target)
    if args.json:
        json.dump(report, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        render(report, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
