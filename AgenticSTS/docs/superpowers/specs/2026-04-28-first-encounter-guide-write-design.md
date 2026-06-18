# First-encounter guide / card-note write — design

**Date:** 2026-04-28
**Status:** Draft, pending implementation plan
**Motivation:** Self-evolve ablation runs from blank stores. Current `min_episodes=2` gate blocks all guide writes during postrun of run 1 — agent learns nothing from its first run. This change makes the first encounter with any enemy / event / route / deck-archetype / unannotated-card always trigger a write, after which the existing selective-refresh mechanism resumes.

## Problem

Current postrun guide consolidation has two layers of gating that suppress first-encounter writes:

1. **`min_episodes = 2`** ([config.py:476](../../../config.py)) — combat / event / route / deck consolidators all skip a key whose episode count is `< 2`. Effect: nothing gets written until the second occurrence.
2. **Combat selection** ([guide_consolidator.py::_select_combat_keys_for_refresh](../../../src/memory/guide_consolidator.py)) — bosses + elites always selected; small monsters only the worst-per-act-character. Effect: most small monsters never enter the LLM consolidation loop at all, regardless of episode count.

Card notes have a different problem: [card_note_updater.py:108-110](../../../src/memory/card_note_updater.py) prompt says "**Favor** cards where ... no note yet" — soft hint, not a requirement. Empty-noted cards may still be skipped if the LLM judges nothing else is interesting.

For a self-evolve run starting from blank stores, this means run 1 produces effectively zero L4 knowledge. Run 2 starts mostly blank too because most encounters are first-encounters of new keys. Learning curve is shifted by ~2 runs unnecessarily.

## Decisions locked

| ID | Decision |
|----|----------|
| D1 | Two independent tracks: (A) card via prompt strengthening, (B) guides via code-level bypass. |
| D2 | First-encounter bypass triggers when `existing_guide is None` AND there is ≥1 non-aborted episode for the key in the current run. |
| D3 | Aborted-only keys do NOT trigger bypass. Existing aborted-episode filtering preserved. |
| D4 | Combat selection layer also gets a None-guide override, otherwise small non-worst monsters never enter the loop. |
| D5 | 1-episode prompt quality not addressed in this change — observe in self-evolve pilot before deciding whether to harden prompts. |
| D6 | Cost: run 1 of self-evolve will spike to +30-50 guide LLM calls (every key first-time). Run 2+ regresses to selective refresh. Acceptable. |

## Track A — `card_note_updater` prompt strengthening

**File:** [`src/memory/card_note_updater.py`](../../../src/memory/card_note_updater.py)

**Change:** Strengthen [`_UPDATER_PROMPT_TEMPLATE`](../../../src/memory/card_note_updater.py) instructions section.

Current text (lines 105-114):

```
For each candidate card, decide whether the traces at the top of this user
message justify a new or updated note. Favor cards where the trace reveals
something the current note misses, or where the card has no note yet. Keep
new_note terse (<=200 chars), concrete, and oriented toward future deck-
building decisions. Never invent cards not in the candidate list.
```

Replace with:

```
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
```

The "shown as `—` in the table" hint must match what `_render_candidate_table` emits for empty-note cards — verify during implementation that empty notes render as `—` (em-dash) and not as an empty string or `None`. If the rendering differs, adjust the prompt to match.

## Track B — guide consolidator code changes

Four guide types share a common bypass pattern:

```python
non_aborted_count = sum(
    1 for e in episodes_or_memories
    if not getattr(e, "is_aborted", False)
    and not _is_otherwise_aborted(e)  # e.g. route boss_result == "aborted"
)

if existing is None and non_aborted_count >= 1:
    pass  # first-encounter bypass — proceed into LLM call
elif len(episodes_or_memories) < min_episodes:
    continue
```

The check sits **after** `existing = guide_store.get_X_guide(...)` and **before** the existing `min_episodes` gate. The condition is intentionally `non_aborted_count >= 1` not `len(episodes) >= 1` — pure-aborted keys do not trigger first-write.

### B.1 Combat (`guide_consolidator.py`)

Two-level fix because combat has both selection and min_episodes gates:

**Selection (`_select_combat_keys_for_refresh`):**

Current signature:
```python
def _select_combat_keys_for_refresh(
    episodes: list[CombatEpisode],
    current_run_id: str,
) -> set[tuple[str, str]]:
```

New signature:
```python
def _select_combat_keys_for_refresh(
    episodes: list[CombatEpisode],
    current_run_id: str,
    guide_store: GuideStore | None = None,
) -> set[tuple[str, str]]:
```

After the existing boss/elite/worst-per-act selection logic, add:

```python
# First-encounter bypass: any (key) with no existing guide and ≥1 non-aborted
# episode in the current run is forced into the refresh set, even if it would
# otherwise have been filtered out (e.g. a small monster that's not the
# worst-of-act).
if guide_store is not None:
    for ep in episodes:
        if ep.run_id != current_run_id or getattr(ep, "is_aborted", False):
            continue
        key = (
            normalize_enemy_key(ep.enemy_key),
            normalize_character(ep.character),
        )
        if guide_store.get_combat_guide(*key) is None:
            selected.add(key)
```

