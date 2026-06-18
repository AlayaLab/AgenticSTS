"""Tests for the tiered thinking strategy.

Strategic tier: thinking ON (effort from config).
Fast tier: thinking OFF (effort="").
Post-run (call_raw): thinking ON, <thinking> tags stripped.
"""
import config
from src.brain.llm_caller import _THINKING_TAG_RE


class TestThinkingTagStrip:
    def test_strip_thinking_tags(self):
        text = "<thinking>\nSome analysis\n</thinking>\n\nActual response"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Actual response"

    def test_strip_multiple_thinking_blocks(self):
        text = "<thinking>A</thinking>\nMiddle\n<thinking>B</thinking>\nEnd"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Middle\nEnd"

    def test_no_thinking_tags_passthrough(self):
        text = "Normal response without thinking"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == text

    def test_empty_thinking_block(self):
        text = "<thinking></thinking>\nResponse"
        result = _THINKING_TAG_RE.sub("", text).strip()
        assert result == "Response"


class TestV2EngineTierRouting:
    def test_returns_tuple(self):
        from src.brain.v2_engine import V2Engine
        result = V2Engine._get_v2_tier("map")
        assert isinstance(result, tuple)
        assert len(result) == 3  # (provider, model, effort)

    def test_fast_tier_low_effort(self):
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier("map")
        assert isinstance(model, str)
        assert effort == config.LLM_THINK_EFFORT_FAST  # "low" — explicit thinking cap

    def test_strategic_tier_has_effort(self):
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier("combat_plan")
        assert isinstance(model, str)
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC
        assert effort != ""

    def test_replan_low_effort(self):
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier("combat_plan", is_replan=True)
        assert model == config.LLM_STRATEGIC_MODEL
        assert effort == "low"

    def test_unknown_state_defaults_strategic(self):
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier("unknown_state_xyz")
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC

    def test_all_fast_states(self):
        from src.brain.v2_engine import V2Engine
        for state in ("map", "hand_select", "treasure"):
            _p, _m, effort = V2Engine._get_v2_tier(state)
            assert effort == config.LLM_THINK_EFFORT_FAST, f"{state} should be fast tier"

    def test_all_strategic_states(self):
        from src.brain.v2_engine import V2Engine
        for state in ("combat_plan", "rest_site", "shop", "event",
                       "card_reward", "card_select", "monster", "elite", "boss"):
            _p, _m, effort = V2Engine._get_v2_tier(state)
            assert effort != "", f"{state} should be strategic tier (has effort)"

    def test_simple_uses_fast_tier(self):
        """simple=True routes combat_plan to the fast tier model."""
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier(
            "combat_plan", simple=True,
        )
        assert model == config.LLM_FAST_MODEL
        assert effort == config.LLM_THINK_EFFORT_FAST

    def test_simple_overrides_is_replan(self):
        """simple wins over is_replan — both flags True still routes to fast."""
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier(
            "combat_plan", is_replan=True, simple=True,
        )
        assert model == config.LLM_FAST_MODEL
        assert effort == config.LLM_THINK_EFFORT_FAST

    def test_simple_false_preserves_strategic(self):
        """simple=False keeps the existing strategic-tier routing."""
        from src.brain.v2_engine import V2Engine
        _provider, model, effort = V2Engine._get_v2_tier(
            "combat_plan", simple=False,
        )
        assert model == config.LLM_STRATEGIC_MODEL
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC

    def test_simple_default_is_false(self):
        """Calling without simple kwarg behaves as before (back-compat)."""
        from src.brain.v2_engine import V2Engine
        _p, model, effort = V2Engine._get_v2_tier("combat_plan")
        assert model == config.LLM_STRATEGIC_MODEL
        assert effort == config.LLM_THINK_EFFORT_STRATEGIC

    def test_generate_combat_plan_signature_accepts_simple(self):
        """generate_combat_plan accepts simple kwarg (Task 2 wiring)."""
        import inspect
        from src.brain.v2_engine import V2Engine
        sig = inspect.signature(V2Engine.generate_combat_plan)
        assert "simple" in sig.parameters
        assert sig.parameters["simple"].default is False
