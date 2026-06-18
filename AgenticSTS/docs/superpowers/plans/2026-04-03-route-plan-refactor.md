# Route Plan Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace rigid heuristic-scored route planning with annotation-based candidate generation, LLM-driven route selection, and condition-triggered re-planning.

**Architecture:** DFS enumeration (unchanged) produces candidate routes annotated with features (elite/rest/shop counts, shop position, pre-boss node). Routes are multi-key sorted by player preference priority instead of numeric scoring. A lightweight Python check at each map node detects HP danger, gold surplus, or path deviation to trigger re-planning. Two prompt scenarios: full-context route selection (Scenario A) and compact step-by-step walking (Scenario B).

**Tech Stack:** Python 3.11+, pytest, existing Anthropic `call_raw` for route selection LLM calls.

**Spec:** `docs/superpowers/specs/2026-04-03-route-plan-refactor-design.md`

---

### Task 1: Rewrite RoutePath dataclass and multi-key sorting

**Files:**
- Modify: `src/brain/route_planner.py:27-99` (RoutePath + score_route)
- Test: `tests/test_route_planner.py`

- [ ] **Step 1: Write failing tests for new RoutePath and sort_routes**

Replace the `TestScoreRoute` class entirely. Add new tests for the annotation-based sorting:

```python
# tests/test_route_planner.py — replace TestScoreRoute with:

from src.brain.route_planner import (
    RoutePath,
    enumerate_routes,
    sort_routes,
)


class TestSortRoutes:
    """Multi-key sort: elite↑, rest↓, 1-shop preferred, shop near boss, treasure↓, event↓."""

    def test_fewer_elites_wins(self):
        a = RoutePath(nodes=("Elite", "Rest", "Boss"), coords=((0,1),(0,2),(0,3)),
                      elite_count=1, rest_count=1, shop_count=0, monster_count=0,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Boss")
        b = RoutePath(nodes=("Rest", "Rest", "Boss"), coords=((1,1),(1,2),(0,3)),
                      elite_count=0, rest_count=2, shop_count=0, monster_count=0,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Boss")
        result = sort_routes([a, b])
        assert result[0] is b  # 0 elite beats 1 elite

    def test_more_rests_wins_when_elites_equal(self):
        a = RoutePath(nodes=("Rest", "Monster", "Boss"), coords=((0,1),(0,2),(0,3)),
                      elite_count=0, rest_count=1, shop_count=0, monster_count=1,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Boss")
        b = RoutePath(nodes=("Rest", "Rest", "Boss"), coords=((1,1),(1,2),(0,3)),
                      elite_count=0, rest_count=2, shop_count=0, monster_count=0,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Boss")
        result = sort_routes([a, b])
        assert result[0] is b  # 2 rest beats 1 rest

    def test_one_shop_preferred(self):
        no_shop = RoutePath(nodes=("Rest", "Monster", "Boss"), coords=((0,1),(0,2),(0,3)),
                            elite_count=0, rest_count=1, shop_count=0, monster_count=1,
                            event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Boss")
        one_shop = RoutePath(nodes=("Rest", "Shop", "Boss"), coords=((1,1),(1,2),(0,3)),
                             elite_count=0, rest_count=1, shop_count=1, monster_count=0,
                             event_count=0, treasure_count=0, shop_positions=(2,), pre_boss_node="Boss")
        two_shop = RoutePath(nodes=("Shop", "Shop", "Boss"), coords=((2,1),(2,2),(0,3)),
                             elite_count=0, rest_count=0, shop_count=2, monster_count=0,
                             event_count=0, treasure_count=0, shop_positions=(1, 2), pre_boss_node="Boss")
        result = sort_routes([no_shop, two_shop, one_shop])
        assert result[0] is one_shop  # exactly 1 shop wins

    def test_shop_closer_to_boss_preferred(self):
        early_shop = RoutePath(nodes=("Shop", "Monster", "Monster", "Boss"), coords=((0,1),(0,2),(0,3),(0,4)),
                               elite_count=0, rest_count=0, shop_count=1, monster_count=2,
                               event_count=0, treasure_count=0, shop_positions=(1,), pre_boss_node="Monster")
        late_shop = RoutePath(nodes=("Monster", "Monster", "Shop", "Boss"), coords=((1,1),(1,2),(1,3),(0,4)),
                              elite_count=0, rest_count=0, shop_count=1, monster_count=2,
                              event_count=0, treasure_count=0, shop_positions=(3,), pre_boss_node="Shop")
        result = sort_routes([early_shop, late_shop])
        assert result[0] is late_shop  # shop at step 3 beats step 1

    def test_more_treasure_wins(self):
        a = RoutePath(nodes=("Monster", "Monster", "Boss"), coords=((0,1),(0,2),(0,3)),
                      elite_count=0, rest_count=0, shop_count=0, monster_count=2,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Monster")
        b = RoutePath(nodes=("Treasure", "Monster", "Boss"), coords=((1,1),(1,2),(0,3)),
                      elite_count=0, rest_count=0, shop_count=0, monster_count=1,
                      event_count=0, treasure_count=1, shop_positions=(), pre_boss_node="Monster")
        result = sort_routes([a, b])
        assert result[0] is b

    def test_more_events_wins_lowest_priority(self):
        a = RoutePath(nodes=("Monster", "Monster", "Boss"), coords=((0,1),(0,2),(0,3)),
                      elite_count=0, rest_count=0, shop_count=0, monster_count=2,
                      event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Monster")
        b = RoutePath(nodes=("Event", "Monster", "Boss"), coords=((1,1),(1,2),(0,3)),
                      elite_count=0, rest_count=0, shop_count=0, monster_count=1,
                      event_count=1, treasure_count=0, shop_positions=(), pre_boss_node="Monster")
        result = sort_routes([a, b])
        assert result[0] is b
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_route_planner.py::TestSortRoutes -v`
Expected: FAIL — `sort_routes` does not exist, `RoutePath` missing new fields.

