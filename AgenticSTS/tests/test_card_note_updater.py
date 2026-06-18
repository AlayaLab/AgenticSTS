"""Unit tests for the Turn 2 card note updater."""
from __future__ import annotations

import pytest


def test_parse_note_updates_returns_valid_proposals():
    from src.memory.card_note_updater import parse_note_updates

    raw = '{"updates": [{"card_name": "backstab", "new_note": "reliable first-turn 11", "reason": "saw it", "trace_citation": "C1 R1"}]}'
    candidates = {"backstab", "strike"}
    proposals, invalid = parse_note_updates(raw, candidates)
    assert len(proposals) == 1
    assert invalid == 0
    assert proposals[0]["card_name"] == "backstab"


def test_parse_note_updates_canonicalizes_upgrade_variants():
    """LLM emits 'pinpoint+' while candidate list has 'Pinpoint++'
    (or vice versa) — both must canonicalize to 'pinpoint' and match."""
    from src.memory.card_note_updater import parse_note_updates

    raw = (
        '{"updates": ['
        '{"card_name": "pinpoint+", "new_note": "n1", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "Hidden Daggers", "new_note": "n2", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "STRIKE++", "new_note": "n3", "reason": "r", "trace_citation": "c"}'
        ']}'
    )
    # Candidates use the runtime-name forms (mixed case, with various +)
    candidates = {"Pinpoint++", "Hidden Daggers+", "Strike"}
    proposals, invalid = parse_note_updates(raw, candidates)
    assert invalid == 0
    names = {p["card_name"] for p in proposals}
    # All canonicalized to base name
    assert names == {"pinpoint", "hidden daggers", "strike"}


