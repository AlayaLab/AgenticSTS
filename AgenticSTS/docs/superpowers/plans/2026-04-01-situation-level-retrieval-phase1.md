# Situation-Level Retrieval — Phase 1 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add situation tagging (threat level, intent class, hand capabilities) to combat rounds, enable round-level retrieval from memory, and inject situation-aware exemplars + confidence-gated upcoming patterns into combat prompts.

**Architecture:** New `src/memory/situation.py` module computes `SituationTag` + `HandCapabilityTag` from game state at each combat round start. `CombatRound` model gains an optional `situation_tag` field. `CombatMemoryStore` gains a `query_rounds()` method for two-tier retrieval (hard filter → ranked similarity). `retriever.py` calls it and formats results as structured exemplars. `prompt_injector.py` adds a `## Situation Intel` section with progressive injection (R1 guide-heavy, R2+ situation-heavy).

**Tech Stack:** Python 3.12, frozen dataclasses, no new dependencies. Zero additional API calls.

**Spec:** `docs/2026-03-31-situation-level-retrieval-design.md` Sections 3–11, 14.

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `src/memory/situation.py` | **CREATE** | `HandCapabilityTag`, `SituationTag`, classifiers (`classify_threat`, `classify_intent`, `classify_deck_stage`), `compute_hand_capabilities`, `compute_situation_tag`, `hand_capability_similarity`, `format_round_exemplar`, `format_upcoming_with_confidence` |
| `src/memory/models_v2.py` | MODIFY | Add `situation_tag` + `hand_at_start` fields to `CombatRound`; add `situation_hints` field to `WorkingContext` |
| `src/memory/combat_extractor.py` | MODIFY | Pass `situation_tag` + `hand_at_start` through `_tracker_round_to_frozen` |
| `src/memory/short_term.py` | MODIFY | Add `situation_tag` field to `CombatRoundTracker` |
| `src/memory/combat_store.py` | MODIFY | Add `query_rounds()` two-tier retrieval method |
| `src/memory/retriever.py` | MODIFY | Accept `current_round` kwarg, compute situation, call `query_rounds`, populate `situation_hints` |
| `src/memory/prompt_injector.py` | MODIFY | Add `## Situation Intel` section, progressive injection by round |
| `config.py` | MODIFY | Add 4 situation threshold constants |
| `tests/test_situation.py` | **CREATE** | Unit tests for all classifiers + similarity + exemplar formatting |
| `tests/test_situation_retrieval.py` | **CREATE** | Integration tests for `query_rounds` + retriever situation path |
| `scripts/backfill_situation_tags.py` | **CREATE** | Migration script for existing `combat_episodes.jsonl` |

---

### Task 1: Config Constants

**Files:**
- Modify: `config.py` (after line ~108, after MEMORY_TOTAL_TOKEN_CEILING)

- [ ] **Step 1: Add situation threshold constants to config.py**

```python
# ── Situation Classification ─────────────────────────────────
THREAT_LETHAL_HP_RATIO = float(os.getenv("STS2_THREAT_LETHAL_HP_RATIO", "0.5"))
THREAT_HIGH_DAMAGE = int(os.getenv("STS2_THREAT_HIGH_DAMAGE", "15"))
THREAT_MEDIUM_DAMAGE = int(os.getenv("STS2_THREAT_MEDIUM_DAMAGE", "8"))
UPCOMING_PATTERN_MIN_CONSISTENCY = float(os.getenv("STS2_UPCOMING_MIN_CONSISTENCY", "0.6"))
```

Insert these after `MEMORY_TOTAL_TOKEN_CEILING = 500` (line 108).

- [ ] **Step 2: Commit**

```bash
git add config.py
git commit -m "feat: add situation classification threshold config constants"
```

---

### Task 2: HandCapabilityTag + Classifiers — Tests

**Files:**
- Create: `tests/test_situation.py`
- Create: `src/memory/situation.py`

- [ ] **Step 1: Write failing tests for classify_threat**

```python
# tests/test_situation.py
"""Tests for situation classification and hand capability tagging."""

from src.memory.situation import classify_threat


class TestClassifyThreat:
    def test_lethal_when_effective_damage_over_half_hp(self):
        # 20 incoming, 0 block, 30 HP → effective 20/30 = 67% → lethal
        assert classify_threat(total_incoming=20, current_hp=30, current_block=0) == "lethal"

    def test_high_when_effective_damage_ge_15(self):
        # 18 incoming, 0 block, 80 HP → effective 18 < 50% but >= 15 → high
        assert classify_threat(total_incoming=18, current_hp=80, current_block=0) == "high"

    def test_medium_when_effective_damage_ge_8(self):
        assert classify_threat(total_incoming=10, current_hp=80, current_block=0) == "medium"

    def test_low_when_effective_damage_lt_8(self):
        assert classify_threat(total_incoming=5, current_hp=80, current_block=0) == "low"

    def test_block_reduces_effective_damage(self):
        # 18 incoming, 12 block → effective 6 < 8 → low
        assert classify_threat(total_incoming=18, current_hp=80, current_block=12) == "low"

    def test_zero_incoming_is_low(self):
        assert classify_threat(total_incoming=0, current_hp=50, current_block=0) == "low"

    def test_block_exceeds_incoming(self):
        assert classify_threat(total_incoming=10, current_hp=50, current_block=15) == "low"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation.py::TestClassifyThreat -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'src.memory.situation'`

- [ ] **Step 3: Write classify_threat implementation**

Create `src/memory/situation.py`:

```python
"""Situation classification for combat rounds.

Computes per-round tags (threat level, intent class, hand capabilities,
deck stage) from game state. All local computation — zero API calls.

Spec: docs/2026-03-31-situation-level-retrieval-design.md Sections 4-7.
"""

from __future__ import annotations

import config


def classify_threat(
    total_incoming: int,
    current_hp: int,
    current_block: int,
) -> str:
    """Classify threat level for this round.

    Returns: "lethal" | "high" | "medium" | "low"
    """
    effective_damage = max(0, total_incoming - current_block)
    if current_hp > 0 and effective_damage / current_hp >= config.THREAT_LETHAL_HP_RATIO:
        return "lethal"
    if effective_damage >= config.THREAT_HIGH_DAMAGE:
        return "high"
    if effective_damage >= config.THREAT_MEDIUM_DAMAGE:
        return "medium"
    return "low"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation.py::TestClassifyThreat -v`
Expected: All 7 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/situation.py tests/test_situation.py
git commit -m "feat: add classify_threat with tests"
```

---

### Task 3: classify_intent — Tests + Implementation

**Files:**
- Modify: `tests/test_situation.py`
- Modify: `src/memory/situation.py`

- [ ] **Step 1: Write failing tests for classify_intent**

Append to `tests/test_situation.py`:

```python
from src.memory.situation import classify_intent


