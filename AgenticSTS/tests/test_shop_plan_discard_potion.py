"""Regression: shop plan accepts discard_potion as a purchase action and
executes it by resolving the held-potion index by name.

Context — Plan 2 / Option B Fix F3:
The shop prompt's ``## Potion Slot Decision`` subsection tells the LLM to
discard a held potion before buying a new one when slots are full. F3 wires
this into the multi-step shop_plan tool: a plan item with action
``discard_potion`` and item_name = held potion's name executes first,
freeing a slot so a subsequent buy_potion succeeds.
"""

from types import SimpleNamespace

import pytest

from src.brain.tool_schemas import SHOP_PLAN_TOOL


def test_discard_potion_in_shop_plan_enum():
    purchases = SHOP_PLAN_TOOL["input_schema"]["properties"]["purchases"]
    action_enum = purchases["items"]["properties"]["action"]["enum"]
    assert "discard_potion" in action_enum


def _potion(index, name, occupied=True, can_discard=True):
    return SimpleNamespace(
        index=index, name=name, occupied=occupied, can_discard=can_discard,
    )


def _shop_item(index, name, price=50, is_stocked=True, enough_gold=True):
    return SimpleNamespace(
        index=index,
        name=name,
        price=price,
        is_stocked=is_stocked,
        enough_gold=enough_gold,
    )


def test_parse_shop_plan_accepts_discard_potion():
    """_parse_shop_plan should accept a purchase with action='discard_potion'
    and price=0, building a ShopPlanItem with the held-potion name."""
    from src.agent.loop import AgentLoop

    loop = AgentLoop.__new__(AgentLoop)

    decision_input = {
        "purchases": [
            {"action": "discard_potion", "item_name": "Speed Potion",
             "price": 0, "gold_after": 100, "reason": "free slot"},
            {"action": "buy_potion", "item_name": "Ghost Potion",
             "price": 50, "gold_after": 50, "reason": "upgrade"},
        ],
        "skipped_items": [],
        "reasoning": "swap weak potion for stronger one",
    }
    plan = loop._parse_shop_plan(decision_input)
    assert plan is not None
    assert len(plan.items) == 2
    assert plan.items[0].action == "discard_potion"
    assert plan.items[0].item_name == "Speed Potion"
    assert plan.items[1].action == "buy_potion"


@pytest.mark.asyncio
async def test_execute_shop_plan_discards_held_potion_by_name():
    """When executing a discard_potion step, the executor should find the
    held potion matching item_name and call actions.discard_potion(slot)."""
    from src.agent.loop import AgentLoop, ShopPlan, ShopPlanItem

    loop = AgentLoop.__new__(AgentLoop)

    executed: list[dict] = []

    async def fake_execute(action, **kwargs):
        executed.append(action if isinstance(action, dict) else {})

    loop._execute = fake_execute
    loop._shop_plan = ShopPlan(
        items=[
            ShopPlanItem(action="discard_potion", item_name="Speed Potion",
                         price=0, gold_after=100, reason="free slot"),
        ],
    )

    gs = SimpleNamespace(
        shop=SimpleNamespace(card_removal=None, potions=[], relics=[], cards=[]),
        potions=[
            _potion(0, "Fire Potion"),
            _potion(1, "Speed Potion"),
            _potion(2, "Block Potion"),
        ],
        run=SimpleNamespace(floor=7),
        state_type="shop",
        gold=100,
    )

    decision = await loop._execute_shop_plan_step(gs)
    assert decision is not None
    assert len(executed) == 1
    assert executed[0]["action"] == "discard_potion"
    assert executed[0]["option_index"] == 1  # slot of "Speed Potion"


@pytest.mark.asyncio
async def test_execute_shop_plan_discard_unknown_name_replans():
    """If the plan names a potion not currently held, executor returns None
    (replan signal) without executing any action."""
    from src.agent.loop import AgentLoop, ShopPlan, ShopPlanItem

    loop = AgentLoop.__new__(AgentLoop)

    async def no_execute(action, **kwargs):
        raise AssertionError("should not be called")

    loop._execute = no_execute
    loop._shop_plan = ShopPlan(
        items=[
            ShopPlanItem(action="discard_potion", item_name="Nonexistent Potion",
                         price=0, gold_after=100, reason="bad plan"),
        ],
    )

    gs = SimpleNamespace(
        shop=SimpleNamespace(card_removal=None, potions=[], relics=[], cards=[]),
        potions=[_potion(0, "Fire Potion")],
        run=SimpleNamespace(floor=7),
        state_type="shop",
        gold=100,
    )

    decision = await loop._execute_shop_plan_step(gs)
    assert decision is None  # replan triggered
    assert loop._shop_plan is None


