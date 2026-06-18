# No-Target Replan Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent run aborts when a multi-phase boss (e.g. Subject) transitions between phases and `gs.enemies == []` while play_phase is still active, by injecting a no-target replan context to the LLM and enforcing target availability in the plan validator.

**Architecture:** Three-layer defense inside `src/agent/loop.py`: (1) per-round flag `_no_target_replan_round` gates re-entry; (2) early detection in `_execute_combat_plan` calls `_generate_combat_plan(no_target_mode=True)` which injects a fixed `replan_context` string through the existing `CombatConversation.add_round_state` channel; (3) a new rule in `_validate_combat_plan` rejects `requires_target=True` cards when no alive enemies exist, using existing truncate-or-replan semantics.

**Tech Stack:** Python 3.12, pytest, existing AgenticSTS loop/planner/conversation modules. No new dependencies.

**Design spec:** [docs/superpowers/specs/2026-04-19-no-target-replan-design.md](../specs/2026-04-19-no-target-replan-design.md)

---

## File Structure

- **Modify:** `src/agent/loop.py` — add flag + reset (3 sites), add detection branch in `_execute_combat_plan`, extend `_generate_combat_plan` signature + replan_ctx construction, extend `_validate_combat_plan` with target-availability rule
- **Create:** `tests/test_no_target_replan.py` — 8 unit tests for the new behavior
- **No changes:** `CombatConversation.add_round_state` (already accepts `replan_context` — just pass through), `prompts/*` (immutable), knowledge data, skill library

---

## Task 1: Add state flag with reset at three sites

**Files:**
- Modify: `src/agent/loop.py:252` (flag init), `src/agent/loop.py:1811`, `src/agent/loop.py:1985`, `src/agent/loop.py:2892` (resets)
- Test: `tests/test_no_target_replan.py`

- [ ] **Step 1: Write the failing test**

Create `tests/test_no_target_replan.py` with the initial test:

```python
"""No-target replan tests — multi-phase boss transition handling."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import src.agent.loop as loop_module
from src.brain.conversation import CombatConversation
from src.brain.planner import CombatPlan, PlannedAction
from src.mcp_client import actions
from src.mcp_client.upstream_models import (
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState

from tests.conftest import (
    make_combat_gs,
    make_enemy,
    make_hand_card,
    make_loop,
)


def _combat_gs_no_enemies(hand):
    """Build a combat GameState with zero alive enemies (boss phase transition)."""
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(current_hp=40, max_hp=80, energy=3),
        hand=hand,
        enemies=[],  # key: no alive enemies
    )
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=48,
        current_hp=40,
        max_hp=80,
        gold=99,
        max_energy=3,
        deck=[],
    )
    raw = UpstreamGameState(
        screen="MONSTER",
        in_combat=True,
        turn=3,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )
    return GameState(raw=raw, state_type="boss")


def test_flag_initialized_to_minus_one():
    loop = make_loop(MagicMock())
    assert loop._no_target_replan_round == -1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_no_target_replan.py::test_flag_initialized_to_minus_one -v`
Expected: FAIL with `AttributeError: 'AgentLoop' object has no attribute '_no_target_replan_round'`

- [ ] **Step 3: Add flag init at line 252**

In `src/agent/loop.py`, find the existing line:
```python
        self._combat_plan_round: int = -1  # Round the plan was generated for
```

Add immediately after it:
```python
        self._no_target_replan_round: int = -1  # Round we entered no-target replan mode
```

- [ ] **Step 4: Add reset at line 1811 (general reset)**

In `src/agent/loop.py`, find the existing block near line 1811:
```python
        self._combat_plan = None
        self._combat_plan_index = 0
        self._combat_plan_round = -1
        self._prev_combat_plan = None
```

Add after `self._combat_plan_round = -1`:
```python
        self._no_target_replan_round = -1
```

- [ ] **Step 5: Add reset at line 1985 (COMBAT_START transition)**

