"""Background AI summarizer for monitor events.

Watches the EventBus for llm_call and combat_plan events,
generates concise English summaries via the configured post-run model,
and emits ai_summary events back to the EventBus.
"""

from __future__ import annotations

import asyncio
import logging
import queue
from typing import Any

import config

logger = logging.getLogger(__name__)

SUMMARY_MODEL = config.MONITOR_SUMMARY_MODEL
SUMMARY_MAX_INPUT = 2000  # max chars of thinking/reasoning to send
SUMMARY_MAX_PENDING = 20  # skip older events if queue backs up
SUMMARY_MIN_INTERVAL = 5.0  # seconds between summary calls to avoid starving gameplay API

SYSTEM_PROMPT = (
    "You are a concise game AI summarizer. "
    "Summarize the key decision/reasoning in 1-2 short English sentences. "
    "Focus on WHAT was decided and WHY. Be specific about card names, enemies, and numbers."
)


class EventSummarizer:
    """Background summarizer that processes monitor events via the post-run LLM."""

    def __init__(self, event_bus: Any) -> None:
        self._event_bus = event_bus
        self._backend: Any = None  # lazy-init V2Backend
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._queue: queue.Queue[Any] | None = None

    def start(self) -> None:
        """Subscribe to EventBus and start background processing."""
        self._queue = self._event_bus.subscribe()
        self._running = True
        self._task = asyncio.ensure_future(self._process_loop())
        logger.info("EventSummarizer started (model=%s)", SUMMARY_MODEL)

    def stop(self) -> None:
        """Stop processing and unsubscribe."""
        self._running = False
        if self._queue:
            self._event_bus.unsubscribe(self._queue)
        if self._task:
            self._task.cancel()

    async def _process_loop(self) -> None:
        """Main loop: read events from queue, summarize eligible ones."""
        loop = asyncio.get_event_loop()
        while self._running:
            try:
                # Blocking get with 1s timeout (run in executor to not block event loop)
                event = await loop.run_in_executor(
                    None, lambda: self._queue.get(timeout=1.0),  # type: ignore[union-attr]
                )
            except queue.Empty:
                continue
            except Exception:
                continue

            if not self._should_summarize(event):
                continue

            # Backpressure: if the subscriber queue has backed up beyond
            # the threshold, skip this event to drain faster.  qsize()
            # reflects the real pending count (items the EventBus pushed
            # but we haven't consumed yet), unlike a local counter that
            # stays at 1 in a serial loop.
            try:
                backlog = self._queue.qsize()  # type: ignore[union-attr]
            except Exception:
                backlog = 0
            if backlog > SUMMARY_MAX_PENDING:
                logger.debug(
                    "Summarizer backpressure (backlog=%d): skipping %s",
                    backlog, event.id,
                )
                continue

            try:
                await self._summarize_event(event)
                # Throttle: avoid starving gameplay API calls on shared proxy
                await asyncio.sleep(SUMMARY_MIN_INTERVAL)
            except Exception as exc:
                logger.debug("Summarizer failed for %s: %s", event.id, exc)

    @staticmethod
    def _should_summarize(event: Any) -> bool:
        """Check if event has content worth summarizing."""
        if event.type == "llm_call":
            return bool(event.data.get("thinking_text"))
        if event.type == "combat_plan":
            return bool(event.data.get("reasoning"))
        return False

    async def _summarize_event(self, event: Any) -> None:
        """Call Haiku to summarize, then emit ai_summary event."""
        if event.type == "llm_call":
            text = str(event.data.get("thinking_text", ""))
        elif event.type == "combat_plan":
            text = str(event.data.get("reasoning", ""))
        else:
            return

        if not text.strip():
            return

        # Truncate input
        if len(text) > SUMMARY_MAX_INPUT:
            text = text[:SUMMARY_MAX_INPUT] + "..."

        summary = await self._call_haiku(text, event.type)
        if summary:
            self._event_bus.emit(
                "ai_summary",
                {"parent_id": event.id, "summary": summary},
                run_id=event.run_id,
            )

    async def _call_haiku(self, text: str, event_type: str) -> str:
        """Call the configured post-run model for a concise summary."""
        if self._backend is None:
            self._backend = self._init_backend()

        from src.brain.llm_router import (
            FailureType,
            classify_failure,
            get_router,
        )
        router = get_router()
        call_class = "monitor_summary"
        selection = router.select_model(call_class)

        prompt = f"Summarize this {event_type} reasoning:\n\n{text}"

        try:
            response = await self._backend.acall(
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
                provider=selection.provider,
                model=selection.model,
                max_tokens=150,
                openai_relay_profile="postrun",
            )
            router.report_success(call_class, selection.provider, selection.model)
        except Exception as exc:
            router.report_failure(
                call_class, selection.provider, selection.model,
                classify_failure(exc), error=str(exc)[:200],
            )
            logger.debug("Summary LLM call failed: %s", exc)
            return ""

        result = ""
        for block in response.content:
            if hasattr(block, "text"):
                result += block.text
        return result.strip()

    @staticmethod
    def _init_backend() -> Any:
        """Lazy-initialize V2Backend for summary calls."""
        from src.brain.v2_backend import V2Backend

        return V2Backend()