def test_apply_note_updates_writes_under_canonical_key():
    """Even when the proposal's card_name is 'pinpoint+', the note is
    written into the same slot the extractor uses ('pinpoint')."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import apply_note_updates
    from src.memory.models_v2 import CardMemory

    store = CardMemoryStore()
    # Pre-existing extractor entry under base name with stats
    store.put(CardMemory(
        character="the silent", card_name="pinpoint", play_count=12, sample_count=3,
    ))
    proposals = [
        {"card_name": "pinpoint+", "new_note": "scaling finisher",
         "reason": "r", "trace_citation": "c"},
    ]
    written = apply_note_updates(
        store, character="the silent", proposals=proposals, run_id="run_X",
    )
    assert written == 1
    assert store.count == 1  # no second slot created
    mem = store.get("the silent", "pinpoint")
    assert mem is not None
    assert mem.note == "scaling finisher"
    assert mem.play_count == 12  # stats preserved


def test_parse_note_updates_drops_unknown_card():
    from src.memory.card_note_updater import parse_note_updates

    raw = '{"updates": [{"card_name": "phantom_card", "new_note": "x", "reason": "r", "trace_citation": "c"}]}'
    proposals, invalid = parse_note_updates(raw, {"backstab"})
    assert proposals == []
    assert invalid == 1


def test_parse_note_updates_drops_oversized_new_note():
    from src.memory.card_note_updater import parse_note_updates

    long_note = "x" * 201
    raw = f'{{"updates": [{{"card_name": "strike", "new_note": "{long_note}", "reason": "r", "trace_citation": "c"}}]}}'
    proposals, invalid = parse_note_updates(raw, {"strike"})
    assert proposals == []
    assert invalid == 1


def test_parse_note_updates_drops_empty_fields():
    from src.memory.card_note_updater import parse_note_updates

    cases = [
        '{"updates":[{"card_name":"strike","new_note":"","reason":"r","trace_citation":"c"}]}',
        '{"updates":[{"card_name":"strike","new_note":"x","reason":"","trace_citation":"c"}]}',
        '{"updates":[{"card_name":"strike","new_note":"x","reason":"r","trace_citation":""}]}',
    ]
    for raw in cases:
        proposals, invalid = parse_note_updates(raw, {"strike"})
        assert proposals == []
        assert invalid == 1


def test_parse_note_updates_bad_json_returns_empty():
    from src.memory.card_note_updater import parse_note_updates

    proposals, invalid = parse_note_updates("not json {", {"strike"})
    assert proposals == []
    assert invalid == 0


def test_parse_note_updates_mixed_batch():
    from src.memory.card_note_updater import parse_note_updates

    raw = (
        '{"updates": ['
        '{"card_name": "strike", "new_note": "good", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "ghost_card", "new_note": "x", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "defend", "new_note": "ok", "reason": "r", "trace_citation": "c"},'
        '{"card_name": "sly", "new_note": "", "reason": "r", "trace_citation": "c"}'
        ']}'
    )
    proposals, invalid = parse_note_updates(raw, {"strike", "defend", "sly"})
    assert len(proposals) == 2
    assert {p["card_name"] for p in proposals} == {"strike", "defend"}
    assert invalid == 2


def test_apply_note_updates_writes_and_creates_missing_cards(tmp_path):
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import apply_note_updates

    store = CardMemoryStore()
    proposals = [
        {"card_name": "backstab", "new_note": "n1", "reason": "r1", "trace_citation": "c1"},
        {"card_name": "strike",   "new_note": "n2", "reason": "r2", "trace_citation": "c2"},
    ]
    written = apply_note_updates(
        store, character="silent", proposals=proposals, run_id="run_X",
    )
    assert written == 2
    assert store.get("silent", "backstab").note == "n1"
    assert store.get("silent", "strike").note == "n2"
    assert len(store.get("silent", "backstab").note_history) == 1


def test_apply_note_updates_dry_run_does_not_write(tmp_path):
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import apply_note_updates

    store = CardMemoryStore()
    proposals = [
        {"card_name": "backstab", "new_note": "n1", "reason": "r1", "trace_citation": "c1"},
    ]
    written = apply_note_updates(
        store, character="silent", proposals=proposals, run_id="run_X",
        dry_run=True,
    )
    assert written == 0
    assert store.get("silent", "backstab") is None


def test_turn2_result_default_shape():
    from src.memory.card_note_updater import Turn2Result
    r = Turn2Result()
    assert r.notes_written == 0
    assert r.notes_kept_unchanged == 0
    assert r.notes_invalid == 0
    assert r.core_engine_applied == 0
    assert r.core_engine_emitted is False


def test_turn2_result_is_frozen():
    from src.memory.card_note_updater import Turn2Result
    r = Turn2Result()
    with pytest.raises((AttributeError, Exception)):
        r.notes_written = 5  # type: ignore[misc]


def test_parse_core_engine_block_returns_emitted_with_validated_engine():
    """LLM emitted a valid, non-empty engine block."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '{"updates": [],'
        ' "core_engine": {'
        '   "engine_mechanic": "stacking passive damage while stalling",'
        '   "core_cards": ["Noxious Fumes"],'
        '   "support_cards": ["Prepared"],'
        '   "notes": "debuff stack"'
        ' }}'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True
    assert eng is not None
    assert eng["engine_mechanic"] == "stacking passive damage while stalling"
    assert eng["core_cards"] == ["Noxious Fumes"]
    assert eng["support_cards"] == ["Prepared"]
    assert eng["notes"] == "debuff stack"