- [ ] **Step 3: Rewrite RoutePath and implement sort_routes**

In `src/brain/route_planner.py`, replace the `RoutePath` dataclass and `score_route()` function:

```python
@dataclass(frozen=True)
class RoutePath:
    """An annotated route through the act map."""

    nodes: tuple[str, ...]           # node_type sequence ("Monster", "Rest", ...)
    coords: tuple[tuple[int, int], ...]  # (col, row) sequence
    rest_count: int
    elite_count: int
    shop_count: int
    monster_count: int
    event_count: int
    treasure_count: int
    shop_positions: tuple[int, ...]  # 1-based step indices of shops
    pre_boss_node: str               # node type immediately before Boss


def _shop_sort_key(route: RoutePath) -> int:
    """0 = exactly 1 shop (best), 1 = otherwise."""
    return 0 if route.shop_count == 1 else 1


def _max_shop_position(route: RoutePath) -> int:
    """Higher = shop closer to boss (better). 0 if no shops."""
    return max(route.shop_positions) if route.shop_positions else 0


def sort_routes(routes: list[RoutePath]) -> list[RoutePath]:
    """Multi-key sort by player preference priority.

    Priority order:
    1. Elite count ascending (fewer = better)
    2. Rest count descending (more = better)
    3. Has exactly 1 shop preferred
    4. Shop position closer to Boss preferred (higher step = better)
    5. Treasure count descending (more = better)
    6. Event count descending (lowest priority)
    """
    return sorted(routes, key=lambda r: (
        r.elite_count,           # ascending: fewer elites first
        -r.rest_count,           # descending: more rests first
        _shop_sort_key(r),       # 0 (1 shop) before 1 (other)
        -_max_shop_position(r),  # descending: later shop first
        -r.treasure_count,       # descending: more treasure first
        -r.event_count,          # descending: more events first
    ))
```

Also delete the `_NODE_SCORES` dict and `score_route()` function entirely.

- [ ] **Step 4: Update enumerate_routes to populate new fields**

In `enumerate_routes()`, where `RoutePath` is constructed (around line 213), update:

```python
                    types_tuple = tuple(path_types)
                    coords_tuple = tuple(path_coords)
                    counts = _count_types(types_tuple)

                    # Shop step positions (1-based)
                    shop_positions = tuple(
                        i + 1 for i, t in enumerate(types_tuple) if t == "Shop"
                    )
                    # Node immediately before Boss (or "Boss" if path is just Boss)
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
```

Replace the final sort line `all_paths.sort(key=lambda r: r.score, reverse=True)` with:

```python
    all_paths = sort_routes(all_paths)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/test_route_planner.py::TestSortRoutes -v`
Expected: All PASS.

- [ ] **Step 6: Fix existing enumerate tests for new RoutePath fields**

Update `TestEnumerateRoutes` — remove all `score`-related assertions. The `test_sorted_by_score_descending` and `test_rest_path_scores_highest` tests need rewriting:

```python
    def test_sorted_by_elite_count(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        elite_counts = [r.elite_count for r in routes]
        assert elite_counts == sorted(elite_counts)  # ascending

    def test_zero_elite_path_first(self):
        nodes = _build_three_path_map()
        routes = enumerate_routes(nodes)
        assert routes[0].elite_count == 0
```

