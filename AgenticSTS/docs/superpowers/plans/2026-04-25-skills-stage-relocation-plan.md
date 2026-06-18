# Skills Stage Relocation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Relocate `mistake_discovery` and non-combat `record_outcome` from the memory stage / `_safe_post_run` body into `_post_run_skill_update` so postrun stage names match what each stage actually does, and replace the inline `consolidation_count` reset with a `finally`-anchored reset that survives skip paths.

**Architecture:** A new instance flag `_postrun_consolidation_active` snapshots `memory.should_consolidate` at memory-stage entry. Memory stage drops `mistake_discovery`. Skills stage gains `mistake_discovery` (gated on the snapshot) and absorbs the non-combat `record_outcome` block. The cadence reset moves to `_safe_post_run`'s `finally` block guarded by the snapshot, so it fires across every skip path.

**Tech Stack:** Python 3.12, pytest, async/await, `unittest.mock` (`AsyncMock` / `patch`). No new libraries.

**Spec:** [`docs/superpowers/specs/2026-04-25-skills-stage-relocation-design.md`](../specs/2026-04-25-skills-stage-relocation-design.md)

---

## File Map

| File | Action | Notes |
|---|---|---|
| `src/agent/loop.py` | Modify | New instance attribute; rewrite memory-stage cadence flow; rewrite skills stage to absorb `mistake_discovery` + non-combat `record_outcome`; delete record_outcome block from `_safe_post_run`; add cadence reset to `_safe_post_run` finally |
| `tests/test_loop_post_run.py` | Modify | Add 4 new orchestration tests covering cadence snapshot, skills-stage discovery dispatch, finally reset, and non-combat record_outcome relocation |

`src/skills/mistake_discovery.py` stays untouched (the function being relocated is already self-contained — only the call site moves). `src/memory/memory_manager.py` stays untouched (`should_consolidate` / `reset_consolidation_count` semantics unchanged).

**Sequencing rationale:** every commit must leave the system in a working state. Incremental order: (1) add the snapshot flag, (2) wire the safety-net reset in `finally` BEFORE removing the inline reset, (3) move `mistake_discovery` atomically (delete-from-memory + add-to-skills in one commit), (4) move non-combat `record_outcome`, (5) verify.

---

## Task 1: Initialize `_postrun_consolidation_active` Instance Attribute

**Files:**
- Modify: `src/agent/loop.py` (around L498, in `AgentLoop.__init__`)
- Test: `tests/test_loop_post_run.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loop_post_run.py`:

```python
def test_loop_init_sets_postrun_consolidation_flag_false():
    """The skills-stage cadence snapshot flag must default to False so a
    fresh AgentLoop never accidentally triggers mistake_discovery on
    its first postrun."""
    client = MagicMock()
    loop = make_loop(client)
    assert loop._postrun_consolidation_active is False
```

- [ ] **Step 2: Run test to verify it fails**

```
pytest tests/test_loop_post_run.py::test_loop_init_sets_postrun_consolidation_flag_false -v
```
Expected: FAIL with `AttributeError`.

- [ ] **Step 3: Add the instance attribute**

Edit `src/agent/loop.py`. Locate the block of instance-attribute initializers around lines 491-498 (look for `self._skill_trigger_log: list[dict[str, object]] = []` followed by `self._pending_build_mem`). Add a new line immediately AFTER `self._pending_trace_candidates: list[str] = []`:

```python
        self._postrun_consolidation_active: bool = False  # Spec #2: cadence snapshot for skills-stage mistake_discovery
```

- [ ] **Step 4: Run test to verify it passes**

```
pytest tests/test_loop_post_run.py::test_loop_init_sets_postrun_consolidation_flag_false -v
```
Expected: PASS.

- [ ] **Step 5: Commit**

```
git add src/agent/loop.py tests/test_loop_post_run.py
git commit -m "feat(loop): add _postrun_consolidation_active cadence snapshot flag"
```

---

## Task 2: Snapshot in Memory Stage + Reset in `_safe_post_run` Finally

