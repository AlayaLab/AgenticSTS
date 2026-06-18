# Strategic Thread Memory Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the agent run-level strategic coherence by recording WHY it makes decisions (not just WHAT), injecting this "strategic thread" into all future prompts so every decision builds on the deck-building rationale and win-condition awareness.

**Architecture:** Extend all 6 non-combat decision tool schemas with a `strategic_note` field (combat already has `note_to_future_self`). After each successful decision, extract the note and store it in ShortTermMemory. Replace the current factual STM injection (`## Current Progress`) with a `## Strategic Thread` section containing the accumulated intent chain. Zero additional API calls.

**Tech Stack:** Python, Anthropic tool_use schemas, existing V2Engine pipeline

**Key insight from STS expert strategy (Jorbs "Jobs Framework"):** Expert players maintain a running evaluation of 5 "Jobs" their deck must perform: frontloaded damage, AoE, frontloaded block, scaling, card draw. Every card pick/skip is evaluated against which Jobs are solved vs missing. This strategic thread is exactly the context our agent lacks.

---

### Task 1: Add `strategic_note` field to 6 non-combat tool schemas

**Files:**
- Modify: `src/brain/tool_schemas.py`

- [ ] **Step 1: Add `strategic_note` to MAP_TOOL, REST_TOOL, EVENT_TOOL, SHOP_TOOL, CARD_REWARD_TOOL, CARD_SELECT_TOOL**

In each tool's `input_schema.properties`, add:

```python
"strategic_note": {
    "type": "string",
    "description": (
        "One sentence: WHY you made this choice and what your deck still needs. "
        "Frame around Jobs: frontload damage, block, scaling, draw. "
        "Example: 'Took Noxious Fumes for scaling — deck now needs more block.'"
    ),
},
```

Do NOT add to `required` — keep it optional so existing thinking-disabled paths don't break.

Also update `COMBAT_PLAN_TOOL.note_to_future_self` description to align:

```python
"note_to_future_self": {
    "type": "string",
    "description": (
        "One sentence for future rounds about combat strategy. "
        "E.g. 'Poison at 15, survive 2 more rounds.' or 'Save Catalyst for when Vulnerable lands.'"
    ),
},
```

No other changes to tool schemas. HAND_SELECT_TOOL and TREASURE_TOOL are low-value (hand discard and relic claim) — skip them.

- [ ] **Step 2: Verify schemas are valid JSON**

Run:
```bash
python -c "from src.brain.tool_schemas import *; print('All schemas loaded OK')"
```
Expected: `All schemas loaded OK`

- [ ] **Step 3: Commit**

```bash
git add src/brain/tool_schemas.py
git commit -m "feat: add strategic_note field to 6 non-combat tool schemas"
```

---

### Task 2: Add strategic thread storage to ShortTermMemory

**Files:**
- Modify: `src/memory/short_term.py`
- Test: `tests/test_short_term_strategic.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_short_term_strategic.py`:

```python
"""Tests for ShortTermMemory strategic thread feature."""

from src.memory.short_term import ShortTermMemory


def test_record_and_get_strategic_notes():
    stm = ShortTermMemory()
    stm.record_strategic_note("card_reward", "Took Noxious Fumes — scaling job solved")
    stm.record_strategic_note("shop", "Removed Strike — faster cycle time")

    thread = stm.get_strategic_thread(max_entries=5)
    assert "Noxious Fumes" in thread
    assert "Strike" in thread
    assert "[card_reward]" in thread
    assert "[shop]" in thread


def test_strategic_thread_max_entries():
    stm = ShortTermMemory()
    for i in range(15):
        stm.record_strategic_note("map", f"Note {i}")

    # Internal storage capped at 10
    thread = stm.get_strategic_thread(max_entries=5)
    assert "Note 14" in thread
    assert "Note 10" in thread
    assert "Note 5" not in thread  # Trimmed from storage


def test_strategic_thread_empty():
    stm = ShortTermMemory()
    assert stm.get_strategic_thread() == ""


def test_reset_clears_strategic_thread():
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Some note")
    stm.reset_run()
    assert stm.get_strategic_thread() == ""


def test_get_deck_identity_empty():
    stm = ShortTermMemory()
    assert stm.deck_identity == ""


def test_set_deck_identity():
    stm = ShortTermMemory()
    stm.deck_identity = "poison scaling via Noxious Fumes + Catalyst"
    assert stm.deck_identity == "poison scaling via Noxious Fumes + Catalyst"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_short_term_strategic.py -v`
Expected: FAIL — `ShortTermMemory` has no `record_strategic_note` method

- [ ] **Step 3: Implement strategic thread in ShortTermMemory**

Add to `src/memory/short_term.py`:

In `__init__`:
```python
self._strategic_thread: list[tuple[str, str]] = []  # (context_type, note)
self._deck_identity: str = ""
```

In `reset_run()`, add:
```python
self._strategic_thread.clear()
self._deck_identity = ""
```

Add new methods:
```python
def record_strategic_note(self, context_type: str, note: str) -> None:
    """Record a strategic intent note. Keeps last 10."""
    if note and note.strip():
        self._strategic_thread.append((context_type, note.strip()))
        if len(self._strategic_thread) > 10:
            self._strategic_thread = self._strategic_thread[-10:]

def get_strategic_thread(self, max_entries: int = 5) -> str:
    """Format recent strategic notes for prompt injection.

    Returns empty string if no notes recorded.
    """
    if not self._strategic_thread:
        return ""
    recent = self._strategic_thread[-max_entries:]
    lines = []
    for ctx, note in recent:
        lines.append(f"- [{ctx}] {note}")
    return "\n".join(lines)

@property
def deck_identity(self) -> str:
    """Current deck identity/archetype description."""
    return self._deck_identity

@deck_identity.setter
def deck_identity(self, value: str) -> None:
    self._deck_identity = value.strip() if value else ""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_short_term_strategic.py -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/short_term.py tests/test_short_term_strategic.py
git commit -m "feat: add strategic thread storage to ShortTermMemory"
```

---

### Task 3: Extract `strategic_note` from non-combat decisions into STM

**Files:**
- Modify: `src/agent/loop.py` (near line 3082-3087, where v2_decision result is processed)

- [ ] **Step 1: Add extraction helper method to AgentLoop**

Find the `_hcm_record_card_play` / `_hcm_record_potion_use` region (~line 1789-1807) and add nearby:

```python
def _record_strategic_note(self, decision: "LLMDecision", context_type: str) -> None:
    """Extract strategic_note from decision params and record in STM."""
    note = decision.params.get("strategic_note", "")
    if not note or not isinstance(note, str):
        return
    stm = self._hcm_short_term()
    if stm is not None:
        stm.record_strategic_note(context_type, note)
        logger.debug("Strategic note [%s]: %s", context_type, note[:80])
```

- [ ] **Step 2: Call extraction after successful non-combat decisions**

In the non-combat V2 decision path (around line 3082-3087), after `if result:` and before `return result`:

```python
if result:
    # Extract strategic note from decision
    self._record_strategic_note(
        v2_decision,
        gs.state_type,  # "map", "rest_site", "shop", "card_reward", etc.
    )
    return result
```

Apply the same pattern to the retry path (~line 3114-3115):
```python
if result2:
    self._record_strategic_note(v2_retry, gs.state_type)
    return result2
```

- [ ] **Step 3: Also extract from combat plan's `note_to_future_self` into STM**

Find line ~3247-3250 where `plan.note_to_future_self` is handled. After the existing `record_strategic_note` call to CombatConversation, add STM recording:

```python
if plan.note_to_future_self and self._v2_combat_conversation:
    self._v2_combat_conversation.record_strategic_note(
        self._round_number,
        plan.note_to_future_self,
    )
    # Also record in STM for cross-decision-type continuity
    stm = self._hcm_short_term()
    if stm is not None:
        stm.record_strategic_note("combat", plan.note_to_future_self)
```

- [ ] **Step 4: Verify the agent still starts correctly**

Run: `python -c "from src.agent.loop import AgentLoop; print('OK')"`
Expected: `OK`

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: extract strategic_note from decisions into STM"
```

---

### Task 4: Replace STM prompt injection with Strategic Thread

**Files:**
- Modify: `src/memory/retriever.py` (replace STM summary calls with strategic thread)
- Modify: `src/memory/prompt_injector.py` (format strategic thread section)
- Test: `tests/test_strategic_thread_injection.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_strategic_thread_injection.py`:

```python
"""Tests for strategic thread prompt injection."""

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context


def test_strategic_thread_in_output():
    wc = WorkingContext(
        combat_guide_hints=(),
        combat_episode_hints=(),
        route_guide_hints=(),
        route_memory_hints=(),
        deck_guide_hints=(),
        deck_memory_hints=(),
        short_term_hints=(
            "- [card_reward] Took Noxious Fumes for scaling",
            "- [shop] Removed Strike for faster cycle",
        ),
        rule_hints=(),
        rule_ids=(),
    )
    output = format_working_context(wc)
    assert "## Strategic Thread" in output
    assert "Noxious Fumes" in output
    assert "## Current Progress" not in output  # Old header gone
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_strategic_thread_injection.py -v`
Expected: FAIL — `## Current Progress` is still the header

- [ ] **Step 3: Update `prompt_injector.py` — change section header and format**

