"""Tests for EventGuide consolidation."""
from src.memory.event_guide_consolidator import (
    build_event_guide_prompt,
    parse_event_guide_response,
)
from src.memory.event_models import (
    EventGuide,
    EventMemory,
    EventOptionSnapshot,
    RelicReward,
)


def test_parse_event_guide_response():
    raw = """
    {
      "guide_text": "- Prefer Alchemical Coffer when potion slots are low.",
      "confidence": 0.7
    }
    """
    guide = parse_event_guide_response(
        raw,
        event_id="OROBAS",
        character="silent",
        episode_count=4,
        memories=[],
        existing_guide=None,
    )
    assert guide is not None
    assert guide.event_id == "OROBAS"
    assert guide.confidence == 0.7
    assert "Alchemical Coffer" in guide.guide_text
    assert guide.version == 1


def test_parse_event_guide_response_updates_version():
    existing = EventGuide(
        event_id="OROBAS",
        character="silent",
        guide_text="Old guide",
        version=2,
    )
    raw = '{"guide_text": "New guide", "confidence": 0.8}'
    guide = parse_event_guide_response(
        raw,
        event_id="OROBAS",
        character="silent",
        episode_count=6,
        memories=[],
        existing_guide=existing,
    )
    assert guide is not None
    assert guide.version == 3


def test_build_event_guide_prompt_includes_run_outcome_tag():
    """Guide prompt shows the final run outcome for every encounter so the
    consolidator can score options itself — the separate boss-impact LLM pass
    was removed in favour of guide-level reasoning."""
    mem = EventMemory(
        event_id="OROBAS",
        event_title="Orobas",
        character="silent",
        floor=18,
        act=2,
        chosen_option_text="Alchemical Coffer",
        run_victory=True,
        run_final_floor=51,
    )
    prompt = build_event_guide_prompt("OROBAS", "silent", [mem])
    assert "Alchemical Coffer" in prompt
    assert "VICTORY F51" in prompt


def test_parse_event_guide_response_handles_garbage():
    assert parse_event_guide_response("not json", "X", "y", 1, []) is None
    assert parse_event_guide_response('{"guide_text": ""}', "X", "y", 1, []) is None


def test_event_guide_prompt_includes_option_details():
    """Guide consolidation prompt should show all options when details available."""
    opts = (
        EventOptionSnapshot(index=0, title="Grab the Sword",
                            description="Obtain the Sword of Stone.",
                            relics_offered=(RelicReward(name="Sword of Stone"),)),
        EventOptionSnapshot(index=1, title="Dive into the Water",
                            description="Gain 111 Gold. Lose 7 HP.",
                            hp_cost=7),
    )
    em = EventMemory(
        event_id="SUNKEN_STATUE",
        event_title="The Sunken Statue",
        floor=8, act=1,
        chosen_option_text="Grab the Sword",
        all_option_details=opts,
        run_victory=False,
        run_final_floor=22,
    )
    prompt = build_event_guide_prompt("SUNKEN_STATUE", "the silent", [em])
    assert "Dive into the Water" in prompt
    assert "Obtain the Sword of Stone" in prompt
    assert "Gain 111 Gold" in prompt


def test_select_event_keys_for_refresh_run_scoped():
    """Only (event_id, character) pairs from the current run are selected."""
    from src.memory.event_guide_consolidator import _select_event_keys_for_refresh
    from src.memory.event_models import EventMemory

    memories = [
        EventMemory(run_id="run_A", event_id="OROBAS", character="the silent"),
        EventMemory(run_id="run_A", event_id="SUNKEN_STATUE", character="the silent"),
        EventMemory(run_id="run_B", event_id="OROBAS", character="the ironclad"),
        EventMemory(run_id="run_B", event_id="DESIGNER", character="the ironclad"),
    ]
    selected = _select_event_keys_for_refresh(memories, current_run_id="run_A")
    assert selected == {
        ("OROBAS", "the silent"),
        ("SUNKEN_STATUE", "the silent"),
    }


def test_select_event_keys_normalizes_character():
    from src.memory.event_guide_consolidator import _select_event_keys_for_refresh
    from src.memory.event_models import EventMemory

    memories = [
        EventMemory(run_id="r", event_id="OROBAS", character="Silent"),
        EventMemory(run_id="r", event_id="OROBAS", character="静默猎人"),
    ]
    selected = _select_event_keys_for_refresh(memories, current_run_id="r")
    # Both records normalize to "the silent"
    assert selected == {("OROBAS", "the silent")}


