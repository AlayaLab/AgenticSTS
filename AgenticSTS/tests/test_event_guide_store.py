"""Tests for EventGuide storage in GuideStore."""
import tempfile
from pathlib import Path

from src.memory.event_models import EventGuide


def test_event_guide_set_and_get():
    """Store and retrieve an event guide."""
    from src.memory.guide_store import GuideStore

    store = GuideStore()
    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Alchemical Coffer is best when potion slots are low.",
        episode_count=5,
        confidence=0.7,
    )
    store.set_event_guide(guide)
    result = store.get_event_guide("OROBAS", "the silent")
    assert result is not None
    assert result.guide_text.startswith("Alchemical Coffer")


def test_event_guide_persistence():
    """Event guides survive save/load."""
    from src.memory.guide_store import GuideStore

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "guides.json"
        store = GuideStore()
        store.set_event_guide(EventGuide(
            event_id="OROBAS", character="the silent",
            guide_text="Test guide", episode_count=3, confidence=0.6,
        ))
        store.save(path)

        loaded = GuideStore.load(path)
        result = loaded.get_event_guide("OROBAS", "the silent")
        assert result is not None
        assert result.guide_text == "Test guide"


def test_event_guide_in_stats():
    """Stats include event_guides count."""
    from src.memory.guide_store import GuideStore

    store = GuideStore()
    store.set_event_guide(EventGuide(event_id="TEST", character="silent"))
    s = store.stats()
    assert "event_guides" in s
    assert s["event_guides"] == 1
