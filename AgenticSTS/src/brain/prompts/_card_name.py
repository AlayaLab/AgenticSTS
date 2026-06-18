"""Card display-name helpers.

The C# mod's `card.Title` already includes "+" in `name` for upgraded cards
(e.g. `Volley+`, `Neutralize+`). The `upgraded` boolean flag separately
encodes the same signal. Naive formatters that do `f"{c.name}{'+' if c.upgraded else ''}"`
double the suffix and produce `Volley++`, which then breaks the locale
translator (no entry for `Volley++`) and surfaces in the stream-ui plan
display as untranslated `Volley++` rows.

Use `upgrade_suffix(c)` in formatters: it returns "+" only when the card
is upgraded AND its name does not already end with "+".
"""

from __future__ import annotations


def upgrade_suffix(card) -> str:
    """Return "+" iff the card is upgraded and `card.name` doesn't already end with "+"."""
    if not getattr(card, "upgraded", False):
        return ""
    name = getattr(card, "name", "") or ""
    if name.endswith("+"):
        return ""
    return "+"


def display_name(card) -> str:
    """Return the card's display name with at most one trailing "+"."""
    name = getattr(card, "name", "") or ""
    return name + upgrade_suffix(card)
