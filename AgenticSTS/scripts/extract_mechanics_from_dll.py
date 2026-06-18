"""Extract enchantment mechanic descriptions from the STS2 game DLL using ilspycmd.

Outputs data/knowledge/upstream/mechanics_dll.json — a name→description dict
consumed by _keyword_fmt.py as a fallback for mechanics not in KW_GLOSSARY.

Run automatically at agent startup when the DLL is newer than the cache.

Usage:
    python -m scripts.extract_mechanics_from_dll
    python -m scripts.extract_mechanics_from_dll --dll-path /path/to/sts2.dll
    python -m scripts.extract_mechanics_from_dll --force
"""
from __future__ import annotations

import argparse
import json
import logging
import re
import subprocess
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# ── Paths ──────────────────────────────────────────────────────────────────────

DEFAULT_DLL = Path(
    "C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/"
    "data_sts2_windows_x86_64/sts2.dll"
)
OUTPUT = Path("data/knowledge/upstream/mechanics_dll.json")
ILSPY = "ilspycmd"

ENCHANTMENT_NS = "MegaCrit.Sts2.Core.Models.Enchantments"
AFFLICTION_NS = "MegaCrit.Sts2.Core.Models.Afflictions"
CARDS_NS = "MegaCrit.Sts2.Core.Models.Cards"
POWERS_NS = "MegaCrit.Sts2.Core.Models.Powers"
_SKIP_CLASSES = {"DeprecatedEnchantment"}

# Powers we treat as glossary keywords (mechanic explainers). Boss-specific and
# character-lineage powers are intentionally excluded — they're either too niche
# or already encoded in KW_GLOSSARY. Add sparingly; every entry widens the
# glossary match surface.
_POWER_WHITELIST = {
    "FocusPower",           # Scholar core: boosts orb passive/evoke
    "TemporaryFocusPower",  # Turn-local Focus
    "RegenPower",           # Heal at end of turn, counter ticks down
    "RitualPower",          # Gain Strength at end of turn
    "ThornsPower",          # Reflect damage on hit
    "BarricadePower",       # Block persists across turns
    "BufferPower",          # Prevent next HP loss
    "EnvenomPower",         # Unblocked attack applies Poison
    "InfiniteBladesPower",  # Start of turn: add a Shiv
    "BurstPower",           # Next Skill plays twice
    "DuplicationPower",     # Next card plays twice
    "NoxiousFumesPower",    # Start of turn: apply Poison to all enemies
    "AccelerantPower",      # Poison triggers an extra time
    "AccuracyPower",        # Shivs deal more damage
}

# Intent-level mechanics (Stun, Asleep, etc.) have no clean `*Model` class —
# Stun is applied via `CreatureCmd.Stun()`. For these we emit a hardcoded line
# keyed off the localization id. Keeping the list tight; keys must also appear
# in card rules_text to trigger.
_INTENT_MECHANIC_LINES: dict[str, str] = {
    "stun": (
        "Stun: The stunned enemy cannot act on its next turn. "
        "Applied by a handful of Silent/Regent skills and some rest-site options."
    ),
    "stunned": (
        "Stunned: The affected enemy cannot act on its next turn. "
        "Equivalent to Stun; text may render as either form."
    ),
}

# Upstream-extracted affliction localization (authoritative text the game shows
# on cards). Sourced from Slay the Spire 2's Godot .pck resource pack. We merge
# this with class-level metadata from the DLL (stackable flag, has-extra-text).
_AFFLICTIONS_LOC = Path(
    "../AgenticSTS-Mod/mcp_server/data/eng/afflictions.json"
)
_AFFLICTION_SKIP_IDS = {
    "MOCK_NO_UNPLAYABLE_AFFLICTION",
    "MOCK_SELF_DAMAGE_AFFLICTION",
    "MOCK_USELESS_AFFLICTION",
}
# Extra behavioral notes observed in the DLL for afflictions whose localization
# text does not mention the mechanic that actually enforces the rule. E.g. Bound
# itself is a marker affliction; the "only 1 Bound card per turn" rule lives in
# ChainsOfBindingPower.ShouldPlay, and BeforeTurnEnd clears all Bound cards.
_AFFLICTION_EXTRA_NOTES: dict[str, str] = {
    "bound": (
        "Applied by Chains of Binding: the first N drawn cards each turn are "
        "Bound."
    ),
}

# ── Behavioral pattern → description ──────────────────────────────────────────

