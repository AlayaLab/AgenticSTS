"""Post-run evolution, memory, and finalization tests.

Covers: safe_post_run stage isolation, run finalization on errors,
HCM extraction for aborted runs, and evolution context profile.
"""
from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, call, patch

import src.agent.loop as loop_module

from tests.conftest import make_loop, make_potion_discard_gs
from src.mcp_client.upstream_models import RawRunPayload, UpstreamGameState
from src.state.game_state import GameState


def test_safe_post_run_runs_evolution_even_if_memory_stage_raises(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._memory = MagicMock()
    loop._use_llm = True
    loop._post_run_memory_update = AsyncMock(side_effect=RuntimeError("memory boom"))
    loop._post_run_evolution = AsyncMock()

    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "EVOLUTION_PROVIDER", "openai_compatible")

    asyncio.run(loop._safe_post_run())

    loop._post_run_evolution.assert_awaited_once()


def test_safe_post_run_logs_stage_events(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()
    loop._post_run_memory_update = AsyncMock()
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock(
        return_value={
            "status": "done",
            "context_profile": "heavy",
            "context_chars": 321,
            "action_count": 0,
        }
    )

    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _tier: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _provider: True)

    asyncio.run(loop._safe_post_run())

    loop._session_logger.log_post_run_start.assert_called_once()
    assert call("memory", "start") in loop._session_logger.log_post_run_stage.call_args_list
    assert call("memory", "done") in loop._session_logger.log_post_run_stage.call_args_list
    assert call("skills", "start") in loop._session_logger.log_post_run_stage.call_args_list
    assert call("skills", "done") in loop._session_logger.log_post_run_stage.call_args_list
    assert call(
        "evolution",
        "start",
        context_profile="heavy",
    ) in loop._session_logger.log_post_run_stage.call_args_list
    assert call(
        "evolution",
        "done",
        context_profile="heavy",
        context_chars=321,
        action_count=0,
        error=None,
    ) in loop._session_logger.log_post_run_stage.call_args_list
    loop._session_logger.log_post_run_end.assert_called_once()


def test_run_finalizes_incomplete_state_on_runtime_error(monkeypatch):
    client = MagicMock()
    client.get_state = AsyncMock(return_value={"data": {"screen": "CARD_SELECT"}})
    loop = make_loop(client)
    loop._check_pending_batches = AsyncMock()
    loop._ensure_character_guide = AsyncMock()
    loop._decide_and_act = AsyncMock(side_effect=RuntimeError("fatal test error"))
    loop._safe_post_run = AsyncMock()

    session_logger = MagicMock()
    session_logger.log_path = "test-log.jsonl"
    monkeypatch.setattr(loop_module, "SessionLogger", MagicMock(return_value=session_logger))

    gs = make_potion_discard_gs(
        available_actions=["select_deck_card", "discard_potion"],
        state_type="card_select",
    )

    async def _drive():
        run_state = await loop.run()
        # Postrun is now driven by orchestrator-level finalize_session()
        # rather than loop.run() itself (refactored 2026-04-28). Mirror the
        # orchestrator here so we exercise the full lifecycle.
        await loop.finalize_session()
        return run_state

    with patch.object(loop_module, "parse_state", return_value=gs):
        run_state = asyncio.run(_drive())

    assert run_state.final_floor == 17
    assert run_state.end_time > 0
    assert run_state.victory is False
    loop._safe_post_run.assert_awaited_once()
    session_logger.log_run_end.assert_called_once()


