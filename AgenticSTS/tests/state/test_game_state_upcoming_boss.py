"""Regression: GameState must expose upcoming_boss_enemy_keys (separate from UpstreamStateView).

Prompt builders (reward.py, shop.py) receive GameState, and the helper reads the
property via getattr; a missing property silently returns `[]` and the injection
vanishes. This test guards against that regression."""
from src.mcp_client.upstream_models import UpstreamGameState
from src.state.game_state import GameState


def _gs(boss_id: str | None, second_boss_id: str | None = None) -> GameState:
    raw = UpstreamGameState(
        boss_encounter_id=boss_id,
        second_boss_encounter_id=second_boss_id,
    )
    return GameState(raw=raw)


def test_gamestate_upcoming_boss_keys_empty_when_missing():
    assert _gs(None).upcoming_boss_enemy_keys == []


def test_gamestate_upcoming_boss_keys_single():
    assert _gs("CEREMONIAL_BEAST_BOSS").upcoming_boss_enemy_keys == ["Ceremonial Beast"]


def test_gamestate_upcoming_boss_keys_two_bosses():
    keys = _gs("CEREMONIAL_BEAST_BOSS", "DOORMAKER_BOSS").upcoming_boss_enemy_keys
    assert keys == ["Ceremonial Beast", "multi:Door+Doormaker"]


def test_gamestate_upcoming_boss_keys_unknown_filtered():
    assert _gs("NOT_REAL").upcoming_boss_enemy_keys == []
