# Core-Engine Merge to Turn 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Merge the postrun `core_engine` stage into Turn 2 (`card_note_updater`) so a single LLM call produces both per-card note updates and (on Act 3 boss victory) structured engine observations, sharing the trace cache and incidentally fixing the silent gpt-5.4-mini routing bug.

**Architecture:** Turn 2's prompt is extended with a conditional schema for an `core_engine` block, gated by an `is_act3_boss_victory` parameter. When true, the user message tail includes the final deck + relics; the LLM emits both `updates` and `core_engine`. The existing `core_engine_extractor.apply_to_card_memory` writer is reused; the unused prompt-builder functions there are deleted. The `core_engine` postrun stage in `_safe_post_run` is removed.

**Tech Stack:** Python 3.12, pytest, async/await, dataclasses (frozen). No new libraries.

**Spec:** [`docs/superpowers/specs/2026-04-25-core-engine-merge-to-turn2-design.md`](../specs/2026-04-25-core-engine-merge-to-turn2-design.md)

---

## File Map

| File | Action | Notes |
|---|---|---|
| `src/memory/card_note_updater.py` | Modify | Add `Turn2Result` dataclass; add `parse_core_engine_block`; extend prompt strings; extend `update_card_notes_from_traces` signature + body |
| `src/memory/core_engine_extractor.py` | Modify | Delete `build_analysis_prompt`, `package_round_context`, `select_top_damage_rounds`, `extract_core_engine` (lines ~67-87, ~90-200, ~291-465); update module docstring |
| `src/agent/loop.py` | Modify | Delete `_post_run_core_engine_update` (L4353-4451); delete `_load_run_log_events_for_core_engine` (L4453-4480); delete the `core_engine` stage block in `_safe_post_run` (L2856-2883); update Turn 2 call site (L4337-4344) |
| `src/log/session_logger.py` | Audit + maybe modify | If a hardcoded `core_engine` stage row exists, remove |
| `src/brain/llm_caller.py` | Modify | Add WARNING comment above L108 about the heuristic trap |
| `tests/test_card_note_updater.py` | Modify | Add ~7 new test cases covering Turn 2 expansion |
| `tests/test_core_engine_extractor.py` | Modify | Delete 7 tests (`test_select_top_damage_rounds_*`, `test_package_round_context_*`, `test_extract_core_engine_*`) |

---

## Task 1: Add `Turn2Result` Dataclass

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_card_note_updater.py`:

```python
def test_turn2_result_default_shape():
    from src.memory.card_note_updater import Turn2Result
    r = Turn2Result()
    assert r.notes_written == 0
    assert r.notes_kept_unchanged == 0
    assert r.notes_invalid == 0
    assert r.core_engine_applied == 0
    assert r.core_engine_emitted is False


def test_turn2_result_is_frozen():
    from src.memory.card_note_updater import Turn2Result
    r = Turn2Result()
    with pytest.raises((AttributeError, Exception)):
        r.notes_written = 5  # type: ignore[misc]
```

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_card_note_updater.py::test_turn2_result_default_shape tests/test_card_note_updater.py::test_turn2_result_is_frozen -v
```
Expected: FAIL with `ImportError` (Turn2Result not defined).

- [ ] **Step 3: Add the dataclass**

Edit `src/memory/card_note_updater.py`. Add after the existing `from src.memory.models_v2 import ...` line:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Turn2Result:
    """Outcome of one card_note_updater (Turn 2) invocation.

    Captures both the existing card-note channel and the new core_engine
    channel introduced when this stage absorbed the deleted core_engine
    postrun stage. ``core_engine_emitted`` distinguishes "LLM produced an
    engine block" (True) from "LLM produced an empty / no-engine result"
    (False) — useful for telemetry on gate-on / no-engine-found runs.
    """
    notes_written: int = 0
    notes_kept_unchanged: int = 0
    notes_invalid: int = 0
    core_engine_applied: int = 0
    core_engine_emitted: bool = False
```

- [ ] **Step 4: Run tests, verify they pass**

```
pytest tests/test_card_note_updater.py::test_turn2_result_default_shape tests/test_card_note_updater.py::test_turn2_result_is_frozen -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(card-note-updater): add Turn2Result dataclass for merged Turn 2 output"
```

---

## Task 2: Add `parse_core_engine_block` Helper

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_card_note_updater.py`:

