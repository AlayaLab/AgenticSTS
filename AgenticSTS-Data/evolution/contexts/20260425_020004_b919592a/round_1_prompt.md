# Evolution System Prompt

You are a self-evolving Slay the Spire 2 agent. You just completed a run and are now analyzing your performance to improve for future runs.

Your goal: identify your WORST mistakes and create tools or skills that would have prevented them. Focus on concrete, actionable improvements.

Guidelines:
- Create a Python tool (author_tool) when you need a CALCULATION (damage math, lethal checks, energy optimization, poison stacking, etc.)
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, boss patterns, deck building heuristics, etc.)
- Update a guide (update_guide) when existing knowledge is WRONG or INCOMPLETE
- Update a card note (update_card_note) to write an experience-based evaluation for a card. Prioritize cards without existing notes in the Card Notes section. Base your note on: (1) The card's rules_text from the Card Mechanics Reference, (2) Observable combat outcomes from the Combat Digest, (3) Keyword interactions deducible from card descriptions, (4) Act death correlations from Card Memory Stats. Evidence thresholds: mechanic discoveries can be low-sample if grounded in rules_text; tier ratings and take/skip guidance require >=10 plays AND act death data. Do NOT write notes for generated/status cards (Shiv, Burn, Slimed, Wound). Only write discoveries logically derivable from card descriptions and gameplay evidence.
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

READ-ONLY DIAGNOSTIC PHASE:
- You are in diagnosis mode.
- You MUST call at least one read/query tool this round.
- Do not attempt to write or mutate memory in this phase.
- Build a concrete problem list first, then gather evidence.


# Round 1 User Context

You just completed a Slay the Spire 2 run as the silent.
Result: VICTORY (fitness: 235.5)
Combats won: 14/14
Run duration: 7169.7s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F14
- [card_select] Committed shiv plan: play Phantom Blades early to buff the first shiv each turn and retain the rest. Use Knife Trap as a burst finisher once enough shivs have exhausted. Focus on drafting more shiv generation, card draw, and energy. Remove remaining Strikes as they dilute the engine.
- [map] Foundation deck focusing on early monster rewards; currently seeking a primary damage engine like Poison or Shivs while prioritizing upgrades at rest sites to maintain momentum into Act 2.
### F15
- [card_reward] Foundation plan: Use Shivs and Phantom Blades for frontload and stripping Vantom's Slippery, while Corrosive Wave + Calculated Gamble serves as a scaling poison engine. Prioritize Acrobatics and draw to fuel Corrosive Wave.
### F16
- [rest_site] Committed Shiv/Poison hybrid: generate Shivs and Retain them with Phantom Blades, then burst damage with Knife Trap or stack poison with Corrosive Wave plus draw. Needs more Shiv generation and reliable block. Avoid adding raw basic attacks.
### F17
- [card_select] Committed shiv plan: use Phantom Blades and shiv generators to output damage. Look for Cloak and Dagger, Blade Dance, Accuracy, and card draw (Acrobatics) to fuel the zero-cost engine. Focus on surviving with efficient block and avoiding expensive cards.
- [card_reward] Committed shiv plan: use Phantom Blades and Fan of Knives to clear hallways, building up exhaust pile for massive Knife Trap finishes. Look for Accuracy or Finisher for boss scaling, and efficient Block to survive.
### F18
- [event] Foundation deck focusing on shivs and cycling (Fan of Knives, Phantom Blades). Needs solid scaling attacks or block to round out the engine. Pandora's Box will provide a massive influx of cards to guide our direction.
- [map] Foundation deck seeking a primary damage engine; prioritize hallway fights early in Act 2 to find Poison or Shiv synergies while preserving HP for upgrades.
### F19
- [card_reward] Committed Shiv/Poison plan: play Envenom and Phantom Blades, generate Shivs to stack poison and burst damage, then finish with Knife Trap. Look for Blade Dance, Cloak and Dagger, Accuracy, and efficient draw; skip generic or low-impact cards.
### F20
- [card_reward] Committed Shiv/Poison hybrid: retain Shiv generators, draw to cycle to Envenom/Strangle, and rely on Afterimage for defense. Focus on finding Accuracy, draw (Acrobatics/Adrenaline), and energy. Skip generic attacks and block cards.
- [map] Foundation deck seeking a primary damage engine; prioritize events and shops in Act 2 to find Poison or Shiv synergies while preserving HP for critical upgrades.
### F21
- [event] Committed poison/multi-hit plan: use Envenom and Fan of Knives to scale poison rapidly through multi-hit attacks. Exterminate is a key AoE poison applicator. Prioritize upgrading Envenom and Exterminate, and draft cheap defensive tools to survive while poison scales.
### F22
- [card_reward] Committed Shiv/Poison hybrid: use Shivs to trigger Envenom, Strangle, Afterimage, and Joss Paper, then finish with Knife Trap. Focus on burst damage and draw to outpace boss scaling.
- [map] Foundation deck seeking a primary damage engine; prioritizing shops and events in Act 2 to find Poison or Shiv synergies while using gold for removals or high-impact relics.
### F23
- [map] Foundation deck seeking a primary damage engine; prioritizing events and non-combat nodes in Act 2 to preserve HP while looking for a win condition like Poison or Shivs.
### F24
- [event] Committed poison/multi-hit plan: use Envenom and Fan of Knives to scale poison rapidly through multi-hit attacks. Survive with Afterimage and defend cards.
### F25
- [rest_site] Committed shiv-power hybrid deck: set up powers like Tracking, Phantom Blades, and Envenom, then unleash shivs and AoE attacks. Needs more reliable Weak application to maximize Tracking and maybe some extra energy generation.
- [map] Foundation deck seeking a primary damage engine; prioritizing shops and events in Act 2 to find Poison or Shiv synergies while using gold for removals or high-impact relics.
### F27
- [card_reward] Committed to shiv and poison scaling via Envenom. Prioritize Accuracy, draw (Acrobatics, Adrenaline), and energy generators. For the Act 2 Boss, focus fire one enemy to break Surrounded. Keep the deck lean to consistently draw core pieces.
### F28
- [card_reward] Committed shiv/poison burst plan: generate massive amounts of Shivs to stack poison via Envenom and load up the exhaust pile for a huge Knife Trap finish. Prioritize draw and energy to play more Shivs and powers; skip narrow or expensive off-plan cards.
### F29
- [rest_site] Committed shiv-poison power hybrid: set up Afterimage and Envenom+, then unleash Shivs and multi-hits to stack massive poison while generating block. Needs more reliable Weak or Block for the setup turns.
### F30
- [card_reward] Committed to Shiv/Poison hybrid with Envenom++. Use discard outlets to trigger Sly on Ricochet or cycle through to Shiv generators. Stack massive poison quickly on safe turns, defend, and let poison do the work. Avoid off-plan attacks and bloated cards.
- [map] Foundation deck transitioning into a Shiv or Poison engine; prioritize survival and card quality over risky Act 2 elites until a definitive win condition is upgraded.
### F31
- [card_reward] Committed to Envenom shiv scaling. Defend on heavy attack turns, then spam attacks/shivs when safe to stack poison and burst. Need more card draw and shiv generators.
### F32
- [rest_site] Committed shiv-poison power hybrid: set up Afterimage and Envenom+, then unleash Shivs and multi-hits to stack massive poison while generating block. Needs more reliable Weak or Block for the setup turns.
### F33
- [card_reward] Committed to Shiv/Poison hybrid with Envenom++ and Sly mechanics. Tools of the Trade enables passive triggers for Flick-Flack/Ricochet. Focus on playing powers early and using Shiv generators to apply massive poison via Envenom. Need energy generation or 0-cost draw.
### F34
- [event] Foundation: Multi-hit attacks with Envenom and Phantom Blades for scaling damage, relying on Afterimage and Dodge and Roll for block. Need more card draw or a 4th energy to play powers faster. Path aggressively into Elites in Act 3 thanks to Fur Coat, saving campfires to upgrade key powers.
- [map] Foundation deck focusing on Shiv and Poison flexibility; prioritizing safe hallway fights and early shops to refine the engine before committing to a final damage scaling plan.
### F35
- [card_select] Committed Shiv/Attack spam engine: scale with Phantom Blades, Afterimage, and Fan of Knives, using cheap attacks and Shivs. Prioritize draw and energy to fuel the engine; we have plenty of damage and passive block scaling now.
- [hand_select] Using Sly cards as discard targets is a high-value interaction that saves energy and increases tempo.
- [card_reward] Committed to Shiv/Poison hybrid. Play Tools of the Trade, Envenom, and Phantom Blades early, then use Shivs and Sly cards for passive scaling damage while defending with Afterimage.
### F36
- [card_reward] Committed to Shiv/Poison hybrid. Use Shiv generators like Fan of Knives and Leading Strike to stack poison via Envenom and scale physical damage via Accuracy. Defend passively with Afterimage while spamming attacks. We have enough damage engines; prioritize draw and mitigation for bad turns.
- [map] Foundation Shiv/Poison hybrid: currently low HP in Act 3, prioritizing survival through shops and rest sites over elites. Need to find more reliable block or a 'Wraith Form' to stabilize while shivs and poison scale damage. Avoid unnecessary combats until HP is above 50.
### F38
- [event] Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal the event damage using Regal Pillow.
### F40
- [event] Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.
### F42
- [rest_site] Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Fan of Knives) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.
### F43
- [event] Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Accept curses from Act 3 events only if the reward scales our endgame.
- [event] Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.
- [card_select] Committed shiv/poison plan: cycle into shiv generators (Storm of Steel, Fan of Knives) while stacking powers (Accuracy, Envenom, Afterimage). Use Corrosive Wave and Strangle for massive extra scaling.
### F44
- [rest_site] Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Afterimage) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.
### F45
- [event] Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Needs to find a swift and safe way to deploy powers.
- [card_select] Committed Shiv/Poison hybrid: setup Afterimage and Phantom Blades/Accuracy early, then spam retained Shivs to stack Envenom poison and generate block. Use Tracking to double Shiv damage on weak targets.
### F46
- [card_reward] Committed Shiv/Poison hybrid: generate shivs to trigger Envenom+Snecko Skull and Afterimage. Keep deck cycling fast to find key powers early.
### F47
- [rest_site] Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Afterimage) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.
### F48
- [hand_select] Discarding the curse is the highest value use of Tools of the Trade here.
- [hand_select] Prioritizing poison scaling with Envenom++ over defensive block while Frail.

### Combat Decision Digest (14 combats)
F15 [elite] Phrog Parasite (8R, HP 59->44, loss=15, WIN)
  R1[Phrog Parasite: StatusCard(3)]: Phantom Blades->Leading Strike->Shiv->Strike | dealt=22 taken=0
  R2[Phrog Parasite: Atk(4x4=16)]: Piercing Wail->Shiv->Neutralize+->Strike->Calculated Gamble->Defend | dealt=23 taken=0
  R3[Phrog Parasite: StatusCard(3)]: Backflip->Dagger Throw->Strike | dealt=6 taken=0
  R4[Phrog Parasite: Atk(4x4=16)]: Neutralize+->Survivor->Defend*2 | dealt=2 taken=0
  R5[Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)+Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)]: Leading Strike->Shiv*2->Defend*2 | dealt=0 taken=2
  R6[Wriggler: Atk(8)+Wriggler: Buff, StatusCard(1)+Wriggler: Atk(8)]: Knife Trap->Strike | dealt=2 taken=14
  R7[Wriggler: Buff, StatusCard(1)+Wriggler: Atk(8)]: Dagger Throw->Backflip->Neutralize+->Survivor | dealt=4 taken=0
  R8[Wriggler: Buff, StatusCard(1)]: Knife Trap | dealt=0 taken=0

F17 [boss] Vantom (8R, HP 74->46, loss=28, WIN)
  R1[Vantom: Atk(7)]: Leading Strike->Shiv*2->Neutralize+->Corrosive Wave->Backflip | dealt=4 taken=0
  R2[Vantom: Atk(4x2=8)]: Calculated Gamble->Phantom Blades->Survivor->Defend | dealt=0 taken=0
  R3[Vantom: Atk(27), StatusCard(3)]: Panache->Leading Strike->Shiv*2->Piercing Wail->Defend | dealt=13 taken=16
  R4[Vantom: Buff]: Neutralize+->Backflip->Knife Trap | dealt=39 taken=0
  R5[Vantom: Atk(6)]: Leading Strike->Shiv*2->Defend->Survivor | dealt=20 taken=0
  R6[Vantom: Atk(8x2=16)]: Neutralize+->Dagger Throw->Defend*2 | dealt=4 taken=2
  R7[Vantom: Atk(21), StatusCard(3)]: Backflip->Leading Strike->Shiv*2->Defend | dealt=30 taken=11
  R8[Vantom: Buff]: Neutralize+->Strike->Knife Trap | dealt=10 taken=0

F19 [monster] Tunneler (6R, HP 69->56, loss=13, WIN)
  R1[Tunneler: Atk(13)]: Backstab->Corrosive Wave->Backflip->Survivor | dealt=11 taken=0
  R2[Tunneler: Buff, Defend]: Neutralize+->Phantom Blades->Dagger Throw | dealt=4 taken=0
  R3[Tunneler: Atk(17)]: Afterimage->Corrosive Wave->Calculated Gamble->Anticipate->Dagger Throw | dealt=0 taken=13
  R4[Tunneler: Atk(23)]: Neutralize+->Piercing Wail->Survivor | dealt=0 taken=1
  R5[Tunneler: Atk(17)]: Strangle->Leading Strike->Backflip->Shiv*2 | dealt=17 taken=0
  R6[Tunneler: Atk(13)]: Corrosive Wave->Neutralize+->Dagger Throw->Anticipate->Dagger Spray | dealt=4 taken=0