In `src/agent/loop.py`, find:
```python
                        if transition == PhaseTransition.COMBAT_START:
                            self._last_combat_round = -1
                            self._end_turn_sent_round = -1
                            self._combat_plan = None
                            self._combat_plan_index = 0
                            self._combat_plan_round = -1
```

Add after `self._combat_plan_round = -1`:
```python
                            self._no_target_replan_round = -1
```

- [ ] **Step 6: Add reset at line 2892 (replay reload)**

In `src/agent/loop.py`, find:
```python
        self._v2_combat_conversation = None
        self._combat_plan = None
        self._combat_plan_index = 0
        self._combat_plan_round = -1
```

Add after `self._combat_plan_round = -1`:
```python
        self._no_target_replan_round = -1
```

- [ ] **Step 7: Run test to verify it passes**

Run: `pytest tests/test_no_target_replan.py::test_flag_initialized_to_minus_one -v`
Expected: PASS

- [ ] **Step 8: Commit**

```bash
git add src/agent/loop.py tests/test_no_target_replan.py
git commit -m "feat(loop): add _no_target_replan_round flag with combat resets

Tracks which round the agent entered no-target replan mode (for multi-phase
boss transitions). Reset at all three existing combat-state reset sites."
```

---

## Task 2: Validator rule — reject target-requiring cards when no alive enemies

**Files:**
- Modify: `src/agent/loop.py` (method `_validate_combat_plan`, around line 6432)
- Test: `tests/test_no_target_replan.py`

- [ ] **Step 1: Write the failing test — plan with only attack vs no enemies**

Append to `tests/test_no_target_replan.py`:

```python
def test_validator_rejects_target_attack_when_no_enemies():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="attack-only",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert "no alive enemies" in error.lower()
    assert valid_count == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_no_target_replan.py::test_validator_rejects_target_attack_when_no_enemies -v`
Expected: FAIL — current validator returns `(None, 1)` (no rule exists yet)

- [ ] **Step 3: Add the validator rule**

In `src/agent/loop.py`, find in `_validate_combat_plan` (around line 6432-6441):
```python
            card_pos, card = _match_remaining_card(action.card_name)
            if card is None:
                return (
                    "Invalid plan: "
                    f"step {action_idx} tries to play {action.card_name}, "
                    "but that card is not in your playable hand yet. "
                    f"Your playable hand RIGHT NOW: [{_hand_summary()}]. "
                    "Only plan cards that are currently in hand until after a draw/create action resolves.",
                    valid_count,
                )
```

Immediately after that block (before the `rules = getattr(...)` line), add:

```python
            # Target availability: target-requiring card cannot execute with no alive enemies
            # (e.g. multi-phase boss mid-transition). Existing truncate logic handles
            # the valid-prefix case; valid_count=0 triggers the replan-with-context path.
            card_needs_target = (
                getattr(card, "requires_target", False)
                or card.target_type in ("AnyEnemy", "single_enemy", "Enemy")
            )
            if card_needs_target and not gs.enemies:
                return (
                    "Invalid plan: "
                    f"step {action_idx} tries to play {getattr(card, 'name', action.card_name)} "
                    "which needs an enemy target, but no alive enemies "
                    "(multi-phase boss transitioning between phases). "
                    "Plan only non-target cards (Defend / Powers / self-buffs) or end_turn.",
                    valid_count,
                )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_no_target_replan.py::test_validator_rejects_target_attack_when_no_enemies -v`
Expected: PASS

- [ ] **Step 5: Write the truncate test (valid prefix preserved)**

Append to `tests/test_no_target_replan.py`:

```python
def test_validator_truncates_mixed_plan_at_first_target_attack():
    gs = _combat_gs_no_enemies([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card("Footwork", 1, playable=True, requires_target=False),
        make_hand_card("Strike", 2, playable=True, requires_target=True),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Footwork", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="mixed plan",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert "no alive enemies" in error.lower()
    assert valid_count == 2  # Defend + Footwork valid; Strike rejected


def test_validator_allows_non_target_plan_with_no_enemies():
    gs = _combat_gs_no_enemies([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card("Footwork", 1, playable=True, requires_target=False),
    ])
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Footwork", target_index=None),
        ),
        end_turn=True,
        reasoning="all self-target",
    )

    error, valid_count = loop._validate_combat_plan(plan, gs)

    assert error is None
    assert valid_count == 2
```