This task introduces the snapshot capture and the safety-net reset in the `finally` block. The inline reset in the memory stage stays for now (Task 3 removes it). After this task: snapshot is captured (unused), and the finally reset is a no-op safety net (count is already reset by the inline reset). Functional behavior unchanged.

**Files:**
- Modify: `src/agent/loop.py` (memory-stage method + `_safe_post_run` finally block)
- Test: `tests/test_loop_post_run.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_loop_post_run.py`:

```python
def test_memory_stage_captures_consolidation_snapshot(monkeypatch):
    """When memory's increment pushes should_consolidate True, the
    AgentLoop captures the decision into _postrun_consolidation_active
    BEFORE invoking consolidate_guides. The snapshot must be set even
    if consolidate_guides raises."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._use_llm = False  # skip the build-analysis branch
    loop._memory = MagicMock()
    loop._memory.should_consolidate = True
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._memory.maintenance = MagicMock()
    loop._memory.save_all = MagicMock()
    loop._memory.stats = MagicMock(return_value={})
    loop._post_run_hcm_extraction = MagicMock()

    # consolidate_guides raises — snapshot must already be captured
    async def _raise(*a, **kw):
        raise RuntimeError("consolidate boom")
    monkeypatch.setattr(
        "src.memory.guide_consolidator.consolidate_guides", _raise,
    )

    asyncio.run(loop._post_run_memory_update())
    assert loop._postrun_consolidation_active is True


def test_safe_post_run_finally_resets_consolidation_when_active(monkeypatch):
    """The finally block resets _memory.consolidation_count when the
    snapshot was True, regardless of whether memory/skills/evolution
    stages succeeded. Always clears the flag for the next run."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()
    loop._post_run_memory_update = AsyncMock(
        side_effect=lambda: setattr(loop, "_postrun_consolidation_active", True),
    )
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock(
        return_value={"status": "done", "context_profile": "heavy", "context_chars": 0, "action_count": 0},
    )
    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _t: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _p: True)

    asyncio.run(loop._safe_post_run())

    loop._memory.reset_consolidation_count.assert_called_once()
    assert loop._postrun_consolidation_active is False  # cleared at end


def test_safe_post_run_finally_does_not_reset_when_inactive(monkeypatch):
    """When snapshot is False (no consolidation due), reset must NOT fire."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()
    loop._post_run_memory_update = AsyncMock()  # leaves flag at False
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock(
        return_value={"status": "done", "context_profile": "heavy", "context_chars": 0, "action_count": 0},
    )
    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _t: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _p: True)

    asyncio.run(loop._safe_post_run())

    loop._memory.reset_consolidation_count.assert_not_called()
    assert loop._postrun_consolidation_active is False
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_loop_post_run.py -k "consolidation_snapshot or finally_resets_consolidation or finally_does_not_reset" -v
```
Expected: FAIL — snapshot is not yet captured; `reset_consolidation_count` is not yet called from `_safe_post_run` finally.

- [ ] **Step 3: Add snapshot capture in `_post_run_memory_update`**

Edit `src/agent/loop.py`. Locate the block in `_post_run_memory_update`:

```python
            # Consolidate guides periodically (every N runs)
            self._memory.increment_consolidation_count()
            if self._memory.should_consolidate:
```

Replace with:

```python
            # Consolidate guides periodically (every N runs).
            # Snapshot the decision BEFORE consolidate_guides runs so that
            # an exception in consolidate_guides does not prevent the
            # skills-stage mistake_discovery from firing on this cadence
            # cycle (Spec #2 §3.4 bundled improvement).
            self._memory.increment_consolidation_count()
            self._postrun_consolidation_active = self._memory.should_consolidate
            if self._postrun_consolidation_active:
```

(Two edits: add the snapshot line; change the `if` to use the snapshot.)

- [ ] **Step 4: Add cadence reset in `_safe_post_run` finally block**

Locate the `finally:` block in `_safe_post_run` (look for `await self._flush_write_gate_judge()`). It starts around L2924 in the file.

Find the existing block:

```python
        finally:
            # Flush write-gate judge queue (observation mode — commit 2 spec
            # §4.4 / §5). One batched fast-tier LLM call covering every
            # candidate that hit the judge zone during this postrun, plus
            # any structural cross-store conflicts found in the live skill
            # library. Result is logged but not yet enforced (commit 4).
            await self._flush_write_gate_judge()
```

Insert a new block IMMEDIATELY AFTER the `await self._flush_write_gate_judge()` line, BEFORE the `# Drain any merge-queue entries...` comment. The new block:

```python
            # Consolidation cadence reset (Spec #2 §3.2). Happens here
            # rather than inside the memory stage so it survives every
            # skip path (memory-only run, skills-stage exception,
            # evolution-stage exception). Always clears the snapshot
            # flag for the next run regardless of whether reset fired.
            if (
                getattr(self, "_postrun_consolidation_active", False)
                and self._memory is not None
            ):
                try:
                    self._memory.reset_consolidation_count()
                except Exception:
                    logger.warning(
                        "Post-run consolidation_count reset failed",
                        exc_info=True,
                    )
            self._postrun_consolidation_active = False
```

- [ ] **Step 5: Run tests to verify they pass**

```
pytest tests/test_loop_post_run.py -k "consolidation_snapshot or finally_resets_consolidation or finally_does_not_reset" -v
```
Expected: 3 PASS.

Also run the full file to confirm existing tests still pass:

```
pytest tests/test_loop_post_run.py -v
```
Expected: all PASS.

- [ ] **Step 6: Commit**

```
git add src/agent/loop.py tests/test_loop_post_run.py
git commit -m "feat(loop): snapshot consolidation cadence + reset in finally block"
```

---

## Task 3: Move `mistake_discovery` from Memory Stage to Skills Stage

This task atomically (single commit) deletes the `mistake_discovery` block from `_post_run_memory_update` AND adds it to `_post_run_skill_update`. Also deletes the inline `reset_consolidation_count()` call (the finally-block reset added in Task 2 takes over).

**Files:**
- Modify: `src/agent/loop.py` (`_post_run_memory_update` + `_post_run_skill_update`)
- Test: `tests/test_loop_post_run.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_loop_post_run.py`:

```python
def _setup_skill_stage_mocks(loop, monkeypatch):
    """Bypass `_post_run_skill_update`'s lifecycle / score helpers so the
    test can focus on the discovery-dispatch decision. Returns nothing;
    mutates loop and monkeypatches lifecycle imports."""
    loop._score_noncombat_skills_end_of_run = MagicMock()
    monkeypatch.setattr(
        "src.skills.lifecycle.update_skill_usage_from_run", MagicMock(),
    )
    monkeypatch.setattr(
        "src.skills.lifecycle.apply_retirement_policy",
        MagicMock(return_value=[]),
    )


def test_skills_stage_runs_mistake_discovery_when_snapshot_true(monkeypatch):
    """When _postrun_consolidation_active is True at skills-stage entry,
    mistake_discovery is invoked from _post_run_skill_update."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = True  # snapshot pretend-set by memory stage
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = set()
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    loop._session_logger.log_path = None

    _setup_skill_stage_mocks(loop, monkeypatch)
    discovery_mock = AsyncMock(return_value={
        "candidates": 0, "ab_passed": 0, "persisted": 0,
    })
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )
    monkeypatch.setattr(loop_module.config, "MISTAKE_DISCOVERY_ENABLED", True)

    asyncio.run(loop._post_run_skill_update())

    discovery_mock.assert_awaited_once()


def test_skills_stage_skips_mistake_discovery_when_snapshot_false(monkeypatch):
    """When the cadence snapshot is False, mistake_discovery must NOT
    fire from the skills stage."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = False  # not a cadence cycle
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = set()
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    loop._session_logger.log_path = None

    _setup_skill_stage_mocks(loop, monkeypatch)
    discovery_mock = AsyncMock()
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )
    monkeypatch.setattr(loop_module.config, "MISTAKE_DISCOVERY_ENABLED", True)

    asyncio.run(loop._post_run_skill_update())

    discovery_mock.assert_not_awaited()


def test_memory_stage_no_longer_calls_mistake_discovery(monkeypatch):
    """The memory stage must no longer invoke mistake_discovery directly.
    Discovery is now the skills stage's responsibility."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._use_llm = False  # skip build-analysis branch
    loop._memory = MagicMock()
    loop._memory.should_consolidate = True
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._memory.maintenance = MagicMock()
    loop._memory.save_all = MagicMock()
    loop._memory.stats = MagicMock(return_value={})
    loop._post_run_hcm_extraction = MagicMock()

    async def _ok(*a, **kw):
        return {"combat": 0, "route": 0, "deck": 0}
    monkeypatch.setattr(
        "src.memory.guide_consolidator.consolidate_guides", _ok,
    )

    discovery_mock = AsyncMock()
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )

    asyncio.run(loop._post_run_memory_update())

    discovery_mock.assert_not_awaited()  # not called from memory stage
    loop._memory.reset_consolidation_count.assert_not_called()  # reset moved to finally
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_loop_post_run.py -k "skills_stage_runs_mistake or skills_stage_skips_mistake or memory_stage_no_longer" -v
```
Expected: FAIL — `mistake_discovery` is still called from memory stage; not yet from skills stage.

