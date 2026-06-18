# Strategy Rules Removal Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the `StrategyRule` / `rule_distiller` / `RuleStore` subsystem. Preserve seeds, guides, mistake-driven combat skill discovery, and the guide consolidation counter.

**Architecture:** Rules lived in their own model + store + distiller + prompt, with 7 injection sites (5 retriever + 1 evolution + the `WorkingContext.rule_hints` field). Removal is ordered to keep tests green at every commit boundary: prune tests first, then retriever injection, then the evolution-engine injection, then the `WorkingContext.rule_hints` field, then the loop trigger + memory_manager plumbing, then the model + store + prompt + distiller modules, then the config flags, then end-to-end validation.

**Tech Stack:** Python 3.14, pytest.

**Spec:** [docs/superpowers/specs/2026-04-23-rules-removal-design.md](../specs/2026-04-23-rules-removal-design.md)

---

## File Structure

**Deleted files:**
- `src/memory/rule_distiller.py`
- `src/memory/rule_store.py`
- `src/brain/prompts/distill.py`
- `tests/test_rule_gating_and_past_experience.py`

**Modified files:**
- `src/memory/models_v2.py` — `StrategyRule` class gone; `WorkingContext.rule_hints` field gone
- `src/memory/memory_manager.py` — `self.rules`, `record_rules`, distillation counter helpers, `should_distill`, `"runs_since_distill"` stat, associated imports gone
- `src/memory/retriever.py` — `rule_store` kwarg, 5 injection blocks, `rule_hints` accumulator, imports gone
- `src/brain/evolution_engine.py` — rule-injection block around line 2523 gone
- `src/agent/loop.py` — distillation trigger + `"distillation"` batch branch gone
- `src/memory/__init__.py` — `StrategyRule` / `RuleStore` re-exports gone
- `config.py` — `RULE_CAPACITY`, `DISTILL_EVERY_N_RUNS` gone
- `tests/test_build_memory.py`, `tests/test_card_memory.py`, `tests/test_prompt_cleanup.py`, `tests/test_combat_delta.py`, `tests/test_evolution_engine.py` — StrategyRule / rule_hints / rule_store references pruned

**Untouched (verification targets):**
- `src/skills/seeds/*.json`
- `src/memory/guide_store.py`, `src/memory/guide_consolidator.py`
- `src/memory/combat_store.py`, `src/memory/route_store.py`, `src/memory/card_build_store.py`, `src/memory/card_memory_store.py`, `src/memory/event_store.py`
- `src/skills/mistake_discovery.py`, `src/skills/library.py`, `src/skills/composer.py`
- `CONSOLIDATION_EVERY_N_RUNS` counter and cadence
- `_score_noncombat_skills_end_of_run`, retirement sweep

---

## Task 1: Prune tests that depend on the rules subsystem

**Goal:** Drop every test reference to `StrategyRule`, `RuleStore`, `rule_store`, `rule_hints`, `rule_distiller`, `record_rules`, `distill_rules`, `should_distill`, `RULE_CAPACITY`, `DISTILL_EVERY_N_RUNS`. Subsequent tasks can then delete the production code without cascading false failures.

**Files:**
- Delete: `tests/test_rule_gating_and_past_experience.py`
- Modify: `tests/test_build_memory.py`
- Modify: `tests/test_card_memory.py`
- Modify: `tests/test_prompt_cleanup.py`
- Modify: `tests/test_combat_delta.py`
- Modify: `tests/test_evolution_engine.py`

