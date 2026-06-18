# Non-combat Skill Discovery Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the non-combat LLM skill discovery pipeline. Preserve seeds, retrieval, lifecycle, and the combat mistake-discovery path.

**Architecture:** The pipeline lives in `src/skills/discovery.py` + its 4 call sites in `src/agent/loop.py` + 2 config flags. We remove it in an order that keeps tests green at every commit: first prune tests that import from the module, then strip loop.py of all references, then drop config flags, finally delete the module.

**Tech Stack:** Python 3.14, pytest, Anthropic Batch API (indirect).

**Spec:** [docs/superpowers/specs/2026-04-23-noncombat-skill-discovery-removal-design.md](../specs/2026-04-23-noncombat-skill-discovery-removal-design.md)

---

## File Structure

**Deleted files:**
- `src/skills/discovery.py` (entire module)
- `tests/test_event_skill_discovery.py` (only exercises discovery)

**Modified files:**
- `src/agent/loop.py` — 9 distinct removal sites; see Task 2 for the full list
- `config.py` — 2 flags removed
- `tests/test_postrun_context_builder.py` — 1 test + 1 import removed
- `tests/test_token_optimization.py` — 2 tests in `TestSkillGeneration400Char` removed
- `tests/test_loop_post_run.py` — all `SKILLS_DISCOVERY_*` monkeypatches + `_skill_run_count` assignments removed; affected tests rewritten to exercise only surviving behavior

**Untouched (verification targets):**
- `src/skills/library.py`, `src/skills/composer.py`, `src/skills/models.py`
- `src/skills/mistake_discovery.py`, `src/skills/critic_prompt.py`, `src/skills/prewrite_ab.py`
- `src/skills/lifecycle.py`, `src/skills/write_gate*.py`, `src/skills/merge_pipeline.py`
- `src/skills/noncombat_scorer.py` + `_score_noncombat_skills_end_of_run` call in `loop.py:4560`
- `src/skills/seeds/*.json`
- Decision-time skill retrieval at `loop.py:5200` (`skill_library.query`)

---

## Task 1: Prune tests that depend on discovery.py

**Goal:** Drop every test reference to `src.skills.discovery` so that tasks 2–4 don't cascade into false failures.

**Files:**
- Delete: `tests/test_event_skill_discovery.py`
- Modify: `tests/test_postrun_context_builder.py`
- Modify: `tests/test_token_optimization.py`
- Modify: `tests/test_loop_post_run.py`

- [ ] **Step 1: Establish baseline failure set**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: `1730 passed` OR `1727 passed, 3 failed` where the 3 failures are:
- `tests/test_write_gate_reap_integration.py::test_flush_write_gate_judge_invokes_reap_when_enabled`
- `tests/test_write_gate_reap_integration.py::test_flush_write_gate_judge_skips_reap_when_disabled`
- `tests/test_token_optimization.py::TestSkillGeneration400Char::test_evolution_returns_error_for_long_content`

Write this baseline number down. Every subsequent task must not increase the failure count.

- [ ] **Step 2: Delete `tests/test_event_skill_discovery.py`**

The entire file tests the discovery prompt's event-section assembly; nothing in it is salvageable after discovery.py is gone.

```bash
rm tests/test_event_skill_discovery.py
```

- [ ] **Step 3: Remove discovery import + test from `tests/test_postrun_context_builder.py`**

Remove the top-level import:

```python
from src.skills.discovery import build_discovery_prompt
```

Remove the one test that uses it: `test_build_discovery_prompt_reuses_full_run_digest_without_deduping` (around line 217–249). Leave every other test in the file untouched — they exercise `build_decision_digest` directly, which stays.

After the edit, the file must have **zero** references to `src.skills.discovery`:

```bash
grep -n discovery tests/test_postrun_context_builder.py
```

Expected: no output.

- [ ] **Step 4: Remove `_parse_discovered_candidates` tests from `tests/test_token_optimization.py`**

Around lines 347 and 362 there are two tests inside `TestSkillGeneration400Char` that import and call `_parse_discovered_candidates`. Delete those two tests.

Leave `test_evolution_returns_error_for_long_content` (the pre-existing failure) and any other tests in the class alone. If the class becomes empty after the deletion, also remove the empty class.

After the edit:

```bash
grep -n '_parse_discovered_candidates\|src\.skills\.discovery' tests/test_token_optimization.py
```

