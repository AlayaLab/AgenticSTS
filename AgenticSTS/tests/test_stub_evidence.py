"""Tests for stub evidence assembly: run selection, replay sampling, trajectory."""

from dataclasses import dataclass
from types import SimpleNamespace


@dataclass
class FakeRun:
    """Minimal RunRecord-like for testing selection."""
    run_id: str
    outcome: str
    started_at: float = 0.0


def test_select_runs_returns_only_current_when_history_has_one():
    from src.skills.stub_evidence import select_runs_for_fill
    history = [FakeRun("r1", "victory", 1.0)]
    selected = select_runs_for_fill(history)
    assert [r.run_id for r in selected] == ["r1"]


def test_select_runs_picks_current_plus_recent_win_plus_recent_loss():
    from src.skills.stub_evidence import select_runs_for_fill
    # Newest first
    history = [
        FakeRun("r5", "defeat", 5.0),     # current
        FakeRun("r4", "victory", 4.0),
        FakeRun("r3", "defeat", 3.0),
        FakeRun("r2", "victory", 2.0),
        FakeRun("r1", "defeat", 1.0),
    ]
    selected = select_runs_for_fill(history)
    ids = [r.run_id for r in selected]
    assert ids[0] == "r5"  # current
    assert "r4" in ids     # most recent win (excluding current)
    assert "r3" in ids     # most recent loss (excluding current)
    assert len(selected) == 3


def test_select_runs_skips_aborts_and_interrupts():
    from src.skills.stub_evidence import select_runs_for_fill
    history = [
        FakeRun("r3", "defeat", 3.0),       # current
        FakeRun("r2", "agent_abort", 2.0),  # not a real loss
        FakeRun("r1", "interrupt", 1.0),    # not a real loss
    ]
    selected = select_runs_for_fill(history)
    assert [r.run_id for r in selected] == ["r3"]


def test_select_runs_handles_current_is_win():
    from src.skills.stub_evidence import select_runs_for_fill
    history = [
        FakeRun("r3", "victory", 3.0),
        FakeRun("r2", "defeat", 2.0),
        FakeRun("r1", "victory", 1.0),
    ]
    selected = select_runs_for_fill(history)
    ids = [r.run_id for r in selected]
    assert "r3" in ids       # current
    assert "r2" in ids       # most recent loss
    # The recent_win search excludes the current run; r1 is the next win.
    assert "r1" in ids
    assert len(selected) == 3


def test_select_runs_empty_history_returns_empty():
    from src.skills.stub_evidence import select_runs_for_fill
    assert select_runs_for_fill([]) == []


# ── Combat replay sampling ──────────────────────────────────────


def _ep(combat_type: str, enemy_key: str = "x", run_id: str = ""):
    """Episode mock — minimal interface used by sampler.

    Real CombatEpisode is a frozen dataclass with run_id pre-set by the
    extractor. Tests pre-populate run_id to mirror that contract.
    """
    return SimpleNamespace(
        combat_type=combat_type,
        enemy_key=enemy_key,
        run_id=run_id,
    )


def test_sample_combat_stub_picks_one_hallway_one_elite_per_run():
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {
        "r1": [_ep("monster", run_id="r1"), _ep("monster", run_id="r1"),
               _ep("elite", run_id="r1"), _ep("boss", run_id="r1")],
        "r2": [_ep("monster", run_id="r2"), _ep("boss", run_id="r2")],
    }
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_combat",
        run_ids=["r1", "r2"],
        episodes_by_run=episodes_by_run,
    )
    # r1 yields 2 (one monster + one elite), r2 yields 1 (only one monster, no elite)
    assert len(replays) == 3
    types_r1 = sorted(e.combat_type for e in replays if e.run_id == "r1")
    assert types_r1 == ["elite", "monster"]
    # r2 contributes its monster, never the boss (boss stub handles those)
    types_r2 = [e.combat_type for e in replays if e.run_id == "r2"]
    assert types_r2 == ["monster"]


