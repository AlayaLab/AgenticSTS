# No-Target Replan for Multi-Phase Boss Transitions

**Status:** Design approved, pending implementation plan
**Date:** 2026-04-19
**Author:** brainstorming session
**Related log:** step=969 run aborted at floor 48 vs. Subject boss

## Problem

When a multi-phase boss (Subject / TestSubject) dies during the player's
turn, the mod exposes a transient state where `enemies=[]` (all filtered
out by `is_alive`) while `is_play_phase=True` and the player still has
energy and attack cards in hand. The agent runs this flow:

1. `_execute_combat_plan` — `playable_cards` is non-empty (Strike/Leading
   Strike still satisfy `c.playable`, which only checks energy/unplayable
   flag, not target availability), so the "no playable → end_turn"
   shortcut at `loop.py:5700` does not trigger.
2. LLM is asked to plan → returns `[Leading Strike, Strike, ...]`.
3. Runtime target check at `loop.py:6086` fails (`needs target but
   none available`) → plan advances, eventually fails entirely.
4. Outer retry loop calls the LLM again with the same state → same
   failure.
5. Fallback (analysis-tier) model also fails.
6. `loop.py:5649` raises `RuntimeError("LLM decision failed for boss
   ...")` and the run aborts.

The root cause is a mismatch between "the game model says there are
cards playable right now" and "no alive enemy means target-requiring
cards cannot actually be executed." The LLM is never told about this
constraint, and the validator does not enforce it.

## Goals

- Eliminate the abort path for the `enemies=[] + is_play_phase=True`
  transient state.
- Minimal, localized changes — no new LLM tiers, no system-prompt
  edits, no new modules.
- Preserve existing behavior for all other combat states.
- Allow the LLM to still play useful non-target cards (Powers,
  self-buffs) during the transition when sensible.

## Non-Goals

- Handling `is_hittable=False` on alive enemies (invulnerable /
  shielded state) — different problem, out of scope.
- Changes to `COMBAT` / `COMBAT_BOSS` system prompts (immutable per
  post-PE-deprecation architecture).
- New skill-discovery mechanism specifically for phase transitions
  (existing cohort discovery can absorb the pattern).

## Design

### 1. Architecture

Three layers of defense, all inside `_execute_combat_plan` /
`_generate_combat_plan` / `_validate_combat_plan`:

1. **Early detection + per-round flag** — catch the state before
   burning LLM calls.
2. **Replan with explicit no-target context** — give the LLM one
   chance to play non-target cards or end turn cleanly.
3. **Validator target-availability check** — truncate any attack
   actions the LLM still produces, forcing `end_turn=True`.

### 2. Replan Context String

Injected through the existing `CombatConversation.add_round_state(
replan_context=...)` channel. Content (~45 tokens):

```
## No Valid Targets
All enemies are non-hittable (likely a multi-phase boss like
Subject transitioning between phases).

- DO NOT plan enemy-target-requiring cards.
- You MAY play non-target cards — especially Powers, or any
  non-target attack/skill that benefits future turns.
- Choose `end_turn` if no useful non-target card is in hand.
```

Language: English (matches COMBAT system prompt language to avoid
LLM language switching).

### 3. Trigger Condition

Strict: `gs.is_play_phase and not gs.enemies` (where `gs.enemies`
is already filtered by `is_alive=True`).

`is_hittable=False` on alive enemies is **not** in scope.

### 4. State Field

New field on the agent loop instance:

```python
self._no_target_replan_round: int = -1
```

- Set to the current round when we enter the no-target replan path.
- Reset to `-1` on combat reset (alongside other `_combat_plan_*`
  state).
- Prevents a second LLM call in the same round if the first replan
  still produced invalid output.

### 5. Execution Flow

```
_execute_combat_plan entry
├─ play_phase, playable cards present
│
├─ [NEW] gs.enemies == []?
│   ├─ no  → existing plan-generation path
│   └─ yes → no-target mode
│       ├─ _no_target_replan_round == current_round?
│       │   ├─ yes → end_turn directly (branch C)
│       │   └─ no  → _no_target_replan_round = current_round
│       │           → _generate_combat_plan(gs, no_target_mode=True)
│       │           → (plan may be truncated by validator)
│       │           ├─ branch A: plan executes cleanly (Defend/Powers)
│       │           ├─ branch B: validator truncated to prefix + end_turn
│       │           └─ branch C: plan=None → outer retry → flag blocks → end_turn
```

**Branch A — LLM compliant:** Plan is Defend / Powers / self-buffs +
`end_turn=True`. Validator passes. Normal execution.

**Branch B — LLM still plans attacks:** Validator's new rule rejects
`requires_target AND not gs.enemies`. Truncate-to-valid-prefix logic
(existing) keeps any leading non-target cards and forces
`end_turn=True`. If the entire plan is attacks, `valid_count=0` and
the outer retry fires → flag blocks re-entry → end_turn.

**Branch C — Empty plan:** Existing empty-plan + `end_turn=True`
path handles it (`loop.py:5811-5875`). If `end_turn=False`, outer
retry → flag blocks → end_turn.

### 6. Validator Extension

`_validate_combat_plan` gains one rule in the card loop (after
hand-match, before energy check):

```python
needs_target = getattr(card, "requires_target", False) or \
               card.target_type in ("AnyEnemy", "single_enemy", "Enemy")
if needs_target and not gs.enemies:
    return (
        f"Invalid plan: step {action_idx} tries to play "
        f"{display_name} which needs a target, but no alive enemies "
        f"(multi-phase boss transitioning). "
        f"Plan only non-target cards (Defend/Power/self-buffs) or end_turn.",
        valid_count,
    )
```

