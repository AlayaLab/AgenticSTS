# First-encounter guide / card-note write Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make postrun guide consolidation always write a guide on the first encounter with any enemy / event / route / deck-archetype, and force the card-note updater to propose a note for any candidate card whose `current_note` is empty.

**Architecture:** Two independent tracks. Track A is a prompt-only change in [`card_note_updater.py`](../../../src/memory/card_note_updater.py) — the LLM call already runs unconditionally, so strengthening the prompt suffices. Track B is a code-level bypass in 4 guide consolidators: when `existing_guide is None` and there is ≥1 (non-aborted) record, the `min_episodes=2` gate is skipped. Combat additionally needs a selection-layer override so small non-worst monsters are not filtered out.

**Tech Stack:** Python 3.14, pytest (with `pytest-asyncio` for async tests), dataclasses.

**Spec:** [`docs/superpowers/specs/2026-04-28-first-encounter-guide-write-design.md`](../specs/2026-04-28-first-encounter-guide-write-design.md)

---

## Task 1: Track A — card_note_updater prompt strengthening

**Files:**
- Modify: `src/memory/card_note_updater.py:100-114` (`_UPDATER_PROMPT_TEMPLATE`)
- Test: `tests/test_card_note_updater.py` (extend existing or create)

- [ ] **Step 1: Check whether a test file already exists**

```bash
ls tests/test_card_note_updater*.py 2>/dev/null
```

If it exists, append. If not, create.

- [ ] **Step 2: Write the failing snapshot test**

Create or append to `tests/test_card_note_updater.py`:

```python
"""Snapshot tests for the card_note_updater prompt template."""
from __future__ import annotations

from src.memory.card_note_updater import _UPDATER_PROMPT_TEMPLATE


def test_prompt_contains_mandatory_first_note_rule():
    """The prompt MUST contain the literal 'MANDATORY first-note rule' phrase
    so the LLM is forced to write notes for empty-noted candidates that
    appear in the trace.
    """
    assert "MANDATORY first-note rule" in _UPDATER_PROMPT_TEMPLATE


def test_prompt_references_actual_empty_note_renderings():
    """The prompt's empty-note literal must match what _render_candidate_table
    actually emits: '(empty)' or '(no memory yet)'.
    """
    assert "(empty)" in _UPDATER_PROMPT_TEMPLATE
    assert "(no memory yet)" in _UPDATER_PROMPT_TEMPLATE


def test_prompt_keeps_no_invent_safeguard():
    """The 'Never invent cards' guardrail must remain after the strengthening."""
    assert "Never invent cards" in _UPDATER_PROMPT_TEMPLATE
```

- [ ] **Step 3: Run tests to verify they fail**

```bash
python -m pytest tests/test_card_note_updater.py -v
```
Expected: 3 failures — `MANDATORY first-note rule`, `(empty)`, `(no memory yet)` are not yet in the prompt template.

- [ ] **Step 4: Strengthen the prompt template**

In `src/memory/card_note_updater.py`, replace lines 100-114 (`_UPDATER_PROMPT_TEMPLATE`) with:

```python
_UPDATER_PROMPT_TEMPLATE = """\
## Candidate cards (name | current_note | play_count | sly_play | total_damage | total_block)

{candidate_table}

## Instructions

For each candidate card, decide whether the traces at the top of this user
message justify a new or updated note.

**MANDATORY first-note rule:** For any candidate card whose `current_note`
column shows `(empty)` or `(no memory yet)` AND that appears at least once
in the trace (drawn, played, discarded, exhausted, or retained), you MUST
propose a `new_note`. Skip only if the card is in the candidate list but
the trace contains no evidence of it being interacted with.

For cards that already have a `current_note`, propose updates only when the
trace reveals something the current note misses. Keep new_note terse
(<=200 chars), concrete, and oriented toward future deck-building decisions.
Never invent cards not in the candidate list.

Respond with ONLY the JSON object.
"""
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_card_note_updater.py -v
```
Expected: 3 pass.