- [ ] **Step 6: Run tests**

Run: `pytest tests/test_no_target_replan.py -v`
Expected: all 4 tests PASS. Also re-run the existing validator suite:
Run: `pytest tests/test_loop_combat.py -v -k validate`
Expected: all existing validator tests still PASS (no regression).

- [ ] **Step 7: Commit**

```bash
git add src/agent/loop.py tests/test_no_target_replan.py
git commit -m "feat(loop): validator rejects target-requiring cards with no alive enemies

Plans that target attack cards during multi-phase boss transitions now
truncate to the valid non-target prefix (or return valid_count=0 so the
caller replans with explicit no-target context)."
```

---

## Task 3: Early detection in `_execute_combat_plan` + `no_target_mode` parameter

**Files:**
- Modify: `src/agent/loop.py` — `_execute_combat_plan` (around line 5747, before "Generate new plan if needed"); `_generate_combat_plan` (line 6229, add parameter + replan_ctx construction)
- Test: `tests/test_no_target_replan.py`

- [ ] **Step 1: Write the failing test — detection triggers no_target_mode**

Append to `tests/test_no_target_replan.py`:

```python
def test_no_enemies_triggers_replan_with_no_target_mode():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend", target_index=None),
            ),
            end_turn=True,
            reasoning="play defend, phase transition",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        asyncio.run(loop._execute_combat_plan(gs))

    # Verify no_target_mode=True was passed to generator
    kwargs = loop._generate_combat_plan.await_args.kwargs
    assert kwargs.get("no_target_mode") is True
    # Verify flag now set for this round
    assert loop._no_target_replan_round == gs.combat_round


def test_no_enemies_second_call_same_round_skips_llm_and_ends_turn():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._no_target_replan_round = gs.combat_round  # simulate already-tried this round
    loop._generate_combat_plan = AsyncMock()
    loop._execute = AsyncMock(return_value={"stable": True})

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    loop._generate_combat_plan.assert_not_awaited()
    loop._execute.assert_awaited_once_with(actions.end_turn(), delta_source="turn_end")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_no_target_replan.py::test_no_enemies_triggers_replan_with_no_target_mode tests/test_no_target_replan.py::test_no_enemies_second_call_same_round_skips_llm_and_ends_turn -v`
Expected: FAIL. First test: `no_target_mode` kwarg absent / `TypeError` on unexpected kwarg or `kwargs.get("no_target_mode")` is None. Second test: LLM is still called (no early return).

- [ ] **Step 3: Add `no_target_mode` parameter to `_generate_combat_plan`**

In `src/agent/loop.py`, modify the signature at line 6229:

```python
    async def _generate_combat_plan(
        self, gs: GameState, *, is_replan: bool = False,
        use_fallback_model: bool = False,
        no_target_mode: bool = False,
    ) -> CombatPlan | None:
```

Update the docstring to describe `no_target_mode` (add a bullet):

```
            no_target_mode: If ``True``, inject a replan_context telling the
                LLM no alive enemies exist (boss phase transition); allowed
                actions are non-target cards or end_turn.
```

In the method body, find the existing replan_ctx build (around line 6257-6267):

```python
                # Build re-plan context from the previous plan
                replan_ctx = ""
                if is_replan and self._prev_combat_plan:
                    prev = self._prev_combat_plan
                    completed = getattr(self, "_combat_plan_index", 0)
                    total = len(prev.actions)
                    replan_ctx = (
                        f"Original plan ({completed}/{total} completed): "
                        f"{prev.reasoning[:200]}\n"
                        f"Trigger: {self._last_played_card_name or '?'} drew new cards."
                    )
```

Replace the block with:

```python
                # Build re-plan context: no-target mode takes precedence
                replan_ctx = ""
                if no_target_mode:
                    replan_ctx = (
                        "## No Valid Targets\n"
                        "All enemies are non-hittable (likely a multi-phase boss like "
                        "Subject transitioning between phases).\n\n"
                        "- DO NOT plan enemy-target-requiring cards.\n"
                        "- You MAY play non-target cards — especially Powers, or any "
                        "non-target attack/skill that benefits future turns.\n"
                        "- Choose `end_turn` if no useful non-target card is in hand."
                    )
                elif is_replan and self._prev_combat_plan:
                    prev = self._prev_combat_plan
                    completed = getattr(self, "_combat_plan_index", 0)
                    total = len(prev.actions)
                    replan_ctx = (
                        f"Original plan ({completed}/{total} completed): "
                        f"{prev.reasoning[:200]}\n"
                        f"Trigger: {self._last_played_card_name or '?'} drew new cards."
                    )
```

- [ ] **Step 4: Add detection branch in `_execute_combat_plan`**

In `src/agent/loop.py`, find the block starting around line 5747:

```python
        # Generate new plan if needed (new round, no plan, or plan exhausted)
        if (
            self._combat_plan is None
            or self._combat_plan_round != current_round
            or self._combat_plan_index >= len(self._combat_plan.actions)
        ):
            # Re-plan within the same round (draw-card split, validation failure)
            # uses fast tier; fresh round plan uses strategic tier
            is_replan = (
                self._combat_plan is None
                and self._combat_plan_round == current_round
            )
            plan = await self._generate_combat_plan(
                gs, is_replan=is_replan,
                use_fallback_model=use_fallback_model,
            )
```

Immediately BEFORE the `# Generate new plan if needed` comment (but AFTER the `if not playable` block at line 5700-5745 which ends with the end_turn decision), insert:

```python
        # No-target mode: all enemies dead/invulnerable (e.g. Subject phase transition).
        # Playable cards exist (energy-wise) but target-requiring cards cannot execute.
        # Either replan with explicit no-target context, or end_turn if we already tried.
        if not gs.enemies:
            if self._no_target_replan_round == current_round:
                # Already tried replan this round; LLM did not produce a usable plan.
                # End turn to let the next phase spawn.
                if current_round == self._end_turn_sent_round:
                    return None
                logger.info(
                    "Combat: no alive enemies at round %d, already replanned this round — ending turn",
                    current_round,
                )
                self._end_turn_sent_round = current_round
                self._combat_plan = None
                action = actions.end_turn()
                await self._execute(action, delta_source="turn_end")
                try:
                    await self._wait_for_play_phase_timed(
                        reason="combat_plan:no_target_fallback",
                    )
                except McpTimeout:
                    pass
                return Decision(
                    floor=floor, state_type=gs.state_type, action=action,
                    reasoning="No alive enemies, no-target replan exhausted — end turn",
                    source="plan",
                )
            logger.info(
                "Combat: no alive enemies at round %d — entering no-target replan mode",
                current_round,
            )
            self._no_target_replan_round = current_round
            plan = await self._generate_combat_plan(
                gs, is_replan=True,
                use_fallback_model=use_fallback_model,
                no_target_mode=True,
            )
            if plan is None:
                # LLM failed entirely; outer retry will re-enter and the flag above
                # will short-circuit to end_turn.
                return None
            self._combat_plan = plan
            self._combat_plan_index = 0
            self._combat_plan_round = current_round
            self._combat_plan_alive = set()
            # Emit monitor event (mirrors the normal plan-emit at line 5773)
            self._emit_monitor("combat_plan", {
                "items": [
                    {"type": a.action_type, "card": a.card_name, "target": a.target_index}
                    for a in plan.actions
                ],
                "end_turn": plan.end_turn,
                "reasoning": plan.reasoning[:500],
                "no_target_mode": True,
            })
            # Fall through to the normal plan-execution path below. If the plan
            # is empty with end_turn=True, the existing empty-plan branch handles
            # end_turn cleanly.
```

- [ ] **Step 5: Run the detection tests**

