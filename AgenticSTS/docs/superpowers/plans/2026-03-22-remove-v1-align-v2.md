# Remove V1 Memory + Brain, Align to V2-Only Architecture

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove all V1 memory and brain code, making V2 the only decision and memory path. Eliminate feature flags, dead code, and V1 fallbacks.

**Architecture:** V2Engine (tool-use agent) becomes the sole decision engine. V2 HCM stores (combat/route/deck/guides) become the sole memory system. The shared `RuleStore` + `StrategyRule` are preserved (V2 retriever uses them). Post-run LLM calls (distillation, discovery, consolidation) migrate from `LLMReasoner.call_raw()` to a thin V2Backend adapter.

**Scope change:** This explicitly removes non-Anthropic LLM support (Ollama, OpenAI-compatible backends). V2Engine and V2Backend are Anthropic-only by design. Multi-provider support is a separate future task (P1.5 in CLAUDE.md roadmap via new `OpenAIToolBackend`). The old V1 backends were never tested with V2 and would not work.

**Tech Stack:** Python 3.11+, Anthropic SDK, Pydantic, frozen dataclasses

---

## File Structure

### Files to DELETE (V1-only, no V2 usage)

| File | Reason |
|------|--------|
| `src/brain/reasoner.py` (~1140 lines) | V1 LLM backends (Ollama/OpenAI/Anthropic), `LLMReasoner`. `LLMDecision` extracted first. |
| `src/brain/strategy_selector.py` (~124 lines) | V1 decision router. `DecisionSource` extracted first. |
| `src/memory/episode_store.py` (~150 lines) | V1 Layer 1 episodes. Replaced by V2 combat_store/route_store/card_build_store. |
| `src/memory/reflection_store.py` (~170 lines) | V1 Layer 2 reflections. V2 does not use reflections. |
| `src/memory/extractor.py` (~200 lines) | V1 episode extractor. Replaced by V2 domain extractors. |
| `src/memory/reflector.py` (~150 lines) | V1 reflection generator. Replaced by V2 guide consolidation. |
| `src/memory/models.py` (~289 lines) | V1 models. `StrategyRule` moved to `models_v2.py`, rest deleted. |
| `src/brain/prompts/distill.py` | V1 distillation prompt (takes `RunReflection`). Rewritten for V2 data. |
| `src/brain/prompts/reflection.py` (~83 lines) | V1 reflection prompt builder. Only used by `reflector.py` and batch reflection task. |
| `scripts/test_reflection.py` | Tests V1 reflection pipeline. |
| `scripts/test_phase3_memory.py` | Tests V1 episode extraction. |
| `scripts/test_prompts_offline.py` | V1-era Ollama offline tester, imports `SYSTEM_PROMPT`. |

### Files to CREATE

| File | Purpose |
|------|---------|
| `src/brain/models.py` (~40 lines) | Shared `LLMDecision` + `DecisionSource` extracted from deleted V1 files. |
| `src/brain/llm_caller.py` (~60 lines) | Thin `call_raw(system, prompt, think)` adapter wrapping V2Backend. Replaces `LLMReasoner.call_raw()` for post-run callers. |

### Files to MODIFY

| File | Changes |
|------|---------|
| `src/memory/models_v2.py` | Add `StrategyRule` class (moved from `models.py`). |
| `src/memory/memory_manager.py` | Remove V1 stores (episodes, reflections). Remove `query_for_state()`, `record_episodes()`, `record_reflection()`, `mark_victory()`, V1 maintenance. V2 stores become non-optional. |
| `src/memory/prompt_injector.py` | Remove V1 functions (`format_memory_hints`, `inject_memory_into_prompt`). Keep only V2 functions. |
| `src/memory/__init__.py` | Update exports: remove V1 types, export V2 types. |
| `src/memory/rule_store.py` | Update import: `StrategyRule` from `models_v2` instead of `models`. |
| `src/memory/rule_distiller.py` | Refactor: accept V2 domain data (CombatEpisode/RouteMemory wins vs losses) instead of ReflectionStore. Use `llm_caller.call_raw()` instead of `reasoner.call_raw()`. |
| `src/memory/guide_consolidator.py` | Update: use `llm_caller.call_raw()` instead of `reasoner.call_raw()`. |
| `src/brain/prompts/distill.py` | Rewrite: accept V2 domain summaries instead of `RunReflection` objects. |
| `src/brain/prompts/system.py` | Remove `SYSTEM_PROMPT` (V1). Rename `SYSTEM_PROMPT_V2` to `SYSTEM_PROMPT`. |
| `src/brain/v2_engine.py` | Update import: `LLMDecision` from `src.brain.models`. |
| `src/brain/tool_schemas.py` | Remove V1 provider gates if any. |
| `src/agent/loop.py` | Major refactor: remove `_strategy`/`LLMReasoner` init, `_BatchRunShim`, `_retry_llm_with_error()`, V1 decision paths, V1 memory recording, V1 combat fallback, V1 potion LLM path, V1 route plan path. V2Engine is the only LLM path. |
| `src/skills/discovery.py` | Update: use `llm_caller.call_raw()` instead of `LLMReasoner.call_raw()`. |
| `config.py` | Remove: `PROMPT_ARCHITECTURE`, `MEMORY_V2_ENABLED`, V1-only memory configs, legacy Ollama configs. |
| `scripts/inspect_memory.py` | Remove V1 store inspection (`mm.episodes`, `mm.reflections`). Add V2 store stats. Must be updated in same task as MemoryManager cleanup (will crash otherwise). |
| `tests/test_pipeline_fixes.py` | Remove `_BatchRunShim` tests, V1 reflection parsing tests. |
| `tests/test_phase2a_integration.py` | Remove `test_batch_run_shim_in_reflection_pipeline`. |
| `tests/test_phase8_regression.py` | Update `LLMDecision` import from `src.brain.models`. |
| `src/memory/models_v2.py` (cleanup) | Remove vestigial `reflection_hints` field from `WorkingContext` (no longer populated after V1 removal). |
| `CLAUDE.md` | Update architecture section to reflect V2-only design. |

