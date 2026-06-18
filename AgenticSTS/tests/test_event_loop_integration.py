"""Tests for event loop integration and state diff capture."""
from types import SimpleNamespace

from src.agent.loop import _compute_event_state_diff


def _card(name: str, upgraded: bool = False):
    return SimpleNamespace(name=name, upgraded=upgraded)


def _relic(name: str):
    return SimpleNamespace(name=name)


def _potion(name: str | None, occupied: bool = True):
    return SimpleNamespace(name=name, occupied=occupied)


def _gs(*, hp=57, gold=110, deck=None, relics=None, potions=None):
    return SimpleNamespace(
        player_hp=hp,
        gold=gold,
        deck=list(deck or []),
        relics=list(relics or []),
        potions=list(potions or []),
    )


def test_compute_event_state_diff_detects_transform_relic_and_potion_gain():
    prev_gs = _gs(
        deck=[_card("Neutralize", upgraded=True), _card("Strike")],
        relics=[],
        potions=[_potion("Fire Potion"), _potion(None, occupied=False), _potion(None, occupied=False)],
    )
    next_gs = _gs(
        deck=[_card("Suppress", upgraded=True), _card("Strike")],
        relics=[_relic("Happy Flower")],
        potions=[_potion("Fire Potion"), _potion("Block Potion"), _potion(None, occupied=False)],
    )

    diff = _compute_event_state_diff(prev_gs, next_gs)

    assert diff["cards_gained"] == ["Suppress+"]
    assert diff["cards_lost"] == ["Neutralize+"]
    assert diff["relics_gained"] == ["Happy Flower"]
    assert diff["potions_gained"] == ["Block Potion"]


def test_compute_event_state_diff_handles_missing_next_state():
    prev_gs = _gs(deck=[_card("Strike")], relics=[_relic("Anchor")], potions=[_potion("Fire Potion")])
    diff = _compute_event_state_diff(prev_gs, None)
    assert diff == {
        "cards_gained": [],
        "cards_lost": [],
        "relics_gained": [],
        "potions_gained": [],
    }


def test_compute_event_state_diff_no_changes():
    prev_gs = _gs(
        deck=[_card("Strike"), _card("Defend")],
        relics=[_relic("Anchor")],
        potions=[_potion("Fire Potion")],
    )
    next_gs = _gs(
        deck=[_card("Strike"), _card("Defend")],
        relics=[_relic("Anchor")],
        potions=[_potion("Fire Potion")],
    )
    diff = _compute_event_state_diff(prev_gs, next_gs)
    assert diff["cards_gained"] == []
    assert diff["cards_lost"] == []
    assert diff["relics_gained"] == []
    assert diff["potions_gained"] == []


def test_compute_event_state_diff_card_gain_only():
    prev_gs = _gs(deck=[_card("Strike")], relics=[], potions=[])
    next_gs = _gs(deck=[_card("Strike"), _card("Shiv")], relics=[], potions=[])
    diff = _compute_event_state_diff(prev_gs, next_gs)
    assert diff["cards_gained"] == ["Shiv"]
    assert diff["cards_lost"] == []


