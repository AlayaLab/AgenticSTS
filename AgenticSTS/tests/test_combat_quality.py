from __future__ import annotations

from src.skills.combat_quality import compute_combat_quality_score
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def test_monster_clean_and_costly_wins_score_differently():
    assert compute_combat_quality_score("monster", 100, 97, won=True) == 1.0
    assert compute_combat_quality_score("monster", 100, 70, won=True) == 0.45


def test_elite_and_boss_mid_tiers_use_expected_buckets():
    assert compute_combat_quality_score("elite", 100, 75, won=True) == 0.75
    assert compute_combat_quality_score("boss", 100, 65, won=True) == 0.80


def test_boss_costly_win_is_weighted_higher_than_monster_costly_win():
    monster = compute_combat_quality_score("monster", 100, 60, won=True)
    boss = compute_combat_quality_score("boss", 100, 60, won=True)
    assert boss > monster


def test_unknown_combat_type_falls_back_to_neutral_win_weight():
    assert compute_combat_quality_score("unknown", 100, 50, won=True) == 1.0


def test_losses_keep_full_failure_weight():
    assert compute_combat_quality_score("elite", 50, 0, won=False) == 1.0


def test_loss_weight_is_applied_as_failure_not_high_quality():
    skill = Skill(
        skill_id="loss-test",
        name="Loss Test",
        category="combat",
        trigger=SkillTrigger(),
        content="Test",
    )
    library = SkillLibrary((skill,))
    quality = compute_combat_quality_score("boss", 80, 0, won=False)
    library.record_outcome(["loss-test"], success=False, quality_score=quality)
    updated = library.get("loss-test")
    assert updated is not None
    assert updated.success_count == 0
    assert updated.failure_count == 1
