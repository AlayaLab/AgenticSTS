# ruff: noqa: E501
"""Prompt template for rest site decisions.

Hybrid approach: Version A's structured scoring framework + Version B's
strategic conviction and concrete examples. Designed for Qwen 3.5 9B.
"""

from __future__ import annotations

import config

from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.brain.prompts._regent_economy_fmt import format_regent_economy
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.brain.prompts._relic_fmt import format_relic_hints
from src.brain.prompts._card_name import upgrade_suffix
from src.mcp_client.upstream_models import (
    RawDeckCardPayload,
    RawSelectionCardPayload,
    get_damage_block_from_dynamic_values,
)
from src.state.game_state import GameState


def _format_smith_card_line(c: RawSelectionCardPayload) -> tuple[str, str]:
    """Format current + upgraded card lines from Smith card_select data.

    Returns (current_line, upgraded_line).
    """
    cost_str = "X" if c.costs_x else str(c.energy_cost)
    desc = strip_bbcode(
        (c.resolved_rules_text or c.rules_text or "").strip()
    ).replace("\n", " ").strip()

    current = f"[{c.index}] {c.name} ({cost_str}E, {c.card_type}, {c.rarity}): {desc}"

    dvs = c.dynamic_values or []
    if dvs:
        d, b, h = get_damage_block_from_dynamic_values(dvs)
        parts = []
        if d is not None:
            parts.append(f"{d} dmg")
        if b is not None and b > 0:
            parts.append(f"{b} block")
        if h is not None and h > 1:
            parts.append(f"x{h} hits")
        if parts:
            current += f" [{' | '.join(parts)}]"

    # Upgraded preview from MCP
    upg_desc = c.upgrade_preview_description
    if upg_desc:
        upg_desc = strip_bbcode(upg_desc.strip()).replace("\n", " ").strip()
        upg_cost = str(c.upgrade_preview_cost) if c.upgrade_preview_cost is not None else cost_str
        upgraded = f"  → {c.name}+ ({upg_cost}E): {upg_desc}"
    else:
        upgraded = ""

    return current, upgraded


def _build_smith_preview_section(
    smith_cards: list[RawSelectionCardPayload],
) -> list[str]:
    """Build the Smith preview section from actual game card_select data."""
    if not smith_cards:
        return ["", "## Smith — Upgradeable Cards", "No upgradeable cards available."]

    lines = ["", "## Smith — Upgradeable Cards"]
    card_texts: list[str] = []

    for c in smith_cards:
        current, upgraded = _format_smith_card_line(c)
        lines.append(f"- {current}")
        if upgraded:
            lines.append(upgraded)
        desc = strip_bbcode(
            (c.resolved_rules_text or c.rules_text or "").strip()
        )
        if desc:
            card_texts.append(desc)

    # Keyword glossary
    glossary = format_keyword_glossary(card_texts)
    if glossary:
        lines.append("")
        lines.append(glossary)

    return lines


