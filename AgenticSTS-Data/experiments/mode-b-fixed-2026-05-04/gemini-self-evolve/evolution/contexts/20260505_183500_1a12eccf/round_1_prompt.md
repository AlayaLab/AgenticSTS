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
Result: VICTORY (fitness: 233.9)
Combats won: 24/24
Run duration: 6395.0s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: rely on strikes/defends while finding early damage to survive Act 1 elites. Focus on drafting high-damage attacks.
- [card_select] Foundation plan: rely on basic strikes and defends while aggressively drafting high-damage frontload attacks to survive Act 1 elites. With Prowess secured, multi-hit attacks and cheap block become more valuable.
- [map] Foundation phase: drafting frontloaded damage and consistent block to survive early hallways while building a gold base for a mid-act shop.
### F2
- [card_reward] Foundation plan: rely on basic strikes and defends while aggressively drafting high-damage frontload attacks to survive Act 1 elites. With Prowess secured, multi-hit attacks and cheap block become more valuable.
### F3
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; prioritize high-impact attacks for early Elites.
- [map] Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. I am aiming for 4-5 early combats before a major shop or elite to ensure the deck has enough impact cards to survive Act 1's scaling threats.
### F4
- [event] Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. Clumsy curse means we need to be slightly more careful about draw. We still need impactful damage cards to handle upcoming Elites.
### F5
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F6
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation phase: prioritizing standard monster encounters to draft essential frontloaded damage and block cards while maintaining a healthy HP buffer for Act 1 elites.
### F7
- [rest_site] Foundation phase: prioritize frontloaded damage and block. Play Prowess early to scale attacks and defenses, relying on Predator and Dagger Spray for burst damage. Need one more solid damage or block card; avoid overly situational cards.
### F8
- [card_reward] Foundation plan: scale with Prowess+ and use cheap/multi-hit attacks and efficient block to survive. Need card removals and cheap block/draw to support the core scaling.
### F9
- [rest_site] Foundation phase: prioritizing frontloaded damage and block cards while looking for a coherent damage engine. Play priority: maintain Weak on dangerous enemies and use discard (Survivor, Dagger Throw) to filter past the Clumsy curse. Avoid adding too many expensive cards without an energy relic.
- [map] Foundation phase: focusing on standard monster encounters to draft frontloaded damage and block. Clumsy curse necessitates careful draw management; looking for high-impact damage and scaling to handle the upcoming Act 1 elites.
### F10
- [map] Foundation phase: prioritizing hallway fights and card rewards for frontloaded damage and block. Clumsy curse means we need to be careful about draw. Currently hunting for impactful damage cards to handle Elites while using Rest Sites to Smith key upgrades.
### F11
- [rest_site] Foundation phase: relying on frontloaded damage and Prowess+ for stats while using discard to filter past Clumsy. Needs a cohesive scaling engine and energy generation to support expensive cards like Predator.
### F12
- [card_reward] Foundation plan: survive with frontload and Prowess while looking for multi-attacks and efficient scaling; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F13
- [rest_site] Foundation phase: relying on frontloaded physical damage and weak application to clear Act 1 fights. Need scaling damage or strong block solutions for the boss, and card draw to mitigate the Clumsy curse.
- [map] Foundation phase: prioritizing frontloaded damage and block cards in hallway fights to prepare for Act 1 Elite and Boss. The deck is currently seeking consistent damage to minimize chip damage while navigating around the Clumsy curse.
### F14
- [card_reward] Foundation plan: survive with frontload, block efficiently, and use Prowess+ for both offense and defense scaling. Leverage Ice Cream for big energy turns. Needs a cohesive scaling engine; avoid generic attacks.
### F15
- [hand_select] Discarding status cards that have negative 'in-hand' effects is a priority to conserve HP.
- [card_select] Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. Clumsy curse means we need to be slightly more careful about draw. We still need impactful damage cards to handle upcoming Elites.
- [card_reward] Foundation phase: relying on frontloaded physical damage, weak application, and Prowess+ scaling. Keep the deck lean to cycle into key cards; skip low-impact additions.
### F16
- [rest_site] Foundation phase: relying on frontloaded physical damage and weak application. Need scaling damage or strong block solutions for upcoming Acts, and card draw to mitigate the Clumsy curse.
### F17
- [card_reward] Transitioning to a committed Shiv/Attack plan with Prowess+ and Nunchaku; prioritize multi-hit cards, draw, and discard synergies to leverage Strength, while actively removing basic attacks.
### F18
- [event] Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.
- [map] Foundation phase: leveraging high gold reserves to find key scaling pieces at the upcoming shop while prioritizing block and frontloaded damage to survive the initial Act 2 hallway spike.
### F19
- [card_reward] Foundation plan: transition into a Shiv/Strength scaling engine using Prowess+. Prioritize card draw, Shiv generators, and multi-hits to maximize Strength benefits, while avoiding slow poison or heavy single-hit cards.
- [map] Foundation phase: relying on frontloaded physical damage and weak application; need scaling damage and card draw to mitigate Clumsy while prioritizing HP preservation through non-combat nodes.
### F20
- [card_reward] Committed to scaling with Prowess+ (Strength/Dexterity) and utilizing Ice Cream/Energy relics. Prioritize multi-hit attacks to leverage Strength and strong mitigation to stall for Prowess. Focus on removing Strikes/Defends to draw Prowess faster.
### F21
- [hand_select] Finishing the fight quickly to avoid future damage.
- [card_reward] Foundation phase: relying on Prowess+ for str/dex scaling and Ice Cream for energy hoarding. Focus on acquiring card draw (Acrobatics, Backflip) and removing basic cards to cycle faster into our scaling.
### F22
- [card_select] Poison scaling (Noxious Fumes) is established. Focus on survival, block, and deck thinning. Avoid generic attacks and prioritize card draw/discard synergies.
### F23
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [card_reward] Foundation plan: Use massive starting energy and Ice Cream to play many cards per turn. Prioritize card draw and removals to continuously cycle our deck. Look for a core scaling engine like multi-hit/shivs for Prowess+ or heavy poison.
### F24
- [card_reward] Committed shiv/strength engine with Prowess+ and Nunchaku/Pen Nib: play Prowess early, then use Shiv generators to output massive scaling damage and block with Dexterity.
### F25
- [event] Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.
- [card_reward] Foundation plan: surviving with robust mitigation (Leg Sweep, Piercing Wail) and scaling with Noxious Fumes/Shivs. Focus on removing Strikes to draw defensive and scaling pieces faster. Needs consistent draw.
### F27
- [event] Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.
### F28
- [card_reward] Committed to Shivs and energy banking with Ice Cream. Use extra energy to cycle with Expertise+ and Finesse. Stack Accuracy/Prowess+ and unleash high-damage Shivs. Need more card draw and card removals.
- [map] Foundation phase: relying on frontloaded physical damage and weak application. Need scaling damage or strong block solutions for upcoming Acts, and card draw to mitigate the Clumsy curse.
### F29
- [rest_site] Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy to play out our hand, while saving excess for high-cost defense (Leg Sweep). Needs more card draw to fully utilize the massive energy reserves.
- [map] Committed Ice Cream energy-banking strategy: accumulate energy on quiet turns to fuel high-impact cycles of Predator+ and Leg Sweep, prioritizing card draw to ensure banked energy is never wasted.
### F30
- [card_reward] Committed Shiv/Energy plan: play defensively while setting up Accuracy/Prowess+ scaling, then use massive Shiv generation and energy banking (Ice Cream) to overwhelm enemies. Avoid bloated basic attacks and focus on card draw to find the engine quickly.
### F31
- [event] Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy to play out our hand, while saving excess for high-cost defense (Leg Sweep). Needs more card draw to fully utilize the massive energy reserves.
- [card_select] Committed to a Shiv engine backed by Prowess and Accuracy. Prioritize Shiv generation, efficient Block with Dexterity, and let Fumes scale in longer fights.
### F32
- [rest_site] Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.
### F33
- [card_select] Committed to Ice Cream energy-banking: rely on massive starting energy and banking to play huge hands. Prioritize abundant card draw (Acrobatics, Backflip) and X-cost or high-impact cards to turn excess energy into damage and defense. Need consistent scaling damage to complement Prowess+.
- [hand_select] Managing hand space for the Shiv engine while facing a 23 damage turn.
- [card_reward] Committed to Ice Cream energy-banking and Shiv/Poison hybrid: rely on massive starting energy and banking to play huge hands. Prioritize abundant card draw and X-cost/high-impact cards. Avoid adding low-impact common attacks.
### F34
- [event] Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.
- [map] Committed Ice Cream energy-banking strategy: accumulate energy on quiet turns to fuel high-impact cycles of Predator+ and Leg Sweep, prioritizing card draw to ensure banked energy is never wasted; focus on finding more draw power to capitalize on banked energy.
### F35
- [hand_select] Targeting Scroll 1 to finish it off this turn.
- [hand_select] Prioritizing Shiv generation and card draw to maximize the Accuracy synergy.
- [card_reward] Committed to Ice Cream energy banking and Shivs with Prowess+. Prioritize heavy card draw and high-impact cards to dump excess energy. Skip low-impact or 0-cost cards since energy is abundant and draw is the real bottleneck.
### F36
- [event] Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.
### F38
- [event] Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.
### F39
- [card_reward] Committed to Shiv/Energy Ice Cream plan: stall and draw heavily with Acrobatics/Backflip while banking massive energy, using Shivs and Prowess+ to scale up and burst enemies. Skip minor attacks and prioritize heavy card draw or premium rare powers.
### F40
- [event] Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.
- [card_select] Committed Shiv/Energy plan: We have massive energy generation and Shivs/Accuracy for damage. Look to thin out basic cards and acquire card draw to utilize our huge energy pool.
### F41
- [map] Committed Shiv and Ice Cream engine: prioritize frontloaded card draw and defensive consistency to leverage banked energy, avoiding Act 3 Elites to preserve HP for the final boss.
### F42
- [card_reward] Focus on finding fast frontload damage or high-value draw to burst down the Queen in Act 3 boss. Skip slow scaling powers and clunky cards.
### F43
- [card_reward] Committed Shiv/Str/Dex plan: cycle rapidly using surplus energy to play Accuracy and Prowess+ multiple times. Play shivs aggressively to trigger Nunchaku and Pen Nib. Prioritize card removal to accelerate scaling setup.
### F44
- [rest_site] Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively. Need to thin out Strikes to improve consistency.
### F45
- [card_reward] Committed plan: stall and build up strength/dex with Prowess+, using Shivs from Blade Dance and Cloak and Dagger alongside Ice Cream energy banking to clear enemies. Discard cards to trigger Tough Bandages for extra defense. Avoid adding low-impact cards.
- [map] Committed Shiv and Ice Cream engine: bank energy on easy turns to fuel expensive defense or massive draw sequences. Priority is finding more card draw to convert banked energy into impact and removing basic strikes to improve consistency.
### F46
- [card_select] Committed plan: generate huge energy and draw through Adrenaline/Expertise, scaling with Accuracy/Shivs and Prowess. Continue removing Strikes to cycle faster.
### F47
- [rest_site] Committed shiv and energy-banking engine: play Adrenaline and zero-cost draw to build energy with Ice Cream, deploy shivs for damage, and use the banked energy for Leg Sweep or finishing with Murder. Keep the deck thin and focus on playing high-draw turns.
### F48
- [hand_select] Prioritizing non-Bound cards and energy generation to maximize the turn's potential.
- [hand_select] Queen is at 58 HP. Keeping Shiv generators and high-impact skills is priority over basic damage.

### Combat Decision Digest (24 combats)
F2 [monster] multi:Leaf Slime (S)+Twig Slime (M)+Twig Slime (S) (5R, HP 56->56, loss=0, WIN)
  R1[Twig Slime (S): Atk(4)+Twig Slime (M): StatusCard(1)+Leaf Slime (S): StatusCard(1)]: Prowess(power:+Strength(1),power:+Dexterity(1))->Strike(7dmg)->Neutralize->Strike(7dmg) | dealt=17 taken=0
  R2[Twig Slime (M): Atk(11)+Leaf Slime (S): Atk(3)]: Defend(+6blk)->Defend(+6blk)->Strike | dealt=4 taken=0
  R3[Twig Slime (M): Atk(11)]: Neutralize(4dmg,1+Weak(1))->Defend(+6blk)->Defend(+6blk)->Defend(+6blk) | dealt=4 taken=0
  R4[Twig Slime (M): StatusCard(1)]: Slimed(exhaust:1)->Strike(7dmg)->Strike(7dmg) | dealt=14 taken=0
  R5[Twig Slime (M): Atk(11)]: Strike(7dmg)->Strike(power:-Strength,power:-Dexterity) | dealt=7 taken=0

