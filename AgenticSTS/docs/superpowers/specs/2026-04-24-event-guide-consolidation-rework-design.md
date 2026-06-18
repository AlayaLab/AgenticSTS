# Event Guide Consolidation Rework

**Date**: 2026-04-24
**Status**: Approved, pending implementation plan
**Scope**: Rework event guide consolidation into a scored option library with
knowledge snapshots, stage awareness, and run-scoped refresh.

## Motivation

The current event guide pipeline under-delivers on three fronts:

1. **BBCode not stripped.** The consolidator prompt passes `[blue]15[/blue]`
   / `[gold]Ironclad[/gold]` verbatim into the LLM, wasting tokens and
   obscuring the actual content.
2. **Knowledge starved.** Each `EventOptionSnapshot` persists
   `relics_offered` / `cards_offered` / `potions_offered` as **name-only
   strings** — the C# mod already supplies the full rule text
   (`effect_description`, `rules_text`, `rarity`, `cost`, `type`, etc.)
   but `src/agent/loop.py::_finalize_event_stage` actively reduces each
   dict to `.get("name")`. The LLM never sees the rules text and has to
   reason from memory alone.
3. **No usable scoring.** The previous `boss_impact_score` field was
   removed (2026-04-15) because it was a separate LLM call producing
   fragile one-shot judgements. The consolidator now has only
   `run_victory` / `run_final_floor` as an outcome anchor, and it
   emits freeform bullet text that downstream retrieval cannot filter
   or rank.
4. **Random-variant conflation.** Options that are structurally the same
   but randomize concrete rewards (e.g. Orobas's "Archaic Tooth"
   transform-a-card slot; events with "random Uncommon card" rewards)
   are treated as separate rows each run. The LLM cannot tell whether
   two encounters differ because the *choice* was different or because
   the *random roll* was different.
5. **Stage collapsing.** Multi-step events (bridge, judgment) produce
   one `EventMemory` per stage. The current prompt flattens them, so
   the LLM sees Orobas's real choice and its "Proceed" closing page as
   peer options. Bridge-style events where stage-2 has real branches
   lose the sequencing.
6. **Noise records.** Many events have a stage-2 that is a single
   "Proceed" button. Those records have zero decision signal and just
   pad the store.
7. **Full-scan refresh.** Every postrun refreshes every
   `(event_id, character)` pair in the store — including pairs the
   current run never touched. Combat consolidation already switched to
   run-scoped (2026-04-23); event should follow.

## Goal

Replace the event branch of `consolidate_guides()` with a
run-scoped, scored option-library pipeline, backed by knowledge-rich
`EventOptionSnapshot` records captured at gameplay time.

## Non-goals

- Touching the combat / route / deck consolidation branches.
- Changing the C# mod (it already exposes the full hover-tip payload
  via `effect_description` / `cards_offered` / `relics_offered` /
  `potions_offered`).
- Keyword glossary injection inside event prompts. The global
  keyword glossary (which falls back to DLL-reverse-engineered
  definitions) already handles this at the agent-time prompt layer.
- Re-introducing a separate `boss_impact_score` LLM pass. Scoring
  happens inside the consolidator itself (no extra LLM call).

## Scope

### Decision summary (from brainstorming)

| Q | Decision | Rationale |
|---|---|---|
| Scoring source | Guide consolidator scores in the same LLM call, using `run_victory`/`run_final_floor` anchor + state-diff as evidence | No extra LLM pass; stable across multiple memories |
| Library shape | Structured `options: tuple[EventGuideOption, ...]` on `EventGuide`, plus a short `guide_text` takeaway | Retriever can filter/sort; stable across guide versions |
| Stage handling | Group memories by `(run_id, event_id, floor)` → playthrough; each option tagged with `stage_index` | Stage ordering inferred from timestamp; no new storage field |
| Knowledge enrichment | Mod payload preserved at extract time; **no lookup calls** | Knowledge DB can drift vs game patch; snapshot at observation time |
| Refresh trigger | Run-scoped: only `(event_id, character)` pairs touched by the current run | Mirrors 2026-04-23 combat refactor |
| Keyword injection | Dropped from event pipeline | Global glossary + DLL fallback already handles |
| Proceed-only stage | Dropped at extractor | Zero signal; only triggered when *every* option in the stage is `is_proceed=True` |

