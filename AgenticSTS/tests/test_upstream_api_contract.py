"""Regression tests for upstream STS2-Agent API contract.

Covers:
  - State invariants per screen type
  - Target-index contract
  - Action builder output format
  - Selection constraints
  - Reward / potion / shop / event / treasure flow
  - GameState convenience properties
  - LLM tool schema → to_action() → upstream format chain
"""

from __future__ import annotations

from types import SimpleNamespace

from src.brain.models import LLMDecision
from src.brain.tool_schemas import (
    CARD_REWARD_TOOL,
    CARD_SELECT_TOOL,
    COMBAT_PLAN_TOOL,
    COMBAT_TOOL,
    EVENT_TOOL,
    HAND_SELECT_TOOL,
    MAP_TOOL,
    POTION_TOOL,
    RELIC_SELECT_TOOL,
    REST_TOOL,
    SHOP_PLAN_TOOL,
    TREASURE_TOOL,
    get_tool_for_state,
)
from src.mcp_client import actions
from src.state.state_parser import parse_state

# ── Test data builders ───────────────────────────────────────


def _base_run() -> dict:
    return {
        "character_id": "ironclad",
        "character_name": "Ironclad",
        "floor": 6,
        "current_hp": 60,
        "max_hp": 80,
        "gold": 120,
        "max_energy": 3,
        "base_orb_slots": 0,
        "deck": [
            {
                "index": 0,
                "card_id": "strike",
                "name": "Strike",
                "upgraded": False,
                "card_type": "Attack",
                "rarity": "Starter",
                "costs_x": False,
                "star_costs_x": False,
                "energy_cost": 1,
                "star_cost": 0,
                "rules_text": "Deal 6 damage.",
            }
        ],
        "relics": [
            {
                "index": 0,
                "relic_id": "burning_blood",
                "name": "Burning Blood",
                "description": "Heal 6 HP at end of combat.",
                "stack": None,
                "is_melted": False,
            }
        ],
        "players": [],
        "potions": [
            {
                "index": 0,
                "potion_id": "fire_potion",
                "name": "Fire Potion",
                "description": "Deal 20 damage.",
                "rarity": "Common",
                "occupied": True,
                "usage": "Combat",
                "target_type": "Enemy",
                "is_queued": False,
                "requires_target": True,
                "target_index_space": "enemies",
                "valid_target_indices": [0],
                "can_use": True,
                "can_discard": True,
            },
            {
                "index": 1,
                "potion_id": None,
                "name": None,
                "description": None,
                "rarity": None,
                "occupied": False,
                "usage": None,
                "target_type": None,
                "is_queued": False,
                "requires_target": False,
                "target_index_space": None,
                "valid_target_indices": [],
                "can_use": False,
                "can_discard": False,
            },
        ],
    }


def _combat_state(**overrides) -> dict:
    base = {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "COMBAT",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": True,
        "turn": 2,
        "available_actions": ["play_card", "end_turn", "use_potion"],
        "combat": {
            "player": {
                "current_hp": 60,
                "max_hp": 80,
                "block": 0,
                "energy": 3,
                "stars": 0,
                "focus": 0,
                "powers": [],
                "base_orb_slots": 0,
                "orb_capacity": 0,
                "empty_orb_slots": 0,
                "orbs": [],
            },
            "players": [],
            "hand": [
                {
                    "index": 0,
                    "card_id": "strike",
                    "name": "Strike",
                    "upgraded": False,
                    "target_type": "Enemy",
                    "requires_target": True,
                    "target_index_space": "enemies",
                    "valid_target_indices": [0, 1],
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Deal 6 damage.",
                    "playable": True,
                    "unplayable_reason": None,
                },
                {
                    "index": 1,
                    "card_id": "defend",
                    "name": "Defend",
                    "upgraded": False,
                    "target_type": "None",
                    "requires_target": False,
                    "target_index_space": None,
                    "valid_target_indices": [],
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Gain 5 Block.",
                    "playable": True,
                    "unplayable_reason": None,
                },
            ],
            "enemies": [
                {
                    "index": 0,
                    "enemy_id": "louse",
                    "name": "Louse",
                    "current_hp": 12,
                    "max_hp": 15,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [],
                    "intent": "attack",
                    "move_id": "bite",
                    "intents": [
                        {
                            "index": 0,
                            "intent_type": "Attack",
                            "label": "6",
                            "damage": 6,
                            "hits": 1,
                            "total_damage": 6,
                        }
                    ],
                },
                {
                    "index": 1,
                    "enemy_id": "louse",
                    "name": "Louse",
                    "current_hp": 10,
                    "max_hp": 15,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [],
                    "intent": "attack",
                    "move_id": "bite",
                    "intents": [
                        {
                            "index": 0,
                            "intent_type": "Attack",
                            "label": "8",
                            "damage": 8,
                            "hits": 1,
                            "total_damage": 8,
                        }
                    ],
                },
            ],
        },
        "run": _base_run(),
        "map": {
            "current_node": {"row": 2, "col": 1},
            "is_travel_enabled": False,
            "is_traveling": False,
            "map_generation_count": 1,
            "rows": 15,
            "cols": 7,
            "starting_node": None,
            "boss_node": None,
            "second_boss_node": None,
            "nodes": [
                {
                    "row": 2,
                    "col": 1,
                    "node_type": "Combat",
                    "state": "REACHED",
                    "visited": True,
                    "is_current": True,
                    "is_available": False,
                    "is_start": False,
                    "is_boss": False,
                    "is_second_boss": False,
                    "parents": [],
                    "children": [],
                }
            ],
            "available_nodes": [],
        },
    }
    base.update(overrides)
    return base