class TestClassifyIntent:
    def test_attack_only(self):
        assert classify_intent(["Attack 12", "Attack 6"]) == "attack"

    def test_buff_only(self):
        assert classify_intent(["Buff", "Strength Up"]) == "buff"

    def test_debuff_only(self):
        assert classify_intent(["Debuff", "Apply Weak"]) == "debuff"

    def test_mixed_attack_and_buff(self):
        assert classify_intent(["Attack 12", "Ritual"]) == "mixed"

    def test_mixed_attack_and_debuff(self):
        assert classify_intent(["Attack 8", "Frail"]) == "mixed"

    def test_unknown_when_no_keywords(self):
        assert classify_intent(["LIQUIFY_GROUND_MOVE"]) == "unknown"

    def test_empty_list(self):
        assert classify_intent([]) == "unknown"

    def test_case_insensitive(self):
        assert classify_intent(["attack 12"]) == "attack"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation.py::TestClassifyIntent -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement classify_intent**

Append to `src/memory/situation.py`:

```python
_ATTACK_PATTERNS = {"attack", "strike", "bite", "slash", "thrash", "smash"}
_BUFF_PATTERNS = {"buff", "strength", "ritual", "rage", "grow", "enrage"}
_DEBUFF_PATTERNS = {"debuff", "weak", "vulnerable", "frail", "poison", "curse"}


def classify_intent(intents: list[str]) -> str:
    """Classify round intent pattern from enemy intent strings.

    Returns: "attack" | "buff" | "debuff" | "mixed" | "unknown"
    """
    if not intents:
        return "unknown"
    lowered = " ".join(i.lower() for i in intents)
    has_attack = any(kw in lowered for kw in _ATTACK_PATTERNS)
    has_buff = any(kw in lowered for kw in _BUFF_PATTERNS)
    has_debuff = any(kw in lowered for kw in _DEBUFF_PATTERNS)

    if has_attack and not (has_buff or has_debuff):
        return "attack"
    if has_buff and not has_attack:
        return "buff"
    if has_debuff and not has_attack:
        return "debuff"
    if has_attack:
        return "mixed"
    return "unknown"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation.py::TestClassifyIntent -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/situation.py tests/test_situation.py
git commit -m "feat: add classify_intent with tests"
```

---

### Task 4: HandCapabilityTag + compute_hand_capabilities

**Files:**
- Modify: `tests/test_situation.py`
- Modify: `src/memory/situation.py`

- [ ] **Step 1: Write failing tests for HandCapabilityTag computation**

Append to `tests/test_situation.py`:

```python
from src.memory.situation import HandCapabilityTag, compute_hand_capabilities


def _make_card(
    name: str = "Strike",
    damage: int | None = None,
    block: int | None = None,
    energy_cost: int = 1,
    rules_text: str = "",
    playable: bool = True,
    hits: int | None = None,
    total_damage: int | None = None,
) -> dict:
    """Minimal card dict that mirrors RawCombatHandCardPayload fields."""
    return {
        "name": name,
        "damage": damage,
        "block": block,
        "energy_cost": energy_cost,
        "rules_text": rules_text,
        "playable": playable,
        "hits": hits,
        "total_damage": total_damage,
        "costs_x": False,
    }


class TestComputeHandCapabilities:
    def test_attack_hand(self):
        hand = [
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
            _make_card("Dagger Spray", damage=4, hits=2, total_damage=8),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=10, enemy_hp_lowest=25, energy=3)
        assert tag.attack_count == 3
        assert tag.block_count == 0
        assert tag.total_damage == 20  # 6 + 6 + 4*2
        assert tag.can_deal_12_plus is True
        assert tag.can_kill_this_turn is False  # 20 < 25
        assert tag.has_setup_only is False

    def test_defensive_hand_with_weak(self):
        hand = [
            _make_card("Neutralize", damage=3, rules_text="Apply 1 Weak", energy_cost=0),
            _make_card("Defend", block=5),
            _make_card("Defend+", block=8),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=12, enemy_hp_lowest=40, energy=3)
        assert tag.can_apply_weak is True
        assert tag.can_block_8_plus is True  # 5 + 8 = 13
        assert tag.can_block_full_incoming is True  # 13 >= 12
        assert tag.total_block == 13
        assert tag.zero_cost_count == 1

    def test_setup_only_hand(self):
        hand = [
            _make_card("Footwork", rules_text="Gain 2 Dexterity"),
            _make_card("Accuracy", rules_text="Gain 3 Shiv damage"),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=6, enemy_hp_lowest=40, energy=3)
        assert tag.has_setup_only is True
        assert tag.attack_count == 0
        assert tag.block_count == 0

    def test_draw_detection(self):
        hand = [
            _make_card("Backflip", block=5, rules_text="Draw 2 cards"),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=20, energy=3)
        assert tag.has_draw_or_retain is True

    def test_aoe_detection(self):
        hand = [
            _make_card("Dagger Spray", damage=4, hits=2, rules_text="Deal damage to ALL enemies twice"),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=20, energy=3)
        assert tag.has_aoe is True

    def test_can_kill_this_turn(self):
        hand = [
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
            _make_card("Strike", damage=6),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=15, energy=3)
        assert tag.can_kill_this_turn is True  # 18 >= 15
        assert tag.can_deal_12_plus is True

    def test_vulnerable_detection(self):
        hand = [
            _make_card("Bash", damage=8, rules_text="Apply 2 Vulnerable"),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=5, enemy_hp_lowest=30, energy=3)
        assert tag.can_apply_vulnerable is True

    def test_playable_count(self):
        hand = [
            _make_card("Strike", damage=6, energy_cost=1, playable=True),
            _make_card("Strike", damage=6, energy_cost=1, playable=True),
            _make_card("Carnage", damage=20, energy_cost=2, playable=True),
            _make_card("Bludgeon", damage=32, energy_cost=3, playable=False),
        ]
        tag = compute_hand_capabilities(hand, total_incoming=0, enemy_hp_lowest=50, energy=3)
        assert tag.total_playable == 3  # Bludgeon not playable
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation.py::TestComputeHandCapabilities -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement HandCapabilityTag and compute_hand_capabilities**

Append to `src/memory/situation.py`:

```python
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class HandCapabilityTag:
    """Tactical capabilities of a hand — what can this hand DO.

    Spec: Section 4. Focused on capabilities (can_apply_weak, can_kill)
    rather than static counts. Counts kept for similarity scoring.
    """

    # Defensive capabilities
    can_apply_weak: bool = False
    can_apply_vulnerable: bool = False
    can_block_8_plus: bool = False
    can_block_full_incoming: bool = False

    # Offensive capabilities
    can_deal_12_plus: bool = False
    can_kill_this_turn: bool = False
    has_aoe: bool = False

    # Utility capabilities
    has_draw_or_retain: bool = False
    has_setup_only: bool = False

    # Energy profile
    zero_cost_count: int = 0
    total_playable: int = 0

    # Raw counts (for similarity scoring)
    attack_count: int = 0
    block_count: int = 0
    total_damage: int = 0
    total_block: int = 0

    def to_dict(self) -> dict:
        return {
            "can_apply_weak": self.can_apply_weak,
            "can_apply_vulnerable": self.can_apply_vulnerable,
            "can_block_8_plus": self.can_block_8_plus,
            "can_block_full_incoming": self.can_block_full_incoming,
            "can_deal_12_plus": self.can_deal_12_plus,
            "can_kill_this_turn": self.can_kill_this_turn,
            "has_aoe": self.has_aoe,
            "has_draw_or_retain": self.has_draw_or_retain,
            "has_setup_only": self.has_setup_only,
            "zero_cost_count": self.zero_cost_count,
            "total_playable": self.total_playable,
            "attack_count": self.attack_count,
            "block_count": self.block_count,
            "total_damage": self.total_damage,
            "total_block": self.total_block,
        }

    @classmethod
    def from_dict(cls, d: dict) -> HandCapabilityTag:
        if not d:
            return cls()
        return cls(
            can_apply_weak=d.get("can_apply_weak", False),
            can_apply_vulnerable=d.get("can_apply_vulnerable", False),
            can_block_8_plus=d.get("can_block_8_plus", False),
            can_block_full_incoming=d.get("can_block_full_incoming", False),
            can_deal_12_plus=d.get("can_deal_12_plus", False),
            can_kill_this_turn=d.get("can_kill_this_turn", False),
            has_aoe=d.get("has_aoe", False),
            has_draw_or_retain=d.get("has_draw_or_retain", False),
            has_setup_only=d.get("has_setup_only", False),
            zero_cost_count=d.get("zero_cost_count", 0),
            total_playable=d.get("total_playable", 0),
            attack_count=d.get("attack_count", 0),
            block_count=d.get("block_count", 0),
            total_damage=d.get("total_damage", 0),
            total_block=d.get("total_block", 0),
        )


