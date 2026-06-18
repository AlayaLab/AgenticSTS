# Act-Boss-Aware Reward/Shop — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject the current act's scheduled-boss CombatGuide into `card_reward` and shop (card sale) prompts so the agent can consider boss matchup when deckbuilding, without over-optimizing for one fight.

**Architecture:** C# mod exposes boss encounter IDs from `runState.Act.BossEncounter` / `SecondBossEncounter`. Python resolves encounter id → enemy_key using the exact convention in `memory.combat_extractor._build_enemy_key` (single → monster name; multi → `multi:`-joined sorted names). Prompt helper injects the guide (if present) into reward / shop prompts.

**Tech Stack:** Python 3.11 (Pydantic, pytest), C# 9 / .NET 9 (Godot bindings).

**Spec:** [docs/superpowers/specs/2026-04-18-act-boss-aware-reward-shop-design.md](../specs/2026-04-18-act-boss-aware-reward-shop-design.md)

---

## File Structure

| File | Role |
|---|---|
| `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs` (modify) | Expose `boss_encounter_id` / `second_boss_encounter_id` on `MapPayload` |
| `src/mcp_client/upstream_models.py` (modify) | Add nullable string fields to `RawMapPayload` |
| `src/knowledge/encounter_lookup.py` (modify) | Add `resolve_encounter_enemy_key` |
| `src/state/upstream_game_state.py` (modify) | Add `upcoming_boss_enemy_keys` property |
| `src/brain/prompts/_boss_guide_fmt.py` (new) | Format-level helper; renders `## Upcoming Act Boss` subsection |
| `src/brain/prompts/reward.py` (modify) | Inject subsection inside `build_card_reward_prompt` |
| `src/brain/prompts/shop.py` (modify) | Inject subsection inside `build_shop_plan_prompt` when cards are for sale |
| `tests/knowledge/test_encounter_lookup_enemy_key.py` (new) | Unit: encounter → enemy_key resolution |
| `tests/state/test_upcoming_boss_keys.py` (new) | Unit: state view property |
| `tests/brain/prompts/test_boss_guide_fmt.py` (new) | Unit: helper format output |
| `tests/brain/prompts/test_reward_boss_guide.py` (new) | Unit: reward prompt injection |
| `tests/brain/prompts/test_shop_boss_guide.py` (new) | Unit: shop prompt injection |

---

### Task 1: C# Mod — expose boss encounter IDs

**Files:**
- Modify: `STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs` (MapPayload record + `BuildMapPayload`)

- [ ] **Step 1.1: Locate the `MapPayload` record definition**

Run: `grep -n "class MapPayload\|record MapPayload\|MapPayload {" STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs`

Record (or record-like class) defines the JSON-serialized map fields. Note which fields already exist (e.g. `boss_node`, `second_boss_node` for coords).

- [ ] **Step 1.2: Add two nullable string fields to `MapPayload`**

Add within the `MapPayload` definition (adjacent to `boss_node` / `second_boss_node`):

```csharp
public string? boss_encounter_id { get; init; }
public string? second_boss_encounter_id { get; init; }
```