### Data model changes

All changes live in `src/memory/models_v2.py`.

**New reward detail types** (frozen dataclasses):

```python
@dataclass(frozen=True)
class RelicReward:
    name: str
    description: str = ""   # BBCode-stripped at extract time
    rarity: str = ""

@dataclass(frozen=True)
class CardReward:
    name: str
    cost: int = 0
    card_type: str = ""     # skill/attack/power
    rules_text: str = ""    # BBCode-stripped at extract time
    upgraded: bool = False

@dataclass(frozen=True)
class PotionReward:
    name: str
    description: str = ""   # BBCode-stripped at extract time
    potion_type: str = ""
```

Each exposes `to_dict` / `from_dict`. `from_dict` tolerates unknown keys.

**Key-rename conventions** (Python side, to avoid Python built-in
collisions while keeping mod payload untouched):

- Mod emits `{"name", "description", "rarity"}` for relics. Direct map.
- Mod emits `{"name", "cost", "type", "rules_text", "is_upgraded"}` for
  cards. `from_dict` reads `type` into `card_type`, `is_upgraded` into
  `upgraded`. `to_dict` emits the Python-side field names (`card_type`,
  `upgraded`) so persisted JSONL is self-consistent after first
  extraction round. Legacy records with `is_upgraded`/`type` keys are
  still accepted by `from_dict`.
- Mod emits `{"name", "description", "type"}` for potions. `from_dict`
  reads `type` into `potion_type`.

**`EventOptionSnapshot` extension** (backward-compatible `from_dict`):

```python
@dataclass(frozen=True)
class EventOptionSnapshot:
    index: int = 0
    title: str = ""                 # BBCode-stripped
    description: str = ""           # BBCode-stripped (from effect_description if available)
    hp_cost: int | None = None
    gold_cost: int | None = None
    relics_offered: tuple[RelicReward, ...] = ()
    cards_offered: tuple[CardReward, ...] = ()
    potions_offered: tuple[PotionReward, ...] = ()
```

Legacy JSONL compatibility: `from_dict` detects when each element is a
bare string (old format `["relic_name_1", ...]`) and upgrades to
`RelicReward(name=s)` / `CardReward(name=s)` / `PotionReward(name=s)`.
When the element is already a dict, it forwards to the respective
`from_dict`.

**`EventGuide` extension**:

```python
@dataclass(frozen=True)
class EventGuideOption:
    canonical_name: str
    stage_index: int                # 0-based
    variant_type: str               # "fixed" | "random_from_pool" | "deck_random"
    score: float                    # -1.0 to 1.0
    analysis: str                   # 1-2 sentence rationale
    observed_rewards: tuple[str, ...] = ()  # concrete names for random_from_pool
    sample_size: int = 0            # encounters this option appeared in

@dataclass(frozen=True)
class EventGuide:
    guide_id: str
    event_id: str
    character: str
    guide_text: str                 # cross-option takeaway (1-2 sentences)
    options: tuple[EventGuideOption, ...] = ()    # ← NEW
    episode_count: int = 0
    confidence: float = 0.5
    version: int = 1
    created_at: float
    updated_at: float
```

Legacy `EventGuide` JSONL without `options`: `from_dict` defaults
to `()`. Retriever handles empty-options case by falling back to
`guide_text`-only injection.

### Extractor changes

**`src/agent/loop.py::_finalize_event_stage`** (lines ~3099–3131):

Current code reduces each reward dict to `{"name": ...}`. Replace the
reduction with full-fidelity capture:

