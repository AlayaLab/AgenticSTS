# Combat Guide Selective Refresh

**Date**: 2026-04-23
**Status**: Approved, pending implementation plan
**Scope**: Replace the full-scan combat guide consolidation loop with a run-scoped selection policy

## Motivation

Current `consolidate_guides()` runs every postrun and, for the combat branch,
walks the **entire** `combat_store` — grouping all historical episodes by
`(enemy_key, character)` and refreshing any group whose
`episode_count < len(episodes)` or where `mechanic_summary` is missing.

Observed problems in live runs:

1. **Cross-character / cross-run refreshes**. A Silent run triggers Ironclad
   deck/combat guide rebuilds as long as the historical group has new episodes
   relative to the stored `episode_count`. The agent spends LLM tokens
   regenerating guides for characters it didn't even play.
2. **Even same-character refreshes are too frequent**. Every small enemy
   fought this run becomes a candidate. A mature guide against a common
   Act 1 monster gets rebuilt on every encounter despite zero new insight.
3. **Frequency mismatch with difficulty**. Boss and elite guides are the
   high-leverage ones — they decide run outcomes. Small monsters are
   frequent and cheap; most of their guides stabilize quickly and don't
   reward refresh.

The architectural principle:

> **Refresh the guides this run actually produced evidence for. Prioritize
> refreshes by stakes (boss/elite every time) and pain (the single worst
> small-monster fight per act).**

## Goal

Replace the combat section of `consolidate_guides()` with a run-scoped
selection policy:

- **All boss fights from this run → refresh.**
- **All elite fights from this run → refresh.**
- **Per act, the single small-monster fight with highest HP loss → refresh.**
  (At most 3 per run, since a run has at most 3 acts.)
- **Anything else — not touched.** No cross-run or cross-character refresh.

Non-goals:

- Any change to the route / deck / event guide consolidation branches.
  They keep full-scan behavior until a future task.
- Any change to the LLM prompt for combat guide consolidation.
- Any change to how the LLM receives historical episodes — once a key is
  selected, the LLM still sees the full cross-run history for that
  `(enemy_key, character)` so the guide reflects aggregate learning.

## Scope

### What changes

**`src/memory/guide_consolidator.py::consolidate_guides`** (around lines
772–821, the combat branch): replaced with the selection policy below.

**Signature change:** `consolidate_guides(memory_manager)` →
`consolidate_guides(memory_manager, *, current_run_id: str)`. The run_id is
required; it's the pivot for "which episodes this run contributed." The
caller in `src/agent/loop.py:3782` updated to pass
`self._run_state.run_id`.

### The selection algorithm

Input: current `run_id`, full `combat_store`.

Pre-filter: pull the subset of `combat_store.get_all()` whose
`run_id == current_run_id` and `not is_aborted`.

```
selected_keys: set[(enemy_key, character)] = {}

# 1. All boss and elite fights from this run
for ep in run_episodes:
    if ep.combat_type in ("boss", "elite"):
        selected_keys.add((normalize_enemy_key(ep.enemy_key),
                           normalize_character(ep.character)))

# 2. Per act: the small-monster fight with max HP loss
worst_monster_per_act: dict[int, CombatEpisode] = {}
for ep in run_episodes:
    if ep.combat_type != "monster":
        continue
    hp_loss = ep.hp_before - ep.hp_after
    prev = worst_monster_per_act.get(ep.act)
    if prev is None or hp_loss > (prev.hp_before - prev.hp_after):
        worst_monster_per_act[ep.act] = ep

for ep in worst_monster_per_act.values():
    selected_keys.add((normalize_enemy_key(ep.enemy_key),
                       normalize_character(ep.character)))
```

For each key in `selected_keys`, run the existing refresh pipeline unchanged:
fetch **full** historical episodes for the key from `combat_store`, run
`CONSOLIDATION_MIN_EPISODES` gate, call LLM with the existing
`build_combat_guide_prompt`, persist via `guide_store.set_combat_guide`.