def test_select_event_keys_empty_run():
    """No memories for the current run → empty selection."""
    from src.memory.event_guide_consolidator import _select_event_keys_for_refresh
    from src.memory.event_models import EventMemory

    memories = [
        EventMemory(run_id="old", event_id="OROBAS", character="the silent"),
    ]
    assert _select_event_keys_for_refresh(memories, current_run_id="new") == set()


def test_select_event_keys_uppercases_event_id():
    from src.memory.event_guide_consolidator import _select_event_keys_for_refresh
    from src.memory.event_models import EventMemory

    memories = [
        EventMemory(run_id="r", event_id="orobas", character="the silent"),
    ]
    assert _select_event_keys_for_refresh(memories, current_run_id="r") == {
        ("OROBAS", "the silent"),
    }


def test_event_guide_prompt_groups_playthroughs():
    """Memories with the same (run_id, floor) are grouped into one playthrough."""
    from src.memory.event_guide_consolidator import build_event_guide_prompt
    from src.memory.event_models import EventMemory, EventOptionSnapshot

    stage0 = EventMemory(
        run_id="runA", floor=18, act=2,
        event_id="BRIDGE", event_title="Bridge",
        character="the silent",
        chosen_option_index=0, chosen_option_text="Cross",
        all_option_details=(
            EventOptionSnapshot(index=0, title="Cross", description="Continue."),
            EventOptionSnapshot(index=1, title="Turn Back", description="Abandon."),
        ),
        timestamp=100.0,
        run_victory=True, run_final_floor=51,
    )
    stage1 = EventMemory(
        run_id="runA", floor=18, act=2,
        event_id="BRIDGE", event_title="Bridge",
        character="the silent",
        chosen_option_index=0, chosen_option_text="Fight",
        all_option_details=(
            EventOptionSnapshot(index=0, title="Fight", description="Elite."),
            EventOptionSnapshot(index=1, title="Flee", description="Lose HP."),
        ),
        timestamp=101.0,
        run_victory=True, run_final_floor=51,
    )
    prompt = build_event_guide_prompt("BRIDGE", "the silent", [stage0, stage1])
    # Both stages appear under the same playthrough header
    assert "Playthrough 1" in prompt
    assert prompt.count("Playthrough 1") == 1
    assert "Stage 0" in prompt
    assert "Stage 1" in prompt
    # Stages are ordered by timestamp
    idx_stage_0 = prompt.index("Stage 0")
    idx_stage_1 = prompt.index("Stage 1")
    assert idx_stage_0 < idx_stage_1


def test_event_guide_prompt_expands_reward_details_once():
    """Reward details (rules_text / rarity) show on first occurrence, then abbreviated."""
    from src.memory.event_guide_consolidator import build_event_guide_prompt
    from src.memory.event_models import EventMemory, EventOptionSnapshot, RelicReward

    archaic = RelicReward(
        name="Archaic Tooth",
        description="Transform a starter card into a stronger one.",
        rarity="uncommon",
    )
    opt = EventOptionSnapshot(
        index=2, title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        relics_offered=(archaic,),
    )
    mem1 = EventMemory(
        run_id="r1", floor=18, act=2, event_id="OROBAS", event_title="Orobas",
        character="the silent",
        chosen_option_index=2, chosen_option_text="Archaic Tooth",
        all_option_details=(opt,),
        run_victory=True, run_final_floor=51,
        timestamp=100.0,
    )
    mem2 = EventMemory(
        run_id="r2", floor=18, act=2, event_id="OROBAS", event_title="Orobas",
        character="the silent",
        chosen_option_index=2, chosen_option_text="Archaic Tooth",
        all_option_details=(opt,),
        run_victory=False, run_final_floor=34,
        timestamp=200.0,
    )
    prompt = build_event_guide_prompt("OROBAS", "the silent", [mem1, mem2])
    # Full description appears exactly once
    assert prompt.count("Transform a starter card into a stronger one.") == 1
    # The abbreviated marker appears in the second playthrough
    assert "(same as Playthrough 1)" in prompt


def test_event_guide_prompt_json_output_spec():
    """Prompt instructs the LLM to emit the structured options JSON."""
    from src.memory.event_guide_consolidator import build_event_guide_prompt
    from src.memory.event_models import EventMemory

    mem = EventMemory(event_id="OROBAS", character="the silent",
                      run_victory=True, run_final_floor=51)
    prompt = build_event_guide_prompt("OROBAS", "the silent", [mem])
    assert '"options"' in prompt
    assert "canonical_name" in prompt
    assert "variant_type" in prompt
    assert '"score"' in prompt
    assert "fixed" in prompt and "random_from_pool" in prompt and "deck_random" in prompt