- [ ] **Step 3: Delete the `mistake_discovery` block + inline reset from memory stage**

Edit `src/agent/loop.py`. In `_post_run_memory_update`, find the block that starts:

```python
                if self._skill_library and getattr(config, "MISTAKE_DISCOVERY_ENABLED", True):
                    try:
                        import os as _os

                        from src.brain.prompts.system import SYSTEM_COMBAT as _COMBAT_SYS
                        from src.skills.mistake_discovery import run_mistake_discovery
```

…and ends with…

```python
                    except Exception:
                        logger.warning("Mistake-driven discovery failed", exc_info=True)
                self._memory.reset_consolidation_count()
```

DELETE this entire block (the `if self._skill_library and ...` block AND the trailing `self._memory.reset_consolidation_count()` line).

After this edit, the consolidation cycle in memory stage is just:

```python
            if self._postrun_consolidation_active:
                try:
                    from src.memory.guide_consolidator import consolidate_guides
                    guide_stats = await consolidate_guides(
                        self._memory,
                        current_run_id=self._run_state.run_id if self._run_state else "",
                    )
                    total_guides = sum(guide_stats.values())
                    if total_guides > 0:
                        logger.info("Guide consolidation: %s", guide_stats)
                        if self._session_logger is not None and hasattr(
                            self._session_logger, "log_postrun_artifact",
                        ):
                            try:
                                self._session_logger.log_postrun_artifact(
                                    stage="guides",
                                    kind="guide_consolidation",
                                    action="update",
                                    summary=(
                                        f"combat={guide_stats.get('combat', 0)}, "
                                        f"route={guide_stats.get('route', 0)}, "
                                        f"deck={guide_stats.get('deck', 0)}"
                                    ),
                                    after=dict(guide_stats),
                                    source="guide_consolidator",
                                )
                            except Exception:
                                pass
                except Exception:
                    logger.warning("Guide consolidation failed", exc_info=True)
            # mistake_discovery moved to _post_run_skill_update (Spec #2 §3.1).
            # consolidation_count reset moved to _safe_post_run finally
            # block (Spec #2 §3.2).
```

- [ ] **Step 4: Add the `mistake_discovery` block to skills stage**

Edit `src/agent/loop.py`. In `_post_run_skill_update`, find the existing structure:

```python
        try:
            # Score non-combat skills once at run end
            self._score_noncombat_skills_end_of_run()

            # Save current skill state (with any usage/confidence updates)
            skill_path = paths.skills_file()
            self._skill_library.save(skill_path)
```

Insert a new block IMMEDIATELY AFTER `self._score_noncombat_skills_end_of_run()` and BEFORE `# Save current skill state`:

```python
            # Mistake-driven skill discovery (relocated from memory stage,
            # Spec #2 §3.1). Gated on the cadence snapshot taken at memory-
            # stage entry so consolidate_guides exceptions don't suppress
            # discovery (Spec #2 §3.4). Runs BEFORE save so any newly
            # written probation skills land in the persisted file below.
            if (
                getattr(self, "_postrun_consolidation_active", False)
                and self._memory
                and getattr(config, "MISTAKE_DISCOVERY_ENABLED", True)
            ):
                try:
                    import os as _os

                    from src.brain.prompts.system import SYSTEM_COMBAT as _COMBAT_SYS
                    from src.skills.mistake_discovery import run_mistake_discovery

                    run_id = self._run_state.run_id if self._run_state else ""
                    this_run_episodes = [
                        e for e in self._memory.combat_store.get_all()
                        if e.run_id == run_id
                    ]
                    sl = getattr(self, "_session_logger", None)
                    log_path = getattr(sl, "log_path", None) or getattr(sl, "path", None)
                    if log_path is None:
                        log_path = Path("nul") if _os.name == "nt" else Path("/dev/null")

                    stats = await run_mistake_discovery(
                        this_run_episodes=this_run_episodes,
                        combat_store=self._memory.combat_store,
                        skill_library=self._skill_library,
                        write_gate=self._write_gate,
                        log_path=log_path,
                        run_id=run_id,
                        combat_system_prompt=_COMBAT_SYS,
                        session_logger=self._session_logger,
                    )
                    if any(v > 0 for v in stats.values()):
                        logger.info("Mistake-driven discovery: %s", stats)
                    if self._session_logger is not None and hasattr(
                        self._session_logger, "log_postrun_artifact",
                    ) and any(v > 0 for v in stats.values()):
                        try:
                            self._session_logger.log_postrun_artifact(
                                stage="skills",
                                kind="skill_discovery",
                                action="mine",
                                summary=(
                                    f"persisted={stats.get('persisted', 0)}, "
                                    f"candidates={stats.get('candidates', 0)}, "
                                    f"ab_passed={stats.get('ab_passed', 0)}"
                                ),
                                after=dict(stats),
                                source="mistake_discovery",
                            )
                        except Exception:
                            pass
                except Exception:
                    logger.warning("Mistake-driven discovery failed", exc_info=True)
```

(The `if stats.get("persisted", 0) > 0: skill_path = paths.skills_file(); self._skill_library.save(skill_path)` block from the old memory-stage version is intentionally NOT carried over: the unconditional `self._skill_library.save(skill_path)` IMMEDIATELY BELOW this insertion already persists everything, including the newly written probation skills.)

- [ ] **Step 5: Run tests**

```
pytest tests/test_loop_post_run.py -k "skills_stage_runs_mistake or skills_stage_skips_mistake or memory_stage_no_longer" -v
```
Expected: 3 PASS.

```
pytest tests/test_loop_post_run.py -v
```
Expected: all PASS (the existing 8-ish + new ones).

- [ ] **Step 6: Commit**

```
git add src/agent/loop.py tests/test_loop_post_run.py
git commit -m "refactor(loop): move mistake_discovery from memory to skills stage"
```

---

## Task 4: Move Non-Combat `record_outcome` to Skills Stage

The non-combat `record_outcome` block currently lives at the top of `_safe_post_run` (around L2811-2835). This task moves the entire block into `_post_run_skill_update` (where it belongs given that the work is purely skill-related).

**Files:**
- Modify: `src/agent/loop.py` (`_safe_post_run` deletion + `_post_run_skill_update` addition)
- Test: `tests/test_loop_post_run.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_loop_post_run.py`:

```python
def test_skills_stage_records_noncombat_outcome_for_meaningful_run(monkeypatch):
    """The non-combat record_outcome block (formerly in _safe_post_run
    body) must now fire from inside _post_run_skill_update for runs
    that are meaningful (>= 20 steps and >= floor 5).

    NOTE: this test uses `_setup_skill_stage_mocks` defined in
    `test_skills_stage_runs_mistake_discovery_when_snapshot_true` above.
    """
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = False
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = {"sk1", "sk2", "sk3"}
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    _setup_skill_stage_mocks(loop, monkeypatch)

    asyncio.run(loop._post_run_skill_update())

    # record_outcome called once with the 3 skill ids and an "ok" bool
    loop._skill_library.record_outcome.assert_called_once()
    call_args = loop._skill_library.record_outcome.call_args
    skill_ids_arg = call_args[0][0]
    run_ok_arg = call_args[0][1]
    assert set(skill_ids_arg) == {"sk1", "sk2", "sk3"}
    # final_floor=20 and victory=False → run_ok should be False (floor < 30, not victory)
    assert run_ok_arg is False


def test_skills_stage_skips_noncombat_record_outcome_for_short_run(monkeypatch):
    """A run too short to be meaningful (< 20 steps OR floor < 5) must
    NOT receive record_outcome — it would unfairly penalize skills."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=2, _highest_floor=2, victory=False)
    loop._current_step = 5
    loop._postrun_consolidation_active = False
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = {"sk1"}
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    _setup_skill_stage_mocks(loop, monkeypatch)

    asyncio.run(loop._post_run_skill_update())

    loop._skill_library.record_outcome.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```
pytest tests/test_loop_post_run.py -k "noncombat_outcome_for_meaningful or noncombat_record_outcome_for_short" -v
```
Expected: FAIL — `record_outcome` is still in `_safe_post_run`'s body, not in `_post_run_skill_update`.

- [ ] **Step 3: Delete the record_outcome block from `_safe_post_run`**

Edit `src/agent/loop.py`. In `_safe_post_run`, find and DELETE the entire block (around L2806-2835):

```python
            # Determine if this run was too short to produce meaningful skill
            # evaluations.  Error-aborted or reloaded runs (e.g. <5 floors of
            # actual gameplay) would unfairly penalise skills that were working.
            run_floor = (self._run_state.final_floor or self._run_state._highest_floor) if self._run_state else 0
            run_steps = self._current_step
            is_meaningful_run = run_steps >= 20 and run_floor >= 5

            # Record coarse outcome for non-combat skills (map, deck_building,
            # event, rest).  These never get COMBAT_END feedback — use floor
            # reached as a proxy for "this run's non-combat decisions were OK".
            if self._skill_library and self._noncombat_skill_ids:
                if is_meaningful_run:
                    run_ok = (self._run_state.victory if self._run_state else False) or run_floor >= 30
                    self._skill_library.record_outcome(
                        list(self._noncombat_skill_ids), run_ok,
                    )
                    logger.info(
                        "Non-combat skill outcome: %s (floor %d) for %d skills",
                        "ok" if run_ok else "poor",
                        run_floor,
                        len(self._noncombat_skill_ids),
                    )
                else:
                    logger.info(
                        "Skipping skill scoring — run too short (floor %d, %d steps) "
                        "to produce meaningful evaluation",
                        run_floor, run_steps,
                    )
```

After deletion, the next code in `_safe_post_run` should be `if self._memory:` for the memory stage block.

- [ ] **Step 4: Add the record_outcome block to `_post_run_skill_update`**

Edit `src/agent/loop.py`. In `_post_run_skill_update`, find the existing top of the `try:` body:

```python
        try:
            # Score non-combat skills once at run end
            self._score_noncombat_skills_end_of_run()
```

Insert a new block IMMEDIATELY BEFORE `# Score non-combat skills once at run end`:

```python
            # Coarse non-combat outcome recording (relocated from
            # _safe_post_run body, Spec #2 §2). These skills (map,
            # deck_building, event, rest) never get COMBAT_END feedback
            # — use floor reached as a proxy. Skip when the run is too
            # short to produce meaningful evaluation.
            run_floor = (
                (self._run_state.final_floor or self._run_state._highest_floor)
                if self._run_state else 0
            )
            run_steps = self._current_step
            is_meaningful_run = run_steps >= 20 and run_floor >= 5
            if self._noncombat_skill_ids:
                if is_meaningful_run:
                    run_ok = (
                        (self._run_state.victory if self._run_state else False)
                        or run_floor >= 30
                    )
                    self._skill_library.record_outcome(
                        list(self._noncombat_skill_ids), run_ok,
                    )
                    logger.info(
                        "Non-combat skill outcome: %s (floor %d) for %d skills",
                        "ok" if run_ok else "poor",
                        run_floor,
                        len(self._noncombat_skill_ids),
                    )
                else:
                    logger.info(
                        "Skipping skill scoring — run too short (floor %d, %d steps) "
                        "to produce meaningful evaluation",
                        run_floor, run_steps,
                    )
```

