"""Mode B end-to-end integration smoke.

Exercises the full postrun stage 5 chain with a mock LLM backend:
1. AgentLoop with skill library populated by 5 stubs (pending_fill).
2. Mocked combat_store with episodes for current run.
3. Mocked card_memory_store + STM (Strategic Thread).
4. Mocked RunHistoryStore returning current + recent_win + recent_loss.
5. Mocked decisions JSONL log so trajectory rendering works.
6. Mock LLM backend returns a valid 5-principle JSON for every call.

Verifies:
- All 5 stubs transition pending_fill → active in a single _post_run_fill_stubs() call.
- Audit log entry written to stub_fill_log.jsonl.
- Library save invoked.
- Combat / boss stubs received combat-replay evidence.
- Non-combat stubs received trajectory + Attribution Summary evidence.
"""

import importlib
import json
import os
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from src.agent.loop import AgentLoop
from src.skills.library import SkillLibrary


def _good_payload(prefix: str = "P") -> dict:
    return {
        "principles": [
            {"text": f"{prefix} use ALL energy each turn.",
             "example": "If 1 energy left, play a 1-cost."},
            {"text": f"{prefix} read intents BEFORE deciding offense vs defense.",
             "example": "When the enemy buffs, set up your engine."},
            {"text": f"{prefix} prefer the 0-damage line over a faster line.",
             "example": "Take a defensive turn even if slower."},
            {"text": f"{prefix} sequence free plays first.",
             "example": "Free Strike before a costed skill."},
            {"text": f"{prefix} save buff potions for boss fights.",
             "example": "Don't burn Strength Potion on a hallway."},
        ],
        "confidence": 0.7,
        "dimensions_covered": ["energy_allocation", "intent_reading"],
        "evidence_basis": "Cross-run pattern.",
    }


def _make_episode(combat_type: str, enemy_key: str, run_id: str):
    """Minimal combat episode for the sampler."""
    return SimpleNamespace(
        combat_type=combat_type,
        enemy_key=enemy_key,
        run_id=run_id,
        is_aborted=False,
        floor=1,
        timestamp=0.0,
        # Fields format_combat_replay reads:
        rounds=[],
        relics=[],
        deck=[],
        won=True,
        hp_before=70,
        hp_after=70,
        total_damage_dealt=20,
        total_damage_taken=0,
    )


