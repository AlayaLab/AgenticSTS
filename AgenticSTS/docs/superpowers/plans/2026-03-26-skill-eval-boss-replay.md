# Skill Eval Boss Replay — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A/B test skill sets during boss fights using STS2's save/load, precisely detecting kill/death mid-plan to trigger replays without ending the combat.

**Architecture:** Hooks into existing `_execute_combat_plan` in `loop.py` for per-card kill/death detection. Uses `save_and_quit`/`continue_run` to replay the same boss fight with swapped skill sets. `replay_evaluator.py` provides data structures and confidence computation; `loop.py` owns the flow. `library.py` gains explicit `set_active_override`/`clear_active_override` for cross-round skill injection.

**Tech Stack:** Python 3.12, httpx (MCP client), existing agent loop infrastructure

---

### Task 1: Add `set_active_override` / `clear_active_override` to SkillLibrary

**Files:**
- Modify: `AgenticSTS\src\skills\library.py:180-188`
- Test: `AgenticSTS\tests\test_skill_library_override.py`

Currently `library.py` only has `temporary_override` (context manager). For eval mode we need explicit set/clear because the override persists across multiple combat rounds and save/load cycles.

- [ ] **Step 1: Write failing test**

```python
# tests/test_skill_library_override.py
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger

def _make_lib():
    lib = SkillLibrary.__new__(SkillLibrary)
    lib._skills = {}
    lib._active_override = None
    s1 = Skill(skill_id="s1", name="S1", category="combat",
               content="test", trigger=SkillTrigger())
    s2 = Skill(skill_id="s2", name="S2", category="combat",
               content="test2", trigger=SkillTrigger())
    lib._skills = {"s1": s1, "s2": s2}
    return lib

def test_set_active_override():
    lib = _make_lib()
    assert lib._active_override is None
    lib.set_active_override(["s1"])
    assert lib._active_override == {"s1"}
    results = lib.query(state_type="combat", limit=10)
    assert len(results) == 1
    assert results[0][0].skill_id == "s1"

def test_clear_active_override():
    lib = _make_lib()
    lib.set_active_override(["s1"])
    lib.clear_active_override()
    assert lib._active_override is None

def test_set_override_missing_id_ignored():
    lib = _make_lib()
    lib.set_active_override(["s1", "nonexistent"])
    results = lib.query(state_type="combat", limit=10)
    assert len(results) == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_skill_library_override.py -v`
Expected: FAIL — `AttributeError: 'SkillLibrary' object has no attribute 'set_active_override'`

- [ ] **Step 3: Implement `set_active_override` and `clear_active_override`**

In `src/skills/library.py`, after the `temporary_override` context manager (~line 188):

```python
def set_active_override(self, skill_ids: list[str]) -> None:
    """Set persistent skill override for eval mode (survives across rounds)."""
    self._active_override = set(skill_ids)

def clear_active_override(self) -> None:
    """Clear persistent skill override, restoring normal query behavior."""
    self._active_override = None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_skill_library_override.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add tests/test_skill_library_override.py src/skills/library.py
git commit -m "feat(P4-L4): set/clear active override for skill eval"
```

---

### Task 2: Simplify `replay_evaluator.py` — remove dead code, keep data structures

**Files:**
- Modify: `AgenticSTS\src\skills\replay_evaluator.py`
- Test: `AgenticSTS\tests\test_replay_evaluator.py`

Remove `evaluate_boss_skills` and `_run_single_combat` (logic moves to loop.py). Keep `ReplayResult`, `compute_confidence_deltas`, and `build_alternative_sets`. Add `build_eval_schedule` that prioritizes untested skills.

- [ ] **Step 1: Write failing test**

