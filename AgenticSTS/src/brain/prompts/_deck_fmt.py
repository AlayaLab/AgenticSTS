"""Shared formatting helpers for LLM prompts."""

from __future__ import annotations
from src.brain.prompts._card_name import upgrade_suffix

import re

from src.mcp_client.upstream_models import RawDeckCardPayload


_ENERGY_TOK = "\x00E\x00"
_STAR_TOK = "\x00S\x00"
_HP_TOK = "\x00H\x00"


def strip_bbcode(text: str) -> str:
    """Remove BBCode tags and Godot resource paths from game text."""
    # Replace icon img tags with private tokens to count runs later
    text = re.sub(r"\[img\][^\[]*energy_icon[^\[]*\[/img\]", _ENERGY_TOK, text)
    text = re.sub(r"\[img\][^\[]*star_icon[^\[]*\[/img\]", _STAR_TOK, text)
    text = re.sub(r"\[img\][^\[]*(?:hp|health)_icon[^\[]*\[/img\]", _HP_TOK, text)
    # Strip remaining [img]...[/img] blocks entirely
    text = re.sub(r"\[img\][^\[]*\[/img\]", "", text)
    # Strip simple BBCode tags (e.g. [gold], [/gold], [blue])
    text = re.sub(r"\[/?[a-zA-Z_]+\]", "", text)
    # Merge consecutive icon tokens into "N Label" (handles "EnergyEnergy" → "2 Energy")
    for tok, singular, plural in (
        (_ENERGY_TOK, "Energy", "Energy"),
        (_STAR_TOK, "Star", "Stars"),
        (_HP_TOK, "HP", "HP"),
    ):
        def _merge(m: re.Match, _tok: str = tok, _s: str = singular, _p: str = plural) -> str:
            n = len(m.group(0)) // len(_tok)
            return f"{n} {_p}" if n > 1 else _s
        text = re.sub(f"(?:{re.escape(tok)})+", _merge, text)
    return text.strip()


def _format_cost(c: RawDeckCardPayload) -> str:
    """Format energy cost for display: 'X' if costs_x, else str(energy_cost)."""
    return "X" if c.costs_x else str(c.energy_cost)


def format_deck_section(
    deck: list[RawDeckCardPayload] | None,
    include_descriptions: bool = False,
) -> list[str]:
    """Format the master deck as prompt lines.

    Groups identical cards (e.g. "Strike x5") sorted by count descending
    within each card type. Upgrade markers preserved: "Strike+ x2".

    When *include_descriptions* is True, each unique card gets its own line
    with the card's rules_text appended (one-card-per-line format).
    """
    if deck is None:
        return ["", "## Current Deck (unknown — data not available)"]

    if not deck:
        return ["", "## Current Deck (empty — no cards yet)"]

    lines = ["", f"## Current Deck ({len(deck)} cards)"]

    # Group by card_type
    by_type: dict[str, list[RawDeckCardPayload]] = {}
    for card in deck:
        by_type.setdefault(card.card_type, []).append(card)

    for card_type in sorted(by_type):
        cards = by_type[card_type]
        # Count by display name (with upgrade marker + enchantment marker)
        counts: dict[str, int] = {}
        cost_map: dict[str, str] = {}
        desc_map: dict[str, str] = {}
        for c in cards:
            enchant = getattr(c, "enchantment_name", None) or getattr(c, "enchantment_id", None)
            enchant_suffix = f"[{enchant}]" if enchant else ""
            display = c.name + upgrade_suffix(c) + enchant_suffix
            counts[display] = counts.get(display, 0) + 1
            star = f" ★{c.star_cost}" if c.star_cost else ""
            cost_map[display] = f"cost={_format_cost(c)}{star}"
            # Store rules_text for descriptions (first seen wins)
            if display not in desc_map:
                raw = (getattr(c, "resolved_rules_text", "") or c.rules_text or "").strip()
                desc_map[display] = strip_bbcode(raw) if raw else ""

        # Sort by count descending, then name
        sorted_cards = sorted(counts.items(), key=lambda x: (-x[1], x[0]))

        if include_descriptions:
            # One card per line with description
            for name, count in sorted_cards:
                cost_info = cost_map.get(name, "")
                desc = desc_map.get(name, "")
                count_str = f" x{count}" if count > 1 else ""
                desc_suffix = f": {desc}" if desc else ""
                lines.append(f"  - {name}({cost_info}){count_str}{desc_suffix}")
        else:
            # Compact comma-separated format (original)
            card_strs = []
            for name, count in sorted_cards:
                cost_info = cost_map.get(name, "")
                if count == 1 and cost_info:
                    card_strs.append(f"{name}({cost_info})")
                else:
                    card_strs.append(f"{name} x{count}")
            lines.append(f"  [{card_type}] {', '.join(card_strs)}")

    return lines
