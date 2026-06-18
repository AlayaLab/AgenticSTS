# Agent Watchdog Skill Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create a Claude Code skill that monitors, diagnoses, hot-fixes, and restarts the STS2 agent — invoked via `/loop 5m /agent-watchdog`.

**Architecture:** A single SKILL.md file at `.claude/skills/agent-watchdog/SKILL.md` contains all monitoring logic as structured instructions for Claude Code. It calls the existing `check_agent_health.py` for Layer 1, then does Layer 2/3 checks via Bash/Grep. An enhanced `check_agent_health.py` adds `--json` output and `restart_timestamps` support for the watchdog. The `start_agent_bg.sh` script gets a minor update to write `restart_timestamps`.

**Tech Stack:** Bash, Python (check_agent_health.py enhancements only), Claude Code Skill YAML/Markdown

**Spec:** `docs/superpowers/specs/2026-03-29-agent-watchdog-skill-design.md`

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `.claude/skills/agent-watchdog/SKILL.md` | **Create** | Main skill — all monitoring instructions, error patterns, fix protocols |
| `scripts/check_agent_health.py` | **Modify** | Add `--json` flag for structured output, `restart_timestamps` support |
| `scripts/start_agent_bg.sh` | **Modify** | Write `restart_timestamps` array into monitor_state.json |
| `tests/test_check_agent_health.py` | **Create** | Unit tests for new health check features |

---

### Task 1: Enhance start_agent_bg.sh with restart_timestamps

**Files:**
- Modify: `scripts/start_agent_bg.sh:37-43`

- [ ] **Step 1: Update monitor_state.json writer to include restart_timestamps**

Replace the Python state writer (lines 38-43) to also write `restart_timestamps`:

```bash
# Write fresh state with restart_timestamps
python -c "
import json, time
from datetime import datetime
state_file = '$STATE_FILE'
# Load existing timestamps if any
old_ts = []
try:
    old = json.load(open(state_file))
    old_ts = old.get('restart_timestamps', [])
except Exception:
    pass
# Append current timestamp
old_ts.append(datetime.now().isoformat())
# Keep only last 20 entries to prevent unbounded growth
old_ts = old_ts[-20:]
state = {
    'last_log_size': 0,
    'last_activity_time': time.time(),
    'restart_count': $RESTARTS,
    'restart_timestamps': old_ts
}
with open(state_file, 'w') as f:
    json.dump(state, f, indent=2)
"
```

- [ ] **Step 2: Verify script runs without error**

Run: `cd AgenticSTS && bash -n scripts/start_agent_bg.sh`
Expected: No output (syntax OK)

- [ ] **Step 3: Commit**

```bash
git add scripts/start_agent_bg.sh
git commit -m "feat(watchdog): add restart_timestamps to monitor_state.json"
```

---

### Task 2: Enhance check_agent_health.py with --json output

**Files:**
- Modify: `scripts/check_agent_health.py`
- Create: `tests/test_check_agent_health.py`

- [ ] **Step 0: Ensure scripts/ is importable as a Python package**

Run: `touch AgenticSTS/scripts/__init__.py`

This creates an empty `__init__.py` so `from scripts.check_agent_health import ...` works in tests.

- [ ] **Step 1: Write failing tests for new JSON output mode**

Create `tests/test_check_agent_health.py`:

```python
"""Tests for check_agent_health.py --json mode and Layer 2/3 metrics."""
import json
import os
import sys
import time
import pytest
from pathlib import Path
from unittest.mock import patch

# Add project root to path
ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

from scripts.check_agent_health import (
    detect_errors,
    count_llm_issues,
    count_game_issues,
    build_json_report,
    read_state,
)


class TestDetectErrors:
    """Existing error detection (unchanged behavior)."""

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
    """Layer 2: LLM health metrics from log lines."""

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
    """Layer 3: Game performance metrics from log lines."""

    def test_counts_mechanical_fallbacks(self):
        lines = [
            "INFO - Using mechanical fallback",
            "INFO - random fallback for card",
        ] * 6
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
    """JSON report assembly."""

    def test_report_has_required_fields(self):
        report = build_json_report(
            status="HEALTHY",
            pid=12345,
            idle_secs=30.0,
            log_size_kb=100.5,
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
            status="ERROR",
            pid=999,
            idle_secs=5.0,
            log_size_kb=50.0,
            errors=["Traceback...\n  File..."],
            llm_issues={"tool_use_retries": 0, "timeouts": 0, "empty_responses": 0, "model_errors": 0},
            game_issues={"mechanical_fallbacks": 0, "evolution_errors": 0},
        )
        parsed = json.loads(report)
        assert parsed["status"] == "ERROR"
        assert len(parsed["errors"]) == 1


class TestRestartTimestamps:
    """restart_timestamps in monitor_state.json."""

    def test_read_state_handles_restart_timestamps(self, tmp_path):
        state_file = tmp_path / "monitor_state.json"
        state_file.write_text(json.dumps({
            "last_log_size": 0,
            "last_activity_time": time.time(),
            "restart_count": 2,
            "restart_timestamps": ["2026-03-29T23:00:00", "2026-03-29T23:10:00"]
        }))
        with patch("scripts.check_agent_health.STATE_FILE", state_file):
            state = read_state()
        assert len(state.get("restart_timestamps", [])) == 2

    def test_read_state_defaults_empty_timestamps(self, tmp_path):
        state_file = tmp_path / "monitor_state.json"
        state_file.write_text(json.dumps({
            "last_log_size": 0,
            "last_activity_time": time.time(),
            "restart_count": 1,
        }))
        with patch("scripts.check_agent_health.STATE_FILE", state_file):
            state = read_state()
        assert state.get("restart_timestamps", []) == []
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd AgenticSTS && python -m pytest tests/test_check_agent_health.py -v --tb=short 2>&1 | head -40`
Expected: FAIL — `count_llm_issues`, `count_game_issues`, `build_json_report` not defined