- [ ] **Step 6: Run wider test sweep to ensure no regression**

```bash
python -m pytest tests/ -k "card_note or card_memory" 2>&1 | tail -10
```
Expected: no new failures (any pre-existing failures unrelated).

- [ ] **Step 7: Commit**

```bash
git add src/memory/card_note_updater.py tests/test_card_note_updater.py
git commit -m "feat(memory): force card-note write when current_note is empty"
```

---

## Task 2: Track B — combat guide first-encounter bypass

**Files:**
- Modify: `src/memory/guide_consolidator.py:40-88` (`_select_combat_keys_for_refresh` signature + body)
- Modify: `src/memory/guide_consolidator.py:1106-1122` (call site + per-key loop)
- Test: `tests/test_guide_consolidator_first_encounter.py` (new)

The combat track is two-level: selection layer admits None-guide keys, and the per-key loop bypasses `min_episodes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/test_guide_consolidator_first_encounter.py`:

```python
"""Tests for first-encounter bypass in combat guide consolidation.

Spec: docs/superpowers/specs/2026-04-28-first-encounter-guide-write-design.md
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.memory.guide_consolidator import _select_combat_keys_for_refresh
from src.memory.models_v2 import CombatEpisode


def _ep(*, run_id, enemy_key, character, combat_type, act,
        is_aborted=False, hp_before=80, hp_after=60, won=True):
    """is_aborted on CombatEpisode is a property derived from terminal_reason."""
    return CombatEpisode(
        episode_id=f"ep-{enemy_key}-{run_id}",
        run_id=run_id,
        character=character,
        enemy_key=enemy_key,
        combat_type=combat_type,
        act=act,
        floor=1,
        hp_before=hp_before,
        hp_after=hp_after,
        won=won,
        rounds=(),
        terminal_reason="abort" if is_aborted else ("win" if won else "loss"),
    )


def test_select_without_guide_store_preserves_legacy_behavior():
    """Calling without guide_store kwarg must produce the exact historical
    selection (boss + elite + worst small monster per act)."""
    episodes = [
        _ep(run_id="r1", enemy_key="boss_a", character="Silent",
            combat_type="boss", act=1),
        _ep(run_id="r1", enemy_key="elite_a", character="Silent",
            combat_type="elite", act=1),
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),  # worst
    ]
    selected = _select_combat_keys_for_refresh(episodes, "r1")
    assert ("boss_a", "silent") in selected
    assert ("elite_a", "silent") in selected
    assert ("slug_b", "silent") in selected   # worst-of-act
    assert ("slug_a", "silent") not in selected  # filtered out


def test_select_with_empty_guide_store_admits_all_non_aborted_keys():
    """guide_store with no guides for any key must force ALL non-aborted
    keys from current run into the refresh set, even non-worst monsters."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)

    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug_a", "silent") in selected
    assert ("slug_b", "silent") in selected


def test_select_with_existing_guide_skips_first_encounter_bypass():
    """Keys that already have a guide do NOT get added by first-encounter
    logic — they fall back to the legacy selection rules."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),
    ]
    existing_guide = MagicMock()
    guide_store = MagicMock()
    # slug_a has a guide; slug_b does not
    guide_store.get_combat_guide = MagicMock(
        side_effect=lambda key, char: existing_guide if key == "slug_a" else None
    )

    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug_b", "silent") in selected   # bypass triggers (no guide)
    # slug_a: not worst-of-act AND has guide → NOT in selected
    assert ("slug_a", "silent") not in selected


def test_select_excludes_aborted_episodes_from_bypass():
    """Aborted-only keys must NOT trigger the first-encounter bypass."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, is_aborted=True),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug_a", "silent") not in selected


def test_select_ignores_other_run_episodes_in_bypass():
    """Episodes from other runs must not trigger first-encounter bypass."""
    episodes = [
        _ep(run_id="r0", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug_a", "silent") not in selected
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py -v
```
Expected: 4 fail (`test_select_with_empty_guide_store...`, `test_select_with_existing_guide...`, `test_select_excludes_aborted...`, `test_select_ignores_other_run...`) — `_select_combat_keys_for_refresh` currently does not accept a `guide_store` kwarg. The legacy-behavior test passes.

