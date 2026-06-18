# Skill Eval Mode: Boss Combat Replay — Design Spec

## Context

The skill library has 100+ skills but 89% have zero usage. The P4 skill lifecycle (implemented) added fair competition, retirement, and dedup. But confidence scores remain unreliable because they're based on binary win/lose attribution across the entire run — not precise per-skill measurement.

This spec adds a **boss combat replay system** that uses STS2's save/load to A/B test skill sets on the exact same boss fight. The game engine handles all mechanics (card effects, status tracking, draw pile, enemy AI) with 100% accuracy.

## Goals

1. Every untested skill gets evaluated within ~17-33 boss fights (2-3 skills per replay × 2 replays per boss)
2. Confidence scores reflect actual boss combat performance, not run-level win/lose
3. Zero simulation code — game engine is the simulator
4. Toggleable — off during development/testing
5. Integrated into existing agent loop — no new `run_single_combat` abstraction

## Save/Continue Behavior (verified)

STS2 saves at floor entry. `save_and_quit` mid-combat discards combat progress. `continue_run` resumes at **combat start** (round 1, full enemy HP, fresh hand, same RNG seed = same draw order). This is the foundation of the replay system.

Verified 2026-03-26: `save_and_quit` during COMBAT → `continue_run` → same floor, same run_id, combat restarts from round 1.

## Design

### Activation

Skill eval mode activates when ALL of:
- `SKILL_EVAL_ENABLED = true` (env var `STS2_SKILL_EVAL`, default **false** — opt-in until validated)
- Combat is a boss fight (`combat_type == "boss"`)
- Library has untested skills (`usage_count == 0, status == "active"`, matching boss context via trigger)

### State Machine

```
IDLE → boss combat start + untested skills exist → EVAL_ACTIVE
EVAL_ACTIVE → normal combat → kill/death detected mid-plan → SAVE_AND_SWAP
SAVE_AND_SWAP → record result → save_and_quit → continue_run →
  more alternatives? → EVAL_ACTIVE (with swapped skill set)
  no more? → FINAL_RUN
FINAL_RUN → continue_run with best skill set → play to completion → IDLE
```

State tracked via `self._skill_eval_state: str` in AgentLoop (`"idle"` | `"active"` | `"final"`).

### Precise Kill Detection (mid-plan, per-card)

Kill detection happens DURING plan execution, after each card is played. The agent loop already polls game state after each card play (for draw-card splitting, enemy-death re-plan, etc.). We add one check:

```python
# In _execute_combat_plan(), after each card play + state poll:
if self._skill_eval_state == "active":
    remaining_actions = plan.actions[i+1:]
    if self._remaining_plan_kills_boss(new_gs, remaining_actions):
        # Save BEFORE executing remaining cards
        self._record_eval_result(new_gs, "kill")
        await self._save_and_swap()
        return  # don't execute the killing blow
```

**`_remaining_plan_kills_boss(gs, remaining)` logic:**
1. For each remaining action, look up the card in `gs.hand` by name (game engine has recomputed all values post-buff)
2. Skip non-attack cards (`card.damage is None`) and potion actions
3. For targeted cards with `card.target_previews`: find the TargetPreview matching the boss index via `next((tp for tp in card.target_previews if tp.target_index == boss_idx), None)`, use `tp.total_damage`
4. For AoE/untargeted attacks: use `card.total_damage`
5. Sum remaining damage vs `sum(e.hp + (e.block or 0) for e in gs.enemies if e.is_alive)`
6. Return `remaining_damage >= boss_effective_hp`

**Note:** Cards not yet played still show damage for the CURRENT state (post-buff from earlier played cards). This is precise for already-applied buffs but cannot account for buffs from other remaining cards (e.g., if remaining = [Inflame, Strike], Strike's damage doesn't reflect Inflame yet). This is acceptable — it causes under-prediction (miss a kill), not over-prediction (false kill). Missing a kill just means we play the turn normally.

**Why this is precise:** After each card play, the game engine recalculates all hand card values (Strength, Dexterity, Vulnerable, Weak, relic procs). We use the engine's numbers, not our own math.