```python
# tests/test_replay_evaluator.py
from src.skills.replay_evaluator import (
    ReplayResult,
    compute_confidence_deltas,
    build_eval_schedule,
)

def test_confidence_deltas_best_vs_worst():
    best = ReplayResult("a", ("s1", "s2", "s3"), hp_lost=5, rounds=3, potions_used=0, won=True)
    worst = ReplayResult("b", ("s1", "s4", "s5"), hp_lost=25, rounds=8, potions_used=2, won=True)
    deltas = compute_confidence_deltas([best, worst])
    # s2, s3 only in best → positive
    assert deltas.get("s2", 0) > 0
    assert deltas.get("s3", 0) > 0
    # s4, s5 only in worst → negative
    assert deltas.get("s4", 0) < 0
    assert deltas.get("s5", 0) < 0
    # s1 in both → not in deltas
    assert "s1" not in deltas

def test_confidence_deltas_same_hp():
    r1 = ReplayResult("a", ("s1",), hp_lost=10, rounds=3, potions_used=0, won=True)
    r2 = ReplayResult("b", ("s2",), hp_lost=10, rounds=3, potions_used=0, won=True)
    assert compute_confidence_deltas([r1, r2]) == {}

def test_build_eval_schedule_prioritizes_untested():
    """build_eval_schedule exists and returns list[list[str]]."""
    # Tested via integration — here just verify import and signature
    result = build_eval_schedule(
        original_skill_ids=["s1", "s2", "s3"],
        all_skills_pool=[("u1", 0), ("u2", 0), ("u3", 0)],
        max_replays=2,
    )
    assert isinstance(result, list)
    assert len(result) <= 2
    for skill_set in result:
        assert isinstance(skill_set, list)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_replay_evaluator.py -v`
Expected: FAIL — `ImportError: cannot import name 'build_eval_schedule'`

- [ ] **Step 3: Rewrite replay_evaluator.py**

```python
"""Skill eval data structures and confidence computation.

The eval flow itself is orchestrated by AgentLoop in loop.py.
This module provides ReplayResult, confidence delta computation,
and eval schedule building.
"""

from __future__ import annotations

import logging
import random
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ReplayResult:
    skill_set_id: str
    skills_used: tuple[str, ...]
    hp_lost: int
    rounds: int
    potions_used: int
    won: bool


def compute_confidence_deltas(
    results: list[ReplayResult],
) -> dict[str, float]:
    """Compare replay results, return per-skill confidence deltas.

    Skills ONLY in the best set get positive signal.
    Skills ONLY in the worst set get negative signal.
    Skills in both (shared) are unaffected.
    """
    if len(results) < 2:
        return {}
    scored = sorted(results, key=lambda r: (not r.won, r.hp_lost, r.potions_used))
    best, worst = scored[0], scored[-1]
    if best.hp_lost >= worst.hp_lost:
        return {}

    magnitude = (worst.hp_lost - best.hp_lost) / max(worst.hp_lost, 1)
    deltas: dict[str, float] = {}
    best_set = set(best.skills_used)
    worst_set = set(worst.skills_used)

    for sid in best.skills_used:
        if sid not in worst_set:
            deltas[sid] = magnitude * 0.1

    for sid in worst.skills_used:
        if sid not in best_set:
            deltas[sid] = -magnitude * 0.1

    return deltas


def build_eval_schedule(
    *,
    original_skill_ids: list[str],
    all_skills_pool: list[tuple[str, int]],  # (skill_id, usage_count)
    max_replays: int = 2,
) -> list[list[str]]:
    """Build alternative skill sets prioritizing untested skills.

    Args:
        original_skill_ids: skills injected during the original combat
        all_skills_pool: candidate skills with usage counts (pre-filtered by trigger)
        max_replays: max number of alternative sets to build

    Returns:
        List of skill ID lists, each an alternative set to test.
    """
    original_set = set(original_skill_ids)
    # Prioritize untested (usage_count == 0), then low-usage
    candidates = sorted(
        [(sid, uc) for sid, uc in all_skills_pool if sid not in original_set],
        key=lambda x: x[1],  # lowest usage first
    )
    pool = [sid for sid, _uc in candidates]

    schedule: list[list[str]] = []
    for _ in range(max_replays):
        if not pool:
            break
        swap_count = min(3, len(pool), len(original_skill_ids))
        if swap_count == 0:
            break
        swap_indices = random.sample(range(len(original_skill_ids)), swap_count)
        kept = [s for i, s in enumerate(original_skill_ids) if i not in swap_indices]
        replacements = pool[:swap_count]
        pool = pool[swap_count:]  # consume — don't re-test same skills
        schedule.append(kept + replacements)

    return schedule
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_replay_evaluator.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/replay_evaluator.py tests/test_replay_evaluator.py
git commit -m "refactor(P4-L4): simplify replay_evaluator, add build_eval_schedule"
```