def test_parse_core_engine_block_field_absent_means_not_emitted():
    """LLM did not emit the core_engine field at all."""
    from src.memory.card_note_updater import parse_core_engine_block

    emitted, eng = parse_core_engine_block('{"updates": []}')
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_empty_sentinel_is_emitted_but_no_engine():
    """LLM emitted core_engine but said 'no clear scaling engine' — empty
    mechanic + empty core_cards. Per spec §6 this is a LEGITIMATE outcome:
    emitted=True (the LLM tried), eng=None (no apply call). This
    distinction matters for telemetry."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "", "core_cards": [],'
        '                 "support_cards": [], "notes": ""}}'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True   # LLM did emit the field
    assert eng is None       # but no engine to apply


def test_parse_core_engine_block_bad_outer_json_is_not_emitted():
    """Malformed JSON: cannot tell if engine was intended → not emitted."""
    from src.memory.card_note_updater import parse_core_engine_block
    emitted, eng = parse_core_engine_block("not json {")
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_non_dict_engine_is_not_emitted():
    """LLM gave the field but it's not a dict → treat as not-emitted
    (we cannot extract anything from it; warning logging is the caller's
    job)."""
    from src.memory.card_note_updater import parse_core_engine_block

    raw = '{"updates": [], "core_engine": "not a dict"}'
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is False
    assert eng is None


def test_parse_core_engine_block_strips_code_fence():
    from src.memory.card_note_updater import parse_core_engine_block

    raw = (
        '```json\n'
        '{"updates": [], "core_engine": {'
        '   "engine_mechanic": "M", "core_cards": ["X"],'
        '   "support_cards": [], "notes": "N"}}\n'
        '```'
    )
    emitted, eng = parse_core_engine_block(raw)
    assert emitted is True
    assert eng is not None
    assert eng["engine_mechanic"] == "M"


def test_system_prompt_documents_core_engine_conditional():
    """The system prompt must instruct the LLM to emit `core_engine`
    iff the user message says 'this run won the Act 3 final boss'.

    Locking literal phrases here is intentional: the user-message
    section header MUST match what the system prompt references."""
    from src.memory.card_note_updater import _NOTE_UPDATER_SYSTEM
    assert "core_engine" in _NOTE_UPDATER_SYSTEM
    assert "Act 3 final boss" in _NOTE_UPDATER_SYSTEM
    assert "engine_mechanic" in _NOTE_UPDATER_SYSTEM
    assert "core_cards" in _NOTE_UPDATER_SYSTEM
    assert "Omit" in _NOTE_UPDATER_SYSTEM or "omit" in _NOTE_UPDATER_SYSTEM


def test_render_act3_victory_section_includes_phrase_and_cards():
    """The literal phrase 'Act 3 final boss' must appear so the
    system-prompt rule fires, plus deck and relic listings."""
    from src.memory.card_note_updater import _render_act3_victory_section

    deck = ["Strike", "Backstab", "Noxious Fumes", "Defend"]
    relics = ["Burning Blood", "Snake Skull"]
    text = _render_act3_victory_section(deck, relics)
    assert "Act 3 final boss" in text
    for card in deck:
        assert card in text
    for relic in relics:
        assert relic in text
    # Must instruct LLM to output core_engine
    assert "core_engine" in text


def test_render_act3_victory_section_handles_empty_relics():
    from src.memory.card_note_updater import _render_act3_victory_section

    text = _render_act3_victory_section(["Strike"], [])
    assert "Act 3 final boss" in text
    assert "Strike" in text
    # Empty relics list shouldn't break the rendering
    assert text  # non-empty


def test_render_act3_victory_section_handles_empty_deck():
    """Should still render the gating phrase even if deck is unknown."""
    from src.memory.card_note_updater import _render_act3_victory_section

    text = _render_act3_victory_section([], ["Burning Blood"])
    assert "Act 3 final boss" in text
    assert "Burning Blood" in text


import asyncio
from unittest.mock import patch


def _mock_call_raw_factory(response_text: str):
    """Return an async stub that mimics call_raw's contract."""
    async def _stub(system, prompt, **kwargs):  # noqa: ARG001
        return response_text, 100.0, 500
    return _stub


def test_update_card_notes_returns_turn2_result():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import (
        Turn2Result,
        update_card_notes_from_traces,
    )

    store = CardMemoryStore()
    response = (
        '{"updates": ['
        '{"card_name":"strike","new_note":"reliable","reason":"r","trace_citation":"c"}'
        ']}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
        ))
    assert isinstance(result, Turn2Result)
    assert result.notes_written == 1
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is False


def test_update_card_notes_act3_victory_applies_engine():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {'
        '   "engine_mechanic": "stacking debuffs",'
        '   "core_cards": ["Noxious Fumes"],'
        '   "support_cards": ["Prepared"],'
        '   "notes": "debuff stack"'
        ' }}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="the silent",
            combat_trace_text="(trace)",
            candidate_cards=["Noxious Fumes", "Prepared"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Noxious Fumes", "Prepared", "Defend"],
            final_relics=["Snake Skull"],
        ))
    assert result.core_engine_emitted is True
    assert result.core_engine_applied == 2  # 1 core + 1 support
    obs_core = store.get("the silent", "Noxious Fumes")
    obs_supp = store.get("the silent", "Prepared")
    assert obs_core is not None and len(obs_core.core_engine_observations) == 1
    assert obs_core.core_engine_observations[0]["role"] == "core"
    assert obs_supp is not None and obs_supp.core_engine_observations[0]["role"] == "support"


