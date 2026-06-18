"""Thin LLM calling adapter for post-run analysis tasks.

Wraps V2Backend.acall() to provide the simple
  call_raw(system, prompt, think) -> (text, latency_ms, tokens)
interface used by guide_consolidator and skill discovery.

This replaces the old LLMReasoner.call_raw() interface.
"""

from __future__ import annotations

import asyncio
import logging
import re
import time

import config
from src.brain.llm_router import (
    FailureType,
    classify_failure,
    get_router,
)
from src.brain.v2_engine import _retry_delay_seconds

logger = logging.getLogger(__name__)

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)

_backend = None
_session_logger = None  # Set before post-run to enable telemetry


def set_session_logger(sl: object | None) -> None:
    """Set the session logger for post-run LLM call telemetry."""
    global _session_logger
    _session_logger = sl


def _get_or_create_backend():
    """Lazy-init a V2Backend for post-run LLM calls."""
    global _backend
    if _backend is None:
        from src.brain.v2_backend import V2Backend
        _backend = V2Backend()
    return _backend


async def call_raw(
    system: str,
    prompt: str,
    think: bool = False,
    model: str | None = None,
    effort: str = "",
    provider: str | None = None,
    openai_relay_profile: str = "postrun",
    session_logger: object | None = None,
    call_type: str = "",
    call_class: str = "",
    max_tokens: int | None = None,
) -> tuple[str, float, int]:
    """Call LLM and return (response_text, latency_ms, total_tokens).

    Drop-in replacement for the old LLMReasoner.call_raw() interface.
    Uses analysis tier model/provider by default for post-run tasks.
    Pass provider= explicitly when calling with a gameplay-tier model.

    Args:
        call_class: Explicit router call class.  When empty, inferred from
            ``call_type`` and ``openai_relay_profile``:
            - ``openai_relay_profile="default"`` → ``"gameplay_strategic"``
            - ``call_type`` containing "summary"/"consolidat" →
              ``"postrun_summary"``
            - otherwise ``"postrun_analysis"``

    Now uses the global health-aware router for model selection and
    fallback on ALL error types (not just content_filter).
    """
    backend = _get_or_create_backend()
    start = time.monotonic()

    messages = [{"role": "user", "content": prompt}]

    # WARNING: this name-based heuristic routes any call_type containing
    # "summary" or "consolidat" to the postrun_summary chain (monitor's
    # gpt-5.4-mini), which is wrong for analysis-tier work. The previously
    # bug-inducing call_type "core_engine_summary" was removed in the
    # 2026-04-25 core-engine stage merge (see
    # docs/superpowers/specs/2026-04-25-core-engine-merge-to-turn2-design.md)
    # by deleting the call site;
    # any future caller whose call_type contains those substrings but
    # actually wants the analysis tier MUST pass explicit
    # call_class="postrun_analysis" to bypass this heuristic.
    # Determine call class for router
    if not call_class:
        if openai_relay_profile == "default":
            # Gameplay call going through call_raw (e.g. route selection)
            call_class = "gameplay_strategic"
        elif call_type and (
            "summary" in call_type.lower() or "consolidat" in call_type.lower()
        ):
            call_class = "postrun_summary"
        else:
            call_class = "postrun_analysis"

    router = get_router()
    _sl = session_logger or _session_logger
    router.set_session_logger(_sl)

    # Router respects caller's preferred model if healthy, falls back otherwise.
    selection = router.select_model(
        call_class,
        preferred_provider=provider or "",
        preferred_model=model or "",
    )
    use_model = selection.model
    use_provider = selection.provider
    use_effort = effort or config.LLM_THINK_EFFORT_ANALYSIS

    # Snapshot the initial selection so retry-forever can restart the fallback
    # chain from its head after every model in the chain has been exhausted.
    initial_model = use_model
    initial_provider = use_provider

    retry_count = 0
    max_hard_retries = config.ROUTER_MAX_HARD_RETRIES
    while True:
        try:
            response = await backend.acall(
                system=system,
                messages=messages,
                provider=use_provider,
                model=use_model,
                think=think,
                effort=use_effort if think else "",
                openai_relay_profile=openai_relay_profile,
                max_tokens=max_tokens,
            )

            # Detect empty response
            text = ""
            for block in response.content:
                if hasattr(block, "text"):
                    text += block.text

            resp_usage = getattr(response, "usage", None)
            resp_tokens = 0
            if resp_usage:
                resp_tokens = (
                    (getattr(resp_usage, "input_tokens", 0) or 0) +
                    (getattr(resp_usage, "output_tokens", 0) or 0)
                )

            if not text.strip() and resp_tokens == 0:
                # Empty response = hard fail
                router.report_failure(
                    call_class, use_provider, use_model,
                    FailureType.HARD, error="empty response 0tok",
                )
                fb = router.get_fallback(call_class, use_model)
                if fb is not None:
                    logger.warning(
                        "call_raw: empty response on %s, switching to %s",
                        use_model, fb.model,
                    )
                    use_model = fb.model
                    use_provider = fb.provider
                    retry_count = 0
                    await asyncio.sleep(1)
                    continue
                # Fallback chain exhausted on empty responses.
                if config.LLM_RETRY_FOREVER:
                    delay = max(config.LLM_RETRY_MAX_DELAY_SEC, 1.0)
                    logger.warning(
                        "call_raw: empty-response chain exhausted; "
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

            call_latency_ms = (time.monotonic() - start) * 1000
            router.report_success(
                call_class, use_provider, use_model,
                latency_ms=call_latency_ms,
            )
            break
        except Exception as exc:
            failure_type = classify_failure(exc)
            opened = router.report_failure(
                call_class, use_provider, use_model,
                failure_type, error=str(exc)[:200],
            )

            if failure_type == FailureType.HARD:
                if retry_count < max_hard_retries and not opened:
                    retry_count += 1
                    delay = _retry_delay_seconds(retry_count)
                    logger.warning(
                        "call_raw: hard fail on %s (retry #%d), retrying in %.0fs: %s",
                        use_model, retry_count, delay, exc,
                    )
                    await asyncio.sleep(delay)
                    continue
            else:
                if retry_count < config.ROUTER_MAX_SOFT_RETRIES:
                    retry_count += 1
                    delay = _retry_delay_seconds(retry_count)
                    logger.warning(
                        "call_raw: soft fail on %s (retry #%d), retrying in %.0fs: %s",
                        use_model, retry_count, delay, exc,
                    )
                    await asyncio.sleep(delay)
                    continue

            # Switch model via router
            fb = router.get_fallback(call_class, use_model)
            if fb is not None:
                logger.warning(
                    "call_raw: switching %s -> %s after %s",
                    use_model, fb.model, exc,
                )
                use_model = fb.model
                use_provider = fb.provider
                retry_count = 0
                await asyncio.sleep(1)
                continue

            # Fallback chain exhausted. Normally: give up. With LLM_RETRY_FOREVER
            # AND a transient (hard) failure, wait out at max backoff, reset to
            # the chain head, and try again — assumes the network will return.
            # Soft failures (programming errors, schema mismatches) still raise:
            # waiting on them would just spin forever on a deterministic bug.
            if failure_type == FailureType.HARD and config.LLM_RETRY_FOREVER:
                delay = max(config.LLM_RETRY_MAX_DELAY_SEC, 1.0)
                logger.warning(
                    "call_raw: fallback chain exhausted; LLM_RETRY_FOREVER=true, "
                    "resetting to %s and retrying in %.0fs: %s",
                    initial_model, delay, exc,
                )
                use_model = initial_model
                use_provider = initial_provider
                retry_count = 0
                await asyncio.sleep(delay)
                continue

            raise

    # Extract text from anthropic.Message response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Strip <thinking> tags injected by proxy (proxy.example.com converts thinking blocks to text tags)
    if think and "<thinking>" in text:
        text = _THINKING_TAG_RE.sub("", text).strip()

    latency_ms = (time.monotonic() - start) * 1000
    tokens = 0
    input_tok = 0
    output_tok = 0
    if response.usage:
        input_tok = getattr(response.usage, "input_tokens", 0) or 0
        output_tok = getattr(response.usage, "output_tokens", 0) or 0
        # OpenAI-compat fallback
        if not input_tok:
            input_tok = getattr(response.usage, "prompt_tokens", 0) or 0
            output_tok = getattr(response.usage, "completion_tokens", 0) or 0
        tokens = input_tok + output_tok

    # Extract thinking text if the backend surfaced reasoning blocks
    thinking_text = ""
    try:
        for block in response.content:
            btype = getattr(block, "type", "")
            if btype == "thinking":
                thinking_text += getattr(block, "thinking", "") or getattr(
                    block, "text", "",
                )
        if not thinking_text:
            thinking_text = getattr(response, "_reasoning_content", "") or ""
    except Exception:
        thinking_text = ""

    # Post-run telemetry (use explicit param or module-level logger).
    if _sl is not None and call_type and hasattr(_sl, "log_postrun_llm_call"):
        try:
            _sl.log_postrun_llm_call(
                call_type=call_type,
                model=use_model,
                provider=use_provider,
                effort=use_effort if think else "",
                input_tokens=input_tok,
                output_tokens=output_tok,
                latency_ms=round(latency_ms),
                system_prompt=system,
                prompt=prompt,
                response=text,
                thinking_text=thinking_text,
            )
        except Exception:
            pass  # Telemetry never crashes the pipeline

    return text, latency_ms, tokens


def reset():
    """Reset the cached backend (for testing)."""
    global _backend
    _backend = None
