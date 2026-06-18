"""Tests for STS2_STM_ENABLED=false bypass of STM reads in AgentLoop."""
from __future__ import annotations

import importlib
import os
from contextlib import contextmanager
from unittest.mock import MagicMock

from tests.conftest import make_loop


@contextmanager
def _stm_enabled(value: bool):
    original = os.environ.get("STS2_STM_ENABLED")
    os.environ["STS2_STM_ENABLED"] = "true" if value else "false"
    try:
        import config
        importlib.reload(config)
        yield
    finally:
        if original is None:
            os.environ.pop("STS2_STM_ENABLED", None)
        else:
            os.environ["STS2_STM_ENABLED"] = original
        import config
        importlib.reload(config)


def test_stm_disabled_get_short_term_ref_returns_none():
    with _stm_enabled(False):
        loop = make_loop(MagicMock())
        # Manually inject a mock _memory with short_term attribute
        # to test that the gate forces None regardless
        mock_stm = MagicMock()
        mock_memory = MagicMock()
        mock_memory.short_term = mock_stm
        loop._memory = mock_memory

        # Even if STM exists, the gated accessor returns None when STM_ENABLED=False
        assert loop._get_short_term_ref() is None
        assert loop._hcm_short_term() is None


def test_stm_enabled_get_short_term_ref_returns_object():
    with _stm_enabled(True):
        loop = make_loop(MagicMock())
        # Manually inject a mock _memory with short_term attribute
        mock_stm = MagicMock()
        mock_memory = MagicMock()
        mock_memory.short_term = mock_stm
        loop._memory = mock_memory

        # When enabled, accessor returns the STM object
        assert loop._get_short_term_ref() is mock_stm
        assert loop._hcm_short_term() is mock_stm
