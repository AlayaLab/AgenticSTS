"""End-to-end mistake_discovery with mocked LLM calls (spec §8.4).

Single mistake episode -> critic produces valid candidate -> cascade
dedup passes -> A/B validator mocks helpful verdict -> skill persisted
with source='mistake_driven'.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.memory.combat_store import CombatMemoryStore
from src.memory.models_v2 import CombatEpisode, CombatRound
from src.memory.write_gate import EmbeddingClient, StaticSpanIndex, WriteGate
from src.skills.library import SkillLibrary
from src.skills.mistake_discovery import run_mistake_discovery


def _round(round_num: int = 1, dmg: int = 5, seq: int = 1) -> CombatRound:
    return CombatRound(
        round_num=round_num, hp_start=60, hp_end=60 - dmg,
        energy_available=3, damage_taken=dmg,
        hand_at_start=("Strike", "Defend"),
        enemy_intents=("Rat -> Attack 8",),
        incoming_damage=8, agent_plan=("Strike -> Rat",),
        llm_call_seq=seq,
    )


def _ep_mistake() -> CombatEpisode:
    return CombatEpisode(
        episode_id="ep_bad", run_id="run_now",
        enemy_key="Rat", combat_type="monster", character="silent",
        act=1, floor=2, hp_before=60, hp_after=30,
        total_damage_taken=30,  # loss_ratio 0.50
        rounds=(_round(round_num=1, dmg=15, seq=1), _round(round_num=2, dmg=15, seq=2)),
    )


def _ep_old(run_id: str, floor: int = 0, dmg: int = 10) -> CombatEpisode:
    return CombatEpisode(
        run_id=run_id, enemy_key="Rat", combat_type="monster",
        character="silent", act=1, floor=floor, hp_before=60,
        total_damage_taken=dmg,
        rounds=(_round(round_num=1, dmg=dmg, seq=0),),
    )


def _make_gate(tmp_path: Path) -> WriteGate:
    """Offline WriteGate: embedder disabled → lexical-only fallback (accepts)."""
    emb = EmbeddingClient(api_key="", cache_path=tmp_path / "emb_cache.json")
    idx = StaticSpanIndex(emb, evolution_dir=tmp_path)
    return WriteGate(
        embedder=emb, static_index=idx, log_path=tmp_path / "write_gate_log.jsonl",
    )


@pytest.mark.asyncio
async def test_run_mistake_discovery_happy_path(tmp_path, monkeypatch):
    # --- Setup ---
    # History: 5 episodes at loss 0.17 (baseline_a median = 0.17)
    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])
    store.add_batch([_ep_mistake()])

    # Run log with 3 llm_call events (seqs 0, 1, 2)
    log = tmp_path / "run_now.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seq in range(3):
            f.write(json.dumps({
                "event": "llm_call", "prompt": f"PROMPT_{seq}", "tier": "strategic"
            }) + "\n")

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    # --- Mock responses ---
    critic_json = json.dumps({
        "analysis": "Agent struck when should have blocked.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Block on Rat T1",
            "content": "Do play Defend on turn 1 against Rat; do NOT rush with Strike when incoming >= 8.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"], "enemy_names": ["Rat"],
                "character": "silent", "requires_cards": [],
                "requires_hand_capabilities": [], "any_of_relics": [],
                "requires_enemy_powers": []
            },
            "counterfactual_note": "Playing Defend would have saved ~7 damage per round.",
            "mistake_round_indices": [1, 2],  # 1-based round_num
            "expected_correction": "Defend -> self"
        }
    })
    redecide_txt = "plan: Defend -> self"
    judge_json = json.dumps({
        "verdict": "skill_helps", "hit_count_B": 3, "rationale": "B all block"
    })

    async def fake_call_raw(*, system="", prompt="", effort="", call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        if call_type == "mistake_redecide":
            return redecide_txt, 1.0, 50
        if call_type == "mistake_judge":
            return judge_json, 1.0, 80
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)
    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    # --- Exercise ---
    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store,
        skill_library=lib,
        write_gate=gate,
        log_path=log,
        run_id="run_now",
        combat_system_prompt="you are an STS2 agent",
    )

    # --- Verify ---
    assert stats["mistakes"] == 1
    assert stats["critic_skill_needed"] == 1
    assert stats["cascade_rejected"] == 0
    assert stats["ab_passed"] == 1
    assert stats["ab_failed"] == 0
    assert stats["persisted"] == 1

    persisted = [s for s in lib.all_skills if s.source == "mistake_driven"]
    assert len(persisted) == 1
    sk = persisted[0]
    assert sk.name == "Block on Rat T1"
    # confidence = 0.40 + 0.05 * len(mistake_round_indices) = 0.40 + 0.05*2 = 0.50
    assert sk.confidence == pytest.approx(0.50, abs=1e-6)
    assert "Rat" in sk.trigger.enemy_names


@pytest.mark.asyncio
async def test_run_mistake_discovery_stamps_anchor_exemplars(tmp_path, monkeypatch):
    """After Stage 6 persists, the landed skill carries AnchorExemplars built
    from the critic's mistake_round_indices + expected_correction + counterfactual_note,
    resolving ep.rounds[idx-1].llm_call_seq as the authoritative log anchor."""
    from src.skills.models import AnchorExemplar

    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])
    store.add_batch([_ep_mistake()])

    log = tmp_path / "run_now.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seq in range(3):
            f.write(json.dumps({
                "event": "llm_call", "prompt": f"PROMPT_{seq}", "tier": "strategic"
            }) + "\n")

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    critic_json = json.dumps({
        "analysis": "Agent struck when should have blocked.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Block on Rat T1",
            "content": "Do play Defend on turn 1 against Rat; do NOT rush with Strike when incoming >= 8.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"], "enemy_names": ["Rat"],
                "character": "silent", "requires_cards": [],
                "requires_hand_capabilities": [], "any_of_relics": [],
                "requires_enemy_powers": []
            },
            "counterfactual_note": "Playing Defend would have saved ~7 damage per round.",
            "mistake_round_indices": [1, 2],
            "expected_correction": "Defend -> self"
        }
    })
    redecide_txt = "plan: Defend -> self"
    judge_json = json.dumps({
        "verdict": "skill_helps", "hit_count_B": 3, "rationale": "B all block"
    })

    async def fake_call_raw(*, system="", prompt="", effort="", call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        if call_type == "mistake_redecide":
            return redecide_txt, 1.0, 50
        if call_type == "mistake_judge":
            return judge_json, 1.0, 80
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)
    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store,
        skill_library=lib,
        write_gate=gate,
        log_path=log,
        run_id="run_now",
        combat_system_prompt="you are an STS2 agent",
    )

    persisted = [s for s in lib.all_skills if s.source == "mistake_driven"]
    assert len(persisted) == 1
    sk = persisted[0]
    # Two anchors, one per mistake_round_indices entry (1-based -> rounds[0], rounds[1])
    assert len(sk.anchor_exemplars) == 2
    for a in sk.anchor_exemplars:
        assert isinstance(a, AnchorExemplar)
        assert a.run_id == "run_now"
        assert a.expected_correction == "Defend -> self"
        assert a.counterfactual_note == "Playing Defend would have saved ~7 damage per round."
        assert a.episode_id == "ep_bad"
    # llm_call_seq comes from rounds' seq field: _round(...seq=1), _round(...seq=2)
    seqs = {a.llm_call_seq for a in sk.anchor_exemplars}
    assert seqs == {1, 2}
    # round_num tracks the 1-based index from the critic
    round_nums = {a.round_num for a in sk.anchor_exemplars}
    assert round_nums == {1, 2}


@pytest.mark.asyncio
async def test_run_mistake_discovery_critic_rejects_returns_zero_persisted(
    tmp_path, monkeypatch,
):
    """Critic returns no_skill_needed -> pipeline stops before A/B, nothing persisted."""
    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])

    log = tmp_path / "run_now.jsonl"
    log.write_text(
        json.dumps({"event": "llm_call", "prompt": "P"}) + "\n",
        encoding="utf-8",
    )

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    critic_json = json.dumps({
        "analysis": "Bad luck — RNG draw.",
        "decision": "no_skill_needed",
        "reason": "bad_luck",
        "skill": None,
    })

    async def fake_call_raw(*, call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        raise AssertionError(f"unexpected call_type={call_type}")

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store, skill_library=lib, write_gate=gate,
        log_path=log, run_id="run_now",
        combat_system_prompt="system",
    )

    assert stats["mistakes"] == 1
    assert stats["critic_skill_needed"] == 0
    assert stats["persisted"] == 0
    assert not any(s.source == "mistake_driven" for s in lib.all_skills)


@pytest.mark.asyncio
async def test_run_mistake_discovery_ab_fails_drops_candidate(tmp_path, monkeypatch):
    """Critic accepts, cascade passes, but A/B judge returns skill_harmful -> drop."""
    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])

    log = tmp_path / "run_now.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seq in range(3):
            f.write(json.dumps({"event": "llm_call", "prompt": f"P{seq}"}) + "\n")

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    critic_json = json.dumps({
        "analysis": "Could have blocked.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Some skill", "content": "Do play Defend early.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"], "enemy_names": ["Rat"],
                "character": "silent",
            },
            "counterfactual_note": "Would save damage.",
            "mistake_round_indices": [1, 2],
            "expected_correction": "Defend",
        }
    })
    harmful_judge_json = json.dumps({
        "verdict": "skill_harmful", "hit_count_B": 0,
        "rationale": "B samples made it worse",
    })

    async def fake_call_raw(*, call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        if call_type == "mistake_redecide":
            return "plan: Strike -> Rat", 1.0, 50
        if call_type == "mistake_judge":
            return harmful_judge_json, 1.0, 80
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)
    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store, skill_library=lib, write_gate=gate,
        log_path=log, run_id="run_now",
        combat_system_prompt="system",
    )

    assert stats["critic_skill_needed"] == 1
    assert stats["ab_failed"] == 1
    assert stats["persisted"] == 0
    assert not any(s.source == "mistake_driven" for s in lib.all_skills)


# ---------------------------------------------------------------------------
# §5.4 — structured mistake_discovery_verdict events
# ---------------------------------------------------------------------------


class _FakeSessionLogger:
    """Minimal session_logger test double — matches the _write_event API."""

    def __init__(self):
        self.events: list[tuple[str, dict]] = []

    def _write_event(self, event_type: str, data: dict) -> None:
        self.events.append((event_type, dict(data)))


@pytest.mark.asyncio
async def test_verdict_events_emitted_for_each_mistake(tmp_path, monkeypatch):
    """One mistake_discovery_verdict event per mistake episode (happy path)."""
    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])
    store.add_batch([_ep_mistake()])

    log = tmp_path / "run_now.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seq in range(3):
            f.write(json.dumps({
                "event": "llm_call", "prompt": f"PROMPT_{seq}", "tier": "strategic"
            }) + "\n")

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    critic_json = json.dumps({
        "analysis": "Agent struck when should have blocked.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Block on Rat T1",
            "content": "Do play Defend on turn 1 against Rat; do NOT rush with Strike when incoming >= 8.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"], "enemy_names": ["Rat"],
                "character": "silent",
            },
            "counterfactual_note": "Would save ~7 damage per round.",
            "mistake_round_indices": [1, 2],
            "expected_correction": "Defend -> self",
        }
    })
    redecide_txt = "plan: Defend -> self"
    judge_json = json.dumps({
        "verdict": "skill_helps", "hit_count_B": 3, "rationale": "B all block"
    })

    async def fake_call_raw(*, call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        if call_type == "mistake_redecide":
            return redecide_txt, 1.0, 50
        if call_type == "mistake_judge":
            return judge_json, 1.0, 80
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)
    monkeypatch.setattr("src.skills.prewrite_ab.call_raw", fake_call_raw)

    fake_sl = _FakeSessionLogger()
    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store, skill_library=lib, write_gate=gate,
        log_path=log, run_id="run_now",
        combat_system_prompt="system",
        session_logger=fake_sl,
    )

    assert stats["persisted"] == 1
    # Exactly one event per mistake episode
    verdict_events = [(t, d) for t, d in fake_sl.events if t == "mistake_discovery_verdict"]
    assert len(verdict_events) == 1
    payload = verdict_events[0][1]
    assert payload["event"] == "mistake_discovery_verdict"
    assert payload["run_id"] == "run_now"
    assert payload["enemy"] == "Rat"
    assert payload["episode_id"] == "ep_bad"
    assert payload["critic_decision"] == "skill_needed"
    assert payload["cascade_verdict"] == "ACCEPT"
    assert payload["ab_verdict"] == "skill_helps"
    assert payload["skill_id"] is not None
    # Baseline A visible from the 5-episode history; baseline B may be None depending on pool filters
    assert payload["baseline_A"] is not None
    assert payload["loss_ratio"] > 0


@pytest.mark.asyncio
async def test_verdict_events_absent_when_no_session_logger(tmp_path, monkeypatch):
    """session_logger=None must not crash or emit anything."""
    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])
    store.add_batch([_ep_mistake()])

    log = tmp_path / "run.jsonl"
    log.write_text("", encoding="utf-8")

    gate = _make_gate(tmp_path)
    lib = SkillLibrary()

    critic_json = json.dumps({
        "analysis": "Bad luck.", "decision": "no_skill_needed",
        "reason": "bad_luck", "skill": None,
    })

    async def fake_call_raw(*, call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 10
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    # Should not raise
    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store, skill_library=lib, write_gate=gate,
        log_path=log, run_id="r_none",
        combat_system_prompt="system",
        session_logger=None,
    )
    # Pipeline still ran through Stage 1
    assert stats["mistakes"] == 1


@pytest.mark.asyncio
async def test_run_mistake_discovery_stamps_anchors_on_held_buffer(
    tmp_path: Path, monkeypatch
):
    """Held candidates must land on ``write_gate.pending_skills()`` with
    anchor_exemplars stamped from ``mistake_round_indices``.

    The candidate is force-routed to ``held`` by pre-populating a fake
    PendingSkillCandidate and then monkeypatching ``filter_skill_batch`` to
    return the skill in the ``held`` bucket. ``_stamp_anchors_on_held`` is
    then called by ``run_mistake_discovery`` and must update those rows in the
    pending buffer.
    """
    import dataclasses
    from src.memory.write_gate import GateDecision, PendingSkillCandidate
    from src.skills.models import AnchorExemplar

    store = CombatMemoryStore()
    store.add_batch([_ep_old(run_id=f"old{i}", floor=i, dmg=10) for i in range(5)])
    store.add_batch([_ep_mistake()])

    log = tmp_path / "run_now.jsonl"
    with log.open("w", encoding="utf-8") as f:
        for seq in range(3):
            f.write(json.dumps({
                "event": "llm_call", "prompt": f"PROMPT_{seq}", "tier": "strategic"
            }) + "\n")

    lib = SkillLibrary()
    gate = _make_gate(tmp_path)

    critic_json = json.dumps({
        "analysis": "Agent struck when should have blocked.",
        "decision": "skill_needed",
        "reason": "skill_would_help",
        "skill": {
            "name": "Block on Rat T1",
            "content": "Do play Defend on turn 1 against Rat.",
            "category": "combat",
            "trigger": {
                "state_types": ["monster"], "enemy_names": ["Rat"],
                "character": "silent", "requires_cards": [],
                "requires_hand_capabilities": [], "any_of_relics": [],
                "requires_enemy_powers": [],
            },
            "counterfactual_note": "Playing Defend would have saved ~7 damage per round.",
            "mistake_round_indices": [1, 2],
            "expected_correction": "Defend -> self",
        }
    })

    async def fake_call_raw(*, call_type="", **kw):
        if call_type == "mistake_critic":
            return critic_json, 1.0, 100
        return "", 0.0, 0

    monkeypatch.setattr("src.skills.mistake_discovery.call_raw", fake_call_raw)

    # Capture what Stage 3 builds so we can insert a fake pending row.
    _built_skills: list = []
    _orig_filter = gate.filter_skill_batch

    defer_decision = GateDecision(
        action="defer_to_judge",
        target_id="",
        reason="below_reject_above_accept",
    )

    def fake_filter_skill_batch(new_skills, existing_skills=None, *, run_id=""):
        # Record the skills Stage 3 built.
        _built_skills.extend(new_skills)
        # Pre-populate the pending buffer so _stamp_anchors_on_held has rows to update.
        for sk in new_skills:
            pending_cand = PendingSkillCandidate(
                skill=sk,
                decision_action="defer_to_judge",
                request_id="cand_0001",
            )
            with gate._pending_lock:
                gate._pending_skills.append(pending_cand)
        # Route ALL skills to held (simulating defer_to_judge verdict).
        return [], [], [(sk, defer_decision) for sk in new_skills]

    monkeypatch.setattr(gate, "filter_skill_batch", fake_filter_skill_batch)

    stats = await run_mistake_discovery(
        this_run_episodes=[_ep_mistake()],
        combat_store=store,
        skill_library=lib,
        write_gate=gate,
        log_path=log,
        run_id="run_now",
        combat_system_prompt="you are an STS2 agent",
    )

    assert stats["cascade_held"] == 1
    assert stats["persisted"] == 0

    pending = gate.pending_skills()
    assert len(pending) == 1
    stamped_skill = pending[0].skill
    assert len(stamped_skill.anchor_exemplars) == 2
    for a in stamped_skill.anchor_exemplars:
        assert isinstance(a, AnchorExemplar)
        assert a.run_id == "run_now"
        assert a.expected_correction == "Defend -> self"
        assert a.counterfactual_note == "Playing Defend would have saved ~7 damage per round."
        assert a.episode_id == "ep_bad"
    seqs = {a.llm_call_seq for a in stamped_skill.anchor_exemplars}
    assert seqs == {1, 2}
    round_nums = {a.round_num for a in stamped_skill.anchor_exemplars}
    assert round_nums == {1, 2}
