# Skill Validation Pipeline Design

**Date:** 2026-04-07
**Status:** Approved
**Motivation:** Evolved skills bypass all validation — hallucinated content enters prompt at 99%+ confidence. Pinpoint case study: evolution engine wrote factually wrong motivation ("HEALED enemy by 9 HP" when replay shows enemy was killed), with overly broad trigger (`boss/elite/monster` with no card/enemy filter), and 202/202 success rate from unrelated hallway victories.

## Problem Statement

Five gaps in the current `write_skill` path vs `author_tool`:

1. **No query tool routing** — `recall_encounter` returns "Unknown tool" in evolution engine (ToolExecutor not connected)
2. **No factual validation** — LLM hallucinations in skill content/motivation pass unchecked
3. **No injection simulation** — no test that the skill actually improves decisions
4. **No quality judge** — unlike author_tool's 8-stage pipeline, write_skill has 0 validation stages
5. **Trigger too coarse** — write_skill schema exposes only 2 of 16 SkillTrigger fields; card-specific skills match all combats

## Design

### 1. Query Tool Routing Fix

**File:** `src/brain/evolution_engine.py`

Connect ToolExecutor to EvolutionEngine's `_execute_tool()` three-stage dispatch:

```
_execute_tool(name, tool_input):
  Stage 1: Write tools (author_tool, write_skill, etc.) → _execute_write_tool()
  Stage 2: Static query tools (recall_encounter) → ToolExecutor   [NEW]
  Stage 3: Dynamic tools → DynamicToolRegistry
  Stage 4: fallback → "Unknown tool"
```

**Changes:**
- `EvolutionEngine.__init__()` accepts optional `ToolExecutor` (or `MemoryManager` to construct one)
- `_execute_tool()` checks ToolExecutor handlers between write tools and dynamic tools
- `_post_run_evolution()` in `loop.py` passes `self._memory` to EvolutionEngine constructor
- ToolExecutor's query tool schemas added to `all_tools` list so LLM sees them

**System prompt update** — add to `EVOLUTION_SYSTEM_PROMPT`:
```
MANDATORY WORKFLOW:
1. BEFORE writing any skill, call recall_encounter with the relevant enemy_key
   and character to check if similar encounters exist in history.
2. BEFORE writing any skill, call get_performance_stats to understand patterns.
3. Only after reviewing historical data, decide whether a skill is truly needed.
```

### 2. write_skill Schema Expansion + Trigger Auto-Classification

**File:** `src/brain/write_tools.py`

#### 2.1 Schema Changes

Add to WRITE_SKILL `input_schema.properties`:

```json
"trigger_requires_cards": {
  "type": "array",
  "items": {"type": "string"},
  "description": "Card names that must be in hand or deck for this skill to activate. Required for card-specific skills."
},
"trigger_character": {
  "type": "array",
  "items": {"type": "string"},
  "description": "Characters this skill applies to (e.g., ['silent']). Empty = all characters."
}
```

Total trigger fields exposed to LLM: `trigger_state_types`, `trigger_enemy_names`, `trigger_requires_cards`, `trigger_character` (4 fields).

#### 2.2 Trigger Auto-Classification

**File:** `src/brain/evolution_engine.py` — in `_handle_write_skill()`

After basic validation, before the 4-stage pipeline:

1. **Content scan** — scan skill `content` + `motivation` against card names from `knowledge/cards.md` and enemy names from `knowledge/monsters.md`
2. **Auto-fill logic:**

| Detected in content | LLM provided | Action |
|---------------------|--------------|--------|
| Card name(s) | `trigger_requires_cards` empty | Auto-fill `requires_cards` with detected card names |
| Card name(s) | `trigger_requires_cards` set | Use LLM-provided value (trust explicit) |
| Enemy name(s) | `trigger_enemy_names` empty | Auto-fill `enemy_names` with detected enemy names |
| Enemy name(s) | `trigger_enemy_names` set | Use LLM-provided value |
| Neither | — | General strategy, wide trigger acceptable |

This ensures card-specific skills like "Pinpoint targets weakest enemy" always get `requires_cards={"Pinpoint"}` even if the LLM forgets to set it.

