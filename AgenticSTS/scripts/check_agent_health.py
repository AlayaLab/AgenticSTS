"""
STS2 Agent health monitor.
Checks if the background agent process is alive, detecting errors and hangs.
Exit codes: 0=healthy, 1=error_detected, 2=hung, 3=process_dead
"""
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).parent.parent
LOG_FILE = ROOT / "logs" / "agent_stdout.log"
PID_FILE = ROOT / "logs" / "agent.pid"
STATE_FILE = ROOT / "logs" / "monitor_state.json"

HANG_THRESHOLD_SECS = 420   # 7 minutes without new output = hung (non-streaming fallback can take 5+ min)
TAIL_LINES = 120             # lines to scan for errors

ERROR_PATTERNS = [
    "Traceback (most recent call last)",
    "Error:",
    "Exception:",
    "KeyboardInterrupt",
    "SystemExit",
    "AssertionError",
    "JSONDecodeError",
    "ConnectionError",
    "TimeoutError",
    "RecursionError",
    # Only match CRITICAL as a log-level prefix (e.g. "CRITICAL     msg   module.py:N")
    # NOT the word "CRITICAL" appearing in LLM reasoning text
]
CRITICAL_LOG_RE = re.compile(r"CRITICAL\s+\S.*\w+\.py:\d+")

IGNORE_PATTERNS = [
    # These appear in normal log lines that contain "Error" as part of data
    '"level": "ERROR"',        # structured log field — we handle separately
    # Transient proxy/network errors that the agent handles by aborting the run
    # Note: box-wrapping in logs can split "Error code: 503" across lines,
    # so we match both the full string and the prefix without the status code.
    "InternalServerError: Error code: 502",
    "InternalServerError: Error code: 503",
    "InternalServerError: Error code: 529",
    "InternalServerError: Error code:",  # catches box-wrapped splits
    "V2Backend API error:",              # caught+logged by our code, not a crash
    "Upstream request failed",
    "model_not_found",          # proxy capacity issue for Opus, SDK retries automatically
    "No available channel",     # same proxy capacity issue
    # Normal abort-on-LLM-failure behavior (not a code bug)
    "aborting to prevent random play",
    "Batch submission failed",
    # Anthropic SDK streaming quirk with proxy (malformed content_block_delta)
    # Agent catches this and falls back to non-streaming automatically
    "IndexError: list index out of range",
]

# Only flag errors if they appear in the last N lines (agent hasn't recovered)
ERROR_RECENT_LINES = 25

def read_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text())
        except Exception:
            pass
    return {"last_log_size": 0, "last_activity_time": time.time(), "restart_count": 0}

def write_state(state: dict):
    STATE_FILE.write_text(json.dumps(state, indent=2))

def read_pid() -> int | None:
    if not PID_FILE.exists():
        return None
    try:
        return int(PID_FILE.read_text().strip())
    except Exception:
        return None

def is_process_alive(pid: int) -> bool:
    """Check if PID is still running (works in Git Bash on Windows)."""
    import subprocess
    # Try ps first (Git Bash / Unix)
    try:
        result = subprocess.run(
            ["ps", "-p", str(pid)],
            capture_output=True, text=True, timeout=5
        )
        if result.returncode == 0:
            return True
    except Exception:
        pass
    # Fallback: tasklist (native Windows)
    try:
        result = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/NH"],
            capture_output=True, text=True, timeout=5, shell=True
        )
        return str(pid) in result.stdout
    except Exception:
        pass
    return False

def tail_log(n: int = TAIL_LINES) -> list[str]:
    if not LOG_FILE.exists():
        return []
    try:
        lines = LOG_FILE.read_text(encoding="utf-8", errors="replace").splitlines()
        return lines[-n:]
    except Exception:
        return []

def detect_errors(lines: list[str]) -> list[str]:
    # Only scan the most recent lines — if the agent recovered, old errors are irrelevant
    recent = lines[-ERROR_RECENT_LINES:]
    errors = []
    for i, line in enumerate(recent):
        # Skip lines that match ignore patterns
        if any(ig in line for ig in IGNORE_PATTERNS):
            continue
        if any(pat in line for pat in ERROR_PATTERNS) or CRITICAL_LOG_RE.search(line):
            # Grab context (up to 15 lines around the error)
            start = max(0, i - 2)
            end = min(len(recent), i + 15)
            errors.append("\n".join(recent[start:end]))
            break  # report first error block only
    return errors

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
            if "hung" not in lower and "idle" not in lower:
                timeouts += 1
        if any(kw in lower for kw in ("empty response", "empty content")):
            empty_responses += 1
        if "model_not_found" in lower or "overloaded" in lower or "no available channel" in lower:
            model_errors += 1
    return {
        "tool_use_retries": tool_use_retries,
        "timeouts": timeouts,
        "empty_responses": empty_responses,
        "model_errors": model_errors,
    }


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


def main():
    json_mode = "--json" in sys.argv
    state = read_state()
    pid = read_pid()
    now = time.time()

    # Safe defaults for JSON report
    idle_secs = 0.0
    log_size = 0
    errors = []
    lines = []

    def _exit(code: int, st: str):
        """Helper: print JSON or text, then exit."""
        if json_mode:
            all_lines = tail_log(500)
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

if __name__ == "__main__":
    main()