---

## Task 1: Extract shared types to `src/brain/models.py`

**Files:**
- Create: `src/brain/models.py`
- Read: `src/brain/reasoner.py:41-80` (LLMDecision class)
- Read: `src/brain/strategy_selector.py:18-21` (DecisionSource enum)

- [ ] **Step 1: Write test for LLMDecision import from new location**

```python
# tests/test_brain_models.py
from src.brain.models import DecisionSource, LLMDecision

def test_llm_decision_creation():
    d = LLMDecision("play_card", {"card_index": 0}, "test reasoning")
    assert d.action_name == "play_card"
    assert d.params == {"card_index": 0}
    assert d.reasoning == "test reasoning"

def test_decision_source_enum():
    assert DecisionSource.LLM.value == "llm"
    assert DecisionSource.RANDOM.value == "random"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_brain_models.py -v`
Expected: FAIL — `src.brain.models` does not exist

- [ ] **Step 3: Create `src/brain/models.py` with LLMDecision + DecisionSource**

Copy `LLMDecision` class from `reasoner.py:41-80` and `DecisionSource` from `strategy_selector.py:18-21` into the new file. No other dependencies.

```python
"""Shared brain data models used by both V2Engine and the agent loop."""

from __future__ import annotations
from enum import Enum


class DecisionSource(Enum):
    LLM = "llm"
    RANDOM = "random"


class LLMDecision:
    """Parsed LLM response."""

    __slots__ = (
        "action_name",
        "params",
        "reasoning",
        "raw_text",
        "prompt_text",
        "latency_ms",
        "tokens_used",
    )

    def __init__(
        self,
        action_name: str,
        params: dict | None = None,
        reasoning: str = "",
        raw_text: str = "",
        prompt_text: str = "",
        latency_ms: float = 0.0,
        tokens_used: int = 0,
    ) -> None:
        self.action_name = action_name
        self.params = params or {}
        self.reasoning = reasoning
        self.raw_text = raw_text
        self.prompt_text = prompt_text
        self.latency_ms = latency_ms
        self.tokens_used = tokens_used

    def __repr__(self) -> str:
        return f"LLMDecision({self.action_name!r}, params={self.params})"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_brain_models.py -v`
Expected: PASS

- [ ] **Step 5: Update all imports of LLMDecision and DecisionSource**

Change these imports across the codebase:
- `src/brain/v2_engine.py`: `from src.brain.reasoner import LLMDecision` → `from src.brain.models import LLMDecision`
- `src/agent/loop.py`: `from src.brain.reasoner import LLMDecision, LLMReasoner` → `from src.brain.models import DecisionSource, LLMDecision` (remove LLMReasoner import later)
- `src/agent/loop.py`: `from src.brain.strategy_selector import DecisionSource, StrategySelector` → remove (DecisionSource now from models)

- [ ] **Step 6: Commit**

```bash
git add src/brain/models.py tests/test_brain_models.py
git commit -m "refactor: extract LLMDecision + DecisionSource to shared brain/models.py"
```

---

## Task 2: Create `src/brain/llm_caller.py` — V2Backend adapter for post-run LLM calls

**Files:**
- Create: `src/brain/llm_caller.py`
- Read: `src/brain/v2_backend.py` (V2Backend API)

Post-run callers (guide_consolidator, rule_distiller, discovery) all call `reasoner.call_raw(system, prompt, think=True) -> (text, latency_ms, tokens)`. We need a drop-in replacement wrapping V2Backend.

- [ ] **Step 1: Write test for call_raw adapter**

```python
# tests/test_llm_caller.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

@pytest.mark.asyncio
async def test_call_raw_returns_tuple():
    """call_raw returns (text, latency_ms, tokens) tuple."""
    from src.brain.llm_caller import call_raw
    # Mock the V2Backend
    with patch("src.brain.llm_caller._get_or_create_backend") as mock_get:
        mock_backend = MagicMock()
        mock_backend.acall = AsyncMock(return_value=MagicMock(
            content=[MagicMock(type="text", text="test response")],
            usage=MagicMock(input_tokens=100, output_tokens=50),
        ))
        mock_get.return_value = mock_backend

        text, latency, tokens = await call_raw("system", "prompt", think=True)
        assert text == "test response"
        assert isinstance(latency, float)
        assert tokens > 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_llm_caller.py -v`
