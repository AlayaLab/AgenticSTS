"""Event-specific memory models.

Extracted from `src/memory/models_v2.py` on 2026-04-24 to keep that file
under the codebase's maintainability ceiling. These dataclasses describe
the memory + guide shape for run-time events (Orobas, bridges, judgments,
etc.) — everything the event guide consolidator persists and the
retriever injects.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Any

from src.memory.models_v2 import normalize_character


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


def _now() -> float:
    return time.time()


@dataclass(frozen=True)
class RelicReward:
    """A relic offered by an event option, snapshotted at encounter time."""

    name: str = ""
    description: str = ""       # BBCode-stripped at extract time
    rarity: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "description": self.description, "rarity": self.rarity}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RelicReward":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            rarity=d.get("rarity", ""),
        )


@dataclass(frozen=True)
class CardReward:
    """A card offered by an event option, snapshotted at encounter time.

    Mod-side payload uses keys ``type`` and ``is_upgraded``. Python-side
    uses ``card_type`` and ``upgraded`` to avoid shadowing the ``type``
    built-in. ``from_dict`` accepts both spellings; ``to_dict`` emits the
    Python-side names.
    """

    name: str = ""
    cost: int = 0
    card_type: str = ""         # "skill" | "attack" | "power"
    rules_text: str = ""        # BBCode-stripped at extract time
    upgraded: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "cost": self.cost,
            "card_type": self.card_type,
            "rules_text": self.rules_text,
            "upgraded": self.upgraded,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "CardReward":
        return cls(
            name=d.get("name", ""),
            cost=int(d.get("cost", 0) or 0),
            card_type=d.get("card_type", d.get("type", "")),
            rules_text=d.get("rules_text", ""),
            upgraded=bool(d.get("upgraded", d.get("is_upgraded", False))),
        )


@dataclass(frozen=True)
class PotionReward:
    """A potion offered by an event option, snapshotted at encounter time."""

    name: str = ""
    description: str = ""       # BBCode-stripped at extract time
    potion_type: str = ""       # mod-side key is "type"

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "potion_type": self.potion_type,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "PotionReward":
        return cls(
            name=d.get("name", ""),
            description=d.get("description", ""),
            potion_type=d.get("potion_type", d.get("type", "")),
        )


@dataclass(frozen=True)
class EventOptionSnapshot:
    """Snapshot of a single event option with full reward details.

    BBCode is stripped at extract time (``src/agent/loop.py::_finalize_event_stage``)
    so consumers can trust the strings. Reward fields are frozen dataclasses
    of (name, description, ...) so the consolidator prompt can render rich
    rules text without any runtime knowledge lookups.

    Legacy JSONL with bare-string reward lists is accepted by ``from_dict``
    and upgraded to the dataclass form with empty description/rarity/etc.
    """

    index: int = 0
    title: str = ""
    description: str = ""
    hp_cost: int | None = None
    gold_cost: int | None = None
    relics_offered: tuple[RelicReward, ...] = ()
    cards_offered: tuple[CardReward, ...] = ()
    potions_offered: tuple[PotionReward, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "index": self.index,
            "title": self.title,
            "description": self.description,
        }
        if self.hp_cost is not None:
            d["hp_cost"] = self.hp_cost
        if self.gold_cost is not None:
            d["gold_cost"] = self.gold_cost
        if self.relics_offered:
            d["relics_offered"] = [r.to_dict() for r in self.relics_offered]
        if self.cards_offered:
            d["cards_offered"] = [c.to_dict() for c in self.cards_offered]
        if self.potions_offered:
            d["potions_offered"] = [p.to_dict() for p in self.potions_offered]
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "EventOptionSnapshot":
        def _coerce(items: Any, reward_cls: type) -> tuple:
            if not items:
                return ()
            out = []
            for it in items:
                if isinstance(it, str):
                    out.append(reward_cls.from_dict({"name": it}))
                elif isinstance(it, dict):
                    out.append(reward_cls.from_dict(it))
                else:
                    # Unknown shape — keep processing siblings.
                    continue
            return tuple(out)

        return cls(
            index=d.get("index", 0),
            title=d.get("title", ""),
            description=d.get("description", ""),
            hp_cost=d.get("hp_cost"),
            gold_cost=d.get("gold_cost"),
            relics_offered=_coerce(d.get("relics_offered", ()), RelicReward),
            cards_offered=_coerce(d.get("cards_offered", ()), CardReward),
            potions_offered=_coerce(d.get("potions_offered", ()), PotionReward),
        )


@dataclass(frozen=True)
class EventMemory:
    """A single event decision with outcome tracking.

    The previous ``boss_impact_score`` / ``boss_impact_analysis`` /
    ``outcome_quality`` fields were removed: per-run event scoring ran as a
    separate postrun LLM call that produced fragile one-shot judgements the
    downstream guide consolidation was not actually using in its scoring
    logic. The guide consolidator is now the single place where event
    decisions are evaluated, and it works off the raw memory fields plus
    the newly-added ``run_victory`` / ``run_final_floor`` outcome anchor.
    Unknown keys in persisted JSONL (including the deprecated fields) are
    silently dropped by ``from_dict``.
    """

    memory_id: str = field(default_factory=_new_id)
    run_id: str = ""
    floor: int = 0
    act: int = 1
    event_id: str = ""
    event_title: str = ""
    character: str = ""
    chosen_option_index: int = -1
    chosen_option_text: str = ""
    all_options: tuple[str, ...] = ()
    all_option_details: tuple[EventOptionSnapshot, ...] = ()
    # State changes
    hp_before: int = 0
    hp_after: int = 0
    gold_before: int = 0
    gold_after: int = 0
    cards_gained: tuple[str, ...] = ()
    cards_lost: tuple[str, ...] = ()
    relics_gained: tuple[str, ...] = ()
    potions_gained: tuple[str, ...] = ()
    # Run-level outcome anchor for downstream guide scoring
    run_victory: bool = False
    run_final_floor: int = 0
    timestamp: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "run_id": self.run_id,
            "floor": self.floor,
            "act": self.act,
            "event_id": self.event_id,
            "event_title": self.event_title,
            "character": self.character,
            "chosen_option_index": self.chosen_option_index,
            "chosen_option_text": self.chosen_option_text,
            "all_options": list(self.all_options),
            "all_option_details": [od.to_dict() for od in self.all_option_details],
            "hp_before": self.hp_before,
            "hp_after": self.hp_after,
            "gold_before": self.gold_before,
            "gold_after": self.gold_after,
            "cards_gained": list(self.cards_gained),
            "cards_lost": list(self.cards_lost),
            "relics_gained": list(self.relics_gained),
            "potions_gained": list(self.potions_gained),
            "run_victory": self.run_victory,
            "run_final_floor": self.run_final_floor,
            "timestamp": self.timestamp,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventMemory:
        return cls(
            memory_id=d.get("memory_id", _new_id()),
            run_id=d.get("run_id", ""),
            floor=d.get("floor", 0),
            act=d.get("act", 1),
            event_id=d.get("event_id", ""),
            event_title=d.get("event_title", ""),
            character=d.get("character", ""),
            chosen_option_index=d.get("chosen_option_index", -1),
            chosen_option_text=d.get("chosen_option_text", ""),
            all_options=tuple(d.get("all_options", ())),
            all_option_details=tuple(
                EventOptionSnapshot.from_dict(od)
                for od in d.get("all_option_details", ())
            ),
            hp_before=d.get("hp_before", 0),
            hp_after=d.get("hp_after", 0),
            gold_before=d.get("gold_before", 0),
            gold_after=d.get("gold_after", 0),
            cards_gained=tuple(d.get("cards_gained", ())),
            cards_lost=tuple(d.get("cards_lost", ())),
            relics_gained=tuple(d.get("relics_gained", ())),
            potions_gained=tuple(d.get("potions_gained", ())),
            run_victory=bool(d.get("run_victory", False)),
            run_final_floor=int(d.get("run_final_floor", 0)),
            timestamp=d.get("timestamp", _now()),
        )


def event_run_outcome_tag(em: EventMemory) -> str:
    """Compact '[run: VICTORY F51]' / '[run: DEFEAT F34]' tag for an event memory.

    Returns '' when the memory has no outcome anchor (legacy records
    predating the run_victory/run_final_floor fields, or backfill rows
    whose source run is missing from runs/history.jsonl). Kept in one
    place so the guide consolidator / retriever / skill-discovery prompts
    stay in sync if the format ever changes.
    """
    if not em.run_final_floor:
        return ""
    return f" [run: {'VICTORY' if em.run_victory else 'DEFEAT'} F{em.run_final_floor}]"


@dataclass(frozen=True)
class EventGuideOption:
    """A single scored option in an event's option library.

    ``canonical_name`` is the LLM-normalized title (matched against
    ``gs.event.options[*].title`` case-insensitively at injection time).
    ``stage_index`` is 0-based; multi-step events use 0,1,2... in stage
    order. ``variant_type`` distinguishes deterministic vs pool-random vs
    deck-random choices. ``sample_size`` is recomputed server-side from
    ``EventMemory`` count (LLM output is overridden).
    """

    canonical_name: str = ""
    stage_index: int = 0
    variant_type: str = "fixed"     # "fixed" | "random_from_pool" | "deck_random"
    score: float = 0.0              # -1.0 to 1.0
    analysis: str = ""
    observed_rewards: tuple[str, ...] = ()
    sample_size: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical_name": self.canonical_name,
            "stage_index": self.stage_index,
            "variant_type": self.variant_type,
            "score": self.score,
            "analysis": self.analysis,
            "observed_rewards": list(self.observed_rewards),
            "sample_size": self.sample_size,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventGuideOption:
        return cls(
            canonical_name=d.get("canonical_name", ""),
            stage_index=int(d.get("stage_index", 0) or 0),
            variant_type=d.get("variant_type", "fixed"),
            score=float(d.get("score", 0.0) or 0.0),
            analysis=d.get("analysis", ""),
            observed_rewards=tuple(d.get("observed_rewards", ()) or ()),
            sample_size=int(d.get("sample_size", 0) or 0),
        )


@dataclass(frozen=True)
class EventGuide:
    """Consolidated guide for a specific event type."""

    guide_id: str = field(default_factory=_new_id)
    event_id: str = ""
    character: str = ""
    guide_text: str = ""
    options: tuple[EventGuideOption, ...] = ()
    episode_count: int = 0
    confidence: float = 0.5
    version: int = 1
    created_at: float = field(default_factory=_now)
    updated_at: float = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return {
            "guide_id": self.guide_id,
            "event_id": self.event_id,
            "character": self.character,
            "guide_text": self.guide_text,
            "options": [o.to_dict() for o in self.options],
            "episode_count": self.episode_count,
            "confidence": self.confidence,
            "version": self.version,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> EventGuide:
        raw_options = d.get("options", ()) or ()
        options = tuple(
            EventGuideOption.from_dict(o) if isinstance(o, dict) else o
            for o in raw_options
        )
        return cls(
            guide_id=d.get("guide_id", _new_id()),
            event_id=d.get("event_id", ""),
            character=normalize_character(d.get("character", "")),
            guide_text=d.get("guide_text", ""),
            options=options,
            episode_count=d.get("episode_count", 0),
            confidence=d.get("confidence", 0.5),
            version=d.get("version", 1),
            created_at=d.get("created_at", _now()),
            updated_at=d.get("updated_at", _now()),
        )
