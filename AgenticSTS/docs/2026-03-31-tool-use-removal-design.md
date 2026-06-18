# Tool-Use Removal: Text-Only Agent Architecture

**Date:** 2026-03-31
**Status:** Draft (Rev 3 — final pre-implementation)
**Scope:** Remove all tool_use from gameplay LLM calls; simplify to text-in/text-out

## Motivation

1. **Cross-provider complexity**: V2Backend has 500+ lines of Anthropic↔OpenAI tool schema translation, proxy-specific streaming workarounds, and tool-result reconstruction. Removing tool_use eliminates this.
2. **NeurIPS framing**: "Training-free self-evolution with plain text completion only, provider-agnostic, no native tool API dependency" is a stronger contribution statement.
3. **Query tool redundancy**: 2 of 3 query tools duplicate already-auto-injected context. The third (`recall_encounter`) provides value but doesn't need tool_use protocol.
4. **Multi-provider**: Currently Kimi 2.5 via OpenAI-compatible relay. Text-only means any LLM works without adapter code.

## Design Decisions

### D1: Query Tools → Deterministic Gated Retrieval

**Delete** `read_guide` and `assess_potion_value` entirely — their outputs are already auto-injected:
- `read_guide` → `retriever.py` already injects `combat_guide_hints`, `route_guide_hints`, `deck_guide_hints` from guide_store
- `assess_potion_value` → `conversation.py` already injects `## Potion Strategy` with timing tags per potion

**Delete** `combat_episode_hints` (the old run-retrospective format):
- Old format: `"Past: vs Automaton (5 rounds): WON, cards played: 18"` — this is run retrospective, not tactical foresight
- Removed from `retriever.py` and `WorkingContext`

**Replace with** `enemy_pattern_hints` — a new field focused on enemy behavior prediction:
- **Trigger**: ALL combat states (monster, elite, boss) where past episodes exist for the current enemy
- **Output**: Enemy action sequences only (not win/loss, not player cards played), with current round alignment
- **No episodes**: If no past fights exist for this enemy, omit the section entirely (no empty header)
- **Format**:
  ```
  ## Enemy Patterns
  Current round: R3
  These are possible move patterns from past fights, not guaranteed future actions.

  - Past fight 1: R1 Attack 12 → R2 Buff → R3 Attack 18 → R4 Attack 12 → R5 Multi-Attack 8x3
  - Past fight 2: R1 Attack 15 → R2 Attack 15 → R3 Buff → R4 Multi-Attack 10x3

  Likely upcoming after R3:
  - Pattern A: R4 Attack 12 → R5 Multi-Attack 8x3
  - Pattern B: R4 Multi-Attack 10x3
  ```
- **Round alignment**: Always display `Current round: R{N}` so the model knows where it is in the sequence
- **Upcoming section**: Extract upcoming 1-3 rounds from each past fight starting from current round, reducing alignment reasoning burden on the LLM
- **Budget**: Max 3 past episodes, max 8 rounds per episode, ~300 tokens total
- **Injection point**: Into `CombatConversation.add_combat_start()` for round 1; into `add_round_state()` for subsequent rounds (upcoming section updates as current round advances)
- **Data source**: `combat_store.query(enemy_key=..., character=..., limit=3)`

**Rendering ownership** (single source of truth, no double injection):
- **Round 1**: `retriever.py` formats full enemy patterns → `WorkingContext.enemy_pattern_hints` → `prompt_injector.py` renders `## Enemy Patterns` section → injected into the non-combat prompt path (which feeds into `CombatConversation.add_combat_start()` via `strategic_context`). CombatConversation does NOT independently inject patterns.
- **Round 2+**: `CombatConversation.add_round_state()` renders a compact `Likely upcoming after R{N}:` section (upcoming-only, not full history). This is the only path — prompt_injector is not re-invoked per round.
- Rule: full pattern → prompt_injector (once at combat start). Upcoming update → CombatConversation (per round).

**Memory model changes**:
- `WorkingContext`: remove `combat_episode_hints`, add `enemy_pattern_hints`
- `retriever.py`: remove episode hint formatting, add enemy pattern formatting with round alignment
- `prompt_injector.py`: `## Past Encounters` section replaced by `## Enemy Patterns` section

### D2: Decision Tools → Tagged JSON Output

Replace tool_use structured output with a `<decision>` tagged JSON block.

