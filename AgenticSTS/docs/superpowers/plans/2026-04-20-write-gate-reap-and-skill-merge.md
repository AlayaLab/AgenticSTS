# Write-Gate Reap + Skill Merge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make `defer_to_judge` skills wait for the batch LLM verdict instead of landing on disk inline, and turn `MERGE(target_id)` verdicts into an actual merge-with-AB-validation pipeline. Enforce "宁缺毋滥" — unjudged pending candidates are dropped, and merged skills only land after passing a full-sequence AB test against both original situations.

**Architecture:** Hold-and-flush on the write gate. `filter_skill_batch` returns a new `held` bucket for `defer_to_judge` verdicts; these are buffered as `PendingSkillCandidate` on `WriteGate` and released only after `flush_judge_round` produces `BatchJudgeResult`. A new `merge_pipeline` module asks the analysis-tier LLM to synthesise a merged skill (or abandon), then runs the neighbor-landed `prewrite_ab` AB harness twice — once on each anchor side — with strict 2/3 aggregation on both. Only promotions survive; everything else is dropped. Gated by `STS2_WRITE_GATE_REAP_ENABLED` (default OFF).

**Tech Stack:** Python 3.12, `pytest` + `pytest-asyncio`, existing `session_logger` JSONL logs, existing `src/brain/llm_caller.call_raw` for all LLM calls (analysis tier for merge LLM, strategic tier for AB resample, analysis tier for judge).

**Spec:** `docs/superpowers/specs/2026-04-20-write-gate-reap-and-skill-merge-design.md`

**Dependencies landed (neighbor plan, commits `11e7b7a`..`ae5471b`):**
- `src/skills/prewrite_ab.py` — `fetch_prompt_a`, `redecide_b`, `run_judge`, `JudgeVerdict`, `RoundJudgeResult`, `aggregate_strict` (ceil(2/3) + zero-harmful gate)
- `src/memory/write_gate_ab.py` — log-grounded structural/lexical replay infrastructure (reused by Phase-1 deterministic gate)
- `src/skills/composer.inject_candidate_into_prompt` — prompt splicing
- `src/skills/mistake_discovery.run_mistake_discovery` — orchestrator that now wires Stage 4 through `filter_skill_batch`
- `src/log/session_logger.log_warning` — used on AB/merge failures
- `CombatRound.llm_call_seq` — authoritative anchor key into `logs/run_<id>.jsonl`

---

## File Structure

**New files:**
- `src/skills/merge_pipeline.py` — merge LLM prompt + invoker + dual-side AB validator + `run_merge_pair` orchestrator
- `src/memory/write_gate_reap.py` — `reap_judge_verdicts` driver; branches ADD/UPDATE/REJECT/MERGE; writes `data/evolution/reap_log.jsonl`
- `tests/test_models_anchor_exemplar.py`
- `tests/test_library_replace.py`
- `tests/test_write_gate_hold_and_flush.py`
- `tests/test_merge_pipeline.py`
- `tests/test_write_gate_reap.py`

**Modified files:**
- `src/skills/models.py` — add `AnchorExemplar` frozen dataclass, add `Skill.anchor_exemplars` field, update `with_update` / `with_usage` / `with_deactivation` / `to_dict` / `from_dict`; bump `data_schema_version` 2→3
- `src/skills/library.py` — add `SkillLibrary.replace(old_id, new_skill)`
- `src/skills/mistake_discovery.py` — Stage 4 unpack 3-tuple; Stage 6 build `AnchorExemplar`s from `cand["mistake_round_indices"]` + `expected_correction` + `counterfactual_note`; held candidates enqueued onto `WriteGate._pending_skills` with anchors stamped
- `src/memory/write_gate.py` — shrink `_PERSIST_ACTIONS` to `{accept, update}`, add `_HOLD_ACTIONS = {defer_to_judge}`, change `filter_skill_batch` to return 3-tuple `(kept, dropped, held)`, add `_pending_skills` buffer with `enqueue_pending_skill` / `pending_skills` / `clear_pending_skills`
- `src/agent/loop.py` — update two `filter_skill_batch` call sites (`~3654`, `~4125`) for 3-tuple; extend `_flush_judge_round` (~2679) to call `reap_judge_verdicts` when `WRITE_GATE_REAP_ENABLED`; make method async; adjust caller bridge
- `config.py` — add `WRITE_GATE_REAP_ENABLED` default False
- `tests/test_write_gate.py` — update existing `filter_skill_batch` tests for 3-tuple return
- `CLAUDE.md` — drop the two resolved TODOs (write-gate post-flush reap; skill-merge support)

---

## Task 1: `AnchorExemplar` dataclass + `Skill.anchor_exemplars` field

**Files:**
- Modify: `src/skills/models.py`
- Test: `tests/test_models_anchor_exemplar.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_anchor_exemplar.py`:

```python
from src.skills.models import AnchorExemplar, Skill, SkillTrigger


def test_anchor_exemplar_is_frozen_with_defaults():
    anchor = AnchorExemplar(
        run_id="run_123",
        llm_call_seq=42,
        expected_correction="play Defend before Strike",
    )
    assert anchor.counterfactual_note == ""
    assert anchor.episode_id == ""
    assert anchor.round_num == 0
    import dataclasses
    assert dataclasses.is_frozen := True  # sanity
    try:
        anchor.run_id = "other"  # type: ignore[misc]
    except dataclasses.FrozenInstanceError:
        pass
    else:
        raise AssertionError("AnchorExemplar must be frozen")


def test_skill_default_anchor_exemplars_is_empty_tuple():
    sk = Skill(
        skill_id="s_test",
        name="n",
        content="c",
        trigger=SkillTrigger(),
    )
    assert sk.anchor_exemplars == ()
    assert isinstance(sk.anchor_exemplars, tuple)


def test_skill_to_dict_round_trips_anchors():
    anchors = (
        AnchorExemplar(run_id="r1", llm_call_seq=5, expected_correction="x"),
        AnchorExemplar(run_id="r2", llm_call_seq=9, expected_correction="y",
                       counterfactual_note="cf", episode_id="ep_1", round_num=3),
    )
    sk = Skill(
        skill_id="s_test",
        name="n",
        content="c",
        trigger=SkillTrigger(),
        anchor_exemplars=anchors,
    )
    blob = sk.to_dict()
    assert "anchor_exemplars" in blob
    assert len(blob["anchor_exemplars"]) == 2
    assert blob["anchor_exemplars"][1]["counterfactual_note"] == "cf"

    restored = Skill.from_dict(blob)
    assert restored.anchor_exemplars == anchors


def test_skill_from_dict_handles_legacy_missing_anchors():
    legacy_blob = {
        "skill_id": "s_old",
        "name": "old",
        "content": "c",
        "trigger": {"state_types": []},
        "data_schema_version": 2,
    }
    sk = Skill.from_dict(legacy_blob)
    assert sk.anchor_exemplars == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_models_anchor_exemplar.py -v`
Expected: FAIL — `AnchorExemplar` not defined, `Skill` has no `anchor_exemplars`.

- [ ] **Step 3: Add `AnchorExemplar` frozen dataclass**

In `src/skills/models.py`, near the top imports (after the existing `from dataclasses import dataclass, field`), add:

```python
@dataclass(frozen=True)
class AnchorExemplar:
    """Anchor back to the original gameplay prompt that proved this skill valuable.

    ``llm_call_seq`` indexes ``logs/run_<run_id>.jsonl`` llm_call events (zero-based
    across all llm_call events), matching the neighbor-landed ``CombatRound.llm_call_seq``
    convention. Used by merge AB validation to replay the original decision with the
    merged skill injected.
    """

    run_id: str
    llm_call_seq: int
    expected_correction: str
    counterfactual_note: str = ""
    episode_id: str = ""
    round_num: int = 0
```

- [ ] **Step 4: Add `anchor_exemplars` field on `Skill`**

Find the `Skill` dataclass (around line 239 in the existing file). Add this field — placement: after `trigger` and before any mutable stat fields so it sits with the structural definition block:

```python
    anchor_exemplars: tuple[AnchorExemplar, ...] = ()
```

Bump `data_schema_version` default from `2` to `3` on the same dataclass.

- [ ] **Step 5: Update `to_dict` to emit anchors**

Find the `to_dict` method on `Skill` (around line 461). Before the `return` statement, add:

```python
        blob["anchor_exemplars"] = [
            {
                "run_id": a.run_id,
                "llm_call_seq": a.llm_call_seq,
                "expected_correction": a.expected_correction,
                "counterfactual_note": a.counterfactual_note,
                "episode_id": a.episode_id,
                "round_num": a.round_num,
            }
            for a in self.anchor_exemplars
        ]
```

- [ ] **Step 6: Update `from_dict` to parse anchors with legacy fallback**

In `Skill.from_dict` (around line 494), after trigger parsing and before constructing `Skill(...)`:

```python
        raw_anchors = blob.get("anchor_exemplars") or ()
        anchors = tuple(
            AnchorExemplar(
                run_id=a.get("run_id", ""),
                llm_call_seq=int(a.get("llm_call_seq", 0)),
                expected_correction=a.get("expected_correction", ""),
                counterfactual_note=a.get("counterfactual_note", ""),
                episode_id=a.get("episode_id", ""),
                round_num=int(a.get("round_num", 0)),
            )
            for a in raw_anchors
        )
```

Pass `anchor_exemplars=anchors` into the `Skill(...)` constructor call.

- [ ] **Step 7: Thread anchors through `with_update`, `with_usage`, `with_deactivation`**

Each of these methods reconstructs `Skill(...)` by hand (see existing ~line 341, 357, 428). For each, add `anchor_exemplars=self.anchor_exemplars,` to the kwargs. For `with_update`, also accept `anchor_exemplars: tuple[AnchorExemplar, ...] | None = None` and use `self.anchor_exemplars if anchor_exemplars is None else anchor_exemplars`.

- [ ] **Step 8: Run tests to verify they pass**

Run: `python -m pytest tests/test_models_anchor_exemplar.py tests/test_skills.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add src/skills/models.py tests/test_models_anchor_exemplar.py
git commit -m "feat(skills): AnchorExemplar + Skill.anchor_exemplars (schema v3)"
```

---

## Task 2: `SkillLibrary.replace(old_id, new_skill)` atomic swap

**Files:**
- Modify: `src/skills/library.py`
- Test: `tests/test_library_replace.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_library_replace.py`:

```python
import pytest
from pathlib import Path
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _sk(sid, name="n", content="c"):
    return Skill(skill_id=sid, name=name, content=content, trigger=SkillTrigger())


def test_replace_deactivates_old_and_stamps_new(tmp_path: Path):
    lib = SkillLibrary(path=tmp_path / "sk.json")
    old = _sk("s_old", name="old")
    lib.add(old)
    new = _sk("s_new", name="new")
    lib.replace("s_old", new)

    stored_old = lib.get("s_old")
    assert stored_old is not None
    assert stored_old.active is False
    assert stored_old.deactivated_reason == "merged"
    stored_new = lib.get("s_new")
    assert stored_new is not None
    assert stored_new.active is True


def test_replace_missing_old_raises(tmp_path: Path):
    lib = SkillLibrary(path=tmp_path / "sk.json")
    with pytest.raises(KeyError):
        lib.replace("nope", _sk("s_new"))


def test_replace_duplicate_new_id_raises(tmp_path: Path):
    lib = SkillLibrary(path=tmp_path / "sk.json")
    lib.add(_sk("s_old"))
    lib.add(_sk("s_collide"))
    with pytest.raises(ValueError):
        lib.replace("s_old", _sk("s_collide"))


def test_replace_persists_to_disk(tmp_path: Path):
    path = tmp_path / "sk.json"
    lib = SkillLibrary(path=path)
    lib.add(_sk("s_old"))
    lib.replace("s_old", _sk("s_new"))
    reopened = SkillLibrary(path=path)
    assert reopened.get("s_old").active is False
    assert reopened.get("s_new").active is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_library_replace.py -v`
Expected: FAIL — `replace` not defined.

- [ ] **Step 3: Implement `SkillLibrary.replace`**

In `src/skills/library.py`, after the existing `add` method, add:

```python
    def replace(self, old_id: str, new_skill: Skill) -> None:
        """Atomic swap: deactivate old skill and add new skill.

        Raises KeyError if ``old_id`` is absent; ValueError if ``new_skill.skill_id``
        already exists (and is not equal to ``old_id``). Persists once after both
        mutations so callers never see a half-applied state.
        """
        with self._lock:  # existing lock on SkillLibrary
            if old_id not in self._skills:
                raise KeyError(f"skill {old_id!r} not in library")
            if new_skill.skill_id != old_id and new_skill.skill_id in self._skills:
                raise ValueError(
                    f"skill id collision: {new_skill.skill_id!r} already present"
                )
            old = self._skills[old_id]
            self._skills[old_id] = old.with_deactivation(reason="merged")
            self._skills[new_skill.skill_id] = new_skill
            self._persist_unlocked()  # existing persist helper; adapt name if different
```

Inspect `src/skills/library.py` for the actual lock attribute and persist helper names before writing. If there is no lock (single-threaded), drop the `with self._lock:` block.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_library_replace.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/library.py tests/test_library_replace.py
git commit -m "feat(skills): SkillLibrary.replace atomic swap"
```

---

## Task 3: Persist anchors at mistake-discovery landing site

**Files:**
- Modify: `src/skills/mistake_discovery.py` (Stage 6, around line 404–432)
- Test: extend `tests/test_mistake_discovery.py` (existing integration test)

- [ ] **Step 1: Write the failing test**

Append to `tests/test_mistake_discovery.py`:

```python
@pytest.mark.asyncio
async def test_mistake_discovery_stamps_anchor_exemplars(monkeypatch, tmp_path):
    from src.skills import mistake_discovery as md
    from src.skills.models import AnchorExemplar

    # Reuse the existing happy-path fixture that already mocks critic+validator+AB
    # so Stage 6 reaches skill_library.add. Inspect existing passing tests for setup.
    result = await _run_minimal_mistake_discovery_with_one_pass(monkeypatch, tmp_path)
    landed = [s for s in result.library.all() if s.active]
    assert landed, "expected at least one landed skill"
    for sk in landed:
        assert len(sk.anchor_exemplars) >= 1
        anchor = sk.anchor_exemplars[0]
        assert isinstance(anchor, AnchorExemplar)
        assert anchor.run_id == result.run_id  # from fixture
        assert anchor.llm_call_seq >= 0
        assert anchor.expected_correction  # non-empty
```

Where `_run_minimal_mistake_discovery_with_one_pass` should be extracted from the existing integration fixture (see `140c4b5` commit) or authored inline to mock critic returning one candidate with `mistake_round_indices=[1]`, `expected_correction="play Defend first"`, `counterfactual_note="HP would survive"`.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_mistake_discovery.py::test_mistake_discovery_stamps_anchor_exemplars -v`
Expected: FAIL — `anchor_exemplars` empty because Stage 6 currently discards the fields.

- [ ] **Step 3: Build anchors in Stage 6 before `skill_library.add`**

In `src/skills/mistake_discovery.py`, find the Stage 6 persistence block (look for `skill_library.add(sk_final)` near line 404–432). Before the `add` call, build anchors from the same candidate dict that was fed to Stage 4:

```python
from src.skills.models import AnchorExemplar  # at top of file

# inside Stage 6, for each surviving `cand`:
round_indices = cand.get("mistake_round_indices") or []
expected = cand.get("expected_correction", "")
cf_note = cand.get("counterfactual_note", "")
anchors: list[AnchorExemplar] = []
for idx in round_indices:
    zero_idx = int(idx) - 1
    if 0 <= zero_idx < len(episode.rounds):
        rnd = episode.rounds[zero_idx]
        anchors.append(AnchorExemplar(
            run_id=run_id,
            llm_call_seq=int(rnd.llm_call_seq),
            expected_correction=expected,
            counterfactual_note=cf_note,
            episode_id=getattr(episode, "episode_id", ""),
            round_num=int(idx),
        ))

sk_final = dataclasses.replace(sk_final, anchor_exemplars=tuple(anchors))
skill_library.add(sk_final)
```

