"""Tests for AgentLoop._refresh_live_remaining_route chosen-coord filter.

Regression: when two map options exist and the agent picks the non-preferred
one, the live remaining route cache must follow the chosen branch, not the
enumerator's top-scored branch. Without the filter, rest/shop prompts at the
next floor would show a path from the wrong branch (see F24 rest-site bug
observed in run_20260423_120959_0de3a9f4: F25 was Elite in reality but the
prompt showed F25 as RestSite because routes[0] started through the Unknown
branch).
"""
from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from src.mcp_client.upstream_models import (
    RawMapCoordPayload,
    RawMapGraphNodePayload,
)

from tests.conftest import make_loop


def _graph_node(
    col: int,
    row: int,
    node_type: str,
    children: list[tuple[int, int]] | None = None,
    is_current: bool = False,
    is_boss: bool = False,
) -> RawMapGraphNodePayload:
    return RawMapGraphNodePayload(
        col=col,
        row=row,
        node_type=node_type,
        state="REACHED" if is_current else "UNREACHED",
        visited=is_current,
        is_current=is_current,
        is_boss=is_boss,
        children=[RawMapCoordPayload(col=c, row=r) for c, r in (children or [])],
    )


def _build_gs_with_map(nodes: list[RawMapGraphNodePayload], act: int = 2, gold: int = 400):
    """Minimal gs-like object with only the attributes the method reads."""
    return SimpleNamespace(
        act=act,
        gold=gold,
        map=SimpleNamespace(nodes=nodes),
    )


def _build_branching_map() -> list[RawMapGraphNodePayload]:
    """F23 current → F24 has two children: Unknown and RestSite.

    Unknown branch (col=0): F24 Unknown → F25 RestSite → F26 Treasure → Boss
    RestSite branch (col=2): F24 RestSite → F25 Elite → F26 Monster → Boss

    With default sort_routes, the Unknown branch scores higher (more rests,
    no elites). Without chosen_coord, routes[0] == Unknown branch; the cache
    would then show F25: RestSite. With chosen_coord=(2, 7) (the RestSite
    F24 node), the filter forces routes through the RestSite branch, so the
    cache shows F25: Elite — matching reality at the next floor.

    Rows:
      row 6 = F23 (act_start_floor 17 + 6 + 1 = 24? Wait: floor_num = 17+row+1)
    Let me use row 6 → floor 24 (F24). So F23 is row 5.
    """
    # F23 (row 5) current, children = F24 Unknown (col 0) and F24 RestSite (col 2)
    f23 = _graph_node(col=1, row=5, node_type="Monster",
                     children=[(0, 6), (2, 6)], is_current=True)
    # Unknown branch
    f24_unknown = _graph_node(col=0, row=6, node_type="Unknown", children=[(0, 7)])
    f25_rest = _graph_node(col=0, row=7, node_type="RestSite", children=[(0, 8)])
    f26_treasure = _graph_node(col=0, row=8, node_type="Treasure", children=[(1, 9)])
    # RestSite branch
    f24_rest = _graph_node(col=2, row=6, node_type="RestSite", children=[(2, 7)])
    f25_elite = _graph_node(col=2, row=7, node_type="Elite", children=[(2, 8)])
    f26_monster = _graph_node(col=2, row=8, node_type="Monster", children=[(1, 9)])
    # Shared boss (row 9)
    boss = _graph_node(col=1, row=9, node_type="Boss", is_boss=True)
    return [f23, f24_unknown, f25_rest, f26_treasure, f24_rest, f25_elite, f26_monster, boss]


def test_refresh_without_chosen_coord_picks_routes_zero():
    """Without chosen_coord, enumerator picks the best-sorted route.

    In the branching map, the Unknown branch (more rests, no elites) wins.
    """
    client = MagicMock()
    loop = make_loop(client)
    gs = _build_gs_with_map(_build_branching_map(), act=2, gold=400)

    loop._refresh_live_remaining_route(gs)

    cache = loop._live_remaining_route
    assert cache is not None
    # Floor 24 entry (first hop) should be Unknown from the best-sorted route
    floor_map = dict(cache)
    assert floor_map.get(24) == "Unknown"
    assert floor_map.get(25) == "RestSite"  # stale cache would show this at rest


def test_refresh_with_chosen_coord_follows_actual_choice():
    """With chosen_coord set to the F24 RestSite node, cache follows that branch.

    This is the fix: after the agent picks F24 RestSite, subsequent rest/shop
    prompts see F25: Elite instead of the Unknown branch's F25: RestSite.
    """
    client = MagicMock()
    loop = make_loop(client)
    gs = _build_gs_with_map(_build_branching_map(), act=2, gold=400)

    # F24 RestSite lives at (col=2, row=6)
    loop._refresh_live_remaining_route(gs, chosen_coord=(2, 6))

    cache = loop._live_remaining_route
    assert cache is not None
    floor_map = dict(cache)
    assert floor_map.get(24) == "RestSite"
    assert floor_map.get(25) == "Elite"  # real path, not Unknown branch's F25
    assert floor_map.get(26) == "Monster"


def test_refresh_with_unmatched_chosen_coord_yields_empty_cache():
    """If chosen_coord matches no route's first coord, cache becomes None.

    Defensive: a stale or mis-derived chosen_coord should not silently
    fall back to routes[0].
    """
    client = MagicMock()
    loop = make_loop(client)
    gs = _build_gs_with_map(_build_branching_map(), act=2, gold=400)

    loop._refresh_live_remaining_route(gs, chosen_coord=(9, 9))

    assert loop._live_remaining_route is None
