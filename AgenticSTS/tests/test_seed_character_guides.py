from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.agent.loop import AgentLoop
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.skills.library import SkillLibrary
from src.state.game_state import GameState


def _make_silent_state(state_type: str) -> GameState:
    deck = [
        RawDeckCardPayload(
            index=0,
            card_id="strike",
            name="Strike",
            card_type="Attack",
            energy_cost=1,
            rarity="Starter",
            rules_text="Deal 6 damage.",
        ),
        RawDeckCardPayload(
            index=1,
            card_id="defend",
            name="Defend",
            card_type="Skill",
            energy_cost=1,
            rarity="Starter",
            rules_text="Gain 5 Block.",
        ),
    ]
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=8,
        current_hp=52,
        max_hp=70,
        gold=160,
        max_energy=3,
        deck=deck,
    )

    if state_type in {"monster", "elite", "boss"}:
        raw = UpstreamGameState(
            screen=state_type.upper(),
            in_combat=True,
            available_actions=["play_card", "end_turn"],
            run=run,
            combat=RawCombatPayload(
                player=RawCombatPlayerPayload(current_hp=52, max_hp=70, energy=3),
                hand=[
                    RawCombatHandCardPayload(
                        index=0,
                        card_id="backstab",
                        name="Backstab",
                        energy_cost=0,
                        playable=True,
                        damage=11,
                        rules_text="Innate. Deal 11 damage. Exhaust.",
                        requires_target=True,
                        target_index_space="enemies",
                    )
                ],
                enemies=[
                    RawCombatEnemyPayload(
                        index=0,
                        enemy_id="jaw_worm",
                        name="Jaw Worm",
                        current_hp=40,
                        max_hp=40,
                        block=0,
                        is_alive=True,
                    )
                ],
            ),
        )
    else:
        raw = UpstreamGameState(
            screen=state_type.upper(),
            available_actions=["choose_option"],
            run=run,
        )

    return GameState(raw=raw, state_type=state_type)


def _make_loop(skill_library: SkillLibrary) -> AgentLoop:
    with (
        patch.object(AgentLoop, "_init_knowledge", return_value=None),
        patch.object(AgentLoop, "_init_web_searcher", return_value=None),
        patch.object(AgentLoop, "_load_counter", return_value=0),
        patch.object(AgentLoop, "_init_skill_library", return_value=None),
        patch.object(AgentLoop, "_init_v2", return_value=None),
    ):
        loop = AgentLoop(client=MagicMock(), use_llm=False)
    loop._skill_library = skill_library
    return loop


@pytest.mark.parametrize(
    ("state_type", "expected_name"),
    [
        ("map", "Silent - Route Priorities"),
        ("card_reward", "Silent - Draft and Shop Rules"),
        ("shop", "Silent - Draft and Shop Rules"),
        ("monster", "Silent - Combat Sequencing"),
        ("rest_site", "Rest Site and Event Decisions"),
        ("boss", "Boss and Elite Fight Strategy"),
    ],
)
def test_silent_seed_guides_auto_inject_for_matching_states(
    state_type: str,
    expected_name: str,
) -> None:
    lib = SkillLibrary.load_seeds(Path("src/skills/seeds"))
    loop = _make_loop(lib)

    text, ids = loop._query_skills(_make_silent_state(state_type))

    assert ids
    assert expected_name in text
