"""Regression: when the only claimable reward is a potion and slots are full,
the mechanical reward handler must return None (fall through to LLM) — not
claim it, not silently skip-and-return a sentinel. This invariant is what
Spec 2 (flexible potion usage) prompt-side changes rely on: the LLM needs to
see the reward state so the ``## Potion Slot Decision`` subsection can drive
a ``discard_potion(J)`` action.

Method under test: ``AgentLoop._handle_rewards`` in ``src/agent/loop.py``.
The spec refers to this conceptually as ``_try_mechanical_rewards``; same
function, renamed in the code.
"""
from __future__ import annotations

from types import SimpleNamespace


def _reward_item(index, reward_type, description="", claimable=True):
    return SimpleNamespace(
        index=index,
        reward_type=reward_type,
        description=description,
        claimable=claimable,
    )


def _minimal_loop():
    """Build a bare ``AgentLoop`` with just the attributes ``_handle_rewards`` touches.

    Kept intentionally tight: if a future refactor makes the handler depend
    on more state, the test should fail loudly rather than accidentally keep
    passing against a stubbed attribute.
    """
    from src.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)
    # Card-reward bookkeeping touched on entry (lines ~7436-7451)
    loop._card_reward_count_before_open = None
    loop._last_opened_card_index = None
    loop._opened_card_rewards = set()
    return loop


def _gs_with_only_potion_reward(open_potion_slots=0):
    reward = SimpleNamespace(
        rewards=[_reward_item(0, "potion", description="Ghost Potion")],
        pending_card_choice=False,
        can_proceed=False,
    )
    run = SimpleNamespace(floor=4)
    return SimpleNamespace(
        reward=reward,
        run=run,
        state_type="card_reward",
        open_potion_slots=open_potion_slots,
        potion_slots=3,
        # collect_rewards_and_proceed not in available_actions → the quick-exit
        # shortcut at line ~7461 is skipped, forcing the iteration path.
        available_actions=[],
    )


async def test_mechanical_reward_falls_through_when_only_potion_and_full():
    """If slots are full and potion is the only claimable item, the mechanical
    path must return None (not auto-claim, not auto-skip-and-return-a-sentinel).

    Why this matters: Spec 2's ``## Potion Slot Decision`` prompt section only
    gets rendered when the reward state reaches the LLM. A silent mechanical
    skip would suppress the subsection and the discard-to-claim flow would
    never fire.
    """
    loop = _minimal_loop()
    # Executing anything here is a failure — the method should not reach _execute.
    async def fake_execute(*args, **kwargs):
        raise AssertionError("must not execute any action")

    loop._execute = fake_execute

    gs = _gs_with_only_potion_reward(open_potion_slots=0)
    result = await loop._handle_rewards(gs)
    assert result is None


async def test_mechanical_reward_still_claims_gold_when_mixed():
    """Sanity check: when reward has [gold, potion] with full slots, gold is
    still claimed mechanically. Covers the first tick of the spec's reward
    flow — we only want fall-through when the *only* claimable is a potion."""
    executed: list = []

    async def fake_execute(action, *args, **kwargs):
        executed.append(action)

    loop = _minimal_loop()
    loop._execute = fake_execute

    reward = SimpleNamespace(
        rewards=[
            _reward_item(0, "gold", description="+50 gold"),
            _reward_item(1, "potion", description="Ghost Potion"),
        ],
        pending_card_choice=False,
        can_proceed=False,
    )
    gs = SimpleNamespace(
        reward=reward,
        run=SimpleNamespace(floor=4),
        state_type="card_reward",
        open_potion_slots=0,
        potion_slots=3,
        available_actions=[],
        gold=0,  # required for gold-delta calculation in claim_reward path
    )

    decision = await loop._handle_rewards(gs)
    assert decision is not None
    # Verify a claim_reward action was executed for the gold item.
    assert any(
        (a.get("action") if isinstance(a, dict) else getattr(a, "action", None))
        == "claim_reward"
        for a in executed
    )
