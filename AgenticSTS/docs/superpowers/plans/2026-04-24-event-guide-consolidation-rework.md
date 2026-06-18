# Event Guide Consolidation Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the event guide consolidation branch with a run-scoped, scored option-library pipeline backed by knowledge-rich `EventOptionSnapshot` records captured at gameplay time.

**Architecture:** The C# mod already emits full hover-tip payloads (effect_description, card rules_text, relic rarity, potion type) but the Python extractor reduces each to a name string. We keep the richer payload, BBCode-strip at capture time, drop Proceed-only closing stages, then in postrun group memories by (run_id, floor) into playthroughs, and emit a structured option library scored in the same LLM call — no extra LLM pass, no lookup calls at extract or consolidation time.

**Tech Stack:** Python 3.11 frozen dataclasses, pytest, existing `src/memory/models_v2.py` patterns.

**Spec:** `docs/superpowers/specs/2026-04-24-event-guide-consolidation-rework-design.md`

---

## File Structure

| File | Responsibility | Action |
|---|---|---|
| `src/memory/models_v2.py` | HCM data models | Add `RelicReward`/`CardReward`/`PotionReward`; upgrade `EventOptionSnapshot`; add `EventGuideOption`; extend `EventGuide.options` |
| `src/memory/short_term.py` | Mutable working memory | Add `cancel_event()` helper |
| `src/agent/loop.py` | Core agent loop | Modify `_finalize_event_stage`: preserve mod payload, strip BBCode, drop Proceed-only stages |
| `src/memory/guide_consolidator.py` | Postrun guide builder | Add `_select_event_keys_for_refresh`; rewrite `build_event_guide_prompt` and `parse_event_guide_response`; swap event branch |
| `src/memory/retriever.py` | Context injection | Filter `EventGuide.options` by current event + render scored block |
| `tests/test_event_memory_model.py` | Model round-trip | Extend with RewardDetail + upgraded EventOptionSnapshot + EventGuideOption tests |
| `tests/test_event_guide_consolidator.py` | Consolidator logic | Extend with selection + playthrough grouping + option parsing tests |

---

## Task Order

1. Reward detail types (`RelicReward` / `CardReward` / `PotionReward`)
2. `EventOptionSnapshot` upgrade (with legacy-string compat)
3. `EventGuideOption` + `EventGuide.options` extension
4. `_select_event_keys_for_refresh` helper
5. `build_event_guide_prompt` rewrite (stage-aware, knowledge-rich, token-budgeted)
6. `parse_event_guide_response` rewrite (structured options, server-side sample_size)
7. Extractor: preserve full payload + BBCode strip + Proceed-only drop
8. Wire consolidator event branch + retriever injection

---

### Task 1: Reward detail types

**Files:**
- Modify: `src/memory/models_v2.py` (append after `EventOptionSnapshot` block near line 1120)
- Test: `tests/test_event_memory_model.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_memory_model.py`:

```python
def test_relic_reward_roundtrip():
    """RelicReward serializes with name/description/rarity."""
    from src.memory.models_v2 import RelicReward

    r = RelicReward(name="Archaic Tooth", description="Transform a card.", rarity="uncommon")
    d = r.to_dict()
    restored = RelicReward.from_dict(d)
    assert restored.name == "Archaic Tooth"
    assert restored.description == "Transform a card."
    assert restored.rarity == "uncommon"


def test_relic_reward_defaults():
    from src.memory.models_v2 import RelicReward

    r = RelicReward(name="X")
    assert r.description == ""
    assert r.rarity == ""


def test_card_reward_maps_mod_keys():
    """CardReward.from_dict accepts mod-side keys `type` and `is_upgraded`."""
    from src.memory.models_v2 import CardReward

    mod_payload = {
        "name": "Suppress+",
        "cost": 1,
        "type": "skill",
        "rules_text": "Apply 2 Weak.",
        "is_upgraded": True,
    }
    c = CardReward.from_dict(mod_payload)
    assert c.name == "Suppress+"
    assert c.cost == 1
    assert c.card_type == "skill"
    assert c.rules_text == "Apply 2 Weak."
    assert c.upgraded is True

    # to_dict emits the Python-side names, not the mod keys
    persisted = c.to_dict()
    assert persisted == {
        "name": "Suppress+",
        "cost": 1,
        "card_type": "skill",
        "rules_text": "Apply 2 Weak.",
        "upgraded": True,
    }

    # Round-trip from persisted form
    restored = CardReward.from_dict(persisted)
    assert restored.card_type == "skill"
    assert restored.upgraded is True


def test_potion_reward_maps_mod_key():
    """PotionReward.from_dict reads mod-side `type` into potion_type."""
    from src.memory.models_v2 import PotionReward

    mod_payload = {
        "name": "Fire Potion",
        "description": "Deal 20 damage.",
        "type": "damage",
    }
    p = PotionReward.from_dict(mod_payload)
    assert p.name == "Fire Potion"
    assert p.description == "Deal 20 damage."
    assert p.potion_type == "damage"

    persisted = p.to_dict()
    assert persisted["potion_type"] == "damage"
    assert "type" not in persisted


def test_reward_from_dict_tolerates_unknown_keys():
    """All three reward types silently drop unknown keys."""
    from src.memory.models_v2 import RelicReward, CardReward, PotionReward

    assert RelicReward.from_dict({"name": "X", "future_field": 1}).name == "X"
    assert CardReward.from_dict({"name": "X", "future_field": 1}).name == "X"
    assert PotionReward.from_dict({"name": "X", "future_field": 1}).name == "X"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_memory_model.py::test_relic_reward_roundtrip tests/test_event_memory_model.py::test_card_reward_maps_mod_keys tests/test_event_memory_model.py::test_potion_reward_maps_mod_key tests/test_event_memory_model.py::test_reward_from_dict_tolerates_unknown_keys tests/test_event_memory_model.py::test_relic_reward_defaults -v`
Expected: FAIL with `ImportError` (RelicReward etc. not defined).

- [ ] **Step 3: Add the dataclasses**

In `src/memory/models_v2.py`, insert **before** the existing `class EventOptionSnapshot` block (so EventOptionSnapshot can reference them in the next task). Search for the line `# ── Event Models ──────────────────────────────────────────────` and add this block between that header and `class EventOptionSnapshot`:

```python
@dataclass(frozen=True)
class RelicReward:
    """A relic offered by an event option, snapshotted at encounter time."""

    name: str = ""
    description: str = ""       # BBCode-stripped at extract time
    rarity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "rarity": self.rarity}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RelicReward:
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            rarity=d.get("rarity", ""),
        )


@dataclass(frozen=True)
class CardReward:
    """A card offered by an event option, snapshotted at encounter time.

    Mod-side payload uses keys ``type`` and ``is_upgraded``. Python-side
    uses ``card_type`` and ``upgraded`` to avoid shadowing the ``type``
    built-in. ``from_dict`` accepts both spellings; ``to_dict`` emits the
    Python-side names.
    """

    name: str = ""
    cost: int = 0
    card_type: str = ""         # "skill" | "attack" | "power"
    rules_text: str = ""        # BBCode-stripped at extract time
    upgraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cost": self.cost,
            "card_type": self.card_type,
            "rules_text": self.rules_text,
            "upgraded": self.upgraded,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardReward:
        return cls(
            name=d.get("name", ""),
            cost=int(d.get("cost", 0) or 0),
            card_type=d.get("card_type", d.get("type", "")),
            rules_text=d.get("rules_text", ""),
            upgraded=bool(d.get("upgraded", d.get("is_upgraded", False))),
        )


@dataclass(frozen=True)
class PotionReward:
    """A potion offered by an event option, snapshotted at encounter time."""

    name: str = ""
    description: str = ""       # BBCode-stripped at extract time
    potion_type: str = ""       # mod-side key is "type"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "potion_type": self.potion_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> PotionReward:
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            potion_type=d.get("potion_type", d.get("type", "")),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_event_memory_model.py -v`
Expected: PASS (all existing + new tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py tests/test_event_memory_model.py
git commit -m "feat(event-guide): RelicReward/CardReward/PotionReward dataclasses

Snapshotted reward detail types for EventOptionSnapshot. from_dict accepts
both mod-side keys (type, is_upgraded) and Python-side keys (card_type,
potion_type, upgraded); to_dict emits Python-side names for persisted JSONL.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Upgrade EventOptionSnapshot with legacy-string compat

**Files:**
- Modify: `src/memory/models_v2.py:1078-1120` (`EventOptionSnapshot` class)
- Test: `tests/test_event_memory_model.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_memory_model.py`:

```python
def test_event_option_snapshot_accepts_dict_rewards():
    """New payload shape: reward dicts with full detail."""
    from src.memory.models_v2 import (
        EventOptionSnapshot, RelicReward, CardReward, PotionReward,
    )

    opt = EventOptionSnapshot(
        index=0,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        relics_offered=(
            RelicReward(name="Archaic Tooth",
                        description="Transform a starter card.",
                        rarity="uncommon"),
        ),
        cards_offered=(
            CardReward(name="Suppress+", cost=1, card_type="skill",
                       rules_text="Apply 2 Weak.", upgraded=True),
        ),
        potions_offered=(
            PotionReward(name="Fire Potion", description="Deal 20.",
                         potion_type="damage"),
        ),
    )
    d = opt.to_dict()
    restored = EventOptionSnapshot.from_dict(d)
    assert restored.relics_offered[0].rarity == "uncommon"
    assert restored.cards_offered[0].rules_text == "Apply 2 Weak."
    assert restored.cards_offered[0].upgraded is True
    assert restored.potions_offered[0].potion_type == "damage"


def test_event_option_snapshot_legacy_strings_upgrade():
    """Legacy JSONL with string-only reward lists loads cleanly."""
    from src.memory.models_v2 import EventOptionSnapshot

    legacy = {
        "index": 0,
        "title": "Archaic Tooth",
        "description": "Transform a card.",
        "relics_offered": ["Archaic Tooth"],
        "cards_offered": ["Suppress+"],
        "potions_offered": ["Fire Potion"],
    }
    opt = EventOptionSnapshot.from_dict(legacy)
    assert opt.relics_offered[0].name == "Archaic Tooth"
    assert opt.relics_offered[0].description == ""
    assert opt.cards_offered[0].name == "Suppress+"
    assert opt.cards_offered[0].rules_text == ""
    assert opt.potions_offered[0].name == "Fire Potion"
    assert opt.potions_offered[0].potion_type == ""


def test_event_option_snapshot_mod_payload_keys():
    """Mod-side keys (type, is_upgraded) flow through via reward from_dict."""
    from src.memory.models_v2 import EventOptionSnapshot

    mod_style = {
        "index": 1,
        "title": "Demon Glass",
        "description": "See 15 cards from Ironclad.",
        "cards_offered": [
            {"name": "Bash", "cost": 2, "type": "attack",
             "rules_text": "Deal 8. Vuln 2.", "is_upgraded": False},
        ],
    }
    opt = EventOptionSnapshot.from_dict(mod_style)
    assert opt.cards_offered[0].card_type == "attack"
    assert opt.cards_offered[0].upgraded is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_memory_model.py::test_event_option_snapshot_accepts_dict_rewards tests/test_event_memory_model.py::test_event_option_snapshot_legacy_strings_upgrade tests/test_event_memory_model.py::test_event_option_snapshot_mod_payload_keys -v`
Expected: FAIL (current schema uses `tuple[str, ...]`).

- [ ] **Step 3: Replace the EventOptionSnapshot class**

In `src/memory/models_v2.py`, replace the current `EventOptionSnapshot` block (starts `@dataclass(frozen=True)\nclass EventOptionSnapshot:` around line 1078) with:

```python
@dataclass(frozen=True)
class EventOptionSnapshot:
    """Snapshot of a single event option with full reward details.

    BBCode is stripped at extract time (``src/agent/loop.py::_finalize_event_stage``)
    so consumers can trust the strings. Reward fields are frozen dataclasses
    of (name, description, …) so the consolidator prompt can render rich
    rules text without any runtime knowledge lookups.

    Legacy JSONL with bare-string reward lists is accepted by ``from_dict``
    and upgraded to the dataclass form with empty description/rarity/etc.
    """

    index: int = 0
    title: str = ""
    description: str = ""
    hp_cost: int | None = None
    gold_cost: int | None = None
    relics_offered: tuple[RelicReward, ...] = ()
    cards_offered: tuple[CardReward, ...] = ()
    potions_offered: tuple[PotionReward, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "title": self.title,
            "description": self.description,
        }
        if self.hp_cost is not None:
            d["hp_cost"] = self.hp_cost
        if self.gold_cost is not None:
            d["gold_cost"] = self.gold_cost
        if self.relics_offered:
            d["relics_offered"] = [r.to_dict() for r in self.relics_offered]
        if self.cards_offered:
            d["cards_offered"] = [c.to_dict() for c in self.cards_offered]
        if self.potions_offered:
            d["potions_offered"] = [p.to_dict() for p in self.potions_offered]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventOptionSnapshot":
        def _coerce(items: Any, reward_cls: type) -> tuple:
            if not items:
                return ()
            out = []
            for it in items:
                if isinstance(it, str):
                    out.append(reward_cls.from_dict({"name": it}))
                elif isinstance(it, dict):
                    out.append(reward_cls.from_dict(it))
                else:
                    # Unknown shape — keep processing siblings.
                    continue
            return tuple(out)

        return cls(
            index=d.get("index", 0),
            title=d.get("title", ""),
            description=d.get("description", ""),
            hp_cost=d.get("hp_cost"),
            gold_cost=d.get("gold_cost"),
            relics_offered=_coerce(d.get("relics_offered", ()), RelicReward),
            cards_offered=_coerce(d.get("cards_offered", ()), CardReward),
            potions_offered=_coerce(d.get("potions_offered", ()), PotionReward),
        )
```

- [ ] **Step 4: Update any existing call sites that indexed the old string tuples**

Grep for breakages:

```bash
grep -rn "relics_offered\|cards_offered\|potions_offered" src/memory/ src/agent/ src/brain/ tests/ | grep -v ".pyc"
```

Expected breakage sites (fix them in this step):

1. `tests/test_event_guide_consolidator.py::test_event_guide_prompt_includes_option_details` (line 80): construction uses `relics_offered=("Sword of Stone",)`. Update to `relics_offered=(RelicReward(name="Sword of Stone"),)` and add `from src.memory.models_v2 import RelicReward` to the existing top-of-file import.

2. `src/memory/guide_consolidator.py:1100-1109` currently renders rewards with `list(od.relics_offered)`. It still works (prints the RelicReward repr), but the output is ugly. **Leave this for Task 5** which rewrites the prompt builder entirely.

3. `src/agent/loop.py` around `_finalize_event_stage` flattens incoming dicts to `.get("name")`. **Leave this for Task 7** which rewrites the extractor.

- [ ] **Step 5: Run tests**

Run: `pytest tests/test_event_memory_model.py tests/test_event_guide_consolidator.py -v`
Expected: PASS (both files; 5 new tests plus existing round-trip tests).

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py tests/test_event_memory_model.py tests/test_event_guide_consolidator.py
git commit -m "feat(event-guide): EventOptionSnapshot carries full reward details

Upgrades relics_offered/cards_offered/potions_offered from tuple[str,...]
to tuple[RelicReward,...] etc. from_dict accepts legacy bare-string
elements and upgrades them with empty description/rarity.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Add EventGuideOption and EventGuide.options

**Files:**
- Modify: `src/memory/models_v2.py:1234-1273` (`EventGuide` class) + insert `EventGuideOption` before it
- Test: `tests/test_event_memory_model.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_memory_model.py`:

```python
def test_event_guide_option_roundtrip():
    from src.memory.models_v2 import EventGuideOption

    opt = EventGuideOption(
        canonical_name="Archaic Tooth",
        stage_index=0,
        variant_type="fixed",
        score=0.7,
        analysis="Free upgrade to starter card.",
        observed_rewards=("Suppress+",),
        sample_size=14,
    )
    d = opt.to_dict()
    restored = EventGuideOption.from_dict(d)
    assert restored.canonical_name == "Archaic Tooth"
    assert restored.variant_type == "fixed"
    assert restored.score == 0.7
    assert restored.sample_size == 14


def test_event_guide_option_defaults():
    from src.memory.models_v2 import EventGuideOption

    opt = EventGuideOption(canonical_name="X")
    assert opt.stage_index == 0
    assert opt.variant_type == "fixed"
    assert opt.score == 0.0
    assert opt.sample_size == 0
    assert opt.observed_rewards == ()


def test_event_guide_with_options_roundtrip():
    from src.memory.models_v2 import EventGuide, EventGuideOption

    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Free power spike.",
        options=(
            EventGuideOption(canonical_name="Archaic Tooth", stage_index=0,
                             score=0.7, analysis="Free upgrade.", sample_size=14),
            EventGuideOption(canonical_name="Demon Glass", stage_index=0,
                             variant_type="random_from_pool", score=0.3,
                             analysis="Deck injection.",
                             observed_rewards=("Bash", "Iron Wave"),
                             sample_size=3),
        ),
        episode_count=20,
        confidence=0.8,
    )
    d = guide.to_dict()
    restored = EventGuide.from_dict(d)
    assert len(restored.options) == 2
    assert restored.options[0].canonical_name == "Archaic Tooth"
    assert restored.options[1].observed_rewards == ("Bash", "Iron Wave")


def test_event_guide_legacy_without_options():
    """Legacy EventGuide JSONL (no `options` key) still loads; options=()."""
    from src.memory.models_v2 import EventGuide

    legacy = {
        "event_id": "OROBAS",
        "character": "the silent",
        "guide_text": "Legacy freeform text.",
        "episode_count": 5,
        "confidence": 0.7,
        "version": 2,
    }
    guide = EventGuide.from_dict(legacy)
    assert guide.event_id == "OROBAS"
    assert guide.options == ()
    assert guide.version == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_memory_model.py::test_event_guide_option_roundtrip tests/test_event_memory_model.py::test_event_guide_option_defaults tests/test_event_memory_model.py::test_event_guide_with_options_roundtrip tests/test_event_memory_model.py::test_event_guide_legacy_without_options -v`
Expected: FAIL with `ImportError` for `EventGuideOption`.

- [ ] **Step 3: Add EventGuideOption and extend EventGuide**

In `src/memory/models_v2.py`, insert a new block **immediately before** `class EventGuide`:

```python
@dataclass(frozen=True)
class EventGuideOption:
    """A single scored option in an event's option library.

    ``canonical_name`` is the LLM-normalized title (matched against
    ``gs.event.options[*].title`` case-insensitively at injection time).
    ``stage_index`` is 0-based; multi-step events use 0,1,2... in stage
    order. ``variant_type`` distinguishes deterministic vs pool-random vs
    deck-random choices. ``sample_size`` is recomputed server-side from
    ``EventMemory`` count (LLM output is overridden).
    """

    canonical_name: str = ""
    stage_index: int = 0
    variant_type: str = "fixed"     # "fixed" | "random_from_pool" | "deck_random"
    score: float = 0.0              # -1.0 to 1.0
    analysis: str = ""
    observed_rewards: tuple[str, ...] = ()
    sample_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "stage_index": self.stage_index,
            "variant_type": self.variant_type,
            "score": self.score,
            "analysis": self.analysis,
            "observed_rewards": list(self.observed_rewards),
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventGuideOption:
        return cls(
            canonical_name=d.get("canonical_name", ""),
            stage_index=int(d.get("stage_index", 0) or 0),
            variant_type=d.get("variant_type", "fixed"),
            score=float(d.get("score", 0.0) or 0.0),
            analysis=d.get("analysis", ""),
            observed_rewards=tuple(d.get("observed_rewards", ()) or ()),
            sample_size=int(d.get("sample_size", 0) or 0),
        )
```

Then in the existing `EventGuide` class, add the `options` field and update `to_dict` / `from_dict`:

```python
@dataclass(frozen=True)
class EventGuide:
    """Consolidated guide for a specific event type."""

    guide_id: str = field(default_factory=_new_id)
    event_id: str = ""
    character: str = ""
    guide_text: str = ""
    options: tuple[EventGuideOption, ...] = ()    # ← NEW
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
            "options": [o.to_dict() for o in self.options],
            "episode_count": self.episode_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventGuide:
        raw_options = d.get("options", ()) or ()
        options = tuple(
            EventGuideOption.from_dict(o) if isinstance(o, dict) else o
            for o in raw_options
        )
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            event_id=d.get("event_id", ""),
            character=d.get("character", ""),
            guide_text=d.get("guide_text", ""),
            options=options,
            episode_count=d.get("episode_count", 0),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
        )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_event_memory_model.py -v`
Expected: PASS (all existing + 4 new tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/models_v2.py tests/test_event_memory_model.py
git commit -m "feat(event-guide): EventGuide carries structured option library

New EventGuideOption dataclass (canonical_name, stage_index, variant_type,
score, analysis, observed_rewards, sample_size). EventGuide.options defaults
to () for legacy JSONL.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: `_select_event_keys_for_refresh` helper

**Files:**
- Modify: `src/memory/guide_consolidator.py` (add helper near `_select_combat_keys_for_refresh` at line 42)
- Test: `tests/test_event_guide_consolidator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_guide_consolidator.py`:

```python
def test_select_event_keys_for_refresh_run_scoped():
    """Only (event_id, character) pairs from the current run are selected."""
    from src.memory.guide_consolidator import _select_event_keys_for_refresh
    from src.memory.models_v2 import EventMemory

    memories = [
        EventMemory(run_id="run_A", event_id="OROBAS", character="the silent"),
        EventMemory(run_id="run_A", event_id="SUNKEN_STATUE", character="the silent"),
        EventMemory(run_id="run_B", event_id="OROBAS", character="the ironclad"),
        EventMemory(run_id="run_B", event_id="DESIGNER", character="the ironclad"),
    ]
    selected = _select_event_keys_for_refresh(memories, current_run_id="run_A")
    assert selected == {
        ("OROBAS", "the silent"),
        ("SUNKEN_STATUE", "the silent"),
    }


def test_select_event_keys_normalizes_character():
    from src.memory.guide_consolidator import _select_event_keys_for_refresh
    from src.memory.models_v2 import EventMemory

    memories = [
        EventMemory(run_id="r", event_id="OROBAS", character="Silent"),
        EventMemory(run_id="r", event_id="OROBAS", character="静默猎人"),
    ]
    selected = _select_event_keys_for_refresh(memories, current_run_id="r")
    # Both records normalize to "the silent"
    assert selected == {("OROBAS", "the silent")}


def test_select_event_keys_empty_run():
    """No memories for the current run → empty selection."""
    from src.memory.guide_consolidator import _select_event_keys_for_refresh
    from src.memory.models_v2 import EventMemory

    memories = [
        EventMemory(run_id="old", event_id="OROBAS", character="the silent"),
    ]
    assert _select_event_keys_for_refresh(memories, current_run_id="new") == set()


def test_select_event_keys_uppercases_event_id():
    from src.memory.guide_consolidator import _select_event_keys_for_refresh
    from src.memory.models_v2 import EventMemory

    memories = [
        EventMemory(run_id="r", event_id="orobas", character="the silent"),
    ]
    assert _select_event_keys_for_refresh(memories, current_run_id="r") == {
        ("OROBAS", "the silent"),
    }
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_guide_consolidator.py::test_select_event_keys_for_refresh_run_scoped tests/test_event_guide_consolidator.py::test_select_event_keys_normalizes_character tests/test_event_guide_consolidator.py::test_select_event_keys_empty_run tests/test_event_guide_consolidator.py::test_select_event_keys_uppercases_event_id -v`
Expected: FAIL with `ImportError` for `_select_event_keys_for_refresh`.

- [ ] **Step 3: Implement the helper**

In `src/memory/guide_consolidator.py`, add **immediately after** the `_select_combat_keys_for_refresh` function (around line 90, after the closing `return selected`):

```python
def _select_event_keys_for_refresh(
    memories: list[EventMemory],
    current_run_id: str,
) -> set[tuple[str, str]]:
    """Pick (event_id, character) keys whose guides should refresh this postrun.

    Policy (mirrors combat refresh, simpler): only events encountered in the
    current run are selected. Cross-run / cross-character refresh is not
    performed — LLM cost is spent only on pairs the run actually produced
    evidence for.

    Keys are returned with uppercase ``event_id`` and normalized
    ``character`` so downstream equality matches the guide store.
    """
    selected: set[tuple[str, str]] = set()
    for em in memories:
        if em.run_id != current_run_id:
            continue
        selected.add((
            em.event_id.upper(),
            normalize_character(em.character),
        ))
    return selected
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_event_guide_consolidator.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_event_guide_consolidator.py
git commit -m "feat(event-guide): _select_event_keys_for_refresh helper

Mirrors combat pattern — only (event_id, character) pairs touched by the
current run get refreshed. Wiring into consolidate_guides comes in a later
task.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Rewrite `build_event_guide_prompt` (stage-aware, knowledge-rich)

**Files:**
- Modify: `src/memory/guide_consolidator.py:1079-1119` (`build_event_guide_prompt` function)
- Test: `tests/test_event_guide_consolidator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_guide_consolidator.py`:

```python
def test_event_guide_prompt_groups_playthroughs():
    """Memories with the same (run_id, floor) are grouped into one playthrough."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import EventMemory, EventOptionSnapshot

    stage0 = EventMemory(
        run_id="runA", floor=18, act=2,
        event_id="BRIDGE", event_title="Bridge",
        character="the silent",
        chosen_option_index=0, chosen_option_text="Cross",
        all_option_details=(
            EventOptionSnapshot(index=0, title="Cross", description="Continue."),
            EventOptionSnapshot(index=1, title="Turn Back", description="Abandon."),
        ),
        timestamp=100.0,
        run_victory=True, run_final_floor=51,
    )
    stage1 = EventMemory(
        run_id="runA", floor=18, act=2,
        event_id="BRIDGE", event_title="Bridge",
        character="the silent",
        chosen_option_index=0, chosen_option_text="Fight",
        all_option_details=(
            EventOptionSnapshot(index=0, title="Fight", description="Elite."),
            EventOptionSnapshot(index=1, title="Flee", description="Lose HP."),
        ),
        timestamp=101.0,
        run_victory=True, run_final_floor=51,
    )
    prompt = build_event_guide_prompt("BRIDGE", "the silent", [stage0, stage1])
    # Both stages appear under the same playthrough header
    assert "Playthrough 1" in prompt
    assert prompt.count("Playthrough 1") == 1
    assert "Stage 0" in prompt
    assert "Stage 1" in prompt
    # Stages are ordered by timestamp
    idx_stage_0 = prompt.index("Stage 0")
    idx_stage_1 = prompt.index("Stage 1")
    assert idx_stage_0 < idx_stage_1


def test_event_guide_prompt_expands_reward_details_once():
    """Reward details (rules_text / rarity) show on first occurrence, then abbreviated."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import (
        EventMemory, EventOptionSnapshot, RelicReward,
    )

    archaic = RelicReward(
        name="Archaic Tooth",
        description="Transform a starter card into a stronger one.",
        rarity="uncommon",
    )
    opt = EventOptionSnapshot(
        index=2, title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        relics_offered=(archaic,),
    )
    mem1 = EventMemory(
        run_id="r1", floor=18, act=2, event_id="OROBAS", event_title="Orobas",
        character="the silent",
        chosen_option_index=2, chosen_option_text="Archaic Tooth",
        all_option_details=(opt,),
        run_victory=True, run_final_floor=51,
        timestamp=100.0,
    )
    mem2 = EventMemory(
        run_id="r2", floor=18, act=2, event_id="OROBAS", event_title="Orobas",
        character="the silent",
        chosen_option_index=2, chosen_option_text="Archaic Tooth",
        all_option_details=(opt,),
        run_victory=False, run_final_floor=34,
        timestamp=200.0,
    )
    prompt = build_event_guide_prompt("OROBAS", "the silent", [mem1, mem2])
    # Full description appears exactly once
    assert prompt.count("Transform a starter card into a stronger one.") == 1
    # The abbreviated marker appears in the second playthrough
    assert "(same as Playthrough 1)" in prompt


def test_event_guide_prompt_json_output_spec():
    """Prompt instructs the LLM to emit the structured options JSON."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import EventMemory

    mem = EventMemory(event_id="OROBAS", character="the silent",
                      run_victory=True, run_final_floor=51)
    prompt = build_event_guide_prompt("OROBAS", "the silent", [mem])
    assert '"options"' in prompt
    assert "canonical_name" in prompt
    assert "variant_type" in prompt
    assert '"score"' in prompt
    assert "fixed" in prompt and "random_from_pool" in prompt and "deck_random" in prompt


def test_event_guide_prompt_includes_run_outcome_anchor():
    """Each playthrough header shows victory/defeat + final floor."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import EventMemory

    victory = EventMemory(
        run_id="rV", floor=18, event_id="OROBAS", character="the silent",
        run_victory=True, run_final_floor=51, timestamp=100.0,
    )
    defeat = EventMemory(
        run_id="rD", floor=18, event_id="OROBAS", character="the silent",
        run_victory=False, run_final_floor=34, timestamp=200.0,
    )
    prompt = build_event_guide_prompt("OROBAS", "the silent", [victory, defeat])
    assert "VICTORY F51" in prompt
    assert "DEFEAT F34" in prompt


def test_event_guide_prompt_caps_at_12_playthroughs():
    """Only the 12 most recent playthroughs (by max timestamp in group) are rendered."""
    from src.memory.guide_consolidator import build_event_guide_prompt
    from src.memory.models_v2 import EventMemory

    memories = [
        EventMemory(
            run_id=f"r{i}", floor=18, event_id="OROBAS", character="the silent",
            run_victory=(i % 2 == 0), run_final_floor=30 + i,
            timestamp=float(i),
        )
        for i in range(20)
    ]
    prompt = build_event_guide_prompt("OROBAS", "the silent", memories)
    # Only 12 most recent playthroughs appear
    playthrough_count = prompt.count("Playthrough ")
    # Each playthrough appears once in a header, guidelines reference "Playthrough" 0 times
    assert playthrough_count == 12
    # The most recent (r19) is present, the oldest (r0) is absent
    assert "r19" in prompt
    assert "r0," not in prompt  # use trailing comma to avoid r0 matching r19
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_guide_consolidator.py::test_event_guide_prompt_groups_playthroughs tests/test_event_guide_consolidator.py::test_event_guide_prompt_expands_reward_details_once tests/test_event_guide_consolidator.py::test_event_guide_prompt_json_output_spec tests/test_event_guide_consolidator.py::test_event_guide_prompt_includes_run_outcome_anchor tests/test_event_guide_consolidator.py::test_event_guide_prompt_caps_at_12_playthroughs -v`
Expected: FAIL (current prompt is flat, no playthrough grouping, no structured JSON spec).

- [ ] **Step 3: Rewrite `build_event_guide_prompt`**

In `src/memory/guide_consolidator.py`, replace the current `build_event_guide_prompt` function (lines ~1079-1119) with:

```python
_EVENT_PROMPT_MAX_PLAYTHROUGHS = 12


def _format_reward_line(kind: str, reward: Any) -> str:
    """Render one reward entry (relic/card/potion) with full detail."""
    name = getattr(reward, "name", "") or ""
    if kind == "relic":
        rarity = getattr(reward, "rarity", "") or ""
        desc = getattr(reward, "description", "") or ""
        parts = [f"[relic] {name}"]
        if rarity:
            parts.append(f"(rarity={rarity})")
        if desc:
            parts.append(f"— {desc}")
        return " ".join(parts)
    if kind == "card":
        card_type = getattr(reward, "card_type", "") or ""
        cost = getattr(reward, "cost", 0)
        upgraded = getattr(reward, "upgraded", False)
        rules = getattr(reward, "rules_text", "") or ""
        upg_mark = "+" if upgraded else ""
        parts = [f"[card]  {name}{upg_mark}"]
        if card_type:
            parts.append(f"type={card_type}")
        parts.append(f"cost={cost}")
        if rules:
            parts.append(f"— {rules}")
        return " ".join(parts)
    if kind == "potion":
        potion_type = getattr(reward, "potion_type", "") or ""
        desc = getattr(reward, "description", "") or ""
        parts = [f"[potion] {name}"]
        if potion_type:
            parts.append(f"(type={potion_type})")
        if desc:
            parts.append(f"— {desc}")
        return " ".join(parts)
    return name


def _format_option_full(opt: EventOptionSnapshot) -> list[str]:
    """Render one option with every reward expanded. Returns a list of
    rendered lines (indented by caller)."""
    lines = [f'[{opt.index}] {opt.title} — {opt.description}']
    for r in opt.relics_offered:
        lines.append(_format_reward_line("relic", r))
    for c in opt.cards_offered:
        lines.append(_format_reward_line("card", c))
    for p in opt.potions_offered:
        lines.append(_format_reward_line("potion", p))
    if opt.hp_cost is not None:
        lines.append(f"(hp_cost={opt.hp_cost})")
    if opt.gold_cost is not None:
        lines.append(f"(gold_cost={opt.gold_cost})")
    return lines


def _option_seen_key(opt: EventOptionSnapshot, stage_index: int) -> tuple[int, str]:
    """Dedup key: (stage_index, option title). Case-insensitive title."""
    return (stage_index, (opt.title or "").strip().lower())


def _group_playthroughs(
    memories: list[EventMemory],
) -> list[list[EventMemory]]:
    """Group memories by (run_id, floor) into playthroughs, ordered stages
    within group by timestamp; return playthroughs sorted by max-timestamp
    descending (most recent first)."""
    groups: dict[tuple[str, int], list[EventMemory]] = {}
    for em in memories:
        groups.setdefault((em.run_id, em.floor), []).append(em)
    playthroughs = []
    for _key, stages in groups.items():
        stages_sorted = sorted(stages, key=lambda m: m.timestamp)
        playthroughs.append(stages_sorted)
    playthroughs.sort(
        key=lambda stages: max(m.timestamp for m in stages),
        reverse=True,
    )
    return playthroughs


def build_event_guide_prompt(
    event_id: str,
    character: str,
    memories: list[EventMemory],
    existing: EventGuide | None = None,
) -> str:
    """Build a stage-aware, knowledge-rich event guide prompt.

    Memories are grouped by (run_id, floor) into playthroughs; stages
    within a playthrough are ordered by timestamp. Reward details are
    expanded on first occurrence across the prompt; repeat occurrences
    render as ``(same as Playthrough K)``. Capped to the
    ``_EVENT_PROMPT_MAX_PLAYTHROUGHS`` most recent playthroughs.

    Output spec instructs the LLM to emit structured
    ``{guide_text, confidence, options: [...]}`` with ``options`` matching
    ``EventGuideOption``.
    """
    playthroughs = _group_playthroughs(memories)[:_EVENT_PROMPT_MAX_PLAYTHROUGHS]

    lines: list[str] = [
        f"Event: {event_id} | Character: {character} | "
        f"Playthroughs: {len(playthroughs)} (of {len(memories)} total memories)",
        "",
    ]

    # Track first playthrough index that expanded each option fully.
    seen_options: dict[tuple[int, str], int] = {}

    for pt_idx, stages in enumerate(playthroughs, start=1):
        first_stage = stages[0]
        run_prefix = first_stage.run_id[:6] if first_stage.run_id else "?"
        outcome_tag = event_run_outcome_tag(first_stage).strip()
        if outcome_tag.startswith("[") and outcome_tag.endswith("]"):
            outcome_tag = outcome_tag[1:-1]
        lines.append(
            f"Playthrough {pt_idx} (run={run_prefix}, F{first_stage.floor}, "
            f"{outcome_tag or 'outcome=UNKNOWN'}):"
        )
        for stage_idx, em in enumerate(stages):
            n_opts = len(em.all_option_details) or len(em.all_options)
            lines.append(f"  Stage {stage_idx}: Choose 1 of {n_opts}")
            for opt in em.all_option_details:
                key = _option_seen_key(opt, stage_idx)
                first_pt = seen_options.get(key)
                if first_pt is None:
                    seen_options[key] = pt_idx
                    for rendered in _format_option_full(opt):
                        lines.append(f"    {rendered}")
                else:
                    lines.append(
                        f"    [{opt.index}] {opt.title}  "
                        f"(same as Playthrough {first_pt})"
                    )
            diff_parts = [
                f"HP {em.hp_before}→{em.hp_after}",
                f"Gold {em.gold_before}→{em.gold_after}",
            ]
            if em.cards_gained:
                diff_parts.append(f"+{list(em.cards_gained)}")
            if em.cards_lost:
                diff_parts.append(f"-{list(em.cards_lost)}")
            if em.relics_gained:
                diff_parts.append(f"relics+{list(em.relics_gained)}")
            if em.potions_gained:
                diff_parts.append(f"potions+{list(em.potions_gained)}")
            lines.append(
                f"    → chose [{em.chosen_option_index}] "
                f"'{em.chosen_option_text}', diff: {', '.join(diff_parts)}"
            )
        lines.append("")

    if existing:
        lines.append(f"Previous guide (v{existing.version}): {existing.guide_text}")
        if existing.options:
            lines.append("Previous options (update in place where relevant):")
            for o in existing.options:
                lines.append(
                    f"  - {o.canonical_name} [stage={o.stage_index}, "
                    f"{o.variant_type}, score={o.score:+.2f}, n={o.sample_size}]: "
                    f"{o.analysis}"
                )
        lines.append("")

    lines.extend([
        "Task: Build the option library for this event.",
        "",
        "Respond with JSON ONLY (no markdown fences):",
        "{",
        '  "guide_text": "<1-2 sentences: cross-option takeaway>",',
        '  "confidence": <0.0-1.0>,',
        '  "options": [',
        "    {",
        '      "canonical_name": "<name>",',
        '      "stage_index": <int 0-based>,',
        '      "variant_type": "fixed | random_from_pool | deck_random",',
        '      "score": <-1.0 to 1.0>,',
        '      "analysis": "<1-2 sentence rationale>",',
        '      "observed_rewards": ["<name>", "..."],',
        '      "sample_size": <int>',
        "    }",
        "  ]",
        "}",
        "",
        "Guidelines:",
        "- fixed: option outcome is deterministic across encounters.",
        "- random_from_pool: option rewards a roll from a fixed pool "
        '(e.g. "a random Uncommon relic"). Merge variants under one entry '
        'and enumerate concrete rolls in observed_rewards.',
        "- deck_random: option transforms/affects a random card from your deck.",
        "- score: weight by run outcome anchor (VICTORY>DEFEAT), concrete "
        "state-diff gain (HP/gold/cards/relics), and cross-encounter stability.",
        "- Do NOT invent options not seen in any playthrough.",
        "- Do NOT output options for stages that contained only a single "
        '"Proceed" button — those are closing pages and carry no signal.',
    ])
    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_event_guide_consolidator.py -v`
Expected: PASS (5 new tests + existing `test_event_guide_prompt_includes_option_details`, `test_build_event_guide_prompt_includes_run_outcome_tag` — the existing tests may need minor updates if they assert exact prompt phrasing; check failure messages and update asserts to match the new playthrough-grouped format if needed; the *semantic* assertions (event names, option titles) should still hold).

If `test_build_event_guide_prompt_includes_run_outcome_tag` fails: the old test looks for `"VICTORY F51"` which the new prompt also produces — should pass. If `test_event_guide_prompt_includes_option_details` fails: the old test checks for `"Dive into the Water"` and `"Obtain the Sword of Stone"` which the new prompt includes under Stage 0 — should pass. `"Gain 111 Gold"` is also included in the description field — should pass.

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_event_guide_consolidator.py
git commit -m "feat(event-guide): stage-aware knowledge-rich consolidation prompt

build_event_guide_prompt groups memories by (run_id, floor) into
playthroughs, expands reward details on first occurrence (with
'(same as Playthrough K)' dedup on repeats), caps at 12 recent
playthroughs, and instructs LLM to emit structured options JSON.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 6: Rewrite `parse_event_guide_response` (structured options + server-side sample_size)

**Files:**
- Modify: `src/memory/guide_consolidator.py:1122-1157` (`parse_event_guide_response` function)
- Test: `tests/test_event_guide_consolidator.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_event_guide_consolidator.py`:

```python
def test_parse_event_guide_response_parses_options():
    from src.memory.guide_consolidator import parse_event_guide_response
    from src.memory.models_v2 import EventMemory, EventOptionSnapshot

    raw = """{
      "guide_text": "Orobas is always a free power spike.",
      "confidence": 0.85,
      "options": [
        {"canonical_name": "Archaic Tooth", "stage_index": 0,
         "variant_type": "fixed", "score": 0.7,
         "analysis": "Free upgrade to starter.",
         "observed_rewards": ["Suppress+"], "sample_size": 99},
        {"canonical_name": "Demon Glass", "stage_index": 0,
         "variant_type": "random_from_pool", "score": 0.3,
         "analysis": "Deck injection.",
         "observed_rewards": ["Bash"], "sample_size": 99}
      ]
    }"""
    # Memories: two records with titles matching canonical_name
    memories = [
        EventMemory(all_option_details=(
            EventOptionSnapshot(index=2, title="Archaic Tooth"),
            EventOptionSnapshot(index=0, title="Demon Glass"),
        )),
        EventMemory(all_option_details=(
            EventOptionSnapshot(index=2, title="Archaic Tooth"),
        )),
    ]
    guide = parse_event_guide_response(
        raw, event_id="OROBAS", character="the silent",
        episode_count=2, memories=memories,
    )
    assert guide is not None
    assert len(guide.options) == 2
    names = {o.canonical_name for o in guide.options}
    assert names == {"Archaic Tooth", "Demon Glass"}
    # sample_size recomputed server-side (LLM said 99, memories say otherwise)
    archaic = next(o for o in guide.options if o.canonical_name == "Archaic Tooth")
    demon = next(o for o in guide.options if o.canonical_name == "Demon Glass")
    assert archaic.sample_size == 2   # appeared in both memories
    assert demon.sample_size == 1


def test_parse_event_guide_response_drops_malformed_options():
    """Malformed option entries are skipped; valid siblings survive."""
    from src.memory.guide_consolidator import parse_event_guide_response
    from src.memory.models_v2 import EventMemory, EventOptionSnapshot

    raw = """{
      "guide_text": "x",
      "options": [
        {"canonical_name": "Good", "stage_index": 0, "score": 0.5,
         "analysis": "fine"},
        "not a dict",
        {"missing_required": true}
      ]
    }"""
    mem = EventMemory(all_option_details=(
        EventOptionSnapshot(index=0, title="Good"),
    ))
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1, memories=[mem],
    )
    assert guide is not None
    # Only the one with a non-empty canonical_name survives
    assert len(guide.options) == 1
    assert guide.options[0].canonical_name == "Good"


