# Non-combat Skill Discovery Removal

**Date**: 2026-04-23
**Status**: Approved, pending implementation plan
**Scope**: Delete the LLM-based non-combat skill discovery pipeline

## Motivation

The postrun pipeline currently runs an LLM-based skill discovery pass that emits
candidate skills in `map / rest / event / deck_building` categories (combat
candidates were migrated out on 2026-04-19 to `mistake_discovery.py`). Empirically
this pass underperforms:

- Its system prompt still reads like a combat prompt — talks about "HP efficiency",
  "Tank the damage", lists `combat` and `boss` as valid categories, and shows
  round-level examples (`Floor 8 vs Lagavulin: tanked 18 dmg…`). Combat candidates
  get silently dropped downstream, but the LLM is still primed by combat framing.
- The four non-combat categories are already well-served by narrower mechanisms:
  `RouteGuide` (per act×character), `DeckGuide` (per archetype×character),
  `EventGuide` (per event_id×character), and authored `rest` / `map` /
  `deck_building` seed skills.
- There is no cross-type dedup between guides and discovered skills, so
  near-duplicate content routinely lands in prompts twice.

The architectural principle we are committing to:

> **Skills = error correction. Guides = memory.**

Non-combat decisions (map / rest / event / deck building) are low-complexity
choices from a small, enumerable option set. Memory (guides) + authored
baselines (seed skills) suffice. A run-derived error-correction layer is
unnecessary and produces net-negative prompt churn.

Combat decisions remain an error-correction target — the dedicated
`mistake_discovery.py` pipeline owns that and is out of scope for this change
(slated for its own review next).

## Goal

Delete the entire non-combat LLM skill discovery pipeline. Preserve authored
seed skills, skill retrieval at decision time, skill lifecycle, and the combat
mistake-discovery pipeline.

Non-goals:

- Any change to combat skill discovery.
- Any change to seed skill content.
- Any purge of previously-discovered non-combat skills from `skills/skills.json`
  — they will age out via the existing lifecycle policy.

## Scope

### Files deleted

1. `src/skills/discovery.py` — entire module (`_DISCOVERY_SYSTEM`,
   `_DISCOVERY_PROMPT`, `build_discovery_prompt`, `discover_skills`,
   `gate_candidates`, `_parse_discovered_candidates`, and all formatting helpers).

### `src/agent/loop.py` edits

Remove:

- Module-level constant `_NONCOMBAT_DISCOVERY_CATEGORIES` (line 111).
- Field `self._skill_run_count` and its initialization via
  `_load_counter("skill_discovery")` (line 414).
- All six `_save_counter("skill_discovery", …)` calls.
- The discovery trigger counter block that increments `_skill_run_count` in the
  postrun loop (lines 3820–3825).
- Method `_run_sync_skill_discovery` (~lines 3965–4018).
- The `"discovery"` branch inside `_post_run_batch_submit`
  (lines 4043–4090).
- The `"discovery"` branch inside `_check_pending_batches`
  (lines 4136–4164). Preserve the surrounding `try/except` shell and the
  `"distillation"` branch.
- The non-Anthropic sync discovery fallback block inside
  `_post_run_skill_update` (~lines 4566–4617). The surrounding
  `_score_noncombat_skills_end_of_run`, `self._skill_library.save`, and
  retirement sweep remain.

### `config.py` edits

Remove:

- `SKILLS_DISCOVERY_ENABLED`
- `SKILLS_DISCOVERY_EVERY_N_RUNS`

### Test edits

- `tests/test_event_skill_discovery.py` — delete entire file.
- `tests/test_postrun_context_builder.py` —
  delete `test_build_discovery_prompt_reuses_full_run_digest_without_deduping`
  and prune the `from src.skills.discovery import build_discovery_prompt`
  import. Remaining `build_decision_digest` tests stay.
- `tests/test_token_optimization.py` — delete the tests inside
  `TestSkillGeneration400Char` that import `_parse_discovered_candidates`
  (two tests). Retain the class if other tests remain; otherwise drop it.
