"""TDD tests for the postrun core-engine extractor pipeline.

The extractor identifies the core engine of a winning deck by analyzing
the top-3 highest-damage rounds of the Act 3 final boss fight, and writes
structured observations back to card_memory so the abstract two-phase
deckbuilding prompt can be grounded in concrete card-level knowledge.

See 2026-04-22 gemini-full ablation investigation for motivation.
"""
from __future__ import annotations

import pytest


# ── Cycle 1: CardMemory schema extension ─────────────────────


def test_card_memory_has_core_engine_observations_field():
    """CardMemory must carry a tuple of core-engine observation dicts.

    Backward-compat: default is empty, old serialized records load.
    """
    from src.memory.models_v2 import CardMemory
    m = CardMemory(character="silent", card_name="backstab")
    assert hasattr(m, "core_engine_observations"), (
        "CardMemory needs a core_engine_observations field"
    )
    assert m.core_engine_observations == ()


def test_card_memory_to_dict_includes_core_engine_observations():
    from src.memory.models_v2 import CardMemory
    obs = {"run_id": "r1", "engine_mechanic": "stacking debuffs", "core_cards": ["X"]}
    m = CardMemory(
        character="silent", card_name="backstab",
        core_engine_observations=(obs,),
    )
    d = m.to_dict()
    assert d.get("core_engine_observations") == [obs]


def test_card_memory_from_dict_roundtrip():
    from src.memory.models_v2 import CardMemory
    obs = {"run_id": "r1", "engine_mechanic": "poison scaling"}
    m = CardMemory(
        character="silent", card_name="backstab",
        core_engine_observations=(obs,),
    )
    restored = CardMemory.from_dict(m.to_dict())
    assert restored.core_engine_observations == (obs,)


def test_card_memory_from_dict_missing_field_defaults_empty():
    """Old persisted records lack the field → load cleanly with empty default."""
    from src.memory.models_v2 import CardMemory
    old_record = {"character": "silent", "card_name": "backstab", "note": "old seed"}
    m = CardMemory.from_dict(old_record)
    assert m.core_engine_observations == ()
    assert m.note == "old seed"


# ── Cycle 2: find_final_boss_combat ─────────────────────────


def _mk_episode(run_id="r1", act=3, combat_type="boss", won=True,
                enemy_key="Final Boss", **kw):
    from src.memory.models_v2 import CombatEpisode
    return CombatEpisode(
        run_id=run_id, act=act, combat_type=combat_type, won=won,
        enemy_key=enemy_key, **kw,
    )


def test_find_final_boss_combat_returns_act3_boss_victory():
    from src.memory.core_engine_extractor import find_final_boss_combat
    eps = [
        _mk_episode(floor=15, act=1, combat_type="boss", won=True, enemy_key="Act1"),
        _mk_episode(floor=33, act=2, combat_type="boss", won=True, enemy_key="Act2"),
        _mk_episode(floor=48, act=3, combat_type="boss", won=True, enemy_key="Act3Final"),
    ]
    result = find_final_boss_combat(eps, run_id="r1")
    assert result is not None
    assert result.enemy_key == "Act3Final"
    assert result.act == 3


def test_find_final_boss_combat_returns_none_if_not_won():
    from src.memory.core_engine_extractor import find_final_boss_combat
    eps = [_mk_episode(floor=48, act=3, combat_type="boss", won=False)]
    assert find_final_boss_combat(eps, run_id="r1") is None


def test_find_final_boss_combat_filters_by_run_id():
    from src.memory.core_engine_extractor import find_final_boss_combat
    eps = [
        _mk_episode(run_id="other", floor=48, act=3, combat_type="boss"),
        _mk_episode(run_id="r1", floor=48, act=3, combat_type="boss"),
    ]
    result = find_final_boss_combat(eps, run_id="r1")
    assert result is not None
    assert result.run_id == "r1"


def test_find_final_boss_combat_none_if_no_act3():
    from src.memory.core_engine_extractor import find_final_boss_combat
    eps = [_mk_episode(floor=15, act=1, combat_type="boss")]
    assert find_final_boss_combat(eps, run_id="r1") is None


# ── Cycle 5: apply_to_card_memory ────────────────────────────