(If `MapPayload` is a record with positional params, add them to the parameter list in the same spot; if it's a class with init properties, use the above.)

- [ ] **Step 1.3: Populate the new fields in `BuildMapPayload`**

Locate (around line 4079 from the earlier survey):
```csharp
return new MapPayload
{
    ...
    boss_node = BuildMapCoordPayload(runState.Map.BossMapPoint.coord),
    second_boss_node = BuildMapCoordPayload(runState.Map.SecondBossMapPoint?.coord),
    ...
};
```

Add two lines in the same initializer:
```csharp
boss_encounter_id        = runState.Act?.BossEncounter?.Id.ToString(),
second_boss_encounter_id = runState.Act?.SecondBossEncounter?.Id.ToString(),
```

`Id` on `EncounterModel` is typically an enum or a string-convertible identifier; `.ToString()` is safe for both. `runState.Act` / `BossEncounter` may be null on the character-select screen or first tick, so null-conditional propagation ensures no NRE.

- [ ] **Step 1.4: Build the mod**

Run: `cd STS2-Agent-Fork/STS2AIAgent && dotnet build -c Release`
Expected: `Build succeeded. 0 Warning(s). 0 Error(s).`

If compiler complains that `MapPayload` is a record with positional parameters, adjust by inserting the new params into the positional list and updating call sites accordingly.

- [ ] **Step 1.5: Commit**

```bash
git add STS2-Agent-Fork/STS2AIAgent/Game/GameStateService.cs
git commit -m "feat(mod): expose boss_encounter_id / second_boss_encounter_id on MapPayload"
```

---

### Task 2: Python — extend `RawMapPayload`

**Files:**
- Modify: `src/mcp_client/upstream_models.py` (RawMapPayload class)

- [ ] **Step 2.1: Locate `RawMapPayload`**

Run: `grep -n "class RawMapPayload" src/mcp_client/upstream_models.py`
Expected line: around 299 (`class RawMapPayload(UpstreamModel):`).

- [ ] **Step 2.2: Add nullable fields**

Inside `RawMapPayload`, add (after `second_boss_node`):

```python
    boss_encounter_id: str | None = None
    second_boss_encounter_id: str | None = None
```

Default `None` keeps compatibility with older mod versions.

- [ ] **Step 2.3: Quick import-smoke**

Run: `python -c "from src.mcp_client.upstream_models import RawMapPayload; p = RawMapPayload(); assert p.boss_encounter_id is None"`
Expected: no output, exit 0.

- [ ] **Step 2.4: Commit**

```bash
git add src/mcp_client/upstream_models.py
git commit -m "feat(state): add boss_encounter_id fields to RawMapPayload"
```

---

### Task 3: `resolve_encounter_enemy_key` in `encounter_lookup.py`

**Files:**
- Modify: `src/knowledge/encounter_lookup.py`
- Test: `tests/knowledge/test_encounter_lookup_enemy_key.py` (new)

- [ ] **Step 3.1: Write failing test — single-monster encounter**

Create `tests/knowledge/test_encounter_lookup_enemy_key.py`:

```python
from pathlib import Path

from src.knowledge.encounter_lookup import EncounterLookup


def _lookup() -> EncounterLookup:
    return EncounterLookup(Path("data/knowledge"))


def test_resolve_enemy_key_single_monster():
    lk = _lookup()
    # CEREMONIAL_BEAST_BOSS ships with monsters=[{"name": "Ceremonial Beast"}]
    assert lk.resolve_encounter_enemy_key("CEREMONIAL_BEAST_BOSS") == "Ceremonial Beast"


def test_resolve_enemy_key_multi_monster_sorted():
    lk = _lookup()
    # DOORMAKER_BOSS ships with monsters=[{"name": "Door"}, {"name": "Doormaker"}]
    assert lk.resolve_encounter_enemy_key("DOORMAKER_BOSS") == "multi:Door+Doormaker"


def test_resolve_enemy_key_multi_monster_with_duplicates_sorted():
    lk = _lookup()
    # KAISER_CRAB_BOSS ships with monsters=[{"name": "Crusher"}, {"name": "Rocket"}]
    assert lk.resolve_encounter_enemy_key("KAISER_CRAB_BOSS") == "multi:Crusher+Rocket"


def test_resolve_enemy_key_unknown_returns_none():
    lk = _lookup()
    assert lk.resolve_encounter_enemy_key("NOT_A_REAL_ENCOUNTER") is None


def test_resolve_enemy_key_empty_string_returns_none():
    lk = _lookup()
    assert lk.resolve_encounter_enemy_key("") is None
```

- [ ] **Step 3.2: Run tests — expect fail**

Run: `python -m pytest tests/knowledge/test_encounter_lookup_enemy_key.py -v`
Expected: `AttributeError: 'EncounterLookup' object has no attribute 'resolve_encounter_enemy_key'`.

- [ ] **Step 3.3: Implement `resolve_encounter_enemy_key`**

Append to `src/knowledge/encounter_lookup.py` (inside `EncounterLookup`):

```python
    def resolve_encounter_enemy_key(self, encounter_id: str) -> str | None:
        """Build the enemy_key used by memory.combat_extractor._build_enemy_key
        for the given encounter, so CombatGuide lookups match the stored key.

        Rules (identical to combat_extractor):
        - exactly one monster: normalize_enemy_key(monster_name)
        - multiple monsters:   normalize_enemy_key("multi:" + "+".join(sorted(names)))
        - unknown or empty:    None
        """
        from src.memory.enemy_keys import normalize_enemy_key

        if not encounter_id:
            return None
        enc = self._by_id.get(encounter_id)
        if enc is None or not enc.monsters:
            return None
        names = list(enc.monsters)
        if len(names) == 1:
            return normalize_enemy_key(names[0])
        return normalize_enemy_key("multi:" + "+".join(sorted(names)))
```

The import is inside the method to avoid circular imports with `src.memory` packages at module load time.

- [ ] **Step 3.4: Run tests — expect pass**

Run: `python -m pytest tests/knowledge/test_encounter_lookup_enemy_key.py -v`
Expected: 5 passed.

- [ ] **Step 3.5: Commit**

```bash
git add src/knowledge/encounter_lookup.py tests/knowledge/test_encounter_lookup_enemy_key.py
git commit -m "feat(knowledge): add resolve_encounter_enemy_key to EncounterLookup"
```

---

### Task 4: `upcoming_boss_enemy_keys` on `UpstreamStateView`

**Files:**
- Modify: `src/state/upstream_game_state.py`
- Test: `tests/state/test_upcoming_boss_keys.py` (new)

- [ ] **Step 4.1: Write failing test**

Create `tests/state/test_upcoming_boss_keys.py`:

```python
from src.mcp_client.upstream_models import RawMapPayload, UpstreamGameState
from src.state.upstream_game_state import UpstreamStateView


def _view(boss_id: str | None, second_boss_id: str | None = None) -> UpstreamStateView:
    raw = UpstreamGameState()
    raw.map = RawMapPayload(
        boss_encounter_id=boss_id,
        second_boss_encounter_id=second_boss_id,
    )
    return UpstreamStateView(raw=raw)


def test_upcoming_boss_keys_none_when_missing():
    assert _view(None).upcoming_boss_enemy_keys == []


def test_upcoming_boss_keys_single():
    assert _view("CEREMONIAL_BEAST_BOSS").upcoming_boss_enemy_keys == ["Ceremonial Beast"]


def test_upcoming_boss_keys_with_second_boss():
    keys = _view("CEREMONIAL_BEAST_BOSS", "DOORMAKER_BOSS").upcoming_boss_enemy_keys
    assert keys == ["Ceremonial Beast", "multi:Door+Doormaker"]


def test_upcoming_boss_keys_unknown_encounter_filtered():
    # Unknown encounter id → resolver returns None → filtered out
    assert _view("NOT_REAL").upcoming_boss_enemy_keys == []
```

- [ ] **Step 4.2: Run tests — expect fail**

Run: `python -m pytest tests/state/test_upcoming_boss_keys.py -v`
Expected: `AttributeError` on missing property.

- [ ] **Step 4.3: Add the property**

Open `src/state/upstream_game_state.py`. Near other `@property` definitions (e.g. `boss_stage`), add:

```python
    @property
    def upcoming_boss_enemy_keys(self) -> list[str]:
        """Enemy_keys for current act's boss node(s), resolved via encounter_lookup.
        Returns 0, 1, or 2 keys. Empty list if mod data missing / encounter unknown."""
        map_payload = self.raw.map
        if map_payload is None:
            return []
        ids = [map_payload.boss_encounter_id, map_payload.second_boss_encounter_id]
        ids = [i for i in ids if i]
        if not ids:
            return []
        from src.knowledge.knowledge import GameKnowledge
        try:
            kb = GameKnowledge.get_instance()
        except Exception:
            return []
        resolved = [kb.encounters.resolve_encounter_enemy_key(i) for i in ids]
        return [k for k in resolved if k]
```

Import is inside the method to stay lazy and avoid circular imports at state-view module load time.

- [ ] **Step 4.4: Run tests — expect pass**

Run: `python -m pytest tests/state/test_upcoming_boss_keys.py -v`
Expected: 4 passed.

- [ ] **Step 4.5: Commit**

```bash
git add src/state/upstream_game_state.py tests/state/test_upcoming_boss_keys.py
git commit -m "feat(state): add upcoming_boss_enemy_keys property"
```

---

### Task 5: Prompt helper `_boss_guide_fmt.py`

**Files:**
- Create: `src/brain/prompts/_boss_guide_fmt.py`
- Test: `tests/brain/prompts/test_boss_guide_fmt.py` (new)

- [ ] **Step 5.1: Write failing tests**

Create `tests/brain/prompts/test_boss_guide_fmt.py`:

```python
from types import SimpleNamespace

from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guides: dict[tuple[str, str], CombatGuide]):
        self._guides = guides

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guides.get((enemy_key, character))


def _gs(boss_keys: list[str]) -> object:
    # Minimal stand-in for GameState — helper only needs upcoming_boss_enemy_keys + raw
    return SimpleNamespace(upcoming_boss_enemy_keys=boss_keys)


def test_empty_when_no_upcoming_boss():
    gs = _gs([])
    lines = format_upcoming_boss_guide(gs, "Silent", _FakeGuideStore({}))
    assert lines == []


def test_empty_when_guide_missing():
    gs = _gs(["Queen"])
    lines = format_upcoming_boss_guide(gs, "Silent", _FakeGuideStore({}))
    assert lines == []


def test_single_boss_renders_guide_text():
    guide = CombatGuide(
        enemy_key="Queen", character="Silent",
        guide_text="Tank the lvl-3 wave, then burst.",
        key_patterns=("Prioritize AOE round 1", "Watch for big slash turn 4"),
    )
    gs = _gs(["Queen"])
    store = _FakeGuideStore({("Queen", "Silent"): guide})
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Boss: Queen" in text
    assert "Tank the lvl-3 wave" in text
    assert "Prioritize AOE round 1" in text
    assert "Consider matchup when picking, but don't over-optimize" in text


def test_two_bosses_render_as_sequential_section():
    g1 = CombatGuide(enemy_key="Queen", character="Silent", guide_text="A")
    g2 = CombatGuide(enemy_key="multi:Door+Doormaker", character="Silent", guide_text="B")
    gs = _gs(["Queen", "multi:Door+Doormaker"])
    store = _FakeGuideStore({
        ("Queen", "Silent"): g1,
        ("multi:Door+Doormaker", "Silent"): g2,
    })
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Bosses (sequential)" in text
    assert "### Queen" in text
    assert "### multi:Door+Doormaker" in text
    assert "A" in text and "B" in text


def test_only_one_guide_present_falls_back_to_single_header():
    # First boss has guide, second does not → render as single-boss form (skip missing)
    g1 = CombatGuide(enemy_key="Queen", character="Silent", guide_text="A")
    gs = _gs(["Queen", "multi:Door+Doormaker"])
    store = _FakeGuideStore({("Queen", "Silent"): g1})
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Boss: Queen" in text
    assert "### Queen" not in text  # sub-header form not used for single guide
```

- [ ] **Step 5.2: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_boss_guide_fmt.py -v`
Expected: `ModuleNotFoundError: No module named 'src.brain.prompts._boss_guide_fmt'`.

- [ ] **Step 5.3: Implement helper**

Create `src/brain/prompts/_boss_guide_fmt.py`:

```python
"""Format upcoming-act-boss CombatGuide into card_reward / shop prompts."""

from __future__ import annotations

from typing import Protocol

from src.memory.models_v2 import CombatGuide


class _GuideStoreLike(Protocol):
    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None: ...


_FOOTER = (
    "Consider matchup when picking, but don't over-optimize deckbuild for one fight."
)


def _format_guide_body(guide: CombatGuide) -> list[str]:
    """Render the body lines of a single guide (no header)."""
    body: list[str] = []
    text = (guide.guide_text or "").strip()
    if text:
        body.append(text)
    patterns = [p for p in guide.key_patterns if p]
    if patterns:
        body.append("Key patterns:")
        body.extend(f"- {p}" for p in patterns)
    return body


def format_upcoming_boss_guide(
    gs,
    character: str,
    guide_store: _GuideStoreLike,
) -> list[str]:
    """Return prompt lines injecting CombatGuide(s) for the upcoming act boss(es).

    Returns [] when:
    - gs has no upcoming boss keys (mod missing fields, unknown encounter, etc.)
    - character is empty
    - guide_store has no match for any resolved key
    """
    if not character:
        return []
    keys: list[str] = list(getattr(gs, "upcoming_boss_enemy_keys", []) or [])
    if not keys:
        return []

    # Collect (key, guide) pairs where guide exists
    hits: list[tuple[str, CombatGuide]] = []
    for key in keys:
        guide = guide_store.get_combat_guide(key, character)
        if guide is not None:
            hits.append((key, guide))

    if not hits:
        return []

    lines: list[str] = [""]
    if len(hits) == 1:
        key, guide = hits[0]
        lines.append(f"## Upcoming Act Boss: {key}")
        lines.extend(_format_guide_body(guide))
        lines.append("")
        lines.append(_FOOTER)
    else:
        lines.append("## Upcoming Act Bosses (sequential):")
        for key, guide in hits:
            lines.append("")
            lines.append(f"### {key}")
            lines.extend(_format_guide_body(guide))
        lines.append("")
        lines.append(_FOOTER)
    return lines
```

- [ ] **Step 5.4: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_boss_guide_fmt.py -v`
Expected: 5 passed.

- [ ] **Step 5.5: Commit**

```bash
git add src/brain/prompts/_boss_guide_fmt.py tests/brain/prompts/test_boss_guide_fmt.py
git commit -m "feat(prompts): add _boss_guide_fmt helper for upcoming-boss injection"
```

---

### Task 6: Inject into `build_card_reward_prompt`

**Files:**
- Modify: `src/brain/prompts/reward.py`
- Test: `tests/brain/prompts/test_reward_boss_guide.py` (new)

- [ ] **Step 6.1: Inspect current reward.py header + signature**

Run: `grep -n "def build_card_reward_prompt\|import\|def " src/brain/prompts/reward.py | head -20`

Note existing signature: `build_card_reward_prompt(gs, deck=None, relics=None, card_memory_store=None, character="")`. We need to add an optional `guide_store` parameter AND thread it from the call site (agent loop).

- [ ] **Step 6.2: Find reward prompt call sites**

Run: `grep -rn "build_card_reward_prompt" src/`

Identify where the function is invoked (e.g. `src/agent/loop.py` somewhere near the V2 engine dispatch). Each call site will need the new `guide_store` kwarg.

- [ ] **Step 6.3: Write failing test**

Create `tests/brain/prompts/test_reward_boss_guide.py`:

```python
from types import SimpleNamespace

import pytest

from src.brain.prompts.reward import build_card_reward_prompt
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guide: CombatGuide | None):
        self._guide = guide

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guide


def _reward_gs(upcoming: list[str]) -> object:
    # Minimal stub — only fields the prompt builder touches in our code paths.
    # Any missing attributes fail loudly in tests to surface plan drift.
    card_opt = SimpleNamespace(
        index=0, stable_id="strike", card_id="strike",
        name="Strike", upgraded=False, card_type="Attack", rarity="Basic",
        costs_x=False, energy_cost=1, rules_text="Deal 6 damage.",
        resolved_rules_text="Deal 6 damage.", dynamic_values=[], alternatives=[],
    )
    reward = SimpleNamespace(
        pending_card_choice=True,
        card_options=[card_opt],
        alternatives=[],
    )
    return SimpleNamespace(
        reward=reward,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=4,
        upcoming_boss_enemy_keys=upcoming,
    )


def test_reward_prompt_no_guide_omits_section():
    gs = _reward_gs(["Queen"])
    store = _FakeGuideStore(None)
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text


def test_reward_prompt_injects_guide_when_present():
    guide = CombatGuide(
        enemy_key="Queen", character="Silent",
        guide_text="Heavy AOE works best round 1.",
        key_patterns=("Stack block turn 2",),
    )
    gs = _reward_gs(["Queen"])
    store = _FakeGuideStore(guide)
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "## Upcoming Act Boss: Queen" in text
    assert "Heavy AOE works best round 1." in text
    assert "Stack block turn 2" in text


def test_reward_prompt_omits_section_when_no_upcoming_keys():
    gs = _reward_gs([])
    store = _FakeGuideStore(
        CombatGuide(enemy_key="Queen", character="Silent", guide_text="X")
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text
```

- [ ] **Step 6.4: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_reward_boss_guide.py -v`
Expected: `TypeError: build_card_reward_prompt() got an unexpected keyword argument 'guide_store'`.

- [ ] **Step 6.5: Extend `build_card_reward_prompt` signature + inject**

Edit `src/brain/prompts/reward.py`. At the top, import helper:

```python
from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
```

Change the function signature to:

```python
def build_card_reward_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    card_memory_store: object | None = None,
    character: str = "",
    guide_store: object | None = None,
) -> str:
```

Immediately before the `lines.append("## Available Cards")` line (originally line 50), insert:

```python
    if guide_store is not None:
        lines.extend(format_upcoming_boss_guide(gs, character, guide_store))
