from src.mcp_client.upstream_models import UpstreamGameState
from src.state.upstream_game_state import UpstreamStateView


def _view(boss_id: str | None, second_boss_id: str | None = None) -> UpstreamStateView:
    raw = UpstreamGameState(
        boss_encounter_id=boss_id,
        second_boss_encounter_id=second_boss_id,
    )
    return UpstreamStateView(raw=raw)


def test_upcoming_boss_keys_none_when_missing():
    assert _view(None).upcoming_boss_enemy_keys == []


def test_upcoming_boss_keys_single():
    assert _view("CEREMONIAL_BEAST_BOSS").upcoming_boss_enemy_keys == ["Ceremonial Beast"]


def test_upcoming_boss_keys_with_second_boss():
    keys = _view("CEREMONIAL_BEAST_BOSS", "DOORMAKER_BOSS").upcoming_boss_enemy_keys
    assert keys == ["Ceremonial Beast", "multi:Door+Doormaker"]


def test_upcoming_boss_keys_unknown_encounter_filtered():
    # Unknown encounter id → resolver returns None → filtered out
    assert _view("NOT_REAL").upcoming_boss_enemy_keys == []
