from src.skills.lifecycle import classify_combat_outcome


def test_improved_when_below_baseline_minus_delta():
    # baseline 0.30, delta 0.10 -> improved if actual <= 0.20
    assert classify_combat_outcome(actual=0.15, baseline=0.30, combat_type="monster") == "improved"
    assert classify_combat_outcome(actual=0.20, baseline=0.30, combat_type="monster") == "improved"


def test_unchanged_near_baseline():
    assert classify_combat_outcome(actual=0.30, baseline=0.30, combat_type="monster") == "unchanged"
    assert classify_combat_outcome(actual=0.25, baseline=0.30, combat_type="monster") == "unchanged"


def test_worse_above_baseline_plus_delta():
    assert classify_combat_outcome(actual=0.45, baseline=0.30, combat_type="monster") == "worse"


def test_delta_varies_by_combat_type():
    # monster delta = 0.10, boss delta = 0.20
    # Boss: baseline=0.30, delta=0.20 => improved if <= 0.10, worse if >= 0.50
    assert classify_combat_outcome(actual=0.08, baseline=0.30, combat_type="boss") == "improved"
    assert classify_combat_outcome(actual=0.10, baseline=0.30, combat_type="boss") == "improved"
    assert classify_combat_outcome(actual=0.51, baseline=0.30, combat_type="boss") == "worse"


def test_confidence_mult_table_exists():
    from src.skills.lifecycle import CONFIDENCE_MULT
    assert CONFIDENCE_MULT == {"improved": 1.10, "unchanged": 0.98, "worse": 0.85}


import json
from pathlib import Path

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger


def _ep(*, run_id="r_now", enemy_key="Rat", hp=100, dmg=40, skills=("s1",)):
    return CombatEpisode(
        run_id=run_id, enemy_key=enemy_key, combat_type="monster",
        character="silent", act=1, hp_before=hp, total_damage_taken=dmg,
        retrieved_skill_ids=skills,
    )


def test_update_skill_usage_improved_boosts_confidence(tmp_path):
    from src.skills.lifecycle import update_skill_usage_from_run
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s1", name="Test", confidence=0.50))

    store = CombatMemoryStore()
    # History: 5 previous episodes at 0.40 loss_ratio
    for i in range(5):
        store.add_batch([_ep(run_id=f"r_old{i}", hp=100, dmg=40, skills=())])
    ep_this = _ep(run_id="r_now", hp=100, dmg=10, skills=("s1",))  # loss 0.10, baseline 0.40 -> improved

    usage_log = tmp_path / "skill_usage.jsonl"
    update_skill_usage_from_run(
        this_run_episodes=[ep_this],
        skill_library=lib,
        combat_store=store,
        usage_log_path=usage_log,
    )

    sk = next((s for s in lib.all_skills if s.skill_id == "s1"), None)
    assert sk is not None
    assert sk.confidence > 0.50

    assert usage_log.exists()
    line = usage_log.read_text().strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["skill_id"] == "s1"
    assert rec["outcome"] == "improved"


def test_update_skill_usage_worse_decays_confidence(tmp_path):
    from src.skills.lifecycle import update_skill_usage_from_run
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s1", name="Test", confidence=0.50))
    store = CombatMemoryStore()
    for i in range(5):
        store.add_batch([_ep(run_id=f"r_old{i}", hp=100, dmg=20, skills=())])
    ep_this = _ep(run_id="r_now", hp=100, dmg=50, skills=("s1",))  # worse (0.50 vs ~0.20 baseline)
    update_skill_usage_from_run(
        this_run_episodes=[ep_this],
        skill_library=lib,
        combat_store=store,
        usage_log_path=tmp_path / "u.jsonl",
    )
    sk = next((s for s in lib.all_skills if s.skill_id == "s1"), None)
    assert sk is not None
    assert sk.confidence < 0.50


def test_update_skill_usage_no_retrieved_skills_skips(tmp_path):
    """Episodes with empty retrieved_skill_ids are skipped (nothing to attribute)."""
    from src.skills.lifecycle import update_skill_usage_from_run
    lib = SkillLibrary()
    lib.add(Skill(skill_id="s1", name="Test", confidence=0.50))
    store = CombatMemoryStore()
    ep = _ep(run_id="r_now", hp=100, dmg=10, skills=())  # no skills attributed
    usage_log = tmp_path / "u.jsonl"
    update_skill_usage_from_run(
        this_run_episodes=[ep],
        skill_library=lib,
        combat_store=store,
        usage_log_path=usage_log,
    )
    sk = next((s for s in lib.all_skills if s.skill_id == "s1"), None)
    assert sk.confidence == 0.50  # unchanged
    # Usage log should be empty or not exist
    if usage_log.exists():
        assert usage_log.read_text().strip() == ""