```

- [ ] **Step 6.6: Thread `guide_store` at the call site**

Find the call in `src/agent/loop.py` (grep gave us the line). The agent loop holds a reference to the memory manager; pass `self._memory.guide_store` (or equivalent path — verify via `grep -n "guide_store" src/memory/memory_manager.py`). Update the call:

```python
prompt = build_card_reward_prompt(
    gs, deck=deck, relics=relics, card_memory_store=cms,
    character=char, guide_store=self._memory.guide_store if self._memory else None,
)
```

(Use whatever attribute path actually holds the `GuideStore` — verify before editing.)

- [ ] **Step 6.7: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_reward_boss_guide.py -v`
Expected: 3 passed.

- [ ] **Step 6.8: Broader regression**

Run: `python -m pytest tests/brain/prompts/ -v`
Expected: pre-existing tests still pass (kwarg is optional with default `None`).

- [ ] **Step 6.9: Commit**

```bash
git add src/brain/prompts/reward.py src/agent/loop.py tests/brain/prompts/test_reward_boss_guide.py
git commit -m "feat(reward): inject upcoming-boss guide into card_reward prompt"
```

---

### Task 7: Inject into `build_shop_plan_prompt` (cards-for-sale only)

**Files:**
- Modify: `src/brain/prompts/shop.py`
- Test: `tests/brain/prompts/test_shop_boss_guide.py` (new)