```python
def test_parse_core_engine_block_returns_emitted_with_validated_engine():
    """LLM emitted a valid, non-empty engine block."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '{"updates": [],'
        ' "core_engine": {'
        '   "engine_mechanic": "stacking passive damage while stalling",'
        '   "core_cards": ["Noxious Fumes"],'
        '   "support_cards": ["Prepared"],'
        '   "notes": "debuff stack"'
        ' }}'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True
    assert eng is not None
    assert eng["engine_mechanic"] == "stacking passive damage while stalling"
    assert eng["core_cards"] == ["Noxious Fumes"]
    assert eng["support_cards"] == ["Prepared"]
    assert eng["notes"] == "debuff stack"


def test_parse_core_engine_block_field_absent_means_not_emitted():
    """LLM did not emit the core_engine field at all."""
    from src.memory.card_note_updater import parse_core_engine_block

    emitted, eng = parse_core_engine_block('{"updates": []}')
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_empty_sentinel_is_emitted_but_no_engine():
    """LLM emitted core_engine but said 'no clear scaling engine' — empty
    mechanic + empty core_cards. Per spec §6 this is a LEGITIMATE outcome:
    emitted=True (the LLM tried), eng=None (no apply call). This
    distinction matters for telemetry."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "", "core_cards": [],'
        '                 "support_cards": [], "notes": ""}}'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True   # LLM did emit the field
    assert eng is None       # but no engine to apply


def test_parse_core_engine_block_bad_outer_json_is_not_emitted():
    """Malformed JSON: cannot tell if engine was intended → not emitted."""
    from src.memory.card_note_updater import parse_core_engine_block
    emitted, eng = parse_core_engine_block("not json {")
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_non_dict_engine_is_not_emitted():
    """LLM gave the field but it's not a dict → treat as not-emitted
    (we cannot extract anything from it; warning logging is the caller's
    job)."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = '{"updates": [], "core_engine": "not a dict"}'
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_strips_code_fence():
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '```json\n'
        '{"updates": [], "core_engine": {'
        '   "engine_mechanic": "M", "core_cards": ["X"],'
        '   "support_cards": [], "notes": "N"}}\n'
        '```'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True
    assert eng is not None
    assert eng["engine_mechanic"] == "M"
```

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_card_note_updater.py -k "parse_core_engine_block" -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add the helper**

Edit `src/memory/card_note_updater.py`. After `parse_note_updates` (after the existing function body), add:

```python
def parse_core_engine_block(raw_text: str) -> tuple[bool, dict | None]:
    """Extract and validate the optional ``core_engine`` field from the
    Turn 2 response.

    Returns ``(emitted, engine_or_none)``:
      - ``(True, dict)``: LLM emitted a valid non-empty engine block.
        Caller MUST invoke ``apply_to_card_memory(engine, ...)``.
      - ``(True, None)``: LLM emitted the field but with empty mechanic
        AND empty core_cards (the "no clear engine" sentinel). Caller
        must NOT apply, but must log this as a legitimate outcome
        (telemetry distinguishes it from absence).
      - ``(False, None)``: field absent OR outer JSON malformed OR
        engine is not a dict. Caller does nothing.

    Independent of ``parse_note_updates``: each function parses the
    outer envelope itself. The overhead is negligible for Turn 2's
    single-response volume; the simplicity is worth it.
    """
    raw = (raw_text or "").strip()
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[1] if "\n" in raw else raw[3:]
        if raw.endswith("```"):
            raw = raw[:-3]
        raw = raw.strip()

    try:
        parsed = json.loads(raw)
    except Exception:
        return False, None
    if not isinstance(parsed, dict):
        return False, None

    if "core_engine" not in parsed:
        return False, None
    engine = parsed.get("core_engine")
    if not isinstance(engine, dict):
        # Field present but unusable. Treat as not-emitted (we can't
        # extract anything); caller can warn separately if needed.
        return False, None

    mechanic = str(engine.get("engine_mechanic", "") or "").strip()
    core_cards = [str(c) for c in (engine.get("core_cards") or []) if c]
    support_cards = [str(c) for c in (engine.get("support_cards") or []) if c]
    notes = str(engine.get("notes", "") or "").strip()

    # Sentinel: empty mechanic AND empty core_cards → "no engine found".
    # The LLM emitted the field deliberately, so emitted=True; but the
    # contents are not applyable, so engine=None.
    if not mechanic and not core_cards:
        return True, None

    return True, {
        "engine_mechanic": mechanic,
        "core_cards": core_cards,
        "support_cards": support_cards,
        "notes": notes,
    }
```

- [ ] **Step 4: Run tests, verify they pass**

```
pytest tests/test_card_note_updater.py -k "parse_core_engine_block" -v
```
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(card-note-updater): add parse_core_engine_block helper for Turn 2 merge"
```

---

## Task 3: Extend System Prompt with Conditional `core_engine` Rules

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_card_note_updater.py`:

```python
def test_system_prompt_documents_core_engine_conditional():
    """The system prompt must instruct the LLM to emit `core_engine`
    iff the user message says 'this run won the Act 3 final boss'.

    Locking literal phrases here is intentional: the user-message
    section header MUST match what the system prompt references."""
    from src.memory.card_note_updater import _NOTE_UPDATER_SYSTEM
    assert "core_engine" in _NOTE_UPDATER_SYSTEM
    assert "Act 3 final boss" in _NOTE_UPDATER_SYSTEM
    assert "engine_mechanic" in _NOTE_UPDATER_SYSTEM
    assert "core_cards" in _NOTE_UPDATER_SYSTEM
    assert "Omit" in _NOTE_UPDATER_SYSTEM or "omit" in _NOTE_UPDATER_SYSTEM