### Edge cases

| Case | Behavior |
|---|---|
| Early death in Act 1 | Only Act 1 entries exist in `worst_monster_per_act`. At most 1 monster refreshed + any elites encountered. |
| Act with no small monsters (e.g. only events) | That act's slot absent from `worst_monster_per_act`. Skip silently. |
| Two small monsters tied on max HP loss in same act | Pick whichever was encountered first (iteration order over `run_episodes` — already floor-ordered in `combat_store`). Log a debug line. |
| Selected small monster had 0 HP loss (perfect clean win as sole Act fight) | Still refreshed. ≤ 3 small-monster refreshes per run is a cheap cap; not worth an extra "skip if clean" rule. |
| Selected key's cross-run history has fewer than `CONSOLIDATION_MIN_EPISODES` episodes | Same as today — the existing `min_episodes` gate continues to skip. |
| `run_episodes` is empty (no combats this run, e.g. interrupted at character select) | `selected_keys` is empty. Combat branch is a silent no-op. Other branches still run. |

### What stays untouched

- Route / deck / event branches of `consolidate_guides`.
- `CONSOLIDATION_MIN_EPISODES`, `CONSOLIDATION_EVERY_N_RUNS`.
- `build_combat_guide_prompt`, `parse_combat_guide_response`,
  `COMBAT_ANALYST_PROMPT`.
- LLM's view of the combat guide prompt (it still receives full cross-run
  history for the selected key).
- `CombatEpisode` model.
- `CombatMemoryStore` API.

## Data compatibility

| Artifact | Action |
|---|---|
| Existing `CombatGuide` records in `memory/v2/guides.json` | Unchanged. New policy only changes **when** they're refreshed, not the record shape. |
| Guides for keys the new policy will never select (e.g. mature small-monster guides) | Left in place. They remain retrievable for prompt injection; they just won't be auto-updated until they happen to become the act's worst fight. |

## Invariants preserved

1. Guide store content round-trips cleanly; no schema change.
2. Retriever-side consumption of combat guides is unaffected.
3. `CONSOLIDATION_MIN_EPISODES` gate still applies to the selected keys.
4. Route, deck, event consolidation cadence and full-scan scope unchanged.

## Risks

1. **Signature change**: `consolidate_guides` gains a required kwarg.
   The single caller (`src/agent/loop.py:3782`) must be updated in the
   same commit. Tests that call `consolidate_guides` directly
   (if any) also need the kwarg.
2. **Old combat guides go stale under the new policy**. If a guide was
   written under the old full-scan logic, it will not be auto-refreshed
   by the new policy unless the enemy reappears as "this run's worst
   act-k small monster." That's the intended behavior, but it means
   pre-existing guides may permanently reflect older data. Acceptable —
   they still feed retrieval.
3. **Ties at zero HP loss**: an Act with multiple 0-HP-loss monster
   fights will pick the first-seen. Logged, not surfaced. No correctness
   hazard.

## Validation plan

- `pytest tests/` — baseline failure count unchanged.
- Unit tests:
  - Run with 2 bosses, 1 elite, 5 monsters across 2 acts → selects
    exactly `{2 boss keys, 1 elite key, Act1 worst monster,
    Act2 worst monster}` = 5 keys.
  - Run with only small monsters in Act 1 → selects 1 key.
  - Run with `combat_store` entries from other characters / other run_ids
    present → those keys do not appear in `selected_keys`.
  - Run with 0 combats → `selected_keys` empty, no LLM calls.
  - Tie between two same-act monsters → first-seen wins.
- Live smoke run (50 steps) — postrun log shows at most a handful of
  `Consolidated combat guide` lines, none for characters other than
  this run's.

## Out of scope / follow-up

- Route, deck, event guide consolidation — separate future task.
- Deck guide's `memory_count != build_count` refresh bug (should be `<`)
  — separate future task.
- Cleaning up stale locale entries (Chinese card names) in
  `card_build_store` — separate future task.