---

### Task 3: Config constant + eval state fields in `loop.py`

**Files:**
- Modify: `AgenticSTS\config.py:104-105`
- Modify: `AgenticSTS\src\agent\loop.py:108-115,809-858`

- [ ] **Step 1: Add SKILL_EVAL_ENABLED to config.py**

After the existing REPLAY constants (~line 105):

```python
SKILL_EVAL_ENABLED = os.getenv("STS2_SKILL_EVAL", "false").lower() == "true"
SKILL_EVAL_MAX_REPLAYS = int(os.getenv("STS2_SKILL_EVAL_MAX_REPLAYS", "2"))
```

- [ ] **Step 2: Add eval state fields to AgentLoop.__init__**

In `loop.py` `__init__` (~line 112), after `self._combat_plan_alive`:

```python
# Skill eval mode (boss replay A/B testing)
self._skill_eval_state: str = "idle"  # "idle" | "active" | "final"
self._eval_results: list = []
self._eval_skill_sets: list[list[str]] = []
self._eval_current_index: int = 0
self._eval_original_skill_ids: list[str] = []
self._eval_combat_start_hp: int = 0
self._eval_round_count: int = 0
self._eval_potions_used: int = 0
```

- [ ] **Step 3: Add reset in reset_for_new_run**

In `reset_for_new_run` (~line 830), add:

```python
# Skill eval reset
self._skill_eval_state = "idle"
self._eval_results = []
self._eval_skill_sets = []
self._eval_current_index = 0
self._eval_original_skill_ids = []
self._eval_combat_start_hp = 0
self._eval_round_count = 0
self._eval_potions_used = 0
if self._skill_library:
    self._skill_library.clear_active_override()
```

- [ ] **Step 4: Commit**

```bash
git add config.py src/agent/loop.py
git commit -m "feat(P4-L4): eval state fields and config for boss replay"
```

---

### Task 4: Boss combat start — activate eval mode

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py:917-1008` (COMBAT_START handler)

- [ ] **Step 1: Add eval activation after combat conversation init**

In the COMBAT_START handler, after the existing combat init code (~after line 1008, the boss search task creation), add:

```python
# Skill eval: activate for boss fights with untested skills
if (config.SKILL_EVAL_ENABLED
        and combat_type == "boss"
        and self._skill_library
        and self._skill_eval_state == "idle"):
    self._try_activate_skill_eval(gs, combat_type)
```

- [ ] **Step 2: Implement `_try_activate_skill_eval`**

Add method to AgentLoop:

```python
def _try_activate_skill_eval(self, gs: "GameState", combat_type: str) -> None:
    """Check for untested skills and activate eval mode if appropriate."""
    from src.skills.replay_evaluator import build_eval_schedule

    original_ids = list(self._combat_skill_ids)
    if not original_ids:
        return

    # Build pool of candidate skills (active, trigger-matching boss context)
    boss_name = max((e.name for e in gs.enemies), key=lambda n: len(n), default="")
    all_active = [
        (s.skill_id, s.usage_count)
        for s in self._skill_library.all_skills
        if s.status == "active"
        and s.skill_id not in original_ids
        and s.trigger.matches(
            state_type=gs.state_type,
            enemy_name=boss_name,
        )[0]  # trigger must match boss context
    ]
    # Filter to those with usage_count == 0 first (untested)
    untested = [(sid, uc) for sid, uc in all_active if uc == 0]
    if not untested:
        logger.info("Skill eval: no untested skills, staying idle")
        return

    schedule = build_eval_schedule(
        original_skill_ids=original_ids,
        all_skills_pool=untested,
        max_replays=config.SKILL_EVAL_MAX_REPLAYS,
    )
    if not schedule:
        return

    self._skill_eval_state = "active"
    self._eval_results = []
    self._eval_skill_sets = schedule
    self._eval_current_index = 0
    self._eval_original_skill_ids = original_ids
    self._eval_combat_start_hp = gs.player_hp
    self._eval_round_count = 0
    self._eval_potions_used = 0
    logger.info(
        "Skill eval ACTIVATED: %d alternative sets to test (%d untested skills)",
        len(schedule),
        len(untested),
    )
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(P4-L4): activate eval mode at boss combat start"
```

---

### Task 5: Kill detection — `_remaining_plan_kills_boss`

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py`
- Test: `AgenticSTS\tests\test_kill_detection.py`

