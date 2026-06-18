
SCHEMA = {
    "name": "poison_kill_and_survive_check",
    "description": "Calculates turns until poison kills each enemy (no new poison added) and estimates if player can survive that long given block potential. Returns per-enemy lethality, survival estimate, and recommendation (defend-and-wait vs add-more-poison).",
    "parameters": {
        "current_hp": {"type": "integer", "description": "Player current HP"},
        "max_hp": {"type": "integer", "description": "Player max HP"},
        "incoming_damage": {"type": "integer", "description": "Total incoming damage this turn"},
        "enemy_hp": {"type": "array", "items": {"type": "integer"}, "description": "HP of each enemy"},
        "poison_stacks": {"type": "array", "items": {"type": "integer"}, "description": "Poison stacks on each enemy"},
        "num_enemies": {"type": "integer", "description": "Number of enemies"},
        "dexterity": {"type": "integer", "description": "Player dexterity"},
        "block_cards_in_hand": {"type": "integer", "description": "Block cards in hand"},
        "current_block": {"type": "integer", "description": "Player current block"},
        "energy": {"type": "integer", "description": "Available energy"},
        "act": {"type": "integer", "description": "Current act number"}
    },
    "required": ["current_hp", "incoming_damage", "enemy_hp", "poison_stacks", "num_enemies", "dexterity", "block_cards_in_hand", "current_block", "energy"]
}

APPLICABLE_STATES = ["monster", "elite", "boss"]

_UNKILLABLE_HP_THRESHOLD = 1_000_000

def _to_int(val):
    """Safely convert a value to int, handling lists, dicts, etc."""
    if isinstance(val, (list, tuple)):
        return _to_int(val[0]) if len(val) > 0 else 0
    if isinstance(val, dict):
        # Try common keys
        for k in ['amount', 'value', 'hp', 'stacks']:
            if k in val:
                return _to_int(val[k])
        return 0
    try:
        return int(val)
    except (TypeError, ValueError):
        return 0

