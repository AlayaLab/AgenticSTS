"""Unit tests for decision parsing helpers."""
from __future__ import annotations

from scripts._prompt_ab.decision import parse_card_reward_decision


def test_parse_valid_choose_reward_card() -> None:
    text = (
        "Some thinking...\n"
        "<decision>\n"
        '{"action": "choose_reward_card", "option_index": 1, "reasoning": "fits poison plan"}\n'
        "</decision>"
    )
    v = parse_card_reward_decision(text)
    assert v.malformed is False
    assert v.action == "choose_reward_card"
    assert v.option_index == 1
    assert v.is_skip is False


def test_parse_valid_skip_alternative() -> None:
    text = (
        '<decision>{"action": "choose_reward_alternative", '
        '"option_index": 0, "reasoning": "no fit"}</decision>'
    )
    v = parse_card_reward_decision(text)
    assert v.malformed is False
    assert v.action == "choose_reward_alternative"
    assert v.option_index == 0
    assert v.is_skip is True


def test_parse_missing_decision_block() -> None:
    text = "I think I'd pick option 1 because of the synergy."
    v = parse_card_reward_decision(text)
    assert v.malformed is True
    assert v.option_index is None


def test_parse_invalid_json() -> None:
    text = '<decision>{"action": "choose_reward_card", option_index: 1}</decision>'
    v = parse_card_reward_decision(text)
    assert v.malformed is True
