"""Tests for trajectory loading + rendering in postrun stage 5.

Critical: per spec section 6 Part B, non-combat stubs (deckbuilding/map/
intermission) MUST receive trajectory evidence (full per-decision context
with reasoning, strategic_note, HP/Gold/Deck delta) — not just a thin
Attribution Summary. The previous Task 15 implementation deferred this;
this test locks the contract that trajectory is now wired in.
"""

import json
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.agent.loop import AgentLoop


def _empty_agent() -> AgentLoop:
    return AgentLoop.__new__(AgentLoop)


def test_load_decisions_for_run_method_exists():
    """Helper that reads JSONL run log and returns LoggedDecision-shaped objects."""
    assert hasattr(AgentLoop, "_load_decisions_for_run")


def test_load_decisions_for_run_returns_empty_for_unknown_run():
    """Missing run log → empty list, no exception."""
    agent = _empty_agent()
    decisions = agent._load_decisions_for_run("run_does_not_exist")
    assert decisions == []


def test_load_decisions_for_run_parses_real_log(tmp_path, monkeypatch):
    """Build a minimal JSONL with state + decision events, verify parse + adapter."""
    run_id = "test_run_001"
    log_dir = tmp_path / "logs"
    log_dir.mkdir()
    log_file = log_dir / f"run_{run_id}.jsonl"

    # Sequence: state_before -> decision -> state_after
    events = [
        {"event": "state", "run_id": run_id, "step": 5, "floor": 1,
         "state_type": "card_reward", "player": {"hp_current": 70, "max_hp": 70, "gold": 0},
         "deck_size": 12, "deck": ["Strike", "Defend"]},
        {"event": "decision", "run_id": run_id, "step": 5, "floor": 1,
         "state_type": "card_reward", "source": "llm",
         "action": {"action": "resolve_rewards", "option_index": 1},
         "reasoning": "Backstab is premium",
         "strategic_note": "Foundation: frontload damage"},
        {"event": "state", "run_id": run_id, "step": 6, "floor": 1,
         "state_type": "map", "player": {"hp_current": 70, "max_hp": 70, "gold": 0},
         "deck_size": 13, "deck": ["Strike", "Defend", "Backstab"]},
    ]
    with log_file.open("w", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev) + "\n")

    # Patch paths so the loader looks under our tmp_path
    monkeypatch.setattr(
        "src.agent.loop._run_log_path",
        lambda rid: log_dir / f"run_{rid}.jsonl",
        raising=False,
    )

    agent = _empty_agent()
    decisions = agent._load_decisions_for_run(run_id, log_dir=log_dir)
    assert len(decisions) == 1
    d = decisions[0]
    # render_trajectory_for_stub expects floor as "F<n>" string
    assert d.floor == "F1"
    assert d.state_type == "card_reward"
    assert d.action == "resolve_rewards"
    assert d.option_index == 1
    assert d.reasoning == "Backstab is premium"
    assert d.strategic_note == "Foundation: frontload damage"
    # Deck delta computed from before/after states
    assert d.deck_before == 12
    assert d.deck_after == 13
    # deck_change is non-trivial (either set-diff or size-delta string)
    assert d.deck_change != "no change"


@pytest.mark.asyncio
async def test_post_run_fill_stubs_uses_trajectory_for_non_combat(tmp_path, monkeypatch):
    """When stage 5 fires for a deckbuilding stub, trajectory + Attribution
    are BOTH included in evidence_by_stub (not just Attribution alone)."""
    import importlib
    os.environ["STS2_SEED_STUB_FILL_ENABLED"] = "true"
    os.environ["STS2_USE_SEED_STUBS"] = "true"

    try:
        import config as _cfg
        importlib.reload(_cfg)

        from src.skills.library import SkillLibrary
        from src.runs.history import RunRecord

        # Build minimal agent
        agent = _empty_agent()
        agent._memory = None
        agent._skill_library = SkillLibrary()
        stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
        agent._skill_library.load_seed_stubs(stub_dir, character="the silent")

        agent._run_state = SimpleNamespace(
            run_id="r1", character="the silent",
            actual_ascension=0, victory=False,
        )

        # Capture evidence built before backend.call by patching StubFiller
        captured_evidence = {}
        from src.skills import stub_filler as _sf

        async def _spy_afill_all(self, *, character, evidence_by_stub):
            captured_evidence.update(evidence_by_stub)
            return {"filled_count": 0, "skipped_count": len(evidence_by_stub),
                    "warnings_by_stub": {}}
        monkeypatch.setattr(_sf.StubFiller, "afill_all_stubs", _spy_afill_all)

        # Patch RunHistoryStore.load to return a single fake run
        fake_record = SimpleNamespace(
            run_id="r1", character="the silent", outcome="defeat",
            started_at=1.0, actual_ascension=0,
        )
        from src.runs import history as _hist
        class _FakeStore:
            def query(self, **kwargs):
                return [fake_record]
        monkeypatch.setattr(_hist.RunHistoryStore, "load", classmethod(lambda cls, p: _FakeStore()))

        # Provide a decision-loading stub so the deckbuilding trajectory has content
        def _fake_load_decisions(run_id, log_dir=None):
            return [SimpleNamespace(
                floor="F5", state_type="card_reward",
                action="resolve_rewards", option_index=1,
                reasoning="Tester reasoning",
                strategic_note="Foundation phase",
                hp_before=70, hp_after=70,
                gold_before=0, gold_after=0,
                deck_before=12, deck_after=13,
                deck_change="+Backstab",
            )]
        monkeypatch.setattr(AgentLoop, "_load_decisions_for_run", _fake_load_decisions)

        # Stub backend & paths (patched but not actually called because spy returns early)
        from src.brain import v2_backend
        monkeypatch.setattr(v2_backend, "V2Backend", lambda: object())

        await agent._post_run_fill_stubs()

        # Deckbuilding stub evidence must contain trajectory markers
        deckbuilding = captured_evidence.get("stub_the_silent_deckbuilding", "")
        assert "Tester reasoning" in deckbuilding, (
            "trajectory reasoning missing — non-combat stub got only Attribution Summary"
        )
        assert "Foundation phase" in deckbuilding, "strategic note missing"
        assert "card_reward" in deckbuilding
        assert "## Deckbuilding Trajectory" in deckbuilding
    finally:
        for k in ("STS2_SEED_STUB_FILL_ENABLED", "STS2_USE_SEED_STUBS"):
            os.environ.pop(k, None)
        import config as _cfg
        importlib.reload(_cfg)