def test_track_event_lifecycle_resolves_chosen_index_from_decision():
    """_track_event_lifecycle reads option_index from Decision.action dict."""
    from unittest.mock import MagicMock, patch

    from src.agent.loop import AgentLoop
    from src.memory.short_term import ShortTermMemory
    from src.state.run_state import Decision, RunState

    client = MagicMock()
    loop = AgentLoop.__new__(AgentLoop)
    loop._memory = MagicMock()
    stm = ShortTermMemory()
    loop._memory.short_term = stm

    # Simulate: event was started (Orobas, floor 18)
    stm.start_event("OROBAS", "Orobas", 18, 2, 57, 110, ["Strike"])

    # Simulate: run_state has a recorded event decision
    rs = RunState(run_id="test")
    rs.record_decision(Decision(
        floor=18,
        state_type="event",
        action={"action": "choose_event_option", "option_index": 1},
        reasoning="test",
        source="llm",
    ))
    loop._run_state = rs

    # Build the prev_event_gs mock (event screen)
    prev_event_gs = MagicMock()
    prev_event_gs.event = MagicMock()
    opt0, opt1, opt2 = MagicMock(), MagicMock(), MagicMock()
    opt0.title = "Gear Glass"
    opt0.description = ""
    opt0.effect_description = ""
    opt0.hp_cost = None
    opt0.gold_cost = None
    opt0.is_proceed = False
    opt0.relics_offered = []
    opt0.cards_offered = []
    opt0.potions_offered = []
    opt1.title = "Alchemical Coffer"
    opt1.description = ""
    opt1.effect_description = ""
    opt1.hp_cost = None
    opt1.gold_cost = None
    opt1.is_proceed = False
    opt1.relics_offered = []
    opt1.cards_offered = []
    opt1.potions_offered = []
    opt2.title = "Archaic Tooth"
    opt2.description = ""
    opt2.effect_description = ""
    opt2.hp_cost = None
    opt2.gold_cost = None
    opt2.is_proceed = False
    opt2.relics_offered = []
    opt2.cards_offered = []
    opt2.potions_offered = []
    prev_event_gs.event.options = [opt0, opt1, opt2]
    prev_event_gs.event.event_id = "OROBAS"
    prev_event_gs.floor = 18
    prev_event_gs.deck = [SimpleNamespace(name="Strike", upgraded=False)]
    prev_event_gs.relics = []
    prev_event_gs.potions = []
    loop._prev_event_gs = prev_event_gs

    # Now simulate next state: left the event, now on map
    next_gs = MagicMock()
    next_gs.state_type = "map"
    next_gs.event = None
    next_gs.player_hp = 55
    next_gs.gold = 100
    next_gs.deck = [SimpleNamespace(name="Strike", upgraded=False)]
    next_gs.relics = []
    next_gs.potions = []

    loop._track_event_lifecycle(next_gs)

    # Verify: event was finalized with correct chosen_index
    assert len(stm.completed_events) == 1
    completed = stm.completed_events[0]
    assert completed.chosen_option_index == 1
    assert completed.chosen_option_text == "Alchemical Coffer"
    assert completed.all_options == ["Gear Glass", "Alchemical Coffer", "Archaic Tooth"]


def test_finalize_event_stage_drops_proceed_only_by_title_when_flag_missing():
    """Closing Proceed pages where mod's IsProceed reflection returns False
    should still be dropped based on title alone."""
    from unittest.mock import MagicMock

    from src.agent.loop import AgentLoop
    from src.memory.short_term import ShortTermMemory
    from src.state.run_state import Decision, RunState

    loop = AgentLoop.__new__(AgentLoop)
    loop._memory = MagicMock()
    stm = ShortTermMemory()
    loop._memory.short_term = stm
    stm.start_event("TEZCATARA", "Tezcatara", 18, 2, 50, 100, ["Strike"])

    rs = RunState(run_id="test")
    rs.record_decision(Decision(
        floor=18,
        state_type="event",
        action={"action": "choose_event_option", "option_index": 0},
        reasoning="test",
        source="llm",
    ))
    loop._run_state = rs

    prev_event_gs = MagicMock()
    prev_event_gs.event = MagicMock()
    proceed_opt = MagicMock()
    proceed_opt.title = "Proceed"
    proceed_opt.description = ""
    proceed_opt.effect_description = ""
    proceed_opt.hp_cost = None
    proceed_opt.gold_cost = None
    proceed_opt.is_proceed = False
    proceed_opt.relics_offered = []
    proceed_opt.cards_offered = []
    proceed_opt.potions_offered = []
    prev_event_gs.event.options = [proceed_opt]
    prev_event_gs.event.event_id = "TEZCATARA"
    prev_event_gs.floor = 18
    prev_event_gs.deck = [SimpleNamespace(name="Strike", upgraded=False)]
    prev_event_gs.relics = []
    prev_event_gs.potions = []
    loop._prev_event_gs = prev_event_gs

    next_gs = MagicMock()
    next_gs.state_type = "map"
    next_gs.event = None
    next_gs.player_hp = 50
    next_gs.gold = 100
    next_gs.deck = [SimpleNamespace(name="Strike", upgraded=False)]
    next_gs.relics = []
    next_gs.potions = []

    loop._track_event_lifecycle(next_gs)

    assert stm.completed_events == []
    assert stm.current_event is None
