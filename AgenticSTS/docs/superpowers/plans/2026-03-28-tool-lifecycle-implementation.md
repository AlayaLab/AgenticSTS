# Tool Lifecycle System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build complete lifecycle for dynamic tools — generation, usage, evaluation, optimization, retirement.

**Architecture:** Four-phase rollout: (1) fix usage layer (APPLICABLE_STATES, query filtering, insights compression, tracking), (2) plan verification pipeline for plan_evaluator tools, (3) generation quality gates (dedup, param validation, test requirements), (4) evaluation scoring + retirement sweep + promotion.

**Tech Stack:** Python 3.11+, pytest, Anthropic Claude API (tool_use), frozen dataclasses, JSONL logging.

**Spec:** `docs/superpowers/specs/2026-03-28-tool-lifecycle-design.md`

---

## File Structure

| File | Responsibility |
|------|---------------|
| `src/brain/dynamic_tools.py` | DynamicTool + DynamicToolRegistry: execute_raw(), deactivated field, dedup, param validation, test requirements, effectiveness scoring, retirement sweep, runs tracking, promotion |
| `src/brain/tool_schemas.py` | Query tool relevance mapping + filtered get_v2_tools() |
| `src/brain/tool_preprocessor.py` | ToolHint.result type fix, FORMAT_COMPACT dispatch, use execute_raw() |
| `src/brain/v2_engine.py` | QueryToolRecord tracking in _agent_loop |
| `src/brain/plan_verifier.py` | **NEW**: PlanParamBinder + PlanVerifier + telemetry |
| `src/brain/evolution_engine.py` | Updated system prompt with param/state constraints |
| `src/agent/loop.py` | PlanVerifier integration, shared re-plan budget |
| `config.py` | Retirement sweep config vars |
| `data/evolution/tools/*.py` | APPLICABLE_STATES + FORMAT_COMPACT for 10 active tools |
| `tests/test_tool_lifecycle.py` | **NEW**: Tests for all lifecycle features |

---

## Task 1: DynamicTool.execute_raw() + ToolHint type fix

**Files:**
- Modify: `src/brain/dynamic_tools.py:562-595` (DynamicTool class)
- Modify: `src/brain/tool_preprocessor.py:39-45` (ToolHint dataclass)
- Modify: `src/brain/tool_preprocessor.py:430-474` (run_applicable — call execute_raw)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for execute_raw()**

```python
# tests/test_tool_lifecycle.py
"""Tests for tool lifecycle features."""
from __future__ import annotations

import tempfile
from types import SimpleNamespace
from pathlib import Path

from src.brain.dynamic_tools import DynamicToolRegistry


# ── Test Helpers ──────────────────────────────────────────────

def _make_combat_gs(hand_cards=None, hp=50, max_hp=70, energy=3, enemies=None, floor=10, act=1, gold=100):
    """Create a minimal mock GameState for testing."""
    hand = []
    for c in (hand_cards or []):
        hand.append(SimpleNamespace(
            name=c.get("name", "Card"),
            damage=c.get("damage"),
            block=c.get("block"),
            energy_cost=c.get("energy_cost", 1),
            rules_text="",
            rarity="Common",
        ))
    enemy_list = []
    for e in (enemies or []):
        intents = [SimpleNamespace(
            damage=e.get("damage"), hits=e.get("hits", 1),
            total_damage=e.get("total_damage"), intent_type="attack",
        )] if e.get("damage") else []
        enemy_list.append(SimpleNamespace(
            name=e.get("name", "Enemy"), current_hp=e.get("hp", 30),
            max_hp=e.get("max_hp", 30), block=e.get("block", 0),
            intents=intents, powers=[],
        ))
    raw_run = SimpleNamespace(max_energy=energy)
    raw_combat_player = SimpleNamespace(block=0, powers=[])
    raw_combat = SimpleNamespace(player=raw_combat_player)
    raw = SimpleNamespace(run=raw_run, combat=raw_combat)
    return SimpleNamespace(
        player_hp=hp, player_max_hp=max_hp, hp_ratio=hp/max_hp,
        energy=energy, hand=hand, enemies=enemy_list,
        deck=[], deck_size=10, floor=floor, act=act, gold=gold,
        relics=[], potions=[], character="Silent",
        state_type="monster", is_combat=True, raw=raw,
    )


def _make_tool_code(name, params, include_applicable_states=True, num_test_cases=2):
    """Generate valid dynamic tool code for testing."""
    param_defs = ", ".join(f'"{p}": {{"type": "int", "description": "{p}"}}' for p in params)
    param_args = ", ".join(f"{p}=0" for p in params)
    param_sum = " + ".join(params) if params else "0"

    states_line = 'APPLICABLE_STATES = ["monster", "elite", "boss"]\n' if include_applicable_states else ""

    tc_lines = []
    for i in range(num_test_cases):
        inputs = ", ".join(f'"{p}": {i + 1}' for p in params)
        expected_val = sum(i + 1 for _ in params)
        assertion = f', "expected": {{"total": {expected_val}}}' if i == 0 else f', "expected_contains": "total"'
        tc_lines.append(f'    {{"input": {{{inputs}}}{assertion}}}')

    test_cases = ",\n".join(tc_lines)

    return f'''
SCHEMA = {{
    "name": "{name}",
    "description": "Test tool: {name}.",
    "parameters": {{{param_defs}}},
}}
{states_line}
def execute({param_args}, **kwargs):
    return {{"total": {param_sum}}}

TEST_CASES = [
{test_cases}
]
'''


DICT_RETURNING_TOOL = '''
SCHEMA = {
    "name": "test_dict_tool",
    "description": "Returns a dict result.",
    "parameters": {
        "value": {"type": "int", "description": "Input value"},
    },
}

def execute(value=0, **kwargs):
    return {"result": value * 2, "note": "doubled"}

TEST_CASES = [
    {"input": {"value": 5}, "expected": {"result": 10}},
    {"input": {"value": 0}, "expected": {"result": 0}},
]
'''


class TestExecuteRaw:
    def test_execute_raw_returns_dict(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool is not None
            raw = tool.execute_raw(value=5)
            assert isinstance(raw, dict)
            assert raw["result"] == 10

    def test_execute_returns_str(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool is not None
            result = tool.execute(value=5)
            assert isinstance(result, str)
            assert "10" in result

    def test_execute_raw_increments_counters(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool.usage_count == 0
            tool.execute_raw(value=1)
            assert tool.usage_count == 1
            assert tool.success_count == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestExecuteRaw -v`
