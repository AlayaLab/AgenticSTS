"""Shared intent formatting helpers for combat prompts.

Uses structured intent fields (damage, hits, total_damage) when available,
falling back to fragile label parsing for backward compatibility with
older mod versions.
"""

from __future__ import annotations

import re

from src.knowledge.power_lookup import format_power_with_description
from src.mcp_client.upstream_models import (
    RawCombatEnemyIntentPayload,
    RawCombatEnemyPayload,
    RawCombatPowerPayload,
)


def format_powers_inline(powers: list[RawCombatPowerPayload]) -> str:
    """Format powers into a comma-separated line with descriptions.

    Matches the combat plan's enemy/player power formatting so selection
    prompts (hand_select, card_select) carry the same context density.
    """
    if not powers:
        return ""
    return ", ".join(
        format_power_with_description(
            power.name,
            power.amount,
            getattr(power, "power_id", ""),
            getattr(power, "description", ""),
        )
        for power in powers
    )


def _get_power_amount(powers: list[RawCombatPowerPayload], power_id: str) -> int:
    """Return the amount of a power by power_id (e.g. 'POISON', 'ACCELERANT')."""
    for pw in powers:
        if pw.power_id == power_id:
            return pw.amount or 0
    return 0


def compute_poison_effective_hp(
    enemy_hp: int,
    poison_stacks: int,
    accelerant_stacks: int = 0,
) -> int | None:
    """Enemy HP remaining after poison ticks at the start of their turn.

    With Accelerant(N), poison triggers N+1 times total.
    Each tick: deal current_poison damage, then poison -= 1.

    Returns effective HP (>= 0), or None if no poison.
    """
    if poison_stacks <= 0:
        return None
    total_damage = 0
    remaining = poison_stacks
    for _ in range(accelerant_stacks + 1):
        if remaining <= 0:
            break
        total_damage += remaining
        remaining -= 1
    return max(0, enemy_hp - total_damage)


def format_poison_hint(
    enemy_powers: list[RawCombatPowerPayload],
    enemy_hp: int,
    player_powers: list[RawCombatPowerPayload] | None = None,
) -> str:
    """Return a short annotation like ' (→6 after poison)' or '' if no poison."""
    poison = _get_power_amount(enemy_powers, "POISON")
    if poison <= 0:
        return ""
    acc = _get_power_amount(player_powers, "ACCELERANT") if player_powers else 0
    eff = compute_poison_effective_hp(enemy_hp, poison, acc)
    if eff is None:
        return ""
    if eff <= 0:
        return " (dies to poison)"
    return f" (→{eff} after poison)"


def compute_intent_damage(intent: RawCombatEnemyIntentPayload) -> int:
    """Extract total damage from a single intent.

    Prefers structured total_damage field, falls back to damage*hits,
    then to label string parsing as last resort.
    """
    if intent.intent_type != "Attack":
        return 0

    # Prefer structured fields
    if intent.total_damage is not None:
        return intent.total_damage
    if intent.damage is not None:
        hits = intent.hits if intent.hits is not None else 1
        return intent.damage * hits

    # Fallback: parse label string (e.g. "12", "3x8")
    if intent.label:
        try:
            label = intent.label.replace(" ", "")
            if "x" in label.lower():
                parts = label.lower().split("x")
                return int(parts[0]) * int(parts[1])
            return int(label)
        except (ValueError, IndexError):
            pass
    return 0


def compute_total_incoming(enemies: list[RawCombatEnemyPayload]) -> int:
    """Sum total incoming damage across all alive enemies."""
    return sum(
        compute_intent_damage(i)
        for e in enemies if e.is_alive
        for i in e.intents
    )


def format_intent(intent: RawCombatEnemyIntentPayload) -> str:
    """Format a single intent for display in prompts.

    Uses structured fields for precise output, label as fallback.
    """
    itype = intent.intent_type

    if itype == "Attack":
        if intent.damage is not None:
            hits = intent.hits if intent.hits is not None else 1
            if hits > 1:
                return f"Attack({intent.damage}x{hits}={intent.damage * hits})"
            return f"Attack({intent.damage})"
        if intent.label:
            return f"Attack({intent.label})"
        return "Attack(?)"

    if itype == "Status" and intent.status_card_count is not None:
        label = intent.label or "Status"
        return f"{itype}({label}, {intent.status_card_count} cards)"

    # Generic: Buff, Debuff, Defend, Unknown, etc.
    if intent.label:
        return f"{itype}({intent.label})"
    return itype


def format_enemy_intents(enemy: RawCombatEnemyPayload) -> str:
    """Format all intents for an enemy into a comma-separated string."""
    return ", ".join(format_intent(i) for i in enemy.intents)


_MOVE_ID_RE = re.compile(r"\b[A-Z][A-Z0-9_]*_MOVE\b")
_NUMERIC_RE = re.compile(r"^\d+$")


def is_move_id_like(text: str | None) -> bool:
    """Return True when a string looks like an internal move id."""
    if not text:
        return False
    return bool(_MOVE_ID_RE.search(text))


def normalize_legacy_intent_text(text: str | None) -> str:
    """Normalize legacy single-string intent text for memory storage.

    Returns an empty string for raw move ids so callers can fall back to a
    safer source instead of persisting opaque debug identifiers.
    """
    if not text:
        return ""

    normalized = " ".join(text.strip().split())
    if not normalized or is_move_id_like(normalized):
        return ""
    if _NUMERIC_RE.fullmatch(normalized):
        return f"Attack({normalized})"
    return normalized


def format_enemy_intents_for_memory(
    enemy: RawCombatEnemyPayload,
    *,
    fallback_intent: str | None = None,
) -> str:
    """Format an enemy intent string suitable for memory snapshots."""
    if enemy.intents:
        parts = [format_intent(i) for i in enemy.intents if format_intent(i)]
        if parts:
            return ", ".join(parts)

    for candidate in (fallback_intent, enemy.intent):
        normalized = normalize_legacy_intent_text(candidate)
        if normalized:
            return normalized

    return "Unknown"