_WEAK_KW = re.compile(r"weak|虚弱", re.IGNORECASE)
_VULN_KW = re.compile(r"vulnerable|易伤", re.IGNORECASE)
_DRAW_KW = re.compile(r"\bdraw\b|抽|retain|保留", re.IGNORECASE)
_AOE_KW = re.compile(r"all enemies|所有敌人", re.IGNORECASE)


def compute_hand_capabilities(
    hand: list,
    total_incoming: int,
    enemy_hp_lowest: int,
    energy: int,
) -> HandCapabilityTag:
    """Compute tactical capability tag from hand cards.

    Accepts either RawCombatHandCardPayload objects or dicts with the
    same field names (for testing). Zero API calls.
    """
    def _get(card, field, default=None):
        if isinstance(card, dict):
            return card.get(field, default)
        return getattr(card, field, default)

    total_damage = 0
    total_block = 0
    attack_count = 0
    block_count = 0
    can_weak = False
    can_vuln = False
    has_draw = False
    has_aoe = False
    zero_cost = 0
    playable_count = 0

    for c in hand:
        dmg = _get(c, "damage")
        blk = _get(c, "block")
        rules = _get(c, "rules_text", "") or ""
        cost = _get(c, "energy_cost", 1) or 0
        is_playable = _get(c, "playable", True)
        hits = _get(c, "hits")

        if dmg is not None:
            h = hits if (hits is not None and hits > 1) else 1
            total_damage += dmg * h
            attack_count += 1
        if blk is not None:
            total_block += blk
            block_count += 1

        if _WEAK_KW.search(rules):
            can_weak = True
        if _VULN_KW.search(rules):
            can_vuln = True
        if _DRAW_KW.search(rules):
            has_draw = True
        if _AOE_KW.search(rules):
            has_aoe = True

        if cost == 0:
            zero_cost += 1
        if is_playable and cost <= energy:
            playable_count += 1

    setup_only = attack_count == 0 and block_count == 0 and len(hand) > 0

    return HandCapabilityTag(
        can_apply_weak=can_weak,
        can_apply_vulnerable=can_vuln,
        can_block_8_plus=total_block >= 8,
        can_block_full_incoming=total_block >= total_incoming,
        can_deal_12_plus=total_damage >= 12,
        can_kill_this_turn=(total_damage >= enemy_hp_lowest > 0),
        has_aoe=has_aoe,
        has_draw_or_retain=has_draw,
        has_setup_only=setup_only,
        zero_cost_count=zero_cost,
        total_playable=playable_count,
        attack_count=attack_count,
        block_count=block_count,
        total_damage=total_damage,
        total_block=total_block,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation.py::TestComputeHandCapabilities -v`
Expected: All 8 tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/situation.py tests/test_situation.py
git commit -m "feat: add HandCapabilityTag + compute_hand_capabilities with tests"
```

---

### Task 5: classify_deck_stage + hand_capability_similarity + SituationTag

**Files:**
- Modify: `tests/test_situation.py`
- Modify: `src/memory/situation.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_situation.py`:

```python
from src.memory.situation import (
    classify_deck_stage,
    hand_capability_similarity,
    SituationTag,
)


class TestClassifyDeckStage:
    def test_starter_early_floor(self):
        assert classify_deck_stage(floor=3, deck_size=10, has_scaling=False,
                                   has_core_card=False, has_premium_block=False) == "starter"

    def test_building_no_core(self):
        assert classify_deck_stage(floor=10, deck_size=15, has_scaling=False,
                                   has_core_card=False, has_premium_block=False) == "building"

    def test_scaling_has_scaling(self):
        assert classify_deck_stage(floor=15, deck_size=18, has_scaling=True,
                                   has_core_card=True, has_premium_block=False) == "scaling"

    def test_mature_core_and_premium(self):
        assert classify_deck_stage(floor=15, deck_size=18, has_scaling=False,
                                   has_core_card=True, has_premium_block=True) == "scaling"

    def test_building_with_large_deck_no_core(self):
        assert classify_deck_stage(floor=20, deck_size=25, has_scaling=False,
                                   has_core_card=False, has_premium_block=True) == "building"


class TestHandCapabilitySimilarity:
    def test_identical_tags(self):
        tag = HandCapabilityTag(can_apply_weak=True, can_block_8_plus=True)
        score = hand_capability_similarity(tag, tag)
        assert score > 10.0  # all 9 booleans match

    def test_completely_different(self):
        a = HandCapabilityTag(can_apply_weak=True, can_block_full_incoming=True)
        b = HandCapabilityTag(can_apply_weak=False, can_block_full_incoming=False,
                              can_kill_this_turn=True)
        score = hand_capability_similarity(a, b)
        # Some booleans still match (both False for many fields)
        assert score > 0.0

    def test_symmetric(self):
        a = HandCapabilityTag(can_apply_weak=True)
        b = HandCapabilityTag(can_apply_vulnerable=True)
        assert hand_capability_similarity(a, b) == hand_capability_similarity(b, a)


class TestSituationTag:
    def test_to_dict_round_trip(self):
        tag = SituationTag(
            threat_level="high",
            intent_class="attack",
            threat_window="burst",
            deck_stage="building",
            damage_taken=12,
            outcome_quality="bad",
            cards_that_helped=("Defend",),
            next_round_window="recovery",
            hand_capabilities=HandCapabilityTag(can_apply_weak=True),
        )
        d = tag.to_dict()
        restored = SituationTag.from_dict(d)
        assert restored.threat_level == "high"
        assert restored.intent_class == "attack"
        assert restored.hand_capabilities is not None
        assert restored.hand_capabilities.can_apply_weak is True
        assert restored.cards_that_helped == ("Defend",)

    def test_none_hand_capabilities(self):
        tag = SituationTag(threat_level="low")
        d = tag.to_dict()
        restored = SituationTag.from_dict(d)
        assert restored.hand_capabilities is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation.py -k "DeckStage or Similarity or SituationTag" -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement classify_deck_stage, hand_capability_similarity, SituationTag**

Append to `src/memory/situation.py`:

```python
from typing import Any


def classify_deck_stage(
    floor: int,
    deck_size: int,
    has_scaling: bool,
    has_core_card: bool,
    has_premium_block: bool,
) -> str:
    """Classify deck development stage.

    Uses composite signal: floor + deck_size + card quality.
    Returns: "starter" | "building" | "scaling" | "mature"
    """
    if floor <= 5 and deck_size <= 12:
        return "starter"
    if not has_core_card and not has_scaling:
        return "building"
    if has_scaling or (has_core_card and has_premium_block):
        return "scaling"
    return "mature"


_CAPABILITY_WEIGHTS: dict[str, float] = {
    "can_apply_weak": 1.5,
    "can_apply_vulnerable": 1.0,
    "can_block_full_incoming": 2.0,
    "can_block_8_plus": 1.0,
    "can_deal_12_plus": 1.0,
    "can_kill_this_turn": 2.5,
    "has_aoe": 1.0,
    "has_draw_or_retain": 0.5,
    "has_setup_only": 1.5,
}


def hand_capability_similarity(a: HandCapabilityTag, b: HandCapabilityTag) -> float:
    """Weighted overlap of boolean capabilities. Range: 0.0 - ~12.0."""
    score = 0.0
    for field_name, weight in _CAPABILITY_WEIGHTS.items():
        if getattr(a, field_name) == getattr(b, field_name):
            score += weight
    return score


def _adjacent_threat(a: str, b: str) -> bool:
    """Check if two threat levels are adjacent (one step apart)."""
    order = ["low", "medium", "high", "lethal"]
    try:
        return abs(order.index(a) - order.index(b)) == 1
    except ValueError:
        return False


@dataclass(frozen=True)
class SituationTag:
    """Per-round situation tag for memory retrieval.

    Spec: Section 7. Attached to each CombatRound.
    """

    threat_level: str = "medium"
    intent_class: str = "unknown"
    threat_window: str = ""
    hand_capabilities: HandCapabilityTag | None = None
    deck_stage: str = ""
    damage_taken: int = 0
    outcome_quality: str = ""
    cards_that_helped: tuple[str, ...] = ()
    next_round_window: str = ""

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "threat_level": self.threat_level,
            "intent_class": self.intent_class,
        }
        if self.threat_window:
            d["threat_window"] = self.threat_window
        if self.hand_capabilities is not None:
            d["hand_capabilities"] = self.hand_capabilities.to_dict()
        if self.deck_stage:
            d["deck_stage"] = self.deck_stage
        if self.damage_taken:
            d["damage_taken"] = self.damage_taken
        if self.outcome_quality:
            d["outcome_quality"] = self.outcome_quality
        if self.cards_that_helped:
            d["cards_that_helped"] = list(self.cards_that_helped)
        if self.next_round_window:
            d["next_round_window"] = self.next_round_window
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SituationTag:
        if not d:
            return cls()
        hc_raw = d.get("hand_capabilities")
        return cls(
            threat_level=d.get("threat_level", "medium"),
            intent_class=d.get("intent_class", "unknown"),
            threat_window=d.get("threat_window", ""),
            hand_capabilities=HandCapabilityTag.from_dict(hc_raw) if hc_raw else None,
            deck_stage=d.get("deck_stage", ""),
            damage_taken=d.get("damage_taken", 0),
            outcome_quality=d.get("outcome_quality", ""),
            cards_that_helped=tuple(d.get("cards_that_helped", ())),
            next_round_window=d.get("next_round_window", ""),
        )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/situation.py tests/test_situation.py
