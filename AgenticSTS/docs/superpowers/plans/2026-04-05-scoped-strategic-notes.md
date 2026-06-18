# Scoped Strategic Notes Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add lifetime scoping (turn/combat/run) and trigger-based filtering to strategic notes, fix hand_select pollution and duplicate injection.

**Architecture:** Extend `ShortTermMemory` with `NoteScope` enum and `StrategicNote` dataclass. Notes carry `scope` and `triggers` metadata. Expiry hooks at round-start and combat-end prune short-lived notes. Retrieval filters by `current_context`. Quick fixes (hand_select guard, combat dedup) are implemented first.

**Tech Stack:** Python dataclasses, enum — no new dependencies.

**Spec:** `docs/superpowers/specs/2026-04-05-scoped-strategic-notes-design.md`

---

### Task 1: Data Model — NoteScope + StrategicNote

**Files:**
- Modify: `src/memory/short_term.py:1-20` (imports), `src/memory/short_term.py:226-228` (storage field)
- Test: `tests/test_short_term_strategic.py`

- [ ] **Step 1: Write failing tests for scoped notes**

Add to `tests/test_short_term_strategic.py`:

```python
from src.memory.short_term import ShortTermMemory, NoteScope, StrategicNote


def test_record_scoped_note():
    stm = ShortTermMemory()
    stm.record_strategic_note(
        "card_reward", "Need AoE for Act 2",
        scope=NoteScope.RUN, triggers=("deck_building",),
    )
    stm.record_strategic_note(
        "shop", "Save gold for remove",
        scope=NoteScope.COMBAT, triggers=("routing",),
    )
    # Both stored
    thread = stm.get_strategic_thread(max_entries=10)
    assert "AoE" in thread
    assert "gold" in thread


def test_expire_turn_notes():
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Run-level note", scope=NoteScope.RUN)
    stm.record_strategic_note("card_reward", "Combat note", scope=NoteScope.COMBAT)
    stm.record_strategic_note("card_reward", "Turn note", scope=NoteScope.TURN)
    stm.expire_turn_notes()
    thread = stm.get_strategic_thread(max_entries=10)
    assert "Run-level" in thread
    assert "Combat note" in thread
    assert "Turn note" not in thread


def test_expire_combat_notes():
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Run-level note", scope=NoteScope.RUN)
    stm.record_strategic_note("card_reward", "Combat note", scope=NoteScope.COMBAT)
    stm.record_strategic_note("card_reward", "Turn note", scope=NoteScope.TURN)
    stm.expire_combat_notes()
    thread = stm.get_strategic_thread(max_entries=10)
    assert "Run-level" in thread
    assert "Combat note" not in thread
    assert "Turn note" not in thread


def test_filter_by_trigger_context():
    stm = ShortTermMemory()
    stm.record_strategic_note(
        "card_reward", "Deck needs poison",
        triggers=("deck_building",),
    )
    stm.record_strategic_note(
        "map", "Take elite path",
        triggers=("routing",),
    )
    stm.record_strategic_note(
        "shop", "Universal strategy",
        triggers=("all",),
    )

    # card_reward context -> sees deck_building + all
    deck_thread = stm.get_strategic_thread(max_entries=10, current_context="card_reward")
    assert "poison" in deck_thread
    assert "Universal" in deck_thread
    assert "elite path" not in deck_thread

    # map context -> sees routing + all
    map_thread = stm.get_strategic_thread(max_entries=10, current_context="map")
    assert "elite path" in map_thread
    assert "Universal" in map_thread
    assert "poison" not in map_thread

    # empty context -> sees all
    all_thread = stm.get_strategic_thread(max_entries=10, current_context="")
    assert "poison" in all_thread
    assert "elite path" in all_thread
    assert "Universal" in all_thread


def test_scoped_note_capacity_15():
    stm = ShortTermMemory()
    for i in range(20):
        stm.record_strategic_note("map", f"Note {i}")
    # Internal storage capped at 15 (FIFO)
    thread = stm.get_strategic_thread(max_entries=15)
    assert "Note 19" in thread
    assert "Note 5" in thread
    assert "Note 4" not in thread
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_short_term_strategic.py -v -x`
Expected: FAIL — `NoteScope` and `StrategicNote` not importable, `scope`/`triggers` kwargs not accepted.

