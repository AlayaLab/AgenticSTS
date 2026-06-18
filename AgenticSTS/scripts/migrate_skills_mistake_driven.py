"""One-shot migration: drop cohort-era combat skills + strip legacy trigger fields.

Run once after merging the mistake-driven-discovery redesign:

    python -m scripts.migrate_skills_mistake_driven

Keeps:
- source=seed skills (all categories)
- source=discovered skills with category in {map, event, rest, deck_building, shop}

Drops:
- All combat/boss skills regardless of source (cohort-produced, evolved, etc.)
  — mistake-driven pipeline re-derives the needed corrections from over-baseline
  combats. Descriptive combat rhythm belongs in combat_guide, not skills.

Writes skills.json.pre-mistake-driven.bak before overwriting.
See docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §7.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402


_NONCOMBAT_CATEGORIES = {"map", "event", "rest", "deck_building", "shop"}
_LEGACY_TRIGGER_FIELDS = ("threat_levels", "intent_classes", "deck_stages", "tags")


def migrate(skills_path: Path) -> tuple[int, int]:
    """Filter skills.json in place. Returns (kept_count, dropped_count).

    Supports both the list-format and the `{"skills": [...]}` envelope format
    for skills.json. Backup is written before any mutation.
    """
    data = json.loads(skills_path.read_text(encoding="utf-8"))
    skills = data if isinstance(data, list) else data.get("skills", [])

    kept: list[dict] = []
    for s in skills:
        source = s.get("source", "")
        category = s.get("category", "")
        if source == "seed":
            kept.append(s)
            continue
        if source == "discovered" and category in _NONCOMBAT_CATEGORIES:
            kept.append(s)
            continue
        # Drop: all combat/boss skills + any evolved/refined/merged variants

    # Strip legacy trigger fields from survivors
    for s in kept:
        trig = s.get("trigger", {})
        for f in _LEGACY_TRIGGER_FIELDS:
            trig.pop(f, None)

    backup = skills_path.with_suffix(".json.pre-mistake-driven.bak")
    shutil.copy2(skills_path, backup)

    # Preserve the original top-level format (list vs envelope)
    if isinstance(data, list):
        out: object = kept
    else:
        data["skills"] = kept
        out = data

    skills_path.write_text(json.dumps(out, indent=2), encoding="utf-8")
    return len(kept), len(skills) - len(kept)


def main() -> int:
    path = paths.skills_file()
    if not path.exists():
        print(f"no skills file at {path}", file=sys.stderr)
        return 1
    kept, dropped = migrate(path)
    print(f"Migration complete: kept={kept}, dropped={dropped}")
    print(
        f"Backup written to {path.with_suffix('.json.pre-mistake-driven.bak')}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
