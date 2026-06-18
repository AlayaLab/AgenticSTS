"""Test JSONL log _meta header with version provenance."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch

from src.log.session_logger import SessionLogger


def test_session_logger_writes_meta_header(tmp_path: Path, monkeypatch):
    """Fresh JSONL file should have _meta header on first write."""
    monkeypatch.setenv("STS2_GAME_VERSION", "v-test")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-test")

    # Patch config.LOG_DIR to use our temp directory
    with patch("config.LOG_DIR", str(tmp_path)):
        logger = SessionLogger(run_id="test-meta")

    # Get the actual log path from the logger
    log_path = logger.log_path

    # Ensure data is flushed to disk
    logger.close()

    lines = log_path.read_text(encoding="utf-8").splitlines()

    # First line should be _meta header
    assert len(lines) >= 2, "Expected at least 2 lines (meta + run_start)"
    assert lines[0].startswith('{"_meta"')

    meta = json.loads(lines[0])["_meta"]
    assert meta["game_version"] == "v-test"
    assert meta["mod_version"] == "m-test"
    assert meta["data_schema_version"] == 2

    # Second line should be run_start
    run_start = json.loads(lines[1])
    assert run_start["event"] == "run_start"
    assert run_start["run_id"] == "test-meta"


def test_session_logger_no_meta_on_append(tmp_path: Path, monkeypatch):
    """Appending to existing log file should NOT add duplicate _meta header.

    This simulates a case where the same log file is appended to by multiple
    logger instances (e.g., in tests that reuse file paths).
    """
    monkeypatch.setenv("STS2_GAME_VERSION", "v-test")
    monkeypatch.setenv("STS2_MOD_VERSION", "m-test")

    # Create first logger and write some events
    log_path = tmp_path / "run_persistent.jsonl"
    with patch("config.LOG_DIR", str(tmp_path)):
        logger1 = SessionLogger(run_id="persistent")
        logger1.close()

    lines_after_first = log_path.read_text(encoding="utf-8").splitlines()
    assert len(lines_after_first) >= 2, "Expected _meta + run_start"
    assert lines_after_first[0].startswith('{"_meta"')
    first_run_start_line = lines_after_first[1]

    # Manually append an event to simulate append mode behavior
    with open(log_path, "a", encoding="utf-8") as f:
        f.write('{"ts": 1234567890, "event": "test_manual", "run_id": "persistent"}\n')

    lines_after_manual = log_path.read_text(encoding="utf-8").splitlines()
    assert lines_after_manual[0].startswith('{"_meta"')  # Still there
    assert lines_after_manual[1] == first_run_start_line  # Still there
    assert json.loads(lines_after_manual[2])["event"] == "test_manual"  # Manually added

    # Now create a second logger instance with same run_id (appends to same file)
    with patch("config.LOG_DIR", str(tmp_path)):
        # File already exists and has content, so _ensure_meta should skip
        logger2 = SessionLogger(run_id="persistent")
        logger2.close()

    lines_final = log_path.read_text(encoding="utf-8").splitlines()

    # Should still have exactly one _meta header (no duplicate)
    meta_lines = [l for l in lines_final if l.startswith('{"_meta"')]
    assert len(meta_lines) == 1, f"Expected 1 _meta header, got {len(meta_lines)}"

    # Content should be preserved in order
    assert lines_final[0].startswith('{"_meta"')
    assert lines_final[1] == first_run_start_line
    assert json.loads(lines_final[2])["event"] == "test_manual"
    # Fourth line is second run_start from logger2
    assert json.loads(lines_final[3])["event"] == "run_start"
    assert json.loads(lines_final[3])["run_id"] == "persistent"