Run: `pytest tests/test_no_target_replan.py::test_no_enemies_triggers_replan_with_no_target_mode tests/test_no_target_replan.py::test_no_enemies_second_call_same_round_skips_llm_and_ends_turn -v`
Expected: both PASS.

- [ ] **Step 6: Add regression test — existing empty-plan path still works**

Append to `tests/test_no_target_replan.py`:

```python
def test_no_enemies_empty_plan_with_end_turn_ends_turn():
    gs = _combat_gs_no_enemies([
        make_hand_card("Strike", 0, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(),
            end_turn=True,
            reasoning="nothing useful to play",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    assert loop._no_target_replan_round == gs.combat_round
```

- [ ] **Step 7: Run full no-target test suite**

Run: `pytest tests/test_no_target_replan.py -v`
Expected: all 6 tests PASS.

- [ ] **Step 8: Regression check — entire loop combat suite**

Run: `pytest tests/test_loop_combat.py -v`
Expected: all existing tests PASS.

- [ ] **Step 9: Commit**

```bash
git add src/agent/loop.py tests/test_no_target_replan.py
git commit -m "feat(loop): no-target replan for multi-phase boss transitions

When gs.enemies is empty but play_phase is active, inject a fixed
replan_context telling the LLM all enemies are non-hittable and only
non-target cards or end_turn are allowed. A per-round flag prevents
the LLM from being called twice in the same round; if the replan fails
or is exhausted, end_turn is dispatched directly to let the next boss
phase spawn. Resolves the Subject boss abort bug at floor 48.

Fixes run abort: 'LLM decision failed for boss, aborting to prevent
random play'."
```

---

## Task 4: Reset-scope test + skill-eval safety verification

**Files:**
- Modify: `tests/test_no_target_replan.py`
- Verify only: `src/agent/loop.py:1569-1589` (already guarded for `not gs.enemies`)

- [ ] **Step 1: Write the reset-scope test**

Append to `tests/test_no_target_replan.py`:

```python
def test_flag_resets_on_combat_start():
    """New combat should reset the flag even if a prior combat set it."""
    loop = make_loop(MagicMock())
    loop._no_target_replan_round = 5  # simulate prior combat leaving the flag set

    # Simulate the COMBAT_START reset block body
    loop._last_combat_round = -1
    loop._end_turn_sent_round = -1
    loop._combat_plan = None
    loop._combat_plan_index = 0
    loop._combat_plan_round = -1
    loop._no_target_replan_round = -1  # the line added by this feature

    assert loop._no_target_replan_round == -1


def test_poison_kill_check_safe_with_no_enemies():
    """Regression: _poison_kills_all_enemies must not return True for empty list."""
    from src.agent.loop import AgentLoop

    class _Stub:
        enemies = []

    assert AgentLoop._poison_kills_all_enemies(_Stub()) is False
```

- [ ] **Step 2: Run tests**

Run: `pytest tests/test_no_target_replan.py::test_flag_resets_on_combat_start tests/test_no_target_replan.py::test_poison_kill_check_safe_with_no_enemies -v`
Expected: both PASS (the poison helper is already guarded at loop.py:1576-1577).

- [ ] **Step 3: Run the whole new test file**

Run: `pytest tests/test_no_target_replan.py -v`
Expected: all 8 tests PASS.

- [ ] **Step 4: Commit**

```bash
git add tests/test_no_target_replan.py
git commit -m "test(loop): verify no-target flag reset + poison-kill safety

Locks in the reset at COMBAT_START and documents that the existing
_poison_kills_all_enemies guard already handles the enemies=[] case
that occurs during boss phase transitions."
```

---

## Task 5: End-to-end abort-prevention regression test

**Files:**
- Modify: `tests/test_no_target_replan.py`

- [ ] **Step 1: Write the regression test — boss phase transition does not abort**

Append to `tests/test_no_target_replan.py`:

```python
def test_boss_phase_transition_does_not_abort_when_llm_still_plans_attacks():
    """The specific Subject-boss bug: LLM persistently plans attacks, agent
    must not raise RuntimeError — it should fall through to end_turn."""
    gs = _combat_gs_no_enemies([
        make_hand_card("Leading Strike", 0, playable=True, requires_target=True),
        make_hand_card("Strike", 1, playable=True, requires_target=True),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round

    # Mock LLM that keeps returning target-requiring attacks even with no-target context
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Leading Strike", target_index=0),
            ),
            end_turn=True,
            reasoning="LLM ignored no-target context",
        )
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    # First call — enters no-target replan mode; validator will truncate the
    # attack-only plan to empty, returning None from _execute_combat_plan.
    with patch.object(loop_module, "parse_state", return_value=gs):
        first = asyncio.run(loop._execute_combat_plan(gs))

    # Second call (simulating outer retry) — flag is set, so short-circuits to end_turn.
    with patch.object(loop_module, "parse_state", return_value=gs):
        second = asyncio.run(loop._execute_combat_plan(gs))

    assert second is not None
    assert second.action == actions.end_turn()
    # Crucial: no RuntimeError was raised
```

- [ ] **Step 2: Run the regression test**

Run: `pytest tests/test_no_target_replan.py::test_boss_phase_transition_does_not_abort_when_llm_still_plans_attacks -v`
Expected: PASS.

- [ ] **Step 3: Run the full project test suite**

Run: `pytest tests/ -x --ignore=tests/regression -q`
Expected: all tests PASS (or only pre-existing failures unrelated to this change).

- [ ] **Step 4: Commit**

```bash
git add tests/test_no_target_replan.py
git commit -m "test(loop): regression for Subject boss phase-transition abort

Reproduces the step=969 failure path (LLM persistently plans attack
cards despite no-target replan context). Asserts the agent falls
through to end_turn instead of raising RuntimeError."
```

---

## Task 6: Final verification

- [ ] **Step 1: Full test suite**

Run: `pytest tests/ --ignore=tests/regression -q`
Expected: all tests PASS (or only pre-existing failures unrelated to this feature).

- [ ] **Step 2: Targeted check — the new test file**

Run: `pytest tests/test_no_target_replan.py -v`
Expected: 10 tests PASS:
- `test_flag_initialized_to_minus_one`
- `test_validator_rejects_target_attack_when_no_enemies`
- `test_validator_truncates_mixed_plan_at_first_target_attack`
- `test_validator_allows_non_target_plan_with_no_enemies`
- `test_no_enemies_triggers_replan_with_no_target_mode`
- `test_no_enemies_second_call_same_round_skips_llm_and_ends_turn`
- `test_no_enemies_empty_plan_with_end_turn_ends_turn`
- `test_flag_resets_on_combat_start`
- `test_poison_kill_check_safe_with_no_enemies`
- `test_boss_phase_transition_does_not_abort_when_llm_still_plans_attacks`

- [ ] **Step 3: Spec coverage review**

Confirm every section of the design spec maps to implemented code:
- Section 3 trigger condition → Task 3 Step 4 (`if not gs.enemies`)
- Section 4 flag → Task 1
- Section 5 execution flow branches A/B/C → Task 3 Step 4 + Task 2
- Section 6 validator rule → Task 2
- Section 7 `no_target_mode` parameter → Task 3 Step 3
- "Edge Case — Skill Eval" → Task 4 Step 1 (verified, no new guard needed)
- Section 2 replan context string → Task 3 Step 3 (exact verbatim match)

No further commit — verification only.

---

## Notes for the Implementer

- **Strictly TDD** — every task follows RED → GREEN → COMMIT. Do not batch.
- **Exact line numbers** in the plan refer to the HEAD of the feature branch at the time the spec was written (commit 3586830). If the file has shifted by a few lines, use the surrounding code as the authoritative anchor.
- The existing `make_loop(MagicMock())` helper in `tests/conftest.py` patches network initialization — reuse it; do not construct `AgentLoop` directly.
- `make_hand_card` accepts `requires_target`, `playable`, `energy_cost`, `rules_text` kwargs.
- **Do not edit** any prompt file under `src/brain/prompts/`. The replan context string lives in the loop layer as per the post-PE-deprecation architecture.
