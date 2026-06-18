"""Migrate existing card_builds.jsonl: reprocess builds with LLM analysis.

Phase 1 (--evidence-only): Reconstruct evidence from stored fields, write back.
Phase 2 (default): Also call LLM to produce build_tags, build_summary, etc.

Usage:
    python -m scripts.migrate_build_tags                # Full LLM migration
    python -m scripts.migrate_build_tags --evidence-only # Evidence only (no LLM)
    python -m scripts.migrate_build_tags --dry-run       # Preview changes
    python -m scripts.migrate_build_tags --limit 5       # Process only N entries
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import config  # noqa: F401
from src.storage import paths

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger(__name__)

CARD_BUILDS_PATH = paths.card_builds_file()


def _reconstruct_evidence(data: dict) -> dict:
    """Reconstruct build_evidence from stored CardBuildMemory fields.

    This is a best-effort reconstruction from persisted data — it won't
    have per-card damage/block attribution (needs live round trackers),
    but it preserves what's available.
    """
    play_counts_raw = data.get("card_play_counts", [])
    play_counts = [(p[0], int(p[1])) for p in play_counts_raw if len(p) >= 2]

    final_deck = data.get("final_deck", [])
    starting_deck = data.get("starting_deck", [])
    deck_events = data.get("deck_events", [])
    victory = data.get("victory", False)
    final_floor = data.get("final_floor", 0)
    fitness = data.get("fitness", 0.0)
    character = data.get("character", "")

    # Reconstruct deck event summary
    deck_event_summary = []
    for e in deck_events:
        if isinstance(e, dict):
            deck_event_summary.append({
                "floor": e.get("floor", 0),
                "type": e.get("event_type", ""),
                "card": e.get("card_name", ""),
                "source": e.get("source", ""),
            })

    return {
        "character": character,
        "victory": victory,
        "final_floor": final_floor,
        "fitness": round(fitness, 1),
        "deck_size": len(final_deck),
        "final_deck": final_deck,
        "starting_deck": starting_deck,
        # Explicitly mark quality: historical data lacks action-level combat deltas
        "evidence_quality": "deck_snapshot_only",
        "top_played": play_counts[:10],
        # NOT available from persisted data — left empty, not fabricated
        "top_damage": [],
        "top_block": [],
        "top_energy_gain": [],
        "top_exhaust": [],
        "top_powers_applied": [],
        "top_enemy_debuffs": [],
        "deck_events": deck_event_summary,
        "combat_summaries": [],
        "combats_won": 0,
        "combats_total": 0,
    }


async def _analyze_one(evidence: dict) -> dict:
    """Call LLM to analyze one build."""
    from src.memory.card_build_extractor import analyze_build_with_llm
    return await analyze_build_with_llm(evidence)


async def migrate(
    dry_run: bool = False,
    evidence_only: bool = False,
    limit: int = 0,
) -> None:
    """Reprocess card build memories with evidence + optional LLM analysis."""
    if not CARD_BUILDS_PATH.exists():
        logger.warning("No card_builds.jsonl found at %s", CARD_BUILDS_PATH)
        return

    lines = CARD_BUILDS_PATH.read_text(encoding="utf-8").strip().splitlines()
    logger.info("Found %d card build entries", len(lines))

    if limit:
        lines = lines[:limit]
        logger.info("Processing first %d entries only", limit)

    updated: list[str] = []
    changed = 0
    llm_calls = 0

    for i, line in enumerate(lines):
        try:
            data = json.loads(line)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed line %d", i + 1)
            updated.append(line)
            continue

        # Phase 1: Evidence reconstruction
        evidence = _reconstruct_evidence(data)
        data["build_evidence"] = evidence

        # Phase 2: LLM analysis (unless evidence-only)
        if not evidence_only:
            # Skip if already has LLM-generated tags
            existing_summary = data.get("build_summary", "")
            if existing_summary and data.get("build_tags"):
                logger.info("  [%d] Already analyzed, skipping", i + 1)
                updated.append(json.dumps(data, ensure_ascii=False))
                continue

            run_id = data.get("run_id", "?")[:8]
            logger.info("  [%d] Analyzing run %s ...", i + 1, run_id)

            try:
                analysis = await _analyze_one(evidence)
                llm_calls += 1

                data["build_tags"] = list(analysis.get("build_tags", []))
                data["build_summary"] = analysis.get("build_summary", "")
                data["primary_plan"] = analysis.get("primary_plan", "")
                data["damage_engine"] = analysis.get("damage_engine", "")
                data["defense_engine"] = analysis.get("defense_engine", "")
                data["cycle_engine"] = analysis.get("cycle_engine", "")
                data["energy_engine"] = analysis.get("energy_engine", "")
                data["weak_points"] = analysis.get("weak_points", "")

                # Reduce confidence for partial evidence
                raw_conf = analysis.get("confidence", 0.5)
                if evidence.get("evidence_quality") == "deck_snapshot_only":
                    raw_conf = min(raw_conf, 0.4)  # cap at 0.4 for partial
                data["analysis_confidence"] = raw_conf

                # Update legacy archetype from primary_plan
                primary_plan = data["primary_plan"]
                if primary_plan:
                    data["archetype"] = primary_plan

                changed += 1
                logger.info(
                    "  [%d] -> plan=%s, tags=%s, conf=%.1f (%s)",
                    i + 1,
                    primary_plan,
                    data["build_tags"],
                    raw_conf,
                    evidence.get("evidence_quality", "?"),
                )

                # Rate limit: 1 call per second
                if llm_calls % 5 == 0:
                    logger.info("  ... %d/%d done, pausing ...", i + 1, len(lines))
                    await asyncio.sleep(2)

            except Exception as exc:
                logger.warning("  [%d] LLM analysis failed: %s", i + 1, exc)
        else:
            changed += 1

        updated.append(json.dumps(data, ensure_ascii=False))

    logger.info(
        "Migration complete: %d/%d changed, %d LLM calls",
        changed, len(lines), llm_calls,
    )

    if not dry_run:
        # Backup original
        backup = CARD_BUILDS_PATH.with_suffix(".jsonl.bak")
        if not backup.exists():
            import shutil
            shutil.copy2(CARD_BUILDS_PATH, backup)
            logger.info("Backed up to %s", backup)

        CARD_BUILDS_PATH.write_text(
            "\n".join(updated) + "\n",
            encoding="utf-8",
        )
        logger.info("Written updated card_builds.jsonl")
    else:
        logger.info("Dry run — no changes written")


if __name__ == "__main__":
    dry = "--dry-run" in sys.argv
    evidence_only = "--evidence-only" in sys.argv
    limit_val = 0
    for i, arg in enumerate(sys.argv):
        if arg == "--limit" and i + 1 < len(sys.argv):
            limit_val = int(sys.argv[i + 1])

    asyncio.run(migrate(dry_run=dry, evidence_only=evidence_only, limit=limit_val))
