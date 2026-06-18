# Thinking Tiered Strategy Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Disable thinking for tool_use calls (gameplay) to avoid proxy.example.com proxy stripping tool_use blocks, keep thinking for text-only post-run analysis, remove dead circuit breaker code.

**Architecture:** proxy.example.com proxy drops tool_use blocks when response contains multiple content blocks (text + tool_use). This wastes ~95% of tokens on retries. Fix by disabling thinking/effort params on all tool_use paths (V2Engine, EvolutionEngine), keeping them on text-only paths (call_raw). Strip proxy-injected `<thinking>` tags from text responses. Remove circuit breaker (never triggers — proxy silently drops blocks instead of erroring).

**Tech Stack:** Python, Anthropic SDK

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `config.py:68-87` | Modify | Remove unused thinking config vars, keep `LLM_THINK_TYPE` + `LLM_THINK_EFFORT_ANALYSIS` + `LLM_THINK_BUDGET_ANALYSIS` |
| `src/brain/v2_backend.py:70-71,162-240` | Modify | Remove circuit breaker, simplify thinking logic |
| `src/brain/v2_engine.py:118-119,175-215,417-418,490-492` | Modify | Remove thinking from `_get_v2_tier` and `_agent_loop` |
| `src/brain/llm_caller.py:31-66` | Modify | Add effort param, strip `<thinking>` tags from proxy |
| `src/brain/evolution_engine.py:350-351` | Modify | Disable thinking for tool_use evolution calls |
| `src/brain/batch.py:173,182` | Modify | Remove `LLM_THINK_MODE` ref, keep budget for Batch API |
| `scripts/run_agent.py:89` | Modify | Replace `LLM_THINK_MODE` in startup log |
| `tests/test_v2_components.py` | Modify | Update thinking-related tests |
| `tests/test_thinking_tiered.py` | Create | New tests for tiered thinking behavior |
| `CLAUDE.md` | Modify | Update Key Technical Decisions, patterns, config docs |

---

### Task 1: Remove thinking from V2Engine gameplay path

**Files:**
- Modify: `src/brain/v2_engine.py:175-215` (_get_v2_tier)
- Modify: `src/brain/v2_engine.py:417-418` (_agent_loop use_think)
- Modify: `src/brain/v2_engine.py:490-492` (tier_name logging)

- [ ] **Step 1: Simplify `_get_v2_tier` — remove think_budget and effort from return**

Change the return type from `tuple[str, int, str]` to `str` (just model name). The thinking budget and effort are no longer used for gameplay.

```python
# v2_engine.py — replace _get_v2_tier entirely

@staticmethod
def _get_v2_tier(
    state_type: str,
    *,
    is_replan: bool = False,
) -> str:
    """Select model for a V2 decision.

    Args:
        state_type: The game state type (e.g. ``"map"``, ``"shop"``).
        is_replan: If ``True``, use strategic model (draw-card re-plan).

    Returns:
        Model name string.
    """
    if is_replan:
        return config.LLM_STRATEGIC_MODEL

    tier = _V2_TIER_MAP.get(state_type, "strategic")
    return getattr(config, f"LLM_{tier.upper()}_MODEL")
```

- [ ] **Step 2: Remove `_V2_HALF_BUDGET_STATES` constant**

```python
# Delete this line (v2_engine.py:118-119):
# _V2_HALF_BUDGET_STATES: frozenset[str] = frozenset({"card_reward", "card_select"})
```

- [ ] **Step 3: Update all `_get_v2_tier` call sites**

In `decide_noncombat` (~line 285):
```python
# Before:
model, think_budget, effort = self._get_v2_tier(gs.state_type)
# After:
model = self._get_v2_tier(gs.state_type)
```

Pass to `_agent_loop` without think params:
```python
# Before:
    model=model,
    think_budget=think_budget,
    effort=effort,
# After:
    model=model,
```

In `generate_combat_plan` (~line 332):
```python
# Before:
model, think_budget, effort = self._get_v2_tier("combat_plan", is_replan=is_replan)
# After:
model = self._get_v2_tier("combat_plan", is_replan=is_replan)
```

Pass to `_agent_loop`:
```python
# Before:
    model=model,
    think_budget=think_budget,
    effort=effort,
# After:
    model=model,
```

- [ ] **Step 4: Simplify `_agent_loop` — remove think params**

