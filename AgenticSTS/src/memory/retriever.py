"""Unified retriever: decision-type-aware memory retrieval.

Assembles a WorkingContext from domain-specific stores, guides, and
short-term memory. Per-decision-type token budgets keep prompts focused.
"""

from __future__ import annotations

import logging
import re
import time

import config
from src.memory.card_build_store import CardBuildStore
from src.memory.card_memory_store import CardMemoryStore
from src.memory.combat_store import CombatMemoryStore
from src.memory.deck_build_registry import active_deck_builds, canonical_deck_build_tag
from src.memory.enemy_keys import normalize_enemy_key, normalize_enemy_name
from src.memory.guide_store import GuideStore
from src.memory.hint_sanitizer import sanitize_deck_guide_text
from src.memory.models_v2 import WorkingContext
from src.memory.event_models import event_run_outcome_tag
from src.memory.route_store import RouteMemoryStore
from src.memory.short_term import ShortTermMemory
from src.state.game_state import GameState

logger = logging.getLogger(__name__)
_TAG_SLUG_RE = re.compile(r"[^a-z0-9]+")


# Strategic-thread relevance filtering used to live here as a second-pass
# regex over already-rendered ``- [{tag}] {body}`` lines. That filter was
# load-bearing only on this retrieval path — combat-start (loop.py) and the
# map / replay paths called ``get_strategic_thread`` directly and bypassed
# it entirely. The filter also misread the bracket text as a "scope" while
# ``get_strategic_thread`` rendered it as ``context_type``, so the regex
# silently dropped almost everything when it did run.
#
# The filter is now applied at the source (``ShortTermMemory.get_strategic_thread``
# via ``note.triggers``), so every caller sees the same filtered output. Per-
# state allow lists are derived from ``_CONTEXT_TYPE_TO_TRIGGERS`` /
# ``TRIGGER_STATE_MAP`` in ``short_term.py``.


def _render_event_guide_block(
    event_guide,
    current_option_titles: list[str],
    stage_index: int,
) -> str:
    """Render an event guide into a scored option library block.

    Filters ``event_guide.options`` to those whose ``stage_index`` matches
    the current stage (or all stages when stage_index == -1), sorts by
    score descending, and marks current-encounter options not found in
    the guide as 'not in guide — new or unseen'.

    Falls back to guide_text only when ``options`` is empty.
    """
    header = (
        f"## Event Guide: {event_guide.event_id} "
        f"({event_guide.character}, v{event_guide.version})"
    )
    lines = [header, event_guide.guide_text]

    if not event_guide.options:
        return "\n".join(lines)

    # Filter by stage (or all stages if stage_index is -1)
    if stage_index < 0:
        stage_options = list(event_guide.options)
    else:
        stage_options = [
            o for o in event_guide.options if o.stage_index == stage_index
        ]
        # Fallback: if nothing matches, show all (better than empty)
        if not stage_options:
            stage_options = list(event_guide.options)

    # Build canonical-name match for current encounter
    guide_names_lower = {
        o.canonical_name.strip().lower(): o for o in stage_options
    }
    seen_titles_lower = {t.strip().lower() for t in current_option_titles}

    matched = [
        o for o in stage_options
        if o.canonical_name.strip().lower() in seen_titles_lower
    ]
    matched.sort(key=lambda o: -o.score)

    unmatched_titles = [
        t for t in current_option_titles
        if t.strip().lower() not in guide_names_lower
    ]

    if matched or unmatched_titles:
        lines.append("")
        lines.append("Options for this encounter (score descending):")
        for o in matched:
            lines.append(
                f"- {o.canonical_name} [{o.variant_type}, "
                f"score {o.score:+.2f}, seen {o.sample_size}x]"
            )
            if o.analysis:
                lines.append(f"  {o.analysis}")
        for t in unmatched_titles:
            lines.append(f'- [Option "{t}" not in guide — new or unseen]')

    return "\n".join(lines)


# ── Decision type classification ──────────────────────────────

