"""Tests for strategic thread prompt injection."""

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context


def test_strategic_thread_in_output():
    wc = WorkingContext(
        combat_guide_hints=(),
        enemy_pattern_hints=(),
        route_guide_hints=(),
        route_memory_hints=(),
        deck_guide_hints=(),
        deck_memory_hints=(),
        short_term_hints=(
            "- [card_reward] Took Noxious Fumes for scaling",
            "- [shop] Removed Strike for faster cycle",
        ),
    )
    output = format_working_context(wc)
    assert "## Strategic Thread" in output
    assert "Noxious Fumes" in output
    assert "## Current Progress" not in output  # Old header gone
