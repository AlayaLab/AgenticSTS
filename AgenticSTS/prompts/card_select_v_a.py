# ruff: noqa: E501
"""CARD SELECT PROMPT VERSION A: Tier-Based Evaluation.

Approach: Assign each selectable card a tier (S/A/B/C/D) based on how much
the selection effect improves or fixes the card/deck. Quick categorical
decisions work well for small models that struggle with open-ended reasoning.
"""

CARD_SELECT_PROMPT_A = """## Card Selection — Tier-Based Evaluation

**Screen**: {screen_type}
**Prompt**: {prompt}
**Status**: HP {hp}/{max_hp} | Gold: {gold} | Act {act} Floor {floor}

{deck_section}

{relics_section}

## Available Cards
{cards_section}

## Decision Framework: Tier Assignment

Assign each card a tier based on the selection type:

### If UPGRADE:
| Tier | Criteria | Examples |
|------|----------|---------|
| **S** | Cost reduction (2→1 or 1→0), doubles a key effect | Defragment, Footwork, Neutralize, Rupture |
| **A** | Major power boost on a card you play every combat | Demon Form, Noxious Fumes, Genesis, Haunt |
| **B** | Solid improvement on a regularly-played card | Shrug It Off, Coolheaded, Backflip |
| **C** | Minor stat bump (+1 damage/block) or situational card | Most Strikes, niche utility cards |
| **D** | Cards you plan to remove, or rarely play | Strike, Defend (if removal planned) |

### If REMOVE:
| Tier | Criteria | Examples |
|------|----------|---------|
| **S** | Curses, status cards, unplayable junk | Any Curse, Wound, Dazed, Burn |
| **A** | Basic Strikes (worst cards in most decks) | Strike |
| **B** | Basic Defends (once you have better block) | Defend |
| **C** | Off-archetype cards that dilute draws | Cards from wrong build direction |
| **D** | Cards that still contribute to your deck | Keep these |

### If ENCHANT:
| Tier | Criteria |
|------|----------|
| **S** | High-frequency card that benefits massively (e.g., Corrupted on a scaling attack) |
| **A** | Core card that gains a strong bonus from the enchantment |
| **B** | Decent card, moderate benefit |
| **C** | Rarely-played card, marginal benefit |

## Character-Specific Hints
- **Ironclad**: Upgrade Rupture (1→2 Strength/trigger), Bash (more Vulnerable turns), Body Slam
- **Silent**: Upgrade Neutralize first (free Weak), Footwork (+3 Dex), Noxious Fumes
- **Defect**: Upgrade Defragment (doubled Focus), Echo Form, Coolheaded
- **Regent**: Upgrade Genesis, Glow, Star generators before payoff cards
- **Necrobinder**: Upgrade Haunt (Soul build), Squeeze (Osty build), Soul Spark first

## Rules
- NEVER upgrade Strikes/Defends if you plan to remove them later
- Pick the HIGHEST tier card. If tied, pick the card you play most often.
- If all options are bad and cancel is available, cancel.

## Output
Pick the highest-tier card.
Select: {{"action": "select_card", "params": {{"index": <int>}}, "reasoning": "Card X is tier [S/A/B/C] because ..."}}
{cancel_line}"""
