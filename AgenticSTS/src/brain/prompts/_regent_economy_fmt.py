"""Regent-only deck-economy summary block.

Reads the per-card star + Forge classifications from
`src/skills/seeds/regent_card_notes.json` and produces a 4–8 line snapshot
of the current deck's resource balance for injection into reward / shop /
card_select / rest prompts. Emits empty for non-Regent runs so other
characters' prompts are unaffected.

Output shape:
    ## Deck Economy (Regent)
    Star providers (X cards): Genesis, Hidden Cache, Solar Strike, Venerate
    Star consumers (Y cards): Stardust
    Forge engine (Z cards): Beat into Shape, The Smith, Refine Blade
    Blade synergy (W cards): Conqueror, Sword Sage
    Archetype: forge-stack (heavy Forge, light spend) — keep stacking before
    playing Sovereign Blade; avoid exhaust/transform on a buffed Blade.

The classification table is built once at first call from the regent_card_notes
seed; the schema fields read here are `card_name`, `star_role`, `forge_role`.
Entries without those fields default to neutral / null.
"""

from __future__ import annotations

import json
import threading
from pathlib import Path

from src.mcp_client.upstream_models import RawDeckCardPayload

_LOCK = threading.Lock()
_LOADED = False
# card_name (lowercase, no upgrade suffix) -> (star_role, forge_role)
_CLASSIFICATIONS: dict[str, tuple[str, str | None]] = {}
# card_name (lowercase, no upgrade suffix) -> (forge_tier, star_tier)
# Each tier ∈ {"S", "A", "B", "C", "skip"}. "skip" = anti-synergy in that archetype.
_TIERS: dict[str, tuple[str, str]] = {}
# card_name (lowercase, no upgrade suffix) -> XecnaR's note text. Used inline
# in card_reward / shop offerings so the LLM sees WHY a tier is what it is,
# not just the letter.
_NOTES: dict[str, str] = {}

# Tier rank order, lower = stronger. Used by the offering summary.
_TIER_RANK = {"S": 0, "A": 1, "B": 2, "C": 3, "skip": 4}
_TIER_NAMES = ("S", "A", "B", "C", "skip")


def _seed_path() -> Path:
    return Path(__file__).resolve().parents[3] / "src" / "skills" / "seeds" / "regent_card_notes.json"


def _ensure_loaded() -> None:
    global _LOADED
    if _LOADED:
        return
    with _LOCK:
        if _LOADED:
            return
        _LOADED = True
        path = _seed_path()
        if not path.exists():
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        for entry in data:
            name = (entry.get("card_name") or "").strip().lower()
            if not name:
                continue
            star_role = (entry.get("star_role") or "neutral").strip().lower()
            forge_role = entry.get("forge_role")
            if forge_role is not None:
                forge_role = str(forge_role).strip().lower() or None
            _CLASSIFICATIONS[name] = (star_role, forge_role)
            forge_tier = (entry.get("forge_tier") or "").strip().upper() or "B"
            star_tier = (entry.get("star_tier") or "").strip().upper() or "B"
            # Normalize "SKIP" / "skip" → "skip" (lowercase) for consistency.
            if forge_tier == "SKIP":
                forge_tier = "skip"
            if star_tier == "SKIP":
                star_tier = "skip"
            _TIERS[name] = (forge_tier, star_tier)
            note = (entry.get("note") or "").strip()
            if note:
                _NOTES[name] = note


def _strip_upgrade(name: str) -> str:
    """Strip trailing `+`, `+1`, `+2`, `*N` so 'Strike+1' matches 'Strike'."""
    s = name.strip()
    # Remove "*N" pile-collapse marker
    if "*" in s:
        s = s.split("*", 1)[0].rstrip()
    # Remove trailing "+N" or "+"
    if s.endswith("+"):
        s = s[:-1].rstrip()
    while s and s[-1].isdigit():
        s = s[:-1]
    if s.endswith("+"):
        s = s[:-1].rstrip()
    return s


