# Event Decision Enhancement Design

**Date**: 2026-04-13
**Status**: Approved
**Owner:** AgenticSTS Contributors

## Problem

Event decisions (both unknown-room events and per-act Ancient events) suffer from three systemic deficiencies:

1. **MCP information gap**: Event options that involve cards, relics, or potions only show names — no effects, costs, or descriptions. Example: "Transform Neutralize+ into Suppress+" gives the LLM no information about what Suppress+ does.

2. **Memory gap**: Events share a `rest_event` classification with rest sites, have no episodic memory, and no post-run analysis of event outcomes. The agent cannot learn from past event decisions.

3. **Skill matching gap**: Skills are retrieved by coarse `state_type` only, not by specific event content. Event-specific skills are never discovered during post-run analysis.

## Design

### 1. C# Mod — Extend `/state` Event Payload

Extend `EventOptionPayload` in `GameStateService.cs` to include structured effect data:

```csharp
EventOptionPayload {
    // Existing fields
    index: int,
    title: string,
    description: string,
    is_locked: bool,
    is_proceed: bool,
    will_kill_player: bool,
    has_relic_preview: bool,
    
    // New fields
    effect_description: string,     // Full effect text from EventModel
    hp_cost: int?,                  // HP cost if applicable
    gold_cost: int?,                // Gold cost if applicable
    cards_offered: CardInfo[],      // Cards involved (with full effects)
    relics_offered: RelicInfo[],    // Relics involved (with descriptions)
    potions_offered: PotionInfo[],  // Potions involved (with effects)
    curses_risk: string[],          // Potential curses from this option
}

CardInfo { name: string, cost: int, type: string, rules_text: string, is_upgraded: bool }
RelicInfo { name: string, description: string, rarity: string }
PotionInfo { name: string, description: string, type: string }
```

**Python side**: Extend `EventOptionPayload` in `upstream_models.py`, parse new fields in `state_parser.py`.

### 2. Event Prompt Enhancement

#### 2a. `build_event_prompt()` Rewrite

Transform `src/brain/prompts/event.py` to display structured option effects:

```
## Options
- [index=0] Gear Glass: See 15 cards from The Defect. Choose any number to add.
  → Cards: [list of Defect cards with cost, type, rules_text]
  → Risk: Cross-class cards may dilute deck coherence

- [index=1] Alchemical Coffer: Gain 4 potion slots filled with random potions.
  → Potions: [names + effects if pre-determined, "random" if unknown]
  → Value: 4 potion slots for combat flexibility

- [index=2] Archaic Tooth: Transform Neutralize+ into Suppress+.
  → Suppress+ (1 cost, Skill): Apply 3 Weak. Draw 1 card.
  → Replaces: Neutralize++ (0 cost): Apply 2 Weak, 2 Vulnerable.
  → Trade-off: Loses Vulnerable, gains draw + extra Weak stack
```

#### 2b. Boss Preview Injection

Inject upcoming boss information for strategic evaluation:

```
## Upcoming Bosses
- Act 2 Boss: [name] (~400 HP, ~10 turns). Key threat: [pattern].
- Act 3 Boss: [name] (~600 HP). Key threat: [pattern].
```

This helps the LLM evaluate options against future challenges (e.g., "will these Defect cards help against the Act 2 boss?").

#### 2c. Deck Synergy Hints

For options that add/transform cards, include a brief synergy analysis based on current deck:
- Does the offered card synergize with existing deck archetype?
- Does it address known deck weaknesses (from strategic thread)?

### 3. EventMemory Pipeline

Follows the established Combat/Route/CardBuild three-phase pattern.

#### 3a. EventTracker (ShortTermMemory)

New mutable tracker in `src/memory/short_term.py`:

```python
@dataclass
class EventTracker:
    event_id: str = ""
    event_title: str = ""
    floor: int = 0
    act: int = 1
    chosen_option_index: int = -1
    chosen_option_text: str = ""
    all_options: list[str] = field(default_factory=list)
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    deck_before: list[str] = field(default_factory=list)
    cards_gained: list[str] = field(default_factory=list)
    cards_lost: list[str] = field(default_factory=list)
    relics_gained: list[str] = field(default_factory=list)
    potions_gained: list[str] = field(default_factory=list)
```

