"""Tests for first-encounter bypass in combat guide consolidation.

Spec: docs/superpowers/specs/2026-04-28-first-encounter-guide-write-design.md
"""
from __future__ import annotations

from unittest.mock import MagicMock

from src.memory.guide_consolidator import _select_combat_keys_for_refresh
from src.memory.models_v2 import CombatEpisode


def _ep(*, run_id, enemy_key, character, combat_type, act,
        is_aborted=False, hp_before=80, hp_after=60, won=True):
    """is_aborted on CombatEpisode is a property derived from terminal_reason."""
    return CombatEpisode(
        episode_id=f"ep-{enemy_key}-{run_id}",
        run_id=run_id,
        character=character,
        enemy_key=enemy_key,
        combat_type=combat_type,
        act=act,
        floor=1,
        hp_before=hp_before,
        hp_after=hp_after,
        won=won,
        rounds=(),
        terminal_reason="abort" if is_aborted else ("win" if won else "loss"),
    )


def test_select_without_guide_store_preserves_legacy_behavior():
    """Calling without guide_store kwarg must produce the exact historical
    selection (boss + elite + worst small monster per act)."""
    episodes = [
        _ep(run_id="r1", enemy_key="boss_a", character="Silent",
            combat_type="boss", act=1),
        _ep(run_id="r1", enemy_key="elite_a", character="Silent",
            combat_type="elite", act=1),
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),  # worst
    ]
    selected = _select_combat_keys_for_refresh(episodes, "r1")
    assert ("boss a", "the silent") in selected
    assert ("elite a", "the silent") in selected
    assert ("slug b", "the silent") in selected   # worst-of-act
    assert ("slug a", "the silent") not in selected  # filtered out


def test_select_with_empty_guide_store_admits_all_non_aborted_keys():
    """guide_store with no guides for any key must force ALL non-aborted
    keys from current run into the refresh set, even non-worst monsters."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)

    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug a", "the silent") in selected
    assert ("slug b", "the silent") in selected


def test_select_with_existing_guide_skips_first_encounter_bypass():
    """Keys that already have a guide do NOT get added by first-encounter
    logic — they fall back to the legacy selection rules."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
        _ep(run_id="r1", enemy_key="slug_b", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=50),
    ]
    existing_guide = MagicMock()
    guide_store = MagicMock()
    # slug_a has a guide; slug_b does not
    guide_store.get_combat_guide = MagicMock(
        side_effect=lambda key, char: existing_guide if key == "slug a" else None
    )

    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug b", "the silent") in selected   # bypass triggers (no guide)
    # slug_a: not worst-of-act AND has guide → NOT in selected
    assert ("slug a", "the silent") not in selected


def test_select_excludes_aborted_episodes_from_bypass():
    """Aborted-only keys must NOT trigger the first-encounter bypass."""
    episodes = [
        _ep(run_id="r1", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, is_aborted=True),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug a", "the silent") not in selected


def test_select_ignores_other_run_episodes_in_bypass():
    """Episodes from other runs must not trigger first-encounter bypass."""
    episodes = [
        _ep(run_id="r0", enemy_key="slug_a", character="Silent",
            combat_type="monster", act=1, hp_before=80, hp_after=70),
    ]
    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    selected = _select_combat_keys_for_refresh(
        episodes, "r1", guide_store=guide_store,
    )
    assert ("slug a", "the silent") not in selected


# ── Route guide first-encounter (Task 4) ───────────────────────


import asyncio
from unittest.mock import AsyncMock, patch

from src.memory.models_v2 import RouteMemory


def _route_memory(*, run_id, act, character, boss_result="won"):
    """Minimal RouteMemory. boss_result must NOT be 'aborted' or memory
    is filtered out upstream of the consolidation loop."""
    return RouteMemory(
        memory_id=f"rm-{act}-{run_id}",
        run_id=run_id,
        character=character,
        act=act,
        nodes=(),
        boss_result=boss_result,
    )


def test_route_first_encounter_bypass_triggers_llm():
    """1 route memory + no existing guide → LLM call fires for routes."""
    from src.memory.guide_consolidator import consolidate_guides

    memory_manager = MagicMock()
    memory_manager.v2_enabled = True

    combat_store = MagicMock()
    combat_store.get_all = MagicMock(return_value=[])
    memory_manager.combat_store = combat_store

    route_store = MagicMock()
    route_store.get_all = MagicMock(return_value=[
        _route_memory(run_id="r1", act=1, character="Silent"),
    ])
    memory_manager.route_store = route_store

    # Other stores empty so only route path runs
    memory_manager.card_build_store = MagicMock()
    memory_manager.card_build_store.get_all = MagicMock(return_value=[])
    memory_manager.event_store = MagicMock()
    memory_manager.event_store.get_all = MagicMock(return_value=[])

    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    guide_store.get_route_guide = MagicMock(return_value=None)
    guide_store.get_deck_guide = MagicMock(return_value=None)
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_route_guide = MagicMock()
    memory_manager.guide_store = guide_store

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch("src.brain.llm_caller.call_raw", fake_llm):
        with patch(
            "src.memory.guide_consolidator.parse_route_guide_response",
            return_value=None,
        ):
            asyncio.run(consolidate_guides(
                memory_manager, current_run_id="r1",
            ))

    # At least one llm call (route guide) — combat/event/deck stores are empty
    assert fake_llm.await_count >= 1


# ── Deck guide first-encounter (Task 5) ────────────────────────


from src.memory.models_v2 import CardBuildMemory


def _build_memory(*, run_id, character, archetype):
    """Minimal CardBuildMemory."""
    return CardBuildMemory(
        memory_id=f"bm-{archetype}-{run_id}",
        run_id=run_id,
        character=character,
        archetype=archetype,
    )


def test_deck_first_encounter_bypass_triggers_llm():
    """1 deck build + no existing guide → LLM call fires for deck guide."""
    from src.memory.guide_consolidator import consolidate_guides

    memory_manager = MagicMock()
    memory_manager.v2_enabled = True
    memory_manager.combat_store = MagicMock()
    memory_manager.combat_store.get_all = MagicMock(return_value=[])
    memory_manager.route_store = MagicMock()
    memory_manager.route_store.get_all = MagicMock(return_value=[])
    memory_manager.event_store = MagicMock()
    memory_manager.event_store.get_all = MagicMock(return_value=[])

    card_build_store = MagicMock()
    card_build_store.get_all = MagicMock(return_value=[
        _build_memory(run_id="r1", character="Silent", archetype="poison"),
    ])
    memory_manager.card_build_store = card_build_store

    guide_store = MagicMock()
    guide_store.get_combat_guide = MagicMock(return_value=None)
    guide_store.get_route_guide = MagicMock(return_value=None)
    guide_store.get_deck_guide = MagicMock(return_value=None)
    guide_store.get_event_guide = MagicMock(return_value=None)
    guide_store.set_deck_guide = MagicMock()
    memory_manager.guide_store = guide_store

    fake_llm = AsyncMock(return_value=("<empty>", 0.0, {}))
    with patch("src.brain.llm_caller.call_raw", fake_llm):
        with patch(
            "src.memory.guide_consolidator.parse_deck_guide_response",
            return_value=None,
        ):
            with patch(
                "src.memory.guide_consolidator._select_deck_keys_for_refresh",
                return_value={("the silent", "poison")},
            ):
                asyncio.run(consolidate_guides(
                    memory_manager, current_run_id="r1",
                ))

    assert fake_llm.await_count >= 1
