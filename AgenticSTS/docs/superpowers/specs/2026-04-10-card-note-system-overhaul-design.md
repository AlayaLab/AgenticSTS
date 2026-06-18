# Card Note System Overhaul

**Date**: 2026-04-10
**Status**: Draft
**Goal**: Unify card knowledge into a single `note` field per card, provide grounded card descriptions to the evolution LLM, and inject card notes into combat prompts.

## Problem

The current CardMemory has three overlapping text fields:

| Field | Source | Used where | Problem |
|-------|--------|------------|---------|
| `seed_note` | Hand-written JSON (88 Silent cards) | Evolution stats display | Static, never updated by LLM |
| `combat_hint` | Hand-written JSON (25 Silent cards) | Combat prompt (`!! Card: hint`) | Likely LLM-generated, redundant with seed_note |
| `live_summary` | Evolution LLM `update_card_note` | `effective_note()` overrides seed_note | Only 10/171 cards have one |

Problems:
1. Three fields that all represent "knowledge about this card" but are maintained separately.
2. `combat_hint` is not updatable by LLM. `live_summary` doesn't appear in combat prompts.
3. Evolution LLM writes `live_summary` but lacks card descriptions (`rules_text`) and per-action combat deltas, so notes are subjective ("A-tier") rather than grounded.
4. The prompt says "update when seed_note is WRONG" — LLM can't confidently judge wrongness, so it rarely updates.

## Design

### 1. Single-authority `note` Field

Replace `seed_note`, `combat_hint`, and `live_summary` with a single `note: str` field on `CardMemory`. No `note_source` or seed/live distinction.

**CardMemory model change** (`models_v2.py`):
```python
# BEFORE
seed_note: str = ""
combat_hint: str = ""
live_summary: str = ""

# AFTER
note: str = ""    # Single source of truth
```

- `effective_note()` simplifies to `return self.note`
- `has_content` simplifies to `return bool(self.note)`
- Old `combat_hint` field dropped entirely (not migrated).

**Runtime authority**:
- `data/memory/v2/card_memories.json` is the **only runtime source of truth**.
- `src/skills/seeds/silent_card_notes.json` is **bootstrap content only** — it fills gaps, never overwrites.

**Note length limit**: 400 characters. The current `live_summary` enforced 200 chars but existing seed notes average 209 chars (max 365). Raise to 400 to accommodate both seed-quality and LLM-written notes without forced truncation. Update the validation in `_handle_update_card_note` and the `UPDATE_CARD_NOTE` tool schema accordingly.

**Seed JSON change** (`silent_card_notes.json`):
```json
// BEFORE
{"card_name": "Abrasive", "seed_note": "Sly: plays for free...", "combat_hint": "Sly: plays FREE..."}

// AFTER
{"card_name": "Abrasive", "note": "Sly: plays for free when discarded..."}
```

Remove all `combat_hint` entries. Rename `seed_note` → `note`.

**Seed loading behavior** (`CardMemoryStore.load_seeds()`):
- If a card memory entry **does not exist**, create it from seed.
- If an entry exists but `note` is **empty**, fill it from seed.
- If an entry exists and `note` is **non-empty**, never overwrite it from seed.

Seed edits do NOT propagate into existing stored notes. The persisted `card_memories.json` always wins.

**Evolution engine `update_card_note` tool**: Overwrites `note` directly.

**Combat hint injection** (`loop._get_combat_hints` + `conversation.py`): Remove the separate `combat_hint` injection path entirely. Card notes will be injected through the new COMBAT_START mechanism (Section 3).

### 2. Evolution Post-run Context Enhancements

Four changes to what the evolution LLM sees when deciding whether to write/update card notes.

#### 2a. Card Mechanics Reference (new section)

Inject a `## Card Mechanics Reference` section into the evolution context, placed before the existing card stats section.

**Data source**: Extract all unique `(card_name, rules_text)` pairs from the run's JSONL log by scanning `state` events. This set is called `seen_this_run_cards` — it includes every card the agent encountered during the run, not just the final deck:
- Combat hand cards: `state.combat.player.hand[].{name, rules_text}`
- Card reward options: `state.card_reward_details.card_options[].{name, rules_text}`
- Card select options: `state.selection_details.cards[].{name, rules_text}`
- Shop cards: (if logged with rules_text)

