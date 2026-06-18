# ruff: noqa: E501
"""Card mechanic clarifications for commonly misunderstood cards.

Injected into card reward, shop, and combat prompts when relevant cards
appear in offered options or the current deck.
"""

from __future__ import annotations

# Card name (case-insensitive key) -> clarification text.
# Extend this dict as more misunderstandings are discovered.
BOSS_HP_TARGETS: dict[int, int] = {1: 200, 2: 400, 3: 600}

CARD_CLARIFICATIONS: dict[str, str] = {
    "speedster": (
        "Speedster: Turn-start draw does NOT trigger Speedster. "
        "Only draw effects from played cards (Backflip, Acrobatics, etc.) count. "
        "Without draw cards in deck, Speedster deals 0 damage/turn. "
        "Value scales with draw card density."
    ),
    "ricochet": (
        "Ricochet: Accuracy does NOT buff Ricochet. "
        "Accuracy only adds +4 damage to Shivs; Ricochet is not a Shiv. "
        "Base damage is 4 hits × 3 = 12 (upgraded: 4 × 4 = 16). "
        "Value comes from Sly (free when discarded) with discard outlets."
    ),
    "accuracy": (
        "Accuracy: ONLY boosts Shiv cards (Blade Dance outputs, Infinite Blades outputs, "
        "Fan of Knives outputs, Cloak and Dagger outputs, etc.). "
        "Does NOT buff other multi-hit attacks like Ricochet or Dagger Spray."
    ),
    "follow through": (
        "Follow Through: The '5 or more other cards' check happens AT THE MOMENT it is played. "
        "ALWAYS play Follow Through BEFORE playing other cards from your hand, or the double-hit "
        "condition will fail. Example: with 6 cards in hand, playing 2 zero-cost cards first "
        "reduces hand to 4 — Follow Through then only hits once. Play it first to guarantee the "
        "second hit."
    ),
}

# Short inline warnings appended directly to the card's display line.
# Must be concise (<80 chars) since they sit on the same line as the card description.
CARD_INLINE_WARNINGS: dict[str, str] = {
    "speedster": "!! Turn-start draw does NOT trigger. 0 dmg without draw cards (Backflip, Acrobatics).",
    "ricochet": "!! Accuracy does NOT buff this card. Not a Shiv.",
    "accuracy": "!! Only buffs Shiv cards. Does not buff Ricochet, Dagger Spray, or other multi-hits.",
    "follow through": "!! Play FIRST — double-hit checks hand size at play time; playing other cards first will fail the condition.",
}


def get_inline_warning(card_name: str) -> str:
    """Return a short inline warning for a card, or empty string."""
    return CARD_INLINE_WARNINGS.get(card_name.rstrip("+").lower(), "")


def format_card_notes(
    offered_names: list[str],
    deck_names: list[str],
) -> str:
    """Build a Card Notes section if any relevant cards are present.

    Scans both offered card names and deck card names against
    CARD_CLARIFICATIONS. Returns a formatted section or empty string.

    Args:
        offered_names: Names of cards being offered (reward/shop).
        deck_names: Names of cards currently in the deck.
    """
    # Normalize: strip "+" suffix, lowercase
    all_names = {n.rstrip("+").lower() for n in offered_names}
    all_names.update(n.rstrip("+").lower() for n in deck_names)

    matched = [
        note
        for key, note in CARD_CLARIFICATIONS.items()
        if key in all_names
    ]

    if not matched:
        return ""

    lines = ["", "## Card Notes"]
    for note in matched:
        lines.append(f"- {note}")
    return "\n".join(lines)
