# Tool Validation Pipeline Design

**Date**: 2026-04-04
**Status**: Draft
**Scope**: Bug fix (bind_params scalar/array mismatch) + two-stage tool validation in EvolutionEngine

## Problem

1. **Binding bug**: `_bind_single_param()` returns scalars for `enemy_hp`, `poison_stacks`, `enemy_block`, but agent-authored tools expect arrays. All 3 active tools (poison_turns_to_kill, poison_survival_analysis, poison_block_survival_plan) silently fail at runtime with `TypeError: object of type 'int' has no len()`. The exception is caught by `ToolPreprocessor.run_applicable()` and swallowed — tools appear loaded but never produce hints.

2. **No real-state validation**: `register_tool()` validates AST + TEST_CASES (synthetic inputs), but never tests whether params can be bound from a real GameState or whether the output is useful. Of 63 `author_tool` calls in evolution_log, 44 tools were archived for manual review and 3 survive but have never been called.

3. **No quality gate**: A tool that executes correctly but produces redundant or misleading hints wastes prompt tokens and can degrade LLM decisions. No mechanism exists to evaluate tool usefulness before deployment.

## Design

### Module 1: Array-Aware Parameter Binding

**File**: `src/brain/tool_preprocessor.py`

**Change**: `bind_params()` receives the tool's SCHEMA so it knows each parameter's declared type. When a parameter is declared `type: "array"`, the binding returns a list across all enemies instead of a scalar from `enemies[0]`.

**New bindings when type=array**:

| Param name | Scalar (current) | Array (new) |
|---|---|---|
| `enemy_hp` | `gs.enemies[0].current_hp` | `[e.current_hp for e in gs.enemies]` |
| `poison_stacks` | `get_power_amount(enemies[0], "Poison")` | `[get_power_amount(e.powers, "Poison") for e in gs.enemies]` |
| `enemy_block` | `gs.enemies[0].block` | `[e.block or 0 for e in gs.enemies]` |

**Backward compatibility**: Tools without schema type info (or with `type: "integer"`) continue to receive scalars. Only explicit `type: "array"` triggers list binding.

**Implementation**:
- `bind_params(param_names, gs)` → `bind_params(param_names, gs, schema=None)`
- `_bind_single_param(pname, gs, ...)` → `_bind_single_param(pname, gs, ..., declared_type=None)`
- When `declared_type == "array"` and pname in (`enemy_hp`, `poison_stacks`, `enemy_block`), return list version
- Schema type extraction: `schema.get("parameters", {}).get(pname, {}).get("type")` — handles both flat and nested parameter formats via `get_param_info()` + raw schema lookup

### Module 2: State Snapshot Store

**New file**: `src/brain/state_snapshot_store.py`

Captures real GameState snapshots during gameplay for use in tool validation.

**Storage**:
- In-memory ring buffer: 20 most recent combat states (cleared per run)
- Persistent file: `data/evolution/state_snapshots.jsonl` — up to 100 entries, FIFO eviction
- Each entry: `{"state_type": str, "timestamp": float, "raw_state": dict}` where `raw_state` is the MCP `/state` response `data` payload (the same JSON that `parse_state()` consumes)

**Capture point**: `AgentLoop._step()`, after `parse_state()` succeeds, before decision logic. Only capture combat states (`monster`, `elite`, `boss`) since all 3 current tools and most future tools target combat.

**Query API**:
```python
class StateSnapshotStore:
    def capture(self, state_type: str, raw_state: dict) -> None
    def get_snapshots(self, state_types: list[str], n: int = 5) -> list[StateSnapshot]
    def flush_to_disk(self) -> None  # called at post-run
```

**StateSnapshot** is a frozen dataclass with `state_type`, `timestamp`, `raw_state`. Callers reconstruct GameState via `parse_state(raw_state)` when needed.

**Why not use existing JSONL logs**: Log entries store truncated prompt fragments and event metadata, not the raw MCP payload. Reconstructing GameState from logs would require a fragile reverse-engineering of the logging format. Capturing the raw payload directly is simpler and more reliable.

### Module 3: Two-Stage Tool Validation

**File**: `src/brain/evolution_engine.py` (modify `_handle_author_tool`)

After `register_tool()` succeeds (passes AST + TEST_CASES), run validation:

#### Stage 1 — Binding Dry-Run (0 API calls)

