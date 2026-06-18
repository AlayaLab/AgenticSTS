# HP Efficiency Bias Fix — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate offensive bias in dynamic tools and seed skills that causes unnecessary HP loss, and prevent future self-evolution from generating similarly biased content.

**Architecture:** Direct edits to 2 dynamic tool files, 1 seed skill JSON (+ runtime skills.json), and 3 Python prompt files. No new files created. All changes are content/text modifications to existing files.

**Tech Stack:** Python, JSON

**Spec:** `docs/superpowers/specs/2026-03-28-hp-efficiency-bias-fix-design.md`

---

### Task 1: Fix `multi_enemy_incoming_damage.py` — eliminate CAN_SKIP_BLOCK

**Files:**
- Modify: `data/evolution/tools/multi_enemy_incoming_damage.py`

- [ ] **Step 1: Rewrite the tool**

Replace the entire file content with the fixed version. Key changes:
- Add `block_cards_in_hand` parameter to SCHEMA and `execute()`
- Replace 3-tier recommendation (`MUST_BLOCK`/`BLOCK_ADVISED`/`CAN_SKIP_BLOCK`) with 4-tier (`MUST_BLOCK`/`BLOCK_ADVISED`/`BLOCK_OPTIMAL`/`FREE_OFFENSE`)
- Add energy-aware best-block-card selection
- Update description to remove "GO/NO-GO on skipping block"
- Replace all 3 TEST_CASES with 5 new ones covering every tier

```python

SCHEMA = {
    "name": "multi_enemy_incoming_damage",
    "description": (
        "Given a list of enemies with their intents and damage values, returns total incoming "
        "damage this turn, which enemies are attacking, and which block card to play. "
        "Use BEFORE deciding block card allocation."
    ),
    "parameters": {
        "enemies": {
            "type": "array",
            "description": "List of enemies. Each has 'name', 'intent' ('attack'|'buff'|'debuff'|'unknown'), and 'damage' (int, 0 if not attacking).",
        },
        "current_block": {
            "type": "integer",
            "description": "Block already on the player this turn.",
            "default": 0,
        },
        "current_hp": {
            "type": "integer",
            "description": "Player's current HP.",
        },
        "block_cards_in_hand": {
            "type": "array",
            "description": "Block cards in hand. Each has 'name', 'block_amount', 'energy_cost'.",
            "default": [],
        },
    },
    "required": ["enemies", "current_hp"],
}

APPLICABLE_STATES = ["monster", "elite", "boss"]


def execute(enemies, current_hp, current_block=0, block_cards_in_hand=None):
    if block_cards_in_hand is None:
        block_cards_in_hand = []

    attacking = [e for e in enemies if e.get("intent") == "attack" and e.get("damage", 0) > 0]
    unknown = [e for e in enemies if e.get("intent") == "unknown"]
    total_damage = sum(e.get("damage", 0) for e in attacking)
    # unknown enemies conservatively assumed to deal 6 damage each (floor 1-10 baseline)
    total_damage += sum(e.get("damage", 6) for e in unknown)

    net_damage = max(0, total_damage - current_block)
    survives = current_hp - net_damage > 0
    hp_after = current_hp - net_damage

    attackers_summary = [
        {"name": e["name"], "damage": e.get("damage", 6)} for e in attacking + unknown
    ]

    # Find best block card: prefer cheapest card that fully covers damage,
    # fall back to highest block value if none fully covers.
    best_block = None
    if block_cards_in_hand:
        covers = [c for c in block_cards_in_hand if c.get("block_amount", 0) >= net_damage]
        if covers:
            best_block = min(covers, key=lambda c: c.get("energy_cost", 99))
        else:
            best_block = max(block_cards_in_hand, key=lambda c: c.get("block_amount", 0))

    # Four-tier recommendation
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
        note = "FATAL — you will die this turn. Must block."
    elif best_block and best_block.get("block_amount", 0) >= net_damage:
        note = (
            f"{net_damage} incoming. Best block: {best_block['name']} "
            f"({best_block['block_amount']} block) — fully covers. "
            f"Use remaining energy for offense."
        )
    elif best_block:
        remainder = net_damage - best_block.get("block_amount", 0)
        note = (
            f"{net_damage} incoming. Best block: {best_block['name']} "
            f"({best_block['block_amount']} block) — reduces to "
            f"{remainder} net damage."
        )
    else:
        note = f"{net_damage} incoming, no block cards available."

    result = {
        "total_incoming": total_damage,
        "current_block": current_block,
        "net_damage": net_damage,
        "hp_after": hp_after,
        "survives": survives,
        "recommendation": recommendation,
        "attackers": attackers_summary,
        "note": note,
    }
    if best_block:
        result["best_block"] = {
            "name": best_block["name"],
            "block_amount": best_block.get("block_amount", 0),
            "energy_cost": best_block.get("energy_cost", 0),
        }
    else:
        result["best_block"] = None
    return result


TEST_CASES = [
    # 1. Multi-enemy attack — BLOCK_ADVISED (>30% HP)
    {
        "input": {
            "enemies": [
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
                {"name": "Rat", "intent": "attack", "damage": 8},
            ],
            "current_hp": 20,
            "current_block": 14,
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
            "current_hp": 15,
            "current_block": 6,
        },
        "expected": {"total_incoming": 24, "recommendation": "MUST_BLOCK"},
    },
    # 3. All enemies buffing — FREE_OFFENSE
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
            "best_block": {"name": "Survivor", "block_amount": 8, "energy_cost": 1},
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

- [ ] **Step 2: Verify the tool loads and passes its own test cases**

Run:
```bash
cd AgenticSTS && python -c "
from src.brain.dynamic_tools import DynamicToolRegistry
import config
r = DynamicToolRegistry(config.EVOLUTION_TOOLS_DIR)
loaded = r.load_all()
print(f'Loaded: {loaded} tools')
tool = r.get('multi_enemy_incoming_damage')
assert tool is not None, 'Tool not found'
print(f'Tool loaded: {tool.name}')
# Run test cases
from src.brain.dynamic_tools import _validate_test_case
for i, tc in enumerate(tool.test_cases):
    result = _validate_test_case(tool.execute_fn, tc, tool.name)
    status = 'PASS' if result is None else f'FAIL: {result}'
    print(f'  TC{i+1}: {status}')
