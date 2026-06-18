"""Tests for postrun stage 5 (Mode B stub fill) wiring in AgentLoop."""

import importlib
import json
import os
from pathlib import Path

import pytest

from src.agent.loop import AgentLoop


def _clear_env():
    for k in ("STS2_SEED_STUB_FILL_ENABLED", "STS2_USE_SEED_STUBS"):
        os.environ.pop(k, None)


def _empty_agent() -> AgentLoop:
    """Build an AgentLoop instance via __new__ (skips __init__) for unit testing."""
    return AgentLoop.__new__(AgentLoop)


def test_post_run_fill_stubs_method_exists():
    """AgentLoop must expose _post_run_fill_stubs (Mode B stage 5 entry point)."""
    assert hasattr(AgentLoop, "_post_run_fill_stubs")


def test_post_run_fill_stubs_is_async():
    """Stage 5 runs in the same async pipeline as other postrun stages."""
    import inspect
    assert inspect.iscoroutinefunction(AgentLoop._post_run_fill_stubs)


@pytest.mark.asyncio
async def test_post_run_fill_stubs_no_op_when_disabled():
    """SEED_STUB_FILL_ENABLED=false must short-circuit immediately."""
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.SEED_STUB_FILL_ENABLED is False

    agent = _empty_agent()
    # Method should not raise even with all attributes missing — early return.
    await agent._post_run_fill_stubs()


@pytest.mark.asyncio
async def test_post_run_fill_stubs_no_op_when_no_skill_library():
    """Even with flag enabled, missing skill library means nothing to fill."""
    os.environ["STS2_SEED_STUB_FILL_ENABLED"] = "true"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        agent = _empty_agent()
        agent._skill_library = None
        agent._run_state = None
        # Returns cleanly without raising
        await agent._post_run_fill_stubs()
    finally:
        _clear_env()
        import config as _cfg
        importlib.reload(_cfg)


def test_write_stub_fill_log_method_exists():
    """The audit log helper must exist."""
    assert hasattr(AgentLoop, "_write_stub_fill_log")


def test_write_stub_fill_log_appends_jsonl(tmp_path, monkeypatch):
    """_write_stub_fill_log appends a JSON line to the configured log path."""
    log_file = tmp_path / "stub_fill_log.jsonl"
    import config as _cfg
    monkeypatch.setattr(_cfg, "SEED_STUB_FILL_LOG", str(log_file))

    agent = _empty_agent()
    agent._write_stub_fill_log(
        run_id="r1",
        character="the silent",
        summary={
            "filled_count": 3,
            "skipped_count": 2,
            "warnings_by_stub": {"stub_the_silent_combat": ["voice_check: 3/5 ..."]},
        },
    )
    assert log_file.exists()
    line = log_file.read_text(encoding="utf-8").strip()
    assert line, "log line was empty"
    entry = json.loads(line)
    assert entry["run_id"] == "r1"
    assert entry["character"] == "the silent"
    assert entry["filled_count"] == 3
    assert entry["skipped_count"] == 2
    assert "warnings_by_stub" in entry
    assert "timestamp" in entry


def test_post_run_fill_stubs_wired_into_safe_post_run():
    """_safe_post_run must call _post_run_fill_stubs (between skill stage and evolution)."""
    import inspect
    src = inspect.getsource(AgentLoop._safe_post_run)
    assert "_post_run_fill_stubs" in src, (
        "_safe_post_run must invoke _post_run_fill_stubs between skill-update "
        "(stage 4) and evolution (stage 6)"
    )
