"""Tests for first-encounter bypass in event guide consolidation."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.memory.event_models import EventMemory


def _event_memory(*, run_id, event_id, character, floor=5):
    """Minimal EventMemory — most fields default to safe values."""
    return EventMemory(
        memory_id=f"em-{event_id}-{run_id}",
        run_id=run_id,
        character=character,
        event_id=event_id,
        floor=floor,
        act=1,
    )


def _make_mm(event_store, guide_store):
    """Build a minimal memory_manager-shaped object for consolidate_event_guides."""
    mm = MagicMock()
    mm.event_store = event_store
    mm.guide_store = guide_store
    return mm


def test_event_first_encounter_bypass_triggers_llm_when_existing_is_none():
    """1 event memory + no existing guide → LLM call fires."""
    from src.memory.event_guide_consolidator import consolidate_event_guides

    event_store = MagicMock()
    event_store.get_all = MagicMock(return_value=[
        _event_memory(run_id="r1", event_id="EVT_A", character="Silent"),
    ])

    guide_store = MagicMock()
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_event_guide = MagicMock()

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch(
        "src.memory.event_guide_consolidator.parse_event_guide_response",
        return_value=None,  # parse returns None → no set, but LLM still called
    ):
        asyncio.run(consolidate_event_guides(
            _make_mm(event_store, guide_store),
            current_run_id="r1",
            min_episodes=2,
            llm_call_raw=fake_llm,
        ))

    fake_llm.assert_awaited_once()


def test_event_no_bypass_when_existing_guide_present():
    """1 event memory + existing guide → falls back to min_episodes=2 → skipped."""
    from src.memory.event_guide_consolidator import consolidate_event_guides

    event_store = MagicMock()
    event_store.get_all = MagicMock(return_value=[
        _event_memory(run_id="r1", event_id="EVT_A", character="Silent"),
    ])

    existing = MagicMock()
    guide_store = MagicMock()
    guide_store.get_event_guide = MagicMock(return_value=existing)
    guide_store.set_event_guide = MagicMock()

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    asyncio.run(consolidate_event_guides(
        _make_mm(event_store, guide_store),
        current_run_id="r1",
        min_episodes=2,
        llm_call_raw=fake_llm,
    ))

    fake_llm.assert_not_awaited()