F3 [monster] Fuzzy Wurm Crawler (5R, HP 56->54, loss=2, WIN)
  R1[Fuzzy Wurm Crawler: Atk(4)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Dagger Spray(8dmg)->Strike(6dmg) | dealt=17 taken=0
  R2[Fuzzy Wurm Crawler: Buff]: Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=6 taken=0
  R3[Fuzzy Wurm Crawler: Atk(11)]: Prowess(power:+Strength(1),power:+Dexterity(1))->Neutralize(4dmg,1+Weak(1))->Defend(+6blk)->Strike(7dmg) | dealt=11 taken=2
  R4[Fuzzy Wurm Crawler: Atk(11)]: Dagger Spray(10dmg)->Defend(+6blk)->Survivor(+9blk) | dealt=10 taken=0
  R5[Fuzzy Wurm Crawler: Buff]: Dagger Spray(10dmg)->Strike(power:-Strength,power:-Dexterity) | dealt=10 taken=0

F5 [monster] Shrinker Beetle (5R, HP 54->54, loss=0, WIN)
  R1[Shrinker Beetle: DebuffStrong]: Prowess(power:+Strength(1),power:+Dexterity(1))->Dagger Spray(10dmg)->Strike(7dmg) | dealt=17 taken=0
  R2[Shrinker Beetle: Atk(7)]: Defend(+6blk) | dealt=0 taken=0
  R3[Shrinker Beetle: Atk(13)]: Neutralize(2dmg,1+Weak(1))->Defend(+6blk)->Defend(+6blk)->Strike(4dmg) | dealt=6 taken=0
  R4[Shrinker Beetle: Atk(7)]: Survivor(+9blk)->Dagger Spray(6dmg)->Strike(4dmg) | dealt=10 taken=0
  R5[Shrinker Beetle: Atk(13)]: Strike(4dmg)->Strike(power:-Strength,power:-Dexterity,power:-Shrink) | dealt=4 taken=0

F6 [monster] multi:Nibbit+Nibbit (3R, HP 54->54, loss=0, WIN)
  R1[Nibbit: Atk(6), Defend+Nibbit: Buff]: Neutralize->Dagger Spray(8dmg)->Strike->Survivor(+8blk) | dealt=8 taken=0
  R2[Nibbit: Buff+Nibbit: Atk(14)]: Prowess(power:+Strength(1),power:+Dexterity(1))->Shiv+(7dmg,exhaust:1)->Shiv+(7dmg)->Shiv+(7dmg)->Strike(7dmg)->Strike(1-Strength) | dealt=28 taken=0
  R3[Nibbit: Atk(14)]: Predator(16dmg,power:+Draw Cards Next Turn(2))->Dagger Throw(power:-Strength,power:-Dexterity,power:-Draw Cards Next Turn) | dealt=16 taken=0

F8 [monster] Mawler (4R, HP 54->40, loss=14, WIN)
  R1[Mawler: Atk(4x2=8)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=9 taken=0
  R2[Mawler: Atk(14)]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Dagger Spray(8dmg) | dealt=23 taken=14
  R3[Mawler: Debuff]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Poisoned Stab(8dmg,1+Poison(3))->Dagger Throw(11dmg) | dealt=8 taken=0
  R4[Mawler: Atk(21)]: Predator(17dmg,power:+Draw Cards Next Turn(2))->Strike(power:-Strength,power:-Dexterity,power:-Vulnerable,power:-Draw Cards Next Turn) | dealt=17 taken=0

F12 [elite] Bygone Effigy (7R, HP 40->28, loss=12, WIN)
  R1[Bygone Effigy: Sleep]: none | dealt=0 taken=0
  R2[Bygone Effigy: Buff]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Neutralize+(6dmg,1+Weak(2))->Predator+(26dmg,power:+Draw Cards Next Turn(2)) | dealt=32 taken=0
  R3[Bygone Effigy: Atk(17)]: Defend(+7blk)->Survivor(+10blk)->Strike(9dmg) | dealt=9 taken=0
  R4[Bygone Effigy: Atk(23)]: Dagger Throw(11dmg)->Defend(+7blk)->Defend(+7blk)->Poisoned Stab(10dmg,1+Poison(3))->Survivor(+10blk) | dealt=10 taken=0
  R5[Bygone Effigy: Atk(23)]: Dagger Throw(11dmg)->Defend(+7blk)->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=2
  R6[Bygone Effigy: Atk(23)]: Neutralize+(6dmg,1+Weak(2))->Defend(+7blk)->Dagger Spray(14dmg)->Strike(10dmg) | dealt=30 taken=10
  R7[Bygone Effigy: Atk(17)]: Dagger Throw(11dmg)->Strike(power:-Strength,power:-Dexterity) | dealt=0 taken=0

F14 [monster] multi:Flyconid+Snapping Jaxfruit (3R, HP 49->49, loss=0, WIN)
  R1[Snapping Jaxfruit: Atk(3), Buff+Flyconid: Atk(11)]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Backstab(13dmg,exhaust:1)->Defend(+7blk)->Defend(+7blk)->Strike(8dmg) | dealt=21 taken=0
  R2[Snapping Jaxfruit: Atk(5), Buff+Flyconid: Debuff]: Dagger Spray(12dmg)->Predator+(22dmg,power:+Draw Cards Next Turn(2)) | dealt=44 taken=0
  R3[Flyconid: Atk(12), Debuff]: Neutralize+(6dmg,1+Weak(2))->Strike(power:-Strength,power:-Dexterity,power:-Vulnerable) | dealt=6 taken=0

F15 [elite] Phrog Parasite (7R, HP 49->49, loss=0, WIN)
  R1[Phrog Parasite: StatusCard(3)]: Backstab(11dmg,exhaust:1)->Neutralize+(4dmg,1+Weak(2)) | dealt=15 taken=0
  R2[Phrog Parasite: Atk(3x4=12)]: Dagger Spray(8dmg)->Defend(+5blk)->Defend(+5blk)->Defend(+5blk)->Dagger Throw(9dmg) | dealt=17 taken=0
  R3[Phrog Parasite: StatusCard(3)]: Dagger Throw(9dmg)->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike | dealt=21 taken=0
  R4[Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)+Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Defend(+7blk)->Defend(+7blk)->Dagger Throw | dealt=0 taken=0
  R5[Wriggler: Buff, StatusCard(1)+Wriggler: Atk(8)+Wriggler: Buff, StatusCard(1)+Wriggler: Atk(8)]: Dagger Spray(12dmg)->Neutralize+->Defend(+7blk)->Survivor(+10blk) | dealt=12 taken=0
  R6[Wriggler: Atk(8)+Wriggler: Buff, StatusCard(1)+Wriggler: Buff, StatusCard(1)]: Strike->Strike(8dmg)->Strike(1+Weak(1))->Shadow Step(power:+Shadow Step(1)) | dealt=8 taken=0
  R7[Wriggler: Atk(10)]: Strike(power:-Strength,power:-Dexterity,power:-Double Damage) | dealt=0 taken=0

F17 [boss] Vantom (10R, HP 70->43, loss=27, WIN)
  R1[Vantom: Atk(7)]: Backstab(1dmg,1Slippery(9→8),exhaust:1)->Poisoned Stab(1dmg,2Slippery(8→7),+Poison(3))->Leg Sweep(+11blk,1+Weak(2)) | dealt=2 taken=0
  R2[Vantom: Atk(4x2=8)]: Neutralize+(1dmg,2Slippery(6→5),Weak(1→3))->Defend(+5blk)->Dagger Throw(1dmg,1Slippery(5→4))->Strike(1dmg,1Slippery(4→3))->Strike(1dmg,1Slippery(3→2)) | dealt=3 taken=3
  R3[Vantom: Atk(20), StatusCard(3)]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Dagger Spray(7dmg,1-Slippery)->Survivor(+10blk) | dealt=7 taken=10
  R4[Vantom: Buff]: Dagger Spray(12dmg)->Strike(8dmg)->Strike(8dmg) | dealt=28 taken=0
  R5[Vantom: Atk(9)]: Defend(+7blk)->Defend(+7blk)->Strike(8dmg) | dealt=8 taken=0
  R6[Vantom: Atk(8x2=16)]: Dagger Throw(11dmg)->Predator+(22dmg,power:+Draw Cards Next Turn(2))->Survivor(+10blk) | dealt=22 taken=6
  R7[Vantom: Atk(29), StatusCard(3)]: Neutralize+(6dmg,1+Weak(2))->Leg Sweep(+13blk,1Weak(2→4))->Poisoned Stab(8dmg,1+Poison(3)) | dealt=14 taken=8
  R8[Vantom: Buff]: Dagger Throw(11dmg)->Strike(8dmg)->Strike(8dmg) | dealt=16 taken=0
  R9[Vantom: Atk(8)]: Defend(+7blk)->Strike(8dmg)->Dagger Throw(11dmg)->Defend(+7blk) | dealt=8 taken=0
  R10[Vantom: Atk(7x2=14)]: Predator+(power:-Strength,power:-Dexterity) | dealt=0 taken=0

F19 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (2R, HP 64->64, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Dagger Spray(12dmg)->Backstab(9dmg,exhaust:1)->Poisoned Stab->Neutralize+(6dmg,1+Weak(2))->Strike(8dmg)->Survivor(+10blk) | dealt=35 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff]: Storm of Steel->Shiv(1-Weak,exhaust:1)->Shiv(6dmg)->Shiv(6dmg)->Shiv(power:-Strength,power:-Dexterity) | dealt=12 taken=0

F20 [monster] multi:Bowlbug (Egg)+Bowlbug (Rock) (3R, HP 64->64, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Egg): Atk(7), Defend]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Backstab(13dmg,exhaust:1)->Dagger Throw->Dagger Throw(11dmg)->Defend(+7blk)->Defend(+7blk)->Strike(8dmg) | dealt=21 taken=0
  R2[Bowlbug (Rock): Stun]: Dagger Spray(12dmg)->Cloak and Dagger+(+8blk)->Shiv(6dmg,exhaust:1)->Shiv(6dmg) | dealt=24 taken=0
  R3[Bowlbug (Rock): Atk(15)]: Strike(power:-Strength,power:-Dexterity,power:-Plating) | dealt=0 taken=0

F21 [monster] Spiny Toad (5R, HP 64->64, loss=0, WIN)
  R1[Spiny Toad: Buff]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Backstab(13dmg,exhaust:1)->Neutralize+(6dmg,+1energy,1+Weak(2))->Dagger Spray(12dmg)->Strike(8dmg)->Dagger Throw(11dmg)->Strike(8dmg) | dealt=47 taken=0
  R2[Spiny Toad: Atk(17)]: Leg Sweep(+13blk,1Weak(1→3))->Survivor(+10blk) | dealt=0 taken=0
  R3[Spiny Toad: Atk(12)]: Defend(+7blk)->Defend(+7blk)->Strike(8dmg)->Strike(8dmg) | dealt=16 taken=0
  R4[Spiny Toad: Buff]: Poisoned Stab(8dmg,1+Poison(3))->Cloak and Dagger+(+8blk)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Dagger Throw(11dmg)->Storm of Steel->Shiv(6dmg) | dealt=26 taken=0
  R5[Spiny Toad: Atk(23)]: none | dealt=0 taken=0

F23 [monster] multi:Chomper+Chomper (5R, HP 64->59, loss=5, WIN)
  R1[Chomper: Atk(8x2=16)+Chomper: StatusCard(3)]: Noxious Fumes(power:+Noxious Fumes(2))->Backstab(exhaust:1)->Defend(+5blk)->Defend(+5blk)->Defend(+5blk)->Dagger Throw->Neutralize+ | dealt=0 taken=1
  R2[Chomper: StatusCard(3)+Chomper: Atk(8x2=16)]: Burst(power:+Burst(1))->Cloak and Dagger+(+12blk,power:-Burst)->Blade Dance(exhaust:1)->Dagger Spray(8dmg)->Shiv(exhaust:1)->Shiv*3->Shiv(+1energy)->Shiv*2->Strike->Strike(6dmg) | dealt=14 taken=4
  R3[Chomper: StatusCard(3)]: Finesse(+4blk)->Dagger Throw(9dmg)->Poisoned Stab(6dmg,1+Poison(3))->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Leg Sweep(+11blk,1+Weak(2)) | dealt=6 taken=0
  R4[Chomper: Atk(6x2=12)]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=20 taken=0
  R5[Chomper: StatusCard(3)]: Strike(6dmg)->Strike(power:-Noxious Fumes) | dealt=6 taken=0

F24 [elite] multi:Decimillipede+Decimillipede+Decimillipede (5R, HP 59->45, loss=14, WIN)
  R1[Decimillipede: Atk(8), Debuff+Decimillipede: Atk(5x2=10)+Decimillipede: Atk(6), Buff]: Backstab(11dmg,+1energy,exhaust:1)->Neutralize+(4dmg,1+Weak(2))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Expertise+->Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Dagger Spray(24dmg)->Dagger Throw(9dmg)->Dagger Throw(9dmg)->Poisoned Stab(6dmg,1+Poison(3)) | dealt=73 taken=0
  R2[Decimillipede: Atk(6), Buff+Decimillipede: Atk(6), Debuff+Decimillipede: Atk(7x2=14)]: Finesse(+4blk)->Defend(+5blk)->Defend(+5blk)->Dodge and Roll(+4blk,power:+Block Next Turn(4)) | dealt=0 taken=4
  R3[Decimillipede: Atk(7x2=14)+Decimillipede: Atk(6), Buff+Decimillipede: Atk(10), Debuff]: Blade Dance(exhaust:1)->Shiv(3dmg)->Shiv(3dmg,+1energy)->Shiv(3dmg)->Leg Sweep(+11blk,1+Weak(2))->Survivor(+8blk) | dealt=9 taken=3
  R4[Decimillipede: Atk(7), Debuff+Decimillipede: Atk(7x2=14)+Decimillipede: Atk(8), Buff]: Neutralize+(3dmg,1+Weak(2))->Dagger Throw(6dmg,1-Strength)->Finesse(+4blk)->Dagger Throw(6dmg)->Cloak and Dagger+(+6blk)->Shiv(3dmg)->Shiv(3dmg) | dealt=9 taken=7
  R5[Decimillipede: Atk(8), Buff+Decimillipede: Atk(7), Debuff]: Storm of Steel->Shiv(2dmg,1-Strength)->Shiv(3dmg,power:-Weak,2-Strength,-Weak) | dealt=2 taken=0

F25 [monster] Mysterious Knight (4R, HP 45->41, loss=4, WIN)
  R1[Mysterious Knight: Atk(21)]: Backstab(5dmg,exhaust:1)->Neutralize+(4dmg,+1energy,1+Weak(2))->Dagger Spray(8dmg)->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Strike(6dmg)->Expertise+->Prowess+(power:+Strength(2),power:+Dexterity(2))->Leg Sweep(+13blk,1Weak(2→4))->Poisoned Stab(8dmg,1+Poison(3)) | dealt=31 taken=0
  R2[Mysterious Knight: Buff]: Noxious Fumes(power:+Noxious Fumes(2))->Strike(2dmg) | dealt=2 taken=0
  R3[Mysterious Knight: Atk(18)]: Leading Strike->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Defend(+7blk)->Defend(+7blk)->Dagger Throw(22dmg) | dealt=12 taken=4
  R4[Mysterious Knight: Atk(13x2=26)]: Blade Dance(exhaust:1)->Cloak and Dagger+(+8blk)->Dagger Throw(7dmg)->Shiv(6dmg,+1energy)->Shiv(6dmg)->Shiv(6dmg)->Shiv(power:-Strength,power:-Dexterity,power:-Noxious Fumes) | dealt=18 taken=0

F28 [monster] Hunter Killer (5R, HP 27->28, loss=0, WIN)
  R1[Hunter Killer: Debuff]: Backstab(11dmg,exhaust:1)->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Strike(6dmg)->Strike(12dmg)->Dagger Throw(9dmg)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Storm of Steel | dealt=48 taken=0
  R2[Hunter Killer: Atk(7x3=21)]: Leg Sweep(+11blk,power:+Strength(-1),power:+Dexterity(-1),1+Weak(2))->Defend(+4blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Noxious Fumes(power:Strength(-2→-3),power:Dexterity(-2→-3),power:+Noxious Fumes(2)) | dealt=0 taken=0
  R3[Hunter Killer: Atk(5x3=15)]: Defend(+5blk,power:+Strength(-1),power:+Dexterity(-1))->Predator+(19dmg,power:Strength(-1→-2),power:Dexterity(-1→-2),power:+Draw Cards Next Turn(2))->Dagger Throw(7dmg)->Piercing Wail(power:Strength(-3→-4),power:Dexterity(-3→-4),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Blade Dance(power:Strength(-4→-5),power:Dexterity(-4→-5),exhaust:1)->Shiv(power:Strength(-5→-6),power:Dexterity(-5→-6))->Shiv(power:Strength(-6→-7),power:Dexterity(-6→-7))->Shiv(power:Strength(-7→-8),power:Dexterity(-7→-8)) | dealt=19 taken=0
  R4[Hunter Killer: Atk(17)]: Poisoned Stab(12dmg,power:+Strength(-1),power:+Dexterity(-1),1Poison(3→6))->Neutralize+(3dmg,power:Strength(-1→-2),power:Dexterity(-1→-2),1+Weak(2))->Finesse(+2blk,power:Strength(-2→-3),power:Dexterity(-2→-3))->Survivor(+5blk) | dealt=15 taken=0
  R5[Hunter Killer: Atk(5x3=15)]: Predator+(power:-Tender,power:-Noxious Fumes,power:-Plating) | dealt=0 taken=0

F30 [elite] Entomancer (5R, HP 49->48, loss=1, WIN)
  R1[Entomancer: Atk(3x7=21)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Backstab(11dmg,exhaust:1)->Poisoned Stab(6dmg,1+Poison(3))->Dagger Throw(9dmg) | dealt=17 taken=0
  R2[Entomancer: Atk(18)]: Defend(+5blk)->Accuracy(power:+Accuracy(4))->Blade Dance(exhaust:1)->Shiv(8dmg,exhaust:1)->Shiv(8dmg)->Shiv(8dmg)->Strike(6dmg)->Predator+(40dmg,power:+Draw Cards Next Turn(2)) | dealt=70 taken=2
  R3[Entomancer: Buff]: Cloak and Dagger+(+6blk)->Shiv(8dmg)->Shiv(8dmg,+1energy)->Dagger Spray(8dmg)->Strike(6dmg)->Strike(6dmg) | dealt=36 taken=0
  R4[Entomancer: Atk(4x7=28)]: Finesse(+4blk)->Leg Sweep(+11blk,1+Weak(2))->Defend(+5blk) | dealt=0 taken=0
  R5[Entomancer: Atk(14)]: Strike(6dmg)->Strike(power:-Plating,power:-Accuracy) | dealt=6 taken=0

F33 [boss] multi:Crusher+Rocket (14R, HP 69->8, loss=61, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Cloak and Dagger+(+6blk)->Neutralize+(4dmg,1+Weak(2))->Shiv(4dmg,exhaust:1)->Backstab(22dmg,exhaust:1)->Dagger Throw(9dmg)->Leg Sweep(+11blk,1+Weak(2))->Shiv(4dmg,+1energy) | dealt=34 taken=0
  R2[Crusher: Atk(3)+Rocket: Atk(20)]: Thinking Ahead->Dagger Spray(16dmg)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Poisoned Stab(6dmg,1+Poison(3))->Strike(6dmg)->Strike(6dmg)->Strike(12dmg) | dealt=57 taken=17
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Leg Sweep(+11blk,1+Weak(2))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R4[Crusher: Buff+Rocket: Atk(49)]: Finesse(+3blk)->Noxious Fumes(power:+Noxious Fumes(2))->Cloak and Dagger+(+4blk)->Blade Dance(exhaust:1)->Shiv(3dmg,+1energy)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg)->Expertise+->Prowess+(power:+Strength(2),power:+Dexterity(2))->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Survivor(+7blk) | dealt=15 taken=15
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Dagger Throw(8dmg)->Leg Sweep(+9blk,1+Weak(2)) | dealt=0 taken=0
  R6[Crusher: Atk(10)+Rocket: Atk(7)]: Cloak and Dagger+(+8blk)->Defend(+7blk)->Poisoned Stab(8dmg,1Poison(3→6))->Shiv | dealt=8 taken=2
  R7[Crusher: Atk(6)+Rocket: Atk(30)]: Predator+(44dmg,power:+Draw Cards Next Turn(2))->Dagger Spray(24dmg)->Leading Strike(5dmg)->Neutralize+(6dmg,1+Weak(2))->Shiv(6dmg)->Shiv(6dmg) | dealt=91 taken=24
  R8[Crusher: Atk(12x2=24), Debuff+Rocket: Buff]: Leg Sweep(+13blk,1+Weak(2))->Dodge and Roll(+6blk,power:+Block Next Turn(6))->Strike(8dmg) | dealt=8 taken=0
  R9[Crusher: Buff+Rocket: Atk(52)]: Piercing Wail(2Strength(2→-4),+Piercing Wail(6),2Strength(4→-2),+Piercing Wail(6),exhaust:1)->Finesse(+4blk)->Cloak and Dagger+(+6blk)->Survivor(+7blk) | dealt=0 taken=0
  R10[Crusher: Atk(16), Defend+Rocket: Sleep]: Defend(+5blk)->Expertise+->Neutralize+(4dmg,1+Weak(2))->Poisoned Stab(6dmg,1Poison(7→10))->Survivor(+7blk) | dealt=10 taken=4
  R11[Crusher: Atk(16)]: Finesse(+6blk)->Cloak and Dagger+(+8blk) | dealt=0 taken=0
  R12[Crusher: Atk(14)]: Dodge and Roll(+6blk,power:+Block Next Turn(6))->Defend(+7blk) | dealt=0 taken=0
  R13[Crusher: Atk(16x2=32), Debuff]: Leg Sweep(+13blk,1+Weak(2))->Shiv(6dmg)->Strike(16dmg)->Dagger Throw(11dmg)->Cloak and Dagger+(+8blk)->Shiv(6dmg,+1energy)->Shiv(6dmg) | dealt=34 taken=0
  R14[Crusher: Buff]: Predator+(power:-Surrounded,power:-Noxious Fumes,power:-Strength,power:-Dexterity,power:-Weak,power:-Frail) | dealt=0 taken=0

F35 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (2R, HP 60->61, loss=0, WIN)
  R1[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff+Scroll of Biting: Atk(14)]: Backstab(11dmg,exhaust:1)->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Noxious Fumes(power:+Noxious Fumes(2))->Expertise+->Dagger Spray->Leg Sweep(+11blk)->Cloak and Dagger+(+6blk)->Shiv(exhaust:1)->Shiv->Survivor(+8blk) | dealt=31 taken=0
  R2[Scroll of Biting: Atk(3x2=6)+Scroll of Biting: Atk(7x2=14)]: Accuracy(power:+Accuracy(4))->Piercing Wail(2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Dagger Throw(18dmg)->Neutralize+->Strike->Dagger Throw(2+Weak(3),Strength(-4→-6))->Blade Dance(exhaust:1)->Shiv(8dmg)->Shiv(power:-Noxious Fumes,power:-Accuracy) | dealt=8 taken=0

F39 [monster] Devoted Sculptor (4R, HP 61->48, loss=13, WIN)
  R1[Devoted Sculptor: Buff]: Backstab(11dmg,exhaust:1)->Adrenaline(+1energy,exhaust:1)->Noxious Fumes(power:+Noxious Fumes(2))->Finesse(+4blk)->Neutralize+(4dmg,1+Weak(2))->Strike(9dmg)->Leading Strike(6dmg)->Shiv(8dmg,exhaust:1)->Shiv(4dmg)->Blade Dance(exhaust:1)->Shiv(4dmg,+1energy)->Shiv(4dmg)->Shiv(4dmg)->Cloak and Dagger+(+6blk)->Shiv(4dmg)->Shiv(4dmg)->Dagger Throw(9dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=62 taken=0
  R2[Devoted Sculptor: Atk(9)]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Dagger Throw(11dmg)->Defend(+7blk)->Poisoned Stab(8dmg,1Poison(2→5))->Dagger Spray(24dmg) | dealt=32 taken=0
  R3[Devoted Sculptor: Atk(21)]: Defend(+7blk)->Strike(11dmg)->Strike(11dmg)->Strike(11dmg) | dealt=33 taken=14
  R4[Devoted Sculptor: Atk(30)]: Predator+(power:-Noxious Fumes,power:-Strength,power:-Dexterity) | dealt=0 taken=0

F42 [monster] multi:The Forgotten+The Lost (3R, HP 48->39, loss=9, WIN)
  R1[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Accuracy(power:+Accuracy(4))->Leading Strike(6dmg)->Shiv(8dmg,exhaust:1)->Shiv(8dmg)->Cloak and Dagger+(+6blk)->Shiv(8dmg)->Shiv(8dmg)->Backstab(22dmg,exhaust:1)->Dagger Throw(9dmg) | dealt=60 taken=0
  R2[The Lost: Atk(6x2=12)+The Forgotten: Atk(15)]: Cloak and Dagger+(+4blk)->Neutralize+(2dmg,+1energy,1+Weak(2))->Shiv(6dmg)->Shiv(6dmg)->Strike(7dmg)->Defend(+3blk)->Survivor(+6blk) | dealt=21 taken=10
  R3[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Strike(power:-Strength)->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike(9dmg)->Dagger Throw(9dmg)->Adrenaline(+1energy,exhaust:1)->Expertise+->Finesse(+2blk)->Prowess+(power:+Strength(2),power:-Dexterity)->Strike(22dmg)->Dagger Spray(12dmg)->Blade Dance(exhaust:1)->Shiv(10dmg,+1energy)->Shiv(10dmg)->Shiv(10dmg)->Storm of Steel(+6blk)->Shiv(power:-Accuracy,power:-Draw Cards Next Turn,power:-Strength) | dealt=96 taken=0

F43 [elite] Soul Nexus (7R, HP 39->40, loss=0, WIN)
  R1[Soul Nexus: Atk(29)]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Accuracy(power:+Accuracy(4))->Backstab(13dmg,exhaust:1)->Adrenaline(+1energy,exhaust:1)->Finesse(+6blk)->Dagger Throw(11dmg)->Survivor(+10blk)->Defend(+7blk)->Defend(+7blk) | dealt=13 taken=0
  R2[Soul Nexus: Atk(18), DebuffStrong]: Noxious Fumes(power:+Noxious Fumes(2))->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=0
  R3[Soul Nexus: Atk(9x4=36)]: Leg Sweep(+13blk,1+Weak(2))->Leg Sweep(+13blk,1Weak(2→4))->Cloak and Dagger+(+8blk)->Shiv(7dmg,exhaust:1)->Shiv(7dmg)->Predator+(33dmg,power:+Draw Cards Next Turn(2)) | dealt=47 taken=0
  R4[Soul Nexus: Atk(20), DebuffStrong]: Defend(+7blk)->Dodge and Roll(+6blk,power:+Block Next Turn(6))->Cloak and Dagger+(+8blk)->Neutralize+(4dmg,1Weak(3→5))->Leading Strike(6dmg)->Blade Dance(exhaust:1)->Shiv(7dmg)->Shiv(7dmg)->Shiv(7dmg)->Shiv(7dmg)->Shiv(7dmg)->Shiv(7dmg)->Shiv(7dmg)->Strike(16dmg) | dealt=75 taken=0
  R5[Soul Nexus: Atk(6x4=24)]: Cloak and Dagger+(+8blk)->Shiv(7dmg)->Shiv(7dmg,+1energy)->Leg Sweep(+13blk,1Weak(4→6))->Poisoned Stab(6dmg,1Poison(4→7))->Dagger Throw(8dmg)->Dagger Spray(8dmg) | dealt=28 taken=0
  R6[Soul Nexus: Atk(20), DebuffStrong]: Leg Sweep(+13blk,1Weak(5→7))->Defend(+7blk)->Dodge and Roll(+6blk,power:+Block Next Turn(6))->Strike(8dmg) | dealt=8 taken=0
  R7[Soul Nexus: Atk(6x4=24)]: Murder(power:-Strength,power:-Dexterity,power:-Accuracy,power:-Noxious Fumes,power:-Vulnerable,power:-Weak) | dealt=0 taken=0

F45 [monster] multi:Axebot+Axebot (5R, HP 58->59, loss=0, WIN)
  R1[Axebot: Atk(8), Debuff+Axebot: Atk(8), Debuff]: Prowess+(power:+Strength(2),power:+Dexterity(2))->Accuracy+(power:+Accuracy(6))->Backstab(13dmg,exhaust:1)->Dagger Spray(12dmg)->Dagger Throw(1Stock(2→1))->Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv(+1energy)->Shiv->Dodge and Roll(+6blk,power:+Block Next Turn(6))->Leg Sweep(+13blk,1+Weak(2)) | dealt=25 taken=0
  R2[Axebot: Buff+Axebot: Atk(4x2=8)]: Expertise+->Noxious Fumes(power:+Noxious Fumes(2))->Cloak and Dagger+(+8blk)->Shiv*2->Poisoned Stab->Strike | dealt=0 taken=0
  R3[Axebot: Atk(10x2=20)+Axebot: Atk(6x2=12)]: Finesse(+6blk)->Strike->Defend(+7blk)->Dagger Throw(11dmg)->Neutralize+(12dmg,1+Weak(2))->Piercing Wail(2Strength(1→-5),+Piercing Wail(6),exhaust:1) | dealt=12 taken=0
  R4[Axebot: Atk(6x2=12)+Axebot: Buff]: Cloak and Dagger+(+8blk)->Shiv(12dmg)->Shiv(+1energy,4-Stock,-Strength,-Poison,-Weak)->Predator+(power:+Draw Cards Next Turn(2))->Leading Strike->Shiv*2->Strike(11dmg)->Defend(+7blk) | dealt=23 taken=0
  R5[Axebot: Buff]: Adrenaline(+1energy,exhaust:1)->Finesse(+6blk)->Murder(power:-Strength,power:-Dexterity,power:-Accuracy,power:-Noxious Fumes) | dealt=0 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (8R, HP 77->31, loss=46, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Backstab(13dmg,exhaust:1)->Predator+(44dmg,power:+Draw Cards Next Turn(2))->Poisoned Stab(8dmg,1+Poison(3))->Leg Sweep(+11blk,1+Weak(2))->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Dagger Throw(11dmg)->Dagger Spray(24dmg)->Strike(11dmg)->Murder(13dmg) | dealt=113 taken=0
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Neutralize+(6dmg,1+Weak(2))->Leading Strike(8dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Cloak and Dagger+(+6blk)->Shiv(12dmg)->Shiv(6dmg)->Leg Sweep(+11blk,1Weak(1→3))->Finesse(+4blk)->Adrenaline+(+2energy,exhaust:1)->Expertise+->Finesse(+4blk)->Prowess+(power:Strength(2→4),power:+Dexterity(2))->Blade Dance(exhaust:1)->Shiv(8dmg,+1energy)->Shiv(8dmg)->Shiv(8dmg)->Dagger Throw(13dmg)->Adrenaline(+1energy,exhaust:1) | dealt=68 taken=0
  R3[Torch Head Amalgam: Atk(9x3=27)+Queen: Buff, Defend]: Accuracy+(power:+Accuracy(6))->Defend(+5blk)->Strike(9dmg) | dealt=9 taken=22
  R4[Torch Head Amalgam: Atk(16)+Queen: Buff, Defend]: Cloak and Dagger+(+6blk)->Leg Sweep(+9blk,1Weak(1→3))->Shiv*2 | dealt=0 taken=1
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Dagger Throw->Murder(62dmg)->Defend(+5blk)->Survivor(+10blk) | dealt=62 taken=0
  R6[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Predator+(power:+Draw Cards Next Turn(2))->Dagger Throw(7dmg)->Dodge and Roll(+4blk,power:+Block Next Turn(4))->Defend(+5blk) | dealt=0 taken=24
  R7[Torch Head Amalgam: Atk(27)+Queen: Buff, Defend]: Dagger Spray(12dmg)->Leading Strike->Cloak and Dagger+(+6blk)->Shiv(9dmg)->Shiv(10dmg)->Shiv(10dmg)->Shiv(10dmg)->Poisoned Stab(7dmg,1+Poison(3))->Expertise+->Dagger Throw(19dmg)->Finesse(+4blk)->Storm of Steel(+15blk)->Shiv(10dmg)->Shiv(10dmg,+1energy)->Shiv(10dmg)->Shiv(10dmg)->Shiv(10dmg) | dealt=108 taken=0
  R8[Torch Head Amalgam: Atk(28)+Queen: Buff, Defend]: Cloak and Dagger+(+6blk)->Shiv*2->Strike(power:-Strength,power:-Chains of Binding,power:-Dexterity,power:-Frail,power:-Weak,power:-Vulnerable,power:-Accuracy) | dealt=0 taken=0

### Non-combat Decisions (208 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=combat,deck_building) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Lead Paperweight gives a choice of Colorless cards which can provide excellent early utility and flexibility, while Arcane Scroll is too high variance and Scroll Boxes costs all our starting gold.
  strategic_note: Foundation deck: rely on strikes/defends while finding early damage to survive Act 1 elites. Focus on drafting high-damage attacks.

F1 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->13
  deck_change: added Prowess
  reasoning: Prowess provides highly efficient, generic scaling (Strength and Dexterity) that synergizes perfectly with Silent's basic defensive kit and any future multi-hit attacks. Finesse is a low-impact cycle card that doesn't solve any immediate or long-term problems this early in the run.
  strategic_note: Foundation plan: rely on basic strikes and defends while aggressively drafting high-damage frontload attacks to survive Act 1 elites. With Prowess secured, multi-hit attacks and cheap block become more valuable.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Starting the Act 1 standard monster chain to draft foundational damage and block cards. This route provides the most flexibility for hitting future nodes and aligns with the expert recommendation of 4-5 early combats.
  strategic_note: Foundation phase: drafting frontloaded damage and consistent block to survive early hallways while building a gold base for a mid-act shop.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->106 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 106->106 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 56->56 | Gold 106->106 | Deck 13->14
  deck_change: picked Dagger Spray
  reasoning: Dagger Spray provides much-needed AoE damage for early Act 1 hallway fights and scales excellently with the Strength from Prowess.
  strategic_note: Foundation plan: rely on basic strikes and defends while aggressively drafting high-damage frontload attacks to survive Act 1 elites. With Prowess secured, multi-hit attacks and cheap block become more valuable.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 106->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 106->121 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 121->121 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Gambler's Brew

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 121->121 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 54->54 | Gold 121->121 | Deck 14->15
  deck_change: picked Predator
  reasoning: Predator provides excellent upfront damage to handle early Elites like Gremlin Nob, while the +2 draw next turn helps smooth out energy usage and finds defensive options.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; prioritize high-impact attacks for early Elites.

F3 [map] choose_map_node (option_index=0) | source=llm
  HP 54->54 | Gold 121->121 | Deck 15->15
  deck_change: no deck change
  reasoning: Continuing the recommended route toward early monster fights and rest sites. While a shop is available, 121 gold is slightly low for a high-impact shop visit this early. The Unknown node offers the chance for a favorable event or a combat that provides card rewards and gold to further build the foundation.
  strategic_note: Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. I am aiming for 4-5 early combats before a major shop or elite to ensure the deck has enough impact cards to survive Act 1's scaling threats.

F4 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 54->54 | Gold 121->121 | Deck 15->16
  deck_change: added Clumsy
  reasoning: With no shop currently planned on the route, 66 Gold provides no immediate benefit for surviving Act 1. A random Relic provides immediate power. Clumsy is Ethereal, meaning it only penalizes draw once per combat, which is manageable given our Turn 1 extra draw from Ring of the Snake.
  strategic_note: Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. Clumsy curse means we need to be slightly more careful about draw. We still need impactful damage cards to handle upcoming Elites.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 54->54 | Gold 121->121 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 121->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Unknown

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 121->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 129->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Cunning Potion

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 129->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 54->54 | Gold 129->129 | Deck 16->17
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides solid upfront damage for Act 1 elites, replaces itself in hand, and offers a discard outlet for future synergies or getting rid of basic strikes.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 129->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 129->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 54->54 | Gold 143->143 | Deck 17->18
  deck_change: picked Poisoned Stab
  reasoning: Poisoned Stab provides decent upfront damage and scales well with its poison effect, helping us push through Act 1 elites while we look for a cohesive engine.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F6 [map] choose_map_node (option_index=0) | source=llm
  HP 54->54 | Gold 143->143 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the recommended route to reach a Rest Site. With 54/70 HP and a deck that needs refinement, this is a safe point to either upgrade a key card or heal if the upcoming hallway fight seems risky. Consistent with the goal of reaching the Act 1 boss with high stability.
  strategic_note: Foundation phase: prioritizing standard monster encounters to draft essential frontloaded damage and block cards while maintaining a healthy HP buffer for Act 1 elites.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 54->54 | Gold 143->143 | Deck 18->18
  deck_change: upgraded Prowess->Prowess+
  reasoning: With 54/70 HP and another rest site before the Elite, smithing is safe and optimal. Upgrading Prowess to provide 2 Strength and 2 Dexterity is a massive scaling boost for both damage (especially multi-hit like Dagger Spray) and block, making it the most impactful upgrade for upcoming Elite and Boss fights.
  strategic_note: Foundation phase: prioritize frontloaded damage and block. Play Prowess early to scale attacks and defenses, relying on Predator and Dagger Spray for burst damage. Need one more solid damage or block card; avoid overly situational cards.

F7 [rest_site] proceed | source=auto
  HP 54->54 | Gold 143->143 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 143->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 143->156 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 156->156 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 40->40 | Gold 156->156 | Deck 18->19
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides cycling to help us find our key cards like Prowess+ and Predator faster, while upgrading our strike damage. Follow Through is too clunky to trigger reliably since it requires 5 other cards in hand, conflicting with playing Prowess first.
  strategic_note: Foundation plan: scale with Prowess+ and use cheap/multi-hit attacks and efficient block to survive. Need card removals and cheap block/draw to support the core scaling.

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 156->156 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: RestSite

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=10) | source=llm
  HP 40->40 | Gold 156->156 | Deck 19->19
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With 40 HP and a treasure room next, we are healthy enough to smith before the F13 Elite. Upgrading Neutralize to apply 2 turns of Weak is arguably the best early defensive upgrade for Silent, massively improving survivability against Elites like Gremlin Nob and Lagavulin.
  strategic_note: Foundation phase: prioritizing frontloaded damage and block cards while looking for a coherent damage engine. Play priority: maintain Weak on dangerous enemies and use discard (Survivor, Dagger Throw) to filter past the Clumsy curse. Avoid adding too many expensive cards without an energy relic.

F9 [rest_site] proceed | source=auto
  HP 40->40 | Gold 156->156 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=1) | source=llm
  HP 40->40 | Gold 156->156 | Deck 19->19
  deck_change: no deck change
  reasoning: Moving to the recommended Treasure node at c4,r9. This is a mandatory progression step towards the next Rest Site and Elite. I have 40 HP, which is acceptable for this stage of Act 1, but I need to find scaling or strong frontloaded damage soon.
  strategic_note: Foundation phase: focusing on standard monster encounters to draft frontloaded damage and block. Clumsy curse necessitates careful draw management; looking for high-impact damage and scaling to handle the upcoming Act 1 elites.

F10 [treasure] open_chest | source=random
  HP 40->40 | Gold 156->194 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 40->40 | Gold 194->194 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim: Ice Cream

F10 [treasure] proceed | source=random
  HP 40->40 | Gold 194->194 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=llm
  HP 40->40 | Gold 194->194 | Deck 19->19
  deck_change: no deck change
  reasoning: My current HP is 40/70 (57%). While this is not critically low, the route guide emphasizes taking a Rest Site here to buffer for the upcoming mandatory Elite on Floor 12. Using this node to Smith will improve my deck's efficiency, and I have another Rest Site immediately after the Elite to recover if needed. Following the route's advice for safety.
  strategic_note: Foundation phase: prioritizing hallway fights and card rewards for frontloaded damage and block. Clumsy curse means we need to be careful about draw. Currently hunting for impactful damage cards to handle Elites while using Rest Sites to Smith key upgrades.

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 40->40 | Gold 194->194 | Deck 19->19
  deck_change: upgraded Predator->Predator+
  reasoning: With 40 HP, we have a reasonable buffer for the upcoming Floor 12 Elite, especially since we have another Rest Site immediately after at Floor 13. Upgrading Predator to 20 damage significantly improves our burst damage against Gremlin Nob and Lagavulin, likely saving us more HP than a heal would provide.
  strategic_note: Foundation phase: relying on frontloaded damage and Prowess+ for stats while using discard to filter past Clumsy. Needs a cohesive scaling engine and energy generation to support expensive cards like Predator.

F11 [rest_site] proceed | source=auto
  HP 40->40 | Gold 194->194 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 194->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Elite

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 194->224 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 224->224 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 224->224 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim relic: Lantern

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 224->224 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 28->28 | Gold 224->224 | Deck 19->20
  deck_change: picked Backstab
  reasoning: Backstab provides excellent Turn 1 frontload damage for zero energy, which helps eliminate dangerous enemies early without slowing down our deck cycle in longer fights since it exhausts. It works well with Ring of the Snake's extra draw.
  strategic_note: Foundation plan: survive with frontload and Prowess while looking for multi-attacks and efficient scaling; take cheap draw or high-impact damage, skip narrow synergy pieces.

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 28->28 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F13 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 28->49 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: HP is at 28/70, which is dangerously low going into an unknown node and an Act 1 Elite. Healing now ensures we survive these fights, and we have another rest site right after the Elite to smith if we take minimal damage.
  strategic_note: Foundation phase: relying on frontloaded physical damage and weak application to clear Act 1 fights. Need scaling damage or strong block solutions for the boss, and card draw to mitigate the Clumsy curse.

F13 [rest_site] proceed | source=auto
  HP 49->49 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=llm
  HP 49->49 | Gold 224->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the established route to fight a Monster. This is the 6th hallway fight, allowing us to further refine the deck before the upcoming Elite at Floor 14. With 224 gold, we are well-positioned for a late Act 1 or early Act 2 shop, and 49 HP is sufficient for one more hallway fight and the Elite, especially with a campfire guaranteed after.
  strategic_note: Foundation phase: prioritizing frontloaded damage and block cards in hallway fights to prepare for Act 1 Elite and Boss. The deck is currently seeking consistent damage to minimize chip damage while navigating around the Clumsy curse.

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 224->233 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 233->233 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 49->49 | Gold 233->233 | Deck 20->21
  deck_change: picked Leg Sweep
  reasoning: Leg Sweep is premium mitigation that provides Weak and high Block, which is crucial for surviving multi-attacks from the Act 1 Boss and beyond. With Ice Cream and Lantern, its 2E cost is very manageable.
  strategic_note: Foundation plan: survive with frontload, block efficiently, and use Prowess+ for both offense and defense scaling. Leverage Ice Cream for big energy turns. Needs a cohesive scaling engine; avoid generic attacks.

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 233->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Elite

F15 [card_select] select_deck_card (option_index=2) | source=llm
  HP 49->49 | Gold 233->0 | Deck 21->21
  deck_change: no deck change
  reasoning: We failed to find damage or card draw from the Skill Potion, but Shadow Step allows us to discard our entire hand, which includes the Infections, saving us from taking 6 damage at the end of the turn. It also sets up double attack damage for next turn to guarantee the kill.
  strategic_note: Foundation phase: prioritizing hallway fights and card rewards to build frontloaded damage and block. Clumsy curse means we need to be slightly more careful about draw. We still need impactful damage cards to handle upcoming Elites.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 233->259 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim relic: Nunchaku

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 49->49 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: None of these cards significantly improve our boss fight or long-term scaling. Sucker Punch is redundant with Neutralize+ and Leg Sweep. Anticipate is weak block scaling compared to Prowess+. Hand Trick requires a combo of discard outlet + expensive skill in hand, which is too situational. Skipping keeps the deck lean to draw Prowess+ and Predator+ faster.
  strategic_note: Foundation phase: relying on frontloaded physical damage, weak application, and Prowess+ scaling. Keep the deck lean to cycle into key cards; skip low-impact additions.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 49->70 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: We are facing the Act 1 Boss next and are missing exactly the 21 HP a rest restores. Our deck lacks fast scaling damage, meaning the boss fight will likely take several turns. Having full HP gives us the necessary buffer to survive the boss's major attacks while our physical damage and weak application do their work.
  strategic_note: Foundation phase: relying on frontloaded physical damage and weak application. Need scaling damage or strong block solutions for upcoming Acts, and card draw to mitigate the Clumsy curse.

F16 [rest_site] proceed | source=auto
  HP 70->70 | Gold 259->259 | Deck 21->21
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 259->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 259->334 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 334->334 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Poison Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 334->334 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 43->43 | Gold 334->334 | Deck 21->22
  deck_change: picked Storm of Steel
  reasoning: Storm of Steel has massive synergy with Prowess+ (Strength scales multi-hits) and Nunchaku (Shivs trigger the energy gain quickly). It allows us to convert weak hands of Strikes and Defends into burst damage, which scales incredibly well with our established Strength from Prowess+.
  strategic_note: Transitioning to a committed Shiv/Attack plan with Prowess+ and Nunchaku; prioritize multi-hit cards, draw, and discard synergies to leverage Strength, while actively removing basic attacks.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 43->64 | Gold 334->334 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 64->64 | Gold 334->334 | Deck 22->22
  deck_change: no deck change
  reasoning: Very Hot Cocoa gives 4 energy on turn 1. Paired with Ice Cream, any unused energy will carry over to future turns, providing a massive, flexible energy pool for every combat without any downsides like draining gold or expiring after Act 2.
  strategic_note: Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 64->64 | Gold 334->334 | Deck 22->22
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 64->64 | Gold 334->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended route to reach the shop at floor 22 with 334 gold. Act 2 hallways are dangerous, but the initial fight is necessary to access the events and shop nodes that define a winning Act 2 path.
  strategic_note: Foundation phase: leveraging high gold reserves to find key scaling pieces at the upcoming shop while prioritizing block and frontloaded damage to survive the initial Act 2 hallway spike.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 334->349 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 349->349 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Heart of Iron

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 349->349 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 64->64 | Gold 349->349 | Deck 22->23
  deck_change: picked Cloak and Dagger+
  reasoning: Cloak and Dagger+ synergizes perfectly with Prowess+, providing scaled block from Dexterity and multiple scaled attacks from Strength. It also accelerates Nunchaku triggers.
  strategic_note: Foundation plan: transition into a Shiv/Strength scaling engine using Prowess+. Prioritize card draw, Shiv generators, and multi-hits to maximize Strength benefits, while avoiding slow poison or heavy single-hit cards.

F19 [map] choose_map_node (option_index=1) | source=llm
  HP 64->64 | Gold 349->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to minimize combat encounters in Act 2. My health is high (64/70) and I have significant gold (349), so I want to reach the upcoming shop safely to buy scaling solutions. Act 2 hallway fights are notoriously dangerous for decks still in the foundation phase.
  strategic_note: Foundation phase: relying on frontloaded physical damage and weak application; need scaling damage and card draw to mitigate Clumsy while prioritizing HP preservation through non-combat nodes.

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 349->361 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 361->361 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 64->64 | Gold 361->361 | Deck 23->24
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a premium defensive card that completely neutralizes deadly multi-attacks in Act 2 and 3 (Book of Stabbing, Act Boss). Our current deck has Prowess+ for scaling, so having an exhaustible stall tool helps us survive long enough to play it.
  strategic_note: Committed to scaling with Prowess+ (Strength/Dexterity) and utilizing Ice Cream/Energy relics. Prioritize multi-hit attacks to leverage Strength and strong mitigation to stall for Prowess. Focus on removing Strikes/Defends to draw Prowess faster.

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 64->64 | Gold 361->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Unknown

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 361->369 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 369->369 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 369->369 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 64->64 | Gold 369->369 | Deck 24->24
  deck_change: no deck change
  reasoning: With 24 cards and our only scaling being Prowess+, we need to keep the deck lean to ensure we draw our key pieces (Prowess+, Predator+, Leg Sweep) consistently. Blur offers decent utility with Dexterity, but doesn't solve our draw bottleneck or improve our engine enough to justify diluting the deck.
  strategic_note: Foundation phase: relying on Prowess+ for str/dex scaling and Ice Cream for energy hoarding. Focus on acquiring card draw (Acrobatics, Backflip) and removing basic cards to cycle faster into our scaling.

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 64->64 | Gold 369->369 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Shop

F22 [shop] buy_card (option_index=4) | source=plan
  HP 64->64 | Gold 369->296 | Deck 24->25
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/5]: Crucial passive AoE scaling that damages both enemies evenly, essential for managing the Crab Rage threshold triggers in the upcoming multi-enemy boss.

F22 [shop] buy_card (option_index=2) | source=plan
  HP 64->64 | Gold 296->247 | Deck 25->26
  deck_change: bought Blade Dance
  reasoning: Shop plan [2/5]: Cheap way to deliver multiple hits that scale perfectly with the Strength from our Prowess+ and charge our Nunchaku.

F22 [shop] buy_card (option_index=5) | source=plan
  HP 64->64 | Gold 247->164 | Deck 26->27
  deck_change: bought Finesse
  reasoning: Shop plan [3/5]: Free draw and block that benefits from our Dexterity (via Prowess+). Doesn't cost energy, which synergizes with our Ice Cream hoarding strategy.

F22 [shop] buy_card (option_index=3) | source=plan
  HP 64->64 | Gold 164->116 | Deck 27->28
  deck_change: bought Dodge and Roll
  reasoning: Shop plan [4/5]: Double-dips on Dexterity and carries block over to future turns, helping us mitigate the massive predetermined hits on Boss turns 2 and 4.

F22 [shop] remove_card_at_shop | source=plan
  HP 64->64 | Gold 116->116 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan [5/5]: Removing a Strike increases the density of our defensive and scaling tools so we can find Prowess+ and Noxious Fumes faster.

F22 [card_select] select_deck_card (option_index=0) | source=llm
  HP 64->64 | Gold 116->41 | Deck 28->27
  deck_change: lost Clumsy
  reasoning: Clumsy is a Curse that costs a draw. Even though it is Ethereal, drawing it on turn 1 or 2 can be lethal in Act 2. Following the general rule to remove Curses first.
  strategic_note: Poison scaling (Noxious Fumes) is established. Focus on survival, block, and deck thinning. Avoid generic attacks and prioritize card draw/discard synergies.

F22 [shop] close_shop_inventory | source=llm
  HP 64->64 | Gold 41->41 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F22 [shop] proceed | source=auto
  HP 64->64 | Gold 41->41 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 64->64 | Gold 41->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Unknown

F23 [card_select] select_deck_card (option_index=2) | source=llm
  HP 63->63 | Gold 41->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Burst is an exceptionally powerful skill. Since it comes from a Skill Potion, it costs 0 this turn. We can use it to double Cloak and Dagger+ to generate an additional 6 Block and 2 Shivs, covering our defensive needs while giving us more damage to finish off Chomper 0.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 41->55 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 55->55 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Heart of Iron

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 55->55 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 59->59 | Gold 55->55 | Deck 27->28
  deck_change: picked Expertise+
  reasoning: With Ice Cream, Lantern, and Very Hot Cocoa, we have an enormous amount of energy but lack the card draw to spend it effectively. Expertise+ is the perfect solution, allowing us to dump our cheap cards and refill our hand to keep the turn going.
  strategic_note: Foundation plan: Use massive starting energy and Ice Cream to play many cards per turn. Prioritize card draw and removals to continuously cycle our deck. Look for a core scaling engine like multi-hit/shivs for Prowess+ or heavy poison.

F23 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 55->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Elite

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 55->87 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 32 Gold

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 87->87 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim relic: Pen Nib

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 87->87 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F24 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 45->45 | Gold 87->87 | Deck 28->29
  deck_change: picked Leading Strike
  reasoning: Leading Strike provides 3 attacks in one card, rapidly stacking our Nunchaku and Pen Nib relics. It also scales incredibly well with the Strength provided by Prowess+.
  strategic_note: Committed shiv/strength engine with Prowess+ and Nunchaku/Pen Nib: play Prowess early, then use Shiv generators to output massive scaling damage and block with Dexterity.

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 45->45 | Gold 87->87 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Unknown

F25 [event] choose_event_option (option_index=1) | source=llm
  HP 45->45 | Gold 87->87 | Deck 29->29
  deck_change: no deck change
  reasoning: Our Turn 1 is exceptionally strong with 8 starting Energy (Lantern + Very Hot Cocoa) and Ice Cream, making us heavily favored in sudden fights. We have no shops on our planned route in Act 2, so the 100 Gold is less valuable than obtaining the unique Key reward.
  strategic_note: Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.

F25 [event] choose_event_option (option_index=0) | source=auto
  HP 45->45 | Gold 87->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Fight

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 87->101 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 101->101 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim potion: Heart of Iron

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 101->101 | Deck 29->30
  deck_change: picked Lantern Key
  reasoning: Claim specialcard: Add Lantern Key to your deck.

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 101->101 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F25 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 41->41 | Gold 101->101 | Deck 30->31
  deck_change: picked Leg Sweep
  reasoning: A second Leg Sweep provides crucial, consistent Weak application and heavy block, which is perfectly suited for surviving the massive alternating attacks from Crusher+Rocket.
  strategic_note: Foundation plan: surviving with robust mitigation (Leg Sweep, Piercing Wail) and scaling with Noxious Fumes/Shivs. Focus on removing Strikes to draw defensive and scaling pieces faster. Needs consistent draw.

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 101->101 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 41->41 | Gold 101->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 41->41 | Gold 132->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim: Candelabra

F26 [treasure] proceed | source=random
  HP 41->41 | Gold 132->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 132->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Unknown

F27 [event] choose_event_option (option_index=1) | source=llm
  HP 41->27 | Gold 132->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Taking 14 damage drops us to 27 HP, which is risky, but we have a Rest Site coming up at Floor 29 if we need to heal. We have immense Turn 1 energy and defensive tools like Leg Sweep, Piercing Wail, and Finesse to survive Floor 28 safely. Chosen Cheese provides scaling Max HP for the entirety of Act 3.
  strategic_note: Committed to an Ice Cream energy-banking strategy: use immense Turn 1 energy to play out our hand, while saving any excess for high-cost turns (like Predator+ and Leg Sweep). Prioritize card draw to fully utilize the massive energy reserves.

F27 [event] choose_event_option (option_index=0) | source=auto
  HP 27->27 | Gold 132->132 | Deck 31->31
  deck_change: no deck change
  reasoning: Only option: Proceed

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 132->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Monster

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 132->147 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 147->147 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 28->28 | Gold 147->147 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 28->28 | Gold 147->147 | Deck 31->32
  deck_change: picked Accuracy
  reasoning: With Blade Dance, Cloak and Dagger+, Leading Strike, and Storm of Steel in the deck, Accuracy provides a huge scaling boost to our damage output, complementing our Ice Cream energy banking and Nunchaku/Pen Nib relics.
  strategic_note: Committed to Shivs and energy banking with Ice Cream. Use extra energy to cycle with Expertise+ and Finesse. Stack Accuracy/Prowess+ and unleash high-damage Shivs. Need more card draw and card removals.

F28 [map] choose_map_node (option_index=0) | source=llm
  HP 28->28 | Gold 147->147 | Deck 32->32
  deck_change: no deck change
  reasoning: With 28/71 HP and a Clumsy curse in the deck, I am not in a position to take a standard monster fight when a Rest Site is available. The Route Intelligence for Act 2 emphasizes HP preservation and avoiding lethal regular monsters. Resting here is mandatory to prepare for the forced Elite and Boss later in the act.
  strategic_note: Foundation phase: relying on frontloaded physical damage and weak application. Need scaling damage or strong block solutions for upcoming Acts, and card draw to mitigate the Clumsy curse.

F29 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 28->49 | Gold 147->147 | Deck 32->32
  deck_change: no deck change
  reasoning: HP is critically low at 28/71, and the next node is an Act 2 Elite. Resting restores 21 HP to ensure survival, while we still have another rest site at F32 to smith or heal again before the Boss.
  strategic_note: Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy to play out our hand, while saving excess for high-cost defense (Leg Sweep). Needs more card draw to fully utilize the massive energy reserves.

F29 [rest_site] proceed | source=auto
  HP 49->49 | Gold 147->147 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=llm
  HP 49->49 | Gold 147->0 | Deck 32->32
  deck_change: no deck change
  reasoning: The route intelligence for Act 2 strongly advises avoiding elites, but the current situation contradicts this for several reasons. 1) I have Ice Cream, which makes my energy pool much more flexible and allows for explosive starts or heavy blocking turns. 2) I have Leg Sweep and Predator+, providing both high-value defense and draw. 3) My current HP (49/71) is healthy enough to handle a challenge. 4) The 'Route Intelligence' provided seems overly cautious (advocating 0 elites) which often stunts a deck's scaling for Act 3. Taking this Elite provides a chance for a high-impact relic and rare cards to further leverage the Ice Cream engine.
  strategic_note: Committed Ice Cream energy-banking strategy: accumulate energy on quiet turns to fuel high-impact cycles of Predator+ and Leg Sweep, prioritizing card draw to ensure banked energy is never wasted.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 147->175 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 28 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 175->175 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim potion: Fortifier

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 175->175 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim relic: Happy Flower

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 175->175 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 48->48 | Gold 175->175 | Deck 32->33
  deck_change: picked Cloak and Dagger+
  reasoning: Cloak and Dagger+ is highly efficient in our deck, providing 6 Block and 2 Shivs for 1 Energy. With Accuracy and Prowess+, it scales extremely well into both damage and defense, fueling our Shiv synergy and helping trigger Nunchaku.
  strategic_note: Committed Shiv/Energy plan: play defensively while setting up Accuracy/Prowess+ scaling, then use massive Shiv generation and energy banking (Ice Cream) to overwhelm enemies. Avoid bloated basic attacks and focus on card draw to find the engine quickly.

F30 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Unknown

F31 [event] choose_event_option (option_index=1) | source=llm
  HP 48->48 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Normality is a run-ending curse for a Shiv deck since it limits card plays to 3 per turn. Enter Your Hole offers a strictly beneficial enchant with no downside.
  strategic_note: Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy to play out our hand, while saving excess for high-cost defense (Leg Sweep). Needs more card draw to fully utilize the massive energy reserves.

F31 [card_select] select_deck_card (option_index=12) | source=llm
  HP 48->48 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Prowess+ provides both Strength for our Shivs and Dexterity for our Block cards, making it the highest impact scaling card in our deck and the best target for a permanent enhancement.
  strategic_note: Committed to a Shiv engine backed by Prowess and Accuracy. Prioritize Shiv generation, efficient Block with Dexterity, and let Fumes scale in longer fights.

F31 [event] choose_event_option (option_index=0) | source=auto
  HP 48->48 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 48->69 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: We are facing the Act 2 Boss next with 48/72 HP. While we have excellent block scaling and weaken, a 21 HP buffer provides critical safety against a bad draw during the boss's setup phase or big attacks like Hyperbeam/Execute. Healing is the conservative and correct play.
  strategic_note: Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.

F32 [rest_site] proceed | source=auto
  HP 69->69 | Gold 175->175 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 69->69 | Gold 175->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 69->69 | Gold 175->0 | Deck 33->33
  deck_change: no deck change
  reasoning: With 10 banked energy and 24 incoming damage, we desperately need card draw right now to find defensive options. Thinking Ahead provides immediate, free card draw to help us access our block cards.
  strategic_note: Committed to Ice Cream energy-banking: rely on massive starting energy and banking to play huge hands. Prioritize abundant card draw (Acrobatics, Backflip) and X-cost or high-impact cards to turn excess energy into damage and defense. Need consistent scaling damage to complement Prowess+.

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 8->8 | Gold 175->250 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 8->8 | Gold 250->250 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 8->8 | Gold 250->250 | Deck 33->34
  deck_change: picked Adrenaline
  reasoning: Adrenaline is a strictly positive card, giving us free energy to bank with Ice Cream and 2 cards drawn to accelerate through our 33-card deck. It helps us find key pieces like Prowess+ and Accuracy faster without costing a draw.
  strategic_note: Committed to Ice Cream energy-banking and Shiv/Poison hybrid: rely on massive starting energy and banking to play huge hands. Prioritize abundant card draw and X-cost/high-impact cards. Avoid adding low-impact common attacks.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 8->60 | Gold 250->250 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 250->250 | Deck 34->34
  deck_change: no deck change
  reasoning: Spiked Gauntlets provides +1 Energy per turn, which is incredible with Ice Cream for banking energy. We only have three Powers (Accuracy, Noxious Fumes, Prowess) and we generate 8 Energy on Turn 1 (Lantern + Very Hot Cocoa), so paying 1 extra energy for them is trivial.
  strategic_note: Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 250->250 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 250->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Following the recommended route to enter Act 2. Although the general strategy advises avoiding Act 2 hallway fights, I currently have 60/73 HP and 250 gold. Taking an early monster fight helps test the consistency of the Ice Cream/Predator engine and provides a card reward to improve scaling before the middle of the act.
  strategic_note: Committed Ice Cream energy-banking strategy: accumulate energy on quiet turns to fuel high-impact cycles of Predator+ and Leg Sweep, prioritizing card draw to ensure banked energy is never wasted; focus on finding more draw power to capitalize on banked energy.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 250->265 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 265->265 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 265->265 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 61->61 | Gold 265->265 | Deck 34->34
  deck_change: no deck change
  reasoning: With our immense starting energy (Very Hot Cocoa, Lantern, Spiked Gauntlets) and Ice Cream, energy is not our bottleneck—card draw is. Adding low-impact 0-cost cards like Slice+ or Deflect+ only dilutes our draws and prevents us from finding our high-impact scaling cards (Prowess+, Accuracy) or draw engines (Expertise+). Skipping to keep the deck lean.
  strategic_note: Committed to Ice Cream energy banking and Shivs with Prowess+. Prioritize heavy card draw and high-impact cards to dump excess energy. Skip low-impact or 0-cost cards since energy is abundant and draw is the real bottleneck.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Unknown

F36 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 61->61 | Gold 265->265 | Deck 34->33
  deck_change: lost Lantern Key
  reasoning: Trading the Lantern Key for 2 random relics and 2 potions provides a massive, immediate power spike for Act 3. While History Course is a unique and powerful relic, its requirement to carefully sequence the final card of every turn could backfire with our discard cards (Survivor, Storm of Steel) or be underwhelming if we end on a simple Shiv.
  strategic_note: Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim potion: Clarity Extract

F36 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim relic: Tough Bandages

F36 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim relic: Strike Dummy

F36 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Unknown

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Unknown

F38 [event] choose_event_option (option_index=0) | source=llm
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: The only available choice is to Accept.
  strategic_note: Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.

F38 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 265->265 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 265->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Monster

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 265->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Deck size is already 33 and none of these Common cards provide a significant scaling or draw benefit. The deck already has enough Shiv generation and chip damage; skipping keeps the deck slightly leaner to find critical cards like Prowess+, Adrenaline, and Accuracy more reliably.
  strategic_note: Committed to Shiv/Energy Ice Cream plan: stall and draw heavily with Acrobatics/Backflip while banking massive energy, using Shivs and Prowess+ to scale up and burst enemies. Skip minor attacks and prioritize heavy card draw or premium rare powers.

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Unknown

F40 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Transforming a basic Strike removes a weak card from our deck and potentially replaces it with a useful utility or draw card. This aligns much better with our strategy than adding self-damage to an attack.
  strategic_note: Committed to Shivs and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively.

F40 [card_select] select_deck_card (option_index=0) | source=llm
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: changed: +Murder; -Strike
  reasoning: Transforming a basic Strike is standard to remove low-impact cards and potentially gain a valuable scaling or utility piece.
  strategic_note: Committed Shiv/Energy plan: We have massive energy generation and Shivs/Accuracy for damage. Look to thin out basic cards and acquire card draw to utilize our huge energy pool.

F40 [event] choose_event_option (option_index=0) | source=auto
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 280->280 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 48->48 | Gold 280->317 | Deck 33->33
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 48->48 | Gold 317->317 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim: Eternal Feather

F41 [treasure] proceed | source=random
  HP 48->48 | Gold 317->317 | Deck 33->33
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=1) | source=llm
  HP 48->48 | Gold 317->0 | Deck 33->33
  deck_change: no deck change
  reasoning: My current HP (48/75) is too low to safely challenge an Act 3 Elite, especially following the expert knowledge suggesting 0 Elites in Act 3 for the Silent. The Unknown node offers a safer path to the upcoming Rest Site and Shop where I can spend my 317 gold to finalize the deck for the boss.
  strategic_note: Committed Shiv and Ice Cream engine: prioritize frontloaded card draw and defensive consistency to leverage banked energy, avoiding Act 3 Elites to preserve HP for the final boss.

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 317->326 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 326->326 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F42 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 39->39 | Gold 326->326 | Deck 33->33
  deck_change: no deck change
  reasoning: Our deck is currently at 33 cards and has sufficient scaling with Shivs/Accuracy and our existing Noxious Fumes. The upcoming boss requires bursting down the Queen quickly before her debuffs and scaling overwhelm us. Haze is too clunky without massive discard support, Noxious Fumes costs 2 energy due to Spiked Gauntlets and is too slow for the burst requirement, and Dagger Spray is low-impact generic AoE. Skipping to keep the deck as lean as possible.
  strategic_note: Focus on finding fast frontload damage or high-value draw to burst down the Queen in Act 3 boss. Skip slow scaling powers and clunky cards.

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 326->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Elite

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 326->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 33 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 359->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim relic: Regal Pillow

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 359->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 40->40 | Gold 359->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Our deck relies heavily on Shiv generation with Accuracy and scaling with Prowess+. We already have two copies of Leg Sweep for mitigation, and adding more cards at this point dilutes our draw density for our core scaling and energy-generation pieces. Skipping keeps the deck lean and consistent for the upcoming boss.
  strategic_note: Committed Shiv/Str/Dex plan: cycle rapidly using surplus energy to play Accuracy and Prowess+ multiple times. Play shivs aggressively to trigger Nunchaku and Pen Nib. Prioritize card removal to accelerate scaling setup.

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 40->58 | Gold 359->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: RestSite

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=24, note_scope=run, note_triggers=all) | source=llm
  HP 58->58 | Gold 359->359 | Deck 33->33
  deck_change: upgraded Accuracy->Accuracy+
  reasoning: We are only missing 19 HP, so resting with Regal Pillow would overheal significantly. We are committed to a Shiv strategy, and upgrading Accuracy to Accuracy+ permanently adds 2 damage to every single Shiv we play for the rest of the run, providing massive scaling for the Act 3 Boss.
  strategic_note: Committed to Shivs (Accuracy) and Ice Cream energy banking: build immense Turn 1 energy, play out our hand, and save excess for high-cost defense (Leg Sweep). Focus on card draw to utilize energy reserves and play safe defensively. Need to thin out Strikes to improve consistency.

F44 [rest_site] proceed | source=auto
  HP 58->58 | Gold 359->359 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 359->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Monster

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 359->366 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F45 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 59->59 | Gold 366->366 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 59->59 | Gold 366->366 | Deck 33->33
  deck_change: no deck change
  reasoning: The deck is quite large at 33 cards. We already have reliable scaling from Prowess+ and Accuracy+, and strong mitigation from Leg Sweeps and Tough Bandages. Strangle is okay with Shivs but doesn't solve any immediate problems, and unupgraded Cloak and Dagger is too low impact. Skipping keeps the deck focused on drawing into core pieces.
  strategic_note: Committed plan: stall and build up strength/dex with Prowess+, using Shivs from Blade Dance and Cloak and Dagger alongside Ice Cream energy banking to clear enemies. Discard cards to trigger Tough Bandages for extra defense. Avoid adding low-impact cards.

F45 [map] choose_map_node (option_index=0) | source=llm
  HP 59->59 | Gold 366->366 | Deck 33->33
  deck_change: no deck change
  reasoning: I have 366 gold and a functional energy-banking deck. A shop at this stage is the highest-value node to find card draw (Acrobatics/Backflip) or powerful relics that complement Ice Cream and Shivs. This follows the strategic advice of hitting a late-act shop with high gold reserves while avoiding unnecessary combats before the final boss.
  strategic_note: Committed Shiv and Ice Cream engine: bank energy on easy turns to fuel expensive defense or massive draw sequences. Priority is finding more card draw to convert banked energy into impact and removing basic strikes to improve consistency.

F46 [shop] buy_card (option_index=2) | source=plan
  HP 59->59 | Gold 366->210 | Deck 33->34
  deck_change: bought Adrenaline
  reasoning: Shop plan [1/3]: Adrenaline is the premier cycle and energy card for Silent, effectively thinning the deck and accelerating setup.

F46 [shop] remove_card_at_shop | source=plan
  HP 59->59 | Gold 210->210 | Deck 34->34
  deck_change: no deck change
  reasoning: Shop plan [2/3]: Removing a basic Strike to improve the density of our engine pieces (Shivs, Prowess) and defensive tools.

F46 [card_select] select_deck_card (option_index=0) | source=llm
  HP 59->59 | Gold 210->110 | Deck 34->33
  deck_change: lost Strike
  reasoning: Strikes are the weakest cards in the deck and dilute our draws from scaling powers, block, and better attacks.
  strategic_note: Committed plan: generate huge energy and draw through Adrenaline/Expertise, scaling with Accuracy/Shivs and Prowess. Continue removing Strikes to cycle faster.

F46 [shop] buy_card (option_index=5) | source=plan
  HP 59->59 | Gold 110->22 | Deck 33->34
  deck_change: bought Finesse
  reasoning: Shop plan [3/3]: Finesse provides 0-cost block that scales with our Dexterity and cycles itself, keeping our turns fluid.

F46 [shop] close_shop_inventory | source=plan
  HP 59->59 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F46 [shop] proceed | source=auto
  HP 59->59 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 59->77 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=23, note_scope=run) | source=llm
  HP 77->77 | Gold 22->22 | Deck 34->34
  deck_change: upgraded Adrenaline->Adrenaline+
  reasoning: With 77/78 HP, healing is effectively useless, so we must Smith. Upgrading Adrenaline to gain 2 Energy instead of 1 provides a massive tempo boost, helping us jumpstart our turn with Ice Cream and our card draw engine.
  strategic_note: Committed shiv and energy-banking engine: play Adrenaline and zero-cost draw to build energy with Ice Cream, deploy shivs for damage, and use the banked energy for Leg Sweep or finishing with Murder. Keep the deck thin and focus on playing high-draw turns.

F47 [rest_site] proceed | source=auto
  HP 77->77 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 77->77 | Gold 22->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 31->31 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 31->0 | Gold 22->22 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (9 replays)
[Selected: elite] Bygone Effigy (F12, elite)
## Combat Replay: vs Bygone Effigy (Floor 12, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream
Deck (19): Defend x5, Strike x5, Dagger Throw x2, Clumsy, Dagger Spray, Neutralize+, Poisoned Stab, Predator+, Prowess+, Survivor
Enemies: Bygone Effigy HP=127/127

### Round 1
Intent: Bygone Effigy: Sleep
  turn_end
    block +4

### Round 2
Agent plan (hypothesis): Energy conserved, big draw next turn.
Intent: Bygone Effigy: Buff
  Prowess+
    energy -1 | +Strength(2) | +Dexterity(2)
  Neutralize+ -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -6, +Weak(2)
  Predator+ -> Bygone Effigy[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Bygone Effigy: hp -26
  turn_end
    exhausted: Clumsy [0]: Unplayable. Ethereal.

### Round 3
Agent plan (hypothesis): Next turn we'll have a fresh deck with 6 energy, play attacks to maximize Slow.
Intent: Bygone Effigy: Attack(17)
  Defend
    energy -1 | block +7
  Survivor
    energy -1 | block +10
  Defend
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -9
  turn_end

### Round 4
Agent plan (hypothesis): If we don't draw Neutralize+ or enough block, use Gambler's Brew on the remaining Strikes to dig deeper.
Agent plan (hypothesis): Poison is applied, keep stacking Slow on big damage turns.
Intent: Bygone Effigy: Attack(23)
  Dagger Throw -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -11
  Strike
  Gambler's Brew
  Strike
  Strike
  confirm
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Poisoned Stab -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -10, +Poison(3)
  Survivor
    energy -1 | block +10
  turn_end

### Round 5
Agent plan (hypothesis): Play defenses after seeing what we draw to minimize the 23 incoming damage.
Agent plan (hypothesis): We will have Neutralize next turn to apply weak and finish the fight.
Intent: Bygone Effigy: Attack(23)
  Dagger Throw -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -11
  Strike
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end

### Round 6
Agent plan (hypothesis): Lethal next turn
Intent: Bygone Effigy: Attack(23)
  Neutralize+ -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -6, +Weak(2)
  Defend
    energy -1 | block +7
  Dagger Spray
    energy -1 | enemy_deltas: Bygone Effigy: hp -14
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -10
  turn_end

### Round 7
Agent plan (hypothesis): Good job surviving and using Slow effectively.
Intent: Bygone Effigy: Attack(17)
  Dagger Throw -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -11
  Defend
  Strike -> Bygone Effigy[0]
    energy -1 | -Strength | -Dexterity | enemy_deltas: Bygone Effigy: DIED
## Combat Analytics: Bygone Effigy (WIN - 7 rounds)

Cards played (with descriptions):
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity." -> 1 plays
  Neutralize+ "Deal 6 damage. Apply 2 Weak." -> 2 plays, 12 dmg
  Predator+ "Deal 22 damage. Next turn, draw 2 cards." -> 1 plays, 26 dmg
  Defend "Gain 7 Block." -> 7 plays, 49 block
  Survivor "Gain 10 Block. Discard 1 card." -> 2 plays, 20 block
  Strike "Deal 8 damage." -> 3 plays, 19 dmg
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 3 plays, 33 dmg
  Poisoned Stab "Deal 8 damage. Apply 3 Poison." -> 1 plays, 10 dmg, +3 poison
  Dagger Spray "Deal 6 damage to ALL enemies twice." -> 1 plays, 14 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:-
  Slow: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Strength: R1:- -> R2:- -> R3:10 -> R4:10 -> R5:10 -> R6:10 -> R7:10
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1

[Selected: elite] Phrog Parasite (F15, elite)
## Combat Replay: vs Phrog Parasite (Floor 15, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern
Deck (21): Defend x5, Strike x5, Dagger Throw x2, Backstab, Clumsy, Dagger Spray, Leg Sweep, Neutralize+, Poisoned Stab, Predator+, Prowess+, Survivor
Enemies: Phrog Parasite HP=62/62

### Round 1
Intent: Phrog Parasite: StatusCard(3)
  Backstab -> Phrog Parasite[0]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Phrog Parasite: hp -11
  Neutralize+ -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -4, +Weak(2)
  turn_end

### Round 2
Agent plan (hypothesis): Preserving HP with full block before cycling.
Intent: Phrog Parasite: Attack(3x4=12)
  Dagger Spray
    energy -1 | enemy_deltas: Phrog Parasite: hp -8
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Dagger Throw -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -9
  turn_end

### Round 3
Intent: Phrog Parasite: StatusCard(3)
  Dagger Throw -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -9
  Leg Sweep
  Predator+ -> Phrog Parasite[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Phrog Parasite: hp -20
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: DIED
  turn_end
    exhausted: Clumsy [0]: Unplayable. Ethereal.

### Round 4
Agent plan (hypothesis): Infection discarded to prevent damage.
Intent: Wriggler: Attack(6), Wriggler: Buff, StatusCard(1), Wriggler: Attack(6), Wriggler: Buff, StatusCard(1)
  Prowess+
    energy -1 | +Strength(2) | +Dexterity(2)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Dagger Throw -> Wriggler[2]
    energy -1
  Infection
  turn_end

### Round 5
Agent plan (hypothesis): Enemies will be very low HP next turn, clean them up.
Agent plan (hypothesis): Clean up the Wrigglers next turn.
Intent: Wriggler: Buff, StatusCard(1), Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Dagger Spray
    energy -1 | enemy_deltas: Wriggler: hp -12
  Neutralize+ -> Wriggler[1]
  Defend
    energy -1 | block +7
  Survivor
    energy -1 | block +10
  turn_end

### Round 6
Agent plan (hypothesis): Finish the last Wriggler off next turn.
Agent plan (hypothesis): Finish the last Wriggler.
Agent plan (hypothesis): Last Wriggler is at 1 HP. Kill it immediately.
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Buff, StatusCard(1)
  Skill Potion
  Shadow Step
  Strike -> Wriggler[0]
    energy -1
  Strike -> Wriggler[1]
    energy -1 | enemy_deltas: Wriggler: hp -8
  Strike -> Wriggler[1]
    energy -1 | enemy_deltas: Wriggler: +Weak(1)
  Shadow Step
    +Shadow Step(1)
  turn_end

### Round 7
Agent plan (hypothesis): Combat ended efficiently.
Intent: Wriggler: Attack(10)
  Strike -> Wriggler[0]
    energy -1 | -Strength | -Dexterity | -Double Damage | enemy_deltas: Wriggler: DIED
## Combat Analytics: Phrog Parasite (WIN - 7 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 2 plays, 20 dmg
  Defend "Gain 5 Block." -> 6 plays, 36 block
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 18 dmg
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Strike "Deal 6 damage." -> 5 plays, 8 dmg
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity." -> 1 plays
  Survivor "Gain 10 Block. Discard 1 card." -> 1 plays, 10 block
  Shadow Step "Discard your Hand. Next turn, Attacks deal double damage." -> 1 plays

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:- -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:4
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:-
  Strength[3]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:- -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:-

[Selected: boss] Vantom (F17, boss)
## Combat Replay: vs Vantom (Floor 17, boss)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku
Deck (21): Defend x5, Strike x5, Dagger Throw x2, Backstab, Clumsy, Dagger Spray, Leg Sweep, Neutralize+, Poisoned Stab, Predator+, Prowess+, Survivor
Enemies: Vantom HP=173/173

### Round 1
Agent plan (hypothesis): Continue using small attacks to strip Slippery quickly before committing high damage hits.
Intent: Vantom: Attack(7)
  Backstab -> Vantom[0]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Vantom: hp -1, Slippery(9→8)
  Poisoned Stab -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -1, Slippery(8→7), +Poison(3)
  Leg Sweep -> Vantom[0]
    energy -2 | block +11 | enemy_deltas: Vantom: +Weak(2)
  turn_end
    exhausted: Clumsy [0]: Unplayable. Ethereal.

### Round 2
Agent plan (hypothesis): Save energy if drawing a low-value card, as we have Ice Cream.
Intent: Vantom: Attack(4x2=8)
  Neutralize+ -> Vantom[0]
    enemy_deltas: Vantom: hp -1, Slippery(6→5), Weak(1→3)
  Defend
    energy -1 | block +5
  Dagger Throw -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -1, Slippery(5→4)
  Predator+
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -1, Slippery(4→3)
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -1, Slippery(3→2)
  turn_end

### Round 3
Intent: Vantom: Attack(20), StatusCard(3)
  Prowess+
    energy -1 | +Strength(2) | +Dexterity(2)
  Dagger Spray
    energy -1 | enemy_deltas: Vantom: hp -7, -Slippery
  Survivor
    energy -1 | block +10
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): We have Ice Cream and gained energy from Nunchaku.
Intent: Vantom: Buff
  Dagger Spray
    energy -1 | enemy_deltas: Vantom: hp -12
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8
  Strike -> Vantom[0]
    enemy_deltas: Vantom: hp -8
  turn_end

### Round 5
Agent plan (hypothesis): Slippery is gone, we can now start hitting hard. Conserving energy with Ice Cream.
Intent: Vantom: Attack(9)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8
  turn_end

### Round 6
Agent plan (hypothesis): Next turn will be huge with 7 draw.
Intent: Vantom: Attack(8x2=16)
  Dagger Throw -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -11
  Wound
  Predator+ -> Vantom[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Vantom: hp -22
  Survivor
    energy -1 | block +10
  Dagger Throw
  turn_end

### Round 7
Agent plan (hypothesis): Vantom will have Weak applied, dropping its damage. Keep stacking poison and surviving.
Intent: Vantom: Attack(29), StatusCard(3)
  Neutralize+ -> Vantom[0]
    enemy_deltas: Vantom: hp -6, +Weak(2)
  Leg Sweep -> Vantom[0]
    energy -2 | block +13 | enemy_deltas: Vantom: Weak(2→4)
  Poisoned Stab -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8, +Poison(3)
  turn_end

### Round 8
Agent plan (hypothesis): Saved 0 energy, but dealt solid damage.
Intent: Vantom: Buff
  Dagger Throw -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -11
  Wound
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8
  turn_end

### Round 9
Agent plan (hypothesis): Lethal next turn with Predator+.
Intent: Vantom: Attack(8)
  Defend
    energy -1 | block +7
  Strike -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -8
  Dagger Throw -> Vantom[0]
    energy -1 | enemy_deltas: Vantom: hp -11
  Defend
  Defend
    energy -1 | block +7
  turn_end

### Round 10
Intent: Vantom: Attack(7x2=14)
  Predator+ -> Vantom[0]
    energy -2 | -Strength | -Dexterity | enemy_deltas: Vantom: DIED
## Combat Analytics: Vantom (WIN - 10 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 1 dmg, EXHAUST
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 9 dmg, +6 poison
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 24 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 7 dmg
  Defend "Gain 5 Block." -> 5 plays, 33 block
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 4 plays, 34 dmg
  Strike "Deal 6 damage." -> 8 plays, 50 dmg
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity." -> 1 plays
  Dagger Spray "Deal 6 damage to ALL enemies twice." -> 2 plays, 19 dmg
  Survivor "Gain 10 Block. Discard 1 card." -> 2 plays, 20 block
  Predator+ "Deal 22 damage. Next turn, draw 2 cards." -> 2 plays, 22 dmg

Poison stacks applied per card:
  Poisoned Stab: 6 stacks

Enemy power timeline:
  Poison: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2 -> R9:1 -> R10:-
  Slippery: R1:9 -> R2:6 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4
  Weak: R1:- -> R2:1 -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:3 -> R9:2 -> R10:1

[Selected: elite] multi:Decimillipede+Decimillipede+Decimillipede (F24, elite)
## Combat Replay: vs multi:Decimillipede+Decimillipede+Decimillipede (Floor 24, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa
Deck (28): Defend x5, Strike x5, Dagger Throw x2, Backstab, Blade Dance, Cloak and Dagger+, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Leg Sweep, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Decimillipede HP=42/42, Decimillipede HP=44/44, Decimillipede HP=46/46

### Round 1
Agent plan (hypothesis): Watch out for Reattach mechanics; try to kill all segments on the same turn.
Agent plan (hypothesis): HP is now 17, 12, 12 with 3 poison on index 2.
Agent plan (hypothesis): HP is now balanced. Use AoE or targeted attacks next turn to finish them off simultaneously.
Intent: Decimillipede: Attack(8), Debuff, Decimillipede: Attack(5x2=10), Decimillipede: Attack(6), Buff
  Backstab -> Decimillipede[2]
    energy +1 | exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Decimillipede: hp -11
  Neutralize+ -> Decimillipede[1]
    enemy_deltas: Decimillipede: hp -4, +Weak(2)
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Decimillipede[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Decimillipede: hp -4
  Shiv -> Decimillipede[0]
    enemy_deltas: Decimillipede: hp -4
  Predator+ -> Decimillipede[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Decimillipede: hp -20
  Expertise+
    energy -1
  Piercing Wail
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Decimillipede: +Strength(-6), +Piercing Wail(6); Decimillipede: +Strength(-6), +Piercing Wail(6); Decimillipede: +Strength(-6), +Piercing Wail(6)
  Dagger Spray
    energy -1 | enemy_deltas: Decimillipede: hp -8; Decimillipede: hp -8; Decimillipede: hp -8
  Dagger Throw -> Decimillipede[0]
    energy -1 | enemy_deltas: Decimillipede: hp -9
  Defend
  Dagger Throw -> Decimillipede[2]
    energy -1 | enemy_deltas: Decimillipede: hp -9
  Strike
  Poisoned Stab -> Decimillipede[2]
    energy -1 | enemy_deltas: Decimillipede: hp -6, +Poison(3)
  turn_end

### Round 2
Agent plan (hypothesis): Depending on the draw, prioritize blocking or mitigating the multi-attack from index 2.
Agent plan (hypothesis): We are weakened, wait it out and align their HP for a simultaneous kill. Be mindful of Ripple Basin for extra block.
Intent: Decimillipede: Attack(6), Buff, Decimillipede: Attack(6), Debuff, Decimillipede: Attack(7x2=14)
  Finesse
    block +4
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  turn_end
    block +4

### Round 3
Agent plan (hypothesis): Enemies will be at 11, 9, 7 HP. Finish them off simultaneously to prevent Reattach.
Intent: Decimillipede: Attack(7x2=14), Decimillipede: Attack(6), Buff, Decimillipede: Attack(10), Debuff
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Decimillipede[0]
    enemy_deltas: Decimillipede: hp -3
  Shiv -> Decimillipede[0]
    energy +1 | enemy_deltas: Decimillipede: hp -3
  Shiv -> Decimillipede[1]
    enemy_deltas: Decimillipede: hp -3
  Leg Sweep -> Decimillipede[0]
    energy -2 | block +11 | enemy_deltas: Decimillipede: +Weak(2)
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): Next turn, index 0 is at 4 HP, index 1 at 6 HP. Kill them both simultaneously to prevent any revives and end the fight.
Agent plan (hypothesis): Look for AoE to finish them off or strong block.
Agent plan (hypothesis): Enemies will be at 2 and 3 HP. Kill both next turn.
Intent: Decimillipede: Attack(7), Debuff, Decimillipede: Attack(7x2=14), Decimillipede: Attack(8), Buff
  Neutralize+ -> Decimillipede[1]
    enemy_deltas: Decimillipede: hp -3, +Weak(2)
  Dagger Throw -> Decimillipede[2]
    energy -1 | enemy_deltas: Decimillipede: hp -6, -Strength, DIED
  Strike
  Finesse
    block +4
  Dagger Throw -> Decimillipede[0]
    energy -1 | enemy_deltas: Decimillipede: hp -6
  Poisoned Stab
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Decimillipede[1]
    enemy_deltas: Decimillipede: hp -3
  Shiv -> Decimillipede[0]
    enemy_deltas: Decimillipede: hp -3
  turn_end

### Round 5
Intent: Decimillipede: Attack(8), Buff, Decimillipede: Attack(7), Debuff
  Storm of Steel
    energy -1
  Shiv -> Decimillipede[0]
    enemy_deltas: Decimillipede: hp -2, -Strength, DIED
  Shiv -> Decimillipede[1]
    -Weak | enemy_deltas: Decimillipede: hp -3, -Strength, -Weak, DIED
## Combat Analytics: multi:Decimillipede+Decimillipede+Decimillipede (WIN - 5 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 7 dmg
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 2 plays, 12 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 9 plays, 28 dmg, EXHAUST
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 24 dmg
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 4 plays, 30 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Finesse "Gain 4 Block. Draw 1 card." -> 2 plays, 8 block
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 1 plays, 4 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, generates 1 Shivs

Token attribution (Shivs):
  Cloak and Dagger+: 4 Shivs -> ~12 dmg
  Blade Dance: 3 Shivs -> ~9 dmg
  Storm of Steel: 1 Shivs -> ~3 dmg
  other: 1 Shivs -> ~3 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:-
  Reattach[0]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25
  Reattach[1]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25
  Reattach[2]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:-
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Decimillipede+Decimillipede+Decimillipede (Floor 29, elite)
Relics: Ring of the Snake, Neow's Torment, The Chosen Cheese, Vexing Puzzlebox, Very Hot Cocoa, Art of War, Amethyst Aubergine
Deck (28): Defend x5, Strike x4, Poisoned Stab x2, Abrasive, Acrobatics+, Backflip, Bubble Bubble, Burst, Dagger Spray+, Dagger Throw, Footwork+, Haze, Neow's Fury, Neutralize+, Outbreak, Predator+, Prepared+, Snakebite, Survivor, Untouchable+
Enemies: Decimillipede HP=44/44, Decimillipede HP=46/46, Decimillipede HP=40/40

### Round 1
Intent: Decimillipede: Attack(8), Debuff, Decimillipede: Attack(5x2=10), Decimillipede: Attack(6), Buff
  Survivor
    energy -1 | block +8
  Abrasive
  Dodge and Roll
    block +5 | +Dexterity(1) | +Thorns(4) | +Block Next Turn(5)
  Dagger Spray+
    energy -1 | enemy_deltas: Decimillipede: hp -12; Decimillipede: hp -12; Decimillipede: hp -12
  Acrobatics+
    energy -1
  Haze
  Predator+ -> Decimillipede[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Decimillipede: hp -20
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Prepared+
  Burst
  Outbreak
  Neutralize+ -> Decimillipede[2]
    enemy_deltas: Decimillipede: hp -4, +Weak(2)
  turn_end

### Round 2
Intent: Decimillipede: Attack(6), Buff, Decimillipede: Attack(8), Debuff
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Poisoned Stab -> Decimillipede[1]
    energy -1 | enemy_deltas: Decimillipede: hp -4, Poison(3→6)
  turn_end

### Round 3
Intent: Decimillipede: Attack(7x2=14), Decimillipede: Attack(6), Buff, Decimillipede: Attack(8), Debuff
  Strike -> Decimillipede[0]
    energy -1 | enemy_deltas: Decimillipede: hp -4
  Strike -> Decimillipede[0]
    energy -1 | enemy_deltas: Decimillipede: hp -4
  Strike -> Decimillipede[0]
    energy -1 | enemy_deltas: Decimillipede: hp -4
  turn_end

### Round 4
Intent: Decimillipede: Attack(6), Buff
  Survivor
    energy -1 | block +9
  Untouchable+
  Snakebite -> Decimillipede[2]
    energy -2 | enemy_deltas: Decimillipede: +Poison(7)
  turn_end

### Round 5
Intent: Decimillipede: Attack(8), Debuff, Decimillipede: Attack(6), Buff, Decimillipede: Attack(7x2=14)
  Neow's Fury -> Decimillipede[2]
    energy -1 | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Decimillipede: hp -10, -Poison, -Strength, DIED
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end

### Round 6
Intent: Decimillipede: Attack(6), Buff, Decimillipede: Attack(7x2=14)
  Neutralize+ -> Decimillipede[1]
    enemy_deltas: Decimillipede: hp -3, +Weak(2)
  Dagger Throw -> Decimillipede[1]
    energy -1 | enemy_deltas: Decimillipede: hp -6
  Strike
  Strike -> Decimillipede[1]
    energy -1 | enemy_deltas: Decimillipede: hp -4
  Strike -> Decimillipede[1]
    energy -1 | enemy_deltas: Decimillipede: hp -4
  turn_end

### Round 7
Intent: Decimillipede: Attack(7x2=14), Decimillipede: Attack(5x2=10)
  Acrobatics+
    energy -1
  Predator+
  Prepared+
  Strike
  Strike
  Neutralize+ -> Decimillipede[0]
    enemy_deltas: Decimillipede: hp -4, +Weak(2)
  Burst
    energy -1 | +Burst(1)
  Defend
    energy -1 | block +12 | -Burst
  turn_end
## Combat Analytics: multi:Decimillipede+Decimillipede+Decimillipede (LOSS - 7 rounds)
Death cause: Killed by damage. HP 2 -> 0, took 0 damage.

Cards played (with descriptions):
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 17 block
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 1 plays, 5 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 1 plays, 36 dmg
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Defend "Gain 6 Block." -> 6 plays, 42 block
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 11 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 2 plays, 12 block
  Poisoned Stab "Deal 4 damage. Apply 3 Poison." -> 1 plays, 4 dmg, +3 poison
  Strike "Deal 4 damage." -> 5 plays, 20 dmg
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, +7 poison
  Neow's Fury "Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust." -> 1 plays, 10 dmg, EXHAUST
  Dagger Throw "Deal 6 damage. Draw 1 card. Discard 1 card." -> 1 plays, 6 dmg
  Burst "This turn, your next Skill is played an extra time." -> 1 plays

Poison stacks applied per card:
  Snakebite: 7 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:6 -> R6:- -> R7:-
  Poison[0]: R1:- -> R2:3 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:-
  Poison[1]: R1:- -> R2:3 -> R3:5 -> R4:- -> R5:- -> R6:- -> R7:-
  Reattach[0]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25 -> R6:25 -> R7:25
  Reattach[1]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25 -> R6:25 -> R7:25
  Reattach[2]: R1:25 -> R2:25 -> R3:25 -> R4:25 -> R5:25 -> R6:25 -> R7:25
  Strength: R1:- -> R2:- -> R3:2 -> R4:- -> R5:2 -> R6:2 -> R7:2

[Selected: run_combat] Hunter Killer (F28, monster)
Historical: loss=0 vs historical avg=6.0+/-5.0 (z=-1.2, BETTER_THAN_USUAL, n=3)
## Combat Replay: vs Hunter Killer (Floor 28, monster)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese
Deck (31): Defend x5, Strike x5, Dagger Throw x2, Leg Sweep x2, Backstab, Blade Dance, Cloak and Dagger+, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Lantern Key, Leading Strike, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Hunter Killer HP=121/121

### Round 1
Agent plan (hypothesis): See what Dagger Throw draws, play it if it's useful scaling or damage.
Agent plan (hypothesis): Tender will reduce stats per card played starting next turn. Plan carefully to play key cards first.
Intent: Hunter Killer: Debuff
  Backstab -> Hunter Killer[0]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Hunter Killer: hp -11
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Hunter Killer[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Hunter Killer: hp -4
  Shiv -> Hunter Killer[0]
    enemy_deltas: Hunter Killer: hp -4
  Strike -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -6
  Strike -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -12
  Dagger Throw -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -9
  Defend
  Leading Strike -> Hunter Killer[0]
    enemy_deltas: Hunter Killer: hp -3
  Shiv -> Hunter Killer[0]
    enemy_deltas: Hunter Killer: hp -4
  Shiv -> Hunter Killer[0]
    enemy_deltas: Hunter Killer: hp -4
  Storm of Steel
    energy -1
  turn_end

### Round 2
Agent plan (hypothesis): We skipped weak Strikes to bank energy thanks to Ice Cream.
Intent: Hunter Killer: Attack(7x3=21)
  Leg Sweep -> Hunter Killer[0]
    energy -2 | block +11 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: +Weak(2)
  Defend
    energy -1 | block +4 | Strength(-1→-2) | Dexterity(-1→-2)
  Noxious Fumes
    energy -1 | Strength(-2→-3) | Dexterity(-2→-3) | +Noxious Fumes(2)
  turn_end
    block +4

### Round 3
Intent: Hunter Killer: Attack(5x3=15)
  Heart of Iron
    +Plating(7)
  Defend
    energy -1 | block +5 | +Strength(-1) | +Dexterity(-1)
  Predator+ -> Hunter Killer[0]
    energy -2 | Strength(-1→-2) | Dexterity(-1→-2) | +Draw Cards Next Turn(2) | enemy_deltas: Hunter Killer: hp -19
  Dagger Throw -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -7
  Lantern Key
  Piercing Wail
    energy -1 | Strength(-3→-4) | Dexterity(-3→-4) | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Hunter Killer: +Strength(-6), +Piercing Wail(6)
  Blade Dance
    energy -1 | Strength(-4→-5) | Dexterity(-4→-5) | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  Shiv -> Hunter Killer[0]
    Strength(-5→-6) | Dexterity(-5→-6)
  Shiv -> Hunter Killer[0]
    Strength(-6→-7) | Dexterity(-6→-7)
  Shiv -> Hunter Killer[0]
    Strength(-7→-8) | Dexterity(-7→-8)
  turn_end
    block +7

### Round 4
Intent: Hunter Killer: Attack(17)
  Poisoned Stab -> Hunter Killer[0]
    energy -1 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -12, Poison(3→6)
  Neutralize+ -> Hunter Killer[0]
    Strength(-1→-2) | Dexterity(-1→-2) | enemy_deltas: Hunter Killer: hp -3, +Weak(2)
  Finesse
    block +2 | Strength(-2→-3) | Dexterity(-2→-3)
  Survivor
    energy -1 | block +5
  Strike
  turn_end
    block +6

### Round 5
Intent: Hunter Killer: Attack(5x3=15)
  Predator+ -> Hunter Killer[0]
    energy -2 | hp +1 | -Tender | -Noxious Fumes | -Plating | enemy_deltas: Hunter Killer: DIED
## Combat Analytics: Hunter Killer (WIN - 5 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 1 plays, 6 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 7 plays, 16 dmg, EXHAUST
  Strike "Deal 6 damage." -> 2 plays, 18 dmg
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 16 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, generates 2 Shivs
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, generates 1 Shivs
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Defend "Gain 4 Block." -> 2 plays, 9 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Predator+ "Deal 19 damage. Next turn, draw 2 cards." -> 2 plays, 19 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Poisoned Stab "Deal 12 damage. Apply 3 Poison." -> 1 plays, 12 dmg, +3 poison
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 1 plays, 3 dmg
  Finesse "Gain 2 Block. Draw 1 card." -> 1 plays, 2 block
  Survivor "Gain 5 Block. Discard 1 card." -> 1 plays, 5 block

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~7 dmg
  Cloak and Dagger+: 2 Shivs -> ~5 dmg
  Leading Strike: 2 Shivs -> ~5 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:2 -> R4:3 -> R5:7
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:1
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Hunter Killer (Floor 22, monster)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra, Sword of Stone, Yummy Cookie, The Abacus
Deck (22): Defend x5, Strike x4, Snakebite+ x2, Acrobatics, Afterimage+, Blade Dance+, Bullet Time+, Dagger Throw, Deadly Poison, Flick-Flack, Neutralize+, Piercing Wail, Predator, Survivor
Enemies: Hunter Killer HP=121/121

### Round 1
Intent: Hunter Killer: Debuff
  Afterimage+
    energy -1 | +Afterimage(1)
  Predator -> Hunter Killer[0]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Hunter Killer: hp -15
  turn_end

### Round 2
Intent: Hunter Killer: Attack(17)
  Defend
    energy -1 | block +6 | +Strength(-1) | +Dexterity(-1)
  Acrobatics
    energy -1
  Strike
  Bullet Time+
    energy -2 | block +1 | Strength(-2→-3) | Dexterity(-2→-3) | +No Draw(1)
  Defend
    block +3 | Strength(-3→-4) | Dexterity(-3→-4)
  Neutralize+ -> Hunter Killer[0]
    block +1 | Strength(-4→-5) | Dexterity(-4→-5) | enemy_deltas: Hunter Killer: +Weak(2)
  Defend
    block +1 | Strength(-5→-6) | Dexterity(-5→-6)
  Snakebite+ -> Hunter Killer[0]
    block +1 | Strength(-6→-7) | Dexterity(-6→-7) | enemy_deltas: Hunter Killer: +Poison(10)
  Snakebite+ -> Hunter Killer[0]
    block +1 | Strength(-7→-8) | Dexterity(-7→-8) | enemy_deltas: Hunter Killer: Poison(10→20)
  Deadly Poison -> Hunter Killer[0]
    block +1 | Strength(-8→-9) | Dexterity(-8→-9) | enemy_deltas: Hunter Killer: Poison(20→25)
  Dagger Throw -> Hunter Killer[0]
    block +1 | Strength(-9→-10) | Dexterity(-9→-10)
  turn_end
    -Strength

### Round 3
Intent: Hunter Killer: Attack(5x3=15)
  Strike -> Hunter Killer[0]
    energy -1 | block +1 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -6
  Strike -> Hunter Killer[0]
    energy -1 | block +1 | Strength(-1→-2) | Dexterity(-1→-2) | enemy_deltas: Hunter Killer: hp -5
  Piercing Wail
    energy -1 | block +1 | Strength(-2→-3) | Dexterity(-2→-3) | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Hunter Killer: +Strength(-6), +Piercing Wail(6)
  turn_end

### Round 4
Intent: Hunter Killer: Attack(7x3=21)
  Defend
    energy -1 | block +6 | +Strength(-1) | +Dexterity(-1)
  Defend
    energy -1 | block +5 | Strength(-1→-2) | Dexterity(-1→-2)
  Strike -> Hunter Killer[0]
    energy -1 | block +1 | Strength(-2→-3) | Dexterity(-2→-3) | enemy_deltas: Hunter Killer: hp -4
  turn_end

### Round 5
Intent: Hunter Killer: Attack(17)
  turn_end
## Combat Analytics: Hunter Killer (WIN - 5 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg, 1 block
  Defend "Gain 5 Block." -> 5 plays, 21 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays, 1 block
  Neutralize+ "Deal 0 damage. Apply 2 Weak." -> 1 plays, 1 block
  Snakebite+ "Retain. Apply 10 Poison." -> 2 plays, 2 block, +20 poison
  Deadly Poison "Apply 5 Poison." -> 1 plays, 1 block, +5 poison
  Dagger Throw "Deal 0 damage. Draw 1 card. Discard 1 card." -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 3 plays, 15 dmg, 3 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST

Poison stacks applied per card:
  Snakebite+: 20 stacks
  Deadly Poison: 5 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:24 -> R4:23 -> R5:22
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-

[Selected: elite] Entomancer (F30, elite)
## Combat Replay: vs Entomancer (Floor 30, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese
Deck (32): Defend x5, Strike x5, Dagger Throw x2, Leg Sweep x2, Accuracy, Backstab, Blade Dance, Cloak and Dagger+, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Lantern Key, Leading Strike, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Entomancer HP=145/145

### Round 1
Agent plan (hypothesis): Saved 4 energy for Turn 2. Candelabra will provide 2 more. Total starting energy next turn: 9.
Intent: Entomancer: Attack(3x7=21)
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Entomancer: +Strength(-6), +Piercing Wail(6)
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Backstab -> Entomancer[0]
    exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Entomancer: hp -11
  Poisoned Stab -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6, +Poison(3)
  Dagger Throw -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -9
  Lantern Key
  turn_end

### Round 2
Intent: Entomancer: Attack(18)
  Heart of Iron
    +Plating(7)
  Defend
    energy -1 | block +5
  Accuracy
    energy -1 | +Accuracy(4)
  Blade Dance
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust.
  Shiv -> Entomancer[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Entomancer: hp -8
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -8
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -8
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6
  Predator+ -> Entomancer[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Entomancer: hp -40
  turn_end
    block +7

### Round 3
Agent plan (hypothesis): He should die easily next turn. Remember that Ice Cream conserves our unspent energy.
Intent: Entomancer: Buff
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -8
  Shiv -> Entomancer[0]
    energy +1 | enemy_deltas: Entomancer: hp -8
  Dagger Spray
    energy -1 | enemy_deltas: Entomancer: hp -8
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6
  turn_end
    block +6

### Round 4
Intent: Entomancer: Attack(4x7=28)
  Finesse
    block +4
  Leg Sweep -> Entomancer[0]
    energy -2 | block +11 | enemy_deltas: Entomancer: +Weak(2)
  Defend
    energy -1 | block +5
  turn_end
    block +5

### Round 5
Intent: Entomancer: Attack(14)
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6
  Strike -> Entomancer[0]
    energy -1 | hp +1 | -Plating | -Accuracy | enemy_deltas: Entomancer: DIED
## Combat Analytics: Entomancer (WIN - 5 rounds)

Cards played (with descriptions):
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 1 plays, 4 block
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 8 damage. Exhaust." -> 5 plays, 40 dmg, EXHAUST
  Strike "Deal 6 damage." -> 5 plays, 24 dmg
  Predator+ "Deal 40 damage. Next turn, draw 2 cards." -> 1 plays, 40 dmg
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 1 plays, 6 block, generates 2 Shivs
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg
  Finesse "Gain 4 Block. Draw 1 card." -> 1 plays, 4 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~24 dmg
  Cloak and Dagger+: 2 Shivs -> ~16 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2
  Poison: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:1

[Selected: boss] multi:Crusher+Rocket (F33, boss)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese, Happy Flower
Deck (33): Defend x5, Strike x5, Cloak and Dagger+ x2, Dagger Throw x2, Leg Sweep x2, Accuracy, Backstab, Blade Dance, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Lantern Key, Leading Strike, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Agent plan (hypothesis): We have 5 energy banked for next turn. Look for heavy draw to find Noxious Fumes and Accuracy scaling.
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Cloak and Dagger+
    energy -1 | block +6
  Neutralize+ -> Crusher[0]
    enemy_deltas: Crusher: hp -4, +Weak(2)
  Shiv -> Crusher[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: hp -4
  Backstab -> Crusher[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: hp -22
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -9
  Strike
  Leg Sweep -> Rocket[1]
    energy -2 | block +11 | enemy_deltas: Rocket: +Weak(2)
  Shiv -> Crusher[0]
    energy +1 | enemy_deltas: Crusher: hp -4
  turn_end

### Round 2
Agent plan (hypothesis): If we draw cards, keep an eye on orientation - we must attack Rocket last to face him and minimize the Back Attack damage bonus.
Agent plan (hypothesis): We have 10 energy, so we can play whatever we draw. Ensure we end facing Rocket.
Intent: Crusher: Attack(3), Rocket: Attack(20)
  Colorless Potion
  Thinking Ahead
  Thinking Ahead
  Lantern Key
  Dagger Spray
    energy -1 | enemy_deltas: Crusher: hp -8; Rocket: hp -8
  Leading Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -3
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -4
  Poisoned Stab -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -6, +Poison(3)
  Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -6
  Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -6
  Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -12
  turn_end

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Leg Sweep -> Crusher[0]
    energy -2 | block +11 | enemy_deltas: Crusher: +Weak(2)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -6
  turn_end

### Round 4
Intent: Crusher: Buff, Rocket: Attack(49)
  Finesse
    block +3
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Cloak and Dagger+
    energy -1 | block +4
  Blade Dance
    energy -1 | exhausted: Thinking Ahead [0]: Draw 2 cards. Put 1 card from your Hand on top of your Draw Pile. Exhaust.
  Shiv -> Rocket[1]
    energy +1 | enemy_deltas: Rocket: hp -3
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -3
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -3
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -3
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -3
  Expertise+
    energy -1
  Prowess+
    energy -1 | +Strength(2) | +Dexterity(2)
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Survivor
    energy -1 | block +7
  Piercing Wail
  turn_end

### Round 5
Agent plan (hypothesis): Crusher is Weakened for next turn.
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -8
  Lantern Key
  Leg Sweep -> Crusher[0]
    energy -2 | block +9 | enemy_deltas: Crusher: +Weak(2)
  turn_end

### Round 6
Agent plan (hypothesis): Pen Nib is at 9! First attack next turn will deal double damage.
Intent: Crusher: Attack(10), Rocket: Attack(7)
  Cloak and Dagger+
    energy -1 | block +8
  Defend
    energy -1 | block +7
  Poisoned Stab -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -8, Poison(3→6)
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: block -6
  turn_end

### Round 7
Agent plan (hypothesis): We will take severe damage but survive. Next turn we draw 9 cards thanks to Predator+ and Ring of the Snake. Look for Fumes, Accuracy, or Leg Sweep to stabilize.
Intent: Crusher: Attack(6), Rocket: Attack(30)
  Predator+ -> Rocket[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Rocket: hp -44
  Dagger Spray
    energy -1 | enemy_deltas: Crusher: hp -12; Rocket: hp -12
  Leading Strike -> Rocket[1]
    enemy_deltas: Rocket: hp -5
  Neutralize+ -> Rocket[1]
    enemy_deltas: Rocket: hp -6, +Weak(2)
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -6
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -6
  turn_end

### Round 8
Agent plan (hypothesis): Rocket will attack heavily next turn. D&R gives 6 block. Be prepared to face Rocket to avoid Back Attack from the 30 damage hit.
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  Leg Sweep -> Crusher[0]
    energy -2 | block +13 | enemy_deltas: Crusher: +Weak(2)
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(6)
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -8
  turn_end

### Round 9
Agent plan (hypothesis): Crusher attacks heavily next turn (Turn 10). Let poison handle Rocket or kill Rocket AFTER Crusher's attack to avoid buffing Crusher beforehand.
Agent plan (hypothesis): Crusher attacks big next turn. Keep mitigating until Rocket dies to poison, then burst Crusher.
Intent: Crusher: Buff, Rocket: Attack(52)
  Piercing Wail
    energy -1 | exhausted: Thinking Ahead [0]: Draw 2 cards. Put 1 card from your Hand on top of your Draw Pile. Exhaust. | enemy_deltas: Crusher: Strength(2→-4), +Piercing Wail(6); Rocket: Strength(4→-2), +Piercing Wail(6)
  Finesse
    block +4
  Cloak and Dagger+
    energy -1 | block +6
  Survivor
    energy -1 | block +7
  Dagger Throw
  Fortifier
    block +46
  turn_end
    block +4

### Round 10
Agent plan (hypothesis): See what we draw from Expertise+ and use the remaining 2 energy for defense. If Rocket dies to poison, Crusher will enrage, but Crusher attacks first this turn.
Agent plan (hypothesis): Rocket dies to poison this turn, giving Crusher crab rage, but since Crusher attacks before Rocket takes poison damage, Crusher won't have the strength buff for this attack.
Intent: Crusher: Attack(16), Defend, Rocket: Sleep
  Defend
    energy -1 | block +5
  Expertise+
    energy -1
  Neutralize+ -> Crusher[0]
    enemy_deltas: Crusher: hp -4, +Weak(2)
  Poisoned Stab -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -6, Poison(7→10)
  Survivor
    energy -1 | block +7
  Strike
  turn_end

### Round 11
Agent plan (hypothesis): Survive the incoming 16 damage using Ripple Basin.
Intent: Crusher: Attack(16)
  Finesse
    block +6
  Cloak and Dagger+
    energy -1 | block +8
  turn_end
    block +4

### Round 12
Intent: Crusher: Attack(14)
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(6)
  Defend
    energy -1 | block +7
  turn_end
    block +4

### Round 13
Agent plan (hypothesis): Play drawn defensive card if possible to preserve HP.
Intent: Crusher: Attack(16x2=32), Debuff
  Leg Sweep -> Crusher[0]
    energy -2 | block +13 | enemy_deltas: Crusher: +Weak(2)
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -6
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -16
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -11
  Storm of Steel
  Cloak and Dagger+
    energy -1 | block +8
  Shiv -> Crusher[0]
    energy +1 | enemy_deltas: Crusher: hp -6
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -6
  turn_end

### Round 14
Intent: Crusher: Buff
  Predator+ -> Crusher[0]
    energy -2 | hp +1 | -Surrounded | -Noxious Fumes | -Strength | -Dexterity | -Weak | -Frail | enemy_deltas: Crusher: DIED
## Combat Analytics: multi:Crusher+Rocket (WIN - 14 rounds)

Cards played (with descriptions):
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 6 plays, 40 block, generates 2 Shivs
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 14 dmg
  Shiv "Deal 4 damage. Exhaust." -> 15 plays, 61 dmg, EXHAUST
  Backstab "Innate. Deal 22 damage. Exhaust." -> 1 plays, 22 dmg, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 28 dmg
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 5 plays, 57 block
  Thinking Ahead "Draw 2 cards. Put 1 card from your Hand on top of your Draw Pile. Exhaust." -> 1 plays, EXHAUST
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 2 plays, 40 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 2 plays, 8 dmg, generates 2 Shivs
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 3 plays, 20 dmg, +9 poison
  Strike "Deal 6 damage." -> 6 plays, 54 dmg
  Defend "Gain 5 Block." -> 5 plays, 29 block
  Finesse "Gain 3 Block. Draw 1 card." -> 3 plays, 13 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Expertise+ "Draw cards until you have 7 in your Hand." -> 2 plays
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity. Perfect Fit." -> 1 plays
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 3 plays, 16 block
  Survivor "Gain 7 Block. Discard 1 card." -> 3 plays, 21 block
  Predator+ "Deal 44 damage. Next turn, draw 2 cards." -> 2 plays, 44 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST

Active powers: Surrounded(1)

Token attribution (Shivs):
  Cloak and Dagger+: 7 Shivs -> ~28 dmg
  Leading Strike: 4 Shivs -> ~16 dmg
  Blade Dance: 3 Shivs -> ~12 dmg
  other: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Poisoned Stab: 9 stacks

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:1 -> R12:1 -> R13:1 -> R14:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:- -> R12:- -> R13:- -> R14:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:- -> R12:- -> R13:- -> R14:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:- -> R12:- -> R13:- -> R14:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:- -> R12:- -> R13:- -> R14:-
  Poison: R1:- -> R2:- -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:11 -> R12:12 -> R13:13 -> R14:14
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:6 -> R10:7 -> R11:- -> R12:- -> R13:- -> R14:-
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:7 -> R8:8 -> R9:9 -> R10:10 -> R11:- -> R12:- -> R13:- -> R14:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:10 -> R12:10 -> R13:10 -> R14:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:2 -> R10:4 -> R11:- -> R12:- -> R13:- -> R14:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4 -> R11:- -> R12:- -> R13:- -> R14:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:- -> R8:1 -> R9:1 -> R10:- -> R11:1 -> R12:- -> R13:- -> R14:1
  Weak[0]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:-
  Weak[1]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra, Sword of Stone, Yummy Cookie, The Abacus, Juzu Bracelet, Bowler Hat
Deck (27): Defend x5, Strike x4, Snakebite+ x2, Acrobatics+, Afterimage+, Backflip, Blade Dance+, Bouncing Flask, Bullet Time+, Dagger Throw, Deadly Poison, Fan of Knives, Flick-Flack, Footwork+, Neutralize+, Noxious Fumes+, Piercing Wail, Predator, Survivor
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Dexterity Potion
    +Dexterity(2)
  Powdered Demise -> Crusher[0]
    enemy_deltas: Crusher: +Demise(9)
  Afterimage+
    energy -1 | +Afterimage(1)
  Noxious Fumes+
    energy -1 | block +1 | +Noxious Fumes(3)
  Survivor
    energy -1 | block +10
  Strike
  turn_end

### Round 2
Intent: Crusher: Attack(4), Rocket: Attack(27)
  Neutralize+ -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4, +Weak(2)
  Bullet Time+
    energy -2 | block +1 | +No Draw(1)
  Predator -> Rocket[1]
    block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Rocket: hp -15
  Defend
    block +8
  Defend
    block +8
  turn_end
    -No Draw

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Backflip
    energy -1 | block +8
  Footwork+
    energy -1 | block +1 | Dexterity(2→5)
  Defend
    energy -1 | block +11
  turn_end

### Round 4
Intent: Crusher: Buff, Rocket: Attack(33)
  Snakebite+ -> Rocket[1]
    energy -2 | block +1 | enemy_deltas: Rocket: Poison(7→17)
  Defend
    energy -1 | block +8
  turn_end

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Acrobatics+
    energy -1
  Strike
  Bullet Time+
    energy -2 | block +1 | +No Draw(1)
  Defend
    block +8
  Defend
    block +8
  Bouncing Flask
    block +1 | enemy_deltas: Crusher: Poison(9→15); Rocket: Poison(19→22)
  Deadly Poison -> Crusher[0]
    block +1 | enemy_deltas: Crusher: Poison(15→20)
  Snakebite+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: Poison(20→30)
  Strike -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -4
  Blade Dance+
    block +1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust.
  Shiv -> Crusher[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: hp -3
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -3
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -3
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -3
  turn_end
    -No Draw

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  Strike -> Rocket[1]
    energy -1 | block +1 | enemy_deltas: Rocket: hp -6
  Neutralize+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: block -4, +Weak(2)
  Defend
    energy -1 | block +11
  Survivor
    energy -1 | block +14
  turn_end

### Round 7
Intent: Crusher: Attack(4), Rocket: Attack(30)
  Piercing Wail
    energy -1 | block +1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: Strength(2→-4), +Piercing Wail(6); Rocket: Strength(2→-4), +Piercing Wail(6)
  Defend
    energy -1 | block +11
  Dagger Throw -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -9
  Flick-Flack
  turn_end

### Round 8
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  Backflip
    energy -1 | block +11
  Neutralize+ -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4, +Weak(2)
  Predator -> Rocket[1]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Rocket: hp -15
  turn_end

### Round 9
Intent: Rocket: Attack(30)
  Defend
    energy -1 | block +11
  Defend
    energy -1 | block +11
  Defend
    energy -1 | block +11
  turn_end
## Combat Analytics: multi:Crusher+Rocket (WIN - 9 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 1 block
  Survivor "Gain 10 Block. Discard 1 card." -> 2 plays, 24 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg, 3 block
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 2 plays, 2 block
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 30 dmg, 2 block
  Defend "Gain 7 Block." -> 11 plays, 106 block
  Backflip "Gain 7 Block. Draw 2 cards." -> 2 plays, 19 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 1 block
  Snakebite+ "Retain. Apply 10 Poison." -> 2 plays, 2 block, +20 poison
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, 1 block, +9 poison
  Deadly Poison "Apply 5 Poison." -> 1 plays, 1 block, +5 poison
  Strike "Deal 4 damage." -> 2 plays, 10 dmg, 2 block
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 block, EXHAUST, generates 4 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 4 plays, 12 dmg, 4 block, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg

Active powers: Surrounded(1)

Token attribution (Shivs):
  Blade Dance+: 4 Shivs -> ~12 dmg

Poison stacks applied per card:
  Snakebite+: 20 stacks
  Bouncing Flask: 9 stacks
  Deadly Poison: 5 stacks

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Demise: R1:- -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:9 -> R7:9 -> R8:9 -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:30
  Poison[0]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:32 -> R7:34 -> R8:36 -> R9:-
  Poison[1]: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:19 -> R6:24 -> R7:26 -> R8:28 -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:1

[Selected: elite] Soul Nexus (F43, elite)
## Combat Replay: vs Soul Nexus (Floor 43, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese, Happy Flower, Spiked Gauntlets, Tough Bandages, Strike Dummy, Bag of Preparation, Eternal Feather
Deck (33): Defend x5, Strike x4, Cloak and Dagger+ x2, Dagger Throw x2, Leg Sweep x2, Accuracy, Adrenaline, Backstab, Blade Dance, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Leading Strike, Murder, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Soul Nexus HP=234/234

### Round 1
Agent plan (hypothesis): Saved energy for a big burst turn.
Agent plan (hypothesis): Energy is banked, prepare for a big turn next.
Intent: Soul Nexus: Attack(29)
  Prowess+
    energy -2 | +Strength(2) | +Dexterity(2)
  Accuracy
    energy -2 | +Accuracy(4)
  Backstab -> Soul Nexus[0]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Soul Nexus: hp -13
  Adrenaline
    energy +1 | exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust.
  Finesse
    block +6
  Dagger Throw -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -11
  Strike
  Survivor
    energy -1 | block +10
  Murder
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end

### Round 2
Agent plan (hypothesis): Used Ripple Basin to full block. Next turn we look to utilize banked energy.
Intent: Soul Nexus: Attack(18), DebuffStrong
  Noxious Fumes
    energy -2 | +Noxious Fumes(2)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end
    block +4

### Round 3
Intent: Soul Nexus: Attack(9x4=36)
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +13 | enemy_deltas: Soul Nexus: +Weak(2)
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +13 | enemy_deltas: Soul Nexus: Weak(2→4)
  Cloak and Dagger+
    energy -1 | block +8
  Shiv -> Soul Nexus[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Predator+ -> Soul Nexus[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Nexus: hp -33
  turn_end

### Round 4
Agent plan (hypothesis): Pen Nib will be triggered on the Strike. We banked a little extra energy thanks to Nunchaku triggering.
Intent: Soul Nexus: Attack(20), DebuffStrong
  Defend
    energy -1 | block +7
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(6)
  Cloak and Dagger+
    energy -1 | block +8
  Neutralize+ -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -4, Weak(3→5)
  Leading Strike -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -6
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Strike -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -16
  turn_end

### Round 5
Intent: Soul Nexus: Attack(6x4=24)
  Cloak and Dagger+
    energy -1 | block +8
  Shiv -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -7
  Shiv -> Soul Nexus[0]
    energy +1 | enemy_deltas: Soul Nexus: hp -7
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +13 | enemy_deltas: Soul Nexus: Weak(4→6)
  Poisoned Stab -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -6, Poison(4→7)
  Dagger Throw -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -8
  Defend
  Dagger Spray
    energy -1 | enemy_deltas: Soul Nexus: hp -8
  turn_end

### Round 6
Agent plan (hypothesis): Continue to play safe and let Poison/Shivs secure the kill.
Intent: Soul Nexus: Attack(20), DebuffStrong
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +13 | enemy_deltas: Soul Nexus: Weak(5→7)
  Defend
    energy -1 | block +7
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(6)
  Strike -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -8
  turn_end

### Round 7
Intent: Soul Nexus: Attack(6x4=24)
  Murder -> Soul Nexus[0]
    energy -3 | hp +1 | block -6 | -Strength | -Dexterity | -Accuracy | -Noxious Fumes | -Vulnerable | -Weak | enemy_deltas: Soul Nexus: DIED
## Combat Analytics: Soul Nexus (WIN - 7 rounds)

Cards played (with descriptions):
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity. Perfect Fit." -> 1 plays
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Backstab "Innate. Deal 13 damage. Exhaust." -> 1 plays, 13 dmg, EXHAUST
  Adrenaline "Gain 1 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Finesse "Gain 6 Block. Draw 1 card." -> 1 plays, 6 block
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 2 plays, 19 dmg
  Survivor "Gain 10 Block. Discard 1 card." -> 1 plays, 10 block
  Defend "Gain 7 Block." -> 6 plays, 42 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 13 Block." -> 4 plays, 52 block
  Cloak and Dagger+ "Gain 8 Block. Add 2 Shivs into your Hand." -> 3 plays, 24 block, generates 2 Shivs
  Shiv "Deal 7 damage. Exhaust." -> 11 plays, 77 dmg, EXHAUST
  Predator+ "Deal 33 damage. Next turn, draw 2 cards." -> 1 plays, 33 dmg
  Dodge and Roll "Gain 6 Block. Next turn, gain 6 Block." -> 2 plays, 12 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Leading Strike "Deal 6 damage. Add 2 Shivs into your Hand." -> 1 plays, 6 dmg, generates 2 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Strike "Deal 16 damage." -> 2 plays, 24 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg
  Murder "Deal 36 damage. Deals 1 additional damage for each card drawn this combat." -> 1 plays

Token attribution (Shivs):
  Cloak and Dagger+: 6 Shivs -> ~42 dmg
  Blade Dance: 3 Shivs -> ~21 dmg
  Leading Strike: 2 Shivs -> ~14 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:2 -> R4:3 -> R5:4 -> R6:8 -> R7:9
  Weak: R1:- -> R2:- -> R3:- -> R4:3 -> R5:4 -> R6:5 -> R7:6

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese, Happy Flower, Spiked Gauntlets, Tough Bandages, Strike Dummy, Bag of Preparation, Eternal Feather, Regal Pillow
Deck (34): Defend x5, Strike x3, Cloak and Dagger+ x2, Dagger Throw x2, Finesse x2, Leg Sweep x2, Accuracy+, Adrenaline, Adrenaline+, Backstab, Blade Dance, Dagger Spray, Dodge and Roll, Expertise+, Leading Strike, Murder, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Agent plan (hypothesis): We conserved energy with Ice Cream. Queen will apply Chains of Binding next turn. Focus all damage on Queen.
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Strength Potion
    +Strength(2)
  Energy Potion
    energy +2
  Backstab -> Queen[1]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Queen: hp -13
  Predator+ -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -44
  Poisoned Stab -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -8, +Poison(3)
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +11 | enemy_deltas: Torch Head Amalgam: +Weak(2)
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Dagger Throw -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -11
  Strike
  Dagger Spray
    energy -1 | enemy_deltas: Torch Head Amalgam: hp -12; Queen: hp -12
  Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -11
  Murder -> Queen[1]
    energy -3 | enemy_deltas: Queen: hp -13
  turn_end

### Round 2
Agent plan (hypothesis): We still have energy for whatever Finesse draws. Prioritize scaling or further draw.
Agent plan (hypothesis): Continue cycling and dumping damage into the Queen.
Agent plan (hypothesis): See what we draw
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Neutralize+ -> Queen[1]
    enemy_deltas: Queen: hp -6, +Weak(2)
  Leading Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -8
  Shiv -> Queen[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Queen: hp -6
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -6
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -12
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -6
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +11 | enemy_deltas: Torch Head Amalgam: Weak(1→3)
  Finesse
    block +4
  Adrenaline+
    energy +2 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  Expertise+
    energy -1
  Finesse
    block +4
  Prowess+
    energy -2 | Strength(2→4) | +Dexterity(2)
  Blade Dance
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  Shiv -> Queen[1]
    energy +1 | enemy_deltas: Queen: hp -8
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -8
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -8
  Dagger Throw -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -13
  Defend
  Adrenaline
    energy +1 | exhausted: Shiv*7 [0]: Deal 4 damage. Exhaust.
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(9x3=27), Queen: Buff, Defend
  Accuracy+
    energy -2 | +Accuracy(6)
  Defend
    energy -1 | block +5
  Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -9
  turn_end

### Round 4
Agent plan (hypothesis): Saved energy for a big draw turn next round.
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Cloak and Dagger+
    energy -1 | block +6
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +9 | enemy_deltas: Torch Head Amalgam: Weak(1→3)
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -10
  turn_end

### Round 5
Agent plan (hypothesis): Queen is very low on health. Save energy with Ice Cream.
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Dagger Throw -> Queen[1]
    energy -1 | enemy_deltas: Queen: block -9
  Strike
  Murder -> Queen[1]
    energy -3 | enemy_deltas: Queen: hp -62, block -11
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +10
  turn_end

### Round 6
Agent plan (hypothesis): See what we draw and use remaining 4 energy optimally.
Agent plan (hypothesis): Survival is the priority. The Queen is at 123 HP. Need a high damage turn soon or scaling will finish us.
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Predator+ -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: block -18
  Dagger Throw -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -7, block -2
  Strike
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Defend
    energy -1 | block +5
  turn_end

### Round 7
Agent plan (hypothesis): Queen dies next turn. Maintain offensive pressure.
Agent plan (hypothesis): Queen will die next turn. Survive until then.
Agent plan (hypothesis): Finish the Queen next turn.
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  Dagger Spray
    energy -1 | enemy_deltas: Torch Head Amalgam: hp -12; Queen: block -12
  Leading Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: block -7
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -9, block -1
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Poisoned Stab -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -7, +Poison(3)
  Expertise+
    energy -1
  Dagger Throw -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -19
  Strike
  Finesse
    block +4
  Storm of Steel
    energy -1 | block +15
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    energy +1 | enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -10
  turn_end

### Round 8
Intent: Torch Head Amalgam: Attack(28), Queen: Buff, Defend
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -10
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -10
  Strike -> Queen[1]
    energy -1 | hp +1 | block -6 | -Strength | -Chains of Binding | -Dexterity | -Frail | -Weak | -Vulnerable | -Accuracy | enemy_deltas: Torch Head Amalgam: DIED; Queen: DIED
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 8 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 13 damage. Exhaust." -> 1 plays, 13 dmg, EXHAUST
  Predator+ "Deal 44 damage. Next turn, draw 2 cards." -> 2 plays, 44 dmg
  Poisoned Stab "Deal 8 damage. Apply 3 Poison." -> 2 plays, 15 dmg, +6 poison
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 3 plays, 31 block
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 2 plays, 8 block
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 5 plays, 50 dmg
  Dagger Spray "Deal 6 damage to ALL enemies twice." -> 2 plays, 36 dmg
  Strike "Deal 11 damage." -> 3 plays, 20 dmg
  Murder "Deal 13 damage. Deals 1 additional damage for each card drawn this combat." -> 2 plays, 75 dmg
  Neutralize+ "Deal 6 damage. Apply 2 Weak." -> 1 plays, 6 dmg
  Leading Strike "Deal 8 damage. Add 2 Shivs into your Hand. Bound" -> 2 plays, 8 dmg, generates 2 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 20 plays, 143 dmg, EXHAUST
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand. Bound" -> 4 plays, 24 block, generates 2 Shivs
  Finesse "Gain 4 Block. Draw 1 card." -> 3 plays, 12 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Expertise+ "Draw cards until you have 7 in your Hand." -> 2 plays
  Prowess+ "Gain 2 Strength. Gain 2 Dexterity. Perfect Fit." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Adrenaline "Gain 1 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Accuracy+ "Shivs deal 6 additional damage. Bound" -> 1 plays
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Survivor "Gain 7 Block. Discard 1 card." -> 1 plays, 10 block
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, 15 block, generates 1 Shivs

Token attribution (Shivs):
  Cloak and Dagger+: 8 Shivs -> ~57 dmg
  Leading Strike: 4 Shivs -> ~29 dmg
  other: 4 Shivs -> ~29 dmg
  Blade Dance: 3 Shivs -> ~21 dmg
  Storm of Steel: 1 Shivs -> ~7 dmg

Poison stacks applied per card:
  Poisoned Stab: 6 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1
  Poison: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:5
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:2 -> R6:1 -> R7:- -> R8:-
  Weak[0]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Weak[1]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Candelabra, Sword of Stone, Yummy Cookie, The Abacus, Juzu Bracelet, Bowler Hat, Sai, Gorget, Fragrant Mushroom, Potion Belt, Kunai
Deck (31): Defend x4, Noxious Fumes x2, Piercing Wail x2, Strike+ x2, Accelerant, Acrobatics+, Afterimage+, Backflip, Blade Dance+, Bouncing Flask, Bullet Time+, Calculated Gamble+, Dagger Throw, Deadly Poison+, Defend+, Fan of Knives, Flick-Flack+, Footwork+, Malaise, Neutralize+, Predator, Snakebite, Snakebite+, Survivor, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Afterimage+
    energy -1 | +Afterimage(1)
  Neutralize+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -4, +Weak(2)
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Backflip
    energy -1 | block +6
  turn_end
    block +4
  Acrobatics+
  Predator

### Round 2
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Noxious Fumes
    energy -1 | block +1 | +Noxious Fumes(2)
  Accelerant
    energy -1 | block +1 | +Accelerant(1)
  Acrobatics+
    energy -1
  Flick-Flack+
  Bullet Time+
    energy -2 | block +1 | +No Draw(1)
  Footwork+
    block +1 | +Dexterity(3)
  Bouncing Flask
    block +1 | enemy_deltas: Torch Head Amalgam: +Poison(6); Queen: +Poison(3)
  Predator -> Queen[1]
    block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -15
  Defend
    block +9
  turn_end
    block +3
  Malaise
  Defend

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Noxious Fumes
    energy -1 | block +1 | Noxious Fumes(2→4)
  Piercing Wail
    energy -1 | block +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Torch Head Amalgam: +Strength(-6), +Piercing Wail(6); Queen: +Strength(-6), +Piercing Wail(6)
  Deadly Poison+ -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: Poison(3→10)
  turn_end
    block +2
  Malaise
  Piercing Wail

### Round 4
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  Defend+
    energy -1 | block +9
  Snakebite+ -> Queen[1]
    energy -2 | block +1 | enemy_deltas: Queen: Poison(12→22)
  Calculated Gamble+
    block +7 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust.
  Neutralize+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, +Weak(2)
  turn_end
    block +1
  Predator
  Piercing Wail

### Round 5
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Snakebite+ -> Queen[1]
    energy -2 | block +1 | enemy_deltas: Queen: Poison(24→34)
  Survivor
    energy -1 | block +8
  Predator
  turn_end
  Piercing Wail
  Malaise

### Round 6
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  Piercing Wail
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: Strength(3→-3), +Piercing Wail(6); Queen: +Strength(-6), +Piercing Wail(6)
  Blade Dance+
    energy -1 | block +1 | exhausted: Piercing Wail*2 [1]: ALL enemies lose 6 Strength this turn. Exhaust.
  Shiv -> Torch Head Amalgam[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    block +1 | Dexterity(3→4) | enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3
  Malaise -> Torch Head Amalgam[0]
    energy -1 | block +1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: Strength(-3→-4), +Weak(1)
  turn_end
  Bouncing Flask
  Fan of Knives

### Round 7
Intent: Torch Head Amalgam: Attack(25), Queen: Buff, Defend
  Acrobatics+
    energy -1 | block +6
  Flick-Flack+
  Bullet Time+
    energy -2 | block +1 | +No Draw(1)
  Bouncing Flask
    block +1 | enemy_deltas: Torch Head Amalgam: Poison(14→20); Queen: Poison(38→41)
  Fan of Knives
    block +1 | +Fan of Knives(1)
  Shiv
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: block -3
  Shiv
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: block -3
  Shiv
    block +1 | Dexterity(4→5) | enemy_deltas: Torch Head Amalgam: hp -3; Queen: block -3
  Shiv
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: block -3
  Snakebite -> Queen[1]
    block +1 | enemy_deltas: Queen: Poison(41→48)
  Snakebite+ -> Queen[1]
    block +1 | enemy_deltas: Queen: Poison(48→58)
  Deadly Poison+ -> Queen[1]
    block +1 | enemy_deltas: Queen: Poison(58→65)
  Defend+
    block +10
  Dagger Throw -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -6
  turn_end
    -No Draw

### Round 8
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  Neutralize+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, +Weak(2)
  Backflip
    energy -1 | block +8
  Defend
    energy -1 | block +8
  turn_end
  Survivor
  Predator
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 8 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 10 dmg, 3 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 14 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 2 plays, 2 block
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 1 block
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays, 6 block
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 2 plays, 2 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 1 block
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 2 plays, 2 block, +18 poison
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg, 1 block
  Defend "Gain 8 Block. Bound" -> 2 plays, 17 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, 2 block, EXHAUST
  Deadly Poison+ "Apply 7 Poison." -> 2 plays, 2 block, +14 poison
  Defend+ "Gain 8 Block." -> 2 plays, 19 block
  Snakebite+ "Retain. Apply 10 Poison." -> 3 plays, 3 block, +30 poison
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 7 block, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 block, EXHAUST, generates 4 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 8 plays, 24 dmg, 8 block, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, 1 block, EXHAUST
  Fan of Knives "Shivs now hit ALL enemies. Add 4 Shivs into your Hand." -> 1 plays, 1 block, generates 4 Shivs
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, 1 block, +7 poison
  Dagger Throw "Deal 6 damage. Draw 1 card. Discard 1 card." -> 1 plays, 6 dmg, 1 block

Active powers: Plating(4)

Token attribution (Shivs):
  Blade Dance+: 4 Shivs -> ~12 dmg
  Fan of Knives: 4 Shivs -> ~12 dmg

Poison stacks applied per card:
  Snakebite+: 30 stacks
  Bouncing Flask: 18 stacks
  Deadly Poison+: 14 stacks
  Snakebite: 7 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1
  Poison[0]: R1:- -> R2:- -> R3:6 -> R4:8 -> R5:10 -> R6:12 -> R7:14 -> R8:22
  Poison[1]: R1:- -> R2:- -> R3:3 -> R4:12 -> R5:24 -> R6:36 -> R7:38 -> R8:67
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:3 -> R8:4
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:-

## Triggered Skills This Run
- The Silent - Deckbuilding Principles: F1(), F2(), F3(), F5(), F6(), F8(), F12(), F14(), F15(), F15(), F17(), F19(), F20(), F21(), F22(), F22(), F22(), F23(), F23(), F24(), F25(), F28(), F30(), F31(), F33(), F33(), F35(), F39(), F40(), F42(), F43(), F45(), F46(), F46()
- The Silent - Path Selection: F1(), F1(), F3(), F6(), F9(), F10(), F13(), F13(), F18(), F18(), F19(), F28(), F28(), F29(), F34(), F34(), F41(), F41(), F45()
- The Silent - Rest & Event Decisions: F7(), F9(), F11(), F13(), F16(), F29(), F32(), F44(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.