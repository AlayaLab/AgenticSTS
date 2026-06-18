# Tool Lifecycle System Design

**Date**: 2026-03-28
**Status**: Approved
**Goal**: Build complete lifecycle for dynamic tools — generation, usage, evaluation, optimization, retirement.

## Problem Statement

The agent's self-evolution system (EvolutionEngine) can create dynamic Python tools, but lacks lifecycle management. Current state:

- **38 dynamic tools** exist: 10 state_derived (active via Preprocessor), 28 plan_evaluator (0 usage, no execution path)
- **Generation**: No dedup check, no use-path validation, creates tools that can never run
- **Usage**: Keyword-based applicability causes mismatches (deck_bloat runs in combat); query tools sent unfiltered; Computed Insights output raw dicts
- **Evaluation**: success_count only means "no exception", no effectiveness measurement
- **Optimization/Retirement**: None. Tools accumulate forever.

## Architecture Overview

```
Generation ──→ Usage ──→ Evaluation ──→ Optimization/Retirement
    │            │           │                │
    │            │           │                └─ retirement sweep + promote path
    │            │           └─ effectiveness scoring
    │            ├─ state_derived: Preprocessor (fixed applicability)
    │            ├─ plan_evaluator: PlanVerifier (NEW)
    │            └─ query tools: state_type filtered
    └─ dedup + use-path validation + strict test cases
```

## Phase 1: Usage Fixes + Tracking

### 1a. Explicit APPLICABLE_STATES

**Problem**: `_infer_applicable_states()` in tool_preprocessor.py uses keyword scoring from tool description. `deck_bloat_energy_check` matches combat keywords because "energy" is in `_COMBAT_KEYWORDS`, causing it to run every combat round (4189 calls, mostly noise).

**Solution**:
- Add explicit `APPLICABLE_STATES` to all 9 active state_derived tool `.py` files
- `_infer_applicable_states()` becomes fallback only (tools without explicit declaration)
- Existing code already checks `tool.schema.get("APPLICABLE_STATES")` first (tool_preprocessor.py:413)

**Mapping for active tools**:

| Tool | APPLICABLE_STATES |
|------|-------------------|
| buffer_survival_check | monster, elite, boss |
| deck_bloat_energy_check | card_reward, card_select, shop |
| deck_size_removal_urgency | card_select, shop |
| multi_enemy_incoming_damage | monster, elite, boss |
| multi_enemy_total_damage | monster, elite, boss |
| playable_cards_check | monster, elite, boss |
| rest_site_heal_vs_upgrade_v2 | rest_site |
| silent_archetype_score | card_reward, card_select, shop |
| silent_survival_check | monster, elite, boss |
| turn_lethal_check | monster, elite, boss |

**Pre-existing bug**: Two tools already have `APPLICABLE_STATES` but use wrong state name `"rest"` instead of `"rest_site"`:
- `rest_site_heal_vs_upgrade_v2.py`: `APPLICABLE_STATES = ["rest"]` → fix to `["rest_site"]`
- `deck_bloat_energy_check.py`: `APPLICABLE_STATES = ["card_reward", "shop", "rest", "card_select"]` → fix `"rest"` to `"rest_site"`

**Files modified**: `data/evolution/tools/*.py` (add `APPLICABLE_STATES = [...]` to 8 tools, fix state name in 2 existing tools)

### 1b. Query Tools State-Type Filtering

**Problem**: `get_v2_tools()` in tool_schemas.py always returns all 5 query tools regardless of state_type. `assess_potion_value` sent during rest/map/event (useless). ~750 tokens of schema overhead per call.

**Solution**: New relevance mapping + filtered `get_v2_tools()`.

```python
_QUERY_TOOL_RELEVANCE: dict[str, list[str]] = {
    "monster":      ["recall_encounter", "search_strategy", "read_guide", "assess_potion_value"],
    "elite":        ["recall_encounter", "search_strategy", "read_guide", "assess_potion_value"],
    "boss":         ["recall_encounter", "search_strategy", "read_guide", "assess_potion_value"],
    "map":          ["search_strategy", "read_guide", "get_run_progress"],
    "rest_site":    ["search_strategy", "read_guide", "get_run_progress"],
    "shop":         ["search_strategy", "read_guide", "get_run_progress"],
    "card_reward":  ["search_strategy", "read_guide"],
    "card_select":  ["search_strategy", "read_guide"],
    "event":        ["search_strategy", "read_guide"],
    "hand_select":  [],
    "treasure":     [],
    "relic_select": [],
}
```

