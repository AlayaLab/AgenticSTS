"""Tests for SkillTrigger matching and CardBuildMemory round-trip."""

from types import SimpleNamespace as NS

from src.memory.card_build_extractor import _VALID_ROLES
from src.memory.models_v2 import CardBuildMemory
from src.skills.models import SkillTrigger

# ── Layer 2a: Overlap-weighted requires_cards scoring ──


def test_requires_cards_single_match_scores_1_5():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Catalyst", "Strike"}))
    assert matched is True
    assert score == 1.5


def test_requires_cards_two_matches_scores_2_0():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Catalyst", "Noxious Fumes"}))
    assert matched is True
    assert score == 2.0


def test_requires_cards_four_matches_scores_3_0():
    trigger = SkillTrigger(requires_cards=frozenset({"A", "B", "C", "D", "E", "F"}))
    matched, score = trigger.matches(hand_cards=frozenset({"A", "B", "C", "D"}))
    assert matched is True
    assert score == 3.0


def test_requires_cards_no_match_returns_false():
    trigger = SkillTrigger(requires_cards=frozenset({"Catalyst"}))
    matched, score = trigger.matches(hand_cards=frozenset({"Strike", "Defend"}))
    assert matched is False
    assert score == 0.0


def test_requires_cards_six_matches_capped_by_diminishing_returns():
    trigger = SkillTrigger(requires_cards=frozenset({"A", "B", "C", "D", "E", "F"}))
    matched, score = trigger.matches(hand_cards=frozenset({"A", "B", "C", "D", "E", "F"}))
    assert matched is True
    assert score == 4.0


# ── Layer 2b: Deck-based card matching ──


def test_deck_cards_used_for_non_combat_skill_matching():
    trigger = SkillTrigger(
        state_types=frozenset({"card_reward"}),
        requires_cards=frozenset({"Catalyst", "Noxious Fumes"}),
    )
    deck_cards = frozenset({"Catalyst", "Strike", "Defend", "Survivor"})
    matched, score = trigger.matches(
        state_type="card_reward",
        hand_cards=deck_cards,
    )
    assert matched is True
    assert score >= 1.5


def test_skill_card_context_includes_card_reward_options():
    from src.agent.loop import _skill_matching_card_names

    gs = NS(
        state_type="card_reward",
        is_combat=False,
        combat=None,
        hand=[],
        deck=[NS(name="Strike")],
        reward=NS(card_options=[NS(name="Nightmare")]),
        shop=None,
        selection=None,
    )

    trigger = SkillTrigger(
        state_types=frozenset({"card_reward"}),
        requires_cards=frozenset({"Nightmare"}),
    )
    matched, _ = trigger.matches(
        state_type="card_reward",
        hand_cards=_skill_matching_card_names(gs),
    )
    assert matched is True


def test_skill_card_context_includes_shop_options():
    from src.agent.loop import _skill_matching_card_names

    gs = NS(
        state_type="shop",
        is_combat=False,
        combat=None,
        hand=[],
        deck=[NS(name="Strike")],
        reward=None,
        shop=NS(cards=[NS(name="Nightmare", is_stocked=True)]),
        selection=None,
    )

    names = _skill_matching_card_names(gs)
    assert "Nightmare" in names
    assert "nightmare" in names


def test_skill_card_context_includes_rest_site_deck_cards_and_base_names():
    from src.agent.loop import _skill_matching_card_names

    gs = NS(
        state_type="rest_site",
        is_combat=False,
        combat=None,
        hand=[],
        deck=[NS(name="Nightmare+")],
        reward=None,
        shop=None,
        selection=None,
    )

    names = _skill_matching_card_names(gs)
    assert "Nightmare+" in names
    assert "Nightmare" in names
    assert "nightmare" in names


# ── Layers 3+4: CardBuildMemory new fields ──


def test_card_build_memory_key_cards_default_empty():
    mem = CardBuildMemory(run_id="r1")
    assert mem.key_cards == ()
    assert mem.coherence_score == 0.0
    assert mem.coherence_analysis == ""


def test_card_build_memory_key_cards_roundtrip():
    mem = CardBuildMemory(
        run_id="r1",
        character="The Silent",
        key_cards=(
            ("Noxious Fumes", "keystone", "Passive poison stacking enabled win condition"),
            ("Strike", "dead_weight", "Never contributed meaningful damage"),
        ),
        coherence_score=0.72,
        coherence_analysis="Clear poison chain but weak draw engine",
    )
    d = mem.to_dict()
    assert len(d["key_cards"]) == 2
    assert d["key_cards"][0] == {"card": "Noxious Fumes", "role": "keystone", "insight": "Passive poison stacking enabled win condition"}
    assert d["key_cards"][1]["role"] == "dead_weight"
    assert d["coherence_score"] == 0.72
    assert d["coherence_analysis"] == "Clear poison chain but weak draw engine"

    restored = CardBuildMemory.from_dict(d)
    assert restored.key_cards == mem.key_cards
    assert restored.coherence_score == 0.72
    assert restored.coherence_analysis == "Clear poison chain but weak draw engine"


def test_card_build_memory_from_dict_missing_new_fields():
    d = {"run_id": "old_run", "character": "Ironclad"}
    mem = CardBuildMemory.from_dict(d)
    assert mem.key_cards == ()
    assert mem.coherence_score == 0.0
    assert mem.coherence_analysis == ""

# ── Layer 3+4: Validation logic ──


def test_valid_roles_constant_has_expected_values():
    assert "keystone" in _VALID_ROLES
    assert "dead_weight" in _VALID_ROLES
    assert "bad_pick" in _VALID_ROLES
    assert "core_damage" in _VALID_ROLES
    assert len(_VALID_ROLES) == 8


def test_key_cards_extraction_normalizes_invalid_roles():
    analysis = {
        "key_cards": [
            {"card": "Demon Form", "role": "keystone", "insight": "test"},
            {"card": "Strike", "role": "garbage_card", "insight": "bad role"},
            {"card": "Defend"},
            "not_a_dict",
        ],
    }
    key_cards = tuple(
        (kc["card"], kc["role"] if kc.get("role") in _VALID_ROLES else "utility", kc.get("insight", ""))
        for kc in analysis.get("key_cards", [])
        if isinstance(kc, dict) and "card" in kc
    )
    assert len(key_cards) == 3
    assert key_cards[0] == ("Demon Form", "keystone", "test")
    assert key_cards[1] == ("Strike", "utility", "bad role")
    assert key_cards[2] == ("Defend", "utility", "")
