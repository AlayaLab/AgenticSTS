"""Card/hand/batch selection tests.

Covers: pack selection previews, hand select (discard/retain), batch card
selection with re-resolution, Crystal Sphere event heuristic, and
_parse_select_count_from_prompt.
"""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, call, patch

import src.agent.loop as loop_module
from src.agent.loop import AgentLoop
from src.brain.models import DecisionSource, LLMDecision
from src.brain.planner import PlannedAction
from src.mcp_client import actions
from src.mcp_client.upstream_models import (
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawEventOptionPayload,
    RawRunPayload,
    RawSelectionCardPayload,
    RawSelectionPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState

from tests.conftest import (
    make_card_select_gs,
    make_enemy,
    make_event_gs,
    make_loop,
    make_selection_card,
    instant_sleep as _instant_sleep,
)


def test_pack_selection_preview_records_current_pack_then_opens_next_pack():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": False})
    pack_cards = [
        make_selection_card("Pack Alpha", 0, card_type="Bundle"),
        make_selection_card("Pack Beta", 1, card_type="Bundle"),
    ]

    first_state = make_card_select_gs(
        available_actions=["select_deck_card"],
        can_confirm=False,
        prompt="Choose one pack.",
        cards=pack_cards,
        kind="choose_card_select",
    )
    first_result = asyncio.run(loop._handle_pack_selection_preview(first_state))

    second_state = make_card_select_gs(
        available_actions=["select_deck_card", "confirm_selection"],
        can_confirm=True,
        selected_count=1,
        prompt="Choose one pack.",
        cards=pack_cards,
        preview_cards=[
            make_selection_card("Backflip", 0),
            make_selection_card("Prepared", 1),
        ],
        kind="choose_card_select",
    )
    second_result = asyncio.run(loop._handle_pack_selection_preview(second_state))

    assert first_result is not None
    assert first_result.action == actions.select_deck_card(0)
    assert second_result is not None
    assert second_result.action == actions.select_deck_card(1)
    assert [card.name for card in loop._pack_previews[0]] == ["Backflip", "Prepared"]


def test_build_state_prompt_v2_uses_pack_prompt_after_all_previews():
    loop = make_loop(MagicMock())
    pack_cards = [
        make_selection_card("Pack Alpha", 0, card_type="Bundle"),
        make_selection_card("Pack Beta", 1, card_type="Bundle"),
    ]
    gs = make_card_select_gs(
        available_actions=["select_deck_card", "confirm_selection"],
        can_confirm=True,
        selected_count=1,
        prompt="Choose one pack.",
        cards=pack_cards,
        preview_cards=[make_selection_card("Calculated Gamble", 0)],
        kind="choose_card_select",
    )

    loop._sync_pack_selection_session(gs)
    loop._pack_last_clicked_option = 1
    loop._pack_previews = {
        0: [make_selection_card("Backflip", 0)],
        1: [make_selection_card("Calculated Gamble", 0)],
    }

    prompt = loop._build_state_prompt_v2(gs)

    assert "## Pack Selection" in prompt
    assert "Current preview/selection: [1] Pack Beta" in prompt
    assert "`confirm_selection`" in prompt
    assert "Backflip" in prompt
    assert "Calculated Gamble" in prompt


def test_pack_selection_preview_uses_action_result_state_and_ignores_stale_selection_preview():
    client = MagicMock()
    loop = make_loop(client)
    pack_cards = [
        make_selection_card("Pack Alpha", 0, card_type="Bundle"),
        make_selection_card("Pack Beta", 1, card_type="Bundle"),
    ]
    initial_state = make_card_select_gs(
        available_actions=["select_deck_card"],
        can_confirm=False,
        prompt="Choose one pack.",
        cards=pack_cards,
        kind="choose_card_select",
    )
    stale_first_preview_state = make_card_select_gs(
        available_actions=["select_deck_card", "confirm_selection"],
        can_confirm=True,
        selected_count=1,
        prompt="Choose one pack.",
        cards=pack_cards,
        preview_cards=[
            make_selection_card("Backflip", 0),
            make_selection_card("Prepared", 1),
        ],
        kind="choose_card_select",
    )
    second_preview_state = make_card_select_gs(
        available_actions=["select_deck_card", "confirm_selection"],
        can_confirm=True,
        selected_count=1,
        prompt="Choose one pack.",
        cards=pack_cards,
        preview_cards=[
            make_selection_card("Calculated Gamble", 0),
            make_selection_card("Acrobatics", 1),
        ],
        kind="choose_card_select",
    )
    loop._execute = AsyncMock(
        side_effect=[
            {
                "stable": False,
                "state": stale_first_preview_state.raw.model_dump(by_alias=True),
            },
            {
                "stable": False,
                "state": second_preview_state.raw.model_dump(by_alias=True),
            },
        ]
    )

    first_result = asyncio.run(loop._handle_pack_selection_preview(initial_state))
    second_result = asyncio.run(loop._handle_pack_selection_preview(stale_first_preview_state))
    prompt = loop._build_state_prompt_v2(stale_first_preview_state)

    assert first_result is not None
    assert first_result.action == actions.select_deck_card(0)
    assert second_result is not None
    assert second_result.action == actions.select_deck_card(1)
    assert [card.name for card in loop._pack_previews[0]] == ["Backflip", "Prepared"]
    assert [card.name for card in loop._pack_previews[1]] == ["Calculated Gamble", "Acrobatics"]
    assert "Calculated Gamble" in prompt
    assert "Acrobatics" in prompt


def test_execute_llm_decision_single_select_confirms_when_refresh_exposes_confirm(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    initial_gs = make_card_select_gs(
        available_actions=["select_deck_card"],
        can_confirm=False,
        prompt="Choose one pack.",
        cards=[make_selection_card("Pack Alpha", 0, card_type="Bundle")],
        kind="choose_card_select",
    )
    refreshed_gs = make_card_select_gs(
        available_actions=["select_deck_card", "confirm_selection"],
        can_confirm=True,
        selected_count=1,
        prompt="Choose one pack.",
        cards=[make_selection_card("Pack Alpha", 0, card_type="Bundle")],
        preview_cards=[make_selection_card("Backflip", 0)],
        kind="choose_card_select",
    )
    loop._refresh_selection_state = AsyncMock(return_value=refreshed_gs)
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    decision, error = asyncio.run(
        loop._execute_llm_decision(
            initial_gs,
            LLMDecision(
                action_name="select_deck_card",
                params={"option_index": 0},
                reasoning="Preview and take Pack Alpha.",
            ),
            DecisionSource.LLM,
        )
    )

    assert error is None
    assert decision is not None
    assert any(
        awaited == call(actions.confirm_selection(), delta_source="confirm")
        for awaited in loop._execute.await_args_list
    )


def test_handle_card_select_does_not_confirm_without_actual_selection(monkeypatch):
    gs = make_card_select_gs(
        can_confirm=True,
        selected_count=0,
        max_select=2,
        prompt="Choose 2 cards.",
        cards=[
            RawSelectionCardPayload(
                index=7,
                card_id="slice",
                name="Slice",
                card_type="Attack",
                rarity="Common",
            ),
        ],
    )
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    monkeypatch.setattr(loop_module.random, "choice", lambda seq: seq[0])

    result = asyncio.run(loop._handle_card_select(gs))

    assert result is not None
    assert result.action == actions.select_deck_card(7)
    assert "Select Slice" in result.reasoning
    loop._execute.assert_awaited_once_with(actions.select_deck_card(7), delta_source="Slice")


def test_build_state_prompt_uses_hand_select_for_combat_hand_select():
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=54, max_hp=89, block=0, energy=4),
            enemies=[make_enemy(name="Myte", hp=40, max_hp=64)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=30,
            current_hp=54,
            max_hp=89,
            gold=0,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose [blue]2[/blue] cards to [gold]Discard[/gold].[/center]",
            min_select=2,
            max_select=2,
            selected_count=0,
            can_confirm=False,
            cards=[
                RawSelectionCardPayload(
                    index=0,
                    card_id="abrasive",
                    name="Abrasive",
                    card_type="Skill",
                    energy_cost=3,
                    rules_text="Sly. Gain 1 Dexterity. Gain 4 Thorns.",
                ),
                RawSelectionCardPayload(
                    index=1,
                    card_id="untouchable",
                    name="Untouchable+",
                    upgraded=True,
                    card_type="Skill",
                    energy_cost=2,
                    rules_text="Sly. Gain 15 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    assert gs.state_type == "hand_select"
    assert "## Hand Selection (In-Combat)" in prompt
    assert "Discard = temporary" in prompt
    assert "Abrasive" in prompt
    assert "PRIORITY: Discard a Sly card" in prompt
    assert "THE SLY CARD ITSELF" in prompt


def test_build_state_prompt_allows_skipping_optional_retain_selection():
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=80, max_hp=86, block=9, energy=0),
            enemies=[make_enemy(name="Slimed Berserker", hp=201, max_hp=266)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=38,
            current_hp=80,
            max_hp=86,
            gold=140,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                RawSelectionCardPayload(
                    index=0,
                    card_id="defend",
                    name="Defend",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Gain 8 Block.",
                ),
                RawSelectionCardPayload(
                    index=1,
                    card_id="mayhem",
                    name="Mayhem",
                    card_type="Power",
                    energy_cost=2,
                    rules_text="At the start of your turn, play the top card of your Draw Pile.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    assert gs.state_type == "hand_select"
    assert "Retained cards are FREE" in prompt
    assert "Retain = keep for next turn" in prompt


def test_build_state_prompt_allows_optional_retain_even_when_confirm_is_available():
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=80, max_hp=86, block=9, energy=0),
            enemies=[make_enemy(name="Slimed Berserker", hp=174, max_hp=266)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=38,
            current_hp=80,
            max_hp=86,
            gold=140,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=True,
            cards=[
                make_selection_card(
                    "Serpent Form+",
                    0,
                    card_id="serpent_form",
                    card_type="Power",
                    energy_cost=3,
                    rules_text="Whenever you play a card, deal 5 damage to a random enemy.",
                ),
                make_selection_card(
                    "Survivor",
                    1,
                    card_id="survivor",
                    rules_text="Gain 11 Block. Discard 1 card.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    assert prompt
    assert "Retained cards are FREE" in prompt
    assert "Retain = keep for next turn" in prompt


def test_hand_select_retain_groups_harmful_cards_separately():
    """Retain mode places harmful cards under 'Do NOT retain' and good cards under 'Retain these'."""
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=70, max_hp=80, block=0, energy=2),
            enemies=[make_enemy(name="Cultist", hp=50, max_hp=50)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=10,
            current_hp=70,
            max_hp=80,
            gold=50,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose cards to [gold]Retain[/gold].[/center]",
            min_select=0,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Dagger Spray",
                    0,
                    card_id="dagger_spray",
                    card_type="Attack",
                    energy_cost=1,
                    rules_text="Deal 8 damage to ALL enemies twice. Lose 2 HP.",
                ),
                make_selection_card(
                    "Predator+",
                    1,
                    card_id="predator",
                    card_type="Attack",
                    energy_cost=2,
                    rules_text="Deal 21 damage. Next turn, draw 2 cards.",
                ),
                make_selection_card(
                    "Bouncing Flask",
                    2,
                    card_id="bouncing_flask",
                    card_type="Skill",
                    energy_cost=2,
                    rules_text="Apply 3 Poison to a random enemy 3 times.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    assert "Do NOT retain" in prompt
    assert "Retain these" in prompt

    # Dagger Spray is harmful -- must appear after "Do NOT retain" but before "Retain these"
    do_not_retain_pos = prompt.index("Do NOT retain")
    retain_these_pos = prompt.index("Retain these")
    dagger_spray_pos = prompt.index("Dagger Spray")
    predator_pos = prompt.index("Predator+")
    bouncing_flask_pos = prompt.index("Bouncing Flask")

    assert do_not_retain_pos < dagger_spray_pos < retain_these_pos
    assert predator_pos > retain_these_pos
    assert bouncing_flask_pos > retain_these_pos


def test_hand_select_retain_all_good_cards_in_keep_group():
    """Retain mode with no harmful cards shows only 'Retain these' group (not 'Do NOT retain')."""
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=60, max_hp=80, block=5, energy=1),
            enemies=[make_enemy(name="Cultist", hp=40, max_hp=50)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=5,
            current_hp=60,
            max_hp=80,
            gold=30,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose cards to Retain.[/center]",
            min_select=0,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Defend",
                    0,
                    card_id="defend",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Gain 8 Block.",
                ),
                make_selection_card(
                    "Leg Sweep",
                    1,
                    card_id="leg_sweep",
                    card_type="Skill",
                    energy_cost=2,
                    rules_text="Apply 6 Weak. Gain 11 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    assert "Do NOT retain —" not in prompt  # group header only absent when no harmful cards
    assert "Retain these" in prompt
    assert "Retain = keep for next turn" in prompt
    assert "FREE EXTRAS" in prompt


def test_hand_select_retain_shows_sly_end_of_turn_note():
    """Retain mode shows the end-of-turn Sly note but NOT the 'PRIORITY: Discard a Sly card' flag."""
    client = MagicMock()
    loop = make_loop(client)
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=75, max_hp=80, block=0, energy=2),
            enemies=[make_enemy(name="Cultist", hp=45, max_hp=50)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=12,
            current_hp=75,
            max_hp=80,
            gold=60,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose cards to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Haze+",
                    0,
                    card_id="haze",
                    card_type="Skill",
                    energy_cost=0,
                    rules_text="Sly. Apply 6 Poison to ALL enemies.",
                ),
                make_selection_card(
                    "Defend",
                    1,
                    card_id="defend",
                    card_type="Skill",
                    energy_cost=1,
                    rules_text="Gain 8 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    prompt = loop._build_state_prompt_v2(gs)

    # Retain mode shows generic Sly note, not the discard-priority flag
    assert "Discarding these by a card effect PLAYS them for free" in prompt
    assert "PRIORITY: Discard a Sly card" not in prompt


def test_handle_hand_select_confirms_optional_empty_selection():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection", "discard_potion"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=80, max_hp=86, block=9, energy=0),
            enemies=[make_enemy(name="Slimed Berserker", hp=201, max_hp=266)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=38,
            current_hp=80,
            max_hp=86,
            gold=140,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card("Defend", 0, card_id="defend", rules_text="Gain 8 Block."),
                make_selection_card(
                    "Mayhem",
                    1,
                    card_id="mayhem",
                    card_type="Power",
                    energy_cost=2,
                    rules_text="At the start of your turn, play the top card of your Draw Pile.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    result = asyncio.run(loop._handle_hand_select(gs))

    assert result is not None
    assert result.action == actions.confirm_selection()
    assert "without choosing a card" in result.reasoning
    loop._execute.assert_awaited_once_with(actions.confirm_selection(), delta_source="confirm")


def test_decide_and_act_mechanically_confirms_optional_hand_select_without_conversation():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._v2_engine = MagicMock()
    loop._use_llm = True
    loop._v2_combat_conversation = None
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=False,
        available_actions=["select_deck_card", "confirm_selection", "discard_potion"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=80, max_hp=86, block=9, energy=0),
            enemies=[make_enemy(name="Slimed Berserker", hp=201, max_hp=266)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=38,
            current_hp=80,
            max_hp=86,
            gold=140,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card("Defend", 0, card_id="defend", rules_text="Gain 8 Block."),
                make_selection_card(
                    "Mayhem",
                    1,
                    card_id="mayhem",
                    card_type="Power",
                    energy_cost=2,
                    rules_text="At the start of your turn, play the top card of your Draw Pile.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    result = asyncio.run(loop._decide_and_act(gs, step=1))

    assert result is not None
    assert result.action == actions.confirm_selection()
    loop._execute.assert_awaited_once_with(actions.confirm_selection(), delta_source="confirm")


def test_decide_and_act_falls_back_to_empty_confirm_when_optional_hand_select_llm_returns_none():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._v2_engine = MagicMock()
    loop._v2_engine.decide_noncombat = AsyncMock(return_value=None)
    loop._use_llm = True
    loop._v2_combat_conversation = MagicMock()
    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=False,
        available_actions=["select_deck_card", "confirm_selection", "discard_potion"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=80, max_hp=86, block=0, energy=0),
            enemies=[make_enemy(name="Slimed Berserker", hp=174, max_hp=266)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=38,
            current_hp=80,
            max_hp=86,
            gold=140,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose a card to Retain.[/center]",
            min_select=0,
            max_select=1,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=True,
            cards=[
                make_selection_card(
                    "Serpent Form+",
                    0,
                    card_id="serpent_form",
                    card_type="Power",
                    energy_cost=3,
                    rules_text="Whenever you play a card, deal 5 damage to a random enemy.",
                ),
                make_selection_card(
                    "Survivor",
                    1,
                    card_id="survivor",
                    rules_text="Gain 11 Block. Discard 1 card.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    result = asyncio.run(loop._decide_and_act(gs, step=24))

    assert result is not None
    assert result.action == actions.confirm_selection()
    assert loop._v2_engine.decide_noncombat.await_count == 1
    loop._execute.assert_awaited_once_with(actions.confirm_selection(), delta_source="confirm")


def test_decide_and_act_re_resolves_multi_discard_plan_by_name(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._last_played_card_name = "Prepared+"
    loop._last_played_plan_action = PlannedAction(
        action_type="card",
        card_name="Prepared+",
        discard=("Haze+", "Untouchable+"),
    )

    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=54, max_hp=89, block=0, energy=4),
            enemies=[make_enemy(name="Hunter Killer", hp=79, max_hp=79)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=31,
            current_hp=54,
            max_hp=89,
            gold=0,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose [blue]2[/blue] cards to [gold]Discard[/gold].[/center]",
            min_select=2,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Sucker Punch",
                    0,
                    card_id="sucker_punch",
                    card_type="Attack",
                    rules_text="Deal 8 damage. Apply 1 Weak.",
                ),
                make_selection_card(
                    "Haze+",
                    1,
                    card_id="haze",
                    upgraded=True,
                    energy_cost=3,
                    rules_text="Sly. Gain 13 Block.",
                ),
                make_selection_card(
                    "Toxic",
                    2,
                    card_id="toxic",
                    card_type="Status",
                    rules_text=(
                        "At the end of your turn, if this is in your Hand, "
                        "take 5 damage. Exhaust."
                    ),
                ),
                make_selection_card(
                    "Scrawl+",
                    3,
                    card_id="scrawl",
                    upgraded=True,
                    rules_text="Retain. Draw cards until your Hand is full. Exhaust.",
                ),
                make_selection_card(
                    "Untouchable+",
                    4,
                    card_id="untouchable",
                    upgraded=True,
                    energy_cost=2,
                    rules_text="Sly. Gain 15 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)
    fresh_after_first = GameState.from_upstream(
        UpstreamGameState(
            screen="CARD_SELECTION",
            in_combat=True,
            available_actions=["select_deck_card", "confirm_selection"],
            combat=raw.combat,
            run=raw.run,
            selection=RawSelectionPayload(
                kind="combat_hand_select",
                prompt=raw.selection.prompt,
                min_select=2,
                max_select=2,
                selected_count=1,
                requires_confirmation=True,
                can_confirm=False,
                cards=[
                    make_selection_card(
                        "Sucker Punch",
                        0,
                        card_id="sucker_punch",
                        card_type="Attack",
                        rules_text="Deal 8 damage. Apply 1 Weak.",
                    ),
                    make_selection_card(
                        "Defend",
                        1,
                        card_id="defend",
                        rules_text="Gain 8 Block.",
                    ),
                    make_selection_card(
                        "Untouchable+",
                        2,
                        card_id="untouchable",
                        upgraded=True,
                        energy_cost=2,
                        rules_text="Sly. Gain 15 Block.",
                    ),
                    make_selection_card(
                        "Toxic",
                        3,
                        card_id="toxic",
                        card_type="Status",
                        rules_text=(
                            "At the end of your turn, if this is in your Hand, "
                            "take 5 damage. Exhaust."
                        ),
                    ),
                ],
            ),
        )
    )
    fresh_ready = GameState.from_upstream(
        UpstreamGameState(
            screen="CARD_SELECTION",
            in_combat=True,
            available_actions=["confirm_selection"],
            combat=raw.combat,
            run=raw.run,
            selection=RawSelectionPayload(
                kind="combat_hand_select",
                prompt=raw.selection.prompt,
                min_select=2,
                max_select=2,
                selected_count=2,
                requires_confirmation=True,
                can_confirm=True,
                cards=[],
            ),
        )
    )
    loop._refresh_selection_state = AsyncMock(side_effect=[fresh_after_first, fresh_ready])

    result = asyncio.run(loop._decide_and_act(gs, step=261))

    assert result is not None
    assert result.source == "plan"
    assert "Haze+, Untouchable+" in result.reasoning
    assert loop._execute.await_args_list == [
        call(actions.select_deck_card(1), delta_source="Haze+"),
        call(actions.select_deck_card(2), delta_source="Untouchable+"),
        call(actions.confirm_selection(), delta_source="confirm"),
    ]
    assert loop._last_played_plan_action is None


def test_decide_and_act_skips_confirm_when_plan_discard_auto_processes(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    loop._last_played_card_name = "Prepared+"
    loop._last_played_plan_action = PlannedAction(
        action_type="card",
        card_name="Prepared+",
        discard=("Haze+", "Untouchable+"),
    )

    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=54, max_hp=89, block=0, energy=4),
            enemies=[make_enemy(name="Hunter Killer", hp=79, max_hp=79)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=31,
            current_hp=54,
            max_hp=89,
            gold=0,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose [blue]2[/blue] cards to [gold]Discard[/gold].[/center]",
            min_select=2,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Sucker Punch",
                    0,
                    card_id="sucker_punch",
                    card_type="Attack",
                    rules_text="Deal 8 damage. Apply 1 Weak.",
                ),
                make_selection_card(
                    "Haze+",
                    1,
                    card_id="haze",
                    upgraded=True,
                    energy_cost=3,
                    rules_text="Sly. Gain 13 Block.",
                ),
                make_selection_card(
                    "Toxic",
                    2,
                    card_id="toxic",
                    card_type="Status",
                    rules_text=(
                        "At the end of your turn, if this is in your Hand, "
                        "take 5 damage. Exhaust."
                    ),
                ),
                make_selection_card(
                    "Untouchable+",
                    4,
                    card_id="untouchable",
                    upgraded=True,
                    energy_cost=2,
                    rules_text="Sly. Gain 15 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)
    fresh_after_first = GameState.from_upstream(
        UpstreamGameState(
            screen="CARD_SELECTION",
            in_combat=True,
            available_actions=["select_deck_card"],
            combat=raw.combat,
            run=raw.run,
            selection=RawSelectionPayload(
                kind="combat_hand_select",
                prompt=raw.selection.prompt,
                min_select=2,
                max_select=2,
                selected_count=1,
                requires_confirmation=True,
                can_confirm=False,
                cards=[
                    make_selection_card(
                        "Sucker Punch",
                        0,
                        card_id="sucker_punch",
                        card_type="Attack",
                        rules_text="Deal 8 damage. Apply 1 Weak.",
                    ),
                    make_selection_card(
                        "Defend",
                        1,
                        card_id="defend",
                        rules_text="Gain 8 Block.",
                    ),
                    make_selection_card(
                        "Untouchable+",
                        2,
                        card_id="untouchable",
                        upgraded=True,
                        energy_cost=2,
                        rules_text="Sly. Gain 15 Block.",
                    ),
                ],
            ),
        )
    )
    loop._refresh_selection_state = AsyncMock(side_effect=[fresh_after_first, None])

    result = asyncio.run(loop._decide_and_act(gs, step=261))

    assert result is not None
    assert result.source == "plan"
    assert "Haze+, Untouchable+" in result.reasoning
    assert loop._execute.await_args_list == [
        call(actions.select_deck_card(1), delta_source="Haze+"),
        call(actions.select_deck_card(2), delta_source="Untouchable+"),
    ]
    assert loop._last_played_plan_action is None


def test_execute_llm_decision_re_resolves_batch_selection_by_name(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    raw = UpstreamGameState(
        screen="CARD_SELECTION",
        in_combat=True,
        available_actions=["select_deck_card", "confirm_selection"],
        combat=RawCombatPayload(
            player=RawCombatPlayerPayload(current_hp=54, max_hp=89, block=0, energy=3),
            enemies=[make_enemy(name="Hunter Killer", hp=79, max_hp=79)],
        ),
        run=RawRunPayload(
            character_id="silent",
            character_name="The Silent",
            floor=31,
            current_hp=54,
            max_hp=89,
            gold=0,
            max_energy=3,
            deck=[],
        ),
        selection=RawSelectionPayload(
            kind="combat_hand_select",
            prompt="[center]Choose [blue]2[/blue] cards to [gold]Discard[/gold].[/center]",
            min_select=2,
            max_select=2,
            selected_count=0,
            requires_confirmation=True,
            can_confirm=False,
            cards=[
                make_selection_card(
                    "Sucker Punch",
                    0,
                    card_id="sucker_punch",
                    card_type="Attack",
                    rules_text="Deal 8 damage. Apply 1 Weak.",
                ),
                make_selection_card(
                    "Haze+",
                    1,
                    card_id="haze",
                    upgraded=True,
                    energy_cost=3,
                    rules_text="Sly. Gain 13 Block.",
                ),
                make_selection_card(
                    "Toxic",
                    2,
                    card_id="toxic",
                    card_type="Status",
                    rules_text=(
                        "At the end of your turn, if this is in your Hand, "
                        "take 5 damage. Exhaust."
                    ),
                ),
                make_selection_card(
                    "Scrawl+",
                    3,
                    card_id="scrawl",
                    upgraded=True,
                    rules_text="Retain. Draw cards until your Hand is full. Exhaust.",
                ),
                make_selection_card(
                    "Untouchable+",
                    4,
                    card_id="untouchable",
                    upgraded=True,
                    energy_cost=2,
                    rules_text="Sly. Gain 15 Block.",
                ),
            ],
        ),
    )
    gs = GameState.from_upstream(raw)

    fresh_after_first = GameState.from_upstream(
        UpstreamGameState(
            screen="CARD_SELECTION",
            in_combat=True,
            available_actions=["select_deck_card", "confirm_selection"],
            combat=raw.combat,
            run=raw.run,
            selection=RawSelectionPayload(
                kind="combat_hand_select",
                prompt=raw.selection.prompt,
                min_select=2,
                max_select=2,
                selected_count=1,
                requires_confirmation=True,
                can_confirm=False,
                cards=[
                    make_selection_card(
                        "Sucker Punch",
                        0,
                        card_id="sucker_punch",
                        card_type="Attack",
                        rules_text="Deal 8 damage. Apply 1 Weak.",
                    ),
                    make_selection_card(
                        "Defend",
                        1,
                        card_id="defend",
                        rules_text="Gain 8 Block.",
                    ),
                    make_selection_card(
                        "Untouchable+",
                        2,
                        card_id="untouchable",
                        upgraded=True,
                        energy_cost=2,
                        rules_text="Sly. Gain 15 Block.",
                    ),
                    make_selection_card(
                        "Toxic",
                        3,
                        card_id="toxic",
                        card_type="Status",
                        rules_text=(
                            "At the end of your turn, if this is in your Hand, "
                            "take 5 damage. Exhaust."
                        ),
                    ),
                ],
            ),
        )
    )
    fresh_ready = GameState.from_upstream(
        UpstreamGameState(
            screen="CARD_SELECTION",
            in_combat=True,
            available_actions=["confirm_selection"],
            combat=raw.combat,
            run=raw.run,
            selection=RawSelectionPayload(
                kind="combat_hand_select",
                prompt=raw.selection.prompt,
                min_select=2,
                max_select=2,
                selected_count=2,
                requires_confirmation=True,
                can_confirm=True,
                cards=[],
            ),
        )
    )
    loop._refresh_selection_state = AsyncMock(side_effect=[fresh_after_first, fresh_ready])

    llm_dec = LLMDecision(
        action_name="select_deck_card",
        params={"selected_indices": [1, 4], "option_index": 1},
        reasoning="Discard Haze+ and Untouchable+",
    )

    result, err = asyncio.run(
        loop._execute_llm_decision(
            gs,
            llm_dec,
            loop_module.DecisionSource.LLM,
        )
    )

    assert err is None
    assert result is not None
    assert loop._execute.await_args_list == [
        call(actions.select_deck_card(1), delta_source="Haze+", delta_target=None),
        call(actions.select_deck_card(2), delta_source="Untouchable+"),
        call(actions.confirm_selection(), delta_source="confirm"),
    ]


def test_execute_llm_decision_batch_card_select_tracks_progress_when_indices_reuse(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    gs = make_card_select_gs(
        can_confirm=False,
        selected_count=0,
        max_select=4,
        prompt="Choose 4 cards to Remove.",
        kind="deck_card_select",
        cards=[
            make_selection_card("Strike", 0, card_id="strike_0", card_type="Attack"),
            make_selection_card("Strike", 1, card_id="strike_1", card_type="Attack"),
            make_selection_card("Strike", 2, card_id="strike_2", card_type="Attack"),
            make_selection_card("Strike", 3, card_id="strike_3", card_type="Attack"),
            make_selection_card("Defend", 4, card_id="defend_0"),
        ],
    )

    refresh_states = [
        make_card_select_gs(
            can_confirm=False,
            selected_count=1,
            max_select=4,
            prompt="Choose 4 cards to Remove.",
            kind="deck_card_select",
            cards=[
                make_selection_card("Strike", 0, card_id="strike_1", card_type="Attack"),
                make_selection_card("Strike", 1, card_id="strike_2", card_type="Attack"),
                make_selection_card("Strike", 2, card_id="strike_3", card_type="Attack"),
                make_selection_card("Defend", 3, card_id="defend_0"),
            ],
        ),
        make_card_select_gs(
            can_confirm=False,
            selected_count=2,
            max_select=4,
            prompt="Choose 4 cards to Remove.",
            kind="deck_card_select",
            cards=[
                make_selection_card("Strike", 0, card_id="strike_2", card_type="Attack"),
                make_selection_card("Strike", 1, card_id="strike_3", card_type="Attack"),
                make_selection_card("Defend", 2, card_id="defend_0"),
            ],
        ),
        make_card_select_gs(
            can_confirm=False,
            selected_count=3,
            max_select=4,
            prompt="Choose 4 cards to Remove.",
            kind="deck_card_select",
            cards=[
                make_selection_card("Strike", 0, card_id="strike_3", card_type="Attack"),
                make_selection_card("Defend", 1, card_id="defend_0"),
            ],
        ),
        make_card_select_gs(
            available_actions=["confirm_selection"],
            can_confirm=True,
            selected_count=4,
            max_select=4,
            prompt="Choose 4 cards to Remove.",
            kind="deck_card_select",
            cards=[],
        ),
    ]
    loop._refresh_selection_state = AsyncMock(side_effect=refresh_states)

    llm_dec = LLMDecision(
        action_name="select_deck_card",
        params={"selected_indices": [0, 1, 2, 3], "option_index": 0},
        reasoning="Remove all Strikes.",
    )

    result, err = asyncio.run(
        loop._execute_llm_decision(
            gs,
            llm_dec,
            loop_module.DecisionSource.LLM,
        )
    )

    assert err is None
    assert result is not None
    assert loop._execute.await_args_list == [
        call(actions.select_deck_card(0), delta_source="Strike", delta_target=None),
        call(actions.select_deck_card(0), delta_source="Strike"),
        call(actions.select_deck_card(0), delta_source="Strike"),
        call(actions.select_deck_card(0), delta_source="Strike"),
        call(actions.confirm_selection(), delta_source="confirm"),
    ]
    assert loop._card_select_progress == 0
    assert loop._card_select_selected == set()


def test_execute_llm_decision_batch_card_select_uses_stable_selected_and_selectable_payloads(
    monkeypatch,
):
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    monkeypatch.setattr(loop_module.asyncio, "sleep", _instant_sleep)

    initial_cards = [
        make_selection_card("Strike", 0, stable_id="strike-a", card_id="strike", card_type="Attack"),
        make_selection_card("Strike", 1, stable_id="strike-b", card_id="strike", card_type="Attack"),
        make_selection_card("Strike", 2, stable_id="strike-c", card_id="strike", card_type="Attack"),
    ]
    gs = make_card_select_gs(
        can_confirm=False,
        selected_count=0,
        max_select=2,
        prompt="Choose 2 cards to Remove.",
        kind="deck_card_select",
        cards=initial_cards,
        selectable_cards=initial_cards,
        selected_cards=[],
    )

    refresh_states = [
        make_card_select_gs(
            can_confirm=False,
            selected_count=1,
            max_select=2,
            prompt="Choose 2 cards to Remove.",
            kind="deck_card_select",
            cards=[
                make_selection_card(
                    "Strike", 0, stable_id="strike-b", card_id="strike", card_type="Attack"
                ),
                make_selection_card(
                    "Strike", 1, stable_id="strike-c", card_id="strike", card_type="Attack"
                ),
            ],
            selectable_cards=[
                make_selection_card(
                    "Strike", 0, stable_id="strike-b", card_id="strike", card_type="Attack"
                ),
                make_selection_card(
                    "Strike", 1, stable_id="strike-c", card_id="strike", card_type="Attack"
                ),
            ],
            selected_cards=[
                make_selection_card(
                    "Strike",
                    0,
                    stable_id="strike-a",
                    card_id="strike",
                    card_type="Attack",
                    is_selected=True,
                    is_selectable=False,
                ),
            ],
        ),
        make_card_select_gs(
            available_actions=["confirm_selection"],
            can_confirm=True,
            selected_count=2,
            max_select=2,
            prompt="Choose 2 cards to Remove.",
            kind="deck_card_select",
            cards=[],
            selectable_cards=[],
            selected_cards=[
                make_selection_card(
                    "Strike",
                    0,
                    stable_id="strike-a",
                    card_id="strike",
                    card_type="Attack",
                    is_selected=True,
                    is_selectable=False,
                ),
                make_selection_card(
                    "Strike",
                    1,
                    stable_id="strike-b",
                    card_id="strike",
                    card_type="Attack",
                    is_selected=True,
                    is_selectable=False,
                ),
            ],
        ),
    ]
    loop._refresh_selection_state = AsyncMock(side_effect=refresh_states)

    llm_dec = LLMDecision(
        action_name="select_deck_card",
        params={"selected_indices": [0, 1], "option_index": 0},
        reasoning="Remove the first two Strikes.",
    )

    result, err = asyncio.run(
        loop._execute_llm_decision(
            gs,
            llm_dec,
            loop_module.DecisionSource.LLM,
        )
    )

    assert err is None
    assert result is not None
    assert loop._execute.await_args_list == [
        call(actions.select_deck_card(0), delta_source="Strike", delta_target=None),
        call(actions.select_deck_card(0), delta_source="Strike"),
        call(actions.confirm_selection(), delta_source="confirm"),
    ]


def test_validate_llm_decision_only_blocks_repeat_index_for_stable_selection():
    client = MagicMock()
    loop = make_loop(client)
    loop._card_select_selected = {0}

    hand_gs = GameState(raw=make_card_select_gs(kind="combat_hand_select").raw, state_type="hand_select")
    hand_err = loop._validate_llm_decision(
        hand_gs,
        LLMDecision(
            action_name="select_deck_card",
            params={"option_index": 0},
            reasoning="Pick the first card.",
        ),
    )
    assert hand_err is not None
    assert "DESELECT" in hand_err

    card_gs = make_card_select_gs(kind="deck_card_select")
    card_err = loop._validate_llm_decision(
        card_gs,
        LLMDecision(
            action_name="select_deck_card",
            params={"option_index": 0},
            reasoning="Pick the first card.",
        ),
    )
    assert card_err is None


def test_validate_llm_decision_uses_selectable_cards_when_selected_cards_remain_visible():
    client = MagicMock()
    loop = make_loop(client)

    selected = make_selection_card(
        "Defend",
        0,
        stable_id="defend-picked",
        card_id="defend",
        is_selected=True,
        is_selectable=False,
    )
    remaining = make_selection_card(
        "Strike",
        1,
        stable_id="strike-open",
        card_id="strike",
    )
    gs = GameState(
        raw=make_card_select_gs(
            kind="combat_hand_select",
            cards=[selected, remaining],
            selected_cards=[selected],
            selectable_cards=[remaining],
        ).raw,
        state_type="hand_select",
    )

    err = loop._validate_llm_decision(
        gs,
        LLMDecision(
            action_name="select_deck_card",
            params={"option_index": 0},
            reasoning="Pick the selected card again.",
        ),
    )

    assert err is not None
    assert "valid: [1]" in err


def _make_crystal_sphere_gs(
    *,
    is_finished: bool = False,
    can_proceed: bool = False,
    can_use_big_tool: bool = True,
    can_use_small_tool: bool = True,
    tool: str = "none",
    clickable: list[tuple[int, int]] | None = None,
    revealed: list[dict] | None = None,
):
    from src.mcp_client.upstream_models import (
        RawCrystalSphereCellPayload,
        RawCrystalSphereCellRefPayload,
        RawCrystalSphereRevealedItemPayload,
        RawCrystalSpherePayload,
    )

    clickable = clickable or []
    revealed = revealed or []

    grid_w = 4
    grid_h = 4
    cells: list[RawCrystalSphereCellPayload] = []
    clickable_set = set(clickable)
    for y in range(grid_h):
        for x in range(grid_w):
            is_clk = (x, y) in clickable_set
            cells.append(
                RawCrystalSphereCellPayload(
                    x=x, y=y, is_hidden=is_clk, is_clickable=is_clk
                )
            )

    cs = RawCrystalSpherePayload(
        grid_width=grid_w,
        grid_height=grid_h,
        tool=tool,
        can_use_big_tool=can_use_big_tool,
        can_use_small_tool=can_use_small_tool,
        divinations_left=2,
        divinations_left_text="2 Divinations remain",
        can_proceed=can_proceed,
        is_finished=is_finished,
        cells=cells,
        clickable_cells=[
            RawCrystalSphereCellRefPayload(x=x, y=y) for (x, y) in clickable
        ],
        revealed_items=[
            RawCrystalSphereRevealedItemPayload(
                x=item["x"],
                y=item["y"],
                item_type=item.get("item_type", "Reward"),
                is_good=item.get("is_good", True),
            )
            for item in revealed
        ],
    )

    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=22,
        current_hp=42,
        max_hp=70,
        gold=160,
        max_energy=3,
        deck=[
            RawDeckCardPayload(
                index=0,
                card_id="strike",
                name="Strike",
                card_type="Attack",
                energy_cost=1,
                rarity="Starter",
                rules_text="Deal 6 damage.",
            ),
        ],
    )
    avail: list[str] = []
    if can_proceed:
        avail.append("crystal_sphere_proceed")
    if can_use_big_tool or can_use_small_tool:
        avail.append("crystal_sphere_set_tool")
    if clickable:
        avail.append("crystal_sphere_click_cell")
    raw = UpstreamGameState(
        screen="EVENT",
        available_actions=avail,
        run=run,
        crystal_sphere=cs,
    )
    return GameState.from_upstream(raw)


def test_crystal_sphere_state_type_derived_from_payload():
    gs = _make_crystal_sphere_gs()
    assert gs.state_type == "crystal_sphere"
    assert gs.crystal_sphere is not None
    assert gs.event is None


def test_crystal_sphere_finished_auto_proceeds_without_llm():
    client = MagicMock()
    loop = make_loop(client)
    loop._execute = AsyncMock(return_value={"stable": True})
    gs = _make_crystal_sphere_gs(
        is_finished=True,
        can_proceed=True,
        can_use_big_tool=False,
        can_use_small_tool=False,
        clickable=[],
    )

    result = asyncio.run(loop._decide_and_act(gs, step=1))

    assert result is not None
    assert result.source == "auto"
    assert result.action == actions.crystal_sphere_proceed()
    loop._execute.assert_awaited_once_with(actions.crystal_sphere_proceed())


def test_crystal_sphere_prompt_renders_grid_and_revealed_items():
    from src.brain.prompts.crystal_sphere import build_crystal_sphere_prompt

    gs = _make_crystal_sphere_gs(
        tool="big",
        can_use_big_tool=False,
        clickable=[(0, 0), (1, 1)],
        revealed=[{"x": 2, "y": 2, "item_type": "Curse", "is_good": False}],
    )
    text = build_crystal_sphere_prompt(gs)
    assert "Crystal Sphere" in text
    assert "Active tool: **big**" in text
    assert "(2,2) Curse" in text
    assert "harmful" in text
    assert "(0,0)" in text and "(1,1)" in text  # clickable list
    assert "crystal_sphere_set_tool" in text
    assert "crystal_sphere_click_cell" in text
    assert "crystal_sphere_proceed" in text


# ── _parse_select_count_from_prompt ──


def test_parse_select_count_any_number():
    """'Choose any number of cards to replace' should return 0 (defer to max_select)."""
    assert AgentLoop._parse_select_count_from_prompt("Choose any number of cards to replace.") == 0


def test_parse_select_count_numeric():
    """'Choose 2 cards to Remove' should return 2."""
    assert AgentLoop._parse_select_count_from_prompt("Choose 2 cards to Remove") == 2


def test_parse_select_count_bbcode():
    """'Choose [blue]3[/blue] Common cards' should return 3."""
    assert AgentLoop._parse_select_count_from_prompt("Choose [blue]3[/blue] Common cards to Remove") == 3


def test_parse_select_count_a_card():
    """'Choose a card to Upgrade' should return 1."""
    assert AgentLoop._parse_select_count_from_prompt("Choose a card to Upgrade") == 1


def test_parse_select_count_unknown():
    """Unrecognized prompt should return 0 (defer to max_select), not 1."""
    assert AgentLoop._parse_select_count_from_prompt("Pick something") == 0