`get_v2_tools(state_type)` filters QUERY_TOOLS by this map.

`get_v2_combat_tools(combat_state_type)` also accepts the combat state_type (monster/elite/boss) and filters accordingly. Currently it takes no parameters — add `combat_state_type: str = "monster"` with default for backward compatibility.

**Files modified**: `src/brain/tool_schemas.py` (add mapping, modify `get_v2_tools()` and `get_v2_combat_tools()`), fix docstring "8 static query tools" → "up to 5 query tools"

### 1c. Computed Insights Compression

**Problem**: `format_hints()` outputs `key=value` pairs from raw dicts (~200-500 chars per tool). Noisy and hard for LLM to parse quickly.

**Root cause**: `DynamicTool.execute()` converts all results to `str` via `str(result)`. The existing `format_hints()` has `isinstance(hint.result, dict)` checks that are effectively dead code — `ToolHint.result` is always a string.

**Solution**: Two-part fix:

1. **Split execute into raw + formatted**: Add `execute_raw(**kwargs) -> Any` that returns the raw result (dict, str, etc.). Existing `execute()` calls `execute_raw()` then converts to str. ToolPreprocessor uses `execute_raw()` to get the dict.

```python
class DynamicTool:
    def execute_raw(self, **kwargs: Any) -> Any:
        """Run execute function, return raw result. Increments counters."""
        self.usage_count += 1
        try:
            result = self.execute_fn(**kwargs)
            self.success_count += 1
            return result
        except Exception as exc:
            return f"Tool {self.name} execution error: {exc}"

    def execute(self, **kwargs: Any) -> str:
        """Run execute function, return string result."""
        return str(self.execute_raw(**kwargs))
```

2. **FORMAT_COMPACT in tool .py files**: Optional function that receives the raw result.

```python
# In each dynamic tool .py file:
def FORMAT_COMPACT(result) -> str:
    """One-sentence summary of tool result."""
    if isinstance(result, dict) and result.get("survives"):
        return f"Survive: YES, {result['hp_remaining']}hp remaining"
    elif isinstance(result, dict):
        return f"Survive: NO, need {result.get('deficit', '?')} more block"
    return str(result)[:80]
```

3. **ToolPreprocessor calls `execute_raw()`** and stores raw result in ToolHint. `format_hints()` then:
   - Checks for FORMAT_COMPACT in tool namespace → call it on raw result
   - Falls back to priority-key extraction on dict results
   - Falls back to str truncation for string results

**ToolHint change**: `result: str` → `result: Any` (raw result from execute_raw)

**Files modified**: `src/brain/dynamic_tools.py` (add `execute_raw()`), `src/brain/tool_preprocessor.py` (use `execute_raw()`, FORMAT_COMPACT dispatch, fix ToolHint type), `data/evolution/tools/*.py` (add FORMAT_COMPACT to active tools)

### 1d. Query Tool Usage Tracking

**Problem**: No visibility into which query tools LLM actually calls. Preprocessor has `ToolUsageRecord` but V2Engine's `_agent_loop` has nothing.

**Solution**: Track query tool calls in V2Engine.

```python
@dataclass
class QueryToolRecord:
    tool_name: str
    state_type: str
    latency_ms: float
    result_chars: int
    timestamp: float
```

- V2Engine accumulates records in `_query_tool_records: list[QueryToolRecord]`
- Reset per run (like Preprocessor)
- Exposed via `get_query_telemetry() -> dict` for evolution agent's `get_performance_stats`

**Files modified**: `src/brain/v2_engine.py` (add tracking in `_agent_loop` after query tool execution)

## Phase 2: Plan Verification Pipeline

### 2a. PlanParamBinder

**Problem**: plan_evaluator tools need parameters derived from CombatPlan (e.g., `play_sequence`, `planned_block`). Currently only GameState params can be auto-bound.

**Constraint**: `CombatPlan` stores card **names** only — no damage/block values. Deriving `planned_damage` requires cross-referencing card names against hand card previews (`c.damage`, `c.block` from `GameState.hand`), and some values are target-dependent or conditional (X-cost cards, multi-hit). Complex params like `num_shivs` require card effect parsing.

