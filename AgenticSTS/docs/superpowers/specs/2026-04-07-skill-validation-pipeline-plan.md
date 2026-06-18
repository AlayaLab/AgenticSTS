# Skill Validation Pipeline — Implementation Plan

**Spec:** `2026-04-07-skill-validation-pipeline-design.md`
**Date:** 2026-04-07

## Phase 1: Query Tool Routing + System Prompt

### Step 1.1: Extract recall_encounter schema as reusable constant

**File:** `src/brain/tool_executor.py`

Add a module-level `QUERY_TOOL_SCHEMAS` list containing the Anthropic/OpenAI tool schema for `recall_encounter`:

```python
RECALL_ENCOUNTER_SCHEMA: dict = {
    "name": "recall_encounter",
    "description": "Recall past combat encounters from memory...",
    "input_schema": {
        "type": "object",
        "properties": {
            "enemy_key": {"type": "string", "description": "Enemy name to search for."},
            "character": {"type": "string", "description": "Character name to filter by."},
        },
    },
}

QUERY_TOOL_SCHEMAS: list[dict] = [RECALL_ENCOUNTER_SCHEMA]
```

**Test:** Import and verify schema is valid dict with "name" key.

### Step 1.2: Connect ToolExecutor in EvolutionEngine._execute_tool()

**File:** `src/brain/evolution_engine.py`

In `_execute_tool()`, add Stage 2 between write tools and dynamic tools:

```python
# Stage 2: Static query tools (recall_encounter, etc.)
if self._tool_executor is not None:
    handler = self._tool_executor._handlers.get(name)
    if handler is not None:
        try:
            return self._tool_executor.execute(name, tool_input)
        except Exception as exc:
            return f"Query tool {name} error: {exc}"
```

**Cleaner approach:** Use `ToolExecutor.execute()` directly — it already has the dispatch + error handling:

```python
# Stage 2: Static query tools
if self._tool_executor is not None and name in self._tool_executor._handlers:
    return self._tool_executor.execute(name, tool_input)
```

### Step 1.3: Add query schemas to evolution tool list

**File:** `src/brain/evolution_engine.py` — `run_evolution()`

Currently `all_tools = list(WRITE_TOOLS)`. Change to:

```python
from src.brain.tool_executor import QUERY_TOOL_SCHEMAS

all_tools = list(WRITE_TOOLS) + list(QUERY_TOOL_SCHEMAS)
if self._dynamic_registry:
    all_tools.extend(self._dynamic_registry.get_normalized_schemas())
```

### Step 1.4: Update EVOLUTION_SYSTEM_PROMPT

**File:** `src/brain/evolution_engine.py`

Append to `EVOLUTION_SYSTEM_PROMPT`:

```
MANDATORY WORKFLOW:
1. BEFORE writing any skill, call recall_encounter with the relevant enemy_key
   and character to check if similar encounters exist in history.
2. BEFORE writing any skill, call get_performance_stats to understand patterns.
3. Only after reviewing historical data, decide whether a skill is truly needed.
```

**Verification for Phase 1:** Run agent with `STS2_EVOLUTION_ENABLED=true`. In evolution log, confirm `recall_encounter` calls appear and return data (not "Unknown tool").

---

## Phase 2: write_skill Schema + Trigger Auto-Classification

### Step 2.1: Expand WRITE_SKILL schema

**File:** `src/brain/write_tools.py`

Add two new properties to `WRITE_SKILL["input_schema"]["properties"]`:

```python
"trigger_requires_cards": {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Card names that must be in hand or deck for this skill to activate. "
        "Required when skill content mentions specific cards."
    ),
},
"trigger_character": {
    "type": "array",
    "items": {"type": "string"},
    "description": (
        "Characters this skill applies to (e.g., ['silent']). "
        "Empty = all characters."
    ),
},
```

### Step 2.2: Read new trigger fields in _handle_write_skill

**File:** `src/brain/evolution_engine.py` — `_handle_write_skill()`

After reading existing `state_types` and `enemy_names`, add:

```python
requires_cards = tool_input.get("trigger_requires_cards", [])
character = tool_input.get("trigger_character", [])
```

Pass to SkillTrigger constructor:

```python
trigger = SkillTrigger(
    state_types=normalize_state_types(state_types) if state_types else frozenset(),
    enemy_names=frozenset(enemy_names) if enemy_names else frozenset(),
    requires_cards=frozenset(requires_cards),
    character=frozenset(character),
)
```

