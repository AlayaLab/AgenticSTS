# Route Plan Refactor: Condition-Triggered GPS Navigation

**Date:** 2026-04-03
**Status:** Draft
**Scope:** `src/brain/route_planner.py`, `src/brain/prompts/map.py`, `src/agent/loop.py`

## Problem

Current route planning is rigid: a heuristic scoring function picks a fixed path at act start, and the LLM has limited autonomy to deviate. Key issues:

1. **No re-planning** — route is fixed for the entire act regardless of HP drops, gold spikes, or deck changes
2. **Heuristic scoring is opaque** — numeric weights (Rest=+3, Elite=-3, Shop=+1) hide trade-offs from the LLM
3. **No state-awareness in scoring** — gold doesn't affect Shop value, deck strength doesn't affect Elite risk
4. **LLM lacks context to deviate well** — map prompt says "you may deviate" but doesn't give enough information to make informed deviations

## Design: GPS Navigation Model

Like GPS navigation: generate a recommended route at act start, follow it step-by-step, but re-route when conditions change significantly.

### Core Principles

- **Annotate, don't score** — present route characteristics (Elite count, Rest count, Shop position) and let the LLM reason about trade-offs
- **Plan once, re-plan on trigger** — avoid unnecessary LLM calls, but don't lock into a bad plan
- **Two prompt scenarios** — full context for route selection (Scenario A), lightweight for step-by-step walking (Scenario B)

## Part 1: Route Generation

### Annotation-Based Candidates (replaces score_route)

`enumerate_routes()` keeps the existing DFS enumeration on the map DAG (no cycles, proven reliable). The scoring layer is replaced with **feature annotation + multi-dimensional sorting**.

Each candidate route includes:

```
Route N: Event(c2,r5) -> Monster(c1,r6) -> Rest(c2,r7) -> Shop(c2,r8) -> Boss(c2,r10)
  [0 Elite | 2 Rest | 1 Shop(step 4/6, near Boss) | 2 Monster | 1 Event | 0 Treasure]
  [pre-boss node: Rest]
```

### Sorting Priority (not scoring)

Routes are sorted by these criteria in order of priority. This is a multi-key sort, not a weighted sum:

1. **Elite count ascending** — fewer elites is always better
2. **Rest count descending** — more rest sites is always better
3. **Has exactly 1 Shop preferred** — routes with 1 shop sort before 0-shop or 2+-shop routes
4. **Shop position closer to Boss preferred** — later shops allow more gold accumulation
5. **Treasure count descending** — more treasure is better
6. **Event count descending** — prefer events over monsters (lowest priority)

**Output**: Top 8-10 candidate routes presented to LLM with full annotations.

### Why Not Scoring

Scoring collapses multi-dimensional trade-offs into a single number. A route with "0 Elite, 0 Rest, 2 Shop" scores differently from "1 Elite, 3 Rest, 0 Shop" but the right choice depends on current HP, deck, and gold — context the scoring function doesn't have. Annotation lets the LLM weigh these factors with full game state.

## Part 2: Condition-Triggered Re-plan

### When to Re-plan

At each map node with multiple options, a lightweight Python check runs before the LLM decision. No LLM call — just condition evaluation against the remaining planned route.

**Trigger conditions (any one triggers re-plan):**

| # | Condition | Rationale |
|---|-----------|-----------|
| 1 | `hp < 25` AND (remaining route has Elite OR 2+ Monsters before next Rest) | Low HP with danger ahead — need a safer path |
| 2 | `gold >= 350` AND remaining route has no Shop | Lots of gold with no way to spend it — need a shop |
| 3 | Current position not on planned route coordinates | LLM deviated last step — old plan is invalid |

### Re-plan with Extra Constraints

When re-plan is triggered by HP (condition 1), the route generation applies additional filtering:
- **Filter out** routes where the path between current node and nearest Rest contains any Elite
- This ensures the LLM only sees "safe to Rest" options when HP is critical

When re-plan is triggered by Gold (condition 2):
- **Prioritize** routes that include at least one Shop (sort these first)

### When NOT to Re-plan

- Only 1-2 nodes remaining before Boss — not worth re-planning, just use Scenario B
- Single option available — auto-select mechanically (existing behavior, unchanged)

### No Frequency Limit

The trigger conditions are specific enough to self-limit. A player at 25 HP with elites ahead *should* re-plan every step until the situation resolves.

## Part 3: Map Prompt Restructuring

### Scenario A: Route Selection (Act Start or Re-plan)

Used when LLM needs to choose a route from candidates. Injects full game state for informed decision-making.

```
## Route Selection
HP: 45/80 | Gold: 230 | Act 2 | Floor 20
Character: Silent | Deck: 28 cards
Potions: [Weak Potion, Fire Potion]
Relics: [Vajra, Bag of Marbles, ...]
Strategic Thread: "Need more defense, prioritize Strike removal"

Candidate routes from current position to Boss:
1. Event(c2,r5) -> Monster(c1,r6) -> Rest(c2,r7) -> Shop(c2,r8) -> Monster(c1,r9) -> Rest(c2,r10) -> Boss
   [0 Elite | 2 Rest | 1 Shop(step 4) | 2 Monster | 1 Event | pre-boss: Rest]
2. Monster(c3,r5) -> Rest(c3,r6) -> Elite(c2,r7) -> Treasure(c2,r8) -> Event(c1,r9) -> Rest(c2,r10) -> Boss
   [1 Elite(step 3) | 2 Rest | 0 Shop | 1 Monster | 1 Event | 1 Treasure | pre-boss: Rest]
... (8-10 routes)

Choose the route that best fits your current state. Respond with:
{"route": <number>, "reasoning": "..."}
```

