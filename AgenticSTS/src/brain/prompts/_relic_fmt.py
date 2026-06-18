"""Shared relic synergy formatting for LLM prompts.

Maps known relic names to their strategic implications and provides
context-aware hint injection. Token-efficient: only includes relics
relevant to the current decision type.
"""

from __future__ import annotations

from typing import Sequence

from src.brain.prompts._deck_fmt import strip_bbcode
from src.knowledge.knowledge import GameKnowledge

# ---------------------------------------------------------------------------
# Relic effects database
# ---------------------------------------------------------------------------
# Each entry maps a relic name (case-insensitive key) to a dict with:
#   "hint"  : short strategic implication (1 sentence)
#   "tags"  : which decision contexts benefit from this hint
#             Valid tags: "combat", "rest", "map", "shop", "reward", "event"

RELIC_EFFECTS: dict[str, dict] = {
    # --- Energy / Draw (S-tier universals) ---
    "bag of preparation": {
        "hint": "+2 card draw at combat start — front-load your best plays turn 1.",
        "tags": ["combat", "reward"],
    },
    "ice cream": {
        "hint": "Unspent energy carries over — save energy for big turns.",
        "tags": ["combat"],
    },
    "lantern": {
        "hint": "+1 energy on turn 1 — play an extra card to establish tempo.",
        "tags": ["combat"],
    },
    "happy flower": {
        "hint": "+1 energy every 3 turns — plan big plays on those turns.",
        "tags": ["combat"],
    },

    # --- Starting relics (character identity) ---
    "burning blood": {
        "hint": "Heals 6 HP after each combat — be more aggressive, take riskier paths.",
        "tags": ["rest", "map", "shop", "combat"],
    },
    "ring of the snake": {
        "hint": "Draw 2 extra cards turn 1 — front-load damage and debuffs.",
        "tags": ["combat", "reward"],
    },
    "cracked core": {
        "hint": "Channel 1 Lightning at combat start — free chip damage every fight.",
        "tags": ["combat"],
    },
    "divine right": {
        "hint": (
            "Gain 3 Stars at combat start. Stars persist across rounds within "
            "a fight (no per-turn reset) but DO clear at combat end. Spend "
            "opportunistically on Star-cost cards when their effect beats the "
            "energy-only line; don't burn Stars on suboptimal targets when "
            "energy alone covers the turn."
        ),
        "tags": ["combat"],
    },
    "bound phylactery": {
        "hint": "Summon Osty each turn — Osty absorbs damage, keep him alive.",
        "tags": ["combat"],
    },

    # --- Rest site relics ---
    "dream catcher": {
        "hint": "Resting gives a card reward — rest is less wasteful (rest value UP).",
        "tags": ["rest"],
    },
    "regal pillow": {
        "hint": "Rest heals +15 HP — resting is more efficient (rest value UP).",
        "tags": ["rest"],
    },
    "meat cleaver": {
        "hint": "Can Cook at rest: remove 2 cards + gain 9 max HP — powerful deck-thinning option.",
        "tags": ["rest"],
    },
    "girya": {
        "hint": "Can Lift at rest: gain 1 Strength (up to 3) — consider Lift on safe turns.",
        "tags": ["rest"],
    },
    "shovel": {
        "hint": "Can Dig at rest: find a relic — very high value if HP is safe.",
        "tags": ["rest"],
    },
    "peace pipe": {
        "hint": "Can Toke at rest: remove a card — deck thinning without gold cost.",
        "tags": ["rest"],
    },
    "miniature tent": {
        "hint": "Can perform multiple rest actions — much higher rest site value.",
        "tags": ["rest"],
    },

    # --- Map routing relics ---
    "juzu bracelet": {
        "hint": "No monster fights in ? rooms — ? rooms are safe to visit.",
        "tags": ["map"],
    },
    "maw bank": {
        "hint": "Gain 12 gold per non-shop location — avoid shops to bank gold.",
        "tags": ["map", "shop"],
    },
    "meal ticket": {
        "hint": "Heal 15 HP when visiting a shop — path toward shops for free healing.",
        "tags": ["map", "shop"],
    },
    "prayer wheel": {
        "hint": "Extra card reward after combat — monster fights give more value.",
        "tags": ["map", "reward"],
    },
    "pantograph": {
        "hint": "Heal 25 HP at boss start — can enter boss at lower HP safely.",
        "tags": ["map", "rest"],
    },
    "meat on the bone": {
        "hint": "Heal 12 HP after combat if below 50% HP — aggressive play is safer.",
        "tags": ["map", "combat"],
    },

    # --- Shop relics ---
    "membership card": {
        "hint": "50% discount on all shop purchases — shops are extremely efficient.",
        "tags": ["shop", "map"],
    },
    "the courier": {
        "hint": "Shop items restock on purchase + 20% discount — buy more at shops.",
        "tags": ["shop", "map"],
    },
    "old coin": {
        "hint": "Gained 300 gold — can afford expensive shop items.",
        "tags": ["shop"],
    },

    # --- Combat relics ---
    "vajra": {
        "hint": "+1 Strength — all attacks deal 1 extra damage (multi-hit scales).",
        "tags": ["combat", "reward"],
    },
    "pen nib": {
        "hint": "Every 10th attack deals double damage — track and time big attacks.",
        "tags": ["combat"],
    },
    "mercury hourglass": {
        "hint": "Deal 3 damage to all enemies each turn — free passive AoE.",
        "tags": ["combat"],
    },
    "anchor": {
        "hint": "Gain 10 Block at combat start — safe turn 1.",
        "tags": ["combat"],
    },
    "orichalcum": {
        "hint": "Gain 6 Block at end of turn if you have 0 Block — skip blocking on safe turns.",
        "tags": ["combat"],
    },
    "red skull": {
        "hint": "+3 Strength when below 50% HP — low HP = more damage.",
        "tags": ["combat", "rest"],
    },
    "tungsten rod": {
        "hint": "Reduce all HP loss by 1 — chip damage and multi-hit attacks hurt less.",
        "tags": ["combat", "map"],
    },
    "bronze scales": {
        "hint": "Deal 3 damage to attacker when hit — punishes multi-hit enemies.",
        "tags": ["combat"],
    },
    "kunai": {
        "hint": "+1 Dexterity per 3 attacks played — spam attacks for scaling Block.",
        "tags": ["combat", "reward"],
    },
    "shuriken": {
        "hint": "+1 Strength per 3 attacks played — spam attacks for scaling damage.",
        "tags": ["combat", "reward"],
    },
    "ornamental fan": {
        "hint": "Gain 4 Block per 3 attacks played — multi-attack turns generate defense.",
        "tags": ["combat"],
    },
    "lizard tail": {
        "hint": "Revive at 50% HP on death (once) — you have a safety net.",
        "tags": ["map", "combat"],
    },
    "self-forming clay": {
        "hint": "Gain 3 Block when losing HP — taking hits builds defense.",
        "tags": ["combat"],
    },
    "chemical x": {
        "hint": "+2 to all X-cost cards — Whirlwind/Multi-Cast become much stronger.",
        "tags": ["combat", "reward"],
    },
    "pocketwatch": {
        "hint": "Draw 3 extra if you played 3 or fewer cards last turn — reward low-play turns.",
        "tags": ["combat"],
    },
    "stone calendar": {
        "hint": "Deal 52 damage to all enemies at end of turn 7 — long fights have a finisher.",
        "tags": ["combat"],
    },
}