```

- [ ] **Step 2: Run test, verify it fails**

```
pytest tests/test_card_note_updater.py::test_system_prompt_documents_core_engine_conditional -v
```
Expected: FAIL — current prompt does not mention `core_engine`.

- [ ] **Step 3: Extend the system prompt**

Edit `src/memory/card_note_updater.py`. Replace the existing `_NOTE_UPDATER_SYSTEM` constant body's trailing line ("Empty list if nothing in the traces warrants an update. Never invent cards. Only use card names that appear in the provided candidate list.") so the constant becomes:

```python
_NOTE_UPDATER_SYSTEM = (
    "You review postrun combat traces and selectively propose updates to "
    "per-card notes. A note is a <=200-character deck-building hint that "
    "surfaces when the card appears in a reward / shop / card_select "
    "decision. It should capture non-obvious role or risk information that "
    "aggregated counters cannot express.\n\n"
    "Output STRICTLY a JSON object with this shape:\n"
    "{\n"
    '  "updates": [\n'
    "    {\n"
    '      "card_name": "<one of the provided candidates, lowercase>",\n'
    '      "new_note": "<= 200 chars, concrete and forward-looking",\n'
    '      "reason": "<1 line — why this note, what trace moment justifies it>",\n'
    '      "trace_citation": "<short quote from trace, e.g. \'Combat 2 R3: '
    "played Backstab for 11 dmg after Sly'>\"\n"
    "    }\n"
    "  ]\n"
    "}\n\n"
    "Empty list if nothing in the traces warrants an update. Never invent "
    "cards. Only use card names that appear in the provided candidate list.\n\n"
    "Additionally, when the calling instructions explicitly state "
    "\"this run won the Act 3 final boss\", you MUST also output a "
    "`core_engine` field alongside `updates`:\n"
    "{\n"
    '  "core_engine": {\n'
    '    "engine_mechanic": "<abstract description of how the deck scaled, '
    "e.g. \\\"stacking continuous passive debuff damage while stalling\\\">\",\n"
    '    "core_cards": ["<1-3 card or relic names that provided '
    "multiplicative scaling>\"],\n"
    '    "support_cards": ["<cards that generated, applied, or cycled the '
    "mechanic; may be empty>\"],\n"
    '    "notes": "<1-2 sentences describing the synergy concretely>"\n'
    "  }\n"
    "}\n\n"
    "Rules: (1) core_cards must reference cards in the provided final "
    "deck or relics. (2) engine_mechanic is abstract — do NOT use "
    "archetype labels (shiv/poison/panache/etc.); describe the action or "
    "trigger. (3) If the win came from raw tempo with no clear scaling "
    "engine, engine_mechanic should say so and core_cards may be empty. "
    "(4) Omit the `core_engine` field entirely when the calling "
    "instructions do not mention \"Act 3 final boss\"."
)
```

- [ ] **Step 4: Run test, verify it passes**

```
pytest tests/test_card_note_updater.py::test_system_prompt_documents_core_engine_conditional -v
```
Expected: PASS.

- [ ] **Step 5: Run full test file to confirm no regressions**

```
pytest tests/test_card_note_updater.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(card-note-updater): extend system prompt with conditional core_engine schema"
```

---

## Task 4: Add Conditional User-Message Section Helper

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_card_note_updater.py`:

```python
def test_render_act3_victory_section_includes_phrase_and_cards():
    """The literal phrase 'Act 3 final boss' must appear so the
    system-prompt rule fires, plus deck and relic listings."""
    from src.memory.card_note_updater import _render_act3_victory_section

    deck = ["Strike", "Backstab", "Noxious Fumes", "Defend"]
    relics = ["Burning Blood", "Snake Skull"]
    text = _render_act3_victory_section(deck, relics)
    assert "Act 3 final boss" in text
    for card in deck:
        assert card in text
    for relic in relics:
        assert relic in text
    # Must instruct LLM to output core_engine
    assert "core_engine" in text


def test_render_act3_victory_section_handles_empty_relics():
    from src.memory.card_note_updater import _render_act3_victory_section

    text = _render_act3_victory_section(["Strike"], [])
    assert "Act 3 final boss" in text
    assert "Strike" in text
    # Empty relics list shouldn't break the rendering
    assert text  # non-empty


def test_render_act3_victory_section_handles_empty_deck():
    """Should still render the gating phrase even if deck is unknown."""
    from src.memory.card_note_updater import _render_act3_victory_section

    text = _render_act3_victory_section([], ["Burning Blood"])
    assert "Act 3 final boss" in text
    assert "Burning Blood" in text
```

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_card_note_updater.py -k "render_act3_victory_section" -v
```
Expected: FAIL with `ImportError`.

- [ ] **Step 3: Add the helper**

Edit `src/memory/card_note_updater.py`. Add after `_render_candidate_table`:

```python
def _render_act3_victory_section(
    final_deck: list[str], final_relics: list[str],
) -> str:
    """Conditional user-message tail rendered only when this run won
    the Act 3 final boss.

    The literal phrase ``Act 3 final boss`` is the trigger keyword the
    system prompt looks for to require ``core_engine`` output; do not
    paraphrase.
    """
    lines = [
        "## This run won the Act 3 final boss",
        "",
        "Final deck (at end of run):",
    ]
    if final_deck:
        lines.extend(f"- {c}" for c in final_deck)
    else:
        lines.append("(deck not captured)")
    lines.append("")
    lines.append("Final relics:")
    if final_relics:
        lines.extend(f"- {r}" for r in final_relics)
    else:
        lines.append("(no relics captured)")
    lines.append("")
    lines.append(
        "Identify the core engine of this winning deck per the rules "
        "in the system prompt. Output the `core_engine` field "
        "alongside `updates`."
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests, verify they pass**

```
pytest tests/test_card_note_updater.py -k "render_act3_victory_section" -v
```
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(card-note-updater): add Act 3 victory section helper for conditional prompt"
```

---

## Task 5: Wire Both Channels into `update_card_notes_from_traces`

**Files:**
- Modify: `src/memory/card_note_updater.py`
- Test: `tests/test_card_note_updater.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_card_note_updater.py`:

```python
import asyncio
from unittest.mock import patch


def _mock_call_raw_factory(response_text: str):
    """Return an async stub that mimics call_raw's contract."""
    async def _stub(system, prompt, **kwargs):  # noqa: ARG001
        return response_text, 100.0, 500
    return _stub


def test_update_card_notes_returns_turn2_result():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import (
        Turn2Result,
        update_card_notes_from_traces,
    )

    store = CardMemoryStore()
    response = (
        '{"updates": ['
        '{"card_name":"strike","new_note":"reliable","reason":"r","trace_citation":"c"}'
        ']}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
        ))
    assert isinstance(result, Turn2Result)
    assert result.notes_written == 1
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is False


