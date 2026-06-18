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
Result: DEFEAT at Floor 48 (fitness: 137.6)
Combats won: 6/6
Run duration: 3938.3s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F30
- [card_select] Committed Shiv plan: generate shivs to fuel Finisher and Fan of Knives AoE, while scaling defense with Footwork. Keep removing basic Strikes and Defends.
- [map] Foundation deck focusing on defensive stability; currently prioritizing survival through Act 2 by avoiding elites and pathing toward the final rest site for a key upgrade or emergency heal.
### F31
- [card_select] Committed shiv plan: generate shivs to fuel Finisher and fan of knives damage, while scaling defense with Footwork. Needs consistent card draw; skip off-plan attacks.
- [card_reward] Committed to Shivs and frontload damage. Use Calculated Gamble to cycle past basics and find Footwork++ or Finisher on key turns. Need more scaling damage like Accuracy or Shuriken, and reliable card draw to keep the engine going.
### F32
- [rest_site] Committed Shiv deck: generates shivs with Blade Dance, Leading Strike, and Up My Sleeve to deal damage and fuel Finisher. Footwork provides block scaling. Needs more card draw to sustain hand size.
### F33
- [card_select] Committed shiv plan: utilize shiv generation to trigger Fan of Knives and scale damage, using Footwork for block. Keep prioritizing upgraded shiv generators and exhaust synergies.
- [card_reward] Committed Shiv/Poison hybrid: Use Shivs and multi-attacks to rapidly stack Poison via Envenom while relying on Footwork++ for defense. The deck needs more card draw to consistently find and play Envenom early, and perhaps a Catalyst or more multi-hits.
### F34
- [event] Committed shiv/poison hybrid: survive using Apparitions and block cards while setting up Footwork, Envenom, and Fan of Knives to deal passive and scaling damage. Focus on cycling through the deck to find key powers and defensive tools.
- [map] Foundation deck: currently balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F35
- [card_select] Committed shiv/poison plan: cycle fast with Gamble/Acrobatics, generate shivs to trigger Fan of Knives/Envenom/Joss Paper, and survive with Apparitions.
- [card_reward] Committed Shiv engine: use Apparitions to safely set up powers like Accuracy and Envenom, then chain Shiv generators for massive burst damage. Needs more card draw to cycle quickly and find Apparitions on dangerous turns.
- [map] Foundation deck currently balanced between strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F36
- [event] Committed shiv/poison hybrid: survive using Apparitions and block cards while setting up Footwork, Envenom, and Fan of Knives to deal passive and scaling damage. Focus on cycling through the deck to find key powers and defensive tools.
- [map] Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F37
- [map] Foundation deck focusing on basic strikes and blocks; prioritizing shops to trigger Meal Ticket healing and card removal while searching for a definitive poison or shiv scaling engine.
### F39
- [card_select] Shiv engine with Apparitions. Use Apparitions to buy time to set up Envenom, Accuracy, and Footwork, then spam Shivs.
- [card_reward] Committed Shiv/Poison hybrid. Use Apparitions for boss multi-attacks and Footwork+Dodge and Roll for sustained mitigation. Output damage via Accuracy++ Shivs and Envenom. Avoid bloated cards; focus on draw and upgrading Shiv generators.
- [map] Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F40
- [rest_site] Committed Shiv-Poison hybrid. Use Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom. Well-Laid Plans is crucial for holding Apparitions until dangerous turns. Generate massive damage and poison scaling with Shivs. Needs card draw to keep hand full and energy to play everything.
### F41
- [map] Foundation deck focusing on basic strikes and blocks; prioritizing shops to trigger Meal Ticket healing and card removal while searching for a definitive poison or shiv scaling engine.
### F42
- [rest_site] Committed Shiv-Poison hybrid. Retain Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom, then scale massively with Shivs.
- [map] Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F43
- [card_select] Play Blade Dance to maximize damage output with our last energy.
- [card_reward] Committed shiv/poison plan: play Envenom and Accuracy, cycle fast with draw to find Apparitions for safety, and scale damage with Shivs. Need to keep deck lean and focus on card draw and energy to output enough attacks.
- [map] Foundation deck still reliant on basic strikes and blocks; prioritizing rest sites and shops to leverage Meal Ticket healing while fishing for a late-game poison or shiv scaling engine before the Act 3 boss.
### F44
- [rest_site] Committed Shiv-Poison hybrid. Retain Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom, then scale massively with Shivs. Need to prioritize card draw and retain mechanics; avoid raw non-scaling attacks.
- [map] Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.
### F45
- [event] Committed shiv/poison hybrid with Apparitions. Win by setting up Envenom, Accuracy, and Fan of Knives, then bursting with Shivs and Finisher. Stall with Apparitions while scaling. Avoid adding non-synergistic attacks.
### F46
- [card_select] Committed shiv plan: scale with Accuracy and Envenom, play generated Shivs for damage and exhaust synergies, and use Apparitions/Footwork to survive.
- [card_reward] Committed shiv/poison plan: generate shivs to fuel Accuracy++ and Envenom++, while using Apparitions and Footwork to survive. Play powers early and cycle into shiv generators. Needs card draw to find the engine faster.
### F47
- [rest_site] Committed shiv/poison plan: play Envenom and Accuracy, then spam Shivs to scale both direct damage and poison. Use Well-Laid Plans to retain Apparitions for dangerous turns. Avoid adding more basic attacks; look for card draw.
### F48
- [card_select] Committed shiv/poison plan: Play cheap attacks to stack poison via Envenom and scale with Accuracy. Prioritize defensive cards and use Expose to strip block when necessary. Maintain block via Apparitions and high-value block cards while poison kills.

