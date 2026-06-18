# ruff: noqa: E501
"""REST PROMPT VERSION A: Structured scoring framework.

Approach: Give the LLM an explicit multi-factor scoring rubric.
Each factor has a clear weight and direction. The model scores
each factor and picks the option with the highest total.
Designed for small models (9B) that follow explicit rules well.
"""

REST_PROMPT_A = """## Rest Site Decision

**Status**: HP {hp}/{max_hp} ({hp_pct}%) | Gold: {gold} | Act {act} Floor {floor}

{deck_section}

## Available Options
{options_section}

## Decision Framework

**DEFAULT: Smith (upgrade) unless HP is dangerously low.**
Upgrading a card improves EVERY future combat. Healing only helps the next fight.

### Score each factor (-2 to +2), then sum:

| Factor | Favors Smith (+) | Favors Rest (-) |
|--------|------------------|-----------------|
| **HP Safety** | HP > 60%: +2 | HP < 25%: -2, HP 25-40%: -1 |
| **Upcoming Threat** | Next is normal monster: +1 | Next is boss/elite: -1 |
| **Upgrade Target Quality** | Have a game-changing upgrade (cost→0, doubled effect): +2 | Only mediocre upgrades left: -1 |
| **Deck Strength** | Deck already handles most fights: +1 | Deck has critical weakness an upgrade fixes: +2 |
| **Run Position** | Early/mid act (more fights ahead to benefit): +1 | Pre-boss floor: -1 if HP < 50% |

**Smith if total >= 0. Rest if total < 0.**

### Upgrade Priority (if Smith):
1. Cards that become dramatically better upgraded (cost reduction to 0, doubled damage/block)
2. Core scaling cards (Powers, key attacks you play every combat)
3. Cards you play most frequently
4. NEVER upgrade Strikes or Defends you plan to remove

### Rest Override Conditions:
- HP below 25% AND no Regal Pillow → almost always Rest
- Would die to any attack next combat → Rest
- Have Dream Catcher relic → Rest is less wasteful (gives card reward)

## Your Task
Choose a rest site option.
Respond: {{"action": "choose_rest_option", "params": {{"index": <int>}}, "reasoning": "Score: HP=X, Threat=X, Upgrade=X, Deck=X, Position=X → total=X → [Smith/Rest]"}}
"""