Expected: FAIL — `execute_raw` not defined

- [ ] **Step 3: Implement execute_raw() in DynamicTool**

In `src/brain/dynamic_tools.py`, add `execute_raw()` and update `__slots__`:

```python
# DynamicTool class — update __slots__ to add 'deactivated'
__slots__ = ("name", "schema", "execute_fn", "test_cases", "source_path",
             "usage_count", "success_count", "created_at", "motivation",
             "deactivated", "format_compact_fn")

def __init__(self, ..., motivation: str = "") -> None:
    # ... existing fields ...
    self.deactivated = False
    self.format_compact_fn = None  # Set from tool namespace if present

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

- [ ] **Step 4: Update ToolHint result type + Preprocessor to use execute_raw**

In `src/brain/tool_preprocessor.py`:

```python
# ToolHint: change result type
@dataclass(frozen=True)
class ToolHint:
    tool_name: str
    result: Any  # was str — now raw result (dict, str, etc.)
    latency_ms: float
```

In `run_applicable()`, change execute call:

```python
# Line ~434: change self._registry.execute(name, bound) to:
tool_obj = self._registry.get(name)
result = tool_obj.execute_raw(**bound) if tool_obj else ""
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestExecuteRaw tests/test_tool_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/brain/dynamic_tools.py src/brain/tool_preprocessor.py tests/test_tool_lifecycle.py
git commit -m "feat: add DynamicTool.execute_raw() + ToolHint.result type fix"
```

---

## Task 2: APPLICABLE_STATES for 10 active tools

**Files:**
- Modify: `data/evolution/tools/buffer_survival_check.py`
- Modify: `data/evolution/tools/deck_bloat_energy_check.py` (fix "rest" → "rest_site")
- Modify: `data/evolution/tools/deck_size_removal_urgency.py`
- Modify: `data/evolution/tools/multi_enemy_incoming_damage.py`
- Modify: `data/evolution/tools/multi_enemy_total_damage.py`
- Modify: `data/evolution/tools/playable_cards_check.py`
- Modify: `data/evolution/tools/rest_site_heal_vs_upgrade_v2.py` (fix "rest" → "rest_site")
- Modify: `data/evolution/tools/silent_archetype_score.py`
- Modify: `data/evolution/tools/silent_survival_check.py`
- Modify: `data/evolution/tools/turn_lethal_check.py`
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for APPLICABLE_STATES loading**

```python
class TestApplicableStates:
    def test_applicable_states_loaded_from_tool_file(self):
        tool_code = '''
SCHEMA = {
    "name": "test_with_states",
    "description": "A test tool with explicit states.",
    "parameters": {"current_hp": {"type": "int"}},
}
APPLICABLE_STATES = ["monster", "elite", "boss"]

def execute(current_hp=0, **kwargs):
    return {"hp": current_hp}

TEST_CASES = [
    {"input": {"current_hp": 10}, "expected": {"hp": 10}},
    {"input": {"current_hp": 0}, "expected": {"hp": 0}},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_with_states.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_with_states")
            assert tool is not None
            assert tool.schema.get("APPLICABLE_STATES") == ["monster", "elite", "boss"]
```

- [ ] **Step 2: Run test — should PASS** (existing code already loads APPLICABLE_STATES at dynamic_tools.py:754-756)

Run: `python -m pytest tests/test_tool_lifecycle.py::TestApplicableStates -v`

- [ ] **Step 3: Add APPLICABLE_STATES to all 10 active tools**

Add to the top of each file (after SCHEMA dict):

| File | Line to add |
|------|------------|
| `buffer_survival_check.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |
| `deck_bloat_energy_check.py` | Change existing `["card_reward", "shop", "rest", "card_select"]` → `["card_reward", "shop", "rest_site", "card_select"]` |
| `deck_size_removal_urgency.py` | `APPLICABLE_STATES = ["card_select", "shop"]` |
| `multi_enemy_incoming_damage.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |
| `multi_enemy_total_damage.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |
| `playable_cards_check.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |
| `rest_site_heal_vs_upgrade_v2.py` | Change existing `["rest"]` → `["rest_site"]` |
| `silent_archetype_score.py` | `APPLICABLE_STATES = ["card_reward", "card_select", "shop"]` |
| `silent_survival_check.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |
| `turn_lethal_check.py` | `APPLICABLE_STATES = ["monster", "elite", "boss"]` |

- [ ] **Step 4: Run preprocessor tests to verify no regressions**

Run: `python -m pytest tests/test_tool_preprocessor.py tests/test_tool_lifecycle.py -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add data/evolution/tools/*.py tests/test_tool_lifecycle.py
git commit -m "feat: add explicit APPLICABLE_STATES to 10 active dynamic tools"
```

---

## Task 3: Query tools state-type filtering

**Files:**
- Modify: `src/brain/tool_schemas.py:478-511` (get_v2_tools, get_v2_combat_tools)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for query tool filtering**

```python
class TestQueryToolFiltering:
    def test_combat_gets_all_4_query_tools(self):
        from src.brain.tool_schemas import get_v2_tools
        tools, name = get_v2_tools("monster")
        tool_names = {t["name"] for t in tools}
        assert "recall_encounter" in tool_names
        assert "assess_potion_value" in tool_names
        assert name == "combat_action"

    def test_rest_excludes_potion_and_encounter(self):
        from src.brain.tool_schemas import get_v2_tools
        tools, name = get_v2_tools("rest_site")
        tool_names = {t["name"] for t in tools}
        assert "assess_potion_value" not in tool_names
        assert "recall_encounter" not in tool_names
        assert "get_run_progress" in tool_names
        assert name == "rest_action"

    def test_hand_select_gets_no_query_tools(self):
        from src.brain.tool_schemas import get_v2_tools
        tools, name = get_v2_tools("hand_select")
        tool_names = {t["name"] for t in tools}
        # Only the decision tool, no query tools
        assert tool_names == {"hand_select_action"}

    def test_combat_plan_tools_filtered(self):
        from src.brain.tool_schemas import get_v2_combat_tools
        tools, name = get_v2_combat_tools("boss")
        tool_names = {t["name"] for t in tools}
        assert "recall_encounter" in tool_names
        assert name == "combat_plan"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestQueryToolFiltering -v`
Expected: FAIL — rest_site still has all 5 query tools

- [ ] **Step 3: Implement query tool filtering**

In `src/brain/tool_schemas.py`, add relevance mapping and update functions:

```python
# After QUERY_TOOLS import area (inside get_v2_tools)
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


def get_v2_tools(state_type: str) -> tuple[list[dict], dict | None]:
    """Get tools for V2 agent loop: filtered query tools + decision tool.

    Returns (all_tools, decision_tool_name).
    Query tools are filtered by state_type relevance — not all 5 are sent every time.
    """
    from src.brain.query_tools import QUERY_TOOLS

    decision_tool = _STATE_TOOL_MAP.get(state_type)
    if decision_tool is None:
        return [], None

    relevant_names = _QUERY_TOOL_RELEVANCE.get(state_type, [])
    filtered_query = [t for t in QUERY_TOOLS if t["name"] in relevant_names]

    all_tools = filtered_query + [decision_tool]
    return all_tools, decision_tool["name"]


def get_v2_combat_tools(combat_state_type: str = "monster") -> tuple[list[dict], str]:
    """Get tools for V2 combat plan: filtered query tools + combat_plan tool."""
    from src.brain.query_tools import QUERY_TOOLS

    relevant_names = _QUERY_TOOL_RELEVANCE.get(combat_state_type, [])
    filtered_query = [t for t in QUERY_TOOLS if t["name"] in relevant_names]

    all_tools = filtered_query + [COMBAT_PLAN_TOOL]
    return all_tools, COMBAT_PLAN_TOOL["name"]
```

- [ ] **Step 4: Fix docstring + update combat tools caller**

In `src/brain/tool_schemas.py:485`, fix docstring: change `"8 static query tools + 1 decision tool"` to `"Filtered query tools (0-5) + 1 decision tool"`.

In `src/brain/v2_engine.py:290`, update `get_v2_combat_tools()` call to pass the combat state type:

```python
# Was: tools, decision_tool_name = get_v2_combat_tools()
# Now: pass combat state type from conversation or state
combat_type = getattr(conversation, '_combat_state_type', 'monster') if hasattr(conversation, '_combat_state_type') else 'monster'
tools, decision_tool_name = get_v2_combat_tools(combat_type)
```

Note: The actual combat state type (monster/elite/boss) is available via `self._cached_map_node_type` in the agent loop. The caller (`_generate_combat_plan` in loop.py) should pass it through when creating the conversation or as a parameter. For now, default "monster" is acceptable — all combat states share the same 4 query tools.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestQueryToolFiltering -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/brain/tool_schemas.py src/brain/v2_engine.py tests/test_tool_lifecycle.py
git commit -m "feat: filter query tools by state_type relevance"
```

---

## Task 4: FORMAT_COMPACT dispatch in Preprocessor

**Files:**
- Modify: `src/brain/tool_preprocessor.py:478-531` (format_hints)
- Modify: `src/brain/dynamic_tools.py:700-766` (_load_tool_file — capture FORMAT_COMPACT)
- Modify: `data/evolution/tools/buffer_survival_check.py` (add FORMAT_COMPACT)
- Modify: `data/evolution/tools/turn_lethal_check.py` (add FORMAT_COMPACT)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for FORMAT_COMPACT**

```python
class TestFormatCompact:
    def test_format_compact_used_when_present(self):
        tool_code = '''
