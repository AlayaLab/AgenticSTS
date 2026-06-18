"""Unit tests for B1 prompt transform."""
from __future__ import annotations

import pytest

from scripts._prompt_ab.transform import B1TransformError, apply_b1


def test_apply_b1_relocates_available_cards_before_eval() -> None:
    src = "\n".join([
        "## Card Reward",
        "HP: 50/75",
        "",
        "## Available Cards",
        "- [index=0] Strike",
        "- [index=1] Defend",
        "",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "",
        "## Evaluation — Boss Damage Check",
        "Estimate DPS...",
        "",
        "## Decision Format (card_reward_action)",
        "Valid actions: choose_reward_card",
    ])

    out = apply_b1(src)

    avail_pos = out.index("## Available Cards")
    eval_pos = out.index("## Evaluation — Boss Damage Check")
    assert avail_pos < eval_pos
    glossary_pos = out.index("## Keyword Glossary")
    assert glossary_pos < avail_pos
    assert "- [index=0] Strike" in out
    assert "- [index=1] Defend" in out
    assert "HP: 50/75" in out
    assert out.count("## Available Cards") == 1


def test_apply_b1_idempotent_when_already_at_tail() -> None:
    """If Available Cards already directly precedes Evaluation, leave as-is."""
    src = "\n".join([
        "## Card Reward",
        "HP: 50/75",
        "",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "",
        "## Available Cards",
        "- [index=0] Strike",
        "",
        "## Evaluation — Boss Damage Check",
        "Estimate DPS...",
    ])

    out = apply_b1(src)

    assert out == src


def test_apply_b1_raises_when_section_missing() -> None:
    src = "## Card Reward\nHP: 50/75\n## Evaluation — Boss Damage Check\n"

    with pytest.raises(B1TransformError):
        apply_b1(src)


def test_apply_b1_preserves_content_outside_moved_block() -> None:
    src = "\n".join([
        "## Expert Knowledge (retrieved skills)",
        "Some skill text spanning",
        "multiple lines.",
        "",
        "## Card Reward",
        "HP: 50/75",
        "## Current Deck (12 cards)",
        "- Strike x5",
        "## Relics: A, B, C",
        "## Available Cards",
        "- [index=0] Strike",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "## Evaluation — Boss Damage Check",
        "Eval text",
        "## Decision Format (card_reward_action)",
        "Schema",
    ])

    out = apply_b1(src)

    expected_order = [
        "## Expert Knowledge",
        "## Card Reward",
        "## Current Deck",
        "## Relics:",
        "## Keyword Glossary",
        "## Available Cards",
        "## Evaluation — Boss Damage Check",
        "## Decision Format",
    ]
    positions = [out.index(h) for h in expected_order]
    assert positions == sorted(positions), f"Header order broken: {positions}"
