"""Resample (system, user) prompts via the dedicated a relay_gemini source.

Uses scripts._prompt_ab.direct_caller (pure httpx, no model-family fallback).
This guarantees A vs B comparison is always against the SAME model.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from scripts._prompt_ab.direct_caller import DirectCallError, call_a relay_gemini

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResampleResult:
    """One resample attempt for a (sample, version, attempt_index) tuple."""
    response_text: str
    latency_ms: float
    tokens: int
    error: str = ""


async def resample_one(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    timeout_s: float = 180.0,
    max_attempts: int = 6,
    backoff_base_s: float = 2.0,
) -> ResampleResult:
    """Single resample with timeout, error capture, and retry on transient failures.

    No fallback to other models — retries the SAME model+endpoint.
    Up to ``max_attempts`` attempts with exponential backoff
    (2s, 4s, 8s, 16s, 32s for default 6 attempts).
    """
    last_error = ""
    for attempt in range(max_attempts):
        try:
            text, latency_ms, tokens = await asyncio.wait_for(
                call_a relay_gemini(
                    system=system_prompt,
                    user=user_message,
                    model=model,
                    timeout_s=timeout_s,
                ),
                timeout=timeout_s + 10,
            )
            if text:
                return ResampleResult(
                    response_text=text, latency_ms=latency_ms, tokens=tokens,
                )
            last_error = "empty response"
        except (asyncio.TimeoutError, DirectCallError, Exception) as exc:  # noqa: BLE001
            last_error = repr(exc)
            logger.warning(
                "resample attempt %d/%d failed for model=%s: %s",
                attempt + 1, max_attempts, model, str(exc)[:200],
            )
        if attempt < max_attempts - 1:
            await asyncio.sleep(backoff_base_s * (2 ** attempt))
    return ResampleResult(
        response_text="", latency_ms=0.0, tokens=0, error=last_error,
    )


async def resample_pair(
    *,
    system_prompt: str,
    user_a: str,
    user_b: str,
    model: str,
    samples_per_version: int = 3,
    concurrency: int = 4,
) -> tuple[list[ResampleResult], list[ResampleResult]]:
    """Resample A and B versions in parallel, ``samples_per_version`` each.

    Bounded concurrency keeps us under provider-side rate limits.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(user: str) -> ResampleResult:
        async with sem:
            return await resample_one(
                system_prompt=system_prompt, user_message=user, model=model
            )

    a_tasks = [asyncio.create_task(_one(user_a)) for _ in range(samples_per_version)]
    b_tasks = [asyncio.create_task(_one(user_b)) for _ in range(samples_per_version)]
    a_results = await asyncio.gather(*a_tasks)
    b_results = await asyncio.gather(*b_tasks)
    return list(a_results), list(b_results)