- [ ] **Step 3: Update `_select_combat_keys_for_refresh` signature and body**

In `src/memory/guide_consolidator.py`, replace the function (lines 40-88) with:

```python
def _select_combat_keys_for_refresh(
    episodes: list[CombatEpisode],
    current_run_id: str,
    guide_store: object | None = None,  # GuideStore — duck-typed to avoid circular import
) -> set[tuple[str, str]]:
    """Pick (enemy_key, character) keys to refresh this postrun.

    Policy:
    - All boss + elite fights from the current run always refresh.
    - Per act, the single small-monster fight with max HP loss refreshes
      (tie → first-encountered in iteration order).
    - First-encounter bypass: when ``guide_store`` is provided, any key with
      no existing guide and ≥1 non-aborted episode in the current run is
      additionally forced into the refresh set. This ensures self-evolve
      runs from blank stores capture every encountered enemy on the first
      run instead of waiting for a second occurrence.
    - Episodes from other runs or marked aborted are ignored.

    Returns a set of normalized (enemy_key, character) tuples. The caller
    runs the existing refresh pipeline per key.
    """
    run_episodes = [
        ep for ep in episodes
        if ep.run_id == current_run_id and not getattr(ep, "is_aborted", False)
    ]

    selected: set[tuple[str, str]] = set()

    # Boss + elite: always refresh
    for ep in run_episodes:
        if ep.combat_type in ("boss", "elite"):
            selected.add((
                normalize_enemy_key(ep.enemy_key),
                normalize_character(ep.character),
            ))

    # Small monster: per (act, character) pick the single worst HP loss fight
    worst_per_act_char: dict[tuple[int, str], CombatEpisode] = {}
    for ep in run_episodes:
        if ep.combat_type != "monster":
            continue
        hp_loss = ep.hp_before - ep.hp_after
        char = normalize_character(ep.character)
        key = (ep.act, char)
        prev = worst_per_act_char.get(key)
        if prev is None or hp_loss > (prev.hp_before - prev.hp_after):
            worst_per_act_char[key] = ep

    for ep in worst_per_act_char.values():
        selected.add((
            normalize_enemy_key(ep.enemy_key),
            normalize_character(ep.character),
        ))

    # First-encounter bypass: any (key) with no existing guide and ≥1
    # non-aborted episode in the current run is forced into the refresh set.
    if guide_store is not None:
        for ep in run_episodes:
            key = (
                normalize_enemy_key(ep.enemy_key),
                normalize_character(ep.character),
            )
            if guide_store.get_combat_guide(*key) is None:
                selected.add(key)

    return selected
```

- [ ] **Step 4: Update the call site to pass `guide_store`**

In `src/memory/guide_consolidator.py`, find the line (around 1106):

```python
selected_keys = _select_combat_keys_for_refresh(all_episodes, current_run_id)
```

Replace with:

```python
selected_keys = _select_combat_keys_for_refresh(
    all_episodes, current_run_id, guide_store=guide_store,
)
```

- [ ] **Step 5: Add the per-key min_episodes bypass**

In the same file, find the per-key consolidation loop (around lines 1108-1122). Replace this block:

```python
        for (enemy_key, character) in sorted(selected_keys):
            # LLM still sees full cross-run history for this key
            episodes = [
                ep for ep in all_episodes
                if normalize_enemy_key(ep.enemy_key) == enemy_key
                and normalize_character(ep.character) == character
                and not getattr(ep, "is_aborted", False)
            ]
            if len(episodes) < min_episodes:
                continue

            existing = guide_store.get_combat_guide(enemy_key, character)
            # Skip if guide is up-to-date (same episode count AND has mechanic_summary)
            if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary:
                continue
```

