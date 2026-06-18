# Restore Thinking via Streaming Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Re-enable Claude extended thinking for strategic gameplay decisions now that streaming bypasses the proxy.example.com proxy block-stripping issue.

**Architecture:** `_get_v2_tier` returns `(model, effort)` tuple. `_agent_loop` derives `think=bool(effort)` and passes both to `v2_backend.acall`. Fast tier keeps `effort=""` (no thinking). Strategic tier gets `effort="medium"`. Streaming in backend (already landed) ensures thinking + tool_use blocks survive the proxy. Evolution engine also restored with thinking block stripping for multi-turn.

**Tech Stack:** Python, Anthropic SDK (streaming already in v2_backend.py)

---

## File Map

| File | Action | Change |
|------|--------|--------|
| `config.py:68-76` | Modify | Add `LLM_THINK_EFFORT_STRATEGIC`, update comment |
| `src/brain/v2_engine.py:172-193` | Modify | `_get_v2_tier` → returns `tuple[str, str]` |
| `src/brain/v2_engine.py:263,308` | Modify | Call sites unpack 2 values, pass `effort` |
| `src/brain/v2_engine.py:349-408` | Modify | `_agent_loop` accepts `effort`, derives `think` |
| `src/brain/evolution_engine.py:345-389` | Modify | Restore `think=True`, strip thinking from history |
| `scripts/run_agent.py:89` | Modify | Update startup log string |
| `tests/test_thinking_tiered.py` | Modify | Update tests for new return type + effort |

---

### Task 1: Add `LLM_THINK_EFFORT_STRATEGIC` to config

**Files:**
- Modify: `config.py:68-76`

- [ ] **Step 1: Replace the thinking config block**

```python
# config.py lines 68-76 — replace entire block with:

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

- [ ] **Step 2: Verify import**

Run: `python -c "import config; print(config.LLM_THINK_EFFORT_STRATEGIC)"`
Expected: `medium`

- [ ] **Step 3: Commit**

```bash
git add config.py
git commit -m "feat: add LLM_THINK_EFFORT_STRATEGIC config for streaming thinking"
```

---

### Task 2: Restore thinking in V2Engine

**Files:**
- Modify: `src/brain/v2_engine.py:172-193` (_get_v2_tier)
- Modify: `src/brain/v2_engine.py:263` (decide_noncombat call site)
- Modify: `src/brain/v2_engine.py:308` (generate_combat_plan call site)
- Modify: `src/brain/v2_engine.py:349-408` (_agent_loop)

- [ ] **Step 1: Update `_get_v2_tier` to return `tuple[str, str]`**

Replace the entire method (lines 172-193):

```python
@staticmethod
def _get_v2_tier(
    state_type: str,
    *,
    is_replan: bool = False,
) -> tuple[str, str]:
    """Select model and effort level for a V2 decision.

    Args:
        state_type: The game state type (e.g. ``"map"``, ``"shop"``,
            ``"combat_plan"``).
        is_replan: If ``True``, use strategic model with low effort
            (draw-card re-plan, validation retry).

    Returns:
        ``(model_name, effort)`` tuple.  ``effort`` is ``""`` for
        fast tier (no thinking) or ``"medium"``/``"low"`` for
        strategic tier.
    """
    if is_replan:
        return (config.LLM_STRATEGIC_MODEL, "low")

    tier = _V2_TIER_MAP.get(state_type, "strategic")
    model = getattr(config, f"LLM_{tier.upper()}_MODEL")
    # fast tier: no thinking (effort="")
    # strategic tier: thinking with configured effort
    effort = (
        ""
        if tier == "fast"
        else getattr(config, f"LLM_THINK_EFFORT_{tier.upper()}", "medium")
    )
    return (model, effort)
