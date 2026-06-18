#!/usr/bin/env python3
"""One-time batch job: enrich zero-usage skills' triggers with specificity.

Usage: python -m scripts.enrich_skill_triggers [--dry-run]

Loads skills.json, finds skills with usage_count==0, sends each skill's
content to Sonnet to infer: enemy_names, min_act/max_act, tags.
Updates trigger fields and saves back.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.storage import paths  # noqa: E402

logger = logging.getLogger(__name__)

TAGS_VOCABULARY = [
    "low_hp", "multi_enemy", "poison_build", "shiv_build", "boss_prep",
    "scaling", "aoe", "block_heavy", "energy_tight", "deck_thin",
    "strength_scaling", "draw_engine", "retain", "exhaust",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true", help="Print changes without saving")
    parser.add_argument("--skills-path", default=None,
                        help="Path to skills.json (default: resolved via src.storage.paths)")
    args = parser.parse_args()

    skills_path = Path(args.skills_path) if args.skills_path else paths.skills_file()
    if not skills_path.exists():
        logger.error("Skills file not found: %s", skills_path)
        return

    with open(skills_path, encoding="utf-8") as f:
        skills_data = json.load(f)

    zero_usage = [s for s in skills_data if s.get("usage_count", 0) == 0]
    logger.info("Found %d zero-usage skills out of %d total", len(zero_usage), len(skills_data))

    # TODO: For each skill, call Sonnet to infer trigger specifics from content
    # For now, this is a skeleton -- the LLM enrichment will be added when
    # the Anthropic API integration is wired.

    if not args.dry_run:
        with open(skills_path, "w", encoding="utf-8") as f:
            json.dump(skills_data, f, indent=2, ensure_ascii=False)
        logger.info("Saved updated skills to %s", skills_path)
    else:
        logger.info("Dry run -- no changes saved")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