def _parse_enchantment_description(class_name: str, code: str) -> str:
    """Generate a one-line English description from decompiled enchantment C# code."""
    c = code

    # Replay: EnchantPlayCount adds extra plays
    if "EnchantPlayCount" in c:
        if "_usedThisCombat" in c or "UsedThisCombat" in c:
            return (
                f"{class_name}: The first time this card is played each combat, "
                "it plays 1 additional time (2 plays total)."
            )
        return (
            f"{class_name}: This card plays 1 additional time when played "
            "(all effects trigger for each play)."
        )

    # Damage multiplier (Favored = 2x, Corrupted = 1.5x)
    # The method has an early-exit `return 1m;` for non-powered attacks, then the
    # real multiplier. Take the largest non-1.0 value to get the actual effect.
    if "EnchantDamageMultiplicative" in c:
        all_returns = re.findall(r"return\s+([\d.]+)m;", c)
        mult = max((float(v) for v in all_returns), default=0.0)
        if mult == 2.0:
            desc = f"{class_name}: Powered attacks deal double damage."
        elif mult == 1.5:
            desc = f"{class_name}: Powered attacks deal 50% more damage."
        elif mult > 1.0:
            desc = f"{class_name}: Powered attacks deal {mult}x damage."
        else:
            desc = f"{class_name}: Modifies attack damage."
        # Corrupted also self-damages
        if "Unpowered" in c and "Unblockable" in c and "Damage(" in c:
            m2 = re.search(r"(\d+)m,\s*ValueProp\.Unblockable", c)
            if m2:
                desc += f" Also deals {m2.group(1)} unblockable damage to you when played."
        return desc

    # Damage additive (Sharp, Momentum, Vigorous, Inky)
    if "EnchantDamageAdditive" in c and "EnchantBlockAdditive" not in c:
        accumulate = "ExtraDamage" in c or "_extraDamage" in c
        once = "EnchantmentStatus.Disabled" in c
        powered_only = "IsPoweredAttack()" in c
        show_amount = "ShowAmount => true" in c

        # Compound effect: OnPlay applies a Power to the target (Inky → Weak).
        onplay_power_m = re.search(
            r"OnPlay\b[\s\S]*?PowerCmd\.Apply<(\w+)Power>",
            c,
        )
        onplay_power = onplay_power_m.group(1) if onplay_power_m else None

        # ShowAmount=false hides the stack count in the UI; describe with the
        # fixed numeric values from CanonicalVars instead of an "N" placeholder.
        fixed_damage: int | None = None
        fixed_power_amount: int | None = None
        if not show_amount:
            m = re.search(r"new\s+DamageVar\(\s*(-?[\d.]+)m?", c)
            if m:
                try:
                    fixed_damage = int(float(m.group(1)))
                except ValueError:
                    pass
            m = re.search(r"new\s+PowerVar<\w+Power>\(\s*(-?[\d.]+)m?", c)
            if m:
                try:
                    fixed_power_amount = int(float(m.group(1)))
                except ValueError:
                    pass

        name_token = f"{class_name} N" if show_amount else class_name
        dmg_n = str(fixed_damage) if fixed_damage is not None else "N"

        if accumulate:
            damage_clause = (
                f"Each time played this combat, deals {dmg_n} more damage "
                "(accumulates until end of combat)"
            )
        elif once:
            damage_clause = (
                f"The first time played in a combat, deals {dmg_n} extra damage"
            )
        elif powered_only:
            damage_clause = f"Powered attacks deal {dmg_n} additional damage"
        else:
            damage_clause = f"Deals {dmg_n} additional damage"

        if onplay_power:
            pwr_n = str(fixed_power_amount) if fixed_power_amount is not None else "N"
            return (
                f"{name_token}: When played, apply {pwr_n} {onplay_power} to target. "
                f"{damage_clause}."
            )
        return f"{name_token}: {damage_clause}."

    # Block additive (Adroit, Nimble, Goopy)
    if "EnchantBlockAdditive" in c or ("OnPlay" in c and "GainBlock" in c):
        if "AfterCardPlayed" in c and "Amount++" in c:
            return (
                f"{class_name}: Gains Exhaust; gains more Block each time it's played "
                "(Block bonus grows permanently)."
            )
        if "OnPlay" in c and "GainBlock" in c:
            return f"{class_name} N: When played, gain N Block."
        return f"{class_name} N: Gains N extra Block when played."

    # Slither: randomizes cost when drawn (SetThisCombat to a random 0-3 value)
    if "AfterCardDrawn" in c and "SetThisCombat" in c and "NextInt" in c:
        return f"{class_name}: When drawn, this card gets a random energy cost (0-3) for this combat turn."

    # Keyword additions/removals
    # AddKeyword form: base.Card.AddKeyword(CardKeyword.X)
    # RemoveKeyword form: CardCmd.RemoveKeyword(base.Card, CardKeyword.X)
    added_kws: list[str] = re.findall(r'AddKeyword\(CardKeyword\.(\w+)\)', c)
    removed_kws: list[str] = re.findall(r'RemoveKeyword\([^)]*CardKeyword\.(\w+)\)', c)

    if "UpgradeBy(-" in c and "Eternal" in added_kws:
        return (
            f"{class_name}: Sets this card's cost to 0 and grants Eternal "
            "(cannot be removed from deck)."
        )
    if added_kws and not removed_kws:
        return f"{class_name}: Grants this card {' and '.join(added_kws)}."
    if removed_kws and not added_kws:
        return f"{class_name}: Removes {' and '.join(removed_kws)} from this card."

    # Cost reduction
    if "UpgradeBy(-1)" in c and "EnergyCost" in c and "AfterCardDrawn" not in c:
        return f"{class_name}: This card costs 1 less energy (permanent)."
    if "AfterCardDrawn" in c and ("AddUntilPlayed" in c or "GetEnergyCost" in c):
        return f"{class_name}: Costs 0 energy on the turn it is drawn into your hand."
    if "BeforeFlush" in c and "AddUntilPlayed" in c:
        return (
            f"{class_name}: Costs 1 less energy for each turn it remains in hand "
            "unplayed (stacks, resets when played)."
        )

    # Auto-play (Imbued)
    if "AfterPlayerTurnStart" in c and "AutoPlay" in c:
        return f"{class_name}: Automatically plays at the start of your first turn in combat."

    # Draw once (Swift)
    if "OnPlay" in c and "Draw(" in c and "EnchantmentStatus.Disabled" in c:
        return f"{class_name} N: The first time played, draw N cards."

    # Energy gain once (Sown)
    if "OnPlay" in c and "GainEnergy" in c and "EnchantmentStatus.Disabled" in c:
        return f"{class_name} N: The first time played, gain N energy."

    # Shuffle positioning (PerfectFit)
    if "ModifyShuffleOrder" in c and "Insert(0" in c:
        return f"{class_name}: Moves to the top of your draw pile after each shuffle."

    # Clone (empty class body)
    if class_name == "Clone" and c.count("public override") == 0:
        return "Clone: Creates a copy of this card and adds it to your hand."

    # Generic fallback: list behavioral methods
    overrides = re.findall(r'public override\s+\S+\s+(\w+)\(', c)
    if overrides:
        return f"{class_name}: Card enchantment (behaviors: {', '.join(dict.fromkeys(overrides))})."
    return f"{class_name}: Card enchantment (see game UI for details)."


