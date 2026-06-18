# Event Decision Enhancement Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give the event decision system full MCP-sourced information (card/relic/potion effects), episodic memory with boss-impact analysis, and fine-grained skill matching — on par with combat decision quality.

**Architecture:** Three layers built bottom-up. (1) C# mod extends `/state` event payload with structured option effects → Python parses them → prompt displays rich effects. (2) EventTracker/EventMemory/EventMemoryStore pipeline mirrors the existing Combat/Route/CardBuild pattern, with concrete deck/relic/potion diffs captured at event resolution and post-run boss-impact analysis enriching each memory. (3) Retriever separates events from rest sites, injects past event memories, GuideStore consolidates repeated events into EventGuides, and skill discovery includes event decisions in post-run analysis.

**Tech Stack:** Python 3.12 (frozen dataclasses, Pydantic models, JSONL persistence), C# .NET 9 (STS2 game mod)

**Spec:** `docs/superpowers/specs/2026-04-13-event-decision-enhancement-design.md`

---

### Task 1: Extend C# Event Payload with Option Effects

**Files:**
- Modify: `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs:6507-6537` (payload classes)
- Modify: `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs:4191-4240` (BuildEventPayload)

This task adds structured effect data to the event option payload so the Python agent can display full card/relic/potion details.

- [ ] **Step 1: Add new payload sub-models and extend EventOptionPayload**

In `GameStateService.cs`, just before `internal sealed class EventPayload` (line ~6507), add the sub-models. Then extend EventOptionPayload:

```csharp
internal sealed class EventCardInfo
{
    public string name { get; init; } = string.Empty;
    public int cost { get; init; }
    public string type { get; init; } = string.Empty;
    public string rules_text { get; init; } = string.Empty;
    public bool is_upgraded { get; init; }
}

internal sealed class EventRelicInfo
{
    public string name { get; init; } = string.Empty;
    public string description { get; init; } = string.Empty;
    public string rarity { get; init; } = string.Empty;
}

internal sealed class EventPotionInfo
{
    public string name { get; init; } = string.Empty;
    public string description { get; init; } = string.Empty;
    public string type { get; init; } = string.Empty;
}
```

Add to `EventOptionPayload`:

```csharp
internal sealed class EventOptionPayload
{
    public int index { get; init; }
    public string text_key { get; init; } = string.Empty;
    public string title { get; init; } = string.Empty;
    public string description { get; init; } = string.Empty;
    public bool is_locked { get; init; }
    public bool is_proceed { get; init; }
    public bool will_kill_player { get; init; }
    public bool has_relic_preview { get; init; }
    // New fields
    public string effect_description { get; init; } = string.Empty;
    public int? hp_cost { get; init; }
    public int? gold_cost { get; init; }
    public EventCardInfo[] cards_offered { get; init; } = Array.Empty<EventCardInfo>();
    public EventRelicInfo[] relics_offered { get; init; } = Array.Empty<EventRelicInfo>();
    public EventPotionInfo[] potions_offered { get; init; } = Array.Empty<EventPotionInfo>();
    public string[] curses_risk { get; init; } = Array.Empty<string>();
}
```

- [ ] **Step 2: Populate new fields in BuildEventPayload**

Inside the `for (int i = 0; i < currentOptions.Count; i++)` loop in `BuildEventPayload` (line ~4211), enrich each option with reflected data from the `EventOptionModel`. This is exploratory — the game's `EventOptionModel` may or may not expose card/relic/potion reward data via reflection. Add safe extraction helpers:

```csharp
// Inside the loop, after existing option fields:
string effectDesc = "";
int? hpCost = null;
int? goldCost = null;
var cardsOffered = new List<EventCardInfo>();
var relicsOffered = new List<EventRelicInfo>();
var potionsOffered = new List<EventPotionInfo>();
var cursesRisk = new List<string>();

try
{
    // Attempt to read option effects via reflection
    // Try Description (full text) — often contains effect details
    effectDesc = SafeReadString(() => opt.Description?.GetFormattedText());
    
    // Try to extract HP/gold cost from option model via reflection
    var hpCostObj = GetReflectedProperty(opt, "HpCost") ?? GetReflectedProperty(opt, "HealthCost");
    if (hpCostObj is int hpVal && hpVal != 0) hpCost = hpVal;
    
    var goldCostObj = GetReflectedProperty(opt, "GoldCost");
    if (goldCostObj is int goldVal && goldVal != 0) goldCost = goldVal;
    
    // Try to extract card rewards
    var cardReward = GetReflectedProperty(opt, "Card") ?? GetReflectedProperty(opt, "CardReward");
    if (cardReward != null)
    {
        // Build EventCardInfo from reflected card data
        cardsOffered.Add(new EventCardInfo
        {
            name = SafeReadString(() => GetReflectedProperty(cardReward, "Title")?.ToString()),
            cost = (int)(GetReflectedProperty(cardReward, "EnergyCost") ?? 0),
            type = SafeReadString(() => GetReflectedProperty(cardReward, "CardType")?.ToString()),
            rules_text = SafeReadString(() => GetReflectedProperty(cardReward, "RulesText")?.ToString()),
            is_upgraded = (bool)(GetReflectedProperty(cardReward, "IsUpgraded") ?? false)
        });
    }
    
    // Try to extract relic data
    var relic = GetReflectedProperty(opt, "Relic");
    if (relic != null)
    {
        relicsOffered.Add(new EventRelicInfo
        {
            name = SafeReadString(() => GetReflectedProperty(relic, "Title")?.ToString()),
            description = SafeReadString(() => GetReflectedProperty(relic, "Description")?.ToString()),
            rarity = SafeReadString(() => GetReflectedProperty(relic, "Rarity")?.ToString())
        });
    }
}
catch { /* Safe fallback — options still returned with existing fields */ }
```

Then include in the payload:
```csharp
options.Add(new EventOptionPayload
{
    index = i,
    text_key = SafeReadString(() => opt.TextKey),
    title = SafeReadString(() => opt.Title?.GetFormattedText()),
    description = SafeReadString(() => opt.Description?.GetFormattedText()),
    is_locked = SafeReadBool(() => opt.IsLocked),
    is_proceed = SafeReadBool(() => opt.IsProceed),
    will_kill_player = willKill,
    has_relic_preview = hasRelic,
    effect_description = effectDesc,
    hp_cost = hpCost,
    gold_cost = goldCost,
    cards_offered = cardsOffered.ToArray(),
    relics_offered = relicsOffered.ToArray(),
    potions_offered = potionsOffered.ToArray(),
    curses_risk = cursesRisk.ToArray()
});
```

**NOTE:** The exact reflection paths depend on the game's `EventOptionModel` internals. This is exploratory — test with a debugger to confirm property names. If a property doesn't exist, the safe wrappers return defaults. The Python side handles missing data gracefully.

- [ ] **Step 3: Build and deploy**

```bash
cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release
```

Copy DLL to game's mods directory and verify the `/state` response includes new fields when on an event screen.

- [ ] **Step 4: Commit**

```bash
git add STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs
git commit -m "feat(mod): extend event payload with card/relic/potion details"
```

---

### Task 2: Parse Extended Event Payload in Python

**Files:**
- Modify: `src/mcp_client/upstream_models.py:401-418`
- Test: `tests/test_upstream_state_parser.py`

- [ ] **Step 1: Write failing test for new event option fields**

In `tests/test_upstream_state_parser.py`, add:

```python
def test_event_option_extended_fields():
    """Extended event option payload includes card/relic/potion data."""
    from src.mcp_client.upstream_models import RawEventOptionPayload

    payload = RawEventOptionPayload(
        index=2,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        effect_description="Transform Neutralize+ into Suppress+.",
        hp_cost=None,
        gold_cost=None,
        cards_offered=[{
            "name": "Suppress+",
            "cost": 1,
            "type": "Skill",
            "rules_text": "Apply 3 Weak. Draw 1 card.",
            "is_upgraded": True,
        }],
        relics_offered=[],
        potions_offered=[],
        curses_risk=[],
    )
    assert payload.index == 2
    assert len(payload.cards_offered) == 1
    assert payload.cards_offered[0]["name"] == "Suppress+"
    assert payload.hp_cost is None


def test_event_option_backward_compatible():
    """Old payloads without new fields still parse."""
    from src.mcp_client.upstream_models import RawEventOptionPayload

    payload = RawEventOptionPayload(index=0, title="Test")
    assert payload.cards_offered == []
    assert payload.hp_cost is None
    assert payload.effect_description == ""
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_upstream_state_parser.py::test_event_option_extended_fields -xvs
```

Expected: FAIL — `RawEventOptionPayload` has no field `effect_description`.

- [ ] **Step 3: Add new fields to RawEventOptionPayload**

In `src/mcp_client/upstream_models.py`, modify `RawEventOptionPayload`:

```python
class RawEventOptionPayload(UpstreamModel):
    index: int = 0
    text_key: str = ""
    title: str = ""
    description: str = ""
    is_locked: bool = False
    is_proceed: bool = False
    will_kill_player: bool = False
    has_relic_preview: bool = False
    # Extended fields (from enhanced C# mod)
    effect_description: str = ""
    hp_cost: int | None = None
    gold_cost: int | None = None
    cards_offered: list[dict] = Field(default_factory=list)
    relics_offered: list[dict] = Field(default_factory=list)
    potions_offered: list[dict] = Field(default_factory=list)
    curses_risk: list[str] = Field(default_factory=list)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_upstream_state_parser.py::test_event_option_extended_fields tests/test_upstream_state_parser.py::test_event_option_backward_compatible -xvs
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/mcp_client/upstream_models.py tests/test_upstream_state_parser.py
git commit -m "feat: parse extended event option payload (cards/relics/potions)"
```

---

### Task 3: Enhance Event Prompt with Rich Option Details

**Files:**
- Modify: `src/brain/prompts/event.py`
- Test: `tests/test_event_prompt.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_event_prompt.py`:

```python
"""Tests for enhanced event prompt with rich option details."""
from unittest.mock import MagicMock

from src.brain.prompts.event import build_event_prompt


def _make_gs(event_id="OROBAS", options=None):
    """Build a minimal GameState mock with event data."""
    gs = MagicMock()
    gs.player_hp = 57
    gs.player_max_hp = 57
    gs.hp_ratio = 1.0
    gs.gold = 110
    gs.act = 2
    gs.floor = 18
    gs.state_type = "event"

    ev = MagicMock()
    ev.event_id = event_id
    ev.title = "Orobas"
    ev.description = "An ancient event with powerful choices."
    ev.options = options or []
    gs.event = ev
    return gs


def _make_option(index, title, description="", cards_offered=None,
                 relics_offered=None, potions_offered=None,
                 hp_cost=None, gold_cost=None, effect_description="",
                 is_locked=False, is_proceed=False, will_kill_player=False):
    opt = MagicMock()
    opt.index = index
    opt.title = title
    opt.description = description
    opt.is_locked = is_locked
    opt.is_proceed = is_proceed
    opt.will_kill_player = will_kill_player
    opt.effect_description = effect_description
    opt.hp_cost = hp_cost
    opt.gold_cost = gold_cost
    opt.cards_offered = cards_offered or []
    opt.relics_offered = relics_offered or []
    opt.potions_offered = potions_offered or []
    opt.curses_risk = []
    return opt


def test_card_effects_shown_in_prompt():
    """When an option offers cards, their effects appear in the prompt."""
    opt = _make_option(
        index=2,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        cards_offered=[{
            "name": "Suppress+",
            "cost": 1,
            "type": "Skill",
            "rules_text": "Apply 3 Weak. Draw 1 card.",
            "is_upgraded": True,
        }],
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Suppress+" in prompt
    assert "Apply 3 Weak" in prompt


def test_relic_description_shown():
    """When an option offers a relic, its description appears."""
    opt = _make_option(
        index=0,
        title="Accept the gift",
        relics_offered=[{
            "name": "Happy Flower",
            "description": "Every 3 turns, gain Energy.",
            "rarity": "common",
        }],
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Happy Flower" in prompt
    assert "Every 3 turns" in prompt


def test_hp_gold_cost_shown():
    """HP and gold costs are displayed when present."""
    opt = _make_option(
        index=0,
        title="Blood Sacrifice",
        description="Lose 10 HP, gain a random relic.",
        hp_cost=10,
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "HP cost: 10" in prompt


def test_backward_compat_no_extended_fields():
    """Options without extended fields still render correctly."""
    opt = MagicMock()
    opt.index = 0
    opt.title = "Basic Option"
    opt.description = "A simple choice."
    opt.is_locked = False
    opt.is_proceed = False
    opt.will_kill_player = False
    # No extended fields — mock returns default MagicMock for missing attrs
    opt.cards_offered = []
    opt.relics_offered = []
    opt.potions_offered = []
    opt.hp_cost = None
    opt.gold_cost = None
    opt.effect_description = ""
    opt.curses_risk = []
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Basic Option" in prompt
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
python -m pytest tests/test_event_prompt.py -xvs
```

Expected: FAIL — `build_event_prompt()` doesn't read `cards_offered` etc.

- [ ] **Step 3: Rewrite build_event_prompt() with rich option rendering**

Replace `src/brain/prompts/event.py`:

```python
# ruff: noqa: E501
"""Prompt template for event decisions.

Multi-factor scoring framework for event option evaluation.
Includes rich option details (card effects, relic descriptions, potion info)
from the extended MCP event payload.
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import format_deck_section, strip_bbcode
from src.mcp_client.upstream_models import RawDeckCardPayload
from src.state.game_state import GameState


def _format_card_info(card: dict) -> str:
    """Format a single card info dict into a readable line."""
    name = card.get("name", "?")
    cost = card.get("cost", "?")
    ctype = card.get("type", "")
    rules = card.get("rules_text", "")
    upgraded = "+" if card.get("is_upgraded") else ""
    parts = [f"{name}{upgraded}"]
    if cost != "?" or ctype:
        parts.append(f"(cost={cost}, {ctype})" if ctype else f"(cost={cost})")
    if rules:
        parts.append(f": {strip_bbcode(rules)}")
    return " ".join(parts)


def _format_relic_info(relic: dict) -> str:
    """Format a single relic info dict."""
    name = relic.get("name", "?")
    desc = relic.get("description", "")
    rarity = relic.get("rarity", "")
    parts = [name]
    if rarity:
        parts.append(f"({rarity})")
    if desc:
        parts.append(f"— {strip_bbcode(desc)}")
    return " ".join(parts)


def _format_potion_info(potion: dict) -> str:
    """Format a single potion info dict."""
    name = potion.get("name", "?")
    desc = potion.get("description", "")
    parts = [name]
    if desc:
        parts.append(f"— {strip_bbcode(desc)}")
    return " ".join(parts)


def _format_option_details(opt) -> list[str]:
    """Build detail lines for a single event option's rewards/costs."""
    details: list[str] = []

    # Costs
    hp_cost = getattr(opt, "hp_cost", None)
    gold_cost = getattr(opt, "gold_cost", None)
    if hp_cost and hp_cost > 0:
        details.append(f"  HP cost: {hp_cost}")
    if gold_cost and gold_cost > 0:
        details.append(f"  Gold cost: {gold_cost}")

    # Cards
    cards = getattr(opt, "cards_offered", []) or []
    for card in cards:
        details.append(f"  Card: {_format_card_info(card)}")

    # Relics
    relics = getattr(opt, "relics_offered", []) or []
    for relic in relics:
        details.append(f"  Relic: {_format_relic_info(relic)}")

    # Potions
    potions = getattr(opt, "potions_offered", []) or []
    for potion in potions:
        details.append(f"  Potion: {_format_potion_info(potion)}")

    # Curses
    curses = getattr(opt, "curses_risk", []) or []
    if curses:
        details.append(f"  Curse risk: {', '.join(curses)}")

    return details


def build_event_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
) -> str:
    """Build a prompt for event option selection with rich option details."""
    ev = gs.event
    if not ev:
        return ""

    lines = [
        "## Event",
        f"Event: {ev.title} (id={ev.event_id})",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold}",
    ]

    lines.append(f"Act: {gs.act} | Floor: {gs.floor}")

    lines.extend(format_deck_section(deck))

    if relics:
        lines.append("")
        lines.append("## Relics: " + ", ".join(relics))

    if ev.description:
        body = strip_bbcode(ev.description)
        if len(body) > 300:
            body = body[:297] + "..."
        lines.append("")
        lines.append(f"Description: {body}")

    lines.append("")
    lines.append("## Options")
    for opt in ev.options:
        locked = " [LOCKED]" if opt.is_locked else ""
        proceed = " [PROCEED]" if opt.is_proceed else ""
        lethal = " [LETHAL]" if opt.will_kill_player else ""
        desc = f": {strip_bbcode(opt.description)}" if opt.description else ""
        lines.append(f"- [index={opt.index}] {opt.title}{desc}{locked}{proceed}{lethal}")

        # Rich option details from extended payload
        details = _format_option_details(opt)
        lines.extend(details)

    lines.append("")
    lines.append("Evaluate each option's risk vs reward. Consider HP cost, gold cost, and what you gain.")
    lines.append("If an option offers a card: consider whether your deck needs more damage to handle upcoming bosses (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns). Prefer damage/poison options when your deck's attack output is low.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_prompt.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/event.py tests/test_event_prompt.py
git commit -m "feat: rich event prompt with card/relic/potion details"
```

---

### Task 4: EventMemory Data Model