Remove `think_budget` and `effort` from `_agent_loop` signature and body:

```python
async def _agent_loop(
    self,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    decision_tool_name: str,
    *,
    model: str | None = None,
    max_query_rounds: int = 5,
    mutate_messages: bool = False,
    state_type_hint: str = "",
) -> tuple[dict | None, list, float, int]:
```

Remove `use_think = think_budget > 0` (line 418). In the backend call:

```python
response = await self._backend.acall(
    system=system,
    messages=msgs,
    model=use_model,
    think=False,  # Thinking disabled for tool_use (proxy compat)
    tools=tools,
    tool_choice={"type": "auto"},
)
```

- [ ] **Step 5: Fix tier_name logging**

Replace `tier_name = "fast" if not use_think else "strategic"` (line 492) with tier lookup from the map. The old logic broke when `LLM_FAST_MODEL == LLM_STRATEGIC_MODEL` (common case). Use `state_type_hint` which is already passed as a parameter:

```python
tier_name = _V2_TIER_MAP.get(state_type_hint, "strategic")
```

Also remove `think_budget=think_budget` from `log_llm_call` call (line 509) — pass `think_budget=0`.

- [ ] **Step 6: Run existing tests**

Run: `python -m pytest tests/test_v2_components.py -v -x`
Expected: Some tests may fail if they mock `_get_v2_tier` return value — fix in Task 5.

- [ ] **Step 7: Commit**

```bash
git add src/brain/v2_engine.py
git commit -m "refactor: remove thinking from V2Engine gameplay path (proxy compat)"
```

---

### Task 2: Remove circuit breaker from V2Backend

**Files:**
- Modify: `src/brain/v2_backend.py:70-71` (remove `_thinking_broken`)
- Modify: `src/brain/v2_backend.py:162-240` (simplify thinking logic)

- [ ] **Step 1: Remove `_thinking_broken` field from `__init__`**

Delete line 71: `self._thinking_broken: bool = False`

- [ ] **Step 2: Remove circuit breaker from `call()` method**

Replace lines 162-240 with simplified logic. Since tool_use callers now pass `think=False`, thinking only activates for text-only calls (call_raw). The circuit breaker was useless anyway (proxy never errors, just silently drops blocks).

```python
# Extended thinking — only for text-only calls (no tools)
if think:
    think_type = config.LLM_THINK_TYPE

    if think_type == "adaptive":
        kwargs["thinking"] = {"type": "adaptive"}
        use_effort = effort or "medium"
        kwargs["output_config"] = {"effort": use_effort}
        _effort_max = {"low": 8192, "medium": 12000, "high": 16000, "max": 32000}
        base_max = max_tokens or config.LLM_MAX_TOKENS
        kwargs["max_tokens"] = max(base_max, _effort_max.get(use_effort, 12000))
    else:
        budget = think_budget if think_budget > 0 else 4000
        kwargs["thinking"] = {
            "type": "enabled",
            "budget_tokens": budget,
        }
        base_max = max_tokens or config.LLM_MAX_TOKENS
        kwargs["max_tokens"] = budget + base_max

    # Anthropic requires temperature=1.0 when thinking is enabled
    kwargs["temperature"] = 1.0
else:
    kwargs["max_tokens"] = max_tokens or config.LLM_MAX_TOKENS
    kwargs["temperature"] = (
        temperature if temperature is not None else config.LLM_TEMPERATURE
    )

# Tool use
if tools:
    kwargs["tools"] = tools
    if tool_choice:
        if think and tool_choice.get("type") == "tool":
            kwargs["tool_choice"] = {"type": "auto"}
        else:
            kwargs["tool_choice"] = tool_choice

client = self._get_client(use_model)
try:
    response: anthropic.Message = client.messages.create(**kwargs)
except self._anthropic.RateLimitError as exc:
    logger.warning("V2Backend rate limited: %s — caller should retry", exc)
    time.sleep(2)
    raise
except self._anthropic.APIError as exc:
    logger.error("V2Backend API error: %s", exc)
    raise
```

- [ ] **Step 3: Update logging — remove `_thinking_broken` references**

The `use_thinking` check in the logging section (~line 267) changes from `use_thinking` to just `think`:

```python
tags = []
if think:
    tags.append("THINK")
if tools:
    tags.append("TOOL")
```

- [ ] **Step 4: Commit**

