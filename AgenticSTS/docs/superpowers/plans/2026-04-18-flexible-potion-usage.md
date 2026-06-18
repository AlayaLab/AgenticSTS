# Flexible Potion Usage — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stop silently skipping potion rewards / shop purchases when potion slots are full. Let the LLM choose to discard a held potion and take the new one, skip it, or keep status quo. Add a short combat hint biasing the agent toward spending low-value potions when slots are full.

**Architecture:** Pure Python. Zero mod changes. Zero change to `_try_mechanical_rewards` (its existing `continue` already falls through to the LLM path). New prompt helper renders a `## Potion Slot Decision` subsection injected into reward/shop prompts only when slots full + candidate potion present. A single-line hint appended to combat prompt when slots are full.

**Tech Stack:** Python 3.11, pytest, `SimpleNamespace`-based test doubles.

**Spec:** [docs/superpowers/specs/2026-04-18-flexible-potion-usage-design.md](../specs/2026-04-18-flexible-potion-usage-design.md)

---

## File Structure

| File | Role |
|---|---|
| `src/brain/prompts/_potion_slot_fmt.py` (new) | Format helper: held potions + candidate → `## Potion Slot Decision` lines |
| `src/brain/prompts/reward.py` (modify) | Inject subsection when potion reward present + slots full |
| `src/brain/prompts/shop.py` (modify) | Inject subsection when shop has affordable potion + slots full |
| `src/brain/conversation.py` (modify) | Append single-line hint when slots full in combat prompt |
| `tests/brain/prompts/test_potion_slot_fmt.py` (new) | Unit: helper format output |
| `tests/brain/prompts/test_reward_potion_slot.py` (new) | Unit: reward prompt injection |
| `tests/brain/prompts/test_shop_potion_slot.py` (new) | Unit: shop prompt injection |
| `tests/test_combat_conversation_potion_hint.py` (new) | Unit: combat hint line |
| `tests/test_loop_potion_fallthrough.py` (new) | Regression: mechanical loop still falls through to LLM when potion + full |

---

### Task 1: `_potion_slot_fmt.py` helper

**Files:**
- Create: `src/brain/prompts/_potion_slot_fmt.py`
- Test: `tests/brain/prompts/test_potion_slot_fmt.py` (new)

- [ ] **Step 1.1: Write failing tests**

Create `tests/brain/prompts/test_potion_slot_fmt.py`:

```python
from types import SimpleNamespace

from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision


def _potion(index: int, name: str, desc: str, occupied: bool = True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _gs(potions, open_slots, total_slots=3):
    return SimpleNamespace(
        potions=potions, open_potion_slots=open_slots, potion_slots=total_slots,
    )


def test_empty_when_not_full():
    gs = _gs([_potion(0, "Fire Potion", "Deal 10 damage.")], open_slots=2)
    lines = format_potion_slot_decision(gs, candidate_potions=[("Ghost Potion", "Intangible.")])
    assert lines == []


def test_empty_when_no_candidates():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(gs, candidate_potions=[])
    assert lines == []


def test_subsection_renders_held_and_candidate():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Ancient Potion", "Start each turn with +1 energy."),
    ]
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(
        gs,
        candidate_potions=[("Ghost Potion", "Intangible for 1 turn.")],
    )
    text = "\n".join(lines)
    assert "## Potion Slot Decision (slots FULL)" in text
    assert "[0] Fire Potion" in text
    assert "Deal 10 damage." in text
    assert "[1] Block Potion" in text
    assert "[2] Ancient Potion" in text
    # Sustained keyword detection → timing tag
    assert "[SUSTAINED]" in text or "[INSTANT]" in text
    assert "Ghost Potion" in text
    assert "Intangible for 1 turn." in text
    assert "discard one of [0/1/2]" in text


def test_subsection_skips_empty_held_slots():
    # Only occupied slots should be listed even if gs.potions includes empty placeholders.
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage.", occupied=True),
        _potion(1, "", "", occupied=False),
        _potion(2, "Block Potion", "Gain 12 block.", occupied=True),
    ]
    # open_slots=0 is still the trigger even if gs.potions has holes (the game model
    # can produce weird mixes — we must render only the real held ones).
    gs = _gs(held, open_slots=0)
    lines = format_potion_slot_decision(gs, candidate_potions=[("Ghost Potion", "Intangible.")])
    text = "\n".join(lines)
    assert "[0] Fire Potion" in text
    assert "[1] " not in text or "[1] Block" not in text  # index 1 placeholder skipped
    assert "[2] Block Potion" in text
    assert "discard one of [0/2]" in text


def test_subsection_handles_multiple_candidates():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _gs(held, open_slots=0, total_slots=1)
    lines = format_potion_slot_decision(
        gs,
        candidate_potions=[
            ("Ghost Potion", "Intangible for 1 turn."),
            ("Regen Potion", "Regen 5 for 5 turns."),
        ],
    )
    text = "\n".join(lines)
    assert "Ghost Potion" in text
    assert "Regen Potion" in text
    assert "Candidate" in text
```