F20 [monster] multi:Bowlbug (Nectar)+Bowlbug (Rock) (3R, HP 56->52, loss=4, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(3)]: Backstab->Phantom Blades->Backflip->Survivor | dealt=11 taken=5
  R2[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Buff]: Neutralize+->Dagger Spray->Dagger Throw->Tools of the Trade->Up My Sleeve->Shiv*3->Strangle->Anticipate->Calculated Gamble | dealt=58 taken=0
  R3[Bowlbug (Nectar): Atk(18)]: Dagger Throw | dealt=0 taken=0

F22 [monster] The Obscura (5R, HP 52->52, loss=0, WIN)
  R1[The Obscura: Summon]: Envenom->Backstab->Neutralize+->Exterminate | dealt=27 taken=0
  R2[Parafright: Atk(16)+The Obscura: Atk(4), Defend]: Corrosive Wave->Calculated Gamble->Afterimage->Leading Strike->Shiv*2 | dealt=11 taken=1
  R3[Parafright: Atk(16)+The Obscura: Atk(10)]: Phantom Blades->Leading Strike->Shiv*2->Survivor | dealt=20 taken=0
  R4[Parafright: Atk(16)+The Obscura: Atk(6), Defend]: Piercing Wail->Anticipate->Neutralize+->Backflip->Dagger Throw | dealt=4 taken=0
  R5[Parafright: Atk(12)+The Obscura: Atk(10)]: Fan of Knives->Shiv*2->Neutralize+->Exterminate->Shiv*2 | dealt=51 taken=0

