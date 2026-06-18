# Event Memory Pipeline Fix — Design Spec

**Date:** 2026-04-15
**Status:** Draft
**Motivation:** Agent picks Sword of Stone 71% of the time (10/14 encounters) despite it being a trap relic. Root cause: the event memory pipeline fails to learn from past mistakes due to 5 compounding data/retrieval/analysis gaps.

## Problem Statement

The Sunken Statue event offers two options:
- **Grab the Sword** → Sword of Stone relic ("Transforms into a powerful Relic after defeating 5 Elites")
- **Dive into the Water** → ~111 Gold for 7 HP

Sword of Stone is a trap: a typical run encounters 3-4 elites, so the relic almost never transforms. It occupies a relic slot with zero benefit. The agent should learn this through its event memory pipeline, but 5 root causes prevent learning:

1. **Character field empty** — 91% (1079/1186) of event memories have `character=""`, making them invisible to the retriever
2. **Retrieval priority bug** — `EventMemoryStore.query()` applies character filter before event_id filter, discarding all `character=""` records
3. **Analysis skipped** — `analyze_event_boss_impact()` only runs when the run reaches a boss; 17/18 SUNKEN_STATUE memories have `boss_impact_score=0.0`
4. **Relic gain not captured** — All "Grab the Sword" entries have `relics_gained=[]` despite code logic being correct (timing issue in `_finalize_event_stage`)
5. **No relic utility signal** — Pipeline measures immediate diffs and boss impact, but cannot detect "relic did nothing for 30+ floors" (opportunity cost)

## Approach: Two-Phase Fix

### Phase 1 — Data Quality

Fix data capture and retrieval so the pipeline can accumulate correct event experience.

### Phase 2 — Run Impact Analysis

Upgrade event analysis from boss-only to run-wide, with relic descriptions and counterfactual options in the prompt so the LLM can infer relic utility from existing data.

---

## Phase 1: Data Quality Fixes

### 1a. Character Backfill Script

**File:** `scripts/backfill_event_memories.py` (new)

**Logic:**
1. Read `data/memory/v2/event_memories.jsonl`
2. For entries with `character=""`, look up `run_id` in `data/memory/v2/combat_episodes.jsonl` to find the character from the same run
3. If no combat episode match, fall back to grepping the character from `logs/run_{run_id}.jsonl`
4. Write updated file, backup original to `data/memory/v2/_backups/pre_character_backfill_{timestamp}/`
5. Report: N entries updated, M entries still unresolved

**One-time script.** Future runs already pass character correctly (fixed ~4/13).

### 1b. Retriever Priority Fix

**File:** `src/memory/event_store.py` — `EventMemoryStore.query()`

**Current (broken):**
```python
# Step 1: filter by character (hard filter)
if character:
    candidates = [m for m in candidates if normalize_character(m.character) == norm_char]
# Step 2: filter by event_id
if event_id:
    exact = [m for m in candidates if m.event_id.upper() == event_id.upper()]
```

Character filter in step 1 removes all `character=""` entries before event_id matching, causing SUNKEN_STATUE records to be invisible.

**Fixed:**
```python
# Step 1: event_id filter FIRST (primary key for event retrieval)
if event_id:
    exact = [m for m in candidates if m.event_id.upper() == event_id.upper()]
    if exact:
        candidates = exact

# Step 2: character as sort signal, not hard filter
if character:
    norm = normalize_character(character)
    candidates.sort(key=lambda m: (
        normalize_character(m.character) != norm,  # same-character first
        -m.timestamp,                              # then by recency
    ))
else:
    candidates.sort(key=lambda m: -m.timestamp)
```

**Effect:** SUNKEN_STATUE memories with `character=""` are now retrievable. Same-character entries rank higher but don't exclude cross-character experience.

### 1c. Relic Capture Debug

**File:** `src/agent/loop.py` — `_finalize_event_stage()`

**Hypothesis:** When `_finalize_event_stage()` is called, `gs` is still the event screen state (pre-transition), so `gs.relics` hasn't been updated with the newly acquired relic yet. The diff sees no change.

**Action:**
1. Add debug logging in `_finalize_event_stage()`:
   ```python
   prev_relics = [r.name for r in getattr(self._prev_event_gs, "relics", [])]
   curr_relics = [r.name for r in getattr(gs, "relics", [])]
   logger.info("Event relic diff: prev=%s curr=%s", prev_relics, curr_relics)
   ```
2. Run agent, trigger SUNKEN_STATUE → "Grab the Sword", observe logs
3. Two likely outcomes:
   - **If `gs.relics` is stale at finalize time:** Defer relic diff to the next non-event state. Store `_prev_event_gs` and compute relic diff when `state_type` transitions away from `"event"` (the first non-event `gs` will have the updated relic list).
   - **If `gs.relics` is correct but the relic name doesn't match:** Check whether the C# mod reports the relic under a different name or ID format and normalize accordingly.

---

## Phase 2: Run Impact Analysis

### 2a. Rename + Remove Boss Gate

**File:** `src/memory/event_analysis.py`

- Rename `analyze_event_boss_impact` → `analyze_event_run_impact`
- Rename `build_event_boss_impact_prompt` → `build_event_run_impact_prompt`
- Remove the early return:
  ```python
  # REMOVE:
  if not boss_encounters:
      return event_memories
  ```
- Update callers in `src/agent/loop.py` (`_analyze_event_boss_impact_async` → `_analyze_event_run_impact_async`)

### 2b. EventOptionSnapshot Model

