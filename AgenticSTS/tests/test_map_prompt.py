"""Tests for map prompt builders (Scenario A and B)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.prompts.map import build_map_step_prompt, build_route_selection_prompt
from src.brain.route_planner import RoutePath


def _mock_gs(hp=50, max_hp=80, gold=200, act=1, floor=5, character="Silent"):
    gs = MagicMock()
    gs.player_hp = hp
    gs.player_max_hp = max_hp
    gs.hp_ratio = hp / max_hp
    gs.gold = gold
    gs.act = act
    gs.floor = floor
    gs.character = character
    gs.deck_size = 20
    gs.potions = []
    return gs


def _make_route(nodes, coords=None):
    if coords is None:
        coords = tuple((0, i) for i in range(len(nodes)))
    shop_positions = tuple(i + 1 for i, t in enumerate(nodes) if t == "Shop")
    non_boss = [t for t in nodes if t != "Boss"]
    return RoutePath(
        nodes=nodes, coords=coords,
        rest_count=sum(1 for t in nodes if t == "Rest"),
        elite_count=sum(1 for t in nodes if t == "Elite"),
        shop_count=sum(1 for t in nodes if t == "Shop"),
        monster_count=sum(1 for t in nodes if t == "Monster"),
        event_count=sum(1 for t in nodes if t == "Event"),
        treasure_count=sum(1 for t in nodes if t == "Treasure"),
        shop_positions=shop_positions,
        pre_boss_node=non_boss[-1] if non_boss else "Boss",
    )


class TestBuildRouteSelectionPrompt:
    def test_contains_route_selection_header(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest -> Boss\n   [0 Elite | 1 Rest]",
            relics=["Vajra"],
            strategic_thread="Need defense",
        )
        assert "## Route Selection" in text

    def test_contains_hp_gold(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(hp=45, gold=230),
            routes_text="1. Rest -> Boss",
        )
        assert "45" in text
        assert "230" in text

    def test_contains_strategic_thread(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest -> Boss",
            strategic_thread="Prioritize removal",
        )
        assert "Prioritize removal" in text

    def test_contains_routes(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest(c0,r1) -> Boss(c0,r2)\n   [0 Elite | 1 Rest]",
        )
        assert "Rest(c0,r1)" in text

    def test_contains_json_schema(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest -> Boss",
        )
        assert '"route"' in text
        assert '"reasoning"' in text

    def test_replan_reason_shown(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest -> Boss",
            replan_reason="HP is 20 with danger ahead",
        )
        assert "Re-routing because" in text
        assert "HP is 20" in text

    def test_no_replan_reason_when_empty(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(),
            routes_text="1. Rest -> Boss",
        )
        assert "Re-routing" not in text

    def test_character_and_deck_shown(self):
        text = build_route_selection_prompt(
            gs=_mock_gs(character="Silent"),
            routes_text="1. Rest -> Boss",
        )
        assert "Silent" in text
        assert "20 cards" in text


class TestBuildMapStepPrompt:
    def test_contains_navigation_header(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0, 1), (0, 2), (0, 3)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=0,
            options=[],
        )
        assert "## Map Navigation" in text

    def test_shows_here_marker(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0, 1), (0, 2), (0, 3)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=1,
            options=[],
        )
        assert "[HERE]" in text

    def test_shows_recommendation(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0, 1), (0, 2), (0, 3)))
        opt = MagicMock()
        opt.index = 0
        opt.node_type = "Shop"
        opt.col = 0
        opt.row = 2
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=1,
            options=[opt],
        )
        assert "route recommends" in text

    def test_deviation_message(self):
        route = _make_route(("Rest", "Boss"), coords=((0, 1), (0, 2)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=0,
            options=[],
        )
        assert "deviate" in text.lower()

    def test_next_recommended_node(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0, 1), (0, 2), (0, 3)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=1,
            options=[],
        )
        assert "Shop(c0,r2)" in text
        assert "step 2" in text