def test_post_run_hcm_extraction_uses_real_final_state_for_abort(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    stm = MagicMock()
    stm.starting_deck = []
    stm.deck_events = []
    loop._memory = MagicMock(
        short_term=stm,
        combat_store=None,
        route_store=None,
        card_build_store=None,
        card_memory_store=None,
    )
    loop._run_state = SimpleNamespace(
        run_id="run-1",
        character="The Silent",
        victory=False,
        final_floor=12,
        final_hp=17,
        final_gold=143,
        fitness=lambda: 11.0,
        floor_snapshots=[],
    )
    loop._run_completion_reason = "aborted"
    loop._planned_act = 2

    with (
        patch("src.memory.combat_extractor.extract_combat_episodes", return_value=[]),
        patch("src.memory.route_extractor.extract_route_memories", return_value=[]),
    ):
        loop._post_run_hcm_extraction()

    stm.finalize_open_state.assert_called_once_with(
        act=2,
        hp=17,
        gold=143,
        combat_terminal_reason="abort",
    )


def test_post_run_evolution_uses_heavy_context(monkeypatch):
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="run-1", character="The Silent")
    loop._memory = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._v2_tool_executor = MagicMock()
    loop._tool_preprocessor = MagicMock()
    loop._dynamic_registry = MagicMock()
    loop._dynamic_registry.save_stats = MagicMock()
    loop._snapshot_store = None
    loop._session_logger = MagicMock()

    decision_digest = MagicMock()
    decision_digest.text = "digest"
    decision_digest.estimated_tokens = 123
    replay_package = MagicMock()
    context_bundle = SimpleNamespace(text="heavy context", summary={}, estimated_tokens=456, seen_card_names=set())
    build_context = MagicMock(return_value=context_bundle)
    engine_instance = MagicMock()
    engine_instance._last_session_summary = {"total_input_tokens": 210000, "target_reached": True}
    engine_instance.run_evolution.return_value = []

    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _tier: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _provider: True)

    with (
        patch("src.postrun.context_builder.build_decision_digest", return_value=decision_digest),
        patch("src.postrun.context_builder.build_replay_package", return_value=replay_package),
        patch("src.postrun.context_builder.build_evolution_context", build_context),
        patch("src.brain.evolution_engine.EvolutionEngine", return_value=engine_instance),
        patch("src.brain.v2_backend.V2Backend", return_value=MagicMock()),
        patch.object(loop, "_write_evolution_meta_log") as meta_log,
    ):
        result = asyncio.run(loop._post_run_evolution())

    build_context.assert_called_once_with(
        loop._run_state,
        decision_digest,
        replay_package,
        dynamic_registry=loop._dynamic_registry,
        memory_manager=loop._memory,
        skill_triggers=None,
        return_bundle=True,
    )
    meta_log.assert_called_once()
    assert result["context_profile"] == "heavy"
    assert result["action_count"] == 0


def test_invalid_start_skips_post_run_processing(monkeypatch):
    """Agent woke up into an already-dead run (HP=0, not game_over) — post-run
    stages (memory, skills, evolution) must be skipped entirely."""
    client = MagicMock()
    loop = make_loop(client)
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._post_run_memory_update = AsyncMock()
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock()
    session_logger = MagicMock()
    loop._session_logger = session_logger

    # Simulate invalid_start reason set by the main loop
    loop._run_end_reason = "invalid_start"

    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _tier: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _provider: True)

    asyncio.run(loop._safe_post_run())

    loop._post_run_memory_update.assert_not_awaited()
    loop._post_run_skill_update.assert_not_awaited()
    loop._post_run_evolution.assert_not_awaited()
    session_logger.log_post_run_end.assert_called_once()


def test_invalid_start_detected_on_zero_hp_first_step(monkeypatch):
    """Main loop terminates immediately with invalid_start when HP=0 at step 1."""
    from src.mcp_client.upstream_models import RawDeckCardPayload

    run = RawRunPayload(
        character_id="silent",
        character_name="The Silent",
        floor=48,
        current_hp=0,
        max_hp=70,
        gold=0,
        max_energy=3,
        deck=[
            RawDeckCardPayload(
                index=0,
                card_id="strike",
                name="Strike",
                card_type="Attack",
                energy_cost=1,
                rarity="Starter",
                rules_text="Deal 6 damage.",
            )
        ],
        potions=[],
    )
    dead_gs = GameState(
        raw=UpstreamGameState(
            screen="MAP",
            available_actions=["navigate_map"],
            run=run,
        ),
        state_type="map",
    )

    client = MagicMock()
    client.get_state = AsyncMock(return_value={})
    loop = make_loop(client)
    loop._check_pending_batches = AsyncMock()
    loop._ensure_character_guide = AsyncMock()
    loop._safe_post_run = AsyncMock()

    session_logger = MagicMock()
    session_logger.log_path = "test.jsonl"
    monkeypatch.setattr(loop_module, "SessionLogger", MagicMock(return_value=session_logger))

    async def _drive():
        await loop.run()
        # Postrun is driven by orchestrator-level finalize_session()
        # (refactored 2026-04-28). Internal short-circuit on invalid_start
        # is covered by test_invalid_start_skips_post_run_processing.
        await loop.finalize_session()

    with patch.object(loop_module, "parse_state", return_value=dead_gs):
        asyncio.run(_drive())

    assert loop._run_end_reason == "invalid_start"
    assert loop._run_completion_reason == "aborted"
    loop._safe_post_run.assert_awaited_once()


def test_loop_init_sets_postrun_consolidation_flag_false():
    """The skills-stage cadence snapshot flag must default to False so a
    fresh AgentLoop never accidentally triggers mistake_discovery on
    its first postrun."""
    client = MagicMock()
    loop = make_loop(client)
    assert loop._postrun_consolidation_active is False


