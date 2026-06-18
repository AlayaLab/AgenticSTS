# ruff: noqa: E501
"""Prompt template for in-combat hand selection (discard, exhaust, etc).

Mode-aware selection framework. Exhaust and discard have fundamentally
different costs -- exhaust removes cards for the entire combat.
Designed for Qwen 3.5 9B -- explicit priority lists, not vague guidelines.
"""

from __future__ import annotations

import re as _re

import config

from src.brain.prompts._deck_fmt import strip_bbcode as _strip_bbcode
from src.brain.prompts._intent_fmt import (
    compute_total_incoming,
    format_enemy_intents,
    format_poison_hint,
    format_powers_inline,
)
from src.brain.prompts._keyword_fmt import format_keyword_glossary
from src.brain.prompts._card_name import upgrade_suffix
from src.state.game_state import GameState

_HAND_SELECTION_KINDS = frozenset({"hand", "combat_hand_select"})

# Patterns for cards that deal self-damage when held in hand
_HARMFUL_STATUS_RE = _re.compile(r"lose \d+ HP|take \d+ damage", _re.IGNORECASE)


def _payload_has_field(payload: object | None, field_name: str) -> bool:
    fields_set = getattr(payload, "model_fields_set", None)
    return isinstance(fields_set, set) and field_name in fields_set


def _selection_selectable_cards(sel) -> list:
    if not sel:
        return []
    if _payload_has_field(sel, "selectable_cards"):
        return list(sel.selectable_cards or [])
    return list(sel.cards or [])


def _selection_selected_cards(sel) -> list:
    if not sel:
        return []
    if _payload_has_field(sel, "selected_cards"):
        return list(sel.selected_cards or [])
    return [card for card in (sel.cards or []) if getattr(card, "is_selected", False)]


def _format_hand_cost(c) -> str:
    """Format energy cost for a selection card: 'X' if costs_x, else str(energy_cost)."""
    return "X" if c.costs_x else str(c.energy_cost)


def _format_card_line(c) -> str:
    """Format a single card line for display."""
    upgraded = upgrade_suffix(c)
    cost_str = _format_hand_cost(c)
    return f"- [index={c.index}] {c.name}{upgraded} ({c.card_type}, cost={cost_str}): {c.rules_text}"


def _render_selectable_cards_flat(selectable_cards) -> list[str]:
    """Render cards as a flat list without priority grouping.

    Used in the baseline ablation variant where strategy hints (Sly first /
    harmful first / non-harmful retain default) are stripped.
    """
    return [_format_card_line(c) for c in selectable_cards]


def _is_sly(c) -> bool:
    """True if card has the Sly keyword (starts with 'Sly.' in rules_text)."""
    return (c.rules_text or "").startswith("Sly.")


def _is_harmful_status(c) -> bool:
    """True if card is an unplayable status/curse that deals self-damage when held."""
    rt = c.rules_text or ""
    return bool(_HARMFUL_STATUS_RE.search(rt))


