from src.state.state_parser import (
    StateParseError,
    parse_state,
    parse_upstream_game_state,
    parse_upstream_state_payload,
    unwrap_state_payload,
)


def _sample_upstream_state() -> dict:
    return {
        "state_version": 2,
        "run_id": "seed_123",
        "screen": "COMBAT",
        "session": {
            "mode": "singleplayer",
            "phase": "run",
            "control_scope": "local_player",
        },
        "in_combat": True,
        "turn": 3,
        "available_actions": ["play_card", "use_potion", "end_turn"],
        "combat": {
            "player": {
                "current_hp": 51,
                "max_hp": 72,
                "block": 8,
                "energy": 3,
                "stars": 1,
                "focus": 2,
                "base_orb_slots": 3,
                "orb_capacity": 4,
                "empty_orb_slots": 1,
                "powers": [
                    {
                        "index": 0,
                        "power_id": "artifact",
                        "name": "Artifact",
                        "amount": 1,
                        "description": "Negates 1 debuff application.",
                        "is_debuff": False,
                    }
                ],
                "orbs": [
                    {
                        "slot_index": 0,
                        "orb_id": "lightning",
                        "name": "Lightning",
                        "passive_value": 3,
                        "evoke_value": 8,
                        "is_front": True,
                    }
                ],
            },
            "players": [
                {
                    "player_id": "local",
                    "slot_index": 0,
                    "is_local": True,
                    "is_connected": True,
                    "character_id": "defect",
                    "character_name": "Defect",
                    "current_hp": 51,
                    "max_hp": 72,
                    "block": 8,
                    "energy": 3,
                    "stars": 1,
                    "focus": 2,
                    "is_alive": True,
                }
            ],
            "hand": [
                {
                    "index": 0,
                    "card_id": "doom_and_gloom",
                    "name": "Doom and Gloom",
                    "upgraded": False,
                    "card_type": "Attack",
                    "target_type": "Enemy",
                    "requires_target": True,
                    "target_index_space": "enemy",
                    "valid_target_indices": [0, 1],
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 2,
                    "star_cost": 0,
                    "rules_text": "Deal damage. Channel Dark.",
                    "playable": True,
                    "unplayable_reason": None,
                },
                {
                    "index": 1,
                    "card_id": "meteor_strike",
                    "name": "Meteor Strike",
                    "upgraded": False,
                    "card_type": "Attack",
                    "target_type": "Enemy",
                    "requires_target": True,
                    "target_index_space": "enemy",
                    "valid_target_indices": [0, 1],
                    "costs_x": False,
                    "star_costs_x": True,
                    "energy_cost": 5,
                    "star_cost": 0,
                    "rules_text": "Big hit.",
                    "playable": False,
                    "unplayable_reason": "Not enough energy",
                },
            ],
            "enemies": [
                {
                    "index": 0,
                    "enemy_id": "slaver_red",
                    "name": "Red Slaver",
                    "current_hp": 36,
                    "max_hp": 50,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [],
                    "intent": "attack",
                    "move_id": "stab",
                    "intents": [
                        {
                            "index": 0,
                            "intent_type": "attack",
                            "label": "9",
                            "damage": 9,
                            "hits": 1,
                            "total_damage": 9,
                            "status_card_count": None,
                        }
                    ],
                }
            ],
        },
        "run": {
            "character_id": "defect",
            "character_name": "Defect",
            "floor": 14,
            "current_hp": 51,
            "max_hp": 72,
            "gold": 148,
            "max_energy": 3,
            "base_orb_slots": 3,
            "deck": [
                {
                    "index": 0,
                    "card_id": "zap",
                    "name": "Zap",
                    "upgraded": True,
                    "card_type": "Skill",
                    "rarity": "Starter",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 0,
                    "star_cost": 0,
                    "rules_text": "Channel 1 Lightning.",
                }
            ],
            "relics": [
                {
                    "index": 0,
                    "relic_id": "cracked_core",
                    "name": "Cracked Core",
                    "description": "At the start of each combat, channel 1 Lightning.",
                    "stack": None,
                    "is_melted": False,
                }
            ],
            "players": [
                {
                    "player_id": "local",
                    "slot_index": 0,
                    "is_local": True,
                    "is_connected": True,
                    "character_id": "defect",
                    "character_name": "Defect",
                    "current_hp": 51,
                    "max_hp": 72,
                    "gold": 148,
                    "is_alive": True,
                }
            ],
            "potions": [
                {
                    "index": 0,
                    "potion_id": "fire_potion",
                    "name": "Fire Potion",
                    "description": "Deal 20 damage.",
                    "rarity": "Common",
                    "occupied": True,
                    "usage": "Deal 20 damage.",
                    "target_type": "Enemy",
                    "is_queued": False,
                    "requires_target": True,
                    "target_index_space": "enemy",
                    "valid_target_indices": [0, 1],
                    "can_use": True,
                    "can_discard": True,
                }
            ],
        },
        "multiplayer": {
            "is_multiplayer": False,
            "net_game_type": "",
            "local_player_id": None,
            "player_count": 1,
            "connected_player_ids": [],
        },
        "multiplayer_lobby": {
            "net_game_type": "",
            "join_host": "127.0.0.1",
            "join_port": 0,
            "local_net_id_hint": None,
            "has_lobby": False,
            "is_host": False,
            "is_client": False,
            "local_ready": False,
            "can_host": False,
            "can_join": False,
            "can_ready": False,
            "can_disconnect": False,
            "can_unready": False,
            "selected_character_id": None,
            "player_count": 0,
            "max_players": 0,
            "players": [],
            "characters": [],
        },
        "selection": {
            "kind": "deck",
            "prompt": "Choose a card to upgrade",
            "min_select": 1,
            "max_select": 1,
            "selected_count": 0,
            "requires_confirmation": True,
            "can_confirm": False,
            "cards": [
                {
                    "index": 0,
                    "card_id": "zap",
                    "name": "Zap",
                    "upgraded": False,
                    "card_type": "Skill",
                    "rarity": "Starter",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Channel 1 Lightning.",
                }
            ],
        },
        "event": {
            "event_id": "golden_idol",
            "title": "Golden Idol",
            "description": "Take the idol or leave.",
            "is_finished": False,
            "options": [
                {
                    "index": 0,
                    "text_key": "take",
                    "title": "Take",
                    "description": "Become injured.",
                    "is_locked": False,
                    "is_proceed": False,
                    "will_kill_player": False,
                    "has_relic_preview": False,
                }
            ],
        },
        "shop": {
            "is_open": True,
            "can_open": False,
            "can_close": True,
            "cards": [
                {
                    "index": 0,
                    "category": "card",
                    "card_id": "sunder",
                    "name": "Sunder",
                    "upgraded": False,
                    "card_type": "Attack",
                    "rarity": "Uncommon",
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 3,
                    "star_cost": 0,
                    "rules_text": "Deal 24 damage.",
                    "price": 78,
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
                    "enough_gold": True,
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
            "card_removal": {
                "price": 75,
                "available": True,
                "used": False,
                "enough_gold": True,
            },
        },
        "reward": {
            "pending_card_choice": True,
            "can_proceed": False,
            "rewards": [
                {
                    "index": 0,
                    "reward_type": "gold",
                    "description": "Gain 25 gold",
                    "claimable": True,
                }
            ],
            "card_options": [
                {
                    "index": 0,
                    "card_id": "echo_form",
                    "name": "Echo Form",
                    "upgraded": False,
                    "rules_text": "The first card played each turn is played twice.",
                }
            ],
            "alternatives": [
                {
                    "index": 0,
                    "label": "Skip",
                }
            ],
        },
        "agent_view": {
            "version": 1,
            "screen": "COMBAT",
            "run_id": "seed_123",
            "session": {
                "mode": "singleplayer",
                "phase": "run",
                "control_scope": "local_player",
            },
            "turn": 3,
            "actions": ["play_card", "use_potion", "end_turn"],
            "available_actions": ["play_card", "use_potion", "end_turn"],
            "combat": {
                "player": {
                    "hp": "51/72",
                    "block": 8,
                    "energy": 3,
                    "stars": 1,
                    "focus": 2,
                    "orbs": ["Lightning 被动3/激发8"],
                },
                "hand": [
                    {
                        "i": 0,
                        "line": "Doom and Gloom [2费]：Deal damage. Channel Dark.",
                        "type": "Attack",
                        "playable": True,
                        "target": "enemy",
                        "targets": [0, 1],
                        "why": None,
                        "keywords": ["channel"],
                        "mods": [],
                    }
                ],
                "draw": [],
                "discard": [],
                "exhaust": [],
                "enemies": [
                    {
                        "i": 0,
                        "name": "Red Slaver",
                        "hp": "36/50",
                        "block": 0,
                        "intent": "attack",
                        "alive": True,
                        "hittable": True,
                    }
                ],
            },
            "run": {
                "character": "Defect",
                "floor": 14,
                "hp": "51/72",
                "gold": 148,
                "max_energy": 3,
                "base_orb_slots": 3,
                "deck": [
                    {
                        "line": "Zap+ [0费]：Channel 1 Lightning.",
                        "keywords": ["channel"],
                        "mods": [],
                    }
                ],
                "relics": ["Cracked Core"],
                "potions": [
                    {
                        "i": 0,
                        "line": "0: Fire Potion：Deal 20 damage.",
                        "usable": True,
                        "discard": True,
                        "target": "enemy",
                        "targets": [0, 1],
                    }
                ],
                "piles": {
                    "draw": [],
                    "discard": [],
                    "exhaust": [],
                },
            },
            "selection": {
                "kind": "deck",
                "prompt": "Choose a card to upgrade",
                "min": 1,
                "max": 1,
                "selected": 0,
                "confirm": False,
                "cards": [
                    {
                        "i": 0,
                        "line": "Zap [1费]：Channel 1 Lightning.",
                        "keywords": ["channel"],
                        "mods": [],
                    }
                ],
            },
            "shop": {
                "open": True,
                "can_open": False,
                "can_close": True,
                "cards": [
                    {
                        "i": 0,
                        "line": "Sunder [3费]：Deal 24 damage. | 78g",
                        "affordable": True,
                        "keywords": ["damage"],
                        "mods": [],
                    }
                ],
                "relics": [],
                "potions": [],
                "remove": {
                    "price": 75,
                    "affordable": True,
                    "available": True,
                    "used": False,
                },
            },
            "reward": {
                "pending_card_choice": True,
                "can_proceed": False,
                "rewards": [
                    {
                        "i": 0,
                        "line": "gold: Gain 25 gold",
                        "claimable": True,
                    }
                ],
                "cards": [
                    {
                        "i": 0,
                        "line": "Echo Form：The first card played each turn is played twice.",
                        "keywords": [],
                        "mods": [],
                    }
                ],
                "alternatives": [
                    {
                        "i": 0,
                        "line": "Skip",
                    }
                ],
            },
            "glossary": {
                "Channel": "Create an orb.",
                "Dark": "Increases each turn.",
            },
        },
    }


def test_parse_upstream_state_payload_preserves_raw_and_agent_view_fields():
    payload = parse_upstream_state_payload(_sample_upstream_state())

    assert payload.screen == "COMBAT"
    assert payload.combat is not None
    assert payload.combat.player.focus == 2
    assert payload.combat.player.orbs[0].is_front is True
    assert payload.combat.player.powers[0].description == "Negates 1 debuff application."
    assert payload.combat.hand[0].card_type == "Attack"
    assert payload.combat.hand[1].star_costs_x is True
    assert payload.combat.hand[0].valid_target_indices == [0, 1]
    assert payload.run is not None
    assert payload.run.character_name == "Defect"
    assert payload.run.base_orb_slots == 3
    assert payload.run.players[0].character_name == "Defect"
    assert payload.run.potions[0].target_index_space == "enemy"
    assert payload.selection is not None
    assert payload.selection.requires_confirmation is True
    assert payload.event is not None
    assert payload.event.options[0].will_kill_player is False
    assert payload.shop is not None
    assert payload.shop.can_close is True
    assert payload.shop.card_removal is not None
    assert payload.shop.card_removal.available is True
    assert payload.shop.relics[0].description == "Start each combat with 1 Strength."
    assert payload.shop.potions[0].description == "Deal 20 damage."
    assert payload.agent_view is not None
    assert payload.agent_view.glossary["Channel"] == "Create an orb."
    assert payload.agent_view.combat is not None
    assert payload.agent_view.combat.hand[0].type == "Attack"
    assert payload.agent_view.combat.hand[0].targets == [0, 1]
    assert payload.agent_view.run is not None
    assert payload.agent_view.run.potions[0].targets == [0, 1]


def test_parse_upstream_state_payload_unwraps_envelope():
    payload = parse_upstream_state_payload({"ok": True, "data": _sample_upstream_state()})

    assert payload.run_id == "seed_123"
    assert payload.available_actions == ["play_card", "use_potion", "end_turn"]


def test_parse_upstream_game_state_exposes_convenience_helpers():
    gs = parse_upstream_game_state(_sample_upstream_state())

    assert gs.state_type == "monster"
    assert gs.is_combat is True
    assert gs.is_in_run is True
    assert gs.energy == 3
    assert gs.player_hp == 51
    assert gs.gold == 148
    assert len(gs.playable_cards) == 1
    assert gs.enemies[0].name == "Red Slaver"
    assert gs.next_map_options == []
    assert gs.agent_view is not None
    assert "monster" in gs.summary()


def test_parse_state_exposes_migrated_block_and_max_energy_shims():
    gs = parse_state(_sample_upstream_state())

    assert gs.block == 8
    assert gs.max_energy == 3


def test_parse_upstream_game_state_marks_boss_floor_without_map_metadata():
    raw = _sample_upstream_state()
    raw["run"]["floor"] = 51
    raw["map"] = None

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "boss"


def test_parse_upstream_state_payload_preserves_mod_encounter_metadata():
    raw = _sample_upstream_state()
    raw["run"]["floor"] = 51
    raw["combat_type"] = "boss"
    raw["boss_stage"] = "final_boss"
    raw["is_final_boss"] = True
    raw["act"] = 3
    raw["agent_view"]["combat_type"] = "boss"
    raw["agent_view"]["boss_stage"] = "final_boss"
    raw["agent_view"]["is_final_boss"] = True
    raw["agent_view"]["act"] = 3

    payload = parse_upstream_state_payload(raw)

    assert payload.combat_type == "boss"
    assert payload.boss_stage == "final_boss"
    assert payload.is_final_boss is True
    assert payload.act == 3
    assert payload.agent_view is not None
    assert payload.agent_view.combat_type == "boss"
    assert payload.agent_view.boss_stage == "final_boss"
    assert payload.agent_view.is_final_boss is True
    assert payload.agent_view.act == 3


def test_parse_upstream_game_state_prefers_mod_combat_type_over_floor_fallback():
    raw = _sample_upstream_state()
    raw["run"]["floor"] = 17
    raw["map"] = None
    raw["combat_type"] = "elite"

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "elite"


def test_parse_upstream_game_state_uses_act_for_boss_stage_when_floor_is_not_legacy_boss_floor():
    raw = _sample_upstream_state()
    raw["screen"] = "CARD_SELECTION"
    raw["reward"] = None
    raw["run"]["floor"] = 48
    raw["combat_type"] = "boss"
    raw["act"] = 3
    raw["selection"]["kind"] = "combat_hand_select"

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "hand_select"
    assert gs.combat_type == "boss"
    assert gs.act == 3
    assert gs.boss_stage == "final_boss"
    assert gs.is_final_boss is True


def test_parse_upstream_game_state_prefers_reward_actions_over_shop_screen():
    raw = _sample_upstream_state()
    raw["screen"] = "SHOP"
    raw["available_actions"] = ["buy_relic", "choose_reward_card", "skip_reward_cards"]

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "card_reward"


def test_parse_upstream_game_state_prefers_reward_alternative_action_over_shop_screen():
    raw = _sample_upstream_state()
    raw["screen"] = "SHOP"
    raw["available_actions"] = ["buy_relic", "choose_reward_alternative"]

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "card_reward"


def test_parse_upstream_game_state_prefers_claimable_rewards_over_shop_screen():
    raw = _sample_upstream_state()
    raw["screen"] = "SHOP"
    raw["reward"]["pending_card_choice"] = False
    raw["available_actions"] = ["buy_relic", "claim_reward", "collect_rewards_and_proceed"]

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "combat_rewards"


def test_parse_upstream_game_state_prefers_selection_actions_over_shop_screen():
    raw = _sample_upstream_state()
    raw["screen"] = "SHOP"
    raw["available_actions"] = ["buy_relic", "select_deck_card", "confirm_selection"]
    raw["selection"]["kind"] = "deck_card_select"
    raw["selection"]["prompt"] = "Choose a card to duplicate."

    gs = parse_upstream_game_state(raw)

    assert gs.state_type == "card_select"
    assert gs.selection is not None
    assert gs.selection.prompt == "Choose a card to duplicate."


def test_parse_upstream_state_payload_rejects_invalid_payload():
    bad_payload = {"ok": True, "data": {"screen": "COMBAT", "state_version": "bad"}}
    try:
        parse_upstream_state_payload(bad_payload)
    except StateParseError:
        pass  # Expected
    else:
        raise AssertionError("Expected StateParseError for invalid payload")


def test_unwrap_state_payload_rejects_non_dict():
    try:
        unwrap_state_payload([])
    except StateParseError as exc:
        assert "must be a dict" in str(exc)
    else:
        raise AssertionError("Expected StateParseError for non-dict payload")


def test_parse_upstream_state_payload_shop_descriptions_are_backward_compatible():
    raw = _sample_upstream_state()
    assert raw["shop"]["relics"][0]["description"] == "Start each combat with 1 Strength."
    assert raw["shop"]["potions"][0]["description"] == "Deal 20 damage."

    del raw["shop"]["relics"][0]["description"]
    del raw["shop"]["potions"][0]["description"]

    payload = parse_upstream_state_payload(raw)

    assert payload.shop is not None
    assert payload.shop.relics[0].description is None
    assert payload.shop.potions[0].description is None


def test_event_option_extended_fields():
    """Extended event option payload includes card/relic/potion data."""
    from src.mcp_client.upstream_models import RawEventOptionPayload

    payload = RawEventOptionPayload(
        index=2,
        title="Archaic Tooth",
        description="Transform Neutralize+ into Suppress+.",
        effect_description="Transform Neutralize+ into Suppress+.",
        hp_cost=None,
        gold_cost=None,
        cards_offered=[{
            "name": "Suppress+",
            "cost": 1,
            "type": "Skill",
            "rules_text": "Apply 3 Weak. Draw 1 card.",
            "is_upgraded": True,
        }],
        relics_offered=[],
        potions_offered=[],
        curses_risk=[],
    )
    assert payload.index == 2
    assert len(payload.cards_offered) == 1
    assert payload.cards_offered[0]["name"] == "Suppress+"
    assert payload.hp_cost is None


def test_event_option_backward_compatible():
    """Old payloads without new fields still parse."""
    from src.mcp_client.upstream_models import RawEventOptionPayload

    payload = RawEventOptionPayload(index=0, title="Test")
    assert payload.cards_offered == []
    assert payload.hp_cost is None
    assert payload.effect_description == ""