In `format_working_context()`, replace the `short_term_hints` section:

Old:
```python
if wc.short_term_hints:
    parts.append("## Current Progress")
    for hint in wc.short_term_hints:
        parts.append(hint)
    parts.append("")
```

New:
```python
if wc.short_term_hints:
    parts.append("## Strategic Thread")
    parts.append("*Your deck-building rationale — maintain coherence across decisions.*\n")
    for hint in wc.short_term_hints:
        parts.append(hint)
    parts.append("")
```

- [ ] **Step 4: Update `retriever.py` — use strategic thread instead of STM facts**

In `query_for_decision()`, find all three places where `short_term.get_combat_summary()`, `short_term.get_route_summary()`, or `short_term.get_deck_summary()` are called and stored in `short_term_hints`.

Replace ALL three with a single strategic thread call at the end (after all domain-specific queries):

```python
# Strategic thread (replaces per-decision-type STM facts)
thread = short_term.get_strategic_thread(max_entries=5)
if thread:
    short_term_hints = [thread]
```

This means all decision types get the same strategic thread (which is the point — cross-decision coherence).

- [ ] **Step 5: Run test to verify it passes**

Run: `python -m pytest tests/test_strategic_thread_injection.py -v`
Expected: PASS

- [ ] **Step 6: Run existing memory tests to verify no regression**

Run: `python -m pytest tests/ -k "memory or conversation or compress" -v`
Expected: All pass (no existing tests depend on `## Current Progress` text)

- [ ] **Step 7: Commit**

```bash
git add src/memory/retriever.py src/memory/prompt_injector.py tests/test_strategic_thread_injection.py
git commit -m "feat: replace STM facts injection with strategic thread"
```

---

### Task 5: Add strategic thread to combat conversation init

**Files:**
- Modify: `src/brain/conversation.py` (inject strategic thread at combat start)
- Modify: `src/agent/loop.py` (pass STM to combat conversation init)

- [ ] **Step 1: Modify `CombatConversation.init_combat()` to accept strategic thread**

In `conversation.py`, find `def init_combat(self, gs, *, strategic_context="", potion_strategy="")`.

Add parameter: `strategic_thread: str = ""`

After the `## Relics` section and before `## Strategic context (skills, boss strategy, archetype)`, inject:

```python
# Run-level strategic thread (deck-building rationale)
if strategic_thread:
    lines.append("")
    lines.append("## Strategic Thread")
    lines.append("*Your deck-building decisions so far — fight with this deck's strengths.*\n")
    lines.append(strategic_thread)
```

- [ ] **Step 2: Pass strategic thread from loop.py to init_combat**

Find where `self._v2_combat_conversation.init_combat(gs, ...)` is called in loop.py. Add:

```python
stm_thread = ""
stm = self._hcm_short_term()
if stm is not None:
    stm_thread = stm.get_strategic_thread(max_entries=7)

self._v2_combat_conversation.init_combat(
    gs,
    strategic_context=strategic_parts_str,
    potion_strategy=potion_str,
    strategic_thread=stm_thread,
)
```

- [ ] **Step 3: Verify combat conversation still initializes**