def _classify(card_name: str) -> tuple[str, str | None]:
    """Look up `(star_role, forge_role)` for a card. Returns ('neutral', None) on miss."""
    base = _strip_upgrade(card_name).lower()
    return _CLASSIFICATIONS.get(base, ("neutral", None))


def classify_card(card_name: str) -> tuple[str, str | None]:
    """Public Regent card classification: ``(star_role, forge_role)``.

    star_role ∈ {"provider", "consumer", "both", "neutral"}.
    forge_role ∈ {"forge", "blade_synergy", "blade_buff", None}.
    Returns ("neutral", None) when the seed file is absent or the card is unknown.
    """
    _ensure_loaded()
    return _classify(card_name)


def card_tiers(card_name: str) -> tuple[str, str]:
    """Public per-archetype tier lookup: ``(forge_tier, star_tier)``.

    Each tier ∈ {"S", "A", "B", "C", "skip"}. ``skip`` means anti-synergy /
    don't-take in that archetype. Unknown cards default to ``("B", "B")``
    so they don't get hard-skipped purely from missing seed data.
    """
    _ensure_loaded()
    base = _strip_upgrade(card_name).lower()
    return _TIERS.get(base, ("B", "B"))


def regent_star_state(deck, character: str) -> dict | None:
    """Public deck-state summary used for tier-annotation overrides + verdicts.

    Returns ``None`` for non-Regent characters. Otherwise a dict with:
      - ``provider_n``: count of star_role=='provider' cards in deck
      - ``consumer_n``: count of star_role=='consumer' cards in deck
      - ``forge_n``: count of forge_role!=None cards in deck
      - ``state``: one of {'debt', 'tight', 'fueled', 'hoarder', 'balanced'}
        following the same thresholds as ``_archetype_directive``.

    The ``state`` is what ``annotate_card_tiers`` and the offering verdict
    use to decide whether to override S-tier consumers down to skip.
    """
    if (character or "").strip().lower() != "the regent":
        return None
    if not deck:
        return None
    _ensure_loaded()
    if not _CLASSIFICATIONS:
        return None

    provider_n = consumer_n = forge_n = 0
    seen: set[str] = set()
    for card in deck:
        raw = (getattr(card, "name", "") or "").strip()
        if not raw or raw in seen:
            continue
        seen.add(raw)
        star_role, forge_role = _classify(raw)
        if star_role == "provider":
            provider_n += 1
        elif star_role == "consumer":
            consumer_n += 1
        if forge_role is not None:
            forge_n += 1

    star_gap = consumer_n - provider_n
    if star_gap >= 2:
        state = "debt"
    elif star_gap >= 1:
        state = "tight"
    elif provider_n >= 3 and consumer_n == 0:
        state = "hoarder"
    elif consumer_n >= 1 and provider_n >= consumer_n + 1:
        state = "fueled"
    else:
        state = "balanced"

    return {
        "provider_n": provider_n,
        "consumer_n": consumer_n,
        "forge_n": forge_n,
        "state": state,
    }


