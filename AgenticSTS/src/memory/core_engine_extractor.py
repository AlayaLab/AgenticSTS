"""Postrun core-engine writers and retrieval helpers.

Identifies winning-deck core engines via Turn 2 of the postrun
combat-trace pipeline (see ``card_note_updater.py``) and writes
structured observations back to each contributing card's CardMemory.

Public surface:
- ``find_final_boss_combat(episodes, run_id)`` — predicate used by the
  Turn 2 caller to gate on Act 3 boss victory.
- ``apply_to_card_memory(result, store, character, run_id)`` — append
  per-card observations from a parsed engine dict.
- ``parse_analysis_response(raw)`` / ``empty_result()`` — JSON parsers
  for engine blocks (now invoked from card_note_updater).
- ``format_core_engine_hint(memory)`` — prompt-side renderer used by
  the retriever to surface observations at deck-decision time.

The prompt-building / LLM-orchestration functions that previously lived
here (build_analysis_prompt, package_round_context,
select_top_damage_rounds, extract_core_engine) were deleted when the
core_engine postrun stage was merged into Turn 2 (see spec
2026-04-25-core-engine-merge-to-turn2-design.md).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import replace

from src.memory.card_memory_store import CardMemoryStore
from src.memory.models_v2 import CardMemory, CombatEpisode

logger = logging.getLogger(__name__)


# ── Cycle 2: Find Act 3 final boss combat ─────────────────────


def find_final_boss_combat(
    episodes: list[CombatEpisode], run_id: str,
) -> CombatEpisode | None:
    """Return the Act 3 boss combat that was won for the given run_id.

    Returns None when: no Act 3 boss combat exists, or the Act 3 boss
    combat was not won, or the run_id has no matching episodes.
    Used as the gating step for postrun core-engine analysis.
    """
    for ep in episodes:
        if ep.run_id != run_id:
            continue
        if ep.act != 3:
            continue
        if ep.combat_type != "boss":
            continue
        if not ep.won:
            continue
        return ep
    return None


def _find_matching_state_snapshot(
    run_log_events: list[dict], *, floor: int, round_num: int,
) -> dict | None:
    """Scan run log for the state snapshot matching this round.

    Matches on floor and combat.round; returns the first match. When
    multiple snapshots match (replans), returns the first chronological
    match — that's the pre-replan state with the hand as first seen.
    """
    for ev in run_log_events:
        if ev.get("event") != "state":
            continue
        if ev.get("floor") != floor:
            continue
        combat = ev.get("combat") or {}
        if combat.get("round") != round_num:
            continue
        # Prefer boss/elite/monster state_types over transient map/etc.
        if ev.get("state_type") not in ("boss", "monster", "elite"):
            continue
        return ev
    return None


# ── Cycle 5: Write core-engine observations to card_memory ────


def apply_to_card_memory(
    result: dict,
    store: CardMemoryStore,
    *,
    character: str,
    run_id: str,
) -> int:
    """Append core/support observations from an extractor result.

    For each name in ``result["core_cards"]``, append an observation with
    ``role="core"`` to that card's CardMemory; similarly for
    ``result["support_cards"]`` with ``role="support"``.

    Creates a new CardMemory entry when the card is not yet in the store.
    Returns the number of cards updated.
    """
    mechanic = (result or {}).get("engine_mechanic", "").strip()
    core_cards = list((result or {}).get("core_cards") or [])
    support_cards = list((result or {}).get("support_cards") or [])
    notes = (result or {}).get("notes", "").strip()

    if not mechanic and not core_cards and not support_cards:
        return 0  # nothing to record

    timestamp = time.time()
    updated = 0

    for name in core_cards:
        if name:
            _append_observation(
                store, character=character, card_name=name,
                role="core", mechanic=mechanic, notes=notes,
                co_cards=[c for c in core_cards if c != name] + support_cards,
                run_id=run_id, timestamp=timestamp,
            )
            updated += 1

    for name in support_cards:
        if name:
            _append_observation(
                store, character=character, card_name=name,
                role="support", mechanic=mechanic, notes=notes,
                co_cards=list(core_cards),
                run_id=run_id, timestamp=timestamp,
            )
            updated += 1

    return updated


def _append_observation(
    store: CardMemoryStore,
    *,
    character: str,
    card_name: str,
    role: str,
    mechanic: str,
    notes: str,
    co_cards: list[str],
    run_id: str,
    timestamp: float,
) -> None:
    """Append a single core-engine observation to a card's memory entry.

    If no entry exists, create one. Preserves all existing counters.
    """
    obs: dict = {
        "run_id": run_id,
        "role": role,
        "engine_mechanic": mechanic,
        "notes": notes,
        "co_cards": co_cards,
        "timestamp": timestamp,
    }
    existing = store.get(character, card_name)
    if existing is None:
        new_mem = CardMemory(
            character=character, card_name=card_name,
            core_engine_observations=(obs,),
        )
        store.put(new_mem)
        return
    merged_obs = existing.core_engine_observations + (obs,)
    store.put(replace(existing, core_engine_observations=merged_obs))


def parse_analysis_response(raw: str) -> dict:
    """Parse the LLM's JSON response. Tolerant of code-fence wrapping and
    leading prose — returns empty_result() on failure.

    Public alias: the agent loop calls this directly after awaiting its
    async LLM call.
    """
    text = (raw or "").strip()
    # Strip common code-fence wrapping.
    if text.startswith("```"):
        # drop first line (``` or ```json) and trailing fence
        lines = text.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        text = "\n".join(lines).strip()
    # Fall back to first balanced {} span.
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return empty_result()
        text = text[start : end + 1]
    try:
        obj = json.loads(text)
    except Exception:
        logger.warning("core_engine LLM output not valid JSON: %r", raw[:200])
        return empty_result()
    if not isinstance(obj, dict):
        return empty_result()
    return {
        "engine_mechanic": str(obj.get("engine_mechanic", "") or ""),
        "core_cards": [str(c) for c in (obj.get("core_cards") or []) if c],
        "support_cards": [str(c) for c in (obj.get("support_cards") or []) if c],
        "notes": str(obj.get("notes", "") or ""),
    }


def empty_result() -> dict:
    """Shape of a no-engine-identified result. Safe to pass to
    apply_to_card_memory — it will be a no-op."""
    return {
        "engine_mechanic": "",
        "core_cards": [],
        "support_cards": [],
        "notes": "",
    }


# ── Prompt-injection formatter ───────────────────────────────


def format_core_engine_hint(memory: "CardMemory") -> str:
    """Format a CardMemory's core_engine_observations as a prompt hint.

    Returns an empty string when the memory has no observations.
    Aggregates across multiple past wins so the hint stays compact.

    Example outputs:
      "core of stacking continuous passive debuff damage (1 win); co-played with Prepared, Acrobatics"
      "core in 3 wins of passive damage"
      "support for poison scaling (1 win); co-played with Noxious Fumes"
    """
    obs = list(memory.core_engine_observations)
    if not obs:
        return ""

    # Separate by role. Most-recent role-wise pick wins for mechanic wording.
    core_obs = [o for o in obs if o.get("role") == "core"]
    support_obs = [o for o in obs if o.get("role") == "support"]

    if core_obs:
        primary = core_obs[-1]  # most recent
        mechanic = (primary.get("engine_mechanic") or "").strip()
        count = len(core_obs)
        role_label = "core"
        co = primary.get("co_cards") or []
    elif support_obs:
        primary = support_obs[-1]
        mechanic = (primary.get("engine_mechanic") or "").strip()
        count = len(support_obs)
        role_label = "support for"
        co = primary.get("co_cards") or []
    else:
        return ""

    # Aggregate wording
    if count >= 2:
        count_phrase = f"in {count} wins"
    else:
        count_phrase = "in 1 win"

    if role_label == "core":
        head = f"core {count_phrase}"
    else:
        head = f"support {count_phrase}"

    if mechanic:
        head += f" of {mechanic}"

    if co:
        # Limit to first 3 co-cards to keep hint short
        co_str = ", ".join(str(c) for c in co[:3])
        head += f"; co-played with {co_str}"

    return head