**Files:**
- Modify: `src/memory/models_v2.py`
- Test: `tests/test_event_memory_model.py` (create)

- [ ] **Step 1: Write failing test for EventMemory**

Create `tests/test_event_memory_model.py`:

```python
"""Tests for EventMemory frozen dataclass."""


def test_event_memory_roundtrip():
    """EventMemory serializes and deserializes correctly."""
    from src.memory.models_v2 import EventMemory

    mem = EventMemory(
        run_id="run_abc",
        floor=18,
        act=2,
        event_id="OROBAS",
        event_title="Orobas",
        character="the silent",
        chosen_option_index=1,
        chosen_option_text="Alchemical Coffer",
        all_options=("Gear Glass", "Alchemical Coffer", "Archaic Tooth"),
        hp_before=57,
        hp_after=57,
        gold_before=110,
        gold_after=110,
        cards_gained=(),
        cards_lost=(),
        relics_gained=(),
        potions_gained=("Fire Potion", "Block Potion", "Weak Potion", "Regen Potion"),
        boss_impact_score=0.0,
        boss_impact_analysis="",
        outcome_quality="",
    )
    d = mem.to_dict()
    restored = EventMemory.from_dict(d)
    assert restored.event_id == "OROBAS"
    assert restored.chosen_option_index == 1
    assert restored.potions_gained == ("Fire Potion", "Block Potion", "Weak Potion", "Regen Potion")
    assert restored.run_id == "run_abc"


def test_event_memory_defaults():
    """EventMemory has sane defaults for all fields."""
    from src.memory.models_v2 import EventMemory

    mem = EventMemory()
    assert mem.event_id == ""
    assert mem.boss_impact_score == 0.0
    assert mem.cards_gained == ()
    assert mem.memory_id  # auto-generated
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_memory_model.py -xvs
```

Expected: FAIL — `EventMemory` does not exist yet.

- [ ] **Step 3: Add EventMemory and EventGuide to models_v2.py**

In `src/memory/models_v2.py`, after the `DeckGuide` class (around line ~830), add:

```python
# ── Event Models ──────────────────────────────────────────────


@dataclass(frozen=True)
class EventMemory:
    """A single event decision with outcome tracking and boss impact analysis."""

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
    # Post-run LLM analysis
    boss_impact_score: float = 0.0      # -1.0 (harmful) to 1.0 (beneficial)
    boss_impact_analysis: str = ""
    outcome_quality: str = ""           # "good" | "neutral" | "bad"
    timestamp: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "run_id": self.run_id,
            "floor": self.floor,
            "act": self.act,
            "event_id": self.event_id,
            "event_title": self.event_title,
            "character": self.character,
            "chosen_option_index": self.chosen_option_index,
            "chosen_option_text": self.chosen_option_text,
            "all_options": list(self.all_options),
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "gold_before": self.gold_before,
            "gold_after": self.gold_after,
            "cards_gained": list(self.cards_gained),
            "cards_lost": list(self.cards_lost),
            "relics_gained": list(self.relics_gained),
            "potions_gained": list(self.potions_gained),
            "boss_impact_score": self.boss_impact_score,
            "boss_impact_analysis": self.boss_impact_analysis,
            "outcome_quality": self.outcome_quality,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventMemory:
        return cls(
            memory_id=d.get("memory_id", _new_id()),
            run_id=d.get("run_id", ""),
            floor=d.get("floor", 0),
            act=d.get("act", 1),
            event_id=d.get("event_id", ""),
            event_title=d.get("event_title", ""),
            character=d.get("character", ""),
            chosen_option_index=d.get("chosen_option_index", -1),
            chosen_option_text=d.get("chosen_option_text", ""),
            all_options=tuple(d.get("all_options", ())),
            hp_before=d.get("hp_before", 0),
            hp_after=d.get("hp_after", 0),
            gold_before=d.get("gold_before", 0),
            gold_after=d.get("gold_after", 0),
            cards_gained=tuple(d.get("cards_gained", ())),
            cards_lost=tuple(d.get("cards_lost", ())),
            relics_gained=tuple(d.get("relics_gained", ())),
            potions_gained=tuple(d.get("potions_gained", ())),
            boss_impact_score=d.get("boss_impact_score", 0.0),
            boss_impact_analysis=d.get("boss_impact_analysis", ""),
            outcome_quality=d.get("outcome_quality", ""),
            timestamp=d.get("timestamp", _now()),
        )


@dataclass(frozen=True)
class EventGuide:
    """Consolidated guide for a specific event type."""

    guide_id: str = field(default_factory=_new_id)
    event_id: str = ""
    character: str = ""
    guide_text: str = ""
    episode_count: int = 0
    confidence: float = 0.5
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide_id": self.guide_id,
            "event_id": self.event_id,
            "character": self.character,
            "guide_text": self.guide_text,
            "episode_count": self.episode_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventGuide:
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            event_id=d.get("event_id", ""),
            character=d.get("character", ""),
            guide_text=d.get("guide_text", ""),
            episode_count=d.get("episode_count", 0),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
        )
```

- [ ] **Step 4: Add event_memory_hints to WorkingContext**

In the `WorkingContext` dataclass, add after `situation_hints`:

```python
    # Event-specific memory hints
    event_memory_hints: tuple[str, ...] = ()
```

Update `is_empty` to include the new field, and update `estimated_tokens()` / `total_hints` if they exist.

- [ ] **Step 5: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_memory_model.py -xvs
```

Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_event_memory_model.py
git commit -m "feat: EventMemory + EventGuide data models"
```

---

### Task 5: EventTracker in ShortTermMemory

**Files:**
- Modify: `src/memory/short_term.py`
- Test: `tests/test_short_term_event.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_short_term_event.py`:

```python
"""Tests for EventTracker in ShortTermMemory."""
from src.memory.short_term import ShortTermMemory


def test_event_tracking_lifecycle():
    """start_event → end_event → completed_events records the event."""
    stm = ShortTermMemory()
    stm.start_event(
        event_id="OROBAS",
        event_title="Orobas",
        floor=18,
        act=2,
        hp=57,
        gold=110,
        deck=["Strike", "Defend", "Neutralize++"],
    )
    stm.end_event(
        chosen_index=1,
        option_text="Alchemical Coffer",
        hp_after=57,
        gold_after=110,
        all_options=["Gear Glass", "Alchemical Coffer", "Archaic Tooth"],
        cards_gained=[],
        cards_lost=[],
        relics_gained=[],
        potions_gained=["Fire Potion", "Block Potion"],
    )
    assert len(stm.completed_events) == 1
    ev = stm.completed_events[0]
    assert ev.event_id == "OROBAS"
    assert ev.chosen_option_index == 1
    assert ev.hp_before == 57
    assert ev.potions_gained == ["Fire Potion", "Block Potion"]


def test_reset_run_clears_events():
    """reset_run clears completed events."""
    stm = ShortTermMemory()
    stm.start_event("TEST", "Test", 5, 1, 50, 100, [])
    stm.end_event(0, "Option A", 50, 100, ["Option A"], [], [], [], [])
    assert len(stm.completed_events) == 1
    stm.reset_run()
    assert len(stm.completed_events) == 0


def test_multiple_events_tracked():
    """Multiple events in a single run are all tracked."""
    stm = ShortTermMemory()
    for i in range(3):
        stm.start_event(f"EVT_{i}", f"Event {i}", i + 5, 1, 50, 100, [])
        stm.end_event(0, "Option A", 48, 95, ["Option A"], [], [], [], [])
    assert len(stm.completed_events) == 3
    assert stm.completed_events[2].event_id == "EVT_2"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_short_term_event.py -xvs
```

Expected: FAIL — `ShortTermMemory` has no `start_event`/`end_event`/`completed_events`.

- [ ] **Step 3: Add EventTracker and tracking methods to ShortTermMemory**

In `src/memory/short_term.py`, add after the existing `RouteNodeTracker` class:

```python
@dataclass
class EventTracker:
    """Mutable tracker for a single event encounter."""

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

In `ShortTermMemory.__init__`, add:

```python
        # Event tracking
        self._completed_events: list[EventTracker] = []
        self._current_event: EventTracker | None = None
```

In `reset_run`, add:

```python
        self._completed_events.clear()
        self._current_event = None
