"""Mechanical flow tests (potions, cards view, shop transitions).

Covers: forced potion discard, foul potion pre-shop throw, cards view
handling (close/proceed/confirm), and shop relic transition waits.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call

import src.agent.loop as loop_module
from src.brain.models import DecisionSource, LLMDecision
from src.mcp_client import actions
from src.mcp_client.upstream_models import RawRunPotionPayload

from tests.conftest import (
    make_cards_view_gs,
    make_loop,
    make_potion_discard_gs,
    make_selection_card,
    make_shop_gs,
)


def test_handle_mechanical_forced_discard_uses_potion_slot_index():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = make_potion_discard_gs(
        potions=[
            RawRunPotionPayload(
                index=0,
                name="Fire Potion",
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
            RawRunPotionPayload(
                index=2,
                name="Blessing of the Forge",
                occupied=True,
                can_use=False,
                can_discard=True,
            ),
        ]
    )

    result = asyncio.run(loop._handle_mechanical(gs))

    assert result is not None
    assert result.action == actions.discard_potion(2)
    assert result.source == "heuristic"
    loop._execute.assert_awaited_once_with(actions.discard_potion(2))


def test_decide_and_act_bypasses_llm_for_forced_potion_discard_with_save_and_quit():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._v2_engine = MagicMock()
    loop._v2_engine.decide_noncombat = AsyncMock(return_value=None)
    loop._use_llm = True
    gs = make_potion_discard_gs(
        state_type="map",
        available_actions=["discard_potion", "save_and_quit"],
        potions=[
            RawRunPotionPayload(
                index=0,
                name="Fire Potion",
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
            RawRunPotionPayload(
                index=2,
                name="Blessing of the Forge",
                occupied=True,
                can_use=False,
                can_discard=True,
            ),
        ],
    )

    result = asyncio.run(loop._decide_and_act(gs, step=1))

    assert result is not None
    assert result.action == actions.discard_potion(2)
    assert result.source == "heuristic"
    loop._v2_engine.decide_noncombat.assert_not_awaited()
    loop._execute.assert_awaited_once_with(actions.discard_potion(2))


def test_decide_and_act_throws_all_foul_potions_before_opening_shop():
    client = MagicMock()
    loop = make_loop(client)
    loop._use_llm = True
    loop._v2_engine = MagicMock()
    loop._v2_engine.decide_noncombat = AsyncMock(return_value=None)
    gs = make_shop_gs(
        is_open=False,
        available_actions=["use_potion", "open_shop_inventory"],
        potions=[
            RawRunPotionPayload(
                index=1,
                potion_id="FOUL_POTION",
                name="Foul Potion",
                description=(
                    "Deal 12 damage to EVERYONE. "
                    "Can be thrown at the Merchant for 100 Gold instead."
                ),
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
            RawRunPotionPayload(
                index=2,
                potion_id="FOUL_POTION",
                name="Foul Potion",
                description=(
                    "Deal 12 damage to EVERYONE. "
                    "Can be thrown at the Merchant for 100 Gold instead."
                ),
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
        ],
    )
    after_first_throw = make_shop_gs(
        is_open=False,
        available_actions=["use_potion", "open_shop_inventory"],
        potions=[
            RawRunPotionPayload(
                index=2,
                potion_id="FOUL_POTION",
                name="Foul Potion",
                description=(
                    "Deal 12 damage to EVERYONE. "
                    "Can be thrown at the Merchant for 100 Gold instead."
                ),
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
        ],
    )
    after_second_throw = make_shop_gs(
        is_open=False,
        available_actions=["open_shop_inventory"],
        potions=[],
    )
    after_first_throw_state = after_first_throw.raw.model_dump(mode="json")
    after_first_throw_state["run"]["gold"] = 444
    after_second_throw_state = after_second_throw.raw.model_dump(mode="json")
    after_second_throw_state["run"]["gold"] = 544
    loop._execute = AsyncMock(
        side_effect=[
            {"stable": True, "state": after_first_throw_state},
            {"stable": True, "state": after_second_throw_state},
            {"stable": True},
        ]
    )

    result = asyncio.run(loop._decide_and_act(gs, step=1))

    assert result is not None
    assert result.action == actions.open_shop_inventory()
    assert result.source == "heuristic"
    assert "200 gold" in result.reasoning.lower()
    assert "open shop" in result.reasoning.lower()
    assert loop._shop_auto_opened_this_visit is True
    loop._v2_engine.decide_noncombat.assert_not_awaited()
    assert loop._execute.await_args_list == [
        call(
            actions.use_potion(1),
            delta_source="Foul Potion",
        ),
        call(
            actions.use_potion(2),
            delta_source="Foul Potion",
        ),
        call(actions.open_shop_inventory()),
    ]


def test_force_unstick_skips_generic_discard_potion_without_slot_index():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = make_potion_discard_gs(
        available_actions=["select_deck_card", "discard_potion"],
        state_type="card_select",
    )

    result = asyncio.run(loop._force_unstick(gs))

    assert result is None
    loop._execute.assert_not_awaited()


def test_handle_cards_view_records_preview_and_closes_view():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._pack_last_clicked_option = 1
    gs = make_cards_view_gs(cards=[make_selection_card("Acrobatics", 0)])

    result = asyncio.run(loop._handle_cards_view(gs))

    assert result is not None
    assert result.action == actions.close_cards_view()
    assert [card.name for card in loop._pack_previews[1]] == ["Acrobatics"]
    loop._execute.assert_awaited_once_with(actions.close_cards_view())


def test_handle_cards_view_proceeds_when_close_is_unavailable():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._pack_last_clicked_option = 2
    gs = make_cards_view_gs(
        title="Pandora's Box",
        cards=[make_selection_card("Noxious Fumes", 0)],
        available_actions=["proceed"],
    )

    result = asyncio.run(loop._handle_cards_view(gs))

    assert result is not None
    assert result.action == actions.proceed()
    assert result.reasoning == "Proceed from cards view"
    assert [card.name for card in loop._pack_previews[2]] == ["Noxious Fumes"]
    loop._execute.assert_awaited_once_with(actions.proceed())


def test_handle_cards_view_confirms_when_confirm_is_unavailable_exit():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._pack_last_clicked_option = 3
    gs = make_cards_view_gs(
        title="Pandora's Box",
        cards=[make_selection_card("Adrenaline", 0)],
        available_actions=["confirm_selection"],
    )

    result = asyncio.run(loop._handle_cards_view(gs))

    assert result is not None
    assert result.action == actions.confirm_selection()
    assert result.reasoning == "Confirm cards view"
    assert [card.name for card in loop._pack_previews[3]] == ["Adrenaline"]
    loop._execute.assert_awaited_once_with(actions.confirm_selection())


def test_handle_mechanical_routes_cards_view_without_close_action():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = make_cards_view_gs(
        title="Pandora's Box",
        cards=[make_selection_card("Adrenaline", 0)],
        available_actions=["proceed"],
    )

    result = asyncio.run(loop._handle_mechanical(gs))

    assert result is not None
    assert result.action == actions.proceed()
    assert result.reasoning == "Proceed from cards view"
    loop._execute.assert_awaited_once_with(actions.proceed())


def test_handle_mechanical_routes_cards_view_with_confirm_action():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = make_cards_view_gs(
        title="Pandora's Box",
        cards=[make_selection_card("Noxious Fumes", 0)],
        available_actions=["confirm_selection"],
    )

    result = asyncio.run(loop._handle_mechanical(gs))

    assert result is not None
    assert result.action == actions.confirm_selection()
    assert result.reasoning == "Confirm cards view"
    loop._execute.assert_awaited_once_with(actions.confirm_selection())


def test_execute_llm_decision_waits_for_orrery_transition_after_shop_purchase():
    client = MagicMock()
    client.wait_for_state_change = AsyncMock(return_value={"data": {"screen": "REWARD"}})
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = make_shop_gs(relic_name="Orrery", relic_index=2)

    decision, error = asyncio.run(
        loop._execute_llm_decision(
            gs,
            LLMDecision(
                action_name="buy_relic",
                params={"option_index": 2},
                reasoning="Orrery opens 5 card rewards.",
            ),
            DecisionSource.LLM,
        )
    )

    assert error is None
    assert decision is not None
    assert decision.action == actions.buy_relic(2)
    loop._execute.assert_awaited_once_with(
        actions.buy_relic(2),
        delta_source=None,
        delta_target=None,
    )
    client.wait_for_state_change.assert_awaited_once_with("shop", timeout=4.0)


def test_wait_for_post_shop_relic_transition_ignores_timeout_for_orrery(caplog):
    client = MagicMock()
    client.wait_for_state_change = AsyncMock(side_effect=loop_module.McpTimeout("slow"))
    loop = make_loop(client)
    gs = make_shop_gs(relic_name="Orrery", relic_index=2)

    with caplog.at_level("WARNING"):
        asyncio.run(loop._wait_for_post_shop_relic_transition(gs, 2))

    assert "Orrery" in caplog.text
    client.wait_for_state_change.assert_awaited_once_with("shop", timeout=4.0)
