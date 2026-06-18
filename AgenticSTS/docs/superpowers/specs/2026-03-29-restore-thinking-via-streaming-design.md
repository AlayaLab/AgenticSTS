# Restore Thinking via Streaming — Design Spec

## Problem

After disabling thinking for all tool_use calls (commit `112aa67`) to work around proxy.example.com proxy stripping tool_use blocks, Codex discovered that **streaming mode** (`messages.stream(...).get_final_message()`) bypasses the proxy's non-streaming aggregation layer and preserves all content blocks (thinking + text + tool_use).

Verified empirically:
- Non-streaming: `blocks=['text']`, thinking converted to `<thinking>` tag, tool_use stripped
- **Streaming: `blocks=['thinking', 'text', 'tool_use']` — all 3 blocks preserved**

Codex already landed the streaming change in `v2_backend.py`. The remaining work is re-enabling thinking in the gameplay path with tiered effort levels.

## Design

### Tier Effort Strategy

| Tier | States | Model | Thinking | Effort | Rationale |
|------|--------|-------|----------|--------|-----------|
| fast | map, hand_select, treasure | Sonnet 4.6 | OFF | — | Simple decisions, no reasoning needed |
| strategic | combat_plan, rest_site, shop, event, card_reward, card_select, monster, elite, boss | Sonnet 4.6 | ON | medium | Core gameplay quality. Medium balances latency (~20s) vs reasoning depth |
| analysis | post-run (call_raw) | Opus 4.6 | ON | high | Deep reasoning for guide/rule/skill generation |
| evolution | post-run (EvolutionEngine) | Opus 4.6 | ON | high | Now safe via streaming |

### Changes by File

**`config.py`** — Restore `LLM_THINK_EFFORT_STRATEGIC` and update comment:
```python
# ── Thinking Mode ─────────────────────────────────────────────
# Thinking DISABLED for fast tier (simple decisions).
# Thinking ENABLED for strategic tier (gameplay) and analysis tier (post-run)
# via streaming to bypass proxy.example.com proxy block stripping.
LLM_THINK_TYPE = os.getenv("STS2_THINK_TYPE", "adaptive")
LLM_THINK_EFFORT_STRATEGIC = os.getenv("STS2_THINK_EFFORT_STRATEGIC", "medium")
LLM_THINK_EFFORT_ANALYSIS = os.getenv("STS2_THINK_EFFORT_ANALYSIS", "high")
# Budget for Batch API (legacy type=enabled mode, not adaptive)
LLM_THINK_BUDGET_ANALYSIS = int(os.getenv("STS2_THINK_BUDGET_ANALYSIS", "10000"))
```

**`v2_engine.py`** — `_get_v2_tier` returns `tuple[str, str]` (model, effort):
```python
def _get_v2_tier(state_type, *, is_replan=False) -> tuple[str, str]:
    if is_replan:
        return (config.LLM_STRATEGIC_MODEL, "low")
    tier = _V2_TIER_MAP.get(state_type, "strategic")
    model = getattr(config, f"LLM_{tier.upper()}_MODEL")
    # fast tier: no thinking (effort="")
    # strategic tier: medium effort thinking
    effort = "" if tier == "fast" else getattr(config, f"LLM_THINK_EFFORT_{tier.upper()}", "medium")
    return (model, effort)
```

**`v2_engine.py`** — `_agent_loop` accepts `effort`, derives `think`:
```python
async def _agent_loop(self, ..., effort: str = "", ...):
    use_think = bool(effort)
    # ...
    response = await self._backend.acall(
        ..., think=use_think, effort=effort, ...
    )
```

**`v2_engine.py`** — Call sites unpack 2 values:
```python
model, effort = self._get_v2_tier(gs.state_type)
# pass effort=effort to _agent_loop
```

