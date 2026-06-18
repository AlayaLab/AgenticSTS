"""Format `generated_cards` (cards a card generates mid-play) for prompts.

The upstream C# mod populates `generated_cards` from `CardModel.HoverTips`
(same source the in-game long-press preview uses). It is upgrade-aware:
when the source card is upgraded, the generated card here is the upgraded
variant (e.g. Hidden Daggers+ → Shiv+).

Two output styles:
  - `format_generated_cards_lines`: indented multi-line (combat hand)
  - `format_generated_cards_inline`: short single-line suffix (reward/shop)
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import strip_bbcode
from src.mcp_client.upstream_models import RawGeneratedCardPayload


def format_generated_cards_lines(
    gens: list[RawGeneratedCardPayload],
) -> list[str]:
    """Render generated cards as indented preview lines (one per generated card).

    Empty list when no generated cards.
    """
    if not gens:
        return []

    lines: list[str] = []
    for gen in gens:
        upgraded = "+" if gen.upgraded else ""
        kw = f", {', '.join(gen.keywords)}" if gen.keywords else ""
        rules = strip_bbcode(gen.rules_text) if gen.rules_text else ""
        rules_part = f": {rules}" if rules else ""
        lines.append(
            f"  ↳ generates {gen.name}{upgraded} "
            f"({gen.card_type}, cost={gen.energy_cost}{kw}){rules_part}"
        )
    return lines


def format_generated_cards_inline(
    gens: list[RawGeneratedCardPayload],
) -> str:
    """Render generated cards as a short single-line suffix.

    Empty string when no generated cards. Format:
        " → generates: Shiv (Attack, 0E, Exhaust): Deal 4 damage."
        " → generates: Shiv (Attack, 0E, Exhaust); Soul (Skill, 0E)"
    """
    if not gens:
        return ""

    parts: list[str] = []
    for gen in gens:
        upgraded = "+" if gen.upgraded else ""
        kw = f", {', '.join(gen.keywords)}" if gen.keywords else ""
        rules = strip_bbcode(gen.rules_text) if gen.rules_text else ""
        rules_part = f": {rules}" if rules else ""
        parts.append(
            f"{gen.name}{upgraded} ({gen.card_type}, {gen.energy_cost}E{kw}){rules_part}"
        )
    return " → generates: " + "; ".join(parts)
