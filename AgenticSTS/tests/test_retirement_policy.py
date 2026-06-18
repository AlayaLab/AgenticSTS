import json
import tempfile
from pathlib import Path
from dataclasses import replace

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode
from src.skills.library import SkillLibrary
from src.skills.models import Skill, SkillTrigger
from src.skills.lifecycle import (
    apply_retirement_policy,
    update_skill_usage_from_run,
)


def _ep(run_id="r", enemy_key="Rat", hp=100, dmg=10, skills=()):
    return CombatEpisode(
        run_id=run_id, enemy_key=enemy_key, combat_type="monster",
        character="silent", act=1, hp_before=hp, total_damage_taken=dmg,
        retrieved_skill_ids=skills,
    )


def test_retirement_seed_skill_floors_at_0_40():
    lib = SkillLibrary()
    lib.add(Skill(skill_id="seed_x", name="Seed", source="seed", confidence=0.15))
    apply_retirement_policy(lib)
    sk = next(s for s in lib.all_skills if s.skill_id == "seed_x")
    assert sk.confidence == 0.40
    assert sk.status == "active"  # seed NEVER deactivates


def test_retirement_low_confidence_high_usage_deactivates():
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.25, usage_count=12, status="active",
    ))
    deactivated = apply_retirement_policy(lib)
    assert "t1" in deactivated
    sk = next(s for s in lib.all_skills if s.skill_id == "t1")
    assert sk.status == "deactivated"


def test_retirement_low_confidence_low_usage_keeps_active():
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.20, usage_count=5, status="active",  # usage < 10
    ))
    deactivated = apply_retirement_policy(lib)
    assert deactivated == []
    sk = next(s for s in lib.all_skills if s.skill_id == "t1")
    assert sk.status == "active"


def test_retirement_three_unimproved_runs_deactivates():
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.55, usage_count=5,
        consecutive_unimproved_runs=3, status="active",
    ))
    deactivated = apply_retirement_policy(lib)
    assert "t1" in deactivated


def test_retirement_already_deactivated_skipped():
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.10, usage_count=20, status="deactivated",
    ))
    deactivated = apply_retirement_policy(lib)
    assert deactivated == []  # already deactivated, not double-counted


def test_update_skill_usage_resets_counter_on_improved(tmp_path):
    """If ANY combat this run hits 'improved', counter resets to 0."""
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.50, consecutive_unimproved_runs=2,
    ))
    store = CombatMemoryStore()
    # History: 5 episodes at loss 0.40 (baseline_a = 0.40)
    for i in range(5):
        store.add_batch([_ep(run_id=f"old{i}", hp=100, dmg=40)])

    # This run: one combat with loss 0.10 (improved!)
    ep = _ep(run_id="r_now", hp=100, dmg=10, skills=("t1",))
    update_skill_usage_from_run(
        this_run_episodes=[ep],
        skill_library=lib,
        combat_store=store,
        usage_log_path=tmp_path / "u.jsonl",
    )
    sk = next(s for s in lib.all_skills if s.skill_id == "t1")
    assert sk.consecutive_unimproved_runs == 0  # reset


def test_update_skill_usage_increments_counter_on_worse(tmp_path):
    """If NO combat this run hits 'improved', counter increments."""
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.50, consecutive_unimproved_runs=1,
    ))
    store = CombatMemoryStore()
    for i in range(5):
        store.add_batch([_ep(run_id=f"old{i}", hp=100, dmg=10)])  # baseline 0.10
    ep = _ep(run_id="r_now", hp=100, dmg=50, skills=("t1",))  # worse
    update_skill_usage_from_run(
        this_run_episodes=[ep],
        skill_library=lib,
        combat_store=store,
        usage_log_path=tmp_path / "u.jsonl",
    )
    sk = next(s for s in lib.all_skills if s.skill_id == "t1")
    assert sk.consecutive_unimproved_runs == 2  # incremented


def test_update_skill_usage_best_outcome_improved_wins(tmp_path):
    """2 combats: one 'unchanged', one 'improved' -> counter resets."""
    lib = SkillLibrary()
    lib.add(Skill(
        skill_id="t1", name="T1", source="mistake_driven",
        confidence=0.50, consecutive_unimproved_runs=2,
    ))
    store = CombatMemoryStore()
    for i in range(5):
        store.add_batch([_ep(run_id=f"old{i}", hp=100, dmg=20)])  # baseline 0.20

    ep1 = _ep(run_id="r_now", hp=100, dmg=20, skills=("t1",))   # unchanged
    ep2 = _ep(run_id="r_now", hp=100, dmg=5, skills=("t1",))    # improved
    update_skill_usage_from_run(
        this_run_episodes=[ep1, ep2],
        skill_library=lib,
        combat_store=store,
        usage_log_path=tmp_path / "u.jsonl",
    )
    sk = next(s for s in lib.all_skills if s.skill_id == "t1")
    # 'improved' in ep2 wins over 'unchanged' in ep1
    assert sk.consecutive_unimproved_runs == 0
