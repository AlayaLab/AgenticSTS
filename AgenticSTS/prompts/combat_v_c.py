# ruff: noqa: E501
"""Combat prompt Version C: Kill-or-Survive Binary Framework.

Simplest possible decision framework for a 9B parameter model.
Structure: (1) Can I kill? → damage (2) Will I die? → block (3) Neither → scale.

Good for: clarity, minimal reasoning, fast inference, fewer errors.
"""

COMBAT_V_C_PROMPT = """\
## Combat — Kill or Survive

Choose ONE card to play. Follow these three checks IN ORDER. Stop at the first one that applies.

---

### Check 1: CAN I KILL an enemy this turn?
Look at each enemy's effective HP (HP + Block).
If your remaining playable attack cards can deal enough total damage to kill it — play damage cards targeting that enemy.

Kill priority:
- Kill the enemy dealing the MOST damage to you (removes the threat)
- If tied, kill the lowest HP enemy (easier to finish)
- Apply Vulnerable first if you have it AND have attacks to follow up (Vulnerable = +50% damage)

If you can kill → play your best attack card (or Vulnerable if not yet applied).

---

### Check 2: WILL I DIE this turn?
Sum all enemy attack intents. Subtract your current Block. Compare to your HP.

If net incoming damage >= your HP:
- Play your highest Block card
- OR kill the attacking enemy (Check 1 takes priority)
- Weak on the attacker also helps (-25% damage dealt)

If net damage > 40% of HP:
- Block is strongly preferred over damage
- Exception: you can kill the biggest attacker

If you will die or take heavy damage → play Block or Weak.

---

### Check 3: SAFE TURN — Scale up
You will survive and cannot kill. Use this turn to grow stronger:

Best plays (in order):
1. **Power cards** — permanent buffs (Strength, Dexterity, Focus, Demon Form, Noxious Fumes)
2. **Debuff cards** — Vulnerable or Weak on enemies for future turns
3. **Damage** — chip away at the most dangerous enemy
4. **0-cost cards** — free value, always play these
5. **Block** — if nothing better, reduce chip damage

---

### Quick Reference
| Situation | Play |
|-----------|------|
| Can kill enemy | Attack (Vulnerable first if available) |
| Lethal incoming | Highest Block card or kill attacker |
| Heavy damage (>40% HP) | Block cards, then damage |
| Safe turn | Powers > Debuffs > Damage > Block |
| No playable cards | End turn |

### Output Format
One JSON object:
- Play card: {"action": "play_card", "params": {"card_index": <int>, "target": "<entity_id or null>"}, "reasoning": "..."}
- End turn: {"action": "end_turn", "params": {}, "reasoning": "..."}

### Rules
- ONLY [PLAYABLE] cards. No [UNPLAYABLE] cards ever.
- Enemy-targeting cards: target = entity_id string. Non-targeting: target = null.
- Index shifts: playing a card moves all higher indices down by 1.
- Spend ALL energy. Unspent energy = wasted.
- Reasoning: 1 sentence. Which check applied and why this card.
"""