Expected: FAIL — module does not exist

- [ ] **Step 3: Implement `src/brain/llm_caller.py`**

Uses the real V2Backend API: `V2Backend()` (no constructor args), `acall(system=, messages=, model=, think=)` returns `anthropic.Message`.

```python
"""Thin LLM calling adapter for post-run analysis tasks.

Wraps V2Backend.acall() to provide the simple call_raw(system, prompt, think) -> (text, latency_ms, tokens)
interface used by guide_consolidator, rule_distiller, and skill discovery.

V2Backend API:
  - Constructor: V2Backend() — no args, reads config for API key/base URL/model
  - Sync: backend.call(system=, messages=, model=, think=, ...) -> anthropic.Message
  - Async: backend.acall(system=, messages=, model=, think=, ...) -> anthropic.Message
"""

from __future__ import annotations

import logging
import time

import config

logger = logging.getLogger(__name__)

_backend = None


def _get_or_create_backend():
    """Lazy-init a V2Backend for post-run LLM calls."""
    global _backend
    if _backend is None:
        from src.brain.v2_backend import V2Backend
        _backend = V2Backend()  # No constructor args — reads from config
    return _backend


async def call_raw(
    system: str,
    prompt: str,
    think: bool = False,
    model: str | None = None,
) -> tuple[str, float, int]:
    """Call LLM and return (response_text, latency_ms, total_tokens).

    Drop-in replacement for the old LLMReasoner.call_raw() interface.
    """
    backend = _get_or_create_backend()
    start = time.monotonic()

    messages = [{"role": "user", "content": prompt}]

    # Use analysis tier model by default for post-run tasks
    use_model = model or config.EVOLUTION_MODEL or config.LLM_ANALYSIS_MODEL

    response = await backend.acall(
        system=system,
        messages=messages,
        model=use_model,
        think=think,
    )

    # Extract text from anthropic.Message response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    latency_ms = (time.monotonic() - start) * 1000
    tokens = (response.usage.input_tokens + response.usage.output_tokens) if response.usage else 0

    return text, latency_ms, tokens


def reset():
    """Reset the cached backend (for testing)."""
    global _backend
    _backend = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_llm_caller.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/llm_caller.py tests/test_llm_caller.py
git commit -m "feat: add llm_caller adapter wrapping V2Backend for post-run LLM calls"
```

---

## Task 3: Move StrategyRule to models_v2.py

**Files:**
- Modify: `src/memory/models_v2.py` (add StrategyRule)
- Modify: `src/memory/rule_store.py` (update import)
- Modify: `src/memory/retriever.py` (verify import — already uses rule_store, not models)
- Modify: `src/memory/memory_manager.py` (update import)

- [ ] **Step 1: Copy StrategyRule class from `models.py:170-261` to `models_v2.py`**

Append the `StrategyRule` frozen dataclass to the end of `models_v2.py`. Include the `_new_id()` and `_now()` helpers if not already present (check — models_v2.py may have its own).

- [ ] **Step 2: Update imports in rule_store.py**

```python
# Before:
from src.memory.models import StrategyRule
# After:
from src.memory.models_v2 import StrategyRule
```

- [ ] **Step 3: Update imports in memory_manager.py**

```python
# Before:
from src.memory.models import EpisodeCase, MemoryContext, RunReflection, StrategyRule
# After (temporary — EpisodeCase/MemoryContext/RunReflection removed in Task 6):
from src.memory.models_v2 import StrategyRule
```

- [ ] **Step 4: Run existing tests to verify nothing broke**

Run: `python -m pytest tests/ -v --tb=short -x`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py src/memory/rule_store.py src/memory/memory_manager.py
git commit -m "refactor: move StrategyRule to models_v2.py (shared by V2 retriever)"
```

---

## Task 4: Refactor rule_distiller to use V2 domain data

**Files:**
- Modify: `src/memory/rule_distiller.py`
- Modify/Rewrite: `src/brain/prompts/distill.py`
- Test: `tests/test_rule_distiller_v2.py`

Currently `rule_distiller.distill_rules()` takes a `ReflectionStore` and compares winning vs losing `RunReflection` text. We refactor it to compare winning vs losing run summaries built from V2 domain stores (CombatEpisode, RouteMemory, CardBuildMemory).

- [ ] **Step 1: Write test for refactored distiller**

```python
# tests/test_rule_distiller_v2.py
import pytest
from unittest.mock import AsyncMock, patch
from src.memory.rule_distiller import distill_rules_v2

@pytest.mark.asyncio
async def test_distill_with_empty_data():
    """Empty domain data returns no rules."""
    rules = await distill_rules_v2(
        winning_summaries=[],
        losing_summaries=[],
        llm_caller=AsyncMock(),
    )
    assert rules == []

