# DPS-Aware Card Evaluation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the agent quantitatively evaluate card picks against Boss HP targets instead of relying on qualitative "fills a gap" reasoning.

**Architecture:** Pure prompt changes across 4 files + 1 new shared helper. No Python DPS calculation — LLM is guided to estimate DPS itself. Card clarifications (Speedster etc.) injected conditionally when relevant cards appear.

**Tech Stack:** Python prompt builders, knowledge DB lookup for card metadata, pytest

---

## File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `src/brain/prompts/_card_clarifications.py` | **Create** | Shared dict of card mechanic clarifications + injection helper |
| `src/brain/prompts/reward.py` | **Modify** | Enhanced card display + DPS Check evaluation |
| `src/brain/prompts/shop.py` | **Modify** | DPS-aware guide section |
| `src/brain/prompts/event.py` | **Modify** | Lightweight DPS reminder |
| `src/brain/prompts/system.py` | **Modify** | Damage-first framing in SYSTEM_DECKBUILD |
| `tests/test_dps_aware_prompts.py` | **Create** | Tests for all changes |

---

### Task 1: Card Clarifications Shared Module

**Files:**
- Create: `src/brain/prompts/_card_clarifications.py`
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write the failing test**

```python
# tests/test_dps_aware_prompts.py
from __future__ import annotations


def test_card_clarifications_returns_notes_when_speedster_in_offered():
    from src.brain.prompts._card_clarifications import format_card_notes

    result = format_card_notes(
        offered_names=["Speedster", "Backflip"],
        deck_names=["Strike", "Defend"],
    )
    assert "## Card Notes" in result
    assert "Speedster" in result
    assert "Turn-start draw does NOT trigger" in result


def test_card_clarifications_returns_notes_when_speedster_in_deck():
    from src.brain.prompts._card_clarifications import format_card_notes

    result = format_card_notes(
        offered_names=["Backflip"],
        deck_names=["Strike", "Speedster+"],
    )
    assert "## Card Notes" in result
    assert "Speedster" in result


def test_card_clarifications_returns_empty_when_no_match():
    from src.brain.prompts._card_clarifications import format_card_notes

    result = format_card_notes(
        offered_names=["Backflip"],
        deck_names=["Strike", "Defend"],
    )
    assert result == ""
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: FAIL with `ModuleNotFoundError` or `ImportError`

- [ ] **Step 3: Write the implementation**

```python
# src/brain/prompts/_card_clarifications.py
"""Card mechanic clarifications for commonly misunderstood cards.

Injected into card reward, shop, and combat prompts when relevant cards
appear in offered options or the current deck.
"""

from __future__ import annotations

# Card name (case-insensitive key) → clarification text.
# Extend this dict as more misunderstandings are discovered.
CARD_CLARIFICATIONS: dict[str, str] = {
    "speedster": (
        "Speedster: Turn-start draw does NOT trigger Speedster. "
        "Only draw effects from played cards (Backflip, Acrobatics, etc.) count. "
        "Without draw cards in deck, Speedster deals 0 damage/turn. "
        "Value scales with draw card density."
    ),
}


def format_card_notes(
    offered_names: list[str],
    deck_names: list[str],
) -> str:
    """Build a Card Notes section if any relevant cards are present.

    Scans both offered card names and deck card names against
    CARD_CLARIFICATIONS. Returns a formatted section or empty string.

    Args:
        offered_names: Names of cards being offered (reward/shop).
        deck_names: Names of cards currently in the deck.
    """
    # Normalize: strip "+" suffix, lowercase
    all_names = {n.rstrip("+").lower() for n in offered_names}
    all_names.update(n.rstrip("+").lower() for n in deck_names)

    matched = [
        note
        for key, note in CARD_CLARIFICATIONS.items()
        if key in all_names
    ]

    if not matched:
        return ""

    lines = ["", "## Card Notes"]
    for note in matched:
        lines.append(f"- {note}")
    return "\n".join(lines)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m pytest tests/test_dps_aware_prompts.py::test_card_clarifications_returns_notes_when_speedster_in_offered tests/test_dps_aware_prompts.py::test_card_clarifications_returns_notes_when_speedster_in_deck tests/test_dps_aware_prompts.py::test_card_clarifications_returns_empty_when_no_match -v`
Expected: 3 PASSED

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/_card_clarifications.py tests/test_dps_aware_prompts.py
git commit -m "feat: add card clarifications module (Speedster mechanic note)"
```

---

