"""Short-term working memory: mutable state within a run/combat.

The only mutable data structure in the memory system (mirrors MemGPT's
working memory concept). Accumulates round-by-round combat data,
route node traversals, and deck change events during gameplay.

Reset per run (reset_run) and per combat (reset_combat).
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING

from src.memory.enemy_keys import normalize_enemy_key

if TYPE_CHECKING:
    from src.memory.models_v2 import (
        CombatContext,
        CombatDelta,
        EnemyRoundState,
        PowerSnapshot,
    )
    from src.memory.situation import SituationTag

logger = logging.getLogger(__name__)


class NoteScope(str, Enum):
    """Lifetime scope for strategic notes."""
    TURN = "turn"
    COMBAT = "combat"
    RUN = "run"


TRIGGER_STATE_MAP: dict[str, set[str] | None] = {
    "combat": {"monster", "elite", "boss", "hand_select"},
    "deck_building": {"card_reward", "shop", "card_select"},
    "routing": {"map", "rest_site", "event"},
    "all": None,
}


# Auto-infer note.triggers from the recording context_type when the caller
# omits triggers (passes None). Most LLM tool schemas default note_triggers
# to ["all"], which loop.py::_record_strategic_note also collapses into the
# None sentinel so this matrix kicks in by default. The matrix here controls
# which decision types see a note recorded under each context_type.
#
# Design intent:
#   - Combat-state notes (monster/elite/boss/hand_select) describe in-fight
#     intent → only relevant to other combat decisions.
#   - Deck-shaping notes (card_reward/shop/card_select) describe build plans
#     → relevant to combat (fight with this deck) AND further deck decisions.
#   - Cross-cutting nodes (rest_site/event) often touch HP, relics, AND deck
#     → broad relevance.
#   - Map notes are purely about path choice → only routing decisions.
#   - ``potion`` and ``treasure`` are intentionally absent: their tool schemas
#     do not expose a strategic_note field, so no note is ever recorded under
#     those context_types from the main path. ``get_strategic_thread`` filters
#     potion / treasure decisions via TRIGGER_STATE_MAP for any explicitly
#     authored note that does land there.
_CONTEXT_TYPE_TO_TRIGGERS: dict[str, tuple[str, ...]] = {
    "monster": ("combat",),
    "elite": ("combat",),
    "boss": ("combat",),
    "hand_select": ("combat",),
    "card_reward": ("combat", "deck_building"),
    "shop": ("combat", "deck_building"),
    "card_select": ("combat", "deck_building"),
    "rest_site": ("combat", "deck_building", "routing"),
    "event": ("combat", "deck_building", "routing"),
    "map": ("routing",),
}


@dataclass(frozen=True)
class StrategicNote:
    """A scoped strategic note with trigger filtering."""
    context_type: str
    note: str
    scope: NoteScope = NoteScope.RUN
    triggers: tuple[str, ...] = ("all",)
    created_floor: int = 0
    created_round: int = 0


def _note_matches_context(note: StrategicNote, state_type: str) -> bool:
    """Check if a note's triggers match the given state_type."""
    for trigger in note.triggers:
        if trigger == "all":
            return True
        matched_types = TRIGGER_STATE_MAP.get(trigger)
        if matched_types is not None and state_type in matched_types:
            return True
    return False