@pytest.mark.asyncio
async def test_distill_produces_rules():
    """Non-empty data produces StrategyRule objects."""
    mock_caller = AsyncMock(return_value=(
        '[{"rule_text": "Test rule", "context": "combat", "confidence": 0.6}]',
        100.0, 500,
    ))
    rules = await distill_rules_v2(
        winning_summaries=["Won vs Kin Priest, HP 50->35, strong scaling"],
        losing_summaries=["Lost vs Kin Priest, HP 50->0, no block"],
        llm_caller=mock_caller,
    )
    assert len(rules) >= 1
    assert rules[0].rule_text == "Test rule"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_rule_distiller_v2.py -v`

- [ ] **Step 3: Rewrite `src/brain/prompts/distill.py`**

Replace the prompt builder to accept string summaries (not `RunReflection` objects):

```python
"""Distillation prompt: extracts strategy rules from win/loss comparison.

V2: accepts run summaries built from domain stores instead of RunReflection objects.
"""

def build_distill_prompt(
    winning_summaries: list[str],
    losing_summaries: list[str],
) -> str:
    """Build a distillation prompt comparing winning vs losing run summaries."""
    parts = [
        "Analyze these winning vs losing Slay the Spire 2 runs and extract",
        "reusable strategy rules that explain what winners did differently.",
        "",
        "## Winning Runs",
    ]
    for i, s in enumerate(winning_summaries, 1):
        parts.append(f"\n### Win #{i}\n{s}")

    parts.append("\n## Losing Runs")
    for i, s in enumerate(losing_summaries, 1):
        parts.append(f"\n### Loss #{i}\n{s}")

    parts.append("""
## Instructions
Extract 1-5 strategy rules. For each rule, output JSON:
```json
[
  {"rule_text": "...", "context": "combat|map|event|rest|reward|all", "confidence": 0.5}
]
```
Rules should be specific and actionable. Confidence 0.5 = unverified hypothesis.""")

    return "\n".join(parts)
```

- [ ] **Step 4: Rewrite `src/memory/rule_distiller.py`**

Replace `distill_rules()` with `distill_rules_v2()` that:
1. Accepts `winning_summaries: list[str]` and `losing_summaries: list[str]`
2. Uses `llm_caller.call_raw()` instead of `reasoner.call_raw()`
3. Returns `list[StrategyRule]`

Also add a helper `build_run_summary()` that converts V2 domain data (combat episodes, route memories, card builds for a run) into a text summary.

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_rule_distiller_v2.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory/rule_distiller.py src/brain/prompts/distill.py tests/test_rule_distiller_v2.py
git commit -m "refactor: rule_distiller uses V2 domain data instead of V1 reflections"
```

---

## Task 5: Update post-run callers to use llm_caller

**Files:**
- Modify: `src/memory/guide_consolidator.py` (3 call sites)
- Modify: `src/skills/discovery.py` (1 call site)

- [ ] **Step 1: Update guide_consolidator.py**

Replace all 3 occurrences of `await reasoner.call_raw(system, prompt, think=True)` with:

```python
from src.brain.llm_caller import call_raw as llm_call_raw
# ...
raw, _latency, _tokens = await llm_call_raw(system, prompt, think=True)
```

Update function signature: `consolidate_guides(memory, reasoner)` → `consolidate_guides(memory)` (no reasoner needed).

- [ ] **Step 2: Update discovery.py**

Replace `reasoner.call_raw()` with `llm_call_raw()`. Update function signature to remove `reasoner` parameter.

- [ ] **Step 3: Run existing tests**

Run: `python -m pytest tests/ -v --tb=short -x`
Expected: PASS (or test updates needed for changed signatures)

- [ ] **Step 4: Commit**

```bash
git add src/memory/guide_consolidator.py src/skills/discovery.py
git commit -m "refactor: guide_consolidator and discovery use llm_caller instead of LLMReasoner"
```

---

## Task 6: Migrate EvolutionEngine stats from reflections to V2 stores

**Files:**
- Modify: `src/brain/evolution_engine.py` (lines 310-365)
- Test: `tests/test_evolution_engine.py` (update stats tests)

`EvolutionEngine.get_performance_stats()` currently reads `self._memory.reflections` for `win_rate`, `floor_progress`, `recent_runs`, `death_causes`. This MUST be migrated BEFORE deleting reflections.

**Data source migration:**
- `self._memory.reflections` -> `self._memory.card_build_store` (CardBuildMemory has `victory`, `final_floor`, `character`, `timestamp` per run)
- `death_causes`: query last `CombatEpisode` per losing run from `self._memory.combat_store` (has `enemy_key`, `hp_before`, `hp_after`)
- `recent_runs` summary: build from CardBuildMemory fields (no `reflection_text`, use archetype + top cards instead)

- [ ] **Step 1: Write test for V2-based stats**

