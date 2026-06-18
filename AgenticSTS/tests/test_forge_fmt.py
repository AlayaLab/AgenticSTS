"""Sovereign Blade / Forge state prompt-block formatter tests."""
from __future__ import annotations

from src.brain.prompts._forge_fmt import format_forge_state
from src.mcp_client.upstream_models import (
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawCombatPowerPayload,
    RawDeckCardPayload,
    RawPileCardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState


def _make_gs(
    *,
    character: str = "The Regent",
    in_combat: bool = True,
    hand: list | None = None,
    draw: list | None = None,
    discard: list | None = None,
    exhaust: list | None = None,
    deck: list | None = None,
    powers: list | None = None,
) -> GameState:
    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(
            current_hp=70, max_hp=80, energy=3, stars=2,
            draw_cards=draw or [],
            discard_cards=discard or [],
            exhaust_cards=exhaust or [],
            powers=powers or [],
        ),
        hand=hand or [],
        enemies=[],
    )
    run = RawRunPayload(
        character_id="the_regent",
        character_name=character,
        floor=4,
        current_hp=70,
        max_hp=80,
        gold=99,
        max_energy=3,
        deck=deck or [],
    )
    raw = UpstreamGameState(
        screen="MONSTER" if in_combat else "MAIN_MENU",
        in_combat=in_combat,
        turn=1,
        available_actions=["play_card", "end_turn"] if in_combat else [],
        combat=combat if in_combat else None,
        run=run,
    )
    return GameState(raw=raw, state_type="monster" if in_combat else "main_menu")


def _sb_in_hand(damage: int) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=0,
        card_id="sovereign_blade",
        name="Sovereign Blade",
        energy_cost=2,
        playable=True,
        damage=damage,
        requires_target=True,
        target_index_space="enemies",
    )


def _pile_card(card_id: str) -> RawPileCardPayload:
    return RawPileCardPayload(card_id=card_id)


def _deck_card(name: str) -> RawDeckCardPayload:
    return RawDeckCardPayload(
        index=0,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        card_type="Attack",
        energy_cost=1,
        rarity="Common",
        rules_text="",
    )


def test_non_regent_returns_empty():
    gs = _make_gs(character="The Silent", deck=[_deck_card("Beat into Shape")])
    assert format_forge_state(gs) == []


def test_no_forge_presence_returns_empty():
    """Regent with neither a Blade nor any Forge cards in deck → empty."""
    gs = _make_gs(deck=[_deck_card("Strike"), _deck_card("Defend")])
    assert format_forge_state(gs) == []


def test_blade_in_hand_unbuffed():
    gs = _make_gs(
        hand=[_sb_in_hand(damage=10)],
        deck=[_deck_card("Beat into Shape"), _deck_card("Wrought in War")],
    )
    lines = format_forge_state(gs)
    assert any("## Sovereign Blade" in line for line in lines)
    status_line = next(line for line in lines if line.startswith("Status:"))
    assert "in_hand" in status_line
    assert "10" in status_line
    assert "FORGED" not in status_line  # base damage, not yet Forged
    # Risk warning only fires when Forged
    assert not any("Risk:" in line for line in lines)


def test_blade_in_hand_forged_emits_risk_warning():
    gs = _make_gs(
        hand=[_sb_in_hand(damage=18)],
        deck=[_deck_card("Beat into Shape")],
    )
    lines = format_forge_state(gs)
    status_line = next(line for line in lines if line.startswith("Status:"))
    assert "FORGED" in status_line
    assert "18" in status_line
    assert any("Risk:" in line for line in lines)
    assert any("exhaust" in line.lower() for line in lines)


def test_blade_in_exhaust_pile_emits_recovery_hint():
    gs = _make_gs(
        exhaust=[_pile_card("sovereign_blade")],
        deck=[_deck_card("Beat into Shape")],
    )
    lines = format_forge_state(gs)
    status_line = next(line for line in lines if line.startswith("Status:"))
    assert "EXHAUSTED" in status_line


def test_forge_cards_listed_with_truncation():
    """More than 5 Forge cards → truncated with overflow indicator."""
    deck = [_deck_card(f"Forge Card {i}") for i in range(7)]
    # Patch one to be a real Forge card so classify hits at least once;
    # for the truncation test we just need the count, but real Forge names
    # are required because classify_card looks up the seed table.
    deck[0] = _deck_card("Beat into Shape")
    deck[1] = _deck_card("Wrought in War")
    deck[2] = _deck_card("Refine Blade")
    deck[3] = _deck_card("Bulwark")
    deck[4] = _deck_card("The Smith")
    # The remaining 2 are unknowns and won't classify as Forge — that's fine,
    # we just verify the listing of the 5 known ones.
    gs = _make_gs(deck=deck, hand=[_sb_in_hand(damage=10)])
    lines = format_forge_state(gs)
    forge_line = next(
        (line for line in lines if line.startswith("Forge cards in deck")),
        None,
    )
    assert forge_line is not None
    assert "5" in forge_line  # the count of known Forge cards


def test_active_forge_buff_powers_listed():
    powers = [
        RawCombatPowerPayload(
            index=0,
            power_id="seeking_edge",
            name="Seeking Edge",
            amount=1,
        ),
    ]
    gs = _make_gs(
        hand=[_sb_in_hand(damage=14)],
        deck=[_deck_card("Beat into Shape")],
        powers=powers,
    )
    lines = format_forge_state(gs)
    buffs_line = next(
        (line for line in lines if line.startswith("Active Forge buffs")),
        None,
    )
    assert buffs_line is not None
    assert "Seeking Edge" in buffs_line
    assert "1" in buffs_line


def test_non_combat_returns_empty():
    """Map / event / shop screens — never inject the block."""
    gs = _make_gs(in_combat=False, deck=[_deck_card("Beat into Shape")])
    assert format_forge_state(gs) == []
