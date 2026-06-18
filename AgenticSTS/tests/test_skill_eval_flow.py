"""Test skill eval state machine flow."""
from src.skills.replay_evaluator import (
    ReplayResult,
    build_eval_schedule,
    compute_confidence_deltas,
    remaining_plan_kills_boss,
)


def test_full_eval_flow_data():
    """Simulate a full eval: original + 2 alternatives, verify confidence."""
    original = ReplayResult("orig", ("s1", "s2", "s3"), hp_lost=20, rounds=8, potions_used=1, won=True)
    alt1 = ReplayResult("alt1", ("s1", "u1", "u2"), hp_lost=10, rounds=5, potions_used=0, won=True)
    alt2 = ReplayResult("alt2", ("s1", "u3", "u4"), hp_lost=35, rounds=12, potions_used=2, won=True)

    deltas = compute_confidence_deltas([original, alt1, alt2])
    # u1, u2 only in best (alt1) → positive
    assert deltas.get("u1", 0) > 0
    assert deltas.get("u2", 0) > 0
    # u3, u4 only in worst (alt2) → negative
    assert deltas.get("u3", 0) < 0
    assert deltas.get("u4", 0) < 0
    # s2, s3 only in original (middle) → no change
    # s1 in all → no change


def test_schedule_consumes_pool():
    """Verify pool is consumed so skills aren't retested."""
    result = build_eval_schedule(
        original_skill_ids=["s1", "s2", "s3", "s4"],
        all_skills_pool=[("u1", 0), ("u2", 0), ("u3", 0), ("u4", 0), ("u5", 0), ("u6", 0)],
        max_replays=2,
    )
    assert len(result) == 2
    # All skill IDs across both sets should be unique (no re-testing)
    all_replacements = []
    for skill_set in result:
        replacements = [s for s in skill_set if s.startswith("u")]
        all_replacements.extend(replacements)
    assert len(all_replacements) == len(set(all_replacements))


def test_kill_detection_multi_card():
    """Multiple remaining cards sum to kill."""
    class C:
        def __init__(self, n, d):
            self.name = n
            self.damage = d
            self.total_damage = d
            self.target_previews = []

    class E:
        def __init__(self, hp, block=0):
            self.index = 0
            self.current_hp = hp
            self.hp = hp
            self.block = block
            self.is_alive = True

    class A:
        def __init__(self, name):
            self.card_name = name
            self.is_potion = False
            self.target_index = 0

    hand = [C("Strike", 6), C("Strike", 6), C("Bash", 10)]
    enemies = [E(hp=20, block=0)]
    remaining = [A("Strike"), A("Strike"), A("Bash")]
    assert remaining_plan_kills_boss(hand, enemies, remaining) is True
