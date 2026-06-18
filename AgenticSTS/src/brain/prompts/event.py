# ruff: noqa: E501
"""Prompt template for event decisions.

Multi-factor scoring framework for event option evaluation.
Includes rich option details (card effects, relic descriptions, potion info)
from the extended MCP event payload.
"""

from __future__ import annotations

import re

import config

from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.knowledge.knowledge import GameKnowledge
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState

_ENCHANT_BBCODE_RE = re.compile(r"\[purple\](.*?)\[/purple\]")
# Detect cards whose rules text actually Exhausts (excluding "Exhaust Pile" references).
_EXHAUST_CARD_RE = re.compile(r"\bExhaust(?!\s*Pile)", re.IGNORECASE)

# Localization-key shape: dotted identifier with at least 2 segments, no spaces.
# The mod's EnglishLocResolver returns the LocEntryKey verbatim when an entry is
# missing (e.g. NEOW has no static pages.INITIAL.description — Neow's flavor
# comes from dynamic talk dialogues). Drop these so they don't leak into prompts.
_LOC_KEY_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*){1,}$")


def _is_unresolved_loc_key(text: str) -> bool:
    return bool(_LOC_KEY_RE.fullmatch(text.strip()))


def _resolve_event_placeholders(text: str, opt) -> str:
    """Substitute {Card}/{Curse}/{Relic}/{Potion} from the option's offered lists.

    The mod's static description template still ships placeholders like
    `{Curse}` / `{Relic}` even though `cards_offered`/`relics_offered`/
    `curses_risk` are populated alongside it. Substitute them so the agent
    actually sees the names instead of empty gaps after the cleaner strips
    unresolved templates.
    """
    if opt is None:
        return text

    cards = getattr(opt, "cards_offered", None) or []
    relics = getattr(opt, "relics_offered", None) or []
    potions = getattr(opt, "potions_offered", None) or []
    curses = getattr(opt, "curses_risk", None) or []

    for card in cards:
        if not isinstance(card, dict):
            continue
        name = card.get("name")
        if not name:
            continue
        ctype = card.get("type", "")
        if ctype == "Curse":
            text = text.replace("{Curse}", name)
        elif ctype == "Status":
            text = text.replace("{Status}", name)
        else:
            text = text.replace("{Card}", name)
    for c in curses:
        if isinstance(c, str) and c:
            text = text.replace("{Curse}", c)
    for relic in relics:
        if isinstance(relic, dict) and relic.get("name"):
            text = text.replace("{Relic}", relic["name"])
    for potion in potions:
        if isinstance(potion, dict) and potion.get("name"):
            text = text.replace("{Potion}", potion["name"])
    return text


def _pick_option_text(opt) -> str:
    """Prefer the runtime-resolved effect_description over the static template."""
    eff = getattr(opt, "effect_description", "")
    if isinstance(eff, str) and eff.strip():
        return eff
    desc = getattr(opt, "description", "")
    return desc if isinstance(desc, str) else ""


