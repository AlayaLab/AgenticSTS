# Upstream Repository Adoption Plan

**Date**: 2026-03-30
**Status**: Draft (Rev 2 — post spec review)
**Sources**: CharTyr/STS2-Agent v0.5.3, Gennadiyev/STS2MCP v0.3.2

## Overview

Adopt improvements from two upstream STS2 repositories to fill knowledge gaps, upgrade API consumption, and prevent soft-locks. Organized into three phases by impact.

## Context

### CharTyr/STS2-Agent v0.5.3 (released 2026-03-30)
- 16 bundled game data JSON files (cards, relics, monsters, potions, events, encounters, etc.)
- `dynamic_values[]` and `resolved_rules_text` on ALL card payloads (not just hand cards)
- `/actions/available` endpoint with parameter hints
- State version 7

### Gennadiyev/STS2MCP v0.3.2
- Crystal Sphere minigame + Bundle selection support
- Overlay catch-all for soft-lock prevention
- Keyword glossary auto-collection

## Current Gaps

| Data | Ours | Upstream | Gap |
|------|------|----------|-----|
| Relics | 35 hand-picked | 289 complete | Missing 87% |
| Encounters | None | 87 fight compositions | Entirely new |
| Events | 68 name+type only | 66 with structured options/outcomes | Agent blind to outcomes |
| Cards | 577 decompiled text | 576 with powers_applied, spawns_cards, upgrade deltas | Missing structured effects |
| Monsters | 121 raw move text | 111 with per-move damage_values (normal+ascension) | Missing numeric damage |
| Enchantments | None | 22 types | Entirely new |
| Acts | Hardcoded floor heuristics | 4 structured (bosses, encounters, events per act) | Data-driven replacement |
| Keywords | None | 8 definitions | LLM must infer |
| Crystal Sphere | Not handled | Full support | Potential soft-lock |
| Bundle selection | Not handled | Full support | Potential soft-lock |

---

## Phase 1: Game Data JSON Integration

### 1.1 Data Acquisition & Loading Strategy

Download 16 JSON files from CharTyr/STS2-Agent `mcp_server/data/eng/` into `data/knowledge/upstream/`.

Files: cards.json, relics.json, monsters.json, potions.json, events.json, encounters.json, powers.json, enchantments.json, acts.json, keywords.json, characters.json, epochs.json, intents.json, afflictions.json, modifiers.json, ascensions.json

**Loading strategy**: JSON files loaded via new `_load_upstream_json(filename)` utility in each lookup module, **alongside** existing markdown loaders (not replacing them). Both systems coexist:
- Markdown DB (`cards.md`, `card-behaviors.md`, etc.): decompiled C# behavior text — richer OnPlay/OnUpgrade descriptions
- Upstream JSON (`upstream/cards.json`, etc.): structured metadata — powers_applied, damage_values, upgrade deltas

**Merge priority**: For enriched modules (cards, monsters), markdown fields are authoritative for behavior text; JSON fields supplement with structured metadata not available in markdown. No field conflicts possible because they carry different data.

**`powers.json` note**: We already ship `data/knowledge/powers.json` (loaded by `power_lookup.py`). The upstream `powers.json` is the same data source — compare at acquisition time, use upstream if newer, keep existing if identical.

**Data freshness**: One-time import with a lightweight `scripts/sync_upstream_data.py` script for future updates (downloads, diffs, reports changes). Not automated — run manually when upstream releases a new version.

**Backward compatibility**: All new fields default to `None`/`[]`/`{}`. Code paths that consume enriched data must check for `None` and fall back gracefully. This ensures the system works even if upstream JSON files are missing or outdated.

### 1.2 Relic System Overhaul

**Current**: `_relic_fmt.py` has 35 relics in a hardcoded dict with context-specific hints.

**Target**:
- New `src/knowledge/relic_lookup.py` with `RelicKnowledge` dataclass:
  - Fields: `id`, `name`, `description`, `rarity`, `pool`, `flavor`
  - O(1) lookup by name (case-insensitive)
  - Character-pool filtering, rarity grouping
