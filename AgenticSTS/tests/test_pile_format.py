"""Tests for _pile_fmt.py — pile formatting helpers for combat prompts."""

from __future__ import annotations

from src.brain.prompts._pile_fmt import (
    extract_card_name,
    format_pile_compact,
    format_pile_detailed,
    format_piles_section,
)
from src.mcp_client.upstream_models import AgentViewCardStackItem

# ---------------------------------------------------------------------------
# extract_card_name
# ---------------------------------------------------------------------------


class TestExtractCardName:
    def test_basic_card(self):
        assert extract_card_name("Strike [1费]：Deal 6 damage.") == "Strike"

    def test_card_with_copy_marker(self):
        assert extract_card_name("Defend*3 [1费]：Gain 5 Block.") == "Defend"

    def test_upgraded_card(self):
        assert extract_card_name("Strike+ [1费]：Deal 9 damage.") == "Strike+"

    def test_upgraded_card_with_copy_marker(self):
        assert extract_card_name("Bash+*2 [2费]：Deal 10 damage.") == "Bash+"

    def test_zero_cost_card(self):
        assert extract_card_name("Neutralize [0费]：Deal 3 damage. Apply 1 Weak.") == "Neutralize"

    def test_multi_word_card_name(self):
        assert extract_card_name("Ice Lance [1费|★1]：Channel 3 Frost.") == "Ice Lance"

    def test_card_with_star_cost(self):
        assert extract_card_name("Particle Wall [2费|★1]：Gain 12 Block.") == "Particle Wall"

    def test_empty_string(self):
        assert extract_card_name("") == ""

    def test_no_bracket(self):
        # Edge case: line without cost bracket
        assert extract_card_name("Unknown Card") == "Unknown Card"

    def test_x_cost_card(self):
        assert (
            extract_card_name("Whirlwind [X费]：Deal 5 damage to ALL enemies X times.")
            == "Whirlwind"
        )

    def test_copy_marker_single_digit(self):
        assert extract_card_name("Defend*1 [1费]：Gain 5 Block.") == "Defend"

    def test_copy_marker_double_digit(self):
        assert extract_card_name("Strike*12 [1费]：Deal 6 damage.") == "Strike"


# ---------------------------------------------------------------------------
# format_pile_compact
# ---------------------------------------------------------------------------


def _make_item(line: str) -> AgentViewCardStackItem:
    """Helper to create an AgentViewCardStackItem with a given line."""
    return AgentViewCardStackItem(line=line)


class TestFormatPileCompact:
    def test_empty_pile(self):
        assert format_pile_compact([], "Draw") == ""

    def test_single_card(self):
        items = [_make_item("Bash [2费]：Deal 8 damage. Apply 2 Vulnerable.")]
        result = format_pile_compact(items, "Draw")
        assert result == "Draw (1): Bash"

    def test_multiple_unique_cards(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Bash [2费]：Deal 8 damage."),
        ]
        result = format_pile_compact(items, "Discard")
        assert result == "Discard (3): Strike, Defend, Bash"

    def test_grouped_duplicates(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Bash [2费]：Deal 8 damage."),
            _make_item("Footwork [1费]：Gain 2 Dexterity."),
        ]
        result = format_pile_compact(items, "Draw")
        assert result == "Draw (7): Strike x3, Defend x2, Bash, Footwork"

    def test_preserves_first_seen_order(self):
        items = [
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
        ]
        result = format_pile_compact(items, "Discard")
        assert result == "Discard (3): Defend x2, Strike"

    def test_upgraded_cards_separate(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike+ [1费]：Deal 9 damage."),
        ]
        result = format_pile_compact(items, "Draw")
        assert result == "Draw (2): Strike, Strike+"

    def test_copy_marker_stripped(self):
        items = [
            _make_item("Defend*3 [1费]：Gain 5 Block."),
            _make_item("Strike*3 [1费]：Deal 6 damage."),
        ]
        result = format_pile_compact(items, "Draw")
        assert result == "Draw (2): Defend, Strike"

    def test_items_with_empty_lines(self):
        items = [
            _make_item(""),
            _make_item("Strike [1费]：Deal 6 damage."),
        ]
        result = format_pile_compact(items, "Exhaust")
        assert result == "Exhaust (2): Strike"


# ---------------------------------------------------------------------------
# format_pile_detailed
# ---------------------------------------------------------------------------


