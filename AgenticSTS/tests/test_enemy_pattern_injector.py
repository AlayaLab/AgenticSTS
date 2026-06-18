# tests/test_enemy_pattern_injector.py
"""Tests for enemy pattern injector."""
from src.brain.enemy_pattern_injector import format_enemy_patterns, format_upcoming_patterns


def _make_round(num: int, intents: tuple[str, ...]) -> dict:
    """Create a minimal CombatRound-like dict for testing."""
    return {"round_num": num, "enemy_intents": intents}


def _make_episode(rounds: list[dict]) -> object:
    """Create a minimal CombatEpisode-like object for testing."""
    class FakeRound:
        def __init__(self, d):
            self.round_num = d["round_num"]
            self.enemy_intents = tuple(d["enemy_intents"])

    class FakeEpisode:
        def __init__(self, rounds):
            self.rounds = [FakeRound(r) for r in rounds]

    return FakeEpisode(rounds)


class TestFormatEnemyPatterns:
    def test_empty_episodes_returns_empty(self):
        result = format_enemy_patterns([], current_round=1)
        assert result == ""

    def test_single_episode_formats_correctly(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
            _make_round(3, ("Attack 18",)),
        ])
        result = format_enemy_patterns([ep], current_round=1)
        assert "## Enemy Patterns" in result
        assert "Current round: R1" in result
        assert "not guaranteed future actions" in result
        assert "R1 Attack 12" in result
        assert "R2 Buff" in result
        assert "R3 Attack 18" in result

    def test_max_episodes_respected(self):
        episodes = [_make_episode([_make_round(1, ("Attack",))]) for _ in range(5)]
        result = format_enemy_patterns(episodes, current_round=1)
        assert result.count("Past fight") <= 3

    def test_max_rounds_per_episode_respected(self):
        rounds = [_make_round(i, (f"Attack {i}",)) for i in range(1, 12)]
        ep = _make_episode(rounds)
        result = format_enemy_patterns([ep], current_round=1)
        # Should cap at 8 rounds
        assert "R9" not in result

    def test_multi_intent_per_round(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12", "Debuff")),
        ])
        result = format_enemy_patterns([ep], current_round=1)
        assert "Attack 12 + Debuff" in result

    def test_opaque_move_ids_are_filtered_from_full_patterns(self):
        ep = _make_episode([
            _make_round(1, ("Mecha Knight: CHARGE_MOVE",)),
            _make_round(2, ("Mecha Knight: FLAMETHROWER_MOVE",)),
        ])
        result = format_enemy_patterns([ep], current_round=1)
        assert "Past fight" not in result
        assert "CHARGE_MOVE" not in result
        assert "FLAMETHROWER_MOVE" not in result


class TestFormatUpcomingPatterns:
    def test_upcoming_from_round_3(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
            _make_round(3, ("Attack 18",)),
            _make_round(4, ("Multi-Attack 8x3",)),
        ])
        result = format_upcoming_patterns([ep], current_round=3)
        assert "Likely upcoming after R3" in result
        assert "R4 Multi-Attack 8x3" in result
        # Should NOT include past rounds
        assert "R1" not in result
        assert "R2" not in result

    def test_upcoming_empty_when_past_end(self):
        ep = _make_episode([
            _make_round(1, ("Attack 12",)),
            _make_round(2, ("Buff",)),
        ])
        result = format_upcoming_patterns([ep], current_round=5)
        assert result == ""

    def test_upcoming_max_3_rounds(self):
        rounds = [_make_round(i, (f"Move {i}",)) for i in range(1, 10)]
        ep = _make_episode(rounds)
        result = format_upcoming_patterns([ep], current_round=2)
        assert "R3" in result
        assert "R4" in result
        assert "R5" in result
        assert "R6" not in result

    def test_upcoming_skips_opaque_move_ids(self):
        ep = _make_episode([
            _make_round(1, ("Mecha Knight: Attack(25)",)),
            _make_round(2, ("Mecha Knight: FLAMETHROWER_MOVE",)),
            _make_round(3, ("Mecha Knight: WINDUP_MOVE",)),
        ])
        result = format_upcoming_patterns([ep], current_round=1)
        assert result == ""