F27 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (2R, HP 52->53, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Piercing Wail->Leading Strike->Backstab->Shiv*2->Anticipate->Calculated Gamble->Survivor | dealt=9 taken=0
  R2[Exoskeleton: Buff+Exoskeleton: Atk(3x3=9)+Exoskeleton: Buff]: Neutralize+->Fan of Knives->Shiv*4->Dagger Throw | dealt=15 taken=0

F28 [monster] Ovicopter (4R, HP 53->54, loss=0, WIN)
  R1[Ovicopter: Summon]: Backstab->Fan of Knives->Leading Strike+->Shiv*6->Calculated Gamble | dealt=61 taken=0
  R2[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(16)]: Anticipate->Backflip->Dagger Throw->Flick-Flack->Dagger Spray->Neutralize+->Piercing Wail | dealt=20 taken=0
  R3[Hatchling: Atk(4)+Ovicopter: Atk(5), Debuff]: Leading Strike+->Exterminate->Shiv*2->Survivor | dealt=41 taken=0
  R4[Ovicopter: Summon]: Neutralize+->Tracking+->Knife Trap | dealt=4 taken=0

F30 [monster] Louse Progenitor (6R, HP 54->52, loss=2, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Afterimage->Backstab->Fan of Knives->Shiv*4->Anticipate->Calculated Gamble | dealt=26 taken=1
  R2[Louse Progenitor: Defend, Buff]: Neutralize+->Exterminate->Knife Trap | dealt=32 taken=0
  R3[Louse Progenitor: Atk(14)]: Leg Sweep->Leading Strike->Shiv*2 | dealt=0 taken=2
  R4[Louse Progenitor: Atk(10), Debuff]: Leg Sweep->Tracking+ | dealt=0 taken=0
  R5[Louse Progenitor: Defend, Buff]: Anticipate->Neutralize+->Leading Strike->Shiv*2->Piercing Wail->Backflip | dealt=30 taken=0
  R6[Louse Progenitor: Atk(18)]: Leading Strike+->Shiv*2->Dagger Spray->Dagger Throw | dealt=30 taken=0

F31 [monster] multi:Bowlbug (Nectar)+Bowlbug (Rock)+Bowlbug (Silk) (2R, HP 52->53, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(3)+Bowlbug (Silk): Debuff]: Backstab->Envenom+->Exterminate->Calculated Gamble->Neutralize+ | dealt=70 taken=0
  R2[Bowlbug (Nectar): Buff+Bowlbug (Silk): Atk(4x2=8)]: Piercing Wail->Anticipate->Leading Strike->Leading Strike+->Shiv*4 | dealt=18 taken=0

F33 [boss] multi:Crusher+Rocket (9R, HP 82->45, loss=37, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Neutralize+->Backstab->Piercing Wail->Calculated Gamble->Envenom+ | dealt=38 taken=4
  R2[Crusher: Atk(3)+Rocket: Atk(27)]: Afterimage->Phantom Blades->Leading Strike+->Shiv*2 | dealt=34 taken=18
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Dagger Throw->Flick-Flack->Leg Sweep | dealt=0 taken=0
  R4[Crusher: Buff+Rocket: Atk(49)]: Anticipate->Backflip->Neutralize+->Dodge and Roll+->Survivor | dealt=4 taken=1
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Fan of Knives->Leading Strike+->Shiv*6 | dealt=52 taken=0
  R6[Crusher: Atk(14)+Rocket: Atk(7)]: Leading Strike->Shiv*2->Leg Sweep | dealt=20 taken=0
  R7[Crusher: Atk(9)]: Strangle->Corrosive Wave->Backflip | dealt=4 taken=1
  R8[Crusher: Atk(14x2=28), Debuff]: Tracking+->Neutralize+->Leading Strike+->Shiv*2->Dagger Spray | dealt=66 taken=14
  R9[Crusher: Buff]: Dagger Throw | dealt=0 taken=0

F35 [monster] multi:Living Shield+Turret Operator (6R, HP 75->55, loss=20, WIN)
  R1[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Backstab->Leading Strike+->Shiv*2->Leg Sweep | dealt=12 taken=5
  R2[Living Shield: Atk(6)+Turret Operator: Atk(2x5=10)]: Acrobatics->Flick-Flack->Dodge and Roll+->Tools of the Trade->Dagger Throw->Calculated Gamble->Ricochet | dealt=0 taken=10
  R3[Living Shield: Atk(6)+Turret Operator: Buff]: Strangle->Corrosive Wave->Anticipate->Neutralize+->Backflip | dealt=8 taken=0
  R4[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Piercing Wail->Tracking+->Leading Strike+->Shiv*2 | dealt=3 taken=0
  R5[Living Shield: Atk(6)+Turret Operator: Atk(4x5=20)]: Neutralize+->Fan of Knives->Shiv*4->Leading Strike->Shiv*2->Ricochet | dealt=38 taken=6
  R6[Living Shield: Atk(16), Buff]: none | dealt=0 taken=0

F36 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (4R, HP 55->29, loss=26, WIN)
  R1[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff]: Anticipate->Backstab->Flick-Flack->Ricochet | dealt=13 taken=24
  R2[Scroll of Biting: Buff+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Atk(7x2=14)]: Afterimage->Neutralize+->Piercing Wail->Survivor | dealt=0 taken=0
  R3[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(16)]: Strangle->Dodge and Roll+->Leading Strike->Shiv*2 | dealt=18 taken=3
  R4[Scroll of Biting: Buff]: Fan of Knives->Shiv*4->Exterminate | dealt=16 taken=0

F46 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (1R, HP 52->53, loss=0, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Backstab->Mad Science->Neutralize+->Expose->Storm of Steel+->Shiv+ | dealt=2 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (10R, HP 78->14, loss=64, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Backstab->Afterimage+->Calculated Gamble->Neutralize+->Phantom Blades->Backflip | dealt=40 taken=0
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Corrosive Wave->Mad Science->Tools of the Trade | dealt=0 taken=0
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Piercing Wail->Dodge and Roll+->Blade Dance->Shiv*3 | dealt=15 taken=0
  R4[Torch Head Amalgam: Atk(22)+Queen: Buff, Defend]: Envenom+->Neutralize+->Survivor->Flick-Flack | dealt=3 taken=0
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Backflip->Accuracy+->Leading Strike+->Shiv*2 | dealt=9 taken=7
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Mad Science->Neutralize+->Leading Strike+->Shiv*2->Corrosive Wave->Expose->Flick-Flack | dealt=28 taken=22
  R7[Torch Head Amalgam: Atk(20)+Queen: Buff, Defend]: Backflip->Leading Strike->Shiv*2->Noxious Fumes | dealt=23 taken=9
  R8[Torch Head Amalgam: Atk(28)+Queen: Buff, Defend]: Mad Science->Fan of Knives->Shiv*4->Flick-Flack | dealt=41 taken=0
  R9[Queen: Atk(7x5=35)]: Tracking+->Leading Strike->Storm of Steel+->Shiv+*4 | dealt=44 taken=27
  R10[Queen: Atk(25)]: Leading Strike+->Shiv*2->Knife Trap | dealt=166 taken=0

### Non-combat Decisions (157 decisions)
F13 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 81->81 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Unknown

F14 [shop] remove_card_at_shop | source=plan
  HP 59->59 | Gold 81->81 | Deck 17->17
  deck_change: no deck change
  reasoning: Shop plan [1/1]: Removing a Strike increases the consistency of finding our key block cards, draw, and Shiv synergies (Phantom Blades, Leading Strike, Piercing Wail) in time for Vantom's crucial turns.

F14 [card_select] select_deck_card (option_index=0) | source=llm
  HP 59->59 | Gold 81->6 | Deck 17->16
  deck_change: lost Strike
  reasoning: Removing basic Strikes is standard to improve draw consistency. We have a clear Shiv engine with Phantom Blades and Knife Trap, so Strikes just get in the way of our core synergy.
  strategic_note: Committed shiv plan: play Phantom Blades early to buff the first shiv each turn and retain the rest. Use Knife Trap as a burst finisher once enough shivs have exhausted. Focus on drafting more shiv generation, card draw, and energy. Remove remaining Strikes as they dilute the engine.

F14 [shop] close_shop_inventory | source=llm
  HP 59->59 | Gold 6->6 | Deck 16->16
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F14 [shop] proceed | source=auto
  HP 59->59 | Gold 6->6 | Deck 16->16
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F14 [map] choose_map_node (option_index=1) | source=llm
  HP 59->59 | Gold 6->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Following the recommended route to the Elite. With 59/73 HP and a decent start, taking an Elite before the final Rest Site and Boss is the best way to secure a relic and a rare card to scale for Act 2. The Rest Site immediately follows this node, providing a safety net if the fight goes poorly.
  strategic_note: Foundation deck focusing on early monster rewards; currently seeking a primary damage engine like Poison or Shivs while prioritizing upgrades at rest sites to maintain momentum into Act 2.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 6->38 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 32 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 38->38 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 38->38 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim relic: Joss Paper

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 38->38 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 44->44 | Gold 38->38 | Deck 16->17
  deck_change: picked Corrosive Wave
  reasoning: Corrosive Wave is a premium rare scaling engine. With Calculated Gamble and Backflip already in the deck, it can provide massive AoE poison immediately. It also ignores Vantom's Slippery mechanic. While we have some Shiv cards, Corrosive Wave is too strong to pass up and synergizes well with any future draw we draft.
  strategic_note: Foundation plan: Use Shivs and Phantom Blades for frontload and stripping Vantom's Slippery, while Corrosive Wave + Calculated Gamble serves as a scaling poison engine. Prioritize Acrobatics and draw to fuel Corrosive Wave.

F15 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 44->44 | Gold 38->38 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 44->44 | Gold 38->38 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 44->74 | Gold 38->38 | Deck 17->17
  deck_change: no deck change
  reasoning: We are about to face the Act 1 Boss and are missing 30 HP. Resting with Regal Pillow will heal us to full HP, giving us maximum survivability which outweighs the benefit of a single upgrade at this stage.
  strategic_note: Committed Shiv/Poison hybrid: generate Shivs and Retain them with Phantom Blades, then burst damage with Knife Trap or stack poison with Corrosive Wave plus draw. Needs more Shiv generation and reliable block. Avoid adding raw basic attacks.

F16 [rest_site] proceed | source=auto
  HP 74->74 | Gold 38->38 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 74->74 | Gold 38->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [card_select] select_deck_card (option_index=0) | source=llm
  HP 74->74 | Gold 38->0 | Deck 17->17
  deck_change: no deck change
  reasoning: None of the colorless options provide direct block for the incoming attack. Panache costs 0 energy, meaning it won't interfere with playing defensive cards this turn, and it scales very well with our Phantom Blades/Shiv setup.
  strategic_note: Committed shiv plan: use Phantom Blades and shiv generators to output damage. Look for Cloak and Dagger, Blade Dance, Accuracy, and card draw (Acrobatics) to fuel the zero-cost engine. Focus on surviving with efficient block and avoiding expensive cards.

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 38->113 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 113->113 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 46->46 | Gold 113->113 | Deck 17->18
  deck_change: picked Fan of Knives
  reasoning: Fan of Knives perfectly fits our developing Shiv engine. It provides incredible AoE for Act 2 hallway fights and Elites, feeds Knife Trap with 4 exhausted Shivs, triggers Joss Paper draw via Exhaust, and synergizes heavily with Phantom Blades.
  strategic_note: Committed shiv plan: use Phantom Blades and Fan of Knives to clear hallways, building up exhaust pile for massive Knife Trap finishes. Look for Accuracy or Finisher for boss scaling, and efficient Block to survive.

F17 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 46->46 | Gold 113->113 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 46->69 | Gold 113->113 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=deck_building) | source=llm
  HP 69->69 | Gold 113->113 | Deck 18->18
  deck_change: changed: +Afterimage, Anticipate, Backstab, Dagger Spray, Envenom, Strangle, Tracking; -Defend x5, Strike x2
  reasoning: Transforming 7 basic cards with Pandora's Box will drastically increase the overall power and synergy of the deck, offering massive transformation which is much stronger than removing 2 cards or adding a single Wraith Form+.
  strategic_note: Foundation deck focusing on shivs and cycling (Fan of Knives, Phantom Blades). Needs solid scaling attacks or block to round out the engine. Pandora's Box will provide a massive influx of cards to guide our direction.

F18 [cards_view] confirm_selection | source=heuristic
  HP 69->69 | Gold 113->113 | Deck 18->18
  deck_change: no deck change
  reasoning: Confirm cards view

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 69->69 | Gold 113->113 | Deck 18->18
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=0) | source=llm
  HP 69->69 | Gold 113->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Starting Act 2 with a high HP total (69/75), I need to follow the prescribed route to find a primary damage engine. The deck currently lacks a committed win condition (Shivs/Poison/Discard), so taking early hallway fights to see card rewards is the highest priority before the mid-act shops and events.
  strategic_note: Foundation deck seeking a primary damage engine; prioritize hallway fights early in Act 2 to find Poison or Shiv synergies while preserving HP for upgrades.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 113->125 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 125->125 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Orobic Acid

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 125->125 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 56->56 | Gold 125->125 | Deck 18->18
  deck_change: no deck change
  reasoning: The deck is leaning into a strong Shiv/Poison hybrid with Envenom, Phantom Blades, and Knife Trap. None of the offered cards significantly improve the deck's scaling or defense. Skipping keeps the deck lean to draw our core powers and shiv generators faster.
  strategic_note: Committed Shiv/Poison plan: play Envenom and Phantom Blades, generate Shivs to stack poison and burst damage, then finish with Knife Trap. Look for Blade Dance, Cloak and Dagger, Accuracy, and efficient draw; skip generic or low-impact cards.

F19 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 56->56 | Gold 125->125 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 125->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 125->135 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 135->135 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 52->52 | Gold 135->135 | Deck 18->18
  deck_change: no deck change
  reasoning: The deck is committed to a Shiv/Poison engine with Envenom, Fan of Knives, Phantom Blades, and Knife Trap. None of the offered cards strongly support this engine. Pounce lacks expensive Skills to discount, we already have Anticipate, and Flick-Flack is unneeded AoE. Skipping to keep the deck lean.
  strategic_note: Committed Shiv/Poison hybrid: retain Shiv generators, draw to cycle to Envenom/Strangle, and rely on Afterimage for defense. Focus on finding Accuracy, draw (Acrobatics/Adrenaline), and energy. Skip generic attacks and block cards.

F20 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 52->52 | Gold 135->135 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F20 [map] choose_map_node (option_index=1) | source=llm
  HP 52->52 | Gold 135->135 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. Act 2 hallway fights are notoriously difficult and tax HP heavily; taking an Unknown node provides a chance for a high-value event or a shop/treasure while minimizing chip damage before the guaranteed shop and rest site sequence.
  strategic_note: Foundation deck seeking a primary damage engine; prioritize events and shops in Act 2 to find Poison or Shiv synergies while preserving HP for critical upgrades.

F21 [event] choose_event_option (option_index=0) | source=llm
  HP 52->52 | Gold 135->135 | Deck 18->19
  deck_change: added Exterminate
  reasoning: Exterminate is a fantastic 4-hit AoE attack. Since we have Envenom, a 4-hit attack will apply 4 Poison to ALL enemies for just 1 energy, making it an incredibly powerful synergy for our deck.
  strategic_note: Committed poison/multi-hit plan: use Envenom and Fan of Knives to scale poison rapidly through multi-hit attacks. Exterminate is a key AoE poison applicator. Prioritize upgrading Envenom and Exterminate, and draft cheap defensive tools to survive while poison scales.

F21 [event] choose_event_option (option_index=0) | source=auto
  HP 52->52 | Gold 135->135 | Deck 19->19
  deck_change: no deck change
  reasoning: Only option: Proceed

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 135->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 135->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Cure All

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=deck_building) | source=llm
  HP 52->52 | Gold 150->150 | Deck 19->20
  deck_change: picked Leading Strike+
  reasoning: Leading Strike++ increases our Shiv density, which synergizes incredibly well with our current engine: Envenom, Strangle, Knife Trap, Afterimage, and Joss Paper (draw on exhaust). For the upcoming Act 2 boss, we need high-burst single-target damage to kill one quickly, making a frontloaded Shiv generator much more valuable than the slow AoE scaling of Noxious Fumes.
  strategic_note: Committed Shiv/Poison hybrid: use Shivs to trigger Envenom, Strangle, Afterimage, and Joss Paper, then finish with Knife Trap. Focus on burst damage and draw to outpace boss scaling.

F22 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 52->52 | Gold 150->150 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F22 [map] choose_map_node (option_index=1) | source=llm
  HP 52->52 | Gold 150->150 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the recommended route to the Shop at (c3, r5). With 150 gold, I can afford a card removal, a strong relic, or a key engine-defining card. This aligns with the strategy of stabilizing in Act 2 through shops and events rather than taking risky Elite fights.
  strategic_note: Foundation deck seeking a primary damage engine; prioritizing shops and events in Act 2 to find Poison or Shiv synergies while using gold for removals or high-impact relics.

F23 [shop] buy_card (option_index=2) | source=plan
  HP 52->52 | Gold 150->74 | Deck 20->21
  deck_change: bought Leg Sweep
  reasoning: Shop plan [1/3]: Provides much needed Weak to enable Tracking (double damage on attacks), while also offering premium block.

F23 [shop] buy_card (option_index=0) | source=plan
  HP 52->52 | Gold 74->50 | Deck 21->22
  deck_change: bought Flick-Flack
  reasoning: Shop plan [2/3]: On sale. We have Calculated Gamble, Survivor, and Dagger Throw to trigger its Sly effect for free AoE damage.

F23 [shop] buy_potion (option_index=1) | source=plan
  HP 52->52 | Gold 50->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan [3/3]: Excellent emergency defense for the upcoming Act 2 boss, fully utilizing our remaining gold.

F23 [shop] close_shop_inventory | source=plan
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F23 [shop] proceed | source=auto
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F23 [map] choose_map_node (option_index=1) | source=llm
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node to avoid Act 2 Elites. My current gold is nearly zero, so avoiding the Elite to preserve HP for the upcoming boss and rest sites is the safer play, adhering to the strategy of event chaining in Act 2.
  strategic_note: Foundation deck seeking a primary damage engine; prioritizing events and non-combat nodes in Act 2 to preserve HP while looking for a win condition like Poison or Shivs.

F24 [event] choose_event_option (option_index=0) | source=llm
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Foul Potions provide huge economic value. They can be sold to a merchant for 100 gold each, which is massive since we currently have only 1 gold. If needed, we can also use them for 12 AoE damage, provided we have the HP to spare.
  strategic_note: Committed poison/multi-hit plan: use Envenom and Fan of Knives to scale poison rapidly through multi-hit attacks. Survive with Afterimage and defend cards.

F24 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F24 [event] choose_event_option (option_index=0) | source=auto
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Only option: Proceed

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: RestSite

F25 [rest_site] choose_rest_option (option_index=1, smith_card_index=10) | source=llm
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: upgraded Tracking->Tracking+
  reasoning: HP is healthy enough (67%) to Smith, especially with no fights until Floor 30. Tracking's cost reduction from 2 to 1 energy is massive for getting our key damage multiplier in play smoothly alongside our other powers.
  strategic_note: Committed shiv-power hybrid deck: set up powers like Tracking, Phantom Blades, and Envenom, then unleash shivs and AoE attacks. Needs more reliable Weak application to maximize Tracking and maybe some extra energy generation.

F25 [rest_site] proceed | source=auto
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F25 [map] choose_map_node (option_index=1) | source=llm
  HP 52->52 | Gold 1->1 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure node. All options lead to the same set of future nodes, so following the central path preserves the most flexibility for future navigation if needed.
  strategic_note: Foundation deck seeking a primary damage engine; prioritizing shops and events in Act 2 to find Poison or Shiv synergies while using gold for removals or high-impact relics.

F26 [treasure] open_chest | source=random
  HP 52->52 | Gold 1->37 | Deck 22->22
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 52->52 | Gold 37->37 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim: Bag of Marbles

F26 [treasure] proceed | source=random
  HP 52->52 | Gold 37->37 | Deck 22->22
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 37->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Unknown

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 37->46 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F27 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 53->53 | Gold 46->46 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F27 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 53->53 | Gold 46->46 | Deck 22->22
  deck_change: no deck change
  reasoning: None of the offered cards improve our Shiv/Envenom engine. Prepared is card disadvantage without Reflex/Tactician, Skewer doesn't fit our multi-hit scaling, and Sucker Punch is redundant with Neutralize++ and Leg Sweep. Skipping to keep the deck lean.
  strategic_note: Committed to shiv and poison scaling via Envenom. Prioritize Accuracy, draw (Acrobatics, Adrenaline), and energy generators. For the Act 2 Boss, focus fire one enemy to break Surrounded. Keep the deck lean to consistently draw core pieces.

F27 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 53->53 | Gold 46->46 | Deck 22->22
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 46->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Unknown

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 46->57 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 57->57 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] choose_reward_card (option_index=1, note_scope=run, note_triggers=deck_building,combat) | source=llm
  HP 54->54 | Gold 57->57 | Deck 22->23
  deck_change: picked Storm of Steel
  reasoning: Storm of Steel fits our Shiv/Exhaust engine perfectly. It generates multiple Shivs that stack Poison with Envenom, trigger Joss Paper draws when they exhaust, and massively fuel Knife Trap for boss-killing burst damage.
  strategic_note: Committed shiv/poison burst plan: generate massive amounts of Shivs to stack poison via Envenom and load up the exhaust pile for a huge Knife Trap finish. Prioritize draw and energy to play more Shivs and powers; skip narrow or expensive off-plan cards.

F28 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 54->54 | Gold 57->57 | Deck 23->23
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 57->57 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: RestSite

F29 [rest_site] choose_rest_option (option_index=1, smith_card_index=11) | source=llm
  HP 54->54 | Gold 57->57 | Deck 23->23
  deck_change: upgraded Envenom->Envenom+
  reasoning: At 54/80 HP, I do not need to rest, especially with Regal Pillow making a later rest much more efficient (no overheal). Upgrading Envenom doubles the poison applied per hit, which synergizes incredibly with Exterminate, Dagger Spray, and Fan of Knives to rapidly stack massive poison on all enemies.
  strategic_note: Committed shiv-poison power hybrid: set up Afterimage and Envenom+, then unleash Shivs and multi-hits to stack massive poison while generating block. Needs more reliable Weak or Block for the setup turns.

F29 [rest_site] proceed | source=auto
  HP 54->54 | Gold 57->57 | Deck 23->23
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 57->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Monster

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 57->67 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 67->67 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 67->67 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 52->52 | Gold 67->67 | Deck 23->24
  deck_change: picked Ricochet
  reasoning: Ricochet pairs incredibly well with Envenom++ (applying 8 poison if unblocked) and has excellent synergy with our multiple discard outlets (Calculated Gamble, Storm of Steel, Survivor, Dagger Throw) to play for free.
  strategic_note: Committed to Shiv/Poison hybrid with Envenom++. Use discard outlets to trigger Sly on Ricochet or cycle through to Shiv generators. Stack massive poison quickly on safe turns, defend, and let poison do the work. Avoid off-plan attacks and bloated cards.

F30 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 52->52 | Gold 67->67 | Deck 24->24
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F30 [map] choose_map_node (option_index=0) | source=llm
  HP 52->52 | Gold 67->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Act 2 elites are extremely dangerous for the Silent, and the current route and strategy both recommend avoiding them to preserve HP for the boss. My HP (52/81) is decent but a bad Elite encounter could end the run. The hallway fight (Monster) is safer and provides gold/card rewards.
  strategic_note: Foundation deck transitioning into a Shiv or Poison engine; prioritize survival and card quality over risky Act 2 elites until a definitive win condition is upgraded.

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 67->80 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 80->80 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Poison Potion

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 80->80 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 53->53 | Gold 80->80 | Deck 24->25
  deck_change: picked Dodge and Roll+
  reasoning: Dodge and Roll++ provides 12 total block for 1 energy, helping mitigate the heavy burst damage from the upcoming Crusher+Rocket boss fight. I must avoid Bubble Bubble as my deck is a hybrid physical/poison build (Envenom), and Bubble Bubble acts as a curse when I need to play attacks to generate poison.
  strategic_note: Committed to Envenom shiv scaling. Defend on heavy attack turns, then spam attacks/shivs when safe to stack poison and burst. Need more card draw and shiv generators.

F31 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 53->53 | Gold 80->80 | Deck 25->25
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 80->80 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 53->82 | Gold 80->80 | Deck 25->25
  deck_change: no deck change
  reasoning: With 53/82 HP and the Act 2 Boss up next, surviving is the absolute top priority. Rest restores 24 HP to bring us near full (77/82). While upgrading Afterimage to Innate would be incredibly strong, we cannot risk dying to bad draw variance against the boss. Taking the heal guarantees we have the health buffer needed to set up our power engine.
  strategic_note: Committed shiv-poison power hybrid: set up Afterimage and Envenom+, then unleash Shivs and multi-hits to stack massive poison while generating block. Needs more reliable Weak or Block for the setup turns.

F32 [rest_site] proceed | source=auto
  HP 82->82 | Gold 80->80 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 82->82 | Gold 80->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 80->155 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 155->155 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 155->155 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] choose_reward_card (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 45->45 | Gold 155->155 | Deck 25->26
  deck_change: picked Tools of the Trade
  reasoning: Tools of the Trade is a 1-cost Rare Power that provides a free discard trigger every turn. This perfectly activates our Sly cards (Flick-Flack, Ricochet) for passive damage and AoE without spending energy, while also helping us cycle through our deck to find key powers like Envenom and Afterimage.
  strategic_note: Committed to Shiv/Poison hybrid with Envenom++ and Sly mechanics. Tools of the Trade enables passive triggers for Flick-Flack/Ricochet. Focus on playing powers early and using Shiv generators to apply massive poison via Envenom. Need energy generation or 0-cost draw.

F33 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 45->45 | Gold 155->155 | Deck 26->26
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 45->75 | Gold 155->155 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2) | source=llm
  HP 75->75 | Gold 155->155 | Deck 26->26
  deck_change: no deck change
  reasoning: Fur Coat will trivialize up to 7 combats in Act 3, which is almost all the hallway fights and elites. This allows us to take the most aggressive path possible, farming elites for relics and gold with zero HP loss, while saving campfires for crucial upgrades rather than resting. This huge snowball of free resources will prepare us perfectly for the Act 3 Boss.
  strategic_note: Foundation: Multi-hit attacks with Envenom and Phantom Blades for scaling damage, relying on Afterimage and Dodge and Roll for block. Need more card draw or a 4th energy to play powers faster. Path aggressively into Elites in Act 3 thanks to Fur Coat, saving campfires to upgrade key powers.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 75->75 | Gold 155->155 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=0) | source=llm
  HP 75->75 | Gold 155->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node. This leads toward a Shop and Rest Site sequence which is optimal for stabilizing Act 2. The Fur Coat relic might trigger on these early hallways, potentially providing free wins.
  strategic_note: Foundation deck focusing on Shiv and Poison flexibility; prioritizing safe hallway fights and early shops to refine the engine before committing to a final damage scaling plan.

F35 [card_select] select_deck_card (option_index=1) | source=llm
  HP 70->70 | Gold 155->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Acrobatics draws 3 cards, letting us dig into our deck for our premium block cards (like Piercing Wail, Backflip, or Dodge and Roll) to spend our remaining energy on and fully mitigate the incoming damage.
  strategic_note: Committed Shiv/Attack spam engine: scale with Phantom Blades, Afterimage, and Fan of Knives, using cheap attacks and Shivs. Prioritize draw and energy to fuel the engine; we have plenty of damage and passive block scaling now.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 155->169 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 169->169 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 55->55 | Gold 169->169 | Deck 26->26
  deck_change: no deck change
  reasoning: None of these cards significantly improve the deck. Pinpoint++ is clunky without massive skill spam, Anticipate++ is redundant since we already have one and our passive block (Afterimage) is better for scaling defense, and Slice is too low-impact. Skipping to keep the deck consistent for drawing Envenom and Phantom Blades.
  strategic_note: Committed to Shiv/Poison hybrid. Play Tools of the Trade, Envenom, and Phantom Blades early, then use Shivs and Sly cards for passive scaling damage while defending with Afterimage.

F35 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 55->55 | Gold 169->169 | Deck 26->26
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 55->55 | Gold 169->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 169->181 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 181->181 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F36 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 29->29 | Gold 181->181 | Deck 26->27
  deck_change: picked Accuracy+
  reasoning: Accuracy++ is the core multiplicative scaling engine piece for any Shiv deck. With Fan of Knives, Leading Strike x2, Storm of Steel, and Knife Trap already in the deck, this completely solves our damage scaling for the Act 3 Boss and synergizes perfectly with Afterimage and Envenom++.
  strategic_note: Committed to Shiv/Poison hybrid. Use Shiv generators like Fan of Knives and Leading Strike to stack poison via Envenom and scale physical damage via Accuracy. Defend passively with Afterimage while spamming attacks. We have enough damage engines; prioritize draw and mitigation for bad turns.

F36 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 29->29 | Gold 181->181 | Deck 27->27
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F36 [map] choose_map_node (option_index=0) | source=llm
  HP 29->29 | Gold 181->181 | Deck 27->27
  deck_change: no deck change
  reasoning: With 29 HP in Act 3, I am in a precarious position. The Shop is the safest immediate path and allows me to spend 181 gold on card removal or defensive tools. The route guide emphasizes staying above 60 HP via Rest Sites, but immediate survival necessitates avoiding a hallway fight where I could take chip damage. I will look for HP restoration or strong block cards at the shop.
  strategic_note: Foundation Shiv/Poison hybrid: currently low HP in Act 3, prioritizing survival through shops and rest sites over elites. Need to find more reliable block or a 'Wraith Form' to stabilize while shivs and poison scale damage. Avoid unnecessary combats until HP is above 50.

F37 [shop] buy_card (option_index=2) | source=plan
  HP 29->29 | Gold 181->143 | Deck 27->28
  deck_change: bought Expose
  reasoning: Shop plan [1/2]: Cheap utility card to strip Artifact and Block from elites and bosses, applying Vulnerable for our Shiv burst turns.

F37 [shop] buy_potion (option_index=2) | source=plan
  HP 29->29 | Gold 143->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Crucial defensive boost for the upcoming Act 3 Boss, enabling better mitigation against the Amalgam's multi-attacks via Backflip, Leg Sweep, and Dodge and Roll.

F37 [shop] close_shop_inventory | source=plan
  HP 29->29 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F37 [shop] proceed | source=auto
  HP 29->29 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 29->29 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Unknown

F38 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=routing) | source=llm
  HP 29->14 | Gold 95->95 | Deck 28->28
  deck_change: upgraded Dagger Spray->Dagger Spray+, Storm of Steel->Storm of Steel+
  reasoning: Big Mushroom's turn 1 draw penalty completely negates Ring of the Snake, which is catastrophic for setting up our powers. Taking the 15 damage for Fragrant Mushroom is risky at 29 HP, but we have Regal Pillow to heal back up quickly at the next rest site.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal the event damage using Regal Pillow.