- [ ] **Step 1.2: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_potion_slot_fmt.py -v`
Expected: `ModuleNotFoundError: No module named 'src.brain.prompts._potion_slot_fmt'`.

- [ ] **Step 1.3: Implement helper**

Create `src/brain/prompts/_potion_slot_fmt.py`:

```python
"""Format the Potion Slot Decision subsection for reward/shop prompts.

Injected only when potion slots are full AND new potions are available — gives the
LLM an explicit discard-then-take option instead of silently losing the new potion.
"""

from __future__ import annotations

from src.brain.prompts._deck_fmt import strip_bbcode
from src.knowledge.potion_classifier import classify_potion


def _timing_tag(name: str, desc: str) -> str:
    profile = classify_potion(name or "", desc or "")
    return "[SUSTAINED]" if profile.timing == "sustained" else "[INSTANT]"


def format_potion_slot_decision(
    gs,
    candidate_potions: list[tuple[str, str]],
) -> list[str]:
    """Return subsection lines for the full-slot + new-potion scenario.

    Args:
        gs: GameState-like object with `potions`, `open_potion_slots`.
        candidate_potions: list of (name, description) for new potions available
            to claim/buy. Caller must pre-filter (e.g., affordable in shop).

    Returns:
        [] when slots are not full, or when candidate_potions is empty.
        Otherwise a list of prompt lines ready for `lines.extend(...)`.
    """
    if getattr(gs, "open_potion_slots", 0) > 0:
        return []
    if not candidate_potions:
        return []

    held = [p for p in (getattr(gs, "potions", []) or []) if getattr(p, "occupied", False)]
    held_indices = [p.index for p in held]

    lines: list[str] = ["", "## Potion Slot Decision (slots FULL)", "Currently held:"]
    for pot in held:
        name = (pot.name or "").strip()
        desc = strip_bbcode(pot.description or "").strip() if pot.description else ""
        tag = _timing_tag(name, desc)
        lines.append(f"  [{pot.index}] {name} {tag} — {desc}")

    if len(candidate_potions) == 1:
        cname, cdesc = candidate_potions[0]
        cdesc_clean = strip_bbcode(cdesc or "").strip() if cdesc else ""
        lines.append(
            f"Candidate: {cname} {_timing_tag(cname, cdesc_clean)} — {cdesc_clean}"
        )
    else:
        lines.append("Candidates:")
        for cname, cdesc in candidate_potions:
            cdesc_clean = strip_bbcode(cdesc or "").strip() if cdesc else ""
            lines.append(
                f"  - {cname} {_timing_tag(cname, cdesc_clean)} — {cdesc_clean}"
            )

    idx_list = "/".join(str(i) for i in held_indices)
    lines.append("")
    lines.append(
        "Prefer keep unless the candidate is clearly stronger than your "
        "weakest held potion."
    )
    lines.append(
        f"To take the candidate, discard one of [{idx_list}] first; otherwise skip."
    )
    return lines
