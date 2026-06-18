# Combat Plan: Route Simple Hands to Fast Tier — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route combat-plan generation to the fast tier when `len(gs.playable_cards) <= 2`, so trivial hand decisions skip the slow strategic tier.

**Architecture:** Pure routing-layer change. Add a `simple` keyword arg to `V2Engine._get_v2_tier` and `V2Engine.generate_combat_plan`. Compute `simple` once inside `AgentLoop._generate_combat_plan` from the GameState. `simple` takes priority over `is_replan` (orthogonal axes — `simple` picks the tier, `is_replan` only modulates effort within strategic). The internal validation-retry call inside `_generate_combat_plan` deliberately does not pass `simple`, so a fast-tier failure escalates to strategic-low.

**Tech Stack:** Python 3.14, pytest. Touches `src/brain/v2_engine.py`, `src/agent/loop.py`, `tests/test_thinking_tiered.py`.

**Spec:** `docs/superpowers/specs/2026-04-29-combat-plan-simple-fast-tier-design.md`

---

## File Structure

| File | Change | Responsibility |
|------|--------|---------------|
| `src/brain/v2_engine.py` | Modify | `_get_v2_tier` gains `simple: bool = False`; `generate_combat_plan` gains `simple: bool = False` and passes through. |
| `src/agent/loop.py` | Modify | `_generate_combat_plan` computes `simple = len(gs.playable_cards) <= 2` once and passes to the first `v2_engine.generate_combat_plan` call. The validation-retry call (line ~7140) intentionally omits `simple` so failures escalate to strategic. |
| `tests/test_thinking_tiered.py` | Modify | Add four unit tests covering the new routing matrix. |

No new files. No prompt changes. No conversation-history changes.

---

## Task 1: Add `simple` parameter to `_get_v2_tier` (TDD)

**Files:**
- Modify: `src/brain/v2_engine.py:423-456`
- Test: `tests/test_thinking_tiered.py` (append to `TestV2EngineTierRouting` class)

- [ ] **Step 1: Write four failing tests**

Append these test methods to `class TestV2EngineTierRouting` in `tests/test_thinking_tiered.py`:

```python
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
```

- [ ] **Step 2: Run tests, verify they fail**

Run: `python -m pytest tests/test_thinking_tiered.py::TestV2EngineTierRouting -v`

Expected: 4 new tests fail with `TypeError: _get_v2_tier() got an unexpected keyword argument 'simple'`. The 7 existing tests still pass.

- [ ] **Step 3: Implement the `simple` branch**

In `src/brain/v2_engine.py`, replace the entire `_get_v2_tier` method (lines 422-456) with:

```python
    @staticmethod
    def _get_v2_tier(
        state_type: str,
        *,
        is_replan: bool = False,
        simple: bool = False,
    ) -> tuple[str, str, str]:
        """Select provider, model, and effort level for a V2 decision.

        Args:
            state_type: The game state type (e.g. ``"map"``, ``"shop"``,
                ``"combat_plan"``).
            is_replan: If ``True``, use strategic model with low effort
                (draw-card re-plan, validation retry).
            simple: If ``True``, route to the fast tier regardless of the
                state_type's normal routing. Used for trivial combat plans
                (≤2 playable cards) where strategic-tier reasoning is
                wasted. Takes priority over ``is_replan`` — a draw-card
                re-plan that ends up with a trivial hand should still go
                fast.

        Returns:
            ``(provider, model_name, effort)`` tuple.  ``effort`` is ``""`` for
            fast tier (no thinking) or ``"medium"``/``"low"`` for
            strategic tier.
        """
        if simple:
            return (
                config.get_tier_provider("fast"),
                config.LLM_FAST_MODEL,
                config.LLM_THINK_EFFORT_FAST or "low",
            )

        if is_replan:
            return (
                config.get_tier_provider("strategic"),
                config.LLM_STRATEGIC_MODEL,
                "low",
            )

        tier = _V2_TIER_MAP.get(state_type, "strategic")
        provider = config.get_tier_provider(tier)
        model = getattr(config, f"LLM_{tier.upper()}_MODEL")
        # Both tiers now read effort from config.  Fast tier defaults to
        # "low" instead of "" because Gemini 3.1 flash-lite-preview is
        # *faster* with explicit thinking_level=low than without it (the
        # server runs thinking either way; explicit "low" caps the budget).
        effort = getattr(config, f"LLM_THINK_EFFORT_{tier.upper()}", "low" if tier == "fast" else "medium")
        return (provider, model, effort)
```