```python
# tests/test_evolution_stats_v2.py
from unittest.mock import MagicMock
from src.brain.evolution_engine import EvolutionEngine

def test_win_rate_from_card_builds():
    """win_rate computed from card_build_store instead of reflections."""
    mock_memory = MagicMock()
    mock_memory.card_build_store.get_all.return_value = [
        MagicMock(victory=True, character="Regent"),
        MagicMock(victory=False, character="Regent"),
        MagicMock(victory=True, character="Regent"),
    ]
    engine = EvolutionEngine.__new__(EvolutionEngine)
    engine._memory = mock_memory
    engine._skill_library = None
    result = engine._get_performance_stats("win_rate", character="Regent")
    assert "66%" in result or "2W/1L" in result
```

- [ ] **Step 2: Run test — should fail (still uses reflections)**

- [ ] **Step 3: Refactor `get_performance_stats()` in evolution_engine.py**

Replace `self._memory.reflections` access with:
```python
# Get run data from card_build_store
card_builds = self._memory.card_build_store
if card_builds is None:
    return "Card build store not available."
all_builds = card_builds.get_all()

# Filter by character if specified
if character:
    all_builds = [b for b in all_builds if b.character == character]

if metric == "win_rate":
    wins = [b for b in all_builds if b.victory]
    losses = [b for b in all_builds if not b.victory]
    total = len(wins) + len(losses)
    if total == 0:
        return "No run data available yet."
    rate = len(wins) / total
    return f"Win rate: {rate:.0%} ({len(wins)}W/{len(losses)}L out of {total} runs)"

if metric == "floor_progress":
    floors = [b.final_floor for b in all_builds]
    if floors:
        return f"Floor progress: avg={sum(floors)/len(floors):.1f}, max={max(floors)}, runs={len(floors)}"
    return "No floor data available."

if metric == "recent_runs":
    recent = sorted(all_builds, key=lambda b: b.timestamp, reverse=True)[:5]
    lines = ["Recent runs:"]
    for b in recent:
        outcome = "WIN" if b.victory else "LOSS"
        top_cards = ", ".join(n for n, _ in b.card_play_counts[:3])
        lines.append(f"  {outcome} floor {b.final_floor} ({b.character}/{b.archetype}): {top_cards}")
    return "\n".join(lines)

if metric == "death_causes":
    losses = [b for b in all_builds if not b.victory][:5]
    if not losses:
        return "No defeats recorded."
    combat_store = self._memory.combat_store
    lines = ["Recent defeats:"]
    for b in losses:
        # Find last combat for this run
        enemy = "unknown"
        if combat_store:
            run_combats = [e for e in combat_store.get_all() if e.run_id == b.run_id and not e.won]
            if run_combats:
                enemy = run_combats[-1].enemy_key
        lines.append(f"  Floor {b.final_floor} ({b.character}): died to {enemy}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test — should pass**

- [ ] **Step 5: Commit**

```bash
git add src/brain/evolution_engine.py tests/test_evolution_stats_v2.py
git commit -m "refactor: evolution stats use V2 card_build_store instead of V1 reflections"
```

---

## Task 7: Remove V1 memory system

**Files:**
- Delete: `src/memory/models.py`
- Delete: `src/memory/episode_store.py`
- Delete: `src/memory/reflection_store.py`
- Delete: `src/memory/extractor.py`
- Delete: `src/memory/reflector.py`
- Modify: `src/memory/memory_manager.py` (major cleanup)
- Modify: `src/memory/prompt_injector.py` (remove V1 functions)
- Modify: `src/memory/__init__.py` (update exports)

- [ ] **Step 1: Clean memory_manager.py**

Remove:
- Import of `EpisodeStore`, `ReflectionStore`, `EpisodeCase`, `MemoryContext`, `RunReflection`
- Import of `_hp_bucket` from extractor
- `_state_features()`, `_state_tags()`, `_context_for_state_type()` helper functions
- V1 store initialization: `self.episodes`, `self.reflections` (keep `self.rules`)
- `query_for_state()` method
- `record_episodes()`, `record_reflection()`, `mark_victory()` methods
- `_trim_to_budget()` static method
- V1 save paths in `save_all()`: remove `self.episodes.save()` and `self.reflections.save()`
- V1 stats in `stats()`: remove `episodes`, `reflections` keys
- `maintenance()`: remove `self.reflections.prune_stale()`, keep `self.rules.deactivate_unverified()`
- `_v2_enabled` flag — V2 is always enabled

Make V2 stores non-optional (remove None checks, remove `_init_v2_stores` conditional).

- [ ] **Step 1b: Clean WorkingContext in models_v2.py**

Remove the vestigial `reflection_hints` field from `WorkingContext` (no longer populated after V1 removal). Update `prompt_injector.py` to remove the `reflection_hints` section rendering.

- [ ] **Step 1c: Update inspect_memory.py**

MUST be done in this task (not deferred to Task 9). After MemoryManager loses `self.episodes` and `self.reflections`, `inspect_memory.py` will crash with `AttributeError`. Remove V1 store inspection, add V2 store stats.

- [ ] **Step 2: Clean prompt_injector.py**

Remove:
- `from src.memory.models import MemoryContext`
- `format_memory_hints()` function
- `inject_memory_into_prompt()` function
- `_MEMORY_HEADER` constant

Keep:
- `format_working_context()` (V2)
- `inject_working_context_into_prompt()` (V2)
- `_insert_before_task()` (shared helper)

- [ ] **Step 3: Update `src/memory/__init__.py`**

```python
"""Memory subpackage: V2 HCM (Hierarchical Categorical Memory) system.

- Domain stores: combat episodes, route memories, card builds
- Consolidated guides: LLM-generated tactical advice
- Strategy rules: cross-run distilled rules with self-verification
- Short-term memory: mutable trackers within a run
"""

