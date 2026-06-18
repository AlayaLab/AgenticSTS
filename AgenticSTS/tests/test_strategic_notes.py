from src.brain.planner import CombatPlan, parse_combat_plan


class TestCombatPlanNotes:
    def test_field_exists(self):
        plan = CombatPlan(actions=(), note_to_future_self="Block next turn")
        assert plan.note_to_future_self == "Block next turn"

    def test_defaults_empty(self):
        assert CombatPlan(actions=()).note_to_future_self == ""
        assert CombatPlan(actions=()).analysis is None

    def test_parse_with_note(self):
        raw = (
            '{"plan": [{"type":"card","card":"Strike","target_index":0}], '
            '"end_turn":true, "reasoning":"x", '
            '"analysis":{"problem":"solve turn","key_observations":["a","b"],'
            '"candidate_lines":["line a","line b"],"chosen_line":"line a"},'
            '"note_to_future_self":"Block next round"}'
        )
        plan = parse_combat_plan(raw)
        assert plan is not None
        assert plan.note_to_future_self == "Block next round"
        assert plan.analysis is not None
        assert plan.analysis["chosen_line"] == "line a"

    def test_parse_without_note(self):
        raw = (
            '{"plan": [{"type":"card","card":"Strike","target_index":0}], '
            '"end_turn":true, "reasoning":"x"}'
        )
        plan = parse_combat_plan(raw)
        assert plan is not None
        assert plan.note_to_future_self == ""
