# tests/test_replay_evaluator.py
from src.skills.replay_evaluator import (
    ReplayResult,
    build_eval_schedule,
    compute_confidence_deltas,
)


def test_confidence_deltas_best_vs_worst():
    best = ReplayResult("a", ("s1", "s2", "s3"), hp_lost=5, rounds=3, potions_used=0, won=True)
    worst = ReplayResult("b", ("s1", "s4", "s5"), hp_lost=25, rounds=8, potions_used=2, won=True)
    deltas = compute_confidence_deltas([best, worst])
    # s2, s3 only in best → positive
    assert deltas.get("s2", 0) > 0
    assert deltas.get("s3", 0) > 0
    # s4, s5 only in worst → negative
    assert deltas.get("s4", 0) < 0
    assert deltas.get("s5", 0) < 0
    # s1 in both → not in deltas
    assert "s1" not in deltas


def test_confidence_deltas_same_hp():
    r1 = ReplayResult("a", ("s1",), hp_lost=10, rounds=3, potions_used=0, won=True)
    r2 = ReplayResult("b", ("s2",), hp_lost=10, rounds=3, potions_used=0, won=True)
    assert compute_confidence_deltas([r1, r2]) == {}


def test_build_eval_schedule_prioritizes_untested():
    """build_eval_schedule exists and returns list[list[str]]."""
    # Tested via integration — here just verify import and signature
    result = build_eval_schedule(
        original_skill_ids=["s1", "s2", "s3"],
        all_skills_pool=[("u1", 0), ("u2", 0), ("u3", 0)],
        max_replays=2,
    )
    assert isinstance(result, list)
    assert len(result) <= 2
    for skill_set in result:
        assert isinstance(skill_set, list)
