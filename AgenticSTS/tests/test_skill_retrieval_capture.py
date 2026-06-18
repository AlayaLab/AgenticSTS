"""Task B6: verify injected skill IDs accumulate onto the active CombatTracker.

The helper lives at ``src.agent.loop._record_injected_skills`` and is invoked
from the combat retrieval call site in ``_query_skills``. Each invocation
appends returned skill IDs to the active ``CombatTracker.retrieved_skill_ids``
list. Downstream lifecycle (spec §6.1) reads this list set-wise when
attributing per-combat baseline outcomes.
"""
from __future__ import annotations

from src.memory.short_term import CombatTracker, ShortTermMemory


def test_tracker_accumulates_skill_ids_across_rounds():
    """retrieved_skill_ids is an append-only list — duplicates permitted."""
    t = CombatTracker()
    t.retrieved_skill_ids.extend(["skill_a", "skill_b"])
    t.retrieved_skill_ids.extend(["skill_a", "skill_c"])  # dedup on READ, not write
    assert len(t.retrieved_skill_ids) == 4
    assert "skill_a" in t.retrieved_skill_ids
    assert "skill_c" in t.retrieved_skill_ids
    # set-view for downstream lifecycle
    assert set(t.retrieved_skill_ids) == {"skill_a", "skill_b", "skill_c"}


def test_record_injected_skills_helper_no_active_combat_noop():
    """The helper must be a safe no-op when no combat is active."""
    from src.agent.loop import _record_injected_skills

    stm = ShortTermMemory()
    # No active combat
    _record_injected_skills(stm, ["skill_a"])  # must not raise
    # Nothing to observe — helper is a side-effect no-op


def test_record_injected_skills_helper_appends_to_active_tracker():
    from src.agent.loop import _record_injected_skills

    stm = ShortTermMemory()
    stm.start_combat(
        enemy_names=["Rat"],
        combat_type="monster",
        hp=50,
        deck_size=10,
        relics=[],
        floor=1,
        act=1,
    )
    _record_injected_skills(stm, ["skill_a", "skill_b"])
    _record_injected_skills(stm, ["skill_c"])
    tracker = stm.active_combat_tracker()
    assert tracker is not None
    assert tracker.retrieved_skill_ids == ["skill_a", "skill_b", "skill_c"]


def test_record_injected_skills_helper_empty_input_noop():
    from src.agent.loop import _record_injected_skills

    stm = ShortTermMemory()
    stm.start_combat(
        enemy_names=["Rat"],
        combat_type="monster",
        hp=50,
        deck_size=10,
        relics=[],
        floor=1,
        act=1,
    )
    _record_injected_skills(stm, [])  # empty list: safe no-op
    tracker = stm.active_combat_tracker()
    assert tracker is not None
    assert tracker.retrieved_skill_ids == []


def test_record_injected_skills_helper_none_short_term_noop():
    """Helper must tolerate a None short-term reference — never raise."""
    from src.agent.loop import _record_injected_skills

    _record_injected_skills(None, ["skill_a"])  # must not raise