def test_update_card_notes_act3_victory_applies_engine():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {'
        '   "engine_mechanic": "stacking debuffs",'
        '   "core_cards": ["Noxious Fumes"],'
        '   "support_cards": ["Prepared"],'
        '   "notes": "debuff stack"'
        ' }}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="the silent",
            combat_trace_text="(trace)",
            candidate_cards=["Noxious Fumes", "Prepared"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Noxious Fumes", "Prepared", "Defend"],
            final_relics=["Snake Skull"],
        ))
    assert result.core_engine_emitted is True
    assert result.core_engine_applied == 2  # 1 core + 1 support
    obs_core = store.get("the silent", "Noxious Fumes")
    obs_supp = store.get("the silent", "Prepared")
    assert obs_core is not None and len(obs_core.core_engine_observations) == 1
    assert obs_core.core_engine_observations[0]["role"] == "core"
    assert obs_supp is not None and obs_supp.core_engine_observations[0]["role"] == "support"


def test_update_card_notes_drops_engine_when_gate_off():
    """LLM emits engine despite gate=False — must drop with warning."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "X", "core_cards": ["Y"],'
        '                 "support_cards": [], "notes": "N"}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Y"],
            run_id="r1",
            is_act3_boss_victory=False,  # gate OFF
        ))
    assert result.core_engine_emitted is False  # block dropped
    assert result.core_engine_applied == 0
    assert store.count == 0


def test_update_card_notes_act3_victory_empty_engine_is_legitimate():
    """Gate ON + LLM returns no-engine sentinel → noop write but
    emitted=True (LLM tried, said 'no clear engine'). Per spec §6 this
    is a legitimate outcome; telemetry distinguishes 'emitted but no
    engine' (LLM was honest) from 'not emitted' (LLM forgot)."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "", "core_cards": [],'
        '                 "support_cards": [], "notes": ""}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Strike"],
            final_relics=[],
        ))
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is True


