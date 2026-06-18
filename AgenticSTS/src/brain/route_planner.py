"""Local route enumeration + scoring for STS2 map navigation.

Two-stage architecture:
1. Local: BFS/DFS enumerate all paths from current position to boss -> score
   with heuristic -> top N candidates.
2. LLM (Sonnet no-think, ~3-5s): Pick from top N with deck/gold/relic context.

Replaces the old approach of sending the full map DAG to the LLM for analysis
(44K tokens, 67s) with a local enumeration (~0ms) + lightweight LLM selection.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from src.mcp_client.upstream_models import RawMapGraphNodePayload

logger = logging.getLogger(__name__)

REST_NODE_TYPES = frozenset({"Rest", "RestSite"})
ELITE_EQUIVALENT_MONSTERS = 3

# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RoutePath:
    """An annotated route through the act map."""

    nodes: tuple[str, ...]           # node_type sequence ("Monster", "RestSite", ...)
    coords: tuple[tuple[int, int], ...]  # (col, row) sequence
    rest_count: int
    elite_count: int
    shop_count: int
    monster_count: int
    event_count: int
    treasure_count: int
    shop_positions: tuple[int, ...]  # 1-based step indices of shops
    pre_boss_node: str               # node type immediately before Boss


# ---------------------------------------------------------------------------
# Sorting (replaces numeric scoring)
# ---------------------------------------------------------------------------


def canonical_node_type(node_type: str) -> str:
    """Normalize synonymous node labels used by upstream map payloads."""
    if node_type in REST_NODE_TYPES:
        return "Rest"
    return node_type


def is_rest_node(node_type: str) -> bool:
    """Return True when the node represents a campfire/rest site."""
    return canonical_node_type(node_type) == "Rest"


def combat_equivalent(node_type: str) -> int:
    """Model node risk as equivalent hallway combats.

    One elite is treated as three hallway monster fights. Unknown/Event/Treasure
    nodes stay neutral here so route pacing is driven only by explicit combat
    commitments, as intended by the current heuristic.
    """
    node_type = canonical_node_type(node_type)
    if node_type == "Monster":
        return 1
    if node_type == "Elite":
        return ELITE_EQUIVALENT_MONSTERS
    return 0


def total_equivalent_combats(nodes: Sequence[str]) -> int:
    """Return total explicit combat risk for a route."""
    return sum(combat_equivalent(node_type) for node_type in nodes)


def segment_equivalent_combats(nodes: Sequence[str]) -> tuple[int, ...]:
    """Return equivalent combats in each segment between rest sites."""
    segments: list[int] = []
    current_segment = 0

    for node_type in nodes:
        if is_rest_node(node_type):
            segments.append(current_segment)
            current_segment = 0
            continue
        current_segment += combat_equivalent(node_type)

    segments.append(current_segment)
    return tuple(segments)


def average_combats_per_rest(route: RoutePath) -> float:
    """Average explicit combat risk per rest site.

    Routes with zero rests are treated as one giant segment so they are
    penalized instead of dividing by zero.
    """
    rest_sites = max(route.rest_count, 1)
    return total_equivalent_combats(route.nodes) / rest_sites


def max_combats_between_rests(route: RoutePath) -> int:
    """Worst equivalent-combat stretch on the route."""
    return max(segment_equivalent_combats(route.nodes), default=0)


GOLD_SHOP_THRESHOLD = 150


def _shop_sort_key(route: RoutePath) -> int:
    """0 = exactly 1 shop (best), 1 = otherwise."""
    return 0 if route.shop_count == 1 else 1


def _has_no_shop(route: RoutePath) -> bool:
    """True if route has zero shops — penalized when gold is high."""
    return route.shop_count == 0


def _max_shop_position(route: RoutePath) -> int:
    """Higher = shop closer to boss (better). 0 if no shops."""
    return max(route.shop_positions) if route.shop_positions else 0


def sort_routes(routes: list[RoutePath], gold: int = 0) -> list[RoutePath]:
    """Multi-key sort by player preference priority.

    When gold >= GOLD_SHOP_THRESHOLD, having at least one shop is boosted
    to priority #1. This prevents the agent from choosing a shop-less route
    when sitting on enough gold to meaningfully spend.

    Priority order (gold >= 150):
    1. **Routes with 0 shops penalized** (gold-aware)
    2. Max equivalent combats between rests ascending
    3. Average equivalent combats per rest ascending
    4. Total equivalent combats ascending (1 elite ~= 3 monsters)
    5. Elite count ascending
    6. Rest count descending
    7. Has exactly 1 shop preferred
    8. Shop position closer to Boss preferred
    9. Treasure count descending
    10. Event count descending

    Priority order (gold < 150): same but without #1.
    """
    need_shop = gold >= GOLD_SHOP_THRESHOLD

    return sorted(routes, key=lambda r: (
        _has_no_shop(r) if need_shop else False,  # gold-aware shop boost
        max_combats_between_rests(r),  # safer segment pacing first
        average_combats_per_rest(r),   # lower combat load per fire first
        total_equivalent_combats(r.nodes),
        r.elite_count,
        -r.rest_count,
        _shop_sort_key(r),             # 0 (1 shop) before 1 (other)
        -_max_shop_position(r),        # descending: later shop first
        -r.treasure_count,             # descending: more treasure first
        -r.event_count,                # descending: more events first
    ))


# ---------------------------------------------------------------------------
# Enumeration
# ---------------------------------------------------------------------------


def _count_types(path_types: tuple[str, ...]) -> dict[str, int]:
    """Count occurrences of each node type in a path."""
    counts: dict[str, int] = {}
    for t in path_types:
        t = canonical_node_type(t)
        counts[t] = counts.get(t, 0) + 1
    return counts


def enumerate_routes(
    map_nodes: Sequence[RawMapGraphNodePayload],
    max_paths: int = 100,
) -> list[RoutePath]:
    """Enumerate all paths from current position to boss row via DFS.

    The map is a DAG (rows always increase), so no cycles are possible.

    Args:
        map_nodes: All nodes in the map graph.
        max_paths: Maximum number of paths to collect before stopping.

    Returns:
        All discovered paths (up to max_paths), unsorted.
        Call sort_routes() to sort by player preference.
    """
    if not map_nodes:
        return []

    # Build lookup: (col, row) -> node
    node_lookup: dict[tuple[int, int], RawMapGraphNodePayload] = {
        (n.col, n.row): n for n in map_nodes
    }

    # Build adjacency: (col, row) -> list of (col, row) children
    adjacency: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for n in map_nodes:
        children = [(c.col, c.row) for c in n.children]
        adjacency[(n.col, n.row)] = children

    # Find starting nodes: is_current or is_available (next choices)
    # Priority: is_current first, then is_available
    current_nodes = [n for n in map_nodes if n.is_current]
    if not current_nodes:
        # No current node -- use available nodes as starting points
        current_nodes = [n for n in map_nodes if n.is_available]
    if not current_nodes:
        # Fallback: look for nodes that are visited but have unvisited children
        # (i.e. the player is at a completed node and needs to pick next)
        visited = [n for n in map_nodes if n.visited]
        if visited:
            # Use the visited node with the highest row (most recent)
            current_nodes = [max(visited, key=lambda n: n.row)]

    if not current_nodes:
        logger.warning("No starting nodes found in map")
        return []

    # Find boss nodes
    boss_coords: set[tuple[int, int]] = set()
    for n in map_nodes:
        if n.is_boss or n.is_second_boss:
            boss_coords.add((n.col, n.row))

    # If no explicit boss, use nodes at the maximum row
    if not boss_coords:
        max_row = max(n.row for n in map_nodes)
        boss_coords = {(n.col, n.row) for n in map_nodes if n.row == max_row}

    if not boss_coords:
        logger.warning("No boss nodes found in map")
        return []

    # DFS from each starting node to any boss node
    all_paths: list[RoutePath] = []

    for start_node in current_nodes:
        start_coord = (start_node.col, start_node.row)
        # Stack: (current_coord, path_coords_so_far, path_types_so_far)
        # We start from the children of the current node (the current node
        # is already visited / is our position, we want FUTURE nodes).
        start_children = adjacency.get(start_coord, [])

        if not start_children:
            # Current node has no children -- we might be at a boss already
            if start_coord in boss_coords:
                continue  # Already at boss, no route needed
            logger.debug("Start node (%d,%d) has no children", *start_coord)
            continue

        for first_child_coord in start_children:
            first_child = node_lookup.get(first_child_coord)
            if first_child is None:
                continue

            stack: list[tuple[tuple[int, int], list[tuple[int, int]], list[str]]] = [
                (first_child_coord, [first_child_coord], [first_child.node_type])
            ]

            while stack and len(all_paths) < max_paths:
                coord, path_coords, path_types = stack.pop()

                # Reached a boss node -- record this path
                if coord in boss_coords:
                    types_tuple = tuple(path_types)
                    coords_tuple = tuple(path_coords)
                    counts = _count_types(types_tuple)
                    shop_positions = tuple(
                        i + 1 for i, t in enumerate(types_tuple) if t == "Shop"
                    )
                    non_boss = [t for t in types_tuple if t != "Boss"]
                    pre_boss_node = non_boss[-1] if non_boss else "Boss"
                    route = RoutePath(
                        nodes=types_tuple,
                        coords=coords_tuple,
                        rest_count=counts.get("Rest", 0),
                        elite_count=counts.get("Elite", 0),
                        shop_count=counts.get("Shop", 0),
                        monster_count=counts.get("Monster", 0),
                        event_count=counts.get("Event", 0),
                        treasure_count=counts.get("Treasure", 0),
                        shop_positions=shop_positions,
                        pre_boss_node=pre_boss_node,
                    )
                    all_paths.append(route)
                    continue

                # Expand children
                children = adjacency.get(coord, [])
                if not children:
                    # Dead end (not a boss) -- discard this path
                    continue

                for child_coord in children:
                    child_node = node_lookup.get(child_coord)
                    if child_node is None:
                        continue
                    # Extend path (new list copies to avoid mutation)
                    new_coords = path_coords + [child_coord]
                    new_types = path_types + [child_node.node_type]
                    stack.append((child_coord, new_coords, new_types))

            if len(all_paths) >= max_paths:
                break

        if len(all_paths) >= max_paths:
            break

    logger.info(
        "Enumerated %d routes (max_paths=%d)",
        len(all_paths),
        max_paths,
    )

    return all_paths


# ---------------------------------------------------------------------------
# Prompt formatting
# ---------------------------------------------------------------------------


def format_routes_for_prompt(
    routes: list[RoutePath],
    top_n: int = 10,
) -> str:
    """Format top N routes as annotated candidate list for LLM selection.

    Each route shows the node sequence with coordinates and a feature
    annotation line (elite/rest/shop counts, shop position, pre-boss node).
    No numeric scores — the LLM reasons about trade-offs with full game state.
    """
    if not routes:
        return ""

    top_routes = routes[:top_n]
    lines: list[str] = []

    for i, route in enumerate(top_routes, 1):
        # Node sequence with coordinates
        parts = [f"{ntype}(c{c},r{r})" for ntype, (c, r) in zip(route.nodes, route.coords)]
        lines.append(f"{i}. {' -> '.join(parts)}")

        # Feature annotation
        annotations: list[str] = []
        annotations.append(f"{route.elite_count} Elite")
        annotations.append(f"{route.rest_count} Rest")
        annotations.append(f"avg/rest {average_combats_per_rest(route):.1f}")
        annotations.append(f"max gap {max_combats_between_rests(route)}")

        if route.shop_positions:
            shop_steps = ", ".join(str(s) for s in route.shop_positions)
            annotations.append(f"{route.shop_count} Shop(step {shop_steps})")
        else:
            annotations.append("0 Shop")

        annotations.append(f"{route.monster_count} Monster")
        annotations.append(f"eq combat {total_equivalent_combats(route.nodes)}")
        annotations.append(f"{route.event_count} Event")

        if route.treasure_count > 0:
            annotations.append(f"{route.treasure_count} Treasure")

        annotations.append(f"pre-boss: {route.pre_boss_node}")

        lines.append(f"   [{' | '.join(annotations)}]")

    return "\n".join(lines)
