# stream-ui Integration

How an external React-based streaming overlay (`stream-ui`) consumes STS2Agent's runtime events for live display during streamed runs.

## Counterpart

- Repo: external sibling project (path varies by contributor; checkout the `stream-ui` repo alongside `AgenticSTS`)
- Tech: Vite + React 18 + Tailwind v4, designed as an OBS Browser Source at 1920×1080.
- Detailed mapping table: `<stream-ui>/docs/integration-sts2agent.md`.

## What stream-ui Reads From STS2Agent

stream-ui subscribes to the existing **monitor WebSocket** as a passive client. **No changes to STS2Agent are required for the basic feed to work.**

```
[STS2Agent]
  EventBus → FastAPI :8081/ws/events  ──→  [stream-ui WS subscriber]
                                                │
                                                ▼
                                       LogPanel (right column)
```

Direction: push-only, agent → UI. stream-ui never sends events back into STS2Agent.

## Operational Contract

| Item | Value |
|---|---|
| Endpoint | `ws://localhost:8081/ws/events` |
| Enable | `STS2_MONITOR_ENABLED=true` before launching `scripts.run_agent` |
| Frame format | `MonitorEvent` JSON (existing) — `{id, timestamp, type, data, step, run_id}` |
| Auth | none (local-only) |
| Backpressure | none expected; stream-ui consumes at WS rate, no blocking semantics |

## Events stream-ui Already Renders Usefully

These map to display tiers in the UI's log panel:

| `MonitorEvent.type` | UI display tier |
|---|---|
| `run_start`, `run_end` | run-lifecycle marker |
| `state`, `transition` | log row (debug/info) |
| `decision`, `llm_call` | "thinking" row with 🧠 icon |
| `tool_call`, `tool_result` | log row |
| `error` | red-dot log row |
| `perf` | log row (debug) |
| anything else | generic log row |

stream-ui pulls a display string from `data.message` → `data.text` → `data.reasoning` → `data.summary` → `data.tool_name` → `data.state_type` → falls back to `type`.

## Where Adding Emits Helps the Stream

These are **optional** — stream-ui works without them — but each one makes the stream visibly richer.

### High value: LLM reasoning text

`SessionLogger` does not currently broadcast the streamed `<thinking>` content from V2Backend. Adding it makes the stream genuinely show the agent thinking.

Suggested emit point: `src/brain/v2_engine.py` (or whichever layer has access to the streaming completion).

```python
# pseudo
self._session.event_bus.emit(MonitorEvent(
    id=uuid4().hex,
    timestamp=time.time(),
    type="decision",
    data={"reasoning": chunk_text, "step": self.step},
    step=self.step,
    run_id=self.run_id,
))
```

If high-frequency streaming is too chatty, batch by sentence or by 200ms.

### Medium value: tool call I/O

Currently `tool_call` typically carries only the tool name. Add full arguments and return values:

```python
self._event_bus.emit(MonitorEvent(
    type="tool_call",
    data={"tool_name": name, "arguments": args, "summary": short_summary(args)},
    ...
))
self._event_bus.emit(MonitorEvent(
    type="tool_result",
    data={"tool_name": name, "ok": ok, "return_value": result, "summary": short_summary(result)},
    ...
))
```

`summary` is what stream-ui shows; `arguments`/`return_value` flow into `meta` for future inspection panels.

### Lower value: postrun stage progress

Memory writes, skill discovery, guide consolidation — interesting to viewers but lower-frequency. Mirror existing JSONL `_write_event()` calls into `event_bus.emit()` where appropriate. Already partially done; gaps are around write-gate reap and merge-pipeline progress.

## Don't-Do List

- **Don't** rename `MonitorEvent.type` values silently — stream-ui maps known types to UI affordances. If you remove `decision` or rename it to `agent_decision`, the icon goes away. Coordinate via this doc.
- **Don't** put streaming-only fields under top-level event keys; keep them inside `data`. stream-ui treats `data` as opaque metadata and only the documented top-level keys are stable.
- **Don't** broadcast >100 events/second sustained without batching. WS clients and the UI's 500-entry ring buffer can absorb bursts but not floods.
- **Don't** emit secrets in `data` — the WebSocket is unauthenticated and stream-ui displays the message text directly on a public stream. Sanitize before emitting.

## Verification

After enabling the monitor:

```bash
# health
curl http://localhost:8081/api/status

# inspect live frames
websocat ws://localhost:8081/ws/events | head -5
```

Then start stream-ui (`pnpm dev` in its repo) and open `http://127.0.0.1:5274/overlay` — the right log panel should fill with violet `[sts2agent]` rows as the agent runs.

## Related

- Original monitor design: `docs/2026-03-20-monitor-dashboard-design.md`
- Existing internal frontend (separate from stream-ui): `frontend/`
- stream-ui's reciprocal contract doc: `<stream-ui>/docs/integration-sts2agent.md`
