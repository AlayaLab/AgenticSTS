import pytest
from pathlib import Path
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _sk(sid, name="n", content="c"):
    return Skill(skill_id=sid, name=name, content=content, trigger=SkillTrigger())


def test_replace_deactivates_old_and_stamps_new():
    lib = SkillLibrary()
    lib.add(_sk("s_old", name="old"))
    lib.replace("s_old", _sk("s_new", name="new"))

    stored_old = lib.get("s_old")
    assert stored_old is not None
    assert stored_old.active is False
    assert stored_old.superseded_by == "s_new"

    stored_new = lib.get("s_new")
    assert stored_new is not None
    assert stored_new.active is True


def test_replace_missing_old_raises():
    lib = SkillLibrary()
    with pytest.raises(KeyError):
        lib.replace("nope", _sk("s_new"))


def test_replace_duplicate_new_id_raises():
    lib = SkillLibrary()
    lib.add(_sk("s_old"))
    lib.add(_sk("s_collide"))
    with pytest.raises(ValueError):
        lib.replace("s_old", _sk("s_collide"))


def test_replace_roundtrips_through_save_load(tmp_path: Path):
    path = tmp_path / "sk.json"
    lib = SkillLibrary()
    lib.add(_sk("s_old"))
    lib.replace("s_old", _sk("s_new"))
    lib.save(path)

    reopened = SkillLibrary.load(path)
    old = reopened.get("s_old")
    new = reopened.get("s_new")
    assert old is not None and old.active is False
    assert old.superseded_by == "s_new"
    assert new is not None and new.active is True


def test_replace_with_same_id_is_allowed():
    """In-place replacement using same skill_id should work (edge case).

    Old is still deactivated; new takes the same slot with active=True
    because it's literally replacing itself — useful during an update-via-merge
    flow where the merged skill happens to reuse the old id.
    """
    lib = SkillLibrary()
    lib.add(_sk("s_same", name="v1"))
    lib.replace("s_same", _sk("s_same", name="v2"))
    stored = lib.get("s_same")
    assert stored is not None
    assert stored.name == "v2"
    assert stored.active is True  # new active skill wins the slot
    assert stored.superseded_by == ""  # not self-referential
    assert stored.status == "active"