```

- [ ] **Step 1.4: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_potion_slot_fmt.py -v`
Expected: 5 passed.

- [ ] **Step 1.5: Commit**

```bash
git add src/brain/prompts/_potion_slot_fmt.py tests/brain/prompts/test_potion_slot_fmt.py
git commit -m "feat(prompts): add _potion_slot_fmt helper for full-slot decisions"
```

---

### Task 2: Inject into `build_card_reward_prompt`

**Files:**
- Modify: `src/brain/prompts/reward.py`
- Test: `tests/brain/prompts/test_reward_potion_slot.py` (new)

- [ ] **Step 2.1: Inspect reward payload structure**

Run: `grep -n "rewards\b\|reward_type\|claimable\|class Reward\|pending_card_choice" src/mcp_client/upstream_models.py | head -10`

Confirm how `gs.reward.rewards` is shaped (items with `reward_type`, `claimable`, `description`, and enough info to identify a potion name). If items carry only a description (no name), use description as the "name" in the subsection.

Run: `grep -n "reward_type\|potion" src/state/game_state.py src/mcp_client/upstream_models.py | head -10`

If potion reward items carry a richer payload (e.g. `potion_id`, `potion_name`), prefer that. Otherwise fall back to `item.description`.

- [ ] **Step 2.2: Write failing test**

Create `tests/brain/prompts/test_reward_potion_slot.py`:

```python
from types import SimpleNamespace

from src.brain.prompts.reward import build_card_reward_prompt


def _potion(index, name, desc, occupied=True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _reward_item(reward_type, description="", claimable=True, index=0):
    return SimpleNamespace(
        reward_type=reward_type, description=description,
        claimable=claimable, index=index,
    )


def _reward_gs(potions, open_slots, reward_items):
    reward = SimpleNamespace(
        pending_card_choice=False, card_options=[], alternatives=[],
        rewards=reward_items,
    )
    return SimpleNamespace(
        reward=reward,
        potions=potions, open_potion_slots=open_slots, potion_slots=3,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=120,
        act=1, floor=4,
    )


def test_slot_decision_injected_when_full_and_potion_reward():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Energy Potion", "Gain 2 energy."),
    ]
    gs = _reward_gs(
        potions=held, open_slots=0,
        reward_items=[_reward_item("potion", description="Ghost Potion — Intangible for 1 turn.")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "## Potion Slot Decision" in text
    assert "Ghost Potion" in text


def test_slot_decision_omitted_when_slots_open():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _reward_gs(
        potions=held, open_slots=2,
        reward_items=[_reward_item("potion", description="Ghost Potion — Intangible for 1 turn.")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_omitted_when_no_potion_reward():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _reward_gs(
        potions=held, open_slots=0,
        reward_items=[_reward_item("gold", description="+50 gold")],
    )
    text = build_card_reward_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text
```

- [ ] **Step 2.3: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_reward_potion_slot.py -v`
Expected: All three tests fail because the subsection is not yet injected.

- [ ] **Step 2.4: Inject helper into `build_card_reward_prompt`**

Open `src/brain/prompts/reward.py`. Add import at top:

```python
from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision
```

Inside `build_card_reward_prompt`, locate where reward-level context is computed (after relics section, before `## Available Cards`). Insert this block:

```python
    # Potion slot decision: slots full + claimable potion reward
    reward_obj = gs.reward
    if reward_obj is not None and getattr(gs, "open_potion_slots", 0) <= 0:
        potion_items = [
            item for item in (getattr(reward_obj, "rewards", []) or [])
            if getattr(item, "claimable", False)
            and str(getattr(item, "reward_type", "")).lower() == "potion"
        ]
        candidates = [
            ((getattr(i, "potion_name", "") or i.description or "").strip(),
             (getattr(i, "potion_description", "") or "").strip())
            for i in potion_items
        ]
        candidates = [(n, d) for n, d in candidates if n]
        if candidates:
            lines.extend(format_potion_slot_decision(gs, candidates))
```

