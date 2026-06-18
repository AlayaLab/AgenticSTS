"""Tests for SessionLogger llm_call_seq counter (Task B4)."""

import tempfile
from pathlib import Path

from src.log.session_logger import SessionLogger


def test_llm_call_seq_starts_at_minus_one():
    """Counter should initialize to -1 before any llm_call events."""
    with tempfile.TemporaryDirectory() as td:
        sl = SessionLogger("test_run_001")
        assert sl.current_llm_call_seq() == -1
        sl.close()


def test_llm_call_seq_increments_per_llm_call_event():
    """Counter must increment exactly once per llm_call event written."""
    with tempfile.TemporaryDirectory() as td:
        sl = SessionLogger("test_run_002")

        # Writing a non-llm_call event must NOT increment
        sl._write_event("round_end", {"hp": 50})
        assert sl.current_llm_call_seq() == -1

        # First llm_call event should increment to 0
        sl._write_event("llm_call", {"prompt": "p1", "tier": "fast"})
        assert sl.current_llm_call_seq() == 0

        # Second llm_call event should increment to 1
        sl._write_event("llm_call", {"prompt": "p2", "tier": "strategic"})
        assert sl.current_llm_call_seq() == 1

        # Non-llm_call events should not increment
        sl._write_event("decision", {"action": "play_card"})
        assert sl.current_llm_call_seq() == 1

        # Third llm_call should increment to 2
        sl._write_event("llm_call", {"prompt": "p3", "tier": "analysis"})
        assert sl.current_llm_call_seq() == 2

        sl.close()