```

- [ ] **Step 2: Update `decide_noncombat` call site (line 263)**

```python
# Before (line 263):
model = self._get_v2_tier(gs.state_type)
# After:
model, effort = self._get_v2_tier(gs.state_type)
```

Add `effort=effort` to the `_agent_loop` call (after `model=model,` at line 270):

```python
decision_input, _content, total_latency, total_tokens = await self._agent_loop(
    system=system,
    messages=messages,
    tools=tools,
    decision_tool_name=decision_tool_name,
    model=model,
    effort=effort,
    max_query_rounds=3,
    state_type_hint=gs.state_type,
)
```

- [ ] **Step 3: Update `generate_combat_plan` call site (line 308)**

```python
# Before (line 308):
model = self._get_v2_tier("combat_plan", is_replan=is_replan)
# After:
model, effort = self._get_v2_tier("combat_plan", is_replan=is_replan)
```

Add `effort=effort` to the `_agent_loop` call (after `model=model,` at line 316):

```python
decision_input, content_blocks, total_latency, total_tokens = (
    await self._agent_loop(
        system=conversation.system_prompt,
        messages=conversation.messages_mut,
        tools=tools,
        decision_tool_name=decision_tool_name,
        model=model,
        effort=effort,
        mutate_messages=True,
        max_query_rounds=2,
        state_type_hint="combat_plan",
    )
)
```

- [ ] **Step 4: Add `effort` param to `_agent_loop` and wire through**

In `_agent_loop` signature (line 349-360), add `effort`:

```python
async def _agent_loop(
    self,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    decision_tool_name: str,
    *,
    model: str | None = None,
    effort: str = "",
    max_query_rounds: int = 5,
    mutate_messages: bool = False,
    state_type_hint: str = "",
) -> tuple[dict | None, list, float, int]:
```

After `use_model = model or config.LLM_STRATEGIC_MODEL` (line 389), add:

```python
use_think = bool(effort)
```

Change the `acall` at line 401-408:

```python
response = await self._backend.acall(
    system=system,
    messages=msgs,
    model=use_model,
    think=use_think,
    effort=effort,
    tools=tools,
    tool_choice={"type": "auto"},
)
```

- [ ] **Step 5: Verify import and basic smoke test**

Run: `python -c "import config; from src.brain.v2_engine import V2Engine; m, e = V2Engine._get_v2_tier('combat_plan'); print(f'model={m}, effort={e}'); assert e == config.LLM_THINK_EFFORT_STRATEGIC; m2, e2 = V2Engine._get_v2_tier('map'); print(f'model={m2}, effort={e2}'); assert e2 == ''"`

Expected: model names from config (env-dependent), strategic effort=medium, fast effort="" (empty).

- [ ] **Step 6: Commit**

```bash
git add src/brain/v2_engine.py
git commit -m "feat: restore thinking for strategic tier via streaming (effort=medium)"
```

---

### Task 3: Restore thinking in EvolutionEngine + strip thinking blocks

**Files:**
- Modify: `src/brain/evolution_engine.py:345-389`

- [ ] **Step 1: Restore `think=True, effort="high"` in the call (line 345-352)**

```python
response = self._backend.call(
    system=EVOLUTION_SYSTEM_PROMPT,
    messages=messages,
    model=model,
    tools=all_tools,
    think=True,
    effort="high",
    max_tokens=4096,
)
```

- [ ] **Step 2: Strip thinking blocks before appending to messages (line 389)**

Replace:
```python
messages.append({"role": "assistant", "content": response.content})
```

With:
```python
# Strip thinking blocks — Anthropic requires prior-turn thinking
# to be removed/redacted in multi-turn conversations.
# Dual-check pattern matches conversation.py and v2_engine.py filters.
filtered_content = [
    b for b in response.content
    if not (
        (isinstance(b, dict) and b.get("type") == "thinking")
        or (hasattr(b, "type") and getattr(b, "type", None) == "thinking")
    )
] or [{"type": "text", "text": "(thinking only)"}]
messages.append({"role": "assistant", "content": filtered_content})
```

- [ ] **Step 3: Verify import**

Run: `python -c "from src.brain.evolution_engine import EvolutionEngine; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "feat: restore thinking for evolution engine, strip thinking from multi-turn"
```

---

### Task 4: Update startup log + tests

**Files:**
- Modify: `scripts/run_agent.py:89`
- Modify: `tests/test_thinking_tiered.py`

- [ ] **Step 1: Update startup log (run_agent.py line 89)**

```python
# Before:
mode, "off-gameplay/on-analysis", skills_str, memory_str, runs_str,
# After:
mode, "fast=off/strategic=medium/analysis=high", skills_str, memory_str, runs_str,
```

- [ ] **Step 2: Update tests/test_thinking_tiered.py**

Replace entire file:

```python
"""Tests for the tiered thinking strategy.

Strategic tier: thinking ON (effort from config).
Fast tier: thinking OFF (effort="").
Post-run (call_raw): thinking ON, <thinking> tags stripped.
"""
import config
from src.brain.llm_caller import _THINKING_TAG_RE


