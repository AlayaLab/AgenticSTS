# ruff: noqa: E501
"""Prompt template for card selection decisions (enchant, upgrade, remove, transform).

Card selection for upgrade, remove, enchant, and transform screens.
4-dimension evaluation with post-removal function checks for remove mode.
"""

from __future__ import annotations

import config

from src.brain.prompts._deck_fmt import format_deck_section
from src.brain.prompts._regent_economy_fmt import format_regent_economy
from src.brain.prompts._deck_fmt import strip_bbcode as _strip_bbcode
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.brain.prompts._card_name import upgrade_suffix
from src.mcp_client.upstream_models import (
    RawDeckCardPayload,
    RawSelectionCardPayload,
    get_damage_block_from_dynamic_values,
)
from src.state.game_state import GameState


def _payload_has_field(payload: object | None, field_name: str) -> bool:
    fields_set = getattr(payload, "model_fields_set", None)
    return isinstance(fields_set, set) and field_name in fields_set


def _selection_selectable_cards(selection) -> list[RawSelectionCardPayload]:
    if not selection:
        return []
    if _payload_has_field(selection, "selectable_cards"):
        return list(selection.selectable_cards or [])
    return list(selection.cards or [])


def _selection_selected_cards(selection) -> list[RawSelectionCardPayload]:
    if not selection:
        return []
    if _payload_has_field(selection, "selected_cards"):
        return list(selection.selected_cards or [])
    return [card for card in (selection.cards or []) if getattr(card, "is_selected", False)]


def _format_selection_cost(c) -> str:
    """Format energy cost for a selection card: 'X' if costs_x, else str(energy_cost)."""
    return "X" if c.costs_x else str(c.energy_cost)


def _lookup_upgrade_info(card_name: str, knowledge: object | None) -> str:
    """Look up upgrade effect for a card from the knowledge DB.

    Returns a compact hint or empty string.  The raw ``on_upgrade``
    field is C# DSL (e.g. ``UpgradeValueBy(2m)``).  We translate
    common patterns to readable text.
    """
    if knowledge is None:
        return ""
    cards_lookup = getattr(knowledge, "cards", None)
    if cards_lookup is None:
        return ""
    base_name = card_name.rstrip("+").strip()
    card_data = cards_lookup.get(base_name)
    if card_data is None or not card_data.on_upgrade:
        return ""

    raw = card_data.on_upgrade
    # Translate common DSL patterns to readable text
    import re
    readable_parts: list[str] = []
    for part in raw.split(", "):
        part = part.strip()
        m = re.match(r"UpgradeValueBy\((\d+)m?\)", part)
        if m:
            readable_parts.append(f"+{m.group(1)} to a value")
            continue
        m = re.match(r"UpgradeCostBy\((-?\d+)m?\)", part)
        if m:
            readable_parts.append(f"cost {m.group(1)}")
            continue
        # Fallback: include raw DSL (LLM can sometimes interpret it)
        readable_parts.append(part)

    return f" → UPGRADE: {'; '.join(readable_parts)}" if readable_parts else ""


def _format_choice_card_line(c: RawSelectionCardPayload) -> str:
    upgraded = upgrade_suffix(c)
    cost_str = _format_selection_cost(c)
    display_text = (getattr(c, "resolved_rules_text", "") or c.rules_text or "").strip()
    base_line = f"{c.name}{upgraded} ({cost_str}E, {c.rarity}): {display_text}"
    dvs = getattr(c, "dynamic_values", None) or []
    if dvs:
        d, b, h = get_damage_block_from_dynamic_values(dvs)
        val_parts = []
        if d is not None:
            val_parts.append(f"{d} dmg")
        if b is not None and b > 0:
            val_parts.append(f"{b} block")
        if h is not None and h > 1:
            val_parts.append(f"x{h} hits")
        if val_parts:
            base_line += f" [{' | '.join(val_parts)}]"
    return base_line


