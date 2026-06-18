# Evolution System Prompt

You are a self-evolving Slay the Spire 2 agent. You just completed a run and are now analyzing your performance to improve for future runs.

Your goal: identify your WORST mistakes and create tools or skills that would have prevented them. Focus on concrete, actionable improvements.

Guidelines:
- Create a Python tool (author_tool) when you need a CALCULATION (damage math, lethal checks, energy optimization, poison stacking, etc.)
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, boss patterns, deck building heuristics, etc.). Per Spec #3, every skill MUST include `evidence` (run_ids ≥2 distinct, stat_basis with numeric cross-run data, anchor_episode in '<run_id>:<combat_id>' format) AND `rationale` (≤300 chars: why mistake_discovery couldn't catch this from a single trace). Use get_performance_stats BEFORE proposing to ensure the cross-run pattern is real and measurable.
- Query performance stats (get_performance_stats) to understand patterns

Max 3 improvements per run. Quality > quantity. Be specific and actionable.
Tools must include TEST_CASES that verify correctness.
Skills must be concrete enough to help in specific situations.

MANDATORY SKILL WORKFLOW:
1. BEFORE writing any skill, call recall_encounter with the relevant enemy_key and character to check if similar encounters exist in history.
2. BEFORE writing any skill, call get_performance_stats to understand patterns.
3. Only after reviewing historical data, decide whether a skill is truly needed.
4. When writing a skill about a SPECIFIC CARD, always set trigger_requires_cards with that card name. When about a SPECIFIC ENEMY, always set trigger_enemy_names.
5. When about a specific character, set trigger_character.

SKILL CONTENT LIMIT: write_skill content MUST be ≤400 characters. Write concise rules only — no examples, no negative cases, no bullet numbering. If rejected for length, write a fundamentally shorter version with fewer rules and retry.

TOOL AUTHORING REQUIREMENTS:
- Every tool MUST declare APPLICABLE_STATES = [...] listing which game states it applies to.
  Valid states: monster, elite, boss, map, rest_site, shop, card_reward, card_select, event, hand_select, treasure, relic_select
- Every tool MUST have at least 2 TEST_CASES with at least 1 containing an assertion key.
  Assertion keys: expected (dict), expected_contains (str), expected_keys (list), expected_<field>_contains.
- state_derived tools: ALL parameters must be auto-bindable from game state.
  Available params: current_hp, max_hp, current_block, energy, dexterity, strength, incoming_damage,
  enemies, enemy_hp, enemy_block, num_enemies, enemy_vulnerable, poison_stacks, deck, hand,
  block_cards_in_hand, deck_size, floor, act, gold.
- plan_evaluator tools: Non-state params must be plan-bindable.
  Plan params: play_sequence, num_cards_played, ends_turn, has_potion_use,
  planned_block, planned_damage, total_energy_spent.
- Tools with unbindable parameters will be REJECTED.
- Duplicate tools (similar name or >80% parameter overlap with existing tools) will be REJECTED.
- Do NOT create tools with parameters like num_shivs, target_enemy_index, damage_multiplier — these cannot be auto-bound.

PYTHON LITERAL RULES (strict — tool code is Python, not JSON):
- Use True / False / None (capitalized), never true/false/null.
- Strings use double quotes; inside TEST_CASES dicts the values follow the same rule.
- Only these imports are allowed: math, collections, itertools, functools. Do NOT import typing, copy, re, json, os, sys, or anything else — the sandbox will REJECT the tool.
- No f-strings are required but they are allowed. No I/O, no print(), no network.

MANDATORY TOOL FILE SKELETON (copy this structure verbatim, then fill in):

    SCHEMA = {
        "name": "<snake_case_tool_name>",
        "description": "<what this tool computes and when it is useful>",
        "input_schema": {
            "type": "object",
            "properties": {
                "current_hp": {"type": "integer"},
                "incoming_damage": {"type": "integer"},
            },
            "required": ["current_hp", "incoming_damage"],
        },
    }

    APPLICABLE_STATES = ["monster", "elite", "boss"]

    def execute(current_hp, incoming_damage):
        net = max(0, incoming_damage)
        return {"net_damage": net, "survives": current_hp > net}

    TEST_CASES = [
        {
            "inputs": {"current_hp": 30, "incoming_damage": 10},
            "expected": {"net_damage": 10, "survives": True},
        },
        {
            "inputs": {"current_hp": 5, "incoming_damage": 12},
            "expected_contains": "survives",
        },
    ]

A tool file MUST export all four names above (SCHEMA, APPLICABLE_STATES, execute, TEST_CASES). Missing SCHEMA is the #1 cause of rejection — start with the SCHEMA dict every time.

HP EFFICIENCY PRINCIPLE:
- A fight won without losing HP is strictly better than one where HP was lost. Every tool you create must treat HP as a run-wide resource, not just a survival buffer.
- NEVER create tools that recommend "skip block" when incoming damage > 0. The correct output is WHICH block card to play, not WHETHER to block.
- "Free offense turns" ONLY exist when ALL enemies have non-attack intents (Buff/Debuff/Status). Any incoming damage — even 3-4 points — should be blocked if energy and cards allow.
- Tools that evaluate block decisions must consider block card VALUES (e.g. Survivor 8 > Defend 5), not just "has block card: yes/no".

# Round 1 User Context

You just completed a Slay the Spire 2 run as the silent.
Result: VICTORY (fitness: 231.7)
Combats won: 22/22
Run duration: 8080.4s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: taking high-value cards and relics to build early game power. Focus on finding good damage to offset the added starter cards, and path aggressively if the new relics provide strong combat benefits.
- [map] Foundation deck: prioritizing clean early-game damage and block cards to preserve HP while leveraging Meat on the Bone for more aggressive pathing later.
### F2
- [card_reward] Foundation plan: Use frontload damage like Blade Dance to survive early elites and hallways. Looking for core scaling engines (Shiv or Poison). Take efficient damage and block.
### F3
- [event] Foundation deck: prioritizing clean early-game damage and block cards to preserve HP while leveraging Meat on the Bone for more aggressive pathing later.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. We have a Blade Dance but are not yet fully committed to shivs.
- [map] Foundation deck: prioritizing high-value early damage and block cards to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.
### F5
- [card_reward] Foundation plan: survive with frontload damage like Skewer while looking for a core scaling engine. We draw 9 cards on turn 1, so prioritize high-impact cards or energy generation to capitalize on early draw.
- [map] Foundation deck: prioritizing clean early-game damage and block cards to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.
### F6
- [card_reward] Foundation plan: survive with current frontload (Skewer, Blade Dance) while digging for a core engine piece like Finisher or Acrobatics. Take high-impact damage or premium draw; avoid narrow synergy pieces until the engine is clear.
### F7
- [rest_site] Foundation deck: prioritizing clean early-game damage (Skewer, Blade Dance) and block to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.
- [map] Foundation deck: prioritizing clean early-game damage and block to preserve HP while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.
### F8
- [map] Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.
### F9
- [card_reward] Foundation plan: Use our massive turn 1 draw (9 cards + Gambling Chip) to find scaling like Noxious Fumes or setup like Well-Laid Plans. Retain Skewer+ for big burst turns to push boss thresholds. Still looking for block scaling or a committed engine.
### F11
- [rest_site] Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Noxious Fumes for boss scaling and Meat on the Bone to path aggressively. Focus on upgrading key pieces like Fumes, Neutralize, and Well-Laid Plans while removing basic Strikes/Defends.
- [map] Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.
### F13
- [rest_site] Committed poison engine: stack Noxious Fumes and play Footwork to scale defensively while passive poison kills. Retain key cards with Well-Laid Plans to optimize block turns. Avoid bloated raw attacks; look for Corpse Explosion or Catalyst to accelerate boss fights.
- [map] Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.
### F14
- [card_reward] Committed poison plan: use Noxious Fumes+ and Deadly Poison to scale damage while surviving with Footwork+ and Dodge and Roll. Push Ceremonial Beast to 150 HP quickly, then use Dodge and Roll the turn before Ringing to mitigate its big attack.
- [map] Foundation deck: prioritizing clean early-game damage and block to preserve HP while leveraging Meat on the Bone for aggressive elite pathing.
### F15
- [hand_select] Retaining key damage pieces while Noxious Fumes and Poison do work is optimal for the Silent.
- [hand_select] Retaining Skewer+ for the next enemy phase ensures high frontload damage.
- [card_reward] Committed poison plan: rely on massive Turn 1 draw to set up Noxious Fumes+, Footwork+, and Well-Laid Plans. Stack poison while defending, and use Retain to hold key blocks for the Beast's Ringing turn.
### F16
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Retain key cards with Well-Laid Plans to optimize block turns. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
### F17
- [card_reward] Committed to poison/block scaling. Use Well-Laid Plans to set up Nightmare on Noxious Fumes+ for damage or Footwork+ for block in long fights. Focus on acquiring cheap card draw and mitigation. Avoid adding unnecessary attacks; rely on poison to kill.
### F18
- [event] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
- [map] Foundation deck: focusing on high-quality card rewards from hallway fights to prepare for elite hunting, leveraging Meat on the Bone for aggressive HP management and Pantograph for boss sustain.
### F19
- [hand_select] Massive Dexterity makes every basic block card premium. Retaining one ensures safety next turn.
- [hand_select] Following the defensive scaling plan; high Dexterity makes every Defend a priority for retention.
- [card_reward] Committed poison plan: use massive turn 1 draw and energy to set up Noxious Fumes, Footwork, and Nightmare, then play defensively while passive poison kills. Needs more card draw (Acrobatics/Backflip) for sustained cycling after turn 1; avoid adding any more raw attacks.
### F21
- [card_reward] Hybrid poison and burst damage plan: cycle aggressively to find Noxious Fumes and Footwork for scaling, or use Turn 1 energy for a massive Skewer+. Prioritize card draw and card removal to improve consistency; skip generic attacks.
- [map] Committed poison engine: scale via Footwork and Noxious Fumes while using Well-Laid Plans to line up blocks. Scaling is currently slow; aggressively hunting for Catalyst or Corpse Explosion to handle Act 2 Elites and the Boss.
### F22
- [hand_select] Prioritizing survival this turn by keeping Defend while maintaining scaling options.
- [card_reward] Committed to Fumes+/Footwork+ scaling with Nightmare. Use Pounce to cheat Nightmare's energy cost. Retain key pieces with WLP.
### F23
- [card_reward] Committed poison plan: rely on Noxious Fumes and poison cards to scale damage, while using block and draw (like Backflip+) to survive. Utilize our massive Turn 1 energy to set up powers and big Skewers. Needs more consistent block and poison scaling; avoid narrow synergies like shivs unless we find Envenom.
- [map] Committed poison engine: scale defense with Footwork and passive damage with Noxious Fumes. Use Well-Laid Plans to hold block for big hits. Priority is finding a Catalyst or Corpse Explosion to speed up kills while surviving through rest site pathing.
### F24
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; avoid elites until damage scaling improves.
### F25
- [hand_select] Prioritizing poison and high-efficiency block cards to leverage the 12 Dexterity and outlast the damage-capped enemies.
- [card_reward] Committed poison/defense plan: survive with frontloaded block and Footwork scaling while Noxious Fumes and poison cards slowly kill. Use Very Hot Cocoa and high draw to rapidly set up powers. Needs Catalyst or more focused poison; skip off-plan attacks.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; currently prioritizing safety via Rest Sites to leverage Meat on the Bone.
### F26
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
### F27
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw to set up powers quickly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
### F28
- [hand_select] Prioritizing full block this turn to preserve HP while Noxious Fumes and Poison (16) scale on the Entomancer.
- [hand_select] Focusing on poison scaling while minimizing Personal Hive triggers.
- [card_reward] Committed to passive poison (Noxious Fumes) and Dexterity stalling. Look for Catalyst or Corpse Explosion to accelerate poison damage, and retain efficient block/draw. Avoid bloating with non-poison attacks.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
### F29
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; prioritize finding these in card rewards and the upcoming shop.
### F30
- [card_reward] Foundation plan: survive with high turn-1 energy (Very Hot Cocoa) and draw (Gambling Chip, Bag of Prep) to set up scaling (Noxious Fumes, Nightmare) or burst (Skewer+). Seeking a more concrete scaling engine for Act 3.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale while defending. Current priority is finding a Catalyst or Corpse Explosion to accelerate kill speed and thinning the deck of basic strikes at shops.
### F32
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling.
### F33
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [card_select] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.
- [card_reward] Committed to poison/defense scaling. Focus on playing Noxious Fumes and Footwork, using Nightmare on key powers or block cards, and surviving while poison ramps. Prioritize removing Strikes to thin the deck.
### F34
- [event] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling. Delicate Frond gives free potions every combat, so use them aggressively.
- [map] Committed poison engine: scale via Footwork and Noxious Fumes while prioritizing defense. Current focus is deck thinning at shops and hunting for Catalyst or Corpse Explosion to solve multi-enemy fights and boss scaling.
### F35
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [hand_select] Focusing on surviving the 30 damage hit while Noxious Fumes scales.
- [card_reward] Committed to poison scaling. Setup huge turn 1 with Very Hot Cocoa (+4 energy) and Gambling Chip. Prioritize Nightmare on Bouncing Flask, Noxious Fumes, or Footwork depending on combat needs. Focus on removing basic Strikes and Defends to thin the deck.
- [map] Committed poison engine: scale via Noxious Fumes and Footwork while using Well-Laid Plans to set up Nightmare on key powers or defensive pieces. Prioritize shops for card removal and defensive upgrades to ensure the slow poison scaling has time to win.
### F36
- [event] Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers. Use the 3 Foul Potions on the F40 merchant for 300 Gold to fuel card removals and find key block/power upgrades. Delicate Frond keeps us safe with random potions in combats once our slots are empty again.
### F37
- [hand_select] Keep Ethereal curses in hand to exhaust them.
- [card_reward] Committed poison/Skewer plan: Retain key cards like Nightmare and Footwork+, burst enemies with Skewer+ early using Very Hot Cocoa energy, and let Noxious Fumes scale. Keep deck lean.
### F38
- [event] Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers. Meat on the Bone provides massive sustain, allowing us to hover safely around 33 HP and greed relics/upgrades instead of resting.
- [map] Committed poison engine: play Footwork and Noxious Fumes to scale while holding Nightmare for key powers with Well-Laid Plans. Currently in survival mode due to low HP; prioritize events and shops to find sustain or defensive upgrades, relying on Meat on the Bone and Pantograph to reach the boss.
### F39
- [hand_select] Conserving HP and setting up the Nightmare/Poison engine is the priority.
- [hand_select] Bouncing Flask is the priority target for Nightmare next turn. Retaining Expertise+ ensures I have draw power to supplement the Nightmare copies.
- [hand_select] Prioritizing defensive scaling (Footwork) over immediate poison (Bouncing Flask) or draw (Expertise) because HP is low (19/66) and the boss's incoming damage scales quickly.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
### F42
- [hand_select] Prioritizing full block with Defends to preserve HP while Noxious Fumes and future Poison cards (like Bouncing Flask) scale.
- [hand_select] Well-Laid Plans level 2 allows retaining 1 card. Bouncing Flask is the highest value card here for the long-term poison engine.
- [hand_select] Discarding Strike to keep poison cards. I need to stack poison to leverage the passive damage while keeping HP high.
- [hand_select] Prioritizing survival over chip damage; Strike does negligible damage compared to the poison engine.
- [card_select] Committed poison plan: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [hand_select] Retaining Bouncing Flask at the end of turn is the priority to start stacking poison on the Berserker.
- [card_reward] Committed poison plan: accelerate poison stacks with Bubble Bubble and Bouncing Flask while hiding behind massive Dexterity from Footworks. Keep the deck focused on cycle and poison; avoid taking any more direct damage attacks.
- [map] Committed poison engine: utilize Well-Laid Plans to setup Nightmare on Noxious Fumes or Footwork for scaling. Prioritize defensive consistency and let poison tick down enemies; avoid Act 3 elites as they pose a high risk of run-ending burst damage.
### F43
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Use Well-Laid Plans to hold Nightmare for key powers or block cards. Razor Tooth automatically upgrades Skills/Attacks upon play, so focus future permanent upgrades on Powers like Footwork.
### F44
- [card_select] Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers.
- [card_reward] Committed poison/dexterity plan: use Gambling Chip to dig for Footworks and Fumes turn 1, stack poison and block. Nightmare can copy Footwork for invincible block or Bubble Bubble for lethal poison. Skip unnecessary attacks to keep the deck as lean as possible given its current size.
### F45
- [hand_select] Copying Footwork ensures we can out-scale the Fabricator's summons and maintain the HP conservation strategy.
- [hand_select] Conserving HP by prioritizing defensive setup while digging for Noxious Fumes/Nightmare.
- [hand_select] Building up Dexterity and Poison is the win condition for this deck.
- [hand_select] With Well-Laid Plans and high Dexterity, we can afford to keep high-value cards for the right moment.
- [hand_select] Focusing on scaling poison on the Fabricator to end the fight quickly while the minions are busy with non-attacking actions.
- [card_reward] Committed poison plan: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers or burst damage. Keep deck thin from here on to draw combo pieces faster.
- [map] Committed poison engine: scale via Noxious Fumes and Footwork while using Well-Laid Plans to nightmare key powers; focus on card removal and high-value block at the shop to ensure the engine has time to ramp up.
### F46
- [card_select] Committed poison/dexterity plan: scale defense with multiple Footworks and damage with Noxious Fumes and targeted poison. Use Nightmare on Footwork or strong block/draw to out-scale bosses. Remove remaining Strikes.
### F47
- [rest_site] Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Use Well-Laid Plans to hold Nightmare for key powers or block cards. Razor Tooth automatically upgrades Skills/Attacks upon play, so permanent upgrades must focus on Powers like Footwork.
### F48
- [card_select] Committed poison plan: rely on Noxious Fumes, Bouncing Flask, and Deadly Poison to stack damage, while scaling Dexterity with Footwork to survive. Focus on surviving with high block and let passive poison do the work. Skip off-plan attacks.
- [hand_select] Focus on applying Weak and stacking Block while Poison ticks up.
- [hand_select] Well-Laid Plans+ allows retaining 2 cards. These cards don't cost draw space, so there's no reason not to take them.
- [hand_select] Surviving this turn is priority 1. I have 9 Dex, so Defend+ is extremely high value (17 block).
- [hand_select] HP is critical (4/58); keeping Nightmare+ for potential block generation or Dexterity scaling via Footwork is vital.
- [hand_select] Surviving this turn is the absolute priority. With Dexterity 9, Survivor+ gives 20, Backflip+ gives 17, and Defend+ gives 17, totaling 54 block, which covers the 49 damage. Nightmare+ must be kept to potentially copy block or poison next turn.
- [hand_select] Total block potential this turn: 15 (current) + 17 (Blur+) + 17 (Defend+) + 17 (Defend+) = 66 Block. This covers the 56 damage perfectly and ensures Block carries over due to Blur+.
- [hand_select] With Blur active and 66 Block, we are safe from the 56 incoming damage. Retaining these cards provides more options for the next turn while still drawing 6 new cards (5 draw + 1 Tools).
- [hand_select] Critical survival turn.
- [hand_select] Enemy is Intangible and not attacking this turn, but we must maintain high block/health because our HP is critical (4/58).
- [hand_select] Discarding Strike to keep scaling and defensive options. Priority is setting up the Nightmare combo while maintaining high block stacks.
- [hand_select] Enemy is Intangible 1. I need to stack enough block to survive 35 damage (I have 15, need 20 more).
- [hand_select] Enemy is Intangible; don't waste energy on raw damage. Focus on survival and setting up the next cycle.
- [hand_select] Enemy loses Intangible next turn. Flask + Poison ticks will likely end the fight.

### Combat Decision Digest (22 combats)
F2 [monster] Fuzzy Wurm Crawler (6R, HP 56->56, loss=0, WIN)
  R1[Fuzzy Wurm Crawler: Atk(4)]: Strike(6dmg)->Strike(6dmg)->Defend(+5blk) | dealt=12 taken=0
  R2[Fuzzy Wurm Crawler: Buff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg) | dealt=15 taken=0
  R3[Fuzzy Wurm Crawler: Atk(11)]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R4[Fuzzy Wurm Crawler: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=0
  R5[Fuzzy Wurm Crawler: Buff]: Strike(6dmg)->Strike(6dmg)->Defend(+5blk) | dealt=12 taken=0
  R6[Fuzzy Wurm Crawler: Atk(18)]: Neutralize | dealt=0 taken=0

F5 [monster] multi:Leaf Slime (S)+Twig Slime (M)+Twig Slime (S) (3R, HP 56->55, loss=1, WIN)
  R1[Twig Slime (S): Atk(4)+Twig Slime (M): StatusCard(1)+Leaf Slime (S): Atk(3)]: Neutralize(3dmg,1+Weak(1))->Strike->Blade Dance(exhaust:1)->Peck(6dmg)->Shiv(4dmg,exhaust:1)->Shiv->Shiv(4dmg) | dealt=26 taken=0
  R2[Twig Slime (M): Atk(11)]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=1
  R3[Twig Slime (M): Atk(11)]: Strike(6dmg)->Strike(6dmg)->Strike | dealt=12 taken=0

F6 [monster] Nibbit (4R, HP 55->55, loss=0, WIN)
  R1[Nibbit: Atk(12)]: Peck(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R2[Nibbit: Atk(6), Defend]: Defend(+5blk)->Defend(+5blk)->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg) | dealt=12 taken=0
  R3[Nibbit: Buff]: Neutralize(1+Weak(1))->Skewer(22dmg) | dealt=22 taken=0
  R4[Nibbit: Atk(14)]: Strike | dealt=0 taken=0

F9 [elite] Byrdonis (3R, HP 55->48, loss=7, WIN)
  R1[Byrdonis: Atk(17)]: Defend(+5blk)->Blade Dance(exhaust:1)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Shiv(9dmg)->Peck(21dmg) | dealt=48 taken=0
  R2[Byrdonis: Atk(4x3=12)]: Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=7
  R3[Byrdonis: Atk(19)]: Neutralize(3dmg,1+Weak(1))->Skewer+ | dealt=3 taken=0

F14 [monster] multi:Slithering Strangler+Twig Slime (M) (4R, HP 48->40, loss=8, WIN)
  R1[Twig Slime (M): StatusCard(1)+Slithering Strangler: Debuff]: Blade Dance(exhaust:1)->Skewer+(22dmg)->Shiv(exhaust:1)->Shiv(4dmg) | dealt=30 taken=0
  R2[Slithering Strangler: Atk(12)]: Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Neutralize(3dmg,1+Weak(1))->Deadly Poison(1+Poison(5))->Strike(6dmg) | dealt=9 taken=5
  R3[Slithering Strangler: Debuff]: Poisoned Stab(6dmg,1Poison(7→10))->Strike(6dmg)->Strike(6dmg) | dealt=18 taken=3
  R4[Slithering Strangler: Atk(7), Defend]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0

F15 [elite] Phrog Parasite (7R, HP 40->34, loss=6, WIN)
  R1[Phrog Parasite: StatusCard(3)]: Neutralize(3dmg,1+Weak(1))->Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Footwork+(power:+Dexterity(3))->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=3 taken=0
  R2[Phrog Parasite: Atk(4x4=16)]: Dodge and Roll(+7blk,power:+Block Next Turn(7))->Deadly Poison(1Poison(3→8))->Poisoned Stab(6dmg,1Poison(8→11)) | dealt=6 taken=9
  R3[Phrog Parasite: StatusCard(3)]: Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Peck(6dmg)->Strike(6dmg) | dealt=24 taken=0
  R4[Phrog Parasite: Atk(4x4=16)]: Defend(+8blk)->Defend(+8blk)->Defend(+8blk) | dealt=0 taken=0
  R5[Wriggler: Stun+Wriggler: Stun+Wriggler: Stun+Wriggler: Stun]: Skewer+ | dealt=0 taken=9
  R6[Wriggler: Buff, StatusCard(1)+Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)]: Survivor(+11blk)->Poisoned Stab->Deadly Poison(1Poison(5→10)) | dealt=0 taken=0
  R7[Wriggler: Atk(8)+Wriggler: Buff, StatusCard(1)+Wriggler: Atk(8)]: Strike*2->Defend(+8blk) | dealt=0 taken=0