def _map_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "MAP",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": ["choose_map_node"],
        "run": _base_run(),
        "map": {
            "current_node": {"row": 3, "col": 2},
            "is_travel_enabled": True,
            "is_traveling": False,
            "map_generation_count": 1,
            "rows": 15,
            "cols": 7,
            "starting_node": None,
            "boss_node": None,
            "second_boss_node": None,
            "nodes": [],
            "available_nodes": [
                {"index": 0, "row": 4, "col": 1, "node_type": "Elite", "state": "UNREACHED"},
                {"index": 1, "row": 4, "col": 3, "node_type": "Event", "state": "UNREACHED"},
            ],
        },
    }


def _event_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "EVENT",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": ["choose_event_option"],
        "run": _base_run(),
        "event": {
            "event_id": "big_fish",
            "title": "Big Fish",
            "description": "A massive fish blocks your path.",
            "is_finished": False,
            "options": [
                {
                    "index": 0,
                    "text_key": "eat",
                    "title": "Eat",
                    "description": "Heal 5 HP.",
                    "is_locked": False,
                    "is_proceed": False,
                    "will_kill_player": False,
                    "has_relic_preview": False,
                },
                {
                    "index": 1,
                    "text_key": "banana",
                    "title": "Feed Banana",
                    "description": "Gain a relic.",
                    "is_locked": False,
                    "is_proceed": False,
                    "will_kill_player": False,
                    "has_relic_preview": True,
                },
                {
                    "index": 2,
                    "text_key": "death",
                    "title": "Challenge",
                    "description": "Die instantly.",
                    "is_locked": False,
                    "is_proceed": False,
                    "will_kill_player": True,
                    "has_relic_preview": False,
                },
            ],
        },
    }


def _rest_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "REST",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": ["choose_rest_option"],
        "run": _base_run(),
        "rest": {
            "options": [
                {
                    "index": 0,
                    "option_id": "smith",
                    "title": "Smith",
                    "description": "Upgrade a card.",
                    "is_enabled": True,
                },
                {
                    "index": 1,
                    "option_id": "rest",
                    "title": "Rest",
                    "description": "Heal 30% of max HP.",
                    "is_enabled": True,
                },
            ]
        },
    }


