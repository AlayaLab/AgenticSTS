"""Drain the sibling-repo merge queue.

``scripts/data_sync.py`` writes conflict quarantine entries to
``<data_repo>/evolution/merge_queue.jsonl`` whenever its per-file drivers
can't auto-resolve (content divergence on the same ``skill_id``, same
``guide_id`` with different ``guide_text``, etc.). Those entries sit in
the queue until drained.

This module does the draining:

    drain(cap=2)  — library API, called from postrun. Handles two entry
                    types:

    skills entries (file="skills/skills.json"):
        Reconstruct Skill objects from the quarantined local/remote dicts,
        run through :func:`run_merge_pair` (LLM + A/B validation). On
        outcome="merged" the new skill is added to the library and the
        queue entry is removed; on abandon/failure the entry is re-queued
        up to 3 times. Bounded by ``cap`` because each entry costs an LLM
        call.

    guides entries (file="memory/v2/guides.json"):
        No LLM. Resolved by preference tuple
        ``(version, episode_count/memory_count, confidence, updated_at)``
        — the stronger-evidence side wins. If remote outranks local, swap
        it into the live guide_store. Consolidation on the next postrun
        rebuilds from accumulated episodes anyway, so convergence is
        naturally robust. Not cap-bounded (cheap to process).

    other sections: held in queue (no handler registered yet).

CLI:
    python -m scripts.drain_merge_queue [--cap N] [--all]
"""
from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import asdict
from pathlib import Path
from typing import Any

from src.memory.guide_store import GuideStore
from src.memory.models_v2 import (
    CombatGuide,
    DeckGuide,
    RouteGuide,
)
from src.memory.event_models import EventGuide
from src.skills.library import SkillLibrary
from src.skills.merge_pipeline import run_merge_pair
from src.skills.models import Skill
from src.storage import paths

logger = logging.getLogger(__name__)


DEFAULT_CAP = 2


