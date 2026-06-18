# ruff: noqa: E501
"""Prompt template for shop decisions.

Gold-budget-aware purchase framework with explicit priority ordering.
Balanced purchase framework: cards, relics, removal, potions evaluated equally.
"""

from __future__ import annotations

import config
from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
from src.brain.prompts._card_clarifications import (
    BOSS_HP_TARGETS,
    format_card_notes,
    get_inline_warning,
)
from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._generated_fmt import format_generated_cards_inline
from src.brain.prompts._regent_economy_fmt import (
    annotate_card_note,
    annotate_card_tiers,
    format_regent_economy,
    format_regent_offering_summary,
    regent_star_state,
)
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision
from src.brain.prompts._relic_fmt import format_relic_hints
from src.knowledge.knowledge import GameKnowledge
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState

_MAX_ITEM_DESC = 180


def _clean_item_text(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(strip_bbcode(text).split())


def _truncate_item_text(text: str, max_chars: int = _MAX_ITEM_DESC) -> str:
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _get_shop_relic_description(name: str, description: str | None, kb: GameKnowledge | None) -> str:
    clean = _clean_item_text(description)
    if clean:
        return _truncate_item_text(clean)
    if kb is None:
        return ""
    relic = kb.relics.get(name)
    if relic and relic.description:
        return _truncate_item_text(_clean_item_text(relic.description))
    return ""


def _get_shop_potion_description(name: str | None, description: str | None, kb: GameKnowledge | None) -> str:
    clean = _clean_item_text(description)
    if clean:
        return _truncate_item_text(clean)
    if kb is None or not name:
        return ""
    potion = kb.potions.get(name)
    if potion and potion.on_use:
        return _truncate_item_text(_clean_item_text(potion.on_use))
    return ""


def build_shop_plan_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    character: str = "",
    guide_store: object | None = None,
) -> str:
    """Build a prompt for shop purchase decisions.

    Per-card experience notes are injected via the unified memory retriever
    (`## Card-Specific Insights`); no direct card_memory_store read here.

    If ``guide_store`` is provided and the shop has cards for sale, a
    ``## Upcoming Act Boss`` section is injected via
    :func:`format_upcoming_boss_guide`. The ``shop.cards`` precondition keeps
    relic-only / potion-only shop visits unchanged, since the guide is about
    deckbuild-time card picking.
    """
    shop = gs.shop
    if not shop:
        return ""

    try:
        kb = GameKnowledge.get_instance()
    except Exception:
        kb = None

    gold = gs.gold

    lines = [
        "## Shop",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gold}",
    ]

    lines.append(f"Status: {'OPEN' if shop.is_open else 'CLOSED'}")

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    lines.extend(format_deck_section(deck, include_descriptions=True))
    lines.extend(format_regent_economy(deck, character))
    # Compute deck-state once for tier annotation + offering verdict.
    _regent_deck_state = regent_star_state(deck, character)

    if relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    if not config.PROMPT_HINT_FILTER:
        relic_section = format_relic_hints(relics or [], context="shop")
        if relic_section:
            lines.append(relic_section)

    # Upcoming-boss guide: only inject when cards are actually for sale
    if guide_store is not None and shop.cards:
        lines.extend(format_upcoming_boss_guide(gs, character, guide_store))

    # Potion slot decision: slots full + affordable potion in shop
    try:
        open_slots = int(getattr(gs, "open_potion_slots", 0) or 0)
    except (TypeError, ValueError):
        open_slots = 1  # treat unknown as "slots available" → skip injection
    if open_slots <= 0 and shop.potions:
        affordable = [p for p in shop.potions if getattr(p, "price", 0) <= gold]
        candidates = [
            ((getattr(p, "name", "") or "").strip(),
             (getattr(p, "description", "") or "").strip())
            for p in affordable
        ]
        candidates = [(n, d) for n, d in candidates if n]
        if candidates:
            lines.extend(format_potion_slot_decision(gs, candidates))

    # Gold budget analysis
    lines.append("")
    lines.append("## Gold Budget Analysis")

    # Card removal
    removal = shop.card_removal
    affordable_cards = [c for c in shop.cards if c.is_stocked and c.enough_gold]
    affordable_relics = [r for r in shop.relics if r.is_stocked and r.enough_gold]
    affordable_potions = [p for p in shop.potions if p.is_stocked and p.enough_gold]
    # Potions that gold covers but potion slots are full for (upstream marks
    # these as enough_gold=False). They remain buyable via discard_potion swap.
    slot_blocked_potions = [
        p for p in shop.potions
        if p.is_stocked and not p.enough_gold and getattr(p, "price", 0) <= gold
    ] if open_slots <= 0 else []

    total_affordable = len(affordable_cards) + len(affordable_relics) + len(affordable_potions)
    removal_affordable = bool(removal and removal.available and not removal.used and removal.enough_gold)
    lines.append(f"Affordable: {total_affordable} items ({len(affordable_cards)}c {len(affordable_relics)}r {len(affordable_potions)}p)")
    if slot_blocked_potions:
        lines.append(
            f"+ {len(slot_blocked_potions)} potion(s) within gold budget but slots FULL — "
            "swap via discard_potion (see Potion Slot Decision above)."
        )
    if total_affordable == 0 and not removal_affordable and not slot_blocked_potions:
        lines.append("Nothing affordable — consider leaving.")

    # Build Glossary + Items For Sale into sub-lists; append them at the very
    # end of this builder's output so they sit immediately before the
    # ## Decision Format schema appended by v2_engine.
    glossary_lines: list[str] = []
    items_lines: list[str] = []

    card_texts = [c.rules_text for c in shop.cards if c.is_stocked]
    if deck:
        card_texts.extend(d.rules_text or "" for d in deck)
    glossary = format_keyword_glossary(card_texts)
    if glossary:
        glossary_lines.append(glossary)

    items_lines.append("")
    items_lines.append("## Items For Sale")

    # Cards
    for c in shop.cards:
        if not c.is_stocked:
            continue
        tag = "CAN BUY" if c.enough_gold else "TOO EXPENSIVE"
        sale = " SALE" if c.on_sale else ""
        cost_str = "X" if c.costs_x else str(c.energy_cost)
        rarity = f" {c.rarity}" if c.rarity else ""
        card_line = (
            f"- [{c.index}] {c.name} ({cost_str}E, {c.price}g{sale}) "
            f"[{tag}]{rarity}: {strip_bbcode(c.rules_text)}"
        )
        if not config.PROMPT_HINT_FILTER:
            inline_warn = get_inline_warning(c.name)
            if inline_warn:
                card_line += f" {inline_warn}"
        card_line += format_generated_cards_inline(getattr(c, "generated_cards", []) or [])
        card_line += annotate_card_tiers(c.name, character, deck_state=_regent_deck_state)
        card_line += annotate_card_note(c.name, character)
        items_lines.append(card_line)

    # Relics
    for r in shop.relics:
        if not r.is_stocked:
            continue
        tag = "CAN BUY" if r.enough_gold else "TOO EXPENSIVE"
        desc = _get_shop_relic_description(r.name, r.description, kb)
        suffix = f": {desc}" if desc else ""
        items_lines.append(f"- [{r.index}] {r.name} (Relic, {r.rarity}, {r.price}g) [{tag}]{suffix}")

    # Potions
    for p in shop.potions:
        if not p.is_stocked:
            continue
        if p.enough_gold:
            tag = "CAN BUY"
        elif open_slots <= 0 and getattr(p, "price", 0) <= gold:
            tag = "SLOTS FULL — discard_potion first"
        else:
            tag = "TOO EXPENSIVE"
        desc = _get_shop_potion_description(p.name, p.description, kb)
        suffix = f": {desc}" if desc else ""
        items_lines.append(f"- [{p.index}] {p.name} (Potion, {p.price}g) [{tag}]{suffix}")

    # Card removal as separate entry (part of Items For Sale)
    if removal and removal.available and not removal.used:
        affordable = "CAN BUY" if removal.enough_gold else "TOO EXPENSIVE"
        items_lines.append(f"- [REMOVE] Card Removal ({removal.price}g) [{affordable}]")

    # DPS-aware guide — generic character-agnostic. SUPPRESSED for Regent
    # (the 'PRIORITIZE damage/poison cards if below target' framing
    # contradicts XecnaR's macro 'skip mediocre commons; basic deck is
    # strong enough'). Regent gets purchase guidance from the deck-economy
    # block + per-card tiers + offering verdict + seed skills.
    is_regent = (character or "").strip().lower() == "the regent"
    if config.PROMPT_VARIANT != "baseline" and not is_regent:
        boss_hp = BOSS_HP_TARGETS.get(gs.act, BOSS_HP_TARGETS[2])
        target_dps = boss_hp // 10

        lines.append("")
        lines.append("## Guide")
        lines.append("Best purchase = biggest power spike for remaining run.")
        lines.append("")
        lines.append(f"Boss HP: ~{boss_hp} in ~10 turns → need ~{target_dps} damage/turn.")
        lines.append("Estimate your deck's damage output first. If below target, prioritize damage/poison cards.")
        lines.append("For scaling attacks, estimate their damage on boss turns 5-10, not just their baseline text.")
        lines.append("If a card strengthens an engine you already have, count it as immediate plan support even if future rewards are unknown.")
        lines.append("If above target, invest in defense, draw, relics, or save gold.")
        lines.append("If card removal costs more than 100g, prefer combat-improving cards, relics, or potions unless removing a Curse.")
        lines.append("")
        lines.append("Review your Build Plan in the Strategic Thread. Prioritize purchases that fill gaps.")

    # Card clarification notes
    if not config.PROMPT_HINT_FILTER:
        shop_card_names = [c.name for c in shop.cards if c.is_stocked]
        deck_names = [d.name for d in deck] if deck else []
        notes = format_card_notes(shop_card_names, deck_names)
        if notes:
            lines.append(notes)

    lines.append("")
    lines.append("## Your Task")
    lines.append("Plan ALL purchases for this shop visit in one decision.")
    lines.append("Order matters: items are bought first-to-last. Track gold after each purchase.")
    lines.append("")
    lines.append("For each affordable item you choose NOT to buy, explain why in skipped_items.")
    lines.append("")
    lines.append("Output format:")
    lines.append('```')
    lines.append('{')
    lines.append('  "purchases": [')
    lines.append('    {"action": "buy_card|buy_relic|buy_potion|remove_card|discard_potion",')
    lines.append('     "item_name": "exact name", "price": <int>,')
    lines.append('     "gold_after": <int>, "reason": "..."}')
    lines.append('  ],')
    lines.append('  "skipped_items": [')
    lines.append('    {"item_name": "...", "reason": "..."}')
    lines.append('  ],')
    lines.append('  "reasoning": "overall strategy",')
    lines.append('  "strategic_note": "plain prose current deck game plan, not JSON"')
    lines.append('}')
    lines.append('```')
    lines.append("")
    lines.append("Rules:")
    lines.append("- Gold math must be exact: start with current gold, subtract each price in order.")
    lines.append("- If you buy nothing, purchases = [] and list all affordable items in skipped_items.")
    lines.append(f"- Current gold: {gold}. Double-check gold_after values.")
    if removal and removal.available and not removal.used and removal.enough_gold:
        lines.append(f'- Schema for card removal purchase entries: action "remove_card", item_name "Card Removal", price {removal.price}.')
    if slot_blocked_potions:
        lines.append(
            '- Potion swap: to replace a held potion, emit TWO purchases in order — first '
            '{"action":"discard_potion","item_name":"<HELD potion name>","price":0}, '
            'then {"action":"buy_potion","item_name":"<shop potion name>","price":<price>}. '
            'discard_potion has no gold cost; item_name MUST match a currently held potion.'
        )

    # Regent-only: offering verdict — explicit Skip recommendation when
    # all stocked cards are C-tier-or-worse, so the LLM doesn't waste gold
    # on a bad card just because its raw stats look ok. Also overrides
    # S/A consumer recommendations when the deck is in star debt.
    shop_card_names = [c.name for c in shop.cards if c.is_stocked]
    verdict_lines = format_regent_offering_summary(
        shop_card_names, character, deck_state=_regent_deck_state,
    )

    # Append Glossary + Items For Sale + Verdict as the FINAL block — they
    # sit immediately before the ## Decision Format that v2_engine appends.
    lines.extend(glossary_lines)
    lines.extend(items_lines)
    lines.extend(verdict_lines)

    return "\n".join(lines)