Expected: no output.

- [ ] **Step 5: Prune `SKILLS_DISCOVERY_*` / `_skill_run_count` from `tests/test_loop_post_run.py`**

Around line 102, 112, 113 the tests:
- Assign `loop._skill_run_count = 0`
- Monkeypatch `config.SKILLS_DISCOVERY_ENABLED = True`
- Monkeypatch `config.SKILLS_DISCOVERY_EVERY_N_RUNS = 1`

Walk every test in the file. For each test that references any of these three names:
- Remove the monkeypatches.
- Remove the `_skill_run_count` assignment.
- If the test was specifically asserting that discovery ran (e.g. asserting a mocked `discover_skills` was called), delete the test entirely.
- If the test was exercising some other behavior (retirement sweep, save path) and just happened to set these values as prerequisites, keep the test but drop only the now-obsolete lines.

After the edit:

```bash
grep -n 'SKILLS_DISCOVERY\|_skill_run_count\|src\.skills\.discovery' tests/test_loop_post_run.py
```

Expected: no output.

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: failure count **equal to the baseline from Step 1** (the same 3 pre-existing unrelated failures, or zero). If the number increased, you broke something — do not proceed. Read the new failure, decide whether the test is discovery-adjacent and should be pruned further, or whether the prune was too aggressive.

- [ ] **Step 7: Commit**

```bash
git add tests/test_event_skill_discovery.py tests/test_postrun_context_builder.py tests/test_token_optimization.py tests/test_loop_post_run.py
git commit -m "test: drop tests that depend on src.skills.discovery

Prep step for removing the non-combat skill discovery pipeline.
Drops:
- tests/test_event_skill_discovery.py (entire file)
- test_build_discovery_prompt_reuses_full_run_digest_without_deduping
- _parse_discovered_candidates tests in TestSkillGeneration400Char
- SKILLS_DISCOVERY_* / _skill_run_count references in test_loop_post_run"
```

---

## Task 2: Strip non-combat discovery plumbing from `src/agent/loop.py`

**Goal:** Remove every import/reference/call site of `src.skills.discovery` from `loop.py`, along with the `_skill_run_count` field and `_NONCOMBAT_DISCOVERY_CATEGORIES` constant. After this task, `loop.py` must not reference `discovery.py` at all.

**Files:**
- Modify: `src/agent/loop.py`

The edits below target 9 distinct locations. Line numbers are approximate — anchor on the code shown, not the number.

- [ ] **Step 1: Remove the module-level constant (around line 111)**

Find and delete:

```python
_NONCOMBAT_DISCOVERY_CATEGORIES = frozenset({"map", "deck_building", "event", "rest"})
```

Delete any immediately-preceding/following blank lines or comments that only describe this constant.

- [ ] **Step 2: Remove the `_skill_run_count` field initialization (around line 414)**

Find and delete:

```python
self._skill_run_count: int = self._load_counter("skill_discovery")
```

Leave any other `_load_counter(...)` calls for other counters alone.

- [ ] **Step 3: Remove the discovery counter trigger block (around lines 3820–3825)**

Find and delete the entire block:

```python
# Skill discovery uses a separate persisted counter because new
# skills are mined across multiple runs rather than every game.
if self._skill_library and config.SKILLS_DISCOVERY_ENABLED and self._use_llm:
    self._skill_run_count += 1
    self._save_counter("skill_discovery", self._skill_run_count)

    if self._skill_run_count >= config.SKILLS_DISCOVERY_EVERY_N_RUNS:
        # ... (may include further lines triggering sync discovery)
```

Read the surrounding lines carefully — the `if self._skill_run_count >= …` nested block is the one that ultimately calls `_run_sync_skill_discovery`. Remove the outer `if` along with everything nested under it related to discovery counting. Leave the surrounding postrun orchestration intact.

- [ ] **Step 4: Remove the `_run_sync_skill_discovery` method (around lines 3965–4018)**

Find the whole method definition:

```python
async def _run_sync_skill_discovery(self, *, log_label: str) -> None:
    """Run post-run skill discovery synchronously via the analysis LLM."""
    ...
```

Delete from the `async def` line through to (but not including) the next method definition. Leave blank-line separator between the preceding and following methods.

