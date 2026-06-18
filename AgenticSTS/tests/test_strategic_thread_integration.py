"""Integration test: strategic notes flow through STM -> retriever -> prompt."""

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context
from src.memory.short_term import NoteScope, ShortTermMemory


def test_full_strategic_thread_pipeline():
    """Simulate a run where strategic notes accumulate and inject.

    Per-context_type dedup means each context_type slot holds at most one
    note (the latest); the test covers four distinct context_types.
    """
    stm = ShortTermMemory()

    stm.record_strategic_note("card_reward", "Took Noxious Fumes — scaling job solved")
    stm.record_strategic_note("shop", "Removed Strike — cycle time 2.4 turns now")
    stm.record_strategic_note("rest_site", "Upgraded Catalyst+ — doubles poison for boss")
    stm.record_strategic_note("map", "Elite path — need relic, HP 60/72 safe")

    # Get thread for prompt — no current_context, so triggers don't filter
    thread = stm.get_strategic_thread(max_entries=5)

    assert "Noxious Fumes" in thread
    assert "Strike" in thread
    assert "Catalyst" in thread
    assert "Elite" in thread

    wc = WorkingContext(
        combat_guide_hints=("Guide: Poison build works well against Kin Priest",),
        enemy_pattern_hints=(),
        route_guide_hints=(),
        route_memory_hints=(),
        deck_guide_hints=(),
        deck_memory_hints=(),
        short_term_hints=(thread,),
    )

    output = format_working_context(wc)

    assert "## Strategic Thread" in output
    assert "Noxious Fumes" in output
    assert "## Combat Guide" in output


def test_strategic_thread_survives_reset():
    """Thread resets between runs."""
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Going aggressive")
    assert stm.get_strategic_thread() != ""

    stm.reset_run()
    assert stm.get_strategic_thread() == ""


def test_scoped_notes_lifecycle():
    """Simulate a run with scoped notes: turn/combat expire, run persists.

    Distinct context_types are used so the per-context_type strong dedup
    doesn't fold these into a single slot — the test exercises scope-based
    expiry, not dedup semantics.
    """
    stm = ShortTermMemory()

    # Run-level note (deck-building decision)
    stm.record_strategic_note(
        "card_reward", "Deck needs AoE — took Dagger Spray",
        scope=NoteScope.RUN, triggers=("deck_building",),
    )
    # Combat-level note (use a different context_type to survive dedup)
    stm.record_strategic_note(
        "monster", "Focus poison on beetle",
        scope=NoteScope.COMBAT, triggers=("combat",),
    )
    # Turn-level note (yet another context_type)
    stm.record_strategic_note(
        "elite", "Block the 15 incoming this turn",
        scope=NoteScope.TURN, triggers=("combat",),
    )

    # All 3 visible in unfiltered
    assert "AoE" in stm.get_strategic_thread(max_entries=10)
    assert "beetle" in stm.get_strategic_thread(max_entries=10)
    assert "Block the 15" in stm.get_strategic_thread(max_entries=10)

    # Turn expires at round start
    stm.expire_turn_notes()
    assert "Block the 15" not in stm.get_strategic_thread(max_entries=10)
    assert "beetle" in stm.get_strategic_thread(max_entries=10)

    # Combat expires at combat end
    stm.expire_combat_notes()
    assert "beetle" not in stm.get_strategic_thread(max_entries=10)
    assert "AoE" in stm.get_strategic_thread(max_entries=10)

    # Run-level note only visible in matching context
    deck_thread = stm.get_strategic_thread(max_entries=10, current_context="card_reward")
    assert "AoE" in deck_thread
    combat_thread = stm.get_strategic_thread(max_entries=10, current_context="monster")
    assert "AoE" not in combat_thread