F38 [event] choose_event_option (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only option: Proceed

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Unknown

F39 [event] choose_event_option (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only option: Proceed

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Unknown

F40 [event] choose_event_option (option_index=1) | source=llm
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Accepting the Forgotten Soul gives a free relic that synergizes perfectly with the deck's shiv engine, dealing passive chip damage whenever a shiv is exhausted. Confronting with Truth adds a harmful curse (Decay), which is too dangerous at 14 HP without curse mitigation.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.

F40 [event] choose_event_option (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: Only option: Accept

F40 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 14->14 | Gold 95->95 | Deck 28->28
  deck_change: no deck change
  reasoning: With only 14 HP, I desperately need immediate survivability. Crafting a Skill that starts with 8 Block gives a strong defensive foundation, which I can hopefully customize further with card draw or additional block.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.

F40 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 14->14 | Gold 95->95 | Deck 28->29
  deck_change: added Mad Science
  reasoning: A 1-cost skill that grants 8 block and draws 3 cards is an exceptionally powerful card draw engine, strictly better than a Backflip. With a 28-card deck full of important powers, drawing through the deck quickly is our highest priority to set up the engine.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.

F40 [event] choose_event_option (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 14->14 | Gold 95->95 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 14->14 | Gold 95->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 14->14 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim: Anchor

F41 [treasure] proceed | source=random
  HP 14->14 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=auto
  HP 14->14 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: RestSite

F42 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=combat,deck_building,routing) | source=llm
  HP 14->52 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: HP is critically low at 14/77 and we have Regal Pillow. Resting heals 38 HP, which is absolutely necessary to survive the upcoming Act 3 nodes before the next rest site.
  strategic_note: Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Fan of Knives) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.

F42 [rest_site] proceed | source=auto
  HP 52->52 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Unknown

F43 [event] choose_event_option (option_index=0) | source=llm
  HP 52->52 | Gold 129->129 | Deck 29->29
  deck_change: no deck change
  reasoning: Accepting the role as Decider leads to high-value rewards (like 2 Relics or Gold) which far outweighs the cost of the curse, especially compared to the Reject option which only gives a curse without a reward.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Accept curses from Act 3 events only if the reward scales our endgame.

F43 [event] choose_event_option (option_index=1) | source=llm
  HP 52->52 | Gold 129->129 | Deck 29->30
  deck_change: added Doubt
  reasoning: Both options give the Doubt curse. Transforming 2 cards allows us to get rid of two less useful cards from our deck (like Strangle or Exterminate) and replace them, whereas card rewards would just add to the deck size. With Tools of the Trade and Calculated Gamble, we can easily discard the Doubt curse when drawn.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Need to find a campfire soon to heal using Regal Pillow.

F43 [card_select] select_deck_card (option_index=17) | source=llm
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: changed: +Memento Mori, Noxious Fumes; -Anticipate, Ricochet
  reasoning: Transforming Anticipate (low impact block scaling that costs a draw) and Ricochet (2-cost attack that clogs our hand since we already have several 2-cost powers and setup cards). Our shiv engine is very strong with Accuracy, Phantom Blades, and Envenom, so we want to trim clunky non-synergistic cards.
  strategic_note: Committed shiv/poison plan: cycle into shiv generators (Storm of Steel, Fan of Knives) while stacking powers (Accuracy, Envenom, Afterimage). Use Corrosive Wave and Strangle for massive extra scaling.

F43 [event] choose_event_option (option_index=0) | source=auto
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: RestSite

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: upgraded Afterimage->Afterimage+
  reasoning: 52 HP is healthy enough to survive the upcoming Elite, especially with another Rest Site at F48 before the Boss. Upgrading Afterimage to Innate guarantees our block engine is online from Turn 1, which is crucial for surviving Act 3 Elites and the Boss while we spam Shivs.
  strategic_note: Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Afterimage) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.

F44 [rest_site] proceed | source=auto
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Unknown

F45 [event] choose_event_option (option_index=2, note_scope=run) | source=llm
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Enchanting a Power with Swift 2 (Draw 2) provides massive value for this deck. The deck relies heavily on getting key powers (Accuracy, Afterimage, Envenom, Tools of the Trade) into play quickly. Swift 2 allows the enchanted power to replace itself and draw an additional card, significantly accelerating the setup phase.
  strategic_note: Committed shiv/power engine: use early draw to set up Accuracy, Fan of Knives, and Envenom, then overwhelm enemies with upgraded shivs and attacks while building block. Needs to find a swift and safe way to deploy powers.

F45 [card_select] select_deck_card (option_index=4) | source=llm
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Afterimage++ is both a critical survival engine for our Shiv spam AND Innate. Enchanting an Innate card guarantees we draw it on turn 1 of every combat, giving us maximum consistency and immediate value from whatever enchantment we apply.
  strategic_note: Committed Shiv/Poison hybrid: setup Afterimage and Phantom Blades/Accuracy early, then spam retained Shivs to stack Envenom poison and generate block. Use Tracking to double Shiv damage on weak targets.

F45 [event] choose_event_option (option_index=0) | source=auto
  HP 52->52 | Gold 129->129 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 129->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Elite

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 129->158 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 29 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 158->158 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim relic: Snecko Skull

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 158->158 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 53->53 | Gold 158->158 | Deck 30->31
  deck_change: picked Blade Dance
  reasoning: Blade Dance is premium Shiv generation for our Accuracy++, Envenom++, Afterimage++, and Knife Trap synergies.
  strategic_note: Committed Shiv/Poison hybrid: generate shivs to trigger Envenom+Snecko Skull and Afterimage. Keep deck cycling fast to find key powers early.

F46 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 53->53 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 53->78 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: HP is 53/78 (missing 25) and the next node is the Act 3 Boss. With a 31-card deck containing many expensive setup powers (Envenom, Accuracy, Fan of Knives), we will likely take chip damage early before stabilizing with Afterimage. Healing ensures we have a large enough buffer to survive the setup turns.
  strategic_note: Committed Shiv/Poison hybrid: deploy key powers (Accuracy, Envenom, Afterimage) then spam Shivs to melt enemies. Prioritize HP preservation and defensive consistency until the engine is online in each fight.

F47 [rest_site] proceed | source=auto
  HP 78->78 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 78->78 | Gold 158->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 14->14 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 14->0 | Gold 158->158 | Deck 31->31
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (6 replays)
[Selected: elite] Phrog Parasite (F15, elite)
Historical: loss=15 vs historical avg=19.1+/-20.0 (z=-0.2, TYPICAL, n=16)
## Combat Replay: vs Phrog Parasite (Floor 15, elite)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow
Deck (16): Defend x5, Strike x2, Backflip, Calculated Gamble, Dagger Throw, Knife Trap, Leading Strike, Neutralize+, Phantom Blades, Piercing Wail, Survivor
Enemies: Phrog Parasite HP=62/62

### Round 1
Agent plan (hypothesis): Saved the second Shiv to benefit from Phantom Blades buff next turn.
Agent plan (hypothesis): Retaining one Shiv to maximize Phantom Blades value next turn.
Agent plan (hypothesis): Play the retained Shiv first next turn to get the +9 damage bonus. Focus on damage since the enemy is still not attacking.
Intent: Phrog Parasite: StatusCard(3)
  turn_end

### Round 2
Agent plan (hypothesis): Save Flex Potion for the Wriggler phase or the Boss.
Agent plan (hypothesis): Phrog Parasite is low on HP. We will need AoE or burst to deal with the summoned Wrigglers once it dies.
Intent: Phrog Parasite: Attack(4x4=16)
  turn_end

### Round 3
Agent plan (hypothesis): We need 17 damage. Dagger Throw deals 9. Strike deals 6. If we kill it, Wrigglers spawn instantly and we can hit them with our remaining energy/shivs.
Agent plan (hypothesis): If we draw Neutralize or Leading Strike, use them to kill. Otherwise just Strike to leave it at 2 HP.
Agent plan (hypothesis): Kill the parasite next turn and prepare to face the Wrigglers.
Intent: Phrog Parasite: StatusCard(3)
  Defend
  turn_end

### Round 4
Agent plan (hypothesis): Wrigglers are spawned now, prepare AoE and burst.
Intent: Phrog Parasite: Attack(4x4=16)
  Infection
  turn_end

### Round 5
Agent plan (hypothesis): Infections are a problem. Need to burst the remaining Wrigglers.
Intent: Wriggler: Attack(6), Wriggler: Buff, StatusCard(1), Wriggler: Attack(6), Wriggler: Buff, StatusCard(1)
  turn_end

### Round 6
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Flex Potion
    +Strength(5) | +Flex Potion(5)
  turn_end

### Round 7
Agent plan (hypothesis): If Survivor is drawn, play it and discard Infection. Otherwise play Defend.
Agent plan (hypothesis): We need to finish this Wriggler soon before it gains more strength.
Intent: Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Infection
  Infection
  turn_end

### Round 8
Intent: Wriggler: Buff, StatusCard(1)
  cards: Knife Trap, dealt=0, taken=0
## Combat Analytics: Phrog Parasite (WIN - 8 rounds)

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:4 -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:2 -> R8:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2 -> R8:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:- -> R8:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1

Unattributed damage (power/passive effects): 59
  Per round: R1:22 R2:23 R3:6 R4:2 R6:2 R7:4
Comparator (recent same-enemy comparator):
## Combat Replay: vs Phrog Parasite (Floor 15, elite)
Relics: Ring of the Snake, Golden Pearl, Game Piece, Pear
Deck (20): Defend x5, Strike x4, Afterimage, Ascender's Bane, Blade Dance, Bouncing Flask+, Calculated Gamble, Dagger Spray, Deadly Poison, Footwork+, Neutralize+, Ricochet, Survivor
Enemies: Phrog Parasite HP=66/66

### Round 1
Intent: Phrog Parasite: StatusCard(3)
  Power Potion
  Tools of the Trade
  turn_end
    exhausted: Ascender's Bane [0费]：Unplayable. Ethereal. Eternal.
  Strike

### Round 2
Intent: Phrog Parasite: Attack(3x4=12)
  turn_end
  Strike

### Round 3
Intent: Phrog Parasite: StatusCard(3)
  turn_end
  Defend

### Round 4
Intent: Wriggler: Stun, Wriggler: Stun, Wriggler: Stun, Wriggler: Stun
  turn_end
  Ricochet

### Round 5
Intent: Wriggler: Attack(6), Wriggler: Buff, StatusCard(1), Wriggler: Attack(4), Wriggler: Buff, StatusCard(1)
  turn_end
  Infection

### Round 6
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Ricochet
  turn_end
  Infection

### Round 7
Intent: Wriggler: Attack(8)
  cards: Dagger Spray, dealt=0, taken=0
## Combat Analytics: Phrog Parasite (WIN - 7 rounds)

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:- -> R5:- -> R6:- -> R7:-
  Poison: R1:- -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:5 -> R6:6 -> R7:-
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:7 -> R6:1 -> R7:-
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:-

Unattributed damage (power/passive effects): 43
  Per round: R1:4 R2:12 R3:20 R6:7

[Selected: boss] Vantom (F17, boss)
Historical: loss=28 vs historical avg=26.0+/-11.6 (z=0.2, TYPICAL, n=24)
## Combat Replay: vs Vantom (Floor 17, boss)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper
Deck (17): Defend x5, Strike x2, Backflip, Calculated Gamble, Corrosive Wave, Dagger Throw, Knife Trap, Leading Strike, Neutralize+, Phantom Blades, Piercing Wail, Survivor
Enemies: Vantom HP=173/173

### Round 1
Intent: Vantom: Attack(7)
  turn_end

### Round 2
Agent plan (hypothesis): Play Phantom Blades, then Survivor (discarding a low-value card), then use remaining energy to strip Slippery if possible.
Agent plan (hypothesis): Turn 3 nuke is incoming. Use Piercing Wail / Neutralize / Backflip to survive.
Agent plan (hypothesis): Turn 3 is the big 27-damage nuke. Play defensive options.
Intent: Vantom: Attack(4x2=8)
  Dagger Throw
  turn_end

### Round 3
Agent plan (hypothesis): Slippery is stripped. Next turn Vantom buffs, so use Knife Trap and setup cards. We draw Backflip to find more damage.
Intent: Vantom: Attack(27), StatusCard(3)
  Colorless Potion
  Panache
  turn_end

### Round 4
Agent plan (hypothesis): Vantom will attack for 6-9 next turn. Save some block.
Agent plan (hypothesis): Save energy and block for upcoming attacks, especially the turn 7 nuke.
Intent: Vantom: Buff
  turn_end

### Round 5
Intent: Vantom: Attack(6)
  Wound
  turn_end

### Round 6
Agent plan (hypothesis): Evaluate drawn card before spending the remaining 2 energy. Keep next turn's nuke in mind.
Agent plan (hypothesis): Next turn is the big nuke. We have 56 HP, Weak is already applied. Draw pile has Piercing Wail and Backflip, hopefully we draw enough block.
Intent: Vantom: Attack(8x2=16)
  Wound
  turn_end

### Round 7
Agent plan (hypothesis): Depending on draws, we can follow up with Leading Strike and its generated Shivs to trigger Panache, plus whatever block we drew.
Intent: Vantom: Attack(21), StatusCard(3)
  turn_end

### Round 8
Agent plan (hypothesis): Boss is dead. Good job surviving!
Intent: Vantom: Buff
  cards: Neutralize+, Strike, Knife Trap, dealt=10, taken=0
## Combat Analytics: Vantom (WIN - 8 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:-
  Slippery: R1:9 -> R2:4 -> R3:3 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:1 -> R8:-

Unattributed damage (power/passive effects): 120
  Per round: R1:4 R3:13 R4:39 R5:20 R6:4 R7:30 R8:10
Comparator (recent same-enemy comparator):
## Combat Replay: vs Vantom (Floor 17, boss)
Relics: Ring of the Snake, Leafy Poultice, Byrdpip, Kusarigama
Deck (23): Defend x4, Strike x3, Acrobatics, Backflip, Byrd Swoop, Dagger Throw, Escape Plan, Flick-Flack, Leading Strike, Neutralize, Peck, Phantom Blades, Piercing Wail, Reflex, Ricochet, Shadowmeld+, Survivor, Well-Laid Plans
Enemies: Vantom HP=173/173

### Round 1
Intent: Vantom: Attack(7)
  Reflex
  turn_end
  Phantom Blades

### Round 2
Intent: Vantom: Attack(6x2=12)
  turn_end
  Defend

### Round 3
Intent: Vantom: Attack(27), StatusCard(3)
  Strike
  turn_end
  Peck

### Round 4
Intent: Vantom: Buff
  Reflex
  turn_end
  Ricochet

### Round 5
Intent: Vantom: Attack(9)
  Reflex
  Ricochet
  turn_end
  Strike

### Round 6
Intent: Vantom: Attack(8x2=16)
  Flick-Flack
  turn_end
  Peck

### Round 7
Intent: Vantom: Attack(29), StatusCard(3)
  turn_end
  Ricochet

### Round 8
Intent: Vantom: Buff
  Ricochet
## Combat Analytics: Vantom (WIN - 8 rounds)

Enemy power timeline:
  Slippery: R1:9 -> R2:9 -> R3:4 -> R4:3 -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1

Unattributed damage (power/passive effects): 128
  Per round: R2:5 R3:1 R4:26 R5:45 R6:13 R7:18 R8:20

[Selected: boss] multi:Crusher+Rocket (F33, boss)
Historical: loss=37 vs historical avg=35.9+/-16.1 (z=0.1, TYPICAL, n=32)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper, Pandora's Box, Bag of Marbles
Deck (25): Afterimage, Anticipate, Backflip, Backstab, Calculated Gamble, Corrosive Wave, Dagger Spray, Dagger Throw, Dodge and Roll+, Envenom+, Exterminate, Fan of Knives, Flick-Flack, Knife Trap, Leading Strike, Leading Strike+, Leg Sweep, Neutralize+, Phantom Blades, Piercing Wail, Ricochet, Storm of Steel, Strangle, Survivor, Tracking+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Agent plan (hypothesis): Envenom is active. Spam shivs and multi-hits.
Intent: Crusher: Attack(18), Rocket: Attack(3)
  turn_end

### Round 2
Agent plan (hypothesis): Continue focusing Rocket to reduce the massive incoming damage spikes.
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Vulnerable Potion -> Rocket[1]
    enemy_deltas: Rocket: +Vulnerable(3)
  Poison Potion -> Rocket[1]
    enemy_deltas: Rocket: +Poison(6)
  turn_end

### Round 3
Agent plan (hypothesis): Blocked perfectly this turn, prepare for Rocket's massive attack next turn.
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Flick-Flack
  turn_end

### Round 4
Agent plan (hypothesis): Survive the massive attack, then counter attack on the next turns.
Intent: Crusher: Buff, Rocket: Attack(49)
  Corrosive Wave
  turn_end

### Round 5
Agent plan (hypothesis): Continue stalling and stacking poison. Use discard synergies if available next turn.
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  turn_end

### Round 6
Agent plan (hypothesis): Rocket will die to poison, Crusher will gain Crab Rage next turn. Prepare to stall his 99 block or burst him down.
Intent: Crusher: Attack(14), Rocket: Attack(7)
  turn_end

### Round 7
Intent: Crusher: Attack(9)
  turn_end

### Round 8
Agent plan (hypothesis): Crusher dies at the start of next turn to poison.
Intent: Crusher: Attack(14x2=28), Debuff
  turn_end

### Round 9
Agent plan (hypothesis): Easy win.
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
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Neow's Bones, Stone Humidifier, Silver Crucible, The Chosen Cheese, Sword of Stone, Archaic Tooth, Nunchaku, Meal Ticket
Deck (21): Strike x5, Defend x4, Backflip x2, Accuracy+, Blade Dance+, Dodge and Roll+, Finisher, Nightmare+, Piercing Wail+, Suppress+, Survivor, Up My Sleeve, Well-Laid Plans
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Dexterity Potion
    +Dexterity(2)
  turn_end
  Finisher

### Round 2
Intent: Crusher: Attack(3), Rocket: Attack(27)
  turn_end
  Defend

### Round 3
Intent: Crusher: Attack(6x2=12), Debuff, Rocket: Buff
  Strike
  turn_end
  Nightmare+

### Round 4
Intent: Crusher: Buff, Rocket: Attack(33)
  turn_end
  Nightmare+

### Round 5
Intent: Crusher: Attack(15), Defend, Rocket: Sleep
  Strike
  turn_end
  Nightmare+

### Round 6
Intent: Crusher: Attack(21), Rocket: Attack(3)
  turn_end
  Nightmare+

### Round 7
Intent: Crusher: Attack(9), Rocket: Attack(15)
  Defend
  turn_end
  Nightmare+

### Round 8
Intent: Crusher: Attack(10x2=20), Debuff
  turn_end
  Nightmare+

### Round 9
Intent: Crusher: Buff
  turn_end
  Nightmare+

### Round 10
Intent: Crusher: Attack(16), Defend
  turn_end
  Nightmare+

### Round 11
Intent: Crusher: Attack(16)
  Strike
  turn_end
  Nightmare+

### Round 12
Intent: Crusher: Attack(10)
  turn_end
  Nightmare+

### Round 13
Intent: Crusher: Attack(12x2=24), Debuff
  Shackling Potion
    enemy_deltas: Crusher: Strength(10→3), +Shackling Potion(7)
  Nightmare+
  turn_end
  Defend

### Round 14
Intent: Crusher: Buff
  turn_end
  Dodge and Roll+

### Round 15
Intent: Crusher: Attack(18), Defend
  cards: Suppress+, dealt=0, taken=0
## Combat Analytics: multi:Crusher+Rocket (WIN - 15 rounds)

Active powers: Surrounded(1)

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1 -> R13:1 -> R14:1 -> R15:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:8 -> R9:8 -> R10:10 -> R11:10 -> R12:10 -> R13:10 -> R14:10 -> R15:12
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:- -> R6:3 -> R7:2 -> R8:4 -> R9:3 -> R10:7 -> R11:11 -> R12:10 -> R13:9 -> R14:13 -> R15:12
  Weak[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-
  Weak[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:-

Unattributed damage (power/passive effects): 403
  Per round: R1:17 R2:96 R3:30 R4:12 R5:33 R7:52 R8:6 R9:37 R10:16 R11:12 R12:36 R13:23 R14:33

[Selected: run_combat] multi:Living Shield+Turret Operator (F35, monster)
Historical: loss=20 vs historical avg=4.6+/-6.3 (z=2.4, WORSE_THAN_USUAL, n=36)
## Combat Replay: vs multi:Living Shield+Turret Operator (Floor 35, monster)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper, Pandora's Box, Bag of Marbles, Fur Coat
Deck (26): Afterimage, Anticipate, Backflip, Backstab, Calculated Gamble, Corrosive Wave, Dagger Spray, Dagger Throw, Dodge and Roll+, Envenom+, Exterminate, Fan of Knives, Flick-Flack, Knife Trap, Leading Strike, Leading Strike+, Leg Sweep, Neutralize+, Phantom Blades, Piercing Wail, Ricochet, Storm of Steel, Strangle, Survivor, Tools of the Trade, Tracking+
Enemies: Living Shield HP=55/55, Turret Operator HP=41/41

### Round 1
Agent plan (hypothesis): Play any 0-cost defensive cards drawn if they help mitigate the remaining 4 damage.
Intent: Living Shield: Attack(6), Turret Operator: Attack(3x5=15)
  turn_end

### Round 2
Agent plan (hypothesis): See what we draw, then prioritize mitigating the 16 incoming damage.
Agent plan (hypothesis): Play Tools for long term value.
Agent plan (hypothesis): See what we draw from Gamble.
Intent: Living Shield: Attack(6), Turret Operator: Attack(2x5=10)
  Skill Potion
  Acrobatics
  Flick-Flack
  Envenom+
  turn_end
  Ricochet

### Round 3
Agent plan (hypothesis): Turret will be weakened next turn. Try to kill it or mitigate the incoming 4x5.
Intent: Living Shield: Attack(6), Turret Operator: Buff
  turn_end
  Knife Trap

### Round 4
Agent plan (hypothesis): Turret operator is almost dead. Try to finish it off next turn.
Agent plan (hypothesis): Kill Turret next turn
Intent: Living Shield: Attack(6), Turret Operator: Attack(3x5=15)
  turn_end
  Survivor

### Round 5
Agent plan (hypothesis): Kill Living Shield next turn.
Intent: Living Shield: Attack(6), Turret Operator: Attack(4x5=20)
  turn_end
  Ricochet

### Round 6
Intent: Living Shield: Attack(16), Buff
  cards: none, dealt=0, taken=0
## Combat Analytics: multi:Living Shield+Turret Operator (WIN - 6 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:3 -> R5:2 -> R6:-
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:3 -> R5:2 -> R6:-
  Rampart: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25 -> R6:25
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:- -> R6:-

Unattributed damage (power/passive effects): 61
  Per round: R1:12 R3:8 R4:3 R5:38
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Living Shield+Turret Operator (Floor 35, monster)
Relics: Ring of the Snake, Golden Pearl, The Chosen Cheese, Bellows, Horn Cleat, Kusarigama, Biiig Hug, Amethyst Aubergine, Lord's Parasol
Deck (21): Defend x3, Afterimage x2, Leading Strike x2, Accuracy, Alchemize+, Backflip, Blade Dance, Calculated Gamble, Cloak and Dagger+, Deadly Poison, Expertise+, Expose, Fan of Knives, Neutralize+, Peck, Survivor, Well-Laid Plans+
Enemies: Living Shield HP=55/55, Turret Operator HP=41/41

### Round 1
Intent: Living Shield: Attack(6), Turret Operator: Attack(3x5=15)
  turn_end

### Round 2
Intent: Living Shield: Attack(16), Buff
  turn_end

### Round 3
Intent: Living Shield: Attack(19), Buff
  cards: Leading Strike, Shiv, Shiv, dealt=11, taken=0
## Combat Analytics: multi:Living Shield+Turret Operator (WIN - 3 rounds)

Enemy power timeline:
  Rampart: R1:25 -> R2:25 -> R3:25
  Strength: R1:- -> R2:- -> R3:3

Unattributed damage (power/passive effects): 94
  Per round: R1:67 R2:16 R3:11

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F46, elite)
Historical: loss=0 vs historical avg=12.6+/-14.7 (z=-0.9, TYPICAL, n=11)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 46, elite)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper, Pandora's Box, Bag of Marbles, Fur Coat, Fragrant Mushroom, Anchor
Deck (30): Accuracy+, Afterimage+, Backflip, Backstab, Calculated Gamble, Corrosive Wave, Dagger Spray+, Dagger Throw, Dodge and Roll+, Doubt, Envenom+, Expose, Exterminate, Fan of Knives, Flick-Flack, Knife Trap, Leading Strike, Leading Strike+, Leg Sweep, Mad Science, Memento Mori, Neutralize+, Noxious Fumes, Phantom Blades, Piercing Wail, Storm of Steel+, Strangle, Survivor, Tools of the Trade, Tracking+
Enemies: Flail Knight HP=1/101, Spectral Knight HP=1/93, Magi Knight HP=1/82

### Round 1
Agent plan (hypothesis): Play attacks drawn from Mad Science to finish the fight.
Agent plan (hypothesis): Fight should end here.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  cards: Backstab, Mad Science, Neutralize+, Expose, Storm of Steel+, Shiv+, dealt=2, taken=0
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 1 rounds)

