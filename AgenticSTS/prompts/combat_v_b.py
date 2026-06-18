# ruff: noqa: E501
"""Combat prompt Version B: Sequencing-Optimized Framework.

Focus on optimal card play ORDER within the turn to maximize value.
Structure: (1) Debuffs/setup (2) Draw/energy cards (3) Damage/block by intent.

Good for: maximizing per-turn efficiency, combo plays, advanced sequencing.
"""

COMBAT_V_B_PROMPT = """\
## Combat — Sequencing-Optimized Framework

You are choosing ONE card to play right now. Cards are played one at a time.
To maximize this turn's value, follow the optimal play order below.

### Optimal Play Order (play the FIRST applicable category)

**Priority 1 — Lethal Defense**
If incoming damage after block >= your HP, you MUST play a Block card or kill the attacker NOW.
Survival always comes first.

**Priority 2 — 0-Cost Cards**
Free value. Play any 0-cost card that provides draw, damage, or block.
Examples: Prepared (draw+discard), Claw (growing damage), Shiv attacks.
Reason: costs nothing, may draw into better options.

**Priority 3 — Draw/Cycle Cards**
Cards that draw more cards or generate energy (Offering, Adrenaline, Acrobatics).
Reason: see more options before committing energy to big plays.

**Priority 4 — Debuff Cards**
Apply Vulnerable or Weak BEFORE playing attack cards.
- Vulnerable: target takes +50% damage from ALL subsequent attacks this turn
- Weak: target deals -25% damage (reduces incoming threat)
Play debuffs even if enemies are buffing — the debuff persists for future turns.
Skip if enemies already have Vulnerable/Weak.

**Priority 5 — Power Cards (if safe)**
If incoming damage is manageable (< 40% HP after block), play Powers for lasting scaling.
Examples: Demon Form (+Strength/turn), Defragment (+Focus), Noxious Fumes (+Poison/turn).

**Priority 6 — Damage Cards**
Target priority: (a) enemy you can kill this turn, (b) enemy with highest incoming damage, (c) lowest HP enemy.
Multi-hit attacks benefit most from Strength and Vulnerable — play after buffs/debuffs.
AoE attacks when facing 3+ enemies.

**Priority 7 — Block Cards**
Play remaining block cards to reduce incoming damage.
Block resets next turn — only block what you need to survive this turn's attacks.
Over-blocking wastes value.

**Priority 8 — End Turn**
If all playable cards are low-value and you have already blocked enough, end turn.

### Card Interaction Reminders
- Monologue: play FIRST — each card after grants +1 Strength
- Radiate: play LAST — hits = stars gained this turn
- Slow enemies: non-attack cards before attacks stack bonus damage
- Draw cards may change your hand — reassess after drawing

### Output Format
Respond with exactly one JSON object:
- Play a card: {"action": "play_card", "params": {"card_index": <int>, "target": "<entity_id or null>"}, "reasoning": "..."}
- End turn: {"action": "end_turn", "params": {}, "reasoning": "..."}

### Rules
- ONLY choose [PLAYABLE] cards. If none are playable, end_turn.
- Enemy-targeting cards MUST include target as entity_id string.
- Non-targeting cards MUST have target: null.
- Playing a card shifts all higher indices down by 1.
- Use ALL energy — unspent energy is wasted.
- Reasoning: 1-2 sentences. Name the priority category and the card's impact.
"""
