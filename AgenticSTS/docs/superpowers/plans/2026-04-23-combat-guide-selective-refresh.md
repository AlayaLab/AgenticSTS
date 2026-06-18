# Combat Guide Selective Refresh Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the full-scan combat branch of `consolidate_guides()` with a run-scoped selection policy: all boss + elite fights from this run, plus the per-act max-HP-loss small monster.

**Architecture:** Change `consolidate_guides()` signature to take the current `run_id`. Add a `_select_combat_keys_for_refresh()` helper that encodes the selection algorithm. Replace the existing combat block with a call to the helper + the existing per-key refresh pipeline (unchanged).

**Tech Stack:** Python 3.14, pytest.

**Spec:** [docs/superpowers/specs/2026-04-23-combat-guide-selective-refresh-design.md](../specs/2026-04-23-combat-guide-selective-refresh-design.md)

---

## File Structure

**Modified files:**
- `src/memory/guide_consolidator.py` — new helper `_select_combat_keys_for_refresh`; combat branch of `consolidate_guides` rewritten; function signature gains `current_run_id` kwarg.
- `src/agent/loop.py` — caller at line ~3782 passes `current_run_id=self._run_state.run_id`.
- `tests/test_guide_consolidation.py` (create if missing, or fold into existing test files like `tests/test_event_guide_consolidator.py` — pick whichever is canonical) — tests for the selection helper.

**Untouched:**
- Route / deck / event branches of `consolidate_guides`.
- `build_combat_guide_prompt`, `parse_combat_guide_response`, `COMBAT_ANALYST_PROMPT`.
- `CombatEpisode` / `CombatMemoryStore` / `CombatGuide` models.
- Consumers of existing guides (retriever, loop).

---

## Task 1: Add the `_select_combat_keys_for_refresh` helper + tests

**Goal:** Introduce the selection algorithm as a pure function. Test it thoroughly before wiring it in — the helper has no dependencies on `memory_manager` / `guide_store` / LLM and can be tested directly.