- [ ] **Step 7.1: Write failing test**

Create `tests/brain/prompts/test_shop_boss_guide.py`:

```python
from types import SimpleNamespace

from src.brain.prompts.shop import build_shop_plan_prompt
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guide: CombatGuide | None):
        self._guide = guide

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guide


def _shop_gs(cards: list, upcoming: list[str]) -> object:
    shop = SimpleNamespace(
        is_open=True, cards=cards, relics=[], potions=[],
    )
    return SimpleNamespace(
        shop=shop,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=7,
        upcoming_boss_enemy_keys=upcoming,
    )


def _fake_shop_card(name: str = "Strike"):
    return SimpleNamespace(
        index=0, name=name, card_type="Attack", rarity="Common",
        upgraded=False, costs_x=False, energy_cost=1, rules_text="Deal 6.",
        resolved_rules_text="Deal 6.", dynamic_values=[], price=50,
    )


def test_shop_prompt_injects_when_cards_and_guide():
    guide = CombatGuide(enemy_key="Queen", character="Silent", guide_text="Burst plan.")
    gs = _shop_gs([_fake_shop_card()], ["Queen"])
    store = _FakeGuideStore(guide)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "## Upcoming Act Boss: Queen" in text


def test_shop_prompt_skips_when_no_cards_for_sale():
    guide = CombatGuide(enemy_key="Queen", character="Silent", guide_text="Burst plan.")
    gs = _shop_gs([], ["Queen"])
    store = _FakeGuideStore(guide)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text


def test_shop_prompt_skips_when_no_guide():
    gs = _shop_gs([_fake_shop_card()], ["Queen"])
    store = _FakeGuideStore(None)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], guide_store=store, character="Silent")
    assert "Upcoming Act Boss" not in text
```