- [ ] **Step 1: Write failing test**

```python
# tests/test_kill_detection.py
"""Test kill detection logic (isolated from AgentLoop)."""
from src.skills.replay_evaluator import remaining_plan_kills_boss

class FakeCard:
    def __init__(self, name, damage=None, total_damage=None, target_previews=None):
        self.name = name
        self.damage = damage
        self.total_damage = total_damage
        self.target_previews = target_previews or []

class FakeEnemy:
    def __init__(self, index, hp, block=0, is_alive=True):
        self.index = index
        self.current_hp = hp  # matches RawCombatEnemyPayload field name
        self.hp = hp  # fallback for getattr chain
        self.block = block
        self.is_alive = is_alive

class FakePlan:
    def __init__(self, card_name, is_potion=False, target_index=None):
        self.card_name = card_name
        self.is_potion = is_potion
        self.target_index = target_index

def test_exact_kill():
    hand = [FakeCard("Strike", damage=10, total_damage=10)]
    enemies = [FakeEnemy(0, hp=10, block=0)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True

def test_not_enough_damage():
    hand = [FakeCard("Strike", damage=5, total_damage=5)]
    enemies = [FakeEnemy(0, hp=20, block=0)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is False

def test_accounts_for_block():
    hand = [FakeCard("Strike", damage=15, total_damage=15)]
    enemies = [FakeEnemy(0, hp=10, block=5)]
    remaining = [FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True

def test_potion_ignored():
    hand = [FakeCard("Strike", damage=10, total_damage=10)]
    enemies = [FakeEnemy(0, hp=5, block=0)]
    remaining = [FakePlan("Potion", is_potion=True), FakePlan("Strike", target_index=0)]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True

def test_non_attack_ignored():
    hand = [FakeCard("Defend", damage=None, total_damage=None)]
    enemies = [FakeEnemy(0, hp=5, block=0)]
    remaining = [FakePlan("Defend")]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is False
```

- [ ] **Step 2: Run test — verify failure**

Run: `python -m pytest tests/test_kill_detection.py -v`
Expected: FAIL — `ImportError: cannot import name 'remaining_plan_kills_boss'`

- [ ] **Step 3: Implement `remaining_plan_kills_boss`**

Add to `src/skills/replay_evaluator.py` (pure function, no loop.py dependency):

```python
def remaining_plan_kills_boss(
    hand: list,       # cards in current hand (game engine values)
    enemies: list,    # alive enemies
    remaining: list,  # remaining plan actions
) -> bool:
    """Check if remaining plan actions can kill all enemies.

    Uses card damage values from the game engine (already includes
    Strength, Weak, etc.). target_previews include Vulnerable.
    """
    if not enemies:
        return False

    # Build hand lookup by name (case-insensitive, handle duplicates)
    hand_by_name: dict[str, list] = {}
    for c in hand:
        key = c.name.lower().rstrip("+")
        hand_by_name.setdefault(key, []).append(c)

    total_damage = 0
    used_cards: dict[str, int] = {}  # track which copies used

    for action in remaining:
        if getattr(action, "is_potion", False):
            continue
        card_name = getattr(action, "card_name", "")
        key = card_name.lower().rstrip("+")
        copies = hand_by_name.get(key, [])
        idx = used_cards.get(key, 0)
        if idx >= len(copies):
            continue
        card = copies[idx]
        used_cards[key] = idx + 1

        if card.damage is None:
            continue

        # Check target_previews for per-target damage (Vulnerable etc.)
        target_idx = getattr(action, "target_index", None)
        if target_idx is not None and card.target_previews:
            for tp in card.target_previews:
                if tp.target_index == target_idx:
                    total_damage += tp.total_damage or tp.damage or card.total_damage or 0
                    break
            else:
                total_damage += card.total_damage or card.damage or 0
        else:
            total_damage += card.total_damage or card.damage or 0

    boss_effective_hp = sum(
        getattr(e, "current_hp", getattr(e, "hp", 0))
        + (getattr(e, "block", 0) or 0)
        for e in enemies
        if getattr(e, "is_alive", True)
    )
    return total_damage >= boss_effective_hp
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_kill_detection.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add src/skills/replay_evaluator.py tests/test_kill_detection.py
git commit -m "feat(P4-L4): precise kill detection using game engine values"
```

