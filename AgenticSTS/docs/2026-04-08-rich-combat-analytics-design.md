# Rich Combat Analytics — Post-Run Information Enhancement

**Date:** 2026-04-08
**Status:** Draft
**Goal:** Give the post-run analysis LLM enough observable data to learn from combat outcomes — death causes, per-card damage/poison attribution, enemy mechanic timelines, and card descriptions for combo reasoning.

## Problem

The post-run pipeline (guide consolidation, skill discovery, rule distillation) cannot learn critical combat lessons because `_format_combat_episodes` discards most of the rich CombatDelta event data:

1. **Death cause invisible**: Agent dies to Sandpit timer (HP=31, not damage) but episode only shows `won=False, hp_after=0`. ~53% of Insatiable deaths are Sandpit kills, yet the guide says nothing about Frantic Escape priority.
2. **Per-card damage not surfaced**: CombatDelta events have exact `enemy_deltas.hp` per card_play, but `_format_combat_episodes` only shows `cards_played` names and total `damage_dealt`.
3. **Poison attribution lost**: Each `card_play` event records poison stacks applied via `powers_changed`, but this is never aggregated for the post-run LLM.
4. **Token source unknown**: Shivs from Blade Dance (exhaust, 3 per fight) vs Infinite Blades (1/turn, scales) are indistinguishable in output.
5. **Card descriptions absent**: CombatDelta stores only `source` (card name). Without `rules_text`, the LLM cannot reason about indirect effects (Crippling Cloud's draw→poison trigger, Catalyst's poison doubling, Envenom's attack→poison).
6. **Enemy power timeline missing**: Sandpit countdown, Strength scaling, etc. not tracked across rounds.

## Data Availability Audit

All needed data already exists in CombatDelta events or game state:

| Data | Source | Currently Stored? |
|------|--------|-------------------|
| Per-card enemy HP change | `event.enemy_deltas[].hp` | ✅ In events |
| Per-card poison stacks | `event.enemy_deltas[].powers_changed` Poison delta | ✅ In events |
| Exhaust tracking | `event.cards_exhausted[]` with rules_text | ✅ In events |
| Enemy power changes | `event.enemy_deltas[].powers_changed` | ✅ In events |
| Player power changes | `event.powers_changed` | ✅ In events |
| Round total damage | `round.damage_dealt` | ✅ In round |
| Card rules_text | `GameState.combat.player.hand[].rules_text` | ✅ In game state, ❌ NOT in CombatDelta |
| Player powers at combat start | `GameState.combat.player.powers` | ✅ In game state, ❌ NOT in CombatContext |
| Enemy powers per round | `GameState.combat.enemies[].powers` | ✅ In game state, ❌ NOT in CombatRound |

## Design

### 1. Data Model Changes

#### 1a. CombatDelta: add `source_description`

```python
@dataclass(frozen=True)
class CombatDelta:
    source: str = ""                  # card name (existing)
    source_description: str = ""      # rules_text from hand card (NEW)
    ...
```

Populated in `compute_combat_delta()` by looking up the played card in `pre.combat.player.hand` matching by name (or by the action's card index if available).

#### 1b. CombatContext: add `player_powers`

```python
@dataclass(frozen=True)
class CombatContext:
    ...
    player_powers: tuple[str, ...] = ()   # ("Noxious Fumes(2)", "Envenom(1)")  NEW
```

Populated in `build_combat_context()` from `GameState.combat.player.powers`.

#### 1c. CombatRound: add `enemy_powers_snapshot`

```python
@dataclass(frozen=True)
class CombatRound:
    ...
    enemy_powers_snapshot: tuple[tuple[str, ...], ...] = ()  # per-enemy power list at round start  NEW
```

Populated in `CombatTracker` at round start from game state enemy powers.

### 2. New Module: `src/memory/combat_analytics.py`

Pure computation module. Input: `CombatEpisode`. Output: `CombatAnalytics` dataclass.

```python
@dataclass(frozen=True)
class CardStats:
    name: str
    description: str            # rules_text
    plays: int
    total_damage: int           # sum of enemy HP deltas from this card's events
    total_block: int            # player block gained from this card's events
    poison_stacks_applied: int  # sum of Poison delta from this card's events
    exhausts: bool              # "Exhaust" in description
    tokens_generated: int       # e.g. Blade Dance → 3 (parsed from "Add N Shivs")
    energy_cost: int

@dataclass(frozen=True)
class CombatAnalytics:
    # Death analysis
    death_cause: str            # "hp_damage" | "sandpit" | "mechanic" | "" (win)
    death_detail: str           # human-readable: "Sandpit reached 0 with HP=31"

    # Per-card attribution
    card_stats: tuple[CardStats, ...]

    # Token source attribution (per round)
    token_attribution: dict     # {"Blade Dance": {"generated": 3, "attributed_damage": 36}, ...}

    # Poison tracking
    poison_by_card: dict        # {"Deadly Poison": 10, "Noxious Fumes (power)": 16, "Strike (Envenom)": 6}
    poison_tick_per_round: tuple[int, ...]  # (0, 4, 7, 10, 19, 33, ...)

    # Enemy mechanic timeline
    enemy_power_timeline: tuple[dict, ...]  # per-round: {"Sandpit": 3, "Strength": 2}

    # Cards played with descriptions (for LLM combo reasoning)
    unique_cards_played: tuple[tuple[str, str], ...]  # (("Blade Dance", "Add 3 Shivs. Exhaust."), ...)
    active_powers: tuple[str, ...]  # player powers active during combat
```

#### 2a. Death Cause Detection

```python
def detect_death_cause(episode: CombatEpisode) -> tuple[str, str]:
    if episode.won or episode.hp_after > 0:
        return ("", "")
    last_round = episode.rounds[-1]
    # If HP before final round > damage taken, it wasn't HP damage
    if last_round.hp_start > last_round.damage_taken + 5:
        # Check enemy powers for death mechanics
        if any("Sandpit" in p for powers in last_round.enemy_powers_snapshot for p in powers):
            return ("sandpit", f"Sandpit timer reached 0. HP was {last_round.hp_start} when killed.")
        return ("mechanic", f"Died with HP={last_round.hp_start}, damage_taken={last_round.damage_taken}. Likely mechanic kill.")
    return ("hp_damage", f"Killed by damage. HP {last_round.hp_start} → 0.")
```

#### 2b. Per-Card Damage Attribution

Iterate `round.events` where `event_type == "card_play"`, sum `enemy_deltas[].hp` per card name. Include `source_description` for LLM context.

#### 2c. Poison Stacks per Card

Parse `enemy_deltas[].powers_changed` for Poison entries:
- `+Poison(X)` → card applied X stacks
- `Poison(A→B)` → card applied B-A stacks

Aggregate by card name. Special case: if a non-poison card (per its rules_text) applies poison, annotate "(via Envenom)" using active player powers.

#### 2d. Per-Round Poison Tick Damage

`tick_damage = round.damage_dealt - sum(event enemy_hp deltas for all events in round)`

This captures poison ticks + power passive damage that happen between turns.

#### 2e. Token Attribution

Per round, track:
1. Active start-of-turn generators (Infinite Blades = 1 Shiv/turn, from player powers)
2. On-play generators (Blade Dance → 3, Cloak and Dagger → 1, parsed from `source_description` "Add N Shivs")
3. Token plays in that round
4. Attribute: generators' declared count as upper bound per source

#### 2f. Enemy Power Timeline

From `CombatRound.enemy_powers_snapshot` (new field), extract per-round values for key powers (Sandpit, Strength, Poison on enemies, etc.)

### 3. Integration: `_format_combat_episodes` Enhancement

In `guide_consolidator.py`, after existing format, append analytics sections for episodes that have events data:

```
## Combat Analytics: The Insatiable (LOSS - 6 rounds)
Death cause: Sandpit timer reached 0 (HP was 31 when killed)

Cards played (with descriptions):
  Blade Dance [1E, Exhaust]: "Add 3 Shivs into your Hand. Exhaust." → 1 play, 2 direct dmg, generated 3 Shivs
  Predator [2E]: "Deal 20 damage. Draw 2 cards." → 2 plays, 64 dmg
  Frantic Escape [1E, Exhaust]: "Gain 8 Block. Increase Sandpit by 1. Exhaust." → 1 play (R3 only!)
  Shiv [0E, Exhaust]: "Deal 4 damage. Exhaust." → 9 plays, 108 dmg
  ...

Active powers: Infinite Blades, Accuracy(6)

Token attribution:
  Blade Dance (1 play, exhaust): 3 Shivs → ~36 dmg
  Infinite Blades (power, 6 turns): 6 Shivs → ~72 dmg

Per-round poison tick damage: R1:0 R2:0 R3:0 R4:0 R5:0 R6:0
Poison stacks applied: (none in this fight)

Enemy power timeline:
  Sandpit: 4(R1) → 3(R2) → 4(R3,FE) → 3(R4) → 2(R5) → 1(R6) → DEATH
  Strength: 0 → 0 → 2 → 2 → 2 → 2

Unattributed damage per round (poison/power effects): R1:0 R2:0 ...
```

### 4. What We Do NOT Build

- ❌ No causal chain tracking (Crippling Cloud → draw → poison). LLM infers from rules_text + observed data.
- ❌ No per-card poison tick damage attribution. Only total stacks applied per card + total tick per round.
- ❌ No knowledge base card mechanic table. All info from runtime game state rules_text.
- ❌ No special-case code for Catalyst, Envenom, Corpse Explosion. LLM reads descriptions and data.

### 5. Files Changed

| File | Change |
|------|--------|
| `src/memory/models_v2.py` | Add `source_description` to CombatDelta, `player_powers` to CombatContext, `enemy_powers_snapshot` to CombatRound |
| `src/memory/combat_delta.py` | Populate `source_description` from hand card rules_text in `compute_combat_delta()`, `player_powers` in `build_combat_context()` |
| `src/memory/short_term.py` | Capture `enemy_powers_snapshot` at round start in CombatTracker |
| `src/memory/combat_analytics.py` | **NEW** — Pure analytics module: death cause, per-card stats, poison, tokens, enemy timeline |
| `src/memory/guide_consolidator.py` | `_format_combat_episodes` calls analytics and appends rich sections |
| `src/memory/combat_extractor.py` | Pass through `enemy_powers_snapshot` from tracker to CombatRound |

### 6. Verification Plan

After implementation:
1. Run `combat_analytics.py` against last 5 Insatiable episodes from `combat_episodes.jsonl`
2. Verify death_cause correctly identifies Sandpit deaths
3. Verify per-card damage sums match round totals
4. Verify poison stacks per card are accurate
5. Verify Shiv attribution to Blade Dance vs Infinite Blades
6. Print formatted analytics output and review for LLM readability
7. Run one live agent game and check guide consolidation prompt includes new analytics

### 7. Backward Compatibility

- Old episodes without `source_description` or `enemy_powers_snapshot`: analytics gracefully degrades (skips those sections, only computes what's available from existing fields)
- No migration needed — new fields have defaults (empty string/tuple)
- JSON serialization: new fields added to `to_dict`/`from_dict` with fallback defaults
