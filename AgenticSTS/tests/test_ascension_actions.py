"""Tests for ascension action builders."""
from src.mcp_client import actions as act


def test_increase_ascension():
    result = act.increase_ascension()
    assert result == {"action": "increase_ascension"}


def test_decrease_ascension():
    result = act.decrease_ascension()
    assert result == {"action": "decrease_ascension"}
