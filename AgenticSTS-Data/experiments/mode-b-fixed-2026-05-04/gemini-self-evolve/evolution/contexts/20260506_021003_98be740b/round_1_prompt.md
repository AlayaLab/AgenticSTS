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
Result: DEFEAT at Floor 22 (fitness: 79.4)
Combats won: 10/10
Run duration: 3710.8s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: leverage massive early gold (432) at shops to buy run-defining relics, strong attacks, and potions to snowball Act 1; prioritize finding discard synergies or extra card draw to offset the permanent Greed curse.
- [map] Foundation deck: leverage massive early gold at shops to buy run-defining relics and strong attacks to snowball Act 1; prioritize finding discard synergies or extra card draw to offset the permanent Greed curse.
### F2
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; use early shops to convert our massive gold pool into premium damage and card removals. Take cheap draw or high-impact damage, skip narrow synergy pieces.
### F3
- [hand_select] Acrobatics draw resulted in 9 cards in hand. Discarding the curse is the most efficient way to manage hand space and draw quality.
- [card_reward] Foundation phase leaning poison: looking for cheap frontload damage to survive Act 1 elites, but committed to poison scaling for bosses. Prioritize damage at shops.
### F4
- [card_reward] Foundation plan: stall with efficient block from discard synergies while Noxious Fumes kills enemies. Need more upfront damage for early Elites and more poison scaling; avoid basic attacks.
### F5
- [hand_select] Prioritizing Sly card discard to maximize energy efficiency and block.
- [hand_select] Acrobatics triggered a discard choice; Untouchable is the optimal target to save energy and gain block.
- [card_reward] Foundation plan: Use Noxious Fumes for scaling damage while relying on Acrobatics and Survivor to trigger Sly cards like Ricochet and Untouchable for efficient upfront damage and block. Need more frontload and basic card removals.
- [map] Foundation deck: leverage massive early gold (473) at future shops to buy run-defining relics while prioritizing early standard monster encounters to draft essential frontloaded damage and block before the first Elite.
### F6
- [card_reward] Committed to Sly / Poison hybrid. Use discard outlets (Acrobatics, Dagger Throw, Survivor) to trigger Sly cards (Ricochet, Untouchable) for free value while Noxious Fumes scales. We need more efficient discard outlets and block. Avoid bloated hands; prioritize campfires for healing since HP is critical.
- [map] Foundation deck with high gold: survive until the Floor 8 shop to buy power and relics that offset the Greed curse. Prioritize high-impact frontloaded cards and discard outlets to handle the curse while moving toward a defensive engine.
### F7
- [rest_site] Foundation deck with high gold: survive until the Floor 9 shop to buy power and relics that offset the Greed curse. Prioritize high-impact frontloaded cards and discard outlets to handle the curse while moving toward a defensive engine.
### F8
- [event] Foundation deck with high gold: going into the Floor 9 shop, use our 483 gold to buy run-defining relics, potion support for the upcoming Elite, and strong card removal/additions. Focus on mitigating the Greed curse and setting up a solid engine.
- [card_select] Committed poison/sly plan: use discard synergies for immediate block/draw while Noxious Fumes scales, relying on Footwork to survive long encounters. Look for more card draw, remove Strikes, and avoid adding low-impact attacks.
- [map] Foundation deck with critical gold reserves: use this shop to pivot into a committed engine by purchasing scaling and high-impact defensive relics. Prioritize removing the Greed curse or finding discard outlets to mitigate its impact. The goal is to stabilize health and secure a clear win condition before the Act 1 boss.
### F9
- [card_select] Committed poison/defense plan: stall with Footwork, Piercing Wail, and block while Noxious Fumes scales. Use Sly triggers (Survivor, Acrobatics) to play Untouchable/Ricochet for free. Needs more poison application/acceleration or block scaling; skip low-impact attacks.
### F11
- [card_reward] Foundation phase, shifting towards control/poison. Retain key defensive cards (Piercing Wail, Malaise) for big hits, use discard synergy (Acrobatics/Survivor + Sly) for tempo, and let Noxious Fumes scale damage. Need more focused damage scaling (poison) and deck thinning.
- [map] Foundation deck with Meat on the Bone sustain: take calculated risks in Elites to trigger healing and find scaling pieces. Prioritize high-impact frontloaded damage and discard outlets to mitigate the Greed curse while transitioning toward a defensive engine.
### F12
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [hand_select] Greed is a dead draw; discarding it thins the current hand to allow for better plays with remaining energy.
- [hand_select] Retaining Sly cards increases the value of future discard effects.
- [hand_select] Utilizing Sly cards is key to maximizing energy efficiency and frontloading damage/block.
- [card_reward] Committed poison/discard plan: use Fumes to scale damage while cycling for key defensive powers (Footwork, Afterimage) and utilizing Pocketwatch for massive draw. Keep the deck focused on mitigation and draw, avoiding standard attacks.
### F13
- [rest_site] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.
### F14
- [event] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.
- [card_select] Committed poison plan: rely on Noxious Fumes for scaling damage while maximizing defense with Footwork, Afterimage, and block cards. Pace turns to trigger Pocketwatch draw. Continue removing Strikes and avoid low-impact attacks.
- [map] Foundation deck with Meat on the Bone sustain: prioritize deck thinning to remove Greed and finding defensive scaling or discard outlets to manage the curse until removed. Avoid taking unnecessary chip damage in hallways while looking for a finisher card for the Act 1 boss.
### F16
- [rest_site] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.
### F17
- [hand_select] Prioritizing defensive consistency and poison scaling over physical damage.
- [hand_select] Retaining Piercing Wail allows for a flexible defensive response to the Matriarch's biggest attacks.
- [hand_select] Pocketwatch triggers on 3 or fewer cards played. I've played 1 (Acrobatics). I will end turn after this selection to draw 3 extra cards next turn.
- [hand_select] Utilizing Sly to trigger Afterimage for free block while scaling poison.
- [card_reward] Committed to a defensive poison and Sly engine. Retain Sly cards to discard with Tools of the Trade or Acrobatics for free plays. Stall with Footwork, Afterimage, and Piercing Wail while Noxious Fumes handles scaling damage. Prioritize Strike removals and power upgrades.
### F18
- [event] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Use Pael's Eye on weak hands to exhaust junk (like Greed) and take a fresh turn. Needs more upgraded defense and reliable discard outlets; avoid slow attacks.
- [map] Foundation deck with Meat on the Bone sustain: prioritize drafting defensive scaling and discard outlets to manage Greed while looking for a reliable poison or shiv engine to transition into a committed scaling build.
### F19
- [card_select] Committed poison/defense plan: survive and stall using high-value block, Footwork, and damage mitigation while Noxious Fumes slowly kills everything. Needs upgraded Noxious Fumes or Catalyst for faster scaling; avoid low-impact attacks.
- [hand_select] Utilizing Sly cards is a key efficiency gain for this deck's energy management.
- [hand_select] Executing the 'Sly' mechanic to maximize action economy and damage output during this high-threat turn.
- [card_reward] Committed poison/defense plan: Noxious Fumes is our main scaling, heavily accelerated by Bubble Bubble. Retain Bubble Bubble with Well-Laid Plans until Poison is applied. Play Footwork, Afterimage, and block heavily while poison ticks down enemies. Use Pocketwatch by playing 3 or fewer high-impact cards when possible. Remove Strikes at shops.
- [map] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.
### F20
- [event] Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Use Pael's Eye on weak hands to exhaust junk and take a fresh turn. Needs upgraded defense and discard outlets; avoid slow attacks.
### F21
- [card_reward] Committed to defensive stall with poison (Fumes, Bubble Bubble) and Pocketwatch card advantage. Play 3 or fewer impactful cards per turn to maintain massive draw. Avoid multi-play cards like Shivs that disrupt Pocketwatch.