- [ ] **Step 7.2: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_shop_boss_guide.py -v`
Expected: `TypeError: build_shop_plan_prompt() got an unexpected keyword argument 'guide_store'`.

- [ ] **Step 7.3: Extend `build_shop_plan_prompt`**

Edit `src/brain/prompts/shop.py`:

At the top imports:
```python
from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
```

Extend signature:
```python
def build_shop_plan_prompt(
    gs: GameState,
    deck: list[RawDeckCardPayload] | None = None,
    relics: list[str] | None = None,
    card_memory_store: object | None = None,
    character: str = "",
    guide_store: object | None = None,
) -> str:
```

After the `format_deck_section` append and relic section (before the gold-budget analysis block starting around line 99), insert:

```python
    # Upcoming-boss guide: only inject when cards are actually for sale
    if guide_store is not None and shop.cards:
        lines.extend(format_upcoming_boss_guide(gs, character, guide_store))
```

- [ ] **Step 7.4: Thread `guide_store` at the shop call site**

Edit `src/agent/loop.py:4760` (the `build_shop_plan_prompt` call). Add `guide_store=self._memory.guide_store if self._memory else None`. Use the same attribute path confirmed in Task 6.6.

- [ ] **Step 7.5: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_shop_boss_guide.py -v`
Expected: 3 passed.

