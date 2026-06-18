"""Card build memory extractor: converts ShortTermMemory deck data into CardBuildMemory.

Two-phase design:
  1. Deterministic evidence extraction: raw signals from the run (play counts,
     damage/block per card, deck events, combat outcomes).  No interpretation.
  2. LLM-based build analysis: an async call to Opus that reads the evidence
     and produces build_summary, build_tags, primary_plan, and engine analysis.
     This is the ONLY place where build labels/tags are generated.
"""

from __future__ import annotations

import json
import logging
from collections import Counter
from typing import Any

from src.memory.deck_build_registry import (
    active_deck_builds,
    canonical_deck_build_tag,
)
from src.memory.models_v2 import CardBuildMemory, CardEvent, normalize_character
from src.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)

_VALID_ROLES = frozenset({
    "keystone", "core_damage", "core_defense", "draw_engine",
    "energy_engine", "utility", "dead_weight", "bad_pick",
})


# ── Phase 1: Deterministic evidence extraction ─────────────────


def _derive_play_counts_from_combats(short_term: ShortTermMemory) -> dict[str, int]:
    """Fallback aggregation when global play counts were not populated."""
    counts: dict[str, int] = {}
    for tracker in short_term.completed_combats:
        if getattr(tracker, "terminal_reason", "") == "abort":
            continue
        for round_tracker in tracker.rounds:
            for card_name in round_tracker.cards_played:
                counts[card_name] = counts.get(card_name, 0) + 1
    return counts


def _payload_to_plain_dicts(
    payload: list[Any] | None,
) -> list[dict[str, Any]]:
    """Flatten a list of RawDeckCardPayload (or any attr-bearing card objects)
    into plain JSON-serialisable dicts keyed on the fields the downstream
    prompt renderer actually consumes. Stored verbatim inside
    ``CardBuildMemory.build_evidence``; Pydantic objects cannot round-trip
    through ``json.dumps``.
    """
    if not payload:
        return []
    plain: list[dict[str, Any]] = []
    for c in payload:
        plain.append({
            "name": getattr(c, "name", "") or "",
            "upgraded": bool(getattr(c, "upgraded", False)),
            "enchantment_name": getattr(c, "enchantment_name", None)
                or getattr(c, "enchantment_id", None)
                or "",
            "rules_text": (
                getattr(c, "resolved_rules_text", "")
                or getattr(c, "rules_text", "")
                or ""
            ),
            "card_type": getattr(c, "card_type", "") or "",
            "rarity": getattr(c, "rarity", "") or "",
        })
    return plain