Enemy power timeline:
  Vulnerable[0]: R1:1
  Vulnerable[1]: R1:1
  Vulnerable[2]: R1:1

Unattributed damage (power/passive effects): 2
  Per round: R1:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 40, elite)
Relics: Ring of the Snake, Golden Pearl, The Chosen Cheese, Bellows, Horn Cleat, Kusarigama, Biiig Hug, Amethyst Aubergine, Lord's Parasol, Pantograph, Regal Pillow, Burning Sticks, Red Mask, Planisphere, The Abacus
Deck (35): Defend x3, Afterimage x2, Blade Dance x2, Expose x2, Leading Strike x2, Volley x2, Accuracy, Acrobatics, Alchemize+, Backflip, Calculated Gamble, Cloak and Dagger, Cloak and Dagger+, Expertise+, Fan of Knives, Flick-Flack, Footwork+, Murder, Neutralize+, Peck, Phantom Blades, Pinpoint, Precise Cut, Prepared, Rolling Boulder, Speedster, Survivor, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Intent: Flail Knight: Attack(11), Spectral Knight: Debuff, Magi Knight: Attack(4), Defend
  turn_end

### Round 2
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Debuff
  Speedster
  turn_end
    exhausted: Shiv*8 [0费]：Ethereal. Deal 4 damage to ALL enemies. Exhaust.

