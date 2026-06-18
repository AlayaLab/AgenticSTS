"""Warn-only validators for filled seed stubs.

All checks emit warning strings; none reject. Warnings are accumulated in
``_metadata.warnings`` (or returned to the caller) for post-hoc human review.
The philosophy is: trust the LLM to produce reasonable content, surface
quality concerns to the human reviewer, but never block the write.

Spec: ``docs/superpowers/specs/2026-05-03-seed-stub-self-evolution-design.md``
"""

from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)


def _estimate_tokens(text: str) -> int:
    """Rough estimate: 1 token ≈ 4 characters (English-leaning, matches OpenAI tiktoken)."""
    return max(1, len(text) // 4)


def _parse_token_range(spec: str) -> tuple[int, int]:
    """e.g. ``'400-700 tokens'`` -> ``(400, 700)``. Falls back to (0, inf) on parse error."""
    m = re.search(r"(\d+)\s*-\s*(\d+)", spec)
    if not m:
        return (0, 10**9)
    return (int(m.group(1)), int(m.group(2)))


def _flatten_text(parsed: dict) -> str:
    """Concat all principle text+example fields into one searchable string."""
    parts: list[str] = []
    for p in parsed.get("principles", []):
        parts.append(p.get("text", ""))
        parts.append(p.get("example", ""))
    return " ".join(parts)


def _extract_card_names(text: str) -> list[str]:
    """Extract distinct card names mentioned in text via GameKnowledge.

    Returns lowercase names. Falls back to empty list if knowledge layer is
    unavailable (e.g. test environments). Tests can monkeypatch this function.
    """
    try:
        from src.knowledge.knowledge import GameKnowledge
        gk = GameKnowledge.get_instance()
        # CardLookup keys are lowercased card names
        all_names = list(gk.cards._cards.keys())  # noqa: SLF001  (deliberate internal access)
    except Exception:
        return []
    text_low = text.lower()
    found: list[str] = []
    for name in all_names:
        # Word-boundary match
        if re.search(rf"\b{re.escape(name)}\b", text_low):
            found.append(name)
    return found


def _extract_enemy_names(text: str) -> list[str]:
    """Extract distinct enemy names mentioned in text via GameKnowledge."""
    try:
        from src.knowledge.knowledge import GameKnowledge
        gk = GameKnowledge.get_instance()
        all_names = list(gk.monsters._monsters.keys())  # noqa: SLF001
    except Exception:
        return []
    text_low = text.lower()
    found: list[str] = []
    for name in all_names:
        if re.search(rf"\b{re.escape(name)}\b", text_low):
            found.append(name)
    return found


def _starts_imperative(text: str) -> bool:
    """Heuristic: principle text starts with an imperative verb.

    Returns True if the first word does NOT match common descriptive starters
    (subject pronouns, articles, copulas). False positives (some imperatives
    incorrectly flagged) are acceptable since the validator is warn-only.
    """
    if not text:
        return False
    first = text.strip().split()[0].rstrip(",.!?;:").lower()
    # Common descriptive starters that indicate non-imperative voice
    descriptive_starters = {
        "energy", "hp", "block", "the", "a", "an", "this", "that",
        "your", "you", "it", "there", "every", "each", "is", "are", "was",
        "were", "has", "have", "had", "will", "would", "should", "could",
        "card", "cards", "deck", "boss", "enemy", "enemies",
    }
    if first in descriptive_starters:
        return False
    return True


def run_stub_validators(parsed: dict, scaffold: dict) -> list[str]:
    """Run all 7 warn-only validators on a parsed fill response.

    Args:
        parsed: ``{"principles": [...], "confidence": float, ...}`` from LLM.
        scaffold: the stub's scaffold dict (token_budget, leakage_guard, etc.).

    Returns:
        List of warning strings (may be empty). Each warning is a short
        diagnostic the human reviewer can scan.
    """
    warnings: list[str] = []
    text = _flatten_text(parsed)
    principles = parsed.get("principles", [])

    # 1. Token count vs budget
    actual = _estimate_tokens(text)
    budget = scaffold.get("format_constraints", {}).get("token_budget", "0-999999")
    lo, hi = _parse_token_range(budget)
    if actual < lo or actual > hi:
        warnings.append(f"token_count_out_of_range: {actual} not in [{lo},{hi}]")

    # 2. Principle count (4-8 range; some stubs allow 4 minimum)
    if not (4 <= len(principles) <= 8):
        warnings.append(f"principle_count_off: got {len(principles)}, want 4-8")

    # 3. Card name density (leakage guard)
    cards = _extract_card_names(text)
    max_cards = scaffold.get("leakage_guard", {}).get("max_distinct_card_names", 8)
    distinct_cards = len(set(cards))
    if distinct_cards > max_cards:
        warnings.append(
            f"card_name_density_high: {distinct_cards} distinct cards (max {max_cards})"
        )

    # 4. Enemy name density (leakage guard)
    enemies = _extract_enemy_names(text)
    max_enemies = scaffold.get("leakage_guard", {}).get("max_distinct_enemy_names", 3)
    distinct_enemies = len(set(enemies))
    if distinct_enemies > max_enemies:
        warnings.append(
            f"enemy_name_density_high: {distinct_enemies} distinct enemies (max {max_enemies})"
        )

    # 5. Specific damage thresholds (regex)
    if scaffold.get("leakage_guard", {}).get("no_specific_damage_thresholds", True):
        nums = re.findall(r"\b\d+\s+(?:damage|HP|hp|block|Block)\b", text)
        if nums:
            warnings.append(f"specific_thresholds_found: {nums}")

    # 6. Imperative voice (heuristic)
    descriptive = sum(
        1 for p in principles
        if not _starts_imperative(p.get("text", ""))
    )
    if descriptive > 2:
        warnings.append(
            f"voice_check: {descriptive}/{len(principles)} principles non-imperative"
        )

    # 7. Confidence sanity
    confidence = parsed.get("confidence", 0.5)
    if not (0.3 <= confidence <= 0.95):
        warnings.append(f"confidence_out_of_range: {confidence}")

    return warnings