- [ ] **Step 1: Establish baseline**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -5`

Write down the exact `X passed, Y failed` numbers. Every step below must keep `Y` equal to that baseline (3 pre-existing unrelated failures expected). Passes will drop as tests are removed; that's expected.

- [ ] **Step 2: Delete `tests/test_rule_gating_and_past_experience.py`**

```bash
rm tests/test_rule_gating_and_past_experience.py
```

- [ ] **Step 3: Audit all other test files for rule references**

Run:

```bash
grep -rln 'StrategyRule\|RuleStore\|rule_store\|rule_hints\|rule_distiller\|record_rules\|distill_rules\|should_distill\|RULE_CAPACITY\|DISTILL_EVERY_N_RUNS' tests/
```

Walk each hit. For each test:
- If the test's primary subject is rules behavior → delete the whole test.
- If the test happens to pass `rule_store=...` / `rule_hints=...` as kwargs or touches `MemoryManager.record_rules` merely as setup → drop the obsolete line but keep the test.
- If a test constructs `WorkingContext(rule_hints=(...))` explicitly → drop the kwarg.
- If a test asserts specific rule_hints content → delete the assertion; if the whole test was about that assertion, delete the test.

- [ ] **Step 4: Verify zero rule references remain in tests**

Run: `grep -rln 'StrategyRule\|RuleStore\|rule_store\|rule_hints\|rule_distiller\|record_rules\|distill_rules\|should_distill\|RULE_CAPACITY\|DISTILL_EVERY_N_RUNS' tests/`

Expected: no output.

- [ ] **Step 5: Run full test suite**

Run: `python -m pytest tests/ --no-header -q 2>&1 | tail -5`

Expected: failure count equal to the baseline from Step 1. Passes will have dropped by roughly the number of deleted tests.

- [ ] **Step 6: Commit**

```bash
git add tests/
git commit -m "test: drop tests that depend on StrategyRule / rule_store subsystem

Prep step for removing the strategy rules subsystem. Drops:
- tests/test_rule_gating_and_past_experience.py (entire file)
- rule-specific assertions and kwargs across test_build_memory,
  test_card_memory, test_prompt_cleanup, test_combat_delta,
  test_evolution_engine"
```

---

## Task 2: Strip rule injection from `src/memory/retriever.py`

**Goal:** Remove the `rule_store` parameter, the `rule_hints` accumulator, all 5 `rule_store.query(...)` / rule-injection blocks, and the `rule_hints=...` kwarg on the final `WorkingContext` construction. After this task, `retriever.py` has zero references to rules.

**Files:**
- Modify: `src/memory/retriever.py`

- [ ] **Step 1: Remove the `RuleStore` import**

Find and delete:

```python
from src.memory.rule_store import RuleStore
```

- [ ] **Step 2: Remove the `rule_store` parameter from `retrieve_working_context`**

Around line 424 the signature includes `rule_store: RuleStore` as a parameter. Delete that parameter from the signature. Also delete any docstring line that documents it.

- [ ] **Step 3: Remove the `rule_hints` accumulator initialization**

Around line 455, find and delete:

```python
rule_hints: list[str] = []
```

- [ ] **Step 4: Remove each of the 5 rule-injection blocks**

At lines ~554, ~588, ~647, ~707, ~736 (not 728 — the pattern appears 5x; the approximate line numbers from the spec are anchors, not gospel), each block follows this pattern:

```python
rules = rule_store.query(
    ...
)
for r in rules:
    rule_hints.append(f"Rule ({r.confidence:.0%}): {r.rule_text}")
```

Delete each block in full, including the `rule_store.query(...)` call and the `for r in rules` loop. Be careful not to delete any surrounding code that handles combat/route/deck/event/card hints — those stay.

- [ ] **Step 5: Remove `rule_hints=rule_hints` from the `WorkingContext(...)` construction**

At the bottom of `retrieve_working_context` there is a `return WorkingContext(...)` call. Remove the `rule_hints=rule_hints` (or `rule_hints=tuple(rule_hints)`) kwarg from that call.

- [ ] **Step 6: Audit callers of `retrieve_working_context`**

Run:

```bash
grep -rn 'retrieve_working_context' src/ tests/
```

For each caller, check whether it passes `rule_store=...`. If yes, remove that kwarg in the same commit. Common callers are in `src/agent/loop.py` (decision-time retrieval wrapper) — verify and update.

- [ ] **Step 7: Audit for remaining rule references**

Run:

```bash
grep -n 'RuleStore\|rule_store\|rule_hints' src/memory/retriever.py
```

Expected: zero output.

- [ ] **Step 8: Smoke import + test**

```bash
python -c "from src.memory.retriever import retrieve_working_context; print('ok')"
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: `ok` + failure count matching Task 1 baseline. If retrieve_working_context callers in tests still pass `rule_store=...`, tests will fail here — go back to Step 6 and audit tests too.

- [ ] **Step 9: Commit**