with:

```python
        for (enemy_key, character) in sorted(selected_keys):
            # LLM still sees full cross-run history for this key
            episodes = [
                ep for ep in all_episodes
                if normalize_enemy_key(ep.enemy_key) == enemy_key
                and normalize_character(ep.character) == character
                and not getattr(ep, "is_aborted", False)
            ]
            existing = guide_store.get_combat_guide(enemy_key, character)

            # First-encounter bypass: skip min_episodes gate when no existing guide.
            if existing is None and len(episodes) >= 1:
                pass
            elif len(episodes) < min_episodes:
                continue

            # Skip if guide is up-to-date (same episode count AND has mechanic_summary)
            if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary:
                continue
```

The `existing` fetch moves above the min_episodes gate so the bypass can read it.

- [ ] **Step 6: Run combat tests**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py tests/test_guide_consolidator.py 2>&1 | tail -10
```
Expected: all pass (existing `tests/test_guide_consolidator.py` tests must remain green).

- [ ] **Step 7: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_guide_consolidator_first_encounter.py
git commit -m "feat(memory): combat guide first-encounter bypass + selection override"
```

---

## Task 3: Track B — event guide first-encounter bypass

**Files:**
- Modify: `src/memory/event_guide_consolidator.py:402-412`
- Test: `tests/test_event_guide_consolidator_first_encounter.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_event_guide_consolidator_first_encounter.py`:

```python
"""Tests for first-encounter bypass in event guide consolidation."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from src.memory.event_models import EventMemory


def _event_memory(*, run_id, event_id, character, floor=5):
    """Minimal EventMemory — most fields default to safe values."""
    return EventMemory(
        memory_id=f"em-{event_id}-{run_id}",
        run_id=run_id,
        character=character,
        event_id=event_id,
        floor=floor,
        act=1,
    )


def _make_mm(event_store, guide_store):
    """Build a minimal memory_manager-shaped object for consolidate_event_guides."""
    mm = MagicMock()
    mm.event_store = event_store
    mm.guide_store = guide_store
    return mm


def test_event_first_encounter_bypass_triggers_llm_when_existing_is_none():
    """1 event memory + no existing guide → LLM call fires."""
    from src.memory.event_guide_consolidator import consolidate_event_guides

    event_store = MagicMock()
    event_store.get_all = MagicMock(return_value=[
        _event_memory(run_id="r1", event_id="EVT_A", character="Silent"),
    ])

    guide_store = MagicMock()
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_event_guide = MagicMock()

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch(
        "src.memory.event_guide_consolidator.parse_event_guide_response",
        return_value=None,  # parse returns None → no set, but LLM still called
    ):
        asyncio.run(consolidate_event_guides(
            _make_mm(event_store, guide_store),
            current_run_id="r1",
            min_episodes=2,
            llm_call_raw=fake_llm,
        ))

    fake_llm.assert_awaited_once()


def test_event_no_bypass_when_existing_guide_present():
    """1 event memory + existing guide → falls back to min_episodes=2 → skipped."""
    from src.memory.event_guide_consolidator import consolidate_event_guides

    event_store = MagicMock()
    event_store.get_all = MagicMock(return_value=[
        _event_memory(run_id="r1", event_id="EVT_A", character="Silent"),
    ])

    existing = MagicMock()
    guide_store = MagicMock()
    guide_store.get_event_guide = MagicMock(return_value=existing)
    guide_store.set_event_guide = MagicMock()

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    asyncio.run(consolidate_event_guides(
        _make_mm(event_store, guide_store),
        current_run_id="r1",
        min_episodes=2,
        llm_call_raw=fake_llm,
    ))

    fake_llm.assert_not_awaited()
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_guide_consolidator_first_encounter.py -v
```
Expected: `test_event_first_encounter_bypass_triggers_llm_when_existing_is_none` FAILS (LLM not awaited because min_episodes=2 currently skips). The other test passes.