SCHEMA = {
    "name": "test_compact",
    "description": "Tool with compact formatter.",
    "parameters": {"value": {"type": "int"}},
}
APPLICABLE_STATES = ["monster"]

def execute(value=0, **kwargs):
    return {"score": value, "verdict": "good" if value > 5 else "bad"}

def FORMAT_COMPACT(result):
    if isinstance(result, dict):
        return f"Score={result['score']}: {result['verdict']}"
    return str(result)[:80]

TEST_CASES = [
    {"input": {"value": 10}, "expected": {"score": 10, "verdict": "good"}},
    {"input": {"value": 2}, "expected": {"score": 2, "verdict": "bad"}},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_compact.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_compact")
            assert tool is not None
            assert tool.format_compact_fn is not None
            raw = tool.execute_raw(value=10)
            compact = tool.format_compact_fn(raw)
            assert compact == "Score=10: good"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestFormatCompact -v`
Expected: FAIL — format_compact_fn not set

- [ ] **Step 3: Capture FORMAT_COMPACT in _load_tool_file**

In `src/brain/dynamic_tools.py` `_load_tool_file()`, after capturing TOOL_TYPE and APPLICABLE_STATES:

```python
# Capture optional FORMAT_COMPACT for ToolPreprocessor
format_compact_fn = namespace.get("FORMAT_COMPACT")
# ... in DynamicTool constructor:
tool = DynamicTool(...)
if callable(format_compact_fn):
    tool.format_compact_fn = format_compact_fn
```

- [ ] **Step 4: Update format_hints() to use FORMAT_COMPACT**

In `src/brain/tool_preprocessor.py` `format_hints()`:

```python
for hint in deduped:
    # Try FORMAT_COMPACT first
    tool_obj = self._registry.get(hint.tool_name) if hasattr(self, '_registry') else None
    if tool_obj and tool_obj.format_compact_fn:
        try:
            result_str = tool_obj.format_compact_fn(hint.result)
        except Exception:
            result_str = str(hint.result)[:200]
    elif isinstance(hint.result, dict):
        # Existing priority-key extraction
        extracted = {k: v for k, v in hint.result.items() if k in _PRIORITY_KEYS and v is not None}
        if not extracted:
            extracted = dict(list(hint.result.items())[:3])
        parts = [f"{k}={v}" for k, v in extracted.items()]
        result_str = ", ".join(parts)
    else:
        result_str = str(hint.result)[:200]
    # ... rest unchanged
```

- [ ] **Step 5: Add FORMAT_COMPACT to buffer_survival_check.py and turn_lethal_check.py**

```python
# buffer_survival_check.py — add at end, before TEST_CASES
def FORMAT_COMPACT(result):
    if isinstance(result, dict):
        if result.get("survives"):
            return f"Survive: YES, {result.get('hp_remaining', '?')}hp left"
        return f"Survive: NO, fatal hit {result.get('fatal_attack', '?')}"
    return str(result)[:80]
```

```python
# turn_lethal_check.py — add at end, before TEST_CASES
def FORMAT_COMPACT(result):
    if isinstance(result, dict):
        d = result.get("decision", "?")
        hp_after = result.get("hp_after_no_block", "?")
        return f"Lethal: {d}, hp_after_no_block={hp_after}"
    return str(result)[:80]
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestFormatCompact tests/test_tool_preprocessor.py -v`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/brain/dynamic_tools.py src/brain/tool_preprocessor.py data/evolution/tools/buffer_survival_check.py data/evolution/tools/turn_lethal_check.py tests/test_tool_lifecycle.py
git commit -m "feat: FORMAT_COMPACT dispatch for compressed tool hints"
```

---

## Task 5: Query tool usage tracking in V2Engine

**Files:**
- Modify: `src/brain/v2_engine.py:110-130` (V2Engine.__init__) + `_agent_loop` (line ~385-470)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for QueryToolRecord**

```python
from dataclasses import dataclass


class TestQueryToolTracking:
    def test_query_tool_record_fields(self):
        from src.brain.v2_engine import QueryToolRecord
        rec = QueryToolRecord(
            tool_name="recall_encounter",
            state_type="monster",
            latency_ms=45.2,
            result_chars=350,
            timestamp=1234567890.0,
        )
        assert rec.tool_name == "recall_encounter"
        assert rec.state_type == "monster"
        assert rec.latency_ms == 45.2
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestQueryToolTracking -v`
Expected: FAIL — QueryToolRecord not defined

- [ ] **Step 3: Add QueryToolRecord + tracking to V2Engine**

In `src/brain/v2_engine.py`:

```python
import time as _time
from dataclasses import dataclass, field

@dataclass(frozen=True)
class QueryToolRecord:
    tool_name: str
    state_type: str
    latency_ms: float
    result_chars: int
    timestamp: float = field(default_factory=_time.time)
```

In `V2Engine.__init__`: add `self._query_tool_records: list[QueryToolRecord] = []`

In `V2Engine._agent_loop`, after query tool execution (~line 450-460), add:

```python
self._query_tool_records.append(QueryToolRecord(
    tool_name=tool_name,
    state_type=state_type_hint,
    latency_ms=tool_latency_ms,
    result_chars=len(result_text),
))
```

Add methods:

```python
def reset_query_telemetry(self) -> None:
    self._query_tool_records.clear()

def get_query_telemetry(self) -> dict:
    if not self._query_tool_records:
        return {}
    by_tool: dict[str, dict] = {}
    for rec in self._query_tool_records:
        if rec.tool_name not in by_tool:
            by_tool[rec.tool_name] = {"calls": 0, "total_chars": 0, "state_types": set()}
        entry = by_tool[rec.tool_name]
        entry["calls"] += 1
        entry["total_chars"] += rec.result_chars
        entry["state_types"].add(rec.state_type)
    return {
        name: {"calls": d["calls"], "total_chars": d["total_chars"],
               "state_types": sorted(d["state_types"])}
        for name, d in by_tool.items()
    }
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestQueryToolTracking -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/v2_engine.py tests/test_tool_lifecycle.py
git commit -m "feat: query tool usage tracking in V2Engine"
```

---

## Task 6: PlanParamBinder

**Files:**
- Create: `src/brain/plan_verifier.py`
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for PlanParamBinder**

```python
class TestPlanParamBinder:
    def test_tier1_params_from_plan(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan, PlannedAction

        plan = CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend"),
                PlannedAction(action_type="card", card_name="Strike"),
                PlannedAction(action_type="potion", potion_index=0),
            ),
            end_turn=True,
        )
        # Minimal GameState mock
        gs = _make_combat_gs(hand_cards=[
            {"name": "Defend", "block": 5, "damage": None, "energy_cost": 1},
            {"name": "Strike", "block": None, "damage": 6, "energy_cost": 1},
        ])
        result = bind_plan_params(plan, gs, required_params={"play_sequence", "num_cards_played", "ends_turn", "has_potion_use"})
        assert result is not None
        assert result["play_sequence"] == ["Defend", "Strike"]
        assert result["num_cards_played"] == 2
        assert result["ends_turn"] is True
        assert result["has_potion_use"] is True

    def test_tier2_params_cross_reference(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan, PlannedAction

        plan = CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend"),
                PlannedAction(action_type="card", card_name="Strike"),
            ),
            end_turn=True,
        )
        gs = _make_combat_gs(hand_cards=[
            {"name": "Defend", "block": 5, "damage": None, "energy_cost": 1},
            {"name": "Strike", "block": None, "damage": 6, "energy_cost": 1},
        ])
        result = bind_plan_params(plan, gs, required_params={"planned_block", "planned_damage", "total_energy_spent"})
        assert result is not None
        assert result["planned_block"] == 5
        assert result["planned_damage"] == 6
        assert result["total_energy_spent"] == 2

    def test_unbindable_param_returns_none(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan
        plan = CombatPlan(actions=(), end_turn=True)
        gs = _make_combat_gs()
        result = bind_plan_params(plan, gs, required_params={"num_shivs"})
        assert result is None  # num_shivs not in bindable set
```

Include a helper `_make_combat_gs()` that creates a minimal mock GameState with SimpleNamespace. (Reuse the pattern from existing `tests/test_tool_preprocessor.py`.)

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestPlanParamBinder -v`
Expected: FAIL — plan_verifier module not found

- [ ] **Step 3: Implement PlanParamBinder**

Create `src/brain/plan_verifier.py`:

```python
"""PlanVerifier: verify combat plans with plan_evaluator tools.

Contains PlanParamBinder (extracts params from CombatPlan + GameState)
and PlanVerifier (runs applicable plan_evaluator tools post-plan).
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from src.brain.planner import CombatPlan
from src.state.game_state import GameState

logger = logging.getLogger(__name__)

# Tier 1: trivially derivable from CombatPlan structure
AUTO_BINDABLE_FROM_PLAN_T1: frozenset[str] = frozenset({
    "play_sequence", "num_cards_played", "ends_turn", "has_potion_use",
})

# Tier 2: requires cross-referencing card names against GameState.hand
AUTO_BINDABLE_FROM_PLAN_T2: frozenset[str] = frozenset({
    "planned_block", "planned_damage", "total_energy_spent",
})

ALL_PLAN_BINDABLE = AUTO_BINDABLE_FROM_PLAN_T1 | AUTO_BINDABLE_FROM_PLAN_T2


def bind_plan_params(
    plan: CombatPlan,
    gs: GameState,
    *,
    required_params: set[str],
) -> dict[str, Any] | None:
    """Bind parameters from CombatPlan + GameState.

    Returns dict of bound params, or None if any required param is unbindable.
    Combines plan-derived params with state-derived params.
    """
    from src.brain.tool_preprocessor import bind_params as bind_state_params

    bindings: dict[str, Any] = {}
    card_actions = [a for a in plan.actions if a.action_type == "card"]

    # Build name→card lookup from hand
    hand_lookup: dict[str, Any] = {}
    for c in gs.hand:
        hand_lookup[c.name] = c

    for pname in required_params:
        # Try plan Tier 1
        if pname in AUTO_BINDABLE_FROM_PLAN_T1:
            bindings[pname] = _bind_plan_t1(pname, plan, card_actions)
            continue
        # Try plan Tier 2
        if pname in AUTO_BINDABLE_FROM_PLAN_T2:
            bindings[pname] = _bind_plan_t2(pname, card_actions, hand_lookup)
            continue
        # Try state binding
        from src.brain.dynamic_tools import AUTO_BINDABLE
        if pname in AUTO_BINDABLE:
            state_result = bind_state_params({pname: {}}, gs)
            if state_result is not None and pname in state_result:
                bindings[pname] = state_result[pname]
                continue
        # Unbindable
        return None

    return bindings


def _bind_plan_t1(pname: str, plan: CombatPlan, card_actions: list) -> Any:
    if pname == "play_sequence":
        return [a.card_name for a in card_actions]
    if pname == "num_cards_played":
        return len(card_actions)
    if pname == "ends_turn":
        return plan.end_turn
    if pname == "has_potion_use":
        return any(a.action_type == "potion" for a in plan.actions)
    return None


def _bind_plan_t2(pname: str, card_actions: list, hand_lookup: dict) -> Any:
    total = 0
    for action in card_actions:
        card = hand_lookup.get(action.card_name)
        if card is None:
            continue  # Card not in hand (e.g., drawn mid-plan)
        if pname == "planned_block":
            total += getattr(card, "block", 0) or 0
        elif pname == "planned_damage":
            total += getattr(card, "damage", 0) or 0
        elif pname == "total_energy_spent":
            total += getattr(card, "energy_cost", 0) or 0
    return total
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestPlanParamBinder -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/plan_verifier.py tests/test_tool_lifecycle.py
git commit -m "feat: PlanParamBinder — extract params from CombatPlan + GameState"
```

---

## Task 7: PlanVerifier + integration

**Files:**
- Modify: `src/brain/plan_verifier.py` (add PlanVerifier class)
- Modify: `src/agent/loop.py` (call PlanVerifier after combat plan)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for PlanVerifier**

```python
class TestPlanVerifier:
    def test_no_applicable_tools_returns_empty(self):
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.planner import CombatPlan

        reg = DynamicToolRegistry(tempfile.mkdtemp())
        verifier = PlanVerifier(reg)
        plan = CombatPlan(actions=(), end_turn=True)
        gs = _make_combat_gs()
        result = verifier.verify(plan, gs, combat_state_type="monster")
        assert result.needs_replan is False
        assert result.warnings == []

    def test_critical_warning_triggers_replan(self):
        from src.brain.plan_verifier import PlanVerifier
        # Create a tool that always returns critical severity
        tool_code = '''
SCHEMA = {
    "name": "test_critical",
    "description": "Always critical.",
    "parameters": {"play_sequence": {"type": "list"}},
}
APPLICABLE_STATES = ["monster", "elite", "boss"]
TOOL_TYPE = "plan_evaluator"

def execute(play_sequence=None, **kwargs):
    return {"severity": "critical", "warning": "Missed lethal!"}

TEST_CASES = [
    {"input": {"play_sequence": []}, "expected_contains": "critical"},
    {"input": {"play_sequence": ["Strike"]}, "expected_contains": "critical"},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_critical.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            verifier = PlanVerifier(reg)
            plan = CombatPlan(actions=(), end_turn=True)
            gs = _make_combat_gs()
            result = verifier.verify(plan, gs, combat_state_type="monster")
            assert result.needs_replan is True
            assert len(result.warnings) == 1
            assert "Missed lethal" in result.warnings[0]
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestPlanVerifier -v`
Expected: FAIL — PlanVerifier not defined

- [ ] **Step 3: Implement PlanVerifier**

Add to `src/brain/plan_verifier.py`:

```python
@dataclass(frozen=True)
class VerificationResult:
    needs_replan: bool
    warnings: list[str]
    hints: list[str]  # Non-critical observations


class PlanVerifier:
    """Post-plan verification using plan_evaluator tools."""

    def __init__(self, registry, *, max_tools: int = 5, timeout_ms: float = 500) -> None:
        self._registry = registry
        self._max_tools = max_tools
        self._timeout_ms = timeout_ms
        self._usage_records: list = []  # ToolUsageRecord compatible

    def verify(self, plan: CombatPlan, gs: GameState, *, combat_state_type: str = "monster") -> VerificationResult:
        """Run applicable plan_evaluator tools against a combat plan."""
        from src.brain.dynamic_tools import classify_tool_runtime_mode
        from src.brain.tool_preprocessor import ToolUsageRecord

        warnings: list[str] = []
        hints: list[str] = []
        budget_start = time.monotonic()
        tools_run = 0

        for name in sorted(self._registry.names()):
            if tools_run >= self._max_tools:
                break
            elapsed_ms = (time.monotonic() - budget_start) * 1000
            if elapsed_ms > self._timeout_ms:
                break

            # Only plan_evaluator tools
            mode = classify_tool_runtime_mode(name, self._registry)
            if mode != "plan_evaluator":
                continue

            tool = self._registry.get(name)
            if tool is None or tool.deactivated:
                continue

            # Check APPLICABLE_STATES
            applicable = tool.schema.get("APPLICABLE_STATES", [])
            if applicable and combat_state_type not in applicable:
                continue

            # Try to bind params
            param_info = self._registry.get_param_info(name)
            if param_info is None:
                continue

            bound = bind_plan_params(plan, gs, required_params=set(param_info.keys()))
            if bound is None:
                continue

            # Execute
            t0 = time.monotonic()
            try:
                result = tool.execute_raw(**bound)
                latency = (time.monotonic() - t0) * 1000
                tools_run += 1

                self._usage_records.append(ToolUsageRecord(
                    tool_name=name, state_type=combat_state_type,
                    success=True, latency_ms=latency,
                ))

                # Classify severity
                if isinstance(result, dict) and result.get("severity") == "critical":
                    warning_msg = result.get("warning", result.get("reason", str(result)))
                    warnings.append(f"[{name}] {warning_msg}")
                elif isinstance(result, dict):
                    hint_msg = result.get("note", result.get("recommendation", str(result)))
                    hints.append(f"[{name}] {hint_msg}")
            except Exception as exc:
                latency = (time.monotonic() - t0) * 1000
                self._usage_records.append(ToolUsageRecord(
                    tool_name=name, state_type=combat_state_type,
                    success=False, latency_ms=latency, error=str(exc),
                ))

        return VerificationResult(
            needs_replan=len(warnings) > 0,
            warnings=warnings,
            hints=hints,
        )

    def reset(self) -> None:
        self._usage_records.clear()

    def get_telemetry_summary(self) -> dict:
        # Same structure as Preprocessor telemetry
        if not self._usage_records:
            return {}
        by_tool: dict[str, dict] = {}
        for rec in self._usage_records:
            if rec.tool_name not in by_tool:
                by_tool[rec.tool_name] = {"runs": 0, "successes": 0, "state_types": set()}
            entry = by_tool[rec.tool_name]
            entry["runs"] += 1
            if rec.success:
                entry["successes"] += 1
            entry["state_types"].add(rec.state_type)
        return {name: {"runs": d["runs"], "successes": d["successes"],
                       "state_types": sorted(d["state_types"])}
                for name, d in by_tool.items()}
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestPlanVerifier -v`
Expected: ALL PASS

- [ ] **Step 5: Integrate PlanVerifier into agent loop**

In `src/agent/loop.py`, after `_generate_combat_plan()` returns a valid plan and `_validate_combat_plan()` passes, add PlanVerifier call. The integration is in the combat execution path — find where plan is used and add:

```python
# After validation passes, before execution:
if self._plan_verifier and replans_remaining > 0:
    vresult = self._plan_verifier.verify(plan, gs, combat_state_type=self._cached_map_node_type or "monster")
    if vresult.needs_replan:
        # Inject warnings as feedback
        warning_text = "Plan verification found critical issues:\n" + "\n".join(vresult.warnings)
        self._v2_combat_conversation.add_user_feedback(warning_text)
        replans_remaining -= 1
        # Trigger re-plan
        plan = await self._v2_engine.generate_combat_plan(self._v2_combat_conversation, is_replan=True)
```

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/brain/plan_verifier.py src/agent/loop.py tests/test_tool_lifecycle.py
git commit -m "feat: PlanVerifier — post-plan verification with plan_evaluator tools"
```

---

## Task 8: Generation quality gates (dedup + param validation + test requirements)

**Files:**
- Modify: `src/brain/dynamic_tools.py:770-836` (register_tool)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write tests for generation gates**

```python
class TestGenerationGates:
    def test_dedup_rejects_similar_name(self):
        with tempfile.TemporaryDirectory() as td:
            # Register first tool
            code1 = _make_tool_code("block_check", ["current_hp", "current_block"])
            reg = DynamicToolRegistry(td)
            result1 = reg.register_tool("block_check", code1)
            assert "SUCCESS" in result1
            # Try registering near-duplicate
            code2 = _make_tool_code("block_check_v2", ["current_hp", "current_block"])
            result2 = reg.register_tool("block_check_v2", code2)
            assert "REJECTED" in result2
            assert "Similar tool" in result2

    def test_missing_applicable_states_rejected(self):
        code = _make_tool_code("no_states_tool", ["current_hp"], include_applicable_states=False)
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("no_states_tool", code)
            assert "REJECTED" in result
            assert "APPLICABLE_STATES" in result

    def test_insufficient_test_cases_rejected(self):
        code = _make_tool_code("one_test_tool", ["current_hp"], num_test_cases=1)
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("one_test_tool", code)
            assert "REJECTED" in result
            assert "test case" in result.lower()

    def test_valid_tool_accepted(self):
        code = _make_tool_code("valid_tool", ["current_hp", "incoming_damage"])
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("valid_tool", code)
            assert "SUCCESS" in result
```

Include helper `_make_tool_code(name, params, include_applicable_states=True, num_test_cases=2)` that generates valid tool code.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestGenerationGates -v`
Expected: FAIL — no dedup/validation logic yet

- [ ] **Step 3: Implement dedup + param validation + test requirements**

In `src/brain/dynamic_tools.py`, add `_check_dedup()`:

```python
def _check_dedup(self, name: str, schema: dict) -> str | None:
    """Check for duplicate tools. Returns rejection message or None."""
    new_words = set(name.split("_"))
    new_params = set(_extract_raw_params(schema).keys())
    new_desc_words = set(schema.get("description", "").lower().split())

    for existing in self._tools.values():
        # Name word overlap
        ex_words = set(existing.name.split("_"))
        if len(new_words) > 0 and len(ex_words) > 0:
            overlap = len(new_words & ex_words) / max(len(new_words), len(ex_words))
            if overlap > 0.8:
                return f"Similar tool already exists: {existing.name} (name overlap {overlap:.0%})"

        # Param overlap
        ex_params = set(_extract_raw_params(existing.schema).keys())
        if new_params and ex_params:
            jaccard = len(new_params & ex_params) / len(new_params | ex_params)
            if jaccard > 0.8:
                return f"Similar tool already exists: {existing.name} (param overlap {jaccard:.0%})"

    return None
```

In `register_tool()`, after test case validation, add:

```python
# Quality gate: APPLICABLE_STATES required
applicable = namespace.get("APPLICABLE_STATES")
if not applicable:
    return "REJECTED: APPLICABLE_STATES is required. Declare which state types this tool applies to."

# Quality gate: minimum 2 test cases with at least 1 assertion
if len(test_cases) < 2:
    return f"REJECTED: Need at least 2 TEST_CASES (got {len(test_cases)})."
assertion_keys = {"expected", "expected_contains", "expected_keys"}
assertion_count = sum(
    1 for tc in test_cases
    if any(k in tc for k in assertion_keys)
    or any(k.startswith("expected_") and k.endswith("_contains") for k in tc)
)
if assertion_count < 1:
    return "REJECTED: At least 1 test case must have an assertion (expected, expected_contains, expected_keys)."

# Quality gate: dedup check
dedup_msg = self._check_dedup(actual_name, schema)
if dedup_msg:
    return f"REJECTED: {dedup_msg}"

# Quality gate: param bindability
# ... classify and check params against AUTO_BINDABLE / ALL_PLAN_BINDABLE
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestGenerationGates -v`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/dynamic_tools.py tests/test_tool_lifecycle.py
git commit -m "feat: generation quality gates — dedup, param validation, test requirements"
```

---

## Task 9: Effectiveness scoring + retirement sweep

**Files:**
- Modify: `src/brain/dynamic_tools.py` (add compute_effectiveness, retirement_sweep, runs tracking)
- Modify: `config.py` (add retirement config vars)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write tests for effectiveness + retirement**

```python
class TestRetirement:
    def test_compute_effectiveness_new_tool(self):
        from src.brain.dynamic_tools import compute_effectiveness
        # New tool: benefit of doubt
        assert compute_effectiveness(usage=0, success=0, runs_since=0) == 1.0

    def test_compute_effectiveness_active_tool(self):
        from src.brain.dynamic_tools import compute_effectiveness
        # 100 uses over 10 runs = usage_rate 10, 100% success
        score = compute_effectiveness(usage=100, success=100, runs_since=10)
        assert score == 10.0

    def test_compute_effectiveness_low_usage(self):
        from src.brain.dynamic_tools import compute_effectiveness
        # 1 use over 10 runs
        score = compute_effectiveness(usage=1, success=1, runs_since=10)
        assert score == 0.1

    def test_retirement_sweep_deactivates_low_score(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("low_usage", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("low_usage", code)
            # Simulate 10 runs with 0 usage
            reg._total_runs = 10
            tool = reg.get("low_usage")
            tool.usage_count = 0
            tool.success_count = 0
            # Run sweep
            actions = reg.retirement_sweep()
            assert len(actions) > 0
            assert tool.deactivated is True

    def test_retirement_two_sweep_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("doomed_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("doomed_tool", code)
            reg._total_runs = 10
            tool = reg.get("doomed_tool")
            tool.usage_count = 0
            tool.success_count = 0
            # First sweep: deactivated
            reg.retirement_sweep()
            assert tool.deactivated is True
            assert (Path(td) / "doomed_tool.py").exists()
            # Second sweep: deleted
            reg._total_runs = 20
            reg.retirement_sweep()
            assert not (Path(td) / "doomed_tool.py").exists()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestRetirement -v`
Expected: FAIL — functions not defined

- [ ] **Step 3: Add config vars**

In `config.py` after evolution section:

```python
# ── Tool Retirement ──────────────────────────────────────────
TOOL_RETIREMENT_SWEEP_INTERVAL = int(os.getenv("STS2_TOOL_RETIREMENT_INTERVAL", "10"))
TOOL_RETIREMENT_MIN_AGE_RUNS = int(os.getenv("STS2_TOOL_RETIREMENT_MIN_AGE", "5"))
TOOL_RETIREMENT_SCORE_THRESHOLD = float(os.getenv("STS2_TOOL_RETIREMENT_THRESHOLD", "0.1"))
TOOL_RETIREMENT_DELETE_AFTER_SWEEPS = int(os.getenv("STS2_TOOL_RETIREMENT_DELETE_AFTER", "2"))
```

- [ ] **Step 4: Implement effectiveness + retirement + runs tracking**

In `src/brain/dynamic_tools.py`:

```python
def compute_effectiveness(usage: int, success: int, runs_since: int) -> float:
    if runs_since == 0:
        return 1.0
    usage_rate = usage / max(1, runs_since)
    success_rate = success / max(1, usage)
    return usage_rate * success_rate
```

Add to `DynamicToolRegistry`:
- `_total_runs: int = 0` field (persisted in tool_stats.json under `"__meta__": {"total_runs": N}`)
- `_retirement_state: dict` loaded from `retirement_state.json`
- `retirement_sweep() -> list[str]` method
- `increment_run_counter()` method (called from agent loop's `reset_for_new_run()`)

Add to `DynamicTool`:
- `creation_run: int = 0` field (set from tool_stats.json at load time, or from `_total_runs` at registration time)

In `save_stats()`: persist `creation_run` per tool + `__meta__.total_runs`
In `load_stats()`: restore `creation_run` per tool + `_total_runs`
In `register_tool()`: set `tool.creation_run = self._total_runs`

`runs_since_creation` in retirement_sweep: `self._total_runs - tool.creation_run`

**Effectiveness normalization for narrow tools**: DEFERRED to v2. Reason: requires tracking per-run state_type encounter counts and correlating with each tool's APPLICABLE_STATES. The Preprocessor telemetry tracks this but only per-run (not accumulated). For v1, the `RETIREMENT_MIN_AGE_RUNS = 5` provides basic protection. Silent-only tools may need manual threshold adjustment if false retirements occur.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_tool_lifecycle.py::TestRetirement -v`
Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/brain/dynamic_tools.py config.py tests/test_tool_lifecycle.py
git commit -m "feat: effectiveness scoring + retirement sweep for dynamic tools"
```

---

## Task 10: Evolution system prompt update

**Files:**
- Modify: `src/brain/evolution_engine.py:43-61` (EVOLUTION_SYSTEM_PROMPT)
- Test: Manual verification (prompt text change)

- [ ] **Step 1: Update EVOLUTION_SYSTEM_PROMPT**

Add to `EVOLUTION_SYSTEM_PROMPT` in `src/brain/evolution_engine.py`:

```python
EVOLUTION_SYSTEM_PROMPT = """\
You are a self-evolving Slay the Spire 2 agent...

[existing content]

TOOL AUTHORING REQUIREMENTS:
- Every tool MUST declare APPLICABLE_STATES = [...] listing which game states it applies to.
  Valid states: monster, elite, boss, map, rest_site, shop, card_reward, card_select, event, hand_select, treasure, relic_select
- Every tool MUST have at least 2 TEST_CASES with at least 1 containing an assertion.
- state_derived tools: ALL parameters must be auto-bindable from game state.
  Available: current_hp, max_hp, current_block, energy, dexterity, strength, incoming_damage, enemies, deck, hand, floor, act, gold, etc.
- plan_evaluator tools: Non-state params must be plan-bindable.
  Available: play_sequence, num_cards_played, ends_turn, has_potion_use, planned_block, planned_damage, total_energy_spent.
- Tools with unbindable parameters will be REJECTED.
- Duplicate tools (similar name or >80% parameter overlap) will be REJECTED."""
```

- [ ] **Step 2: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "feat: update evolution system prompt with tool authoring requirements"
```

---

## Task 11: Promotion candidates + integration wiring

**Files:**
- Modify: `src/brain/dynamic_tools.py` (add promote_candidates to stats)
- Modify: `src/agent/loop.py` (wire PlanVerifier init + reset)
- Test: `tests/test_tool_lifecycle.py`

- [ ] **Step 1: Write test for promotion candidates**

```python
class TestPromotion:
    def test_promote_candidate_high_score(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("star_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("star_tool", code)
            reg._total_runs = 25
            tool = reg.get("star_tool")
            tool.usage_count = 60  # ~2.4 per run
            tool.success_count = 59  # 98% success
            tool.created_at = 0  # old
            stats = reg.stats()
            # Check promote_candidates in stats
            assert "star_tool" in stats.get("promote_candidates", [])
```

- [ ] **Step 2: Implement promotion logic in stats()**

Add to `DynamicToolRegistry.stats()`:

```python
def stats(self) -> dict[str, Any]:
    tool_stats = {
        t.name: {
            "usage_count": t.usage_count,
            "success_count": t.success_count,
            "motivation": t.motivation,
            "deactivated": t.deactivated,
        }
        for t in self._tools.values()
    }
    # Identify promote candidates
    candidates = []
    for t in self._tools.values():
        if t.deactivated:
            continue
        runs_since = max(1, self._total_runs - getattr(t, 'creation_run', 0))
        score = compute_effectiveness(t.usage_count, t.success_count, runs_since)
        success_rate = t.success_count / max(1, t.usage_count)
        if score > 2.0 and runs_since > 20 and success_rate > 0.95:
            candidates.append(t.name)
    tool_stats["promote_candidates"] = candidates
    return tool_stats
```

- [ ] **Step 3: Wire PlanVerifier in agent loop**

In `src/agent/loop.py` `_init_v2()`, add PlanVerifier initialization:

```python
from src.brain.plan_verifier import PlanVerifier
self._plan_verifier = PlanVerifier(self._dynamic_registry) if self._dynamic_registry else None
```

In `reset_for_new_run()`:
```python
if self._plan_verifier:
    self._plan_verifier.reset()
```

- [ ] **Step 4: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/dynamic_tools.py src/agent/loop.py tests/test_tool_lifecycle.py
git commit -m "feat: promotion candidates + PlanVerifier wiring in agent loop"
```

---

## Task 12: Final integration test + cleanup

**Files:**
- Test: `tests/test_tool_lifecycle.py` (add integration test)
- Modify: `docs/superpowers/specs/2026-03-28-tool-lifecycle-design.md` (mark implemented)

- [ ] **Step 1: Write integration test covering full lifecycle**

```python
class TestLifecycleIntegration:
    def test_full_lifecycle_generation_to_retirement(self):
        """Test: generate tool → use via preprocessor → evaluate → retire."""
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)

            # 1. Generate — valid tool accepted
            code = _make_tool_code("lifecycle_test", ["current_hp", "incoming_damage"])
            result = reg.register_tool("lifecycle_test", code)
            assert "SUCCESS" in result
            assert reg.count == 1

            # 2. Generate — duplicate rejected
            code2 = _make_tool_code("lifecycle_test_v2", ["current_hp", "incoming_damage"])
            result2 = reg.register_tool("lifecycle_test_v2", code2)
            assert "REJECTED" in result2

            # 3. Use — tool executes and returns raw result
            tool = reg.get("lifecycle_test")
            raw = tool.execute_raw(current_hp=50, incoming_damage=20)
            assert isinstance(raw, dict)

            # 4. Evaluate — effectiveness score
            score = compute_effectiveness(tool.usage_count, tool.success_count, runs_since=5)
            assert score > 0

            # 5. Retire — low usage tool gets deactivated
            tool.usage_count = 0
            tool.success_count = 0
            reg._total_runs = 10
            actions = reg.retirement_sweep()
            assert tool.deactivated is True
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_tool_lifecycle.py -v`
Expected: ALL PASS

- [ ] **Step 3: Run existing tests for regressions**

Run: `python -m pytest tests/ -v --tb=short`
Expected: ALL PASS (no regressions in existing test files)

- [ ] **Step 4: Commit**

```bash
git add tests/test_tool_lifecycle.py
git commit -m "test: full lifecycle integration test"
```

- [ ] **Step 5: Update CLAUDE.md with tool lifecycle section**

Add to the development phases section and important patterns in CLAUDE.md.

- [ ] **Step 6: Final commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with tool lifecycle system"
```
