"""Verify STS2_STM_ENABLED=false suppresses Strategic Thread injection.

The mechanism: STM_ENABLED gates AgentLoop._get_short_term_ref and
_hcm_short_term. With STM disabled, those return None, so STM data never
flows into WorkingContext.short_term_hints, so format_working_context
omits the '## Strategic Thread' section.

This test locks down that behavior so Mode B's no-STM stance for baseline /
Mode A stays correct.
"""

import importlib
import os

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context


def _clear_env():
    os.environ.pop("STS2_STM_ENABLED", None)


def test_strategic_thread_renders_when_short_term_hints_present():
    """Sanity: when STM data flows through to short_term_hints, the section appears."""
    wc = WorkingContext(short_term_hints=("Foundation: frontload damage",))
    out = format_working_context(wc)
    assert "## Strategic Thread" in out
    assert "Foundation: frontload damage" in out


def test_strategic_thread_omitted_when_short_term_hints_empty():
    """When STM produces no hints (e.g. STM_ENABLED=false), section is absent."""
    wc = WorkingContext()  # all hints empty by default
    out = format_working_context(wc)
    assert "## Strategic Thread" not in out


def test_stm_enabled_default_true():
    _clear_env()
    import config as _cfg
    importlib.reload(_cfg)
    assert _cfg.STM_ENABLED is True


def test_stm_disabled_via_env():
    os.environ["STS2_STM_ENABLED"] = "false"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        assert _cfg.STM_ENABLED is False
    finally:
        _clear_env()


def test_get_short_term_ref_returns_none_when_disabled():
    """The actual gating point: AgentLoop._get_short_term_ref returns None.
    This is the contract that ensures no Strategic Thread leaks into prompts
    when STM is disabled.
    """
    os.environ["STS2_STM_ENABLED"] = "false"
    try:
        import config as _cfg
        importlib.reload(_cfg)
        # Minimal AgentLoop-shaped object that exercises _get_short_term_ref
        from src.agent.loop import AgentLoop

        # Create an empty AgentLoop instance via __new__ to skip __init__
        agent = AgentLoop.__new__(AgentLoop)
        agent._memory = type("Mem", (), {"short_term": "would-be-stm"})()
        result = agent._get_short_term_ref()
        assert result is None, (
            "STM_ENABLED=false must make _get_short_term_ref return None "
            "to prevent Strategic Thread leakage into prompts"
        )
    finally:
        _clear_env()
        # Reload config to restore default
        import config as _cfg
        importlib.reload(_cfg)
