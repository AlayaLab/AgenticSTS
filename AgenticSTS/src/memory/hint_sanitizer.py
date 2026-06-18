"""Small prompt-safety sanitizers for persisted memory hints."""

from __future__ import annotations

_BAD_DECK_GUIDE_LINES = {
    (
        "- Prioritize damage cards in first 3 fights: Blade Dance, Backstab, "
        "Dagger Spray, Poisoned Stab, Quick Slash, Sucker Punch. Base Strikes "
        "cannot kill enemies before they overwhelm you."
    ),
    (
        "- Add block cards by Floor 4: Deflect, Backflip, Dodge and Roll, "
        "Leg Sweep. You cannot survive on Survivor alone."
    ),
}


def sanitize_deck_guide_text(text: str) -> str:
    """Drop known-bad legacy deck-guide lines from prompt output."""
    if not text:
        return ""

    kept = [line for line in text.splitlines() if line.strip() not in _BAD_DECK_GUIDE_LINES]
    return "\n".join(kept).strip()


def sanitize_deck_guide_hints(hints: tuple[str, ...]) -> tuple[str, ...]:
    """Sanitize already-formatted deck-guide hints."""
    cleaned: list[str] = []
    for hint in hints:
        sanitized = sanitize_deck_guide_text(hint)
        if sanitized:
            cleaned.append(sanitized)
    return tuple(cleaned)