- [ ] **Step 3: Implement count_llm_issues()**

Add to `scripts/check_agent_health.py` after the `detect_errors` function (after line 129):

```python
def count_llm_issues(lines: list[str]) -> dict:
    """Layer 2: Count LLM health issues in log lines."""
    tool_use_retries = 0
    timeouts = 0
    empty_responses = 0
    model_errors = 0
    for line in lines:
        lower = line.lower()
        if "must call the decision tool" in lower:
            tool_use_retries += 1
        if any(kw in lower for kw in ("readtimeout", "timed out", "timeout")):
            # Exclude the HANG_THRESHOLD line from health check itself
            if "hung" not in lower and "idle" not in lower:
                timeouts += 1
        if any(kw in lower for kw in ("empty response", "empty content")):
            empty_responses += 1
        # Note: "model_not_found" is in IGNORE_PATTERNS (won't trigger ERROR exit)
        # but we still count it here for Layer 2 metrics
        if "model_not_found" in lower or "overloaded" in lower or "no available channel" in lower:
            model_errors += 1
    return {
        "tool_use_retries": tool_use_retries,
        "timeouts": timeouts,
        "empty_responses": empty_responses,
        "model_errors": model_errors,
    }
```

- [ ] **Step 4: Implement count_game_issues()**

Add after `count_llm_issues`:

```python
def count_game_issues(lines: list[str]) -> dict:
    """Layer 3: Count game performance issues in log lines."""
    mechanical_fallbacks = 0
    evolution_errors = 0
    for line in lines:
        lower = line.lower()
        if "mechanical fallback" in lower or "random fallback" in lower:
            mechanical_fallbacks += 1
        if any(kw in lower for kw in ("failed to load", "syntaxerror", "importerror")):
            if "evolution" in lower or "tool" in lower:
                evolution_errors += 1
    return {
        "mechanical_fallbacks": mechanical_fallbacks,
        "evolution_errors": evolution_errors,
    }
```

- [ ] **Step 5: Implement build_json_report()**

Add after `count_game_issues`:

```python
def build_json_report(
    status: str,
    pid: int | None,
    idle_secs: float,
    log_size_kb: float,
    errors: list[str],
    llm_issues: dict,
    game_issues: dict,
) -> str:
    """Build structured JSON health report."""
    from datetime import datetime
    report = {
        "timestamp": datetime.now().isoformat(),
        "status": status,
        "pid": pid,
        "idle_secs": round(idle_secs, 1),
        "log_size_kb": round(log_size_kb, 1),
        "errors": errors,
        "llm": llm_issues,
        "game": game_issues,
    }
    return json.dumps(report, indent=2)
```

- [ ] **Step 6: Add --json flag to main()**

Rewrite `main()` to support `--json`. The key change is initializing safe defaults at the top so all exit paths can produce JSON:

```python
def main():
    json_mode = "--json" in sys.argv
    state = read_state()
    pid = read_pid()
    now = time.time()

    # Safe defaults for JSON report (populated as we progress through checks)
    idle_secs = 0.0
    log_size = 0
    errors = []
    lines = []
    exit_code = 0
    status = "HEALTHY"

    def _exit(code: int, st: str):
        """Helper: print JSON or text, then exit."""
        if json_mode:
            all_lines = tail_log(500)  # larger tail for LLM/game metrics
            llm = count_llm_issues(all_lines[-100:])
            game = count_game_issues(all_lines[-500:])
            print(build_json_report(
                status=st, pid=pid, idle_secs=idle_secs,
                log_size_kb=log_size / 1024, errors=errors,
                llm_issues=llm, game_issues=game,
            ))
        write_state(state)
        sys.exit(code)

    # --- 1. Check process alive ---
    if pid is None:
        if not json_mode:
            print("STATUS: DEAD — no PID file found")
        _exit(3, "DEAD")

    if not is_process_alive(pid):
        if not json_mode:
            print(f"STATUS: DEAD — PID {pid} not found in tasklist")
        _exit(3, "DEAD")

    # --- 2. Check log activity ---
    log_size = LOG_FILE.stat().st_size if LOG_FILE.exists() else 0
    if log_size > state["last_log_size"]:
        state["last_activity_time"] = now
        state["last_log_size"] = log_size

    # --- 3. Check for errors in recent output ---
    lines = tail_log()
    errors = detect_errors(lines)
    if errors:
        if not json_mode:
            print(f"STATUS: ERROR — PID {pid} running but error detected")
            print("\n--- ERROR CONTEXT ---")
            print(errors[0])
            print("--- LAST 30 LINES ---")
            print("\n".join(lines[-30:]))
        _exit(1, "ERROR")

    # --- 4. Check for hang ---
    idle_secs = now - state["last_activity_time"]
    if idle_secs > HANG_THRESHOLD_SECS:
        if not json_mode:
            print(f"STATUS: HUNG — no new output for {idle_secs:.0f}s (PID {pid})")
            print("\n--- LAST 30 LINES ---")
            print("\n".join(lines[-30:]))
        _exit(2, "HUNG")

    # --- 5. All good ---
    if not json_mode:
        print(f"STATUS: HEALTHY — PID {pid}, idle {idle_secs:.0f}s, log {log_size/1024:.1f}KB")
        print("\n--- LAST 10 LINES ---")
        print("\n".join(lines[-10:]))
    _exit(0, "HEALTHY")
```