### Combat Decision Digest (7 combats)
F31 [monster] multi:Myte+Myte (4R, HP 58->59, loss=0, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Dagger Throw->Blade Dance->Cloak and Dagger->Shiv*4->Finisher | dealt=16 taken=0
  R2[Myte: Atk(13)]: Secret Technique->Survivor->Dodge and Roll->Toxic->Footwork+->Deflect | dealt=0 taken=0
  R3[Myte: Atk(4), Buff]: Fan of Knives->Shiv*4->Leading Strike->Shiv->Neutralize->Leading Strike->Shiv*3 | dealt=47 taken=0
  R4[Myte: StatusCard(2)]: Predator+ | dealt=0 taken=0

F33 [boss] multi:Crusher+Rocket (10R, HP 82->68, loss=14, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Fan of Knives->Shiv*4->Leading Strike->Shiv*2->Neutralize->Dodge and Roll | dealt=57 taken=5
  R2[Crusher: Atk(4)+Rocket: Atk(27)]: Expose->Secret Technique->Deflect->Predator+->Cloak and Dagger->Shiv->Strike | dealt=49 taken=7
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Footwork+->Blade Dance->Shiv*3->Finisher->Defend+->Survivor | dealt=69 taken=0
  R4[Crusher: Buff+Rocket: Atk(33)]: Dodge and Roll->Cloak and Dagger->Shiv->Leading Strike->Shiv*2->Defend->Neutralize | dealt=24 taken=0
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Deflect->Defend->Leading Strike->Shiv*2->Strike*2 | dealt=24 taken=0
  R6[Crusher: Atk(14)+Rocket: Atk(7)]: Cloak and Dagger->Leading Strike->Shiv*3->Neutralize->Dodge and Roll->Dagger Throw | dealt=21 taken=1
  R7[Crusher: Atk(6)+Rocket: Atk(30)]: Deflect->Predator+->Calculated Gamble+->Up My Sleeve->Shiv*3 | dealt=11 taken=0
  R8[Crusher: Atk(14x2=28), Debuff]: Neutralize->Predator+->Finisher->Deflect->Defend+ | dealt=44 taken=2
  R9[Crusher: Buff]: Up My Sleeve->Shiv*3->Leading Strike->Shiv*2->Leading Strike->Shiv*2->Dodge and Roll | dealt=27 taken=0
  R10[Crusher: Atk(22), Defend]: Neutralize->Defend->Dagger Throw->Up My Sleeve->Shiv*2 | dealt=7 taken=0

F35 [monster] Devoted Sculptor (4R, HP 74->66, loss=8, WIN)
  R1[Devoted Sculptor: Buff]: Envenom->Neutralize->Leading Strike->Shiv*2->Deflect | dealt=20 taken=0
  R2[Devoted Sculptor: Atk(12)]: Footwork+->Predator+ | dealt=20 taken=9
  R3[Devoted Sculptor: Atk(21)]: Apparition->Secret Technique->Expose->Calculated Gamble+->Blade Dance->Shiv*3->Leading Strike->Shiv*2 | dealt=34 taken=0
  R4[Devoted Sculptor: Atk(30)]: Apparition->Leading Strike->Shiv*2->Finisher | dealt=60 taken=0

F39 [monster] multi:Living Shield+Turret Operator (4R, HP 68->65, loss=3, WIN)
  R1[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Secret Technique->Apparition->Well-Laid Plans->Defend | dealt=0 taken=0
  R2[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Accuracy+->Cloak and Dagger->Shiv->Survivor | dealt=0 taken=4
  R3[Living Shield: Atk(6)+Turret Operator: Buff]: Neutralize->Dodge and Roll->Blade Dance->Shiv*3->Finisher | dealt=45 taken=0
  R4[Living Shield: Atk(16), Buff]: Expose->Leading Strike->Shiv*2->Up My Sleeve->Shiv*2 | dealt=49 taken=0

F43 [monster] multi:Cubex Construct+Cubex Construct+Punch Construct (5R, HP 67->42, loss=25, WIN)
  R1[Punch Construct: Defend+Cubex Construct: Buff+Cubex Construct: Buff]: Neutralize->Accuracy+->Strike->Strike+->Deflect | dealt=0 taken=0
  R2[Punch Construct: Atk(14)+Cubex Construct: Atk(9), Buff+Cubex Construct: Atk(9), Buff]: Apparition->Well-Laid Plans+->Secret Technique->Blade Dance->Shiv*3 | dealt=0 taken=0
  R3[Punch Construct: Atk(5x2=10), Debuff+Cubex Construct: Atk(11), Buff+Cubex Construct: Atk(11), Buff]: Expose->Leading Strike->Shiv*2->Finisher->Defend+ | dealt=51 taken=11
  R4[Punch Construct: Defend+Cubex Construct: Atk(11x2=22)]: Cloak and Dagger->Shiv->Predator+->Calculated Gamble+ | dealt=22 taken=15
  R5[Punch Construct: Atk(14)]: Leading Strike->Shiv*2->Predator+ | dealt=21 taken=0

F46 [monster] Globe Head (5R, HP 44->36, loss=8, WIN)
  R1[Globe Head: Atk(13), Debuff]: Apparition->Envenom+ | dealt=0 taken=0
  R2[Globe Head: Atk(6x3=18)]: Dagger Throw->Deflect->Defend+->Defend | dealt=0 taken=3
  R3[Globe Head: Atk(16), Buff]: Expose->Neutralize->Apparition->Backflip->Cloak and Dagger+->Shiv*2 | dealt=21 taken=0
  R4[Globe Head: Atk(15), Debuff]: Blade Dance->Shiv*3->Calculated Gamble+->Secret Technique->Defend+->Cloak and Dagger+->Shiv*2 | dealt=30 taken=0
  R5[Globe Head: Atk(8x3=24)]: Deflect->Up My Sleeve->Shiv->Accuracy+->Shiv*2 | dealt=36 taken=5

F48 [boss] multi:Queen+Torch Head Amalgam (7R, HP 38->0, loss=38, LOSS)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Well-Laid Plans+->Cloak and Dagger+->Blade Dance->Shiv*5 | dealt=20 taken=1
  R2[Torch Head Amalgam: Atk(18)+Queen: Debuff]: Accuracy+->Defend->Blade Dance->Shiv*3 | dealt=30 taken=10
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Apparition+->Leading Strike->Shiv*2->Finisher | dealt=36 taken=2
  R4[Torch Head Amalgam: Atk(22)+Queen: Buff, Defend]: Neutralize->Deflect->Dodge and Roll+->Leading Strike->Shiv*2->Secret Technique->Expose->Defend+ | dealt=20 taken=2
  R5[Torch Head Amalgam: Atk(24)+Queen: Buff, Defend]: Footwork+->Calculated Gamble->Cloak and Dagger+->Shiv*2->Dodge and Roll | dealt=14 taken=1
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Neutralize->Dodge and Roll+->Survivor->Calculated Gamble+->Strike | dealt=8 taken=15
  R7[Torch Head Amalgam: Atk(27)+Queen: Buff, Defend]: Fan of Knives->Leading Strike->Shiv*6->Deflect | dealt=73 taken=0

### Non-combat Decisions (86 decisions)
F30 [shop] buy_relic (option_index=0) | source=plan
  HP 56->56 | Gold 656->469 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan [1/4]: Provides burst card draw exactly when we need it most (upon taking damage), helping us recover and stabilize.

F30 [shop] buy_card (option_index=6) | source=plan
  HP 56->56 | Gold 469->304 | Deck 24->25
  deck_change: bought Secret Technique
  reasoning: Shop plan [2/4]: Allows us to instantly tutor our critical Skills, such as Footwork++ for early defense or Blade Dance / Up My Sleeve for burst damage.

F30 [shop] remove_card_at_shop | source=plan
  HP 56->56 | Gold 304->304 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Removing a Strike to increase the consistency of drawing our Shiv engine cards and defensive tools.

F30 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->56 | Gold 304->154 | Deck 25->24
  deck_change: lost Strike
  reasoning: Strike is the weakest card in the deck. We have plenty of better attacks and shiv generators to fuel Finisher and Fan of Knives. Removing Strike improves our draw consistency.
  strategic_note: Committed Shiv plan: generate shivs to fuel Finisher and Fan of Knives AoE, while scaling defense with Footwork. Keep removing basic Strikes and Defends.

F30 [shop] buy_potion (option_index=1) | source=plan
  HP 56->56 | Gold 154->51 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan [4/4]: A premium potion that lets us recur high-impact cards like Predator++ or Finisher for free during crucial turns, especially Act 2/3 bosses.

F30 [shop] close_shop_inventory | source=plan
  HP 56->56 | Gold 51->51 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F30 [shop] proceed | source=auto
  HP 56->56 | Gold 51->51 | Deck 24->24
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F30 [map] choose_map_node (option_index=0) | source=llm
  HP 56->58 | Gold 51->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Act 2 hallway fights are dangerous, but elites in Act 2 are often run-ending without a highly specialized deck. Given my current HP (56/81) and the route intelligence suggesting zero elites is optimal for Act 2, the Monster node is the safer path to the pre-boss Rest Site.
  strategic_note: Foundation deck focusing on defensive stability; currently prioritizing survival through Act 2 by avoiding elites and pathing toward the final rest site for a key upgrade or emergency heal.

F31 [card_select] select_deck_card (option_index=0) | source=llm
  HP 58->58 | Gold 51->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Secret Technique only fetches Skills, so we cannot fetch Footwork+. Deflect provides 0-cost block to help mitigate incoming damage while we deal with the Toxic cards in hand.
  strategic_note: Committed shiv plan: generate shivs to fuel Finisher and fan of knives damage, while scaling defense with Footwork. Needs consistent card draw; skip off-plan attacks.

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 51->66 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 66->66 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 59->59 | Gold 66->66 | Deck 24->25
  deck_change: picked Calculated Gamble+
  reasoning: Calculated Gamble++ is a premium cycle card, especially with Retain. It allows us to hold it until we need to dig for key cards like Footwork++ or Finisher, or simply cycle away a hand full of basics. It also exhausts, which synergizes with Joss Paper.
  strategic_note: Committed to Shivs and frontload damage. Use Calculated Gamble to cycle past basics and find Footwork++ or Finisher on key turns. Need more scaling damage like Accuracy or Shuriken, and reliable card draw to keep the engine going.

F31 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 59->59 | Gold 66->66 | Deck 25->25
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 66->66 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 59->82 | Gold 66->66 | Deck 25->25
  deck_change: no deck change
  reasoning: With the Act 2 Boss next and missing 23 HP, resting to enter the fight at maximum HP (82/82) provides more value and safety than a single card upgrade.
  strategic_note: Committed Shiv deck: generates shivs with Blade Dance, Leading Strike, and Up My Sleeve to deal damage and fuel Finisher. Footwork provides block scaling. Needs more card draw to sustain hand size.

F32 [rest_site] proceed | source=auto
  HP 82->82 | Gold 66->66 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 82->82 | Gold 66->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [card_select] select_deck_card (option_index=1) | source=llm
  HP 77->77 | Gold 66->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Fetching Cloak and Dagger to generate block and a Shiv for offense and defense.
  strategic_note: Committed shiv plan: utilize shiv generation to trigger Fan of Knives and scale damage, using Footwork for block. Keep prioritizing upgraded shiv generators and exhaust synergies.

F33 [card_select] select_deck_card (option_index=6) | source=llm
  HP 70->70 | Gold 66->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Choosing Blade Dance to generate 3 Shivs. With Liquid Memories, it costs 0, which lets us maximize our attack count for Finisher to deal massive damage.

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 66->141 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 141->141 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 141->141 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 68->68 | Gold 141->141 | Deck 25->26
  deck_change: picked Envenom
  reasoning: With our high density of Shiv generation (Blade Dance, Fan of Knives, Up My Sleeve, Leading Strikes) and multi-hit attacks, Envenom provides an incredible scaling damage engine. This gives our deck the necessary reach to take down high-HP bosses like the upcoming Crusher+Rocket.
  strategic_note: Committed Shiv/Poison hybrid: Use Shivs and multi-attacks to rapidly stack Poison via Envenom while relying on Footwork++ for defense. The deck needs more card draw to consistently find and play Envenom early, and perhaps a Catalyst or more multi-hits.

F33 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 68->68 | Gold 141->141 | Deck 26->26
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 68->80 | Gold 141->141 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 80->74 | Gold 141->141 | Deck 26->29
  deck_change: added Apparition x3
  reasoning: Apparitions provide unmatched defensive power, giving us safe turns to play our expensive powers like Envenom and Fan of Knives. The Max HP loss is minimal.
  strategic_note: Committed shiv/poison hybrid: survive using Apparitions and block cards while setting up Footwork, Envenom, and Fan of Knives to deal passive and scaling damage. Focus on cycling through the deck to find key powers and defensive tools.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 74->74 | Gold 141->141 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=2) | source=llm
  HP 74->74 | Gold 141->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Starting Act 2 with full HP. Taking the recommended Monster node at c4,r1 to begin building deck strength for the act. Act 2 hallway fights are dangerous, but I need gold and card rewards to scale, and I have Meal Ticket to sustain via future shops.
  strategic_note: Foundation deck: currently balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F35 [card_select] select_deck_card (option_index=3) | source=llm
  HP 65->65 | Gold 141->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Fetching Expose to strip block and apply Vulnerable before using Calculated Gamble to cycle our hand and save our Apparitions from exhausting.
  strategic_note: Committed shiv/poison plan: cycle fast with Gamble/Acrobatics, generate shivs to trigger Fan of Knives/Envenom/Joss Paper, and survive with Apparitions.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 141->148 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 148->148 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 66->66 | Gold 148->148 | Deck 29->30
  deck_change: picked Accuracy+
  reasoning: Deck has 6 Shiv generators producing up to 15 Shivs per cycle. Accuracy++ gives +6 damage per Shiv, representing a massive scaling spike (+90 damage per cycle) that is desperately needed for Act 3 bosses.
  strategic_note: Committed Shiv engine: use Apparitions to safely set up powers like Accuracy and Envenom, then chain Shiv generators for massive burst damage. Needs more card draw to cycle quickly and find Apparitions on dangerous turns.

F35 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 66->66 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F35 [map] choose_map_node (option_index=1) | source=llm
  HP 66->66 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route towards an early shop to leverage Meal Ticket for healing while avoiding unnecessary chip damage from elites. Unknown nodes in Act 3 are generally safer than early monster nodes when looking to preserve HP for the final boss.
  strategic_note: Foundation deck currently balanced between strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F36 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 66->51 | Gold 148->148 | Deck 30->30
  deck_change: upgraded Defend->Defend+, Strike->Strike+
  reasoning: The -2 draw penalty from Big Mushroom severely cripples our turn 1 setup, which is critical for finding our Apparitions and setting up powers like Envenom and Footwork. Losing 15 HP to gain 2 random upgrades is a minor price to pay, especially since we have Apparitions to mitigate damage in combats.
  strategic_note: Committed shiv/poison hybrid: survive using Apparitions and block cards while setting up Footwork, Envenom, and Fan of Knives to deal passive and scaling damage. Focus on cycling through the deck to find key powers and defensive tools.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 51->51 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=llm
  HP 51->51 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: The 'Unknown' node on the current route is the safest path toward the upcoming Shop, which triggers Meal Ticket for 15 HP. Act 3 hallway fights (Monster node) can be high-damage, so avoiding unnecessary combat while at 68% HP is prudent.
  strategic_note: Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 51->51 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [map] choose_map_node (option_index=0) | source=llm
  HP 51->66 | Gold 148->148 | Deck 30->30
  deck_change: no deck change
  reasoning: Meal Ticket provides 15 HP healing at shops, and I have 148 gold for card removals or key relics. This path aligns with the goal of maintaining high HP for the Act 3 boss while thinning the deck.
  strategic_note: Foundation deck focusing on basic strikes and blocks; prioritizing shops to trigger Meal Ticket healing and card removal while searching for a definitive poison or shiv scaling engine.

F38 [shop] buy_card (option_index=4) | source=plan
  HP 66->66 | Gold 148->71 | Deck 30->31
  deck_change: bought Well-Laid Plans
  reasoning: Shop plan [1/2]: Crucial for holding Apparitions or Calculated Gamble for the exact turn they are needed, drastically increasing our consistency and survivability.

F38 [shop] buy_potion (option_index=2) | source=plan
  HP 66->66 | Gold 71->21 | Deck 31->31
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Emergency draw is extremely valuable for finding our key powers or Apparitions on turn 1/2 of elite or boss fights.

F38 [shop] close_shop_inventory | source=plan
  HP 66->66 | Gold 21->21 | Deck 31->31
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F38 [shop] proceed | source=auto
  HP 66->66 | Gold 21->21 | Deck 31->31
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 66->68 | Gold 21->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Monster

F39 [card_select] select_deck_card (option_index=0) | source=llm
  HP 68->68 | Gold 21->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the turn plan to mitigate incoming damage, we fetch Apparition so we can safely play our setup cards this turn.
  strategic_note: Shiv engine with Apparitions. Use Apparitions to buy time to set up Envenom, Accuracy, and Footwork, then spam Shivs.

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 21->28 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 28->28 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 65->65 | Gold 28->28 | Deck 31->32
  deck_change: picked Dodge and Roll+
  reasoning: Dodge and Roll++ double-dips into the +3 Dexterity from Footwork++, providing a massive 18 block for 1 energy over two turns. This is incredibly valuable for surviving the Act 3 Boss's permanent Frail debuff.
  strategic_note: Committed Shiv/Poison hybrid. Use Apparitions for boss multi-attacks and Footwork+Dodge and Roll for sustained mitigation. Output damage via Accuracy++ Shivs and Envenom. Avoid bloated cards; focus on draw and upgrading Shiv generators.

F39 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 65->65 | Gold 28->28 | Deck 32->32
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F39 [map] choose_map_node (option_index=1) | source=llm
  HP 65->65 | Gold 28->28 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended path to a Rest Site. Given Act 3's high damage potential and my current HP, the Rest Site allows for a critical upgrade (Smith) to solidify the deck's foundation before the upcoming Treasure and Monster nodes. Avoiding the Elite at index 0 as it poses a high risk of significant HP loss or death without clear immediate scaling for the Act 3 boss.
  strategic_note: Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F40 [rest_site] choose_rest_option (option_index=1, smith_card_index=18) | source=llm
  HP 65->65 | Gold 28->28 | Deck 32->32
  deck_change: upgraded Envenom->Envenom+
  reasoning: HP is high (65/76), so we upgrade. Envenom+ doubles the poison output from every unblocked attack. With a Shiv-heavy deck (Fan of Knives, Blade Dance, Leading Strike, Cloak and Dagger), this provides massive, run-winning damage scaling for Act 3 Elites and Bosses.
  strategic_note: Committed Shiv-Poison hybrid. Use Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom. Well-Laid Plans is crucial for holding Apparitions until dangerous turns. Generate massive damage and poison scaling with Shivs. Needs card draw to keep hand full and energy to play everything.

F40 [rest_site] proceed | source=auto
  HP 65->65 | Gold 28->28 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 65->65 | Gold 28->28 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 65->65 | Gold 28->64 | Deck 32->32
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 65->65 | Gold 64->64 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim: Permafrost

F41 [treasure] proceed | source=random
  HP 65->65 | Gold 64->64 | Deck 32->32
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=llm
  HP 65->65 | Gold 64->64 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended route to the Rest Site to upgrade a key card. With 65/76 HP, I am healthy enough to prioritize smithing over resting, which aligns with the goal of strengthening the deck for the Act 3 boss.
  strategic_note: Foundation deck focusing on basic strikes and blocks; prioritizing shops to trigger Meal Ticket healing and card removal while searching for a definitive poison or shiv scaling engine.

F42 [rest_site] choose_rest_option (option_index=1, smith_card_index=21, note_scope=run, note_triggers=all) | source=llm
  HP 65->65 | Gold 64->64 | Deck 32->32
  deck_change: upgraded Well-Laid Plans->Well-Laid Plans+
  reasoning: HP is high, so we upgrade. Well-Laid Plans+ allows us to retain up to 2 cards, which is incredibly powerful for holding key combo pieces like Fan of Knives, Finisher, or an Apparition for the perfect turn.
  strategic_note: Committed Shiv-Poison hybrid. Retain Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom, then scale massively with Shivs.

F42 [rest_site] proceed | source=auto
  HP 65->65 | Gold 64->64 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=1) | source=llm
  HP 65->67 | Gold 64->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node. With only 64 gold and 65 HP, an Elite fight (index 0) is unnecessarily risky in Act 3 when the deck is still in a foundation stage. The Monster node provides gold and card rewards to further refine the deck before the upcoming Rest Site and Boss.
  strategic_note: Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F43 [card_select] select_deck_card (option_index=7) | source=llm
  HP 67->67 | Gold 64->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Blade Dance costs 1 energy, which exactly matches our remaining energy, and provides 3 Shivs for immediate damage.
  strategic_note: Play Blade Dance to maximize damage output with our last energy.

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 64->71 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 71->71 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim potion: Speed Potion

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 71->71 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 42->42 | Gold 71->71 | Deck 32->33
  deck_change: picked Backflip
  reasoning: The deck currently has no Backflips and relies heavily on Ring of the Snake for initial draw. Backflip provides essential card draw to cycle into Apparitions and our scaling Powers (Envenom, Accuracy), while synergizing perfectly with Footwork++ for efficient block.
  strategic_note: Committed shiv/poison plan: play Envenom and Accuracy, cycle fast with draw to find Apparitions for safety, and scale damage with Shivs. Need to keep deck lean and focus on card draw and energy to output enough attacks.

F43 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F43 [map] choose_map_node (option_index=0) | source=llm
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: no deck change
  reasoning: Current HP is 42/77 (55%). Heading into the final stretch of Act 3, prioritizing a Rest Site over a Monster node is the safer play to ensure survival for the boss. This allows for either a crucial upgrade to improve deck scaling or a heal if the previous fight was taxing.
  strategic_note: Foundation deck still reliant on basic strikes and blocks; prioritizing rest sites and shops to leverage Meal Ticket healing while fishing for a late-game poison or shiv scaling engine before the Act 3 boss.

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=9) | source=llm
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: upgraded Cloak and Dagger->Cloak and Dagger+
  reasoning: With 42 HP and Apparitions, we are safe enough to upgrade, especially with more rest sites ahead before the boss. Cloak and Dagger goes from 1 Shiv to 2 Shivs, doubling its damage potential and scaling perfectly with Accuracy, Envenom, and Finisher.
  strategic_note: Committed Shiv-Poison hybrid. Retain Apparitions for safety while setting up Accuracy, Fan of Knives, and Envenom, then scale massively with Shivs. Need to prioritize card draw and retain mechanics; avoid raw non-scaling attacks.

F44 [rest_site] proceed | source=auto
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=1) | source=llm
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: no deck change
  reasoning: With 42 HP and no major power spikes, taking an Elite at c0,r11 is extremely risky. The Unknown node at c1,r11 (recommended route) provides a safer path toward the Boss, allowing me to preserve HP for the final stretch and potentially find a high-value event or additional resources without the risk of a lethal encounter.
  strategic_note: Foundation deck: balanced between basic strikes and blocks; seeking high-impact poison or shiv scaling and premium block cards. Prioritize upgrading core engine pieces at rest sites and using shops to trigger Meal Ticket healing while removing basic cards.

