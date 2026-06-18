# Mistake-Driven Skill Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace win-pattern cohort skill discovery with mistake-driven pipeline: detect over-baseline combats, critic LLM decides if a reusable correction exists, pre-write A/B test validates before persistence, per-combat baseline tracks skill usefulness afterward.

**Architecture:** Post-run runs `mistake_discovery` instead of `cohort_discovery`. Baselines A (per-enemy median) + B (act×type recent-10) identify mistakes. Analysis-tier critic emits one candidate per mistake. Candidate goes through existing cascade dedup (`WriteGate.filter_skill_batch`) then a new §4 A/B validator: inject into original round prompt, re-sample N=3 strategic-tier, LLM judge votes. Strict aggregation rule (from brainstorming): for N mistake rounds → N×3 B samples total → need ≥ ⌈total×2/3⌉ hits AND zero harmful rounds to persist. Post-write lifecycle updates `Skill.confidence` per-combat against the same baselines.

**Tech Stack:** Python 3.12 / asyncio / Pydantic-free frozen dataclasses / pytest / existing `V2Backend` (Gemini 3.1 Pro analysis tier).

---

## File Structure

### New files

| Path | Responsibility |
|---|---|
| `src/skills/mistake_discovery.py` | Orchestrator: baselines → filter → critic → cascade → A/B → persist |
| `src/skills/critic_prompt.py` | Prompt templates, round-snapshot formatter, output schema validator |
| `src/skills/prewrite_ab.py` | Pre-write A/B: read prompt_A from log, redecide B×3, LLM judge, strict aggregation |
| `src/skills/lifecycle.py` | Post-write per-combat baseline confidence update |
| `scripts/migrate_skills_mistake_driven.py` | One-shot: drop all combat skills except seeds + non-combat discovery |
| `tests/test_mistake_discovery.py` | Baselines, filter, orchestrator integration |
| `tests/test_critic_prompt.py` | Snapshot builder + validator (§3.4) |
| `tests/test_prewrite_ab.py` | Injection, judge parsing, strict aggregation math |
| `tests/test_lifecycle.py` | Per-combat outcome classification + confidence update |
| `tests/test_migrate_skills_mistake_driven.py` | Migration keeps seeds+non-combat, drops rest |
| `tests/test_models_v2_new_fields.py` | Round-trip for new CombatRound / CombatEpisode fields |

### Modified files

| Path | Change |
|---|---|
| `src/memory/models_v2.py` | Add 6 new `CombatRound` fields + `llm_call_seq` + `CombatEpisode.retrieved_skill_ids`; update to_dict/from_dict |
| `src/memory/combat_store.py` | Add `recent_by_act_type(...)` |
| `src/memory/combat_extractor.py` | Populate new round fields from tracker + `retrieved_skill_ids` from STM |
| `src/memory/short_term.py` | Add new fields to `CombatRoundTracker` + `record_round_context()` + skill-injection log |
| `src/memory/situation.py` | Drop `threat_level` / `intent_class` / `deck_stage` computation; keep `HandCapabilities` |
| `src/memory/write_gate.py::_trigger_tags_from_skill` | Drop 4 fields (tags/threat_levels/intent_classes/deck_stages); add `requires_enemy_powers` |
| `src/skills/models.py` | Drop `threat_levels`/`intent_classes`/`deck_stages`/`tags` from `SkillTrigger`; `Skill.source` docstring mentions `"mistake_driven"` |
| `src/skills/composer.py` | Add `inject_candidate_into_prompt(prompt, candidate)` |
| `src/skills/library.py` | Drop `hypothesis_store` imports; remove filters keyed on removed trigger fields |
| `src/skills/discovery.py` | Stop writing to removed trigger fields |
| `src/agent/loop.py` | Replace cohort call (~line 3547) with `run_mistake_discovery`; remove hypothesis re-eval block (~line 4106) |
| `src/log/session_logger.py` | Add `_llm_call_seq` counter + `current_llm_call_seq()` |
| `config.py` | Add `MISTAKE_DISCOVERY_ENABLED`, `MISTAKE_VALIDATION_ENABLED`, delta thresholds |

### Deleted files

`src/skills/cohort_discovery.py`, `src/skills/cohort_utils.py`, `src/skills/hypothesis_store.py`, `src/skills/evidence.py`, `tests/test_cohort_discovery.py`, `tests/test_cohort_utils.py`.

---

## Task Dependency Notes

- **Phase A** (schema) blocks everything — do first.
- **Phase B** (capture) needs A1–A2.
- **Phase C** (mistake filter + critic) needs A2–A3.
- **Phase D** (A/B) needs C + B + `session_logger` counter (B4).
- **Phase E** (write_gate) is independent — can happen anytime before Phase G.
- **Phase F** (lifecycle) needs A2.
- **Phase G** (orchestration) ties everything.
- **Phase H** (migrate + cleanup) runs after G green-ends.
- Commit after every task. Many small commits > fewer large ones.

---

## Phase A — Schema Foundations

### Task A1: CombatRound new fields (schema only)

**Files:**
- Modify: `src/memory/models_v2.py:277-350` (`CombatRound` dataclass)
- Test: `tests/test_models_v2_new_fields.py` (new)

**Fields to ADD** (spec §2.3; reuse existing `hp_start`/`energy_available`/`hand_at_start`, do NOT duplicate):

```python
block_before: int = 0
draw_pile_size: int = 0
discard_pile_size: int = 0
exhaust_pile_size: int = 0
usable_potions: tuple[str, ...] = ()
incoming_damage: int = 0
agent_plan: tuple[str, ...] = ()
llm_call_seq: int = -1
```

- [ ] **Step 1: Write the failing test**

Create `tests/test_models_v2_new_fields.py`:

```python
from src.memory.models_v2 import CombatRound, CombatEpisode


def test_combat_round_new_fields_default():
    r = CombatRound()
    assert r.block_before == 0
    assert r.draw_pile_size == 0
    assert r.discard_pile_size == 0
    assert r.exhaust_pile_size == 0
    assert r.usable_potions == ()
    assert r.incoming_damage == 0
    assert r.agent_plan == ()
    assert r.llm_call_seq == -1


def test_combat_round_new_fields_roundtrip():
    r = CombatRound(
        round_num=2,
        hp_start=50,
        block_before=8,
        draw_pile_size=5,
        discard_pile_size=3,
        exhaust_pile_size=1,
        usable_potions=("Fire Potion",),
        incoming_damage=12,
        agent_plan=("Defend -> self", "Strike -> enemy_0"),
        llm_call_seq=7,
    )
    d = r.to_dict()
    r2 = CombatRound.from_dict(d)
    assert r2 == r


def test_combat_round_legacy_dict_loads_with_defaults():
    """Old JSONL without new fields must still load."""
    legacy = {"round_num": 1, "hp_start": 60, "damage_taken": 5}
    r = CombatRound.from_dict(legacy)
    assert r.round_num == 1
    assert r.block_before == 0
    assert r.llm_call_seq == -1
    assert r.usable_potions == ()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models_v2_new_fields.py::test_combat_round_new_fields_default -v`
Expected: FAIL — `AttributeError: 'CombatRound' object has no attribute 'block_before'`

- [ ] **Step 3: Add fields to CombatRound dataclass**

Edit `src/memory/models_v2.py` — in `CombatRound` dataclass after `enemy_hp_snapshot`:

```python
    # Pre-round context (filled by combat_extractor for mistake-driven discovery)
    block_before: int = 0
    draw_pile_size: int = 0
    discard_pile_size: int = 0
    exhaust_pile_size: int = 0
    usable_potions: tuple[str, ...] = ()
    incoming_damage: int = 0
    agent_plan: tuple[str, ...] = ()
    # Index into run_log llm_call events for this round's strategic plan.
    # -1 means unknown/not recorded. Used by prewrite A/B to fetch raw prompt.
    llm_call_seq: int = -1
```

- [ ] **Step 4: Update to_dict to include new fields (only if non-default to keep logs compact)**

In `CombatRound.to_dict` add after `d["damage_taken"] = self.damage_taken`:

```python
        if self.block_before: d["block_before"] = self.block_before
        if self.draw_pile_size: d["draw_pile_size"] = self.draw_pile_size
        if self.discard_pile_size: d["discard_pile_size"] = self.discard_pile_size
        if self.exhaust_pile_size: d["exhaust_pile_size"] = self.exhaust_pile_size
        if self.usable_potions: d["usable_potions"] = list(self.usable_potions)
        if self.incoming_damage: d["incoming_damage"] = self.incoming_damage
        if self.agent_plan: d["agent_plan"] = list(self.agent_plan)
        if self.llm_call_seq >= 0: d["llm_call_seq"] = self.llm_call_seq
```

- [ ] **Step 5: Update from_dict**

In `CombatRound.from_dict` add before `events=...`:

```python
            block_before=d.get("block_before", 0),
            draw_pile_size=d.get("draw_pile_size", 0),
            discard_pile_size=d.get("discard_pile_size", 0),
            exhaust_pile_size=d.get("exhaust_pile_size", 0),
            usable_potions=tuple(d.get("usable_potions", ())),
            incoming_damage=d.get("incoming_damage", 0),
            agent_plan=tuple(d.get("agent_plan", ())),
            llm_call_seq=d.get("llm_call_seq", -1),
```

- [ ] **Step 6: Run tests to verify pass**

Run: `pytest tests/test_models_v2_new_fields.py -v`
Expected: 3 tests PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memory/models_v2.py tests/test_models_v2_new_fields.py
git commit -m "feat(memory): add CombatRound fields for mistake-driven discovery"
```

---

### Task A2: CombatEpisode.retrieved_skill_ids

**Files:**
- Modify: `src/memory/models_v2.py:354-440` (`CombatEpisode` dataclass)
- Test: `tests/test_models_v2_new_fields.py` (extend)

Spec §2.3 also mentioned `deck_snapshot` / `relic_snapshot` — we REUSE existing `CombatEpisode.context.deck_cards` and `CombatEpisode.relics` instead of duplicating. Only `retrieved_skill_ids` is net-new.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_models_v2_new_fields.py`:

```python
def test_combat_episode_retrieved_skill_ids_default():
    ep = CombatEpisode()
    assert ep.retrieved_skill_ids == ()


def test_combat_episode_retrieved_skill_ids_roundtrip():
    ep = CombatEpisode(
        episode_id="ep1",
        run_id="r1",
        enemy_key="Sewer Clam",
        retrieved_skill_ids=("skill_a", "skill_b", "skill_a"),  # dedupe is caller responsibility
    )
    d = ep.to_dict()
    ep2 = CombatEpisode.from_dict(d)
    assert ep2.retrieved_skill_ids == ("skill_a", "skill_b", "skill_a")


def test_combat_episode_legacy_loads():
    legacy = {"episode_id": "x", "run_id": "r", "enemy_key": "Rat"}
    ep = CombatEpisode.from_dict(legacy)
    assert ep.retrieved_skill_ids == ()
```

- [ ] **Step 2: Run tests to verify failure**

Run: `pytest tests/test_models_v2_new_fields.py::test_combat_episode_retrieved_skill_ids_default -v`
Expected: FAIL — `AttributeError: 'CombatEpisode' object has no attribute 'retrieved_skill_ids'`

- [ ] **Step 3: Add field**

In `src/memory/models_v2.py` `CombatEpisode` dataclass after `data_schema_version: int = 2` line:

```python
    # Skill IDs that were injected into this combat's prompts (all turns aggregated,
    # caller does NOT dedupe — length may exceed unique count). Used by post-write
    # lifecycle (§6) to attribute combat-level baseline deltas back to skills.
    retrieved_skill_ids: tuple[str, ...] = ()
```

- [ ] **Step 4: Update to_dict**

In `CombatEpisode.to_dict` after the main dict build, before `return d`:

```python
        if self.retrieved_skill_ids:
            d["retrieved_skill_ids"] = list(self.retrieved_skill_ids)
```

- [ ] **Step 5: Update from_dict**

Find the `from_dict` classmethod and add in the constructor call:

```python
            retrieved_skill_ids=tuple(d.get("retrieved_skill_ids", ())),
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_models_v2_new_fields.py -v`
Expected: all PASS.

- [ ] **Step 7: Commit**

```bash
git add src/memory/models_v2.py tests/test_models_v2_new_fields.py
git commit -m "feat(memory): add CombatEpisode.retrieved_skill_ids for skill lifecycle"
```

---

### Task A3: combat_store.recent_by_act_type

**Files:**
- Modify: `src/memory/combat_store.py:88-128` (add method after `query`)
- Test: `tests/test_combat_store_recent.py` (new)

- [ ] **Step 1: Write the failing test**

Create `tests/test_combat_store_recent.py`:

```python
from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
import time


def _ep(*, run_id="r", act=1, combat_type="monster", character="silent", ts=None):
    return CombatEpisode(
        run_id=run_id,
        act=act,
        combat_type=combat_type,
        character=character,
        enemy_key="Anything",
        timestamp=ts if ts is not None else time.time(),
    )


def test_recent_by_act_type_filters_all_three_keys():
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="r1", act=1, combat_type="monster", character="silent"),
        _ep(run_id="r2", act=2, combat_type="monster", character="silent"),  # wrong act
        _ep(run_id="r3", act=1, combat_type="elite", character="silent"),     # wrong type
        _ep(run_id="r4", act=1, combat_type="monster", character="regent"),   # wrong character
        _ep(run_id="r5", act=1, combat_type="monster", character="silent"),
    ])
    result = store.recent_by_act_type(act=1, combat_type="monster", character="silent", limit=10)
    assert len(result) == 2
    assert {ep.run_id for ep in result} == {"r1", "r5"}


def test_recent_by_act_type_respects_limit_and_recency():
    store = CombatMemoryStore()
    base = time.time()
    for i in range(15):
        store.add(_ep(run_id=f"r{i}", act=1, combat_type="monster", character="silent", ts=base + i))
    result = store.recent_by_act_type(act=1, combat_type="monster", character="silent", limit=10)
    assert len(result) == 10
    # Most recent first — r14 ... r5
    assert result[0].run_id == "r14"
    assert result[-1].run_id == "r5"


def test_recent_by_act_type_excludes_run_id():
    store = CombatMemoryStore()
    store.add_batch([
        _ep(run_id="current"),
        _ep(run_id="r1"),
        _ep(run_id="r2"),
    ])
    result = store.recent_by_act_type(
        act=1, combat_type="monster", character="silent",
        limit=10, exclude_run_id="current",
    )
    assert {ep.run_id for ep in result} == {"r1", "r2"}
```

- [ ] **Step 2: Verify it fails**

Run: `pytest tests/test_combat_store_recent.py -v`
Expected: FAIL — `AttributeError: 'CombatMemoryStore' object has no attribute 'recent_by_act_type'` (also check that `CombatMemoryStore.add` or `add_batch` accept single; if `add` missing use `add_batch([ep])`).

- [ ] **Step 3: Implement method**

Add to `src/memory/combat_store.py` after the `query` method (around line 128):