**File:** `src/memory/models_v2.py` (new dataclass)

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
```

### 2c. Expand EventTracker + EventMemory

**File:** `src/memory/short_term.py` — `EventTracker`

Add field:
```python
all_option_details: list[dict] = field(default_factory=list)
```

**File:** `src/memory/models_v2.py` — `EventMemory`

Add field:
```python
all_option_details: tuple[EventOptionSnapshot, ...] = ()
```

Keep existing `all_options: tuple[str, ...]` for backward compatibility. New field is additive.

### 2d. Capture Full Option Details

**File:** `src/agent/loop.py` — `_finalize_event_stage()`

Change option capture from:
```python
all_opts = [o.title for o in self._prev_event_gs.event.options]
```

To also capture details:
```python
all_opts = [o.title for o in self._prev_event_gs.event.options]
all_details = []
for o in self._prev_event_gs.event.options:
    all_details.append({
        "index": o.index,
        "title": o.title,
        "description": o.description,
        "hp_cost": getattr(o, "hp_cost", None),
        "gold_cost": getattr(o, "gold_cost", None),
        "relics_offered": [r.get("name", "") for r in getattr(o, "relics_offered", [])],
        "cards_offered": [c.get("name", "") for c in getattr(o, "cards_offered", [])],
        "potions_offered": [p.get("name", "") for p in getattr(o, "potions_offered", [])],
    })
```

Pass `all_details` through `stm.end_event()` → `EventTracker` → `event_extractor` → `EventMemory`.

### 2e. Relic Context Helper

**File:** `src/memory/event_analysis.py` (new helper)

```python
def _build_relic_context(combat_episodes: list) -> list[dict]:
    """Extract end-of-run relic snapshot with descriptions from combat episodes."""
    for ep in reversed(combat_episodes):
        ctx = getattr(ep, "context", None)
        if ctx and ctx.relics:
            return [
                {"name": r.name, "description": r.description, "stack": r.stack}
                for r in ctx.relics
            ]
    return []
```

### 2f. Run Impact Prompt Redesign

**File:** `src/memory/event_analysis.py` — `build_event_run_impact_prompt()`

New prompt structure:

```
Analyze how each event decision affected this run's outcome.

## Run Summary
Result: DEFEAT at floor 14
Elite kills: 3, Boss kills: 0
Final HP: 0/70

## Relics at Run End
- Ring of the Snake: "Draw 2 additional cards at combat start"
- Sword of Stone: "Transforms into a powerful Relic after defeating 5 Elites" [stack=3]

## Event Decisions

### [memory_id] F8 The Sunken Statue (Act 1)
Options available:
  [0] "Grab the Sword": Obtain the Sword of Stone.
      Relics offered: Sword of Stone
  [1] "Dive into the Water": Gain 111 Gold. Lose 7 HP.
      HP cost: 7
Chose: [0] "Grab the Sword"
Outcome: HP 32→32, Gold 167→167, relics_gained=["Sword of Stone"]

## Instructions
For each event decision, evaluate:
1. Did event-gained relics actually contribute during the run? Check relic description
   against actual run outcome (e.g. conditional relics that never activated).
2. Was the resource trade-off (HP/gold) efficient given what happened after?
3. What would the unchosen alternative have provided? Was it objectively better?

Respond with JSON array:
[{"memory_id": "<id>", "score": <-1.0 to 1.0>, "analysis": "<1 sentence>", "quality": "good|neutral|bad"}]

Score: -1.0 = severely hurt the run, 0.0 = no impact, 1.0 = critical to success.
```

### 2g. Guide Consolidation Linkage

**File:** `src/memory/guide_consolidator.py` — `build_event_guide_prompt()`

Minor change: include `all_option_details` in the per-encounter summary so the consolidation LLM sees what alternatives existed:

```python
if em.all_option_details:
    for od in em.all_option_details:
        lines.append(f"    Option[{od.index}] \"{od.title}\": {od.description}")
```

No structural change needed — the improved run impact scores and relic data will naturally produce better guides.

---

## Verification Plan

### Phase 1 Verification
1. Run `scripts/backfill_event_memories.py` → confirm character fill rate ≥95%
2. Manual test: `event_store.query("SUNKEN_STATUE", "the silent", limit=5)` returns historical records
3. Run agent with debug logging → trigger an event with relic reward → confirm `relics_gained` is populated

### Phase 2 Verification
1. Replay historical event memories through new `build_event_run_impact_prompt()` → verify prompt contains relic descriptions and counterfactual options
2. Run analysis on SUNKEN_STATUE "Grab the Sword" entries → confirm negative scores
3. Trigger guide reconsolidation for SUNKEN_STATUE → verify guide text recommends gold over sword
4. Run full agent session → verify SUNKEN_STATUE prompt shows "Past Event Experience" with quality signals

---

## Files Changed

| File | Change Type | Description |
|------|-------------|-------------|
| `scripts/backfill_event_memories.py` | **New** | One-time character backfill script |
| `src/memory/event_store.py` | **Modify** | query() priority: event_id first, character as sort signal |
| `src/memory/models_v2.py` | **Add** | EventOptionSnapshot dataclass; EventMemory.all_option_details field |
| `src/memory/short_term.py` | **Add** | EventTracker.all_option_details field |
| `src/memory/event_extractor.py` | **Modify** | Pass all_option_details through to EventMemory |
| `src/memory/event_analysis.py` | **Rewrite** | boss impact → run impact; new prompt with relic context + counterfactuals |
| `src/agent/loop.py` | **Modify** | _finalize_event_stage: capture full option details + relic debug logging |
| `src/memory/guide_consolidator.py` | **Modify** | Include option details in event guide consolidation prompt |

## Out of Scope

- Structured trap detection fields on EventGuide (current freeform `guide_text` is sufficient given improved data)
- Relic utility tracking beyond binary "did conditional relic activate" (description-based LLM inference covers this)
- Event-aware skill discovery (separate future work per CLAUDE.md TODO)