F45 [event] choose_event_option (option_index=0) | source=llm
  HP 42->42 | Gold 71->71 | Deck 33->33
  deck_change: no deck change
  reasoning: Accepting is the only viable path forward since rejecting is either not allowed or severely penalizing.
  strategic_note: Committed shiv/poison hybrid with Apparitions. Win by setting up Envenom, Accuracy, and Fan of Knives, then bursting with Shivs and Finisher. Stall with Apparitions while scaling. Avoid adding non-synergistic attacks.

F45 [event] choose_event_option (option_index=0) | source=llm
  HP 42->42 | Gold 71->71 | Deck 33->34
  deck_change: added Regret
  reasoning: 2 random Relics provide a much higher ceiling than 2 card upgrades. We will add Regret to the deck, which we can hopefully exhaust with Calculated Gamble or simply endure, as our Apparitions will handle incoming damage.
  strategic_note: Committed shiv/poison hybrid with Apparitions. Win by setting up Envenom, Accuracy, and Fan of Knives, then bursting with Shivs and Finisher. Stall with Apparitions while scaling. Avoid adding non-synergistic attacks.

F45 [event] choose_event_option (option_index=0) | source=auto
  HP 42->42 | Gold 71->71 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Proceed

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 42->44 | Gold 71->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Monster