- [ ] **Step 3: Update event consolidator**

In `src/memory/event_guide_consolidator.py`, locate the per-key loop (around line 402-412):

```python
    for (event_id, character) in sorted(selected_event_keys):
        memories = [
            m for m in all_event_memories
            if m.event_id.upper() == event_id
            and normalize_character(m.character) == character
        ]
        if len(memories) < min_episodes:
            continue

        existing = guide_store.get_event_guide(event_id, character)
```

Replace with:

```python
    for (event_id, character) in sorted(selected_event_keys):
        memories = [
            m for m in all_event_memories
            if m.event_id.upper() == event_id
            and normalize_character(m.character) == character
        ]
        existing = guide_store.get_event_guide(event_id, character)

        # First-encounter bypass: skip min_episodes gate when no existing guide.
        # EventMemory has no is_aborted field today; non-aborted check is a
        # defensive getattr in case the model gains the field later.
        non_aborted = [m for m in memories if not getattr(m, "is_aborted", False)]
        if existing is None and len(non_aborted) >= 1:
            pass
        elif len(memories) < min_episodes:
            continue
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_event_guide_consolidator_first_encounter.py -v
```
Expected: both pass.

- [ ] **Step 5: Run wider event tests for regression**

```bash
python -m pytest tests/ -k "event_guide or event_extractor" 2>&1 | tail -10
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/memory/event_guide_consolidator.py tests/test_event_guide_consolidator_first_encounter.py
git commit -m "feat(memory): event guide first-encounter bypass"
```

---

## Task 4: Track B — route guide first-encounter bypass

**Files:**
- Modify: `src/memory/guide_consolidator.py:1165-1171`
- Test: extend `tests/test_guide_consolidator_first_encounter.py`

Route consolidation already filters aborted memories upstream of the loop ([guide_consolidator.py:1160-1161](../../../src/memory/guide_consolidator.py)), so memories reaching the loop are all non-aborted. The bypass simplifies to `len(memories) >= 1`.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_guide_consolidator_first_encounter.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch

from src.memory.models_v2 import RouteMemory


def _route_memory(*, run_id, act, character, boss_result="won"):
    """Minimal RouteMemory. boss_result must NOT be 'aborted' or memory
    is filtered out upstream of the consolidation loop."""
    return RouteMemory(
        memory_id=f"rm-{act}-{run_id}",
        run_id=run_id,
        character=character,
        act=act,
        nodes=(),
        boss_result=boss_result,
    )


def test_route_first_encounter_bypass_triggers_llm():
    """1 route memory + no existing guide → LLM call fires for routes."""
    from src.memory.guide_consolidator import consolidate_guides

    memory_manager = MagicMock()
    memory_manager.v2_enabled = True

    combat_store = MagicMock()
    combat_store.get_all = MagicMock(return_value=[])
    memory_manager.combat_store = combat_store

    route_store = MagicMock()
    route_store.get_all = MagicMock(return_value=[
        _route_memory(run_id="r1", act=1, character="Silent"),
    ])
    memory_manager.route_store = route_store

    # Other stores empty so only route path runs
    memory_manager.card_build_store = MagicMock()
    memory_manager.card_build_store.get_all = MagicMock(return_value=[])
    memory_manager.event_store = MagicMock()
    memory_manager.event_store.get_all = MagicMock(return_value=[])

    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    guide_store.get_route_guide = MagicMock(return_value=None)
    guide_store.get_deck_guide = MagicMock(return_value=None)
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_route_guide = MagicMock()
    memory_manager.guide_store = guide_store

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch("src.brain.llm_caller.call_raw", fake_llm):
        with patch(
            "src.memory.guide_consolidator.parse_route_guide_response",
            return_value=None,
        ):
            asyncio.run(consolidate_guides(
                memory_manager, current_run_id="r1",
            ))

    # At least one llm call (route guide) — combat/event/deck stores are empty
    assert fake_llm.await_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py::test_route_first_encounter_bypass_triggers_llm -v