def _classify_decision_type(gs: GameState) -> str:
    """Map game state to decision type for retrieval."""
    if gs.is_combat:
        return "combat"
    if gs.is_map:
        return "route"
    if gs.state_type in ("card_reward", "card_select", "shop"):
        return "deck"
    if gs.state_type == "event":
        return "event"
    if gs.state_type == "rest_site":
        return "rest"
    return "other"


def _token_budget(decision_type: str) -> int:
    """Get token budget for a decision type."""
    budgets = {
        "combat": config.COMBAT_MEMORY_TOKENS,
        "route": config.ROUTE_MEMORY_TOKENS,
        "deck": config.DECK_MEMORY_TOKENS,
        "event": config.EVENT_MEMORY_TOKENS,
        "rest": config.REST_EVENT_MEMORY_TOKENS,
        "rest_event": config.REST_EVENT_MEMORY_TOKENS,  # backward compat
    }
    return budgets.get(decision_type, 150)


def _estimate_tokens(text: str) -> int:
    """Rough token estimate (1 token ~ 4 chars)."""
    return len(text) // 4


def _trim_hints(hints: tuple[str, ...], budget: int) -> tuple[str, ...]:
    """Trim hints to fit within token budget on coherent boundaries only.

    Previously this truncated mid-text with a trailing ``...`` which sliced
    Combat Guide / Past Experience content into incoherent fragments (e.g.
    ``...hits for 20 damage on its Pin...``). Now:

    - Hints that fit whole are admitted as-is.
    - Oversized multi-line hints (bulleted guides, mechanic summaries) are
      truncated at **line boundaries** — leading whole lines only, no
      partial tails, no ``...``.
    - Oversized single-line hints with multiple sentences are truncated at
      **sentence boundaries** (``. `` or ``! ``, ``? ``).
    - Otherwise the hint is dropped whole. Subsequent smaller hints are
      still considered (``continue``, not ``break``).
    """
    kept: list[str] = []
    used = 0
    for h in hints:
        tokens = _estimate_tokens(h)
        if used + tokens <= budget:
            kept.append(h)
            used += tokens
            continue

        remaining = budget - used
        if remaining <= 0:
            continue

        partial = _truncate_on_boundary(h, remaining)
        if partial:
            kept.append(partial)
            used += _estimate_tokens(partial)
    return tuple(kept)


def _truncate_on_boundary(text: str, budget: int) -> str:
    """Keep a leading coherent prefix of ``text`` that fits in ``budget`` tokens.

    Tries line boundaries first, then sentence boundaries. Never produces
    a mid-word cut or a trailing ``...``. Returns ``""`` if no whole
    boundary-delimited chunk fits.
    """
    if budget <= 0 or not text:
        return ""

    # Line-boundary attempt (for bulleted guides and multi-line summaries)
    if "\n" in text:
        lines = text.split("\n")
        kept_lines: list[str] = []
        used = 0
        for line in lines:
            tokens = _estimate_tokens(line)
            if kept_lines:
                tokens += 1  # newline
            if used + tokens > budget:
                break
            kept_lines.append(line)
            used += tokens
        if kept_lines:
            return "\n".join(kept_lines)

    # Sentence-boundary attempt for single-line content.
    # Split on ". ", "! ", "? " — keep delimiters attached to preceding sentence.
    import re as _re
    parts = _re.split(r"(?<=[.!?])\s+", text)
    kept_parts: list[str] = []
    used = 0
    for part in parts:
        tokens = _estimate_tokens(part)
        if kept_parts:
            tokens += 1  # space
        if used + tokens > budget:
            break
        kept_parts.append(part)
        used += tokens
    if kept_parts:
        return " ".join(kept_parts)

    return ""


# ── Offered card extraction ───────────────────────────────────