F46 [card_select] select_deck_card (option_index=5) | source=llm
  HP 41->41 | Gold 71->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Cloak and Dagger++ provides block to survive the incoming damage while generating Shivs to fuel our damage and scaling synergies.
  strategic_note: Committed shiv plan: scale with Accuracy and Envenom, play generated Shivs for damage and exhaust synergies, and use Apparitions/Footwork to survive.

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 71->86 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 86->86 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 86->86 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 36->36 | Gold 86->86 | Deck 34->35
  deck_change: picked Blade Dance
  reasoning: Blade Dance is a premium Shiv generator that directly fuels our Accuracy++ and Envenom++ engine, as well as Finisher. It is the best possible common card for our current deck.
  strategic_note: Committed shiv/poison plan: generate shivs to fuel Accuracy++ and Envenom++, while using Apparitions and Footwork to survive. Play powers early and cycle into shiv generators. Needs card draw to find the engine faster.

F46 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 36->36 | Gold 86->86 | Deck 35->35
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 86->86 | Deck 35->35
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=17, note_scope=run, note_triggers=all) | source=llm
  HP 36->36 | Gold 86->86 | Deck 35->35
  deck_change: upgraded Apparition->Apparition+
  reasoning: Since we have two back-to-back rest sites before the boss (F47 and F48), we can Smith now and evaluate if we need to Rest at F48 with our Regal Pillow. Upgrading Apparition removes Ethereal, allowing our Well-Laid Plans to safely retain it for crucial boss attacks.
  strategic_note: Committed shiv/poison plan: play Envenom and Accuracy, then spam Shivs to scale both direct damage and poison. Use Well-Laid Plans to retain Apparitions for dangerous turns. Avoid adding more basic attacks; look for card draw.