### Step 2.3: Implement trigger auto-classification

**File:** `src/brain/evolution_engine.py` — new helper `_auto_classify_triggers()`

```python
def _auto_classify_triggers(
    self,
    content: str,
    motivation: str,
    explicit_cards: list[str],
    explicit_enemies: list[str],
) -> tuple[frozenset[str], frozenset[str]]:
    """Scan content for card/enemy mentions, auto-fill if LLM forgot.

    Returns (requires_cards, enemy_names) — possibly augmented.
    """
```

Logic:
1. Load card name set from `GameKnowledge().cards._cards` (lowercase keys → original `.name`)
2. Load enemy name set from `GameKnowledge().monsters._monsters`
3. Tokenize `content + " " + motivation` into words, match against both sets
4. For multi-word names (e.g. "Phrog Parasite"), use substring matching
5. If card names detected and `explicit_cards` empty → return detected cards
6. If enemy names detected and `explicit_enemies` empty → return detected enemies
7. Otherwise return originals

Call this in `_handle_write_skill()` right after reading trigger fields, before creating SkillTrigger.

**Verification for Phase 2:** Create a mock write_skill call with content "Pinpoint deals damage..." but no `trigger_requires_cards`. Verify auto-classification detects "Pinpoint" and adds it to trigger.

---

## Phase 3: 4-Stage Validation Pipeline

### Step 3.1: Scaffold _validate_skill() method

**File:** `src/brain/evolution_engine.py`

New method called from `_handle_write_skill()` after basic checks + auto-classification, before `skill_library.add()`:

```python
def _validate_skill(
    self,
    skill_name: str,
    content: str,
    motivation: str,
    trigger: SkillTrigger,
    category: str,
    run_context: str,
) -> tuple[bool, str]:
    """Run 4-stage validation. Returns (passed, reject_reason)."""

    # Stage 1: Factual Consistency
    result = self._validate_skill_facts(skill_name, content, motivation, trigger, run_context)
    if result: return False, result

    # Stage 2: Injection Simulation
    result = self._validate_skill_injection(skill_name, content, trigger)
    if result: return False, result

    # Stage 3: Over-Match Check (warn only)
    self._check_skill_overmatch(trigger)

    # Stage 4: Quality Judge
    result = self._validate_skill_quality(skill_name, content, category, trigger)
    if result: return False, result

    return True, ""
```

Need to thread `run_context` through — store it as `self._run_context` in `run_evolution()`.

### Step 3.2: Stage 1 — Factual Consistency

**File:** `src/brain/evolution_engine.py` — new method `_validate_skill_facts()`

1. Extract relevant combat replay from `self._run_context`:
   - Search for `## Combat Replay:` sections
   - Match by enemy names from trigger, or by card names from content
   - If no matching replay found, try `self._memory.combat_store.query()` for recent episodes
   - If still nothing, return `None` (skip stage)

2. Single LLM call via `self._backend.call()`:
   - system: short prompt about factual verification
   - user: combat replay + skill name/content/motivation
   - model: evolution model, max_tokens=500
   - Parse verdict: CONSISTENT / INCONSISTENT / UNVERIFIABLE

3. Return reject reason string if INCONSISTENT, else None.

