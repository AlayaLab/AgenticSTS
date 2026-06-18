from __future__ import annotations

from copy import deepcopy

import pytest

from src.mcp_client.sse_client import (
    SseEvent,
    _decode_sse_event,
    wait_for_play_phase_sse,
    wait_for_state_change_sse,
)
from tests.test_upstream_state_parser import _sample_upstream_state


class FakeEventStream:
    def __init__(self, events: list[SseEvent]) -> None:
        self._events = events

    async def __aiter__(self):
        for event in self._events:
            yield event


def _map_state() -> dict:
    state = deepcopy(_sample_upstream_state())
    state["screen"] = "MAP"
    state["in_combat"] = False
    state["turn"] = None
    state["available_actions"] = ["choose_map_node"]
    state["combat"] = None
    state["map"] = {
        "current_node": {"row": 5, "col": 2},
        "available_nodes": [
            {
                "index": 0,
                "row": 6,
                "col": 1,
                "node_type": "Monster",
                "state": "UNREACHED",
            }
        ],
    }
    state["agent_view"] = None
    return state


def _combat_enemy_turn_state() -> dict:
    state = deepcopy(_sample_upstream_state())
    state["available_actions"] = []
    return state


def _combat_play_phase_state() -> dict:
    return deepcopy(_sample_upstream_state())


def test_decode_sse_event_unwraps_upstream_envelope():
    event = _decode_sse_event(
        "screen_changed",
        [
            (
                '{"event_id":42,"type":"screen_changed","timestamp_utc":"2026-03-19T00:00:00Z",'
                '"data":{"from":"COMBAT","to":"MAP","run_id":"seed_123"}}'
            )
        ],
        "42",
    )

    assert event is not None
    assert event.name == "screen_changed"
    assert event.event_id == "42"
    assert event.data == {"from": "COMBAT", "to": "MAP", "run_id": "seed_123"}


@pytest.mark.asyncio
async def test_wait_for_state_change_sse_fetches_state_after_summary_event():
    states = [_combat_play_phase_state(), _map_state()]
    calls = 0

    async def fetch_state() -> dict:
        nonlocal calls
        calls += 1
        return states.pop(0)

    stream = FakeEventStream([
        SseEvent(name="screen_changed", data={"from": "COMBAT", "to": "MAP"}),
    ])

    result = await wait_for_state_change_sse(
        stream,
        fetch_state,
        prev_state_type="monster",
        timeout=0.1,
    )

    assert result is not None
    assert result["screen"] == "MAP"
    assert calls == 2


@pytest.mark.asyncio
async def test_wait_for_play_phase_sse_fetches_state_after_action_window_event():
    states = [_combat_enemy_turn_state(), _combat_play_phase_state()]
    calls = 0

    async def fetch_state() -> dict:
        nonlocal calls
        calls += 1
        return states.pop(0)

    stream = FakeEventStream([
        SseEvent(
            name="player_action_window_opened",
            data={"screen": "COMBAT", "actions": ["play_card", "end_turn"]},
        ),
    ])

    result = await wait_for_play_phase_sse(
        stream,
        fetch_state,
        timeout=0.1,
    )

    assert result is not None
    assert result["screen"] == "COMBAT"
    assert result["available_actions"] == ["play_card", "use_potion", "end_turn"]
    assert calls == 2