**Death detection:** At plan end (before `end_turn`), check `compute_total_incoming(gs) >= gs.player_hp + (gs.raw.combat.player.block or 0)`. If lethal, record result as `won=False` and save before ending turn. Note: this is a best-effort estimate — powers like Buffer/Intangible may prevent actual death. False positives cause an extra harmless replay.

**Misfire handling:**
- Kill prediction wrong (boss survives): harmless — save/continue gave us an extra replay, agent re-enters combat
- Death prediction wrong (player survives): same — extra replay, no harm
- Kill not detected (boss dies normally): missed eval opportunity — this boss fight doesn't get replayed. Next boss will. Not catastrophic.

### Eval Schedule: Prioritize Untested Skills

At boss combat start, build the replay schedule:

```python
def _build_eval_schedule(self) -> list[list[str]]:
    # Get skills that were injected at combat start (captured before combat)
    original_skills = list(self._eval_original_skill_ids)

    # Untested skills matching boss context (trigger-filtered)
    boss_name = self._current_enemy_key or ""
    untested = [s for s in self._skill_library.all_skills
                if s.usage_count == 0 and s.status == "active"
                and s.skill_id not in original_skills
                and s.trigger.matches_context(
                    state_type="boss", enemy_name=boss_name, act=self._current_act)]

    schedule = []
    pool = [s.skill_id for s in untested]

    for _ in range(SKILL_EVAL_MAX_REPLAYS):  # default 2
        if not pool:
            break
        swap_count = min(3, len(pool), len(original_skills))
        swap_indices = random.sample(range(len(original_skills)), swap_count)
        kept = [s for i, s in enumerate(original_skills) if i not in swap_indices]
        replacements = pool[:swap_count]
        pool = pool[swap_count:]  # consume, don't re-test
        schedule.append(kept + replacements)

    return schedule
```

**Coverage:** 100+ untested skills ÷ (3 per replay × 2 replays per boss) = ~17-33 boss fights to test all. At ~3 bosses per run, that's ~6-11 runs for full coverage.

### Result Recording & Confidence Update

Each replay records:
```python
@dataclass(frozen=True)
class ReplayResult:
    skill_set_id: str          # hash of skill IDs
    skills_used: tuple[str, ...]
    hp_lost: int               # from combat start HP
    rounds: int                # rounds played before kill/death detected
    potions_used: int
    won: bool                  # kill detected (true) or death detected (false)
```

After all replays, compare:
```python
scored = sorted(results, key=lambda r: (not r.won, r.hp_lost, r.potions_used))
best, worst = scored[0], scored[-1]

# Skills ONLY in best → positive confidence signal
# Skills ONLY in worst → negative confidence signal
# Skills in both → no change (can't attribute)
```

Confidence updates use `record_replay_outcome(skill_id, success, quality)` from the P4 implementation (double-counted via `with_usage` for stronger signal).

### Save/Swap Flow

```python
async def _save_and_swap(self):
    """Save current state, continue, load next skill set."""
    try:
        await self._client.post_action(actions.save_and_quit())
        await asyncio.sleep(2)
        await self._client.post_action(actions.continue_run())
        await asyncio.sleep(2)
    except Exception as e:
        logger.warning("Skill eval save/swap failed: %s — aborting eval", e)
        self._skill_eval_state = "idle"
        self._skill_library.clear_active_override()
        return

    # Reset combat-tracking state (conversation, plan, round actions)
    # so the new replay starts clean
    self._v2_combat_conversation = None
    self._combat_plan = None
    self._v2_round_actions = []

    self._eval_current_index += 1
    if self._eval_current_index < len(self._eval_skill_sets):
        # More alternatives to test
        next_skills = self._eval_skill_sets[self._eval_current_index]
        self._skill_library.set_active_override(next_skills)
        # Agent loop naturally re-enters boss combat with new skills
    else:
        # All alternatives tested → enter FINAL_RUN
        self._skill_eval_state = "final"
        # Apply best skill set for the real fight
        best = min(self._eval_results, key=lambda r: (not r.won, r.hp_lost))
        self._skill_library.set_active_override(list(best.skills_used))
        # Update confidence from all results
        self._update_eval_confidence()
```

