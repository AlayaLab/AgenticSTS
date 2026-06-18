"""Tests for non-combat skill scoring integration: Skill model + SkillLibrary."""

from src.skills.models import Skill

# ── Skill.with_noncombat_score ───────────────────────────────────────


def test_with_noncombat_score_appends():
    """with_noncombat_score returns a new Skill with score appended."""
    skill = Skill(skill_id="s1", name="Test", category="map")
    updated = skill.with_noncombat_score(25.0)
    assert updated.recent_noncombat_scores == (25.0,)
    # Original is unchanged (frozen)
    assert skill.recent_noncombat_scores == ()


def test_with_noncombat_score_keeps_last_3():
    """Only the last 3 scores are kept."""
    skill = Skill(
        skill_id="s1", name="Test",
        recent_noncombat_scores=(10.0, 20.0, 30.0),
    )
    updated = skill.with_noncombat_score(40.0)
    assert updated.recent_noncombat_scores == (20.0, 30.0, 40.0)


def test_with_noncombat_score_grows_to_3():
    """Scores accumulate up to 3 before trimming."""
    skill = Skill(skill_id="s1", name="Test")
    s1 = skill.with_noncombat_score(10.0)
    s2 = s1.with_noncombat_score(20.0)
    s3 = s2.with_noncombat_score(30.0)
    assert s3.recent_noncombat_scores == (10.0, 20.0, 30.0)
    s4 = s3.with_noncombat_score(40.0)
    assert s4.recent_noncombat_scores == (20.0, 30.0, 40.0)


def test_with_noncombat_score_immutable():
    """Original skill is not mutated."""
    skill = Skill(
        skill_id="s1", name="Test",
        recent_noncombat_scores=(10.0,),
    )
    updated = skill.with_noncombat_score(20.0)
    assert skill.recent_noncombat_scores == (10.0,)
    assert updated.recent_noncombat_scores == (10.0, 20.0)


# ── Serialization round-trip ─────────────────────────────────────────


def test_to_dict_includes_noncombat_scores():
    """to_dict serializes recent_noncombat_scores."""
    skill = Skill(
        skill_id="s1", name="Test",
        recent_noncombat_scores=(25.0, 30.5),
    )
    d = skill.to_dict()
    assert d["recent_noncombat_scores"] == [25.0, 30.5]


def test_from_dict_loads_noncombat_scores():
    """from_dict deserializes recent_noncombat_scores."""
    d = {"skill_id": "s1", "name": "Test", "recent_noncombat_scores": [10.0, 20.0, 30.0]}
    skill = Skill.from_dict(d)
    assert skill.recent_noncombat_scores == (10.0, 20.0, 30.0)


def test_from_dict_missing_noncombat_scores():
    """from_dict defaults to empty tuple for old data without noncombat scores."""
    d = {"skill_id": "s1", "name": "Test"}
    skill = Skill.from_dict(d)
    assert skill.recent_noncombat_scores == ()


# ── SkillLibrary.record_noncombat_outcome ────────────────────────────


def test_record_noncombat_outcome_updates_scores():
    """record_noncombat_outcome appends score to matching skills."""
    from src.skills.library import SkillLibrary

    s1 = Skill(skill_id="s1", name="Map Routing", category="map")
    s2 = Skill(skill_id="s2", name="Rest Strategy", category="rest")
    lib = SkillLibrary(skills=(s1, s2))

    lib.record_noncombat_outcome(["s1", "s2"], 28.0)

    assert lib.get("s1").recent_noncombat_scores == (28.0,)
    assert lib.get("s2").recent_noncombat_scores == (28.0,)


def test_record_noncombat_outcome_skips_missing():
    """Unknown skill IDs are silently skipped."""
    from src.skills.library import SkillLibrary

    s1 = Skill(skill_id="s1", name="Map Routing", category="map")
    lib = SkillLibrary(skills=(s1,))

    lib.record_noncombat_outcome(["s1", "nonexistent"], 28.0)

    assert lib.get("s1").recent_noncombat_scores == (28.0,)


def test_record_noncombat_outcome_skips_deactivated():
    """Deactivated skills are not scored."""
    from src.skills.library import SkillLibrary

    s1 = Skill(skill_id="s1", name="Map Routing", category="map", status="deactivated")
    lib = SkillLibrary(skills=(s1,))

    lib.record_noncombat_outcome(["s1"], 28.0)

    # Score should NOT be recorded for deactivated skill
    assert lib.get("s1").recent_noncombat_scores == ()


def test_record_noncombat_outcome_probation_on_low_avg():
    """Skills with 3+ scores and avg < 15 get put on probation."""
    from src.skills.library import SkillLibrary

    # Skill with 2 existing low scores
    s1 = Skill(
        skill_id="s1", name="Bad Strategy", category="map",
        recent_noncombat_scores=(8.0, 10.0),
    )
    lib = SkillLibrary(skills=(s1,))

    # Third score makes avg = (8+10+12)/3 = 10 < 15
    lib.record_noncombat_outcome(["s1"], 12.0)

    result = lib.get("s1")
    assert result.recent_noncombat_scores == (8.0, 10.0, 12.0)
    assert result.status == "probation"


def test_record_noncombat_outcome_no_probation_when_avg_ok():
    """Skills with avg >= 15 stay active."""
    from src.skills.library import SkillLibrary

    s1 = Skill(
        skill_id="s1", name="Good Strategy", category="map",
        recent_noncombat_scores=(20.0, 25.0),
    )
    lib = SkillLibrary(skills=(s1,))

    lib.record_noncombat_outcome(["s1"], 30.0)

    result = lib.get("s1")
    assert result.recent_noncombat_scores == (20.0, 25.0, 30.0)
    assert result.status == "active"


def test_record_noncombat_outcome_no_probation_under_3_scores():
    """Don't judge skills with fewer than 3 scores."""
    from src.skills.library import SkillLibrary

    s1 = Skill(
        skill_id="s1", name="New Strategy", category="map",
        recent_noncombat_scores=(5.0,),
    )
    lib = SkillLibrary(skills=(s1,))

    # Only 2 scores after this - not enough to judge
    lib.record_noncombat_outcome(["s1"], 6.0)

    result = lib.get("s1")
    assert result.recent_noncombat_scores == (5.0, 6.0)
    assert result.status == "active"


def test_record_noncombat_outcome_already_probation_stays():
    """Skills already on probation don't get double-probationed."""
    from src.skills.library import SkillLibrary

    s1 = Skill(
        skill_id="s1", name="Weak Strategy", category="map",
        status="probation",
        recent_noncombat_scores=(5.0, 6.0),
    )
    lib = SkillLibrary(skills=(s1,))

    lib.record_noncombat_outcome(["s1"], 7.0)

    result = lib.get("s1")
    assert result.recent_noncombat_scores == (5.0, 6.0, 7.0)
    # Probation check only applies to "active" skills
    assert result.status == "probation"
