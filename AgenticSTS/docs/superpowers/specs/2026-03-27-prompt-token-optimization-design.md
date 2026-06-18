# Prompt Token Optimization Design

**Date**: 2026-03-27
**Status**: Approved (brainstorming complete)
**Goal**: Reduce combat LLM call input from ~5000 → ~3300 tokens (-34%)

## Background

STS2 agent averages ~8000 chars (~5000 tokens) input per LLM call, with 86s average latency. System prompt (967 tokens) and tool schemas (969 tokens) are cached via Anthropic prompt caching. The uncached portion — user prompt (1144 tokens) and message history (4348 tokens) — is the optimization target.

## Token Distribution (Baseline)

| Component | Avg chars | Est. tokens | Cached? |
|-----------|----------|-------------|---------|
| System prompt | 3,869 | ~967 | Yes |
| Tool schemas | 3,875 | ~969 | Yes |
| User prompt | 4,574 | ~1,144 | No |
| Messages history | 17,393 | ~4,348 | No |

## Optimizations

### P0: Combat Conversation History — keep_recent=2 → 1

**Problem**: `compress_history(keep_recent=2)` retains last 2 full rounds (~2000 tokens). Each round includes round state, tool_use messages, tool_results, and protocol messages.

**Design**:
- Change `keep_recent` from 2 to 1
- Last round provides immediate context (what was just played, enemy actions)
- Older rounds already compressed into `_round_summaries`
- Strategic continuity preserved via `_strategic_notes` (last 5 notes in `## Strategic Thread`)
- Combat start message NOT compressed — it contains deck overview, relic descriptions, combat rules (critical anchor for entire combat)

**Files**: `src/brain/conversation.py` (compress_history call site)
**Savings**: ~1000 tokens/combat call

### P0: Key Effects Delta Injection

**Problem**: `_KW_GLOSSARY` (11 keyword definitions, ~40 tokens each) injected every round. Effects rarely change mid-combat — Block, Weak, Vulnerable definitions are identical from Round 1 to Round 8.

**Design**:
- Add `_injected_effects: set[str]` to `CombatConversation`
- On each `add_round_state()`, only inject keyword definitions for effects NOT already injected
- Round 1: full injection (~175 tokens for 4-5 effects)
- Round 2+: skip already-seen effects (typically 0 tokens)
- After `compress_history()` fires: reset `_injected_effects` to empty (old definitions lost in compression, must re-inject)
- After reset, next round re-injects all current effects (one-time cost), then delta mode resumes

**Files**: `src/brain/conversation.py` (add_round_state Key Effects section)
**Savings**: ~130 tokens/round for rounds 2+ (avg 8-round combat saves ~900 tokens total)

### P0: Deck Listing Grouping

**Problem**: `format_deck_section()` lists every card individually at combat start. A 20-card deck costs ~200 tokens. This message persists in conversation history.

**Design**:
- Group identical cards: `Strike x5, Defend x5, Pommel Strike x2, Bash x1`
- Sort by count descending (most common first)
- Retain upgrade markers: `Strike+ x2, Strike x3`

**Files**: `src/brain/prompts/_deck_fmt.py`
**Savings**: ~140 tokens (persists in history, multiplied by rounds until compression)

### P1: Skill Format Slimming + Generation Validation

**Problem**: Each skill in prompt includes content (~100 tokens) + examples (~30 tokens) + lessons (~30 tokens) + metadata (~15 tokens). 5 skills x 175 = 875 tokens. Examples and negative-case lessons ("Without this:") add little value for Sonnet 4.6.

**Design — Display (composer.py)**:
- Remove `⚠ Without this: {lessons}` section
- Remove `Example: {ex}` section (max 2 per skill)
- Remove `({category}, ...)` — category is redundant (skills already filtered by state_type at retrieval)
- Remove `[Supplements seed: ...]` — internal tracking, not useful for LLM
- Exception: skills with `category=combat` AND content containing "sequence"/"order"/"先"/"then" retain 1 example (procedural knowledge benefits from concrete examples)
- Keep 900 token budget unchanged — more skills fit per prompt

**Design — Generation validation (discovery.py, write_tools.py)**:
- Add 400-char limit instruction to generation prompts: "content must be under 400 chars, concise rules only, no examples or negative cases"
- Post-generation check: if `len(content) > 400`:
  1. Retry once with compression prompt: "Too long ({len} chars). Compress to ≤400 chars preserving key rules only."
  2. If still over 400 → reject skill (do not save)
- No truncation ever — truncation loses key information, equivalent to 0 value

**Files**: `src/skills/composer.py`, `src/skills/discovery.py`, `src/brain/write_tools.py`
**Savings**: ~100 tokens/call (display). Prevents future bloat (generation).

### P1: Computed Insights Compression + Filtering

**Problem**: `ToolPreprocessor.format_hints()` dumps full tool result dicts as strings. 5 tools x ~200 chars = ~1000 chars in combat. Two of the 5 tools (`deck_bloat_energy_check`, `rest_site_heal_vs_upgrade_v2`) are irrelevant during combat. Two damage tools (`multi_enemy_incoming_damage`, `multi_enemy_total_damage`) overlap heavily.

**Design — Filtering**:
- Add `APPLICABLE_STATES = ["card_reward", "shop", "rest"]` to `deck_bloat_energy_check.py`
- Add `APPLICABLE_STATES = ["rest"]` to `rest_site_heal_vs_upgrade_v2.py`
- Existing ToolPreprocessor state filtering handles the rest