def test_parse_event_guide_response_clamps_score_and_confidence():
    from src.memory.guide_consolidator import parse_event_guide_response
    from src.memory.models_v2 import EventMemory

    raw = """{
      "guide_text": "x",
      "confidence": 1.5,
      "options": [
        {"canonical_name": "A", "score": 2.0, "stage_index": 0, "analysis": "x"},
        {"canonical_name": "B", "score": -3.0, "stage_index": 0, "analysis": "x"}
      ]
    }"""
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1,
        memories=[EventMemory()],
    )
    assert guide is not None
    assert guide.confidence == 1.0
    scores = sorted(o.score for o in guide.options)
    assert scores == [-1.0, 1.0]


def test_parse_event_guide_response_handles_legacy_without_options():
    """Legacy LLM response (no `options` key) still produces a guide; options=()."""
    from src.memory.guide_consolidator import parse_event_guide_response
    from src.memory.models_v2 import EventMemory

    raw = '{"guide_text": "old-format advice", "confidence": 0.6}'
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1,
        memories=[EventMemory()],
    )
    assert guide is not None
    assert guide.guide_text == "old-format advice"
    assert guide.options == ()


def test_parse_event_guide_response_garbage_returns_none():
    from src.memory.guide_consolidator import parse_event_guide_response

    assert parse_event_guide_response(
        "not json", event_id="X", character="y",
        episode_count=1, memories=[],
    ) is None