def build_pack_selection_prompt(
    gs: GameState,
    *,
    pack_previews: dict[int, list[RawSelectionCardPayload]],
    current_pack_index: int | None,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    cs = gs.selection
    pack_cards = _selection_selectable_cards(cs)
    if not cs or not pack_cards:
        return ""

    lines = [
        "## Pack Selection",
        f"Prompt: {_strip_bbcode(cs.prompt) if cs.prompt else 'Choose one pack'}",
        f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold}",
        f"Act: {gs.act} | Floor: {gs.floor}",
    ]

    if gs.character:
        lines.append(f"Character: {gs.character}")

    current_pack = None
    if current_pack_index is not None:
        current_pack = next((card for card in pack_cards if card.index == current_pack_index), None)
    if current_pack is not None:
        lines.append(
            "Current preview/selection: "
            f"[{current_pack.index}] {current_pack.name}"
        )

    lines.append("")
    lines.append(
        "Choose exactly one pack. If the CURRENT previewed pack is best, use "
        "`confirm_selection`. Otherwise use `select_deck_card` with the better pack's index."
    )

    lines.extend(format_deck_section(deck))
    lines.extend(format_regent_economy(deck, getattr(gs, "character", "") or ""))

    if relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    lines.append("")
    lines.append("## Pack Options")
    for pack in pack_cards:
        lines.append(f"- [{pack.index}] {_format_choice_card_line(pack)}")
        preview_cards = pack_previews.get(pack.index, [])
        if preview_cards:
            lines.append("  Contains:")
            for preview in preview_cards:
                lines.append(f"  - {_format_choice_card_line(preview)}")
        else:
            lines.append("  Contains: preview unavailable")

    glossary = format_keyword_glossary(
        [card.rules_text for cards in pack_previews.values() for card in cards]
    )
    if glossary:
        lines.append(glossary)

    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        lines.append(
            "Prefer the pack that best fits the deck's current win condition, curve, and act survival."
        )
    return "\n".join(lines)