```
snapshots = snapshot_store.get_snapshots(tool.APPLICABLE_STATES, n=5)
if not snapshots:
    → ACCEPT (cold-start grace — no snapshots yet)

failures = []
successes = []
for snap in snapshots:
    gs = parse_state(snap.raw_state)
    bound = bind_params(tool.params, gs, tool.schema)
    if bound is None:
        failures.append("bind failed: param X unresolvable")
        continue
    try:
        result = tool.execute_raw(**bound)
        if not result or "execution error" in str(result):
            failures.append(f"execute returned error: {result}")
        else:
            successes.append((gs, bound, result))
    except Exception as e:
        failures.append(f"execute raised: {e}")

if not successes:
    → REJECTED: f"Tool failed on all {len(snapshots)} real game states. Errors: {failures[:3]}"
```

**Key**: Failure messages are returned to the LLM in the evolution loop, so it can fix the tool and retry.

#### Stage 2 — LLM Quality Judge (1 Sonnet call)

Pick the first successful snapshot. Format the tool hint and game state summary. Ask Sonnet to judge:

```
JUDGE_PROMPT = """You are evaluating whether a computed combat insight helps an AI agent make better decisions in Slay the Spire 2.

## Game State
{state_summary}

## Computed Insight
{tool_hint_text}

## Evaluation Criteria
1. Does this insight provide information NOT easily derivable from the raw numbers?
2. Is the recommendation actionable (tells the agent what to DO)?
3. Could this insight change a decision (e.g., "focus defense" vs "stack more poison")?

Rate: HELPFUL / REDUNDANT / MISLEADING
One sentence reasoning."""
```

**State summary**: Compact format — player HP/block/energy, enemy names + HP + intents + poison stacks, hand card names. ~200 tokens. Built from GameState, not the full combat prompt.

**Verdict handling**:
- `HELPFUL` → ACCEPT, return "SUCCESS: Tool registered and validated"
- `REDUNDANT` → REJECT, unregister tool, return "REJECTED: Judge found insight redundant — {reasoning}. Consider: does this tool add information beyond what the LLM can see in the raw state?"
- `MISLEADING` → REJECT, unregister tool, return "REJECTED: Judge found insight misleading — {reasoning}. Fix the calculation or recommendation logic."
- Parse failure → ACCEPT with warning (don't block on judge errors)

**Model**: `config.LLM_FAST_MODEL` (Sonnet 4.6). No thinking needed. Max 200 tokens response.

**Cost**: ~$0.003 per tool validation (200 input tokens state + 100 tokens hint + 100 tokens prompt + 200 tokens response).

### Module 4: Wiring

**AgentLoop changes**:
- `_init_v2()`: Create `StateSnapshotStore`, pass to `EvolutionEngine`
- `_step()`: After `parse_state()`, call `snapshot_store.capture(gs.state_type, raw_state)` for combat states
- `_post_run_evolution()`: Call `snapshot_store.flush_to_disk()` before evolution, pass store to engine
- `reset_for_new_run()`: Clear in-memory ring buffer (keep disk snapshots)

**EvolutionEngine changes**:
- Constructor: accept `snapshot_store` parameter
- `_handle_author_tool()`: After `register_tool()` succeeds, run Stage 1 + Stage 2
- On rejection: call `registry.unregister(tool_name)` + delete .py file, return REJECTED message
- Store the validation backend (Sonnet) separately from evolution backend (Opus)

**DynamicToolRegistry changes**:
- Add `unregister(name)` method: remove from `_tools` dict + delete .py file from disk + remove entry from `tool_stats.json`

### Error Budget

- Stage 1 dry-run: <50ms (5 snapshots × bind + execute, all local)
- Stage 2 judge: ~2s (one Sonnet call)
- Total overhead per `author_tool`: ~2s + $0.003
- Evolution loop has max 5 rounds, typically 1-2 tools per run → max ~$0.015 extra per run

### Testing

**Unit tests** (`tests/test_tool_validation.py`):

1. **Array binding**: Mock GameState with 2 enemies, verify `enemy_hp` returns `[hp1, hp2]` when schema declares `type: "array"`, returns `hp1` (scalar) when schema declares `type: "integer"`
2. **Snapshot store**: Capture 25 states, verify ring buffer keeps 20, verify JSONL flush, verify `get_snapshots` filtering by state_type
3. **Stage 1 dry-run**: Tool that binds correctly → passes. Tool with unbindable param → rejected with message.
4. **Stage 2 judge**: Mock Sonnet response "HELPFUL" → accepted. Mock "REDUNDANT" → rejected + unregistered. Mock "MISLEADING" → rejected.
5. **Cold start grace**: Empty snapshot store → tool accepted without validation.
6. **Integration**: Full `_handle_author_tool` flow with real poison_turns_to_kill code + mock snapshot + mock judge.

### Non-Goals

- Validating plan_evaluator tools (requires P2 integration)
- Retroactively validating the 44 archived tools (separate manual task)
- Validating skills (different system, different validation needs)
- Runtime A/B testing during actual gameplay (方案 C, deferred)