This replaces the entire `main()` function (lines 131-179 of the original file).

- [ ] **Step 7: Run tests to verify they pass**

Run: `cd AgenticSTS && python -m pytest tests/test_check_agent_health.py -v`
Expected: All tests PASS

- [ ] **Step 8: Manual smoke test with --json**

Run: `cd AgenticSTS && python scripts/check_agent_health.py --json 2>/dev/null; echo "exit: $?"`
Expected: JSON output with status field, exit code 0 or 3 (depending on whether agent is running)

- [ ] **Step 9: Commit**

```bash
git add scripts/check_agent_health.py tests/test_check_agent_health.py
git commit -m "feat(watchdog): add --json output, Layer 2/3 metrics to health check"
```

---

### Task 3: Write SKILL.md — Overview + Execution Flow (~100 lines)

**Files:**
- Create: `.claude/skills/agent-watchdog/SKILL.md`

- [ ] **Step 1: Create skill directory**

Run: `mkdir -p AgenticSTS/.claude/skills/agent-watchdog`

- [ ] **Step 2: Write frontmatter + Overview + Execution Flow sections**

Create `.claude/skills/agent-watchdog/SKILL.md` with:

```markdown
---
name: agent-watchdog
description: STS2 Agent continuous monitor — health checks, hot-fixes, and auto-restart. Use with /loop 5m /agent-watchdog
---

# Agent Watchdog

Continuously monitor the STS2 agent process for health, detect errors and performance degradation, apply hot-fixes, and manage kill/restart cycles.

**Invocation**: `/loop 5m /agent-watchdog`

**Working directory**: Must be the AgenticSTS project root.

## Overview

You are a watchdog monitoring an autonomous game-playing agent. Your job is operational health — NOT game strategy. Each poll cycle:

1. Check if the agent process is alive and healthy
2. Check LLM infrastructure health (proxy, API, timeouts)
3. Check game performance metrics (floor progress, HP, fallback rate)
4. If problems found: diagnose, fix if possible, restart if needed
5. Report status

**Key principle**: Be conservative. Only fix what you can verify. When unsure, restart-only and log for human review.

## Execution Flow

Every poll cycle follows this three-phase pipeline:

### Phase 1: Quick Health Check

Run the existing health check script:

```bash
cd AgenticSTS
python scripts/check_agent_health.py --json
```

Parse the JSON output. Check the `status` field:
- `HEALTHY` (exit 0) → proceed to Phase 2
- `ERROR` (exit 1) → proceed to Phase 3 (diagnose + act)
- `HUNG` (exit 2) → proceed to Phase 3 (kill + restart)
- `DEAD` (exit 3) → proceed to Phase 3 (restart only)

### Phase 2: Lightweight Metrics Scan

Only reached if Phase 1 returned HEALTHY. Parse the JSON report's `llm` and `game` sections:

**LLM Health** (from `llm` field):
- `tool_use_retries >= 3` → flag "LLM_TOOL_USE_LOSS"
- `timeouts >= 3` → flag "LLM_TIMEOUT_STORM"
- `empty_responses >= 5` → flag "LLM_EMPTY_RESPONSES"
- `model_errors >= 3` → flag "LLM_MODEL_UNAVAILABLE"

**Game Health** (from `game` field):
- `mechanical_fallbacks >= 10` → flag "GAME_LLM_FAILING"
- `evolution_errors >= 1` → flag "GAME_EVOLUTION_BROKEN"

**Hysteresis rule**: Layer 2 flags (LLM_*) require the SAME flag in **2 consecutive polls** before escalating. Track flags in a local variable across polls. A single spike is logged but not acted on.

If any flag persists for 2 polls → proceed to Phase 3.
If no flags → report HEALTHY and finish.

**Floor stagnation check** (supplement, grep from log):
```bash
tail -200 logs/agent_stdout.log | grep -oP "Floor: \d+" | sort -u | wc -l
```
If only 1 unique floor value in last 200 lines → flag "GAME_FLOOR_STUCK"

**Consecutive early death check** (supplement):
```bash
tail -2000 logs/agent_stdout.log | grep -c "=== Run .* ended ==="
```
Then for the last 3 run-end blocks, check if final floor < 10.

### Phase 3: Diagnose + Act

Read last 200 lines for deeper analysis:
```bash
tail -200 logs/agent_stdout.log
```

Match against the Error Pattern Library (see below). Then execute the appropriate fix protocol.

**Decision tree**:
1. Process DEAD or HUNG with no error pattern → **restart-only**
2. Infrastructure error pattern matched → **fix+restart** (modify .env/config)
3. Game logic error pattern matched → **fix+restart** (modify src/ code)
4. Data pollution pattern matched → **data-cleanup+restart**
5. Unknown error → **restart-only** (log for human review)
```

