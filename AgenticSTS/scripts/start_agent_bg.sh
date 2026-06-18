#!/bin/bash
# Start the STS2 agent in background, logging stdout+stderr to agent_stdout.log
# Usage: bash scripts/start_agent_bg.sh [--steps N]

cd "$(dirname "$0")/.." || exit 1

STEPS=${1:-1500}
LOG=logs/agent_stdout.log
PID_FILE=logs/agent.pid
STATE_FILE=logs/monitor_state.json

# Kill any existing agent process
if [ -f "$PID_FILE" ]; then
    OLD_PID=$(cat "$PID_FILE")
    if ps -p "$OLD_PID" > /dev/null 2>&1 || tasklist /FI "PID eq $OLD_PID" /NH /FO CSV 2>/dev/null | grep -q "$OLD_PID"; then
        echo "[monitor] Killing old process PID=$OLD_PID"
        kill "$OLD_PID" 2>/dev/null || taskkill /PID "$OLD_PID" /F 2>/dev/null
        sleep 2
    fi
fi

# Reset monitor state (preserve restart_count)
if [ -f "$STATE_FILE" ]; then
    RESTARTS=$(python -c "import json; d=json.load(open('$STATE_FILE')); print(d.get('restart_count',0)+1)" 2>/dev/null || echo "1")
else
    RESTARTS=0
fi

echo "[monitor] Starting agent (restart #$RESTARTS), steps=$STEPS → $LOG"
echo "--- RESTART #$RESTARTS @ $(date) ---" >> "$LOG"

# Start in background (nohup so it survives shell exit)
nohup python -m scripts.run_agent --steps "$STEPS" >> "$LOG" 2>&1 &
NEW_PID=$!
echo $NEW_PID > "$PID_FILE"

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

echo "[monitor] Agent started with PID=$NEW_PID"