- [ ] **Step 7.6: Broader regression**

Run: `python -m pytest tests/brain/prompts/ tests/state/ tests/knowledge/ -v`
Expected: all passing.

- [ ] **Step 7.7: Commit**

```bash
git add src/brain/prompts/shop.py src/agent/loop.py tests/brain/prompts/test_shop_boss_guide.py
git commit -m "feat(shop): inject upcoming-boss guide when cards are for sale"
```

---

### Task 8: Live smoke test

**Files:** none modified; live run verification.

- [ ] **Step 8.1: Deploy the rebuilt mod DLL**

Copy `STS2-Agent-Fork/STS2AIAgent/bin/Release/net9.0/STS2AIAgent.dll` into the STS2 `mods/` directory. Launch STS2 and load a run to character-select. No errors in the game log should appear.

- [ ] **Step 8.2: Start an agent run**

Run: `python -m scripts.run_agent --steps 100 --runs 1 --character Silent --ascension 0`

- [ ] **Step 8.3: Verify act-boss exposure in state dump**

While the run is in act 1 between floors 1-2, inspect `logs/run_*.jsonl` for a state snapshot containing `boss_encounter_id`. Expected: a non-null string like `"QUEEN_BOSS"` or similar.

Command: `python -c "import json; [print(json.dumps(ln := json.loads(l), indent=2)) for l in open(sorted(__import__('glob').glob('logs/run_*.jsonl'))[-1]) if '\"boss_encounter_id\"' in l][:1]"`

