# Hand Select Retain Prompt Fix Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the retain mode prompt in hand_select to correctly explain STS2 retain mechanics (retained cards are EXTRA options, not replacements) and add priority-grouped card display, eliminating the old misleading "keep only clearly stronger cards" guidance that caused the LLM to skip retaining 80% of the time.

**Architecture:** Three changes: (1) `hand_select.py` already updated with new retain logic — needs unit tests, (2) existing tests in `test_agent_loop_fixes.py` need assertion updates for changed prompt text, (3) `loop.py` has a small `run_id` format change and whitespace cleanup to commit alongside. The `skills.json` has cosmetic dash-to-emdash changes.

**Tech Stack:** Python, pytest

---

### Task 1: Update existing retain test assertions

**Files:**
- Modify: `tests/test_agent_loop_fixes.py:1370` (assertion text)
- Modify: `tests/test_agent_loop_fixes.py:1426` (assertion text)

The two existing retain tests assert old prompt text that no longer exists. Update them to match the new prompt.

- [ ] **Step 1: Update assertion in `test_build_state_prompt_allows_skipping_optional_retain_selection`**

At line 1370, change:
```python
    assert "It is valid to keep nothing." in prompt
```
to:
```python
    assert "Retain = keep cards for next turn" in prompt
```

- [ ] **Step 2: Update assertion in `test_build_state_prompt_allows_optional_retain_even_when_confirm_is_available`**

At line 1426, change:
```python
    assert "Retain choice:" in prompt
```
to:
```python
    assert "Retain = keep cards for next turn" in prompt
```

- [ ] **Step 3: Run existing tests to verify they pass**

Run: `python -m pytest tests/test_agent_loop_fixes.py::test_build_state_prompt_allows_skipping_optional_retain_selection tests/test_agent_loop_fixes.py::test_build_state_prompt_allows_optional_retain_even_when_confirm_is_available tests/test_agent_loop_fixes.py::test_build_state_prompt_uses_hand_select_for_combat_hand_select -v`
Expected: All 3 PASS

- [ ] **Step 4: Commit**

```bash
git add tests/test_agent_loop_fixes.py
git commit -m "test: update retain assertions for new hand_select prompt text"
```

---

### Task 2: Add unit tests for retain priority grouping

**Files:**
- Modify: `tests/test_agent_loop_fixes.py` (add new test functions after existing retain tests)

Add tests that verify: (1) retain mode groups cards into "Do NOT retain" and "Retain these" sections, (2) harmful cards go into the skip group, (3) normal cards go into the keep group.

- [ ] **Step 1: Write test for retain harmful card grouping**

Add after the existing retain tests (around line 1428):

```python
def test_hand_select_retain_groups_harmful_cards_separately():
    """Retain mode should put harmful/status cards in 'Do NOT retain' group."""
    client = MagicMock()
    loop = _make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=50, max_hp=80, block=0, energy=0),
            enemies=[_make_enemy(name="Frog Knight", hp=100, max_hp=120)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=30,
            current_hp=50,
            max_hp=80,
            gold=100,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose cards to [gold]Retain[/gold].[/center]",
            min_select=0,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                _make_selection_card(
                    "Dagger Spray", 0,
                    card_id="dagger_spray",
                    card_type="Attack",
                    energy_cost=1,
                    rules_text="Deal 8 damage to ALL enemies twice. Lose 2 HP.",
                ),
                _make_selection_card(
                    "Predator+", 1,
                    card_id="predator",
                    card_type="Attack",
                    energy_cost=2,
                    rules_text="Deal 21 damage. Next turn, draw 2 cards.",
                ),
                _make_selection_card(
                    "Bouncing Flask", 2,
                    card_id="bouncing_flask",
                    card_type="Skill",
                    energy_cost=2,
                    rules_text="Apply 3 Poison to a random enemy 3 times.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)
    prompt = loop._build_state_prompt_v2(gs)

    # Harmful card should be in skip group
    assert "Do NOT retain" in prompt
    assert "Retain these" in prompt
    # Dagger Spray (lose HP) should be in skip group
    dagger_pos = prompt.index("Dagger Spray")
    skip_pos = prompt.index("Do NOT retain")
    keep_pos = prompt.index("Retain these")
    assert skip_pos < dagger_pos < keep_pos
    # Good cards should be in keep group
    assert prompt.index("Predator+") > keep_pos
    assert prompt.index("Bouncing Flask") > keep_pos
```

