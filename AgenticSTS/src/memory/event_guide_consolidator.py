"""Event guide consolidation — run-scoped refresh + scored option library.

Extracted from ``src/memory/guide_consolidator.py`` on 2026-04-24 to keep
that file under the codebase's maintainability ceiling. The main
``consolidate_guides`` orchestrator in ``guide_consolidator`` now delegates
its event branch to ``consolidate_event_guides`` here.

See ``docs/superpowers/specs/2026-04-24-event-guide-consolidation-rework-design.md``.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from src.memory import guide_consolidation_log
from src.memory.event_models import (
    EventGuide,
    EventGuideOption,
    EventMemory,
    EventOptionSnapshot,
    event_run_outcome_tag,
)
from src.memory.models_v2 import normalize_character

logger = logging.getLogger(__name__)


EVENT_ANALYST_PROMPT = (
    "You are a Slay the Spire 2 strategy analyst. "
    "Analyze event decisions and produce event guides."
)


_EVENT_PROMPT_MAX_PLAYTHROUGHS = 12


# ── Selection ────────────────────────────────────────────────


def _select_event_keys_for_refresh(
    memories: list[EventMemory],
    current_run_id: str,
) -> set[tuple[str, str]]:
    """Pick (event_id, character) keys whose guides should refresh this postrun.

    Policy (mirrors combat refresh, simpler): only events encountered in the
    current run are selected. Cross-run / cross-character refresh is not
    performed — LLM cost is spent only on pairs the run actually produced
    evidence for.

    Keys are returned with uppercase ``event_id`` and normalized
    ``character`` so downstream equality matches the guide store.
    """
    selected: set[tuple[str, str]] = set()
    for em in memories:
        if em.run_id != current_run_id:
            continue
        selected.add((
            em.event_id.upper(),
            normalize_character(em.character),
        ))
    return selected


# ── Prompt helpers ───────────────────────────────────────────


def _format_reward_line(kind: str, reward: Any) -> str:
    """Render one reward entry (relic/card/potion) with full detail."""
    name = getattr(reward, "name", "") or ""
    if kind == "relic":
        rarity = getattr(reward, "rarity", "") or ""
        desc = getattr(reward, "description", "") or ""
        parts = [f"[relic] {name}"]
        if rarity:
            parts.append(f"(rarity={rarity})")
        if desc:
            parts.append(f"— {desc}")
        return " ".join(parts)
    if kind == "card":
        card_type = getattr(reward, "card_type", "") or ""
        cost = getattr(reward, "cost", 0)
        upgraded = getattr(reward, "upgraded", False)
        rules = getattr(reward, "rules_text", "") or ""
        upg_mark = "+" if upgraded else ""
        parts = [f"[card]  {name}{upg_mark}"]
        if card_type:
            parts.append(f"type={card_type}")
        parts.append(f"cost={cost}")
        if rules:
            parts.append(f"— {rules}")
        return " ".join(parts)
    if kind == "potion":
        potion_type = getattr(reward, "potion_type", "") or ""
        desc = getattr(reward, "description", "") or ""
        parts = [f"[potion] {name}"]
        if potion_type:
            parts.append(f"(type={potion_type})")
        if desc:
            parts.append(f"— {desc}")
        return " ".join(parts)
    return name


def _format_option_full(opt: EventOptionSnapshot) -> list[str]:
    """Render one option with every reward expanded. Returns a list of
    rendered lines (indented by caller)."""
    lines = [f'[{opt.index}] {opt.title} — {opt.description}']
    for r in opt.relics_offered:
        lines.append(_format_reward_line("relic", r))
    for c in opt.cards_offered:
        lines.append(_format_reward_line("card", c))
    for p in opt.potions_offered:
        lines.append(_format_reward_line("potion", p))
    if opt.hp_cost is not None:
        lines.append(f"(hp_cost={opt.hp_cost})")
    if opt.gold_cost is not None:
        lines.append(f"(gold_cost={opt.gold_cost})")
    return lines


def _option_seen_key(opt: EventOptionSnapshot, stage_index: int) -> tuple[int, str]:
    """Dedup key: (stage_index, option title). Case-insensitive title."""
    return (stage_index, (opt.title or "").strip().lower())


def _group_playthroughs(
    memories: list[EventMemory],
) -> list[list[EventMemory]]:
    """Group memories by (run_id, floor) into playthroughs, ordered stages
    within group by timestamp; return playthroughs sorted by max-timestamp
    descending (most recent first)."""
    groups: dict[tuple[str, int], list[EventMemory]] = {}
    for em in memories:
        groups.setdefault((em.run_id, em.floor), []).append(em)
    playthroughs = []
    for _key, stages in groups.items():
        stages_sorted = sorted(stages, key=lambda m: m.timestamp)
        playthroughs.append(stages_sorted)
    playthroughs.sort(
        key=lambda stages: max(m.timestamp for m in stages),
        reverse=True,
    )
    return playthroughs


def build_event_guide_prompt(
    event_id: str,
    character: str,
    memories: list[EventMemory],
    existing: EventGuide | None = None,
) -> str:
    """Build a stage-aware, knowledge-rich event guide prompt.

    Memories are grouped by (run_id, floor) into playthroughs; stages
    within a playthrough are ordered by timestamp. Reward details are
    expanded on first occurrence across the prompt; repeat occurrences
    render as ``(same as Playthrough K)``. Capped to the
    ``_EVENT_PROMPT_MAX_PLAYTHROUGHS`` most recent playthroughs.

    Output spec instructs the LLM to emit structured
    ``{guide_text, confidence, options: [...]}`` with ``options`` matching
    ``EventGuideOption``.
    """
    playthroughs = _group_playthroughs(memories)[:_EVENT_PROMPT_MAX_PLAYTHROUGHS]

    lines: list[str] = [
        f"Event: {event_id} | Character: {character} | "
        f"Playthroughs: {len(playthroughs)} (of {len(memories)} total memories)",
        "",
    ]

    # Track first playthrough index that expanded each option fully.
    seen_options: dict[tuple[int, str], int] = {}

    for pt_idx, stages in enumerate(playthroughs, start=1):
        first_stage = stages[0]
        run_prefix = first_stage.run_id[:6] if first_stage.run_id else "?"
        outcome_tag = event_run_outcome_tag(first_stage).strip()
        if outcome_tag.startswith("[") and outcome_tag.endswith("]"):
            outcome_tag = outcome_tag[1:-1]
        lines.append(
            f"Playthrough {pt_idx} (run={run_prefix}, F{first_stage.floor}, "
            f"{outcome_tag or 'outcome=UNKNOWN'}):"
        )
        for stage_idx, em in enumerate(stages):
            n_opts = len(em.all_option_details) or len(em.all_options)
            lines.append(f"  Stage {stage_idx}: Choose 1 of {n_opts}")
            for opt in em.all_option_details:
                key = _option_seen_key(opt, stage_idx)
                first_pt = seen_options.get(key)
                if first_pt is None:
                    seen_options[key] = pt_idx
                    for rendered in _format_option_full(opt):
                        lines.append(f"    {rendered}")
                else:
                    lines.append(
                        f"    [{opt.index}] {opt.title}  "
                        f"(same as Playthrough {first_pt})"
                    )
            diff_parts = [
                f"HP {em.hp_before}→{em.hp_after}",
                f"Gold {em.gold_before}→{em.gold_after}",
            ]
            if em.cards_gained:
                diff_parts.append(f"+{list(em.cards_gained)}")
            if em.cards_lost:
                diff_parts.append(f"-{list(em.cards_lost)}")
            if em.relics_gained:
                diff_parts.append(f"relics+{list(em.relics_gained)}")
            if em.potions_gained:
                diff_parts.append(f"potions+{list(em.potions_gained)}")
            lines.append(
                f"    → chose [{em.chosen_option_index}] "
                f"'{em.chosen_option_text}', diff: {', '.join(diff_parts)}"
            )
        lines.append("")

    if existing:
        lines.append(f"Previous guide (v{existing.version}): {existing.guide_text}")
        if existing.options:
            lines.append("Previous options (update in place where relevant):")
            for o in existing.options:
                lines.append(
                    f"  - {o.canonical_name} [stage={o.stage_index}, "
                    f"{o.variant_type}, score={o.score:+.2f}, n={o.sample_size}]: "
                    f"{o.analysis}"
                )
        lines.append("")

    lines.extend([
        "Task: Build the option library for this event.",
        "",
        "Respond with JSON ONLY (no markdown fences):",
        "{",
        '  "guide_text": "<1-2 sentences: cross-option takeaway>",',
        '  "confidence": <0.0-1.0>,',
        '  "options": [',
        "    {",
        '      "canonical_name": "<name>",',
        '      "stage_index": <int 0-based>,',
        '      "variant_type": "fixed | random_from_pool | deck_random",',
        '      "score": <-1.0 to 1.0>,',
        '      "analysis": "<1-2 sentence rationale>",',
        '      "observed_rewards": ["<name>", "..."],',
        '      "sample_size": <int>',
        "    }",
        "  ]",
        "}",
        "",
        "Guidelines:",
        "- fixed: option outcome is deterministic across encounters.",
        "- random_from_pool: option rewards a roll from a fixed pool "
        '(e.g. "a random Uncommon relic"). Merge variants under one entry '
        'and enumerate concrete rolls in observed_rewards.',
        "- deck_random: option transforms/affects a random card from your deck.",
        "- score: weight by run outcome anchor (VICTORY>DEFEAT), concrete "
        "state-diff gain (HP/gold/cards/relics), and cross-encounter stability.",
        "- Do NOT invent options not seen in any playthrough.",
        "- Do NOT output options for stages that contained only a single "
        '"Proceed" button — those are closing pages and carry no signal.',
    ])
    return "\n".join(lines)


# ── Response parsing ─────────────────────────────────────────


def _count_option_appearances(
    canonical_name: str,
    memories: list[EventMemory],
) -> int:
    """Count memories where at least one option title matches canonical_name
    case-insensitively."""
    needle = canonical_name.strip().lower()
    if not needle:
        return 0
    count = 0
    for em in memories:
        titles: set[str] = {
            (od.title or "").strip().lower() for od in em.all_option_details
        }
        titles.update((t or "").strip().lower() for t in em.all_options)
        if needle in titles:
            count += 1
    return count


def parse_event_guide_response(
    raw: str,
    event_id: str,
    character: str,
    episode_count: int,
    memories: list[EventMemory],
    existing_guide: EventGuide | None = None,
) -> EventGuide | None:
    """Parse LLM response into an EventGuide with structured options.

    Server-side overrides:
      - ``sample_size`` is recomputed from ``memories`` (LLM value ignored).
      - ``score`` is clamped to [-1.0, 1.0].
      - ``confidence`` is clamped to [0.0, 1.0].

    Malformed option entries are skipped; valid siblings survive. A response
    lacking an ``options`` key is accepted (legacy guide shape) and yields
    ``EventGuide.options == ()``.
    """
    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    guide_text = data.get("guide_text", "")
    if not guide_text:
        return None

    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.0)))
    version = (existing_guide.version + 1) if existing_guide else 1

    raw_options = data.get("options", []) or []
    parsed_options: list[EventGuideOption] = []
    for entry in raw_options:
        if not isinstance(entry, dict):
            continue
        canonical = (entry.get("canonical_name") or "").strip()
        if not canonical:
            continue
        variant = entry.get("variant_type", "fixed")
        if variant not in ("fixed", "random_from_pool", "deck_random"):
            variant = "fixed"
        try:
            score = float(entry.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(-1.0, min(1.0, score))
        try:
            stage_idx = int(entry.get("stage_index", 0) or 0)
        except (TypeError, ValueError):
            stage_idx = 0
        observed = tuple(
            str(x) for x in (entry.get("observed_rewards") or ())
            if isinstance(x, (str, int, float))
        )
        # Server-side sample_size: override LLM claim.
        sample_size = _count_option_appearances(canonical, memories)
        parsed_options.append(EventGuideOption(
            canonical_name=canonical,
            stage_index=stage_idx,
            variant_type=variant,
            score=score,
            analysis=(entry.get("analysis") or "").strip(),
            observed_rewards=observed,
            sample_size=sample_size,
        ))

    return EventGuide(
        event_id=event_id.upper(),
        character=normalize_character(character),
        guide_text=guide_text,
        options=tuple(parsed_options),
        episode_count=episode_count,
        confidence=confidence,
        version=version,
    )


# ── Orchestration ────────────────────────────────────────────


async def consolidate_event_guides(
    memory_manager,
    *,
    current_run_id: str,
    min_episodes: int,
    llm_call_raw,
) -> int:
    """Run the event branch of guide consolidation. Returns count of guides
    created/updated.

    ``llm_call_raw`` is injected (rather than imported at module scope) so
    tests can monkeypatch the LLM call site exactly as they do for the
    parent orchestrator.
    """
    event_store = getattr(memory_manager, "event_store", None)
    guide_store = memory_manager.guide_store
    if not event_store:
        return 0

    all_event_memories = event_store.get_all()
    selected_event_keys = _select_event_keys_for_refresh(
        all_event_memories, current_run_id,
    )

    updated = 0
    for (event_id, character) in sorted(selected_event_keys):
        memories = [
            m for m in all_event_memories
            if m.event_id.upper() == event_id
            and normalize_character(m.character) == character
        ]
        existing = guide_store.get_event_guide(event_id, character)

        # First-encounter bypass: skip min_episodes gate when no existing guide.
        # EventMemory has no is_aborted field today; non-aborted check is a
        # defensive getattr in case the model gains the field later.
        non_aborted = [m for m in memories if not getattr(m, "is_aborted", False)]
        if existing is None and len(non_aborted) >= 1:
            pass
        elif len(memories) < min_episodes:
            continue
        prompt = build_event_guide_prompt(event_id, character, memories, existing)
        try:
            raw, _latency, _tokens = await llm_call_raw(
                EVENT_ANALYST_PROMPT,
                prompt,
                think=True,
                call_type="guide_event",
            )
            guide = parse_event_guide_response(
                raw,
                event_id,
                character,
                len(memories),
                memories,
                existing,
            )
            if guide:
                guide_store.set_event_guide(guide)
                guide_consolidation_log.append_event(
                    event_id=guide.event_id,
                    character=guide.character,
                    version=guide.version,
                    memory_count=len(memories),
                )
                updated += 1
                logger.info(
                    "Consolidated event guide: %s (%s) v%d "
                    "(%d options, %d memories)",
                    event_id,
                    character,
                    guide.version,
                    len(guide.options),
                    len(memories),
                )
        except Exception:
            logger.warning(
                "Event guide consolidation failed for %s",
                event_id,
                exc_info=True,
            )

    return updated
