"""Shared test fixtures and factory helpers.

Convention: public helpers use ``make_*`` (no underscore prefix).
pytest auto-discovers this file; no explicit imports needed for fixtures.
Plain helper functions must be imported explicitly::

    from tests.conftest import make_enemy, make_hand_card, make_combat_gs
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from src.agent.loop import AgentLoop
from src.mcp_client.upstream_models import (
    RawCardsViewPayload,
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawEventOptionPayload,
    RawEventPayload,
    RawRunPayload,
    RawRunPotionPayload,
    RawSelectionCardPayload,
    RawSelectionPayload,
    RawShopPayload,
    RawShopRelicPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState


# ── Enemy / card builders ──────────────────────────────────────────

def make_enemy(
    name: str = "Test Louse",
    index: int = 0,
    hp: int = 30,
    max_hp: int = 30,
) -> RawCombatEnemyPayload:
    return RawCombatEnemyPayload(
        index=index,
        enemy_id=name.lower().replace(" ", "_"),
        name=name,
        current_hp=hp,
        max_hp=max_hp,
        block=0,
        is_alive=True,
    )


def make_hand_card(
    name: str,
    index: int,
    *,
    playable: bool,
    energy_cost: int = 1,
    requires_target: bool = True,
    rules_text: str = "Test card.",
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        playable=playable,
        damage=6 if requires_target else None,
        rules_text=rules_text,
        requires_target=requires_target,
        target_index_space="enemies" if requires_target else None,
    )


def make_selection_card(
    name: str,
    index: int,
    *,
    stable_id: str | None = None,
    card_id: str | None = None,
    upgraded: bool = False,
    card_type: str = "Skill",
    energy_cost: int = 1,
    rules_text: str = "Test card.",
    is_selected: bool = False,
    is_selectable: bool = True,
) -> RawSelectionCardPayload:
    return RawSelectionCardPayload(
        index=index,
        stable_id=stable_id or f"{card_id or name.lower().replace(' ', '_').replace('+', 'plus')}::{index}",
        card_id=card_id or name.lower().replace(" ", "_").replace("+", "plus"),
        name=name,
        upgraded=upgraded,
        card_type=card_type,
        energy_cost=energy_cost,
        rules_text=rules_text,
        is_selected=is_selected,
        is_selectable=is_selectable,
    )


# ── GameState builders ─────────────────────────────────────────────

def make_combat_gs(
    hand: list[RawCombatHandCardPayload],
    *,
    available_actions: list[str] | None = None,
    potions: list[RawRunPotionPayload] | None = None,
    turn: int = 1,
    energy: int = 3,
) -> GameState:
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(current_hp=60, max_hp=80, energy=energy),
        hand=hand,
        enemies=[make_enemy()],
    )
    run = RawRunPayload(
        character_id="ironclad",
        character_name="Ironclad",
        floor=6,
        current_hp=60,
        max_hp=80,
        gold=99,
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
        potions=potions or [],
    )
    raw = UpstreamGameState(
        screen="MONSTER",
        in_combat=True,
        turn=turn,
        available_actions=available_actions or ["play_card", "end_turn"],
        combat=combat,
        run=run,
    )
    return GameState(raw=raw, state_type="monster")


def make_card_select_gs(
    *,
    available_actions: list[str] | None = None,
    can_confirm: bool = False,
    selected_count: int = 0,
    max_select: int = 1,
    prompt: str = "Choose a card.",
    cards: list[RawSelectionCardPayload] | None = None,
    selected_cards: list[RawSelectionCardPayload] | None = None,
    selectable_cards: list[RawSelectionCardPayload] | None = None,
    preview_cards: list[RawSelectionCardPayload] | None = None,
    kind: str = "card",
) -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=12,
        current_hp=52,
        max_hp=67,
        gold=99,
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
    selection_kwargs = dict(
        kind=kind,
        prompt=prompt,
        min_select=1,
        max_select=max_select,
        selected_count=selected_count,
        requires_confirmation=True,
        can_confirm=can_confirm,
        cards=cards
        or [
            RawSelectionCardPayload(
                index=0,
                card_id="slice",
                name="Slice",
                card_type="Attack",
                rarity="Common",
            ),
        ],
        preview_cards=preview_cards or [],
    )
    if selected_cards is not None:
        selection_kwargs["selected_cards"] = selected_cards
    if selectable_cards is not None:
        selection_kwargs["selectable_cards"] = selectable_cards

    raw = UpstreamGameState(
        screen="CARD_SELECT",
        available_actions=available_actions or ["select_deck_card", "confirm_selection"],
        run=run,
        selection=RawSelectionPayload(**selection_kwargs),
    )
    return GameState(raw=raw, state_type="card_select")


def make_cards_view_gs(
    *,
    title: str = "Cards View",
    cards: list[RawSelectionCardPayload] | None = None,
    available_actions: list[str] | None = None,
) -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=12,
        current_hp=52,
        max_hp=67,
        gold=99,
        max_energy=3,
    )
    raw = UpstreamGameState(
        screen="CARDS_VIEW",
        available_actions=available_actions or ["close_cards_view"],
        run=run,
        cards_view=RawCardsViewPayload(
            title=title,
            cards=cards or [make_selection_card("Backflip", 0)],
        ),
    )
    return GameState(raw=raw, state_type="cards_view")


def make_event_gs(
    options: list[RawEventOptionPayload],
    *,
    event_id: str = "CRYSTAL_SPHERE",
) -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=22,
        current_hp=7,
        max_hp=70,
        gold=480,
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
    raw = UpstreamGameState(
        screen="EVENT",
        available_actions=["choose_event_option"],
        run=run,
        event=RawEventPayload(
            event_id=event_id,
            title="Crystal Sphere",
            description="Test event.",
            is_finished=False,
            options=options,
        ),
    )
    return GameState(raw=raw, state_type="event")


def make_potion_discard_gs(
    *,
    available_actions: list[str] | None = None,
    state_type: str = "card_select",
    potions: list[RawRunPotionPayload] | None = None,
) -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=17,
        current_hp=18,
        max_hp=70,
        gold=136,
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
        potions=potions or [],
    )
    raw = UpstreamGameState(
        screen="CARD_SELECT",
        available_actions=available_actions or ["discard_potion"],
        run=run,
    )
    return GameState(raw=raw, state_type=state_type)


def make_shop_gs(
    *,
    relic_name: str = "Orrery",
    relic_index: int = 0,
    available_actions: list[str] | None = None,
    is_open: bool = True,
    potions: list[RawRunPotionPayload] | None = None,
) -> GameState:
    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=11,
        current_hp=54,
        max_hp=77,
        gold=344,
        max_energy=3,
        deck=[],
        potions=potions or [],
    )
    raw = UpstreamGameState(
        screen="SHOP",
        available_actions=available_actions or (
            ["buy_relic", "close_shop_inventory"] if is_open else ["open_shop_inventory"]
        ),
        run=run,
        shop=RawShopPayload(
            is_open=is_open,
            can_open=not is_open,
            can_close=is_open,
            relics=[
                RawShopRelicPayload(
                    index=relic_index,
                    relic_id=relic_name.lower().replace(" ", "_"),
                    name=relic_name,
                    description="Test relic.",
                    rarity="Shop",
                    price=160,
                    is_stocked=True,
                    enough_gold=True,
                )
            ],
        ),
    )
    return GameState.from_upstream(raw)


# ── AgentLoop helpers ──────────────────────────────────────────────

def make_loop(client: MagicMock) -> AgentLoop:
    with (
        patch.object(AgentLoop, "_init_knowledge", return_value=None),
        patch.object(AgentLoop, "_init_web_searcher", return_value=None),
        patch.object(AgentLoop, "_load_counter", return_value=0),
        patch.object(AgentLoop, "_init_skill_library", return_value=None),
        patch.object(AgentLoop, "_init_v2", return_value=None),
    ):
        return AgentLoop(client=client, use_llm=False)


async def instant_sleep(_delay: float) -> None:
    return None
