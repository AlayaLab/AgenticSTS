from functools import lru_cache

APPLICABLE_STATES = ["monster", "elite", "boss"]

SCHEMA = {
    "name": "silent_exact_mitigation_line",
    "description": "Compute the mitigation-maximizing legal line for a Silent hand using recognized block, Weak, attack-down, and Pounce-to-free-Skill interactions.",
    "tool_type": "state_derived",
    "input_schema": {
        "type": "object",
        "properties": {
            "hand": {"type": "array", "items": {"type": ["string", "object"]}},
            "current_block": {"type": "integer", "minimum": 0},
            "dexterity": {"type": "integer"},
            "energy": {"type": "integer", "minimum": 0},
            "incoming_damage": {"type": "integer", "minimum": 0},
            "enemies": {"type": "array", "items": {"type": ["object", "string"]}},
            "current_hp": {"type": "integer", "minimum": 0}
        },
        "required": ["hand", "current_block", "dexterity", "energy", "incoming_damage", "enemies", "current_hp"]
    }
}


def _digits(s):
    out = []
    cur = ""
    for ch in str(s):
        if ch.isdigit():
            cur += ch
        elif cur:
            out.append(int(cur))
            cur = ""
    if cur:
        out.append(int(cur))
    return out


def _normalize_card_name(card):
    if isinstance(card, dict):
        for key in ("name", "card_name", "id", "key"):
            if key in card and card[key] is not None:
                card = card[key]
                break
    name = str(card).strip().lower()
    while "+" in name:
        name = name.replace("+", "")
    return " ".join(name.split())


def _is_upgraded(card):
    if isinstance(card, dict):
        for key in ("upgraded", "is_upgraded"):
            if key in card:
                return bool(card[key])
        for key in ("name", "card_name", "id", "key"):
            if key in card and card[key] is not None:
                return "+" in str(card[key])
        return False
    return "+" in str(card)


def _extract_attack_from_text(text):
    s = str(text).lower()
    start = s.find("attack(")
    marker_len = 7
    if start == -1:
        start = s.find("atk(")
        marker_len = 4
    if start == -1:
        return None
    start += marker_len
    end = s.find(")", start)
    if end == -1:
        return None
    inside = s[start:end].replace(" ", "")
    if "=" in inside:
        inside = inside.split("=", 1)[0]
    if "x" in inside:
        left, right = inside.split("x", 1)
        left_nums = _digits(left)
        right_nums = _digits(right)
        if left_nums and right_nums:
            return (left_nums[0], right_nums[0])
    nums = _digits(inside)
    if nums:
        return (nums[0], 1)
    return None


def _extract_enemy_attack(enemy):
    if isinstance(enemy, dict):
        for key_base, key_hits in (
            ("intent_damage", "hits"),
            ("damage", "hits"),
            ("attack_damage", "num_hits"),
            ("base_damage", "hits"),
        ):
            if key_base in enemy and enemy[key_base] is not None:
                base = int(enemy[key_base])
                hits = int(enemy.get(key_hits, enemy.get("multihit", enemy.get("hits", 1))) or 1)
                if base > 0 and hits > 0:
                    return (base, hits)
        for key in ("intent", "intent_text", "move", "move_text", "description", "name"):
            if key in enemy and enemy[key] is not None:
                parsed = _extract_attack_from_text(enemy[key])
                if parsed:
                    return parsed
        parsed = _extract_attack_from_text(str(enemy))
        if parsed:
            return parsed
        return None
    return _extract_attack_from_text(enemy)


def _extract_attacks(enemies, incoming_damage):
    attacks = []
    for enemy in enemies or []:
        parsed = _extract_enemy_attack(enemy)
        if parsed:
            base, hits = parsed
            if base > 0 and hits > 0:
                attacks.append((base, hits))
    if not attacks and incoming_damage > 0:
        attacks.append((incoming_damage, 1))
    return attacks


def _enemy_total(base, hits, weak, attack_down):
    per_hit = base - attack_down
    if per_hit < 0:
        per_hit = 0
    if weak:
        per_hit = (per_hit * 3) // 4
    return per_hit * hits


def _state_total(enemy_state):
    total = 0
    for base, hits, weak, attack_down in enemy_state:
        total += _enemy_total(base, hits, weak, attack_down)
    return total


def _make_actions(hand, dexterity):
    actions = []
    for idx, raw in enumerate(hand):
        base_name = _normalize_card_name(raw)
        upgraded = _is_upgraded(raw)
        display = str(raw.get("name") if isinstance(raw, dict) and raw.get("name") is not None else raw)
        if base_name == "defend":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 1, "skill": True, "block": 8 if upgraded else 5})
        elif base_name == "survivor":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 1, "skill": True, "block": 11 if upgraded else 8})
        elif base_name == "backflip":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 1, "skill": True, "block": 8 if upgraded else 5})
        elif base_name == "dash":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 2, "skill": False, "block": 13 if upgraded else 10})
        elif base_name == "piercing wail":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 1, "skill": True, "pw": 8 if upgraded else 6})
        elif base_name == "neutralize":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 0, "skill": False, "weak": True})
        elif base_name == "pounce":
            actions.append({"id": idx, "name": display, "base": base_name, "cost": 1, "skill": False, "pounce": True})
    for action in actions:
        if "block" in action:
            action["block"] += dexterity
            if action["block"] < 0:
                action["block"] = 0
    return actions


