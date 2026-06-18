"""Regression tests for plan-time target_index remapping after mid-plan enemy deaths.

The mod renumbers surviving enemies after each death: if old enemy 0 dies, the
previous indices 1 and 2 become 0 and 1 respectively. The plan was authored
against the original indices, so the agent must remap stale indices to the
current positional slot of the same creature before sending the action.
"""
from __future__ import annotations

from dataclasses import dataclass

from src.agent.loop import AgentLoop


@dataclass(frozen=True)
class _FakeEnemy:
    index: int
    enemy_id: str


class _LoopStub:
    """Lightweight stand-in with just the attributes _remap_plan_target reads."""

    def __init__(self, snapshot):
        self._combat_plan_enemy_ids = tuple(snapshot)

    # Reuse the real implementation — it only touches the snapshot attribute.
    _remap_plan_target = AgentLoop._remap_plan_target


def _make(snapshot, current):
    enemies = [_FakeEnemy(index=i, enemy_id=eid) for i, eid in enumerate(current)]
    return _LoopStub(snapshot), enemies


def test_remap_unchanged_when_no_deaths():
    stub, enemies = _make(["A", "B", "C"], ["A", "B", "C"])
    assert stub._remap_plan_target(0, enemies) == 0
    assert stub._remap_plan_target(1, enemies) == 1
    assert stub._remap_plan_target(2, enemies) == 2


def test_remap_after_first_enemy_dies():
    # The reported bug: plan targets old enemy 2 (index 2); after old 0 dies,
    # survivors renumber to 0 and 1. Plan-time index 2 must map to current 1.
    stub, enemies = _make(["A", "B", "C"], ["B", "C"])
    assert stub._remap_plan_target(2, enemies) == 1  # old C is now index 1
    assert stub._remap_plan_target(1, enemies) == 0  # old B is now index 0
    assert stub._remap_plan_target(0, enemies) is None  # old A died


def test_remap_after_middle_enemy_dies():
    stub, enemies = _make(["A", "B", "C"], ["A", "C"])
    assert stub._remap_plan_target(0, enemies) == 0
    assert stub._remap_plan_target(1, enemies) is None  # B died
    assert stub._remap_plan_target(2, enemies) == 1  # C now at 1


def test_remap_after_last_enemy_dies():
    stub, enemies = _make(["A", "B", "C"], ["A", "B"])
    assert stub._remap_plan_target(0, enemies) == 0
    assert stub._remap_plan_target(1, enemies) == 1
    assert stub._remap_plan_target(2, enemies) is None


def test_remap_duplicates_preserve_relative_order():
    # Two Smugs + one Boss. Plan targets "second Smug" (index 2).
    stub, enemies = _make(["boss", "smug", "smug"], ["smug", "smug"])
    # Boss died. Remaining two Smugs — the plan-time "second smug" (index 2)
    # is the second surviving smug, now at index 1.
    assert stub._remap_plan_target(0, enemies) is None
    assert stub._remap_plan_target(1, enemies) == 0
    assert stub._remap_plan_target(2, enemies) == 1


def test_remap_duplicates_first_of_pair_dies():
    stub, enemies = _make(["smug", "smug", "boss"], ["smug", "boss"])
    # Ambiguous by enemy_id alone, but sequential matching preserves order:
    # first snapshot smug pairs with the only remaining smug.
    assert stub._remap_plan_target(0, enemies) == 0
    # Plan-time "second smug" (idx 1) has no surviving pair — return None.
    assert stub._remap_plan_target(1, enemies) is None
    # Boss maps to index 1 (after consuming the smug).
    assert stub._remap_plan_target(2, enemies) == 1


def test_remap_no_snapshot_returns_none():
    stub = _LoopStub([])
    stub._combat_plan_enemy_ids = None
    enemies = [_FakeEnemy(index=0, enemy_id="A")]
    assert stub._remap_plan_target(0, enemies) is None


def test_remap_out_of_range_plan_target():
    stub, enemies = _make(["A", "B"], ["A", "B"])
    assert stub._remap_plan_target(5, enemies) is None
    assert stub._remap_plan_target(-1, enemies) is None


def test_remap_all_enemies_died():
    stub, enemies = _make(["A", "B"], [])
    assert stub._remap_plan_target(0, enemies) is None
    assert stub._remap_plan_target(1, enemies) is None
