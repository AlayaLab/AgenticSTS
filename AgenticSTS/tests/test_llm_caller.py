from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import httpx
import pytest

import config
import src.brain.llm_caller as llm_caller


def _make_response(text: str) -> SimpleNamespace:
    return SimpleNamespace(
        content=[SimpleNamespace(text=text)],
        usage=SimpleNamespace(input_tokens=7, output_tokens=5),
    )


async def _immediate_sleep(_delay: float) -> None:
    return None


def test_call_raw_retries_transient_timeout_until_success(monkeypatch):
    """Post-run LLM calls should keep retrying retryable transport errors."""
    backend = MagicMock()
    backend.acall = AsyncMock(
        side_effect=[
            Exception("The read operation timed out"),
            _make_response("ok"),
        ]
    )
    backend._is_openai_failover_error = MagicMock(return_value=False)

    monkeypatch.setattr(llm_caller, "_get_or_create_backend", lambda: backend)
    monkeypatch.setattr(llm_caller.asyncio, "sleep", _immediate_sleep)
    monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)
    monkeypatch.setattr(config, "LLM_RETRY_BASE_DELAY_SEC", 0.01)
    monkeypatch.setattr(config, "LLM_RETRY_MAX_DELAY_SEC", 0.02)

    text, _latency_ms, tokens = asyncio.run(
        llm_caller.call_raw("system", "prompt", provider="anthropic", model="test-model")
    )

    assert text == "ok"
    assert tokens == 12
    assert backend.acall.await_count == 2


def test_call_raw_retries_openai_upstream_400_until_success(monkeypatch):
    """OpenAI-compatible upstream 400s should stay on the retry path."""
    request = httpx.Request("POST", "https://relay.example/v1/chat/completions")
    response = httpx.Response(
        400,
        request=request,
        text=(
            '{"error":{"message":"Invalid project resource name",'
            '"type":"upstream_error","code":400}}'
        ),
    )
    exc = httpx.HTTPStatusError("400 upstream", request=request, response=response)

    backend = MagicMock()
    backend.acall = AsyncMock(side_effect=[exc, _make_response("ok")])
    backend._is_openai_failover_error = MagicMock(return_value=True)

    monkeypatch.setattr(llm_caller, "_get_or_create_backend", lambda: backend)
    monkeypatch.setattr(llm_caller.asyncio, "sleep", _immediate_sleep)
    monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)
    monkeypatch.setattr(config, "LLM_RETRY_BASE_DELAY_SEC", 0.01)
    monkeypatch.setattr(config, "LLM_RETRY_MAX_DELAY_SEC", 0.02)

    text, _latency_ms, tokens = asyncio.run(
        llm_caller.call_raw(
            "system",
            "prompt",
            provider="openai_compatible",
            model="gemini-3.1-pro-preview",
        )
    )

    assert text == "ok"
    assert tokens == 12
    assert backend.acall.await_count == 2


def test_call_raw_raises_soft_errors_after_exhausting_fallbacks(monkeypatch):
    """Soft failures (e.g. ValueError) are retried through the model fallback chain,
    then raised after all models are exhausted."""
    backend = MagicMock()
    backend.acall = AsyncMock(side_effect=ValueError("prompt schema mismatch"))
    backend._is_openai_failover_error = MagicMock(return_value=False)

    monkeypatch.setattr(llm_caller, "_get_or_create_backend", lambda: backend)
    monkeypatch.setattr(llm_caller.asyncio, "sleep", _immediate_sleep)
    monkeypatch.setattr(config, "LLM_RETRY_FOREVER", True)

    with pytest.raises(ValueError, match="prompt schema mismatch"):
        asyncio.run(llm_caller.call_raw("system", "prompt", provider="anthropic"))

    # Router retries soft failures per model then falls back through all models
    assert backend.acall.await_count > 1


def test_call_raw_defaults_to_postrun_relay_profile(monkeypatch):
    backend = MagicMock()
    backend.acall = AsyncMock(return_value=_make_response("ok"))

    monkeypatch.setattr(llm_caller, "_get_or_create_backend", lambda: backend)

    text, _latency_ms, tokens = asyncio.run(
        llm_caller.call_raw("system", "prompt", provider="openai_compatible", model="gpt-5.4-thinking")
    )

    assert text == "ok"
    assert tokens == 12
    assert backend.acall.await_args.kwargs["openai_relay_profile"] == "postrun"