- [ ] **Step 3: Implement NoteScope, StrategicNote, TRIGGER_STATE_MAP**

In `src/memory/short_term.py`, add after the existing imports (line 12):

```python
from enum import Enum


class NoteScope(str, Enum):
    """Lifetime scope for strategic notes."""
    TURN = "turn"        # expires at next combat round start
    COMBAT = "combat"    # expires when combat ends
    RUN = "run"          # persists entire run (default)


TRIGGER_STATE_MAP: dict[str, set[str] | None] = {
    "combat": {"monster", "elite", "boss", "hand_select"},
    "deck_building": {"card_reward", "shop", "card_select"},
    "routing": {"map", "rest_site", "event"},
    "all": None,  # None = matches everything
}


@dataclass(frozen=True)
class StrategicNote:
    """A scoped strategic note with trigger filtering."""
    context_type: str
    note: str
    scope: NoteScope = NoteScope.RUN
    triggers: tuple[str, ...] = ("all",)
    created_floor: int = 0
    created_round: int = 0


def _note_matches_context(note: StrategicNote, state_type: str) -> bool:
    """Check if a note's triggers match the given state_type."""
    for trigger in note.triggers:
        if trigger == "all":
            return True
        matched_types = TRIGGER_STATE_MAP.get(trigger)
        if matched_types is not None and state_type in matched_types:
            return True
    return False
```

- [ ] **Step 4: Replace storage and update methods**

In `src/memory/short_term.py`, replace line 227:
```python
        self._strategic_thread: list[tuple[str, str]] = []  # (context_type, note)
```
with:
```python
        self._strategic_notes: list[StrategicNote] = []
```

Replace `reset_run()` line 242:
```python
        self._strategic_thread.clear()
```
with:
```python
        self._strategic_notes.clear()
```

Replace the entire `record_strategic_note` method (lines 544-549):
```python
    def record_strategic_note(
        self,
        context_type: str,
        note: str,
        *,
        scope: NoteScope = NoteScope.RUN,
        triggers: tuple[str, ...] = ("all",),
        floor: int = 0,
        combat_round: int = 0,
    ) -> None:
        """Record a scoped strategic note. Keeps last 15."""
        if note and note.strip():
            self._strategic_notes.append(StrategicNote(
                context_type=context_type,
                note=note.strip(),
                scope=scope,
                triggers=triggers,
                created_floor=floor,
                created_round=combat_round,
            ))
            if len(self._strategic_notes) > 15:
                self._strategic_notes = self._strategic_notes[-15:]
```

Replace the entire `get_strategic_thread` method (lines 551-562):
```python
    def get_strategic_thread(
        self, max_entries: int = 5, *, current_context: str = "",
    ) -> str:
        """Format recent strategic notes for prompt injection.

        When *current_context* is non-empty, only notes whose triggers
        match that state_type are included.
        """
        if not self._strategic_notes:
            return ""
        if current_context:
            filtered = [
                n for n in self._strategic_notes
                if _note_matches_context(n, current_context)
            ]
        else:
            filtered = list(self._strategic_notes)
        recent = filtered[-max_entries:]
        if not recent:
            return ""
        return "\n".join(f"- [{n.context_type}] {n.note}" for n in recent)
```

Add two new methods after `get_strategic_thread`:
```python
    def expire_turn_notes(self) -> None:
        """Remove all notes with TURN scope."""
        self._strategic_notes = [
            n for n in self._strategic_notes if n.scope != NoteScope.TURN
        ]

    def expire_combat_notes(self) -> None:
        """Remove all notes with TURN or COMBAT scope."""
        self._strategic_notes = [
            n for n in self._strategic_notes
            if n.scope not in (NoteScope.TURN, NoteScope.COMBAT)
        ]
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_short_term_strategic.py -v`
Expected: ALL PASS (both new scoped tests and existing backward-compat tests).

