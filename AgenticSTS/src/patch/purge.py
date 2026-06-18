"""Per-store purge functions driven by changed_entities set (slugged)."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from src.patch.slug import slug


@dataclass
class PurgeReport:
    store: str
    deleted: int = 0
    kept: int = 0
    details: list[str] | None = None


def _card_name_from_key(key: str) -> str:
    """Keys are 'character::card_name'; extract and slug the card_name."""
    parts = key.split("::", 1)
    return slug(parts[1]) if len(parts) == 2 else slug(key)


def purge_card_memories(path: Path, changed: set[str], *, dry_run: bool) -> PurgeReport:
    report = PurgeReport(store="card_memories")
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))

    # Handle both dict (old) and list (new) formats
    if isinstance(data, list):
        # New format: list of CardMemory dicts with 'character' and 'card_name' fields
        survivors = []
        for entry in data:
            card_name = entry.get("card_name", "")
            card_slug = slug(card_name)
            if card_slug in changed:
                report.deleted += 1
            else:
                survivors.append(entry)
                report.kept += 1
    else:
        # Old format: dict with 'character::card_name' keys
        survivors = {}
        for k, v in data.items():
            card_slug = _card_name_from_key(k)
            if card_slug in changed:
                report.deleted += 1
            else:
                survivors[k] = v
                report.kept += 1

    if not dry_run and report.deleted > 0:
        path.write_text(json.dumps(survivors, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _enemy_key_matches(enemy_key: str, changed: set[str]) -> bool:
    """Check if enemy_key matches any changed major enemy (handles multi:A+B format)."""
    if not enemy_key:
        return False
    # multi:A+B → check each component
    key = enemy_key.lower()
    if key.startswith("multi:"):
        key = key[6:]
    parts = [slug(p) for p in key.replace("+", "|").split("|")]
    return any(p in changed for p in parts)


def purge_jsonl_episodes(
    path: Path,
    *,
    changed_major_enemies: set[str],
    changed_cards: set[str],
    dry_run: bool,
) -> PurgeReport:
    """Purge combat_episodes.jsonl by changed_major_enemies or changed_cards.

    Deletes any episode that references a changed enemy or card.
    Preserves metadata header (_meta line).
    """
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        enemy_key = row.get("enemy_key", "")
        cards = row.get("cards_played", []) or []
        card_slugs = {slug(c) for c in cards}

        if _enemy_key_matches(enemy_key, changed_major_enemies):
            report.deleted += 1
            continue
        if card_slugs & changed_cards:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1

    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report


def purge_jsonl_card_builds(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Purge card_builds.jsonl by changed cards in starting_deck, final_deck, key_cards, or card_play_counts.

    Deletes any record that references a changed card in any deck or play list.
    Preserves metadata header (_meta line).
    """
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        all_names: set[str] = set()
        for k in ("starting_deck", "final_deck", "key_cards"):
            vals = row.get(k, []) or []
            for v in vals:
                if isinstance(v, str):
                    all_names.add(slug(v))
                elif isinstance(v, dict) and "card" in v:
                    all_names.add(slug(v["card"]))
        for pair in row.get("card_play_counts", []) or []:
            if isinstance(pair, list) and pair:
                all_names.add(slug(pair[0]))
        if all_names & changed:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report


