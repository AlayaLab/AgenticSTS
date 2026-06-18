# STS2 Agent Monitor Dashboard — Design Spec

**Date**: 2026-03-20
**Status**: Final (rev 3)
**Goal**: Real-time monitoring dashboard showing all LLM interactions and game actions in a chat-style timeline.

## Architecture

```
Agent Process (asyncio)
├── SessionLogger._write_event()  ──push──→  EventBus  ──broadcast──→  WS clients
├── LLMReasoner._call_llm_sync()  ──push──→  EventBus  (from worker thread)
├── MCPClient.post_action()       ──push──→  EventBus  (from main thread)
└── FastAPI Server (daemon thread, uvicorn)
    ├── GET  /api/status
    ├── GET  /api/events/history?after_id=X
    └── WS   /ws/events
```

**Key principle**: SessionLogger is the canonical record builder. EventBus is wired into `_write_event()` as a second sink. No parallel event normalization.

## EventBus (Thread-Safe Broadcast)

Per-subscriber model — each WebSocket client gets its own queue:

```python
class EventBus:
    _subscribers: list[queue.Queue]  # one per WS client
    _lock: threading.Lock
    _buffer: deque  # ring buffer for reconnect

    def emit(type, data, step=None):
        """Thread-safe. Pushes to ALL subscriber queues. Never blocks."""
        event = MonitorEvent(...)
        self._buffer.append(event)
        with self._lock:
            for q in self._subscribers:
                try: q.put_nowait(event)
                except queue.Full: pass  # drop for slow client

    def subscribe() -> queue.Queue:
        """Called by each WS handler. Returns dedicated queue."""

    def unsubscribe(q):
        """Called on WS disconnect. Removes queue."""
```

## Event Types

| Type | Source | Emitted From |
|------|--------|-------------|
| `state` | SessionLogger.log_state() | loop.py (existing call, auto-forwarded via _write_event) |
| `llm_call` | SessionLogger.log_llm_call() | reasoner.py _call_llm_sync / _call_plan_sync (NEW: wire up existing method) |
| `decision` | SessionLogger.log_decision() | loop.py (existing call, auto-forwarded) |
| `transition` | SessionLogger.log_transition() | loop.py (existing call, auto-forwarded) |
| `error` | SessionLogger.log_error() | loop.py (existing call, auto-forwarded) |
| `run_start` / `run_end` | SessionLogger constructor / log_run_end() | auto-forwarded |
| `game_action` | EventBus.emit() directly | client.py post_action() ONLY (single source) |
| `combat_plan` | EventBus.emit() directly | loop.py after plan_combat_turn() returns |
| `context_assembly` | EventBus.emit() directly | loop.py after _build_decision_context() |

### Enriched `llm_call` payload

Extend `SessionLogger.log_llm_call()` to include:
- model, tier, call_type (threaded through from callers)
- system_prompt (full), user_prompt (full) — NO truncation in transport
- raw_text (full response), reasoning, thinking_text
- latency_ms, tokens_used, cache_read_tokens, stop_reason
- attempt (1=first try, 2=no-think retry) — captures internal retries

### State snapshot deduplication

Emit state only when payload actually differs from last:
- Serialize the full `log_state()` payload dict → JSON string → hash
- Only forward to EventBus if hash changed
- Force-emit on transitions

## Instrumentation Changes

### SessionLogger (modify existing)

```python
class SessionLogger:
    def __init__(self, run_id, event_bus=None):
        self._event_bus = event_bus  # NEW: optional EventBus ref
        self._lock = threading.Lock()  # NEW: thread safety
        self._last_state_hash = None  # NEW: dedup

    def _write_event(self, event_type, data):
        with self._lock:  # thread-safe for LLM worker threads
            # Existing: write to JSONL
            record = {"ts": ..., "event": event_type, ...}
            self._file.write(json.dumps(record) + "\n")
            # NEW: push to EventBus
            if self._event_bus:
                self._event_bus.emit(event_type, data)

    def log_state(self, gs, step):  # Add dedup
        data = ... # existing payload build
        h = hash(json.dumps(data, sort_keys=True))
        if h == self._last_state_hash:
            return  # skip duplicate
        self._last_state_hash = h
        self._write_event("state", data)

    def log_llm_call(self, ...):  # Enrich existing method
        # Add: model, tier, call_type, thinking_text, cache_read, attempt, stop_reason
```

### LLMReasoner (modify existing, ~25 lines)

In `_call_llm_sync()` and `_call_plan_sync()` — the actual backend boundary:

```python
def _call_llm_sync(self, prompt, think, model, think_budget, tools, tool_choice,
                   call_type="decision"):  # NEW param
    # Before backend.call:
    # (nothing — no pre-emit, we log after to capture result)

    raw_text, latency, tokens = self._backend.call(...)

    # After backend.call — emit from worker thread:
    if self._session_logger:
        self._session_logger.log_llm_call(
            prompt=prompt, response=raw_text,
            latency_ms=latency, tokens=tokens,
            call_type=call_type, model=model,
            attempt=1, ...
        )

    # If retry (think→no-think):
    raw2, lat2, tok2 = self._backend.call(..., think=False)
    if self._session_logger:
        self._session_logger.log_llm_call(
            ..., call_type=call_type, attempt=2, ...
        )
```

Thread `call_type` through:
- `call_llm(prompt, ..., call_type="decision")` ← from `decide()`
- `plan_combat_turn(gs, ctx)` → `_call_plan_sync(..., call_type="combat_plan")`
- `call_raw(system, user, ..., call_type="reflection")` ← from callers

### MCPClient (modify existing, ~5 lines)

```python
async def post_action(self, action_body):
    data = ...  # existing
    # NEW: emit game_action
    if self._event_bus:
        self._event_bus.emit("game_action", {
            "action": action_body.get("action"),
            "params": action_body,
            "result_status": data.get("status"),
            "stable": data.get("stable", True),
        })
    return data
```

### AgentLoop (modify existing, ~10 lines)

```python
# After _build_decision_context():
if self._event_bus:
    self._event_bus.emit("context_assembly", {
        "skills": ctx.get("skill_context", "")[:500],
        "memory_type": "v2" if ctx.get("memory_hints") else "none",
        "archetype": ctx.get("archetype_context", "")[:200],
        "boss_strategy": bool(ctx.get("boss_strategy")),
    })

# After plan_combat_turn():
if self._event_bus and plan:
    self._event_bus.emit("combat_plan", {
        "items": [{"type": a.type, "card": a.card_name, "target": a.target} for a in plan.actions],
        "end_turn": plan.end_turn,
        "reasoning": plan.reasoning[:300],
    })
```

### run_agent.py (~10 lines)

- Create EventBus if `STS2_MONITOR_ENABLED`
- Pass to SessionLogger, MCPClient, Reasoner
- Start FastAPI server in daemon thread

## Frontend (React + Vite + TypeScript)

### Tech: React 18, Vite, react-virtuoso, Tailwind CSS

### Layout

```
┌─────────────────────────────────────────────────────┐
│ [●] Connected  |  Run #3  |  Floor 12  |  HP 45/80 │
├─────────────────────────────────────────────────────┤
│ [All] [LLM] [Actions] [State] [Errors]    [Search]  │
├─────────────────────────────────────────────────────┤
│                                                      │
│  10:23:05  STATE  Floor 12 · R3 · 2 enemies    [+]  │
│  10:23:05  LLM  [haiku-4-5] combat  340ms       [+] │
│  10:23:06  ACTION  play_card(2, target=0)            │
│  10:23:07  TRANSITION  COMBAT_END · Victory          │
│                                                      │
├─────────────────────────────────────────────────────┤
│ Tokens: 12,450  |  Cache: 78%  |  Calls: 23        │
└─────────────────────────────────────────────────────┘
```

### Files

```
frontend/
  src/
    App.tsx, main.tsx
    hooks/useEventStream.ts, useAutoScroll.ts
    components/
      StatusBar.tsx, FilterBar.tsx, Timeline.tsx, EventCard.tsx, StatsFooter.tsx
      cards/ (LlmCallCard, GameActionCard, StateCard, TransitionCard, etc.)
    types/events.ts
    utils/formatters.ts
```

### Key behaviors

- **Collapsed default**: one-line summary per event
- **Expand [+]**: full prompt, full response, full state JSON
- **Auto-scroll**: react-virtuoso followOutput, pause on manual scroll-up
- **Reconnect**: exponential backoff, catch-up via /api/events/history?after_id=X
- **Stats**: client-side aggregation from llm_call events

## Config

```
STS2_MONITOR_ENABLED=true    # default: false
STS2_MONITOR_PORT=8081       # default: 8081
```

## Scope

- **src/monitor/**: ~200 lines (event_bus.py, server.py)
- **Existing file changes**: ~50 lines (session_logger +15, reasoner +25, client +5, loop +10, run_agent +10)
- **Frontend**: ~1000 lines React/TS