---

### Task 6: Hook kill/death detection into `_execute_combat_plan`

**DEPENDENCY:** Task 7 (`_handle_eval_terminal`) must be implemented BEFORE this task because the kill/death hooks call `_handle_eval_terminal`. Implement Task 7 first, then Task 6.

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py:3063-3118` (after card play, before enemy-death re-plan)

This is the core integration. After each card is played and state is polled, check if remaining plan kills the boss.

- [ ] **Step 1: Add kill detection after card play**

In `_execute_combat_plan`, after the card play at line 3064 and the action recording at line 3081, BEFORE the enemy-death re-plan check at line 3084, insert:

```python
        # ── Skill eval: precise kill detection ──
        if self._skill_eval_state == "active" and self._combat_plan:
            try:
                raw_eval = await self._client.get_state()
                gs_eval = parse_state(raw_eval)
            except Exception:
                gs_eval = None

            if gs_eval:
                from src.skills.replay_evaluator import remaining_plan_kills_boss
                remaining_actions = self._combat_plan.actions[self._combat_plan_index:]
                if remaining_plan_kills_boss(gs_eval.hand, gs_eval.enemies, remaining_actions):
                    logger.info("Skill eval: KILL DETECTED — remaining plan kills boss")
                    self._eval_round_count = current_round
                    await self._handle_eval_terminal(gs_eval, won=True)
                    return Decision(
                        floor=floor, state_type=gs.state_type, action=action,
                        reasoning="Skill eval: kill detected, save and swap",
                        source="eval",
                    )
```

- [ ] **Step 2: Add death detection before end_turn**

In `_execute_combat_plan`, at each `end_turn` call site (lines 2871, 2893), BEFORE the `end_turn` action, add:

```python
        # ── Skill eval: death detection before end_turn ──
        if self._skill_eval_state == "active":
            from src.brain.prompts._intent_fmt import compute_total_incoming
            incoming = compute_total_incoming(gs.enemies)
            player_block = gs.raw.combat.player.block if gs.raw.combat else 0
            effective_hp = gs.player_hp + player_block
            if incoming >= effective_hp:
                logger.info("Skill eval: DEATH DETECTED — incoming %d >= effective HP %d",
                           incoming, effective_hp)
                self._eval_round_count = current_round
                await self._handle_eval_terminal(gs, won=False)
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="Skill eval: death detected, save and swap",
                    source="eval",
                )
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(P4-L4): hook kill/death detection into combat plan execution"
```

---

### Task 7: Implement `_handle_eval_terminal` and `_update_eval_confidence`

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py`

- [ ] **Step 1: Implement `_handle_eval_terminal`**

