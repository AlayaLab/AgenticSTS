# ruff: noqa: E501
"""CARD SELECT PROMPT VERSION B: Deck Architecture Framework.

Approach: Evaluate each card in context of the deck's archetype and win
condition. Forces the model to identify what the deck is trying to do
before choosing, leading to archetype-coherent decisions.
"""

CARD_SELECT_PROMPT_B = """## Card Selection — Deck Architecture Framework

**Screen**: {screen_type}
**Prompt**: {prompt}
**Status**: HP {hp}/{max_hp} | Gold: {gold} | Act {act} Floor {floor}

{deck_section}

{relics_section}

## Available Cards
{cards_section}

## Decision Framework: Deck Architecture Analysis

### Step 1: Identify your deck's win condition
Scan your Current Deck and determine the PRIMARY archetype:
- **Ironclad**: Vulnerable exploit? Strength/self-damage? Exhaust engine? Block+Body Slam?
- **Silent**: Sly discard? Poison stacking? Shiv spam?
- **Defect**: Focus+Orbs? Claw spam? Dark Orb burst?
- **Regent**: Star engine? Forge/Sovereign Blade?
- **Necrobinder**: Soul cycling? Osty/Summon? Doom execution?

If no clear archetype yet (early Act 1), evaluate which direction each card pushes toward.

### Step 2: Evaluate each card against your archetype

**If UPGRADE — ask for each card:**
1. Is this card CENTRAL to my win condition? (highest priority)
2. Do I play this card every combat or only sometimes?
3. Does the upgrade create a meaningful power spike? (cost reduction > stat bump)
4. Does upgrading this card fix a weakness in my deck (draw, block, energy)?

**If REMOVE — ask for each card:**
1. Does this card actively HURT my deck plan? (wrong archetype, clogs draws)
2. Is this a dead draw in most combats? (high cost with no support, wrong synergy)
3. Does removing this card increase the chance of drawing my win condition cards?
4. Basic cards: Strike is almost always the worst card in your deck. Remove it.

### Step 3: Character-specific upgrade priorities
- **Ironclad**: Rupture (1→2 Str), Bash (extra Vulnerable turn), scaling Powers
- **Silent**: Neutralize first (0-cost Weak), Footwork (2→3 Dex), key Powers
- **Defect**: Defragment (doubled Focus), Coolheaded (draw+Frost), Echo Form
- **Regent**: Star generators (Genesis, Glow) before payoff cards
- **Necrobinder**: Haunt/Squeeze based on archetype, Soul Spark in Act 1

### Critical Rules
- NEVER upgrade a Strike or Defend you plan to remove — that wastes the upgrade
- Upgrade cards you play EVERY combat over cards you play sometimes
- Remove Curses immediately if offered (always highest priority removal)
- If your deck has no clear direction yet, upgrade the card with the broadest impact
- If all cards are poor targets and cancel is available, consider canceling

## Output
Choose the card most aligned with your deck's win condition.
Select: {{"action": "select_card", "params": {{"index": <int>}}, "reasoning": "My deck's win condition is [X]. Card Y is [central/peripheral] because ..."}}
{cancel_line}"""
