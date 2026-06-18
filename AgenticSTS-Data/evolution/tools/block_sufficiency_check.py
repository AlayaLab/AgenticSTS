
"""
Checks if available block cards can prevent HP loss this turn.
Estimates max achievable block, calculates net damage, flags lethal risk.
Also detects effectively unkillable enemies (HP > 1M) and redirects to setup mode.
"""

SCHEMA = {
    "name": "block_sufficiency_check",
    "description": "Checks if available block cards can prevent HP loss this turn. Estimates max achievable block from block cards + dexterity, calculates net damage, and flags lethal risk.",
    "parameters": {
        "current_hp": {"type": "integer", "description": "Player current HP", "required": True},
        "current_block": {"type": "integer", "description": "Player current block", "required": True},
        "incoming_damage": {"type": "integer", "description": "Total incoming damage this turn", "required": True},
        "energy": {"type": "integer", "description": "Energy available", "required": True},
        "dexterity": {"type": "integer", "description": "Player dexterity", "required": True},
        "block_cards_in_hand": {"type": "integer", "description": "Number of block cards in hand", "required": True},
        "max_hp": {"type": "integer", "description": "Player max HP"},
        "enemy_hp": {"type": "integer", "description": "Current HP of primary enemy (0 if unknown)"}
    },
    "required": ["current_hp", "current_block", "incoming_damage", "energy", "dexterity", "block_cards_in_hand"]
}

_UNKILLABLE_HP_THRESHOLD = 1_000_000

APPLICABLE_STATES = ["monster", "elite", "boss"]

def _to_int(val):
    """Safely convert a value to int, summing if it's a list."""
    if isinstance(val, list):
        return sum(int(v) if not isinstance(v, dict) else 0 for v in val)
    return int(val) if val is not None else 0

def execute(current_hp, current_block, incoming_damage, energy, dexterity, block_cards_in_hand, max_hp=80, enemy_hp=0):
    current_hp = _to_int(current_hp)
    current_block = _to_int(current_block)
    incoming_damage = _to_int(incoming_damage)
    energy = _to_int(energy)
    dexterity = _to_int(dexterity)
    block_cards_in_hand = _to_int(block_cards_in_hand)
    max_hp = _to_int(max_hp) if max_hp else 80
    enemy_hp = _to_int(enemy_hp) if enemy_hp else 0

    if enemy_hp > _UNKILLABLE_HP_THRESHOLD:
        return {
            "unkillable_enemy": True,
            "enemy_hp": enemy_hp,
            "recommendation": (
                "SETUP PHASE: Enemy HP is effectively infinite — damage is futile. "
                "DO NOT exhaust cards trying to deal damage. "
                "Play Powers and self-buffs. "
                "Save your resources for the actual fight phase."
            ),
        }

    base_block_per_card = max(0, 5 + dexterity)
    playable_block_cards = min(block_cards_in_hand, energy)
    max_new_block = playable_block_cards * base_block_per_card
    total_block = current_block + max_new_block
    net_damage = max(0, incoming_damage - total_block)
    hp_after = current_hp - net_damage

    damage_needing_block = max(0, incoming_damage - current_block)
    if base_block_per_card > 0:
        cards_for_full_block = -(-damage_needing_block // base_block_per_card)
    else:
        cards_for_full_block = 999 if damage_needing_block > 0 else 0

    block_cards_used = min(cards_for_full_block, block_cards_in_hand)
    energy_for_offense = max(0, energy - block_cards_used)
    can_fully_block = cards_for_full_block <= playable_block_cards
    is_lethal = hp_after <= 0
    hp_percent = round(current_hp / max_hp * 100) if max_hp > 0 else 0

    result = {
        "block_per_card_estimate": base_block_per_card,
        "playable_block_cards": playable_block_cards,
        "max_achievable_block": total_block,
        "can_fully_block": can_fully_block,
        "net_damage_if_max_block": net_damage,
        "hp_after_turn": hp_after,
        "is_lethal": is_lethal,
        "cards_needed_to_fully_block": min(cards_for_full_block, 99),
        "energy_for_offense_after_full_block": energy_for_offense,
        "hp_percent": hp_percent,
    }

    if incoming_damage == 0:
        result["recommendation"] = "No incoming damage. Spend all energy on offense."
    elif is_lethal:
        result["recommendation"] = "LETHAL DANGER: Play ALL block cards. Use every resource to survive."
    elif not can_fully_block and current_hp <= 20:
        result["recommendation"] = "CRITICAL: Cannot fully block and HP is low. Play all block cards."
    elif not can_fully_block:
        result["recommendation"] = "Cannot fully block. Will take {} damage.".format(net_damage)
    elif energy_for_offense == 0:
        result["recommendation"] = "Full block requires all energy."
    else:
        result["recommendation"] = "Full block with {} card(s). {} energy for offense.".format(
            block_cards_used, energy_for_offense)

    return result


TEST_CASES = [
    {
        "description": "Lethal scenario: 4 HP, 19 incoming, 2 block cards",
        "input": {
            "current_hp": 4,
            "current_block": 0,
            "incoming_damage": 19,
            "energy": 3,
            "dexterity": 0,
            "block_cards_in_hand": 2,
            "max_hp": 70
        },
        "expected": {
            "is_lethal": True,
            "playable_block_cards": 2,
            "max_achievable_block": 10,
            "net_damage_if_max_block": 9
        }
    },
    {
        "description": "Comfortable: 50 HP, 10 incoming, can fully block",
        "input": {
            "current_hp": 50,
            "current_block": 0,
            "incoming_damage": 10,
            "energy": 3,
            "dexterity": 0,
            "block_cards_in_hand": 3,
            "max_hp": 70
        },
        "expected": {
            "is_lethal": False,
            "can_fully_block": True,
            "cards_needed_to_fully_block": 2,
            "energy_for_offense_after_full_block": 1,
            "net_damage_if_max_block": 0
        }
    },
    {
        "description": "No incoming damage - free offense",
        "input": {
            "current_hp": 40,
            "current_block": 0,
            "incoming_damage": 0,
            "energy": 3,
            "dexterity": 0,
            "block_cards_in_hand": 2
        },
        "expected": {
            "is_lethal": False,
            "net_damage_if_max_block": 0,
            "can_fully_block": True
        }
    },
    {
        "description": "Existing block helps negate damage",
        "input": {
            "current_hp": 25,
            "current_block": 5,
            "incoming_damage": 8,
            "energy": 2,
            "dexterity": 0,
            "block_cards_in_hand": 1
        },
        "expected": {
            "is_lethal": False,
            "can_fully_block": True,
            "max_achievable_block": 10,
            "cards_needed_to_fully_block": 1,
            "energy_for_offense_after_full_block": 1
        }
    }
]