from src.memory.memory_manager import MemoryManager
from src.memory.models_v2 import (
    CardBuildMemory,
    CombatEpisode,
    CombatGuide,
    DeckGuide,
    RouteGuide,
    RouteMemory,
    StrategyRule,
    WorkingContext,
)
from src.memory.prompt_injector import format_working_context, inject_working_context_into_prompt
from src.memory.rule_store import RuleStore

__all__ = [
    "CardBuildMemory",
    "CombatEpisode",
    "CombatGuide",
    "DeckGuide",
    "MemoryManager",
    "RouteGuide",
    "RouteMemory",
    "RuleStore",
    "StrategyRule",
    "WorkingContext",
    "format_working_context",
    "inject_working_context_into_prompt",
]
```

- [ ] **Step 4: Clean V1-dependent tests BEFORE deleting V1 files**

Must be done in this task to avoid broken intermediate state:
- `tests/test_pipeline_fixes.py`: remove `_BatchRunShim` tests, V1 reflection parsing tests
- `tests/test_phase2a_integration.py`: remove `test_batch_run_shim_in_reflection_pipeline`
- `scripts/test_reflection.py`: delete entirely
- `scripts/test_phase3_memory.py`: delete entirely

- [ ] **Step 5: Delete V1-only memory files**

```bash
rm src/memory/models.py
rm src/memory/episode_store.py
rm src/memory/reflection_store.py
rm src/memory/extractor.py
rm src/memory/reflector.py
```

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/ -v --tb=short`
Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add -A src/memory/
git commit -m "refactor: remove V1 memory system (episodes, reflections, extractor)"
```

---

## Task 8: Remove V1 brain + decision path from agent loop

This is the largest task. The agent loop has interleaved V1/V2 code paths.

**Files:**
- Modify: `src/agent/loop.py` (major cleanup)
- Delete: `src/brain/reasoner.py`
- Delete: `src/brain/strategy_selector.py`
- Modify: `src/brain/prompts/system.py`

- [ ] **Step 1: Remove V1 system prompt**

In `src/brain/prompts/system.py`:
- Delete `SYSTEM_PROMPT` (the large V1 prompt)
- Rename `SYSTEM_PROMPT_V2` → `SYSTEM_PROMPT`
- Update all references

- [ ] **Step 2: Clean agent loop imports**

In `src/agent/loop.py`, replace:
```python
from src.brain.reasoner import LLMDecision, LLMReasoner
from src.brain.strategy_selector import DecisionSource, StrategySelector
```
With:
```python
from src.brain.models import DecisionSource, LLMDecision
```

- [ ] **Step 3: Remove `_strategy` from AgentLoop.__init__**

Remove:
- `strategy: StrategySelector | None = None` parameter
- `self._strategy` attribute and its initialization
- `self._reasoner` references
- The V1 `LLMReasoner()` / `StrategySelector(reasoner)` construction

V2Engine init (`_init_v2()`) becomes unconditional (no `PROMPT_ARCHITECTURE` check):
```python
if config.LLM_PROVIDER == "anthropic" and use_llm:
    self._init_v2()
```

- [ ] **Step 4: Remove V1 non-combat decision path**

In `_decide()` (around line 2186), remove the entire V1 block:
```python
if self._use_llm and self._strategy and not self._v2_engine:
    # ... ~80 lines of V1 decision + 3-stage retry ...
```

The V2 block (around line 2139) remains as the only LLM path. The mechanical fallback below it remains.

- [ ] **Step 5: Remove V1 combat plan path**

In `_generate_combat_plan()` (around line 2640), remove any remaining V1 code. The V2 `V2Engine.generate_combat_plan()` is the only path.

Also remove V1 combat-related methods:
- `_handle_combat_single_card_v1()` if it exists
- Any `self._strategy` usage in combat paths

- [ ] **Step 6: Clean post-run pipeline**

In `_post_run_memory_update()` (line 1053):
- Remove: `from src.memory.extractor import extract_episodes`
- Remove: `from src.memory.reflector import generate_reflection`
- Remove: V1 episode extraction + recording
- Remove: `self._memory.mark_victory()` call
- Remove: sync reflection generation path
- Remove: `self._strategy`/`reasoner` access for post-run
- Keep: V2 HCM extraction (`_post_run_hcm_extraction()`)
- Keep: guide consolidation (update to not pass reasoner)
- Keep: rule distillation (update to use new V2 API)
- Keep: batch API (update to remove reflection task)
- Keep: evolution engine post-run

Updated flow:
```python
async def _post_run_memory_update(self):
    # 1. V2 HCM extraction (combat/route/deck)
    self._post_run_hcm_extraction()

    # 2. Rule distillation (every N runs, uses V2 domain data)
    self._memory.increment_run_count()
    if self._memory.should_distill:
        await self._distill_rules_from_v2_data()

    # 3. Guide consolidation (every N runs)
    self._memory.increment_consolidation_count()
    if self._memory.should_consolidate:
        await self._consolidate_guides()

    # 4. Save all
    self._memory.save_all()