def _normalize_strategic_note(note: str) -> str:
    """Convert legacy JSON-style deck-state notes into prose.

    Older prompts asked the model to place a structured object inside the
    string-valued ``strategic_note`` field. The Strategic Thread is read by
    another model, so keep the stored form as an actionable sentence instead
    of leaking schema keys back into future prompts.
    """
    cleaned = " ".join((note or "").strip().split())
    if not cleaned:
        return ""
    if not (cleaned.startswith("{") and cleaned.endswith("}")):
        return cleaned

    try:
        payload = json.loads(cleaned)
    except json.JSONDecodeError:
        return cleaned
    if not isinstance(payload, dict):
        return cleaned

    known_keys = {"phase", "engine_mechanic", "core_pieces", "needs", "avoid"}
    if not any(key in payload for key in known_keys):
        return cleaned

    phase = str(payload.get("phase") or "").strip().lower()
    engine = str(payload.get("engine_mechanic") or "").strip()
    needs = str(payload.get("needs") or "").strip()
    avoid = str(payload.get("avoid") or "").strip()
    raw_core = payload.get("core_pieces") or []
    if isinstance(raw_core, str):
        raw_core = [raw_core]
    elif not isinstance(raw_core, (list, tuple)):
        raw_core = []
    core_pieces = [str(piece).strip() for piece in raw_core if str(piece).strip()]
    core_text = ", ".join(core_pieces[:3])

    if phase == "committed":
        lead = "Committed plan"
    elif phase == "foundation":
        lead = "Foundation plan"
    else:
        lead = "Build plan"

    parts: list[str] = []
    if engine and engine.lower() != "none":
        sentence = f"{lead}: {engine}"
        if core_text:
            sentence += f" via {core_text}"
        parts.append(sentence + ".")
    elif phase == "foundation":
        parts.append(f"{lead}: no core engine yet.")
    else:
        parts.append(f"{lead}: keep the current deck direction coherent.")

    if needs:
        parts.append(f"Needs {needs}.")
    if avoid:
        parts.append(f"Avoid {avoid}.")

    return " ".join(parts)


# ── Mutable tracking records (internal, not persisted) ────────


@dataclass
class CombatRoundTracker:
    """Mutable tracker for a single combat round (accumulated during gameplay)."""

    round_num: int = 0
    energy_available: int = 0
    energy_used: int = 0
    hp_start: int = 0
    hp_end: int = 0
    block_gained: int = 0
    enemy_intents: list[str] = field(default_factory=list)
    cards_played: list[str] = field(default_factory=list)
    potions_used: list[str] = field(default_factory=list)
    damage_dealt: int = 0
    damage_taken: int = 0
    events: list[CombatDelta] = field(default_factory=list)  # per-action state deltas
    hand_at_start: list[str] = field(default_factory=list)  # cards in hand at round start
    situation_tag: SituationTag | None = None   # computed at round start
    enemy_states: list[EnemyRoundState] = field(default_factory=list)  # rich per-enemy round-start state
    player_powers_snapshot: list[PowerSnapshot] = field(default_factory=list)  # round-start player powers
    enemy_powers_snapshot: list[tuple[str, ...]] = field(default_factory=list)  # per-enemy powers at round start
    enemy_hp_snapshot: list[tuple[str, str, int, int]] = field(default_factory=list)  # per-enemy (id, name, hp, max_hp)
    # Pre-round context for mistake-driven skill discovery (§2.3 of spec
    # 2026-04-19-mistake-driven-skill-discovery-design.md).
    block_before: int = 0
    draw_pile_size: int = 0
    discard_pile_size: int = 0
    exhaust_pile_size: int = 0
    usable_potions: list[str] = field(default_factory=list)
    incoming_damage: int = 0
    agent_plan: list[str] = field(default_factory=list)
    llm_call_seq: int = -1