F17 [boss] Ceremonial Beast (9R, HP 59->41, loss=18, WIN)
  R1[Ceremonial Beast: Buff]: Footwork+(+7blk,power:+Dexterity(3))->Neutralize+(4dmg,1+Weak(2))->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Skewer+(11dmg) | dealt=27 taken=0
  R2[Ceremonial Beast: Atk(13), Buff]: Well-Laid Plans(power:+Well-Laid Plans(1))->Noxious Fumes+(power:+Noxious Fumes(3))->Defend(+8blk) | dealt=0 taken=5
  R3[Ceremonial Beast: Atk(20), Buff]: Deadly Poison(1Poison(3→8))->Peck(6dmg)->Survivor(+11blk) | dealt=6 taken=9
  R4[Ceremonial Beast: Atk(22), Buff]: Poisoned Stab(6dmg,1Poison(10→13))->Defend(+8blk)->Survivor(+11blk) | dealt=6 taken=3
  R5[Ceremonial Beast: Atk(24), Buff]: Skewer+(55dmg,2-Plow,-Strength) | dealt=55 taken=0
  R6[Ceremonial Beast: Debuff]: Neutralize+(4dmg,1+Weak(2))->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Peck(6dmg)->Defend(+8blk) | dealt=10 taken=0
  R7[Ceremonial Beast: Atk(11)]: Defend(+8blk) | dealt=0 taken=0
  R8[Ceremonial Beast: Atk(17), Buff]: Neutralize+(4dmg,1+Weak(2))->Deadly Poison(1Poison(21→26))->Strike(6dmg)->Survivor(+11blk) | dealt=10 taken=1
  R9[Ceremonial Beast: Debuff]: Skewer+(33dmg) | dealt=33 taken=0

F19 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (6R, HP 64->59, loss=5, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Nightmare->Neutralize+->Footwork+(+7blk,power:+Dexterity(3))->Deadly Poison->Defend(+8blk)->Strike | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)]: Footwork+(power:Dexterity(3→6))->Footwork+(power:Dexterity(6→9))->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=0 taken=5
  R3[Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)+Exoskeleton: Atk(10)]: Strike->Footwork+(power:Dexterity(9→12))->Dodge and Roll(+16blk,power:+Block Next Turn(16)) | dealt=0 taken=0
  R4[Exoskeleton: Atk(3x3=9)+Exoskeleton: Buff]: Noxious Fumes+(power:+Noxious Fumes(3))->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Skewer+(9dmg) | dealt=21 taken=0
  R5[Exoskeleton: Atk(10)+Exoskeleton: Atk(12)]: Neutralize+->Defend(+17blk)->Deadly Poison->Peck | dealt=0 taken=0
  R6[Exoskeleton: Buff]: Skewer+(power:-Dexterity,power:-Well-Laid Plans,power:-Noxious Fumes) | dealt=0 taken=0

F21 [monster] multi:Bowlbug (Nectar)+Bowlbug (Rock) (5R, HP 59->59, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(3)]: Well-Laid Plans(+7blk,power:+Well-Laid Plans(1))->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Dodge and Roll(+4blk,power:Block Next Turn(4→8))->Poisoned Stab(6dmg,1+Poison(3))->Skewer+ | dealt=38 taken=0
  R2[Bowlbug (Rock): Stun]: Acrobatics->Deadly Poison(1+Poison(5))->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Deflect(+4blk) | dealt=12 taken=0
  R3[Bowlbug (Rock): Atk(15)]: Footwork+(power:+Dexterity(3))->Survivor(+11blk)->Defend(+8blk) | dealt=0 taken=0
  R4[Bowlbug (Rock): Stun]: Noxious Fumes+(power:+Noxious Fumes(3))->Peck(6dmg)->Strike(6dmg)->Neutralize+(4dmg,1+Weak(2)) | dealt=16 taken=0
  R5[Bowlbug (Rock): Atk(11)]: Skewer+(power:-Well-Laid Plans,power:-Dexterity,power:-Noxious Fumes) | dealt=0 taken=0

F22 [monster] The Obscura (10R, HP 59->22, loss=37, WIN)
  R1[The Obscura: Summon]: Footwork+(+7blk,power:+Dexterity(3))->Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Survivor(+11blk)->Defend(+8blk)->Defend(+8blk)->Deflect(+7blk) | dealt=10 taken=0
  R2[Parafright: Atk(16)+The Obscura: Buff]: Well-Laid Plans(power:+Well-Laid Plans(1))->Defend(+8blk)->Poisoned Stab(6dmg,1+Poison(3)) | dealt=6 taken=1
  R3[Parafright: Atk(19)+The Obscura: Atk(9), Defend]: Backflip(+8blk)->Acrobatics->Defend(+8blk) | dealt=0 taken=12
  R4[Parafright: Atk(19)+The Obscura: Buff]: Noxious Fumes+(power:+Noxious Fumes(3))->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk) | dealt=0 taken=4
  R5[Parafright: Atk(22)+The Obscura: Atk(16)]: Neutralize+(4dmg,1+Weak(2))->Defend(+8blk)->Deadly Poison(1Poison(3→8))->Strike(6dmg) | dealt=10 taken=17
  R6[Parafright: Atk(16)+The Obscura: Atk(12), Defend]: Deflect(+7blk)->Defend(+8blk)->Poisoned Stab(6dmg,1Poison(10→13))->Skewer+(11dmg) | dealt=17 taken=0
  R7[Parafright: Atk(22)+The Obscura: Atk(16)]: Backflip(+8blk)->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk) | dealt=0 taken=15
  R8[Parafright: Atk(22)+The Obscura: Buff]: Acrobatics->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Survivor(+11blk) | dealt=0 taken=0
  R9[Parafright: Atk(25)+The Obscura: Atk(19)]: Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Deflect(+7blk)->Backflip(+8blk)->Dodge and Roll(+7blk,power:+Block Next Turn(7)) | dealt=12 taken=0
  R10[Parafright: Atk(25)+The Obscura: Buff]: Strike(6dmg)->Strike(6dmg)->Peck(21dmg,1-Poison) | dealt=12 taken=0

F23 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (10R, HP 22->13, loss=9, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Pounce(12dmg,power:+Free Skill(1))->Survivor(+8blk,power:-Free Skill)->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Defend(+5blk)->Strike(6dmg)->Poisoned Stab(6dmg,1+Poison(3))->Deadly Poison(1Poison(3→8)) | dealt=24 taken=0
  R2[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Blade Dance(exhaust:1)->Shiv(3dmg,exhaust:1)->Shiv(3dmg)->Shiv(3dmg)->Strike(4dmg)->Strike(4dmg) | dealt=17 taken=0
  R3[Bowlbug (Rock): Atk(15)+Slumbering Beetle: Sleep]: Footwork+(+7blk,power:+Dexterity(3))->Neutralize+(4dmg,1+Weak(2))->Deflect(+7blk)->Defend(+8blk) | dealt=4 taken=0
  R4[Bowlbug (Rock): Stun+Slumbering Beetle: Atk(16), Buff]: Defend(+8blk)->Noxious Fumes+(power:+Noxious Fumes(3))->Skewer+(11dmg) | dealt=11 taken=8
  R5[Bowlbug (Rock): Atk(15)+Slumbering Beetle: Atk(18), Buff]: Backflip(+8blk)->Deflect(+7blk)->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk) | dealt=0 taken=3
  R6[Bowlbug (Rock): Stun+Slumbering Beetle: Atk(20), Buff]: Neutralize+(4dmg,1+Weak(2))->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk)->Defend(+8blk) | dealt=4 taken=0
  R7[Bowlbug (Rock): Atk(15)+Slumbering Beetle: Atk(16), Buff]: Pounce(power:+Free Skill(1))->Acrobatics(power:-Free Skill)->Defend(+8blk) | dealt=8 taken=1
  R8[Slumbering Beetle: Atk(24), Buff]: Poisoned Stab(6dmg,1Poison(9→12))->Defend(+8blk)->Survivor(+11blk) | dealt=6 taken=5
  R9[Slumbering Beetle: Atk(26), Buff]: Neutralize+(4dmg,1+Weak(2))->Backflip(+8blk)->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Skewer+(11dmg) | dealt=15 taken=4
  R10[Slumbering Beetle: Atk(21), Buff]: Peck(6dmg)->Defend(+8blk)->Defend(+8blk) | dealt=6 taken=0

F25 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (6R, HP 34->34, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Nightmare->Footwork+(+7blk,power:+Dexterity(3))->Noxious Fumes+(power:+Noxious Fumes(3))->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk) | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)+Exoskeleton: Buff]: Footwork+(power:Dexterity(3→6))->Footwork+(power:Dexterity(6→9))->Footwork+(power:Dexterity(9→12))->Deflect(+16blk) | dealt=0 taken=0
  R3[Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)+Exoskeleton: Atk(10)+Exoskeleton: Atk(3x3=9)]: Acrobatics->Dodge and Roll(+16blk,power:+Block Next Turn(16))->Deadly Poison | dealt=0 taken=12
  R4[Exoskeleton: Atk(10)+Exoskeleton: Atk(10)+Exoskeleton: Buff+Exoskeleton: Atk(10)]: Pounce(9dmg,power:+Free Skill(1))->Neutralize+(4dmg,1+Weak(2))->Blade Dance(power:-Free Skill,exhaust:1)->Shiv(exhaust:1)->Shiv*2->Defend(+17blk) | dealt=13 taken=0
  R5[Exoskeleton: Buff+Exoskeleton: Atk(12)]: Backflip+(+20blk)->Strike(6dmg)->Deflect(+16blk)->Acrobatics | dealt=6 taken=0
  R6[Exoskeleton: Atk(12)]: Poisoned Stab(power:-Dexterity,power:-Noxious Fumes) | dealt=0 taken=0

F28 [elite] Entomancer (8R, HP 55->46, loss=9, WIN)
  R1[Entomancer: Atk(3x7=21)]: Footwork+(+7blk,power:+Dexterity(3))->Noxious Fumes+(power:+Noxious Fumes(3))->Defend(+8blk)->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Acrobatics->Backflip+(+11blk)->Neutralize+(4dmg,1+Weak(2))->Poisoned Stab(6dmg,1+Poison(3)) | dealt=10 taken=0
  R2[Entomancer: Atk(13)]: Deflect(+7blk)->Expertise+->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Defend(+8blk) | dealt=0 taken=0
  R3[Entomancer: Buff]: Backflip(+8blk)->Pounce(12dmg,power:+Free Skill(1)) | dealt=12 taken=0
  R4[Entomancer: Atk(4x7=28)]: Deadly Poison(power:-Free Skill,1Poison(9→14))->Defend(+8blk)->Defend+(+11blk)->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=0 taken=9
  R5[Entomancer: Atk(19)]: Acrobatics+->Neutralize+(4dmg,1+Weak(2))->Dodge and Roll+(+9blk,power:+Block Next Turn(9))->Survivor(+11blk) | dealt=4 taken=0
  R6[Entomancer: Buff]: Pounce+(18dmg,power:+Free Skill(1))->Backflip+(+11blk,power:-Free Skill)->Dodge and Roll+(+9blk,power:+Block Next Turn(9)) | dealt=18 taken=0
  R7[Entomancer: Atk(5x7=35)]: Deflect+(+10blk)->Backflip+(+11blk)->Defend(+8blk) | dealt=0 taken=0
  R8[Entomancer: Atk(20)]: Defend(+8blk)->Defend+(+11blk) | dealt=0 taken=0

