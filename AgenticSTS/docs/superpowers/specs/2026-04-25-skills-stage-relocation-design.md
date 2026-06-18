# Skills Stage Relocation: Move mistake_discovery into Its Own Stage

**Date:** 2026-04-25
**Status:** Design — pending implementation plan
**Depends on:** `2026-04-25-core-engine-merge-to-turn2-design.md` (#1 must land first; the stage diagrams in §3.1 assume the `core_engine` stage has already been deleted).
**Related:**
- `docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md` (the discovery pipeline being relocated)
- `docs/superpowers/specs/2026-04-20-write-gate-reap-and-skill-merge-design.md` (the write-gate flush this spec leaves in `finally`)
- `src/agent/loop.py:3898` `_post_run_memory_update` (loses mistake_discovery)
- `src/agent/loop.py:4484` `_post_run_skill_update` (gains mistake_discovery + non-combat scoring)

## 1. Problem

The postrun stage names lie about what each stage does:

- `memory` stage actually drives **two** very different LLM pipelines: deterministic HCM extraction + Turn 1/2 trace analysis (genuinely "memory work"), **and** `mistake_discovery` (genuinely "skill work"). The latter only lives in the memory stage because it shares the consolidation cadence (`memory.should_consolidate`).
- `skills` stage today is housekeeping only — `save`, retirement sweeps, category caps, `update_skill_usage_from_run`, `apply_retirement_policy`. No skill is **discovered** in the skills stage.
- Non-combat skill `record_outcome` happens at the top of `_safe_post_run` (loop.py:2818-2835), unrelated to either stage method.

Result: when looking at the monitor or stage logs, "skills done" tells you nothing useful about whether discovery ran. The actual production of new skills is silently bundled into a stage labeled "memory done."

## 2. Scope

**In scope:**
- Move `run_mistake_discovery` invocation from `_post_run_memory_update` (loop.py:3950-4003) into `_post_run_skill_update` (loop.py:4484).
- Move non-combat `record_outcome` from the top of `_safe_post_run` (loop.py:2818-2835) into `_post_run_skill_update`.
- Keep cadence gating on `self._memory.should_consolidate` — read it from the skills stage instead of branching inside the memory stage. Functional behavior preserved (same N-run cadence, same gating predicates).
- **Bundled behavior improvement (explicit scope creep):** decouple `mistake_discovery` from `consolidate_guides` failure mode. Today they share an `if`-block, so a `consolidate_guides` exception silently kills `mistake_discovery` for that cycle. After this spec, the snapshot flag (`_postrun_consolidation_active`) is set BEFORE `consolidate_guides` runs, so `mistake_discovery` proceeds even if consolidation crashes. Net: more robust, slightly different failure surface. See §7 risks.
- Update the artifact log entry kind (`stage="skills"` instead of the current implicit `stage="skills"`-via-skill-discovery — they already match in the artifact emit, but the calling stage now matches too).

**Out of scope:**
- Decoupling the discovery cadence from `consolidation_count`. Deferred (option II / III in the brainstorm).
- Moving `consolidate_guides`. It stays in the memory stage — guides are memory-domain artifacts, not skill artifacts.
- Moving `_flush_write_gate_judge` out of the postrun `finally` block. It must stay there because it drains both the skills-stage write_gate queue **and** any deferred candidates evolution produces afterwards.
- Touching `mistake_discovery.py` itself. The module is already self-contained; this is purely a call-site relocation.
- Changing the order of `consolidate_guides` relative to `mistake_discovery`. Today `consolidate_guides` runs first (so the critic prompt sees the freshest guides). After relocation, that order is preserved across two stage methods rather than within one.

## 3. Architecture

### 3.1 Stage layout

Before (post-#1, pre-#2):
```
_safe_post_run:
  L2818-2835  record_outcome(non-combat skills)            ← will move
  memory stage:
    HCM extraction
    Turn 1 / Turn 2  (Turn 2 absorbs core_engine writes per #1)
    consolidate_guides       (every N runs)
    mistake_discovery        (every N runs)                ← will move
    save_all
  skills stage:
    score_noncombat_skills_end_of_run
    save
    retirement sweep + category cap
    update_skill_usage_from_run
    apply_retirement_policy
    re-save
  evolution stage
  finally:
    _flush_write_gate_judge      (drains BOTH stages' deferred candidates)
    merge_queue.drain
```

After:
```
_safe_post_run:
  memory stage:
    HCM extraction
    Turn 1 / Turn 2  (Turn 2 absorbs core_engine writes per #1)
    consolidate_guides           (every N runs)
    save_all
  skills stage:
    record_outcome(non-combat)               ← moved from _safe_post_run top
    score_noncombat_skills_end_of_run
    mistake_discovery            (every N runs, gate via memory.should_consolidate)  ← moved
    save                          (after discovery so new skills land)
    retirement sweep + category cap
    update_skill_usage_from_run
    apply_retirement_policy
    re-save
  evolution stage
  finally:
    _flush_write_gate_judge
    merge_queue.drain
```

### 3.2 Cadence gate (Option I from brainstorm)

Today's flow has an implicit read-after-reset bug if we naively split it:

```python
# _post_run_memory_update today:
self._memory.increment_consolidation_count()
if self._memory.should_consolidate:
    consolidate_guides(...)
    if mistake_discovery_enabled:
        mistake_discovery(...)              # inside the if-block
    self._memory.reset_consolidation_count()  # reset at end
```

If we move just the `mistake_discovery(...)` call to the skills stage and leave the reset where it is, the skills stage reads `should_consolidate` AFTER it has been reset to False — discovery never runs.

**Locked design**: snapshot the consolidation decision into a new instance flag at memory-stage entry; reset the counter from the postrun `finally` block guarded by the snapshot.

```python
# memory stage (top of _post_run_memory_update):
self._memory.increment_consolidation_count()
self._postrun_consolidation_active = self._memory.should_consolidate
# (snapshot is set BEFORE consolidate_guides; survives consolidate_guides exceptions —
#  see §3.4 / §7 for the failure-isolation reasoning)

# memory stage (body):
if self._postrun_consolidation_active:
    consolidate_guides(...)
# do NOT reset here

# skills stage (top of _post_run_skill_update):
if self._postrun_consolidation_active and self._skill_library and mistake_enabled:
    await run_mistake_discovery(...)

# postrun `finally` block (after _flush_write_gate_judge, before merge_queue.drain):
if getattr(self, "_postrun_consolidation_active", False):
    self._memory.reset_consolidation_count()
self._postrun_consolidation_active = False
```

The reset lives in `finally` so it fires even when:
- Skills stage is skipped (`self._skill_library is None`).
- Skills stage raises mid-discovery.
- Evolution stage raises (orthogonal but the reset must not depend on its outcome).

Without the `finally`-anchored reset, an exception in skills could leave `consolidation_count` un-reset, double-firing consolidation on the next run. The `finally` location is the ONLY one safe against all three skip paths.

`self._postrun_consolidation_active` is initialized to `False` in `__init__` and cleared at the end of every `_safe_post_run` finally block (whether or not it was set). This prevents stale state across runs.

### 3.3 Files affected

**Modified:**
- `src/agent/loop.py`:
  - `_safe_post_run`: delete the L2818-2835 non-combat record_outcome block.
  - `_post_run_memory_update`: delete the `if self._skill_library and mistake_discovery_enabled:` block (L3950-4003); change the consolidation flow to set `self._postrun_consolidation_active` and **not** reset the counter inline.
  - `_post_run_skill_update`: prepend non-combat `record_outcome`; insert mistake_discovery call gated on `self._postrun_consolidation_active`; reset `consolidation_count` at the end of this stage when active was True.
  - The artifact log emit (currently in memory stage with `stage="skills"`) moves into the skills stage call site.

**Untouched:**
- `src/skills/mistake_discovery.py`: no changes.
- `src/memory/memory_manager.py`: `should_consolidate` / `reset_consolidation_count` semantics unchanged; only the call site moves.
- `_flush_write_gate_judge`: stays in postrun `finally`. Must drain BOTH skills stage (mistake_discovery candidates) AND evolution stage (write_skill candidates).

### 3.4 Failure isolation

Each stage already has its own try/except wrapper in `_safe_post_run`. After relocation, the failure matrix changes as follows:

| Failure point | Today's behavior | Behavior after this spec |
|---|---|---|
| `consolidate_guides` raises | `mistake_discovery` is skipped; reset never happens; next run double-fires | `mistake_discovery` still runs (snapshot taken before consolidate); reset happens in `finally` |
| `mistake_discovery` raises | `consolidate_guides` already done; reset happens at end of memory stage | `consolidate_guides` already done; reset happens in `finally` |
| skills stage entirely skipped (no skill_library) | Memory stage still resets at end | `finally` resets via snapshot |
| evolution stage raises | `_flush_write_gate_judge` still runs in `finally` | Same; plus reset still runs |

The first row is the bundled behavior improvement called out in §2 — it is the only intended-different case. The remaining rows preserve today's effective behavior under stricter exception isolation.

## 4. Config

No new env vars. Existing gates behave unchanged:
- `STS2_POSTRUN_ENABLED`
- `MISTAKE_DISCOVERY_ENABLED`
- `STS2_WRITE_GATE_REAP_ENABLED` (for write-gate reap of deferred candidates)
- The implicit cadence threshold inside `MemoryManager.should_consolidate` (whatever its current value is — unchanged).

## 5. Observability

Stage logs:
- `POSTRUN STAGE memory start / done` — no longer includes mistake_discovery work in its timing.
- `POSTRUN STAGE skills start / done` — now includes mistake_discovery time on consolidation cycles. Will be visibly slower on those runs (good — it makes the cadence visible).

Artifact logs (`log_postrun_artifact`):
- `stage="skills"` artifacts produced by mistake_discovery still use `stage="skills"`, but now correctly emit during the skills stage rather than the memory stage. The monitor's grouping-by-stage display becomes truthful.

## 6. Testing strategy

This is a behavior-preserving relocation. Minimal new tests; mostly regression coverage.

**Unit tests** (no new test file):
- The existing `tests/test_mistake_discovery.py` and `tests/test_skill_lifecycle.py` continue to drive the same code paths. Confirm they pass after relocation.
- Add one new test in `tests/test_postrun_pipeline.py` (or wherever stage-orchestration tests live, create if absent):
  - Fake memory + skill_library; cadence-due cycle. Assert that `mistake_discovery` is called from the skills stage path, not from memory stage path. (Spy on the function.)
  - Cadence-not-due cycle. Assert no discovery call.
  - Memory-stage exception path: assert `_postrun_consolidation_active` is set before the exception, so skills stage still gets to attempt discovery.

**Integration test** (light):
- Run a full mocked postrun cycle. Inspect the order: memory stage emits its events, then skills stage emits non-combat + score + discovery + lifecycle events, then evolution. No interleaving.

No regression / E2E tests required.

## 7. Risks

- **Cadence reset timing.** The biggest correctness risk is double-firing consolidation if the reset is missed. Mitigation: per §3.2, the reset lives in the postrun `finally` block guarded by `_postrun_consolidation_active`, so it fires across every skip path (no skill_library / skills exception / evolution exception).
- **Bundled behavior change — `mistake_discovery` decoupled from `consolidate_guides` failure.** Today an exception in `consolidate_guides` silently swallows `mistake_discovery` for that cycle. After this spec, `mistake_discovery` runs even if consolidation crashed (the snapshot was taken first). Net: more skill discoveries land per N runs in the failure mode. Acceptable because: (a) consolidator crashes are rare, (b) when they do happen we'd rather still try discovery than lose a cadence cycle, (c) the snapshot is set BEFORE any I/O that could throw, so semantics are predictable. Risk surface: if a future change inside `consolidate_guides` mutates state that `mistake_discovery` reads, a half-consolidated state could feed bad input to discovery. Mitigation: discovery reads only `combat_store`, which `consolidate_guides` does not write — verified by grep at spec-write time.
- **Read-after-reset regressions.** Future code that reads `should_consolidate` outside these two stages would now race against the `finally`-block reset. Mitigation: comment in `MemoryManager` noting that `consolidation_count` is single-consumer (the memory→skills postrun pipeline) and other readers must use the snapshot flag.
- **Monitor expectation churn.** Frontend stage table rows shift: skills-stage runtime grows on cadence cycles, memory-stage runtime shrinks on the same cycles. No data loss, but timing graphs will show a step change. Mitigation: mention in commit message; no UI change required.

## 8. Non-goals (explicit)

- Decoupling skill discovery cadence from memory consolidation cadence. Logical refactor for a later spec.
- Moving non-combat skill discovery into skills stage — it was already removed from the codebase (2026-04-23). Only `record_outcome` for non-combat skills moves; the discovery half does not exist anymore.
- Moving `consolidate_guides` into the skills stage. Guides are memory artifacts, not skill artifacts; ownership stays with memory.
- Moving `_flush_write_gate_judge` into the skills stage. Already explained: it must run after evolution to drain both stages' deferred candidates.
- Renaming the `consolidation_count` field. Cross-store rename is out of scope.