F47 [rest_site] proceed | source=auto
  HP 36->36 | Gold 86->86 | Deck 35->35
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 36->38 | Gold 86->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [card_select] select_deck_card (option_index=0) | source=llm
  HP 25->25 | Gold 86->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Expose strips the Queen's block and applies Vulnerable, fulfilling the turn plan to set up damage while leaving enough energy to defend against the Amalgam.
  strategic_note: Committed shiv/poison plan: Play cheap attacks to stack poison via Envenom and scale with Accuracy. Prioritize defensive cards and use Expose to strip block when necessary. Maintain block via Apparitions and high-value block cards while poison kills.

F48 [card_select] select_deck_card (option_index=0) | source=llm
  HP 23->23 | Gold 86->0 | Deck 35->35
  deck_change: no deck change
  reasoning: We used a Skill potion looking for Apparition or high-impact block to survive 24 incoming damage. None of the generated cards provide sufficient immediate mitigation, so Calculated Gamble is the best choice to cycle our hand and dig through the deck for an Apparition or better defensive cards.

## Selected Replay Package (3 replays)
[Selected: boss] multi:Crusher+Rocket (F33, boss)
Historical: loss=14 vs historical avg=36.0+/-15.9 (z=-1.4, BETTER_THAN_USUAL, n=33)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Neow's Talisman, The Chosen Cheese, Joss Paper, Ripple Basin, Meal Ticket, Pumpkin Candle, Mr. Struggles, Blood Vial, Gorget, Gnarled Hammer, Centennial Puzzle
Deck (25): Defend x4, Leading Strike x2, Strike x2, Ascender's Bane, Blade Dance, Calculated Gamble+, Cloak and Dagger, Dagger Throw, Defend+, Deflect, Dodge and Roll, Expose, Fan of Knives, Finisher, Footwork+, Neutralize, Predator+, Secret Technique, Survivor, Up My Sleeve
Enemies: Crusher HP=218/219, Rocket HP=208/209