### Round 3
Intent: Flail Knight: Attack(18), Spectral Knight: Attack(2x3=6), Magi Knight: Attack(10)
  Fysh Oil
    Dexterity(3→4) | +Strength(1)
  turn_end
    exhausted: Survivor [1费]：Ethereal. Gain 8 Block. Discard 1 card.

### Round 4
Intent: Flail Knight: Buff, Spectral Knight: Attack(15)
  turn_end
    exhausted: Well-Laid Plans+ [1费]：Ethereal. At the end of your turn, Retain up to 2 cards.

### Round 5
Intent: Flail Knight: Attack(15x2=30), Spectral Knight: Attack(15)
  cards: Expose, Blade Dance, Shiv, Shiv, Shiv, Peck, dealt=61, taken=0
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 5 rounds)

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:6
  Vulnerable[1]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-
  Vulnerable[2]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-
  Weak[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-

Unattributed damage (power/passive effects): 267
  Per round: R1:22 R2:66 R3:108 R4:10 R5:61

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
Historical: loss=64 vs historical avg=35.8+/-16.0 (z=1.8, WORSE_THAN_USUAL, n=11)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Precarious Shears, The Chosen Cheese, Regal Pillow, Joss Paper, Pandora's Box, Bag of Marbles, Fur Coat, Fragrant Mushroom, Anchor, Snecko Skull
Deck (31): Accuracy+, Afterimage+, Backflip, Backstab, Blade Dance, Calculated Gamble, Corrosive Wave, Dagger Spray+, Dagger Throw, Dodge and Roll+, Doubt, Envenom+, Expose, Exterminate, Fan of Knives, Flick-Flack, Knife Trap, Leading Strike, Leading Strike+, Leg Sweep, Mad Science, Memento Mori, Neutralize+, Noxious Fumes, Phantom Blades, Piercing Wail, Storm of Steel+, Strangle, Survivor, Tools of the Trade, Tracking+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Agent plan (hypothesis): We drew 2 cards from Afterimage. Evaluate whether to play Noxious Fumes, Accuracy, or newly drawn cards.
Agent plan (hypothesis): See what we draw, spend remaining 2 energy.
Agent plan (hypothesis): Continue digging for Envenom/Accuracy
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Dexterity Potion
    +Dexterity(2)
  turn_end

### Round 2
Agent plan (hypothesis): Set up Tools of the Trade. Prepare for large multi-attacks on turn 3.
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  turn_end
  Doubt

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  turn_end
  Leg Sweep

### Round 4
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  Exterminate
  turn_end
  Flick-Flack

### Round 5
Agent plan (hypothesis): See what Backflip draws before spending the rest of the energy.
Agent plan (hypothesis): Need to prepare for Amalgam multi-attack next turn.
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  turn_end
  Memento Mori

### Round 6
Agent plan (hypothesis): Amalgam is weakened, keep focusing it down to reduce incoming damage.
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  turn_end
  Flick-Flack

### Round 7
Agent plan (hypothesis): See what we draw, then prioritize block and playing Leading Strike/Shivs.
Agent plan (hypothesis): We will have 1 energy left. If the drawn card isn't better, we can play Exterminate or Noxious Fumes.
Agent plan (hypothesis): Amalgam will take heavy poison damage next turn.
Intent: Torch Head Amalgam: Attack(20), Queen: Buff, Defend
  turn_end
  Doubt

### Round 8
Intent: Torch Head Amalgam: Attack(28), Queen: Buff, Defend
  turn_end
  Flick-Flack

### Round 9
Intent: Queen: Attack(7x5=35)
  turn_end
  Dagger Spray+

### Round 10
Agent plan (hypothesis): If this doesn't kill we are dead anyway.
Intent: Queen: Attack(25)
  turn_end
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 10 rounds)

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:- -> R10:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:26 -> R10:43
  Poison[0]: R1:- -> R2:- -> R3:8 -> R4:7 -> R5:12 -> R6:11 -> R7:25 -> R8:36 -> R9:- -> R10:-
  Poison[1]: R1:- -> R2:- -> R3:8 -> R4:7 -> R5:6 -> R6:11 -> R7:10 -> R8:12 -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:2 -> R10:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:-

Unattributed damage (power/passive effects): 369
  Per round: R1:40 R3:15 R4:3 R5:9 R6:28 R7:23 R8:41 R9:44 R10:166
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Scroll Boxes, Sword of Stone, Candelabra, Beating Remnant, Very Hot Cocoa, Ghost Seed, Juzu Bracelet, Twisted Funnel, Lord's Parasol, Fragrant Mushroom, Permafrost, Strike Dummy, Sling of Courage, Royal Poison, Horn Cleat, Joss Paper, Venerable Tea Set
Deck (41): Backflip x3, Defend x3, Defend+ x2, Deflect x2, Escape Plan x2, Footwork x2, Piercing Wail x2, Strike x2, Ascender's Bane, Blade Dance, Blade Dance+, Calculated Gamble+, Cloak and Dagger+, Dagger Spray, Dash, Deadly Poison, Finesse, Follow Through, Footwork+, Infinite Blades, Neutralize+, Nostalgia, Phantom Blades+, Skewer+, Slice, Strangle+, Strike+, Survivor, Tools of the Trade+, Tracking+, Well-Laid Plans
Enemies: Torch Head Amalgam HP=211/211, Queen HP=419/419

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  turn_end
    exhausted: Piercing Wail*2 [1费]：ALL enemies lose 6 Strength this turn. Exhaust.

### Round 2
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  Strike
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  turn_end
    exhausted: Piercing Wail*2 [1费]：ALL enemies lose 6 Strength this turn. Exhaust.
  Dagger Spray

### Round 4
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  turn_end
    exhausted: Shiv*4 [0费]：Deal 4 damage. Exhaust.
  Dash
  Infinite Blades

### Round 5
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  turn_end
    exhausted: Strike+ [1费]：Ethereal. Deal 9 damage.
  Dash
  Blade Dance

### Round 6
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  turn_end
  Dash
  Blade Dance

### Round 7
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  turn_end
  Backflip
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 7 rounds)
Death cause: Killed by damage. HP 1 -> 0, took 0 damage.

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Poison[0]: R1:4 -> R2:3 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:-
  Poison[1]: R1:4 -> R2:3 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:1 -> R7:-

Unattributed damage (power/passive effects): 95
  Per round: R1:66 R3:3 R4:15 R5:11

## Existing Combat Guides (relevant enemies)
[Guide: Louse Progenitor] WR=91%, 47 episodes, confidence=0.90, v35
  - **Pop Curl Up Early:** The Progenitor starts with 14 Curl Up. Strike it with your weakest attack (like Neutralize or a single Shiv) early on Turn 1 to trigger the block, then break it so your heavier attacks land unmitigated.
- **Exploit Setup Turns:** Turn 1 (Curl Up) and Turn 3 (Strength buff) are low-threat windows. Use these turns to safely deploy powers like Noxious Fumes, Footwork, or Caltrops without bleeding HP.
- **Mitigate Escalation:** The boss gains +5 Strength every three turns (Turns 3, 6, 9). Chain Weakness starting on Turn 3 to survive its boosted 14-19 damage swings, and save Piercing Wail for its heaviest multi-attacks.
- **Race the Clock:** While mitigation is possible (as seen in 10-round wins), the fight becomes highly lethal past Turn 6. Accelerate your damage using Shiv burst (Blade Dance, Storm of Steel) or fast poison scaling to finish the fight by Turn 4 or 5.
[Guide: Ovicopter] WR=94%, 47 episodes, confidence=0.90, v37
  - **Zero-Damage Setup (Round 1):** The Ovicopter does not attack on its first turn. Use this window exclusively for scaling (Accuracy, Afterimage) or high-cost setup cards (Bullet Time). If your hand is purely offensive, push early damage to the Ovicopter to enable a Round 2 or 3 kill.
- **The Hatchling Threat (Round 2):** Eggs hatch and attack immediately with multi-hits (e.g., 6x3). You must either clear all Hatchlings using AoE (Dagger Spray, Fan of Knives) or apply Weakness to them. Because they multi-hit, Weakness is significantly more effective than standard Block cards.
- **Manage Passive Damage:** Combat data indicates a Thorns-like effect or high chip damage during Shiv-heavy turns. Prioritize playing Afterimage or Cloak and Dagger+ to ensure every Shiv generates enough Block to offset passive health loss.
- **Aggressive Execution:** The cleanest wins (0 HP loss) occur when ending the fight by Round 3. Use Shiv-synergy bursts (Finisher, Blade Dance+) to bypass the second summon cycle entirely. If the fight lasts until Round 5, you face a second swarm that is often lethal if AoE has been exhausted.
[Guide: Phrog Parasite] WR=88%, 16 episodes, confidence=0.90, v16
  - **Exploit the Opening Window**: Rounds 1-3 are incredibly safe, as enemies prioritize adding status cards to your deck and applying minor buffs. Dedicate all your energy during this window to deploying powers (Footwork, Accuracy) and aggressive scaling (Poison, Shivs) instead of playing unnecessary block.