"
```
Expected: all 5 test cases PASS.

- [ ] **Step 3: Run existing test suite**

Run: `python -m pytest tests/ -x --tb=short -q`
Expected: all tests pass (no existing tests depend on `CAN_SKIP_BLOCK` output value).

- [ ] **Step 4: Commit**

```bash
git add data/evolution/tools/multi_enemy_incoming_damage.py
git commit -m "fix: replace CAN_SKIP_BLOCK with 4-tier block recommendation + best card advice"
```

---

### Task 2: Fix `ramp_enemy_turn_cost.py` — remove "NEVER block" rule

**Files:**
- Modify: `data/evolution/tools/ramp_enemy_turn_cost.py:98`

- [ ] **Step 1: Replace the warning text on line 98**

Current line 98:
```python
        "warning": f"Each turn costs +{ramp_per_turn} more damage. Turn {turns_to_kill} attack: {current_attack + ramp_per_turn * (turns_to_kill - 1)}. NEVER play a pure block turn if you have any attack card.",
```

Replace with:
```python
        "warning": f"Each turn costs +{ramp_per_turn} more damage. Turn {turns_to_kill} attack: {current_attack + ramp_per_turn * (turns_to_kill - 1)}. Pure block turns delay the kill and let the enemy ramp further. Mix offense + defense each turn to minimize total HP loss. Exception: a full-block turn may be correct if incoming damage exceeds your total block capacity.",
