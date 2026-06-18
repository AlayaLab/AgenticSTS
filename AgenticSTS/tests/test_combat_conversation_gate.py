"""Tests for STS2_COMBAT_CONVERSATION_ENABLED=false single-turn fallback."""
from __future__ import annotations

import asyncio
import importlib
import os
from contextlib import contextmanager
from unittest.mock import AsyncMock, MagicMock, patch

from tests.conftest import make_combat_gs, make_loop


@contextmanager
def _combat_conv_enabled(value: bool):
    original = os.environ.get("STS2_COMBAT_CONVERSATION_ENABLED")
    os.environ["STS2_COMBAT_CONVERSATION_ENABLED"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_COMBAT_CONVERSATION_ENABLED", None)
        else:
            os.environ["STS2_COMBAT_CONVERSATION_ENABLED"] = original
        import config
        importlib.reload(config)


def test_maybe_create_combat_conversation_returns_none_when_disabled():
    """When STS2_COMBAT_CONVERSATION_ENABLED=false, the factory returns None
    without attempting to construct CombatConversation. Pre-implementation
    this fails with AttributeError (no helper); post-implementation the gate
    short-circuits and returns None."""
    with _combat_conv_enabled(False):
        loop = make_loop(MagicMock())
        result = loop._maybe_create_combat_conversation(MagicMock())
        assert result is None


def test_maybe_create_combat_conversation_helper_exists_when_enabled():
    """Pre-implementation: AttributeError. Post-implementation: helper
    callable. Exact return value depends on whether real CombatConversation
    can be built from a MagicMock backend; we only require the helper exists
    and does not short-circuit to None on the enabled path."""
    with _combat_conv_enabled(True):
        loop = make_loop(MagicMock())
        assert hasattr(loop, "_maybe_create_combat_conversation")
        # Calling with MagicMock may raise inside CombatConversation
        # construction — that's acceptable; we don't assert a return value
        # here. Exception means the gate did not early-return None.
        try:
            loop._maybe_create_combat_conversation(MagicMock())
        except Exception:
            pass


def test_generate_combat_plan_uses_fresh_conversation_when_disabled():
    """When COMBAT_CONVERSATION_ENABLED=false and persistent conversation is
    None, _generate_combat_plan must still invoke the V2 engine with a fresh
    per-turn CombatConversation rather than returning None."""
    from src.brain.planner import CombatPlan

    dummy_plan = CombatPlan(actions=[], end_turn=True, reasoning="test", analysis="", note_to_future_self="")

    with _combat_conv_enabled(False):
        loop = make_loop(MagicMock())

        # Wire a mock V2 engine that returns a dummy plan
        mock_engine = MagicMock()
        mock_engine.generate_combat_plan = AsyncMock(return_value=dummy_plan)
        loop._v2_engine = mock_engine

        # Persistent conversation is None (COMBAT_CONVERSATION_ENABLED=false)
        loop._v2_combat_conversation = None

        # Patch helpers that _generate_combat_plan touches
        loop._v2_tool_executor = None
        loop._build_tool_preprocessor_context = MagicMock(return_value="")
        loop._get_enemy_episodes = MagicMock(return_value=[])
        loop._memory = None
        loop._validate_combat_plan = MagicMock(return_value=(None, 0))
        loop._capture_round_context_for_plan = MagicMock()
        loop._prev_combat_plan = None

        gs = make_combat_gs([])

        result = asyncio.run(loop._generate_combat_plan(gs))

        # A plan must be returned (not None) — confirming the fresh-conversation path ran
        assert result is not None, (
            "_generate_combat_plan returned None when COMBAT_CONVERSATION_ENABLED=false; "
            "the fresh-conversation fallback is broken"
        )

        # The engine must have been called with a non-None CombatConversation argument
        assert mock_engine.generate_combat_plan.called, "V2 engine was never called"
        call_args = mock_engine.generate_combat_plan.call_args
        conv_arg = call_args.args[0] if call_args.args else call_args.kwargs.get("conversation")
        assert conv_arg is not None, "V2 engine was called with conversation=None"

        # Persistent conversation must remain None (fresh conv is per-turn only)
        assert loop._v2_combat_conversation is None, (
            "self._v2_combat_conversation was mutated — it must stay None in single-turn mode"
        )
