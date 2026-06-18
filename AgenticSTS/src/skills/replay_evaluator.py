"""Skill eval data structures and confidence computation.

The eval flow itself is orchestrated by AgentLoop in loop.py.
This module provides ReplayResult, confidence delta computation,
and eval schedule building.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    skill_set_id: str
    skills_used: tuple[str, ...]
    hp_lost: int
    rounds: int
    potions_used: int
    won: bool


def compute_confidence_deltas(
    results: list[ReplayResult],
) -> dict[str, float]:
    """Compare replay results, return per-skill confidence deltas.

    Skills ONLY in the best set get positive signal.
    Skills ONLY in the worst set get negative signal.
    Skills in both (shared) are unaffected.
    """
    if len(results) < 2:
        return {}
    scored = sorted(results, key=lambda r: (not r.won, r.hp_lost, r.potions_used))
    best, worst = scored[0], scored[-1]
    if best.hp_lost >= worst.hp_lost:
        return {}

    magnitude = (worst.hp_lost - best.hp_lost) / max(worst.hp_lost, 1)
    deltas: dict[str, float] = {}
    best_set = set(best.skills_used)
    worst_set = set(worst.skills_used)

    for sid in best.skills_used:
        if sid not in worst_set:
            deltas[sid] = magnitude * 0.1

    for sid in worst.skills_used:
        if sid not in best_set:
            deltas[sid] = -magnitude * 0.1

    return deltas


def build_eval_schedule(
    *,
    original_skill_ids: list[str],
    all_skills_pool: list[tuple[str, int]],  # (skill_id, usage_count)
    max_replays: int = 2,
) -> list[list[str]]:
    """Build alternative skill sets prioritizing untested skills.

    Args:
        original_skill_ids: skills injected during the original combat
        all_skills_pool: candidate skills with usage counts (pre-filtered by trigger)
        max_replays: max number of alternative sets to build

    Returns:
        List of skill ID lists, each an alternative set to test.
    """
    original_set = set(original_skill_ids)
    # Prioritize untested (usage_count == 0), then low-usage
    candidates = sorted(
        [(sid, uc) for sid, uc in all_skills_pool if sid not in original_set],
        key=lambda x: x[1],  # lowest usage first
    )
    pool = [sid for sid, _uc in candidates]

    schedule: list[list[str]] = []
    for _ in range(max_replays):
        if not pool:
            break
        swap_count = min(3, len(pool), len(original_skill_ids))
        if swap_count == 0:
            break
        swap_indices = random.sample(range(len(original_skill_ids)), swap_count)
        kept = [s for i, s in enumerate(original_skill_ids) if i not in swap_indices]
        replacements = pool[:swap_count]
        pool = pool[swap_count:]  # consume — don't re-test same skills
        schedule.append(kept + replacements)

    return schedule


def remaining_plan_kills_boss(
    hand: list,       # cards in current hand (game engine values)
    enemies: list,    # alive enemies
    remaining: list,  # remaining plan actions
) -> bool:
    """Check if remaining plan actions can kill all enemies.

    Uses card damage values from the game engine (already includes
    Strength, Weak, etc.). target_previews include Vulnerable.
    """
    if not enemies:
        return False

    # Build hand lookup by name (case-insensitive, handle duplicates)
    hand_by_name: dict[str, list] = {}
    for c in hand:
        key = c.name.lower().rstrip("+")
        hand_by_name.setdefault(key, []).append(c)

    total_damage = 0
    used_cards: dict[str, int] = {}  # track which copies used

    for action in remaining:
        if getattr(action, "is_potion", False):
            continue
        card_name = getattr(action, "card_name", "")
        key = card_name.lower().rstrip("+")
        copies = hand_by_name.get(key, [])
        idx = used_cards.get(key, 0)
        if idx >= len(copies):
            continue
        card = copies[idx]
        used_cards[key] = idx + 1

        if card.damage is None:
            continue

        # Check target_previews for per-target damage (Vulnerable etc.)
        target_idx = getattr(action, "target_index", None)
        if target_idx is not None and card.target_previews:
            for tp in card.target_previews:
                if tp.target_index == target_idx:
                    total_damage += tp.total_damage or tp.damage or card.total_damage or 0
                    break
            else:
                total_damage += card.total_damage or card.damage or 0
        else:
            total_damage += card.total_damage or card.damage or 0

    boss_effective_hp = sum(
        getattr(e, "current_hp", getattr(e, "hp", 0))
        + (getattr(e, "block", 0) or 0)
        for e in enemies
        if getattr(e, "is_alive", True)
    )
    return total_damage >= boss_effective_hp
