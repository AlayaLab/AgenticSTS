"""Tests for fill / update prompt assembly."""


SCAFFOLD = {
    "topic": "Combat principles for this character",
    "scope": "Generalizable principles for hallway and elite encounters.",
    "out_of_scope": ["Per-enemy mechanics belong in combat_guides"],
    "dimensions_to_consider": [
        "Energy allocation",
        "Intent reading",
        "HP loss MINIMIZATION",
    ],
    "format_constraints": {
        "token_budget": "400-700 tokens",
        "structure": "5-8 numbered principles + concrete example each",
        "voice": "Imperative, second-person",
    },
    "leakage_guard": {
        "max_distinct_card_names": 8,
        "max_distinct_enemy_names": 3,
    },
}


def test_fill_prompt_contains_role_topic_dimensions_evidence():
    from src.skills.stub_prompts import build_fill_prompt

    prompt = build_fill_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="non-boss combat",
        evidence="## Combat Replay 1 ...",
    )
    assert "strategy-skill author" in prompt.lower()
    assert "Energy allocation" in prompt
    assert "HP loss MINIMIZATION" in prompt
    assert "## Combat Replay 1" in prompt
    assert "max_distinct_card_names: 8" in prompt
    assert "## Existing Content" not in prompt  # fill mode, no existing


def test_fill_prompt_includes_out_of_scope():
    from src.skills.stub_prompts import build_fill_prompt

    prompt = build_fill_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="combat",
        evidence="evidence",
    )
    assert "Per-enemy mechanics" in prompt


def test_fill_prompt_specifies_output_schema():
    from src.skills.stub_prompts import build_fill_prompt

    prompt = build_fill_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="combat",
        evidence="evidence",
    )
    assert "principles" in prompt
    assert "confidence" in prompt
    # Token budget shown
    assert "400-700" in prompt


def test_update_prompt_includes_existing_content_section():
    from src.skills.stub_prompts import build_update_prompt

    prompt = build_update_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="non-boss combat",
        evidence="## Combat Replay 1 ...",
        existing_content="1. Use ALL energy each turn.\n2. Read intents first.",
        existing_version=3,
    )
    assert "## Existing Content (v3)" in prompt
    assert "Use ALL energy each turn" in prompt
    assert "REPLACE rather than append" in prompt
    # Update prompt still has all the fill prompt elements
    assert "Energy allocation" in prompt
    assert "## Combat Replay 1" in prompt


def test_update_prompt_has_rewrite_freely_clause():
    """Early-run rewrite hint must be present (per spec section 6 update mode)."""
    from src.skills.stub_prompts import build_update_prompt

    prompt = build_update_prompt(
        scaffold=SCAFFOLD,
        state_type_cluster="combat",
        evidence="ev",
        existing_content="old",
        existing_version=1,
    )
    assert "rewrite freely" in prompt.lower() or "early-run" in prompt.lower()