def _shop_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "SHOP",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": ["buy_card", "buy_relic", "remove_card_at_shop", "proceed"],
        "run": _base_run(),
        "shop": {
            "is_open": True,
            "can_open": False,
            "can_close": True,
            "cards": [
                {
                    "index": 0,
                    "category": "card",
                    "card_id": "headbutt",
                    "name": "Headbutt",
                    "upgraded": False,
                    "card_type": "Attack",
                    "rarity": "Common",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Deal 9 damage.",
                    "price": 50,
                    "on_sale": False,
                    "is_stocked": True,
                    "enough_gold": True,
                }
            ],
            "relics": [
                {
                    "index": 0,
                    "relic_id": "vajra",
                    "name": "Vajra",
                    "description": "Start each combat with 1 Strength.",
                    "rarity": "Common",
                    "price": 150,
                    "is_stocked": True,
                    "enough_gold": False,
                }
            ],
            "potions": [
                {
                    "index": 0,
                    "potion_id": "fire_potion",
                    "name": "Fire Potion",
                    "description": "Deal 20 damage.",
                    "rarity": "Common",
                    "usage": "Combat",
                    "price": 65,
                    "is_stocked": True,
                    "enough_gold": True,
                }
            ],
            "card_removal": {"price": 75, "available": True, "used": False, "enough_gold": True},
        },
    }


def _reward_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "REWARD",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": [
            "claim_reward",
            "choose_reward_card",
            "choose_reward_alternative",
            "skip_reward_cards",
            "proceed",
        ],
        "run": _base_run(),
        "reward": {
            "pending_card_choice": True,
            "can_proceed": False,
            "rewards": [
                {"index": 0, "reward_type": "gold", "description": "25 Gold", "claimable": True},
                {
                    "index": 1,
                    "reward_type": "potion",
                    "description": "Fire Potion",
                    "claimable": True,
                },
            ],
            "card_options": [
                {
                    "index": 0,
                    "card_id": "anger",
                    "name": "Anger",
                    "upgraded": False,
                    "rules_text": "Deal 6 damage. Add a copy to discard.",
                },
                {
                    "index": 1,
                    "card_id": "cleave",
                    "name": "Cleave",
                    "upgraded": False,
                    "rules_text": "Deal 8 damage to ALL enemies.",
                },
            ],
            "alternatives": [{"index": 0, "label": "Skip"}],
        },
    }


def _chest_state(opened: bool = False, claimed: bool = False) -> dict:
    relics = (
        []
        if not opened
        else [
            {"index": 0, "relic_id": "war_paint", "name": "War Paint", "rarity": "Uncommon"},
        ]
    )
    avail = []
    if not opened:
        avail = ["open_chest"]
    elif not claimed and relics:
        avail = ["choose_treasure_relic", "proceed"]
    else:
        avail = ["proceed"]
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "CHEST",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": avail,
        "run": _base_run(),
        "chest": {"is_opened": opened, "has_relic_been_claimed": claimed, "relic_options": relics},
    }


def _selection_state(kind: str = "upgrade") -> dict:
    return {
        "state_version": 6,
        "run_id": "run_test",
        "screen": "CARD_SELECTION",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": False,
        "turn": None,
        "available_actions": ["select_deck_card", "confirm_selection"],
        "run": _base_run(),
        "selection": {
            "kind": kind,
            "prompt": "Choose a card to upgrade.",
            "min_select": 1,
            "max_select": 1,
            "selected_count": 0,
            "requires_confirmation": True,
            "can_confirm": False,
            "cards": [
                {
                    "index": 0,
                    "card_id": "strike",
                    "name": "Strike",
                    "upgraded": False,
                    "card_type": "Attack",
                    "rarity": "Starter",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Deal 6 damage.",
                },
            ],
        },
    }


# ── 1. State invariants per screen type ──────────────────────


def test_combat_state_type_from_node():
    gs = parse_state(_combat_state())
    assert gs.state_type == "monster"
    assert gs.is_combat
    assert gs.is_play_phase  # end_turn in available_actions


def test_elite_inferred_from_node_type():
    s = _combat_state()
    s["map"]["nodes"][0]["node_type"] = "Elite"
    gs = parse_state(s)
    assert gs.state_type == "elite"


def test_boss_inferred_from_is_boss():
    s = _combat_state()
    s["map"]["nodes"][0]["is_boss"] = True
    gs = parse_state(s)
    assert gs.state_type == "boss"


def test_map_state_type():
    gs = parse_state(_map_state())
    assert gs.state_type == "map"
    assert gs.is_map
    assert len(gs.next_map_options) == 2
    assert gs.next_map_options[0].node_type == "Elite"


def test_event_state_type():
    gs = parse_state(_event_state())
    assert gs.state_type == "event"
    assert gs.event is not None
    assert len(gs.event.options) == 3
    assert gs.event.options[2].will_kill_player is True


