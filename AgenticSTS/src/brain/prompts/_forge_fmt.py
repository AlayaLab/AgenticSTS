"""Regent-only Sovereign Blade / Forge state block.

Sovereign Blade is the Regent's flagship combat-state pseudo-resource:
a 10-damage Colorless Token Attack that spawns when the first Forge card
is played in combat, and gains permanent damage from every subsequent
Forge play *across all piles* — but only on whichever copy is currently
"alive". Exhausting or transforming the buffed Blade resets all Forge
investment.

This formatter surfaces, in 3–6 prompt lines:
  * Sovereign Blade location (hand/draw/discard/exhaust/absent) + damage
    when in hand (its current damage IS the Forge stack value)
  * Forge cards still available to play (deck count)
  * Blade synergy + Blade buff cards present in deck
  * Active Forge-buff powers (Seeking Edge, Sword Sage)
  * Risk reminder when SB is in hand AND Forged (damage > base)

Returns an empty list for non-Regent runs, non-combat states, and Regent
combats that have neither a spawned Blade nor any Forge cards in deck —
so the block stays out of the way until the LLM actually has Forge
decisions to make.

Classification uses the same `classify_card` table from
`_regent_economy_fmt.py` (single source of truth, populated from
`src/skills/seeds/regent_card_notes.json`).
"""

from __future__ import annotations

from typing import Any

from src.brain.prompts._regent_economy_fmt import classify_card

SOVEREIGN_BLADE_CARD_ID = "sovereign_blade"
SOVEREIGN_BLADE_BASE_DAMAGE = 10

# Power IDs / names that count as Forge buffs (case-insensitive, normalized
# to snake_case for matching). Documented in the Phase 4.5 plan; expand here
# if upstream adds new Forge-stacking powers.
_FORGE_BUFF_POWER_KEYS: frozenset[str] = frozenset({
    "seeking_edge",
    "sword_sage",
})

# Listing cap so a heavily Forged deck doesn't blow the prompt budget.
_LIST_LIMIT = 5


def _norm_power_key(power: Any) -> str:
    """Normalize a power's id/name to snake_case lowercase for matching."""
    pid = getattr(power, "power_id", "") or ""
    if pid:
        return pid.strip().lower().replace(" ", "_")
    name = getattr(power, "name", "") or ""
    return name.strip().lower().replace(" ", "_")


def _find_blade_in_hand(hand: list[Any]) -> Any | None:
    for c in hand:
        if (getattr(c, "card_id", "") or "").lower() == SOVEREIGN_BLADE_CARD_ID:
            return c
    return None


def _find_blade_in_pile(pile: list[Any]) -> Any | None:
    for c in pile:
        if (getattr(c, "card_id", "") or "").lower() == SOVEREIGN_BLADE_CARD_ID:
            return c
    return None


def _truncate(items: list[str], limit: int = _LIST_LIMIT) -> str:
    if len(items) <= limit:
        return ", ".join(items)
    return f"{', '.join(items[:limit])} (+{len(items) - limit} more)"


def format_forge_state(gs: Any) -> list[str]:
    """Return Forge-state prompt lines (or [] when not applicable)."""
    if (getattr(gs, "character", None) or "").strip().lower() != "the regent":
        return []
    if not getattr(gs, "is_combat", False):
        return []

    raw = getattr(gs, "raw", None)
    combat = getattr(raw, "combat", None) if raw is not None else None
    if combat is None:
        return []
    player = getattr(combat, "player", None)
    if player is None:
        return []

    hand = getattr(combat, "hand", []) or []
    draw_pile = getattr(player, "draw_cards", []) or []
    discard_pile = getattr(player, "discard_cards", []) or []
    exhaust_pile = getattr(player, "exhaust_cards", []) or []

    sb_in_hand = _find_blade_in_hand(hand)
    sb_in_draw = _find_blade_in_pile(draw_pile)
    sb_in_discard = _find_blade_in_pile(discard_pile)
    sb_in_exhaust = _find_blade_in_pile(exhaust_pile)
    sb_present = any([sb_in_hand, sb_in_draw, sb_in_discard, sb_in_exhaust])

    deck = (getattr(raw, "run", None) and getattr(raw.run, "deck", None)) or []
    forge_cards: list[str] = []
    synergy_cards: list[str] = []
    buff_cards: list[str] = []
    for card in deck:
        name = (getattr(card, "name", "") or "").strip()
        if not name:
            continue
        _, forge_role = classify_card(name)
        if forge_role == "forge":
            forge_cards.append(name)
        elif forge_role == "blade_synergy":
            synergy_cards.append(name)
        elif forge_role == "blade_buff":
            buff_cards.append(name)

    # Quiet for non-Forge Regent runs (no Blade present, no Forge cards drafted).
    if not sb_present and not forge_cards:
        return []

    lines: list[str] = ["", "## Sovereign Blade"]

    # Status line
    if sb_in_hand is not None:
        damage = getattr(sb_in_hand, "damage", None)
        if damage is None:
            damage = SOVEREIGN_BLADE_BASE_DAMAGE
        forged = damage > SOVEREIGN_BLADE_BASE_DAMAGE
        flag = " (FORGED)" if forged else ""
        lines.append(f"Status: in_hand — current damage {damage}{flag}")
    elif sb_in_draw is not None:
        lines.append("Status: in draw pile (not yet drawn this round)")
    elif sb_in_discard is not None:
        lines.append("Status: in discard pile (will reshuffle into draw)")
    elif sb_in_exhaust is not None:
        lines.append(
            "Status: EXHAUSTED — next Forge will spawn a fresh 10-damage Blade. "
            "Prior Forge stacks are LOST."
        )
    else:
        lines.append("Status: not yet spawned — play a Forge card to summon (10 base damage).")

    # Deck-side context
    if forge_cards:
        lines.append(f"Forge cards in deck ({len(forge_cards)}): {_truncate(forge_cards)}")
    if synergy_cards:
        lines.append(f"Blade synergy ({len(synergy_cards)}): {_truncate(synergy_cards)}")
    if buff_cards:
        lines.append(f"Blade buffs ({len(buff_cards)}): {_truncate(buff_cards)}")

    # Active Forge-buff powers in current combat
    active_buffs: list[str] = []
    for power in getattr(player, "powers", []) or []:
        if _norm_power_key(power) in _FORGE_BUFF_POWER_KEYS:
            label = (getattr(power, "name", "") or getattr(power, "power_id", "") or "?").strip()
            amount = getattr(power, "amount", None)
            if amount is not None:
                label = f"{label} ({amount})"
            active_buffs.append(label)
    if active_buffs:
        lines.append(f"Active Forge buffs: {', '.join(active_buffs)}")

    # Risk warning when the Forged Blade is in hand and one bad play wipes the stack
    if sb_in_hand is not None:
        damage = getattr(sb_in_hand, "damage", None) or SOVEREIGN_BLADE_BASE_DAMAGE
        if damage > SOVEREIGN_BLADE_BASE_DAMAGE:
            lines.append(
                "Risk: do NOT exhaust or transform this Blade — Forge investment "
                "would reset to 10 dmg on the next spawn."
            )

    return lines