Error handling: any exception → log warning, return None (don't block).

### Step 3.3: Stage 2 — Injection Simulation

**File:** `src/brain/evolution_engine.py` — new method `_validate_skill_injection()`

1. Query `self._snapshot_store.get_snapshots()`:
   - Filter by trigger's state_types
   - Max 3 snapshots
   - If empty → return None (skip stage)

2. For each snapshot, filter by trigger relevance:
   - Parse state via `parse_state(raw_state)`
   - Check if hand contains `trigger.requires_cards` (if specified)
   - Check if enemies match `trigger.enemy_names` (if specified)
   - Keep only relevant snapshots (at most 3)

3. For each relevant snapshot, LLM call:
   - Format game state summary (~200 tokens): HP, energy, hand cards, enemies with HP/intents
   - Include skill content
   - Parse verdict: HELPFUL / IRRELEVANT / HARMFUL

4. Decision:
   - Any HARMFUL → return reject reason
   - All IRRELEVANT → log warning, return None (don't block)
   - At least 1 HELPFUL → return None (pass)

Error handling: any exception → log warning, return None.

### Step 3.4: Stage 3 — Over-Match Check

**File:** `src/brain/evolution_engine.py` — new method `_check_skill_overmatch()`

1. Query `self._snapshot_store.get_snapshots()` for non-matching state types (max 2)
2. For each, parse state and run `trigger.matches()` with hand_cards and enemy names extracted from snapshot
3. If trigger matches a non-relevant snapshot → log warning with suggestion
4. Returns nothing (warn only, never reject)

Pure computation, no LLM calls.

### Step 3.5: Stage 4 — Quality Judge

**File:** `src/brain/evolution_engine.py` — new method `_validate_skill_quality()`

Adapted from existing `_validate_tool_quality()` pattern:

1. Single LLM call:
   - Format trigger info (state_types, enemy_names, requires_cards)
   - Questions about novelty, specificity, safety
   - Parse verdict: HELPFUL / REDUNDANT / MISLEADING

2. MISLEADING or REDUNDANT → return reject reason
3. HELPFUL or unparseable → return None (pass)

Error handling: any exception → log warning, return None.

### Step 3.6: Wire _validate_skill into _handle_write_skill

In `_handle_write_skill()`, after auto-classification and before `skill_library.add()`:

```python
passed, reject_reason = self._validate_skill(
    skill_name, content, motivation, trigger, category, self._run_context,
)
if not passed:
    return f"REJECTED: {reject_reason}"
```

**Verification for Phase 3:** Unit test with the Pinpoint case:
- Content: "Pinpoint deals damage equal to target enemy's current HP..."
- Motivation: "agent played Pinpoint on a Wriggler and it HEALED the enemy by 9 HP"
- Mock combat replay showing Wriggler HP 11→0 (killed)
- Expected: Stage 1 returns INCONSISTENT → REJECTED

---

## Phase 4: Existing Skills Remediation

### Step 4.1: One-time migration script

**File:** `scripts/backfill_skill_triggers.py` (new)

Scan `data/skills/skills.json`:
1. Load all card names from `GameKnowledge().cards`
2. Load all enemy names from `GameKnowledge().monsters`
3. For each evolved skill with `source="evolved"`:
   - Scan content for card name mentions → if found and `requires_cards` empty, add them
   - Scan content for enemy name mentions → if found and `enemy_names` empty, add them
4. Write updated skills.json
5. Print summary: "Updated N skills with refined triggers"

Run once after deployment: `python -m scripts.backfill_skill_triggers`

---

## Implementation Order + Dependencies

```
Phase 1 (routing)  ─┐
                     ├─ Phase 3 (validation pipeline)
Phase 2 (schema)   ─┘           │
                                 └─ Phase 4 (remediation script)
```

Phases 1 and 2 are independent, can be done in parallel.
Phase 3 depends on both (needs query routing for replay extraction, needs trigger fields for snapshot matching).
Phase 4 runs last (reuses auto-classification logic from Phase 2).

## Files Summary

| File | Phase | Changes |
|------|-------|---------|
| `src/brain/tool_executor.py` | 1 | Add `RECALL_ENCOUNTER_SCHEMA`, `QUERY_TOOL_SCHEMAS` constants |
| `src/brain/evolution_engine.py` | 1,2,3 | Route query tools; store run_context; auto-classify triggers; 4-stage `_validate_skill()` with `_validate_skill_facts()`, `_validate_skill_injection()`, `_check_skill_overmatch()`, `_validate_skill_quality()` |
| `src/brain/write_tools.py` | 2 | Add `trigger_requires_cards`, `trigger_character` to WRITE_SKILL schema |
| `scripts/backfill_skill_triggers.py` | 4 | New file — one-time migration |

No changes needed in `src/agent/loop.py` — `EvolutionEngine.__init__` already accepts `tool_executor` and `snapshot_store`, and `_post_run_evolution()` already passes them.

## Risk Mitigation

- **LLM call failures:** Every stage catches exceptions and returns None (pass). A transient API error never blocks skill creation entirely.
- **Empty StateSnapshotStore:** Stages 2-3 skip gracefully (cold start grace). First few runs after deployment may have reduced validation coverage.
- **Auto-classification false positives:** Card names like "Strike" are very common English words. Mitigation: only auto-classify card names with ≥5 characters and not in a stop list (`{"Strike", "Defend", "Block"}`). Short/common names require explicit LLM trigger.
- **Cost:** Max 5 LLM calls per skill × 3 skills per run = 15 calls. GPT-5.4 via relay at ~500 tokens each = ~7,500 tokens per run. Negligible vs 200-400 gameplay calls.
