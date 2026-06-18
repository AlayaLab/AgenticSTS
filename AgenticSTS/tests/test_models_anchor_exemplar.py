import dataclasses
import pytest
from src.skills.models import AnchorExemplar, Skill, SkillTrigger


def test_anchor_exemplar_is_frozen_with_defaults():
    anchor = AnchorExemplar(
        run_id="run_123",
        llm_call_seq=42,
        expected_correction="play Defend before Strike",
    )
    assert anchor.counterfactual_note == ""
    assert anchor.episode_id == ""
    assert anchor.round_num == 0
    with pytest.raises(dataclasses.FrozenInstanceError):
        anchor.run_id = "other"  # type: ignore[misc]


def test_skill_default_anchor_exemplars_is_empty_tuple():
    sk = Skill(
        skill_id="s_test",
        name="n",
        content="c",
        trigger=SkillTrigger(),
    )
    assert sk.anchor_exemplars == ()
    assert isinstance(sk.anchor_exemplars, tuple)


def test_skill_to_dict_round_trips_anchors():
    anchors = (
        AnchorExemplar(run_id="r1", llm_call_seq=5, expected_correction="x"),
        AnchorExemplar(run_id="r2", llm_call_seq=9, expected_correction="y",
                       counterfactual_note="cf", episode_id="ep_1", round_num=3),
    )
    sk = Skill(
        skill_id="s_test",
        name="n",
        content="c",
        trigger=SkillTrigger(),
        anchor_exemplars=anchors,
    )
    blob = sk.to_dict()
    assert "anchor_exemplars" in blob
    assert len(blob["anchor_exemplars"]) == 2
    assert blob["anchor_exemplars"][1]["counterfactual_note"] == "cf"

    restored = Skill.from_dict(blob)
    assert restored.anchor_exemplars == anchors


def test_skill_from_dict_handles_legacy_missing_anchors():
    legacy_blob = {
        "skill_id": "s_old",
        "name": "old",
        "content": "c",
        "trigger": {"state_types": []},
        "data_schema_version": 2,
    }
    sk = Skill.from_dict(legacy_blob)
    assert sk.anchor_exemplars == ()