def extract_build_evidence(
    short_term: ShortTermMemory,
    character: str,
    final_deck: list[str],
    victory: bool,
    final_floor: int,
    fitness: float,
    completion_reason: str = "completed",
    relics: list[str] | None = None,
    final_deck_payload: list[Any] | None = None,
    card_rules: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Extract raw, deterministic evidence from a completed run.

    Returns a plain dict of observable signals — NO interpretation or labels.
    This dict is both stored in CardBuildMemory.build_evidence AND fed to
    the LLM for build analysis.

    Args:
        relics: Optional pre-formatted relic strings ("Name (description)" or "Name").
        final_deck_payload: Optional list of RawDeckCardPayload objects from the
            last known GameState — carries enchantment + rules_text fidelity that
            the name-only ``final_deck`` list cannot. When absent, the evidence
            falls back to the plain name list.
        card_rules: Optional dict ``name → rules_text`` accumulated live from
            every card-bearing payload during the run. Preferred over the
            knowledge-base lookup because game balance patches make the lookup
            drift — the live payload is always what this run actually saw.
    """
    play_counts_source = dict(short_term.card_play_counts)
    if not play_counts_source:
        play_counts_source = _derive_play_counts_from_combats(short_term)

    # ── Per-card signals from action-level CombatDeltas ─────────
    # ALL attribution is strictly traceable: each signal is extracted from
    # a CombatDelta whose event_type == "card_play" and source == card_name.
    # No round-level averaging or heuristic splitting.
    card_damage: dict[str, int] = {}         # sum of abs(enemy hp delta) per source card
    card_block: dict[str, int] = {}          # sum of positive player block delta per source card
    card_energy_gain: dict[str, int] = {}    # sum of positive player energy delta per source card
    card_powers_applied: dict[str, list[str]] = {}  # powers_changed per source card
    card_enemy_debuffs: dict[str, list[str]] = {}   # enemy powers_changed per source card
    card_exhaust_count: dict[str, int] = {}  # cards that triggered exhaust actions
    combat_summaries: list[dict[str, Any]] = []
    has_action_deltas = False

    for tracker in short_term.completed_combats:
        if getattr(tracker, "terminal_reason", "") == "abort":
            continue
        total_dmg = 0
        total_blk = 0
        total_taken = 0
        total_rounds = len(tracker.rounds)

        for rnd in tracker.rounds:
            total_dmg += rnd.damage_dealt
            total_blk += rnd.block_gained
            total_taken += rnd.damage_taken

            # Walk per-action deltas (CombatDelta objects)
            for delta in rnd.events:
                if delta.event_type != "card_play" or not delta.source:
                    continue
                has_action_deltas = True
                card_name = delta.source

                # Damage: sum of negative enemy HP deltas
                for ed in delta.enemy_deltas:
                    if ed.hp is not None and ed.hp < 0:
                        card_damage[card_name] = (
                            card_damage.get(card_name, 0) + abs(ed.hp)
                        )
                    # Enemy debuffs applied by this card
                    if ed.powers_changed:
                        card_enemy_debuffs.setdefault(card_name, []).extend(
                            ed.powers_changed
                        )

                # Block gained
                if delta.block is not None and delta.block > 0:
                    card_block[card_name] = (
                        card_block.get(card_name, 0) + delta.block
                    )

                # Energy gained (positive delta = card generated energy)
                if delta.energy is not None and delta.energy > 0:
                    card_energy_gain[card_name] = (
                        card_energy_gain.get(card_name, 0) + delta.energy
                    )

                # Player powers/statuses applied by this card
                if delta.powers_changed:
                    card_powers_applied.setdefault(card_name, []).extend(
                        delta.powers_changed
                    )

                # Exhaust events triggered by this card
                if delta.cards_exhausted:
                    card_exhaust_count[card_name] = (
                        card_exhaust_count.get(card_name, 0)
                        + len(delta.cards_exhausted)
                    )

        won = getattr(tracker, "won", getattr(tracker, "_won", False))
        hp_after = getattr(tracker, "hp_after", getattr(tracker, "_hp_after", 0))
        combat_summaries.append({
            "enemy": tracker.enemy_key,
            "type": tracker.combat_type,
            "won": won,
            "rounds": total_rounds,
            "hp_before": tracker.hp_before,
            "hp_after": hp_after,
            "total_damage_dealt": total_dmg,
            "total_block_gained": total_blk,
            "total_damage_taken": total_taken,
        })

    # ── Sorted top-N per signal (all traceable) ─────────────────
    def _top(d: dict[str, float], n: int = 10) -> list[tuple[str, float]]:
        return sorted(d.items(), key=lambda x: x[1], reverse=True)[:n]

    top_played = sorted(play_counts_source.items(), key=lambda x: x[1], reverse=True)[:10]
    top_damage = _top(card_damage)
    top_block = _top(card_block)
    top_energy_gain = _top(card_energy_gain)
    top_exhaust = _top(card_exhaust_count)

    # Aggregate power/debuff occurrences per card into counts
    def _power_counts(d: dict[str, list[str]]) -> list[tuple[str, list[tuple[str, int]]]]:
        """card → [(power_name, count), ...] sorted by count."""
        result = []
        for card, powers in d.items():
            counts = Counter(powers).most_common(5)
            result.append((card, counts))
        result.sort(key=lambda x: sum(c for _, c in x[1]), reverse=True)
        return result[:10]

    top_powers_applied = _power_counts(card_powers_applied)
    top_enemy_debuffs = _power_counts(card_enemy_debuffs)

    # ── Deck events summary ─────────────────────────────────────
    deck_event_summary: list[dict[str, str | int]] = []
    for e in short_term.deck_events:
        deck_event_summary.append({
            "floor": e.floor,
            "type": e.event_type,
            "card": e.card_name,
            "source": e.source,
        })

    return {
        "character": character,
        "victory": victory,
        "completion_reason": completion_reason,
        "final_floor": final_floor,
        "fitness": round(fitness, 1),
        "deck_size": len(final_deck),
        "final_deck": final_deck,
        "final_deck_payload": _payload_to_plain_dicts(final_deck_payload),
        "starting_deck": list(short_term.starting_deck),
        "relics": list(relics) if relics else [],
        "card_rules": dict(card_rules) if card_rules else {},
        # Evidence quality marker
        "evidence_quality": "full" if has_action_deltas else "round_summary_only",
        # Play frequency (from global counter, always available)
        "top_played": top_played,
        # Action-level traceable signals (empty if no CombatDelta data)
        "top_damage": top_damage,
        "top_block": top_block,
        "top_energy_gain": top_energy_gain,
        "top_exhaust": top_exhaust,
        "top_powers_applied": top_powers_applied,
        "top_enemy_debuffs": top_enemy_debuffs,
        # Deck trajectory
        "deck_events": deck_event_summary,
        # Combat outcomes
        "combat_summaries": combat_summaries,
        "combats_won": sum(1 for c in combat_summaries if c["won"]),
        "combats_total": len(combat_summaries),
    }


def _card_description(
    card_name: str,
    card_rules: dict[str, str] | None = None,
) -> str:
    """Return a stripped, human-readable description for a card.

    Prefers the runtime ``card_rules`` dict (populated live from MCP payloads
    during the run) so the description reflects the game version actually
    played. Falls back to the static knowledge-base lookup when the live text
    is unavailable (e.g. cards removed before we ever observed them).
    """
    if card_rules:
        # Exact match first, then strip a trailing '+' so upgraded variants
        # still resolve when the lookup table only keyed the base name.
        txt = card_rules.get(card_name)
        if txt:
            return txt
        base = card_name.rstrip("+")
        if base != card_name:
            txt = card_rules.get(base)
            if txt:
                return txt

    try:
        from src.knowledge.knowledge import GameKnowledge
    except Exception:  # pragma: no cover - defensive
        return ""
    try:
        kb = GameKnowledge.get_instance()
    except Exception:  # pragma: no cover - defensive
        return ""
    card = kb.cards.get(card_name)
    if card is None:
        return ""
    from src.brain.prompts._deck_fmt import strip_bbcode

    # Prefer resolved description; fall back to on_play (behaviors md).
    desc = (card.description or "").strip()
    if desc:
        return strip_bbcode(desc)
    return (card.on_play or "").strip()


def _final_deck_lines(
    evidence: dict[str, Any],
) -> tuple[list[str], list[str]]:
    """Render the final deck with enchantment + effect text and collect card
    texts that should seed the keyword glossary.

    Returns (lines, card_texts_for_glossary).
    """
    from src.brain.prompts._deck_fmt import strip_bbcode

    payload = evidence.get("final_deck_payload") or []
    final_names: list[str] = list(evidence.get("final_deck", []) or [])
    card_rules: dict[str, str] = evidence.get("card_rules") or {}

    lines: list[str] = []
    glossary_texts: list[str] = []

    if payload:
        # Group payload by (display_name, enchantment, rules_text) so duplicates
        # collapse while preserving enchantment variants separately. payload
        # entries are plain dicts produced by _payload_to_plain_dicts so the
        # evidence dict round-trips through json.dumps.
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for c in payload:
            name = c.get("name", "") or ""
            upgraded = bool(c.get("upgraded", False))
            enchant = c.get("enchantment_name", "") or ""
            display_name = name + ("+" if upgraded else "")
            raw_text = (c.get("rules_text", "") or "").strip()
            rules_text = strip_bbcode(raw_text) if raw_text else ""
            if not rules_text:
                rules_text = _card_description(display_name, card_rules)
            key = (display_name, str(enchant))
            bucket = grouped.setdefault(
                key,
                {"count": 0, "rules": rules_text, "enchant": str(enchant)},
            )
            bucket["count"] += 1

        # Deterministic ordering: name asc, enchant asc.
        for (display_name, enchant), info in sorted(grouped.items()):
            count = info["count"]
            rules = info["rules"]
            enchant_str = f" [Enchant: {enchant}]" if enchant else ""
            count_str = f" x{count}" if count > 1 else ""
            desc_suffix = f" — {rules}" if rules else ""
            lines.append(f"  - {display_name}{enchant_str}{count_str}{desc_suffix}")
            if rules:
                glossary_texts.append(rules)
    else:
        # No payload: collapse by plain name, add descriptions from the runtime
        # card-rules cache (falling back to knowledge base).
        counts: dict[str, int] = {}
        for n in final_names:
            counts[n] = counts.get(n, 0) + 1
        for name in sorted(counts):
            count = counts[name]
            desc = _card_description(name, card_rules)
            count_str = f" x{count}" if count > 1 else ""
            desc_suffix = f" — {desc}" if desc else ""
            lines.append(f"  - {name}{count_str}{desc_suffix}")
            if desc:
                glossary_texts.append(desc)

    return lines, glossary_texts


def format_evidence_for_llm(evidence: dict[str, Any]) -> str:
    """Format evidence dict into a compact text prompt for the LLM.

    Surfaces traceable signals only. Sections with no data are omitted.
    Play-frequency and per-combat HP/round breakdowns are intentionally
    excluded: raw counts and rounds carry no build-quality signal on their
    own, and their presence encouraged the LLM to pattern-match on noise.
    """
    from src.brain.prompts._deck_fmt import strip_bbcode
    from src.brain.prompts._keyword_fmt import format_keyword_glossary

    lines: list[str] = []
    card_rules: dict[str, str] = evidence.get("card_rules") or {}
    eq = evidence.get("evidence_quality", "unknown")
    lines.append(f"Character: {evidence['character']}")
    completion = evidence.get("completion_reason", "completed")
    if completion == "completed":
        result_label = "VICTORY" if evidence["victory"] else "DEFEAT"
    else:
        result_label = f"INCOMPLETE ({completion})"
    lines.append(f"Result: {result_label} at floor {evidence['final_floor']}")
    lines.append(f"Fitness: {evidence['fitness']}")
    lines.append(f"Deck size: {evidence['deck_size']}")
    lines.append(f"Combats: {evidence['combats_won']}/{evidence['combats_total']} won")
    if eq != "full":
        lines.append(f"Evidence quality: {eq} (some signals may be unavailable)")

    # Traceable damage sources (from action deltas)
    if evidence.get("top_damage"):
        items = ", ".join(f"{c}({d} dmg)" for c, d in evidence["top_damage"][:6])
        lines.append(f"Top damage sources (traceable): {items}")

    # Traceable block sources (from action deltas)
    if evidence.get("top_block"):
        items = ", ".join(f"{c}({b} blk)" for c, b in evidence["top_block"][:6])
        lines.append(f"Top block sources (traceable): {items}")

    # Energy generation (from action deltas)
    if evidence.get("top_energy_gain"):
        items = ", ".join(f"{c}(+{e} energy)" for c, e in evidence["top_energy_gain"][:5])
        lines.append(f"Energy generators (traceable): {items}")

    # Powers/statuses applied by cards (from action deltas)
    if evidence.get("top_powers_applied"):
        parts = []
        for card, powers in evidence["top_powers_applied"][:5]:
            pw_str = ", ".join(f"{p}(×{n})" for p, n in powers[:3])
            parts.append(f"{card} → {pw_str}")
        lines.append(f"Powers applied by cards: {'; '.join(parts)}")

    # Enemy debuffs applied by cards (from action deltas)
    if evidence.get("top_enemy_debuffs"):
        parts = []
        for card, debuffs in evidence["top_enemy_debuffs"][:5]:
            db_str = ", ".join(f"{d}(×{n})" for d, n in debuffs[:3])
            parts.append(f"{card} → {db_str}")
        lines.append(f"Enemy debuffs applied: {'; '.join(parts)}")

    # Exhaust events (from action deltas)
    if evidence.get("top_exhaust"):
        items = ", ".join(f"{c}({n} exhausts)" for c, n in evidence["top_exhaust"][:5])
        lines.append(f"Exhaust triggers: {items}")

    # Relics with descriptions (from cached run-state relic payload)
    relics = evidence.get("relics") or []
    if relics:
        lines.append("")
        lines.append(f"## Relics ({len(relics)})")
        for r in relics:
            lines.append(f"  - {strip_bbcode(str(r))}")

    # Deck trajectory — keep removes/upgrades compact; expand ADDED cards with
    # rules text so the analyst can judge build commitment without guessing.
    # Descriptions are captured once here and reused by the keyword glossary
    # below so we never do the same lookup twice.
    added_descriptions: list[str] = []
    if evidence.get("deck_events"):
        adds = [e for e in evidence["deck_events"] if e["type"] == "add"]
        removes = [e for e in evidence["deck_events"] if e["type"] == "remove"]
        upgrades = [e for e in evidence["deck_events"] if e["type"] == "upgrade"]
        if adds:
            lines.append("")
            lines.append(f"## Cards added ({len(adds)})")
            for e in adds:
                desc = _card_description(str(e["card"]), card_rules)
                desc_suffix = f" — {desc}" if desc else ""
                lines.append(f"  - {e['card']}{desc_suffix}")
                if desc:
                    added_descriptions.append(desc)
        if removes:
            lines.append(
                f"Cards removed ({len(removes)}): "
                f"{', '.join(e['card'] for e in removes)}"
            )
        if upgrades:
            lines.append(
                f"Cards upgraded ({len(upgrades)}): "
                f"{', '.join(e['card'] for e in upgrades)}"
            )

    # Final deck with enchantments + per-card rules text.
    deck_lines, glossary_texts = _final_deck_lines(evidence)
    if deck_lines:
        lines.append("")
        lines.append(f"## Final deck ({evidence['deck_size']})")
        lines.extend(deck_lines)

    # Keyword glossary seeded from final-deck + already-captured added-card
    # descriptions — gives the LLM enough to reason about mechanics without
    # asking it to recall card text.
    glossary = format_keyword_glossary(glossary_texts + added_descriptions)
    if glossary:
        lines.append("")
        lines.append(glossary.lstrip("\n"))

    return "\n".join(lines)


# ── Phase 2: LLM-based build analysis ──────────────────────────

_BUILD_ANALYSIS_SYSTEM = (
    "You are a Slay the Spire 2 deck analyst. "
    "Given raw run evidence, produce a structured build analysis. "
    "Output ONLY valid JSON, no markdown fences."
)

_BUILD_ANALYSIS_PROMPT = """\
Analyze this completed run and describe the deck build.

{evidence_text}

{build_registry_text}

Respond with a JSON object:
{{
  "decision": "update_existing|merge_into_existing|create_candidate|reject_no_clear_build|reject_too_early",
  "target_build_id": "<existing build id if this run clearly matches one, else empty>",
  "build_summary": "<1-2 sentence description of what this deck tried to do>",
  "primary_plan": "<short phrase naming the win condition at an ARCHETYPE level, not a card list>",
  "damage_engine": "<short phrase: the mechanism that produced damage (archetype + enabler class), derived from the traceable damage/power signals above>",
  "defense_engine": "<short phrase: the mechanism that produced survival (archetype + enabler class), derived from the traceable block/power signals above>",
  "cycle_engine": "<short phrase: the mechanism that cycled the deck, or 'not observed'>",
  "energy_engine": "<short phrase: the mechanism that produced extra energy, or 'base energy' if none>",
  "build_tags": ["<short reusable archetype tag>", "..."],
  "card_roles": [
    {{"card": "<card name from this run>", "build_id": "<target build id>", "role": "core|fuel|payoff|support|patch|trap|foundation", "phase": "foundation|commitment", "evidence": "<1 sentence grounded in the traceable signals above>"}}
  ],
  "weak_points": "<1 sentence: what was this deck worst at?>",
  "confidence": <0.3-0.9 float>,
  "key_cards": [
    {{"card": "<card name from this run>", "role": "<role>", "insight": "<1 sentence grounded in the traceable signals above>"}}
  ],
  "coherence_score": <0.0-1.0 float>,
  "coherence_analysis": "<1 sentence: strengths and gaps in card synergy>"
}}

Guidelines:
- Describe ENGINES AND ROLES AT THE ARCHETYPE LEVEL (e.g. a mechanic + the class of cards enabling it). Do NOT default to the example cards in any prompt you have seen — only name cards that actually appear in the evidence above.
- build_tags: 2-5 short, lowercase, reusable archetype tags. Include an outcome tag: "victory" or "defeat".
- If an Active Build Registry is listed above, target_build_id MUST be one of those builds or empty. Do NOT invent a new active build tag for that character.
- Generic labels like thin_deck / small_deck / general are NOT active builds; they belong in build_tags only.
- Use reject_no_clear_build when the run never committed to an active build; still summarize card mistakes, but do not force a build.
- card_roles and key_cards must only name cards present in this run's evidence (adds, final deck, or traceable top_* signals).
- If the run ended very early (floor < 5) or evidence is sparse, use low confidence and fewer tags.
- Be specific to what actually happened, not what the deck could theoretically do.
- For damage_engine, defense_engine, energy_engine: the top damage/block/energy sources are measured per action — base the engine on those traceable signals, not on card names alone.
- For cycle_engine: draw/discard events are NOT directly measured. You may INFER cycle capability from the rules text of cards that actually appear in the final deck or traceable plays, but label it as inference. If no such card is present, write "not observed".
- key_cards: 5-8 most notable cards in this run, including NEGATIVE contributions.
  Roles: keystone, core_damage, core_defense, draw_engine, energy_engine, utility, dead_weight, bad_pick.
  "keystone": Played rarely but DEFINED the strategy (power cards, scaling enablers). A card played once that enabled large downstream damage outranks a card played many times for small incremental effect.
  "dead_weight": In final deck but contributed little — should have been removed.
  "bad_pick": Taken during the run but rarely/never played. A deck-building mistake.
  Base roles on TRACEABLE evidence (damage/block/power attribution), not play count alone.
- coherence_score (0.0-1.0): How well do the final deck's cards work together?
  0.0-0.3: No clear strategy, random collection. 0.4-0.6: Has direction but significant dead weight or missing pieces. 0.7-0.8: Clear strategy, mostly synergistic, minor gaps. 0.9-1.0: Tight, focused deck with every card serving the win condition.
- coherence_analysis: 1 sentence. Name specific strengths and gaps.
- Respond with ONLY the JSON object."""


def _extract_json_object(raw_text: str) -> str:
    """Extract the first JSON object from an LLM response."""
    text = (raw_text or "").strip()
    if not text:
        return ""

    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text[3:]
        if text.endswith("```"):
            text = text[:-3]
        text = text.strip()

    start = text.find("{")
    if start < 0:
        return text

    depth = 0
    in_string = False
    escaped = False
    for idx in range(start, len(text)):
        ch = text[idx]
        if in_string:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == '"':
                in_string = False
            continue

        if ch == '"':
            in_string = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:idx + 1]

    return text[start:]


def _format_build_registry_for_llm(character: str) -> str:
    """Render active build constraints for the build-analysis prompt."""
    active = active_deck_builds(character)
    if not active:
        return "## Active Build Registry\n(no active builds registered for this character)"
    lines = [
        "## Active Build Registry",
        "Classify this run against these character-specific builds:",
    ]
    for tag in active:
        lines.append(f"- {tag}")
    lines.append(
        "If none match, return decision='reject_no_clear_build' and target_build_id=''."
    )
    return "\n".join(lines)


def _outcome_tag(evidence: dict[str, Any]) -> str:
    return "victory" if evidence.get("victory") else "defeat"


async def analyze_build_with_llm(
    evidence: dict[str, Any],
    *,
    combat_trace_text: str | None = None,
) -> dict[str, Any]:
    """Call the analysis-tier LLM to interpret build evidence.

    Args:
        evidence: Run evidence dict with character, victory, floor, deck, etc.
        combat_trace_text: Optional full round-by-round trace of recent combats.
            When provided, the trace is prepended directly to the user message
            (single-block content). The previous user_cached_prefix path was a
            no-op on the openai_compatible relay and is gone — see spec
            docs/superpowers/specs/2026-05-01-postrun-cache-cleanup-and-class-pool-injection-design.md.

    Returns a dict with build_summary, build_tags, primary_plan, etc.
    On failure, returns a minimal fallback dict with low confidence.
    """
    from src.brain.llm_caller import call_raw
    from src.knowledge.class_pool_injector import render_class_pool_section

    evidence_text = format_evidence_for_llm(evidence)
    character = normalize_character(str(evidence.get("character", "")))
    registry_text = _format_build_registry_for_llm(character)
    prompt = _BUILD_ANALYSIS_PROMPT.format(
        evidence_text=evidence_text,
        build_registry_text=registry_text,
    )

    pool_section = render_class_pool_section(character)
    system_prompt = (
        _BUILD_ANALYSIS_SYSTEM + "\n\n" + pool_section
        if pool_section else _BUILD_ANALYSIS_SYSTEM
    )

    # Inline the trace at the top of the user message when provided.
    if combat_trace_text:
        instruction_note = (
            "Additional context: a full round-by-round trace of the 1-2 most recent combats "
            "appears at the top of this user message (before the evidence block). Use it as ground "
            "truth for how the deck actually played when choosing build_summary / damage_engine / "
            "weak_points.\n\n"
        )
        prompt = combat_trace_text + "\n\n" + instruction_note + prompt

    raw_text = ""
    for attempt in range(2):
        try:
            raw_text, latency_ms, tokens = await call_raw(
                system_prompt,
                prompt,
                think=False,  # structured output, no need for extended thinking
                call_type="build_analysis",
            )
            logger.info(
                "Build analysis LLM call: %.0fms, %d tokens",
                latency_ms, tokens,
            )

            # Parse JSON from response
            text = _extract_json_object(raw_text)
            if not text:
                raise ValueError("empty build analysis response")
            analysis = json.loads(text)

            # Sanitize and constrain tags. Characters with an active registry
            # may only persist registered build ids plus the outcome tag.
            active = active_deck_builds(character)
            outcome = _outcome_tag(evidence)
            raw_target = str(
                analysis.get("target_build_id", "") or analysis.get("target_build", ""),
            )
            target = canonical_deck_build_tag(character, raw_target)
            if not target:
                for raw in analysis.get("build_tags", []) or []:
                    target = canonical_deck_build_tag(character, str(raw))
                    if target:
                        break
            if not target and analysis.get("primary_plan"):
                target = canonical_deck_build_tag(character, str(analysis.get("primary_plan")))

            if active:
                clean_tags = (target, outcome) if target else (outcome,)
                analysis["target_build_id"] = target
                analysis["primary_plan"] = target if target else "general"
            else:
                raw_tags = analysis.get("build_tags", [])
                clean_tags = tuple(
                    t.strip().lower().replace(" ", "_")
                    for t in raw_tags
                    if isinstance(t, str) and t.strip()
                )
            analysis["build_tags"] = clean_tags

            # Clamp confidence
            conf = analysis.get("confidence", 0.5)
            analysis["confidence"] = min(0.9, max(0.1, float(conf)))

            # Validate and normalize key_cards
            raw_key_cards = analysis.get("key_cards", [])
            clean_key_cards = []
            for kc in raw_key_cards:
                if isinstance(kc, dict) and "card" in kc:
                    role = kc.get("role", "utility")
                    if role not in _VALID_ROLES:
                        role = "utility"
                    clean_key_cards.append({
                        "card": kc["card"],
                        "role": role,
                        "insight": kc.get("insight", ""),
                    })
            analysis["key_cards"] = clean_key_cards

            # Clamp coherence score
            coh = analysis.get("coherence_score", 0.0)
            analysis["coherence_score"] = min(1.0, max(0.0, float(coh)))
            analysis["coherence_analysis"] = analysis.get("coherence_analysis", "")

            return analysis

        except Exception as exc:
            raw_preview = " ".join((raw_text or "").strip().split())[:240]
            if attempt == 0:
                logger.warning(
                    "Build analysis parse failed on attempt %d: %s%s",
                    attempt + 1,
                    exc,
                    f" | raw={raw_preview!r}" if raw_preview else "",
                )
                continue
            logger.warning("Build analysis LLM failed: %s", exc, exc_info=True)

    # Fallback: sparse output, no fake labels
    return {
        "decision": "reject_no_clear_build",
        "target_build_id": "",
        "build_summary": "",
        "primary_plan": "general",
        "damage_engine": "",
        "defense_engine": "",
        "cycle_engine": "",
        "energy_engine": "",
        "build_tags": ("defeat",) if not evidence.get("victory") else ("victory",),
        "card_roles": [],
        "weak_points": "",
        "confidence": 0.1,
        "key_cards": [],
        "coherence_score": 0.0,
        "coherence_analysis": "",
    }


# ── Primary tag extraction (for guide grouping) ────────────────

_OUTCOME_TAGS = frozenset({"victory", "defeat"})


def primary_tag(mem: CardBuildMemory) -> str:
    """Extract the primary build tag (first non-outcome tag).

    Used by guide consolidation for grouping memories.
    Falls back to primary_plan, then "general".
    """
    for tag in mem.build_tags:
        if tag not in _OUTCOME_TAGS:
            return tag
    if mem.primary_plan and mem.primary_plan != "general":
        return mem.primary_plan.lower().replace(" ", "_")
    return mem.archetype or "general"


# ── Main extraction function ────────────────────────────────────


def extract_card_build_memory(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
    final_deck: list[str],
    victory: bool,
    final_floor: int,
    fitness: float,
    build_analysis: dict[str, Any] | None = None,
    completion_reason: str = "completed",
    relics: list[str] | None = None,
    final_deck_payload: list[Any] | None = None,
    card_rules: dict[str, str] | None = None,
) -> CardBuildMemory:
    """Extract a CardBuildMemory from short-term memory.

    Args:
        build_analysis: LLM-generated analysis dict (from analyze_build_with_llm).
                        If None, build interpretation fields will be empty
                        (to be filled later by migration or async processing).

    Returns a frozen CardBuildMemory capturing the full deck trajectory.
    """
    # Convert mutable deck events to frozen
    deck_events = tuple(
        CardEvent(
            floor=e.floor,
            event_type=e.event_type,
            card_name=e.card_name,
            source=e.source,
        )
        for e in short_term.deck_events
    )

    play_counts_source = dict(short_term.card_play_counts)
    if not play_counts_source:
        play_counts_source = _derive_play_counts_from_combats(short_term)

    # Sort play counts by frequency (descending)
    play_counts = tuple(
        sorted(
            play_counts_source.items(),
            key=lambda x: x[1],
            reverse=True,
        )
    )

    # Extract evidence (deterministic)
    evidence = extract_build_evidence(
        short_term, character, final_deck, victory, final_floor, fitness,
        completion_reason=completion_reason,
        relics=relics,
        final_deck_payload=final_deck_payload,
        card_rules=card_rules,
    )

    # Use LLM analysis if provided, else empty (pending async backfill)
    analysis = build_analysis or {}
    build_tags = tuple(analysis.get("build_tags", ()))
    build_summary = analysis.get("build_summary", "")
    primary_plan = analysis.get("primary_plan", "")
    damage_engine = analysis.get("damage_engine", "")
    defense_engine = analysis.get("defense_engine", "")
    cycle_engine = analysis.get("cycle_engine", "")
    energy_engine = analysis.get("energy_engine", "")
    weak_points = analysis.get("weak_points", "")
    confidence = analysis.get("confidence", 0.0)
    key_cards = tuple(
        (kc["card"], kc["role"], kc.get("insight", ""))
        for kc in analysis.get("key_cards", [])
        if isinstance(kc, dict) and "card" in kc
    )
    coherence_score = analysis.get("coherence_score", 0.0)
    coherence_analysis = analysis.get("coherence_analysis", "")

    # Legacy archetype: primary_plan or first non-outcome tag
    legacy_archetype = primary_plan or next(
        (t for t in build_tags if t not in _OUTCOME_TAGS),
        "",
    )

    memory = CardBuildMemory(
        run_id=run_id,
        character=normalize_character(character),
        deck_events=deck_events,
        card_play_counts=play_counts,
        archetype=legacy_archetype,
        build_tags=build_tags,
        build_summary=build_summary,
        primary_plan=primary_plan,
        damage_engine=damage_engine,
        defense_engine=defense_engine,
        cycle_engine=cycle_engine,
        energy_engine=energy_engine,
        weak_points=weak_points,
        analysis_confidence=confidence,
        build_evidence=evidence,
        starting_deck=tuple(short_term.starting_deck),
        final_deck=tuple(final_deck),
        victory=victory,
        completion_reason=completion_reason,
        final_floor=final_floor,
        fitness=fitness,
        key_cards=key_cards,
        coherence_score=coherence_score,
        coherence_analysis=coherence_analysis,
    )

    logger.info(
        "Extracted card build: plan=%s, tags=%s, summary=%s (run %s)",
        primary_plan or "(pending)",
        build_tags or "(pending)",
        build_summary[:60] if build_summary else "(pending)",
        run_id[:8] if run_id else "?",
    )
    return memory
