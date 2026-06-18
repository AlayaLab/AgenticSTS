# Archetype System → Skill-Driven Deck Intelligence

**Date**: 2026-03-29
**Status**: Draft
**Scope**: Remove rigid archetype system, replace with agent-driven build reasoning + learning pipeline

## Problem

The archetype system (`src/knowledge/archetype.py`) hardcodes per-character build definitions (Strength, Poison, Focus, etc.) with fixed core/support card lists. This:

1. **Limits self-evolution**: Agent can't discover new builds or redefine what's "core"
2. **Labels instead of reasons**: Telling agent "you're playing Poison" is less useful than it understanding "Catalyst doubles all poison, making any poison source 2-3× more valuable"
3. **Stale data**: Seed guides never update. Web enrichment disabled in Phase A. Guides directory empty
4. **Wrong abstraction**: Top players think in win conditions and synergy chains, not archetype labels

## Design

Four-layer replacement, from in-run decision support to cross-run learning:

### Layer 1: Strategic Thread as Build Plan

**What**: Enhance the existing `strategic_note` mechanism so the agent maintains a running build plan within each run.

**Current state**: System prompt already mentions "win condition" and "Jobs" but agent writes vague notes like "拿了 Demon Form 因为 Strength 好".

**Change**: Modify system prompt strategic note guidance from:

```
Every decision tool includes an optional `strategic_note` field. Use it to record:
- WHY you made this choice (not what you chose — that's in the action)
- How this advances your deck's win condition
- What your deck still needs (unfilled Jobs: frontload damage, block, scaling, draw)
Keep under 25 words.
```

To:

```
Every non-combat decision tool has a `strategic_note` field. Write a RUNNING BUILD PLAN:
1. Win condition: How do you kill bosses? (e.g., "Poison stacking via Noxious Fumes + Catalyst burst")
2. Key pieces: Cards that define your build
3. Gaps: What's missing? (e.g., "No draw engine yet")
4. Avoid: What doesn't fit your win condition
Keep under 50 words. Revise when you take or skip a pivotal card.
```

Additionally, add a one-line hint to `build_card_reward_prompt()`:

```
Review your Build Plan in the Strategic Thread above. Does any offered card fill a gap or strengthen your win condition?
```

**Files changed**:
- `src/brain/prompts/system.py` — strategic note section rewrite (~50 token increase)
- `src/brain/prompts/reward.py` — add build plan reference line
- `src/brain/prompts/shop.py` — add build plan reference line (if card purchase section exists)

**No new code, no new data structures.** Pure prompt engineering.

**Token cost**: Strategic note word limit increases from 25→50 words. With last-5 injection, worst case is ~330 tokens per prompt (up from ~165). Acceptable given the P6 combat optimization saved ~34% — this uses part of that headroom.

### Layer 2: Skill Trigger Mechanism Fixes

**What**: Two fixes that enable discovered combo skills to trigger correctly.

#### 2a: Overlap-weighted requires_cards scoring

Current `SkillTrigger.matches()` gives a flat +1.5 score regardless of how many required cards match. A deck with 5 Poison cards and 1 Shiv card gives Poison and Shiv skills identical scores.

**Change** in `src/skills/models.py`, `SkillTrigger.matches()`:

```python
# Before:
if self.requires_cards:
    if not self.requires_cards.intersection(hand_cards):
        return False, 0.0
    score += 1.5

# After (diminishing returns to prevent score explosion):
if self.requires_cards:
    overlap = self.requires_cards.intersection(hand_cards)
    if not overlap:
        return False, 0.0
    score += 1.5 + 0.5 * (len(overlap) - 1)  # 1 match=1.5, 2=2.0, 4=3.0, 6=4.0
```

Effect: More overlap = higher score, but capped via diminishing returns. Prevents card-heavy skills from eclipsing enemy-specific (+2.0) or act-specific (+0.5) matches. A skill with 6 matching cards scores 4.0 — strong but not dominant.

#### 2b: Deck-based card matching for non-combat states

Current skill retrieval populates `hand_cards` only during combat (from `gs.hand`). For deck building states (card_reward, shop, card_select), `hand_cards` is empty — so `requires_cards` triggers never match.

**Change** in `src/agent/loop.py`, `_query_skills()` (around line 2588):