@pytest.mark.asyncio
async def test_execute_shop_plan_skips_buy_potion_when_slots_full():
    """When a buy_potion step has gold-sufficient but enough_gold=False (because
    held-potion slots are full) AND the plan has no discard_potion step, the
    executor should silently skip the buy (preserving gold) and continue with
    the rest of the plan rather than aborting the run.

    Regression for the 2026-04-27 pilot run that aborted at floor 31 because
    the plan validator treated 'slots full' as 'unbuyable' and triggered a
    replan cascade with no valid LLM action available.

    Rationale: the shop prompt already exposes a 'SLOTS FULL — discard_potion
    first' hint at plan time. If the LLM still didn't prepend a discard, the
    buy is low-priority — better to keep the gold than to auto-discard an
    arbitrary held potion.
    """
    from src.agent.loop import AgentLoop, ShopPlan, ShopPlanItem

    loop = AgentLoop.__new__(AgentLoop)

    executed: list[dict] = []

    async def fake_execute(action, **kwargs):
        executed.append(action if isinstance(action, dict) else {})

    loop._execute = fake_execute
    loop._shop_plan = ShopPlan(
        items=[
            ShopPlanItem(action="buy_potion", item_name="Speed Potion",
                         price=51, gold_after=152, reason="extra mobility"),
            ShopPlanItem(action="buy_card", item_name="Reflex",
                         price=77, gold_after=75, reason="cycle"),
        ],
    )

    gs = SimpleNamespace(
        shop=SimpleNamespace(
            card_removal=None,
            potions=[
                _shop_item(0, "Speed Potion", price=51, enough_gold=False),
            ],
            relics=[],
            cards=[_shop_item(0, "Reflex", price=77, enough_gold=True)],
        ),
        potions=[
            _potion(0, "Block Potion"),
            _potion(1, "Fire Potion"),
            _potion(2, "Dexterity Potion"),
        ],
        run=SimpleNamespace(floor=31),
        state_type="shop",
        gold=203,
    )

    decision = await loop._execute_shop_plan_step(gs)
    # buy_potion was skipped, executor proceeded to buy_card 'Reflex'.
    assert decision is not None
    assert len(executed) == 1
    assert executed[0]["action"] == "buy_card"
    assert loop._shop_plan is not None
    # plan advanced past the skipped buy_potion AND the executed buy_card.
    assert loop._shop_plan.current_index == 2


@pytest.mark.asyncio
async def test_execute_shop_plan_skips_terminal_buy_potion_when_slots_full():
    """If the only remaining plan item is an unbuyable buy_potion (slots full),
    skipping it advances past the end and the executor returns None — letting
    the outer loop close the shop instead of aborting."""
    from src.agent.loop import AgentLoop, ShopPlan, ShopPlanItem

    loop = AgentLoop.__new__(AgentLoop)

    async def no_execute(action, **kwargs):
        raise AssertionError("should not be called")

    loop._execute = no_execute
    loop._shop_plan = ShopPlan(
        items=[
            ShopPlanItem(action="buy_potion", item_name="Speed Potion",
                         price=51, gold_after=152, reason="extra mobility"),
        ],
    )

    gs = SimpleNamespace(
        shop=SimpleNamespace(
            card_removal=None,
            potions=[
                _shop_item(0, "Speed Potion", price=51, enough_gold=False),
            ],
            relics=[],
            cards=[],
        ),
        potions=[_potion(0, "Block Potion")],
        run=SimpleNamespace(floor=31),
        state_type="shop",
        gold=203,
    )

    decision = await loop._execute_shop_plan_step(gs)
    assert decision is None
    # plan advanced and is now complete — outer loop will close shop.
    assert loop._shop_plan is not None
    assert loop._shop_plan.is_complete


@pytest.mark.asyncio
async def test_execute_shop_plan_replans_when_item_genuinely_unaffordable():
    """When a non-potion item is marked enough_gold=False AND the player can't
    actually afford it, the plan is discarded and a replan is triggered."""
    from src.agent.loop import AgentLoop, ShopPlan, ShopPlanItem

    loop = AgentLoop.__new__(AgentLoop)

    async def no_execute(action, **kwargs):
        raise AssertionError("should not be called")

    loop._execute = no_execute
    loop._shop_plan = ShopPlan(
        items=[
            ShopPlanItem(action="buy_relic", item_name="Whetstone",
                         price=151, gold_after=0, reason="upgrade"),
        ],
    )

    gs = SimpleNamespace(
        shop=SimpleNamespace(
            card_removal=None,
            potions=[],
            relics=[
                _shop_item(0, "Whetstone", price=151, enough_gold=False),
            ],
            cards=[],
        ),
        potions=[],
        run=SimpleNamespace(floor=36),
        state_type="shop",
        gold=50,
    )

    decision = await loop._execute_shop_plan_step(gs)
    assert decision is None
    assert loop._shop_plan is None