def annotate_card_tiers(
    card_name: str,
    character: str,
    *,
    deck_state: dict | None = None,
) -> str:
    """Return ``" [Forge:A | Star:skip]"`` or ``""`` for inline use in prompts.

    Empty string when (a) character isn't Regent, or (b) the card isn't in
    the seed (avoids polluting prompts with default ``B/B`` for unknown
    cards).

    DECK-STATE OVERRIDE: when ``deck_state['state'] == 'debt'`` and the
    card is a star consumer, the displayed tier is rewritten to
    ``[Forge:skip | Star:skip — STAR DEBT override]`` regardless of the
    seed tier. This stops the LLM from rationalizing "but Astral Pulse is
    S-tier" when the deck already has too many payoffs to fuel.
    Symmetrically, in 'hoarder' state we tag consumer S/A picks with a
    "← USE STARS" note to encourage the LLM to spend accumulated gen.
    """
    if (character or "").strip().lower() != "the regent":
        return ""
    _ensure_loaded()
    base = _strip_upgrade(card_name).lower()
    tiers = _TIERS.get(base)
    if tiers is None:
        return ""

    # Default display: just the seed tier, no transformation
    forge_disp = tiers[0]
    star_disp = tiers[1]
    suffix = ""

    # Apply deck-state-aware override for consumers — show as "S→skip" so the
    # LLM sees BOTH the underlying tier AND the override (transparent veto).
    if isinstance(deck_state, dict):
        state = deck_state.get("state")
        star_role, _ = _CLASSIFICATIONS.get(base, ("neutral", None))
        if state == "debt" and star_role == "consumer":
            # Only show arrow when the seed tier is actually being downgraded.
            if tiers[0] != "skip":
                forge_disp = f"{tiers[0]}→skip"
            if tiers[1] != "skip":
                star_disp = f"{tiers[1]}→skip"
            suffix = (
                f" — STAR DEBT override (deck has {deck_state.get('consumer_n', '?')} "
                f"payoffs vs {deck_state.get('provider_n', '?')} providers; this card "
                "would brick on draw)"
            )
        elif state == "hoarder" and star_role == "consumer" and tiers[1] in ("S", "A"):
            suffix = " ← USE STARS (deck has unspent star generation)"

    return f" [Forge:{forge_disp} | Star:{star_disp}{suffix}]"


def annotate_card_note(card_name: str, character: str, max_chars: int = 220) -> str:
    """Return ``"\\n      ⤷ Why: <note>"`` or ``""`` for inline use.

    Surfaces the per-card seed note (XecnaR's reasoning) right under the
    offering line so the LLM sees WHY a tier is what it is, not just the
    letter. Truncates to keep the prompt compact. Empty for non-Regent or
    unknown cards.
    """
    if (character or "").strip().lower() != "the regent":
        return ""
    _ensure_loaded()
    base = _strip_upgrade(card_name).lower()
    note = _NOTES.get(base)
    if not note:
        return ""
    if len(note) > max_chars:
        # Truncate at sentence boundary if possible
        cutoff = note.rfind(". ", 0, max_chars)
        if cutoff < max_chars - 60:
            cutoff = max_chars - 3
        note = note[:cutoff].rstrip(" .") + "..."
    return f"\n      ⤷ Why: {note}"


