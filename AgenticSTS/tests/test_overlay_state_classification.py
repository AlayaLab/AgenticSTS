"""Regression tests for stray-UI-overlay state classification.

Bug context (2026-05-01):
    When the human supervisor opens a UI overlay mid-combat (TopBar deck
    button, TopBar map button, card/relic inspect zoom, pause menu) the mod
    keeps the underlying screen field as e.g. "MAP" or "COMBAT" but exposes
    only an overlay-escape action in `available_actions`.

    The previous `derive_state_type` looked only at `screen`, so it
    returned "map" for a mid-combat NMapScreen-IsOpen overlay.  That tripped
    `GameStateMachine` into firing a false `COMBAT_END` (because "map" is
    not in `COMBAT_ADJACENT_PHASES`), which recorded a bogus Victory based
    on `player_hp > 0`, polluted skill confidence and L4 combat memory,
    discarded the multi-turn `_v2_combat_conversation`, and on the next
    tick told the LLM to pick a map node — the validator then rejected the
    output and aborted the run.

    The fix in `01125ad` (auto-close grace) only short-circuits LLM
    dispatch in `_decide_and_act`.  By the time that runs, `state_machine`
    has already fired COMBAT_END.  The proper fix is to short-circuit at
    `derive_state_type` so the false transition never fires in the first
    place.
"""

from __future__ import annotations

from src.agent.state_machine import GameStateMachine, PhaseTransition
from src.mcp_client.upstream_models import RawRunPayload, UpstreamGameState
from src.state.game_state import GameState
from src.state.upstream_game_state import (
    COMBAT_ADJACENT_PHASES,
    derive_state_type,
)


def _make_run() -> RawRunPayload:
    return RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=8,
        current_hp=4,
        max_hp=70,
        gold=120,
        max_energy=3,
    )


def _make_state(
    *,
    screen: str,
    available_actions: list[str],
    combat_type: str = "",
) -> GameState:
    raw = UpstreamGameState(
        screen=screen,
        available_actions=available_actions,
        run=_make_run(),
        combat_type=combat_type,
    )
    return GameState.from_upstream(raw)


# ── derive_state_type ─────────────────────────────────────────


def test_capstone_overlay_only_classifies_as_overlay():
    """avail=[close_capstone_overlay] → state_type="capstone_overlay"."""
    raw = UpstreamGameState(
        screen="MAP",  # NMapScreen.IsOpen mid-combat reads as MAP
        available_actions=["close_capstone_overlay"],
        run=_make_run(),
    )
    assert derive_state_type(raw) == "capstone_overlay"


def test_pause_menu_only_classifies_as_overlay():
    """avail=[close_pause_menu] → state_type="capstone_overlay"."""
    raw = UpstreamGameState(
        screen="COMBAT",
        available_actions=["close_pause_menu"],
        run=_make_run(),
    )
    assert derive_state_type(raw) == "capstone_overlay"


def test_overlay_with_save_and_quit_still_classifies_as_overlay():
    """save_and_quit is always present; should not break overlay detection."""
    raw = UpstreamGameState(
        screen="MAP",
        available_actions=["close_capstone_overlay", "save_and_quit"],
        run=_make_run(),
    )
    assert derive_state_type(raw) == "capstone_overlay"


def test_play_card_avail_does_not_classify_as_overlay():
    """If real play actions are present, NOT an overlay-only state."""
    raw = UpstreamGameState(
        screen="COMBAT",
        available_actions=["play_card", "end_turn", "save_and_quit"],
        run=_make_run(),
        combat_type="elite",
    )
    assert derive_state_type(raw) != "capstone_overlay"


def test_only_save_and_quit_is_not_overlay():
    """avail=[save_and_quit] alone (e.g. enemy turn) is not overlay-only."""
    raw = UpstreamGameState(
        screen="COMBAT",
        available_actions=["save_and_quit"],
        run=_make_run(),
        combat_type="elite",
    )
    # Should fall through to combat classification, not "capstone_overlay".
    assert derive_state_type(raw) != "capstone_overlay"