### Round 1
Agent plan (hypothesis): We took a small hit to trigger Centennial Puzzle. Focus fire on one to break the Surrounded debuff soon, but be ready for Crab Rage.
Agent plan (hypothesis): Centennial Puzzle will trigger next turn, giving 3 extra cards.
Intent: Crusher: Attack(18), Rocket: Attack(3)
  turn_end
    block +4

### Round 2
Agent plan (hypothesis): Turn 4 is the massive incoming damage turn (Rocket attacks for 49). Save the Block potion for that turn. Next turn, use Liquid Memories on Finisher or Blade Dance to maximize damage and try to kill Rocket before he attacks on Turn 4.
Agent plan (hypothesis): We will draw heavily next turn due to Puzzle + Predator + normal draw. Be prepared for a large hand. Save Block Potion for Turn 4.
Intent: Crusher: Attack(4), Rocket: Attack(27)
  Cloak and Dagger
  turn_end
    block +3

### Round 3
Agent plan (hypothesis): Save Block Potion for Turn 4 when Rocket attacks for 49.
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Liquid Memories
  Blade Dance
  Predator+
  turn_end
    block +2

### Round 4
Intent: Crusher: Buff, Rocket: Attack(33)
  Block Potion
    block +12
  turn_end
    block +1

### Round 5
Agent plan (hypothesis): Rocket should be in range soon; keep prioritizing lethal on Rocket when possible, but always end facing the current attacker until Surrounded is broken.
Agent plan (hypothesis): Use Gamble next turn if draw is bad. Continue focusing Rocket down.
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  turn_end

### Round 6
Agent plan (hypothesis): Continue focusing Rocket down while managing facing.
Intent: Crusher: Attack(14), Rocket: Attack(7)
  Defend
  turn_end

### Round 7
Agent plan (hypothesis): Rocket is dead, Surrounded is broken. Time to chew through 99 Block and kill Crusher.
Agent plan (hypothesis): Up My Sleeve cost reduced. Keep chewing through the 99 block.
Intent: Crusher: Attack(6), Rocket: Attack(30)
  turn_end

### Round 8
Intent: Crusher: Attack(14x2=28), Debuff
  turn_end

### Round 9
Agent plan (hypothesis): See what Joss Paper draws before spending the last energy.
Agent plan (hypothesis): Crusher will attack next turn with massive strength. Prioritize block and finish him off.
Intent: Crusher: Buff
  turn_end

### Round 10
Agent plan (hypothesis): If we draw a damage card, we can finish Crusher. Otherwise, play out the remaining Defend.
Agent plan (hypothesis): Act 2 Boss defeated!
Intent: Crusher: Attack(22), Defend
  Defend
## Combat Analytics: multi:Crusher+Rocket (WIN - 10 rounds)

Active powers: Plating(4), Surrounded(1)

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:1 -> R10:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:8 -> R9:8 -> R10:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:-
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-

Unattributed damage (power/passive effects): 333
  Per round: R1:57 R2:49 R3:69 R4:24 R5:24 R6:21 R7:11 R8:44 R9:27 R10:7
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper, Pandora's Box, Bag of Marbles
Deck (25): Afterimage, Anticipate, Backflip, Backstab, Calculated Gamble, Corrosive Wave, Dagger Spray, Dagger Throw, Dodge and Roll+, Envenom+, Exterminate, Fan of Knives, Flick-Flack, Knife Trap, Leading Strike, Leading Strike+, Leg Sweep, Neutralize+, Phantom Blades, Piercing Wail, Ricochet, Storm of Steel, Strangle, Survivor, Tracking+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  turn_end

### Round 2
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Vulnerable Potion -> Rocket[1]
    enemy_deltas: Rocket: +Vulnerable(3)
  Poison Potion -> Rocket[1]
    enemy_deltas: Rocket: +Poison(6)
  turn_end

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Flick-Flack
  turn_end

### Round 4
Intent: Crusher: Buff, Rocket: Attack(49)
  Corrosive Wave
  turn_end

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  turn_end

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  turn_end

### Round 7
Intent: Crusher: Attack(9)
  turn_end