- [ ] **Step 5: Remove the discovery branch in `_post_run_batch_submit` (around lines 4043–4090)**

Find the block that starts:

```python
# Skill discovery (every 3 runs)
if (
    self._skill_library
    and self._skill_run_count >= config.SKILLS_DISCOVERY_EVERY_N_RUNS
):
    try:
        from src.skills.discovery import (
            _DISCOVERY_SYSTEM,
            build_discovery_prompt,
        )
        ...
        requests.append(
            build_batch_request(f"discover-{run_id}", _DISCOVERY_SYSTEM, prompt)
        )
        tasks_meta.append({
            "type": "discovery",
            "run_id": run_id,
        })
    except Exception:
        logger.warning("Failed to build discovery batch request", exc_info=True)
```

Delete the entire `if (self._skill_library and …):` block including the `try/except` inside it. Leave the surrounding `_post_run_batch_submit` logic (request accumulation for other task types, final `submit_batch` call) intact.

- [ ] **Step 6: Remove the discovery branch in `_check_pending_batches` (around lines 4136–4164)**

Find the block:

```python
if task["type"] == "discovery" and self._skill_library:
    from src.skills.discovery import (
        _parse_discovered_candidates,
        gate_candidates,
    )
    candidates = _parse_discovered_candidates(
        raw_text,
        allowed_categories=_NONCOMBAT_DISCOVERY_CATEGORIES,
    )
    if candidates:
        ...
    self._skill_run_count = 0
    self._save_counter("skill_discovery", 0)

elif task["type"] == "distillation" and self._memory:
    ...
```

Delete the entire `if task["type"] == "discovery" …:` branch (through and including the `_save_counter("skill_discovery", 0)` line). Convert the following `elif` to `if`:

```python
if task["type"] == "distillation" and self._memory:
    ...
```

Leave the outer `for task in tasks_meta:` loop, the `try/except` shell, and the `custom_id` / `raw_text` discovery code intact.

- [ ] **Step 7: Remove the non-Anthropic sync fallback path in `_post_run_skill_update` (around lines 4566–4617)**

Find the block:

```python
# Non-Anthropic providers fall back to synchronous discovery here.
# Anthropic uses the batch path scheduled in _post_run_memory_update().
should_discover = (
    config.SKILLS_DISCOVERY_ENABLED
    and config.get_tier_provider("analysis") != "anthropic"
    and self._skill_run_count >= config.SKILLS_DISCOVERY_EVERY_N_RUNS
    and self._use_llm
)
if should_discover:
    from src.skills.discovery import discover_skills

    existing = list(self._skill_library.all_skills)
    combat_st = self._memory.combat_store if self._memory else None
    event_st = self._memory.event_store if self._memory else None
    new_skills, _evidence = await discover_skills(
        self._run_state,
        existing_skills=existing,
        combat_store=combat_st,
        event_store=event_st,
        allowed_categories=_NONCOMBAT_DISCOVERY_CATEGORIES,
    )
    self._skill_run_count = 0
    self._save_counter("skill_discovery", 0)
    if new_skills:
        # Enforcement-mode write-gate (see filter_skill_batch).
        try:
            new_skills, dropped, held = self._write_gate.filter_skill_batch(
                new_skills,
                existing_skills=existing,
                run_id=self._run_state.run_id if self._run_state else "",
            )
            ...
        except Exception:
            ...
        if new_skills:
            added = self._skill_library.add_batch(new_skills)
            if added > 0:
                logger.info("Discovered %d new skills", added)
                self._skill_library.save(skill_path)
```

Delete the entire `should_discover = …` expression through the end of `self._skill_library.save(skill_path)` inside `if new_skills:`. Preserve the preceding `self._skill_library.save(skill_path)` call that saves current skill state (unrelated to discovery) and the following `# Retirement sweep + category caps` block.

- [ ] **Step 8: Audit for any remaining references**

Run:

```bash
grep -n 'src\.skills\.discovery\|_skill_run_count\|SKILLS_DISCOVERY\|_NONCOMBAT_DISCOVERY_CATEGORIES' src/agent/loop.py
```

Expected: **zero output**. If any hits remain, go back and delete the straggler.

- [ ] **Step 9: Smoke import**

```bash
python -c "import src.agent.loop; print('ok')"
```