def test_event_guide_prompt_includes_run_outcome_anchor():
    """Each playthrough header shows victory/defeat + final floor."""
    from src.memory.event_guide_consolidator import build_event_guide_prompt
    from src.memory.event_models import EventMemory

    victory = EventMemory(
        run_id="rV", floor=18, event_id="OROBAS", character="the silent",
        run_victory=True, run_final_floor=51, timestamp=100.0,
    )
    defeat = EventMemory(
        run_id="rD", floor=18, event_id="OROBAS", character="the silent",
        run_victory=False, run_final_floor=34, timestamp=200.0,
    )
    prompt = build_event_guide_prompt("OROBAS", "the silent", [victory, defeat])
    assert "VICTORY F51" in prompt
    assert "DEFEAT F34" in prompt


def test_event_guide_prompt_caps_at_12_playthroughs():
    """Only the 12 most recent playthroughs (by max timestamp in group) are rendered."""
    from src.memory.event_guide_consolidator import build_event_guide_prompt
    from src.memory.event_models import EventMemory

    memories = [
        EventMemory(
            run_id=f"r{i}", floor=18, event_id="OROBAS", character="the silent",
            run_victory=(i % 2 == 0), run_final_floor=30 + i,
            timestamp=float(i),
        )
        for i in range(20)
    ]
    prompt = build_event_guide_prompt("OROBAS", "the silent", memories)
    # Only 12 most recent playthroughs appear
    playthrough_count = prompt.count("Playthrough ")
    assert playthrough_count == 12
    # The most recent (r19) is present, the oldest (r0) is absent
    assert "r19" in prompt
    assert "r0," not in prompt  # trailing comma to avoid matching r19


def test_parse_event_guide_response_parses_options():
    from src.memory.event_guide_consolidator import parse_event_guide_response
    from src.memory.event_models import EventMemory, EventOptionSnapshot

    raw = """{
      "guide_text": "Orobas is always a free power spike.",
      "confidence": 0.85,
      "options": [
        {"canonical_name": "Archaic Tooth", "stage_index": 0,
         "variant_type": "fixed", "score": 0.7,
         "analysis": "Free upgrade to starter.",
         "observed_rewards": ["Suppress+"], "sample_size": 99},
        {"canonical_name": "Demon Glass", "stage_index": 0,
         "variant_type": "random_from_pool", "score": 0.3,
         "analysis": "Deck injection.",
         "observed_rewards": ["Bash"], "sample_size": 99}
      ]
    }"""
    # Memories: two records with titles matching canonical_name
    memories = [
        EventMemory(all_option_details=(
            EventOptionSnapshot(index=2, title="Archaic Tooth"),
            EventOptionSnapshot(index=0, title="Demon Glass"),
        )),
        EventMemory(all_option_details=(
            EventOptionSnapshot(index=2, title="Archaic Tooth"),
        )),
    ]
    guide = parse_event_guide_response(
        raw, event_id="OROBAS", character="the silent",
        episode_count=2, memories=memories,
    )
    assert guide is not None
    assert len(guide.options) == 2
    names = {o.canonical_name for o in guide.options}
    assert names == {"Archaic Tooth", "Demon Glass"}
    # sample_size recomputed server-side (LLM said 99, memories say otherwise)
    archaic = next(o for o in guide.options if o.canonical_name == "Archaic Tooth")
    demon = next(o for o in guide.options if o.canonical_name == "Demon Glass")
    assert archaic.sample_size == 2   # appeared in both memories
    assert demon.sample_size == 1


def test_parse_event_guide_response_drops_malformed_options():
    """Malformed option entries are skipped; valid siblings survive."""
    from src.memory.event_guide_consolidator import parse_event_guide_response
    from src.memory.event_models import EventMemory, EventOptionSnapshot

    raw = """{
      "guide_text": "x",
      "options": [
        {"canonical_name": "Good", "stage_index": 0, "score": 0.5,
         "analysis": "fine"},
        "not a dict",
        {"missing_required": true}
      ]
    }"""
    mem = EventMemory(all_option_details=(
        EventOptionSnapshot(index=0, title="Good"),
    ))
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1, memories=[mem],
    )
    assert guide is not None
    # Only the one with a non-empty canonical_name survives
    assert len(guide.options) == 1
    assert guide.options[0].canonical_name == "Good"


