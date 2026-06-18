"""SSE (Server-Sent Events) client for upstream event notifications.

Upstream `/events/stream` does not push full `/state` payloads. It emits
lightweight event envelopes such as `screen_changed` and
`available_actions_changed`. Callers use these events as wake-up signals and
fetch `/state` on demand.
"""

from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from typing import Any

import httpx

import config
from src.mcp_client import cjk_audit

logger = logging.getLogger(__name__)

StateFetcher = Callable[[], Awaitable[dict]]


@dataclass(frozen=True, slots=True)
class SseEvent:
    """One parsed SSE message from the upstream event stream."""

    name: str
    data: Any = None
    event_id: str | None = None
    envelope: dict[str, Any] | None = None


def _decode_sse_event(
    event_name: str,
    data_lines: list[str],
    event_id: str | None = None,
) -> SseEvent | None:
    """Decode one SSE message into a normalized upstream event."""
    if not event_name and not data_lines and event_id is None:
        return None

    raw_data = "\n".join(data_lines)
    parsed_data: Any = raw_data
    if raw_data:
        try:
            parsed_data = json.loads(raw_data)
        except json.JSONDecodeError:
            parsed_data = raw_data

    envelope = parsed_data if isinstance(parsed_data, dict) else None
    normalized_name = event_name or "message"
    normalized_data = parsed_data
    normalized_event_id = event_id

    if envelope is not None:
        normalized_name = str(envelope.get("type") or event_name or "message")
        normalized_data = envelope.get("data", parsed_data)
        if normalized_event_id is None and envelope.get("event_id") is not None:
            normalized_event_id = str(envelope["event_id"])

    return SseEvent(
        name=normalized_name,
        data=normalized_data,
        event_id=normalized_event_id,
        envelope=envelope,
    )


class SseStateStream:
    """Async SSE client for upstream `/events/stream`.

    A background task consumes the SSE response exactly once and pushes parsed
    events into a bounded queue so waiters can iterate safely.
    """

    def __init__(
        self,
        base_url: str = config.MCP_BASE_URL,
        timeout: float = 30.0,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/events/stream"
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._response: httpx.Response | None = None
        self._connected = False
        self._queue: asyncio.Queue[SseEvent | None] = asyncio.Queue(maxsize=64)
        self._reader_task: asyncio.Task | None = None

    async def connect(self) -> None:
        """Establish the SSE connection and start the background reader."""
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(self._timeout, read=None))
        try:
            request = self._client.build_request(
                "GET",
                self._url,
                headers={
                    "Accept": "text/event-stream",
                    "Cache-Control": "no-cache",
                },
            )
            self._response = await self._client.send(request, stream=True)
            self._response.raise_for_status()
            self._connected = True
            self._reader_task = asyncio.create_task(self._read_loop())
            logger.info("SSE connected to %s", self._url)
        except (httpx.ConnectError, httpx.HTTPStatusError) as e:
            logger.warning("SSE connection failed: %s — falling back to polling", e)
            self._connected = False

    async def _read_loop(self) -> None:
        """Background task: parse SSE messages and push events to the queue."""
        try:
            event_name = ""
            event_id = None
            data_lines: list[str] = []

            async for raw_line in self._response.aiter_lines():
                line = raw_line.rstrip("\r\n")

                if not line:
                    event = _decode_sse_event(event_name, data_lines, event_id)
                    if event is not None:
                        cjk_audit.audit(f"sse:{event.name}", event.data)
                        if self._queue.full():
                            try:
                                self._queue.get_nowait()
                            except asyncio.QueueEmpty:
                                pass
                        await self._queue.put(event)
                    event_name = ""
                    event_id = None
                    data_lines = []
                    continue

                if line.startswith(":"):
                    continue

                field, _, value = line.partition(":")
                if value.startswith(" "):
                    value = value[1:]

                if field == "event":
                    event_name = value
                elif field == "id":
                    event_id = value or None
                elif field == "data":
                    data_lines.append(value)
        except Exception as e:
            logger.warning("SSE reader stopped: %s", e)
        finally:
            self._connected = False
            try:
                self._queue.put_nowait(None)
            except asyncio.QueueFull:
                pass

    async def close(self) -> None:
        """Close the SSE connection."""
        if self._reader_task and not self._reader_task.done():
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass
            self._reader_task = None
        if self._response:
            await self._response.aclose()
            self._response = None
        if self._client:
            await self._client.aclose()
            self._client = None
        self._connected = False

    async def __aenter__(self) -> SseStateStream:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    @property
    def is_connected(self) -> bool:
        return self._connected

    async def __aiter__(self) -> AsyncIterator[SseEvent]:
        """Yield parsed events from the shared queue."""
        while self._connected or not self._queue.empty():
            try:
                event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except (asyncio.TimeoutError, TimeoutError):
                if not self._connected:
                    return
                continue
            if event is None:
                return
            yield event


def _matches_game_state(raw_state: dict, predicate: Callable[[Any], bool]) -> bool:
    """Parse a raw state payload and apply the given predicate."""
    from src.state.state_parser import safe_parse_state

    gs = safe_parse_state(raw_state)
    return gs is not None and predicate(gs)


async def _wait_for_matching_state(
    stream: SseStateStream,
    fetch_state: StateFetcher,
    predicate: Callable[[Any], bool],
    timeout: float,
) -> dict | None:
    """Wait for upstream events, fetching `/state` until the predicate matches."""
    try:
        initial_state = await fetch_state()
        if _matches_game_state(initial_state, predicate):
            return initial_state

        async with asyncio.timeout(timeout):
            async for event in stream:
                if event.name == "error":
                    logger.warning("SSE error event received: %s", event.data)
                    continue

                raw_state = await fetch_state()
                if _matches_game_state(raw_state, predicate):
                    return raw_state
    except TimeoutError:
        return None

    return None


async def wait_for_state_change_sse(
    stream: SseStateStream,
    fetch_state: StateFetcher,
    prev_state_type: str,
    timeout: float = config.STATE_CHANGE_TIMEOUT,
) -> dict | None:
    """Wait for `state_type` to change using upstream SSE events plus `/state`."""
    return await _wait_for_matching_state(
        stream,
        fetch_state,
        lambda gs: gs.state_type != prev_state_type,
        timeout,
    )


async def wait_for_play_phase_sse(
    stream: SseStateStream,
    fetch_state: StateFetcher,
    timeout: float = config.STATE_CHANGE_TIMEOUT,
) -> dict | None:
    """Wait until combat is actionable again using SSE-triggered state refreshes."""
    return await _wait_for_matching_state(
        stream,
        fetch_state,
        lambda gs: gs.is_play_phase or not gs.is_combat,
        timeout,
    )