```python
# Before:
if gs.is_combat and gs.combat and gs.combat.player:
    hand_cards = frozenset(c.name for c in gs.hand)

# After:
if gs.is_combat and gs.combat and gs.combat.player:
    hand_cards = frozenset(c.name for c in gs.hand)
elif gs.state_type in ("card_reward", "shop", "card_select") and gs.deck:
    hand_cards = frozenset(c.name for c in gs.deck)
```

**Semantic note**: For combat states, `hand_cards` = current hand (5 cards, high signal). For deck building states, `hand_cards` = full deck (15-30 cards, lower signal per card). The diminishing-returns formula in 2a ensures deck-based matching doesn't produce runaway scores even with many matches.

Effect: Discovered combo skills like "Catalyst timing in boss fights" (requires_cards: ["Catalyst"]) now trigger during card_reward when Catalyst is already in the deck.

**Files changed**:
- `src/skills/models.py` — `SkillTrigger.matches()`, 3 lines
- `src/agent/loop.py` — `_query_skills()`, 3 lines

### Layer 3: Post-Run Card Assessment

**What**: Add per-card qualitative importance assessment to the existing post-run LLM build analysis.

**Why**: Play count is a poor proxy for card importance. A Power card played once may be the keystone of the entire build. A Strike played 20 times is dead weight. The agent needs to judge card importance from the full picture (damage attribution, power application, synergy role), not raw frequency.

**Current state**: `card_build_extractor.py` already extracts rich per-card evidence (top_damage, top_block, top_powers_applied, top_enemy_debuffs) and sends it to `analyze_build_with_llm()` which produces build_summary, damage_engine, etc. But no per-card assessment.

**Change 1**: Extend `_BUILD_ANALYSIS_PROMPT` in `src/memory/card_build_extractor.py`:

Add to the JSON schema:

```json
"key_cards": [
  {
    "card": "<card name>",
    "role": "<keystone|core_damage|core_defense|draw_engine|energy_engine|utility|dead_weight|bad_pick>",
    "insight": "<1 sentence: WHY this role, based on traceable evidence>"
  }
]
```

Add to guidelines:

```
- key_cards: List 5-8 most notable cards (both positive and negative contributions).
- "keystone": Played rarely but DEFINED the strategy (power cards, scaling enablers). A card played once that enabled 200 damage across 5 combats outranks a card played 20 times for 5 damage each.
- "dead_weight": In the final deck but contributed little — should have been removed.
- "bad_pick": Taken during the run but rarely/never played. A deck building mistake.
- Base roles on TRACEABLE evidence (damage/block/power attribution), not play count alone.
```

**Change 2**: Add field to `CardBuildMemory` in `src/memory/models_v2.py`:

```python
key_cards: tuple[tuple[str, str, str], ...] = ()
# (card_name, role, insight)
```

**Change 3**: Wire through in `extract_card_build_memory()`:

```python
# Extraction (with role validation):
_VALID_ROLES = frozenset({
    "keystone", "core_damage", "core_defense", "draw_engine",
    "energy_engine", "utility", "dead_weight", "bad_pick",
})

key_cards = tuple(
    (kc["card"], kc["role"] if kc.get("role") in _VALID_ROLES else "utility", kc.get("insight", ""))
    for kc in analysis.get("key_cards", [])
    if isinstance(kc, dict) and "card" in kc
)
```

**Serialization** (dict format for robustness, not bare tuples):

```python
# to_dict:
"key_cards": [{"card": c, "role": r, "insight": i} for c, r, i in self.key_cards]

# from_dict:
key_cards=tuple(
    (kc["card"], kc["role"], kc.get("insight", ""))
    for kc in d.get("key_cards", [])
    if isinstance(kc, dict) and "card" in kc
)
```

**Learning loop**: Over multiple runs, key_cards data accumulates in CardBuildStore. Cross-run consumers:
- **Guide consolidation**: DeckGuide can reference consistently-keystone cards
- **Skill discovery**: LLM reads multi-run key_cards → creates combo/synergy skills
- **EvolutionEngine**: `get_performance_stats` can expose aggregated key_cards

**Cost**: Zero additional API calls. ~200 extra output tokens in the existing post-run Opus 4.6 analysis call.