Remove `test_hp_ratio_affects_elite_scoring` (no more hp_ratio in scoring). Remove `hp_ratio` param from `enumerate_routes` calls in tests.

Also update `TestFormatRoutesForPrompt` and `TestIntegration` to use new RoutePath fields (remove `score=`, add `shop_positions=()`, `pre_boss_node="Boss"`).

- [ ] **Step 7: Run full test suite**

Run: `python -m pytest tests/test_route_planner.py -v`
Expected: All PASS.

- [ ] **Step 8: Commit**

```bash
git add src/brain/route_planner.py tests/test_route_planner.py
git commit -m "refactor: replace route scoring with annotation-based multi-key sort"
```

---

### Task 2: Rewrite format_routes_for_prompt with annotation format

**Files:**
- Modify: `src/brain/route_planner.py:266-342` (format functions)
- Test: `tests/test_route_planner.py`

- [ ] **Step 1: Write failing tests for new annotation format**

```python
class TestFormatRoutesAnnotated:
    def test_annotation_line_format(self):
        routes = [
            RoutePath(
                nodes=("Rest", "Shop", "Event", "Boss"),
                coords=((0,1), (0,2), (0,3), (1,4)),
                rest_count=1, elite_count=0, shop_count=1, monster_count=0,
                event_count=1, treasure_count=0,
                shop_positions=(2,), pre_boss_node="Event",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        # Should contain annotation line with counts
        assert "0 Elite" in text
        assert "1 Rest" in text
        assert "1 Shop" in text
        assert "pre-boss: Event" in text

    def test_shop_step_shown(self):
        routes = [
            RoutePath(
                nodes=("Monster", "Shop", "Boss"),
                coords=((0,1), (0,2), (0,3)),
                rest_count=0, elite_count=0, shop_count=1, monster_count=1,
                event_count=0, treasure_count=0,
                shop_positions=(2,), pre_boss_node="Shop",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "Shop(step 2" in text or "1 Shop(step 2)" in text

    def test_top_n_limits(self):
        routes = [
            RoutePath(
                nodes=("Monster", "Boss"), coords=((0,1),(0,2)),
                rest_count=0, elite_count=0, shop_count=0, monster_count=1,
                event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Monster",
            )
            for _ in range(15)
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "10." in text
        assert "11." not in text

    def test_empty_routes_returns_empty(self):
        assert format_routes_for_prompt([], top_n=10) == ""

    def test_no_score_in_output(self):
        routes = [
            RoutePath(
                nodes=("Rest", "Boss"), coords=((0,1),(0,2)),
                rest_count=1, elite_count=0, shop_count=0, monster_count=0,
                event_count=0, treasure_count=0, shop_positions=(), pre_boss_node="Rest",
            ),
        ]
        text = format_routes_for_prompt(routes, top_n=10)
        assert "Score" not in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_route_planner.py::TestFormatRoutesAnnotated -v`
Expected: FAIL — signature mismatch (old params hp/max_hp/gold/deck_size removed).

- [ ] **Step 3: Rewrite format_routes_for_prompt**

```python
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

        if route.shop_positions:
            shop_steps = ", ".join(str(s) for s in route.shop_positions)
            annotations.append(f"{route.shop_count} Shop(step {shop_steps})")
        else:
            annotations.append("0 Shop")

        annotations.append(f"{route.monster_count} Monster")
        annotations.append(f"{route.event_count} Event")

        if route.treasure_count > 0:
            annotations.append(f"{route.treasure_count} Treasure")

        annotations.append(f"pre-boss: {route.pre_boss_node}")

        lines.append(f"   [{' | '.join(annotations)}]")

    return "\n".join(lines)


def format_routes_for_llm_selection(routes_prompt: str) -> str:
    """Append LLM response schema for route selection call."""
    return (
        routes_prompt
        + '\n\nChoose the route that best fits your current state. Respond with:\n'
        '```json\n{"route": <number>, "reasoning": "..."}\n```'
    )
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_route_planner.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/brain/route_planner.py tests/test_route_planner.py
git commit -m "refactor: annotation-based route formatting (no scores)"
```

---

### Task 3: Implement re-plan condition checker

**Files:**
- Create: `src/brain/route_checker.py`
- Test: `tests/test_route_checker.py`

- [ ] **Step 1: Write failing tests for _should_replan**

