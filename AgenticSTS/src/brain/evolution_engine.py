"""EvolutionEngine: post-run self-evolution via tool-use agent loop.

Separate from V2Engine — different tool set, different flow.
V2Engine assumes one decision tool per state; evolution needs multiple
write tools. Evolution runs synchronously at post-run time.

Flow:
  1. Build evolution context from run replay
  2. Run multi-turn tool-use loop (up to MAX_ROUNDS)
  3. LLM calls read tools (query) + write tools (author_tool, write_skill, etc.)
  4. Write tool results are recorded as EvolutionActions
  5. Return list of actions taken
"""

from __future__ import annotations

import json
import logging
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import config
from src.memory.combat_analytics import format_analytics
from src.postrun.context_builder import (
    DecisionDigest,
    ReplayPackage,
    SectionStat,
    build_card_mechanics_section,
    build_decision_digest,
    build_relic_context,
    build_replay_package,
    estimate_tokens,
)
from src.storage import paths

# ── Re-exports for backwards compatibility ──────────────────────
# Spec #4 module split: the following identifiers used to live here
# but were absorbed into context_builder.py. Callers using
# `from src.brain.evolution_engine import build_evolution_context`
# (and friends) continue to work via this shim. A follow-up cleanup
# PR can migrate direct importers and remove this shim.
from src.postrun.context_builder import (  # noqa: E402
    EvolutionContextBundle,
    _format_delta_line,
    _format_enemy_deltas,
    _render_dynamic_tools,
    _render_replay_package,
    _render_summary,
    _render_triggered_skills,
    _section,
    _select_smart_episodes,
    _truncate_at_boundary,
    build_evolution_context,
    format_combat_replay,
)

logger = logging.getLogger(__name__)


def _can_bind_param(pname: str, gs: Any) -> bool:
    """Quick check whether a parameter name is resolvable from GameState.

    Used to produce informative rejection messages (which params failed).
    """
    from src.brain.dynamic_tools import AUTO_BINDABLE
    return pname in AUTO_BINDABLE


def _build_state_summary(gs: Any) -> str:
    """Build a compact game state summary for the LLM judge (~200 tokens)."""
    lines: list[str] = []
    lines.append(f"Player: HP {gs.player_hp}/{gs.player_max_hp}, "
                 f"Energy {gs.energy}, Block {getattr(gs, 'block', 0)}")

    if gs.hand:
        card_names = [c.name for c in gs.hand[:10]]
        lines.append(f"Hand: {', '.join(card_names)}")

    for i, e in enumerate(gs.enemies):
        parts = [f"{e.name}: HP {e.current_hp}/{e.max_hp}"]
        if e.block:
            parts.append(f"Block {e.block}")
        # Poison
        for p in (e.powers or []):
            if p.name == "Poison" and p.amount:
                parts.append(f"Poison {p.amount}")
        # Intent
        for intent in (e.intents or []):
            if intent.damage is not None:
                hits = intent.hits or 1
                if hits > 1:
                    parts.append(f"Intent: {intent.damage}x{hits}")
                else:
                    parts.append(f"Intent: {intent.damage} dmg")
            elif intent.intent_type:
                parts.append(f"Intent: {intent.intent_type}")
        lines.append(f"Enemy {i}: {', '.join(parts)}")

    return "\n".join(lines)


def _is_transient(exc_str: str) -> bool:
    """Check if an error message indicates a transient/retriable failure."""
    return any(kw in exc_str.lower() for kw in (
        "502",
        "503",
        "504",
        "524",
        "timed out",
        "timeout",
        "gateway timeout",
        "upstream",
        "connection",
        "deadline exceeded",
        "read timeout",
    ))


@dataclass(frozen=True)
class EvolutionAction:
    """Record of a single evolution action taken by the LLM."""

    tool: str
    tool_input: dict
    result: str
    timestamp: float = field(default_factory=time.time)


# ── Evolution System Prompt ─────────────────────────────────────

