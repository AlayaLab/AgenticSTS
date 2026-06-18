"""Tests for route re-plan trigger conditions."""

from __future__ import annotations

from src.brain.route_checker import ReplanReason, check_replan_needed
from src.brain.route_planner import RoutePath


def _make_route(nodes: tuple[str, ...]) -> RoutePath:
    """Build a minimal RoutePath for testing."""
    coords = tuple((0, i) for i in range(len(nodes)))
    shop_positions = tuple(i + 1 for i, t in enumerate(nodes) if t == "Shop")
    non_boss = [t for t in nodes if t != "Boss"]
    return RoutePath(
        nodes=nodes, coords=coords,
        rest_count=sum(1 for t in nodes if t in {"Rest", "RestSite"}),
        elite_count=sum(1 for t in nodes if t == "Elite"),
        shop_count=sum(1 for t in nodes if t == "Shop"),
        monster_count=sum(1 for t in nodes if t == "Monster"),
        event_count=sum(1 for t in nodes if t == "Event"),
        treasure_count=sum(1 for t in nodes if t == "Treasure"),
        shop_positions=shop_positions,
        pre_boss_node=non_boss[-1] if non_boss else "Boss",
    )


class TestCheckReplanNeeded:
    def test_no_replan_when_healthy(self):
        route = _make_route(("Monster", "Rest", "Boss"))
        reason = check_replan_needed(hp=50, gold=100, current_coord=(0, 0), route=route)
        assert reason is None

    def test_hp_danger_with_elite_ahead(self):
        # Player at (0,0) = completed first node, remaining = Elite, Rest, Boss
        route = _make_route(("Monster", "Elite", "Rest", "Boss"))
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 0), route=route)
        assert reason == ReplanReason.HP_DANGER

    def test_hp_danger_with_monsters_before_rest(self):
        # Player at (0,0), remaining = Monster, Monster, Rest, Boss
        route = _make_route(("Event", "Monster", "Monster", "Rest", "Boss"))
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 0), route=route)
        assert reason == ReplanReason.HP_DANGER

    def test_hp_low_but_safe_path_no_replan(self):
        # Player at (0,0), remaining = Rest, Monster, Monster, Boss — Rest is next
        route = _make_route(("Monster", "Rest", "Monster", "Monster", "Boss"))
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 0), route=route)
        assert reason is None  # next node is Rest, safe

    def test_hp_low_one_monster_before_rest_ok(self):
        # Player at (0,0), remaining = Monster, Rest, Monster, Boss — only 1 before Rest
        route = _make_route(("Event", "Monster", "Rest", "Monster", "Boss"))
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 0), route=route)
        assert reason is None  # only 1 monster before Rest, threshold is 2

    def test_restsite_alias_is_treated_as_rest(self):
        route = _make_route(("Event", "Monster", "RestSite", "Monster", "Boss"))
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 0), route=route)
        assert reason is None  # only 1 monster before RestSite, still safe

    def test_gold_surplus_no_shop(self):
        # Player at (0,0), remaining = Rest, Monster, Boss — no shop
        route = _make_route(("Monster", "Rest", "Monster", "Boss"))
        reason = check_replan_needed(hp=50, gold=400, current_coord=(0, 0), route=route)
        assert reason == ReplanReason.GOLD_NO_SHOP

    def test_gold_surplus_with_shop_no_replan(self):
        # Player at (0,0), remaining = Shop, Monster, Boss — has shop
        route = _make_route(("Monster", "Shop", "Monster", "Boss"))
        reason = check_replan_needed(hp=50, gold=400, current_coord=(0, 0), route=route)
        assert reason is None

    def test_path_deviation(self):
        route = _make_route(("Monster", "Rest", "Monster", "Boss"))
        # (5, 5) not in route coords → deviation
        reason = check_replan_needed(hp=50, gold=100, current_coord=(5, 5), route=route)
        assert reason == ReplanReason.PATH_DEVIATION

    def test_no_replan_when_route_almost_done(self):
        route = _make_route(("Boss",))
        reason = check_replan_needed(hp=10, gold=500, current_coord=(0, 0), route=route)
        assert reason is None  # only 1 node left

    def test_no_replan_two_nodes_left(self):
        route = _make_route(("Monster", "Boss"))
        reason = check_replan_needed(hp=10, gold=500, current_coord=(0, 0), route=route)
        assert reason is None  # 2 nodes left including current

    def test_no_route_returns_none(self):
        reason = check_replan_needed(hp=10, gold=500, current_coord=(0, 0), route=None)
        assert reason is None

    def test_hp_exactly_30_no_trigger(self):
        route = _make_route(("Elite", "Monster", "Monster", "Boss"))
        reason = check_replan_needed(hp=30, gold=100, current_coord=(0, 0), route=route)
        assert reason is None  # threshold is < 30, not <=

    def test_hp_29_triggers_with_danger(self):
        route = _make_route(("Elite", "Monster", "Monster", "Boss"))
        reason = check_replan_needed(hp=29, gold=100, current_coord=(0, 0), route=route)
        assert reason == ReplanReason.HP_DANGER

    def test_gold_exactly_200_triggers(self):
        route = _make_route(("Monster", "Rest", "Monster", "Boss"))
        reason = check_replan_needed(hp=50, gold=200, current_coord=(0, 0), route=route)
        assert reason == ReplanReason.GOLD_NO_SHOP

    def test_gold_199_no_trigger(self):
        route = _make_route(("Monster", "Rest", "Monster", "Boss"))
        reason = check_replan_needed(hp=50, gold=199, current_coord=(0, 0), route=route)
        assert reason is None

    def test_remaining_from_midroute(self):
        route = _make_route(("Monster", "Elite", "Rest", "Monster", "Boss"))
        # current at (0,1) = second node, remaining = Rest, Monster, Boss (3 nodes)
        reason = check_replan_needed(hp=20, gold=100, current_coord=(0, 1), route=route)
        # remaining has no elite before rest, only 0 monsters before rest
        assert reason is None