```

Also update the existing `test_parse_event_guide_response` and `test_parse_event_guide_response_updates_version` tests to pass the new `memories` kwarg — change the calls to include `memories=[]`:

Replace in `tests/test_event_guide_consolidator.py`:

```python
# OLD (two existing tests)
    guide = parse_event_guide_response(
        raw,
        event_id="OROBAS",
        character="silent",
        episode_count=4,
        existing_guide=None,
    )
```

with

```python
    guide = parse_event_guide_response(
        raw,
        event_id="OROBAS",
        character="silent",
        episode_count=4,
        memories=[],
        existing_guide=None,
    )
```

Apply the same update (adding `memories=[]` before `existing_guide`) to the second legacy test `test_parse_event_guide_response_updates_version` and to the `test_parse_event_guide_response_handles_garbage` inline calls at the top of the file.

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_event_guide_consolidator.py -v`
Expected: FAIL (new `memories` parameter not in signature; existing tests fail with `TypeError: unexpected keyword argument 'memories'` or pass only because the old signature still exists).

- [ ] **Step 3: Rewrite `parse_event_guide_response`**

In `src/memory/guide_consolidator.py`, replace the current `parse_event_guide_response` function (lines ~1122-1157) with:

```python
def _count_option_appearances(
    canonical_name: str,
    memories: list[EventMemory],
) -> int:
    """Count memories where at least one option title matches canonical_name
    case-insensitively."""
    needle = canonical_name.strip().lower()
    if not needle:
        return 0
    count = 0
    for em in memories:
        titles: list[str] = []
        for od in em.all_option_details:
            titles.append((od.title or "").strip().lower())
        for t in em.all_options:
            titles.append((t or "").strip().lower())
        if needle in titles:
            count += 1
    return count


def parse_event_guide_response(
    raw: str,
    event_id: str,
    character: str,
    episode_count: int,
    memories: list[EventMemory],
    existing_guide: EventGuide | None = None,
) -> EventGuide | None:
    """Parse LLM response into an EventGuide with structured options.

    Server-side overrides:
      - ``sample_size`` is recomputed from ``memories`` (LLM value ignored).
      - ``score`` is clamped to [-1.0, 1.0].
      - ``confidence`` is clamped to [0.0, 1.0].

    Malformed option entries are skipped; valid siblings survive. A response
    lacking an ``options`` key is accepted (legacy guide shape) and yields
    ``EventGuide.options == ()``.
    """
    import json

    text = raw.strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        return None

    try:
        data = json.loads(text[start:end + 1])
    except json.JSONDecodeError:
        return None

    guide_text = data.get("guide_text", "")
    if not guide_text:
        return None

    confidence = max(0.0, min(1.0, float(data.get("confidence", 0.5) or 0.0)))
    version = (existing_guide.version + 1) if existing_guide else 1

    raw_options = data.get("options", []) or []
    parsed_options: list[EventGuideOption] = []
    for entry in raw_options:
        if not isinstance(entry, dict):
            continue
        canonical = (entry.get("canonical_name") or "").strip()
        if not canonical:
            continue
        variant = entry.get("variant_type", "fixed")
        if variant not in ("fixed", "random_from_pool", "deck_random"):
            variant = "fixed"
        try:
            score = float(entry.get("score", 0.0) or 0.0)
        except (TypeError, ValueError):
            score = 0.0
        score = max(-1.0, min(1.0, score))
        try:
            stage_idx = int(entry.get("stage_index", 0) or 0)
        except (TypeError, ValueError):
            stage_idx = 0
        observed = tuple(
            str(x) for x in (entry.get("observed_rewards") or ())
            if isinstance(x, (str, int, float))
        )
        # Server-side sample_size: override LLM claim.
        sample_size = _count_option_appearances(canonical, memories)
        parsed_options.append(EventGuideOption(
            canonical_name=canonical,
            stage_index=stage_idx,
            variant_type=variant,
            score=score,
            analysis=(entry.get("analysis") or "").strip(),
            observed_rewards=observed,
            sample_size=sample_size,
        ))

    return EventGuide(
        event_id=event_id.upper(),
        character=normalize_character(character),
        guide_text=guide_text,
        options=tuple(parsed_options),
        episode_count=episode_count,
        confidence=confidence,
        version=version,
    )
```