### Round 8
Intent: Crusher: Attack(14x2=28), Debuff
  turn_end

### Round 9
Intent: Crusher: Buff
  cards: Dagger Throw, dealt=0, taken=0
## Combat Analytics: multi:Crusher+Rocket (WIN - 9 rounds)

Active powers: Surrounded(1)

Poison stacks applied per card:
  Poison Potion: 6 stacks
Total poison/power tick damage: 218
  Per round: R1:38 R2:34 R4:4 R5:52 R6:20 R7:4 R8:66

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1 -> R9:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:11 -> R4:- -> R5:15 -> R6:- -> R7:12 -> R8:15 -> R9:26
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:13 -> R7:- -> R8:- -> R9:-
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:14 -> R5:- -> R6:26 -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:8 -> R8:8 -> R9:8
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:- -> R8:- -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:- -> R8:- -> R9:-
  Vulnerable: R1:- -> R2:- -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:1 -> R6:- -> R7:1 -> R8:- -> R9:1

[Selected: run_combat] multi:Cubex Construct+Cubex Construct+Punch Construct (F43, monster)
Historical: loss=25 vs historical avg=7.5+/-10.9 (z=1.6, WORSE_THAN_USUAL, n=19)
## Combat Replay: vs multi:Cubex Construct+Cubex Construct+Punch Construct (Floor 43, monster)
Relics: Ring of the Snake, Neow's Talisman, The Chosen Cheese, Joss Paper, Ripple Basin, Meal Ticket, Pumpkin Candle, Mr. Struggles, Blood Vial, Gorget, Gnarled Hammer, Centennial Puzzle, Distinguished Cape, Fragrant Mushroom, Permafrost
Deck (32): Apparition x3, Defend x3, Defend+ x2, Leading Strike x2, Accuracy+, Ascender's Bane, Blade Dance, Calculated Gamble+, Cloak and Dagger, Dagger Throw, Deflect, Dodge and Roll, Dodge and Roll+, Envenom+, Expose, Fan of Knives, Finisher, Footwork+, Neutralize, Predator+, Secret Technique, Strike, Strike+, Survivor, Up My Sleeve, Well-Laid Plans+
Enemies: Punch Construct HP=59/60, Cubex Construct HP=69/70, Cubex Construct HP=69/70

### Round 1
Intent: Punch Construct: Defend, Cubex Construct: Buff, Cubex Construct: Buff
  Swift Potion
  turn_end
    block +4

### Round 2
Intent: Punch Construct: Attack(14), Cubex Construct: Attack(9), Buff, Cubex Construct: Attack(9), Buff
  Blade Dance
  turn_end
    block +3
  Defend+
  Envenom+

### Round 3
Agent plan (hypothesis): Retain Footwork++ for next turn to scale block if needed.
Agent plan (hypothesis): Retain Footwork++ for next turn.
Agent plan (hypothesis): Retain Footwork+ and Envenom+ if possible.
Intent: Punch Construct: Attack(5x2=10), Debuff, Cubex Construct: Attack(11), Buff, Cubex Construct: Attack(11), Buff
  turn_end
    block +2
  Envenom+
  Footwork+

### Round 4
Agent plan (hypothesis): Retain Footwork or Calculated Gamble.
Intent: Punch Construct: Defend, Cubex Construct: Attack(11x2=22)
  turn_end
    block +1
  Dodge and Roll+
  Leading Strike

### Round 5
Intent: Punch Construct: Attack(14)
  cards: Leading Strike, Shiv, Shiv, Predator+, dealt=21, taken=0
## Combat Analytics: multi:Cubex Construct+Cubex Construct+Punch Construct (WIN - 5 rounds)

Active powers: Plating(4)

Enemy power timeline:
  Artifact: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1
  Artifact[0]: R1:1 -> R2:1 -> R3:1 -> R4:- -> R5:-
  Artifact[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Artifact[2]: R1:1 -> R2:1 -> R3:1 -> R4:- -> R5:-
  Strength: R1:- -> R2:- -> R3:- -> R4:6 -> R5:-
  Strength[1]: R1:- -> R2:2 -> R3:4 -> R4:- -> R5:-
  Strength[2]: R1:- -> R2:2 -> R3:4 -> R4:- -> R5:-

Unattributed damage (power/passive effects): 94
  Per round: R3:51 R4:22 R5:21
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Cubex Construct+Cubex Construct+Punch Construct (Floor 44, monster)
Relics: Ring of the Snake, Leafy Poultice, Strike Dummy, Bellows, Runic Pyramid, Bronze Scales, Jeweled Mask, Bag of Preparation
Deck (34): Defend x4, Blade Dance x3, Backflip x2, Blade Dance+ x2, Cloak and Dagger x2, Strike x2, Accuracy+, Adrenaline+, Ascender's Bane, Blur, Calculated Gamble+, Dagger Spray, Escape Plan, Finisher, Footwork+, Hidden Daggers+, Leading Strike, Mad Science, Master of Strategy+, Neutralize, Piercing Wail, Pinpoint+, Purity, Slice, Survivor
Enemies: Punch Construct HP=55/55, Cubex Construct HP=65/65, Cubex Construct HP=65/65

### Round 1
Intent: Punch Construct: Defend, Cubex Construct: Buff, Cubex Construct: Buff
  Ascender's Bane
  Defend+
  confirm
    exhausted: Shiv*2 [0费]：Deal 4 damage. Exhaust.
  turn_end

### Round 2
Intent: Punch Construct: Attack(14), Cubex Construct: Attack(9), Buff
  turn_end

### Round 3
Intent: Punch Construct: Attack(5x2=10), Debuff
  turn_end

### Round 4
Intent: Punch Construct: Defend
  cards: Slice, Strike, dealt=4, taken=0
## Combat Analytics: multi:Cubex Construct+Cubex Construct+Punch Construct (WIN - 4 rounds)

Active powers: Thorns(3)

Enemy power timeline:
  Artifact: R1:- -> R2:- -> R3:1 -> R4:1
  Artifact[0]: R1:1 -> R2:1 -> R3:- -> R4:-
  Artifact[1]: R1:1 -> R2:1 -> R3:- -> R4:-
  Artifact[2]: R1:1 -> R2:- -> R3:- -> R4:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:-

Unattributed damage (power/passive effects): 107
  Per round: R1:20 R2:45 R3:38 R4:4

[Selected: boss, death] multi:Queen+Torch Head Amalgam (F48, boss)
Historical: loss=38 vs historical avg=38.7+/-18.4 (z=-0.0, TYPICAL, n=14)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Neow's Talisman, The Chosen Cheese, Joss Paper, Ripple Basin, Meal Ticket, Pumpkin Candle, Mr. Struggles, Blood Vial, Gorget, Gnarled Hammer, Centennial Puzzle, Distinguished Cape, Fragrant Mushroom, Permafrost, Twisted Funnel, Regal Pillow
Deck (35): Defend x3, Apparition x2, Blade Dance x2, Defend+ x2, Leading Strike x2, Accuracy+, Apparition+, Ascender's Bane, Backflip, Calculated Gamble+, Cloak and Dagger+, Dagger Throw, Deflect, Dodge and Roll, Dodge and Roll+, Envenom+, Expose, Fan of Knives, Finisher, Footwork+, Neutralize, Predator+, Regret, Secret Technique, Strike, Strike+, Survivor, Up My Sleeve, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=210/211, Queen HP=418/419

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  turn_end
    block +4
  Finisher
  Dagger Throw

### Round 2
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  turn_end
    block +3
  Finisher
  Backflip

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  turn_end
    block +2
  Leading Strike
  Dodge and Roll+

### Round 4
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  Expose
  turn_end
    block +1
  Dodge and Roll
  Defend

### Round 5
Intent: Torch Head Amalgam: Attack(24), Queen: Buff, Defend
  Skill Potion
  Calculated Gamble
  Speed Potion
    Dexterity(3→8) | +Speed Potion(5)
  turn_end
  Dodge and Roll+
  Finisher

### Round 6
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  Strike+
  turn_end
  Fan of Knives
  confirm

### Round 7
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  turn_end
  Leading Strike
  Defend+
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 7 rounds)
Death cause: Died with HP=7, damage_taken=0. Likely mechanic kill.