```python
# tests/test_route_checker.py
"""Tests for route re-plan trigger conditions."""

from __future__ import annotations

import pytest

from src.brain.route_checker import ReplanReason, check_replan_needed
from src.brain.route_planner import RoutePath


def _make_route(nodes: tuple[str, ...]) -> RoutePath:
    """Build a minimal RoutePath for testing."""
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


class TestCheckReplanNeeded:
    def test_no_replan_when_healthy(self):
        route = _make_route(("Monster", "Rest", "Boss"))
        # current_coord at (0,0) which is the start, remaining is full route
        reason = check_replan_needed(
            hp=50, gold=100,
            current_coord=(0, 0),
            route=route,
        )
        assert reason is None

    def test_hp_danger_with_elite_ahead(self):
        route = _make_route(("Elite", "Rest", "Boss"))
        reason = check_replan_needed(
            hp=20, gold=100,
            current_coord=(0, 0),
            route=route,
        )
        assert reason == ReplanReason.HP_DANGER

    def test_hp_danger_with_monsters_before_rest(self):
        route = _make_route(("Monster", "Monster", "Rest", "Boss"))
        reason = check_replan_needed(
            hp=20, gold=100,
            current_coord=(0, 0),
            route=route,
        )
        assert reason == ReplanReason.HP_DANGER

    def test_hp_low_but_safe_path_no_replan(self):
        route = _make_route(("Rest", "Monster", "Boss"))
        reason = check_replan_needed(
            hp=20, gold=100,
            current_coord=(0, 0),
            route=route,
        )
        assert reason is None  # next node is Rest, safe

    def test_gold_surplus_no_shop(self):
        route = _make_route(("Monster", "Rest", "Boss"))
        reason = check_replan_needed(
            hp=50, gold=400,
            current_coord=(0, 0),
            route=route,
        )
        assert reason == ReplanReason.GOLD_NO_SHOP

    def test_gold_surplus_with_shop_no_replan(self):
        route = _make_route(("Shop", "Monster", "Boss"))
        reason = check_replan_needed(
            hp=50, gold=400,
            current_coord=(0, 0),
            route=route,
        )
        assert reason is None

    def test_path_deviation(self):
        route = _make_route(("Monster", "Rest", "Boss"))
        # current_coord not in route.coords
        reason = check_replan_needed(
            hp=50, gold=100,
            current_coord=(5, 5),
            route=route,
        )
        assert reason == ReplanReason.PATH_DEVIATION

    def test_no_replan_when_route_almost_done(self):
        route = _make_route(("Boss",))
        reason = check_replan_needed(
            hp=10, gold=500,
            current_coord=(0, 0),
            route=route,
        )
        assert reason is None  # only 1 node left, not worth re-planning

    def test_no_route_returns_none(self):
        reason = check_replan_needed(
            hp=10, gold=500,
            current_coord=(0, 0),
            route=None,
        )
        assert reason is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_route_checker.py -v`
Expected: FAIL — module `src.brain.route_checker` does not exist.

- [ ] **Step 3: Implement route_checker.py**

```python
# src/brain/route_checker.py
"""Lightweight re-plan trigger checker for route navigation.

Runs at each map node with multiple options. Pure Python, no LLM calls.
"""

from __future__ import annotations

import enum

from src.brain.route_planner import RoutePath


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

    remaining = _get_remaining_nodes(route, current_coord)

    # Short route (0-2 nodes to boss) — not worth re-planning
    if len(remaining) <= 2:
        return None

    # Check path deviation: current_coord not in route
    if current_coord not in route.coords:
        return ReplanReason.PATH_DEVIATION

    # Check HP danger: hp < 25 AND (elite ahead OR 2+ monsters before next rest)
    if hp < 25:
        has_elite = "Elite" in remaining
        # Count monsters before first Rest
        monsters_before_rest = 0
        for node_type in remaining:
            if node_type == "Rest":
                break
            if node_type == "Monster":
                monsters_before_rest += 1
        if has_elite or monsters_before_rest >= 2:
            return ReplanReason.HP_DANGER

    # Check gold surplus: gold >= 350 AND no shop remaining
    if gold >= 350 and "Shop" not in remaining:
        return ReplanReason.GOLD_NO_SHOP

    return None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/test_route_checker.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/brain/route_checker.py tests/test_route_checker.py
git commit -m "feat: add route re-plan condition checker"
```

---

### Task 4: Rewrite map prompts (Scenario A and Scenario B)

**Files:**
- Modify: `src/brain/prompts/map.py`
- Test: `tests/test_map_prompt.py` (create)

- [ ] **Step 1: Write failing tests for new prompt builders**

