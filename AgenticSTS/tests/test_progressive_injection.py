"""Tests for progressive prompt injection (Phase 2)."""

from src.memory.models_v2 import WorkingContext
from src.memory.prompt_injector import format_working_context


class TestGuideProgression:
    def test_r1_shows_full_guide(self):
        wc = WorkingContext(
            combat_guide_hints=("[Guide: Nibbit] Lead with Bash to apply Vulnerable early.",),
            situation_hints=("### Similar Past Situation\n- Intent: Attack 12",),
            current_round=1,
        )
        text = format_working_context(wc)
        assert "## Combat Guide" in text
        assert "Lead with Bash" in text
        # At R1, full guide shown (not truncated)
        assert "Background reference" not in text

    def test_r2_plus_demotes_guide(self):
        wc = WorkingContext(
            combat_guide_hints=("[Guide: Nibbit] Lead with Bash to apply Vulnerable early. Pommel Strike is MVP. Block is largely unnecessary. Prioritize raw damage output.",),
            situation_hints=("### Similar Past Situation\n- Intent: Attack 12",),
            current_round=3,
        )
        text = format_working_context(wc)
        assert "## Combat Guide" in text
        assert "Background reference" in text
        # Past experience should come first
        assert text.index("## Past Experience") < text.index("## Combat Guide")
        # Full guide text preserved on R2+ — no more first-sentence truncation.
        assert "Pommel Strike is MVP" in text
        assert "Prioritize raw damage output" in text

    def test_non_combat_shows_full_guide(self):
        wc = WorkingContext(
            route_guide_hints=("[Route Guide Act 1] Prioritize elites early.",),
            current_round=0,
        )
        text = format_working_context(wc)
        assert "Prioritize elites" in text

    def test_r2_keeps_full_multi_sentence_guide(self):
        """Regression: R2+ must NOT chop the guide to the first sentence.

        Prior behavior truncated to ``first_sentence[:77] + "..."`` which
        dropped the actionable half of every multi-sentence guide.
        """
        wc = WorkingContext(
            combat_guide_hints=(
                "Long guide text sentence one. Sentence two about more stuff. "
                "Sentence three has the actionable advice.",
            ),
            current_round=5,
        )
        text = format_working_context(wc)
        assert "sentence one." in text.lower()
        assert "Sentence two about more stuff" in text
        assert "Sentence three has the actionable advice" in text
        assert "..." not in text


class TestThreatBanner:
    def test_high_threat_adds_survival_banner(self):
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="lethal",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" in text
        assert "lethal" in text

    def test_medium_threat_no_banner(self):
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="medium",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" not in text

    def test_low_threat_no_banner(self):
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="low",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" not in text

    def test_empty_threat_level_no_banner(self):
        wc = WorkingContext(
            situation_hints=("### Similar Past Situation",),
            current_round=2,
            current_threat_level="",
        )
        text = format_working_context(wc)
        assert "SURVIVAL PRIORITY" not in text


class TestMetadataPassthrough:
    def test_current_round_on_working_context(self):
        wc = WorkingContext(current_round=3, current_threat_level="high")
        assert wc.current_round == 3
        assert wc.current_threat_level == "high"

    def test_defaults(self):
        wc = WorkingContext()
        assert wc.current_round == 0
        assert wc.current_threat_level == ""

    def test_metadata_not_in_is_empty(self):
        """Metadata fields should not affect is_empty."""
        wc = WorkingContext(current_round=3, current_threat_level="high")
        assert wc.is_empty is True  # no actual content