- **Conclude the Soft Race**: You must finish this fight by round 6 or 7. From round 4 onward, the enemies begin aggressively stacking Strength (+2, then +4). Matches that drag past round 8 consistently end in massive HP loss or death due to overwhelming incoming damage.
- **AoE and Target Elimination**: Eliminate Wrigglers as quickly as possible. Leverage early AoE (Dagger Spray) and frontloaded burst (Skewer, Blade Dance) to clear the board. Fewer enemies alive means less incoming scaled damage later.
- **Tactical Mitigation**: Once the enemies shift from setup to attacking (base 8 damage), rely on high-efficiency defense. Target your Weakness sources (Neutralize) specifically at the enemies with the highest Strength buffs, and use high-value block cards (Survivor) to survive their synchronized attacks while you finish the race.
[Guide: The Obscura] WR=90%, 39 episodes, confidence=0.90, v29
  - **Race the Escalation:** This encounter is a strict DPS check. The cleanest, zero-damage wins bypass the enemy's scaling entirely by deploying explosive frontloaded burst (Shivs, Accuracy, Skewer+, Follow Through) to end the fight in 3-4 rounds.
- **Mitigate the Minion:** The Parafright consistently attacks for 16 base damage. Prioritize applying Weak (Neutralize+) to the Parafright to reduce its threat, allowing you to efficiently block with a single Defend or Survivor while focusing your energy on killing The Obscura.
- **Survive the Synchronization:** If the fight extends to Rounds 4 or 5, +3 Strength buffs will trigger, pushing the Parafright's damage to 19+ while The Obscura begins attacking. Retain AoE damage reduction (Piercing Wail, Dark Shackles) specifically for these synchronized, high-damage spikes.
- **Avoid Slow Setup:** Defensive or slow poison builds (Noxious Fumes) routinely take high damage (11+ per late round) or lose outright. If you cannot burst the boss down by Round 4, you must aggressively cycle defensive mitigation (Footwork+, Escape Plan) to outlast the overlapping buffed attacks.
[Guide: Tunneler] WR=99%, 71 episodes, confidence=0.90, v47
  - **The R1-R2 Opening:** Tunneler is completely exposed during the first two rounds. Use this window to deal maximum damage or stack Poison before it raises its defenses. It will attack for 13 on R1, then prepare its shield on R2.
- **Burrowed Phase (R3+):** On Round 3, Tunneler gains 32 Block and the `Burrowed` power, which prevents its Block from expiring. It will then attack for 17-23 damage every turn.
- **Break the Shield:** Your primary goal during the Burrowed phase is to deal 32 damage to break its Block. Reducing its Block to 0 immediately Stuns it, cancelling its attack for that turn and removing the `Burrowed` status. Time your shield-break to interrupt its most threatening attack.
- **Poison Bypass:** Since Poison deals HP damage directly, it bypasses the 32 Block entirely. If your deck excels at defense and Poison, you can simply block its heavy attacks and let Poison secure the kill without ever breaking the shield.
[Guide: Vantom] WR=96%, 25 episodes, confidence=0.90, v18
  - **The Slippery Mechanic:** Vantom starts the fight with exactly 9 stacks of Slippery. For the first 9 times he loses HP, he will only lose 1 HP. Stacks do not regenerate. Strip these 9 stacks rapidly using multi-hit or low-damage attacks before committing your heavy hitters.
- **The Turn 3 Nuke:** Vantom follows a strict 4-turn cycle. Turn 3 (and 7, 11) features a massive attack (27 base damage) that also shuffles 3 Status cards into your deck. Plan your defenses from Turn 1 specifically for these rounds.
- **Rhythm of the Fight:** Turn 4 (and 8, 12) is a non-attacking turn where Vantom gains 2 Strength. This permanently buffs subsequent cycles, making the Turn 6 multi-attack and Turn 7 nuke highly lethal. Use the free buff turns to push heavy damage and end the fight before his Strength scales out of control.
[Guide: multi:Bowlbug (Nectar)+Bowlbug (Rock)] WR=97%, 38 episodes, confidence=0.90, v33
  - Maximize aggression in Rounds 1 and 2. The bugs are primarily passive or use low-damage debuffs during this window; ignore blocking to dump all energy into frontloaded damage like Blade Dance, Shivs, and Backstab.
- Prioritize Bowlbug (Rock) for single-target burst. It acts as the primary damage threat during the enrage phase.
- If a Round 3 kill is impossible, you must apply Weak (Neutralize+, Leg Sweep) or save Piercing Wail. The +15 Strength gain on Round 3 creates a lethal damage spike that standard block cards cannot comfortably mitigate.
- Avoid slow scaling like Noxious Fumes unless paired with strong defensive cycling (Blur, Backflip). Data shows longer fights (6+ rounds) correlate with significantly higher HP loss due to sustained enraged attacks.
- Use the 'Imbalanced' window to set up finishers. Cards that generate multiple hits (Dagger Spray, Fan of Knives) are high value for clearing both targets simultaneously before the Strength buff triggers.
[Guide: multi:Bowlbug (Nectar)+Bowlbug (Rock)+Bowlbug (Silk)] WR=79%, 14 episodes, confidence=0.88, v12
  - **Survive the Opening Volley:** Rock (15 damage) and Nectar (18 damage) can attack simultaneously on early turns. Prioritize mitigating this 33-damage burst using `Backflip`, `Defend`, and `Neutralize+` before playing any slow scaling cards.
- **Beat the Round 3 Death Timer:** The enemies gain a massive +15 Strength buff at the start of Round 3. Treat this fight as a sprint. You must kill the primary attackers (Rock and Nectar) before this buff activates, or you will take rapid, lethal damage.
- **Exploit AoE and Shiv Bursts:** Single-target elimination is too slow. The cleanest wins rely heavily on sweeping the board in 2-3 turns using AoE (`Dagger Spray`, `Ricochet`) and massive Shiv generation (`Blade Dance`, `Storm of Steel`, `Fan of Knives`).
- **Targeting Priority:** If you cannot wipe the board completely, focus all lethal damage on Nectar and Rock first to remove their high base damage. Leave Silk (who spends turns applying debuffs) for last.
[Guide: multi:Crusher+Rocket] WR=61%, 33 episodes, confidence=0.90, v32
  - **Manage Facing**: You take 50% extra damage from the enemy behind you. Play your last targeted card on the most threatening attacker to face them and negate their Back Attack multiplier.
- **Understand the Cycles**: Both enemies follow strict 5-turn cycles. Rocket hits hard on R2, buffs on R3, attacks massively on R4, and sleeps on R5. Crusher applies Weak/Frail on R3, buffs on R4, and blocks on R5.
- **Prepare for Round 4**: R4 is the primary danger window. Rocket attacks for massive damage (often 49 if behind you), perfectly timed with Crusher's Frail debuff from R3. Retain your best mitigation for this turn.
- **Focus One Target**: Splitting damage is heavily punished. Burst one enemy down to break Surrounded, but be prepared: killing one triggers Crab Rage, granting the survivor 99 Block and +5 Strength.
[Guide: multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton] WR=88%, 41 episodes, confidence=0.90, v35
  - **Bypass the Cap:** "Hard to Kill" restricts single-hit attack damage to 9. Overcome this by utilizing high-volume multi-hits (Shivs via Blade Dance, Finisher) or continuous AoE Poison (Noxious Fumes, Corrosive Wave), which completely ignores the damage cap.
- **Focus Fire Early:** Direct your damage at a single Exoskeleton to secure an early kill by Round 2 or 3. Systematically reducing their numbers is vital to mitigate the escalating threat of their synchronized attack rounds.
- **Exploit Buff Windows:** The swarm frequently spends early turns applying Strength buffs rather than attacking. Capitalize on these zero-pressure windows to play scaling powers (Accuracy, Noxious Fumes) or unleash aggressive combos without needing to block.
- **Mitigate Synchronized Assaults:** High-loss rounds occur when multiple Exoskeletons attack simultaneously with scaled Strength (dealing 8-10+ damage each). Strictly reserve AoE mitigation like Piercing Wail for these heavy-hitting rounds to prevent massive damage spikes.
[Guide: multi:Flail Knight+Magi Knight+Spectral Knight] WR=100%, 12 episodes, confidence=0.90, v9
  - **Aura Management (Priority Targets):** Spectral Knight applies Hex on Round 1 (cards become Ethereal), and Magi Knight applies Dampen on Round 2 (cards are Downgraded). Focus one down quickly to lift their devastating aura. Killing Spectral Knight is usually the priority to prevent key card exhaustion.
- **The Round 5 Execution:** Round 5 is extremely deadly. Magi Knight will strike for 35 damage, and Flail Knight typically unleashes a multi-attack (hitting for 30+). You must kill at least one of them before Round 5 or prepare significant damage mitigation (e.g., Weakness, massive Block).
- **Flail Knight's Scaling:** Flail Knight buffs its Strength by 3 every other round. While its early single attacks are manageable, its multi-attacks on Round 5 and beyond scale dangerously. Use Weakness to stall its scaling if left for last.
- **Hex Hand Mitigation:** While Spectral Knight lives, unplayed cards exhaust. Avoid drawing heavily unless you have the energy to play the drawn cards.
[Guide: multi:Living Shield+Turret Operator] WR=100%, 34 episodes, confidence=0.90, v32
  - **Focus Turret First:** The Turret Operator is the scaling threat. Target it immediately with high-volume attacks (Shivs, Backstab, Assassinate). Clean wins (0 HP loss) typically involve killing the Turret by Round 2.
- **Mitigate Multi-Hits:** If the Turret survives past Round 1, prioritize applying Weak (Neutralize) or using Piercing Wail. Its 3x5 and 4x5 attacks are the primary source of HP loss.
- **Bypass or Break Rampart:** The Living Shield's 25 Rampart makes it a low-priority physical target. Use Poison to bypass the Shield's armor or save physical burst for the Turret. Only engage the Shield once the Turret is neutralized.
- **Discard-Draw over Setup:** Prioritize card cycle (Acrobatics, Calculated Gamble) to find burst damage or Weak applications. Delaying to play slow powers like Noxious Fumes or Snakebite while the Turret is active frequently leads to 10+ HP loss.
[Guide: multi:Queen+Torch Head Amalgam] WR=58%, 12 episodes, confidence=0.80, v11
  - This encounter features a strict execution timer; fighting beyond ~24 rounds results in instant defeat.
- The Queen scales Strength periodically, increasing her threat level each turn.
- The Torch Head Amalgam delivers dangerous multi-hit bursts (up to 3 hits) that bypass passive mitigation easily.
- The Queen consistently applies Chains of Binding, limiting card draw efficiency while stacking Frail and Weak on your character.
- Priority targets must shift based on phase: eliminate the Amalgam to mitigate burst damage, but maintain pressure on the Queen to prevent Strength scaling and meet the turn limit.
- Expect the Amalgam to respawn after death, creating cyclical danger zones.
- Avoid stalling for defense; the timer dictates pace. Surviving the initial Frail/Weak stacking phase (Rounds 1-4) is critical before entering high-damage windows.
[Guide: multi:Scroll of Biting+Scroll of Biting+Scroll of Biting] WR=94%, 35 episodes, confidence=0.90, v33
  - **Understand Paper Cuts:** Paper Cuts removes 1 Max HP for *every unblocked hit* you take. Full blocking is absolutely critical. Taking even 1 chip damage per hit on a multi-attack will permanently drain your Max HP multiple times.
- **Staggered Cycles:** The Scrolls independently cycle through three moves: Buff (+2 Strength), Multi-Attack, and Heavy Attack. Turn 1 always features exactly one of each intent.
- **The Turn 2 Threat:** The Scroll that Buffs on Turn 1 will predictably follow up with a Strength-scaled multi-attack (7x2) on Turn 2. Prioritize killing this specific Scroll first, or use Strength debuffs to heavily neutralize its multi-hits.
- **Burst Over Stall:** Long defensive setups are lethal. Since full blocking is mandatory and they continually cycle Strength buffs, you must focus fire to burst them down one at a time and reduce the incoming attack volume.

## Relevant Deck Guides
[Deck Guide: shiv] memories=87, confidence=0.85, v27
  - **Scaling & Hybrids:** `Accuracy` and `Phantom Blades` remain core damage engines. However, contrary to past advice, hybridizing with Poison (`Envenom`, Snecko Skull) is a highly viable and successful win condition.
