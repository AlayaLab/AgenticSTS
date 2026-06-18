"""Power/buff/debuff description lookup from static powers.json.

Provides O(1) lookup of power descriptions by power_id.
Data source: STS2 game data (260 powers with descriptions).
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

# ── Singleton data ────────────────────────────────────────

_POWERS: dict[str, dict[str, Any]] = {}
_LOADED = False

# Manual overrides for powers with missing/useless decompiled descriptions.
# Key: power_id (uppercase). Value: corrected description text.
_DESCRIPTION_OVERRIDES: dict[str, str] = {
    "SANDPIT": (
        "DEATH TIMER. Decreases by 1 each turn. "
        "When Sandpit reaches 0, YOU DIE INSTANTLY. "
        "Play Frantic Escape cards to add Sandpit stacks and survive longer. "
        "You MUST kill The Insatiable before Sandpit runs out!"
    ),
    "STEAM_ERUPTION": (
        "When this enemy dies, deals damage equal to the stack count "
        "to you at the end of your NEXT turn. Plan your block accordingly!"
    ),
    "OUTBREAK": (
        "Every 10 times you apply Poison, deal damage equal to the stack count "
        "to ALL enemies."
    ),
    "POISON": (
        "Loses N HP at the start of its turn, before it acts (attack or buff), "
        "then Poison decreases by 1. Bypasses Block."
    ),
    "SMOGGY": (
        "While Smoggy is active, you can only play 1 Skill card per turn. "
        "Prioritize Attack cards instead. Decreases by 1 each turn."
    ),
    "ASLEEP": (
        "Awakens upon losing HP or after N turns. "
        "While Asleep, the enemy does NOT act — free damage window. "
        "But waking it via damage triggers its first attack — burst it down or stay above its hit."
    ),
}


def _ensure_loaded() -> None:
    global _POWERS, _LOADED
    if _LOADED:
        return

    data_path = Path(__file__).resolve().parents[2] / "data" / "knowledge" / "powers.json"
    if data_path.exists():
        with open(data_path, encoding="utf-8") as f:
            raw = json.load(f)
        for p in raw:
            pid = p.get("id", "")
            if pid:
                _POWERS[pid.upper()] = p
    _LOADED = True


def _strip_bbcode(text: str) -> str:
    """Remove BBCode tags like [blue], [gold], [/blue], etc."""
    return re.sub(r"\[/?(?:blue|gold|red|green|purple|white|gray|yellow)\]", "", text)


# Placeholder phrases that upstream data and the C# mod sometimes emit when the
# real description is missing. We must not let these leak into prompts.
_PLACEHOLDER_FRAGMENTS: tuple[str, ...] = (
    "a power used by",
    "see game ui for details",
)
# Whole-string placeholders the game devs left as stubs in localization
# (e.g. ASLEEP_POWER.description == "TODO" in eng/powers.json).
_PLACEHOLDER_EXACT: frozenset[str] = frozenset({"todo", "tbd"})

# Unresolved Godot template tokens like '{energyPrefix:energyIcons(1)}' or
# '{IfUpgraded:show:Card+|Card}' — the C# mod sometimes hands us raw text
# instead of the game-rendered version.
_TEMPLATE_TOKEN_RE = re.compile(r"\{[A-Za-z_][^}]*\}")


def _is_placeholder_description(text: str) -> bool:
    if not text:
        return True
    lowered = text.strip().lower()
    if lowered in _PLACEHOLDER_EXACT:
        return True
    return any(frag in lowered for frag in _PLACEHOLDER_FRAGMENTS)


def _sanitize_runtime_description(text: str) -> str:
    """Strip unresolved Godot template tokens and tidy whitespace.

    Used when the runtime description is mostly meaningful but contains a
    stray '{token:args}' the mod failed to render. Returns the residual text
    after token removal — callers should re-check :func:`_is_placeholder_description`
    to decide whether the residue is still useful.
    """
    cleaned = _TEMPLATE_TOKEN_RE.sub("", text)
    cleaned = re.sub(r"\s{2,}", " ", cleaned)
    return cleaned.strip()


# ── Public API ────────────────────────────────────────────

def get_power_description(power_id: str) -> str | None:
    """Get a clean description for a power by its ID.

    Manual overrides take precedence over decompiled data for powers
    with missing or useless descriptions.
    Returns None if the power is not found.
    """
    key = power_id.upper()
    # Check overrides first (hand-curated accurate descriptions)
    override = _DESCRIPTION_OVERRIDES.get(key)
    if override:
        return override

    _ensure_loaded()
    p = _POWERS.get(key)
    if p is None:
        return None
    desc = p.get("description", "")
    if not desc:
        return None
    clean = _strip_bbcode(desc)
    # Skip useless placeholder descriptions from decompiled source
    if clean and not _is_placeholder_description(clean):
        return clean
    return None


def get_power_info(power_id: str) -> dict[str, Any] | None:
    """Get full power info dict (id, name, description, type, stack_type)."""
    _ensure_loaded()
    return _POWERS.get(power_id.upper())


def format_power_with_description(
    name: str,
    amount: int | None,
    power_id: str = "",
    description: str = "",
) -> str:
    """Format a power for prompt injection: 'Name(amount): description'.

    If no power_id given, tries matching by uppercased name.
    Falls back to just 'Name(amount)' if no description found.
    """
    desc = description.strip()
    # Runtime descriptions from the C# mod can be the upstream placeholder
    # ("A power used by X.", localization-stub "TODO") for powers whose
    # game-side resolver has no real text. Treat those as missing so the
    # override / static lookup runs and the curated description
    # (e.g. SANDPIT death-timer warning) is used.
    if _is_placeholder_description(desc):
        desc = ""
    elif desc:
        # Real text but may contain stray unresolved tokens like
        # '{energyPrefix:energyIcons(1)}'. Strip those — keep the surrounding
        # sentence. Re-check placeholder in case the residue is empty.
        sanitized = _sanitize_runtime_description(desc)
        desc = "" if _is_placeholder_description(sanitized) else sanitized
    if not desc:
        lookup_key = power_id.upper() if power_id else name.upper().replace(" ", "_")
        desc = get_power_description(lookup_key)
        # C# mod sends power_id like "SmoggyPower" or "ASLEEP_POWER" but DB
        # keys are "SMOGGY" / "ASLEEP". Strip common suffixes (and the
        # trailing separator left behind, e.g. "ASLEEP_POWER" → "ASLEEP_"
        # → "ASLEEP") and retry.
        if desc is None and lookup_key:
            for suffix in ("POWER", "BUFF", "DEBUFF"):
                if lookup_key.endswith(suffix):
                    candidate = lookup_key[: -len(suffix)].rstrip("_")
                    desc = get_power_description(candidate)
                    if desc:
                        break
        # Last resort: try name-based lookup
        if desc is None:
            desc = get_power_description(name.upper().replace(" ", "_"))

    amount_str = f"({amount})" if amount is not None else ""
    if desc:
        return f"{name}{amount_str}: {desc}"
    return f"{name}{amount_str}"


def format_powers_section(
    powers: list[Any],
    label: str = "Buffs/Debuffs",
) -> str:
    """Format a list of power payloads into a prompt section.

    Each power should have: name, amount, power_id (optional), is_debuff (optional).
    Returns empty string if no powers.
    """
    if not powers:
        return ""

    lines: list[str] = []
    for p in powers:
        if isinstance(p, dict):
            name = p.get("name", "")
            amount = p.get("amount")
            pid = p.get("power_id", "")
            desc = p.get("description", "")
        else:
            name = getattr(p, "name", "")
            amount = getattr(p, "amount", None)
            pid = getattr(p, "power_id", "")
            desc = getattr(p, "description", "")

        formatted = format_power_with_description(name, amount, pid, desc)
        lines.append(f"  - {formatted}")

    if not lines:
        return ""
    return f"  {label}:\n" + "\n".join(lines)