**LLM tier**: Strategic (Sonnet + thinking) via `call_raw` — route selection affects the entire act. This is a standalone call (not V2Engine tool-use) because the response is a simple JSON route choice, not a gameplay action.

### Scenario B: Step-by-Step Walking (Has Plan, No Re-plan Triggered)

Used for normal per-node decisions when a plan exists and conditions are stable.

```
## Map Navigation
HP: 45/80 | Gold: 230 | Act 2 | Floor 20

Current route: Event -> Monster -> [HERE] -> Shop -> Monster -> Rest -> Boss
Next recommended: Shop(c2,r8) — step 4 of route

Available nodes:
- [index=0] Shop at c2,r8  <- route recommends
- [index=1] Monster at c3,r8
- [index=2] Event at c1,r8

You may deviate from the route. Explain why if you do.
```

**Key difference from current**: Scenario B is more compact. No full path tree, no HP assessment boilerplate — just the plan context and options. Full state context (deck/potions/relics) is available through the existing V2Engine conversation context.

## Part 4: Architecture Changes

### Files Modified

| File | Change | Details |
|------|--------|---------|
| `src/brain/route_planner.py` | **Rewrite** | Remove `score_route()`. Add `annotate_route()` for feature extraction, `sort_routes()` for multi-key sort, rewrite `format_routes_for_prompt()` for annotation format. Keep DFS `enumerate_routes()` core. |
| `src/brain/prompts/map.py` | **Rewrite** | Split `build_map_prompt()` into `build_route_selection_prompt()` (Scenario A) and `build_map_step_prompt()` (Scenario B). Scenario A includes full state injection. |
| `src/agent/loop.py` | **Modify** | Rewrite `_maybe_plan_route()` to support re-planning. Add `_should_replan_route(gs)` condition checker. Update map decision flow in `_decide_and_act()`. |

### Unchanged

- DFS enumeration algorithm (DAG, no cycles, reliable)
- Single-option auto-select mechanism
- `_cached_map_node_type` (combat type caching)
- V2Engine map decision path (Scenario B uses existing flow)
- `_build_remaining_route()` (adapted to new data structure)

### State Storage Changes

Current:
```python
self._route_plan: str = ""           # plain text
self._route_coords: tuple = ()       # (col, row) sequence
self._route_node_types: tuple = ()   # node type sequence
self._planned_act: int = -1          # which act
```

New:
```python
self._route_plan: RoutePath | None = None   # structured route (coords + types + features)
self._planned_act: int = -1                  # which act (kept for act-change detection)
```

The `RoutePath` dataclass already has `coords` and `nodes` tuples. Extend it to drop the `score` field and add feature annotations (shop_positions, pre_boss_node, etc.).

### Decision Flow

```
map node decision:
  if single option -> mechanical auto-select (unchanged)
  if no plan (act start / plan is None):
    -> Scenario A: generate candidates -> LLM selects route (strategic tier)
  if has plan:
    if remaining route <= 2 nodes:
      -> Scenario B (no re-plan, not worth it)
    if _should_replan_route(gs) triggers:
      -> Scenario A: re-generate candidates (with extra constraints) -> LLM selects
    else:
      -> Scenario B: show plan + recommend next -> LLM step decision (existing V2Engine)
```

## Part 5: Edge Cases

| Situation | Handling |
|-----------|----------|
| DFS enumerates 0 paths | Degrade to Scenario B with no plan — LLM sees raw options only |
| LLM route selection fails (parse error / timeout) | Use sorted candidate #1 as plan (sorting reflects player preference) |
| Re-plan selects same route as before | Normal — old route is still best for current state |
| Path deviation then re-plan with very short remaining path (1-2 nodes) | Skip re-plan, use Scenario B directly |
| `_build_remaining_route()` can't locate current position in plan | Treat as "path deviated" — trigger re-plan |
| Re-plan triggered every step (e.g. stuck at low HP) | No frequency limit — conditions are specific enough to self-regulate |

## Observability

Re-plan events emitted to EventBus as `ROUTE_REPLAN` with trigger reason (`hp_danger`, `gold_no_shop`, `path_deviation`), visible in monitor dashboard.

## Token Budget Estimate

| Component | Tokens (approx) |
|-----------|-----------------|
| Scenario A: 10 annotated routes | ~800-1000 |
| Scenario A: full state context | ~300-500 |
| Scenario A: total per call | ~1100-1500 |
| Scenario B: plan summary + options | ~200-400 |
| Re-plan overhead per act (0-2 re-plans typical) | ~0-3000 additional |

Compared to current: Act-level planning uses ~800 tokens (formatted routes + LLM selection). The new Scenario A is slightly larger but provides much more information to the LLM. Scenario B is smaller than the current map prompt.

## Out of Scope

- Dynamic tool integration (ToolPreprocessor hints for map decisions)
- Route memory/learning (HCM route store updates — existing pipeline unchanged)
- Map visualization in monitor dashboard
- Multi-act planning (cross-act route strategy)
