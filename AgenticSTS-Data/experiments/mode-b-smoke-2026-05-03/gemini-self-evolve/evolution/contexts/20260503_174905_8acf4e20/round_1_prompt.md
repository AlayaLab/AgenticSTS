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
Result: VICTORY (fitness: 243.8)
Combats won: 20/20
Run duration: 5624.2s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck plan: find early flat damage to defeat Act 1 elites, then transition to a scaling poison or discard engine. Keep the deck thin and focus on immediate power.
- [map] Foundation deck plan: prioritize finding high-efficiency front-loaded damage in early hallway fights to survive the first Elite. Use Winged Boots later to potentially path into a second Elite or a critical rest site once the deck engine begins to form.
### F2
- [card_reward] Foundation plan: survive with frontload damage like Predator and efficient block while looking for a scaling engine. Prioritize elite fights for relics and card rewards.
- [map] Foundation stage: prioritize monster fights to find high-impact flat damage cards like Poisoned Stab or Blade Dance to prepare for the first Elite; skip early shops to accumulate gold for a high-value relic or key removal later.
### F3
- [card_reward] Foundation plan: seeking flat damage and discard/poison enablers. We have Predator for frontload and Haze for AoE/discard synergy. Prioritize cheap attacks (like Dagger Throw) and discard outlets (like Acrobatics).
- [map] Foundation deck focusing on securing early flat damage to tackle Act 1 elites, while looking for a long-term scaling engine like poison or discard; prioritize high-impact card upgrades and thin deck composition.
### F4
- [event] Foundation deck focusing on securing early flat damage to tackle Act 1 elites, while looking for a long-term scaling engine like poison or discard; prioritize high-impact card upgrades and thin deck composition.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation stage: prioritizing hallway fights for front-loaded damage cards to handle Act 1 elites while looking for a scaling engine like poison or discard. Use Winged Boots to pivot if pathing towards a crucial campfire or shop becomes necessary.
### F5
- [card_reward] Foundation plan: prioritize immediate damage and efficient mitigation to survive Act 1 elites. Keep an eye out for ways to discard Haze for free (like Survivor or Acrobatics) to leverage its AoE poison without paying 3 energy.
- [map] Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a long-term engine like poison or discard; prioritize high-impact upgrades and deck thinning.
### F6
- [card_reward] Foundation phase: surviving with Predator's raw damage and Haze's AoE poison while looking for a core scaling engine (either poison or shivs). Prioritize high-impact win conditions, more draw/cycle, and removals for basic Strikes/Defends.
- [map] Foundation deck focusing on securing early flat damage; prioritize card rewards that solve Gremlin Nob and Lagavulin before pivoting to scaling or excessive elite hunting.
### F7
- [card_reward] Foundation plan: Use Acrobatics and Survivor to trigger Haze's Sly effect for free AoE poison. Prioritize efficient frontload, draw, and defensive tools to survive Act 1. Do not over-commit to a single engine until we find a strong multiplicative scaling piece.
- [map] Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a long-term scaling engine; currently leveraging high HP and Winged Boots to aggressively hunt relics.
### F8
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a scaling engine like poison or discard; prioritize high-impact upgrades and thinning deck composition.
### F9
- [event] Foundation deck looking for scaling discard or poison synergies; currently prioritizing early flat damage and mitigation while holding a Spoils Map for a massive Act 2 gold injection, aiming to remove basic strikes when possible.
- [map] Foundation deck focusing on securing early flat damage; prioritize converting gold at the upcoming shop and using rest sites for high-impact upgrades before the Act 1 boss.
### F10
- [map] Foundation discard/poison deck prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.
### F11
- [event] Foundation discard/poison deck prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.
- [map] Foundation discard/poison plan: prioritizing early damage and mitigation while seeking a shop to convert high gold into removals or key scaling pieces before the boss.
### F12
- [rest_site] Foundation discard/poison plan: prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.
- [map] Foundation discard and poison deck; prioritizing health preservation and gold accumulation to maximize the impact of the upcoming shop visit before the boss.
### F13
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [map] Foundation discard/poison deck seeking consistency; prioritizing the final shop and rest site to stabilize for the Act 1 boss while preserving HP.
### F14
- [map] Foundation discard and poison deck seeking final damage pieces and an upgrade before the boss; focusing on high-value hallway fights to refine the deck's output.
### F15
- [card_reward] Committed poison plan: retain Snakebite to combo with Bubble Bubble, use Acrobatics/Survivor to trigger Haze, and defend with Backflip+. Needs more energy or cheaper poison (like Noxious Fumes), and Catalyst. Skip heavy cards.
- [map] Foundation deck focusing on discard and poison; looking to smith a key card at this final rest site to secure the Act 1 boss win, then pivoting to gold accumulation via Spoils Map in Act 2.
### F16
- [rest_site] Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.
### F17
- [card_reward] Leaning towards poison and discard synergies (Snakebite, Bubble Bubble, Haze + Acro/Survivor). Use Adrenaline to accelerate setup and cycle fast. Prioritize efficient block and draw; skip narrow shiv/attack synergies.
### F18
- [event] Foundation discard/poison deck: rely on Suppress to mitigate early damage while setting up poison pieces (Snakebite, Bubble Bubble) and Malaise; prioritize finding card removal and more efficient poison/block scaling.
- [map] Foundation discard and poison deck: prioritizing early Act 2 hallway fights to find AoE and reliable block before attempting elites. I need to convert my current high HP into deck quality through aggressive drafting.
### F19
- [card_reward] Foundation plan: surviving with efficient attacks and defense while looking for a definitive scaling engine. Currently leveraging poison and Sly mechanics. Needs strong block scaling or a true core scaling card.
- [map] Foundation discard/poison plan: hunt for poison scaling and defensive discard pieces in hallway fights to stabilize before tackling elites. Avoid early event chains; prioritize cards and gold to make future shops and rest sites more impactful.
### F20
- [hand_select] Acrobatics draw resolved, discarding the dead weight map card to proceed with the turn.
- [hand_select] Prioritizing Predator+ to accelerate deck cycle and find more poison/block pieces.
- [hand_select] Executing the Sly synergy to scale poison for free.
- [hand_select] Discarding the dead card to maintain better play options.
- [card_reward] Committed to discard-poison plan: use Acrobatics, Survivor, and Dagger Throw to discard Sly poison cards (Haze) for free AoE damage, then amplify with Bubble Bubble. Prioritize efficient block and further discard/draw to cycle fast. Skip narrow attacks and focus on surviving while passive poison scales.
- [map] Foundation discard/poison plan: utilizing Malaise to mitigate heavy hitters while poison scales. Prioritizing standard combats to find missing engine pieces and building gold for a high-impact shop visit; needs more reliable block and card draw.
### F21
- [card_reward] Committed to a Poison/Discard hybrid plan: use Acrobatics/Dagger Throw/Survivor to trigger Sly Haze for free AoE poison, then escalate with Bubble Bubble. Need block scaling (Footwork) and Catalyst/more card draw. Avoid adding more generic attacks.
- [map] Foundation discard and poison plan: using Malaise to mitigate heavy hits while poison scales. Currently hunting for consistent poison sources and AoE damage to handle Act 2's multiple-enemy encounters. Prioritizing hallway fights to stabilize the engine before shifting toward elite hunting or heavy shop investment.
### F22
- [hand_select] Discarding basic Strike to thin current hand for better poison/defense synergy.
- [hand_select] Prioritizing the upgraded Sly card for maximum poison stack.
- [hand_select] Prioritizing survival over chip damage with Strike.
- [hand_select] Ovicopter dies to poison (13 poison vs 12 HP). Eggs retreat. Combat ends this turn.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [map] Foundation discard/poison plan: focus on thinning the deck at upcoming shops to increase the frequency of Malaise and poison applications while seeking more reliable block or card draw.
### F23
- [event] Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.
- [map] Foundation discard/poison plan: currently focusing on survival and stabilization. Malaise and poison are the primary scaling tools; I need to use this gold at the upcoming shop for card removals or high-impact defensive tools to survive Act 2 elites/boss.
### F24
- [rest_site] Foundation discard/poison plan: rely on Malaise to mitigate dangerous attacks while poison stacks via Haze and Snakebite. Use upcoming shops to thin Strikes and find more block density. Prioritize card draw and Sly triggers.
- [map] Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking card removal and key relics at this shop to refine the engine and increase consistency.
### F25
- [card_select] Committed poison plan: stack poison with Snakebite/Haze/Bubble, retain setup tools with cycle, and defend with tools and Weak. Remove remaining Strikes.
### F26
- [map] Foundation Malaise and poison plan: mitigate multi-attacks with Malaise while building poison stacks. With over 600 gold, prioritize finding a shop to buy key relics or removals to thin the deck for consistency. Avoid elites until HP is higher or defense is fully stabilized.
### F27
- [event] Foundation Malaise and poison plan: mitigate attacks with Malaise while building poison stacks. Seek a shop to use 600+ gold for removals and key relics. Prioritize defensive consistency.
- [map] Foundation poison/discard plan: rely on Malaise to neutralize high-damage enemies while poison stacks; prioritize adding block density and deck thinning at shops to ensure core skills are drawn reliably.
### F28
- [rest_site] Foundation discard/poison plan: mitigate damage with Malaise+ and Suppress while building poison stacks via Haze and Snakebite. Use upcoming shop to thin Strikes and find defensive or engine-accelerating relics.
- [map] Foundation poison and Malaise plan: mitigate heavy hitters while stacking poison. With over 600 gold, the priority is surviving to the next shop for removals and high-impact relics to stabilize defense.
### F29
- [rest_site] Foundation discard/poison plan: mitigate damage with Malaise+ and Suppress while building poison stacks via Haze and Snakebite. Use the upcoming shop to thin Strikes and find key defensive or engine-accelerating relics.
### F30
- [hand_select] Triggering Sly on Haze+ allows us to stack poison while keeping energy for Dash or Defends.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs block scaling like Footwork; skip off-plan attacks and expensive cards.
### F31
- [card_select] Committed poison plan: discard Haze to trigger Sly and stack poison, then cycle deck and play block cards while poison ticks. Remove basic Strikes to improve consistency.
### F32
- [rest_site] Committed poison plan: mitigate damage with Malaise and Shackles while scaling poison with Bubble Bubble and Accelerant. Needs more block and consistency.
- [rest_site] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks.
### F33
- [hand_select] Maximizing free poison application while preserving energy for blocking or additional poison cards.
- [card_reward] Committed poison plan: cycle rapidly to stack poison with Haze/Bubble Bubble/Snakebite, then burst it with Accelerant+. Defend heavily with efficient block and damage reduction (Malaise/Wail) while passive damage kills. Avoid slow powers and off-plan attacks.
### F34
- [event] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Use the massive gold pool at shops to buy crucial relics and card removals.
- [map] Foundation poison and Malaise plan: mitigate heavy hitters while stacking poison. With over 1100 gold, the priority is hitting shops to remove strikes and buy high-impact relics while using early hallways to find missing AoE or defense.
### F35
- [card_reward] Committed poison plan: discard Haze to trigger Sly and stack poison, then cycle deck and play block cards while poison ticks. Use Well-Laid Plans to hold combo pieces and defensive cards. Remove basic Strikes to improve consistency.
### F36
- [card_select] Committed poison plan: scale poison, survive with discard synergy and defensive tools. Remove remaining Strikes to draw setup faster.
### F38
- [card_select] Committed poison plan: stack poison with Bubble Bubble and Haze, trigger with Accelerant. Retain Snakebite until the right target. Needs more draw to find pieces quickly; skip attacks and keep thinning basic cards.
### F39
- [hand_select] Building a hand of defensive options while poison ticks down.
- [card_reward] Committed poison plan: survive with efficient block and damage mitigation while scaling poison via Noxious Fumes, Haze, and Bubble Bubble; use Accelerant+ to finish. Retain cycle/draw pieces and prioritize card removal and upgraded defensive tools over filler.
### F40
- [hand_select] Accelerant is active, so finding poison applicators quickly is the priority.
- [hand_select] Hex makes everything Ethereal, so cards not played will exhaust. I want to keep the defensive cards to mitigate the 22 damage from Flail and Spectral Knights.
- [hand_select] Executing the Sly trigger to play a 3-cost card for free is highly efficient. The 8 poison applied (due to Accelerant triggering it twice) will also improve Mirage's block value for later this turn.
- [card_reward] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep the deck cycling with cards like Backflip.
- [map] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks.
### F42
- [event] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep our deck thin by removing attacks we don't need.
- [event] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.
- [map] Committed poison plan: mitigate damage with Malaise and Weak while scaling rapid damage with Accelerant and Bubble Bubble; pivoting to Elites now to secure relic power for the final boss.
### F43
- [hand_select] Clearing Burns is the highest priority when drawn alongside discard effects to mitigate chip damage.
- [hand_select] Prioritizing status removal to minimize chip damage while setting up the poison win condition.
- [hand_select] Enemy has 16 poison and 2 stacks of Accelerant. It will take (16 + 16 + 16) = 48 damage at the start of its turn. With 58 HP remaining, it is very close to death. I will prioritize block and cycle to finish it off.
- [card_reward] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep prioritizing block scaling and deck cycle.
### F44
- [rest_site] Committed poison plan: stack poison with Fumes and Bubble Bubble, mitigate with Malaise/Shackles, and block heavily with Mirage while Accelerant triggers rapid damage. Prioritize retaining Mirage or key mitigation for dangerous turns.
- [rest_site] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.
### F45
- [hand_select] Utilizing Sly keyword to scale poison without spending energy.
- [card_reward] Committed poison plan: stack poison with Bubble Bubble and Haze, trigger with Accelerant. Retain Snakebite until the right target. Avoid bloating the deck further.
- [map] Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.
### F46
- [event] Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.
### F47
- [rest_site] Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.
- [rest_site] Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.

