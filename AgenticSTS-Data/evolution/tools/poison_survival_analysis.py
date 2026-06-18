
SCHEMA = {
    "name": "poison_survival_analysis",
    "description": "Calculates turns until poison kills each enemy (no new poison assumed) and whether player can survive that long. Helps decide: keep stacking poison vs switch to pure defense. Shows damage shortfall if poison isn't lethal.",
    "parameters": {
        "enemy_hp": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Current HP of each enemy"
        },
        "poison_stacks": {
            "type": "array",
            "items": {"type": "integer"},
            "description": "Current poison stacks on each enemy"
        },
        "current_hp": {
            "type": "integer",
            "description": "Player current HP"
        },
        "incoming_damage": {
            "type": "integer",
            "description": "Total incoming damage this turn"
        }
    }
}

APPLICABLE_STATES = ["monster", "elite", "boss"]

_UNKILLABLE_HP_THRESHOLD = 1_000_000

def execute(enemy_hp, poison_stacks, current_hp, incoming_damage):
    hp_list = [int(h) for h in enemy_hp] if isinstance(enemy_hp, (list, tuple)) else [int(enemy_hp)]
    if any(hp > _UNKILLABLE_HP_THRESHOLD for hp in hp_list):
        return {
            "unkillable_enemy": True,
            "recommendation": (
                "SETUP PHASE: Enemy HP is effectively infinite — poison/damage is futile. "
                "Focus on Powers and self-buffs. Do not exhaust cards for offense."
            ),
        }

    results = []

    for i in range(len(enemy_hp)):
        hp = int(enemy_hp[i])
        poison = int(poison_stacks[i]) if i < len(poison_stacks) else 0

        if poison <= 0:
            results.append({
                "enemy": i,
                "hp": hp,
                "poison": 0,
                "lethal": False,
                "turns_to_kill": None,
                "total_poison_damage": 0,
                "damage_shortfall": hp
            })
            continue

        remaining = hp
        p = poison
        turns = 0
        while remaining > 0 and p > 0:
            remaining -= p
            p -= 1
            turns += 1

        total_damage = poison * (poison + 1) // 2

        results.append({
            "enemy": i,
            "hp": hp,
            "poison": poison,
            "lethal": remaining <= 0,
            "turns_to_kill": turns if remaining <= 0 else None,
            "total_poison_damage": total_damage,
            "damage_shortfall": max(0, remaining)
        })

    all_lethal = all(r["lethal"] for r in results) if results else False
    max_turns = max((r["turns_to_kill"] or 0) for r in results) if results else 0

    # Survival estimate based on current incoming damage rate
    if incoming_damage > 0:
        turns_can_survive = current_hp // incoming_damage
    else:
        turns_can_survive = 999

    can_outlast = turns_can_survive >= max_turns if max_turns > 0 else True

    if all_lethal and can_outlast:
        recommendation = "Poison is lethal and survivable. Focus DEFENSE only."
    elif all_lethal and not can_outlast:
        recommendation = "Poison lethal in {} turns but you survive ~{} turns. Need more block/debuffs urgently.".format(max_turns, turns_can_survive)
    else:
        shortfalls = [r for r in results if not r["lethal"]]
        total_shortfall = sum(r["damage_shortfall"] for r in shortfalls)
        recommendation = "Poison NOT lethal. {} more damage needed. Stack more poison or deal direct damage.".format(total_shortfall)

    return {
        "enemies": results,
        "all_poison_lethal": all_lethal,
        "max_turns_to_kill": max_turns if all_lethal else None,
        "turns_you_can_survive": turns_can_survive,
        "can_outlast_poison": can_outlast,
        "recommendation": recommendation
    }

TEST_CASES = [
    {
        "description": "Single enemy, poison is lethal, player can survive",
        "input": {
            "enemy_hp": [50],
            "poison_stacks": [10],
            "current_hp": 60,
            "incoming_damage": 5
        },
        "expected": {
            "all_poison_lethal": True,
            "can_outlast_poison": True
        }
    },
    {
        "description": "Mecha Knight scenario: 300 HP, 19 poison = only 190 damage, NOT lethal",
        "input": {
            "enemy_hp": [300],
            "poison_stacks": [19],
            "current_hp": 17,
            "incoming_damage": 30
        },
        "expected": {
            "all_poison_lethal": False
        }
    },
    {
        "description": "Two enemies, both lethal but tight survival",
        "input": {
            "enemy_hp": [20, 30],
            "poison_stacks": [7, 8],
            "current_hp": 50,
            "incoming_damage": 10
        },
        "expected": {
            "all_poison_lethal": True,
            "can_outlast_poison": True
        }
    },
    {
        "description": "No poison on enemy",
        "input": {
            "enemy_hp": [100],
            "poison_stacks": [0],
            "current_hp": 50,
            "incoming_damage": 10
        },
        "expected": {
            "all_poison_lethal": False
        }
    }
]