def execute(current_hp, incoming_damage, enemy_hp, poison_stacks, num_enemies,
            dexterity=0, block_cards_in_hand=0, current_block=0, energy=3, max_hp=80, act=1):
    current_hp = _to_int(current_hp)
    incoming_damage = _to_int(incoming_damage)
    dexterity = _to_int(dexterity)
    block_cards_in_hand = _to_int(block_cards_in_hand)
    current_block = _to_int(current_block)
    energy = _to_int(energy)
    num_enemies = _to_int(num_enemies)

    # Normalize arrays
    if not isinstance(enemy_hp, (list, tuple)):
        enemy_hp = [enemy_hp]
    if not isinstance(poison_stacks, (list, tuple)):
        poison_stacks = [poison_stacks]

    enemy_hp = [_to_int(x) for x in enemy_hp]
    poison_stacks_clean = [_to_int(x) for x in poison_stacks]

    if any(hp > _UNKILLABLE_HP_THRESHOLD for hp in enemy_hp):
        return {
            "unkillable_enemy": True,
            "recommendation": (
                "SETUP PHASE: Enemy HP is effectively infinite — poison/damage is futile. "
                "Focus on Powers and self-buffs. "
                "Do not exhaust cards for offense."
            ),
        }

    # Pad poison_stacks if shorter than enemy_hp
    while len(poison_stacks_clean) < len(enemy_hp):
        poison_stacks_clean.append(0)

    enemies = []
    for i in range(len(enemy_hp)):
        hp = enemy_hp[i]
        poison = poison_stacks_clean[i]

        if poison <= 0:
            enemies.append({
                "enemy_index": i, "hp": hp, "poison": poison,
                "turns_to_kill": -1, "poison_lethal": False, "damage_shortfall": hp
            })
            continue

        turns = 0
        remaining_hp = hp
        p = poison
        total_poison_dmg = 0
        while remaining_hp > 0 and p > 0:
            remaining_hp -= p
            total_poison_dmg += p
            p -= 1
            turns += 1

        if remaining_hp <= 0:
            enemies.append({
                "enemy_index": i, "hp": hp, "poison": poison,
                "turns_to_kill": turns, "poison_lethal": True, "damage_shortfall": 0,
                "total_poison_damage": total_poison_dmg
            })
        else:
            max_poison_dmg = poison * (poison + 1) // 2
            enemies.append({
                "enemy_index": i, "hp": hp, "poison": poison,
                "turns_to_kill": -1, "poison_lethal": False,
                "damage_shortfall": remaining_hp,
                "total_poison_damage": max_poison_dmg
            })

    # Block potential estimation
    block_per_card = 5 + dexterity
    playable_blocks_now = min(block_cards_in_hand, energy)
    block_this_turn = current_block + playable_blocks_now * block_per_card

    net_damage_this_turn = max(0, incoming_damage - block_this_turn)
    hp_after_this_turn = current_hp - net_damage_this_turn

    # Sustained survival estimate
    avg_blocks_per_turn = min(2, energy)
    avg_block_per_turn = avg_blocks_per_turn * block_per_card
    avg_net_damage = max(0, incoming_damage - avg_block_per_turn)

    if hp_after_this_turn <= 0:
        survival_turns = 0
        lethal_this_turn = True
    else:
        lethal_this_turn = False
        if avg_net_damage <= 0:
            survival_turns = 999
        else:
            survival_turns = 1 + int(hp_after_this_turn / avg_net_damage)

    all_lethal = all(e["poison_lethal"] for e in enemies)
    max_turns_needed = max((e["turns_to_kill"] for e in enemies if e["poison_lethal"]), default=-1)
    can_survive = all_lethal and survival_turns >= max_turns_needed

    if lethal_this_turn:
        recommendation = "LETHAL_DANGER - Block everything, you may die this turn"
    elif all_lethal and can_survive:
        recommendation = "DEFEND_AND_WAIT - Poison kills all in {} turns, focus blocking".format(max_turns_needed)
    elif all_lethal and not can_survive:
        recommendation = "NEED_MORE_BLOCK - Poison lethal in {} turns but can only survive ~{} turns".format(max_turns_needed, survival_turns)
    elif any(e["poison_lethal"] for e in enemies):
        non_lethal = [e for e in enemies if not e["poison_lethal"]]
        shortfalls = [e["damage_shortfall"] for e in non_lethal]
        recommendation = "ADD_POISON - {} enemies need more poison (shortfall: {})".format(len(non_lethal), shortfalls)
    else:
        total_shortfall = sum(e["damage_shortfall"] for e in enemies)
        recommendation = "ADD_POISON - No lethal poison (total shortfall: {})".format(total_shortfall)

    return {
        "enemies": enemies,
        "all_poison_lethal": all_lethal,
        "max_turns_to_kill": max_turns_needed,
        "block_this_turn": block_this_turn,
        "net_damage_this_turn": net_damage_this_turn,
        "hp_after_this_turn": max(0, hp_after_this_turn),
        "estimated_survival_turns": survival_turns,
        "can_survive_poison_kill": can_survive,
        "lethal_this_turn": lethal_this_turn,
        "recommendation": recommendation
    }


TEST_CASES = [
    {
        "description": "Poison is lethal and player can survive",
        "input": {
            "current_hp": 50,
            "max_hp": 80,
            "incoming_damage": 20,
            "enemy_hp": [30],
            "poison_stacks": [10],
            "num_enemies": 1,
            "dexterity": 0,
            "block_cards_in_hand": 2,
            "current_block": 0,
            "energy": 3,
            "act": 2
        },
        "expected": {
            "all_poison_lethal": True,
            "can_survive_poison_kill": True,
            "lethal_this_turn": False
        }
    },
    {
        "description": "Poison not lethal - large HP enemy with small poison",
        "input": {
            "current_hp": 40,
            "max_hp": 80,
            "incoming_damage": 15,
            "enemy_hp": [100],
            "poison_stacks": [5],
            "num_enemies": 1,
            "dexterity": 0,
            "block_cards_in_hand": 1,
            "current_block": 0,
            "energy": 3,
            "act": 2
        },
        "expected": {
            "all_poison_lethal": False
        }
    },
    {
        "description": "Lethal danger this turn",
        "input": {
            "current_hp": 10,
            "max_hp": 80,
            "incoming_damage": 40,
            "enemy_hp": [50],
            "poison_stacks": [15],
            "num_enemies": 1,
            "dexterity": 0,
            "block_cards_in_hand": 1,
            "current_block": 0,
            "energy": 3,
            "act": 3
        },
        "expected": {
            "lethal_this_turn": True
        }
    }
]