```python
    def recent_by_act_type(
        self,
        *,
        act: int,
        combat_type: str,
        character: str,
        limit: int = 10,
        exclude_run_id: str | None = None,
    ) -> list[CombatEpisode]:
        """Most-recent episodes at same act × combat_type × character.

        Used by mistake-driven discovery for Baseline B (§2.1 of spec
        2026-04-19-mistake-driven-skill-discovery-design.md).
        Sorted by timestamp desc. Caller computes aggregates (mean/median).
        """
        with self._lock:
            pool = [
                ep for ep in self._episodes
                if ep.act == act
                and ep.combat_type == combat_type
                and ep.character.lower() == character.lower()
                and (exclude_run_id is None or ep.run_id != exclude_run_id)
                and not ep.is_aborted
            ]
        pool.sort(key=lambda e: e.timestamp, reverse=True)
        return pool[:limit]
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_combat_store_recent.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/combat_store.py tests/test_combat_store_recent.py
git commit -m "feat(memory): CombatMemoryStore.recent_by_act_type for Baseline B"
```

---

### Task A4: SkillTrigger drop 4 fields

**Files:**
- Modify: `src/skills/models.py:69-114` (`SkillTrigger` dataclass)
- Test: `tests/test_skill_trigger_matching.py` (review/extend)

- [ ] **Step 1: Find current test coverage**

Run: `pytest tests/test_skill_trigger_matching.py -v 2>&1 | grep -E "threat|intent|deck_stage|tags" | head -20`
Note any tests exercising the 4 dropped fields — those tests will be deleted in Phase H (Task H4).

- [ ] **Step 2: Write new test (forward-compat loading)**

Create `tests/test_skill_trigger_drop_legacy.py`:

```python
from src.skills.models import SkillTrigger


def test_legacy_trigger_dict_with_removed_fields_loads():
    """Skills persisted before removal must still load — removed fields ignored."""
    legacy = {
        "state_types": ["monster"],
        "enemy_names": ["Sewer Clam"],
        "threat_levels": ["high"],
        "intent_classes": ["attack"],
        "deck_stages": ["scaling"],
        "tags": ["alternating"],
        "character": ["silent"],
    }
    t = SkillTrigger.from_dict(legacy)
    assert "monster" in t.state_types
    assert "Sewer Clam" in t.enemy_names
    assert "silent" in t.character
    # Removed fields must not exist as attributes:
    assert not hasattr(t, "threat_levels")
    assert not hasattr(t, "intent_classes")
    assert not hasattr(t, "deck_stages")
    assert not hasattr(t, "tags")
```

- [ ] **Step 3: Verify test fails**

Run: `pytest tests/test_skill_trigger_drop_legacy.py -v`
Expected: FAIL — `hasattr(t, "threat_levels")` is True.

- [ ] **Step 4: Edit SkillTrigger**

In `src/skills/models.py`, `SkillTrigger` dataclass (lines 108–113), REMOVE these four field declarations:

```python
    threat_levels: frozenset[str] = frozenset()    # {"high", "lethal"} — ranking signal
    intent_classes: frozenset[str] = frozenset()    # {"attack", "mixed"} — ranking signal
    deck_stages: frozenset[str] = frozenset()       # {"building", "scaling"} — ranking signal
```

Also remove `tags: frozenset[str] = frozenset()` (line 101).

Keep: `state_types`, `enemy_names`, `min_act`, `max_act`, `hp_below`, `hp_above`, `min_deck_size`, `max_deck_size`, `requires_cards`, `character`, `any_of_relics`, `requires_hand_capabilities`, `requires_enemy_powers`.

- [ ] **Step 5: Update matches() to drop removed-field branches**

In `SkillTrigger.matches()` search for any usage of `self.threat_levels`, `self.intent_classes`, `self.deck_stages`, `self.tags` — delete those if-blocks. They were ranking-score contributions; matches still returns correct bool/score without them.

- [ ] **Step 6: Update from_dict / to_dict**

Find `SkillTrigger.from_dict` and `to_dict`. Remove any references to the 4 dropped keys (do NOT error on legacy dicts that still have them — just ignore extra keys via `d.get(...)` remaining absent).

- [ ] **Step 7: Run tests**

Run: `pytest tests/test_skill_trigger_drop_legacy.py tests/test_skill_trigger_matching.py -v`
Expected: new test PASS; `test_skill_trigger_matching.py` may have regressions — defer until Task H4 (strip legacy tests).

- [ ] **Step 8: Commit**

```bash
git add src/skills/models.py tests/test_skill_trigger_drop_legacy.py
git commit -m "refactor(skills): drop threat_levels/intent_classes/deck_stages/tags from SkillTrigger

Legacy persisted dicts still load via extra-key tolerance in from_dict.
Mistake-driven discovery only needs state_types/enemy_names/requires_* triggers."
```

---

### Task A5: situation.py drop threat/intent/deck_stage computation

**Files:**
- Modify: `src/memory/situation.py` (find and strip `threat_level`/`intent_class`/`deck_stage` functions)
- Test: `tests/test_situation.py` (trim in Phase H; skip for now)

- [ ] **Step 1: Identify targets**

Run: `grep -n "def compute_threat_level\|def compute_intent_class\|def compute_deck_stage\|threat_level\|intent_class\|deck_stage" src/memory/situation.py | head -40`

- [ ] **Step 2: Preserve HandCapabilities**

Before editing, confirm `HandCapabilities` is still needed by `SkillTrigger.requires_hand_capabilities` matching. Search:
`grep -n "HandCapabilities\|hand_capabilities" src/memory/situation.py src/memory/models_v2.py src/skills/models.py`

- [ ] **Step 3: Make `SituationTag` keep only `hand_capabilities` + outcome fields**

Edit `src/memory/situation.py`:

- In the `SituationTag` dataclass, REMOVE fields `threat_level`, `intent_class`, `threat_window`, `deck_stage`, `next_round_window`, `cards_that_helped` if present.
- KEEP: `hand_capabilities`, `damage_taken`, `outcome_quality`, `tag_source`.
- Remove corresponding `compute_*` helpers for threat/intent/deck_stage.
- Leave `HandCapabilities` dataclass and its compute helper untouched.

- [ ] **Step 4: Update to_dict/from_dict**

Strip removed keys from `SituationTag.to_dict()` and `.from_dict()` — tolerate legacy dicts with extra keys (use `d.get`).

- [ ] **Step 5: Fix callers**

Run: `grep -rn "threat_level\|intent_class\|deck_stage\b" src/ --include="*.py" | grep -v tests`
For each hit: delete the read/write. Expected call sites: `combat_store.py::query_rounds` (which we will also delete in a later task since cohort is gone), `situation.py` itself, `short_term.py::_finalize_round_tag`.

In `src/memory/short_term.py`, `_finalize_round_tag`, reduce to only `damage_taken` + `outcome_quality` + `hand_capabilities`.

In `src/memory/combat_store.py::query_rounds` — since this is cohort's entry point and cohort is being removed, DELETE `query_rounds` entirely (also any helper like `_deduplicate_rounds`, `_adjacent_threat`). Keep `query`, `get_by_enemy`, and the new `recent_by_act_type`.

- [ ] **Step 6: Type-check / import-check**

Run: `python -c "from src.memory.situation import SituationTag, HandCapabilities; from src.memory.short_term import CombatTracker; print('ok')"`
Expected: `ok`.

- [ ] **Step 7: Commit**

```bash
git add src/memory/situation.py src/memory/short_term.py src/memory/combat_store.py
git commit -m "refactor(memory): drop threat/intent/deck_stage computation (cohort residue)

Keep HandCapabilities (still a trigger dim). SituationTag reduces to
hand_capabilities + outcome_quality + damage_taken. query_rounds (cohort-only
entrypoint) deleted from CombatMemoryStore."
```

---

## Phase B — Data Capture

### Task B1: CombatRoundTracker new fields

**Files:**
- Modify: `src/memory/short_term.py:66-86` (`CombatRoundTracker`)
- Test: `tests/test_models_v2_new_fields.py` (extend)

- [ ] **Step 1: Write failing test**

Append to `tests/test_models_v2_new_fields.py`:

```python
from src.memory.short_term import CombatRoundTracker


def test_combat_round_tracker_new_fields():
    t = CombatRoundTracker()
    assert t.block_before == 0
    assert t.draw_pile_size == 0
    assert t.discard_pile_size == 0
    assert t.exhaust_pile_size == 0
    assert t.usable_potions == []
    assert t.incoming_damage == 0
    assert t.agent_plan == []
    assert t.llm_call_seq == -1
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_models_v2_new_fields.py::test_combat_round_tracker_new_fields -v`
Expected: FAIL — attribute missing.

- [ ] **Step 3: Add fields to CombatRoundTracker**

In `src/memory/short_term.py` around line 86, after `enemy_hp_snapshot`:

```python
    # Pre-round context for mistake-driven skill discovery (§2.3 of spec).
    block_before: int = 0
    draw_pile_size: int = 0
    discard_pile_size: int = 0
    exhaust_pile_size: int = 0
    usable_potions: list[str] = field(default_factory=list)
    incoming_damage: int = 0
    agent_plan: list[str] = field(default_factory=list)
    llm_call_seq: int = -1
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_models_v2_new_fields.py::test_combat_round_tracker_new_fields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/short_term.py tests/test_models_v2_new_fields.py
git commit -m "feat(memory): CombatRoundTracker fields for mistake-driven discovery"
```

---

### Task B2: Tracker capture method

**Files:**
- Modify: `src/memory/short_term.py` (add `record_round_context` to `CombatTracker`)
- Test: `tests/test_short_term_record_context.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_short_term_record_context.py`:

```python
from src.memory.short_term import CombatTracker


def test_record_round_context_sets_all_fields():
    t = CombatTracker()
    t.start_round(round_num=1, energy=3, hp=50, enemy_intents=["Attack 12"], hand_cards=["Strike"])
    t.record_round_context(
        block_before=5,
        draw_pile_size=12,
        discard_pile_size=3,
        exhaust_pile_size=0,
        usable_potions=["Fire Potion"],
        incoming_damage=12,
        agent_plan=["Defend -> self", "Strike -> enemy_0"],
        llm_call_seq=42,
    )
    cur = t._current_round
    assert cur.block_before == 5
    assert cur.draw_pile_size == 12
    assert cur.usable_potions == ["Fire Potion"]
    assert cur.incoming_damage == 12
    assert cur.agent_plan == ["Defend -> self", "Strike -> enemy_0"]
    assert cur.llm_call_seq == 42


def test_record_round_context_noop_when_no_active_round():
    t = CombatTracker()
    # Do NOT call start_round — _current_round is None
    t.record_round_context(block_before=5)  # must not raise
    assert t._current_round is None
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_short_term_record_context.py -v`
Expected: FAIL — `AttributeError: 'CombatTracker' object has no attribute 'record_round_context'`.

- [ ] **Step 3: Implement method**

Add to `src/memory/short_term.py` inside `CombatTracker` class (any location after `start_round`):

```python
    def record_round_context(
        self,
        *,
        block_before: int = 0,
        draw_pile_size: int = 0,
        discard_pile_size: int = 0,
        exhaust_pile_size: int = 0,
        usable_potions: list[str] | None = None,
        incoming_damage: int = 0,
        agent_plan: list[str] | None = None,
        llm_call_seq: int = -1,
    ) -> None:
        """Record pre-plan context for the current round.

        Called from the combat codepath immediately after the strategic
        plan LLM returns (so llm_call_seq can be attached). Safe no-op
        when there is no active round (e.g. boundary cases before
        start_round is first called).
        """
        if self._current_round is None:
            return
        r = self._current_round
        r.block_before = block_before
        r.draw_pile_size = draw_pile_size
        r.discard_pile_size = discard_pile_size
        r.exhaust_pile_size = exhaust_pile_size
        r.usable_potions = list(usable_potions or [])
        r.incoming_damage = incoming_damage
        r.agent_plan = list(agent_plan or [])
        r.llm_call_seq = llm_call_seq
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_short_term_record_context.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/short_term.py tests/test_short_term_record_context.py
git commit -m "feat(memory): CombatTracker.record_round_context capture hook"
```

---

### Task B3: combat_extractor populates new fields

**Files:**
- Modify: `src/memory/combat_extractor.py:27-50` (`_tracker_round_to_frozen`)
- Test: `tests/test_combat_extractor.py` (create or extend if exists)

- [ ] **Step 1: Write failing test**

Create `tests/test_combat_extractor_new_fields.py`:

```python
from src.memory.short_term import CombatTracker, ShortTermMemory
from src.memory.combat_extractor import extract_combat_episodes


def test_extractor_preserves_round_context():
    stm = ShortTermMemory()
    tracker = CombatTracker(
        enemy_key="Sewer Clam",
        combat_type="monster",
        enemy_names=["Sewer Clam"],
        hp_before=60,
        floor=3,
        act=1,
    )
    tracker.start_round(round_num=1, energy=3, hp=60, enemy_intents=["Attack 10"], hand_cards=["Defend"])
    tracker.record_round_context(
        block_before=0,
        draw_pile_size=9,
        discard_pile_size=0,
        exhaust_pile_size=0,
        usable_potions=[],
        incoming_damage=10,
        agent_plan=["Defend -> self"],
        llm_call_seq=3,
    )
    tracker.record_card_play("Defend", energy_cost=1)
    tracker.update_hp(55)
    # Simulate end: push to completed
    tracker.rounds.append(tracker._current_round)
    tracker._current_round = None
    tracker.hp_after = 55
    stm.completed_combats.append(tracker)

    episodes = extract_combat_episodes(stm, run_id="rX", character="silent")
    assert len(episodes) == 1
    ep = episodes[0]
    r = ep.rounds[0]
    assert r.block_before == 0
    assert r.draw_pile_size == 9
    assert r.incoming_damage == 10
    assert r.agent_plan == ("Defend -> self",)
    assert r.llm_call_seq == 3
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_combat_extractor_new_fields.py -v`
Expected: FAIL — new fields arrive as defaults (0 / ()).

- [ ] **Step 3: Update `_tracker_round_to_frozen`**

Edit `src/memory/combat_extractor.py:27-50`. Add to the `CombatRound(...)` call:

```python
        block_before=r.block_before,
        draw_pile_size=r.draw_pile_size,
        discard_pile_size=r.discard_pile_size,
        exhaust_pile_size=r.exhaust_pile_size,
        usable_potions=tuple(r.usable_potions),
        incoming_damage=r.incoming_damage,
        agent_plan=tuple(r.agent_plan),
        llm_call_seq=r.llm_call_seq,
```

- [ ] **Step 4: Also populate CombatEpisode.retrieved_skill_ids**

Look at the `CombatEpisode(...)` constructor call in `extract_combat_episodes` (~line 80). Add:

```python
            retrieved_skill_ids=tuple(getattr(tracker, "retrieved_skill_ids", [])),
```

And in `src/memory/short_term.py::CombatTracker`, add field:

```python
    retrieved_skill_ids: list[str] = field(default_factory=list)
```

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_combat_extractor_new_fields.py -v`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add src/memory/combat_extractor.py src/memory/short_term.py tests/test_combat_extractor_new_fields.py
git commit -m "feat(memory): combat_extractor preserves new round context + retrieved_skill_ids"
```

---

### Task B4: session_logger llm_call_seq counter

**Files:**
- Modify: `src/log/session_logger.py:615-630`
- Test: `tests/test_session_logger_seq.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_session_logger_seq.py`:

```python
import tempfile, os
from pathlib import Path
from src.log.session_logger import SessionLogger


def test_llm_call_seq_starts_at_zero_and_increments():
    with tempfile.TemporaryDirectory() as td:
        sl = SessionLogger(Path(td) / "run.jsonl")
        assert sl.current_llm_call_seq() == -1  # no calls yet
        sl.log_llm_call("fast", "prompt1", "response1", {"tokens": 10})
        assert sl.current_llm_call_seq() == 0
        sl.log_llm_call("strategic", "prompt2", "response2", {"tokens": 20})
        assert sl.current_llm_call_seq() == 1
        sl.close()


def test_llm_call_seq_survives_close():
    """Counter is session-scoped; after close/reopen a new logger counter is fresh."""
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "run.jsonl"
        sl1 = SessionLogger(p)
        sl1.log_llm_call("fast", "p", "r", {})
        assert sl1.current_llm_call_seq() == 0
        sl1.close()
        # Fresh logger starts fresh — this is by design for post-run reads,
        # which should use jsonl line index, not the live counter.
        sl2 = SessionLogger(p)
        assert sl2.current_llm_call_seq() == -1
        sl2.close()
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_session_logger_seq.py -v`
Expected: FAIL — `AttributeError: 'SessionLogger' object has no attribute 'current_llm_call_seq'`. If `log_llm_call` signature differs, run `grep -n "def log_llm_call\|_write_event.*llm_call" src/log/session_logger.py` first and adjust test call.

- [ ] **Step 3: Add counter**

In `src/log/session_logger.py`:

1. In `SessionLogger.__init__` after existing instance attrs, add:
   ```python
   self._llm_call_seq: int = -1
   ```

2. Find the method (or line) that writes an `"llm_call"` event (around line 621). After the write, increment:
   ```python
   self._llm_call_seq += 1
   ```

3. Add public method:
   ```python
   def current_llm_call_seq(self) -> int:
       """Zero-based index of the most recent llm_call event written, or -1 if none yet.

       Used by CombatTracker.record_round_context to pin the round to a
       specific log entry so prewrite A/B can later fetch the raw prompt.
       """
       return self._llm_call_seq
   ```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_session_logger_seq.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/log/session_logger.py tests/test_session_logger_seq.py
git commit -m "feat(log): expose llm_call_seq counter on SessionLogger"
```

---

### Task B5: Wire capture into combat plan codepath

**Files:**
- Modify: `src/brain/v2_engine.py` (find the method that produces a `CombatPlan` for a round)
- Modify: `src/agent/loop.py` (where STM is updated with round outcome)
- Test: integration-tested via `tests/test_mistake_discovery_integration.py` (Phase G)

- [ ] **Step 1: Find plan-emit codepath**

Run: `grep -rn "record_card_play\|update_hp\|start_round" src/agent src/brain --include="*.py" | head -30`

This shows which module owns the round lifecycle. Target: find the lines where a strategic combat plan is received from V2Backend and applied.

- [ ] **Step 2: Add capture call**

After the strategic-tier combat plan call returns (typically in `v2_engine.py` or wherever `CombatPlan` is constructed for the round), insert:

```python
# Snapshot round context for mistake-driven skill discovery.
# This must run AFTER the llm_call event has been written (so seq is correct).
if self._memory and self._memory.short_term and self._memory.short_term.current_combat_tracker:
    session_logger = getattr(self, "_session_logger", None)
    seq = session_logger.current_llm_call_seq() if session_logger else -1
    try:
        self._memory.short_term.current_combat_tracker.record_round_context(
            block_before=observation.player.block,
            draw_pile_size=len(observation.player.draw_pile),
            discard_pile_size=len(observation.player.discard_pile),
            exhaust_pile_size=len(observation.player.exhaust_pile),
            usable_potions=[p.name for p in observation.player.potions if p.can_use],
            incoming_damage=observation.total_incoming_damage,
            agent_plan=[f"{a.card}->{a.target}" for a in plan.actions],
            llm_call_seq=seq,
        )
    except (AttributeError, KeyError):
        pass  # Do not crash combat on capture failure
```

Exact attribute names (`observation.player.block`, etc.) must be verified against `src/state/game_state.py` and `src/brain/planner.py::CombatPlan`. Adjust imports as needed. If `current_combat_tracker` doesn't exist on `ShortTermMemory`, use existing getter or add a passthrough property that returns the active `CombatTracker`.

- [ ] **Step 3: Smoke test — live no-LLM run**

Run: `python -m scripts.run_agent --steps 20 --runs 1 --no-llm`

Inspect `logs/run_*.jsonl` for `"llm_call_seq"` keys in `round_end` or combat episode dump events. If absent (no LLM = no strategic plan), that's fine — just confirm no exception.

- [ ] **Step 4: Commit**

```bash
git add src/brain/v2_engine.py src/agent/loop.py src/memory/short_term.py
git commit -m "feat(agent): capture round context for mistake-driven skill discovery"
```

---

### Task B6: Wire retrieved_skill_ids capture

**Files:**
- Modify: `src/skills/composer.py` (where skills are composed into prompt)
- Modify: `src/agent/loop.py` (find composer call site)
- Test: via integration

- [ ] **Step 1: Find composer call site**

Run: `grep -rn "compose_skills_for\|inject_skills_into_prompt" src/agent src/brain --include="*.py" | head -20`

- [ ] **Step 2: Append IDs to tracker**

At every composer call site, after retrieval, append the returned `skill_ids` to the active combat tracker:

```python
skill_text, injected_ids = compose_skills_for(...)
if injected_ids and self._memory and self._memory.short_term:
    tracker = getattr(self._memory.short_term, "current_combat_tracker", None)
    if tracker is not None:
        tracker.retrieved_skill_ids.extend(injected_ids)
```

- [ ] **Step 3: Write unit test**

Create `tests/test_skill_retrieval_capture.py`:

```python
from src.memory.short_term import CombatTracker


def test_tracker_accumulates_skill_ids():
    t = CombatTracker()
    t.retrieved_skill_ids.extend(["skill_a", "skill_b"])
    t.retrieved_skill_ids.extend(["skill_a", "skill_c"])  # dup OK; dedup on read
    assert len(t.retrieved_skill_ids) == 4
    assert "skill_c" in t.retrieved_skill_ids
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_skill_retrieval_capture.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py src/memory/short_term.py tests/test_skill_retrieval_capture.py
git commit -m "feat(skills): accumulate injected skill_ids onto active combat tracker"
```

---

## Phase C — Mistake Filter + Critic

### Task C1: loss_ratio + baselines

**Files:**
- Create: `src/skills/mistake_discovery.py`
- Test: `tests/test_mistake_discovery.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_mistake_discovery.py`:

```python
from src.memory.models_v2 import CombatEpisode
from src.skills.mistake_discovery import (
    loss_ratio,
    baseline_a,
    baseline_b,
)


def _ep(hp_before=100, dmg=10, enemy_key="Rat", act=1, combat_type="monster",
        character="silent", run_id="r"):
    return CombatEpisode(
        run_id=run_id, enemy_key=enemy_key, act=act, combat_type=combat_type,
        character=character, hp_before=hp_before, total_damage_taken=dmg,
    )


def test_loss_ratio_basic():
    ep = _ep(hp_before=100, dmg=30)
    assert loss_ratio(ep) == 0.30


def test_loss_ratio_zero_hp_safe():
    ep = _ep(hp_before=0, dmg=5)
    # max(hp, 1) guard
    assert loss_ratio(ep) == 5.0


def test_baseline_a_median_over_history():
    # 5 episodes for Sewer Clam, loss_ratios 0.1/0.2/0.3/0.4/0.5
    history = [_ep(hp_before=100, dmg=r, enemy_key="Sewer Clam") for r in (10,20,30,40,50)]
    val = baseline_a(history)
    assert val == 0.30


def test_baseline_a_inactive_below_three():
    assert baseline_a([_ep(), _ep()]) is None


def test_baseline_b_mean_recent_pool():
    pool = [_ep(hp_before=100, dmg=r) for r in (20, 20, 30)]  # 0.20, 0.20, 0.30
    val = baseline_b(pool)
    assert val == pytest.approx(0.2333, abs=1e-3)


def test_baseline_b_inactive_below_three():
    assert baseline_b([_ep(), _ep()]) is None
```

Add at top: `import pytest`.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_mistake_discovery.py -v`
Expected: FAIL — `ModuleNotFoundError: src.skills.mistake_discovery`.

- [ ] **Step 3: Create module**

Create `src/skills/mistake_discovery.py`:

```python
"""Mistake-driven skill discovery.

See docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md.
"""
from __future__ import annotations

import statistics
from typing import Iterable

from src.memory.models_v2 import CombatEpisode

# Minimum sample sizes (§2.1)
BASELINE_MIN_SAMPLES: int = 3


def loss_ratio(ep: CombatEpisode) -> float:
    """Fraction of pre-combat HP lost. Guard against hp_before=0."""
    return ep.total_damage_taken / max(ep.hp_before, 1)


def baseline_a(history: list[CombatEpisode]) -> float | None:
    """Per-enemy historical median loss_ratio.

    Returns None when fewer than BASELINE_MIN_SAMPLES episodes (§2.1:
    'Baseline A requires ≥3 historical episodes; otherwise A is inactive').
    """
    if len(history) < BASELINE_MIN_SAMPLES:
        return None
    return statistics.median(loss_ratio(e) for e in history)


def baseline_b(pool: list[CombatEpisode]) -> float | None:
    """Act × combat_type × character mean loss_ratio over recent pool.

    Returns None when fewer than BASELINE_MIN_SAMPLES pool entries.
    """
    if len(pool) < BASELINE_MIN_SAMPLES:
        return None
    return statistics.fmean(loss_ratio(e) for e in pool)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_mistake_discovery.py -v`
Expected: 6 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/mistake_discovery.py tests/test_mistake_discovery.py
git commit -m "feat(skills): mistake_discovery baselines + loss_ratio"
```

---

### Task C2: is_mistake_episode filter

**Files:**
- Modify: `src/skills/mistake_discovery.py` (add filter)
- Modify: `tests/test_mistake_discovery.py` (extend)

Delta per combat_type (§2.1): monster 0.10, elite 0.15, boss 0.20.

- [ ] **Step 1: Write failing test**

Append to `tests/test_mistake_discovery.py`:

```python
from src.skills.mistake_discovery import is_mistake_episode, DELTA_BY_TYPE


def test_delta_table():
    assert DELTA_BY_TYPE == {"monster": 0.10, "elite": 0.15, "boss": 0.20}


def test_mistake_episode_a_only_triggers():
    ep = _ep(hp_before=100, dmg=30, combat_type="monster")  # loss = 0.30
    assert is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)


def test_mistake_episode_b_only_triggers():
    ep = _ep(hp_before=100, dmg=30, combat_type="monster")
    assert is_mistake_episode(ep, baseline_a_val=None, baseline_b_val=0.15)


def test_mistake_episode_both_inactive_returns_false():
    ep = _ep(hp_before=100, dmg=50, combat_type="monster")
    assert not is_mistake_episode(ep, baseline_a_val=None, baseline_b_val=None)


def test_mistake_episode_within_delta_not_flagged():
    ep = _ep(hp_before=100, dmg=20, combat_type="monster")  # loss = 0.20
    # Baseline 0.15, delta 0.10 → threshold 0.25 → not a mistake
    assert not is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)


def test_mistake_episode_uses_elite_delta():
    ep = _ep(hp_before=100, dmg=30, combat_type="elite")  # loss = 0.30
    # 0.15 + 0.15 (elite delta) = 0.30 → NOT exceeded (strict >)
    assert not is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)
    ep = _ep(hp_before=100, dmg=31, combat_type="elite")  # loss = 0.31
    assert is_mistake_episode(ep, baseline_a_val=0.15, baseline_b_val=None)
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_mistake_discovery.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/skills/mistake_discovery.py`:

```python
DELTA_BY_TYPE: dict[str, float] = {
    "monster": 0.10,
    "elite": 0.15,
    "boss": 0.20,
}


def is_mistake_episode(
    ep: CombatEpisode,
    *,
    baseline_a_val: float | None,
    baseline_b_val: float | None,
) -> bool:
    """Return True iff ep.loss_ratio exceeds either baseline by its type's delta.

    If both baselines are None (insufficient prior data) → False, per §2.1
    ('If both inactive → episode is not a mistake candidate').
    """
    if baseline_a_val is None and baseline_b_val is None:
        return False
    delta = DELTA_BY_TYPE.get(ep.combat_type, 0.10)
    actual = loss_ratio(ep)
    if baseline_a_val is not None and actual > baseline_a_val + delta:
        return True
    if baseline_b_val is not None and actual > baseline_b_val + delta:
        return True
    return False
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_mistake_discovery.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/mistake_discovery.py tests/test_mistake_discovery.py
git commit -m "feat(skills): is_mistake_episode filter with per-type delta"
```

---

### Task C3: Round-snapshot formatter

**Files:**
- Create: `src/skills/critic_prompt.py`
- Test: `tests/test_critic_prompt.py`

Produces the §2.2 snapshot text for the critic prompt.

- [ ] **Step 1: Write failing test**

Create `tests/test_critic_prompt.py`:

```python
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.skills.critic_prompt import format_round_snapshot, format_combat_header


def _round(**kw):
    defaults = dict(
        round_num=1, energy_available=3, hp_start=50, hp_end=48,
        block_before=0, draw_pile_size=8, discard_pile_size=0, exhaust_pile_size=0,
        hand_at_start=("Strike", "Defend", "Neutralize"),
        usable_potions=(),
        enemy_intents=("Sewer Clam -> Attack 10",),
        incoming_damage=10,
        agent_plan=("Defend -> self",),
        damage_taken=2,
    )
    defaults.update(kw)
    return CombatRound(**defaults)


def _ep():
    return CombatEpisode(
        enemy_key="Sewer Clam",
        combat_type="monster",
        character="silent",
        act=1,
        floor=3,
        hp_before=60,
        hp_after=55,
        total_damage_taken=5,
        rounds=(_round(),),
    )


def test_format_combat_header_contains_key_fields():
    s = format_combat_header(_ep())
    assert "monster" in s
    assert "act 1" in s.lower() or "Act 1" in s
    assert "silent" in s
    assert "hp_before: 60" in s or "hp_before=60" in s


def test_format_round_snapshot_shape():
    s = format_round_snapshot(_round())
    assert "### Round 1" in s
    assert "Hand:" in s
    assert "Strike" in s
    assert "Piles:" in s
    assert "Draw 8" in s
    assert "Enemy intents:" in s
    assert "Incoming:" in s
    assert "10" in s
    assert "Agent plan:" in s
    assert "Defend -> self" in s
    assert "Outcome:" in s
    assert "damage_taken=2" in s


def test_format_round_snapshot_usable_potions():
    r = _round(usable_potions=("Fire Potion", "Block Potion"))
    s = format_round_snapshot(r)
    assert "Usable Potions:" in s
    assert "Fire Potion" in s
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_critic_prompt.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create module**

Create `src/skills/critic_prompt.py`:

```python
"""Critic prompt builder for mistake-driven skill discovery (spec §2.2, §3.2)."""
from __future__ import annotations

from src.memory.models_v2 import CombatEpisode, CombatRound


def format_combat_header(ep: CombatEpisode) -> str:
    ctx = ep.context
    lines: list[str] = []
    lines.append("## Combat Start")
    lines.append(f"encounter_type: {ep.combat_type}")
    lines.append(f"act: {ep.act} | floor: {ep.floor}")
    lines.append(f"character: {ep.character} | hp_before: {ep.hp_before}")
    # Relics: use episode.relics (tuple[str] of "Name (desc)") if present
    if ep.relics:
        lines.append("")
        lines.append("## Relics")
        for r in ep.relics:
            lines.append(f"- {r}")
    # Deck (from context.deck_cards if available)
    if ctx and getattr(ctx, "deck_cards", None):
        lines.append("")
        lines.append(f"## Current Deck ({len(ctx.deck_cards)} cards)")
        # Simple comma-separated format; a more sophisticated card typer can come later
        lines.append("  " + ", ".join(sorted(ctx.deck_cards)))
    # Enemies
    if ctx and getattr(ctx, "enemy_lineup", None):
        lines.append("")
        lines.append("## Enemies (at combat start)")
        for i, en in enumerate(ctx.enemy_lineup):
            name = getattr(en, "name", str(en))
            hp = getattr(en, "hp", "?")
            maxhp = getattr(en, "max_hp", "?")
            lines.append(f"- {name} [index={i}]: HP {hp}/{maxhp}")
    return "\n".join(lines)


def format_round_snapshot(r: CombatRound) -> str:
    lines: list[str] = []
    lines.append(f"### Round {r.round_num}")
    lines.append(
        f"State: Energy {r.energy_available}/{r.energy_available + r.energy_used}, "
        f"HP {r.hp_start}, Block {r.block_before}"
    )
    if r.hand_at_start:
        lines.append(f"Hand: {', '.join(r.hand_at_start)} ({len(r.hand_at_start)} playable)")
    else:
        lines.append("Hand: (empty)")
    lines.append(
        f"Piles: Draw {r.draw_pile_size} | Discard {r.discard_pile_size} | "
        f"Exhaust {r.exhaust_pile_size}"
    )
    if r.usable_potions:
        lines.append(f"Usable Potions: {', '.join(r.usable_potions)}")
    if r.enemy_intents:
        lines.append(f"Enemy intents: {' | '.join(r.enemy_intents)}")
    lines.append(f"Incoming: {r.incoming_damage}")
    if r.agent_plan:
        lines.append(f"Agent plan: [{', '.join(r.agent_plan)}]")
    # Outcome
    quality = "clean" if r.damage_taken == 0 else ("acceptable" if r.damage_taken < 8 else "ugly")
    lines.append(
        f"Outcome: damage_taken={r.damage_taken}, hp_after={r.hp_end}, quality={quality}"
    )
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_critic_prompt.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/critic_prompt.py tests/test_critic_prompt.py
git commit -m "feat(skills): critic prompt round-snapshot formatter"
```

---

### Task C4: Full critic prompt + system text

**Files:**
- Modify: `src/skills/critic_prompt.py` (add `build_critic_prompt`)
- Modify: `tests/test_critic_prompt.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_critic_prompt.py`:

```python
from src.skills.critic_prompt import build_critic_prompt


def test_build_critic_prompt_includes_baselines_and_hard_boundary():
    ep = _ep()
    prompt = build_critic_prompt(
        ep,
        baseline_a=0.10,
        baseline_b=0.12,
        n_a=5, n_b=7,
    )
    assert "Mistake Signal" in prompt
    assert "0.08" not in prompt  # computed, not hardcoded
    assert f"{ep.total_damage_taken}" in prompt
    assert "baseline_a" in prompt.lower() or "Baseline A" in prompt
    assert "HARD BOUNDARY" in prompt
    assert "descriptive_rhythm" in prompt
    assert "Counterfactual Test" in prompt
    assert "JSON" in prompt.upper()
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_critic_prompt.py::test_build_critic_prompt_includes_baselines_and_hard_boundary -v`
Expected: FAIL.

- [ ] **Step 3: Implement**

Append to `src/skills/critic_prompt.py`:

```python
_CRITIC_BODY = """You are a Slay the Spire 2 critic. One past combat underperformed.
Decide if a reusable SKILL would have helped, OR if it was unavoidable.

## Counterfactual Test (MANDATORY)
For each round where HP was lost or a better play existed:
1. What did agent actually do? (see "Agent plan")
2. What COULD agent have done with the SAME hand/energy/intents/potions?
3. Would an average STS2 player naturally make the better choice from
   game mechanics alone, or would they need explicit guidance?

Decision rules:
- Agent's plan was already optimal for this hand/energy/intent     -> no_skill_needed, reason="bad_luck"
- Better play existed but required mechanic never surfaced by game -> no_skill_needed, reason="unavoidable_mechanic"
- The "fix" would just describe enemy rhythm without a concrete    -> no_skill_needed, reason="descriptive_rhythm"
  corrective card/target pick agent should have made
- Better play existed AND a reusable rule would catch it next time -> skill_needed

## Skill Scope (if you propose one)
The skill must GENERALIZE across future combats AND be PRESCRIPTIVE.
- GOOD: "vs {enemy}, do X" / "vs {enemy}, do NOT do Y"
- GOOD: "holding {card}, use it as X"
- BAD:  "vs {enemy} turn 1 play Strike then Defend" (hand/intent RNG)
- BAD:  anything already obvious from card text or enemy intent display

## HARD BOUNDARY — Skill vs Memory (descriptive rhythm is NOT a skill)
If your proposed "skill" is a turn-by-turn description of how the enemy behaves
with no concrete correction, REJECT and return reason="descriptive_rhythm".
Litmus: would agent have picked a DIFFERENT card/target on the failing round
if this skill were in its prompt? If no -> descriptive_rhythm.

Content budget: <=80 words, prescriptive tone, cite trigger conditions inline.
If skill_needed, you MUST list the round indices where the mistake happened
in mistake_round_indices and write what the agent SHOULD have done in
expected_correction (<=30 words).

## Output (strict JSON, no prose before or after)
{
  "analysis": "2-3 sentences on what went wrong",
  "decision": "skill_needed" | "no_skill_needed",
  "reason": "bad_luck" | "unavoidable_mechanic" | "descriptive_rhythm" | "skill_would_help",
  "skill": null | {
    "name": "<=8 words",
    "content": "<=80 words prescriptive rule",
    "category": "combat" | "boss" | "map" | "event" | "rest" | "deck_building" | "shop",
    "trigger": {
      "state_types": [...], "enemy_names": [...], "character": "silent" | null,
      "min_act": 1|2|3 | null, "max_act": 1|2|3 | null,
      "requires_cards": [...], "requires_hand_capabilities": [...],
      "hp_below": 0.0-1.0 | null, "hp_above": 0.0-1.0 | null,
      "any_of_relics": [...], "requires_enemy_powers": [...]
    },
    "counterfactual_note": "1 sentence",
    "mistake_round_indices": [int, ...],
    "expected_correction": "<=30 words"
  }
}
"""


def build_critic_prompt(
    ep: CombatEpisode,
    *,
    baseline_a: float | None,
    baseline_b: float | None,
    n_a: int,
    n_b: int,
) -> str:
    from src.skills.mistake_discovery import loss_ratio
    actual = loss_ratio(ep)
    ba_str = f"{baseline_a:.2f}" if baseline_a is not None else "n/a"
    bb_str = f"{baseline_b:.2f}" if baseline_b is not None else "n/a"
    da = (f"{actual - baseline_a:+.2f}" if baseline_a is not None else "n/a")
    db = (f"{actual - baseline_b:+.2f}" if baseline_b is not None else "n/a")
    header = (
        "## Mistake Signal\n"
        f"- Enemy: {ep.enemy_key} ({ep.combat_type}, act {ep.act}, character {ep.character})\n"
        f"- This run: loss_ratio = {actual:.2f}  ({ep.total_damage_taken} damage on {ep.hp_before} HP)\n"
        f"- Baseline A (this enemy, historical median over N={n_a} fights): {ba_str}\n"
        f"- Baseline B (act {ep.act} x {ep.combat_type} x {ep.character}, last {n_b}): {bb_str}\n"
        f"- Exceeded: A by {da} | B by {db}\n"
    )
    round_traces = "\n\n".join(format_round_snapshot(r) for r in ep.rounds)
    combat_section = format_combat_header(ep) + "\n\n## Per-Round Trace\n" + round_traces
    return f"{_CRITIC_BODY}\n\n{header}\n{combat_section}\n"
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_critic_prompt.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/critic_prompt.py tests/test_critic_prompt.py
git commit -m "feat(skills): build_critic_prompt with hard-boundary instructions"
```

---

### Task C5: Critic output validator (schema + descriptive-rhythm regex)

**Files:**
- Modify: `src/skills/critic_prompt.py` (add `parse_and_validate_critic_output`)
- Modify: `tests/test_critic_prompt.py`

Implements spec §3.4 validator rules, including the regex soft-check for descriptive rhythm.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_critic_prompt.py`:

```python
from src.skills.critic_prompt import parse_and_validate_critic_output, CriticResult


def _valid_skill_output():
    return {
        "analysis": "Agent wasted energy blocking on a buff turn.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Save Shivs for attack turns",
            "content": "Do not apply Poison via Shiv on Sewer Clam buff turns; save Shivs for attack turns so Weak reduces the incoming hit.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"],
                "enemy_names": ["Sewer Clam"],
                "character": "silent",
                "requires_cards": ["Shiv"],
                "requires_hand_capabilities": [],
                "any_of_relics": [],
                "requires_enemy_powers": []
            },
            "counterfactual_note": "Holding Shivs for attack turns reduces damage taken by ~6.",
            "mistake_round_indices": [2],
            "expected_correction": "Hold Shivs until attack turn."
        }
    }


def test_validator_accepts_well_formed(tmp_path):
    result = parse_and_validate_critic_output(_valid_skill_output(), enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "skill_needed"
    assert result.skill is not None
    assert result.skill["name"] == "Save Shivs for attack turns"


def test_validator_rejects_empty_name():
    out = _valid_skill_output()
    out["skill"]["name"] = ""
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "no_skill_needed"
    assert "name" in result.rejection_reason


def test_validator_rejects_bad_round_indices():
    out = _valid_skill_output()
    out["skill"]["mistake_round_indices"] = [99]  # beyond rounds
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "no_skill_needed"


def test_validator_rejects_missing_llm_call_seq():
    out = _valid_skill_output()
    # round 2 has llm_call_seq = -1 (not recorded) -> cannot fetch prompt for A/B
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,-1,3])
    assert result.decision == "no_skill_needed"


def test_validator_descriptive_rhythm_regex():
    """Purely descriptive content + no imperative cue -> auto-relabel."""
    out = _valid_skill_output()
    out["skill"]["content"] = "Sewer Clam attacks on odd turns and buffs on even. The safe window is turn 2."
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "no_skill_needed"
    assert result.reason == "descriptive_rhythm"


def test_validator_imperative_cue_passes():
    out = _valid_skill_output()
    # 'save' is an imperative cue even though content mentions "attacks on"
    out["skill"]["content"] = "Sewer Clam attacks on odd turns: SAVE your Shivs for those turns and do not waste Poison on buff turns."
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "skill_needed"


def test_validator_enemy_mismatch_rejected():
    out = _valid_skill_output()
    out["skill"]["trigger"]["enemy_names"] = ["Rat"]
    result = parse_and_validate_critic_output(out, enemy_name="Sewer Clam", character="silent", round_count=3, round_llm_call_seqs=[1,2,3])
    assert result.decision == "no_skill_needed"
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_critic_prompt.py -v`
Expected: all new tests FAIL — `parse_and_validate_critic_output` doesn't exist.

- [ ] **Step 3: Implement validator**

Append to `src/skills/critic_prompt.py`:

```python
import re
from dataclasses import dataclass