# Build a case-insensitive lookup
_RELIC_LOOKUP: dict[str, dict] = {k.lower(): v for k, v in RELIC_EFFECTS.items()}

_CONTEXT_KEYWORDS: dict[str, list[str]] = {
    "combat": [
        "damage", "block", "attack", "enemy", "hit", "kill",
        "strength", "dexterity", "energy", "card", "play", "turn",
    ],
    "rest": ["rest", "heal", "hp", "smith", "upgrade", "max hp"],
    "map": ["map", "path", "route", "floor", "room", "elite", "boss", "event"],
    "shop": ["gold", "buy", "shop", "price", "cost", "discount", "remove"],
    "reward": ["card", "reward", "relic", "upgrade", "add"],
    "event": ["event", "option", "choice", "gold", "hp"],
}


def format_relic_hints(
    relics: Sequence[str],
    context: str = "",
) -> str:
    """Format relic strategic hints for prompt injection.

    Parameters
    ----------
    relics:
        List of relic names the player currently has.
    context:
        Decision context filter. One of: "combat", "rest", "map", "shop",
        "reward", "event". If empty, all matching relics are included.

    Returns
    -------
    A short "## Relic Synergies" section string, or empty string if no
    relevant relics are found.
    """
    if not relics:
        return ""

    hints: list[str] = []
    for relic_entry in relics:
        # Relics may be "Name (description)" — extract name for lookup
        relic_name = relic_entry.split(" (")[0] if " (" in relic_entry else relic_entry
        relic_name = strip_bbcode(relic_name).strip()
        entry = _RELIC_LOOKUP.get(relic_name.lower().strip())
        if entry is None:
            continue
        # Filter by context tag if specified
        if context and context not in entry["tags"]:
            continue
        hints.append(f"- **{relic_name}**: {entry['hint']}")

    # Fallback: upstream descriptions for non-curated relics
    if len(hints) < 6:
        try:
            upstream = GameKnowledge.get_instance().relics
        except Exception:
            upstream = None
        if upstream and upstream.count > 0:
            ctx_kws = _CONTEXT_KEYWORDS.get(context, [])
            for relic_str in relics:
                if len(hints) >= 6:
                    break
                rname = relic_str.split(" (")[0].strip()
                if rname.lower() in _RELIC_LOOKUP:
                    continue  # already handled by curated hints
                rk = upstream.get(rname)
                if rk and rk.description:
                    clean_desc = strip_bbcode(rk.description)
                    desc_lower = clean_desc.lower()
                    if not context or any(kw in desc_lower for kw in ctx_kws):
                        hints.append(f"- **{strip_bbcode(rk.name)}**: {clean_desc}")

    if not hints:
        return ""

    # Cap at 6 hints to stay within ~100 tokens
    if len(hints) > 6:
        hints = hints[:6]

    lines = ["", "## Relic Synergies"]
    lines.extend(hints)
    return "\n".join(lines)