**Solution**: Two-tier bindable params — trivially derivable (Tier 1) and hand-cross-referenced (Tier 2).

```python
# Tier 1: Trivially derivable from CombatPlan structure alone
AUTO_BINDABLE_FROM_PLAN_T1: frozenset[str] = frozenset({
    "play_sequence",      # list[str] — card names in plan order
    "num_cards_played",   # int — len(plan.actions where type=card)
    "ends_turn",          # bool — plan.end_turn
    "has_potion_use",     # bool — any action with type=potion
})

# Tier 2: Requires cross-referencing plan card names against GameState.hand
# Best-effort: if a card name isn't found in hand (e.g., drawn mid-plan), value is 0
AUTO_BINDABLE_FROM_PLAN_T2: frozenset[str] = frozenset({
    "planned_block",      # sum of c.block for cards in plan (from hand previews)
    "planned_damage",     # sum of c.damage for cards in plan (base, not target-specific)
    "total_energy_spent", # sum of c.energy_cost for cards in plan
})
```

`bind_plan_params(plan: CombatPlan, gs: GameState) -> dict`:
- Tier 1: Extract directly from CombatPlan fields
- Tier 2: Build name→card lookup from `gs.hand`, iterate plan actions, accumulate values
  - Card not found in hand → skip (0 contribution), don't fail
  - Target-specific damage not attempted — use base `c.damage` only
- Combine with GameState params (from existing `bind_params()`)
- Returns full param dict or None if any required param unbindable

**Removed from bindable set**: `num_shivs` (requires card effect parsing), `target_enemy_index` (ambiguous for multi-action plans), `damage_multiplier` (subjective). These params remain in `NOT_BINDABLE` — tools using them stay classified as plan_evaluator but cannot be auto-bound (evolution will be informed of available params).

**New file**: `src/brain/plan_verifier.py` (contains PlanParamBinder + PlanVerifier)

### 2b. PlanVerifier

**Problem**: 28 plan_evaluator tools have no execution path.

**Solution**: Post-plan verification step in combat flow.

```
Current:  GameState → CombatPlan → Execute
New:      GameState → CombatPlan → PlanVerifier → [re-plan if critical] → Execute
```

PlanVerifier:
1. Filter applicable plan_evaluator tools (by APPLICABLE_STATES matching current combat type)
2. Bind params via `bind_plan_params()`
3. Execute each tool (max 5 tools, 500ms budget — same as Preprocessor)
4. Classify results:
   - Tool returns dict with `severity: "critical"` → collect as critical warning
   - Otherwise → record in telemetry
5. If any critical warnings:
   - Inject warnings into CombatConversation as feedback message
   - Return `needs_replan=True`

**Integration point**: `AgentLoop._generate_combat_plan()` — after `_validate_combat_plan()` passes, before execution.

**Re-plan budget**: The existing validation-retry flow and PlanVerifier share a single re-plan budget per round. The caller maintains a `replans_remaining = 1` counter:
- If `_validate_combat_plan()` fails → re-plan, decrement counter
- If validation passes → run PlanVerifier → if critical + counter > 0 → re-plan, decrement counter
- PlanVerifier only runs on validated plans (never on already-re-planned plans)

This ensures at most 1 re-plan per round regardless of the source (validation failure OR plan verification).

**PlanVerifier telemetry**: PlanVerifier maintains its own `ToolUsageRecord` list (same structure as Preprocessor). Exposed via `get_telemetry_summary() -> dict`. Both Preprocessor and PlanVerifier telemetry are passed to EvolutionEngine's `get_performance_stats` as separate sections (`preprocessor_telemetry` and `plan_verifier_telemetry`).

**Files modified**: `src/brain/plan_verifier.py` (new), `src/agent/loop.py` (call PlanVerifier after combat plan)

### 2c. EvolutionEngine Adaptation

**Problem**: EvolutionEngine creates plan_evaluator tools without validating that params are bindable.

**Solution**: Validate at registration time.

In `DynamicToolRegistry.register_tool()`:
- After AST validation and test case validation
- Classify as state_derived or plan_evaluator
- If state_derived: all params must be in `AUTO_BINDABLE`
- If plan_evaluator: non-state params must be in `AUTO_BINDABLE_FROM_PLAN`
- If neither: REJECT with error listing available params