### Task 2: Enhanced Card Display in Reward Prompt

**Files:**
- Modify: `src/brain/prompts/reward.py:10-11,44-46`
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dps_aware_prompts.py`:

```python
def _make_reward_card(index, name, rules_text, upgraded=False, dynamic_values=None):
    """Create a minimal RawRewardCardOptionPayload-like object."""
    from unittest.mock import MagicMock

    c = MagicMock()
    c.index = index
    c.name = name
    c.upgraded = upgraded
    c.rules_text = rules_text
    c.resolved_rules_text = rules_text
    c.dynamic_values = dynamic_values or []
    return c


def _make_gs_with_reward(card_options, act=1, floor=7, hp=54, max_hp=70, gold=100, deck=None):
    """Create a minimal GameState with reward data."""
    from unittest.mock import MagicMock

    gs = MagicMock()
    gs.act = act
    gs.floor = floor
    gs.player_hp = hp
    gs.player_max_hp = max_hp
    gs.hp_ratio = hp / max_hp
    gs.gold = gold

    rw = MagicMock()
    rw.pending_card_choice = True
    rw.card_options = card_options
    gs.reward = rw
    return gs


def test_reward_prompt_shows_card_metadata():
    """Card reward should show energy cost, type, rarity from knowledge DB."""
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [
        _make_reward_card(0, "Follow Through", "Deal 6 damage to ALL enemies."),
        _make_reward_card(1, "Snakebite", "Retain. Apply 7 Poison."),
    ]
    gs = _make_gs_with_reward(cards)
    deck = []

    result = build_card_reward_prompt(gs, deck=deck)

    # Should contain card type/cost info from knowledge DB lookup
    # Even if KB unavailable, rules_text must still appear
    assert "Follow Through" in result
    assert "Snakebite" in result
    assert "rules_text" not in result  # Shouldn't show the literal field name


def test_reward_prompt_contains_boss_damage_check():
    """Evaluation section should contain Boss HP targets and DPS guidance."""
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [_make_reward_card(0, "Strike", "Deal 6 damage.")]
    gs = _make_gs_with_reward(cards, act=1)
    deck = []

    result = build_card_reward_prompt(gs, deck=deck)

    assert "Boss" in result or "boss" in result
    assert "200" in result  # Act 1 boss HP target
    assert "20" in result   # ~20 damage/turn target
    assert "Total damage test" not in result  # Old biased text removed


def test_reward_prompt_act2_boss_hp():
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [_make_reward_card(0, "Strike", "Deal 6 damage.")]
    gs = _make_gs_with_reward(cards, act=2)
    deck = []

    result = build_card_reward_prompt(gs, deck=deck)
    assert "300" in result  # Act 2 boss HP target
    assert "30" in result   # ~30 damage/turn target
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dps_aware_prompts.py::test_reward_prompt_contains_boss_damage_check tests/test_dps_aware_prompts.py::test_reward_prompt_act2_boss_hp -v`
Expected: FAIL — "200" / "Total damage test" assertions fail against current prompt

- [ ] **Step 3: Modify reward.py**

In `src/brain/prompts/reward.py`, make these changes:

**Add imports** (after line 11):
```python
from src.brain.prompts._card_clarifications import format_card_notes
from src.mcp_client.upstream_models import get_damage_block_from_dynamic_values
```

**Add Boss HP constant** (after imports):
```python
_BOSS_HP: dict[int, int] = {1: 200, 2: 400, 3: 600}
```

**Replace the card display loop** (lines 43-46) with:
```python
    lines.append("")
    lines.append("## Available Cards")

    # Try knowledge DB for card metadata (type, cost, rarity)
    try:
        from src.knowledge.knowledge import GameKnowledge
        kb = GameKnowledge.get_instance()
    except Exception:
        kb = None

    for c in rw.card_options:
        upgraded = "+" if c.upgraded else ""
        display_text = (getattr(c, "resolved_rules_text", "") or c.rules_text or "").strip()
        base_line = f"- [index={c.index}] {c.name}{upgraded}"

        # Enrich with knowledge DB metadata if available
        card_data = kb.cards.get(c.name) if kb else None
        if card_data:
            cost = card_data.cost or "?"
            ctype = card_data.type or "?"
            rarity = card_data.rarity or "?"
            base_line += f" ({cost}E, {ctype}, {rarity})"

        base_line += f": {display_text}"

        # Append numeric damage/block from dynamic_values
        dvs = getattr(c, "dynamic_values", None) or []
        if dvs:
            d, b, h = get_damage_block_from_dynamic_values(dvs)
            val_parts = []
            if d is not None:
                val_parts.append(f"{d} dmg")
            if b is not None and b > 0:
                val_parts.append(f"{b} block")
            if h is not None and h > 1:
                val_parts.append(f"x{h} hits")
            if val_parts:
                base_line += f" [{' | '.join(val_parts)}]"

        lines.append(base_line)