def test_update_card_notes_drops_engine_when_gate_off():
    """LLM emits engine despite gate=False — must drop with warning."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "X", "core_cards": ["Y"],'
        '                 "support_cards": [], "notes": "N"}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Y"],
            run_id="r1",
            is_act3_boss_victory=False,  # gate OFF
        ))
    assert result.core_engine_emitted is False  # block dropped
    assert result.core_engine_applied == 0
    assert store.count == 0


def test_update_card_notes_act3_victory_empty_engine_is_legitimate():
    """Gate ON + LLM returns no-engine sentinel -> noop write but
    emitted=True (LLM tried, said 'no clear engine'). Per spec §6 this
    is a legitimate outcome; telemetry distinguishes 'emitted but no
    engine' (LLM was honest) from 'not emitted' (LLM forgot)."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "", "core_cards": [],'
        '                 "support_cards": [], "notes": ""}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Strike"],
            final_relics=[],
        ))
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is True


def test_update_card_notes_act3_victory_field_omitted_is_not_emitted():
    """Gate ON + LLM omits core_engine field entirely -> emitted=False."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = '{"updates": []}'  # no core_engine field
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Strike"],
            final_relics=[],
        ))
    assert result.core_engine_applied == 0
    assert result.core_engine_emitted is False


def test_update_card_notes_dry_run_blocks_engine_writes_too():
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "M", "core_cards": ["X"],'
        '                 "support_cards": [], "notes": "N"}}'
    )
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["X"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["X"],
            final_relics=[],
            dry_run=True,
        ))
    assert result.core_engine_emitted is True   # parsed
    assert result.core_engine_applied == 0      # but not applied
    assert store.count == 0


from unittest.mock import MagicMock


def test_update_card_notes_emits_engine_artifact_on_apply():
    """When engine is applied, session_logger receives a
    log_postrun_artifact call with kind='core_engine_observation' and
    a summary containing engine_mechanic + core/support cards."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {'
        '   "engine_mechanic": "stacking debuffs while stalling",'
        '   "core_cards": ["Noxious Fumes"],'
        '   "support_cards": ["Prepared"],'
        '   "notes": "debuff stack"'
        ' }}'
    )
    sl = MagicMock()
    sl.log_postrun_artifact = MagicMock()
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        result = asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Noxious Fumes", "Prepared"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Noxious Fumes", "Prepared"],
            final_relics=[],
            session_logger=sl,
        ))
    assert result.core_engine_applied == 2
    assert sl.log_postrun_artifact.called
    call_kwargs = sl.log_postrun_artifact.call_args.kwargs
    assert call_kwargs["kind"] == "core_engine_observation"
    assert "stacking debuffs" in call_kwargs["summary"]
    assert call_kwargs["after"]["engine_mechanic"] == "stacking debuffs while stalling"


