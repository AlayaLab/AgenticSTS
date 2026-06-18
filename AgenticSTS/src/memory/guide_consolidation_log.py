"""Append-only audit log of guide consolidations.

Each successful ``set_*_guide()`` call appends one row recording when the
new version landed. Required because ``CombatGuide``/``RouteGuide``/
``DeckGuide``/``EventGuide`` constructors reset ``created_at`` on every
re-consolidation, making the in-store ``created_at`` field unusable for
"when did this guide first exist?" queries.

Consumers (e.g. ``scripts/analyze_boss_guide_effect.py``) read this log to
bucket episodes by guide-availability at episode time.
"""
from __future__ import annotations

import json
import logging
import time
from typing import Any

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.models_v2 import normalize_character
from src.storage import paths

logger = logging.getLogger(__name__)


def append_combat(
    *, enemy_key: str, character: str, version: int, episode_count: int, win_rate: float
) -> None:
    _append({
        "ts": time.time(),
        "guide_type": "combat",
        "enemy_key": normalize_enemy_key(enemy_key),
        "character": normalize_character(character),
        "version": int(version),
        "episode_count": int(episode_count),
        "win_rate": float(win_rate),
    })


def append_route(*, act: int, character: str, version: int, memory_count: int) -> None:
    _append({
        "ts": time.time(),
        "guide_type": "route",
        "act": int(act),
        "character": normalize_character(character),
        "version": int(version),
        "memory_count": int(memory_count),
    })


def append_deck(
    *, character: str, archetype: str, version: int, build_count: int
) -> None:
    _append({
        "ts": time.time(),
        "guide_type": "deck",
        "character": normalize_character(character),
        "archetype": archetype,
        "version": int(version),
        "build_count": int(build_count),
    })


def append_event(
    *, event_id: str, character: str, version: int, memory_count: int
) -> None:
    _append({
        "ts": time.time(),
        "guide_type": "event",
        "event_id": event_id,
        "character": normalize_character(character),
        "version": int(version),
        "memory_count": int(memory_count),
    })


def _append(record: dict[str, Any]) -> None:
    try:
        path = paths.guide_consolidation_log_file()
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception:
        logger.warning("Failed to append guide consolidation log", exc_info=True)