def test_memory_stage_captures_consolidation_snapshot(monkeypatch):
    """When memory's increment pushes should_consolidate True, the
    AgentLoop captures the decision into _postrun_consolidation_active
    BEFORE invoking consolidate_guides. The snapshot must be set even
    if consolidate_guides raises."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._use_llm = False  # skip the build-analysis branch
    loop._memory = MagicMock()
    loop._memory.should_consolidate = True
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._memory.maintenance = MagicMock()
    loop._memory.save_all = MagicMock()
    loop._memory.stats = MagicMock(return_value={})
    loop._post_run_hcm_extraction = MagicMock()

    # consolidate_guides raises — snapshot must already be captured
    async def _raise(*a, **kw):
        raise RuntimeError("consolidate boom")
    monkeypatch.setattr(
        "src.memory.guide_consolidator.consolidate_guides", _raise,
    )

    asyncio.run(loop._post_run_memory_update())
    assert loop._postrun_consolidation_active is True


def test_safe_post_run_finally_resets_consolidation_when_active(monkeypatch):
    """The finally block resets _memory.consolidation_count when the
    snapshot was True, regardless of whether memory/skills/evolution
    stages succeeded. Always clears the flag for the next run."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()
    loop._post_run_memory_update = AsyncMock(
        side_effect=lambda: setattr(loop, "_postrun_consolidation_active", True),
    )
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock(
        return_value={"status": "done", "context_profile": "heavy", "context_chars": 0, "action_count": 0},
    )
    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _t: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _p: True)

    asyncio.run(loop._safe_post_run())

    loop._memory.reset_consolidation_count.assert_called_once()
    assert loop._postrun_consolidation_active is False  # cleared at end


def test_safe_post_run_finally_does_not_reset_when_inactive(monkeypatch):
    """When snapshot is False (no consolidation due), reset must NOT fire."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()
    loop._post_run_memory_update = AsyncMock()  # leaves flag at False
    loop._post_run_skill_update = AsyncMock()
    loop._post_run_evolution = AsyncMock(
        return_value={"status": "done", "context_profile": "heavy", "context_chars": 0, "action_count": 0},
    )
    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _t: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _p: True)

    asyncio.run(loop._safe_post_run())

    loop._memory.reset_consolidation_count.assert_not_called()
    assert loop._postrun_consolidation_active is False


def _setup_skill_stage_mocks(loop, monkeypatch):
    """Bypass `_post_run_skill_update`'s lifecycle / score helpers so the
    test can focus on the discovery-dispatch decision. Returns nothing;
    mutates loop and monkeypatches lifecycle imports."""
    loop._score_noncombat_skills_end_of_run = MagicMock()
    monkeypatch.setattr(
        "src.skills.lifecycle.update_skill_usage_from_run", MagicMock(),
    )
    monkeypatch.setattr(
        "src.skills.lifecycle.apply_retirement_policy",
        MagicMock(return_value=[]),
    )


def test_skills_stage_runs_mistake_discovery_when_snapshot_true(monkeypatch):
    """When _postrun_consolidation_active is True at skills-stage entry,
    mistake_discovery is invoked from _post_run_skill_update."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = True  # snapshot pretend-set by memory stage
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = set()
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    loop._session_logger.log_path = None

    _setup_skill_stage_mocks(loop, monkeypatch)
    discovery_mock = AsyncMock(return_value={
        "candidates": 0, "ab_passed": 0, "persisted": 0,
    })
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )
    monkeypatch.setattr(loop_module.config, "MISTAKE_DISCOVERY_ENABLED", True)

    asyncio.run(loop._post_run_skill_update())

    discovery_mock.assert_awaited_once()


def test_skills_stage_skips_mistake_discovery_when_snapshot_false(monkeypatch):
    """When the cadence snapshot is False, mistake_discovery must NOT
    fire from the skills stage."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = False  # not a cadence cycle
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = set()
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    loop._session_logger.log_path = None

    _setup_skill_stage_mocks(loop, monkeypatch)
    discovery_mock = AsyncMock()
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )
    monkeypatch.setattr(loop_module.config, "MISTAKE_DISCOVERY_ENABLED", True)

    asyncio.run(loop._post_run_skill_update())

    discovery_mock.assert_not_awaited()


def test_memory_stage_no_longer_calls_mistake_discovery(monkeypatch):
    """The memory stage must no longer invoke mistake_discovery directly.
    Discovery is now the skills stage's responsibility."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._use_llm = False  # skip build-analysis branch
    loop._memory = MagicMock()
    loop._memory.should_consolidate = True
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._memory.maintenance = MagicMock()
    loop._memory.save_all = MagicMock()
    loop._memory.stats = MagicMock(return_value={})
    loop._post_run_hcm_extraction = MagicMock()

    async def _ok(*a, **kw):
        return {"combat": 0, "route": 0, "deck": 0}
    monkeypatch.setattr(
        "src.memory.guide_consolidator.consolidate_guides", _ok,
    )

    discovery_mock = AsyncMock()
    monkeypatch.setattr(
        "src.skills.mistake_discovery.run_mistake_discovery",
        discovery_mock,
    )

    asyncio.run(loop._post_run_memory_update())

    discovery_mock.assert_not_awaited()  # not called from memory stage
    loop._memory.reset_consolidation_count.assert_not_called()  # reset moved to finally