- Refactor `_relic_fmt.py`:
  - Keep 35 curated strategic hints for analyzed relics (context-tagged with rest/map/shop/combat)
  - For other 254 relics: inject upstream `description` text ONLY when context matches
  - Context matching for non-curated relics: simple keyword scan of description for context relevance
    - "rest"/"heal" keywords → inject in rest context
    - "gold"/"buy"/"shop" → inject in shop context
    - "damage"/"block"/"attack" → inject in combat context
    - No keyword match → skip (don't inject everywhere)
  - `format_relic_hints()` keeps existing 6-hint cap, priority: curated hints first, then description-based
  - This prevents token overflow: same cap, wider source pool

**Token budget**: ~200 tokens (context-filtered, cap preserved, up from ~100).

### 1.3 Encounter Database

**Current**: No fight composition data.

**Target**:
- New `src/knowledge/encounter_lookup.py` with `EncounterKnowledge` dataclass:
  - Fields: `id`, `name`, `room_type` (Normal/Elite/Boss), `act`, `monsters[]`, `is_weak`, `tags`
  - Primary lookup: by `enemy_id` set (from `RawCombatEnemyPayload.enemy_id`) — most reliable
  - Secondary lookup: by monster display name set — fallback when enemy_id unavailable
  - Index: build `frozenset(monster_ids) -> EncounterKnowledge` at load time for O(1) set-match
  - Multi-enemy matching: unordered set comparison (all monsters present = match)
  - Also supports lookup by encounter_id, by act+room_type
- Prompt injection at COMBAT_START:
  - Look up encounter by enemy_id set from combat state
  - Inject: "This is a [Normal/Elite/Boss] fight in Act [N]. Known composition: [monsters]"
- Route planning benefit: encounter difficulty data per act

**Token budget**: ~50 tokens per combat.

### 1.4 Event Knowledge Upgrade

**Current**: `event_lookup.py` returns `EventKnowledge(name, event_type)`.

**Target**:
- Enrich `EventKnowledge` with:
  - `act: str` — which act the event appears in
  - `options: list[EventOption]` — each with `id`, `title`, `description`
  - `pages: list` — follow-up branches (for multi-page events)
- At event decision time, inject known outcomes into prompt
- Primary key: `event_id` (from MCP state's `RawEventPayload.event_id`, e.g., `"CRYSTAL_SPHERE"`)
- Fallback: `title` (display name, case-insensitive match)
- **Note**: Static JSON options are pre-condition — runtime state may lock/unlock options dynamically. Injection provides context ("Option 1 typically does X") but agent still decides based on runtime `is_locked`/`is_proceed` flags

**Token budget**: ~150 tokens per event decision.

### 1.5 Card Knowledge Enrichment

**Current**: `CardKnowledge` has `on_play`, `on_upgrade`, `vars` (decompiled C# text).

**Add fields from upstream**:
- `powers_applied: list[dict] | None` — e.g., `[{"power": "Vulnerable", "amount": 2}]`
- `spawns_cards: list[str] | None` — e.g., `["SHIV"]`
- `upgrade_deltas: dict | None` — e.g., `{"damage": "+2", "vulnerable": "+1"}`
- `base_hit_count: int | None` — static hit count from game data (supplements runtime DynamicVar chain)

**Card ID matching**: Upstream JSON keys by `id` (e.g., `"STRIKE_RED"`). Our lookup keys by `name.lower()`. Merge strategy:
1. Load upstream JSON, build `id -> upstream_card` dict
2. Load existing markdown, build `name.lower() -> CardKnowledge` dict
3. Match upstream to existing via `upstream.name.lower() == existing_name.lower()`
4. For upgraded cards (`"Strike+"`): strip trailing `+`, match to base card
5. Count discrepancy (577 vs 576): log any unmatched cards, treat as non-blocking

**`base_hit_count` priority** in the existing fallback chain:
1. Runtime `DynamicVar` hits (authoritative — accounts for in-combat modifiers)
2. `_parse_hits_from_rules()` from rules_text ("twice"/"N times")
3. `base_hit_count` from upstream JSON (static baseline, lowest priority)
This adds a third fallback, not a replacement.

**Merge strategy**: Load upstream cards.json after markdown load, match by name, add new fields. Keep our decompiled `on_play`/`on_upgrade` text (richer behavior descriptions). Unmatched cards in either direction are logged but not fatal.

**Prompt impact**: Card reward/shop prompts show "Applies: 2 Vulnerable", "Upgrade: +2 damage".

**Token budget**: ~100 tokens in card reward/shop contexts.

### 1.6 Monster Knowledge Enrichment

**Current**: `MonsterKnowledge` has `moves` (raw text), `passive`, `min_hp`, `max_hp`.

**Add fields from upstream**:
- `damage_values: dict[str, dict]` — per-move `{normal: N, ascension: N}`
- `block_values: dict[str, int]` — per-move block
- `monster_type: str` — Normal/Elite/Boss classification

**Prompt impact**: Combat prompts show "Jaw Worm: Chomp deals 12 damage" instead of raw code.

**Token budget**: ~80 tokens in combat context.

### 1.7 New Reference Data

- **`acts.json`** → `src/knowledge/act_lookup.py`:
  - `ActKnowledge`: act number, bosses, encounters, events
  - Supplements (not replaces) the existing `_cached_map_node_type` pattern — the cache handles runtime combat type detection, while `acts.json` provides pre-knowledge for route planning and post-run analysis where runtime cache is unavailable
  - Used by route planning (which bosses/encounters to expect) and memory analysis

- **`enchantments.json`** → `src/knowledge/enchantment_lookup.py`:
  - `EnchantmentKnowledge`: id, name, description, card_type, is_stackable
  - Reference for card evaluation when cards are enchanted

- **`keywords.json`** → `src/knowledge/keyword_lookup.py`:
  - `KeywordKnowledge`: id, name, description
  - Inject definitions when hand/deck cards have these keywords
  - Eliminates LLM guessing at keyword meanings

### 1.8 Knowledge Facade Update

`GameKnowledge` singleton in `knowledge.py` gains:
- `get_relic(name) -> RelicKnowledge`
- `get_encounter_by_monsters(names) -> EncounterKnowledge`
- `get_event_details(event_id) -> EventKnowledge`
- `get_act(number) -> ActKnowledge`
- `get_enchantment(name) -> EnchantmentKnowledge`
- `get_keyword(name) -> KeywordKnowledge`

Existing methods enriched: `get_card()` returns new fields, `get_monster()` returns damage_values.

### 1.9 Prompt Injection Points

| Prompt | New Injection | Source |
|--------|--------------|--------|
| Combat (COMBAT_START) | Encounter composition + monster damage values — injected into **initial combat message** (user message, not system prompt, to preserve prompt caching) | encounter_lookup + monster_lookup |
| Combat (per-round) | Keyword definitions for hand cards — injected into **round state update** (user message) alongside hand card list | keyword_lookup |
| Event | Structured options with outcomes | event_lookup |
| Card reward / Shop / Card select | powers_applied, spawns_cards, upgrade deltas | card_lookup |
| Rest / Map | Full relic descriptions (289 relics) | relic_lookup |
| Route plan | Act encounter difficulty, boss data | act_lookup + encounter_lookup |

---

## Phase 2: v0.5.3 API Upgrade

### 2.1 `dynamic_values[]` Model

New model in `upstream_models.py`:
```python
class DynamicValue(BaseModel):
    name: str
    base_value: int | float
    current_value: int | float
    enchanted_value: int | float | None = None
    is_modified: bool = False
    was_just_upgraded: bool = False
```

Add `dynamic_values: list[DynamicValue] = []` and `resolved_rules_text: str = ""` to:
- `RawDeckCardPayload`
- `RawSelectionCardPayload` (if separate from hand)
- `RawRewardCardPayload`
- `RawShopCardPayload`

**Relationship to existing hand card fields**: `RawCombatHandCardPayload` already has `damage`, `block`, `hits`, `total_damage` as top-level fields. These are **derived from** `dynamic_values` by the C# mod. For hand cards, keep using the existing top-level fields (they're simpler and already integrated). For non-hand card payloads (deck, reward, shop, selection), use `dynamic_values[]` to extract the same values. Helper method: `get_damage_block_from_dynamic_values(dvs)` returns `(damage, block, hits)` by scanning DynamicValue names.

**v0.5.2 backward compatibility**: All new fields have defaults (`[]`, `""`). When connected to a v0.5.2 server, these fields will simply be empty — existing behavior is preserved. Code consuming `dynamic_values` must always check `if card.dynamic_values:` before using.

### 2.2 Prompt Impact

- Deck view: show current values with modification indicators (`is_modified`, `enchanted_value`)
- Card reward: show exact damage/block numbers (not just rules_text)
- Shop: show value-for-cost comparison with real numbers
- Card select (upgrade/remove): show before/after values — **this addresses the existing TODO "Card upgrade comparison not shown at Smith"** by leveraging `was_just_upgraded` and `base_value` vs `current_value`

### 2.3 `/actions/available` Endpoint

Add to `client.py`:
```python
async def get_available_actions(self) -> dict:
    """Get available actions with parameter hints."""
    return await self._get("/actions/available")
```

Use parameter hints for:
- Pre-validation before `post_action()` (reduce retry loops)
- Dynamic action discovery (detect new actions like Crystal Sphere)

---

## Phase 3: Soft-lock Prevention

### 3.1 Crystal Sphere

**Note**: The codebase may already have partial Crystal Sphere handling. Before implementing, check for existing methods like `_handle_crystal_sphere_event()`, `_is_crystal_sphere_event()`, etc. in `loop.py`. Scope this to:
- If existing handlers work: no changes needed, just verify they cover the CharTyr v0.5.3 actions
- If not: add detection via `state_type` / `screen` / `available_actions` containing crystal sphere actions
- Handler: mechanical fallback (random tool + clicks + proceed) — minigame doesn't need LLM
- Fallback: `confirm_modal` / `dismiss_modal` / `proceed` to skip

### 3.2 Bundle Selection

**Detection**: `selection.kind` indicates bundle, or `available_actions` contains bundle-specific actions.

**Pre-implementation check**: Confirm what v0.5.3 actually exposes for bundle handling. Possible scenarios:
- CharTyr API has `select_bundle` / `confirm_bundle_selection` → implement handler
- CharTyr API reuses `select_deck_card` / `confirm_selection` → our existing selection handler may already work
- CharTyr API has no bundle support → defer until API adds it

**Handler** (if actions available):
- LLM path: treat like card_select (evaluate cards in each bundle, pick best)
- Fallback: select first bundle

**state_type**: Likely reuses `"card_select"` or `"hand_select"` — verify at runtime.

### 3.3 Overlay Catch-all

Add to `_force_unstick()`:
```
if "confirm_modal" in available_actions or "dismiss_modal" in available_actions:
    try confirm_modal first, then dismiss_modal
    log unknown overlay state for debugging
```

This prevents unhandled overlay types from causing stuck loops.

---

## Token Budget Summary

| Injection Point | Current | After Adoption | Delta |
|-----------------|---------|----------------|-------|
| Relic hints (rest/map/shop) | ~100 | ~200 | +100 |
| Combat context (encounter) | 0 | ~50 | +50 |
| Combat (monster damage) | 0 | ~80 | +80 |
| Combat (keywords) | 0 | ~30 | +30 |
| Event options | 0 | ~150 | +150 |
| Card enrichment (reward/shop) | 0 | ~100 | +100 |
| **Total new tokens** | | | **+510** |

All injections are context-specific (only injected in relevant prompt types).

**Worst-case analysis (combat prompt)**:
- Existing: knowledge ~750 + skills ~600 + memory ~400 + strategic thread ~200 + relic descriptions ~300 = ~2250 tokens
- New: encounter +50 + monster damage +80 + keywords +30 = +160 tokens
- Worst-case total: ~2410 tokens — well within budget (system prompt ~970 tokens, total context ~3400 tokens)

**Worst-case analysis (event prompt)**:
- Existing: knowledge ~200 + skills ~200 + memory ~200 + strategic thread ~200 = ~800 tokens
- New: event options +150 = +150 tokens
- Worst-case total: ~950 tokens — within budget

No single prompt grows by more than ~200 tokens in the worst case.

---

## Testing Strategy

- **Unit tests**: Each new lookup module (relic, encounter, event, act, enchantment, keyword) tested for load, lookup, edge cases
- **Model tests**: `dynamic_values[]` parsing verified with sample v0.5.3 payloads
- **Integration**: 2-3 full game runs after each phase to verify no regressions
- **Prompt inspection**: Manually verify new knowledge injection is useful and within token budgets
- **Soft-lock test**: Verify Crystal Sphere / Bundle / overlay states don't cause stuck loops (may require triggering these in-game)

---

## Files Modified

### New Files
- `data/knowledge/upstream/*.json` (16 files)
- `src/knowledge/relic_lookup.py`
- `src/knowledge/encounter_lookup.py`
- `src/knowledge/enchantment_lookup.py`
- `src/knowledge/keyword_lookup.py`
- `src/knowledge/act_lookup.py`

### Modified Files
- `src/knowledge/card_lookup.py` — add powers_applied, spawns_cards, upgrade_deltas, hit_count
- `src/knowledge/monster_lookup.py` — add damage_values, block_values, monster_type
- `src/knowledge/event_lookup.py` — add structured options/outcomes
- `src/knowledge/knowledge.py` — add new lookup accessors
- `src/knowledge/injector.py` — new injection points for enriched data
- `src/mcp_client/upstream_models.py` — DynamicValue model, new fields on card payloads
- `src/mcp_client/client.py` — `/actions/available` endpoint
- `src/brain/prompts/_relic_fmt.py` — refactor to use relic_lookup.py
- `src/brain/prompts/event.py` — inject event option knowledge
- `src/brain/conversation.py` — inject encounter/keyword data in combat
- `src/agent/loop.py` — Crystal Sphere/Bundle/overlay handlers in _force_unstick()

---

## Out of Scope

- Instant Mode (C# Harmony patch) — deferred, not critical
- Multiplayer support — not relevant
- Native MCP server — we use direct REST, no need for MCP protocol layer
- entity_id targeting — requires upstream API change we can't control
- Draw pile shuffling — fair play consideration, not needed for our agent
