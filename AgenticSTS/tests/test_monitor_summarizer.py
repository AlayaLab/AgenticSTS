from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import config
from src.monitor.summarizer import EventSummarizer


def test_event_summarizer_uses_postrun_profile_for_summary_calls():
    backend = MagicMock()
    backend.acall = AsyncMock(
        return_value=SimpleNamespace(content=[SimpleNamespace(text="short summary")])
    )
    summarizer = EventSummarizer(event_bus=MagicMock())
    summarizer._backend = backend

    result = asyncio.run(summarizer._call_haiku("reasoning text", "llm_call"))

    assert result == "short summary"
    kwargs = backend.acall.await_args.kwargs
    assert kwargs["provider"] == config.LLM_ANALYSIS_PROVIDER
    assert kwargs["model"] == config.MONITOR_SUMMARY_MODEL
    assert kwargs["openai_relay_profile"] == "postrun"