def test_skills_stage_records_noncombat_outcome_for_meaningful_run(monkeypatch):
    """The non-combat record_outcome block (formerly in _safe_post_run
    body) must now fire from inside _post_run_skill_update for runs
    that are meaningful (>= 20 steps and >= floor 5).

    NOTE: this test uses `_setup_skill_stage_mocks` defined in
    `test_skills_stage_runs_mistake_discovery_when_snapshot_true` above.
    """
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=20, _highest_floor=20, victory=False)
    loop._current_step = 60
    loop._postrun_consolidation_active = False
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = {"sk1", "sk2", "sk3"}
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    _setup_skill_stage_mocks(loop, monkeypatch)

    asyncio.run(loop._post_run_skill_update())

    # record_outcome called once with the 3 skill ids and an "ok" bool
    loop._skill_library.record_outcome.assert_called_once()
    call_args = loop._skill_library.record_outcome.call_args
    skill_ids_arg = call_args[0][0]
    run_ok_arg = call_args[0][1]
    assert set(skill_ids_arg) == {"sk1", "sk2", "sk3"}
    # final_floor=20 and victory=False → run_ok should be False (floor < 30, not victory)
    assert run_ok_arg is False


def test_skills_stage_skips_noncombat_record_outcome_for_short_run(monkeypatch):
    """A run too short to be meaningful (< 20 steps OR floor < 5) must
    NOT receive record_outcome — it would unfairly penalize skills."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(run_id="r1", final_floor=2, _highest_floor=2, victory=False)
    loop._current_step = 5
    loop._postrun_consolidation_active = False
    loop._memory = MagicMock()
    loop._memory.combat_store = MagicMock()
    loop._memory.combat_store.get_all.return_value = []
    loop._skill_library = MagicMock()
    loop._skill_library.stats.return_value = {}
    loop._skill_library.sweep_retirements.return_value = []
    loop._skill_library.enforce_category_caps.return_value = []
    loop._noncombat_skill_ids = {"sk1"}
    loop._write_gate = MagicMock()
    loop._session_logger = MagicMock()
    _setup_skill_stage_mocks(loop, monkeypatch)

    asyncio.run(loop._post_run_skill_update())

    loop._skill_library.record_outcome.assert_not_called()


def test_safe_post_run_finally_resets_when_skills_stage_raises(monkeypatch):
    """When the skills stage raises mid-execution (e.g., mistake_discovery
    throws), the _safe_post_run finally block must still reset the
    consolidation count and clear the snapshot flag. Verifies Spec #2 §3.4
    row 2."""
    client = MagicMock()
    loop = make_loop(client)
    loop._run_state = SimpleNamespace(final_floor=12, _highest_floor=12, victory=False)
    loop._current_step = 40
    loop._memory = MagicMock()
    loop._skill_library = MagicMock()
    loop._use_llm = True
    loop._session_logger = MagicMock()

    # Memory stage sets the snapshot flag, then succeeds
    loop._post_run_memory_update = AsyncMock(
        side_effect=lambda: setattr(loop, "_postrun_consolidation_active", True),
    )
    # Skills stage raises (simulates mistake_discovery failure escalating)
    loop._post_run_skill_update = AsyncMock(side_effect=RuntimeError("skills boom"))
    loop._post_run_evolution = AsyncMock(
        return_value={"status": "done", "context_profile": "heavy", "context_chars": 0, "action_count": 0},
    )
    monkeypatch.setattr(loop_module.config, "EVOLUTION_ENABLED", True)
    monkeypatch.setattr(loop_module.config, "get_tier_provider", lambda _t: "openai")
    monkeypatch.setattr(loop_module.config, "provider_supports_tool_loop", lambda _p: True)

    asyncio.run(loop._safe_post_run())

    # Skills stage failure should NOT prevent the finally-block reset
    loop._memory.reset_consolidation_count.assert_called_once()
    assert loop._postrun_consolidation_active is False