**Files changed**:
- `src/memory/card_build_extractor.py` — prompt extension + extraction wiring
- `src/memory/models_v2.py` — CardBuildMemory field + serialization

### Layer 4: Deck Coherence Score

**What**: A 0-1 metric quantifying how well the cards in a deck work together. Primarily for NeurIPS evaluation, secondarily for guide consolidation quality signal.

**Why**: Win rate and floor progress are outcome metrics affected by RNG. Coherence measures deck building quality directly — a process metric that shows self-evolution independent of luck.

**Change**: Add to the same `_BUILD_ANALYSIS_PROMPT` (same LLM call as Layer 3):

```json
"coherence_score": 0.72,
"coherence_analysis": "Clear Strength+multi-hit chain. Draw engine weak. 2 dead cards should have been removed."
```

Add to guidelines:

```
- coherence_score (0.0-1.0): How well do the cards in the final deck work together?
  0.0-0.3: No clear strategy, random collection
  0.4-0.6: Has a direction but significant dead weight or missing pieces
  0.7-0.8: Clear strategy, mostly synergistic, minor gaps
  0.9-1.0: Tight, focused deck with every card serving the win condition
- coherence_analysis: 1 sentence. Name specific strengths and gaps.
```

**Data model**: Add to `CardBuildMemory` in `src/memory/models_v2.py`:

```python
coherence_score: float = 0.0
coherence_analysis: str = ""
```

**NeurIPS paper value**:
- Coherence over runs → deck building quality improvement curve
- Coherence vs win rate → validate metric correlates with outcomes
- Coherence by character → learning speed per character
- Ablation: no-skills vs seeds-only vs full-evolution coherence comparison

**Cost**: Zero additional API calls. ~30 extra output tokens in the existing post-run analysis call.

**Files changed**:
- `src/memory/card_build_extractor.py` — prompt + extraction
- `src/memory/models_v2.py` — CardBuildMemory fields + serialization

## Deletions

### Remove archetype.py and all references

**NOTE**: Run `grep -r "archetype" src/` before implementation to catch any references missed here. The list below covers all known references as of 2026-03-29.

**Delete file**: `src/knowledge/archetype.py` (327 lines)

**Delete directory**: `data/knowledge/guides/` (if exists — currently empty)

**Remove from `src/agent/loop.py`** (~38 references):
- Import: `from src.knowledge.archetype import ArchetypeTracker, load_guide`
- Field: `self._archetype_tracker`
- Field: `self._character_guide`, `self._character_guide_loaded`
- Method: `_ensure_character_guide()` — character guide loading + tracker init
- Method: `_build_archetype_context()` — build summary formatting
- All `archetype_context` references in `_build_decision_context()`, combat init, event emit
- Card tracking: `record_card_taken()` / `record_card_skipped()` calls
- Run reset: `_archetype_tracker.reset()`
- Context size config: `"archetype_context": 800` entry
- Memory query: `archetype=detected_archetype` kwarg at ~line 2764

**Remove from `src/brain/v2_engine.py`**:
- `archetype_context` parameter from `build_user_message()` and callers

**Remove from `src/brain/tool_executor.py`**:
- `archetype_tracker` field and constructor parameter
- `search_strategy`: archetype-based deck guide lookup (lines ~258-261)
- `_read_guide()`: entire "section 2" fallback (lines ~271-294) that reads character guide from tracker — this becomes dead code. Delete it. The skill library fallback (section 3) and guide store (section 1) remain.

**Adapt `src/memory/retriever.py`**:
- `query_for_decision()` has `archetype` parameter (~line 81) passed to `card_build_store.query()`
- Keep the parameter but document it now receives `primary_plan` or `""` instead of tracker-detected archetype
- Empty string falls through to same-character matching (existing behavior)

**Adapt `src/memory/memory_manager.py`**:
- `query_for_decision()` accepts and passes `archetype` parameter (~lines 82, 87, 102)
- Keep parameter signature. Callers will pass `""` after tracker removal. Works correctly — empty string triggers general (non-archetype-filtered) retrieval.

**Adapt `src/knowledge/web_searcher.py`**:
- `search_character_guide()` and `search_card_ratings()` reference archetype concepts
- These methods are already unused (web enrichment disabled in Phase A, call site in `_ensure_character_guide()` commented out)
- Mark as dead code or delete if no other callers exist. Boss strategy search (`search_boss_strategy()`) is unrelated and stays.