def test_sample_combat_stub_falls_back_to_two_monsters_when_no_elite():
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {
        "r1": [_ep("monster", run_id="r1"), _ep("monster", run_id="r1"),
               _ep("monster", run_id="r1")],
    }
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_combat",
        run_ids=["r1"],
        episodes_by_run=episodes_by_run,
    )
    assert len(replays) == 2
    assert all(e.combat_type == "monster" for e in replays)


def test_sample_boss_stub_includes_all_boss_episodes():
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {
        "r1": [_ep("monster", run_id="r1"),
               _ep("boss", "Insatiable", run_id="r1"),
               _ep("boss", "Champ", run_id="r1")],
        "r2": [_ep("monster", run_id="r2")],  # never reached boss
    }
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_boss",
        run_ids=["r1", "r2"],
        episodes_by_run=episodes_by_run,
    )
    assert len(replays) == 2
    assert all(e.combat_type == "boss" for e in replays)
    assert {e.enemy_key for e in replays} == {"Insatiable", "Champ"}


def test_sample_combat_returns_empty_for_non_combat_stub():
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {"r1": [_ep("monster", run_id="r1"), _ep("boss", run_id="r1")]}
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_deckbuilding",
        run_ids=["r1"],
        episodes_by_run=episodes_by_run,
    )
    assert replays == []


def test_sample_combat_handles_missing_run_id():
    """run_id absent from episodes_by_run → no contribution from that run."""
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    episodes_by_run = {"r1": [_ep("monster", run_id="r1"), _ep("elite", run_id="r1")]}
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_combat",
        run_ids=["r1", "r2_missing"],
        episodes_by_run=episodes_by_run,
    )
    assert len(replays) == 2  # only r1 contributes


def test_sample_combat_does_not_mutate_frozen_episodes():
    """Real CombatEpisode is frozen (dataclass(frozen=True)). The sampler
    must NOT attempt attribute assignment. Regression test for the bug
    discovered during 2026-05-03 live smoke (FrozenInstanceError on real
    episodes after stage 1 extraction).
    """
    from dataclasses import dataclass
    from src.skills.stub_evidence import sample_combat_replays_for_stub

    @dataclass(frozen=True)
    class FrozenEp:
        combat_type: str
        enemy_key: str
        run_id: str

    eps = [FrozenEp("monster", "x", "r1"), FrozenEp("elite", "y", "r1")]
    episodes_by_run = {"r1": eps}
    # Must not raise FrozenInstanceError
    replays = sample_combat_replays_for_stub(
        stub_id="stub_the_silent_combat",
        run_ids=["r1"],
        episodes_by_run=episodes_by_run,
    )
    assert len(replays) == 2


# ── Trajectory rendering for non-combat stubs ───────────────────


def _dec(floor, state_type, **kwargs):
    """Decision mock — minimal interface used by trajectory renderer."""
    return SimpleNamespace(
        floor=floor,
        state_type=state_type,
        action=kwargs.get("action", ""),
        option_index=kwargs.get("option_index", -1),
        reasoning=kwargs.get("reasoning", ""),
        strategic_note=kwargs.get("strategic_note", ""),
        hp_before=kwargs.get("hp_before", 0),
        hp_after=kwargs.get("hp_after", 0),
        gold_before=kwargs.get("gold_before", 0),
        gold_after=kwargs.get("gold_after", 0),
        deck_before=kwargs.get("deck_before", 0),
        deck_after=kwargs.get("deck_after", 0),
        deck_change=kwargs.get("deck_change", "no change"),
    )


def test_render_trajectory_filters_by_state_type_for_deckbuilding():
    from src.skills.stub_evidence import render_trajectory_for_stub

    decisions = [
        _dec("F1", "card_reward", action="resolve_rewards", option_index=1,
             reasoning="Backstab is premium",
             strategic_note="Foundation: frontload damage",
             hp_before=70, hp_after=70, gold_before=0, gold_after=0,
             deck_before=12, deck_after=13, deck_change="+Backstab"),
        _dec("F2", "monster", action="play_card", reasoning="should be filtered",
             hp_before=70, hp_after=65),
        _dec("F3", "shop", action="buy_card", option_index=0,
             reasoning="Removal is cheap",
             strategic_note="keep deck thin",
             hp_before=65, hp_after=65, gold_before=88, gold_after=13,
             deck_before=14, deck_after=15, deck_change="+Footwork"),
    ]
    rendered = render_trajectory_for_stub(
        stub_id="stub_the_silent_deckbuilding",
        run_id="r1",
        outcome="defeat",
        character="the silent",
        ascension=0,
        decisions=decisions,
    )
    assert "[F1 card_reward]" in rendered
    assert "[F3 shop]" in rendered
    assert "monster" not in rendered  # filtered out
    assert "Backstab" in rendered      # reasoning preserved
    assert "Foundation: frontload" in rendered  # strategic note preserved
    assert "OUTCOME=defeat" in rendered
    assert "the silent A0" in rendered


