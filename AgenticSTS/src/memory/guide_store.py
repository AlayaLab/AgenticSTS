"""Guide store: persistent storage for consolidated guides.

Stores CombatGuide, RouteGuide, and DeckGuide in a single JSON file.
Guides are the "self-evolution" output — consolidated from domain episodes.
"""

from __future__ import annotations

import json
import logging
import threading
from dataclasses import replace
from pathlib import Path
from typing import Any

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.models_v2 import(
    CombatGuide,
    DeckGuide,
    RouteGuide,
    normalize_character,
)
from src.memory.event_models import EventGuide
from src.patch.version import get_runtime_version

logger = logging.getLogger(__name__)


class GuideStore:
    """Thread-safe store for all guide types. Single JSON persistence."""

    def __init__(self) -> None:
        self._combat_guides: dict[str, CombatGuide] = {}   # key: "enemy_key:character"
        self._route_guides: dict[str, RouteGuide] = {}      # key: "act:character"
        self._deck_guides: dict[str, DeckGuide] = {}         # key: "character:archetype"
        self._event_guides: dict[str, EventGuide] = {}       # key: "event_id:character"
        self._lock = threading.Lock()

    # ── Combat guides ──────────────────────────────────────────

    @staticmethod
    def _combat_key(enemy_key: str, character: str) -> str:
        return f"{normalize_enemy_key(enemy_key).lower()}:{normalize_character(character)}"

    @staticmethod
    def _prefer_combat_guide(current: CombatGuide | None, candidate: CombatGuide) -> CombatGuide:
        if current is None:
            return candidate
        current_score = (current.episode_count, current.confidence, current.updated_at)
        candidate_score = (candidate.episode_count, candidate.confidence, candidate.updated_at)
        return candidate if candidate_score >= current_score else current

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        with self._lock:
            return self._combat_guides.get(self._combat_key(enemy_key, character))

    def set_combat_guide(self, guide: CombatGuide) -> None:
        with self._lock:
            normalized = replace(guide, enemy_key=normalize_enemy_key(guide.enemy_key))
            key = self._combat_key(normalized.enemy_key, normalized.character)
            self._combat_guides[key] = self._prefer_combat_guide(
                self._combat_guides.get(key), normalized
            )

    @property
    def combat_guide_count(self) -> int:
        with self._lock:
            return len(self._combat_guides)

    # ── Route guides ───────────────────────────────────────────

    @staticmethod
    def _route_key(act: int, character: str) -> str:
        return f"{act}:{normalize_character(character)}"

    def get_route_guide(self, act: int, character: str) -> RouteGuide | None:
        with self._lock:
            return self._route_guides.get(self._route_key(act, character))

    def set_route_guide(self, guide: RouteGuide) -> None:
        with self._lock:
            key = self._route_key(guide.act, guide.character)
            self._route_guides[key] = guide

    @property
    def route_guide_count(self) -> int:
        with self._lock:
            return len(self._route_guides)

    # ── Deck guides ────────────────────────────────────────────

    @staticmethod
    def _deck_key(character: str, archetype: str) -> str:
        return f"{normalize_character(character)}:{archetype.lower()}"

    def get_deck_guide(self, character: str, archetype: str) -> DeckGuide | None:
        with self._lock:
            return self._deck_guides.get(self._deck_key(character, archetype))

    def set_deck_guide(self, guide: DeckGuide) -> None:
        with self._lock:
            key = self._deck_key(guide.character, guide.archetype)
            self._deck_guides[key] = guide

    @property
    def deck_guide_count(self) -> int:
        with self._lock:
            return len(self._deck_guides)

    # ── Event guides ───────────────────────────────────────────

    @staticmethod
    def _event_key(event_id: str, character: str) -> str:
        return f"{event_id.upper()}:{normalize_character(character)}"

    def get_event_guide(self, event_id: str, character: str) -> EventGuide | None:
        with self._lock:
            return self._event_guides.get(self._event_key(event_id, character))

    def set_event_guide(self, guide: EventGuide) -> None:
        with self._lock:
            key = self._event_key(guide.event_id, guide.character)
            self._event_guides[key] = guide

    @property
    def event_guide_count(self) -> int:
        with self._lock:
            return len(self._event_guides)

    # ── Persistence ────────────────────────────────────────────

    def save(self, path: Path) -> None:
        rv = get_runtime_version()
        with self._lock:
            combat_guides = {
                k: replace(
                    g,
                    game_version=g.game_version or rv.game_version,
                    mod_version=g.mod_version or rv.mod_version,
                    data_schema_version=g.data_schema_version or rv.data_schema_version,
                ).to_dict()
                for k, g in self._combat_guides.items()
            }
            route_guides = {
                k: replace(
                    g,
                    game_version=g.game_version or rv.game_version,
                    mod_version=g.mod_version or rv.mod_version,
                    data_schema_version=g.data_schema_version or rv.data_schema_version,
                ).to_dict()
                for k, g in self._route_guides.items()
            }
            deck_guides = {
                k: replace(
                    g,
                    game_version=g.game_version or rv.game_version,
                    mod_version=g.mod_version or rv.mod_version,
                    data_schema_version=g.data_schema_version or rv.data_schema_version,
                ).to_dict()
                for k, g in self._deck_guides.items()
            }
            data: dict[str, Any] = {
                "combat_guides": combat_guides,
                "route_guides": route_guides,
                "deck_guides": deck_guides,
                "event_guides": {k: g.to_dict() for k, g in self._event_guides.items()},
            }

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        logger.debug(
            "Saved guides: %d combat, %d route, %d deck to %s",
            len(data["combat_guides"]), len(data["route_guides"]),
            len(data["deck_guides"]), path,
        )

    @classmethod
    def load(cls, path: Path) -> GuideStore:
        store = cls()
        if not path.exists():
            return store

        try:
            data = json.loads(path.read_text(encoding="utf-8"))

            for _k, v in data.get("combat_guides", {}).items():
                guide = CombatGuide.from_dict(v)
                key = cls._combat_key(guide.enemy_key, guide.character)
                store._combat_guides[key] = cls._prefer_combat_guide(
                    store._combat_guides.get(key), guide
                )

            for _k, v in data.get("route_guides", {}).items():
                guide = RouteGuide.from_dict(v)
                store._route_guides[cls._route_key(guide.act, guide.character)] = guide

            for _k, v in data.get("deck_guides", {}).items():
                guide = DeckGuide.from_dict(v)
                store._deck_guides[cls._deck_key(guide.character, guide.archetype)] = guide

            for _k, v in data.get("event_guides", {}).items():
                guide = EventGuide.from_dict(v)
                store._event_guides[cls._event_key(guide.event_id, guide.character)] = guide

            logger.info(
                "Loaded guides: %d combat, %d route, %d deck from %s",
                store.combat_guide_count, store.route_guide_count,
                store.deck_guide_count, path,
            )
        except Exception as exc:
            logger.warning("Failed to load guide store from %s: %s", path, exc)

        return store

    def stats(self) -> dict[str, int]:
        return {
            "combat_guides": self.combat_guide_count,
            "route_guides": self.route_guide_count,
            "deck_guides": self.deck_guide_count,
            "event_guides": self.event_guide_count,
        }
