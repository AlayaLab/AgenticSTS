"""Tests for src.brain.route_planner — local route enumeration + annotation sorting."""

from __future__ import annotations

import pytest

from src.brain.route_planner import (
    RoutePath,
    enumerate_routes,
    format_routes_for_prompt,
    sort_routes,
)
from src.mcp_client.upstream_models import RawMapCoordPayload, RawMapGraphNodePayload

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _node(
    col: int,
    row: int,
    node_type: str = "Monster",
    children: list[tuple[int, int]] | None = None,
    is_current: bool = False,
    is_available: bool = False,
    is_boss: bool = False,
    visited: bool = False,
) -> RawMapGraphNodePayload:
    """Build a minimal RawMapGraphNodePayload for testing."""
    child_payloads = [
        RawMapCoordPayload(col=c, row=r) for c, r in (children or [])
    ]
    return RawMapGraphNodePayload(
        col=col,
        row=row,
        node_type=node_type,
        state="REACHED" if visited else "UNREACHED",
        visited=visited,
        is_current=is_current,
        is_available=is_available,
        is_boss=is_boss,
        children=child_payloads,
    )


def _build_three_path_map() -> list[RawMapGraphNodePayload]:
    """Build a small map with 3 distinct paths to the boss.

    Layout (3 rows + boss):
        Row 0 (current): Monster(0,0)
        Row 1:           Rest(0,1)    Elite(1,1)    Shop(2,1)
        Row 2:           Event(0,2)   Monster(1,2)  Treasure(2,2)
        Row 3 (boss):    Boss(1,3)

    Paths:
        1. Monster -> Rest -> Event -> Boss
        2. Monster -> Elite -> Monster -> Boss
        3. Monster -> Shop -> Treasure -> Boss
    """
    nodes = [
        # Row 0: current position
        _node(0, 0, "Monster", children=[(0, 1), (1, 1), (2, 1)], is_current=True, visited=True),
        # Row 1: three choices
        _node(0, 1, "Rest", children=[(0, 2)]),
        _node(1, 1, "Elite", children=[(1, 2)]),
        _node(2, 1, "Shop", children=[(2, 2)]),
        # Row 2: each leads to boss
        _node(0, 2, "Event", children=[(1, 3)]),
        _node(1, 2, "Monster", children=[(1, 3)]),
        _node(2, 2, "Treasure", children=[(1, 3)]),
        # Row 3: boss
        _node(1, 3, "Boss", is_boss=True),
    ]
    return nodes


def _make_route(**kwargs) -> RoutePath:
    """Build a RoutePath with sensible defaults."""
    defaults = dict(
        nodes=("Monster", "Boss"),
        coords=((0, 1), (0, 2)),
        rest_count=0, elite_count=0, shop_count=0,
        monster_count=1, event_count=0, treasure_count=0,
        shop_positions=(), pre_boss_node="Monster",
    )
    defaults.update(kwargs)
    return RoutePath(**defaults)


# ---------------------------------------------------------------------------
# sort_routes tests
# ---------------------------------------------------------------------------


