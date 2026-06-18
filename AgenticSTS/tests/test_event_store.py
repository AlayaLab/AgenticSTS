"""Tests for EventMemoryStore JSONL persistence."""
import tempfile
from pathlib import Path

from src.memory.event_models import EventMemory


def _make_event(event_id="OROBAS", character="the silent", act=2, floor=18,
                run_id="run_1", chosen=1, option_text="Alchemical Coffer"):
    return EventMemory(
        run_id=run_id,
        floor=floor,
        act=act,
        event_id=event_id,
        event_title=event_id.title(),
        character=character,
        chosen_option_index=chosen,
        chosen_option_text=option_text,
        all_options=("Option A", "Option B", "Option C"),
    )


def test_add_and_query():
    """Store an event and retrieve it by event_id."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event())
    results = store.query(event_id="OROBAS", character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "OROBAS"


def test_query_filters_character():
    """When event_id is given, character ranks matching records first (not a hard filter)."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event(character="the silent"))
    store.add(_make_event(character="the ironclad"))
    results = store.query(event_id="OROBAS", character="the silent")
    # Both records match the event_id; character is a ranking signal, not a hard filter
    assert len(results) == 2
    assert results[0].character == "the silent"


def test_persistence_roundtrip():
    """Save and load preserves all data."""
    from src.memory.event_store import EventMemoryStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "events.jsonl"
        store = EventMemoryStore()
        store.add(_make_event())
        store.add(_make_event(event_id="SHRINE", floor=10))
        store.save(path)

        loaded = EventMemoryStore.load(path)
        assert loaded.count == 2
        results = loaded.query(event_id="OROBAS")
        assert len(results) == 1


def test_get_all():
    """get_all returns all stored memories."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event())
    store.add(_make_event(event_id="SHRINE"))
    all_mems = store.get_all()
    assert len(all_mems) == 2


def test_query_event_id_priority_over_character():
    """event_id match should return results even when character is empty."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event(event_id="SUNKEN_STATUE", character="", floor=5))
    results = store.query(event_id="SUNKEN_STATUE", character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "SUNKEN_STATUE"


def test_query_same_character_ranked_first():
    """Same-character results should rank above empty-character results."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    old = _make_event(event_id="SUNKEN_STATUE", character="the silent", floor=3)
    empty = _make_event(event_id="SUNKEN_STATUE", character="", floor=8)
    store.add(old)
    store.add(empty)
    results = store.query(event_id="SUNKEN_STATUE", character="the silent", limit=5)
    assert len(results) == 2
    assert results[0].character == "the silent"


def test_query_no_event_id_still_filters_character():
    """When no event_id given, character filter still applies as before."""
    from src.memory.event_store import EventMemoryStore

    store = EventMemoryStore()
    store.add(_make_event(event_id="A", character="the silent"))
    store.add(_make_event(event_id="B", character="the ironclad"))
    results = store.query(character="the silent")
    assert len(results) == 1
    assert results[0].event_id == "A"