EVOLUTION_SYSTEM_PROMPT = """\
You are a self-evolving Slay the Spire 2 agent. You just completed a run and \
are now analyzing your performance to improve for future runs.

Your goal: identify your WORST mistakes and create tools or skills that would \
have prevented them. Focus on concrete, actionable improvements.

Guidelines:
- Create a Python tool (author_tool) when you need a CALCULATION (damage math, \
lethal checks, energy optimization, poison stacking, etc.)
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, \
boss patterns, deck building heuristics, etc.). Per Spec #3, every skill MUST \
include `evidence` (run_ids ≥2 distinct, stat_basis with numeric cross-run data, \
anchor_episode in '<run_id>:<combat_id>' format) AND `rationale` (≤300 chars: \
why mistake_discovery couldn't catch this from a single trace). Use \
get_performance_stats BEFORE proposing to ensure the cross-run pattern is \
real and measurable.
- Query performance stats (get_performance_stats) to understand patterns

Max 3 improvements per run. Quality > quantity. Be specific and actionable.
Tools must include TEST_CASES that verify correctness.
Skills must be concrete enough to help in specific situations.

MANDATORY SKILL WORKFLOW:
1. BEFORE writing any skill, call recall_encounter with the relevant enemy_key \
and character to check if similar encounters exist in history.
2. BEFORE writing any skill, call get_performance_stats to understand patterns.
3. Only after reviewing historical data, decide whether a skill is truly needed.
4. When writing a skill about a SPECIFIC CARD, always set trigger_requires_cards \
with that card name. When about a SPECIFIC ENEMY, always set trigger_enemy_names.
5. When about a specific character, set trigger_character.

SKILL CONTENT LIMIT: write_skill content MUST be ≤400 characters. \
Write concise rules only — no examples, no negative cases, no bullet numbering. \
If rejected for length, write a fundamentally shorter version with fewer rules and retry.

TOOL AUTHORING REQUIREMENTS:
- Every tool MUST declare APPLICABLE_STATES = [...] listing which game states it applies to.
  Valid states: monster, elite, boss, map, rest_site, shop, card_reward, card_select, event, hand_select, treasure, relic_select
- Every tool MUST have at least 2 TEST_CASES with at least 1 containing an assertion key.
  Assertion keys: expected (dict), expected_contains (str), expected_keys (list), expected_<field>_contains.
- state_derived tools: ALL parameters must be auto-bindable from game state.
  Available params: current_hp, max_hp, current_block, energy, dexterity, strength, incoming_damage,
  enemies, enemy_hp, enemy_block, num_enemies, enemy_vulnerable, poison_stacks, deck, hand,
  block_cards_in_hand, deck_size, floor, act, gold.
- plan_evaluator tools: Non-state params must be plan-bindable.
  Plan params: play_sequence, num_cards_played, ends_turn, has_potion_use,
  planned_block, planned_damage, total_energy_spent.
- Tools with unbindable parameters will be REJECTED.
- Duplicate tools (similar name or >80% parameter overlap with existing tools) will be REJECTED.
- Do NOT create tools with parameters like num_shivs, target_enemy_index, damage_multiplier — these cannot be auto-bound.

PYTHON LITERAL RULES (strict — tool code is Python, not JSON):
- Use True / False / None (capitalized), never true/false/null.
- Strings use double quotes; inside TEST_CASES dicts the values follow the same rule.
- Only these imports are allowed: math, collections, itertools, functools. Do NOT import typing, copy, re, json, os, sys, or anything else — the sandbox will REJECT the tool.
- No f-strings are required but they are allowed. No I/O, no print(), no network.

MANDATORY TOOL FILE SKELETON (copy this structure verbatim, then fill in):

    SCHEMA = {
        "name": "<snake_case_tool_name>",
        "description": "<what this tool computes and when it is useful>",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_hp": {"type": "integer"},
                "incoming_damage": {"type": "integer"},
            },
            "required": ["current_hp", "incoming_damage"],
        },
    }

    APPLICABLE_STATES = ["monster", "elite", "boss"]

    def execute(current_hp, incoming_damage):
        net = max(0, incoming_damage)
        return {"net_damage": net, "survives": current_hp > net}

    TEST_CASES = [
        {
            "inputs": {"current_hp": 30, "incoming_damage": 10},
            "expected": {"net_damage": 10, "survives": True},
        },
        {
            "inputs": {"current_hp": 5, "incoming_damage": 12},
            "expected_contains": "survives",
        },
    ]

A tool file MUST export all four names above (SCHEMA, APPLICABLE_STATES, execute, TEST_CASES). Missing SCHEMA is the #1 cause of rejection — start with the SCHEMA dict every time.

HP EFFICIENCY PRINCIPLE:
- A fight won without losing HP is strictly better than one where HP was lost. \
Every tool you create must treat HP as a run-wide resource, not just a survival buffer.
- NEVER create tools that recommend "skip block" when incoming damage > 0. \
The correct output is WHICH block card to play, not WHETHER to block.
- "Free offense turns" ONLY exist when ALL enemies have non-attack intents (Buff/Debuff/Status). \
Any incoming damage — even 3-4 points — should be blocked if energy and cards allow.
- Tools that evaluate block decisions must consider block card VALUES (e.g. Survivor 8 > Defend 5), \
not just "has block card: yes/no"."""



