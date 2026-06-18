"""Retriever-side event guide option library injection tests."""


def test_retriever_event_guide_renders_scored_options():
    """With a guide that has structured options, the injected block contains
    matching-encounter options sorted by score with analysis lines."""
    from src.memory.event_models import (
    EventGuide,
    EventGuideOption,
)
    from src.memory.retriever import _render_event_guide_block

    guide = EventGuide(
        event_id="OROBAS",
        character="the silent",
        guide_text="Always a free power spike.",
        options=(
            EventGuideOption(canonical_name="Archaic Tooth", stage_index=0,
                             variant_type="fixed", score=0.7,
                             analysis="Starter upgrade.", sample_size=14),
            EventGuideOption(canonical_name="Demon Glass", stage_index=0,
                             variant_type="random_from_pool", score=0.3,
                             analysis="Deck injection.", sample_size=4),
            EventGuideOption(canonical_name="Never Seen", stage_index=1,
                             variant_type="fixed", score=-0.9,
                             analysis="Bad idea.", sample_size=1),
        ),
        confidence=0.8, version=3,
    )
    current_option_titles = ["Archaic Tooth", "Demon Glass", "Mystery Box"]
    block = _render_event_guide_block(guide, current_option_titles, stage_index=0)

    # Header contains event id + character + version
    assert "OROBAS" in block
    assert "the silent" in block
    assert "v3" in block
    # Takeaway line
    assert "Always a free power spike." in block
    # Both matched options present
    assert "Archaic Tooth" in block
    assert "Demon Glass" in block
    # Unknown option flagged
    assert "Mystery Box" in block
    assert "not in guide" in block
    # Off-stage option excluded
    assert "Never Seen" not in block
    # Ordered by score descending (Archaic first)
    assert block.index("Archaic Tooth") < block.index("Demon Glass")


def test_retriever_event_guide_legacy_without_options():
    """Legacy guides (options=()) fall back to guide_text-only injection."""
    from src.memory.event_models import EventGuide
    from src.memory.retriever import _render_event_guide_block

    guide = EventGuide(
        event_id="OROBAS", character="the silent",
        guide_text="Old-format advice.", options=(),
        confidence=0.6, version=1,
    )
    block = _render_event_guide_block(guide, ["Any"], stage_index=0)
    assert "Old-format advice." in block
    # No "Options for this encounter" header when options=()
    assert "Options for this encounter" not in block