```

- [ ] **Step 7: Update batch.py submission + pending batch processing**

In `_submit_post_run_batch()`:
- Remove reflection batch task (no more `build_reflection_prompt`)
- Refactor distillation batch task: use V2 domain data (`build_run_summary()` from Task 4) instead of `self._memory.reflections.get_victory_reflections()`. This is the same data source as the sync path in Task 4.
- Keep discovery task (uses `self._run_state` directly, no V1 dependency)
- Delete `_BatchRunShim` class (~20 lines) — only existed for V1 reflection parsing

In `_check_pending_batches()`:
- Remove the `"reflect-"` result processing branch (lines ~1279-1291)
- Add graceful skip for unknown/old batch task types (pending batches from before migration)
- Keep distillation and discovery result processing

- [ ] **Step 8: Remove `_build_decision_context()` V1 fallback**

In `_build_decision_context()` (line 1774):
- Remove the V1 fallback path (`query_for_state` + `memory_hints`)
- Only use V2 `query_for_decision()` → `working_context`

- [ ] **Step 9: Migrate route plan to llm_caller**

`_generate_route_plan()` (around line 2818) uses `self._strategy.call_raw(system, prompt, think=False, call_type="route_plan")`. Replace with `llm_caller.call_raw(system, prompt, think=False)`. Note: `call_type` parameter used for session logging will be lost — add optional `call_type` to `llm_caller.call_raw()` if logging is important.

- [ ] **Step 10: Migrate potion check to V2 or remove**

`_check_potion_use()` / `_maybe_use_potion()` (around line 2707) uses `self._strategy.call_llm()` for potion decisions. V2 combat plans already include potions inline (`type: "potion"` plan items). Decision required:
- **Option A** (recommended): Remove the pre-round potion LLM call entirely. V2 combat plans handle potions. This simplifies the code.
- **Option B**: Convert to `llm_caller.call_raw()` if pre-round potion check adds value.

- [ ] **Step 11: Delete `_retry_llm_with_error()` method**

This method (around line 3042) uses `self._strategy.reasoner.build_prompt()` and `self._strategy.call_llm()`. V2Engine handles its own retries internally (nudge messages in the agent loop). Delete the entire method.

- [ ] **Step 12: Remove remaining `self._strategy` references**

Grep for `self._strategy` and remove:
- Boss search logger wiring (`self._strategy.reasoner.set_session_logger`)
- Any other references

- [ ] **Step 13: Clean V1-dependent tests BEFORE deleting brain files**

- `tests/test_phase8_regression.py`: update `from src.brain.reasoner import LLMDecision` -> `from src.brain.models import LLMDecision`
- `scripts/test_prompts_offline.py`: delete entirely (V1 Ollama offline tester)

- [ ] **Step 14: Delete V1 brain files**

```bash
rm src/brain/reasoner.py
rm src/brain/strategy_selector.py
rm src/brain/prompts/reflection.py
```

- [ ] **Step 15: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: PASS

- [ ] **Step 16: Commit**

```bash
git add -A
git commit -m "refactor: remove V1 brain (reasoner, strategy_selector) — V2Engine is the only path"
```

---

## Task 9: Config cleanup

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Remove V1 config vars**

Remove:
```python
# PROMPT_ARCHITECTURE — V2 is always active
PROMPT_ARCHITECTURE = os.getenv("STS2_PROMPT_ARCH", "v1")

# MEMORY_V2_ENABLED — V2 is always active
MEMORY_V2_ENABLED = os.getenv("STS2_MEMORY_V2_ENABLED", "true").lower() in ("true", "1", "yes")

# V1 memory capacities (no longer used)
EPISODE_CAPACITY = 500
REFLECTION_CAPACITY = 100
MEMORY_DECAY_HALF_LIFE = 48.0
MEMORY_MAX_INJECTION_TOKENS = 400
MEMORY_MIN_FEATURE_OVERLAP = 2