```python
# tests/test_map_prompt.py
"""Tests for map prompt builders (Scenario A and B)."""

from __future__ import annotations

from unittest.mock import MagicMock

from src.brain.prompts.map import build_route_selection_prompt, build_map_step_prompt
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


class TestBuildMapStepPrompt:
    def test_contains_navigation_header(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0,1),(0,2),(0,3)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=0,
            options=[],
        )
        assert "## Map Navigation" in text

    def test_shows_current_route_with_here_marker(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0,1),(0,2),(0,3)))
        text = build_map_step_prompt(
            gs=_mock_gs(),
            route=route,
            current_step_index=1,
            options=[],
        )
        assert "[HERE]" in text

    def test_shows_recommendation(self):
        route = _make_route(("Rest", "Shop", "Boss"), coords=((0,1),(0,2),(0,3)))
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
        assert "route recommends" in text.lower() or "Shop" in text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m pytest tests/test_map_prompt.py -v`
Expected: FAIL — `build_route_selection_prompt` and `build_map_step_prompt` not found.

- [ ] **Step 3: Rewrite map.py with two prompt builders**

```python
# src/brain/prompts/map.py
# ruff: noqa: E501
"""Prompt templates for map navigation decisions.

Two scenarios:
- Scenario A (build_route_selection_prompt): Full-context route selection
  at act start or on re-plan trigger.
- Scenario B (build_map_step_prompt): Compact step-by-step walking with
  existing plan.
"""

from __future__ import annotations

from src.brain.prompts._relic_fmt import format_relic_hints
from src.brain.route_planner import RoutePath
from src.state.game_state import GameState


def build_route_selection_prompt(
    gs: GameState,
    routes_text: str,
    relics: list[str] | None = None,
    strategic_thread: str = "",
    replan_reason: str = "",
) -> str:
    """Build Scenario A prompt: full-context route selection.

    Used at act start or when re-plan is triggered. Includes full game
    state so the LLM can make an informed route choice.
    """
    lines = [
        "## Route Selection",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold} | Act: {gs.act} | Floor: {gs.floor}",
    ]

    if gs.character:
        lines.append(f"Character: {gs.character} | Deck: {gs.deck_size} cards")

    # Potions
    if gs.potions:
        potion_names = [p.name for p in gs.potions if p.name]
        if potion_names:
            lines.append(f"Potions: [{', '.join(potion_names)}]")

    # Relics
    relic_section = format_relic_hints(relics or [], context="map")
    if relic_section:
        lines.append(relic_section)

    # Strategic thread
    if strategic_thread:
        lines.append(f"\nStrategic Thread: {strategic_thread}")

    # Re-plan reason
    if replan_reason:
        lines.append(f"\n**Re-routing because:** {replan_reason}")

    # Candidate routes
    lines.append("")
    lines.append("## Candidate Routes (from current position to Boss)")
    lines.append(routes_text)

    # Response schema
    lines.append("")
    lines.append('Choose the route that best fits your current state. Respond with:')
    lines.append('```json')
    lines.append('{"route": <number>, "reasoning": "..."}')
    lines.append('```')

    return "\n".join(lines)


def build_map_step_prompt(
    gs: GameState,
    route: RoutePath,
    current_step_index: int,
    options: list,
    relics: list[str] | None = None,
) -> str:
    """Build Scenario B prompt: compact step-by-step walking.

    Used for normal per-node decisions when a plan exists and no re-plan
    is triggered. Shows the route with a [HERE] marker and recommends
    the next node.
    """
    lines = [
        "## Map Navigation",
        f"HP: {gs.player_hp}/{gs.player_max_hp} ({gs.hp_ratio:.0%}) | Gold: {gs.gold} | Act: {gs.act} | Floor: {gs.floor}",
    ]

    # Show route with [HERE] marker
    route_parts: list[str] = []
    for i, ntype in enumerate(route.nodes):
        if i == current_step_index:
            route_parts.append("[HERE]")
        route_parts.append(ntype)
    if current_step_index >= len(route.nodes):
        route_parts.append("[HERE]")

    lines.append(f"\nCurrent route: {' -> '.join(route_parts)}")

    # Recommend next node
    next_idx = current_step_index
    if next_idx < len(route.nodes):
        next_type = route.nodes[next_idx]
        next_coord = route.coords[next_idx]
        lines.append(f"Next recommended: {next_type}(c{next_coord[0]},r{next_coord[1]}) -- step {next_idx + 1} of route")

    # Available options
    lines.append("\nAvailable nodes:")
    recommended_coord = route.coords[next_idx] if next_idx < len(route.coords) else None
    for opt in options:
        marker = "  <- route recommends" if (opt.col, opt.row) == recommended_coord else ""
        lines.append(f"- [index={opt.index}] {opt.node_type} at c{opt.col},r{opt.row}{marker}")

    relic_section = format_relic_hints(relics or [], context="map")
    if relic_section:
        lines.append("")
        lines.append(relic_section)

    lines.append("\nYou may deviate from the route. Explain why if you do.")

    return "\n".join(lines)
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest tests/test_map_prompt.py -v`
Expected: All PASS.

- [ ] **Step 5: Commit**

```bash
git add src/brain/prompts/map.py tests/test_map_prompt.py
git commit -m "feat: split map prompt into route selection (A) and step walking (B)"
```

---

### Task 5: Wire new route planning into agent loop

**Files:**
- Modify: `src/agent/loop.py:136-159` (state vars), `1095-1113` (reset), `3127-3144` (prompt builder), `3354-3356` (decision flow), `4596-4755` (_maybe_plan_route + _build_remaining_route)

This is the integration task — connects Tasks 1-4 into the live agent loop.

- [ ] **Step 1: Update state variables**

In `src/agent/loop.py`, replace route-related state vars (around lines 136, 157-159):

```python
        # Old — delete these 3 lines:
        # self._route_plan: str = ""
        # self._route_coords: tuple[tuple[int, int], ...] = ()
        # self._route_node_types: tuple[str, ...] = ()

        # New — single structured route:
        self._route_plan: RoutePath | None = None  # Selected route for current act
