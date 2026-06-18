"""Tests for check_agent_health.py --json mode and Layer 2/3 metrics."""
import json
import time
from pathlib import Path
from unittest.mock import patch

from scripts.check_agent_health import (
    build_json_report,
    count_game_issues,
    count_llm_issues,
    detect_errors,
    read_state,
)


class TestDetectErrors:
    def test_no_errors_in_clean_log(self):
        lines = ["2026-03-29 10:00:00 - loop - INFO - Step 42 completed"] * 30
        assert detect_errors(lines) == []

    def test_detects_traceback(self):
        lines = ["normal line"] * 20 + ["Traceback (most recent call last)"] + ["  File ..."] * 10
        assert len(detect_errors(lines)) > 0

    def test_ignores_known_transient_errors(self):
        lines = ["normal"] * 20 + ["InternalServerError: Error code: 502"] + ["normal"] * 5
        assert detect_errors(lines) == []


class TestCountLlmIssues:
    def test_counts_tool_use_retries(self):
        lines = [
            "2026-03-29 10:00:00 - v2 - WARNING - must call the decision tool",
            "2026-03-29 10:00:01 - v2 - WARNING - must call the decision tool",
            "2026-03-29 10:00:02 - v2 - WARNING - must call the decision tool",
        ]
        result = count_llm_issues(lines)
        assert result["tool_use_retries"] == 3

    def test_counts_timeouts(self):
        lines = [
            "2026-03-29 10:00:00 - v2 - ERROR - ReadTimeout after 120s",
            "2026-03-29 10:00:01 - v2 - ERROR - Request timed out",
        ]
        result = count_llm_issues(lines)
        assert result["timeouts"] == 2

    def test_counts_empty_responses(self):
        lines = [
            "2026-03-29 10:00:00 - v2 - WARNING - Empty response from API",
            "2026-03-29 10:00:01 - v2 - WARNING - empty content in response",
        ]
        result = count_llm_issues(lines)
        assert result["empty_responses"] == 2

    def test_counts_model_errors(self):
        lines = [
            "2026-03-29 10:00:00 - v2 - WARNING - model_not_found for claude-opus",
            "2026-03-29 10:00:01 - v2 - WARNING - No available channel",
        ]
        result = count_llm_issues(lines)
        assert result["model_errors"] == 2

    def test_zero_on_clean_log(self):
        lines = ["2026-03-29 10:00:00 - loop - INFO - Step done"] * 50
        result = count_llm_issues(lines)
        assert result["tool_use_retries"] == 0
        assert result["timeouts"] == 0
        assert result["empty_responses"] == 0
        assert result["model_errors"] == 0


class TestCountGameIssues:
    def test_counts_mechanical_fallbacks(self):
        lines = ["INFO - Using mechanical fallback", "INFO - random fallback for card"] * 6
        result = count_game_issues(lines)
        assert result["mechanical_fallbacks"] == 12

    def test_detects_evolution_errors(self):
        lines = [
            "ERROR - Failed to load tool: data/evolution/tools/foo.py",
            "ERROR - SyntaxError in tool bar.py",
        ]
        result = count_game_issues(lines)
        assert result["evolution_errors"] == 2

    def test_zero_on_clean_log(self):
        lines = ["INFO - Step completed"] * 50
        result = count_game_issues(lines)
        assert result["mechanical_fallbacks"] == 0
        assert result["evolution_errors"] == 0


class TestBuildJsonReport:
    def test_report_has_required_fields(self):
        report = build_json_report(
            status="HEALTHY", pid=12345, idle_secs=30.0, log_size_kb=100.5,
            errors=[],
            llm_issues={"tool_use_retries": 0, "timeouts": 0, "empty_responses": 0, "model_errors": 0},
            game_issues={"mechanical_fallbacks": 0, "evolution_errors": 0},
        )
        parsed = json.loads(report)
        assert parsed["status"] == "HEALTHY"
        assert parsed["pid"] == 12345
        assert "llm" in parsed
        assert "game" in parsed
        assert "timestamp" in parsed

    def test_report_includes_error_context(self):
        report = build_json_report(
            status="ERROR", pid=999, idle_secs=5.0, log_size_kb=50.0,
            errors=["Traceback...\n  File..."],
            llm_issues={"tool_use_retries": 0, "timeouts": 0, "empty_responses": 0, "model_errors": 0},
            game_issues={"mechanical_fallbacks": 0, "evolution_errors": 0},
        )
        parsed = json.loads(report)
        assert parsed["status"] == "ERROR"
        assert len(parsed["errors"]) == 1


class TestRestartTimestamps:
    def test_read_state_handles_restart_timestamps(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "monitor_state.json"
            state_file.write_text(json.dumps({
                "last_log_size": 0, "last_activity_time": time.time(),
                "restart_count": 2,
                "restart_timestamps": ["2026-03-29T23:00:00", "2026-03-29T23:10:00"]
            }))
            with patch("scripts.check_agent_health.STATE_FILE", state_file):
                state = read_state()
        assert len(state.get("restart_timestamps", [])) == 2

    def test_read_state_defaults_empty_timestamps(self):
        import tempfile
        with tempfile.TemporaryDirectory() as td:
            state_file = Path(td) / "monitor_state.json"
            state_file.write_text(json.dumps({
                "last_log_size": 0, "last_activity_time": time.time(),
                "restart_count": 1,
            }))
            with patch("scripts.check_agent_health.STATE_FILE", state_file):
                state = read_state()
        assert state.get("restart_timestamps", []) == []
