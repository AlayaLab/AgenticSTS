"""Lightweight re-plan trigger checker for route navigation.

Runs at each map node with multiple options. Pure Python, no LLM calls.
"""

from __future__ import annotations

import enum

from src.brain.route_planner import RoutePath, combat_equivalent, is_rest_node


class ReplanReason(enum.Enum):
    HP_DANGER = "hp_danger"
    GOLD_NO_SHOP = "gold_no_shop"
    PATH_DEVIATION = "path_deviation"


def _get_remaining_nodes(
    route: RoutePath,
    current_coord: tuple[int, int],
) -> list[str]:
    """Get node types remaining after current_coord in the route.

    If current_coord is not in route, returns empty list (deviation).
    """
    try:
        idx = route.coords.index(current_coord)
        return list(route.nodes[idx + 1:])
    except ValueError:
        return []


def check_replan_needed(
    hp: int,
    gold: int,
    current_coord: tuple[int, int],
    route: RoutePath | None,
) -> ReplanReason | None:
    """Check whether the current state warrants a route re-plan.

    Returns the trigger reason, or None if no re-plan needed.
    """
    if route is None:
        return None

    # Check path deviation first (before remaining-length check,
    # since deviation returns empty remaining which would falsely
    # trigger the "short route" guard)
    if current_coord not in route.coords:
        return ReplanReason.PATH_DEVIATION

    remaining = _get_remaining_nodes(route, current_coord)

    # Short route (0-2 nodes to boss) — re-routing not actionable since
    # the player cannot avoid the immediate next nodes anyway.
    if len(remaining) <= 2:
        return None

    # Check HP danger: hp < 30 AND (elite ahead OR 2+ equivalent combats before next rest)
    if hp < 30:
        has_elite = "Elite" in remaining
        equivalent_combats_before_rest = 0
        for node_type in remaining:
            if is_rest_node(node_type):
                break
            equivalent_combats_before_rest += combat_equivalent(node_type)
        if has_elite or equivalent_combats_before_rest >= 2:
            return ReplanReason.HP_DANGER

    # Check gold surplus: gold >= 200 AND no shop remaining
    if gold >= 200 and "Shop" not in remaining:
        return ReplanReason.GOLD_NO_SHOP

    return None