@dataclass
class CombatTracker:
    """Mutable tracker for a full combat encounter."""

    enemy_key: str = ""
    combat_type: str = ""             # "monster" | "elite" | "boss"
    enemy_names: list[str] = field(default_factory=list)
    hp_before: int = 0
    deck_size: int = 0
    relics: list[str] = field(default_factory=list)
    floor: int = 0
    act: int = 1
    hp_after: int = 0
    won: bool = True
    terminal_reason: str = ""
    rounds: list[CombatRoundTracker] = field(default_factory=list)
    strategic_notes: list[tuple[int, str]] = field(default_factory=list)  # (round_num, note)
    retrieved_skill_ids: list[str] = field(default_factory=list)
    _current_round: CombatRoundTracker | None = None
    combat_context: CombatContext | None = None  # fixed per-combat context

    def start_round(self, round_num: int, energy: int, hp: int,
                    enemy_intents: list[str],
                    hand_cards: list[str] | None = None) -> None:
        """Begin tracking a new combat round."""
        # Finalize previous round if exists
        if self._current_round is not None:
            self._finalize_round_tag(self._current_round)
            self.rounds.append(self._current_round)
        self._current_round = CombatRoundTracker(
            round_num=round_num,
            energy_available=energy,
            hp_start=hp,
            hp_end=hp,
            enemy_intents=enemy_intents,
            hand_at_start=list(hand_cards) if hand_cards else [],
        )

    def record_round_context(
        self,
        *,
        block_before: int = 0,
        draw_pile_size: int = 0,
        discard_pile_size: int = 0,
        exhaust_pile_size: int = 0,
        usable_potions: list[str] | None = None,
        incoming_damage: int = 0,
        agent_plan: list[str] | None = None,
        llm_call_seq: int = -1,
    ) -> None:
        """Record pre-plan context for the current round.

        Called from the combat codepath immediately after the strategic
        plan LLM returns (so llm_call_seq can be attached). Safe no-op
        when there is no active round (e.g. boundary cases before
        start_round is first called).

        See docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §2.2.
        """
        if self._current_round is None:
            return
        r = self._current_round
        r.block_before = block_before
        r.draw_pile_size = draw_pile_size
        r.discard_pile_size = discard_pile_size
        r.exhaust_pile_size = exhaust_pile_size
        r.usable_potions = list(usable_potions or [])
        r.incoming_damage = incoming_damage
        r.agent_plan = list(agent_plan or [])
        r.llm_call_seq = llm_call_seq

    def set_round_situation_tag(self, tag: SituationTag) -> None:
        """Set the situation tag for the current round (computed by caller)."""
        if self._current_round is not None:
            self._current_round.situation_tag = tag

    @staticmethod
    def _classify_outcome(damage_taken: int) -> str:
        """Classify round outcome by damage taken."""
        if damage_taken == 0:
            return "clean"
        if damage_taken < 8:
            return "acceptable"
        if damage_taken < 15:
            return "bad"
        return "disaster"

    def _finalize_round_tag(self, rnd: CombatRoundTracker) -> None:
        """Fill outcome fields on a round's situation tag before archiving."""
        if rnd.situation_tag is None:
            return
        from src.memory.situation import SituationTag
        old = rnd.situation_tag
        rnd.situation_tag = SituationTag(
            hand_capabilities=old.hand_capabilities,
            damage_taken=rnd.damage_taken,
            outcome_quality=self._classify_outcome(rnd.damage_taken),
            tag_source=old.tag_source,
        )

    def record_card_play(self, card_name: str, energy_cost: int = 0) -> None:
        """Record a card being played in the current round."""
        if self._current_round is None:
            return
        self._current_round.cards_played.append(card_name)
        self._current_round.energy_used += energy_cost

    def record_potion_use(self, potion_name: str) -> None:
        """Record a potion being used in the current round."""
        if self._current_round is None:
            return
        self._current_round.potions_used.append(potion_name)

    def record_strategic_note(self, note: str) -> None:
        """Append a strategic note keyed by the current round."""
        note = (note or "").strip()
        if not note:
            return
        round_num = self._current_round.round_num if self._current_round else 0
        if self.strategic_notes and self.strategic_notes[-1] == (round_num, note):
            return
        self.strategic_notes.append((round_num, note))

    def update_hp(self, hp: int) -> None:
        """Update HP at end of round or after damage."""
        if self._current_round is not None:
            self._current_round.hp_end = hp

    def record_metrics(
        self,
        *,
        damage_dealt: int = 0,
        block_gained: int = 0,
        hp_after: int | None = None,
    ) -> None:
        """Record numeric combat outcomes for the current round."""
        if self._current_round is None:
            return
        if damage_dealt > 0:
            self._current_round.damage_dealt += damage_dealt
        if block_gained > 0:
            self._current_round.block_gained += block_gained
        if hp_after is not None:
            self._current_round.hp_end = hp_after

    def finalize(self) -> None:
        """Finalize tracking — flush current round."""
        if self._current_round is not None:
            self._finalize_round_tag(self._current_round)
            self.rounds.append(self._current_round)
            self._current_round = None

    @property
    def total_rounds(self) -> int:
        extra = 1 if self._current_round is not None else 0
        return len(self.rounds) + extra

    @property
    def total_cards_played(self) -> int:
        total = sum(len(r.cards_played) for r in self.rounds)
        if self._current_round:
            total += len(self._current_round.cards_played)
        return total


