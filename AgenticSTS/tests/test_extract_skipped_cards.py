"""Tests for combat_trace_renderer.extract_skipped_cards."""
from __future__ import annotations

from src.memory.combat_trace_renderer import extract_skipped_cards


def _state_card_reward(options: list[tuple[int, str]]) -> dict:
    return {
        "event": "state",
        "state_type": "card_reward",
        "card_reward_details": {
            "card_options": [{"index": i, "name": n} for i, n in options],
            "alternatives": [{"index": 99, "label": "Skip"}],
        },
    }


def _decision_card_reward(option_index: int) -> dict:
    return {
        "event": "decision",
        "state_type": "card_reward",
        "action": {"action": "resolve_rewards", "option_index": option_index},
    }


def _state_shop(cards: list[tuple[int, str]]) -> dict:
    return {
        "event": "state",
        "state_type": "shop",
        "shop_details": {
            "cards": [{"index": i, "name": n} for i, n in cards],
        },
    }


def _decision_shop_buy(option_index: int) -> dict:
    return {
        "event": "decision",
        "state_type": "shop",
        "action": {"action": "buy_card", "option_index": option_index},
    }


def _decision_shop_leave() -> dict:
    return {
        "event": "decision",
        "state_type": "shop",
        "action": {"action": "leave_shop"},
    }


def test_extract_skipped_cards_card_reward_picks_one():
    """A card_reward with 3 options and option_index=2 picked → 2 skipped."""
    events = [
        _state_card_reward([(0, "Catalyst"), (1, "Footwork"), (2, "Eviscerate")]),
        _decision_card_reward(option_index=2),  # picked Eviscerate
    ]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Catalyst", "Footwork"}


def test_extract_skipped_cards_card_reward_skip_alternative():
    """When option_index does not match any card index (e.g. skip alt at 99),
    every card is skipped."""
    events = [
        _state_card_reward([(0, "Catalyst"), (1, "Footwork"), (2, "Eviscerate")]),
        _decision_card_reward(option_index=99),  # skip alternative
    ]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Catalyst", "Footwork", "Eviscerate"}


def test_extract_skipped_cards_shop_one_buy_then_leave():
    events = [
        _state_shop([(0, "Adrenaline"), (1, "Calculated Gamble"), (2, "Pinpoint")]),
        _decision_shop_buy(option_index=0),  # bought Adrenaline
        _decision_shop_leave(),
    ]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Calculated Gamble", "Pinpoint"}


def test_extract_skipped_cards_shop_no_buy():
    events = [
        _state_shop([(0, "Adrenaline"), (1, "Calculated Gamble")]),
        _decision_shop_leave(),
    ]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Adrenaline", "Calculated Gamble"}


def test_extract_skipped_cards_shop_buy_multiple():
    events = [
        _state_shop([(0, "A"), (1, "B"), (2, "C")]),
        _decision_shop_buy(option_index=0),
        _decision_shop_buy(option_index=2),
        _decision_shop_leave(),
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == ["B"]


def test_extract_skipped_cards_dedupes_across_events():
    events = [
        _state_card_reward([(0, "Catalyst"), (1, "X")]),
        _decision_card_reward(option_index=1),  # X picked, Catalyst skipped
        _state_card_reward([(0, "Catalyst"), (1, "Y")]),
        _decision_card_reward(option_index=1),  # Y picked, Catalyst skipped again
    ]
    skipped = extract_skipped_cards(events)
    assert skipped.count("Catalyst") == 1


def test_extract_skipped_cards_preserves_first_seen_order():
    events = [
        _state_card_reward([(0, "A"), (1, "B"), (2, "C")]),
        _decision_card_reward(option_index=2),
        _state_card_reward([(0, "D"), (1, "E")]),
        _decision_card_reward(option_index=1),
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == ["A", "B", "D"]


def test_extract_skipped_cards_returns_empty_on_malformed_event():
    events = [
        {"event": "state", "state_type": "card_reward"},  # missing details
        {"event": "state", "state_type": "card_reward",
         "card_reward_details": {"card_options": "not a list"}},
        {"event": "state", "state_type": "card_reward",
         "card_reward_details": {"card_options": []}},
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == []


def test_extract_skipped_cards_ignores_non_card_decisions():
    events = [
        {"event": "state", "state_type": "map"},
        {"event": "decision", "state_type": "map", "action": {"action": "go"}},
        {"event": "state", "state_type": "rest"},
        {"event": "decision", "state_type": "rest", "action": {"action": "rest"}},
    ]
    skipped = extract_skipped_cards(events)
    assert skipped == []


def test_extract_skipped_cards_state_without_decision_treats_all_as_skipped():
    """Run aborted mid-decision: state event present, no following decision.
    Conservative interpretation — every offered card is skipped."""
    events = [
        _state_card_reward([(0, "Catalyst"), (1, "Footwork")]),
    ]
    skipped = extract_skipped_cards(events)
    assert set(skipped) == {"Catalyst", "Footwork"}


def test_extract_skipped_cards_empty_input():
    assert extract_skipped_cards([]) == []


def test_extract_skipped_cards_handles_none_input():
    assert extract_skipped_cards(None) == []  # type: ignore[arg-type]