def _extract_offered_card_names(gs: GameState) -> list[str]:
    """Extract card names currently offered to the player.

    Works for card_reward, shop, and card_select state types.
    Returns card names stripped of '+' suffix for canonical matching.
    """
    names: list[str] = []
    st = gs.state_type

    if st == "card_reward":
        rw = gs.reward
        if rw and rw.pending_card_choice:
            for c in rw.card_options:
                name = c.name.rstrip("+").strip()
                if name:
                    names.append(name)

    elif st == "shop":
        shop = gs.shop
        if shop:
            for c in shop.cards:
                if c.is_stocked:
                    name = c.name.rstrip("+").strip()
                    if name:
                        names.append(name)

    elif st == "card_select":
        sel = gs.selection
        if sel and sel.cards:
            for c in sel.cards:
                name = c.name.rstrip("+").strip()
                if name:
                    names.append(name)

    return names


def _slug_tag(value: str) -> str:
    """Normalize a value into a compact trigger tag token."""
    return _TAG_SLUG_RE.sub("_", (value or "").strip().lower()).strip("_")


def _add_tag(tags: set[str], prefix: str, value: str | int | None) -> None:
    if value is None:
        return
    slug = _slug_tag(str(value))
    if slug:
        tags.add(f"{prefix}:{slug}")


def _coerce_positive_int(value: object) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError):
        return 0
    return coerced if coerced > 0 else 0


def _build_common_rule_tags(gs: GameState, decision_type: str) -> set[str]:
    """Build cross-cutting trigger tags for rule lookup."""
    tags: set[str] = set()
    _add_tag(tags, "decision", decision_type)
    _add_tag(tags, "state", gs.state_type)
    _add_tag(tags, "character", gs.character or "")
    act = _coerce_positive_int(getattr(gs, "act", 0))
    if not act and getattr(gs, "run", None) is not None:
        act = _coerce_positive_int(getattr(gs.run, "act", 0))
    if act:
        _add_tag(tags, "act", act)

    hp = _coerce_positive_int(getattr(gs, "player_hp", 0))
    max_hp = _coerce_positive_int(getattr(gs, "player_max_hp", 0))
    if max_hp > 0:
        ratio = hp / max_hp
        hp_bucket = "critical" if ratio <= 0.3 else "low" if ratio <= 0.5 else "healthy"
        _add_tag(tags, "hp", hp_bucket)

    return tags


def _tag_cards(tags: set[str], card_names: list[str] | tuple[str, ...]) -> None:
    for name in card_names:
        _add_tag(tags, "card", name)


def _extract_deck_card_names(gs: GameState) -> list[str]:
    deck = []
    if getattr(gs, "run", None) is not None and getattr(gs.run, "deck", None):
        deck = list(gs.run.deck)
    elif getattr(gs, "deck", None):
        deck = list(gs.deck)

    names: list[str] = []
    for card in deck:
        name = getattr(card, "name", "") if not isinstance(card, str) else card
        if name:
            names.append(str(name).rstrip("+").strip())
    return names


_SHIV_SIGNAL_TERMS = frozenset({
    "shiv", "blade dance", "cloak and dagger", "accuracy", "infinite blades",
    "finisher", "hidden daggers", "phantom blades",
})

_POISON_SIGNAL_TERMS = frozenset({
    "poison", "noxious fumes", "deadly poison", "bouncing flask", "catalyst",
    "envenom", "poisoned stab", "snakebite", "bubble bubble", "outbreak",
    "accelerant",
})


def _has_any_signal(text: str, terms: frozenset[str]) -> bool:
    return any(term in text for term in terms)