**LLM output format** (all state types):
```
[Free-form reasoning text — analysis, comparisons, observations]

<decision>
{"action": "play_card", "card_index": 2, "target_index": 0, "reasoning": "..."}
</decision>
```

**Combat plan format**:
```
[Free-form analysis text]

<decision>
{"plan": [{"type": "card", "card": "Backflip", "target_index": -1}, ...], "end_turn": true, "reasoning": "...", "note_to_future_self": "..."}
</decision>
```

**Local validation pipeline**:
1. Extract last `<decision>...</decision>` block from response text
2. `json.loads()` the content
3. Validate against existing schemas from `tool_schemas.py` (repurposed as local response schemas)
4. Semantic validation: card_index range, target_index validity, action enum membership
5. On failure: one repair turn with concise error message, then fallback (see D10)

**Schema preservation**: `tool_schemas.py` keeps its filename in this migration. Its role changes from "provider tool schema" to "local response schema" — update module docstring only. Rename to `response_schemas.py` in a future cleanup pass.

**`analysis` field**: Required for combat states (visible scratchpad with problem/key_observations/candidate_lines/chosen_line). Optional for non-combat states — validator accepts but does not require it.

### D3: V2Engine Simplification

**Before** (multi-turn tool-use loop):
```
For each round (up to max_query_rounds + 1):
  Call LLM with tools + tool_choice
  If query tool called → execute, append result, continue
  If decision tool called → return
```

**After** (single-call with optional repair):
```
1. Pre-inject all context (knowledge + skills + memory + enemy patterns + computed insights)
2. Single LLM call (no tools parameter, text completion only)
3. Extract <decision> block → validate → execute
4. If validation fails → one repair turn with error → validate → execute or fallback (D10)
```

**Key simplifications**:
- No `tools` parameter in API calls
- No `tool_choice` logic (thinking vs forced)
- No tool_result message construction
- No query round counting
- No parallel query tool execution
- `_agent_loop()` replaced by `_single_call()` + `_validate_and_repair()`

### D4: Combat Conversation Changes

**Remove** from `CombatConversation`:
- Tool-result message merging/compression logic
- Tool_use block handling in message history
- `add_tool_result()` method

**Add** to `CombatConversation`:
- Round 1 full patterns arrive via `strategic_context` parameter (rendered by prompt_injector, not by CombatConversation itself)
- `add_round_state()`: compact `Likely upcoming after R{N}:` section for round 2+ (CombatConversation owns this)

**Keep unchanged**:
- Multi-turn round accumulation (state updates per round)
- Round compression (keep_recent=1)
- Strategic notes and note_to_future_self

Messages become pure user/assistant text alternation — no tool_use/tool_result blocks.

### D5: V2Backend Simplification

**Practical approach**: Don't delete methods wholesale. Gameplay callers simply stop passing `tools=` and `tool_choice=` to `acall()`. The tool-handling code paths become dead for gameplay but remain active for evolution. Clean up in a later pass once evolution also migrates.

**Gameplay changes**:
- `acall()` called with `tools=None, tool_choice=None`
- Response is pure text — parse `<decision>` block from text content

**Kept for evolution** (used by EvolutionEngine):
- `extract_tool_uses()`, `build_tool_result()`
- `_normalize_openai_tools()`
- Tool_result block handling in `_to_openai_messages()`
- `tool_choice` parameter handling

**Kept for all paths**:
- Provider routing (Anthropic vs OpenAI-compatible)
- Streaming for thinking/reasoning capture (Kimi reasoning_content passback)
- `_to_openai_messages()` core logic (reasoning passback, message alternation)
- Prompt caching (system prompt stability)

### D6: System Prompt Changes

Bound to same phase as `<decision>` protocol (D2) — the prompt instruction is required for the tagged output to work.

**Remove** from all 4 system prompts (`system.py`):
- Query tool descriptions ("Available query tools: recall_encounter, read_guide, assess_potion_value")
- Query budget instructions ("max 5 rounds before MUST decide")
- Tool-use protocol ("call the decision tool to commit")

**Add** to all 4 system prompts:
- Output format instruction: "End your response with a `<decision>` block containing your choice as JSON"
- Per-state-type JSON example (derived from existing tool schemas, one compact example each)

### D7: Evolution Engine — No Behavioral Changes, Minimal Compatibility Fixes