- [ ] **Step 3: Verify file created**

Run: `head -10 AgenticSTS/.claude/skills/agent-watchdog/SKILL.md`
Expected: Shows frontmatter + title

- [ ] **Step 4: Commit**

```bash
git add .claude/skills/agent-watchdog/SKILL.md
git commit -m "feat(watchdog): SKILL.md skeleton — overview + execution flow"
```

---

### Task 4: Write SKILL.md — Health Metrics section (~200 lines)

**Files:**
- Modify: `.claude/skills/agent-watchdog/SKILL.md`

- [ ] **Step 1: Append Health Metrics section**

Append to SKILL.md after the Execution Flow section. This section provides the concrete bash commands and thresholds for each metric layer:

```markdown
## Health Metrics

### Layer 1: Process Health

Handled by `python scripts/check_agent_health.py --json`. No additional commands needed.

Exit code mapping:
| Code | Status | Meaning |
|------|--------|---------|
| 0 | HEALTHY | Process alive, no errors, recent log activity |
| 1 | ERROR | Process alive but error patterns in recent log |
| 2 | HUNG | Process alive but no log output for 7+ minutes |
| 3 | DEAD | PID file missing or process not found |

### Layer 2: LLM Health

Parsed from the `--json` report's `llm` field. Thresholds:

| Metric | JSON Field | Threshold | Flag |
|--------|-----------|-----------|------|
| tool_use retries | `llm.tool_use_retries` | >= 3 | LLM_TOOL_USE_LOSS |
| Timeouts | `llm.timeouts` | >= 3 | LLM_TIMEOUT_STORM |
| Empty responses | `llm.empty_responses` | >= 5 | LLM_EMPTY_RESPONSES |
| Model errors | `llm.model_errors` | >= 3 | LLM_MODEL_UNAVAILABLE |

**Supplementary grep commands** (for deeper diagnosis in Phase 3):

tool_use stripping detection:
```bash
# Count consecutive "must call" retries (proxy stripping tool_use blocks)
tail -100 logs/agent_stdout.log | grep -c "must call the decision tool"
```

Thinking waste detection:
```bash
# Thinking tokens consumed but tool_use dropped by proxy
tail -100 logs/agent_stdout.log | grep -c -i "thinking disabled\|Retrying without thinking"
```

Timeout pattern:
```bash
# API/proxy timeout storm
tail -50 logs/agent_stdout.log | grep -c -i "ReadTimeout\|timed out"
```

### Layer 3: Game Performance

Parsed from the `--json` report's `game` field plus supplementary grep:

| Metric | Source | Threshold | Flag |
|--------|--------|-----------|------|
| Mechanical fallbacks | `game.mechanical_fallbacks` | >= 10 | GAME_LLM_FAILING |
| Evolution errors | `game.evolution_errors` | >= 1 | GAME_EVOLUTION_BROKEN |
| Floor stagnation | grep (see below) | 1 unique floor in 200 lines | GAME_FLOOR_STUCK |
| Consecutive early death | grep (see below) | 3+ runs < floor 10 | GAME_EARLY_DEATH |

**Floor stagnation**:
```bash
# Count unique floor values in recent output
FLOORS=$(tail -200 logs/agent_stdout.log | grep -oP "Floor: \K\d+" | sort -u | wc -l)
# If FLOORS == 1 and at least 20 step lines exist → stuck
STEPS=$(tail -200 logs/agent_stdout.log | grep -c "Step")
if [ "$FLOORS" -le 1 ] && [ "$STEPS" -ge 20 ]; then
    echo "GAME_FLOOR_STUCK"
fi
```

**Consecutive early death**:
```bash
# Extract last 3 run-end floor values
tail -3000 logs/agent_stdout.log | grep -B5 "=== Run .* ended ===" | grep -oP "Floor: \K\d+" | tail -3
# If all 3 values < 10 → GAME_EARLY_DEATH
```

### Hysteresis Tracking

Layer 2 and Layer 3 flags (except GAME_EARLY_DEATH) use 2-consecutive-polls hysteresis.

Track state between polls using a simple approach:
- After each Phase 2 scan, if a flag is set, check if the same flag was set in the PREVIOUS poll
- Use a temp file `logs/watchdog_flags.json` to persist flags between polls
- **On first run or if file is missing**, create it:
  ```bash
  if [ ! -f logs/watchdog_flags.json ]; then
      echo '{"previous_flags": [], "timestamp": null}' > logs/watchdog_flags.json
  fi
  ```
- Expected schema:
  ```json
  {"previous_flags": ["LLM_TIMEOUT_STORM"], "timestamp": "2026-03-29T23:15:00"}
  ```
- Flag escalates to Phase 3 only if present in BOTH current and previous polls
- GAME_EARLY_DEATH is inherently multi-run — no hysteresis needed
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/agent-watchdog/SKILL.md
git commit -m "feat(watchdog): SKILL.md health metrics — Layer 1/2/3 with commands"
```