def build_hand_select_prompt(gs: GameState, *, combat_context: str = "") -> str:
    """Build a prompt for in-combat hand card selection.

    These screens appear when a card effect asks you to choose cards to
    discard, exhaust, put on top of draw pile, etc.
    """
    sel = gs.selection
    selectable_cards = _selection_selectable_cards(sel)
    selected_cards = _selection_selected_cards(sel)
    if not sel or not selectable_cards:
        return ""

    kind = sel.kind or ""
    kind_lower = kind.lower()

    # Only handle in-combat hand selections
    if kind not in _HAND_SELECTION_KINDS:
        return ""

    # If a choice has already been made and we can confirm, let the mechanical
    # handler finish it. Optional selections (min_select=0) may expose
    # confirm_selection before any card is chosen, and still need an LLM prompt.
    if sel.can_confirm and ((sel.selected_count or 0) > 0 or sel.min_select > 0):
        return ""

    is_exhaust = "exhaust" in kind_lower or "exhaust" in (sel.prompt or "").lower()
    is_discard = "discard" in kind_lower or "discard" in (sel.prompt or "").lower()
    is_retain = "retain" in (sel.prompt or "").lower()

    lines = [
        "## Hand Selection (In-Combat)",
        f"Mode: {kind}",
        f"Prompt: {_strip_bbcode(sel.prompt) if sel.prompt else kind}",
    ]

    if sel.min_select == 0:
        if is_retain:
            lines.append(
                f"Select: 0 to {sel.max_select} cards. "
                "IMPORTANT: Retained cards are FREE — you still draw your full 5 cards next turn. "
                "Default: retain every non-harmful card. "
                "Only skip a card if it is a Status/Curse or actively harmful to hold."
            )
        else:
            lines.append(
                f"Select: 0 to {sel.max_select} cards. Return ALL chosen indices in "
                "`selected_indices` array."
            )
            lines.append(
                "You may choose zero cards. If keeping nothing is best, respond with "
                "`{\"action\":\"confirm_selection\",\"reasoning\":\"...\"}`."
            )
    elif sel.min_select != sel.max_select:
        lines.append(f"Select: {sel.min_select} to {sel.max_select} cards. Return ALL indices in `selected_indices` array.")
    elif sel.max_select > 1:
        lines.append(f"Select: exactly {sel.max_select} cards. Return ALL {sel.max_select} indices in `selected_indices` array.")
    else:
        # min_select == max_select == 1 (most common: "Discard 1 card")
        lines.append("Select: exactly 1 card. Return its index as `selected_indices: [<index>]` array.")

    if gs.combat and gs.combat.player:
        p = gs.combat.player
        max_energy = gs.run_info.max_energy if gs.run_info and gs.run_info.max_energy else "?"
        stars_str = f" | Stars: {p.stars}" if p.stars else ""
        lines.append(
            f"Energy: {p.energy}/{max_energy}{stars_str} | "
            f"HP: {p.current_hp}/{p.max_hp} | Block: {p.block}"
        )
        if p.powers:
            lines.append(f"Player buffs/debuffs: {format_powers_inline(p.powers)}")

    # Show combat plan context if available (mid-combat selection)
    if combat_context:
        lines.append("")
        lines.append("## Combat Context")
        lines.append(combat_context)

    # Show enemies for context — same density as formal combat plan: index,
    # HP, poison hint, block, intent, and inline powers with descriptions.
    # Stale turn-plan reasoning in Combat Context must be contradictable by
    # the LIVE enemy state shown here.
    if gs.enemies:
        player_powers = gs.combat.player.powers if gs.combat and gs.combat.player.powers else None
        alive_enemies = [e for e in gs.enemies if getattr(e, "is_alive", True)]
        lines.append("")
        lines.append("## Enemies")
        for e in gs.enemies:
            intent_str = format_enemy_intents(e) if e.intents else "Unknown"
            poison_hint = format_poison_hint(e.powers, e.current_hp, player_powers)
            powers_suffix = ""
            if e.powers:
                powers_suffix = " | powers: " + format_powers_inline(e.powers)
            block_part = f", Block {e.block}" if getattr(e, "block", 0) else ""
            lines.append(
                f"- {e.name} [index={e.index}]: "
                f"HP {e.current_hp}/{e.max_hp}{poison_hint}{block_part}, "
                f"Intent: {intent_str}{powers_suffix}"
            )

        if gs.combat and gs.combat.player and alive_enemies:
            total_incoming = compute_total_incoming(alive_enemies)
            effective_incoming = max(0, total_incoming - gs.combat.player.block)
            lines.append(
                f"Incoming damage: {total_incoming} "
                f"(after block: {effective_incoming}) | Your HP: {gs.combat.player.current_hp}"
            )

    # Build Glossary + Cards You Can Select into sub-lists; append them at
    # the very end of this builder's output so they sit immediately before
    # the ## Decision Format schema appended by v2_engine. Tactical Flags +
    # Already Selected + mode hint are emitted first to `lines`.
    glossary_lines: list[str] = []
    options_lines: list[str] = []

    card_texts = [c.rules_text or "" for c in selectable_cards]
    glossary = format_keyword_glossary(card_texts)
    if glossary:
        glossary_lines.append(glossary)

    # ── Cards You Can Select ──────────────────────────────────
    options_lines.append("")
    options_lines.append("## Cards You Can Select")

    if config.PROMPT_VARIANT == "baseline":
        options_lines.extend(_render_selectable_cards_flat(selectable_cards))
    elif is_discard:
        # Priority-grouped card listing for discard mode
        sly_lines = []
        harmful_lines = []
        other_lines = []
        for c in selectable_cards:
            line = _format_card_line(c)
            if _is_sly(c):
                sly_lines.append(line)
            elif _is_harmful_status(c):
                harmful_lines.append(line)
            else:
                other_lines.append(line)

        if sly_lines:
            options_lines.append("### Discard FIRST — plays for free")
            options_lines.extend(sly_lines)
        if harmful_lines:
            options_lines.append("### Discard SECOND — remove harmful cards")
            options_lines.extend(harmful_lines)
        if other_lines:
            options_lines.append("### Other")
            options_lines.extend(other_lines)
    elif is_retain:
        # Priority-grouped for retain mode (inverse: flag what NOT to keep)
        skip_lines = []
        keep_lines = []
        for c in selectable_cards:
            line = _format_card_line(c)
            if _is_harmful_status(c) or c.card_type in ("Status", "Curse"):
                skip_lines.append(line)
            else:
                keep_lines.append(line)

        if skip_lines:
            options_lines.append("### Do NOT retain — harmful/status/curse")
            options_lines.extend(skip_lines)
        if keep_lines:
            options_lines.append("### Retain these — more options next turn")
            options_lines.extend(keep_lines)
    else:
        # Flat listing for exhaust/other modes
        for c in selectable_cards:
            options_lines.append(_format_card_line(c))

    # ── Tactical Flags ────────────────────────────────────────
    if config.PROMPT_VARIANT != "baseline":
        tactical_flags: list[str] = []

        sly_cards = [c.name for c in selectable_cards if _is_sly(c)]
        if sly_cards and is_discard:
            tactical_flags.append(
                f"PRIORITY: Discard a Sly card ({', '.join(sly_cards)}) to play it for FREE. "
                "You must discard THE SLY CARD ITSELF — discarding other cards does NOT trigger Sly."
            )
        elif sly_cards:
            tactical_flags.append(
                f"Sly cards: {', '.join(sly_cards)}. "
                "Discarding these by a card effect PLAYS them for free."
            )

        # Detect countdown-management cards (e.g. Frantic Escape increases Sandpit).
        # If the enemy has a Sandpit power (death countdown), these cards must NOT be discarded.
        sandpit_cards = [
            c.name
            for c in selectable_cards
            if "sandpit" in (c.rules_text or "").lower()
        ]
        if sandpit_cards:
            tactical_flags.append(
                f"!! DEATH COUNTDOWN CARDS: {', '.join(sandpit_cards)} manage Sandpit. "
                "Sandpit on the enemy counts down to 0 = INSTANT DEATH. "
                "Check Enemy powers in Combat Context — if Sandpit <= 2, do NOT discard these!"
            )

        if tactical_flags:
            lines.append("")
            lines.append("## Tactical Flags")
            for flag in tactical_flags:
                lines.append(flag)

    if sel.selected_count > 0:
        lines.append("")
        lines.append(f"## Already Selected: {sel.selected_count} card(s)")
        for card in selected_cards:
            lines.append(f"- {card.name}{upgrade_suffix(card)}")

    # Compact mode-aware hint
    lines.append("")
    if is_exhaust:
        if config.PROMPT_VARIANT == "baseline":
            lines.append("Exhaust = GONE forever this combat.")
        else:
            lines.append("Exhaust = GONE forever this combat. Exhaust Curses/Status first, then Strikes, then worst cards. Never exhaust your key scaling cards.")
    elif is_discard:
        lines.append(
            "Discard = temporary (you'll draw them again). "
            "If an Ethereal Status or Curse card has no harmful effect while held "
            "(e.g. Ascender's Bane), DO NOT discard it — let it auto-exhaust at end of "
            "turn so it's permanently gone this combat instead of being reshuffled "
            "into the draw pile."
        )
    elif is_retain:
        if config.PROMPT_VARIANT == "baseline":
            lines.append(
                "Retain = keep for next turn (free extras — you still draw 5 normally; hand cap 10)."
            )
        else:
            lines.append(
                "Retain = keep for next turn. Retained cards are FREE EXTRAS — "
                "you still draw your full 5 cards normally (hand limit 10). "
                "Retain every non-harmful card unless there is a specific reason not to. "
                "Do NOT retain: Status cards, Curses, cards that deal self-damage."
            )
    else:
        lines.append(f'This is a "{kind}" selection. Pick what you need least.')

    # Append Glossary + Cards You Can Select as the FINAL block.
    lines.extend(glossary_lines)
    lines.extend(options_lines)

    return "\n".join(lines)
