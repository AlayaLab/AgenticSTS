# ruff: noqa: E501
"""Combat prompt Version A: Threat-Priority Framework.

Decision tree: (1) Assess incoming threats (2) Classify turn as block/damage
(3) Pick the single best card for the situation.

Good for: clear decision tree, defensive play, survival-oriented reasoning.
"""

COMBAT_V_A_PROMPT = """\
## Combat — Threat-Priority Framework

### Step 1: Assess Threats
Look at each enemy's intent:
- Attack intents: sum all incoming damage
- Subtract your current Block → net incoming damage
- Compare net damage to your HP

Threat levels:
- **LETHAL**: net damage >= your HP → you MUST block or kill the attacker
- **HEAVY**: net damage > 40% of your HP → prioritize defense
- **SAFE**: net damage <= 40% of your HP → this is a damage/scaling turn

### Step 2: Classify This Turn
Based on threat level, decide your turn type:

**BLOCK TURN** (LETHAL or HEAVY threat):
1. Play the card that gives the most Block per energy
2. If you can kill the attacker instead (removing the threat entirely), that is better than blocking
3. If you have leftover energy after blocking enough, spend it on damage

**DAMAGE TURN** (SAFE threat — enemies buffing, debuffing, or low damage):
1. Apply debuffs first: Vulnerable (+50% damage taken) or Weak (-25% enemy damage)
2. Play 0-cost cards and draw cards before committing energy
3. Play your strongest attack card targeting the most dangerous enemy
4. Powers are excellent on safe turns — lasting value

**SCALING TURN** (no immediate threat, early rounds):
1. Play Power cards (permanent buffs)
2. Apply Vulnerable/Weak for future turns
3. Build resources (Stars, Orbs, Strength)

### Step 3: Pick ONE Card
From PLAYABLE cards only, choose the single best card for your turn type.
- Never pick [UNPLAYABLE] cards
- For enemy-targeting cards, provide the entity_id of your target
- Prefer killing a low-HP enemy over partial damage to a high-HP one
- 0-cost cards first (free value), then highest-impact card for remaining energy
- Debuffs before attacks: Vulnerable = +50% damage, Weak = -25% enemy damage

### Output Format
Respond with exactly one JSON object:
- Play a card: {"action": "play_card", "params": {"card_index": <int>, "target": "<entity_id or null>"}, "reasoning": "..."}
- End turn: {"action": "end_turn", "params": {}, "reasoning": "..."}

### Rules
- ONLY choose [PLAYABLE] cards. If none are playable, end_turn.
- Cards with (targets: enemy) MUST have a target entity_id.
- Cards without (targets: enemy) MUST have target: null.
- Use ALL energy each turn — unspent energy is wasted.
- Playing a card shifts all higher indices down by 1.
- Keep reasoning to 1-2 sentences: state the threat level and why this card is best.
"""