The `consolidate_guides` call site (line 1106) updates to pass `guide_store`:

```python
selected_keys = _select_combat_keys_for_refresh(
    all_episodes, current_run_id, guide_store=guide_store,
)
```

**Min-episodes bypass (inside the per-key loop, around line 1116):**

```python
non_aborted = [e for e in episodes if not getattr(e, "is_aborted", False)]

if existing is None and len(non_aborted) >= 1:
    pass  # first-encounter bypass
elif len(episodes) < min_episodes:
    continue
```

### B.2 Event (`event_guide_consolidator.py`)

Selection layer already covers all events from current run — only min_episodes bypass needed (around line 408):

```python
non_aborted = [m for m in memories if not getattr(m, "is_aborted", False)]

if existing is None and len(non_aborted) >= 1:
    pass  # first-encounter bypass
elif len(memories) < min_episodes:
    continue
```

EventMemory may not have an `is_aborted` field — use `getattr(..., "is_aborted", False)` defensively. If the field is unused, all memories count as non-aborted (correct behavior).

### B.3 Route (`guide_consolidator.py`)

The route consolidator already filters `mem.boss_result == "aborted"` and per-node `is_aborted` upstream of the loop ([line 1160-1161](../../../src/memory/guide_consolidator.py)). Memories that survive this filter are all non-aborted. Bypass simplifies to:

```python
if existing is None and len(memories) >= 1:
    pass  # first-encounter bypass
elif len(memories) < min_episodes:
    continue
```

### B.4 Deck (`guide_consolidator.py`)

Deck guide consolidation uses the more complex `_deck_guide_needs_refresh` short-circuit — bypass needs to interact with that gate carefully. Around line 1222:

Current:
```python
if len(builds) < min_episodes:
    continue

existing = guide_store.get_deck_guide(character, archetype)
source_fingerprint = _deck_guide_source_fingerprint(builds)
if not _deck_guide_needs_refresh(existing, builds):
    continue
```

New:
```python
existing = guide_store.get_deck_guide(character, archetype)
non_aborted = builds  # CardBuildMemory does not have is_aborted today

if existing is None and len(non_aborted) >= 1:
    pass  # first-encounter bypass
elif len(builds) < min_episodes:
    continue

source_fingerprint = _deck_guide_source_fingerprint(builds)
if not _deck_guide_needs_refresh(existing, builds):
    continue
```

The order matters: `existing = ...` must come before the bypass check (was after the `min_episodes` check).

## Edge cases

- **Aborted-only key**: pure-aborted episodes do not trigger first-write (see D3). After more runs the key may accumulate non-aborted episodes; first-write triggers then.
- **1-episode prompt quality**: prompts currently iterate over episodes / memories, so single-input does not crash. Output quality may be weaker (e.g. mechanic_summary based on one fight) — accepted for now (D5). If pilot reveals empty / nonsensical guides, harden prompts with explicit "if only one episode, focus on observable mechanics rather than strategy" framing.
- **selective-refresh "already up-to-date" short-circuit** (combat: `if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary: continue`): unchanged. Bypass only fires when `existing is None`, so this short-circuit is unreachable from bypass path.
- **`current_note` rendering**: verified at spec time — [`_render_candidate_table`](../../../src/memory/card_note_updater.py) emits `(empty)` for cards with `mem.note == ""` and `(no memory yet)` for cards with no memory entry. Track A prompt matches both literals.

## Test plan

Combat:
- `_select_combat_keys_for_refresh` with `guide_store=None` returns the historical baseline (boss + elite + worst-per-act) — back-compat.
- `_select_combat_keys_for_refresh` with empty guide store and 1 small non-worst monster episode in current run includes that key.
- Per-key consolidation loop with `existing=None` + 1 non-aborted episode triggers LLM call (mock `llm_call_raw`, assert called once).
- Per-key consolidation loop with `existing=None` + 1 aborted episode does NOT trigger LLM call.
- Per-key consolidation loop with `existing=existing_guide` + 1 episode falls back to old `min_episodes=2` skip.

Event / Route / Deck:
- Same shape: empty store + 1 non-aborted record triggers write; pure-aborted does not; existing guide regresses to old gate.

Card:
- Snapshot test on `_UPDATER_PROMPT_TEMPLATE` confirming the literal "MANDATORY first-note rule" phrase is present. (Behavioral test — does the LLM actually obey — is too expensive for unit; covered by manual review of card_memory output after first self-evolve pilot run.)

## Out of scope

- Hardening 1-episode prompt quality (D5).
- Changing card_memory_extractor (statistical pipeline, already first-encounter aware).
- Skill discovery first-encounter rules (mistake-driven path runs independently).
- Seed guides (currently no seed guide files; could be added later if first-encounter quality is consistently bad).