#### 2.3 Handler Changes

**File:** `src/brain/evolution_engine.py` — `_handle_write_skill()`

Read new fields from `tool_input`:
```python
requires_cards = tool_input.get("trigger_requires_cards", [])
character = tool_input.get("trigger_character", [])
```

Pass to SkillTrigger constructor:
```python
trigger = SkillTrigger(
    state_types=...,
    enemy_names=...,
    requires_cards=frozenset(requires_cards),
    character=frozenset(character),
)
```

### 3. Multi-Stage Validation Pipeline

**File:** `src/brain/evolution_engine.py` — new method `_validate_skill()` called from `_handle_write_skill()` after basic checks pass.

All LLM calls use the evolution backend (`self._backend`) which routes to the configured evolution model (currently GPT-5.4 Thinking via OpenAI-compatible relay).

#### Stage 1: Factual Consistency Check

**Purpose:** Detect factual hallucinations in skill content/motivation by cross-referencing combat replay data.

**Input:** skill content, motivation, combat replay excerpt (from evolution message history)

**Method:** Single LLM call (evolution model, low max_tokens ~500):

```
Given this combat replay data:
{relevant_combat_replay}

The agent wants to create this skill:
Name: {skill_name}
Content: {content}
Motivation: {motivation}

Check FACTUAL CLAIMS in the content and motivation against the replay data:
1. Does the replay support the claimed card behavior?
2. Are damage/HP numbers consistent with what happened?
3. Is the causal chain correct (did X actually cause Y)?

Verdict: CONSISTENT / INCONSISTENT / UNVERIFIABLE
If INCONSISTENT, quote the specific wrong claim.
```