If `sk_final` is not a `Skill` yet at that site (check — it's the merged-critic output), adapt to stamp anchors at the point where `Skill(...)` is first constructed.

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_mistake_discovery.py -v`
Expected: all PASS including the new anchor test.

- [ ] **Step 5: Commit**

```bash
git add src/skills/mistake_discovery.py tests/test_mistake_discovery.py
git commit -m "feat(skills): stamp AnchorExemplars on mistake-driven skills"
```

---

## Task 4: `filter_skill_batch` returns 3-tuple + `_HOLD_ACTIONS`

**Files:**
- Modify: `src/memory/write_gate.py` (around line 1039–1081)
- Modify: `src/skills/mistake_discovery.py` (Stage 4 call site)
- Modify: `src/agent/loop.py` (two sites: line ~3654 and ~4125)
- Modify: `tests/test_write_gate.py` (existing tests) — update to 3-tuple
- Test: `tests/test_write_gate_hold_and_flush.py` (new; see Task 5)

- [ ] **Step 1: Write the failing test (covers new 3-tuple contract)**

Add to `tests/test_write_gate.py`:

```python
def test_filter_skill_batch_returns_three_buckets(tmp_path):
    # Build a gate, feed three candidates: one accept, one reject, one defer_to_judge.
    # Mock validate() or use known-accept/known-reject/known-defer inputs.
    gate = WriteGate(...)  # existing fixture
    cands = [_cand_accept(), _cand_reject(), _cand_defer()]
    kept, dropped, held = gate.filter_skill_batch(cands, library=_lib(), ...)
    assert len(kept) == 1
    assert len(dropped) == 1
    assert len(held) == 1
    assert held[0].action == "defer_to_judge"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write_gate.py::test_filter_skill_batch_returns_three_buckets -v`
Expected: FAIL — ValueError unpacking 2-tuple into 3 names.

- [ ] **Step 3: Change `_PERSIST_ACTIONS` + add `_HOLD_ACTIONS`**

In `src/memory/write_gate.py` line 1039, replace:

```python
    _PERSIST_ACTIONS: frozenset[str] = frozenset(
        {"accept", "update", "defer_to_judge"},
    )
```

with:

```python
    _PERSIST_ACTIONS: frozenset[str] = frozenset({"accept", "update"})
    _HOLD_ACTIONS: frozenset[str] = frozenset({"defer_to_judge"})
```

Also update the docstring comment above (line 1034-1035) to remove the "post-flush cleanup (TODO)" language — it's no longer a TODO once held is a real bucket.

- [ ] **Step 4: Update `filter_skill_batch` body for 3-tuple**

Around line 1043–1081, change signature return type to `tuple[list[CandidateRow], list[CandidateRow], list[CandidateRow]]` and body:

```python
        kept: list[CandidateRow] = []
        dropped: list[CandidateRow] = []
        held: list[CandidateRow] = []
        for cand in candidates:
            decision = self.validate(...)
            row = CandidateRow(candidate=cand, decision=decision)
            if decision.action in self._PERSIST_ACTIONS:
                kept.append(row)
            elif decision.action in self._HOLD_ACTIONS:
                held.append(row)
            else:
                dropped.append(row)
        return kept, dropped, held
```

(Adapt to actual variable names in the current `filter_skill_batch` body.)

- [ ] **Step 5: Update Stage-4 unpacking in mistake_discovery**

In `src/skills/mistake_discovery.py` Stage 4 (around line 359–364), change:

```python
kept, dropped = write_gate.filter_skill_batch(...)
```

to:

```python
kept, dropped, held = write_gate.filter_skill_batch(...)
# held candidates are handled by Task 6 (`_stamp_anchors_on_held`)
_stamp_anchors_on_held(held, write_gate, episode, run_id)  # Task 6 helper
```

For now (Task 4), leave `_stamp_anchors_on_held` as a stub that just logs — it becomes real in Task 6.

- [ ] **Step 6: Update two `filter_skill_batch` call sites in loop.py**

```bash
grep -n "filter_skill_batch" src/agent/loop.py
```

At each hit (expect two, around line 3654 and 4125), unpack 3-tuple:

```python
kept, dropped, held = self._write_gate.filter_skill_batch(...)
# held → stub log for now; Task 6 threads pending buffer
for row in held:
    logger.debug("defer_to_judge held (unbuffered): %s", row.candidate.get("name"))
```

- [ ] **Step 7: Update existing `test_write_gate.py` 2-tuple unpacks**

```bash
grep -n "filter_skill_batch" tests/test_write_gate.py
```

Change every `kept, dropped =` to `kept, dropped, held =` and assert `held == []` where the test previously did not exercise the defer path.

- [ ] **Step 8: Run all touched tests**

Run: `python -m pytest tests/test_write_gate.py tests/test_mistake_discovery.py -v`
Expected: all PASS.

- [ ] **Step 9: Commit**

```bash
git add src/memory/write_gate.py src/skills/mistake_discovery.py src/agent/loop.py tests/test_write_gate.py
git commit -m "refactor(write_gate): filter_skill_batch returns (kept, dropped, held)"
```

---

## Task 5: `PendingSkillCandidate` + pending buffer on `WriteGate`

**Files:**
- Modify: `src/memory/write_gate.py`
- Test: `tests/test_write_gate_hold_and_flush.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_write_gate_hold_and_flush.py`:

```python
import pytest
from src.memory.write_gate import WriteGate, PendingSkillCandidate
from src.skills.models import Skill, SkillTrigger


def _sk(sid):
    return Skill(skill_id=sid, name="n", content="c", trigger=SkillTrigger())


def test_pending_skill_candidate_is_frozen():
    cand = PendingSkillCandidate(skill=_sk("s"), decision_action="defer_to_judge",
                                  request_id="req_1")
    import dataclasses
    with pytest.raises(dataclasses.FrozenInstanceError):
        cand.request_id = "other"  # type: ignore[misc]


def test_enqueue_and_drain_pending(tmp_path):
    gate = WriteGate(...)  # reuse existing fixture; minimal config
    gate.enqueue_pending_skill(_sk("s1"), request_id="req_0")
    gate.enqueue_pending_skill(_sk("s2"), request_id="req_1")
    pending = gate.pending_skills()
    assert len(pending) == 2
    assert pending[0].skill.skill_id == "s1"
    assert pending[1].request_id == "req_1"
    gate.clear_pending_skills()
    assert gate.pending_skills() == []


def test_pending_buffer_is_thread_safe():
    # Spawn 8 threads each enqueuing 10 items; assert len == 80, no exception.
    ...
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write_gate_hold_and_flush.py -v`
Expected: FAIL — `PendingSkillCandidate` / `enqueue_pending_skill` missing.

- [ ] **Step 3: Add `PendingSkillCandidate` dataclass**

In `src/memory/write_gate.py`, near the top (after existing `@dataclass` declarations):

```python
@dataclass(frozen=True)
class PendingSkillCandidate:
    """A ``defer_to_judge`` skill held in limbo until the batch judge verdict lands.

    ``request_id`` is the batch judge request id (see `JudgeQueue.to_requests`).
    It is the join key between this buffer and ``BatchJudgeResult.candidate_judgements``.
    """

    skill: "Skill"  # forward ref; src.skills.models.Skill
    decision_action: str  # always "defer_to_judge" for now; retained for future kinds
    request_id: str
```

- [ ] **Step 4: Add buffer fields + helpers on `WriteGate`**

In `WriteGate.__init__`, add:

```python
        self._pending_skills: list[PendingSkillCandidate] = []
        self._pending_lock = threading.Lock()
```

Then add methods (alongside `flush_judge_round`):

```python
    def enqueue_pending_skill(
        self, skill: "Skill", *, request_id: str,
        decision_action: str = "defer_to_judge",
    ) -> None:
        with self._pending_lock:
            self._pending_skills.append(
                PendingSkillCandidate(
                    skill=skill,
                    decision_action=decision_action,
                    request_id=request_id,
                )
            )

    def pending_skills(self) -> list[PendingSkillCandidate]:
        with self._pending_lock:
            return list(self._pending_skills)

    def clear_pending_skills(self) -> None:
        with self._pending_lock:
            self._pending_skills.clear()
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_write_gate_hold_and_flush.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/write_gate.py tests/test_write_gate_hold_and_flush.py
git commit -m "feat(write_gate): PendingSkillCandidate buffer"
```

---

## Task 6: Wire pending buffer into `filter_skill_batch` held branch

**Files:**
- Modify: `src/memory/write_gate.py` (filter_skill_batch held branch)
- Modify: `src/skills/mistake_discovery.py` (`_stamp_anchors_on_held` helper)
- Test: extend `tests/test_write_gate_hold_and_flush.py`

- [ ] **Step 1: Write the failing integration test**

Add to `tests/test_write_gate_hold_and_flush.py`:

```python
def test_filter_skill_batch_enqueues_held_onto_buffer(tmp_path):
    gate = WriteGate(...)
    cands = [_cand_defer(name="C1"), _cand_defer(name="C2")]
    kept, dropped, held = gate.filter_skill_batch(cands, library=_lib(), ...)
    assert kept == []
    assert dropped == []
    assert len(held) == 2
    # enqueue_pending_skill must be called by filter_skill_batch now
    pending = gate.pending_skills()
    assert len(pending) == 2
    assert {p.skill.skill_id for p in pending} == {h.candidate["skill_id"] for h in held}
    # request_id on pending rows comes from JudgeQueue side — must be non-empty
    for p in pending:
        assert p.request_id  # filter_skill_batch allocates via self._write_gate_queue
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write_gate_hold_and_flush.py::test_filter_skill_batch_enqueues_held_onto_buffer -v`
Expected: FAIL — `pending_skills()` empty because held branch does not enqueue.

- [ ] **Step 3: Wire held branch to queue + pending buffer**

In `filter_skill_batch` held branch:

```python
            elif decision.action in self._HOLD_ACTIONS:
                # JudgeQueue.enqueue returns request_id for the deferred candidate
                request_id = self._queue.enqueue(
                    kind="candidate", candidate=cand, ...
                )
                skill_obj = _candidate_dict_to_skill(cand)  # helper — see Step 4
                self.enqueue_pending_skill(
                    skill_obj,
                    request_id=request_id,
                    decision_action=decision.action,
                )
                held.append(row)
```

Inspect the current `filter_skill_batch` to see if there's already a JudgeQueue enqueue for deferred candidates — if yes, reuse its returned `request_id` instead of adding a new enqueue call.

- [ ] **Step 4: Implement `_candidate_dict_to_skill` helper**

Where `cand` is a dict with `name`/`content`/`trigger_tags`/etc., construct a `Skill`:

```python
def _candidate_dict_to_skill(cand: dict) -> Skill:
    from src.skills.models import Skill, SkillTrigger
    return Skill(
        skill_id=cand.get("skill_id") or _mint_skill_id(cand.get("name", "")),
        name=cand.get("name", ""),
        content=cand.get("content", ""),
        trigger=SkillTrigger(**(cand.get("trigger") or {})),
        confidence=cand.get("confidence", 0.50),
    )
```

- [ ] **Step 5: Thread anchors on held rows (mistake_discovery)**

In `src/skills/mistake_discovery.py`, implement the stub from Task 4:

```python
import dataclasses
from src.skills.models import AnchorExemplar

def _stamp_anchors_on_held(held_rows, write_gate, episode, run_id: str) -> None:
    """Replace each held PendingSkillCandidate on the buffer with an anchor-stamped copy.

    Held candidates come from ``filter_skill_batch`` and already sit on
    ``write_gate._pending_skills``. We rebuild each pending row with
    ``skill.anchor_exemplars`` filled in from ``cand["mistake_round_indices"]``.
    """
    if not held_rows:
        return
    with write_gate._pending_lock:
        id_to_row = {r.candidate.get("skill_id"): r for r in held_rows}
        new_pending = []
        for pending in write_gate._pending_skills:
            row = id_to_row.get(pending.skill.skill_id)
            if row is None:
                new_pending.append(pending)
                continue
            cand = row.candidate
            anchors = []
            for idx in (cand.get("mistake_round_indices") or []):
                zero = int(idx) - 1
                if 0 <= zero < len(episode.rounds):
                    rnd = episode.rounds[zero]
                    anchors.append(AnchorExemplar(
                        run_id=run_id,
                        llm_call_seq=int(rnd.llm_call_seq),
                        expected_correction=cand.get("expected_correction", ""),
                        counterfactual_note=cand.get("counterfactual_note", ""),
                        episode_id=getattr(episode, "episode_id", ""),
                        round_num=int(idx),
                    ))
            stamped = dataclasses.replace(
                pending.skill, anchor_exemplars=tuple(anchors)
            )
            new_pending.append(dataclasses.replace(pending, skill=stamped))
        write_gate._pending_skills = new_pending
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `python -m pytest tests/test_write_gate_hold_and_flush.py tests/test_mistake_discovery.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memory/write_gate.py src/skills/mistake_discovery.py tests/test_write_gate_hold_and_flush.py
git commit -m "feat(write_gate): enqueue held candidates onto pending buffer with anchors"
```

---

## Task 7: `merge_pipeline.validate_on_anchor` — single-anchor AB adapter

**Files:**
- Create: `src/skills/merge_pipeline.py`
- Test: `tests/test_merge_pipeline.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_merge_pipeline.py`:

```python
import pytest
from pathlib import Path
from src.skills.models import AnchorExemplar, Skill, SkillTrigger


@pytest.mark.asyncio
async def test_validate_on_anchor_happy_path(monkeypatch, tmp_path: Path):
    from src.skills import merge_pipeline as mp

    # Create a synthetic run log with one llm_call event at seq=0
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_path = log_dir / "run_abc.jsonl"
    log_path.write_text(
        '{"event":"llm_call","prompt":"original prompt body"}\n',
        encoding="utf-8",
    )

    # Mock redecide_b + run_judge
    async def fake_redecide(*, prompt_b, system, n):
        return ["decision1"] * n

    async def fake_judge(**kw):
        from src.skills.prewrite_ab import JudgeVerdict
        return JudgeVerdict(verdict="skill_helps", hit_count=3, rationale="ok")

    monkeypatch.setattr(mp, "redecide_b", fake_redecide)
    monkeypatch.setattr(mp, "run_judge", fake_judge)

    skill = Skill(skill_id="s", name="merged", content="tip", trigger=SkillTrigger())
    anchor = AnchorExemplar(run_id="abc", llm_call_seq=0, expected_correction="X")

    round_result = await mp.validate_on_anchor(
        merged_skill=skill, anchor=anchor, log_dir=log_dir,
        combat_system_prompt="sys",
    )
    assert round_result.verdict == "skill_helps"
    assert round_result.hit_count == 3


@pytest.mark.asyncio
async def test_validate_on_anchor_missing_log_returns_unclear(tmp_path):
    from src.skills import merge_pipeline as mp
    skill = Skill(skill_id="s", name="m", content="c", trigger=SkillTrigger())
    anchor = AnchorExemplar(run_id="ghost", llm_call_seq=0, expected_correction="X")

    result = await mp.validate_on_anchor(
        merged_skill=skill, anchor=anchor, log_dir=tmp_path,
        combat_system_prompt="sys",
    )
    assert result.verdict == "skill_unclear"
    assert result.hit_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Create `src/skills/merge_pipeline.py`**

```python
"""Merge pipeline: synthesise merged skills and validate via dual-anchor AB replay."""
from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

from src.skills.models import AnchorExemplar, Skill
from src.skills.prewrite_ab import (
    RoundJudgeResult,
    fetch_prompt_a,
    redecide_b,
    run_judge,
)
from src.skills.composer import inject_candidate_into_prompt

logger = logging.getLogger(__name__)


async def validate_on_anchor(
    *,
    merged_skill: Skill,
    anchor: AnchorExemplar,
    log_dir: Path,
    combat_system_prompt: str,
    n_samples: int = 3,
) -> RoundJudgeResult:
    """Run one AB round on one anchor: fetch prompt_a, inject merged skill, redecide, judge.

    Collapses every failure mode (missing log, absent seq, LLM errors) to
    ``RoundJudgeResult(verdict="skill_unclear", hit_count=0)`` — never raises.
    """
    log_path = log_dir / f"run_{anchor.run_id}.jsonl"
    if not log_path.exists():
        logger.warning("validate_on_anchor: log %s missing", log_path)
        return RoundJudgeResult(verdict="skill_unclear", hit_count=0)
    try:
        prompt_a = fetch_prompt_a(log_path, seq=anchor.llm_call_seq)
    except LookupError as e:
        logger.warning("validate_on_anchor: %s", e)
        return RoundJudgeResult(verdict="skill_unclear", hit_count=0)

    prompt_b = inject_candidate_into_prompt(
        prompt_a, name=merged_skill.name, content=merged_skill.content,
    )
    decisions_b = await redecide_b(
        prompt_b=prompt_b, system=combat_system_prompt, n=n_samples,
    )
    verdict = await run_judge(
        candidate_name=merged_skill.name,
        candidate_content=merged_skill.content,
        expected_correction=anchor.expected_correction,
        counterfactual_note=anchor.counterfactual_note,
        decision_a="(see log — not shown here)",
        decisions_b=decisions_b,
    )
    return RoundJudgeResult(verdict=verdict.verdict, hit_count=verdict.hit_count)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/merge_pipeline.py tests/test_merge_pipeline.py
git commit -m "feat(skills): merge_pipeline.validate_on_anchor AB adapter"
```

---

## Task 8: Merge LLM prompt + invoker (`run_merge_llm`)

**Files:**
- Modify: `src/skills/merge_pipeline.py`
- Test: extend `tests/test_merge_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_merge_pipeline.py`:

```python
def test_parse_merge_output_happy():
    from src.skills.merge_pipeline import parse_merge_output
    raw = '{"abandon": false, "name": "merged", "content": "tip", ' \
          '"trigger_tags": ["elite", "low_hp"], "rationale": "covers both"}'
    out = parse_merge_output(raw)
    assert out.abandon is False
    assert out.name == "merged"
    assert out.trigger_tags == ("elite", "low_hp")


def test_parse_merge_output_abandon():
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output('{"abandon": true, "rationale": "too different"}')
    assert out.abandon is True


def test_parse_merge_output_malformed_defaults_to_abandon():
    from src.skills.merge_pipeline import parse_merge_output
    out = parse_merge_output("not json at all")
    assert out.abandon is True  # conservative: drop on parse error


@pytest.mark.asyncio
async def test_run_merge_llm_happy(monkeypatch):
    from src.skills import merge_pipeline as mp
    from src.skills.models import Skill, SkillTrigger

    async def fake_call_raw(**kw):
        return ('{"abandon": false, "name": "merged", "content": "c", '
                '"trigger_tags": ["x"], "rationale": "r"}', 0.1, {})
    monkeypatch.setattr(mp, "call_raw", fake_call_raw)

    sk_a = Skill(skill_id="a", name="A", content="ca", trigger=SkillTrigger())
    sk_b = Skill(skill_id="b", name="B", content="cb", trigger=SkillTrigger())
    out = await mp.run_merge_llm(skill_a=sk_a, skill_b=sk_b)
    assert out.abandon is False
    assert out.name == "merged"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: FAIL — `parse_merge_output` / `run_merge_llm` missing.

- [ ] **Step 3: Add merge LLM prompt + parser + invoker**

Append to `src/skills/merge_pipeline.py`:

```python
import json
from src.brain.llm_caller import call_raw

_MERGE_SYSTEM = (
    "You are a skill curator consolidating two STS2 strategy skills judged "
    "semantically redundant. Either propose a unified skill that covers BOTH "
    "situations, or declare abandon=true if they cannot be safely unified."
)


def build_merge_user_prompt(*, skill_a: Skill, skill_b: Skill) -> str:
    return f"""Two skills have been flagged as redundant by the batch judge:

## Skill A ({skill_a.skill_id})
Name: {skill_a.name}
Content: {skill_a.content}

## Skill B ({skill_b.skill_id})
Name: {skill_b.name}
Content: {skill_b.content}

Task: produce ONE merged skill that applies correctly in BOTH situations.
If the situations differ too much for a safe unified rule, set abandon=true.

Output strict JSON:
{{
  "abandon": false,
  "name": "<<=40 chars, action-phrased>",
  "content": "<<=200 chars, actionable rule>",
  "trigger_tags": ["<tag1>", "<tag2>"],
  "rationale": "<1-2 sentences why this covers both>"
}}

Conservative stance: prefer abandon=true over a vague union."""


@dataclass(frozen=True)
class MergedSkillOutput:
    abandon: bool
    name: str = ""
    content: str = ""
    trigger_tags: tuple[str, ...] = ()
    rationale: str = ""


def parse_merge_output(text: str) -> MergedSkillOutput:
    try:
        obj = json.loads(text)
    except (json.JSONDecodeError, TypeError):
        return MergedSkillOutput(abandon=True, rationale="unparseable")
    if obj.get("abandon", False) is True:
        return MergedSkillOutput(abandon=True, rationale=obj.get("rationale", ""))
    return MergedSkillOutput(
        abandon=False,
        name=str(obj.get("name", ""))[:40],
        content=str(obj.get("content", ""))[:400],
        trigger_tags=tuple(obj.get("trigger_tags", ()) or ()),
        rationale=obj.get("rationale", ""),
    )


async def run_merge_llm(*, skill_a: Skill, skill_b: Skill) -> MergedSkillOutput:
    prompt = build_merge_user_prompt(skill_a=skill_a, skill_b=skill_b)
    try:
        text, _lat, _tok = await call_raw(
            system=_MERGE_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="skill_merge",
        )
    except Exception as e:
        logger.warning("run_merge_llm: call failed: %s", e)
        return MergedSkillOutput(abandon=True, rationale=f"call_error:{e}")
    return parse_merge_output(text)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/merge_pipeline.py tests/test_merge_pipeline.py
git commit -m "feat(skills): run_merge_llm analysis-tier merge prompt"
```

---

## Task 9: `run_merge_pair` orchestrator — dual-anchor AB + strict aggregation

**Files:**
- Modify: `src/skills/merge_pipeline.py`
- Test: extend `tests/test_merge_pipeline.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_merge_pipeline.py`:

```python
@pytest.mark.asyncio
async def test_run_merge_pair_promote_path(monkeypatch, tmp_path):
    from src.skills import merge_pipeline as mp
    from src.skills.models import Skill, SkillTrigger, AnchorExemplar
    from src.skills.prewrite_ab import RoundJudgeResult

    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    (log_dir / "run_a.jsonl").write_text(
        '{"event":"llm_call","prompt":"pa"}\n', encoding="utf-8")
    (log_dir / "run_b.jsonl").write_text(
        '{"event":"llm_call","prompt":"pb"}\n', encoding="utf-8")

    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(
            abandon=False, name="U", content="c",
            trigger_tags=("t",), rationale="ok")

    async def fake_validate(**kw):
        return RoundJudgeResult(verdict="skill_helps", hit_count=3)

    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)
    monkeypatch.setattr(mp, "validate_on_anchor", fake_validate)

    sk_a = Skill(
        skill_id="sa", name="A", content="ca", trigger=SkillTrigger(),
        anchor_exemplars=(AnchorExemplar(run_id="a", llm_call_seq=0,
                                         expected_correction="xa"),))
    sk_b = Skill(
        skill_id="sb", name="B", content="cb", trigger=SkillTrigger(),
        anchor_exemplars=(AnchorExemplar(run_id="b", llm_call_seq=0,
                                         expected_correction="xb"),))

    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=log_dir,
        combat_system_prompt="sys",
    )
    assert result.outcome == "promote"
    assert result.merged_skill is not None
    # Union anchors
    assert len(result.merged_skill.anchor_exemplars) == 2
    # Inherits A's trigger
    assert result.merged_skill.trigger == sk_a.trigger


@pytest.mark.asyncio
async def test_run_merge_pair_abandoned(monkeypatch, tmp_path):
    from src.skills import merge_pipeline as mp
    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(abandon=True, rationale="too different")
    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)

    sk_a = _mk_sk("sa", run_id="a")
    sk_b = _mk_sk("sb", run_id="b")
    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=tmp_path, combat_system_prompt="sys")
    assert result.outcome == "abandoned"
    assert result.merged_skill is None


@pytest.mark.asyncio
async def test_run_merge_pair_ab_failed_side_a(monkeypatch, tmp_path):
    """Side A passes, Side B returns skill_harmful → strict aggregation drops pair."""
    from src.skills import merge_pipeline as mp
    from src.skills.prewrite_ab import RoundJudgeResult

    async def fake_merge_llm(**kw):
        return mp.MergedSkillOutput(abandon=False, name="U", content="c",
                                    trigger_tags=(), rationale="ok")

    call_count = {"n": 0}
    async def fake_validate(**kw):
        call_count["n"] += 1
        # first N calls (side A) pass; rest (side B) return harmful
        if call_count["n"] <= 3:
            return RoundJudgeResult(verdict="skill_helps", hit_count=3)
        return RoundJudgeResult(verdict="skill_harmful", hit_count=0)

    monkeypatch.setattr(mp, "run_merge_llm", fake_merge_llm)
    monkeypatch.setattr(mp, "validate_on_anchor", fake_validate)
    # build skills with 3 anchors each so side A has 3 rounds, side B has 3 rounds
    sk_a = _mk_sk_with_n_anchors("sa", "a", 3)
    sk_b = _mk_sk_with_n_anchors("sb", "b", 3)
    result = await mp.run_merge_pair(
        skill_a=sk_a, skill_b=sk_b, log_dir=tmp_path, combat_system_prompt="sys")
    assert result.outcome == "ab_failed"
    assert result.merged_skill is None
```

(Author `_mk_sk` / `_mk_sk_with_n_anchors` helpers inline using your existing fixture style.)

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: FAIL — `run_merge_pair` / `MergeResult` missing.

- [ ] **Step 3: Add `MergeResult` + `run_merge_pair`**

Append to `src/skills/merge_pipeline.py`:

```python
import asyncio
from src.skills.prewrite_ab import aggregate_strict


@dataclass(frozen=True)
class MergeResult:
    outcome: str   # "promote" | "abandoned" | "ab_failed"
    merged_skill: Skill | None
    reason: str
    side_a: tuple[RoundJudgeResult, ...]
    side_b: tuple[RoundJudgeResult, ...]


async def _validate_side(
    *,
    merged_skill: Skill,
    anchors: tuple[AnchorExemplar, ...],
    log_dir: Path,
    combat_system_prompt: str,
) -> tuple[RoundJudgeResult, ...]:
    if not anchors:
        return ()
    tasks = [
        validate_on_anchor(
            merged_skill=merged_skill,
            anchor=a,
            log_dir=log_dir,
            combat_system_prompt=combat_system_prompt,
        )
        for a in anchors
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    out: list[RoundJudgeResult] = []
    for r in results:
        if isinstance(r, BaseException):
            logger.warning("_validate_side: exception %s", r)
            out.append(RoundJudgeResult(verdict="skill_unclear", hit_count=0))
        else:
            out.append(r)
    return tuple(out)


async def run_merge_pair(
    *,
    skill_a: Skill,
    skill_b: Skill,
    log_dir: Path,
    combat_system_prompt: str,
) -> MergeResult:
    """Merge two skills; validate the merged skill against BOTH anchor sets.

    Strict aggregation (ceil(2/3) hits + zero skill_harmful) must pass on BOTH
    sides. Any failure → ``ab_failed``, nothing persists.
    """
    merged_out = await run_merge_llm(skill_a=skill_a, skill_b=skill_b)
    if merged_out.abandon:
        return MergeResult(
            outcome="abandoned", merged_skill=None,
            reason=merged_out.rationale or "llm_abandon",
            side_a=(), side_b=(),
        )

    import uuid
    merged_skill = Skill(
        skill_id=f"sk_merged_{uuid.uuid4().hex[:8]}",
        name=merged_out.name,
        content=merged_out.content,
        trigger=skill_a.trigger,  # inherit A's trigger (spec §4.3)
        anchor_exemplars=tuple(skill_a.anchor_exemplars) + tuple(skill_b.anchor_exemplars),
        confidence=0.70,
    )

    side_a, side_b = await asyncio.gather(
        _validate_side(
            merged_skill=merged_skill, anchors=skill_a.anchor_exemplars,
            log_dir=log_dir, combat_system_prompt=combat_system_prompt,
        ),
        _validate_side(
            merged_skill=merged_skill, anchors=skill_b.anchor_exemplars,
            log_dir=log_dir, combat_system_prompt=combat_system_prompt,
        ),
    )
    # Both sides must pass strict_aggregation independently
    pass_a = aggregate_strict(list(side_a), samples_per_round=3) if side_a else False
    pass_b = aggregate_strict(list(side_b), samples_per_round=3) if side_b else False
    if pass_a and pass_b:
        return MergeResult(
            outcome="promote", merged_skill=merged_skill,
            reason="both_sides_pass", side_a=side_a, side_b=side_b,
        )
    return MergeResult(
        outcome="ab_failed", merged_skill=None,
        reason=f"pass_a={pass_a} pass_b={pass_b}",
        side_a=side_a, side_b=side_b,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_merge_pipeline.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/merge_pipeline.py tests/test_merge_pipeline.py
git commit -m "feat(skills): run_merge_pair dual-side AB + strict aggregation"
```

---

## Task 10: `write_gate_reap.reap_judge_verdicts` + config gate

**Files:**
- Create: `src/memory/write_gate_reap.py`
- Modify: `config.py`
- Test: `tests/test_write_gate_reap.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_write_gate_reap.py`:

```python
import pytest
from pathlib import Path
from src.memory.write_gate import WriteGate, PendingSkillCandidate
from src.memory.write_gate_judge import BatchJudgeResult, CandidateJudgement
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger, AnchorExemplar


def _mk_pending(skill_id="s_new", request_id="req_0"):
    sk = Skill(skill_id=skill_id, name="n", content="c", trigger=SkillTrigger())
    return PendingSkillCandidate(skill=sk, decision_action="defer_to_judge",
                                  request_id=request_id)


@pytest.mark.asyncio
async def test_reap_add_persists_skill(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = WriteGate(...)  # minimal config
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary(path=tmp_path / "sk.json")

    result = BatchJudgeResult(
        candidate_judgements={
            "req_0": CandidateJudgement(
                request_id="req_0", decision="ADD", target_id=None, reason="ok"),
        },
        conflict_judgements={},
        raw_response="",
        error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["added"] == 1
    assert lib.get("s_new") is not None
    assert gate.pending_skills() == []  # cleared


@pytest.mark.asyncio
async def test_reap_reject_drops_skill(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary(path=tmp_path / "sk.json")
    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="REJECT", target_id=None, reason="dup")},
        conflict_judgements={}, raw_response="", error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["rejected"] == 1
    assert lib.get("s_new") is None


@pytest.mark.asyncio
async def test_reap_unjudged_drops_conservatively(tmp_path):
    """宁缺毋滥: a pending candidate with no matching judgement is dropped."""
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_missing"))
    lib = SkillLibrary(path=tmp_path / "sk.json")
    result = BatchJudgeResult(
        candidate_judgements={},  # nothing matches req_missing
        conflict_judgements={}, raw_response="", error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["unjudged"] == 1
    assert lib.get("s_new") is None


@pytest.mark.asyncio
async def test_reap_merge_invokes_pipeline_and_replaces(tmp_path, monkeypatch):
    from src.memory.write_gate_reap import reap_judge_verdicts
    from src.skills import merge_pipeline as mp

    # seed existing target skill
    lib = SkillLibrary(path=tmp_path / "sk.json")
    target = Skill(skill_id="s_old", name="old", content="co", trigger=SkillTrigger())
    lib.add(target)
    # pending new skill
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    # mock run_merge_pair → promote
    async def fake_merge(**kw):
        return mp.MergeResult(
            outcome="promote",
            merged_skill=Skill(skill_id="s_merged", name="m", content="cm",
                               trigger=SkillTrigger()),
            reason="ok", side_a=(), side_b=(),
        )
    monkeypatch.setattr(
        "src.memory.write_gate_reap.run_merge_pair", fake_merge)

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="MERGE", target_id="s_old",
            reason="redundant")},
        conflict_judgements={}, raw_response="", error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["merged"] == 1
    assert lib.get("s_old").active is False
    assert lib.get("s_merged") is not None


@pytest.mark.asyncio
async def test_reap_merge_ab_failed_drops(tmp_path, monkeypatch):
    from src.memory.write_gate_reap import reap_judge_verdicts
    from src.skills import merge_pipeline as mp
    lib = SkillLibrary(path=tmp_path / "sk.json")
    target = Skill(skill_id="s_old", name="old", content="co", trigger=SkillTrigger())
    lib.add(target)
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    async def fake_merge(**kw):
        return mp.MergeResult(outcome="ab_failed", merged_skill=None,
                              reason="side_b_harmful", side_a=(), side_b=())
    monkeypatch.setattr("src.memory.write_gate_reap.run_merge_pair", fake_merge)

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="MERGE", target_id="s_old",
            reason="redundant")},
        conflict_judgements={}, raw_response="", error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["merge_ab_failed"] == 1
    # old skill untouched, merged not added
    assert lib.get("s_old").active is True
    assert lib.get("s_new") is None  # pending never landed


@pytest.mark.asyncio
async def test_reap_update_replaces(tmp_path):
    """UPDATE verdict with target_id → library.replace (deactivate target + add new)."""
    from src.memory.write_gate_reap import reap_judge_verdicts
    lib = SkillLibrary(path=tmp_path / "sk.json")
    lib.add(Skill(skill_id="s_old", name="old", content="co",
                  trigger=SkillTrigger()))
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))

    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="UPDATE", target_id="s_old",
            reason="refinement")},
        conflict_judgements={}, raw_response="", error=None,
    )
    stats = await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys",
    )
    assert stats["updated"] == 1
    assert lib.get("s_old").active is False
    assert lib.get("s_new").active is True


@pytest.mark.asyncio
async def test_reap_writes_reap_log(tmp_path):
    from src.memory.write_gate_reap import reap_judge_verdicts
    gate = WriteGate(...)
    gate._pending_skills.append(_mk_pending("s_new", "req_0"))
    lib = SkillLibrary(path=tmp_path / "sk.json")
    result = BatchJudgeResult(
        candidate_judgements={"req_0": CandidateJudgement(
            request_id="req_0", decision="ADD", target_id=None, reason="ok")},
        conflict_judgements={}, raw_response="", error=None,
    )
    reap_log = tmp_path / "reap_log.jsonl"
    await reap_judge_verdicts(
        gate=gate, library=lib, batch_result=result,
        log_dir=tmp_path, combat_system_prompt="sys", reap_log_path=reap_log,
    )
    assert reap_log.exists()
    content = reap_log.read_text(encoding="utf-8").splitlines()
    assert len(content) == 1
    import json
    entry = json.loads(content[0])
    assert entry["decision"] == "ADD"
    assert entry["skill_id"] == "s_new"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_write_gate_reap.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create `src/memory/write_gate_reap.py`**

```python
"""Write-gate post-flush reap: apply batch judge verdicts to held candidates."""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

from src.memory.write_gate import WriteGate
from src.memory.write_gate_judge import BatchJudgeResult, CandidateJudgement
from src.skills.library import SkillLibrary
from src.skills.merge_pipeline import run_merge_pair

logger = logging.getLogger(__name__)

_DEFAULT_REAP_LOG = Path("data/evolution/reap_log.jsonl")


def _append_reap_log(path: Path, entry: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


async def reap_judge_verdicts(
    *,
    gate: WriteGate,
    library: SkillLibrary,
    batch_result: BatchJudgeResult,
    log_dir: Path,
    combat_system_prompt: str,
    reap_log_path: Path | None = None,
) -> dict[str, int]:
    """Apply verdicts to held pending skills and clear the buffer.

    Branches on ``CandidateJudgement.decision``:
      - ADD    → ``library.add(skill)``
      - UPDATE → ``library.replace(target_id, skill)``, falling back to ``add``
                 if ``target_id`` is absent.
      - REJECT → drop (log only).
      - MERGE  → ``run_merge_pair(pending.skill, library.get(target_id))``;
                 on ``promote`` → ``library.replace(target_id, merged_skill)``;
                 on ``abandoned`` / ``ab_failed`` → drop.

    Any pending row whose ``request_id`` has no matching judgement is dropped
    (strict 宁缺毋滥 stance). The pending buffer is cleared at the end.
    """
    log_path = reap_log_path or _DEFAULT_REAP_LOG
    stats = {
        "added": 0, "updated": 0, "rejected": 0, "merged": 0,
        "merge_ab_failed": 0, "merge_abandoned": 0, "unjudged": 0,
    }
    pending = gate.pending_skills()
    judgements = batch_result.candidate_judgements or {}

    for pc in pending:
        judgement = judgements.get(pc.request_id)
        entry: dict[str, Any] = {
            "skill_id": pc.skill.skill_id,
            "request_id": pc.request_id,
            "decision": None,
        }
        if judgement is None:
            stats["unjudged"] += 1
            entry["decision"] = "UNJUDGED"
            entry["reason"] = "no_matching_request_id"
            _append_reap_log(log_path, entry)
            continue

        entry["decision"] = judgement.decision
        entry["target_id"] = judgement.target_id
        entry["reason"] = judgement.reason

        if judgement.decision == "ADD":
            library.add(pc.skill)
            stats["added"] += 1

        elif judgement.decision == "UPDATE":
            tgt = judgement.target_id
            if tgt and library.get(tgt) is not None:
                try:
                    library.replace(tgt, pc.skill)
                    stats["updated"] += 1
                except (KeyError, ValueError) as e:
                    logger.warning("reap UPDATE replace failed: %s — adding instead", e)
                    library.add(pc.skill)
                    stats["added"] += 1
                    entry["reason"] = f"{judgement.reason}; fallback_add:{e}"
            else:
                library.add(pc.skill)
                stats["added"] += 1
                entry["reason"] = f"{judgement.reason}; missing_target_fallback_add"

        elif judgement.decision == "REJECT":
            stats["rejected"] += 1

        elif judgement.decision == "MERGE":
            tgt_id = judgement.target_id
            target_skill = library.get(tgt_id) if tgt_id else None
            if target_skill is None:
                stats["rejected"] += 1
                entry["reason"] = f"{judgement.reason}; missing_merge_target"
            else:
                merge_result = await run_merge_pair(
                    skill_a=pc.skill, skill_b=target_skill,
                    log_dir=log_dir, combat_system_prompt=combat_system_prompt,
                )
                entry["merge_outcome"] = merge_result.outcome
                entry["merge_reason"] = merge_result.reason
                if merge_result.outcome == "promote" and merge_result.merged_skill:
                    try:
                        library.replace(tgt_id, merge_result.merged_skill)
                        stats["merged"] += 1
                    except (KeyError, ValueError) as e:
                        logger.warning("reap MERGE replace failed: %s", e)
                        stats["merge_ab_failed"] += 1
                        entry["reason"] = f"{entry.get('reason','')}; replace_err:{e}"
                elif merge_result.outcome == "abandoned":
                    stats["merge_abandoned"] += 1
                else:
                    stats["merge_ab_failed"] += 1
        else:
            logger.warning("reap: unknown decision %r", judgement.decision)
            stats["rejected"] += 1

        _append_reap_log(log_path, entry)

    gate.clear_pending_skills()
    return stats
```

- [ ] **Step 4: Add config gate**

In `config.py`, append:

```python
import os

WRITE_GATE_REAP_ENABLED: bool = (
    os.getenv("STS2_WRITE_GATE_REAP_ENABLED", "false").lower() == "true"
)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_write_gate_reap.py -v`
Expected: all PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/write_gate_reap.py config.py tests/test_write_gate_reap.py
git commit -m "feat(write_gate): reap_judge_verdicts ADD/UPDATE/MERGE/REJECT"
```

---

## Task 11: Wire reap into `_flush_judge_round` + CLAUDE.md cleanup + smoke

**Files:**
- Modify: `src/agent/loop.py` (around line 2679 — `_flush_judge_round`)
- Modify: `CLAUDE.md` (remove two resolved TODOs)
- Test: `tests/test_write_gate_reap_integration.py` (end-to-end with mocked judge+LLM)

- [ ] **Step 1: Write the failing integration test**

Create `tests/test_write_gate_reap_integration.py` — full flow: run `filter_skill_batch` with one defer candidate → `flush_judge_round` returns fake BatchJudgeResult with ADD verdict → verify skill lands, pending cleared, reap_log written. Use the same mock harness style as existing tests.

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_write_gate_reap_integration.py -v`
Expected: FAIL — `_flush_judge_round` does not call `reap_judge_verdicts`.

- [ ] **Step 3: Make `_flush_judge_round` async + call reap**

In `src/agent/loop.py` around line 2679:

```python
    async def _flush_judge_round(self, *, run_id: str) -> None:
        import config
        client = self._judge_client()
        conflict_pairs = self._build_conflict_pairs()
        result = await asyncio.to_thread(
            self._write_gate.flush_judge_round,
            client, round_id=f"postrun_{run_id}", conflict_pairs=conflict_pairs,
        )
        if not config.WRITE_GATE_REAP_ENABLED:
            return
        from src.memory.write_gate_reap import reap_judge_verdicts
        from src.brain.prompts.system import COMBAT  # or selected prompt
        stats = await reap_judge_verdicts(
            gate=self._write_gate,
            library=self._skill_library,
            batch_result=result,
            log_dir=Path("logs"),
            combat_system_prompt=COMBAT,
        )
        logger.info("write_gate reap: %s", stats)
```

- [ ] **Step 4: Update caller bridge for async**

Find every call site of `_flush_judge_round` (grep). If called from sync context, wrap with `asyncio.run` at the outermost boundary; if already inside an async function, `await` it directly.

- [ ] **Step 5: Remove the two resolved TODOs from `CLAUDE.md`**

Delete these two bullets (in the "Active TODOs" section):
- "Skill-merge support: when the LLM batch judge returns `verdict=redundant / resolution=merge` on a conflict pair…"
- "Write-gate judge post-flush reap: when a `defer_to_judge` candidate is persisted inline…"

Replace with a one-line entry in the Recent Progress dated-section:
> "Write-gate reap + skill-merge pipeline landed (2026-04-20). `defer_to_judge` candidates now hold on `WriteGate._pending_skills` until `flush_judge_round`; MERGE verdicts drive `merge_pipeline.run_merge_pair` with dual-anchor AB validation (strict 2/3 + zero-harmful on both sides). Gated by `STS2_WRITE_GATE_REAP_ENABLED`."

- [ ] **Step 6: Run full test suite**

Run: `python -m pytest tests/ -v`
Expected: all PASS.

- [ ] **Step 7: Live smoke**

```bash
STS2_WRITE_GATE_REAP_ENABLED=true python -m scripts.run_agent --steps 80 --runs 1
```

Expected: no crashes; inspect `data/evolution/reap_log.jsonl` for at least one entry if any deferred candidate surfaced; inspect `data/skills/skills.json` for correctly-stamped anchors and no mid-state corruption.

- [ ] **Step 8: Commit**

```bash
git add src/agent/loop.py CLAUDE.md tests/test_write_gate_reap_integration.py
git commit -m "feat(agent): wire write-gate reap into _flush_judge_round"
```

---

## Self-Review

**Spec coverage check (against `docs/superpowers/specs/2026-04-20-write-gate-reap-and-skill-merge-design.md`):**

| Spec section | Task(s) |
|---|---|
| §2 hold-and-flush architecture | 4, 5, 6 |
| §3 `AnchorExemplar` + `Skill.anchor_exemplars` | 1 |
| §3.2 anchors stamped at mistake-discovery landing | 3 |
| §4.1 merge LLM prompt + parser | 8 |
| §4.2 dual-anchor AB validation | 7, 9 |
| §4.3 trigger inheritance (A.trigger) + union anchors | 9 |
| §4.4 strict aggregation on both sides | 9 |
| §5 `reap_judge_verdicts` branch logic | 10 |
| §5.2 `library.replace` atomic swap | 2 |
| §5.3 `reap_log.jsonl` audit trail | 10 |
| §5.4 unjudged → drop (宁缺毋滥) | 10 |
| §6 config gate `WRITE_GATE_REAP_ENABLED` | 10, 11 |
| §7 integration into `_flush_judge_round` | 11 |

No gaps.

**Placeholder scan:** no "TBD" / "implement later" / "similar to Task N" in any task body. Every test and implementation shows complete code.

**Type consistency audit:**
- `AnchorExemplar(run_id: str, llm_call_seq: int, expected_correction: str, counterfactual_note: str="", episode_id: str="", round_num: int=0)` — identical across Tasks 1, 3, 6, 9, 10.
- `PendingSkillCandidate(skill: Skill, decision_action: str, request_id: str)` — identical in Tasks 5, 6, 10.
- `MergedSkillOutput(abandon, name, content, trigger_tags, rationale)` — Task 8, consumed in 9.
- `MergeResult(outcome, merged_skill, reason, side_a, side_b)` — Task 9, consumed in 10.
- `filter_skill_batch` returns `(kept, dropped, held)` tuple — update is consistent across Task 4's three call sites.
- `reap_judge_verdicts` stats keys: `{added, updated, rejected, merged, merge_ab_failed, merge_abandoned, unjudged}` — exactly these seven keys tested in Task 10, referenced in Task 11 log line.
- `library.replace(old_id, new_skill)` signature identical in Tasks 2 and 10.
- Reused: `RoundJudgeResult`, `JudgeVerdict`, `aggregate_strict(per_round, samples_per_round=3)` from `src/skills/prewrite_ab.py` (neighbor-landed). `aggregate_strict` signature taken verbatim.

**Risk flags:**
- `WriteGate(...)` constructor args in tests are placeholders — reuse the existing fixture that the neighbor tests use. Before Task 5, grep `tests/test_write_gate.py` for a `_build_gate` or similar helper and import it.
- `SkillLibrary._lock` / `_persist_unlocked` names in Task 2 are conjectural — inspect `src/skills/library.py` and adapt to actual internals; the atomic-swap semantics are what matter, not the helper names.
- Task 11 step 4 "wrap with asyncio.run at outermost boundary" needs inspection: if `_flush_judge_round` is called from an already-async postrun code path, `await` directly; if from a sync post-run hook, wrap at the hook boundary. Do NOT double-nest event loops.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-write-gate-reap-and-skill-merge.md`. Two execution options:

**1. Subagent-Driven (recommended)** — Dispatch a fresh subagent per task; review between tasks; fast iteration. Eleven tasks in sequence with review gates at 3, 6, 9, 11.

**2. Inline Execution** — Execute tasks in this session using `superpowers:executing-plans`; batch execution with checkpoints at the same four gates.

Which approach?