def test_rest_state_type():
    gs = parse_state(_rest_state())
    assert gs.state_type == "rest_site"
    assert gs.rest is not None
    assert gs.rest.options[0].option_id == "smith"
    assert gs.rest.options[1].option_id == "rest"


def test_shop_state_type():
    gs = parse_state(_shop_state())
    assert gs.state_type == "shop"
    assert gs.shop is not None
    assert len(gs.shop.cards) == 1
    assert len(gs.shop.relics) == 1
    assert len(gs.shop.potions) == 1
    assert gs.shop.relics[0].description == "Start each combat with 1 Strength."
    assert gs.shop.potions[0].description == "Deal 20 damage."
    assert gs.shop.card_removal is not None
    assert gs.shop.card_removal.enough_gold is True


def test_reward_card_choice_state_type():
    gs = parse_state(_reward_state())
    assert gs.state_type == "card_reward"
    assert gs.reward is not None
    assert gs.reward.pending_card_choice is True
    assert len(gs.reward.card_options) == 2
    assert len(gs.reward.alternatives) == 1


def test_chest_state_type():
    gs = parse_state(_chest_state(opened=True))
    assert gs.state_type == "treasure"
    assert gs.chest is not None
    assert len(gs.chest.relic_options) == 1


def test_card_select_state_type():
    gs = parse_state(_selection_state("upgrade"))
    assert gs.state_type == "card_select"
    assert gs.selection is not None
    assert gs.selection.min_select == 1


def test_hand_select_state_type():
    gs = parse_state(_selection_state("hand"))
    assert gs.state_type == "hand_select"
    assert gs.is_hand_select


def test_combat_hand_select_state_type():
    s = _selection_state("combat_hand_select")
    s["in_combat"] = True
    s["selection"]["prompt"] = (
        "[center]Choose [blue]2[/blue] cards to [gold]Discard[/gold].[/center]"
    )
    s["selection"]["min_select"] = 2
    s["selection"]["max_select"] = 2
    gs = parse_state(s)
    assert gs.state_type == "hand_select"
    assert gs.is_hand_select


# ── 2. Target-index contract ─────────────────────────────────


def test_enemy_valid_target_indices():
    gs = parse_state(_combat_state())
    card = gs.hand[0]  # Strike, requires_target=True
    assert card.requires_target is True
    assert card.valid_target_indices == [0, 1]
    assert card.target_index_space == "enemies"


def test_potion_valid_target_indices():
    gs = parse_state(_combat_state())
    pot = gs.potions[0]  # Fire Potion
    assert pot.requires_target is True
    assert pot.valid_target_indices == [0]
    assert pot.can_use is True


def test_enemy_is_alive_filtering():
    s = _combat_state()
    s["combat"]["enemies"][1]["is_alive"] = False
    gs = parse_state(s)
    assert len(gs.enemies) == 1  # Only alive enemies
    assert gs.enemies[0].index == 0


def test_enemy_is_hittable():
    gs = parse_state(_combat_state())
    assert gs.enemies[0].is_hittable is True


# ── 3. Action builder output format ─────────────────────────


def test_play_card_action_format():
    a = actions.play_card(0, target_index=1)
    assert a == {"action": "play_card", "card_index": 0, "target_index": 1}


def test_play_card_no_target():
    a = actions.play_card(1)
    assert a == {"action": "play_card", "card_index": 1}
    assert "target_index" not in a


def test_end_turn_action():
    a = actions.end_turn()
    assert a == {"action": "end_turn"}


def test_use_potion_action():
    a = actions.use_potion(0, target_index=1)
    assert a == {"action": "use_potion", "option_index": 0, "target_index": 1}


def test_choose_map_node_action():
    a = actions.choose_map_node(1)
    assert a == {"action": "choose_map_node", "option_index": 1}


def test_choose_event_option_action():
    a = actions.choose_event_option(0)
    assert a == {"action": "choose_event_option", "option_index": 0}


def test_choose_rest_option_action():
    a = actions.choose_rest_option(1)
    assert a == {"action": "choose_rest_option", "option_index": 1}


def test_buy_card_action():
    a = actions.buy_card(0)
    assert a == {"action": "buy_card", "option_index": 0}


def test_remove_card_at_shop_action():
    a = actions.remove_card_at_shop()
    assert a == {"action": "remove_card_at_shop"}