**`evolution_engine.py`** — Restore thinking + strip thinking blocks from multi-turn history:
```python
# Restore thinking in the call:
response = self._backend.call(..., think=True, effort="high", ...)

# Strip thinking blocks before appending to multi-turn messages (line ~389):
# Anthropic requires prior-turn thinking blocks to be removed/redacted.
filtered_content = [
    b for b in response.content
    if not (hasattr(b, "type") and getattr(b, "type", None) == "thinking")
] or [{"type": "text", "text": "(thinking only)"}]
messages.append({"role": "assistant", "content": filtered_content})
```

Note: evolution engine's `max_tokens=4096` will be overridden to `max(4096, 16000)=16000` by the adaptive thinking logic. This is acceptable — evolution calls are infrequent (<5 per run).

**`conversation.py`** — No change. Thinking block stripping is correct behavior:
- Anthropic requires prior-turn thinking blocks to be removed or redacted
- Current `_append_assistant` filter preserves this requirement
- Thinking value is per-turn reasoning quality, not cross-turn memory

**`v2_backend.py`** — No change. Streaming already gates on `tools and ANTHROPIC_BASE_URL`.

**`call_raw` (llm_caller.py)** — No change. Still non-streaming (no tools), `<thinking>` tag stripping stays.

### Preserved Defensive Code

The `proxy_stripped` detection and retry logic in `_agent_loop` (lines 581-632) is **kept** as defensive code. With streaming it should never trigger, but it protects against:
- Future proxy behavior changes
- Network issues causing partial streaming responses
- Edge cases where SDK falls back to non-streaming

**`scripts/run_agent.py`** — Update startup log string:
```python
# "off-gameplay/on-analysis" → "fast=off/strategic=medium/analysis=high"
mode, "fast=off/strategic=medium/analysis=high", skills_str, memory_str, runs_str,
```

**`v2_engine.py` session logger** — Change `think_budget=0` to log actual effort:
```python
# Line ~478: replace think_budget=0 with effort info
think_budget=0,  # → keep 0 (effort is logged via tier_name)
```

### Session Logger / Monitor Impact

- `_extract_thinking()` will now find real `ThinkingBlock` objects (not empty strings)
- `thinking_text` field in session logs will be populated for strategic tier calls
- Monitor AI summarizer will receive thinking text for combat plan analysis
- Tier logging uses `_V2_TIER_MAP.get(state_type_hint, "strategic")` — already correct

### Anthropic API Constraints (verified)

- `tool_choice: {"type": "auto"}` is the only mode used in `_agent_loop` — compatible with thinking
- `v2_backend.py` already coerces `{"type": "tool"}` → `{"type": "auto"}` when `think=True`
- Prior-turn thinking blocks must be stripped — handled by `conversation.py` and `_agent_loop` (both have existing filter logic that was dormant with `think=False`)
- Unlisted state_types default to `"strategic"` tier → thinking ON. This is the correct default for new state types

### Existing Thinking Block Stripping (already in code, becomes active)

Two places already strip thinking blocks from multi-turn messages:
1. `conversation.py:_append_assistant` (lines 207-217) — combat multi-turn
2. `v2_engine.py:_agent_loop` (lines ~506-512) — query tool round-trips

These were dormant with `think=False` but will now activate. Both correctly filter `type=="thinking"` from content blocks before storing in message history.

### Performance Expectations

| Metric | Before (no thinking) | After (strategic=medium) |
|--------|---------------------|-------------------------|
| Output tokens per strategic call | ~350 | ~1500-2500 |
| Latency per combat plan | ~10s | ~20-30s |
| Total per run (~200 calls, ~130 strategic) | ~5 min | ~12-15 min |
| Post-run analysis | unchanged | unchanged |

### What This Does NOT Change

1. **`call_raw` path** — still non-streaming, still strips `<thinking>` tags from proxy text
2. **`conversation.py` thinking block stripping** — correct and required for multi-turn
3. **Batch API** — still uses legacy `type=enabled` + `budget_tokens` (separate path)
4. **Fast tier decisions** — remain think=False (map, hand_select, treasure)
5. **proxy_stripped retry logic** — kept as defensive fallback