```bash
git add src/brain/v2_backend.py
git commit -m "refactor: remove circuit breaker from V2Backend (never triggered with proxy)"
```

---

### Task 3: Add `<thinking>` tag stripping to call_raw + effort param

**Files:**
- Modify: `src/brain/llm_caller.py`

The proxy converts thinking blocks to `<thinking>...</thinking>` text tags. Post-run callers (rule_distiller, guide_consolidator, discovery) parse the response text for structured output. The `<thinking>` content must be stripped so parsers see clean output.

- [ ] **Step 1: Add effort parameter and `<thinking>` strip to call_raw**

```python
import re

_THINKING_TAG_RE = re.compile(r"<thinking>.*?</thinking>\s*", re.DOTALL)


async def call_raw(
    system: str,
    prompt: str,
    think: bool = False,
    model: str | None = None,
    effort: str = "",
) -> tuple[str, float, int]:
    """Call LLM and return (response_text, latency_ms, total_tokens).

    Drop-in replacement for the old LLMReasoner.call_raw() interface.
    Uses analysis tier model by default for post-run tasks.

    Note: proxy.example.com proxy converts thinking blocks to <thinking> text
    tags. These are stripped from the returned text so callers see
    clean output.
    """
    backend = _get_or_create_backend()
    start = time.monotonic()

    messages = [{"role": "user", "content": prompt}]
    use_model = model or config.LLM_ANALYSIS_MODEL
    use_effort = effort or config.LLM_THINK_EFFORT_ANALYSIS

    response = await backend.acall(
        system=system,
        messages=messages,
        model=use_model,
        think=think,
        effort=use_effort if think else "",
    )

    # Extract text from anthropic.Message response
    text = ""
    for block in response.content:
        if hasattr(block, "text"):
            text += block.text

    # Strip proxy-injected <thinking> tags (a relay converts thinking
    # blocks to text with <thinking> tags)
    if think and "<thinking>" in text:
        text = _THINKING_TAG_RE.sub("", text).strip()

    latency_ms = (time.monotonic() - start) * 1000
    tokens = 0
    if response.usage:
        tokens = response.usage.input_tokens + response.usage.output_tokens

    return text, latency_ms, tokens
```

- [ ] **Step 2: Commit**

```bash
git add src/brain/llm_caller.py
git commit -m "fix: strip proxy <thinking> tags from call_raw, add effort param"
```

---

### Task 4: Disable thinking for EvolutionEngine

**Files:**
- Modify: `src/brain/evolution_engine.py:350-351`

Evolution engine uses tool_use (5 write tools) → same proxy issue.

- [ ] **Step 1: Set think=False in evolution loop**

```python
# evolution_engine.py ~line 345-352
response = self._backend.call(
    system=EVOLUTION_SYSTEM_PROMPT,
    messages=messages,
    model=model,
    tools=all_tools,
    think=False,  # Disabled: proxy drops tool_use when thinking produces text
    max_tokens=4096,
)
```