```

Add import at top of file:

```python
from src.brain.route_checker import ReplanReason, check_replan_needed
```

- [ ] **Step 2: Update reset_for_new_run**

In `reset_for_new_run()` (around line 1110-1113), replace:

```python
        # Old — delete these 3 lines:
        # self._route_plan = ""
        # self._route_coords = ()
        # self._route_node_types = ()

        # New:
        self._route_plan = None
```

- [ ] **Step 3: Update _build_state_prompt_v2 for map**

In `_build_state_prompt_v2()` (around line 3138-3144), replace the map branch:

```python
        if gs.is_map:
            # Scenario B is handled here; Scenario A is handled in _decide_and_act
            # before this method is called (route selection bypasses normal prompt flow)
            if self._route_plan is not None:
                current_step = self._find_current_step_index(gs)
                return build_map_step_prompt(
                    gs,
                    route=self._route_plan,
                    current_step_index=current_step,
                    options=gs.next_map_options,
                    relics=relics,
                )
            # No plan — basic options list (fallback)
            lines = ["## Map Navigation",
                     f"HP: {gs.player_hp}/{gs.player_max_hp} | Gold: {gs.gold} | Act: {gs.act}",
                     "\nAvailable nodes:"]
            for opt in gs.next_map_options:
                lines.append(f"- [index={opt.index}] {opt.node_type} at c{opt.col},r{opt.row}")
            return "\n".join(lines)
```

Update the import at top to use new prompt functions:

```python
from src.brain.prompts.map import build_route_selection_prompt, build_map_step_prompt
```

Add a helper method `_find_current_step_index`:

```python
    def _find_current_step_index(self, gs: GameState) -> int:
        """Find where the player currently is in the planned route."""
        if self._route_plan is None:
            return 0
        # Match current map position to route coordinates
        if gs.map and gs.map.current_node:
            current = (gs.map.current_node.col, gs.map.current_node.row)
            try:
                return self._route_plan.coords.index(current) + 1
            except ValueError:
                pass
        # Fallback: estimate from floor number
        return 0
```

- [ ] **Step 4: Update map decision flow in _decide_and_act**

Replace lines 3354-3356 with the new decision flow:

```python
        # Route planning + re-plan check (multi-option map nodes only)
        if in_map and gs.next_map_options and len(gs.next_map_options) > 1:
            route_decision = await self._handle_map_route_decision(gs)
            if route_decision is not None:
                return route_decision
```

Add the new `_handle_map_route_decision` method:

```python
    async def _handle_map_route_decision(self, gs: GameState) -> Decision | None:
        """Handle map route selection or re-plan if triggered.

        Returns a Decision if route selection consumed the step (Scenario A),
        or None to fall through to normal V2Engine decision (Scenario B).
        """
        current_act = gs.act

        # Determine current coordinate for re-plan check
        current_coord = None
        if gs.map and gs.map.current_node:
            current_coord = (gs.map.current_node.col, gs.map.current_node.row)

        need_plan = False
        replan_reason_str = ""

        if self._route_plan is None or current_act != self._planned_act:
            # No plan yet (act start)
            need_plan = True
        elif current_coord is not None:
            # Check re-plan conditions
            reason = check_replan_needed(
                hp=gs.player_hp,
                gold=gs.gold,
                current_coord=current_coord,
                route=self._route_plan,
            )
            if reason is not None:
                need_plan = True
                replan_reason_str = {
                    ReplanReason.HP_DANGER: f"HP is {gs.player_hp} with danger ahead",
                    ReplanReason.GOLD_NO_SHOP: f"Gold is {gs.gold} but no shop on current route",
                    ReplanReason.PATH_DEVIATION: "Deviated from planned route",
                }[reason]
                logger.info("Route re-plan triggered: %s", reason.value)
                self._emit_monitor("route_replan", {
                    "reason": reason.value,
                    "hp": gs.player_hp,
                    "gold": gs.gold,
                    "detail": replan_reason_str,
                })

        if need_plan:
            await self._select_route(gs, replan_reason=replan_reason_str)
            # After route selection, fall through to Scenario B prompt
            # (the selected route is stored, normal V2Engine handles node choice)

        return None  # Always fall through to V2Engine for the actual node selection
