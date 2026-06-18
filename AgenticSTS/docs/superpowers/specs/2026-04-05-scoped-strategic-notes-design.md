# Scoped Strategic Notes

**Date:** 2026-04-05
**Status:** Draft
**Scope:** Memory subsystem — `short_term.py`, `loop.py`, `tool_schemas.py`, `decision_parser.py`, `retriever.py`

## Problem

The Strategic Thread records LLM-generated notes across decisions to maintain run-level coherence (deck-building rationale, win condition tracking). Three issues degrade note quality:

1. **hand_select pollution** — `decision_parser.py:193` unconditionally tells the LLM "Optional: strategic_note" for ALL tools, including `hand_select` which has no such field in its schema. The `<decision>` JSON extractor doesn't enforce `additionalProperties`, so the LLM writes tactical notes like "The Rock is stunned, so I don't need to prioritize block" into the run-level thread. These occupy the 5-entry injection window and mislead card_reward/shop decisions.

2. **Duplicate injection in combat start** — msg[0] of the combat conversation receives the Strategic Thread twice: once via `add_combat_start(strategic_thread=stm_thread)` (conversation.py:605-612) and again inside `format_working_context(wc)` from the memory retriever which includes `short_term_hints` (prompt_injector.py:99-104), wrapped as "Past Combat Experience".

3. **No lifetime or scope** — All notes are `(context_type, note)` tuples stored in a flat list. A turn-scoped tactical observation ("block the 15 damage incoming") and a run-scoped deck plan ("need more poison cards") are treated identically. Notes never expire and compete for the same 5-entry window.

## Design

### Scope Levels

Three levels of note lifetime, automatically expired:

| Scope | Expires when | Example |
|-------|-------------|---------|
| `turn` | Next combat round starts | "Block Bowlbug's 15 damage this turn" |
| `combat` | Current combat ends | "Focus poison on the beetle, ignore the bugs" |
| `run` | Run ends (or `reset_run()`) | "Deck needs more AoE for Act 2 hallways" |

### Trigger Categories

Coarse-grained enum controlling which decision contexts see a note. LLM specifies triggers when writing a note.

| Trigger | Matched state_types | Use case |
|---------|-------------------|----------|
| `combat` | monster, elite, boss, hand_select | Combat-relevant observations |
| `deck_building` | card_reward, shop, card_select | Deck plan and card evaluation |
| `routing` | map, rest_site, event | Pathing and resource decisions |
| `all` | everything (default) | Cross-cutting strategy |

Multiple triggers can be combined (e.g. `["combat", "deck_building"]`).

### Data Model

```python
# src/memory/short_term.py

class NoteScope(str, Enum):
    TURN = "turn"
    COMBAT = "combat"
    RUN = "run"

TRIGGER_STATE_MAP: dict[str, set[str] | None] = {
    "combat": {"monster", "elite", "boss", "hand_select"},
    "deck_building": {"card_reward", "shop", "card_select"},
    "routing": {"map", "rest_site", "event"},
    "all": None,  # None = matches everything
}

@dataclass(frozen=True)
class StrategicNote:
    context_type: str                        # state_type that created it
    note: str
    scope: NoteScope = NoteScope.RUN
    triggers: tuple[str, ...] = ("all",)     # subset of TRIGGER_STATE_MAP keys
    created_floor: int = 0
    created_round: int = 0
```

### Storage

Replace `_strategic_thread: list[tuple[str, str]]` with `_strategic_notes: list[StrategicNote]`.

- Max capacity: 15 (up from 10, accommodating multi-scope notes)
- FIFO eviction when full (oldest first)
- `reset_run()` clears all

### Matching Logic

```python
def _note_matches_context(note: StrategicNote, state_type: str) -> bool:
    for trigger in note.triggers:
        if trigger == "all":
            return True
        matched_types = TRIGGER_STATE_MAP.get(trigger)
        if matched_types is not None and state_type in matched_types:
            return True
    return False
```

### Retrieval

