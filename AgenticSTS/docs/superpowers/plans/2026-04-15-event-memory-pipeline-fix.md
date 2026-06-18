# Event Memory Pipeline Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the event memory pipeline so the agent learns from event outcomes (e.g. Sword of Stone is a trap) by fixing data quality issues and upgrading event analysis from boss-only to run-wide.

**Architecture:** Two-phase approach. Phase 1 fixes data capture (character backfill, retriever priority, relic capture timing). Phase 2 upgrades analysis (run impact prompt with relic descriptions and counterfactual options). Each phase is independently verifiable.

**Tech Stack:** Python 3.12, frozen dataclasses, JSONL persistence, async LLM calls via `call_raw()`

**Spec:** `docs/superpowers/specs/2026-04-15-event-memory-pipeline-fix-design.md`

---

## Phase 1: Data Quality

### Task 1: Fix EventMemoryStore.query() Priority

The retriever applies character filter before event_id filter, hiding all `character=""` records. Fix: event_id first, character as sort signal.

**Files:**
- Modify: `src/memory/event_store.py:41-71`
- Test: `tests/test_event_store.py`

- [ ] **Step 1: Write failing tests for the new priority behavior**

Add to `tests/test_event_store.py`:

```python
def test_query_event_id_priority_over_character():
    """event_id match should return results even when character is empty."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    # Old record with empty character (pre-backfill data)
    store.add(_make_event(event_id="SUNKEN_STATUE", character="", floor=5))
    # Query with specific character — should still find the event_id match
    results = store.query(event_id="SUNKEN_STATUE", character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "SUNKEN_STATUE"


def test_query_same_character_ranked_first():
    """Same-character results should rank above empty-character results."""
    from src.memory.event_store import EventMemoryStore
    import time

    store = EventMemoryStore()
    # Older record with matching character
    old = _make_event(event_id="SUNKEN_STATUE", character="the silent", floor=3)
    # Newer record with empty character
    empty = _make_event(event_id="SUNKEN_STATUE", character="", floor=8)
    store.add(old)
    store.add(empty)
    results = store.query(event_id="SUNKEN_STATUE", character="the silent", limit=5)
    assert len(results) == 2
    # Same-character entry should be first regardless of timestamp
    assert results[0].character == "the silent"


def test_query_no_event_id_still_filters_character():
    """When no event_id given, character filter still applies as before."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event(event_id="A", character="the silent"))
    store.add(_make_event(event_id="B", character="the ironclad"))
    results = store.query(character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "A"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_store.py::test_query_event_id_priority_over_character tests/test_event_store.py::test_query_same_character_ranked_first -v`

Expected: FAIL — `test_query_event_id_priority_over_character` returns 0 results (character filter removes empty-character entry)

- [ ] **Step 3: Implement the fix**

In `src/memory/event_store.py`, replace the `query()` method body (lines 47-71):

```python
    def query(
        self,
        event_id: str = "",
        character: str = "",
        act: int = 0,
        limit: int = 3,
    ) -> list[EventMemory]:
        """Retrieve event memories by event_id, character, and/or act.

        Priority: exact event_id match > character-preferred sort > recency.
        When event_id is given, character acts as a ranking signal (not a
        hard filter) so that legacy records with character="" are still
        retrievable.
        """
        with self._lock:
            candidates = list(self._memories)

        # event_id is the primary key for event-specific retrieval
        if event_id:
            exact = [m for m in candidates if m.event_id.upper() == event_id.upper()]
            if exact:
                candidates = exact

        # When no event_id, character IS a hard filter (browsing by character)
        if not event_id and character:
            norm_char = normalize_character(character)
            candidates = [m for m in candidates if normalize_character(m.character) == norm_char]

        if act > 0 and not event_id:
            act_match = [m for m in candidates if m.act == act]
            if act_match:
                candidates = act_match

        # Sort: same-character first (when event_id given), then by recency
        if event_id and character:
            norm = normalize_character(character)
            candidates.sort(key=lambda m: (
                normalize_character(m.character) != norm,
                -m.timestamp,
            ))
        else:
            candidates.sort(key=lambda m: -m.timestamp)

        return candidates[:limit]
```

- [ ] **Step 4: Run all event store tests**

Run: `python -m pytest tests/test_event_store.py -v`

Expected: ALL PASS (including existing tests)

- [ ] **Step 5: Commit**

```bash
git add src/memory/event_store.py tests/test_event_store.py
git commit -m "fix: event store query prioritizes event_id over character filter"
```

---

### Task 2: Add EventOptionSnapshot Model + Expand EventMemory

**Files:**
- Modify: `src/memory/models_v2.py:827-910`
- Test: `tests/test_event_memory_model.py`

- [ ] **Step 1: Write failing test for EventOptionSnapshot and expanded EventMemory**