def build_rest_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    *,
    upcoming_nodes: list[str] | None = None,
    remaining_route: list[tuple[int, str]] | None = None,
    smith_cards: list[RawSelectionCardPayload] | None = None,
) -> str:
    """Build a prompt for rest site option selection.

    *smith_cards*: if provided, the actual card data fetched from the game's
    Smith card_select screen via MCP.  Shown as an upgrade preview section
    so the LLM can make an informed rest-vs-smith decision.
    """
    rest = gs.rest
    if not rest:
        return ""

    lines = [
        "## Rest Site",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    # Detect boss/elite proximity from both upcoming_nodes and remaining_route
    boss_imminent = False
    elite_imminent = False

    # Source 1: upcoming map nodes (sibling nodes at last map screen)
    if upcoming_nodes:
        node_types_lower = [n.lower() for n in upcoming_nodes]
        if any("boss" in n for n in node_types_lower):
            boss_imminent = True
        elif any(n == "elite" for n in node_types_lower):
            elite_imminent = True

    # Source 2: remaining route (more reliable — shows actual path ahead)
    rest_floors: list[int] = []
    if remaining_route:
        # Check if boss is within 1-2 nodes AND no rest before it
        remaining_types = [nt.lower() for _, nt in remaining_route]
        for i, nt in enumerate(remaining_types):
            if "rest" in nt:
                rest_floors.append(remaining_route[i][0])
        has_boss_ahead = any("boss" in nt for nt in remaining_types)
        # Boss with no rest between here and boss → imminent
        if has_boss_ahead and not rest_floors:
            boss_imminent = True

    if boss_imminent:
        heal_amt = int(gs.player_max_hp * 0.3)
        healed = min(gs.player_hp + heal_amt, gs.player_max_hp)
        missing = gs.player_max_hp - gs.player_hp
        lines.append("")
        lines.append("⚠ **BOSS FIGHT AHEAD — NO MORE REST SITES!**")
        lines.append(f"Healing: +{heal_amt} HP → {healed}/{gs.player_max_hp} (missing {missing})")
        if missing >= heal_amt:
            if config.PROMPT_VARIANT != "baseline":
                lines.append("Healing uses the full amount with no overflow. You should heal before the boss fight.")
        elif missing >= heal_amt * 0.5:
            if config.PROMPT_VARIANT != "baseline":
                lines.append("Your deck is mostly finalized. Healing gives you more margin to survive the boss. Strongly consider healing unless HP is already near full.")
        else:
            if config.PROMPT_VARIANT != "baseline":
                lines.append("HP is relatively healthy. Smith if there is a high-impact upgrade target; otherwise heal to top off.")
    elif elite_imminent:
        heal_amt = int(gs.player_max_hp * 0.3)
        healed = min(gs.player_hp + heal_amt, gs.player_max_hp)
        lines.append("")
        if config.PROMPT_VARIANT != "baseline":
            lines.append(f"⚠ **ELITE FIGHT NEXT** — Healing restores {heal_amt} HP (to {healed}). Weigh that against upgrading a card for every remaining combat.")
        else:
            lines.append(f"Healing restores {heal_amt} HP (to {healed}).")

    if remaining_route:
        lines.append("")
        lines.append("## Upcoming Path (from route plan)")
        path_parts = []
        for floor_num, node_type in remaining_route:
            path_parts.append(f"F{floor_num}: {node_type}")
        lines.append(" → ".join(path_parts))
        rest_count = len(rest_floors)
        if rest_count > 0:
            rest_locs = ", ".join(f"F{f}" for f in rest_floors)
            lines.append(f"Rest sites remaining before boss: {rest_count} (at {rest_locs})")
            lines.append("You can smith now and heal later, or heal now and smith later.")
        else:
            lines.append("No rest sites remaining before boss. This is your last chance to upgrade or heal.")

    lines.extend(format_deck_section(deck))
    lines.extend(format_regent_economy(deck, getattr(gs, "character", "") or ""))

    # Smith preview: actual game card data from MCP
    if smith_cards is not None:
        lines.extend(_build_smith_preview_section(smith_cards))

    if not config.PROMPT_HINT_FILTER:
        relic_section = format_relic_hints(relics or [], context="rest")
        if relic_section:
            lines.append(relic_section)

    # Clone option: list enchanted cards explicitly so the LLM knows what duplicates
    has_clone_option = any(
        (opt.option_id or "").upper() == "CLONE" and opt.is_enabled
        for opt in rest.options
    )
    if has_clone_option and deck:
        clone_cards = [
            c for c in deck
            if ((getattr(c, "enchantment_id", None) or "").upper() == "CLONE"
                or (getattr(c, "enchantment_name", None) or "").lower() == "clone")
        ]
        lines.append("")
        lines.append("## Clone-Enchanted Cards (used by the Clone option)")
        if clone_cards:
            names = sorted(
                c.name + upgrade_suffix(c) for c in clone_cards
            )
            lines.append(
                f"{len(clone_cards)} card(s) carry the Clone enchantment: "
                + ", ".join(names)
            )
            lines.append(
                "Clone duplicates ALL of them at this rest site. "
                "Each future rest visit doubles again (exponential growth), "
                "so the cloned count can snowball across acts."
            )
        else:
            lines.append(
                "No cards currently carry the Clone enchantment — "
                "this option would add nothing."
            )

    lines.append("")
    lines.append("## Options")
    for opt in rest.options:
        enabled = "+" if opt.is_enabled else "x (disabled)"
        opt_desc = strip_bbcode(opt.description or "")
        lines.append(f"- [index={opt.index}] {opt.title} {enabled}: {opt_desc}")

    # Check if rest options are all disabled (already used)
    if gs.can_proceed:
        lines.append("")
        lines.append("NOTE: You have already used a rest option. You MUST proceed now.")
        lines.append('Respond: {"action": "proceed", "params": {}, "reasoning": "..."}')
    else:
        heal_amt = int(gs.player_max_hp * 0.3)
        missing = gs.player_max_hp - gs.player_hp
        lines.append("")
        if boss_imminent:
            lines.append(f"Healing restores {heal_amt} HP ({missing} HP currently missing).")
            if config.PROMPT_VARIANT != "baseline":
                lines.append("Boss is next — HP matters more than one more upgrade. Heal unless already near full HP.")
        elif gs.player_hp < 30:
            lines.append(f"⚠ **HP CRITICAL ({gs.player_hp}/{gs.player_max_hp})** — Healing restores {heal_amt} HP ({missing} HP currently missing).")
            if config.PROMPT_VARIANT != "baseline":
                lines.append("At this HP level, you are at serious risk of dying in the next combat. Prioritize healing over upgrading.")
        else:
            lines.append(f"Healing restores {heal_amt} HP ({missing} HP currently missing).")
            if config.PROMPT_VARIANT != "baseline":
                lines.append("Review the Smith upgradeable cards above to assess Smith value. Choose based on which option provides more long-term value for this run.")

        # Smith shortcut: if upgrade cards are shown, LLM can pick one directly
        if smith_cards:
            lines.append("")
            lines.append("**If you choose Smith**, include `smith_card_index` with the card's `[index]` from the Upgradeable Cards list above.")
            lines.append('Example: {"action": "choose_rest_option", "option_index": <smith_index>, "smith_card_index": <card_index>, "reasoning": "..."}')

    return "\n".join(lines)