---

### Task 5: Write SKILL.md — Error Pattern Library section (~250 lines)

**Files:**
- Modify: `.claude/skills/agent-watchdog/SKILL.md`

- [ ] **Step 1: Append Error Pattern Library section**

Append to SKILL.md:

```markdown
## Error Pattern Library

When Phase 3 is triggered, match the issue against these patterns to determine fix strategy.

### Infrastructure Patterns (auto-fixable via .env/config)

**Pattern: Proxy tool_use stripping**
- Log signature: 3+ occurrences of "must call the decision tool" in last 100 lines
- Root cause: Proxy (proxy.example.com) strips tool_use blocks from multi-block responses when thinking is enabled
- Fix: Edit `.env` file, set `STS2_THINK_TYPE=disabled` (or switch `ANTHROPIC_BASE_URL` if available)
- Verify: `python -c "from config import *; print('OK')"`
- Category: fix+restart

**Pattern: API timeout storm**
- Log signature: 3+ occurrences of "ReadTimeout" or "timed out" in last 50 lines
- Root cause: Proxy/API unresponsive or overloaded
- Fix: Edit `.env`, increase `STS2_MCP_TIMEOUT` to 60 (from default 30) for MCP timeouts. For LLM API timeouts, the 120s timeout is hardcoded in v2_backend.py — if persistent, switch `ANTHROPIC_BASE_URL` to alternate proxy
- Verify: `python -c "from config import *; print('OK')"`
- Category: fix+restart

**Pattern: Model unavailable**
- Log signature: "model_not_found" or "overloaded" in last 50 lines
- Root cause: Proxy doesn't have capacity for the requested model
- Fix: Identify which model tier is failing from log context:
  - If "strategic" or `STS2_STRATEGIC_MODEL` mentioned → edit `.env`: `STS2_STRATEGIC_MODEL=claude-haiku-4-5-20251001`
  - If "fast" or `STS2_FAST_MODEL` mentioned → edit `.env`: `STS2_FAST_MODEL=claude-haiku-4-5-20251001`
  - If post-run models (analysis/evolution) → don't fix, just restart (these are non-critical)
- Verify: `python -c "from config import *; print('OK')"`
- Category: fix+restart

**Pattern: Token/rate limit exhaustion**
- Log signature: "rate_limit" or "quota_exceeded" in last 50 lines
- Root cause: API key has hit its rate/quota limit
- Fix: If `STS2_OPUS_API_KEY` exists in `.env`, swap it with `ANTHROPIC_API_KEY`. Otherwise reduce thinking effort: set `STS2_THINK_EFFORT_STRATEGIC=low`
- Verify: `python -c "from config import *; print('OK')"`
- Category: fix+restart

### Game Logic Patterns (diagnose then fix src/)

**Pattern: State loop stuck**
- Log signature: "stuck" or "force_unstick" appearing 5+ times in last 200 lines, or same state_type repeated 20+ times
- Root cause: Agent hitting unhandled state transition
- Fix: Read `src/agent/loop.py` around `_force_unstick()`. Check if the stuck state_type is handled. If not, add a handler. This requires reading the actual stuck state from logs to understand what action would unstick it.
- Verify: `python -c "import src.agent.loop; print('OK')"` + `python -m pytest tests/ -k "stuck" --timeout=30 -q`
- Category: fix+restart

**Pattern: Action repeated failure**
- Log signature: Same action name + "McpError" appearing 3+ consecutive times
- Root cause: MCP API parameter mismatch or API version change
- Fix: Read the McpError message from logs. Check `src/mcp_client/actions.py` for the failing action builder. Compare parameters against current MCP API state response.
- Verify: `python -c "import src.mcp_client.actions; print('OK')"`
- Category: fix+restart

**Pattern: Parse crash**
- Log signature: "StateParseError" + Python traceback
- Root cause: MCP API returning unexpected fields or structure
- Fix: Read traceback to identify which field/model failed. Check `src/mcp_client/upstream_models.py`. Add Optional[] annotation or default value for new fields.
- Verify: `python -c "import src.mcp_client.upstream_models; print('OK')"` + `python -m pytest tests/ -k "parse or state" --timeout=30 -q`
- Category: fix+restart

**Pattern: RuntimeError abort**
- Log signature: "RuntimeError" + ("V2 failed" or "unstable action" or "aborting")
- Root cause: V2Engine decision pipeline failure
- Fix: Read the full traceback. Check `src/brain/v2_engine.py` and `src/brain/v2_backend.py`. These are often proxy-related (tool_use stripping) — check infrastructure patterns first before attempting code fix.
- Verify: `python -c "import src.brain.v2_engine; print('OK')"`
- Category: Usually restart-only (RuntimeError aborts are intentional safety stops)

### Data Pollution Patterns (cleanup + restart)

**Pattern: Consecutive early death**
- Log signature: Last 3 run-end entries show floor < 10
- Root cause: Agent may have learned bad skills/rules that degrade play quality
- Fix:
  1. Read `data/skills/skills.json`
  2. Identify entries where `created_at` is recent (within last 3 runs' timeframe) AND (`confidence < 0.3` OR `usage_count < 2`)
  3. Remove those entries
  4. If no clear suspects found: `git checkout HEAD -- data/skills/skills.json` to rollback entirely
- Verify: `python -c "import json; json.load(open('data/skills/skills.json')); print('OK')"`
- Category: data-cleanup+restart

**Pattern: Broken evolution tool**
- Log signature: "Failed to load" or "SyntaxError" or "ImportError" referencing `data/evolution/tools/`
- Root cause: Self-evolution authored a broken Python tool
- Fix:
  1. Parse the filename from the error log
  2. Delete the broken `.py` file: `rm data/evolution/tools/<filename>.py`
- Verify: `ls data/evolution/tools/` (confirm file removed)
- Category: data-cleanup+restart

**Pattern: Bad skill propagation**
- Log signature: New skills with high confidence but game performance declining (floor/HP metrics worse over last 3+ runs)
- Root cause: Skill discovery produced a harmful skill that scored high
- Fix: Same as consecutive early death — identify and remove recent high-confidence low-usage skills
- Category: data-cleanup+restart

**Pattern: Guide degradation**
- Log signature: Performance decline starting after a "Guide consolidation" log entry
- Root cause: Guide consolidation produced poor-quality guides
- Fix: `git checkout HEAD -- data/memory/v2/guides.json`
- Verify: `python -c "import json; json.load(open('data/memory/v2/guides.json')); print('OK')"`
- Category: data-cleanup+restart

### Unknown Errors

For errors not matching any pattern above:
1. Read the full traceback from the last 200 lines of logs
2. Read the source file mentioned in the traceback
3. Attempt to understand the root cause
4. **If confident** the fix is correct and limited in scope (< 10 lines changed):
   - Follow the fix+restart protocol with git safety
5. **If not confident**:
   - Do NOT attempt a code fix
   - Kill and restart only
   - Log the full error details for human review:
     ```
     [watchdog] UNKNOWN_ERROR — manual review needed
       Traceback: <first 5 lines>
       File: <source file>
       Attempted: restart-only (no fix applied)
     ```
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/agent-watchdog/SKILL.md
git commit -m "feat(watchdog): SKILL.md error pattern library — 15 patterns with fix strategies"
```