def purge_jsonl_event_memories(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Purge event_memories.jsonl by changed cards in cards_gained.

    Deletes any record that references a changed card.
    Preserves metadata header (_meta line).
    """
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    lines = path.read_text(encoding="utf-8").splitlines()
    keep: list[str] = []
    for ln in lines:
        if not ln.strip():
            continue
        if ln.startswith('{"_meta"'):
            keep.append(ln)
            continue
        row = json.loads(ln)
        cards = row.get("cards_gained", []) or []
        if {slug(c) for c in cards} & changed:
            report.deleted += 1
            continue
        keep.append(ln)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report


def purge_skills(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Purge skills.json by changed cards in trigger.requires_cards.

    Deletes any skill that requires a changed card.
    """
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))

    # Handle both dict (old) and list (new) formats
    if isinstance(data, list):
        # New format: list of Skill dicts
        skills = data
        is_list_format = True
    else:
        # Old format: dict with "skills" key
        skills = data.get("skills", [])
        is_list_format = False

    keep = []
    for sk in skills:
        required = sk.get("trigger", {}).get("requires_cards", []) or []
        if {slug(c) for c in required} & changed:
            report.deleted += 1
            continue
        keep.append(sk)
        report.kept += 1

    if not dry_run and report.deleted > 0:
        if is_list_format:
            path.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
        else:
            data["skills"] = keep
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def purge_silent_card_notes(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Purge silent_card_notes.json by changed card names.

    Deletes any note entry for a changed card.
    """
    report = PurgeReport(store=path.name)
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    keep = []
    for entry in data:
        name = entry.get("card_name", "")
        if slug(name) in changed:
            report.deleted += 1
            continue
        keep.append(entry)
        report.kept += 1
    if not dry_run and report.deleted > 0:
        path.write_text(json.dumps(keep, indent=2, ensure_ascii=False), encoding="utf-8")
    return report


def _text_references_any(text: str, changed: set[str]) -> bool:
    """Return True if any entity in changed appears (slug-matched) in text."""
    if not text:
        return False
    text_slug = slug(text)
    return any(entity in text_slug for entity in changed if entity)


def purge_evolution_dir(evo_root: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Scan every file under evolution dir and delete those that reference changed entities."""
    report = PurgeReport(store="evolution")
    if not evo_root.exists():
        return report
    for subdir in ("tools", "proposals", "ab_test_results"):
        d = evo_root / subdir
        if not d.exists():
            continue
        for f in d.iterdir():
            if not f.is_file():
                continue
            try:
                content = f.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            if _text_references_any(content, changed):
                report.deleted += 1
                if not dry_run:
                    f.unlink()
            else:
                report.kept += 1
    # evolution_log.jsonl: per-line scan
    log = evo_root / "evolution_log.jsonl"
    if log.exists():
        lines = log.read_text(encoding="utf-8").splitlines()
        keep: list[str] = []
        for ln in lines:
            if not ln.strip():
                continue
            if _text_references_any(ln, changed):
                report.deleted += 1
            else:
                keep.append(ln)
                report.kept += 1
        if not dry_run:
            log.write_text("\n".join(keep) + "\n", encoding="utf-8")
    return report


def _guide_references_changed(guide: dict, changed: set[str]) -> bool:
    """Check if a guide entry references any changed entity.

    Inspects both structured fields (enemy_key, key_cards) and narrative
    text fields (guide_text, mechanic_summary, round_triggers,
    threshold_triggers, danger_windows, failure_modes, key_patterns).
    """
    # Structured refs
    ek = guide.get("enemy_key", "")
    if ek and slug(ek) in changed:
        return True
    for kc in guide.get("key_cards", []) or []:
        name = kc if isinstance(kc, str) else (kc.get("card", "") if isinstance(kc, dict) else "")
        if name and slug(name) in changed:
            return True
    # Narrative text scan — collect from any field that might hold text.
    # Fields vary by guide section: guide_text (all), mechanic_summary / round_triggers /
    # threshold_triggers / danger_windows / failure_modes / key_patterns (list or str),
    # preferred_pattern (str).
    text_parts: list[str] = []
    for field in (
        "guide_text",
        "mechanic_summary",
        "round_triggers",
        "threshold_triggers",
        "danger_windows",
        "failure_modes",
        "key_patterns",
        "preferred_pattern",
    ):
        val = guide.get(field)
        if val is None:
            continue
        if isinstance(val, str):
            text_parts.append(val)
        elif isinstance(val, list):
            text_parts.extend(item for item in val if isinstance(item, str))
    combined = " ".join(text_parts)
    if not combined:
        return False
    text_slug = slug(combined)
    return any(e in text_slug for e in changed if e)


def purge_guides(path: Path, *, changed: set[str], dry_run: bool) -> PurgeReport:
    """Remove guides that reference changed entities; keep unaffected guides.

    Handles both dict-keyed and list formats for each guide section.
    Sections scanned: combat_guides, route_guides, deck_guides, event_guides.
    """
    report = PurgeReport(store="guides")
    if not path.exists():
        return report
    data = json.loads(path.read_text(encoding="utf-8"))
    any_changed = False
    for section in ("combat_guides", "route_guides", "deck_guides", "event_guides"):
        guides = data.get(section)
        if guides is None:
            continue
        if isinstance(guides, dict):
            survivors: dict = {}
            for key, guide in guides.items():
                if not isinstance(guide, dict):
                    survivors[key] = guide
                    report.kept += 1
                    continue
                if _guide_references_changed(guide, changed):
                    report.deleted += 1
                    any_changed = True
                else:
                    survivors[key] = guide
                    report.kept += 1
            if len(survivors) != len(guides):
                data[section] = survivors
        elif isinstance(guides, list):
            survivor_list: list = []
            for guide in guides:
                if not isinstance(guide, dict):
                    survivor_list.append(guide)
                    report.kept += 1
                    continue
                if _guide_references_changed(guide, changed):
                    report.deleted += 1
                    any_changed = True
                else:
                    survivor_list.append(guide)
                    report.kept += 1
            if len(survivor_list) != len(guides):
                data[section] = survivor_list
    if not dry_run and any_changed:
        path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    return report
