"""Event knowledge lookup — event types from decompiled source."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.knowledge.parser import parse_md_table

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class EventOption:
    """A single option available within an event."""

    id: str = ""
    title: str = ""
    description: str = ""


@dataclass(frozen=True, slots=True)
class EventKnowledge:
    """Event metadata."""

    name: str
    base_type: str = ""
    # New fields from upstream JSON:
    event_id: str = ""
    act: str = ""
    options: tuple[EventOption, ...] = ()


class EventLookup:
    """O(1) event lookup by name (case-insensitive)."""

    def __init__(self, data_dir: Path) -> None:
        self._events: dict[str, EventKnowledge] = {}
        self._by_event_id: dict[str, EventKnowledge] = {}
        self._load(data_dir)

    def _load(self, data_dir: Path) -> None:
        path = data_dir / "events.md"
        if not path.exists():
            return
        for row in parse_md_table(path):
            name = row.get("Name", "")
            if not name:
                continue
            self._events[name.lower()] = EventKnowledge(
                name=name,
                base_type=row.get("BaseType", ""),
            )

        # Enrich with upstream JSON
        json_path = data_dir / "upstream" / "events.json"
        if json_path.exists():
            import json
            try:
                with open(json_path, encoding="utf-8") as f:
                    upstream = json.load(f)
            except (json.JSONDecodeError, OSError) as exc:
                logger.warning("Failed to load upstream events: %s", exc)
                return
            for entry in upstream:
                eid = entry.get("id", "")
                ename = entry.get("name", "")
                opts = tuple(
                    EventOption(
                        id=o.get("id", ""),
                        title=o.get("title", ""),
                        description=o.get("description", ""),
                    )
                    for o in (entry.get("options") or [])
                )
                key = ename.lower()
                existing = self._events.get(key)
                self._events[key] = EventKnowledge(
                    name=existing.name if existing else ename,
                    base_type=existing.base_type if existing else "",
                    event_id=eid,
                    act=entry.get("act", ""),
                    options=opts,
                )
                if eid:
                    self._by_event_id[eid.lower()] = self._events[key]
            logger.info("Enriched events with %d upstream entries", len(upstream))

    def get(self, event_name: str) -> EventKnowledge | None:
        """Lookup by event name (case-insensitive)."""
        return self._events.get(event_name.lower())

    def get_by_event_id(self, event_id: str) -> EventKnowledge | None:
        """Lookup by upstream event ID (case-insensitive)."""
        return self._by_event_id.get(event_id.lower())

    def is_ancient(self, event_name: str) -> bool:
        """Check if an event is an ancient event."""
        evt = self.get(event_name)
        return evt is not None and evt.base_type == "AncientEventModel"

    @property
    def count(self) -> int:
        return len(self._events)