Expected: `ok`. Any `ImportError` / `NameError` / `AttributeError` means a removed symbol is still referenced somewhere — find it and fix before proceeding.

- [ ] **Step 10: Run the full test suite**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: failure count equal to the baseline from Task 1 Step 1. If higher, re-read the failing tests for any discovery-related assertion we missed in Task 1.

- [ ] **Step 11: Commit**

```bash
git add src/agent/loop.py
git commit -m "refactor(agent): strip non-combat skill discovery plumbing from loop.py

Removes:
- _NONCOMBAT_DISCOVERY_CATEGORIES constant
- _skill_run_count field + _save_counter('skill_discovery', ...) calls
- _run_sync_skill_discovery method
- 'discovery' branch in _post_run_batch_submit
- 'discovery' branch in _check_pending_batches
- Non-Anthropic sync fallback in _post_run_skill_update

loop.py no longer references src.skills.discovery. Combat mistake-
discovery path and _score_noncombat_skills_end_of_run untouched."
```

---

## Task 3: Remove `SKILLS_DISCOVERY_*` config flags

**Goal:** Delete the two config flags that no production code reads any more.

**Files:**
- Modify: `config.py`

- [ ] **Step 1: Verify no consumers remain**

```bash
grep -rn 'SKILLS_DISCOVERY_ENABLED\|SKILLS_DISCOVERY_EVERY_N_RUNS' src/ scripts/ tests/
```

Expected: **zero output**. If any code still reads these flags, go back to Task 2 and remove the stragglers before continuing here.

- [ ] **Step 2: Remove the two flag definitions from `config.py`**

Around line 420–422, find and delete:

```python
SKILLS_DISCOVERY_ENABLED = True                 # Discover new skills from gameplay
...
SKILLS_DISCOVERY_EVERY_N_RUNS = 1               # Discover skills every run
```

Also delete any immediately-surrounding comments that only document these flags. Leave surrounding config (other `SKILLS_*` flags, other lifecycle flags) intact.

- [ ] **Step 3: Smoke import**

```bash
python -c "import config; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: failure count equal to the baseline from Task 1 Step 1.

- [ ] **Step 5: Commit**

```bash
git add config.py
git commit -m "refactor(config): drop SKILLS_DISCOVERY_ENABLED / SKILLS_DISCOVERY_EVERY_N_RUNS

No consumers remain after loop.py plumbing removal."
```

---

## Task 4: Delete `src/skills/discovery.py`

**Goal:** Remove the now-orphaned module.

**Files:**
- Delete: `src/skills/discovery.py`

- [ ] **Step 1: Confirm the module has no remaining importers**

```bash
grep -rn 'src\.skills\.discovery\|from src.skills import discovery' src/ scripts/ tests/
```

Expected: **zero output**. Any hit means Task 1 or Task 2 missed a spot — go back and fix before deleting.

- [ ] **Step 2: Delete the module**

```bash
rm src/skills/discovery.py
```

- [ ] **Step 3: Smoke imports**

```bash
python -c "import src.agent.loop; print('loop ok')"
python -c "from src.skills.library import SkillLibrary; print('library ok')"
python -c "from src.skills.mistake_discovery import run_mistake_discovery; print('mistake ok')"
```

Expected: all three print `ok`.

- [ ] **Step 4: Run the full test suite**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: failure count equal to the baseline from Task 1 Step 1.

- [ ] **Step 5: Commit**

```bash
git add -A src/skills/discovery.py
git commit -m "refactor(skills): delete non-combat LLM skill discovery module

All callers removed in prior commits. Combat skill discovery continues
via src/skills/mistake_discovery.py. Non-combat knowledge is now
produced solely by authored seeds + run-derived guides, matching the
architectural principle 'skills = error correction, guides = memory'."
```

---

## Task 5: End-to-end validation

**Goal:** Confirm the change is complete, tests are green, a short live run completes without invoking discovery, and the orphan-reference checklist from the spec passes.

**Files:** None modified.

- [ ] **Step 1: Exhaustive grep for any orphan references**

Run:

```bash
grep -rn 'SKILLS_DISCOVERY\|_skill_run_count\|src\.skills\.discovery\|_NONCOMBAT_DISCOVERY_CATEGORIES\|_DISCOVERY_SYSTEM\|_DISCOVERY_PROMPT\|_parse_discovered_candidates\|gate_candidates\|build_discovery_prompt\|discover_skills' src/ tests/ scripts/ config.py
```

Expected: **zero output**. Any hit indicates an orphan reference that must be fixed before declaring success.

- [ ] **Step 2: Confirm surviving surface still imports cleanly**

```bash
python -c "
import src.agent.loop
from src.skills.library import SkillLibrary
from src.skills.composer import compose_skill_context
from src.skills.mistake_discovery import run_mistake_discovery
from src.skills.noncombat_scorer import compute_noncombat_score
from src.skills.lifecycle import apply_retirement_policy
print('all surviving skill-module imports ok')
"
```

Expected: `all surviving skill-module imports ok`.

- [ ] **Step 3: Full test suite — final check**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -15`