```bash
git add src/memory/retriever.py src/agent/loop.py
git commit -m "refactor(retriever): remove rule_store param + rule_hints injection

Strips the 5 rule_store.query(...) injection sites, the rule_hints
accumulator, and the rule_store kwarg from retrieve_working_context.
All WorkingContext consumers still receive combat/route/deck/event/
card/skill hints; only rule_hints is dropped."
```

---

## Task 3: Strip rule injection from `src/brain/evolution_engine.py`

**Goal:** Remove the rule injection block that assembles `all_rules` into the evolution prompt.

**Files:**
- Modify: `src/brain/evolution_engine.py`

- [ ] **Step 1: Find the rule injection block**

Start at `src/brain/evolution_engine.py:2523`:

```python
rule_store = getattr(memory_manager, "rule_store", None)
if rule_store is None or not hasattr(rule_store, "get_all"):
    ...
all_rules = sorted(rule_store.get_all(), key=lambda rule: getattr(rule, "confidence", 0.0), reverse=True)
```

Read the full block — it spans from `rule_store = getattr(...)` through wherever the `all_rules` list is consumed in the surrounding prompt assembly. Include any `for rule in all_rules: parts.append(...)` loop that follows. Delete the entire block.

- [ ] **Step 2: Audit for any remaining rule references in the file**

```bash
grep -n 'rule_store\|all_rules\|rule_text\|StrategyRule' src/brain/evolution_engine.py
```

Expected: zero output.

- [ ] **Step 3: Smoke import**

```bash
python -c "import src.brain.evolution_engine; print('ok')"
```

Expected: `ok`.

- [ ] **Step 4: Run tests**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: failure count matching baseline.

- [ ] **Step 5: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "refactor(evolution): drop rule_store injection from evolution prompt

The evolution engine still reads combat guides, deck guides, event
guides, skills, and the strategic thread. Only the StrategyRule
injection block is removed."
```

---

## Task 4: Remove `WorkingContext.rule_hints` + `StrategyRule` from the model layer

**Goal:** Drop the `rule_hints` field from `WorkingContext` and the entire `StrategyRule` class from `src/memory/models_v2.py`.

**Files:**
- Modify: `src/memory/models_v2.py`

- [ ] **Step 1: Remove `rule_hints` from `WorkingContext`**

At `src/memory/models_v2.py:1328`:

```python
rule_hints: tuple[str, ...] = ()
```

Delete that field. Then walk lines 1347, 1360, 1374 (per the spec) — these are `WorkingContext` methods that reference `self.rule_hints` for stats / serialization / iteration. Remove every reference to `rule_hints` inside the class body.

- [ ] **Step 2: Delete the `StrategyRule` class**

Around `src/memory/models_v2.py:1386` the `StrategyRule` dataclass begins. Delete the whole class (model fields + `to_dict` + `from_dict` + `with_verification` + `with_violation`) through the end of the class definition (next blank-line + class/function boundary).

- [ ] **Step 3: Audit for remaining references in the file**

```bash
grep -n 'StrategyRule\|rule_hints' src/memory/models_v2.py
```

Expected: zero output.

- [ ] **Step 4: Smoke import**

```bash
python -c "from src.memory.models_v2 import WorkingContext; ctx = WorkingContext(); print('ok', not hasattr(ctx, 'rule_hints'))"
```

Expected: `ok True`.

- [ ] **Step 5: Run tests**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: failure count matching baseline. Any new failure pointing at `rule_hints` or `StrategyRule` means Task 1's test sweep missed a reference — go back to Task 1.

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py
git commit -m "refactor(models): delete StrategyRule + WorkingContext.rule_hints

The rule_hints field is no longer populated (Task 2 retriever cleanup)
and the StrategyRule model has no persisted consumers after Task 3
(evolution engine) and Task 2 (retriever). The class and the field
are now dead — remove from the model layer."
```

---

## Task 5: Remove distillation plumbing from `MemoryManager` and `loop.py`

**Goal:** Drop the `self.rules = RuleStore.load(...)` initializer, the distillation counter (`_run_count`, `increment_run_count`, `reset_run_count`, `should_distill`, `_load_counter`, `_save_counter`), `record_rules`, `"runs_since_distill"` stat, all related imports from `MemoryManager`, and the distillation trigger block + batch-result branch from `loop.py`. Preserve the consolidation counter.