The `getattr` indirection covers both shapes: if the upstream payload adds a proper `potion_name` field later, we use it; otherwise we fall back to the reward-item description (which already contains the potion name).

- [ ] **Step 2.5: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_reward_potion_slot.py tests/brain/prompts/test_potion_slot_fmt.py -v`
Expected: all tests pass.

- [ ] **Step 2.6: Regression**

Run: `python -m pytest tests/brain/prompts/ -v`
Expected: pre-existing reward tests still pass (injection is conditional and zero-impact when conditions not met).

- [ ] **Step 2.7: Commit**

```bash
git add src/brain/prompts/reward.py tests/brain/prompts/test_reward_potion_slot.py
git commit -m "feat(reward): inject potion slot decision subsection on full slots"
```

---

### Task 3: Inject into `build_shop_plan_prompt`

**Files:**
- Modify: `src/brain/prompts/shop.py`
- Test: `tests/brain/prompts/test_shop_potion_slot.py` (new)

- [ ] **Step 3.1: Identify shop potion fields**

Run: `grep -n "class .*Shop.*Potion\|ShopPotion\|potions\b" src/mcp_client/upstream_models.py | head -10`

Confirm the field shape of `shop.potions` (name, description, price/cost). Examples from earlier inspection: `RawShopPotionPayload` / `AgentViewShopItemPayload` — both expose `name`, `description`, and a price field. Use whichever is materialized by the shop prompt's existing code path.

- [ ] **Step 3.2: Write failing test**

Create `tests/brain/prompts/test_shop_potion_slot.py`:

```python
from types import SimpleNamespace

from src.brain.prompts.shop import build_shop_plan_prompt


def _potion(index, name, desc, occupied=True):
    return SimpleNamespace(index=index, name=name, description=desc, occupied=occupied)


def _shop_potion(name, desc, price):
    return SimpleNamespace(name=name, description=desc, price=price)


def _shop_gs(held, open_slots, shop_potions, gold=100):
    shop = SimpleNamespace(
        is_open=True, cards=[], relics=[], potions=shop_potions,
    )
    return SimpleNamespace(
        shop=shop,
        potions=held, open_potion_slots=open_slots, potion_slots=3,
        player_hp=60, player_max_hp=80, hp_ratio=0.75, gold=gold,
        act=1, floor=7,
    )


def test_slot_decision_injected_when_full_and_affordable_potion():
    held = [
        _potion(0, "Fire Potion", "Deal 10 damage."),
        _potion(1, "Block Potion", "Gain 12 block."),
        _potion(2, "Energy Potion", "Gain 2 energy."),
    ]
    gs = _shop_gs(held, open_slots=0, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=50)], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "## Potion Slot Decision" in text
    assert "Ghost Potion" in text


