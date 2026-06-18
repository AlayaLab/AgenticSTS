
SCHEMA = {
    "name": "poison_block_survival_plan",
    "description": "Calculates turns until poison kills each enemy and whether player can survive that long given current block potential. Accounts for dexterity when estimating block. Helps decide: keep stacking poison vs switch to pure defense vs recognize lethal.",
    "parameters": {
        "type": "object",
        "properties": {
            "current_hp": {"type": "integer", "description": "Player current HP"},
            "incoming_damage": {"type": "integer", "description": "Total incoming damage this turn"},
            "enemy_hp": {"type": "array", "items": {"type": "integer"}, "description": "Current HP of each enemy"},
            "poison_stacks": {"type": "array", "items": {"type": "integer"}, "description": "Poison stacks on each enemy"},
            "energy": {"type": "integer", "description": "Current energy available"},
            "dexterity": {"type": "integer", "description": "Player dexterity (affects block card values)"},
            "block_cards_in_hand": {"type": "integer", "description": "Number of block cards in hand"},
            "current_block": {"type": "integer", "description": "Player current block"}
        },
        "required": ["current_hp", "incoming_damage", "enemy_hp", "poison_stacks", "energy", "dexterity", "block_cards_in_hand", "current_block"]
    }
}

APPLICABLE_STATES = ["monster", "elite", "boss"]

_UNKILLABLE_HP_THRESHOLD = 1_000_000

def execute(current_hp, incoming_damage, enemy_hp, poison_stacks, energy, dexterity, block_cards_in_hand, current_block):
    hp_list = [int(h) for h in enemy_hp] if isinstance(enemy_hp, (list, tuple)) else [int(enemy_hp)]
    if any(hp > _UNKILLABLE_HP_THRESHOLD for hp in hp_list):
        return {
            "unkillable_enemy": True,
            "recommendation": (
                "SETUP PHASE: Enemy HP is effectively infinite — poison/damage is futile. "
                "Focus on Powers and self-buffs. Do not exhaust cards for offense."
            ),
        }

    results = {}

    # --- Poison lethality per enemy ---
    enemy_results = []
    all_lethal = True

    for i in range(len(enemy_hp)):
        hp = enemy_hp[i]
        poison = poison_stacks[i] if i < len(poison_stacks) else 0

        if hp <= 0:
            enemy_results.append({"enemy_index": i, "status": "already_dead", "turns_to_kill": 0})
            continue

        if poison <= 0:
            all_lethal = False
            enemy_results.append({
                "enemy_index": i,
                "status": "no_poison",
                "hp_remaining": hp,
                "turns_to_kill": -1
            })
            continue

        # Simulate poison ticking: each turn deals current_poison then poison -= 1
        remaining_hp = hp
        current_poison = poison
        turns = 0
        total_poison_dmg = 0

        while remaining_hp > 0 and current_poison > 0:
            remaining_hp -= current_poison
            total_poison_dmg += current_poison
            current_poison -= 1
            turns += 1

        if remaining_hp <= 0:
            enemy_results.append({
                "enemy_index": i,
                "status": "poison_lethal",
                "turns_to_kill": turns,
                "total_poison_damage": total_poison_dmg,
                "overkill": abs(remaining_hp)
            })
        else:
            all_lethal = False
            enemy_results.append({
                "enemy_index": i,
                "status": "poison_NOT_lethal",
                "turns_to_kill": -1,
                "total_poison_damage": total_poison_dmg,
                "hp_remaining_after_poison": remaining_hp,
                "damage_shortfall": remaining_hp
            })

    results["enemies"] = enemy_results

    max_turns = 0
    if all_lethal:
        for e in enemy_results:
            t = e.get("turns_to_kill", 0)
            if t > max_turns:
                max_turns = t
    results["all_poison_lethal"] = all_lethal
    results["turns_to_win_via_poison"] = max_turns if all_lethal else -1

    # --- Block and survival analysis ---
    base_block_per_card = max(0, 5 + dexterity)
    playable_block_cards = min(block_cards_in_hand, energy)
    max_new_block = playable_block_cards * base_block_per_card
    total_block = current_block + max_new_block
    unblocked_damage = max(0, incoming_damage - total_block)
    hp_after = current_hp - unblocked_damage
    is_lethal = hp_after <= 0
    energy_after_blocking = energy - playable_block_cards

    results["survival"] = {
        "incoming_damage": incoming_damage,
        "current_block": current_block,
        "estimated_block_per_card": base_block_per_card,
        "max_additional_block": max_new_block,
        "total_possible_block": total_block,
        "unblocked_damage": unblocked_damage,
        "hp_after_full_block": hp_after,
        "is_lethal_this_turn": is_lethal,
        "energy_remaining_after_block": energy_after_blocking
    }

    # --- Recommendation ---
    if is_lethal:
        results["recommendation"] = "LETHAL THREAT: Cannot survive this turn even blocking with all block cards. Use potions, kill enemy, or find other mitigation."
    elif all_lethal and max_turns <= 2:
        results["recommendation"] = f"DEFEND ONLY: Poison kills all enemies in {max_turns} turn(s). Play all block cards and survive."
    elif all_lethal and max_turns <= 4:
        results["recommendation"] = f"Poison lethal in {max_turns} turns. Prioritize block but consider if more poison speeds things up."
    elif not all_lethal:
        shortfalls = [e.get("damage_shortfall", 0) for e in enemy_results if e.get("status") == "poison_NOT_lethal"]
        total_shortfall = sum(shortfalls)
        if total_shortfall > 0:
            results["recommendation"] = f"Poison NOT lethal (shortfall: {total_shortfall} HP). Need more poison or direct damage. Block incoming {incoming_damage} first."
        else:
            results["recommendation"] = "Mix offense and defense based on HP cushion."
    else:
        results["recommendation"] = "Evaluate based on HP cushion and remaining enemies."

    return results


TEST_CASES = [
    {
        "description": "Poison is lethal in 4 turns, player can survive",
        "input": {
            "current_hp": 50,
            "incoming_damage": 15,
            "enemy_hp": [30],
            "poison_stacks": [10],
            "energy": 3,
            "dexterity": 0,
            "block_cards_in_hand": 2,
            "current_block": 0
        },
        "expected": {
            "all_poison_lethal": True,
            "turns_to_win_via_poison": 4
        }
    },
    {
        "description": "Lagavulin Matriarch Round 11 - lethal turn with dex debuff, poison not lethal",
        "input": {
            "current_hp": 18,
            "incoming_damage": 23,
            "enemy_hp": [100],
            "poison_stacks": [7],
            "energy": 3,
            "dexterity": -2,
            "block_cards_in_hand": 1,
            "current_block": 0
        },
        "expected_contains": "LETHAL THREAT"
    },
    {
        "description": "Poison lethal in 2 turns, should defend only",
        "input": {
            "current_hp": 30,
            "incoming_damage": 12,
            "enemy_hp": [10],
            "poison_stacks": [8],
            "energy": 3,
            "dexterity": 1,
            "block_cards_in_hand": 2,
            "current_block": 0
        },
        "expected_contains": "DEFEND ONLY"
    },
    {
        "description": "Multiple enemies, one poisoned one not",
        "input": {
            "current_hp": 40,
            "incoming_damage": 20,
            "enemy_hp": [15, 25],
            "poison_stacks": [12, 0],
            "energy": 3,
            "dexterity": 0,
            "block_cards_in_hand": 2,
            "current_block": 5
        },
        "expected": {
            "all_poison_lethal": False,
            "turns_to_win_via_poison": -1
        }
    }
]