**Combat state reset:** After `continue_run`, the game restarts the combat. The agent loop must also reset its combat-tracking state (`CombatConversation`, `_combat_plan`, `_v2_round_actions`, `_combat_plan_alive`, etc.) to avoid stale context from the previous attempt bleeding into the new one. This happens naturally in the COMBAT_START handler when it detects a new combat — but we explicitly clear plan/conversation to be safe.

### Final Run

After all replays, the agent enters `FINAL_RUN` state:
- `continue_run` resumes at boss fight start
- Best skill set is active (via override)
- Agent plays normally — this time the kill/death check is bypassed (state is "final", not "active")
- Boss dies or player dies normally
- Post-combat flow continues (rewards, map, etc.)
- `_skill_eval_state` resets to "idle"
- Active override cleared

### Run Identity

All replays happen within the SAME run_id. The game's save/continue doesn't create a new run. Log/monitor will see multiple boss combat entries for the same floor, which is acceptable — each provides memory data.

### One-Time Skill Dedup

Before the replay system is useful, the 100+ skills need deduplication. This is a manual Claude Code session:

**Prompt for dedup session:**
```
Read data/skills/skills.json. Analyze all skills and:
1. Group skills with >50% content overlap (same advice, different wording)
2. For each group, keep the BEST one (highest confidence, most specific trigger)
3. Delete the rest
4. Report: how many skills before/after, which ones were removed and why
Save the cleaned skills.json.
```

This reduces the untested pool from 100+ to a manageable 30-50 unique skills.

## Files Changed

| File | Change |
|------|--------|
| `src/agent/loop.py` | Add `_skill_eval_state`, `_eval_results`, `_eval_skill_sets`, `_eval_current_index`. Hook into `_execute_combat_plan` for kill detection. Hook into boss combat start for activation. |
| `src/skills/replay_evaluator.py` | Simplify — keep `ReplayResult`, `compute_confidence_deltas`, remove `evaluate_boss_skills` and `_run_single_combat` (logic moves to loop.py). |
| `src/skills/library.py` | Add `set_active_override(ids)` / `clear_active_override()` (explicit set/clear for cross-round persistence, alongside existing `temporary_override` context manager). |
| `config.py` | Reuse existing `REPLAY_ENABLED` + `REPLAY_MAX_ALTERNATIVES`, add `SKILL_EVAL_ENABLED` |

## Config

```python
# Reuse existing replay constants (already in config.py from P4 implementation)
# REPLAY_ENABLED, REPLAY_MAX_ALTERNATIVES

# New: skill eval mode (default OFF until validated)
SKILL_EVAL_ENABLED = os.getenv("STS2_SKILL_EVAL", "false").lower() == "true"
```

Note: `SKILL_EVAL_MAX_REPLAYS` reuses `REPLAY_MAX_ALTERNATIVES` (already 2). No new constant needed.

## Per-Card State Poll

The spec assumes `_execute_combat_plan` polls state after each card play. Currently this only happens inside the enemy-death re-plan block (gated by `if self._combat_plan_alive`). For eval mode, we need a state poll after EVERY card play when `_skill_eval_state == "active"`. Add:

```python
# After each card play in _execute_combat_plan:
if self._skill_eval_state == "active":
    gs_after = parse_state(await self._client.get_state())
    if self._remaining_plan_kills_boss(gs_after, remaining):
        ...
```

This is a targeted addition — only polls when eval mode is active, so zero overhead during normal gameplay.

## Cost

- Per boss with eval: 2 extra boss fights × ~5-10 Sonnet calls = ~$0.10-0.20 extra
- Per run (3 bosses): ~$0.30-0.60 extra
- Total to test all 100+ skills: ~6-11 runs = ~$2-7
- After all skills tested: eval mode auto-skips (no untested skills → IDLE)