Expected: same failure count as baseline (0 or 3 pre-existing unrelated).

- [ ] **Step 4: Short live smoke run**

```bash
python -m scripts.run_agent --steps 50 --runs 1 2>&1 | tail -40
```

Expected:
- Run completes without `ImportError` / `AttributeError`.
- No log line containing `skill discovery` or `discover_skills` or `_run_sync_skill_discovery`.
- Log lines like `Skill retrieval` / `skill matched` may appear (seed skills injecting at decision time) — this is correct behavior.
- Postrun logs should include `_score_noncombat_skills_end_of_run` effects (non-combat seed confidence updates still happen) and `Retirement sweep`.

If the run fails or you see unexpected `discovery` references in logs, go back and find the remaining plumbing.

- [ ] **Step 5: Final commit — only if something was fixed during validation**

If Steps 1–4 surfaced any leftover reference that needed fixing, commit the fix:

```bash
git add -A
git commit -m "chore: final sweep for non-combat discovery orphans"
```

If every validation step passed cleanly with no code change needed, skip this step.

- [ ] **Step 6: Record done**

The postrun pipeline should now have zero non-combat LLM skill discovery. The architectural invariant is established:

- **Combat skills** come from `mistake_discovery.py` (error correction of identified mistakes).
- **Non-combat knowledge** comes from `src/skills/seeds/*.json` (authored baselines) + `guide_consolidator.py` outputs (memory of past runs).
- No LLM pass produces discovered non-combat skills any more.

---

## Self-Review Notes

Spec requirements checked against this plan:

- Delete `src/skills/discovery.py` → Task 4
- `_NONCOMBAT_DISCOVERY_CATEGORIES` removal → Task 2 Step 1
- `_skill_run_count` field + `_load_counter` → Task 2 Step 2
- All `_save_counter("skill_discovery", …)` calls → Task 2 Steps 3, 6, 7 (removed within each excised block)
- Discovery trigger counter block (3820–3825) → Task 2 Step 3
- `_run_sync_skill_discovery` method → Task 2 Step 4
- Discovery branch in `_post_run_batch_submit` → Task 2 Step 5
- Discovery branch in `_check_pending_batches` (keep distillation + try/except shell) → Task 2 Step 6
- Non-Anthropic sync fallback (4566–4617) → Task 2 Step 7
- `SKILLS_DISCOVERY_ENABLED` / `SKILLS_DISCOVERY_EVERY_N_RUNS` removal → Task 3
- `tests/test_event_skill_discovery.py` delete → Task 1 Step 2
- `tests/test_postrun_context_builder.py` prune → Task 1 Step 3
- `tests/test_token_optimization.py` prune → Task 1 Step 4
- `tests/test_loop_post_run.py` prune → Task 1 Step 5

Invariants validated at end:
- Seed loading and retrieval → Task 5 Step 2 + Step 4 observation
- Combat discovery intact → Task 5 Step 2 imports `run_mistake_discovery`
- `_score_noncombat_skills_end_of_run` still runs → Task 5 Step 4 log observation
- Retirement sweep still runs → Task 5 Step 4 log observation

Risks from spec mitigated:
- Control-flow excisions across 4 sites → Task 2 split into 4 focused steps (3, 5, 6, 7), each with its own smoke check (Step 9 import, Step 10 pytest)
- Batch result handler must keep outer loop alive → Task 2 Step 6 explicitly preserves the shell and converts `elif` to `if`
- Test files partially deleted → Task 1 steps target specific tests, not whole files, with post-edit grep verification
- Counter field referenced in 9+ places → Task 2 Step 8 final grep catches any miss