git commit -m "feat: add classify_deck_stage, SituationTag, hand_capability_similarity"
```

---

### Task 6: CombatRound + CombatRoundTracker + WorkingContext Model Changes

**Files:**
- Modify: `src/memory/models_v2.py` (CombatRound class, ~line 266; WorkingContext class, ~line 910)
- Modify: `src/memory/short_term.py` (CombatRoundTracker, ~line 26)
- Modify: `src/memory/combat_extractor.py` (_tracker_round_to_frozen, ~line 26)

- [ ] **Step 1: Add situation_tag + hand_at_start to CombatRound in models_v2.py**

In `CombatRound` (line 266), add two fields after `events`:

```python
    events: tuple[CombatDelta, ...] = ()  # per-action state deltas
    hand_at_start: tuple[str, ...] = ()        # cards in hand at round start (for backfill)
    situation_tag: SituationTag | None = None   # per-round situation classification
```

Add import at top of `models_v2.py`:

```python
from src.memory.situation import SituationTag
```

Update `CombatRound.to_dict()` — after the events block (line 297-298), add:

```python
        if self.hand_at_start:
            d["hand_at_start"] = list(self.hand_at_start)
        if self.situation_tag is not None:
            d["situation_tag"] = self.situation_tag.to_dict()
```

Update `CombatRound.from_dict()` — add to the constructor call:

```python
            hand_at_start=tuple(d.get("hand_at_start", ())),
            situation_tag=SituationTag.from_dict(st) if (st := d.get("situation_tag")) else None,