- [ ] **Step 2: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "fix: disable thinking for evolution engine (proxy compat)"
```

---

### Task 5: Clean up config.py + fix all removed-var references

**Files:**
- Modify: `config.py:68-87`
- Modify: `src/brain/batch.py:173,182`
- Modify: `scripts/run_agent.py:89`

Several config vars are now dead code. Keep `LLM_THINK_TYPE`, `LLM_THINK_EFFORT_ANALYSIS`, and `LLM_THINK_BUDGET_ANALYSIS` (batch API uses legacy budget mode).

- [ ] **Step 1: Simplify thinking config**

Replace the thinking config block (lines 68-87):

```python
# ── Thinking Mode ─────────────────────────────────────────────
# Thinking is DISABLED for tool_use calls (gameplay + evolution) because
# proxy.example.com proxy drops tool_use blocks when response has multiple content
# blocks.  Thinking is ONLY used by text-only post-run calls (call_raw):
# guide consolidation, rule distillation, skill discovery.
LLM_THINK_TYPE = os.getenv("STS2_THINK_TYPE", "adaptive")
LLM_THINK_EFFORT_ANALYSIS = os.getenv("STS2_THINK_EFFORT_ANALYSIS", "high")
# Budget for Batch API (legacy type=enabled mode, not adaptive)
LLM_THINK_BUDGET_ANALYSIS = int(os.getenv("STS2_THINK_BUDGET_ANALYSIS", "10000"))
```

Remove:
- `LLM_THINK_MODE` (thinking is off for gameplay unconditionally, no global kill switch needed)
- `LLM_THINK_STATES` (never used in code)
- `LLM_THINK_EFFORT_FAST`, `LLM_THINK_EFFORT_STRATEGIC` (gameplay thinking disabled)
- `LLM_THINK_BUDGET_FAST`, `LLM_THINK_BUDGET_STRATEGIC` (gameplay thinking disabled)

Keep `LLM_THINK_BUDGET_ANALYSIS` — used by `batch.py` which uses legacy `type=enabled + budget_tokens` format (Batch API may not support adaptive mode).

- [ ] **Step 2: Fix batch.py — remove `LLM_THINK_MODE` check**

`src/brain/batch.py:182` checks `config.LLM_THINK_MODE != "off"`. Since `LLM_THINK_MODE` is removed, simplify:

```python
# Before (line 182):
if budget > 0 and config.LLM_THINK_MODE != "off":
# After:
if budget > 0:
```

`batch.py:173` uses `config.LLM_THINK_BUDGET_ANALYSIS` — this is kept, no change needed.

- [ ] **Step 3: Fix scripts/run_agent.py — replace `LLM_THINK_MODE` in startup log**

Line 89 references `config.LLM_THINK_MODE` which will be removed. Replace:

```python
# Before (line 87-90):
logger.info(
    "Starting agent: mode=%s, think=%s, skills=%s, memory=%s, runs=%s",
    mode, config.LLM_THINK_MODE, skills_str, memory_str, runs_str,
)
# After:
logger.info(
    "Starting agent: mode=%s, think=%s, skills=%s, memory=%s, runs=%s",
    mode, "off-gameplay/on-analysis", skills_str, memory_str, runs_str,
)
```

- [ ] **Step 4: Verify no remaining references to removed vars**

Run: `grep -rn "LLM_THINK_MODE\|LLM_THINK_STATES\|LLM_THINK_BUDGET_FAST\|LLM_THINK_BUDGET_STRATEGIC\|LLM_THINK_EFFORT_FAST\|LLM_THINK_EFFORT_STRATEGIC" src/ config.py tests/ scripts/`

Expected: 0 matches (all references cleaned up by Tasks 1-5).

- [ ] **Step 5: Commit**

```bash
git add config.py src/brain/batch.py scripts/run_agent.py
git commit -m "refactor: clean up dead thinking config vars, fix batch.py and run_agent.py"
```

---

### Task 6: Update tests

**Files:**
- Modify: `tests/test_v2_components.py`
- Modify: `tests/test_session_logger.py`
- Create: `tests/test_thinking_tiered.py`

- [ ] **Step 1: Fix `_get_v2_tier` tests in test_v2_components.py**

Tests that unpack 3 values from `_get_v2_tier` need updating to unpack 1 value:

```python
# Before:
model, budget, effort = V2Engine._get_v2_tier("map")
# After:
model = V2Engine._get_v2_tier("map")
```

- [ ] **Step 2: Update think_budget test in test_session_logger.py**

`test_llm_call_has_think_budget` (line 600) — update to expect `think_budget=0` for gameplay calls.

- [ ] **Step 3: Create test_thinking_tiered.py with key behavioral tests**

```python
"""Tests for the tiered thinking strategy.

Gameplay (tool_use): thinking disabled.
Post-run (call_raw): thinking enabled, <thinking> tags stripped.
"""
import re
import pytest

from src.brain.llm_caller import _THINKING_TAG_RE


class TestThinkingTagStrip:
    """Verify <thinking> tag removal from proxy responses."""

    def test_strip_thinking_tags(self):
        text = "<thinking>\nSome analysis\n</thinking>\n\nActual response"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Actual response"

    def test_strip_multiple_thinking_blocks(self):
        text = "<thinking>A</thinking>\nMiddle\n<thinking>B</thinking>\nEnd"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Middle\nEnd"

    def test_no_thinking_tags_passthrough(self):
        text = "Normal response without thinking"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == text

    def test_empty_thinking_block(self):
        text = "<thinking></thinking>\nResponse"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Response"