# ── Engine ──────────────────────────────────────────────────────

class EvolutionEngine:
    """Synchronous local tool-use loop for post-run self-evolution.

    Uses V2Backend for LLM calls but operates independently from the
    V2Engine gameplay loop. Has access to both read tools (query) and
    write tools (author_tool, write_skill, etc.).
    """

    def __init__(
        self,
        backend: Any,  # V2Backend
        tool_executor: Any,  # ToolExecutor (for read tools)
        dynamic_registry: Any,  # DynamicToolRegistry
        skill_library: Any,  # SkillLibrary
        memory_manager: Any | None = None,  # MemoryManager
        tool_preprocessor: Any | None = None,  # ToolPreprocessor
        plan_verifier: Any | None = None,  # PlanVerifier
        snapshot_store: Any | None = None,  # StateSnapshotStore
        session_logger: Any | None = None,  # SessionLogger
    ) -> None:
        self._backend = backend
        self._tool_executor = tool_executor
        self._dynamic_registry = dynamic_registry
        self._skill_library = skill_library
        self._memory = memory_manager
        self._tool_preprocessor = tool_preprocessor
        self._plan_verifier = plan_verifier
        self._snapshot_store = snapshot_store
        self._session_logger = session_logger
        self._stats_cache: dict[str, str] = {}  # Per-session cache for get_performance_stats
        self._last_session_summary: dict[str, Any] | None = None
        self._artifact_dir: Path | None = None

    def run_evolution(
        self,
        run_context: str,
        *,
        character: str = "",
        artifact_dir: Path | None = None,
        target_input_tokens: int | None = None,
        min_rounds: int | None = None,
        max_rounds: int | None = None,
        read_only_rounds: int | None = None,
        seen_card_names: tuple[str, ...] = (),
        combat_trace_text: str | None = None,
    ) -> list[EvolutionAction]:
        """Run evolution agent loop. Returns list of actions taken.

        This is a synchronous multi-turn tool-use loop. The LLM can call
        read tools (search_strategy, recall_encounter, etc.) and write tools
        (author_tool, write_skill, etc.) in any order.

        When ``combat_trace_text`` is provided (non-empty), the first user message
        becomes a multi-block list with the trace as a cache_control: ephemeral
        prefix. Empty string / None falls back to plain string content.
        """
        self._run_character = character
        self._seen_card_names = frozenset(n.lower() for n in seen_card_names)
        self._last_session_summary = None
        self._artifact_dir = artifact_dir
        # Build staged tool lists: read-only first, full write phase afterwards
        from src.brain.tool_executor import QUERY_TOOL_SCHEMAS
        from src.brain.write_tools import (
            MUTATING_WRITE_TOOL_NAMES,
            MUTATING_WRITE_TOOLS,
            READ_PHASE_TOOLS,
        )

        read_phase_tools = list(QUERY_TOOL_SCHEMAS) + list(READ_PHASE_TOOLS)
        full_tools = list(QUERY_TOOL_SCHEMAS) + list(READ_PHASE_TOOLS) + list(MUTATING_WRITE_TOOLS)
        if self._dynamic_registry:
            full_tools.extend(self._dynamic_registry.get_normalized_schemas())

        from src.brain.llm_router import (
            FailureType,
            classify_failure,
            get_router,
        )
        router = get_router()
        router.set_session_logger(self._session_logger)
        evo_call_class = "evolution"

        # Let router pick initial model (respects circuit breaker)
        evo_selection = router.select_model(evo_call_class)
        primary_model = evo_selection.model
        model = primary_model
        if target_input_tokens is None:
            target_input_tokens = config.EVOLUTION_TARGET_INPUT_TOKENS
        if min_rounds is None:
            min_rounds = config.EVOLUTION_MIN_ROUNDS
        if max_rounds is None:
            max_rounds = config.EVOLUTION_MAX_ROUNDS
        if read_only_rounds is None:
            read_only_rounds = config.EVOLUTION_READ_ONLY_ROUNDS
        enforce_target_tokens = target_input_tokens > 0

        # Store run_context for skill validation (Stage 1 needs combat replays)
        self._run_context = run_context

        # Spec #3 §3.4: when a trace is provided, render the user
        # message as a multi-block list with the trace as a
        # cache_control: ephemeral prefix, sharing Turn 1/2's
        # 5-minute TTL. Without trace, fall back to plain string for
        # backwards compatibility.
        if combat_trace_text:
            first_user_content: str | list[dict] = [
                {
                    "type": "text",
                    "text": combat_trace_text,
                    "cache_control": {"type": "ephemeral"},
                },
                {"type": "text", "text": run_context},
            ]
        else:
            first_user_content = run_context
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": first_user_content},
        ]
        initial_is_read_phase = read_only_rounds > 0
        self._write_round_artifact(
            round_number=1,
            phase="context",
            messages=messages,
            model=model,
            tool_names=[],
            tool_choice={"type": "any"} if initial_is_read_phase else None,
        )
        self._write_round_1_prompt_artifact(
            system_prompt=self._phase_system_prompt(initial_is_read_phase),
            run_context=run_context,
        )

        actions_taken: list[EvolutionAction] = []
        round_input_tokens: list[int] = []
        round_output_tokens: list[int] = []
        total_input_tokens = 0
        total_output_tokens = 0
        fallbacks_used = 0
        session_start = time.monotonic()
        total_rounds = 0
        force_tool_choice_next_round = False

        for round_idx in range(max_rounds):
            total_rounds = round_idx + 1
            is_read_phase = round_idx < read_only_rounds
            must_force_write = self._is_final_force_write_round(
                round_idx=round_idx,
                max_rounds=max_rounds,
                read_only_rounds=read_only_rounds,
                actions_taken_count=len(actions_taken),
            )
            if must_force_write:
                tools = list(MUTATING_WRITE_TOOLS)
                tool_choice = {"type": "any"}
                phase_name = "force_write"
            else:
                tools = read_phase_tools if is_read_phase else full_tools
                tool_choice = (
                    {"type": "any"}
                    if (is_read_phase or force_tool_choice_next_round)
                    else None
                )
                phase_name = "read_only" if is_read_phase else "write"
            force_tool_choice_next_round = False
            # Router-guided retry with model fallback
            response = None
            current_model = model
            current_provider = config.get_tier_provider("evolution")
            retry_count = 0
            max_hard_retries = config.ROUTER_MAX_HARD_RETRIES
            round_start = time.monotonic()
            while response is None:
                try:
                    response = self._backend.call(
                        system=self._phase_system_prompt(is_read_phase),
                        messages=messages,
                        provider=current_provider,
                        model=current_model,
                        tools=tools,
                        tool_choice=tool_choice,
                        think=True,
                        effort="high",
                        max_tokens=4096,
                        openai_relay_profile="postrun",
                    )
                    router.report_success(evo_call_class, current_provider, current_model)
                except Exception as exc:
                    exc_str = str(exc)
                    status_code = getattr(exc, "status_code", None)
                    # 400 = schema/validation error — won't self-heal
                    if status_code == 400 or "ValidationException" in exc_str:
                        logger.warning(
                            "Evolution schema rejected at round %d: %s",
                            round_idx, exc,
                        )
                        break  # inner while — will exit outer for via response=None check

                    ft = classify_failure(exc)
                    opened = router.report_failure(
                        evo_call_class, current_provider, current_model,
                        ft, error=exc_str[:200],
                    )

                    if ft == FailureType.HARD:
                        if retry_count < max_hard_retries and not opened:
                            retry_count += 1
                            delay = min(30, 3 * (2 ** min(retry_count - 1, 3)))
                            logger.warning(
                                "Evolution hard fail on %s (retry #%d), "
                                "retrying in %ds: %s",
                                current_model, retry_count, delay, exc,
                            )
                            time.sleep(delay)
                            continue
                    else:
                        if retry_count < config.ROUTER_MAX_SOFT_RETRIES:
                            retry_count += 1
                            delay = min(30, 3 * (2 ** min(retry_count - 1, 3)))
                            logger.warning(
                                "Evolution soft fail on %s (retry #%d), "
                                "retrying in %ds: %s",
                                current_model, retry_count, delay, exc,
                            )
                            time.sleep(delay)
                            continue

                    # Switch model via router
                    fb = router.get_fallback(evo_call_class, current_model)
                    if fb is not None:
                        fallbacks_used += 1
                        logger.warning(
                            "Evolution switching %s -> %s after failure: %s",
                            current_model, fb.model, exc,
                        )
                        current_model = fb.model
                        current_provider = fb.provider
                        retry_count = 0
                        time.sleep(2)
                        continue

                    # No fallback available — abort round
                    logger.error(
                        "Evolution: no fallback at round %d: %s", round_idx, exc,
                    )
                    break

            if response is None:
                # Schema/validation break — abort this round
                break

            # Extract tool uses
            tool_uses = self._backend.extract_tool_uses(response)
            usage = getattr(response, "usage", None)
            stop = getattr(response, "stop_reason", "") or ""
            if not stop and hasattr(response, "choices"):
                try:
                    stop = response.choices[0].finish_reason or ""
                except (IndexError, AttributeError):
                    pass
            input_tok = getattr(usage, "input_tokens", 0) or 0
            output_tok = getattr(usage, "output_tokens", 0) or 0
            if not input_tok and usage:
                input_tok = getattr(usage, "prompt_tokens", 0) or 0
                output_tok = getattr(usage, "completion_tokens", 0) or 0
            total_input_tokens += int(input_tok)
            total_output_tokens += int(output_tok)
            round_input_tokens.append(int(input_tok))
            round_output_tokens.append(int(output_tok))
            latency_ms = round((time.monotonic() - round_start) * 1000)

            # ── Telemetry: log this round ──
            if self._session_logger is not None:
                _thinking_tok = 0
                if usage and hasattr(usage, "cache_read_input_tokens"):
                    _thinking_tok = getattr(usage, "cache_read_input_tokens", 0) or 0
                # Serialize messages + response text for the monitor stream.
                try:
                    serialized_messages = [
                        self._serialize_message(msg) for msg in messages
                    ]
                except Exception:
                    serialized_messages = None
                response_text_parts: list[str] = []
                thinking_text_parts: list[str] = []
                try:
                    for block in getattr(response, "content", []) or []:
                        btype = getattr(block, "type", "") or (
                            block.get("type", "") if isinstance(block, dict) else ""
                        )
                        if btype == "text":
                            t = getattr(block, "text", None)
                            if t is None and isinstance(block, dict):
                                t = block.get("text", "")
                            response_text_parts.append(t or "")
                        elif btype == "thinking":
                            t = getattr(block, "thinking", None) or getattr(
                                block, "text", None,
                            )
                            if t is None and isinstance(block, dict):
                                t = block.get("thinking", "") or block.get("text", "")
                            thinking_text_parts.append(t or "")
                    extra_reasoning = getattr(response, "_reasoning_content", "") or ""
                    if extra_reasoning:
                        thinking_text_parts.append(extra_reasoning)
                except Exception:
                    pass
                self._session_logger.log_evolution_round(
                    round_idx=round_idx,
                    model=current_model,
                    provider=config.EVOLUTION_PROVIDER or "openai_compatible",
                    input_tokens=int(input_tok),
                    output_tokens=int(output_tok),
                    thinking_tokens=_thinking_tok,
                    tool_calls=len(tool_uses),
                    tool_names=[tu["name"] for tu in tool_uses],
                    stop_reason=stop,
                    latency_ms=int(latency_ms),
                    phase=phase_name,
                    system_prompt=self._phase_system_prompt(is_read_phase),
                    messages=serialized_messages,
                    response_text="\n".join(response_text_parts),
                    thinking_text="\n".join(thinking_text_parts),
                    tool_uses=list(tool_uses) if tool_uses else None,
                )
            self._write_round_artifact(
                round_number=round_idx + 1,
                phase=phase_name,
                messages=messages,
                model=current_model,
                tool_names=[tu["name"] for tu in tool_uses],
                tool_choice=tool_choice,
                response=response,
                input_tokens=int(input_tok),
                output_tokens=int(output_tok),
                latency_ms=int(latency_ms),
            )

            if not tool_uses:
                base_can_finish = (
                    (round_idx + 1) >= min_rounds
                    and (
                        not enforce_target_tokens
                        or total_input_tokens >= target_input_tokens
                    )
                )
                can_finish = (
                    base_can_finish
                    and (
                        is_read_phase
                        or bool(actions_taken)
                        or (round_idx + 1) >= max_rounds
                    )
                )
                filtered_content = self._filter_response_content(response)
                assistant_msg: dict[str, Any] = {"role": "assistant", "content": filtered_content}
                reasoning = getattr(response, "_reasoning_content", "")
                if reasoning:
                    assistant_msg["_reasoning_content"] = reasoning
                messages.append(assistant_msg)
                if can_finish:
                    logger.info(
                        "Evolution complete after %d rounds (%d actions, %d input tokens)",
                        round_idx + 1,
                        len(actions_taken),
                        total_input_tokens,
                    )
                    break
                next_round_idx = round_idx + 1
                next_is_read_phase = next_round_idx < read_only_rounds
                force_tool_choice_next_round = not next_is_read_phase and not actions_taken
                messages.append({
                    "role": "user",
                    "content": self._continuation_prompt(
                        next_is_read_phase=next_is_read_phase,
                        has_mutating_actions=bool(actions_taken),
                        enforce_target_tokens=enforce_target_tokens,
                        target_input_tokens=target_input_tokens,
                        total_input_tokens=total_input_tokens,
                        min_rounds=min_rounds,
                        round_number=round_idx + 1,
                    ),
                })
                continue

            # Execute all tools, collect results
            tool_results: list[dict[str, Any]] = []
            for tu in tool_uses:
                name = tu["name"]
                tool_input = tu["input"]
                result = self._execute_tool(name, tool_input)

                # Mark rejections as errors so LLM is more likely to retry
                is_err = result.startswith("REJECTED:")
                tool_results.append(
                    self._backend.build_tool_result(
                        tu["id"], result, is_error=is_err,
                    )
                )

                # Record write tool actions
                if name in MUTATING_WRITE_TOOL_NAMES:
                    actions_taken.append(EvolutionAction(
                        tool=name,
                        tool_input=tool_input,
                        result=result,
                    ))

            # Append assistant + tool results for multi-turn
            # Strip thinking blocks — Anthropic requires prior-turn thinking
            # to be removed/redacted in multi-turn conversations.
            # Dual-check pattern matches conversation.py and v2_engine.py filters.
            filtered_content = self._filter_response_content(response)
            assistant_msg: dict[str, Any] = {"role": "assistant", "content": filtered_content}
            reasoning = getattr(response, "_reasoning_content", "")
            if reasoning:
                assistant_msg["_reasoning_content"] = reasoning
            messages.append(assistant_msg)
            messages.append({"role": "user", "content": tool_results})

        else:
            logger.info(
                "Evolution hit max rounds (%d), %d actions taken",
                max_rounds,
                len(actions_taken),
            )

        summary = {
            "total_rounds": total_rounds,
            "total_input_tokens": total_input_tokens,
            "total_output_tokens": total_output_tokens,
            "round_input_tokens": list(round_input_tokens),
            "round_output_tokens": list(round_output_tokens),
            "actions_taken": len(actions_taken),
            "action_types": sorted({action.tool for action in actions_taken}),
            "model": primary_model,
            "fallbacks_used": fallbacks_used,
            "duration_ms": round((time.monotonic() - session_start) * 1000),
            "target_input_tokens": target_input_tokens,
            "target_enforced": enforce_target_tokens,
            "target_reached": (
                total_input_tokens >= target_input_tokens
                if enforce_target_tokens
                else True
            ),
            "min_rounds": min_rounds,
            "max_rounds": max_rounds,
            "read_only_rounds": read_only_rounds,
        }
        self._last_session_summary = summary
        if self._session_logger is not None:
            self._session_logger.log_evolution_summary(**summary)
        return actions_taken

    @staticmethod
    def _is_final_force_write_round(
        *,
        round_idx: int,
        max_rounds: int,
        read_only_rounds: int,
        actions_taken_count: int,
    ) -> bool:
        """Identify the final write-phase round that must restrict tools to writes.

        Bug A1 (2026-04-30): when MAX_ROUNDS is tight, a diagnostic-biased LLM
        can spend every available round on query tools and produce
        actions_taken=0. Returns True when the caller should narrow the tool
        list to MUTATING_WRITE_TOOLS and force tool_choice=any so the session
        ends with at least one write attempt.
        """
        is_read_phase = round_idx < read_only_rounds
        is_final_round = round_idx == max_rounds - 1
        return is_final_round and not is_read_phase and actions_taken_count == 0

    @staticmethod
    def _phase_system_prompt(is_read_phase: bool) -> str:
        from src.brain.evolution_handlers import phase_system_prompt
        return phase_system_prompt(is_read_phase)

    @staticmethod
    def _filter_response_content(response: Any) -> list[Any]:
        from src.brain.evolution_artifacts import filter_response_content
        return filter_response_content(response)

    @staticmethod
    def _continuation_prompt(
        *,
        next_is_read_phase: bool,
        has_mutating_actions: bool,
        enforce_target_tokens: bool,
        target_input_tokens: int,
        total_input_tokens: int,
        min_rounds: int,
        round_number: int,
    ) -> str:
        from src.brain.evolution_handlers import continuation_prompt
        return continuation_prompt(
            next_is_read_phase=next_is_read_phase,
            has_mutating_actions=has_mutating_actions,
            enforce_target_tokens=enforce_target_tokens,
            target_input_tokens=target_input_tokens,
            total_input_tokens=total_input_tokens,
            min_rounds=min_rounds,
            round_number=round_number,
        )

    def _write_round_1_prompt_artifact(self, *, system_prompt: str, run_context: str) -> None:
        from src.brain.evolution_artifacts import write_round_1_prompt_artifact
        return write_round_1_prompt_artifact(self, system_prompt=system_prompt, run_context=run_context)

    def _write_round_artifact(
        self,
        *,
        round_number: int,
        phase: str,
        messages: list[dict[str, Any]],
        model: str,
        tool_names: list[str],
        tool_choice: dict[str, Any] | None,
        response: Any | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        latency_ms: int = 0,
    ) -> None:
        from src.brain.evolution_artifacts import write_round_artifact
        return write_round_artifact(
            self,
            round_number=round_number,
            phase=phase,
            messages=messages,
            model=model,
            tool_names=tool_names,
            tool_choice=tool_choice,
            response=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            latency_ms=latency_ms,
        )

    @classmethod
    def _serialize_message(cls, message: dict[str, Any]) -> dict[str, Any]:
        from src.brain.evolution_artifacts import serialize_message
        return serialize_message(message)

    @classmethod
    def _serialize_response(cls, response: Any) -> dict[str, Any]:
        from src.brain.evolution_artifacts import serialize_response
        return serialize_response(response)

    @classmethod
    def _serialize_content(cls, content: Any) -> Any:
        from src.brain.evolution_artifacts import serialize_content
        return serialize_content(content)

    def _execute_tool(self, name: str, tool_input: dict) -> str:
        """Execute a tool by name via four-stage dispatch.

        1. Write tools (author_tool, write_skill, etc.) → local handlers
        2. Static query tools (recall_encounter, etc.) → ToolExecutor
        3. Dynamic tools (agent-authored .py) → DynamicToolRegistry
        4. Fallback → "Unknown tool"
        """
        from src.brain.write_tools import WRITE_TOOL_NAMES

        # Stage 1: Write tools
        if name in WRITE_TOOL_NAMES:
            return self._execute_write_tool(name, tool_input)

        # Stage 2: Static query tools (recall_encounter, etc.)
        if self._tool_executor is not None and name in getattr(
            self._tool_executor, "_handlers", {},
        ):
            return self._tool_executor.execute(name, tool_input)

        # Stage 3: Dynamic tools (agent-authored)
        if self._dynamic_registry is not None and self._dynamic_registry.has(name):
            return self._dynamic_registry.execute(name, tool_input)

        return f"Unknown tool: {name}"

    def _execute_write_tool(self, name: str, tool_input: dict) -> str:
        """Execute a write-side tool."""
        handlers = {
            "author_tool": self._handle_author_tool,
            "write_skill": self._handle_write_skill,
            "get_performance_stats": self._handle_performance_stats,
        }
        handler = handlers.get(name)
        if handler is None:
            return f"Unknown write tool: {name}"
        try:
            return handler(tool_input)
        except Exception as exc:
            logger.warning("Write tool %s failed: %s", name, exc, exc_info=True)
            return f"Write tool {name} error: {exc}"

    # ── Write tool handlers ─────────────────────────────────────

    def _handle_author_tool(self, tool_input: dict) -> str:
        from src.brain.evolution_handlers import handle_author_tool
        return handle_author_tool(self, tool_input)

    def _validate_tool_binding(self, tool: Any) -> str | None:
        from src.brain.evolution_validators import validate_tool_binding
        return validate_tool_binding(self, tool)

    def _validate_tool_quality(self, tool: Any) -> str | None:
        from src.brain.evolution_validators import validate_tool_quality
        return validate_tool_quality(self, tool)

    def _find_similar_skill(
        self, content: str, category: str, skill_name: str = ""
    ) -> Any | None:
        from src.brain.evolution_validators import find_similar_skill
        return find_similar_skill(self, content, category, skill_name)

    def _compress_skill_content(self, content: str, skill_name: str) -> str | None:
        from src.brain.evolution_validators import compress_skill_content
        return compress_skill_content(self, content, skill_name)

    def _handle_write_skill(self, tool_input: dict) -> str:
        from src.brain.evolution_handlers import handle_write_skill
        return handle_write_skill(self, tool_input)

    # ── Trigger auto-classification ──────────────────────────────

    def _auto_classify_triggers(
        self,
        content: str,
        motivation: str,
        explicit_cards: list[str],
        explicit_enemies: list[str],
        skill_name: str = "",
    ) -> tuple[list[str], list[str]]:
        from src.brain.evolution_validators import auto_classify_triggers
        return auto_classify_triggers(
            self, content, motivation, explicit_cards, explicit_enemies,
            skill_name=skill_name,
        )

    # ── Skill validation pipeline (4 stages) ───────────────────

    def _validate_skill(
        self,
        skill_name: str,
        content: str,
        motivation: str,
        trigger: object,  # SkillTrigger
        category: str,
    ) -> tuple[bool, str]:
        from src.brain.evolution_validators import validate_skill
        return validate_skill(self, skill_name, content, motivation, trigger, category)

    def _extract_relevant_replay(self, trigger: object) -> str:
        from src.brain.evolution_validators import extract_relevant_replay
        return extract_relevant_replay(self, trigger)

    def _validate_skill_facts(
        self,
        skill_name: str,
        content: str,
        motivation: str,
        trigger: object,
        category: str,
    ) -> str | None:
        from src.brain.evolution_validators import validate_skill_facts
        return validate_skill_facts(self, skill_name, content, motivation, trigger, category)

    def _validate_skill_injection(
        self,
        skill_name: str,
        content: str,
        trigger: object,
    ) -> str | None:
        from src.brain.evolution_validators import validate_skill_injection
        return validate_skill_injection(self, skill_name, content, trigger)

    def _check_skill_overmatch(self, trigger: object) -> None:
        from src.brain.evolution_validators import check_skill_overmatch
        return check_skill_overmatch(self, trigger)

    def _validate_skill_quality(
        self,
        skill_name: str,
        content: str,
        category: str,
        trigger: object,
    ) -> str | None:
        from src.brain.evolution_validators import validate_skill_quality
        return validate_skill_quality(self, skill_name, content, category, trigger)

    def _handle_performance_stats(self, tool_input: dict) -> str:
        from src.brain.evolution_handlers import handle_performance_stats
        return handle_performance_stats(self, tool_input)

    def _compute_performance_stats(self, metric: str, character: str) -> str:
        from src.brain.evolution_handlers import compute_performance_stats
        return compute_performance_stats(self, metric, character)

    # ── Utilities ───────────────────────────────────────────────

    def _emit_artifact(
        self,
        *,
        kind: str,
        action: str = "write",
        target: str = "",
        summary: str = "",
        before: object = None,
        after: object = None,
        details: dict | None = None,
        source: str = "",
        stage: str = "evolution",
    ) -> None:
        from src.brain.evolution_artifacts import emit_artifact
        return emit_artifact(
            self,
            kind=kind,
            action=action,
            target=target,
            summary=summary,
            before=before,
            after=after,
            details=details,
            source=source,
            stage=stage,
        )

    def _save_proposal(self, proposal_type: str, data: dict) -> str:
        from src.brain.evolution_artifacts import save_proposal
        return save_proposal(self, proposal_type, data)