class TestSortRoutes:
    """Multi-key sort: gold-aware shop boost, pacing between rests, then classic tie-breakers."""

    def test_fewer_elites_wins(self):
        a = _make_route(elite_count=1, rest_count=1)
        b = _make_route(elite_count=0, rest_count=2)
        result = sort_routes([a, b])
        assert result[0] is b

    def test_more_rests_wins_when_elites_equal(self):
        a = _make_route(elite_count=0, rest_count=1)
        b = _make_route(elite_count=0, rest_count=2)
        result = sort_routes([a, b])
        assert result[0] is b

    def test_one_shop_preferred(self):
        no_shop = _make_route(rest_count=1, shop_count=0, shop_positions=())
        one_shop = _make_route(rest_count=1, shop_count=1, shop_positions=(2,))
        two_shop = _make_route(rest_count=0, shop_count=2, shop_positions=(1, 2))
        result = sort_routes([no_shop, two_shop, one_shop])
        assert result[0] is one_shop

    def test_shop_closer_to_boss_preferred(self):
        early_shop = _make_route(shop_count=1, shop_positions=(1,))
        late_shop = _make_route(shop_count=1, shop_positions=(3,))
        result = sort_routes([early_shop, late_shop])
        assert result[0] is late_shop

    def test_more_treasure_wins(self):
        a = _make_route(treasure_count=0)
        b = _make_route(treasure_count=1)
        result = sort_routes([a, b])
        assert result[0] is b

    def test_more_events_wins_lowest_priority(self):
        a = _make_route(event_count=0)
        b = _make_route(event_count=1)
        result = sort_routes([a, b])
        assert result[0] is b

    def test_gold_aware_shop_boost(self):
        """When gold >= 150, routes with shops should beat shop-less routes
        even if the shop-less route has better combat pacing."""
        no_shop = _make_route(rest_count=2, shop_count=0, shop_positions=())
        has_shop = _make_route(rest_count=1, shop_count=1, shop_positions=(2,))
        # Without gold: no_shop wins (more rests)
        result = sort_routes([no_shop, has_shop], gold=0)
        assert result[0] is no_shop
        # With gold: has_shop wins
        result = sort_routes([no_shop, has_shop], gold=200)
        assert result[0] is has_shop

    def test_gold_below_threshold_no_shop_boost(self):
        """Below 150 gold, shop preference stays at normal priority."""
        no_shop = _make_route(rest_count=2, shop_count=0, shop_positions=())
        has_shop = _make_route(rest_count=1, shop_count=1, shop_positions=(2,))
        result = sort_routes([no_shop, has_shop], gold=100)
        assert result[0] is no_shop

    def test_high_elite_route_loses_via_combat_load(self):
        """Two elites (6 eq combats) lose to 3 monsters (3 eq combats)."""
        lots_of_rest = _make_route(
            nodes=("Elite", "Rest", "Elite", "Rest", "Boss"),
            coords=((0, 1), (0, 2), (0, 3), (0, 4), (0, 5)),
            rest_count=2,
            elite_count=2,
            pre_boss_node="Rest",
        )
        less_rest = _make_route(
            nodes=("Monster", "Monster", "Monster", "Rest", "Boss"),
            coords=((1, 1), (1, 2), (1, 3), (1, 4), (1, 5)),
            rest_count=1,
            monster_count=3,
            pre_boss_node="Rest",
        )
        result = sort_routes([lots_of_rest, less_rest])
        assert result[0] is less_rest

    def test_shorter_max_gap_between_rests_wins(self):
        long_gap = _make_route(
            nodes=("Monster", "Monster", "Monster", "Monster", "Rest", "Boss"),
            coords=((0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6)),
            rest_count=1,
            monster_count=4,
            pre_boss_node="Rest",
        )
        split_gap = _make_route(
            nodes=("Monster", "Monster", "Rest", "Monster", "Monster", "Boss"),
            coords=((1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6)),
            rest_count=1,
            monster_count=4,
            pre_boss_node="Monster",
        )
        result = sort_routes([long_gap, split_gap])
        assert result[0] is split_gap

    def test_lower_average_combats_per_rest_wins_when_max_gap_ties(self):
        one_rest = _make_route(
            nodes=("Monster", "Monster", "Rest", "Monster", "Monster", "Boss"),
            coords=((0, 1), (0, 2), (0, 3), (0, 4), (0, 5), (0, 6)),
            rest_count=1,
            monster_count=4,
            pre_boss_node="Monster",
        )
        two_rests = _make_route(
            nodes=("Monster", "Monster", "Rest", "Monster", "Rest", "Monster", "Boss"),
            coords=((1, 1), (1, 2), (1, 3), (1, 4), (1, 5), (1, 6), (1, 7)),
            rest_count=2,
            monster_count=4,
            pre_boss_node="Monster",
        )
        result = sort_routes([one_rest, two_rests])
        assert result[0] is two_rests

    def test_empty_list(self):
        assert sort_routes([]) == []


# ---------------------------------------------------------------------------
# enumerate_routes tests
# ---------------------------------------------------------------------------


