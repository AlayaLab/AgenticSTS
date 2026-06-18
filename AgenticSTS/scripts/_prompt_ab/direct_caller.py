"""Direct httpx caller for the harness — no family fallback.

Bypasses ``src.brain.llm_caller.call_raw`` (which has multi-family fallback)
and posts straight to ``STS2_a relay_GEMINI_BASE_URL`` with
``STS2_a relay_GEMINI_API_KEY``. This is for the prompt-reorder A/B test
specifically: we want pure same-model A vs B comparison, not a fallback
chain that drifts to a different family on transient errors.
"""
from __future__ import annotations

import os
import time

import httpx


class DirectCallError(RuntimeError):
    """Raised when the direct call fails after all retries."""


def _resolve_credentials() -> tuple[str, str]:
    base = os.environ.get("STS2_a relay_GEMINI_BASE_URL", "").rstrip("/")
    key = os.environ.get("STS2_a relay_GEMINI_API_KEY", "")
    if not base or not key:
        raise DirectCallError(
            "STS2_a relay_GEMINI_BASE_URL and STS2_a relay_GEMINI_API_KEY must be set"
        )
    return base, key


def _endpoint(base_url: str) -> str:
    if base_url.endswith("/chat/completions"):
        return base_url
    if base_url.endswith("/v1"):
        return f"{base_url}/chat/completions"
    return f"{base_url}/v1/chat/completions"


async def call_a relay_gemini(
    *,
    system: str,
    user: str,
    model: str = "gemini-3.1-pro-preview",
    timeout_s: float = 180.0,
) -> tuple[str, float, int]:
    """Send a single non-streaming chat completion. Returns (text, latency_ms, tokens).

    Raises DirectCallError on HTTP error or malformed response.
    """
    base_url, api_key = _resolve_credentials()
    endpoint = _endpoint(base_url)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        "stream": False,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    t0 = time.perf_counter()
    async with httpx.AsyncClient(timeout=timeout_s) as client:
        resp = await client.post(endpoint, json=payload, headers=headers)
    latency_ms = (time.perf_counter() - t0) * 1000.0
    if resp.status_code != 200:
        raise DirectCallError(f"HTTP {resp.status_code}: {resp.text[:500]}")
    try:
        body = resp.json()
        choice = body["choices"][0]
        text = choice["message"]["content"] or ""
        tokens = int(body.get("usage", {}).get("total_tokens") or 0)
    except (KeyError, IndexError, ValueError, TypeError) as exc:
        raise DirectCallError(f"malformed response: {exc} | body={resp.text[:500]}") from exc
    return text, latency_ms, tokens
