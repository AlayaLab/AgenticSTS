# HP Efficiency Bias Fix — Design Spec

**Date**: 2026-03-28
**Problem**: Agent-authored dynamic tools and seed skills have offensive bias that causes unnecessary HP loss in combat. Tools recommend "skip block" when damage is survivable, and skills say "trade HP for damage" without safety conditions. The evaluation pipeline (skill confidence, tool effectiveness) treats combat as binary win/loss, providing no feedback signal for HP efficiency.

**Root cause**: The self-evolution pipeline lacks HP efficiency as a design principle. Tools evaluate "will I die?" instead of "how much HP will I lose?". Skills generated from win/loss data learn "winning = good" without learning "winning cheaply = better".

## Scope

### In scope (this spec)
1. Fix 2 HIGH-severity dynamic tools (`multi_enemy_incoming_damage.py`, `ramp_enemy_turn_cost.py`)
2. Fix 1 HIGH-severity seed skill (`seed_boss_and_elite_fight_strategy`)
3. Add HP efficiency principle to 3 generation prompts (Evolution, Skill discovery, Rule distiller)

### Out of scope (future work)
- Changing `record_outcome(success: bool)` to include HP efficiency score
- Changing `compute_effectiveness()` to weight HP-efficient tool usage
- Auditing/fixing MEDIUM-severity tools (binary survival gates that aren't actively harmful)

## Part 1: Fix Dynamic Tools

### 1.1 `multi_enemy_incoming_damage.py`

**Current logic (line 45)**:
```python
recommendation = "MUST_BLOCK" if not survives
    else ("BLOCK_ADVISED" if net_damage > current_hp * 0.3
    else "CAN_SKIP_BLOCK")
```

**New logic**: Four-tier recommendation with best-block-card advice.

Add parameter: `block_cards_in_hand` (already auto-bindable via `_build_block_cards_in_hand`).

```python
def execute(enemies, current_hp, current_block=0, block_cards_in_hand=None):
    # ... existing damage calculation ...

    # Find best block card: prefer cheapest card that fully covers damage,
    # fall back to highest block value if none fully covers.
    best_block = None
    if block_cards_in_hand:
        covers = [c for c in block_cards_in_hand if c["block_amount"] >= net_damage]
        if covers:
            best_block = min(covers, key=lambda c: c["energy_cost"])
        else:
            best_block = max(block_cards_in_hand, key=lambda c: c["block_amount"])

    if not survives:
        recommendation = "MUST_BLOCK"
    elif total_damage == 0:
        recommendation = "FREE_OFFENSE"
    elif net_damage > current_hp * 0.3:
        recommendation = "BLOCK_ADVISED"
    else:
        recommendation = "BLOCK_OPTIMAL"

    # Build note
    if total_damage == 0:
        note = "All enemies buffing/debuffing. Free offense turn — no block needed."
    elif not survives:
        note = f"FATAL — you will die. Must block."
    elif best_block and best_block["block_amount"] >= net_damage:
        note = (f"{net_damage} incoming. Best block: {best_block['name']} "
                f"({best_block['block_amount']} block) — fully covers. "
                f"Use remaining energy for offense.")
    elif best_block:
        note = (f"{net_damage} incoming. Best block: {best_block['name']} "
                f"({best_block['block_amount']} block) — reduces to "
                f"{net_damage - best_block['block_amount']} net damage.")
    else:
        note = f"{net_damage} incoming, no block cards available."
```

Key changes:
- `CAN_SKIP_BLOCK` eliminated. Only `FREE_OFFENSE` (0 incoming) means "skip block".
- `BLOCK_OPTIMAL` replaces the old skip-block tier: "you won't die, but block anyway with best card".
- `best_block` selection is energy-aware: prefers cheapest card that fully covers damage, falls back to highest block value.
- `note` text guides LLM to the specific card to play.
- The tool is advisory — the LLM sees full hand with costs and can override if energy is insufficient.

Update TEST_CASES to cover new tiers:

```python
TEST_CASES = [
    # 1. Multi-enemy attack — BLOCK_ADVISED (>30% HP)
    {
        "input": {
            "enemies": [
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
            ],
            "current_hp": 20, "current_block": 14,
        },
        "expected": {"total_incoming": 24, "recommendation": "BLOCK_ADVISED"},
    },
    # 2. Fatal incoming — MUST_BLOCK
    {
        "input": {
            "enemies": [
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
            ],
            "current_hp": 15, "current_block": 6,
        },
        "expected": {"total_incoming": 24, "recommendation": "MUST_BLOCK"},
    },
    # 3. All enemies buffing — FREE_OFFENSE (was CAN_SKIP_BLOCK)
    {
        "input": {
            "enemies": [{"name": "Cultist", "intent": "buff", "damage": 0}],
            "current_hp": 70,
        },
        "expected": {"total_incoming": 0, "recommendation": "FREE_OFFENSE"},
    },
    # 4. Low damage, block cards available — BLOCK_OPTIMAL with best card
    {
        "input": {
            "enemies": [{"name": "Beetle", "intent": "attack", "damage": 7}],
            "current_hp": 47,
            "block_cards_in_hand": [
                {"name": "Defend", "block_amount": 5, "energy_cost": 1},
                {"name": "Survivor", "block_amount": 8, "energy_cost": 1},
            ],
        },
        "expected": {
            "recommendation": "BLOCK_OPTIMAL",
            "best_block": {"name": "Survivor", "block_amount": 8},
        },
    },
    # 5. Low damage, no block cards — BLOCK_OPTIMAL but no card to recommend
    {
        "input": {
            "enemies": [{"name": "Beetle", "intent": "attack", "damage": 5}],
            "current_hp": 50,
            "block_cards_in_hand": [],
        },
        "expected": {"recommendation": "BLOCK_OPTIMAL", "best_block": None},
    },
]
```

### 1.2 `ramp_enemy_turn_cost.py`

**Current (line 98)**: `"NEVER play a pure block turn if you have any attack card"`

**Replace with**: Remove the absolute prohibition. Change the warning to conditional guidance:

```
"Pure block turns delay the kill and let the enemy ramp further.
Mix offense + defense each turn to minimize total HP loss.
Exception: if incoming damage this turn exceeds your total block capacity,
a full-block turn may be correct to survive."
```

This preserves the strategic insight (ramping enemies punish slow play) without the absolute "NEVER block" rule that eliminates valid defensive strategies.

**Note**: This tool is classified as `plan_evaluator` (its parameters are not auto-bindable), so it is NOT run by ToolPreprocessor during gameplay. The fix prevents the Evolution engine from treating "NEVER block" as a validated pattern when authoring future tools. Runtime impact is limited.

## Part 2: Fix Seed Skill

### `seed_boss_and_elite_fight_strategy`

Located in `data/skills/seeds/core_boss_strategy.json` (seed source) and propagated to `data/skills/skills.json` (runtime, entry `seed_core_boss_strategy`). Edit both files.

**Current problematic text**:
- "HP doesn't matter after Boss — you heal to full between Acts. Play to WIN, trade HP for damage."
- "Boss at 30 HP, you at 15 HP: go all-in on damage, don't waste energy on Block"

**Replace with**:
- "After beating a Boss, HP fully restores. You CAN play more aggressively in boss fights — but first verify you survive the next enemy turn. Never go all-in if incoming damage would kill you."
- Example: "Boss at 30 HP, you at 40 HP, 12 incoming: offense-heavy is fine. Boss at 30 HP, you at 15 HP, 20 incoming: block first to survive, kill next turn."

The strategic direction (boss fights allow more aggression) stays the same. The change adds a survival check condition.

## Part 3: Generation Prompt Updates

### 3.1 `EVOLUTION_SYSTEM_PROMPT` (evolution_engine.py)

Append after the existing TOOL AUTHORING REQUIREMENTS section:

```
HP EFFICIENCY PRINCIPLE:
- A fight won without losing HP is strictly better than one where HP was lost.
  Every tool you create must treat HP as a run-wide resource, not just a survival buffer.
- NEVER create tools that recommend "skip block" when incoming damage > 0.
  The correct output is WHICH block card to play, not WHETHER to block.
- "Free offense turns" ONLY exist when ALL enemies have non-attack intents (Buff/Debuff/Status).
  Any incoming damage — even 3-4 points — should be blocked if energy and cards allow.
- Tools that evaluate block decisions must consider block card VALUES (e.g. Survivor 8 > Defend 5),
  not just "has block card: yes/no".
```

### 3.2 `_DISCOVERY_SYSTEM` (skills/discovery.py)

Append to the existing system prompt:

```
HP efficiency matters: a fight won without losing HP is better than one where
HP was lost. Skills should guide the agent to minimize HP loss in every fight,
not just survive. "Tank the damage" is only acceptable when ALL energy is needed
for a kill this turn AND there are no 0-cost block options.
```

### 3.3 `build_distill_prompt` (brain/prompts/distill.py)

Add to the Instructions section:

```
When comparing wins vs losses, also analyze HP efficiency: runs that minimized
HP loss through non-boss fights preserved more resources for boss encounters.
A run that won 5 combats but lost 60% HP in each is weaker than one that won
5 combats losing 10% HP each, even if both reached the same floor.
```

## Verification

### Replay test for Part 1
Use the saved `_replay_call.json` to verify `multi_enemy_incoming_damage.py` fix:
- Baseline: 5/5 chose Defend (bug reproduced)
- After fix: should choose Survivor (highest block card)

### Unit tests for Part 1
- `multi_enemy_incoming_damage.py`: update TEST_CASES, verify `BLOCK_OPTIMAL` + `best_block` output
- `ramp_enemy_turn_cost.py`: verify warning text no longer contains "NEVER"

### Manual review for Parts 2-3
- Read the modified skill text and prompt text
- Verify no contradictions with existing system prompt (which already says "cherish every single point")

## Future Work (not in this spec)

- **Evaluation metrics**: `record_outcome` should accept `hp_efficiency: float` (hp_after/hp_before) to weight skill confidence by HP preservation, not just win/loss.
- **Tool effectiveness**: `compute_effectiveness` should incorporate "HP delta when tool hint was used vs not used" — requires A/B tracking infrastructure.
- **MEDIUM-severity tools**: `early_game_survival_gate.py`, `event_cost_survival_check.py`, etc. have binary survival logic that doesn't actively cause bad decisions but could be improved to report HP efficiency.
