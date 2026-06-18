"""Semantic deduplication and common knowledge detection for skill candidates.

Used during skill discovery to filter out:
1. Duplicates of existing skills (content_overlap + trigger_overlap)
2. Restated system-prompt concepts (common_knowledge_score)
3. Restated seed skills (is_seed_restatement)
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.skills.models import Skill, SkillTrigger

# ── Stopword set ─────────────────────────────────────────────────────────────

_STOPWORDS: frozenset[str] = frozenset({
    "the", "a", "an", "is", "are", "when", "if", "then", "and", "or",
    "to", "in", "on", "at", "for", "with", "this", "that", "it", "of",
    "be", "do", "not", "no", "but", "by", "from", "as", "so",
})

# ── System-prompt concept dictionary ─────────────────────────────────────────

SYSTEM_PROMPT_CONCEPTS: dict[str, set[str]] = {
    "block_when_high_incoming": {"block", "incoming", "damage", "high", "defend"},
    "energy_management": {"energy", "cost", "0-cost", "free", "spend"},
    "kill_if_possible": {"kill", "lethal", "finish", "one-shot"},
    "vulnerable_before_damage": {"vulnerable", "before", "damage", "apply"},
    "weak_reduces_damage": {"weak", "reduce", "incoming", "less"},
    "dont_waste_energy": {"waste", "energy", "unspent", "leftover"},
    "play_0_cost_first": {"0-cost", "free", "first", "before"},
    "aoe_for_multi_enemy": {"aoe", "all", "enemies", "multi", "area"},
    "draw_before_play": {"draw", "before", "play", "cards", "cycle"},
    "potion_timing": {"potion", "timing", "save", "boss", "emergency"},
}

# ── Token helpers ─────────────────────────────────────────────────────────────


def _tokenize(text: str) -> set[str]:
    """Lowercase, split on non-alphanumeric, remove stopwords."""
    tokens: set[str] = set()
    for word in text.lower().split():
        # Strip leading/trailing punctuation
        word = word.strip(".,!?;:\"'()-[]{}*/\\")
        if word and word not in _STOPWORDS:
            tokens.add(word)
    return tokens


# ── Public API ────────────────────────────────────────────────────────────────


def content_overlap(a_content: str, b_content: str) -> float:
    """Jaccard similarity between two skill content strings after stopword removal.

    Returns 0.0-1.0. Returns 0.0 if both strings produce empty token sets.
    """
    a_tokens = _tokenize(a_content)
    b_tokens = _tokenize(b_content)

    union = a_tokens | b_tokens
    if not union:
        return 0.0

    intersection = a_tokens & b_tokens
    return len(intersection) / len(union)


def trigger_overlap(a: SkillTrigger, b: SkillTrigger) -> float:
    """Compare two SkillTriggers across shared frozenset dimensions.

    Dimensions compared: state_types, enemy_names, requires_hand_capabilities.
    A dimension is "shared" if at least one side is non-empty.
    Returns 0.0 if no dimensions have any content on either side.

    Score for each shared dimension = Jaccard similarity of the two frozensets.
    Final result = mean across shared dimensions.
    """
    dimensions: list[tuple[frozenset[str], frozenset[str]]] = [
        (a.state_types, b.state_types),
        (a.enemy_names, b.enemy_names),
        (a.requires_hand_capabilities, b.requires_hand_capabilities),
    ]

    scores: list[float] = []
    for fa, fb in dimensions:
        if not fa and not fb:
            # Both empty — dimension carries no information, skip
            continue
        union = fa | fb
        intersection = fa & fb
        scores.append(len(intersection) / len(union) if union else 0.0)

    if not scores:
        return 0.0

    return sum(scores) / len(scores)


def is_semantic_duplicate(candidate: dict, existing: Skill) -> bool:
    """True if the candidate skill dict is semantically a duplicate of existing.

    Duplicate conditions (OR):
    - trigger_overlap >= 0.7 AND content_overlap >= 0.4
    - content_overlap >= 0.6  (regardless of trigger)
    """
    from src.skills.models import SkillTrigger

    candidate_trigger = SkillTrigger.from_dict(candidate.get("trigger", {}))
    candidate_content = candidate.get("content", "")

    c_overlap = content_overlap(candidate_content, existing.content)
    if c_overlap >= 0.6:
        return True

    t_overlap = trigger_overlap(candidate_trigger, existing.trigger)
    return t_overlap >= 0.7 and c_overlap >= 0.4


def _trigger_specificity(trigger: dict) -> float:
    """Measure how specific a trigger dict is (0.0 = fully generic, 1.0 = maximally specific).

    Scoring contributions (capped at 1.0):
    - enemy_names non-empty:                +0.3
    - requires_cards non-empty:             +0.2
    - requires_hand_capabilities non-empty: +0.2
    - requires_enemy_powers non-empty:      +0.1
    - any_of_relics non-empty:              +0.1
    - act range narrower than 1-3 acts:     +0.1
    """
    score = 0.0

    if trigger.get("enemy_names"):
        score += 0.3
    if trigger.get("requires_cards"):
        score += 0.2
    if trigger.get("requires_hand_capabilities"):
        score += 0.2
    if trigger.get("requires_enemy_powers"):
        score += 0.1
    if trigger.get("any_of_relics"):
        score += 0.1

    # Act range specificity: default is 0-99 (99 acts wide).
    # A range of 1 act or less is maximally specific (+0.1).
    min_act = trigger.get("min_act", 0)
    max_act = trigger.get("max_act", 99)
    act_range = max_act - min_act
    if act_range <= 3:
        score += 0.1

    return min(score, 1.0)


def common_knowledge_score(
    content: str,
    trigger: dict,
    novelty: float,
) -> tuple[float, str]:
    """Estimate how much of content is common knowledge already in the system prompt.

    Returns (penalty: float 0.0-1.0, matched_concept_name: str).

    Heavy penalty (full keyword-overlap score) is applied ONLY when ALL THREE:
    - keyword overlap with a known concept >= 0.6
    - trigger specificity < 0.2   (broad / generic trigger)
    - novelty < 0.5               (low novelty signal)

    Otherwise penalty is capped at 0.3 (mild warning, not disqualifying).
    """
    content_tokens = _tokenize(content)
    if not content_tokens:
        return 0.0, ""

    best_concept = ""
    best_overlap = 0.0

    for concept_name, keywords in SYSTEM_PROMPT_CONCEPTS.items():
        intersection = content_tokens & keywords
        # Jaccard over the concept keyword set (content tokens as denominator
        # would penalise long content — use concept-side union for fairness)
        union = content_tokens | keywords
        if not union:
            continue
        overlap = len(intersection) / len(union)
        if overlap > best_overlap:
            best_overlap = overlap
            best_concept = concept_name

    if best_overlap == 0.0:
        return 0.0, ""

    specificity = _trigger_specificity(trigger)

    # Heavy penalty gate: ALL THREE conditions must hold
    if best_overlap >= 0.6 and specificity < 0.2 and novelty < 0.5:
        return best_overlap, best_concept

    # Otherwise: mild warning, capped at 0.3
    penalty = min(best_overlap, 0.3)
    return penalty, best_concept


def is_seed_restatement(content: str, seed_skills: list) -> bool:
    """True if content_overlap >= 0.5 with any skill in seed_skills.

    seed_skills may be a list of Skill objects or dicts with a "content" key.
    """
    for skill in seed_skills:
        if isinstance(skill, dict):
            seed_content = skill.get("content", "")
        else:
            seed_content = getattr(skill, "content", "")

        if content_overlap(content, seed_content) >= 0.5:
            return True

    return False