```

Add event methods:

```python
    # ── Event tracking ─────────────────────────────────────────

    def start_event(
        self,
        event_id: str,
        event_title: str,
        floor: int,
        act: int,
        hp: int,
        gold: int,
        deck: list[str],
    ) -> None:
        """Begin tracking an event encounter."""
        self._current_event = EventTracker(
            event_id=event_id,
            event_title=event_title,
            floor=floor,
            act=act,
            hp_before=hp,
            gold_before=gold,
            deck_before=list(deck),
        )

    def end_event(
        self,
        chosen_index: int,
        option_text: str,
        hp_after: int,
        gold_after: int,
        all_options: list[str],
        cards_gained: list[str],
        cards_lost: list[str],
        relics_gained: list[str],
        potions_gained: list[str],
    ) -> None:
        """Finalize the current event with outcome data."""
        if self._current_event is None:
            logger.warning("end_event called without start_event")
            return
        self._current_event.chosen_option_index = chosen_index
        self._current_event.chosen_option_text = option_text
        self._current_event.hp_after = hp_after
        self._current_event.gold_after = gold_after
        self._current_event.all_options = list(all_options)
        self._current_event.cards_gained = list(cards_gained)
        self._current_event.cards_lost = list(cards_lost)
        self._current_event.relics_gained = list(relics_gained)
        self._current_event.potions_gained = list(potions_gained)
        self._completed_events.append(self._current_event)
        self._current_event = None

    @property
    def completed_events(self) -> list[EventTracker]:
        return self._completed_events

    @property
    def current_event(self) -> EventTracker | None:
        return self._current_event
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_short_term_event.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/short_term.py tests/test_short_term_event.py
git commit -m "feat: EventTracker in ShortTermMemory"
```

---

### Task 6: EventMemoryStore (JSONL Persistence)

**Files:**
- Create: `src/memory/event_store.py`
- Test: `tests/test_event_store.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_event_store.py`:

```python
"""Tests for EventMemoryStore JSONL persistence."""
import tempfile
from pathlib import Path

from src.memory.models_v2 import EventMemory


def _make_event(event_id="OROBAS", character="the silent", act=2, floor=18,
                run_id="run_1", chosen=1, option_text="Alchemical Coffer"):
    return EventMemory(
        run_id=run_id,
        floor=floor,
        act=act,
        event_id=event_id,
        event_title=event_id.title(),
        character=character,
        chosen_option_index=chosen,
        chosen_option_text=option_text,
        all_options=("Option A", "Option B", "Option C"),
    )


def test_add_and_query():
    """Store an event and retrieve it by event_id."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event())
    results = store.query(event_id="OROBAS", character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "OROBAS"


def test_query_filters_character():
    """Query filters by character."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event(character="the silent"))
    store.add(_make_event(character="the ironclad"))
    results = store.query(event_id="OROBAS", character="the silent")
    assert len(results) == 1


def test_persistence_roundtrip():
    """Save and load preserves all data."""
    from src.memory.event_store import EventMemoryStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = EventMemoryStore()
        store.add(_make_event())
        store.add(_make_event(event_id="SHRINE", floor=10))
        store.save(path)

        loaded = EventMemoryStore.load(path)
        assert loaded.count == 2
        results = loaded.query(event_id="OROBAS")
        assert len(results) == 1


def test_update_boss_impact():
    """update_boss_impact modifies an existing memory."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    mem = _make_event()
    store.add(mem)
    store.update_boss_impact(mem.memory_id, 0.6, "Potions saved HP", "good")
    results = store.query(event_id="OROBAS")
    assert results[0].boss_impact_score == 0.6
    assert results[0].outcome_quality == "good"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_store.py -xvs
```

Expected: FAIL — `event_store` module does not exist.

- [ ] **Step 3: Implement EventMemoryStore**

Create `src/memory/event_store.py`:

```python
"""Thread-safe event memory store with JSONL persistence.

Stores event decisions with boss-impact analysis for retrieval
during future event encounters.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import replace
from pathlib import Path

from src.memory.models_v2 import EventMemory, normalize_character

logger = logging.getLogger(__name__)