def _deck_guide_candidate_tags(
    character: str,
    archetype: str,
    gs: GameState,
    short_term: ShortTermMemory,
    card_memory_store: CardMemoryStore | None = None,
) -> list[str]:
    """Infer active deck-guide candidates from current run context.

    This intentionally does not return ``general``. If no active build signal
    exists, deck decisions rely on the two-phase framework and card memories.
    """
    raw_candidates: list[str] = []
    if archetype:
        raw_candidates.append(archetype)

    names = _extract_deck_card_names(gs) + _extract_offered_card_names(gs)
    text_parts = [" ".join(names).lower()]
    try:
        thread = short_term.get_strategic_thread(
            max_entries=5, current_context=getattr(gs, "state_type", ""),
        )
    except Exception:
        thread = ""
    if isinstance(thread, str):
        text_parts.append(thread.lower())
    context_text = "\n".join(part for part in text_parts if part)

    if _has_any_signal(context_text, _SHIV_SIGNAL_TERMS):
        raw_candidates.append("shiv")
    if _has_any_signal(context_text, _POISON_SIGNAL_TERMS):
        raw_candidates.append("poison")

    # Keep registered builds available for exact text mentions in future
    # characters without hard-coding card names in this module.
    for tag in active_deck_builds(character):
        if tag and tag in context_text:
            raw_candidates.append(tag)

    if card_memory_store and character:
        for mem in card_memory_store.query_cards(character, names):
            for obs in mem.build_role_observations:
                build_id = str(obs.get("build_id", ""))
                if build_id:
                    raw_candidates.append(build_id)

    candidates: list[str] = []
    seen: set[str] = set()
    for raw in raw_candidates:
        tag = canonical_deck_build_tag(character, raw)
        if tag and tag not in seen:
            candidates.append(tag)
            seen.add(tag)
    return candidates


def _add_runtime_signals(tags: set[str], gs: GameState, short_term: ShortTermMemory) -> None:
    """Attach simple, runtime-computable signal tags for rule triggering."""
    act = _coerce_positive_int(getattr(gs, "act", 0))
    floor = _coerce_positive_int(getattr(gs, "floor", 0))
    if not floor and getattr(gs, "run", None) is not None:
        floor = _coerce_positive_int(getattr(gs.run, "floor", 0))
    if act == 1 and floor >= 15:
        _add_tag(tags, "signal", "late_act1")

    deck_names = [name.lower() for name in _extract_deck_card_names(gs)]
    if deck_names:
        starter_like = sum(1 for name in deck_names if name in {"strike", "defend"})
        if starter_like / max(len(deck_names), 1) >= 0.35:
            _add_tag(tags, "signal", "starter_dense")

        silent_aoe_cards = {
            "bouncing flask", "corpse explosion", "die die die", "blade dance",
            "dagger spray", "crippling cloud", "all out attack", "cloak and dagger",
        }
        if not any(name in silent_aoe_cards for name in deck_names):
            _add_tag(tags, "signal", "aoe_missing")

    recent = short_term.completed_combats[-1] if short_term.completed_combats else None
    if recent is not None:
        if recent.total_rounds >= 8:
            _add_tag(tags, "signal", "last_combat_long")
        if recent.total_rounds >= 12:
            _add_tag(tags, "signal", "last_combat_very_long")
        hp_lost = max(0, recent.hp_before - recent.hp_after)
        if hp_lost >= 10:
            _add_tag(tags, "signal", "last_combat_costly")
        if hp_lost >= 20:
            _add_tag(tags, "signal", "last_combat_very_costly")
        if recent.enemy_key.startswith("multi:"):
            _add_tag(tags, "signal", "last_multi_enemy")


# ── Retriever ─────────────────────────────────────────────────


