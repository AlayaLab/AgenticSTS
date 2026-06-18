# Agent Watchdog Skill Design

**Date**: 2026-03-29
**Status**: Draft
**Approach**: Claude Code Skill + `/loop` periodic execution

## Goal

Create a Claude Code skill (`agent-watchdog`) that continuously monitors the STS2 agent process, detects errors/performance degradation, applies hot-fixes to code/config/data, and manages kill/restart cycles — all within a Claude Code session via `/loop 5m /agent-watchdog`.

## Non-Goals

- Not a standalone Python daemon or systemd service
- Not a game strategy optimizer (only operational health)
- Not a replacement for the existing agent loop error handling (complements it from outside)

## Architecture

```
/loop 5m /agent-watchdog
         |
         v
+-- Phase 1: Quick Health Check --------+
| bash scripts/check_agent_health.py    |
| exit code: 0=OK, 1=ERROR,            |
|            2=HUNG, 3=DEAD             |
+----------+----------------------------+
           |
     +-----+-----+
     | exit == 0? |--yes--> Phase 2 (lightweight metrics)
     |            |--no---> Phase 3 (diagnose + act)
     +------------+

+-- Phase 2: Game Metrics Check ---------+
| Read logs/agent_stdout.log recent tail |
| Check: floor progress, HP efficiency,  |
|        LLM call success rate,          |
|        token waste rate                |
| Normal --> report "healthy", done      |
| Abnormal --> enter Phase 3             |
+----------------------------------------+

+-- Phase 3: Diagnose + Act ------------+
| 1. Read last 200 lines of logs        |
| 2. Match known error patterns         |
|    (see Error Pattern Library)        |
| 3. Decide: restart-only / fix+restart |
|            / data-cleanup+restart     |
| 4. Execute fix protocol               |
+----------------------------------------+
```

## Health Metrics (Three Layers)

### Layer 1: Process Health (existing, reuse check_agent_health.py)

| Metric | Threshold | Action |
|--------|-----------|--------|
| Process dead | PID does not exist | Restart immediately |
| Process hung | 7 min no log output | Kill + restart |
| Error burst | Last 25 lines match ERROR patterns | Enter diagnosis |

**PID file contract**: `scripts/start_agent_bg.sh` creates `logs/agent.pid` at startup (line 35: `echo $! > logs/agent.pid`). Before `kill`, the watchdog MUST validate the PID: (1) file exists, (2) `ps -p $PID` confirms process is alive, (3) process command contains `python` or `run_agent`. If validation fails, skip kill and proceed directly to restart.

### Layer 2: LLM Health (new, from agent_stdout.log)

`logs/agent_stdout.log` is plain-text stdout+stderr captured by `start_agent_bg.sh` via `nohup ... > logs/agent_stdout.log 2>&1`. Lines are Python logging format: `YYYY-MM-DD HH:MM:SS - module - LEVEL - message`. All grep patterns below match against this format.

| Metric | Abnormal Condition | Detection Command | Meaning |
|--------|--------------------|-------------------|---------|
| tool_use loss rate | 3+ consecutive in last 100 lines | `grep -c "must call the decision tool" <(tail -100 logs/agent_stdout.log)` | Proxy stripping tool_use blocks |
| Thinking waste | Consecutive "thinking disabled" followed by retry | `grep -c "thinking disabled\|Retrying without thinking" <(tail -100 logs/agent_stdout.log)` | Thinking enabled but eaten by proxy |
| Timeout rate | 3+ consecutive in last 50 lines | `grep -c "ReadTimeout\|timed out\|timeout" <(tail -50 logs/agent_stdout.log)` | API/proxy unresponsive |
| Empty response rate | 5+ consecutive in last 100 lines | `grep -c "empty content\|Empty response" <(tail -100 logs/agent_stdout.log)` | Model returning nothing |

**Hysteresis**: Layer 2 metrics require the threshold to be met in **2 consecutive polls** (10 minutes) before triggering Phase 3. A single spike is logged but not acted on, since transient proxy hiccups are normal.

### Layer 3: Game Performance (new, from JSONL run log or stdout)

Run boundaries are detected from `logs/agent_stdout.log` by matching `"=== Run .* started ==="` and `"=== Run .* ended ==="` log lines emitted by `scripts/run_agent.py`. Floor progress is extracted from `"Floor: \d+"` patterns in state log lines.

| Metric | Abnormal Condition | Detection Command | Meaning |
|--------|--------------------|-------------------|---------|
| Floor stagnation | Same floor for 20+ steps | `grep "Floor:" <(tail -200 logs/agent_stdout.log) \| awk` to check unique floor values | Stuck in state loop |
| HP crash | Single combat HP loss >60% | `grep "HP:" <(tail -100 logs/agent_stdout.log)` to track HP delta | Decision quality issue |
| Consecutive early death | 3+ runs ending below floor 10 | Scan last 3 run-end log entries for final floor | Systemic problem, possibly bad learned data |
| Mechanical fallback freq | >10 per run | `grep -c "mechanical fallback\|random fallback" <(tail -500 logs/agent_stdout.log)` between run boundaries | LLM consistently failing |
| Evolution anomaly | Broken tool/skill from evolution | `grep -c "Failed to load\|SyntaxError\|ImportError" <(tail -50 logs/agent_stdout.log)` in evolution context | Self-evolution polluting data |