def test_update_card_notes_skips_engine_artifact_on_dry_run():
    """Dry-run: even when engine is parsed, no artifact emitted (no apply)."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "M", "core_cards": ["X"],'
        '                 "support_cards": [], "notes": "N"}}'
    )
    sl = MagicMock()
    sl.log_postrun_artifact = MagicMock()
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["X"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["X"],
            final_relics=[],
            dry_run=True,
            session_logger=sl,
        ))
    sl.log_postrun_artifact.assert_not_called()


def test_update_card_notes_no_artifact_when_engine_not_applied():
    """Engine emitted but empty sentinel → no apply → no artifact."""
    from src.memory.card_memory_store import CardMemoryStore
    from src.memory.card_note_updater import update_card_notes_from_traces

    store = CardMemoryStore()
    response = (
        '{"updates": [],'
        ' "core_engine": {"engine_mechanic": "", "core_cards": [],'
        '                 "support_cards": [], "notes": ""}}'
    )
    sl = MagicMock()
    sl.log_postrun_artifact = MagicMock()
    with patch(
        "src.memory.card_note_updater.call_raw",
        new=_mock_call_raw_factory(response),
    ):
        asyncio.run(update_card_notes_from_traces(
            store=store,
            character="silent",
            combat_trace_text="(trace)",
            candidate_cards=["Strike"],
            run_id="r1",
            is_act3_boss_victory=True,
            final_deck=["Strike"],
            final_relics=[],
            session_logger=sl,
        ))
    sl.log_postrun_artifact.assert_not_called()


# ── First-encounter prompt rule (2026-04-28) ────────────────


def test_prompt_contains_mandatory_first_note_rule():
    """The prompt MUST contain the literal 'MANDATORY first-note rule' phrase
    so the LLM is forced to write notes for empty-noted candidates that
    appear in the trace.
    """
    from src.memory.card_note_updater import _UPDATER_PROMPT_TEMPLATE
    assert "MANDATORY first-note rule" in _UPDATER_PROMPT_TEMPLATE


def test_prompt_references_actual_empty_note_renderings():
    """The prompt's empty-note literal must match what _render_candidate_table
    actually emits: '(empty)' or '(no memory yet)'.
    """
    from src.memory.card_note_updater import _UPDATER_PROMPT_TEMPLATE
    assert "(empty)" in _UPDATER_PROMPT_TEMPLATE
    assert "(no memory yet)" in _UPDATER_PROMPT_TEMPLATE


def test_prompt_keeps_no_invent_safeguard():
    """The 'Never invent cards' guardrail must remain after the strengthening."""
    from src.memory.card_note_updater import _UPDATER_PROMPT_TEMPLATE
    assert "Never invent cards" in _UPDATER_PROMPT_TEMPLATE


# ── Trace inlining + class pool injection (2026-05-01) ────────


def test_update_card_notes_inlines_trace_into_prompt(monkeypatch, tmp_path):
    """When combat_trace_text is provided, it must appear in the prompt
    body sent to call_raw."""
    import asyncio
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"updates": []}', 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)

    store = CardMemoryStore()
    asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="UNIQUE_TRACE_MARKER_42",
        candidate_cards=["Backstab"],
        run_id="test-run",
        dry_run=True,
    ))

    assert "UNIQUE_TRACE_MARKER_42" in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]


def test_update_card_notes_appends_class_pool_to_system(monkeypatch, tmp_path):
    import asyncio
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        return ('{"updates": []}', 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)

    store = CardMemoryStore()
    asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace",
        candidate_cards=["Backstab"],
        run_id="test-run",
        dry_run=True,
    ))

    assert "## Class Pool Reference (Silent" in captured["system"]


def test_update_card_notes_writes_bucket_b_skipped_entry(monkeypatch, tmp_path):
    """End-to-end: a valid bucket B 'skipped' entry lands in the store
    with reason prefixed [skipped]."""
    import asyncio
    import json
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    payload = {
        "updates": [],
        "non_deck_updates": [{
            "card_name": "Footwork",
            "new_note": "Top poison payoff; take whenever offered.",
            "evidence_type": "skipped",
            "reason": "Skipped at card_reward floor 9.",
            "trace_citation": "Combat 3 R1: skipped Footwork",
        }],
    }

    async def _fake_call_raw(system, prompt, **kwargs):
        return (json.dumps(payload), 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)
    import config as _config
    monkeypatch.setattr(_config, "POSTRUN_NOTE_UPDATE_ENABLED", True, raising=False)

    store = CardMemoryStore()
    result = asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace text",
        candidate_cards=["Backstab"],
        run_id="test-run",
        skipped_cards=["Footwork"],
        final_deck=["Strike", "Defend"],
        final_relics=[],
        dry_run=False,
    ))

    assert result.non_deck_written == 1
    assert result.non_deck_dropped == 0
    written = store.get("the silent", "footwork")
    assert written is not None
    assert written.note.startswith("Top poison payoff")
    assert any("[skipped]" in (h.get("reason") or "") for h in written.note_history)


def test_update_card_notes_drops_bucket_b_when_skipped_cards_empty(monkeypatch, tmp_path):
    """With no skipped_cards passed in, a 'skipped'-type entry must be dropped."""
    import asyncio
    import json
    from src.memory import card_note_updater as cnu
    from src.memory.card_memory_store import CardMemoryStore

    payload = {
        "updates": [],
        "non_deck_updates": [{
            "card_name": "Footwork",
            "new_note": "x" * 50,
            "evidence_type": "skipped",
            "reason": "skipped",
            "trace_citation": "cite",
        }],
    }

    async def _fake_call_raw(system, prompt, **kwargs):
        return (json.dumps(payload), 50.0, 50)

    monkeypatch.setattr(cnu, "call_raw", _fake_call_raw)
    import config as _config
    monkeypatch.setattr(_config, "POSTRUN_NOTE_UPDATE_ENABLED", True, raising=False)

    store = CardMemoryStore()
    result = asyncio.run(cnu.update_card_notes_from_traces(
        store=store,
        character="silent",
        combat_trace_text="trace",
        candidate_cards=["Backstab"],
        run_id="test-run",
        skipped_cards=[],
        final_deck=["Strike"],
        final_relics=[],
        dry_run=False,
    ))

    assert result.non_deck_written == 0
    assert result.non_deck_dropped == 1