```

- [ ] **Step 2: Add situation_tag to CombatRoundTracker in short_term.py**

In `CombatRoundTracker` (line 26), add after `hand_at_start`:

```python
    situation_tag: SituationTag | None = None   # computed at round start
```

Add import at top of `short_term.py`:

```python
from src.memory.situation import SituationTag
```

- [ ] **Step 3: Pass new fields through in combat_extractor.py**

Update `_tracker_round_to_frozen` (line 26) to pass the new fields:

```python
def _tracker_round_to_frozen(r) -> CombatRound:
    """Convert a mutable CombatRoundTracker to a frozen CombatRound."""
    return CombatRound(
        round_num=r.round_num,
        energy_available=r.energy_available,
        energy_used=r.energy_used,
        hp_start=r.hp_start,
        hp_end=r.hp_end,
        block_gained=r.block_gained,
        enemy_intents=tuple(r.enemy_intents),
        cards_played=tuple(r.cards_played),
        potions_used=tuple(r.potions_used),
        damage_dealt=r.damage_dealt,
        damage_taken=r.damage_taken,
        events=tuple(r.events),
        hand_at_start=tuple(r.hand_at_start),
        situation_tag=r.situation_tag,
    )
```

- [ ] **Step 4: Add situation_hints to WorkingContext in models_v2.py**

In `WorkingContext` (line 910), add after `rule_ids`:

```python
    # Situation-level exemplars (formatted past rounds)
    situation_hints: tuple[str, ...] = ()
```

Update `is_empty` (line 932) — add `self.situation_hints` to the `any()` tuple.

Update `total_hints` (line 944) — add `+ len(self.situation_hints)`.

Update `estimated_tokens` (line 954) — add `self.situation_hints` to the `for` loop tuple.

- [ ] **Step 5: Verify existing tests still pass**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: All existing tests PASS (new fields have defaults, backward compatible)

- [ ] **Step 6: Commit**

```bash
git add src/memory/models_v2.py src/memory/short_term.py src/memory/combat_extractor.py
git commit -m "feat: add situation_tag + hand_at_start to CombatRound, situation_hints to WorkingContext"
```

---

### Task 7: query_rounds in CombatMemoryStore

**Files:**
- Create: `tests/test_situation_retrieval.py`
- Modify: `src/memory/combat_store.py`

- [ ] **Step 1: Write failing tests for query_rounds**

```python
# tests/test_situation_retrieval.py
"""Tests for situation-level round retrieval from combat memory store."""

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.memory.situation import HandCapabilityTag, SituationTag


def _make_round(
    round_num: int = 1,
    threat_level: str = "medium",
    intent_class: str = "attack",
    can_weak: bool = False,
    damage_taken: int = 5,
    outcome: str = "acceptable",
    cards: tuple[str, ...] = ("Strike",),
) -> CombatRound:
    tag = SituationTag(
        threat_level=threat_level,
        intent_class=intent_class,
        hand_capabilities=HandCapabilityTag(can_apply_weak=can_weak),
        damage_taken=damage_taken,
        outcome_quality=outcome,
    )
    return CombatRound(
        round_num=round_num,
        enemy_intents=("Attack 12",),
        cards_played=cards,
        damage_taken=damage_taken,
        situation_tag=tag,
    )


def _make_episode(
    enemy_key: str = "Fuzzy Wurm",
    character: str = "the silent",
    rounds: tuple[CombatRound, ...] = (),
) -> CombatEpisode:
    return CombatEpisode(
        enemy_key=enemy_key,
        character=character,
        combat_type="monster",
        rounds=rounds,
        run_id="test_run",
    )


class TestQueryRounds:
    def test_returns_matching_rounds(self):
        store = CombatMemoryStore()
        r = _make_round(threat_level="high", intent_class="attack", can_weak=True,
                        damage_taken=3, outcome="clean", cards=("Neutralize", "Defend"))
        store.add(_make_episode(rounds=(r,)))

        query_sit = SituationTag(
            threat_level="high",
            intent_class="attack",
            hand_capabilities=HandCapabilityTag(can_apply_weak=True),
        )
        results = store.query_rounds("Fuzzy Wurm", "the silent", query_sit, limit=3)
        assert len(results) == 1
        rnd, tag, score = results[0]
        assert rnd.cards_played == ("Neutralize", "Defend")
        assert score > 0

    def test_filters_by_enemy_key(self):
        store = CombatMemoryStore()
        r = _make_round()
        store.add(_make_episode(enemy_key="Nibbit", rounds=(r,)))

        query_sit = SituationTag(threat_level="medium", intent_class="attack")
        results = store.query_rounds("Fuzzy Wurm", "the silent", query_sit)
        assert len(results) == 0  # wrong enemy

    def test_skips_rounds_without_tags(self):
        store = CombatMemoryStore()
        r = CombatRound(round_num=1, enemy_intents=("Attack 12",), cards_played=("Strike",))
        store.add(_make_episode(rounds=(r,)))

        query_sit = SituationTag(threat_level="medium", intent_class="attack")
        results = store.query_rounds("Fuzzy Wurm", "the silent", query_sit)
        assert len(results) == 0  # no tag → skipped

    def test_prefers_clean_outcomes(self):
        store = CombatMemoryStore()
        r_clean = _make_round(damage_taken=0, outcome="clean", cards=("Neutralize",))
        r_bad = _make_round(damage_taken=15, outcome="disaster", cards=("Strike",))
        store.add(_make_episode(rounds=(r_clean, r_bad)))

        query_sit = SituationTag(threat_level="medium", intent_class="attack")
        results = store.query_rounds("Fuzzy Wurm", "the silent", query_sit, limit=2)
        assert len(results) == 2
        # clean outcome should score higher
        assert results[0][0].cards_played == ("Neutralize",)

    def test_deduplicates_by_intent_threat_cards(self):
        store = CombatMemoryStore()
        r1 = _make_round(cards=("Strike", "Defend"))
        r2 = _make_round(cards=("Strike", "Defend"))  # same dedup key
        r3 = _make_round(cards=("Neutralize", "Backflip"))  # different
        store.add(_make_episode(rounds=(r1, r2, r3)))

        query_sit = SituationTag(threat_level="medium", intent_class="attack")
        results = store.query_rounds("Fuzzy Wurm", "the silent", query_sit, limit=3)
        assert len(results) == 2  # r1 and r2 deduped into one
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation_retrieval.py -v`
Expected: FAIL — `query_rounds` does not exist

- [ ] **Step 3: Implement query_rounds in combat_store.py**

Add to `src/memory/combat_store.py`, after the existing `query()` method (line ~114):

```python
    def query_rounds(
        self,
        enemy_key: str,
        character: str,
        situation: SituationTag,
        limit: int = 3,
    ) -> list[tuple[CombatRound, SituationTag, float]]:
        """Retrieve past rounds matching the current situation.

        Two-tier retrieval:
        1. Hard filter: enemy_key + character
        2. Ranked: threat_level, intent_class, hand_capability, deck_stage, outcome

        Returns: list of (round, tag, similarity_score) sorted by score desc.
        """
        from src.memory.situation import _adjacent_threat, hand_capability_similarity

        candidates: list[tuple[CombatRound, SituationTag, float]] = []

        with self._lock:
            for ep in self._episodes:
                # Hard filter
                if ep.enemy_key.lower() != enemy_key.lower():
                    continue
                if character and ep.character.lower() != character.lower():
                    continue

                for rnd in ep.rounds:
                    tag = rnd.situation_tag
                    if tag is None:
                        continue

                    score = 0.0

                    # Strong ranking: threat + intent + hand capabilities
                    if tag.threat_level == situation.threat_level:
                        score += 2.0
                    elif _adjacent_threat(tag.threat_level, situation.threat_level):
                        score += 0.5

                    if tag.intent_class == situation.intent_class:
                        score += 1.5

                    if tag.hand_capabilities and situation.hand_capabilities:
                        score += hand_capability_similarity(
                            tag.hand_capabilities, situation.hand_capabilities
                        ) * 0.15

                    # Weak ranking
                    if tag.deck_stage and situation.deck_stage and tag.deck_stage == situation.deck_stage:
                        score += 0.5

                    # Prefer rounds with clean outcomes
                    if tag.outcome_quality == "clean":
                        score += 0.5
                    elif tag.outcome_quality == "acceptable":
                        score += 0.2

                    candidates.append((rnd, tag, score))

        candidates.sort(key=lambda x: x[2], reverse=True)
        return self._deduplicate_rounds(candidates, limit)

    @staticmethod
    def _deduplicate_rounds(
        candidates: list[tuple[CombatRound, SituationTag, float]],
        limit: int,
    ) -> list[tuple[CombatRound, SituationTag, float]]:
        """Deduplicate by (intent_class, threat_level, top-3-cards)."""
        seen: set[tuple] = set()
        result: list[tuple[CombatRound, SituationTag, float]] = []
        for rnd, tag, score in candidates:
            dedup_key = (
                tag.intent_class,
                tag.threat_level,
                tuple(sorted(rnd.cards_played[:3])),
            )
            if dedup_key in seen:
                continue
            seen.add(dedup_key)
            result.append((rnd, tag, score))
            if len(result) >= limit:
                break
        return result