# Legacy Ollama config (V1 only)
LLM_NUM_CTX = int(os.getenv("STS2_NUM_CTX", "65536"))
LLM_THINK_BUDGET = int(os.getenv("STS2_THINK_BUDGET", "16384"))
```

Keep:
- All V2 memory configs
- Model routing configs
- Rule configs (`RULE_CAPACITY`, `RULE_VERIFICATION_THRESHOLD`, `DISTILL_EVERY_N_RUNS`)
- LLM provider + model configs (even non-Anthropic, for future multi-provider)

- [ ] **Step 2: Remove stale references to deleted config vars**

Search codebase for `config.PROMPT_ARCHITECTURE`, `config.MEMORY_V2_ENABLED`, `config.EPISODE_CAPACITY`, etc. and remove.

- [ ] **Step 3: Run tests**

Run: `python -m pytest tests/ -v --tb=short`

- [ ] **Step 4: Commit**

```bash
git add config.py
git commit -m "chore: remove V1 config flags (PROMPT_ARCHITECTURE, MEMORY_V2_ENABLED, V1 capacities)"
```

---

## ~~Task 9 (REMOVED)~~: Test cleanup merged into Tasks 7 and 8

> Test cleanup was merged into Tasks 7 Step 4 and Task 8 Step 13 to avoid broken intermediate states. No separate task needed.

---

## Task 10: Update V1 data files (optional cleanup)

**Files:**
- Data: `data/memory/episodes.jsonl` (V1)
- Data: `data/memory/reflections.jsonl` (V1)
- Data: `data/memory/distill_counter.json` (shared)

- [ ] **Step 1: Note V1 data files**

The V1 data files (`episodes.jsonl`, `reflections.jsonl`) will no longer be read. They can be left in place (harmless) or archived. Do NOT delete — they contain historical data.

- [ ] **Step 2: Verify V2 data files unaffected**

```bash
ls -la data/memory/v2/
```
Expected: `combat_episodes.jsonl`, `route_memories.jsonl`, `card_builds.jsonl`, `guides.json` intact.

---

## Task 11: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update architecture section**

Remove all V1 references:
- "V1: stateless one-shot prompts" descriptions
- "V1 3-layer" memory references
- `PROMPT_ARCHITECTURE` / `STS2_PROMPT_ARCH` config docs
- `MEMORY_V2_ENABLED` config docs
- V1 file listings (reasoner.py, strategy_selector.py, episode_store.py, etc.)
- "V1 preserved as fallback" language

Update:
- Memory section: describe V2 HCM as the sole memory system
- Brain section: V2Engine as the sole decision engine
- Config section: remove V1 config vars
- File tree: remove deleted files, update remaining

- [ ] **Step 2: Update memory project files**

Update `~/.claude/projects/D--code-AgenticSTS/memory/project_v2_architecture.md`:
- Remove "V1 preserved as fallback" note
- Mark V2 as the sole architecture

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for V2-only architecture (V1 removed)"
```

---

## Dependency Graph

```
Task 1 (extract shared types)     ─┐
Task 2 (llm_caller: V2Backend)    ─┤─→ Task 5 (update callers)
Task 3 (move StrategyRule)         ─┘─→ Task 4 (refactor distiller)
                                            ↓
                                   Task 6 (evolution stats migration)
                                            ↓
                                   Task 7 (remove V1 memory + clean V1-dependent tests)
                                            ↓
                                   Task 8 (remove V1 brain + clean V1-dependent tests)
                                            ↓
                                   Task 9 (config cleanup)
                                            ↓
                                   Task 10 (data files)
                                            ↓
                                   Task 11 (docs)
```

Tasks 1-3 can be parallelized. Tasks 4-5 can be parallelized after their deps. Tasks 6+ are sequential.

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Loop.py is 3000+ lines — easy to miss V1 references | Grep for `_strategy`, `reasoner`, `query_for_state`, `MemoryContext`, `EpisodeCase`, `ReflectionStore` after cleanup |
| Batch API processes old pending batches with V1 format | Add graceful skip for "reflect-" task type in `_check_pending_batches` |
| Rule distillation quality may change with V2 data | V2 domain data is richer (combat rounds, route nodes) — likely improvement |
| Post-run callers expect `reasoner.call_raw()` signature | `llm_caller.call_raw()` wraps `V2Backend.acall()` with identical return signature |
| V1 data files on disk | Leave in place — harmless, preserves history |
| Potion LLM check uses V1 `self._strategy.call_llm()` | Removed entirely — V2 combat plans handle potions inline |
| `inspect_memory.py` crashes after MemoryManager changes | Updated in Task 7 (same task as MemoryManager cleanup) |
| `maintenance()` calls removed `self.reflections` | Clean in Task 7 — keep only rule deactivation |
| Test files import from deleted V1 modules | Cleaned in Tasks 7 and 8 (same task as V1 deletion) — no broken intermediate states |
| `_BatchRunShim` orphaned after reflection removal | Deleted in Task 8 |
| EvolutionEngine reads reflections for stats | Migrated to V2 stores in Task 6 (BEFORE reflections deleted in Task 7) |
| Non-Anthropic LLM support removed | Deliberate scope change — documented in plan Context, planned for P1.5 via new backend |

## Estimated Scope

- ~2500 lines deleted
- ~250 lines created (models.py, llm_caller.py, evolution stats refactor)
- ~500 lines modified (memory_manager, loop, config, prompts)
- Net: **~1750 lines removed**