def test_apply_appends_core_engine_observation_to_listed_cards():
    """Each card named in core_cards gets a core_engine_observation appended
    to its CardMemory entry."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.core_engine_extractor import apply_to_card_memory
    from src.memory.models_v2 import CardMemory

    store = CardMemoryStore()
    # Pre-existing memory for one of the cards; the other is new.
    store.put(CardMemory(character="silent", card_name="noxious fumes", note="seed"))

    result = {
        "engine_mechanic": "stacking continuous passive debuff damage",
        "core_cards": ["Noxious Fumes", "Catalyst"],
        "support_cards": ["Prepared", "Acrobatics"],
        "notes": "Noxious Fumes + Catalyst scales poison fast; support from draw.",
    }
    updated = apply_to_card_memory(
        result, store, character="silent", run_id="r1",
    )
    # Both core_cards should get an observation
    assert updated >= 2
    fumes = store.get("silent", "Noxious Fumes")
    assert fumes is not None
    assert len(fumes.core_engine_observations) == 1
    obs = fumes.core_engine_observations[0]
    assert obs["role"] == "core"
    assert obs["run_id"] == "r1"
    assert "debuff" in obs["engine_mechanic"].lower()
    # New card entry created for Catalyst
    cat = store.get("silent", "Catalyst")
    assert cat is not None
    assert len(cat.core_engine_observations) == 1


def test_apply_records_support_role_for_support_cards():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.core_engine_extractor import apply_to_card_memory
    store = CardMemoryStore()
    result = {
        "engine_mechanic": "shiv chain via buff",
        "core_cards": ["Accuracy"],
        "support_cards": ["Blade Dance"],
        "notes": "",
    }
    apply_to_card_memory(result, store, character="silent", run_id="r2")
    blade = store.get("silent", "Blade Dance")
    assert blade is not None
    assert blade.core_engine_observations[0]["role"] == "support"


def test_apply_is_append_only_across_runs():
    """Repeated apply calls for different runs append new observations."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.core_engine_extractor import apply_to_card_memory
    store = CardMemoryStore()
    r1 = {"engine_mechanic": "m1", "core_cards": ["X"], "support_cards": [], "notes": ""}
    r2 = {"engine_mechanic": "m2", "core_cards": ["X"], "support_cards": [], "notes": ""}
    apply_to_card_memory(r1, store, character="silent", run_id="r1")
    apply_to_card_memory(r2, store, character="silent", run_id="r2")
    x = store.get("silent", "X")
    assert x is not None
    assert len(x.core_engine_observations) == 2
    run_ids = {o["run_id"] for o in x.core_engine_observations}
    assert run_ids == {"r1", "r2"}


def test_apply_ignores_empty_result():
    """Malformed / empty extractor result should not create garbage entries."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.core_engine_extractor import apply_to_card_memory
    store = CardMemoryStore()
    updated = apply_to_card_memory(
        {"engine_mechanic": "", "core_cards": [], "support_cards": [], "notes": ""},
        store, character="silent", run_id="r1",
    )
    assert updated == 0
    assert store.count == 0


# ── Cycle 7: has_content + store.query_cards surface observations ───


def test_card_memory_has_content_true_when_only_observations():
    """A card with no note but at least one core-engine observation should
    still be considered content-bearing so the retriever surfaces it."""
    from src.memory.models_v2 import CardMemory
    obs = {"run_id": "r1", "role": "core", "engine_mechanic": "stacking"}
    m = CardMemory(
        character="silent", card_name="x", note="",
        core_engine_observations=(obs,),
    )
    assert m.has_content is True


def test_card_memory_has_content_false_when_truly_empty():
    from src.memory.models_v2 import CardMemory
    m = CardMemory(character="silent", card_name="x")
    assert m.has_content is False


def test_store_query_cards_returns_memory_with_only_observations():
    """query_cards must return cards that have observations even if note is empty."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.core_engine_extractor import apply_to_card_memory

    store = CardMemoryStore()
    apply_to_card_memory(
        {"engine_mechanic": "debuff stacking",
         "core_cards": ["Noxious Fumes"],
         "support_cards": [], "notes": ""},
        store, character="silent", run_id="r1",
    )
    results = store.query_cards("silent", ["Noxious Fumes"])
    assert len(results) == 1
    assert results[0].core_engine_observations


# ── Cycle 8: format_core_engine_hint for prompt injection ────


def test_format_core_engine_hint_core_role():
    """Produce a compact one-liner summarizing recent core-engine observations."""
    from src.memory.core_engine_extractor import format_core_engine_hint
    from src.memory.models_v2 import CardMemory
    obs1 = {"run_id": "r1", "role": "core",
            "engine_mechanic": "stacking continuous passive debuff damage",
            "notes": "", "co_cards": ["Prepared", "Acrobatics"]}
    m = CardMemory(
        character="silent", card_name="Noxious Fumes",
        core_engine_observations=(obs1,),
    )
    hint = format_core_engine_hint(m)
    assert hint
    assert "core" in hint.lower()
    # Mechanic should appear
    assert "debuff" in hint.lower()


def test_format_core_engine_hint_support_role():
    from src.memory.core_engine_extractor import format_core_engine_hint
    from src.memory.models_v2 import CardMemory
    obs = {"run_id": "r2", "role": "support",
           "engine_mechanic": "poison scaling", "notes": "",
           "co_cards": ["Noxious Fumes"]}
    m = CardMemory(
        character="silent", card_name="Acrobatics",
        core_engine_observations=(obs,),
    )
    hint = format_core_engine_hint(m)
    assert hint
    assert "support" in hint.lower()


def test_format_core_engine_hint_empty_when_no_observations():
    from src.memory.core_engine_extractor import format_core_engine_hint
    from src.memory.models_v2 import CardMemory
    m = CardMemory(character="silent", card_name="x")
    assert format_core_engine_hint(m) == ""


def test_format_core_engine_hint_aggregates_multiple_observations():
    """When a card has been core in multiple past wins, hint should
    mention the pattern (e.g. "core in 3 wins") rather than list each."""
    from src.memory.core_engine_extractor import format_core_engine_hint
    from src.memory.models_v2 import CardMemory
    obs = [
        {"run_id": f"r{i}", "role": "core",
         "engine_mechanic": "passive damage", "notes": "", "co_cards": []}
        for i in range(3)
    ]
    m = CardMemory(
        character="silent", card_name="X",
        core_engine_observations=tuple(obs),
    )
    hint = format_core_engine_hint(m)
    assert hint
    assert "3" in hint or "multiple" in hint.lower()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