Reuses existing truncate semantics — the caller already handles
`valid_count>0` (truncate) and `valid_count=0` (replan) branches.

### 7. Plumbing — `no_target_mode` Parameter

`_generate_combat_plan` gains:

```python
async def _generate_combat_plan(
    self, gs: GameState, *, is_replan: bool = False,
    use_fallback_model: bool = False,
    no_target_mode: bool = False,   # NEW
) -> CombatPlan | None:
```

When `no_target_mode=True`:

- Build `replan_ctx` from the fixed no-target context string (see
  Section 2).
- Pass through `conversation.add_round_state(replan_context=replan_ctx)`.
- Route through the normal `is_replan=True` fast-tier path (no new
  tier required).

If both `is_replan` and `no_target_mode` are true, `no_target_mode`
takes precedence for context construction.

## Edge Case Interactions

### Skill Eval Mode

The kill/death detection helpers (`_poison_kills_all_enemies`,
`compute_total_incoming`) should be guarded for `enemies=[]`:

- Wrap kill/death checks in the no-target branch with
  `if gs.enemies:` — when empty, skip both (neither win nor loss,
  just end_turn).
- Confirm `_poison_kills_all_enemies` returns `False` (or is skipped)
  for empty enemy list; if it returns `True` via vacuous `all([])`,
  that bug must be fixed.

### Strategic Thread

`plan.note_to_future_self` from a no-target replan should flow
through the existing `_strategic_notes` pathway (`loop.py:5783-5787`)
unchanged — the next round's LLM benefits from knowing "we just
survived a phase transition."

### CombatConversation History

The no-target replan round is added to `CombatConversation` via
`add_round_state` like any other round. Later rounds (when the next
phase spawns) see the transition as context → better decisions.

### HCM / Round Recording

Empty or Defend-only `_v2_round_actions` is already a supported case
("end_turn without playing cards" exists normally); no HCM changes
needed.

### Monitor Event

Existing `emit_monitor("combat_plan", ...)` fires as usual. Optional
enhancement: include `"no_target_mode": True` in the payload for
frontend filtering — not required for correctness.

### Log Breadcrumb

One new log line on entry:

```
logger.info(
    "Combat: no alive enemies at round %d — entering no-target replan mode",
    current_round,
)
```

Truncation / branch-B paths reuse existing warning logs.

## Testing Strategy

New file `tests/test_no_target_replan.py`:

| Test | Scenario | Expected |
|---|---|---|
| `test_no_enemies_triggers_replan_context` | `enemies=[]`, play_phase=True, first call | `_generate_combat_plan` called with `no_target_mode=True`; `replan_context` contains "No Valid Targets" |
| `test_same_round_twice_ends_turn` | flag already set to current round | LLM skipped, `end_turn` dispatched directly |
| `test_validator_rejects_target_attack_when_no_enemies` | plan=[Strike(target=0)], enemies=[] | `valid_count=0`; error contains "no alive enemies" |
| `test_validator_truncates_mixed_plan` | plan=[Defend, Footwork, Strike], enemies=[] | `valid_count=2`; truncate to first two + `end_turn=True` |
| `test_empty_plan_ends_turn` | LLM returns empty plan + `end_turn=True` | Direct `end_turn`; flag does not block |
| `test_flag_resets_between_combats` | combat_end → new combat round 1, enemies=[] | Still enters no-target mode (flag reset on combat reset) |
| `test_validator_allows_self_target_cards` | plan=[Footwork, Prepared], enemies=[] | `valid_count=2`, no error |
| `test_skill_eval_no_target_no_false_kill` | skill_eval_state=active, enemies=[], poison powers present | `_poison_kills_all_enemies` path not triggered (guarded) |

Regression fixture (optional): if `data/runs/history.jsonl` retains
the step=969 run, seed a mock MCP snapshot (enemies=[], hand with
Strike/Leading Strike/Shiv) and assert the run does not abort.

## Risks and Mitigations

| Risk | Mitigation |
|---|---|
| LLM persistently returns attack-only plans | Three-layer defense: validator truncate + flag + outer retry end_turn |
| Legitimate multi-round self-buff window missed | Flag resets each round; each round gets one LLM chance to play non-target cards before end_turn fallback |
| MCP state race: enemies list momentarily empty | Branch C end_turn costs at most one wasted turn; next round recovers; acceptable |
| Regression in normal combat | Trigger guarded by `not gs.enemies` — impossible for normal combat states |

## Out of Scope

- `is_hittable=False` alive enemies (invulnerable shields).
- `COMBAT` / `COMBAT_BOSS` / `DECKBUILD` / `STRATEGIC` system prompt
  edits.
- New LLM tier or model routing change.
- Skill-discovery additions for phase-transition patterns.

## Implementation Checklist

1. Add `self._no_target_replan_round: int = -1` init alongside
   `_combat_plan_round` (loop.py:1811), and reset to `-1` at every
   existing combat-state reset site (loop.py:1809-1811, 1983-1985,
   2890-2892).
2. In `_execute_combat_plan`, insert no-target detection branch after
   the `if not playable` block.
3. Add `no_target_mode: bool = False` parameter to
   `_generate_combat_plan`; build replan_ctx when True.
4. Extend `_validate_combat_plan` with the target-availability rule.
5. Add kill/death detection guards for `enemies=[]` in the no-target
   branch (skill eval mode).
6. Add the single info log breadcrumb.
7. Write tests in `tests/test_no_target_replan.py`.
8. Run full test suite + smoke-run against a multi-phase boss fight
   (ideally Subject) to confirm live behavior.