**Files:**
- Modify: `src/memory/memory_manager.py`
- Modify: `src/memory/__init__.py`
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Edit `src/memory/memory_manager.py`**

Remove:

- Imports: `from src.memory.models_v2 import StrategyRule`, `from src.memory.rule_store import RuleStore` (lines 15-16).
- `self._rule_path = base / "rules.json"` (line 31).
- `self.rules = RuleStore.load(self._rule_path, capacity=config.RULE_CAPACITY)` (line 34-37).
- `self._run_count = self._load_counter(base)` (line 39).
- Any `rule_store=self.rules` wiring passed to retriever / consumer setup (line 172 area).
- Methods `_load_counter`, `_save_counter`, `increment_run_count`, `reset_run_count`, `should_distill` (approximately lines 220-254). Preserve `_load_consolidation_counter`, `_save_consolidation_counter`, `increment_consolidation_count`, `reset_consolidation_count`, `should_consolidate` — those are for guide consolidation.
- `record_rules` method (line 214).
- `"runs_since_distill": self._run_count` key from the `stats()` dict (line 318).
- Update the loader log line (lines 45-49) to drop "%d rules (%d active)" and just log HCM V2 load stats.

Audit:

```bash
grep -n 'StrategyRule\|RuleStore\|rule_store\|record_rules\|should_distill\|_run_count\|_load_counter\|_save_counter\|increment_run_count\|reset_run_count\|RULE_CAPACITY\|runs_since_distill' src/memory/memory_manager.py
```

Expected: zero output.

- [ ] **Step 2: Edit `src/memory/__init__.py`**

Remove any `StrategyRule` or `RuleStore` re-exports. Grep:

```bash
grep -n 'StrategyRule\|RuleStore\|rule_store\|rule_distiller' src/memory/__init__.py
```

Expected: zero output after edits.

- [ ] **Step 3: Edit `src/agent/loop.py`: delete the distillation trigger in `_post_run_memory_update`**

At `src/agent/loop.py` around lines 3814–3842 there is:

```python
self._memory.increment_run_count()

# Rule distillation (every N runs, uses V2 domain data)
if self._memory.should_distill and self._use_llm:
    try:
        from src.memory.rule_distiller import distill_rules
        new_rules = await distill_rules(
            self._memory.card_build_store,
            self._memory.combat_store,
        )
        if new_rules:
            self._memory.record_rules(new_rules)
            if self._session_logger is not None and hasattr(
                self._session_logger, "log_postrun_artifact",
            ):
                try:
                    self._session_logger.log_postrun_artifact(
                        stage="distill",
                        kind="rule",
                        action="append",
                        summary=f"{len(new_rules)} new rule(s) distilled",
                        after=list(new_rules),
                        source="rule_distiller",
                    )
                except Exception:
                    pass
        self._memory.reset_run_count()
    except Exception:
        logger.warning("Rule distillation failed", exc_info=True)
```

Delete the whole block from `self._memory.increment_run_count()` through the `except` clause. The `self._memory.increment_consolidation_count()` call that follows belongs to a different counter — keep it.

- [ ] **Step 4: Edit `src/agent/loop.py`: delete the `"distillation"` batch-result branch in `_check_pending_batches`**

At `src/agent/loop.py` around lines 3977–3984 there is:

```python
if task["type"] == "distillation" and self._memory:
    # Legacy batch results may still arrive
    from src.memory.rule_distiller import _parse_rules
    rules = _parse_rules(raw_text)
    if rules:
        self._memory.record_rules(rules)
        logger.info("Batch: %d rules distilled", len(rules))
    self._memory.reset_run_count()
```

Delete the entire `if task["type"] == "distillation" …:` branch. The outer `for task in tasks_meta` loop, `try/except` shell, `custom_id` / `raw_text` setup stay.

After this deletion `_check_pending_batches` will have an empty task-dispatch body inside the try. That is intentional — the method is kept so legacy batch state files still get drained from disk by `_load_pending` / `_save_pending` inside `batch.check_completed()`. Add a short comment explaining this:

```python
# No active batch task types after the 2026-04-23 distillation
# removal. check_completed still runs so legacy batch state files
# get cleaned up; no branch handles the results.
```

- [ ] **Step 5: Audit for remaining references across the three files**