Also require `APPLICABLE_STATES` declaration. Missing → REJECT.

**Files modified**: `src/brain/dynamic_tools.py` (add validation in `register_tool()`), `src/brain/evolution_engine.py` (update system prompt to inform LLM of available params and APPLICABLE_STATES requirement)

## Phase 3: Generation Quality Gates

### 3a. Dedup Check

**Problem**: No check for overlapping tools. Agent could create `block_check_v2` that does the same thing as `block_sufficiency_check`.

**Solution**: Before registration, check existing tools:
- Name similarity: word-overlap ratio on underscore-split tool names (reject if overlap > 80%). No external dependency — simple set intersection over split names.
- Parameter overlap: Jaccard similarity on param sets (reject if > 80%)
- Description overlap: word-level Jaccard on descriptions (warn if > 60%)

If overlap detected: REJECT with message `"Similar tool already exists: {existing_name}. Use update_guide to improve it or author a tool with different functionality."`

**Files modified**: `src/brain/dynamic_tools.py` (add `_check_dedup()` in `register_tool()`)

### 3b. Use-Path Validation

Covered in 2c above — params must be bindable, APPLICABLE_STATES must be declared.

### 3c. Test Case Requirements

**Problem**: TEST_CASES is optional and many tools have trivial smoke tests.

**Solution**:
- Require `len(TEST_CASES) >= 2`
- At least 1 test case must have a recognized assertion key: `expected`, `expected_contains`, `expected_keys`, or any `expected_<field>_contains` pattern (which is already supported by `_validate_test_case` assertion type 5)
- Pure smoke tests (no assertion) count max 1 toward the minimum

**Files modified**: `src/brain/dynamic_tools.py` (add validation in `_load_tool_file()` and `register_tool()`)

## Phase 4: Evaluation + Retirement

### 4a. Effectiveness Scoring

**Problem**: `success_count` only means "didn't raise exception". No measurement of whether tool output was useful.

**Solution**: `effectiveness_score` computed per tool per sweep.

```python
def compute_effectiveness(tool: DynamicTool, runs_since_creation: int) -> float:
    """Effectiveness = usage_rate * success_rate."""
    if runs_since_creation == 0:
        return 1.0  # New tool, give benefit of doubt
    usage_rate = tool.usage_count / max(1, runs_since_creation)
    success_rate = tool.success_count / max(1, tool.usage_count)
    return usage_rate * success_rate
```

- `usage_rate`: average uses per run (high = frequently applicable)
- `success_rate`: fraction of non-error executions
- Score range: 0.0 (never used or always fails) to N (used N times per run successfully)

Future enhancement: track `decision_alignment` — did the LLM's final decision align with tool's recommendation? This requires Phase 1d tracking data and is optional for v1.

**Files modified**: `src/brain/dynamic_tools.py` (add `compute_effectiveness()`)

### 4b. Retirement Sweep

**Problem**: No mechanism to remove low-value tools. 28 plan_evaluator tools sit forever.

**Solution**: Sweep every N runs (configurable, default 10).

```python
RETIREMENT_SWEEP_INTERVAL = 10  # runs
RETIREMENT_MIN_AGE_RUNS = 5     # must exist for at least 5 runs
RETIREMENT_SCORE_THRESHOLD = 0.1
RETIREMENT_DELETE_AFTER_SWEEPS = 2  # deactivated for 2 consecutive sweeps → delete
```

Sweep logic:
1. Compute `effectiveness_score` for each tool
2. If `score < threshold` and `age >= min_age`:
   - First offense: mark `deactivated` in retirement state file
   - Second consecutive sweep still deactivated: delete .py file
3. Log all actions to `data/evolution/evolution_log.jsonl`

**Retirement state tracking**: Use `data/evolution/tools/retirement_state.json` (separate from tool_stats.json):
```json
{
  "block_sufficiency_check": {"deactivated_at_sweep": 3, "consecutive_sweeps": 1},
  "boss_dps_readiness_check": {"deactivated_at_sweep": 2, "consecutive_sweeps": 2}
}
```
- Deactivated tools remain as valid `.py` files (NOT renamed with `_` prefix)
- Registry `load_all()` loads them normally but skips execution via a deactivated check
- `DynamicToolRegistry` checks retirement_state.json at load time, marks deactivated tools
- `DynamicTool` gets a `deactivated: bool` field; Preprocessor and PlanVerifier skip deactivated tools
- This avoids the `_` prefix rename approach which would break cross-run tracking