```python
async def _handle_eval_terminal(self, gs: "GameState", *, won: bool) -> None:
    """Record eval result and either swap to next skill set or finish eval."""
    from src.skills.replay_evaluator import ReplayResult
    import hashlib

    # Record this replay's result
    current_skills = (
        tuple(sorted(self._eval_skill_sets[self._eval_current_index]))
        if self._eval_current_index < len(self._eval_skill_sets)
        else tuple(sorted(self._eval_original_skill_ids))
    )
    hp_lost = max(0, self._eval_combat_start_hp - gs.player_hp)
    result = ReplayResult(
        skill_set_id=hashlib.md5(str(current_skills).encode()).hexdigest()[:8],
        skills_used=current_skills,
        hp_lost=hp_lost,
        rounds=self._eval_round_count,
        potions_used=self._eval_potions_used,
        won=won,
    )
    self._eval_results.append(result)
    logger.info(
        "Skill eval result: set=%s won=%s hp_lost=%d rounds=%d",
        result.skill_set_id, won, hp_lost, self._eval_round_count,
    )

    # Save and continue
    try:
        from src.mcp_client import actions as mcp_actions
        await self._client.post_action(mcp_actions.save_and_quit())
        await asyncio.sleep(2)
        await self._client.post_action(mcp_actions.continue_run())
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning("Skill eval save/swap failed: %s — aborting eval", e)
        self._skill_eval_state = "idle"
        if self._skill_library:
            self._skill_library.clear_active_override()
        return

    # Reset combat tracking for the new replay
    self._v2_combat_conversation = None
    self._combat_plan = None
    self._combat_plan_index = 0
    self._combat_plan_round = -1
    self._v2_round_actions = []
    self._last_combat_round = -1
    self._end_turn_sent_round = -1
    self._eval_round_count = 0
    self._eval_potions_used = 0

    # Advance to next skill set
    self._eval_current_index += 1
    if self._eval_current_index < len(self._eval_skill_sets):
        next_skills = self._eval_skill_sets[self._eval_current_index]
        self._skill_library.set_active_override(next_skills)
        logger.info(
            "Skill eval: swapping to set %d/%d: %s",
            self._eval_current_index + 1, len(self._eval_skill_sets),
            next_skills,
        )
    else:
        # All alternatives tested → enter FINAL_RUN with best set
        self._skill_eval_state = "final"
        self._update_eval_confidence()
        # Apply best skill set
        if self._eval_results:
            best = min(self._eval_results, key=lambda r: (not r.won, r.hp_lost))
            self._skill_library.set_active_override(list(best.skills_used))
            logger.info("Skill eval: FINAL RUN with best set %s (hp_lost=%d)",
                       best.skill_set_id, best.hp_lost)
        else:
            self._skill_library.clear_active_override()
            self._skill_eval_state = "idle"
```

- [ ] **Step 2: Implement `_update_eval_confidence`**

```python
def _update_eval_confidence(self) -> None:
    """Update skill confidence based on all eval results."""
    from src.skills.replay_evaluator import compute_confidence_deltas

    if not self._skill_library or len(self._eval_results) < 2:
        return

    deltas = compute_confidence_deltas(self._eval_results)
    for sid, delta in deltas.items():
        success = delta > 0
        quality = abs(delta)
        self._skill_library.record_replay_outcome(sid, success=success, quality=quality)
        logger.info("Skill eval confidence: %s → %+.3f", sid, delta)
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(P4-L4): eval terminal handling with save/swap/confidence"
```

---

### Task 8: First replay records original result + Combat end cleanup

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py`

The FIRST boss combat (before any replay) uses the original skills. When kill/death is detected, we record it as the "original" result and THEN start swapping. We also need to clean up eval state at COMBAT_END.

- [ ] **Step 1: Record original result before first swap**

In `_try_activate_skill_eval`, after setting state to active, set the override to original (so the first combat uses original skills but is tracked):

The first call to `_handle_eval_terminal` already handles this because `_eval_current_index == 0` means it records with `self._eval_original_skill_ids` and then sets `_eval_current_index = 1` which loads `_eval_skill_sets[0]`.

Wait — the current code in `_handle_eval_terminal` uses `self._eval_skill_sets[self._eval_current_index]` as the current skills. For the first combat (index 0), this would be the FIRST ALTERNATIVE set, not the original. We need to handle the original separately.

Fix: track the first combat as index -1 or handle explicitly:

```python
# In _handle_eval_terminal, determine current skill set:
if not self._eval_results:
    # First result = original skills
    current_skills = tuple(sorted(self._eval_original_skill_ids))
else:
    alt_idx = self._eval_current_index
    if alt_idx < len(self._eval_skill_sets):
        current_skills = tuple(sorted(self._eval_skill_sets[alt_idx]))
    else:
        current_skills = tuple(sorted(self._eval_original_skill_ids))
