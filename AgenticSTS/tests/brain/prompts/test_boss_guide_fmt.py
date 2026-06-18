from types import SimpleNamespace

from src.brain.prompts._boss_guide_fmt import format_upcoming_boss_guide
from src.memory.models_v2 import CombatGuide


class _FakeGuideStore:
    def __init__(self, guides: dict[tuple[str, str], CombatGuide]):
        self._guides = guides

    def get_combat_guide(self, enemy_key: str, character: str) -> CombatGuide | None:
        return self._guides.get((enemy_key, character))


def _gs(boss_keys: list[str]) -> object:
    # Minimal stand-in for GameState — helper only needs upcoming_boss_enemy_keys + raw
    return SimpleNamespace(upcoming_boss_enemy_keys=boss_keys)


def test_empty_when_no_upcoming_boss():
    gs = _gs([])
    lines = format_upcoming_boss_guide(gs, "Silent", _FakeGuideStore({}))
    assert lines == []


def test_empty_when_guide_missing():
    gs = _gs(["Queen"])
    lines = format_upcoming_boss_guide(gs, "Silent", _FakeGuideStore({}))
    assert lines == []


def test_single_boss_renders_guide_text():
    guide = CombatGuide(
        enemy_key="Queen", character="Silent",
        guide_text="Tank the lvl-3 wave, then burst.",
        key_patterns=("Prioritize AOE round 1", "Watch for big slash turn 4"),
    )
    gs = _gs(["Queen"])
    store = _FakeGuideStore({("Queen", "Silent"): guide})
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Boss: Queen" in text
    assert "Tank the lvl-3 wave" in text
    assert "Prioritize AOE round 1" in text
    assert "Consider matchup when picking, but don't over-optimize" in text


def test_two_bosses_render_as_sequential_section():
    g1 = CombatGuide(enemy_key="Queen", character="Silent", guide_text="A")
    g2 = CombatGuide(enemy_key="multi:Door+Doormaker", character="Silent", guide_text="B")
    gs = _gs(["Queen", "multi:Door+Doormaker"])
    store = _FakeGuideStore({
        ("Queen", "Silent"): g1,
        ("multi:Door+Doormaker", "Silent"): g2,
    })
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Bosses (sequential)" in text
    assert "### Queen" in text
    assert "### multi:Door+Doormaker" in text
    assert "A" in text and "B" in text


def test_only_one_guide_present_falls_back_to_single_header():
    # First boss has guide, second does not → render as single-boss form (skip missing)
    g1 = CombatGuide(enemy_key="Queen", character="Silent", guide_text="A")
    gs = _gs(["Queen", "multi:Door+Doormaker"])
    store = _FakeGuideStore({("Queen", "Silent"): g1})
    lines = format_upcoming_boss_guide(gs, "Silent", store)
    text = "\n".join(lines)
    assert "## Upcoming Act Boss: Queen" in text
    assert "### Queen" not in text  # sub-header form not used for single guide
