"""Tests for stub template loading and character substitution."""

from pathlib import Path

import pytest
from src.skills.models import Skill, SkillTrigger


def test_skill_accepts_scaffold_field():
    """Skill model must accept a scaffold dict (used by stubs)."""
    skill = Skill(
        skill_id="stub_the_silent_combat",
        name="The Silent - Combat Principles",
        category="combat",
        trigger=SkillTrigger(
            state_types=frozenset(["monster", "elite"]),
            character=frozenset(["the silent"]),
        ),
        content="TBD",
        source="stub",
        status="pending_fill",
        scaffold={
            "topic": "combat principles",
            "scope": "Generalizable principles...",
            "dimensions_to_consider": ["energy", "intent"],
            "out_of_scope": ["per-enemy"],
            "format_constraints": {"token_budget": "400-700"},
            "leakage_guard": {"max_distinct_card_names": 8},
        },
    )
    assert skill.scaffold["topic"] == "combat principles"
    assert skill.status == "pending_fill"
    assert skill.source == "stub"


def test_skill_scaffold_roundtrips_through_dict():
    """to_dict / from_dict preserves scaffold."""
    skill = Skill(
        skill_id="stub_x",
        scaffold={"topic": "T", "leakage_guard": {"max_distinct_card_names": 5}},
        source="stub",
        status="pending_fill",
    )
    d = skill.to_dict()
    assert d["scaffold"]["topic"] == "T"
    restored = Skill.from_dict(d)
    assert restored.scaffold == skill.scaffold
    assert restored.status == "pending_fill"
    assert restored.source == "stub"


def test_skill_default_scaffold_is_empty_dict():
    """Non-stub skills default to empty scaffold (no key in to_dict output)."""
    skill = Skill(skill_id="seed_x")
    assert skill.scaffold == {}
    d = skill.to_dict()
    # Empty scaffold should be omitted from serialization (consistent with anchor_exemplars pattern)
    assert d.get("scaffold", {}) == {}


# ── Character substitution ──────────────────────────────────────


def test_substitute_character_in_template():
    """Templates with {character_id}, {character}, {character_name} substitute cleanly."""
    from src.skills.stub_template import substitute_character

    template = {
        "skill_id_template": "stub_{character_id}_combat",
        "name_template": "{character_name} - Combat Principles",
        "category": "combat",
        "trigger": {
            "state_types": ["monster"],
            "character": ["{character}"],
        },
    }
    result = substitute_character(template, character="the silent")
    assert result["skill_id"] == "stub_the_silent_combat"
    assert result["name"] == "The Silent - Combat Principles"
    assert result["category"] == "combat"  # non-templated values pass through
    assert result["trigger"]["character"] == ["the silent"]
    assert result["trigger"]["state_types"] == ["monster"]


def test_substitute_handles_multi_word_character():
    """Multi-word characters: spaces -> underscores in id, title case in name."""
    from src.skills.stub_template import substitute_character

    template = {
        "skill_id_template": "stub_{character_id}_boss",
        "name_template": "{character_name} - Boss Strategy",
        "trigger": {"character": ["{character}"]},
    }
    result = substitute_character(template, character="the regent")
    assert result["skill_id"] == "stub_the_regent_boss"
    assert result["name"] == "The Regent - Boss Strategy"


def test_substitute_renames_template_suffix_keys():
    """Keys ending with _template are renamed to non-suffixed final keys."""
    from src.skills.stub_template import substitute_character

    template = {
        "skill_id_template": "stub_{character_id}_x",
        "name_template": "{character_name} - X",
        "non_template_key": "verbatim",
    }
    result = substitute_character(template, character="silent")
    assert "skill_id" in result
    assert "name" in result
    assert "skill_id_template" not in result
    assert "name_template" not in result
    assert result["non_template_key"] == "verbatim"


def test_load_stub_templates_returns_empty_when_dir_missing():
    """Graceful fallback when seeds_stubs/ does not exist yet."""
    from src.skills.stub_template import load_stub_templates

    result = load_stub_templates(Path("/nonexistent/path/that/should/not/exist"))
    assert result == []


# ── 5-template integration sanity ───────────────────────────────


def test_all_5_stub_templates_load_for_silent():
    """Sanity check: 5 templates exist, all instantiate cleanly for 'the silent'."""
    from src.skills.stub_template import load_stub_templates, substitute_character

    repo_root = Path(__file__).resolve().parent.parent
    stub_dir = repo_root / "src/skills/seeds_stubs"
    templates = load_stub_templates(stub_dir)
    assert len(templates) == 5, f"Expected 5 templates, got {len(templates)}"

    expected_ids = {
        "stub_the_silent_combat",
        "stub_the_silent_boss",
        "stub_the_silent_deckbuilding",
        "stub_the_silent_map",
        "stub_the_silent_intermission",
    }
    actual_ids: set[str] = set()
    for t in templates:
        instance = substitute_character(t, character="the silent")
        actual_ids.add(instance["skill_id"])
        assert instance["status"] == "pending_fill"
        assert instance["source"] == "stub"
        assert instance["content"].startswith("TBD")
        assert "scaffold" in instance
        assert "dimensions_to_consider" in instance["scaffold"]
        assert "leakage_guard" in instance["scaffold"]
        # trigger.character correctly substituted
        assert instance["trigger"]["character"] == ["the silent"]

    assert actual_ids == expected_ids, (
        f"missing: {expected_ids - actual_ids}, extra: {actual_ids - expected_ids}"
    )


def test_5_templates_cover_complete_state_type_partition():
    """Combined trigger.state_types across 5 templates must cover the full
    Silent decision surface without overlap (besides hand_select edge case)."""
    from src.skills.stub_template import load_stub_templates, substitute_character

    repo_root = Path(__file__).resolve().parent.parent
    stub_dir = repo_root / "src/skills/seeds_stubs"
    templates = load_stub_templates(stub_dir)

    state_types_by_stub: dict[str, set[str]] = {}
    for t in templates:
        instance = substitute_character(t, character="the silent")
        state_types_by_stub[instance["skill_id"]] = set(
            instance["trigger"]["state_types"]
        )

    # Combined: all decision state_types must appear
    all_covered: set[str] = set()
    for st_set in state_types_by_stub.values():
        all_covered |= st_set
    expected_state_types = {
        "monster", "elite", "boss", "hand_select",
        "card_reward", "card_select", "shop", "treasure", "relic_select",
        "map", "rest_site", "event",
    }
    missing = expected_state_types - all_covered
    assert not missing, f"State types not covered by any stub: {missing}"