```

- [ ] **Step 2: Verify tool loads**

Run:
```bash
cd AgenticSTS && python -c "
from src.brain.dynamic_tools import DynamicToolRegistry
import config
r = DynamicToolRegistry(config.EVOLUTION_TOOLS_DIR)
r.load_all()
tool = r.get('ramp_enemy_turn_cost')
assert tool is not None
# Verify 'NEVER' is not in the warning output
result = tool.execute_fn(enemy_hp=37, current_attack=9, ramp_per_turn=2, player_damage_per_turn=6, player_block_per_turn=10, player_hp=10)
assert 'NEVER' not in result['warning'], f'Still contains NEVER: {result[\"warning\"]}'
print('OK: warning text updated, no NEVER')
"
```

- [ ] **Step 3: Commit**

```bash
git add data/evolution/tools/ramp_enemy_turn_cost.py
git commit -m "fix: replace absolute NEVER-block rule with conditional guidance in ramp tool"
```

---

### Task 3: Fix boss strategy seed skill — add survival check condition

**Files:**
- Modify: `src/skills/seeds/core_boss_strategy.json`
- Modify: `data/skills/skills.json` (entry `seed_core_boss_strategy`)

- [ ] **Step 1: Update the seed file**

In `src/skills/seeds/core_boss_strategy.json`, replace the `content` field (item 5 and item 6 in the list):

Change `content` from:
```
... (5) HP doesn't matter after Boss — you heal to full between Acts. Play to WIN, trade HP for damage. (6) For specific boss/elite mechanics ...
```
To:
```
... (5) After beating a Boss, HP fully restores between Acts. You CAN play more aggressively — but first verify you survive the next enemy turn. Never go all-in if incoming damage would kill you. (6) For specific boss/elite mechanics ...
```

Also replace `examples` array item 3 from:
```json
"Boss at 30 HP, you at 15 HP: go all-in on damage, don't waste energy on Block"
```
To:
```json
"Boss at 30 HP, you at 40 HP, 12 incoming: offense-heavy, accept some damage. Boss at 30 HP, you at 15 HP, 20 incoming: block first, kill next turn"
```

- [ ] **Step 2: Propagate to runtime skills.json**

In `data/skills/skills.json`, find the entry with `"skill_id": "seed_core_boss_strategy"` and apply the same `content` and `examples` changes.

The skill library merges seeds on startup, but `skills.json` persists runtime state. Both files must match to avoid the seed overwriting the runtime fix or vice versa.

- [ ] **Step 3: Verify seed loads correctly**

Run:
```bash
cd AgenticSTS && python -c "
import json
with open('src/skills/seeds/core_boss_strategy.json') as f:
    seeds = json.load(f)
