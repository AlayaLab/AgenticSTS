"""Tests for src.brain.prompts._generated_fmt."""

from __future__ import annotations

import pytest

from src.brain.prompts._generated_fmt import (
    format_generated_cards_inline,
    format_generated_cards_lines,
)
from src.mcp_client.upstream_models import RawGeneratedCardPayload


def _shiv(*, upgraded: bool = False) -> RawGeneratedCardPayload:
    """Token Shiv mirroring the in-game model."""
    return RawGeneratedCardPayload(
        card_id="Shiv",
        name="Shiv",
        upgraded=upgraded,
        card_type="Attack",
        energy_cost=0,
        rules_text="Deal 4 damage. Exhaust." if not upgraded else "Deal 6 damage. Exhaust.",
        keywords=["Exhaust"],
    )


def _soul() -> RawGeneratedCardPayload:
    return RawGeneratedCardPayload(
        card_id="Soul",
        name="Soul",
        upgraded=False,
        card_type="Skill",
        energy_cost=0,
        rules_text="Channel 1 Soul.",
        keywords=[],
    )


def test_lines_empty_returns_empty_list():
    assert format_generated_cards_lines([]) == []


def test_inline_empty_returns_empty_string():
    assert format_generated_cards_inline([]) == ""


def test_lines_single_blade_of_ink_target():
    out = format_generated_cards_lines([_shiv()])
    assert out == [
        "  ↳ generates Shiv (Attack, cost=0, Exhaust): Deal 4 damage. Exhaust."
    ]


def test_lines_upgrade_aware():
    """A `+` marker must show when the generated card is the upgraded variant."""
    out = format_generated_cards_lines([_shiv(upgraded=True)])
    assert out[0].startswith("  ↳ generates Shiv+ (Attack, cost=0, Exhaust):")
    assert "Deal 6 damage" in out[0]


def test_inline_short_form_shiv():
    out = format_generated_cards_inline([_shiv()])
    assert out == " → generates: Shiv (Attack, 0E, Exhaust): Deal 4 damage. Exhaust."


def test_inline_multiple_generates_semicolon_joined():
    out = format_generated_cards_inline([_shiv(), _soul()])
    assert out.startswith(" → generates:")
    assert "Shiv" in out and "Soul" in out
    # Multiple gens are separated by `; ` (not commas, since rules_text may contain commas)
    assert "; " in out


def test_lines_no_keywords_omits_keyword_segment():
    """Cards without keywords should not emit a trailing comma."""
    out = format_generated_cards_lines([_soul()])
    assert out == ["  ↳ generates Soul (Skill, cost=0): Channel 1 Soul."]


def test_lines_no_rules_text_omits_colon_part():
    bare = RawGeneratedCardPayload(
        card_id="X", name="X", card_type="Skill", energy_cost=1, rules_text="", keywords=[]
    )
    out = format_generated_cards_lines([bare])
    assert out == ["  ↳ generates X (Skill, cost=1)"]


@pytest.mark.parametrize("rules_text", ["Deal 4 damage.", "[red]Deal 4[/red] damage."])
def test_lines_strips_bbcode(rules_text: str):
    """Generated card rules_text should have BBCode tags scrubbed."""
    g = RawGeneratedCardPayload(
        card_id="X", name="X", card_type="Attack", energy_cost=0, rules_text=rules_text
    )
    out = format_generated_cards_lines([g])
    assert "[red]" not in out[0]
    assert "[/red]" not in out[0]
    assert "Deal 4" in out[0]