@dataclass
class RouteNodeTracker:
    """Mutable tracker for a route node traversal."""

    floor: int = 0
    node_type: str = ""
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    cards_gained: list[str] = field(default_factory=list)
    cards_removed: list[str] = field(default_factory=list)
    relics_gained: list[str] = field(default_factory=list)
    potions_gained: list[str] = field(default_factory=list)
    completion_reason: str = "completed"


@dataclass
class EventTracker:
    """Mutable tracker for a single event encounter."""

    event_id: str = ""
    event_title: str = ""
    floor: int = 0
    act: int = 1
    chosen_option_index: int = -1
    chosen_option_text: str = ""
    all_options: list[str] = field(default_factory=list)
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    deck_before: list[str] = field(default_factory=list)
    cards_gained: list[str] = field(default_factory=list)
    cards_lost: list[str] = field(default_factory=list)
    relics_gained: list[str] = field(default_factory=list)
    potions_gained: list[str] = field(default_factory=list)
    all_option_details: list[dict] = field(default_factory=list)


@dataclass
class DeckChangeRecord:
    """A single deck modification event (mutable, internal)."""

    floor: int = 0
    event_type: str = ""              # "add" | "remove" | "upgrade" | "transform"
    card_name: str = ""
    source: str = ""                  # "combat_reward", "shop", "event", "boss_reward"


# ── Short-Term Memory ─────────────────────────────────────────


