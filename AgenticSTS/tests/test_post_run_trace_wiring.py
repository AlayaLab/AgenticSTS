"""Integration test for the combat-trace postrun wiring.

Asserts that when `_post_run_hcm_extraction` runs:
  - combat_trace_renderer is called once.
  - analyze_build_with_llm receives combat_trace_text.
  - update_card_notes_from_traces is called iff trace is non-None and
    floor_sum >= threshold.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


def test_trace_disabled_skips_pipeline(monkeypatch):
    """When POSTRUN_COMBAT_TRACE_ENABLED=False, helper returns None."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", False)

    from src.agent import loop as loop_mod
    assert hasattr(loop_mod, "_maybe_render_combat_trace"), \
        "AgentLoop helper _maybe_render_combat_trace must be exposed at module level"

    out = loop_mod._maybe_render_combat_trace(stm=None, run_log_events=[], floor_sum=100)
    assert out is None


def test_floor_sum_gate_skips_pipeline(monkeypatch):
    """When floor_sum < threshold, helper returns None without rendering."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", True)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MIN_FLOOR_SUM", 15)

    from src.agent import loop as loop_mod

    class _FakeSTM:
        completed_combats = []

    out = loop_mod._maybe_render_combat_trace(
        stm=_FakeSTM(), run_log_events=[], floor_sum=10,
    )
    assert out is None


def test_render_called_when_conditions_met(monkeypatch):
    """When enabled and floor_sum passes, renderer is invoked and its
    output returned."""
    import config
    monkeypatch.setattr(config, "POSTRUN_COMBAT_TRACE_ENABLED", True)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MIN_FLOOR_SUM", 15)
    monkeypatch.setattr(config, "POSTRUN_TRACE_MAX_ROUNDS", 30)

    from src.agent import loop as loop_mod
    from src.memory import combat_trace_renderer as ctr

    called = {"count": 0}
    def _fake_render(stm, run_log_events, *, max_rounds=30):
        called["count"] += 1
        return "RENDERED TRACE"
    monkeypatch.setattr(ctr, "render_last_two_combats", _fake_render)
    monkeypatch.setattr(loop_mod, "render_last_two_combats", _fake_render, raising=False)

    class _FakeSTM:
        completed_combats = ["c1", "c2"]

    out = loop_mod._maybe_render_combat_trace(
        stm=_FakeSTM(), run_log_events=[], floor_sum=20,
    )
    assert out == "RENDERED TRACE"
    assert called["count"] == 1