```python
# strip_bbcode on all user-visible text at capture time
from src.brain.prompts._deck_fmt import strip_bbcode

all_details: list[dict] = []
if self._prev_event_gs.event:
    for o in self._prev_event_gs.event.options:
        # Use effect_description if available, else description
        raw_desc = getattr(o, "effect_description", "") or getattr(o, "description", "")
        detail = {
            "index": o.index,
            "title": strip_bbcode(o.title),
            "description": strip_bbcode(raw_desc),
        }
        if getattr(o, "hp_cost", None) is not None:
            detail["hp_cost"] = o.hp_cost
        if getattr(o, "gold_cost", None) is not None:
            detail["gold_cost"] = o.gold_cost
        for src_attr, dst_key, keys in (
            ("relics_offered", "relics_offered",
             ("name", "description", "rarity")),
            ("cards_offered", "cards_offered",
             ("name", "cost", "type", "rules_text", "is_upgraded")),
            ("potions_offered", "potions_offered",
             ("name", "description", "type")),
        ):
            raw_list = getattr(o, src_attr, []) or []
            if raw_list:
                detail[dst_key] = [
                    {k: strip_bbcode(v) if isinstance(v, str) else v
                     for k, v in (
                        item.items() if isinstance(item, dict)
                        else {"name": str(item)}.items()
                     )
                     if k in keys or k == "name"}
                    for item in raw_list
                ]
        all_details.append(detail)

# Drop Proceed-only stages
is_proceed_only = (
    self._prev_event_gs.event
    and all(getattr(o, "is_proceed", False)
            for o in self._prev_event_gs.event.options)
)
if is_proceed_only:
    stm.cancel_event()  # discards _current_event without persisting
    return
```

A new `ShortTermMemory.cancel_event()` method discards the current
tracker without appending to `_completed_events`.

The extractor layer (`src/memory/event_extractor.py`) is unchanged
because it simply reads `tracker.all_option_details` and wraps in
`EventOptionSnapshot.from_dict`, which now handles the richer dicts.

### Consolidator changes

**`src/memory/guide_consolidator.py`**.

**Selection** — new helper, mirrors combat:

```python
def _select_event_keys_for_refresh(
    memories: list[EventMemory],
    current_run_id: str,
) -> set[tuple[str, str]]:
    selected: set[tuple[str, str]] = set()
    for em in memories:
        if em.run_id == current_run_id:
            selected.add((em.event_id.upper(),
                          normalize_character(em.character)))
    return selected
```

The event branch of `consolidate_guides` replaces the current full-scan
grouping with:

```python
selected = _select_event_keys_for_refresh(event_store.get_all(), current_run_id)
for (event_id, character) in sorted(selected):
    memories = [m for m in event_store.get_all()
                if m.event_id.upper() == event_id
                and normalize_character(m.character) == character]
    if len(memories) < min_episodes:
        continue
    existing = guide_store.get_event_guide(event_id, character)
    prompt = build_event_guide_prompt(event_id, character, memories, existing)
    raw, _, _ = await llm_call_raw(EVENT_ANALYST_PROMPT, prompt,
                                   think=True, call_type="guide_event")
    guide = parse_event_guide_response(raw, event_id, character,
                                       len(memories), existing)
    if guide:
        guide_store.set_event_guide(guide)
        stats["event"] += 1
```

**Prompt construction** — new `build_event_guide_prompt`:

1. Group `memories` by `(run_id, floor)` → list of playthroughs.
2. Sort each playthrough's stages by `timestamp`.
3. Take the last 12 playthroughs (ordered by most recent run).
4. For each playthrough, render:
   ```
   Playthrough K (run=<id_prefix>, F<floor>, outcome=<VICTORY/DEFEAT> F<run_final_floor>):
     Stage 0: Choose 1 of N
       [i] <title> — <description>
           [relic] <name> (rarity=<r>) — <description>
           [card]  <name> [+] cost=<c> type=<t> — <rules_text>
           [potion] <name> (type=<t>) — <description>
       → chose [i], diff: HP x→y, Gold a→b, +[...], -[...]
     Stage 1: (if real choices exist)
       ...
   ```
5. **Token budget optimization**: For each `(canonical_name,
   stage_index)` pair, expand full reward details only on first
   occurrence across the prompt. Subsequent occurrences render as
   `[i] <title>  (same as Playthrough K)`.
6. If `existing` guide present, append `Previous guide (v<N>)` block
   with full options JSON so LLM can update in place.
