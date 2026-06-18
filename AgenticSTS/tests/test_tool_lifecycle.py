"""Tests for tool lifecycle features."""
from __future__ import annotations

import tempfile
from pathlib import Path
from types import SimpleNamespace

from src.brain.dynamic_tools import DynamicToolRegistry

# ── Test Helpers ──────────────────────────────────────────────

def _make_combat_gs(
    hand_cards=None,
    hp=50,
    max_hp=70,
    energy=3,
    enemies=None,
    floor=10,
    act=1,
    gold=100,
):
    """Create a minimal mock GameState for testing."""
    hand = []
    for c in (hand_cards or []):
        hand.append(SimpleNamespace(
            name=c.get("name", "Card"),
            damage=c.get("damage"),
            block=c.get("block"),
            energy_cost=c.get("energy_cost", 1),
            rules_text="",
            rarity="Common",
        ))
    enemy_list = []
    for e in (enemies or []):
        intents = [SimpleNamespace(
            damage=e.get("damage"), hits=e.get("hits", 1),
            total_damage=e.get("total_damage"), intent_type="attack",
        )] if e.get("damage") else []
        enemy_list.append(SimpleNamespace(
            name=e.get("name", "Enemy"), current_hp=e.get("hp", 30),
            max_hp=e.get("max_hp", 30), block=e.get("block", 0),
            intents=intents, powers=[],
        ))
    raw_run = SimpleNamespace(max_energy=energy)
    raw_combat_player = SimpleNamespace(block=0, powers=[])
    raw_combat = SimpleNamespace(player=raw_combat_player)
    raw = SimpleNamespace(run=raw_run, combat=raw_combat)
    return SimpleNamespace(
        player_hp=hp, player_max_hp=max_hp, hp_ratio=hp / max_hp,
        energy=energy, hand=hand, enemies=enemy_list,
        deck=[], deck_size=10, floor=floor, act=act, gold=gold,
        relics=[], potions=[], character="Silent",
        state_type="monster", is_combat=True, raw=raw,
    )


def _make_tool_code(name, params, include_applicable_states=True, num_test_cases=2):
    """Generate valid dynamic tool code for testing."""
    param_defs = ", ".join(f'"{p}": {{"type": "int", "description": "{p}"}}' for p in params)
    param_args = ", ".join(f"{p}=0" for p in params)
    param_sum = " + ".join(params) if params else "0"
    states_line = (
        'APPLICABLE_STATES = ["monster", "elite", "boss"]\n'
        if include_applicable_states
        else ""
    )
    tc_lines = []
    for i in range(num_test_cases):
        inputs = ", ".join(f'"{p}": {i + 1}' for p in params)
        expected_val = sum(i + 1 for _ in params)
        assertion = (
            f', "expected": {{"total": {expected_val}}}'
            if i == 0
            else ', "expected_contains": "total"'
        )
        tc_lines.append(f'    {{"input": {{{inputs}}}{assertion}}}')
    test_cases = ",\n".join(tc_lines)
    return f"""
SCHEMA = {{
    "name": "{name}",
    "description": "Test tool: {name}.",
    "parameters": {{{param_defs}}},
}}
{states_line}
def execute({param_args}, **kwargs):
    return {{"total": {param_sum}}}

TEST_CASES = [
{test_cases}
]
"""


DICT_RETURNING_TOOL = '''
SCHEMA = {
    "name": "test_dict_tool",
    "description": "Returns a dict result.",
    "parameters": {
        "value": {"type": "int", "description": "Input value"},
    },
}

def execute(value=0, **kwargs):
    return {"result": value * 2, "note": "doubled"}

TEST_CASES = [
    {"input": {"value": 5}, "expected": {"result": 10}},
    {"input": {"value": 0}, "expected": {"result": 0}},
]
'''