def test_update_card_notes_act3_victory_field_omitted_is_not_emitted():
    """Gate ON + LLM omits core_engine field entirely → emitted=False."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = '{"updates": []}'  # no core_engine field
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Strike"],
            final_relics=[],
        ))
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is False


def test_update_card_notes_dry_run_blocks_engine_writes_too():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "M", "core_cards": ["X"],'
        '                 "support_cards": [], "notes": "N"}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["X"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["X"],
            final_relics=[],
            dry_run=True,
        ))
    assert result.core_engine_emitted is True   # parsed
    assert result.core_engine_applied == 0      # but not applied
    assert store.count == 0
```

- [ ] **Step 2: Run tests, verify they fail**

```
pytest tests/test_card_note_updater.py -k "update_card_notes_returns_turn2_result or update_card_notes_act3 or update_card_notes_drops_engine or update_card_notes_dry_run_blocks_engine" -v
```
Expected: FAIL — current function returns a 3-tuple, doesn't accept the new kwargs.

- [ ] **Step 3: Rewrite `update_card_notes_from_traces`**

Edit `src/memory/card_note_updater.py`. Replace the entire `update_card_notes_from_traces` function (currently at the bottom of the file, ~50 lines) with:

```python
async def update_card_notes_from_traces(
    *,
    store: CardMemoryStore,
    character: str,
    combat_trace_text: str,
    candidate_cards: list[str],
    run_id: str,
    is_act3_boss_victory: bool = False,
    final_deck: list[str] | None = None,
    final_relics: list[str] | None = None,
    dry_run: bool = False,
) -> Turn2Result:
    """Turn 2 entry point. Calls LLM, parses both channels, applies.

    Channels:
      - `updates`: per-card note updates (always solicited).
      - `core_engine`: block emitted by the LLM only when the user
        message contains the literal phrase "Act 3 final boss". The
        caller passes ``is_act3_boss_victory=True`` plus the final
        deck/relics to render that section. Off-gate emissions are
        dropped defensively (warning logged).

    Returns a ``Turn2Result`` summarizing both channels' outcomes.
    """
    from src.brain.llm_caller import call_raw

    if not combat_trace_text or not candidate_cards:
        return Turn2Result()

    char_norm = normalize_character(character)
    candidate_table = _render_candidate_table(store, char_norm, candidate_cards)
    prompt = _UPDATER_PROMPT_TEMPLATE.format(candidate_table=candidate_table)

    if is_act3_boss_victory:
        prompt = (
            prompt
            + "\n\n"
            + _render_act3_victory_section(
                list(final_deck or []), list(final_relics or []),
            )
        )

    try:
        raw_text, latency_ms, tokens = await call_raw(
            _NOTE_UPDATER_SYSTEM,
            prompt,
            think=False,
            call_type="card_note_update",
            user_cached_prefix=combat_trace_text,
        )
    except Exception:
        logger.warning("card_note_updater: LLM call failed", exc_info=True)
        return Turn2Result()

    logger.info(
        "card_note_updater: LLM call %.0fms, %d tokens", latency_ms, tokens,
    )

    candidate_set = {c.lower() for c in candidate_cards}
    proposals, invalid = parse_note_updates(raw_text, candidate_set)
    written = apply_note_updates(
        store, character=char_norm,
        proposals=proposals, run_id=run_id, dry_run=dry_run,
    )
    kept_unchanged = max(0, len(candidate_cards) - len(proposals) - invalid)

    # ── core_engine channel ─────────────────────────────────────
    engine_applied = 0
    engine_emitted = False
    if is_act3_boss_victory:
        engine_emitted, engine = parse_core_engine_block(raw_text)
        if engine is not None:
            if dry_run:
                logger.info(
                    "card_note_updater[DRY_RUN]: would apply core_engine "
                    "mechanic=%s core=%d support=%d",
                    engine["engine_mechanic"][:60],
                    len(engine["core_cards"]),
                    len(engine["support_cards"]),
                )
            else:
                from src.memory.core_engine_extractor import apply_to_card_memory
                engine_applied = apply_to_card_memory(
                    engine, store, character=char_norm, run_id=run_id,
                )
        elif engine_emitted:
            # Sentinel — LLM tried, said no engine. Spec §6 legitimate.
            logger.info(
                "card_note_updater: core_engine emitted as no-engine "
                "sentinel (no apply)"
            )
    else:
        # Gate off: detect off-gate leak and warn (purely observational;
        # parse_core_engine_block never produces apply input here).
        leaked, _leak = parse_core_engine_block(raw_text)
        if leaked:
            logger.warning(
                "card_note_updater: dropped off-gate core_engine emission "
                "(is_act3_boss_victory=False)"
            )

    logger.info(
        "postrun_trace: turn2 notes_written=%d kept=%d invalid=%d  "
        "engine_applied=%d engine_emitted=%s  (dry_run=%s)",
        written, kept_unchanged, invalid,
        engine_applied, engine_emitted, dry_run,
    )
    return Turn2Result(
        notes_written=written,
        notes_kept_unchanged=kept_unchanged,
        notes_invalid=invalid,
        core_engine_applied=engine_applied,
        core_engine_emitted=engine_emitted,
    )
```

- [ ] **Step 4: Run tests, verify they pass**

```
pytest tests/test_card_note_updater.py -v
```
Expected: all PASS (existing + new ones from Tasks 1-5).

- [ ] **Step 5: Commit**

```
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(card-note-updater): merge core_engine output into Turn 2"
```

---

## Task 6: Update Turn 2 Call Site in `loop.py`

**Files:**
- Modify: `src/agent/loop.py:4326-4346`

- [ ] **Step 1: Read the current call site**

```
sed -n '4326,4346p' src/agent/loop.py
```

(Use the Read tool with offset=4326 limit=21 — the snippet starts at line 4326.)

- [ ] **Step 2: Replace the Turn 2 call site**

Edit `src/agent/loop.py`. Find the block:

```python
            # Turn 2 — card note updater (only when trace is non-empty and
            # card_memory_store is available).
            if combat_trace_text and self._memory and getattr(
                self._memory, "card_memory_store", None,
            ):
                from src.memory.card_note_updater import update_card_notes_from_traces

                # candidates were extracted from the same combats that produced the trace.
                if candidates:
                    dry = not config.POSTRUN_NOTE_UPDATE_ENABLED
                    try:
                        await update_card_notes_from_traces(
                            store=self._memory.card_memory_store,
                            character=build_mem.character,
                            combat_trace_text=combat_trace_text,
                            candidate_cards=candidates,
                            run_id=build_mem.run_id,
                            dry_run=dry,
                        )
                    except Exception:
                        logger.warning("postrun_trace: Turn 2 failed", exc_info=True)
```

Replace with:

```python
            # Turn 2 — card note updater (only when trace is non-empty and
            # card_memory_store is available). Also absorbs the deleted
            # core_engine postrun stage on Act 3 boss victories: the merged
            # call emits an additional `core_engine` block which is parsed
            # and applied to per-card observations in the same store write.
            if combat_trace_text and self._memory and getattr(
                self._memory, "card_memory_store", None,
            ):
                from src.memory.card_note_updater import update_card_notes_from_traces
                from src.memory.core_engine_extractor import find_final_boss_combat

                # candidates were extracted from the same combats that produced the trace.
                if candidates:
                    dry = not config.POSTRUN_NOTE_UPDATE_ENABLED
                    # Gate the core_engine output on confirmed Act 3 boss
                    # victory in this run. Reuses the existing helper.
                    episodes = (
                        self._memory.combat_store.get_all()
                        if self._memory.combat_store else []
                    )
                    act3_boss = find_final_boss_combat(
                        episodes, run_id=build_mem.run_id,
                    )
                    is_act3 = act3_boss is not None
                    final_deck: list[str] = []
                    final_relics: list[str] = []
                    if act3_boss is not None:
                        if act3_boss.context and act3_boss.context.deck_cards:
                            final_deck = list(act3_boss.context.deck_cards)
                        final_relics = list(act3_boss.relics or ())
                    try:
                        result = await update_card_notes_from_traces(
                            store=self._memory.card_memory_store,
                            character=build_mem.character,
                            combat_trace_text=combat_trace_text,
                            candidate_cards=candidates,
                            run_id=build_mem.run_id,
                            is_act3_boss_victory=is_act3,
                            final_deck=final_deck,
                            final_relics=final_relics,
                            dry_run=dry,
                        )
                        logger.info(
                            "postrun_trace: turn2 result %s",
                            result,
                        )
                    except Exception:
                        logger.warning("postrun_trace: Turn 2 failed", exc_info=True)
```

- [ ] **Step 3: Run all tests to confirm no regressions**

```
pytest tests/ -x -q
```
Expected: all PASS (some unrelated tests may already be broken — accept the same status as before this task).

- [ ] **Step 4: Commit**

```
git add src/agent/loop.py
git commit -m "feat(loop): wire Turn 2 call site for core_engine merge"
```

---

## Task 7: Delete `_post_run_core_engine_update` and the Stage Block

**Files:**
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Locate the stage block in `_safe_post_run`**

Find the block at L2856-2883 of `src/agent/loop.py`. It begins with the comment `# Core-engine identification (victory-only):` and ends with `session_logger.log_post_run_stage("core_engine", "skipped")`.

- [ ] **Step 2: Delete the stage block**

Remove the entire block (~28 lines):

```python
            # Core-engine identification (victory-only): analyze the Act 3
            # boss top-3 rounds with the analysis-tier LLM and write
            # structured observations to each contributing card's
            # CardMemory. This grounds the abstract two-phase deckbuilding
            # prompt with concrete card-level knowledge without putting
            # card names into the prompt itself.
            if self._memory and self._use_llm:
                if session_logger:
                    session_logger.log_post_run_stage("core_engine", "start")
                try:
                    applied = await self._post_run_core_engine_update()
                except Exception as exc:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "core_engine",
                            "failed",
                            error=str(exc) or type(exc).__name__,
                        )
                    logger.warning("Post-run core-engine stage failed", exc_info=True)
                else:
                    if session_logger:
                        session_logger.log_post_run_stage(
                            "core_engine",
                            "done",
                            cards_updated=applied,
                        )
            elif session_logger:
                session_logger.log_post_run_stage("core_engine", "skipped")
```

- [ ] **Step 3: Delete `_post_run_core_engine_update` method**

Delete the entire method body at L4353-4451 (~99 lines), including its docstring and the section comment `# ── Post-run core-engine identification ─────────────────────`.

- [ ] **Step 4: Delete `_load_run_log_events_for_core_engine` method**

Delete the entire method body at L4453-4480 (~28 lines).

- [ ] **Step 5: Verify `find_final_boss_combat` import is still healthy**

The Turn 2 call site (Task 6) still imports `find_final_boss_combat`. Confirm:

```
grep -n "find_final_boss_combat" src/agent/loop.py
```
Expected: at least one match (the import added in Task 6). If zero, Task 6 was applied wrong.

- [ ] **Step 6: Also delete the disabled-postrun core_engine stage line**

Find the early-return block in `_safe_post_run`:

```python
            if session_logger:
                session_logger.log_post_run_start(...)
                session_logger.log_post_run_stage("memory", "skipped", reason=reason)
                session_logger.log_post_run_stage("skills", "skipped", reason=reason)
                session_logger.log_post_run_stage("evolution", "skipped", reason=reason)
                session_logger.log_post_run_end()
            return
```

There should be no `core_engine` line in this block — but verify and remove if present (likely already absent since this lists the four stages separately and the original code may have been: memory / skills / evolution + a missed core_engine entry).

```
grep -n 'log_post_run_stage("core_engine"' src/agent/loop.py
```
Expected: 0 matches after Task 7 is complete. If any remain, delete them.

- [ ] **Step 7: Run tests**

```
pytest tests/ -x -q
```
Expected: all PASS (some tests in `test_core_engine_extractor.py` will start failing here because they import deleted functions — that's Task 8's job. If failure count exceeds 7, debug.)

- [ ] **Step 8: Commit**

```
git add src/agent/loop.py
git commit -m "refactor(loop): remove core_engine postrun stage (merged into Turn 2)"
```

---

## Task 8: Drop Superseded Tests in `test_core_engine_extractor.py`

**Files:**
- Modify: `tests/test_core_engine_extractor.py`

- [ ] **Step 1: List the tests to delete**

Open `tests/test_core_engine_extractor.py` and locate (use grep + line numbers):

| Test name | Reason |
|---|---|
| `test_select_top_damage_rounds_returns_top_n_by_damage` | function deleted |
| `test_select_top_damage_rounds_handles_fewer_rounds_than_n` | function deleted |
| `test_select_top_damage_rounds_ties_broken_by_round_num` | function deleted |
| `test_package_round_context_includes_required_fields` | function deleted |
| `test_package_round_context_enriches_hand_from_run_log` | function deleted |
| `test_extract_core_engine_calls_llm_with_structured_prompt` | function deleted |
| `test_extract_core_engine_handles_malformed_llm_output` | function deleted |

Also delete the `# ── Cycle 3: ...`, `# ── Cycle 4: ...`, `# ── Cycle 6: ...` section-divider comments that bracket these.

- [ ] **Step 2: Delete the tests**

Use the Edit tool to remove each test function body and its preceding section comment. Concretely: delete the file region from the line above `# ── Cycle 3: select_top_damage_rounds ───────────────────────` through the last line of `test_extract_core_engine_handles_malformed_llm_output`. Cycle 5 (`test_apply_*`) sits between Cycles 4 and 6 — do NOT delete those tests; preserve them in place.

The simplest approach: open the file in an editor and identify the precise byte ranges by section comments; delete the blocks.

- [ ] **Step 3: Run the test file**

```
pytest tests/test_core_engine_extractor.py -v
```
Expected: all remaining tests PASS, no `ImportError`.

- [ ] **Step 4: Commit**

```
git add tests/test_core_engine_extractor.py
git commit -m "test(core-engine): drop tests for deleted prompt-build functions"
```

---

## Task 9: Delete the Four Unused Functions in `core_engine_extractor.py`

**Files:**
- Modify: `src/memory/core_engine_extractor.py`

- [ ] **Step 1: Identify the targets**

Functions to delete (verify line numbers with grep before each delete):

| Function | Reason |
|---|---|
| `select_top_damage_rounds` | unused after merge |
| `package_round_context` | unused after merge (and its private helpers if any) |
| `build_analysis_prompt` | unused after merge |
| `extract_core_engine` | unused after merge |

- [ ] **Step 2: Delete `select_top_damage_rounds`**

Locate via:
```
grep -n "^def select_top_damage_rounds" src/memory/core_engine_extractor.py
```

Delete the function (definition through the last line of its body) plus its preceding section comment `# ── Cycle 3: ...`.

- [ ] **Step 3: Delete `package_round_context` and its private helpers**

Locate via:
```
grep -n "^def package_round_context\|^def _" src/memory/core_engine_extractor.py
```

Delete `package_round_context` and any private `_helper` functions used only by it (verify with grep that they have no other callers in `src/`). The known target is the `# ── Cycle 4: ...` section.

- [ ] **Step 4: Delete `build_analysis_prompt`**

Locate via:
```
grep -n "^def build_analysis_prompt" src/memory/core_engine_extractor.py
```

Delete the function. Caution: this function is large (~100 lines).

- [ ] **Step 5: Delete `extract_core_engine`**

Locate via:
```
grep -n "^def extract_core_engine" src/memory/core_engine_extractor.py
```

Delete the function plus its preceding `# ── Cycle 6: ...` section comment.

- [ ] **Step 6: Update the module docstring**

The file's top-of-module docstring describes the orchestration pipeline (`extract_core_engine`, `build_analysis_prompt`, etc.) that no longer exists. Replace it with:

```python
"""Postrun core-engine writers and retrieval helpers.

