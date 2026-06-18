"""Library-level tests for seed stub loading and retrieval."""

from pathlib import Path

import pytest
from src.skills.library import SkillLibrary


def _stub_dir() -> Path:
    return Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"


def test_load_seed_stubs_creates_5_pending_stubs_for_silent():
    """load_seed_stubs reads templates and instantiates them per character."""
    lib = SkillLibrary()
    n = lib.load_seed_stubs(_stub_dir(), character="the silent")
    assert n == 5

    stub_ids = {s.skill_id for s in lib.all_skills if s.skill_id.startswith("stub_")}
    expected = {
        "stub_the_silent_combat",
        "stub_the_silent_boss",
        "stub_the_silent_deckbuilding",
        "stub_the_silent_map",
        "stub_the_silent_intermission",
    }
    assert stub_ids == expected
    for s in lib.all_skills:
        if s.skill_id.startswith("stub_"):
            assert s.status == "pending_fill"
            assert s.source == "stub"
            assert s.scaffold  # non-empty
            assert s.content.startswith("TBD")


def test_load_seed_stubs_returns_zero_when_dir_missing():
    """Missing stub dir → zero loaded, no exception."""
    lib = SkillLibrary()
    n = lib.load_seed_stubs(Path("/nonexistent"), character="the silent")
    assert n == 0
    assert lib.count == 0


def test_load_seed_stubs_idempotent():
    """Calling load twice with same character does not duplicate stubs."""
    lib = SkillLibrary()
    n1 = lib.load_seed_stubs(_stub_dir(), character="the silent")
    n2 = lib.load_seed_stubs(_stub_dir(), character="the silent")
    assert n1 == 5
    assert n2 == 0  # all already loaded
    assert lib.count == 5


def test_load_seed_stubs_for_different_characters_coexist():
    """Loading for two characters yields 10 stubs (5 per character)."""
    lib = SkillLibrary()
    lib.load_seed_stubs(_stub_dir(), character="the silent")
    lib.load_seed_stubs(_stub_dir(), character="the regent")
    assert lib.count == 10
    silent_stubs = [s for s in lib.all_skills if "silent" in s.skill_id]
    regent_stubs = [s for s in lib.all_skills if "regent" in s.skill_id]
    assert len(silent_stubs) == 5
    assert len(regent_stubs) == 5


# ── query() skips pending_fill ──────────────────────────────────


def test_query_skips_pending_fill_stubs():
    """pending_fill stubs must NOT appear in retrieval — would inject 'TBD'."""
    lib = SkillLibrary()
    lib.load_seed_stubs(_stub_dir(), character="the silent")

    # Query for combat — would normally match stub_the_silent_combat
    results = lib.query(
        state_type="monster",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    skill_ids = {s.skill_id for s, _ in results}
    assert "stub_the_silent_combat" not in skill_ids, (
        "pending_fill stubs leaked into retrieval — they will inject 'TBD' content into prompts"
    )


def test_query_includes_active_stubs_after_fill():
    """After a stub is filled (status=active, source=stub_filled), it appears in retrieval."""
    lib = SkillLibrary()
    lib.load_seed_stubs(_stub_dir(), character="the silent")

    combat_stub = lib.get("stub_the_silent_combat")
    assert combat_stub is not None
    activated = combat_stub.with_update(
        status="active",
        source="stub_filled",
        content="1. Use ALL energy each turn.\n   Example: even with 1 energy left, play a 1-cost.",
    )
    lib.add(activated)

    results = lib.query(
        state_type="monster",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    skill_ids = {s.skill_id for s, _ in results}
    assert "stub_the_silent_combat" in skill_ids


def test_query_still_skips_other_pending_stubs_when_one_is_active():
    """Activating one stub doesn't accidentally unblock the others."""
    lib = SkillLibrary()
    lib.load_seed_stubs(_stub_dir(), character="the silent")

    # Activate combat only
    combat = lib.get("stub_the_silent_combat")
    lib.add(combat.with_update(status="active", source="stub_filled", content="x"))

    # Boss still pending
    results = lib.query(
        state_type="boss",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    skill_ids = {s.skill_id for s, _ in results}
    assert "stub_the_silent_boss" not in skill_ids
    # And combat appears for state_type=monster (separate query)
    monster_results = lib.query(
        state_type="monster",
        context_tags=frozenset(["the silent"]),
        limit=10,
    )
    assert "stub_the_silent_combat" in {s.skill_id for s, _ in monster_results}