def test_render_trajectory_returns_empty_for_combat_stub():
    """Combat / boss stubs use replay sampling, not trajectories."""
    from src.skills.stub_evidence import render_trajectory_for_stub

    rendered = render_trajectory_for_stub(
        stub_id="stub_the_silent_combat",
        run_id="r1",
        outcome="defeat",
        character="the silent",
        ascension=0,
        decisions=[_dec("F1", "monster")],
    )
    assert rendered == ""


def test_render_trajectory_for_map_filters_to_map_only():
    from src.skills.stub_evidence import render_trajectory_for_stub

    decisions = [
        _dec("F1", "map", action="choose_map_node", option_index=0,
             reasoning="Take the easier path"),
        _dec("F2", "card_reward", reasoning="ignored by map stub"),
        _dec("F3", "map", action="choose_map_node", option_index=2,
             reasoning="Reroute for the shop"),
    ]
    rendered = render_trajectory_for_stub(
        stub_id="stub_the_silent_map",
        run_id="r1", outcome="victory", character="the silent",
        ascension=0, decisions=decisions,
    )
    assert "[F1 map]" in rendered
    assert "[F3 map]" in rendered
    assert "card_reward" not in rendered


def test_render_trajectory_for_intermission_includes_rest_and_event():
    from src.skills.stub_evidence import render_trajectory_for_stub

    decisions = [
        _dec("F1", "rest_site", action="choose_rest_option",
             reasoning="Smith my key card"),
        _dec("F2", "event", action="choose_event_option",
             reasoning="Take the relic"),
        _dec("F3", "shop", reasoning="ignored"),
    ]
    rendered = render_trajectory_for_stub(
        stub_id="stub_the_silent_intermission",
        run_id="r1", outcome="victory", character="the silent",
        ascension=0, decisions=decisions,
    )
    assert "rest_site" in rendered
    assert "event" in rendered
    assert "[F3 shop]" not in rendered


# ── Attribution Summary ────────────────────────────────────────


def test_attribution_summary_renders_top_cards_and_thread():
    from src.skills.stub_evidence import build_attribution_summary

    summary = build_attribution_summary(
        run_id="r1",
        final_deck=["Strike", "Defend", "Backstab"],
        final_relics=["Burning Blood"],
        death_cause="F33 Champ unblocked R5 Strike(28)",
        strategic_thread_evolution=[
            ("F1", "Foundation: frontload damage"),
            ("F12", "Committed: poison"),
        ],
        card_play_stats={
            "Backstab": {"plays": 22, "total_damage": 286, "total_block": 0},
            "Defend": {"plays": 40, "total_damage": 0, "total_block": 200},
            "Pinpoint": {"plays": 1, "total_damage": 8, "total_block": 0},
        },
    )
    assert "Most-played cards" in summary
    assert "Backstab" in summary
    # Pinpoint has only 1 play (≤4) → appears in rarely-used list
    assert "Pinpoint" in summary
    assert "Death cause" in summary
    assert "Foundation" in summary


def test_attribution_summary_handles_empty_data():
    from src.skills.stub_evidence import build_attribution_summary

    summary = build_attribution_summary(
        run_id="r1",
        final_deck=[],
        final_relics=[],
        death_cause="",
        strategic_thread_evolution=[],
        card_play_stats={},
    )
    # Even with empty inputs, render shouldn't crash; produces minimal summary
    assert "Attribution Summary" in summary