Note: existing tests call `record_strategic_note(ctx, note)` with positional args only — this still works because `scope`/`triggers`/`floor`/`combat_round` are keyword-only with defaults.

The existing `test_strategic_thread_max_entries` checks for cap at 10 — update that test:
```python
def test_strategic_thread_max_entries():
    stm = ShortTermMemory()
    for i in range(20):
        stm.record_strategic_note("map", f"Note {i}")

    # Internal storage capped at 15
    thread = stm.get_strategic_thread(max_entries=5)
    assert "Note 19" in thread
    assert "Note 15" in thread
    assert "Note 4" not in thread  # Trimmed from storage
```

- [ ] **Step 6: Commit**

```bash
git add src/memory/short_term.py tests/test_short_term_strategic.py
git commit -m "feat: scoped strategic notes — NoteScope enum, StrategicNote dataclass, trigger filtering, expiry methods"
```

---

### Task 2: Tool Schema — note_scope + note_triggers

**Files:**
- Modify: `src/brain/tool_schemas.py:199-206, 232-239, 265-272, 306-313, 339-346, 378-385`

- [ ] **Step 1: Define the shared schema snippet**

Create a helper constant at the top of `src/brain/tool_schemas.py` (after the existing imports/constants, before MAP_TOOL):

```python
# Shared note scope + trigger fields for strategic note tools
_NOTE_SCOPE_SCHEMA = {
    "note_scope": {
        "type": "string",
        "enum": ["turn", "combat", "run"],
        "description": (
            "How long this note stays relevant. "
            "turn = this combat turn only, combat = until this fight ends, "
            "run = entire run. Default: run."
        ),
    },
    "note_triggers": {
        "type": "array",
        "items": {
            "type": "string",
            "enum": ["combat", "deck_building", "routing", "all"],
        },
        "description": (
            "Which decision types should see this note. "
            "combat = during fights, deck_building = card rewards/shop/card select, "
            "routing = map/rest/event, all = everywhere. Default: ['all']."
        ),
    },
}
```

- [ ] **Step 2: Add note_scope + note_triggers to all 6 tools**

For each of these 6 tools, add `**_NOTE_SCOPE_SCHEMA` to the `"properties"` dict, right after the `"strategic_note"` entry:

1. **MAP_TOOL** — after line 206, add `**_NOTE_SCOPE_SCHEMA,` inside `"properties"`
2. **REST_TOOL** — same pattern after its `"strategic_note"` entry
3. **EVENT_TOOL** — same
4. **SHOP_TOOL** — same
5. **CARD_REWARD_TOOL** — same
6. **CARD_SELECT_TOOL** — same

For example, MAP_TOOL properties become:
```python
        "properties": {
            "action": { ... },
            "option_index": { ... },
            "reasoning": { ... },
            "strategic_note": { ... },
            **_NOTE_SCOPE_SCHEMA,
        },
```

- [ ] **Step 3: Verify schemas are valid**

Run: `python -c "from src.brain.tool_schemas import MAP_TOOL, REST_TOOL, EVENT_TOOL, SHOP_TOOL, CARD_REWARD_TOOL, CARD_SELECT_TOOL; print('All 6 tools loaded OK'); [print(t['name'], list(t['input_schema']['properties'].keys())) for t in [MAP_TOOL, REST_TOOL, EVENT_TOOL, SHOP_TOOL, CARD_REWARD_TOOL, CARD_SELECT_TOOL]]"`
Expected: All 6 tools print with `note_scope` and `note_triggers` in properties.

- [ ] **Step 4: Commit**

```bash
git add src/brain/tool_schemas.py
git commit -m "feat: add note_scope and note_triggers fields to 6 strategic note tools"
```

---

### Task 3: Schema Hint Fix — decision_parser.py

**Files:**
- Modify: `src/brain/decision_parser.py:193`
- Test: `tests/test_decision_parser_hint.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_decision_parser_hint.py`:

