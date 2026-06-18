"""Unit tests for ToolExecutor and tool schema integration.

Covers:
  - ToolExecutor: handler dispatch, error handling, state management
  - TestToolSchemaIntegration: get_tool_for_state mapping
"""

from __future__ import annotations

from src.brain.tool_executor import ToolExecutor
from src.brain.tool_schemas import (
    COMBAT_TOOL,
    get_tool_for_state,
)
from src.mcp_client.upstream_models import (
    RawCombatEnemyPayload,
    RawCombatHandCardPayload,
    RawCombatPayload,
    RawCombatPlayerPayload,
    RawDeckCardPayload,
    RawRunPayload,
    UpstreamGameState,
)
from src.state.game_state import GameState


# ── Local helpers (signatures differ from conftest) ──────────────


def _make_enemy(
    name: str = "Test Louse",
    index: int = 0,
    hp: int = 30,
    max_hp: int = 30,
    is_alive: bool = True,
) -> RawCombatEnemyPayload:
    return RawCombatEnemyPayload(
        index=index,
        enemy_id=name.lower().replace(" ", "_"),
        name=name,
        current_hp=hp,
        max_hp=max_hp,
        block=0,
        is_alive=is_alive,
    )


def _make_hand_card(
    name: str = "Strike",
    index: int = 0,
    energy_cost: int = 1,
    playable: bool = True,
    damage: int | None = 6,
    rules_text: str = "Deal 6 damage.",
    requires_target: bool = True,
) -> RawCombatHandCardPayload:
    return RawCombatHandCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        energy_cost=energy_cost,
        playable=playable,
        damage=damage,
        rules_text=rules_text,
        requires_target=requires_target,
        target_index_space="enemies" if requires_target else None,
    )


def _make_deck_card(
    name: str = "Strike",
    index: int = 0,
    card_type: str = "Attack",
    energy_cost: int = 1,
    rarity: str = "Starter",
) -> RawDeckCardPayload:
    return RawDeckCardPayload(
        index=index,
        card_id=name.lower().replace(" ", "_"),
        name=name,
        card_type=card_type,
        energy_cost=energy_cost,
        rarity=rarity,
        rules_text=f"{name} description.",
    )


def _make_combat_gs(
    enemies: list[RawCombatEnemyPayload] | None = None,
    hand: list[RawCombatHandCardPayload] | None = None,
    player_hp: int = 60,
    player_max_hp: int = 80,
    energy: int = 3,
    floor: int = 6,
    state_type_hint: str = "boss",
    turn: int = 1,
    deck: list[RawDeckCardPayload] | None = None,
) -> GameState:
    """Build a GameState suitable for combat tests."""
    if enemies is None:
        enemies = [_make_enemy()]
    if hand is None:
        hand = [
            _make_hand_card("Strike", 0),
            _make_hand_card(
                "Defend", 1, damage=None, rules_text="Gain 5 block.", requires_target=False
            ),
        ]
    if deck is None:
        deck = [_make_deck_card("Strike", 0), _make_deck_card("Defend", 1, card_type="Skill")]

    combat = RawCombatPayload(
        player=RawCombatPlayerPayload(
            current_hp=player_hp,
            max_hp=player_max_hp,
            energy=energy,
        ),
        hand=hand,
        enemies=enemies,
    )

    run = RawRunPayload(
        character_id="ironclad",
        character_name="Ironclad",
        floor=floor,
        current_hp=player_hp,
        max_hp=player_max_hp,
        gold=120,
        max_energy=3,
        deck=deck,
        potions=[],
    )

    raw = UpstreamGameState(
        screen=state_type_hint.upper(),
        in_combat=True,
        turn=turn,
        available_actions=["play_card", "end_turn"],
        combat=combat,
        run=run,
    )

    return GameState(raw=raw, state_type=state_type_hint)


# ═══════════════════════════════════════════════════════════════
# ToolExecutor tests
# ═══════════════════════════════════════════════════════════════


class TestToolExecutor:
    """Tests for ToolExecutor handler dispatch and error handling."""

    def test_execute_unknown_tool(self):
        """Executing an unknown tool should return error, not crash."""
        executor = ToolExecutor()
        result = executor.execute("nonexistent_tool", {})
        assert "Unknown tool" in result
        assert "nonexistent_tool" in result

    def test_removed_query_tools_return_unknown(self):
        """Removed static query tools should return unknown-tool errors."""
        executor = ToolExecutor(game_state=None)

        assert "Unknown tool" in executor.execute("get_run_progress", {})
        assert "Unknown tool" in executor.execute("search_strategy", {})

    def test_all_handlers_never_raise(self):
        """Every handler should catch exceptions and return error strings."""
        executor = ToolExecutor()  # All dependencies are None

        # recall_encounter is the only remaining static query handler
        result = executor.execute("recall_encounter", {})
        assert isinstance(result, str)

    def test_set_game_state(self):
        """set_game_state should update the internal state reference."""
        executor = ToolExecutor()
        assert executor._game_state is None

        gs = _make_combat_gs()
        executor.set_game_state(gs)
        assert executor._game_state is gs


# ═══════════════════════════════════════════════════════════════
# Tool schema integration tests
# ═══════════════════════════════════════════════════════════════


class TestToolSchemaIntegration:
    """Tests for get_tool_for_state."""

    def test_get_tool_for_state(self):
        """get_tool_for_state should return correct tools for combat states."""
        assert get_tool_for_state("monster") == COMBAT_TOOL
        assert get_tool_for_state("boss") == COMBAT_TOOL
        assert get_tool_for_state("unknown") is None