- **Mandatory Defense:** `Afterimage` is the absolute linchpin for survival. Upgrading it (Innate is premium) provides essential passive block, freeing you from playing expensive defensive cards.
- **Cycle over Energy:** Winning decks consistently succeeded on base 3 energy! Focus on 0-cost generators (`Blade Dance`, `Cloak and Dagger`) paired with intense draw (`Calculated Gamble`, `Acrobatics`) rather than stressing over energy generation.
- **What to Avoid:** Aim for 23-24 cards. Strictly avoid `Art of War` (which natively clashes with Shiv spam) and high-cost block cards that choke your combo turns.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- Dagger Throw: 1-cost: 9 damage + draw 1 + discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Cycles deck while dealing damage. Flat 9 damage — does not scale with build progression.
- Knife Trap: Replays EVERY Shiv in your Exhaust pile. Functions as a lethal boss finisher. Base damage is low, so scale it first with Accuracy, Envenom, Vulnerable, or Tracking before unleashing the swarm.
- Calculated Gamble: 0-cost hand refresh. Triggers Sly on discarded cards. Incredible with Corrosive Wave. Warning: Under a 'no draw' debuff (like Doormaker's Scrutiny), this discards your hand and draws 0!
- Phantom Blades: Power: Your first Shiv played each turn deals bonus damage (+6). ALL Shivs Retain. This is primarily a combo/burst enabler, not just passive scaling. By hoarding 0-cost Shivs in hand over multiple turns, you can unleash massive zero-energy burst to push specific boss phases, bypass alternating immunities (like Test Subject's Nemesis), or secure lethal. High priority in Shiv decks.
- Leading Strike: 1-cost Attack: Deals damage and adds 1 Shiv to your hand. Provides solid immediate frontloaded damage while acting as a generator for Shiv synergies (Accuracy, Fan of Knives, Finisher). It offers immediate impact compared to purely generator cards like Cloak and Dagger, making it strong in early Act 1 where raw damage is necessary to burst down Elites.
- Backflip: 1-cost: block + draw 2. Defends and cycles simultaneously. The draw does not trigger Sly (draw is not discard). Pairs with Dexterity (Footwork) for scaled Block.
- Piercing Wail: A-tier defense. Its value multiplies per enemy attack instance. Against a single attack, it mitigates 6 damage (worse than Survivor). Against a 3x3 attack, it mitigates 18 damage. Save/retain it specifically for the scariest multi-hit turns. Do not waste it on single heavy hits unless lethal is imminent. Outstanding in boss fights and multi-enemy encounters.
- Corrosive Wave: Rare Skill: after playing Corrosive Wave, each card drawn THIS TURN applies Poison to ALL enemies. Pairs with draw cards (Prepared, Acrobatics, Backflip) — more draws in the same turn = more Poison stacks on all enemies. Best with high draw density in the turn it is played.
- Fan of Knives: Power: Gives 3 Shivs immediately and makes Shivs deal AoE. In single-target boss fights, the AoE does nothing, so its ONLY value is the 3 Shivs. Do NOT play this during invulnerability/sleep phases (like Lagavulin Matriarch) unless Phantom Blades is already active to retain the Shivs. Otherwise, they exhaust and the card is 100% wasted.
- Tracking: Scaling effect for extended fights. Requires reliable Weak application to function well — upgraded Neutralize (2 Weak) is the key enabler. Without consistent Weak sources, effectiveness is limited.
- Dagger Spray: 1-cost: multi-hit attack to ALL enemies. Each hit is a separate damage instance. Combos: Envenom (each hit applies Poison to all targets), Strength (added per hit). Does NOT benefit from Accuracy (not a Shiv).
- Envenom: Envenom is a severe trap for Shiv decks unless you already have massive card draw (Acrobatics/Calculated Gamble). It costs 2 energy and yields minimal poison per Shiv, vastly underperforming Accuracy. Drafting Envenom alongside Noxious Fumes in a Shiv deck causes fatal Act 2 deck bloat. Only draft in heavy cycle decks where you consistently play 8+ attacks per turn.
- Strangle: 1-cost: 8 damage + Strangle debuff (reduces enemy power generation, stacks). Both offensive damage and debuff utility. Stacking multiple Strangles compounds the debuff.
- Backstab: 0-cost Innate frontload. Exhausts when played. Against Turn 1 invincible enemies (like Door), skip playing it so it discards normally and can be drawn during later, vulnerable phases.
- Afterimage: Power: gain 1 Block per card played. Scales with cards-per-turn — Shiv generators (Blade Dance = 3 Shivs = 3 Block), 0-cost cards, and draw engines increase its output. Provides passive Block without spending energy on Block cards.
- Exterminate: Exterminate deals damage 4 times. It is NOT a Shiv and does NOT benefit from Phantom Blades, Accuracy, or Fan of Knives. It is a trap in Shiv-centric decks unless you have high flat Strength or Vulnerable. Do not draft it as a payoff for Shiv-specific scaling; prioritize real Shiv generators (Blade Dance) or Finisher instead.
- Leg Sweep: 2-cost: high Block + applies Weak. Scales with Dexterity for the Block portion. Pounce reduces the next Skill cost to 0 — play Pounce before Leg Sweep to play it for free.
- Flick-Flack: Sly: plays for free when discarded by a card effect. 1-cost 7 damage to ALL enemies. Effective cost is 0 energy via discard outlets (Acrobatics, Survivor, Prepared). AoE damage for free in discard builds.
- Storm of Steel: Discards your ENTIRE hand to generate Shivs. This destroys Retained cards (Well-Laid Plans), Nightmared copies, and defensive tools held for future turns. NEVER play this if you are holding essential mitigation (Apparition, Piercing Wail). Best used to convert unplayable cards, statuses (Slimed), or basic strikes into damage. Excellent synergy with Tingsha or Tough Bandages.
- Dodge and Roll: 1-cost: gain Block this turn and next turn. Provides Block over 2 turns, unlike Defend which is 1 turn only. Scales with Dexterity for both applications.
- Tools of the Trade: Triggers its discard at the END of your turn! This allows you to safely discard 'retained' curses like Doubt before their end-of-turn penalties activate. Also triggers Sly cards for free every turn.
- Accuracy: Power: +4 damage to all Shivs per copy. Base Shiv = 4 dmg → 8 with 1 copy, 12 with 2 copies. ONLY buffs Shiv cards — does NOT affect Ricochet, Dagger Spray, or other multi-hit attacks. Stacks: multiple copies multiply value linearly with Shiv generators (Blade Dance, Up My Sleeve, Infinite Blades, Fan of Knives).
- Expose: Expose removes ALL Block and Artifact. Do NOT waste it on Turn 1 against bosses that generate massive shields on Turn 2 (e.g., Ceremonial Beast's 150-Block Plow). Hold it until the enemy actually has the block or artifact you need to strip. Do not burn it blindly just for 2 Vulnerable.
- Memento Mori: 1-cost: 8 base damage + 4 extra damage per card discarded THIS turn. Requires heavy discard support (Acrobatics, Prepared, Survivor, Dagger Throw, Calculated Gamble) to deal meaningful damage. Without discard outlets, deals only 8 damage for 1 energy — below average.
- Noxious Fumes: Power: applies 2 Poison to ALL enemies at start of each turn passively. Scales linearly over time (turn 5 = 10 total Poison applied). AoE — affects all enemies simultaneously. Upgrade from 2 → 3 per turn is significant for long fights.
- Blade Dance: Premium Shiv engine. Best generator for Accuracy, Fan of Knives, Phantom Blades, Envenom, and Kunai-style scaling. In Shiv decks it is usually stronger than basic attacks or flat-damage filler; upgrade and protect it on remove/transform screens unless you already have redundant generation.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3978 | 0 | 3485 | 161 | 4494 | 27W|A1:16,A2:33,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2419 | 5 | 3530 | 1413 | 10 | 27W|A1:16,A2:34,A3:14,inc:10
- Dagger Throw | 1-cost: 9 damage + draw 1 + discard 1. The discard | 1090 | 0 | 1326 | 400 | 2191 | 15W|A1:4,A2:16,A3:5,inc:6
- Knife Trap | Replays EVERY Shiv in your Exhaust pile. Functions | 61 | 0 | 129 | 73 | 122 | 2W|A1:1,A2:2,A3:2,inc:1
- Calculated Gamble | 0-cost hand refresh. Triggers Sly on discarded car | 323 | 0 | 443 | 190 | 186 | 13W|A1:2,A2:12,A3:10,inc:4
- Phantom Blades | Power: Your first Shiv played each turn deals bonu | 317 | 0 | 368 | 113 | 20 | 12W|A1:2,A2:12,A3:8,inc:2
- Leading Strike | 1-cost Attack: Deals damage and adds 1 Shiv to you | 975 | 0 | 1201 | 336 | 1610 | 11W|A1:5,A2:13,A3:7,inc:2
- Backflip | 1-cost: block + draw 2. Defends and cycles simulta | 1721 | 0 | 1927 | 458 | 387 | 22W|A1:6,A2:22,A3:10,inc:3
- Piercing Wail | A-tier defense. Its value multiplies per enemy att | 501 | 0 | 1098 | 668 | 67 | 19W|A1:4,A2:18,A3:12,inc:7
- Corrosive Wave | Rare Skill: after playing Corrosive Wave, each car | 81 | 1 | 139 | 72 | 11 | 6W|A1:0,A2:1,A3:2
- Fan of Knives | Power: Gives 3 Shivs immediately and makes Shivs d | 162 | 0 | 238 | 97 | 9 | 9W|A1:1,A2:3,A3:2,inc:3
- Tracking | Scaling effect for extended fights. Requires relia | 63 | 0 | 103 | 43 | 8 | 2W|A1:0,A2:2,A3:1
- Dagger Spray | 1-cost: multi-hit attack to ALL enemies. Each hit  | 666 | 0 | 1056 | 478 | 2991 | 9W|A1:6,A2:16,A3:6,inc:1
- Envenom | Envenom is a severe trap for Shiv decks unless you | 53 | 0 | 134 | 90 | 0 | 1W|A1:0,A2:4,A3:4,inc:1
- Strangle | 1-cost: 8 damage + Strangle debuff (reduces enemy  | 353 | 0 | 412 | 111 | 506 | 8W|A1:2,A2:6,A3:6
- Backstab | 0-cost Innate frontload. Exhausts when played. Aga | 433 | 0 | 434 | 6 | 1169 | 13W|A1:3,A2:12,A3:3,inc:2
- Afterimage | Power: gain 1 Block per card played. Scales with c | 239 | 0 | 248 | 39 | 0 | 9W|A1:1,A2:5,A3:5,inc:3
- Exterminate | Exterminate deals damage 4 times. It is NOT a Shiv | 25 | 0 | 39 | 17 | 34 | 1W|A1:0,A2:3,A3:0,inc:1
- Leg Sweep | 2-cost: high Block + applies Weak. Scales with Dex | 395 | 2 | 562 | 225 | 13 | 9W|A1:3,A2:8,A3:5,inc:3
- Flick-Flack | Sly: plays for free when discarded by a card effec | 577 | 338 | 734 | 293 | 560 | 12W|A1:7,A2:12,A3:3,inc:3
- Storm of Steel | Discards your ENTIRE hand to generate Shivs. This  | 117 | 0 | 186 | 89 | 4 | 6W|A1:0,A2:3,A3:2,inc:1
- Dodge and Roll | 1-cost: gain Block this turn and next turn. Provid | 418 | 2 | 564 | 211 | 76 | 7W|A1:1,A2:7,A3:4,inc:3
- Tools of the Trade | Triggers its discard at the END of your turn! This | 107 | 0 | 140 | 62 | 8 | 6W|A1:0,A2:4,A3:3,inc:1
- Accuracy | Power: +4 damage to all Shivs per copy. Base Shiv  | 360 | 0 | 391 | 103 | 12 | 17W|A1:0,A2:10,A3:8,inc:5
- Expose | Expose removes ALL Block and Artifact. Do NOT wast | 281 | 1 | 255 | 22 | 12 | 9W|A1:4,A2:10,A3:4,inc:2
- Mad Science |  | 24 | 0 | 24 | 3 | 0 | 4W|A1:0,A2:0,A3:3
- Memento Mori | 1-cost: 8 base damage + 4 extra damage per card di | 111 | 0 | 158 | 77 | 697 | 2W|A1:0,A2:2,A3:1
- Noxious Fumes | Power: applies 2 Poison to ALL enemies at start of | 482 | 0 | 592 | 184 | 45 | 14W|A1:0,A2:9,A3:7,inc:2
- Blade Dance | Premium Shiv engine. Best generator for Accuracy,  | 1166 | 0 | 1212 | 220 | 22 | 16W|A1:9,A2:19,A3:10,inc:4

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F15(Phrog Parasite: ), F17(Vantom: WIN), F33(Crusher: WIN), F46(Flail Knight: ), F48(Torch Head Amalgam: )
- Core Combat Principles: F15(Phrog Parasite: ), F17(Vantom: WIN), F19(Tunneler: WIN), F20(Bowlbug (Rock): ), F22(The Obscura: WIN), F27(Exoskeleton: WIN), F28(Ovicopter: WIN), F30(Louse Progenitor: WIN), F31(Bowlbug (Rock): ), F33(Crusher: WIN), F35(Living Shield: WIN), F36(Scroll of Biting: WIN), F46(Flail Knight: ), F48(Torch Head Amalgam: )
- Deck Building Across the Run: F14(), F14(), F14(), F15(), F17(), F17(), F19(), F20(), F22(), F23(), F27(), F28(), F30(), F31(), F33(), F35(), F35(), F36(), F37(), F43(), F45(), F46()
- Map Routing and Path Planning: F14(), F14(), F18(), F18(), F20(), F22(), F23(), F25(), F30(), F34(), F34(), F36(), F36()
- Never Smith Upgraded Cards: F16(), F25(), F29(), F32(), F42(), F44(), F47()
- Phantom Blades Scaling Limit: F14(), F14(), F15(), F17(), F19(), F20(), F22(), F23(), F27(), F28(), F30(), F31(), F33(), F35(), F36(), F37(), F46()
- Rest Site and Event Decisions: F16(), F25(), F29(), F32(), F42(), F44(), F47()
- Silent - Combat Sequencing: F15(Phrog Parasite: ), F17(Vantom: WIN), F19(Tunneler: WIN), F20(Bowlbug (Rock): ), F22(The Obscura: WIN), F27(Exoskeleton: WIN), F28(Ovicopter: WIN), F30(Louse Progenitor: WIN), F31(Bowlbug (Rock): ), F33(Crusher: WIN), F35(Living Shield: WIN), F36(Scroll of Biting: WIN), F46(Flail Knight: ), F48(Torch Head Amalgam: )
- Silent - Draft and Shop Rules: F14(), F14(), F14(), F15(), F17(), F17(), F19(), F20(), F22(), F23(), F27(), F28(), F30(), F31(), F33(), F35(), F35(), F36(), F37(), F43(), F45(), F46()
- Silent - Route Priorities: F14(), F14(), F18(), F18(), F20(), F22(), F23(), F25(), F30(), F34(), F34(), F36(), F36()
- Vantom Mechanics: F17(Vantom: WIN)

## Dynamic Tools
- block_sufficiency_check: 19635 calls, 19635 successes
- poison_block_survival_plan: 4588 calls, 4588 successes
- poison_kill_and_survive_check: 19088 calls, 19088 successes
- poison_survival_analysis: 21498 calls, 20401 successes
- poison_turns_to_kill: 21541 calls, 20401 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.