@pytest.mark.asyncio
async def test_mode_b_full_postrun_chain(tmp_path, monkeypatch):
    """End-to-end: 5 stubs go from pending_fill → active in one postrun call."""
    # ── Mode B env ────────────────────────────────────────────
    os.environ["STS2_SEED_STUB_FILL_ENABLED"] = "true"
    os.environ["STS2_USE_SEED_STUBS"] = "true"

    # Redirect audit log + skills file to tmp
    audit_log = tmp_path / "stub_fill_log.jsonl"
    skills_file = tmp_path / "skills.json"

    try:
        import config as _cfg
        importlib.reload(_cfg)
        monkeypatch.setattr(_cfg, "SEED_STUB_FILL_LOG", str(audit_log))

        # ── Build library with 5 stubs ────────────────────────
        agent = AgentLoop.__new__(AgentLoop)
        agent._skill_library = SkillLibrary()
        stub_dir = Path(__file__).resolve().parent.parent / "src/skills/seeds_stubs"
        agent._skill_library.load_seed_stubs(stub_dir, character="the silent")

        pending_before = sum(1 for s in agent._skill_library.all_skills if s.status == "pending_fill")
        assert pending_before == 5

        # ── Mock memory: combat_store with one hallway + one boss episode ──
        episodes = [
            _make_episode("monster", "Toadpole", "r1"),
            _make_episode("elite", "Lagavulin", "r1"),
            _make_episode("boss", "Insatiable", "r1"),
        ]
        card_memories = [
            SimpleNamespace(
                card_name="strike",
                play_count=20,
                total_damage=200,
                total_block=0,
            ),
            SimpleNamespace(
                card_name="defend",
                play_count=15,
                total_damage=0,
                total_block=120,
            ),
        ]

        class _FakeSTM:
            _strategic_thread = [("F1", "Foundation: frontload damage"),
                                 ("F12", "Committed: poison")]

        class _FakeCombatStore:
            def get_all(self):
                return episodes

        class _FakeCardMemory:
            def get_all_for_character(self, character):
                return card_memories

        agent._memory = SimpleNamespace(
            combat_store=_FakeCombatStore(),
            card_memory_store=_FakeCardMemory(),
            short_term=_FakeSTM(),
        )

        # ── Run state ─────────────────────────────────────────
        agent._run_state = SimpleNamespace(
            run_id="r1",
            character="the silent",
            actual_ascension=0,
            victory=False,
            outcome="defeat",
        )

        # ── Mock RunHistoryStore: 1 run (current only, startup case) ──
        fake_record = SimpleNamespace(
            run_id="r1", character="the silent", outcome="defeat",
            started_at=1.0, actual_ascension=0,
        )
        from src.runs import history as _hist
        class _FakeStore:
            def query(self, **kwargs):
                return [fake_record]
        monkeypatch.setattr(_hist.RunHistoryStore, "load",
                            classmethod(lambda cls, p: _FakeStore()))

        # ── Mock decisions for trajectory rendering ───────────
        def _fake_load_decisions(run_id, log_dir=None):
            return [
                SimpleNamespace(
                    floor="F1", state_type="card_reward",
                    action="resolve_rewards", option_index=1,
                    reasoning="Backstab is premium Silent damage",
                    strategic_note="Foundation: frontload damage",
                    hp_before=70, hp_after=70,
                    gold_before=0, gold_after=0,
                    deck_before=12, deck_after=13,
                    deck_change="+Backstab",
                ),
                SimpleNamespace(
                    floor="F2", state_type="map",
                    action="choose_map_node", option_index=0,
                    reasoning="Take the easier path",
                    strategic_note="Foundation: build deck",
                    hp_before=70, hp_after=70,
                    gold_before=0, gold_after=0,
                    deck_before=13, deck_after=13,
                    deck_change="no change",
                ),
                SimpleNamespace(
                    floor="F3", state_type="rest_site",
                    action="choose_rest_option", option_index=1,
                    reasoning="Smith Backstab for the boss",
                    strategic_note="Pre-boss: upgrade key card",
                    hp_before=65, hp_after=65,
                    gold_before=20, gold_after=20,
                    deck_before=13, deck_after=13,
                    deck_change="upgrade Backstab",
                ),
            ]
        monkeypatch.setattr(AgentLoop, "_load_decisions_for_run", _fake_load_decisions)

        # ── Mock V2Backend: returns valid JSON for every call ──
        from src.brain import v2_backend
        captured_prompts: list[str] = []
        class _FakeBackend:
            def call(self, *, system, messages, **kwargs):
                captured_prompts.append(messages[0]["content"])
                return SimpleNamespace(
                    content=[SimpleNamespace(
                        type="text",
                        text=json.dumps(_good_payload()),
                    )],
                    stop_reason="end_turn",
                    usage=SimpleNamespace(input_tokens=5000, output_tokens=600),
                )
        monkeypatch.setattr(v2_backend, "V2Backend", _FakeBackend)

        # Patch skills_file path so library.save lands in tmp
        from src.storage import paths as _paths
        monkeypatch.setattr(_paths, "skills_file", lambda: skills_file)

        # ── Run! ──────────────────────────────────────────────
        await agent._post_run_fill_stubs()

        # ── Assertions ────────────────────────────────────────
        # 1. All 5 stubs went pending_fill → active
        pending_after = sum(1 for s in agent._skill_library.all_skills if s.status == "pending_fill")
        active_after = sum(1 for s in agent._skill_library.all_skills if s.status == "active")
        assert pending_after == 0, f"some stubs still pending: {pending_after}"
        assert active_after >= 5

        # 2. Each stub has filled content
        for s in agent._skill_library.all_skills:
            if s.skill_id.startswith("stub_"):
                assert s.source == "stub_filled"
                assert s.version == 1
                assert "use ALL energy" in s.content

        # 3. Audit log written with one entry
        assert audit_log.exists()
        entries = [json.loads(line) for line in audit_log.read_text(encoding="utf-8").splitlines() if line]
        assert len(entries) == 1
        e = entries[0]
        assert e["run_id"] == "r1"
        assert e["character"] == "the silent"
        assert e["filled_count"] == 5
        assert e["skipped_count"] == 0

        # 4. Library saved to disk
        assert skills_file.exists()
        saved = json.loads(skills_file.read_text(encoding="utf-8"))
        saved_stub_ids = {s.get("skill_id", "") for s in saved if s.get("skill_id", "").startswith("stub_")}
        assert len(saved_stub_ids) == 5

        # 5. Combat / boss stub got combat-replay evidence
        combat_prompt = next(
            (p for p in captured_prompts if "stub_the_silent_combat" in p
             or "non-boss combat" in p), None,
        )
        assert combat_prompt is not None

        # 6. Non-combat stubs got trajectory evidence (key fix this round)
        deckbuilding_prompt = next(
            (p for p in captured_prompts
             if "Deckbuilding Trajectory" in p or "deck-building decisions" in p),
            None,
        )
        assert deckbuilding_prompt is not None
        # Trajectory must include reasoning + strategic_note from our fake decisions
        assert "Backstab is premium" in deckbuilding_prompt
        assert "Foundation: frontload damage" in deckbuilding_prompt

        # 7. Concurrent dispatch — each stub got its own backend.call
        # (5 stubs → 5 prompts captured)
        assert len(captured_prompts) == 5
    finally:
        for k in ("STS2_SEED_STUB_FILL_ENABLED", "STS2_USE_SEED_STUBS"):
            os.environ.pop(k, None)
        import config as _cfg
        importlib.reload(_cfg)