**Files:**
- Modify: `src/memory/guide_consolidator.py` (add helper, don't wire yet)
- Create or modify: `tests/test_guide_consolidation_combat_selection.py` (new test file; if there's a more natural host like `tests/test_event_guide_consolidator.py` and it covers consolidation broadly, place tests there instead)

- [ ] **Step 1: Locate existing guide-consolidator test files**

```bash
ls tests/ | grep -i 'guide\|consolidat'
```

Read the hit list. If `tests/test_event_guide_consolidator.py` exists and is the broader consolidator test file, add to it. Otherwise create `tests/test_combat_guide_selection.py`.

- [ ] **Step 2: Write the failing test**

Pick the test file decided in Step 1. Add the following tests. (If the helper import path or function name needs adjustment, update imports as needed — the helper will be added in Step 4.)

```python
from dataclasses import replace

from src.memory.guide_consolidator import _select_combat_keys_for_refresh
from src.memory.models_v2 import CombatEpisode


def _make_ep(
    *,
    run_id: str = "run-a",
    enemy_key: str = "jaw_worm",
    character: str = "the ironclad",
    act: int = 1,
    combat_type: str = "monster",
    hp_before: int = 70,
    hp_after: int = 70,
) -> CombatEpisode:
    return CombatEpisode(
        run_id=run_id,
        enemy_key=enemy_key,
        character=character,
        act=act,
        combat_type=combat_type,
        hp_before=hp_before,
        hp_after=hp_after,
    )


def test_selects_all_bosses_and_elites_from_this_run():
    episodes = [
        _make_ep(enemy_key="boss_a", act=3, combat_type="boss",
                 hp_before=80, hp_after=20),
        _make_ep(enemy_key="elite_a", act=1, combat_type="elite",
                 hp_before=70, hp_after=50),
        _make_ep(enemy_key="elite_b", act=2, combat_type="elite",
                 hp_before=65, hp_after=40),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("boss_a", "the ironclad"),
        ("elite_a", "the ironclad"),
        ("elite_b", "the ironclad"),
    }


def test_selects_per_act_max_hp_loss_monster_only():
    episodes = [
        # Act 1: three small monsters, jaw_worm is worst (loss 20)
        _make_ep(enemy_key="cultist", act=1, hp_before=70, hp_after=65),  # loss 5
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50), # loss 20
        _make_ep(enemy_key="louses", act=1, hp_before=70, hp_after=60),   # loss 10
        # Act 2: two small monsters, byrds is worst (loss 25)
        _make_ep(enemy_key="slaver", act=2, hp_before=60, hp_after=50),   # loss 10
        _make_ep(enemy_key="byrds", act=2, hp_before=55, hp_after=30),    # loss 25
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("jaw_worm", "the ironclad"),
        ("byrds", "the ironclad"),
    }


def test_combines_boss_elite_and_per_act_worst_monster():
    episodes = [
        _make_ep(enemy_key="boss_a", act=3, combat_type="boss",
                 hp_before=70, hp_after=10),
        _make_ep(enemy_key="elite_a", act=2, combat_type="elite",
                 hp_before=70, hp_after=40),
        _make_ep(enemy_key="cultist", act=1, hp_before=70, hp_after=65),
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {
        ("boss_a", "the ironclad"),
        ("elite_a", "the ironclad"),
        ("jaw_worm", "the ironclad"),
    }


def test_ignores_episodes_from_other_runs():
    episodes = [
        _make_ep(run_id="run-a", enemy_key="jaw_worm", act=1,
                 hp_before=70, hp_after=50),
        _make_ep(run_id="run-b", enemy_key="byrds", act=1,
                 hp_before=70, hp_after=30),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {("jaw_worm", "the ironclad")}


def test_ignores_episodes_from_other_characters_grouping_is_perrun():
    # Different character appears only when present under the same run_id.
    episodes = [
        _make_ep(run_id="run-a", enemy_key="jaw_worm",
                 character="the silent", act=1,
                 hp_before=70, hp_after=50),
        _make_ep(run_id="run-a", enemy_key="louses",
                 character="the ironclad", act=1,
                 hp_before=70, hp_after=60),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    # Each character gets its own Act-1 worst
    assert keys == {
        ("jaw_worm", "the silent"),
        ("louses", "the ironclad"),
    }


def test_empty_run_produces_no_keys():
    keys = _select_combat_keys_for_refresh([], "run-a")
    assert keys == set()


def test_tie_picks_first_encountered():
    episodes = [
        _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50),
        _make_ep(enemy_key="louses", act=1, hp_before=70, hp_after=50),
    ]
    keys = _select_combat_keys_for_refresh(episodes, "run-a")
    assert keys == {("jaw_worm", "the ironclad")}


def test_skips_aborted_episodes():
    normal = _make_ep(enemy_key="jaw_worm", act=1, hp_before=70, hp_after=50)
    aborted = _make_ep(enemy_key="byrds", act=1, hp_before=70, hp_after=20)
    # Mark aborted via terminal_reason (the is_aborted property reads that field)
    aborted = replace(aborted, terminal_reason="abort")
    keys = _select_combat_keys_for_refresh([normal, aborted], "run-a")
    assert keys == {("jaw_worm", "the ironclad")}
```

**Note on `is_aborted`:** `CombatEpisode.is_aborted` is a `@property` (models_v2.py:486). Check what field it reads (likely `terminal_reason == "abort"`). If the property can't be satisfied via a public field, fall back to `getattr(ep, "is_aborted", False)` checks in tests rather than trying to synthesize an aborted episode.

- [ ] **Step 3: Run the test — it should fail because the helper doesn't exist**

```bash
python -m pytest <path-to-test-file> -v 2>&1 | tail -20
```

Expected: `ImportError` or `AttributeError` on `_select_combat_keys_for_refresh`.

- [ ] **Step 4: Implement the helper in `src/memory/guide_consolidator.py`**

Add near the top of the file (after imports, before `COMBAT_ANALYST_PROMPT` definition). Reuse the existing `normalize_enemy_key` / `normalize_character` imports.

```python
def _select_combat_keys_for_refresh(
    episodes: list[CombatEpisode],
    current_run_id: str,
) -> set[tuple[str, str]]:
    """Pick (enemy_key, character) keys to refresh this postrun.

    Policy:
    - All boss + elite fights from the current run always refresh.
    - Per act, the single small-monster fight with max HP loss refreshes
      (tie → first-encountered in iteration order).
    - Episodes from other runs or marked aborted are ignored.

    Returns a set of normalized (enemy_key, character) tuples. The caller
    runs the existing refresh pipeline per key.
    """
    run_episodes = [
        ep for ep in episodes
        if ep.run_id == current_run_id and not getattr(ep, "is_aborted", False)
    ]

    selected: set[tuple[str, str]] = set()

    # Boss + elite: always refresh
    for ep in run_episodes:
        if ep.combat_type in ("boss", "elite"):
            selected.add((
                normalize_enemy_key(ep.enemy_key),
                normalize_character(ep.character),
            ))

    # Small monster: per (act, character) pick the single worst HP loss fight
    # Using (act, character) as the inner key means a multi-character run
    # (should not exist in practice, but guards against future corruption)
    # still gets one per character per act.
    worst_per_act_char: dict[tuple[int, str], CombatEpisode] = {}
    for ep in run_episodes:
        if ep.combat_type != "monster":
            continue
        hp_loss = ep.hp_before - ep.hp_after
        char = normalize_character(ep.character)
        key = (ep.act, char)
        prev = worst_per_act_char.get(key)
        if prev is None or hp_loss > (prev.hp_before - prev.hp_after):
            worst_per_act_char[key] = ep

    for ep in worst_per_act_char.values():
        selected.add((
            normalize_enemy_key(ep.enemy_key),
            normalize_character(ep.character),
        ))

    return selected
```

Also ensure `CombatEpisode` is imported at the top of the file (it likely is; grep to confirm).

- [ ] **Step 5: Run the tests — they should all pass**

```bash
python -m pytest <path-to-test-file> -v 2>&1 | tail -20
```

Expected: all 8 tests pass.

- [ ] **Step 6: Run the full suite to confirm no regressions**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: baseline + 8 new passes (i.e. `1716 passed, 3 failed` if baseline was `1708 passed, 3 failed`).

- [ ] **Step 7: Commit**

```bash
git add src/memory/guide_consolidator.py <test-file>
git commit -m "feat(memory): add _select_combat_keys_for_refresh helper

Pure function encoding the combat-guide refresh selection policy:
all boss + elite fights from this run, plus the per-act max-HP-loss
small monster. Cross-run / cross-character episodes ignored.

Helper added but not yet wired into consolidate_guides — that's the
next commit. 8 unit tests cover the selection algorithm.

Spec: docs/superpowers/specs/2026-04-23-combat-guide-selective-refresh-design.md"
```

---

## Task 2: Wire the helper into `consolidate_guides` + update caller

**Goal:** Replace the combat branch of `consolidate_guides` with a call to `_select_combat_keys_for_refresh` + the existing per-key refresh pipeline. Update the caller in `loop.py` to pass `current_run_id`.

**Files:**
- Modify: `src/memory/guide_consolidator.py`
- Modify: `src/agent/loop.py`

- [ ] **Step 1: Update `consolidate_guides` signature**

Around `src/memory/guide_consolidator.py:749`:

```python
async def consolidate_guides(
    memory_manager: object,
    *,
    current_run_id: str,
) -> dict[str, int]:
```

Make `current_run_id` a required keyword-only argument. Update the docstring to mention it.

- [ ] **Step 2: Rewrite the combat branch**

Around `src/memory/guide_consolidator.py:772–821` — the `# ── Combat guides ──` block. Replace the existing full-scan grouping with:

```python
    # ── Combat guides ─────────────────────────────────────────
    # Run-scoped selection: boss + elite always, per-act worst monster.
    # See docs/superpowers/specs/2026-04-23-combat-guide-selective-refresh-design.md
    combat_store = memory_manager.combat_store
    if combat_store:
        all_episodes = combat_store.get_all()
        selected_keys = _select_combat_keys_for_refresh(all_episodes, current_run_id)

        for (enemy_key, character) in sorted(selected_keys):
            # LLM still sees full cross-run history for this key
            episodes = [
                ep for ep in all_episodes
                if normalize_enemy_key(ep.enemy_key) == enemy_key
                and normalize_character(ep.character) == character
                and not getattr(ep, "is_aborted", False)
            ]
            if len(episodes) < min_episodes:
                continue

            existing = guide_store.get_combat_guide(enemy_key, character)
            # Skip if guide is up-to-date (same episode count AND has mechanic_summary)
            if existing and existing.episode_count >= len(episodes) and existing.mechanic_summary:
                continue

            wins = sum(1 for e in episodes if e.won)
            win_rate = wins / len(episodes) if episodes else 0.0

            prompt = build_combat_guide_prompt(enemy_key, character, episodes, existing)
            try:
                raw, _latency, _tokens = await llm_call_raw(
                    COMBAT_ANALYST_PROMPT,
                    prompt,
                    think=True,
                    call_type="guide_combat",
                )
                guide = parse_combat_guide_response(
                    raw,
                    enemy_key,
                    character,
                    len(episodes),
                    win_rate,
                    existing,
                )
                if guide:
                    guide_store.set_combat_guide(guide)
                    stats["combat"] += 1
                    logger.info(
                        "Consolidated combat guide: %s (%s) v%d",
                        enemy_key, character, guide.version,
                    )
            except Exception:
                logger.warning(
                    "Combat guide consolidation failed for %s", enemy_key, exc_info=True,
                )
```

Key changes vs. the old block:
- No more grouping over all-history episodes.
- Loop iterates only `selected_keys`.
- "`episode_count >= len(episodes) AND mechanic_summary`" skip stays as a safety guard for the rare case where the same key is selected twice in one postrun — harmless.
- Sorted iteration order for deterministic logs.

- [ ] **Step 3: Update the caller in `src/agent/loop.py`**

At `src/agent/loop.py:3782`:

```python
guide_stats = await consolidate_guides(self._memory)
```

Change to:

```python
guide_stats = await consolidate_guides(
    self._memory,
    current_run_id=self._run_state.run_id if self._run_state else "",
)
```

Rationale for the empty-string fallback: if `_run_state` is somehow None when postrun fires (defensive), `current_run_id=""` will cause `_select_combat_keys_for_refresh` to return an empty set (no episode has `run_id == ""`), so the combat branch becomes a silent no-op. Safer than crashing.

- [ ] **Step 4: Audit for other callers**

```bash
grep -rn 'consolidate_guides' src/ tests/ scripts/
```

Update any additional caller found.

- [ ] **Step 5: Smoke imports**

```bash
python -c "import src.agent.loop; print('loop ok')"
python -c "from src.memory.guide_consolidator import consolidate_guides; print('gc ok')"
```

Expected: both `ok`.

- [ ] **Step 6: Run the full test suite**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: same failure count as Task 1 end state. Some existing guide-consolidation tests may need the new kwarg; update them if pytest surfaces a `TypeError: consolidate_guides() missing 1 required keyword-only argument`.

- [ ] **Step 7: Commit**

```bash
git add src/memory/guide_consolidator.py src/agent/loop.py
git commit -m "refactor(memory): run-scope combat branch of consolidate_guides

Replaces the full-scan grouping of all historical CombatEpisodes with
a call to _select_combat_keys_for_refresh — only episodes from the
current run are candidates for refresh. consolidate_guides now takes
current_run_id as a required kwarg; loop.py caller updated.

Route / deck / event branches unchanged. LLM still receives full
cross-run history for each selected key.

Spec: docs/superpowers/specs/2026-04-23-combat-guide-selective-refresh-design.md"
```

---

## Task 3: End-to-end validation

**Goal:** Confirm the change works end-to-end: all tests green, smoke run shows expected behavior.

**Files:** None modified unless validation surfaces a miss.

- [ ] **Step 1: Full test suite**

```bash
python -m pytest tests/ --no-header -q 2>&1 | tail -5
```

Expected: baseline + 8 new passes (i.e. `1716 passed, 3 failed`).

- [ ] **Step 2: Smoke imports**

```bash
python -c "
import src.agent.loop
from src.memory.guide_consolidator import consolidate_guides, _select_combat_keys_for_refresh
from src.memory.memory_manager import MemoryManager
print('all surviving surface imports ok')
"
```

Expected: `all surviving surface imports ok`.

- [ ] **Step 3: Short live smoke run**

```bash
python -m scripts.run_agent --steps 50 --runs 1 2>&1 | tail -80
```

Expected:
- Run completes without `ImportError` / `AttributeError` / `NameError`.
- At most a handful of `Consolidated combat guide:` log lines.
- **None** of those lines reference characters other than this run's character.
- Other postrun stages (guide consolidation for route/deck/event, mistake discovery, retirement sweep) still fire normally.

If the live run shows a `Consolidated combat guide` line for a wrong-character enemy, that's a regression — investigate.

- [ ] **Step 4: Conditional commit**

If Steps 1-3 surfaced anything requiring fix, commit the fix:
```bash
git add -A
git commit -m "chore: final sweep for combat guide selection"
```

If everything passed cleanly, skip.

- [ ] **Step 5: Record done**

Full commit list for this plan (SHAs + subjects), test delta, invariant: after this plan, `consolidate_guides` only refreshes combat guides for keys the current run produced evidence for — boss/elite always, per-act worst small monster — bounded to ≤(num bosses + num elites + num acts) LLM calls per postrun.

---

## Self-Review Notes

Spec requirements covered:

- Helper for selection algorithm → Task 1
- Signature change on `consolidate_guides` → Task 2 Step 1
- Combat branch rewrite → Task 2 Step 2
- Caller update → Task 2 Step 3
- Route / deck / event untouched → Task 2 Step 2 explicitly only modifies the combat branch
- LLM sees full cross-run history per selected key → Task 2 Step 2 preserves the `episodes = [... not is_aborted ...]` filter that was in the old block
- `CONSOLIDATION_MIN_EPISODES` still gates → Task 2 Step 2 keeps the `if len(episodes) < min_episodes: continue` line

Risks from spec mitigated:

- Signature change → Task 2 Step 4 audits additional callers
- Old guides go stale under new policy → acceptable per spec; no code action
- Ties at zero HP loss → first-seen wins (tested in Task 1 Step 2)

Invariants validated at end → Task 3.