```

Add imports at top of `combat_store.py`:

```python
from src.memory.situation import SituationTag
```

And add `CombatRound` to the existing import from `models_v2`:

```python
from src.memory.models_v2 import CombatEpisode, CombatRound
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation_retrieval.py -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Run all existing tests to check no regressions**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add src/memory/combat_store.py tests/test_situation_retrieval.py
git commit -m "feat: add query_rounds() for situation-level round retrieval"
```

---

### Task 8: format_round_exemplar + format_upcoming_with_confidence

**Files:**
- Modify: `tests/test_situation.py`
- Modify: `src/memory/situation.py`

- [ ] **Step 1: Write failing tests**

Append to `tests/test_situation.py`:

```python
from src.memory.situation import format_round_exemplar, format_upcoming_with_confidence


class TestFormatRoundExemplar:
    def test_basic_format(self):
        tag = SituationTag(
            threat_level="high",
            intent_class="attack",
            hand_capabilities=HandCapabilityTag(can_apply_weak=True, can_block_8_plus=True),
            damage_taken=5,
            outcome_quality="acceptable",
            next_round_window="recovery",
        )
        rnd = CombatRound(
            round_num=3,
            enemy_intents=("Attack 18",),
            cards_played=("Neutralize", "Defend+", "Defend"),
            damage_taken=5,
        )
        text = format_round_exemplar(rnd, tag, 7.2)
        assert "7.2" in text
        assert "Attack 18" in text
        assert "can_apply_weak" in text
        assert "Neutralize" in text
        assert "5 HP lost" in text
        assert "recovery" in text

    def test_no_hand_capabilities(self):
        tag = SituationTag(threat_level="low", intent_class="buff")
        rnd = CombatRound(round_num=1, enemy_intents=("Buff",), cards_played=("Strike",))
        text = format_round_exemplar(rnd, tag, 3.0)
        assert "Hand capabilities" not in text  # no caps to show


class TestFormatUpcomingWithConfidence:
    def test_consistent_pattern(self):
        from src.memory.models_v2 import CombatEpisode, CombatRound
        r1 = CombatRound(round_num=1, enemy_intents=("Attack 12",))
        r2_atk = CombatRound(round_num=2, enemy_intents=("Attack 8",))
        r2_buf = CombatRound(round_num=2, enemy_intents=("Buff",))
        # 2 out of 3 episodes have attack at R2 → 67%
        ep1 = CombatEpisode(rounds=(r1, r2_atk), enemy_key="X", character="Y")
        ep2 = CombatEpisode(rounds=(r1, r2_atk), enemy_key="X", character="Y")
        ep3 = CombatEpisode(rounds=(r1, r2_buf), enemy_key="X", character="Y")

        result = format_upcoming_with_confidence([ep1, ep2, ep3], current_round=1)
        assert "R2" in result
        assert "attack" in result.lower()
        assert "67%" in result

    def test_below_threshold_returns_empty(self):
        from src.memory.models_v2 import CombatEpisode, CombatRound
        r1 = CombatRound(round_num=1, enemy_intents=("Attack 12",))
        r2a = CombatRound(round_num=2, enemy_intents=("Attack 8",))
        r2b = CombatRound(round_num=2, enemy_intents=("Buff",))
        r2c = CombatRound(round_num=2, enemy_intents=("Debuff",))
        # All different → no consistency
        ep1 = CombatEpisode(rounds=(r1, r2a), enemy_key="X", character="Y")
        ep2 = CombatEpisode(rounds=(r1, r2b), enemy_key="X", character="Y")
        ep3 = CombatEpisode(rounds=(r1, r2c), enemy_key="X", character="Y")

        result = format_upcoming_with_confidence([ep1, ep2, ep3], current_round=1)
        assert result == ""

    def test_too_few_episodes(self):
        from src.memory.models_v2 import CombatEpisode, CombatRound
        r1 = CombatRound(round_num=1, enemy_intents=("Attack 12",))
        r2 = CombatRound(round_num=2, enemy_intents=("Attack 8",))
        ep = CombatEpisode(rounds=(r1, r2), enemy_key="X", character="Y")
        result = format_upcoming_with_confidence([ep], current_round=1)
        assert result == ""  # need >= 2 episodes
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_situation.py -k "Exemplar or Upcoming" -v`
Expected: FAIL — `ImportError`

- [ ] **Step 3: Implement both formatters**

Append to `src/memory/situation.py`:

```python
from collections import Counter as _Counter


