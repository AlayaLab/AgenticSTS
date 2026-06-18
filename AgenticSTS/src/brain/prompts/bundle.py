# ruff: noqa: E501
"""Prompt template for ScrollBoxes bundle selection.

Triggered by the Ancient relic ``ScrollBoxes``: the player loses all gold
and is presented with N bundles of cards.  Picking a bundle adds **all**
its cards to the deck (no per-card choice within a bundle).
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.mcp_client.upstream_models import RawBundleCardPayload, RawDeckCardPayload
from src.state.game_state import GameState


_DECISION_OUTPUT = """## Output (JSON inside <decision>)
Pick exactly one bundle.  Use `select_deck_card` with the bundle's index:

```
<decision>
{"action": "select_deck_card", "option_index": <bundle_index>, "reasoning": "...", "strategic_note": "..."}
</decision>
```

If a confirmation step appears next (a single bundle preview screen with a
confirm button), the runtime auto-confirms via `confirm_selection`.
"""


def _format_bundle_card(card: RawBundleCardPayload) -> str:
    cost = "X" if card.costs_x else str(card.energy_cost)
    upgrade_marker = "+" if card.upgraded else ""
    rules = card.resolved_rules_text or card.rules_text or ""
    rules = strip_bbcode(rules)
    rarity = f", {card.rarity}" if card.rarity else ""
    type_str = f" [{card.card_type}{rarity}]" if card.card_type else ""
    if rules:
        return f"  - {card.name}{upgrade_marker} (cost={cost}){type_str}: {rules}"
    return f"  - {card.name}{upgrade_marker} (cost={cost}){type_str}"


def build_bundle_selection_prompt(
    gs: GameState,
    *,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    """Build the user-message prompt for ScrollBoxes bundle selection."""
    bundles = gs.bundles
    if not bundles:
        return "## Bundle Selection\n(no bundles)\n"

    sections: list[str] = []
    sections.append("## Bundle Selection — ScrollBoxes")
    sections.append(
        "ScrollBoxes drained all your gold and is offering you a one-time "
        "deck-shaping. Pick exactly **one** bundle; **every** card in that "
        "bundle is added to your deck (you cannot pick individual cards)."
    )

    sections.append(
        f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold} (just lost to ScrollBoxes) | "
        f"Floor: {gs.run.floor if gs.run else '?'} | Act: {gs.act}"
    )
    if gs.character:
        sections.append(f"Character: {gs.character}")

    if deck is not None:
        deck_lines = format_deck_section(deck)
        if deck_lines:
            sections.append("\n".join(deck_lines))

    if relics:
        sections.append("## Relics")
        sections.append(", ".join(relics))

    sections.append("## Bundle Options")
    glossary_text_sources: list[str] = []
    for bundle in bundles:
        sections.append(f"### Bundle [{bundle.index}] — {len(bundle.cards)} cards")
        for card in bundle.cards:
            sections.append(_format_bundle_card(card))
            if card.resolved_rules_text:
                glossary_text_sources.append(card.resolved_rules_text)
            elif card.rules_text:
                glossary_text_sources.append(card.rules_text)

    glossary = format_keyword_glossary(glossary_text_sources)
    if glossary:
        sections.append(glossary)

    sections.append(
        "## How to think about this\n"
        "- Look at the **whole bundle** as one decision: cost curve, attack/skill mix, "
        "synergy with current deck, and how many junk cards you'd be forced to take.\n"
        "- Bundles can hide trap cards — a single Curse / unplayable in a bundle of 3 is "
        "often worse than skipping the relic entirely (but ScrollBoxes already drained the gold).\n"
        "- Prefer bundles aligned with the run's win condition (poison/scaling/burst/etc.)."
    )

    sections.append(_DECISION_OUTPUT)

    return "\n\n".join(sections)