class TestEnumerateRoutes:
    def test_three_path_map_finds_all_paths(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        assert len(routes) == 3

    def test_three_path_map_types(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        all_type_seqs = {r.nodes for r in routes}
        assert ("Rest", "Event", "Boss") in all_type_seqs
        assert ("Elite", "Monster", "Boss") in all_type_seqs
        assert ("Shop", "Treasure", "Boss") in all_type_seqs

    def test_sorted_by_elite_count_after_sort(self):
        nodes = _build_three_path_map()
        routes = sort_routes(enumerate_routes(nodes))
        elite_counts = [r.elite_count for r in routes]
        assert elite_counts == sorted(elite_counts)

    def test_zero_elite_path_first_after_sort(self):
        nodes = _build_three_path_map()
        routes = sort_routes(enumerate_routes(nodes))
        assert routes[0].elite_count == 0

    def test_counts_populated(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        rest_route = next(r for r in routes if r.nodes[0] == "Rest")
        assert rest_route.rest_count == 1
        assert rest_route.elite_count == 0
        assert rest_route.event_count == 1

    def test_restsite_alias_counts_as_rest(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1)], is_current=True),
            _node(0, 1, "RestSite", children=[(0, 2)]),
            _node(0, 2, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 1
        assert routes[0].nodes == ("RestSite", "Boss")
        assert routes[0].rest_count == 1

    def test_shop_positions_populated(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        shop_route = next(r for r in routes if r.shop_count > 0)
        assert len(shop_route.shop_positions) == 1
        assert shop_route.shop_positions[0] >= 1

    def test_pre_boss_node_populated(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        for route in routes:
            non_boss = [t for t in route.nodes if t != "Boss"]
            if non_boss:
                assert route.pre_boss_node == non_boss[-1]

    def test_single_linear_path(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1)], is_current=True),
            _node(0, 1, "Rest", children=[(0, 2)]),
            _node(0, 2, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 1
        assert routes[0].nodes == ("Rest", "Boss")

    def test_current_near_boss(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1)], visited=True),
            _node(0, 1, "Rest", children=[(0, 2)], is_current=True),
            _node(0, 2, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 1
        assert routes[0].nodes == ("Boss",)

    def test_multiple_available_starts(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1), (1, 1)], is_current=True, visited=True),
            _node(0, 1, "Rest", children=[(0, 2)], is_available=True),
            _node(1, 1, "Elite", children=[(0, 2)], is_available=True),
            _node(0, 2, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 2

    def test_empty_map(self):
        routes = enumerate_routes([])
        assert routes == []

    def test_no_boss_uses_max_row(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1)], is_current=True),
            _node(0, 1, "Rest", children=[(0, 2)]),
            _node(0, 2, "Monster"),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 1
        assert routes[0].nodes == ("Rest", "Monster")

    def test_max_paths_cap(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes, max_paths=2)
        assert len(routes) <= 2

    def test_coords_populated(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        for route in routes:
            assert len(route.coords) == len(route.nodes)
            for coord in route.coords:
                assert len(coord) == 2

    def test_available_nodes_as_start_when_no_current(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1)], visited=True),
            _node(0, 1, "Rest", children=[(0, 2)], is_available=True),
            _node(0, 2, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes)
        assert len(routes) == 1
        assert routes[0].nodes == ("Boss",)


# ---------------------------------------------------------------------------
# format_routes_for_prompt tests
# ---------------------------------------------------------------------------


class TestFormatRoutesForPrompt:
    def test_annotation_line_format(self):
        routes = [
            _make_route(
                nodes=("Rest", "Shop", "Event", "Boss"),
                coords=((0,1), (0,2), (0,3), (1,4)),
                rest_count=1, elite_count=0, shop_count=1,
                event_count=1, treasure_count=0,
                shop_positions=(2,), pre_boss_node="Event",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "0 Elite" in text
        assert "1 Rest" in text
        assert "avg/rest" in text
        assert "max gap" in text
        assert "1 Shop" in text
        assert "pre-boss: Event" in text

    def test_shop_step_shown(self):
        routes = [
            _make_route(
                nodes=("Monster", "Shop", "Boss"),
                coords=((0,1), (0,2), (0,3)),
                shop_count=1, shop_positions=(2,), pre_boss_node="Shop",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "Shop(step 2)" in text

    def test_top_n_limits(self):
        routes = [_make_route() for _ in range(15)]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "10." in text
        assert "11." not in text

    def test_empty_routes_returns_empty(self):
        assert format_routes_for_prompt([], top_n=10) == ""

    def test_no_score_in_output(self):
        routes = [_make_route()]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "Score" not in text

    def test_coord_format(self):
        routes = [
            _make_route(
                nodes=("Rest", "Boss"),
                coords=((2, 5), (1, 6)),
                rest_count=1, pre_boss_node="Rest",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "Rest(c2,r5)" in text
        assert "Boss(c1,r6)" in text


# ---------------------------------------------------------------------------
# Integration: enumerate + sort + format round-trip
# ---------------------------------------------------------------------------


class TestIntegration:
    def test_enumerate_sort_and_format(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        sorted_routes = sort_routes(routes)
        assert format_routes_for_prompt(sorted_routes, top_n=10)
        assert len(routes) == 3
        # First route should have 0 elites
        assert sorted_routes[0].elite_count == 0

    def test_wide_map_with_many_paths(self):
        nodes = [
            _node(0, 0, "Monster", children=[(0, 1), (1, 1), (2, 1), (3, 1)], is_current=True),
            _node(0, 1, "Rest", children=[(0, 2), (1, 2)]),
            _node(1, 1, "Elite", children=[(1, 2), (2, 2)]),
            _node(2, 1, "Shop", children=[(2, 2), (3, 2)]),
            _node(3, 1, "Event", children=[(3, 2), (0, 2)]),
            _node(0, 2, "Monster", children=[(0, 3)]),
            _node(1, 2, "Treasure", children=[(0, 3)]),
            _node(2, 2, "Event", children=[(0, 3)]),
            _node(3, 2, "Rest", children=[(0, 3)]),
            _node(0, 3, "Boss", is_boss=True),
        ]
        routes = enumerate_routes(nodes, max_paths=50)
        assert len(routes) >= 8
        for route in routes:
            assert route.nodes[-1] == "Boss"

    def test_frozen_dataclass(self):
        route = _make_route()
        with pytest.raises(AttributeError):
            route.elite_count = 10  # type: ignore[misc]
