# tests/test_decision_parser.py
"""Tests for <decision> tag extraction and validation."""
from src.brain.decision_parser import (
    extract_decision,
    normalize_decision_payload,
    validate_decision,
)


class TestExtractDecision:
    def test_extracts_tagged_json(self):
        text = 'Some reasoning here.\n\n<decision>\n{"action": "play_card", "card_index": 2, "target_index": 0, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result is not None
        assert result["action"] == "play_card"
        assert result["card_index"] == 2

    def test_extracts_last_tag_when_multiple(self):
        text = '<decision>\n{"action": "bad"}\n</decision>\nMore text\n<decision>\n{"action": "good"}\n</decision>'
        result = extract_decision(text)
        assert result["action"] == "good"

    def test_returns_none_on_no_tag(self):
        text = "Just some reasoning without any decision block."
        result = extract_decision(text)
        assert result is None

    def test_returns_none_on_invalid_json(self):
        text = "<decision>\n{not valid json}\n</decision>"
        result = extract_decision(text)
        assert result is None

    def test_handles_whitespace_in_tag(self):
        text = '<decision>  \n  {"action": "end_turn"}  \n  </decision>'
        result = extract_decision(text)
        assert result["action"] == "end_turn"

    def test_handles_nested_json(self):
        text = '<decision>\n{"plan": [{"type": "card", "card": "Strike", "target_index": 0}], "end_turn": true, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result["plan"][0]["card"] == "Strike"

    def test_fallback_raw_json_when_no_tag(self):
        text = 'Some text\n```json\n{"action": "play_card", "card_index": 0, "target_index": 0, "reasoning": "x"}\n```'
        result = extract_decision(text, allow_fallback=True)
        assert result is not None
        assert result["action"] == "play_card"

    def test_flatten_params_wrapper(self):
        """Gemini sometimes wraps fields in a ``params`` object."""
        text = '<decision>\n{"action": "buy_card", "params": {"option_index": 0}, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result is not None
        assert result["action"] == "buy_card"
        assert result["option_index"] == 0
        assert "params" not in result

    def test_flatten_params_top_level_takes_precedence(self):
        text = '<decision>\n{"action": "buy_card", "option_index": 1, "params": {"option_index": 0}, "reasoning": "test"}\n</decision>'
        result = extract_decision(text)
        assert result["option_index"] == 1

    def test_flatten_params_fallback(self):
        text = '```json\n{"action": "buy_card", "params": {"option_index": 2}, "reasoning": "x"}\n```'
        result = extract_decision(text, allow_fallback=True)
        assert result is not None
        assert result["option_index"] == 2


class TestValidateDecision:
    def test_valid_combat_plan(self):
        data = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "end_turn": True,
            "reasoning": "test",
            "analysis": {
                "problem": "need damage",
                "key_observations": ["low hp", "vulnerable"],
                "candidate_lines": ["Strike", "Defend"],
                "chosen_line": "Strike for kill",
            },
        }
        errors = validate_decision(data, "combat_plan")
        assert errors == []

    def test_normalize_combat_plan_defaults_end_turn_and_flattens_reasoning(self):
        data = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "reasoning": [
                "Block first.",
                "Then attack.",
            ],
        }
        normalized = normalize_decision_payload(data, "combat_plan")

        assert normalized["end_turn"] is True
        assert normalized["reasoning"] == "Block first. Then attack."
        assert validate_decision(normalized, "combat_plan") == []

    def test_valid_map_action(self):
        data = {"action": "choose_map_node", "option_index": 2, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert errors == []

    def test_missing_required_field(self):
        data = {"action": "choose_map_node"}
        errors = validate_decision(data, "map_action")
        assert any("option_index" in e for e in errors)

    def test_invalid_action_enum(self):
        data = {"action": "fly_away", "option_index": 0, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert any("action" in e for e in errors)

    def test_combat_plan_missing_plan_key(self):
        data = {"end_turn": True, "reasoning": "test"}
        errors = validate_decision(data, "combat_plan")
        assert any("plan" in e for e in errors)

    def test_analysis_optional_for_combat(self):
        data = {
            "plan": [{"type": "card", "card": "Strike", "target_index": 0}],
            "end_turn": True,
            "reasoning": "test",
        }
        errors = validate_decision(data, "combat_plan")
        assert errors == []

    def test_analysis_optional_for_noncombat(self):
        data = {"action": "choose_map_node", "option_index": 2, "reasoning": "test"}
        errors = validate_decision(data, "map_action")
        assert errors == []

    def test_hand_select_confirm_allows_no_selected_indices(self):
        data = {"action": "confirm_selection", "reasoning": "Skip retaining a weak card."}
        errors = validate_decision(data, "hand_select_action")
        assert errors == []

    def test_hand_select_select_requires_selected_indices(self):
        data = {"action": "select_deck_card", "reasoning": "Keep the best card."}
        errors = validate_decision(data, "hand_select_action")
        assert any("selected_indices" in e for e in errors)

    def test_card_select_confirm_allows_no_selected_indices(self):
        data = {"action": "confirm_selection", "reasoning": "Skip the optional selection."}
        errors = validate_decision(data, "card_select_action")
        assert errors == []

    def test_card_select_select_requires_selected_indices(self):
        data = {"action": "select_deck_card", "reasoning": "Pick the best card."}
        errors = validate_decision(data, "card_select_action")
        assert any("selected_indices" in e for e in errors)

    def test_card_select_select_allows_legacy_option_index(self):
        data = {
            "action": "select_deck_card",
            "option_index": 0,
            "reasoning": "Pick the best card.",
        }
        errors = validate_decision(data, "card_select_action")
        assert errors == []

    def test_card_reward_alternative_requires_option_index(self):
        data = {"action": "choose_reward_alternative", "reasoning": "Reroll this pack."}
        errors = validate_decision(data, "card_reward_action")
        assert any("option_index" in e for e in errors)

    def test_card_reward_legacy_skip_alias_still_validates(self):
        data = {"action": "skip_reward_cards", "reasoning": "No card helps."}
        errors = validate_decision(data, "card_reward_action")
        assert errors == []

    def test_card_reward_legacy_sacrifice_alias_still_validates(self):
        data = {"action": "sacrifice_reward_cards", "reasoning": "Pael value is higher."}
        errors = validate_decision(data, "card_reward_action")
        assert errors == []
