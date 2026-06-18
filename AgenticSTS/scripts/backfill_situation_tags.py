#!/usr/bin/env python3
"""Backfill SituationTag onto existing combat_episodes.jsonl.

Computes what it can from existing round data:
  - intent_class: from enemy_intents strings (always available)
  - threat_level: retrospective from damage_taken vs hp_start
    (not the same as predictive threat from incoming damage, but a
    usable proxy for "how dangerous was this round")
  - outcome_quality: from damage_taken thresholds
  - next_round_window: from the following round's intent_class
  - hand_capabilities: None (no hand_at_start in historical data)
  - deck_stage: empty (would need deck composition data)

Rounds that already have a situation_tag are skipped (idempotent).

Usage:
    python -m scripts.backfill_situation_tags              # apply
    python -m scripts.backfill_situation_tags --dry-run    # preview only
    python -m scripts.backfill_situation_tags --sample 5   # show 5 samples
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.situation import SituationTag, classify_intent

# ── Retrospective threat classification ──────────────────────

def _classify_threat_retrospective(damage_taken: int, hp_start: int) -> str:
    """Classify threat from actual damage taken (retrospective).

    This is NOT the same as predictive classify_threat() which uses
    incoming intent damage. For historical data without intent damage
    values, actual damage_taken is the best available signal.
    """
    if hp_start <= 0:
        return "medium"  # can't compute ratio
    ratio = damage_taken / hp_start
    if ratio >= 0.5:
        return "lethal"
    if damage_taken >= 15:
        return "high"
    if damage_taken >= 8:
        return "medium"
    return "low"


def _classify_outcome(damage_taken: int) -> str:
    """Classify round outcome by damage taken."""
    if damage_taken == 0:
        return "clean"
    if damage_taken < 8:
        return "acceptable"
    if damage_taken < 15:
        return "bad"
    return "disaster"


# ── Intent parsing for historical format ─────────────────────

# Historical intents have mixed formats:
#   "Kin Follower"                          → just enemy name, no intent info
#   "The Insatiable: LIQUIFY_GROUND_MOVE"   → enemy: raw move name
#   "Nibbit: Attack(12)"                    → structured (newer runs)
#   "Attack 12"                             → simple attack

_ATTACK_IN_INTENT = re.compile(r"\battack\b", re.IGNORECASE)


def _extract_damage_from_intent(intent: str) -> int:
    """Try to extract attack damage from an intent string.

    Returns 0 if no attack damage found.
    """
    # "Attack(12)" or "Attack(6x3=18)"
    m = re.search(r"Attack\((\d+)", intent)
    if m:
        return int(m.group(1))
    # "Attack 12"
    m = re.search(r"Attack\s+(\d+)", intent, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return 0


def _estimate_incoming_from_intents(intents: list[str]) -> int | None:
    """Estimate total incoming damage from intent strings.

    Returns None if no attack damage can be extracted (fall back to
    retrospective threat classification).
    """
    total = 0
    found_any = False
    for intent in intents:
        dmg = _extract_damage_from_intent(intent)
        if dmg > 0:
            total += dmg
            found_any = True
    return total if found_any else None


# ── Backfill logic ───────────────────────────────────────────

def backfill_episode(ep_dict: dict) -> tuple[dict, int, int]:
    """Add situation_tag to each round in an episode dict.

    Returns (updated_dict, tagged_count, skipped_count).
    """
    rounds = ep_dict.get("rounds", [])
    tagged = 0
    skipped = 0

    for i, rnd in enumerate(rounds):
        if rnd.get("situation_tag"):
            skipped += 1
            continue

        intents = rnd.get("enemy_intents", [])
        damage_taken = rnd.get("damage_taken", 0)
        hp_start = rnd.get("hp_start", 0)

        # Intent classification (always available)
        intent_class = classify_intent(intents)

        # Threat level: try predictive (from intent damage), fall back to retrospective
        estimated_incoming = _estimate_incoming_from_intents(intents)
        if estimated_incoming is not None and hp_start > 0:
            # Predictive: use estimated incoming vs hp_start (no block info)
            from src.memory.situation import classify_threat
            threat_level = classify_threat(estimated_incoming, hp_start, 0)
        else:
            # Retrospective: use actual damage_taken
            threat_level = _classify_threat_retrospective(damage_taken, hp_start)

        # Outcome quality
        outcome_quality = _classify_outcome(damage_taken)

        # Next round window: peek at next round's intent
        next_round_window = ""
        if i + 1 < len(rounds):
            next_intents = rounds[i + 1].get("enemy_intents", [])
            next_ic = classify_intent(next_intents)
            if next_ic == "buff":
                next_round_window = "setup"
            elif next_ic == "debuff":
                next_round_window = "setup"  # debuff rounds are also low-pressure windows
            elif next_ic == "attack":
                next_round_window = "burst"

        tag = SituationTag(
            threat_level=threat_level,
            intent_class=intent_class,
            hand_capabilities=None,  # no hand data in historical episodes
            deck_stage="",           # no deck composition data
            damage_taken=damage_taken,
            outcome_quality=outcome_quality,
            next_round_window=next_round_window,
            tag_source="backfill",
        )

        rnd["situation_tag"] = tag.to_dict()
        tagged += 1

    return ep_dict, tagged, skipped


def main() -> None:
    dry_run = "--dry-run" in sys.argv
    sample_count = 0
    for i, arg in enumerate(sys.argv):
        if arg == "--sample" and i + 1 < len(sys.argv):
            sample_count = int(sys.argv[i + 1])

    from src.storage import paths
    path = paths.combat_episodes_file()
    if not path.exists():
        print(f"File not found: {path}")
        sys.exit(1)

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    lines = [line for line in lines if line.strip()]
    print(f"Processing {len(lines)} episodes...")

    updated_lines: list[str] = []
    total_tagged = 0
    total_skipped = 0
    total_rounds = 0
    intent_class_counts: dict[str, int] = {}
    threat_level_counts: dict[str, int] = {}
    samples_shown = 0

    for line in lines:
        ep_dict = json.loads(line)
        total_rounds += len(ep_dict.get("rounds", []))

        updated, tagged, skipped = backfill_episode(ep_dict)
        total_tagged += tagged
        total_skipped += skipped

        # Collect stats
        for rnd in updated.get("rounds", []):
            st = rnd.get("situation_tag", {})
            if st:
                ic = st.get("intent_class", "unknown")
                tl = st.get("threat_level", "medium")
                intent_class_counts[ic] = intent_class_counts.get(ic, 0) + 1
                threat_level_counts[tl] = threat_level_counts.get(tl, 0) + 1

        # Show samples
        if sample_count > 0 and samples_shown < sample_count and tagged > 0:
            enemy = updated.get("enemy_key", "?")
            for rnd in updated.get("rounds", [])[:2]:
                st = rnd.get("situation_tag")
                if st:
                    print(f"\n  Sample — {enemy} R{rnd.get('round_num', '?')}:")
                    print(f"    intents: {rnd.get('enemy_intents', [])[:3]}")
                    print(f"    tag: threat={st.get('threat_level')}, "
                          f"intent={st.get('intent_class')}, "
                          f"outcome={st.get('outcome_quality')}, "
                          f"next_window={st.get('next_round_window', '')}")
                    samples_shown += 1
                    if samples_shown >= sample_count:
                        break

        updated_lines.append(json.dumps(updated, ensure_ascii=False))

    # Summary
    print("\nResults:")
    print(f"  Total rounds:  {total_rounds}")
    print(f"  Tagged:        {total_tagged}")
    print(f"  Skipped:       {total_skipped} (already had tags)")
    print("\nIntent class distribution:")
    for k, v in sorted(intent_class_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} ({v * 100 // max(total_tagged, 1)}%)")
    print("\nThreat level distribution:")
    for k, v in sorted(threat_level_counts.items(), key=lambda x: -x[1]):
        print(f"  {k}: {v} ({v * 100 // max(total_tagged, 1)}%)")

    if dry_run:
        print(f"\n[DRY RUN] No changes written to {path}")
    else:
        # Write atomically: write to temp then rename
        tmp_path = path.with_suffix(".jsonl.tmp")
        tmp_path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        tmp_path.replace(path)
        print(f"\nWritten to {path}")


if __name__ == "__main__":
    main()