class TestFormatPileDetailed:
    def test_empty_pile(self):
        assert format_pile_detailed([], "Draw") == []

    def test_single_card(self):
        items = [_make_item("Bash [2费]：Deal 8 damage. Apply 2 Vulnerable.")]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Bash [2 cost]: Deal 8 damage. Apply 2 Vulnerable.",
        ]

    def test_multiple_unique_cards(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (2):",
            "  - Strike [1 cost]: Deal 6 damage.",
            "  - Defend [1 cost]: Gain 5 Block.",
        ]

    def test_grouped_duplicates_with_count_suffix(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Bash [2费]：Deal 8 damage."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (6):",
            "  - Strike [1 cost]: Deal 6 damage. x3",
            "  - Defend [1 cost]: Gain 5 Block. x2",
            "  - Bash [2 cost]: Deal 8 damage.",
        ]

    def test_preserves_first_seen_order(self):
        items = [
            _make_item("Defend [1费]：Gain 5 Block."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (3):",
            "  - Defend [1 cost]: Gain 5 Block. x2",
            "  - Strike [1 cost]: Deal 6 damage.",
        ]

    def test_upgraded_cards_are_distinct(self):
        items = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike+ [1费]：Deal 9 damage."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (2):",
            "  - Strike [1 cost]: Deal 6 damage.",
            "  - Strike+ [1 cost]: Deal 9 damage.",
        ]

    def test_copy_marker_stripped_from_display(self):
        items = [
            _make_item("Defend*3 [1费]：Gain 5 Block."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Defend [1 cost]: Gain 5 Block.",
        ]

    def test_items_with_empty_lines_skipped(self):
        items = [
            _make_item(""),
            _make_item("Strike [1费]：Deal 6 damage."),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (2):",
            "  - Strike [1 cost]: Deal 6 damage.",
        ]

    def test_single_mod_shown_inline(self):
        items = [
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge"],
            ),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Strike [1 cost]: Deal 6 damage. [Mods: Keen Edge]",
        ]

    def test_multiple_mods_joined(self):
        items = [
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge", "Sharpened"],
            ),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Strike [1 cost]: Deal 6 damage. [Mods: Keen Edge, Sharpened]",
        ]

    def test_same_name_different_mods_split(self):
        items = [
            AgentViewCardStackItem(line="Strike [1费]：Deal 6 damage.", mods=[]),
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge"],
            ),
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge"],
            ),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (3):",
            "  - Strike [1 cost]: Deal 6 damage.",
            "  - Strike [1 cost]: Deal 6 damage. [Mods: Keen Edge] x2",
        ]

    def test_mods_order_preserved_across_dedup(self):
        items = [
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge", "Sharpened"],
            ),
            AgentViewCardStackItem(
                line="Strike [1费]：Deal 6 damage.",
                mods=["Keen Edge", "Sharpened"],
            ),
        ]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (2):",
            "  - Strike [1 cost]: Deal 6 damage. [Mods: Keen Edge, Sharpened] x2",
        ]

    def test_x_cost_card_translated(self):
        items = [_make_item("Whirlwind [X费]：Deal 5 damage to ALL enemies X times.")]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Whirlwind [X cost]: Deal 5 damage to ALL enemies X times.",
        ]

    def test_star_enchant_marker_kept(self):
        # The "★N" enchantment marker inside the cost bracket survives — we
        # only translate "费" → " cost"; the star is universal.
        items = [_make_item("Ice Lance [1费|★1]：Channel 3 Frost.")]
        result = format_pile_detailed(items, "Draw")
        assert result == [
            "Draw (1):",
            "  - Ice Lance [1 cost|★1]: Channel 3 Frost.",
        ]

    def test_no_chinese_characters_in_output(self):
        items = [_make_item("Bash [2费]：Deal 8 damage. Apply 2 Vulnerable.")]
        result = format_pile_detailed(items, "Draw")
        joined = "\n".join(result)
        assert "费" not in joined
        assert "：" not in joined


# ---------------------------------------------------------------------------
# format_piles_section
# ---------------------------------------------------------------------------


class TestFormatPilesSection:
    def test_all_empty(self):
        assert format_piles_section([], [], []) == []

    def test_draw_only(self):
        draw = [_make_item("Strike [1费]：Deal 6 damage.")]
        result = format_piles_section(draw, [], [])
        assert result == ["", "## Piles", "Draw (1): Strike"]

    def test_all_three_piles(self):
        draw = [
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Strike [1费]：Deal 6 damage."),
            _make_item("Defend [1费]：Gain 5 Block."),
        ]
        discard = [_make_item("Bash [2费]：Deal 8 damage.")]
        exhaust = [_make_item("Neutralize [0费]：Deal 3 damage.")]
        result = format_piles_section(draw, discard, exhaust)
        assert len(result) == 5  # header blank + "## Piles" + 3 pile lines
        assert result[0] == ""
        assert result[1] == "## Piles"
        assert result[2] == "Draw (3): Strike x2, Defend"
        assert result[3] == "Discard (1): Bash"
        assert result[4] == "Exhaust (1): Neutralize"

    def test_only_exhaust(self):
        exhaust = [_make_item("Shiv [0费]：Deal 4 damage. Exhaust.")]
        result = format_piles_section([], [], exhaust)
        assert result == ["", "## Piles", "Exhaust (1): Shiv"]

    def test_empty_piles_omitted(self):
        draw = [_make_item("Strike [1费]：Deal 6 damage.")]
        exhaust = [_make_item("Shiv [0费]：Deal 4 damage.")]
        result = format_piles_section(draw, [], exhaust)
        assert len(result) == 4  # header blank + "## Piles" + 2 pile lines
        assert "Discard" not in " ".join(result)