content = seeds[0]['content']
assert 'trade HP for damage' not in content, 'Old text still present'
assert 'verify you survive the next enemy turn' in content, 'New text missing'
examples = seeds[0]['examples']
assert any('block first' in e for e in examples), 'New example missing'
assert not any('don\\'t waste energy on Block' in e for e in examples), 'Old example still present'
print('OK: seed skill updated correctly')
"
```

- [ ] **Step 4: Commit**

```bash
git add src/skills/seeds/core_boss_strategy.json data/skills/skills.json
git commit -m "fix: add survival check to boss strategy seed — no blind all-in at low HP"
```

---

### Task 4: Add HP efficiency principle to Evolution prompt

**Files:**
- Modify: `src/brain/evolution_engine.py:43-77`

- [ ] **Step 1: Append HP efficiency block to EVOLUTION_SYSTEM_PROMPT**

After the closing `"""` of the existing `TOOL AUTHORING REQUIREMENTS` section (line 77), the string ends. Insert the new principle before the closing `"""`:

Find the end of the prompt (the line with `— these cannot be auto-bound."""`), and change it to:

```python
- Do NOT create tools with parameters like num_shivs, target_enemy_index, damage_multiplier — these cannot be auto-bound.

HP EFFICIENCY PRINCIPLE:
- A fight won without losing HP is strictly better than one where HP was lost. \
Every tool you create must treat HP as a run-wide resource, not just a survival buffer.
- NEVER create tools that recommend "skip block" when incoming damage > 0. \
The correct output is WHICH block card to play, not WHETHER to block.
- "Free offense turns" ONLY exist when ALL enemies have non-attack intents (Buff/Debuff/Status). \
Any incoming damage — even 3-4 points — should be blocked if energy and cards allow.
- Tools that evaluate block decisions must consider block card VALUES (e.g. Survivor 8 > Defend 5), \
not just "has block card: yes/no"."""
```

- [ ] **Step 2: Verify prompt compiles**

Run:
```bash
cd AgenticSTS && python -c "
from src.brain.evolution_engine import EVOLUTION_SYSTEM_PROMPT
assert 'HP EFFICIENCY PRINCIPLE' in EVOLUTION_SYSTEM_PROMPT
assert 'WHICH block card to play' in EVOLUTION_SYSTEM_PROMPT
assert 'CAN_SKIP_BLOCK' not in EVOLUTION_SYSTEM_PROMPT
print(f'OK: evolution prompt updated ({len(EVOLUTION_SYSTEM_PROMPT)} chars)')
"
```

- [ ] **Step 3: Commit**

```bash
git add src/brain/evolution_engine.py
git commit -m "feat: add HP efficiency principle to evolution system prompt"
```

---

### Task 5: Add HP efficiency to skill discovery prompt

**Files:**
- Modify: `src/skills/discovery.py:27-37`

- [ ] **Step 1: Append HP efficiency guidance to `_DISCOVERY_SYSTEM`**

Change the `_DISCOVERY_SYSTEM` string. After the last line (`Focus on patterns that led to success or patterns whose absence led to failure."`), add:

```python
_DISCOVERY_SYSTEM = """\
You are an expert Slay the Spire 2 strategy analyst. Your task is to extract
reusable strategic skills from gameplay run data.

A "skill" is a specific, actionable piece of game knowledge that helps make
better decisions. Skills should be:
1. Specific enough to be useful (not just "play good cards")
2. General enough to apply across multiple situations
3. Testable — you can tell if following the skill helped or hurt

Focus on patterns that led to success or patterns whose absence led to failure.

HP efficiency matters: a fight won without losing HP is better than one where \
HP was lost. Skills should guide the agent to minimize HP loss in every fight, \
not just survive. "Tank the damage" is only acceptable when ALL energy is needed \
for a kill this turn AND there are no 0-cost block options."""
```

- [ ] **Step 2: Verify import works**

Run:
```bash
cd AgenticSTS && python -c "
from src.skills.discovery import _DISCOVERY_SYSTEM
assert 'HP efficiency' in _DISCOVERY_SYSTEM
assert 'Tank the damage' in _DISCOVERY_SYSTEM
print(f'OK: discovery system prompt updated ({len(_DISCOVERY_SYSTEM)} chars)')
"
```

- [ ] **Step 3: Commit**

```bash
git add src/skills/discovery.py
git commit -m "feat: add HP efficiency guidance to skill discovery prompt"
```

---

### Task 6: Add HP efficiency to rule distillation prompt

**Files:**
- Modify: `src/brain/prompts/distill.py:33-41`

- [ ] **Step 1: Append HP efficiency guidance to Instructions section**

In the `build_distill_prompt` function, the Instructions section starts at line 33. Add the HP efficiency guidance after the existing instructions, before the closing `""")`:

Change:
```python
    parts.append("""
## Instructions
Extract 1-5 strategy rules. For each rule, output JSON:
```json
[
  {"rule_text": "...", "context": "combat|map|event|rest|reward|all", "confidence": 0.5}
]
```
Rules should be specific and actionable. Confidence 0.5 = unverified hypothesis.""")
```

To:
```python
    parts.append("""
## Instructions
Extract 1-5 strategy rules. For each rule, output JSON:
```json
[
  {"rule_text": "...", "context": "combat|map|event|rest|reward|all", "confidence": 0.5}
]
```
Rules should be specific and actionable. Confidence 0.5 = unverified hypothesis.

When comparing wins vs losses, also analyze HP efficiency: runs that minimized \
HP loss through non-boss fights preserved more resources for boss encounters. \
A run that won 5 combats but lost 60% HP in each is weaker than one that won \
5 combats losing 10% HP each, even if both reached the same floor.""")
```

- [ ] **Step 2: Verify import works**

Run:
```bash
cd AgenticSTS && python -c "
from src.brain.prompts.distill import build_distill_prompt
prompt = build_distill_prompt(['win1'], ['loss1'])
assert 'HP efficiency' in prompt
assert 'non-boss fights' in prompt
print(f'OK: distill prompt updated ({len(prompt)} chars)')
"
```

- [ ] **Step 3: Commit**

```bash
git add src/brain/prompts/distill.py
git commit -m "feat: add HP efficiency guidance to rule distillation prompt"
```

---

### Task 7: Run full test suite + replay verification

**Files:**
- Read: `_replay_call.json` (existing replay data from brainstorming)
- Read: `_replay_test.py` (existing replay test script)

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -x --tb=short -q`
Expected: all 568+ tests pass.

- [ ] **Step 2: Run replay test to verify multi_enemy_incoming_damage fix**

The preprocessor hint in `_replay_call.json` still contains the old `CAN_SKIP_BLOCK` text (it was captured before the fix). The replay test verifies that the new tool's output would change the LLM's block card choice.

Run the baseline and fix3 variants to confirm the fix still works:
```bash
cd AgenticSTS && python _replay_test.py 2>&1 | tail -8
cd AgenticSTS && python _replay_test.py --fix 3 2>&1 | tail -8
```

Expected:
- Baseline: 5/5 Defend (reproduces bug — replay uses old cached prompt)
- Fix 3: 5/5 Survivor (confirms hint wording change works)

Note: In live gameplay, the preprocessor will now inject the new `BLOCK_OPTIMAL` + `best_block: Survivor` hint instead of `CAN_SKIP_BLOCK`. The replay test validates the prompt-level fix; the tool change ensures future runs get the correct hint automatically.

- [ ] **Step 3: Clean up temporary files**

```bash
rm -f _replay_call.json _replay_test.py _check.py
```

- [ ] **Step 4: Final commit**

```bash
git add -A
git commit -m "chore: clean up replay test artifacts"
```