Note the structural change: `simple` is checked FIRST, before `is_replan`. This implements the "simple wins" semantics from the spec.

- [ ] **Step 4: Run new tests, verify they pass**

Run: `python -m pytest tests/test_thinking_tiered.py::TestV2EngineTierRouting -v`

Expected: all 11 tests pass (7 existing + 4 new).

- [ ] **Step 5: Run the full v2_engine test suite to catch regressions**

Run: `python -m pytest tests/test_v2_engine_core.py tests/test_thinking_tiered.py -v`

Expected: all pass. No `_get_v2_tier`-shaped failures.

- [ ] **Step 6: Commit**

```bash
git add src/brain/v2_engine.py tests/test_thinking_tiered.py
git commit -m "feat(v2_engine): add simple flag to _get_v2_tier for fast-tier routing

simple=True routes to fast tier regardless of state_type. Takes
priority over is_replan so that a trivial hand triggers fast tier
even on draw-card re-plans. simple=False preserves all existing
behavior. Wired up to combat_plan in next commit."
```

---

## Task 2: Thread `simple` through `generate_combat_plan`

**Files:**
- Modify: `src/brain/v2_engine.py:557-589`

This task adds a backward-compatible `simple` kwarg to `generate_combat_plan` and forwards it to `_get_v2_tier`. No caller uses it yet — the caller wiring is Task 3. After this task, the signature is in place and the code is dead-but-not-broken (callers default to `simple=False`).

- [ ] **Step 1: Write the failing test**

Append to `class TestV2EngineTierRouting` in `tests/test_thinking_tiered.py`:

```python
    def test_generate_combat_plan_signature_accepts_simple(self):
        """generate_combat_plan accepts simple kwarg (Task 2 wiring)."""
        import inspect
        from src.brain.v2_engine import V2Engine
        sig = inspect.signature(V2Engine.generate_combat_plan)
        assert "simple" in sig.parameters
        assert sig.parameters["simple"].default is False
```

- [ ] **Step 2: Run test, verify it fails**

Run: `python -m pytest tests/test_thinking_tiered.py::TestV2EngineTierRouting::test_generate_combat_plan_signature_accepts_simple -v`

Expected: FAIL with `assert "simple" in sig.parameters` (signature does not yet have the param).

- [ ] **Step 3: Modify `generate_combat_plan` signature and tier call**

In `src/brain/v2_engine.py`, modify the `generate_combat_plan` method. Find this block (around lines 557-588):

```python
    async def generate_combat_plan(
        self,
        conversation: CombatConversation,
        *,
        is_replan: bool = False,
        use_fallback_model: bool = False,
    ) -> CombatPlan | None:
        """Generate a combat plan from a multi-turn conversation.

        Args:
            conversation: ``CombatConversation`` with accumulated messages.
            is_replan: If ``True``, use fast tier (draw-card re-plan,
                validation retry). Defaults to ``False`` (strategic tier).
            use_fallback_model: If ``True``, use analysis tier as a stronger
                fallback when the default tier fails repeatedly.
```

Replace with (note the new `simple` kwarg + its docstring):

```python
    async def generate_combat_plan(
        self,
        conversation: CombatConversation,
        *,
        is_replan: bool = False,
        simple: bool = False,
        use_fallback_model: bool = False,
    ) -> CombatPlan | None:
        """Generate a combat plan from a multi-turn conversation.

        Args:
            conversation: ``CombatConversation`` with accumulated messages.
            is_replan: If ``True``, use strategic model with low effort
                (draw-card re-plan, validation retry). Defaults to
                ``False`` (strategic tier with configured effort).
            simple: If ``True``, route to the fast tier — trivial hands
                (≤2 playable cards) where strategic-tier reasoning is
                wasted. Takes priority over ``is_replan``.
            use_fallback_model: If ``True``, use analysis tier as a stronger
                fallback when the default tier fails repeatedly.
```

Then find the `_get_v2_tier` call in the same method (around line 588):

