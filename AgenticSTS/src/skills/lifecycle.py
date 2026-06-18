"""Post-write lifecycle for mistake-driven skills (spec §6).

Replaces the coarse run-level win/loss signal used by sweep_retirements
with per-combat baseline outcome attribution. Each CombatEpisode's
loss_ratio is compared to that combat's baseline; the resulting outcome
tag (improved/unchanged/worse) applies a multiplier to every skill that
was actually injected into that combat's prompts.
"""
from __future__ import annotations

import logging

from src.skills.mistake_discovery import DELTA_BY_TYPE

logger = logging.getLogger(__name__)


def classify_combat_outcome(
    *,
    actual: float,
    baseline: float,
    combat_type: str,
) -> str:
    """Classify per-combat outcome relative to baseline (§6.1).

    Returns one of:
    - 'improved' : actual <= baseline - delta  (clean beat)
    - 'unchanged': within +/- delta             (no meaningful signal)
    - 'worse'    : actual >= baseline + delta   (regression)

    Delta comes from DELTA_BY_TYPE per combat_type (monster 0.10,
    elite 0.15, boss 0.20 — same table used by is_mistake_episode
    in spec §2.1).

    Uses a small epsilon (1e-9) for floating-point comparison safety.
    """
    delta = DELTA_BY_TYPE.get(combat_type, 0.10)
    epsilon = 1e-9

    if actual <= baseline - delta + epsilon:
        return "improved"
    if actual >= baseline + delta - epsilon:
        return "worse"
    return "unchanged"


# Multipliers applied to Skill.confidence per outcome (§6.1).
# Over runs this compounds: a skill with 10 "improved" attributions
# at 1.10 each ends up at 1.10^10 ~= 2.59, then clamped to 1.0.
# A skill with 10 "worse" at 0.85 each ends at 0.85^10 ~= 0.20.
CONFIDENCE_MULT: dict[str, float] = {
    "improved": 1.10,
    "unchanged": 0.98,
    "worse": 0.85,
}


# ---------------------------------------------------------------------------
# §6 — update_skill_usage_from_run
# ---------------------------------------------------------------------------

import json
from pathlib import Path
from typing import TYPE_CHECKING

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
from src.skills.mistake_discovery import baseline_a, baseline_b, loss_ratio

if TYPE_CHECKING:
    from src.skills.library import SkillLibrary


def update_skill_usage_from_run(
    *,
    this_run_episodes: list[CombatEpisode],
    skill_library: "SkillLibrary",
    combat_store: CombatMemoryStore,
    usage_log_path: Path,
) -> None:
    """Attribute per-combat outcomes and update skill confidence (§6).

    For every episode in this run that has non-empty retrieved_skill_ids:
      1. Compute baseline (A per-enemy median preferred, B pool mean fallback)
      2. Classify outcome (improved/unchanged/worse) via classify_combat_outcome
      3. Multiply each injected skill's confidence by CONFIDENCE_MULT[outcome]
      4. Append an audit record to usage_log_path (JSONL)

    Writes one line per (episode, skill) pair. Safe to call with empty
    this_run_episodes (no-op).
    """
    usage_log_path.parent.mkdir(parents=True, exist_ok=True)
    log_lines: list[str] = []

    # --- Track per-run best outcome per skill across this run's combats.
    # Precedence: 'improved' > 'unchanged' > 'worse'. Only skills that actually
    # saw baseline-backed attribution in at least one combat this run are
    # considered — skills whose only injections all fell through the
    # "no baseline" guard are NOT counted as "unimproved this run".
    _OUTCOME_RANK = {"worse": 0, "unchanged": 1, "improved": 2}
    best_outcome_per_skill: dict[str, str] = {}

    for ep in this_run_episodes:
        if not ep.retrieved_skill_ids:
            continue

        actual = loss_ratio(ep)
        # Baseline A: per-enemy history, excluding current run
        history = [
            e for e in combat_store.get_by_enemy(ep.enemy_key)
            if e.run_id != ep.run_id
        ]
        ba = baseline_a(history)

        # Baseline B: act × combat_type × character recent pool, excluding current run
        pool = combat_store.recent_by_act_type(
            act=ep.act,
            combat_type=ep.combat_type,
            character=ep.character,
            limit=10,
            exclude_run_id=ep.run_id,
        )
        bb = baseline_b(pool)

        # Prefer A (enemy-specific is more discriminative); fall back to B
        baseline = ba if ba is not None else bb
        if baseline is None:
            logger.debug(
                "update_skill_usage: no baseline for episode %s (enemy=%s)",
                ep.episode_id, ep.enemy_key,
            )
            continue  # insufficient prior data; skip attribution

        outcome = classify_combat_outcome(
            actual=actual, baseline=baseline, combat_type=ep.combat_type,
        )
        mult = CONFIDENCE_MULT[outcome]

        # Dedup skill_ids within the same combat — multiple injections in the
        # same fight should count once per attribution
        unique_skill_ids = set(ep.retrieved_skill_ids)
        for skill_id in unique_skill_ids:
            sk = _lookup_skill(skill_library, skill_id)
            if sk is None:
                continue
            new_conf = max(0.0, min(1.0, sk.confidence * mult))
            _update_skill_confidence(skill_library, skill_id, sk, new_conf)

            # Track best outcome seen for this skill across the run
            prev = best_outcome_per_skill.get(skill_id)
            if prev is None or _OUTCOME_RANK[outcome] > _OUTCOME_RANK[prev]:
                best_outcome_per_skill[skill_id] = outcome

            log_lines.append(json.dumps({
                "skill_id": skill_id,
                "run_id": ep.run_id,
                "episode_id": ep.episode_id,
                "enemy": ep.enemy_key,
                "combat_type": ep.combat_type,
                "actual_loss_ratio": round(actual, 4),
                "baseline": round(baseline, 4),
                "baseline_source": "A" if ba is not None else "B",
                "outcome": outcome,
                "confidence_before": round(sk.confidence, 4),
                "confidence_after": round(new_conf, 4),
            }))

    # --- Apply per-run unimproved-run counter updates (§6.2).
    # For each skill injected AND attributed at least once this run:
    #   - best == 'improved'  -> reset counter to 0
    #   - best in {'unchanged','worse'} -> increment by 1
    for skill_id, best in best_outcome_per_skill.items():
        sk = _lookup_skill(skill_library, skill_id)
        if sk is None:
            continue
        if best == "improved":
            new_counter = 0
        else:
            new_counter = sk.consecutive_unimproved_runs + 1
        if new_counter != sk.consecutive_unimproved_runs:
            _update_skill_field(
                skill_library, skill_id, sk,
                consecutive_unimproved_runs=new_counter,
            )

    if log_lines:
        with usage_log_path.open("a", encoding="utf-8") as f:
            for line in log_lines:
                f.write(line + "\n")