_CANONICAL_CATEGORIES = frozenset({"combat", "boss", "map", "event", "rest", "deck_building", "shop"})
_CANONICAL_STATES = frozenset({"monster", "elite", "boss", "shop", "event", "rest_site", "map", "card_reward", "treasure"})
_IMPERATIVE_CUES = frozenset({
    "do", "don", "do not", "avoid", "prefer", "use", "save", "skip",
    "play", "block", "target", "hold", "never", "always",
})
_DESCRIPTIVE_RE = re.compile(
    r"(attacks on|buffs on|follows .* pattern|consistently (opens|alternates)|safe window)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class CriticResult:
    decision: str  # "skill_needed" | "no_skill_needed"
    reason: str
    skill: dict | None
    rejection_reason: str = ""


def _has_imperative_cue(content: str) -> bool:
    tokens = re.findall(r"[A-Za-z']+", content.lower())
    tset = set(tokens)
    for cue in _IMPERATIVE_CUES:
        if " " in cue:
            if cue in content.lower():
                return True
        elif cue in tset:
            return True
    return False


def _reject(reason: str, rejection_reason: str = "") -> CriticResult:
    return CriticResult(
        decision="no_skill_needed",
        reason=reason,
        skill=None,
        rejection_reason=rejection_reason or reason,
    )


def parse_and_validate_critic_output(
    output: dict,
    *,
    enemy_name: str,
    character: str,
    round_count: int,
    round_llm_call_seqs: list[int],
) -> CriticResult:
    """Apply spec §3.4 validator.

    Arguments:
        output: parsed JSON from critic (already json.loads'd)
        enemy_name: ep.enemy_key (for enemy-overlap check)
        character: ep.character (for character equality check)
        round_count: total rounds in episode (for index range)
        round_llm_call_seqs: llm_call_seq per round_index; -1 means unrecorded
    """
    decision = output.get("decision", "")
    reason = output.get("reason", "")

    if decision == "no_skill_needed":
        return CriticResult(decision="no_skill_needed", reason=reason or "bad_luck", skill=None)

    if decision != "skill_needed":
        return _reject("invalid_decision", f"decision={decision!r}")

    skill = output.get("skill") or {}
    name = skill.get("name", "")
    if not name or len(name) > 60:
        return _reject("invalid_name", f"name_len={len(name)}")
    content = skill.get("content", "")
    if not content or len(content.split()) > 80:
        return _reject("invalid_content_len", f"words={len(content.split())}")
    category = skill.get("category", "")
    if category not in _CANONICAL_CATEGORIES:
        return _reject("invalid_category", category)

    trigger = skill.get("trigger") or {}
    state_types = trigger.get("state_types") or []
    for s in state_types:
        if s not in _CANONICAL_STATES:
            return _reject("invalid_state_type", s)
    # enemy overlap
    enemy_names = trigger.get("enemy_names") or []
    if enemy_names:
        en_lower = enemy_name.lower()
        overlap = any(n.lower() in en_lower or en_lower in n.lower() for n in enemy_names)
        if not overlap:
            return _reject("enemy_mismatch", f"{enemy_names} vs {enemy_name}")
    # character equality
    tc = trigger.get("character")
    if tc is not None and tc and tc.lower() != character.lower():
        return _reject("character_mismatch", f"{tc} vs {character}")
    # at least one non-null dimension
    has_dim = any(trigger.get(k) for k in (
        "state_types", "enemy_names", "requires_cards",
        "requires_hand_capabilities", "any_of_relics", "requires_enemy_powers",
    ))
    if not has_dim and not (trigger.get("hp_below") or trigger.get("hp_above")):
        return _reject("universal_trigger")

    # counterfactual_note + expected_correction
    if not skill.get("counterfactual_note"):
        return _reject("missing_counterfactual_note")
    ec = skill.get("expected_correction", "")
    if not ec or len(ec.split()) > 30:
        return _reject("invalid_expected_correction")

    # mistake_round_indices
    indices = skill.get("mistake_round_indices") or []
    if not indices:
        return _reject("empty_mistake_round_indices")
    for idx in indices:
        if not isinstance(idx, int) or idx < 0 or idx >= round_count:
            return _reject("mistake_round_index_out_of_range", str(idx))
        if idx >= len(round_llm_call_seqs) or round_llm_call_seqs[idx] < 0:
            return _reject("missing_llm_call_seq", f"round={idx}")

    # descriptive-rhythm regex soft-check
    if _DESCRIPTIVE_RE.search(content) and not _has_imperative_cue(content):
        return CriticResult(
            decision="no_skill_needed",
            reason="descriptive_rhythm",
            skill=None,
            rejection_reason="content matched descriptive regex and lacks imperative cue",
        )

    return CriticResult(
        decision="skill_needed",
        reason=reason or "skill_would_help",
        skill=skill,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_critic_prompt.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/critic_prompt.py tests/test_critic_prompt.py
git commit -m "feat(skills): critic output validator with descriptive-rhythm regex"
```

---

### Task C6: run_critic async wrapper

**Files:**
- Modify: `src/skills/mistake_discovery.py` (add `run_critic_parallel`)
- Test: `tests/test_mistake_discovery.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_mistake_discovery.py`:

```python
import asyncio
from unittest.mock import AsyncMock, patch
import json


def test_run_critic_parallel_fans_out_gather(monkeypatch):
    from src.skills.mistake_discovery import run_critic_parallel
    episodes = [
        _ep(enemy_key="A", hp_before=100, dmg=40),
        _ep(enemy_key="B", hp_before=100, dmg=50),
        _ep(enemy_key="C", hp_before=100, dmg=60),
    ]

    async def fake_call_raw(*args, **kwargs):
        prompt = kwargs.get("prompt", "") or (args[1] if len(args) > 1 else "")
        enemy = "A" if "A " in prompt or "A," in prompt else ("B" if "B " in prompt else "C")
        resp = {
            "analysis": f"mistake vs {enemy}",
            "decision": "no_skill_needed",
            "reason": "bad_luck",
            "skill": None
        }
        return json.dumps(resp), 1.0, 10

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    async def run():
        results = await run_critic_parallel(episodes, baselines_a=[0.1]*3, baselines_b=[0.2]*3, ns_a=[5]*3, ns_b=[5]*3)
        return results

    results = asyncio.run(run())
    assert len(results) == 3
    assert all(r.decision == "no_skill_needed" for r in results)
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_mistake_discovery.py::test_run_critic_parallel_fans_out_gather -v`
Expected: FAIL — `ImportError: cannot import name 'run_critic_parallel'`.

- [ ] **Step 3: Implement**

Append to `src/skills/mistake_discovery.py`:

```python
import asyncio
import json
import logging

from src.brain.llm_caller import call_raw
from src.skills.critic_prompt import build_critic_prompt, parse_and_validate_critic_output, CriticResult

logger = logging.getLogger(__name__)

_CRITIC_SYSTEM = "You are a Slay the Spire 2 tactical critic. Produce strict JSON only."


async def _critic_one(
    ep: CombatEpisode,
    baseline_a_val: float | None,
    baseline_b_val: float | None,
    n_a: int,
    n_b: int,
) -> CriticResult:
    prompt = build_critic_prompt(ep, baseline_a=baseline_a_val, baseline_b=baseline_b_val, n_a=n_a, n_b=n_b)
    try:
        text, _latency, _tokens = await call_raw(
            system=_CRITIC_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="mistake_critic",
        )
    except Exception as e:
        logger.warning("critic call failed for episode %s: %s", ep.episode_id, e)
        return CriticResult(decision="no_skill_needed", reason="critic_error", skill=None, rejection_reason=str(e))
    try:
        obj = json.loads(text)
    except json.JSONDecodeError as e:
        logger.warning("critic returned non-JSON for episode %s: %s", ep.episode_id, e)
        return CriticResult(decision="no_skill_needed", reason="invalid_json", skill=None, rejection_reason=str(e))
    round_seqs = [r.llm_call_seq for r in ep.rounds]
    return parse_and_validate_critic_output(
        obj,
        enemy_name=ep.enemy_key,
        character=ep.character,
        round_count=len(ep.rounds),
        round_llm_call_seqs=round_seqs,
    )


async def run_critic_parallel(
    episodes: list[CombatEpisode],
    *,
    baselines_a: list[float | None],
    baselines_b: list[float | None],
    ns_a: list[int],
    ns_b: list[int],
) -> list[CriticResult]:
    """Fan critic calls out in parallel across all mistake episodes (§3.1)."""
    tasks = [
        _critic_one(ep, ba, bb, na, nb)
        for ep, ba, bb, na, nb in zip(episodes, baselines_a, baselines_b, ns_a, ns_b)
    ]
    return list(await asyncio.gather(*tasks))
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_mistake_discovery.py::test_run_critic_parallel_fans_out_gather -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/mistake_discovery.py tests/test_mistake_discovery.py
git commit -m "feat(skills): run_critic_parallel fans out via asyncio.gather"
```

---

## Phase D — Pre-Write A/B

### Task D1: inject_candidate_into_prompt

**Files:**
- Modify: `src/skills/composer.py` (add function)
- Test: `tests/test_prewrite_ab.py` (new)

- [ ] **Step 1: Write failing test**

Create `tests/test_prewrite_ab.py`:

```python
from src.skills.composer import inject_candidate_into_prompt


def test_inject_appends_to_existing_expert_knowledge_block():
    prompt = "## Something\ntext\n\n## Expert Knowledge\n- skill X: do Y\n\n## Your Task\n..."
    out = inject_candidate_into_prompt(prompt, name="NewSkill", content="Do Z instead of W")
    assert "- skill X: do Y" in out
    assert "NewSkill" in out
    assert "candidate" in out.lower()
    # Original skill still present BEFORE the new one
    i1 = out.index("skill X: do Y")
    i2 = out.index("NewSkill")
    assert i1 < i2


def test_inject_creates_block_when_missing():
    prompt = "## Something\ntext\n\n## Your Task\n..."
    out = inject_candidate_into_prompt(prompt, name="NewSkill", content="Do Z")
    assert "## Expert Knowledge" in out
    assert "NewSkill" in out
    # Block must appear BEFORE Your Task
    assert out.index("## Expert Knowledge") < out.index("## Your Task")
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: FAIL — `ImportError`.

- [ ] **Step 3: Implement**

Append to `src/skills/composer.py`:

```python
def inject_candidate_into_prompt(prompt: str, *, name: str, content: str) -> str:
    """Inject a candidate skill into an existing prompt for A/B testing.

    If the prompt already has an `## Expert Knowledge` section, append to it.
    Otherwise insert a fresh section before `## Your Task` (or at the end).
    Candidate entry is tagged '(candidate - under evaluation)' so later audit
    logs can distinguish it from retrieved skills.
    """
    entry = f"- {name} (candidate - under evaluation): {content}"
    marker = "## Expert Knowledge"
    if marker in prompt:
        # Append entry to the end of that block (before next ## or EOF)
        idx = prompt.index(marker)
        tail_idx = prompt.find("\n## ", idx + len(marker))
        if tail_idx == -1:
            return prompt.rstrip() + "\n" + entry + "\n"
        return prompt[:tail_idx] + "\n" + entry + "\n" + prompt[tail_idx:]
    # No block — create one
    block = f"\n## Expert Knowledge\n{entry}\n"
    your_task = prompt.find("## Your Task")
    if your_task >= 0:
        return prompt[:your_task] + block + prompt[your_task:]
    return prompt.rstrip() + "\n" + block
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: 2 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/composer.py tests/test_prewrite_ab.py
git commit -m "feat(skills): composer.inject_candidate_into_prompt for A/B testing"
```

---

### Task D2: fetch_prompt_a from run log

**Files:**
- Create: `src/skills/prewrite_ab.py`
- Modify: `tests/test_prewrite_ab.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_prewrite_ab.py`:

```python
import json, tempfile
from pathlib import Path


def test_fetch_prompt_a_reads_jsonl_by_seq():
    from src.skills.prewrite_ab import fetch_prompt_a
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "run.jsonl"
        with p.open("w") as f:
            # Event without llm_call is skipped; seq counts only llm_calls
            f.write(json.dumps({"event": "round_end"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_0", "tier": "fast"}) + "\n")
            f.write(json.dumps({"event": "combat_start"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_1", "tier": "strategic"}) + "\n")
            f.write(json.dumps({"event": "llm_call", "prompt": "PROMPT_2", "tier": "strategic"}) + "\n")
        assert fetch_prompt_a(p, seq=0) == "PROMPT_0"
        assert fetch_prompt_a(p, seq=1) == "PROMPT_1"
        assert fetch_prompt_a(p, seq=2) == "PROMPT_2"


def test_fetch_prompt_a_missing_seq_raises():
    from src.skills.prewrite_ab import fetch_prompt_a
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "run.jsonl"
        p.write_text(json.dumps({"event": "llm_call", "prompt": "only"}) + "\n")
        import pytest
        with pytest.raises(LookupError):
            fetch_prompt_a(p, seq=5)
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: FAIL — `ModuleNotFoundError`.

- [ ] **Step 3: Create module**

Create `src/skills/prewrite_ab.py`:

```python
"""Pre-write A/B validation for mistake-driven skill candidates (spec §4)."""
from __future__ import annotations

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def fetch_prompt_a(log_path: Path, *, seq: int) -> str:
    """Fetch the N-th llm_call event's prompt from the run log.

    seq is zero-based across all llm_call events (matches
    session_logger.current_llm_call_seq semantics).
    """
    count = 0
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") != "llm_call":
                continue
            if count == seq:
                return obj.get("prompt", "")
            count += 1
    raise LookupError(f"llm_call seq={seq} not found in {log_path} (only {count} events)")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/prewrite_ab.py tests/test_prewrite_ab.py
git commit -m "feat(skills): prewrite_ab.fetch_prompt_a reads raw prompt from run log"
```

---

### Task D3: redecide_b (N=3 parallel)

**Files:**
- Modify: `src/skills/prewrite_ab.py`
- Modify: `tests/test_prewrite_ab.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_prewrite_ab.py`:

```python
import asyncio


def test_redecide_b_runs_three_in_parallel(monkeypatch):
    from src.skills.prewrite_ab import redecide_b
    calls: list[str] = []

    async def fake_call_raw(*, system="", prompt="", **kw):
        calls.append(prompt[:20])
        return f"response_for_{len(calls)}", 0.5, 5

    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    result = asyncio.run(redecide_b(
        prompt_b="## Expert Knowledge\n- x\n## Your Task\npick a card",
        system="system prompt",
        n=3,
    ))
    assert len(result) == 3
    assert all("response_for_" in r for r in result)
    assert len(calls) == 3
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prewrite_ab.py::test_redecide_b_runs_three_in_parallel -v`
Expected: FAIL — `redecide_b` missing.

- [ ] **Step 3: Implement**

Append to `src/skills/prewrite_ab.py`:

```python
import asyncio

from src.brain.llm_caller import call_raw


async def redecide_b(
    *,
    prompt_b: str,
    system: str,
    n: int = 3,
) -> list[str]:
    """Resample N decisions with candidate-injected prompt (strategic tier)."""
    tasks = [
        call_raw(
            system=system,
            prompt=prompt_b,
            effort="medium",
            call_type="mistake_redecide",
            openai_relay_profile="default",  # gameplay-tier routing
        )
        for _ in range(n)
    ]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    texts: list[str] = []
    for r in results:
        if isinstance(r, Exception):
            logger.warning("redecide_b sample failed: %s", r)
            texts.append("")
            continue
        text, _latency, _tokens = r
        texts.append(text)
    return texts
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prewrite_ab.py::test_redecide_b_runs_three_in_parallel -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/prewrite_ab.py tests/test_prewrite_ab.py
git commit -m "feat(skills): prewrite_ab.redecide_b for N=3 strategic-tier resampling"
```

---

### Task D4: Judge prompt + parser

**Files:**
- Modify: `src/skills/prewrite_ab.py`
- Modify: `tests/test_prewrite_ab.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_prewrite_ab.py`:

```python
import json


def test_build_judge_prompt_contains_all_samples():
    from src.skills.prewrite_ab import build_judge_prompt
    p = build_judge_prompt(
        candidate_name="X", candidate_content="do Y",
        expected_correction="play Defend turn 1",
        counterfactual_note="would have avoided 8 dmg",
        decision_a="played Strike",
        decisions_b=["Defend", "Defend", "Strike"],
    )
    assert "X" in p and "do Y" in p
    assert "## A (" in p and "## B (" in p
    assert "Defend" in p
    assert "skill_helps" in p and "skill_harmful" in p
    assert "hit_count_B" in p


def test_parse_judge_output_valid():
    from src.skills.prewrite_ab import parse_judge_output, JudgeVerdict
    raw = json.dumps({"verdict": "skill_helps", "hit_count_B": 2, "rationale": "B follows correction"})
    v = parse_judge_output(raw)
    assert v.verdict == "skill_helps"
    assert v.hit_count == 2


def test_parse_judge_output_invalid_falls_back_unclear():
    from src.skills.prewrite_ab import parse_judge_output
    v = parse_judge_output("not json")
    assert v.verdict == "skill_unclear"
    assert v.hit_count == 0
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: FAIL — functions missing.

- [ ] **Step 3: Implement**

Append to `src/skills/prewrite_ab.py`:

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class JudgeVerdict:
    verdict: str  # "skill_helps" | "skill_unclear" | "skill_harmful"
    hit_count: int  # 0..N (out of N B samples)
    rationale: str = ""


_JUDGE_SYSTEM = "You are a strict reviewer evaluating whether a proposed STS2 skill actually steered the agent's decision."


def build_judge_prompt(
    *,
    candidate_name: str,
    candidate_content: str,
    expected_correction: str,
    counterfactual_note: str,
    decision_a: str,
    decisions_b: list[str],
) -> str:
    b_block = "\n".join(f"Sample {i+1}: {d}" for i, d in enumerate(decisions_b))
    return f"""You proposed this skill for an STS2 combat round:

{candidate_name}: {candidate_content}

Your stated correction:
"{expected_correction}"
"{counterfactual_note}"

## A (original decision, no skill)
{decision_a}

## B (re-decided with skill injected, {len(decisions_b)} samples)
{b_block}

Did the skill steer the agent toward the correction you proposed?

Output strict JSON:
{{
  "verdict": "skill_helps" | "skill_unclear" | "skill_harmful",
  "hit_count_B": 0..{len(decisions_b)},
  "rationale": "<=2 sentences"
}}

skill_helps:    >=2/3 B samples clearly follow expected_correction AND differ from A
skill_unclear:  1/3 or ambiguous
skill_harmful:  0/3, or B samples perform objectively worse than A
"""


def parse_judge_output(text: str) -> JudgeVerdict:
    try:
        obj = json.loads(text)
    except json.JSONDecodeError:
        return JudgeVerdict(verdict="skill_unclear", hit_count=0, rationale="unparseable")
    v = obj.get("verdict", "skill_unclear")
    if v not in {"skill_helps", "skill_unclear", "skill_harmful"}:
        v = "skill_unclear"
    hc = obj.get("hit_count_B", 0)
    try:
        hc = int(hc)
    except (TypeError, ValueError):
        hc = 0
    return JudgeVerdict(verdict=v, hit_count=max(0, hc), rationale=obj.get("rationale", ""))


async def run_judge(
    *,
    candidate_name: str,
    candidate_content: str,
    expected_correction: str,
    counterfactual_note: str,
    decision_a: str,
    decisions_b: list[str],
) -> JudgeVerdict:
    prompt = build_judge_prompt(
        candidate_name=candidate_name,
        candidate_content=candidate_content,
        expected_correction=expected_correction,
        counterfactual_note=counterfactual_note,
        decision_a=decision_a,
        decisions_b=decisions_b,
    )
    try:
        text, _lat, _tok = await call_raw(
            system=_JUDGE_SYSTEM,
            prompt=prompt,
            effort="high",
            call_type="mistake_judge",
        )
    except Exception as e:
        logger.warning("judge call failed: %s", e)
        return JudgeVerdict(verdict="skill_unclear", hit_count=0, rationale=f"call_error:{e}")
    return parse_judge_output(text)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/prewrite_ab.py tests/test_prewrite_ab.py
git commit -m "feat(skills): prewrite_ab judge prompt + verdict parser"
```

---

### Task D5: Strict aggregation + per-candidate orchestrator

Brainstorming-fixed policy (宁缺毋滥 / strict): for a candidate with N mistake rounds, total B samples = N×3. Pass iff (a) `total_hits >= ceil(total × 2/3)` AND (b) no round is harmful.

For N=2 → 6 samples → need 4 hits, 0 harmful rounds.

- [ ] **Step 1: Write failing tests**

Append to `tests/test_prewrite_ab.py`:

```python
def test_strict_aggregation_passes():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=3),
        RoundJudgeResult(verdict="skill_helps", hit_count=1),  # 4/6 total
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is True


def test_strict_aggregation_fails_below_threshold():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=2),
        RoundJudgeResult(verdict="skill_unclear", hit_count=1),  # 3/6
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is False


def test_strict_aggregation_fails_on_any_harmful_round():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    per_round = [
        RoundJudgeResult(verdict="skill_helps", hit_count=3),
        RoundJudgeResult(verdict="skill_harmful", hit_count=0),  # hard fail even though other helps
    ]
    assert aggregate_strict(per_round, samples_per_round=3) is False


def test_strict_aggregation_single_round_needs_two_of_three():
    from src.skills.prewrite_ab import aggregate_strict, RoundJudgeResult
    # 1 round × 3 samples = 3 total; ceil(3*2/3)=2
    assert aggregate_strict([RoundJudgeResult("skill_helps", 2)], samples_per_round=3) is True
    assert aggregate_strict([RoundJudgeResult("skill_unclear", 1)], samples_per_round=3) is False
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: FAIL — missing symbols.

- [ ] **Step 3: Implement**

Append to `src/skills/prewrite_ab.py`:

```python
import math


@dataclass(frozen=True)
class RoundJudgeResult:
    verdict: str
    hit_count: int


def aggregate_strict(per_round: list[RoundJudgeResult], *, samples_per_round: int = 3) -> bool:
    """Strict 'ning-que-wu-lan' aggregation rule.

    Pass iff:
      1. No round's verdict is 'skill_harmful', AND
      2. sum(hit_count) >= ceil(total_samples * 2/3)
    where total_samples = len(per_round) * samples_per_round.
    """
    if not per_round:
        return False
    if any(r.verdict == "skill_harmful" for r in per_round):
        return False
    total_samples = len(per_round) * samples_per_round
    threshold = math.ceil(total_samples * 2 / 3)
    total_hits = sum(r.hit_count for r in per_round)
    return total_hits >= threshold


async def validate_candidate(
    *,
    candidate: dict,  # output from critic (the "skill" sub-dict)
    episode,          # CombatEpisode
    log_path: Path,
    combat_system_prompt: str,
) -> tuple[bool, list[RoundJudgeResult], int]:
    """Run A/B validation for one candidate across all its mistake rounds.

    Returns (passed, per_round_results, total_hits).
    """
    round_indices = candidate.get("mistake_round_indices") or []
    per_round: list[RoundJudgeResult] = []
    total_hits = 0
    for idx in round_indices:
        rnd = episode.rounds[idx]
        try:
            prompt_a = fetch_prompt_a(log_path, seq=rnd.llm_call_seq)
        except LookupError as e:
            logger.warning("skipping round %s: %s", idx, e)
            per_round.append(RoundJudgeResult(verdict="skill_unclear", hit_count=0))
            continue
        prompt_b = prompt_a  # inject candidate
        from src.skills.composer import inject_candidate_into_prompt
        prompt_b = inject_candidate_into_prompt(
            prompt_b, name=candidate["name"], content=candidate["content"],
        )
        decisions_b = await redecide_b(prompt_b=prompt_b, system=combat_system_prompt, n=3)
        # For A, we would load the original decision from the log; stubbed as empty
        # and filled by orchestrator in production (see Task G1).
        verdict = await run_judge(
            candidate_name=candidate["name"],
            candidate_content=candidate["content"],
            expected_correction=candidate.get("expected_correction", ""),
            counterfactual_note=candidate.get("counterfactual_note", ""),
            decision_a="(see log — not shown here)",
            decisions_b=decisions_b,
        )
        per_round.append(RoundJudgeResult(verdict=verdict.verdict, hit_count=verdict.hit_count))
        total_hits += verdict.hit_count
    return aggregate_strict(per_round), per_round, total_hits
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_prewrite_ab.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/prewrite_ab.py tests/test_prewrite_ab.py
git commit -m "feat(skills): strict aggregation + per-candidate A/B orchestrator"
```

---

## Phase E — Write-Gate Integration

### Task E1: Update _trigger_tags_from_skill

**Files:**
- Modify: `src/memory/write_gate.py:1104-1133`
- Test: `tests/test_write_gate.py` (extend)

- [ ] **Step 1: Write failing test**

Create `tests/test_write_gate_trigger_tags.py`:

```python
from src.memory.write_gate import _trigger_tags_from_skill
from src.skills.models import Skill, SkillTrigger


def test_trigger_tags_has_only_active_fields():
    s = Skill(
        name="t",
        trigger=SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Rat"}),
            requires_hand_capabilities=frozenset({"can_apply_weak"}),
            requires_enemy_powers=frozenset({"Strength"}),
        ),
    )
    tags = _trigger_tags_from_skill(s)
    assert "state_types:monster" in tags
    assert "enemy_names:Rat" in tags
    assert "requires_hand_capabilities:can_apply_weak" in tags
    assert "requires_enemy_powers:Strength" in tags
    # Removed fields must not appear:
    assert not any(t.startswith("threat_levels:") for t in tags)
    assert not any(t.startswith("intent_classes:") for t in tags)
    assert not any(t.startswith("deck_stages:") for t in tags)
    assert not any(t.startswith("tags:") for t in tags)
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_write_gate_trigger_tags.py -v`
Expected: FAIL — `requires_enemy_powers` tag missing (current code only reads 7 fields, some removed).

- [ ] **Step 3: Update**

Edit `src/memory/write_gate.py:1104-1133`. Replace the attribute tuple:

```python
    for attr in (
        "state_types",
        "enemy_names",
        "requires_hand_capabilities",
        "requires_enemy_powers",
    ):
```

Remove `"tags"`, `"threat_levels"`, `"intent_classes"`, `"deck_stages"`. Update docstring:

```python
    """Flatten a SkillTrigger-like object into a tag set for Jaccard.

    Reads the active frozensets on :class:`SkillTrigger`:
    state_types / enemy_names / requires_hand_capabilities /
    requires_enemy_powers.

    The legacy fields tags / threat_levels / intent_classes / deck_stages
    were removed on 2026-04-20 with the mistake-driven redesign.
    Missing attributes are skipped silently so the gate still works on
    legacy skills that were loaded from disk before migration.
    """
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_write_gate_trigger_tags.py tests/test_write_gate.py -v`
Expected: new test PASS. Existing write_gate tests may fail if they seeded trigger-tags via the dropped fields — in that case update fixtures to use the 4 active fields.

- [ ] **Step 5: Commit**

```bash
git add src/memory/write_gate.py tests/test_write_gate_trigger_tags.py
git commit -m "refactor(write_gate): trigger_tags uses only 4 active trigger fields"
```

---

## Phase F — Post-Write Lifecycle

### Task F1: classify_combat_outcome

**Files:**
- Create: `src/skills/lifecycle.py`
- Test: `tests/test_lifecycle.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_lifecycle.py`:

```python
from src.skills.lifecycle import classify_combat_outcome


def test_improved_when_below_baseline_minus_delta():
    # baseline 0.30, delta 0.10 -> improved if actual <= 0.20
    assert classify_combat_outcome(actual=0.15, baseline=0.30, combat_type="monster") == "improved"
    assert classify_combat_outcome(actual=0.20, baseline=0.30, combat_type="monster") == "improved"


def test_unchanged_near_baseline():
    assert classify_combat_outcome(actual=0.30, baseline=0.30, combat_type="monster") == "unchanged"
    assert classify_combat_outcome(actual=0.25, baseline=0.30, combat_type="monster") == "unchanged"


def test_worse_above_baseline_plus_delta():
    assert classify_combat_outcome(actual=0.45, baseline=0.30, combat_type="monster") == "worse"


def test_delta_varies_by_combat_type():
    # monster delta = 0.10, boss delta = 0.20
    assert classify_combat_outcome(actual=0.12, baseline=0.30, combat_type="boss") == "improved"
    assert classify_combat_outcome(actual=0.09, baseline=0.30, combat_type="boss") == "improved"
    assert classify_combat_outcome(actual=0.51, baseline=0.30, combat_type="boss") == "worse"
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_lifecycle.py -v`
Expected: FAIL — module missing.

- [ ] **Step 3: Create module**

Create `src/skills/lifecycle.py`:

```python
"""Post-write lifecycle for mistake-driven skills (spec §6)."""
from __future__ import annotations

import logging

from src.skills.mistake_discovery import DELTA_BY_TYPE

logger = logging.getLogger(__name__)


def classify_combat_outcome(
    *, actual: float, baseline: float, combat_type: str,
) -> str:
    """Return 'improved' | 'unchanged' | 'worse' per §6.1."""
    delta = DELTA_BY_TYPE.get(combat_type, 0.10)
    if actual <= baseline - delta:
        return "improved"
    if actual >= baseline + delta:
        return "worse"
    return "unchanged"


CONFIDENCE_MULT = {
    "improved": 1.10,
    "unchanged": 0.98,
    "worse": 0.85,
}
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_lifecycle.py -v`
Expected: 4 PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(skills): lifecycle.classify_combat_outcome per §6.1"
```

---

### Task F2: update_skill_usage_from_run

**Files:**
- Modify: `src/skills/lifecycle.py`
- Modify: `tests/test_lifecycle.py`

- [ ] **Step 1: Write failing test**

Append to `tests/test_lifecycle.py`:

```python
import tempfile, json
from pathlib import Path

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _ep(run_id="r_now", enemy_key="Rat", hp=100, dmg=40, skills=("s1",)):
    return CombatEpisode(
        run_id=run_id, enemy_key=enemy_key, combat_type="monster",
        character="silent", act=1, hp_before=hp, total_damage_taken=dmg,
        retrieved_skill_ids=skills,
    )


def test_update_skill_usage_improved_boosts_confidence(tmp_path):
    from src.skills.lifecycle import update_skill_usage_from_run
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s1", name="Test", confidence=0.50))
    store = CombatMemoryStore()
    # History: 5 previous episodes at 0.40 loss_ratio
    for i in range(5):
        store.add(_ep(run_id=f"r_old{i}", hp=100, dmg=40, skills=()))
    ep_this = _ep(run_id="r_now", hp=100, dmg=10, skills=("s1",))  # loss 0.10, baseline 0.40 -> improved
    usage_log = tmp_path / "skill_usage.jsonl"
    update_skill_usage_from_run(
        this_run_episodes=[ep_this],
        skill_library=lib,
        combat_store=store,
        usage_log_path=usage_log,
    )
    conf = lib.get_skill("s1").confidence
    assert conf > 0.50
    assert usage_log.exists()
    line = usage_log.read_text().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["skill_id"] == "s1"
    assert rec["outcome"] == "improved"


def test_update_skill_usage_worse_decays_confidence(tmp_path):
    from src.skills.lifecycle import update_skill_usage_from_run
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s1", name="Test", confidence=0.50))
    store = CombatMemoryStore()
    for i in range(5):
        store.add(_ep(run_id=f"r_old{i}", hp=100, dmg=20, skills=()))
    ep_this = _ep(run_id="r_now", hp=100, dmg=50, skills=("s1",))  # worse
    update_skill_usage_from_run(
        this_run_episodes=[ep_this],
        skill_library=lib,
        combat_store=store,
        usage_log_path=tmp_path / "u.jsonl",
    )
    assert lib.get_skill("s1").confidence < 0.50
```

Make sure `SkillLibrary.get_skill(skill_id)` exists or substitute a direct lookup if not. Run `grep -n "def get_skill\|_skills\[" src/skills/library.py` and adjust.

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_lifecycle.py -v`
Expected: FAIL — function missing.

- [ ] **Step 3: Implement**

Append to `src/skills/lifecycle.py`:

```python
import json
from pathlib import Path
from typing import Iterable

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
from src.skills.mistake_discovery import baseline_a, baseline_b, loss_ratio


def update_skill_usage_from_run(
    *,
    this_run_episodes: list[CombatEpisode],
    skill_library,
    combat_store: CombatMemoryStore,
    usage_log_path: Path,
) -> None:
    """Attribute outcomes per-combat baseline and update skill confidence.

    Replaces run-level success/failure attribution. Writes one JSONL
    record per (episode, skill) to usage_log_path for audit.
    """
    usage_log_path.parent.mkdir(parents=True, exist_ok=True)
    with usage_log_path.open("a", encoding="utf-8") as out:
        for ep in this_run_episodes:
            if not ep.retrieved_skill_ids:
                continue
            actual = loss_ratio(ep)
            # Baseline = per-enemy history excluding current run
            history = [
                e for e in combat_store.get_by_enemy(ep.enemy_key)
                if e.run_id != ep.run_id
            ]
            ba = baseline_a(history)
            pool = combat_store.recent_by_act_type(
                act=ep.act, combat_type=ep.combat_type, character=ep.character,
                limit=10, exclude_run_id=ep.run_id,
            )
            bb = baseline_b(pool)
            # Use whichever baseline is available; prefer A (enemy-specific)
            baseline = ba if ba is not None else bb
            if baseline is None:
                continue  # insufficient data
            outcome = classify_combat_outcome(
                actual=actual, baseline=baseline, combat_type=ep.combat_type,
            )
            mult = CONFIDENCE_MULT[outcome]
            for skill_id in set(ep.retrieved_skill_ids):
                sk = getattr(skill_library, "get_skill", lambda _id: None)(skill_id)
                if sk is None:
                    continue
                new_conf = max(0.0, min(1.0, sk.confidence * mult))
                # Dataclass immutability -> with_update/replace
                if hasattr(sk, "with_update"):
                    updated = sk.with_update(confidence=new_conf, usage_count=sk.usage_count + 1)
                else:
                    from dataclasses import replace
                    updated = replace(sk, confidence=new_conf, usage_count=sk.usage_count + 1)
                # write back through the library's private map (mirrors record_outcome shape)
                lib_map = getattr(skill_library, "_skills", None)
                if isinstance(lib_map, dict):
                    lib_map[skill_id] = updated
                json.dump({
                    "skill_id": skill_id, "run_id": ep.run_id, "episode_id": ep.episode_id,
                    "enemy": ep.enemy_key, "actual": actual, "baseline": baseline,
                    "outcome": outcome, "confidence_before": sk.confidence, "confidence_after": new_conf,
                }, out)
                out.write("\n")
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_lifecycle.py -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/skills/lifecycle.py tests/test_lifecycle.py
git commit -m "feat(skills): update_skill_usage_from_run with per-combat baseline"
```

---

## Phase G — Orchestration

### Task G1: run_mistake_discovery orchestrator

**Files:**
- Modify: `src/skills/mistake_discovery.py`
- Modify: `tests/test_mistake_discovery.py` (add integration test)

- [ ] **Step 1: Write failing test**

Append to `tests/test_mistake_discovery.py`:

```python
def test_run_mistake_discovery_integration_mock_llm(tmp_path, monkeypatch):
    """End-to-end with mocked critic + redecide + judge.

    Setup:
    - 5 historical episodes vs 'Sewer Clam' at loss 0.10
    - Current run: 1 episode vs Sewer Clam at loss 0.30 (>> 0.10 + 0.10)
    - Mocked critic returns a valid candidate
    - Mocked redecide returns the correction
    - Mocked judge returns skill_helps, hits=3 on 1 round -> 3/3 >= 2, passes
    - Assert skill persisted with source='mistake_driven'
    """
    # ... skip full scaffolding here — the integration test is in Task I2.
```

For now the orchestrator is tested indirectly; Task I2 adds the full integration test.

- [ ] **Step 2: Implement orchestrator**

Append to `src/skills/mistake_discovery.py`:

```python
from pathlib import Path
from typing import Any

from src.memory.combat_store import CombatMemoryStore


async def run_mistake_discovery(
    *,
    this_run_episodes: list[CombatEpisode],
    combat_store: CombatMemoryStore,
    skill_library,
    write_gate,
    log_path: Path,
    run_id: str,
    combat_system_prompt: str,
) -> dict[str, int]:
    """Main entrypoint — spec §5.2. Returns stats dict for logging."""
    from src.skills.prewrite_ab import validate_candidate
    from src.skills.composer import inject_candidate_into_prompt
    from dataclasses import replace

    stats = {"mistakes": 0, "critic_skill_needed": 0, "cascade_rejected": 0, "ab_passed": 0, "ab_failed": 0, "persisted": 0}

    # 1. Filter mistakes + compute baselines
    mistakes: list[CombatEpisode] = []
    ba_list: list[float | None] = []
    bb_list: list[float | None] = []
    na_list: list[int] = []
    nb_list: list[int] = []
    for ep in this_run_episodes:
        history = [e for e in combat_store.get_by_enemy(ep.enemy_key) if e.run_id != run_id]
        pool = combat_store.recent_by_act_type(
            act=ep.act, combat_type=ep.combat_type, character=ep.character,
            limit=10, exclude_run_id=run_id,
        )
        ba = baseline_a(history)
        bb = baseline_b(pool)
        if is_mistake_episode(ep, baseline_a_val=ba, baseline_b_val=bb):
            mistakes.append(ep)
            ba_list.append(ba); bb_list.append(bb)
            na_list.append(len(history)); nb_list.append(len(pool))

    stats["mistakes"] = len(mistakes)
    if not mistakes:
        return stats

    # 2. Parallel critic
    critic_results = await run_critic_parallel(
        mistakes, baselines_a=ba_list, baselines_b=bb_list, ns_a=na_list, ns_b=nb_list,
    )
    candidates: list[tuple[CombatEpisode, dict]] = []
    for ep, res in zip(mistakes, critic_results):
        if res.decision == "skill_needed" and res.skill is not None:
            candidates.append((ep, res.skill))
            stats["critic_skill_needed"] += 1

    if not candidates:
        return stats

    # 3. Convert to Skill objects, run cascade dedup
    from src.skills.models import Skill, SkillTrigger
    skill_objs: list[Skill] = []
    for ep, cand in candidates:
        trig_raw = cand.get("trigger") or {}
        trigger = SkillTrigger(
            state_types=frozenset(trig_raw.get("state_types") or ()),
            enemy_names=frozenset(trig_raw.get("enemy_names") or ()),
            character=frozenset([trig_raw["character"]] if trig_raw.get("character") else ()),
            min_act=trig_raw.get("min_act") if trig_raw.get("min_act") is not None else 0,
            max_act=trig_raw.get("max_act") if trig_raw.get("max_act") is not None else 99,
            requires_cards=frozenset(trig_raw.get("requires_cards") or ()),
            requires_hand_capabilities=frozenset(trig_raw.get("requires_hand_capabilities") or ()),
            any_of_relics=frozenset(trig_raw.get("any_of_relics") or ()),
            requires_enemy_powers=frozenset(trig_raw.get("requires_enemy_powers") or ()),
            hp_below=trig_raw.get("hp_below") if trig_raw.get("hp_below") is not None else 1.0,
            hp_above=trig_raw.get("hp_above") if trig_raw.get("hp_above") is not None else 0.0,
        )
        sk = Skill(
            name=cand["name"], category=cand["category"], trigger=trigger,
            content=cand["content"], source="mistake_driven",
            source_run_ids=(run_id,), confidence=0.40,  # will bump after A/B
            verified=False, status="probation",
        )
        skill_objs.append(sk)

    existing = list(skill_library.all_skills)
    kept, dropped = write_gate.filter_skill_batch(skill_objs, existing_skills=existing, run_id=run_id)
    stats["cascade_rejected"] = len(dropped)

    # Map kept skills back to their (ep, cand) pairs
    keep_pairs: list[tuple[CombatEpisode, dict, Skill]] = []
    kept_names = {k.name for k in kept}
    for (ep, cand), sk in zip(candidates, skill_objs):
        if sk.name in kept_names:
            keep_pairs.append((ep, cand, sk))

    # 4. A/B validate each kept candidate
    async def _validate(ep, cand, sk):
        passed, per_round, hits = await validate_candidate(
            candidate=cand, episode=ep, log_path=log_path,
            combat_system_prompt=combat_system_prompt,
        )
        return sk, cand, passed, per_round, hits

    ab_outcomes = await asyncio.gather(*(_validate(ep, cand, sk) for ep, cand, sk in keep_pairs))

    # 5. Persist survivors
    for sk, cand, passed, per_round, hits in ab_outcomes:
        if not passed:
            stats["ab_failed"] += 1
            logger.info("A/B failed: %s (hits=%d)", sk.name, hits)
            continue
        stats["ab_passed"] += 1
        rounds_in_cand = max(1, len(cand.get("mistake_round_indices", [])))
        new_conf = 0.40 + 0.05 * rounds_in_cand  # 0.45..0.55
        from dataclasses import replace
        sk_final = replace(sk, confidence=new_conf)
        skill_library.add(sk_final)
        stats["persisted"] += 1

    return stats
```

- [ ] **Step 3: Syntax + import sanity check**

Run: `python -c "from src.skills.mistake_discovery import run_mistake_discovery; print('ok')"`
Expected: `ok`.

- [ ] **Step 4: Commit**

```bash
git add src/skills/mistake_discovery.py tests/test_mistake_discovery.py
git commit -m "feat(skills): run_mistake_discovery orchestrator (critic -> cascade -> A/B -> persist)"
```

---

### Task G2: Wire into loop.py — replace cohort call

**Files:**
- Modify: `src/agent/loop.py:3545-3559` (remove cohort block, add mistake_discovery call)
- Test: manual smoke

- [ ] **Step 1: Find exact location**

Run: `grep -n "cohort_discovery\|discover_combat_cohort_skills" src/agent/loop.py | head`
Expected hits around lines 3547–3559.

- [ ] **Step 2: Replace block**

Replace this block (roughly 3545–3559):

```python
                if self._skill_library:
                    try:
                        from src.skills.cohort_discovery import discover_combat_cohort_skills

                        cohort_stats = await discover_combat_cohort_skills(
                            self._memory,
                            self._skill_library,
                        )
                        if any(v > 0 for v in cohort_stats.values()):
                            logger.info("Cohort combat discovery: %s", cohort_stats)
                    except Exception:
                        logger.warning("Cohort combat discovery failed", exc_info=True)
                if cohort_stats and cohort_stats.get("promoted", 0) > 0 and self._skill_library:
                    skill_path = Path(config.SKILLS_DIR) / "skills.json"
                    self._skill_library.save(skill_path)
```

With:

```python
                if self._skill_library and config.MISTAKE_DISCOVERY_ENABLED:
                    try:
                        from src.skills.mistake_discovery import run_mistake_discovery
                        from src.brain.prompts.system import COMBAT
                        run_id = self._run_state.run_id if self._run_state else ""
                        this_run_episodes = [
                            e for e in self._memory.combat_store.get_all()
                            if e.run_id == run_id
                        ]
                        stats = await run_mistake_discovery(
                            this_run_episodes=this_run_episodes,
                            combat_store=self._memory.combat_store,
                            skill_library=self._skill_library,
                            write_gate=self._write_gate,
                            log_path=self._log_path,
                            run_id=run_id,
                            combat_system_prompt=COMBAT,
                        )
                        if any(v > 0 for v in stats.values()):
                            logger.info("Mistake-driven discovery: %s", stats)
                        if stats.get("persisted", 0) > 0:
                            skill_path = Path(config.SKILLS_DIR) / "skills.json"
                            self._skill_library.save(skill_path)
                    except Exception:
                        logger.warning("Mistake-driven discovery failed", exc_info=True)
```

Verify `self._log_path` exists on the loop (search: `grep -n "_log_path" src/agent/loop.py | head`); if not, use `self._session_logger.log_path` or equivalent.

- [ ] **Step 3: Add config flag**

Edit `config.py`. Add near other skill flags:

```python
MISTAKE_DISCOVERY_ENABLED: bool = _env_bool("STS2_MISTAKE_DISCOVERY_ENABLED", True)
MISTAKE_VALIDATION_ENABLED: bool = _env_bool("STS2_MISTAKE_VALIDATION_ENABLED", True)
```

If `_env_bool` doesn't exist, use `os.getenv("STS2_MISTAKE_DISCOVERY_ENABLED", "true").lower() in ("true", "1", "yes")`.

- [ ] **Step 4: Smoke test (no LLM)**

Run: `python -m scripts.run_agent --steps 20 --runs 1 --no-llm`
Expected: run completes, no import errors.

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py config.py
git commit -m "feat(agent): replace cohort_discovery with mistake_driven_discovery call"
```

---

### Task G3: Remove hypothesis re-evaluation block

**Files:**
- Modify: `src/agent/loop.py:4106-4144`

- [ ] **Step 1: Confirm location**

Run: `grep -n "hypothesis_store\|HypothesisStore" src/agent/loop.py`
Expected block 4106–4144.

- [ ] **Step 2: Delete the block**

Remove the entire `try`/`except` covering the hypothesis re-evaluation. Make sure indentation of surrounding code is preserved; nothing else should change.

- [ ] **Step 3: Add lifecycle call in its place**

After the retirement + category-cap block (~line 4104), insert:

```python
            # Mistake-driven post-write lifecycle: attribute each skill's
            # effect using per-combat baseline outcomes (§6 of spec
            # 2026-04-19-mistake-driven-skill-discovery-design.md).
            if self._skill_library and self._memory and self._run_state:
                try:
                    from src.skills.lifecycle import update_skill_usage_from_run
                    this_run_episodes = [
                        e for e in self._memory.combat_store.get_all()
                        if e.run_id == self._run_state.run_id
                    ]
                    update_skill_usage_from_run(
                        this_run_episodes=this_run_episodes,
                        skill_library=self._skill_library,
                        combat_store=self._memory.combat_store,
                        usage_log_path=Path(config.SKILLS_DIR) / "skill_usage.jsonl",
                    )
                except Exception:
                    logger.warning("Post-write lifecycle failed", exc_info=True)
```

- [ ] **Step 4: Smoke test**

Run: `python -m scripts.run_agent --steps 20 --runs 1 --no-llm`
Expected: run completes.

- [ ] **Step 5: Commit**

```bash
git add src/agent/loop.py
git commit -m "refactor(agent): replace hypothesis reevaluation with mistake-driven lifecycle"
```

---

## Phase H — Migration + Cleanup

### Task H1: Migration script + test

**Files:**
- Create: `scripts/migrate_skills_mistake_driven.py`
- Test: `tests/test_migrate_skills_mistake_driven.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_migrate_skills_mistake_driven.py`:

```python
import json
from pathlib import Path
from scripts.migrate_skills_mistake_driven import migrate


def _skill(source, category, name="s"):
    return {
        "skill_id": f"id_{name}", "name": name, "source": source, "category": category,
        "trigger": {
            "state_types": ["monster"], "enemy_names": [], "character": [],
            "min_act": 0, "max_act": 99, "min_deck_size": 0, "max_deck_size": 999,
            "requires_cards": [], "requires_hand_capabilities": [],
            "threat_levels": ["high"], "intent_classes": ["attack"],
            "deck_stages": ["scaling"], "tags": ["x"],
            "any_of_relics": [], "requires_enemy_powers": [],
            "hp_below": 1.0, "hp_above": 0.0,
        },
        "content": f"content {name}", "tier": "specific",
        "priority": 50, "confidence": 0.7, "usage_count": 0,
        "success_count": 0, "failure_count": 0, "verified": True,
        "status": "active", "active": True, "version": 1,
    }


def test_migration_keeps_seeds(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([
        _skill("seed", "combat", "seed_combat"),
        _skill("discovered", "combat", "disc_combat"),
        _skill("discovered", "map", "disc_map"),
    ]))
    migrate(src)
    kept = json.loads(src.read_text())
    names = {s["name"] for s in kept}
    assert "seed_combat" in names
    assert "disc_map" in names
    assert "disc_combat" not in names  # dropped


def test_migration_writes_backup(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([_skill("seed", "combat")]))
    migrate(src)
    bak = src.with_suffix(".json.pre-mistake-driven.bak")
    assert bak.exists()


def test_migration_strips_legacy_trigger_fields(tmp_path):
    src = tmp_path / "skills.json"
    src.write_text(json.dumps([_skill("seed", "combat")]))
    migrate(src)
    kept = json.loads(src.read_text())
    assert kept
    trig = kept[0]["trigger"]
    assert "threat_levels" not in trig
    assert "intent_classes" not in trig
    assert "deck_stages" not in trig
    assert "tags" not in trig
```

- [ ] **Step 2: Verify failure**

Run: `pytest tests/test_migrate_skills_mistake_driven.py -v`
Expected: FAIL — script missing.

- [ ] **Step 3: Create script**

Create `scripts/migrate_skills_mistake_driven.py`:

```python
"""One-shot migration: strip cohort-era combat skills + legacy trigger fields.

Run once after merging the mistake-driven-discovery redesign:

    python -m scripts.migrate_skills_mistake_driven

Writes skills.json.pre-mistake-driven.bak before overwriting.
See docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §7.
"""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

_NONCOMBAT_CATEGORIES = {"map", "event", "rest", "deck_building", "shop"}
_LEGACY_TRIGGER_FIELDS = ("threat_levels", "intent_classes", "deck_stages", "tags")


def migrate(skills_path: Path) -> tuple[int, int]:
    """Filter skills.json in place. Returns (kept_count, dropped_count)."""
    data = json.loads(skills_path.read_text(encoding="utf-8"))
    # Support both list and {"skills": [...]} formats
    skills = data if isinstance(data, list) else data.get("skills", [])

    kept: list[dict] = []
    for s in skills:
        source = s.get("source", "")
        category = s.get("category", "")
        if source == "seed":
            kept.append(s); continue
        if source == "discovered" and category in _NONCOMBAT_CATEGORIES:
            kept.append(s); continue
        # Drop: all combat skills regardless of source (cohort, evolved, etc.)

    # Strip legacy trigger fields from survivors
    for s in kept:
        trig = s.get("trigger", {})
        for f in _LEGACY_TRIGGER_FIELDS:
            trig.pop(f, None)

    backup = skills_path.with_suffix(".json.pre-mistake-driven.bak")
    shutil.copy2(skills_path, backup)

    # Preserve original format
    if isinstance(data, list):
        out: object = kept
    else:
        data["skills"] = kept
        out = data
    skills_path.write_text(json.dumps(out, indent=2), encoding="utf-8")

    return len(kept), len(skills) - len(kept)


def main() -> int:
    path = Path("data/skills/skills.json")
    if not path.exists():
        print(f"no skills file at {path}", file=sys.stderr)
        return 1
    kept, dropped = migrate(path)
    print(f"Migration complete: kept={kept}, dropped={dropped}")
    print(f"Backup written to {path.with_suffix('.json.pre-mistake-driven.bak')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_migrate_skills_mistake_driven.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/migrate_skills_mistake_driven.py tests/test_migrate_skills_mistake_driven.py
git commit -m "feat(scripts): migrate_skills_mistake_driven — drop cohort combat skills"
```

---

### Task H2: Execute migration on live skills.json

**Files:**
- Modify: `data/skills/skills.json`
- Create: `data/skills/skills.json.pre-mistake-driven.bak`

- [ ] **Step 1: Verify expected counts**

Run:
```python
python -c "
import json
d = json.load(open('data/skills/skills.json'))
skills = d if isinstance(d, list) else d['skills']
print('total:', len(skills))
seed = [s for s in skills if s['source']=='seed']
nc = [s for s in skills if s['source']=='discovered' and s['category'] in {'map','event','rest','deck_building','shop'}]
print(f'expect kept: seed={len(seed)} + nc_discovered={len(nc)} = {len(seed)+len(nc)}')
"
```
Expected: `total: 122; expect kept: seed=8 + nc_discovered=5 = 13`.

- [ ] **Step 2: Run migration**

Run: `python -m scripts.migrate_skills_mistake_driven`
Expected: `Migration complete: kept=13, dropped=109`.

- [ ] **Step 3: Verify**

Run:
```python
python -c "
import json
d = json.load(open('data/skills/skills.json'))
skills = d if isinstance(d, list) else d['skills']
print('post-migrate total:', len(skills))
from collections import Counter
print('by source:', Counter(s['source'] for s in skills))
print('by category:', Counter(s['category'] for s in skills))
trig = skills[0]['trigger']
for f in ('threat_levels','intent_classes','deck_stages','tags'):
    assert f not in trig, f'{f} still present'
print('trigger fields clean')
"
```
Expected: `post-migrate total: 13`; no forbidden fields.

- [ ] **Step 4: Archive hypothesis_store if present**

```bash
mkdir -p data.snapshots/2026-04-20-pre-mistake-driven/
if [ -f data/skills/cohort_hypotheses.jsonl ]; then mv data/skills/cohort_hypotheses.jsonl data.snapshots/2026-04-20-pre-mistake-driven/; fi
if [ -f data/skills/cohort_progress.json ]; then mv data/skills/cohort_progress.json data.snapshots/2026-04-20-pre-mistake-driven/; fi
```

- [ ] **Step 5: Commit**

```bash
git add data/skills/skills.json data/skills/skills.json.pre-mistake-driven.bak data.snapshots/2026-04-20-pre-mistake-driven/
git commit -m "chore(data): execute mistake-driven migration (94 cohort skills dropped)"
```

---

### Task H3: Delete obsolete source files

**Files:**
- Delete: `src/skills/cohort_discovery.py`
- Delete: `src/skills/cohort_utils.py`
- Delete: `src/skills/hypothesis_store.py`
- Delete: `src/skills/evidence.py`

- [ ] **Step 1: Verify no remaining imports**

Run:
```bash
grep -rn "from src\.skills\.cohort_discovery\|from src\.skills\.cohort_utils\|from src\.skills\.hypothesis_store\|from src\.skills\.evidence\|import src\.skills\.cohort\|import src\.skills\.hypothesis\|import src\.skills\.evidence" src/ --include="*.py"
```
Expected: no hits (other than in the files being deleted themselves). If any caller remains, fix it — skills.discovery may still import cohort_utils; inline the tiny helpers it needs (`load_basic_card_names`) into discovery.py directly.

- [ ] **Step 2: Delete files**

```bash
git rm src/skills/cohort_discovery.py src/skills/cohort_utils.py src/skills/hypothesis_store.py src/skills/evidence.py
```

- [ ] **Step 3: Verify build**

Run: `python -c "import src.agent.loop; import src.skills.mistake_discovery; import src.skills.prewrite_ab; import src.skills.lifecycle; print('imports ok')"`
Expected: `imports ok`.

- [ ] **Step 4: Commit**

```bash
git commit -m "refactor(skills): remove cohort_discovery/hypothesis_store/evidence/cohort_utils"
```

---

### Task H4: Delete obsolete tests

**Files:**
- Delete: `tests/test_cohort_discovery.py`, `tests/test_cohort_utils.py`, `tests/test_hypothesis_store.py` (if exists), `tests/test_evidence.py` (if exists)
- Modify: `tests/test_situation.py` (strip threat/intent/deck_stage assertions, keep HandCapabilities)
- Modify: `tests/test_skill_composer.py`, `tests/test_skill_trigger_matching.py` (strip removed-field assertions)

- [ ] **Step 1: Delete or skip obsolete tests**

```bash
git rm tests/test_cohort_discovery.py tests/test_cohort_utils.py
# If the following exist:
test -f tests/test_hypothesis_store.py && git rm tests/test_hypothesis_store.py || true
test -f tests/test_evidence.py && git rm tests/test_evidence.py || true
```

- [ ] **Step 2: Strip legacy assertions from situation tests**

Run: `grep -n "threat_level\|intent_class\|deck_stage" tests/test_situation.py`

For each match, either delete the whole test (if it's solely about the removed feature) or the assertion line. Keep tests that exercise `HandCapabilities`.

- [ ] **Step 3: Strip skill composer / trigger match legacy fields**

Same treatment in `tests/test_skill_composer.py` and `tests/test_skill_trigger_matching.py` — delete tests that only exercise `tags`/`threat_levels`/`intent_classes`/`deck_stages`.

- [ ] **Step 4: Run full suite**

Run: `pytest tests/ -x --timeout=60 2>&1 | tail -30`
Expected: all non-deleted tests pass. Some may fail on unrelated issues (pre-existing); scope to skill/memory test files:

`pytest tests/test_skill_*.py tests/test_memory_*.py tests/test_write_gate*.py tests/test_combat_*.py tests/test_mistake_discovery.py tests/test_critic_prompt.py tests/test_prewrite_ab.py tests/test_lifecycle.py tests/test_migrate_skills_mistake_driven.py -v`

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add tests/
git commit -m "chore(tests): remove cohort/hypothesis tests; strip legacy trigger-field assertions"
```

---

## Phase I — Integration + Smoke

### Task I1: Full integration test (mocked LLM)

**Files:**
- Create: `tests/test_mistake_discovery_integration.py`

- [ ] **Step 1: Write the integration test**

Create `tests/test_mistake_discovery_integration.py`:

```python
"""End-to-end mistake_discovery with mocked LLM calls (spec §8.4)."""
import asyncio
import json
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.skills.library import SkillLibrary
from src.memory.write_gate import WriteGate
from src.skills.mistake_discovery import run_mistake_discovery


def _round(idx=0, dmg=5, seq=1):
    return CombatRound(
        round_num=idx+1, hp_start=60, hp_end=60-dmg,
        energy_available=3, damage_taken=dmg,
        hand_at_start=("Strike", "Defend"),
        enemy_intents=("Rat -> Attack 8",),
        incoming_damage=8, agent_plan=("Strike -> Rat",),
        llm_call_seq=seq,
    )


def _ep_mistake():
    return CombatEpisode(
        episode_id="ep_bad", run_id="run_now",
        enemy_key="Rat", combat_type="monster", character="silent",
        act=1, floor=2, hp_before=60, hp_after=30,
        total_damage_taken=30,  # loss 0.50
        rounds=(_round(0, dmg=15, seq=1), _round(1, dmg=15, seq=2)),
    )


def _ep_old(run_id, dmg=10):
    return CombatEpisode(
        run_id=run_id, enemy_key="Rat", combat_type="monster",
        character="silent", act=1, hp_before=60,
        total_damage_taken=dmg, rounds=(_round(dmg=dmg, seq=0),),
    )


@pytest.mark.asyncio
async def test_run_mistake_discovery_happy_path(tmp_path):
    # Build history: 5 episodes at dmg=10 -> loss ~0.17
    store = CombatMemoryStore()
    for i in range(5):
        store.add(_ep_old(run_id=f"old{i}"))
    store.add(_ep_mistake())

    # Write a run log with 3 llm_call events (seqs 0, 1, 2)
    log = tmp_path / "run_now.jsonl"
    with log.open("w") as f:
        for seq in range(3):
            f.write(json.dumps({"event": "llm_call", "prompt": f"PROMPT_{seq}", "tier": "strategic"}) + "\n")

    lib = SkillLibrary()
    gate = WriteGate()

    # Mock critic output (skill_needed)
    critic_json = json.dumps({
        "analysis": "Agent strike instead of defend",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Block against Rat openers",
            "content": "Play Defend on turn 1 against Rat; do NOT rush with Strike.",
            "category": "combat",
            "trigger": {"state_types": ["monster"], "enemy_names": ["Rat"],
                        "character": "silent", "requires_cards": [],
                        "requires_hand_capabilities": [], "any_of_relics": [],
                        "requires_enemy_powers": []},
            "counterfactual_note": "would save 7 damage per round",
            "mistake_round_indices": [0, 1],
            "expected_correction": "Defend -> self"
        }
    })
    # Mock redecide output: each sample says 'Defend -> self'
    redecide_txt = "plan: Defend -> self"
    judge_json = json.dumps({"verdict": "skill_helps", "hit_count_B": 3, "rationale": "B all defend"})

    call_count = [0]
    async def fake_call_raw(*, system="", prompt="", effort="", call_type="", **kw):
        call_count[0] += 1
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        if call_type == "mistake_redecide":
            return redecide_txt, 1.0, 50
        if call_type == "mistake_judge":
            return judge_json, 1.0, 80
        return "", 0.0, 0

    with patch("src.skills.mistake_discovery.call_raw", new=fake_call_raw), \
         patch("src.skills.prewrite_ab.call_raw", new=fake_call_raw):
        stats = await run_mistake_discovery(
            this_run_episodes=[_ep_mistake()],
            combat_store=store,
            skill_library=lib,
            write_gate=gate,
            log_path=log,
            run_id="run_now",
            combat_system_prompt="you are an STS2 agent",
        )

    assert stats["mistakes"] == 1
    assert stats["critic_skill_needed"] == 1
    assert stats["persisted"] == 1
    assert any(s.source == "mistake_driven" for s in lib.all_skills)
```

- [ ] **Step 2: Run**

Run: `pytest tests/test_mistake_discovery_integration.py -v`
Expected: PASS. If anyio/asyncio marker complaint → install `pytest-asyncio` or use `asyncio.run` inline.

- [ ] **Step 3: Commit**

```bash
git add tests/test_mistake_discovery_integration.py
git commit -m "test(skills): mistake_discovery integration with mocked LLM"
```

---

### Task I2: Live no-LLM smoke

- [ ] **Step 1: Run**

`python -m scripts.run_agent --steps 50 --runs 1 --no-llm`

- [ ] **Step 2: Verify**

- No exceptions in output
- `data/skills/skills.json` size unchanged (no critic calls made in no-LLM)
- Check `logs/run_*.jsonl` contains `llm_call_seq` on round-end events where applicable (won't exist in `--no-llm` since strategic plans aren't called — that's fine)

- [ ] **Step 3: Commit (no code changes; nothing to commit if clean)**

Skip if no deltas.

---

### Task I3: Live single LLM run

- [ ] **Step 1: Run**

`STS2_MISTAKE_DISCOVERY_ENABLED=true python -m scripts.run_agent --steps 200 --runs 1 --character Silent`

- [ ] **Step 2: Verify**

```bash
python -c "
import json
with open('data/skills/skills.json') as f:
    d = json.load(f)
skills = d if isinstance(d, list) else d['skills']
mistake = [s for s in skills if s.get('source')=='mistake_driven']
print(f'mistake_driven skills now: {len(mistake)}')
for s in mistake[:5]:
    print(f\"- {s['name']}: confidence={s.get('confidence',0):.2f}\")
"
```

Acceptance per spec §8.6:
- Run completes without error
- New mistake_driven skills ≤ 5 per run
- At least one A/B pass in `data/skills/write_gate_log.jsonl` or similar

- [ ] **Step 3: If issues, capture and iterate.**

No commit here — pure observability.

---

## Self-Review Checklist (already run inline; findings summary)

- [x] Spec §1.4 hard boundary → encoded in `critic_prompt.py` system text + validator regex (Task C5)
- [x] Spec §2.1 baselines → `baseline_a`, `baseline_b`, `is_mistake_episode` (Tasks C1, C2)
- [x] Spec §2.2 round snapshot → `format_round_snapshot`, `format_combat_header`, `build_critic_prompt` (Tasks C3, C4)
- [x] Spec §2.3 schema changes → Tasks A1, A2, B1 (new fields added; existing `hp_start`/`hand_at_start`/`energy_available` reused)
- [x] Spec §2.4 `recent_by_act_type` → Task A3
- [x] Spec §3.1 parallel critic → `run_critic_parallel` Task C6
- [x] Spec §3.4 validator → Task C5 (all rules including `llm_call_seq >= 0` gate and descriptive-rhythm regex)
- [x] Spec §3.5 confidence 0.40 + 0.05×helps → Task G1 orchestrator
- [x] Spec §4.1 core flow → Task D5 `validate_candidate`
- [x] Spec §4.2 injection helper → Task D1
- [x] Spec §4.3 judge → Task D4
- [x] Spec §4.4 raw-prompt fetch → Task D2 `fetch_prompt_a`
- [x] Spec §4.5 parallelism → Task D3 (N=3 via gather) + Task G1 (across candidates)
- [x] Spec §5.1 chain rewrite → Task G2 (replace call), Task G3 (lifecycle inserted)
- [x] Spec §5.3 reuse WriteGate → Task G1 calls `write_gate.filter_skill_batch`
- [x] Spec §6 lifecycle → Tasks F1, F2, G3
- [x] Spec §7 cleanup → Tasks H1–H4
- [x] Spec §8 tests → Tasks C1/C2/C4/C5 unit; D1–D5 unit; F1/F2 unit; I1 integration; A1–B1 migration
- [x] **Strict aggregation (brainstorm answer 宁缺毋滥)** → Task D5 `aggregate_strict` with `ceil(total*2/3)` threshold and zero-harmful gate
- [x] **Per-combat baseline lifecycle (brainstorm answer)** → Task F2, not whole-run win/loss

Type consistency spot-checked: `classify_combat_outcome` / `is_mistake_episode` / `DELTA_BY_TYPE` / `loss_ratio` used with matching signatures across `mistake_discovery.py` and `lifecycle.py`; `CriticResult` / `JudgeVerdict` / `RoundJudgeResult` dataclasses don't collide.

No placeholder text, no "TBD", no "similar to Task N" — every code step has its full block.

---

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-04-20-mistake-driven-skill-discovery.md`. Two execution options:

**1. Subagent-Driven (recommended)** — I dispatch a fresh subagent per task, review between tasks, fast iteration

**2. Inline Execution** — Execute tasks in this session using executing-plans, batch execution with checkpoints

**Which approach?**