- [ ] **Step 4: Run tests**

Run: `pytest tests/test_event_guide_consolidator.py -v`
Expected: PASS (all new tests + updated existing tests).

- [ ] **Step 5: Commit**

```bash
git add src/memory/guide_consolidator.py tests/test_event_guide_consolidator.py
git commit -m "feat(event-guide): structured options parsing with server-side sample_size

parse_event_guide_response now parses EventGuideOption entries, clamps
score/confidence to valid ranges, drops malformed option entries (keeps
valid siblings), and recomputes sample_size from the memories list so the
LLM cannot drift the count across versions.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 7: Extractor — preserve mod payload + BBCode strip + Proceed-only filter

**Files:**
- Modify: `src/memory/short_term.py:387-440` (`ShortTermMemory`) — add `cancel_event()`
- Modify: `src/agent/loop.py:3099-3144` (`_finalize_event_stage`)
- Test: `tests/test_event_memory_model.py` (new integration-style test)
- Test: `tests/test_short_term.py` (if exists; otherwise add to `tests/test_event_memory_model.py`)

- [ ] **Step 1: Check for existing short_term tests**

Run: `ls tests/test_short_term*.py 2>/dev/null || echo "no short_term test file"`

If `tests/test_short_term_event.py` or similar exists, extend it. Otherwise create a new file `tests/test_short_term_event.py`.

- [ ] **Step 2: Write the failing tests**

Create (or append to) `tests/test_short_term_event.py`:

```python
"""Tests for ShortTermMemory event tracking."""