F30 [monster] multi:Myte+Myte (6R, HP 46->41, loss=5, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Footwork(+7blk,power:+Dexterity(2))->Peck(6dmg)->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Acrobatics->Noxious Fumes+(power:+Noxious Fumes(3))->Poisoned Stab(6dmg,1+Poison(3))->Backflip(+7blk) | dealt=24 taken=0
  R2[Myte: Atk(13)+Myte: StatusCard(2)]: Defend(+7blk)->Dodge and Roll(+6blk,power:+Block Next Turn(6))->Toxic(exhaust:1) | dealt=0 taken=5
  R3[Myte: Atk(4), Buff+Myte: Atk(15)]: Footwork+(power:Dexterity(2→5))->Backflip+(+13blk)->Neutralize+(4dmg,1+Weak(2))->Defend(+10blk) | dealt=4 taken=0
  R4[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Deflect(+9blk)->Skewer+(2Poison(9→7),-Weak) | dealt=0 taken=0
  R5[Myte: Atk(15)]: Deflect+(+12blk)->Backflip+(+13blk)->Dodge and Roll(+9blk,power:+Block Next Turn(9))->Peck+(8dmg) | dealt=8 taken=0
  R6[Myte: Atk(6), Buff]: Poisoned Stab+(8dmg,1Poison(11→15))->Deadly Poison(1Poison(15→20))->Skewer+(11dmg) | dealt=19 taken=0

F33 [boss] Knowledge Demon (12R, HP 66->37, loss=29, WIN)
  R1[Knowledge Demon: Debuff]: Prepared->Backflip(+5blk)->Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Slice(8dmg)->Poisoned Stab(8dmg,1+Poison(3))->Peck(12dmg)->Skewer+(39dmg) | dealt=67 taken=0
  R2[Knowledge Demon: Atk(17)]: Expertise+->Backflip+(+8blk)->Footwork(power:+Dexterity(2)) | dealt=0 taken=15
  R3[Knowledge Demon: Atk(8x3=24)]: Deflect(+11blk)->Defend(+12blk)->Defend(+12blk)->Blade Dance(exhaust:1)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Shiv(6dmg) | dealt=18 taken=0
  R4[Knowledge Demon: Atk(11), Heal, Buff]: Footwork+(power:Dexterity(2→5))->Defend(+10blk)->Deadly Poison(1Poison(9→14)) | dealt=0 taken=7
  R5[Knowledge Demon: Debuff]: Pounce(14dmg,power:+Free Skill(1))->Nightmare+(power:-Free Skill)->Neutralize+(6dmg,1+Weak(2))->Slice+(11dmg)->Strike(8dmg) | dealt=39 taken=6
  R6[Knowledge Demon: Atk(14)]: Neutralize+(6dmg,1Weak(1→3))->Dodge and Roll(+9blk,power:+Block Next Turn(9))->Defend(+10blk) | dealt=6 taken=1
  R7[Knowledge Demon: Atk(7x3=21)]: Acrobatics->Dodge and Roll(+9blk,power:+Block Next Turn(9))->Defend(+10blk) | dealt=0 taken=0
  R8[Knowledge Demon: Atk(9), Heal, Buff]: Backflip+(+13blk)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Poisoned Stab+(10dmg,1Poison(22→26)) | dealt=10 taken=0
  R9[Knowledge Demon: Debuff]: Deadly Poison+(1Poison(28→35))->Dodge and Roll+(+11blk,power:+Block Next Turn(11))->Backflip+(+13blk) | dealt=0 taken=0
  R10[Knowledge Demon: Atk(21)]: Neutralize+(6dmg,1+Weak(2))->Dodge and Roll+(+11blk,power:+Block Next Turn(11))->Poisoned Stab+(10dmg,1Poison(37→41)) | dealt=16 taken=7
  R11[Knowledge Demon: Atk(9x3=27)]: Pounce+(20dmg,power:+Free Skill(1))->Deflect+(+12blk,power:-Free Skill)->Defend+(+13blk) | dealt=20 taken=5
  R12[Knowledge Demon: Atk(15), Heal, Buff]: Peck+(16dmg)->Slice+(11dmg)->Strike(power:-Strength,power:-Noxious Fumes,power:-Disintegration,power:-Dexterity,power:-Sloth,power:-Well-Laid Plans) | dealt=27 taken=0

F35 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (5R, HP 63->50, loss=13, WIN)
  R1[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff+Scroll of Biting: Atk(14)]: Footwork(+7blk,power:+Dexterity(2))->Noxious Fumes+(power:+Noxious Fumes(3))->Neutralize+(4dmg,1+Weak(2))->Backflip(+7blk)->Defend(+7blk)->Tools of the Trade(power:+Tools of the Trade(1))->Deadly Poison->Skewer+ | dealt=4 taken=0
  R2[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Buff]: Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv*2->Strike->Deflect(+6blk)->Backflip+(+10blk)->Slice(6dmg) | dealt=6 taken=0
  R3[Scroll of Biting: Atk(16)+Scroll of Biting: Atk(7x2=14)]: Accelerant(power:+Accelerant(1))->Acrobatics->Survivor(+10blk)->Defend(+7blk) | dealt=0 taken=13
  R4[Scroll of Biting: Buff+Scroll of Biting: Atk(7x2=14)]: Slice+(9dmg)->Footwork+(power:Dexterity(2→5))->Dodge and Roll(+9blk,power:+Block Next Turn(9))->Defend+(+13blk) | dealt=9 taken=0
  R5[Scroll of Biting: Atk(9x2=18)]: Skewer+(power:-Dexterity,power:-Noxious Fumes,power:-Tools of the Trade,power:-Accelerant) | dealt=0 taken=0

F37 [monster] Devoted Sculptor (6R, HP 66->30, loss=36, WIN)
  R1[Devoted Sculptor: Buff]: Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Slice(6dmg)->Poisoned Stab(6dmg,1+Poison(3))->Prepared->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Peck(6dmg)->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Dodge and Roll(+4blk,power:Block Next Turn(4→8))->Expertise+ | dealt=30 taken=0
  R2[Devoted Sculptor: Atk(12)]: Neutralize+(4dmg,1+Weak(2))->Acrobatics->Backflip(+5blk)->Deadly Poison(1Poison(5→10)) | dealt=4 taken=0
  R3[Devoted Sculptor: Atk(15)]: Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=10
  R4[Devoted Sculptor: Atk(30)]: Footwork(power:+Dexterity(2))->Defend(+7blk)->Defend(+7blk)->Deflect(+6blk) | dealt=0 taken=10
  R5[Devoted Sculptor: Atk(39)]: Footwork+(power:Dexterity(2→5))->Defend(+10blk)->Survivor(+13blk) | dealt=0 taken=16
  R6[Devoted Sculptor: Atk(48)]: Acrobatics+->Strike+(power:-Noxious Fumes,power:-Dexterity) | dealt=12 taken=0

F39 [monster] Owl Magistrate (11R, HP 19->31, loss=0, WIN)
  R1[Owl Magistrate: Atk(16)]: Nightmare+->Footwork+(+7blk,power:+Dexterity(3))->Backflip(+8blk)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Dodge and Roll(+7blk,power:+Block Next Turn(7))->Acrobatics | dealt=0 taken=0
  R2[Owl Magistrate: Atk(4x6=24)]: Footwork+(power:Dexterity(3→6))->Deflect(+10blk)->Dodge and Roll(+10blk,power:+Block Next Turn(10))->Noxious Fumes+(power:+Noxious Fumes(3)) | dealt=0 taken=0
  R3[Owl Magistrate: Buff]: Footwork+(power:Dexterity(6→9))->Footwork+(power:Dexterity(9→12))->Neutralize+(4dmg,1+Weak(2))->Slice(6dmg)->Peck(6dmg) | dealt=16 taken=0
  R4[Owl Magistrate: Atk(24), Debuff]: Footwork(power:Dexterity(12→14))->Backflip+(+22blk)->Defend(+19blk) | dealt=0 taken=0
  R5[Owl Magistrate: Atk(24)]: Defend(+19blk)->Defend(+19blk)->Deadly Poison(1Poison(7→12)) | dealt=0 taken=0
  R6[Owl Magistrate: Atk(6x6=36)]: Slice+(9dmg)->Dodge and Roll+(+20blk,power:+Block Next Turn(20))->Dodge and Roll+(+20blk,power:Block Next Turn(20→40))->Deadly Poison+(1Poison(14→21))->Prepared | dealt=9 taken=0
  R7[Owl Magistrate: Buff]: Backflip+(+22blk)->Bouncing Flask(1Poison(23→32)) | dealt=0 taken=0
  R8[Owl Magistrate: Atk(49), Debuff]: Backflip+(+22blk)->Defend(+19blk)->Defend+(+22blk) | dealt=0 taken=0
  R9[Owl Magistrate: Atk(24)]: Neutralize+(4dmg,1+Weak(2))->Defend+(+22blk)->Defend(+19blk)->Survivor(+22blk) | dealt=4 taken=0
  R10[Owl Magistrate: Atk(4x6=24)]: Deflect+(+21blk)->Defend+(+22blk)->Defend(+19blk)->Dodge and Roll+(+20blk,power:+Block Next Turn(20)) | dealt=0 taken=0
  R11[Owl Magistrate: Buff]: Neutralize+(4dmg,1+Weak(2))->Skewer+(power:-Dexterity,power:-Well-Laid Plans,power:-Noxious Fumes,power:-Vulnerable) | dealt=4 taken=0

F42 [monster] Slimed Berserker (10R, HP 31->39, loss=0, WIN)
  R1[Slimed Berserker: StatusCard(10)]: Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Poisoned Stab(6dmg,1+Poison(3))->Deflect(+5blk)->Backflip+(+9blk)->Strike(6dmg)->Strike(6dmg)->Survivor(+9blk) | dealt=18 taken=0
  R2[Slimed Berserker: Atk(4x4=16)]: Neutralize+(4dmg,1+Weak(2))->Acrobatics->Defend(+6blk)->Defend(+6blk) | dealt=4 taken=0
  R3[Slimed Berserker: Debuff, Buff]: Footwork(power:Dexterity(1→3))->Tools of the Trade(power:+Tools of the Trade(1))->Prepared->Deadly Poison(1Poison(7→12)) | dealt=0 taken=0
  R4[Slimed Berserker: Atk(33)]: Footwork+(power:Dexterity(3→6))->Deflect(+10blk)->Defend(+11blk)->Defend(+11blk) | dealt=0 taken=1
  R5[Slimed Berserker: StatusCard(10)]: Bouncing Flask(1Poison(16→25))->Backflip(+11blk) | dealt=0 taken=0
  R6[Slimed Berserker: Atk(7x4=28)]: Footwork(power:Dexterity(6→8))->Dodge and Roll(+12blk,power:+Block Next Turn(12))->Defend(+13blk)->Slice(4dmg) | dealt=4 taken=3
  R7[Slimed Berserker: Debuff, Buff]: Nightmare+->Slimed(exhaust:1)->Deflect+(+15blk) | dealt=0 taken=0
  R8[Slimed Berserker: Atk(36)]: Deflect+(+15blk)->Deflect+(+15blk)->Deflect+(+15blk)->Deadly Poison+(1Poison(31→38))->Prepared+->Deflect+(+15blk)->Acrobatics+->Neutralize+(3dmg,1+Weak(2))->Dodge and Roll(+12blk,power:+Block Next Turn(12)) | dealt=3 taken=0
  R9[Slimed Berserker: StatusCard(10)]: Bouncing Flask+(1Poison(40→52))->Skewer+(8dmg) | dealt=8 taken=0
  R10[Slimed Berserker: Atk(10x4=40)]: Neutralize+(3dmg,1+Weak(2))->Defend(+13blk)->Defend+(+16blk)->Survivor+(+19blk) | dealt=3 taken=0

F44 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting+Scroll of Biting (6R, HP 66->49, loss=17, WIN)
  R1[Scroll of Biting: Buff+Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff]: Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv*2->Acrobatics->Neutralize+->Poisoned Stab->Bubble Bubble->Survivor(+9blk)->Defend(+6blk) | dealt=0 taken=0
  R2[Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Atk(7x2=14)]: Defend(+6blk)->Defend(+6blk)->Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Slice(9dmg)->Skewer+(2-Strength,-Vulnerable) | dealt=19 taken=12
  R3[Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Atk(14)]: Footwork(power:Dexterity(1→3))->Deflect(+7blk)->Backflip(+8blk)->Defend(+8blk) | dealt=0 taken=5
  R4[Scroll of Biting: Atk(16)+Scroll of Biting: Buff]: Pounce(power:+Free Skill(1))->Backflip+(+11blk,power:-Free Skill)->Dodge and Roll(+7blk,power:+Block Next Turn(7)) | dealt=0 taken=0
  R5[Scroll of Biting: Buff+Scroll of Biting: Atk(7x2=14)]: Backflip+(+11blk)->Prepared->Skewer+(7dmg) | dealt=7 taken=0
  R6[Scroll of Biting: Atk(9x2=18)]: Poisoned Stab+(power:-Dexterity,power:-Noxious Fumes) | dealt=0 taken=0

F45 [monster] Fabricator (13R, HP 49->37, loss=12, WIN)
  R1[Fabricator: Summon]: Dodge and Roll(+5blk,power:+Block Next Turn(5))->Nightmare+->Footwork(+7blk,power:Dexterity(1→3))->Prepared->Backflip(+8blk)->Acrobatics->Neutralize+(4dmg,1+Weak(2))->Peck(6dmg) | dealt=10 taken=0
  R2[Guardbot: Defend+Stabbot: Atk(11), Debuff+Fabricator: Atk(13), Summon]: Footwork(power:Dexterity(3→5))->Defend(+10blk)->Skewer+ | dealt=41 taken=0
  R3[Guardbot: Defend+Zapbot: Atk(16)+Fabricator: Summon]: Footwork(power:Dexterity(5→7))->Deflect(+11blk)->Expertise+->Dodge and Roll(+11blk,power:+Block Next Turn(11)) | dealt=0 taken=0
  R4[Guardbot: Defend+Zapbot: Atk(18)+Fabricator: Atk(11)+Noisebot: StatusCard(2)+Zapbot: Atk(16)]: Pounce(power:+Free Skill(1))->Slice->Footwork+(power:Dexterity(7→10))->Defend(+15blk,power:-Free Skill) | dealt=0 taken=1
  R5[Guardbot: Defend+Fabricator: Atk(11)+Noisebot: StatusCard(2)+Zapbot: Atk(18)]: Poisoned Stab(6dmg,1Poison(6→9))->Strike(6dmg)->Strike(6dmg) | dealt=18 taken=11
  R6[Guardbot: Defend+Fabricator: Atk(18), Summon+Noisebot: StatusCard(2)]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Dodge and Roll+(+16blk,power:+Block Next Turn(16))->Expertise+->Neutralize+(1+Weak(2)) | dealt=0 taken=0
  R7[Guardbot: Defend+Stabbot: Atk(11), Debuff+Fabricator: Atk(8)+Noisebot: StatusCard(2)]: Footwork(power:Dexterity(10→12))->Dodge and Roll+(+18blk,power:+Block Next Turn(18))->Slice+(9dmg)->Peck+(8dmg) | dealt=17 taken=0
  R8[Guardbot: Defend+Stabbot: Atk(11), Debuff+Fabricator: Atk(11)+Noisebot: StatusCard(2)]: Strike->Noxious Fumes+(power:+Noxious Fumes(3))->Acrobatics+ | dealt=6 taken=0
  R9[Guardbot: Defend+Fabricator: Atk(18), Summon+Noisebot: StatusCard(2)]: Backflip+(+20blk)->Bubble Bubble(1Poison(3→12))->Footwork(power:Dexterity(12→14)) | dealt=0 taken=0
  R10[Guardbot: Defend+Zapbot: Atk(16)+Fabricator: Atk(11)+Noisebot: StatusCard(2)]: Pounce+(18dmg,power:+Free Skill(1))->Backflip+(+22blk,power:-Free Skill)->Deflect+(+21blk)->Prepared+->Tools of the Trade(power:+Tools of the Trade(1)) | dealt=18 taken=0
  R11[Guardbot: Defend+Fabricator: Summon+Noisebot: StatusCard(2)]: Bubble Bubble+(1Poison(16→28))->Deadly Poison(1Poison(28→33))->Poisoned Stab+(1Poison(33→37)) | dealt=0 taken=0
  R12[Noisebot: StatusCard(2)+Zapbot: Atk(16)+Fabricator: Atk(11)+Noisebot: StatusCard(2)]: Defend(+19blk)->Defend(+19blk)->Defend+(+22blk) | dealt=0 taken=0
  R13[Noisebot: StatusCard(2)+Zapbot: Atk(18)+Fabricator: Atk(18), Summon]: Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Defend(+19blk)->Survivor(+22blk) | dealt=12 taken=0

F48 [boss] Test Subject (20R, HP 58->16, loss=42, WIN)
  R1[Test Subject #C66: Atk(20)]: Noxious Fumes+(+7blk,power:+Noxious Fumes(3))->Poisoned Stab(6dmg,1+Poison(3))->Bubble Bubble(2Poison(3→12),+Strength(2))->Blur(+6blk,power:+Blur(1),1Strength(2→4))->Dodge and Roll(+5blk,power:+Block Next Turn(5),1Strength(4→6))->Defend(+6blk,1Strength(6→8))->Defend(+6blk,1Strength(8→10))->Defend(+6blk,1Strength(10→12)) | dealt=6 taken=0
  R2[Test Subject #C66: Atk(26), Debuff]: Acrobatics->Neutralize+(5dmg,1+Weak(2))->Slice(7dmg)->Backflip(+6blk,1Strength(14→16))->Footwork+(power:Dexterity(1→4)) | dealt=12 taken=7
  R3[Test Subject #C66: Atk(40)]: Expertise+(1Strength(16→18)) | dealt=0 taken=42
  R4[Test Subject #C66: Atk(32), Debuff]: Footwork+(power:Dexterity(4→7))->Deflect(+11blk,1Strength(18→20))->Defend(+12blk,1Strength(20→22))->Survivor(+15blk,1Strength(22→24)) | dealt=0 taken=0
  R5[Test Subject #C66: Atk(66)]: Footwork(power:Dexterity(7→9))->Blade Dance(1Strength(24→26),exhaust:1)->Shiv(8dmg,exhaust:1)->Shiv(8dmg)->Shiv(6dmg,3-Enrage,-Poison,-Strength)->Defend(+14blk) | dealt=16 taken=0
  R6[Test Subject #C66: Atk(10x3=30)]: Blur+(+17blk,power:+Blur(1))->Defend+(+17blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=0 taken=0
  R7[Test Subject #C66: Atk(10x4=40)]: Acrobatics+->Slice+(15dmg)->Prepared->Defend+(+17blk) | dealt=15 taken=2
  R8[Test Subject #C66: Atk(10x5=50)]: Backflip+(+17blk)->Defend+(+17blk)->Dodge and Roll(+13blk,power:+Block Next Turn(13)) | dealt=0 taken=3
  R9[Test Subject #C66: Atk(10x6=60)]: Neutralize+(12dmg,1+Weak(2))->Deflect+(+16blk)->Defend(+14blk)->Bubble Bubble+(1Poison(9→21))->Tools of the Trade(power:+Tools of the Trade(1)) | dealt=12 taken=0
  R10[Test Subject #C66: Atk(7x7=49)]: Neutralize+(13dmg,1Weak(1→3))->Backflip+(+17blk)->Dodge and Roll+(+15blk,power:+Block Next Turn(15))->Survivor+(+20blk) | dealt=13 taken=0
  R11[Test Subject #C66: Atk(7x8=56)]: Blur+(+17blk,power:+Blur(1))->Defend+(+17blk)->Defend+(+17blk) | dealt=0 taken=0
  R12[Test Subject #C66: Atk(7x9=63)]: Slice+(20dmg)->Deflect+(+16blk)->Poisoned Stab+(19dmg,1Poison(27→31))->Strike(17dmg)->Backflip+(+17blk)->Prepared+ | dealt=56 taken=0
  R13[Test Subject #C66: Atk(10x3=30)]: Dodge and Roll+(+15blk,power:+Block Next Turn(15))->Defend+(+17blk)->Bubble Bubble+(1Poison(3→15)) | dealt=0 taken=0
  R14[Test Subject #C66: Atk(45)]: Deflect+(+16blk)->Defend+(+17blk)->Peck(45dmg)->Deadly Poison(1Poison(17→22)) | dealt=45 taken=0
  R15[Test Subject #C66: StatusCard(3), Buff]: Dodge and Roll+(+15blk,power:+Block Next Turn(15))->Acrobatics+->Slice+(1dmg)->Blur+(+17blk,power:+Blur(1))->Prepared+ | dealt=1 taken=0
  R16[Test Subject #C66: Atk(12x3=36)]: Neutralize+(19dmg,1+Weak(2))->Pounce(27dmg,power:+Free Skill(1))->Backflip+(+17blk,power:-Free Skill)->Dodge and Roll+(+15blk,power:+Block Next Turn(15)) | dealt=46 taken=0
  R17[Test Subject #C66: Atk(35)]: Deflect+(+16blk)->Bubble Bubble+(1Poison(28→40))->Backflip+(+17blk)->Blur+(+17blk,power:+Blur(1)) | dealt=0 taken=0
  R18[Test Subject #C66: StatusCard(3), Buff]: Deadly Poison+(1Poison(42→49))->Dodge and Roll+(+15blk,power:+Block Next Turn(15))->Dodge and Roll+(+15blk,power:Block Next Turn(15→30)) | dealt=0 taken=0
  R19[Test Subject #C66: Atk(14x3=42)]: Backflip+(+17blk)->Acrobatics+->Slice+(1dmg)->Poisoned Stab+(1dmg,1Poison(51→55))->Prepared+->Neutralize+(1dmg,1+Weak(2)) | dealt=3 taken=0
  R20[Test Subject #C66: Atk(36)]: Peck+(84dmg)->Strike+(power:-Dexterity,power:-Ritual,power:-Noxious Fumes,power:-Strength,power:-Well-Laid Plans,power:-Tools of the Trade) | dealt=84 taken=0

### Non-combat Decisions (202 decisions)
F1 [event] choose_event_option (option_index=2) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->15
  deck_change: added Defend, Strike
  reasoning: Large Capsule provides 2 random relics right at the start of the run, which offers immense snowball potential and immediate power spikes, easily outweighing the drawback of adding an extra Strike and Defend to the starting deck.
  strategic_note: Foundation deck: taking high-value cards and relics to build early game power. Focus on finding good damage to offset the added starter cards, and path aggressively if the new relics provide strong combat benefits.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 15->15
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Standard Act 1 opening. Taking monsters early to see card rewards and build a foundation for the upcoming elite. Route index 1 leads to a path with a treasure chest and multiple potential elites/shops.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block cards to preserve HP while leveraging Meat on the Bone for more aggressive pathing later.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->110 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 110->110 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 110->110 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 56->56 | Gold 110->110 | Deck 15->16
  deck_change: picked Blade Dance
  reasoning: Blade Dance provides 12 damage for 1 energy, which is incredibly efficient early-game burst damage for Elites and Act 1 hallways, even if it exhausts. It also opens up Shiv synergies for the rest of the run.
  strategic_note: Foundation plan: Use frontload damage like Blade Dance to survive early elites and hallways. Looking for core scaling engines (Shiv or Poison). Take efficient damage and block.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Unknown

F3 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: no deck change
  reasoning: Transforming a Defend into Peck increases our attack density, which is exactly what we need for early Act 1 hallway and elite fights. The Snake option is terrible because all our cards cost 0 or 1, and the Torus option is too slow for early game tempo.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block cards to preserve HP while leveraging Meat on the Bone for more aggressive pathing later.

F3 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: changed: +Peck; -Strike
  reasoning: Transforming a basic Strike removes our worst attack card and potentially gives us a better card to help build our Phase 1 foundation. It also helps thin out the extra basic cards from Large Capsule.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. We have a Blade Dance but are not yet fully committed to shivs.

F3 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F3 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. Early Act 1 Unknowns have a high chance of being favorable events or manageable fights that help build the deck without the guaranteed chip damage of a standard hallway fight, and Meat on the Bone provides a safety net if it is a combat.
  strategic_note: Foundation deck: prioritizing high-value early damage and block cards to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 110->110 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 110->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 110->119 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 119->119 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 55->55 | Gold 119->119 | Deck 16->17
  deck_change: picked Skewer
  reasoning: Skewer is an excellent flexible energy sink. With Ring of the Snake and Bag of Preparation, we draw 9 cards on turn 1, so having a card that can efficiently use all our energy to deal frontload damage is very valuable.
  strategic_note: Foundation plan: survive with frontload damage like Skewer while looking for a core scaling engine. We draw 9 cards on turn 1, so prioritize high-impact cards or energy generation to capitalize on early draw.

F5 [map] choose_map_node (option_index=0) | source=llm
  HP 55->55 | Gold 119->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Continuing the established route to fight a Monster on Floor 5. This will provide a card reward to bolster the deck before the first Elite, while Meat on the Bone ensures I can sustain the HP cost of early-game aggression.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block cards to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 119->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Our deck already has Skewer, Peck, and Blade Dance for early damage, alongside 5 Strikes. A second Skewer risks becoming clunky on 3 energy, Memento Mori lacks enough discard support, and Prepared is card-negative without an upgrade or discard synergies. Skipping keeps the deck lean while we search for core scaling pieces like Finisher or premium draw/discard.
  strategic_note: Foundation plan: survive with current frontload (Skewer, Blade Dance) while digging for a core engine piece like Finisher or Acrobatics. Take high-impact damage or premium draw; avoid narrow synergy pieces until the engine is clear.

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: upgraded Skewer->Skewer+
  reasoning: HP is high (55/70) and we have Meat on the Bone, making resting completely unnecessary. Upgrading Skewer is excellent for burst damage, adding 3 damage per energy spent (e.g., +9 damage at 3 energy).
  strategic_note: Foundation deck: prioritizing clean early-game damage (Skewer, Blade Dance) and block to stabilize while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.

F7 [rest_site] proceed | source=auto
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=1) | source=llm
  HP 55->55 | Gold 133->133 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. This path leads toward a late-act Elite, providing time to strengthen the deck. With Meat on the Bone, I can afford to take some chip damage in events or future hallway fights, but preserving HP for the upcoming Elite (node 9) is still a priority.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to preserve HP while leveraging Meat on the Bone to path aggressively toward late-act elites and upgrades.

F8 [shop] buy_card (option_index=4) | source=plan
  HP 55->55 | Gold 133->56 | Deck 17->18
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/2]: Provides essential scaling damage for the upcoming Ceremonial Beast boss and Act 2, serving as a solid core for a poison engine.

F8 [shop] buy_card (option_index=0) | source=plan
  HP 55->55 | Gold 56->31 | Deck 18->19
  deck_change: bought Poisoned Stab
  reasoning: Shop plan [2/2]: On sale, excellent early-game damage that synergizes perfectly with Noxious Fumes to accelerate poison stacking.

F8 [shop] close_shop_inventory | source=plan
  HP 55->55 | Gold 31->31 | Deck 19->19
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F8 [shop] proceed | source=auto
  HP 55->55 | Gold 31->31 | Deck 19->19
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F8 [map] choose_map_node (option_index=1) | source=llm
  HP 55->55 | Gold 31->0 | Deck 19->19
  deck_change: no deck change
  reasoning: I have 55/70 HP and Meat on the Bone, which provides a significant safety net for aggressive pathing. The deck needs relics and higher-impact cards to scale for the Act 1 boss. This Elite node is the recommended path and I am healthy enough to take it.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 31->64 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 33 Gold

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 64->64 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 64->64 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim relic: Gambling Chip

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 64->64 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F9 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 48->48 | Gold 64->64 | Deck 19->20
  deck_change: picked Well-Laid Plans
  reasoning: Well-Laid Plans provides exceptional consistency by letting us hold key cards like Skewer+ for massive burst turns or exact phase pushes, which is crucial for the Ceremonial Beast boss. It also lets us retain defensive tools until the enemy attacks.
  strategic_note: Foundation plan: Use our massive turn 1 draw (9 cards + Gambling Chip) to find scaling like Noxious Fumes or setup like Well-Laid Plans. Retain Skewer+ for big burst turns to push boss thresholds. Still looking for block scaling or a committed engine.

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 64->64 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 48->48 | Gold 64->102 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Permafrost

F10 [treasure] proceed | source=random
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: upgraded Noxious Fumes->Noxious Fumes+
  reasoning: HP is at 48/70, which is perfectly safe, especially with 2 more rest sites before the boss. Noxious Fumes is our primary scaling for the Act 1 Boss. Upgrading it increases the net poison gain per turn from 1 to 2, effectively doubling its scaling speed.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Noxious Fumes for boss scaling and Meat on the Bone to path aggressively. Focus on upgrading key pieces like Fumes, Neutralize, and Well-Laid Plans while removing basic Strikes/Defends.

F11 [rest_site] proceed | source=auto
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 48->48 | Gold 102->102 | Deck 20->20
  deck_change: no deck change
  reasoning: With 102 gold and 48 HP (just above the Meat on the Bone threshold of 35), the shop provides a critical opportunity to remove a Strike/Defend or purchase a scaling card before the upcoming Elite. Following the established route to ensure the deck is prepared for the late-Act 1 power checks.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.

F12 [shop] buy_card (option_index=4) | source=plan
  HP 48->48 | Gold 102->24 | Deck 20->21
  deck_change: bought Footwork
  reasoning: Shop plan [1/2]: Provides crucial defensive scaling for boss fights and pairs perfectly with our 6 Defends and Permafrost relic.

F12 [shop] buy_card (option_index=3) | source=plan
  HP 48->48 | Gold 24->0 | Deck 21->22
  deck_change: bought Deadly Poison
  reasoning: Shop plan [2/2]: An incredibly efficient on-sale poison applicator that synergizes perfectly with our Noxious Fumes+ to create a strong scaling damage engine for the Act boss.

F12 [shop] close_shop_inventory | source=plan
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F12 [shop] proceed | source=auto
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: RestSite

F13 [rest_site] choose_rest_option (option_index=1, smith_card_index=17) | source=llm
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: upgraded Footwork->Footwork+
  reasoning: With 48 HP and another rest site at Floor 16 right before the Boss, we are extremely safe to Smith here. Upgrading Footwork increases our Dexterity gain from 2 to 3, which drastically improves the value of our 6 Defends and Survivor, crucial for surviving the Act 1 Boss's multi-attacks.
  strategic_note: Committed poison engine: stack Noxious Fumes and play Footwork to scale defensively while passive poison kills. Retain key cards with Well-Laid Plans to optimize block turns. Avoid bloated raw attacks; look for Corpse Explosion or Catalyst to accelerate boss fights.

F13 [rest_site] proceed | source=auto
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=1) | source=llm
  HP 48->48 | Gold 0->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Visiting a shop with 0 gold is a wasted floor. Fighting a monster provides a card reward, gold, and a potion chance, which are essential for strengthening the deck before the upcoming elite and boss fights. Meat on the Bone provides a safety net if the combat goes poorly.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to stabilize while leveraging Meat on the Bone to path aggressively toward elites and smithing upgrades.

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 0->8 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 8->8 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 40->40 | Gold 8->8 | Deck 22->23
  deck_change: picked Dodge and Roll
  reasoning: Dodge and Roll is perfect for the upcoming Ceremonial Beast boss. The boss applies Ringing (restricted to 1 card play next turn) before a big attack. Playing Dodge and Roll the turn before provides block during the restricted turn, and it scales exceptionally well with Footwork+.
  strategic_note: Committed poison plan: use Noxious Fumes+ and Deadly Poison to scale damage while surviving with Footwork+ and Dodge and Roll. Push Ceremonial Beast to 150 HP quickly, then use Dodge and Roll the turn before Ringing to mitigate its big attack.

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 40->40 | Gold 8->8 | Deck 23->23
  deck_change: no deck change
  reasoning: With Meat on the Bone and 40 HP, I am in a strong position to take this Elite. The heal from Meat on the Bone (12 HP) will trigger if I end the fight below 35 HP, effectively making this a high-value, lower-risk node that can provide a relic and rare card before the boss. The alternative is a shop with only 8 gold, which is useless.
  strategic_note: Foundation deck: prioritizing clean early-game damage and block to preserve HP while leveraging Meat on the Bone for aggressive elite pathing.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 8->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim relic: Pantograph

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Our deck is 23 cards with an incredible turn 1 draw engine (Ring of the Snake, Bag of Prep, Gambling Chip) that guarantees finding our core powers (Fumes+, Footwork+, WLP). We want to keep the deck lean to draw our poison and defense consistently. None of the offered cards significantly improve our boss strategy.
  strategic_note: Committed poison plan: rely on massive Turn 1 draw to set up Noxious Fumes+, Footwork+, and Well-Laid Plans. Stack poison while defending, and use Retain to hold key blocks for the Beast's Ringing turn.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=1, smith_card_index=9) | source=llm
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With Pantograph, we will heal 25 HP at the start of the boss fight, bringing us to 59 HP (out of 70). This is plenty of health for the Act 1 boss, so we can safely Smith instead of resting. Upgrading Neutralize to apply 2 Weak is crucial for mitigating boss damage over longer fights.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Retain key cards with Well-Laid Plans to optimize block turns. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F16 [rest_site] proceed | source=auto
  HP 34->34 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 34->59 | Gold 38->38 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 38->113 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 113->113 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 41->41 | Gold 113->113 | Deck 23->24
  deck_change: picked Nightmare
  reasoning: Nightmare is a premier scaling multiplier that synergizes perfectly with our current deck. Combined with Well-Laid Plans, we can easily set up Nightmare on Noxious Fumes+ for massive AoE damage scaling or Footwork+ for impenetrable defense in boss fights.
  strategic_note: Committed to poison/block scaling. Use Well-Laid Plans to set up Nightmare on Noxious Fumes+ for damage or Footwork+ for block in long fights. Focus on acquiring cheap card draw and mitigation. Avoid adding unnecessary attacks; rely on poison to kill.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 41->64 | Gold 113->113 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0) | source=llm
  HP 64->64 | Gold 113->113 | Deck 24->24
  deck_change: no deck change
  reasoning: Very Hot Cocoa gives us +4 Energy on Turn 1. This synergizes perfectly with our insane Turn 1 card draw (Ring of the Snake + Bag of Preparation = 9 cards drawn) and Gambling Chip. We can immediately play out our hand, set up key powers like Footwork and Noxious Fumes, or hit massive burst with Skewer+.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 64->64 | Gold 113->113 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 64->64 | Gold 113->113 | Deck 24->24
  deck_change: no deck change
  reasoning: Path c4 leads through a sequence of monsters to build gold for an early shop, while setting up a path with two elites and multiple rest sites to leverage Meat on the Bone and Pantograph.
  strategic_note: Foundation deck: focusing on high-quality card rewards from hallway fights to prepare for elite hunting, leveraging Meat on the Bone for aggressive HP management and Pantograph for boss sustain.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 113->121 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 121->121 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 59->59 | Gold 121->121 | Deck 24->25
  deck_change: picked Dodge and Roll
  reasoning: With Footwork+ already in the deck, Dodge and Roll becomes incredibly efficient since Dexterity applies to the block on both turns. It provides excellent sustained defense to buy time for our Poison engine (Noxious Fumes+, Deadly Poison) to scale and kill.
  strategic_note: Committed poison plan: use massive turn 1 draw and energy to set up Noxious Fumes, Footwork, and Nightmare, then play defensively while passive poison kills. Needs more card draw (Acrobatics/Backflip) for sustained cycling after turn 1; avoid adding any more raw attacks.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 121->121 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Shop

F20 [shop] buy_card (option_index=2) | source=plan
  HP 59->59 | Gold 121->50 | Deck 25->26
  deck_change: bought Acrobatics
  reasoning: Shop plan [1/2]: With Very Hot Cocoa (+4 energy on turn 1), Ring of the Snake, and Gambling Chip, we have a massive Turn 1 burst of energy and hand size. Acrobatics provides crucial card draw to help us spend that 7 energy efficiently and find our Skewer+ or key powers.

F20 [shop] buy_card (option_index=3) | source=plan
  HP 59->59 | Gold 50->24 | Deck 26->27
  deck_change: bought Deflect
  reasoning: Shop plan [2/2]: Cheap 0-cost block that scales with our Footwork+ and lets us defend while spending our energy on setup or Skewer burst.

F20 [shop] close_shop_inventory | source=plan
  HP 59->59 | Gold 24->24 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F20 [shop] proceed | source=auto
  HP 59->59 | Gold 24->24 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 24->24 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Monster

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 24->37 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 37->37 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 59->59 | Gold 37->37 | Deck 27->28
  deck_change: picked Backflip
  reasoning: Backflip provides much-needed card draw and efficient block, especially scaling well with our Footwork+. It helps us cycle to our key powers (Noxious Fumes, Footwork) or find Skewer on Turn 1 to exploit the Very Hot Cocoa energy spike.
  strategic_note: Hybrid poison and burst damage plan: cycle aggressively to find Noxious Fumes and Footwork for scaling, or use Turn 1 energy for a massive Skewer+. Prioritize card draw and card removal to improve consistency; skip generic attacks.

F21 [map] choose_map_node (option_index=1) | source=llm
  HP 59->59 | Gold 37->37 | Deck 28->28
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node to build more deck strength before the upcoming Elites. Meat on the Bone and Pantograph provide significant sustain, allowing me to take these hallway fights to hunt for a Catalyst or Corpse Explosion.
  strategic_note: Committed poison engine: scale via Footwork and Noxious Fumes while using Well-Laid Plans to line up blocks. Scaling is currently slow; aggressively hunting for Catalyst or Corpse Explosion to handle Act 2 Elites and the Boss.

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 37->47 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 47->47 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 47->47 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 22->22 | Gold 47->47 | Deck 28->29
  deck_change: picked Pounce
  reasoning: Pounce is excellent against the Act 2 Knowledge Demon. The boss either limits card plays to 3 (Sloth) or reduces energy by 1 (Waste Away). Pounce cheats energy for expensive skills like Nightmare, allowing us to play Pounce (2E) + Nightmare (0E) even if we only have 2 Energy from Waste Away. It also consolidates energy into fewer card plays, working well against Sloth.
  strategic_note: Committed to Fumes+/Footwork+ scaling with Nightmare. Use Pounce to cheat Nightmare's energy cost. Retain key pieces with WLP.

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 22->22 | Gold 47->47 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 13->13 | Gold 47->58 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 13->13 | Gold 58->58 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 13->13 | Gold 58->58 | Deck 29->30
  deck_change: picked Backflip+
  reasoning: Backflip+ provides excellent block and vital card draw. Since we start combats with +4 energy from Very Hot Cocoa and draw many cards with our relics, having 1-cost draw skills keeps the deck flowing and helps us find our Noxious Fumes+, Footwork+, and Skewer+ on Turn 1.
  strategic_note: Committed poison plan: rely on Noxious Fumes and poison cards to scale damage, while using block and draw (like Backflip+) to survive. Utilize our massive Turn 1 energy to set up powers and big Skewers. Needs more consistent block and poison scaling; avoid narrow synergies like shivs unless we find Envenom.

F23 [map] choose_map_node (option_index=1) | source=llm
  HP 13->13 | Gold 58->58 | Deck 30->30
  deck_change: no deck change
  reasoning: With 13 HP, a rest site is mandatory to avoid death in the next combat. Meat on the Bone and Pantograph provide some sustainability, but we are currently below the threshold to survive even a minor chip-damage hallway fight in Act 2.
  strategic_note: Committed poison engine: scale defense with Footwork and passive damage with Noxious Fumes. Use Well-Laid Plans to hold block for big hits. Priority is finding a Catalyst or Corpse Explosion to speed up kills while surviving through rest site pathing.

F24 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 13->34 | Gold 58->58 | Deck 30->30
  deck_change: no deck change
  reasoning: With only 13 HP and an Elite fight immediately next, healing is absolutely mandatory to survive Act 2.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F24 [rest_site] proceed | source=auto
  HP 34->34 | Gold 58->58 | Deck 30->30
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F24 [map] choose_map_node (option_index=0) | source=llm
  HP 34->34 | Gold 58->58 | Deck 30->30
  deck_change: no deck change
  reasoning: With 34/70 HP and no defensive scaling outside of Footwork, fighting an Elite right now is too risky. Meat on the Bone provides a safety net if I take damage in the hallway fight, and Pantograph ensures I'll be healthy for the boss regardless. I need to find scaling cards (Catalyst/Corpse Explosion) in hallway rewards before taking on the floor 28 Elite.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; avoid elites until damage scaling improves.

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 58->66 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 34->34 | Gold 66->66 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F25 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 34->34 | Gold 66->66 | Deck 30->31
  deck_change: picked Expertise+
  reasoning: Expertise+ is incredibly powerful with Very Hot Cocoa, allowing us to dump our hand using the extra energy on turn 1 and immediately refill to 7 cards. This massive cycle helps us set up our Footwork and Noxious Fumes scaling much faster.
  strategic_note: Committed poison/defense plan: survive with frontloaded block and Footwork scaling while Noxious Fumes and poison cards slowly kill. Use Very Hot Cocoa and high draw to rapidly set up powers. Needs Catalyst or more focused poison; skip off-plan attacks.

F25 [map] choose_map_node (option_index=1) | source=llm
  HP 34->34 | Gold 66->66 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure node. My HP is at 49% (34/70), which triggers Meat on the Bone, and the upcoming Rest Site after the treasure will allow me to Smith or Heal depending on my condition before the Elite fight.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; currently prioritizing safety via Rest Sites to leverage Meat on the Bone.

F26 [treasure] open_chest | source=random
  HP 34->34 | Gold 66->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 34->34 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim: Razor Tooth

F26 [treasure] proceed | source=random
  HP 34->34 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=llm
  HP 34->34 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the established safe route to prioritize recovery and upgrades. Meat on the Bone is active at 34/70 HP, but the upcoming Elite fight requires more than a chip-heal to survive given the current defensive poison setup. This rest site allows for a critical upgrade or a heal depending on confidence before the Elite.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F27 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 34->55 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Facing an Act 2 Elite next floor with exactly 34 HP is too risky, especially against Slavers who can deal 34 damage on turn 1. Healing puts us at a much safer 55 HP, and we have another rest site immediately after the Elite to smith our key cards like Nightmare or Well-Laid Plans.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw to set up powers quickly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F27 [rest_site] proceed | source=auto
  HP 55->55 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 55->55 | Gold 103->103 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Elite

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 103->134 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 31 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 134->134 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 134->134 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim relic: Book of Five Rings

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 134->134 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 46->46 | Gold 134->134 | Deck 31->32
  deck_change: picked Footwork
  reasoning: A second Footwork provides more consistent Dexterity scaling, which is crucial for our Noxious Fumes stalling strategy. Since we have multiple Dodge and Rolls and Backflips, stacking Dexterity allows us to fully block late-game threats.
  strategic_note: Committed to passive poison (Noxious Fumes) and Dexterity stalling. Look for Catalyst or Corpse Explosion to accelerate poison damage, and retain efficient block/draw. Avoid bloating with non-poison attacks.

F28 [map] choose_map_node (option_index=1) | source=llm
  HP 46->46 | Gold 134->134 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the planned route to a Rest Site. With 46/70 HP and Meat on the Bone, I am relatively healthy but should prioritize Smithing to strengthen the deck's scaling before the Act 2 boss.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F29 [rest_site] choose_rest_option (option_index=1, smith_card_index=18, note_scope=run, note_triggers=all) | source=llm
  HP 46->46 | Gold 134->134 | Deck 32->32
  deck_change: upgraded Nightmare->Nightmare+
  reasoning: HP is at 46/70, and with Pantograph healing 25 HP at the start of the boss, we are very safe. Nightmare at 3 energy is incredibly difficult to play on the turn it is drawn. Upgrading it to 2 energy allows us to actually play other cards on the setup turn, which is crucial for our engine. Although Razor Tooth upgrades Skills when played, the initial cost reduction is necessary.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling.

F29 [rest_site] proceed | source=auto
  HP 46->46 | Gold 134->134 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 134->134 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended path to a Monster node. With 46 HP and Meat on the Bone, I am relatively safe, but an Elite at this stage of Act 2 can be devastating for a poison deck that hasn't found a Catalyst or Corpse Explosion yet. The Monster fight provides a card reward to search for those missing pieces and gold for the upcoming Shop.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights; prioritize finding these in card rewards and the upcoming shop.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 134->142 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F30 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 41->41 | Gold 142->142 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 41->41 | Gold 142->142 | Deck 32->32
  deck_change: no deck change
  reasoning: Our deck is already 32 cards large and we don't need these generic commons. Skip to avoid bloat and rely on our strong Relics (Gambling Chip, Razor Tooth, Very Hot Cocoa) and card draw.
  strategic_note: Foundation plan: survive with high turn-1 energy (Very Hot Cocoa) and draw (Gambling Chip, Bag of Prep) to set up scaling (Noxious Fumes, Nightmare) or burst (Skewer+). Seeking a more concrete scaling engine for Act 3.

F30 [map] choose_map_node (option_index=1) | source=llm
  HP 41->41 | Gold 142->142 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the planned route to the Shop. With 142 gold and a committed poison/defensive build, I need to look for a card removal (to thin out strikes), a Catalyst/Corpse Explosion for scaling, or better defensive tools. I am at 41/70 HP, and Pantograph will heal me at the boss, so I am in a stable position to spend gold before the final rest site.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale while defending. Current priority is finding a Catalyst or Corpse Explosion to accelerate kill speed and thinning the deck of basic strikes at shops.

F31 [shop] discard_potion (option_index=1) | source=plan
  HP 41->41 | Gold 142->142 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan: discard Explosive Ampoule

F31 [shop] buy_potion (option_index=0) | source=plan
  HP 41->41 | Gold 142->92 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan [2/4]: Crucial defensive tool for the Knowledge Demon's Turn 3 multi-attack check. 5 Dex will easily let us block the heavy damage.

F31 [shop] buy_card (option_index=2) | source=plan
  HP 41->41 | Gold 92->43 | Deck 32->33
  deck_change: bought Prepared
  reasoning: Shop plan [3/4]: Zero-cost cycle is great when we dump all our energy into Skewer+. It also helps dig for Footwork/Nightmare setup.

F31 [shop] buy_card (option_index=0) | source=plan
  HP 41->41 | Gold 43->19 | Deck 33->34
  deck_change: bought Slice
  reasoning: Shop plan [4/4]: Zero-cost damage to play after an X-cost Skewer+. Gets upgraded by Razor Tooth to 9 damage for free.

F31 [shop] close_shop_inventory | source=plan
  HP 41->41 | Gold 19->19 | Deck 34->34
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F31 [shop] proceed | source=auto
  HP 41->41 | Gold 19->19 | Deck 34->34
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 19->19 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 41->41 | Gold 19->19 | Deck 34->34
  deck_change: upgraded Well-Laid Plans->Well-Laid Plans+
  reasoning: With Pantograph, my 41 HP will become 66 HP at the start of the boss fight, so resting is unnecessary. Upgrading Well-Laid Plans allows me to retain 2 cards, which is crucial for holding both Nightmare and its target (like Footwork+ or Noxious Fumes+) until the perfect turn to play them.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling.

F32 [rest_site] proceed | source=auto
  HP 41->41 | Gold 19->19 | Deck 34->34
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 41->66 | Gold 19->19 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 66->66 | Gold 19->0 | Deck 34->34
  deck_change: no deck change
  reasoning: With Survivor, Acrobatics, Prepared, and Gambling Chip, we have abundant ways to discard Disintegration before it triggers damage. Mind Rot reducing draw is far more detrimental to our cycling.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F33 [card_select] select_deck_card (option_index=1) | source=llm
  HP 38->38 | Gold 19->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Forced to copy a status card with Nightmare. Copying Sloth prevents me from taking 21 damage next turn from Disintegration, even though the hand clog will be annoying.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 37->37 | Gold 19->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Choosing Disintegration over Waste Away. Losing 1 energy per turn is a severe permanent debuff, while taking 8 damage can be mitigated or healed.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage massive turn 1 card draw and energy to set up powers instantly. Needs a Catalyst or Corpse Explosion to accelerate boss fights.

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 19->94 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 94->94 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 37->37 | Gold 94->94 | Deck 34->35
  deck_change: picked Tools of the Trade
  reasoning: Tools of the Trade provides excellent deck filtering and triggers Permafrost for 7 Block. With a 34-card deck, finding our core powers (Footwork, Noxious Fumes) and Nightmare targets is critical, and the passive draw/discard accelerates our cycle without costing ongoing energy.
  strategic_note: Committed to poison/defense scaling. Focus on playing Noxious Fumes and Footwork, using Nightmare on key powers or block cards, and surviving while poison ramps. Prioritize removing Strikes to thin the deck.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 37->63 | Gold 94->94 | Deck 35->35
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1) | source=llm
  HP 63->63 | Gold 94->94 | Deck 35->35
  deck_change: no deck change
  reasoning: Delicate Frond provides incredible run-long value by giving up to 3 potions every single combat, solving any bad hands or specific combat needs. Apotheosis is largely redundant because my key powers are already upgraded and I have Razor Tooth for skills/attacks. Max HP is nice but doesn't solve fights as effectively as free potions per combat.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Leverage Well-Laid Plans to hold Nightmare and a key power/block card for massive scaling. Delicate Frond gives free potions every combat, so use them aggressively.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 63->63 | Gold 94->94 | Deck 35->35
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=0) | source=llm
  HP 63->63 | Gold 94->94 | Deck 35->35
  deck_change: no deck change
  reasoning: This node initiates the planned route through Act 2. Following the 'Zero Combats/Elites' advice is impossible given the map generation, so I will prioritize the route that leads toward shops for deck thinning (removals) and the treasure chest. Meat on the Bone and Pantograph provide significant sustain, making the upcoming combat encounters manageable.
  strategic_note: Committed poison engine: scale via Footwork and Noxious Fumes while prioritizing defense. Current focus is deck thinning at shops and hunting for Catalyst or Corpse Explosion to solve multi-enemy fights and boss scaling.

F35 [card_select] select_deck_card (option_index=2) | source=llm
  HP 63->63 | Gold 94->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Accelerant will significantly speed up the kill by making Poison trigger an additional time, leveraging the deck's Noxious Fumes+ and Deadly Poison. Since we have Permafrost, playing any power will also give 7 Block to fully mitigate the incoming damage this turn.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 94->102 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 102->102 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim potion: Powdered Demise

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 102->102 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 50->66 | Gold 102->102 | Deck 35->36
  deck_change: picked Bouncing Flask
  reasoning: We are heavily invested in Poison scaling with Noxious Fumes+ and Nightmare+. Bouncing Flask is a premium poison applicator that drastically accelerates boss kills, especially since Razor Tooth will upgrade it to apply 12 poison. With Very Hot Cocoa giving us 7 energy on turn 1, we can easily afford it or even Nightmare it for massive damage.
  strategic_note: Committed to poison scaling. Setup huge turn 1 with Very Hot Cocoa (+4 energy) and Gambling Chip. Prioritize Nightmare on Bouncing Flask, Noxious Fumes, or Footwork depending on combat needs. Focus on removing basic Strikes and Defends to thin the deck.

F35 [map] choose_map_node (option_index=0) | source=llm
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: Following the recommended path towards the unknown node. Unknown nodes in Act 3 often provide favorable events or even shops/chests that can improve the deck without the HP risk of a hallway fight. With 66 HP, I am in a strong position to handle events or potential combats, and Meat on the Bone provides a safety net.
  strategic_note: Committed poison engine: scale via Noxious Fumes and Footwork while using Well-Laid Plans to set up Nightmare on key powers or defensive pieces. Prioritize shops for card removal and defensive upgrades to ensure the slow poison scaling has time to win.

F36 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: Grabbing 3 Foul Potions provides an incredible 300 Gold when thrown at the upcoming Merchant on F40. Even with Delicate Frond filling potion slots automatically, guaranteeing 300 Gold for card removals and defensive upgrades at the shop is vastly superior to a single random uncommon potion.
  strategic_note: Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers. Use the 3 Foul Potions on the F40 merchant for 300 Gold to fuel card removals and find key block/power upgrades. Delicate Frond keeps us safe with random potions in combats once our slots are empty again.

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim potion: Foul Potion

F36 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 102->102 | Deck 36->36
  deck_change: no deck change
  reasoning: Only path: Monster

F37 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 102->117 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F37 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: Open card reward

F37 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 30->30 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: The deck is already very large at 36 cards. We have enough poison application (Noxious Fumes, Bouncing Flask, Deadly Poison) and do not need more basic attacks or common poison cards. Skipping keeps the deck leaner to draw our Nightmare, Footworks, and Skewer faster.
  strategic_note: Committed poison/Skewer plan: Retain key cards like Nightmare and Footwork+, burst enemies with Skewer+ early using Very Hot Cocoa energy, and let Noxious Fumes scale. Keep deck lean.

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: Only path: Unknown

F38 [event] choose_event_option (option_index=1, note_scope=run) | source=llm
  HP 30->30 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: With Meat on the Bone, being at 19/66 HP is not as dangerous as it seems, as we can easily heal 12 HP at the end of the next few combats. Taking 11 damage for a random Relic is far superior to taking Royal Poison, which would drain 4 HP every combat for the rest of the run.
  strategic_note: Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers. Meat on the Bone provides massive sustain, allowing us to hover safely around 33 HP and greed relics/upgrades instead of resting.

F38 [event] choose_event_option (option_index=0) | source=auto
  HP 30->19 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: Only option: Continue

F38 [event] choose_event_option (option_index=0) | source=auto
  HP 19->19 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: Only option: Proceed

F38 [map] choose_map_node (option_index=1) | source=llm
  HP 19->19 | Gold 117->117 | Deck 36->36
  deck_change: no deck change
  reasoning: With 19/66 HP, I am in a critical state. I need to avoid combat to benefit from Meat on the Bone if I do fight, but ideally, I find an event that offers healing or a non-combat path. The 'Unknown' node (c1,r5) is safer than a guaranteed 'Monster' fight at this HP level, especially with two shops and two rest sites ahead to stabilize.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale while holding Nightmare for key powers with Well-Laid Plans. Currently in survival mode due to low HP; prioritize events and shops to find sustain or defensive upgrades, relying on Meat on the Bone and Pantograph to reach the boss.

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 117->126 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 31->31 | Gold 126->126 | Deck 36->36
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 31->31 | Gold 126->126 | Deck 36->36
  deck_change: no deck change
  reasoning: The deck is already quite large at 36 cards, and we are heavily committed to a Poison and Dexterity scaling plan (Noxious Fumes+, Bouncing Flask, Footwork). None of these cards significantly improve our core engine. While we have discard outlets for the Sly cards, their impact (15 random damage or 6 block) is too low in Act 3 to justify slowing down our draw to crucial scaling cards.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 31->31 | Gold 126->126 | Deck 36->36
  deck_change: no deck change
  reasoning: Only path: Shop

F40 [shop] buy_card (option_index=4) | source=plan
  HP 31->31 | Gold 126->48 | Deck 36->37
  deck_change: bought Footwork
  reasoning: Shop plan [1/1]: We have an incredible turn 1 draw engine (Ring of the Snake, Bag of Prep, Gambling Chip) and +4 Energy turn 1 (Very Hot Cocoa). Adding a third Footwork ensures we find and play massive defensive scaling immediately, letting our block cards easily outpace Act 3 bosses.

F40 [shop] close_shop_inventory | source=plan
  HP 31->31 | Gold 48->48 | Deck 37->37
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F40 [shop] proceed | source=auto
  HP 31->31 | Gold 48->48 | Deck 37->37
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 31->31 | Gold 48->48 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 31->31 | Gold 48->80 | Deck 37->37
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 31->31 | Gold 80->80 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim: Oddly Smooth Stone

F41 [treasure] proceed | source=random
  HP 31->31 | Gold 80->80 | Deck 37->37
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=auto
  HP 31->31 | Gold 80->80 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: Monster

F42 [card_select] select_deck_card (option_index=0) | source=llm
  HP 31->31 | Gold 80->0 | Deck 37->37
  deck_change: no deck change
  reasoning: I am facing 33 damage with 3 energy and need to maximize block. Deflect costs 0 energy, allowing me to play it alongside the Backflip and Defends already in my hand, whereas I wouldn't have the energy to play another 1-cost block card.
  strategic_note: Committed poison plan: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 80->92 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 92->92 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim potion: Swift Potion

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 92->92 | Deck 37->37
  deck_change: no deck change
  reasoning: Open card reward

F42 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 39->39 | Gold 92->92 | Deck 37->38
  deck_change: picked Bubble Bubble
  reasoning: Bubble Bubble is a massive accelerator for our Poison engine. With Noxious Fumes+, it's guaranteed to trigger, and Razor Tooth upgrades it to 12 Poison in combat. This dramatically improves our boss-killing speed.
  strategic_note: Committed poison plan: accelerate poison stacks with Bubble Bubble and Bouncing Flask while hiding behind massive Dexterity from Footworks. Keep the deck focused on cycle and poison; avoid taking any more direct damage attacks.

F42 [map] choose_map_node (option_index=1) | source=llm
  HP 39->39 | Gold 92->92 | Deck 38->38
  deck_change: no deck change
  reasoning: With 39/66 HP, I am slightly above the Meat on the Bone threshold (33 HP) but well below a safe margin for an Act 3 Elite, especially following the route guide's advice to avoid them. Taking the Rest Site allows me to Smith a key card like Nightmare or Well-Laid Plans to solidify the poison engine before the final push to the boss.
  strategic_note: Committed poison engine: utilize Well-Laid Plans to setup Nightmare on Noxious Fumes or Footwork for scaling. Prioritize defensive consistency and let poison tick down enemies; avoid Act 3 elites as they pose a high risk of run-ending burst damage.

F43 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 39->66 | Gold 92->92 | Deck 38->38
  deck_change: no deck change
  reasoning: Facing a dangerous Act 3 Elite next, and 39 HP is too low a buffer against potential burst damage like Reptomancer's daggers or Nemesis's turn 2 attack. With Regal Pillow, resting heals us to full (66/66). Because we have Razor Tooth, our Attacks and Skills upgrade themselves upon play, reducing the value of Smithing them. We will take the safe heal to guarantee survival.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Use Well-Laid Plans to hold Nightmare for key powers or block cards. Razor Tooth automatically upgrades Skills/Attacks upon play, so focus future permanent upgrades on Powers like Footwork.

F43 [rest_site] proceed | source=auto
  HP 66->66 | Gold 92->92 | Deck 38->38
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 92->92 | Deck 38->38
  deck_change: no deck change
  reasoning: Only path: Monster

F44 [card_select] select_deck_card (option_index=1) | source=llm
  HP 66->66 | Gold 92->0 | Deck 38->38
  deck_change: no deck change
  reasoning: Assassinate costs 0 energy, deals 10 damage, and applies Vulnerable. This gives the best immediate damage output for zero energy, which is crucial for bursting down an enemy to reduce the incoming 38 damage.
  strategic_note: Committed poison engine: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers.

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 92->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Open card reward

F44 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 49->49 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Our deck is heavily committed to Poison scaling with strong Dexterity/Block mitigation. We already have 38 cards and none of these choices significantly improve our win condition. Skipping prevents further deck bloat, helping us draw our Footworks, Noxious Fumes, Bouncing Flask, and Bubble Bubble faster.
  strategic_note: Committed poison/dexterity plan: use Gambling Chip to dig for Footworks and Fumes turn 1, stack poison and block. Nightmare can copy Footwork for invincible block or Bubble Bubble for lethal poison. Skip unnecessary attacks to keep the deck as lean as possible given its current size.

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Only path: Monster

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 103->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 116->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 116->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 37->37 | Gold 116->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Our deck is already quite large at 38 cards and has a committed poison engine with strong defensive scaling via Footworks. We want to maximize the chance of drawing our core scaling cards (Footwork, Noxious Fumes, Nightmare, Well-Laid Plans) rather than adding more transitional cards. None of these options improve our core gameplan enough to justify diluting the deck.
  strategic_note: Committed poison plan: scale defensively via Footwork and Noxious Fumes while using Well-Laid Plans to set up Nightmare on key powers or burst damage. Keep deck thin from here on to draw combo pieces faster.

F45 [map] choose_map_node (option_index=1) | source=llm
  HP 37->37 | Gold 116->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Following the recommended route to the Shop. With 116 gold and a poison-focused deck, I need to look for card removals (Strikes) or defensive scaling pieces like Piercing Wail or another Footwork. Avoiding the Elite at index 0 is consistent with the Route Intelligence for Act 3, which warns that Act 3 elites can be run-ending even with high HP.
  strategic_note: Committed poison engine: scale via Noxious Fumes and Footwork while using Well-Laid Plans to nightmare key powers; focus on card removal and high-value block at the shop to ensure the engine has time to ramp up.

F46 [shop] remove_card_at_shop | source=plan
  HP 37->37 | Gold 116->116 | Deck 38->38
  deck_change: no deck change
  reasoning: Shop plan [1/1]: Removing a basic Strike helps thin our 38-card deck, increasing the consistency of drawing our core poison and block scaling cards.

F46 [card_select] select_deck_card (option_index=0) | source=llm
  HP 37->37 | Gold 116->16 | Deck 38->37
  deck_change: lost Strike
  reasoning: Strikes are completely obsolete in Act 3, especially for a deck relying on Poison and Dexterity. Removing one improves consistency in drawing our defensive skills and poison scaling.
  strategic_note: Committed poison/dexterity plan: scale defense with multiple Footworks and damage with Noxious Fumes and targeted poison. Use Nightmare on Footwork or strong block/draw to out-scale bosses. Remove remaining Strikes.

F46 [shop] close_shop_inventory | source=llm
  HP 37->37 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F46 [shop] proceed | source=auto
  HP 37->37 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=21, note_scope=run, note_triggers=all) | source=llm
  HP 37->37 | Gold 16->16 | Deck 37->37
  deck_change: upgraded Footwork->Footwork+
  reasoning: With Pantograph, we will heal 25 HP at the start of the boss combat, taking us from 37 HP to our max of 58 HP. Resting here would be completely wasted. Since we have Razor Tooth, our Attacks and Skills automatically upgrade upon play, meaning we should prioritize upgrading a Power. Upgrading Footwork increases our Dexterity, which is crucial for scaling block against the Act 3 Boss.
  strategic_note: Committed poison engine: play Footwork and Noxious Fumes to scale defensively while passive poison kills. Use Well-Laid Plans to hold Nightmare for key powers or block cards. Razor Tooth automatically upgrades Skills/Attacks upon play, so permanent upgrades must focus on Powers like Footwork.

F47 [rest_site] proceed | source=auto
  HP 37->37 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 37->58 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [card_select] select_deck_card (option_index=1) | source=llm
  HP 58->58 | Gold 16->0 | Deck 37->37
  deck_change: no deck change
  reasoning: Blur is an excellent defensive tool, especially since we have multiple copies of Footwork in our deck. Banking block during turns where we over-defend will help immensely against the boss's heavy attacks.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Bouncing Flask, and Deadly Poison to stack damage, while scaling Dexterity with Footwork to survive. Focus on surviving with high block and let passive poison do the work. Skip off-plan attacks.

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 16->16 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 16->0 | Gold 16->16 | Deck 37->37
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (10 replays)
[Selected: elite] Byrdonis (F9, elite)
Historical: loss=7 vs historical avg=5.3+/-5.0 (z=0.3, TYPICAL, n=3)
## Combat Replay: vs Byrdonis (Floor 9, elite)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation
Deck (19): Defend x6, Strike x5, Ascender's Bane, Blade Dance, Neutralize, Noxious Fumes, Peck, Poisoned Stab, Skewer+, Survivor
Enemies: Byrdonis HP=81/81

### Round 1
Agent plan (hypothesis): Byrdonis should be close to lethal next turn. Play fast and avoid prolonged scaling.
Intent: Byrdonis: Attack(17)
  Flex Potion
    +Strength(5) | +Flex Potion(5)
  Block Potion
    block +12
  Defend
    energy -1 | block +5
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Byrdonis[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Byrdonis: hp -9
  Shiv -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -9
  Shiv -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -9
  Peck -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: hp -21
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.

### Round 2
Intent: Byrdonis: Attack(4x3=12)
  Defend
    energy -1 | block +5
  Strike -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: hp -6
  Strike -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: hp -6
  turn_end

### Round 3
Agent plan (hypothesis): We survived the elite fight and can now collect our rewards.
Intent: Byrdonis: Attack(19)
  Neutralize -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -3, +Weak(1)
  Skewer+ -> Byrdonis[0]
    energy -3 | enemy_deltas: Byrdonis: DIED
## Combat Analytics: Byrdonis (WIN - 3 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 9 damage. Exhaust." -> 3 plays, 27 dmg, EXHAUST
  Peck "Deal 7 damage 3 times." -> 1 plays, 21 dmg
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Skewer+ "Deal 11 damage X times." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~27 dmg

Enemy power timeline:
  Strength: R1:- -> R2:1 -> R3:2
  Territorial: R1:1 -> R2:1 -> R3:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs Byrdonis (Floor 9, elite)
Relics: Ring of the Snake, Golden Pearl
Deck (21): Defend x5, Strike x5, Ascender's Bane, Backflip, Blade Dance, Dagger Spray, Dagger Throw, Hand of Greed+, Leg Sweep, Neutralize, Piercing Wail, Strangle, Survivor
Enemies: Byrdonis HP=83/83

### Round 1
Intent: Byrdonis: Attack(17)
  Weak Potion -> Byrdonis[0]
    enemy_deltas: Byrdonis: +Weak(3)
  Strangle -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: hp -8, +Strangle(2)
  Cunning Potion
  Shiv+ -> Byrdonis[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Byrdonis: hp -8
  Shiv+ -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -8
  Shiv+ -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -8
  Hand of Greed+ -> Byrdonis[0]
    energy -2 | enemy_deltas: Byrdonis: hp -27
  turn_end

### Round 2
Intent: Byrdonis: Attack(3x3=9)
  Backflip
    energy -1 | block +5
  Blade Dance
    energy -1 | exhausted: Shiv+*3 [0]: Deal 6 damage. Exhaust.
  Shiv -> Byrdonis[0]
    exhausted: Shiv+*3 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Byrdonis: hp -4
  Shiv -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -4
  Shiv -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -4
  Survivor
    energy -1 | block +8
  Strike
  turn_end
    exhausted: Shiv+*3 [0]: Deal 6 damage. Exhaust.

### Round 3
Intent: Byrdonis: Attack(14)
  Neutralize -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -3, Weak(1→2)
  Dagger Spray
    energy -1 | enemy_deltas: Byrdonis: hp -8
  Strike -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: DIED
## Combat Analytics: Byrdonis (WIN - 3 rounds)

Cards played (with descriptions):
  Strangle "Deal 8 damage. Whenever you play a card this turn, the enemy loses 2 HP." -> 1 plays, 8 dmg
  Shiv+ "Deal 6 damage. Exhaust." -> 3 plays, 24 dmg, EXHAUST
  Hand of Greed+ "Deal 25 damage. If Fatal, gain 25 Gold." -> 1 plays, 27 dmg
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg
  Strike "Deal 6 damage." -> 1 plays

Token attribution (Shivs):
  other: 3 Shivs -> ~18 dmg
  Blade Dance: 3 Shivs -> ~18 dmg

Enemy power timeline:
  Strength: R1:- -> R2:1 -> R3:2
  Territorial: R1:1 -> R2:1 -> R3:1
  Weak: R1:- -> R2:2 -> R3:1

[Selected: elite] Phrog Parasite (F15, elite)
## Combat Replay: vs Phrog Parasite (Floor 15, elite)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost
Deck (23): Defend x6, Strike x5, Ascender's Bane, Blade Dance, Deadly Poison, Dodge and Roll, Footwork+, Neutralize, Noxious Fumes+, Peck, Poisoned Stab, Skewer+, Survivor, Well-Laid Plans
Enemies: Phrog Parasite HP=62/62

### Round 1
Agent plan (hypothesis): We will have our full engine online. Next turns focus on blocking and letting Fumes tick, using Retain to hold key cards.
Intent: Phrog Parasite: StatusCard(3)
  Neutralize -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -3, +Weak(1)
  Noxious Fumes+
    energy -1 | block +7 | +Noxious Fumes(3)
  Footwork+
    energy -1 | +Dexterity(3)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end
  Dodge and Roll

### Round 2
Intent: Phrog Parasite: Attack(4x4=16)
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Deadly Poison -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: Poison(3→8)
  Poisoned Stab -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6, Poison(8→11)
  turn_end
  Blade Dance

### Round 3
Agent plan (hypothesis): The enemy will have very low HP and high poison; prepare for the next phase when it dies.
Intent: Phrog Parasite: StatusCard(3)
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Phrog Parasite[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Phrog Parasite: hp -4
  Shiv -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -4
  Shiv -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -4
  Peck -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  turn_end
  Defend

### Round 4
Intent: Phrog Parasite: Attack(4x4=16)
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.
  Skewer+

### Round 5
Intent: Wriggler: Stun, Wriggler: Stun, Wriggler: Stun, Wriggler: Stun
  Skewer+ -> Wriggler[0]
    energy -3
  turn_end
  Peck

### Round 6
Intent: Wriggler: Buff, StatusCard(1), Wriggler: Attack(6), Wriggler: Buff, StatusCard(1)
  Survivor
    energy -1 | block +11
  Infection
  Poisoned Stab -> Wriggler[1]
    energy -1
  Deadly Poison -> Wriggler[2]
    energy -1 | enemy_deltas: Wriggler: Poison(5→10)
  turn_end
  Peck

### Round 7
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Strike -> Wriggler[0]
    energy -1
  Strike -> Wriggler[0]
    energy -1
  Defend
    energy -1 | block +8
  turn_end
  Dodge and Roll
## Combat Analytics: Phrog Parasite (WIN - 7 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 7 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 1 plays, 7 block
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 6 dmg, +3 poison
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Peck "Deal 2 damage 3 times." -> 1 plays, 6 dmg
  Strike "Deal 6 damage." -> 3 plays, 6 dmg
  Defend "Gain 8 Block." -> 4 plays, 32 block
  Skewer+ "Deal 11 damage X times." -> 1 plays
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~12 dmg

Poison stacks applied per card:
  Deadly Poison: 10 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:4 -> R5:- -> R6:- -> R7:-
  Poison: R1:- -> R2:3 -> R3:13 -> R4:15 -> R5:- -> R6:- -> R7:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5 -> R7:7
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5 -> R7:10
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5 -> R7:12
  Poison[3]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:- -> R7:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2

[Selected: boss] Ceremonial Beast (F17, boss)
Historical: loss=18 vs historical avg=30.2+/-11.0 (z=-1.1, BETTER_THAN_USUAL, n=4)
## Combat Replay: vs Ceremonial Beast (Floor 17, boss)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph
Deck (23): Defend x6, Strike x5, Ascender's Bane, Blade Dance, Deadly Poison, Dodge and Roll, Footwork+, Neutralize+, Noxious Fumes+, Peck, Poisoned Stab, Skewer+, Survivor, Well-Laid Plans
Enemies: Ceremonial Beast HP=252/252

### Round 1
Agent plan (hypothesis): Beast will attack next turn, but will be Weakened. Save Energy Potion for burst to hit the 150 HP stun threshold when it matters.
Intent: Ceremonial Beast: Buff
  Footwork+
    energy -1 | block +7 | +Dexterity(3)
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Ceremonial Beast[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Ceremonial Beast: hp -4
  Shiv -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4
  Shiv -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4
  Skewer+ -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -11
  turn_end

### Round 2
Intent: Ceremonial Beast: Attack(13), Buff
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +8
  turn_end
  Deadly Poison

### Round 3
Agent plan (hypothesis): Ascender's Bane exhausts. We will take 9 damage, dropping to 45 HP.
Intent: Ceremonial Beast: Attack(20), Buff
  Deadly Poison -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: Poison(3→8)
  Peck -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Survivor
    energy -1 | block +11
  Strike
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.
  Strike

### Round 4
Agent plan (hypothesis): Save energy potion for the push below 150 HP. Skewer / Blade Dance are coming up.
Intent: Ceremonial Beast: Attack(22), Buff
  Poisoned Stab -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6, Poison(10→13)
  Defend
    energy -1 | block +8
  Survivor
    energy -1 | block +11
  Strike
  turn_end
  Strike

### Round 5
Intent: Ceremonial Beast: Attack(24), Buff
  Energy Potion
    energy +2
  Skewer+ -> Ceremonial Beast[0]
    energy -5 | enemy_deltas: Ceremonial Beast: hp -55, -Plow, -Strength
  turn_end
  Defend

### Round 6
Agent plan (hypothesis): You will be restricted to 1 card next turn. Play the retained Defend (or better if drawn) to block the attack. Use Block Potion if lethal.
Intent: Ceremonial Beast: Debuff
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Peck -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Defend
    energy -1 | block +8
  turn_end
  Defend

### Round 7
Intent: Ceremonial Beast: Attack(11)
  Defend
    energy -1 | block +8
  turn_end
  Deadly Poison

### Round 8
Agent plan (hypothesis): Poison is ticking down the boss. Keep defending.
Intent: Ceremonial Beast: Attack(17), Buff
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  Deadly Poison -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: Poison(21→26)
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Survivor
    energy -1 | block +11
  Strike
  turn_end
  Strike

### Round 9
Agent plan (hypothesis): Boss dies to poison. GG.
Intent: Ceremonial Beast: Debuff
  Skewer+ -> Ceremonial Beast[0]
    energy -3 | enemy_deltas: Ceremonial Beast: hp -33
  turn_end
  Defend
## Combat Analytics: Ceremonial Beast (WIN - 9 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 7 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 12 dmg
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Skewer+ "Deal 11 damage X times." -> 3 plays, 99 dmg
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Defend "Gain 8 Block." -> 4 plays, 32 block
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Peck "Deal 2 damage 3 times." -> 2 plays, 12 dmg
  Survivor "Gain 11 Block. Discard 1 card." -> 3 plays, 33 block
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 1 plays, 7 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~12 dmg

Poison stacks applied per card:
  Deadly Poison: 10 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Plow: R1:- -> R2:150 -> R3:150 -> R4:150 -> R5:150 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:3 -> R4:10 -> R5:15 -> R6:17 -> R7:19 -> R8:21 -> R9:28
  Strength: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:6 -> R6:- -> R7:- -> R8:- -> R9:3
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:1
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Ceremonial Beast (Floor 17, boss)
Relics: Ring of the Snake, Arcane Scroll, Happy Flower
Deck (18): Defend x5, Strike x2, Ascender's Bane, Flick-Flack, Grand Finale, Guilty, Malaise, Neutralize+, Pounce, Skewer+, Sucker Punch+, Survivor+, Toric Toughness
Enemies: Ceremonial Beast HP=252/252

### Round 1
Intent: Ceremonial Beast: Buff
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Flick-Flack
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Ceremonial Beast: Attack(13), Buff
  Touch of Insanity
  Pounce
  Pounce -> Ceremonial Beast[0]
    +Free Skill(1) | enemy_deltas: Ceremonial Beast: hp -12
  Toric Toughness
    block +5 | +Toric Toughness(2) | -Free Skill
  Sucker Punch+ -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -10, Weak(1→3)
  Skewer+ -> Ceremonial Beast[0]
    energy -2 | enemy_deltas: Ceremonial Beast: hp -22
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 3
Intent: Ceremonial Beast: Attack(15), Buff
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Ceremonial Beast: Attack(16), Buff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Survivor+
    energy -1 | block +11
  Guilty
  turn_end

### Round 5
Intent: Ceremonial Beast: Attack(24), Buff
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  Sucker Punch+ -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -10, +Weak(2)
  turn_end

### Round 6
Intent: Ceremonial Beast: Attack(19), Buff
  Pounce -> Ceremonial Beast[0]
    +Free Skill(1) | enemy_deltas: Ceremonial Beast: hp -12
  Defend
    block +5 | -Free Skill
  Defend
    energy -1 | block +5
  Flick-Flack
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  turn_end

### Round 7
Intent: Ceremonial Beast: Attack(28), Buff
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  Skewer+ -> Ceremonial Beast[0]
    energy -3 | enemy_deltas: Ceremonial Beast: hp -33, -Plow, -Strength
  turn_end

### Round 8
Intent: Ceremonial Beast: Debuff
  Pounce -> Ceremonial Beast[0]
    +Free Skill(1) | enemy_deltas: Ceremonial Beast: hp -12
  Toric Toughness
    block +5 | +Toric Toughness(2) | -Free Skill
  Sucker Punch+ -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -10, Weak(1→3)
  Survivor+
    energy -1 | block +11
  turn_end

### Round 9
Intent: Ceremonial Beast: Attack(11)
  Defend
    energy -1 | block +5
  turn_end

### Round 10
Intent: Ceremonial Beast: Attack(12), Buff
  Survivor+
    energy -1 | block +11
  Grand Finale
  Malaise -> Ceremonial Beast[0]
    energy -2 | exhausted: Malaise [X]: Enemy loses X Strength. Apply X Weak. Exhaust. | enemy_deltas: Ceremonial Beast: Weak(1→3), +Strength(-2)
  turn_end

### Round 11
Intent: Ceremonial Beast: Debuff
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, Weak(2→4)
  Skewer+ -> Ceremonial Beast[0]
    energy -3 | enemy_deltas: Ceremonial Beast: hp -33
  turn_end

### Round 12
Intent: Ceremonial Beast: Attack(12)
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  turn_end

### Round 13
Intent: Ceremonial Beast: Attack(13), Buff
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 14
Intent: Ceremonial Beast: Debuff
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  turn_end

### Round 15
Intent: Ceremonial Beast: Attack(19)
  Skewer+ -> Ceremonial Beast[0]
    energy -4 | enemy_deltas: Ceremonial Beast: hp -44
  turn_end

### Round 16
Intent: Ceremonial Beast: Attack(21), Buff
  Pounce -> Ceremonial Beast[0]
    block -5 | enemy_deltas: Ceremonial Beast: DIED
## Combat Analytics: Ceremonial Beast (WIN - 16 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 12 dmg
  Strike "Deal 6 damage." -> 4 plays, 24 dmg
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 2 plays, 12 dmg
  Defend "Gain 5 Block." -> 10 plays, 50 block
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 4 plays, 36 dmg
  Toric Toughness "Gain 5 Block. Gain 5 Block at the start of the next 2 turns." -> 5 plays, 25 block
  Sucker Punch+ "Deal 10 damage. Apply 2 Weak." -> 3 plays, 30 dmg
  Skewer+ "Deal 11 damage X times." -> 4 plays, 132 dmg
  Survivor+ "Gain 11 Block. Discard 1 card." -> 3 plays, 33 block
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST

Enemy power timeline:
  Plow: R1:- -> R2:150 -> R3:150 -> R4:150 -> R5:150 -> R6:150 -> R7:150 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:-
  Strength: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:6 -> R6:8 -> R7:10 -> R8:- -> R9:- -> R10:- -> R11:1 -> R12:1 -> R13:1 -> R14:4 -> R15:4 -> R16:4
  Weak: R1:- -> R2:1 -> R3:2 -> R4:1 -> R5:- -> R6:1 -> R7:- -> R8:1 -> R9:2 -> R10:1 -> R11:2 -> R12:3 -> R13:2 -> R14:1 -> R15:- -> R16:-

[Selected: run_combat] The Obscura (F22, monster)
Historical: loss=37 vs historical avg=2.0+/-2.8 (z=12.4, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs The Obscura (Floor 22, monster)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa
Deck (28): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Blade Dance, Deadly Poison, Deflect, Footwork+, Neutralize+, Nightmare, Noxious Fumes+, Peck, Poisoned Stab, Skewer+, Survivor, Well-Laid Plans
Enemies: The Obscura HP=123/123

### Round 1
Agent plan (hypothesis): Parafright attacks for ~16 next turn. Focus all damage onto Obscura, ignore the reviving minion.
Intent: The Obscura: Summon
  Footwork+
    energy -1 | block +7 | +Dexterity(3)
  Neutralize+ -> The Obscura[0]
    enemy_deltas: The Obscura: hp -4, +Weak(2)
  Strike -> The Obscura[0]
    energy -1 | enemy_deltas: The Obscura: hp -6
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Survivor
    energy -1 | block +11
  Defend
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  Deflect
    block +7
  turn_end

### Round 2
Agent plan (hypothesis): Retain key combo or defensive pieces. Focus all damage on Obscura.
Intent: Parafright: Attack(16), The Obscura: Buff
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Defend
    energy -1 | block +8
  Poisoned Stab -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6, +Poison(3)
  turn_end
  Nightmare

### Round 3
Agent plan (hypothesis): Play the drawn block card to survive.
Agent plan (hypothesis): Retain Noxious Fumes+ with Well-Laid Plans. We take 12 damage this turn.
Intent: Parafright: Attack(19), The Obscura: Attack(9), Defend
  Backflip
    energy -1 | block +8
  Acrobatics
    energy -1
  Strike
  Defend
    energy -1 | block +8
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Noxious Fumes+

### Round 4
Intent: Parafright: Attack(19), The Obscura: Buff
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Defend
    energy -1 | block +8
  turn_end
  Deadly Poison

### Round 5
Intent: Parafright: Attack(22), The Obscura: Attack(16)
  Neutralize+ -> Parafright[0]
    enemy_deltas: Parafright: hp -4, +Weak(2)
  Defend
    energy -1 | block +8
  Deadly Poison -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: Poison(3→8)
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6
  turn_end
  Nightmare

### Round 6
Agent plan (hypothesis): Parafright revives next turn but taking it out when efficient saves huge amounts of HP.
Intent: Parafright: Attack(16), The Obscura: Attack(12), Defend
  Deflect
    block +7
  Defend
    energy -1 | block +8
  Poisoned Stab -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6, Poison(10→13)
  Skewer+ -> Parafright[0]
    energy -1 | enemy_deltas: Parafright: hp -11
  turn_end
  Nightmare

### Round 7
Agent plan (hypothesis): Play the highest block cards with the remaining 2 energy.
Agent plan (hypothesis): Retain Nightmare or let it discard if unneeded.
Intent: Parafright: Attack(22), The Obscura: Attack(16)
  Backflip
    energy -1 | block +8
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Defend
    energy -1 | block +8
  turn_end
  Nightmare

### Round 8
Agent plan (hypothesis): Survive the heavy hits
Intent: Parafright: Attack(22), The Obscura: Buff
  Acrobatics
    energy -1
  Skewer+
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Survivor
    energy -1 | block +11
  Strike
  turn_end
  Nightmare

### Round 9
Agent plan (hypothesis): Victory is secure.
Intent: Parafright: Attack(25), The Obscura: Attack(19)
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Parafright[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Parafright: hp -4
  Shiv -> Parafright[0]
    enemy_deltas: Parafright: hp -4
  Shiv -> The Obscura[1]
    enemy_deltas: The Obscura: hp -4
  Deflect
    block +7
  Backflip
    energy -1 | block +8
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  turn_end
  Nightmare

### Round 10
Intent: Parafright: Attack(25), The Obscura: Buff
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6
  Peck -> The Obscura[1]
    energy -1 | enemy_deltas: Parafright: hp -21, -Poison, DIED; The Obscura: DIED
## Combat Analytics: The Obscura (WIN - 10 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 7 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 8 dmg
  Strike "Deal 6 damage." -> 4 plays, 24 dmg
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 5 plays, 35 block
  Survivor "Gain 11 Block. Discard 1 card." -> 2 plays, 22 block
  Defend "Gain 8 Block." -> 8 plays, 64 block
  Deflect "Gain 7 Block." -> 3 plays, 21 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 12 dmg, +6 poison
  Backflip "Gain 8 Block. Draw 2 cards." -> 3 plays, 24 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Skewer+ "Deal 11 damage X times." -> 1 plays, 11 dmg
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Peck "Deal 2 damage 3 times." -> 1 plays, 21 dmg

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~12 dmg

Poison stacks applied per card:
  Poisoned Stab: 6 stacks
  Deadly Poison: 5 stacks

Enemy power timeline:
  Illusion: R1:- -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1
  Minion: R1:- -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1
  Poison: R1:- -> R2:- -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5 -> R7:3 -> R8:5 -> R9:7 -> R10:3
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:10 -> R7:15 -> R8:17 -> R9:19 -> R10:21
  Strength[0]: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:6 -> R6:6 -> R7:6 -> R8:6 -> R9:9 -> R10:9
  Strength[1]: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:6 -> R6:6 -> R7:6 -> R8:6 -> R9:9 -> R10:9
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs The Obscura (Floor 30, monster)
Relics: Ring of the Drake, Cursed Pearl, Byrdpip, Pantograph, Snecko Skull, Bellows, Amethyst Aubergine, Touch of Orobas, Planisphere
Deck (28): Defend x5, Strike x4, Ascender's Bane, Assassinate, Blur, Bouncing Flask, Bouncing Flask+, Bubble Bubble, Byrd Swoop, Calculated Gamble, Dark Shackles, Deadly Poison, Flick-Flack, Greed, Leg Sweep, Malaise, Neutralize+, Poisoned Stab, Precise Cut, Slice, Survivor
Enemies: The Obscura HP=123/123

### Round 1
Intent: The Obscura: Summon
  Assassinate+ -> The Obscura[0]
    exhausted: Assassinate+ [0]: Innate. Deal 13 damage. Apply 2 Vulnerable. Exhaust. | enemy_deltas: The Obscura: hp -13, +Vulnerable(2)
  Byrd Swoop+ -> The Obscura[0]
    enemy_deltas: The Obscura: hp -27
  Strike+ -> The Obscura[0]
    energy -1 | enemy_deltas: The Obscura: hp -13
  Blur+
    energy -1 | block +8 | +Blur(1)
  Defend+
    energy -1 | block +8
  turn_end

### Round 2
Intent: Parafright: Attack(16), The Obscura: Attack(10)
  Dark Shackles -> Parafright[0]
    exhausted: Dark Shackles [0]: Enemy loses 9 Strength this turn. Exhaust. | enemy_deltas: Parafright: +Strength(-9), +Dark Shackles(9)
  Neutralize+ -> The Obscura[1]
    enemy_deltas: The Obscura: hp -6, +Weak(2)
  Slice -> The Obscura[1]
    enemy_deltas: The Obscura: hp -9
  Poisoned Stab -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -9, +Poison(4)
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -9
  Precise Cut -> The Obscura[1]
    enemy_deltas: The Obscura: hp -16
  turn_end

### Round 3
Intent: Parafright: Attack(16), The Obscura: Attack(4), Defend
  Colorless Potion
  Panic Button
  Panic Button
    block +30 | +No Block(2) | exhausted: Panic Button [0]: Gain 30 Block. You cannot gain Block from cards for 2 turns. Exhaust.
  Bouncing Flask+
    energy -2 | enemy_deltas: Parafright: +Poison(12); The Obscura: Poison(3→7)
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: hp -6
  turn_end
    exhausted: Panic Button [0]: Gain 30 Block. You cannot gain Block from cards for 2 turns. Exhaust.

### Round 4
Intent: Parafright: Attack(16), The Obscura: Attack(10)
  Strike -> The Obscura[1]
    energy -1 | enemy_deltas: The Obscura: block -6
  Flick-Flack
    energy -1 | enemy_deltas: Parafright: hp -9, -Poison, DIED; The Obscura: DIED
## Combat Analytics: The Obscura (WIN - 4 rounds)

Cards played (with descriptions):
  Assassinate+ "Innate. Deal 13 damage. Apply 2 Vulnerable. Exhaust." -> 1 plays, 13 dmg, EXHAUST
  Byrd Swoop+ "Deal 18 damage." -> 1 plays, 27 dmg
  Strike+ "Deal 9 damage." -> 1 plays, 13 dmg
  Blur+ "Gain 8 Block. Block is not removed at the start of your next turn." -> 1 plays, 8 block
  Defend+ "Gain 8 Block." -> 1 plays, 8 block
  Dark Shackles "Enemy loses 9 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 6 dmg
  Slice "Deal 6 damage." -> 1 plays, 9 dmg
  Poisoned Stab "Deal 6 damage. Apply 4 Poison." -> 1 plays, 9 dmg, +4 poison
  Strike "Deal 6 damage." -> 3 plays, 15 dmg
  Precise Cut "Deal 11 damage. Deals 2 less damage for each other card in your Hand." -> 1 plays, 16 dmg
  Panic Button "Gain 30 Block. You cannot gain Block from cards for 2 turns. Exhaust." -> 1 plays, 30 block, EXHAUST
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times. Perfect Fit." -> 1 plays, +16 poison
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 1 plays, 9 dmg

Poison stacks applied per card:
  Bouncing Flask+: 16 stacks
  Poisoned Stab: 4 stacks

Enemy power timeline:
  Illusion: R1:- -> R2:1 -> R3:1 -> R4:1
  Minion: R1:- -> R2:1 -> R3:1 -> R4:1
  Poison: R1:- -> R2:- -> R3:3 -> R4:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:11
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:6
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:-

[Selected: run_combat] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (F25, monster)
Historical: loss=0 vs historical avg=9.6+/-6.2 (z=-1.6, BETTER_THAN_USUAL, n=5)
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (Floor 25, monster)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa
Deck (30): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Deadly Poison, Deflect, Footwork+, Neutralize+, Nightmare, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Skewer+, Survivor, Well-Laid Plans
Enemies: Exoskeleton HP=26/26, Exoskeleton HP=24/24, Exoskeleton HP=28/28, Exoskeleton HP=25/25

### Round 1
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(8)
  Nightmare
    energy -3
  Footwork+
    +Nightmare(3)
  Footwork+
    energy -1 | block +7 | +Dexterity(3)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Defend
    energy -1 | block +8
  turn_end
    exhausted: Nightmare [3]: Choose a card. Next turn, add 3 copies of that card into your Hand. Exhaust.

### Round 2
Intent: Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(3x3=9), Exoskeleton: Buff
  Footwork+
    energy -1 | Dexterity(3→6)
  Footwork+
    energy -1 | Dexterity(6→9)
  Footwork+
    energy -1 | Dexterity(9→12)
  Deflect
    block +16
  turn_end

### Round 3
Agent plan (hypothesis): Use the last energy to full block or apply Weak based on what Acrobatics draws.
Intent: Exoskeleton: Buff, Exoskeleton: Attack(3x3=9), Exoskeleton: Attack(10), Exoskeleton: Attack(3x3=9)
  Acrobatics
    energy -1
  Strike
  Dodge and Roll
    energy -1 | block +16 | +Block Next Turn(16)
  Deadly Poison -> Exoskeleton[1]
    energy -1
  turn_end

### Round 4
Agent plan (hypothesis): Two enemies removed. The poison will finish the remaining soon. Maintain block.
Intent: Exoskeleton: Attack(10), Exoskeleton: Attack(10), Exoskeleton: Buff, Exoskeleton: Attack(10)
  Pounce -> Exoskeleton[3]
    energy -2 | +Free Skill(1) | enemy_deltas: Exoskeleton: hp -9
  Neutralize+ -> Exoskeleton[3]
    enemy_deltas: Exoskeleton: hp -4, +Weak(2)
  Blade Dance
    -Free Skill | exhausted: Nightmare [3]: Choose a card. Next turn, add 3 copies of that card into your Hand. Exhaust.
  Shiv -> Exoskeleton[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Exoskeleton[1]
  Shiv -> Exoskeleton[1]
  Defend
    energy -1 | block +17
  turn_end

### Round 5
Intent: Exoskeleton: Buff, Exoskeleton: Attack(12)
  Backflip+
    energy -1 | block +20
  Strike -> Exoskeleton[1]
    energy -1 | enemy_deltas: Exoskeleton: hp -6
  Deflect
    block +16
  Acrobatics
    energy -1
  Strike
  turn_end

### Round 6
Intent: Exoskeleton: Attack(12)
  Poisoned Stab -> Exoskeleton[0]
    energy -1 | hp +12 | -Dexterity | -Noxious Fumes | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (WIN - 6 rounds)

Cards played (with descriptions):
  Nightmare "Choose a card. Next turn, add 3 copies of that card into your Hand. Exhaust." -> 1 plays, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 4 plays, 7 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 2 plays, 23 block
  Defend "Gain 8 Block." -> 2 plays, 25 block
  Deflect "Gain 16 Block." -> 2 plays, 32 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 1 plays, 9 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, EXHAUST
  Backflip+ "Gain 20 Block. Draw 2 cards." -> 1 plays, 20 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~0 dmg

Enemy power timeline:
  Hard to Kill: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:9
  Hard to Kill[0]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:-
  Hard to Kill[1]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:-
  Hard to Kill[2]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:- -> R6:-
  Hard to Kill[3]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:- -> R6:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:11
  Poison[0]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:-
  Poison[1]: R1:- -> R2:3 -> R3:5 -> R4:12 -> R5:9 -> R6:-
  Poison[2]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:- -> R6:-
  Poison[3]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:- -> R6:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:4
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:-
  Strength[1]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:4 -> R6:-
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:- -> R6:-
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:- -> R6:-
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (Floor 25, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh
Deck (23): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor, Well-Laid Plans+
Enemies: Exoskeleton HP=24/24, Exoskeleton HP=26/26, Exoskeleton HP=25/25, Exoskeleton HP=28/28

### Round 1
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(8)
  Neutralize+ -> Exoskeleton[1]
  Escape Plan
    block +3
  Leg Sweep -> Exoskeleton[3]
    energy -2 | block +11 | enemy_deltas: Exoskeleton: +Weak(2)
  Backflip
    energy -1 | block +5
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(10), Exoskeleton: Buff
  Afterimage
    energy -1 | +Afterimage(1)
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Defend
    energy -1 | block +6
  turn_end
  Finisher
  Strike

### Round 3
Intent: Exoskeleton: Buff, Exoskeleton: Attack(10), Exoskeleton: Buff, Exoskeleton: Attack(10)
  Leading Strike -> Exoskeleton[1]
    energy -1 | block +1
  Shiv -> Exoskeleton[1]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Exoskeleton[1]
    block +1
  Leading Strike -> Exoskeleton[1]
    energy -1 | block +1
  Shiv -> Exoskeleton[1]
    block +1
  Shiv -> Exoskeleton[1]
    block +1
  Finisher -> Exoskeleton[2]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -3
  Strike -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -6
  turn_end
  Defend
  Survivor

### Round 4
Intent: Exoskeleton: Attack(10), Exoskeleton: Attack(12)
  Escape Plan
    block +1
  Strangle+ -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -9, +Strangle(3)
  Strike -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -9
  Expose -> Exoskeleton[1]
    block +1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Exoskeleton: hp +23, Strength(4→2), -Strangle
  Defend
    energy -1 | block +6
  Finisher -> Exoskeleton[0]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -12
  turn_end
  Survivor
  Envenom+

### Round 5
Intent: Exoskeleton: Buff
  Leading Strike -> Exoskeleton[0]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -3
  Neutralize+ -> Exoskeleton[0]
    block +1 | enemy_deltas: Exoskeleton: hp -4, +Weak(2)
  Shiv -> Exoskeleton[0]
    block +1 | enemy_deltas: Exoskeleton: hp -4
  Shiv -> Exoskeleton[0]
    block -3 | -Afterimage | -Well-Laid Plans | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (WIN - 5 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg, 1 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 4 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Defend "Gain 5 Block." -> 2 plays, 12 block
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 3 dmg, 3 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 4 dmg, 5 block, EXHAUST
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 6 times)" -> 2 plays, 15 dmg, 2 block
  Strike "Deal 6 damage." -> 2 plays, 15 dmg, 2 block
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 9 dmg, 1 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~4 dmg

Enemy power timeline:
  Hard to Kill: R1:- -> R2:- -> R3:- -> R4:- -> R5:9
  Hard to Kill[0]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:-
  Hard to Kill[1]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:-
  Hard to Kill[2]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Hard to Kill[3]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:-
  Strength[1]: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:-
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Weak[1]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-
  Weak[3]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-

[Selected: elite] Entomancer (F28, elite)
Historical: loss=9 vs historical avg=18.0+/-9.4 (z=-1.0, TYPICAL, n=3)
## Combat Replay: vs Entomancer (Floor 28, elite)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth
Deck (31): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Deadly Poison, Deflect, Expertise+, Footwork+, Neutralize+, Nightmare, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Skewer+, Survivor, Well-Laid Plans
Enemies: Entomancer HP=145/145

### Round 1
Agent plan (hypothesis): See what we draw from Acrobatics, hopefully a block card. Save Poisoned Stab or use remaining energy appropriately.
Agent plan (hypothesis): Watch out for Dazed pollution. Set up Noxious Fumes or Catalyst soon.
Intent: Entomancer: Attack(3x7=21)
  Footwork+
    energy -1 | block +7 | +Dexterity(3)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +8
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Acrobatics
    energy -1
  Skewer+
  Backflip+
    energy -1 | block +11
  Neutralize+ -> Entomancer[0]
    enemy_deltas: Entomancer: hp -4, +Weak(2)
  Poisoned Stab -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6, +Poison(3)
  turn_end

### Round 2
Agent plan (hypothesis): Avoid playing Strikes to prevent Dazed bloat unless pushing for a kill.
Agent plan (hypothesis): Next turn is a Buff turn, focus on setting up Noxious Fumes or pushing safe damage if any.
Intent: Entomancer: Attack(13)
  Deflect
    block +7
  Expertise+
    energy -1
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Defend
    energy -1 | block +8
  turn_end
    exhausted: Dazed [0]: Unplayable. Ethereal.

### Round 3
Agent plan (hypothesis): Avoid multi-hits like Peck to prevent Dazed bloat. Use remaining energy on poison or WLP.
Agent plan (hypothesis): Next turn will be a heavy multi-attack (potentially 4x7=28). Prepare to block heavily.
Intent: Entomancer: Buff
  Backflip
    energy -1 | block +8
  Pounce -> Entomancer[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Entomancer: hp -12
  turn_end
    exhausted: Dazed*2 [0]: Unplayable. Ethereal.

### Round 4
Agent plan (hypothesis): Takes 9 damage. Next turn is a heavy single attack.
Intent: Entomancer: Attack(4x7=28)
  Deadly Poison -> Entomancer[0]
    -Free Skill | enemy_deltas: Entomancer: Poison(9→14)
  Defend
    energy -1 | block +8
  Defend+
    energy -1 | block +11
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end

### Round 5
Agent plan (hypothesis): Apply Weak with Neutralize+ next to reduce incoming damage from 19 to 14, then block the rest.
Agent plan (hypothesis): Next turn is a Buff turn. Focus on scaling or pushing damage without triggering too many Dazed.
Intent: Entomancer: Attack(19)
  Acrobatics+
    energy -1
  Nightmare
  Neutralize+ -> Entomancer[0]
    enemy_deltas: Entomancer: hp -4, +Weak(2)
  Dodge and Roll+
    energy -1 | block +9 | +Block Next Turn(9)
  Survivor
    energy -1 | block +11
  Strike
  turn_end
  Poisoned Stab+

### Round 6
Intent: Entomancer: Buff
  Pounce+ -> Entomancer[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Entomancer: hp -18
  Backflip+
    block +11 | -Free Skill
  Dodge and Roll+
    energy -1 | block +9 | +Block Next Turn(9)
  turn_end
  Backflip+

### Round 7
Agent plan (hypothesis): Enemy will take 20 poison damage next turn, dropping to 18 HP. Finish it off carefully without triggering too much Dazed, or just let poison finish it.
Intent: Entomancer: Attack(5x7=35)
  Deflect+
    block +10
  Backflip+
    energy -1 | block +11
  Defend
    energy -1 | block +8
  turn_end
  Expertise+

### Round 8
Agent plan (hypothesis): Fight won with poison.
Intent: Entomancer: Attack(20)
  Defend
    energy -1 | block +8
  Defend+
    energy -1 | block +11
  turn_end
  Expertise+
## Combat Analytics: Entomancer (WIN - 8 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 7 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Defend "Gain 8 Block." -> 5 plays, 40 block
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 2 plays, 14 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Backflip+ "Gain 11 Block. Draw 2 cards." -> 3 plays, 33 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 8 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Deflect "Gain 7 Block." -> 1 plays, 7 block
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Backflip "Gain 8 Block. Draw 2 cards." -> 1 plays, 8 block
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 1 plays, 12 dmg
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Defend+ "Gain 11 Block." -> 2 plays, 22 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Dodge and Roll+ "Gain 9 Block. Next turn, gain 9 Block." -> 2 plays, 18 block
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Pounce+ "Deal 18 damage. The next Skill you play costs 0 energy ." -> 1 plays, 18 dmg
  Deflect+ "Gain 10 Block." -> 1 plays, 10 block

Poison stacks applied per card:
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2 -> R6:2 -> R7:3 -> R8:3
  Poison: R1:- -> R2:5 -> R3:7 -> R4:9 -> R5:16 -> R6:18 -> R7:20 -> R8:22
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:1 -> R7:2 -> R8:2
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Entomancer (Floor 25, elite)
Relics: Ring of the Snake, Neow's Bones, New Leaf, Small Capsule, Centennial Puzzle, The Chosen Cheese, Pendulum, Radiant Pearl, Snecko Skull
Deck (23): Defend x5, Strike x3, Afterimage, Ascender's Bane, Backflip, Backstab, Bouncing Flask+, Cloak and Dagger, Dagger Spray+, Expertise+, Flick-Flack, Neutralize+, Piercing Wail, Predator, Strangle+, Survivor, Tools of the Trade
Enemies: Entomancer HP=145/145

### Round 1
Intent: Entomancer: Attack(3x7=21)
  Luminesce
    energy +2 | exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.
  Bouncing Flask+
    energy -2 | enemy_deltas: Entomancer: +Poison(16)
  Cloak and Dagger
    energy -1 | block +6
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.

### Round 2
Intent: Entomancer: Attack(18)
  Afterimage
    energy -1 | +Afterimage(1)
  Defend
    energy -1 | block +6
  Survivor
    energy -1 | block +8
  Predator
  turn_end

### Round 3
Intent: Entomancer: Buff
  Neutralize+ -> Entomancer[0]
    block +1 | enemy_deltas: Entomancer: hp -4, +Weak(2)
  turn_end

### Round 4
Intent: Entomancer: Attack(3x7=21)
  Piercing Wail
    energy -1 | block +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Entomancer: Strength(1→-5), +Piercing Wail(6)
  Backflip
    energy -1 | block +6
  turn_end
    exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust.

### Round 5
Intent: Entomancer: Attack(19)
  Neutralize+ -> Entomancer[0]
    block +1 | enemy_deltas: Entomancer: hp -4, +Weak(2)
  Bouncing Flask+
    energy -2 | block +1 | enemy_deltas: Entomancer: Poison(12→28)
  Shiv -> Entomancer[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Entomancer: hp -4
  Survivor
    energy -1 | block +9
  turn_end

### Round 6
Intent: Entomancer: Buff
  Backstab -> Entomancer[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Entomancer: hp -11
  Expertise+
    energy -1 | block +1
  Strike -> Entomancer[0]
    energy -1 | block +1 | enemy_deltas: Entomancer: hp -6
  turn_end

### Round 7
Intent: Entomancer: Attack(5x7=35)
  Strangle+ -> Entomancer[0]
    energy -1 | hp +1 | -Afterimage | enemy_deltas: Entomancer: DIED
## Combat Analytics: Entomancer (WIN - 7 rounds)

Cards played (with descriptions):
  Luminesce "Retain. Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 2 plays, 1 block, +32 poison
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 1 plays, 6 block, generates 1 Shivs
  Defend "Gain 5 Block." -> 2 plays, 11 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 17 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 8 dmg, 2 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 6 block
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 4 dmg, 1 block, EXHAUST
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, 1 block, EXHAUST
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg, 1 block
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays

Token attribution (Shivs):
  other: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Bouncing Flask+: 32 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2 -> R6:2 -> R7:3
  Poison: R1:- -> R2:15 -> R3:14 -> R4:13 -> R5:12 -> R6:27 -> R7:26
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:1 -> R7:2
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:-

[Selected: boss] Knowledge Demon (F33, boss)
Historical: loss=29 vs historical avg=29.4+/-17.4 (z=-0.0, TYPICAL, n=5)
## Combat Replay: vs Knowledge Demon (Floor 33, boss)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth, Book of Five Rings
Deck (34): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Deadly Poison, Deflect, Expertise+, Footwork, Footwork+, Neutralize+, Nightmare+, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Prepared, Skewer+, Slice, Survivor, Well-Laid Plans+
Enemies: Knowledge Demon HP=379/379

### Round 1
Agent plan (hypothesis): Evaluate drawn cards. Prioritize setting up scaling powers or Well-Laid Plans, then dump remaining energy into Skewer+ or other attacks.
Agent plan (hypothesis): See what Backflip draws
Agent plan (hypothesis): Save Speed Potion for Turn 3 multi-attack.
Intent: Knowledge Demon: Debuff
  Prepared
  Strike
  Strength Potion
    +Strength(2)
  Backflip
    energy -1 | block +5
  Noxious Fumes+
    energy -1 | block +7 | +Noxious Fumes(3)
  Slice -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Poisoned Stab -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -8, +Poison(3)
  Peck -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -12
  Skewer+ -> Knowledge Demon[0]
    energy -3 | enemy_deltas: Knowledge Demon: hp -39
  turn_end
  Disintegration
    +Disintegration(6)

### Round 2
Agent plan (hypothesis): Use Speed Potion next turn for the multi-attack.
Intent: Knowledge Demon: Attack(17)
  Expertise+
    energy -1
  Backflip+
    energy -1 | block +8
  Footwork
    energy -1 | +Dexterity(2)
  turn_end

### Round 3
Intent: Knowledge Demon: Attack(8x3=24)
  Speed Potion
    Dexterity(2→7) | +Speed Potion(5)
  Deflect
    block +11
  Defend
    energy -1 | block +12
  Defend
    energy -1 | block +12
  Blade Dance
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust.
  Shiv -> Knowledge Demon[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Knowledge Demon: hp -6
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -6
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -6
  turn_end

### Round 4
Agent plan (hypothesis): Ascender's Bane will exhaust. Next turn is debuff, then heavy attack.
Intent: Knowledge Demon: Attack(11), Heal, Buff
  Footwork+
    energy -1 | Dexterity(2→5)
  Defend
    energy -1 | block +10
  Deadly Poison -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: Poison(9→14)
  turn_end
    exhausted: Shiv+*3 [0]: Deal 6 damage. Exhaust.

### Round 5
Intent: Knowledge Demon: Debuff
  Pounce -> Knowledge Demon[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Knowledge Demon: hp -14
  Nightmare+
    -Free Skill
  Neutralize+
    +Nightmare(3)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -6, +Weak(2)
  Slice+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -11
  Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -8
  turn_end
    hp -6
  Sloth
    +Sloth(3)

### Round 6
Intent: Knowledge Demon: Attack(14)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -6, Weak(1→3)
  Dodge and Roll
    energy -1 | block +9 | +Block Next Turn(9)
  Defend
    energy -1 | block +10
  turn_end

### Round 7
Agent plan (hypothesis): Dodge and roll gives block for next turn.
Intent: Knowledge Demon: Attack(7x3=21)
  Acrobatics
    energy -1
  Peck+
  Dodge and Roll
    energy -1 | block +9 | +Block Next Turn(9)
  Defend
    energy -1 | block +10
  turn_end

### Round 8
Agent plan (hypothesis): Retain Survivor and Defend+ or Deflect+ to prepare for the heavy multi-attack.
Intent: Knowledge Demon: Attack(9), Heal, Buff
  Backflip+
    energy -1 | block +13
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Poisoned Stab+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10, Poison(22→26)
  turn_end
  Survivor
  Deflect+

### Round 9
Intent: Knowledge Demon: Debuff
  Deadly Poison+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: Poison(28→35)
  Dodge and Roll+
    energy -1 | block +11 | +Block Next Turn(11)
  Backflip+
    energy -1 | block +13
  turn_end
  Survivor
  Deflect+
  Disintegration
    Disintegration(6→14)

### Round 10
Agent plan (hypothesis): Retain Deflect+. Expect the multi-attack next turn, but Weak and Dodge and Roll block will blunt it.
Intent: Knowledge Demon: Attack(21)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -6, +Weak(2)
  Dodge and Roll+
    energy -1 | block +11 | +Block Next Turn(11)
  Poisoned Stab+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10, Poison(37→41)
  turn_end
  Deflect+
  Acrobatics+

### Round 11
Agent plan (hypothesis): Retain Neutralize+ for next turn if WLP triggers.
Intent: Knowledge Demon: Attack(9x3=27)
  Pounce+ -> Knowledge Demon[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Knowledge Demon: hp -20
  Deflect+
    block +12 | -Free Skill
  Defend+
    energy -1 | block +13
  turn_end
  Neutralize+
  Acrobatics+

### Round 12
Agent plan (hypothesis): We win! Act 3 here we come.
Intent: Knowledge Demon: Attack(15), Heal, Buff
  Peck+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -16
  Slice+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -11
  Strike -> Knowledge Demon[0]
    energy -1 | hp +12 | -Strength | -Noxious Fumes | -Disintegration | -Dexterity | -Sloth | -Well-Laid Plans | enemy_deltas: Knowledge Demon: DIED
## Combat Analytics: Knowledge Demon (WIN - 12 rounds)

Cards played (with descriptions):
  Prepared "Draw 1 card. Discard 1 card." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 7 block
  Slice "Deal 8 damage." -> 1 plays, 8 dmg
  Poisoned Stab "Deal 8 damage. Apply 3 Poison." -> 1 plays, 8 dmg, +3 poison
  Peck "Deal 4 damage 3 times." -> 1 plays, 12 dmg
  Skewer+ "Deal 13 damage X times." -> 1 plays, 39 dmg
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 3 plays, 34 block
  Footwork "Gain 2 Dexterity." -> 1 plays
  Deflect "Gain 11 Block." -> 1 plays, 11 block
  Defend "Gain 12 Block." -> 5 plays, 54 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 3 plays, 18 dmg, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Pounce "Deal 14 damage. The next Skill you play costs 0 energy ." -> 1 plays, 14 dmg
  Nightmare+ "Choose a card. Next turn, add 3 copies of that card into your Hand. Exhaust." -> 1 plays, EXHAUST
  Neutralize+ "Deal 6 damage. Apply 2 Weak." -> 3 plays, 18 dmg
  Slice+ "Deal 11 damage." -> 2 plays, 22 dmg
  Strike "Deal 8 damage." -> 2 plays, 8 dmg
  Dodge and Roll "Gain 9 Block. Next turn, gain 9 Block." -> 2 plays, 18 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Poisoned Stab+ "Deal 10 damage. Apply 4 Poison." -> 2 plays, 20 dmg, +8 poison
  Deadly Poison+ "Apply 7 Poison." -> 1 plays, +7 poison
  Dodge and Roll+ "Gain 11 Block. Next turn, gain 11 Block." -> 2 plays, 22 block
  Pounce+ "Deal 20 damage. The next Skill you play costs 0 energy ." -> 1 plays, 20 dmg
  Deflect+ "Gain 12 Block." -> 1 plays, 12 block
  Defend+ "Gain 13 Block." -> 1 plays, 13 block
  Peck+ "Deal 4 damage 4 times." -> 1 plays, 16 dmg

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~18 dmg

Poison stacks applied per card:
  Poisoned Stab+: 8 stacks
  Deadly Poison+: 7 stacks
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:5 -> R3:7 -> R4:9 -> R5:16 -> R6:18 -> R7:20 -> R8:22 -> R9:28 -> R10:37 -> R11:43 -> R12:45
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4 -> R11:4 -> R12:4
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:2 -> R8:1 -> R9:- -> R10:- -> R11:1 -> R12:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Knowledge Demon (Floor 33, boss)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood, Letter Opener
Deck (27): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Blade of Ink, Cloak and Dagger, Dash+, Defend+, Deflect, Expose, Exterminate, Flick-Flack, Leading Strike, Neutralize, Piercing Wail, Prepared+, Skewer+, Survivor+, Tracking+, Well-Laid Plans+
Enemies: Knowledge Demon HP=379/379

### Round 1
Intent: Knowledge Demon: Debuff
  Dexterity Potion
    +Dexterity(2)
  Tracking+
    energy -1 | +Tracking(2)
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: hp -6, +Weak(1)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(1→2)
  Exterminate
    energy -1 | block +4 | enemy_deltas: Knowledge Demon: hp -88
  turn_end
  Disintegration
    +Disintegration(6)

### Round 2
Intent: Knowledge Demon: Attack(12)
  Dash+ -> Knowledge Demon[0]
    energy -2 | block +15 | enemy_deltas: Knowledge Demon: hp -26
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Prepared+
  Flick-Flack
  Strike
  Expose -> Knowledge Demon[0]
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: +Vulnerable(2)
  turn_end
  Defend
  Defend

### Round 3
Intent: Knowledge Demon: Attack(8x3=24)
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, +Weak(1)
  Piercing Wail
    energy -1 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: +Strength(-6), +Piercing Wail(6)
  Leading Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9
  Shiv -> Knowledge Demon[0]
    block +4 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  turn_end
  Defend
  Backflip

### Round 4
Intent: Knowledge Demon: Attack(11), Heal, Buff
  Deflect
    block +6
  Backflip
    energy -1 | block +7
  Leading Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -3
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -4
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -4
  Skewer+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -11
  turn_end
    exhausted: Shiv*7 [0]: Deal 4 damage. Exhaust.
  Survivor+
  Defend+

### Round 5
Intent: Knowledge Demon: Debuff
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5, +Weak(1)
  Prepared+
  Strike+
  Strike+
  Blade of Ink
    energy -1
  Cloak and Dagger
    energy -1 | block +8 | enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(1→2)
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -12, Weak(2→3)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Exterminate
    energy -1 | enemy_deltas: Knowledge Demon: hp -24
  turn_end
  Survivor+
  Dash+
  Disintegration
    Disintegration(6→13)

### Round 6
Intent: Knowledge Demon: Attack(14)
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(2→3)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(3→4)
  Leading Strike -> Knowledge Demon[0]
    energy -1 | block +4 | enemy_deltas: Knowledge Demon: hp -6
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Survivor+
    energy -1 | block +13
  Flick-Flack
  turn_end
    block +4 | enemy_deltas: Knowledge Demon: hp -12
  Dash+
  Defend

### Round 7
Intent: Knowledge Demon: Attack(7x3=21)
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -10, Weak(3→4)
  Dash+ -> Knowledge Demon[0]
    energy -2 | block +15 | enemy_deltas: Knowledge Demon: hp -26
  Strike+ -> Knowledge Demon[0]
    energy -1 | block -15 | -Dexterity | -Tracking | -Disintegration | -Well-Laid Plans | enemy_deltas: Knowledge Demon: DIED
## Combat Analytics: Knowledge Demon (WIN - 7 rounds)

Cards played (with descriptions):
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 3 plays
  Shiv "Deal 6 damage. Apply 1 Weak. Exhaust." -> 16 plays, 158 dmg, 16 block, EXHAUST
  Exterminate "Deal 11 damage 4 times to ALL enemies." -> 2 plays, 112 dmg, 4 block
  Dash+ "Gain 15 Block. Deal 13 damage." -> 2 plays, 52 dmg, 30 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 3 plays, 22 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 18 dmg, 4 block, generates 2 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Deflect "Gain 6 Block." -> 1 plays, 6 block
  Backflip "Gain 7 Block. Draw 2 cards." -> 1 plays, 7 block
  Skewer+ "Deal 11 damage X times." -> 1 plays, 11 dmg
  Cloak and Dagger "Gain 8 Block. Add 1 Shiv into your Hand." -> 1 plays, 5 dmg, 8 block, generates 1 Shivs
  Survivor+ "Gain 13 Block. Discard 1 card." -> 1 plays, 13 block
  Strike+ "Deal 9 damage." -> 1 plays

Token attribution (Shivs):
  other: 6 Shivs -> ~59 dmg
  Leading Strike: 6 Shivs -> ~59 dmg
  Blade Dance: 3 Shivs -> ~30 dmg
  Cloak and Dagger: 1 Shivs -> ~10 dmg

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:3

[Selected: run_combat] Devoted Sculptor (F37, monster)
Historical: loss=36 vs historical avg=6.0+/-9.2 (z=3.3, WORSE_THAN_USUAL, n=6)
## Combat Replay: vs Devoted Sculptor (Floor 37, monster)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth, Book of Five Rings, Delicate Frond
Deck (36): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Bouncing Flask, Deadly Poison, Deflect, Expertise+, Footwork, Footwork+, Neutralize+, Nightmare+, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Prepared, Skewer+, Slice, Survivor, Tools of the Trade, Well-Laid Plans+
Enemies: Devoted Sculptor HP=162/162

### Round 1
Agent plan (hypothesis): See what 0-costs we draw.
Intent: Devoted Sculptor: Buff
  Noxious Fumes+
    energy -1 | block +7 | +Noxious Fumes(3)
  Slice -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -6
  Poisoned Stab -> Devoted Sculptor[0]
    energy -1 | enemy_deltas: Devoted Sculptor: hp -6, +Poison(3)
  Prepared
  Strike
  Powdered Demise -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: +Demise(9)
  Blade Dance
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust.
  Shiv -> Devoted Sculptor[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Devoted Sculptor: hp -4
  Shiv -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -4
  Shiv -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -4
  Peck -> Devoted Sculptor[0]
    energy -1 | enemy_deltas: Devoted Sculptor: hp -6
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Dodge and Roll
    energy -1 | block +4 | Block Next Turn(4→8)
  Expertise+
    energy -1
  turn_end

### Round 2
Agent plan (hypothesis): Evaluate drawn cards for the remaining 1 energy.
Agent plan (hypothesis): Draw pile will be empty after next turn's draw.
Intent: Devoted Sculptor: Attack(12)
  Neutralize+ -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -4, +Weak(2)
  Acrobatics
    energy -1
  Defend
  Backflip
    energy -1 | block +5
  Deadly Poison -> Devoted Sculptor[0]
    energy -1 | enemy_deltas: Devoted Sculptor: Poison(5→10)
  turn_end
    exhausted: Shiv+*3 [0]: Deal 6 damage. Exhaust.

### Round 3
Agent plan (hypothesis): Will take 10 damage. Enemy HP dropping steadily to Poison and Demise.
Intent: Devoted Sculptor: Attack(15)
  Defend
    energy -1 | block +5
  Strike -> Devoted Sculptor[0]
    energy -1 | enemy_deltas: Devoted Sculptor: hp -6
  Strike -> Devoted Sculptor[0]
    energy -1 | enemy_deltas: Devoted Sculptor: hp -6
  turn_end

### Round 4
Intent: Devoted Sculptor: Attack(30)
  Footwork
    energy -1 | +Dexterity(2)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Deflect
    block +6
  turn_end

### Round 5
Agent plan (hypothesis): Enemy HP will drop below 20 next turn from Poison; prioritize lethal or weak if it survives.
Intent: Devoted Sculptor: Attack(39)
  Footwork+
    energy -1 | Dexterity(2→5)
  Defend
    energy -1 | block +10
  Survivor
    energy -1 | block +13
  Strike
  turn_end

### Round 6
Agent plan (hypothesis): Kill the enemy! If you don't draw an attack, use Foul Potion + Strike+.
Intent: Devoted Sculptor: Attack(48)
  Acrobatics+
    energy -1
  Strike
  Foul Potion
    hp -12 | enemy_deltas: Devoted Sculptor: hp -12
  Strike+ -> Devoted Sculptor[0]
    energy -1 | hp +12 | -Noxious Fumes | -Dexterity | enemy_deltas: Devoted Sculptor: DIED
## Combat Analytics: Devoted Sculptor (WIN - 6 rounds)

Cards played (with descriptions):
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 7 block
  Slice "Deal 6 damage." -> 1 plays, 6 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Prepared "Draw 1 card. Discard 1 card." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Peck "Deal 2 damage 3 times." -> 1 plays, 6 dmg
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 2 plays, 8 block
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Defend "Gain 5 Block." -> 4 plays, 29 block
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Footwork "Gain 2 Dexterity." -> 1 plays
  Deflect "Gain 6 Block." -> 1 plays, 6 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Survivor "Gain 13 Block. Discard 1 card." -> 1 plays, 13 block
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Strike+ "Deal 9 damage." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~12 dmg

Poison stacks applied per card:
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Demise: R1:- -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:9
  Poison: R1:- -> R2:5 -> R3:12 -> R4:14 -> R5:16 -> R6:18
  Ritual: R1:- -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:9
  Strength: R1:- -> R2:- -> R3:9 -> R4:18 -> R5:27 -> R6:36
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Devoted Sculptor (Floor 35, monster)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood, Letter Opener, Brilliant Scarf
Deck (28): Defend x4, Strike x2, Strike+ x2, Adrenaline, Ascender's Bane, Backflip, Blade Dance, Blade of Ink, Cloak and Dagger, Dash+, Defend+, Deflect, Expose, Exterminate, Flick-Flack, Leading Strike, Neutralize, Piercing Wail, Prepared+, Skewer+, Survivor+, Tracking+, Well-Laid Plans+
Enemies: Devoted Sculptor HP=162/162

### Round 1
Intent: Devoted Sculptor: Buff
  Adrenaline
    energy +1 | exhausted: Adrenaline [0]: Gain 1 energy . Draw 2 cards. Exhaust.
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Expose -> Devoted Sculptor[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Devoted Sculptor: +Vulnerable(2)
  Blade of Ink
    energy -1 | enemy_deltas: Devoted Sculptor: hp -5
  Strike+ -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -13
  Exterminate
    energy -1 | enemy_deltas: Devoted Sculptor: hp -64
  Shiv -> Devoted Sculptor[0]
    block +4 | exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Devoted Sculptor: hp -9, +Weak(1)
  Shiv -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -9, Weak(1→2)
  turn_end
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Defend
  Piercing Wail

### Round 2
Intent: Devoted Sculptor: Attack(9)
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Devoted Sculptor[0]
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Devoted Sculptor: hp -6
  Shiv -> Devoted Sculptor[0]
    enemy_deltas: Devoted Sculptor: hp -6
  Shiv -> Devoted Sculptor[0]
    block +4 | enemy_deltas: Devoted Sculptor: hp -6
  Dash+ -> Devoted Sculptor[0]
    block +13 | enemy_deltas: Devoted Sculptor: hp -19
  Backflip
    energy -1 | block +5
  Prepared+
  Flick-Flack
  Defend
  Skewer+ -> Devoted Sculptor[0]
    energy -1 | block -22 | -Well-Laid Plans | enemy_deltas: Devoted Sculptor: DIED
## Combat Analytics: Devoted Sculptor (WIN - 2 rounds)

Cards played (with descriptions):
  Adrenaline "Gain 1 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 1 plays, 5 dmg
  Strike+ "Deal 9 damage." -> 1 plays, 13 dmg
  Exterminate "Deal 11 damage 4 times to ALL enemies." -> 1 plays, 64 dmg
  Shiv "Deal 6 damage. Apply 1 Weak. Exhaust." -> 5 plays, 36 dmg, 8 block, EXHAUST
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Dash+ "Gain 13 Block. Deal 13 damage." -> 1 plays, 19 dmg, 13 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 1 plays
  Skewer+ "Deal 11 damage X times." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~22 dmg
  other: 2 Shivs -> ~14 dmg

Enemy power timeline:
  Ritual: R1:- -> R2:9
  Vulnerable: R1:- -> R2:1
  Weak: R1:- -> R2:1

[Selected: run_combat] Slimed Berserker (F42, monster)
Historical: loss=0 vs historical avg=9.0+/-5.7 (z=-1.6, BETTER_THAN_USUAL, n=3)
## Combat Replay: vs Slimed Berserker (Floor 42, monster)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth, Book of Five Rings, Delicate Frond, Regal Pillow, Oddly Smooth Stone
Deck (37): Defend x6, Strike x5, Dodge and Roll x2, Footwork x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Bouncing Flask, Deadly Poison, Deflect, Expertise+, Footwork+, Neutralize+, Nightmare+, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Prepared, Skewer+, Slice, Survivor, Tools of the Trade, Well-Laid Plans+
Enemies: Slimed Berserker HP=266/266

### Round 1
Agent plan (hypothesis): Retain Neutralize+
Intent: Slimed Berserker: StatusCard(10)
  Noxious Fumes+
    energy -1 | block +7 | +Noxious Fumes(3)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Poisoned Stab -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -6, +Poison(3)
  Deflect
    block +5
  Backflip+
    energy -1 | block +9
  Strike -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -6
  Strike -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -6
  Survivor
    energy -1 | block +9
  Defend
  turn_end
  Neutralize+
  Defend

### Round 2
Agent plan (hypothesis): Will play 2 Defends after drawing unless we get something better.
Agent plan (hypothesis): Retain Bouncing Flask. Expect the Berserker to buff and debuff next turn.
Intent: Slimed Berserker: Attack(4x4=16)
  Neutralize+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -4, +Weak(2)
  Acrobatics
    energy -1
  Strike
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Bouncing Flask
  confirm

### Round 3
Intent: Slimed Berserker: Debuff, Buff
  Footwork
    energy -1 | Dexterity(1→3)
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  Prepared
  Strike
  Deadly Poison -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: Poison(7→12)
  turn_end
  Bouncing Flask
  Defend
  Strike

### Round 4
Agent plan (hypothesis): Retain Bouncing Flask to apply poison after the status flood.
Intent: Slimed Berserker: Attack(33)
  Skill Potion
  Deflect
  Footwork+
    energy -1 | Dexterity(3→6)
  Deflect
    block +10
  Defend
    energy -1 | block +11
  Defend
    energy -1 | block +11
  turn_end
  Bouncing Flask
  Backflip
  Slice

### Round 5
Intent: Slimed Berserker: StatusCard(10)
  Bouncing Flask
    energy -2 | enemy_deltas: Slimed Berserker: Poison(16→25)
  Backflip
    energy -1 | block +11
  turn_end
  Nightmare+
  Footwork
  Strike

### Round 6
Intent: Slimed Berserker: Attack(7x4=28)
  Footwork
    energy -1 | Dexterity(6→8)
  Dodge and Roll
    energy -1 | block +12 | +Block Next Turn(12)
  Defend
    energy -1 | block +13
  Slice -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -4
  turn_end
  Nightmare+
  confirm
  Strike

### Round 7
Intent: Slimed Berserker: Debuff, Buff
  Nightmare+
    energy -2
  Deflect+
    +Nightmare(3)
  Slimed
    energy -1 | exhausted: Slimed [1]: Draw 1 card. Exhaust.
  Deflect+
    block +15
  turn_end
  Defend
  Acrobatics+
  Slimed

### Round 8
Agent plan (hypothesis): Retain cards that matter for the next damage window.
Intent: Slimed Berserker: Attack(36)
  Deflect+
    block +15
  Deflect+
    block +15
  Deflect+
    block +15
  Deadly Poison+ -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: Poison(31→38)
  Prepared+
  Strike+
  Defend+
  Deflect+
    block +15
  Acrobatics+
    energy -1
  Peck
  Neutralize+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -3, +Weak(2)
  Dodge and Roll
    energy -1 | block +12 | +Block Next Turn(12)
  turn_end
  Defend
  Survivor+
  Strike

### Round 9
Agent plan (hypothesis): Combat is mathematically solved.
Intent: Slimed Berserker: StatusCard(10)
  Bouncing Flask+
    energy -2 | enemy_deltas: Slimed Berserker: Poison(40→52)
  Skewer+ -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -8
  turn_end
  Defend
  Survivor+
  Slimed

### Round 10
Intent: Slimed Berserker: Attack(10x4=40)
  Neutralize+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -3, +Weak(2)
  Defend
    energy -1 | block +13
  Defend+
    energy -1 | block +16
  Survivor+
    energy -1 | block +19
  Defend+
  turn_end
  Backflip+
  Defend+
## Combat Analytics: Slimed Berserker (WIN - 10 rounds)

Cards played (with descriptions):
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 7 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Deflect "Gain 5 Block." -> 2 plays, 15 block
  Backflip+ "Gain 9 Block. Draw 2 cards." -> 1 plays, 9 block
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 10 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Defend "Gain 6 Block." -> 6 plays, 60 block
  Footwork "Gain 2 Dexterity." -> 2 plays
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Prepared "Draw 1 card. Discard 1 card." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, +9 poison
  Backflip "Gain 11 Block. Draw 2 cards." -> 1 plays, 11 block
  Dodge and Roll "Gain 12 Block. Next turn, gain 12 Block." -> 2 plays, 24 block
  Slice "Deal 4 damage." -> 1 plays, 4 dmg
  Nightmare+ "Choose a card. Next turn, add 3 copies of that card into your Hand. Exhaust." -> 1 plays, EXHAUST
  Slimed "Draw 1 card. Exhaust." -> 1 plays, EXHAUST
  Deflect+ "Gain 15 Block." -> 5 plays, 75 block
  Deadly Poison+ "Apply 7 Poison." -> 1 plays, +7 poison
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 1 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Bouncing Flask+ "Apply 3 Poison to a random enemy 4 times." -> 1 plays, +12 poison
  Skewer+ "Deal 8 damage X times." -> 1 plays, 8 dmg
  Defend+ "Gain 16 Block." -> 1 plays, 16 block
  Survivor+ "Gain 19 Block. Discard 1 card." -> 1 plays, 19 block

Active powers: Dexterity(1)

Poison stacks applied per card:
  Bouncing Flask+: 12 stacks
  Bouncing Flask: 9 stacks
  Deadly Poison+: 7 stacks
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:5 -> R3:7 -> R4:14 -> R5:16 -> R6:27 -> R7:29 -> R8:31 -> R9:40 -> R10:54
  Strength: R1:- -> R2:- -> R3:- -> R4:3 -> R5:3 -> R6:3 -> R7:3 -> R8:6 -> R9:6 -> R10:6
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1 -> R10:-
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Slimed Berserker (Floor 37, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull, Distinguished Cape
Deck (31): Defend x5, Apparition x3, Leading Strike x3, Strike x3, Hidden Daggers+ x2, Accelerant+, Afterimage, Ascender's Bane, Backflip, Burst, Envenom+, Escape Plan, Expose, Finisher, Knife Trap, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Slimed Berserker HP=266/266

### Round 1
Intent: Slimed Berserker: StatusCard(10)
  Envenom+
    energy -2 | block +7 | +Envenom(2)
  Leading Strike -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -3, +Poison(3)
  Shiv -> Slimed Berserker[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Slimed Berserker: hp -4, Poison(3→6)
  Shiv -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -4, Poison(6→9)
  Hidden Daggers+
  Apparition
  Strike
  Shiv+ -> Slimed Berserker[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Slimed Berserker: hp -6, Poison(9→12)
  Shiv+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -6, Poison(12→15)
  turn_end

### Round 2
Intent: Slimed Berserker: Attack(4x4=16)
  Burst
    energy -1 | +Burst(1)
  Defend
    energy -1 | block +10 | -Burst
  Survivor+
    energy -1 | block +11
  Defend
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.

### Round 3
Intent: Slimed Berserker: Debuff, Buff
  Expose -> Slimed Berserker[0]
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Slimed Berserker: +Vulnerable(2)
  Escape Plan
    block +3
  Leg Sweep -> Slimed Berserker[0]
    energy -2 | block +11 | enemy_deltas: Slimed Berserker: +Weak(2)
  Leading Strike -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -4, Poison(13→16)
  Shiv -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -6, Poison(16→19)
  Shiv -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -6, Poison(19→22)
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.

### Round 4
Intent: Slimed Berserker: Attack(24)
  Backflip
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strangle+ -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -11, Poison(21→24), +Strangle(3)
  Leading Strike -> Slimed Berserker[0]
    energy -1 | enemy_deltas: Slimed Berserker: hp -6, Poison(24→27)
  Shiv -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -7, Poison(27→30)
  Shiv -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -7, Poison(30→33)
  Hidden Daggers+
    enemy_deltas: Slimed Berserker: hp -3
  Shiv+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -9, Poison(33→36)
  Shiv+ -> Slimed Berserker[0]
    enemy_deltas: Slimed Berserker: hp -9, Poison(36→39)
  turn_end

### Round 5
Intent: Slimed Berserker: StatusCard(10)
  Accelerant+
    energy -1 | +Accelerant(2)
  Afterimage
    energy -1 | +Afterimage(1)
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Neutralize+ -> Slimed Berserker[0]
    block +1 | enemy_deltas: Slimed Berserker: hp -3, Poison(38→41), +Weak(2)
  Strike -> Slimed Berserker[0]
    energy -1 | block +1 | enemy_deltas: Slimed Berserker: hp -4, Poison(41→44)
  turn_end
  Strike
  confirm
## Combat Analytics: Slimed Berserker (WIN - 5 rounds)

Cards played (with descriptions):
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 7 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 13 dmg, +9 poison, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 34 dmg, +18 poison, EXHAUST
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 2 plays, 3 dmg, generates 2 Shivs
  Shiv+ "Deal 6 damage. Exhaust." -> 4 plays, 30 dmg, +12 poison, EXHAUST
  Burst "This turn, your next Skill is played an extra time." -> 1 plays
  Defend "Gain 5 Block." -> 2 plays, 15 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 3 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Strangle+ "Retain. Deal 7 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 11 dmg, +3 poison
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 1 plays, 3 dmg, 1 block, +3 poison
  Strike "Deal 4 damage." -> 1 plays, 4 dmg, 1 block, +3 poison

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~38 dmg
  Hidden Daggers+: 4 Shivs -> ~26 dmg

Poison stacks applied per card:
  Shiv: 18 stacks
  Shiv+: 12 stacks
  Leading Strike: 9 stacks
  Strangle+: 3 stacks
  Neutralize+: 3 stacks
  Strike: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:14 -> R3:13 -> R4:21 -> R5:38
  Strength: R1:- -> R2:- -> R3:- -> R4:3 -> R5:3
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:-

[Selected: boss] Test Subject (F48, boss)
Historical: loss=42 vs historical avg=24.2+/-21.3 (z=0.8, TYPICAL, n=4)
## Combat Replay: vs Test Subject (Floor 48, boss)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth, Book of Five Rings, Delicate Frond, Regal Pillow, Oddly Smooth Stone
Deck (37): Defend x6, Strike x4, Dodge and Roll x2, Footwork+ x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Bouncing Flask, Bubble Bubble, Deadly Poison, Deflect, Expertise+, Footwork, Neutralize+, Nightmare+, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Prepared, Skewer+, Slice, Survivor, Tools of the Trade, Well-Laid Plans+
Enemies: Test Subject #C66 HP=100/100

### Round 1
Agent plan (hypothesis): We need to survive phase 1 quickly. Strength resets on death, so we can play skills if it saves HP or adds huge poison.
Intent: Test Subject #C66: Attack(20)
  Mazaleth's Gift
    +Ritual(1)
  Noxious Fumes+
    energy -1 | block +7 | +Noxious Fumes(3)
  Poisoned Stab -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -6, +Poison(3)
  Skill Potion
  Blur
  Bubble Bubble -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(3→12), +Strength(2)
  Blur
    block +6 | +Blur(1) | enemy_deltas: Test Subject #C66: Strength(2→4)
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5) | enemy_deltas: Test Subject #C66: Strength(4→6)
  Defend
    energy -1 | block +6 | enemy_deltas: Test Subject #C66: Strength(6→8)
  Defend
    energy -1 | block +6 | enemy_deltas: Test Subject #C66: Strength(8→10)
  Defend
    energy -1 | block +6 | enemy_deltas: Test Subject #C66: Strength(10→12)
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Played Footwork+ for long term scaling. Phase 2 requires heavy blocking.
Intent: Test Subject #C66: Attack(26), Debuff
  Acrobatics
    energy -1
  Strike
  Neutralize+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -5, +Weak(2)
  Slice -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -7
  Backflip
    energy -1 | block +6 | enemy_deltas: Test Subject #C66: Strength(14→16)
  Footwork+
    energy -1 | Dexterity(1→4)
  turn_end

### Round 3
Intent: Test Subject #C66: Attack(40)
  Expertise+
    energy -1 | enemy_deltas: Test Subject #C66: Strength(16→18)
  turn_end

### Round 4
Intent: Test Subject #C66: Attack(32), Debuff
  Footwork+
    energy -1 | Dexterity(4→7)
  Deflect
    block +11 | enemy_deltas: Test Subject #C66: Strength(18→20)
  Defend
    energy -1 | block +12 | enemy_deltas: Test Subject #C66: Strength(20→22)
  Survivor
    energy -1 | block +15 | enemy_deltas: Test Subject #C66: Strength(22→24)
  turn_end
    Strength(3→4)

### Round 5
Intent: Test Subject #C66: Attack(66)
  Footwork
    energy -1 | Dexterity(7→9)
  Blade Dance
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust. | enemy_deltas: Test Subject #C66: Strength(24→26)
  Shiv -> Test Subject #C66[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Test Subject #C66: hp -8
  Shiv -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -8
  Shiv -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -6, -Enrage, -Poison, -Strength, DIED
  Defend
    energy -1 | block +14
  turn_end

### Round 6
Agent plan (hypothesis): WLP is active, prioritize retaining Nightmare and high-value block/poison pieces.
Intent: Test Subject #C66: Attack(10x3=30)
  Blur+
    energy -1 | block +17 | +Blur(1)
  Defend+
    energy -1 | block +17
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  turn_end
  Pounce
  Strike

### Round 7
Agent plan (hypothesis): Survive and keep scaling poison.
Intent: Test Subject #C66: Attack(10x4=40)
  Acrobatics+
    energy -1
  Strike
  Slice+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -15
  Prepared
  Strike
  Defend+
    energy -1 | block +17
  turn_end
  Deadly Poison
  Bouncing Flask

### Round 8
Agent plan (hypothesis): Survive and retain Nightmare+ for scaling or block.
Intent: Test Subject #C66: Attack(10x5=50)
  Backflip+
    energy -1 | block +17
  Defend+
    energy -1 | block +17
  Dodge and Roll
    energy -1 | block +13 | +Block Next Turn(13)
  turn_end
  Nightmare+
  Bubble Bubble+

### Round 9
Intent: Test Subject #C66: Attack(10x6=60)
  Neutralize+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -12, +Weak(2)
  Deflect+
    block +16
  Defend
    energy -1 | block +14
  Bubble Bubble+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(9→21)
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  turn_end
  Nightmare+
  Skewer+
  Skewer+

### Round 10
Agent plan (hypothesis): Retain Poisoned Stab+ with WLP if possible.
Intent: Test Subject #C66: Attack(7x7=49)
  Neutralize+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -13, Weak(1→3)
  Backflip+
    energy -1 | block +17
  Dodge and Roll+
    energy -1 | block +15 | +Block Next Turn(15)
  Survivor+
    energy -1 | block +20
  Nightmare+
  turn_end
  Poisoned Stab+
  Blur+
  Strike

### Round 11
Intent: Test Subject #C66: Attack(7x8=56)
  Blur+
    energy -1 | block +17 | +Blur(1)
  Defend+
    energy -1 | block +17
  Defend+
    energy -1 | block +17
  turn_end
  Poisoned Stab+
  Prepared+
  Wound

### Round 12
Intent: Test Subject #C66: Attack(7x9=63)
  Slice+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -20
  Deflect+
    block +16
  Poisoned Stab+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -19, Poison(27→31)
  Strike -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -17
  Backflip+
    energy -1 | block +17
  Prepared+
  Peck
  Wound
  turn_end
  Dodge and Roll+
  Bubble Bubble+
  Strike

### Round 13
Agent plan (hypothesis): Retain Expertise+ if possible to refill hand next turn, or Bouncing Flask for more poison.
Intent: Test Subject #C66: Attack(10x3=30)
  Dodge and Roll+
    energy -1 | block +15 | +Block Next Turn(15)
  Defend+
    energy -1 | block +17
  Bubble Bubble+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(3→15)
  turn_end
  Bouncing Flask
  Expertise+
  Wound

### Round 14
Agent plan (hypothesis): Retain Bouncing Flask if WLP allows.
Intent: Test Subject #C66: Attack(45)
  Deflect+
    block +16
  Defend+
    energy -1 | block +17
  Peck -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -45
  Deadly Poison -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(17→22)
  turn_end
  Bouncing Flask
  Expertise+
  Strike

### Round 15
Agent plan (hypothesis): Retain key scaling or defensive cards. Next turn we have immense block.
Intent: Test Subject #C66: StatusCard(3), Buff
  Dodge and Roll+
    energy -1 | block +15 | +Block Next Turn(15)
  Acrobatics+
    energy -1
  Strike+
  Slice+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -1
  Blur+
    energy -1 | block +17 | +Blur(1)
  Prepared+
  Defend+
  Strike
  turn_end
  Backflip+
  Bubble Bubble+
  Strike

### Round 16
Agent plan (hypothesis): Retain Nightmare+ to set up a massive turn, and retain Bubble Bubble+ or Poisoned Stab+.
Intent: Test Subject #C66: Attack(12x3=36)
  Neutralize+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -19, +Weak(2)
  Pounce -> Test Subject #C66[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Test Subject #C66: hp -27
  Backflip+
    block +17 | -Free Skill
  Dodge and Roll+
    energy -1 | block +15 | +Block Next Turn(15)
  turn_end
  Nightmare+
  Bubble Bubble+
  Skewer+

### Round 17
Intent: Test Subject #C66: Attack(35)
  Deflect+
    block +16
  Bubble Bubble+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(28→40)
  Backflip+
    energy -1 | block +17
  Blur+
    energy -1 | block +17 | +Blur(1)
  turn_end
  Nightmare+
  Survivor+
  Wound

### Round 18
Intent: Test Subject #C66: StatusCard(3), Buff
  Deadly Poison+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: Poison(42→49)
  Dodge and Roll+
    energy -1 | block +15 | +Block Next Turn(15)
  Dodge and Roll+
    energy -1 | block +15 | Block Next Turn(15→30)
  turn_end
  Nightmare+
  Survivor+
  Burn

### Round 19
Agent plan (hypothesis): Boss loses Intangible next turn. Use Bubble Bubble+ or Bouncing Flask if drawn to finish it off.
Intent: Test Subject #C66: Attack(14x3=42)
  Backflip+
    energy -1 | block +17
  Acrobatics+
    energy -1
  Wound
  Slice+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -1
  Poisoned Stab+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -1, Poison(51→55)
  Prepared+
  Strike
  Strike
  Neutralize+ -> Test Subject #C66[0]
    enemy_deltas: Test Subject #C66: hp -1, +Weak(2)
  turn_end
  Survivor+
  Bouncing Flask
  Burn

### Round 20
Agent plan (hypothesis): We win!
Intent: Test Subject #C66: Attack(36)
  Peck+ -> Test Subject #C66[0]
    energy -1 | enemy_deltas: Test Subject #C66: hp -84
  Strike+ -> Test Subject #C66[0]
    energy -1 | hp +12 | -Dexterity | -Ritual | -Noxious Fumes | -Strength | -Well-Laid Plans | -Tools of the Trade | enemy_deltas: Test Subject #C66: DIED
## Combat Analytics: Test Subject (WIN - 20 rounds)

Cards played (with descriptions):
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 7 block
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 1 plays, +9 poison
  Blur "Gain 6 Block. Block is not removed at the start of your next turn." -> 1 plays, 6 block
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 2 plays, 18 block
  Defend "Gain 6 Block." -> 6 plays, 58 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Neutralize+ "Deal 5 damage. Apply 2 Weak." -> 5 plays, 50 dmg
  Slice "Deal 7 damage." -> 1 plays, 7 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 1 plays, 6 block
  Footwork+ "Gain 3 Dexterity." -> 2 plays
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Deflect "Gain 11 Block." -> 1 plays, 11 block
  Survivor "Gain 15 Block. Discard 1 card." -> 1 plays, 15 block
  Footwork "Gain 2 Dexterity." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 8 damage. Exhaust." -> 3 plays, 22 dmg, EXHAUST
  Blur+ "Gain 17 Block. Block is not removed at the start of your next turn." -> 4 plays, 68 block
  Defend+ "Gain 17 Block." -> 7 plays, 119 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 3 plays
  Slice+ "Deal 15 damage." -> 4 plays, 37 dmg
  Prepared "Draw 1 card. Discard 1 card." -> 1 plays
  Backflip+ "Gain 17 Block. Draw 2 cards." -> 6 plays, 102 block
  Deflect+ "Gain 16 Block." -> 4 plays, 64 block
  Bubble Bubble+ "If the enemy has Poison, apply 12 Poison." -> 3 plays, +36 poison
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Dodge and Roll+ "Gain 15 Block. Next turn, gain 15 Block." -> 6 plays, 90 block
  Survivor+ "Gain 20 Block. Discard 1 card." -> 1 plays, 20 block
  Poisoned Stab+ "Deal 19 damage. Apply 4 Poison." -> 2 plays, 20 dmg, +8 poison
  Strike "Deal 17 damage." -> 1 plays, 17 dmg
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Peck "Deal 15 damage 3 times." -> 1 plays, 45 dmg
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Pounce "Deal 27 damage. The next Skill you play costs 0 energy ." -> 1 plays, 27 dmg
  Deadly Poison+ "Apply 7 Poison." -> 1 plays, +7 poison
  Peck+ "Deal 21 damage 4 times." -> 1 plays, 84 dmg
  Strike+ "Deal 28 damage." -> 1 plays

Active powers: Dexterity(1)

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~22 dmg

Poison stacks applied per card:
  Bubble Bubble+: 36 stacks
  Bubble Bubble: 9 stacks
  Poisoned Stab+: 8 stacks
  Deadly Poison+: 7 stacks
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Adaptable: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1 -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:- -> R20:-
  Enrage: R1:2 -> R2:2 -> R3:2 -> R4:2 -> R5:2 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:- -> R20:-
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:1 -> R14:- -> R15:1 -> R16:- -> R17:1 -> R18:- -> R19:1 -> R20:-
  Nemesis: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:1 -> R14:1 -> R15:1 -> R16:1 -> R17:1 -> R18:1 -> R19:1 -> R20:1
  Painful Stabs: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1 -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:- -> R20:-
  Poison: R1:- -> R2:14 -> R3:16 -> R4:18 -> R5:20 -> R6:3 -> R7:5 -> R8:7 -> R9:9 -> R10:23 -> R11:25 -> R12:27 -> R13:3 -> R14:17 -> R15:24 -> R16:26 -> R17:28 -> R18:42 -> R19:51 -> R20:57
  Strength: R1:- -> R2:12 -> R3:16 -> R4:18 -> R5:24 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:2 -> R17:2 -> R18:2 -> R19:4 -> R20:4
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:1 -> R11:2 -> R12:1 -> R13:- -> R14:- -> R15:- -> R16:- -> R17:1 -> R18:- -> R19:- -> R20:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs Test Subject (Floor 48, boss)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood, Letter Opener, Brilliant Scarf, Red Mask, Joss Paper, Captain's Wheel
Deck (33): Defend x4, Footwork+ x2, Strike x2, Strike+ x2, Adrenaline+, Ascender's Bane, Backflip, Blade Dance, Blade Dance+, Blade of Ink+, Cloak and Dagger, Clumsy, Dash+, Defend+, Deflect, Expertise, Expose, Exterminate, Flick-Flack, Leading Strike, Neutralize, Piercing Wail, Prepared+, Skewer+, Survivor+, Tracking+, Well-Laid Plans+
Enemies: Test Subject #C64 HP=100/100

### Round 1
Intent: Test Subject #C64: Attack(15)
  Strength Potion
    +Strength(2)
  Expose -> Test Subject #C64[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Test Subject #C64: +Vulnerable(2), +Strength(2)
  Blade of Ink+
    energy -1 | enemy_deltas: Test Subject #C64: Strength(2→4)
  Shiv -> Test Subject #C64[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Test Subject #C64: hp -12, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12, Weak(2→3)
  Dash+ -> Test Subject #C64[0]
    block +17 | enemy_deltas: Test Subject #C64: hp -22
  Footwork+
    energy -1 | +Dexterity(3)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Deflect
    block +7 | enemy_deltas: Test Subject #C64: hp -5, Strength(4→6)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12, Weak(3→4)
  turn_end
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Blade Dance
  Exterminate

### Round 2
Intent: Test Subject #C64: Attack(15), Debuff
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -10, Weak(3→4)
  Exterminate
    energy -1 | enemy_deltas: Test Subject #C64: hp -27, -Enrage, -Weak, -Vulnerable, -Strength, DIED
  turn_end
  Blade Dance
  Blade Dance+

### Round 3
Intent: Test Subject #C64: Attack(10x3=30)
  Footwork+
    energy -1 | Dexterity(3→6)
  Cloak and Dagger
    energy -1 | block +12
  Shiv -> Test Subject #C64[0]
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Test Subject #C64: hp -6
  Blade Dance
    energy -1 | exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  turn_end
  Blade Dance+
  Backflip

### Round 4
Intent: Test Subject #C64: Attack(10x4=40)
  Adrenaline+
    energy +2 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  Prepared+
  Flick-Flack
  Ascender's Bane
  Piercing Wail
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C64: hp -5, +Strength(-6), +Piercing Wail(6)
  Tracking+
    energy -1 | +Tracking(2)
  Backflip
    block +11
  Leading Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -5
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -8
  Defend
    energy -1 | block +11
  Prepared+
  Flick-Flack
  Strike
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -7, +Weak(1)
  Skewer+ -> Test Subject #C64[0]
  turn_end
  Blade Dance+
  Strike+

### Round 5
Intent: Test Subject #C64: Attack(10x5=50)
  Blade Dance+
    energy -1 | exhausted: Shiv*6 [0]: Deal 4 damage. Exhaust.
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Dash+ -> Test Subject #C64[0]
    block +19 | enemy_deltas: Test Subject #C64: hp -15
  Survivor+
    energy -1 | block +17
  Ascender's Bane
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -5
  turn_end
  Exterminate
  Defend

### Round 6
Intent: Test Subject #C64: Attack(10x6=60)
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Exterminate
    enemy_deltas: Test Subject #C64: hp -40, -Weak, DIED
  turn_end
  Defend+
  Cloak and Dagger

### Round 7
Intent: Test Subject #C64: Attack(10x3=30)
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1
  Defend+
    energy -1 | block +14
  Defend
    energy -1 | block +22 | enemy_deltas: Test Subject #C64: hp -1
  Cloak and Dagger
    energy -1 | block +12
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -1
  turn_end
  Blade of Ink+
  Strike+

### Round 8
Intent: Test Subject #C64: Attack(45)
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Dash+ -> Test Subject #C64[0]
    block +19 | enemy_deltas: Test Subject #C64: hp -30
  Backflip
    energy -1 | block +11
  Exterminate
    energy -1 | enemy_deltas: Test Subject #C64: hp -40
  turn_end
  Leading Strike
  Expertise

### Round 9
Intent: Test Subject #C64: StatusCard(3), Buff
  Deflect
    block +10
  Leading Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -1
  Survivor+
    block +17
  Defend
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -1
  turn_end
    exhausted: Shiv*9 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Expertise
  Skewer+

### Round 10
Intent: Test Subject #C64: Attack(9x3=27)
  Deflect
    block +10
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -14, Weak(1→2)
  Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -16
  Leading Strike -> Test Subject #C64[0]
    energy -1 | block +4 | enemy_deltas: Test Subject #C64: hp -10
  Strike+ -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -22
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -12
  Skewer+ -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -26
  turn_end
  Expertise
  Strike+

### Round 11
Intent: Test Subject #C64: Attack(35)
  Prepared+
  Burn
  Strike
  Survivor+
    energy -1 | block +17
  Strike+
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -1
  Defend
    energy -1 | block +22
  turn_end
  Expertise
  Exterminate

### Round 12
Intent: Test Subject #C64: StatusCard(3), Buff
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Exterminate
    block -4 | -Strength | -Dexterity | -Well-Laid Plans | -Tracking | enemy_deltas: Test Subject #C64: DIED
## Combat Analytics: Test Subject (WIN - 12 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 4 plays
  Shiv "Deal 8 damage. Apply 1 Weak. Exhaust." -> 27 plays, 238 dmg, 36 block, EXHAUST
  Dash+ "Gain 13 Block. Deal 15 damage." -> 3 plays, 67 dmg, 55 block
  Footwork+ "Gain 3 Dexterity." -> 2 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Deflect "Gain 7 Block." -> 3 plays, 5 dmg, 27 block
  Neutralize "Deal 7 damage. Apply 1 Weak." -> 4 plays, 32 dmg
  Exterminate "Deal 13 damage 4 times to ALL enemies." -> 4 plays, 107 dmg
  Cloak and Dagger "Gain 12 Block. Add 1 Shiv into your Hand." -> 2 plays, 24 block, generates 1 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 5 dmg, EXHAUST
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays
  Backflip "Gain 11 Block. Draw 2 cards." -> 2 plays, 22 block
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 3 plays, 16 dmg, 4 block, generates 2 Shivs
  Strike "Deal 8 damage." -> 2 plays, 24 dmg
  Defend "Gain 11 Block." -> 6 plays, 8 dmg, 88 block
  Skewer+ "Deal 13 damage X times." -> 2 plays, 26 dmg
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Survivor+ "Gain 17 Block. Discard 1 card." -> 3 plays, 51 block
  Defend+ "Gain 14 Block." -> 1 plays, 14 block
  Strike+ "Deal 11 damage." -> 1 plays, 22 dmg

Token attribution (Shivs):
  other: 13 Shivs -> ~115 dmg
  Leading Strike: 6 Shivs -> ~53 dmg
  Blade Dance: 3 Shivs -> ~26 dmg
  Blade Dance+: 3 Shivs -> ~26 dmg
  Cloak and Dagger: 2 Shivs -> ~18 dmg

Enemy power timeline:
  Adaptable: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Enrage: R1:2 -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:1 -> R10:- -> R11:1 -> R12:-
  Nemesis: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1
  Painful Stabs: R1:- -> R2:- -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Strength: R1:- -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:2 -> R11:2 -> R12:2
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Weak: R1:1 -> R2:3 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:2 -> R10:1 -> R11:1 -> R12:-

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F9(Byrdonis: WIN), F15(Phrog Parasite: ), F17(Ceremonial Beast: WIN), F28(Entomancer: WIN), F33(Knowledge Demon: WIN), F48(Test Subject #C66: WIN)
- Core Combat Principles: F2(Fuzzy Wurm Crawler: WIN), F5(Twig Slime (S): ), F6(Nibbit: WIN), F9(Byrdonis: WIN), F14(Twig Slime (M): ), F15(Phrog Parasite: ), F17(Ceremonial Beast: WIN), F19(Exoskeleton: WIN), F21(Bowlbug (Rock): WIN), F22(The Obscura: WIN), F23(Bowlbug (Rock): ), F25(Exoskeleton: WIN), F28(Entomancer: WIN), F30(Myte: WIN), F33(Knowledge Demon: WIN), F35(Scroll of Biting: WIN), F37(Devoted Sculptor: WIN), F39(Owl Magistrate: WIN), F42(Slimed Berserker: WIN), F44(Scroll of Biting: WIN), F45(Fabricator: WIN), F48(Test Subject #C66: WIN)
- Deck Building Across the Run: F2(), F3(), F5(), F6(), F8(), F9(), F12(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F23(), F25(), F28(), F30(), F31(), F33(), F33(), F33(), F33(), F35(), F35(), F37(), F39(), F40(), F42(), F42(), F44(), F44(), F45(), F46(), F46(), F46(), F48()
- Map Routing and Path Planning: F1(), F1(), F3(), F5(), F7(), F8(), F11(), F13(), F14(), F14(), F18(), F18(), F21(), F23(), F23(), F24(), F25(), F26(), F28(), F29(), F30(), F34(), F34(), F35(), F35(), F38(), F42(), F45()
- Poison Deck Thinning & Focus: F35(), F37(), F39(), F40(), F42(), F44(), F45(), F46(), F46()
- Rest Site and Event Decisions: F7(), F11(), F13(), F16(), F24(), F27(), F29(), F32(), F43(), F47()
- Silent - Combat Sequencing: F2(Fuzzy Wurm Crawler: WIN), F5(Twig Slime (S): ), F6(Nibbit: WIN), F9(Byrdonis: WIN), F14(Twig Slime (M): ), F15(Phrog Parasite: ), F17(Ceremonial Beast: WIN), F19(Exoskeleton: WIN), F21(Bowlbug (Rock): WIN), F22(The Obscura: WIN), F23(Bowlbug (Rock): ), F25(Exoskeleton: WIN), F28(Entomancer: WIN), F30(Myte: WIN), F33(Knowledge Demon: WIN), F35(Scroll of Biting: WIN), F37(Devoted Sculptor: WIN), F39(Owl Magistrate: WIN), F42(Slimed Berserker: WIN), F44(Scroll of Biting: WIN), F45(Fabricator: WIN), F48(Test Subject #C66: WIN)
- Silent - Draft and Shop Rules: F2(), F3(), F5(), F6(), F8(), F9(), F12(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F23(), F25(), F28(), F30(), F31(), F33(), F33(), F33(), F33(), F35(), F35(), F37(), F39(), F40(), F42(), F42(), F44(), F44(), F45(), F46(), F46(), F46(), F48()
- Silent - Route Priorities: F1(), F1(), F3(), F5(), F7(), F8(), F11(), F13(), F14(), F14(), F18(), F18(), F21(), F23(), F23(), F24(), F25(), F26(), F28(), F29(), F30(), F34(), F34(), F35(), F35(), F38(), F42(), F45()
- act1_mandatory_elites_shops: F1(), F1(), F3(), F5(), F7(), F8(), F11(), F13(), F14(), F14(), F18(), F18(), F21(), F23(), F23(), F24(), F25(), F26(), F28(), F29(), F30(), F34(), F34(), F35(), F35(), F38(), F42(), F45()
- act1_max_hp_event_trap: F1(), F3(), F18(), F34(), F36(), F38()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.