from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _make_lib():
    lib = SkillLibrary.__new__(SkillLibrary)
    lib._skills = {}
    lib._active_override = None
    s1 = Skill(skill_id="s1", name="S1", category="combat",
               content="test", trigger=SkillTrigger())
    s2 = Skill(skill_id="s2", name="S2", category="combat",
               content="test2", trigger=SkillTrigger())
    lib._skills = {"s1": s1, "s2": s2}
    return lib


def test_set_active_override():
    lib = _make_lib()
    assert lib._active_override is None
    lib.set_active_override(["s1"])
    assert lib._active_override == {"s1"}
    results = lib.query(state_type="combat", limit=10)
    assert len(results) == 1
    assert results[0][0].skill_id == "s1"


def test_clear_active_override():
    lib = _make_lib()
    lib.set_active_override(["s1"])
    lib.clear_active_override()
    assert lib._active_override is None


def test_set_override_missing_id_ignored():
    lib = _make_lib()
    lib.set_active_override(["s1", "nonexistent"])
    results = lib.query(state_type="combat", limit=10)
    assert len(results) == 1
