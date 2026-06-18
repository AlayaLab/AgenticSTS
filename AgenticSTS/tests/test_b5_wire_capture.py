"""Task B5: verify the engine wires CombatTracker.record_round_context after a plan is produced.

The capture site lives in src/agent/loop.py (_generate_combat_plan), but the actual
round-context population is factored into a small helper in src/brain/v2_engine.py
(capture_round_context) so it can be unit-tested without mocking the full agent loop.
"""
from __future__ import annotations

from src.memory.short_term import CombatTracker, ShortTermMemory


# ── ShortTermMemory accessor ─────────────────────────────────────────────


def test_active_combat_tracker_accessor_none_when_idle():
    """ShortTermMemory exposes an accessor that returns None before combat starts."""
    stm = ShortTermMemory()
    assert stm.active_combat_tracker() is None


def test_active_combat_tracker_accessor_returns_live_tracker():
    """After start_combat, accessor returns the active tracker; after end_combat, None."""
    stm = ShortTermMemory()
    stm.start_combat(
        enemy_names=["Rat"],
        combat_type="monster",
        hp=60,
        deck_size=10,
        relics=[],
        floor=1,
        act=1,
    )
    tracker = stm.active_combat_tracker()
    assert isinstance(tracker, CombatTracker)
    assert tracker.enemy_names == ["Rat"]
    # Same object as the existing current_combat property
    assert tracker is stm.current_combat

    stm.end_combat(won=True, hp_after=55)
    assert stm.active_combat_tracker() is None


# ── capture_round_context helper ─────────────────────────────────────────


def test_capture_round_context_populates_fields():
    """The capture helper writes all 8 pre-plan fields onto the current round."""
    from src.brain.v2_engine import capture_round_context

    tracker = CombatTracker(enemy_key="Rat", combat_type="monster", enemy_names=["Rat"])
    tracker.start_round(
        round_num=1, energy=3, hp=60,
        enemy_intents=["Attack 8"], hand_cards=["Strike", "Defend"],
    )

    capture_round_context(
        tracker=tracker,
        block_before=0,
        draw_pile_size=5,
        discard_pile_size=2,
        exhaust_pile_size=1,
        usable_potions=["Fire Potion"],
        incoming_damage=8,
        agent_plan=["Strike->0", "Defend->self"],
        llm_call_seq=7,
    )

    r = tracker._current_round
    assert r.block_before == 0
    assert r.draw_pile_size == 5
    assert r.discard_pile_size == 2
    assert r.exhaust_pile_size == 1
    assert r.usable_potions == ["Fire Potion"]
    assert r.incoming_damage == 8
    assert r.agent_plan == ["Strike->0", "Defend->self"]
    assert r.llm_call_seq == 7


def test_capture_round_context_noop_when_tracker_none():
    """Helper is safe when tracker is None — must not raise."""
    from src.brain.v2_engine import capture_round_context

    capture_round_context(
        tracker=None,
        block_before=0,
        draw_pile_size=0,
        discard_pile_size=0,
        exhaust_pile_size=0,
        usable_potions=[],
        incoming_damage=0,
        agent_plan=[],
        llm_call_seq=-1,
    )  # must not raise


def test_capture_round_context_noop_when_no_active_round():
    """Helper is safe when tracker has no active round — must not raise."""
    from src.brain.v2_engine import capture_round_context

    tracker = CombatTracker(enemy_key="Rat", combat_type="monster", enemy_names=["Rat"])
    # Deliberately do NOT call start_round
    capture_round_context(
        tracker=tracker,
        block_before=5,
        draw_pile_size=10,
        discard_pile_size=0,
        exhaust_pile_size=0,
        usable_potions=[],
        incoming_damage=0,
        agent_plan=["Strike->0"],
        llm_call_seq=3,
    )  # must not raise


def test_capture_round_context_swallows_internal_errors():
    """Helper must never crash combat — even if the tracker's method blows up."""
    from src.brain.v2_engine import capture_round_context

    class BrokenTracker:
        def record_round_context(self, **kwargs):
            raise RuntimeError("simulated disk failure")

    # Passing a broken object must not raise
    capture_round_context(
        tracker=BrokenTracker(),
        block_before=0,
        draw_pile_size=0,
        discard_pile_size=0,
        exhaust_pile_size=0,
        usable_potions=[],
        incoming_damage=0,
        agent_plan=[],
        llm_call_seq=-1,
    )