def _read_queue(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    entries: list[dict[str, Any]] = []
    for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping corrupt merge_queue line %d: %s", lineno, exc)
    return entries


def _write_queue(path: Path, entries: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        for e in entries:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


async def _process_skill_entry(
    entry: dict[str, Any], *,
    library: SkillLibrary, log_dir: Path, combat_system_prompt: str,
) -> dict[str, Any]:
    """Run one skill-merge entry through run_merge_pair. Returns status dict."""
    local_d  = entry.get("local") or {}
    remote_d = entry.get("remote") or {}
    skill_id = entry.get("skill_id") or local_d.get("skill_id") or "?"
    try:
        skill_a = Skill.from_dict(local_d)
        skill_b = Skill.from_dict(remote_d)
    except Exception as exc:
        return {"skill_id": skill_id, "status": "invalid_entry", "reason": str(exc)}

    try:
        result = await run_merge_pair(
            skill_a=skill_a, skill_b=skill_b,
            log_dir=log_dir, combat_system_prompt=combat_system_prompt,
        )
    except Exception as exc:
        logger.warning("run_merge_pair failed for %s: %s", skill_id, exc)
        return {"skill_id": skill_id, "status": "error", "reason": str(exc)}

    if result.outcome == "merged" and result.merged_skill is not None:
        library.add(result.merged_skill)
        library.save(paths.skills_file())
        return {
            "skill_id": skill_id, "status": "merged",
            "merged_id": result.merged_skill.skill_id,
            "merged_name": result.merged_skill.name,
        }
    return {
        "skill_id": skill_id, "status": result.outcome,
        "reason": getattr(result, "reason", ""),
    }


# ───────── guides queue handler ─────────────────────────────────────

_GUIDE_SECTION_TO_CLASS: dict[str, type] = {
    "combat_guides": CombatGuide,
    "route_guides":  RouteGuide,
    "deck_guides":   DeckGuide,
    "event_guides":  EventGuide,
}


def _guide_preference_tuple(guide: Any) -> tuple:
    """Higher-is-better ranking for conflict resolution.

    (version, evidence_count, confidence, updated_at) — the same ordering
    GuideStore._prefer_combat_guide uses, generalized across the four guide
    types. ``evidence_count`` reads ``episode_count`` for combat/event
    guides and ``memory_count`` for route/deck guides (schema split).
    """
    evidence = (
        getattr(guide, "episode_count", None)
        or getattr(guide, "memory_count", 0)
        or 0
    )
    return (
        int(getattr(guide, "version", 0) or 0),
        int(evidence),
        float(getattr(guide, "confidence", 0.0) or 0.0),
        float(getattr(guide, "updated_at", 0.0) or 0.0),
    )


def _set_guide(store: GuideStore, section: str, guide: Any) -> None:
    """Dispatch ``guide`` to the right store setter. Combat guides self-pick
    via the store's own preference logic; others overwrite — callers must
    decide before invoking this for non-combat sections."""
    if section == "combat_guides":
        store.set_combat_guide(guide)
    elif section == "route_guides":
        store.set_route_guide(guide)
    elif section == "deck_guides":
        store.set_deck_guide(guide)
    elif section == "event_guides":
        store.set_event_guide(guide)
    else:
        raise ValueError(f"Unknown guide section: {section}")


def _process_guide_entry(entry: dict[str, Any], *, store: GuideStore) -> dict[str, Any]:
    """Resolve a guide conflict by preferring the side with stronger evidence.

    At conflict time the remote was quarantined, so the store already holds
    the local guide. If the remote's preference tuple outranks local, swap
    it in; otherwise keep local and just retire the entry. No LLM call —
    the next consolidation pass rebuilds the guide from accumulated episodes
    anyway, so the sibling data converges naturally.
    """
    section  = entry.get("section", "")
    guide_id = entry.get("guide_id", "?")
    local_d  = entry.get("local") or {}
    remote_d = entry.get("remote") or {}
    cls      = _GUIDE_SECTION_TO_CLASS.get(section)
    if cls is None:
        return {"guide_id": guide_id, "section": section,
                "status": "invalid_entry", "reason": "unknown_section"}

    try:
        local_g  = cls.from_dict(local_d)
        remote_g = cls.from_dict(remote_d)
    except Exception as exc:
        return {"guide_id": guide_id, "section": section,
                "status": "invalid_entry", "reason": str(exc)}

    local_rank  = _guide_preference_tuple(local_g)
    remote_rank = _guide_preference_tuple(remote_g)

    if remote_rank > local_rank:
        try:
            _set_guide(store, section, remote_g)
        except Exception as exc:
            return {"guide_id": guide_id, "section": section,
                    "status": "error", "reason": str(exc)}
        return {"guide_id": guide_id, "section": section,
                "status": "replaced", "winner": "remote",
                "local_rank": local_rank, "remote_rank": remote_rank}

    return {"guide_id": guide_id, "section": section,
            "status": "kept_local", "winner": "local",
            "local_rank": local_rank, "remote_rank": remote_rank}


async def drain(
    *, cap: int | None = DEFAULT_CAP, log_dir: Path | None = None,
) -> dict[str, Any]:
    """Process up to ``cap`` skills entries. ``cap=None`` means no limit.

    Returns ``{"processed": N, "outcomes": [...], "remaining": M}``.
    """
    queue_path = paths.merge_queue_file()
    entries = _read_queue(queue_path)
    if not entries:
        return {"processed": 0, "outcomes": [], "remaining": 0}

    skill_entries = [e for e in entries if e.get("file") == "skills/skills.json"]
    guide_entries = [e for e in entries if e.get("file") == "memory/v2/guides.json"]
    other_entries = [
        e for e in entries
        if e.get("file") not in ("skills/skills.json", "memory/v2/guides.json")
    ]

    if other_entries:
        logger.info(
            "merge_queue drain: %d entries deferred (no handler registered)",
            len(other_entries),
        )

    from src.brain.prompts.system import SYSTEM_COMBAT

    library = SkillLibrary.load(paths.skills_file())
    guide_store = GuideStore.load(paths.guides_file())
    if log_dir is None:
        log_dir = paths.evolution_dir()
    log_dir.mkdir(parents=True, exist_ok=True)

    processed = 0
    outcomes: list[dict[str, Any]] = []
    kept: list[dict[str, Any]] = list(other_entries)

    # Skills first — cap applies to this bucket since each one can cost an
    # LLM call. Guides are cap-exempt: preference-only, no LLM.
    for entry in skill_entries:
        if cap is not None and processed >= cap:
            kept.append(entry)
            continue
        outcome = await _process_skill_entry(
            entry, library=library, log_dir=log_dir,
            combat_system_prompt=SYSTEM_COMBAT,
        )
        outcomes.append(outcome)
        processed += 1
        if outcome["status"] not in ("merged", "invalid_entry"):
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            entry["last_attempt"] = time.time()
            entry["last_outcome"] = outcome["status"]
            if entry["retry_count"] < 3:
                kept.append(entry)
            else:
                logger.warning(
                    "Dropping skill merge entry after 3 attempts: %s (last=%s)",
                    outcome.get("skill_id"), outcome["status"],
                )

    guides_dirty = False
    for entry in guide_entries:
        outcome = _process_guide_entry(entry, store=guide_store)
        outcomes.append(outcome)
        if outcome["status"] == "replaced":
            guides_dirty = True
        if outcome["status"] == "error":
            entry["retry_count"] = entry.get("retry_count", 0) + 1
            entry["last_attempt"] = time.time()
            entry["last_outcome"] = outcome["status"]
            if entry["retry_count"] < 3:
                kept.append(entry)

    if guides_dirty:
        guide_store.save(paths.guides_file())

    _write_queue(queue_path, kept)
    logger.info(
        "merge_queue drain: skills=%d, guides=%d, kept=%d (cap=%s)",
        len(skill_entries), len(guide_entries), len(kept), cap,
    )
    return {"processed": processed + len(guide_entries),
            "skills_processed": processed,
            "guides_processed": len(guide_entries),
            "outcomes": outcomes, "remaining": len(kept)}


def drain_sync(*, cap: int | None = DEFAULT_CAP, log_dir: Path | None = None) -> dict[str, Any]:
    """Synchronous wrapper for non-async callers."""
    return asyncio.run(drain(cap=cap, log_dir=log_dir))