**Effectiveness normalization for narrow tools**: `usage_rate` is normalized by the fraction of runs where the tool's `APPLICABLE_STATES` were actually encountered. For example, `silent_archetype_score` (applicable to card_reward/card_select/shop) on a non-Silent character run would not count against its usage_rate. Requires tracking which state_types were seen per run (already available from Preprocessor telemetry).

**`runs_since_creation` tracking**: Add `creation_run: int` field to tool_stats.json. DynamicToolRegistry maintains a monotonic `total_runs` counter (incremented in `reset_for_new_run()`, persisted to tool_stats.json).

**Files modified**: `src/brain/dynamic_tools.py` (add `retirement_sweep()`, deactivated field, runs tracking, retirement_state.json persistence)

### 4c. Promotion Path

**Problem**: High-value dynamic tools stay as .py files in data/ forever.

**Solution**: Flag high-value tools as `promote_candidate` in `get_performance_stats()`.

Criteria:
- `effectiveness_score > 2.0` (used 2+ times per applicable run on average)
- `age > 20 runs`
- `success_rate > 95%`

Output in evolution stats:
```json
{"promote_candidates": ["turn_lethal_check", "multi_enemy_incoming_damage"]}
```

Actual promotion (moving to src/brain/) requires human review — not automated.

**Files modified**: `src/brain/dynamic_tools.py` (add promote candidate logic to `stats()`)

## File Change Summary

| File | Changes |
|------|---------|
| `src/brain/tool_schemas.py` | Query tool relevance map, filtered `get_v2_tools()`, fix `get_v2_combat_tools()` signature, fix docstring |
| `src/brain/tool_preprocessor.py` | Use `execute_raw()`, FORMAT_COMPACT dispatch, ToolHint.result type → Any |
| `src/brain/dynamic_tools.py` | Add `execute_raw()`, dedup check, use-path validation, test case requirements, effectiveness scoring, retirement sweep (with retirement_state.json), runs tracking, promote candidates, registration validation, deactivated field |
| `src/brain/v2_engine.py` | Query tool usage tracking (QueryToolRecord) |
| `src/brain/plan_verifier.py` | **NEW**: PlanParamBinder (Tier 1+2 params) + PlanVerifier + telemetry |
| `src/brain/evolution_engine.py` | Updated system prompt (available params, APPLICABLE_STATES requirement, Tier 1/2 param lists) |
| `src/agent/loop.py` | PlanVerifier integration after combat plan, shared re-plan budget |
| `config.py` | Retirement sweep config vars |
| `data/evolution/tools/*.py` | APPLICABLE_STATES + FORMAT_COMPACT for 10 active tools |
| `data/evolution/tools/retirement_state.json` | **NEW**: Deactivation tracking across runs |

## Constraints

- Decision tools structured output mechanism unchanged
- V2Engine multi-turn agent loop core architecture unchanged
- AST sandbox security model not relaxed
- Plan verification re-plan limited to 1 per round (no loops)
- Promotion requires human review (not automated)

## Risks

- **Plan verification latency**: Running evaluator tools adds ~50-200ms per combat round. Mitigated by max 5 tools and 500ms budget (same as Preprocessor).
- **Re-plan cost**: One extra Sonnet API call per critical warning. Expected rare (most plans won't trigger critical). Capped at 1 re-plan.
- **Retirement false positives**: Good tools with narrow applicability (e.g., `silent_archetype_score`, only for Silent character) might have low usage_rate. Mitigated by min_age requirement and per-character normalization option.
- **Dedup false positives**: Simple word-overlap/Jaccard might reject legitimately different tools with similar names. Start conservative (reject only very high overlap), tune thresholds with data.
- **PlanVerifier initial coverage**: Only ~1 of 28 existing plan_evaluator tools will be auto-bindable with Tier 1+2 params at launch. The pipeline's value is forward-looking: new tools created after Phase 2c will be designed for bindability. Existing tools that can't bind will be candidates for retirement in Phase 4.
