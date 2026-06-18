"""Runtime card effect detection from resolved rules_text. No hardcoded card lists."""
from __future__ import annotations

import re

_DISCARD_PATTERNS = (
    re.compile(r"discard\s+(\d+)\s+cards?", re.IGNORECASE),
    re.compile(r"discard\s+a\s+card", re.IGNORECASE),
    re.compile(r"弃置(\d+)张牌"),
)


def detect_discard_count(rules_text: str | None) -> int:
    """Return the number of cards discarded by this card's effect, or 0 if none.

    Detects patterns like 'Discard 1 card', 'Discard a card', '弃置2张牌'.
    Case-insensitive for English patterns.
    """
    if not rules_text:
        return 0
    for pat in _DISCARD_PATTERNS:
        m = pat.search(rules_text)
        if m:
            groups = m.groups()
            return int(groups[0]) if groups and groups[0] else 1
    return 0


_DRAW_PATTERNS = (
    re.compile(r"[Dd]raw\s+\d+\s+cards?"),
    re.compile(r"[Aa]dd\s+.{0,20}to\s+your\s+hand"),
    re.compile(r"[Pp]ut\s+.{0,20}into\s+your\s+hand"),
    re.compile(r"抽\d+张牌"),
)

_SEGMENT_SPLIT = re.compile(r"[.\n;。；]")
_DELAYED_DRAW_PATTERNS = (
    re.compile(r"\bnext\s+turn\b", re.IGNORECASE),
    re.compile(r"\bat\s+the\s+start\s+of\s+your\s+next\s+turn\b", re.IGNORECASE),
    re.compile(r"下(?:个|一)?回合"),
)


def detect_draws_cards(rules_text: str | None) -> bool:
    """Return True if the card draws or adds cards to hand.

    These cards change the hand unpredictably — the combat plan must be split
    at this point: execute up to and including this card, then re-plan.

    Detects patterns like 'Draw 2 cards', 'Add a copy to your hand',
    'Put into your hand', '抽2张牌'.
    """
    if not rules_text:
        return False
    for segment in _SEGMENT_SPLIT.split(rules_text):
        if not segment.strip():
            continue
        if any(p.search(segment) for p in _DELAYED_DRAW_PATTERNS):
            continue
        if any(p.search(segment) for p in _DRAW_PATTERNS):
            return True
    return False