def query_for_decision(
    gs: GameState,
    short_term: ShortTermMemory,
    combat_store: CombatMemoryStore,
    route_store: RouteMemoryStore,
    card_build_store: CardBuildStore,
    guide_store: GuideStore,
    *,
    card_memory_store: CardMemoryStore | None = None,
    event_store=None,  # EventMemoryStore | None
    archetype: str = "",  # Legacy: was tracker-detected, now "" (general matching)
    current_round: int = 0,  # For situation-aware combat retrieval
) -> WorkingContext:
    """Assemble a WorkingContext for the current decision.

    Priority per decision type:
    - Combat: Guide > Episodes > Rules > Short-term timeline
    - Route:  Guide > Route memories > Rules
    - Deck:   Guide > Build memories > Rules
    - Rest/Event: Rules > Reflections
    """
    start = time.monotonic()
    decision_type = _classify_decision_type(gs)
    budget = _token_budget(decision_type)

    character = gs.character or ""

    combat_guide_hints: list[str] = []
    enemy_pattern_hints: list[str] = []
    situation_hints: list[str] = []
    route_guide_hints: list[str] = []
    route_memory_hints: list[str] = []
    deck_guide_hints: list[str] = []
    deck_memory_hints: list[str] = []
    card_memory_hints: list[str] = []
    short_term_hints: list[str] = []
    event_memory_hints: list[str] = []
    # Progressive injection metadata — set inside combat branch, defaults for all other paths
    _inject_round: int = 0
    _inject_threat: str = ""

    if decision_type == "combat":
        enemy_key = ""
        combat_type = gs.state_type
        if gs.enemies:
            names = [normalize_enemy_name(e.name) for e in gs.enemies]
            enemy_key = normalize_enemy_key(
                names[0] if len(names) == 1 else "multi:" + "+".join(sorted(names))
            )

        # 1. Guide (highest priority)
        guide = guide_store.get_combat_guide(enemy_key, character)
        if guide and guide.confidence >= 0.3:
            combat_guide_hints.append(
                f"[Guide: {guide.enemy_key}] {guide.guide_text}"
            )

        # 2. Enemy patterns (behavior sequences, not win/loss)
        from src.brain.enemy_pattern_injector import format_enemy_patterns
        episodes = combat_store.query(
            enemy_key=enemy_key,
            character=character,
            combat_type=combat_type,
            limit=5,
        )
        if episodes:
            pattern_text = format_enemy_patterns(episodes, current_round=max(1, current_round))
            if pattern_text:
                enemy_pattern_hints.append(pattern_text)

        # 2b. Situation-level round retrieval
        _inject_round = current_round  # decision_type is always "combat" here

        if current_round > 0:
            from src.brain.prompts._intent_fmt import is_move_id_like
            from src.memory.situation import format_enemy_behavior_summary

            readable_episodes = [
                ep for ep in episodes
                if any(
                    rnd.enemy_intents
                    and not any(is_move_id_like(intent) for intent in rnd.enemy_intents)
                    for rnd in ep.rounds
                )
            ]

            if (
                current_round >= 1
                and guide is not None
                and guide.episode_count >= 2
                and len(readable_episodes) >= 2
            ):
                mechanic_summary = guide.mechanic_summary
                behavior_summary = format_enemy_behavior_summary(mechanic_summary)
                if behavior_summary:
                    situation_hints.append(behavior_summary)

    elif decision_type == "route":
        act = _coerce_positive_int(getattr(gs, "act", 0))
        if not act and getattr(gs, "run", None) is not None:
            act = _coerce_positive_int(getattr(gs.run, "act", 0))

        guide = guide_store.get_route_guide(act, character)
        if guide and guide.confidence >= 0.3:
            route_guide_hints.append(
                f"[Route Guide Act {guide.act}] {guide.guide_text}"
            )

        memories = route_store.query(act=act, character=character, limit=2)
        for mem in memories:
            node_types = [n.node_type for n in mem.nodes]
            path_str = "→".join(node_types[:6])
            result = f"boss:{mem.boss_result}" if mem.boss_result != "not_reached" else "incomplete"
            route_memory_hints.append(
                f"Past Act{mem.act}: {path_str} | HP {mem.hp_start}→{mem.hp_end} | {result}"
            )

    elif decision_type == "deck":
        deck_archetypes = _deck_guide_candidate_tags(
            character, archetype, gs, short_term, card_memory_store,
        )
        deck_archetype = deck_archetypes[0] if deck_archetypes else ""

        for tag in deck_archetypes:
            guide = guide_store.get_deck_guide(character, tag)
            if guide and guide.confidence >= 0.3:
                sanitized_guide = sanitize_deck_guide_text(guide.guide_text)
                if sanitized_guide:
                    deck_guide_hints.append(
                        f"[Deck Guide: {guide.archetype}] {sanitized_guide}"
                    )
                break

        memory_archetype = deck_archetype or canonical_deck_build_tag(character, archetype)
        memories = card_build_store.query(
            character=character, archetype=memory_archetype, limit=2,
        )
        for mem in memories:
            top_cards = ", ".join(f"{n}({c})" for n, c in mem.card_play_counts[:3])
            parts = [
                f"F{mem.final_floor}",
                f"Top: {top_cards}" if top_cards else None,
                f"{'WIN' if mem.victory else 'LOSS'}",
            ]
            # Surface richer analysis when available
            if mem.primary_plan:
                parts.insert(0, f"Plan: {mem.primary_plan}")
            if mem.damage_engine:
                parts.append(f"Dmg: {mem.damage_engine}")
            if mem.weak_points:
                parts.append(f"Weak: {mem.weak_points}")
            if mem.analysis_confidence > 0:
                parts.append(f"conf={mem.analysis_confidence:.1f}")
            deck_memory_hints.append(
                f"Past build: {' | '.join(p for p in parts if p)}"
            )

        offered_names = _extract_offered_card_names(gs)

        # Per-card memory: only inject for currently offered cards.
        # Hint priority: postrun core-engine observations (recent wins) first,
        # then the static/seed note. This surfaces concrete archetype
        # knowledge (kept OUT of the system prompt by design) in the
        # exact decision where it matters.
        if card_memory_store and character:
            if offered_names:
                from src.memory.build_role_memory import format_build_role_hint
                from src.memory.core_engine_extractor import format_core_engine_hint
                card_mems = card_memory_store.query_cards(character, offered_names)
                for cm in card_mems:
                    build_role_hint = format_build_role_hint(cm, tuple(deck_archetypes))
                    engine_hint = format_core_engine_hint(cm)
                    note = cm.effective_note()
                    if build_role_hint:
                        card_memory_hints.append(f"{cm.card_name}: {build_role_hint}")
                    if engine_hint:
                        card_memory_hints.append(f"{cm.card_name}: {engine_hint}")
                    if note:
                        card_memory_hints.append(f"{cm.card_name}: {note}")

    elif decision_type == "event":
        # Event-specific retrieval. Prefer the consolidated event guide; only
        # fall back to raw past-episode bullets when no guide exists yet — the
        # guide already summarizes those episodes, so emitting both is
        # redundant and can confuse the LLM with stale option text from
        # earlier game versions.
        rendered_guide: str | None = None
        current_option_titles: list[str] = []
        if gs.event:
            current_option_titles = [
                getattr(o, "title", "") for o in (gs.event.options or [])
            ]
            event_guide = guide_store.get_event_guide(gs.event.event_id, character)
            if event_guide and event_guide.confidence >= 0.3:
                # Stage detection: default to 0 for the initial page; if the
                # event is flagged finished (final "Proceed" page), treat as
                # closing and render the whole library as contextual reference.
                stage_index = 0 if not getattr(gs.event, "is_finished", False) else -1
                rendered_guide = _render_event_guide_block(
                    event_guide, current_option_titles, stage_index,
                )

        if rendered_guide:
            event_memory_hints.append(rendered_guide)
        elif event_store is not None and gs.event:
            past_events = event_store.query(
                event_id=gs.event.event_id,
                character=character,
                limit=3,
            )
            current_titles_set = {t for t in current_option_titles if t}
            for em in past_events:
                # Drop episodes whose chosen option text no longer matches any
                # current option (e.g. event text was rewritten in a patch).
                if (
                    current_titles_set
                    and em.chosen_option_text
                    and em.chosen_option_text not in current_titles_set
                ):
                    continue
                event_memory_hints.append(
                    f"{em.event_title} (Act{em.act} F{em.floor}): "
                    f"Chose \"{em.chosen_option_text}\".{event_run_outcome_tag(em)}"
                )

    # Strategic thread (replaces per-decision-type STM facts).
    # ``get_strategic_thread`` already filters by ``note.triggers`` against
    # the current state_type — the redundant post-render scope regex was
    # removed in favor of source-side filtering.
    thread = short_term.get_strategic_thread(
        max_entries=5, current_context=gs.state_type,
    )
    if thread:
        short_term_hints = [thread]

    # Assemble and trim to budget
    wc = WorkingContext(
        combat_guide_hints=tuple(combat_guide_hints),
        enemy_pattern_hints=tuple(enemy_pattern_hints),
        route_guide_hints=tuple(route_guide_hints),
        route_memory_hints=tuple(route_memory_hints),
        deck_guide_hints=tuple(deck_guide_hints),
        deck_memory_hints=tuple(deck_memory_hints),
        card_memory_hints=tuple(card_memory_hints),
        short_term_hints=tuple(short_term_hints),
        situation_hints=tuple(situation_hints),
        event_memory_hints=tuple(event_memory_hints),
        current_round=_inject_round,
        current_threat_level=_inject_threat,
    )

    # Apply budget trimming if needed
    if wc.estimated_tokens() > budget:
        wc = _trim_working_context(wc, budget)

    # Apply total ceiling
    if wc.estimated_tokens() > config.MEMORY_TOTAL_TOKEN_CEILING:
        wc = _trim_working_context(wc, config.MEMORY_TOTAL_TOKEN_CEILING)

    elapsed_ms = (time.monotonic() - start) * 1000
    if not wc.is_empty:
        logger.debug(
            "HCM retrieval [%s]: %d hints (%d tokens est.) in %.1fms",
            decision_type, wc.total_hints, wc.estimated_tokens(), elapsed_ms,
        )

    return wc