def format_regent_offering_summary(
    offered_card_names: list[str],
    character: str,
    *,
    deck_state: dict | None = None,
) -> list[str]:
    """Return a Regent-only summary block analyzing the highest-tier card on offer.

    When all offerings are ≤ B tier, surfaces XecnaR's "skip mediocre commons"
    rule explicitly so the LLM doesn't pick a C/skip card just because its
    raw stats look ok in isolation. Empty for non-Regent.

    DECK-STATE OVERRIDE: when ``deck_state['state'] == 'debt'``, the verdict
    classifies S-tier consumers as effectively-skip and recommends taking a
    generator/skip even if S/A consumers are on offer.
    """
    if (character or "").strip().lower() != "the regent":
        return []
    if not offered_card_names:
        return []
    _ensure_loaded()
    if not _TIERS:
        return []

    in_debt = isinstance(deck_state, dict) and deck_state.get("state") == "debt"

    # Best tier across BOTH columns per card (whichever is stronger).
    # In debt: consumers are forced to "skip" for ranking, but we display the
    # arrow form (e.g. "S→skip") in the summary so the LLM sees both the
    # underlying tier and the override.
    best_per_card: list[tuple[str, str, str]] = []  # (name, effective_rank_tier, display_str)
    for raw in offered_card_names:
        base = _strip_upgrade(raw).lower()
        tiers = _TIERS.get(base)
        star_role, _ = _CLASSIFICATIONS.get(base, ("neutral", None))
        if tiers is None:
            # Unknown — don't penalize the offering; treat as B (neutral).
            best_per_card.append((raw, "B", "B"))
            continue
        f, s = tiers
        # Determine the seed-best tier (used for display when not overridden)
        seed_best = f if _TIER_RANK[f] <= _TIER_RANK[s] else s
        if in_debt and star_role == "consumer":
            # Forcibly skip for ranking; show arrow for display.
            effective = "skip"
            display = f"{seed_best}→skip" if seed_best != "skip" else "skip"
        else:
            effective = seed_best
            display = seed_best
        best_per_card.append((raw, effective, display))

    if not best_per_card:
        return []

    # Find the strongest card's tier across the offer.
    overall_best = min(_TIER_RANK[t] for _, t, _ in best_per_card)

    lines = ["", "## Offering Verdict (Regent)"]
    if in_debt:
        lines.append(
            f"** STAR DEBT MODE ** ({deck_state.get('consumer_n', '?')} payoffs vs "
            f"{deck_state.get('provider_n', '?')} providers). All star-cost cards "
            "are forcibly downgraded to SKIP for this verdict regardless of seed "
            "tier (shown as 'S→skip' / 'A→skip' inline). The autopick list (Astral "
            "Pulse, Reflect, Quasar, Particle Wall, Cloak of Stars) DOES NOT APPLY "
            "in debt."
        )
    summary = ", ".join(f"{n}={d}" for n, _, d in best_per_card)
    lines.append(f"Best-of-archetype tiers: {summary}")
    if overall_best <= 1:  # at least one S or A
        if in_debt:
            lines.append(
                "→ A non-consumer S/A card is on offer (smooth generator, removal, "
                "or universal premium) — pick it. This is the deck's escape from "
                "star debt."
            )
        else:
            lines.append(
                "→ At least one S/A card on offer — pick it. Even off-archetype S/A "
                "cards (per the autopick list) are preferable to skipping."
            )
    elif overall_best == 2:  # best is B
        if in_debt:
            lines.append(
                "→ Best offer is a B-tier non-consumer. Take it if it's a "
                "generator (Glow / Convergence / Hidden Cache / Royal Gamble) or "
                "removal. Otherwise SKIP — DO NOT pick a consumer here, even if "
                "its seed tier was S/A before debt downgrade."
            )
        else:
            lines.append(
                "→ Best offer is B tier. Pickable if it fills a real gap (block, "
                "removal, specific matchup tool), but Skip is also defensible — "
                "adding a B-tier common to a Regent deck displaces room for a "
                "future S/A pick AND the starter deck is strong enough to skip "
                "mediocre commons in early floors."
            )
    else:  # all C or worse
        lines.append(
            "→ All offerings are C tier or worse" + (
                " (in debt mode every consumer is forcibly C-or-worse)" if in_debt else ""
            ) + ". SKIP IS THE CORRECT PICK per XecnaR's macro: 'Adding bad cards "
            "to a Regent deck has a much bigger negative impact than other "
            "characters because Star cards are draw-order dependent — every weak "
            "common is a dead draw on a turn you needed star gen or a payoff.' Do "
            "not be tempted by raw card stats (damage / draw); the C tier already "
            "accounts for them and the deck-pollution cost outweighs the "
            "immediate value."
        )
    return lines


def _archetype_label(forge_n: int, blade_synergy_n: int, blade_buff_n: int,
                     provider_n: int, consumer_n: int) -> str:
    """Short label describing the deck's current resource shape.

    Per XecnaR's A10 guide, Regent does NOT have a hard Forge-vs-Star split —
    the win condition is "farm overstatted cards and snowball." This label
    reports star-economy state (the actual deck-construction concern) rather
    than declaring an archetype the deck is committed to.
    """
    star_gap = consumer_n - provider_n  # +N consumers above providers = stars debt
    if consumer_n == 0 and provider_n == 0:
        return "no star economy yet (just basics)"
    if star_gap >= 2:
        return f"star-debt ({consumer_n} payoffs vs {provider_n} providers — payoffs will brick on draw)"
    if star_gap >= 1:
        return f"star-tight ({consumer_n} payoffs vs {provider_n} providers — pick smooth gen next, not more payoffs)"
    if provider_n >= 3 and consumer_n == 0:
        return f"star-hoarder ({provider_n} providers, 0 payoffs — pick a premium payoff)"
    if consumer_n >= 1 and provider_n >= consumer_n + 1:
        return f"star-fueled (excess gen, room for another premium payoff)"
    if forge_n >= 2 and (blade_synergy_n + blade_buff_n) >= 1:
        return "forge-leaning (Sovereign Blade is your damage plan)"
    return "balanced (no resource imbalance)"