def format_round_exemplar(
    rnd: Any,  # CombatRound
    tag: SituationTag,
    score: float,
) -> str:
    """Format a past round as a structured exemplar for LLM prompt.

    Spec: Section 10.
    """
    lines: list[str] = []
    lines.append(f"### Similar Past Situation (relevance: {score:.1f})")

    intent_str = ", ".join(rnd.enemy_intents) if rnd.enemy_intents else "unknown"
    lines.append(f"- Intent: {intent_str} ({tag.intent_class}, {tag.threat_level} threat)")

    if tag.hand_capabilities:
        caps: list[str] = []
        hc = tag.hand_capabilities
        if hc.can_apply_weak:
            caps.append("can_apply_weak")
        if hc.can_apply_vulnerable:
            caps.append("can_apply_vulnerable")
        if hc.can_block_full_incoming:
            caps.append("can_block_full")
        elif hc.can_block_8_plus:
            caps.append("can_block_8+")
        if hc.can_kill_this_turn:
            caps.append("CAN_KILL")
        if hc.has_setup_only:
            caps.append("setup_only_hand")
        if hc.has_draw_or_retain:
            caps.append("has_draw")
        if caps:
            lines.append(f"- Hand capabilities: {', '.join(caps)}")

    cards = ", ".join(rnd.cards_played) if rnd.cards_played else "none"
    lines.append(f"- Played: [{cards}]")

    lines.append(f"- Result: {tag.damage_taken} HP lost ({tag.outcome_quality})")

    if tag.next_round_window:
        lines.append(f"- Next round: {tag.next_round_window}")

    return "\n".join(lines)