- [ ] **Step 2: Write test for retain with no harmful cards (all in keep group)**

```python
def test_hand_select_retain_all_good_cards_in_keep_group():
    """When no harmful cards, all cards go into 'Retain these' group."""
    client = MagicMock()
    loop = _make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=50, max_hp=80, block=0, energy=0),
            enemies=[_make_enemy(name="Frog Knight", hp=100, max_hp=120)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=30,
            current_hp=50,
            max_hp=80,
            gold=100,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to [gold]Retain[/gold].[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                _make_selection_card(
                    "Defend", 0,
                    card_id="defend",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Gain 8 Block.",
                ),
                _make_selection_card(
                    "Leg Sweep", 1,
                    card_id="leg_sweep",
                    card_type="Skill",
                    energy_cost=2,
                    rules_text="Apply 2 Weak. Gain 13 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)
    prompt = loop._build_state_prompt_v2(gs)

    assert "Do NOT retain" not in prompt
    assert "Retain these" in prompt
    assert "Retain = keep cards for next turn" in prompt
    assert "EXTRA options" in prompt
```

- [ ] **Step 3: Write test for retain hint about end-of-turn Sly**

```python
def test_hand_select_retain_shows_sly_end_of_turn_note():
    """Retain mode hint should explain end-of-turn discard does NOT trigger Sly."""
    client = MagicMock()
    loop = _make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=50, max_hp=80, block=0, energy=0),
            enemies=[_make_enemy(name="Boss", hp=200, max_hp=300)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=40,
            current_hp=50,
            max_hp=80,
            gold=100,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose cards to [gold]Retain[/gold].[/center]",
            min_select=0,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                _make_selection_card(
                    "Haze+", 0,
                    card_id="haze",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Sly. Apply 6 Poison to ALL enemies.",
                ),
                _make_selection_card(
                    "Defend", 1,
                    card_id="defend",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Gain 8 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)
    prompt = loop._build_state_prompt_v2(gs)

    assert "end-of-turn discard does NOT trigger Sly" in prompt
    # Should NOT show discard-priority Sly hints (that's for discard mode)
    assert "PRIORITY: Discard a Sly card" not in prompt
```

- [ ] **Step 4: Run all new tests**

Run: `python -m pytest tests/test_agent_loop_fixes.py::test_hand_select_retain_groups_harmful_cards_separately tests/test_agent_loop_fixes.py::test_hand_select_retain_all_good_cards_in_keep_group tests/test_agent_loop_fixes.py::test_hand_select_retain_shows_sly_end_of_turn_note -v`
Expected: All 3 PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_agent_loop_fixes.py
git commit -m "test: add retain priority grouping and Sly hint tests"
```

---

### Task 3: Run full test suite and commit production changes

**Files:**
- Already modified: `src/brain/prompts/hand_select.py`
- Already modified: `src/agent/loop.py`
- Already modified: `data/skills/skills.json`

- [ ] **Step 1: Run full test suite**

Run: `python -m pytest tests/test_agent_loop_fixes.py -v --tb=short`
Expected: ALL tests pass (including the updated retain assertions from Task 1)

- [ ] **Step 2: Commit hand_select.py retain fix**

```bash
git add src/brain/prompts/hand_select.py
git commit -m "fix: correct retain prompt mechanics — retained cards are extra options, not replacements

Old prompt said 'keep only a card that is clearly stronger next turn than
a fresh draw' which caused LLM to skip retaining 80% of the time.

New prompt explains: retain + normal 5-card draw (hand limit 10), so
retained cards are EXTRA options. Default: retain as many as allowed.
Adds priority grouping (harmful/status in skip group, rest in keep group)
and notes end-of-turn discard does NOT trigger Sly.

A/B test: OLD 19% retain rate → NEW 100% retain rate (10 cases, 5 runs each)."
```

- [ ] **Step 3: Commit loop.py run_id format change**

```bash
git add src/agent/loop.py
git commit -m "feat: add timestamp prefix to run_id for chronological sorting"
```

- [ ] **Step 4: Commit skills.json cosmetic changes**

```bash
git add data/skills/skills.json
git commit -m "chore: normalize dashes to emdashes in seed skill content"
```