class EventMemoryStore:
    """Thread-safe store for event memories with JSONL persistence."""

    def __init__(self) -> None:
        self._memories: list[EventMemory] = []
        self._lock = threading.Lock()

    def add(self, memory: EventMemory) -> None:
        with self._lock:
            self._memories.append(memory)

    def add_batch(self, memories: list[EventMemory]) -> None:
        with self._lock:
            self._memories.extend(memories)

    def query(
        self,
        event_id: str = "",
        character: str = "",
        act: int = 0,
        limit: int = 3,
    ) -> list[EventMemory]:
        """Retrieve event memories by event_id, character, and/or act.

        Priority: exact event_id match > same act > recency.
        """
        with self._lock:
            candidates = list(self._memories)

        if character:
            norm_char = normalize_character(character)
            candidates = [m for m in candidates if normalize_character(m.character) == norm_char]

        if event_id:
            exact = [m for m in candidates if m.event_id.upper() == event_id.upper()]
            if exact:
                candidates = exact

        if act > 0 and not event_id:
            act_match = [m for m in candidates if m.act == act]
            if act_match:
                candidates = act_match

        # Sort by recency
        candidates.sort(key=lambda m: m.timestamp, reverse=True)
        return candidates[:limit]

    def update_boss_impact(
        self,
        memory_id: str,
        score: float,
        analysis: str,
        quality: str,
    ) -> None:
        """Update boss impact fields on an existing memory."""
        with self._lock:
            for i, mem in enumerate(self._memories):
                if mem.memory_id == memory_id:
                    self._memories[i] = replace(
                        mem,
                        boss_impact_score=score,
                        boss_impact_analysis=analysis,
                        outcome_quality=quality,
                    )
                    return

    @property
    def count(self) -> int:
        with self._lock:
            return len(self._memories)

    def save(self, path: Path) -> None:
        with self._lock:
            snapshot = list(self._memories)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            for mem in snapshot:
                f.write(json.dumps(mem.to_dict()) + "\n")
        logger.debug("Saved %d event memories to %s", len(snapshot), path)

    @classmethod
    def load(cls, path: Path) -> EventMemoryStore:
        store = cls()
        if not path.exists():
            return store
        try:
            with open(path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        store._memories.append(EventMemory.from_dict(json.loads(line)))
            logger.info("Loaded %d event memories from %s", store.count, path)
        except Exception as exc:
            logger.warning("Failed to load event store from %s: %s", path, exc)
        return store
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_store.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/event_store.py tests/test_event_store.py
git commit -m "feat: EventMemoryStore with JSONL persistence"
```

---

### Task 7: EventExtractor (ShortTermMemory → EventMemory)

**Files:**
- Create: `src/memory/event_extractor.py`
- Test: `tests/test_event_extractor.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_event_extractor.py`:

```python
"""Tests for event memory extraction."""
from src.memory.short_term import ShortTermMemory


def test_extract_event_memories():
    """Extracts EventMemory from completed events in ShortTermMemory."""
    from src.memory.event_extractor import extract_event_memories

    stm = ShortTermMemory()
    stm.start_event("OROBAS", "Orobas", 18, 2, 57, 110, ["Strike", "Defend"])
    stm.end_event(1, "Alchemical Coffer", 57, 110,
                  ["Gear Glass", "Alchemical Coffer", "Archaic Tooth"],
                  [], [], [], ["Fire Potion"])

    stm.start_event("SHRINE", "Shrine", 10, 1, 60, 50, ["Strike"])
    stm.end_event(0, "Pray", 55, 50, ["Pray", "Leave"], [], [], [], [])

    memories = extract_event_memories(stm, "run_123", "the silent")
    assert len(memories) == 2
    assert memories[0].event_id == "OROBAS"
    assert memories[0].character == "the silent"
    assert memories[0].run_id == "run_123"
    assert memories[0].potions_gained == ("Fire Potion",)
    assert memories[1].event_id == "SHRINE"
    assert memories[1].hp_before == 60
    assert memories[1].hp_after == 55


def test_extract_empty():
    """No events returns empty list."""
    from src.memory.event_extractor import extract_event_memories

    stm = ShortTermMemory()
    memories = extract_event_memories(stm, "run_x", "the silent")
    assert memories == []
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_extractor.py -xvs
```

Expected: FAIL — `event_extractor` module does not exist.

- [ ] **Step 3: Implement extract_event_memories**

Create `src/memory/event_extractor.py`:

```python
"""Event memory extractor: converts ShortTermMemory event data into EventMemory.

Pure data conversion — no LLM calls. Boss impact analysis runs separately in Task 11.
"""

from __future__ import annotations

import logging

from src.memory.models_v2 import EventMemory, normalize_character
from src.memory.short_term import ShortTermMemory

logger = logging.getLogger(__name__)


def extract_event_memories(
    short_term: ShortTermMemory,
    run_id: str,
    character: str,
) -> list[EventMemory]:
    """Extract EventMemory instances from completed events in short-term memory.

    Returns frozen EventMemory objects ready for long-term storage.
    """
    memories: list[EventMemory] = []

    for tracker in short_term.completed_events:
        memory = EventMemory(
            run_id=run_id,
            floor=tracker.floor,
            act=tracker.act,
            event_id=tracker.event_id,
            event_title=tracker.event_title,
            character=normalize_character(character),
            chosen_option_index=tracker.chosen_option_index,
            chosen_option_text=tracker.chosen_option_text,
            all_options=tuple(tracker.all_options),
            hp_before=tracker.hp_before,
            hp_after=tracker.hp_after,
            gold_before=tracker.gold_before,
            gold_after=tracker.gold_after,
            cards_gained=tuple(tracker.cards_gained),
            cards_lost=tuple(tracker.cards_lost),
            relics_gained=tuple(tracker.relics_gained),
            potions_gained=tuple(tracker.potions_gained),
        )
        memories.append(memory)

    logger.info(
        "Extracted %d event memories from run %s",
        len(memories), run_id[:8] if run_id else "?",
    )
    return memories
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_extractor.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/event_extractor.py tests/test_event_extractor.py
git commit -m "feat: EventExtractor converts ShortTermMemory → EventMemory"
```

---

### Task 8: Config + MemoryManager + Retriever Integration

**Files:**
- Modify: `config.py`
- Modify: `src/memory/memory_manager.py`
- Modify: `src/memory/retriever.py`
- Modify: `src/memory/prompt_injector.py`
- Test: `tests/test_event_retrieval.py` (create)

- [ ] **Step 1: Write failing test for event retrieval**

Create `tests/test_event_retrieval.py`:

```python
"""Tests for event-specific memory retrieval."""
from unittest.mock import MagicMock

from src.memory.retriever import _classify_decision_type


def test_event_classified_separately():
    """Events are classified as 'event', not 'rest_event'."""
    gs = MagicMock()
    gs.is_combat = False
    gs.is_map = False
    gs.state_type = "event"
    assert _classify_decision_type(gs) == "event"


def test_rest_classified_separately():
    """Rest sites are classified as 'rest', not 'rest_event'."""
    gs = MagicMock()
    gs.is_combat = False
    gs.is_map = False
    gs.state_type = "rest_site"
    assert _classify_decision_type(gs) == "rest"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_retrieval.py -xvs
```

Expected: FAIL — currently returns `"rest_event"` for both.

- [ ] **Step 3: Add EVENT_MEMORY_TOKENS to config.py**

In `config.py`, after `REST_EVENT_MEMORY_TOKENS = 150`, add:

```python
EVENT_MEMORY_TOKENS = 300            # budget for event decisions (separate from rest)
```

- [ ] **Step 4: Update _classify_decision_type in retriever.py**

In `src/memory/retriever.py`, replace lines 40-41:

```python
    if gs.state_type in ("rest_site", "event"):
        return "rest_event"
```

With:

```python
    if gs.state_type == "event":
        return "event"
    if gs.state_type == "rest_site":
        return "rest"
```

- [ ] **Step 5: Update _token_budget in retriever.py**

Replace the budgets dict (line ~47):

```python
    budgets = {
        "combat": config.COMBAT_MEMORY_TOKENS,
        "route": config.ROUTE_MEMORY_TOKENS,
        "deck": config.DECK_MEMORY_TOKENS,
        "event": config.EVENT_MEMORY_TOKENS,
        "rest": config.REST_EVENT_MEMORY_TOKENS,
        "rest_event": config.REST_EVENT_MEMORY_TOKENS,  # backward compat
    }
```

- [ ] **Step 6: Add event retrieval branch in query_for_decision**

In `retriever.py`, update the `query_for_decision` function signature to accept `event_store`:

```python
def query_for_decision(
    gs: GameState,
    short_term: ShortTermMemory,
    combat_store: CombatMemoryStore,
    route_store: RouteMemoryStore,
    card_build_store: CardBuildStore,
    guide_store: GuideStore,
    rule_store: RuleStore,
    *,
    card_memory_store: CardMemoryStore | None = None,
    event_store=None,  # EventMemoryStore | None
    archetype: str = "",
    current_round: int = 0,
) -> WorkingContext:
```

Then, in the `else` branch (the `rest_event` / `other` section, line ~514), add an `event` branch before the existing code:

```python
    elif decision_type == "event":
        event_memory_hints_list: list[str] = []
        # 1. Past event memories
        if event_store is not None and gs.event:
            past_events = event_store.query(
                event_id=gs.event.event_id,
                character=character,
                limit=3,
            )
            for em in past_events:
                impact = f" Boss impact: {em.boss_impact_score:+.1f}" if em.boss_impact_score else ""
                analysis = f" ({em.boss_impact_analysis})" if em.boss_impact_analysis else ""
                event_memory_hints_list.append(
                    f"{em.event_title} (Act{em.act} F{em.floor}): "
                    f"Chose \"{em.chosen_option_text}\".{impact}{analysis}"
                )

        # 2. Event guide
        if gs.event:
            event_guide = guide_store.get_event_guide(gs.event.event_id, character)
            if event_guide and event_guide.confidence >= 0.3:
                event_memory_hints_list.insert(0,
                    f"[Event Guide: {event_guide.event_id}] {event_guide.guide_text}"
                )

        # 3. Rules
        event_rule_tags = _build_common_rule_tags(gs, decision_type)
        _add_runtime_signals(event_rule_tags, gs, short_term)
        if gs.event:
            _add_tag(event_rule_tags, "event_id", gs.event.event_id)
        rules = rule_store.query(
            context="event",
            tags=event_rule_tags,
            min_confidence=0.3,
            limit=3,
            require_verified=True,
            require_tag_match=True,
        )
        for r in rules:
            rule_hints.append(f"Rule ({r.confidence:.0%}): {r.rule_text}")
            rule_ids.append(r.rule_id)

        event_memory_hints = event_memory_hints_list

    elif decision_type == "rest":
        # Existing rest logic (was part of the old rest_event branch)
        other_rule_tags = _build_common_rule_tags(gs, decision_type)
        _add_runtime_signals(other_rule_tags, gs, short_term)
        rules = rule_store.query(
            context="rest",
            tags=other_rule_tags,
            min_confidence=0.3,
            limit=3,
            require_verified=True,
            require_tag_match=True,
        )
        for r in rules:
            rule_hints.append(f"Rule ({r.confidence:.0%}): {r.rule_text}")
            rule_ids.append(r.rule_id)
```

Update WorkingContext assembly to include `event_memory_hints`:

```python
    wc = WorkingContext(
        ...
        event_memory_hints=tuple(event_memory_hints) if 'event_memory_hints' in dir() and event_memory_hints else (),
    )
```

Actually, cleaner approach — initialize `event_memory_hints` as empty list alongside other hint lists at the top:

```python
    event_memory_hints: list[str] = []
```

Then populate it inside the `event` branch.

- [ ] **Step 7: Add event_memory_hints formatting in prompt_injector.py**

In `src/memory/prompt_injector.py`, in `format_working_context()`, after the card memory section (before short_term_hints), add:

```python
    # Event memory (past event decisions and boss impact)
    if wc.event_memory_hints:
        parts.append("## Past Event Experience")
        parts.append("*Outcomes from previous encounters with this event.*\n")
        for hint in wc.event_memory_hints:
            parts.append(f"- {hint}")
        parts.append("")
```

- [ ] **Step 8: Integrate EventMemoryStore into MemoryManager**

In `src/memory/memory_manager.py`:

Import and initialize:
```python
from src.memory.event_store import EventMemoryStore
```

In `_init_v2_stores`:
```python
        self._event_store = EventMemoryStore.load(
            self._v2_dir / "event_memories.jsonl",
        )
```

Add property:
```python
    @property
    def event_store(self):
        return self._event_store
```

Update `query_for_decision` to pass `event_store`:
```python
        return query_for_decision(
            ...
            event_store=self._event_store,
            ...
        )
```

Update `save_all`:
```python
        self._event_store.save(v2_dir / "event_memories.jsonl")
```

Update `stats`:
```python
            "v2_event_memories": self._event_store.count,
```

Update log in `_init_v2_stores`:
```python
            "%d event",
            self._event_store.count,
```

- [ ] **Step 9: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_retrieval.py -xvs
```

Expected: All PASS

- [ ] **Step 10: Commit**

```bash
git add config.py src/memory/retriever.py src/memory/prompt_injector.py src/memory/memory_manager.py tests/test_event_retrieval.py
git commit -m "feat: event-specific retrieval, prompt injection, and MemoryManager integration"
```

---

### Task 9: EventGuide in GuideStore

**Files:**
- Modify: `src/memory/guide_store.py`
- Test: `tests/test_event_guide_store.py` (create)

- [ ] **Step 1: Write failing test**

Create `tests/test_event_guide_store.py`:

```python
"""Tests for EventGuide storage in GuideStore."""
import tempfile
from pathlib import Path

from src.memory.models_v2 import EventGuide


def test_event_guide_set_and_get():
    """Store and retrieve an event guide."""
    from src.memory.guide_store import GuideStore

    store = GuideStore()
    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Alchemical Coffer is best when potion slots are low.",
        episode_count=5,
        confidence=0.7,
    )
    store.set_event_guide(guide)
    result = store.get_event_guide("OROBAS", "the silent")
    assert result is not None
    assert result.guide_text.startswith("Alchemical Coffer")


def test_event_guide_persistence():
    """Event guides survive save/load."""
    from src.memory.guide_store import GuideStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guides.json"
        store = GuideStore()
        store.set_event_guide(EventGuide(
            event_id="OROBAS", character="the silent",
            guide_text="Test guide", episode_count=3, confidence=0.6,
        ))
        store.save(path)

        loaded = GuideStore.load(path)
        result = loaded.get_event_guide("OROBAS", "the silent")
        assert result is not None
        assert result.guide_text == "Test guide"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_event_guide_store.py -xvs
```

Expected: FAIL — `GuideStore` has no `set_event_guide`/`get_event_guide`.

- [ ] **Step 3: Add EventGuide support to GuideStore**

In `src/memory/guide_store.py`, add import:

```python
from src.memory.models_v2 import CombatGuide, DeckGuide, EventGuide, RouteGuide, normalize_character
```

In `__init__`:
```python
        self._event_guides: dict[str, EventGuide] = {}    # key: "event_id:character"
```

Add event guide methods (after deck guide section):

```python
    # ── Event guides ───────────────────────────────────────────

    @staticmethod
    def _event_key(event_id: str, character: str) -> str:
        return f"{event_id.upper()}:{normalize_character(character)}"

    def get_event_guide(self, event_id: str, character: str) -> EventGuide | None:
        with self._lock:
            return self._event_guides.get(self._event_key(event_id, character))

    def set_event_guide(self, guide: EventGuide) -> None:
        with self._lock:
            key = self._event_key(guide.event_id, guide.character)
            self._event_guides[key] = guide

    @property
    def event_guide_count(self) -> int:
        with self._lock:
            return len(self._event_guides)
```

In `save`, add to the data dict:
```python
                "event_guides": {k: g.to_dict() for k, g in self._event_guides.items()},
```

In `load`, add after deck guides loading:
```python
            for _k, v in data.get("event_guides", {}).items():
                guide = EventGuide.from_dict(v)
                store._event_guides[cls._event_key(guide.event_id, guide.character)] = guide
```

In `stats`:
```python
            "event_guides": self.event_guide_count,
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_event_guide_store.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_store.py tests/test_event_guide_store.py
git commit -m "feat: EventGuide support in GuideStore"
```

---

### Task 10: Agent Loop Integration — Event Tracking Lifecycle and Outcome Diffs

**Files:**
- Modify: `src/agent/loop.py`
- Test: `tests/test_event_loop_integration.py` (create)

This task wires everything together in the agent loop: event tracking before/after decisions, extraction in post-run, and concrete outcome diff computation. Event memories are not useful if `cards_gained` / `cards_lost` / `relics_gained` / `potions_gained` remain placeholder empty lists.

- [ ] **Step 1: Write failing tests for event outcome diff helpers**

Create `tests/test_event_loop_integration.py`:

```python
"""Tests for event loop integration and state diff capture."""
from types import SimpleNamespace

from src.agent.loop import _compute_event_state_diff


def _card(name: str, upgraded: bool = False):
    return SimpleNamespace(name=name, upgraded=upgraded)


def _relic(name: str):
    return SimpleNamespace(name=name)


def _potion(name: str | None, occupied: bool = True):
    return SimpleNamespace(name=name, occupied=occupied)


def _gs(*, hp=57, gold=110, deck=None, relics=None, potions=None):
    return SimpleNamespace(
        player_hp=hp,
        gold=gold,
        deck=list(deck or []),
        relics=list(relics or []),
        potions=list(potions or []),
    )


def test_compute_event_state_diff_detects_transform_relic_and_potion_gain():
    prev_gs = _gs(
        deck=[_card("Neutralize", upgraded=True), _card("Strike")],
        relics=[],
        potions=[_potion("Fire Potion"), _potion(None, occupied=False), _potion(None, occupied=False)],
    )
    next_gs = _gs(
        deck=[_card("Suppress", upgraded=True), _card("Strike")],
        relics=[_relic("Happy Flower")],
        potions=[_potion("Fire Potion"), _potion("Block Potion"), _potion(None, occupied=False)],
    )

    diff = _compute_event_state_diff(prev_gs, next_gs)

    assert diff["cards_gained"] == ["Suppress+"]
    assert diff["cards_lost"] == ["Neutralize+"]
    assert diff["relics_gained"] == ["Happy Flower"]
    assert diff["potions_gained"] == ["Block Potion"]


def test_compute_event_state_diff_handles_missing_next_state():
    prev_gs = _gs(deck=[_card("Strike")], relics=[_relic("Anchor")], potions=[_potion("Fire Potion")])
    diff = _compute_event_state_diff(prev_gs, None)
    assert diff == {
        "cards_gained": [],
        "cards_lost": [],
        "relics_gained": [],
        "potions_gained": [],
    }
```

- [ ] **Step 2: Add event tracking before event decisions without double-starting the same event**

In `loop.py`, find where `gs.state_type == "event"` is handled for prompt construction (around line ~4257). Before the LLM call, add guarded event tracking initialization:

```python
        # Track event encounter for memory (idempotent across retries on the same screen)
        if gs.state_type == "event" and gs.event and self._memory:
            stm = self._hcm_short_term()
            if stm is not None:
                current_event = getattr(stm, "current_event", None)
                if current_event is None or (
                    current_event.event_id != gs.event.event_id
                    or current_event.floor != gs.floor
                ):
                    deck_names = [
                        f"{c.name}{'+' if getattr(c, 'upgraded', False) else ''}"
                        for c in gs.deck
                    ]
                    stm.start_event(
                        event_id=gs.event.event_id,
                        event_title=gs.event.title,
                        floor=gs.floor,
                        act=gs.act,
                        hp=gs.player_hp,
                        gold=gs.gold,
                        deck=deck_names,
                    )
```

- [ ] **Step 3: Implement concrete event outcome diff helpers in `loop.py`**

Near the other top-level helper functions, add dedicated snapshot/diff helpers:

```python
from collections import Counter


def _card_display_name(card) -> str:
    name = getattr(card, "name", "") or ""
    return f"{name}+" if getattr(card, "upgraded", False) and not name.endswith("+") else name


def _occupied_potion_names(gs: GameState | None) -> list[str]:
    if gs is None:
        return []
    return [
        p.name for p in gs.potions
        if getattr(p, "occupied", False) and getattr(p, "name", None)
    ]


def _multiset_added_removed(before: list[str], after: list[str]) -> tuple[list[str], list[str]]:
    before_counter = Counter(before)
    after_counter = Counter(after)
    gained = list((after_counter - before_counter).elements())
    lost = list((before_counter - after_counter).elements())
    return sorted(gained), sorted(lost)


def _compute_event_state_diff(prev_gs: GameState, gs: GameState | None) -> dict[str, list[str]]:
    if gs is None:
        return {
            "cards_gained": [],
            "cards_lost": [],
            "relics_gained": [],
            "potions_gained": [],
        }

    prev_deck = [_card_display_name(c) for c in prev_gs.deck]
    next_deck = [_card_display_name(c) for c in gs.deck]
    cards_gained, cards_lost = _multiset_added_removed(prev_deck, next_deck)

    prev_relics = [r.name for r in prev_gs.relics if getattr(r, "name", "")]
    next_relics = [r.name for r in gs.relics if getattr(r, "name", "")]
    relics_gained, _ = _multiset_added_removed(prev_relics, next_relics)

    prev_potions = _occupied_potion_names(prev_gs)
    next_potions = _occupied_potion_names(gs)
    potions_gained, _ = _multiset_added_removed(prev_potions, next_potions)

    return {
        "cards_gained": cards_gained,
        "cards_lost": cards_lost,
        "relics_gained": relics_gained,
        "potions_gained": potions_gained,
    }
```

Use `Counter` rather than `set` so duplicate cards/potions are handled correctly.

- [ ] **Step 4: Wire the real diffs into event finalization**

Replace the placeholder lists in the post-action event branch with the helper output:

```python
        # Finalize event tracking with concrete outcome diff
        if (
            prev_state_type == "event"
            and self._memory
            and prev_gs is not None
            and prev_gs.event is not None
        ):
            stm = self._hcm_short_term()
            if stm is not None:
                new_hp = gs.player_hp if gs else (prev_gs.player_hp or 0)
                new_gold = gs.gold if gs else (prev_gs.gold or 0)
                all_opts = [o.title for o in prev_gs.event.options]
                diff = _compute_event_state_diff(prev_gs, gs)
                stm.end_event(
                    chosen_index=last_chosen_index,
                    option_text=last_chosen_text,
                    hp_after=new_hp,
                    gold_after=new_gold,
                    all_options=all_opts,
                    cards_gained=diff["cards_gained"],
                    cards_lost=diff["cards_lost"],
                    relics_gained=diff["relics_gained"],
                    potions_gained=diff["potions_gained"],
                )
```

**NOTE:** `last_chosen_index` and `last_chosen_text` still come from the LLM decision parser output; this task removes the outcome-data TODO, it does not change action parsing.

- [ ] **Step 5: Add event extraction to `_post_run_hcm_extraction()`**

In `_post_run_hcm_extraction()` (line ~3252), after the combat/route/card_build extraction block, add:

```python
            # Event memories
            from src.memory.event_extractor import extract_event_memories
            event_mems = extract_event_memories(stm, run_id, character)
            if event_mems and self._memory.event_store:
                self._memory.event_store.add_batch(event_mems)
```

Update the summary log:

```python
            logger.info(
                "HCM extraction: %d combat, %d route, %d event, deck=%s, card_mem=%d",
                len(combat_eps), len(route_mems), len(event_mems),
                "yes" if final_deck else "no",
                card_mem_updated,
            )
```

- [ ] **Step 6: Run targeted tests**

```bash
python -m pytest tests/test_short_term_event.py tests/test_event_loop_integration.py -xvs
```

Expected: All PASS

- [ ] **Step 7: Commit**

```bash
git add src/agent/loop.py tests/test_event_loop_integration.py
git commit -m "feat: capture concrete event outcome diffs in agent loop"
```

---

### Task 11: Post-run Boss Impact Analysis

**Files:**
- Create: `src/memory/event_analysis.py`
- Modify: `src/agent/loop.py`
- Test: `tests/test_event_boss_impact.py` (create)

This task fills the `boss_impact_score` / `boss_impact_analysis` / `outcome_quality` fields that retrieval, EventGuide consolidation, and skill discovery actually read. Without it, all event memories stay at the default neutral values.

- [ ] **Step 1: Write failing tests for boss-impact prompt/parse flow**

Create `tests/test_event_boss_impact.py`:

```python
"""Tests for post-run event boss impact analysis."""
from src.memory.event_analysis import (
    build_event_boss_impact_prompt,
    parse_event_boss_impact_response,
)
from src.memory.models_v2 import EventMemory


def test_build_event_boss_impact_prompt_mentions_event_outcomes_and_bosses():
    mem = EventMemory(
        memory_id="evt_1",
        run_id="run_1",
        floor=18,
        act=2,
        event_id="OROBAS",
        event_title="Orobas",
        character="silent",
        chosen_option_index=1,
        chosen_option_text="Alchemical Coffer",
        potions_gained=("Fire Potion", "Block Potion"),
    )
    prompt = build_event_boss_impact_prompt(
        [mem],
        combat_episodes=[],
        run_result={"victory": False, "final_floor": 34, "boss_encounters": ["Act 2 Boss: took 28 HP"]},
    )
    assert "Orobas" in prompt
    assert "Alchemical Coffer" in prompt
    assert "Fire Potion" in prompt
    assert "Act 2 Boss" in prompt


def test_parse_event_boss_impact_response():
    raw = """
    [
      {
        "memory_id": "evt_1",
        "score": 0.6,
        "analysis": "Potions prevented major HP loss in the boss fight.",
        "quality": "good"
      }
    ]
    """
    parsed = parse_event_boss_impact_response(raw)
    assert len(parsed) == 1
    assert parsed[0]["memory_id"] == "evt_1"
    assert parsed[0]["score"] == 0.6
    assert parsed[0]["quality"] == "good"
```

- [ ] **Step 2: Create `src/memory/event_analysis.py`**

Implement:

```python
def build_event_boss_impact_prompt(
    event_memories: list[EventMemory],
    combat_episodes: list[CombatEpisode],
    run_result: dict[str, object],
) -> str:
    ...


def parse_event_boss_impact_response(raw_text: str) -> list[dict[str, object]]:
    ...


async def analyze_event_boss_impact(
    event_memories: list[EventMemory],
    combat_episodes: list[CombatEpisode],
    run_result: dict[str, object],
) -> list[EventMemory]:
    """Call analysis-tier LLM and return updated EventMemory instances."""
```

Implementation requirements:
- Include boss combats only (`combat_type == "boss"`) in the prompt summary.
- Mention concrete event outcomes: chosen option, HP/gold delta, cards/relics/potions gained/lost.
- Parse a strict JSON array with `memory_id`, `score`, `analysis`, `quality`.
- Clamp `score` into `[-1.0, 1.0]`; normalize `quality` to `good|neutral|bad`.
- If there are no event memories or no boss encounters, return the original memories unchanged.

- [ ] **Step 3: Integrate async boss-impact analysis into the post-run pipeline**

In `src/agent/loop.py`:

1. Add a pending-analysis slot in `__init__`:

```python
        self._pending_event_analysis: tuple[list, list, dict[str, object]] | None = None
```

2. In `_post_run_hcm_extraction()`, after `event_mems` are created, stage them for async analysis:

```python
            boss_eps = [ep for ep in combat_eps if ep.combat_type == "boss"]
            run_result = {
                "victory": self._run_state.victory,
                "final_floor": self._run_state.final_floor,
                "boss_encounters": [
                    f"{ep.enemy_key}: HP {ep.hp_before}->{ep.hp_after}, won={ep.won}"
                    for ep in boss_eps
                ],
            }
            self._pending_event_analysis = (event_mems, boss_eps, run_result)
```

3. In `_post_run_memory_update()`, run event boss-impact analysis after sync extraction and before guide consolidation / skill discovery:

```python
            if self._pending_event_analysis and self._use_llm:
                await self._analyze_event_boss_impact_async()
```

4. Add a new async helper mirroring `_analyze_build_async()`:

```python
    async def _analyze_event_boss_impact_async(self) -> None:
        if not self._pending_event_analysis or not self._memory or not self._memory.event_store:
            return
        event_mems, boss_eps, run_result = self._pending_event_analysis
        self._pending_event_analysis = None

        from src.memory.event_analysis import analyze_event_boss_impact

        updated = await analyze_event_boss_impact(event_mems, boss_eps, run_result)
        for mem in updated:
            self._memory.event_store.update_boss_impact(
                mem.memory_id,
                mem.boss_impact_score,
                mem.boss_impact_analysis,
                mem.outcome_quality,
            )
```

- [ ] **Step 4: Run targeted tests**

```bash
python -m pytest tests/test_event_boss_impact.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/event_analysis.py src/agent/loop.py tests/test_event_boss_impact.py
git commit -m "feat: analyze event boss impact post-run"
```

---

### Task 12: EventGuide Consolidation in `guide_consolidator.py`

**Files:**
- Modify: `src/memory/guide_consolidator.py`
- Test: `tests/test_event_guide_consolidator.py` (create)

Task 9 only adds EventGuide storage. This task adds the missing producer so repeated encounters with the same event actually become reusable event guidance.

- [ ] **Step 1: Write failing test for event guide consolidation**

Create `tests/test_event_guide_consolidator.py`:

```python
"""Tests for EventGuide consolidation."""
from types import SimpleNamespace

from src.memory.guide_consolidator import parse_event_guide_response


def test_parse_event_guide_response():
    raw = """
    {
      "guide_text": "- Prefer Alchemical Coffer when potion slots are low.",
      "confidence": 0.7
    }
    """
    guide = parse_event_guide_response(
        raw,
        event_id="OROBAS",
        character="silent",
        episode_count=4,
        existing_guide=None,
    )
    assert guide is not None
    assert guide.event_id == "OROBAS"
    assert guide.confidence == 0.7
    assert "Alchemical Coffer" in guide.guide_text
```

- [ ] **Step 2: Add event guide prompt/parse helpers**

In `src/memory/guide_consolidator.py`:

- Import `EventGuide` and `EventMemory`.
- Add `EVENT_ANALYST_PROMPT`.
- Add `build_event_guide_prompt(event_id, character, memories, existing_guide=None) -> str`.
- Add `parse_event_guide_response(raw, event_id, character, episode_count, existing_guide=None) -> EventGuide | None`.

Prompt content should include, for each recent memory:
- floor / act
- chosen option
- HP/gold delta
- cards/relics/potions gained/lost
- boss impact line when available

- [ ] **Step 3: Extend `consolidate_guides()` with an event branch**

In `consolidate_guides()`:

1. Expand stats:

```python
    stats = {"combat": 0, "route": 0, "deck": 0, "event": 0}
```

2. Group `memory_manager.event_store.get_all()` by `(event_id.upper(), normalize_character(character))`.
3. Require at least `config.CONSOLIDATION_MIN_EPISODES`.
4. Skip if existing event guide already covers at least as many memories.
5. Call the LLM with `call_type="guide_event"`.
6. Save via `guide_store.set_event_guide(guide)` and increment `stats["event"]`.

Pseudo-structure:

```python
    event_store = getattr(memory_manager, "event_store", None)
    if event_store:
        groups_e: dict[tuple[str, str], list[EventMemory]] = {}
        ...
        existing = guide_store.get_event_guide(event_id, character)
        prompt = build_event_guide_prompt(event_id, character, memories, existing)
        raw, _latency, _tokens = await llm_call_raw(
            EVENT_ANALYST_PROMPT,
            prompt,
            think=True,
            call_type="guide_event",
        )
        guide = parse_event_guide_response(...)
```

- [ ] **Step 4: Run targeted tests**

```bash
python -m pytest tests/test_event_guide_store.py tests/test_event_guide_consolidator.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_event_guide_consolidator.py
git commit -m "feat: consolidate EventGuides from repeated event memories"
```

---

### Task 13: Skill Discovery Enhancement — Include Event Decisions

**Files:**
- Modify: `src/skills/discovery.py`
- Modify: `src/agent/loop.py`
- Test: `tests/test_event_skill_discovery.py` (create)

The architecture and spec both say event decisions should participate in post-run skill discovery. This task adds the missing discovery context so event-specific skills can actually be mined.

- [ ] **Step 1: Write failing test for discovery prompt event context**

Create `tests/test_event_skill_discovery.py`:

```python
"""Tests for event-aware skill discovery."""
from types import SimpleNamespace

from src.skills.discovery import build_discovery_prompt
from src.memory.models_v2 import EventMemory


def test_build_discovery_prompt_includes_event_memories():
    run_state = SimpleNamespace(
        victory=False,
        final_floor=34,
        fitness=lambda: 123.0,
        combats_won=8,
        combats_total=10,
        character="silent",
        run_id="run_1",
    )
    mem = EventMemory(
        memory_id="evt_1",
        run_id="run_1",
        floor=18,
        act=2,
        event_id="OROBAS",
        event_title="Orobas",
        character="silent",
        chosen_option_index=1,
        chosen_option_text="Alchemical Coffer",
        potions_gained=("Fire Potion",),
        boss_impact_score=0.6,
        boss_impact_analysis="Potion gain reduced boss HP loss.",
    )

    prompt = build_discovery_prompt(
        run_state,
        existing_skills=[],
        combat_episodes=[],
        event_memories=[mem],
    )

    assert "## Event Decisions" in prompt
    assert "Orobas" in prompt
    assert "Boss impact: +0.6" in prompt
```

- [ ] **Step 2: Extend `build_discovery_prompt()` and `discover_skills()`**

In `src/skills/discovery.py`:

1. Add an `event_memories` parameter:

```python
def build_discovery_prompt(
    run_state: RunState,
    existing_skills: list[Skill] | None = None,
    *,
    combat_episodes: list[CombatEpisode] | None = None,
    event_memories: list[EventMemory] | None = None,
    ...
) -> str:
```

2. Add a new formatted section before existing skills:

```python
def _format_event_decisions(event_memories: list[EventMemory] | None) -> str:
    if not event_memories:
        return "(no event decisions recorded)"
    lines = []
    for em in sorted(event_memories, key=lambda m: (m.floor, m.timestamp)):
        impact = (
            f" Boss impact: {em.boss_impact_score:+.1f} ({em.boss_impact_analysis})"
            if em.boss_impact_analysis
            else ""
        )
        lines.append(
            f"F{em.floor} [{em.event_id}] chose '{em.chosen_option_text}'. "
            f"HP {em.hp_before}->{em.hp_after}, Gold {em.gold_before}->{em.gold_after}, "
            f"+cards={list(em.cards_gained)}, -cards={list(em.cards_lost)}, "
            f"+relics={list(em.relics_gained)}, +potions={list(em.potions_gained)}.{impact}"
        )
    return \"\\n\".join(lines)
```

3. In the prompt template, insert:

```python
## Event Decisions
{event_decisions}
```

4. Extend `discover_skills()` to accept `event_store=None`, pull current-run memories via `event_store.get_all()`, and pass them into `build_discovery_prompt()`.

- [ ] **Step 3: Update loop callers to pass `event_store`**

In `src/agent/loop.py`, update both sync and batch discovery callers:

```python
                event_st = self._memory.event_store if self._memory else None
                new_skills, _evidence = await discover_skills(
                    self._run_state,
                    existing_skills=existing,
                    combat_store=combat_st,
                    event_store=event_st,
                    allowed_categories=_NONCOMBAT_DISCOVERY_CATEGORIES,
                )
```

And in `_submit_post_run_batch()`, when calling `build_discovery_prompt(...)`, pass the current-run event memories gathered from `event_store`.

- [ ] **Step 4: Run targeted tests**

```bash
python -m pytest tests/test_event_skill_discovery.py -xvs
```

Expected: All PASS

- [ ] **Step 5: Commit**

```bash
git add src/skills/discovery.py src/agent/loop.py tests/test_event_skill_discovery.py
git commit -m "feat: include event decisions in post-run skill discovery"
```

---

### Task 14: Run Full Test Suite and Fix Regressions

**Files:** Various (test fixes)

- [ ] **Step 1: Run full test suite**

```bash
python -m pytest tests/ -x --tb=short 2>&1 | head -80
```

- [ ] **Step 2: Fix any regressions**

The most likely regressions:
- Tests that mock `_classify_decision_type` expecting `"rest_event"` for events
- Tests that check `WorkingContext` fields without `event_memory_hints`
- Tests that check `GuideStore.stats()` key count
- Tests that call `query_for_decision` without the new `event_store` parameter

Fix each regression by updating assertions to match the new behavior.

- [ ] **Step 3: Run tests again to confirm green**

```bash
python -m pytest tests/ -x --tb=short
```

Expected: All PASS

- [ ] **Step 4: Commit fixes**

```bash
git add -A
git commit -m "fix: update tests for event memory integration"
```

---

### Task 15: Final Integration Verification

- [ ] **Step 1: Verify EventMemoryStore loads in MemoryManager**

```bash
python -c "
from src.memory.memory_manager import MemoryManager
mm = MemoryManager()
print('Event store count:', mm.event_store.count)
print('Stats:', mm.stats())
"
```

Expected: `Event store count: 0` and stats include `v2_event_memories: 0`.

- [ ] **Step 2: Verify event prompt renders extended fields**

```bash
python -c "
from unittest.mock import MagicMock
from src.brain.prompts.event import build_event_prompt

gs = MagicMock()
gs.player_hp = 57; gs.player_max_hp = 57; gs.hp_ratio = 1.0
gs.gold = 110; gs.act = 2; gs.floor = 18
ev = MagicMock()
ev.event_id = 'OROBAS'; ev.title = 'Orobas'
ev.description = 'Ancient event'
opt = MagicMock()
opt.index = 2; opt.title = 'Archaic Tooth'
opt.description = 'Transform Neutralize+ into Suppress+.'
opt.is_locked = False; opt.is_proceed = False; opt.will_kill_player = False
opt.cards_offered = [{'name': 'Suppress+', 'cost': 1, 'type': 'Skill', 'rules_text': 'Apply 3 Weak. Draw 1 card.', 'is_upgraded': True}]
opt.relics_offered = []; opt.potions_offered = []
opt.hp_cost = None; opt.gold_cost = None
opt.effect_description = ''; opt.curses_risk = []
ev.options = [opt]
gs.event = ev
gs.run = None
print(build_event_prompt(gs))
"
```

Expected: Output includes `Card: Suppress+ (cost=1, Skill): Apply 3 Weak. Draw 1 card.`

- [ ] **Step 3: Verify discovery prompt includes event decisions and boss impact**

```bash
python -c "
from types import SimpleNamespace
from src.memory.models_v2 import EventMemory
from src.skills.discovery import build_discovery_prompt

run_state = SimpleNamespace(
    victory=False,
    final_floor=34,
    fitness=lambda: 123.0,
    combats_won=8,
    combats_total=10,
    character='silent',
    run_id='run_demo',
)
event_mem = EventMemory(
    memory_id='evt_1',
    run_id='run_demo',
    floor=18,
    act=2,
    event_id='OROBAS',
    event_title='Orobas',
    character='silent',
    chosen_option_index=1,
    chosen_option_text='Alchemical Coffer',
    potions_gained=('Fire Potion',),
    boss_impact_score=0.6,
    boss_impact_analysis='Potion gain reduced boss HP loss.',
)
print(build_discovery_prompt(run_state, existing_skills=[], combat_episodes=[], event_memories=[event_mem]))
"
```

Expected: Output includes `## Event Decisions`, `Orobas`, and `Boss impact: +0.6`.

- [ ] **Step 4: Run full test suite one more time**

```bash
python -m pytest tests/ --tb=short
```

Expected: All PASS

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "feat: event decision enhancement — complete integration"
```