Add to `tests/test_event_memory_model.py`:

```python
def test_event_option_snapshot_roundtrip():
    """EventOptionSnapshot serializes and deserializes correctly."""
    from src.memory.models_v2 import EventOptionSnapshot

    snap = EventOptionSnapshot(
        index=0,
        title="Grab the Sword",
        description="Obtain the Sword of Stone.",
        relics_offered=("Sword of Stone",),
    )
    d = snap.to_dict()
    restored = EventOptionSnapshot.from_dict(d)
    assert restored.title == "Grab the Sword"
    assert restored.relics_offered == ("Sword of Stone",)
    assert restored.hp_cost is None


def test_event_memory_option_details_roundtrip():
    """EventMemory with all_option_details survives serialization."""
    from src.memory.models_v2 import EventMemory, EventOptionSnapshot

    opts = (
        EventOptionSnapshot(index=0, title="Grab the Sword",
                            description="Obtain the Sword of Stone.",
                            relics_offered=("Sword of Stone",)),
        EventOptionSnapshot(index=1, title="Dive into the Water",
                            description="Gain 111 Gold. Lose 7 HP.",
                            hp_cost=7),
    )
    mem = EventMemory(
        event_id="SUNKEN_STATUE",
        all_option_details=opts,
    )
    d = mem.to_dict()
    restored = EventMemory.from_dict(d)
    assert len(restored.all_option_details) == 2
    assert restored.all_option_details[0].relics_offered == ("Sword of Stone",)
    assert restored.all_option_details[1].hp_cost == 7


def test_event_memory_backwards_compat_no_option_details():
    """Old EventMemory dicts without all_option_details load with empty tuple."""
    from src.memory.models_v2 import EventMemory

    d = {"event_id": "SUNKEN_STATUE", "all_options": ["A", "B"]}
    mem = EventMemory.from_dict(d)
    assert mem.all_option_details == ()
    assert mem.all_options == ("A", "B")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_memory_model.py::test_event_option_snapshot_roundtrip tests/test_event_memory_model.py::test_event_memory_option_details_roundtrip tests/test_event_memory_model.py::test_event_memory_backwards_compat_no_option_details -v`

Expected: FAIL — `EventOptionSnapshot` doesn't exist yet

- [ ] **Step 3: Add EventOptionSnapshot dataclass**

In `src/memory/models_v2.py`, insert before the `class EventMemory` block (before line 830):

```python
@dataclass(frozen=True)
class EventOptionSnapshot:
    """Snapshot of a single event option with reward details."""

    index: int = 0
    title: str = ""
    description: str = ""
    hp_cost: int | None = None
    gold_cost: int | None = None
    relics_offered: tuple[str, ...] = ()
    cards_offered: tuple[str, ...] = ()
    potions_offered: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "title": self.title,
            "description": self.description,
        }
        if self.hp_cost is not None:
            d["hp_cost"] = self.hp_cost
        if self.gold_cost is not None:
            d["gold_cost"] = self.gold_cost
        if self.relics_offered:
            d["relics_offered"] = list(self.relics_offered)
        if self.cards_offered:
            d["cards_offered"] = list(self.cards_offered)
        if self.potions_offered:
            d["potions_offered"] = list(self.potions_offered)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventOptionSnapshot:
        return cls(
            index=d.get("index", 0),
            title=d.get("title", ""),
            description=d.get("description", ""),
            hp_cost=d.get("hp_cost"),
            gold_cost=d.get("gold_cost"),
            relics_offered=tuple(d.get("relics_offered", ())),
            cards_offered=tuple(d.get("cards_offered", ())),
            potions_offered=tuple(d.get("potions_offered", ())),
        )
```

- [ ] **Step 4: Add all_option_details field to EventMemory**

In `src/memory/models_v2.py`, in the `EventMemory` class:

Add field after `all_options`:
```python
    all_options: tuple[str, ...] = ()
    all_option_details: tuple[EventOptionSnapshot, ...] = ()
```

In `to_dict()`, add after the `all_options` line:
```python
            "all_option_details": [od.to_dict() for od in self.all_option_details],
```

In `from_dict()`, add after the `all_options` line:
```python
            all_option_details=tuple(
                EventOptionSnapshot.from_dict(od)
                for od in d.get("all_option_details", ())
            ),
```

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_event_memory_model.py -v`

Expected: ALL PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_event_memory_model.py
git commit -m "feat: add EventOptionSnapshot model and EventMemory.all_option_details"
```

---

### Task 3: Expand EventTracker + Extractor for Option Details

**Files:**
- Modify: `src/memory/short_term.py:230-249` (EventTracker), `src/memory/short_term.py:678-703` (end_event)
- Modify: `src/memory/event_extractor.py`
- Test: `tests/test_event_extractor.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_event_extractor.py`:

```python
def test_extract_preserves_option_details():
    """Option details flow from EventTracker through to EventMemory."""
    from src.memory.event_extractor import extract_event_memories
    from src.memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    stm.start_event(
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8, act=1, hp=50, gold=100, deck=["Strike"],
    )
    details = [
        {"index": 0, "title": "Grab the Sword",
         "description": "Obtain the Sword of Stone.",
         "relics_offered": ["Sword of Stone"]},
        {"index": 1, "title": "Dive into the Water",
         "description": "Gain 111 Gold. Lose 7 HP.",
         "hp_cost": 7},
    ]
    stm.end_event(
        chosen_index=0,
        option_text="Grab the Sword",
        hp_after=50,
        gold_after=100,
        all_options=["Grab the Sword", "Dive into the Water"],
        cards_gained=[],
        cards_lost=[],
        relics_gained=["Sword of Stone"],
        potions_gained=[],
        all_option_details=details,
    )
    mems = extract_event_memories(stm, "run_1", "the silent")
    assert len(mems) == 1
    assert len(mems[0].all_option_details) == 2
    assert mems[0].all_option_details[0].title == "Grab the Sword"
    assert mems[0].all_option_details[0].relics_offered == ("Sword of Stone",)
    assert mems[0].all_option_details[1].hp_cost == 7
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_event_extractor.py::test_extract_preserves_option_details -v`

Expected: FAIL — `end_event()` doesn't accept `all_option_details`

- [ ] **Step 3: Add field to EventTracker**

In `src/memory/short_term.py`, add to the `EventTracker` dataclass (after line 249):

```python
    all_option_details: list[dict] = field(default_factory=list)
```

- [ ] **Step 4: Update end_event() to accept option details**

In `src/memory/short_term.py`, update `end_event()` signature and body. Add parameter:

```python
    def end_event(
        self,
        chosen_index: int,
        option_text: str,
        hp_after: int,
        gold_after: int,
        all_options: list[str],
        cards_gained: list[str],
        cards_lost: list[str],
        relics_gained: list[str],
        potions_gained: list[str],
        all_option_details: list[dict] | None = None,
    ) -> None:
```

Add at the end of the method body, before `self._completed_events.append`:

```python
        self._current_event.all_option_details = list(all_option_details or [])
```

- [ ] **Step 5: Update event_extractor to pass option details through**

In `src/memory/event_extractor.py`, add import and update the EventMemory construction:

```python
from src.memory.models_v2 import EventMemory, EventOptionSnapshot, normalize_character
```

Inside `extract_event_memories()`, add after `potions_gained=`:

```python
            all_option_details=tuple(
                EventOptionSnapshot.from_dict(od)
                for od in tracker.all_option_details
            ),
```

- [ ] **Step 6: Run all event extractor tests**

Run: `python -m pytest tests/test_event_extractor.py -v`

Expected: ALL PASS

- [ ] **Step 7: Commit**

```bash
git add src/memory/short_term.py src/memory/event_extractor.py tests/test_event_extractor.py
git commit -m "feat: pass event option details through EventTracker to EventMemory"
```

---

### Task 4: Capture Full Option Details + Relic Debug Logging in Agent Loop

**Files:**
- Modify: `src/agent/loop.py:2683-2718` (_finalize_event_stage)

- [ ] **Step 1: Add debug logging for relic diff**

In `src/agent/loop.py`, at the start of `_finalize_event_stage()` (after the `diff = ...` line), add:

```python
        # Debug: log relic diff to diagnose capture timing
        prev_relics = [r.name for r in getattr(self._prev_event_gs, "relics", [])]
        curr_relics = [r.name for r in getattr(gs, "relics", [])]
        if prev_relics != curr_relics:
            logger.info("Event relic diff detected: prev=%s curr=%s gained=%s",
                        prev_relics, curr_relics, diff["relics_gained"])
        elif diff.get("cards_gained") or diff.get("relics_gained"):
            logger.info("Event diff: cards=%s relics=%s potions=%s",
                        diff["cards_gained"], diff["relics_gained"], diff["potions_gained"])
        else:
            logger.debug("Event finalized with no detected diffs (prev_relics=%s curr_relics=%s)",
                         prev_relics, curr_relics)
```

- [ ] **Step 2: Capture full option details**

In `_finalize_event_stage()`, after the `all_opts` construction (line 2702-2706), add option detail capture:

```python
        all_details: list[dict] = []
        if self._prev_event_gs.event:
            for o in self._prev_event_gs.event.options:
                detail: dict = {
                    "index": o.index,
                    "title": o.title,
                    "description": getattr(o, "description", ""),
                }
                hp_cost = getattr(o, "hp_cost", None)
                if hp_cost is not None:
                    detail["hp_cost"] = hp_cost
                gold_cost = getattr(o, "gold_cost", None)
                if gold_cost is not None:
                    detail["gold_cost"] = gold_cost
                relics_off = getattr(o, "relics_offered", [])
                if relics_off:
                    detail["relics_offered"] = [
                        r.get("name", "") if isinstance(r, dict) else str(r)
                        for r in relics_off
                    ]
                cards_off = getattr(o, "cards_offered", [])
                if cards_off:
                    detail["cards_offered"] = [
                        c.get("name", "") if isinstance(c, dict) else str(c)
                        for c in cards_off
                    ]
                potions_off = getattr(o, "potions_offered", [])
                if potions_off:
                    detail["potions_offered"] = [
                        p.get("name", "") if isinstance(p, dict) else str(p)
                        for p in potions_off
                    ]
                all_details.append(detail)
```

- [ ] **Step 3: Pass details to stm.end_event()**

Update the `stm.end_event()` call to include the new parameter:

```python
        stm.end_event(
            chosen_index=chosen_index,
            option_text=chosen_text,
            hp_after=gs.player_hp,
            gold_after=gs.gold,
            all_options=all_opts,
            cards_gained=diff["cards_gained"],
            cards_lost=diff["cards_lost"],
            relics_gained=diff["relics_gained"],
            potions_gained=diff["potions_gained"],
            all_option_details=all_details,
        )
```

- [ ] **Step 4: Run existing event loop integration tests**

Run: `python -m pytest tests/test_event_loop_integration.py -v`

Expected: ALL PASS (new parameter has default=None, backward compatible)

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat: capture full event option details + relic diff debug logging"
```

---

### Task 5: Character Backfill Script

**Files:**
- Create: `scripts/backfill_event_memories.py`

- [ ] **Step 1: Create the backfill script**

```python
"""One-time backfill: populate empty character fields in event_memories.jsonl.

Reads character from combat_episodes.jsonl (same run_id), falling back
to log file grep when no combat episode exists for the run.
"""

from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime
from pathlib import Path

EVENT_PATH = Path("data/memory/v2/event_memories.jsonl")
COMBAT_PATH = Path("data/memory/v2/combat_episodes.jsonl")
LOG_DIR = Path("logs")
BACKUP_DIR = Path("data/memory/v2/_backups")