class TestExecuteRaw:
    def test_execute_raw_returns_dict(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool is not None
            raw = tool.execute_raw(value=5)
            assert isinstance(raw, dict)
            assert raw["result"] == 10

    def test_execute_returns_str(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool is not None
            result = tool.execute(value=5)
            assert isinstance(result, str)
            assert "10" in result

    def test_execute_raw_increments_counters(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool.usage_count == 0
            tool.execute_raw(value=1)
            assert tool.usage_count == 1
            assert tool.success_count == 1

    def test_execute_delegates_to_execute_raw(self):
        """execute() should NOT double-count -- it delegates to execute_raw()."""
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            tool.execute(value=1)
            assert tool.usage_count == 1  # Not 2
            assert tool.success_count == 1

    def test_deactivated_field_exists(self):
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_dict_tool.py"
            p.write_text(DICT_RETURNING_TOOL)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_dict_tool")
            assert tool.deactivated is False


class TestFormatCompact:
    def test_format_compact_loaded_from_file(self):
        tool_code = '''
SCHEMA = {
    "name": "test_compact",
    "description": "Tool with compact formatter.",
    "parameters": {"value": {"type": "int"}},
}
APPLICABLE_STATES = ["monster"]

def execute(value=0, **kwargs):
    return {"score": value, "verdict": "good" if value > 5 else "bad"}

def FORMAT_COMPACT(result):
    if isinstance(result, dict):
        return f"Score={result['score']}: {result['verdict']}"
    return str(result)[:80]

TEST_CASES = [
    {"input": {"value": 10}, "expected": {"score": 10, "verdict": "good"}},
    {"input": {"value": 2}, "expected": {"score": 2, "verdict": "bad"}},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_compact.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_compact")
            assert tool is not None
            assert tool.format_compact_fn is not None
            raw = tool.execute_raw(value=10)
            compact = tool.format_compact_fn(raw)
            assert compact == "Score=10: good"

    def test_format_compact_none_when_not_present(self):
        tool_code = '''
SCHEMA = {
    "name": "test_no_compact",
    "description": "Tool without compact formatter.",
    "parameters": {"value": {"type": "int"}},
}

def execute(value=0, **kwargs):
    return {"result": value}

TEST_CASES = [
    {"input": {"value": 1}, "expected": {"result": 1}},
    {"input": {"value": 2}, "expected": {"result": 2}},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_no_compact.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_no_compact")
            assert tool is not None
            assert tool.format_compact_fn is None


class TestPlanParamBinder:
    def test_tier1_params_from_plan(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan, PlannedAction

        plan = CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend"),
                PlannedAction(action_type="card", card_name="Strike"),
                PlannedAction(action_type="potion", potion_index=0),
            ),
            end_turn=True,
        )
        gs = _make_combat_gs(hand_cards=[
            {"name": "Defend", "block": 5, "damage": None, "energy_cost": 1},
            {"name": "Strike", "block": None, "damage": 6, "energy_cost": 1},
        ])
        result = bind_plan_params(
            plan,
            gs,
            required_params={
                "play_sequence",
                "num_cards_played",
                "ends_turn",
                "has_potion_use",
            },
        )
        assert result is not None
        assert result["play_sequence"] == ["Defend", "Strike"]
        assert result["num_cards_played"] == 2
        assert result["ends_turn"] is True
        assert result["has_potion_use"] is True

    def test_tier2_params_cross_reference(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan, PlannedAction

        plan = CombatPlan(
            actions=(
                PlannedAction(action_type="card", card_name="Defend"),
                PlannedAction(action_type="card", card_name="Strike"),
            ),
            end_turn=True,
        )
        gs = _make_combat_gs(hand_cards=[
            {"name": "Defend", "block": 5, "damage": None, "energy_cost": 1},
            {"name": "Strike", "block": None, "damage": 6, "energy_cost": 1},
        ])
        result = bind_plan_params(
            plan,
            gs,
            required_params={"planned_block", "planned_damage", "total_energy_spent"},
        )
        assert result is not None
        assert result["planned_block"] == 5
        assert result["planned_damage"] == 6
        assert result["total_energy_spent"] == 2

    def test_unbindable_param_returns_none(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan

        plan = CombatPlan(actions=(), end_turn=True)
        gs = _make_combat_gs()
        result = bind_plan_params(plan, gs, required_params={"num_shivs"})
        assert result is None  # num_shivs not in any bindable set

    def test_missing_card_in_hand_gives_zero(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan, PlannedAction

        plan = CombatPlan(
            actions=(PlannedAction(action_type="card", card_name="Unknown Card"),),
            end_turn=True,
        )
        gs = _make_combat_gs(hand_cards=[
            {"name": "Defend", "block": 5, "damage": None, "energy_cost": 1},
        ])
        result = bind_plan_params(plan, gs, required_params={"planned_damage"})
        assert result is not None
        assert result["planned_damage"] == 0  # Card not in hand, 0 contribution

    def test_state_params_also_bindable(self):
        from src.brain.plan_verifier import bind_plan_params
        from src.brain.planner import CombatPlan

        plan = CombatPlan(actions=(), end_turn=True)
        gs = _make_combat_gs(hp=42)
        result = bind_plan_params(plan, gs, required_params={"current_hp", "ends_turn"})
        assert result is not None
        assert result["current_hp"] == 42
        assert result["ends_turn"] is True


class TestPlanVerifier:
    def test_no_tools_returns_no_replan(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.planner import CombatPlan

        reg = DynamicToolRegistry(tempfile.mkdtemp())
        verifier = PlanVerifier(reg)
        plan = CombatPlan(actions=(), end_turn=True)
        gs = _make_combat_gs()
        result = verifier.verify(plan, gs, combat_state_type="monster")
        assert result.needs_replan is False
        assert result.warnings == []
        assert result.hints == []

    def test_critical_tool_triggers_replan(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.planner import CombatPlan

        tool_code = '''
SCHEMA = {
    "name": "test_critical_eval",
    "description": "Always returns critical severity.",
    "parameters": {"play_sequence": {"type": "list", "description": "Cards played"}},
}
APPLICABLE_STATES = ["monster", "elite", "boss"]
TOOL_TYPE = "plan_evaluator"

def execute(play_sequence=None, **kwargs):
    return {"severity": "critical", "warning": "Missed lethal opportunity!"}

TEST_CASES = [
    {"input": {"play_sequence": []}, "expected_contains": "critical"},
    {"input": {"play_sequence": ["Strike"]}, "expected_contains": "critical"},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_critical_eval.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            verifier = PlanVerifier(reg)
            plan = CombatPlan(actions=(), end_turn=True)
            gs = _make_combat_gs()
            result = verifier.verify(plan, gs, combat_state_type="monster")
            assert result.needs_replan is True
            assert len(result.warnings) == 1
            assert "Missed lethal" in result.warnings[0]

    def test_noncritical_tool_records_hint(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.planner import CombatPlan

        tool_code = '''
SCHEMA = {
    "name": "test_hint_eval",
    "description": "Returns a non-critical observation.",
    "parameters": {"play_sequence": {"type": "list", "description": "Cards played"}},
}
APPLICABLE_STATES = ["monster", "elite", "boss"]
TOOL_TYPE = "plan_evaluator"

def execute(play_sequence=None, **kwargs):
    return {"note": "Consider playing block first"}

TEST_CASES = [
    {"input": {"play_sequence": []}, "expected_contains": "block"},
    {"input": {"play_sequence": ["Defend"]}, "expected_contains": "block"},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_hint_eval.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            verifier = PlanVerifier(reg)
            plan = CombatPlan(actions=(), end_turn=True)
            gs = _make_combat_gs()
            result = verifier.verify(plan, gs, combat_state_type="monster")
            assert result.needs_replan is False
            assert len(result.hints) == 1
            assert "block" in result.hints[0]

    def test_deactivated_tool_skipped(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.planner import CombatPlan

        tool_code = '''
SCHEMA = {
    "name": "test_deactivated_eval",
    "description": "Would return critical but is deactivated.",
    "parameters": {"play_sequence": {"type": "list", "description": "Cards played"}},
}
APPLICABLE_STATES = ["monster", "elite", "boss"]
TOOL_TYPE = "plan_evaluator"

def execute(play_sequence=None, **kwargs):
    return {"severity": "critical", "warning": "Should not appear!"}

TEST_CASES = [
    {"input": {"play_sequence": []}, "expected_contains": "critical"},
    {"input": {"play_sequence": ["X"]}, "expected_contains": "critical"},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_deactivated_eval.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            tool = reg.get("test_deactivated_eval")
            tool.deactivated = True  # Mark as deactivated
            verifier = PlanVerifier(reg)
            plan = CombatPlan(actions=(), end_turn=True)
            gs = _make_combat_gs()
            result = verifier.verify(plan, gs, combat_state_type="monster")
            assert result.needs_replan is False  # Skipped because deactivated

    def test_telemetry_tracked(self):
        from src.brain.dynamic_tools import DynamicToolRegistry
        from src.brain.plan_verifier import PlanVerifier
        from src.brain.planner import CombatPlan

        tool_code = '''
SCHEMA = {
    "name": "test_telemetry_eval",
    "description": "Tool for telemetry testing.",
    "parameters": {"play_sequence": {"type": "list", "description": "Cards played"}},
}
APPLICABLE_STATES = ["monster"]
TOOL_TYPE = "plan_evaluator"

def execute(play_sequence=None, **kwargs):
    return {"note": "ok"}

TEST_CASES = [
    {"input": {"play_sequence": []}, "expected_contains": "ok"},
    {"input": {"play_sequence": ["X"]}, "expected_contains": "ok"},
]
'''
        with tempfile.TemporaryDirectory() as td:
            p = Path(td) / "test_telemetry_eval.py"
            p.write_text(tool_code)
            reg = DynamicToolRegistry(td)
            reg.load_all()
            verifier = PlanVerifier(reg)
            plan = CombatPlan(actions=(), end_turn=True)
            gs = _make_combat_gs()
            verifier.verify(plan, gs, combat_state_type="monster")
            telemetry = verifier.get_telemetry_summary()
            assert "test_telemetry_eval" in telemetry
            assert telemetry["test_telemetry_eval"]["runs"] == 1
            assert telemetry["test_telemetry_eval"]["successes"] == 1


class TestGenerationGates:
    def test_valid_tool_accepted(self):
        code = _make_tool_code("valid_tool_abc", ["current_hp", "incoming_damage"])
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("valid_tool_abc", code)
            assert "SUCCESS" in result

    def test_dedup_rejects_similar_name(self):
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            code1 = _make_tool_code("block_check", ["current_hp", "current_block"])
            result1 = reg.register_tool("block_check", code1)
            assert "SUCCESS" in result1
            code2 = _make_tool_code("block_check_v2", ["current_hp", "current_block"])
            result2 = reg.register_tool("block_check_v2", code2)
            assert "REJECTED" in result2
            assert "Similar tool" in result2

    def test_dedup_allows_different_tools(self):
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            code1 = _make_tool_code("damage_calc", ["current_hp", "incoming_damage"])
            result1 = reg.register_tool("damage_calc", code1)
            assert "SUCCESS" in result1
            code2 = _make_tool_code("block_eval", ["current_block", "dexterity"])
            result2 = reg.register_tool("block_eval", code2)
            assert "SUCCESS" in result2

    def test_missing_applicable_states_rejected(self):
        code = _make_tool_code("no_states", ["current_hp"], include_applicable_states=False)
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("no_states", code)
            assert "REJECTED" in result
            assert "APPLICABLE_STATES" in result

    def test_insufficient_test_cases_rejected(self):
        code = _make_tool_code("one_test", ["current_hp"], num_test_cases=1)
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("one_test", code)
            assert "REJECTED" in result
            assert "TEST_CASES" in result or "test case" in result.lower()

    def test_no_assertion_test_cases_rejected(self):
        # Tool with 2 test cases but no assertions (smoke tests only)
        code = '''
SCHEMA = {
    "name": "no_assert_tool",
    "description": "Tool with smoke tests only.",
    "parameters": {"value": {"type": "int"}},
}
APPLICABLE_STATES = ["monster"]

def execute(value=0, **kwargs):
    return {"result": value}

TEST_CASES = [
    {"input": {"value": 1}},
    {"input": {"value": 2}},
]
'''
        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)
            result = reg.register_tool("no_assert_tool", code)
            assert "REJECTED" in result
            assert "assertion" in result.lower()


class TestRetirement:
    def test_compute_effectiveness_new_tool(self):
        from src.brain.dynamic_tools import compute_effectiveness
        assert compute_effectiveness(usage=0, success=0, runs_since=0) == 1.0

    def test_compute_effectiveness_active_tool(self):
        from src.brain.dynamic_tools import compute_effectiveness
        score = compute_effectiveness(usage=100, success=100, runs_since=10)
        assert score == 10.0

    def test_compute_effectiveness_low_usage(self):
        from src.brain.dynamic_tools import compute_effectiveness
        score = compute_effectiveness(usage=1, success=1, runs_since=10)
        assert score == 0.1

    def test_compute_effectiveness_half_success(self):
        from src.brain.dynamic_tools import compute_effectiveness
        score = compute_effectiveness(usage=10, success=5, runs_since=10)
        assert score == 0.5  # usage_rate=1 * success_rate=0.5

    def test_retirement_sweep_deactivates_low_score(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("low_usage_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("low_usage_tool", code)
            reg._total_runs = 10
            tool = reg.get("low_usage_tool")
            tool.usage_count = 0
            tool.success_count = 0
            tool.creation_run = 0
            actions = reg.retirement_sweep()
            assert any("DEACTIVATED" in a for a in actions)
            assert tool.deactivated is True

    def test_retirement_two_sweep_deletion(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("doomed_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("doomed_tool", code)
            reg._total_runs = 10
            tool = reg.get("doomed_tool")
            tool.usage_count = 0
            tool.success_count = 0
            tool.creation_run = 0
            # First sweep: deactivated
            actions1 = reg.retirement_sweep()
            assert any("DEACTIVATED" in a for a in actions1)
            assert (Path(td) / "doomed_tool.py").exists()
            # Second sweep: deleted
            reg._total_runs = 20
            actions2 = reg.retirement_sweep()
            assert any("DELETED" in a for a in actions2)
            assert not (Path(td) / "doomed_tool.py").exists()
            assert reg.get("doomed_tool") is None

    def test_healthy_tool_not_retired(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("healthy_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("healthy_tool", code)
            reg._total_runs = 10
            tool = reg.get("healthy_tool")
            tool.usage_count = 50
            tool.success_count = 50
            tool.creation_run = 0
            actions = reg.retirement_sweep()
            assert not any("DEACTIVATED" in a or "DELETED" in a for a in actions)
            assert tool.deactivated is False

    def test_young_tool_not_retired(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("young_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("young_tool", code)
            reg._total_runs = 3  # Only 3 runs old
            tool = reg.get("young_tool")
            tool.usage_count = 0
            tool.success_count = 0
            tool.creation_run = 0
            actions = reg.retirement_sweep()
            # Too young (min_age=5), should not be touched
            assert not any("DEACTIVATED" in a or "DELETED" in a for a in actions)


class TestPromotion:
    def test_promote_candidate_high_score(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("star_tool", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("star_tool", code)
            reg._total_runs = 25
            tool = reg.get("star_tool")
            tool.usage_count = 60
            tool.success_count = 59  # 98% success rate
            tool.creation_run = 0
            s = reg.stats()
            assert "star_tool" in s.get("promote_candidates", [])

    def test_no_promote_if_too_young(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("young_star", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("young_star", code)
            reg._total_runs = 10  # Only 10 runs
            tool = reg.get("young_star")
            tool.usage_count = 100
            tool.success_count = 100
            tool.creation_run = 0
            s = reg.stats()
            assert "young_star" not in s.get("promote_candidates", [])

    def test_no_promote_if_deactivated(self):
        with tempfile.TemporaryDirectory() as td:
            code = _make_tool_code("deactivated_star", ["current_hp"])
            reg = DynamicToolRegistry(td)
            reg.register_tool("deactivated_star", code)
            reg._total_runs = 25
            tool = reg.get("deactivated_star")
            tool.usage_count = 60
            tool.success_count = 59
            tool.creation_run = 0
            tool.deactivated = True
            s = reg.stats()
            assert "deactivated_star" not in s.get("promote_candidates", [])


class TestLifecycleIntegration:
    def test_full_lifecycle_generation_to_retirement(self):
        """Full lifecycle: generate -> use -> evaluate -> retire."""
        from src.brain.dynamic_tools import DynamicToolRegistry, compute_effectiveness

        with tempfile.TemporaryDirectory() as td:
            reg = DynamicToolRegistry(td)

            # 1. Generate — valid tool accepted
            code = _make_tool_code("lifecycle_test", ["current_hp", "incoming_damage"])
            result = reg.register_tool("lifecycle_test", code)
            assert "SUCCESS" in result
            assert reg.count == 1

            # 2. Generate — duplicate rejected
            code2 = _make_tool_code("lifecycle_test_v2", ["current_hp", "incoming_damage"])
            result2 = reg.register_tool("lifecycle_test_v2", code2)
            assert "REJECTED" in result2
            assert reg.count == 1  # Still only 1

            # 3. Use — tool executes and returns raw dict
            tool = reg.get("lifecycle_test")
            raw = tool.execute_raw(current_hp=50, incoming_damage=20)
            assert isinstance(raw, dict)
            assert raw["total"] == 70  # 50 + 20
            assert tool.usage_count == 1
            assert tool.success_count == 1

            # 4. Evaluate — effectiveness score
            reg._total_runs = 5
            score = compute_effectiveness(tool.usage_count, tool.success_count, runs_since=5)
            assert score == 0.2  # 1 use / 5 runs * 100% success

            # 5. Retire — low usage tool gets deactivated
            reg._total_runs = 10
            tool.usage_count = 0
            tool.success_count = 0
            tool.creation_run = 0
            actions = reg.retirement_sweep()
            assert tool.deactivated is True
            assert any("DEACTIVATED" in a for a in actions)

            # 6. Delete — second sweep deletes
            reg._total_runs = 20
            actions2 = reg.retirement_sweep()
            assert any("DELETED" in a for a in actions2)
            assert reg.get("lifecycle_test") is None
            assert not (Path(td) / "lifecycle_test.py").exists()