def test_choose_reward_card_action():
    a = actions.choose_reward_card(0)
    assert a == {"action": "choose_reward_card", "option_index": 0}


def test_choose_reward_alternative_action():
    a = actions.choose_reward_alternative(1)
    assert a == {"action": "choose_reward_alternative", "option_index": 1}


def test_skip_reward_cards_action():
    a = actions.skip_reward_cards()
    assert a == {"action": "skip_reward_cards"}


def test_choose_treasure_relic_action():
    a = actions.choose_treasure_relic(0)
    assert a == {"action": "choose_treasure_relic", "option_index": 0}


def test_open_chest_action():
    a = actions.open_chest()
    assert a == {"action": "open_chest"}


def test_select_deck_card_action():
    a = actions.select_deck_card(0)
    assert a == {"action": "select_deck_card", "option_index": 0}


def test_confirm_selection_action():
    a = actions.confirm_selection()
    assert a == {"action": "confirm_selection"}


def test_proceed_action():
    a = actions.proceed()
    assert a == {"action": "proceed"}


# ── 4. Tool schema → to_action() → upstream format chain ────


def test_combat_tool_outputs_target_index():
    props = COMBAT_TOOL["input_schema"]["properties"]
    assert "target_index" in props
    assert "target" not in props
    assert props["target_index"]["type"] == "integer"


def test_combat_plan_tool_outputs_target_index():
    item_props = COMBAT_PLAN_TOOL["input_schema"]["properties"]["plan"]["items"]["properties"]
    assert "target_index" in item_props
    assert "target" not in item_props


def test_potion_tool_outputs_option_index():
    props = POTION_TOOL["input_schema"]["properties"]
    assert "option_index" in props
    assert "slot" not in props
    assert "target_index" in props


def test_shop_tool_uses_upstream_actions():
    schema = SHOP_PLAN_TOOL["input_schema"]
    assert schema["properties"]["purchases"]["type"] == "array"
    purchase_item_props = schema["properties"]["purchases"]["items"]["properties"]
    enums = purchase_item_props["action"]["enum"]
    assert "buy_card" in enums
    assert "buy_relic" in enums
    assert "buy_potion" in enums
    assert "remove_card" in enums
    assert "proceed" not in enums
    assert "shop_purchase" not in enums
    assert "leave_shop" not in enums
    assert "skipped_items" in schema["properties"]
    assert "reasoning" in schema["properties"]
    assert "purchases" in schema["required"]
    assert "skipped_items" in schema["required"]
    assert "reasoning" in schema["required"]


def test_card_reward_tool_uses_upstream_actions():
    enums = CARD_REWARD_TOOL["input_schema"]["properties"]["action"]["enum"]
    assert "choose_reward_card" in enums
    assert "choose_reward_alternative" in enums
    assert "skip_reward_cards" not in enums
    assert "select_card_reward" not in enums


def test_all_index_tools_use_option_index():
    # Single-choice tools use option_index
    for name, tool in [
        ("MAP", MAP_TOOL),
        ("EVENT", EVENT_TOOL),
        ("TREASURE", TREASURE_TOOL),
        ("RELIC_SELECT", RELIC_SELECT_TOOL),
    ]:
        props = tool["input_schema"]["properties"]
        assert "option_index" in props, f"{name} tool missing option_index"
        assert "index" not in props, f"{name} tool still has 'index'"

    # Multi-choice tools use selected_indices (array)
    for name, tool in [
        ("CARD_SELECT", CARD_SELECT_TOOL),
        ("HAND_SELECT", HAND_SELECT_TOOL),
    ]:
        props = tool["input_schema"]["properties"]
        assert "selected_indices" in props, f"{name} tool missing selected_indices"
        assert "index" not in props, f"{name} tool still has 'index'"


def test_hand_select_tool_supports_confirm_without_indices():
    schema = HAND_SELECT_TOOL["input_schema"]
    assert "confirm_selection" in schema["properties"]["action"]["enum"]
    assert "selected_indices" not in schema["required"]


def test_card_select_optional_tool_supports_confirm_without_indices():
    gs = SimpleNamespace(selection=SimpleNamespace(min_select=0))
    schema = get_tool_for_state("card_select", gs=gs)["input_schema"]
    assert "confirm_selection" in schema["properties"]["action"]["enum"]
    assert "selected_indices" not in schema["required"]