```

- [ ] **Step 5: Rewrite _maybe_plan_route as _select_route**

Replace the entire `_maybe_plan_route` method (lines 4596-4736) with:

```python
    async def _select_route(self, gs: GameState, replan_reason: str = "") -> None:
        """Generate candidate routes and let LLM select one.

        Called at act start and when re-plan is triggered.
        """
        if not gs.is_map or not gs.map or not gs.map.nodes:
            return
        if not gs.run:
            return

        current_act = gs.act
        logger.info("Selecting route for Act %d (%d map nodes)%s",
                     current_act, len(gs.map.nodes),
                     f" [re-plan: {replan_reason}]" if replan_reason else "")

        routes = enumerate_routes(gs.map.nodes, max_paths=100)

        if not routes:
            logger.warning("No routes enumerated — no plan available")
            self._route_plan = None
            return

        # Sort by player preference
        routes = sort_routes(routes)

        # Apply re-plan filters
        if replan_reason and "HP" in replan_reason:
            # HP danger: filter out routes with Elite between current and nearest Rest
            def _safe_to_rest(r: RoutePath) -> bool:
                for t in r.nodes:
                    if t == "Rest":
                        return True  # reached rest without hitting elite
                    if t == "Elite":
                        return False  # elite before rest
                return True  # no elite at all
            safe = [r for r in routes if _safe_to_rest(r)]
            if safe:
                routes = safe  # only show safe routes; keep all if none are safe

        if replan_reason and "Gold" in replan_reason:
            # Gold surplus: prioritize routes with shops (sort them first)
            with_shop = [r for r in routes if r.shop_count > 0]
            without_shop = [r for r in routes if r.shop_count == 0]
            routes = with_shop + without_shop

        # Format top 10 for LLM
        formatted = format_routes_for_prompt(routes, top_n=10)
        logger.info("Enumerated %d routes, formatted %d chars", len(routes), len(formatted))

        if not self._use_llm:
            self._route_plan = routes[0]
            self._planned_act = current_act
            logger.info("Route stored (no-LLM mode): %s", routes[0].nodes)
            return

        # Build full-context prompt for Scenario A
        # Strategic thread from short-term memory
        strategic_thread = ""
        stm = self._get_short_term_ref()
        if stm is not None and hasattr(stm, "get_strategic_thread"):
            strategic_thread = stm.get_strategic_thread(max_entries=5)

        prompt = build_route_selection_prompt(
            gs,
            routes_text=formatted,
            relics=self._cached_relics,
            strategic_thread=strategic_thread,
            replan_reason=replan_reason,
        )

        # Inject skills + memory context
        ctx = self._build_decision_context(gs, include_knowledge=False)
        extra_context = ctx.get("extra_context", "")
        skill_context = ctx.get("skill_context", "")
        memory_str = ""
        wc = ctx.get("working_context")
        if wc is not None:
            from src.memory.prompt_injector import format_working_context
            memory_str = format_working_context(wc)

        prompt_parts: list[str] = []
        if skill_context:
            prompt_parts.append(skill_context)
        if memory_str:
            prompt_parts.append(f"## Past Route Experience\n{memory_str}")
        if extra_context:
            prompt_parts.append(extra_context)
        prompt_parts.append(prompt)
        full_prompt = "\n\n".join(prompt_parts)

        try:
            from src.brain.llm_caller import call_raw as llm_call_raw
            raw_text, latency, tokens = await llm_call_raw(
                "You are a Slay the Spire 2 strategy expert. "
                "Pick the best route from the candidates.",
                full_prompt,
                think=True,
                model=config.LLM_STRATEGIC_MODEL,
                provider=config.get_tier_provider("strategic"),
            )
            logger.info("Route selection LLM: %.0fms, %d tokens", latency, tokens)

            # Parse JSON response
            import re as _re
            cleaned = _re.sub(r"<thinking>.*?</thinking>", "", raw_text, flags=_re.DOTALL).strip()

            try:
                _start = cleaned.find("{")
                _end = cleaned.rfind("}")
                if _start != -1 and _end > _start:
                    import json as _json
                    parsed = _json.loads(cleaned[_start:_end + 1])
                    route_num = parsed.get("route")
                    if route_num and 1 <= route_num <= min(10, len(routes)):
                        self._route_plan = routes[route_num - 1]
                        self._planned_act = current_act
                        logger.info("Route selected: #%d — %s", route_num, self._route_plan.nodes)
                        return
            except (ValueError, KeyError, TypeError):
                pass

            # Parse failed — use first sorted route
            logger.warning("Route selection parse failed — using sorted #1")
            self._route_plan = routes[0]
            self._planned_act = current_act

        except Exception as e:
            logger.warning("Route selection LLM failed: %s — using sorted #1", e)
            self._route_plan = routes[0]
            self._planned_act = current_act