def test_cancel_event_discards_current_without_persist():
    """cancel_event clears the current tracker without appending to completed."""
    from src.memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    stm.start_event(
        event_id="X", event_title="x", floor=1, act=1,
        hp=50, gold=100, deck=[],
    )
    assert stm.current_event is not None
    stm.cancel_event()
    assert stm.current_event is None
    assert stm.completed_events == []


def test_cancel_event_no_current_is_noop():
    from src.memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    # No start_event called — cancel is a no-op
    stm.cancel_event()
    assert stm.current_event is None
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `pytest tests/test_short_term_event.py -v`
Expected: FAIL with `AttributeError: 'ShortTermMemory' object has no attribute 'cancel_event'`.

- [ ] **Step 4: Add `cancel_event` to ShortTermMemory**

In `src/memory/short_term.py`, in the `ShortTermMemory` class, add this method **immediately after** the existing `end_event` method (around line 852, after `self._current_event = None`):

```python
    def cancel_event(self) -> None:
        """Discard the current event tracker without persisting.

        Used by the extractor to drop stages where every option is a
        mod-flagged ``is_proceed`` closing page — those carry no decision
        signal.
        """
        self._current_event = None
```

- [ ] **Step 5: Run short_term tests**

Run: `pytest tests/test_short_term_event.py -v`
Expected: PASS.

- [ ] **Step 6: Commit the short_term change**

```bash
git add src/memory/short_term.py tests/test_short_term_event.py
git commit -m "feat(short-term): cancel_event() discards current tracker

Prep for the extractor's Proceed-only stage filter: the event tracker
needs a way to roll back without persisting.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

- [ ] **Step 7: Write the extractor integration test**

Append to `tests/test_event_memory_model.py`:

```python
def test_finalize_event_stage_preserves_mod_reward_detail():
    """Verify the extractor captures full mod payload (name + description +
    rarity / rules_text / type). This test simulates the mod's EventOption
    payload shape directly."""
    # Arrange: a simulated upstream event option matching the mod's shape
    from dataclasses import dataclass

    @dataclass
    class _FakeOption:
        index: int
        title: str
        description: str
        effect_description: str
        hp_cost: int | None
        gold_cost: int | None
        is_proceed: bool
        relics_offered: list
        cards_offered: list
        potions_offered: list

    opt = _FakeOption(
        index=2,
        title="Archaic Tooth",
        description="Transform [gold]Neutralize+[/gold] into [gold]Suppress+[/gold].",
        effect_description="Transform Neutralize+ into Suppress+.",
        hp_cost=None, gold_cost=None, is_proceed=False,
        relics_offered=[{
            "name": "Archaic Tooth",
            "description": "Transform a [gold]starter[/gold] card.",
            "rarity": "uncommon",
        }],
        cards_offered=[{
            "name": "Suppress+", "cost": 1, "type": "skill",
            "rules_text": "Apply [red]2 Weak[/red].", "is_upgraded": True,
        }],
        potions_offered=[],
    )

    # The extractor helper we're about to extract from _finalize_event_stage
    # constructs a detail dict. For this test we exercise the dict → Snapshot
    # round-trip using the shape the extractor produces.
    from src.agent.loop import _build_event_option_detail  # ← introduced in this task

    detail = _build_event_option_detail(opt)
    # BBCode stripped
    assert "[gold]" not in detail["description"]
    assert "[gold]" not in detail["relics_offered"][0]["description"]
    assert "[red]" not in detail["cards_offered"][0]["rules_text"]
    # Mod keys preserved (EventOptionSnapshot.from_dict handles the rename)
    assert detail["relics_offered"][0]["rarity"] == "uncommon"
    assert detail["cards_offered"][0]["rules_text"] == "Apply 2 Weak."
    assert detail["cards_offered"][0]["is_upgraded"] is True

    # Round-trip through EventOptionSnapshot
    from src.memory.models_v2 import EventOptionSnapshot
    snap = EventOptionSnapshot.from_dict(detail)
    assert snap.relics_offered[0].description == "Transform a starter card."
    assert snap.relics_offered[0].rarity == "uncommon"
    assert snap.cards_offered[0].upgraded is True
    assert snap.cards_offered[0].card_type == "skill"
    assert snap.cards_offered[0].rules_text == "Apply 2 Weak."


def test_build_event_option_detail_prefers_effect_description():
    """When effect_description is present, it overrides the raw description."""
    from dataclasses import dataclass
    from src.agent.loop import _build_event_option_detail

    @dataclass
    class _O:
        index: int = 0
        title: str = "X"
        description: str = "raw desc"
        effect_description: str = "effect desc"
        hp_cost: int | None = None
        gold_cost: int | None = None
        is_proceed: bool = False
        relics_offered: list = None
        cards_offered: list = None
        potions_offered: list = None

    o = _O(relics_offered=[], cards_offered=[], potions_offered=[])
    detail = _build_event_option_detail(o)
    assert detail["description"] == "effect desc"
```

- [ ] **Step 8: Run tests to verify they fail**

Run: `pytest tests/test_event_memory_model.py::test_finalize_event_stage_preserves_mod_reward_detail tests/test_event_memory_model.py::test_build_event_option_detail_prefers_effect_description -v`
Expected: FAIL with `ImportError: cannot import name '_build_event_option_detail'`.

- [ ] **Step 9: Extract `_build_event_option_detail` and filter Proceed-only**

In `src/agent/loop.py`, find `_finalize_event_stage` (around line 3061). Above it at the module level (or near the top of the `AgentLoop` class as a staticmethod — module level is cleaner for testability), add:

```python
def _build_event_option_detail(option: Any) -> dict:
    """Convert a mod-side EventOption payload into the dict shape
    EventOptionSnapshot.from_dict expects.

    BBCode is stripped from all user-visible text fields. Reward lists
    (relics_offered / cards_offered / potions_offered) are forwarded as
    dicts; downstream EventOptionSnapshot.from_dict handles the mod→Python
    key rename (type→card_type, is_upgraded→upgraded, type→potion_type).

    Bare-string reward entries (legacy or from reduced payloads) are
    wrapped as ``{"name": s}`` so downstream parsing treats them uniformly.
    """
    from src.brain.prompts._deck_fmt import strip_bbcode

    raw_desc = (
        getattr(option, "effect_description", "")
        or getattr(option, "description", "")
    )
    detail: dict = {
        "index": getattr(option, "index", 0),
        "title": strip_bbcode(getattr(option, "title", "") or ""),
        "description": strip_bbcode(raw_desc or ""),
    }
    hp_cost = getattr(option, "hp_cost", None)
    if hp_cost is not None:
        detail["hp_cost"] = hp_cost
    gold_cost = getattr(option, "gold_cost", None)
    if gold_cost is not None:
        detail["gold_cost"] = gold_cost

    def _coerce_reward(item: Any, text_keys: tuple[str, ...]) -> dict:
        if isinstance(item, dict):
            out = dict(item)
            for k in text_keys:
                if k in out and isinstance(out[k], str):
                    out[k] = strip_bbcode(out[k])
            return out
        # Fallback: bare-string name
        return {"name": str(item) if item is not None else ""}

    for src_attr, text_keys in (
        ("relics_offered", ("description",)),
        ("cards_offered", ("rules_text",)),
        ("potions_offered", ("description",)),
    ):
        raw_list = getattr(option, src_attr, None) or []
        if raw_list:
            detail[src_attr] = [_coerce_reward(it, text_keys) for it in raw_list]

    return detail