- `tests/test_loop_post_run.py` — delete `_skill_run_count` assignments and
  `SKILLS_DISCOVERY_*` monkeypatches; rewrite affected cases to exercise only
  the behaviour that survives (mistake discovery + retirement sweep + save).

## What stays untouched

- `SkillLibrary`, `composer`, `models`, `dedup`, `lifecycle`, `write_gate`,
  `merge_pipeline`, `replay_evaluator`, `combat_quality`.
- `mistake_discovery.py`, `critic_prompt.py`, `prewrite_ab.py` (combat path).
- All `src/skills/seeds/*.json` including the non-combat seeds
  (`core_map_routing.json`, `core_rest_decision.json`,
  `core_deck_building.json`).
- `noncombat_scorer.py` — it scores how often existing non-combat seeds were
  invoked per run and nudges their confidence, independent of any discovery
  pipeline. `_score_noncombat_skills_end_of_run` continues to run.
- The decision-time skill retrieval call in `loop.py` (`skill_library.query`
  at line 5200) and all its call sites in non-combat prompts. Seed skills
  continue to be retrieved and injected.

## Data compatibility

| Artifact | Action |
|---|---|
| `skills/skills.json` (may contain prior discovered non-combat skills) | Leave in place. Existing entries age out via `lifecycle.apply_retirement_policy` + category caps. |
| Pending Anthropic Batch API "discovery" requests | Silently dropped on receipt (the branch that handled them is removed). Non-critical postrun step — acceptable. |
| `data/skill_discovery_counter.json` | Becomes orphaned. Not actively deleted. No reader remains. |

## Invariants preserved

1. Seed skills continue loading at agent start and retrieval at decision time.
2. Non-combat prompts (`map`, `rest`, `event`, `card_reward`, `shop`, etc.)
   continue to receive skill injection whenever seed skills match.
3. Combat skill discovery via `mistake_discovery.py` is unchanged.
4. `_score_noncombat_skills_end_of_run` still runs each postrun; non-combat seed
   confidence updates continue.
5. Retirement sweep + category caps still run each postrun.

## Risks

1. **Four removal points in `loop.py` sit inside distinct control blocks**
   (sync trigger, sync method, batch submit, batch result, late sync fallback).
   Each must be excised with surrounding `try/except` / guard clauses intact.
   Validation: after each edit, confirm the surrounding method still parses and
   its happy path still executes.
2. **Batch result handler must keep the outer loop alive.** Removing only the
   `if task["type"] == "discovery"` branch. The surrounding `for task in …` +
   `try/except` + `elif task["type"] == "distillation"` must stay intact.
3. **Test files are partially deleted, not wholesale removed.**
   `test_postrun_context_builder.py`, `test_token_optimization.py`, and
   `test_loop_post_run.py` contain unrelated tests that must keep passing.
   Grep for discovery imports after edits to catch orphan references.
4. **Counter field removal**. `self._skill_run_count` is referenced in 9+
   places. Grep audit before marking done.

## Validation plan

- `pytest tests/` — expect no new failures beyond the 3 pre-existing unrelated
  failures (`test_write_gate_reap_integration.py` ×2,
  `test_token_optimization.py::test_evolution_returns_error_for_long_content`).
- `python -c "import src.agent.loop"` — smoke import.
- `python -c "from src.skills.library import SkillLibrary; print('ok')"` —
  confirm the surviving surface is importable.
- Short run: `python -m scripts.run_agent --steps 50 --runs 1` — confirm
  postrun does not attempt discovery, seed skills load, and prompts injecting
  skills still function.
- `grep -rn 'SKILLS_DISCOVERY\|_skill_run_count\|skills\.discovery' src/ tests/`
  must return zero hits.

## Out of scope / follow-up

- Audit of `mistake_discovery.py` (combat skill pipeline) — separate review.
- `noncombat_scorer.py` policy review (does its current formula still make
  sense when there are no discovered non-combat skills?) — can land as a
  follow-up; no blocking dependency on this change.
- Event guide prompt tuning and other downstream postrun prompts —
  separate tracks already in flight.