class ShortTermMemory:
    """Mutable working memory that accumulates data during a run.

    Provides formatted summaries for injection into LLM prompts
    (current combat timeline, recent route progress, deck changes).

    Reset per run via reset_run(). Combat tracker reset per combat.
    """

    def __init__(self) -> None:
        # Combat state
        self._combat: CombatTracker | None = None
        self._completed_combats: list[CombatTracker] = []

        # Route state (per act)
        self._route_nodes_by_act: dict[int, list[RouteNodeTracker]] = {}
        self._current_route_node: RouteNodeTracker | None = None

        # Deck change events
        self._deck_events: list[DeckChangeRecord] = []

        # Card play frequency (across all combats in this run)
        self._card_play_counts: dict[str, int] = {}
        # Sly play frequency (subset of plays triggered via Sly discard)
        self._sly_play_counts: dict[str, int] = {}

        # Starting deck snapshot
        self._starting_deck: list[str] = []
        self._starting_deck_captured: bool = False

        # Event tracking
        self._completed_events: list[EventTracker] = []
        self._current_event: EventTracker | None = None

        # Strategic thread: accumulated intent notes across decisions
        self._strategic_notes: list[StrategicNote] = []
        self._deck_identity: str = ""

    # ── Run lifecycle ──────────────────────────────────────────

    def reset_run(self) -> None:
        """Clear all state for a new run."""
        self._combat = None
        self._completed_combats.clear()
        self._route_nodes_by_act.clear()
        self._current_route_node = None
        self._deck_events.clear()
        self._card_play_counts.clear()
        self._sly_play_counts.clear()
        self._starting_deck.clear()
        self._starting_deck_captured = False
        self._completed_events.clear()
        self._current_event = None
        self._strategic_notes.clear()
        self._deck_identity = ""

    def capture_starting_deck(self, deck: list[str]) -> None:
        """Snapshot the starting deck (call once at start of run)."""
        if not self._starting_deck_captured:
            self._starting_deck = list(deck)
            self._starting_deck_captured = True

    # ── Combat tracking ────────────────────────────────────────

    def start_combat(
        self,
        enemy_names: list[str],
        combat_type: str,
        hp: int,
        deck_size: int,
        relics: list[str],
        floor: int,
        act: int,
    ) -> None:
        """Begin tracking a new combat encounter."""
        # Build enemy key
        if len(enemy_names) == 1:
            enemy_key = normalize_enemy_key(enemy_names[0])
        elif len(enemy_names) > 1:
            enemy_key = normalize_enemy_key("multi:" + "+".join(sorted(enemy_names)))
        else:
            enemy_key = "unknown"

        self._combat = CombatTracker(
            enemy_key=enemy_key,
            combat_type=combat_type,
            enemy_names=list(enemy_names),
            hp_before=hp,
            deck_size=deck_size,
            relics=list(relics),
            floor=floor,
            act=act,
        )

    def start_combat_round(
        self,
        round_num: int,
        energy: int,
        hp: int,
        enemy_intents: list[str],
        hand_cards: list[str] | None = None,
        *,
        situation_tag: SituationTag | None = None,
        enemy_states: list[EnemyRoundState] | None = None,
        player_powers_snapshot: list[PowerSnapshot] | None = None,
        enemy_powers: list[tuple[str, ...]] | None = None,
        enemy_hp: list[tuple[str, str, int, int]] | None = None,
    ) -> None:
        """Begin a new round in the current combat."""
        if self._combat is not None:
            self._combat.start_round(round_num, energy, hp, enemy_intents, hand_cards)
            if situation_tag is not None:
                self._combat.set_round_situation_tag(situation_tag)
            if enemy_states is not None and self._combat._current_round is not None:
                self._combat._current_round.enemy_states = list(enemy_states)
            if player_powers_snapshot is not None and self._combat._current_round is not None:
                self._combat._current_round.player_powers_snapshot = list(
                    player_powers_snapshot
                )
            if enemy_powers is not None and self._combat._current_round is not None:
                self._combat._current_round.enemy_powers_snapshot = list(enemy_powers)
            if enemy_hp is not None and self._combat._current_round is not None:
                self._combat._current_round.enemy_hp_snapshot = list(enemy_hp)

    def record_card_play(self, card_name: str, energy_cost: int = 0) -> None:
        """Record a card played in current combat round."""
        if self._combat is not None:
            self._combat.record_card_play(card_name, energy_cost)
        # Track global play counts
        self._card_play_counts[card_name] = self._card_play_counts.get(card_name, 0) + 1

    def record_sly_play(self, card_name: str) -> None:
        """Record a Sly-triggered play (card discarded by effect → auto-played)."""
        self._sly_play_counts[card_name] = self._sly_play_counts.get(card_name, 0) + 1

    def record_potion_use(self, potion_name: str) -> None:
        """Record a potion used in current combat round."""
        if self._combat is not None:
            self._combat.record_potion_use(potion_name)

    def record_combat_delta(self, delta: CombatDelta) -> None:
        """Record a per-action combat delta in the current round."""
        if self._combat is not None and self._combat._current_round is not None:
            self._combat._current_round.events.append(delta)

    def update_combat_hp(self, hp: int) -> None:
        """Update HP during combat (after damage/healing)."""
        if self._combat is not None:
            self._combat.update_hp(hp)

    def record_combat_metrics(
        self,
        *,
        damage_dealt: int = 0,
        block_gained: int = 0,
        hp_after: int | None = None,
    ) -> None:
        """Record aggregate combat metrics for the current round."""
        if self._combat is not None:
            self._combat.record_metrics(
                damage_dealt=damage_dealt,
                block_gained=block_gained,
                hp_after=hp_after,
            )

    def end_combat(
        self,
        won: bool,
        hp_after: int,
        *,
        terminal_reason: str | None = None,
    ) -> None:
        """Finalize the current combat encounter."""
        if self._combat is None:
            return
        self._combat.finalize()
        resolved_terminal_reason = terminal_reason or ("win" if won else "loss")
        self._combat.hp_after = hp_after
        self._combat.won = won
        self._combat.terminal_reason = resolved_terminal_reason
        # Backward compatibility for older consumers/tests still reading attrs.
        self._combat._hp_after = hp_after  # type: ignore[attr-defined]
        self._combat._won = won  # type: ignore[attr-defined]
        self._combat._terminal_reason = resolved_terminal_reason  # type: ignore[attr-defined]
        self._completed_combats.append(self._combat)
        self._combat = None

    @property
    def current_combat(self) -> CombatTracker | None:
        return self._combat

    def active_combat_tracker(self) -> CombatTracker | None:
        """Return the currently-active CombatTracker, or None if no combat is in progress.

        Used by the combat codepath (v2_engine + agent loop) to attach per-round
        context hooks — see CombatTracker.record_round_context and
        docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md §2.2.

        Returned value is the same object as ``current_combat``; this method
        exists as the canonical accessor so future refactors (e.g. moving the
        tracker onto a different attribute) have a single call site to update.
        """
        return self._combat

    @property
    def completed_combats(self) -> list[CombatTracker]:
        return self._completed_combats

    # ── Route tracking ─────────────────────────────────────────

    def start_route_node(
        self,
        floor: int,
        node_type: str,
        hp: int,
        gold: int,
    ) -> None:
        """Begin tracking a route node traversal."""
        # Finalize previous node if exists
        self._finalize_route_node()
        self._current_route_node = RouteNodeTracker(
            floor=floor,
            node_type=node_type,
            hp_before=hp,
            gold_before=gold,
        )

    def end_route_node(self, hp: int, gold: int, act: int) -> None:
        """Finalize the current route node."""
        if self._current_route_node is not None:
            self._current_route_node.hp_after = hp
            self._current_route_node.gold_after = gold
            self._current_route_node.completion_reason = "completed"
            self._finalize_route_node(act)

    def finalize_open_state(
        self,
        act: int,
        hp: int = 0,
        gold: int = 0,
        *,
        combat_terminal_reason: str = "loss",
    ) -> None:
        """Finalize any in-progress combat or route node at run end.

        Called by the agent loop post-run to ensure data is captured
        even when the run ends mid-combat or mid-node (e.g. death).
        Public API — avoids direct private attribute access from loop.py.
        """
        if self._current_route_node is not None:
            self._current_route_node.hp_after = hp
            self._current_route_node.gold_after = gold
            self._current_route_node.completion_reason = (
                "aborted" if combat_terminal_reason == "abort" else "completed"
            )
            self._finalize_route_node(act)
        if self._combat is not None:
            self.end_combat(
                won=combat_terminal_reason == "win",
                hp_after=hp,
                terminal_reason=combat_terminal_reason,
            )

    def record_card_gained(self, card_name: str) -> None:
        """Record a card gained at the current route node."""
        if self._current_route_node is not None:
            self._current_route_node.cards_gained.append(card_name)

    def record_card_removed(self, card_name: str) -> None:
        """Record a card removed at the current route node."""
        if self._current_route_node is not None:
            self._current_route_node.cards_removed.append(card_name)

    def record_relic_gained(self, relic_name: str) -> None:
        """Record a relic gained at the current route node."""
        if self._current_route_node is not None:
            self._current_route_node.relics_gained.append(relic_name)

    def record_potion_gained(self, potion_name: str) -> None:
        """Record a potion gained at the current route node."""
        if self._current_route_node is not None:
            self._current_route_node.potions_gained.append(potion_name)

    def _finalize_route_node(self, act: int | None = None) -> None:
        """Move current route node to the act's list."""
        if self._current_route_node is None:
            return
        if act is None:
            act = 1  # Default if unknown
        if act not in self._route_nodes_by_act:
            self._route_nodes_by_act[act] = []
        self._route_nodes_by_act[act].append(self._current_route_node)
        self._current_route_node = None

    @property
    def route_nodes_by_act(self) -> dict[int, list[RouteNodeTracker]]:
        return self._route_nodes_by_act

    # ── Deck tracking ──────────────────────────────────────────

    def record_deck_change(
        self,
        floor: int,
        event_type: str,
        card_name: str,
        source: str,
    ) -> None:
        """Record a deck modification event."""
        self._deck_events.append(DeckChangeRecord(
            floor=floor,
            event_type=event_type,
            card_name=card_name,
            source=source,
        ))

    @property
    def deck_events(self) -> list[DeckChangeRecord]:
        return self._deck_events

    @property
    def card_play_counts(self) -> dict[str, int]:
        return self._card_play_counts

    @property
    def sly_play_counts(self) -> dict[str, int]:
        return self._sly_play_counts

    @property
    def starting_deck(self) -> list[str]:
        return self._starting_deck

    # ── Prompt summaries ───────────────────────────────────────

    def get_combat_summary(self, max_rounds: int = 3) -> str:
        """Format current combat timeline for prompt injection.

        Shows the last N rounds for context. Returns empty string
        if not in combat or no rounds yet.
        """
        if self._combat is None:
            return ""

        all_rounds = list(self._combat.rounds)
        if self._combat._current_round is not None:
            all_rounds.append(self._combat._current_round)

        if not all_rounds:
            return ""

        recent = all_rounds[-max_rounds:]
        lines = [f"**Current Combat** vs {self._combat.enemy_key} "
                 f"(Round {self._combat.total_rounds}, "
                 f"HP: {self._combat.hp_before}→now):"]

        for r in recent:
            cards = ", ".join(r.cards_played) if r.cards_played else "none"
            potions = f" | Potions: {', '.join(r.potions_used)}" if r.potions_used else ""
            intents = ", ".join(r.enemy_intents) if r.enemy_intents else "?"
            lines.append(
                f"  R{r.round_num}: Played [{cards}]{potions} "
                f"| Intents: [{intents}] | HP: {r.hp_start}→{r.hp_end}"
            )

        return "\n".join(lines)

    def get_route_summary(self, act: int) -> str:
        """Format route progress for the given act."""
        nodes = self._route_nodes_by_act.get(act, [])
        if not nodes:
            return ""

        lines = [f"**Act {act} Route** ({len(nodes)} nodes):"]
        for n in nodes[-5:]:  # Last 5 nodes
            hp_delta = n.hp_after - n.hp_before
            gold_delta = n.gold_after - n.gold_before
            extras = []
            if n.cards_gained:
                extras.append(f"+cards: {', '.join(n.cards_gained)}")
            if n.relics_gained:
                extras.append(f"+relics: {', '.join(n.relics_gained)}")
            extra_str = f" | {'; '.join(extras)}" if extras else ""
            lines.append(
                f"  F{n.floor} {n.node_type}: HP {hp_delta:+d}, Gold {gold_delta:+d}{extra_str}"
            )

        return "\n".join(lines)

    def get_deck_summary(self) -> str:
        """Format deck evolution summary."""
        if not self._deck_events:
            return ""

        adds = [e for e in self._deck_events if e.event_type == "add"]
        removes = [e for e in self._deck_events if e.event_type == "remove"]
        upgrades = [e for e in self._deck_events if e.event_type == "upgrade"]

        parts = ["**Deck Changes**:"]
        if adds:
            parts.append(f"  Added ({len(adds)}): {', '.join(e.card_name for e in adds[-5:])}")
        if removes:
            parts.append(f"  Removed ({len(removes)}): {', '.join(e.card_name for e in removes)}")
        if upgrades:
            parts.append(
                f"  Upgraded ({len(upgrades)}): "
                f"{', '.join(e.card_name for e in upgrades)}"
            )

        # Top played cards
        if self._card_play_counts:
            top = sorted(self._card_play_counts.items(), key=lambda x: x[1], reverse=True)[:5]
            parts.append(f"  Most played: {', '.join(f'{n}({c})' for n, c in top)}")

        return "\n".join(parts)

    # ── Event tracking ─────────────────────────────────────────

    def start_event(
        self,
        event_id: str,
        event_title: str,
        floor: int,
        act: int,
        hp: int,
        gold: int,
        deck: list[str],
    ) -> None:
        """Begin tracking an event encounter."""
        self._current_event = EventTracker(
            event_id=event_id,
            event_title=event_title,
            floor=floor,
            act=act,
            hp_before=hp,
            gold_before=gold,
            deck_before=list(deck),
        )

    def end_event(
        self,
        chosen_index: int,
        option_text: str,
        hp_after: int,
        gold_after: int,
        all_options: list[str],
        cards_gained: list[str],
        cards_lost: list[str],
        relics_gained: list[str],
        potions_gained: list[str],
        all_option_details: list[dict] | None = None,
    ) -> None:
        """Finalize the current event with outcome data."""
        if self._current_event is None:
            logger.warning("end_event called without start_event")
            return
        self._current_event.chosen_option_index = chosen_index
        self._current_event.chosen_option_text = option_text
        self._current_event.hp_after = hp_after
        self._current_event.gold_after = gold_after
        self._current_event.all_options = list(all_options)
        self._current_event.cards_gained = list(cards_gained)
        self._current_event.cards_lost = list(cards_lost)
        self._current_event.relics_gained = list(relics_gained)
        self._current_event.potions_gained = list(potions_gained)
        self._current_event.all_option_details = list(all_option_details or [])
        self._completed_events.append(self._current_event)
        self._current_event = None

    def cancel_event(self) -> None:
        """Discard the current event tracker without persisting.

        Used by the extractor to drop stages where every option is a
        mod-flagged ``is_proceed`` closing page — those carry no decision
        signal.
        """
        self._current_event = None

    @property
    def completed_events(self) -> list[EventTracker]:
        return self._completed_events

    @property
    def current_event(self) -> EventTracker | None:
        return self._current_event

    # ── Strategic thread ───────────────────────────────────────

    def record_strategic_note(
        self,
        context_type: str,
        note: str,
        *,
        scope: NoteScope = NoteScope.RUN,
        triggers: tuple[str, ...] | None = None,
        floor: int = 0,
        combat_round: int = 0,
    ) -> None:
        """Record a scoped strategic note. Keeps last 15.

        ``triggers`` follows a sentinel convention:
          - ``None`` (default) → auto-infer from ``context_type`` via
            ``_CONTEXT_TYPE_TO_TRIGGERS`` so the note only surfaces during
            relevant state types. Use this for notes recorded by the
            decision pipeline.
          - ``("all",)`` (explicit tuple) → preserved as-is; the note shows
            during every state type. Use this for genuinely cross-cutting
            notes.
          - any other tuple → preserved verbatim.

        Two cleanup steps run before the new note is appended:

        1. **Trigger auto-inference (1c)**: see sentinel rule above.

        2. **Per-context_type dedup (2d)**: each ``context_type`` slot holds at
           most one active note — the latest. Earlier notes for the same
           context_type are paraphrases of the same intent and only clutter
           the rendered Strategic Thread.
        """
        note = _normalize_strategic_note(note)
        if not note:
            return

        if triggers is None:
            triggers = _CONTEXT_TYPE_TO_TRIGGERS.get(context_type, ("all",))

        self._strategic_notes = [
            n for n in self._strategic_notes if n.context_type != context_type
        ]
        self._strategic_notes.append(StrategicNote(
            context_type=context_type,
            note=note,
            scope=scope,
            triggers=triggers,
            created_floor=floor,
            created_round=combat_round,
        ))
        if len(self._strategic_notes) > 15:
            self._strategic_notes = self._strategic_notes[-15:]

    def get_strategic_thread(
        self, max_entries: int = 5, *, current_context: str = "",
    ) -> str:
        """Format recent strategic notes for prompt injection.

        When *current_context* is non-empty, only notes whose triggers
        match that state_type are included.
        """
        if not self._strategic_notes:
            return ""
        if current_context:
            filtered = [
                n for n in self._strategic_notes
                if _note_matches_context(n, current_context)
            ]
        else:
            filtered = list(self._strategic_notes)
        recent = filtered[-max_entries:]
        if not recent:
            return ""
        return "\n".join(f"- [{n.context_type}] {n.note}" for n in recent)

    def expire_turn_notes(self) -> None:
        """Remove all notes with TURN scope."""
        self._strategic_notes = [
            n for n in self._strategic_notes if n.scope != NoteScope.TURN
        ]

    def expire_combat_notes(self) -> None:
        """Remove all notes with TURN or COMBAT scope."""
        self._strategic_notes = [
            n for n in self._strategic_notes
            if n.scope not in (NoteScope.TURN, NoteScope.COMBAT)
        ]

    def get_current_situation_tag(self):
        """Get the situation tag for the current combat round, or None."""
        if self._combat and self._combat._current_round:
            return self._combat._current_round.situation_tag
        return None

    @property
    def deck_identity(self) -> str:
        """Current deck identity/archetype description."""
        return self._deck_identity

    @deck_identity.setter
    def deck_identity(self, value: str) -> None:
        self._deck_identity = value.strip() if value else ""
