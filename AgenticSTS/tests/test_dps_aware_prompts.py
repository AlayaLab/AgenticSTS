# ruff: noqa: E501
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


# ── Helpers for reward prompt tests ──────────────────────────


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


def _make_reward_alternative(index, label):
    from unittest.mock import MagicMock

    alt = MagicMock()
    alt.index = index
    alt.label = label
    return alt


def _make_gs_with_reward(card_options, act=1, floor=7, hp=54, max_hp=70, gold=100, alternatives=None):
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
    rw.alternatives = alternatives or []
    gs.reward = rw
    return gs


def test_reward_prompt_shows_card_metadata():
    """Card reward should show card names and rules_text."""
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [
        _make_reward_card(0, "Follow Through", "Deal 6 damage to ALL enemies."),
        _make_reward_card(1, "Snakebite", "Retain. Apply 7 Poison."),
    ]
    gs = _make_gs_with_reward(cards)
    deck = []

    result = build_card_reward_prompt(gs, deck=deck)

    assert "Follow Through" in result
    assert "Snakebite" in result


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
    assert "400" in result  # Act 2 boss HP target
    assert "40" in result   # ~40 damage/turn target


# ── Shop prompt tests ────────────────────────────────────────


def _make_shop_gs(act=1, floor=10, hp=50, max_hp=70, gold=200):
    from unittest.mock import MagicMock

    shop = MagicMock()
    shop.is_open = True
    shop.cards = []
    shop.relics = []
    shop.potions = []
    shop.card_removal = None

    gs = MagicMock()
    gs.shop = shop
    gs.act = act
    gs.floor = floor
    gs.player_hp = hp
    gs.player_max_hp = max_hp
    gs.hp_ratio = hp / max_hp
    gs.gold = gold
    return gs


def test_shop_prompt_contains_boss_hp_target():
    """Shop guide should reference Boss HP targets for DPS awareness."""
    from src.brain.prompts.shop import build_shop_plan_prompt

    gs = _make_shop_gs(act=1)
    result = build_shop_plan_prompt(gs, deck=[])

    assert "200" in result  # Act 1 boss HP
    assert "20" in result   # ~20/turn target


def test_shop_prompt_act3_target():
    from src.brain.prompts.shop import build_shop_plan_prompt

    gs = _make_shop_gs(act=3, floor=35, hp=60, max_hp=80, gold=300)
    result = build_shop_plan_prompt(gs, deck=[])

    assert "600" in result  # Act 3 boss HP
    assert "60" in result   # ~60/turn target


def test_shop_prompt_deemphasizes_removal_budget_summary():
    from unittest.mock import MagicMock

    from src.brain.prompts.shop import build_shop_plan_prompt

    gs = _make_shop_gs(act=1, gold=282)
    removal = MagicMock()
    removal.available = True
    removal.used = False
    removal.enough_gold = True
    removal.price = 75
    gs.shop.card_removal = removal

    result = build_shop_plan_prompt(gs, deck=[])

    assert "Card removal: 75g -- Can afford: YES" not in result
    assert "| Removal: YES" not in result
    assert "Schema for card removal purchase entries" in result
    assert "For scaling attacks, estimate their damage on boss turns 5-10" in result
    assert "strengthens an engine you already have" in result


# ── Event prompt tests ───────────────────────────────────────


def test_event_prompt_contains_dps_reminder():
    """Event prompt should mention Boss HP when evaluating options."""
    from unittest.mock import MagicMock

    from src.brain.prompts.event import build_event_prompt

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
    # The DPS reminder is now gated on an actual addable card being offered.
    opt.cards_offered = [
        {"name": "Strike", "cost": 1, "type": "Attack", "rules_text": "Deal 6 damage."}
    ]
    opt.relics_offered = []
    opt.potions_offered = []
    opt.curses_risk = []
    opt.hp_cost = 0
    opt.gold_cost = 0
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

    assert "200" in result
    assert "400" in result
    assert "600" in result
    assert "boss" in result.lower()


# ── System prompt tests ──────────────────────────────────────


def test_deckbuild_system_prompt_damage_first():
    """SYSTEM_DECKBUILD should frame damage as primary constraint, not 'balance'."""
    from src.brain.prompts.system import SYSTEM_DECKBUILD

    assert "all 4 dimensions in balance" not in SYSTEM_DECKBUILD
    assert "Damage is the primary constraint" in SYSTEM_DECKBUILD
    assert "200" in SYSTEM_DECKBUILD or "boss" in SYSTEM_DECKBUILD.lower()


# ── Integration tests ────────────────────────────────────────


def test_reward_prompt_injects_speedster_note_from_deck():
    """When deck contains Speedster, card notes should appear in reward prompt."""
    from unittest.mock import MagicMock

    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [_make_reward_card(0, "Backflip", "Gain 5 Block. Draw 2 cards.")]
    gs = _make_gs_with_reward(cards, act=1)

    deck_card = MagicMock()
    deck_card.name = "Speedster+"
    deck_card.upgraded = True
    deck_card.energy_cost = 2
    deck_card.card_type = "Power"
    deck_card.costs_x = False
    deck_card.star_cost = None
    deck_card.rules_text = "Deal damage equal to the number of cards drawn this turn."
    deck_card.resolved_rules_text = ""
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


def test_reward_prompt_shows_alternative_indices_and_unknown_labels():
    from src.brain.prompts.reward import build_card_reward_prompt

    cards = [_make_reward_card(0, "Strike", "Deal 6 damage.")]
    alternatives = [
        _make_reward_alternative(0, "Skip"),
        _make_reward_alternative(1, "Reroll"),
    ]
    gs = _make_gs_with_reward(cards, alternatives=alternatives)

    result = build_card_reward_prompt(gs, deck=[])

    assert "[ALT index=0] Skip: Take no card" in result
    assert "[ALT index=1] Reroll" in result