7. Output specification:
   ```
   Respond with JSON:
   {
     "guide_text": "<1-2 sentences: cross-option takeaway>",
     "confidence": <0.0-1.0>,
     "options": [
       {
         "canonical_name": "<name>",
         "stage_index": <int>,
         "variant_type": "fixed|random_from_pool|deck_random",
         "score": <-1.0 to 1.0>,
         "analysis": "<1-2 sentence rationale>",
         "observed_rewards": ["<name>", ...],
         "sample_size": <int>
       }
     ]
   }

   Guidelines:
   - fixed: option outcome is deterministic across encounters.
   - random_from_pool: option rewards a roll from a fixed pool
     (e.g. "a random Uncommon relic").
   - deck_random: option transforms/affects a random card from your deck.
   - score: weight by run outcome anchor (VICTORY>DEFEAT), concrete
     state-diff gain (HP/gold/cards/relics), and cross-encounter stability.
   - Do NOT invent options not seen in any playthrough.
   - Merge random-variant observations under a single canonical_name;
     enumerate concrete observed rewards in `observed_rewards`.
   ```

**Parsing** — new `parse_event_guide_response`:

- Parse outer JSON; on failure return `None` (consolidator preserves
  previous guide).
- Coerce each option dict to `EventGuideOption`; skip malformed entries
  but keep valid siblings.
- Clamp `score` to `[-1.0, 1.0]`; clamp `confidence` to `[0.0, 1.0]`.
- Recompute `sample_size` per option from memories (not trusting LLM):
  for each `canonical_name`, count memories whose
  `chosen_option_index` / `all_options` contained a matching title.
  This avoids drift across versions.

### Retriever / injection changes

**`src/memory/retriever.py`** — the `for_event_decision` pathway (or
wherever event guides are currently fed into `WorkingContext`).

Current behavior: inject `EventGuide.guide_text` as a blob.

New behavior:

1. Fetch `EventGuide` for `(event_id, character)`.
2. Filter `options` to those whose `stage_index` matches the current
   event stage. Stage detection: infer from `gs.event` — if the event
   is_finished flag is False and the options list is non-trivial, use
   stage 0. If a stored "stage sequence" is maintained (future),
   use that. For now: default to stage 0, and fall back to all stages
   if filtering would yield empty.
3. Match each current `gs.event.options[i].title` against
   `EventGuideOption.canonical_name` (case-insensitive, after
   `strip_bbcode`). Matched options are the "seen" set; unmatched
   options in `gs.event.options` are "new/unseen".
4. Render injection block:
   ```
   ## Event Guide: <EVENT_ID> (<character>, v<N>)
   <guide_text>

   Options for this encounter (ordered by score):
   - <canonical_name> [<variant_type>, score <+/-0.00>, seen <n>x]
     <analysis>
   - [Option "<title>" not in guide — new or unseen]
   ```
5. Keep the existing working-context-trim registration in sync
   (add the new field to `_trim_working_context` if a separate
   `event_guide_options` hint field is introduced; otherwise the
   whole block lives in `event_guide_text`).

### What stays untouched

- `EventMemory` schema (the snapshot is already on
  `all_option_details`; we only change the shape of the elements).
- `event_extractor.py` body (it transparently wraps via
  `EventOptionSnapshot.from_dict`).
- `EventMemoryStore` API.
- Combat/route/deck consolidation.
- `EVENT_ANALYST_PROMPT` system prompt.
- Postrun ordering in `loop._post_run_memory_update`.

## Data compatibility

| Artifact | Action |
|---|---|
| Existing `EventMemory` JSONL with string-only reward lists | `EventOptionSnapshot.from_dict` detects `str` elements and upgrades to `RelicReward(name=s)` etc. with empty description/rarity/rules_text. Consolidator prompt tolerates empty description — it just renders the name. |
| Existing `EventGuide` JSONL without `options` field | `from_dict` defaults to `()`. Retriever falls back to `guide_text` only. First consolidation run refreshes the options. |
| Existing Proceed-only stage records in the store | Left in place; consolidator sees them as stage-2 entries. Filtering in `_finalize_event_stage` applies only to new records. Over time the old records become a diminishing tail. |

