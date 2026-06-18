from src.memory.write_gate import _trigger_tags_from_skill
from src.skills.models import Skill, SkillTrigger


def test_trigger_tags_has_only_active_fields():
    s = Skill(
        name="t",
        trigger=SkillTrigger(
            state_types=frozenset({"monster"}),
            enemy_names=frozenset({"Rat"}),
            requires_hand_capabilities=frozenset({"can_apply_weak"}),
            requires_enemy_powers=frozenset({"Strength"}),
        ),
    )
    tags = _trigger_tags_from_skill(s)
    assert "state_types:monster" in tags
    assert "enemy_names:Rat" in tags
    assert "requires_hand_capabilities:can_apply_weak" in tags
    assert "requires_enemy_powers:Strength" in tags
    # Removed fields must not appear:
    assert not any(t.startswith("threat_levels:") for t in tags)
    assert not any(t.startswith("intent_classes:") for t in tags)
    assert not any(t.startswith("deck_stages:") for t in tags)
    assert not any(t.startswith("tags:") for t in tags)


def test_trigger_tags_empty_on_empty_trigger():
    s = Skill(name="t", trigger=SkillTrigger())
    tags = _trigger_tags_from_skill(s)
    assert tags == frozenset()


def test_trigger_tags_handles_none_trigger():
    """Duck-typed path: if skill has no trigger attr, return empty set."""
    class DuckSkill:
        name = "fake"
    tags = _trigger_tags_from_skill(DuckSkill())
    assert tags == frozenset()
