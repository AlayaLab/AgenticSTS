"""Tool handlers + prompts for the evolution stage.

Spec #4 module split: these handlers used to live as methods of
EvolutionEngine. They moved here as the largest concentration of LOC
in the original file. Each retains a 2-line delegator on the class so
existing test code (engine._handle_write_skill, etc.) continues to
work.

The dispatchers (_execute_tool, _execute_write_tool) STAY on
EvolutionEngine and call self._handle_*(...), which delegates here
via the class delegators. The extra hop is a single Python frame
per tool call; negligible.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


# ── Prompt helpers ──────────────────────────────────────────────


def phase_system_prompt(is_read_phase: bool) -> str:
    """(Extracted from EvolutionEngine._phase_system_prompt — staticmethod.)

    Spec #3 §3.3: the prompt is invariant across phases for prompt-cache
    stability. is_read_phase is retained for back-compat but unused.
    """
    # deferred: avoids circular import (evolution_engine ↔ evolution_handlers)
    from src.brain.evolution_engine import EVOLUTION_SYSTEM_PROMPT
    return EVOLUTION_SYSTEM_PROMPT


def continuation_prompt(
    *,
    next_is_read_phase: bool,
    has_mutating_actions: bool,
    enforce_target_tokens: bool,
    target_input_tokens: int,
    total_input_tokens: int,
    min_rounds: int,
    round_number: int,
) -> str:
    """(Extracted from EvolutionEngine._continuation_prompt — staticmethod.)

    Build a per-round continuation instruction for the evolution LLM.
    """
    remaining = max(0, target_input_tokens - total_input_tokens)
    token_clause = (
        f" with about {remaining} input tokens still needed before the session can conclude."
        if enforce_target_tokens
        else "."
    )
    if next_is_read_phase:
        return (
            "Continue the diagnosis. Use another read/query tool to deepen the evidence. "
            f"You are at round {round_number}/{min_rounds}{token_clause}"
        )
    if not has_mutating_actions:
        return (
            "Diagnosis is sufficient. Move to execution now. "
            "Call the single highest-value mutating tool next: write_skill or author_tool. "
            "Only do another read query if it is strictly necessary to unlock that write. "
            "Do not end with summary text only."
        )
    if enforce_target_tokens:
        return (
            "Do not end yet. If evidence is still thin, query more history first; otherwise add another "
            "concrete improvement proposal or write action. "
            f"About {remaining} input tokens remain before the target is reached."
        )
    return (
        "Do not end yet. If evidence is still thin, query more history first; otherwise add another "
        "concrete improvement proposal or write action."
    )


# ── Performance stats ────────────────────────────────────────────


def compute_performance_stats(engine: Any, metric: str, character: str) -> str:
    """(Extracted from EvolutionEngine._compute_performance_stats.)

    Compute a performance stat (uncached). Called by handle_performance_stats.
    """
    if not metric:
        return "No metric specified."

    # Tool preprocessing telemetry (gameplay consumption of dynamic tools)
    if metric == "tool_preprocessing" and engine._tool_preprocessor is not None:
        summary = engine._tool_preprocessor.get_telemetry_summary()
        if not summary:
            return "No tool preprocessing data yet."
        lines = ["Tool preprocessing telemetry (gameplay hints):"]
        for name, data in summary.items():
            lines.append(
                f"  {name}: {data['runs']} runs, "
                f"{data['successes']} ok, "
                f"avg {data['avg_latency_ms']:.0f}ms, "
                f"states: {', '.join(data['state_types'])}"
            )
        return "\n".join(lines)

    # Plan verifier telemetry (post-plan verification of combat plans)
    if metric == "plan_verification" and engine._plan_verifier is not None:
        summary = engine._plan_verifier.get_telemetry_summary()
        if not summary:
            return "No plan verification data yet."
        lines = ["Plan verifier telemetry (combat plan checks):"]
        for name, data in summary.items():
            lines.append(
                f"  {name}: {data['runs']} runs, "
                f"{data['successes']} ok, "
                f"avg {data.get('avg_latency_ms', 0):.0f}ms"
            )
        return "\n".join(lines)

    # Tool usage stats from dynamic registry
    if metric == "tool_usage" and engine._dynamic_registry is not None:
        stats = engine._dynamic_registry.stats()
        if not stats:
            return "No dynamic tools have been created yet."
        lines = ["Dynamic tool usage:"]
        for name, data in stats.items():
            if not isinstance(data, dict):
                continue  # skip non-tool entries (e.g. promote_candidates)
            lines.append(
                f"  {name}: {data.get('usage_count', 0)} calls, "
                f"{data.get('success_count', 0)} successes"
            )
        return "\n".join(lines)

    # Skill usage stats
    if metric == "skill_usage" and engine._skill_library is not None:
        lib_stats = engine._skill_library.stats()
        return (
            f"Skills: {lib_stats['active']} active / {lib_stats['total']} total. "
            f"Categories: {lib_stats.get('categories', {})}. "
            f"Sources: {lib_stats.get('sources', {})}."
        )

    # Recent runs from V2 domain stores (CardBuildMemory + CombatEpisode)
    if metric in ("win_rate", "floor_progress", "recent_runs", "death_causes"):
        if engine._memory is None:
            return "Memory not available for performance queries."

        card_build_store = getattr(engine._memory, "card_build_store", None)
        if card_build_store is None:
            return "Card build store not available."

        try:
            all_builds = card_build_store.get_all()
            if not all_builds:
                return "No run data available yet."

            # Filter by character if specified
            if character:
                all_builds = [b for b in all_builds if b.character == character]
                if not all_builds:
                    return f"No run data for character: {character}"

            if metric == "win_rate":
                wins = [b for b in all_builds if b.victory]
                losses = [b for b in all_builds if not b.victory]
                total = len(wins) + len(losses)
                rate = len(wins) / total if total > 0 else 0
                char_note = f" ({character})" if character else ""
                return (
                    f"Win rate: {rate:.0%} "
                    f"({len(wins)}W/{len(losses)}L out of {total} runs)"
                    f"{char_note}"
                )

            if metric == "floor_progress":
                floors = [b.final_floor for b in all_builds]
                if floors:
                    avg_floor = sum(floors) / len(floors)
                    max_floor = max(floors)
                    return (
                        f"Floor progress: avg={avg_floor:.1f}, "
                        f"max={max_floor}, runs={len(floors)}"
                    )
                return "No floor data available."

            if metric == "recent_runs":
                recent = sorted(all_builds, key=lambda b: b.timestamp, reverse=True)[:5]
                lines = ["Recent runs:"]
                for b in recent:
                    outcome = "WIN" if b.victory else "LOSS"
                    top_cards = (
                        ", ".join(n for n, _ in b.card_play_counts[:3])
                        if b.card_play_counts
                        else "N/A"
                    )
                    lines.append(
                        f"  {outcome} floor {b.final_floor} "
                        f"({b.character}/{b.archetype or '?'}): {top_cards}"
                    )
                return "\n".join(lines)

            if metric == "death_causes":
                losses = [b for b in all_builds if not b.victory]
                losses = sorted(losses, key=lambda b: b.timestamp, reverse=True)[:5]
                if not losses:
                    return "No defeats recorded."
                combat_store = getattr(engine._memory, "combat_store", None)
                all_combats = combat_store.get_all() if combat_store else []
                lines = ["Recent defeats:"]
                for b in losses:
                    enemy = "unknown"
                    run_combats = [
                        e for e in all_combats
                        if e.run_id == b.run_id
                        and not e.won
                        and not getattr(e, "is_aborted", False)
                    ]
                    if run_combats:
                        enemy = run_combats[-1].enemy_key
                    lines.append(f"  Floor {b.final_floor} ({b.character}): died to {enemy}")
                return "\n".join(lines)

        except Exception as exc:
            return f"Error querying performance: {exc}"

    return f"Unknown metric: {metric}"


def handle_performance_stats(engine: Any, tool_input: dict) -> str:
    """(Extracted from EvolutionEngine._handle_performance_stats.)

    Handle get_performance_stats: query historical data.

    Results are cached per session — same metric+character returns
    the cached value to avoid wasting evolution rounds.
    """
    metric = tool_input.get("metric", "")
    character = tool_input.get("character", "")

    # Cache lookup — stats don't change within a single evolution session
    cache_key = f"{metric}:{character}"
    if cache_key in engine._stats_cache:
        return engine._stats_cache[cache_key]

    result = compute_performance_stats(engine, metric, character)
    engine._stats_cache[cache_key] = result
    return result


# ── Write tool handlers ──────────────────────────────────────────


def handle_author_tool(engine: Any, tool_input: dict) -> str:
    """(Extracted from EvolutionEngine._handle_author_tool.)

    Handle author_tool: validate, register, and real-state-test a new Python tool.

    After the registry's 6-stage validation (AST + sandbox + tests + quality),
    runs two additional stages:
      Stage 1 — Binding dry-run against real GameState snapshots (0 API calls)
      Stage 2 — LLM quality judge: does the tool output help decisions? (1 Sonnet call)
    """
    tool_name = tool_input.get("tool_name", "").strip()
    code = tool_input.get("code", "")
    motivation = tool_input.get("motivation", "")

    if not tool_name or not code:
        return "REJECTED: tool_name and code are required."

    if engine._dynamic_registry is None:
        return "REJECTED: Dynamic tool registry not available."

    # Registry validation (AST + sandbox + TEST_CASES + quality gates)
    result = engine._dynamic_registry.register_tool(tool_name, code, motivation)
    if not result.startswith("SUCCESS"):
        return result

    # Retrieve the registered tool's actual name from schema
    tool = None
    for t in engine._dynamic_registry._tools.values():
        if t.source_path and t.source_path.stem == tool_name.replace(" ", "_"):
            tool = t
            break
    if tool is None:
        # Fallback: search by input name
        tool = engine._dynamic_registry.get(tool_name)
    if tool is None:
        return result  # Registration succeeded but can't find tool — accept

    # ── Stage 1: Binding Dry-Run ──
    stage1_result = engine._validate_tool_binding(tool)
    if stage1_result is not None:
        engine._dynamic_registry.unregister(tool.name)
        return stage1_result

    # ── Stage 2: LLM Quality Judge ──
    stage2_result = engine._validate_tool_quality(tool)
    if stage2_result is not None:
        engine._dynamic_registry.unregister(tool.name)
        return stage2_result

    engine._emit_artifact(
        kind="dynamic_tool",
        action="create",
        target=tool.name,
        summary=f"motivation: {motivation[:100]}" if motivation else "",
        after={"name": tool.name, "code": code, "motivation": motivation},
        source="evolution",
    )
    return f"SUCCESS: Tool '{tool.name}' registered and validated against real game states."


def handle_write_skill(engine: Any, tool_input: dict) -> str:
    """(Extracted from EvolutionEngine._handle_write_skill.)

    Handle write_skill: create or update a strategy skill.
    """
    from src.brain.write_tools import validate_skill_trigger
    from src.skills.models import Skill, SkillTrigger, normalize_state_types
    from src.storage import paths

    # ── Spec #3 §3.2: cross-run grounding gates ─────────────
    rationale = (tool_input.get("rationale") or "").strip()
    if not rationale:
        return (
            "REJECTED: missing `rationale`. Per Spec #3, every "
            "proposal must explain why mistake_discovery cannot catch "
            "this from a single run's trace."
        )
    if len(rationale) < 30:
        return (
            "REJECTED: `rationale` too thin "
            f"({len(rationale)} chars; minimum 30). Articulate the "
            "cross-run angle concretely."
        )
    if len(rationale) > 300:
        return (
            "REJECTED: `rationale` too long "
            f"({len(rationale)} chars; maximum 300). Be terse."
        )

    evidence = tool_input.get("evidence") or {}
    if not isinstance(evidence, dict):
        return "REJECTED: `evidence` must be an object."
    run_ids = evidence.get("run_ids") or []
    if not isinstance(run_ids, list) or len({str(r) for r in run_ids if r}) < 2:
        return (
            "REJECTED: `evidence.run_ids` must contain ≥2 distinct "
            "run ids. Cross-run signal is by-construction; single-run "
            "patterns belong to mistake_discovery."
        )
    stat_basis = (evidence.get("stat_basis") or "").strip()
    if not stat_basis:
        return "REJECTED: `evidence.stat_basis` is required."

    # Heuristic: stat_basis must contain a digit AND at least one
    # comparator phrase. Cross-run patterns have measured baselines.
    _has_digit = any(ch.isdigit() for ch in stat_basis)
    _comparator_words = ("rate", "%", "vs", "baseline", "average", "median")
    _has_comparator = any(w in stat_basis.lower() for w in _comparator_words)
    if not (_has_digit and _has_comparator):
        return (
            "REJECTED: `evidence.stat_basis` must reference numeric "
            "cross-run data (digits + a comparator like 'rate', '%', "
            "'vs', 'baseline'). Use get_performance_stats first."
        )

    anchor_episode = (evidence.get("anchor_episode") or "").strip()
    if not anchor_episode:
        return "REJECTED: `evidence.anchor_episode` is required."

    # Spec #3 §3.2: anchor_episode format <run_id>:<combat_id>.
    import re as _re
    if not _re.match(r"^\S+:\S+$", anchor_episode):
        return (
            "REJECTED: `evidence.anchor_episode` must use the format "
            "`<run_id>:<combat_id>` (single colon, both parts non-empty, "
            "no whitespace). Got: %r" % anchor_episode
        )

    # Surviving the gates → continue to existing validation chain.

    skill_name = tool_input.get("skill_name", "").strip()
    category = tool_input.get("category", "general")
    content = tool_input.get("content", "").strip()
    motivation = tool_input.get("motivation", "")

    if not skill_name or not content:
        return "REJECTED: skill_name and content are required."

    # Content length validation:
    #   1. LLM auto-compress (preserves meaning, preferred)
    #   2. Deterministic truncation at sentence boundary (fallback when LLM unavailable)
    #   3. Hard reject if still too long after both attempts
    if len(content) > 400:
        compressed = engine._compress_skill_content(content, skill_name)
        if compressed:
            content = compressed
        else:
            # Fallback: cut at the last natural boundary within 400 chars
            from src.postrun.context_builder import _truncate_at_boundary
            truncated = _truncate_at_boundary(content, 400)
            if len(truncated) <= 400:
                logger.info(
                    "Skill '%s': deterministic truncation %d→%d chars",
                    skill_name, len(content), len(truncated),
                )
                content = truncated
            else:
                return (
                    f"REJECTED: Content too long ({len(content)} chars). "
                    "Must be ≤400 chars. Compress to concise rules only, "
                    "no examples or negative cases, and retry."
                )

    if engine._skill_library is None:
        return "REJECTED: Skill library not available."

    # Dedup check: exact name match OR 40%+ keyword overlap in same category
    existing = engine._find_similar_skill(content, category, skill_name)
    if existing:
        if existing.source == "seed":
            # Seeds are immutable — create a supplement that references the seed
            logger.info(
                "Creating supplement to seed '%s' (%s)",
                existing.name, existing.skill_id,
            )
            supplements_seed_id = existing.skill_id
        else:
            # Merge into existing non-seed skill (append new content)
            merged = existing.with_update(
                content=f"{existing.content}\n\n[Updated]: {content}",
                version=existing.version + 1,
            )
            engine._skill_library.update(merged)
            skill_path = paths.skills_file()
            engine._skill_library.save(skill_path)
            engine._emit_artifact(
                kind="skill",
                action="merge",
                target=f"{existing.category}/{existing.name}",
                summary=f"v{merged.version}, merged with new content ({len(content)} chars)",
                before=existing.content,
                after=merged.content,
                details={"skill_id": existing.skill_id, "version": merged.version},
                source="evolution",
            )
            return (
                f"MERGED: Into existing skill '{existing.name}' "
                f"(v{merged.version}, id: {existing.skill_id})."
            )
    else:
        supplements_seed_id = ""

    # Build trigger from optional fields (normalize state_types to gameplay values)
    state_types = tool_input.get("trigger_state_types", [])
    enemy_names = tool_input.get("trigger_enemy_names", [])
    requires_cards = tool_input.get("trigger_requires_cards", [])
    character = tool_input.get("trigger_character", [])

    # Auto-classify: scan content for card/enemy mentions and backfill
    auto_cards, auto_enemies = engine._auto_classify_triggers(
        content, motivation, requires_cards, enemy_names,
        skill_name=skill_name,
    )

    # Validate trigger specificity — warn about overly generic triggers
    trigger_data = {
        "state_types": state_types,
        "enemy_names": list(auto_enemies),
        "tags": [],
    }
    warnings = validate_skill_trigger(trigger_data)
    for w in warnings:
        logger.warning("Skill trigger warning: %s", w)

    trigger = SkillTrigger(
        state_types=normalize_state_types(state_types) if state_types else frozenset(),
        enemy_names=frozenset(auto_enemies),
        requires_cards=frozenset(auto_cards),
        character=frozenset(character),
    )

    # ── 4-stage validation pipeline ──
    passed, reject_reason = engine._validate_skill(
        skill_name, content, motivation, trigger, category,
    )
    if not passed:
        return f"REJECTED: {reject_reason}"

    skill = Skill(
        name=skill_name,
        category=category,
        content=content,
        trigger=trigger,
        source="evolved",
        lessons=f"Motivation: {motivation}",
        priority=70,       # Higher than default 50; can outrank seeds after verification
        confidence=0.65,   # Start higher than 0.5 so evolved skills can compete with seeds
        verified=False,    # Must earn verification through positive outcomes
        supplements_seed_id=supplements_seed_id,
    )

    engine._skill_library.add(skill)

    # Persist immediately
    skill_path = paths.skills_file()
    engine._skill_library.save(skill_path)

    supplement_note = (
        f", supplements seed '{existing.name}'"
        if supplements_seed_id else ""
    )
    engine._emit_artifact(
        kind="skill",
        action="create",
        target=f"{category}/{skill_name}",
        summary=f"id={skill.skill_id}, priority={skill.priority}, confidence={skill.confidence:.2f}{supplement_note}",
        after={
            "name": skill_name,
            "category": category,
            "content": content,
            "motivation": motivation,
            "skill_id": skill.skill_id,
            "supplements_seed_id": supplements_seed_id,
        },
        source="evolution",
    )
    return (
        f"SUCCESS: Skill '{skill_name}' created "
        f"(category: {category}, id: {skill.skill_id}{supplement_note})."
    )