def test_capstone_overlay_in_combat_adjacent_phases():
    """state_machine relies on this set to suppress false COMBAT_END."""
    assert "capstone_overlay" in COMBAT_ADJACENT_PHASES


# ── state_machine: the load-bearing assertion ────────────────


def test_combat_to_overlay_does_not_fire_combat_end():
    """Reproduces the user's 2026-05-01 fatal-abort scenario.

    Sequence: enter elite fight, then user opens the TopBar map button.
    Mod reports avail=[close_capstone_overlay], screen=MAP.
    state_machine MUST treat this as combat-adjacent (no COMBAT_END).
    """
    sm = GameStateMachine()

    # Tick 1: enter elite combat.
    elite = _make_state(screen="COMBAT", available_actions=["play_card"], combat_type="elite")
    t1 = sm.update(elite)
    assert t1 == PhaseTransition.COMBAT_START
    assert sm.in_combat is True

    # Tick 2: user opens TopBar map button mid-combat.  Mod reports
    # screen=MAP + avail=[close_capstone_overlay], but the underlying
    # combat is still active.  This is the bug we're fixing.
    overlay = _make_state(
        screen="MAP",
        available_actions=["close_capstone_overlay", "save_and_quit"],
    )
    assert overlay.state_type == "capstone_overlay"
    t2 = sm.update(overlay)
    assert t2 != PhaseTransition.COMBAT_END, (
        "Opening a UI overlay mid-combat must NOT fire COMBAT_END — "
        "doing so records a phantom Victory, corrupts skill confidence, "
        "and discards multi-turn combat conversation history."
    )
    assert sm.in_combat is True, "Still in combat — overlay is just a visual interrupt"


def test_overlay_close_returns_to_combat_without_combat_start():
    """After the overlay closes, state_machine must NOT fire a fresh
    COMBAT_START — the same combat is continuing.
    """
    sm = GameStateMachine()

    # Enter combat.
    elite = _make_state(screen="COMBAT", available_actions=["play_card"], combat_type="elite")
    sm.update(elite)
    assert sm.in_combat is True

    # Open overlay mid-combat.
    overlay = _make_state(
        screen="MAP",
        available_actions=["close_capstone_overlay", "save_and_quit"],
    )
    sm.update(overlay)
    assert sm.in_combat is True

    # Close overlay → back to combat.  No COMBAT_START expected since
    # in_combat never flipped.
    back_to_combat = _make_state(
        screen="COMBAT", available_actions=["play_card"], combat_type="elite",
    )
    t3 = sm.update(back_to_combat)
    assert t3 != PhaseTransition.COMBAT_START
    assert sm.in_combat is True


def test_overlay_outside_combat_is_harmless():
    """Opening overlay at the map screen (no combat) is benign — just a
    PHASE_CHANGE both directions, no false transitions.
    """
    sm = GameStateMachine()

    # On map navigation.
    on_map = _make_state(screen="MAP", available_actions=["choose_map_node"])
    sm.update(on_map)
    assert sm.in_combat is False

    # User opens deck view via TopBar.
    overlay = _make_state(
        screen="MAP", available_actions=["close_capstone_overlay", "save_and_quit"],
    )
    t = sm.update(overlay)
    # Non-fatal; just a phase change.  Critically NOT a false COMBAT_START
    # or COMBAT_END.
    assert t not in {PhaseTransition.COMBAT_START, PhaseTransition.COMBAT_END}
    assert sm.in_combat is False


def test_real_combat_end_still_fires_through_rewards():
    """Don't break the happy path: combat → combat_rewards still fires
    COMBAT_END.  Sanity check that the fix doesn't over-extend.
    """
    sm = GameStateMachine()

    elite = _make_state(screen="COMBAT", available_actions=["play_card"], combat_type="elite")
    sm.update(elite)
    assert sm.in_combat is True

    # Player wins → mod transitions to REWARD screen.
    rewards = _make_state(
        screen="REWARD",
        available_actions=["claim_reward", "collect_rewards_and_proceed"],
    )
    t = sm.update(rewards)
    assert t == PhaseTransition.COMBAT_END
    assert sm.in_combat is False