```bash
grep -rn 'StrategyRule\|RuleStore\|rule_store\|record_rules\|should_distill\|increment_run_count\|reset_run_count\|rule_distiller\|distill_rules\|runs_since_distill' src/agent/loop.py src/memory/memory_manager.py src/memory/__init__.py
```

Expected: zero output.

- [ ] **Step 6: Smoke imports**

```bash
python -c "import src.agent.loop; print('loop ok')"
python -c "from src.memory.memory_manager import MemoryManager; print('mm ok')"
python -c "import src.memory; print('pkg ok')"
```

Expected: all three print `ok`.

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: failure count matching baseline.

- [ ] **Step 8: Commit**

```bash
git add src/agent/loop.py src/memory/memory_manager.py src/memory/__init__.py
git commit -m "refactor(memory): delete rule distillation plumbing

Removes:
- MemoryManager rule store init + record_rules + distill counter
  (_run_count / increment_run_count / reset_run_count / should_distill
  / _load_counter / _save_counter / runs_since_distill stat)
- Rule distillation trigger block in _post_run_memory_update
- 'distillation' batch-result branch in _check_pending_batches
- StrategyRule / RuleStore re-exports from src/memory/__init__.py

Preserves:
- MemoryManager consolidation counter (drives guide consolidation)
- check_completed() in _check_pending_batches so legacy batch state
  files still drain from disk"
```

---

## Task 6: Delete the orphaned modules + config flags

**Goal:** With every consumer gone, delete the three orphan production modules and their config flags.

**Files:**
- Delete: `src/memory/rule_distiller.py`
- Delete: `src/memory/rule_store.py`
- Delete: `src/brain/prompts/distill.py`
- Modify: `config.py`

- [ ] **Step 1: Confirm zero remaining importers**

```bash
grep -rn 'src\.memory\.rule_distiller\|src\.memory\.rule_store\|src\.brain\.prompts\.distill\|from src.memory import rule_distiller\|from src.memory import rule_store' src/ scripts/ tests/
```

Expected: zero output. Any hit means Task 1-5 missed a reference — fix before deleting.

- [ ] **Step 2: Delete the three modules**

```bash
rm src/memory/rule_distiller.py
rm src/memory/rule_store.py
rm src/brain/prompts/distill.py
```

- [ ] **Step 3: Remove config flags from `config.py`**

Find and delete:

- `RULE_CAPACITY = ...`
- `DISTILL_EVERY_N_RUNS = ...`

Also delete any comments that solely documented these flags.

- [ ] **Step 4: Audit**

```bash
grep -rn 'RULE_CAPACITY\|DISTILL_EVERY_N_RUNS' src/ scripts/ tests/ config.py
```

Expected: zero output.

- [ ] **Step 5: Smoke imports**

```bash
python -c "import src.agent.loop; print('loop ok')"
python -c "from src.memory.memory_manager import MemoryManager; print('mm ok')"
python -c "from src.memory.retriever import retrieve_working_context; print('retr ok')"
python -c "import src.brain.evolution_engine; print('evo ok')"
```

Expected: all four print `ok`.

- [ ] **Step 6: Run tests**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: failure count matching baseline.

- [ ] **Step 7: Commit**

```bash
git add -A src/memory/rule_distiller.py src/memory/rule_store.py src/brain/prompts/distill.py config.py
git commit -m "refactor(memory): delete rule_distiller / rule_store / distill prompt

Final removal of the strategy rules subsystem. All callers were
removed in Tasks 1-5; these modules and their config flags are now
orphans. Non-combat knowledge is now produced solely by authored
seed skills + run-derived guides, matching the architectural
principle 'skills = error correction, guides = memory'."
```

---

## Task 7: End-to-end validation

**Goal:** Confirm the removal is complete, tests green, a short live run completes without rule-distillation attempts, and the orphan-reference checklist from the spec passes.

**Files:** None modified unless validation surfaces a miss.

- [ ] **Step 1: Exhaustive orphan-reference grep**

```bash
grep -rn 'StrategyRule\|RuleStore\|rule_store\|rule_hints\|rule_distiller\|record_rules\|distill_rules\|should_distill\|RULE_CAPACITY\|DISTILL_EVERY_N_RUNS\|runs_since_distill' src/ tests/ scripts/ config.py
```