### Combat Decision Digest (11 combats)
F2 [monster] Seapunk (5R, HP 56->56, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=0
  R2[Seapunk: Atk(2x4=8)]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R3[Seapunk: Buff, Defend]: Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=18 taken=0
  R4[Seapunk: Atk(12)]: Neutralize(1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(2dmg) | dealt=2 taken=0
  R5[Seapunk: Atk(3x4=12)]: Neutralize | dealt=0 taken=0

F3 [monster] Sludge Spinner (5R, HP 56->54, loss=2, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Acrobatics->Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=1
  R2[Sludge Spinner: Atk(11)]: Survivor(+8blk)->Defend(+5blk)->Strike(4dmg) | dealt=4 taken=0
  R3[Sludge Spinner: Atk(8), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R4[Sludge Spinner: Atk(11)]: Defend(+5blk)->Defend(+5blk)->Strike(4dmg) | dealt=4 taken=1
  R5[Sludge Spinner: Atk(6), Buff]: Strike | dealt=0 taken=0

F4 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 54->46, loss=8, WIN)
  R1[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Neutralize->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Noxious Fumes(power:+Noxious Fumes(2))->Strike->Strike(6dmg) | dealt=6 taken=8
  R3[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Acrobatics->Strike(6dmg)->Survivor(+6blk) | dealt=6 taken=0
  R4[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike(6dmg)->Strike(1+Strength(4))->Neutralize(3dmg,1+Weak(1))->Strike(6dmg) | dealt=15 taken=0
  R5[Corpse Slug: Atk(7x2=14)]: Strike(power:-Noxious Fumes,power:-Frail) | dealt=0 taken=0

F5 [monster] multi:Calcified Cultist+Damp Cultist (9R, HP 46->25, loss=21, WIN)
  R1[Calcified Cultist: Buff+Damp Cultist: Buff]: Neutralize(3dmg,1+Weak(1))->Acrobatics->Untouchable(6dmg)->Strike(6dmg)->Strike | dealt=15 taken=0
  R2[Calcified Cultist: Atk(9)+Damp Cultist: Atk(1)]: Noxious Fumes(power:+Noxious Fumes(2))->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Calcified Cultist: Atk(11)+Damp Cultist: Atk(6)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=9 taken=4
  R4[Calcified Cultist: Atk(13)+Damp Cultist: Atk(11)]: Strike(6dmg)->Strike(6dmg)->Strike | dealt=17 taken=11
  R5[Damp Cultist: Atk(16)]: Survivor(+8blk)->Untouchable(+5blk)->Defend(+5blk)->Defend | dealt=0 taken=0
  R6[Damp Cultist: Atk(21)]: Acrobatics->Untouchable(+5blk)->Defend(+5blk)->Defend | dealt=0 taken=5
  R7[Damp Cultist: Atk(26)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=9 taken=0
  R8[Damp Cultist: Atk(21)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=3 taken=1
  R9[Damp Cultist: Atk(25)]: Acrobatics->Untouchable(6dmg)->Strike(power:-Noxious Fumes)->Strike | dealt=6 taken=0

F6 [monster] Gremlin Merc (9R, HP 25->6, loss=19, WIN)
  R1[Gremlin Merc: Atk(7x2=14)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Gremlin Merc: Atk(6x2=12), Debuff]: Defend(+5blk)->Ricochet(12dmg) | dealt=12 taken=7
  R3[Gremlin Merc: Atk(8), Buff]: Neutralize(2dmg,1+Weak(1))->Survivor(+8blk)->Untouchable | dealt=2 taken=0
  R4[Gremlin Merc: Atk(9x2=18)]: Neutralize(2dmg,1+Weak(1))->Noxious Fumes(power:+Noxious Fumes(2))->Ricochet(8dmg) | dealt=10 taken=12
  R5[Gremlin Merc: Atk(8x2=16), Debuff]: Defend(+5blk)->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R6[Gremlin Merc: Atk(10), Buff]: Acrobatics->Untouchable(+5blk)->Defend(2dmg,1+Weak(1))->Neutralize(4dmg)->Strike | dealt=6 taken=0
  R7[Gremlin Merc: Atk(11x2=22)]: Ricochet(8dmg)->Strike(4dmg) | dealt=12 taken=0
  R8[Sneaky Gremlin: Stun+Fat Gremlin: Stun]: Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=18 taken=0
  R9[Sneaky Gremlin: Atk(9)]: Strike(power:-Noxious Fumes) | dealt=0 taken=0

F11 [monster] Living Fog (8R, HP 27->33, loss=0, WIN)
  R1[Living Fog: Atk(8), CardDebuff]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=2
  R2[Living Fog: Atk(5), Summon]: Dagger Throw(9dmg)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R3[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Defend(+5blk)->Pinpoint | dealt=7 taken=3
  R4[Living Fog: Atk(5), Summon]: Footwork(power:+Dexterity(2))->Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Survivor(+10blk) | dealt=9 taken=0
  R5[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Dagger Throw->Untouchable(15dmg)->Pinpoint | dealt=15 taken=0
  R6[Living Fog: Atk(5), Summon]: Defend(+7blk)->Ricochet(12dmg) | dealt=12 taken=0
  R7[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Strike->Defend(+7blk)->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=7 taken=1
  R8[Living Fog: Atk(5), Summon]: Neutralize(5dmg,1+Weak(1))->Pinpoint(power:-Smoggy,power:-Dexterity,power:-Strength,power:-Noxious Fumes) | dealt=5 taken=0

F12 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (8R, HP 33->27, loss=6, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Footwork(power:+Dexterity(2))->Defend(+7blk)->Fan of Knives(power:+Fan of Knives(1))->Shiv(4dmg,exhaust:1)->Shiv->Shiv(2dmg)->Shiv(4dmg)->Dagger Throw->Malaise(exhaust:1) | dealt=10 taken=8
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Neutralize->Strike->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=3
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)]: Piercing Wail(2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Untouchable(+8blk) | dealt=0 taken=0
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(3x3=9)]: Acrobatics->Untouchable(+9blk)->Defend(power:+Noxious Fumes(2))->Noxious Fumes->Pinpoint | dealt=0 taken=0
  R5[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff]: Defend(+9blk)->Well-Laid Plans(power:+Well-Laid Plans(1))->Strike | dealt=0 taken=7
  R6[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Atk(9)]: Neutralize->Defend(+9blk)->Defend(+9blk)->Survivor(+12blk)->Ricochet | dealt=0 taken=0
  R7[Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(11)]: Defend(+9blk)->Defend(+9blk)->Defend(+9blk) | dealt=0 taken=0
  R8[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(5x3=15)]: Acrobatics->Ricochet->Strike->Neutralize(+12blk)->Survivor | dealt=0 taken=0

F17 [boss] Lagavulin Matriarch (19R, HP 69->52, loss=17, WIN)
  R1[Lagavulin Matriarch: Sleep]: Footwork(power:+Dexterity(2)) | dealt=0 taken=0
  R2[Lagavulin Matriarch: Sleep]: Footwork(power:Dexterity(2→4))->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=0 taken=0
  R3[Lagavulin Matriarch: Sleep]: Noxious Fumes(power:+Noxious Fumes(2))->Afterimage(power:+Afterimage(1)) | dealt=0 taken=0
  R4[Lagavulin Matriarch: Atk(19)]: Neutralize(3dmg,+1blk,1+Weak(1))->Defend(+10blk)->Defend(+10blk)->Acrobatics->Untouchable(15dmg,+1blk)->Pinpoint | dealt=18 taken=0
  R5[Lagavulin Matriarch: Atk(9x2=18)]: Cloak and Dagger(+11blk)->Defend(+10blk)->Strike(6dmg,+1blk) | dealt=6 taken=0
  R6[Lagavulin Matriarch: Atk(12), Defend]: Survivor(+12blk)->Ricochet(9dmg,+3blk,2+Strength(-2),+Weak(2),exhaust:1)->Malaise | dealt=9 taken=0
  R7[Lagavulin Matriarch: Debuff, Buff]: Neutralize(+1blk,1Weak(1→2))->Shiv(+1blk,exhaust:1)->Dagger Throw(4dmg)->Untouchable->Acrobatics(+11blk)->Cloak and Dagger(4dmg,+1blk)->Shiv | dealt=4 taken=0
  R8[Lagavulin Matriarch: Atk(14)]: Neutralize(1dmg,+1blk,1Weak(1→2))->Defend(+8blk)->Survivor(+10blk) | dealt=1 taken=0
  R9[Lagavulin Matriarch: Atk(6x2=12)]: Dagger Throw(7dmg)->Untouchable(+10blk)->Survivor | dealt=0 taken=0
  R10[Lagavulin Matriarch: Atk(12), Defend]: Defend(+8blk)->Defend(+8blk)->Strike(4dmg,+1blk) | dealt=4 taken=0
  R11[Lagavulin Matriarch: Debuff, Buff]: Cloak and Dagger(+9blk)->Pinpoint(1dmg,+1blk)->Shiv(2dmg,+1blk) | dealt=3 taken=0
  R12[Lagavulin Matriarch: Atk(21)]: Neutralize(+1blk,1+Weak(1))->Piercing Wail(+1blk,2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Survivor(+8blk) | dealt=0 taken=0
  R13[Lagavulin Matriarch: Atk(11x2=22)]: Neutralize(+1blk,1+Weak(1))->Dagger Throw(5dmg)->Untouchable(+8blk)->Survivor(+6blk)->Defend | dealt=0 taken=0
  R14[Lagavulin Matriarch: Atk(14), Defend]: Defend(+6blk)->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0
  R15[Lagavulin Matriarch: Debuff, Buff]: Acrobatics->Ricochet | dealt=0 taken=0
  R16[Lagavulin Matriarch: Atk(23)]: Dagger Throw(3dmg)->Untouchable(+5blk)->Cloak and Dagger(+1blk)->Shiv | dealt=0 taken=11
  R17[Lagavulin Matriarch: Atk(13x2=26)]: Neutralize(+1blk,1+Weak(1))->Acrobatics->Ricochet(+6blk)->Survivor(+4blk)->Defend | dealt=0 taken=4
  R18[Lagavulin Matriarch: Atk(16), Defend]: Neutralize(+1blk,1+Weak(1))->Defend(+4blk)->Defend(+4blk)->Pinpoint(9dmg,+1blk) | dealt=9 taken=2
  R19[Lagavulin Matriarch: Debuff, Buff]: none | dealt=0 taken=0

F19 [monster] multi:Bowlbug (Nectar)+Bowlbug (Rock) (7R, HP 66->46, loss=20, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(3)]: Noxious Fumes(power:+Noxious Fumes(2))->Acrobatics->Ricochet(+5blk)->Defend | dealt=0 taken=13
  R2[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Buff]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Cloak and Dagger(+6blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Bowlbug (Rock): Stun+Bowlbug (Nectar): Atk(18)]: Neutralize(3dmg,1+Weak(1))->Survivor(+8blk)->Defend(+5blk) | dealt=3 taken=0
  R4[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(18)]: Footwork(power:+Dexterity(2))->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=19
  R5[Bowlbug (Rock): Atk(15)+Bowlbug (Nectar): Atk(18)]: Dagger Throw(9dmg)->Ricochet(+8blk)->Cloak and Dagger(exhaust:1)->Shiv(+10blk)->Survivor | dealt=1 taken=0
  R6[Bowlbug (Rock): Stun]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg) | dealt=15 taken=0
  R7[Bowlbug (Rock): Atk(15)]: Shiv(power:-Noxious Fumes,power:-Dexterity) | dealt=0 taken=0

F21 [monster] Thieving Hopper (5R, HP 46->46, loss=0, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Neutralize(3dmg,1+Weak(1))->Footwork(power:+Dexterity(2))->Cloak and Dagger(+8blk)->Shiv(4dmg,exhaust:1)->Defend(+7blk) | dealt=7 taken=0
  R2[Thieving Hopper: Buff]: Strike(6dmg)->Malaise(2+Strength(-2),+Weak(2),exhaust:1) | dealt=6 taken=0
  R3[Thieving Hopper: Atk(14)]: Piercing Wail(2Strength(-2→-8),+Piercing Wail(6),exhaust:1)->Survivor(+10blk)->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=0 taken=0
  R4[Thieving Hopper: Atk(12)]: Afterimage(power:+Afterimage(1))->Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Survivor(+10blk) | dealt=0 taken=0
  R5[Thieving Hopper: Escape]: Acrobatics->Ricochet | dealt=0 taken=0

F22 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (9R, HP 46->0, loss=46, LOSS)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Neutralize(3dmg,1+Weak(1))->Acrobatics->Untouchable(+5blk)->Defend | dealt=3 taken=0
  R2[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Survivor(+8blk)->Strike(4dmg)->Strike(4dmg) | dealt=8 taken=0
  R3[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Atk(16), Buff]: Footwork(power:+Dexterity(2))->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=10
  R5[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Atk(18), Buff]: Noxious Fumes(power:+Noxious Fumes(2))->Cloak and Dagger(+8blk)->Survivor(+10blk) | dealt=0 taken=15
  R6[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Atk(20), Buff]: Neutralize(2dmg,1+Weak(1))->Acrobatics->Untouchable(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),2Strength(4→-2),+Piercing Wail(6),exhaust:1)->Piercing Wail | dealt=2 taken=2
  R7[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Atk(22), Buff]: Cloak and Dagger(+8blk)->Defend(+7blk)->Defend(+7blk)->Pinpoint(15dmg)->Shiv(4dmg,exhaust:1) | dealt=19 taken=15
  R8[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Atk(24), Buff]: none | dealt=0 taken=0
  R9[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Atk(24), Buff]: Neutralize(2dmg,1+Weak(1))->Acrobatics->Untouchable(2Strength(8→6),Weak(1→3),exhaust:1)->Malaise | dealt=2 taken=0

### Non-combat Decisions (92 decisions)
F1 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=deck_building,routing) | source=llm
  HP 56->56 | Gold 99->432 | Deck 13->14
  deck_change: added Greed
  reasoning: Cursed Pearl offers 333 gold, which is a massive economic advantage on Floor 1. While the Greed curse is Eternal and cannot be removed, having 432 gold total will allow us to heavily leverage early shops for key relics or cards to snowball the run. Silent's starting relic (Ring of the Snake) and Survivor help mitigate the curse early on.
  strategic_note: Foundation deck: leverage massive early gold (432) at shops to buy run-defining relics, strong attacks, and potions to snowball Act 1; prioritize finding discard synergies or extra card draw to offset the permanent Greed curse.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 432->432 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=2) | source=llm
  HP 56->56 | Gold 432->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to start a chain of monster encounters. With 432 gold and a permanent Greed curse, I need to draft foundational cards immediately to handle the incoming difficulty and eventually leverage the gold at a future shop.
  strategic_note: Foundation deck: leverage massive early gold at shops to buy run-defining relics and strong attacks to snowball Act 1; prioritize finding discard synergies or extra card draw to offset the permanent Greed curse.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 432->439 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 439->439 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 56->56 | Gold 439->439 | Deck 14->15
  deck_change: picked Acrobatics
  reasoning: With 439 gold from Cursed Pearl, we can afford to skip low-impact attacks like Slice and buy premium damage or relics at an early shop. Acrobatics is a highly valuable Uncommon that provides essential late-game cycling and immediately helps us draw past the two dead cards currently in our deck (Greed and Ascender's Bane).
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; use early shops to convert our massive gold pool into premium damage and card removals. Take cheap draw or high-impact damage, skip narrow synergy pieces.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 439->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 439->450 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 450->450 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 450->450 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 54->54 | Gold 450->450 | Deck 15->16
  deck_change: picked Noxious Fumes
  reasoning: Noxious Fumes is a premium uncommon power that provides excellent scaling damage, especially against the Lagavulin Matriarch Act Boss, who gives us 3 free turns to set it up before she wakes. We have 450 gold to buy immediate frontload damage at an upcoming shop.
  strategic_note: Foundation phase leaning poison: looking for cheap frontload damage to survive Act 1 elites, but committed to poison scaling for bosses. Prioritize damage at shops.

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 450->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 450->465 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 465->465 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Beetle Juice

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 465->465 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 46->46 | Gold 465->465 | Deck 16->17
  deck_change: picked Untouchable
  reasoning: Untouchable synergizes perfectly with our Acrobatics and Survivor, providing energy-free block when discarded. This gives us the highly efficient mitigation needed to stall while Noxious Fumes scales up our damage.
  strategic_note: Foundation plan: stall with efficient block from discard synergies while Noxious Fumes kills enemies. Need more upfront damage for early Elites and more poison scaling; avoid basic attacks.

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 465->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 25->25 | Gold 465->473 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 25->25 | Gold 473->473 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 25->25 | Gold 473->473 | Deck 17->18
  deck_change: picked Ricochet
  reasoning: We desperately need upfront damage to survive Act 1 elites and hallways. Ricochet synergizes perfectly with our existing Acrobatics and Survivor, allowing us to deal 12 damage for 0 energy while cycling or blocking.
  strategic_note: Foundation plan: Use Noxious Fumes for scaling damage while relying on Acrobatics and Survivor to trigger Sly cards like Ricochet and Untouchable for efficient upfront damage and block. Need more frontload and basic card removals.

F5 [map] choose_map_node (option_index=1) | source=llm
  HP 25->25 | Gold 473->0 | Deck 18->18
  deck_change: no deck change
  reasoning: I need to follow the route guide and 'Expert Knowledge' to prioritize monster encounters early in Act 1. This builds the foundational card pool needed for the deck to function. At 25 HP, I am vulnerable, but a Rest Site follows this fight, providing a safety net. The Monster node (index 1) is preferred over the Unknown node (index 0) to secure a card reward and start building momentum towards an elite-capable deck.
  strategic_note: Foundation deck: leverage massive early gold (473) at future shops to buy run-defining relics while prioritizing early standard monster encounters to draft essential frontloaded damage and block before the first Elite.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 6->6 | Gold 353->363 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 6->6 | Gold 363->483 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 120 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 6->6 | Gold 483->483 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 6->6 | Gold 483->483 | Deck 18->19
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides a crucial 1-cost discard outlet to reliably trigger our Sly cards (Ricochet, Untouchable) while cycling the deck and providing frontload damage.
  strategic_note: Committed to Sly / Poison hybrid. Use discard outlets (Acrobatics, Dagger Throw, Survivor) to trigger Sly cards (Ricochet, Untouchable) for free value while Noxious Fumes scales. We need more efficient discard outlets and block. Avoid bloated hands; prioritize campfires for healing since HP is critical.

F6 [map] choose_map_node (option_index=1) | source=llm
  HP 6->6 | Gold 483->483 | Deck 19->19
  deck_change: no deck change
  reasoning: Current HP is at a critical 6/70. Entering an Elite fight now is certain death. The Rest Site is mandatory to survive until the upcoming Shop where my 483 gold can be converted into deck-stabilizing relics and cards.
  strategic_note: Foundation deck with high gold: survive until the Floor 8 shop to buy power and relics that offset the Greed curse. Prioritize high-impact frontloaded cards and discard outlets to handle the curse while moving toward a defensive engine.

F7 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 6->27 | Gold 483->483 | Deck 19->19
  deck_change: no deck change
  reasoning: With 6 HP remaining, we are at critical risk of dying to any attack in the next combat. Resting to 27 HP is absolutely necessary to survive.
  strategic_note: Foundation deck with high gold: survive until the Floor 9 shop to buy power and relics that offset the Greed curse. Prioritize high-impact frontloaded cards and discard outlets to handle the curse while moving toward a defensive engine.

F7 [rest_site] proceed | source=auto
  HP 27->27 | Gold 483->483 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 483->483 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Unknown

F8 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 27->27 | Gold 483->483 | Deck 19->19
  deck_change: no deck change
  reasoning: At 27 HP with a shop coming up next floor, spending 5 HP for a colorless card is too risky when we have 483 gold to buy exactly what we need. The free random draft from Share Knowledge gives us a chance at a useful card without the health penalty.
  strategic_note: Foundation deck with high gold: going into the Floor 9 shop, use our 483 gold to buy run-defining relics, potion support for the upcoming Elite, and strong card removal/additions. Focus on mitigating the Greed curse and setting up a solid engine.

F8 [card_select] select_deck_card (option_index=4) | source=llm
  HP 27->27 | Gold 483->483 | Deck 19->20
  deck_change: added Footwork
  reasoning: Footwork is a premium defensive scaling power that perfectly complements Noxious Fumes. With Fumes providing slow but inevitable damage, Footwork ensures our basic block cards can stall out fights effectively.
  strategic_note: Committed poison/sly plan: use discard synergies for immediate block/draw while Noxious Fumes scales, relying on Footwork to survive long encounters. Look for more card draw, remove Strikes, and avoid adding low-impact attacks.

F8 [event] choose_event_option (option_index=0) | source=auto
  HP 27->27 | Gold 483->483 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F8 [map] choose_map_node (option_index=0) | source=llm
  HP 27->27 | Gold 483->483 | Deck 20->20
  deck_change: no deck change
  reasoning: With 483 gold and 27 HP, this shop is critical for survival. I need to buy high-impact relics and cards to compensate for my low HP and the Greed curse before the upcoming Elite fight. Skipping the shop for a monster encounter at this health level is too risky and wastes the massive gold advantage I've built.
  strategic_note: Foundation deck with critical gold reserves: use this shop to pivot into a committed engine by purchasing scaling and high-impact defensive relics. Prioritize removing the Greed curse or finding discard outlets to mitigate its impact. The goal is to stabilize health and secure a clear win condition before the Act 1 boss.

F9 [shop] buy_card (option_index=3) | source=plan
  HP 27->27 | Gold 483->333 | Deck 20->21
  deck_change: bought Malaise
  reasoning: Shop plan [1/5]: Premium defensive scaling against the upcoming Matriarch and Act 2 multi-attackers. Fits perfectly into our slow poison/stall gameplan.

F9 [shop] buy_card (option_index=1) | source=plan
  HP 27->27 | Gold 333->255 | Deck 21->22
  deck_change: bought Pinpoint
  reasoning: Shop plan [2/5]: Provides much-needed frontload damage to help clear hallways and early elites before poison scales. Will frequently cost 0-1 energy given our high skill count.

F9 [shop] buy_card (option_index=2) | source=plan
  HP 27->27 | Gold 255->229 | Deck 22->23
  deck_change: bought Piercing Wail
  reasoning: Shop plan [3/5]: Incredible value on sale. Highly efficient AoE damage mitigation that stalls enemy multi-attacks.

F9 [shop] remove_card_at_shop | source=plan
  HP 27->27 | Gold 229->229 | Deck 23->23
  deck_change: no deck change
  reasoning: Shop plan [4/5]: Removing a Strike increases the density of our defensive skills, discard enablers, and poison scaling. Greed cannot be removed (Eternal).

F9 [card_select] select_deck_card (option_index=0) | source=llm
  HP 27->27 | Gold 229->129 | Deck 23->22
  deck_change: lost Strike
  reasoning: Strikes are the weakest cards in the deck, especially as we pivot toward a Poison and Defensive scaling strategy with Noxious Fumes and Footwork. Removing a Strike improves our draw consistency for key powers and mitigation.
  strategic_note: Committed poison/defense plan: stall with Footwork, Piercing Wail, and block while Noxious Fumes scales. Use Sly triggers (Survivor, Acrobatics) to play Untouchable/Ricochet for free. Needs more poison application/acceleration or block scaling; skip low-impact attacks.

F9 [shop] buy_potion (option_index=2) | source=plan
  HP 27->27 | Gold 129->77 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan [5/5]: Crucial consumable for the Lagavulin Matriarch fight. Helps offset her Dexterity debuff on turn 4 or boosts our block significantly on her heavy-hitting turns.

F9 [shop] close_shop_inventory | source=plan
  HP 27->27 | Gold 77->77 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F9 [shop] proceed | source=auto
  HP 27->27 | Gold 77->77 | Deck 22->22
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 77->77 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 27->27 | Gold 77->113 | Deck 22->22
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 27->27 | Gold 113->113 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim: Meat on the Bone

F10 [treasure] proceed | source=random
  HP 27->27 | Gold 113->113 | Deck 22->22
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 113->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 113->125 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 125->125 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Power Potion

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 125->125 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 33->33 | Gold 125->125 | Deck 22->23
  deck_change: picked Well-Laid Plans
  reasoning: Well-Laid Plans is a premium consistency tool that fits perfectly with our defensive setup and discard synergies. It allows us to hold crucial defensive cards like Piercing Wail for exactly when bosses attack, and pairs well with our Sly cards by holding them until we find a discard outlet.
  strategic_note: Foundation phase, shifting towards control/poison. Retain key defensive cards (Piercing Wail, Malaise) for big hits, use discard synergy (Acrobatics/Survivor + Sly) for tempo, and let Noxious Fumes scale damage. Need more focused damage scaling (poison) and deck thinning.

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 33->33 | Gold 125->0 | Deck 23->23
  deck_change: no deck change
  reasoning: With 33/70 HP and the 'Meat on the Bone' relic, I am in the perfect position to take this Elite fight. Winning the fight (even if I take some damage) will likely trigger the 12 HP heal, and there is a guaranteed Rest Site immediately following this node to recover further before the end of the act. Avoiding this Elite would waste the value of my healing relic and the opportunity for a relic/rare card.
  strategic_note: Foundation deck with Meat on the Bone sustain: take calculated risks in Elites to trigger healing and find scaling pieces. Prioritize high-impact frontloaded damage and discard outlets to mitigate the Greed curse while transitioning toward a defensive engine.

F12 [card_select] select_deck_card (option_index=2) | source=llm
  HP 33->33 | Gold 125->0 | Deck 23->23
  deck_change: no deck change
  reasoning: This is from a Power potion for the current combat. Fan of Knives provides immediate frontload by giving 4 Shivs (which hit all enemies), helping to burst down the Elite. Accelerant would only be useful if we already have Noxious Fumes in play and have time to wait for it to scale.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 27->27 | Gold 125->153 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 28 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 27->27 | Gold 153->153 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Clarity Extract

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 27->27 | Gold 153->153 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim relic: Pocketwatch

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 27->27 | Gold 153->153 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 27->27 | Gold 153->153 | Deck 23->24
  deck_change: picked Afterimage
  reasoning: Afterimage is a premium scaling defense power that perfectly complements a poison strategy (which relies on stalling) and helps mitigate multi-attacks. It also triggers off our Sly cards playing themselves for free.
  strategic_note: Committed poison/discard plan: use Fumes to scale damage while cycling for key defensive powers (Footwork, Afterimage) and utilizing Pocketwatch for massive draw. Keep the deck focused on mitigation and draw, avoiding standard attacks.

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 153->153 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: RestSite

F13 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 27->48 | Gold 153->153 | Deck 24->24
  deck_change: no deck change
  reasoning: With 27 HP and a slow-setup engine (Noxious Fumes, Afterimage, Footwork), resting is crucial to build an HP buffer for the upcoming Act 1 boss. This guarantees survival through the next Unknown node and allows us to potentially smith at the final rest site before the boss.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.

F13 [rest_site] proceed | source=auto
  HP 48->48 | Gold 153->153 | Deck 24->24
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 153->153 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Unknown

F14 [event] choose_event_option (option_index=1) | source=llm
  HP 48->48 | Gold 153->153 | Deck 24->24
  deck_change: no deck change
  reasoning: Removing a Strike increases the consistency of drawing our key defensive and scaling powers (Footwork, Noxious Fumes, Afterimage). With a 24-card deck, thinning out basic cards is highly valuable and more reliable than random upgrades.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.

F14 [card_select] select_deck_card (option_index=0) | source=llm
  HP 48->48 | Gold 153->153 | Deck 24->23
  deck_change: lost Strike
  reasoning: Strike is the least impactful card in our deck. We are transitioning into a defensive poison engine with Noxious Fumes, Footwork, and Afterimage. Removing a Strike increases our chance to draw these key powers and defensive cards, which is especially important when pacing our card plays with Pocketwatch.
  strategic_note: Committed poison plan: rely on Noxious Fumes for scaling damage while maximizing defense with Footwork, Afterimage, and block cards. Pace turns to trigger Pocketwatch draw. Continue removing Strikes and avoid low-impact attacks.

F14 [event] choose_event_option (option_index=0) | source=auto
  HP 48->48 | Gold 153->153 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 48->48 | Gold 153->153 | Deck 23->23
  deck_change: no deck change
  reasoning: With 153 gold and a curse (Greed) in the deck, a shop visit is high value for removal and finding scaling pieces before the boss. While Meat on the Bone encourages aggressive play, the path forward leads to a final Rest Site and Boss, making this the optimal time to clean the deck and spend accumulated gold.
  strategic_note: Foundation deck with Meat on the Bone sustain: prioritize deck thinning to remove Greed and finding defensive scaling or discard outlets to manage the curse until removed. Avoid taking unnecessary chip damage in hallways while looking for a finisher card for the Act 1 boss.

F15 [shop] buy_card (option_index=4) | source=plan
  HP 48->48 | Gold 153->81 | Deck 23->24
  deck_change: bought Footwork
  reasoning: Shop plan [1/2]: A second Footwork gives us up to 4 Dexterity, which creates an incredibly robust defensive engine with our Defends and Afterimage.

F15 [shop] buy_card (option_index=2) | source=plan
  HP 48->48 | Gold 81->31 | Deck 24->25
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [2/2]: Synergizes perfectly with our Footwork and Afterimage, providing efficient block and generating a Shiv that can be used or held.

F15 [shop] close_shop_inventory | source=plan
  HP 48->48 | Gold 31->31 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F15 [shop] proceed | source=auto
  HP 48->48 | Gold 31->31 | Deck 25->25
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 31->31 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 48->69 | Gold 31->31 | Deck 25->25
  deck_change: no deck change
  reasoning: Restoring 21 HP before the Act 1 Boss is critical for our slow-scaling deck. We need the health buffer to safely deploy our powers (Footwork x2, Afterimage, Noxious Fumes) without risking lethal damage during the early turns.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.

F16 [rest_site] proceed | source=auto
  HP 69->69 | Gold 31->31 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 69->69 | Gold 31->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 31->106 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 106->106 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Power Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 106->106 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 52->52 | Gold 106->106 | Deck 25->26
  deck_change: picked Tools of the Trade
  reasoning: Tools of the Trade provides exceptional value with our existing deck. It synergizes heavily with Well-Laid Plans and our Sly cards (Ricochet, Untouchable), allowing us to retain a Sly card and automatically discard it at the start of the next turn for a free play. It also helps filter our deck to find our critical scaling powers (Footwork, Noxious Fumes) faster, which is essential against the upcoming Lagavulin Matriarch.
  strategic_note: Committed to a defensive poison and Sly engine. Retain Sly cards to discard with Tools of the Trade or Acrobatics for free plays. Stall with Footwork, Afterimage, and Piercing Wail while Noxious Fumes handles scaling damage. Prioritize Strike removals and power upgrades.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 52->66 | Gold 106->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2) | source=llm
  HP 66->66 | Gold 106->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Pael's Eye provides an incredible bailout for dead draws, particularly hands choked by Greed, Ascender's Bane, or Strikes. By ending the turn without playing cards, those dead cards exhaust for the rest of the combat and we immediately get a fresh turn, accelerating our engine setup.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Use Pael's Eye on weak hands to exhaust junk (like Greed) and take a fresh turn. Needs more upgraded defense and reliable discard outlets; avoid slow attacks.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 66->66 | Gold 106->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 66->66 | Gold 106->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to a standard monster encounter. This aligns with the strategy of evaluating deck consistency early in the Act while HP is high, especially with Meat on the Bone providing a safety net for chip damage.
  strategic_note: Foundation deck with Meat on the Bone sustain: prioritize drafting defensive scaling and discard outlets to manage Greed while looking for a reliable poison or shiv engine to transition into a committed scaling build.

F19 [card_select] select_deck_card (option_index=1) | source=llm
  HP 66->66 | Gold 106->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Noxious Fumes provides excellent passive AoE damage scaling, stacking with our existing copy to quickly melt enemies while we focus on defending with Footwork and Piercing Wail.
  strategic_note: Committed poison/defense plan: survive and stall using high-value block, Footwork, and damage mitigation while Noxious Fumes slowly kills everything. Needs upgraded Noxious Fumes or Catalyst for faster scaling; avoid low-impact attacks.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 106->113 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 113->113 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 46->46 | Gold 113->113 | Deck 26->27
  deck_change: picked Bubble Bubble
  reasoning: Bubble Bubble provides incredible damage acceleration for our Noxious Fumes. We can use Well-Laid Plans to hold it until Fumes has applied poison to enemies, giving us a massive burst of poison to help win tight damage races like the Knowledge Demon boss fight.
  strategic_note: Committed poison/defense plan: Noxious Fumes is our main scaling, heavily accelerated by Bubble Bubble. Retain Bubble Bubble with Well-Laid Plans until Poison is applied. Play Footwork, Afterimage, and block heavily while poison ticks down enemies. Use Pocketwatch by playing 3 or fewer high-impact cards when possible. Remove Strikes at shops.

F19 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 113->113 | Deck 27->27
  deck_change: no deck change
  reasoning: Following the recommended route intelligence for Act 2 which prioritizes non-combat nodes to preserve HP. With Meat on the Bone, I have some sustain, but the Silent's slow defensive engine is vulnerable to Act 2 hallway attrition. The Unknown node offers a chance for events or a shop rather than a guaranteed chip-damage monster fight.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Needs more upgraded defense and reliable discard outlets for Greed; avoid slow attacks.

F20 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 46->46 | Gold 113->113 | Deck 27->26
  deck_change: lost Dagger Throw
  reasoning: Dagger Throw is an expendable attack. While it provides a discard outlet, we have Tools of the Trade, Acrobatics, and Survivor. Removing it thins the deck without spending HP to reroll into potentially losing a crucial power like Noxious Fumes or Footwork.
  strategic_note: Defensive slow-engine: establish Footwork and Afterimage, apply Noxious Fumes, then block heavily while poison scales. Use Pael's Eye on weak hands to exhaust junk and take a fresh turn. Needs upgraded defense and discard outlets; avoid slow attacks.

F20 [event] choose_event_option (option_index=0) | source=auto
  HP 46->46 | Gold 113->113 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 113->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 113->113 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 46->46 | Gold 113->113 | Deck 25->25
  deck_change: no deck change
  reasoning: Our deck has a strong Pocketwatch relic which encourages playing 3 or fewer cards per turn. Blade Dance+ heavily conflicts with Pocketwatch by requiring 5 card plays for its full effect. Prepared also adds an unnecessary card play. We have enough damage with our Fumes/Bubble Bubble poison package and Pinpoint. Skipping keeps the deck lean and maximizes Pocketwatch value.
  strategic_note: Committed to defensive stall with poison (Fumes, Bubble Bubble) and Pocketwatch card advantage. Play 3 or fewer impactful cards per turn to maintain massive draw. Avoid multi-play cards like Shivs that disrupt Pocketwatch.

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 113->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Monster

## Selected Replay Package (4 replays)
[Selected: run_combat] multi:Calcified Cultist+Damp Cultist (F5, monster)
Historical: loss=21 vs historical avg=3.3+/-4.7 (z=3.7, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs multi:Calcified Cultist+Damp Cultist (Floor 5, monster)
Relics: Ring of the Snake, Cursed Pearl
Deck (17): Defend x5, Strike x5, Acrobatics, Ascender's Bane, Greed, Neutralize, Noxious Fumes, Survivor, Untouchable
Enemies: Calcified Cultist HP=40/40, Damp Cultist HP=52/52

### Round 1
Agent plan (hypothesis): Play Noxious Fumes if drawn.
Agent plan (hypothesis): Ascender's Bane auto-exhausts.
Intent: Calcified Cultist: Buff, Damp Cultist: Buff
  Neutralize -> Damp Cultist[1]
    enemy_deltas: Damp Cultist: hp -3, +Weak(1)
  Acrobatics
    energy -1
  Untouchable
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Noxious Fumes is active. Prioritize blocking and mitigating scaling attacks while poison takes its toll. Consider using Beetle Juice if incoming damage outpaces our block capability.
Intent: Calcified Cultist: Attack(9), Damp Cultist: Attack(1)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Agent plan (hypothesis): Next turn we draw 5 of the remaining 6 cards (Survivor, Untouchable, Acrobatics, 3x Strike). We should be able to block well.
Intent: Calcified Cultist: Attack(11), Damp Cultist: Attack(6)
  Neutralize -> Calcified Cultist[0]
    enemy_deltas: Calcified Cultist: hp -3, +Weak(1)
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Agent plan (hypothesis): Calcified Cultist is dead. Damp Cultist will scale quickly with Ritual(5), prioritize bursting it down or blocking well.
Intent: Calcified Cultist: Attack(13), Damp Cultist: Attack(11)
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: DIED
  turn_end

### Round 5
Agent plan (hypothesis): Next turn the draw pile will consist of 3 Strikes, Neutralize, and Acrobatics, which we will draw fully. Use Neutralize to mitigate the enemy's scaled damage.
Intent: Damp Cultist: Attack(16)
  Survivor
    energy -1 | block +8
  Untouchable
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Agent plan (hypothesis): Damp Cultist is scaling out of control. We need to burn him down next turn if possible.
Intent: Damp Cultist: Attack(21)
  Acrobatics
    energy -1
  Untouchable
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 7
Agent plan (hypothesis): Damp Cultist is heavily poisoned. Just deal enough damage next turn to secure the kill.
Intent: Damp Cultist: Attack(26)
  Beetle Juice -> Damp Cultist[0]
    enemy_deltas: Damp Cultist: +Shrink(4)
  Neutralize -> Damp Cultist[0]
    enemy_deltas: Damp Cultist: hp -3, +Weak(1)
  Strike -> Damp Cultist[0]
    energy -1 | enemy_deltas: Damp Cultist: hp -6
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  turn_end

### Round 8
Agent plan (hypothesis): Survive the turn, then finish it next turn as poison continues to tick.
Intent: Damp Cultist: Attack(21)
  Neutralize -> Damp Cultist[0]
    enemy_deltas: Damp Cultist: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 9
Agent plan (hypothesis): Damp cultist scaling gets out of hand really fast if not killed quickly.
Intent: Damp Cultist: Attack(25)
  Acrobatics
    energy -1
  Untouchable
  Strike -> Damp Cultist[0]
    energy -1 | enemy_deltas: Damp Cultist: hp -6
  Strike -> Damp Cultist[0]
    energy -1 | block -6 | -Noxious Fumes | enemy_deltas: Damp Cultist: DIED
## Combat Analytics: multi:Calcified Cultist+Damp Cultist (WIN - 9 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 4 plays, 12 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 3 plays
  Strike "Deal 6 damage." -> 9 plays, 42 dmg
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Defend "Gain 5 Block." -> 12 plays, 60 block
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:5 -> R7:6 -> R8:7 -> R9:8
  Poison[0]: R1:- -> R2:- -> R3:2 -> R4:3 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Poison[1]: R1:- -> R2:- -> R3:2 -> R4:3 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Ritual: R1:- -> R2:- -> R3:- -> R4:- -> R5:5 -> R6:5 -> R7:5 -> R8:5 -> R9:5
  Ritual[0]: R1:- -> R2:2 -> R3:2 -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Ritual[1]: R1:- -> R2:5 -> R3:5 -> R4:5 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Shrink: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:3 -> R9:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:15 -> R6:20 -> R7:25 -> R8:30 -> R9:35
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:5 -> R4:10 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-

Unattributed damage (power/passive effects): 5
  Per round: R4:5
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Calcified Cultist+Damp Cultist (Floor 12, monster)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra
Deck (18): Defend x5, Strike x5, Snakebite x2, Bullet Time, Dagger Throw, Flick-Flack, Neutralize, Predator, Survivor
Enemies: Calcified Cultist HP=40/40, Damp Cultist HP=52/52

### Round 1
Intent: Calcified Cultist: Buff, Damp Cultist: Buff
  Predator -> Calcified Cultist[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Calcified Cultist: hp -15
  Dagger Throw -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -9
  Defend
  turn_end

### Round 2
Intent: Calcified Cultist: Attack(9), Damp Cultist: Attack(1)
  Poison Potion -> Damp Cultist[1]
    enemy_deltas: Damp Cultist: +Poison(6)
  Neutralize -> Calcified Cultist[0]
    enemy_deltas: Calcified Cultist: hp -3, +Weak(1)
  Flick-Flack
    energy -1 | enemy_deltas: Calcified Cultist: hp -6; Damp Cultist: hp -6
  Strike -> Calcified Cultist[0]
    energy -1 | enemy_deltas: Calcified Cultist: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Intent: Calcified Cultist: Attack(11), Damp Cultist: Attack(6)
  Neutralize -> Calcified Cultist[0]
    enemy_deltas: Calcified Cultist: DIED
  Defend
    energy -1 | block +5
  Snakebite -> Damp Cultist[0]
    energy -2 | enemy_deltas: Damp Cultist: Poison(5→12)
  turn_end

### Round 4
Intent: Damp Cultist: Attack(11)
  Bullet Time
    energy -3 | +No Draw(1)
  Snakebite -> Damp Cultist[0]
    enemy_deltas: Damp Cultist: Poison(11→18)
  Flick-Flack
    enemy_deltas: Damp Cultist: hp -6
  Strike -> Damp Cultist[0]
    enemy_deltas: Damp Cultist: hp -6
  Defend
    block +5
  Defend
    block +5
  turn_end
    -No Draw
## Combat Analytics: multi:Calcified Cultist+Damp Cultist (WIN - 4 rounds)

Cards played (with descriptions):
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 3 dmg
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 2 plays, 18 dmg
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Defend "Gain 5 Block." -> 5 plays, 25 block
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, +14 poison
  Bullet Time "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays

Poison stacks applied per card:
  Snakebite: 14 stacks
  Poison Potion: 6 stacks
Total poison/power tick damage: 1
  Per round: R3:1

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:5 -> R4:11
  Ritual: R1:- -> R2:- -> R3:- -> R4:5
  Ritual[0]: R1:- -> R2:2 -> R3:2 -> R4:-
  Ritual[1]: R1:- -> R2:5 -> R3:5 -> R4:-
  Strength: R1:- -> R2:- -> R3:- -> R4:10
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:-
  Strength[1]: R1:- -> R2:- -> R3:5 -> R4:-

[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F12, elite)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 12, elite)
Relics: Ring of the Snake, Cursed Pearl, Meat on the Bone
Deck (23): Defend x5, Strike x4, Acrobatics, Ascender's Bane, Dagger Throw, Footwork, Greed, Malaise, Neutralize, Noxious Fumes, Piercing Wail, Pinpoint, Ricochet, Survivor, Untouchable, Well-Laid Plans
Enemies: Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=30/30

### Round 1
Agent plan (hypothesis): Dagger Throw drawn card might be 0-cost. Check hand before ending turn.
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Power Potion
  Fan of Knives
  Footwork
    energy -1 | +Dexterity(2)
  Defend
    energy -1 | block +7
  Fan of Knives
    +Fan of Knives(1)
  Shiv
    exhausted: Shiv [0]: Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Phantasmal Gardener: hp -4, block +6
  Shiv
    enemy_deltas: Phantasmal Gardener: block -4
  Shiv
    enemy_deltas: Phantasmal Gardener: hp -2, block -2
  Shiv
    enemy_deltas: Phantasmal Gardener: hp -4
  Dagger Throw -> Phantasmal Gardener[0]
    energy -1
  Greed
  Malaise -> Phantasmal Gardener[0]
    exhausted: Shiv*4 [0]: Deal 4 damage to ALL enemies. Exhaust.
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Neutralize -> Phantasmal Gardener[0]
  Strike -> Phantasmal Gardener[0]
    energy -1
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end

### Round 3
Agent plan (hypothesis): Ascender's Bane exhausts this turn. Be ready to mitigate E2's upcoming multi-attacks with its newly buffed Strength.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  Piercing Wail
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Phantasmal Gardener: Strength(2→-4), +Piercing Wail(6)
  Untouchable
    energy -2 | block +8
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage to ALL enemies. Exhaust.

### Round 4
Agent plan (hypothesis): Fumes is active, G0 is dead.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(3x3=9)
  Dexterity Potion
    Dexterity(2→4)
  Acrobatics
    energy -1
  Untouchable
  Defend
    energy -1 | block +9
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Pinpoint -> Phantasmal Gardener[0]
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff
  Defend
    energy -1 | block +9
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Strike -> Phantasmal Gardener[1]
    energy -1
  turn_end
  Ricochet

### Round 6
Agent plan (hypothesis): Poison is ticking them down steadily. Maintain full block every turn to minimize HP loss.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Attack(9)
  Neutralize -> Phantasmal Gardener[1]
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Survivor
    energy -1 | block +12
  Ricochet
  turn_end
    enemy_deltas: Phantasmal Gardener: hp -3, block +6
  Dagger Throw

### Round 7
Intent: Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(11)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  turn_end
  Acrobatics

### Round 8
Agent plan (hypothesis): G1 is dead, G0 is left with just a few HP and will die to poison soon.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(5x3=15)
  Acrobatics
    energy -1
  Ricochet
  Strike -> Phantasmal Gardener[1]
    energy -1 | enemy_deltas: Phantasmal Gardener: block -6
  Neutralize -> Phantasmal Gardener[0]
  Survivor
    energy -1 | block +12
  Strike
  turn_end
  Pinpoint
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 8 rounds)

Cards played (with descriptions):
  Footwork "Gain 2 Dexterity." -> 1 plays
  Defend "Gain 7 Block." -> 10 plays, 84 block
  Fan of Knives "Shivs now hit ALL enemies. Add 4 Shivs into your Hand." -> 1 plays, generates 4 Shivs
  Shiv "Deal 4 damage to ALL enemies. Exhaust." -> 4 plays, 10 dmg, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 3 plays
  Strike "Deal 6 damage." -> 3 plays
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Untouchable "Sly. Gain 8 Block." -> 1 plays, 8 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Survivor "Gain 12 Block. Discard 1 card." -> 2 plays, 24 block

Token attribution (Shivs):
  Fan of Knives: 4 Shivs -> ~10 dmg

Enemy power timeline:
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4 -> R8:5
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4 -> R8:5
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4 -> R8:5
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[3]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:4
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:4 -> R7:4 -> R8:4
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 14, elite)
Relics: Ring of the Snake, Silver Crucible, Snecko Skull
Deck (18): Defend x5, Strike x4, Abrasive, Backflip, Bouncing Flask+, Cloak and Dagger+, Dagger Spray+, Neutralize+, Predator+, Survivor, Well-Laid Plans+
Enemies: Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=31/31

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Survivor
    energy -1 | block +8
  Abrasive
  Defend
    energy -1 | block +6 | +Dexterity(1) | +Thorns(4)
  turn_end
  Strike
  Strike

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Neutralize+ -> Phantasmal Gardener[3]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6, +Weak(2)
  Backflip
    energy -1 | block +6
  Cloak and Dagger+
    energy -1 | block +7
  Dagger Spray+
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block -6
  Shiv -> Phantasmal Gardener[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Phantasmal Gardener[0]
  turn_end
  Bouncing Flask+
  confirm

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(6)
  Strike -> Phantasmal Gardener[0]
    energy -1
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Bouncing Flask+
  Predator+

### Round 4
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(3x3=9)
  Cloak and Dagger+
    energy -1 | block +7
  Predator+ -> Phantasmal Gardener[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Phantasmal Gardener: hp -12
  Shiv -> Phantasmal Gardener[0]
    block -7 | -Well-Laid Plans | -Dexterity | -Thorns | -Draw Cards Next Turn | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 4 rounds)

Cards played (with descriptions):
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Defend "Gain 5 Block." -> 3 plays, 18 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 1 plays, 6 block
  Cloak and Dagger+ "Gain 7 Block. Add 2 Shivs into your Hand." -> 2 plays, 14 block, generates 2 Shivs
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 1 plays, 6 dmg
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, EXHAUST
  Strike "Deal 6 damage." -> 1 plays
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 12 dmg

Token attribution (Shivs):
  Cloak and Dagger+: 3 Shivs -> ~0 dmg

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:-
  Skittish[3]: R1:6 -> R2:6 -> R3:6 -> R4:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:-
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:-

[Selected: boss] Lagavulin Matriarch (F17, boss)
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Cursed Pearl, Meat on the Bone, Pocketwatch
Deck (25): Defend x5, Strike x3, Footwork x2, Acrobatics, Afterimage, Ascender's Bane, Cloak and Dagger, Dagger Throw, Greed, Malaise, Neutralize, Noxious Fumes, Piercing Wail, Pinpoint, Ricochet, Survivor, Untouchable, Well-Laid Plans
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Agent plan (hypothesis): Pocketwatch + Clarity Extract will draw 9 cards next turn. Boss will have 2 turns of sleep left.
Intent: Lagavulin Matriarch: Sleep
  Clarity Extract
    +Clarity(3)
  Footwork
    energy -1 | +Dexterity(2)
  turn_end

### Round 2
Agent plan (hypothesis): Retain Acrobatics to use after clearing hand space next turn. Next turn, play Afterimage and Fumes.
Intent: Lagavulin Matriarch: Sleep
  Footwork
    energy -1 | Dexterity(2→4)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Acrobatics

### Round 3
Intent: Lagavulin Matriarch: Sleep
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Afterimage
    energy -1 | +Afterimage(1)
  turn_end
  Acrobatics

### Round 4
Agent plan (hypothesis): Retain Piercing Wail. Boss may do a buff turn next, then a heavy multi-attack.
Intent: Lagavulin Matriarch: Attack(19)
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: hp -3, +Weak(1)
  Defend
    energy -1 | block +10
  Defend
    energy -1 | block +10
  Acrobatics
    energy -1
  Untouchable
  Pinpoint -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: hp -15
  turn_end
  Piercing Wail

### Round 5
Agent plan (hypothesis): Play Malaise for X=3 next turn to completely neuter the Matriarch's multi-attacks. Keep triggering Pocketwatch if possible.
Agent plan (hypothesis): Play Malaise for X=3 next turn.
Intent: Lagavulin Matriarch: Attack(9x2=18)
  Cloak and Dagger
    energy -1 | block +11
  Defend
    energy -1 | block +10
  Strike -> Lagavulin Matriarch[0]
    energy -1 | block +1 | enemy_deltas: Lagavulin Matriarch: hp -6
  turn_end
  Malaise

### Round 6
Agent plan (hypothesis): Pocketwatch triggers. Matriarch is weak and has negative strength, her multi-attacks are no longer a threat. Focus on cycling for poison and block.
Intent: Lagavulin Matriarch: Attack(12), Defend
  Survivor
    energy -1 | block +12
  Ricochet
  Malaise -> Lagavulin Matriarch[0]
    energy -2 | block +3 | exhausted: Malaise [X]: Enemy loses X Strength. Apply X Weak. Exhaust. | enemy_deltas: Lagavulin Matriarch: hp -9, +Strength(-2), +Weak(2)
  turn_end
  Acrobatics

### Round 7
Agent plan (hypothesis): Pocketwatch triggers. You will draw 8 cards next turn. Retain Piercing Wail.
Agent plan (hypothesis): Retain Piercing Wail for upcoming attacks.
Agent plan (hypothesis): Retain Piercing Wail.
Intent: Lagavulin Matriarch: Debuff, Buff
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: block -3, Weak(1→2)
  Shiv -> Lagavulin Matriarch[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Lagavulin Matriarch: block -4
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -4, block -5
  Untouchable
  Acrobatics
    energy -1
  Strike
  Cloak and Dagger
    energy -1 | block +11
  Shiv -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: hp -4
  turn_end
  Piercing Wail

### Round 8
Agent plan (hypothesis): Retain Piercing Wail to counter the upcoming multi-attack.
Intent: Lagavulin Matriarch: Attack(14)
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: hp -1, Weak(1→2)
  Defend
    energy -1 | block +8
  Survivor
    energy -1 | block +10
  Strike
  turn_end
  Piercing Wail

### Round 9
Agent plan (hypothesis): Pocketwatch will trigger. Retain Piercing Wail.
Agent plan (hypothesis): Continue stalling for Poison damage while prioritizing Pocketwatch.
Intent: Lagavulin Matriarch: Attack(6x2=12)
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -7
  Untouchable
  Survivor
    energy -1 | block +10
  Greed
  turn_end
  Piercing Wail

### Round 10
Intent: Lagavulin Matriarch: Attack(12), Defend
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  Strike -> Lagavulin Matriarch[0]
    energy -1 | block +1 | enemy_deltas: Lagavulin Matriarch: hp -4
  turn_end
  Piercing Wail

### Round 11
Intent: Lagavulin Matriarch: Debuff, Buff
  Cloak and Dagger
    energy -1 | block +9
  Pinpoint -> Lagavulin Matriarch[0]
    energy -2 | block +1 | enemy_deltas: Lagavulin Matriarch: hp -1, block -12
  Shiv -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: hp -2
  turn_end
  Piercing Wail

### Round 12
Agent plan (hypothesis): Pocketwatch triggers. Keep stacking poison and using WLP to hold key cards.
Intent: Lagavulin Matriarch: Attack(21)
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: +Weak(1)
  Piercing Wail
    energy -1 | block +1 | exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Lagavulin Matriarch: Strength(2→-4), +Piercing Wail(6)
  Survivor
    energy -1 | block +8
  Defend
  turn_end
  Ricochet

### Round 13
Agent plan (hypothesis): Retain Acrobatics with Well-Laid Plans for next turn.
Agent plan (hypothesis): Pocketwatch is already at 3 so we lost it, but preserving HP is worth it.
Intent: Lagavulin Matriarch: Attack(11x2=22)
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: +Weak(1)
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -5
  Untouchable
  Survivor
    energy -1 | block +8
  Strike
  Defend
    energy -1 | block +6
  turn_end
  Acrobatics

### Round 14
Agent plan (hypothesis): Hold Acrobatics with WLP for next turn.
Intent: Lagavulin Matriarch: Attack(14), Defend
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Acrobatics

### Round 15
Agent plan (hypothesis): Pocketwatch triggers. Use Retain on a Defend or Strike.
Intent: Lagavulin Matriarch: Debuff, Buff
  Acrobatics
    energy -1
  Ricochet
  turn_end
  Defend

### Round 16
Agent plan (hypothesis): Pocketwatch will be inactive for a while, but poison continues ticking.
Intent: Lagavulin Matriarch: Attack(23)
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -3
  Untouchable
  Cloak and Dagger
    energy -1 | block +5
  Shiv -> Lagavulin Matriarch[0]
    block +1
  turn_end
  Survivor

### Round 17
Agent plan (hypothesis): Hold the drawn Defend with Well-Laid Plans to secure block for the next turns as the poison finishes her off.
Agent plan (hypothesis): Poison is ticking, just stay alive.
Intent: Lagavulin Matriarch: Attack(13x2=26)
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: +Weak(1)
  Acrobatics
    energy -1
  Ricochet
  Survivor
    energy -1 | block +6
  Strike
  Defend
    energy -1 | block +4
  turn_end
  Pinpoint

### Round 18
Intent: Lagavulin Matriarch: Attack(16), Defend
  Neutralize -> Lagavulin Matriarch[0]
    block +1 | enemy_deltas: Lagavulin Matriarch: +Weak(1)
  Defend
    energy -1 | block +4
  Defend
    energy -1 | block +4
  Pinpoint -> Lagavulin Matriarch[0]
    energy -1 | block +1 | enemy_deltas: Lagavulin Matriarch: hp -9
  turn_end
  confirm_selection

### Round 19
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
  confirm_selection
## Combat Analytics: Lagavulin Matriarch (WIN - 19 rounds)

Cards played (with descriptions):
  Footwork "Gain 2 Dexterity." -> 2 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 7 plays, 4 dmg, 7 block
  Defend "Gain 9 Block." -> 13 plays, 90 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 4 plays
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 3 plays, 25 dmg, 3 block
  Cloak and Dagger "Gain 10 Block. Add 1 Shiv into your Hand." -> 4 plays, 36 block, generates 1 Shivs
  Strike "Deal 6 damage." -> 2 plays, 10 dmg, 2 block
  Survivor "Gain 12 Block. Discard 1 card." -> 6 plays, 54 block
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, 9 dmg, 3 block, EXHAUST
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 6 dmg, 4 block, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 4 plays, 19 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST

Token attribution (Shivs):
  Cloak and Dagger: 3 Shivs -> ~4 dmg
  other: 1 Shivs -> ~2 dmg

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:-
  Plating: R1:12 -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:-
  Poison: R1:- -> R2:- -> R3:- -> R4:2 -> R5:3 -> R6:4 -> R7:5 -> R8:6 -> R9:7 -> R10:8 -> R11:9 -> R12:10 -> R13:11 -> R14:12 -> R15:13 -> R16:14 -> R17:15 -> R18:16 -> R19:17
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-2 -> R8:- -> R9:- -> R10:- -> R11:- -> R12:2 -> R13:2 -> R14:2 -> R15:2 -> R16:4 -> R17:4 -> R18:4 -> R19:4
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1 -> R9:1 -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra, Sword of Stone
Deck (19): Defend x5, Strike x5, Snakebite x2, Bullet Time+, Dagger Throw, Deadly Poison, Flick-Flack, Neutralize, Predator, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Intent: Lagavulin Matriarch: Sleep
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: block -9
  Flick-Flack
  turn_end

### Round 2
Intent: Lagavulin Matriarch: Attack(19)
  Neutralize -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -3, +Weak(1)
  Snakebite -> Lagavulin Matriarch[0]
    energy -2 | enemy_deltas: Lagavulin Matriarch: +Poison(7)
  Snakebite -> Lagavulin Matriarch[0]
    energy -2 | enemy_deltas: Lagavulin Matriarch: Poison(7→14)
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 3
Intent: Lagavulin Matriarch: Attack(9x2=18)
  Colorless Potion
  Scrawl
  Scrawl
    exhausted: Scrawl [1]: Draw cards until your Hand is full. Exhaust.
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -9
  Flick-Flack
  Deadly Poison -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: Poison(13→18)
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Lagavulin Matriarch: Attack(12), Defend
  Neutralize -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -3, +Weak(1)
  Snakebite -> Lagavulin Matriarch[0]
    energy -2 | enemy_deltas: Lagavulin Matriarch: Poison(17→24)
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 5
Intent: Lagavulin Matriarch: Debuff, Buff
  Bullet Time+
    energy -2 | +No Draw(1)
  Snakebite -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: Poison(23→30)
  Strike -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: block -6
  Defend
    block +5
  Defend
    block +5
  Defend
    block +5
  turn_end
    -No Draw

### Round 6
Intent: Lagavulin Matriarch: Attack(21)
  Attack Potion
  Precise Cut
  Predator -> Lagavulin Matriarch[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Lagavulin Matriarch: hp -13
  Defend
    energy -1 | block +3
  Precise Cut -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -5
  turn_end

### Round 7
Intent: Lagavulin Matriarch: Attack(11x2=22)
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -7
  Flick-Flack
  Neutralize -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -1, +Weak(1)
  Survivor
    energy -1 | block +6
  Strike
  Deadly Poison -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: Poison(28→33)
  turn_end

### Round 8
Intent: Lagavulin Matriarch: Attack(14), Defend
  Survivor
    energy -1 | block +6
  Strike
  Defend
    energy -1 | block +3
  turn_end
## Combat Analytics: Lagavulin Matriarch (WIN - 8 rounds)

Cards played (with descriptions):
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 16 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 3 plays, 7 dmg
  Snakebite "Retain. Apply 7 Poison." -> 4 plays, +28 poison
  Survivor "Gain 8 Block. Discard 1 card." -> 4 plays, 28 block
  Scrawl "Draw cards until your Hand is full. Exhaust." -> 1 plays, EXHAUST
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Defend "Gain 5 Block." -> 6 plays, 26 block
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays
  Strike "Deal 6 damage." -> 1 plays
  Predator "Deal 13 damage. Next turn, draw 2 cards." -> 1 plays, 13 dmg
  Precise Cut "Deal 5 damage. Deals 2 less damage for each other card in your Hand." -> 1 plays, 5 dmg

Poison stacks applied per card:
  Snakebite: 28 stacks
  Deadly Poison: 10 stacks

Enemy power timeline:
  Asleep: R1:3 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Plating: R1:12 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Poison: R1:- -> R2:- -> R3:13 -> R4:17 -> R5:23 -> R6:29 -> R7:28 -> R8:32
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:2 -> R8:2

[Selected: death] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (F22, monster)
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 22, monster)
Relics: Ring of the Snake, Cursed Pearl, Meat on the Bone, Pocketwatch, Pael's Eye
Deck (25): Defend x5, Strike x3, Acrobatics, Afterimage, Ascender's Bane, Bubble Bubble, Cloak and Dagger, Footwork, Greed, Malaise, Neutralize, Noxious Fumes, Piercing Wail, Pinpoint, Ricochet, Survivor, Tools of the Trade, Untouchable, Well-Laid Plans
Enemies: Bowlbug (Rock) HP=45/45, Bowlbug (Silk) HP=40/40, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Neutralize -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): hp -3, +Weak(1)
  Acrobatics
    energy -1
  Untouchable
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Survivor
    energy -1 | block +8
  Bubble Bubble
  Strike -> Bowlbug (Silk)[1]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -4
  Strike -> Bowlbug (Silk)[1]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -4
  turn_end

### Round 3
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(16), Buff
  Footwork
    energy -1 | +Dexterity(2)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end

### Round 5
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Attack(18), Buff
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Cloak and Dagger
    energy -1 | block +8
  Survivor
    energy -1 | block +10
  Greed
  turn_end

### Round 6
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(20), Buff
  Neutralize -> Slumbering Beetle[2]
    enemy_deltas: Slumbering Beetle: hp -2, +Weak(1)
  Acrobatics
    energy -1
  Untouchable
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Bowlbug (Rock): +Strength(-6), +Piercing Wail(6); Bowlbug (Silk): +Strength(-6), +Piercing Wail(6); Slumbering Beetle: Strength(4→-2), +Piercing Wail(6)
  turn_end

### Round 7
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Attack(22), Buff
  Cloak and Dagger
    energy -1 | block +8
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Pinpoint -> Slumbering Beetle[2]
    enemy_deltas: Slumbering Beetle: hp -15
  Shiv -> Slumbering Beetle[2]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Slumbering Beetle: hp -4
  turn_end

### Round 8
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(24), Buff
  turn_end
    exhausted: Strike [1]: Deal 6 damage.

### Round 9
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(24), Buff
  Neutralize -> Slumbering Beetle[2]
    enemy_deltas: Slumbering Beetle: hp -2, +Weak(1)
  Acrobatics
    energy -1
  Untouchable
  Malaise -> Slumbering Beetle[2]
    energy -2 | exhausted: Survivor [1]: Gain 8 Block. Discard 1 card. | enemy_deltas: Slumbering Beetle: Strength(8→6), Weak(1→3)
  turn_end
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (LOSS - 9 rounds)
Death cause: Killed by damage. HP 4 -> 0, took 0 damage.

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 3 plays, 7 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 3 plays
  Defend "Gain 5 Block." -> 8 plays, 48 block
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 18 block
  Strike "Deal 4 damage." -> 2 plays, 8 dmg
  Footwork "Gain 2 Dexterity." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Cloak and Dagger "Gain 8 Block. Add 1 Shiv into your Hand." -> 2 plays, 16 block, generates 1 Shivs
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 1 plays, 15 dmg
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 4 dmg, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST

Token attribution (Shivs):
  Cloak and Dagger: 1 Shivs -> ~4 dmg

Enemy power timeline:
  Imbalanced: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:3 -> R8:4 -> R9:6
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:3 -> R8:4 -> R9:6
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:3 -> R8:4 -> R9:6
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:4 -> R7:6 -> R8:8 -> R9:8
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 31, monster)
Relics: Ring of the Snake, Precarious Shears, Gremlin Horn, Red Mask, Darkstone Periapt, Ectoplasm, Sturdy Clamp
Deck (22): Defend x4, Strike x3, Abrasive, Dagger Spray, Deadly Poison, Dodge and Roll, Haze, Leg Sweep+, Mirage, Neutralize+, Nightmare+, Noxious Fumes, Noxious Fumes+, Predator, Prepared, Survivor, Tools of the Trade
Enemies: Bowlbug (Rock) HP=48/48, Bowlbug (Silk) HP=43/43, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(11), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Leg Sweep+ -> Bowlbug (Rock)[0]
    energy -2 | block +14 | enemy_deltas: Bowlbug (Rock): Weak(1→4)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  turn_end
  Strike

### Round 2
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Neutralize+ -> Bowlbug (Silk)[1]
    enemy_deltas: Bowlbug (Silk): hp -3, +Weak(2)
  Deadly Poison -> Bowlbug (Silk)[1]
    energy -1 | enemy_deltas: Bowlbug (Silk): Poison(2→7)
  Dagger Spray
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -6; Bowlbug (Silk): hp -6; Slumbering Beetle: block -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
  Haze

### Round 3
Intent: Bowlbug (Rock): Attack(11), Bowlbug (Silk): Debuff, Slumbering Beetle: Attack(16), Buff
  Mirage
    energy -1 | block +26 | exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 26 Block) Exhaust.
  Noxious Fumes+
    energy -1 | Noxious Fumes(2→5)
  Predator -> Bowlbug (Rock)[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Bowlbug (Rock): hp -15
  turn_end
  Haze

### Round 4
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(18), Buff
  Strike -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -4
  Deadly Poison -> Slumbering Beetle[2]
    energy -1 | enemy_deltas: Slumbering Beetle: Poison(15→20)
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Nightmare+
  turn_end
  Abrasive

### Round 5
Intent: Slumbering Beetle: Attack(20), Buff
  Neutralize+ -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -4, +Weak(2)
  Dagger Spray
    energy -1 | enemy_deltas: Slumbering Beetle: hp -8
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Strike

### Round 6
Intent: Slumbering Beetle: Attack(16), Buff
  Leg Sweep+ -> Slumbering Beetle[0]
    energy -2 | block +15 | enemy_deltas: Slumbering Beetle: Weak(1→4)
  Defend
    energy -1 | block +6
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  turn_end
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 6 rounds)

Cards played (with descriptions):
  Leg Sweep+ "Apply 3 Weak. Gain 14 Block." -> 2 plays, 29 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 2 plays, 7 dmg
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Dagger Spray "Deal 3 damage to ALL enemies twice." -> 2 plays, 20 dmg
  Defend "Gain 5 Block." -> 6 plays, 33 block
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 26 Block) Exhaust." -> 1 plays, 26 block, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg
  Strike "Deal 4 damage." -> 1 plays, 4 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 2 plays, 10 block

Poison stacks applied per card:
  Deadly Poison: 10 stacks

Enemy power timeline:
  Imbalanced: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:- -> R6:-
  Plating: R1:15 -> R2:14 -> R3:- -> R4:- -> R5:- -> R6:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:24 -> R6:28
  Poison[0]: R1:- -> R2:2 -> R3:7 -> R4:15 -> R5:- -> R6:-
  Poison[1]: R1:- -> R2:2 -> R3:8 -> R4:20 -> R5:- -> R6:-
  Poison[2]: R1:- -> R2:2 -> R3:3 -> R4:11 -> R5:- -> R6:-
  Slumber: R1:3 -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:6
  Weak: R1:- -> R2:3 -> R3:- -> R4:1 -> R5:- -> R6:1
  Weak[0]: R1:1 -> R2:- -> R3:2 -> R4:- -> R5:- -> R6:-
  Weak[1]: R1:1 -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:-
  Weak[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-

## Triggered Skills This Run
- The Silent - Deckbuilding Principles: F2(), F3(), F4(), F5(), F6(), F8(), F9(), F9(), F11(), F12(), F12(), F14(), F15(), F17(), F19(), F19(), F21()
- The Silent - Path Selection: F1(), F1(), F5(), F5(), F6(), F6(), F8(), F8(), F11(), F14(), F18(), F18(), F19()
- The Silent - Rest & Event Decisions: F7(), F13(), F16()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.