# Cards XecnaR considers "primary overstatted" or "primary farm targets" —
# autopick when offered (subject to star-economy and presence of better cards).
# Surfaced in the directive to give the LLM concrete autopick guidance instead
# of vague "pick the highest tier." LIST IS FOR PATCH 0.103 — Reflect is
# included here; it gets removed in 0.104.0 due to a -1 block nerf that
# pushes it to unpickable.
_PRIMARY_OVERSTATTED = (
    "Astral Pulse", "Bulwark", "Big Bang", "Crash Landing", "GUARDS!!!",
    "CHARGE!!", "Know Thy Place", "Quasar", "Particle Wall", "Reflect",
    "Spectrum Shift", "Child of the Stars", "Pillar of Creation",
    "Meteor Shower",
)

_PRIMARY_BAD = (
    "Conqueror", "Sword Sage", "Seeking Edge", "Furnace", "Beat into Shape",
    "Shining Strike", "Solar Strike", "Stardust",
    "Cosmic Indifference", "Lunar Blast", "Resonance", "Terraforming",
    "Neutron Aegis", "Monarch's Gaze", "Seven Stars",
)


def _archetype_directive(forge_n: int, blade_synergy_n: int, blade_buff_n: int,
                         provider_n: int, consumer_n: int) -> str:
    """Concrete DRAFT/SKIP guidance per XecnaR's A10 macro.

    The framing is NOT "Forge vs Star = pick one." Instead:
      1. Farm overstatted cards (Astral Pulse, GUARDS!!!, Big Bang, Bulwark,
         Crash Landing, Know Thy Place, Quasar, Particle Wall, Spectrum Shift,
         Child of the Stars, Pillar of Creation, CHARGE!!, Meteor Shower).
      2. Manage star payoff_per_cycle vs gen_per_cycle — extra payoffs without
         gen create dead draws; extra gen without payoffs wastes slots.
      3. Don't add bad cards (Conqueror, Sword Sage, Shining Strike, Solar
         Strike, Stardust, etc) — Regent suffers more than other characters
         from deck dilution because Star cards are draw-order dependent.
    """
    star_gap = consumer_n - provider_n
    autopicks = ", ".join(_PRIMARY_OVERSTATTED[:6]) + ", ..."
    if consumer_n == 0 and provider_n == 0 and forge_n == 0:
        return (
            f"→ Macro: farm act 1 fights to find overstatted cards: {autopicks}. "
            "Skip everything else unless premium (Wrought in War, Refine Blade, Cloak of Stars, Glow, Convergence). "
            "Adding bad cards to a Regent deck has a much bigger negative impact than other characters."
        )
    if star_gap >= 2:
        return (
            f"→ STAR DEBT ({consumer_n} payoffs vs {provider_n} providers). "
            "ABSOLUTE VETO: ALL star-cost cards are SKIP regardless of seed tier — "
            "the autopick list (Astral Pulse, Reflect, Quasar, Particle Wall, Cloak "
            "of Stars, Gamma Blast, Stardust, Comet, Knockout Blow) DOES NOT APPLY "
            "in debt state. A 2nd Astral Pulse / 2nd Reflect / 'cheap' Quasar all "
            "fail equally — they brick on draw because the deck cannot generate "
            "enough stars to fuel them. ALLOWED PICKS: Glow, Convergence (smooth "
            "generators with utility), Hidden Cache / Royal Gamble (pure gen, less "
            "ideal but acceptable), removal, or universal-S cards (Heavenly Drill, "
            "Meteor Shower) and non-star Forge support. If none of those are on "
            "offer: SKIP. Adding a 6th payoff to a deck with 1 provider is "
            "run-losing — the analysis at floor 23 of the prior loss attributed "
            "death to exactly this deck shape (5 consumers, 1 provider)."
        )
    if star_gap >= 1:
        return (
            f"→ Star-tight ({consumer_n} payoffs vs {provider_n} providers). "
            "STRONGLY prefer smooth gen (Glow, Convergence) over any payoff. "
            "Premium payoffs (Astral Pulse, Quasar, Reflect, Particle Wall, Gamma "
            "Blast) are NO LONGER autopick at this state — they require a smooth "
            "generator pick first. Only take a payoff here if (a) no generator is "
            "offered AND (b) the payoff is S-tier AND (c) skipping is worse than "
            "adding modest star debt. Default action when uncertain: skip."
        )
    if provider_n >= 3 and consumer_n == 0:
        return (
            f"→ Star-hoarder ({provider_n} providers, 0 payoffs). Stars are wasted — pick a premium payoff (Astral Pulse, Reflect, Quasar, Particle Wall). "
            "Or pivot: pick removal / a non-star damage solution."
        )
    if consumer_n >= 1 and provider_n >= consumer_n + 1:
        return (
            f"→ Star-fueled ({provider_n} providers, {consumer_n} payoffs — comfortable gap). Room for one more premium payoff. "
            f"Autopick from {autopicks}. Reject mediocre cards even if they look ok in isolation."
        )
    return (
        f"→ Balanced. Continue farming overstatted cards: {autopicks}. "
        "Avoid balanced-number cards (Crescent Spear, Photon Cut, Celestial Might, Conqueror) — Regent hates balanced numbers. "
        "Avoid star-cost cards over 3 stars (Devastate, The Smith, Comet, Knockout Blow) unless Genesis or Sealed Throne is in deck."
    )