def _trim_working_context(wc: WorkingContext, budget: int) -> WorkingContext:
    """Trim WorkingContext to fit within token budget.

    Priority: guides > episodes/memories > short_term
    (Lowest priority trimmed first.)
    """
    # Build prioritized list (lowest priority first = trimmed first).
    # Keep offered-card notes highest within deck decisions so they survive
    # even when generic guide/history context is long.
    all_fields = [
        ("enemy_pattern_hints", wc.enemy_pattern_hints),
        ("route_memory_hints", wc.route_memory_hints),
        ("deck_memory_hints", wc.deck_memory_hints),
        ("short_term_hints", wc.short_term_hints),
        ("combat_guide_hints", wc.combat_guide_hints),
        ("situation_hints", wc.situation_hints),  # keep mechanics before guide when space is tight
        ("route_guide_hints", wc.route_guide_hints),
        ("deck_guide_hints", wc.deck_guide_hints),
        ("card_memory_hints", wc.card_memory_hints),
        ("event_memory_hints", wc.event_memory_hints),  # event guide + past events = top signal for event decisions
    ]

    # Start from highest priority, accumulate tokens
    kept: dict[str, tuple[str, ...]] = {}
    used = 0

    for field_name, hints in reversed(all_fields):
        remaining = budget - used
        trimmed = _trim_hints(hints, remaining)
        kept[field_name] = trimmed
        used += sum(_estimate_tokens(h) for h in trimmed)

    return WorkingContext(
        combat_guide_hints=kept.get("combat_guide_hints", ()),
        enemy_pattern_hints=kept.get("enemy_pattern_hints", ()),
        route_guide_hints=kept.get("route_guide_hints", ()),
        route_memory_hints=kept.get("route_memory_hints", ()),
        deck_guide_hints=kept.get("deck_guide_hints", ()),
        deck_memory_hints=kept.get("deck_memory_hints", ()),
        card_memory_hints=kept.get("card_memory_hints", ()),
        short_term_hints=kept.get("short_term_hints", ()),
        situation_hints=kept.get("situation_hints", ()),
        event_memory_hints=kept.get("event_memory_hints", ()),
        current_round=wc.current_round,
        current_threat_level=wc.current_threat_level,
    )
