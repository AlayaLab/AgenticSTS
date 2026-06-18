# Combat Plan: Route Simple Hands to Fast Tier

**Status:** Design
**Date:** 2026-04-29
**Owner:** AgenticSTS Contributors
**Related code:** `src/brain/v2_engine.py`, `src/agent/loop.py`

## Problem

Every combat-plan generation currently routes to the strategic tier
(Gemini 3.1 Pro, medium effort, streaming). On turns where the player
has very few playable cards (residual cleanup, low-energy end-turn,
trailing 1-2 card hands), the strategic tier is overkill: there is
essentially no decision space, the play order is forced or
near-forced, and the strategic tier costs ~10-15s per call versus
~2-3s for the fast tier (Gemini Flash-Lite).

Across a 200-step run, 30-50% of combat rounds plausibly have ≤2
playable cards, which adds up to 5-10 minutes of wasted strategic-tier
latency per run with no quality upside.

## Goal

Route combat-plan generation to the **fast tier** when the current
hand has **≤2 playable cards**, while preserving strategic-tier
behavior on every other combat plan.

The change must be a pure routing-layer change: no prompt edits, no
conversation-history edits, no tool-schema edits, no impact on prompt
caching.

## Non-Goals

- Boss/elite/low-HP exemptions. Empirically, ≤2-playable boss rounds
  are rare, and adding exemptions defeats the "clean" goal. If a
  pathological boss round ever surfaces in logs, we revisit.
- Special-card exemptions (Catalyst, Apotheosis, Echo Form, etc.).
  Same reasoning — adds branching for vanishingly rare cases.
- Re-plan effort tuning. Re-plan currently hard-codes
  `effort = "low"` regardless of `STS2_THINK_EFFORT_STRATEGIC`. This
  spec preserves that semantics. Decoupling re-plan effort from the
  hardcode is a separate concern and out of scope.
- Hand-size-based routing for non-combat decisions (shop, event,
  rest, etc.). Different decision types, different signals.

## Design

### Key insight: `simple` and `is_replan` are orthogonal axes

- `simple` chooses the **tier** (fast vs strategic).
- `is_replan` chooses the **effort within strategic tier** (low when
  replanning, otherwise the configured strategic effort).

This means `simple` takes priority over `is_replan`: a draw-card
re-plan that ends with ≤2 playable cards is just as trivial as a
fresh plan with ≤2 playable cards. Both go fast.

### Routing rule

```
if simple:
    tier = "fast", effort = config.LLM_THINK_EFFORT_FAST
elif is_replan:
    tier = "strategic", effort = "low"  # preserves current behavior
else:
    tier = state_type's mapped tier (strategic for combat_plan)
    effort = config.LLM_THINK_EFFORT_<TIER>
```

### Trigger condition

```python
simple = len(gs.playable_cards) <= 2
```

`gs.playable_cards` is an existing property on `GameState`
(`src/state/game_state.py:344`). It returns hand cards filtered by
`c.playable`, which already accounts for energy cost, exhaust locks,
and other unplayable conditions.

This rule covers more cases than `len(hand) <= 2`:

| Scenario               | hand | playable | Current   | After      |
|------------------------|------|----------|-----------|------------|
| High-energy big hand   | 5    | 5        | strategic | strategic  |
| Residual cleanup       | 5    | 1        | strategic | **fast**   |
| Out-of-energy end turn | 4    | 0        | strategic | **fast**   |
| Trailing 1-2 cards     | 2    | 2        | strategic | **fast**   |
| Boss turn 1            | 5    | 3        | strategic | strategic  |

## Implementation

### Files touched

1. **`src/brain/v2_engine.py`** — `_get_v2_tier` gains a `simple`
   keyword arg with the routing rule above; `generate_combat_plan`
   gains a `simple` keyword arg and passes it through.

2. **`src/agent/loop.py`** — `_generate_combat_plan` gains a `simple`
   keyword arg and passes it to `v2_engine.generate_combat_plan`. Both
   call sites (line ~6453 for replan, line ~6491 for fresh plan)
   compute `simple = len(gs.playable_cards) <= 2` and pass it.

### Code sketch

`v2_engine.py::_get_v2_tier`:

```python
@staticmethod
def _get_v2_tier(
    state_type: str,
    *,
    is_replan: bool = False,
    simple: bool = False,
) -> tuple[str, str, str]:
    if simple:
        return (
            config.get_tier_provider("fast"),
            config.LLM_FAST_MODEL,
            config.LLM_THINK_EFFORT_FAST or "low",
        )

    tier = _V2_TIER_MAP.get(state_type, "strategic")
    provider = config.get_tier_provider(tier)
    model = getattr(config, f"LLM_{tier.upper()}_MODEL")

    if is_replan and tier == "strategic":
        effort = "low"
    else:
        effort = getattr(
            config, f"LLM_THINK_EFFORT_{tier.upper()}",
            "low" if tier == "fast" else "medium",
        )
    return (provider, model, effort)
```

`v2_engine.py::generate_combat_plan` signature:

```python
async def generate_combat_plan(
    self,
    conversation: CombatConversation,
    *,
    is_replan: bool = False,
    simple: bool = False,
    use_fallback_model: bool = False,
) -> CombatPlan | None:
    ...
    provider, model, effort = self._get_v2_tier(
        "combat_plan", is_replan=is_replan, simple=simple,
    )
    ...
```

`loop.py::_generate_combat_plan` propagation:

```python
async def _generate_combat_plan(
    self, gs: GameState, *, is_replan: bool = False, simple: bool = False,
):
    ...
    plan = await self._v2_engine.generate_combat_plan(
        self._v2_combat_conversation,
        is_replan=is_replan,
        simple=simple,
    )
```

Caller sites in `loop.py` compute `simple` once from `gs`:

```python
simple = len(gs.playable_cards) <= 2
plan = await self._generate_combat_plan(gs, is_replan=is_replan, simple=simple)
```

### Conversation-history compatibility

`CombatConversation` accumulates round-state messages and plan
responses across rounds within a single combat. A simple-tier plan
returned by Flash-Lite is structurally identical to a strategic-tier
plan (same `combat_plan` tool schema, same JSON shape), so a later
strategic-tier round reading prior fast-tier plans in the conversation
sees the same shape it would see otherwise. No special handling
needed.

### Prompt caching

System prompts (COMBAT, COMBAT_BOSS) are unchanged. They sit in the
cached system block regardless of which tier the model call targets.
Switching tier means switching the API endpoint / model name in the
request body — the cached prefix is unaffected.

(Caveat worth noting: the prompt cache is per-model. Strategic and
fast tiers maintain independent caches. This is the same situation as
existing fast-tier callers like `hand_select` and `treasure`, so no
new caching concern.)

## Risks and Mitigations

**R1: Quality regression on simple turns.** Flash-Lite is weaker
than Pro. Mitigation: rule limited to ≤2 playable cards, where the
decision space is essentially trivial; if Flash-Lite produces an
invalid plan, the existing validation-retry path
(`is_replan=True`) catches it and re-plans with strategic-low effort.

**R2: Draw-card cards mid-plan.** A play that triggers a draw can
expand the hand from 2 to 5+. Mitigation: the existing
`_force_replan_on_draw` path (referenced in `loop.py:6487`) re-enters
plan generation with the new hand, at which point the new
`len(playable) <= 2` evaluation correctly determines the tier for the
expanded state.

**R3: Edge case — combat plan called with 0 playable cards.** This
should always result in "end turn", which Flash-Lite handles
trivially. No risk.

**R4: Effort env var interaction.** The change does not touch how
effort env vars resolve. Users with
`STS2_THINK_EFFORT_FAST=high` will see fast-tier combat plans run at
high effort; users with `STS2_THINK_EFFORT_FAST=low` (the typical
case) will see them at low effort. Both are intentional.

## Testing

- **Unit:** `_get_v2_tier` decision matrix — six cases:
  `(state_type=combat_plan, is_replan, simple)` ∈ {F,T} × {F,T} plus a
  non-combat state for regression. Assert returned `(provider, model,
  effort)` matches the routing rule.
- **Integration:** existing `test_v2_engine_combat_plan*` tests pass
  unchanged when `simple=False`. Add one case forcing `simple=True`
  and assert the call site receives the fast-tier provider/model.
- **Smoke:** `python -m scripts.run_agent --steps 80 --runs 1` —
  inspect `logs/run_*.jsonl` for `tier="fast"` rows on combat-plan
  decisions where the round had ≤2 playable cards. Confirm no parse
  errors and no validation-retry loops on those rows.

## Out-of-Scope Follow-ups

- Decoupling re-plan effort from the `effort = "low"` hardcode (let
  re-plan inherit `STS2_THINK_EFFORT_STRATEGIC`).
- Energy-aware refinement: `len(playable) + energy_for_remaining` as a
  more precise complexity signal. Not worth the branching for now.
- Apply the same pattern to non-combat tiers if observation-mode logs
  show similar trivial-decision fast-paths there.