class TestThinkingTagStrip:
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
    def test_returns_tuple(self):
        from src.brain.v2_engine import V2Engine
        result = V2Engine._get_v2_tier("map")
        assert isinstance(result, tuple)
        assert len(result) == 2

    def test_fast_tier_no_thinking(self):
        from src.brain.v2_engine import V2Engine
        model, effort = V2Engine._get_v2_tier("map")
        assert isinstance(model, str)
        assert effort == ""

    def test_strategic_tier_has_effort(self):
        from src.brain.v2_engine import V2Engine
        model, effort = V2Engine._get_v2_tier("combat_plan")
        assert isinstance(model, str)
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC
        assert effort != ""

    def test_replan_low_effort(self):
        from src.brain.v2_engine import V2Engine
        model, effort = V2Engine._get_v2_tier("combat_plan", is_replan=True)
        assert model == config.LLM_STRATEGIC_MODEL
        assert effort == "low"

    def test_unknown_state_defaults_strategic(self):
        from src.brain.v2_engine import V2Engine
        model, effort = V2Engine._get_v2_tier("unknown_state_xyz")
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC

    def test_all_fast_states(self):
        from src.brain.v2_engine import V2Engine
        for state in ("map", "hand_select", "treasure"):
            _, effort = V2Engine._get_v2_tier(state)
            assert effort == "", f"{state} should be fast tier (no effort)"

    def test_all_strategic_states(self):
        from src.brain.v2_engine import V2Engine
        for state in ("combat_plan", "rest_site", "shop", "event",
                       "card_reward", "card_select", "monster", "elite", "boss"):
            _, effort = V2Engine._get_v2_tier(state)
            assert effort != "", f"{state} should be strategic tier (has effort)"
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest tests/test_thinking_tiered.py tests/test_v2_components.py tests/test_session_logger.py -v --tb=short`
Expected: All pass.

- [ ] **Step 4: Commit**

```bash
git add scripts/run_agent.py tests/test_thinking_tiered.py
git commit -m "test: update thinking tiered tests for restored strategic effort"
```

---

### Task 5: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update thinking description in Key Technical Decisions**

Find the thinking-related lines (around line 151) that currently say thinking is disabled for gameplay. Replace with:

```markdown
  - Thinking: DISABLED for fast tier (map, hand_select, treasure). ENABLED for strategic tier (combat, rest, shop, event, card) via streaming — `effort=medium`. ENABLED for analysis tier (post-run call_raw) — `effort=high`. Streaming (`messages.stream().get_final_message()`) bypasses proxy.example.com proxy block stripping.
  - Proxy workaround: proxy.example.com non-streaming aggregation drops non-first content blocks. Streaming preserves all blocks (thinking + text + tool_use). Verified empirically.
  - `call_raw` (non-streaming, no tools) still strips proxy-injected `<thinking>` tags from text responses
```

- [ ] **Step 2: Update Important Patterns**

Find the model routing pattern line and update:

```markdown
- Model routing: `_get_v2_tier(state_type)` → (model, effort); fast tier effort="" (no thinking), strategic tier effort="medium"
```

- [ ] **Step 3: Update Bugs Fixed 2026-03-29 entry**

Append to the existing 2026-03-29 entry:

```markdown
- **Thinking restored via streaming** (IMPROVEMENT): Codex discovered `messages.stream().get_final_message()` bypasses proxy block stripping. Thinking re-enabled for strategic tier (effort=medium) and evolution engine (effort=high). Fast tier remains think=off. Token efficiency: no more wasted retries, thinking tokens are actual reasoning.
```

- [ ] **Step 4: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for restored thinking via streaming"
```
