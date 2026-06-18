"""Real-time monitoring dashboard for STS2 agent.

Provides EventBus (thread-safe broadcast) and FastAPI WebSocket server
for streaming agent events to a browser-based timeline UI.
"""

from src.monitor.event_bus import EventBus, MonitorEvent, event_bus

__all__ = ["EventBus", "EventSummarizer", "MonitorEvent", "event_bus"]


def __getattr__(name: str) -> object:
    """Lazy import EventSummarizer to avoid heavy imports at module load."""
    if name == "EventSummarizer":
        from src.monitor.summarizer import EventSummarizer

        return EventSummarizer
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
