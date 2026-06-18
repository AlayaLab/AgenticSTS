"""Tests for bucket B parser (card_note_updater.parse_non_deck_updates)."""
from __future__ import annotations

import json

from src.memory.card_note_updater import parse_non_deck_updates


def _make_payload(entries: list[dict]) -> str:
    return json.dumps({"updates": [], "non_deck_updates": entries})


def test_parse_non_deck_updates_accepts_valid_skipped_entry():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "Top poison-build payoff; take whenever offered.",
        "evidence_type": "skipped",
        "reason": "Skipped at card_reward floor 9.",
        "trace_citation": "Combat 3 R1: skipped Catalyst, picked Strike+",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "footwork"}),
        final_deck=frozenset({"strike", "defend"}),
        final_relics=frozenset(),
        skipped_cards=frozenset({"Catalyst"}),
    )
    assert dropped == 0
    assert len(proposals) == 1
    assert proposals[0]["card_name"] == "catalyst"
    assert proposals[0]["reason"].startswith("[skipped] ")


def test_parse_non_deck_updates_accepts_valid_combo_entry():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "Doubles existing poison; pick when Noxious Fumes is in deck.",
        "evidence_type": "combo_inferred",
        "reason": "Doubles Noxious Fumes stacks for one-turn payoff.",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "noxious fumes"}),
        final_deck=frozenset({"noxious fumes"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert dropped == 0
    assert len(proposals) == 1
    assert proposals[0]["reason"].startswith("[combo_inferred] ")


def test_parse_non_deck_updates_rejects_card_in_deck():
    """Bucket B rule 2: card must not be in deck."""
    raw = _make_payload([{
        "card_name": "Strike",
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "synergy with Strike",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"strike"}),
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_card_outside_pool():
    """Bucket B rule 1: card must be in class pool."""
    raw = _make_payload([{
        "card_name": "Bandage Up",  # colorless, not in silent pool
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "synergy with Strike",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"strike"}),
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_skipped_without_membership():
    """Bucket B rule 3: skipped requires skipped_cards membership."""
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "skipped",
        "reason": "skipped at floor 9",
        "trace_citation": "Combat 3: skipped Catalyst",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst"}),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),  # empty — Catalyst was not actually skipped
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_skipped_without_citation():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "skipped",
        "reason": "skipped at floor 9",
        "trace_citation": "",  # required for skipped
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst"}),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset({"Catalyst"}),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_rejects_combo_without_deck_token():
    """Bucket B rule 4: combo_inferred reason must mention a deck card or relic."""
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "generally good in poison builds",  # no deck card name
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "noxious fumes"}),
        final_deck=frozenset({"noxious fumes"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1


def test_parse_non_deck_updates_combo_accepts_relic_token():
    """Rule 4 also accepts relic-name tokens."""
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "combo_inferred",
        "reason": "Synergizes with the Snecko Eye relic for cost variance.",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst"}),
        final_deck=frozenset(),
        final_relics=frozenset({"snecko eye"}),
        skipped_cards=frozenset(),
    )
    assert proposals == [{
        "card_name": "catalyst",
        "new_note": "x" * 50,
        "reason": "[combo_inferred] Synergizes with the Snecko Eye relic for cost variance.",
        "trace_citation": "",
    }]
    assert dropped == 0


def test_parse_non_deck_updates_caps_at_three():
    entries = [
        {
            "card_name": f"Card{i}",
            "new_note": "x" * 50,
            "evidence_type": "combo_inferred",
            "reason": f"Combo with Strike {i}",
            "trace_citation": "",
        }
        for i in range(5)
    ]
    raw = _make_payload(entries)
    pool = frozenset({f"card{i}" for i in range(5)})
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=pool,
        final_deck=frozenset({"strike"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert len(proposals) == 3
    assert dropped == 2  # 2 over the cap


def test_parse_non_deck_updates_returns_empty_when_field_missing():
    raw = json.dumps({"updates": []})  # no non_deck_updates
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset(),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 0


def test_parse_non_deck_updates_returns_empty_on_malformed_json():
    proposals, dropped = parse_non_deck_updates(
        "not json",
        class_pool=frozenset(),
        final_deck=frozenset(),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 0


def test_parse_non_deck_updates_rejects_unknown_evidence_type():
    raw = _make_payload([{
        "card_name": "Catalyst",
        "new_note": "x" * 50,
        "evidence_type": "guessed",  # not skipped or combo_inferred
        "reason": "Combo with Noxious Fumes",
        "trace_citation": "",
    }])
    proposals, dropped = parse_non_deck_updates(
        raw,
        class_pool=frozenset({"catalyst", "noxious fumes"}),
        final_deck=frozenset({"noxious fumes"}),
        final_relics=frozenset(),
        skipped_cards=frozenset(),
    )
    assert proposals == []
    assert dropped == 1