```python
"""Tests for format_decision_schema_hint strategic_note filtering."""

from src.brain.decision_parser import format_decision_schema_hint


def test_strategic_note_hint_for_supported_tools():
    """Tools with strategic_note should show the hint."""
    for tool_name in [
        "map_action", "rest_action", "event_action",
        "shop_action", "card_reward_action", "card_select_action",
    ]:
        hint = format_decision_schema_hint(tool_name)
        assert "strategic_note" in hint, f"{tool_name} should have strategic_note hint"
        assert "note_scope" in hint, f"{tool_name} should have note_scope hint"


def test_no_strategic_note_hint_for_unsupported_tools():
    """Tools without strategic_note should NOT show the hint."""
    for tool_name in [
        "hand_select_action", "treasure_action",
        "relic_select_action", "potion_action",
    ]:
        hint = format_decision_schema_hint(tool_name)
        assert "strategic_note" not in hint, f"{tool_name} should NOT have strategic_note hint"


def test_combat_plan_returns_empty():
    """combat_plan always returns empty (schema in system prompt)."""
    assert format_decision_schema_hint("combat_plan") == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_decision_parser_hint.py -v -x`
Expected: FAIL — `hand_select_action` hint currently contains "strategic_note".

- [ ] **Step 3: Fix format_decision_schema_hint**

In `src/brain/decision_parser.py`, replace line 193:
```python
    parts.append("Optional: strategic_note")
```
with:
```python
    _STRATEGIC_NOTE_TOOLS = {
        "map_action", "rest_action", "event_action",
        "shop_action", "card_reward_action", "card_select_action",
    }
    if tool_name in _STRATEGIC_NOTE_TOOLS:
        parts.append(
            "Optional: strategic_note, note_scope (turn|combat|run), "
            "note_triggers (combat|deck_building|routing|all)"
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_decision_parser_hint.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/brain/decision_parser.py tests/test_decision_parser_hint.py
git commit -m "fix: only show strategic_note hint for tools that support it"
```

---

### Task 4: Recording Guard + Scope Parsing — loop.py

**Files:**
- Modify: `src/agent/loop.py:2120-2128`

- [ ] **Step 1: Rewrite _record_strategic_note**

Replace `src/agent/loop.py` lines 2120-2128:

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

with:

```python
    _STRATEGIC_NOTE_STATE_TYPES = frozenset({
        "card_reward", "shop", "map", "rest_site", "event", "card_select",
    })

    def _record_strategic_note(self, decision: "LLMDecision", context_type: str) -> None:
        """Extract strategic_note from decision params and record in STM.

        Only records for state types that have strategic_note in their tool
        schema. Parses optional note_scope and note_triggers from the LLM.
        """
        if context_type not in self._STRATEGIC_NOTE_STATE_TYPES:
            return
        note = decision.params.get("strategic_note", "")
        if not note or not isinstance(note, str):
            return
        stm = self._hcm_short_term()
        if stm is None:
            return

        from src.memory.short_term import NoteScope

        # Parse scope (default: run)
        raw_scope = decision.params.get("note_scope", "run")
        try:
            scope = NoteScope(raw_scope)
        except ValueError:
            scope = NoteScope.RUN

        # Parse triggers (default: ["all"])
        raw_triggers = decision.params.get("note_triggers", ["all"])
        if not isinstance(raw_triggers, list):
            raw_triggers = ["all"]
        valid_triggers = {"combat", "deck_building", "routing", "all"}
        triggers = tuple(t for t in raw_triggers if t in valid_triggers) or ("all",)

        floor = self._run_state.floor if self._run_state and hasattr(self._run_state, "floor") else 0
        combat_round = (
            self._v2_combat_conversation._round_count
            if self._v2_combat_conversation else 0
        )

        stm.record_strategic_note(
            context_type, note,
            scope=scope, triggers=triggers,
            floor=floor, combat_round=combat_round,
        )
        logger.debug(
            "Strategic note [%s] scope=%s triggers=%s: %s",
            context_type, scope.value, triggers, note[:80],
        )
```

- [ ] **Step 2: Verify no import errors**

Run: `python -c "from src.agent.loop import AgentLoop; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: recording guard — whitelist state types, parse scope + triggers from LLM"
```

---