ShortTermMemory additions:
- `_completed_events: list[EventTracker]` — accumulated during run
- `start_event(event_id, title, floor, act, hp, gold, deck)` — snapshot before
- `end_event(chosen_index, option_text, hp_after, gold_after, cards_gained, ...)` — snapshot after, diff computed
- `reset_run()` clears `_completed_events`

#### 3b. EventMemory (Frozen Model)

New frozen dataclass in `src/memory/models_v2.py`:

```python
@dataclass(frozen=True)
class EventMemory:
    memory_id: str = field(default_factory=_new_id)
    run_id: str = ""
    floor: int = 0
    act: int = 1
    event_id: str = ""
    event_title: str = ""
    character: str = ""
    chosen_option_index: int = -1
    chosen_option_text: str = ""
    all_options: tuple[str, ...] = ()
    # State changes
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    cards_gained: tuple[str, ...] = ()
    cards_lost: tuple[str, ...] = ()
    relics_gained: tuple[str, ...] = ()
    potions_gained: tuple[str, ...] = ()
    # Post-run LLM analysis (populated by boss impact analysis)
    boss_impact_score: float = 0.0      # -1.0 to 1.0
    boss_impact_analysis: str = ""      # LLM explanation
    outcome_quality: str = ""           # "good" | "neutral" | "bad"
    timestamp: float = field(default_factory=_now)
    
    def to_dict() -> dict
    @classmethod from_dict(d) -> EventMemory
```

#### 3c. EventMemoryStore

New file `src/memory/event_store.py`:

```python
class EventMemoryStore:
    """JSONL-backed event memory store at data/memory/v2/event_memories.jsonl"""
    
    def add(self, memory: EventMemory) -> None
    def query(self, event_id: str = "", character: str = "", act: int = 0, limit: int = 3) -> list[EventMemory]
    def update_boss_impact(self, memory_id: str, score: float, analysis: str, quality: str) -> None
    def save(self) -> None
    @classmethod def load(cls, path: Path) -> EventMemoryStore
```

Query strategy: exact `event_id` match > same `act` match > recency. Character-filtered.

#### 3d. EventExtractor

New file `src/memory/event_extractor.py`:

```python
def extract_event_memories(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
) -> list[EventMemory]:
    """Convert EventTracker → EventMemory (pure data, no LLM)."""
```

#### 3e. Post-run Boss Impact Analysis

New analysis step in the post-run pipeline (after existing extractions):

```python
def analyze_event_boss_impact(
    event_memories: list[EventMemory],
    combat_episodes: list[CombatEpisode],
    run_result: dict,  # victory, death_floor, boss_encounters
) -> list[EventMemory]:
    """Use analysis-tier LLM to evaluate each event's impact on boss fights.
    
    Returns updated EventMemory instances with boss_impact_score and analysis.
    """
```

Analysis prompt template:
```
You are analyzing event decisions from a completed Slay the Spire 2 run.

Run result: {victory/loss at floor X}
Boss encounters: {boss name, outcome, HP lost}

For each event below, evaluate how the chosen option affected boss fight outcomes:
- Did cards/relics/potions gained contribute to boss fights?
- Did HP/gold costs leave the player vulnerable?
- Would a different option have been better given the run outcome?

Score from -1.0 (very harmful) to 1.0 (very beneficial).
```

**Pipeline order** (updated):
```
memory extract → event extract → distill rules → guide consolidation → 
event boss impact analysis → skill discovery → self-evolution
```

### 4. Retriever — Event-specific Retrieval

#### 4a. Separate Event Classification

```python
def _classify_decision_type(gs: GameState) -> str:
    ...
    if gs.state_type == "event":
        return "event"              # NEW: independent classification
    if gs.state_type == "rest_site":
        return "rest"               # rest stays separate too
    ...
```

New token budget: `config.EVENT_MEMORY_TOKENS` (default: 300, separate from rest).

#### 4b. Event Retrieval Logic

Priority for event decisions:
1. **Past event memories** — same `event_id` + same `character`, sorted by recency
2. **Event guide** — if consolidated (3+ encounters)
3. **Rules** — event-context rules with tag matching
4. **Strategic thread** — current run intent

#### 4c. WorkingContext Extension

Add `event_memory_hints` field:

```python
@dataclass(frozen=True)
class WorkingContext:
    ...
    event_memory_hints: tuple[str, ...] = ()  # NEW
```

