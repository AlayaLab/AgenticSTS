"""Tests for event-specific memory retrieval."""
from unittest.mock import MagicMock

from src.memory.retriever import _classify_decision_type


def test_event_classified_separately():
    """Events are classified as 'event', not 'rest_event'."""
    gs = MagicMock()
    gs.is_combat = False
    gs.is_map = False
    gs.state_type = "event"
    assert _classify_decision_type(gs) == "event"


def test_rest_classified_separately():
    """Rest sites are classified as 'rest', not 'rest_event'."""
    gs = MagicMock()
    gs.is_combat = False
    gs.is_map = False
    gs.state_type = "rest_site"
    assert _classify_decision_type(gs) == "rest"
