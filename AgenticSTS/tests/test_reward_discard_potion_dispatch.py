"""Regression: LLM emitting discard_potion via card_reward_action must be
accepted by the decision parser, pass validation against held-potion slots,
and dispatch to actions.discard_potion(idx).

Context — Plan 2 / Option B Fix F2:
The reward prompt includes a ``## Potion Slot Decision`` subsection that
instructs the LLM to discard a held potion when slots are full and a potion
reward is available. Before F2 the LLM could not actually emit the action —
the tool schema enum forbade it, the decision parser enum rejected it, and
there was no validation against reward-screen held-potion slots. F1 on the
mod side removed the server-side block; this test locks in the Python-side
wiring.
"""
from __future__ import annotations

from types import SimpleNamespace

from src.brain.decision_parser import _ACTION_ENUMS


def test_discard_potion_in_card_reward_action_enum():
    assert "discard_potion" in _ACTION_ENUMS["card_reward_action"]


def test_card_reward_tool_schema_lists_discard_potion():
    from src.brain.tool_schemas import CARD_REWARD_TOOL
    action_enum = CARD_REWARD_TOOL["input_schema"]["properties"]["action"]["enum"]
    assert "discard_potion" in action_enum


def _potion(index: int, *, occupied: bool = True, can_discard: bool = True):
    return SimpleNamespace(
        index=index,
        occupied=occupied,
        can_discard=can_discard,
        name=f"Pot{index}",
        description=f"Effect {index}.",
    )


async def test_reward_discard_potion_rejects_unknown_slot():
    """Validation should reject option_index that isn't a discardable held slot."""
    from src.agent.loop import AgentLoop
    from src.brain.models import LLMDecision

    loop = AgentLoop.__new__(AgentLoop)

    gs = SimpleNamespace(
        potions=[_potion(0), _potion(1, occupied=False)],  # only slot 0 is held
        available_actions=["choose_reward_card", "discard_potion"],
        state_type="card_reward",
    )
    llm_dec = LLMDecision(
        action_name="discard_potion",
        params={"option_index": 5},  # invalid — no such slot
        reasoning="discard slot 5",
        raw_text="",
        prompt_text="",
        latency_ms=0,
        tokens_used=0,
    )
    err = loop._validate_llm_decision(gs, llm_dec)
    assert err is not None
    assert "5" in err


async def test_reward_discard_potion_accepts_valid_held_slot():
    """Validation should accept option_index that matches a discardable held slot."""
    from src.agent.loop import AgentLoop
    from src.brain.models import LLMDecision

    loop = AgentLoop.__new__(AgentLoop)

    gs = SimpleNamespace(
        potions=[_potion(0), _potion(1), _potion(2)],
        available_actions=["choose_reward_card", "discard_potion"],
        state_type="card_reward",
    )
    llm_dec = LLMDecision(
        action_name="discard_potion",
        params={"option_index": 1},
        reasoning="discard slot 1",
        raw_text="",
        prompt_text="",
        latency_ms=0,
        tokens_used=0,
    )
    err = loop._validate_llm_decision(gs, llm_dec)
    assert err is None