`get_strategic_thread(max_entries=5, *, current_context="")`:
1. If `current_context` is non-empty, filter to notes where `_note_matches_context(note, current_context)` is True
2. Take last `max_entries` from filtered list
3. Format: `- [context_type] note` (same as current format)

### Expiry

| Hook | Location | Clears |
|------|----------|--------|
| Round start | `_hcm_start_round()` | `scope == TURN` |
| Combat end | `_hcm_end_combat()` after `stm.end_combat()` | `scope in (TURN, COMBAT)` |
| New run | `reset_run()` | All |

Methods on `ShortTermMemory`:
- `expire_turn_notes()` — remove all with `scope == TURN`
- `expire_combat_notes()` — remove all with `scope in (TURN, COMBAT)`

### Tool Schema Changes

Add two optional fields to 6 tools (MAP, REST, EVENT, SHOP, CARD_REWARD, CARD_SELECT):

```python
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
```

Not added to: COMBAT_PLAN (uses `note_to_future_self`), HAND_SELECT, TREASURE, RELIC_SELECT, POTION.

### Recording Guard

Only these state types may record strategic notes:

```python
_STRATEGIC_NOTE_STATE_TYPES = {
    "card_reward", "shop", "map", "rest_site", "event", "card_select"
}
```

`_record_strategic_note()` returns early if `context_type not in _STRATEGIC_NOTE_STATE_TYPES`.

### Schema Hint Fix

`decision_parser.py:format_decision_schema_hint()` line 193: replace unconditional `"Optional: strategic_note"` with conditional check. Only emit for tools in `{"map_action", "rest_action", "event_action", "shop_action", "card_reward_action", "card_select_action"}`. Updated hint text: `"Optional: strategic_note, note_scope (turn|combat|run), note_triggers (combat|deck_building|routing|all)"`.

### Combat Start Dedup Fix

In `loop.py` combat start block (~line 1278), strip `short_term_hints` from `WorkingContext` before formatting, since the STM thread is already injected separately via `add_combat_start(strategic_thread=...)`:

```python
if wc is not None:
    from dataclasses import replace
    wc_no_thread = replace(wc, short_term_hints=())
    mem_str = format_working_context(wc_no_thread)
```

Apply same fix at eval-reload combat start block (~line 1797).

### Injection Points

All callers of `get_strategic_thread()` pass `current_context`:

| Caller | current_context |
|--------|----------------|
| Combat start (`loop.py ~1325`) | `gs.state_type` |
| Route selection (`loop.py ~4796`) | `"map"` |
| Memory retriever (`retriever.py:339`) | `gs.state_type` |

## Files Modified

| File | Changes |
|------|---------|
| `src/memory/short_term.py` | `NoteScope`, `StrategicNote`, `TRIGGER_STATE_MAP`, scoped storage, expiry methods, filtered retrieval |
| `src/agent/loop.py` | Recording whitelist, scope/trigger parsing, expiry hooks, combat start dedup, `current_context` args |
| `src/brain/tool_schemas.py` | `note_scope` + `note_triggers` on 6 tools |
| `src/brain/decision_parser.py` | Conditional schema hint for strategic_note tools only |
| `src/memory/retriever.py` | Pass `current_context=gs.state_type` to `get_strategic_thread` |

## What Does NOT Change

- `note_to_future_self` in `CombatConversation._strategic_notes` — untouched, continues as combat-internal round-to-round memory
- `prompt_injector.py` — formatting logic unchanged, just receives filtered data
- Memory retriever structure — only the `get_strategic_thread` call gets a new kwarg
- `conversation.py` — no changes needed (dedup is fixed in loop.py caller side)

## Verification

1. Run `python -m pytest tests/ -x` — all existing tests pass
2. Grep logs for `[hand_select]` in strategic thread — should be zero after fix
3. Combat start msg[0] has exactly ONE "## Strategic Thread" section
4. Gameplay test: write a `scope=combat` note during a fight → verify it disappears from thread after combat ends
5. Gameplay test: write a `triggers=["deck_building"]` note → verify it appears during card_reward but NOT during combat planning