Deduplicate by `card_name` (case-insensitive, strip `+` suffix). Keep the first-seen `rules_text` per card (resolved values may vary across combat due to Strength/Dexterity, but any instance suffices for understanding the card's mechanics).

Append a keyword glossary by scanning all collected `rules_text` values against `KW_GLOSSARY` from `_keyword_fmt.py`.

**Format example**:
```
## Card Mechanics Reference (seen this run)
- Afterimage+: Innate. Whenever you play a card, gain 1 Block.
- Calculated Gamble: Discard your Hand, then draw that many cards. Exhaust.
- Flick-Flack+: Sly. Deal 9 damage to ALL enemies.
- Neutralize+: Deal 4 damage. Apply 2 Weak.
- Survivor: Gain 8 Block. Discard 1 card.
...

### Keywords
- Sly: If discarded BY A CARD EFFECT, this card is PLAYED FOR FREE. End-of-turn auto-discard does NOT trigger Sly.
- Exhaust: Removed until the end of combat.
- Innate: Start each combat with this card in your Hand.
```

**Token budget**: Estimate ~15 tokens per card. A 30-card run sees ~50-60 unique cards → ~750-900 tokens. Acceptable within the evolution context budget.

**Implementation**: New function in `src/postrun/context_builder.py`:
```python
def build_card_mechanics_section(log_path: Path, run_id: str) -> tuple[str, tuple[str, ...]]:
    """Extract card mechanics from run log.

    Returns (formatted_section, seen_card_names) where seen_card_names
    is the deduplicated tuple of all card names encountered in the run.
    """
```
Called from `build_evolution_context()` in `evolution_engine.py`. The returned `seen_card_names` tuple is reused by `_render_card_notes()` (Section 2b).

#### 2b. Card Notes and Card Memory Stats — expand to `seen_this_run_cards`

The existing `_render_card_notes()` in `evolution_engine.py` (line 2253) currently iterates only over `deck_cards` (the final deck). Change it to iterate over `seen_this_run_cards` — the full set of cards encountered during the run (the same tuple returned by `build_card_mechanics_section()` in Section 2a).

This means the evolution LLM sees notes AND stats for:
- Cards in the final deck (as before)
- Cards that were offered but not taken (reward, shop)
- Cards that were removed mid-run
- Temporary cards (status cards, potion-generated)

This gives the LLM broader context for writing notes. Note: "offered but skipped" data is visible within the current run's context (the LLM can see reward decisions in the non-combat digest). Cross-run offer/skip tracking is NOT part of this spec — it would require new `offer_count`/`skip_count` fields on `CardMemory`, which is deferred.

**Implementation**: Change `_render_card_notes(memory_manager, character, deck_cards)` signature to accept `seen_cards: tuple[str, ...]` instead of `deck_cards`. Update the call site in `build_evolution_context()` (line 2459) to pass the `seen_card_names` tuple from `build_card_mechanics_section()`.

#### 2c. Enhanced Combat Digest with Per-action Deltas

Extend `format_combat_round_digest()` in `context_builder.py` to include per-action state changes from the `card_play` events stored in `CombatEpisode.rounds[].events[]`.

**Current format**:
```
R1[Boss: Atk(20)]: Afterimage+->Neutralize+->Dash+ | dealt=34 taken=0
```

**New format**:
```
R1[Boss: Atk(20)]: Afterimage+(power:Afterimage)->Neutralize+(3dmg,2Weak)->Dash+(13dmg,+13blk) | dealt=34 taken=0
```

For each `card_play` event, append a compact parenthetical:
- `Xdmg` if any enemy HP delta < 0
- `+Xblk` if block > 0
- `+Xenergy` if energy > 0
- `NStatus` for each power/debuff applied (e.g. `2Weak`, `3Poison`)
- `power:Name` for player powers applied (e.g. `power:Afterimage`)
- `exhaust:N` if cards were exhausted

Omit the parenthetical if no observable effects (e.g. playing a Slimed that just draws 1).

**Token impact**: Adds ~5-10 tokens per card played per round. For a 7-round boss fight with 4 cards/round, that's ~200 extra tokens per combat. Across 20 combats, ~4000 tokens. Significant but within budget for the evolution context (currently ~44k total).

**Implementation**: Modify `format_combat_round_digest()` in `context_builder.py`.

#### 2d. Relic Context for Combo Discovery

Include the run's relic list with descriptions in the evolution context, so the LLM can discover card-relic combos.

**Data source**: Already available in the run's `state` events (`state.combat.player.relics[]`). Extract once from any combat state event.

**Format**:
```
## Run Relics
- Runic Pyramid: At the end of your turn, you no longer discard your hand.
- Shuriken: Every time you play 3 Attacks in a single turn, gain 1 Strength.
```

**Implementation**: Extract from first combat state in log. New helper in `context_builder.py`.

### 3. Combat Prompt Injection

#### 3a. COMBAT_START: Deck Card Notes

At the start of each combat (in `CombatConversation.add_combat_start()` at `conversation.py:568`), inject notes for all deck cards that have a non-empty `note`.

**Format**:
```
## Card Notes (from experience)
- Neutralize: 0-cost starter. Upgrade is premium. Save for big attack turns. 0-cost Weak often beats a Strike.
- Calculated Gamble: Discards entire hand, triggers Sly on ALL discarded Sly cards simultaneously.
- Piercing Wail: Save for scariest attack turn. Absurd vs multi-hit.
```

**Placement**: Inside the first user message of the combat conversation, alongside deck info. This means it will NOT be compressed during multi-turn conversation (first message is preserved).

**Scope**: All cards in current deck that have `note`. Not filtered by hand — this is strategic context for the entire combat.

**Token budget**: Notes range 67-365 chars (avg ~200 chars / ~50 tokens). At current coverage (~10-15 cards in a typical deck have notes), this produces ~500-750 tokens. Upper bound for a 25-card deck where every card has a note: ~1250 tokens.

**Implementation**: In `add_combat_start()`, call `CardMemoryStore.query_cards(character, deck_card_names)` to get memories with notes, format them, and append to the first user message.

#### 3b. Subsequent Rounds: Temporary Card Notes Only

In round 2+, only inject notes for cards **not in the current deck** — i.e. cards generated by potions, enemies (status cards like Slimed, Burn), or card effects (Shivs from Blade Dance).

**Logic**: For each card in hand, if `card.name` is not in the deck card list AND has a `note` in CardMemoryStore, inject it.

**Temporary/status card policy**: Shiv, Burn, Slimed, Wound, Dazed, and similar generated/status cards participate in **combat-time injection only**. The evolution LLM may read their `rules_text` from the Card Mechanics Reference and see their play stats, but `update_card_note` should NOT be used to write long-term notes for these cards — they are not deck-building decisions. If a note is written for such a card, it will not cause errors, but the prompt guidance should discourage it.

**Implementation**: Modify the existing injection path in `CombatConversation.add_round_state()` (`conversation.py:718`) which currently reads the `combat_hints` dict parameter. Replace with a `CardMemoryStore` query for the card's `note`, applying the "not in deck" filter. Remove the `combat_hints` parameter from `add_round_state()` and `loop._get_combat_hints()`.

### 4. Evolution Prompt Update

Change the `update_card_note` tool guidance to be evidence-gated:

**System prompt** (evolution_engine.py):
```
- Update a card note (update_card_note) to write an experience-based evaluation
  for a card. Prioritize cards without existing notes in the Card Notes section.
  Base your note on:
  (1) The card's rules_text from the Card Mechanics Reference
  (2) Observable combat outcomes from the Combat Digest
  (3) Keyword interactions deducible from card descriptions
  (4) Act death correlations from Card Memory Stats

  Evidence thresholds:
  - Mechanic discoveries and keyword interactions can be written with low sample
    count if directly grounded in rules_text (e.g. "Exhaust means one-use per combat").
  - Scenario-based strength (small-fight vs boss) requires observable patterns
    across 2+ combats of the relevant type.
  - Tier ratings and take/skip guidance require >=10 plays AND act death correlation
    data. Do not assign tiers based on a single run.

  Do NOT write notes for generated/status cards (Shiv, Burn, Slimed, Wound, etc.)
  — only for cards that are deck-building decisions.

  Only write discoveries that can be logically derived from the card descriptions
  and gameplay evidence.
```

**Tool description** (write_tools.py `UPDATE_CARD_NOTE`):
```
Write an experience-based evaluation for a card based on gameplay evidence
and card mechanics. The note replaces any existing note in all future prompts.
Base insights on rules_text descriptions and observable combat data.
```

**Tool schema change**: Rename `live_summary` → `note` in input properties. Raise `maxLength` from 200 to 400.

### 5. Note Content Standard

A good card note includes (as applicable):
- **Mechanic discoveries** (low sample OK if grounded in rules_text): "Survivor only discards if you have another card in hand" (derivable from "Discard 1 card" when hand size = 1)
- **Combo interactions** (low sample OK if grounded in both cards' rules_text): "Calculated Gamble + Sly cards = free mass play" (derivable from both cards' descriptions)
- **Scenario-based strength** (requires 2+ combats): "Blade Dance: Exhaust means one-use — strong for small fights, weak for boss" (derivable from Exhaust keyword + observed combat lengths)
- **Cross-run patterns** (requires multi-run evidence): "Noxious Fumes + block/draw = consistent Act 3 boss wins across N runs" (from combat digest data)
- **Take/skip guidance** (requires >=10 plays + act death data): "Skip if already have transition damage; take if deck lacks early AoE" (from act death correlations)

Max length: 400 characters.

### 6. Files Changed

| File | Change |
|------|--------|
| `src/memory/models_v2.py` | Replace `seed_note`/`combat_hint`/`live_summary` with `note`. Update `to_dict`, `from_dict`, `effective_note`, `has_content`. |
| `src/memory/card_memory_store.py` | Update `load_seeds()`: fill-only-if-empty semantics for `note`. Remove `combat_hint` merge logic. Update `query_cards()` to check `note` instead of `seed_note or live_summary`. |
| `src/skills/seeds/silent_card_notes.json` | Rename `seed_note` → `note`, remove all `combat_hint` entries. |
| `src/brain/evolution_engine.py` | Update `_handle_update_card_note` to write `note` (400 char limit). Update `_render_card_notes` to accept `seen_cards: tuple[str, ...]` instead of `deck_cards`. Update system prompt with evidence thresholds and status-card exclusion. Update call site in `build_evolution_context()` (line 2459) to pass `seen_card_names` from `build_card_mechanics_section()`. |
| `src/brain/write_tools.py` | Update `UPDATE_CARD_NOTE` tool schema: rename `live_summary` → `note`, raise `maxLength` to 400. Update description. |
| `src/postrun/context_builder.py` | New `build_card_mechanics_section(log_path, run_id) -> tuple[str, tuple[str, ...]]` returning formatted section + seen_card_names. Enhance `format_combat_round_digest()` with per-action deltas. New `build_relic_context()`. |
| `src/brain/conversation.py` | In `add_combat_start()` (line 568): inject deck card notes via `CardMemoryStore.query_cards()`. In `add_round_state()` (line 718): replace `combat_hints` parameter with `CardMemoryStore` query + "not in deck" filter. |
| `src/agent/loop.py` | Remove `_get_combat_hints()`. Pass `CardMemoryStore` reference and deck card names to `CombatConversation` for note injection. |
| `data/memory/v2/card_memories.json` | Migrated on load via `from_dict` backward compat. |
| `tests/test_card_memory.py` | Update for new field name. |

**Not changed in this spec** (deferred):
| File | Reason |
|------|--------|
| `src/knowledge/injector.py` | `_build_card_mechanics()` / `_build_card_knowledge_lines()` and their callers (`inject_combat_knowledge`, `inject_reward_knowledge`) remain as-is. They serve reward/shop/combat prompts with enrichment from `CardLookup`. Removing them requires defining replacement paths, which is a separate spec. |

### 7. Migration

- `CardMemory.from_dict`: `note = d.get("note") or d.get("live_summary") or d.get("seed_note", "")`
- Existing `card_memories.json` with `live_summary` or `seed_note` will auto-migrate on next load.
- `combat_hint` is dropped (not migrated — content is redundant with seed_note).
- `silent_card_notes.json` updated in-place (one-time manual edit).
- After migration, `card_memories.json` is the sole authority. Seed file only fills gaps for cards that have no stored entry or empty `note`.

### 8. Not In Scope

- Deleting `CardLookup`/`KeywordLookup`/`GameKnowledge` — still used for monster patterns, encounter type detection, reward/shop card enrichment. Separate cleanup spec.
- Replacing `inject_reward_knowledge` / `inject_combat_knowledge` in `knowledge/injector.py`. Deferred.
- Multi-character seed notes (only Silent has seeds currently).
- Changing when evolution runs or how many notes it updates per run.
- Cross-run offer/skip counting (`offer_count`/`skip_count` fields on CardMemory). Would require new persistent counters; deferred.
- Persistent notes for generated/status cards (Shiv, Burn, Slimed, etc.). These participate in combat-time injection if a note exists, but the prompt guidance discourages writing them.