def execute(hand, current_block, dexterity, energy, incoming_damage, enemies, current_hp):
    attacks = _extract_attacks(enemies, incoming_damage)
    enemy_state = tuple((base, hits, False, 0) for base, hits in attacks)
    actions = _make_actions(hand, dexterity)
    start_total = _state_total(enemy_state)
    if incoming_damage > 0 and start_total == 0:
        start_total = incoming_damage
    if incoming_damage > 0 and start_total == 0:
        enemy_state = ((incoming_damage, 1, False, 0),)
        start_total = incoming_damage

    @lru_cache(None)
    def search(used_mask, remaining_energy, pounce_free, state, gained_block):
        state_list = [tuple(x) for x in state]
        damage_after_mitigation = _state_total(state_list)
        final_block = current_block + gained_block
        net_damage = damage_after_mitigation - final_block
        if net_damage < 0:
            net_damage = 0
        best = {
            "sequence": [],
            "sequence_text": "",
            "net_damage": net_damage,
            "damage_after_mitigation": damage_after_mitigation,
            "final_block": final_block,
            "energy_spent": energy - remaining_energy,
            "cards_played": 0,
            "damage_reduction": max(0, start_total - damage_after_mitigation),
            "gained_block": gained_block,
        }

        for i, action in enumerate(actions):
            if used_mask & (1 << i):
                continue
            cost = action["cost"]
            next_pounce = pounce_free
            if pounce_free and action.get("skill"):
                cost = 0
                next_pounce = False
            if cost > remaining_energy:
                continue

            next_state = [list(x) for x in state_list]
            next_block = gained_block
            label = action["name"]

            if action["base"] == "neutralize":
                best_idx = -1
                best_total = None
                for idx_enemy, (base, hits, weak, attack_down) in enumerate(next_state):
                    if _enemy_total(base, hits, weak, attack_down) <= 0:
                        continue
                    cand = [list(x) for x in next_state]
                    cand[idx_enemy][2] = True
                    cand_total = _state_total(cand)
                    if best_total is None or cand_total < best_total:
                        best_total = cand_total
                        best_idx = idx_enemy
                if best_idx != -1:
                    next_state[best_idx][2] = True
                    label = action["name"] + " -> enemy[" + str(best_idx) + "]"
            elif action["base"] == "piercing wail":
                pw = action["pw"]
                for idx_enemy in range(len(next_state)):
                    next_state[idx_enemy][3] += pw
            elif action["base"] == "pounce":
                next_pounce = True
            elif "block" in action:
                next_block += action["block"]

            child = search(
                used_mask | (1 << i),
                remaining_energy - cost,
                next_pounce,
                tuple(tuple(x) for x in next_state),
                next_block,
            )
            candidate = dict(child)
            candidate["sequence"] = [label] + child["sequence"]
            candidate["sequence_text"] = " -> ".join(candidate["sequence"])
            candidate["cards_played"] = child["cards_played"] + 1

            best_tuple = (best["net_damage"], best["energy_spent"], best["cards_played"], -best["damage_reduction"], -best["gained_block"])
            cand_tuple = (candidate["net_damage"], candidate["energy_spent"], candidate["cards_played"], -candidate["damage_reduction"], -candidate["gained_block"])
            if cand_tuple < best_tuple:
                best = candidate

        return best

    result = search(0, energy, False, tuple(enemy_state), 0)
    result["recognized_cards"] = [a["name"] for a in actions]
    result["recognized_count"] = len(actions)
    result["incoming_damage_used"] = start_total if start_total > 0 else incoming_damage
    result["prevents_hp_loss"] = result["net_damage"] == 0
    result["lethal_risk"] = result["net_damage"] >= current_hp if current_hp is not None else None
    result["summary"] = "Play mitigation line first" if result["sequence"] else "No recognized mitigation line found"
    return result


TEST_CASES = [
    {
        "input": {
            "hand": ["Defend", "Survivor", "Neutralize"],
            "current_block": 0,
            "dexterity": 0,
            "energy": 2,
            "incoming_damage": 13,
            "enemies": [{"intent": "Attack(13)"}],
            "current_hp": 20
        },
        "expected": {"net_damage": 0, "prevents_hp_loss": True},
        "expected_sequence_text_contains": "Defend",
        "description": "Uses exact block values instead of relying on weak alone against a single heavy hit."
    },
    {
        "input": {
            "hand": ["Neutralize", "Defend"],
            "current_block": 0,
            "dexterity": 0,
            "energy": 1,
            "incoming_damage": 20,
            "enemies": [{"intent": "Attack(14)"}, {"intent": "Attack(6)"}],
            "current_hp": 20
        },
        "expected": {"net_damage": 11},
        "expected_sequence_text_contains": "enemy[0]",
        "description": "Neutralize should target the highest-damage attacker in a multi-enemy turn."
    },
    {
        "input": {
            "hand": ["Piercing Wail"],
            "current_block": 0,
            "dexterity": 0,
            "energy": 1,
            "incoming_damage": 15,
            "enemies": [{"intent": "Attack(5x3=15)"}],
            "current_hp": 10
        },
        "expected": {"net_damage": 0, "damage_reduction": 15},
        "expected_keys": ["sequence_text", "lethal_risk", "summary"],
        "description": "Correctly values Piercing Wail as premium mitigation versus multi-hit attacks."
    }
]