---

### Task 6: Write SKILL.md — Fix Protocol + Safety Rules sections (~300 lines)

**Files:**
- Modify: `.claude/skills/agent-watchdog/SKILL.md`

- [ ] **Step 1: Append Fix Protocol section**

Append to SKILL.md:

```markdown
## Fix Protocol

### Protocol: restart-only

Use when: process is dead/hung, or unknown error with no confident fix.

```bash
# Step 1: Validate PID before killing
PID_FILE="logs/agent.pid"
if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    # Validate: process exists AND is a python/run_agent process
    if ps -p "$PID" -o args= 2>/dev/null | grep -q "python\|run_agent"; then
        kill "$PID" 2>/dev/null || taskkill /PID "$PID" /F 2>/dev/null
        echo "[watchdog] Killed PID $PID"
    elif tasklist /FI "PID eq $PID" /NH /FO CSV 2>/dev/null | grep -q "$PID"; then
        taskkill /PID "$PID" /F 2>/dev/null
        echo "[watchdog] Killed PID $PID (Windows)"
    else
        echo "[watchdog] PID $PID not found or not our process, skipping kill"
    fi
fi

# Step 2: Wait for process to die
sleep 2

# Step 3: Restart
bash scripts/start_agent_bg.sh 500

# Step 4: Wait and verify
sleep 10
python scripts/check_agent_health.py --json
# Parse output — if status != HEALTHY, log "startup failed" and wait for next poll
```

### Protocol: fix+restart

Use when: a known error pattern is matched and the fix strategy is defined.

**Step 0: Pre-check working tree**
```bash
# Check for existing uncommitted changes
DIRTY=$(git status --porcelain)
if [ -n "$DIRTY" ]; then
    git stash push -m "watchdog-user-changes-$(date +%Y%m%d-%H%M%S)"
    echo "[watchdog] Stashed user changes"
    # Remember we stashed user changes
    USER_STASH=true