**Design — Deduplication**:
- In `format_hints()`: if multiple tools output `total_incoming` and `survives`, keep only the more detailed result (by key count)

**Design — Compression**:
- In `format_hints()`: replace `str(hint.result)` with generic extraction
- Priority keys: `recommendation`, `verdict`, `decision`, `note`, `survives`, `hp_remaining`, `damage_taken`
- Format as single line: `"Survive(63HP after 7dmg) | Incoming 7, block optional"`
- Drop detailed breakdowns (`enemy_breakdown`, `simulation`, `warnings`, `cards_played`)
- New tools from evolution also benefit (generic extraction, no per-tool `format_compact()` needed)

**Files**: `src/brain/tool_preprocessor.py`, `data/evolution/tools/deck_bloat_energy_check.py`, `data/evolution/tools/rest_site_heal_vs_upgrade_v2.py`
**Savings**: ~130 tokens/combat call

### P1: Round Summary Compact Format

**Problem**: `_round_summaries` stores full sentences: `"R1: Played Strike, Strike, Defend. Took 8 damage. HP 62→54. Killed Jaw Worm."` (~35 tokens). 10-round combat compresses 8 rounds = ~280 tokens.

**Design**:
- Compact format at generation time (in `add_round_result()`):
  `"R1: 3cards -8HP(62→54) kill:Jaw Worm"`
- ~15 tokens per summary vs ~35 tokens

**Files**: `src/brain/conversation.py` (add_round_result)
**Savings**: ~160 tokens for long combats (8+ rounds)

### P1: Combat Card Knowledge Skip

**Problem**: `KnowledgeInjector.inject_combat_knowledge()` injects card mechanics from knowledge DB (~400 tokens). But hand cards already display structured `[N dmg]`/`[N block]` + full `rules_text` inline. Information is largely duplicated.

**Design**:
- In combat context assembly: skip card knowledge injection
- Keep monster knowledge (~200 tokens) — enemy patterns not available elsewhere
- Keep potion knowledge (~150 tokens) — potion descriptions may differ from short names
- **Pre-implementation check required**: verify actual overlap between knowledge DB entries and structured card previews. If knowledge DB has unique info (upgrade effects, special interactions), keep selective injection.

**Files**: `src/agent/loop.py` (_build_decision_context or knowledge injection call site)
**Savings**: ~400 tokens/combat call (if overlap confirmed)

### P3: Protocol Message Cleanup

**Problem**: Tool results contain "Plan received." / "Acknowledged." (~10 tokens each). In combat's keep_recent=1 round, ~3 such messages = ~30 tokens.

**Design**:
- Replace all tool_result confirmation text with `"ok"` (Anthropic API requires non-empty)

**Files**: `src/brain/v2_engine.py`, `src/brain/conversation.py`
**Savings**: ~50 tokens/combat call

### P3: Route Plan Fallback Compaction

**Problem**: When route LLM JSON parse fails, `_route_plan` stores all 5 formatted routes (~1200 chars) instead of just the selected one (~200 chars). Injected into every subsequent map call.

**Design**:
- On parse failure, store only top-scored route (route 1) + first 2 lines of formatted output
- Keeps strategic context without 5x redundancy

**Files**: `src/agent/loop.py` (route plan fallback path, line ~3915)
**Savings**: ~250 chars per map call (rare failure case only)

## Rejected Approaches

| Approach | Why Rejected |
|----------|-------------|
| Skill budget 900→600 tokens | Truncates skill slots, loses information |
| RunContextView dedup across steps | Non-combat calls infrequent, complexity not worth it |
| Combat start message compression | Too many critical anchors (deck, relics, rules) |
| Route plan 12K+ summarization | Already solved by route_planner.py (DFS + lightweight LLM) |
| Per-tool `format_compact()` methods | 38 tool files, fragile for auto-evolved tools |

## Expected Total Savings

**Combat call (most frequent):**
- P0: ~1000 (history) + ~130/round (key effects) + ~140 (deck) = ~1270+ tokens
- P1: ~100 (skills) + ~130 (insights) + ~160 (summaries) + ~400 (card knowledge) = ~790 tokens
- P3: ~50 (protocol) = ~50 tokens
- **Total: ~2100+ tokens/combat call → ~5000 → ~2900 (-42%)**

**Non-combat calls:**
- P1 skill format: ~100 tokens savings
- Other optimizations are combat-specific

## Verification Method

After implementation, run 1 full game and analyze logs:

```bash
python -c "
import json, statistics
events = [json.loads(l) for l in open('logs/run_latest.jsonl') if 'llm_call' in l]
sizes = [len(str(e.get('prompt',''))) + len(str(e.get('messages',''))) for e in events]
print(f'Mean input chars: {statistics.mean(sizes):.0f}')
print(f'Median: {statistics.median(sizes):.0f}')
print(f'P95: {sorted(sizes)[int(len(sizes)*0.95)]:.0f}')
"
```

Compare against baseline: mean ~8000 chars → target ~5000 chars.

## Constraints

- System prompt is cached → only user message / history changes save billable tokens
- No information loss that affects decision quality
- No skill truncation — validate at generation, reject if too long
- Architecture unchanged — only formatting logic modifications
- Combat start message is untouchable (critical anchor)
