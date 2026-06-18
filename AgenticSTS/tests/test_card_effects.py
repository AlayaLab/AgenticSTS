"""Tests for regex-based card effect detection."""
from src.brain.card_effects import detect_discard_count, detect_draws_cards


class TestDetectDiscardCount:
    def test_discard_1(self):
        assert detect_discard_count("Gain 11 Block. Discard 1 card.") == 1

    def test_discard_2(self):
        assert detect_discard_count("Discard 2 cards. Add 2 Shivs.") == 2

    def test_discard_a(self):
        assert detect_discard_count("Discard a card.") == 1

    def test_chinese(self):
        assert detect_discard_count("弃置1张牌。") == 1

    def test_chinese_2(self):
        assert detect_discard_count("弃置2张牌。") == 2

    def test_case_insensitive(self):
        assert detect_discard_count("DISCARD 1 card") == 1

    def test_no_discard(self):
        assert detect_discard_count("Deal 6 damage.") == 0

    def test_empty(self):
        assert detect_discard_count("") == 0

    def test_none(self):
        assert detect_discard_count(None) == 0


class TestDetectDrawsCards:
    def test_draw_2(self):
        assert detect_draws_cards("Draw 2 cards.") is True

    def test_draw_1(self):
        assert detect_draws_cards("Draw 1 card.") is True

    def test_add_to_hand(self):
        assert detect_draws_cards("Add a copy to your hand.") is True

    def test_put_into_hand(self):
        assert detect_draws_cards("Put into your hand.") is True

    def test_chinese(self):
        assert detect_draws_cards("抽2张牌。") is True

    def test_next_turn_draw_is_not_immediate(self):
        assert detect_draws_cards("Deal 15 damage.\nNext turn, draw 2 cards.") is False

    def test_start_of_next_turn_draw_is_not_immediate(self):
        assert (
            detect_draws_cards(
                "If you play 5 or more cards in a turn, draw 1 card at the start of your next turn."
            )
            is False
        )

    def test_no_draw(self):
        assert detect_draws_cards("Deal 10 damage.") is False

    def test_empty(self):
        assert detect_draws_cards("") is False

    def test_none(self):
        assert detect_draws_cards(None) is False