def format_regent_economy(
    deck: list[RawDeckCardPayload] | None,
    character: str,
) -> list[str]:
    """Return the Regent deck-economy block. Empty list for non-Regent runs."""
    if (character or "").strip().lower() != "the regent":
        return []
    if not deck:
        return []

    _ensure_loaded()
    if not _CLASSIFICATIONS:
        return []

    providers: list[str] = []
    consumers: list[str] = []
    forges: list[str] = []
    blade_syn: list[str] = []
    blade_buf: list[str] = []
    seen: set[str] = set()

    for card in deck:
        # Use display name with upgrade suffix for human readability, but
        # classify by the base name.
        raw = (card.name or "").strip()
        if not raw:
            continue
        if raw in seen:
            continue
        seen.add(raw)
        star_role, forge_role = _classify(raw)
        if forge_role == "forge":
            forges.append(raw)
        elif forge_role == "blade_synergy":
            blade_syn.append(raw)
        elif forge_role == "blade_buff":
            blade_buf.append(raw)
        if star_role == "provider":
            providers.append(raw)
        elif star_role == "consumer":
            consumers.append(raw)

    # Skip the section entirely if every counter is zero — nothing useful to say.
    if not (providers or consumers or forges or blade_syn or blade_buf):
        return []

    archetype = _archetype_label(
        forge_n=len(forges),
        blade_synergy_n=len(blade_syn),
        blade_buff_n=len(blade_buf),
        provider_n=len(providers),
        consumer_n=len(consumers),
    )
    directive = _archetype_directive(
        forge_n=len(forges),
        blade_synergy_n=len(blade_syn),
        blade_buff_n=len(blade_buf),
        provider_n=len(providers),
        consumer_n=len(consumers),
    )

    lines = ["", "## Deck Economy (Regent)"]
    if providers:
        lines.append(f"Star providers ({len(providers)}): {', '.join(providers)}")
    if consumers:
        lines.append(f"Star consumers ({len(consumers)}): {', '.join(consumers)}")
    if forges:
        lines.append(f"Forge engine ({len(forges)}): {', '.join(forges)}")
    if blade_syn:
        lines.append(f"Blade synergy ({len(blade_syn)}): {', '.join(blade_syn)}")
    if blade_buf:
        lines.append(f"Blade buffs ({len(blade_buf)}): {', '.join(blade_buf)}")
    lines.append(f"Archetype: {archetype}")
    lines.append(directive)
    return lines