Active powers: Plating(4)

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Poison[0]: R1:4 -> R2:3 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:-
  Poison[1]: R1:4 -> R2:3 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:-

Unattributed damage (power/passive effects): 201
  Per round: R1:20 R2:30 R3:36 R4:20 R5:14 R6:8 R7:73
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Hefty Tablet, Eternal Feather, Whetstone, Calling Bell, Red Mask, Petrified Toad, Bellows, Burning Sticks, Ornamental Fan, Tuning Fork, Girya, War Paint, Jeweled Mask, Tingsha, Lasting Candy, Potion Belt, Prayer Wheel, Pendulum
Deck (39): Defend x3, Backflip+ x2, Defend+ x2, Piercing Wail x2, Strike+ x2, Acrobatics+, Adrenaline+, Ascender's Bane, Backstab, Blade Dance, Blade Dance+, Cloak and Dagger+, Curse of the Bell, Dagger Throw, Dash, Dodge and Roll, Expertise, Finisher, Flick-Flack, Flick-Flack+, Footwork+, Master of Strategy, Neutralize+, Noxious Fumes, Phantom Blades, Serpent Form+, Shadowmeld+, Storm of Steel, Strike, Survivor, Ultimate Strike, Up My Sleeve, Well-Laid Plans
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(13), Queen: CardDebuff
  Strength Potion
    Strength(1→3)
  turn_end
    exhausted: Shiv*4 [0费]：Retain. Deal 4 damage. Exhaust.

### Round 2
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(9x3=27), Queen: Buff, Defend
  turn_end

### Round 4
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  turn_end

### Round 5
Intent: Torch Head Amalgam: Attack(24), Queen: Buff, Defend
  Explosive Ampoule
    enemy_deltas: Torch Head Amalgam: DIED; Queen: block -10
  turn_end

### Round 6
Intent: Queen: Attack(7x5=35)
  turn_end

### Round 7
Intent: Queen: Attack(25)
  Potion-Shaped Rock -> Queen[0]
    enemy_deltas: Queen: hp -15
  Fortifier
    block +120
  turn_end

### Round 8
Intent: Queen: Buff
  Flick-Flack
  turn_end

### Round 9
Intent: Queen: Attack(10x5=50)
  cards: Strike+, Ultimate Strike, Finisher, dealt=33, taken=0
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 9 rounds)

Active powers: Strength(1)

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:11 -> R7:13 -> R8:15 -> R9:17
  Poison[0]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison[1]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:- -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-

Unattributed damage (power/passive effects): 468
  Per round: R1:56 R2:61 R3:34 R4:32 R5:60 R6:52 R7:66 R8:74 R9:33

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F33(Crusher: WIN), F48(Torch Head Amalgam: )
- Core Combat Principles: F31(Myte: WIN), F33(Crusher: WIN), F35(Devoted Sculptor: WIN), F39(Living Shield: WIN), F43(Punch Construct: WIN), F46(Globe Head: WIN), F48(Torch Head Amalgam: )
- Deck Building Across the Run: F30(), F30(), F31(), F31(), F33(), F33(), F33(), F35(), F35(), F38(), F39(), F39(), F43(), F43(), F46(), F46(), F48(), F48()
- Map Routing and Path Planning: F30(), F30(), F34(), F34(), F35(), F35(), F36(), F37(), F39(), F41(), F42(), F43(), F44()
- Never Smith Upgraded Cards: F32(), F40(), F42(), F44(), F47()
- Rest Site and Event Decisions: F32(), F40(), F42(), F44(), F47()
- Silent - Combat Sequencing: F31(Myte: WIN), F33(Crusher: WIN), F35(Devoted Sculptor: WIN), F39(Living Shield: WIN), F43(Punch Construct: WIN), F46(Globe Head: WIN), F48(Torch Head Amalgam: )
- Silent - Draft and Shop Rules: F30(), F30(), F31(), F31(), F33(), F33(), F33(), F35(), F35(), F38(), F39(), F39(), F43(), F43(), F46(), F46(), F48(), F48()
- Silent - Route Priorities: F30(), F30(), F34(), F34(), F35(), F35(), F36(), F37(), F39(), F41(), F42(), F43(), F44()
- Sly Discard Synergies: F30(), F31(), F33(), F35(), F38(), F39(), F43(), F46()

## Dynamic Tools
- block_sufficiency_check: 21007 calls, 21007 successes
- poison_block_survival_plan: 5960 calls, 5960 successes
- poison_kill_and_survive_check: 20460 calls, 20460 successes
- poison_survival_analysis: 22870 calls, 21773 successes
- poison_turns_to_kill: 22913 calls, 21773 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.