### Task 5: Expiry Hooks — loop.py

**Files:**
- Modify: `src/agent/loop.py:1945` (combat end), `src/agent/loop.py:2031-2033` (round start)

- [ ] **Step 1: Add expire_combat_notes to _hcm_end_combat**

In `src/agent/loop.py`, after line 1945 (`stm.end_combat(won, hp_after)`), add:

```python
            stm.expire_combat_notes()
```

The method now reads:
```python
    def _hcm_end_combat(self, won: bool, hp_after: int) -> None:
        """Hook: COMBAT_END — finalize combat tracking."""
        stm = self._hcm_short_term()
        if stm is not None:
            # Finalize last round's damage_taken from HP delta
            combat = stm.current_combat
            if combat is not None and combat._current_round is not None:
                prev = combat._current_round
                prev.hp_end = hp_after
                prev.damage_taken = max(0, prev.hp_start - hp_after)
            stm.end_combat(won, hp_after)
            stm.expire_combat_notes()
            # Close the route node opened in _hcm_start_combat
            gold = self._cached_gold if hasattr(self, "_cached_gold") else 0
            act = self._cached_act if hasattr(self, "_cached_act") else 1
            stm.end_route_node(hp_after, gold, act)
```

- [ ] **Step 2: Add expire_turn_notes to _hcm_start_round**

In `src/agent/loop.py`, after line 2032 (`if stm is None or not gs.combat: return`), add:

```python
        stm.expire_turn_notes()
```

The method now starts:
```python
    def _hcm_start_round(self, gs: GameState) -> None:
        """Hook: new combat round — start round tracking.

        Also finalizes previous round's damage_taken from HP delta.
        """
        stm = self._hcm_short_term()
        if stm is None or not gs.combat:
            return

        stm.expire_turn_notes()

        # Finalize previous round's damage_taken from HP delta
        ...
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: expiry hooks — turn notes at round start, combat notes at combat end"
```

---

### Task 6: Combat Start Dedup Fix — loop.py

**Files:**
- Modify: `src/agent/loop.py:1278-1281` (primary combat start), `src/agent/loop.py:1797-1800` (eval-reload)

- [ ] **Step 1: Fix primary combat start block**

In `src/agent/loop.py`, replace lines 1278-1281:
```python
                                    wc = ctx.get("working_context")
                                    if wc is not None:
                                        from src.memory.prompt_injector import format_working_context
                                        mem_str = format_working_context(wc)
```
with:
```python
                                    wc = ctx.get("working_context")
                                    if wc is not None:
                                        from dataclasses import replace as dc_replace
                                        from src.memory.prompt_injector import format_working_context
                                        # Strip short_term_hints to avoid duplicate Strategic Thread
                                        # (STM thread already injected via add_combat_start's strategic_thread param)
                                        wc_no_thread = dc_replace(wc, short_term_hints=())
                                        mem_str = format_working_context(wc_no_thread)
```

- [ ] **Step 2: Fix eval-reload combat start block**

In `src/agent/loop.py`, replace lines 1797-1800:
```python
                wc = ctx.get("working_context")
                if wc is not None:
                    from src.memory.prompt_injector import format_working_context
                    mem_str = format_working_context(wc)
```
with:
```python
                wc = ctx.get("working_context")
                if wc is not None:
                    from dataclasses import replace as dc_replace
                    from src.memory.prompt_injector import format_working_context
                    wc_no_thread = dc_replace(wc, short_term_hints=())
                    mem_str = format_working_context(wc_no_thread)
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "fix: remove duplicate Strategic Thread injection in combat start"
```

---

### Task 7: Context-Filtered Injection — retriever.py + loop.py

**Files:**
- Modify: `src/memory/retriever.py:339`, `src/agent/loop.py:1325`, `src/agent/loop.py:4796`

- [ ] **Step 1: Update retriever.py**

In `src/memory/retriever.py`, the function signature for `query_for_decision` already receives `gs` as the first argument. Replace line 339:
```python
    thread = short_term.get_strategic_thread(max_entries=5)
```
with:
```python
    thread = short_term.get_strategic_thread(
        max_entries=5, current_context=gs.state_type,
    )
```