class TestV2EngineTierRouting:
    """Verify _get_v2_tier returns only model (no think params)."""

    def test_returns_string(self):
        from src.brain.v2_engine import V2Engine
        result = V2Engine._get_v2_tier("map")
        assert isinstance(result, str)

    def test_replan_returns_strategic(self):
        import config
        from src.brain.v2_engine import V2Engine
        result = V2Engine._get_v2_tier("combat_plan", is_replan=True)
        assert result == config.LLM_STRATEGIC_MODEL
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_thinking_tiered.py tests/test_v2_components.py tests/test_session_logger.py -v`
Expected: All pass.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "test: add tiered thinking tests, update existing test expectations"
```

---

### Task 7: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Key Technical Decisions — LLM section**

In the LLM bullet, replace all thinking mode descriptions (lines 151-156, 276) with:

```markdown
  - Thinking: DISABLED for tool_use calls (gameplay + evolution) — proxy.example.com proxy drops tool_use blocks when response has text + tool_use. ENABLED for text-only post-run calls (call_raw): guide consolidation, rule distillation, skill discovery. `LLM_THINK_TYPE=adaptive`, `LLM_THINK_EFFORT_ANALYSIS=high`.
  - Proxy limitation: proxy.example.com strips non-first content blocks from multi-block responses. Thinking causes model to produce text before tool_use → tool_use lost. Verified with 5 test configurations — no workaround possible.
  - `call_raw` strips proxy-injected `<thinking>` tags from text responses
```

Remove old thinking config descriptions:
- Lines 151-153: `STS2_THINK_MODE` references
- Lines 154-156: `STS2_THINK_TYPE` and effort/budget env var docs
- Line 276: `STS2_THINK_MODE=off` Bedrock note

- [ ] **Step 2: Update Important Patterns section**

Replace line 485:
```markdown
# Before:
- Model routing: `_get_v2_tier(state_type)` → (model, budget, effort); re-plans use strategic+low instead of fast
# After:
- Model routing: `_get_v2_tier(state_type)` → model name; thinking disabled for all gameplay tool_use calls
```

Replace line 486:
```markdown
# Before:
- Tier logging: `"fast" if not use_think else "strategic"` — based on thinking flag, not model name comparison
# After:
- Tier logging: `_V2_TIER_MAP.get(state_type_hint, "strategic")` — direct lookup from tier map
```

- [ ] **Step 3: Update config section in Running block**

Replace thinking config lines with:

```markdown
Config: MCP server at `localhost:8080`, ACTION_DELAY `0.6s`, thinking disabled for gameplay (proxy compat), thinking enabled for post-run analysis.
```

- [ ] **Step 4: Update Known Issues**

Add to Known Issues:
```markdown
- [x] ~~Thinking params sent to proxy but thinking blocks lost~~ — FIXED: thinking disabled for tool_use calls, kept for text-only post-run analysis. proxy.example.com proxy drops tool_use blocks when response has multiple content blocks.
```

- [ ] **Step 5: Update Bugs Fixed section**

Add under `### 2026-03-29`:
```markdown
### 2026-03-29
- **Thinking wastes 95% of tokens** (CRITICAL): proxy.example.com proxy drops tool_use blocks when response contains text + tool_use (multi-block). With thinking enabled, model produces thinking text before tool_use → proxy strips tool_use → V2Engine retries without thinking → tokens wasted. 321K tokens wasted per run (39/80 calls broken). Fix: thinking disabled for all tool_use paths (V2Engine gameplay + EvolutionEngine), kept for text-only post-run calls (call_raw). Circuit breaker removed (never triggered — proxy silently drops blocks instead of erroring).
```

- [ ] **Step 6: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for thinking tiered strategy"
```

---

### Task 8: Update memory files

**Files:**
- Modify: `<local-path>`

- [ ] **Step 1: Update feedback_llm_config.md**

Add the proxy thinking limitation:

```markdown
## proxy.example.com Proxy Thinking Limitation (2026-03-29)

proxy.example.com proxy drops tool_use blocks when response has multiple content blocks (text + tool_use). Thinking causes this because model produces text (thinking) before tool_use. Verified with 5 test configurations — no workaround.

**Rule:** NEVER enable thinking or effort params for calls that use tools.
**Why:** 95% token waste rate (321K/run). 49% of tool_use calls broken per run.
**How to apply:** tool_use calls (V2Engine, EvolutionEngine) → think=False, no effort. Text-only calls (call_raw for post-run analysis) → think=True, effort=high.
```

- [ ] **Step 2: Commit memory update**

Memory files are outside the repo — no git commit needed.