def test_slot_decision_skipped_when_nothing_affordable():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _shop_gs(held, open_slots=0, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=200)], gold=50)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_skipped_when_slots_open():
    held = [_potion(0, "Fire Potion", "Deal 10 damage.")]
    gs = _shop_gs(held, open_slots=2, shop_potions=[_shop_potion("Ghost Potion", "Intangible.", price=50)], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text


def test_slot_decision_skipped_when_shop_has_no_potions():
    held = [_potion(i, f"P{i}", "x") for i in range(3)]
    gs = _shop_gs(held, open_slots=0, shop_potions=[], gold=100)
    text = build_shop_plan_prompt(gs, deck=[], relics=[], character="Silent")
    assert "Potion Slot Decision" not in text
```

- [ ] **Step 3.3: Run tests — expect fail**

Run: `python -m pytest tests/brain/prompts/test_shop_potion_slot.py -v`
Expected: 4 failures.

- [ ] **Step 3.4: Inject helper into shop prompt**

Open `src/brain/prompts/shop.py`. Add import near other prompt helper imports:

```python
from src.brain.prompts._potion_slot_fmt import format_potion_slot_decision
```

Inside `build_shop_plan_prompt`, after the relic section (before the gold-budget analysis block near line 99), insert:

```python
    # Potion slot decision: slots full + affordable potion in shop
    if getattr(gs, "open_potion_slots", 0) <= 0 and shop.potions:
        affordable = [p for p in shop.potions if getattr(p, "price", 0) <= gold]
        candidates = [
            ((getattr(p, "name", "") or "").strip(),
             (getattr(p, "description", "") or "").strip())
            for p in affordable
        ]
        candidates = [(n, d) for n, d in candidates if n]
        if candidates:
            lines.extend(format_potion_slot_decision(gs, candidates))
```

- [ ] **Step 3.5: Run tests — expect pass**

Run: `python -m pytest tests/brain/prompts/test_shop_potion_slot.py tests/brain/prompts/test_potion_slot_fmt.py -v`
Expected: all tests pass.

- [ ] **Step 3.6: Regression**

Run: `python -m pytest tests/brain/prompts/ -v`
Expected: all pass.

- [ ] **Step 3.7: Commit**

```bash
git add src/brain/prompts/shop.py tests/brain/prompts/test_shop_potion_slot.py
git commit -m "feat(shop): inject potion slot decision on full slots + affordable potion"
```

---

### Task 4: Combat prompt hint on full slots

**Files:**
- Modify: `src/brain/conversation.py`
- Test: `tests/test_combat_conversation_potion_hint.py` (new)

- [ ] **Step 4.1: Write failing test**

Create `tests/test_combat_conversation_potion_hint.py`:

```python
"""Combat prompt should append a short hint when potion slots are full."""
from types import SimpleNamespace

import pytest

from src.brain.conversation import CombatConversation


def _combat_gs(open_slots, filled_slots=3, total_slots=3):
    potions = []
    for i in range(filled_slots):
        potions.append(SimpleNamespace(
            index=i, name=f"Pot{i}", description=f"Effect {i}.",
            occupied=True, can_use=True, requires_target=False,
            target_index_space="", target_type="",
        ))
    return SimpleNamespace(
        potions=potions, potion_slots=total_slots, open_potion_slots=open_slots,
        # other fields CombatConversation may touch — pad minimally
    )


@pytest.fixture
def conversation():
    # Thin wrapper: real CombatConversation constructor may require more setup.
    # If constructor is heavy, this test may need to call the static _format_potions
    # helper directly. Adjust in implementation step if needed.
    return CombatConversation.__new__(CombatConversation)


def test_combat_hint_present_when_slots_full(conversation):
    gs = _combat_gs(open_slots=0, filled_slots=3, total_slots=3)
    lines: list[str] = []
    conversation._format_potions(gs, lines, playable=[], is_replan=False)
    text = "\n".join(lines)
    assert "Potion slots: 3/3 FULL" in text
    assert "Slots FULL — spend a lower-value potion" in text


def test_combat_hint_absent_when_slots_open(conversation):
    gs = _combat_gs(open_slots=1, filled_slots=2, total_slots=3)
    lines: list[str] = []
    conversation._format_potions(gs, lines, playable=[], is_replan=False)
    text = "\n".join(lines)
    assert "Potion slots: 2/3 (1 open)" in text
    assert "Slots FULL —" not in text
```

**Note:** `_format_potions` may not currently exist as a separate method — the code block lives inline inside a larger method (see spec §5.5 reference: `src/brain/conversation.py` around line 1062-1098). If so, Step 4.3 below also includes extracting the block into a static/class method named `_format_potions` so this test can target it cleanly. Keep the extraction minimal (pure move).

- [ ] **Step 4.2: Run tests — expect fail**

Run: `python -m pytest tests/test_combat_conversation_potion_hint.py -v`
Expected: `AttributeError: 'CombatConversation' object has no attribute '_format_potions'` OR the hint line assertion fails.

- [ ] **Step 4.3: Extract `_format_potions` (if needed) and add hint**

Open `src/brain/conversation.py` and locate the potion block (around lines 1062-1098). The block currently looks like:

```python
        # Potions (skip on re-plan — rarely changes mid-turn)
        potions = gs.potions
        if potions and not is_replan:
            usable = [pot for pot in potions if pot.can_use]
            filled_slots = sum(1 for pot in potions if pot.occupied)
            total_slots = gs.potion_slots
            open_slots = gs.open_potion_slots
            potion_creators = [c.name for c in playable if _creates_potion(c)]
            if total_slots > 0 or usable:
                from src.knowledge.potion_classifier import classify_potion, format_potion_tag
                lines.append("")
                lines.append("## Usable Potions" if usable else "## Potions")
                slot_note = " FULL" if open_slots <= 0 else f" ({open_slots} open)"
                lines.append(f"Potion slots: {filled_slots}/{total_slots}{slot_note}")
                if open_slots <= 0 and potion_creators:
                    names = ", ".join(potion_creators)
                    lines.append(
                        "!! POTION SLOTS FULL: "
                        f"{names} will not add a potion unless you free a slot first."
                    )
                # <<< INSERT NEW HINT HERE >>>
                for pot in usable:
                    ...
```

**(a) Add the hint (in-place, no extraction needed):** insert right after the `POTION SLOTS FULL` conditional:

```python
                if open_slots <= 0:
                    lines.append(
                        "Slots FULL — spend a lower-value potion if it helps this "
                        "round; don't waste just to free a slot."
                    )
```

**(b) Extract into a method so tests can target it:** move the entire `# Potions ...` block into a new method:

```python
    def _format_potions(self, gs, lines: list[str], playable: list, is_replan: bool) -> None:
        """Append potion section to `lines` (mutates). No-op if no potions / replan."""
        potions = gs.potions
        if not potions or is_replan:
            return
        usable = [pot for pot in potions if pot.can_use]
        filled_slots = sum(1 for pot in potions if pot.occupied)
        total_slots = gs.potion_slots
        open_slots = gs.open_potion_slots
        potion_creators = [c.name for c in playable if _creates_potion(c)]
        if not (total_slots > 0 or usable):
            return
        from src.knowledge.potion_classifier import classify_potion, format_potion_tag
        lines.append("")
        lines.append("## Usable Potions" if usable else "## Potions")
        slot_note = " FULL" if open_slots <= 0 else f" ({open_slots} open)"
        lines.append(f"Potion slots: {filled_slots}/{total_slots}{slot_note}")
        if open_slots <= 0 and potion_creators:
            names = ", ".join(potion_creators)
            lines.append(
                "!! POTION SLOTS FULL: "
                f"{names} will not add a potion unless you free a slot first."
            )
        if open_slots <= 0:
            lines.append(
                "Slots FULL — spend a lower-value potion if it helps this "
                "round; don't waste just to free a slot."
            )
        for pot in usable:
            target_hint = (
                " -> targets "
                f"{describe_target_scope(pot.target_index_space, pot.target_type)} "
                "(target_index required)"
                if pot.requires_target
                else ""
            )
            pot_desc = strip_bbcode(pot.description) if pot.description else ""
            profile = classify_potion(pot.name or "", pot.description or "")
            timing_tag = format_potion_tag(
                profile.timing, self._combat_type, self._floors_to_boss
            )
            lines.append(
                f"- [potion_index={pot.index}] {pot.name} {timing_tag}"
                f"{target_hint}: {pot_desc}"
            )
```

Then replace the original inline block with a call:

```python
        self._format_potions(gs, lines, playable, is_replan)
```

- [ ] **Step 4.4: Run tests — expect pass**

Run: `python -m pytest tests/test_combat_conversation_potion_hint.py -v`
Expected: 2 passed.

- [ ] **Step 4.5: Broader regression**

Run: `python -m pytest tests/test_combat_conversation.py -v`
Expected: all pre-existing combat conversation tests pass (the extraction preserves behavior).

- [ ] **Step 4.6: Commit**

```bash
git add src/brain/conversation.py tests/test_combat_conversation_potion_hint.py
git commit -m "feat(combat): hint on full potion slots to spend low-value potions"
```

---

### Task 5: Regression test — mechanical reward loop still falls through

**Files:**
- Test: `tests/test_loop_potion_fallthrough.py` (new)

This is a **behavior-locking regression test** — the spec relies on the existing `continue` at `src/agent/loop.py:7561-7563` to fall through to LLM when the only remaining claimable reward is a potion and slots are full. If a future refactor accidentally breaks this, our prompt injection becomes useless. The test guards that invariant.

- [ ] **Step 5.1: Inspect `_try_mechanical_rewards` signature**

Run: `grep -n "def _try_mechanical_rewards\|_try_mechanical_rewards" src/agent/loop.py | head -5`

Note: it's an async method on `AgentLoop`. Tests must either mock `_execute` or call a narrow helper. Aim for the minimal fake.

- [ ] **Step 5.2: Write the test**

Create `tests/test_loop_potion_fallthrough.py`:

```python
"""Regression: when the only claimable reward is a potion and slots are full,
_try_mechanical_rewards must return None (fall through to LLM) — not claim it
nor raise. This invariant is what Spec 2's prompt-side changes rely on."""

import asyncio
from types import SimpleNamespace

import pytest


def _reward_item(index, reward_type, description="", claimable=True):
    return SimpleNamespace(
        index=index, reward_type=reward_type, description=description, claimable=claimable,
    )


def _gs_with_only_potion_reward(open_potion_slots=0):
    reward = SimpleNamespace(
        rewards=[_reward_item(0, "potion", description="Ghost Potion")],
        pending_card_choice=False, card_options=[], alternatives=[],
    )
    run = SimpleNamespace(floor=4)
    return SimpleNamespace(
        reward=reward, run=run, state_type="card_reward",
        open_potion_slots=open_potion_slots, potion_slots=3,
    )


@pytest.mark.asyncio
async def test_mechanical_reward_falls_through_when_only_potion_and_full():
    """If slots are full and potion is the only claimable item, the mechanical
    path must return None (not auto-claim, not auto-skip-and-return-a-sentinel)."""
    from src.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    # Stub the execute path (should not be called for this scenario)
    loop._execute = lambda *a, **kw: (_ for _ in ()).throw(
        AssertionError("must not execute any action"))
    # Other attributes possibly touched by _try_mechanical_rewards; set to None/defaults:
    loop._run_state = None

    gs = _gs_with_only_potion_reward(open_potion_slots=0)
    result = await loop._try_mechanical_rewards(gs)
    assert result is None


@pytest.mark.asyncio
async def test_mechanical_reward_still_claims_gold_when_mixed():
    """Sanity check: when reward has [gold, potion] with full slots, gold is
    still claimed mechanically (covers the first tick of the spec's reward flow)."""
    from src.agent.loop import AgentLoop

    executed = []

    async def fake_execute(action):
        executed.append(action)

    loop = AgentLoop.__new__(AgentLoop)
    loop._execute = fake_execute
    loop._run_state = None

    reward = SimpleNamespace(
        rewards=[
            _reward_item(0, "gold", description="+50 gold"),
            _reward_item(1, "potion", description="Ghost Potion"),
        ],
        pending_card_choice=False, card_options=[], alternatives=[],
    )
    gs = SimpleNamespace(
        reward=reward, run=SimpleNamespace(floor=4), state_type="card_reward",
        open_potion_slots=0, potion_slots=3,
    )

    decision = await loop._try_mechanical_rewards(gs)
    assert decision is not None
    assert any(getattr(a, "get", lambda *_: None)("action") == "claim_reward"
               for a in executed)
```

**Caveat on test surface:** `AgentLoop` has many dependencies. If instantiating via `__new__` leaks missing attributes, the test body above may require additional stub attributes (`_cached_*`, `_skill_library`, etc.). If the test explodes with `AttributeError: 'AgentLoop' object has no attribute 'X'`, set `loop.X = None` or a minimal stub inside the test setup, guided by the error. Keep stubs as tight as possible to preserve the regression's meaning.

- [ ] **Step 5.3: Run the test — expect pass already**

Run: `python -m pytest tests/test_loop_potion_fallthrough.py -v`
Expected: both tests pass against current code (since we made no change to `_try_mechanical_rewards`). If they fail, fix the stubs per the caveat above until they verify the observed behavior.

- [ ] **Step 5.4: Commit**

```bash
git add tests/test_loop_potion_fallthrough.py
git commit -m "test(loop): lock in mechanical reward fallthrough when potion + full slots"
```

---

### Task 6: Live smoke test

**Files:** none modified; live observation.

- [ ] **Step 6.1: Start an agent run**

Run: `python -m scripts.run_agent --steps 300 --runs 1 --character Silent --ascension 0`

Play until potion slots fill (typically mid-act-1 via combat reward or event). Let the run continue past another potion reward or a shop visit with potions for sale.

- [ ] **Step 6.2: Verify reward-path prompt injection**

Search the session log for `card_reward` prompts after slots filled:

Run: `python -c "import json, glob; f=sorted(glob.glob('logs/run_*.jsonl'))[-1]; [print(line) for line in open(f) if 'Potion Slot Decision' in line][:3]"`

Expected: at least one prompt containing `## Potion Slot Decision (slots FULL)` with held potions and the candidate listed. If the run never naturally hits "full + potion reward" in 300 steps, bump to 500 or run two smoke sessions.

- [ ] **Step 6.3: Verify shop-path prompt injection**

Continue the run until a shop visit with a potion in stock and slots full. Confirm `## Potion Slot Decision` appears in the `shop_plan` prompt.

- [ ] **Step 6.4: Verify combat hint**

Find any `combat_plan` prompt during a round with slots full. Confirm the line `Slots FULL — spend a lower-value potion if it helps this round; don't waste just to free a slot.` appears immediately after the existing `Potion slots: N/M FULL` line.

Run: `python -c "import glob; f=sorted(glob.glob('logs/run_*.jsonl'))[-1]; [print(line[:400]) for line in open(f) if 'Slots FULL — spend' in line][:3]"`

- [ ] **Step 6.5: Verify at least one `discard_potion` occurred**

Run: `python -c "import glob; f=sorted(glob.glob('logs/run_*.jsonl'))[-1]; print(sum(1 for l in open(f) if 'discard_potion' in l))"`

Expected: a non-zero integer if the agent exercised the new option. If zero across several smoke runs, sanity-check the prompt renders correctly (step 6.2/6.3) — the LLM may simply be choosing `skip` each time, which is still valid behavior, but note the absence in the acceptance review.

- [ ] **Step 6.6: Acceptance review**

Read 3-5 injected prompts end-to-end. Check:
- No garbled / duplicate subsections
- Held potions list matches what the agent actually holds
- Candidate name+description is sensible (no BBCode leaks — `strip_bbcode` applied)
- Combat hint line appears only when slots full, not when there's room
- Subsection only appears when potion is actually claimable / affordable

---

## Self-Review Checklist (performed during plan authoring)

- Coverage: spec §5.1 → Task 5 (regression only; no code change as planned). §5.2 shop prompt → Task 3. §5.3 helper → Task 1. §5.4 injection sites → Tasks 2 and 3. §5.5 combat hint → Task 4. §8 unit/integration tests → distributed across Tasks 1-6.
- No TBDs, TODOs, or "implement later" instructions. Every code block contains the full code.
- Function signatures consistent across tasks: `format_potion_slot_decision(gs, candidate_potions)` is the single entry point used by both reward.py and shop.py. Combat hint is a single `lines.append(...)` call.
- Type consistency: `candidate_potions` is `list[tuple[str, str]]` everywhere — Task 1 defines it, Tasks 2/3 produce it.
- Subtle point called out in Task 5.2: `AgentLoop.__new__` instantiation may leak missing attributes; caveat provides the repair path without inventing behavior.
