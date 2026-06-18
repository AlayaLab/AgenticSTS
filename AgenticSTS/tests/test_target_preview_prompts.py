from __future__ import annotations

from src.brain.conversation import (
    CombatConversation,
    _effective_hits,
    _format_card_values,
    _parse_hits_from_rules,
)
from src.brain.prompts.potion import build_potion_prompt
from src.mcp_client.upstream_models import RawCombatHandCardPayload, TargetPreview
from src.state.state_parser import parse_state


def _base_run(*, potions: list[dict]) -> dict:
    return {
        "character_id": "ironclad",
        "character_name": "Ironclad",
        "floor": 6,
        "current_hp": 60,
        "max_hp": 80,
        "gold": 120,
        "max_energy": 3,
        "base_orb_slots": 0,
        "deck": [],
        "relics": [],
        "players": [],
        "potions": potions,
    }


def _combat_state() -> dict:
    return {
        "state_version": 6,
        "run_id": "run_target_preview",
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
            "players": [
                {
                    "player_id": "local",
                    "slot_index": 0,
                    "is_local": True,
                    "is_connected": True,
                    "character_id": "ironclad",
                    "character_name": "Ironclad",
                    "current_hp": 60,
                    "max_hp": 80,
                    "block": 0,
                    "energy": 3,
                    "stars": 0,
                    "focus": 0,
                    "is_alive": True,
                }
            ],
            "hand": [
                {
                    "index": 0,
                    "card_id": "strike",
                    "name": "Strike",
                    "upgraded": False,
                    "target_type": "AnyEnemy",
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
                    "target_previews": [{"target_index": 0, "damage": 9}],
                },
                {
                    "index": 1,
                    "card_id": "body_slam",
                    "name": "Body Slam",
                    "upgraded": False,
                    "target_type": "AnyEnemy",
                    "requires_target": True,
                    "target_index_space": "enemies",
                    "valid_target_indices": [0, 1],
                    "costs_x": False,
                    "star_costs_x": False,
                    "energy_cost": 1,
                    "star_cost": 0,
                    "rules_text": "Deal damage equal to your Block.",
                    "playable": True,
                    "unplayable_reason": None,
                    "target_previews": [{"target_index": 0, "damage": 18}],
                },
            ],
            "enemies": [
                {
                    "index": 0,
                    "enemy_id": "cultist",
                    "name": "Cultist",
                    "current_hp": 20,
                    "max_hp": 50,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [
                        {
                            "index": 0,
                            "power_id": "vulnerable",
                            "name": "Vulnerable",
                            "amount": 1,
                            "is_debuff": True,
                        }
                    ],
                    "intent": "attack",
                    "move_id": "incantation",
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
                    "enemy_id": "jaw_worm",
                    "name": "Jaw Worm",
                    "current_hp": 40,
                    "max_hp": 40,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [],
                    "intent": "attack",
                    "move_id": "chomp",
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
        "run": _base_run(
            potions=[
                {
                    "index": 0,
                    "potion_id": "blessing",
                    "name": "Blessing Potion",
                    "description": "Grant 8 Block to a player.",
                    "rarity": "Common",
                    "occupied": True,
                    "usage": "Combat",
                    "target_type": "AnyPlayer",
                    "is_queued": False,
                    "requires_target": True,
                    "target_index_space": "players",
                    "valid_target_indices": [0],
                    "can_use": True,
                    "can_discard": True,
                }
            ]
        ),
    }


def test_parse_state_preserves_target_preview_damage_payload():
    gs = parse_state(_combat_state())

    assert gs.hand[0].target_previews is not None
    assert gs.hand[0].target_previews[0].target_index == 0
    assert gs.hand[0].target_previews[0].damage == 9

    assert gs.hand[1].target_previews is not None
    assert gs.hand[1].target_previews[0].damage == 18


def _get_conversation_round_text(gs) -> str:
    """Build a CombatConversation, add round state, return the user message text."""
    conv = CombatConversation(system_prompt="test")
    conv.add_round_state(gs)
    # The round state is the last user message
    for msg in reversed(conv.messages):
        if msg["role"] == "user":
            if isinstance(msg["content"], str):
                return msg["content"]
            return " ".join(b.get("text", "") for b in msg["content"] if b.get("type") == "text")
    return ""


def test_conversation_round_state_renders_target_previews_and_potion_scope():
    gs = parse_state(_combat_state())
    prompt = _get_conversation_round_text(gs)

    assert "vs Cultist[0]: 9 dmg" in prompt
    assert "vs Cultist[0]: 18 dmg" in prompt
    assert "Blessing Potion" in prompt


def test_build_potion_prompt_renders_player_target_label():
    prompt = build_potion_prompt(parse_state(_combat_state()))

    assert "Blessing Potion (targets: players)" in prompt


# ---- Phase 10: Structured card preview tests ----


def _structured_combat_state() -> dict:
    """Combat state with full structured fields: damage, block, hits, total_damage."""
    return {
        "state_version": 6,
        "run_id": "run_structured_preview",
        "screen": "COMBAT",
        "session": {"mode": "singleplayer", "phase": "run", "control_scope": "local_player"},
        "in_combat": True,
        "turn": 1,
        "available_actions": ["play_card", "end_turn"],
        "combat": {
            "player": {
                "current_hp": 50,
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
                    "card_id": "strike_plus",
                    "name": "Strike",
                    "upgraded": True,
                    "target_type": "AnyEnemy",
                    "requires_target": True,
                    "target_index_space": "enemies",
                    "valid_target_indices": [0],
                    "energy_cost": 1,
                    "rules_text": "造成9点伤害。",
                    "playable": True,
                    "damage": 9,
                    "block": None,
                    "hits": 1,
                    "total_damage": 9,
                    "target_previews": [
                        {"target_index": 0, "damage": 13, "hits": 1, "total_damage": 13},
                    ],
                },
                {
                    "index": 1,
                    "card_id": "defend",
                    "name": "Defend",
                    "upgraded": False,
                    "target_type": "Self",
                    "requires_target": False,
                    "energy_cost": 1,
                    "rules_text": "获得5点格挡。",
                    "playable": True,
                    "damage": None,
                    "block": 5,
                    "hits": None,
                    "total_damage": None,
                },
                {
                    "index": 2,
                    "card_id": "sword_boomerang",
                    "name": "Sword Boomerang",
                    "upgraded": False,
                    "target_type": "RandomEnemy",
                    "requires_target": False,
                    "energy_cost": 1,
                    "rules_text": "Deal 3 damage to a random enemy 3 times.",
                    "playable": True,
                    "damage": 3,
                    "block": None,
                    "hits": 1,  # hits=1 from old C# mod (Repeat excluded); rules_text fallback corrects this
                    "total_damage": 3,
                },
                {
                    "index": 3,
                    "card_id": "bash",
                    "name": "Bash",
                    "upgraded": False,
                    "target_type": "AnyEnemy",
                    "requires_target": True,
                    "target_index_space": "enemies",
                    "valid_target_indices": [0],
                    "energy_cost": 2,
                    "rules_text": "造成8点伤害。施加2层易伤。",
                    "playable": True,
                    "damage": 8,
                    "block": None,
                    "hits": 1,
                    "total_damage": 8,
                    "target_previews": [
                        {"target_index": 0, "damage": 12, "hits": 1, "total_damage": 12},
                    ],
                },
                {
                    "index": 4,
                    "card_id": "iron_wave",
                    "name": "Iron Wave",
                    "upgraded": False,
                    "target_type": "AnyEnemy",
                    "requires_target": True,
                    "target_index_space": "enemies",
                    "valid_target_indices": [0],
                    "energy_cost": 1,
                    "rules_text": "获得5点格挡。造成5点伤害。",
                    "playable": True,
                    "damage": 5,
                    "block": 5,
                    "hits": 1,
                    "total_damage": 5,
                },
            ],
            "enemies": [
                {
                    "index": 0,
                    "enemy_id": "cultist",
                    "name": "Cultist",
                    "current_hp": 15,
                    "max_hp": 50,
                    "block": 0,
                    "is_alive": True,
                    "is_hittable": True,
                    "powers": [
                        {"index": 0, "power_id": "vulnerable", "name": "Vulnerable",
                         "amount": 2, "is_debuff": True},
                    ],
                    "intent": "attack",
                    "move_id": "slash",
                    "intents": [
                        {"index": 0, "intent_type": "Attack", "damage": 10,
                         "hits": 1, "total_damage": 10},
                    ],
                },
            ],
        },
        "run": _base_run(potions=[]),
    }


def test_model_parses_card_level_structured_fields():
    """Card-level damage/block/hits/total_damage are parsed correctly."""
    gs = parse_state(_structured_combat_state())
    hand = gs.hand

    # Strike+: attack with damage
    assert hand[0].damage == 9
    assert hand[0].block is None
    assert hand[0].hits == 1
    assert hand[0].total_damage == 9

    # Defend: block only
    assert hand[1].damage is None
    assert hand[1].block == 5
    assert hand[1].hits is None
    assert hand[1].total_damage is None

    # Sword Boomerang: hits=1 (Repeat excluded, multi-hit in rules_text only)
    assert hand[2].damage == 3
    assert hand[2].hits == 1
    assert hand[2].total_damage == 3

    # Iron Wave: both damage and block
    assert hand[4].damage == 5
    assert hand[4].block == 5


def test_model_parses_enhanced_target_preview():
    """Target previews include hits and total_damage."""
    gs = parse_state(_structured_combat_state())

    tp = gs.hand[0].target_previews[0]
    assert tp.damage == 13
    assert tp.hits == 1
    assert tp.total_damage == 13


def test_format_card_values_attack():
    """Single-hit attack: '[9 dmg]'."""
    card = RawCombatHandCardPayload(damage=9, hits=1, total_damage=9)
    assert _format_card_values(card) == " [9 dmg]"


def test_format_card_values_multi_hit():
    """Multi-hit attack: '[3 dmg x3 = 9 total]'."""
    card = RawCombatHandCardPayload(damage=3, hits=3, total_damage=9)
    assert _format_card_values(card) == " [3 dmg x3 = 9 total]"


def test_format_card_values_block():
    """Block card: '[5 block]'."""
    card = RawCombatHandCardPayload(block=5)
    assert _format_card_values(card) == " [5 block]"


def test_format_card_values_hybrid():
    """Hybrid card (both damage and block): '[4 dmg, 3 block]'."""
    card = RawCombatHandCardPayload(damage=4, hits=1, total_damage=4, block=3)
    assert _format_card_values(card) == " [4 dmg, 3 block]"


def test_format_card_values_no_values():
    """Card with no structured values: empty string."""
    card = RawCombatHandCardPayload()
    assert _format_card_values(card) == ""


def test_conversation_round_state_shows_structured_values_inline():
    """Conversation round state displays structured values inline."""
    gs = parse_state(_structured_combat_state())
    prompt = _get_conversation_round_text(gs)

    assert "[9 dmg]" in prompt
    assert "[5 block]" in prompt
    assert "[5 dmg, 5 block]" in prompt


def test_backward_compat_old_target_preview_schema():
    """Old target_preview payloads (damage only) still work."""
    tp = TargetPreview(target_index=0, damage=9)
    assert tp.hits == 1
    assert tp.total_damage == 0  # default, not computed


# ---- rules_text multi-hit fallback tests ----


def test_parse_hits_from_rules_twice():
    """'twice' in rules_text → 2 hits."""
    assert _parse_hits_from_rules("Deal 4 damage to ALL enemies twice.") == 2


def test_parse_hits_from_rules_n_times():
    """'N times' in rules_text → N hits."""
    assert _parse_hits_from_rules("Deal 3 damage to a random enemy 3 times.") == 3
    assert _parse_hits_from_rules("Deal 5 damage 4 times.") == 4


def test_parse_hits_from_rules_chinese():
    """Chinese multi-hit patterns work."""
    assert _parse_hits_from_rules("对所有敌人造成4点伤害两次。") == 2
    assert _parse_hits_from_rules("造成3点伤害3次。") == 3


def test_parse_hits_from_rules_no_match():
    """Single-hit cards return None."""
    assert _parse_hits_from_rules("Deal 6 damage.") is None
    assert _parse_hits_from_rules("Gain 5 Block.") is None


def test_effective_hits_uses_rules_fallback():
    """When hits=1 and rules_text says 'twice', _effective_hits returns 2."""
    card = RawCombatHandCardPayload(
        damage=4, hits=1, total_damage=4,
        rules_text="Deal 4 damage to ALL enemies twice.",
    )
    assert _effective_hits(card) == 2


def test_effective_hits_respects_dynamic_var():
    """When hits>1 from DynamicVars, rules_text is not consulted."""
    card = RawCombatHandCardPayload(
        damage=3, hits=3, total_damage=9,
        rules_text="Deal 3 damage 3 times.",
    )
    assert _effective_hits(card) == 3


def test_format_card_values_dagger_spray_rules_fallback():
    """Dagger Spray: hits=1 from mod, but rules_text says 'twice' → [4 dmg x2 = 8 total]."""
    card = RawCombatHandCardPayload(
        damage=4, hits=1, total_damage=4,
        rules_text="Deal 4 damage to ALL enemies twice.",
    )
    assert _format_card_values(card) == " [4 dmg x2 = 8 total]"


def test_format_card_values_repeat_from_mod():
    """When C# mod correctly reports hits (e.g. Repeat fallback), display is correct."""
    card = RawCombatHandCardPayload(
        damage=6, hits=3, total_damage=18,
        rules_text="Deal 6 damage 3 times.",
    )
    assert _format_card_values(card) == " [6 dmg x3 = 18 total]"


def test_format_card_values_replay():
    """Card with Replay shows [Replay xN] tag."""
    card = RawCombatHandCardPayload(
        damage=8, hits=1, total_damage=8, replay=1,
        rules_text="Deal 8 damage.",
    )
    assert "[Replay x1]" in _format_card_values(card)
    assert "[8 dmg]" in _format_card_values(card)


def test_format_card_values_no_replay():
    """Card without Replay has no replay tag."""
    card = RawCombatHandCardPayload(damage=6, hits=1, total_damage=6)
    result = _format_card_values(card)
    assert "Replay" not in result


def test_conversation_shows_multi_hit_from_rules_fallback():
    """Conversation round state uses rules_text fallback for multi-hit display."""
    gs = parse_state(_structured_combat_state())
    prompt = _get_conversation_round_text(gs)

    # Sword Boomerang has hits=1 but rules_text says "3 times" → should show x3
    assert "3 dmg x3 = 9 total" in prompt


def test_replay_field_parsed():
    """Replay field is parsed from payload."""
    card = RawCombatHandCardPayload(damage=5, hits=1, total_damage=5, replay=1)
    assert card.replay == 1

    card_no_replay = RawCombatHandCardPayload(damage=5, hits=1, total_damage=5)
    assert card_no_replay.replay is None


def test_backward_compat_old_card_schema():
    """Old card payloads (no structured fields) still work."""
    card = RawCombatHandCardPayload(
        index=0, name="Strike", rules_text="Deal 6 damage.", playable=True,
        energy_cost=1,
    )
    assert card.damage is None
    assert card.block is None
    assert card.hits is None
    assert card.total_damage is None
    # _format_card_values returns empty for cards without structured fields
    assert _format_card_values(card) == ""