### Combat Decision Digest (20 combats)
F2 [monster] multi:Corpse Slug+Corpse Slug (4R, HP 70->63, loss=7, WIN)
  R1[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Neutralize->Strike*2->Defend(+5blk) | dealt=0 taken=1
  R2[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Survivor(+6blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R3[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike->Neutralize(3dmg,1+Weak(1))->Defend(+3blk)->Defend(+3blk) | dealt=3 taken=6
  R4[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Strike(1+Strength(4))->Strike(6dmg)->Strike(power:-Frail) | dealt=6 taken=0

F3 [monster] multi:Toadpole+Toadpole (4R, HP 63->59, loss=4, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Predator(power:+Draw Cards Next Turn(2))->Neutralize(3dmg,1+Weak(1))->Defend(+5blk) | dealt=3 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=1
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Neutralize(3dmg,1+Weak(1))->Predator(power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=3 taken=3
  R4[Toadpole: Atk(7)]: Strike | dealt=0 taken=0

F5 [monster] Sludge Spinner (3R, HP 59->58, loss=1, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize(5dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Defend(+5blk) | dealt=17 taken=1
  R2[Sludge Spinner: Atk(6), Buff]: Predator(11dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=11 taken=0
  R3[Sludge Spinner: Atk(14)]: Strike(6dmg)->Neutralize | dealt=6 taken=0

F6 [monster] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (4R, HP 58->52, loss=6, WIN)
  R1[Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Debuff]: Predator(power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=0 taken=6
  R2[Two-Tailed Rat: Debuff+Two-Tailed Rat: Debuff+Two-Tailed Rat: Atk(6)]: Survivor(+6blk)->Haze(6dmg,1+Poison(4))->Strike(6dmg)->Strike | dealt=12 taken=0
  R3[Two-Tailed Rat: Summon+Two-Tailed Rat: Atk(8)]: Strike*2->Defend(+3blk) | dealt=0 taken=0
  R4[Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Atk(8)]: Survivor(+8blk)->Neutralize(5dmg,1+Weak(1))->Predator(13dmg,power:+Draw Cards Next Turn(2),2+Poison(2),-Weak) | dealt=18 taken=0

F7 [monster] Punch Construct (6R, HP 52->52, loss=0, WIN)
  R1[Punch Construct: Defend]: Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=18 taken=0
  R2[Punch Construct: Atk(14)]: Cloak and Dagger(+6blk)->Shiv(exhaust:1)->Strike->Survivor(+8blk) | dealt=0 taken=0
  R3[Punch Construct: Atk(5x2=10), Debuff]: Neutralize(5dmg,1-Artifact)->Backflip(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=11 taken=0
  R4[Punch Construct: Defend]: Survivor(+8blk)->Haze(+6blk,1+Poison(4))->Cloak and Dagger(3dmg)->Shiv(4dmg)->Strike | dealt=7 taken=0
  R5[Punch Construct: Atk(14)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R6[Punch Construct: Atk(5x2=10), Debuff]: Neutralize(5dmg,1+Weak(1))->Strike(6dmg)->Strike | dealt=11 taken=0

F8 [elite] Terror Eel (11R, HP 52->33, loss=19, WIN)
  R1[Terror Eel: Atk(16)]: Neutralize(5dmg,1+Weak(1))->Cloak and Dagger(+6blk)->Shiv(4dmg,exhaust:1)->Defend(+5blk)->Defend(+5blk) | dealt=9 taken=0
  R2[Terror Eel: Atk(3x3=9), Buff]: Backflip(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R3[Terror Eel: Atk(22)]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=15 taken=14
  R4[Terror Eel: Atk(3x3=9), Buff]: Neutralize(5dmg,1+Weak(1))->Backflip(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=17 taken=0
  R5[Terror Eel: Atk(22)]: Cloak and Dagger(+6blk)->Shiv(4dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=4 taken=2
  R6[Terror Eel: Atk(3x3=9), Buff]: Neutralize(5dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=11 taken=0
  R7[Terror Eel: Atk(22)]: Predator(15dmg,power:+Draw Cards Next Turn(2),1-Shriek)->Strike(6dmg) | dealt=21 taken=0
  R8[Terror Eel: Debuff]: Backflip(+5blk)->Predator(15dmg,power:+Draw Cards Next Turn(2)) | dealt=15 taken=0
  R9[Terror Eel: Atk(33)]: Neutralize(5dmg,1+Weak(1))->Acrobatics->Haze(+5blk)->Backflip(+6blk)->Cloak and Dagger(4dmg)->Shiv | dealt=9 taken=13
  R10[Terror Eel: Atk(4x3=12), Buff]: Neutralize(5dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=11 taken=0
  R11[Terror Eel: Atk(33)]: Strike(6dmg)->Strike(6dmg)->Strike(power:-Vulnerable) | dealt=12 taken=0

F15 [monster] multi:Calcified Cultist+Damp Cultist (4R, HP 47->46, loss=1, WIN)
  R1[Calcified Cultist: Buff+Damp Cultist: Buff]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=26 taken=0
  R2[Calcified Cultist: Atk(9)+Damp Cultist: Atk(1)]: Neutralize(5dmg,1+Weak(1))->Strike(6dmg)->Acrobatics->Strike->Malaise(exhaust:1) | dealt=14 taken=1
  R3[Damp Cultist: Atk(6)]: Backflip+(+8blk)->Snakebite(1+Poison(7))->Bubble Bubble(1Poison(7→16))->Strike(6dmg) | dealt=6 taken=0
  R4[Damp Cultist: Atk(11)]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=26 taken=0

F17 [boss] Lagavulin Matriarch (7R, HP 71->58, loss=13, WIN)
  R1[Lagavulin Matriarch: Sleep]: Malaise(2+Strength(-3),+Weak(3),exhaust:1) | dealt=0 taken=0
  R2[Lagavulin Matriarch: Sleep]: Snakebite(1+Poison(7))->Bubble Bubble(1Poison(7→16)) | dealt=0 taken=0
  R3[Lagavulin Matriarch: Atk(12)]: Acrobatics->Haze(5dmg,1Weak(1→2))->Neutralize(20dmg,power:+Draw Cards Next Turn(2))->Predator+ | dealt=25 taken=12
  R4[Lagavulin Matriarch: Atk(4x2=8)]: Neutralize(5dmg,1Weak(1→2))->Acrobatics->Haze(1Poison(22→31))->Bubble Bubble(+7blk)->Defend | dealt=5 taken=1
  R5[Lagavulin Matriarch: Atk(6), Defend]: Backflip+(+10blk)->Snakebite(1Poison(30→37)) | dealt=0 taken=0
  R6[Lagavulin Matriarch: Debuff, Buff]: Bubble Bubble(1Poison(36→45))->Predator+(8dmg,power:+Draw Cards Next Turn(2)) | dealt=8 taken=0
  R7[Lagavulin Matriarch: Atk(18)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0

F19 [monster] Tunneler (6R, HP 84->84, loss=0, WIN)
  R1[Tunneler: Atk(13)]: Suppress(13dmg,1+Weak(3))->Defend+(+8blk)->Cloak and Dagger(+6blk)->Shiv(4dmg,exhaust:1)->Strike(6dmg) | dealt=23 taken=0
  R2[Tunneler: Buff, Defend]: Adrenaline(+1energy,exhaust:1)->Acrobatics->Haze(20dmg,power:+Draw Cards Next Turn(2))->Predator+(6dmg)->Strike | dealt=26 taken=0
  R3[Tunneler: Atk(17)]: Backflip+(+8blk)->Survivor(+8blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Tunneler: Atk(23)]: Suppress(1+Weak(3))->Predator+(1dmg,power:+Draw Cards Next Turn(2),1-Burrowed)->Strike(6dmg) | dealt=7 taken=0
  R5[Tunneler: Atk(9)]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R6[Tunneler: Buff, Defend]: Predator+ | dealt=0 taken=0

F20 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (6R, HP 84->80, loss=4, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Suppress->Acrobatics->Adrenaline(+1energy,exhaust:1)->Dagger Throw+->Survivor(+8blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)]: Defend(+5blk)->Defend+(+8blk)->Strike | dealt=0 taken=4
  R3[Exoskeleton: Buff+Exoskeleton: Atk(2x3=6)+Exoskeleton: Atk(10)]: Suppress(9dmg,1+Weak(3))->Cloak and Dagger(+6blk)->Shiv(exhaust:1)->Backflip+(+8blk)->Strike(6dmg) | dealt=15 taken=0
  R4[Exoskeleton: Atk(3x3=9)+Exoskeleton: Buff]: Dagger Throw+(9dmg)->Haze(+5blk)->Defend(+5blk)->Defend | dealt=0 taken=0
  R5[Exoskeleton: Atk(10)]: Acrobatics->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R6[Exoskeleton: Buff]: Suppress(9dmg,1+Weak(3))->Dagger Throw+ | dealt=9 taken=0

F21 [monster] Hunter Killer (4R, HP 80->68, loss=12, WIN)
  R1[Hunter Killer: Debuff]: Suppress(13dmg,1+Weak(3))->Dagger Throw+(12dmg)->Haze+(1Poison(6→15))->Bubble Bubble(6dmg)->Strike | dealt=19 taken=0
  R2[Hunter Killer: Atk(5x3=15)]: Backflip+(+8blk,power:+Strength(-1),power:+Dexterity(-1))->Cloak and Dagger(+5blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Adrenaline(+1energy,power:Strength(-2→-3),power:Dexterity(-2→-3),exhaust:1)->Defend(+2blk,power:Strength(-3→-4),power:Dexterity(-3→-4))->Strike(2dmg,power:Strength(-4→-5),power:Dexterity(-4→-5))->Shiv(power:Strength(-5→-6),power:Dexterity(-5→-6),exhaust:1) | dealt=2 taken=0
  R3[Hunter Killer: Atk(12)]: Predator+(20dmg,power:+Draw Cards Next Turn(2),power:+Strength(-1),power:+Dexterity(-1))->Strike(5dmg,power:Strength(-1→-2),power:Dexterity(-1→-2)) | dealt=25 taken=12
  R4[Hunter Killer: Atk(7x3=21)]: Predator+(20dmg,power:+Draw Cards Next Turn(2),power:+Strength(-1),power:+Dexterity(-1)) | dealt=20 taken=0

F22 [monster] Ovicopter (11R, HP 68->44, loss=24, WIN)
  R1[Ovicopter: Summon]: Suppress(13dmg,1+Weak(3))->Acrobatics->Adrenaline(+1energy,exhaust:1)->Dagger Throw+(12dmg)->Malaise(2Weak(3→5),+Strength(-2),exhaust:1) | dealt=13 taken=0
  R2[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(10)]: Backflip+(+8blk)->Predator+(power:+Draw Cards Next Turn(2)) | dealt=0 taken=2
  R3[Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(3), Debuff]: Backflip+(+8blk)->Dagger Throw+(12dmg)->Haze+(+8blk)->Defend+(13dmg,1Weak(3→6))->Suppress | dealt=13 taken=0
  R4[Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Summon]: Cloak and Dagger(+6blk)->Shiv(exhaust:1)->Strike->Strike(6dmg) | dealt=6 taken=0
  R5[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(15)]: Acrobatics->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=2
  R6[Hatchling: Atk(4)+Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(3), Debuff]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R7[Hatchling: Atk(6)+Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Buff]: Backflip+(+8blk)->Cloak and Dagger(+6blk)->Suppress->Shiv->Strike | dealt=0 taken=0
  R8[Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Atk(19)]: Acrobatics->Haze+->Suppress(12dmg)->Dagger Throw+(+5blk)->Defend | dealt=0 taken=20
  R9[Hatchling: Atk(4)+Ovicopter: Atk(8), Debuff]: Backflip+(+8blk)->Cloak and Dagger(+6blk)->Shiv(4dmg)->Strike(6dmg) | dealt=10 taken=0
  R10[Hatchling: Atk(6)+Ovicopter: Summon]: Strike(6dmg)->Bubble Bubble(1Poison(5→14))->Survivor(+8blk) | dealt=6 taken=0
  R11[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(25)]: Acrobatics->Strike(6dmg)->Cloak and Dagger(+6blk)->Shiv(4dmg) | dealt=10 taken=0

F30 [elite] Infested Prism (5R, HP 40->36, loss=4, WIN)
  R1[Infested Prism: Atk(22)]: Suppress(13dmg,+1energy,1+Weak(3))->Dash(10dmg,+10blk)->Snakebite(1Poison(6→13))->Defend(+5blk)->Defend(+5blk) | dealt=23 taken=0
  R2[Infested Prism: Atk(12), Defend]: Cloak and Dagger(+6blk)->Shiv(4dmg,+1energy,exhaust:1)->Defend+(+8blk)->Malaise+(2Weak(2→5),+Strength(-3),exhaust:1) | dealt=4 taken=0
  R3[Infested Prism: Atk(4x3=12)]: Adrenaline+(+2energy,exhaust:1)->Dagger Throw->Haze->Acrobatics+(5dmg)->Dagger Throw+(1Poison(15→24))->Bubble Bubble(+8blk)->Backflip+(6dmg,1Poison(24→27))->Poisoned Stab | dealt=6 taken=4
  R4[Infested Prism: Buff, Defend]: Dagger Throw+(12dmg)->Haze+(10dmg,+10blk)->Dash(6dmg)->Strike | dealt=16 taken=0
  R5[Infested Prism: Atk(17)]: Suppress(1Weak(2→5))->Dagger Throw(2dmg)->Haze(1Poison(35→42))->Snakebite(6dmg)->Strike | dealt=6 taken=0

F33 [boss] multi:Crusher+Rocket (10R, HP 63->32, loss=31, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Suppress(13dmg,1+Weak(3))->Dark Shackles(2+Strength(-9),+Dark Shackles(9),exhaust:1)->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Defend(+8blk) | dealt=33 taken=0
  R2[Crusher: Atk(3)+Rocket: Atk(27)]: Adrenaline+(+2energy,exhaust:1)->Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Dagger Throw+(12dmg)->Backflip+(+11blk)->Dagger Throw(9dmg)->Haze(+8blk)->Defend | dealt=0 taken=0
  R3[Crusher: Atk(6x2=12), Debuff+Rocket: Buff]: Accelerant+(power:+Accelerant(2))->Cloak and Dagger(+9blk)->Shiv(6dmg,exhaust:1)->Bubble Bubble(1Poison(3→12)) | dealt=6 taken=0
  R4[Crusher: Buff+Rocket: Atk(49)]: Acrobatics+->Backflip+(+8blk)->Malaise+(2+Weak(2),-Strength,exhaust:1) | dealt=0 taken=15
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Suppress(11dmg,1+Weak(3))->Cloak and Dagger(+6blk)->Shiv(4dmg)->Defend(+6blk)->Defend(+6blk) | dealt=15 taken=0
  R6[Crusher: Atk(10)+Rocket: Atk(4)]: Dagger Throw->Haze+(1Poison(9→18))->Bubble Bubble(+8blk)->Defend | dealt=0 taken=6
  R7[Crusher: Atk(4)+Rocket: Atk(27)]: Cloak and Dagger(+9blk)->Shiv(6dmg)->Bubble Bubble(1Poison(3→12))->Backflip+(+11blk)->Calculated Gamble(1Poison(15→19),1Poison(12→16),exhaust:1)->Suppress(15dmg,1+Weak(3)) | dealt=21 taken=0
  R8[Rocket: Buff]: Predator+(power:+Draw Cards Next Turn(2))->Exterminate | dealt=0 taken=0
  R9[Rocket: Atk(29)]: Dagger Throw(11dmg)->Haze(+11blk)->Defend+(+8blk)->Defend | dealt=0 taken=10
  R10[Rocket: Sleep]: Strike(power:-Dexterity,power:-Surrounded,power:-Strength,power:-Accelerant) | dealt=0 taken=0

F35 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (3R, HP 91->91, loss=0, WIN)
  R1[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff+Scroll of Biting: Atk(14)]: Dark Shackles(exhaust:1)->Suppress(13dmg,1+Weak(3))->Accelerant+(power:+Accelerant(2))->Survivor(+9blk)->Haze+ | dealt=13 taken=0
  R2[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Buff]: Backflip+(+9blk)->Bubble Bubble->Defend(+6blk) | dealt=0 taken=0
  R3[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)]: Dagger Throw+->Poisoned Stab(power:-Dexterity,power:-Accelerant) | dealt=0 taken=0

F39 [monster] Devoted Sculptor (4R, HP 91->96, loss=0, WIN)
  R1[Devoted Sculptor: Buff]: Adrenaline+(+2energy,exhaust:1)->Suppress(13dmg,1+Weak(3))->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Poisoned Stab(6dmg,1+Poison(3))->Backflip+(+9blk)->Dagger Throw(9dmg)->Haze(2+Strength(-9),+Dark Shackles(9),exhaust:1)->Dark Shackles | dealt=39 taken=0
  R2[Devoted Sculptor: Atk(9)]: Defend+(+9blk)->Calculated Gamble(exhaust:1)->Accelerant+(power:+Accelerant(2))->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=0 taken=0
  R3[Devoted Sculptor: Atk(15)]: Bubble Bubble(1Poison(3→12))->Noxious Fumes(power:+Noxious Fumes(2))->Defend(+6blk)->Survivor(+9blk) | dealt=0 taken=0
  R4[Devoted Sculptor: Atk(30)]: Suppress(13dmg,1+Weak(3))->Dagger Throw+(12dmg)->Haze+(+6blk)->Defend(+6blk)->Defend | dealt=13 taken=0

F40 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (7R, HP 96->83, loss=13, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Dark Shackles(2+Strength(-9),+Dark Shackles(9),exhaust:1)->Suppress(13dmg,1+Weak(3))->Well-Laid Plans(power:+Well-Laid Plans(1))->Accelerant+(power:+Accelerant(2))->Survivor(+9blk) | dealt=13 taken=3
  R2[Flail Knight: Atk(15)+Spectral Knight: Atk(11)+Magi Knight: Debuff]: Snakebite(1+Poison(7))->Calculated Gamble(exhaust:1)->Backflip+(+9blk)->Adrenaline+(+2energy,exhaust:1)->Deadly Poison+(1Poison(7→14))->Bubble Bubble(1Poison(14→23))->Dagger Throw+(18dmg)->Haze(13dmg)->Dagger Throw(+5blk,power:+Block Next Turn(5))->Dodge and Roll | dealt=0 taken=0
  R3[Flail Knight: Atk(9x2=18)+Magi Knight: Atk(10)]: Bubble Bubble(1Poison(1→10))->Cloak and Dagger(+7blk)->Shiv(4dmg,exhaust:1)->Defend(+6blk) | dealt=4 taken=10
  R4[Flail Knight: Atk(15)+Magi Knight: Defend]: Acrobatics->Haze(1Poison(11→20))->Bubble Bubble(power:+Noxious Fumes(2))->Noxious Fumes | dealt=0 taken=0
  R5[Magi Knight: Atk(35)]: Suppress(8dmg,1+Weak(3))->Cloak and Dagger(+7blk)->Shiv(4dmg)->Mirage(+4blk,exhaust:1)->Defend(+6blk)->Survivor(+9blk) | dealt=12 taken=0
  R6[Magi Knight: Atk(7)]: Dodge and Roll(+5blk,power:+Block Next Turn(5))->Defend(+6blk)->Dagger Throw(9dmg)->Haze(exhaust:1)->Malaise | dealt=0 taken=0
  R7[Magi Knight: Defend]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Poisoned Stab(power:-Dexterity,power:-Well-Laid Plans,power:-Accelerant,power:-Dampen,power:-Noxious Fumes,power:-Draw Cards Next Turn) | dealt=15 taken=0

F43 [elite] Mecha Knight (6R, HP 76->49, loss=27, WIN)
  R1[Mecha Knight: Atk(25)]: Backflip+(+9blk)->Suppress(13dmg,1Artifact(3→2))->Dark Shackles(1Artifact(2→1),exhaust:1)->Defend+(+9blk)->Dodge and Roll(+5blk,power:+Block Next Turn(5))->Malaise+(2+Weak(2),-Artifact,exhaust:1) | dealt=13 taken=0
  R2[Mecha Knight: StatusCard(4)]: Dagger Throw(9dmg)->Haze(1Poison(4→13))->Bubble Bubble(+7blk)->Cloak and Dagger(4dmg,exhaust:1)->Shiv(exhaust:1)->Calculated Gamble | dealt=4 taken=0
  R3[Mecha Knight: Defend, Buff]: Accelerant+(power:+Accelerant(2))->Dagger Throw+(12dmg)->Backflip(+6blk) | dealt=0 taken=0
  R4[Mecha Knight: Atk(40)]: Adrenaline+(+2energy,exhaust:1)->Bubble Bubble(1Poison(9→18))->Noxious Fumes(power:+Noxious Fumes(2))->Well-Laid Plans(power:+Well-Laid Plans(1))->Defend(+6blk)->Defend(+6blk)->Survivor(+9blk) | dealt=0 taken=19
  R5[Mecha Knight: StatusCard(4)]: Dagger Throw+(12dmg)->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=35 taken=2
  R6[Mecha Knight: Defend, Buff]: Acrobatics+->Snakebite(1Poison(16→23)) | dealt=0 taken=6

F45 [monster] Slimed Berserker (4R, HP 77->77, loss=0, WIN)
  R1[Slimed Berserker: StatusCard(10)]: Suppress+(19dmg,1+Weak(5))->Noxious Fumes(power:+Noxious Fumes(2))->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Dagger Throw+(12dmg)->Malaise+(2Weak(5→6),+Strength(-1),exhaust:1) | dealt=39 taken=0
  R2[Slimed Berserker: Atk(2x4=8)]: Well-Laid Plans(power:+Well-Laid Plans(1))->Bubble Bubble(1Poison(2→11))->Accelerant+(power:+Accelerant(2)) | dealt=0 taken=0
  R3[Slimed Berserker: Debuff, Buff]: Backflip(+6blk)->Bubble Bubble(1Poison(10→19))->Calculated Gamble(exhaust:1)->Adrenaline+(+2energy,exhaust:1)->Deadly Poison+(1Poison(19→26))->Acrobatics+->Haze+(19dmg,1Weak(4→9))->Suppress+(12dmg)->Exterminate | dealt=31 taken=0
  R4[Slimed Berserker: Atk(24)]: Mirage+(+32blk,exhaust:1)->Defend+(+9blk) | dealt=0 taken=0

F48 [boss] Door (7R, HP 96->49, loss=47, WIN)
  R1[Door: Summon]: Acrobatics+->Haze(power:+Accelerant(2))->Accelerant+(+9blk)->Backflip+ | dealt=0 taken=0
  R2[Doormaker: Atk(30)]: Backflip(+6blk,exhaust:1)->Noxious Fumes(power:+Noxious Fumes(2))->Malaise+(2+Strength(-2),+Weak(2),exhaust:1) | dealt=15 taken=1
  R3[Doormaker: Atk(16)]: Snakebite(1Poison(2→9))->Deadly Poison+(1Poison(9→16))->Mirage+(+17blk,exhaust:1)->Defend(+6blk) | dealt=0 taken=0
  R4[Doormaker: Atk(8x2=16), Buff]: Adrenaline+(+1energy,exhaust:1)->Bubble Bubble(1Poison(15→24))->Bubble Bubble(1Poison(24→33)) | dealt=0 taken=16
  R5[Doormaker: Atk(31)]: Suppress+(19dmg,1+Weak(5),exhaust:1)->Piercing Wail(2Strength(1→-5),+Piercing Wail(6),exhaust:1)->Dagger Throw+(12dmg)->Haze+(2Strength(-5→-13),Piercing Wail(6→14),exhaust:1)->Piercing Wail+ | dealt=19 taken=12
  R6[Doormaker: Atk(18)]: Bubble Bubble(1Poison(37→46))->Deadly Poison+(1Poison(46→53))->Snakebite(1Poison(53→60)) | dealt=0 taken=18
  R7[Doormaker: Atk(8x2=16), Buff]: Exterminate(power:-Dexterity,power:-Accelerant,power:-Noxious Fumes) | dealt=0 taken=0

### Non-combat Decisions (217 decisions)
F1 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Winged Boots provides incredible routing flexibility, allowing us to snipe high-value nodes like Elites or Campfires, or dodge dangerous areas if our HP is low. The other options are either low impact (Transform 1) or have a significant downside (lose a chest).
  strategic_note: Foundation deck plan: find early flat damage to defeat Act 1 elites, then transition to a scaling poison or discard engine. Keep the deck thin and focus on immediate power.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=3) | source=llm
  HP 70->70 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Standard Act 1 opening: taking early hallway fights to draft foundational damage cards. Following the recommended route to establish a baseline before using Winged Boots to optimize later transitions.
  strategic_note: Foundation deck plan: prioritize finding high-efficiency front-loaded damage in early hallway fights to survive the first Elite. Use Winged Boots later to potentially path into a second Elite or a critical rest site once the deck engine begins to form.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 99->113 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 113->113 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim potion: Regen Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 113->113 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 63->63 | Gold 113->113 | Deck 12->13
  deck_change: picked Predator
  reasoning: Floor 2 requires frontloaded damage to handle early Act 1 elites like Gremlin Nob and Lagavulin. Predator provides 15 damage and crucial card draw for the following turn, significantly improving our early game output.
  strategic_note: Foundation plan: survive with frontload damage like Predator and efficient block while looking for a scaling engine. Prioritize elite fights for relics and card rewards.

F2 [map] choose_map_node (option_index=1) | source=llm
  HP 63->63 | Gold 113->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Floor 2 is too early for a shop with only 113 gold. According to expert knowledge, I should prioritize hallway fights early on to 'patch fundamentals' and find the flat damage cards necessary to survive the Act 1 Elite on Floor 7.
  strategic_note: Foundation stage: prioritize monster fights to find high-impact flat damage cards like Poisoned Stab or Blade Dance to prepare for the first Elite; skip early shops to accumulate gold for a high-value relic or key removal later.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 113->133 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 20 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 133->133 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Cure All

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 133->133 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 59->59 | Gold 133->133 | Deck 13->14
  deck_change: picked Haze
  reasoning: Haze is a Sly card that applies AoE poison, immediately comboing with Survivor to give us a free AoE poison application. It fits into both discard and poison scaling plans, which aligns with our trajectory. While clunky to draw without a discard outlet, we start with Survivor and draw 7 cards on turn 1, giving us a good chance to line them up.
  strategic_note: Foundation plan: seeking flat damage and discard/poison enablers. We have Predator for frontload and Haze for AoE/discard synergy. Prioritize cheap attacks (like Dagger Throw) and discard outlets (like Acrobatics).

F3 [map] choose_map_node (option_index=1) | source=llm
  HP 59->59 | Gold 133->133 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. At this early stage of Act 1, Unknown nodes provide high-value events that can jumpstart the deck's direction or provide gold/removals without the chip damage of a hallway fight, especially since we already have 133 gold to potentially spend later.
  strategic_note: Foundation deck focusing on securing early flat damage to tackle Act 1 elites, while looking for a long-term scaling engine like poison or discard; prioritize high-impact card upgrades and thin deck composition.

F4 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=combat,deck_building,routing) | source=llm
  HP 59->59 | Gold 133->133 | Deck 14->14
  deck_change: no deck change
  reasoning: Enchanting an attack with Sharp 2 (or adding damage) helps increase our upfront burst for Act 1 elites. Neutralize or Predator will benefit nicely from the extra damage output.
  strategic_note: Foundation deck focusing on securing early flat damage to tackle Act 1 elites, while looking for a long-term scaling engine like poison or discard; prioritize high-impact card upgrades and thin deck composition.

F4 [card_select] select_deck_card (option_index=5) | source=llm
  HP 59->59 | Gold 133->133 | Deck 14->14
  deck_change: no deck change
  reasoning: Neutralize is one of the best early upgrades for The Silent. Increasing Weak duration from 1 to 2 turns provides massive damage mitigation against early elites like Gremlin Nob and Lagavulin, allowing us to survive while dealing our damage.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 59->59 | Gold 133->133 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=1) | source=llm
  HP 59->59 | Gold 133->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to accumulate monster rewards and draft essential front-loaded damage. With high HP and Winged Boots as a safety net, I can afford to take these early fights to stabilize the deck before the first elite.
  strategic_note: Foundation stage: prioritizing hallway fights for front-loaded damage cards to handle Act 1 elites while looking for a scaling engine like poison or discard. Use Winged Boots to pivot if pathing towards a crucial campfire or shop becomes necessary.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 133->150 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 150->150 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 58->58 | Gold 150->150 | Deck 14->15
  deck_change: picked Cloak and Dagger
  reasoning: Cloak and Dagger provides solid immediate value as an efficient hybrid card (6 block, 4 damage for 1 energy), which helps us survive early Act 1 hallways and serves as a potential foundation for a Shiv engine later. Piercing Wail is great, but we need more proactive stats right now.
  strategic_note: Foundation plan: prioritize immediate damage and efficient mitigation to survive Act 1 elites. Keep an eye out for ways to discard Haze for free (like Survivor or Acrobatics) to leverage its AoE poison without paying 3 energy.

F5 [map] choose_map_node (option_index=2) | source=llm
  HP 58->58 | Gold 150->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the recommended route to a hallway fight. The deck is in the foundation stage and needs more card rewards to establish a reliable damage or scaling engine before the first Elite. I currently have 150 gold, which is a good amount, but it's better to save it for the shop later in the act when I have more gold and a better sense of what the deck needs.
  strategic_note: Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a long-term engine like poison or discard; prioritize high-impact upgrades and deck thinning.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 150->166 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 166->166 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 52->52 | Gold 166->166 | Deck 15->16
  deck_change: picked Backflip
  reasoning: Backflip is a premium cycling tool that provides minor block while helping to dig for key damage cards like Predator and Haze. Drawing cards is vital to ensure our deck flows well on 3 energy.
  strategic_note: Foundation phase: surviving with Predator's raw damage and Haze's AoE poison while looking for a core scaling engine (either poison or shivs). Prioritize high-impact win conditions, more draw/cycle, and removals for basic Strikes/Defends.

F6 [map] choose_map_node (option_index=2) | source=llm
  HP 52->52 | Gold 166->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Following the recommended route to secure another card reward. At 52 HP and floor 6, the deck still needs to solidify its foundation of front-loaded damage before tackling elites or harder encounters, especially as a Silent. The Winged Boots provide flexibility later, but for now, building deck quality via hallway fights is the priority.
  strategic_note: Foundation deck focusing on securing early flat damage; prioritize card rewards that solve Gremlin Nob and Lagavulin before pivoting to scaling or excessive elite hunting.

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 166->183 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 183->183 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F7 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 52->52 | Gold 183->183 | Deck 16->17
  deck_change: picked Acrobatics
  reasoning: Acrobatics is premium cycle, and critically, it allows us to discard Haze to trigger its Sly effect, playing a 3-cost AoE poison card for free. This gives us a massive power spike for multi-enemy fights.
  strategic_note: Foundation plan: Use Acrobatics and Survivor to trigger Haze's Sly effect for free AoE poison. Prioritize efficient frontload, draw, and defensive tools to survive Act 1. Do not over-commit to a single engine until we find a strong multiplicative scaling piece.

F7 [map] choose_map_node (option_index=3) | source=llm
  HP 52->52 | Gold 183->0 | Deck 17->17
  deck_change: no deck change
  reasoning: With 52 HP and Winged Boots available, I am strong enough to challenge an Elite. Act 1 Elites are the primary source of power-spiking relics, and I have 183 gold to spend at the upcoming shop to shore up any damage taken. Choosing the right-side Elite (c5,r7) keeps me on a path that still includes future rest sites and a shop before the boss.
  strategic_note: Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a long-term scaling engine; currently leveraging high HP and Winged Boots to aggressively hunt relics.

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 183->222 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 39 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->47 | Gold 222->222 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim relic: Mango

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 222->222 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 47->47 | Gold 222->222 | Deck 17->18
  deck_change: picked Malaise
  reasoning: Malaise is a premium rare that solves dangerous multi-attack encounters like Act 1 bosses and Act 2 elites. It provides massive, exhaustible damage mitigation.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F8 [map] choose_map_node (option_index=2) | source=llm
  HP 47->47 | Gold 222->222 | Deck 18->18
  deck_change: no deck change
  reasoning: Taking the Unknown node to avoid excessive chip damage from hallway fights. I have 222 gold and need to preserve HP to make the most of the upcoming shop and rest sites before the boss.
  strategic_note: Foundation deck focusing on securing early flat damage to tackle Act 1 elites while looking for a scaling engine like poison or discard; prioritize high-impact upgrades and thinning deck composition.

F9 [event] choose_event_option (option_index=0) | source=llm
  HP 47->47 | Gold 222->222 | Deck 18->19
  deck_change: added Spoils Map
  reasoning: Taking an unplayable card as a curse is a steep short-term penalty, but 600 Gold in Act 2 is an incredibly powerful run-winning reward. Given that I have Ring of the Snake to mitigate Turn 1 bad draws and a relatively safe path to the Act 1 Boss, the Spoils Map is a worthwhile investment.
  strategic_note: Foundation deck looking for scaling discard or poison synergies; currently prioritizing early flat damage and mitigation while holding a Spoils Map for a massive Act 2 gold injection, aiming to remove basic strikes when possible.

F9 [event] choose_event_option (option_index=0) | source=auto
  HP 47->47 | Gold 222->222 | Deck 19->19
  deck_change: no deck change
  reasoning: Only option: Proceed

F9 [map] choose_map_node (option_index=2) | source=llm
  HP 47->47 | Gold 222->222 | Deck 19->19
  deck_change: no deck change
  reasoning: This node follows the recommended route toward a late-act shop (r13) where my 222 gold can be converted into power. The path offers two rest sites for upgrades or safety and avoids additional elites to conserve HP for the boss.
  strategic_note: Foundation deck focusing on securing early flat damage; prioritize converting gold at the upcoming shop and using rest sites for high-impact upgrades before the Act 1 boss.

F10 [treasure] open_chest | source=random
  HP 47->47 | Gold 222->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: upgraded Backflip->Backflip+, Defend->Defend+
  reasoning: Claim: War Paint

F10 [treasure] proceed | source=random
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=4) | source=llm
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the recommended route to the Unknown node at c6,r10. Current HP (56%) is sufficient to handle floor variance, and this path leads toward a high-value Shop where my 266 Gold can be converted into immediate power or deck thinning before the Act 1 boss.
  strategic_note: Foundation discard/poison deck prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.

F11 [event] choose_event_option (option_index=2) | source=llm
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: We are heading into a shop on Floor 14 with 266 gold, which is enough to buy a relic, a premium card, or multiple removals. Spending 150 gold on a temporary buff (Ember Tea) would severely weaken our shop purchasing power. Tea of Discourtesy has no gold cost and its penalty (2 Dazed next combat) is negligible.
  strategic_note: Foundation discard/poison deck prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.

F11 [event] choose_event_option (option_index=0) | source=auto
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Only option: Proceed

F11 [map] choose_map_node (option_index=3) | source=llm
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. With 47 HP, I am healthy enough to potentially Smith a key card, and this path leads directly toward a high-value Shop where I can spend my 266 gold to improve the deck's foundation before the boss.
  strategic_note: Foundation discard/poison plan: prioritizing early damage and mitigation while seeking a shop to convert high gold into removals or key scaling pieces before the boss.

F12 [rest_site] choose_rest_option (option_index=1, smith_card_index=11, note_scope=run, note_triggers=all) | source=llm
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: upgraded Predator->Predator+
  reasoning: With 47/84 HP and another rest site before the boss, we can afford to Smith. Predator is our primary source of frontload damage, and upgrading it to 20 damage will help end the upcoming F15 hallway fight quickly and preserve HP.
  strategic_note: Foundation discard/poison plan: prioritizing early damage and mitigation; holding Spoils Map for Act 2 gold while seeking a shop to spend current gold on removals or key scaling pieces.

F12 [rest_site] proceed | source=auto
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F12 [map] choose_map_node (option_index=3) | source=llm
  HP 47->47 | Gold 266->266 | Deck 19->19
  deck_change: no deck change
  reasoning: With 266 gold, my priority is reaching the shop safely to convert that gold into scaling or removals before the Act 1 boss. Taking the Unknown node reduces the risk of chip damage compared to a guaranteed monster fight, preserving HP for the boss.
  strategic_note: Foundation discard and poison deck; prioritizing health preservation and gold accumulation to maximize the impact of the upcoming shop visit before the boss.

F13 [shop] buy_card (option_index=2) | source=plan
  HP 47->47 | Gold 266->215 | Deck 19->20
  deck_change: bought Snakebite
  reasoning: Shop plan [1/4]: Provides reliable, retainable base poison to start our scaling engine.

F13 [shop] buy_card (option_index=3) | source=plan
  HP 47->47 | Gold 215->137 | Deck 20->21
  deck_change: bought Bubble Bubble
  reasoning: Shop plan [2/4]: Synergizes perfectly with Snakebite and Haze, establishing a core poison win condition for bosses.

F13 [shop] remove_card_at_shop | source=plan
  HP 47->47 | Gold 137->137 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Removing a Strike to improve draw consistency and let our new poison pieces cycle faster.

F13 [card_select] select_deck_card (option_index=0) | source=llm
  HP 47->47 | Gold 137->62 | Deck 21->20
  deck_change: lost Strike
  reasoning: Removing a basic Strike thins the deck and increases the probability of drawing our poison engine cards and cycle skills. Strike is the weakest card in the deck and actively hinders drawing into Predator, Snakebite, and Bubble Bubble.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F13 [shop] buy_potion (option_index=1) | source=plan
  HP 47->47 | Gold 62->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Shop plan [4/4]: We have several high-cost cards (Predator+, Snakebite) and this potion will smooth out a crucial setup turn against the upcoming Act 1 Boss.

F13 [shop] close_shop_inventory | source=plan
  HP 47->47 | Gold 13->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F13 [shop] proceed | source=auto
  HP 47->47 | Gold 13->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F13 [map] choose_map_node (option_index=5) | source=llm
  HP 47->47 | Gold 13->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Following Route Intelligence to hit a shop before the boss. Although gold is very low (13), I am at 56% HP and the Winged Boots provide flexibility if the shop visit proves completely useless. The alternative is an Elite (index 4) which is risky at this health, or more hallway fights which I've already done several of.
  strategic_note: Foundation discard/poison deck seeking consistency; prioritizing the final shop and rest site to stabilize for the Act 1 boss while preserving HP.

F14 [shop] close_shop_inventory | source=llm
  HP 47->47 | Gold 13->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F14 [shop] proceed | source=auto
  HP 47->47 | Gold 13->13 | Deck 20->20
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F14 [map] choose_map_node (option_index=3) | source=llm
  HP 47->47 | Gold 13->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the Route Guide recommendation to hit a monster node. At floor 14, I need one final chance to find a card reward or potion that stabilizes the deck for the Act 1 boss. My gold is low (13), so shops are useless, and I've already used many unknowns. A hallway fight is the most reliable way to gain value before the final rest site.
  strategic_note: Foundation discard and poison deck seeking final damage pieces and an upgrade before the boss; focusing on high-value hallway fights to refine the deck's output.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 13->23 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 46->46 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: The deck currently has a strong poison foundation (Snakebite, Bubble Bubble, Haze) but is struggling with energy constraints since Snakebite and Predator both cost 2. Adding a second Snakebite at 2-cost would be too clunky. Prepared is card disadvantage unupgraded, and Sucker Punch is unnecessary with Neutralize and Malaise. Skipping keeps the deck lean to cycle to our core pieces.
  strategic_note: Committed poison plan: retain Snakebite to combo with Bubble Bubble, use Acrobatics/Survivor to trigger Haze, and defend with Backflip+. Needs more energy or cheaper poison (like Noxious Fumes), and Catalyst. Skip heavy cards.

F15 [map] choose_map_node (option_index=2) | source=llm
  HP 46->46 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: Standard pathing toward the boss. I am at 46/84 HP, which is enough to comfortably Smith a key card to increase my deck's power for the Act 1 Boss fight. All available nodes lead to the same boss encounter, so I'll follow the recommended step.
  strategic_note: Foundation deck focusing on discard and poison; looking to smith a key card at this final rest site to secure the Act 1 boss win, then pivoting to gold accumulation via Spoils Map in Act 2.

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 46->71 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: HP fully restores after the boss, but going into the Act 1 boss with only 46 HP is risky. Healing to 71 ensures we survive the boss fight without dying to bad draw RNG, even though Malaise+ or Neutralize+ would be strong upgrades.
  strategic_note: Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.

F16 [rest_site] proceed | source=auto
  HP 71->71 | Gold 23->23 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 71->71 | Gold 23->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 23->123 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 123->123 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 58->58 | Gold 123->123 | Deck 20->21
  deck_change: picked Adrenaline
  reasoning: Adrenaline is a premium generic enabler that costs 0, draws 2, and gives 1 energy. It fits perfectly into any deck, improving consistency, helping us cycle our discard/poison synergies, and accelerating setup without requiring specific synergy.
  strategic_note: Leaning towards poison and discard synergies (Snakebite, Bubble Bubble, Haze + Acro/Survivor). Use Adrenaline to accelerate setup and cycle fast. Prioritize efficient block and draw; skip narrow shiv/attack synergies.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 58->84 | Gold 123->123 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2) | source=llm
  HP 84->84 | Gold 123->123 | Deck 21->21
  deck_change: changed: +Suppress; -Neutralize
  reasoning: Archaic Tooth transforms Neutralize into Suppress, an incredibly powerful 0-cost Innate card that deals 11 damage and applies 3 Weak. This gives us exceptional Turn 1 damage mitigation in every fight, allowing us to safely set up our poison engines without bleeding HP. It synergizes perfectly with Ring of the Snake's extra turn 1 draw.
  strategic_note: Foundation discard/poison deck: rely on Suppress to mitigate early damage while setting up poison pieces (Snakebite, Bubble Bubble) and Malaise; prioritize finding card removal and more efficient poison/block scaling.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 84->84 | Gold 123->123 | Deck 21->21
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 84->84 | Gold 123->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Following the recommended route to build deck quality. Act 2 requires scaling and AoE; hallway fights are the most reliable way to find these missing pieces early in the act. Avoiding early events or shops with low gold prevents being underpowered for the mid-act elites.
  strategic_note: Foundation discard and poison deck: prioritizing early Act 2 hallway fights to find AoE and reliable block before attempting elites. I need to convert my current high HP into deck quality through aggressive drafting.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 123->138 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 138->138 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Attack Potion

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 138->138 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 84->84 | Gold 138->138 | Deck 21->22
  deck_change: picked Dagger Throw+
  reasoning: Dagger Throw+ provides 12 upfront damage to help clear Act 2 hallways, replaces itself by drawing a card, and gives us a targeted discard to trigger Haze's Sly effect or get rid of the unplayable Spoils Map.
  strategic_note: Foundation plan: surviving with efficient attacks and defense while looking for a definitive scaling engine. Currently leveraging poison and Sly mechanics. Needs strong block scaling or a true core scaling card.

F19 [map] choose_map_node (option_index=2) | source=llm
  HP 84->84 | Gold 138->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which warns against early Unknown chaining. Standard monsters provide essential card rewards and gold to stabilize the deck for the middle of the act, whereas early events can be high-variance and punishing for a deck that hasn't found its primary Act 2 engine yet.
  strategic_note: Foundation discard/poison plan: hunt for poison scaling and defensive discard pieces in hallway fights to stabilize before tackling elites. Avoid early event chains; prioritize cards and gold to make future shops and rest sites more impactful.

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 80->80 | Gold 138->148 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 80->80 | Gold 148->148 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 80->80 | Gold 148->148 | Deck 22->23
  deck_change: picked Haze+
  reasoning: Haze+ provides incredible AoE poison application for 0 energy when discarded. With our discard outlets (Acrobatics, Survivor, Dagger Throw+), it is highly consistent and perfectly fuels our Bubble Bubble for heavy single-target poison. This solidifies our poison/discard core.
  strategic_note: Committed to discard-poison plan: use Acrobatics, Survivor, and Dagger Throw to discard Sly poison cards (Haze) for free AoE damage, then amplify with Bubble Bubble. Prioritize efficient block and further discard/draw to cycle fast. Skip narrow attacks and focus on surviving while passive poison scales.

F20 [map] choose_map_node (option_index=3) | source=llm
  HP 80->80 | Gold 148->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to a standard hallway fight. Act 2 requires stabilizing the deck with card rewards before taking elites or taking excessive unknown nodes. My current gold (148) is close to the 150+ threshold for a high-value shop later, so I need to accumulate more gold and potentially find AoE or more consistent poison application through combat rewards.
  strategic_note: Foundation discard/poison plan: utilizing Malaise to mitigate heavy hitters while poison scales. Prioritizing standard combats to find missing engine pieces and building gold for a high-impact shop visit; needs more reliable block and card draw.

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 148->168 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 20 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 168->168 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Stable Serum

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 168->168 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 68->68 | Gold 168->168 | Deck 23->23
  deck_change: no deck change
  reasoning: Our deck is currently leaning toward Poison (Haze, Bubble Bubble, Snakebite) and discard synergies (Sly Haze). None of these common cards significantly advance our win condition or provide needed scaling. Cloak and Dagger+ is efficient but adds minor frontload that doesn't solve Act 2/3 boss scaling. Skipping to keep the deck lean and improve our chances of drawing Adrenaline, Predator, and our Sly/discard combos.
  strategic_note: Committed to a Poison/Discard hybrid plan: use Acrobatics/Dagger Throw/Survivor to trigger Sly Haze for free AoE poison, then escalate with Bubble Bubble. Need block scaling (Footwork) and Catalyst/more card draw. Avoid adding more generic attacks.

F21 [map] choose_map_node (option_index=2) | source=llm
  HP 68->68 | Gold 168->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the Route Intelligence recommendation to prioritize hallway fights for card drafting. Act 2 requires scaling and AoE which the current deck still lacks; more combats provide the necessary opportunities to find these pieces before the mid-act elites and boss. Avoid the shop at index 3 for now, as I have a dedicated shop later in the route and need to improve deck quality first.
  strategic_note: Foundation discard and poison plan: using Malaise to mitigate heavy hits while poison scales. Currently hunting for consistent poison sources and AoE damage to handle Act 2's multiple-enemy encounters. Prioritizing hallway fights to stabilize the engine before shifting toward elite hunting or heavy shop investment.

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 168->184 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 184->184 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 44->44 | Gold 184->184 | Deck 23->24
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail provides unmatched mitigation against multi-hit attacks, which are common and deadly in Act 2 (Book of Stabbing, Byrds, Snake Plant). While a second Bubble Bubble would be nice for damage, surviving setup turns is crucial for our poison plan.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F22 [map] choose_map_node (option_index=1) | source=llm
  HP 44->44 | Gold 184->184 | Deck 24->24
  deck_change: no deck change
  reasoning: The Unknown node follows the recommended route and provides a break from hallway fights after a series of four consecutive combats. With 44/84 HP, I need to preserve health for the upcoming rest site and elite preparation. The Unknown node offers potential for non-combat utility or a manageable encounter, whereas the Monster nodes risk further chip damage that could force a Rest instead of a much-needed Smith at the next campfire.
  strategic_note: Foundation discard/poison plan: focus on thinning the deck at upcoming shops to increase the frequency of Malaise and poison applications while seeking more reliable block or card draw.

F23 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 44->39 | Gold 184->184 | Deck 24->24
  deck_change: no deck change
  reasoning: With a Rest Site immediately following this event and 44 HP remaining, I can afford to risk 5 HP to Reach Deeper and potentially secure a much better reward than just 35 gold.
  strategic_note: Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.

F23 [event] choose_event_option (option_index=1) | source=llm
  HP 39->33 | Gold 184->184 | Deck 24->24
  deck_change: no deck change
  reasoning: With 39 HP and a campfire on the next floor, I can afford to lose 6 HP to explore deeper into the Colossal Flower for a potentially larger reward, especially since I'm heading to a shop at Floor 25 and could use more resources.
  strategic_note: Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.

F23 [event] choose_event_option (option_index=0) | source=llm
  HP 33->33 | Gold 184->319 | Deck 24->24
  deck_change: no deck change
  reasoning: 135 free gold is extremely flexible and powerful with two shops coming up. Taking no damage keeps our HP healthier since we are at 33/84.
  strategic_note: Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking gold and card removal shops in Act 2 to refine the engine.

F23 [event] choose_event_option (option_index=0) | source=auto
  HP 33->33 | Gold 319->319 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F23 [map] choose_map_node (option_index=0) | source=llm
  HP 33->33 | Gold 319->319 | Deck 24->24
  deck_change: no deck change
  reasoning: With 33/84 HP, I am too low to safely take an Elite fight in Act 2, especially since my deck still needs to refine its defensive engine. A Rest Site is mandatory here to stabilize. Taking the left-most Rest Site (index 0) keeps me on the prescribed route toward a Shop where my 319 gold can be used to remove cards or buy key relics/powers.
  strategic_note: Foundation discard/poison plan: currently focusing on survival and stabilization. Malaise and poison are the primary scaling tools; I need to use this gold at the upcoming shop for card removals or high-impact defensive tools to survive Act 2 elites/boss.

F24 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 319->319 | Deck 24->24
  deck_change: upgraded Adrenaline->Adrenaline+
  reasoning: The upcoming path shows a Shop, Treasure, and another Rest Site before any forced combat. This means there is absolutely no risk of taking damage before we can rest again, making healing entirely unnecessary here. Adrenaline is arguably the highest-impact upgrade in the deck, doubling its net energy generation from 1 to 2, which allows for much smoother setup of our poison and defense cards.
  strategic_note: Foundation discard/poison plan: rely on Malaise to mitigate dangerous attacks while poison stacks via Haze and Snakebite. Use upcoming shops to thin Strikes and find more block density. Prioritize card draw and Sly triggers.

F24 [rest_site] proceed | source=auto
  HP 33->33 | Gold 319->319 | Deck 24->24
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F24 [map] choose_map_node (option_index=0) | source=llm
  HP 33->33 | Gold 319->319 | Deck 24->24
  deck_change: no deck change
  reasoning: With 319 gold and 33 HP, a shop is the highest value node available. I need to convert this gold into relics, deck thinning (removals), or scaling solutions to stabilize before the next boss. The route guide also recommends this shop to ensure I don't waste gold momentum.
  strategic_note: Foundation discard/poison plan: using Malaise to mitigate boss damage while poison scales; seeking card removal and key relics at this shop to refine the engine and increase consistency.

F25 [shop] buy_card (option_index=2) | source=plan
  HP 33->33 | Gold 319->244 | Deck 24->25
  deck_change: bought Calculated Gamble
  reasoning: Shop plan [1/4]: Incredible enabler for our two Haze cards. Discarding hand will trigger both Sly effects for up to 10 AoE Poison at 0 energy, while cycling into defensive cards.

F25 [shop] buy_card (option_index=1) | source=plan
  HP 33->33 | Gold 244->195 | Deck 25->26
  deck_change: bought Poisoned Stab
  reasoning: Shop plan [2/4]: Cheap 1-energy applicator to reliably enable Bubble Bubble without relying on the 2-energy Snakebite.

F25 [shop] buy_potion (option_index=1) | source=plan
  HP 33->33 | Gold 195->143 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Provides a burst of immediate Poison to fuel Bubble Bubble on turn 1 against dangerous Elites, saving HP while we are at 39%.

F25 [shop] remove_card_at_shop | source=plan
  HP 33->33 | Gold 143->143 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan [4/4]: Removing a Strike increases the density of our Poison enablers, card draw, and Block.

F25 [card_select] select_deck_card (option_index=0) | source=llm
  HP 33->33 | Gold 143->43 | Deck 26->25
  deck_change: lost Strike
  reasoning: Strikes are our weakest cards right now. Our main damage engine is poison and Predator, making Strike a dead draw that hinders cycling.
  strategic_note: Committed poison plan: stack poison with Snakebite/Haze/Bubble, retain setup tools with cycle, and defend with tools and Weak. Remove remaining Strikes.

F25 [shop] buy_card (option_index=0) | source=plan
  HP 33->33 | Gold 43->18 | Deck 25->26
  deck_change: bought Dagger Throw
  reasoning: Shop plan [1/1]: Cheap discard outlet to trigger our two Haze cards for free poison scaling, while also providing cycle.

F25 [shop] close_shop_inventory | source=plan
  HP 33->33 | Gold 18->18 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F25 [shop] proceed | source=auto
  HP 33->33 | Gold 18->18 | Deck 26->26
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 18->18 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 33->33 | Gold 18->665 | Deck 26->25
  deck_change: lost Spoils Map
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 33->40 | Gold 665->665 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim: Strawberry

F26 [treasure] proceed | source=random
  HP 40->40 | Gold 665->665 | Deck 25->25
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=1) | source=llm
  HP 40->40 | Gold 665->665 | Deck 25->25
  deck_change: no deck change
  reasoning: With 40 HP, taking an Elite (Option 0) is unnecessarily risky given the upcoming boss. The Unknown (Option 1) offers high-value potential for events or shops to spend my 665 gold, while still leading into a guaranteed Rest Site at r10 to recover before the final stretch. This follows the route recommendation and preserves Winged Boots charges for emergency pathing or skipping dangerous nodes later.
  strategic_note: Foundation Malaise and poison plan: mitigate multi-attacks with Malaise while building poison stacks. With over 600 gold, prioritize finding a shop to buy key relics or removals to thin the deck for consistency. Avoid elites until HP is higher or defense is fully stabilized.

F27 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 40->40 | Gold 665->665 | Deck 25->26
  deck_change: added Exterminate
  reasoning: Our deck relies on poison for scaling damage, but upfront AoE from Exterminate (12 damage to all enemies for 1 energy) is excellent for clearing weak minions or stripping Artifact charges. Squash applies Vulnerable, which doesn't synergize with our poison damage focus.
  strategic_note: Foundation Malaise and poison plan: mitigate attacks with Malaise while building poison stacks. Seek a shop to use 600+ gold for removals and key relics. Prioritize defensive consistency.

F27 [event] choose_event_option (option_index=0) | source=auto
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F27 [map] choose_map_node (option_index=1) | source=llm
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: no deck change
  reasoning: With 40/91 HP (44%) and a difficult Act 2 boss approaching, the Rest Site is the highest value node. It allows me to either heal to a safe threshold or, if I feel confident after the heal, potentially upgrade a key card. Since I have 665 gold, I need to stay healthy to reach the upcoming shop and final campfire to maximize my late-act scaling.
  strategic_note: Foundation poison/discard plan: rely on Malaise to neutralize high-damage enemies while poison stacks; prioritize adding block density and deck thinning at shops to ensure core skills are drawn reliably.

F28 [rest_site] choose_rest_option (option_index=1, smith_card_index=11) | source=llm
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: upgraded Malaise->Malaise+
  reasoning: With 40 HP and two Unknowns before a Shop and another Rest Site, we are healthy enough to greed a Smith. Malaise+ is one of our best mitigation tools, giving +1 to Strength reduction and Weakness, making it highly efficient even at 0 or 1 energy. This is a critical upgrade for the Act 2 Boss.
  strategic_note: Foundation discard/poison plan: mitigate damage with Malaise+ and Suppress while building poison stacks via Haze and Snakebite. Use upcoming shop to thin Strikes and find defensive or engine-accelerating relics.

F28 [rest_site] proceed | source=auto
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F28 [map] choose_map_node (option_index=2) | source=llm
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: no deck change
  reasoning: With 40/91 HP and 665 gold, prioritizing survival and preparing for the upcoming shop is critical. While the route suggests an Unknown, a Rest Site (Smith) directly increases my power for the final stretch of the act, and I have Winged Boots to adjust pathing later if needed. Given I have a massive gold stack, I need to ensure I reach the next shop alive to convert that gold into power.
  strategic_note: Foundation poison and Malaise plan: mitigate heavy hitters while stacking poison. With over 600 gold, the priority is surviving to the next shop for removals and high-impact relics to stabilize defense.

F29 [rest_site] choose_rest_option (option_index=1, smith_card_index=10) | source=llm
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: upgraded Acrobatics->Acrobatics+
  reasoning: 40 HP is enough to survive one Unknown node before the Shop, especially with our strong mitigation tools (Innate Suppress for turn 1 Weak, Malaise+). Upgrading Acrobatics provides a massive boost to our draw engine, helping us cycle into our poison and defensive cards faster. We can use the F32 rest site to heal for the Boss if needed.
  strategic_note: Foundation discard/poison plan: mitigate damage with Malaise+ and Suppress while building poison stacks via Haze and Snakebite. Use the upcoming shop to thin Strikes and find key defensive or engine-accelerating relics.

F29 [rest_site] proceed | source=auto
  HP 40->40 | Gold 665->665 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 665->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Elite

F30 [card_select] select_deck_card (option_index=1) | source=llm
  HP 40->40 | Gold 665->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Attack Potion makes the chosen card cost 0 this turn. Dash gives 10 block and 10 damage for 0 energy, which is excellent value and helps mitigate incoming damage.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 665->701 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 36 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 701->701 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 701->701 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim relic: Unceasing Top

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 701->701 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 36->36 | Gold 701->701 | Deck 26->26
  deck_change: no deck change
  reasoning: The deck is firmly committed to poison for scaling damage. Flick-Flack+ is an off-plan attack that dilutes our draws, and Prepared is too weak without an upgrade. Skipping keeps the deck focused on finding block scaling and cycling our existing poison/discard engines.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs block scaling like Footwork; skip off-plan attacks and expensive cards.

F30 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 701->701 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Shop

F31 [shop] buy_card (option_index=4) | source=plan
  HP 36->36 | Gold 701->623 | Deck 26->27
  deck_change: bought Accelerant
  reasoning: Shop plan [1/6]: Massive scaling for our poison engine, effectively doubling poison triggers.

F31 [shop] buy_relic (option_index=1) | source=plan
  HP 36->36 | Gold 623->445 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [2/6]: Provides passive Dexterity to enhance all our block cards, solving sustained mitigation.

F31 [shop] buy_relic (option_index=2) | source=plan
  HP 36->36 | Gold 445->266 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [3/6]: Since we are about to enter a Rest Site before the boss, this allows us to both heal and upgrade, providing immense value.

F31 [shop] remove_card_at_shop | source=plan
  HP 36->36 | Gold 266->266 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [4/6]: Remove a Strike to improve deck consistency and find our setup cards faster.

F31 [card_select] select_deck_card (option_index=0) | source=llm
  HP 36->36 | Gold 266->141 | Deck 27->26
  deck_change: lost Strike
  reasoning: We are a committed poison deck. Basic Strikes are our worst cards and only get in the way of drawing our poison stackers and block/cycle.
  strategic_note: Committed poison plan: discard Haze to trigger Sly and stack poison, then cycle deck and play block cards while poison ticks. Remove basic Strikes to improve consistency.

F31 [shop] buy_card (option_index=5) | source=plan
  HP 36->36 | Gold 141->59 | Deck 26->27
  deck_change: bought Dark Shackles
  reasoning: Shop plan [5/6]: Excellent 0-cost mitigation for boss multi-attacks.

F31 [shop] buy_potion (option_index=2) | source=plan
  HP 36->36 | Gold 59->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [6/6]: Additional safety for the upcoming Act 2 boss.

F31 [shop] close_shop_inventory | source=plan
  HP 36->36 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F31 [shop] proceed | source=auto
  HP 36->36 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 36->63 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: With only 36 HP before the Act 2 Boss, healing is mandatory to survive. We have Miniature Tent, so we will heal first and use the extra action to Smith.
  strategic_note: Committed poison plan: mitigate damage with Malaise and Shackles while scaling poison with Bubble Bubble and Accelerant. Needs more block and consistency.

F32 [rest_site] choose_rest_option (option_index=0, smith_card_index=17, note_scope=run, note_triggers=all) | source=llm
  HP 63->63 | Gold 9->9 | Deck 27->27
  deck_change: upgraded Accelerant->Accelerant+
  reasoning: Upgrading Accelerant provides an incredible multiplier to our poison damage, making poison trigger 3 times per turn instead of 2. This gives us the necessary scaling damage to quickly defeat the Act 2 boss while we mitigate with Malaise and Weak.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks.

F32 [rest_site] proceed | source=auto
  HP 63->63 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 63->63 | Gold 9->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 9->109 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 109->109 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 109->109 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 32->32 | Gold 109->109 | Deck 27->27
  deck_change: no deck change
  reasoning: Our deck is heavily committed to a direct poison strategy using Haze, Snakebite, Bubble Bubble, and Accelerant+. Envenom is too slow for 2 energy and requires many attack hits to be worthwhile, which we don't naturally support outside of Exterminate. Skipping keeps our deck lean and our cycle consistent to find our key poison and defense pieces.
  strategic_note: Committed poison plan: cycle rapidly to stack poison with Haze/Bubble Bubble/Snakebite, then burst it with Accelerant+. Defend heavily with efficient block and damage reduction (Malaise/Wail) while passive damage kills. Avoid slow powers and off-plan attacks.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 32->91 | Gold 109->109 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 91->91 | Gold 109->1108 | Deck 27->27
  deck_change: no deck change
  reasoning: Signet Ring provides an immediate 999 gold with no downside. Blessed Antler's Dazed would heavily disrupt Turn 1, especially since we already have 2 Dazed from Tea of Discourtesy next combat, and Dazed cards break our Unceasing Top relic. With 999 gold, we can buy out future shops for relics, removals, and powerful cards.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Use the massive gold pool at shops to buy crucial relics and card removals.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 91->91 | Gold 1108->1108 | Deck 27->27
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 91->91 | Gold 1108->0 | Deck 27->27
  deck_change: no deck change
  reasoning: I have 1108 gold and Winged Boots. The recommended route at c4 leads directly into a shop-rich path where I can convert this massive gold pile into permanent power (removals and relics). Starting with a hallway fight is ideal to find more defensive foundation pieces or AoE before the elite at c4,r6.
  strategic_note: Foundation poison and Malaise plan: mitigate heavy hitters while stacking poison. With over 1100 gold, the priority is hitting shops to remove strikes and buy high-impact relics while using early hallways to find missing AoE or defense.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 91->91 | Gold 1108->1120 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 91->91 | Gold 1120->1120 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Fruit Juice

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 91->91 | Gold 1120->1120 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 91->91 | Gold 1120->1120 | Deck 27->28
  deck_change: picked Well-Laid Plans
  reasoning: Well-Laid Plans is a premium utility power that allows us to retain combo pieces. Specifically, it lets us hold Haze until we draw a discard effect, or hold critical damage mitigation like Piercing Wail/Dark Shackles for the exact turn the enemy uses a multi-attack.
  strategic_note: Committed poison plan: discard Haze to trigger Sly and stack poison, then cycle deck and play block cards while poison ticks. Use Well-Laid Plans to hold combo pieces and defensive cards. Remove basic Strikes to improve consistency.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 91->91 | Gold 1120->1120 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Shop

F36 [shop] remove_card_at_shop | source=plan
  HP 91->91 | Gold 1120->1120 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan [1/5]: Removing a basic Strike helps us draw our poison cards, cycle, and block more consistently.

F36 [card_select] select_deck_card (option_index=0) | source=llm
  HP 91->91 | Gold 1120->970 | Deck 28->27
  deck_change: lost Strike
  reasoning: Strikes are the weakest cards in the deck, especially since our core scaling engine relies on poison and we have better 1-cost cards to play.
  strategic_note: Committed poison plan: scale poison, survive with discard synergy and defensive tools. Remove remaining Strikes to draw setup faster.

F36 [shop] buy_relic (option_index=1) | source=plan
  HP 91->91 | Gold 970->796 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [2/5]: Excellent energy generation for longer boss fights, giving us extra reach every 3 turns.

F36 [shop] buy_relic (option_index=0) | source=plan
  HP 91->91 | Gold 796->604 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [3/5]: Generic value relic for extra early mitigation/damage, good use of our massive gold pile.

F36 [shop] buy_card (option_index=2) | source=plan
  HP 91->91 | Gold 604->553 | Deck 27->28
  deck_change: bought Dodge and Roll
  reasoning: Shop plan [4/5]: Highly efficient multi-turn block card that scales nicely with our Oddly Smooth Stone.

F36 [shop] buy_potion (option_index=2) | source=plan
  HP 91->91 | Gold 553->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan [5/5]: Provides crucial Weak and Vulnerable utility for Act 3 elites and bosses.

F36 [shop] close_shop_inventory | source=plan
  HP 91->91 | Gold 481->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F36 [shop] proceed | source=auto
  HP 91->91 | Gold 481->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F36 [map] choose_map_node (option_index=0) | source=auto
  HP 91->91 | Gold 481->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Unknown

F37 [event] proceed | source=auto
  HP 91->91 | Gold 481->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Event finished, proceed

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 91->91 | Gold 481->481 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Shop

F38 [shop] buy_card (option_index=4) | source=plan
  HP 91->91 | Gold 481->443 | Deck 28->29
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/4]: Crucial passive poison scaling for boss fights.

F38 [shop] buy_card (option_index=3) | source=plan
  HP 91->91 | Gold 443->364 | Deck 29->30
  deck_change: bought Bubble Bubble
  reasoning: Shop plan [2/4]: Second copy of our best poison multiplier to burst down enemies.

F38 [shop] buy_card (option_index=2) | source=plan
  HP 91->91 | Gold 364->289 | Deck 30->31
  deck_change: bought Mirage
  reasoning: Shop plan [3/4]: Synergizes perfectly with our high poison output to provide massive burst block.

F38 [shop] remove_card_at_shop | source=plan
  HP 91->91 | Gold 289->289 | Deck 31->31
  deck_change: no deck change
  reasoning: Shop plan [4/4]: Remove a Strike to improve consistency in finding our poison engine and block.

F38 [card_select] select_deck_card (option_index=0) | source=llm
  HP 91->91 | Gold 289->114 | Deck 31->30
  deck_change: lost Strike
  reasoning: We are a committed Poison deck with one remaining basic Strike. Removing it improves consistency for drawing our Poison enablers, Accelerant, and defensive cards.
  strategic_note: Committed poison plan: stack poison with Bubble Bubble and Haze, trigger with Accelerant. Retain Snakebite until the right target. Needs more draw to find pieces quickly; skip attacks and keep thinning basic cards.

F38 [shop] close_shop_inventory | source=llm
  HP 91->91 | Gold 114->114 | Deck 30->30
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F38 [shop] proceed | source=auto
  HP 91->91 | Gold 114->114 | Deck 30->30
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 91->91 | Gold 114->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Monster

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 96->96 | Gold 114->124 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 96->96 | Gold 124->124 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 96->96 | Gold 124->124 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 96->96 | Gold 124->124 | Deck 30->31
  deck_change: picked Deadly Poison+
  reasoning: Deadly Poison+ provides highly efficient, 1-cost poison application (7 poison). This is an excellent, cheap enabler to guarantee our two Bubble Bubbles always trigger their massive 9-poison effect, accelerating our win condition without clogging our energy.
  strategic_note: Committed poison plan: survive with efficient block and damage mitigation while scaling poison via Noxious Fumes, Haze, and Bubble Bubble; use Accelerant+ to finish. Retain cycle/draw pieces and prioritize card removal and upgraded defensive tools over filler.

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 96->96 | Gold 124->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Elite

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 124->169 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 45 Gold

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 169->169 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim potion: Attack Potion

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 169->169 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim relic: Parrying Shield

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 169->169 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F40 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 83->83 | Gold 169->169 | Deck 31->32
  deck_change: picked Backflip
  reasoning: Backflip provides draw and mitigation, which perfectly supports our poison engine by cycling us to key cards like Accelerant and Bubble Bubble while blocking.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep the deck cycling with cards like Backflip.

F40 [map] choose_map_node (option_index=0) | source=llm
  HP 83->83 | Gold 169->169 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure node at c3,r7. This path sets up a sequence through an elite and multiple rest sites, which allows for scaling my poison engine through upgrades and relic acquisition while maintaining high HP.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks.

F41 [treasure] open_chest | source=random
  HP 83->83 | Gold 169->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 83->83 | Gold 215->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim: Horn Cleat

F41 [treasure] proceed | source=random
  HP 83->83 | Gold 215->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=auto
  HP 83->83 | Gold 215->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Unknown

F42 [event] choose_event_option (option_index=1) | source=llm
  HP 83->80 | Gold 215->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Bubble Bubble is a key poison scaling card for our deck. 3 HP is a trivial cost to reroll the card targeted for removal.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep our deck thin by removing attacks we don't need.

F42 [event] choose_event_option (option_index=1) | source=llm
  HP 80->76 | Gold 215->215 | Deck 32->32
  deck_change: no deck change
  reasoning: Backflip is a good card for draw and block. We'd rather pay 4 HP to try and hit a worse card like Exterminate or Dagger Throw for removal.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.

F42 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 76->76 | Gold 215->215 | Deck 32->31
  deck_change: lost Poisoned Stab
  reasoning: Removing Poisoned Stab for free is excellent. We have far better poison scaling cards (Bubble Bubble, Accelerant, Deadly Poison+) and removing a weak attack helps thin the deck and improve consistency.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.

F42 [event] choose_event_option (option_index=0) | source=auto
  HP 76->76 | Gold 215->215 | Deck 31->31
  deck_change: no deck change
  reasoning: Only option: Proceed

F42 [map] choose_map_node (option_index=0) | source=llm
  HP 76->76 | Gold 215->0 | Deck 31->31
  deck_change: no deck change
  reasoning: With 76/96 HP and Winged Boots available, I am pivoting to the Elite. The deck is committed to a poison scaling plan (Accelerant, Bubble Bubble) and has solid damage mitigation (Malaise, Piercing Wail). I need more relic momentum to ensure I can out-scale the Act 3 boss, and 79% HP is a very safe threshold to hunt an Elite.
  strategic_note: Committed poison plan: mitigate damage with Malaise and Weak while scaling rapid damage with Accelerant and Bubble Bubble; pivoting to Elites now to secure relic power for the final boss.

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 215->260 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 45 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 260->260 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 260->260 | Deck 31->31
  deck_change: upgraded Dagger Throw->Dagger Throw+, Suppress->Suppress+
  reasoning: Claim relic: Whetstone

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 260->260 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 49->49 | Gold 260->260 | Deck 31->32
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is premium mitigation for Act 3 multi-hit enemies and bosses. We already have strong poison scaling, so surviving heavy attack turns is our main priority. A pre-upgraded copy for -8 Strength is an easy inclusion.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Keep prioritizing block scaling and deck cycle.

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 260->260 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: RestSite

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=17) | source=llm
  HP 49->49 | Gold 260->260 | Deck 32->32
  deck_change: upgraded Mirage->Mirage+
  reasoning: Mirage is a critical block scaling card for this deck. Upgrading it to 0 energy ensures we can always play it to block incoming damage, even on turns where we spend our energy applying poison or setting up powers.
  strategic_note: Committed poison plan: stack poison with Fumes and Bubble Bubble, mitigate with Malaise/Shackles, and block heavily with Mirage while Accelerant triggers rapid damage. Prioritize retaining Mirage or key mitigation for dangerous turns.

F44 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 49->77 | Gold 260->260 | Deck 32->32
  deck_change: no deck change
  reasoning: With Miniature Tent, we can perform multiple rest actions. Healing first is a safe use of our first action since we are at 49/96 HP, and we expect to be prompted again to Smith key cards like Noxious Fumes or Well-Laid Plans.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.

F44 [rest_site] proceed | source=auto
  HP 77->77 | Gold 260->260 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 77->77 | Gold 260->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Monster

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 77->77 | Gold 260->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: The deck is already at 32 cards and possesses sufficient poison application, block, and a copy of Well-Laid Plans. We do not need a second WLP or additional expensive poison/Sly block, so skipping is optimal to avoid further diluting our card pool.
  strategic_note: Committed poison plan: stack poison with Bubble Bubble and Haze, trigger with Accelerant. Retain Snakebite until the right target. Avoid bloating the deck further.

F45 [map] choose_map_node (option_index=1) | source=llm
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: With 77 HP and a solid poison core, I am well-positioned for the final stretch. Choosing the Unknown node (index 1) follows the Route Intelligence and provides a chance for a high-value event or a shop (given my 274 gold) before the final rest site and boss. This avoids unnecessary chip damage from a guaranteed hallway fight.
  strategic_note: Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.

F46 [event] choose_event_option (option_index=0) | source=llm
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Explosive Ampoule is a very weak potion for the upcoming boss fights, as 10 damage is negligible at this stage. Trading it for a random relic provides far more value. Keeping gold is useful in case there is an Act 4 shop.
  strategic_note: Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.

F46 [event] choose_event_option (option_index=0) | source=auto
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=13) | source=llm
  HP 77->77 | Gold 274->274 | Deck 32->32
  deck_change: upgraded Well-Laid Plans->Well-Laid Plans+
  reasoning: With Miniature Tent we can likely take multiple actions. Even if we can't, Well-Laid Plans+ is extremely powerful for a control-oriented poison deck facing the Act 3 boss, as retaining two cards lets us hold both crucial mitigation (like Shackles/Malaise) and scaling simultaneously. 77/96 HP is quite healthy given Beating Remnant caps damage at 20 per turn.
  strategic_note: Committed poison plan: mitigate damage with Malaise, Weak, and Shackles while scaling rapid damage with Accelerant and Bubble Bubble. Needs consistent block to survive while poison ticks. Keep deck thin by removing attacks we don't need.

F47 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 77->96 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: With the Act 3 Boss next, healing 19 HP to reach full health provides the largest survival buffer for the fight.
  strategic_note: Committed poison plan: mitigate damage with Malaise and Weak while scaling poison via Accelerant and Bubble Bubble. High priority on consistent block and thinning redundant attacks to ensure we draw our mitigation and scaling pieces every cycle.

F47 [rest_site] proceed | source=auto
  HP 96->96 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 96->96 | Gold 274->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 49->49 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 49->0 | Gold 274->274 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (7 replays)
[Selected: elite] Terror Eel (F8, elite)
## Combat Replay: vs Terror Eel (Floor 8, elite)
Relics: Ring of the Snake, Winged Boots
Deck (17): Defend x5, Strike x5, Acrobatics, Backflip, Cloak and Dagger, Haze, Neutralize, Predator, Survivor
Enemies: Terror Eel HP=140/140

### Round 1
Agent plan (hypothesis): Next turn I will draw 5 of the 6 remaining cards. Look to land Predator or establish Haze scaling.
Intent: Terror Eel: Attack(16)
  Regen Potion
    +Regen(5)
  Neutralize -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -5, +Weak(1)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Terror Eel[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Terror Eel: hp -4
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Agent plan (hypothesis): If Predator is drawn, it might be worth taking 4 damage (healed by Regen) to play it and draw next turn.
Intent: Terror Eel: Attack(3x3=9), Buff
  Backflip
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  turn_end

### Round 3
Agent plan (hypothesis): Next turn we draw 7 cards including Neutralize and Survivor.
Intent: Terror Eel: Attack(22)
  Predator -> Terror Eel[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Terror Eel: hp -15
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Agent plan (hypothesis): Need 1 more block to fully mitigate damage. Maximize damage with remaining 2 energy.
Agent plan (hypothesis): Continue focusing on pushing Eel below 70 HP to trigger Shriek stun.
Intent: Terror Eel: Attack(3x3=9), Buff
  Neutralize -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -5, +Weak(1)
  Backflip
    energy -1 | block +5
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  turn_end

### Round 5
Agent plan (hypothesis): We need 19 damage next turn to stun the Eel. Hopefully we draw Predator + an attack.
Intent: Terror Eel: Attack(22)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -4
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 6
Intent: Terror Eel: Attack(3x3=9), Buff
  Neutralize -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -5, +Weak(1)
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 7
Intent: Terror Eel: Attack(22)
  Predator -> Terror Eel[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Terror Eel: hp -15, -Shriek
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  turn_end

### Round 8
Intent: Terror Eel: Debuff
  Backflip
    energy -1 | block +5
  Predator -> Terror Eel[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Terror Eel: hp -15
  turn_end

### Round 9
Agent plan (hypothesis): Depending on draws, maximize block with final energy.
Agent plan (hypothesis): We will take 13 damage this turn, leaving us at 33 HP. Eel will be at 33 HP. Next turn we draw 4 cards including Neutralize and Survivor.
Intent: Terror Eel: Attack(33)
  Neutralize -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -5, +Weak(1)
  Acrobatics
    energy -1
  Haze
  Backflip
    energy -1 | block +5
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -4
  turn_end

### Round 10
Intent: Terror Eel: Attack(4x3=12), Buff
  Neutralize -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -5, +Weak(1)
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  turn_end

### Round 11
Agent plan (hypothesis): Whew, that was close.
Intent: Terror Eel: Attack(33)
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  Strike -> Terror Eel[0]
    energy -1 | -Vulnerable | enemy_deltas: Terror Eel: DIED
## Combat Analytics: Terror Eel (WIN - 11 rounds)

Cards played (with descriptions):
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 5 plays, 25 dmg
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 3 plays, 18 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Defend "Gain 5 Block." -> 8 plays, 40 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 4 plays, 20 block
  Strike "Deal 6 damage." -> 9 plays, 48 dmg
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 3 plays, 45 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays

Token attribution (Shivs):
  Cloak and Dagger: 3 Shivs -> ~12 dmg

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:3 -> R11:2
  Shriek: R1:70 -> R2:70 -> R3:70 -> R4:70 -> R5:70 -> R6:70 -> R7:70 -> R8:- -> R9:- -> R10:- -> R11:-
  Vigor: R1:- -> R2:- -> R3:6 -> R4:- -> R5:6 -> R6:- -> R7:6 -> R8:6 -> R9:6 -> R10:- -> R11:6

[Selected: boss] Lagavulin Matriarch (F17, boss)
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy
Deck (20): Defend x4, Strike x4, Acrobatics, Backflip+, Bubble Bubble, Cloak and Dagger, Defend+, Haze, Malaise, Neutralize, Predator+, Snakebite, Spoils Map, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Agent plan (hypothesis): Boss is permanently weakened. Start applying poison and building block.
Intent: Lagavulin Matriarch: Sleep
  Dexterity Potion
    +Dexterity(2)
  Malaise -> Lagavulin Matriarch[0]
    energy -3 | exhausted: Malaise [X]: Enemy loses X Strength. Apply X Weak. Exhaust. | enemy_deltas: Lagavulin Matriarch: +Strength(-3), +Weak(3)
  turn_end

### Round 2
Agent plan (hypothesis): Boss will wake up. Keep blocking and cycling for more poison.
Intent: Lagavulin Matriarch: Sleep
  Snakebite -> Lagavulin Matriarch[0]
    energy -2 | enemy_deltas: Lagavulin Matriarch: +Poison(7)
  Bubble Bubble -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: Poison(7→16)
  turn_end

### Round 3
Agent plan (hypothesis): Traded 12 HP for 20 dmg + 2 draw next turn. Keep using HP as a resource.
Agent plan (hypothesis): Predator+ used; drawing 7 cards next turn.
Intent: Lagavulin Matriarch: Attack(12)
  Acrobatics
    energy -1
  Haze
  Neutralize -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -5, Weak(1→2)
  Predator+ -> Lagavulin Matriarch[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Lagavulin Matriarch: hp -20
  turn_end

### Round 4
Intent: Lagavulin Matriarch: Attack(4x2=8)
  Neutralize -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -5, Weak(1→2)
  Acrobatics
    energy -1
  Haze
  Bubble Bubble -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: Poison(22→31)
  Defend
    energy -1 | block +7
  turn_end

### Round 5
Intent: Lagavulin Matriarch: Attack(6), Defend
  Backflip+
    energy -1 | block +10
  Snakebite -> Lagavulin Matriarch[0]
    energy -2 | enemy_deltas: Lagavulin Matriarch: Poison(30→37)
  turn_end

### Round 6
Agent plan (hypothesis): Boss is dead in 2 turns to poison. Prioritize block next turn if it attacks.
Intent: Lagavulin Matriarch: Debuff, Buff
  Bubble Bubble -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: Poison(36→45)
  Predator+ -> Lagavulin Matriarch[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Lagavulin Matriarch: hp -8, block -12
  turn_end

### Round 7
Intent: Lagavulin Matriarch: Attack(18)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
## Combat Analytics: Lagavulin Matriarch (WIN - 7 rounds)

Cards played (with descriptions):
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, +14 poison
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 3 plays, +27 poison
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 2 plays, 10 dmg
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 28 dmg
  Defend "Gain 7 Block." -> 4 plays, 22 block
  Backflip+ "Gain 10 Block. Draw 2 cards." -> 1 plays, 10 block

Poison stacks applied per card:
  Bubble Bubble: 27 stacks
  Snakebite: 14 stacks

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Plating: R1:12 -> R2:11 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Poison: R1:- -> R2:- -> R3:15 -> R4:18 -> R5:30 -> R6:36 -> R7:44
  Strength: R1:- -> R2:-3 -> R3:-3 -> R4:-3 -> R5:-3 -> R6:-3 -> R7:-1
  Weak: R1:- -> R2:2 -> R3:1 -> R4:1 -> R5:1 -> R6:- -> R7:-

[Selected: elite] Infested Prism (F30, elite)
## Combat Replay: vs Infested Prism (Floor 30, elite)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry
Deck (26): Defend x4, Strike x3, Acrobatics+, Adrenaline+, Backflip+, Bubble Bubble, Calculated Gamble, Cloak and Dagger, Dagger Throw, Dagger Throw+, Defend+, Exterminate, Haze, Haze+, Malaise+, Piercing Wail, Poisoned Stab, Predator+, Snakebite, Suppress, Survivor
Enemies: Infested Prism HP=200/200

### Round 1
Intent: Infested Prism: Attack(22)
  Poison Potion -> Infested Prism[0]
    enemy_deltas: Infested Prism: +Poison(6)
  Attack Potion
  Dash
  Suppress -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -13, +Weak(3)
  Dash -> Infested Prism[0]
    block +10 | enemy_deltas: Infested Prism: hp -10
  Snakebite -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: Poison(6→13)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Agent plan (hypothesis): The Prism's Strength is permanently reduced, making the multi-attack turn far less threatening. Continue to use passive poison while blocking.
Intent: Infested Prism: Attack(12), Defend
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Infested Prism[0]
    energy +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: hp -4
  Defend+
    energy -1 | block +8
  Malaise+ -> Infested Prism[0]
    energy -2 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: Weak(2→5), +Strength(-3)
  turn_end

### Round 3
Agent plan (hypothesis): Poison is ticking nicely, block heavily.
Agent plan (hypothesis): Poison scaling is well underway, keep defending.
Intent: Infested Prism: Attack(4x3=12)
  Adrenaline+
    energy +2 | exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Dagger Throw -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: block -9
  Haze
  Acrobatics+
    energy -1
  Strike
  Dagger Throw+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -5, block -7
  Strike
  Bubble Bubble -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: Poison(15→24)
  Backflip+
    energy -1 | block +8
  Poisoned Stab -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6, Poison(24→27)
  turn_end

### Round 4
Agent plan (hypothesis): If we draw cycle or more setup, play that. Otherwise, maximize damage.
Intent: Infested Prism: Buff, Defend
  Dagger Throw+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -12
  Haze+
  Dash -> Infested Prism[0]
    energy -2 | block +10 | enemy_deltas: Infested Prism: hp -10
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  turn_end

### Round 5
Agent plan (hypothesis): Calculate lethal: we need (Enemy HP - Damage Dealt) <= Total Poison. We have 3 Energy remaining.
Intent: Infested Prism: Attack(17)
  Suppress -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -13, Weak(2→5)
  Dagger Throw -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -2, block -7
  Haze
  Snakebite -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: Poison(35→42)
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  turn_end
## Combat Analytics: Infested Prism (WIN - 5 rounds)

Cards played (with descriptions):
  Suppress "Innate. Deal 13 damage. Apply 3 Weak." -> 2 plays, 13 dmg
  Dash "Gain 10 Block. Deal 10 damage." -> 2 plays, 20 dmg, 20 block
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, +14 poison
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 1 plays, 6 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 4 dmg, EXHAUST
  Defend+ "Gain 8 Block." -> 1 plays, 8 block
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 2 dmg
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Dagger Throw+ "Deal 12 damage. Draw 1 card. Discard 1 card." -> 2 plays, 17 dmg
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 1 plays, +9 poison
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 1 plays, 8 block
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Strike "Deal 6 damage." -> 2 plays, 12 dmg

Token attribution (Shivs):
  Cloak and Dagger: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Snakebite: 14 stacks
  Bubble Bubble: 9 stacks
  Poison Potion: 6 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:12 -> R3:11 -> R4:26 -> R5:31
  Strength: R1:- -> R2:- -> R3:-3 -> R4:-3 -> R5:1
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1
  Weak: R1:- -> R2:2 -> R3:4 -> R4:3 -> R5:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs Infested Prism (Floor 28, elite)
Relics: Ring of the Drake, Precarious Shears, Festive Popper, Pen Nib, Pocketwatch, Touch of Orobas, War Paint
Deck (24): Defend x4, Accuracy+, Backflip, Blade Dance+, Blade of Ink+, Cloak and Dagger+, Conflagration, Dodge and Roll+, Footwork+, Hidden Daggers, Infinite Blades, Knife Trap, Leading Strike, Neutralize, Piercing Wail+, Pinpoint, Predator, Rage+, Scrawl, Strike, Survivor
Enemies: Infested Prism HP=191/200

### Round 1
Intent: Infested Prism: Attack(22)
  Footwork+
    energy -1 | +Dexterity(3)
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Infested Prism[0]
    energy +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: hp -4
  Survivor
    energy -1 | block +11
  Conflagration
  Defend
    energy -1 | block +8
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4
  turn_end

### Round 2
Intent: Infested Prism: Attack(16), Defend
  Blade Dance+
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4
  Backflip
    energy -1 | block +8
  Dodge and Roll+
    energy -1 | block +9 | +Block Next Turn(9)
  Pinpoint -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -15
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  Hidden Daggers
  Piercing Wail+
  Knife Trap
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -8
  turn_end

### Round 3
Intent: Infested Prism: Attack(9x3=27)
  Rage+
    +Rage(5)
  Accuracy+
    energy -1 | +Accuracy(6)
  Leading Strike -> Infested Prism[0]
    energy -1 | block +5 | enemy_deltas: Infested Prism: block -3
  Shiv -> Infested Prism[0]
    block +5 | enemy_deltas: Infested Prism: block -10
  Shiv -> Infested Prism[0]
    energy +1 | block +5 | enemy_deltas: Infested Prism: hp -7, block -3
  Blade of Ink+
    energy -1
  Shiv -> Infested Prism[0]
    block +5 | exhausted: Shiv*10 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: hp -12, +Weak(1)
  Shiv -> Infested Prism[0]
    block +5 | enemy_deltas: Infested Prism: hp -12, Weak(1→2)
  Shiv -> Infested Prism[0]
    block +5 | enemy_deltas: Infested Prism: hp -12, Weak(2→3)
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  turn_end

### Round 4
Intent: Infested Prism: Buff, Defend
  Blade of Ink+
    energy -1
  Neutralize -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -3, Weak(2→3)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -10
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -12, Weak(3→4)
  Predator -> Infested Prism[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Infested Prism: hp -30
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -12, Weak(4→5)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -12, Weak(5→6)
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -10
  Shiv -> Infested Prism[0]
    block -9 | -Dexterity | -Accuracy | -Infinite Blades | -Draw Cards Next Turn | enemy_deltas: Infested Prism: DIED
## Combat Analytics: Infested Prism (WIN - 4 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Cloak and Dagger+ "Gain 9 Block. Add 2 Shivs into your Hand." -> 2 plays, 18 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 19 plays, 135 dmg, 25 block, EXHAUST
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Defend "Gain 8 Block." -> 1 plays, 8 block
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Backflip "Gain 8 Block. Draw 2 cards." -> 1 plays, 8 block
  Dodge and Roll+ "Gain 9 Block. Next turn, gain 9 Block." -> 1 plays, 9 block
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 1 plays, 15 dmg
  Strike "Deal 6 damage." -> 1 plays, 6 dmg
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 1 plays, generates 2 Shivs
  Rage+ "Whenever you play an Attack this turn, gain 5 Block." -> 1 plays
  Accuracy+ "Shivs deal 6 additional damage." -> 1 plays
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 5 block, generates 2 Shivs
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 2 plays
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Predator "Deal 30 damage. Next turn, draw 2 cards." -> 1 plays, 30 dmg

Token attribution (Shivs):
  other: 6 Shivs -> ~43 dmg
  Cloak and Dagger+: 4 Shivs -> ~28 dmg
  Blade Dance+: 4 Shivs -> ~28 dmg
  Hidden Daggers: 2 Shivs -> ~14 dmg
  Leading Strike: 2 Shivs -> ~14 dmg
  Infinite Blades: 1 Shivs -> ~7 dmg

Enemy power timeline:
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1
  Weak: R1:- -> R2:- -> R3:- -> R4:2

[Selected: boss] multi:Crusher+Rocket (F33, boss)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry, Unceasing Top, Oddly Smooth Stone, Miniature Tent
Deck (27): Defend x4, Strike x2, Accelerant+, Acrobatics+, Adrenaline+, Backflip+, Bubble Bubble, Calculated Gamble, Cloak and Dagger, Dagger Throw, Dagger Throw+, Dark Shackles, Defend+, Exterminate, Haze, Haze+, Malaise+, Piercing Wail, Poisoned Stab, Predator+, Snakebite, Suppress, Survivor
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Agent plan (hypothesis): Snakebite will retain. Prepare to start stacking poison next turn with the extra draw.
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Dexterity Potion
    Dexterity(1→3)
  Suppress -> Crusher[0]
    enemy_deltas: Crusher: hp -13, +Weak(3)
  Dark Shackles -> Crusher[0]
    exhausted: Dark Shackles [0]: Enemy loses 9 Strength this turn. Exhaust. | enemy_deltas: Crusher: +Strength(-9), +Dark Shackles(9)
  Predator+ -> Crusher[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Crusher: hp -20
  Defend
    energy -1 | block +8
  turn_end

### Round 2
Agent plan (hypothesis): Remember to target Rocket with a card to turn around and mitigate the 50% back-attack damage multiplier.
Agent plan (hypothesis): Need 1 more Block. Use remaining energy efficiently depending on draws.
Agent plan (hypothesis): Depending on the draw, either block the remaining 1 damage or set up further scaling.
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Adrenaline+
    energy +2 | exhausted: Dark Shackles [0]: Enemy loses 9 Strength this turn. Exhaust.
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Crusher: +Strength(-6), +Piercing Wail(6); Rocket: +Strength(-6), +Piercing Wail(6)
  Dagger Throw+ -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -12
  Exterminate
  Backflip+
    energy -1 | block +11
  Dagger Throw -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -9
  Haze
  Defend
    energy -1 | block +8
  turn_end

### Round 3
Agent plan (hypothesis): Poison scaling is active. Focus on surviving while poison ticks down the enemies.
Intent: Crusher: Attack(6x2=12), Debuff, Rocket: Buff
  Strength Potion
    +Strength(2)
  Accelerant+
    energy -1 | +Accelerant(2)
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Crusher[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: hp -6
  Bubble Bubble -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: Poison(3→12)
  turn_end

### Round 4
Agent plan (hypothesis): Play Calculated Gamble, then Suppress on Rocket to turn around and apply Weak, then block with remaining energy.
Intent: Crusher: Buff, Rocket: Attack(49)
  Acrobatics+
    energy -1
  Predator+
  Backflip+
    energy -1 | block +8
  Malaise+ -> Rocket[1]
    energy -1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Rocket: +Weak(2), -Strength
  turn_end

### Round 5
Agent plan (hypothesis): Crusher is weakened and we are facing him. Next turn we can push poison on Crusher or Rocket depending on intents.
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Suppress -> Crusher[0]
    enemy_deltas: Crusher: hp -11, +Weak(3)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -4
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end

### Round 6
Agent plan (hypothesis): Crusher is dying to poison; focus on controlling Rocket next.
Agent plan (hypothesis): Crusher will die to poison soon. Focus on mitigating Rocket.
Intent: Crusher: Attack(10), Rocket: Attack(4)
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: block -11
  Haze+
  Bubble Bubble -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: Poison(9→18)
  Defend
    energy -1 | block +8
  turn_end

### Round 7
Agent plan (hypothesis): Rocket will have 99 Block. Focus entirely on defense and applying more poison/weak while poison kills him.
Intent: Crusher: Attack(4), Rocket: Attack(27)
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -6
  Bubble Bubble -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: Poison(3→12)
  Backflip+
    energy -1 | block +11
  Calculated Gamble
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: Poison(15→19); Rocket: Poison(12→16)
  Suppress -> Rocket[1]
    enemy_deltas: Rocket: hp -15, +Weak(3)
  turn_end

### Round 8
Agent plan (hypothesis): Rocket takes 39 poison damage next turn. We will have 7 cards drawn next turn to deal with whatever Rocket does.
Intent: Rocket: Buff
  Predator+ -> Rocket[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Rocket: block -22
  Exterminate
    energy -1 | enemy_deltas: Rocket: block -20
  turn_end

### Round 9
Agent plan (hypothesis): Combat won by poison.
Intent: Rocket: Attack(29)
  Dagger Throw -> Rocket[0]
    energy -1 | enemy_deltas: Rocket: hp -11
  Haze
  Defend+
    energy -1 | block +11
  Defend
    energy -1 | block +8
  turn_end

### Round 10
Agent plan (hypothesis): Act 2 Boss defeated.
Intent: Rocket: Sleep
  Strike -> Rocket[0]
    energy -1 | -Dexterity | -Surrounded | -Strength | -Accelerant | enemy_deltas: Rocket: DIED
## Combat Analytics: multi:Crusher+Rocket (WIN - 10 rounds)

Cards played (with descriptions):
  Suppress "Innate. Deal 13 damage. Apply 3 Weak." -> 3 plays, 39 dmg
  Dark Shackles "Enemy loses 9 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 20 dmg
  Defend "Gain 8 Block." -> 6 plays, 44 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw+ "Deal 12 damage. Draw 1 card. Discard 1 card." -> 1 plays, 12 dmg
  Backflip+ "Gain 11 Block. Draw 2 cards." -> 3 plays, 30 block
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 20 dmg
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Cloak and Dagger "Gain 9 Block. Add 1 Shiv into your Hand." -> 3 plays, 24 block, generates 1 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 3 plays, 16 dmg, EXHAUST
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 3 plays, +27 poison
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, +8 poison, EXHAUST
  Exterminate "Deal 5 damage 4 times to ALL enemies." -> 1 plays
  Defend+ "Gain 11 Block." -> 1 plays, 11 block
  Strike "Deal 8 damage." -> 1 plays

Active powers: Dexterity(1), Surrounded(1)

Token attribution (Shivs):
  Cloak and Dagger: 3 Shivs -> ~16 dmg

Poison stacks applied per card:
  Bubble Bubble: 27 stacks
  Calculated Gamble: 8 stacks

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:1 -> R10:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Poison: R1:- -> R2:- -> R3:- -> R4:9 -> R5:6 -> R6:3 -> R7:- -> R8:13 -> R9:10 -> R10:11
  Poison[0]: R1:- -> R2:- -> R3:3 -> R4:- -> R5:- -> R6:- -> R7:15 -> R8:- -> R9:- -> R10:-
  Poison[1]: R1:- -> R2:- -> R3:3 -> R4:- -> R5:- -> R6:- -> R7:3 -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:2 -> R8:6 -> R9:8 -> R10:8
  Weak: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:1 -> R6:2 -> R7:1 -> R8:2 -> R9:1 -> R10:-

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F40, elite)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 40, elite)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry, Unceasing Top, Oddly Smooth Stone, Miniature Tent, Signet Ring, Happy Flower, Petrified Toad
Deck (31): Defend x4, Bubble Bubble x2, Accelerant+, Acrobatics+, Adrenaline+, Backflip+, Calculated Gamble, Cloak and Dagger, Dagger Throw, Dagger Throw+, Dark Shackles, Deadly Poison+, Defend+, Dodge and Roll, Exterminate, Haze, Haze+, Malaise+, Mirage, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Snakebite, Suppress, Survivor, Well-Laid Plans
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Agent plan (hypothesis): Retain Calculated Gamble to dig for poison applicators (Snakebite, Bubble Bubble) next turn.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Dark Shackles -> Flail Knight[0]
    exhausted: Dark Shackles [0]: Enemy loses 9 Strength this turn. Exhaust. | enemy_deltas: Flail Knight: +Strength(-9), +Dark Shackles(9)
  Suppress -> Spectral Knight[1]
    enemy_deltas: Spectral Knight: hp -13, +Weak(3)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Accelerant+
    energy -1 | +Accelerant(2)
  Survivor
    energy -1 | block +9
  Exterminate
  turn_end
  Calculated Gamble

### Round 2
Agent plan (hypothesis): Spectral Knight is taking 21 poison damage a turn; try to Bubble Bubble it if drawn.
Agent plan (hypothesis): See what we draw. Likely Deadly Poison+ and Bubble Bubble onto Spectral Knight next.
Agent plan (hypothesis): See what we draw, then prioritize poisoning Spectral Knight with Deadly Poison+ and Bubble Bubble.
Intent: Flail Knight: Attack(15), Spectral Knight: Attack(11), Magi Knight: Debuff
  Potion of Binding
    enemy_deltas: Flail Knight: +Weak(1), +Vulnerable(1); Spectral Knight: Weak(2→3), +Vulnerable(1); Magi Knight: +Weak(1), +Vulnerable(1)
  Snakebite -> Spectral Knight[1]
    energy -2 | enemy_deltas: Spectral Knight: +Poison(7)
  Energy Potion
    energy +2
  Calculated Gamble
    exhausted: Dark Shackles [0]: Ethereal. Enemy loses 9 Strength this turn. Exhaust.
  Backflip+
    energy -1 | block +9
  Adrenaline+
    energy +2 | exhausted: Dark Shackles [0]: Ethereal. Enemy loses 9 Strength this turn. Exhaust.
  Deadly Poison+ -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: Poison(7→14)
  Bubble Bubble -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: Poison(14→23)
  Dagger Throw+ -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: hp -18
  Haze
  Dagger Throw -> Flail Knight[0]
    energy -1 | enemy_deltas: Flail Knight: hp -13
  Poisoned Stab
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  turn_end
    exhausted: Defend+ [1]: Ethereal. Gain 8 Block.

### Round 3
Agent plan (hypothesis): Play Noxious Fumes when there's an opening. Flail Knight is taking 30/turn and will die quickly.
Intent: Flail Knight: Attack(9x2=18), Magi Knight: Attack(10)
  Bubble Bubble -> Flail Knight[0]
    energy -1 | enemy_deltas: Flail Knight: Poison(1→10)
  Cloak and Dagger
    energy -1 | block +7
  Shiv -> Magi Knight[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Magi Knight: hp -4
  Defend
    energy -1 | block +6
  turn_end
  Noxious Fumes

### Round 4
Agent plan (hypothesis): Flail Knight is dead, focus everything on Magi Knight now.
Intent: Flail Knight: Attack(15), Magi Knight: Defend
  Acrobatics
    energy -1
  Haze
  Bubble Bubble -> Flail Knight[0]
    energy -1 | enemy_deltas: Flail Knight: Poison(11→20)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  turn_end
  Mirage

### Round 5
Agent plan (hypothesis): Magi Knight is the last one alive; let poison and accelerant finish it off while we focus purely on blocking its heavy hits.
Intent: Magi Knight: Attack(35)
  Suppress -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -8, block -5, +Weak(3)
  Cloak and Dagger
    energy -1 | block +7
  Shiv -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -4
  Mirage
    energy -1 | block +4 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Defend
    energy -1 | block +6
  Survivor
    energy -1 | block +9
  turn_end
  Predator

### Round 6
Intent: Magi Knight: Attack(7)
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  Defend
    energy -1 | block +6
  Dagger Throw -> Magi Knight[0]
    energy -1 | enemy_deltas: Magi Knight: hp -9
  Haze
  Malaise -> Magi Knight[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  turn_end
  Predator

### Round 7
Agent plan (hypothesis): Good job surviving the multi-enemy elite.
Intent: Magi Knight: Defend
  Predator -> Magi Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Magi Knight: hp -15
  Poisoned Stab -> Magi Knight[0]
    energy -1 | block -5 | -Dexterity | -Well-Laid Plans | -Accelerant | -Dampen | -Noxious Fumes | -Draw Cards Next Turn | enemy_deltas: Magi Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 7 rounds)

Cards played (with descriptions):
  Dark Shackles "Enemy loses 9 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Suppress "Innate. Deal 13 damage. Apply 3 Weak." -> 2 plays, 21 dmg
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Survivor "Gain 9 Block. Discard 1 card." -> 2 plays, 18 block
  Snakebite "Retain. Ethereal. Apply 7 Poison." -> 1 plays, +7 poison
  Calculated Gamble "Ethereal. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Backflip+ "Ethereal. Gain 9 Block. Draw 2 cards." -> 1 plays, 9 block
  Adrenaline+ "Ethereal. Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Deadly Poison+ "Ethereal. Apply 7 Poison." -> 1 plays, +7 poison
  Bubble Bubble "Ethereal. If the enemy has Poison, apply 9 Poison." -> 3 plays, +27 poison
  Dagger Throw+ "Ethereal. Deal 12 damage. Draw 1 card. Discard 1 card." -> 1 plays, 18 dmg
  Dagger Throw "Ethereal. Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 22 dmg
  Dodge and Roll "Ethereal. Gain 5 Block. Next turn, gain 5 Block." -> 2 plays, 10 block
  Cloak and Dagger "Gain 7 Block. Add 1 Shiv into your Hand." -> 2 plays, 14 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 8 dmg, EXHAUST
  Defend "Gain 6 Block." -> 3 plays, 18 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 4 Block) Exhaust." -> 1 plays, 4 block, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays

Active powers: Dexterity(1)

Token attribution (Shivs):
  Cloak and Dagger: 2 Shivs -> ~8 dmg

Poison stacks applied per card:
  Bubble Bubble: 27 stacks
  Snakebite: 7 stacks
  Deadly Poison+: 7 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:7 -> R5:3 -> R6:2 -> R7:5
  Poison[0]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Poison[1]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 42, elite)
Relics: Ring of the Drake, Precarious Shears, Festive Popper, Pen Nib, Touch of Orobas, War Paint, Strawberry, Distinguished Cape, Akabeko, Regal Pillow, Ripple Basin
Deck (35): Defend x4, Apparition x3, Footwork+ x2, Piercing Wail+ x2, Accuracy+, Backflip, Blade Dance, Blade Dance+, Blade of Ink+, Bullet Time, Calculated Gamble, Cloak and Dagger+, Conflagration, Dodge and Roll, Dodge and Roll+, Hidden Daggers, Infinite Blades, Knife Trap, Leading Strike, Leading Strike+, Neutralize+, Pinpoint, Predator, Rage+, Scrawl, Strangle+, Strike, Survivor
Enemies: Flail Knight HP=92/101, Spectral Knight HP=84/93, Magi Knight HP=73/82

### Round 1
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Footwork+
    energy -1 | +Dexterity(3)
  Apparition
    energy -1 | +Intangible(1) | exhausted: Apparition [1]: Ethereal. Gain 1 Intangible. Exhaust.
  Conflagration
    energy -1 | -Vigor | enemy_deltas: Flail Knight: hp -16; Spectral Knight: hp -16; Magi Knight: hp -16
  Hidden Daggers
  Defend
  Defend
  Shiv -> Flail Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Flail Knight: hp -4
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -4
  turn_end

### Round 2
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Debuff
  Accuracy+
    energy -1 | +Accuracy(6)
  Rage+
    +Rage(5)
  Blade of Ink+
    energy -1
  Shiv -> Spectral Knight[1]
    block +5 | exhausted: Shiv*2 [0]: Ethereal. Deal 4 damage. Exhaust. | enemy_deltas: Spectral Knight: hp -12, +Weak(1)
  Shiv -> Spectral Knight[1]
    block +5 | enemy_deltas: Spectral Knight: hp -12, Weak(1→2)
  Shiv -> Spectral Knight[1]
    block +5 | enemy_deltas: Spectral Knight: hp -12, Weak(2→3)
  Blade Dance
    energy -1 | exhausted: Shiv*3 [0]: Ethereal. Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Spectral Knight[1]
    block +5 | enemy_deltas: Spectral Knight: hp -10
  Pinpoint -> Spectral Knight[1]
    block +5 | -Hex | enemy_deltas: Spectral Knight: DIED
  Shiv -> Magi Knight[1]
    block +5 | enemy_deltas: Magi Knight: hp -5, block -5
  Shiv -> Magi Knight[1]
    block +5 | enemy_deltas: Magi Knight: hp -10
  turn_end

### Round 3
Intent: Flail Knight: Attack(18), Magi Knight: Attack(10)
  Bullet Time
    energy -3 | +No Draw(1)
  Strangle -> Magi Knight[1]
    enemy_deltas: Magi Knight: hp -8, +Strangle(2)
  Neutralize -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -3, +Weak(1); Magi Knight: hp -2
  Infinite Blades
    +Infinite Blades(1) | enemy_deltas: Magi Knight: hp -2
  Footwork
    Dexterity(3→5) | enemy_deltas: Magi Knight: hp -2
  Piercing Wail
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Flail Knight: Strength(3→-3), +Piercing Wail(6); Magi Knight: hp -2, +Strength(-6), +Piercing Wail(6)
  Survivor
    block +13 | enemy_deltas: Magi Knight: hp -2
  turn_end
    -No Draw

### Round 4
Intent: Flail Knight: Attack(12x2=24), Magi Knight: Defend
  Apparition
    energy -1 | +Intangible(1)
  Backflip
    energy -1 | block +10
  Shiv -> Magi Knight[1]
    enemy_deltas: Magi Knight: hp -10
  Leading Strike -> Magi Knight[1]
    energy -1 | enemy_deltas: Magi Knight: hp -3
  Shiv -> Magi Knight[1]
    enemy_deltas: Magi Knight: hp -10
  Shiv -> Magi Knight[1]
    -Dampen | enemy_deltas: Magi Knight: DIED
  turn_end

### Round 5
Intent: Flail Knight: Attack(18)
  Calculated Gamble
    exhausted: Shiv*8 [0]: Deal 4 damage. Exhaust.
  Blade Dance+
    energy -1 | exhausted: Shiv*8 [0]: Deal 4 damage. Exhaust.
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -20
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Cloak and Dagger+
    energy -1 | block +11
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    block -11 | -Dexterity | -Accuracy | -Infinite Blades | enemy_deltas: Flail Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 5 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Apparition "Ethereal. Gain 1 Intangible. Exhaust." -> 2 plays, EXHAUST
  Conflagration "Deal 16 damage to ALL enemies. Deals 2 additional damage for each other Attack you've played this turn." -> 1 plays, 48 dmg
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 1 plays, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 17 plays, 149 dmg, 30 block, EXHAUST
  Accuracy+ "Ethereal. Shivs deal 6 additional damage." -> 1 plays
  Rage+ "Ethereal. Whenever you play an Attack this turn, gain 5 Block." -> 1 plays
  Blade of Ink+ "Ethereal. Add 3 Inky Shivs into your Hand." -> 1 plays
  Blade Dance "Ethereal. Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Pinpoint "Ethereal. Deal 30 damage. Costs 1 less 1 energy for each Skill played this turn." -> 1 plays, 5 block
  Bullet Time "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays
  Strangle "Deal 8 damage. Whenever you play a card this turn, the enemy loses 2 HP." -> 1 plays, 8 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 5 dmg
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, 2 dmg, generates 1 Shivs
  Footwork "Gain 2 Dexterity." -> 1 plays, 2 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 2 dmg, EXHAUST
  Survivor "Gain 13 Block. Discard 1 card." -> 1 plays, 2 dmg, 13 block
  Backflip "Gain 10 Block. Draw 2 cards." -> 1 plays, 10 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, generates 2 Shivs
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Cloak and Dagger+ "Gain 11 Block. Add 2 Shivs into your Hand." -> 1 plays, 11 block, generates 2 Shivs

Active powers: Vigor(8)

Token attribution (Shivs):
  other: 4 Shivs -> ~35 dmg
  Blade Dance+: 4 Shivs -> ~35 dmg
  Blade Dance: 3 Shivs -> ~26 dmg
  Hidden Daggers: 2 Shivs -> ~18 dmg
  Leading Strike: 2 Shivs -> ~18 dmg
  Cloak and Dagger+: 2 Shivs -> ~18 dmg

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:3

Unattributed damage (power/passive effects): 23
  Per round: R2:22 R4:1

[Selected: elite] Mecha Knight (F43, elite)
## Combat Replay: vs Mecha Knight (Floor 43, elite)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry, Unceasing Top, Oddly Smooth Stone, Miniature Tent, Signet Ring, Happy Flower, Petrified Toad, Parrying Shield, Horn Cleat
Deck (31): Defend x4, Bubble Bubble x2, Accelerant+, Acrobatics+, Adrenaline+, Backflip, Backflip+, Calculated Gamble, Cloak and Dagger, Dagger Throw, Dagger Throw+, Dark Shackles, Deadly Poison+, Defend+, Dodge and Roll, Exterminate, Haze, Haze+, Malaise+, Mirage, Noxious Fumes, Piercing Wail, Predator+, Snakebite, Suppress, Survivor, Well-Laid Plans
Enemies: Mecha Knight HP=300/300

### Round 1
Intent: Mecha Knight: Attack(25)
  Backflip+
    energy -1 | block +9
  Suppress -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -13, Artifact(3→2)
  Dark Shackles -> Mecha Knight[0]
    exhausted: Dark Shackles [0]: Enemy loses 9 Strength this turn. Exhaust. | enemy_deltas: Mecha Knight: Artifact(2→1)
  Defend+
    energy -1 | block +9
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  Malaise+ -> Mecha Knight[0]
    energy -1 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Mecha Knight: +Weak(2), -Artifact
  turn_end

### Round 2
Agent plan (hypothesis): Enemy has high poison now, look for Accelerant or more multipliers.
Agent plan (hypothesis): Continue pushing poison and looking for Accelerant.
Intent: Mecha Knight: StatusCard(4)
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -9
  Haze
  Bubble Bubble -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(4→13)
  Cloak and Dagger
    energy -1 | block +7
  Shiv -> Mecha Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -4
  Calculated Gamble
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  turn_end

### Round 3
Agent plan (hypothesis): If Adrenaline is drawn, use it to extend the turn.
Intent: Mecha Knight: Defend, Buff
  Accelerant+
    energy -1 | +Accelerant(2)
  Dagger Throw+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -12
  Burn
  Backflip
    energy -1 | block +6
  turn_end

### Round 4
Agent plan (hypothesis): Look for Weak, Piercing Wail, or Shackles to mitigate the massive attack.
Intent: Mecha Knight: Attack(40)
  Adrenaline+
    energy +2 | exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Bubble Bubble -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(9→18)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Survivor
    energy -1 | block +9
  turn_end
  Dagger Throw+

### Round 5
Agent plan (hypothesis): Hold Snakebite with Well-Laid Plans.
Intent: Mecha Knight: StatusCard(4)
  Potion-Shaped Rock -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -15
  Dagger Throw+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -12
  Burn
  Predator+ -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -20
  turn_end
  Backflip

### Round 6
Intent: Mecha Knight: Defend, Buff
  Acrobatics+
    energy -1
  Burn
  Snakebite -> Mecha Knight[0]
    energy -2 | enemy_deltas: Mecha Knight: Poison(16→23)
  turn_end
  Backflip
## Combat Analytics: Mecha Knight (WIN - 6 rounds)

Cards played (with descriptions):
  Backflip+ "Gain 9 Block. Draw 2 cards." -> 1 plays, 9 block
  Suppress "Innate. Deal 13 damage. Apply 3 Weak." -> 1 plays, 13 dmg
  Dark Shackles "Enemy loses 9 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Defend+ "Gain 9 Block." -> 1 plays, 9 block
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 1 plays, 5 block
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 2 plays, +18 poison
  Cloak and Dagger "Gain 7 Block. Add 1 Shiv into your Hand." -> 1 plays, 7 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 4 dmg, EXHAUST
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Dagger Throw+ "Deal 12 damage. Draw 1 card. Discard 1 card." -> 2 plays, 24 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 1 plays, 6 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Defend "Gain 6 Block." -> 2 plays, 12 block
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, +7 poison

Active powers: Dexterity(1)

Token attribution (Shivs):
  Cloak and Dagger: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Bubble Bubble: 18 stacks
  Snakebite: 7 stacks

Enemy power timeline:
  Artifact: R1:3 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Poison: R1:- -> R2:- -> R3:12 -> R4:9 -> R5:17 -> R6:16
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-

[Selected: boss] Door (F48, boss)
## Combat Replay: vs Door (Floor 48, boss)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry, Unceasing Top, Oddly Smooth Stone, Miniature Tent, Signet Ring, Happy Flower, Petrified Toad, Parrying Shield, Horn Cleat, Whetstone, Beating Remnant
Deck (32): Defend x4, Bubble Bubble x2, Dagger Throw+ x2, Accelerant+, Acrobatics+, Adrenaline+, Backflip, Backflip+, Calculated Gamble, Cloak and Dagger, Dark Shackles, Deadly Poison+, Defend+, Dodge and Roll, Exterminate, Haze, Haze+, Malaise+, Mirage+, Noxious Fumes, Piercing Wail, Piercing Wail+, Predator+, Snakebite, Suppress+, Survivor, Well-Laid Plans+
Enemies: Door HP=999999999/999999999

### Round 1
Intent: Door: Summon
  Acrobatics+
    energy -1
  Haze
  Accelerant+
    energy -1 | +Accelerant(2)
  Backflip+
    energy -1 | block +9
  turn_end

### Round 2
Agent plan (hypothesis): Poison is ticking hard. Just keep defending and look for Noxious Fumes to scale it further.
Agent plan (hypothesis): Poison engine is online with Accelerant and Fumes. Survive and stack block.
Intent: Doormaker: Attack(30)
  Potion-Shaped Rock -> Doormaker[0]
    enemy_deltas: Doormaker: hp -15
  Backflip
    energy -1 | block +6 | exhausted: Backflip [1]: Gain 5 Block. Draw 2 cards. Exhaust.
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Malaise+ -> Doormaker[0]
    energy -1 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Doormaker: +Strength(-2), +Weak(2)
  turn_end

### Round 3
Agent plan (hypothesis): Poison is scaling rapidly. Maintain block and let poison do the work.
Intent: Doormaker: Attack(16)
  Snakebite -> Doormaker[0]
    energy -2 | enemy_deltas: Doormaker: Poison(2→9)
  Deadly Poison+ -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(9→16)
  Mirage+
    block +17 | exhausted: Mirage+ [0]: Gain Block equal to Poison on ALL enemies. (Gain 16 Block) Exhaust.
  Defend
    energy -1 | block +6
  turn_end

### Round 4
Agent plan (hypothesis): Grasp makes everything cost 1 more energy. Retained defensive cards will help us block in the following turns while poison finishes the boss.
Agent plan (hypothesis): Poison is scaling exponentially. Keep defending and letting poison do the work in the remaining turns.
Intent: Doormaker: Attack(8x2=16), Buff
  Stable Serum
    +Retain Hand(2)
  Adrenaline+
    energy +1 | exhausted: Mirage+ [0]: Gain Block equal to Poison on ALL enemies. (Gain 15 Block) Lose 1 energy . Exhaust.
  Bubble Bubble -> Doormaker[0]
    energy -2 | enemy_deltas: Doormaker: Poison(15→24)
  Bubble Bubble -> Doormaker[0]
    energy -2 | enemy_deltas: Doormaker: Poison(24→33)
  turn_end
    Retain Hand(2→1)

### Round 5
Agent plan (hypothesis): Poison is accelerating massively. Continue to block and let the poison stack.
Agent plan (hypothesis): Let poison kill the boss.
Intent: Doormaker: Attack(31)
  Suppress+ -> Doormaker[0]
    exhausted: Suppress+ [0]: Innate. Deal 19 damage. Apply 5 Weak. Exhaust. | enemy_deltas: Doormaker: hp -19, +Weak(5)
  Piercing Wail
    energy -1 | exhausted: Suppress+ [0]: Innate. Deal 19 damage. Apply 5 Weak. Exhaust. | enemy_deltas: Doormaker: Strength(1→-5), +Piercing Wail(6)
  Dagger Throw+ -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: hp -12
  Haze+
  Piercing Wail+
    energy -1 | exhausted: Suppress+ [0]: Innate. Deal 19 damage. Apply 5 Weak. Exhaust. | enemy_deltas: Doormaker: Strength(-5→-13), Piercing Wail(6→14)
  turn_end
    -Retain Hand

### Round 6
Agent plan (hypothesis): GG! We stacked poison past his HP threshold.
Intent: Doormaker: Attack(18)
  Bubble Bubble -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(37→46)
  Deadly Poison+ -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(46→53)
  Snakebite -> Doormaker[0]
    energy -2 | enemy_deltas: Doormaker: Poison(53→60)
  turn_end

### Round 7
Agent plan (hypothesis): Boss killed, Act 3 completed.
Intent: Doormaker: Attack(8x2=16), Buff
  Exterminate
    energy -1 | -Dexterity | -Accelerant | -Noxious Fumes | enemy_deltas: Doormaker: DIED
## Combat Analytics: Door (WIN - 7 rounds)

Cards played (with descriptions):
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Backflip+ "Gain 9 Block. Draw 2 cards." -> 1 plays, 9 block
  Backflip "Gain 6 Block. Draw 2 cards. Exhaust." -> 1 plays, 6 block, EXHAUST
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, +14 poison
  Deadly Poison+ "Apply 7 Poison." -> 2 plays, +14 poison
  Mirage+ "Gain Block equal to Poison on ALL enemies. (Gain 17 Block) Exhaust." -> 1 plays, 17 block, EXHAUST
  Defend "Gain 6 Block." -> 1 plays, 6 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Lose 1 energy . Exhaust." -> 1 plays, EXHAUST
  Bubble Bubble "If the enemy has Poison, apply 9 Poison. Lose 1 energy ." -> 3 plays, +27 poison
  Suppress+ "Innate. Deal 19 damage. Apply 5 Weak. Exhaust." -> 1 plays, 19 dmg, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw+ "Deal 12 damage. Draw 1 card. Discard 1 card. Exhaust." -> 1 plays, 12 dmg, EXHAUST
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Exterminate "Deal 3 damage 4 times to ALL enemies. Lose 1 energy ." -> 1 plays

Active powers: Dexterity(1)

Poison stacks applied per card:
  Bubble Bubble: 27 stacks
  Snakebite: 14 stacks
  Deadly Poison+: 14 stacks

Enemy power timeline:
  Grasp: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1
  Hunger: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:-
  Poison: R1:- -> R2:- -> R3:2 -> R4:15 -> R5:32 -> R6:37 -> R7:59
  Scrutiny: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:-
  Strength: R1:- -> R2:- -> R3:-2 -> R4:-2 -> R5:1 -> R6:1 -> R7:1
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:4 -> R7:3

## Triggered Skills This Run
- The Silent - Boss Strategy: F17(Lagavulin Matriarch: WIN), F33(Crusher: ), F48(Door: WIN)
- The Silent - Combat Principles: F2(Corpse Slug: WIN), F3(Toadpole: WIN), F5(Sludge Spinner: WIN), F6(Two-Tailed Rat: WIN), F7(Punch Construct: WIN), F8(Terror Eel: WIN), F15(Calcified Cultist: ), F19(Tunneler: WIN), F20(Exoskeleton: WIN), F21(Hunter Killer: WIN), F22(Ovicopter: WIN), F30(Infested Prism: WIN), F35(Scroll of Biting: WIN), F39(Devoted Sculptor: WIN), F40(Flail Knight: ), F43(Mecha Knight: WIN), F45(Slimed Berserker: WIN)
- The Silent - Deckbuilding Principles: F2(), F3(), F4(), F5(), F6(), F7(), F8(), F13(), F13(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F25(), F25(), F25(), F30(), F30(), F31(), F31(), F33(), F35(), F36(), F36(), F38(), F38(), F38(), F39(), F40(), F43(), F45()
- The Silent - Path Selection: F1(), F1(), F2(), F3(), F3(), F4(), F5(), F6(), F7(), F8(), F8(), F9(), F10(), F11(), F12(), F13(), F14(), F15(), F18(), F18(), F19(), F20(), F21(), F22(), F23(), F24(), F26(), F27(), F28(), F34(), F34(), F40(), F40(), F42(), F42(), F45(), F45()
- The Silent - Rest & Event Decisions: F12(), F16(), F24(), F28(), F29(), F32(), F32(), F44(), F44(), F47(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.