fi
```

**Step 1: Safety stash**
```bash
git stash push -m "watchdog-pre-fix-$(date +%Y%m%d-%H%M%S)"
```

**Step 2: Apply fix**
Use the Edit tool to make targeted changes based on the matched error pattern. Keep changes minimal.

**Step 3: Verify (per fix category)**

For .env / config changes:
```bash
python -c "from config import *; print('OK')"
```

For data file changes (skills.json, guides.json):
```bash
python -c "import json; json.load(open('data/skills/skills.json')); print('OK')"
python -c "import json; json.load(open('data/memory/v2/guides.json')); print('OK')"
```

For Python source changes:
```bash
python -c "import src.agent.loop; print('OK')"
# If there are relevant tests:
python -m pytest tests/ -k "relevant_test" --timeout=30 -q
```

**Step 4a: Verify PASSES**
```bash
git add <changed files>
git commit -m "[watchdog] fix: <description of what was fixed>"
# Proceed to restart-only protocol
# Restore user changes if stashed
if [ "$USER_STASH" = true ]; then
    git stash pop || echo "[watchdog] WARNING: conflict restoring user changes"
fi
```

**Step 4b: Verify FAILS**
```bash
git checkout -- .
git stash pop  # Restore pre-fix state
echo "[watchdog] Fix verification failed, reverting"
# Restore user changes if stashed
if [ "$USER_STASH" = true ]; then
    git stash pop || echo "[watchdog] WARNING: conflict restoring user changes — check git stash list"
fi
# Proceed to restart-only protocol (no code fix)
```

### Protocol: data-cleanup+restart

Use when: data pollution pattern is matched (consecutive early death, broken evolution tools, guide degradation).

```bash
# Step 1: Backup current data
cp data/skills/skills.json data/skills/skills.json.bak
cp data/memory/v2/guides.json data/memory/v2/guides.json.bak

# Step 2: Targeted cleanup based on pattern
# (See specific cleanup steps in Error Pattern Library above)

# Step 3: Commit cleanup
git add data/
git commit -m "[watchdog] cleanup: <description>"

# Step 4: Restart (same as restart-only protocol)
```

## Safety Rules

### Anti-restart-storm

**Before ANY restart action**, check for restart storms:

```bash
# Read restart_timestamps from monitor_state.json
python -c "
import json, time
from datetime import datetime, timedelta
state = json.load(open('logs/monitor_state.json'))
timestamps = state.get('restart_timestamps', [])
now = datetime.now()
cutoff = now - timedelta(minutes=30)
recent = [t for t in timestamps if datetime.fromisoformat(t) > cutoff]
print(f'RECENT_RESTARTS={len(recent)}')
if len(recent) >= 3:
    print('RESTART_STORM=true')
else:
    print('RESTART_STORM=false')
"
```

If `RESTART_STORM=true`:
- **STOP all automatic recovery**
- Output:
  ```
  [watchdog] RESTART_STORM — 3+ restarts in 30 minutes
    Recent restarts: <timestamps>
    Action: PAUSED — waiting for human intervention
    Last error: <brief description>
  ```
- Do NOT restart, do NOT fix code, do NOT modify data
- Wait for human to investigate

### Fix Scope Guardrails

1. **Every code modification** MUST be preceded by `git stash push`
2. **Every fix** MUST be verified with the appropriate verify command
3. **Failed verification** MUST trigger full rollback: `git checkout -- . && git stash pop`
4. **Unknown errors** default to restart-only — no speculative code fixes
5. **Never modify** files outside the AgenticSTS project directory
6. **Max 10 lines** changed per fix — if more is needed, restart-only and flag for human

### Data Cleanup Guardrails

1. **Always** create `.bak` copies before modifying data files
2. **Never** delete ALL skills or rules — only targeted suspicious entries
3. **Suspicious entry criteria**: `created_at` within decline window AND (`confidence < 0.3` OR `usage_count < 2`)
4. **If unsure** which entries are bad: rollback entire file with `git checkout HEAD -- <file>`
5. **Never** delete seed skills (check `source == "seed"` field)
```

- [ ] **Step 2: Commit**

```bash
git add .claude/skills/agent-watchdog/SKILL.md
git commit -m "feat(watchdog): SKILL.md fix protocols + safety rules"
```

---

### Task 7: Write SKILL.md — Output Format + Reference section (~100 lines)

**Files:**
- Modify: `.claude/skills/agent-watchdog/SKILL.md`

- [ ] **Step 1: Append Output Format and Reference sections**

Append to SKILL.md:

```markdown
## Output Format

Every poll cycle MUST end with a status report. Use these templates:

### HEALTHY

```
[watchdog] YYYY-MM-DD HH:MM | HEALTHY
  Process: alive (PID <pid>, idle <N>s)
  LLM: <retries> retries, <timeouts> timeouts, <empty> empty
  Game: floor <N>, fallbacks <N>, evolution errors <N>
```

### FIX+RESTART

```
[watchdog] YYYY-MM-DD HH:MM | FIX+RESTART
  Issue: <pattern name> (<brief evidence>)
  Fix: <what was changed>
  Git: [watchdog] fix: <commit message>
  Restart: PID <old> → killed → PID <new> started
  Post-check: <healthy|failed>
```

### DATA-CLEANUP+RESTART

```
[watchdog] YYYY-MM-DD HH:MM | DATA-CLEANUP+RESTART
  Issue: <pattern name>
  Cleanup: removed <N> suspicious skills, rollback guides
  Git: [watchdog] cleanup: <commit message>
  Restart: PID <old> → killed → PID <new> started
  Post-check: <healthy|failed>
