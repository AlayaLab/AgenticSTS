"""Combat planning, validation, and execution tests.

Covers: combat type resolution, action execution stability,
combat plan generation/validation, energy ordering, and card generation logic.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import src.agent.loop as loop_module
from src.brain.conversation import CombatConversation
from src.brain.planner import CombatPlan, PlannedAction
from src.mcp_client import actions
from src.mcp_client.upstream_models import (
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawRunPayload,
    RawRunPotionPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState
from tests.conftest import (
    instant_sleep as _instant_sleep,
)
from tests.conftest import (
    make_card_select_gs,
    make_combat_gs,
    make_enemy,
    make_hand_card,
    make_loop,
    make_selection_card,
)


def test_resolve_combat_type_uses_boss_floor_fallback_without_map():
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="COMBAT",
        in_combat=True,
        turn=1,
        available_actions=["play_card", "end_turn"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=52, max_hp=67, energy=3),
            hand=[
                RawCombatHandCardPayload(
                    index=0,
                    card_id="strike",
                    name="Strike",
                    playable=True,
                    energy_cost=1,
                    damage=6,
                    rules_text="Deal 6 damage.",
                    requires_target=True,
                    target_index_space="enemies",
                ),
            ],
            enemies=[make_enemy(name="Test Subject #C10", hp=240, max_hp=240)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=51,
            current_hp=52,
            max_hp=67,
            gold=99,
            max_energy=3,
            deck=[],
        ),
        map=None,
    )
    gs = GameState(raw=raw, state_type="monster")

    assert loop._resolve_combat_type(gs) == "boss"


def test_resolve_combat_type_prefers_mod_native_metadata():
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="COMBAT",
        in_combat=True,
        turn=1,
        combat_type="elite",
        available_actions=["play_card", "end_turn"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=52, max_hp=67, energy=3),
            hand=[],
            enemies=[make_enemy(name="Book of Stabbing", hp=170, max_hp=170)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=17,
            current_hp=52,
            max_hp=67,
            gold=99,
            max_energy=3,
            deck=[],
        ),
        map=None,
    )
    gs = GameState(raw=raw, state_type="boss")

    assert loop._resolve_combat_type(gs) == "elite"


def test_resolve_combat_type_for_logging_ignores_previous_combat_cache():
    client = MagicMock()
    loop = make_loop(client)
    loop._last_combat_type = "monster"

    raw = UpstreamGameState(
        screen="COMBAT",
        in_combat=True,
        turn=1,
        available_actions=["play_card", "end_turn"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=52, max_hp=67, energy=3),
            hand=[],
            enemies=[make_enemy(name="Book of Stabbing", hp=170, max_hp=170)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=16,
            current_hp=52,
            max_hp=67,
            gold=99,
            max_energy=3,
            deck=[],
        ),
        map=None,
    )
    gs = GameState(raw=raw, state_type="elite")

    assert loop._state_machine.in_combat is False
    assert loop._resolve_combat_type_for_logging(gs) == "elite"


def test_execute_waits_for_screen_change_on_unstable_action(monkeypatch):
    client = MagicMock()
    client.get_state = AsyncMock(side_effect=[
        {"data": {"state_version": 10, "screen": "MONSTER"}},
        {"data": {"state_version": 10, "screen": "CARD_SELECT"}},
    ])
    client.post_action = AsyncMock(return_value={"stable": False})
    loop = make_loop(client)

    monkeypatch.setattr(loop_module.config, "ACTION_DELAY", 0)
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    result = asyncio.run(loop._execute({"action": "play_card", "card_index": 0}))

    assert not result["stable"]
    assert "state" in result  # _execute enriches result with settled state
    assert client.get_state.await_count == 2
    assert client.post_action.await_count == 1


def test_execute_warns_instead_of_aborting_after_unstable_timeout(monkeypatch, caplog):
    client = MagicMock()
    client.get_state = AsyncMock(
        side_effect=[{"data": {"state_version": 10, "screen": "MONSTER"}}] * 9
    )
    client.post_action = AsyncMock(return_value={"stable": False})
    loop = make_loop(client)

    monkeypatch.setattr(loop_module.config, "ACTION_DELAY", 0)
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    with caplog.at_level("WARNING"):
        result = asyncio.run(loop._execute({"action": "play_card", "card_index": 0}))

    assert not result["stable"]
    assert "state" in result  # _execute enriches result with settled state
    assert "not stable after 4s" in caplog.text
    assert client.get_state.await_count == 9


def test_execute_attaches_settled_state_to_action_result(monkeypatch):
    pre_state = make_card_select_gs().raw.model_dump(by_alias=True)
    post_state = make_card_select_gs(
        prompt="Choose one pack.",
        kind="choose_card_select",
        cards=[
            make_selection_card("Pack Alpha", 0, card_type="Bundle"),
            make_selection_card("Pack Beta", 1, card_type="Bundle"),
        ],
        preview_cards=[make_selection_card("Backflip", 0)],
    ).raw.model_dump(by_alias=True)

    client = MagicMock()
    client.get_state = AsyncMock(side_effect=[pre_state, post_state])
    client.post_action = AsyncMock(return_value={"stable": True, "status": "completed"})
    loop = make_loop(client)

    monkeypatch.setattr(loop_module.config, "ACTION_DELAY", 0)

    result = asyncio.run(loop._execute(actions.select_deck_card(0)))

    assert result is not None
    assert result["state"] == post_state


def test_execute_reuses_state_from_action_result(monkeypatch):
    pre_state = make_card_select_gs().raw.model_dump(by_alias=True)
    post_state = make_card_select_gs(
        prompt="Choose one pack.",
        kind="choose_card_select",
        cards=[
            make_selection_card("Pack Alpha", 0, card_type="Bundle"),
            make_selection_card("Pack Beta", 1, card_type="Bundle"),
        ],
        preview_cards=[make_selection_card("Backflip", 0)],
    ).raw.model_dump(by_alias=True)

    client = MagicMock()
    client.get_state = AsyncMock(return_value=pre_state)
    client.post_action = AsyncMock(
        return_value={"stable": True, "status": "completed", "state": post_state}
    )
    loop = make_loop(client)

    monkeypatch.setattr(loop_module.config, "ACTION_DELAY", 0)

    result = asyncio.run(loop._execute(actions.select_deck_card(0)))

    assert result is not None
    assert result["state"] == post_state
    assert client.get_state.await_count == 1


def test_empty_end_turn_plan_is_trusted_even_with_playable_cards():
    gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    client.wait_for_play_phase = AsyncMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(actions=(), end_turn=True, reasoning="Already fully blocked")
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    assert result.source == "plan"
    loop._execute.assert_awaited_once_with(actions.end_turn(), delta_source="turn_end")


def test_generate_combat_plan_injects_preprocessor_hints_into_conversation():
    gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True),
    ])
    client = MagicMock()
    loop = make_loop(client)
    loop._v2_combat_conversation = CombatConversation(system_prompt="test")
    loop._v2_combat_conversation.add_combat_start(gs)
    loop._v2_engine = MagicMock()
    loop._v2_engine.generate_combat_plan = AsyncMock(return_value=None)
    loop._v2_tool_executor = MagicMock()

    preprocessor = MagicMock()
    preprocessor.run_applicable.return_value = [MagicMock(tool_name="turn_lethal_check")]
    preprocessor.format_hints.return_value = (
        "## Computed Insights\n**turn_lethal_check**: NO-GO"
    )
    loop._tool_preprocessor = preprocessor

    asyncio.run(loop._generate_combat_plan(gs))

    last_user = [
        msg["content"]
        for msg in loop._v2_combat_conversation.messages
        if msg["role"] == "user" and isinstance(msg["content"], str)
    ][-1]
    assert "## Computed Insights" in last_user
    assert last_user.index("## Computed Insights") < last_user.index("## Round")
    assert "## Round" in last_user
    preprocessor.run_applicable.assert_called_once_with("monster", gs)
    loop._v2_engine.generate_combat_plan.assert_awaited_once()


def test_empty_plan_without_end_turn_falls_back_to_single_card_path():
    gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "MONSTER"}})
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._generate_combat_plan = AsyncMock(
        return_value=CombatPlan(actions=(), end_turn=False, reasoning="No plan")
    )
    loop._execute = AsyncMock(return_value={"stable": True})

    with patch.object(loop_module, "parse_state", return_value=gs):
        result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is None
    assert loop._combat_plan is None
    loop._execute.assert_not_awaited()


def test_remaining_unplayable_planned_cards_end_turn_normally():
    gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True),
        make_hand_card("Bash", 1, playable=False),
    ])
    client = MagicMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
            PlannedAction(action_type="card", card_name="Bash", target_index=0),
        ),
        end_turn=True,
        reasoning="Spent energy already",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 1
    loop._execute = AsyncMock(return_value={"stable": True})

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.end_turn()
    assert "unplayable" in result.reasoning.lower()
    loop._execute.assert_awaited_once_with(actions.end_turn(), delta_source="turn_end")


def test_execute_combat_plan_resolves_potion_name_without_slot_index():
    gs = make_combat_gs(
        [make_hand_card("Strike", 0, playable=True)],
        potions=[
            RawRunPotionPayload(
                index=1,
                name="Attack Potion",
                occupied=True,
                can_use=True,
                can_discard=True,
            ),
        ],
    )
    client = MagicMock()
    loop = make_loop(client)
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(PlannedAction(action_type="potion", potion_name="Attack Potion"),),
        end_turn=False,
        reasoning="Use the potion first",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(return_value={"stable": True})

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.use_potion(1)
    assert result.source == "plan"
    loop._execute.assert_awaited_once_with(
        actions.use_potion(1),
        delta_source="Attack Potion",
        delta_target=None,
    )


def test_execute_combat_plan_does_not_split_on_delayed_draw_text():
    gs = make_combat_gs([
        make_hand_card(
            "Predator+",
            0,
            playable=True,
            energy_cost=2,
            rules_text="Deal 21 damage. Next turn, draw 2 cards.",
        ),
        make_hand_card("Strike", 1, playable=True, rules_text="Deal 6 damage."),
    ])
    post_gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True, rules_text="Deal 6 damage."),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Predator", target_index=0),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="Predator then Strike",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0, 0)
    assert loop._combat_plan is not None
    assert loop._combat_plan_index == 1


def test_execute_combat_plan_does_not_split_on_remaining_preview_text_changes():
    gs = make_combat_gs([
        make_hand_card(
            "Shiv",
            0,
            playable=True,
            energy_cost=0,
            rules_text="Retain. Deal 13 damage to ALL enemies. Exhaust.",
        ),
        make_hand_card(
            "Defend",
            1,
            playable=True,
            requires_target=False,
            rules_text="Gain 8 Block.",
        ),
        make_hand_card("Strike", 2, playable=True, rules_text="Deal 6 damage."),
    ])
    post_gs = make_combat_gs([
        make_hand_card(
            "Defend",
            0,
            playable=True,
            requires_target=False,
            rules_text="Gain 7 Block.",
        ),
        make_hand_card("Strike", 1, playable=True, rules_text="Deal 5 damage."),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="Shiv first before Tender changes previews",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0, 0)
    assert loop._combat_plan is not None
    assert loop._prev_combat_plan is None
    assert loop._combat_plan_index == 1


def test_execute_combat_plan_splits_when_mcp_hand_count_increases():
    gs = make_combat_gs([
        make_hand_card("Mystery Draw", 0, playable=True, requires_target=False),
        make_hand_card("Strike", 1, playable=True, rules_text="Deal 6 damage."),
    ])
    post_gs = make_combat_gs([
        make_hand_card("Strike", 0, playable=True, rules_text="Deal 6 damage."),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Mystery Draw", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="Draw then attack",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0)
    assert loop._prev_combat_plan is not None
    assert loop._combat_plan is None


def test_execute_combat_plan_skips_replan_when_plan_consumes_generated_shivs():
    """Blade Dance adds 3 Shivs; plan already queued Shiv x3 → no re-plan."""
    gs = make_combat_gs([
        make_hand_card(
            "Blade Dance", 0, playable=True, requires_target=False,
            rules_text="Add 3 Shivs to your hand.",
        ),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    post_gs = make_combat_gs([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card(
            "Shiv", 1, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
        make_hand_card(
            "Shiv", 2, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
        make_hand_card(
            "Shiv", 3, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Blade Dance", target_index=None),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
        ),
        end_turn=True,
        reasoning="Generate then spend Shivs",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0)
    # Plan should be PRESERVED — Shivs are consumed by the remaining plan
    assert loop._combat_plan is not None
    assert loop._prev_combat_plan is None
    assert loop._combat_plan_index == 1


def test_execute_combat_plan_still_replans_when_shivs_not_fully_consumed():
    """Blade Dance adds 3 Shivs; plan queued only 1 Shiv → still re-plan."""
    gs = make_combat_gs([
        make_hand_card(
            "Blade Dance", 0, playable=True, requires_target=False,
            rules_text="Add 3 Shivs to your hand.",
        ),
        make_hand_card("Defend", 1, playable=True, requires_target=False),
    ])
    post_gs = make_combat_gs([
        make_hand_card("Defend", 0, playable=True, requires_target=False),
        make_hand_card(
            "Shiv", 1, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
        make_hand_card(
            "Shiv", 2, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
        make_hand_card(
            "Shiv", 3, playable=True, energy_cost=0,
            rules_text="Deal 4 damage. Exhaust.",
        ),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Blade Dance", target_index=None),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
        ),
        end_turn=True,
        reasoning="Generate then spend one Shiv",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0)
    # Only 1 Shiv queued to consume 3 generated — must re-plan
    assert loop._combat_plan is None
    assert loop._prev_combat_plan is not None


def test_execute_combat_plan_splits_when_mcp_hand_identity_changes():
    gs = make_combat_gs([
        make_hand_card("Calculated Gamble", 0, playable=True, requires_target=False),
        make_hand_card("Strike", 1, playable=True, rules_text="Deal 6 damage."),
        make_hand_card("Defend", 2, playable=True, requires_target=False),
    ])
    post_gs = make_combat_gs([
        make_hand_card("Backflip", 0, playable=True, requires_target=False),
        make_hand_card("Survivor", 1, playable=True, requires_target=False),
    ])
    loop = make_loop(MagicMock())
    loop._last_combat_round = gs.combat_round
    loop._combat_plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Calculated Gamble", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="Gamble then attack",
    )
    loop._combat_plan_round = gs.combat_round
    loop._combat_plan_index = 0
    loop._execute = AsyncMock(
        return_value={"stable": True, "state": post_gs.raw.model_dump(by_alias=True)}
    )

    result = asyncio.run(loop._execute_combat_plan(gs))

    assert result is not None
    assert result.action == actions.play_card(0)
    assert loop._prev_combat_plan is not None
    assert loop._combat_plan is None


def test_validate_combat_plan_rejects_bad_energy_order_for_x_cost_card():
    gs = make_combat_gs(
        [
            make_hand_card(
                "Tools of the Trade",
                0,
                playable=True,
                requires_target=False,
                rules_text="At the start of your turn, draw 1 card and discard 1 card.",
            ),
            make_hand_card(
                "Defend",
                1,
                playable=True,
                requires_target=False,
                rules_text="Gain 5 Block.",
            ),
            make_hand_card(
                "Malaise++",
                2,
                playable=True,
                energy_cost=0,
                rules_text="Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust.",
            ),
            make_hand_card(
                "Flechettes",
                3,
                playable=True,
                energy_cost=0,
                rules_text="Deal 5 damage for each Skill in your Hand.",
            ),
        ],
        energy=3,
    )
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Malaise++", target_index=0),
            PlannedAction(action_type="card", card_name="Flechettes", target_index=0),
            PlannedAction(action_type="card", card_name="Tools of the Trade", target_index=None),
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
        ),
        end_turn=True,
        reasoning="Bad order",
    )

    error, _valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert not error.startswith("ENERGY_CHECK:")  # Hard error, not soft
    assert "Invalid plan order" in error
    assert "X-cost" in error


def test_validate_combat_plan_allows_generated_card_after_generator():
    gs = make_combat_gs(
        [
            make_hand_card(
                "Cloak and Dagger",
                0,
                playable=True,
                energy_cost=1,
                requires_target=False,
                rules_text="Gain 4 Block. Add 1 Shiv to your hand.",
            ),
            make_hand_card("Shiv", 1, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
            make_hand_card("Shiv", 2, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
            make_hand_card("Shiv", 3, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
        ],
        energy=3,
    )
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Cloak and Dagger", target_index=None),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
        ),
        end_turn=True,
        reasoning="Use generated Shiv after Cloak and Dagger resolves",
    )

    error, _valid_count = loop._validate_combat_plan(plan, gs)
    assert error is None


def test_validate_combat_plan_rejects_missing_generated_card_before_generator():
    gs = make_combat_gs(
        [
            make_hand_card(
                "Cloak and Dagger",
                0,
                playable=True,
                energy_cost=1,
                requires_target=False,
                rules_text="Gain 4 Block. Add 1 Shiv to your hand.",
            ),
            make_hand_card("Shiv", 1, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
            make_hand_card("Shiv", 2, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
            make_hand_card("Shiv", 3, playable=True, energy_cost=0, rules_text="Deal 4 damage."),
        ],
        energy=3,
    )
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Shiv", target_index=0),
            PlannedAction(action_type="card", card_name="Cloak and Dagger", target_index=None),
        ),
        end_turn=True,
        reasoning="Illegal extra Shiv before the generator resolves",
    )

    error, _valid_count = loop._validate_combat_plan(plan, gs)

    assert error is not None
    assert "not in your playable hand yet" in error


def test_validate_combat_plan_tolerates_cost_changing_card():
    """Bullet Time (3E) makes all hand cards cost 0.

    Plan: Bullet Time(3E) -> Defend(1E) -> Strike(1E) should PASS validation
    because the energy deficit is caused by a non-X-cost card (possible
    cost-changer). The validator trusts the LLM for these sequences.
    """
    gs = make_combat_gs(
        [
            make_hand_card(
                "Bullet Time",
                0,
                playable=True,
                energy_cost=3,
                requires_target=False,
                rules_text="You can no longer draw additional cards. "
                "Reduce the cost of all cards in your hand to 0 this turn.",
            ),
            make_hand_card(
                "Defend",
                1,
                playable=True,
                energy_cost=1,
                requires_target=False,
                rules_text="Gain 5 Block.",
            ),
            make_hand_card(
                "Strike",
                2,
                playable=True,
                energy_cost=1,
                rules_text="Deal 6 damage.",
            ),
        ],
        energy=3,
    )
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Bullet Time", target_index=None),
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Strike", target_index=0),
        ),
        end_turn=True,
        reasoning="Bullet Time makes everything free",
    )

    error, _valid_count = loop._validate_combat_plan(plan, gs)

    # Should pass -- trust the LLM for cost-changing card sequences
    assert error is None


def test_validate_combat_plan_allows_energy_legal_order_for_same_cards():
    gs = make_combat_gs(
        [
            make_hand_card(
                "Tools of the Trade",
                0,
                playable=True,
                requires_target=False,
                rules_text="At the start of your turn, draw 1 card and discard 1 card.",
            ),
            make_hand_card(
                "Defend",
                1,
                playable=True,
                requires_target=False,
                rules_text="Gain 5 Block.",
            ),
            make_hand_card(
                "Malaise++",
                2,
                playable=True,
                energy_cost=0,
                rules_text="Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust.",
            ),
            make_hand_card(
                "Flechettes",
                3,
                playable=True,
                energy_cost=0,
                rules_text="Deal 5 damage for each Skill in your Hand.",
            ),
        ],
        energy=3,
    )
    loop = make_loop(MagicMock())
    plan = CombatPlan(
        actions=(
            PlannedAction(action_type="card", card_name="Tools of the Trade", target_index=None),
            PlannedAction(action_type="card", card_name="Defend", target_index=None),
            PlannedAction(action_type="card", card_name="Malaise++", target_index=0),
            PlannedAction(action_type="card", card_name="Flechettes", target_index=0),
        ),
        end_turn=True,
        reasoning="Good order",
    )

    error, _valid_count = loop._validate_combat_plan(plan, gs)

    assert error is None
