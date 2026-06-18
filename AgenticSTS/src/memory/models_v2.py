"""HCM (Hierarchical Categorical Memory) data models.

Domain-specific frozen dataclasses for the 3 categorical memory types:
- Combat: per-encounter timeline with round-by-round data
- Route: per-act traversal with node-level outcomes
- Card Build: per-run deck trajectory with play counts

Plus consolidated Guide models that generalize episodes into reusable knowledge.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field, replace
from typing import Any

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.situation import SituationTag

# ── Helpers ──────────────────────────────────────────────────

def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


# ── Character Name Normalization ──────────────────────────────

_CHARACTER_ALIASES: dict[str, str] = {
    "铁甲战士": "the ironclad", "the ironclad": "the ironclad", "ironclad": "the ironclad",
    "the_ironclad": "the ironclad",
    "静默猎人": "the silent", "the silent": "the silent", "silent": "the silent",
    "the_silent": "the silent",
    "缺陷机器人": "the defect", "the defect": "the defect", "defect": "the defect",
    "the_defect": "the defect",
    "摄政王": "the regent", "the regent": "the regent", "regent": "the regent",
    "the_regent": "the regent",
    "亡灵缚者": "the necrobinder", "the necrobinder": "the necrobinder", "necrobinder": "the necrobinder",
    "the_necrobinder": "the necrobinder",
}


def normalize_character(name: str) -> str:
    """Normalize character name to canonical English form.

    Handles both English and Chinese game locales so that memory stores
    don't fragment when the game language switches.
    """
    return _CHARACTER_ALIASES.get(name.lower().strip(), name.lower().strip())


# ── Combat Delta Models (per-action state diffs) ───────────────


@dataclass(frozen=True)
class EnemyDelta:
    """State change for a single enemy after one action."""

    enemy_id: str = ""                    # primary key: enemy_id or "{name}:{index}"
    name: str = ""                        # display name
    index: int = 0                        # for display only
    hp: int | None = None                 # delta (negative = took damage)
    block: int | None = None              # delta
    powers_changed: tuple[str, ...] = ()  # ("+Vulnerable(2)", "-Weak")
    died: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "enemy_id": self.enemy_id,
            "name": self.name,
            "index": self.index,
        }
        if self.hp is not None:
            d["hp"] = self.hp
        if self.block is not None:
            d["block"] = self.block
        if self.powers_changed:
            d["powers_changed"] = list(self.powers_changed)
        if self.died:
            d["died"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EnemyDelta:
        return cls(
            enemy_id=d.get("enemy_id", ""),
            name=d.get("name", ""),
            index=d.get("index", 0),
            hp=d.get("hp"),
            block=d.get("block"),
            powers_changed=tuple(d.get("powers_changed", ())),
            died=d.get("died", False),
        )


@dataclass(frozen=True)
class CombatDelta:
    """What changed after a single action during combat.

    Only non-None / non-empty fields actually changed.
    """

    event_type: str = ""                  # card_play | potion_use | end_turn | card_select | selection_confirm
    source: str = ""                      # card/potion name or "turn_end"
    source_description: str = ""          # rules_text from played card (for LLM combo reasoning)
    target: str | None = None             # "Toadpole[0]" or None

    # Player deltas (None = unchanged)
    hp: int | None = None
    block: int | None = None
    energy: int | None = None

    # Status effect changes
    powers_changed: tuple[str, ...] = ()  # ("+Strength(2)", "-Weak")

    # Per-enemy changes (only affected enemies)
    enemy_deltas: tuple[EnemyDelta, ...] = ()

    # Card movement (exhaust pile gains)
    cards_exhausted: tuple[str, ...] = ()

    # Relic counter changes
    relic_changes: tuple[str, ...] = ()   # ("Incense Burner: 4→5",)

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "event_type": self.event_type,
            "source": self.source,
        }
        if self.source_description:
            d["source_description"] = self.source_description
        if self.target is not None:
            d["target"] = self.target
        if self.hp is not None:
            d["hp"] = self.hp
        if self.block is not None:
            d["block"] = self.block
        if self.energy is not None:
            d["energy"] = self.energy
        if self.powers_changed:
            d["powers_changed"] = list(self.powers_changed)
        if self.enemy_deltas:
            d["enemy_deltas"] = [ed.to_dict() for ed in self.enemy_deltas]
        if self.cards_exhausted:
            d["cards_exhausted"] = list(self.cards_exhausted)
        if self.relic_changes:
            d["relic_changes"] = list(self.relic_changes)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CombatDelta:
        return cls(
            event_type=d.get("event_type", ""),
            source=d.get("source", ""),
            source_description=d.get("source_description", ""),
            target=d.get("target"),
            hp=d.get("hp"),
            block=d.get("block"),
            energy=d.get("energy"),
            powers_changed=tuple(d.get("powers_changed", ())),
            enemy_deltas=tuple(
                EnemyDelta.from_dict(ed) for ed in d.get("enemy_deltas", ())
            ),
            cards_exhausted=tuple(d.get("cards_exhausted", ())),
            relic_changes=tuple(d.get("relic_changes", ())),
        )


# ── Combat Context Models (fixed per-combat) ────────────────


@dataclass(frozen=True)
class RelicSnapshot:
    """Relic state at combat start, including counter value."""

    name: str = ""
    description: str = ""
    stack: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"name": self.name}
        if self.description:
            d["description"] = self.description
        if self.stack is not None:
            d["stack"] = self.stack
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RelicSnapshot:
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            stack=d.get("stack"),
        )


@dataclass(frozen=True)
class PowerSnapshot:
    """Structured power snapshot with description metadata."""

    power_id: str = ""
    name: str = ""
    amount: int | None = None
    description: str = ""
    is_debuff: bool = False

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "power_id": self.power_id,
            "name": self.name,
        }
        if self.amount is not None:
            d["amount"] = self.amount
        if self.description:
            d["description"] = self.description
        if self.is_debuff:
            d["is_debuff"] = True
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PowerSnapshot":
        return cls(
            power_id=d.get("power_id", ""),
            name=d.get("name", ""),
            amount=d.get("amount"),
            description=d.get("description", ""),
            is_debuff=bool(d.get("is_debuff", False)),
        )


@dataclass(frozen=True)
class EnemyIntentSnapshot:
    """Structured enemy intent snapshot captured at round start."""

    intent_type: str = ""
    label: str = ""
    damage: int | None = None
    hits: int | None = None
    total_damage: int | None = None
    status_card_count: int | None = None

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {"intent_type": self.intent_type}
        if self.label:
            d["label"] = self.label
        if self.damage is not None:
            d["damage"] = self.damage
        if self.hits is not None:
            d["hits"] = self.hits
        if self.total_damage is not None:
            d["total_damage"] = self.total_damage
        if self.status_card_count is not None:
            d["status_card_count"] = self.status_card_count
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EnemyIntentSnapshot":
        return cls(
            intent_type=d.get("intent_type", ""),
            label=d.get("label", ""),
            damage=d.get("damage"),
            hits=d.get("hits"),
            total_damage=d.get("total_damage"),
            status_card_count=d.get("status_card_count"),
        )


@dataclass(frozen=True)
class EnemyRoundState:
    """Enemy state snapshot captured at the start of a combat round."""

    enemy_id: str = ""
    name: str = ""
    hp: int = 0
    max_hp: int = 0
    block: int = 0
    powers: tuple[PowerSnapshot, ...] = ()
    intents: tuple[EnemyIntentSnapshot, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "enemy_id": self.enemy_id,
            "name": self.name,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "block": self.block,
        }
        if self.powers:
            d["powers"] = [p.to_dict() for p in self.powers]
        if self.intents:
            d["intents"] = [i.to_dict() for i in self.intents]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EnemyRoundState":
        return cls(
            enemy_id=d.get("enemy_id", ""),
            name=d.get("name", ""),
            hp=d.get("hp", 0),
            max_hp=d.get("max_hp", 0),
            block=d.get("block", 0),
            powers=tuple(PowerSnapshot.from_dict(p) for p in d.get("powers", ())),
            intents=tuple(
                EnemyIntentSnapshot.from_dict(i) for i in d.get("intents", ())
            ),
        )


@dataclass(frozen=True)
class EnemySnapshot:
    """Enemy state at combat start."""

    name: str = ""
    index: int = 0
    enemy_id: str = ""
    hp: int = 0
    max_hp: int = 0
    powers: tuple[str, ...] = ()  # ("Thorns(2)", "Curl Up(9)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "index": self.index,
            "enemy_id": self.enemy_id,
            "hp": self.hp,
            "max_hp": self.max_hp,
            "powers": list(self.powers),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EnemySnapshot:
        return cls(
            name=d.get("name", ""),
            index=d.get("index", 0),
            enemy_id=d.get("enemy_id", ""),
            hp=d.get("hp", 0),
            max_hp=d.get("max_hp", 0),
            powers=tuple(d.get("powers", ())),
        )


@dataclass(frozen=True)
class CombatContext:
    """Fixed context for a combat encounter — recorded once at combat start."""

    enemy_key: str = ""
    character: str = ""
    combat_type: str = ""
    relics: tuple[RelicSnapshot, ...] = ()
    starting_hp: int = 0
    starting_max_hp: int = 0
    deck_cards: tuple[str, ...] = ()
    enemy_lineup: tuple[EnemySnapshot, ...] = ()
    player_powers: tuple[str, ...] = ()   # ("Noxious Fumes(2)", "Envenom(1)")

    def to_dict(self) -> dict[str, Any]:
        return {
            "enemy_key": self.enemy_key,
            "character": self.character,
            "combat_type": self.combat_type,
            "relics": [r.to_dict() for r in self.relics],
            "starting_hp": self.starting_hp,
            "starting_max_hp": self.starting_max_hp,
            "deck_cards": list(self.deck_cards),
            "enemy_lineup": [e.to_dict() for e in self.enemy_lineup],
            "player_powers": list(self.player_powers),
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CombatContext:
        return cls(
            enemy_key=d.get("enemy_key", ""),
            character=d.get("character", ""),
            combat_type=d.get("combat_type", ""),
            relics=tuple(RelicSnapshot.from_dict(r) for r in d.get("relics", ())),
            starting_hp=d.get("starting_hp", 0),
            starting_max_hp=d.get("starting_max_hp", 0),
            deck_cards=tuple(d.get("deck_cards", ())),
            enemy_lineup=tuple(
                EnemySnapshot.from_dict(e) for e in d.get("enemy_lineup", ())
            ),
            player_powers=tuple(d.get("player_powers", ())),
        )


# ── Combat Models ─────────────────────────────────────────────


@dataclass(frozen=True)
class CombatRound:
    """One round of a combat encounter."""

    round_num: int = 0
    energy_available: int = 0
    energy_used: int = 0
    hp_start: int = 0
    hp_end: int = 0
    block_gained: int = 0
    enemy_intents: tuple[str, ...] = ()       # ("Attack 12", "Debuff")
    cards_played: tuple[str, ...] = ()         # ("Radiate", "Defend+")
    potions_used: tuple[str, ...] = ()         # ("Fire Potion",)
    damage_dealt: int = 0
    damage_taken: int = 0
    events: tuple[CombatDelta, ...] = ()  # per-action state deltas
    hand_at_start: tuple[str, ...] = ()        # cards in hand at round start (for backfill)
    situation_tag: SituationTag | None = None   # per-round situation classification
    enemy_states: tuple[EnemyRoundState, ...] = ()  # rich per-enemy round-start state
    player_powers_snapshot: tuple[PowerSnapshot, ...] = ()  # round-start player powers
    enemy_powers_snapshot: tuple[tuple[str, ...], ...] = ()  # per-enemy powers at round start
    # Per-enemy HP snapshot at round start: ((enemy_id, name, hp, max_hp), ...)
    enemy_hp_snapshot: tuple[tuple[str, str, int, int], ...] = ()
    # Pre-round context (filled by combat_extractor for mistake-driven discovery)
    block_before: int = 0
    draw_pile_size: int = 0
    discard_pile_size: int = 0
    exhaust_pile_size: int = 0
    usable_potions: tuple[str, ...] = ()
    incoming_damage: int = 0
    agent_plan: tuple[str, ...] = ()
    # Index into run_log llm_call events for this round's strategic plan.
    # -1 means unknown/not recorded. Used by prewrite A/B to fetch raw prompt.
    llm_call_seq: int = -1

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "round_num": self.round_num,
            "energy_available": self.energy_available,
            "energy_used": self.energy_used,
            "hp_start": self.hp_start,
            "hp_end": self.hp_end,
            "block_gained": self.block_gained,
            "enemy_intents": list(self.enemy_intents),
            "cards_played": list(self.cards_played),
            "potions_used": list(self.potions_used),
            "damage_dealt": self.damage_dealt,
            "damage_taken": self.damage_taken,
        }
        if self.events:
            d["events"] = [e.to_dict() for e in self.events]
        if self.hand_at_start:
            d["hand_at_start"] = list(self.hand_at_start)
        if self.situation_tag is not None:
            d["situation_tag"] = self.situation_tag.to_dict()
        if self.enemy_states:
            d["enemy_states"] = [e.to_dict() for e in self.enemy_states]
        if self.player_powers_snapshot:
            d["player_powers_snapshot"] = [
                p.to_dict() for p in self.player_powers_snapshot
            ]
        if self.enemy_powers_snapshot:
            d["enemy_powers_snapshot"] = [list(ep) for ep in self.enemy_powers_snapshot]
        if self.enemy_hp_snapshot:
            d["enemy_hp_snapshot"] = [list(eh) for eh in self.enemy_hp_snapshot]
        if self.block_before:
            d["block_before"] = self.block_before
        if self.draw_pile_size:
            d["draw_pile_size"] = self.draw_pile_size
        if self.discard_pile_size:
            d["discard_pile_size"] = self.discard_pile_size
        if self.exhaust_pile_size:
            d["exhaust_pile_size"] = self.exhaust_pile_size
        if self.usable_potions:
            d["usable_potions"] = list(self.usable_potions)
        if self.incoming_damage:
            d["incoming_damage"] = self.incoming_damage
        if self.agent_plan:
            d["agent_plan"] = list(self.agent_plan)
        if self.llm_call_seq >= 0:
            d["llm_call_seq"] = self.llm_call_seq
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CombatRound:
        st_raw = d.get("situation_tag")
        return cls(
            round_num=d.get("round_num", 0),
            energy_available=d.get("energy_available", 0),
            energy_used=d.get("energy_used", 0),
            hp_start=d.get("hp_start", 0),
            hp_end=d.get("hp_end", 0),
            block_gained=d.get("block_gained", 0),
            enemy_intents=tuple(d.get("enemy_intents", ())),
            cards_played=tuple(d.get("cards_played", ())),
            potions_used=tuple(d.get("potions_used", ())),
            damage_dealt=d.get("damage_dealt", 0),
            damage_taken=d.get("damage_taken", 0),
            events=tuple(
                CombatDelta.from_dict(e) for e in d.get("events", ())
            ),
            hand_at_start=tuple(d.get("hand_at_start", ())),
            situation_tag=SituationTag.from_dict(st_raw) if st_raw else None,
            enemy_states=tuple(
                EnemyRoundState.from_dict(e) for e in d.get("enemy_states", ())
            ),
            player_powers_snapshot=tuple(
                PowerSnapshot.from_dict(p)
                for p in d.get("player_powers_snapshot", ())
            ),
            enemy_powers_snapshot=tuple(
                tuple(ep) for ep in d.get("enemy_powers_snapshot", ())
            ),
            enemy_hp_snapshot=tuple(
                tuple(eh) for eh in d.get("enemy_hp_snapshot", ())
            ),
            block_before=d.get("block_before", 0),
            draw_pile_size=d.get("draw_pile_size", 0),
            discard_pile_size=d.get("discard_pile_size", 0),
            exhaust_pile_size=d.get("exhaust_pile_size", 0),
            usable_potions=tuple(d.get("usable_potions", ())),
            incoming_damage=d.get("incoming_damage", 0),
            agent_plan=tuple(d.get("agent_plan", ())),
            llm_call_seq=d.get("llm_call_seq", -1),
        )


@dataclass(frozen=True)
class CombatEpisode:
    """A full combat encounter with round-by-round timeline."""

    episode_id: str = field(default_factory=_new_id)
    run_id: str = ""
    floor: int = 0
    act: int = 1
    enemy_key: str = ""               # "Kin Priest" or "multi:Slime+Fungus"
    character: str = ""
    combat_type: str = ""             # "monster" | "elite" | "boss"
    rounds: tuple[CombatRound, ...] = ()
    hp_before: int = 0
    hp_after: int = 0
    won: bool = True
    terminal_reason: str = "win"    # "win" | "loss" | "abort"
    hp_delta: int = 0                 # hp_after - hp_before
    total_damage_dealt: int = 0
    total_damage_taken: int = 0
    total_cards_played: int = 0
    deck_size: int = 0
    relics: tuple[str, ...] = ()
    timestamp: float = field(default_factory=_now)
    context: CombatContext | None = None  # fixed per-combat context (relics, deck, enemies)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 3
    # Skill IDs that were injected into this combat's prompts (all turns aggregated,
    # caller does NOT dedupe — length may exceed unique count). Used by post-write
    # lifecycle (§6) to attribute combat-level baseline deltas back to skills.
    retrieved_skill_ids: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "episode_id": self.episode_id,
            "run_id": self.run_id,
            "floor": self.floor,
            "act": self.act,
            "enemy_key": self.enemy_key,
            "character": self.character,
            "combat_type": self.combat_type,
            "rounds": [r.to_dict() for r in self.rounds],
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "won": self.won,
            "terminal_reason": self.terminal_reason,
            "hp_delta": self.hp_delta,
            "total_damage_dealt": self.total_damage_dealt,
            "total_damage_taken": self.total_damage_taken,
            "total_cards_played": self.total_cards_played,
            "deck_size": self.deck_size,
            "relics": list(self.relics),
            "timestamp": self.timestamp,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }
        if self.context is not None:
            d["context"] = self.context.to_dict()
        if self.retrieved_skill_ids:
            d["retrieved_skill_ids"] = list(self.retrieved_skill_ids)
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CombatEpisode:
        ctx_raw = d.get("context")
        won = d.get("won", True)
        terminal_reason = d.get("terminal_reason")
        if terminal_reason not in {"win", "loss", "abort"}:
            terminal_reason = "win" if won else "loss"
        return cls(
            episode_id=d.get("episode_id", _new_id()),
            run_id=d.get("run_id", ""),
            floor=d.get("floor", 0),
            act=d.get("act", 1),
            enemy_key=d.get("enemy_key", ""),
            character=d.get("character", ""),
            combat_type=d.get("combat_type", ""),
            rounds=tuple(CombatRound.from_dict(r) for r in d.get("rounds", ())),
            hp_before=d.get("hp_before", 0),
            hp_after=d.get("hp_after", 0),
            won=won,
            terminal_reason=terminal_reason,
            hp_delta=d.get("hp_delta", 0),
            total_damage_dealt=d.get("total_damage_dealt", 0),
            total_damage_taken=d.get("total_damage_taken", 0),
            total_cards_played=d.get("total_cards_played", 0),
            deck_size=d.get("deck_size", 0),
            relics=tuple(d.get("relics", ())),
            timestamp=d.get("timestamp", _now()),
            context=CombatContext.from_dict(ctx_raw) if ctx_raw else None,
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
            retrieved_skill_ids=tuple(d.get("retrieved_skill_ids", ())),
        )

    @property
    def is_aborted(self) -> bool:
        return self.terminal_reason == "abort"


# ── Route Models ─────────────────────────────────────────────


@dataclass(frozen=True)
class RouteNode:
    """A single map node traversal."""

    floor: int = 0
    # "monster", "elite", "rest", "shop", "event", "boss", "treasure"
    node_type: str = ""
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    cards_gained: tuple[str, ...] = ()
    cards_removed: tuple[str, ...] = ()
    relics_gained: tuple[str, ...] = ()
    potions_gained: tuple[str, ...] = ()
    completion_reason: str = "completed"  # "completed" | "aborted"
    summary: str = ""                  # "elite: lost 40 HP, gained Radiate"

    def to_dict(self) -> dict[str, Any]:
        return {
            "floor": self.floor,
            "node_type": self.node_type,
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "gold_before": self.gold_before,
            "gold_after": self.gold_after,
            "cards_gained": list(self.cards_gained),
            "cards_removed": list(self.cards_removed),
            "relics_gained": list(self.relics_gained),
            "potions_gained": list(self.potions_gained),
            "completion_reason": self.completion_reason,
            "summary": self.summary,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RouteNode:
        return cls(
            floor=d.get("floor", 0),
            node_type=d.get("node_type", ""),
            hp_before=d.get("hp_before", 0),
            hp_after=d.get("hp_after", 0),
            gold_before=d.get("gold_before", 0),
            gold_after=d.get("gold_after", 0),
            cards_gained=tuple(d.get("cards_gained", ())),
            cards_removed=tuple(d.get("cards_removed", ())),
            relics_gained=tuple(d.get("relics_gained", ())),
            potions_gained=tuple(d.get("potions_gained", ())),
            completion_reason=d.get("completion_reason", "completed"),
            summary=d.get("summary", ""),
        )

    @property
    def is_aborted(self) -> bool:
        return self.completion_reason == "aborted"


@dataclass(frozen=True)
class RouteMemory:
    """A complete act traversal with node-level details."""

    memory_id: str = field(default_factory=_new_id)
    run_id: str = ""
    act: int = 1
    character: str = ""
    nodes: tuple[RouteNode, ...] = ()
    hp_start: int = 0
    hp_end: int = 0
    gold_start: int = 0
    gold_end: int = 0
    boss_result: str = ""             # "won" | "lost" | "aborted" | "not_reached"
    victory_run: bool = False
    fitness: float = 0.0
    timestamp: float = field(default_factory=_now)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "run_id": self.run_id,
            "act": self.act,
            "character": self.character,
            "nodes": [n.to_dict() for n in self.nodes],
            "hp_start": self.hp_start,
            "hp_end": self.hp_end,
            "gold_start": self.gold_start,
            "gold_end": self.gold_end,
            "boss_result": self.boss_result,
            "victory_run": self.victory_run,
            "fitness": self.fitness,
            "timestamp": self.timestamp,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RouteMemory:
        return cls(
            memory_id=d.get("memory_id", _new_id()),
            run_id=d.get("run_id", ""),
            act=d.get("act", 1),
            character=d.get("character", ""),
            nodes=tuple(RouteNode.from_dict(n) for n in d.get("nodes", ())),
            hp_start=d.get("hp_start", 0),
            hp_end=d.get("hp_end", 0),
            gold_start=d.get("gold_start", 0),
            gold_end=d.get("gold_end", 0),
            boss_result=d.get("boss_result", "not_reached"),
            victory_run=d.get("victory_run", False),
            fitness=d.get("fitness", 0.0),
            timestamp=d.get("timestamp", _now()),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
        )


# ── Card Build Models ──────────────────────────────────────────


@dataclass(frozen=True)
class CardEvent:
    """A single deck modification event."""

    floor: int = 0
    event_type: str = ""              # "add" | "remove" | "upgrade" | "transform"
    card_name: str = ""
    source: str = ""                  # "combat_reward", "shop", "event", "boss_reward"

    def to_dict(self) -> dict[str, Any]:
        return {
            "floor": self.floor,
            "event_type": self.event_type,
            "card_name": self.card_name,
            "source": self.source,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardEvent:
        return cls(
            floor=d.get("floor", 0),
            event_type=d.get("event_type", ""),
            card_name=d.get("card_name", ""),
            source=d.get("source", ""),
        )


@dataclass(frozen=True)
class CardBuildMemory:
    """Full run deck trajectory with play frequency data and LLM build analysis."""

    memory_id: str = field(default_factory=_new_id)
    run_id: str = ""
    character: str = ""
    deck_events: tuple[CardEvent, ...] = ()
    card_play_counts: tuple[tuple[str, int], ...] = ()  # (("Radiate", 15), ("Defend", 8), ...)
    # LEGACY: kept for backward compat — derived from primary_plan or first build_tag
    archetype: str = ""

    # ── LLM-generated structured build analysis ─────────────────
    build_tags: tuple[str, ...] = ()       # free-form tags, e.g. ("poison", "shiv_burst", "victory")
    build_summary: str = ""                # 1-2 sentence build description
    primary_plan: str = ""                 # main win condition / strategy phrase
    damage_engine: str = ""                # what generated damage
    defense_engine: str = ""               # what generated defense
    cycle_engine: str = ""                 # what enabled draw/cycling
    energy_engine: str = ""                # what generated energy
    weak_points: str = ""                  # biggest weakness
    analysis_confidence: float = 0.0       # LLM confidence in the analysis (0.1-0.9)

    # Raw deterministic evidence dict (play counts, action-level signals, etc.)
    build_evidence: dict = field(default_factory=dict)
    starting_deck: tuple[str, ...] = ()
    final_deck: tuple[str, ...] = ()
    victory: bool = False
    completion_reason: str = "completed"   # "completed" | "aborted" | "max_steps" | ...
    final_floor: int = 0
    fitness: float = 0.0
    timestamp: float = field(default_factory=_now)

    # ── Per-card qualitative assessment (Layer 3) ─────────────────
    key_cards: tuple[tuple[str, str, str], ...] = ()  # (card_name, role, insight)

    # ── Deck coherence metric (Layer 4) ───────────────────────────
    coherence_score: float = 0.0       # 0.0-1.0, how well cards work together
    coherence_analysis: str = ""       # 1 sentence explaining the score
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "run_id": self.run_id,
            "character": self.character,
            "deck_events": [e.to_dict() for e in self.deck_events],
            "card_play_counts": [list(p) for p in self.card_play_counts],
            "archetype": self.archetype,
            "build_tags": list(self.build_tags),
            "build_summary": self.build_summary,
            "primary_plan": self.primary_plan,
            "damage_engine": self.damage_engine,
            "defense_engine": self.defense_engine,
            "cycle_engine": self.cycle_engine,
            "energy_engine": self.energy_engine,
            "weak_points": self.weak_points,
            "analysis_confidence": self.analysis_confidence,
            "build_evidence": self.build_evidence,
            "starting_deck": list(self.starting_deck),
            "final_deck": list(self.final_deck),
            "victory": self.victory,
            "completion_reason": self.completion_reason,
            "final_floor": self.final_floor,
            "fitness": self.fitness,
            "timestamp": self.timestamp,
            "key_cards": [{"card": c, "role": r, "insight": i} for c, r, i in self.key_cards],
            "coherence_score": self.coherence_score,
            "coherence_analysis": self.coherence_analysis,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardBuildMemory:
        return cls(
            memory_id=d.get("memory_id", _new_id()),
            run_id=d.get("run_id", ""),
            character=d.get("character", ""),
            deck_events=tuple(CardEvent.from_dict(e) for e in d.get("deck_events", ())),
            card_play_counts=tuple(
                (p[0], int(p[1])) for p in d.get("card_play_counts", ())
            ),
            archetype=d.get("archetype", ""),
            build_tags=tuple(d.get("build_tags", ())),
            build_summary=d.get("build_summary", ""),
            primary_plan=d.get("primary_plan", ""),
            damage_engine=d.get("damage_engine", ""),
            defense_engine=d.get("defense_engine", ""),
            cycle_engine=d.get("cycle_engine", ""),
            energy_engine=d.get("energy_engine", ""),
            weak_points=d.get("weak_points", ""),
            analysis_confidence=d.get("analysis_confidence", 0.0),
            build_evidence=d.get("build_evidence", {}),
            starting_deck=tuple(d.get("starting_deck", ())),
            final_deck=tuple(d.get("final_deck", ())),
            victory=d.get("victory", False),
            completion_reason=d.get("completion_reason", "completed"),
            final_floor=d.get("final_floor", 0),
            fitness=d.get("fitness", 0.0),
            timestamp=d.get("timestamp", _now()),
            key_cards=tuple(
                (kc["card"], kc["role"], kc.get("insight", ""))
                for kc in d.get("key_cards", [])
                if isinstance(kc, dict) and "card" in kc
            ),
            coherence_score=d.get("coherence_score", 0.0),
            coherence_analysis=d.get("coherence_analysis", ""),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
        )


# ── Guide Models (Consolidated Knowledge) ───────────────────


@dataclass(frozen=True)
class CombatGuide:
    """Consolidated guide for fighting a specific enemy."""

    guide_id: str = field(default_factory=_new_id)
    enemy_key: str = ""
    character: str = ""
    guide_text: str = ""              # LLM-generated tactical advice
    trigger_model: str = ""           # "round_based" | "threshold_based" | "death_based" | "mixed" | "unclear"
    mechanic_summary: tuple[str, ...] = ()  # Fight-structure bullets for Past Experience
    round_triggers: tuple[str, ...] = ()
    threshold_triggers: tuple[str, ...] = ()
    danger_windows: tuple[str, ...] = ()
    failure_modes: tuple[str, ...] = ()
    key_patterns: tuple[str, ...] = ()  # Deprecated legacy field, kept for backward compat
    win_rate: float = 0.0
    episode_count: int = 0
    confidence: float = 0.5
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 3

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide_id": self.guide_id,
            "enemy_key": self.enemy_key,
            "character": self.character,
            "guide_text": self.guide_text,
            "trigger_model": self.trigger_model,
            "mechanic_summary": list(self.mechanic_summary),
            "round_triggers": list(self.round_triggers),
            "threshold_triggers": list(self.threshold_triggers),
            "danger_windows": list(self.danger_windows),
            "failure_modes": list(self.failure_modes),
            "key_patterns": list(self.key_patterns),
            "win_rate": self.win_rate,
            "episode_count": self.episode_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CombatGuide:
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            enemy_key=normalize_enemy_key(d.get("enemy_key", "")),
            character=normalize_character(d.get("character", "")),
            guide_text=d.get("guide_text", ""),
            trigger_model=d.get("trigger_model", ""),
            mechanic_summary=tuple(d.get("mechanic_summary", ())),
            round_triggers=tuple(d.get("round_triggers", ())),
            threshold_triggers=tuple(d.get("threshold_triggers", ())),
            danger_windows=tuple(d.get("danger_windows", ())),
            failure_modes=tuple(d.get("failure_modes", ())),
            key_patterns=tuple(d.get("key_patterns", ())),
            win_rate=d.get("win_rate", 0.0),
            episode_count=d.get("episode_count", 0),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 3),
        )


@dataclass(frozen=True)
class RouteGuide:
    """Consolidated guide for act routing strategy."""

    guide_id: str = field(default_factory=_new_id)
    act: int = 1
    character: str = ""
    guide_text: str = ""
    preferred_pattern: str = ""       # "monster→monster→elite→rest→elite→boss"
    memory_count: int = 0
    confidence: float = 0.5
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide_id": self.guide_id,
            "act": self.act,
            "character": self.character,
            "guide_text": self.guide_text,
            "preferred_pattern": self.preferred_pattern,
            "memory_count": self.memory_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> RouteGuide:
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            act=d.get("act", 1),
            character=normalize_character(d.get("character", "")),
            guide_text=d.get("guide_text", ""),
            preferred_pattern=d.get("preferred_pattern", ""),
            memory_count=d.get("memory_count", 0),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
        )


@dataclass(frozen=True)
class DeckGuide:
    """Consolidated guide for deck building strategy."""

    guide_id: str = field(default_factory=_new_id)
    character: str = ""
    archetype: str = ""
    guide_text: str = ""
    key_cards: tuple[str, ...] = ()   # Cards critical to the archetype
    memory_count: int = 0
    source_fingerprint: str = ""      # Stable hash of the build cohort behind this guide
    confidence: float = 0.5
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide_id": self.guide_id,
            "character": self.character,
            "archetype": self.archetype,
            "guide_text": self.guide_text,
            "key_cards": list(self.key_cards),
            "memory_count": self.memory_count,
            "source_fingerprint": self.source_fingerprint,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DeckGuide:
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            character=normalize_character(d.get("character", "")),
            archetype=d.get("archetype", ""),
            guide_text=d.get("guide_text", ""),
            key_cards=tuple(d.get("key_cards", ())),
            memory_count=d.get("memory_count", 0),
            source_fingerprint=d.get("source_fingerprint", ""),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
        )



# ── Per-Card Memory (longitudinal card-level insights) ────────


@dataclass(frozen=True)
class CardMemory:
    """Per-card longitudinal memory keyed by (character, card_name).

    Tracks both hand-authored seed knowledge and deterministic run evidence.
    The ``effective_note()`` method returns a single-sentence prompt hint.
    """

    character: str = ""
    card_name: str = ""            # canonical lowercase, e.g. "backstab"
    note: str = ""                 # unified note: seed knowledge or LLM-compressed summary
    # ── Deterministic counters ───────────────────────────────
    pick_count: int = 0            # times picked in card_reward / boss_reward
    buy_count: int = 0             # times bought in shop
    play_count: int = 0            # total times played across all runs (includes Sly)
    sly_play_count: int = 0        # subset of play_count triggered via Sly discard
    draw_count: int = 0            # times appeared in hand at round start
    unplayed_draw_count: int = 0   # times drawn but not played that round
    total_damage: int = 0
    total_block: int = 0
    total_energy_gain: int = 0
    debuffs_applied: int = 0       # count of debuffs applied to enemies
    powers_applied: int = 0        # count of buffs/powers applied to player
    runs_won: int = 0              # runs containing this card that won
    runs_died_act1: int = 0        # runs where agent died in Act 1
    runs_died_act2: int = 0        # runs where agent died in Act 2
    runs_died_act3: int = 0        # runs where agent died in Act 3
    runs_incomplete: int = 0       # runs aborted (max_steps, interrupt, etc.)
    sample_count: int = 0          # number of runs contributing to stats
    # Qualitative observations from postrun core-engine analysis (§2026-04-22).
    # Each entry: {run_id, role ("core"|"support"), engine_mechanic, notes,
    # co_cards, relics, ...}. Append-only across runs.
    core_engine_observations: tuple[dict, ...] = ()
    # Qualitative observations from postrun build classification (§2026-04-23).
    # Each entry: {run_id, build_id, role, phase, evidence, confidence, ...}.
    build_role_observations: tuple[dict, ...] = ()
    # Audit trail for postrun note updates (§2026-04-24 combat-trace pipeline).
    # Each entry: {note, run_id, reason, trace_citation, ts}. Newest first.
    # Capped at 3 most-recent versions to bound growth per card.
    note_history: tuple[dict, ...] = ()
    last_updated: float = field(default_factory=_now)
    game_version: str | None = None
    mod_version: str | None = None
    data_schema_version: int = 2

    def effective_note(self) -> str:
        """Return the note for prompt injection."""
        return self.note

    def with_new_note(
        self,
        *,
        new_note: str,
        run_id: str,
        reason: str,
        trace_citation: str,
    ) -> "CardMemory":
        """Return a replace()-produced copy with note replaced and a new
        history entry prepended.  Caps history at 3 most-recent entries.

        Used by the postrun card_note_updater (Turn 2) to apply selective
        note rewrites grounded in combat trace evidence.
        """
        entry = {
            "note": new_note,
            "run_id": run_id,
            "reason": reason,
            "trace_citation": trace_citation,
            "ts": time.time(),
        }
        new_history: tuple[dict, ...] = (entry,) + self.note_history
        if len(new_history) > 3:
            new_history = new_history[:3]
        return replace(self, note=new_note, note_history=new_history)

    @property
    def has_content(self) -> bool:
        """Whether this memory has any useful info for injection.

        A note OR at least one qualitative observation qualifies.
        """
        return (
            bool(self.note)
            or bool(self.core_engine_observations)
            or bool(self.build_role_observations)
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "character": self.character,
            "card_name": self.card_name,
            "note": self.note,
            "pick_count": self.pick_count,
            "buy_count": self.buy_count,
            "play_count": self.play_count,
            "sly_play_count": self.sly_play_count,
            "draw_count": self.draw_count,
            "unplayed_draw_count": self.unplayed_draw_count,
            "total_damage": self.total_damage,
            "total_block": self.total_block,
            "total_energy_gain": self.total_energy_gain,
            "debuffs_applied": self.debuffs_applied,
            "powers_applied": self.powers_applied,
            "runs_won": self.runs_won,
            "runs_died_act1": self.runs_died_act1,
            "runs_died_act2": self.runs_died_act2,
            "runs_died_act3": self.runs_died_act3,
            "runs_incomplete": self.runs_incomplete,
            "sample_count": self.sample_count,
            "core_engine_observations": list(self.core_engine_observations),
            "build_role_observations": list(self.build_role_observations),
            "note_history": [dict(e) for e in self.note_history],
            "last_updated": self.last_updated,
            "game_version": self.game_version,
            "mod_version": self.mod_version,
            "data_schema_version": self.data_schema_version,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> CardMemory:
        # Migration: old records may have seed_note/live_summary/combat_hint instead of note
        note = d.get("note") or d.get("live_summary") or d.get("seed_note", "")
        return cls(
            character=d.get("character", ""),
            card_name=d.get("card_name", ""),
            note=note,
            pick_count=d.get("pick_count", 0),
            buy_count=d.get("buy_count", 0),
            play_count=d.get("play_count", 0),
            sly_play_count=d.get("sly_play_count", 0),
            draw_count=d.get("draw_count", 0),
            unplayed_draw_count=d.get("unplayed_draw_count", 0),
            total_damage=d.get("total_damage", 0),
            total_block=d.get("total_block", 0),
            total_energy_gain=d.get("total_energy_gain", 0),
            debuffs_applied=d.get("debuffs_applied", 0),
            powers_applied=d.get("powers_applied", 0),
            runs_won=d.get("runs_won", d.get("victory_runs", 0)),
            runs_died_act1=d.get("runs_died_act1", 0),
            runs_died_act2=d.get("runs_died_act2", 0),
            runs_died_act3=d.get("runs_died_act3", 0),
            runs_incomplete=d.get("runs_incomplete", 0),
            sample_count=d.get("sample_count", 0),
            core_engine_observations=tuple(d.get("core_engine_observations", ())),
            build_role_observations=tuple(d.get("build_role_observations", ())),
            note_history=tuple(d.get("note_history", ())),
            last_updated=d.get("last_updated", _now()),
            game_version=d.get("game_version"),
            mod_version=d.get("mod_version"),
            data_schema_version=d.get("data_schema_version", 2),
        )

    def merge_with(self, other: "CardMemory") -> "CardMemory":
        """Combine two CardMemory records that share the same canonical key.

        Used to collapse upgraded / non-upgraded variants (Strike vs Strike+)
        into a single base-name entry. Counters are summed; ``note`` and
        ``card_name`` come from whichever side has the newer ``last_updated``;
        observation lists and ``note_history`` are interleaved (history sorted
        by ts desc and capped at 3).
        """
        if self.character != other.character:
            raise ValueError(
                f"merge_with: character mismatch {self.character!r} vs {other.character!r}",
            )
        primary, secondary = (
            (self, other) if self.last_updated >= other.last_updated else (other, self)
        )
        combined_history = sorted(
            list(self.note_history) + list(other.note_history),
            key=lambda e: float(e.get("ts", 0)),
            reverse=True,
        )[:3]
        return CardMemory(
            character=self.character,
            card_name=primary.card_name,
            note=primary.note,
            pick_count=self.pick_count + other.pick_count,
            buy_count=self.buy_count + other.buy_count,
            play_count=self.play_count + other.play_count,
            sly_play_count=self.sly_play_count + other.sly_play_count,
            draw_count=self.draw_count + other.draw_count,
            unplayed_draw_count=self.unplayed_draw_count + other.unplayed_draw_count,
            total_damage=self.total_damage + other.total_damage,
            total_block=self.total_block + other.total_block,
            total_energy_gain=self.total_energy_gain + other.total_energy_gain,
            debuffs_applied=self.debuffs_applied + other.debuffs_applied,
            powers_applied=self.powers_applied + other.powers_applied,
            runs_won=self.runs_won + other.runs_won,
            runs_died_act1=self.runs_died_act1 + other.runs_died_act1,
            runs_died_act2=self.runs_died_act2 + other.runs_died_act2,
            runs_died_act3=self.runs_died_act3 + other.runs_died_act3,
            runs_incomplete=self.runs_incomplete + other.runs_incomplete,
            sample_count=self.sample_count + other.sample_count,
            core_engine_observations=primary.core_engine_observations
            + secondary.core_engine_observations,
            build_role_observations=primary.build_role_observations
            + secondary.build_role_observations,
            note_history=tuple(combined_history),
            last_updated=max(self.last_updated, other.last_updated),
            game_version=primary.game_version,
            mod_version=primary.mod_version,
            data_schema_version=max(self.data_schema_version, other.data_schema_version),
        )

    def merge_run_stats(
        self,
        *,
        play_count: int = 0,
        sly_play_count: int = 0,
        draw_count: int = 0,
        unplayed_draw_count: int = 0,
        total_damage: int = 0,
        total_block: int = 0,
        total_energy_gain: int = 0,
        debuffs_applied: int = 0,
        powers_applied: int = 0,
        victory: bool = False,
        final_act: int = 0,
        incomplete: bool = False,
        picked: bool = False,
        bought: bool = False,
    ) -> CardMemory:
        """Return a new CardMemory with this run's stats merged in.

        Args:
            victory: True if run was a win.
            final_act: 1/2/3 — the act where the agent died (ignored if victory or incomplete).
            incomplete: True if run was aborted (max_steps, etc.) — no W/L counted.
        """
        return CardMemory(
            character=self.character,
            card_name=self.card_name,
            note=self.note,
            pick_count=self.pick_count + (1 if picked else 0),
            buy_count=self.buy_count + (1 if bought else 0),
            play_count=self.play_count + play_count,
            sly_play_count=self.sly_play_count + sly_play_count,
            draw_count=self.draw_count + draw_count,
            unplayed_draw_count=self.unplayed_draw_count + unplayed_draw_count,
            total_damage=self.total_damage + total_damage,
            total_block=self.total_block + total_block,
            total_energy_gain=self.total_energy_gain + total_energy_gain,
            debuffs_applied=self.debuffs_applied + debuffs_applied,
            powers_applied=self.powers_applied + powers_applied,
            runs_won=self.runs_won + (1 if victory and not incomplete else 0),
            runs_died_act1=self.runs_died_act1 + (1 if not victory and not incomplete and final_act == 1 else 0),
            runs_died_act2=self.runs_died_act2 + (1 if not victory and not incomplete and final_act == 2 else 0),
            runs_died_act3=self.runs_died_act3 + (1 if not victory and not incomplete and final_act == 3 else 0),
            runs_incomplete=self.runs_incomplete + (1 if incomplete else 0),
            sample_count=self.sample_count + 1,
            core_engine_observations=self.core_engine_observations,
            build_role_observations=self.build_role_observations,
            note_history=self.note_history,
            last_updated=_now(),
        )


# ── Working Context (assembled for prompt injection) ──────────


@dataclass(frozen=True)
class WorkingContext:
    """Decision-type-aware memory context for prompt injection.

    Replaces MemoryContext with domain-specific hint categories.
    """

    # Domain-specific hints (new HCM system)
    combat_guide_hints: tuple[str, ...] = ()
    enemy_pattern_hints: tuple[str, ...] = ()
    route_guide_hints: tuple[str, ...] = ()
    route_memory_hints: tuple[str, ...] = ()
    deck_guide_hints: tuple[str, ...] = ()
    deck_memory_hints: tuple[str, ...] = ()
    # Per-card insights (only for offered cards in deck decisions)
    card_memory_hints: tuple[str, ...] = ()
    # Short-term context (current combat/route)
    short_term_hints: tuple[str, ...] = ()
    # Situation-level exemplars (formatted past rounds)
    situation_hints: tuple[str, ...] = ()
    # Event-specific memory hints
    event_memory_hints: tuple[str, ...] = ()
    # Progressive injection metadata
    current_round: int = 0          # 0 = non-combat; >0 = combat round number
    current_threat_level: str = ""  # "lethal"|"high"|"medium"|"low"|"" (non-combat)

    @property
    def is_empty(self) -> bool:
        return not any((
            self.combat_guide_hints, self.enemy_pattern_hints,
            self.route_guide_hints, self.route_memory_hints,
            self.deck_guide_hints, self.deck_memory_hints,
            self.card_memory_hints,
            self.short_term_hints,
            self.situation_hints,
            self.event_memory_hints,
        ))

    @property
    def total_hints(self) -> int:
        return (
            len(self.combat_guide_hints) + len(self.enemy_pattern_hints)
            + len(self.route_guide_hints) + len(self.route_memory_hints)
            + len(self.deck_guide_hints) + len(self.deck_memory_hints)
            + len(self.card_memory_hints)
            + len(self.short_term_hints)
            + len(self.situation_hints)
            + len(self.event_memory_hints)
        )

    def estimated_tokens(self) -> int:
        """Rough token estimate (1 token ~ 4 chars)."""
        total_chars = 0
        for field_hints in (
            self.combat_guide_hints, self.enemy_pattern_hints,
            self.route_guide_hints, self.route_memory_hints,
            self.deck_guide_hints, self.deck_memory_hints,
            self.card_memory_hints,
            self.short_term_hints,
            self.situation_hints,
            self.event_memory_hints,
        ):
            total_chars += sum(len(h) for h in field_hints)
        return total_chars // 4