- [ ] **Step 2: Update combat start caller**

In `src/agent/loop.py`, replace line 1325:
```python
                                        stm_thread = stm.get_strategic_thread(max_entries=7)
```
with:
```python
                                        stm_thread = stm.get_strategic_thread(
                                            max_entries=7, current_context=gs.state_type,
                                        )
```

- [ ] **Step 3: Update route selection caller**

In `src/agent/loop.py`, replace line 4796:
```python
            strategic_thread = stm.get_strategic_thread(max_entries=5)
```
with:
```python
            strategic_thread = stm.get_strategic_thread(
                max_entries=5, current_context="map",
            )
```

- [ ] **Step 4: Run all tests**

Run: `python -m pytest tests/test_short_term_strategic.py tests/test_strategic_thread_integration.py tests/test_strategic_thread_injection.py tests/test_decision_parser_hint.py -v`
Expected: ALL PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/retriever.py src/agent/loop.py
git commit -m "feat: context-filtered strategic thread injection via current_context kwarg"
```

---

### Task 8: Update Integration Test

**Files:**
- Modify: `tests/test_strategic_thread_integration.py`

- [ ] **Step 1: Add scoped integration test**

Add to `tests/test_strategic_thread_integration.py`:

```python
from src.memory.short_term import NoteScope


def test_scoped_notes_lifecycle():
    """Simulate a run with scoped notes: turn/combat expire, run persists."""
    stm = ShortTermMemory()

    # Run-level note
    stm.record_strategic_note(
        "card_reward", "Deck needs AoE — took Dagger Spray",
        scope=NoteScope.RUN, triggers=("deck_building",),
    )
    # Combat-level note
    stm.record_strategic_note(
        "card_reward", "Focus poison on beetle",
        scope=NoteScope.COMBAT, triggers=("combat",),
    )
    # Turn-level note
    stm.record_strategic_note(
        "card_reward", "Block the 15 incoming this turn",
        scope=NoteScope.TURN, triggers=("combat",),
    )

    # All 3 visible in unfiltered
    assert "AoE" in stm.get_strategic_thread(max_entries=10)
    assert "beetle" in stm.get_strategic_thread(max_entries=10)
    assert "Block the 15" in stm.get_strategic_thread(max_entries=10)

    # Turn expires at round start
    stm.expire_turn_notes()
    assert "Block the 15" not in stm.get_strategic_thread(max_entries=10)
    assert "beetle" in stm.get_strategic_thread(max_entries=10)

    # Combat expires at combat end
    stm.expire_combat_notes()
    assert "beetle" not in stm.get_strategic_thread(max_entries=10)
    assert "AoE" in stm.get_strategic_thread(max_entries=10)

    # Run-level note only visible in matching context
    deck_thread = stm.get_strategic_thread(max_entries=10, current_context="card_reward")
    assert "AoE" in deck_thread
    combat_thread = stm.get_strategic_thread(max_entries=10, current_context="monster")
    assert "AoE" not in combat_thread
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_short_term_strategic.py tests/test_strategic_thread_integration.py tests/test_strategic_thread_injection.py tests/test_decision_parser_hint.py -v`
Expected: ALL PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_strategic_thread_integration.py
git commit -m "test: scoped notes lifecycle integration test"
```

---

### Task 9: Final Verification

- [ ] **Step 1: Run full project test suite**

Run: `python -m pytest tests/ -x --tb=short`
Expected: ALL PASS, no regressions.

- [ ] **Step 2: Verify imports are clean**

Run: `python -c "from src.memory.short_term import NoteScope, StrategicNote, TRIGGER_STATE_MAP; from src.brain.tool_schemas import MAP_TOOL; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Spot-check schema rendering**

Run: `python -c "from src.brain.decision_parser import format_decision_schema_hint; print(format_decision_schema_hint('card_reward_action')); print('---'); print(format_decision_schema_hint('hand_select_action'))"`
Expected: First output includes `strategic_note, note_scope, note_triggers`. Second output does NOT include `strategic_note`.