Identifies winning-deck core engines via Turn 2 of the postrun
combat-trace pipeline (see ``card_note_updater.py``) and writes
structured observations back to each contributing card's CardMemory.

Public surface:
- ``find_final_boss_combat(episodes, run_id)`` — predicate used by the
  Turn 2 caller to gate on Act 3 boss victory.
- ``apply_to_card_memory(result, store, character, run_id)`` — append
  per-card observations from a parsed engine dict.
- ``parse_analysis_response(raw)`` / ``empty_result()`` — JSON parsers
  for engine blocks (now invoked from card_note_updater).
- ``format_core_engine_hint(memory)`` — prompt-side renderer used by
  the retriever to surface observations at deck-decision time.

The prompt-building / LLM-orchestration functions that previously lived
here (build_analysis_prompt, package_round_context,
select_top_damage_rounds, extract_core_engine) were deleted when the
core_engine postrun stage was merged into Turn 2 (see spec
2026-04-25-core-engine-merge-to-turn2-design.md).
"""
```

- [ ] **Step 7: Verify nothing else in the codebase imports the deleted symbols**

```
grep -rn "select_top_damage_rounds\|package_round_context\|build_analysis_prompt\|extract_core_engine" src/ tests/
```
Expected: 0 matches (all references should have been deleted in Tasks 7 and 8). If any remain, fix them now.

- [ ] **Step 8: Run all tests**

```
pytest tests/ -x -q
```
Expected: all PASS.

- [ ] **Step 9: Commit**

```
git add src/memory/core_engine_extractor.py
git commit -m "refactor(core-engine): delete unused prompt-build and orchestration functions"
```

---

## Task 10: Audit `session_logger.py` and Add the `llm_caller` Warning

**Files:**
- Audit: `src/log/session_logger.py`
- Modify: `src/brain/llm_caller.py`

- [ ] **Step 1: Audit session_logger for hardcoded core_engine references**

```
grep -n "core_engine" src/log/session_logger.py
```

If ANY match: open the file, examine each match. Most likely results: stage-name allowlists, monitor table column setups. Remove any references that hardcode the `core_engine` stage. If 0 matches, this step is a noop.

- [ ] **Step 2: Audit the monitor frontend (if present in repo)**

```
grep -rn "core_engine" frontend/ 2>/dev/null
```

If matches: open them, evaluate. Most likely: a stage-table row or stage-name lookup. The change here may be UI-only (stage row disappears). Apply minimum fix.

(If `frontend/` is absent or returns 0 matches, skip.)

- [ ] **Step 3: Add the WARNING comment to llm_caller**

Edit `src/brain/llm_caller.py`. Locate the heuristic at L108:

```python
    # Determine call class for router
    if not call_class:
        if openai_relay_profile == "default":
            ...
```

Insert immediately above the `if not call_class:` line:

```python
    # Determine call class for router
    # WARNING: this name-based heuristic routes any call_type containing
    # "summary" or "consolidat" to the postrun_summary chain (monitor's
    # gpt-5.4-mini), which is wrong for analysis-tier work. The previously
    # bug-inducing call_type "core_engine_summary" was removed in
    # 2026-04-25-core-engine-merge-to-turn2 by deleting the call site;
    # any future caller whose call_type contains those substrings but
    # actually wants the analysis tier MUST pass explicit
    # call_class="postrun_analysis" to bypass this heuristic.
    if not call_class:
```

- [ ] **Step 4: Run all tests**

```
pytest tests/ -x -q
```
Expected: all PASS.

- [ ] **Step 5: Commit**

```
git add src/brain/llm_caller.py src/log/session_logger.py
git commit -m "chore: warn about postrun_summary heuristic; drop stale core_engine stage refs"
```

(If `session_logger.py` was unchanged in step 1, omit it from `git add`.)

---

## Task 11: Final Verification

**Files:** none modified.

- [ ] **Step 1: Full test suite**

```
pytest tests/ -q
```
Expected: same pass/fail count as `git log -1 --before=<plan-start>` baseline. If new failures, debug.

- [ ] **Step 2: Search for stale references**

```
grep -rn "core_engine_summary\|_post_run_core_engine_update\|_load_run_log_events_for_core_engine" src/ tests/
```
Expected: 0 matches.

- [ ] **Step 3: Confirm stage-count change**

```
grep -n 'log_post_run_stage(' src/agent/loop.py | grep -E "memory|skills|evolution|core_engine"
```
Expected: matches for `memory`, `skills`, `evolution` (in start/done/failed/skipped variations); zero matches for `core_engine`.

- [ ] **Step 4: Smoke run (optional, requires live setup)**

```
python -m scripts.run_agent --steps 80 --runs 1 --no-llm
```
Expected: clean run end; stage log shows three stages (memory / skills / evolution), not four.

- [ ] **Step 5: Final commit (if any cleanup arose)**

```
git status
git diff
```
If any unintended changes remain, address; otherwise this task is purely verification.

---

## Spec Coverage Self-Check

| Spec section | Task(s) |
|---|---|
| §3.1 Stage diagram (4→3 segments) | Task 7 |
| §3.2 Turn 2 signature + Turn2Result | Tasks 1, 5 |
| §3.3 Prompt extension | Tasks 3, 4 |
| §3.4 Output schema | Task 2 |
| §3.5 Parsing & validation (gate logic) | Tasks 2, 5 |
| §3.6 Caller wiring (loop.py) | Task 6 |
| §3.7 Files affected — modifications | Tasks 5, 6, 7, 9, 10 |
| §3.7 Files affected — deletions | Tasks 7, 9 |
| §4 Config (no new env vars) | covered by absence of changes |
| §5 Caching (cached prefix preserved) | implicit in Task 5 (no change to `user_cached_prefix` arg) |
| §6 Error handling (per-channel fail-closed) | Task 5 |
| §7 Observability (consolidated log line, monitor row) | Tasks 5 (log line), 10 (monitor) |
| §8 Testing strategy | Tasks 1-5 (new tests), 8 (deleted tests) |
| §9 Bug-fix-implicit + comment | Task 10 |