```
Expected: FAIL — current code skips when `len(memories) < 2`.

- [ ] **Step 3: Update route consolidator**

In `src/memory/guide_consolidator.py`, locate the route loop (around lines 1165-1171):

```python
        for (act, character), memories in groups_r.items():
            if len(memories) < min_episodes:
                continue

            existing = guide_store.get_route_guide(act, character)
            if existing and existing.memory_count >= len(memories):
                continue
```

Replace with:

```python
        for (act, character), memories in groups_r.items():
            existing = guide_store.get_route_guide(act, character)

            # First-encounter bypass: skip min_episodes gate when no existing
            # guide. Memories here are already non-aborted (filtered upstream
            # at groups_r construction).
            if existing is None and len(memories) >= 1:
                pass
            elif len(memories) < min_episodes:
                continue

            if existing and existing.memory_count >= len(memories):
                continue
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py -v
```
Expected: all pass (combat tests from Task 2 still green; new route test passes).

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_guide_consolidator_first_encounter.py
git commit -m "feat(memory): route guide first-encounter bypass"
```

---

## Task 5: Track B — deck guide first-encounter bypass

**Files:**
- Modify: `src/memory/guide_consolidator.py:1221-1228`
- Test: extend `tests/test_guide_consolidator_first_encounter.py`

Deck consolidation has an extra `_deck_guide_needs_refresh` short-circuit that must be kept; the bypass only changes the min_episodes gate placement.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_guide_consolidator_first_encounter.py`:

```python
from src.memory.models_v2 import CardBuildMemory


def _build_memory(*, run_id, character, archetype):
    """Minimal CardBuildMemory."""
    return CardBuildMemory(
        memory_id=f"bm-{archetype}-{run_id}",
        run_id=run_id,
        character=character,
        archetype=archetype,
    )


def test_deck_first_encounter_bypass_triggers_llm():
    """1 deck build + no existing guide → LLM call fires for deck guide."""
    from src.memory.guide_consolidator import consolidate_guides

    memory_manager = MagicMock()
    memory_manager.v2_enabled = True
    memory_manager.combat_store = MagicMock()
    memory_manager.combat_store.get_all = MagicMock(return_value=[])
    memory_manager.route_store = MagicMock()
    memory_manager.route_store.get_all = MagicMock(return_value=[])
    memory_manager.event_store = MagicMock()
    memory_manager.event_store.get_all = MagicMock(return_value=[])

    card_build_store = MagicMock()
    card_build_store.get_all = MagicMock(return_value=[
        _build_memory(run_id="r1", character="Silent", archetype="poison"),
    ])
    memory_manager.card_build_store = card_build_store

    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    guide_store.get_route_guide = MagicMock(return_value=None)
    guide_store.get_deck_guide = MagicMock(return_value=None)
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_deck_guide = MagicMock()
    memory_manager.guide_store = guide_store

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch("src.brain.llm_caller.call_raw", fake_llm):
        with patch(
            "src.memory.guide_consolidator.parse_deck_guide_response",
            return_value=None,
        ):
            with patch(
                "src.memory.guide_consolidator._select_deck_keys_for_refresh",
                return_value={("silent", "poison")},
            ):
                asyncio.run(consolidate_guides(
                    memory_manager, current_run_id="r1",
                ))

    assert fake_llm.await_count >= 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py::test_deck_first_encounter_bypass_triggers_llm -v
```
Expected: FAIL — `len(builds) < min_episodes` skips before LLM call.

- [ ] **Step 3: Update deck consolidator**

In `src/memory/guide_consolidator.py`, locate the deck loop (around lines 1221-1228):

```python
        for (character, archetype), builds in groups_d.items():
            if len(builds) < min_episodes:
                continue

            existing = guide_store.get_deck_guide(character, archetype)
            source_fingerprint = _deck_guide_source_fingerprint(builds)
            if not _deck_guide_needs_refresh(existing, builds):
                continue
