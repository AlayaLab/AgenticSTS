"""Potion timing classification from description keywords.

Trade-off: _SUSTAINED_KEYWORDS is a keyword list (not a potion name list).
This is a deliberate choice: keywords like "Strength", "Dexterity" are game
MECHANICS, not card names. New potions that grant Strength auto-classify
correctly. This is fundamentally different from hardcoding "Strength Potion".
"""
from __future__ import annotations

from dataclasses import dataclass

_SUSTAINED_KEYWORDS = frozenset({
    "strength", "dexterity", "focus", "regeneration", "regen",
    "plated armor", "metallicize", "ritual", "thorns",
    "each turn", "per turn", "every turn",
})


@dataclass(frozen=True)
class PotionProfile:
    name: str
    timing: str  # "sustained" | "instant"
    boss_multiplier: float  # >1 for sustained (more value in long fights)


def classify_potion(name: str, description: str = "") -> PotionProfile:
    text = f"{name} {description}".lower()
    is_sustained = any(kw in text for kw in _SUSTAINED_KEYWORDS)
    return PotionProfile(
        name=name,
        timing="sustained" if is_sustained else "instant",
        boss_multiplier=3.0 if is_sustained else 1.0,
    )


def format_potion_tag(timing: str, combat_type: str, floors_to_boss: int = 0) -> str:
    if timing == "sustained":
        if combat_type == "boss":
            return "[SUSTAINED, USE NOW — maximum value in boss fight]"
        elif combat_type == "elite":
            return "[SUSTAINED, good here — elite fights are long]"
        else:
            return f"[SUSTAINED, save for boss/elite — {floors_to_boss} floors to boss]"
    return "[INSTANT]"