def build_card_select_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    *,
    knowledge: object | None = None,
    combat_context: str = "",
) -> str:
    """Build a prompt for card selection screens (enchant, upgrade, remove, etc).

    These screens appear from events, rest sites, and certain relics.
    The LLM picks one card from the offered list.
    """
    cs = gs.selection
    selectable_cards = _selection_selectable_cards(cs)
    selected_cards = _selection_selected_cards(cs)
    if not cs or not selectable_cards:
        return ""

    # Skip in-combat hand selections -- those are handled by hand_select.py
    if (cs.kind or "") in {"hand", "combat_hand_select"}:
        return ""

    # If can_confirm AND cards are already selected, the mechanical handler
    # should confirm — don't prompt the LLM again.
    # NOTE: some selection kinds (e.g. deck_card_select from Demon Glass)
    # have can_confirm=True from the start with selected_count=0.
    if cs.can_confirm and getattr(cs, "selected_count", 0) > 0:
        return ""

    # Detect mode from kind AND prompt (prompt carries the real intent for
    # generic kinds like "deck_card_select")
    kind = cs.kind or ""
    prompt_text = _strip_bbcode(cs.prompt).lower() if cs.prompt else ""
    kind_lower = kind.lower()
    is_upgrade = "upgrade" in kind_lower or "smith" in kind_lower or "upgrade" in prompt_text
    is_remove = "remove" in kind_lower or "purge" in kind_lower or "remove" in prompt_text
    mode = "UPGRADE" if is_upgrade else "REMOVE" if is_remove else kind.upper() or "SELECT"

    # Detect character
    character = gs.character or ""

    lines = [
        "## Card Selection",
        f"Mode: **{mode}** | Screen: {cs.kind}",
        f"Prompt: {_strip_bbcode(cs.prompt) if cs.prompt else mode}",
        f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")
    if character:
        lines.append(f"Character: {character}")

    # Show combat plan context if available (mid-combat selection)
    if combat_context:
        lines.append("")
        lines.append("## Combat Context")
        lines.append(combat_context)

    # Determine required count: API field → prompt text fallback
    import re
    effective_max = cs.max_select if cs.max_select and cs.max_select > 0 else 0
    effective_min = cs.min_select if cs.min_select else 0
    if effective_max == 0 and cs.prompt:
        clean_prompt = re.sub(r"\[/?[a-zA-Z_]+\]", "", cs.prompt)
        # "any number of cards" → variable selection
        if re.search(r"any\s+number\s+of\s+card", clean_prompt, re.IGNORECASE):
            effective_min = 0
            effective_max = len(selectable_cards) if selectable_cards else 1
        else:
            m = re.search(r"[Cc]hoose\s+(\d+)\s+card", clean_prompt)
            if m:
                effective_max = int(m.group(1))
    # "any number" selection: min=0, max=N
    if effective_min == 0 and effective_max > 1:
        lines.append(
            f"Select: 0 to {effective_max} cards. Pick only cards that fit your deck's win condition. "
            f"Return chosen indices in `selected_indices` array. You may skip (confirm with 0) if nothing fits."
        )
    elif effective_max > 1:
        lines.append(f"Select: exactly {effective_max} cards. Return ALL {effective_max} indices in `selected_indices` array in one call.")
    elif cs.min_select and cs.min_select != cs.max_select:
        lines.append(f"Select: {cs.min_select} to {cs.max_select} cards")

    lines.extend(format_deck_section(deck))
    lines.extend(format_regent_economy(deck, getattr(gs, "character", "") or ""))

    if relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    # Build Glossary + Available Cards into sub-lists; append them at the very
    # end of this builder's output so they sit immediately before the
    # ## Decision Format schema appended by v2_engine. The Already Selected
    # block + guidance text are emitted first to `lines`.
    glossary_lines: list[str] = []
    options_lines: list[str] = []

    card_texts = [c.rules_text for c in selectable_cards]
    glossary = format_keyword_glossary(card_texts)
    if glossary:
        glossary_lines.append(glossary)

    options_lines.append("")
    options_lines.append("## Available Cards")
    for c in selectable_cards:
        upgraded = upgrade_suffix(c)
        cost_str = _format_selection_cost(c)
        # Use resolved_rules_text (v0.5.3+) for fully-substituted values, fall back to raw rules_text
        display_text = (getattr(c, "resolved_rules_text", "") or c.rules_text or "").strip()
        base_line = f"- [{c.index}] {c.name}{upgraded} ({cost_str}E, {c.rarity}): {display_text}"
        # Inject dynamic value tag: [9 dmg | 5 block | x3 hits] (v0.5.3+)
        dvs = getattr(c, "dynamic_values", None) or []
        if dvs:
            d, b, h = get_damage_block_from_dynamic_values(dvs)
            val_parts = []
            if d is not None:
                val_parts.append(f"{d} dmg")
            if b is not None and b > 0:
                val_parts.append(f"{b} block")
            if h is not None and h > 1:
                val_parts.append(f"x{h} hits")
            if val_parts:
                base_line += f" [{' | '.join(val_parts)}]"
        # In upgrade mode, append what the upgrade actually does
        if is_upgrade and knowledge:
            upgrade_info = _lookup_upgrade_info(c.name, knowledge)
            if upgrade_info:
                base_line += upgrade_info
        options_lines.append(base_line)

    if selected_cards:
        lines.append("")
        lines.append(f"## Already Selected: {len(selected_cards)} card(s)")
        for c in selected_cards:
            lines.append(f"- {_format_choice_card_line(c)}")

    # Compact guidance
    if config.PROMPT_VARIANT != "baseline":
        lines.append("")
        if is_upgrade:
            lines.append("Upgrade: pick biggest dimension boost (cost reduction > doubled dmg/block > added draw). Never upgrade basic Strike/Defend.")
        elif is_remove:
            lines.append("Remove: Curses/Statuses first, then weakest card. Check deck still functions after removal (enough damage + defense). Don't over-thin.")
        else:
            lines.append("Pick the card most central to your win condition.")

    # Append Glossary + Available Cards as the FINAL block.
    lines.extend(glossary_lines)
    lines.extend(options_lines)

    return "\n".join(lines)