## Invariants preserved

1. No extra LLM call beyond the existing `guide_event` call.
2. `EventMemory` remains append-only; no in-place mutation.
3. `CONSOLIDATION_MIN_EPISODES` still gates whether an event gets
   consolidated at all.
4. Guide store update is still atomic (`set_event_guide` replaces the
   record by `(event_id, character)`).
5. Parse failure does not drop the existing guide — it logs and
   short-circuits, same as today.

## Risks

1. **Schema upgrade in-place**: `EventOptionSnapshot` field type
   changes from `tuple[str, ...]` to `tuple[RelicReward, ...]` etc.
   Mitigated by `from_dict` auto-upgrading string elements. Regression
   surface: any consumer that indexes into these tuples expecting
   strings — none found in current code (grep confirmed only
   consolidator + extractor touch these).
2. **LLM JSON drift**: LLM may occasionally emit malformed `options`
   arrays. Mitigation: parse per-option; valid entries survive;
   whole-response parse failure preserves prior guide.
3. **`observed_rewards` accuracy for random variants**: LLM may
   conflate two different random pools. Mitigation: recompute
   `sample_size` server-side from memory scan; LLM's claim becomes a
   hint, not source of truth. `observed_rewards` stays LLM-authored
   (used only for descriptive display).
4. **Proceed-only drop false positive**: If any event has a stage
   where all options are literally labeled "Proceed" but diverge in
   effect, we'd discard. Mitigation: filter is stricter —
   `all(is_proceed)` on the mod-provided flag, not title text. Mod
   sets `is_proceed` only for closing screens.
5. **Stage inference from timestamp**: If two stages are finalized in
   rapid succession (< 1ms apart on Windows), timestamp ordering could
   tie. Mitigation: secondary sort key is `chosen_option_index` /
   memory insertion order in `EventMemoryStore`.
6. **Retriever output bloat**: With large option libraries, the
   injection block grows. Mitigation: only "seen this encounter"
   options are rendered, which caps the list at `len(gs.event.options)`.

## Validation plan

- Baseline test count: unchanged.
- New / extended unit tests:
  - `tests/test_event_memory_model.py`:
    - `RelicReward/CardReward/PotionReward` round-trip.
    - `EventOptionSnapshot.from_dict` legacy-string upgrade.
    - `strip_bbcode` applied to title/description/rules_text.
    - `EventGuide.from_dict` with and without `options`.
    - `EventGuideOption` round-trip.
  - `tests/test_event_guide_consolidator.py`:
    - `_select_event_keys_for_refresh` filters by `run_id`.
    - Multi-stage playthrough groups correctly by `(run_id, floor)`.
    - `parse_event_guide_response` drops malformed options and keeps
      valid ones.
    - `sample_size` server-recompute overrides LLM-supplied value.
    - Legacy guide (no `options`) survives load → consolidate →
      save round-trip.
  - `tests/test_event_skill_discovery.py` (existing): unchanged (the
    skill discovery path was removed 2026-04-23; only guide path
    remains).
- Live smoke: `STS2_POSTRUN_ENABLED=true python -m scripts.run_agent
  --steps 50 --runs 1` — postrun log should show `guide_event`
  entries only for `(event_id, character)` pairs the run actually
  encountered. Inspect one resulting `EventGuide` via
  `python -m scripts.inspect_memory` to confirm `options` populated
  with scored entries, `analysis` present, `sample_size` matches
  memory count.

## Out of scope / follow-up

- Keyword glossary integration inside event prompts (deferred —
  global glossary already covers this).
- Cross-character evidence pooling for fixed-option events
  (e.g. Orobas fixed options identical across characters —
  could share scoring).
- Stage detection from live game state for retriever (currently
  defaults to stage 0; future: explicit stage tracking on
  `GameState.event`).
- Backfill script to re-enrich old `EventMemory` records using a
  stored snapshot of the knowledge DB at the time those records were
  written. Not done here because the current mod already emits rich
  payloads for new records, and old records stay functional (just
  with empty descriptions).