# ── Affliction extraction ──────────────────────────────────────────────────────

_BBCODE_TAG = re.compile(r"\[/?[a-z]+\]")
_ENERGY_TAG = re.compile(r"\[energy:(\d+)\]")
_AMOUNT_PLACEHOLDER = re.compile(r"\[Amount\]")


def _strip_bbcode(text: str) -> str:
    """Strip Godot-style BBCode markup used in localization strings."""
    text = _ENERGY_TAG.sub(lambda m: f"{m.group(1)} energy", text)
    text = _AMOUNT_PLACEHOLDER.sub("N", text)
    text = _BBCODE_TAG.sub("", text)
    return re.sub(r"\s+", " ", text).strip()


def _load_upstream_afflictions() -> dict[str, dict]:
    """Load and index the upstream-extracted afflictions localization.

    Returns a dict keyed by the affliction's lowercase short name (e.g. "bound").
    Silently returns {} if the upstream file is not present.
    """
    if not _AFFLICTIONS_LOC.exists():
        logger.debug("Upstream afflictions file missing: %s", _AFFLICTIONS_LOC)
        return {}
    try:
        entries = json.loads(_AFFLICTIONS_LOC.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.warning("Could not parse %s: %s", _AFFLICTIONS_LOC, exc)
        return {}
    indexed: dict[str, dict] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        if entry.get("id") in _AFFLICTION_SKIP_IDS:
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            continue
        indexed[name.lower().replace(" ", "")] = entry
    return indexed


def _list_affliction_classes(dll: Path) -> list[tuple[str, str]]:
    """Return [(short_name, fully_qualified_name), …] for all affliction models."""
    output = _run_ilspy(dll, "-l", "class", timeout=60)
    results: list[tuple[str, str]] = []
    prefix = f"Class {AFFLICTION_NS}."
    for line in output.splitlines():
        if not line.startswith(prefix):
            continue
        full = line[len("Class "):].strip()
        short = full[len(AFFLICTION_NS) + 1:]
        # Skip nested Mocks subnamespace and any dotted child types.
        if "." in short:
            continue
        results.append((short, full))
    return results


def _parse_affliction_description(
    class_name: str,
    code: str,
    loc_entry: dict | None,
) -> str:
    """Assemble an affliction glossary line from DLL metadata + upstream text."""
    stackable = "IsStackable => true" in code
    raw_desc: str = (loc_entry or {}).get("description", "") or ""
    desc = _strip_bbcode(raw_desc) if raw_desc else ""

    if not desc:
        desc = "Card-level debuff applied by certain enemy powers."

    # Stackable afflictions are indicated with trailing "(stacks)" so readers
    # know duplicate applications add up rather than replacing.
    if stackable and "stack" not in desc.lower():
        desc = desc.rstrip(".") + " (stacks)."

    extra = _AFFLICTION_EXTRA_NOTES.get(class_name.lower())
    if extra:
        desc = desc.rstrip(".") + ". " + extra

    return f"{class_name}: {desc}"


# ── Status / Curse card extraction ─────────────────────────────────────────────

# Constructor signature, e.g. `base(-1, CardType.Status, CardRarity.Status, ...)`
_STATUS_CURSE_CTOR = re.compile(
    r"base\(\s*-?\d+\s*,\s*CardType\.(?P<type>Status|Curse)\s*,\s*CardRarity\.(?P<rarity>Status|Curse)"
)
# DynamicVar entries inside CanonicalVars: `new DamageVar(2m, ...)`, `new EnergyVar(1)`.
_DYNAMIC_VAR = re.compile(r"new\s+(\w+)Var\(\s*(-?[\d.]+)m?")
# Extract keyword names from `CardKeyword.Xxx` references.
_CARD_KEYWORD = re.compile(r"CardKeyword\.(\w+)")


def _class_name_to_key(name: str) -> str:
    """Convert CamelCase class name to space-separated lowercase glossary key.

    `MindRot` → "mind rot"; `Burn` → "burn"; `AscendersBane` → "ascenders bane".
    Apostrophes are stripped so keys compare cleanly against lowercased card
    text (which may or may not contain curly quotes).
    """
    with_spaces = re.sub(r"(?<!^)(?=[A-Z])", " ", name).lower()
    return with_spaces.replace("'", "").replace("\u2019", "")


def _parse_status_curse_description(
    class_name: str,
    code: str,
    rarity: str,
) -> str:
    """Synthesize a one-line English description from a Status/Curse card body.

    Strategy: look at CanonicalVars (damage/energy numbers), CanonicalKeywords
    (Unplayable/Ethereal/Exhaust/Eternal), and override hooks (OnTurnEndInHand,
    AfterCardDrawn, OnPlay, ShouldPreventCardPlay) to assemble a sentence. Falls
    back to listing keywords if no known behavior pattern matches.
    """
    keywords: list[str] = []
    for m in _CARD_KEYWORD.finditer(code):
        kw = m.group(1)
        if kw not in keywords:
            keywords.append(kw)
    # Drop the rarity label if it leaked in (some classes reference CardRarity
    # constants which match this regex by accident).
    keywords = [k for k in keywords if k not in ("Status", "Curse")]

    dvars: dict[str, float] = {}
    for m in _DYNAMIC_VAR.finditer(code):
        try:
            dvars[m.group(1).lower()] = float(m.group(2))
        except ValueError:
            continue

    display_name = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    kw_suffix = f" ({'/'.join(keywords)})" if keywords else ""

    # Pick the first non-zero numeric DynamicVar as a fallback "damage number"
    # when classes use HpLossVar/HpCostVar/etc. instead of DamageVar. Cheaper
    # than enumerating every var type.
    def _first_numeric() -> int | None:
        for v in dvars.values():
            iv = int(v)
            if iv:
                return iv
        return None

    # Turn-end penalty (Burn, Decay, Infection, Toxic, Regret, BadLuck)
    # Order matters: scaling patterns before fixed damage, and CreatureCmd.Damage
    # is checked strictly so it doesn't false-match `DamageVar(` declarations.
    has_turn_end = "HasTurnEndInHandEffect => true" in code and "OnTurnEndInHand" in code
    calls_damage = bool(re.search(r"(?:CreatureCmd|PlayerCmd)\.Damage\s*\(", code))
    scales_by_hand = "CardsInHand" in code or "_cardsInHand" in code

    if has_turn_end:
        if scales_by_hand:
            return (
                f"{display_name}: {rarity} card. At end of your turn, triggers a "
                f"penalty scaled by the number of cards in your hand.{kw_suffix}"
            )
        if calls_damage:
            dmg = dvars.get("damage") or dvars.get("hploss") or dvars.get("hpcost")
            dmg_int = int(dmg) if dmg else _first_numeric()
            tail = f"take {dmg_int} damage" if dmg_int else "take damage"
            return (
                f"{display_name}: {rarity} card. At end of your turn, if this is in "
                f"your hand, {tail}.{kw_suffix}"
            )
        if "LoseHp" in code or "LoseHP" in code:
            hp = int(dvars.get("hp", 0)) or _first_numeric()
            tail = f"lose {hp} HP" if hp else "lose HP"
            return (
                f"{display_name}: {rarity} card. At end of your turn, if this is in "
                f"your hand, {tail}.{kw_suffix}"
            )
        if "LoseGold" in code:
            gold = int(dvars.get("gold", 0)) or _first_numeric()
            tail = f"lose {gold} gold" if gold else "lose gold"
            return (
                f"{display_name}: {rarity} card. At end of your turn, if this is in "
                f"your hand, {tail}.{kw_suffix}"
            )
        return (
            f"{display_name}: {rarity} card. Has a turn-end penalty while in your "
            f"hand.{kw_suffix}"
        )

    # When-drawn effects (Void lose-energy, debt-style)
    if "AfterCardDrawn" in code:
        if "LoseEnergy" in code:
            e = int(dvars.get("energy", 0)) or 1
            return (
                f"{display_name}: {rarity} card. Whenever you draw this card, lose "
                f"{e} energy.{kw_suffix}"
            )
        if "LoseGold" in code:
            g = int(dvars.get("gold", 0)) or None
            tail = f"{g} gold" if g else "gold"
            return (
                f"{display_name}: {rarity} card. Whenever you draw this card, lose "
                f"{tail}.{kw_suffix}"
            )

    # Play restriction (Normality = "cannot play more than 3 cards")
    if "ShouldPreventCardPlay" in code or "CardsPlayedThisTurn" in code:
        limit_m = re.search(r"CardsPlayedThisTurn\s*>=?\s*(\d+)", code)
        n = limit_m.group(1) if limit_m else "N"
        return (
            f"{display_name}: {rarity} card. Prevents playing more than {n} cards "
            f"this turn.{kw_suffix}"
        )

    # On-play effects (Slimed-style — might draw or exhaust silently)
    if "OnPlay" in code:
        if "Draw(" in code:
            return (
                f"{display_name}: {rarity} card. Draws cards when played. "
                f"{kw_suffix}".rstrip()
            )
        if "Exhaust" in keywords or "Exhaust" in code:
            return (
                f"{display_name}: {rarity} card. Exhausts when played; no other "
                f"effect.{kw_suffix}"
            )

    # Hand-blocker (Ascender's Bane, Injury, Clumsy, Pain) — Unplayable with
    # no turn-end or on-draw hook just clogs hand until it leaves via effects.
    if "Unplayable" in keywords and "OnTurnEndInHand" not in code and "AfterCardDrawn" not in code:
        return (
            f"{display_name}: {rarity} card. Unplayable; clogs your hand until it "
            f"leaves via effects or end of combat.{kw_suffix}"
        )

    # Generic fallback — at least communicate rarity + keywords.
    return (
        f"{display_name}: {rarity} card.{kw_suffix or ' See game UI for details.'}"
    )


def _list_card_classes(dll: Path) -> list[tuple[str, str]]:
    """Return [(short_name, fully_qualified_name), …] for card model classes.

    Excludes the `Mocks` sub-namespace (test doubles), nested types, and
    deprecated classes which don't represent real cards shipped in the game.
    """
    output = _run_ilspy(dll, "-l", "class", timeout=120)
    results: list[tuple[str, str]] = []
    prefix = f"Class {CARDS_NS}."
    for line in output.splitlines():
        if not line.startswith(prefix):
            continue
        full = line[len("Class "):].strip()
        short = full[len(CARDS_NS) + 1:]
        # Skip nested types (dotted), Mocks sub-namespace, and Deprecated* stubs.
        if "." in short:
            continue
        if short.startswith(("Deprecated", "Mock")):
            continue
        results.append((short, full))
    return results


def extract_status_curse_cards(dll: Path) -> dict[str, str]:
    """Extract Status and Curse card mechanics from the DLL.

    For each class in `Models.Cards.*` whose constructor declares
    `CardRarity.Status` or `CardRarity.Curse`, synthesize a glossary line from
    behavior pattern matching. Keys are space-separated lowercase display names
    ("mind rot", "ascenders bane") so they match word-boundary searches against
    card rules_text as rendered by the game.

    Requires ilspycmd + game DLL. Slow (~2-5s per class × ~33 status/curse
    cards → 1-3 minutes). Runs only when DLL mtime > cache mtime or --force.
    """
    out: dict[str, str] = {}
    classes = _list_card_classes(dll)
    logger.info(
        "Scanning %d card classes for Status/Curse rarity (one-time per game update)…",
        len(classes),
    )
    n_processed = 0
    for short_name, full_name in classes:
        n_processed += 1
        if n_processed % 50 == 0:
            logger.info("  … %d/%d cards scanned, %d status/curse found",
                        n_processed, len(classes), len(out))
        try:
            code = _decompile_type(dll, full_name)
        except Exception as exc:
            logger.debug("Failed to decompile %s: %s", full_name, exc)
            continue
        if not code.strip():
            continue
        m = _STATUS_CURSE_CTOR.search(code)
        if not m:
            continue
        rarity = m.group("rarity")
        try:
            desc = _parse_status_curse_description(short_name, code, rarity)
        except Exception as exc:
            logger.warning("Description synthesis failed for %s: %s", short_name, exc)
            continue
        key = _class_name_to_key(short_name)
        out[key] = desc
    logger.info("Found %d Status/Curse cards", len(out))
    return out


# ── Named power extraction ─────────────────────────────────────────────────────

def _parse_power_description(class_name: str, code: str) -> str:
    """Synthesize a description for a whitelisted Power class.

    Pattern-matches on override methods + callees in the decompiled C# source,
    so the text stays live against the current DLL (no upstream pck needed).
    Each branch decodes a specific buff/debuff behavior; unrecognised classes
    fall through to a `PowerType.` + hover-tip line.
    """
    display_name = re.sub(r"(?<!^)(?=[A-Z])", " ", class_name)
    display_name = re.sub(r"\s*Power$", "", display_name)

    # Focus — Scholar orb scaling, owns ModifyOrbValue
    if "ModifyOrbValue" in code:
        return (
            f"{display_name} N: Increases the passive and evoke values of your Orbs "
            "by N (Scholar's core scaling stat)."
        )

    # Temporary Focus — ITemporaryPower that delegates to FocusPower via
    # InternallyAppliedPower. Abstract base; its own body has no ModifyOrbValue,
    # so we match on the temporary-power protocol + FocusPower reference.
    if "ITemporaryPower" in code and "Power<FocusPower>" in code:
        return (
            f"{display_name} N: Temporary buff. Increases Orb passive and evoke "
            "values by N for this turn (wears off at end of turn)."
        )

    # Regen — heals N at end of turn, counter decrements by 1 per turn
    if (
        "AfterTurnEnd" in code
        and "CreatureCmd.Heal" in code
        and "PowerCmd.Decrement" in code
    ):
        return (
            f"{display_name} N: Heal N HP at end of your turn. "
            "Then N decreases by 1 (ticks down until it expires)."
        )

    # Ritual — applies StrengthPower to owner at end of turn
    if (
        "AfterTurnEnd" in code
        and "PowerCmd.Apply<StrengthPower>" in code
    ):
        return f"{display_name} N: Gain N Strength at the end of your turn."

    # Thorns — reflects damage in BeforeDamageReceived
    if (
        "BeforeDamageReceived" in code
        and "CreatureCmd.Damage" in code
        and "dealer" in code
    ):
        return (
            f"{display_name} N: When hit by an attack, deal N damage back to the "
            "attacker."
        )

    # Barricade — overrides ShouldClearBlock so block is preserved
    if "ShouldClearBlock" in code:
        return (
            f"{display_name}: Your Block is NOT removed at the start of your turn "
            "(persists across turns)."
        )

    # Buffer — ModifyHpLostAfterOstyLate returns 0, decrement per use
    if (
        "ModifyHpLostAfterOstyLate" in code
        and "return 0m" in code
        and "PowerCmd.Decrement" in code
    ):
        return (
            f"{display_name} N: Prevents the next N instances of HP loss "
            "(one charge consumed per HP-loss event)."
        )

    # Envenom — AfterDamageGiven + UnblockedDamage > 0 + Apply PoisonPower
    if (
        "AfterDamageGiven" in code
        and "UnblockedDamage" in code
        and "PowerCmd.Apply<PoisonPower>" in code
    ):
        return (
            f"{display_name} N: Whenever you deal unblocked attack damage, "
            "apply N Poison to the target."
        )

    # Infinite Blades — BeforeHandDraw creates Shivs
    if "BeforeHandDraw" in code and "Shiv.CreateInHand" in code:
        return (
            f"{display_name} N: At the start of your turn (before draw), "
            "add N Shivs into your hand."
        )

    # Noxious Fumes — AfterSideTurnStart + HittableEnemies + Apply<PoisonPower>
    if (
        "AfterSideTurnStart" in code
        and "HittableEnemies" in code
        and "PowerCmd.Apply<PoisonPower>" in code
    ):
        return (
            f"{display_name} N: At the start of your turn, apply N Poison "
            "to ALL enemies."
        )

    # ModifyCardPlayCount + Skill-type check → Burst
    if (
        "ModifyCardPlayCount" in code
        and "CardType.Skill" in code
        and "playCount + 1" in code
    ):
        return (
            f"{display_name} N: Your next N Skills are played an additional time "
            "(consumed on use)."
        )

    # ModifyCardPlayCount without Skill check → Duplication (any card type)
    if "ModifyCardPlayCount" in code and "playCount + 1" in code:
        return (
            f"{display_name} N: Your next N cards are played an additional time "
            "(consumed on use)."
        )

    # Accuracy — ModifyDamageAdditive gated on CardTag.Shiv
    if "ModifyDamageAdditive" in code and "CardTag.Shiv" in code:
        return f"{display_name} N: Your Shivs deal N additional damage."

    # Accelerant — class body is essentially empty; behavior lives in
    # PoisonPower which references AccelerantPower.Amount. Hard-coded because
    # there is no local pattern to decode.
    if class_name == "AccelerantPower":
        return (
            f"{display_name} N: Poison damage triggers N additional times "
            "each turn (multiplies Poison tick damage)."
        )

    # Fallback: declare type
    ptype_m = re.search(r"PowerType\.(\w+)", code)
    ptype = ptype_m.group(1) if ptype_m else "Buff"
    return f"{display_name} N: {ptype}. See game UI for details."


def extract_named_powers(dll: Path) -> dict[str, str]:
    """Extract a curated whitelist of Power mechanics (e.g. Focus).

    See `_POWER_WHITELIST` for the allow-list. We intentionally do not extract
    every power — most are boss-specific or character-lineage debuffs covered
    elsewhere, and including them would pollute the glossary match surface.
    """
    out: dict[str, str] = {}
    output = _run_ilspy(dll, "-l", "class", timeout=120)
    prefix = f"Class {POWERS_NS}."
    for line in output.splitlines():
        if not line.startswith(prefix):
            continue
        full = line[len("Class "):].strip()
        short = full[len(POWERS_NS) + 1:]
        if "." in short or short not in _POWER_WHITELIST:
            continue
        try:
            code = _decompile_type(dll, full)
        except Exception as exc:
            logger.debug("Failed to decompile %s: %s", full, exc)
            continue
        if not code.strip():
            continue
        try:
            desc = _parse_power_description(short, code)
        except Exception as exc:
            logger.warning("Power synthesis failed for %s: %s", short, exc)
            continue
        key = _class_name_to_key(re.sub(r"Power$", "", short))
        out[key] = desc
    logger.info("Extracted %d named powers", len(out))
    return out


# ── DLL helpers ────────────────────────────────────────────────────────────────

def _run_ilspy(dll: Path, *args: str, timeout: int = 30) -> str:
    try:
        result = subprocess.run(
            [ILSPY, str(dll), *args],
            capture_output=True, text=True, timeout=timeout,
        )
        return result.stdout
    except subprocess.TimeoutExpired:
        logger.warning("ilspycmd timed out for args: %s", args)
        return ""
    except FileNotFoundError:
        logger.error("ilspycmd not found — install with: dotnet tool install -g ilspycmd")
        return ""


def _list_enchantment_classes(dll: Path) -> list[tuple[str, str]]:
    """Return [(short_name, fully_qualified_name), …] for all enchantment models."""
    output = _run_ilspy(dll, "-l", "class", timeout=60)
    results: list[tuple[str, str]] = []
    for line in output.splitlines():
        prefix = f"Class {ENCHANTMENT_NS}."
        if not line.startswith(prefix):
            continue
        full = line[len("Class "):].strip()
        short = full[len(ENCHANTMENT_NS) + 1:]
        # Skip nested classes (contain a dot) and deprecated/mock types
        if "." in short or short in _SKIP_CLASSES:
            continue
        results.append((short, full))
    return results


def _decompile_type(dll: Path, type_name: str) -> str:
    return _run_ilspy(dll, "-t", type_name, timeout=30)


# ── Public API ─────────────────────────────────────────────────────────────────

def extract_mechanics(dll: Path) -> dict[str, str]:
    """
    Extract enchantment mechanic descriptions from the DLL.

    Always includes the 'replay' keyword as a special case (it is a card
    property set by cards like Hidden Gem, not a named enchantment class).
    """
    mechanics: dict[str, str] = {
        # Replay is a card-level property (BaseReplayCount), not an enchantment class.
        # Defined here from DLL analysis of CardModel.BaseReplayCount + HiddenGem.OnPlay.
        "replay": (
            "Replay N: When played, this card plays N additional times "
            "(N+1 total plays per turn). All effects — damage, block, powers — "
            "trigger for each play."
        ),
    }

    classes = _list_enchantment_classes(dll)
    logger.info("Processing %d enchantment classes", len(classes))

    for short_name, full_name in classes:
        try:
            code = _decompile_type(dll, full_name)
            if not code.strip():
                logger.debug("Empty decompile for %s, skipping", short_name)
                continue
            desc = _parse_enchantment_description(short_name, code)
            # Use space-separated display name as the match key so "Perfect Fit"
            # in card rules_text actually triggers. The old flat-lowercase keys
            # (perfectfit/slumberingessence/…) never matched real card text.
            mechanics[_class_name_to_key(short_name)] = desc
            logger.debug("  %s → %s", short_name, desc[:80])
        except Exception as exc:
            logger.warning("Failed to process %s: %s", full_name, exc)

    # Afflictions — card-level debuffs (Bound, Entangled, Galvanized, …). The
    # affliction classes themselves are near-empty; the rules live in the
    # Godot-localized resource pack, which the upstream mod has already
    # extracted to afflictions.json.
    loc_index = _load_upstream_afflictions()
    affliction_classes = _list_affliction_classes(dll)
    logger.info(
        "Processing %d affliction classes (loc entries: %d)",
        len(affliction_classes), len(loc_index),
    )
    for short_name, full_name in affliction_classes:
        try:
            code = _decompile_type(dll, full_name)
            if not code.strip():
                continue
            loc_entry = loc_index.get(short_name.lower())
            desc = _parse_affliction_description(short_name, code, loc_entry)
            mechanics[_class_name_to_key(short_name)] = desc
            logger.debug("  %s → %s", short_name, desc[:80])
        except Exception as exc:
            logger.warning("Failed to process %s: %s", full_name, exc)

    # Status + Curse cards — purely DLL-driven, no upstream localization needed.
    # The game's card text for these is embedded in Godot's resource pack, but
    # class-level behavior (damage numbers, keywords, triggers) lives in the
    # DLL and is authoritative. Synthesized descriptions are approximations —
    # the game UI remains ground truth — but they're fresh across game updates.
    try:
        mechanics.update(extract_status_curse_cards(dll))
    except Exception as exc:
        logger.warning("Status/Curse extraction failed: %s", exc)

    # Named powers — Focus + Temporary Focus are Scholar-critical scaling stats,
    # plus Regen/Ritual/Thorns/Barricade/Buffer/Envenom/etc. — common buffs that
    # appear in potion text and card rules_text. All are whitelisted in
    # `_POWER_WHITELIST` and behavior-decoded from the DLL class source, so the
    # text stays live against the current game binary (no upstream pck needed).
    try:
        mechanics.update(extract_named_powers(dll))
    except Exception as exc:
        logger.warning("Named power extraction failed: %s", exc)

    # Intent-level mechanics that have no clean class representation (Stun is
    # dispatched via `CreatureCmd.Stun`, not a `*Power` class). Curated and
    # rarely edited — review the `_INTENT_MECHANIC_LINES` dict for additions.
    mechanics.update(_INTENT_MECHANIC_LINES)

    return mechanics


def needs_update(dll: Path, output: Path) -> bool:
    """Return True if the output JSON is missing or older than the DLL."""
    if not output.exists():
        return True
    try:
        return dll.stat().st_mtime > output.stat().st_mtime
    except OSError:
        return True


def run(
    dll: Path = DEFAULT_DLL,
    output: Path = OUTPUT,
    force: bool = False,
) -> bool:
    """Extract and cache mechanics. Returns True on success or if already fresh."""
    if not dll.exists():
        logger.warning("STS2 DLL not found at %s — skipping mechanics extraction", dll)
        return False

    if not force and not needs_update(dll, output):
        logger.debug("mechanics_dll.json is up to date")
        return True

    logger.info("Extracting mechanics from DLL (this takes ~20s)…")
    mechanics = extract_mechanics(dll)

    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", encoding="utf-8") as f:
        json.dump(mechanics, f, indent=2, ensure_ascii=False)

    logger.info("Wrote %d mechanic definitions to %s", len(mechanics), output)
    return True


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Extract mechanic descriptions from the STS2 DLL"
    )
    parser.add_argument("--dll-path", type=Path, default=DEFAULT_DLL, metavar="PATH")
    parser.add_argument("--output", type=Path, default=OUTPUT, metavar="PATH")
    parser.add_argument(
        "--force", action="store_true",
        help="Re-extract even if cache is already up to date",
    )
    args = parser.parse_args()

    ok = run(dll=args.dll_path, output=args.output, force=args.force)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