**Hysteresis**: Layer 3 "HP crash" and "floor stagnation" require persistence across **2 consecutive polls**. "Consecutive early death" is inherently multi-run and does not need additional hysteresis. A single bad combat (e.g., a difficult elite) should not trigger intervention.

**Phase 2 tail size**: Phase 2 reads the last **100 lines** of `agent_stdout.log` for a lightweight scan. Phase 3 reads the last **200 lines** for deeper diagnosis.

**Decision logic**: Layer 2 anomalies are likely infrastructure (proxy/API) — prioritize config fix or restart. Layer 3 anomalies may indicate bad learned experience — consider data cleanup before restart.

## Error Pattern Library

### Infrastructure (auto-fixable)

| Pattern | Log Signature | Fix Strategy |
|---------|--------------|--------------|
| Proxy tool_use stripping | Consecutive "must call the decision tool" + retry | Toggle thinking mode in .env (STS2_THINK_MODE=off) or switch to streaming |
| API timeout storm | Consecutive "timeout" / "ReadTimeout" | Increase timeout or switch base_url in .env |
| Model unavailable | "model_not_found" / "overloaded" | Downgrade affected tier: if strategic model fails, set `STS2_STRATEGIC_MODEL` to Haiku; if fast model fails, set `STS2_FAST_MODEL` to Haiku. Analysis/evolution models (`LLM_ANALYSIS_MODEL`, `EVOLUTION_MODEL`) are post-run only — skip those fixes, just restart |
| Token exhaustion | "rate_limit" / "quota_exceeded" | Switch API key or reduce effort level |

### Game Logic (diagnose then fix)

| Pattern | Log Signature | Fix Strategy |
|---------|--------------|--------------|
| State loop stuck | Same state hash repeated 15+ times | Read loop.py `_force_unstick` logic, check for new stuck patterns |
| Action repeated failure | Same action 3+ consecutive McpError | Check actions.py param construction, or MCP API version change |
| Parse crash | StateParseError + traceback | Read upstream_models.py, check if MCP returns new fields |
| RuntimeError abort | "V2 failed" / "unstable action" | Read v2_engine.py, analyze root cause |

### Data Pollution (cleanup + restart)

| Pattern | Log Signature | Fix Strategy |
|---------|--------------|--------------|
| Consecutive early death | 3+ runs floor < 10 | Check skills/rules added in the last 3 runs (by timestamp). A "suspicious" entry is one where: (a) `created_at` falls within the decline window AND (b) `confidence < 0.3` OR `usage_count < 2`. Rollback these entries. If no clear suspects, rollback entire `skills.json` to last git-committed version |
| Bad skill propagation | New skill high confidence but run performance declining | Grep recently added skills, evaluate quality, delete if bad |
| Broken evolution tool | `data/evolution/tools/*.py` load failure | Delete tool files with syntax errors or failing test cases |
| Guide degradation | Win rate drops after guide consolidation | Rollback `data/memory/v2/guides.json` to previous git version |

### Unknown Errors (conservative)

For errors not matching known patterns:
1. Read full traceback + surrounding context
2. Attempt to understand root cause
3. If confident in fix: git stash -> modify -> verify -> commit
4. If not confident: kill + restart only, log issue for human review

## Fix Protocol

### restart-only

```
1. kill $(cat logs/agent.pid)
2. Wait 2s, confirm process dead
3. bash scripts/start_agent_bg.sh --steps 500
4. Wait 10s, quick health check
5. If startup failed: log, wait for next poll
```

### fix+restart

```
0. Pre-check: run `git status --porcelain`
   - If working tree is dirty (uncommitted changes exist):
     run `git stash push -m "watchdog-user-changes-{timestamp}"`
     to save user's work separately BEFORE the fix stash
1. git stash push -m "watchdog-pre-fix-{timestamp}"
2. Apply fix (Edit/Write on target files)
3. Quick verify (per fix category):
   - .env / config changes: `python -c "from config import *; print('OK')"`
   - data file changes (skills.json, guides.json):
     `python -c "import json; json.load(open('data/skills/skills.json')); print('OK')"`
   - Python source changes:
     `python -c "import src.agent.loop; print('OK')"` (syntax/import check)
     + pytest relevant test file if exists (max 30s timeout)
4a. Verify passes:
    - git add changed files
    - git commit -m "[watchdog] fix: {description}"
    - kill -> restart (same as restart-only)
    - If user changes were stashed in step 0: `git stash pop` to restore them
4b. Verify fails:
    - git checkout -- .
    - git stash pop (restores pre-fix state)
    - If user changes were stashed in step 0: `git stash pop` again to restore those
    - If any `git stash pop` fails (conflict): log conflict details, do NOT force resolve
    - kill -> restart only
    - Log "fix failed" for human review
```

### data-cleanup+restart

