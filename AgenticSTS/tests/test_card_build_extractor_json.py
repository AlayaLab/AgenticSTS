import asyncio

import src.brain.llm_caller as llm_caller
from src.memory.card_build_extractor import _extract_json_object, analyze_build_with_llm


def test_extract_json_object_from_fenced_block() -> None:
    raw = """```json
    {"primary_plan":"poison","build_tags":["poison","victory"]}
    ```"""

    assert _extract_json_object(raw) == (
        '{"primary_plan":"poison","build_tags":["poison","victory"]}'
    )


def test_extract_json_object_from_prefixed_response() -> None:
    raw = (
        "Here is the analysis you requested:\n"
        '{"primary_plan":"discard","notes":"keeps {brace} text inside strings"}\n'
        "Thanks!"
    )

    assert _extract_json_object(raw) == (
        '{"primary_plan":"discard","notes":"keeps {brace} text inside strings"}'
    )


def test_extract_json_object_handles_empty_text() -> None:
    assert _extract_json_object("") == ""


def test_analyze_build_with_llm_retries_after_empty_response(monkeypatch) -> None:
    calls = 0

    async def fake_call_raw(system: str, prompt: str, think: bool = False, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            return "", 12.0, 34
        return (
            '{"primary_plan":"general","build_tags":["victory"],'
            '"confidence":0.6,"key_cards":[],"coherence_score":0.4,'
            '"coherence_analysis":"Recovered on retry."}',
            15.0,
            55,
        )

    monkeypatch.setattr(llm_caller, "call_raw", fake_call_raw)
    evidence = {
        "character": "the silent",
        "victory": True,
        "final_floor": 52,
        "fitness": 180.0,
        "deck_size": 24,
        "combats_won": 11,
        "combats_total": 12,
        "final_deck": [],
    }

    analysis = asyncio.run(analyze_build_with_llm(evidence))

    assert calls == 2
    assert analysis["build_tags"] == ("victory",)
    assert analysis["confidence"] == 0.6
    assert analysis["coherence_score"] == 0.4


def test_analyze_build_with_llm_canonicalizes_silent_build(monkeypatch) -> None:
    async def fake_call_raw(system: str, prompt: str, think: bool = False, **kwargs):
        assert "Active Build Registry" in prompt
        return (
            '{"decision":"update_existing","target_build_id":"poison_stacking",'
            '"primary_plan":"poison stacking","build_tags":["thin_deck","victory"],'
            '"confidence":0.7,"card_roles":[{"card":"Noxious Fumes","role":"core",'
            '"phase":"commitment","evidence":"recurring poison scaling"}],'
            '"key_cards":[],"coherence_score":0.6,"coherence_analysis":"Clear poison plan."}',
            10.0,
            20,
        )

    monkeypatch.setattr(llm_caller, "call_raw", fake_call_raw)
    analysis = asyncio.run(analyze_build_with_llm({
        "character": "the silent",
        "victory": True,
        "final_floor": 48,
        "fitness": 180,
        "deck_size": 20,
        "combats_won": 10,
        "combats_total": 10,
        "final_deck": ["Noxious Fumes"],
    }))

    assert analysis["target_build_id"] == "poison"
    assert analysis["build_tags"] == ("poison", "victory")
    assert analysis["primary_plan"] == "poison"


def test_analyze_build_with_llm_inlines_combat_trace_into_prompt(monkeypatch):
    """When combat_trace_text is provided, it must appear in the prompt
    body sent to call_raw (single-block user content; no cache hack)."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(cbe, "call_raw", _fake_call_raw, raising=False)
    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(
        evidence, combat_trace_text="FAKE TRACE BLOCK",
    ))

    assert "FAKE TRACE BLOCK" in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]


def test_analyze_build_with_llm_no_trace_omits_trace_block(monkeypatch):
    """When combat_trace_text is empty, no trace text or instruction
    note about a trace appears in the prompt, and call_raw must not
    receive user_cached_prefix."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["prompt"] = prompt
        captured["kwargs"] = kwargs
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(evidence))

    assert "Additional context" not in captured["prompt"]
    assert "user_cached_prefix" not in captured["kwargs"]


def test_analyze_build_with_llm_appends_class_pool_to_system(monkeypatch):
    """Turn 1's system prompt must include the class pool reference for
    the run's character."""
    from src.memory import card_build_extractor as cbe

    captured: dict = {}

    async def _fake_call_raw(system, prompt, **kwargs):
        captured["system"] = system
        return ('{"decision":"reject_no_clear_build","target_build_id":"",'
                '"build_summary":"x","primary_plan":"y","damage_engine":"z",'
                '"defense_engine":"z","cycle_engine":"z","energy_engine":"z",'
                '"build_tags":["defeat"],"card_roles":[],"weak_points":"w",'
                '"confidence":0.3,"key_cards":[],"coherence_score":0.5,'
                '"coherence_analysis":"x"}', 100.0, 100)

    monkeypatch.setattr(llm_caller, "call_raw", _fake_call_raw)

    evidence = {
        "character": "silent",
        "victory": False,
        "final_floor": 8,
        "fitness": 50.0,
        "deck_size": 20,
        "combats_won": 1,
        "combats_total": 2,
        "final_deck": [],
    }
    asyncio.run(cbe.analyze_build_with_llm(evidence))

    assert "## Class Pool Reference (Silent" in captured["system"]
    assert "Backstab" in captured["system"]
