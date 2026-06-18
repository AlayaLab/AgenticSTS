"""Thread-safe broadcast EventBus for real-time monitoring.

Design:
- Per-subscriber queues: each WebSocket client gets its own queue
- emit() is synchronous and safe to call from ANY thread
- Ring buffer for reconnect catch-up
- Absolute silence: emit() never raises, never blocks the agent
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from uuid import uuid4

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class MonitorEvent:
    """Immutable event envelope for the monitoring stream."""

    id: str
    timestamp: float
    type: str
    data: dict
    step: int | None = None
    run_id: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class EventBus:
    """Thread-safe broadcast event bus.

    Each subscriber gets a dedicated queue.Queue so all clients
    receive all events (true broadcast, not competitive consume).
    """

    # Lifecycle event types that are preserved separately so run history
    # survives even when the main buffer wraps around.
    _LIFECYCLE_TYPES = frozenset({"run_start", "run_end"})

    def __init__(self, buffer_size: int = 10000, queue_size: int = 2000) -> None:
        self._subscribers: list[queue.Queue[MonitorEvent]] = []
        self._lock = threading.Lock()
        self._buffer: deque[MonitorEvent] = deque(maxlen=buffer_size)
        self._lifecycle_buffer: list[MonitorEvent] = []  # Never evicted
        self._queue_size = queue_size
        self._enabled = False
        self._event_count = 0

    def enable(self) -> None:
        self._enabled = True
        logger.info("EventBus enabled (buffer=%d)", self._buffer.maxlen)

    def disable(self) -> None:
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def event_count(self) -> int:
        return self._event_count

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    def emit(
        self,
        event_type: str,
        data: dict,
        step: int | None = None,
        run_id: str | None = None,
    ) -> None:
        """Fire-and-forget event broadcast. Safe from ANY thread. Never raises."""
        if not self._enabled:
            return
        try:
            event = MonitorEvent(
                id=uuid4().hex,
                timestamp=time.time(),
                type=event_type,
                data=data,
                step=step,
                run_id=run_id,
            )
            self._buffer.append(event)
            self._event_count += 1
            # Preserve lifecycle events in a separate never-evicted buffer
            if event_type in self._LIFECYCLE_TYPES:
                self._lifecycle_buffer.append(event)

            with self._lock:
                for q in self._subscribers:
                    try:
                        q.put_nowait(event)
                    except queue.Full:
                        # Drop oldest for slow client, then push new
                        try:
                            q.get_nowait()
                            q.put_nowait(event)
                        except (queue.Empty, queue.Full):
                            pass
        except Exception:
            # Absolute silence — monitor never crashes agent
            pass

    def subscribe(self) -> queue.Queue[MonitorEvent]:
        """Create a new subscriber queue. Called by each WebSocket handler."""
        q: queue.Queue[MonitorEvent] = queue.Queue(maxsize=self._queue_size)
        with self._lock:
            self._subscribers.append(q)
        logger.info("EventBus: subscriber added (total=%d)", len(self._subscribers))
        return q

    def unsubscribe(self, q: queue.Queue[MonitorEvent]) -> None:
        """Remove a subscriber queue. Called on WebSocket disconnect."""
        with self._lock:
            try:
                self._subscribers.remove(q)
            except ValueError:
                pass
        logger.info("EventBus: subscriber removed (total=%d)", len(self._subscribers))

    def get_history(self, after_id: str | None = None) -> list[dict]:
        """Return buffered events as dicts, optionally after a given event ID.

        Lifecycle events (run_start, run_end) from the separate never-evicted
        buffer are prepended so the frontend always has full run metadata even
        when per-step events have been evicted from the main ring buffer.
        """
        # Collect lifecycle events that are no longer in the main buffer
        main_ids = {e.id for e in self._buffer}
        extra_lifecycle = [
            e for e in self._lifecycle_buffer if e.id not in main_ids
        ]

        if after_id is None:
            result = [e.to_dict() for e in extra_lifecycle]
            result.extend(e.to_dict() for e in self._buffer)
            return result

        # Check if after_id is in lifecycle buffer (old run)
        found_in_lifecycle = False
        found = False
        result = []

        for e in extra_lifecycle:
            if found_in_lifecycle:
                result.append(e.to_dict())
            elif e.id == after_id:
                found_in_lifecycle = True

        # If found in lifecycle, include ALL main buffer events
        if found_in_lifecycle:
            result.extend(e.to_dict() for e in self._buffer)
            return result

        # Normal case: scan main buffer
        for e in self._buffer:
            if found:
                result.append(e.to_dict())
            elif e.id == after_id:
                found = True
        return result


# Module-level singleton
event_bus = EventBus()