```python
            provider, model, effort = self._get_v2_tier("combat_plan", is_replan=is_replan)
```

Replace with:

```python
            provider, model, effort = self._get_v2_tier(
                "combat_plan", is_replan=is_replan, simple=simple,
            )
```

- [ ] **Step 4: Run the new test, verify it passes**

Run: `python -m pytest tests/test_thinking_tiered.py::TestV2EngineTierRouting::test_generate_combat_plan_signature_accepts_simple -v`

Expected: PASS.

- [ ] **Step 5: Run the full test suite for v2_engine**

Run: `python -m pytest tests/test_v2_engine_core.py tests/test_thinking_tiered.py tests/test_combat_conversation.py tests/test_combat_conversation_gate.py -v`

Expected: all pass. No regression — the new kwarg defaults to `False`, preserving all existing call paths.

- [ ] **Step 6: Commit**

```bash
git add src/brain/v2_engine.py tests/test_thinking_tiered.py
git commit -m "feat(v2_engine): forward simple flag through generate_combat_plan

Signature gains simple: bool = False keyword arg, passed through to
_get_v2_tier. Callers still default to simple=False until the loop.py
wiring lands in the next commit."
```

---

## Task 3: Compute `simple` in `_generate_combat_plan` and pass through

**Files:**
- Modify: `src/agent/loop.py:7005-7110` (specifically the `v2_engine.generate_combat_plan` call at lines 7106-7110)

The validation-retry call at line ~7140 deliberately stays unchanged — when the fast-tier (or any) plan fails validation, escalating to `is_replan=True` (which routes to strategic-low) is the right fallback.

- [ ] **Step 1: Locate the first generate_combat_plan call**

Open `src/agent/loop.py` and find this block (around lines 7104-7110):

```python
                # Generate plan via conversation (model-routed)
                plan = await self._v2_engine.generate_combat_plan(
                    _conversation,
                    is_replan=is_replan,
                    use_fallback_model=use_fallback_model,
                )
```

This is the FIRST call inside `_generate_combat_plan`. The SECOND call lower down (line ~7140, inside `if validation_error:`) is the validation retry — leave that one alone.

- [ ] **Step 2: Replace the first call to compute and pass `simple`**

Replace the block above with:

```python
                # Trivial-hand fast-path: when the player has ≤2 playable
                # cards, strategic-tier reasoning is wasted. Route to fast.
                # Takes priority over is_replan — a draw-card replan that
                # lands on a trivial hand should still go fast.
                simple = len(gs.playable_cards) <= 2
                # Generate plan via conversation (model-routed)
                plan = await self._v2_engine.generate_combat_plan(
                    _conversation,
                    is_replan=is_replan,
                    simple=simple,
                    use_fallback_model=use_fallback_model,
                )
```

- [ ] **Step 3: Verify the validation-retry call (around line 7140) is unchanged**

Confirm via `Grep` or visual scan that the second call inside `if validation_error:` still reads:

```python
                            plan = await self._v2_engine.generate_combat_plan(
                                _conversation,
                                is_replan=True,
                                use_fallback_model=use_fallback_model,
                            )
```

It should NOT pass `simple=`. This is intentional — fast tier failed, so escalate to strategic.

- [ ] **Step 4: Run loop / combat tests**

Run: `python -m pytest tests/test_loop_combat.py tests/test_combat_conversation.py tests/test_combat_conversation_gate.py -v`

Expected: all pass. The `simple` value is derived from `gs.playable_cards`, so existing tests that build a GameState with ≥3 playable cards will see `simple=False` (no behavior change). Tests that build a GameState with ≤2 playable cards will now route to fast — if any existing test mocks the strategic tier and asserts on the call, it may need updating. If a regression appears here, the fix is to update the test mock to expect the fast-tier call OR to construct a hand with ≥3 playable cards.

- [ ] **Step 5: Run the full unit test suite**

Run: `python -m pytest tests/ -x --ignore=tests/regression -q`

Expected: all unit tests pass. (`tests/regression` excluded — those are golden-log fingerprints unrelated to this change.)

- [ ] **Step 6: Commit**