```

- [ ] **Step 6: Update _build_remaining_route for new data structure**

Replace `_build_remaining_route` (lines 4738-4754):

```python
    def _build_remaining_route(self, gs: GameState) -> list[tuple[int, str]] | None:
        """Extract remaining route nodes from current position to boss."""
        if self._route_plan is None:
            return None
        route = self._route_plan
        step_idx = self._find_current_step_index(gs)
        if step_idx >= len(route.nodes):
            return None
        act = gs.act if hasattr(gs, "act") else 1
        act_start_floor = {1: 0, 2: 17, 3: 34}.get(act, 0)
        result: list[tuple[int, str]] = []
        for i in range(step_idx, len(route.nodes)):
            _, row = route.coords[i]
            floor_num = act_start_floor + row + 1
            result.append((floor_num, route.nodes[i]))
        return result if result else None
```

- [ ] **Step 7: Remove old imports and update existing ones**

At the top of `loop.py`, update imports:

```python
# Remove old import:
# from src.brain.prompts.map import build_map_prompt

# Add new imports:
from src.brain.prompts.map import build_route_selection_prompt, build_map_step_prompt
from src.brain.route_checker import ReplanReason, check_replan_needed
from src.brain.route_planner import RoutePath, enumerate_routes, sort_routes, format_routes_for_prompt
```

Remove `format_routes_for_llm_selection` from route_planner imports if present (it's now inlined into `build_route_selection_prompt`).

- [ ] **Step 8: Run existing tests**

Run: `python -m pytest tests/ -v --timeout=30 -x`
Expected: All PASS. Fix any import errors.

- [ ] **Step 9: Commit**

```bash
git add src/agent/loop.py src/brain/prompts/map.py src/brain/route_planner.py src/brain/route_checker.py
git commit -m "feat: wire annotation-based route planning with re-plan triggers into agent loop"
```

---

### Task 6: Clean up and remove dead code

**Files:**
- Modify: `src/brain/route_planner.py` (remove `format_routes_for_llm_selection` if unused)
- Modify: `tests/test_route_planner.py` (remove old test references)

- [ ] **Step 1: Remove format_routes_for_llm_selection**

The JSON response schema is now embedded in `build_route_selection_prompt()`. Delete `format_routes_for_llm_selection()` from `route_planner.py` and any test that references it.

- [ ] **Step 2: Remove `hp_ratio` parameter from enumerate_routes**

The scoring no longer uses HP ratio. Remove the `hp_ratio` parameter from `enumerate_routes()` signature and all call sites.

- [ ] **Step 3: Run full test suite**

Run: `python -m pytest tests/ -v --timeout=30`
Expected: All PASS.

- [ ] **Step 4: Commit**

```bash
git add src/brain/route_planner.py tests/test_route_planner.py src/agent/loop.py
git commit -m "chore: remove dead route scoring code and unused hp_ratio param"
```

---

### Task 7: Update CLAUDE.md documentation

**Files:**
- Modify: `CLAUDE.md`

- [ ] **Step 1: Update Route Planning section in CLAUDE.md**

Find the route planning references in CLAUDE.md and update them to reflect the new architecture. Key changes:

- Replace references to `score_route()` with `sort_routes()` (multi-key sort)
- Update the route planning description: "annotation-based candidates + condition-triggered re-plan"
- Add `route_checker.py` to the file listing under `src/brain/`
- Update `_maybe_plan_route` references to `_select_route`
- Update Important Patterns section: "Route planning: annotation-based multi-key sort + LLM route selection (strategic tier) + condition-triggered re-plan (HP<25+danger, gold>=350+no shop, path deviation)"
- Add to Bugs Fixed / changelog if appropriate

- [ ] **Step 2: Commit**

```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md for route plan refactor"
```
