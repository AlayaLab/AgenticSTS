# ruff: noqa: E501
"""REST PROMPT VERSION B: Strategy narrative framework.

Approach: Provide rich game knowledge and strategic reasoning
principles. Let the LLM reason through the decision using
domain expertise rather than a rigid scoring formula.
More flexible for edge cases, but requires the model to
internalize the reasoning rather than follow a formula.
"""

REST_PROMPT_B = """## Rest Site

HP: {hp}/{max_hp} ({hp_pct}%) | Gold: {gold} | Act {act} Floor {floor}

{deck_section}

## Options
{options_section}

## Strategy Guide

Smith (upgrade) is almost always the correct choice. Here's why:
- An upgraded card improves EVERY remaining combat in the run
- Healing 30% HP only delays death by 1-2 fights — it doesn't solve the problem
- Top players Smith 2-3 times per run and path through campfires specifically for upgrades
- "Offense solves problems permanently; healing just delays your inevitable death"

**When to Rest instead:**
- You would literally die in the next combat at current HP (not just "low HP" — actually lethal)
- You have zero meaningful upgrade targets (all key cards upgraded, only Strikes/Defends left)
- You have Dream Catcher relic (Rest also gives a card reward, making it less of a tradeoff)
- You have Regal Pillow (extra 15 HP makes Rest more efficient)

**When to Smith:**
- HP above 40%: Smith. You can survive the next fight.
- HP 25-40%: Smith if your deck is strong enough to win the next fight even at low HP. Your upgraded card will prevent more damage long-term than 30% healing.
- Even pre-boss: if your deck can beat the boss, Smith the card that makes the boss fight easier
- If you have a card that becomes dramatically better upgraded (cost reduction to 0, doubled effect), that upgrade is worth more than almost any heal

**What to upgrade (priority):**
1. Cards with massive upgrade payoff: cost becomes 0, damage/block doubles, gains new effect
2. Your deck's core engine card: the one you play every single combat
3. Key scaling Powers: these compound across every future turn
4. High-frequency attack/skill cards
5. NEVER upgrade Strikes or basic Defends — you should be removing these, not investing in them

## Your Task
Choose one option. Think about: Can I survive the next fight at current HP? Is there a high-value upgrade target?
Respond: {{"action": "choose_rest_option", "params": {{"index": <int>}}, "reasoning": "..."}}
"""