```bash
git add src/agent/loop.py
git commit -m "feat(loop): route trivial-hand combat plans (≤2 playable) to fast tier

Computes simple = len(gs.playable_cards) <= 2 inside
_generate_combat_plan and forwards it to v2_engine. Skips the
strategic-tier roundtrip on residual cleanup, low-energy end-turn,
and 1-2 card trailing hands. Validation-retry path intentionally
omits simple so fast-tier failures escalate to strategic-low."
```

---

## Task 4: Live smoke verification

**Files:** none (verification only)

Run the agent for a short session and confirm in the logs that low-playable rounds use the fast tier without any validation retries or other regressions.

- [ ] **Step 1: Start a short live run**

```bash
python -m scripts.run_agent --steps 80 --runs 1 --character Silent --no-postrun
```

Expected: run starts, reaches at least floor 1 combat, plays normally to ~80 steps or completion.

- [ ] **Step 2: Inspect the JSONL log for fast-tier combat plans**

Find the log file for the run just completed (most recent `logs/run_*.jsonl`). Use Python to count combat-plan tier dispatches:

```bash
python -c "
import json, glob, os
log = max(glob.glob('logs/run_*.jsonl'), key=os.path.getmtime)
print(f'Inspecting: {log}')
fast = strat = 0
fast_with_few_playable = strat_with_many = 0
with open(log, encoding='utf-8') as f:
    for line in f:
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        if r.get('event') != 'llm_call': continue
        if r.get('state_type_hint') != 'combat_plan': continue
        tier = r.get('tier')
        if tier == 'fast': fast += 1
        elif tier == 'strategic': strat += 1
print(f'combat_plan llm_calls: fast={fast}, strategic={strat}')
print(f'fast/(fast+strat) = {fast/(fast+strat):.1%}' if (fast+strat) else 'no calls')
"
```

Expected:
- `fast` count > 0 (at least one trivial round happened)
- `strategic` count > 0 (at least one non-trivial round happened)
- Roughly fast in 20-50% range (varies by RNG; the headline is "fast tier was hit at all").

- [ ] **Step 3: Confirm no spike in validation retries**

Same log file:

```bash
python -c "
import json, glob, os
log = max(glob.glob('logs/run_*.jsonl'), key=os.path.getmtime)
retries = 0
with open(log, encoding='utf-8') as f:
    for line in f:
        try: r = json.loads(line)
        except json.JSONDecodeError: continue
        if 'Combat re-plan truncated' in str(r) or 'validation failed at step 1' in str(r):
            retries += 1
print(f'validation retries / failures: {retries}')
"
```

Expected: `retries` is 0 or very low (≤1-2 over 80 steps). If you see >5, the fast tier may be stumbling on simple plans more than expected — open the log, find a fast-tier combat plan that triggered a retry, and check whether the failure was a hallucinated card name (a real fast-tier weakness) or something else.

- [ ] **Step 4: No commit needed for verification**

If steps 1-3 look good, the change is shipped. If something is off, file a follow-up; do not amend the previous commits.

---

## Self-Review

**Spec coverage check:**
- ✅ Routing rule (`simple` first, then `is_replan`, then default) → Task 1 implementation
- ✅ Trigger condition (`len(gs.playable_cards) <= 2`) → Task 3 caller computation
- ✅ `simple` overrides `is_replan` → Task 1 test `test_simple_overrides_is_replan`
- ✅ Validation-retry intentionally skipped → Task 3 step 3 explicitly verifies
- ✅ Tests covering routing matrix → Task 1 four tests
- ✅ Smoke test → Task 4
- ✅ No prompt / conversation / cache changes → no Task touches those files

**Type / signature consistency:**
- `simple: bool = False` keyword-only arg used uniformly across `_get_v2_tier`, `generate_combat_plan`. Default `False` means all existing callers are unaffected.
- `_generate_combat_plan` in loop.py does NOT add a `simple` param (the spec called for one, but during plan-writing we recognized the value is purely a function of `gs`, so computing it inside is cleaner). This is a deliberate refinement of the spec; if a future caller of `_generate_combat_plan` needs to override the tier, they can add a param then.

**Placeholder scan:** No "TBD", "TODO", "fill in", or vague "handle errors" steps. Every code block contains the literal code to write or replace.

**Out-of-scope confirmation:** Boss / low-HP / special-card exemptions, energy-aware refinement, and re-plan effort decoupling are out of scope per the spec — none appear in this plan.