- [ ] **Step 8.4: Verify prompt injection (first run: no guide yet)**

Search the log for a `card_reward` prompt. Confirm `## Upcoming Act Boss` is ABSENT (no guide exists yet for first-ever run). Good — helper degraded gracefully.

- [ ] **Step 8.5: Run to post-run guide consolidation**

Continue the run until a boss fight completes. Let post-run hooks run (every 5 runs guide is consolidated). To force consolidation this run:

Run: `STS2_FORCE_GUIDE_CONSOLIDATION=1 python -m scripts.run_agent --steps 500 --runs 1 --character Silent --ascension 0`

(If no such env knob exists, complete 5 runs normally — consolidation triggers automatically.)

- [ ] **Step 8.6: Start second run, verify injection appears**

Run: `python -m scripts.run_agent --steps 100 --runs 1 --character Silent --ascension 0`

In this run's log, find the first `card_reward` prompt after the act 1 boss is scheduled. Expected: `## Upcoming Act Boss: <name>` appears, followed by guide text.

- [ ] **Step 8.7: Acceptance review**

Read 2-3 injected prompts end-to-end. Verify:
- Subsection appears only on reward/shop (not combat/map/event prompts)
- No duplicate injection
- Shop relic-only pages skip the subsection (confirm by inspecting a relic-only shop visit)
- Footer qualifier "Consider matchup when picking, but don't over-optimize" is present

No automated test exists for "agent picks better cards with injection" — just qualitative confirmation for now; A/B evaluation is a separate experiment outside this plan.

- [ ] **Step 8.8: Commit note (optional)**

If any fixes are needed during smoke (e.g. mod DLL version bump, tiny bug discovered), make those changes + commits. Otherwise no commit required — smoke is observation-only.

---

## Self-Review Checklist (performed during plan authoring)

- Coverage: every spec section §6.1 through §6.6 maps to a task (1–7). §5 double-boss handled in Task 5. §9 tests distributed across Tasks 3/4/5/6/7. §10 rollout mirrored by Task 8.
- No TBDs, TODOs, or "implement later" instructions. Every code block contains the full code.
- Function signatures consistent: `resolve_encounter_enemy_key`, `upcoming_boss_enemy_keys`, `format_upcoming_boss_guide`, `build_card_reward_prompt(..., guide_store=...)`, `build_shop_plan_prompt(..., guide_store=...)` match across tasks and tests.
- One subtle type: helper's `gs` arg is duck-typed (`SimpleNamespace` in tests, `GameState` in prod). Explicit in helper signature `gs` with no type annotation to keep `Protocol` light — tests exercise both shapes.