```

Then replace the inline dict-building loop inside `_finalize_event_stage` (the current lines ~3099-3131) with a call to this helper, and add the Proceed-only filter **before** `stm.end_event(...)`:

```python
        all_details: list[dict] = []
        is_proceed_only = False
        if self._prev_event_gs.event:
            opts = self._prev_event_gs.event.options or []
            if opts and all(getattr(o, "is_proceed", False) for o in opts):
                is_proceed_only = True
            else:
                for o in opts:
                    all_details.append(_build_event_option_detail(o))

        if is_proceed_only:
            logger.debug(
                "Dropping Proceed-only event stage for %s F%d",
                self._prev_event_gs.event.event_id if self._prev_event_gs.event else "?",
                getattr(self._prev_event_gs, "floor", 0),
            )
            stm.cancel_event()
            return

        stm.end_event(
            chosen_index=chosen_index,
            option_text=chosen_text,
            hp_after=gs.player_hp,
            gold_after=gs.gold,
            all_options=all_opts,
            cards_gained=diff["cards_gained"],
            cards_lost=diff["cards_lost"],
            relics_gained=diff["relics_gained"],
            potions_gained=diff["potions_gained"],
            all_option_details=all_details,
        )
```

- [ ] **Step 10: Run all touched tests**

Run: `pytest tests/test_event_memory_model.py tests/test_short_term_event.py tests/test_event_guide_consolidator.py -v`
Expected: PASS.

- [ ] **Step 11: Smoke-test the extractor doesn't break the full loop tests**

Run: `pytest tests/ -k "event or loop" -x --tb=short 2>&1 | tail -40`
Expected: baseline failure count unchanged. Any new failures trace back to the changes and should be investigated before continuing.

- [ ] **Step 12: Commit**

```bash
git add src/agent/loop.py tests/test_event_memory_model.py
git commit -m "feat(event-guide): extractor preserves mod reward payload + drops Proceed-only stages

Extracts _build_event_option_detail helper that: (1) forwards the full
mod EventOption payload (name/description/rarity, name/cost/type/
rules_text/is_upgraded, name/description/type) instead of reducing to
name-only; (2) strips BBCode from all user-visible text at capture time;
(3) prefers effect_description over raw description.

_finalize_event_stage drops stages where every option is mod-flagged
is_proceed — closing pages carry no decision signal. Multi-option stages
containing one 'Proceed' option are unaffected.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

### Task 8: Wire consolidator event branch + retriever injection

**Files:**
- Modify: `src/memory/guide_consolidator.py:1351-1396` (event branch of `consolidate_guides`)
- Modify: `src/memory/retriever.py:610-616` (event guide injection)
- Test: `tests/test_event_guide_consolidator.py`

- [ ] **Step 1: Write the failing test for run-scoped consolidator branch**

Append to `tests/test_event_guide_consolidator.py`:

```python
import pytest


@pytest.mark.asyncio
async def test_consolidate_guides_event_branch_is_run_scoped(monkeypatch):
    """The event branch only refreshes (event_id, character) pairs for current run."""
    from src.memory import guide_consolidator as gc
    from src.memory.models_v2 import EventMemory, EventGuide
    from src.memory.event_store import EventMemoryStore
    from src.memory.guide_store import GuideStore

    # Two runs; only run_A is "current"
    mem_a = EventMemory(
        run_id="run_A", event_id="OROBAS", character="the silent",
        chosen_option_text="Archaic Tooth",
        run_victory=True, run_final_floor=51,
    )
    mem_b = EventMemory(
        run_id="run_B", event_id="DESIGNER", character="the ironclad",
        chosen_option_text="Upgrade",
        run_victory=False, run_final_floor=12,
    )
    mem_a2 = EventMemory(
        run_id="old_A", event_id="OROBAS", character="the silent",
        chosen_option_text="Demon Glass",
        run_victory=True, run_final_floor=55,
    )

    event_store = EventMemoryStore()
    event_store.add_batch([mem_a, mem_b, mem_a2])
    guide_store = GuideStore()

    # Fake memory_manager
    class _MM:
        v2_enabled = True
        combat_store = None
        route_store = None
        card_build_store = None
        event_store = event_store
        guide_store = guide_store

    mm = _MM()

    # Mock the LLM caller
    call_log: list[tuple[str, str]] = []

    async def fake_llm_call(system, prompt, *, think=False, call_type=""):
        # Return a valid response for whatever event_id the prompt mentions.
        # Event ID is the first token after "Event: " in the prompt.
        event_line = next(
            (line for line in prompt.split("\n") if line.startswith("Event:")),
            "",
        )
        # Parse: "Event: OROBAS | Character: the silent | ..."
        event_id = event_line.split()[1] if len(event_line.split()) > 1 else "UNKNOWN"
        call_log.append((event_id, prompt))
        return (
            '{"guide_text": "ok", "confidence": 0.7, "options": []}',
            0.1,
            {"input_tokens": 10, "output_tokens": 5},
        )

    monkeypatch.setattr(
        "src.brain.llm_caller.call_raw", fake_llm_call,
    )

    stats = await gc.consolidate_guides(mm, current_run_id="run_A")

    # Only OROBAS/the silent was refreshed (run_A touched it).
    # DESIGNER/the ironclad is untouched (belonged to run_B).
    refreshed_event_ids = {call[0] for call in call_log}
    assert "OROBAS" in refreshed_event_ids
    assert "DESIGNER" not in refreshed_event_ids
    assert stats["event"] == 1
```

Also add an import at the top of the test file if not already present:

```python
import pytest
```

- [ ] **Step 2: Check for pytest-asyncio marker configuration**

Run: `grep -n "asyncio_mode\|asyncio" pyproject.toml pytest.ini setup.cfg 2>/dev/null | head -5`

If `asyncio_mode = "auto"` is set, you can skip the `@pytest.mark.asyncio` decorator. Otherwise leave it.

Also ensure `pytest-asyncio` is installed by running: `python -c "import pytest_asyncio; print(pytest_asyncio.__version__)" 2>&1 | head -1`. If it errors, check `grep "pytest-asyncio" tests/` or other async tests in the repo for the pattern they use.

- [ ] **Step 3: Run test to verify it fails**

Run: `pytest tests/test_event_guide_consolidator.py::test_consolidate_guides_event_branch_is_run_scoped -v`
Expected: FAIL — current event branch scans all `(event_id, character)` pairs, so `DESIGNER` also gets refreshed.

- [ ] **Step 4: Rewrite the event branch of `consolidate_guides`**

In `src/memory/guide_consolidator.py`, find the `# ── Event guides ─` block (around line 1351). Replace the entire block (from `event_store = getattr(...)` to the closing `exc_info=True,` of the try/except) with:

```python
    # ── Event guides (run-scoped) ────────────────────────────────
    # Only refresh (event_id, character) pairs the current run touched.
    # See docs/superpowers/specs/2026-04-24-event-guide-consolidation-rework-design.md
    event_store = getattr(memory_manager, "event_store", None)
    if event_store:
        all_event_memories = event_store.get_all()
        selected_event_keys = _select_event_keys_for_refresh(
            all_event_memories, current_run_id,
        )

        for (event_id, character) in sorted(selected_event_keys):
            memories = [
                m for m in all_event_memories
                if m.event_id.upper() == event_id
                and normalize_character(m.character) == character
            ]
            if len(memories) < min_episodes:
                continue

            existing = guide_store.get_event_guide(event_id, character)
            prompt = build_event_guide_prompt(event_id, character, memories, existing)
            try:
                raw, _latency, _tokens = await llm_call_raw(
                    EVENT_ANALYST_PROMPT,
                    prompt,
                    think=True,
                    call_type="guide_event",
                )
                guide = parse_event_guide_response(
                    raw,
                    event_id,
                    character,
                    len(memories),
                    memories,
                    existing,
                )
                if guide:
                    guide_store.set_event_guide(guide)
                    stats["event"] += 1
                    logger.info(
                        "Consolidated event guide: %s (%s) v%d "
                        "(%d options, %d memories)",
                        event_id,
                        character,
                        guide.version,
                        len(guide.options),
                        len(memories),
                    )
            except Exception:
                logger.warning(
                    "Event guide consolidation failed for %s",
                    event_id,
                    exc_info=True,
                )
```

- [ ] **Step 5: Run the consolidator test**

Run: `pytest tests/test_event_guide_consolidator.py::test_consolidate_guides_event_branch_is_run_scoped -v`
Expected: PASS.

- [ ] **Step 6: Write the failing retriever test**

First check whether a test file already covers `retriever`:

Run: `ls tests/test_retriever*.py 2>/dev/null`

If a test file exists, append to it; otherwise create `tests/test_event_guide_injection.py`:

```python
"""Retriever-side event guide option library injection tests."""


def test_retriever_event_guide_renders_scored_options(monkeypatch):
    """With a guide that has structured options, the injected block contains
    matching-encounter options sorted by score with analysis lines."""
    from src.memory.models_v2 import EventGuide, EventGuideOption
    from src.memory.retriever import _render_event_guide_block

    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Always a free power spike.",
        options=(
            EventGuideOption(canonical_name="Archaic Tooth", stage_index=0,
                             variant_type="fixed", score=0.7,
                             analysis="Starter upgrade.", sample_size=14),
            EventGuideOption(canonical_name="Demon Glass", stage_index=0,
                             variant_type="random_from_pool", score=0.3,
                             analysis="Deck injection.", sample_size=4),
            EventGuideOption(canonical_name="Never Seen", stage_index=1,
                             variant_type="fixed", score=-0.9,
                             analysis="Bad idea.", sample_size=1),
        ),
        confidence=0.8, version=3,
    )
    current_option_titles = ["Archaic Tooth", "Demon Glass", "Mystery Box"]
    block = _render_event_guide_block(guide, current_option_titles, stage_index=0)

    # Header contains event id + character + version
    assert "OROBAS" in block
    assert "the silent" in block
    assert "v3" in block
    # Takeaway line
    assert "Always a free power spike." in block
    # Both matched options present
    assert "Archaic Tooth" in block
    assert "Demon Glass" in block
    # Unknown option flagged
    assert "Mystery Box" in block
    assert "not in guide" in block
    # Off-stage option excluded
    assert "Never Seen" not in block
    # Ordered by score descending (Archaic first)
    assert block.index("Archaic Tooth") < block.index("Demon Glass")


def test_retriever_event_guide_legacy_without_options():
    """Legacy guides (options=()) fall back to guide_text-only injection."""
    from src.memory.models_v2 import EventGuide
    from src.memory.retriever import _render_event_guide_block

    guide = EventGuide(
        event_id="OROBAS", character="the silent",
        guide_text="Old-format advice.", options=(),
        confidence=0.6, version=1,
    )
    block = _render_event_guide_block(guide, ["Any"], stage_index=0)
    assert "Old-format advice." in block
    # No "Options for this encounter" header when options=()
    assert "Options for this encounter" not in block
```

- [ ] **Step 7: Run test to verify it fails**

Run: `pytest tests/test_event_guide_injection.py -v`
Expected: FAIL with `ImportError: cannot import name '_render_event_guide_block'`.

- [ ] **Step 8: Update retriever**

In `src/memory/retriever.py`, find the event guide block (around line 610-616). Replace:

```python
        # Event guide
        if gs.event:
            event_guide = guide_store.get_event_guide(gs.event.event_id, character)
            if event_guide and event_guide.confidence >= 0.3:
                event_memory_hints.insert(0,
                    f"[Event Guide: {event_guide.event_id}] {event_guide.guide_text}"
                )
```

with:

```python
        # Event guide (scored option library + takeaway)
        if gs.event:
            event_guide = guide_store.get_event_guide(gs.event.event_id, character)
            if event_guide and event_guide.confidence >= 0.3:
                current_option_titles = [
                    getattr(o, "title", "") for o in (gs.event.options or [])
                ]
                # Stage detection: default to 0 for the initial page; if the
                # event is flagged finished (final "Proceed" page), treat as
                # closing and render the whole library as contextual reference.
                stage_index = 0 if not getattr(gs.event, "is_finished", False) else -1
                rendered = _render_event_guide_block(
                    event_guide, current_option_titles, stage_index,
                )
                event_memory_hints.insert(0, rendered)
```

Also add, at the module level of `src/memory/retriever.py` (near the existing imports or helper functions — pick a location adjacent to other `_render_*` or `_format_*` helpers if they exist; otherwise put it right below the existing imports):

```python
def _render_event_guide_block(
    event_guide,
    current_option_titles: list[str],
    stage_index: int,
) -> str:
    """Render an event guide into a scored option library block.

    Filters ``event_guide.options`` to those whose ``stage_index`` matches
    the current stage (or all stages when stage_index == -1), sorts by
    score descending, and marks current-encounter options not found in
    the guide as 'not in guide — new or unseen'.

    Falls back to guide_text only when ``options`` is empty.
    """
    header = (
        f"## Event Guide: {event_guide.event_id} "
        f"({event_guide.character}, v{event_guide.version})"
    )
    lines = [header, event_guide.guide_text]

    if not event_guide.options:
        return "\n".join(lines)

    # Filter by stage (or all stages if stage_index is -1)
    if stage_index < 0:
        stage_options = list(event_guide.options)
    else:
        stage_options = [
            o for o in event_guide.options if o.stage_index == stage_index
        ]
        # Fallback: if nothing matches, show all (better than empty)
        if not stage_options:
            stage_options = list(event_guide.options)

    # Build canonical-name match for current encounter
    guide_names_lower = {
        o.canonical_name.strip().lower(): o for o in stage_options
    }
    seen_titles_lower = {t.strip().lower() for t in current_option_titles}

    matched = [
        o for o in stage_options
        if o.canonical_name.strip().lower() in seen_titles_lower
    ]
    matched.sort(key=lambda o: -o.score)

    unmatched_titles = [
        t for t in current_option_titles
        if t.strip().lower() not in guide_names_lower
    ]

    if matched or unmatched_titles:
        lines.append("")
        lines.append("Options for this encounter (score descending):")
        for o in matched:
            lines.append(
                f"- {o.canonical_name} [{o.variant_type}, "
                f"score {o.score:+.2f}, seen {o.sample_size}x]"
            )
            if o.analysis:
                lines.append(f"  {o.analysis}")
        for t in unmatched_titles:
            lines.append(f'- [Option "{t}" not in guide — new or unseen]')

    return "\n".join(lines)
```

- [ ] **Step 9: Run retriever tests**

Run: `pytest tests/test_event_guide_injection.py -v`
Expected: PASS.

- [ ] **Step 10: Full test sweep**

Run: `pytest tests/ -x --tb=short 2>&1 | tail -30`
Expected: baseline failure count unchanged (a small number of pre-existing failures may exist — they should match what was present before this plan started).

If any test fails that references `event_guide`, `EventGuide`, `EventOptionSnapshot`, or event extraction, investigate the regression before committing.

- [ ] **Step 11: Live smoke validation**

Run: `STS2_POSTRUN_ENABLED=true python -m scripts.run_agent --steps 50 --runs 1 2>&1 | tail -60`

Expected in logs:
- `guide_event` entries appear only for `(event_id, character)` pairs encountered during this single run.
- No `guide_event` entries for characters or event_ids not touched by this run.
- No `TypeError` or `AttributeError` in postrun.

Manually inspect a freshly written `EventGuide` via:

```bash
python -c "
from src.memory.guide_store import GuideStore
from src.storage.paths import guides_json_path
gs = GuideStore.load(guides_json_path())
for g in gs.all_event_guides():
    print(g.event_id, 'v' + str(g.version),
          'options=' + str(len(g.options)),
          'confidence=' + str(g.confidence))
    for o in g.options:
        print(f'  [{o.stage_index}] {o.canonical_name} {o.variant_type} '
              f'score={o.score:+.2f} n={o.sample_size}')
"
```

Expected: at least one guide has `options` populated with `canonical_name` + score + analysis + sample_size matching the recorded encounter count.

- [ ] **Step 12: Commit**

```bash
git add src/memory/guide_consolidator.py src/memory/retriever.py tests/test_event_guide_consolidator.py tests/test_event_guide_injection.py
git commit -m "feat(event-guide): run-scoped consolidation + scored option library injection

Event branch of consolidate_guides now only refreshes (event_id, character)
pairs touched by the current run. Retriever injects a scored option
library filtered to current-encounter options, sorted by score
descending, with 'not in guide' markers for unseen options.

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>"
```

---

## Post-Implementation

After Task 8 commits:

- [ ] **Run final full test suite**: `pytest tests/ --tb=short 2>&1 | tail -10`. Expected: same number of baseline failures as before starting.
- [ ] **Dispatch final code-reviewer subagent** over the entire implementation (all 8 commits) to catch any cross-task inconsistencies.
- [ ] **Use superpowers:finishing-a-development-branch** to wrap up.

---

## Self-Review Checklist (run by controller before dispatch)

**Spec coverage:**
- RewardDetail types (RelicReward/CardReward/PotionReward) → Task 1 ✓
- EventOptionSnapshot upgrade → Task 2 ✓
- EventGuideOption + EventGuide.options → Task 3 ✓
- `_select_event_keys_for_refresh` helper → Task 4 ✓
- `build_event_guide_prompt` rewrite → Task 5 ✓
- `parse_event_guide_response` with server-side sample_size → Task 6 ✓
- Extractor preserves payload + BBCode strip + Proceed-only drop → Task 7 ✓
- Consolidator event branch run-scoped + retriever option injection → Task 8 ✓
- No keyword lookup in pipeline (global glossary handles it) → Covered by design; no task produces keyword injection ✓
- Legacy JSONL backward compat → Task 2 (strings), Task 3 (no options field) ✓
- No extra LLM call → Task 6 folds scoring into guide_event call ✓

**Type consistency:**
- `EventGuideOption.canonical_name` used in Tasks 3, 5, 6, 8 ✓
- `EventGuideOption.sample_size` recomputed in Task 6 via `_count_option_appearances` — matches observed counting in Task 8 retriever display ✓
- `CardReward.card_type` / `.upgraded` used consistently (Task 1 dataclass, Task 2 Snapshot, Task 5 prompt renderer, Task 7 extractor) ✓
- `EventOptionSnapshot.relics_offered`/`cards_offered`/`potions_offered` as tuple[RewardType, ...] used consistently ✓

**Placeholders:** None found.