Expected: zero output. Hits in `docs/` are OK (historical specs/plans).

- [ ] **Step 2: Surviving surface imports**

```bash
python -c "
import src.agent.loop
from src.memory.memory_manager import MemoryManager
from src.memory.retriever import retrieve_working_context
from src.memory.models_v2 import WorkingContext
from src.memory.guide_store import GuideStore
from src.skills.library import SkillLibrary
from src.skills.mistake_discovery import run_mistake_discovery
print('all surviving surface imports ok')
"
```

Expected: `all surviving surface imports ok`.

- [ ] **Step 3: Full test suite**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: failure count equal to baseline (3 pre-existing unrelated failures).

- [ ] **Step 4: Short live smoke run**

```bash
python -m scripts.run_agent --steps 50 --runs 1 2>&1 | tail -60
```

Expected:
- Run completes without `ImportError` / `AttributeError` / `NameError`
- **No log lines containing** `rule_distillation`, `distill_rules`, `record_rules`, `rule_store`, `should_distill`
- **Expected log lines present**:
  - Guide consolidation (`increment_consolidation_count`, `should_consolidate`)
  - Mistake-driven combat skill discovery (if any combat mistakes flagged)
  - Seed skill injection at decision time
  - Retirement sweep + category caps
  - `_score_noncombat_skills_end_of_run`

If any rule-related log line appears or the run errors with a NameError / AttributeError referencing deleted symbols, that's a bug — investigate and fix.

- [ ] **Step 5: Conditional commit**

Only if Steps 1-4 surfaced code-level issues that required fixing:

```bash
git add -A
git commit -m "chore: final sweep for rule subsystem orphans"
```

If all passed cleanly, skip this step.

- [ ] **Step 6: Record done**

The postrun pipeline now has no strategy rules. Architectural invariant:
- **Combat skills** from `mistake_discovery.py` (error correction)
- **Non-combat knowledge** from authored seeds + run-derived guides (memory)
- Neither LLM-based non-combat discovery nor LLM-distilled rules exists
- `WorkingContext` fields: combat_hints, route_hints, deck_hints, event_hints, card_hints, skill_hints — no rule_hints

---

## Self-Review Notes

Spec requirements checked against this plan:

- `src/memory/rule_distiller.py` deletion → Task 6
- `src/memory/rule_store.py` deletion → Task 6
- `src/brain/prompts/distill.py` deletion → Task 6
- `StrategyRule` class removal + `WorkingContext.rule_hints` removal → Task 4
- `MemoryManager` distillation counter + `rule_store` field + `record_rules` → Task 5 Step 1
- `src/memory/__init__.py` re-exports → Task 5 Step 2
- `src/agent/loop.py` distillation trigger → Task 5 Step 3
- `src/agent/loop.py` batch-result `"distillation"` branch → Task 5 Step 4
- `src/memory/retriever.py` rule kwarg + 5 injection blocks + `rule_hints` init + WorkingContext kwarg → Task 2
- `src/brain/evolution_engine.py:2523` injection block → Task 3
- `config.py` RULE_CAPACITY + DISTILL_EVERY_N_RUNS → Task 6 Step 3
- Tests → Task 1 + re-audited at each task's test run

Invariants validated at end:
- Seeds + retrieval + composer still work → Task 7 Step 2
- Mistake-driven combat discovery still works → Task 7 Step 2 imports
- Guide consolidation counter + cadence unchanged → Task 5 Step 1 explicitly preserves
- `_score_noncombat_skills_end_of_run` still runs → Task 7 Step 4 log observation
- `_check_pending_batches` drains legacy state → Task 5 Step 4 note

Risks from spec mitigated:
- Signature change on `retrieve_working_context` → Task 2 Step 6 audits callers in the same commit
- `WorkingContext.rule_hints` field removal → Task 1 prunes tests first, Task 4 removes model, Task 7 grep catches stragglers
- `MemoryManager` init ordering → Task 5 Step 1 explicitly preserves `_init_v2_stores(base)`
- Counter file reuse → `_load_counter` for distillation was a private MemoryManager method, no external reader; `_load_counter` for other counters (e.g. guide consolidation) is a separate method (`_load_consolidation_counter`) that stays