Run: `python -c "from src.brain.conversation import CombatConversation; print('OK')"`
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
git add src/brain/conversation.py src/agent/loop.py
git commit -m "feat: inject strategic thread into combat conversation init"
```

---

### Task 6: Add strategic note guidance to system prompt

**Files:**
- Modify: `src/brain/prompts/system.py`

- [ ] **Step 1: Add strategic note guidance after "## Decision Tools" section**

Append to `SYSTEM_PROMPT`:

```python
## Strategic Notes
Every decision tool includes an optional `strategic_note` field. Use it to record:
- WHY you made this choice (not what you chose — that's in the action)
- How this advances your deck's win condition
- What your deck still needs (unfilled Jobs: frontload damage, block, scaling, draw)
Keep under 25 words. This note will be shown to you in every future decision this run.
Example: "Took Noxious Fumes — scaling solved. Still need block density (currently ~20%)."
```

- [ ] **Step 2: Verify system prompt loads**

Run: `python -c "from src.brain.prompts.system import SYSTEM_PROMPT; print(f'Length: {len(SYSTEM_PROMPT)} chars')"`
Expected: Length increased by ~400 chars (from ~3869 to ~4270)

- [ ] **Step 3: Commit**

```bash
git add src/brain/prompts/system.py
git commit -m "feat: add strategic note guidance to system prompt"
```

---

### Task 7: Update prompt injection token priority

**Files:**
- Modify: `src/memory/retriever.py`

- [ ] **Step 1: Raise strategic thread priority in `_trim_working_context`**

In `_trim_working_context()`, the current priority order (lowest first) is:
1. short_term_hints (lowest — trimmed first)
2. rule_hints
3. episode/memory hints
4. guide hints (highest)

Change `short_term_hints` to be priority 3 (between rules and guides):

```python
fields_by_priority = [
    ("rule_hints", wc.rule_hints),          # Trim first (lowest)
    ("combat_episode_hints", ...),
    ("route_memory_hints", ...),
    ("deck_memory_hints", ...),
    ("short_term_hints", wc.short_term_hints),  # Strategic thread — medium-high
    ("combat_guide_hints", ...),
    ("route_guide_hints", ...),
    ("deck_guide_hints", ...),              # Trim last (highest)
]
```

This ensures the strategic thread survives token pressure better than individual episodes/rules.

- [ ] **Step 2: Commit**

```bash
git add src/memory/retriever.py
git commit -m "perf: raise strategic thread token priority above rules and episodes"
```

---

### Task 8: Integration test with mock run

**Files:**
- Test: `tests/test_strategic_thread_integration.py`

- [ ] **Step 1: Write integration test**

```python
"""Integration test: strategic notes flow through STM → retriever → prompt."""

from unittest.mock import MagicMock
from src.memory.short_term import ShortTermMemory
from src.memory.prompt_injector import format_working_context
from src.memory.models_v2 import WorkingContext


def test_full_strategic_thread_pipeline():
    """Simulate a run where strategic notes accumulate and inject."""
    stm = ShortTermMemory()

    # Simulate card reward decisions
    stm.record_strategic_note("card_reward", "Took Noxious Fumes — scaling job solved")
    stm.record_strategic_note("card_reward", "Skipped Backflip — draw not needed yet")
    stm.record_strategic_note("shop", "Removed Strike — cycle time 2.4 turns now")
    stm.record_strategic_note("rest_site", "Upgraded Catalyst+ — doubles poison for boss")
    stm.record_strategic_note("map", "Elite path — need relic, HP 60/72 safe")

    # Get thread for prompt
    thread = stm.get_strategic_thread(max_entries=5)

    # Verify all 5 notes present
    assert "Noxious Fumes" in thread
    assert "Backflip" in thread
    assert "Strike" in thread
    assert "Catalyst" in thread
    assert "Elite" in thread

    # Build WorkingContext with thread as short_term_hints
    wc = WorkingContext(
        combat_guide_hints=("Guide: Poison build works well against Kin Priest",),
        combat_episode_hints=(),
        route_guide_hints=(),
        route_memory_hints=(),
        deck_guide_hints=(),
        deck_memory_hints=(),
        short_term_hints=(thread,),
        rule_hints=("Block density below 30% is risky in Act 2 (85.0%)",),
        rule_ids=("rule123",),
    )

    output = format_working_context(wc)

    # Strategic thread present
    assert "## Strategic Thread" in output
    assert "Noxious Fumes" in output

    # Other sections still work
    assert "## Enemy Intel" in output
    assert "## Strategy Rules" in output


def test_strategic_thread_survives_reset():
    """Thread resets between runs."""
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Going aggressive")
    assert stm.get_strategic_thread() != ""

    stm.reset_run()
    assert stm.get_strategic_thread() == ""
```

- [ ] **Step 2: Run integration test**

Run: `python -m pytest tests/test_strategic_thread_integration.py -v`
Expected: All PASS

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --tb=short`
Expected: All existing tests pass, no regressions

- [ ] **Step 4: Commit**

```bash
git add tests/test_strategic_thread_integration.py
git commit -m "test: add strategic thread integration tests"
```

---

### Task 9: Update CLAUDE.md

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Add Strategic Thread to Key Technical Decisions**

Under the `Skills` bullet in Key Technical Decisions, add:

```markdown
- **Strategic Thread**: Run-level decision coherence via `strategic_note` in tool schemas
  - Every non-combat decision tool has optional `strategic_note` field (combat uses `note_to_future_self`)
  - Notes stored in ShortTermMemory._strategic_thread (max 10, last 5 injected)
  - Injected as `## Strategic Thread` in all prompts (replaces old `## Current Progress` facts)
  - Combat conversation init receives full thread for deck-building context awareness
  - System prompt guides LLM to frame notes around Jobs: frontload damage, block, scaling, draw
  - Zero additional API calls — extracted from existing decision tool responses
```

- [ ] **Step 2: Update Important Patterns**

Add:
```markdown
- Strategic thread: `strategic_note` extracted from tool response params → STM → injected into all prompts. Replaces factual STM summaries (cards played, HP changes) with intent-driven context (why I chose this card, what my deck needs).
```

- [ ] **Step 3: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: add strategic thread documentation to CLAUDE.md"
```