The `EvolutionEngine` keeps tool_use for now:
- Only ~5 calls per run, all via Claude Opus (stable provider)
- Schema enforcement on write tools (`author_tool`, `write_skill`) has high safety value
- Low engineering ROI to migrate now
- Does not affect NeurIPS contribution (post-run internals, not the agent's gameplay protocol)

**Minimal compatibility changes required**:
- **Tool list assembly**: `run_evolution()` currently builds its tool list as `QUERY_TOOLS + WRITE_TOOLS + dynamic_registry schemas`. After `query_tools.py` is deleted, `QUERY_TOOLS` no longer exists. Fix: evolution tool list becomes `WRITE_TOOLS + dynamic_registry schemas` only. Evolution no longer advertises gameplay query tools at all — they provide no value to the evolution LLM (it analyzes run history, not live game state).
- **Dispatch**: EvolutionEngine's `_execute_tool()` stage-2 dispatch currently falls through to `ToolExecutor.execute()` for static query tools. After removal, any unexpected tool name hits the existing "unknown tool" fallback in ToolExecutor. No special compatibility shim needed.
- No behavioral change — evolution rarely called gameplay query tools, and removing them from the advertised tool list means the LLM won't attempt to call them.

### D8: Strategic Note & Analysis Extraction

Currently `strategic_note` and `analysis` are tool input fields extracted from tool_use responses.

**New extraction**: Parse from the `<decision>` JSON block — same fields, same downstream handling. No behavioral change.

`note_to_future_self` (combat only): same — extracted from decision JSON.

### D9: Prompt Instruction for `<decision>` Format

Add to each system prompt variant a compact instruction block:

```
## Output Format
Think through your decision, then output your choice in a <decision> tag:
<decision>
{JSON matching the schema for this state type}
</decision>
```

Per-state-type examples embedded in the system prompt (one example each, ~3-5 lines).

### D10: Fallback Policy on Validation Failure

Explicit fallback chain when `<decision>` parsing or validation fails:

**Combat (combat_plan / combat_action):**
1. Extract `<decision>` → validate schema + semantics
2. **If fails**: one repair turn — send error message as user message, LLM retries
3. **If repair fails**: deterministic combat fallback:
   - If playable cards exist → play first playable card (lowest energy cost, target first alive enemy)
   - If no playable cards → end_turn
   - Never use last-valid-decision (combat state changes every action)

**Non-combat (map, rest, shop, event, card_reward, card_select, hand_select):**
1. Extract `<decision>` → validate schema + semantics
2. **If fails**: one repair turn — send error message as user message, LLM retries
3. **If repair fails**: abort the run. Non-combat decisions are too consequential for random fallback (per existing project policy: NEVER add mechanical/random fallbacks for shop/rest/card/event/map — must abort run).

**Rules:**
- Never reuse a previous decision — game state has changed since then
- Fallback must be deterministic and rule-based, not random
- Combat fallback is a safety net only — it plays conservatively (lowest-cost card)
- Non-combat abort prevents the agent from making uninformed strategic decisions that ruin an entire run
- Repair turn message format: `"Your response did not contain a valid <decision> block. Error: {specific_error}. Please respond with a valid <decision> block."`

## Files Changed

| File | Change | Lines Est. |
|------|--------|-----------|
| `src/brain/query_tools.py` | Delete file | -120 |
| `src/brain/tool_executor.py` | Delete `_read_guide`, `_assess_potion_value`; extract enemy pattern logic into new `enemy_pattern_injector.py` | -200, +60 |
| `src/brain/tool_schemas.py` | Keep filename; update docstring; remove `get_v2_tools()`, `get_v2_combat_tools()`, `get_tool_choice()`, `_QUERY_TOOL_RELEVANCE`; add `validate_decision()` | ~-80, +60 |
| `src/brain/v2_engine.py` | Replace `_agent_loop()` with `_single_call()` + `_validate_and_repair()`; remove query tool dispatch, `QueryToolRecord`, `_PARAM_REMAP`; add `<decision>` extraction + fallback logic (D10) | ~-300, +180 |
| `src/brain/v2_backend.py` | Gameplay callers stop passing `tools`/`tool_choice`; tool methods kept for evolution; no deletions | ~-10 |
| `src/brain/conversation.py` | Remove tool-result merging; add upcoming enemy pattern in `add_round_state()` (round 1 patterns via strategic_context, not here) | ~-100, +40 |
| `src/brain/prompts/system.py` | Remove query tool descriptions; add `<decision>` format instructions + per-state JSON examples | ~-40, +80 |
| `src/agent/loop.py` | Remove ToolExecutor init for query tools; wire enemy pattern injector; remove query tool references | ~-30 |
| `src/brain/evolution_engine.py` | Remove `QUERY_TOOLS` from tool list assembly in `run_evolution()`; no dispatch shim needed | ~-5, +2 |
| `src/memory/models_v2.py` | `WorkingContext`: remove `combat_episode_hints`, add `enemy_pattern_hints` | ~-5, +5 |
| `src/memory/retriever.py` | Remove episode hint formatting; add enemy pattern formatting with round alignment | ~-30, +50 |
| `src/memory/prompt_injector.py` | Replace `## Past Encounters` with `## Enemy Patterns` | ~-5, +5 |
| `src/brain/enemy_pattern_injector.py` | New file: `format_enemy_patterns(episodes, current_round)` → text | +80 |
| `src/brain/write_tools.py` | No change (evolution keeps tool_use) | |
| `src/brain/dynamic_tools.py` | No change (ToolPreprocessor unchanged) | |
| `src/brain/tool_preprocessor.py` | No change | |

**Net**: ~-500 lines deleted, ~+585 added. Migration adds ~85 lines (mostly new validation + pattern formatting logic).

## Risks and Mitigations

| Risk | Severity | Mitigation |
|------|----------|------------|
| JSON parsing less reliable than tool_use | Medium | Tagged `<decision>` block (not raw JSON); schema validation; one repair turn; explicit fallback policy (D10) |
| Stale enemy patterns waste tokens | Low | Budget cap (300 tokens); max 3 episodes × 8 rounds; omit when no data |
| Enemy patterns mislead model | Low | Disclaimer "possible patterns, not guaranteed"; current round alignment reduces misuse |
| Loss of query telemetry | Low | Add retrieval telemetry at injection point (log what was injected, token count) |
| LLM ignores `<decision>` format | Medium | Strong system prompt instruction; repair turn with explicit error; tested with Kimi 2.5 |
| `analysis` field quality drops without schema enforcement | Low | Still required in JSON validation for combat; repair on missing |
| Evolution engine sees removed query tools | Low | Returns "tool not available" → evolution LLM self-corrects |

## Migration Order

1. **Phase 1: `<decision>` Protocol + Prompts** (bound together)
   - `<decision>` tag extraction + JSON parsing in V2Engine
   - Response schema validation (`validate_decision()` in `tool_schemas.py`)
   - Repair loop + fallback policy (D10)
   - System prompt updates: remove tool instructions, add `<decision>` format + examples
   - This phase can be tested immediately: add `<decision>` parsing alongside existing tool_use, verify both paths work

2. **Phase 2: Query Tool Removal + Enemy Patterns**
   - Delete `query_tools.py`
   - Delete `read_guide` and `assess_potion_value` from `tool_executor.py`
   - Create `enemy_pattern_injector.py`
   - Update `WorkingContext`: `combat_episode_hints` → `enemy_pattern_hints`
   - Update `retriever.py` and `prompt_injector.py`
   - Wire into `CombatConversation`
   - Evolution engine compatibility fix

3. **Phase 3: V2Engine Simplification**
   - Replace `_agent_loop()` with `_single_call()` + `_validate_and_repair()`
   - Remove query tool dispatch, `QueryToolRecord`, `_PARAM_REMAP`
   - Gameplay callers stop passing `tools`/`tool_choice` to V2Backend

4. **Phase 4: Conversation Cleanup**
   - Remove tool-result merging from `CombatConversation`
   - Messages become pure user/assistant text alternation

5. **Phase 5: Integration Test**
   - Full run with Kimi 2.5
   - Verify: `<decision>` parse rate, repair frequency, fallback frequency
   - Compare token usage before/after

Phase 1 is the critical path — everything else depends on it. Phase 2 is independent of Phase 1 and can be developed in parallel.

## Non-Goals

- Evolution engine migration to text-only (deferred)
- `tool_schemas.py` file rename (deferred to cleanup pass)
- ToolPreprocessor changes (already auto-executes, unaffected)
- DynamicToolRegistry changes (unaffected)
- Skill system changes (unaffected)
- Memory system changes beyond `WorkingContext` field swap (unaffected)