```

- [ ] **Step 2: Add COMBAT_END cleanup**

In the COMBAT_END handler (~line 1001), add after existing cleanup:

```python
# Skill eval: clean up at combat end (handles normal completion in FINAL state)
if self._skill_eval_state == "final":
    logger.info("Skill eval: final run complete, returning to idle")
    self._skill_eval_state = "idle"
    if self._skill_library:
        self._skill_library.clear_active_override()
    self._eval_results = []
    self._eval_skill_sets = []
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(P4-L4): original result tracking + combat end cleanup"
```

---

### Task 9: Round counter + potion counter tracking

**Files:**
- Modify: `AgenticSTS\src\agent\loop.py`

Track rounds and potions used during eval mode for the ReplayResult.

- [ ] **Step 1: Increment round counter**

In `_execute_combat_plan`, at the round detection point (~line 2751 where `current_round` is computed), add:

```python
if self._skill_eval_state in ("active", "final"):
    if current_round > self._eval_round_count:
        self._eval_round_count = current_round
```

- [ ] **Step 2: Increment potion counter**

In the potion execution path within `_execute_combat_plan` (where `planned.is_potion` is handled), add:

```python
if self._skill_eval_state in ("active", "final"):
    self._eval_potions_used += 1
```

- [ ] **Step 3: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(P4-L4): round and potion counters for eval replay"
```

---

### Task 10: Integration test — full eval flow

**Files:**
- Test: `AgenticSTS\tests\test_skill_eval_flow.py`

This tests the state machine transitions and result recording without a live game.

- [ ] **Step 1: Write integration test**

```python
# tests/test_skill_eval_flow.py
"""Test skill eval state machine flow."""
from src.skills.replay_evaluator import (
    ReplayResult,
    compute_confidence_deltas,
    build_eval_schedule,
    remaining_plan_kills_boss,
)

def test_full_eval_flow_data():
    """Simulate a full eval: original + 2 alternatives, verify confidence."""
    original = ReplayResult("orig", ("s1", "s2", "s3"), hp_lost=20, rounds=8, potions_used=1, won=True)
    alt1 = ReplayResult("alt1", ("s1", "u1", "u2"), hp_lost=10, rounds=5, potions_used=0, won=True)
    alt2 = ReplayResult("alt2", ("s1", "u3", "u4"), hp_lost=35, rounds=12, potions_used=2, won=True)

    deltas = compute_confidence_deltas([original, alt1, alt2])
    # u1, u2 only in best (alt1) → positive
    assert deltas.get("u1", 0) > 0
    assert deltas.get("u2", 0) > 0
    # u3, u4 only in worst (alt2) → negative
    assert deltas.get("u3", 0) < 0
    assert deltas.get("u4", 0) < 0
    # s2, s3 only in original (middle) → no change
    # s1 in all → no change

def test_schedule_consumes_pool():
    """Verify pool is consumed so skills aren't retested."""
    result = build_eval_schedule(
        original_skill_ids=["s1", "s2", "s3", "s4"],
        all_skills_pool=[("u1", 0), ("u2", 0), ("u3", 0), ("u4", 0), ("u5", 0), ("u6", 0)],
        max_replays=2,
    )
    assert len(result) == 2
    # All skill IDs across both sets should be unique (no re-testing)
    all_replacements = []
    for skill_set in result:
        replacements = [s for s in skill_set if s.startswith("u")]
        all_replacements.extend(replacements)
    assert len(all_replacements) == len(set(all_replacements))

def test_kill_detection_multi_card():
    """Multiple remaining cards sum to kill."""
    class C:
        def __init__(self, n, d):
            self.name = n
            self.damage = d
            self.total_damage = d
            self.target_previews = []
    class E:
        def __init__(self, hp, block=0):
            self.index = 0
            self.current_hp = hp
            self.hp = hp
            self.block = block
            self.is_alive = True
    class A:
        def __init__(self, name):
            self.card_name = name
            self.is_potion = False
            self.target_index = 0

    hand = [C("Strike", 6), C("Strike", 6), C("Bash", 10)]
    enemies = [E(hp=20, block=0)]
    remaining = [A("Strike"), A("Strike"), A("Bash")]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True
```

- [ ] **Step 2: Run tests**

Run: `python -m pytest tests/test_skill_eval_flow.py -v`
Expected: 3 passed

- [ ] **Step 3: Commit**

```bash
git add tests/test_skill_eval_flow.py
git commit -m "test(P4-L4): integration tests for skill eval flow"
```