def _clean_option_desc(raw: str, opt=None) -> str:
    """Strip BBCode and resolve {Template} placeholders from option text."""
    cleaned = strip_bbcode(raw)
    if opt is not None:
        cleaned = _resolve_event_placeholders(cleaned, opt)
    cleaned = re.sub(r"\{[A-Za-z]+\}", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip()


def _clean_option_title(title, opt) -> str:
    """Resolve {Relic}/{Card} placeholders in option titles."""
    if not isinstance(title, str):
        return title if title is not None else ""
    cleaned = _resolve_event_placeholders(title, opt)
    cleaned = re.sub(r"\{[A-Za-z]+\}", "", cleaned)
    return re.sub(r"\s{2,}", " ", cleaned).strip() or title


def _format_exhaust_cards_in_deck(deck: list[RawDeckCardPayload] | None) -> list[str]:
    """List deck cards that Exhaust — useful when an event enchants/targets them."""
    if not deck:
        return []
    seen: dict[str, str] = {}
    from src.brain.prompts._card_name import upgrade_suffix
    for c in deck:
        rules = (getattr(c, "resolved_rules_text", "") or c.rules_text or "")
        if not rules or not _EXHAUST_CARD_RE.search(strip_bbcode(rules)):
            continue
        display = c.name + upgrade_suffix(c)
        if display in seen:
            continue
        seen[display] = strip_bbcode(rules).replace("\n", " ")
    if not seen:
        return ["", "## Exhaust Cards in Deck", "  (none — no enchantable Exhaust target available)"]
    lines = ["", "## Exhaust Cards in Deck", "*Cards in your deck that Exhaust on play (candidates for Exhaust-related enchants).*"]
    for name, rules in seen.items():
        lines.append(f"  - {name}: {rules}")
    return lines


def _format_card_info(card: dict) -> str:
    """Format a single card info dict into a readable line."""
    name = card.get("name", "?")
    cost = card.get("cost", "?")
    ctype = card.get("type", "")
    rules = card.get("rules_text", "")
    parts = [f"{name}"]
    if cost != "?" or ctype:
        parts.append(f"(cost={cost}, {ctype})" if ctype else f"(cost={cost})")
    if rules:
        parts.append(f": {strip_bbcode(rules)}")
    return " ".join(parts)


def _format_relic_info(relic: dict) -> str:
    """Format a single relic info dict."""
    name = relic.get("name", "?")
    desc = relic.get("description", "")
    rarity = relic.get("rarity", "")
    parts = [name]
    if rarity:
        parts.append(f"({rarity})")
    if desc:
        parts.append(f"— {strip_bbcode(desc)}")
    return " ".join(parts)


def _format_potion_info(potion: dict) -> str:
    """Format a single potion info dict."""
    name = potion.get("name", "?")
    desc = potion.get("description", "")
    parts = [name]
    if desc:
        parts.append(f"— {strip_bbcode(desc)}")
    return " ".join(parts)


def _format_option_details(opt, kb: GameKnowledge | None = None) -> list[str]:
    """Build detail lines for a single event option's rewards/costs."""
    details: list[str] = []

    # Costs
    hp_cost = getattr(opt, "hp_cost", None)
    gold_cost = getattr(opt, "gold_cost", None)
    if isinstance(hp_cost, (int, float)) and hp_cost > 0:
        details.append(f"  HP cost: {hp_cost}")
    if isinstance(gold_cost, (int, float)) and gold_cost > 0:
        details.append(f"  Gold cost: {gold_cost}")

    # Cards
    cards = getattr(opt, "cards_offered", [])
    if isinstance(cards, list):
        for card in cards:
            if isinstance(card, dict):
                details.append(f"  Card: {_format_card_info(card)}")

    # Relics
    relics = getattr(opt, "relics_offered", [])
    if isinstance(relics, list):
        for relic in relics:
            if isinstance(relic, dict):
                details.append(f"  Relic: {_format_relic_info(relic)}")

    # Potions
    potions = getattr(opt, "potions_offered", [])
    if isinstance(potions, list):
        for potion in potions:
            if isinstance(potion, dict):
                details.append(f"  Potion: {_format_potion_info(potion)}")

    # Curses
    curses = getattr(opt, "curses_risk", [])
    if isinstance(curses, list) and curses:
        details.append(f"  Curse risk: {', '.join(str(c) for c in curses)}")

    # Enchantments — surfaced from the raw BBCode description so the LLM
    # can see effects like "this card no longer Exhausts" instead of just
    # the bare enchantment name. Prefer effect_description (runtime-resolved)
    # over description (static template with `{Enchantment}` placeholders).
    if kb is not None:
        raw_desc = _pick_option_text(opt)
        if raw_desc:
            seen: set[str] = set()
            for enc_name in _ENCHANT_BBCODE_RE.findall(raw_desc):
                if enc_name in seen:
                    continue
                seen.add(enc_name)
                enc = kb.enchantments.get(enc_name)
                if enc and enc.description:
                    enc_desc = strip_bbcode(enc.description)
                    details.append(f"  Enchantment — {enc_name}: {enc_desc}")

    return details


def _format_remaining_route(remaining_route: list[tuple[int, str]] | None) -> list[str]:
    """Format the upcoming map nodes so the agent knows what's ahead.

    Helps event decisions like "skip a card to heal HP" — if a rest site is
    next floor, healing is less valuable; if a boss is 2 nodes away with no
    rest in between, healing matters more.
    """
    if not remaining_route:
        return []
    parts = [f"F{floor} {node_type}" for floor, node_type in remaining_route]
    return ["", "## Path Ahead (planned route)", "  " + " → ".join(parts)]


def build_event_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    kb: GameKnowledge | None = None,
    remaining_route: list[tuple[int, str]] | None = None,
) -> str:
    """Build a prompt for event option selection with rich option details."""
    ev = gs.event
    if not ev:
        return ""

    lines = [
        "## Event",
        f"Event: {ev.title} (id={ev.event_id})",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    lines.extend(format_deck_section(deck, include_descriptions=True))

    # Relics with descriptions (combat-style block) — use structured gs.relics
    # so we get name + description directly. Falls back to the cached string
    # list when gs.relics is empty for any reason.
    if gs.relics:
        lines.append("")
        lines.append(f"## Relics ({len(gs.relics)})")
        for r in gs.relics:
            name = strip_bbcode(r.name)
            if r.description:
                desc = strip_bbcode(r.description)[:200]
                lines.append(f"- {name}: {desc}")
            else:
                lines.append(f"- {name}")
    elif relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    lines.extend(_format_remaining_route(remaining_route))

    if ev.description:
        body = strip_bbcode(ev.description)
        if not _is_unresolved_loc_key(body):
            if len(body) > 300:
                body = body[:297] + "..."
            lines.append("")
            lines.append(f"Description: {body}")

    # Build Glossary + Options into sub-lists; append them at the very end of
    # this builder's output so they sit immediately before the
    # ## Decision Format schema appended by v2_engine. The eval/guidance text
    # below is emitted to `lines` first, so the tail order becomes:
    #   eval guidance → Glossary → ## Options → (## Decision Format)
    glossary_lines: list[str] = []
    options_lines: list[str] = []
    options_lines.append("")
    options_lines.append("## Options")
    keyword_texts: list[str] = []
    mentions_exhaust = False
    for opt in ev.options:
        locked = " [LOCKED]" if opt.is_locked else ""
        proceed = " [PROCEED]" if opt.is_proceed else ""
        lethal = " [LETHAL]" if opt.will_kill_player else ""
        text = _pick_option_text(opt)
        desc = f": {_clean_option_desc(text, opt)}" if text else ""
        title = _clean_option_title(opt.title, opt)
        options_lines.append(f"- [index={opt.index}] {title}{desc}{locked}{proceed}{lethal}")

        # Rich option details from extended payload
        details = _format_option_details(opt, kb=kb)
        options_lines.extend(details)

        if text:
            stripped = strip_bbcode(text)
            keyword_texts.append(stripped)
            if _EXHAUST_CARD_RE.search(stripped):
                mentions_exhaust = True
        for card in getattr(opt, "cards_offered", []) or []:
            if isinstance(card, dict) and card.get("rules_text"):
                keyword_texts.append(strip_bbcode(card["rules_text"]))
        for relic in getattr(opt, "relics_offered", []) or []:
            if isinstance(relic, dict) and relic.get("description"):
                keyword_texts.append(strip_bbcode(relic["description"]))
        for potion in getattr(opt, "potions_offered", []) or []:
            if isinstance(potion, dict) and potion.get("description"):
                keyword_texts.append(strip_bbcode(potion["description"]))

    if mentions_exhaust:
        lines.extend(_format_exhaust_cards_in_deck(deck))

    glossary = format_keyword_glossary(keyword_texts)
    if glossary:
        glossary_lines.append("")
        glossary_lines.append(glossary)

    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append("Evaluate each option's risk vs reward. Consider HP cost, gold cost, and what you gain.")
        # Only show the deck-damage heuristic when an option actually offers a
        # playable card to add. Curses/Statuses are added to the deck but the
        # "needs more damage" framing doesn't apply to them.
        offers_addable_card = any(
            isinstance(c, dict) and c.get("type") not in ("Curse", "Status")
            for opt in ev.options
            for c in (getattr(opt, "cards_offered", []) or [])
        )
        if offers_addable_card:
            lines.append("If an option offers a card: consider whether your deck needs more damage to handle upcoming bosses (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns). Prefer damage/poison options when your deck's attack output is low.")

    # Append Glossary + Options as the FINAL block.
    lines.extend(glossary_lines)
    lines.extend(options_lines)

    return "\n".join(lines)