**Behavior:**
- **INCONSISTENT** → REJECT with quoted wrong claim
- **UNVERIFIABLE** → pass (skill may reference cross-run knowledge)
- **CONSISTENT** → pass
- LLM call failure → pass (don't block on transient errors)

**Replay extraction:** The `run_context` string passed to `run_evolution()` already contains `## Combat Replays` sections (built by `build_evolution_context()`). Extract the replay block whose enemy name matches the skill's `trigger.enemy_names` or whose card mentions match `trigger.requires_cards`. If `run_context` has no matching replay, also try `MemoryManager.combat_store` for recent episodes matching the enemy key. If still no relevant replay found, skip this stage.

#### Stage 2: Injection Simulation

**Purpose:** Verify the skill would actually improve a decision if injected.

**Input:** skill (formatted as prompt injection), matching StateSnapshots

**Method:**
1. Query `StateSnapshotStore` for snapshots matching the skill's trigger (state_types, enemy_names via substring, requires_cards via hand scan). Max 3 snapshots.
2. If no matching snapshots → skip stage (cold start grace)
3. For each snapshot, single LLM call (evolution model, ~500 tokens):

```
You are evaluating a strategy skill for a Slay the Spire 2 agent.

Game state summary:
{snapshot: HP, energy, hand cards, enemies with HP/intents, block, powers}

Proposed skill to inject:
"{skill_content}"

Questions:
1. Is this skill RELEVANT to this game state? (yes/no)
2. If the agent followed this skill, would the DECISION change? (yes/no/maybe)
3. If the decision changes, is the NEW decision BETTER? (yes/no/unclear)

Verdict: HELPFUL / IRRELEVANT / HARMFUL
```

**Behavior:**
- Any **HARMFUL** → REJECT
- All **IRRELEVANT** → WARN (logged, doesn't block — trigger may be too narrow for available snapshots)
- At least 1 **HELPFUL** → pass
- LLM call failure → pass

#### Stage 3: Over-Match Check (No LLM)

**Purpose:** Verify trigger doesn't fire on irrelevant game states.

**Method:**
1. Query `StateSnapshotStore` for snapshots that should NOT match (different state_types, or combat snapshots where hand doesn't contain required cards). Max 2 snapshots.
2. Run `SkillTrigger.matches()` against each snapshot's parsed state.
3. If trigger matches a non-relevant snapshot → WARN + log suggestion to narrow trigger.

**Behavior:** WARN only, never hard reject. General strategy skills legitimately have wide triggers.

#### Stage 4: LLM Quality Judge

**Purpose:** Final quality gate — is the skill novel, specific, and safe?

**Method:** Single LLM call (evolution model, ~300 tokens):

```
Evaluate this strategy skill for a Slay the Spire 2 agent:

Skill: "{skill_name}"
Content: "{skill_content}"
Category: {category}
Trigger: state_types={state_types}, enemy_names={enemy_names}, requires_cards={requires_cards}

Questions:
1. Does this provide knowledge NOT already obvious from card descriptions?
2. Is it specific enough to change a decision in a concrete situation?
3. Could following this advice EVER lead to a worse outcome?

Verdict: HELPFUL / REDUNDANT / MISLEADING
```

**Behavior:**
- **MISLEADING** → REJECT
- **REDUNDANT** → REJECT
- **HELPFUL** or unparseable → pass
- LLM call failure → pass

#### Validation Flow Summary

```
write_skill request
  │
  ├─ Basic checks (name/content/length/dedup) ─── existing
  │
  ├─ Trigger auto-classification (scan content → auto-fill requires_cards/enemy_names) ─── new
  │
  ├─ Stage 1: Factual Consistency (1 LLM call)
  │   └─ INCONSISTENT → REJECT
  │
  ├─ Stage 2: Injection Simulation (1-3 LLM calls)
  │   └─ any HARMFUL → REJECT
  │
  ├─ Stage 3: Over-Match Check (0 LLM calls)
  │   └─ WARN only
  │
  ├─ Stage 4: Quality Judge (1 LLM call)
  │   └─ MISLEADING/REDUNDANT → REJECT
  │
  └─ All passed → skill_library.add() + save()
```

**Cost budget:** 3-5 LLM calls per skill write. Max 3 skills per evolution run → max 15 calls. Using GPT-5.4 via OpenAI-compatible relay — acceptable cost.

### 4. Outcome Tracking (No Changes Needed)

The current `record_outcome()` logic (combat end → all injected skills share win/loss) is adequate AFTER trigger precision is fixed:

- With `requires_cards={"Pinpoint"}`, the Pinpoint skill only activates in combats where Pinpoint is in hand/deck
- Win/loss signal becomes relevant (no more hallway-fight confidence inflation)
- `sweep_retirements()` (usage ≥ 5, success rate < 20% → deactivated) works correctly with clean input

No changes to `record_outcome()`, `sweep_retirements()`, or `with_usage()`.

## Files Changed

| File | Change |
|------|--------|
| `src/brain/write_tools.py` | Add `trigger_requires_cards`, `trigger_character` to WRITE_SKILL schema |
| `src/brain/evolution_engine.py` | Connect ToolExecutor routing; update system prompt; add trigger auto-classification; add 4-stage `_validate_skill()` pipeline in `_handle_write_skill()` |
| `src/agent/loop.py` | Pass MemoryManager to EvolutionEngine constructor in `_post_run_evolution()` |
| `src/brain/tool_executor.py` | Extract `recall_encounter` tool schema as a reusable constant so EvolutionEngine can include it in `all_tools` |

## Existing Skills Remediation

After deploying this pipeline, existing evolved skills with overly broad triggers should be audited. Specifically:
- Skills mentioning specific card names but lacking `requires_cards` in trigger
- Skills mentioning specific enemies but lacking `enemy_names` in trigger

A one-time migration script can scan `data/skills/skills.json`, detect card/enemy mentions in content, and backfill trigger fields.

## Verification

The Pinpoint case serves as the gold standard test:
1. **Factual consistency** — "HEALED enemy by 9 HP" contradicts replay showing enemy killed → Stage 1 REJECT
2. **Trigger precision** — content mentions "Pinpoint" → auto-fill `requires_cards={"Pinpoint"}` → only activates in hand-with-Pinpoint combats
3. **Quality judge** — skill content about "target lowest HP" is actually reasonable strategy → Stage 4 HELPFUL (would pass if Stage 1 didn't catch the hallucination first)
