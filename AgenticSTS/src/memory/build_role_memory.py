"""Apply and format per-card build-role observations."""

from __future__ import annotations

import time
from dataclasses import replace
from typing import Any

from src.memory.card_memory_store import CardMemoryStore
from src.memory.deck_build_registry import canonical_deck_build_tag
from src.memory.models_v2 import CardMemory, normalize_character

_VALID_BUILD_ROLES = frozenset({
    "core",
    "fuel",
    "payoff",
    "support",
    "patch",
    "trap",
    "foundation",
})


def _canonical_card_name(name: str) -> str:
    return (name or "").strip().rstrip("+").lower()


def _canonical_role(role: str) -> str:
    normalized = (role or "").strip().lower().replace(" ", "_")
    if normalized in _VALID_BUILD_ROLES:
        return normalized
    if normalized in {"keystone", "core_damage"}:
        return "core"
    if normalized in {"core_defense", "draw_engine", "energy_engine", "utility"}:
        return "support"
    if normalized in {"dead_weight", "bad_pick"}:
        return "trap"
    return "support"


def role_observations_from_analysis(
    analysis: dict[str, Any],
    *,
    character: str,
    run_id: str,
) -> list[dict[str, Any]]:
    """Build normalized CardMemory role observations from build analysis output."""
    char = normalize_character(character)
    build_id = canonical_deck_build_tag(char, str(analysis.get("target_build_id", "")))
    if not build_id:
        build_id = canonical_deck_build_tag(char, str(analysis.get("target_build", "")))
    if not build_id:
        return []

    timestamp = time.time()
    confidence = max(0.1, min(0.9, float(analysis.get("confidence", 0.5) or 0.5)))
    observations: list[dict[str, Any]] = []
    seen_cards: set[str] = set()

    for item in analysis.get("card_roles", ()) or ():
        if not isinstance(item, dict):
            continue
        card = _canonical_card_name(str(item.get("card", "")))
        if not card or card in seen_cards:
            continue
        role = _canonical_role(str(item.get("role", "")))
        observations.append({
            "card": card,
            "run_id": run_id,
            "build_id": build_id,
            "role": role,
            "phase": str(item.get("phase", "commitment") or "commitment"),
            "evidence": str(item.get("evidence", "") or item.get("insight", "")),
            "confidence": confidence,
            "timestamp": timestamp,
        })
        seen_cards.add(card)

    if observations:
        return observations

    # Fallback for older/repair responses: convert key_cards into broad roles.
    for item in analysis.get("key_cards", ()) or ():
        if not isinstance(item, dict):
            continue
        card = _canonical_card_name(str(item.get("card", "")))
        if not card or card in seen_cards:
            continue
        role = _canonical_role(str(item.get("role", "")))
        observations.append({
            "card": card,
            "run_id": run_id,
            "build_id": build_id,
            "role": role,
            "phase": "commitment",
            "evidence": str(item.get("insight", "")),
            "confidence": confidence,
            "timestamp": timestamp,
        })
        seen_cards.add(card)

    return observations


def apply_build_roles_to_card_memory(
    observations: list[dict[str, Any]],
    store: CardMemoryStore,
    *,
    character: str,
) -> int:
    """Append build-role observations to CardMemory entries."""
    char = normalize_character(character)
    updated = 0
    for obs in observations:
        card_name = _canonical_card_name(str(obs.get("card", "")))
        if not card_name:
            # role_observations_from_analysis stores card name only in the
            # local key, so callers may add it before applying.
            card_name = _canonical_card_name(str(obs.get("card_name", "")))
        if not card_name:
            continue

        clean_obs = dict(obs)
        clean_obs.pop("card", None)
        clean_obs["card_name"] = card_name
        existing = store.get(char, card_name)
        if existing is None:
            store.put(CardMemory(
                character=char,
                card_name=card_name,
                build_role_observations=(clean_obs,),
            ))
        else:
            merged = existing.build_role_observations + (clean_obs,)
            store.put(replace(existing, build_role_observations=merged))
        updated += 1
    return updated


def format_build_role_hint(memory: CardMemory, allowed_builds: tuple[str, ...] = ()) -> str:
    """Format compact build-role observations for prompt injection."""
    observations = list(memory.build_role_observations)
    if allowed_builds:
        allowed = set(allowed_builds)
        observations = [o for o in observations if o.get("build_id") in allowed]
    if not observations:
        return ""

    primary = observations[-1]
    build_id = str(primary.get("build_id", "")).strip()
    role = str(primary.get("role", "")).strip()
    evidence = str(primary.get("evidence", "")).strip()
    count = len([o for o in observations if o.get("build_id") == build_id and o.get("role") == role])
    prefix = f"{role} for {build_id}" if build_id and role else "build role"
    if count > 1:
        prefix = f"{prefix} ({count} runs)"
    return f"{prefix}: {evidence}" if evidence else prefix