```

### RESTART-ONLY

```
[watchdog] YYYY-MM-DD HH:MM | RESTART-ONLY
  Reason: <dead|hung|unknown error>
  Restart: PID <old> → killed → PID <new> started
  Post-check: <healthy|failed>
```

### RESTART_STORM (paused)

```
[watchdog] YYYY-MM-DD HH:MM | RESTART_STORM
  Recent restarts: <N> in last 30 minutes
  Last error: <brief description>
  Action: PAUSED — waiting for human intervention
```

### UNKNOWN_ERROR (no fix attempted)

```
[watchdog] YYYY-MM-DD HH:MM | UNKNOWN_ERROR
  Traceback: <first 3 lines>
  Source: <file:line>
  Action: restart-only (no fix applied)
  Note: manual review recommended
```

## Reference

### Key Files

| File | Purpose |
|------|---------|
| `scripts/check_agent_health.py` | Layer 1 health check (process alive, error detection, hang detection) |
| `scripts/start_agent_bg.sh` | Agent process launcher (background, PID tracking, restart count) |
| `logs/agent_stdout.log` | Agent stdout+stderr (plain text, Python logging format) |
| `logs/agent.pid` | Current agent process ID |
| `logs/monitor_state.json` | Monitor state (restart count, timestamps, log size) |
| `logs/watchdog_flags.json` | Hysteresis tracking (previous poll flags) |
| `data/skills/skills.json` | Skill library (may need cleanup on data pollution) |
| `data/memory/v2/guides.json` | Consolidated guides (may need rollback) |
| `data/evolution/tools/` | Agent-authored Python tools (may need deletion) |
| `.env` | Environment config (API keys, model names, thinking mode) |
| `config.py` | Python config (reads from .env and env vars) |

### Environment Variables (fixable by watchdog)

| Variable | Purpose | Watchdog may change |
|----------|---------|-------------------|
| `STS2_THINK_TYPE` | Thinking type (adaptive/enabled/disabled) | Yes — set to `disabled` if proxy strips tool_use |
| `STS2_STRATEGIC_MODEL` | Strategic tier model | Yes — downgrade to Haiku if unavailable |
| `STS2_FAST_MODEL` | Fast tier model | Yes — downgrade to Haiku if unavailable |
| `STS2_MCP_TIMEOUT` | MCP API call timeout (seconds, default 30) | Yes — increase if MCP timeout storms |
| `STS2_THINK_EFFORT_STRATEGIC` | Strategic tier thinking effort (default medium) | Yes — set to `low` if rate limited |
| `STS2_THINK_EFFORT_ANALYSIS` | Analysis tier thinking effort (default high) | Yes — set to `medium` if rate limited |
| `ANTHROPIC_BASE_URL` | API proxy URL | Yes — switch to alternate if available |
| `ANTHROPIC_API_KEY` / `LLM_API_KEY` | Primary API key | Yes — swap with `STS2_OPUS_API_KEY` if rate limited |
| `STS2_OPUS_API_KEY` | Secondary API key (Opus tier) | Yes — swap to primary if primary is rate limited |

### Project Documentation

For deeper context on specific bugs and fixes, refer to:
- `CLAUDE.md` → "Bugs Fixed" section for historical error patterns
- `CLAUDE.md` → "Key Technical Decisions" for architecture context
- `docs/superpowers/specs/2026-03-29-agent-watchdog-skill-design.md` for full design spec
```

- [ ] **Step 2: Verify total SKILL.md line count**

Run: `wc -l AgenticSTS/.claude/skills/agent-watchdog/SKILL.md`
Expected: ~800-1200 lines

- [ ] **Step 3: Commit**

```bash
git add .claude/skills/agent-watchdog/SKILL.md
git commit -m "feat(watchdog): SKILL.md complete — output format + reference"
```

---

### Task 8: Integration Test — Dry Run

**Files:**
- No files modified (read-only verification)

- [ ] **Step 1: Verify skill is discoverable**

Run: `ls -la AgenticSTS/.claude/skills/agent-watchdog/SKILL.md`
Expected: File exists, ~800-1200 lines

- [ ] **Step 2: Verify health check --json works**

Run: `cd AgenticSTS && python scripts/check_agent_health.py --json 2>/dev/null | python -c "import sys,json; d=json.load(sys.stdin); print(d['status'])"`
Expected: Prints one of HEALTHY/ERROR/HUNG/DEAD

- [ ] **Step 3: Verify start script syntax**

Run: `bash -n AgenticSTS/scripts/start_agent_bg.sh`
Expected: No output (syntax OK)

- [ ] **Step 4: Run all tests**

Run: `cd AgenticSTS && python -m pytest tests/test_check_agent_health.py -v --timeout=30`
Expected: All tests PASS

- [ ] **Step 5: Final commit (if any adjustments needed)**

```bash
git add -A
git commit -m "feat(watchdog): agent-watchdog skill complete — monitoring, diagnosis, hot-fix, auto-restart"
```