#### 4d. Prompt Injection Format

```
## Past Event Experience
- OROBAS (Act2 F18, Silent): Chose "Alchemical Coffer" → 4 potions.
  Boss impact: +0.6 (potions saved ~30 HP in boss fight)
- OROBAS (Act1 F9, Silent): Chose "Gear Glass" → 12 Defect cards.
  Boss impact: -0.8 (deck bloat prevented drawing key cards in boss)
```

### 5. Event Skill Discovery & Matching

#### 5a. Enhanced Skill Trigger Tags

When retrieving skills for events, build fine-grained tags:

```python
tags = {
    "state:event",
    f"event_id:{event_id}",            # Specific event
    f"event_type:{event_type}",        # ancient/normal/shrine
    f"option:transform_card",          # Option category
    f"option:gain_relic",
    f"involves:card:{card_name}",      # Specific cards
    f"act:{act}",
    f"hp:{hp_bucket}",                 # HP state
}
```

#### 5b. Skill Discovery Enhancement

Extend `skills/discovery.py` to include event decisions in the discovery prompt:

```python
# Add to discovery context
event_decisions = [
    f"Floor {em.floor}: {em.event_title} → Chose '{em.chosen_option_text}'. "
    f"Boss impact: {em.boss_impact_score:+.1f} ({em.boss_impact_analysis})"
    for em in event_memories
]
```

Discoverable event skill examples:
- Per-event strategy ("OROBAS: Alchemical Coffer best when potion slots < 2")
- Cross-event patterns ("Ancient events offering cross-class cards: only take if deck < 15 cards")
- HP-threshold rules ("Never choose HP-cost options below 50% HP in Act 2+")

#### 5c. EventGuide Consolidation

After 3+ encounters with the same event_id:

```python
@dataclass(frozen=True)
class EventGuide:
    event_id: str = ""
    character: str = ""
    guide_text: str = ""
    confidence: float = 0.0
    episode_count: int = 0
    timestamp: float = field(default_factory=_now)
```

Stored via `GuideStore` alongside combat/route/deck guides. Consolidation in `guide_consolidator.py` using the same LLM-based pattern.

### 6. Agent Loop Integration

Changes in `src/agent/loop.py`:

1. **Pre-event**: When `state_type == "event"`, call `short_term.start_event()` with current HP, gold, deck snapshot
2. **Prompt construction**: 
   - `build_event_prompt()` with extended option data
   - Retriever returns `event_memory_hints` 
   - SkillLibrary uses fine-grained event tags
3. **Post-event**: After action resolves, call `short_term.end_event()` with new state diff
4. **Post-run**: Call `extract_event_memories()` → store → `analyze_event_boss_impact()` → update store

### 7. Files Changed/Created

**New files:**
- `src/memory/event_store.py` — EventMemoryStore (JSONL persistence)
- `src/memory/event_extractor.py` — EventTracker → EventMemory conversion

**Modified files:**
- `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs` — Extended event payload
- `src/mcp_client/upstream_models.py` — Extended EventOptionPayload
- `src/state/state_parser.py` — Parse new event fields
- `src/brain/prompts/event.py` — Rich event prompt with effects + boss preview
- `src/memory/models_v2.py` — EventMemory dataclass + WorkingContext.event_memory_hints
- `src/memory/short_term.py` — EventTracker + start/end event methods
- `src/memory/retriever.py` — Separate "event" classification + event retrieval logic
- `src/memory/prompt_injector.py` — Event memory hint formatting
- `src/memory/memory_manager.py` — EventMemoryStore integration + post-run event analysis
- `src/memory/guide_store.py` — EventGuide model and storage
- `src/memory/guide_consolidator.py` — Event guide consolidation
- `src/skills/discovery.py` — Event decisions in skill discovery context
- `src/agent/loop.py` — Event tracking lifecycle + prompt construction
- `config.py` — EVENT_MEMORY_TOKENS config

### 8. Token Budget

- Event memory hints: ~300 tokens (configurable via `config.EVENT_MEMORY_TOKENS`)
- Extended option effects: ~50-100 tokens per option (from MCP data, not counted against memory budget)
- Boss preview: ~50 tokens
- Total event prompt increase: ~200-500 tokens depending on option complexity