(Note: the `if self._skill_library` check from the original is dropped here because `_post_run_skill_update` already guards with `if not self._skill_library or not self._run_state: return` at its top.)

- [ ] **Step 5: Run tests**

```
pytest tests/test_loop_post_run.py -k "noncombat_outcome_for_meaningful or noncombat_record_outcome_for_short" -v
```
Expected: 2 PASS.

```
pytest tests/test_loop_post_run.py -v
```
Expected: all PASS.

```
pytest tests/ -q --ignore=tests/regression
```
Expected: same baseline status (no NEW failures).

- [ ] **Step 6: Commit**

```
git add src/agent/loop.py tests/test_loop_post_run.py
git commit -m "refactor(loop): move non-combat record_outcome into skills stage"
```

---

## Task 5: Final Verification

**Files:** none modified.

- [ ] **Step 1: Full test suite**

```
pytest tests/ -q --ignore=tests/regression
```

Expected: same baseline status as before this plan (e.g., 1889 PASS / 1 skipped / 0 failed).

- [ ] **Step 2: Confirm spec coverage**

Check the cadence reset is in `finally` and not anywhere else:

```
grep -n "reset_consolidation_count" src/agent/loop.py
```

Expected: exactly 1 match — inside the `finally` block of `_safe_post_run`. No matches inside `_post_run_memory_update`.

Check `mistake_discovery` is referenced only in the skills stage:

```
grep -n "run_mistake_discovery" src/agent/loop.py
```

Expected: exactly 1 match in `_post_run_skill_update`. No matches in `_post_run_memory_update`.

Check `record_outcome` is in skills stage, not in `_safe_post_run`:

```
grep -n "_skill_library.record_outcome\|skill_library.record_outcome" src/agent/loop.py
```

Expected: 1 match inside `_post_run_skill_update`. No matches inside `_safe_post_run` body.

- [ ] **Step 3: Stage logging unchanged**

The number of stages logged by `_safe_post_run` should still be 3 (`memory`, `skills`, `evolution`):

```
grep -n 'log_post_run_stage(' src/agent/loop.py | head -20
```

Expected: stage names `memory` / `skills` / `evolution` only. NO `core_engine` (that was Spec #1).

- [ ] **Step 4: Sanity import check**

```
python -c "from src.agent.loop import AgentLoop; print('loop OK')"
```

Expected: `loop OK`.

- [ ] **Step 5: Git status clean**

```
git status
```

Expected: clean working tree (only untracked / .log files unrelated to this plan).

- [ ] **Step 6: Commit log review**

```
git log --oneline 4b0983e..HEAD
```

Expected: 4 new commits (one per Task 1 / 2 / 3 / 4) on top of Spec #1's last commit `4b0983e`. Match titles to task names.

No new commit for Task 5 (it's pure verification).

---

## Spec Coverage Self-Check

| Spec section | Task(s) |
|---|---|
| §2 Scope: move `mistake_discovery` | Task 3 |
| §2 Scope: move non-combat `record_outcome` | Task 4 |
| §2 Scope: keep cadence on `should_consolidate` (Option I) | Tasks 2, 3 |
| §2 Scope: bundled improvement (decouple from `consolidate_guides` failure) | Task 2 (snapshot before consolidate) |
| §3.1 Stage layout | Tasks 3, 4 |
| §3.2 Cadence gate (snapshot + finally reset) | Tasks 1, 2 |
| §3.3 Files affected — modifications | Tasks 1-4 |
| §3.4 Failure isolation matrix | Tasks 2-3 (snapshot before consolidate; reset survives skips) |
| §4 Config (no new env vars) | covered by absence |
| §5 Observability (stage timing shifts) | implicit — no code change required, monitor row already exists |
| §6 Testing strategy | Tasks 1-4 (each adds tests) |
| §7 Risks | covered by snapshot design + tests |
| §8 Non-goals | covered by absence (mistake_discovery.py untouched, etc.) |
