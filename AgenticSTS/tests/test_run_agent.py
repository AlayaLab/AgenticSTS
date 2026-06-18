from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock

import scripts.run_agent as run_agent


class _FakeRunState:
    run_id = "run-aborted"
    character = "Silent"
    victory = False
    final_floor = 32
    final_hp = 54
    final_max_hp = 89
    final_gold = 100
    final_score = 96
    total_actions = 17
    llm_calls = 17
    combats_won = 5
    combats_total = 6
    duration_seconds = 1.0
    start_time = 1700000000.0
    end_time = 1700000060.0
    target_ascension = None
    actual_ascension = None

    @property
    def ascension(self) -> int:
        if self.actual_ascension is not None:
            return self.actual_ascension
        if self.target_ascension is not None:
            return self.target_ascension
        return 0

    def fitness(self) -> float:
        return 95.5


class _FakeAgentLoop:
    instances: list["_FakeAgentLoop"] = []

    def __init__(self, *_args, **_kwargs) -> None:
        self._last_run_aborted = False
        self._run_completion_reason = ""
        self._run_end_reason = ""
        type(self).instances.append(self)

    def set_event_bus(self, _event_bus) -> None:
        return None

    def reset_for_new_run(self) -> None:
        return None

    async def run(self) -> _FakeRunState:
        self._last_run_aborted = True
        return _FakeRunState()


class _FakeMcpClient:
    IN_RUN_STATES = {"monster", "elite", "boss", "map", "rest_site", "event"}
    instances: list["_FakeMcpClient"] = []

    def __init__(self, event_bus=None) -> None:
        self.event_bus = event_bus
        self.get_state = AsyncMock(return_value={"state_type": "monster"})
        self.start_new_run = AsyncMock(return_value=True)
        type(self).instances.append(self)

    async def __aenter__(self) -> "_FakeMcpClient":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False


def test_main_stops_after_aborted_run(monkeypatch):
    _FakeAgentLoop.instances.clear()
    _FakeMcpClient.instances.clear()

    monkeypatch.setattr(run_agent, "setup_logging", lambda *args, **kwargs: None)
    monkeypatch.setattr(run_agent.config, "MONITOR_ENABLED", False)
    monkeypatch.setattr(run_agent.config, "MEMORY_ENABLED", False)
    monkeypatch.setattr(run_agent, "AgentLoop", _FakeAgentLoop)
    monkeypatch.setattr(run_agent, "McpClient", _FakeMcpClient)

    asyncio.run(run_agent.main(max_steps=25, max_runs=0, character="Silent", use_llm=True))

    client = _FakeMcpClient.instances[0]
    agent = _FakeAgentLoop.instances[0]

    assert agent._last_run_aborted is True
    assert client.start_new_run.await_count == 0


# ── _ensure_run_started ascension mismatch tests ─────────────────


def test_ensure_run_started_abandons_mismatched_ascension():
    """In-progress A0 run at F1 + target A5 → should abandon and call start_new_run(abandon_existing=True)."""
    client = _FakeMcpClient()
    # Simulate: in a run at A0 F1 (state_type=monster, run.ascension=0, floor=1)
    client.get_state = AsyncMock(return_value={
        "state_type": "monster",
        "run": {"ascension": 0, "floor": 1},
    })
    client.start_new_run = AsyncMock(return_value=True)
    logger = logging.getLogger("test")

    result = asyncio.run(
        run_agent._ensure_run_started(client, "Silent", logger, ascension=5)
    )

    assert result is True
    client.start_new_run.assert_awaited_once()
    call_kwargs = client.start_new_run.call_args.kwargs
    assert call_kwargs.get("abandon_existing") is True
    assert call_kwargs.get("ascension") == 5
    assert call_kwargs.get("character") == "Silent"


def test_ensure_run_started_continues_matching_ascension():
    """In-progress A5 run at F1 + target A5 → should continue without calling start_new_run."""
    client = _FakeMcpClient()
    client.get_state = AsyncMock(return_value={
        "state_type": "monster",
        "run": {"ascension": 5, "floor": 1},
    })
    client.start_new_run = AsyncMock(return_value=True)
    logger = logging.getLogger("test")

    result = asyncio.run(
        run_agent._ensure_run_started(client, "Silent", logger, ascension=5)
    )

    assert result is True
    client.start_new_run.assert_not_awaited()


def test_ensure_run_started_continues_without_ascension_arg():
    """In-progress F1 run + no ascension arg → should continue regardless of run ascension."""
    client = _FakeMcpClient()
    client.get_state = AsyncMock(return_value={
        "state_type": "monster",
        "run": {"ascension": 3, "floor": 1},
    })
    client.start_new_run = AsyncMock(return_value=True)
    logger = logging.getLogger("test")

    result = asyncio.run(
        run_agent._ensure_run_started(client, "Silent", logger, ascension=None)
    )

    assert result is True
    client.start_new_run.assert_not_awaited()


# ── Floor-based safety tests ─────────────────────────────────────


def test_ensure_run_started_abandons_floor_greater_than_one():
    """Leftover mid-run state (F>1) must be abandoned even if ascension
    matches — prevents silent contamination from a prior killed subprocess."""
    client = _FakeMcpClient()
    client.get_state = AsyncMock(return_value={
        "state_type": "monster",
        "run": {"ascension": 0, "floor": 17},
    })
    client.start_new_run = AsyncMock(return_value=True)
    logger = logging.getLogger("test")

    result = asyncio.run(
        run_agent._ensure_run_started(client, "Silent", logger, ascension=0)
    )

    assert result is True
    client.start_new_run.assert_awaited_once()
    assert client.start_new_run.call_args.kwargs.get("abandon_existing") is True


def test_ensure_run_started_floor_check_fires_without_ascension():
    """F>1 safety must trigger even when caller didn't specify ascension."""
    client = _FakeMcpClient()
    client.get_state = AsyncMock(return_value={
        "state_type": "monster",
        "run": {"ascension": 3, "floor": 5},
    })
    client.start_new_run = AsyncMock(return_value=True)
    logger = logging.getLogger("test")

    result = asyncio.run(
        run_agent._ensure_run_started(client, "Silent", logger, ascension=None)
    )

    assert result is True
    client.start_new_run.assert_awaited_once()
    assert client.start_new_run.call_args.kwargs.get("abandon_existing") is True