def apply_retirement_policy(skill_library) -> list[str]:
    """Apply spec §6.2 retirement rules.

    Rules:
      - ``confidence < 0.30`` AND ``usage_count >= 10`` -> deactivated
      - ``consecutive_unimproved_runs >= 3`` -> deactivated
      - Seed skills (``source == 'seed'``) never deactivate; their
        confidence is floored at 0.40 instead.

    Returns list of skill_ids that were newly deactivated this call
    (for logging).
    """
    from dataclasses import replace

    newly_deactivated: list[str] = []
    internal = getattr(skill_library, "_skills", None)
    if not isinstance(internal, dict):
        return newly_deactivated

    for skill_id, sk in list(internal.items()):
        if sk.status == "deactivated":
            continue

        if sk.source == "seed":
            # Seed skills never deactivate. Floor confidence at 0.40.
            if sk.confidence < 0.40:
                internal[skill_id] = replace(sk, confidence=0.40)
            continue

        should_retire = False
        reason = ""
        if sk.confidence < 0.30 and sk.usage_count >= 10:
            should_retire = True
            reason = "low_confidence_with_sufficient_usage"
        elif sk.consecutive_unimproved_runs >= 3:
            should_retire = True
            reason = "three_unimproved_runs"

        if should_retire:
            updated = replace(sk, status="deactivated", active=False)
            internal[skill_id] = updated
            newly_deactivated.append(skill_id)
            logger.info(
                "retirement: deactivated skill %r (reason=%s, conf=%.2f, usage=%d, unimproved_runs=%d)",
                sk.name, reason, sk.confidence, sk.usage_count,
                sk.consecutive_unimproved_runs,
            )

    return newly_deactivated


def _lookup_skill(skill_library, skill_id):
    """Look up a Skill by id across SkillLibrary API variations."""
    if hasattr(skill_library, "get_skill"):
        return skill_library.get_skill(skill_id)
    if hasattr(skill_library, "get"):
        found = skill_library.get(skill_id)
        if found is not None:
            return found
    internal = getattr(skill_library, "_skills", None)
    if isinstance(internal, dict):
        return internal.get(skill_id)
    # Fallback: linear scan of all_skills
    for s in getattr(skill_library, "all_skills", ()):
        if getattr(s, "skill_id", None) == skill_id:
            return s
    return None


def _update_skill_confidence(skill_library, skill_id, current_skill, new_conf: float) -> None:
    """Replace a Skill's confidence (+ bump usage_count) preserving frozen-ness."""
    usage = getattr(current_skill, "usage_count", 0) + 1

    # Try the immutable-update helpers first (SkillLibrary conventions vary)
    if hasattr(current_skill, "with_update"):
        updated = current_skill.with_update(confidence=new_conf, usage_count=usage)
    else:
        from dataclasses import replace
        updated = replace(current_skill, confidence=new_conf, usage_count=usage)

    # Write back through the library's private map if available
    internal = getattr(skill_library, "_skills", None)
    if isinstance(internal, dict):
        internal[skill_id] = updated
    elif hasattr(skill_library, "update"):
        skill_library.update(updated)
    elif hasattr(skill_library, "add"):
        skill_library.add(updated)


def _update_skill_field(skill_library, skill_id, current_skill, **kwargs) -> None:
    """Replace arbitrary Skill fields preserving frozen-ness. Does NOT bump usage_count."""
    if hasattr(current_skill, "with_update"):
        updated = current_skill.with_update(**kwargs)
    else:
        from dataclasses import replace
        updated = replace(current_skill, **kwargs)

    internal = getattr(skill_library, "_skills", None)
    if isinstance(internal, dict):
        internal[skill_id] = updated
    elif hasattr(skill_library, "update"):
        skill_library.update(updated)
    elif hasattr(skill_library, "add"):
        skill_library.add(updated)
