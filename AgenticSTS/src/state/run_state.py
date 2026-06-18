"""Accumulated state across a full game run.

Tracks the trajectory of decisions, floor snapshots, and deck changes
for cross-run learning and memory system.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from src.state.game_state import GameState


@dataclass
class Decision:
    """A single decision made by the agent."""

    floor: int
    state_type: str
    action: dict
    reasoning: str = ""
    reasoning_zh: str = ""  # Display-only translation; empty unless STS2_DISPLAY_LANGUAGE=zh
    source: str = ""  # "llm" | "random"
    strategic_note: str = ""
    timestamp: float = field(default_factory=time.time)

    # Filled in after action executes
    outcome_hp_delta: int = 0
    outcome_gold_delta: int = 0


@dataclass
class FloorSnapshot:
    """Summary of game state at the start of each floor."""

    floor: int
    act: int
    state_type: str
    hp: int
    max_hp: int
    gold: int
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def from_game_state(cls, gs: GameState) -> FloorSnapshot:
        run = gs.run
        return cls(
            floor=run.floor if run else 0,
            act=gs.act,
            state_type=gs.state_type,
            hp=gs.player_hp,
            max_hp=gs.player_max_hp,
            gold=gs.gold,
        )


@dataclass
class RunState:
    """Mutable accumulator for a single game run.

    Collects decisions, floor snapshots, and final outcome metrics.
    Used by memory system for cross-run learning.
    """

    run_id: str = ""
    character: str = ""
    target_ascension: int | None = None
    actual_ascension: int | None = None
    start_time: float = field(default_factory=time.time)

    # Accumulated data
    decisions: list[Decision] = field(default_factory=list)
    floor_snapshots: list[FloorSnapshot] = field(default_factory=list)

    # Final outcome (set when run ends)
    victory: bool = False
    final_floor: int = 0
    final_hp: int = 0
    final_max_hp: int = 0
    final_gold: int = 0
    final_score: int = 0
    end_time: float = 0.0

    # Counters
    llm_calls: int = 0
    total_actions: int = 0
    combats_won: int = 0
    combats_total: int = 0
    _highest_floor: int = 0

    @property
    def ascension(self) -> int:
        """Effective ascension: actual if known, else target, else 0."""
        if self.actual_ascension is not None:
            return self.actual_ascension
        if self.target_ascension is not None:
            return self.target_ascension
        return 0

    def record_decision(self, decision: Decision) -> None:
        self.decisions.append(decision)
        self.total_actions += 1
        if decision.source == "llm":
            self.llm_calls += 1

    def record_floor(self, gs: GameState) -> None:
        snapshot = FloorSnapshot.from_game_state(gs)
        # Avoid duplicate floor snapshots
        if not self.floor_snapshots or self.floor_snapshots[-1].floor != snapshot.floor:
            self.floor_snapshots.append(snapshot)
        # Track highest floor reached (death/menu states may lack run info)
        if gs.run and gs.run.floor > self._highest_floor:
            self._highest_floor = gs.run.floor

    def record_combat_result(self, won: bool) -> None:
        self.combats_total += 1
        if won:
            self.combats_won += 1

    def finalize(self, gs: GameState, victory: bool) -> None:
        """Mark run as complete with final metrics."""
        self.victory = victory
        self.end_time = time.time()
        self.final_floor = gs.run.floor if gs.run else self._highest_floor
        self.final_hp = gs.player_hp
        self.final_max_hp = gs.player_max_hp
        self.final_gold = gs.gold
        # final_score: STS2 API does not expose the in-game score yet.
        # Computed from fitness() for now; will use API score in Phase 3+.
        self.final_score = round(self.fitness())

    @property
    def duration_seconds(self) -> float:
        end = self.end_time or time.time()
        return end - self.start_time

    @property
    def llm_ratio(self) -> float:
        """Fraction of decisions made by LLM."""
        if self.total_actions == 0:
            return 0.0
        return self.llm_calls / self.total_actions

    @property
    def avg_hp_ratio(self) -> float:
        """Average HP ratio across floor snapshots."""
        if not self.floor_snapshots:
            return 1.0
        ratios = [
            s.hp / s.max_hp for s in self.floor_snapshots if s.max_hp > 0
        ]
        return sum(ratios) / len(ratios) if ratios else 1.0

    def fitness(self) -> float:
        """Compute fitness score for memory quality tracking.

        fitness = 100*victory + 2*floor + 50*avg_hp% + 20*gold_efficiency
        """
        gold_eff = min(self.final_gold / 500.0, 1.0) if self.final_gold > 0 else 0.0
        return (
            100.0 * int(self.victory)
            + 2.0 * self.final_floor
            + 50.0 * self.avg_hp_ratio
            + 20.0 * gold_eff
        )
