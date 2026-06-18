"""V2 decision engine: single-call <decision> protocol for the STS2 agent.

An independent dispatcher — the agent loop delegates all LLM
decisions to this engine.

Two modes:
  1. **Non-combat**: single LLM call with assembled state context, decision
     extracted via <decision> tag.
  2. **Combat**: single LLM call within a multi-turn conversation, decision
     extracted via <decision> tag.

Both modes use ``_single_call`` which:
  - Makes one LLM call (no tools= parameter)
  - Extracts a ``<decision>{JSON}</decision>`` block from the response
  - Validates the decision fields
  - Runs one repair turn if extraction or validation fails
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any

import httpx

import config
from src.brain.decision_parser import (
    extract_decision,
    format_decision_schema_hint,
    format_repair_message,
    normalize_decision_payload,
    validate_decision,
)
from src.brain.llm_router import (
    FailureType,
    classify_failure,
    get_router,
)
from src.brain.planner import CombatPlan, parse_combat_plan
from src.brain.prompts.system import get_system_prompt
from src.brain.tool_schemas import get_tool_for_state

if TYPE_CHECKING:
    from src.brain.conversation import CombatConversation
    from src.brain.models import LLMDecision
    from src.brain.tool_executor import ToolExecutor
    from src.brain.v2_backend import V2Backend
    from src.log.session_logger import SessionLogger
    from src.memory.short_term import CombatTracker
    from src.state.game_state import GameState

logger = logging.getLogger(__name__)


# ── Round-context capture (Task B5: mistake-driven skill discovery) ─────
# After the strategic-tier combat plan LLM returns, we snapshot the
# pre-plan round context onto the active CombatTracker so postrun
# analysis can reconstruct exactly what the agent was looking at when
# it made each decision. See:
# docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §2.2
#
# This helper is defensive: missing fields default to 0/[]/-1 and any
# internal error is swallowed. Combat MUST NOT crash on capture failure.


def capture_round_context(
    *,
    tracker: "CombatTracker | None",
    block_before: int,
    draw_pile_size: int,
    discard_pile_size: int,
    exhaust_pile_size: int,
    usable_potions: list[str],
    incoming_damage: int,
    agent_plan: list[str],
    llm_call_seq: int,
) -> None:
    """Attach pre-plan round context to ``tracker``'s current round.

    Safe no-op when ``tracker`` is ``None`` or has no active round.
    Any internal exception is logged and swallowed — combat MUST continue
    working if capture fails (a missing snapshot just means that round
    cannot be re-tested in prewrite A/B).

    Called from ``_generate_combat_plan`` after the strategic tier's
    ``llm_call`` event has been written, so ``llm_call_seq`` pins the
    round to the exact log entry.
    """
    if tracker is None:
        return
    try:
        tracker.record_round_context(
            block_before=block_before,
            draw_pile_size=draw_pile_size,
            discard_pile_size=discard_pile_size,
            exhaust_pile_size=exhaust_pile_size,
            usable_potions=list(usable_potions),
            incoming_damage=incoming_damage,
            agent_plan=list(agent_plan),
            llm_call_seq=llm_call_seq,
        )
    except Exception:  # noqa: BLE001
        # Defensive: never crash combat on capture failure.
        logger.debug("capture_round_context failed", exc_info=True)


# ── Local reasoning_zh post-processing ──────────────────────
# Done locally after the LLM returns so we don't waste prompt tokens on a
# per-decision glossary. The translator runs translate_summary() which
# substitutes English entity names (cards / relics / potions / monsters /
# powers / enchantments / characters / orbs / events) with Chinese, then
# translates structural labels (HP/E/Hand, F<n>, [monster] etc.). We only
# touch reasoning_zh — the canonical English `reasoning` is untouched.

def _localize_reasoning_zh(text: str) -> str:
    if not text or config.DISPLAY_LANGUAGE != "zh":
        return text
    try:
        from src.knowledge.locale_translator import get_translator
        return get_translator().translate_summary(text)
    except Exception:
        return text


# ── Sentinel cleanup ─────────────────────────────────────────

def _clean_params(params: dict[str, Any]) -> dict[str, Any]:
    """Remove sentinel values (``-1``, ``""``) from tool input params.

    These are artefacts of the LLM filling in optional fields with
    placeholder values. Returns a new dict.
    """
    cleaned: dict[str, Any] = {}
    for key, value in params.items():
        if value == -1 or value == "":
            continue
        cleaned[key] = value
    return cleaned


_TRANSIENT_LLM_ERROR_MARKERS = (
    "401",
    "408",
    "429",
    "500",
    "502",
    "503",
    "504",
    "timeout",
    "timed out",
    "read operation timed out",
    "connection reset",
    "connection aborted",
    "connection refused",
    "temporarily unavailable",
    "upstream",
)


def _is_transient_llm_error(exc: Exception | str) -> bool:
    """Return True when an LLM error is worth retrying."""
    if isinstance(exc, (asyncio.TimeoutError, TimeoutError, httpx.TimeoutException)):
        return True

    if isinstance(exc, httpx.HTTPStatusError):
        response = getattr(exc, "response", None)
        status = response.status_code if response is not None else None
        if status in {401, 408, 429, 500, 502, 503, 504}:
            return True

    exc_text = str(exc).lower()
    return any(marker in exc_text for marker in _TRANSIENT_LLM_ERROR_MARKERS)


def _retry_delay_seconds(retry_count: int) -> float:
    """Return a capped exponential backoff for upstream retries."""
    base_delay = max(config.LLM_RETRY_BASE_DELAY_SEC, 0.5)
    max_delay = max(config.LLM_RETRY_MAX_DELAY_SEC, base_delay)
    exponent = max(retry_count - 1, 0)
    return min(base_delay * (2 ** exponent), max_delay)


def _get_fallback_chain(model: str, tier: str) -> list[str]:
    """Return the ordered fallback model list for the given tier, excluding ``model``.

    Fallbacks are tried in order when the primary model fails.
    """
    if tier == "fast":
        candidates = list(config.LLM_FAST_FALLBACK_MODELS)
    elif tier == "strategic":
        candidates = list(config.LLM_STRATEGIC_FALLBACK_MODELS)
    else:
        candidates = []
    model_lower = (model or "").strip().lower()
    return [m for m in candidates if m.strip().lower() != model_lower]


def _should_retry_llm_error(
    exc: Exception,
    *,
    provider: str | None = None,
    backend: Any | None = None,
) -> bool:
    """Return True when an LLM failure should stay on the retry path."""
    if _is_transient_llm_error(exc):
        return True

    if (
        provider == "openai_compatible"
        and backend is not None
        and hasattr(backend, "_is_openai_failover_error")
    ):
        try:
            return bool(backend._is_openai_failover_error(exc))
        except Exception:
            return False

    return False


# ── V2 Model Routing ────────────────────────────────────────
# Maps state_type → tier name ("fast" or "strategic").
# Unlisted state types default to "strategic".

_V2_TIER_MAP: dict[str, str] = {
    "monster": "strategic",
    "elite": "strategic",
    "boss": "strategic",
    "hand_select": "fast",
    "treasure": "fast",
    "card_reward": "strategic",
    "card_select": "strategic",
    "map": "fast",
    "rest_site": "strategic",
    "shop": "strategic",
    "event": "strategic",
    "crystal_sphere": "strategic",
    "bundle_select": "strategic",
    "combat_plan": "strategic",
    # NOTE: combat re-plans are handled by is_replan guard in _get_v2_tier,
    # not via this map. No "combat_replan" entry needed.
}


class V2Engine:
    """V2 decision engine with single-call <decision> protocol.

    Two modes:
      1. Non-combat: single LLM call with assembled context, decision via <decision> tag.
      2. Combat: single LLM call within multi-turn conversation, decision via <decision> tag.
    """

    def __init__(
        self,
        backend: V2Backend,
        tool_executor: ToolExecutor,
        *,
        session_logger: SessionLogger | None = None,
    ) -> None:
        self._backend = backend
        self._executor = tool_executor
        self._session_logger = session_logger

    def set_session_logger(self, session_logger: SessionLogger | None) -> None:
        """Update session logger (called at run start)."""
        self._session_logger = session_logger

    def _log_llm_request_start(
        self,
        *,
        provider: str,
        model: str,
        tier: str,
        state_type_hint: str,
        round_idx: int,
        think_enabled: bool,
        tools: list[dict[str, Any]],
        messages: list[dict[str, Any]],
    ) -> None:
        if self._session_logger is None:
            return
        try:
            self._session_logger.log_llm_request_start(
                call_type="v2_agent_loop",
                provider=provider,
                model=model,
                tier=tier,
                state_type=state_type_hint or "unknown",
                round_idx=round_idx,
                think_enabled=think_enabled,
                tool_count=len(tools),
                message_count=len(messages),
            )
        except Exception:
            pass

    def _log_llm_first_chunk(
        self,
        *,
        provider: str,
        model: str,
        tier: str,
        state_type_hint: str,
        round_idx: int,
        latency_ms: float,
        chunk_meta: dict[str, Any],
    ) -> None:
        if self._session_logger is None:
            return
        try:
            self._session_logger.log_llm_first_chunk(
                call_type="v2_agent_loop",
                provider=provider,
                model=model,
                tier=tier,
                state_type=state_type_hint or "unknown",
                round_idx=round_idx,
                latency_ms=latency_ms,
                chunk_meta=chunk_meta,
            )
        except Exception:
            pass

    def _make_first_chunk_logger(
        self,
        *,
        provider: str,
        model: str,
        tier: str,
        state_type_hint: str,
        round_idx: int,
        started_at: float,
    ) -> Any | None:
        """Return a callback that logs first-byte timing for the in-flight request."""
        if self._session_logger is None:
            return None

        def _callback(chunk_meta: dict[str, Any]) -> None:
            latency_ms = (time.monotonic() - started_at) * 1000
            self._log_llm_first_chunk(
                provider=provider,
                model=model,
                tier=tier,
                state_type_hint=state_type_hint,
                round_idx=round_idx,
                latency_ms=latency_ms,
                chunk_meta=chunk_meta,
            )

        return _callback

    def _log_llm_request_end(
        self,
        *,
        provider: str,
        model: str,
        tier: str,
        state_type_hint: str,
        round_idx: int,
        latency_ms: float,
        status: str,
        stop_reason: str = "",
        tokens: int = 0,
        error: str = "",
    ) -> None:
        if self._session_logger is None:
            return
        try:
            self._session_logger.log_llm_request_end(
                call_type="v2_agent_loop",
                provider=provider,
                model=model,
                tier=tier,
                state_type=state_type_hint or "unknown",
                round_idx=round_idx,
                latency_ms=latency_ms,
                status=status,
                stop_reason=stop_reason,
                tokens=tokens,
                error=error,
            )
        except Exception:
            pass

    # ── Helpers ────────────────────────────────────────────────

    @staticmethod
    def _filter_thinking_blocks(content: list[Any]) -> list[Any]:
        """Strip thinking blocks from content for message history.

        Anthropic strips thinking blocks from context when a non-tool-result
        user message follows, mutating the cached prefix and causing cache
        misses.  We strip proactively to keep conversation history clean.

        Handles both SDK objects (hasattr) and plain dicts (isinstance).
        """
        filtered = [
            b for b in content
            if not (
                (isinstance(b, dict) and b.get("type") == "thinking")
                or (hasattr(b, "type") and getattr(b, "type", None) == "thinking")
            )
        ]
        return filtered or [{"type": "text", "text": "(thinking only)"}]

    @staticmethod
    def _build_assistant_msg(
        filtered_content: list[Any], response: Any,
    ) -> dict[str, Any]:
        """Build an assistant message dict, preserving reasoning_content if present."""
        msg: dict[str, Any] = {"role": "assistant", "content": filtered_content}
        rc = getattr(response, "_reasoning_content", "")
        if rc:
            msg["_reasoning_content"] = rc
        return msg

    # ── Model Routing ──────────────────────────────────────────

    @staticmethod
    def _get_v2_tier(
        state_type: str,
        *,
        is_replan: bool = False,
        simple: bool = False,
    ) -> tuple[str, str, str]:
        """Select provider, model, and effort level for a V2 decision.

        Args:
            state_type: The game state type (e.g. ``"map"``, ``"shop"``,
                ``"combat_plan"``).
            is_replan: If ``True``, use strategic model with low effort
                (draw-card re-plan, validation retry).
            simple: If ``True``, route to the fast tier regardless of the
                state_type's normal routing. Used for trivial combat plans
                (≤2 playable cards) where strategic-tier reasoning is
                wasted. Takes priority over ``is_replan`` — a draw-card
                re-plan that ends up with a trivial hand should still go
                fast.

        Returns:
            ``(provider, model_name, effort)`` tuple.  ``effort`` is ``""`` for
            fast tier (no thinking) or ``"medium"``/``"low"`` for
            strategic tier.
        """
        if simple:
            return (
                config.get_tier_provider("fast"),
                config.LLM_FAST_MODEL,
                config.LLM_THINK_EFFORT_FAST or "low",
            )

        if is_replan:
            return (
                config.get_tier_provider("strategic"),
                config.LLM_STRATEGIC_MODEL,
                "low",
            )

        tier = _V2_TIER_MAP.get(state_type, "strategic")
        provider = config.get_tier_provider(tier)
        model = getattr(config, f"LLM_{tier.upper()}_MODEL")
        # Both tiers now read effort from config.  Fast tier defaults to
        # "low" instead of "" because Gemini 3.1 flash-lite-preview is
        # *faster* with explicit thinking_level=low than without it (the
        # server runs thinking either way; explicit "low" caps the budget).
        effort = getattr(config, f"LLM_THINK_EFFORT_{tier.upper()}", "low" if tier == "fast" else "medium")
        return (provider, model, effort)

    # ── Public API ─────────────────────────────────────────────

    async def decide_noncombat(
        self,
        gs: GameState,
        state_prompt: str,
        *,
        extra_context: str = "",
        skill_context: str = "",
        memory_context: str = "",
        knowledge_context: str = "",
    ) -> LLMDecision | None:
        """Non-combat tool-use agent loop.

        Args:
            gs: Current game state.
            state_prompt: Pre-formatted state description (from simplified
                prompt templates).
            extra_context: Computed insights from ToolPreprocessor.
            skill_context: Retrieved strategy skills text.
            memory_context: HCM working context (past experience).
            knowledge_context: Game knowledge DB text.

        Returns:
            An ``LLMDecision`` parsed from the decision tool output,
            or ``None`` on failure.
        """
        # 1. Build system prompt: state-type-specific
        system = get_system_prompt(gs.state_type)

        # 2. Get decision tool name for this state type
        decision_tool = get_tool_for_state(gs.state_type, gs=gs)
        if decision_tool is None:
            logger.warning(
                "V2Engine: no decision tool for state_type=%s, falling back",
                gs.state_type,
            )
            return None
        decision_tool_name = decision_tool["name"]

        # 3. Prepare initial messages with all context in stable order
        #    (skills → memory → knowledge → insights → state)
        sections: list[str] = []
        if skill_context:
            sections.append(skill_context)
        if memory_context:
            sections.append(memory_context)
        if knowledge_context:
            sections.append(f"## Game Knowledge\n{knowledge_context}")
        if extra_context:
            sections.append(extra_context)  # Has its own ## header
        sections.append(state_prompt)
        # Inject schema hint so model knows exact valid actions + required fields
        # Extract allowed actions from the (possibly dynamic) tool schema
        tool_action_enum = (
            decision_tool.get("input_schema", {})
            .get("properties", {})
            .get("action", {})
            .get("enum")
        )
        schema_hint = format_decision_schema_hint(
            decision_tool_name, allowed_actions=tool_action_enum,
        )
        if schema_hint:
            sections.append(schema_hint)
        user_content = "\n\n".join(sections)
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": user_content},
        ]

        # 4. Update executor with current game state (kept for evolution ToolExecutor compatibility)
        self._executor.set_game_state(gs)

        # 5. Single call with <decision> extraction
        provider, model, effort = self._get_v2_tier(gs.state_type)

        decision_input, _raw_text, total_latency, total_tokens = await self._single_call(
            system=system,
            messages=messages,
            decision_tool_name=decision_tool_name,
            provider=provider,
            model=model,
            effort=effort,
            state_type_hint=gs.state_type,
        )

        if decision_input is None:
            logger.warning("V2Engine: noncombat agent loop returned no decision")
            return None

        # 6. Parse decision tool output → LLMDecision
        return self._parse_decision(
            decision_input,
            prompt_text=state_prompt,
            latency_ms=total_latency,
            tokens_used=total_tokens,
            tool_name=decision_tool_name,
        )

    async def generate_combat_plan(
        self,
        conversation: CombatConversation,
        *,
        is_replan: bool = False,
        simple: bool = False,
        use_fallback_model: bool = False,
    ) -> CombatPlan | None:
        """Generate a combat plan from a multi-turn conversation.

        Args:
            conversation: ``CombatConversation`` with accumulated messages.
            is_replan: If ``True``, use strategic model with low effort
                (draw-card re-plan, validation retry). Defaults to
                ``False`` (strategic tier with configured effort).
            simple: If ``True``, route to the fast tier — trivial hands
                (≤2 playable cards) where strategic-tier reasoning is
                wasted. Takes priority over ``is_replan``.
            use_fallback_model: If ``True``, use analysis tier as a stronger
                fallback when the default tier fails repeatedly.

        Returns:
            A ``CombatPlan`` parsed from the combat_plan tool output,
            or ``None`` on failure.
        """
        # 1. Run single call with <decision> extraction
        decision_tool_name = "combat_plan"
        if use_fallback_model:
            provider = config.get_tier_provider("analysis")
            model = config.LLM_ANALYSIS_MODEL
            effort = "medium"
            logger.info(
                "Combat plan using fallback model: provider=%s model=%s",
                provider, model,
            )
        else:
            provider, model, effort = self._get_v2_tier(
                "combat_plan", is_replan=is_replan, simple=simple,
            )

        decision_input, raw_text, total_latency, total_tokens = await self._single_call(
            system=conversation.system_prompt,
            messages=conversation.llm_messages,
            decision_tool_name=decision_tool_name,
            provider=provider,
            model=model,
            effort=effort,
            state_type_hint="combat_plan",
        )

        # Record the final assistant response into conversation history
        if raw_text:
            conversation._messages.append({"role": "assistant", "content": raw_text})

        if decision_input is None:
            logger.warning("V2Engine: combat agent loop returned no plan")
            return None

        # 3. Parse combat_plan tool output → CombatPlan
        return self._parse_combat_plan(decision_input, raw_text=raw_text)

    # ── Single-call decision extraction ──────────────────────────

    async def _single_call(
        self,
        system: str,
        messages: list[dict[str, Any]],
        decision_tool_name: str,
        *,
        provider: str | None = None,
        model: str | None = None,
        effort: str = "",
        state_type_hint: str = "",
    ) -> tuple[dict | None, str, float, int]:
        """Single LLM call with <decision> extraction and one repair turn.

        Returns (decision_dict, raw_text, latency_ms, token_count).
        decision_dict is None if extraction + repair both fail.
        """
        use_provider = provider or config.get_tier_provider("strategic")
        use_model = model or config.LLM_STRATEGIC_MODEL
        use_think = bool(effort)
        tier_name = _V2_TIER_MAP.get(state_type_hint, "strategic")

        # When the model has a capturable thinking channel (kimi's
        # reasoning_content), reasoning happens in thinking tokens — visible
        # text should be ONLY the <decision> JSON.  This avoids double
        # reasoning (thinking + visible analysis) that causes 2× token cost.
        #
        # Gemini via proxy: thinking runs server-side but content is NOT
        # returned, so the model must write reasoning visibly — no hint.
        # Anthropic: hidden thinking block, no hint needed.
        _model_lower = (model or use_model).lower()
        _has_capturable_thinking = "kimi" in _model_lower
        if use_think and _has_capturable_thinking:
            _DECISION_ONLY_HINT = (
                "IMPORTANT: Your reasoning goes in the thinking process. "
                "Your visible output must contain ONLY the <decision> tag "
                "with valid JSON inside. Do NOT write any analysis, "
                "explanation, or reasoning text before the tag."
            )
            # Append hint to the last user message
            if messages and messages[-1].get("role") == "user":
                messages = list(messages)  # don't mutate caller's list
                last = messages[-1]
                messages[-1] = {
                    **last,
                    "content": last["content"] + "\n\n" + _DECISION_ONLY_HINT,
                }

        # Display-language hint: when DISPLAY_LANGUAGE=zh, ask the model to
        # additionally emit a `reasoning_zh` field for stream-display only.
        # The canonical `reasoning` field stays English so memory + skills
        # + parsing pipelines remain unchanged.
        #
        # Entity-name translation (Strike -> 打击, Akabeko -> 赤牛, ...) is
        # done LOCALLY post-hoc via LocaleTranslator.translate_summary() in
        # the loop's decision-handling path, NOT via an in-prompt glossary.
        # The model is instructed to leave card / relic / potion / enemy
        # names in English so the local translator can substitute them
        # deterministically — this saves prompt tokens and avoids
        # name-hallucination risk.
        if config.DISPLAY_LANGUAGE == "zh":
            _ZH_DISPLAY_HINT = (
                "Additionally, in your <decision> JSON include an optional "
                "field `reasoning_zh` whose value is the `reasoning` field "
                "translated into 简体中文 (Simplified Chinese). Translate the "
                "narrative prose only — leave card / relic / potion / enemy "
                "names in English exactly as they appear in `reasoning`. Keep "
                "numeric values, status labels (HP, Block, Energy), action "
                "types (e.g. play_card), enum values, JSON keys, and any *N "
                "or +N upgrade suffixes verbatim. Keep `reasoning` itself in "
                "English."
            )
            if messages and messages[-1].get("role") == "user":
                messages = list(messages)
                last = messages[-1]
                messages[-1] = {
                    **last,
                    "content": last["content"] + "\n\n" + _ZH_DISPLAY_HINT,
                }

        total_latency_ms: float = 0.0
        total_tokens: int = 0
        raw_text = ""

        # ── Router-based model selection ──
        # Map state_type_hint → call_class for the router.
        call_class = f"gameplay_{tier_name}" if tier_name in ("fast", "strategic") else "gameplay_strategic"
        router = get_router()
        router.set_session_logger(self._session_logger)

        # The caller's (provider, model) is the authoritative preference.
        # The router respects it if healthy, falls back to chain otherwise.
        selection = router.select_model(
            call_class,
            preferred_provider=use_provider,
            preferred_model=use_model,
        )
        use_model = selection.model
        use_provider = selection.provider

        # Snapshot the initial selection so retry-forever can restart the
        # fallback chain from its head after every model has been exhausted.
        initial_model = use_model
        initial_provider = use_provider

        # ── Main call (with router-guided retry + model switch) ──
        response = None
        retry_count = 0
        max_hard_retries = config.ROUTER_MAX_HARD_RETRIES

        while True:
            self._log_llm_request_start(
                provider=use_provider,
                model=use_model,
                tier=tier_name,
                state_type_hint=state_type_hint,
                round_idx=0,
                think_enabled=use_think,
                tools=[],
                messages=messages,
            )
            t0 = time.monotonic()
            on_first_chunk = self._make_first_chunk_logger(
                provider=use_provider,
                model=use_model,
                tier=tier_name,
                state_type_hint=state_type_hint,
                round_idx=0,
                started_at=t0,
            )
            try:
                # Gate hedging on router health — suppress duplicate traffic
                # on models whose circuit breaker is not CLOSED.
                hedge_ok = router.should_hedge(call_class, use_provider, use_model)
                response = await self._backend.acall(
                    system=system,
                    messages=messages,
                    provider=use_provider,
                    model=use_model,
                    think=use_think,
                    effort=effort,
                    on_first_chunk=on_first_chunk,
                    allow_hedge=hedge_ok,
                    tier=tier_name,
                )
                # Detect relay returning empty response (0tok, stop=None).
                _resp_usage = getattr(response, "usage", None)
                _resp_tokens = (
                    (getattr(_resp_usage, "input_tokens", 0) or 0) +
                    (getattr(_resp_usage, "output_tokens", 0) or 0)
                ) if _resp_usage else 0
                _resp_text = self._backend.extract_text(response)
                if not _resp_text.strip() and _resp_tokens == 0:
                    elapsed = (time.monotonic() - t0) * 1000
                    logger.warning(
                        "V2Engine[%s/%s]: empty response (0tok, %.0fms) on %s",
                        tier_name, state_type_hint, elapsed, use_model,
                    )
                    self._log_llm_request_end(
                        provider=use_provider,
                        model=use_model,
                        tier=tier_name,
                        state_type_hint=state_type_hint,
                        round_idx=0,
                        latency_ms=elapsed,
                        status="empty_retry",
                        stop_reason=getattr(response, "stop_reason", "") or "",
                        tokens=0,
                    )
                    # Empty response is a hard fail
                    opened = router.report_failure(
                        call_class, use_provider, use_model,
                        FailureType.HARD, error="empty response 0tok",
                    )
                    if retry_count < max_hard_retries and not opened:
                        retry_count += 1
                        await asyncio.sleep(2)
                        continue
                    # Switch model via router
                    fb = router.get_fallback(call_class, use_model)
                    if fb is not None:
                        use_model = fb.model
                        use_provider = fb.provider
                        retry_count = 0
                        await asyncio.sleep(1)
                        continue
                    # Fallback chain exhausted on empty responses. Normally break
                    # with whatever empty response we have. With retry-forever,
                    # reset and wait — a persistently-empty relay is indistinguishable
                    # from an outage for our purposes.
                    if config.LLM_RETRY_FOREVER:
                        delay = max(config.LLM_RETRY_MAX_DELAY_SEC, 1.0)
                        logger.warning(
                            "V2Engine: empty-response chain exhausted; "
                            "LLM_RETRY_FOREVER=true, resetting to %s in %.0fs",
                            initial_model, delay,
                        )
                        use_model = initial_model
                        use_provider = initial_provider
                        retry_count = 0
                        await asyncio.sleep(delay)
                        continue
                    # No fallback — return empty
                    break
                # Success — pass latency for slow-degradation tracking
                call_latency_ms = (time.monotonic() - t0) * 1000
                router.report_success(
                    call_class, use_provider, use_model,
                    latency_ms=call_latency_ms,
                )
                break
            except Exception as exc:
                elapsed = (time.monotonic() - t0) * 1000
                self._log_llm_request_end(
                    provider=use_provider,
                    model=use_model,
                    tier=tier_name,
                    state_type_hint=state_type_hint,
                    round_idx=0,
                    latency_ms=elapsed,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                failure_type = classify_failure(exc)
                opened = router.report_failure(
                    call_class, use_provider, use_model,
                    failure_type, error=str(exc)[:200],
                )

                if failure_type == FailureType.HARD:
                    # Hard fail: limited retries, then switch model
                    if retry_count < max_hard_retries and not opened:
                        retry_count += 1
                        delay = _retry_delay_seconds(retry_count)
                        logger.warning(
                            "V2Engine: hard fail on %s (retry #%d), retrying in %.0fs: %s",
                            use_model, retry_count, delay, exc,
                        )
                        await asyncio.sleep(delay)
                        continue
                else:
                    # Soft fail: slightly more retries allowed
                    if retry_count < config.ROUTER_MAX_SOFT_RETRIES:
                        retry_count += 1
                        delay = _retry_delay_seconds(retry_count)
                        logger.warning(
                            "V2Engine: soft fail on %s (retry #%d), retrying in %.0fs: %s",
                            use_model, retry_count, delay, exc,
                        )
                        await asyncio.sleep(delay)
                        continue

                # ── Router-guided model switch ──
                fb = router.get_fallback(call_class, use_model)
                if fb is not None:
                    logger.warning(
                        "V2Engine: switching %s -> %s after %s",
                        use_model, fb.model, exc,
                    )
                    use_model = fb.model
                    use_provider = fb.provider
                    retry_count = 0
                    await asyncio.sleep(1)
                    continue

                # Fallback chain exhausted. Normally: return None and the step
                # fails. With LLM_RETRY_FOREVER AND a transient (hard) failure,
                # wait at max backoff then reset the chain. Soft failures
                # (programming errors, schema mismatch) still give up — waiting
                # won't fix a deterministic bug.
                if failure_type == FailureType.HARD and config.LLM_RETRY_FOREVER:
                    delay = max(config.LLM_RETRY_MAX_DELAY_SEC, 1.0)
                    logger.warning(
                        "V2Engine: fallback chain exhausted; LLM_RETRY_FOREVER=true, "
                        "resetting to %s and retrying in %.0fs: %s",
                        initial_model, delay, exc,
                    )
                    use_model = initial_model
                    use_provider = initial_provider
                    retry_count = 0
                    await asyncio.sleep(delay)
                    continue

                logger.error("V2Engine: LLM call failed, no fallback: %s", exc)
                return None, "", 0.0, 0

        call_latency = (time.monotonic() - t0) * 1000
        total_latency_ms += call_latency
        usage = getattr(response, "usage", None)
        call_tokens = (
            (getattr(usage, "input_tokens", 0) or 0) +
            (getattr(usage, "output_tokens", 0) or 0)
        ) if usage else 0
        total_tokens += call_tokens

        self._log_llm_request_end(
            provider=use_provider,
            model=use_model,
            tier=tier_name,
            state_type_hint=state_type_hint,
            round_idx=0,
            latency_ms=call_latency,
            status="ok",
            stop_reason=getattr(response, "stop_reason", "") or "",
            tokens=call_tokens,
        )

        raw_text = self._backend.extract_text(response)

        # Session logger
        if self._session_logger is not None:
            thinking_text = self._extract_thinking(response)
            prompt_text_log = self._select_prompt_text_for_logging(messages)
            try:
                self._session_logger.log_llm_call(
                    prompt=prompt_text_log,
                    response=raw_text,
                    latency_ms=call_latency,
                    tokens=call_tokens,
                    call_type="v2_single_call",
                    model=use_model,
                    tier=tier_name,
                    system_prompt=system,
                    thinking_text=thinking_text or "",
                    cache_read_tokens=getattr(usage, "cache_read_input_tokens", 0) or 0,
                    cache_creation_input_tokens=(
                        getattr(usage, "cache_creation_input_tokens", 0) or 0
                    ),
                    prepared_prefix_hash=getattr(self._backend, "_last_prefix_hash", ""),
                    stop_reason=getattr(response, "stop_reason", "") or "",
                    attempt=1,
                    think_budget=0,
                    tools=[],
                    messages=messages,
                    input_tokens=getattr(usage, "input_tokens", 0) or 0,
                    output_tokens=getattr(usage, "output_tokens", 0) or 0,
                )
            except Exception:
                pass

        logger.info(
            "V2Engine[%s/%s]: main call %.0fms %dtok",
            tier_name, state_type_hint, call_latency, call_tokens,
        )

        # ── Extract <decision> ─────────────────────────────────
        decision = extract_decision(raw_text, allow_fallback=True)
        if decision is not None:
            decision = normalize_decision_payload(decision, decision_tool_name)
            errors = validate_decision(decision, decision_tool_name)
            if not errors:
                logger.info(
                    "V2Engine[%s/%s]: decision extracted (%.0fms, %d tok)",
                    tier_name, state_type_hint, total_latency_ms, total_tokens,
                )
                return decision, raw_text, total_latency_ms, total_tokens
            logger.warning("V2Engine: decision validation failed: %s", errors)
            if self._session_logger is not None:
                try:
                    self._session_logger.log_warning(
                        "V2Engine",
                        "decision validation failed",
                        warning_type="decision_validation_failed",
                        errors=errors,
                        decision_tool=decision_tool_name,
                        state_type=state_type_hint,
                        tier=tier_name,
                        model=use_model,
                    )
                except Exception:
                    pass
        else:
            errors = ["No <decision> block found in response"]
            raw_excerpt_head = (raw_text or "")[:600]
            raw_excerpt_tail = (raw_text or "")[-400:] if len(raw_text or "") > 1000 else ""
            logger.warning(
                "V2Engine: no <decision> block in response (len=%d, head=%r)",
                len(raw_text or ""), raw_excerpt_head[:200],
            )
            if self._session_logger is not None:
                try:
                    self._session_logger.log_warning(
                        "V2Engine",
                        "no <decision> block in response",
                        warning_type="missing_decision_block",
                        errors=errors,
                        decision_tool=decision_tool_name,
                        state_type=state_type_hint,
                        tier=tier_name,
                        model=use_model,
                        raw_len=len(raw_text or ""),
                        raw_head=raw_excerpt_head,
                        raw_tail=raw_excerpt_tail,
                        has_think_tag=("<think>" in (raw_text or "")),
                        has_decision_word=("decision" in (raw_text or "").lower()),
                    )
                except Exception:
                    pass

        # ── Repair turn ────────────────────────────────────────
        repair_msg = format_repair_message(errors, tool_name=decision_tool_name)
        repair_messages = list(messages) + [
            {"role": "assistant", "content": raw_text or "(empty)"},
            {"role": "user", "content": repair_msg},
        ]

        repair_response = None
        repair_retry_count = 0
        repair_call_class = "gameplay_repair"
        # Start repair from the model that actually succeeded the main call,
        # not the chain head — avoids bouncing back to a flaky primary.
        repair_model = use_model
        repair_provider = use_provider
        while True:
            self._log_llm_request_start(
                provider=repair_provider,
                model=repair_model,
                tier=tier_name,
                state_type_hint=state_type_hint,
                round_idx=1,
                think_enabled=False,
                tools=[],
                messages=repair_messages,
            )
            t1 = time.monotonic()
            on_first_chunk = self._make_first_chunk_logger(
                provider=repair_provider,
                model=repair_model,
                tier=tier_name,
                state_type_hint=state_type_hint,
                round_idx=1,
                started_at=t1,
            )
            try:
                repair_response = await self._backend.acall(
                    system=system,
                    messages=repair_messages,
                    provider=repair_provider,
                    model=repair_model,
                    think=False,
                    effort="",
                    on_first_chunk=on_first_chunk,
                    tier=tier_name,
                )
                router.report_success(repair_call_class, repair_provider, repair_model)
                break
            except Exception as exc:
                elapsed = (time.monotonic() - t1) * 1000
                self._log_llm_request_end(
                    provider=repair_provider,
                    model=repair_model,
                    tier=tier_name,
                    state_type_hint=state_type_hint,
                    round_idx=1,
                    latency_ms=elapsed,
                    status="error",
                    error=f"{type(exc).__name__}: {exc}",
                )
                ft = classify_failure(exc)
                router.report_failure(
                    repair_call_class, repair_provider, repair_model,
                    ft, error=str(exc)[:200],
                )
                if repair_retry_count < max_hard_retries:
                    repair_retry_count += 1
                    delay = _retry_delay_seconds(repair_retry_count)
                    logger.warning(
                        "V2Engine: repair fail on %s (retry #%d), retrying in %.0fs: %s",
                        repair_model, repair_retry_count, delay, exc,
                    )
                    await asyncio.sleep(delay)
                    continue
                # Try fallback model for repair
                fb = router.get_fallback(repair_call_class, repair_model)
                if fb is not None:
                    repair_model = fb.model
                    repair_provider = fb.provider
                    repair_retry_count = 0
                    await asyncio.sleep(1)
                    continue
                logger.error("V2Engine: repair call failed: %s", exc)
                return None, raw_text, total_latency_ms, total_tokens

        repair_latency = (time.monotonic() - t1) * 1000
        total_latency_ms += repair_latency
        repair_usage = getattr(repair_response, "usage", None)
        repair_tokens = (
            (getattr(repair_usage, "input_tokens", 0) or 0) +
            (getattr(repair_usage, "output_tokens", 0) or 0)
        ) if repair_usage else 0
        total_tokens += repair_tokens

        self._log_llm_request_end(
            provider=repair_provider,
            model=repair_model,
            tier=tier_name,
            state_type_hint=state_type_hint,
            round_idx=1,
            latency_ms=repair_latency,
            status="ok",
            stop_reason=getattr(repair_response, "stop_reason", "") or "",
            tokens=repair_tokens,
        )

        repair_text = self._backend.extract_text(repair_response)
        decision = extract_decision(repair_text, allow_fallback=True)
        if decision is not None:
            decision = normalize_decision_payload(decision, decision_tool_name)
            errors = validate_decision(decision, decision_tool_name)
            if not errors:
                logger.info(
                    "V2Engine[%s/%s]: decision extracted after repair (%.0fms, %d tok)",
                    tier_name, state_type_hint, total_latency_ms, total_tokens,
                )
                return decision, repair_text, total_latency_ms, total_tokens

        # ── Main + repair both failed → router-guided model fallback ──
        # Report soft fail (extraction/truncation, not transport error)
        # and try the next model in the chain.
        router.report_failure(
            call_class, use_provider, use_model,
            FailureType.SOFT, error=f"no decision after repair ({decision_tool_name})",
        )
        fb = router.get_fallback(call_class, use_model)
        if fb is not None:
            logger.warning(
                "V2Engine: main+repair failed on %s, switching to %s for %s",
                use_model, fb.model, decision_tool_name,
            )
            use_model = fb.model
            use_provider = fb.provider
            # Re-derive thinking settings for the new model
            _model_lower = use_model.lower()
            _has_capturable_thinking = "kimi" in _model_lower
            use_think = bool(effort)

            # ── Retry main call with fallback model ──
            response = None
            retry_count = 0
            while True:
                self._log_llm_request_start(
                    provider=use_provider, model=use_model, tier=tier_name,
                    state_type_hint=state_type_hint, round_idx=0,
                    think_enabled=use_think, tools=[], messages=messages,
                )
                t0 = time.monotonic()
                try:
                    response = await self._backend.acall(
                        system=system, messages=messages,
                        provider=use_provider, model=use_model,
                        think=use_think, effort=effort,
                        tier=tier_name,
                    )
                    _resp_text = self._backend.extract_text(response)
                    _resp_usage = getattr(response, "usage", None)
                    _resp_tokens = (
                        (getattr(_resp_usage, "input_tokens", 0) or 0) +
                        (getattr(_resp_usage, "output_tokens", 0) or 0)
                    ) if _resp_usage else 0
                    if not _resp_text.strip() and _resp_tokens == 0:
                        router.report_failure(
                            call_class, use_provider, use_model,
                            FailureType.HARD, error="empty response 0tok (fallback)",
                        )
                        break
                    fb_call_latency = (time.monotonic() - t0) * 1000
                    router.report_success(
                        call_class, use_provider, use_model,
                        latency_ms=fb_call_latency,
                    )
                    break
                except Exception as exc:
                    ft = classify_failure(exc)
                    router.report_failure(
                        call_class, use_provider, use_model,
                        ft, error=str(exc)[:200],
                    )
                    if retry_count < config.ROUTER_MAX_HARD_RETRIES:
                        retry_count += 1
                        await asyncio.sleep(_retry_delay_seconds(retry_count))
                        continue
                    logger.error(
                        "V2Engine: fallback model %s also failed: %s", use_model, exc,
                    )
                    return None, raw_text, total_latency_ms, total_tokens

            if response is not None:
                fb_latency = (time.monotonic() - t0) * 1000
                total_latency_ms += fb_latency
                fb_usage = getattr(response, "usage", None)
                fb_tokens = (
                    (getattr(fb_usage, "input_tokens", 0) or 0) +
                    (getattr(fb_usage, "output_tokens", 0) or 0)
                ) if fb_usage else 0
                total_tokens += fb_tokens

                self._log_llm_request_end(
                    provider=use_provider, model=use_model, tier=tier_name,
                    state_type_hint=state_type_hint, round_idx=0,
                    latency_ms=fb_latency, status="ok",
                    stop_reason=getattr(response, "stop_reason", "") or "",
                    tokens=fb_tokens,
                )

                fb_text = self._backend.extract_text(response)
                decision = extract_decision(fb_text, allow_fallback=True)
                if decision is not None:
                    decision = normalize_decision_payload(decision, decision_tool_name)
                    errors = validate_decision(decision, decision_tool_name)
                    if not errors:
                        logger.info(
                            "V2Engine[%s/%s]: decision from fallback model %s (%.0fms)",
                            tier_name, state_type_hint, use_model, total_latency_ms,
                        )
                        return decision, fb_text, total_latency_ms, total_tokens

        logger.error("V2Engine: all models failed for %s", decision_tool_name)
        return None, raw_text, total_latency_ms, total_tokens

    # ── Internal helpers ───────────────────────────────────────

    @staticmethod
    def _parse_decision(
        decision_input: dict[str, Any],
        *,
        prompt_text: str = "",
        latency_ms: float = 0.0,
        tokens_used: int = 0,
        tool_name: str = "",
    ) -> LLMDecision | None:
        """Parse a decision tool's input dict into an ``LLMDecision``.

        The decision tool input has an ``action`` field and various
        parameters. Sentinel values (``-1``, ``""``) are stripped.

        For plan-style tools (e.g. ``shop_plan``) that have no top-level
        ``action`` field, pass *tool_name* so the tool name is used as
        ``action_name`` and the full dict becomes ``params``.
        """
        from src.brain.models import LLMDecision

        action_name = decision_input.get("action", "")
        if not action_name:
            if tool_name:
                # Plan-style tool: use tool name as action, full dict as params
                reasoning = ""
                raw_reasoning = decision_input.get("reasoning")
                if isinstance(raw_reasoning, str):
                    reasoning = raw_reasoning
                reasoning_zh = ""
                raw_zh = decision_input.get("reasoning_zh")
                if isinstance(raw_zh, str):
                    reasoning_zh = _localize_reasoning_zh(raw_zh)
                params = _clean_params(
                    {
                        k: v
                        for k, v in decision_input.items()
                        if k not in ("reasoning", "reasoning_zh")
                    }
                )
                return LLMDecision(
                    action_name=tool_name,
                    params=params,
                    reasoning=reasoning,
                    reasoning_zh=reasoning_zh,
                    raw_text=json.dumps(decision_input, ensure_ascii=False),
                    prompt_text=prompt_text[:500],
                    latency_ms=latency_ms,
                    tokens_used=tokens_used,
                )
            logger.warning(
                "V2Engine: decision tool output has no 'action': %s",
                decision_input,
            )
            return None

        # Extract reasoning (without mutating the input dict)
        reasoning = ""
        raw_reasoning = decision_input.get("reasoning")
        if isinstance(raw_reasoning, str):
            reasoning = raw_reasoning
        reasoning_zh = ""
        raw_zh = decision_input.get("reasoning_zh")
        if isinstance(raw_zh, str):
            reasoning_zh = _localize_reasoning_zh(raw_zh)

        # Clean sentinel values; exclude action and reasoning fields from params
        excluded = frozenset({"action", "reasoning", "reasoning_zh"})
        params = _clean_params(
            {k: v for k, v in decision_input.items() if k not in excluded}
        )

        return LLMDecision(
            action_name=action_name,
            params=params,
            reasoning=reasoning,
            reasoning_zh=reasoning_zh,
            raw_text=json.dumps(decision_input, ensure_ascii=False),
            prompt_text=prompt_text[:500],
            latency_ms=latency_ms,
            tokens_used=tokens_used,
        )

    @staticmethod
    def _parse_combat_plan(
        plan_input: dict[str, Any],
        *,
        raw_text: str = "",
    ) -> CombatPlan | None:
        """Parse a combat_plan tool's input dict into a ``CombatPlan``.

        The tool input has ``plan`` (array), ``end_turn`` (bool), and
        ``reasoning`` (str). We serialise to JSON and delegate to the
        existing ``parse_combat_plan`` which handles all edge cases.

        ``raw_text`` is the LLM response text the tool input was extracted
        from; when supplied it is attached to the returned plan's
        ``_debug_trace`` field for downstream zh-loss diagnostics.
        """
        try:
            raw_json = json.dumps(plan_input, ensure_ascii=False)
            plan = parse_combat_plan(raw_json)
            if plan is None:
                return None
            import dataclasses
            return dataclasses.replace(plan, _debug_trace={
                "raw_text": (raw_text or "")[:8000],
                "decision_input": plan_input,
            })
        except Exception as exc:
            logger.warning("V2Engine: combat plan parse failed: %s", exc)
            return None

    @staticmethod
    def _content_to_dicts(content_blocks: list[Any]) -> list[dict[str, Any]]:
        """Convert Anthropic ContentBlock objects to plain dicts.

        Anthropic SDK returns typed objects (TextBlock, ToolUseBlock,
        ThinkingBlock). For re-sending as ``assistant`` message content
        we need them as-is (the SDK accepts the objects). This method
        creates a lightweight dict representation for logging/debugging
        while the actual message uses the raw objects.
        """
        result: list[dict[str, Any]] = []
        for block in content_blocks:
            block_type = getattr(block, "type", "unknown")
            if block_type == "text":
                result.append({"type": "text", "text": block.text})
            elif block_type == "tool_use":
                result.append({
                    "type": "tool_use",
                    "id": block.id,
                    "name": block.name,
                    "input": block.input,
                })
            elif block_type == "thinking":
                result.append({
                    "type": "thinking",
                    "thinking": getattr(block, "thinking", ""),
                })
            else:
                # Preserve unknown block types
                result.append({"type": block_type})
        return result

    @staticmethod
    def _extract_user_message_text(content: Any) -> str:
        """Extract textual content from a user message payload."""
        if isinstance(content, str):
            return content

        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text" and isinstance(block.get("text"), str):
                        parts.append(block["text"])
                    continue

                if getattr(block, "type", None) == "text":
                    text = getattr(block, "text", "")
                    if isinstance(text, str):
                        parts.append(text)

            return "\n".join(part for part in parts if part).strip()

        return ""

    @staticmethod
    def _is_internal_nudge(text: str) -> bool:
        """Detect internal user nudges appended by the agent loop."""
        stripped = text.strip()
        return (
            stripped.startswith("You have used all your research rounds.")
            or stripped.startswith("You must call the `")
        )

    @staticmethod
    def _is_stateful_user_message(text: str) -> bool:
        """Heuristic: does this user text look like a real state snapshot?"""
        markers = (
            "## Round ",
            "## Combat Start",
            "## Run Context",
            "## Hand",
            "## Enemies",
            "## Piles",
            "## Current Deck",
        )
        return any(marker in text for marker in markers)

    @staticmethod
    def _select_prompt_text_for_logging(messages: list[dict[str, Any]]) -> str:
        """Pick the most useful user prompt text for llm_call logging.

        Preference order:
          1. Most recent stateful user message (latest combat round / state snapshot)
          2. Most recent non-nudge textual user message
          3. Most recent textual user message of any kind
        """
        latest_text = ""
        latest_non_nudge = ""

        for message in reversed(messages):
            if message.get("role") != "user":
                continue

            text = V2Engine._extract_user_message_text(message.get("content", ""))
            if not text:
                continue

            if not latest_text:
                latest_text = text

            if V2Engine._is_stateful_user_message(text):
                return text

            if not latest_non_nudge and not V2Engine._is_internal_nudge(text):
                latest_non_nudge = text

        return latest_non_nudge or latest_text

    @staticmethod
    def _extract_thinking(response: Any) -> str:
        """Extract thinking text from a response, if present."""
        # Anthropic: thinking blocks in content
        for block in response.content:
            if getattr(block, "type", None) == "thinking":
                return getattr(block, "thinking", "")
        # OpenAI-compat (kimi): _reasoning_content attribute
        rc = getattr(response, "_reasoning_content", "")
        if rc:
            return rc
        return ""