def test_to_action_passes_option_index():
    dec = LLMDecision(
        action_name="choose_map_node",
        params={"option_index": 2},
        reasoning="test",
    )
    action = dec.to_action()
    assert action == {"action": "choose_map_node", "option_index": 2}


def test_to_action_coerces_string_target_index():
    dec = LLMDecision(
        action_name="play_card",
        params={"card_index": 0, "target_index": "1"},
        reasoning="test",
    )
    action = dec.to_action()
    assert action["target_index"] == 1  # int, not string


# ── 5. GameState convenience properties ──────────────────────


def test_is_play_phase_with_no_playable_cards():
    """is_play_phase should be True even when no cards are playable."""
    s = _combat_state()
    s["available_actions"] = ["end_turn"]  # no play_card
    for card in s["combat"]["hand"]:
        card["playable"] = False
    gs = parse_state(s)
    assert gs.is_play_phase is True
    assert gs.can_play_card is False
    assert len(gs.playable_cards) == 0


def test_can_proceed_rest_used():
    s = _rest_state()
    for opt in s["rest"]["options"]:
        opt["is_enabled"] = False
    gs = parse_state(s)
    assert gs.can_proceed is True


def test_can_proceed_chest_claimed():
    gs = parse_state(_chest_state(opened=True, claimed=True))
    assert gs.can_proceed is True


def test_can_proceed_chest_not_opened():
    gs = parse_state(_chest_state(opened=False))
    assert gs.can_proceed is False


def test_combat_round():
    gs = parse_state(_combat_state())
    assert gs.combat_round == 2


def test_relics_available_outside_combat():
    gs = parse_state(_map_state())
    assert len(gs.relics) == 1
    assert gs.relics[0].name == "Burning Blood"


def test_potions_available_outside_combat():
    gs = parse_state(_map_state())
    occupied = [p for p in gs.potions if p.occupied]
    assert len(occupied) == 1


def test_hp_ratio():
    gs = parse_state(_combat_state())
    assert gs.hp_ratio == 60 / 80


def test_character_and_character_id():
    gs = parse_state(_combat_state())
    assert gs.character == "Ironclad"
    assert gs.character_id == "ironclad"


# ── 6. Chest open → claim → proceed lifecycle ───────────────


def test_chest_lifecycle_open():
    gs = parse_state(_chest_state(opened=False))
    assert "open_chest" in gs.available_actions
    assert not gs.chest.is_opened


def test_chest_lifecycle_claim():
    gs = parse_state(_chest_state(opened=True, claimed=False))
    assert "choose_treasure_relic" in gs.available_actions
    assert len(gs.chest.relic_options) == 1


def test_chest_lifecycle_proceed():
    gs = parse_state(_chest_state(opened=True, claimed=True))
    assert "proceed" in gs.available_actions
    assert gs.can_proceed is True


# ── 7. State type tool mapping ───────────────────────────────


def test_state_type_tool_mapping():
    assert get_tool_for_state("monster") is COMBAT_TOOL
    assert get_tool_for_state("elite") is COMBAT_TOOL
    assert get_tool_for_state("boss") is COMBAT_TOOL
    assert get_tool_for_state("map") is MAP_TOOL
    assert get_tool_for_state("event") is EVENT_TOOL
    assert get_tool_for_state("rest_site") is REST_TOOL
    assert get_tool_for_state("shop") is SHOP_PLAN_TOOL
    assert get_tool_for_state("card_reward") is CARD_REWARD_TOOL
    assert get_tool_for_state("card_select") is CARD_SELECT_TOOL
    assert get_tool_for_state("hand_select") is HAND_SELECT_TOOL
    assert get_tool_for_state("treasure") is TREASURE_TOOL


# ── Run all ──────────────────────────────────────────────────


if __name__ == "__main__":
    import sys

    passed = 0
    failed = 0
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for test_fn in tests:
        try:
            test_fn()
            passed += 1
        except Exception as exc:
            failed += 1
            print(f"FAIL: {test_fn.__name__}: {exc}")
    total = passed + failed
    print(f"\n{passed}/{total} passed, {failed} failed")
    sys.exit(1 if failed else 0)
