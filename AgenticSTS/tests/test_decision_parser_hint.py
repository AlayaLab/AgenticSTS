"""Tests for format_decision_schema_hint strategic_note filtering."""

from src.brain.decision_parser import format_decision_schema_hint


def test_strategic_note_hint_for_supported_tools():
    """Tools with strategic_note should show the hint."""
    for tool_name in [
        "map_action", "rest_action", "event_action",
        "shop_plan", "card_reward_action", "card_select_action",
    ]:
        hint = format_decision_schema_hint(tool_name)
        assert "strategic_note" in hint, f"{tool_name} should have strategic_note hint"
        assert "note_scope" in hint, f"{tool_name} should have note_scope hint"
        assert "plain prose" in hint
        assert "not JSON" in hint


def test_no_strategic_note_hint_for_unsupported_tools():
    """Tools without strategic_note should NOT show the hint."""
    for tool_name in [
        "hand_select_action", "treasure_action",
        "relic_select_action", "potion_action",
    ]:
        hint = format_decision_schema_hint(tool_name)
        assert "strategic_note" not in hint, f"{tool_name} should NOT have strategic_note hint"


def test_combat_plan_returns_empty():
    """combat_plan always returns empty (schema in system prompt)."""
    assert format_decision_schema_hint("combat_plan") == ""


def test_card_select_optional_hint_mentions_confirm_behavior():
    hint = format_decision_schema_hint(
        "card_select_action",
        allowed_actions=["select_deck_card", "confirm_selection"],
    )
    assert "If action=select_deck_card, include selected_indices (array of card indices)." in hint
    assert "If action=confirm_selection, omit selected_indices." in hint
