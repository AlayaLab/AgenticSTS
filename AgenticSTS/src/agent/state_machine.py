"""Game phase state machine.

Tracks transitions between game states and detects
meaningful phase changes (e.g., combat end, floor change).
"""

from __future__ import annotations

import logging
from enum import Enum

from src.state.game_state import COMBAT_PHASES, GameState
from src.state.upstream_game_state import COMBAT_ADJACENT_PHASES

logger = logging.getLogger(__name__)


class PhaseTransition(Enum):
    """Types of phase transitions we care about."""

    NONE = "none"
    COMBAT_START = "combat_start"
    COMBAT_END = "combat_end"
    FLOOR_CHANGE = "floor_change"
    ACT_CHANGE = "act_change"
    PHASE_CHANGE = "phase_change"
    RUN_END = "run_end"


class GameStateMachine:
    """Tracks game state transitions for the agent loop."""

    def __init__(self) -> None:
        self._prev_state_type: str = ""
        self._prev_floor: int = 0
        self._prev_act: int = 0
        self._in_combat: bool = False
        self._combat_count: int = 0

    def update(self, gs: GameState) -> PhaseTransition:
        """Process a new game state and return the transition type."""
        transition = self._detect_transition(gs)

        # Update tracking state
        self._prev_state_type = gs.state_type
        if gs.run:
            self._prev_floor = gs.run.floor
            # Upstream has no 'act' field; floor alone is sufficient for tracking
            self._prev_act = self._prev_floor

        if transition != PhaseTransition.NONE:
            logger.debug("Phase transition: %s → %s", self._prev_state_type, gs.state_type)

        return transition

    def _detect_transition(self, gs: GameState) -> PhaseTransition:
        """Detect the highest-priority transition.

        Priority order: RUN_END > ACT_CHANGE > COMBAT_START/END > FLOOR_CHANGE > PHASE_CHANGE.
        When a floor change coincides with a combat transition, the combat
        transition takes priority since the agent loop needs to react to it
        (e.g. reset round trackers, record combat results).
        """
        # Run ended — highest priority
        if gs.is_game_over or gs.is_menu:
            return PhaseTransition.RUN_END

        # Act change (subsumes floor change)
        # Upstream has no 'act' field — detect act change from floor jump
        # (e.g. floor jumps from 17 to 1 when entering next act)
        cur_floor = gs.run.floor if gs.run else 0
        if cur_floor > 0 and self._prev_floor > 0 and cur_floor < self._prev_floor:
            self._in_combat = False
            return PhaseTransition.ACT_CHANGE

        # Track floor change for later (combat transitions take priority)
        floor_changed = (
            gs.run is not None
            and gs.run.floor != self._prev_floor
            and self._prev_floor > 0
        )

        # Combat transitions take priority over floor change.
        # card_select/hand_select can happen MID-COMBAT (e.g. Survivor discard).
        # Treat them as still "in combat" to avoid false COMBAT_END.
        combat_or_adjacent = COMBAT_PHASES | COMBAT_ADJACENT_PHASES
        was_combat = self._prev_state_type in COMBAT_PHASES
        is_combat = gs.state_type in COMBAT_PHASES
        is_in_combat_zone = gs.state_type in combat_or_adjacent

        if is_combat and not was_combat and not self._in_combat:
            self._in_combat = True
            self._combat_count += 1
            return PhaseTransition.COMBAT_START

        if self._in_combat and not is_in_combat_zone:
            # Truly leaving combat (not just going to card_select mid-fight)
            self._in_combat = False
            return PhaseTransition.COMBAT_END

        if floor_changed:
            return PhaseTransition.FLOOR_CHANGE

        # Generic phase change
        if gs.state_type != self._prev_state_type and self._prev_state_type:
            return PhaseTransition.PHASE_CHANGE

        return PhaseTransition.NONE

    @property
    def in_combat(self) -> bool:
        return self._in_combat

    @property
    def combat_count(self) -> int:
        return self._combat_count

    def reset(self) -> None:
        self._prev_state_type = ""
        self._prev_floor = 0
        self._prev_act = 0
        self._in_combat = False
        self._combat_count = 0