```

Replace with:

```python
        for (character, archetype), builds in groups_d.items():
            existing = guide_store.get_deck_guide(character, archetype)

            # First-encounter bypass: skip min_episodes gate when no existing
            # guide. CardBuildMemory has no is_aborted field today.
            non_aborted = [
                b for b in builds if not getattr(b, "is_aborted", False)
            ]
            if existing is None and len(non_aborted) >= 1:
                pass
            elif len(builds) < min_episodes:
                continue

            source_fingerprint = _deck_guide_source_fingerprint(builds)
            if not _deck_guide_needs_refresh(existing, builds):
                continue
```

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/test_guide_consolidator_first_encounter.py -v
```
Expected: all pass.

- [ ] **Step 5: Run guide-related test sweep**

```bash
python -m pytest tests/ -k "guide_consolidator or guide_store" 2>&1 | tail -10
```
Expected: no new failures.

- [ ] **Step 6: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_guide_consolidator_first_encounter.py
git commit -m "feat(memory): deck guide first-encounter bypass"
```

---

## Verification (after all tasks)

Final test sweep across all touched files:

```bash
python -m pytest \
  tests/test_card_note_updater.py \
  tests/test_guide_consolidator_first_encounter.py \
  tests/test_event_guide_consolidator_first_encounter.py \
  tests/test_guide_consolidator.py \
  -v
```

Expected: all pass.

Verify spec coverage by re-reading the spec test plan section and confirming each scenario maps to a test:

| Spec test scenario | Implemented test |
|---|---|
| `_select_combat_keys_for_refresh` with `guide_store=None` returns historical baseline | `test_select_without_guide_store_preserves_legacy_behavior` |
| Empty guide store + 1 small non-worst monster → key included | `test_select_with_empty_guide_store_admits_all_non_aborted_keys` |
| Combat per-key loop, `existing=None` + 1 non-aborted episode → LLM called | (covered by integration of selection + bypass — combat selection test plus min_episodes bypass code path; verify by reading combat loop after Task 2 step 5) |
| Combat per-key loop, `existing=None` + 1 aborted episode → no LLM call | `test_select_excludes_aborted_episodes_from_bypass` (selection layer rejects) |
| Combat per-key loop, `existing=existing_guide` + 1 episode → falls back to old skip | `test_select_with_existing_guide_skips_first_encounter_bypass` |
| Event empty + 1 record → LLM | `test_event_first_encounter_bypass_triggers_llm_when_existing_is_none` |
| Event existing + 1 record → no LLM | `test_event_no_bypass_when_existing_guide_present` |
| Route empty + 1 record → LLM | `test_route_first_encounter_bypass_triggers_llm` |
| Deck empty + 1 record → LLM | `test_deck_first_encounter_bypass_triggers_llm` |
| Card prompt contains MANDATORY phrase | `test_prompt_contains_mandatory_first_note_rule` |

## Optional: live smoke after merge

After the test suite is green, run a single 1-run self-evolve to confirm postrun writes guides on the first run:

```bash
python -m scripts.run_ablation \
  --tag livesmoke-firstwrite-2026-04-28 \
  --runs-per-condition 1 \
  --models gemini \
  --character Silent \
  --ascension 0
```

Expected post-run state in `<STS2_DATA_REPO>/experiments/livesmoke-firstwrite-2026-04-28/gemini-self-evolve/memory/v2/guides.json`:

- combat guides for every encountered enemy (boss + elite + every small monster fought, not just worst-of-act)
- event guides for every encountered event
- route guides for every act reached
- deck guide for the final archetype

This is optional because it costs LLM credit and depends on the game running. Skip for code-only verification.