```
1. Backup current data files:
   - cp data/skills/skills.json data/skills/skills.json.bak
   - cp data/memory/v2/guides.json data/memory/v2/guides.json.bak
2. Targeted cleanup:
   - Remove suspicious skill entries (criteria: created in last 3 runs
     AND confidence < 0.3 OR usage_count < 2)
   - If no clear suspects: `git checkout HEAD -- data/skills/skills.json`
   - Rollback guides: `git checkout HEAD -- data/memory/v2/guides.json`
   - Delete broken evolution tools: `rm data/evolution/tools/<file>.py`
     for files matching SyntaxError/ImportError in recent logs
3. git commit -m "[watchdog] cleanup: {description}"
4. kill -> restart (same as restart-only)
```

## Safety Rules

### Anti-restart-storm

`logs/monitor_state.json` schema:
```json
{
  "restart_count": 5,
  "restart_timestamps": ["2026-03-29T23:00:00", "2026-03-29T23:10:00", ...],
  "last_log_size": 12345,
  "last_activity_time": "2026-03-29T23:15:00"
}
```

- `restart_timestamps` is an append-only list of ISO timestamps. The watchdog appends one entry each time it triggers a restart.
- `start_agent_bg.sh` already maintains `restart_count` and `last_activity_time`. The watchdog adds `restart_timestamps` for time-windowed analysis.
- **30-minute rolling window**: filter `restart_timestamps` to entries within `now - 30min`. If count >= 3:
  - **Stop all automatic fixes**
  - Log "restart storm detected, pausing auto-recovery"
  - Wait for human intervention

### Fix scope guardrails

- Every code modification MUST be preceded by `git stash push`
- Every fix MUST be verified (at minimum `python -c "import ..."`)
- Failed verification MUST trigger full rollback (`git checkout -- . && git stash pop`)
- Unknown errors default to restart-only (no speculative fixes)

### Data cleanup guardrails

- Always create `.bak` copies before modifying data files
- Never delete ALL skills/rules — only targeted suspicious entries
- If unsure which entries are bad, rollback entire file to last git version

## Skill File Structure

**Location**: `.claude/skills/agent-watchdog/SKILL.md`

**Sections in SKILL.md**:
1. `## Overview` — Purpose and invocation method
2. `## Execution Flow` — Phase 1/2/3 with decision tree
3. `## Health Metrics` — Three layers with bash/grep command templates per metric
4. `## Error Pattern Library` — Pattern -> fix strategy mapping tables
5. `## Fix Protocol` — git stash -> fix -> verify -> commit/revert flow
6. `## Safety Rules` — Anti-restart-storm, fix scope, data cleanup guardrails
7. `## Output Format` — Status report template for each poll

**Output format examples**:

Healthy:
```
[watchdog] 2026-03-29 23:15 | HEALTHY
  Process: alive (PID 12345, uptime 47m)
  LLM: 0 retries, 0 timeouts
  Game: floor 23, HP 65/80, run #3
```

Fix applied:
```
[watchdog] 2026-03-29 23:20 | FIX+RESTART
  Issue: proxy tool_use stripping (5 consecutive retries)
  Fix: disabled thinking in .env (STS2_THINK_MODE=off)
  Git: [watchdog] fix: disable thinking for proxy compat
  Restart: PID 12345 -> killed -> PID 12400 started
  Post-check: healthy
```

**Estimated size**: ~800-1200 lines, broken down approximately:
- Overview + Execution Flow: ~100 lines (architecture diagram, phase descriptions)
- Health Metrics: ~200 lines (3 layers, detection commands with example grep/awk, thresholds, hysteresis rules)
- Error Pattern Library: ~250 lines (4 categories, ~15 patterns, each with log signature + fix strategy + example commands)
- Fix Protocol: ~200 lines (3 protocols with step-by-step bash commands, git safety, verify commands per fix type)
- Safety Rules: ~100 lines (restart storm, fix guardrails, data cleanup guardrails)
- Output Format: ~50 lines (healthy/fix/error templates)
- Reference section: ~50 lines (file paths, env vars, links to CLAUDE.md sections)

**What is NOT in the skill**:
- No embedded Python code — all detection via Bash/Grep commands
- No project knowledge duplication — references CLAUDE.md Bugs Fixed section
- No game strategy content — purely operational monitoring

## Dependencies

- Existing: `scripts/check_agent_health.py`, `scripts/start_agent_bg.sh`, `logs/agent_stdout.log`, `logs/agent.pid`, `logs/monitor_state.json`
- `/loop` skill from Claude Code (already available)
- Git for stash/commit/revert safety net

## Enhancements for check_agent_health.py

Minor additions needed to support Layer 2/3 metrics:
- Add LLM health metrics extraction (grep patterns for tool_use loss, timeouts, empty responses)
- Add game metrics extraction (floor progress, HP tracking from recent log entries)
- Return structured JSON output (not just exit codes) so the skill can parse detailed status
- Keep backward-compatible exit codes for simple usage

## Implementation Estimate

1. Write SKILL.md (~800-1200 lines) — primary deliverable
2. Enhance check_agent_health.py with Layer 2/3 metrics + JSON output
3. Test with `/loop 5m /agent-watchdog` on a live agent session
