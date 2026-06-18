"""Tests for ShortTermMemory strategic thread feature."""

from src.memory.short_term import NoteScope, ShortTermMemory


def test_record_and_get_strategic_notes():
    stm = ShortTermMemory()
    stm.record_strategic_note("card_reward", "Took Noxious Fumes — scaling job solved")
    stm.record_strategic_note("shop", "Removed Strike — faster cycle time")

    thread = stm.get_strategic_thread(max_entries=5)
    assert "Noxious Fumes" in thread
    assert "Strike" in thread
    assert "[card_reward]" in thread
    assert "[shop]" in thread


def test_json_style_strategic_note_is_normalized_to_prose():
    stm = ShortTermMemory()
    stm.record_strategic_note(
        "card_reward",
        (
            '{"phase":"committed","engine_mechanic":"poison stalling with strong draw",'
            '"core_pieces":["Noxious Fumes","Bouncing Flask","Runic Pyramid"],'
            '"needs":"block scaling or dexterity","avoid":"off-plan attacks"}'
        ),
    )

    thread = stm.get_strategic_thread(max_entries=5)
    assert "Committed plan: poison stalling with strong draw" in thread
    assert "via Noxious Fumes, Bouncing Flask, Runic Pyramid" in thread
    assert "Needs block scaling or dexterity." in thread
    assert "Avoid off-plan attacks." in thread
    assert '"phase"' not in thread
    assert "engine_mechanic" not in thread


def test_strategic_thread_max_entries():
    stm = ShortTermMemory()
    # Distinct context_types so per-context_type dedup doesn't collapse them.
    for i in range(20):
        stm.record_strategic_note(f"ctx{i}", f"Note {i}")

    # Internal storage capped at 15
    thread = stm.get_strategic_thread(max_entries=5)
    assert "Note 19" in thread
    assert "Note 15" in thread
    assert "Note 4" not in thread  # Trimmed from storage


def test_strategic_thread_empty():
    stm = ShortTermMemory()
    assert stm.get_strategic_thread() == ""


def test_reset_clears_strategic_thread():
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Some note")
    stm.reset_run()
    assert stm.get_strategic_thread() == ""


def test_get_deck_identity_empty():
    stm = ShortTermMemory()
    assert stm.deck_identity == ""


def test_set_deck_identity():
    stm = ShortTermMemory()
    stm.deck_identity = "poison scaling via Noxious Fumes + Catalyst"
    assert stm.deck_identity == "poison scaling via Noxious Fumes + Catalyst"


def test_record_scoped_note():
    stm = ShortTermMemory()
    stm.record_strategic_note(
        "card_reward", "Need AoE for Act 2",
        scope=NoteScope.RUN, triggers=("deck_building",),
    )
    stm.record_strategic_note(
        "shop", "Save gold for remove",
        scope=NoteScope.COMBAT, triggers=("routing",),
    )
    thread = stm.get_strategic_thread(max_entries=10)
    assert "AoE" in thread
    assert "gold" in thread


def test_expire_turn_notes():
    stm = ShortTermMemory()
    # Distinct context_types to avoid per-context_type dedup interference
    # — this test exercises scope-based expiry, not dedup semantics.
    stm.record_strategic_note("map", "Run-level note", scope=NoteScope.RUN)
    stm.record_strategic_note("shop", "Combat note", scope=NoteScope.COMBAT)
    stm.record_strategic_note("card_reward", "Turn note", scope=NoteScope.TURN)
    stm.expire_turn_notes()
    thread = stm.get_strategic_thread(max_entries=10)
    assert "Run-level" in thread
    assert "Combat note" in thread
    assert "Turn note" not in thread


def test_expire_combat_notes():
    stm = ShortTermMemory()
    stm.record_strategic_note("map", "Run-level note", scope=NoteScope.RUN)
    stm.record_strategic_note("shop", "Combat note", scope=NoteScope.COMBAT)
    stm.record_strategic_note("card_reward", "Turn note", scope=NoteScope.TURN)
    stm.expire_combat_notes()
    thread = stm.get_strategic_thread(max_entries=10)
    assert "Run-level" in thread
    assert "Combat note" not in thread
    assert "Turn note" not in thread


def test_filter_by_trigger_context():
    stm = ShortTermMemory()
    stm.record_strategic_note(
        "card_reward", "Deck needs poison",
        triggers=("deck_building",),
    )
    stm.record_strategic_note(
        "map", "Take elite path",
        triggers=("routing",),
    )
    stm.record_strategic_note(
        "shop", "Universal strategy",
        triggers=("all",),
    )

    deck_thread = stm.get_strategic_thread(max_entries=10, current_context="card_reward")
    assert "poison" in deck_thread
    assert "Universal" in deck_thread
    assert "elite path" not in deck_thread

    map_thread = stm.get_strategic_thread(max_entries=10, current_context="map")
    assert "elite path" in map_thread
    assert "Universal" in map_thread
    assert "poison" not in map_thread

    all_thread = stm.get_strategic_thread(max_entries=10, current_context="")
    assert "poison" in all_thread
    assert "elite path" in all_thread
    assert "Universal" in all_thread