**Note on `src/memory/guide_consolidator.py`**:
- Groups CardBuildMemory by `(character, archetype)` for DeckGuide generation (~lines 342, 389, 548-588)
- No code change needed. The `archetype` field on CardBuildMemory is populated from `primary_plan` (existing legacy behavior). Guide consolidation will now group by LLM-generated `primary_plan` labels (e.g., "poison_stacking", "strength_scaling") instead of tracker-detected archetype labels. This is the desired behavior — LLM-derived labels are more flexible than hardcoded archetype names.

**Net effect**: ~400+ lines deleted, ~40 lines modified across 6 files.

### ToolExecutor search_strategy adaptation

Current `search_strategy` uses `self._archetype_tracker.detected_archetype` for deck guide lookup. After removal, use the `primary_plan` or first `build_tag` from the most recent CardBuildMemory (available via memory manager's card_build_store).

Fallback if no CardBuildMemory yet (first run): return general deck guide without archetype filter.

### ToolExecutor _read_guide() cleanup

Delete the "section 2" fallback (lines ~271-294) that reads archetype data from the tracker's `_guide` attribute. After this change, `read_guide` looks up:
1. Guide store (CombatGuide, RouteGuide, DeckGuide) — primary path
2. Skill library — secondary fallback
3. (deleted) ~~Archetype tracker character guide~~

## Data Migration

**CardBuildMemory.archetype field**: Keep as legacy (already documented as such). New runs populate it from `primary_plan` (existing behavior). No migration needed.

**Existing skills.json**: No changes. Seed skills unchanged (core_deck_building stays, no new seeds added).

**ArchetypeTracker state**: Ephemeral per-run, no persistence. Nothing to migrate.

## Interaction with Existing Systems

### Skill Discovery
No changes to `discovery.py`. It already creates new skills from gameplay patterns. With Layer 3 providing richer card assessment data, discovery quality should improve naturally as CardBuildMemory becomes more informative.

### EvolutionEngine
No changes to write tools. `write_skill` already creates deck_building skills. `get_performance_stats` could optionally expose aggregated key_cards data in a future iteration, but not required for this spec.

### Guide Consolidation
No changes. DeckGuide consolidation reads from CardBuildStore. With richer CardBuildMemory (key_cards, coherence), consolidated guides will naturally become more informative.

### Memory Retrieval
`retriever.py` passes `archetype` to `card_build_store.query()`. After this change, callers pass `""` (tracker removed). CardBuildStore handles empty archetype gracefully (falls back to same-character matching).

### CLAUDE.md
Update after implementation:
- Remove "Web Search + Archetype System" section under Key Technical Decisions
- Remove `archetype.py` from architecture diagram
- Remove ArchetypeTracker references from Agent Loop Flow and Important Patterns
- Add Layer 3/4 fields to CardBuildMemory description
- Update "Known Issues" to remove archetype-related TODOs

## Testing

1. **Unit**: SkillTrigger overlap-weighted scoring with various overlap counts
2. **Unit**: CardBuildMemory serialization round-trip with new fields (key_cards, coherence_score, coherence_analysis)
3. **Integration**: Verify `_query_skills()` populates hand_cards from deck in card_reward state
4. **Integration**: Verify `analyze_build_with_llm()` returns key_cards and coherence fields
5. **Manual**: Run 3-5 games, verify:
   - Strategic thread contains structured build plan
   - Post-run analysis produces meaningful key_cards assessments
   - Coherence scores correlate with perceived deck quality
   - No archetype-related errors in logs

## Success Criteria

1. Agent maintains a coherent build plan in strategic thread across a full run
2. Post-run key_cards assessments distinguish keystone vs dead weight cards (verified manually)
3. Coherence scores show variance (not all 0.5) and rough correlation with outcomes
4. After 10+ runs: at least one combo/synergy skill discovered through normal skill discovery pipeline
5. Zero regressions: no archetype-related errors, no skill retrieval failures

## Non-Goals

- No new seed skills (not even synergy maps — let agent discover)
- No changes to EvolutionEngine write tools
- No changes to skill discovery pipeline
- No card rating system (no S/A/B/C/D tiers)
- No archetype labels anywhere in the system