def _build_run_character_map() -> dict[str, str]:
    """Build run_id → character map from combat episodes."""
    mapping: dict[str, str] = {}
    if not COMBAT_PATH.exists():
        return mapping
    with open(COMBAT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                d = json.loads(line)
            except json.JSONDecodeError:
                continue
            run_id = d.get("run_id", "")
            character = d.get("character", "")
            if run_id and character and run_id not in mapping:
                mapping[run_id] = character
    return mapping


def _grep_character_from_log(run_id: str) -> str:
    """Try to find character from the run's log file."""
    # Log files: logs/run_{run_id}.jsonl
    candidates = list(LOG_DIR.glob(f"run_{run_id}*.jsonl"))
    if not candidates:
        # run_id may be truncated in older data — try prefix match
        short = run_id[:8] if len(run_id) > 8 else run_id
        candidates = list(LOG_DIR.glob(f"run_*{short}*.jsonl"))
    if not candidates:
        return ""
    log_path = candidates[0]
    try:
        with open(log_path, encoding="utf-8") as f:
            for line in f:
                if '"character"' not in line:
                    continue
                try:
                    d = json.loads(line.strip())
                except json.JSONDecodeError:
                    continue
                # Look for character in player data or state
                for key in ("character", "player_character"):
                    val = d.get(key, "")
                    if val:
                        return val.lower().strip()
                # Check nested player
                player = d.get("player", {})
                if isinstance(player, dict):
                    val = player.get("character", "")
                    if val:
                        return val.lower().strip()
    except Exception:
        pass
    return ""


def main() -> None:
    if not EVENT_PATH.exists():
        print(f"No event memories file at {EVENT_PATH}")
        sys.exit(1)

    # Backup
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = BACKUP_DIR / f"pre_character_backfill_{ts}"
    backup_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(EVENT_PATH, backup_dir / EVENT_PATH.name)
    print(f"Backup saved to {backup_dir}")

    # Build run → character map
    run_char_map = _build_run_character_map()
    print(f"Loaded {len(run_char_map)} run→character mappings from combat episodes")

    # Process
    entries: list[dict] = []
    with open(EVENT_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))

    updated = 0
    unresolved = 0
    for entry in entries:
        if entry.get("character", ""):
            continue  # already has character
        run_id = entry.get("run_id", "")
        character = run_char_map.get(run_id, "")
        if not character:
            character = _grep_character_from_log(run_id)
        if character:
            entry["character"] = character
            updated += 1
        else:
            unresolved += 1

    # Write back
    with open(EVENT_PATH, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry) + "\n")

    total = len(entries)
    already = total - updated - unresolved
    print(f"\nResults: {total} total entries")
    print(f"  Already had character: {already}")
    print(f"  Updated: {updated}")
    print(f"  Unresolved: {unresolved}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the backfill**

Run: `python scripts/backfill_event_memories.py`

Expected: Updated count should be ~1000+ (91% of 1186), unresolved should be low (<50).

- [ ] **Step 3: Verify**

Run: `python -c "import json; data=[json.loads(l) for l in open('data/memory/v2/event_memories.jsonl')]; empty=sum(1 for d in data if not d.get('character')); print(f'Empty character: {empty}/{len(data)}')"`

Expected: `Empty character: <50/1186` (down from 1079)

- [ ] **Step 4: Commit**

```bash
git add scripts/backfill_event_memories.py data/memory/v2/event_memories.jsonl
git commit -m "fix: backfill character field in event memories (91% were empty)"
```

---

## Phase 2: Run Impact Analysis

### Task 6: Rewrite event_analysis.py — Run Impact Prompt

**Files:**
- Rewrite: `src/memory/event_analysis.py`
- Test: `tests/test_event_boss_impact.py` (rename + expand)

- [ ] **Step 1: Write test for new prompt builder**

Replace `tests/test_event_boss_impact.py` with `tests/test_event_run_impact.py`:

```python
"""Tests for event run impact analysis."""

from src.memory.models_v2 import (
    EventMemory,
    EventOptionSnapshot,
    RelicSnapshot,
    CombatContext,
    CombatEpisode,
)


def _make_relic_context_episode(relics: list[tuple[str, str, int | None]]) -> CombatEpisode:
    """Create a CombatEpisode with relic context for testing."""
    relic_snaps = tuple(
        RelicSnapshot(name=name, description=desc, stack=stack)
        for name, desc, stack in relics
    )
    ctx = CombatContext(relics=relic_snaps, combat_type="elite")
    return CombatEpisode(context=ctx, combat_type="elite")


def test_build_prompt_includes_relic_descriptions():
    """Prompt should include relic names and descriptions from combat context."""
    from src.memory.event_analysis import build_event_run_impact_prompt

    em = EventMemory(
        memory_id="abc",
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8,
        act=1,
        chosen_option_index=0,
        chosen_option_text="Grab the Sword",
        relics_gained=("Sword of Stone",),
        hp_before=32,
        hp_after=32,
        gold_before=167,
        gold_after=167,
    )
    ep = _make_relic_context_episode([
        ("Ring of the Snake", "Draw 2 additional cards", None),
        ("Sword of Stone", "Transforms into a powerful Relic after defeating 5 Elites", 3),
    ])
    run_result = {"victory": False, "final_floor": 14}
    prompt = build_event_run_impact_prompt([em], [ep], run_result)
    assert "Sword of Stone" in prompt
    assert "Transforms into a powerful Relic" in prompt
    assert "stack=3" in prompt or "[3]" in prompt


def test_build_prompt_includes_counterfactual_options():
    """Prompt should show all options with descriptions, not just the chosen one."""
    from src.memory.event_analysis import build_event_run_impact_prompt

    opts = (
        EventOptionSnapshot(index=0, title="Grab the Sword",
                            description="Obtain the Sword of Stone.",
                            relics_offered=("Sword of Stone",)),
        EventOptionSnapshot(index=1, title="Dive into the Water",
                            description="Gain 111 Gold. Lose 7 HP.",
                            hp_cost=7),
    )
    em = EventMemory(
        memory_id="abc",
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8, act=1,
        chosen_option_index=0,
        chosen_option_text="Grab the Sword",
        all_option_details=opts,
    )
    prompt = build_event_run_impact_prompt([em], [], {"victory": False, "final_floor": 10})
    assert "Dive into the Water" in prompt
    assert "Gain 111 Gold" in prompt
    assert "Grab the Sword" in prompt


def test_build_prompt_runs_without_boss():
    """Prompt should be built even when there are no boss encounters."""
    from src.memory.event_analysis import build_event_run_impact_prompt

    em = EventMemory(memory_id="abc", event_id="TEST")
    prompt = build_event_run_impact_prompt([em], [], {"victory": False, "final_floor": 5})
    assert "abc" in prompt
    assert "DEFEAT" in prompt


def test_analyze_runs_without_boss_encounters():
    """analyze_event_run_impact should NOT skip when no boss encountered."""
    from src.memory.event_analysis import analyze_event_run_impact
    import asyncio

    em = EventMemory(memory_id="abc", event_id="TEST")
    # Will fail at LLM call but should NOT early-return
    # We just verify it doesn't return unchanged memories due to boss gate
    # (The LLM call will fail, but that's fine — we test the gate is removed)
    result = asyncio.get_event_loop().run_until_complete(
        analyze_event_run_impact([em], [], {"victory": False, "final_floor": 5})
    )
    # Should return the original memories (LLM call fails gracefully)
    assert len(result) == 1


def test_parse_response_unchanged():
    """Parser should still work with the same JSON format."""
    from src.memory.event_analysis import parse_event_run_impact_response

    raw = '[{"memory_id": "abc", "score": -0.5, "analysis": "Dead relic", "quality": "bad"}]'
    parsed = parse_event_run_impact_response(raw)
    assert len(parsed) == 1
    assert parsed[0]["score"] == -0.5
    assert parsed[0]["quality"] == "bad"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_event_run_impact.py -v`

Expected: FAIL — functions don't exist yet

- [ ] **Step 3: Rewrite event_analysis.py**

Replace `src/memory/event_analysis.py` entirely:

```python
"""Post-run event run impact analysis.

Calls analysis-tier LLM to score how each event decision affected
the run outcome. Results populate boss_impact_score,
boss_impact_analysis, and outcome_quality on EventMemory instances.

Upgraded from boss-only to run-wide analysis: runs even when no boss
was encountered, includes relic descriptions and counterfactual options.
"""

from __future__ import annotations

import json
import logging
from dataclasses import replace

from src.memory.models_v2 import EventMemory

logger = logging.getLogger(__name__)


def _build_relic_context(combat_episodes: list) -> list[dict]:
    """Extract end-of-run relic snapshot with descriptions from combat episodes."""
    for ep in reversed(combat_episodes):
        ctx = getattr(ep, "context", None)
        if ctx and getattr(ctx, "relics", None):
            return [
                {
                    "name": r.name,
                    "description": getattr(r, "description", ""),
                    "stack": getattr(r, "stack", None),
                }
                for r in ctx.relics
            ]
    return []


def _count_combat_types(combat_episodes: list) -> dict[str, int]:
    """Count elite/boss/monster encounters."""
    counts: dict[str, int] = {"elite": 0, "boss": 0, "monster": 0}
    for ep in combat_episodes:
        ct = getattr(ep, "combat_type", "monster")
        counts[ct] = counts.get(ct, 0) + 1
    return counts


def build_event_run_impact_prompt(
    event_memories: list[EventMemory],
    combat_episodes: list,
    run_result: dict[str, object],
) -> str:
    """Build an LLM prompt to analyze event impact on the entire run."""
    lines: list[str] = []

    # Run summary
    victory = run_result.get("victory", False)
    final_floor = run_result.get("final_floor", 0)
    lines.append("Analyze how each event decision affected this run's outcome.\n")
    lines.append("## Run Summary")
    lines.append(f"Result: {'VICTORY' if victory else 'DEFEAT'} at floor {final_floor}")
    combat_counts = _count_combat_types(combat_episodes)
    lines.append(
        f"Combats: {combat_counts.get('elite', 0)} elites, "
        f"{combat_counts.get('boss', 0)} bosses, "
        f"{combat_counts.get('monster', 0)} monsters"
    )
    boss_encounters = run_result.get("boss_encounters", [])
    if boss_encounters:
        for enc in boss_encounters:
            lines.append(f"  Boss: {enc}")
    lines.append("")

    # Relic context
    relics = _build_relic_context(combat_episodes)
    if relics:
        lines.append("## Relics at Run End")
        for r in relics:
            stack_info = f" [stack={r['stack']}]" if r.get("stack") is not None else ""
            desc = f': "{r["description"]}"' if r.get("description") else ""
            lines.append(f"- {r['name']}{desc}{stack_info}")
        lines.append("")

    # Event decisions with counterfactuals
    lines.append("## Event Decisions\n")
    for em in event_memories:
        lines.append(f"### [{em.memory_id}] F{em.floor} {em.event_title} (Act {em.act})")

        # Show all options with details
        if em.all_option_details:
            lines.append("Options available:")
            for od in em.all_option_details:
                marker = " **(chosen)**" if od.index == em.chosen_option_index else ""
                lines.append(f'  [{od.index}] "{od.title}": {od.description}{marker}')
                if od.hp_cost is not None:
                    lines.append(f"      HP cost: {od.hp_cost}")
                if od.gold_cost is not None:
                    lines.append(f"      Gold cost: {od.gold_cost}")
                if od.relics_offered:
                    lines.append(f"      Relics: {', '.join(od.relics_offered)}")
                if od.cards_offered:
                    lines.append(f"      Cards: {', '.join(od.cards_offered)}")
                if od.potions_offered:
                    lines.append(f"      Potions: {', '.join(od.potions_offered)}")
        else:
            lines.append(
                f'Chose: "{em.chosen_option_text}" (index {em.chosen_option_index})'
            )

        lines.append(
            f"Outcome: HP {em.hp_before}->{em.hp_after}, "
            f"Gold {em.gold_before}->{em.gold_after}"
        )
        if em.cards_gained:
            lines.append(f"  Cards gained: {list(em.cards_gained)}")
        if em.cards_lost:
            lines.append(f"  Cards lost: {list(em.cards_lost)}")
        if em.relics_gained:
            lines.append(f"  Relics gained: {list(em.relics_gained)}")
        if em.potions_gained:
            lines.append(f"  Potions gained: {list(em.potions_gained)}")
        lines.append("")

    # Instructions
    lines.append("## Instructions")
    lines.append("For each event decision, evaluate:")
    lines.append(
        "1. Did event-gained relics actually contribute during the run? "
        "Check relic description against actual run outcome "
        "(e.g. conditional relics that never activated)."
    )
    lines.append(
        "2. Was the resource trade-off (HP/gold) efficient given what happened after?"
    )
    lines.append(
        "3. What would the unchosen alternative have provided? Was it objectively better?"
    )
    lines.append("")
    lines.append("Respond with JSON array:")
    lines.append(
        '[{"memory_id": "<id>", "score": <-1.0 to 1.0>, '
        '"analysis": "<1 sentence>", "quality": "good|neutral|bad"}]'
    )
    lines.append("")
    lines.append(
        "Score: -1.0 = severely hurt the run, 0.0 = no impact, "
        "1.0 = critical to success."
    )

    return "\n".join(lines)


def parse_event_run_impact_response(raw_text: str) -> list[dict[str, object]]:
    """Parse LLM response into list of run impact assessments."""
    text = raw_text.strip()
    start = text.find("[")
    end = text.rfind("]")
    if start == -1 or end == -1:
        logger.warning("No JSON array found in run impact response")
        return []

    try:
        parsed = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        logger.warning("Failed to parse run impact JSON")
        return []

    if not isinstance(parsed, list):
        return []

    results = []
    for item in parsed:
        if not isinstance(item, dict):
            continue
        memory_id = item.get("memory_id", "")
        score = float(item.get("score", 0.0))
        score = max(-1.0, min(1.0, score))
        analysis = str(item.get("analysis", ""))
        quality = str(item.get("quality", "neutral")).lower()
        if quality not in ("good", "neutral", "bad"):
            quality = "neutral"
        results.append({
            "memory_id": memory_id,
            "score": score,
            "analysis": analysis,
            "quality": quality,
        })
    return results


async def analyze_event_run_impact(
    event_memories: list[EventMemory],
    combat_episodes: list,
    run_result: dict[str, object],
) -> list[EventMemory]:
    """Call analysis-tier LLM and return updated EventMemory instances.

    Runs for every run with event memories (no boss-only gate).
    """
    if not event_memories:
        return event_memories

    prompt = build_event_run_impact_prompt(event_memories, combat_episodes, run_result)

    try:
        from src.brain.llm_caller import call_raw

        system = (
            "You are analyzing a Slay the Spire 2 run. "
            "Score how each event decision affected the run's outcome. "
            "Respond with only a JSON array."
        )
        raw, _latency, _tokens = await call_raw(
            system, prompt, think=True, call_type="event_analysis",
        )
        parsed = parse_event_run_impact_response(raw)
    except Exception:
        logger.warning("Event run impact LLM call failed", exc_info=True)
        return event_memories

    impact_map = {item["memory_id"]: item for item in parsed}
    updated = []
    for mem in event_memories:
        if mem.memory_id in impact_map:
            item = impact_map[mem.memory_id]
            mem = replace(
                mem,
                boss_impact_score=item["score"],
                boss_impact_analysis=item["analysis"],
                outcome_quality=item["quality"],
            )
        updated.append(mem)

    logger.info(
        "Event run impact analysis: %d/%d scored",
        len(impact_map), len(event_memories),
    )
    return updated
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_event_run_impact.py -v`

Expected: ALL PASS (the `test_analyze_runs_without_boss_encounters` may warn about LLM call failing, but should not error)

- [ ] **Step 5: Commit**

```bash
git add src/memory/event_analysis.py tests/test_event_run_impact.py
git commit -m "feat: rewrite event analysis as run impact (no boss gate, relic context, counterfactuals)"
```

---

### Task 7: Update Agent Loop Callers

**Files:**
- Modify: `src/agent/loop.py` — rename references from boss_impact to run_impact

- [ ] **Step 1: Update _pending_event_analysis staging**

In `src/agent/loop.py`, find the event memory extraction block (~line 3700-3715). Change the `boss_eps` filter to pass ALL combat episodes:

Find:
```python
                boss_eps = [ep for ep in combat_eps if getattr(ep, "combat_type", "") == "boss"]
```

Replace with:
```python
                all_eps = list(combat_eps)  # run impact uses all episodes, not just boss
```

Update the tuple stored:
```python
                self._pending_event_analysis = (event_mems, all_eps, run_result)
```

- [ ] **Step 2: Rename async method**

Find `_analyze_event_boss_impact_async` and rename to `_analyze_event_run_impact_async`. Update the import inside the method:

```python
    async def _analyze_event_run_impact_async(self) -> None:
        """Run LLM run-impact analysis on event memories from this run."""
        if not self._pending_event_analysis or not self._memory:
            return
        event_mems, combat_eps, run_result = self._pending_event_analysis
        self._pending_event_analysis = None

        if not event_mems:
            return

        try:
            from src.memory.event_analysis import analyze_event_run_impact

            updated = await analyze_event_run_impact(event_mems, combat_eps, run_result)
```

- [ ] **Step 3: Update the caller**

Find the line that calls the old method name (~line 3317):
```python
                await self._analyze_event_boss_impact_async()
```

Replace with:
```python
                await self._analyze_event_run_impact_async()
```

- [ ] **Step 4: Run existing tests**

Run: `python -m pytest tests/test_agent_loop_fixes.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "refactor: rename event boss impact to run impact in agent loop"
```

---

### Task 8: Update Guide Consolidation with Option Details

**Files:**
- Modify: `src/memory/guide_consolidator.py:519-551`
- Test: `tests/test_event_guide_consolidator.py`

- [ ] **Step 1: Write failing test**

Add to `tests/test_event_guide_consolidator.py`:

```python
def test_event_guide_prompt_includes_option_details():
    """Guide consolidation prompt should show all options when details available."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import EventMemory, EventOptionSnapshot

    opts = (
        EventOptionSnapshot(index=0, title="Grab the Sword",
                            description="Obtain the Sword of Stone.",
                            relics_offered=("Sword of Stone",)),
        EventOptionSnapshot(index=1, title="Dive into the Water",
                            description="Gain 111 Gold. Lose 7 HP.",
                            hp_cost=7),
    )
    em = EventMemory(
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8, act=1,
        chosen_option_text="Grab the Sword",
        all_option_details=opts,
        boss_impact_score=-0.5,
        outcome_quality="bad",
    )
    prompt = build_event_guide_prompt("SUNKEN_STATUE", "the silent", [em])
    assert "Dive into the Water" in prompt
    assert "Obtain the Sword of Stone" in prompt
    assert "Gain 111 Gold" in prompt
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_event_guide_consolidator.py::test_event_guide_prompt_includes_option_details -v`

Expected: FAIL — option details not included in prompt

- [ ] **Step 3: Update build_event_guide_prompt**

In `src/memory/guide_consolidator.py`, in `build_event_guide_prompt()`, after the per-encounter line (after `{impact}{analysis}{quality}"`), add option detail lines:

```python
        if em.all_option_details:
            for od in em.all_option_details:
                detail_parts = [f'    Option[{od.index}] "{od.title}": {od.description}']
                if od.relics_offered:
                    detail_parts.append(f" relics={list(od.relics_offered)}")
                if od.hp_cost is not None:
                    detail_parts.append(f" hp_cost={od.hp_cost}")
                if od.gold_cost is not None:
                    detail_parts.append(f" gold_cost={od.gold_cost}")
                lines.append("".join(detail_parts))
```

- [ ] **Step 4: Run all guide consolidator tests**

Run: `python -m pytest tests/test_event_guide_consolidator.py -v`

Expected: ALL PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_event_guide_consolidator.py
git commit -m "feat: include event option details in guide consolidation prompt"
```

---

### Task 9: Delete Old Test File + Final Verification

**Files:**
- Delete: `tests/test_event_boss_impact.py` (replaced by `test_event_run_impact.py`)

- [ ] **Step 1: Remove old test file**

```bash
git rm tests/test_event_boss_impact.py
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_event_*.py -v`

Expected: ALL PASS across all event-related test files

- [ ] **Step 3: Verify retriever integration**

Run: `python -c "
from src.memory.event_store import EventMemoryStore
store = EventMemoryStore.load(__import__('pathlib').Path('data/memory/v2/event_memories.jsonl'))
results = store.query(event_id='SUNKEN_STATUE', character='the silent', limit=5)
print(f'Found {len(results)} SUNKEN_STATUE memories')
for r in results:
    print(f'  char={r.character!r} opt={r.chosen_option_text} score={r.boss_impact_score}')
"`

Expected: Returns 5 results including records that previously had `character=""` (now backfilled).

- [ ] **Step 4: Commit**

```bash
git rm tests/test_event_boss_impact.py 2>/dev/null; git add -A tests/
git commit -m "chore: remove old boss impact test (replaced by run impact tests)"
```