def test_scoped_note_capacity_15():
    stm = ShortTermMemory()
    for i in range(20):
        stm.record_strategic_note(f"ctx{i}", f"Note {i}")
    thread = stm.get_strategic_thread(max_entries=15)
    assert "Note 19" in thread
    assert "Note 5" in thread
    assert "Note 4" not in thread


def test_record_strategic_note_dedups_identical_text():
    stm = ShortTermMemory()
    note = (
        "Foundation: Relying on Neow's Fury for early burst damage. "
        "Need to find scaling, AoE damage, and better mitigation."
    )
    for _ in range(5):
        stm.record_strategic_note("event", note)

    thread = stm.get_strategic_thread(max_entries=10)
    assert thread.count(note) == 1


def test_record_strategic_note_per_context_type_dedup():
    """Per-context_type strong dedup (2d): each context_type slot holds at
    most the latest note. Earlier notes for the same context_type are
    paraphrases of the same intent and just clutter the rendered Strategic
    Thread.
    """
    stm = ShortTermMemory()
    stm.record_strategic_note("event", "Take Noxious Fumes")
    stm.record_strategic_note("event", "Skip the elite this act")
    stm.record_strategic_note("event", "Aim for shop on F8")

    thread = stm.get_strategic_thread(max_entries=10)
    assert "Noxious Fumes" not in thread
    assert "Skip the elite" not in thread
    assert "shop on F8" in thread
    assert thread.count("- [event]") == 1


def test_record_strategic_note_distinct_context_types_kept():
    stm = ShortTermMemory()
    stm.record_strategic_note("event", "Foundation plan")
    stm.record_strategic_note("map", "Take elite path")
    stm.record_strategic_note("event", "Foundation plan v2")  # supersedes prior event

    thread = stm.get_strategic_thread(max_entries=10)
    lines = thread.split("\n")
    assert len(lines) == 2
    assert lines[-1].endswith("Foundation plan v2")
    assert lines[0].endswith("Take elite path")


def test_auto_infer_triggers_from_context_type():
    """Auto-inference (1c): default triggers=("all",) is replaced with
    a context_type-appropriate trigger set so get_strategic_thread actually
    filters by relevance.
    """
    stm = ShortTermMemory()
    stm.record_strategic_note("monster", "Combat note")
    stm.record_strategic_note("card_reward", "Deck note")
    stm.record_strategic_note("rest_site", "Rest note")
    stm.record_strategic_note("map", "Map note")

    # In a combat decision (state_type=monster), map notes should be filtered
    # out (map → triggers=("routing",) which doesn't match monster), but
    # rest_site/card_reward/monster all have "combat" trigger and pass.
    thread = stm.get_strategic_thread(max_entries=10, current_context="monster")
    assert "Combat note" in thread
    assert "Deck note" in thread
    assert "Rest note" in thread
    assert "Map note" not in thread


def test_trigger_filtering_drops_combat_notes_in_routing():
    stm = ShortTermMemory()
    stm.record_strategic_note("monster", "Combat-only note")
    stm.record_strategic_note("map", "Routing-only note")
    stm.record_strategic_note("rest_site", "Cross-cutting rest note")

    # In a map decision, the pure combat note should be filtered out.
    thread = stm.get_strategic_thread(max_entries=10, current_context="map")
    assert "Combat-only" not in thread
    assert "Routing-only" in thread
    assert "Cross-cutting rest" in thread


def test_explicit_all_triggers_force_show():
    """Auto-inference only fires when ``triggers`` is omitted (None default).
    Callers passing explicit ``("all",)`` keep the legacy "show during every
    state" behavior.
    """
    stm = ShortTermMemory()
    # Auto-infer path: monster context_type → triggers=("combat",), so this
    # does NOT show during a map decision.
    stm.record_strategic_note("monster", "Auto-inferred combat note")
    # Explicit ("all",) opts out of auto-inference.
    stm.record_strategic_note(
        "elite", "Explicit force-show note", triggers=("all",),
    )
    # Explicit narrow triggers retained as-is.
    stm.record_strategic_note(
        "boss", "Routing-tagged combat note", triggers=("routing",),
    )

    map_thread = stm.get_strategic_thread(max_entries=10, current_context="map")
    assert "Auto-inferred combat note" not in map_thread
    assert "Explicit force-show note" in map_thread
    assert "Routing-tagged combat note" in map_thread
