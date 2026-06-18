"""Tests for warn-only stub validators."""
from src.skills.stub_validators import run_stub_validators


SCAFFOLD = {
    "format_constraints": {"token_budget": "400-700 tokens"},
    "leakage_guard": {
        "max_distinct_card_names": 8,
        "max_distinct_enemy_names": 3,
        "no_specific_damage_thresholds": True,
    },
}


def _principles(*texts):
    return [{"text": t, "example": "ex"} for t in texts]


def test_token_count_in_range_no_warning(monkeypatch):
    # Each principle ~80 tokens × 5 = ~400, in budget
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names",
        lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names",
        lambda text: [],
    )
    long_text = "Word " * 80
    parsed = {
        "principles": _principles(long_text, long_text, long_text, long_text, long_text),
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert not any("token_count" in w for w in warnings), warnings


def test_token_count_too_low_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {"principles": _principles("Tiny.", "tiny", "x", "y", "z"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("token_count_out_of_range" in w for w in warnings)


def test_principle_count_too_few_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {"principles": _principles("a", "b", "c"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("principle_count_off" in w for w in warnings)


def test_principle_count_too_many_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {"principles": _principles(*list("abcdefghi")), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("principle_count_off" in w for w in warnings)


def test_card_name_density_warns(monkeypatch):
    """If extracted cards exceed max_distinct_card_names, warn."""
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names",
        lambda text: ["Strike", "Defend", "Backstab", "Pinpoint", "Pounce",
                      "Footwork", "Acrobatics", "Survivor", "Cloak"],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {"principles": _principles("a", "b", "c", "d", "e"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("card_name_density" in w for w in warnings)


def test_enemy_name_density_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names",
        lambda text: ["Lagavulin", "Mecha Knight", "Slimed Berserker", "Toadpole"],
    )
    parsed = {"principles": _principles("a", "b", "c", "d", "e"), "confidence": 0.7}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("enemy_name_density" in w for w in warnings)


def test_specific_damage_threshold_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {
        "principles": [
            {"text": "Block 12 damage before round 4.", "example": "ex"},
            {"text": "stuff", "example": "ex"},
            {"text": "stuff", "example": "ex"},
            {"text": "stuff", "example": "ex"},
            {"text": "stuff", "example": "ex"},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("specific_thresholds_found" in w for w in warnings)


def test_imperative_voice_warns_on_descriptive(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {
        "principles": [
            {"text": "Energy resets each turn.", "example": "ex"},
            {"text": "HP carries between fights.", "example": "ex"},
            {"text": "Block resets every turn.", "example": "ex"},
            {"text": "Use ALL energy each turn.", "example": "ex"},
            {"text": "Read intents first.", "example": "ex"},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("voice_check" in w for w in warnings)


def test_confidence_out_of_range_warns(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names", lambda text: [],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names", lambda text: [],
    )
    parsed = {"principles": _principles("a", "b", "c", "d", "e"), "confidence": 0.99}
    warnings = run_stub_validators(parsed, SCAFFOLD)
    assert any("confidence_out_of_range" in w for w in warnings)


def test_clean_input_yields_no_warnings(monkeypatch):
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_card_names",
        lambda text: ["Strike", "Defend"],
    )
    monkeypatch.setattr(
        "src.skills.stub_validators._extract_enemy_names",
        lambda text: ["Lagavulin"],
    )
    parsed = {
        "principles": [
            {"text": "Use ALL energy each turn.", "example": "If 1 energy left, play a 1-cost."},
            {"text": "Read intents BEFORE deciding offense vs defense.", "example": "When the enemy buffs, set up."},
            {"text": "Prefer the no-damage block line over a faster line.", "example": "Take a defensive turn."},
            {"text": "Sequence free plays first to gain tempo.", "example": "Free Strike before a costed skill."},
            {"text": "Save buff potions for boss fights.", "example": "Don't burn Strength Potion on a hallway."},
        ],
        "confidence": 0.7,
    }
    warnings = run_stub_validators(parsed, SCAFFOLD)
    # token count: 5 principles × ~25 chars = ~125 chars / 4 = ~31 tokens — TOO LOW.
    # That's an expected warning given the budget 400-700. Filter only the warnings
    # we explicitly asked for.
    relevant = [
        w for w in warnings
        if any(kw in w for kw in ("card_name_density", "enemy_name_density",
                                   "specific_thresholds_found", "voice_check",
                                   "principle_count_off", "confidence_out_of_range"))
    ]
    assert relevant == [], f"Expected no quality warnings, got: {relevant}"