def test_parse_event_guide_response_clamps_score_and_confidence():
    from src.memory.event_guide_consolidator import parse_event_guide_response
    from src.memory.event_models import EventMemory

    raw = """{
      "guide_text": "x",
      "confidence": 1.5,
      "options": [
        {"canonical_name": "A", "score": 2.0, "stage_index": 0, "analysis": "x"},
        {"canonical_name": "B", "score": -3.0, "stage_index": 0, "analysis": "x"}
      ]
    }"""
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1,
        memories=[EventMemory()],
    )
    assert guide is not None
    assert guide.confidence == 1.0
    scores = sorted(o.score for o in guide.options)
    assert scores == [-1.0, 1.0]


def test_parse_event_guide_response_handles_legacy_without_options():
    """Legacy LLM response (no `options` key) still produces a guide; options=()."""
    from src.memory.event_guide_consolidator import parse_event_guide_response
    from src.memory.event_models import EventMemory

    raw = '{"guide_text": "old-format advice", "confidence": 0.6}'
    guide = parse_event_guide_response(
        raw, event_id="X", character="y", episode_count=1,
        memories=[EventMemory()],
    )
    assert guide is not None
    assert guide.guide_text == "old-format advice"
    assert guide.options == ()


import pytest


@pytest.mark.asyncio
async def test_consolidate_guides_event_branch_is_run_scoped(monkeypatch):
    """The event branch only refreshes (event_id, character) pairs for current run."""
    from src.memory import guide_consolidator as gc
    from src.memory.event_models import EventMemory
    from src.memory.event_store import EventMemoryStore
    from src.memory.guide_store import GuideStore

    # Two events: OROBAS touched by run_A (current) and DESIGNER only by old runs.
    # Both have >= 2 total memories so the min_episodes gate passes for both,
    # but only OROBAS should be refreshed under run-scoped selection.
    mem_a = EventMemory(
        run_id="run_A", event_id="OROBAS", character="the silent",
        chosen_option_text="Archaic Tooth",
        run_victory=True, run_final_floor=51,
    )
    mem_a2 = EventMemory(
        run_id="old_A", event_id="OROBAS", character="the silent",
        chosen_option_text="Demon Glass",
        run_victory=True, run_final_floor=55,
    )
    # DESIGNER is present in two OLD runs (enough for min_episodes) but NOT run_A
    mem_b1 = EventMemory(
        run_id="run_B", event_id="DESIGNER", character="the ironclad",
        chosen_option_text="Upgrade",
        run_victory=False, run_final_floor=12,
    )
    mem_b2 = EventMemory(
        run_id="run_C", event_id="DESIGNER", character="the ironclad",
        chosen_option_text="Upgrade",
        run_victory=True, run_final_floor=40,
    )

    event_store = EventMemoryStore()
    event_store.add_batch([mem_a, mem_a2, mem_b1, mem_b2])
    guide_store = GuideStore()

    # Fake memory_manager
    from types import SimpleNamespace
    mm = SimpleNamespace(
        v2_enabled=True,
        combat_store=None,
        route_store=None,
        card_build_store=None,
        event_store=event_store,
        guide_store=guide_store,
    )

    # Mock the LLM caller
    call_log: list[tuple[str, str]] = []

    async def fake_llm_call(system, prompt, *, think=False, call_type=""):
        event_line = next(
            (line for line in prompt.split("\n") if line.startswith("Event:")),
            "",
        )
        event_id = event_line.split()[1] if len(event_line.split()) > 1 else "UNKNOWN"
        call_log.append((event_id, prompt))
        return (
            '{"guide_text": "ok", "confidence": 0.7, "options": []}',
            0.1,
            {"input_tokens": 10, "output_tokens": 5},
        )

    monkeypatch.setattr(
        "src.brain.llm_caller.call_raw", fake_llm_call,
    )

    stats = await gc.consolidate_guides(mm, current_run_id="run_A")

    # Only OROBAS/the silent was refreshed (run_A touched it).
    # DESIGNER/the ironclad is untouched (belonged to run_B).
    refreshed_event_ids = {call[0] for call in call_log}
    assert "OROBAS" in refreshed_event_ids
    assert "DESIGNER" not in refreshed_event_ids
    assert stats["event"] == 1


def test_parse_event_guide_response_garbage_returns_none():
    from src.memory.event_guide_consolidator import parse_event_guide_response

    assert parse_event_guide_response(
        "not json", event_id="X", character="y",
        episode_count=1, memories=[],
    ) is None
