
SCHEMA = {
    "name": "poison_turns_to_kill",
    "description": "Calculate how many turns until poison kills each enemy (no additional poison assumed). Shows if current poison is lethal and how many survival turns needed. Helps decide: keep stacking poison vs switch to pure defense.",
    "applicable_states": ["monster", "elite", "boss"],
    "parameters": {
        "enemy_hp": {"type": "array", "description": "List of enemy HP values"},
        "poison_stacks": {"type": "array", "description": "List of poison stacks on each enemy"},
        "enemy_block": {"type": "array", "description": "List of enemy block values"}
    }
}

APPLICABLE_STATES = ["monster", "elite", "boss"]

_UNKILLABLE_HP_THRESHOLD = 1_000_000

def execute(enemy_hp, poison_stacks, enemy_block):
    hp_list = [int(h) for h in enemy_hp] if isinstance(enemy_hp, (list, tuple)) else [int(enemy_hp)]
    if any(hp > _UNKILLABLE_HP_THRESHOLD for hp in hp_list):
        return {
            "unkillable_enemy": True,
            "recommendation": "SETUP PHASE: Enemy HP is effectively infinite. Do not waste poison/damage cards.",
        }

    results = []
    for i in range(len(enemy_hp)):
        hp = enemy_hp[i]
        poison = poison_stacks[i] if i < len(poison_stacks) else 0
        block = enemy_block[i] if i < len(enemy_block) else 0

        if poison <= 0:
            results.append({
                "enemy_index": i,
                "hp": hp,
                "poison": 0,
                "total_poison_damage": 0,
                "poison_is_lethal": False,
                "turns_to_kill": -1,
                "message": "No poison on this enemy"
            })
            continue

        # Total damage from current poison: n + (n-1) + ... + 1 = n*(n+1)/2
        total_damage = poison * (poison + 1) // 2
        is_lethal = total_damage >= hp

        # Simulate turn by turn
        remaining_hp = hp
        current_poison = poison
        turns = 0

        while remaining_hp > 0 and current_poison > 0:
            damage = current_poison
            remaining_hp -= damage
            current_poison -= 1
            turns += 1

        if remaining_hp > 0:
            turns_to_kill = -1
            hp_after_poison = remaining_hp
        else:
            turns_to_kill = turns
            hp_after_poison = 0

        # Calculate extra poison needed to kill if not lethal
        extra_poison_needed = 0
        if not is_lethal:
            # Need total_damage + extra >= hp
            # Adding X more poison means total = (poison+X)*(poison+X+1)/2
            test_poison = poison
            while test_poison * (test_poison + 1) // 2 < hp:
                test_poison += 1
            extra_poison_needed = test_poison - poison

        results.append({
            "enemy_index": i,
            "hp": hp,
            "poison": poison,
            "total_poison_damage": total_damage,
            "poison_is_lethal": is_lethal,
            "turns_to_kill": turns_to_kill,
            "hp_remaining_if_not_lethal": hp_after_poison,
            "extra_poison_needed_for_lethal": extra_poison_needed
        })

    all_lethal = all(r["poison_is_lethal"] for r in results if r["poison"] > 0)
    max_turns = max((r["turns_to_kill"] for r in results if r["turns_to_kill"] > 0), default=0)

    if not any(r["poison"] > 0 for r in results):
        recommendation = "No poison on any enemy."
    elif all_lethal and max_turns <= 3:
        recommendation = f"Poison kills all in {max_turns} turns — focus entirely on blocking!"
    elif all_lethal and max_turns <= 6:
        recommendation = f"Poison kills in {max_turns} turns — prioritize defense but add poison if free."
    elif all_lethal:
        recommendation = f"Poison lethal but takes {max_turns} turns — TOO SLOW, add more poison to speed up!"
    else:
        recommendation = "Poison NOT lethal — must add more poison or deal direct damage!"

    return {
        "enemies": results,
        "all_enemies_lethal": all_lethal,
        "max_turns_to_survive": max_turns,
        "recommendation": recommendation
    }

TEST_CASES = [
    {
        "description": "Slimed Berserker scenario: 182 HP, 19 poison — lethal but takes 16 turns",
        "input": {
            "enemy_hp": [182],
            "poison_stacks": [19],
            "enemy_block": [0]
        },
        "expected": {
            "all_enemies_lethal": True,
            "max_turns_to_survive": 16
        }
    },
    {
        "description": "Not enough poison: 100 HP, 5 poison (total 15 damage)",
        "input": {
            "enemy_hp": [100],
            "poison_stacks": [5],
            "enemy_block": [0]
        },
        "expected": {
            "all_enemies_lethal": False
        }
    },
    {
        "description": "Exactly lethal: 15 HP, 5 poison (total 15 damage)",
        "input": {
            "enemy_hp": [15],
            "poison_stacks": [5],
            "enemy_block": [0]
        },
        "expected": {
            "all_enemies_lethal": True,
            "max_turns_to_survive": 5
        }
    },
    {
        "description": "Quick kill: 10 HP, 8 poison",
        "input": {
            "enemy_hp": [10],
            "poison_stacks": [8],
            "enemy_block": [0]
        },
        "expected": {
            "all_enemies_lethal": True,
            "max_turns_to_survive": 2
        }
    },
    {
        "description": "Multi-enemy scenario",
        "input": {
            "enemy_hp": [30, 50],
            "poison_stacks": [10, 3],
            "enemy_block": [0, 0]
        },
        "expected": {
            "all_enemies_lethal": False
        }
    }
]
