# ruff: noqa: E501
"""CARD SELECT PROMPT VERSION C: Frequency-Impact Scoring.

Approach: Score each card on two quantitative axes — how often it gets
played (Frequency) and how much the selection changes game outcomes
(Impact). Multiply for a composite score. Picks the highest-scoring
card. Good for models that handle structured numeric reasoning.
"""

CARD_SELECT_PROMPT_C = """## Card Selection — Frequency x Impact Scoring

**Screen**: {screen_type}
**Prompt**: {prompt}
**Status**: HP {hp}/{max_hp} | Gold: {gold} | Act {act} Floor {floor}

{deck_section}

{relics_section}

## Available Cards
{cards_section}

## Decision Framework: Score Each Card

For each selectable card, assign two scores (1-5), then multiply:

### Frequency (how often this card matters)
| Score | Meaning |
|-------|---------|
| 5 | Play this card EVERY combat, often multiple times |
| 4 | Play this card most combats |
| 3 | Play this card in about half of combats |
| 2 | Play this card occasionally (specific matchups) |
| 1 | Rarely play this card / dead draw most turns |

### Impact (how much does this selection change the game)

**If UPGRADE:**
| Score | Meaning | Examples |
|-------|---------|---------|
| 5 | Transforms the card (cost 2→0, doubles key effect) | Rupture 1→2 Str, Defragment, Neutralize |
| 4 | Major boost (cost reduction, significant stat jump) | Footwork 2→3 Dex, Bash extra Vulnerable |
| 3 | Solid improvement (+2-3 damage/block) | Shrug It Off, Coolheaded |
| 2 | Minor stat bump (+1 damage or block) | Most common attacks |
| 1 | Negligible difference when upgraded | Already-strong cards with tiny bump |

**If REMOVE:**
| Score | Meaning | Examples |
|-------|---------|---------|
| 5 | Actively harms you (Curse, bad status) | Any Curse, Wound, Dazed |
| 4 | Worst card in deck, always a dead draw | Strike in a 25-card deck |
| 3 | Below average, dilutes draw quality | Defend with better block options, off-archetype cards |
| 2 | Mediocre but occasionally useful | Early picks that lost relevance |
| 1 | Still contributes to your deck | Do not remove |

### Composite Score = Frequency x Impact
- Calculate for each card
- Pick the card with the HIGHEST score
- Tiebreaker: prefer the card closer to your deck's win condition

### Character-Specific Frequency Boosters
- **Ironclad**: Bash (every combat), Rupture (if self-damage build), Body Slam (if Block build)
- **Silent**: Neutralize (every combat), Footwork (every combat with Dex build), Noxious Fumes (Poison)
- **Defect**: Defragment (every combat), Coolheaded (every combat), Claw (if Claw build)
- **Regent**: Genesis (every combat), Glow (most combats), Reflect (frequent Block)
- **Necrobinder**: Haunt (every Soul combat), Squeeze (every Osty combat), Bodyguard (every combat)

### Rules
- NEVER upgrade Strikes/Defends you intend to remove (Frequency may be high but Impact is wasted)
- Curses: always Frequency=5, Impact=5 for removal (auto-pick)
- If all scores are below 6 and cancel is available, consider canceling

## Output
Score each card, pick the highest.
Select: {{"action": "select_card", "params": {{"index": <int>}}, "reasoning": "Card X: Freq=N, Impact=M, Score=NxM=S. Highest because ..."}}
{cancel_line}"""