def format_upcoming_with_confidence(
    episodes: list,  # list[CombatEpisode]
    current_round: int,
    min_consistency: float | None = None,
) -> str:
    """Format upcoming enemy patterns with confidence threshold.

    Only injects when consistency >= threshold across episodes.
    Spec: Section 8.
    """
    if min_consistency is None:
        min_consistency = config.UPCOMING_PATTERN_MIN_CONSISTENCY
    if not episodes or len(episodes) < 2:
        return ""

    next_intents: list[str] = []
    for ep in episodes:
        next_rounds = [r for r in ep.rounds if r.round_num == current_round + 1]
        if next_rounds:
            nxt = next_rounds[0]
            tag = getattr(nxt, "situation_tag", None)
            if tag and tag.intent_class != "unknown":
                next_intents.append(tag.intent_class)
            else:
                next_intents.append(classify_intent(list(nxt.enemy_intents)))

    if not next_intents:
        return ""

    counts = _Counter(next_intents)
    most_common_class, most_common_count = counts.most_common(1)[0]
    consistency = most_common_count / len(next_intents)

    if consistency < min_consistency:
        return ""

    confidence_pct = int(consistency * 100)
    return (
        f"Likely R{current_round + 1}: {most_common_class} "
        f"({confidence_pct}% consistent across {len(next_intents)} past fights)"
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_situation.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/memory/situation.py tests/test_situation.py
git commit -m "feat: add format_round_exemplar + format_upcoming_with_confidence"
```

---

### Task 9: Retriever — Situation-Aware Combat Retrieval

**Files:**
- Modify: `src/memory/retriever.py`

- [ ] **Step 1: Add current_round parameter and situation retrieval to query_for_decision**

In `query_for_decision()` (line 113), add `current_round: int = 0` to the keyword arguments:

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
    archetype: str = "",
    current_round: int = 0,  # NEW: for situation-aware retrieval
) -> WorkingContext:
```

Add a new `situation_hints` list alongside the existing hint lists (after line 148):

```python
    situation_hints: list[str] = []
```

In the `if decision_type == "combat":` block (line 150), after the existing enemy pattern retrieval (line 176), add:

```python
        # 2b. Situation-level round retrieval (NEW)
        if current_round > 0:
            from src.memory.situation import (
                classify_intent,
                classify_threat,
                format_round_exemplar,
                format_upcoming_with_confidence,
                SituationTag,
            )
            from src.brain.prompts._intent_fmt import compute_total_incoming

            # Compute current situation
            total_incoming = compute_total_incoming(gs.enemies) if gs.enemies else 0
            current_hp = gs.hp or 0
            current_block = gs.block or 0
            intent_strings = []
            for e in (gs.enemies or []):
                for intent in e.intents:
                    intent_strings.append(str(intent.label or intent.intent_type or ""))

            current_situation = SituationTag(
                threat_level=classify_threat(total_incoming, current_hp, current_block),
                intent_class=classify_intent(intent_strings),
            )

            similar_rounds = combat_store.query_rounds(
                enemy_key=enemy_key,
                character=character,
                situation=current_situation,
                limit=3 if current_round > 1 else 1,
            )
            for rnd, tag, score in similar_rounds:
                situation_hints.append(format_round_exemplar(rnd, tag, score))

            # Confidence-gated upcoming patterns
            upcoming = format_upcoming_with_confidence(episodes, current_round)
            if upcoming:
                situation_hints.append(upcoming)
```

Update the `WorkingContext` construction (line 273) to include `situation_hints`:

```python
    wc = WorkingContext(
        combat_guide_hints=tuple(combat_guide_hints),
        enemy_pattern_hints=tuple(enemy_pattern_hints),
        route_guide_hints=tuple(route_guide_hints),
        route_memory_hints=tuple(route_memory_hints),
        deck_guide_hints=tuple(deck_guide_hints),
        deck_memory_hints=tuple(deck_memory_hints),
        card_memory_hints=tuple(card_memory_hints),
        short_term_hints=tuple(short_term_hints),
        rule_hints=tuple(rule_hints),
        rule_ids=tuple(rule_ids),
        situation_hints=tuple(situation_hints),  # NEW
    )
```

Update `_trim_working_context` (line 304) — add `situation_hints` between `enemy_pattern_hints` and `short_term_hints` in the priority list:

```python
        ("situation_hints", wc.situation_hints),  # medium-high priority
```

And add to the return constructor:

```python
        situation_hints=kept.get("situation_hints", ()),
```

- [ ] **Step 2: Run existing tests to verify no regression**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: All PASS (new kwarg has default, backward compatible)

- [ ] **Step 3: Commit**

```bash
git add src/memory/retriever.py
git commit -m "feat: add situation-aware combat retrieval to query_for_decision"
```

---

### Task 10: Prompt Injector — Situation Intel Section

**Files:**
- Modify: `src/memory/prompt_injector.py`

- [ ] **Step 1: Add Situation Intel section to format_working_context**

In `format_working_context()`, add the situation intel section BEFORE the existing combat domain block (before line 27). The new section should come first because it's the most relevant at R2+:

```python
    # Situation intel (highest priority at R2+)
    if wc.situation_hints:
        parts.append("## Situation Intel")
        parts.append("*Adapt to your CURRENT hand and threat level.*\n")
        for hint in wc.situation_hints:
            parts.append(hint)
        parts.append("")
```

- [ ] **Step 2: Run existing tests**

Run: `python -m pytest tests/ -x -q --timeout=30`
Expected: All PASS

- [ ] **Step 3: Commit**

```bash
git add src/memory/prompt_injector.py
git commit -m "feat: add Situation Intel section to prompt injection"
```

---

### Task 11: Backfill Script

**Files:**
- Create: `scripts/backfill_situation_tags.py`

- [ ] **Step 1: Create the migration script**

```python
#!/usr/bin/env python3
"""Backfill SituationTag onto existing combat_episodes.jsonl.

Computes threat_level and intent_class from existing round data.
hand_capabilities is set to None (no hand_at_start data in old episodes).
outcome_quality computed from damage_taken.

Usage:
    python -m scripts.backfill_situation_tags [--dry-run]
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Ensure project root is on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.memory.models_v2 import CombatEpisode
from src.memory.situation import SituationTag, classify_intent, classify_threat


def _classify_outcome(damage_taken: int) -> str:
    if damage_taken == 0:
        return "clean"
    if damage_taken < 8:
        return "acceptable"
    if damage_taken < 15:
        return "bad"
    return "disaster"


def backfill_episode(ep_dict: dict) -> dict:
    """Add situation_tag to each round in an episode dict."""
    rounds = ep_dict.get("rounds", [])
    updated_rounds = []

    for i, rnd in enumerate(rounds):
        if rnd.get("situation_tag"):
            updated_rounds.append(rnd)
            continue

        # Compute tag from existing data
        intents = rnd.get("enemy_intents", [])
        damage_taken = rnd.get("damage_taken", 0)
        hp_start = rnd.get("hp_start", 0)

        # Approximate total_incoming from intent strings
        total_incoming = 0
        for intent_str in intents:
            # Try to extract "Attack N" pattern
            import re
            m = re.search(r"(?:attack|Attack)\s*(\d+)", intent_str, re.IGNORECASE)
            if m:
                total_incoming += int(m.group(1))

        tag = SituationTag(
            threat_level=classify_threat(total_incoming, hp_start, 0),
            intent_class=classify_intent(intents),
            hand_capabilities=None,  # no hand data in old episodes
            damage_taken=damage_taken,
            outcome_quality=_classify_outcome(damage_taken),
        )

        # Fill next_round_window from following round
        if i + 1 < len(rounds):
            next_intents = rounds[i + 1].get("enemy_intents", [])
            next_ic = classify_intent(next_intents)
            if next_ic in ("buff", "debuff"):
                tag = SituationTag(
                    threat_level=tag.threat_level,
                    intent_class=tag.intent_class,
                    hand_capabilities=tag.hand_capabilities,
                    deck_stage=tag.deck_stage,
                    damage_taken=tag.damage_taken,
                    outcome_quality=tag.outcome_quality,
                    cards_that_helped=tag.cards_that_helped,
                    next_round_window="setup" if next_ic == "buff" else "debuff",
                )

        rnd["situation_tag"] = tag.to_dict()
        updated_rounds.append(rnd)

    ep_dict["rounds"] = updated_rounds
    return ep_dict


def main():
    dry_run = "--dry-run" in sys.argv
    path = Path("data/memory/v2/combat_episodes.jsonl")

    if not path.exists():
        print(f"File not found: {path}")
        return

    lines = path.read_text(encoding="utf-8").strip().split("\n")
    print(f"Processing {len(lines)} episodes...")

    updated_lines = []
    tagged_rounds = 0
    total_rounds = 0

    for line in lines:
        if not line.strip():
            continue
        ep_dict = json.loads(line)
        total_rounds += len(ep_dict.get("rounds", []))
        updated = backfill_episode(ep_dict)
        tagged_rounds += sum(
            1 for r in updated.get("rounds", []) if r.get("situation_tag")
        )
        updated_lines.append(json.dumps(updated, ensure_ascii=False))

    print(f"Tagged {tagged_rounds}/{total_rounds} rounds")

    if dry_run:
        print("[DRY RUN] No changes written")
    else:
        path.write_text("\n".join(updated_lines) + "\n", encoding="utf-8")
        print(f"Written to {path}")


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Test with dry-run**

Run: `python -m scripts.backfill_situation_tags --dry-run`
Expected: Prints count of episodes processed and rounds tagged, no file changes

- [ ] **Step 3: Run actual backfill**

Run: `python -m scripts.backfill_situation_tags`
Expected: Rewrites `data/memory/v2/combat_episodes.jsonl` with tags

- [ ] **Step 4: Verify backfilled data loads**

Run: `python -c "from src.memory.combat_store import CombatMemoryStore; import json; from pathlib import Path; from src.memory.models_v2 import CombatEpisode; lines = Path('data/memory/v2/combat_episodes.jsonl').read_text().strip().split('\\n'); eps = [CombatEpisode.from_dict(json.loads(l)) for l in lines if l.strip()]; tagged = sum(1 for ep in eps for r in ep.rounds if r.situation_tag); print(f'{tagged} tagged rounds across {len(eps)} episodes')"`
Expected: Non-zero tagged count

- [ ] **Step 5: Commit**

```bash
git add scripts/backfill_situation_tags.py
git commit -m "feat: add backfill script for situation tags on existing combat episodes"
```

---

### Task 12: Final Integration Verification

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=60`
Expected: All tests PASS, including new `test_situation.py` and `test_situation_retrieval.py`

- [ ] **Step 2: Verify no import cycles**

Run: `python -c "from src.memory.situation import SituationTag, HandCapabilityTag, classify_threat, classify_intent, classify_deck_stage, compute_hand_capabilities, hand_capability_similarity, format_round_exemplar, format_upcoming_with_confidence; print('All imports OK')"`
Expected: `All imports OK`

- [ ] **Step 3: Verify backward compatibility with old episodes**

Run: `python -c "import json; from src.memory.models_v2 import CombatRound; r = CombatRound.from_dict({'round_num': 1, 'enemy_intents': ['Attack 12'], 'cards_played': ['Strike']}); print(f'situation_tag={r.situation_tag}, hand_at_start={r.hand_at_start}')"`
Expected: `situation_tag=None, hand_at_start=()`

- [ ] **Step 4: Commit all remaining changes**

```bash
git add -A
git commit -m "chore: phase 1 situation-level retrieval complete"
```
