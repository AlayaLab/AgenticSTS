"""Tests for enhanced event prompt with rich option details."""
from unittest.mock import MagicMock

from src.brain.prompts.event import build_event_prompt


def _make_gs(event_id="OROBAS", options=None):
    """Build a minimal GameState mock with event data."""
    gs = MagicMock()
    gs.player_hp = 57
    gs.player_max_hp = 57
    gs.hp_ratio = 1.0
    gs.gold = 110
    gs.act = 2
    gs.floor = 18
    gs.state_type = "event"

    ev = MagicMock()
    ev.event_id = event_id
    ev.title = "Orobas"
    ev.description = "An ancient event with powerful choices."
    ev.options = options or []
    gs.event = ev
    return gs


def _make_option(index, title, description="", cards_offered=None,
                 relics_offered=None, potions_offered=None,
                 hp_cost=None, gold_cost=None, effect_description="",
                 is_locked=False, is_proceed=False, will_kill_player=False):
    opt = MagicMock()
    opt.index = index
    opt.title = title
    opt.description = description
    opt.is_locked = is_locked
    opt.is_proceed = is_proceed
    opt.will_kill_player = will_kill_player
    opt.effect_description = effect_description
    opt.hp_cost = hp_cost
    opt.gold_cost = gold_cost
    opt.cards_offered = cards_offered or []
    opt.relics_offered = relics_offered or []
    opt.potions_offered = potions_offered or []
    opt.curses_risk = []
    return opt


def test_card_effects_shown_in_prompt():
    """When an option offers cards, their effects appear in the prompt."""
    opt = _make_option(
        index=2,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        cards_offered=[{
            "name": "Suppress+",
            "cost": 1,
            "type": "Skill",
            "rules_text": "Apply 3 Weak. Draw 1 card.",
            "is_upgraded": True,
        }],
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Suppress+" in prompt
    assert "Apply 3 Weak" in prompt


def test_relic_description_shown():
    """When an option offers a relic, its description appears."""
    opt = _make_option(
        index=0,
        title="Accept the gift",
        relics_offered=[{
            "name": "Happy Flower",
            "description": "Every 3 turns, gain Energy.",
            "rarity": "common",
        }],
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Happy Flower" in prompt
    assert "Every 3 turns" in prompt


def test_hp_gold_cost_shown():
    """HP and gold costs are displayed when present."""
    opt = _make_option(
        index=0,
        title="Blood Sacrifice",
        description="Lose 10 HP, gain a random relic.",
        hp_cost=10,
    )
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "HP cost: 10" in prompt


def test_backward_compat_no_extended_fields():
    """Options without extended fields still render correctly."""
    opt = MagicMock()
    opt.index = 0
    opt.title = "Basic Option"
    opt.description = "A simple choice."
    opt.is_locked = False
    opt.is_proceed = False
    opt.will_kill_player = False
    opt.cards_offered = []
    opt.relics_offered = []
    opt.potions_offered = []
    opt.hp_cost = None
    opt.gold_cost = None
    opt.effect_description = ""
    opt.curses_risk = []
    gs = _make_gs(options=[opt])
    prompt = build_event_prompt(gs)
    assert "Basic Option" in prompt