```

**Replace the Evaluation section** (lines 57-71) with:
```python
    # Boss damage check
    boss_hp = _BOSS_HP.get(act, 400)
    target_dps = boss_hp // 10

    lines.append("")
    lines.append("## Evaluation — Boss Damage Check")
    lines.append("Before picking, estimate your deck's damage output:")
    lines.append("1. Sum each Attack card's base damage in your deck → total attack damage per cycle")
    lines.append("2. Deck cycle length = deck_size ÷ 5 turns")
    lines.append("3. Poison sources: each \"Apply N Poison\" card deals ~N×(N+1)/2 total damage per play")
    lines.append("4. Your damage per turn ≈ (total attack damage per cycle) ÷ cycle_turns + poison contribution")
    lines.append("")
    lines.append(f"Boss HP target: ~{boss_hp} in ~10 turns → need ~{target_dps} damage/turn while also blocking.")
    lines.append("")
    lines.append("Decision rules:")
    lines.append("- If your estimated DPS is well below target → PRIORITIZE damage/poison cards over defense/draw/utility")
    lines.append("- If DPS is sufficient → take defense/draw/utility, or SKIP to keep deck lean")
    lines.append("- Power cards that deal passive damage need enablers (draw cards, attack cards) — factor in whether you have them")
    lines.append("- 3 energy/turn limits you to ~2-3 card plays: a 2-cost card must be worth two 1-cost cards")
    lines.append("")
    lines.append("Consider your deck's 4 dimensions (Damage/Defense/Draw/Energy) but weight Damage highest when below target.")
    lines.append("Review your Build Plan in the Strategic Thread. Does any card fill a gap?")
    lines.append(f"Adding a card increases deck cycle ({deck_size} → {deck_size + 1} cards).")
    lines.append("SKIP if no card clearly improves your weakest dimension — a lean deck beats a bloated one.")

    # Card clarification notes (e.g. Speedster mechanic)
    offered_names = [c.name for c in rw.card_options]
    deck_names = [d.name for d in deck] if deck else []
    notes = format_card_notes(offered_names, deck_names)
    if notes:
        lines.append(notes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/reward.py tests/test_dps_aware_prompts.py
git commit -m "feat: reward prompt — enhanced card display + DPS check + card notes"
```

---

### Task 3: Shop Prompt — DPS-Aware Guide

**Files:**
- Modify: `src/brain/prompts/shop.py:10,157-160`
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dps_aware_prompts.py`:

```python
def test_shop_prompt_contains_boss_hp_target():
    """Shop guide should reference Boss HP targets for DPS awareness."""
    from src.brain.prompts.shop import build_shop_prompt
    from unittest.mock import MagicMock

    shop = MagicMock()
    shop.is_open = True
    shop.cards = []
    shop.relics = []
    shop.potions = []
    shop.card_removal = None

    gs = MagicMock()
    gs.shop = shop
    gs.act = 1
    gs.floor = 10
    gs.player_hp = 50
    gs.player_max_hp = 70
    gs.hp_ratio = 50 / 70
    gs.gold = 200

    result = build_shop_prompt(gs, deck=[])

    assert "200" in result  # Act 1 boss HP
    assert "20" in result   # ~20/turn target


def test_shop_prompt_act3_target():
    from src.brain.prompts.shop import build_shop_prompt
    from unittest.mock import MagicMock

    shop = MagicMock()
    shop.is_open = True
    shop.cards = []
    shop.relics = []
    shop.potions = []
    shop.card_removal = None

    gs = MagicMock()
    gs.shop = shop
    gs.act = 3
    gs.floor = 35
    gs.player_hp = 60
    gs.player_max_hp = 80
    gs.hp_ratio = 60 / 80
    gs.gold = 300

    result = build_shop_prompt(gs, deck=[])

    assert "400" in result  # Act 3 boss HP
    assert "40" in result   # ~40/turn target
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dps_aware_prompts.py::test_shop_prompt_contains_boss_hp_target tests/test_dps_aware_prompts.py::test_shop_prompt_act3_target -v`
Expected: FAIL — no "200" in current shop output

- [ ] **Step 3: Modify shop.py**

**Add import** (after line 10):
```python
from src.brain.prompts._card_clarifications import format_card_notes
```

**Add Boss HP constant** (after `_MAX_ITEM_DESC = 180` on line 17):
```python
_BOSS_HP: dict[int, int] = {1: 200, 2: 400, 3: 600}
```

**Replace the Guide section** (lines 157-160) with:
```python
    # DPS-aware guide
    boss_hp = _BOSS_HP.get(gs.act, 400)
    target_dps = boss_hp // 10

    lines.append("")
    lines.append("## Guide")
    lines.append("Best purchase = biggest power spike for remaining run.")
    lines.append("")
    lines.append(f"Boss HP: ~{boss_hp} in ~10 turns → need ~{target_dps} damage/turn.")
    lines.append("Estimate your deck's damage output first. If below target, prioritize damage/poison cards")
    lines.append("and card removal (faster cycle = more damage cards drawn). If above target, invest in")
    lines.append("defense, draw, relics, or save gold.")
    lines.append("")
    lines.append("Review your Build Plan in the Strategic Thread. Prioritize purchases that fill gaps.")

    # Card clarification notes
    shop_card_names = [c.name for c in shop.cards if c.is_stocked]
    deck_names = [d.name for d in deck] if deck else []
    notes = format_card_notes(shop_card_names, deck_names)
    if notes:
        lines.append(notes)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/shop.py
git commit -m "feat: shop prompt — DPS-aware guide with Boss HP targets"
```

---

### Task 4: Event Prompt — DPS Reminder

**Files:**
- Modify: `src/brain/prompts/event.py:55-57`
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dps_aware_prompts.py`:

```python
def test_event_prompt_contains_dps_reminder():
    """Event prompt should mention Boss HP when evaluating options."""
    from src.brain.prompts.event import build_event_prompt
    from unittest.mock import MagicMock

    ev = MagicMock()
    ev.title = "Test Event"
    ev.event_id = "TEST"
    ev.description = "A test event."
    opt = MagicMock()
    opt.index = 0
    opt.title = "Option A"
    opt.description = "Gain a card"
    opt.is_locked = False
    opt.is_proceed = False
    opt.will_kill_player = False
    ev.options = [opt]

    gs = MagicMock()
    gs.event = ev
    gs.act = 2
    gs.floor = 20
    gs.player_hp = 40
    gs.player_max_hp = 70
    gs.hp_ratio = 40 / 70
    gs.gold = 100

    result = build_event_prompt(gs, deck=[])

    assert "200" in result or "400" in result or "600" in result  # At least one Boss HP target
    assert "boss" in result.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dps_aware_prompts.py::test_event_prompt_contains_dps_reminder -v`
Expected: FAIL — current event prompt has no boss HP mention

- [ ] **Step 3: Modify event.py**

**Replace** lines 55-57 (the evaluation guidance at the end) with:

```python
    lines.append("")
    lines.append("Evaluate each option's risk vs reward. Consider HP cost, gold cost, and what you gain.")
    lines.append("If an option offers a card: consider whether your deck needs more damage to handle upcoming bosses (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600 in ~10 turns). Prefer damage/poison options when your deck's attack output is low.")
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/event.py
git commit -m "feat: event prompt — lightweight DPS reminder for card options"
```

---

### Task 5: System Prompt — Damage-First Framing

**Files:**
- Modify: `src/brain/prompts/system.py:79-80`
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write the failing test**

Append to `tests/test_dps_aware_prompts.py`:

```python
def test_deckbuild_system_prompt_damage_first():
    """SYSTEM_DECKBUILD should frame damage as primary constraint, not 'balance'."""
    from src.brain.prompts.system import SYSTEM_DECKBUILD

    # Old biased text should be gone
    assert "all 4 dimensions in balance" not in SYSTEM_DECKBUILD

    # New damage-first framing
    assert "Damage is the primary constraint" in SYSTEM_DECKBUILD
    # Should mention Boss HP targets
    assert "200" in SYSTEM_DECKBUILD or "boss" in SYSTEM_DECKBUILD.lower()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/test_dps_aware_prompts.py::test_deckbuild_system_prompt_damage_first -v`
Expected: FAIL — current text says "all 4 dimensions in balance"

- [ ] **Step 3: Modify system.py**

**Replace line 80** in `SYSTEM_DECKBUILD`:

Old:
```
- A strong deck needs all 4 dimensions in balance. Identify which dimension your deck lacks most.
```

New:
```
- A strong deck needs enough damage to kill bosses in ~10 turns (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600) while surviving. Damage is the primary constraint — defense, draw, and energy support damage output.
```

The full `SYSTEM_DECKBUILD` Card & Deck Philosophy section becomes:
```python
SYSTEM_DECKBUILD = _SYSTEM_BASE + """

## Card & Deck Philosophy
- Evaluate cards along 4 dimensions: **Damage** (kill faster), **Defense** (survive), **Draw** (cycle deck faster), **Energy** (play more per turn).
- A strong deck needs enough damage to kill bosses in ~10 turns (Act 1 ≈ 200 HP, Act 2 ≈ 400, Act 3 ≈ 600) while surviving. Damage is the primary constraint — defense, draw, and energy support damage output.
- **Shops**: Choose whatever gives the biggest power spike for remaining fights — cards, relics, removal, or potions.

## Strategic Notes — Build Plan
Include a `strategic_note` field in your <decision> JSON. Write a RUNNING BUILD PLAN:
1. **Win condition**: How do you kill bosses? (e.g., "Poison stacking via Noxious Fumes + Catalyst burst")
2. **Key pieces**: Cards that define your build
3. **Gaps**: What's missing? (e.g., "No draw engine yet")
4. **Avoid**: What doesn't fit your win condition
Keep under 50 words. Revise when you take or skip a pivotal card. This note persists across ALL future decisions this run.
Example: "Win: Strength scaling (Demon Form). Key: Demon Form, Pummel. Gap: draw engine, need Offering/Battle Trance. Avoid: expensive non-scaling attacks."
"""
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/system.py
git commit -m "feat: SYSTEM_DECKBUILD — damage-first framing, remove balance bias"
```

---

### Task 6: Final Integration Test + Full Test Suite Run

**Files:**
- Test: `tests/test_dps_aware_prompts.py`

- [ ] **Step 1: Write integration test**

Append to `tests/test_dps_aware_prompts.py`:

```python
def test_reward_prompt_injects_speedster_note_from_deck():
    """When deck contains Speedster, card notes should appear in reward prompt."""
    from src.brain.prompts.reward import build_card_reward_prompt
    from unittest.mock import MagicMock

    cards = [_make_reward_card(0, "Backflip", "Gain 5 Block. Draw 2 cards.")]
    gs = _make_gs_with_reward(cards, act=1)

    deck_card = MagicMock()
    deck_card.name = "Speedster+"
    deck_card.upgraded = True
    deck_card.energy_cost = 2
    deck_card.card_type = "Power"
    deck_card.costs_x = False
    deck_card.star_cost = None
    deck = [deck_card]

    result = build_card_reward_prompt(gs, deck=deck)

    assert "Card Notes" in result
    assert "Speedster" in result
    assert "Turn-start draw does NOT trigger" in result


def test_reward_prompt_no_notes_when_irrelevant():
    """No card notes section when neither offered nor deck has clarifiable cards."""
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [_make_reward_card(0, "Strike", "Deal 6 damage.")]
    gs = _make_gs_with_reward(cards, act=1)
    deck = []

    result = build_card_reward_prompt(gs, deck=deck)

    assert "Card Notes" not in result
```

- [ ] **Step 2: Run full test suite**

Run: `python -m pytest tests/test_dps_aware_prompts.py -v`
Expected: All tests PASS (should be ~10 tests total)

- [ ] **Step 3: Run existing tests to check for regressions**

Run: `python -m pytest tests/ -v --timeout=30 2>&1 | tail -30`
Expected: No new failures. Existing tests in `test_prompt_cleanup.py` and others should still pass.

- [ ] **Step 4: Commit final test**

```bash
git add tests/test_dps_aware_prompts.py
git commit -m "test: integration tests for card notes injection in reward prompt"
```

---

## Spec Coverage Verification

| Spec Requirement | Task |
|-----------------|------|
| Change 1a: Enhanced card display in reward | Task 2 Step 3 (knowledge DB lookup + dynamic_values) |
| Change 1b: Replace Evaluation with DPS Check | Task 2 Step 3 (Boss HP targets, estimation guide) |
| Change 2: Shop DPS-aware guide | Task 3 Step 3 |
| Change 3: Event DPS reminder | Task 4 Step 3 |
| Change 4: System prompt damage-first | Task 5 Step 3 |
| Change 5: Card clarifications (Speedster) | Task 1 (module) + Task 2/3 (injection) |
