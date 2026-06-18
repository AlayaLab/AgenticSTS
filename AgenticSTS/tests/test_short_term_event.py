"""Tests for EventTracker in ShortTermMemory."""
from src.memory.short_term import ShortTermMemory


def test_event_tracking_lifecycle():
    """start_event → end_event → completed_events records the event."""
    stm = ShortTermMemory()
    stm.start_event(
        event_id="OROBAS",
        event_title="Orobas",
        floor=18,
        act=2,
        hp=57,
        gold=110,
        deck=["Strike", "Defend", "Neutralize++"],
    )
    stm.end_event(
        chosen_index=1,
        option_text="Alchemical Coffer",
        hp_after=57,
        gold_after=110,
        all_options=["Gear Glass", "Alchemical Coffer", "Archaic Tooth"],
        cards_gained=[],
        cards_lost=[],
        relics_gained=[],
        potions_gained=["Fire Potion", "Block Potion"],
    )
    assert len(stm.completed_events) == 1
    ev = stm.completed_events[0]
    assert ev.event_id == "OROBAS"
    assert ev.chosen_option_index == 1
    assert ev.hp_before == 57
    assert ev.potions_gained == ["Fire Potion", "Block Potion"]


def test_reset_run_clears_events():
    """reset_run clears completed events."""
    stm = ShortTermMemory()
    stm.start_event("TEST", "Test", 5, 1, 50, 100, [])
    stm.end_event(0, "Option A", 50, 100, ["Option A"], [], [], [], [])
    assert len(stm.completed_events) == 1
    stm.reset_run()
    assert len(stm.completed_events) == 0


def test_multiple_events_tracked():
    """Multiple events in a single run are all tracked."""
    stm = ShortTermMemory()
    for i in range(3):
        stm.start_event(f"EVT_{i}", f"Event {i}", i + 5, 1, 50, 100, [])
        stm.end_event(0, "Option A", 48, 95, ["Option A"], [], [], [], [])
    assert len(stm.completed_events) == 3
    assert stm.completed_events[2].event_id == "EVT_2"


def test_cancel_event_discards_current_without_persist():
    """cancel_event clears the current tracker without appending to completed."""
    from src.memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    stm.start_event(
        event_id="X", event_title="x", floor=1, act=1,
        hp=50, gold=100, deck=[],
    )
    assert stm.current_event is not None
    stm.cancel_event()
    assert stm.current_event is None
    assert stm.completed_events == []


def test_cancel_event_no_current_is_noop():
    from src.memory.short_term import ShortTermMemory

    stm = ShortTermMemory()
    # No start_event called — cancel is a no-op
    stm.cancel_event()
    assert stm.current_event is None
