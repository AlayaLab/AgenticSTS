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
Result: VICTORY (fitness: 241.1)
Combats won: 21/21
Run duration: 5077.8s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: relying on basic strikes and defends. Look for high-value early game damage and block cards to capitalize on Silver Crucible upgrades, enabling an aggressive elite-hunting path through Act 1.
- [map] Foundation phase: Prioritizing consecutive monster encounters early to draft essential damage and block cards, leveraging full health to stabilize the deck for future elites.
### F2
- [card_reward] Foundation plan: survive with frontload damage like Predator+ while looking for a core scaling engine; take cheap draw or high-impact block, skip narrow synergy pieces until an engine is found.
- [map] Foundation phase: currently relying on basic cards. Prioritizing hallway fights to draft high-value early damage and block cards to leverage the Silver Crucible upgrades and prepare for upcoming Act 1 Elites.
### F3
- [card_reward] Foundation phase: relying on basic attacks, Predator+, and efficient cards like Cloak and Dagger+. Focus on acquiring frontload damage and generic mitigation to survive Act 1 elites before committing to a specific scaling engine.
- [map] Foundation phase: focusing on drafting high-value frontloaded damage and defensive cards to leverage the Silver Crucible upgrades before the first Elite encounter.
### F4
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a core scaling engine; take cheap draw or high-impact damage, and utilize Well-Laid Plans to smooth out hands.
### F5
- [card_reward] Foundation phase shifting to Poison engine. Rely on Predator+ for frontload and Bouncing Flask for boss scaling. Use WLP+ to retain key cards for the right turns. Look for poison synergy and efficient block.
### F6
- [card_reward] Foundation plan: survive with frontload (Predator+) and efficient block while looking for a core scaling engine (preferably poison, given Bouncing Flask). Take cheap draw or high-impact defense, skip mediocre commons.
- [map] Foundation phase: leveraging high health and early gold to upgrade key damage/block cards at rest sites. Preparing for mid-act Elites by focusing on card quality over quantity, seeking efficient front-loaded damage to minimize HP loss in upcoming races.
### F7
- [rest_site] Foundation phase: leveraging Neutralize+, Predator+, and Bouncing Flask for early Elite hunting. Use Well-Laid Plans to retain key cards like Neutralize for heavy attacks or Bouncing Flask for optimal scaling windows. Prioritize removing strikes to improve consistency.
### F8
- [card_reward] Committed to Poison plan with Snecko Skull + Bouncing Flask. Focus on acquiring more poison, mitigation, and draw. Keep the deck lean and remove basic attacks.
### F9
- [rest_site] Foundation phase: relying on Predator+ for frontload and Well-Laid Plans to retain key answers. Prioritize upgrading scaling and AoE damage to breeze through Act 1 Elites, using Dagger Spray for AoE and Bouncing Flask for single-target scaling.
### F11
- [card_reward] Poison engine committed: use Bouncing Flask + Snecko Skull to stack poison, then turtle. Retain Abrasive with Well-Laid Plans until Survivor is drawn to play it for free via Sly. Prioritize deck thinning, defensive scaling, and heavy draw next.
- [map] Foundation phase: relying on basic strikes and defends. Prioritize high-value frontloaded damage and block to maximize Silver Crucible's value while targeting a late Act 1 Elite and Shop for scaling.
### F12
- [rest_site] Foundation phase: relying on Predator+ for frontload and Well-Laid Plans to retain key answers. We have strong AoE and scaling now, so look to prioritize card draw, discard enablers for Abrasive, and defensive consistency while removing basic strikes.
### F13
- [card_select] Committed poison plan: use Snecko Skull and Bouncing Flask+ for damage, stall with defense and Weak. Use Survivor to discard Abrasive for free scaling. Needs more discard outlets and efficient block; continue removing Strikes.
### F14
- [hand_select] Well-Laid Plans(2) allows for 2 Retains. Retaining 2 cost cards for free is a massive tempo gain for the finishing turn.
- [card_reward] Committed poison plan: stack poison with Bouncing Flask and Deadly Poison, amplified by Snecko Skull. Use Well-Laid Plans to hold key block cards or Abrasive for Sly triggers. Looking for defensive scaling, AoE mitigation, and draw. Avoid generic attacks.
### F15
- [card_reward] Committed to poison scaling with Snecko Skull, Bouncing Flask, and Deadly Poison. Prioritize card draw and block to survive while poison kills. Avoid narrow or off-plan attacks.
### F16
- [rest_site] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks like Backflip and Survivor. Sly out Abrasive if possible using Survivor. Needs more block scaling or card draw; avoid raw un-upgraded attacks.
### F17
- [hand_select] Enemy is intangible (1) this turn. Poison (24) will tick for 1 damage. Saving damage for next turn.
- [card_reward] Committed to poison scaling with Snecko Skull, Bouncing Flask, and Deadly Poison. Use upfront damage (Predator, Assassinate) for early kills in hallways, then block and let poison tick. Need more defensive tools and cycle; skip off-plan attacks.
### F18
- [event] Committed poison/defensive plan: cycle through blocks and poison with Bouncing Flask+ and Deadly Poison. Use Survivor to discard Abrasive if it can't be played. Since we just removed our Strikes, we rely entirely on our engine to output damage.
- [card_select] Committed poison plan: rely on Snecko Skull + Bouncing Flask+/Deadly Poison for damage. Defend heavily while passive poison scales. Use Survivor to Sly Abrasive for Dexterity and Thorns. Avoid adding more generic attacks; look for Nightmare, Catalyst (if it exists), or premium block/draw to outlast enemies while they melt.
- [map] Foundation phase: relying on basic strikes and defends with Silver Crucible for value. Prioritizing early Act 2 hallway fights to test defensive consistency and fish for a scaling engine like poison or shivs before the mid-act shop.
### F19
- [card_reward] Committed poison plan: survive with efficient block and draw while Bouncing Flask scales rapidly via Snecko Skull. Find a way to trigger Abrasive or gain more energy/discard.
### F20
- [card_reward] Committed poison plan: survive with efficient block and draw while Bouncing Flask scales rapidly via Snecko Skull. Cycle aggressively to find Flask and defensive tools, using Well-Laid Plans to hold the right pieces. Need more draw, poison synergy, and card removals; skip generic attacks and off-plan mechanics.
- [map] Committed poison/defensive plan: use Bouncing Flask+ and Deadly Poison for damage while cycling blocks like Backflip and Survivor. Needs more block scaling or card draw; avoid raw un-upgraded attacks and prioritize HP preservation through non-combat nodes.
### F22
- [card_select] Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Need more targeted discard to bypass Abrasive's cost and manage Soot from Biiig Hug; avoid generic attacks.
### F23
- [card_reward] Committed poison plan: retain key defensive and poison cards with WLP, stack poison safely, and survive with Footwork and Piercing Wail while passive damage scales. Avoid off-plan attacks. Need more dedicated poison tools (like Catalyst) or reliable block.
- [map] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks like Backflip and Survivor. Needs more block scaling or card draw; prioritize upgrades that increase defensive efficiency or poison stacks.
### F24
- [rest_site] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Sly out Abrasive using Survivor. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.
- [map] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for scaling damage while using Survivor and Defends to stall. Avoid Act 2 Elites at all costs due to slow setup speed; prioritize pathing through Unknowns and Rest Sites to preserve HP for the boss.
### F25
- [event] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for scaling damage while using Survivor and Defends to stall. Carry Foul potions to the shop for a massive gold payout.
### F26
- [map] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage while cycling blocks with Footwork+ active. Prioritize Rest Sites to Smith core cards and avoid unnecessary Act 2 combats. Needs Catalyst or additional draw; avoid adding un-upgraded raw attacks.
### F27
- [rest_site] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Sly out Abrasive using Survivor. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.
- [map] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Currently prioritizing survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, as the deck's setup is slow and vulnerable to the high burst damage of Act 2 Elites.
### F28
- [event] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Continue to prioritize survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, relying on Well-Laid Plans to set up safe scaling turns.
### F29
- [rest_site] Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.
- [map] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Currently prioritizing survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, as the deck's setup is slow and vulnerable to the high burst damage of Act 2 Elites.
### F30
- [hand_select] Well-Laid Plans allows retaining one card. Backflip+ is the priority for draw consistency.
- [hand_select] Retaining key defensive tools like Piercing Wail is essential for the poison/stall strategy.
- [card_reward] Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling defensively with Footwork and Abrasive. Use Prepared and Survivor to discard Abrasive for free triggers or to pitch Soot. Need more card draw and perhaps one more poison source.
- [map] Committed poison plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Continue to prioritize survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, relying on Well-Laid Plans to set up safe scaling turns.
### F32
- [rest_site] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.
### F33
- [hand_select] Prioritizing survival cards (Piercing Wail) and death-timer management (Frantic Escape) over secondary scaling.
- [card_reward] Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Need more targeted discard to bypass Abrasive's cost and manage Soot from Biiig Hug; avoid generic attacks and clunky cards.
### F34
- [event] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.
- [map] Committed poison plan: stall with block while poison scales, using Well-Laid Plans to coordinate defensive turns. Prioritize high-value block cards and poison acceleration to minimize chip damage before the boss.
### F35
- [card_reward] Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Use Prepared+ and Survivor to discard Abrasive and Soots; avoid generic attacks and clunky additions.
- [map] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.
### F36
- [event] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.
- [map] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Use Prepared+ and Survivor to trigger Abrasive for dex. Prioritize card draw, mitigation, and thin the deck at shops to cycle poison faster.
### F37
- [map] Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.
### F38
- [card_reward] Committed poison plan: retain defensive and poison pieces, stack poison with Bouncing Flask and Snecko Skull, and survive using efficient block and Dexterity. Skip off-plan attacks and focus on draw/mitigation.
### F40
- [rest_site] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Outbreak provides AoE clearing.
### F41
- [map] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.
### F42
- [rest_site] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity.
### F43
- [hand_select] Abrasive played via Sly bypasses its 3-energy cost, accelerating my scaling.
- [hand_select] Energy is at 0/3, so I cannot play anything else this turn anyway. Well-Laid Plans allows one free retain.
- [hand_select] Poison lethal is secured.
- [card_reward] Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Retain key cards with Well-Laid Plans. Need targeted discard to bypass Abrasive's cost; avoid generic attacks and distractions.
### F44
- [card_reward] Committed poison plan: use Snecko Skull to stack poison rapidly with Bouncing Flask and Deadly Poison, retaining Bubble Bubble with WLP for a massive burst. Defend with Footwork-scaled block. Needs defensive consistency; avoid off-plan attacks.
- [map] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.
### F45
- [hand_select] Prioritizing the upgraded cards for maximum value next turn.
- [hand_select] Poison is our primary win condition and we have Thorns to chip them down during their multi-hit attacks.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Use Acrobatics/Prepared to trigger Abrasive or dig for Footwork/Outbreak. Needs Nightmare or Apparitions; skip off-plan attacks.
- [map] Committed poison/defensive plan: stall with high block while poison scales; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Prioritizing health preservation and campfires over high-risk elites or low-value shops to reach the boss with enough HP.
### F46
- [event] Committed poison/defensive plan: stall with high block while poison scales; use Prepared+ and Survivor to trigger Abrasive for free Dexterity.
- [card_select] Committed poison plan: apply poison with Bouncing Flask+ and Deadly Poison to trigger Outbreak+ AoE, stall with defensive scaling (Footwork+, Abrasive), and retain combo pieces with Well-Laid Plans. Needs more discard for Abrasive and draw.
### F47
- [rest_site] Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Prioritize survival and block scaling early in combats.

### Combat Decision Digest (21 combats)
F2 [monster] multi:Toadpole+Toadpole (4R, HP 70->70, loss=0, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike*2 | dealt=3 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=6 taken=0
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Neutralize->Strike->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Toadpole: Atk(7)]: Strike(6dmg)->Strike(6dmg)->Strike | dealt=12 taken=0

F3 [monster] Sludge Spinner (3R, HP 70->75, loss=0, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R2[Sludge Spinner: Atk(6), Buff]: Defend(+5blk)->Defend(+5blk)->Strike(4dmg) | dealt=4 taken=0
  R3[Sludge Spinner: Atk(14)]: Predator+ | dealt=0 taken=0

F4 [monster] Seapunk (3R, HP 75->75, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R2[Seapunk: Atk(2x4=8)]: Neutralize(3dmg,1+Weak(1))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Strike(6dmg)->Strike(6dmg) | dealt=23 taken=0
  R3[Seapunk: Buff, Defend]: Predator+ | dealt=0 taken=0

F5 [monster] Fossil Stalker (4R, HP 75->75, loss=0, WIN)
  R1[Fossil Stalker: Atk(12)]: Neutralize(3dmg,1+Weak(1))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Defend(+5blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=11 taken=0
  R2[Fossil Stalker: Atk(3x2=6)]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R3[Fossil Stalker: Atk(12)]: Cloak and Dagger+(+6blk)->Shiv(4dmg)->Shiv(4dmg)->Defend(+5blk)->Defend(+5blk) | dealt=8 taken=0
  R4[Fossil Stalker: Atk(9), Debuff]: Neutralize(3dmg,1+Weak(1))->Predator+(power:-Well-Laid Plans) | dealt=3 taken=0

F6 [monster] multi:Calcified Cultist+Damp Cultist (4R, HP 75->65, loss=10, WIN)
  R1[Calcified Cultist: Buff+Damp Cultist: Buff]: Bouncing Flask(1+Poison(3),1+Poison(6))->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=9 taken=0
  R2[Calcified Cultist: Atk(9)+Damp Cultist: Atk(1)]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=10
  R3[Calcified Cultist: Atk(11)+Damp Cultist: Atk(6)]: Neutralize(3dmg,1+Weak(1))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Defend(+5blk)->Strike(6dmg) | dealt=17 taken=0
  R4[Calcified Cultist: Atk(13)]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike(power:-Well-Laid Plans,power:-Draw Cards Next Turn) | dealt=20 taken=0

F8 [elite] Terror Eel (7R, HP 65->58, loss=7, WIN)
  R1[Terror Eel: Atk(16)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=1
  R2[Terror Eel: Atk(3x3=9), Buff]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R3[Terror Eel: Atk(22)]: Neutralize+(4dmg,1+Weak(2))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Defend(+5blk)->Strike(6dmg) | dealt=18 taken=5
  R4[Terror Eel: Atk(2x3=6), Buff]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=20 taken=1
  R5[Terror Eel: Atk(22)]: Neutralize+(6dmg,1+Weak(2))->Strike(9dmg)->Strike(9dmg)->Cloak and Dagger+(+6blk)->Shiv(6dmg)->Shiv(6dmg,1-Shriek) | dealt=36 taken=0
  R6[Terror Eel: Debuff]: Predator+(30dmg,power:+Draw Cards Next Turn(2))->Strike(9dmg) | dealt=39 taken=0
  R7[Terror Eel: Atk(33)]: Neutralize+(6dmg,1+Weak(2))->Strike(9dmg)->Strike(9dmg)->Strike(power:-Well-Laid Plans,power:-Vulnerable) | dealt=24 taken=0

F11 [monster] Living Fog (3R, HP 58->56, loss=2, WIN)
  R1[Living Fog: Atk(8), CardDebuff]: Bouncing Flask(1+Poison(12))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg) | dealt=8 taken=2
  R2[Living Fog: Atk(5), Summon]: Defend(+5blk)->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=0
  R3[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Dagger Spray+(12dmg)->Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Defend(+5blk) | dealt=29 taken=0

F14 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (4R, HP 56->53, loss=3, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Survivor(+8blk)->Abrasive(+6blk,power:+Dexterity(1),power:+Thorns(4))->Defend | dealt=0 taken=1
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Neutralize+(4dmg,1+Weak(2))->Backflip(+6blk)->Cloak and Dagger+(+7blk)->Dagger Spray+(6dmg)->Shiv(exhaust:1)->Shiv | dealt=10 taken=2
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(6)]: Strike->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0
  R4[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(3x3=9)]: Cloak and Dagger+(+7blk)->Predator+(12dmg,power:+Draw Cards Next Turn(2))->Shiv(power:-Well-Laid Plans,power:-Dexterity,power:-Thorns,power:-Draw Cards Next Turn) | dealt=12 taken=0

F15 [monster] Punch Construct (2R, HP 53->53, loss=0, WIN)
  R1[Punch Construct: Defend]: Neutralize+(4dmg,1-Artifact)->Bouncing Flask+(1+Poison(16))->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg) | dealt=12 taken=0
  R2[Punch Construct: Atk(14)]: Predator+(10dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=16 taken=0

F17 [boss] Soul Fysh (7R, HP 75->57, loss=18, WIN)
  R1[Soul Fysh: StatusCard(2)]: Bouncing Flask+(1+Poison(16))->Deadly Poison(1Poison(16→22)) | dealt=0 taken=0
  R2[Soul Fysh: Atk(16)]: Backflip(+5blk)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=20 taken=6
  R3[Soul Fysh: Atk(7), StatusCard(1)]: Neutralize+(4dmg,1+Weak(2))->Survivor(+8blk)->Dagger Spray+(12dmg)->Backflip(+5blk) | dealt=16 taken=6
  R4[Soul Fysh: Buff]: Survivor(+8blk)->Abrasive(+7blk,power:Thorns(3→7),power:+Dexterity(1))->Cloak and Dagger+(4dmg,exhaust:1)->Shiv(4dmg)->Shiv->Beckon | dealt=8 taken=0
  R5[Soul Fysh: Atk(11), Debuff]: Neutralize+(1dmg,1+Weak(2))->Backflip(+6blk)->Defend(+6blk)->Deadly Poison(1Poison(18→24)) | dealt=1 taken=0
  R6[Soul Fysh: StatusCard(2)]: Neutralize+(4dmg,1Weak(1→3))->Bouncing Flask+(1Poison(23→39))->Dagger Spray+(12dmg) | dealt=16 taken=0
  R7[Soul Fysh: Atk(18)]: Survivor(+9blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=6

F19 [monster] Tunneler (4R, HP 75->70, loss=5, WIN)
  R1[Tunneler: Atk(13)]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Backflip(+5blk)->Survivor(+8blk)->Abrasive(18dmg,power:Thorns(3→7),power:+Dexterity(1))->Dagger Spray+ | dealt=34 taken=0
  R2[Tunneler: Buff, Defend]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Deadly Poison(1+Poison(6)) | dealt=20 taken=0
  R3[Tunneler: Atk(23)]: Neutralize+(1+Weak(2))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=5
  R4[Tunneler: Atk(17)]: Bouncing Flask+(1Poison(4→20))->Defend(+6blk) | dealt=0 taken=0

F20 [monster] Thieving Hopper (3R, HP 70->63, loss=7, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Predator+(30dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=46 taken=7
  R2[Thieving Hopper: Buff]: Backflip(+5blk)->Bouncing Flask+(1+Poison(16)) | dealt=0 taken=0
  R3[Thieving Hopper: Atk(21)]: Neutralize+(2dmg,2Flutter(5→4),+Weak(2))->Survivor(+8blk)->Defend(+5blk)->Backflip(+5blk) | dealt=2 taken=0

F23 [monster] Hunter Killer (5R, HP 63->60, loss=3, WIN)
  R1[Hunter Killer: Debuff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Footwork(power:+Dexterity(2))->Neutralize+(6dmg,1+Weak(2))->Backflip(+7blk)->Cloak and Dagger(+8blk)->Shiv(6dmg,exhaust:1) | dealt=22 taken=0
  R2[Hunter Killer: Atk(5x3=15)]: Cloak and Dagger+(+8blk,power:Dexterity(2→1),power:+Strength(-1))->Backflip(+6blk,power:Strength(-1→-2),power:-Dexterity)->Shiv(2dmg,power:Strength(-2→-3),power:+Dexterity(-1))->Shiv(1dmg,power:Strength(-3→-4),power:Dexterity(-1→-2))->Well-Laid Plans+(power:Strength(-4→-5),power:Dexterity(-2→-3),power:+Well-Laid Plans(2)) | dealt=3 taken=1
  R3[Hunter Killer: Atk(17)]: Survivor(+10blk)->Abrasive(power:Thorns(3→7),power:+Strength(-3),power:-Dexterity,1+Poison(16))->Bouncing Flask+ | dealt=0 taken=2
  R4[Hunter Killer: Atk(5x3=15)]: Cloak and Dagger(+9blk,power:Dexterity(3→2),power:+Strength(-1))->Backflip(+7blk,power:Dexterity(2→1),power:Strength(-1→-2))->Deadly Poison(power:Strength(-2→-3),power:-Dexterity,1Poison(15→21))->Neutralize+(1dmg,power:Strength(-3→-4),power:+Dexterity(-1),1Weak(2→4))->Shiv(power:Strength(-4→-5),power:Dexterity(-1→-2)) | dealt=1 taken=0
  R5[Hunter Killer: Atk(12)]: Predator+(20dmg,power:Dexterity(3→2),power:+Draw Cards Next Turn(2),power:+Strength(-1))->Cloak and Dagger+(+8blk,power:Dexterity(2→1),power:Strength(-1→-2))->Shiv(power:-Thorns,power:-Tender,power:-Well-Laid Plans,power:-Dexterity,power:-Draw Cards Next Turn,power:-Strength) | dealt=20 taken=0

F30 [monster] Louse Progenitor (6R, HP 60->60, loss=0, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Well-Laid Plans(power:+Well-Laid Plans(1))->Assassinate(10dmg,2+Vulnerable(1),-Curl Up,exhaust:1)->Dagger Spray+(4dmg)->Cloak and Dagger+(+6blk)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Cloak and Dagger(+6blk)->Shiv(6dmg) | dealt=32 taken=0
  R2[Louse Progenitor: Defend, Buff]: Footwork+(power:+Dexterity(3))->Backflip+(+8blk)->Survivor(+8blk)->Abrasive | dealt=0 taken=0
  R3[Louse Progenitor: Atk(19)]: Neutralize+(1+Weak(2))->Backflip+(+9blk)->Backflip(+6blk)->Deadly Poison(1+Poison(6)) | dealt=0 taken=0
  R4[Louse Progenitor: Atk(10), Debuff]: Cloak and Dagger(+10blk)->Shiv(4dmg)->Cloak and Dagger+(+10blk)->Shiv(4dmg)->Shiv(4dmg) | dealt=12 taken=0
  R5[Louse Progenitor: Defend, Buff]: Neutralize+(4dmg,1+Weak(2))->Backflip+(+9blk)->Cloak and Dagger+(+7blk)->Shiv(4dmg)->Shiv(4dmg)->Deadly Poison(1Poison(4→10)) | dealt=12 taken=0
  R6[Louse Progenitor: Atk(18)]: Neutralize+(1Weak(1→3))->Predator+(10dmg,power:+Draw Cards Next Turn(2))->Dagger Spray+(power:-Thorns,power:-Well-Laid Plans,power:-Dexterity,power:-Frail,power:-Draw Cards Next Turn) | dealt=10 taken=0

F33 [boss] The Insatiable (10R, HP 60->31, loss=29, WIN)
  R1[The Insatiable: Buff, StatusCard(6)]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Footwork+(power:+Dexterity(3))->Well-Laid Plans(power:+Well-Laid Plans(1))->Survivor(+11blk)->Abrasive(18dmg,power:Thorns(3→7),power:Dexterity(3→4))->Dagger Spray+ | dealt=28 taken=0
  R2[The Insatiable: Atk(8x2=16)]: Neutralize+(4dmg,1+Weak(2))->Backflip(+9blk)->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=24 taken=3
  R3[The Insatiable: Atk(21)]: Prepared+->Backflip+(+12blk)->Cloak and Dagger(+10blk)->Shiv(4dmg,exhaust:1)->Frantic Escape(1Sandpit(3→4)) | dealt=4 taken=0
  R4[The Insatiable: Buff]: Backflip+(+12blk)->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=0
  R5[The Insatiable: Atk(10x2=20)]: Neutralize+(4dmg,1+Weak(2))->Cloak and Dagger(+10blk)->Shiv(4dmg)->Backflip+(+12blk)->Frantic Escape(1Sandpit(2→3)) | dealt=8 taken=0
  R6[The Insatiable: Atk(7x2=14)]: Bouncing Flask+(power:-Duplication,1+Poison(32))->Frantic Escape(1Sandpit(2→3))->Prepared+ | dealt=0 taken=14
  R7[The Insatiable: Atk(30)]: Backflip(+9blk)->Neutralize+(4dmg,1+Weak(2))->Defend(+9blk)->Defend(+9blk) | dealt=4 taken=0
  R8[The Insatiable: Buff]: Frantic Escape(1Sandpit(1→2))->Cloak and Dagger+(+10blk)->Shiv(4dmg)->Shiv(4dmg) | dealt=8 taken=0
  R9[The Insatiable: Atk(12x2=24)]: Frantic Escape(1Sandpit(1→2))->Prepared+->Piercing Wail(2Strength(4→-2),+Piercing Wail(6),exhaust:1)->Frantic Escape(1Sandpit(2→3)) | dealt=0 taken=12
  R10[The Insatiable: Atk(12x2=24)]: Deadly Poison(1Poison(28→34))->Backflip+(+12blk)->Defend(+9blk) | dealt=0 taken=0

F35 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (3R, HP 75->75, loss=0, WIN)
  R1[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff]: Assassinate(exhaust:1)->Assassinate(exhaust:1)->Footwork+(power:+Dexterity(3))->Prepared+->Abrasive->Neutralize+(+10blk)->Cloak and Dagger+(exhaust:1)->Shiv->Shiv(+12blk)->Backflip+(+9blk)->Defend | dealt=0 taken=0
  R2[Scroll of Biting: Atk(3x2=6)+Scroll of Biting: Atk(7x2=14)]: Piercing Wail(2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Backflip+(+12blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=0 taken=0
  R3[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(7x2=14)]: Backflip(+9blk)->Cloak and Dagger+(+10blk)->Shiv->Shiv(4dmg)->Shiv(4dmg,exhaust:1)->Deadly Poison(1+Poison(6)) | dealt=8 taken=0

F38 [monster] Devoted Sculptor (5R, HP 60->60, loss=0, WIN)
  R1[Devoted Sculptor: Buff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Assassinate(15dmg,1Vulnerable(1→2),exhaust:1)->Footwork+(power:+Dexterity(3))->Deadly Poison(1+Poison(6))->Backflip+(+11blk)->Backflip(+8blk) | dealt=25 taken=0
  R2[Devoted Sculptor: Atk(12)]: Neutralize+(6dmg,1+Weak(2))->Neutralize+(6dmg,1Weak(2→4))->Cloak and Dagger+(+9blk)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Bouncing Flask+(1Poison(5→21)) | dealt=24 taken=0
  R3[Devoted Sculptor: Atk(15)]: Backflip+(+11blk)->Cloak and Dagger(+9blk)->Shiv(4dmg)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Shiv(4dmg,exhaust:1) | dealt=8 taken=0
  R4[Devoted Sculptor: Atk(22)]: Prepared+->Abrasive(4dmg,1Weak(2→4))->Neutralize+(4dmg,1Weak(4→6))->Neutralize+(+10blk)->Cloak and Dagger(4dmg)->Shiv(1Poison(19→25))->Deadly Poison(+15blk)->Survivor+ | dealt=12 taken=0
  R5[Devoted Sculptor: Atk(29)]: Dagger Spray+(power:-Thorns,power:-Dexterity,power:-Well-Laid Plans) | dealt=0 taken=0

F43 [monster] Frog Knight (6R, HP 60->57, loss=3, WIN)
  R1[Frog Knight: Atk(13), Debuff]: Footwork+(power:+Dexterity(3))->Assassinate(1+Vulnerable(1),exhaust:1)->Assassinate(10dmg,1Vulnerable(1→2),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Deflect+(+10blk)->Predator+(30dmg,power:+Draw Cards Next Turn(2))->Deadly Poison(1+Poison(6)) | dealt=46 taken=0
  R2[Frog Knight: Atk(15)]: Backflip+(+8blk)->Backflip+(+8blk)->Prepared+->Abrasive(power:+Well-Laid Plans(1))->Well-Laid Plans | dealt=0 taken=0
  R3[Frog Knight: Buff]: Outbreak+(power:+Outbreak(15))->Bouncing Flask+(1dmg,1Poison(4→20))->Cloak and Dagger+(+7blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg) | dealt=9 taken=0
  R4[Frog Knight: Atk(18), Debuff]: Backflip+(+12blk)->Backflip+(+12blk)->Prepared+->Dagger Spray+ | dealt=0 taken=0
  R5[Frog Knight: Atk(26)]: Deflect+(+8blk)->Defend(+6blk)->Defend+(+9blk)->Deadly Poison(1Poison(18→24)) | dealt=0 taken=3
  R6[Frog Knight: Buff]: Bouncing Flask+(19dmg,1Poison(23→39)) | dealt=19 taken=0

F44 [monster] multi:The Forgotten+The Lost (7R, HP 57->38, loss=19, WIN)
  R1[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Neutralize+(4dmg,1+Weak(2))->Neutralize+(4dmg,1+Weak(2))->Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Bouncing Flask+(1+Poison(8),1+Poison(8))->Cloak and Dagger(+6blk)->Shiv(6dmg,exhaust:1)->Backflip+(+8blk) | dealt=24 taken=0
  R2[The Lost: Atk(4x2=8)+The Forgotten: Atk(11)]: Survivor+(+9blk)->Cloak and Dagger(+4blk)->Shiv(2dmg)->Shiv(2dmg,exhaust:1)->Cloak and Dagger+(+4blk)->Shiv(2dmg)->Shiv(2dmg)->Prepared+ | dealt=8 taken=2
  R3[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Backflip+(+6blk)->Deflect+(+5blk)->Backflip+(+6blk) | dealt=0 taken=0
  R4[The Lost: Atk(8x2=16)+The Forgotten: Atk(17)]: Abrasive(power:Thorns(3→7),power:Dexterity(-4→-3))->Neutralize+(1+Weak(2))->Neutralize+(1+Weak(2))->Deflect+(+4blk)->Cloak and Dagger(+3blk)->Shiv | dealt=0 taken=17
  R5[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Outbreak+(power:+Outbreak(15))->Neutralize+(1Weak(1→3))->Neutralize+(1Weak(3→5))->Bouncing Flask+(30dmg,1Poison(4→8),1Poison(4→16)) | dealt=30 taken=0
  R6[The Forgotten: Atk(14)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Backflip+(+3blk)->Survivor+(+6blk) | dealt=0 taken=0
  R7[The Forgotten: Debuff, Defend, Buff]: Prepared+ | dealt=0 taken=0

F45 [monster] multi:Cubex Construct+Cubex Construct+Punch Construct (5R, HP 38->22, loss=16, WIN)
  R1[Punch Construct: Defend+Cubex Construct: Buff+Cubex Construct: Buff]: Footwork+(power:+Dexterity(3))->Assassinate(exhaust:1)->Assassinate(10dmg,1-Artifact,exhaust:1)->Backflip+(+11blk)->Deflect+(+10blk)->Backflip+(+11blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=10 taken=0
  R2[Punch Construct: Atk(14)+Cubex Construct: Atk(9), Buff+Cubex Construct: Atk(9), Buff]: Cloak and Dagger+(+9blk)->Shiv(exhaust:1)->Shiv->Defend+(+11blk)->Outbreak+(power:+Outbreak(15)) | dealt=0 taken=12
  R3[Punch Construct: Atk(5x2=10), Debuff+Cubex Construct: Atk(11), Buff+Cubex Construct: Atk(11), Buff]: Neutralize+(4dmg,1-Artifact)->Neutralize+(4dmg,1+Weak(2))->Survivor+(+14blk)->Abrasive(+10blk,power:Thorns(3→7),power:Dexterity(3→4))->Cloak and Dagger(4dmg)->Shiv(24dmg)->Dagger Spray+ | dealt=36 taken=4
  R4[Punch Construct: Defend+Cubex Construct: Atk(11x2=22)+Cubex Construct: Atk(11x2=22)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Piercing Wail(6),-Strength,exhaust:1)->Backflip+(+12blk)->Cloak and Dagger+(+10blk)->Shiv(3dmg)->Shiv(3dmg) | dealt=6 taken=0
  R5[Punch Construct: Atk(14)+Cubex Construct: Atk(13), Buff+Cubex Construct: Atk(13), Buff]: Neutralize+->Neutralize+(4dmg,1+Weak(2))->Dagger Spray+(2dmg)->Prepared+->Neutralize+(4dmg,1+Weak(2))->Backflip+(+12blk)->Deflect+(+11blk)->Cloak and Dagger(+10blk)->Shiv(4dmg) | dealt=23 taken=0

F48 [boss] Door (12R, HP 44->9, loss=35, WIN)
  R1[Door: Summon]: Well-Laid Plans(power:+Well-Laid Plans(1))->Backflip+(+8blk) | dealt=0 taken=0
  R2[Doormaker: Atk(30)]: Outbreak+(power:+Outbreak(15))->Footwork+(power:+Dexterity(3))->Backflip+(+11blk,exhaust:1)->Backflip+(+11blk)->Prepared+->Abrasive | dealt=0 taken=8
  R3[Doormaker: Atk(24)]: Neutralize+(4dmg,1+Weak(2))->Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Neutralize+(6dmg,1Weak(2→4))->Bouncing Flask+(15dmg,1+Poison(16))->Bubble Bubble(1Poison(16→26))->Survivor+(+15blk) | dealt=35 taken=3
  R4[Doormaker: Atk(7x2=14), Buff]: Backflip+(+12blk)->Deflect+(+11blk) | dealt=0 taken=0
  R5[Doormaker: Atk(24)]: Defend+(+12blk,exhaust:1)->Cloak and Dagger+(+10blk,exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Dagger Spray+(12dmg,exhaust:1) | dealt=20 taken=2
  R6[Doormaker: Atk(20)]: Piercing Wail(2Strength(3→-3),+Piercing Wail(6),exhaust:1)->Defend(+9blk)->Deadly Poison(15dmg,1Poison(23→29)) | dealt=15 taken=6
  R7[Doormaker: Atk(13x2=26), Buff]: Neutralize+(4dmg,1+Weak(2))->Survivor+(+15blk)->Neutralize+(4dmg,1Weak(2→4)) | dealt=8 taken=3
  R8[Doormaker: Atk(27)]: Deflect+(+11blk,exhaust:1)->Backflip+(+12blk)->Cloak and Dagger(+10blk,exhaust:1)->Shiv(4dmg)->Neutralize+(4dmg,1Weak(3→5),exhaust:1)->Shiv(4dmg)->Defend(+9blk,exhaust:1) | dealt=12 taken=0
  R9[Doormaker: Atk(22)]: Cloak and Dagger(+10blk)->Shiv(4dmg)->Defend(+9blk)->Deadly Poison(1Poison(26→32))->Shiv(4dmg) | dealt=8 taken=3
  R10[Doormaker: Atk(12x2=24), Buff]: Survivor+(+15blk) | dealt=0 taken=9
  R11[Doormaker: Atk(29)]: Neutralize+(4dmg,1Weak(2→4))->Neutralize+(4dmg,1Weak(4→6))->Acrobatics->Cloak and Dagger(+10blk)->Shiv(4dmg)->Defend(+9blk)->Defend(+9blk) | dealt=12 taken=1
  R12[Doormaker: Atk(24)]: Bubble Bubble(1Poison(29→39))->Bouncing Flask+(30dmg,1Poison(39→55)) | dealt=30 taken=0

### Non-combat Decisions (191 decisions)
F1 [event] choose_event_option (option_index=2) | source=llm
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Silver Crucible provides a massive early tempo boost by upgrading the first 3 card rewards, which is extremely valuable for taking on Act 1 Elites. The loss of the first treasure chest is an acceptable trade-off for this early power spike.
  strategic_note: Foundation phase: relying on basic strikes and defends. Look for high-value early game damage and block cards to capitalize on Silver Crucible upgrades, enabling an aggressive elite-hunting path through Act 1.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 70->70 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Starting the Act 1 path with consecutive monster encounters to build a deck foundation before hitting shops or elites.
  strategic_note: Foundation phase: Prioritizing consecutive monster encounters early to draft essential damage and block cards, leveraging full health to stabilize the deck for future elites.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 99->114 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 114->114 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim potion: Fruit Juice

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 114->114 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 70->70 | Gold 114->114 | Deck 12->13
  deck_change: picked Predator+
  reasoning: Predator+ offers 20 upfront damage to immediately solve Act 1 elites like Gremlin Nob, and the card draw perfectly smooths out our hands on subsequent turns. Upgraded early thanks to Silver Crucible, this is an incredible power spike for Phase 1.
  strategic_note: Foundation plan: survive with frontload damage like Predator+ while looking for a core scaling engine; take cheap draw or high-impact block, skip narrow synergy pieces until an engine is found.

F2 [map] choose_map_node (option_index=0) | source=llm
  HP 70->70 | Gold 114->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Following the foundational strategy of taking 4 consecutive monster encounters to build deck strength before tackling elites and shops. Starting Act 1 with healthy HP allows for aggressive card drafting.
  strategic_note: Foundation phase: currently relying on basic cards. Prioritizing hallway fights to draft high-value early damage and block cards to leverage the Silver Crucible upgrades and prepare for upcoming Act 1 Elites.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 114->134 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 20 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 134->134 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 134->134 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 75->75 | Gold 134->134 | Deck 13->14
  deck_change: picked Cloak and Dagger+
  reasoning: Cloak and Dagger+ offers an extremely efficient 6 block and 8 damage for 1 energy, providing excellent generic offense and defense for the early game.
  strategic_note: Foundation phase: relying on basic attacks, Predator+, and efficient cards like Cloak and Dagger+. Focus on acquiring frontload damage and generic mitigation to survive Act 1 elites before committing to a specific scaling engine.

F3 [map] choose_map_node (option_index=0) | source=llm
  HP 75->75 | Gold 134->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended path to hit 4 consecutive monster nodes. This is the foundation phase where we need to draft immediate damage and block cards to prepare for elites later in the act.
  strategic_note: Foundation phase: focusing on drafting high-value frontloaded damage and defensive cards to leverage the Silver Crucible upgrades before the first Elite encounter.

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 134->150 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 150->150 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 75->75 | Gold 150->150 | Deck 14->15
  deck_change: picked Well-Laid Plans+
  reasoning: Well-Laid Plans+ is a top-tier utility power that provides massive consistency, allowing us to hold key defensive cards or Predator+ across turns. This is a crucial piece for any future engine and too strong to pass up, especially already upgraded.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a core scaling engine; take cheap draw or high-impact damage, and utilize Well-Laid Plans to smooth out hands.

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 75->75 | Gold 150->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 150->163 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 163->163 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 75->75 | Gold 163->163 | Deck 15->16
  deck_change: picked Bouncing Flask
  reasoning: Bouncing Flask gives us excellent scaling damage against elites and the upcoming Act 1 boss (Soul Fysh), whose Intangible buff is bypassed by poison. This serves as a strong potential core engine piece.
  strategic_note: Foundation phase shifting to Poison engine. Rely on Predator+ for frontload and Bouncing Flask for boss scaling. Use WLP+ to retain key cards for the right turns. Look for poison synergy and efficient block.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 75->75 | Gold 163->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 163->180 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 180->180 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 65->65 | Gold 180->180 | Deck 16->16
  deck_change: no deck change
  reasoning: The deck already has solid early damage with Predator+ and Bouncing Flask. None of these common cards significantly improve our output or survivability, and skipping keeps our deck lean to draw our key cards more often.
  strategic_note: Foundation plan: survive with frontload (Predator+) and efficient block while looking for a core scaling engine (preferably poison, given Bouncing Flask). Take cheap draw or high-impact defense, skip mediocre commons.

F6 [map] choose_map_node (option_index=1) | source=llm
  HP 65->65 | Gold 180->180 | Deck 16->16
  deck_change: no deck change
  reasoning: Following the route to a Rest Site. With 180 gold and 65 HP, I am in a strong position. I will likely Smith to upgrade a key card, as my health is high and I need to prepare for the upcoming Elite fight. Upgrading now maximizes the value of the 'Silver Crucible' start.
  strategic_note: Foundation phase: leveraging high health and early gold to upgrade key damage/block cards at rest sites. Preparing for mid-act Elites by focusing on card quality over quantity, seeking efficient front-loaded damage to minimize HP loss in upcoming races.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=10, note_scope=run, note_triggers=all) | source=llm
  HP 65->65 | Gold 180->180 | Deck 16->16
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With 65/75 HP, we are healthy enough to Smith before the Elite. Upgrading Neutralize to apply 2 turns of Weak fundamentally alters its duration and provides immense damage mitigation, perfectly synergizing with Well-Laid Plans to hold it for crucial attack turns.
  strategic_note: Foundation phase: leveraging Neutralize+, Predator+, and Bouncing Flask for early Elite hunting. Use Well-Laid Plans to retain key cards like Neutralize for heavy attacks or Bouncing Flask for optimal scaling windows. Prioritize removing strikes to improve consistency.

F7 [rest_site] proceed | source=auto
  HP 65->65 | Gold 180->180 | Deck 16->16
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 65->65 | Gold 180->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Elite

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 180->225 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 45 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 225->225 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Potion of Binding

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 225->225 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim relic: Snecko Skull

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 225->225 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 58->58 | Gold 225->225 | Deck 16->17
  deck_change: picked Dagger Spray
  reasoning: Dagger Spray provides much-needed AoE damage for early hallway fights and elites, filling a gap in our current single-target focused deck (Predator, Bouncing Flask). We are building towards a Poison engine with Snecko Skull.
  strategic_note: Committed to Poison plan with Snecko Skull + Bouncing Flask. Focus on acquiring more poison, mitigation, and draw. Keep the deck lean and remove basic attacks.

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: upgraded Dagger Spray->Dagger Spray+
  reasoning: We are at 58/75 HP, which is plenty to survive upcoming hallway fights, so Smithing is clearly better than Healing. Upgrading Dagger Spray gives a 50% damage boost to our only AoE card, securing F11 against potential multi-enemy fights. We can upgrade Bouncing Flask at the F12 rest site right before the F14 Elite.
  strategic_note: Foundation phase: relying on Predator+ for frontload and Well-Laid Plans to retain key answers. Prioritize upgrading scaling and AoE damage to breeze through Act 1 Elites, using Dagger Spray for AoE and Bouncing Flask for single-target scaling.

F9 [rest_site] proceed | source=auto
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] proceed | source=random
  HP 58->58 | Gold 225->225 | Deck 17->17
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 225->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 225->235 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 235->235 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 235->235 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 56->56 | Gold 235->235 | Deck 17->18
  deck_change: picked Abrasive
  reasoning: Abrasive is a Rare power that scales our defense (Dexterity) and adds passive damage (Thorns). With Well-Laid Plans+ already in the deck to retain it, and Survivor to discard it, we can consistently trigger its Sly mechanic to play a 3-cost power for free.
  strategic_note: Poison engine committed: use Bouncing Flask + Snecko Skull to stack poison, then turtle. Retain Abrasive with Well-Laid Plans until Survivor is drawn to play it for free via Sly. Prioritize deck thinning, defensive scaling, and heavy draw next.

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 56->56 | Gold 235->235 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the established route. I have 235 gold and need a shop (next floor) to convert that into power before taking on the Act 1 Elite. Resting or upgrading here at the campfire provides a necessary buffer for the upcoming Elite and Boss sequence, especially given the current HP (75%).
  strategic_note: Foundation phase: relying on basic strikes and defends. Prioritize high-value frontloaded damage and block to maximize Silver Crucible's value while targeting a late Act 1 Elite and Shop for scaling.

F12 [rest_site] choose_rest_option (option_index=1, smith_card_index=11) | source=llm
  HP 56->56 | Gold 235->235 | Deck 18->18
  deck_change: upgraded Bouncing Flask->Bouncing Flask+
  reasoning: At 56 HP we are healthy enough to path through a Shop and an Elite, especially since we have another rest site at F16 before the boss. Upgrading Bouncing Flask increases its poison output from 9 to 12, significantly improving our single-target scaling for the upcoming Elite and Boss fights.
  strategic_note: Foundation phase: relying on Predator+ for frontload and Well-Laid Plans to retain key answers. We have strong AoE and scaling now, so look to prioritize card draw, discard enablers for Abrasive, and defensive consistency while removing basic strikes.

F12 [rest_site] proceed | source=auto
  HP 56->56 | Gold 235->235 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 235->235 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Shop

F13 [shop] remove_card_at_shop | source=plan
  HP 56->56 | Gold 235->235 | Deck 18->18
  deck_change: no deck change
  reasoning: Shop plan [1/2]: Removing a basic Strike improves consistency and lets us draw our strong cards like Bouncing Flask+ and Predator+ more frequently.

F13 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->56 | Gold 235->160 | Deck 18->17
  deck_change: lost Strike
  reasoning: Basic attacks are dead weight in a deck that scales through poison (Bouncing Flask+ with Snecko Skull) and needs to draw into defensive cards and Abrasive. Removing a Strike improves consistency.
  strategic_note: Committed poison plan: use Snecko Skull and Bouncing Flask+ for damage, stall with defense and Weak. Use Survivor to discard Abrasive for free scaling. Needs more discard outlets and efficient block; continue removing Strikes.

F13 [shop] buy_card (option_index=2) | source=plan
  HP 56->56 | Gold 160->110 | Deck 17->18
  deck_change: bought Backflip
  reasoning: Shop plan [2/2]: A premium defensive tool that cycles the deck, finding our poison engine or WLP faster while providing decent block.

F13 [shop] close_shop_inventory | source=plan
  HP 56->56 | Gold 110->110 | Deck 18->18
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F13 [shop] proceed | source=auto
  HP 56->56 | Gold 110->110 | Deck 18->18
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 110->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Elite

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 110->145 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 35 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 145->145 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim relic: Bronze Scales

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 145->145 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 53->53 | Gold 145->145 | Deck 18->19
  deck_change: picked Deadly Poison
  reasoning: Deadly Poison provides cheap, targeted poison application that is heavily amplified by our Snecko Skull relic. It allows us to stack poison on priority targets and deal damage to the Act 1 Boss even while it is Intangible.
  strategic_note: Committed poison plan: stack poison with Bouncing Flask and Deadly Poison, amplified by Snecko Skull. Use Well-Laid Plans to hold key block cards or Abrasive for Sly triggers. Looking for defensive scaling, AoE mitigation, and draw. Avoid generic attacks.

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 145->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 145->155 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 155->155 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 155->155 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 53->53 | Gold 155->155 | Deck 19->20
  deck_change: picked Backflip
  reasoning: Backflip provides block and draw, which are essential for a poison deck to cycle through the deck, find poison cards, and survive while poison ticks down. It also helps mitigate the impact of status cards from the upcoming boss.
  strategic_note: Committed to poison scaling with Snecko Skull, Bouncing Flask, and Deadly Poison. Prioritize card draw and block to survive while poison kills. Avoid narrow or off-plan attacks.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 155->155 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 53->75 | Gold 155->155 | Deck 20->20
  deck_change: no deck change
  reasoning: Our primary damage engine relies on slow-scaling poison (Bouncing Flask+, Deadly Poison) and thorns, meaning we will likely take chip damage while setting up against the Act 1 Boss. Healing to full HP provides the necessary buffer to survive the setup phase.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks like Backflip and Survivor. Sly out Abrasive if possible using Survivor. Needs more block scaling or card draw; avoid raw un-upgraded attacks.

F16 [rest_site] proceed | source=auto
  HP 75->75 | Gold 155->155 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 75->75 | Gold 155->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 155->255 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 255->255 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 255->255 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 57->57 | Gold 255->255 | Deck 20->21
  deck_change: picked Assassinate
  reasoning: Assassinate provides 0-cost upfront damage and Vulnerable, which pairs excellently with Predator+ on Turn 1 to eliminate a priority target in Act 2 hallway fights. It exhausts immediately, keeping the deck lean for our poison scaling in longer fights.
  strategic_note: Committed to poison scaling with Snecko Skull, Bouncing Flask, and Deadly Poison. Use upfront damage (Predator, Assassinate) for early kills in hallways, then block and let poison tick. Need more defensive tools and cycle; skip off-plan attacks.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 57->75 | Gold 255->255 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 75->75 | Gold 255->255 | Deck 21->21
  deck_change: no deck change
  reasoning: Removing 4 cards (all 4 basic Strikes) from a 21-card deck drastically improves the consistency of drawing our key poison and block cards. The downside of adding a single Soot on shuffle is vastly outweighed by not drawing those 4 Strikes over the course of the combat.
  strategic_note: Committed poison/defensive plan: cycle through blocks and poison with Bouncing Flask+ and Deadly Poison. Use Survivor to discard Abrasive if it can't be played. Since we just removed our Strikes, we rely entirely on our engine to output damage.

F18 [card_select] select_deck_card (option_index=0) | source=llm
  HP 75->75 | Gold 255->255 | Deck 21->17
  deck_change: lost Strike x4
  reasoning: With Biiig Hug, I need to remove 4 cards. Since my scaling damage is fully committed to Poison (Bouncing Flask+, Deadly Poison, Snecko Skull) and I have better frontload (Predator+, Dagger Spray+), the basic Strikes are completely dead weight. Removing all 4 Strikes dramatically improves the deck's draw consistency and defensive reliability.
  strategic_note: Committed poison plan: rely on Snecko Skull + Bouncing Flask+/Deadly Poison for damage. Defend heavily while passive poison scales. Use Survivor to Sly Abrasive for Dexterity and Thorns. Avoid adding more generic attacks; look for Nightmare, Catalyst (if it exists), or premium block/draw to outlast enemies while they melt.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 75->75 | Gold 255->255 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 75->75 | Gold 255->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the recommended route to a standard Monster encounter. I have full HP and 255 gold, so I need to fight early Act 2 hallway enemies to see if my deck can handle the increased damage output before hitting the mid-act shop. The Silver Crucible provides some value but I need to find a cohesive engine (Poison or Shivs) soon.
  strategic_note: Foundation phase: relying on basic strikes and defends with Silver Crucible for value. Prioritizing early Act 2 hallway fights to test defensive consistency and fish for a scaling engine like poison or shivs before the mid-act shop.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 255->270 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 270->270 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 70->70 | Gold 270->270 | Deck 17->18
  deck_change: picked Backflip
  reasoning: Backflip provides draw and block, allowing us to cycle to our core poison cards (Bouncing Flask+) while staying alive. It's a premium common that scales well with Dexterity if we trigger Abrasive.
  strategic_note: Committed poison plan: survive with efficient block and draw while Bouncing Flask scales rapidly via Snecko Skull. Find a way to trigger Abrasive or gain more energy/discard.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 270->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 270->280 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F20 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 63->63 | Gold 280->280 | Deck 17->18
  deck_change: picked Well-Laid Plans+
  reasoning: Claim specialcard: Take your stolen card back.

F20 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 63->63 | Gold 280->280 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 63->63 | Gold 280->280 | Deck 18->18
  deck_change: no deck change
  reasoning: Our deck is currently very lean (18 cards) with an established, highly-effective poison engine (Snecko Skull + Bouncing Flask+). Bullet Time is tempting with Well-Laid Plans and expensive cards, but on 3 energy it prevents us from playing our draw cards (Backflip) on the same turn, making it clunky. Keeping the deck small maximizes the frequency we draw Bouncing Flask, Well-Laid Plans, and Survivor to trigger Abrasive.
  strategic_note: Committed poison plan: survive with efficient block and draw while Bouncing Flask scales rapidly via Snecko Skull. Cycle aggressively to find Flask and defensive tools, using Well-Laid Plans to hold the right pieces. Need more draw, poison synergy, and card removals; skip generic attacks and off-plan mechanics.

F20 [map] choose_map_node (option_index=0) | source=llm
  HP 63->63 | Gold 280->280 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which prioritizes non-combat nodes and Unknowns to preserve HP. With 280 gold, I am well-positioned for the upcoming Shop at Floor 22. My current deck relies on slow poison scaling, making standard Act 2 hallway fights risky for chip damage.
  strategic_note: Committed poison/defensive plan: use Bouncing Flask+ and Deadly Poison for damage while cycling blocks like Backflip and Survivor. Needs more block scaling or card draw; avoid raw un-upgraded attacks and prioritize HP preservation through non-combat nodes.

F21 [event] proceed | source=auto
  HP 63->63 | Gold 280->280 | Deck 18->18
  deck_change: no deck change
  reasoning: Event finished, proceed

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 63->63 | Gold 280->280 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Shop

F22 [shop] buy_card (option_index=4) | source=plan
  HP 63->63 | Gold 280->205 | Deck 18->19
  deck_change: bought Footwork
  reasoning: Shop plan [1/5]: Premium defensive scaling that works perfectly with our 3x Backflip and remaining Defends.

F22 [shop] remove_card_at_shop | source=plan
  HP 63->63 | Gold 205->205 | Deck 19->19
  deck_change: no deck change
  reasoning: Shop plan [2/5]: Removing a basic Defend to improve our draw consistency.

F22 [card_select] select_deck_card (option_index=0) | source=llm
  HP 63->63 | Gold 205->105 | Deck 19->18
  deck_change: lost Defend
  reasoning: With all Strikes already removed, Defend is the weakest generic card in the deck. We have plenty of Backflips, Survivor, and Cloak and Dagger for block, and Footwork/Abrasive to scale them. Removing a Defend increases our density of draw and poison cards.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Need more targeted discard to bypass Abrasive's cost and manage Soot from Biiig Hug; avoid generic attacks.

F22 [shop] discard_potion (option_index=1) | source=plan
  HP 63->63 | Gold 105->105 | Deck 18->18
  deck_change: no deck change
  reasoning: Shop plan: discard Weak Potion

F22 [shop] buy_potion (option_index=2) | source=plan
  HP 63->63 | Gold 105->32 | Deck 18->18
  deck_change: no deck change
  reasoning: Shop plan [4/5]: Adds 9 non-decaying damage per turn. Incredible against the Act 2 boss which is a strict DPS race.

F22 [shop] buy_card (option_index=2) | source=plan
  HP 63->63 | Gold 32->6 | Deck 18->19
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [5/5]: On sale, provides cheap block that benefits from Footwork, and a Shiv for chip damage.

F22 [shop] close_shop_inventory | source=plan
  HP 63->63 | Gold 6->6 | Deck 19->19
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F22 [shop] proceed | source=auto
  HP 63->63 | Gold 6->6 | Deck 19->19
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 63->63 | Gold 6->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 6->24 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 24->24 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 24->24 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 60->60 | Gold 24->24 | Deck 19->20
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a premium defensive tool against multi-attacks. It synergizes perfectly with our Well-Laid Plans+, allowing us to hold it until a dangerous multi-attack turn. This buys the critical time needed for our passive poison damage (buffed by Snecko Skull) to scale up and kill enemies.
  strategic_note: Committed poison plan: retain key defensive and poison cards with WLP, stack poison safely, and survive with Footwork and Piercing Wail while passive damage scales. Avoid off-plan attacks. Need more dedicated poison tools (like Catalyst) or reliable block.

F23 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the Route Intelligence and current state. The route guide for Act 2 emphasizes avoiding monsters and prioritizing Rest Sites for survival. My current health is 80%, which is decent, but the route recommends the Rest Site at c6,r6 to minimize risk. I have no need for a hallway fight right now given my low gold and the fact that I've already secured my core poison pieces (Bouncing Flask+, Deadly Poison). Upgrading or resting here is safer than a monster encounter.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks like Backflip and Survivor. Needs more block scaling or card draw; prioritize upgrades that increase defensive efficiency or poison stacks.

F24 [rest_site] choose_rest_option (option_index=1, smith_card_index=11) | source=llm
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: upgraded Footwork->Footwork+
  reasoning: With 60/75 HP and three more rest sites before the Act 2 Boss, smithing is the obvious choice. Upgrading Footwork from 2 to 3 Dexterity permanently improves our defensive scaling, which synergizes perfectly with our multiple Backflips, Defends, and Cloak and Daggers.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Sly out Abrasive using Survivor. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.

F24 [rest_site] proceed | source=auto
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F24 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the Route Intelligence and current deck status, avoiding Act 2 Elites is a high priority. The deck relies on poison ramp-up which is vulnerable to the burst damage typical of Act 2 Elites like Slavers or Book of Stabbing. Choosing the Unknown node aligns with the risk-averse strategy aimed at reaching the Act 2 boss with high HP.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for scaling damage while using Survivor and Defends to stall. Avoid Act 2 Elites at all costs due to slow setup speed; prioritize pathing through Unknowns and Rest Sites to preserve HP for the boss.

F25 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing) | source=llm
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Taking 3 Foul Potions gives us the opportunity to throw them at the upcoming F31 Merchant for 100 Gold each (300 Gold total). We only have Unknowns and Rest Sites before the Shop, so carrying them shouldn't be a problem and the massive gold injection right before the Act 2 Boss will be incredibly valuable.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for scaling damage while using Survivor and Defends to stall. Carry Foul potions to the shop for a massive gold payout.

F25 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F25 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 24->24 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 60->60 | Gold 24->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Lantern

F26 [treasure] proceed | source=random
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the Route Intelligence and current strategic thread. Act 2 in this run data is extremely hostile; prioritizing Rest Sites over Unknown nodes (which could result in a combat) is the safest path to the boss. Although my HP is relatively high at 80%, a Smith upgrade on a defensive or poison card further solidifies the engine.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage while cycling blocks with Footwork+ active. Prioritize Rest Sites to Smith core cards and avoid unnecessary Act 2 combats. Needs Catalyst or additional draw; avoid adding un-upgraded raw attacks.

F27 [rest_site] choose_rest_option (option_index=1, smith_card_index=6) | source=llm
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: upgraded Backflip->Backflip+
  reasoning: HP is high (60/75), so we Smith. Backflip is our primary draw engine, and upgrading it increases its block from 5 to 8, which scales well with Footwork+ and makes our defensive cycling much more efficient.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Sly out Abrasive using Survivor. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.

F27 [rest_site] proceed | source=auto
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 69->69 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the established optimal route for Act 2 which prioritizes risk-free nodes (Unknowns/Rest Sites) over Elites. Given the 'Route Intelligence' warning that Act 2 Elites and high-risk encounters lead to failure, the Unknown node is the safest path to preserve HP for the boss.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Currently prioritizing survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, as the deck's setup is slow and vulnerable to the high burst damage of Act 2 Elites.

F28 [event] choose_event_option (option_index=0) | source=llm
  HP 60->60 | Gold 69->69 | Deck 20->21
  deck_change: added Well-Laid Plans
  reasoning: Random Power gives a higher ceiling for my poison/defensive scaling strategy. Most Silent powers are highly beneficial or at least exhaust upon use, whereas random 0-cost cards often clog the deck in longer fights.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Continue to prioritize survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, relying on Well-Laid Plans to set up safe scaling turns.

F28 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 69->69 | Deck 21->21
  deck_change: no deck change
  reasoning: Only option: Proceed

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 69->69 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: RestSite

F29 [rest_site] choose_rest_option (option_index=1, smith_card_index=7, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 69->69 | Deck 21->21
  deck_change: upgraded Backflip->Backflip+
  reasoning: At 60/75 HP with another Rest Site before the boss, upgrading is much better than healing. Upgrading Backflip improves our block density significantly while keeping our engine cycling safely, which fits our defensive poison strategy.
  strategic_note: Committed poison/defensive plan: rely on Bouncing Flask+ and Deadly Poison for damage, playing them on safe turns, while cycling through blocks with Footwork+ active. Needs more card draw or a catalyst; avoid raw un-upgraded attacks.

F29 [rest_site] proceed | source=auto
  HP 60->60 | Gold 69->69 | Deck 21->21
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 69->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Following the established route intelligence which strongly advises avoiding Act 2 Elites. My current deck relies on slow poison scaling and lacks the burst/defensive speed required to handle Act 2 Elites safely. The Unknown node provides a safer path toward the Act 2 boss, preserving HP for the final encounter.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Currently prioritizing survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, as the deck's setup is slow and vulnerable to the high burst damage of Act 2 Elites.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 69->88 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 19 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 88->88 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Duplicator

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 88->88 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 60->60 | Gold 88->88 | Deck 21->22
  deck_change: picked Prepared
  reasoning: Prepared is a 0-cost hand cycle that provides targeted discard. This perfectly matches our need to discard Soot generated by Biiig Hug and trigger Abrasive's Sly effect for free Dexterity and Thorns.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling defensively with Footwork and Abrasive. Use Prepared and Survivor to discard Abrasive for free triggers or to pitch Soot. Need more card draw and perhaps one more poison source.

F30 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 88->88 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the Route Intelligence and current health strategy. The Shop node (c6, r13) is the recommended path, and while the Route Intelligence suggests shops can be traps, I have 88 gold which might afford a crucial common relic or a cheap defensive card/potion. More importantly, it avoids a potentially dangerous late Act 2 Monster combat (c5, r13) which aligns with the goal of HP preservation before the boss.
  strategic_note: Committed poison plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Continue to prioritize survival and pathing through non-combat nodes to reach the Act 2 boss with maximum HP, relying on Well-Laid Plans to set up safe scaling turns.

F31 [shop] buy_card (option_index=4) | source=plan
  HP 60->60 | Gold 88->14 | Deck 22->23
  deck_change: bought Outbreak
  reasoning: Shop plan [1/1]: Provides a massive AoE damage engine that triggers exceptionally well with Bouncing Flask+ and Snecko Skull, completing our poison strategy's AoE weakness.

F31 [shop] close_shop_inventory | source=plan
  HP 60->60 | Gold 14->14 | Deck 23->23
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F31 [shop] proceed | source=auto
  HP 60->60 | Gold 14->14 | Deck 23->23
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 14->14 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=12, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 14->14 | Deck 23->23
  deck_change: upgraded Prepared->Prepared+
  reasoning: We are only missing 15 HP, so healing is largely wasted. Upgrading Prepared to Prepared+ dramatically improves our deck cycling and gives us a highly reliable way to trigger Abrasive's Sly effect for free Dexterity and Thorns.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.

F32 [rest_site] proceed | source=auto
  HP 60->60 | Gold 14->14 | Deck 23->23
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 14->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 14->114 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 114->114 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 31->31 | Gold 114->114 | Deck 23->23
  deck_change: no deck change
  reasoning: We already have one Abrasive and only two discard outlets (Survivor, Prepared+). While we have Well-Laid Plans to hold them, a second 3-cost Sly card risks bricking our hand, especially against the upcoming Insatiable boss which shuffles 6 statuses into our deck on turn 1. Skipping keeps our deck lean to cycle back to our core poison cards (Bouncing Flask+, Deadly Poison) and existing defensive scaling.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Need more targeted discard to bypass Abrasive's cost and manage Soot from Biiig Hug; avoid generic attacks and clunky cards.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 31->75 | Gold 114->114 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 75->75 | Gold 114->114 | Deck 23->23
  deck_change: no deck change
  reasoning: Music Box has zero downsides and excellent synergy with our 0-cost attacks like Neutralize+ (for massive Weak application) and Shivs from Cloak and Dagger. Preserved Fog is tempting for deck thinning, but Folly clogs turn 1 and we shuffle quite frequently already due to Biiig Hug, making deck thinning slightly less valuable.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 75->75 | Gold 114->114 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 75->75 | Gold 114->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route towards the Act 2 boss. While the route intelligence suggests avoiding monsters, early hallway fights in Act 2 are necessary to test the defensive consistency of the poison engine and potentially draft missing block or utility pieces while at full HP.
  strategic_note: Committed poison plan: stall with block while poison scales, using Well-Laid Plans to coordinate defensive turns. Prioritize high-value block cards and poison acceleration to minimize chip damage before the boss.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 114->124 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 75->75 | Gold 124->124 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 75->75 | Gold 124->124 | Deck 23->23
  deck_change: no deck change
  reasoning: The deck is firmly committed to Poison scaling with Snecko Skull and Dexterity block. Blade Dance+ and Infinite Blades+ offer irrelevant Shiv damage, while Tactician is clunky with only two discard outlets. Skipping keeps the deck lean to cycle Bouncing Flask+ and defensive pieces faster.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Use Prepared+ and Survivor to discard Abrasive and Soots; avoid generic attacks and clunky additions.

F35 [map] choose_map_node (option_index=0) | source=llm
  HP 75->75 | Gold 124->124 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route towards an Unknown node. At full HP, I want to preserve resources for the Act 3 boss while seeking events that might provide further scaling or deck thinners. Avoiding the hallway monster to minimize chip damage as I already have a functional poison engine.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.

F36 [event] choose_event_option (option_index=1) | source=llm
  HP 75->60 | Gold 124->124 | Deck 23->23
  deck_change: upgraded Defend->Defend+, Survivor->Survivor+
  reasoning: Our turn 1 card draw is incredibly valuable for finding our key powers (Footwork, Well-Laid Plans, Outbreak) and block early. Losing 2 draw on turn 1 from Big Mushroom is not worth 20 Max HP. Since we are at full health (75/75), trading 15 HP for two random upgrades from Fragrant Mushroom is easily the better choice.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 124->124 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 124->124 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to the shop. With 124 gold, I can potentially afford a key utility relic, a strong block card (e.g., Leg Sweep or Footwork), or a card removal to trim the deck for better poison/Abrasive cycling. The alternative Unknown node is more volatile, and stabilizing at a shop before the upcoming Rest Site sequence is safer for this poison-stall engine.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Use Prepared+ and Survivor to trigger Abrasive for dex. Prioritize card draw, mitigation, and thin the deck at shops to cycle poison faster.

F37 [shop] buy_potion (option_index=2) | source=plan
  HP 60->60 | Gold 124->24 | Deck 23->23
  deck_change: no deck change
  reasoning: Shop plan [1/2]: Premium insurance policy for the Act 3 Boss and elites, providing a free revive if we fail to mitigate a massive hit.

F37 [shop] buy_card (option_index=2) | source=plan
  HP 60->60 | Gold 24->0 | Deck 23->24
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [2/2]: On sale and scales incredibly well with our Dexterity generators (Footwork+, Abrasive), acting as an efficient 1-cost block.

F37 [shop] close_shop_inventory | source=plan
  HP 60->60 | Gold 0->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F37 [shop] proceed | source=auto
  HP 60->60 | Gold 0->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F37 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 0->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With 0 gold, a shop is useless, and my HP is relatively stable (80%) but needs to stay that way for the Act 3 boss. Unknown nodes offer the best chance for non-combat survival or beneficial events while avoiding unnecessary chip damage from standard monsters in Act 3.
  strategic_note: Committed poison/defensive plan: stall with block while Bouncing Flask+ and Deadly Poison scale. Outbreak adds AoE. Use Prepared+ and Survivor to trigger Abrasive for free Dex. Prioritize card draw and mitigation.

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 0->20 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 20 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 20->20 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 60->60 | Gold 20->20 | Deck 24->25
  deck_change: picked Deflect+
  reasoning: Deflect+ is a 0-energy block card that scales incredibly well with our Footwork+ and Abrasive. With 2x Well-Laid Plans, we can easily retain it for turns when we need extra mitigation without spending energy, allowing us to survive while passive poison damage does the work.
  strategic_note: Committed poison plan: retain defensive and poison pieces, stack poison with Bouncing Flask and Snecko Skull, and survive using efficient block and Dexterity. Skip off-plan attacks and focus on draw/mitigation.

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Unknown

F39 [shop] close_shop_inventory | source=llm
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F39 [shop] proceed | source=auto
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: RestSite

F40 [rest_site] choose_rest_option (option_index=1, smith_card_index=10, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: upgraded Outbreak->Outbreak+
  reasoning: With 60/75 HP and another rest site immediately after the upcoming Treasure room, we are entirely safe to Smith. Upgrading Outbreak increases its AoE damage from 11 to 15 per trigger, which provides a massive boost to our damage output in Act 3 multi-enemy fights.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Outbreak provides AoE clearing.

F40 [rest_site] proceed | source=auto
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 20->20 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 60->60 | Gold 20->65 | Deck 25->25
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 60->60 | Gold 65->65 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim: Art of War

F41 [treasure] proceed | source=random
  HP 60->60 | Gold 65->65 | Deck 25->25
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=1) | source=llm
  HP 60->60 | Gold 65->65 | Deck 25->25
  deck_change: no deck change
  reasoning: Following the Route Intelligence and Strategic Thread which prioritize stability and survival over aggressive Elite hunting in Act 3. At 60 HP, I need to preserve my health and use Rest Sites to either upgrade key defensive pieces or ensure I am topped off for the Boss. The Elite at this stage is too risky for a deck that relies on slow-scaling poison.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.

F42 [rest_site] choose_rest_option (option_index=1, smith_card_index=6, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 65->65 | Deck 25->25
  deck_change: upgraded Backflip->Backflip+
  reasoning: With 60/75 HP, we are healthy enough to Smith before the upcoming Act 3 combats. Upgrading Backflip improves our core defensive/draw engine, increasing its block from 5 to 8, which scales well with our Footwork and Abrasive Dexterity.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity.

F42 [rest_site] proceed | source=auto
  HP 60->60 | Gold 65->65 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 65->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Monster

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 65->81 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 81->81 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 57->57 | Gold 81->81 | Deck 25->25
  deck_change: no deck change
  reasoning: The deck is fully committed to a Poison strategy with Dexterity block scaling. None of the options (Accuracy, Memento Mori+, Cloak and Dagger) support this engine, and taking them would dilute the draw pool for key cards like Bouncing Flask, Outbreak, and Footwork. Skipping keeps the deck lean for the upcoming Act 3 boss.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask and Deadly Poison while scaling block with Dexterity (Footwork, Abrasive). Retain key cards with Well-Laid Plans. Need targeted discard to bypass Abrasive's cost; avoid generic attacks and distractions.

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 57->57 | Gold 81->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Monster

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 81->91 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 91->91 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F44 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 38->38 | Gold 91->91 | Deck 25->26
  deck_change: picked Bubble Bubble
  reasoning: Bubble Bubble is a massive payload for our poison engine, especially with Snecko Skull making it apply 10 poison for 1 energy. We have two copies of Well-Laid Plans to easily retain it until we draw our poison enablers (Bouncing Flask+ or Deadly Poison), providing the raw damage needed to burn down Act 3 bosses.
  strategic_note: Committed poison plan: use Snecko Skull to stack poison rapidly with Bouncing Flask and Deadly Poison, retaining Bubble Bubble with WLP for a massive burst. Defend with Footwork-scaled block. Needs defensive consistency; avoid off-plan attacks.

F44 [map] choose_map_node (option_index=0) | source=llm
  HP 38->38 | Gold 91->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the established route to avoid Elites. At 38 HP, taking an Elite fight (especially Repto or Giant Head) is too risky for a poison deck that requires setup time. The Monster node provides a safer path to the final Rest Site before the boss.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity while seeking more draw and mitigation.

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 91->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 106->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Clarity Extract

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 106->106 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 22->22 | Gold 106->106 | Deck 26->27
  deck_change: picked Acrobatics
  reasoning: Our deck has a committed Poison engine and defensive scaling with Footwork and Abrasive. We currently only have Survivor and Prepared as discard outlets for Abrasive, so Acrobatics significantly improves our consistency by providing premium card draw to find our key powers and a targeted discard to trigger Sly mechanics.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Use Acrobatics/Prepared to trigger Abrasive or dig for Footwork/Outbreak. Needs Nightmare or Apparitions; skip off-plan attacks.

F45 [map] choose_map_node (option_index=0) | source=llm
  HP 22->22 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: With only 22 HP and 106 gold, a Shop (option 1) is high risk with low reward. The route's recommendation for the Unknown node (option 0) provides a chance for a non-combat encounter or event to preserve health before the mandatory rest site and boss fight.
  strategic_note: Committed poison/defensive plan: stall with high block while poison scales; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Prioritizing health preservation and campfires over high-risk elites or low-value shops to reach the boss with enough HP.

F46 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 22->22 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Enchanting a Power with Swift 2 is highly valuable, as our powers (Footwork+, Outbreak+, Well-Laid Plans) are key to our engine and drawing 2 cards upon playing one helps recover the tempo loss of playing a power.
  strategic_note: Committed poison/defensive plan: stall with high block while poison scales; use Prepared+ and Survivor to trigger Abrasive for free Dexterity.

F46 [card_select] select_deck_card (option_index=4) | source=llm
  HP 22->22 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Outbreak+ is the core damage engine for the poison build. Enchanting it provides the highest impact, making it easier to play, draw, or trigger to maximize our AoE damage.
  strategic_note: Committed poison plan: apply poison with Bouncing Flask+ and Deadly Poison to trigger Outbreak+ AoE, stall with defensive scaling (Footwork+, Abrasive), and retain combo pieces with Well-Laid Plans. Needs more discard for Abrasive and draw.

F46 [event] choose_event_option (option_index=0) | source=auto
  HP 22->22 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Only option: Proceed

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 22->22 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=combat) | source=llm
  HP 22->44 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: With only 22 HP going into the Act 3 Boss and a slow-scaling poison engine, survival during the setup phase is our biggest risk. Healing to 44 HP provides the necessary buffer to absorb early damage while setting up Footwork, Outbreak, and our passive block/poison engine.
  strategic_note: Committed poison/defensive plan: stall with high block while Bouncing Flask+ and Deadly Poison scale damage; use Prepared+ and Survivor to trigger Abrasive for free Dexterity. Prioritize survival and block scaling early in combats.

F47 [rest_site] proceed | source=auto
  HP 44->44 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 44->44 | Gold 106->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 9->9 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 9->0 | Gold 106->106 | Deck 27->27
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (5 replays)
[Selected: elite] Terror Eel (F8, elite)
## Combat Replay: vs Terror Eel (Floor 8, elite)
Relics: Ring of the Snake, Silver Crucible
Deck (16): Defend x5, Strike x5, Bouncing Flask, Cloak and Dagger+, Neutralize+, Predator+, Survivor, Well-Laid Plans+
Enemies: Terror Eel HP=140/140

### Round 1
Agent plan (hypothesis): Save Vuln Potion for a big damage turn (like Predator + Shivs) to push Eel to 50% HP (70) and stun it.
Intent: Terror Eel: Attack(16)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Agent plan (hypothesis): Look for a big Predator or Bouncing Flask turn to push the Eel below 70 HP
Intent: Terror Eel: Attack(3x3=9), Buff
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  turn_end
  Strike
  confirm

### Round 3
Intent: Terror Eel: Attack(22)
  Neutralize+ -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -4, +Weak(2)
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Terror Eel[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Terror Eel: hp -4
  Shiv -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -4
  Defend
    energy -1 | block +5
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -6
  turn_end
  Strike
  Strike

### Round 4
Agent plan (hypothesis): Use Bouncing Flask and the 7-card hand to push Eel near 70 HP for the stun next turn.
Intent: Terror Eel: Attack(2x3=6), Buff
  Predator+ -> Terror Eel[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Terror Eel: hp -20
  Defend
    energy -1 | block +5
  turn_end
  Bouncing Flask
  Strike

### Round 5
Intent: Terror Eel: Attack(22)
  Vulnerable Potion -> Terror Eel[0]
    enemy_deltas: Terror Eel: +Vulnerable(3)
  Neutralize+ -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -6, +Weak(2)
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -9
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -9
  Cloak and Dagger+
    energy -1 | block +6
  Shiv -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -6
  Shiv -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -6, -Shriek
  turn_end
  Bouncing Flask
  confirm

### Round 6
Agent plan (hypothesis): Eel is very low, burst damage next turn should finish it.
Intent: Terror Eel: Debuff
  Predator+ -> Terror Eel[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Terror Eel: hp -30
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -9
  turn_end
  Bouncing Flask
  Defend

### Round 7
Agent plan (hypothesis): Lethal achieved, conserving HP.
Intent: Terror Eel: Attack(33)
  Neutralize+ -> Terror Eel[0]
    enemy_deltas: Terror Eel: hp -6, +Weak(2)
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -9
  Strike -> Terror Eel[0]
    energy -1 | enemy_deltas: Terror Eel: hp -9
  Strike -> Terror Eel[0]
    energy -1 | -Well-Laid Plans | -Vulnerable | enemy_deltas: Terror Eel: DIED
## Combat Analytics: Terror Eel (WIN - 7 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 6 plays, 30 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 16 dmg
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 2 plays, 12 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 20 dmg, EXHAUST
  Strike "Deal 6 damage." -> 7 plays, 51 dmg
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 50 dmg

Token attribution (Shivs):
  Cloak and Dagger+: 4 Shivs -> ~20 dmg

Enemy power timeline:
  Shriek: R1:70 -> R2:70 -> R3:70 -> R4:70 -> R5:70 -> R6:- -> R7:-
  Vigor: R1:- -> R2:- -> R3:6 -> R4:- -> R5:6 -> R6:6 -> R7:6
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:1
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:-

[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F14, elite)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 14, elite)
Relics: Ring of the Snake, Silver Crucible, Snecko Skull
Deck (18): Defend x5, Strike x4, Abrasive, Backflip, Bouncing Flask+, Cloak and Dagger+, Dagger Spray+, Neutralize+, Predator+, Survivor, Well-Laid Plans+
Enemies: Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=31/31

### Round 1
Agent plan (hypothesis): Thorns is active. Focus down the buffing enemies or the ones hitting hardest. Use retained cards effectively.
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
Agent plan (hypothesis): Retain Bouncing Flask+.
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
Agent plan (hypothesis): Retain Predator+ to nuke Gardener 3. Gardener 2 is at 1 HP and can be killed with anything.
Agent plan (hypothesis): Finish off the remaining enemies next turn.
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
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 11, elite)
Relics: Ring of the Snake, New Leaf, Lantern
Deck (15): Defend x5, Strike x3, Deflect, Echoing Slash+, Expertise, Neutralize, Poisoned Stab, Precise Cut, Survivor
Enemies: Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=26/26

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Deflect
    block +4
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Echoing Slash+
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -13, block +6
  Expertise
    energy -1
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Deflect
    block +4
  Neutralize -> Phantasmal Gardener[1]
  Poisoned Stab -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block +6, +Poison(3)
  Precise Cut -> Phantasmal Gardener[3]
    enemy_deltas: Phantasmal Gardener: hp -5, block -6
  Survivor
    energy -1 | block +8
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff
  Strike -> Phantasmal Gardener[1]
    energy -1
  Echoing Slash+
    energy -1 | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 3 rounds)

Cards played (with descriptions):
  Deflect "Gain 4 Block." -> 2 plays, 8 block
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Echoing Slash+ "Deal 13 damage to ALL enemies. Repeat this effect for each enemy killed." -> 2 plays, 13 dmg
  Expertise "Draw cards until you have 6 in your Hand." -> 1 plays
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Precise Cut "Deal 11 damage. Deals 2 less damage for each other card in your Hand." -> 1 plays, 5 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Strike "Deal 6 damage." -> 1 plays

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6
  Skittish[3]: R1:6 -> R2:6 -> R3:-
  Strength: R1:- -> R2:2 -> R3:2

[Selected: boss] Soul Fysh (F17, boss)
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Silver Crucible, Snecko Skull, Bronze Scales
Deck (20): Defend x5, Strike x4, Backflip x2, Abrasive, Bouncing Flask+, Cloak and Dagger+, Dagger Spray+, Deadly Poison, Neutralize+, Predator+, Survivor, Well-Laid Plans+
Enemies: Soul Fysh HP=211/211

### Round 1
Agent plan (hypothesis): Hold Abrasive since there's no discard outlet, hope to draw Survivor later or use it when more energy is available. Save Energy Potion for an emergency block/draw turn.
Intent: Soul Fysh: StatusCard(2)
  Bouncing Flask+
    energy -2 | enemy_deltas: Soul Fysh: +Poison(16)
  Deadly Poison -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: Poison(16→22)
  turn_end

### Round 2
Intent: Soul Fysh: Attack(16)
  Energy Potion
    energy +2
  Backflip
    energy -1 | block +5
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Predator+ -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -20
  Defend
    energy -1 | block +5
  turn_end
  Strike
  Strike

### Round 3
Agent plan (hypothesis): Hold cards via Well-Laid Plans if Backflip draws something useful.
Intent: Soul Fysh: Attack(7), StatusCard(1)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Survivor
    energy -1 | block +8
  Beckon
  Dagger Spray+
    energy -1 | enemy_deltas: Soul Fysh: hp -12
  Backflip
    energy -1 | block +5
  turn_end
  Defend
  Defend

### Round 4
Agent plan (hypothesis): Boss gains Intangible next turn, so focus entirely on block and weak.
Intent: Soul Fysh: Buff
  Survivor
    energy -1 | block +8
  Abrasive
  Cloak and Dagger+
    energy -1 | block +7 | Thorns(3→7) | +Dexterity(1)
  Shiv -> Soul Fysh[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Beckon
    energy -1
  turn_end
  Defend
  Defend

### Round 5
Agent plan (hypothesis): Retain Bouncing Flask+.
Intent: Soul Fysh: Attack(11), Debuff
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -1, +Weak(2)
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Deadly Poison -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: Poison(18→24)
  turn_end
  Dagger Spray+
  confirm

### Round 6
Agent plan (hypothesis): Boss will take massive poison damage next turn. Focus entirely on blocking the Vulnerable-amplified attack next turn.
Intent: Soul Fysh: StatusCard(2)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, Weak(1→3)
  Bouncing Flask+
    energy -2 | enemy_deltas: Soul Fysh: Poison(23→39)
  Dagger Spray+
    energy -1 | enemy_deltas: Soul Fysh: hp -12
  turn_end
  Survivor
  Defend

### Round 7
Agent plan (hypothesis): Act 1 complete!
Intent: Soul Fysh: Attack(18)
  Survivor
    energy -1 | block +9
  Beckon
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end
  Defend
  Defend
## Combat Analytics: Soul Fysh (WIN - 7 rounds)

Cards played (with descriptions):
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 2 plays, +32 poison
  Deadly Poison "Apply 6 Poison." -> 2 plays, +12 poison
  Backflip "Gain 5 Block. Draw 2 cards." -> 3 plays, 16 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Defend "Gain 5 Block." -> 2 plays, 11 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 9 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 3 plays, 25 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 2 plays, 24 dmg
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 1 plays, 7 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 8 dmg, EXHAUST
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 1 plays
  Strike "Deal 6 damage." -> 2 plays, 12 dmg

Active powers: Thorns(3)

Token attribution (Shivs):
  Cloak and Dagger+: 2 Shivs -> ~8 dmg

Poison stacks applied per card:
  Bouncing Flask+: 32 stacks
  Deadly Poison: 12 stacks

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:-
  Poison: R1:- -> R2:21 -> R3:20 -> R4:19 -> R5:18 -> R6:23 -> R7:38
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Precarious Shears, Gremlin Horn, Red Mask, Darkstone Periapt
Deck (16): Defend x4, Strike x3, Dagger Spray, Deadly Poison, Dodge and Roll, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator, Survivor, Tools of the Trade
Enemies: Soul Fysh HP=211/211

### Round 1
Intent: Soul Fysh: StatusCard(2)
  Regen Potion -> Soul Fysh[0]
    +Regen(5)
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  Dagger Spray
    energy -1 | enemy_deltas: Soul Fysh: hp -8
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end
  Predator

### Round 2
Intent: Soul Fysh: Attack(16)
  Swift Potion
  Speed Potion
    +Dexterity(5) | +Speed Potion(5)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Dodge and Roll
    energy -1 | block +9 | +Block Next Turn(9)
  Defend
    energy -1 | block +10
  turn_end
  Strike

### Round 3
Intent: Soul Fysh: Attack(5), StatusCard(1)
  Noxious Fumes+
    energy -1 | Noxious Fumes(2→5)
  Predator -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -15
  turn_end
  Beckon

### Round 4
Intent: Soul Fysh: Buff
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Dagger Spray
    energy -1 | enemy_deltas: Soul Fysh: hp -8
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Survivor
    energy -1 | block +8
  Beckon
  turn_end
  Strike

### Round 5
Intent: Soul Fysh: Attack(8), Debuff
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -1, Weak(1→3)
  Defend
    energy -1 | block +5
  Dodge and Roll
    energy -1 | block +4 | +Block Next Turn(4)
  Dagger Spray
    energy -1 | enemy_deltas: Soul Fysh: hp -2
  turn_end
  Beckon

### Round 6
Intent: Soul Fysh: StatusCard(2)
  Predator -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -15
  Survivor
    energy -1 | block +8
  Beckon
  turn_end
  Strike

### Round 7
Intent: Soul Fysh: Attack(18)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, Weak(1→3)
  Beckon
    energy -1
  Beckon
    energy -1
  Beckon
    energy -1
  turn_end
  Beckon

### Round 8
Intent: Soul Fysh: Attack(7), StatusCard(1)
  Predator -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -15
  Survivor
    energy -1 | block +8
  Strike
  turn_end
  Beckon

### Round 9
Intent: Soul Fysh: Buff
  Beckon
    energy -1
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, Weak(1→3)
  Dagger Spray
    energy -1 | enemy_deltas: Soul Fysh: hp -8
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end
  Beckon

### Round 10
Intent: Soul Fysh: Attack(8), Debuff
  Defend
    energy -1 | block +5
  Beckon
    energy -1
  Beckon
    energy -1
  turn_end
  Beckon

### Round 11
Intent: Soul Fysh: StatusCard(2)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, Weak(1→3)
  turn_end
## Combat Analytics: Soul Fysh (WIN - 11 rounds)

Cards played (with descriptions):
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 4 plays, 26 dmg
  Strike "Deal 6 damage." -> 3 plays, 18 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 6 plays, 21 dmg
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Dodge and Roll "Gain 9 Block. Next turn, gain 9 Block." -> 2 plays, 13 block
  Defend "Gain 10 Block." -> 3 plays, 20 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 3 plays, 45 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 3 plays, 24 block
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 6 plays

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:1 -> R11:-
  Poison: R1:- -> R2:- -> R3:2 -> R4:6 -> R5:10 -> R6:14 -> R7:18 -> R8:22 -> R9:26 -> R10:30 -> R11:34
  Weak: R1:1 -> R2:- -> R3:1 -> R4:- -> R5:1 -> R6:2 -> R7:1 -> R8:2 -> R9:1 -> R10:2 -> R11:1

[Selected: boss] The Insatiable (F33, boss)
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Silver Crucible, Snecko Skull, Bronze Scales, Biiig Hug, Lantern
Deck (23): Defend x4, Backflip+ x2, Abrasive, Assassinate, Backflip, Bouncing Flask+, Cloak and Dagger, Cloak and Dagger+, Dagger Spray+, Deadly Poison, Footwork+, Neutralize+, Outbreak, Piercing Wail, Predator+, Prepared+, Survivor, Well-Laid Plans, Well-Laid Plans+
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Assassinate -> The Insatiable[0]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: The Insatiable: hp -10, +Vulnerable(1)
  Footwork+
    energy -1 | +Dexterity(3)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Survivor
    energy -1 | block +11
  Abrasive
  Dagger Spray+
    energy -1 | Thorns(3→7) | Dexterity(3→4) | enemy_deltas: The Insatiable: hp -18
  turn_end
  Piercing Wail

### Round 2
Agent plan (hypothesis): Retain Frantic Escape using Well-Laid Plans for a turn when we have excess energy.
Intent: The Insatiable: Attack(8x2=16)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4, +Weak(2)
  Backflip
    energy -1 | block +9
  Predator+ -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -20
  turn_end
  Piercing Wail

### Round 3
Agent plan (hypothesis): Retain key cards as needed, focus on poison scaling next cycle.
Agent plan (hypothesis): Continue managing Sandpit timer while finding opportunities to scale poison.
Intent: The Insatiable: Attack(21)
  Prepared+
  Well-Laid Plans+
  Bouncing Flask+
  Backflip+
    energy -1 | block +12
  Cloak and Dagger
    energy -1 | block +10
  Shiv -> The Insatiable[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -4
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  turn_end
  Deadly Poison

### Round 4
Agent plan (hypothesis): Retain Frantic Escape. Focus on blocking the 7x2 next turn.
Intent: The Insatiable: Buff
  Backflip+
    energy -1 | block +12
  Predator+ -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -20
  turn_end
  Backflip+

### Round 5
Agent plan (hypothesis): Retain the second Frantic Escape
Intent: The Insatiable: Attack(10x2=20)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4, +Weak(2)
  Cloak and Dagger
    energy -1 | block +10
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Backflip+
    energy -1 | block +12
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  turn_end
  Frantic Escape

### Round 6
Intent: The Insatiable: Attack(7x2=14)
  Duplicator
    +Duplication(1)
  Bouncing Flask+
    energy -2 | -Duplication | enemy_deltas: The Insatiable: +Poison(32)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  Prepared+
  Frantic Escape
  Defend
  turn_end
  Backflip

### Round 7
Agent plan (hypothesis): Retain Frantic Escape.
Intent: The Insatiable: Attack(30)
  Backflip
    energy -1 | block +9
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4, +Weak(2)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  turn_end
  Piercing Wail

### Round 8
Agent plan (hypothesis): Retain the other Frantic Escape. Focus on finishing the boss before Sandpit catches up.
Intent: The Insatiable: Buff
  Frantic Escape
    energy -2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Cloak and Dagger+
    energy -1 | block +10
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  turn_end
  Piercing Wail

### Round 9
Agent plan (hypothesis): Retain Deadly Poison or the Frantic Escape depending on our needs. Boss is close to death.
Intent: The Insatiable: Attack(12x2=24)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Prepared+
  Well-Laid Plans+
  Soot
  Piercing Wail
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: Strength(4→-2), +Piercing Wail(6)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  turn_end
  Deadly Poison

### Round 10
Agent plan (hypothesis): Fight is over.
Intent: The Insatiable: Attack(12x2=24)
  Potion of Binding
    enemy_deltas: The Insatiable: +Weak(1), +Vulnerable(1)
  Deadly Poison -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(28→34)
  Backflip+
    energy -1 | block +12
  Defend
    energy -1 | block +9
  turn_end
  Backflip+
## Combat Analytics: The Insatiable (WIN - 10 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 10 dmg, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 1 plays, 18 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 12 dmg
  Backflip "Gain 9 Block. Draw 2 cards." -> 2 plays, 18 block
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 40 dmg
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Backflip+ "Gain 12 Block. Draw 2 cards." -> 4 plays, 48 block
  Cloak and Dagger "Gain 10 Block. Add 1 Shiv into your Hand." -> 2 plays, 20 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 16 dmg, EXHAUST
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 6 plays
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 1 plays, +32 poison
  Defend "Gain 9 Block." -> 3 plays, 27 block
  Cloak and Dagger+ "Gain 10 Block. Add 2 Shivs into your Hand." -> 1 plays, 10 block, generates 2 Shivs
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Deadly Poison "Apply 6 Poison." -> 1 plays, +6 poison

Active powers: Thorns(3)

Token attribution (Shivs):
  Cloak and Dagger: 2 Shivs -> ~8 dmg
  Cloak and Dagger+: 2 Shivs -> ~8 dmg

Poison stacks applied per card:
  Bouncing Flask+: 32 stacks
  Deadly Poison: 6 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:31 -> R8:30 -> R9:29 -> R10:28
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:3 -> R5:2 -> R6:2 -> R7:2 -> R8:1 -> R9:1 -> R10:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:1 -> R9:- -> R10:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, New Leaf, Lantern, Bronze Scales, Bellows, Pael's Tears, Pen Nib, The Chosen Cheese
Deck (20): Defend x4, Accelerant+, Acrobatics+, Alchemize+, Backflip, Blade Dance, Bubble Bubble, Deadly Poison+, Deflect, Echoing Slash+, Expertise+, Leg Sweep, Neutralize+, Outbreak, Poisoned Stab, Precise Cut, Survivor
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Strength Potion
    +Strength(2)
  Outbreak+
    energy -1 | +Outbreak(15)
  Deadly Poison+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: +Poison(7)
  Acrobatics+
    energy -1
  Blade Dance+
  Alchemize+
    exhausted: Alchemize+ [0]: Procure a random potion. Exhaust.
  Deflect+
    block +7
  Poisoned Stab+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -10, Poison(7→11)
  turn_end

### Round 2
Intent: The Insatiable: Attack(8x2=16)
  Echoing Slash+
    energy -1 | enemy_deltas: The Insatiable: hp -30
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -6, +Weak(2)
  Bubble Bubble -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -15, Poison(10→19)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  Precise Cut -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -15
  turn_end

### Round 3
Intent: The Insatiable: Attack(21)
  Accelerant+
    energy -1 | +Accelerant(2)
  Leg Sweep -> The Insatiable[0]
    energy -2 | block +11 | enemy_deltas: The Insatiable: Weak(1→3)
  turn_end

### Round 4
Intent: The Insatiable: Buff
  Strength Potion
    Strength(2→4)
  Precise Cut -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -9
  Expertise+
    energy -1
  Backflip
    energy -1 | block +5
  Poisoned Stab+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -12, Poison(15→19)
  turn_end

### Round 5
Intent: The Insatiable: Attack(7x2=14)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -8, Weak(1→3)
  Deadly Poison+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(16→23)
  Bubble Bubble -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -15, Poison(23→32)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  turn_end
## Combat Analytics: The Insatiable (WIN - 5 rounds)

Cards played (with descriptions):
  Outbreak+ "Every 3 times you apply Poison, deal 15 damage to ALL enemies." -> 1 plays
  Deadly Poison+ "Apply 7 Poison." -> 2 plays, +14 poison
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Alchemize+ "Procure a random potion. Exhaust." -> 1 plays, EXHAUST
  Deflect+ "Gain 7 Block." -> 1 plays, 7 block
  Poisoned Stab+ "Deal 10 damage. Apply 4 Poison." -> 2 plays, 22 dmg, +8 poison
  Echoing Slash+ "Deal 30 damage to ALL enemies. Repeat this effect for each enemy killed." -> 1 plays, 30 dmg
  Neutralize+ "Deal 6 damage. Apply 2 Weak." -> 2 plays, 14 dmg
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 2 plays, 30 dmg, +18 poison
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 2 plays
  Precise Cut "Deal 15 damage. Deals 2 less damage for each other card in your Hand." -> 2 plays, 24 dmg
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block

Active powers: Thorns(3)

Poison stacks applied per card:
  Bubble Bubble: 18 stacks
  Deadly Poison+: 14 stacks
  Poisoned Stab+: 8 stacks

Enemy power timeline:
  Poison: R1:- -> R2:10 -> R3:18 -> R4:15 -> R5:16
  Sandpit: R1:- -> R2:4 -> R3:4 -> R4:3 -> R5:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2
  Weak: R1:- -> R2:- -> R3:1 -> R4:2 -> R5:1

[Selected: boss] Door (F48, boss)
## Combat Replay: vs Door (Floor 48, boss)
Relics: Ring of the Snake, Silver Crucible, Snecko Skull, Bronze Scales, Biiig Hug, Lantern, Music Box, Fragrant Mushroom, Art of War
Deck (27): Backflip+ x3, Defend x3, Cloak and Dagger x2, Abrasive, Acrobatics, Assassinate, Bouncing Flask+, Bubble Bubble, Cloak and Dagger+, Dagger Spray+, Deadly Poison, Defend+, Deflect+, Footwork+, Neutralize+, Outbreak+, Piercing Wail, Predator+, Prepared+, Survivor+, Well-Laid Plans, Well-Laid Plans+
Enemies: Door HP=999999999/999999999

### Round 1
Agent plan (hypothesis): Hold Bouncing Flask+ for Doormaker.
Agent plan (hypothesis): Hold Flask for Doormaker.
Intent: Door: Summon
  Clarity Extract
    +Clarity(3)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Backflip+
    energy -1 | block +8
  turn_end
  Bouncing Flask+

### Round 2
Agent plan (hypothesis): Next turn, use Prepared+ to discard Abrasive. Do not play extra draws since Scrutiny prevents them.
Agent plan (hypothesis): Retain Abrasive
Agent plan (hypothesis): Retain Abrasive if we don't find Prepared+.
Agent plan (hypothesis): Retain Abrasive for Dexterity scaling. Next turn is Scrutiny: no extra draws allowed.
Intent: Doormaker: Attack(30)
  Outbreak+
    energy -1 | +Outbreak(15)
  Footwork+
    energy -1 | +Dexterity(3)
  Backflip+
    energy -1 | block +11 | exhausted: Backflip+ [1]: Gain 8 Block. Draw 2 cards. Exhaust.
  Backflip+
    energy -1 | block +11
  Prepared+
  Abrasive
  Dagger Spray+
  turn_end
    exhausted: Prepared+ [0]: Draw 2 cards. Discard 2 cards. Exhaust.
  Bouncing Flask+

### Round 3
Agent plan (hypothesis): Next turn is Grasp. Cards cost 1 extra energy. Doormaker will attack for 10x2 (reduced by Weak to 7x2=14) and buff Strength. Rely on high impact cards.
Agent plan (hypothesis): Next turn is Grasp, cards cost 1 more. Use high impact cards.
Intent: Doormaker: Attack(24)
  Neutralize+ -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4, +Weak(2)
  Assassinate -> Doormaker[0]
    exhausted: Prepared+ [0]: Draw 2 cards. Discard 2 cards. | enemy_deltas: Doormaker: hp -10, +Vulnerable(1)
  Neutralize+ -> Doormaker[0]
    enemy_deltas: Doormaker: hp -6, Weak(2→4)
  Bouncing Flask+
    energy -2 | enemy_deltas: Doormaker: hp -15, +Poison(16)
  Bubble Bubble -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(16→26)
  Survivor+
    energy -1 | block +15
  Well-Laid Plans+
  turn_end
  Backflip+

### Round 4
Agent plan (hypothesis): Next turn is Hunger. Playing Attacks or Skills will exhaust them. Be prepared to either exhaust basic Defends or retain a card that already exhausts.
Agent plan (hypothesis): Next turn is Hunger: any attack or skill played will Exhaust. Use this to thin the deck of basic Defends or play expendable cards. Do not play crucial engine cards.
Intent: Doormaker: Attack(7x2=14), Buff
  Backflip+
    energy -2 | block +12
  Deflect+
    energy -1 | block +11
  turn_end
  Piercing Wail

### Round 5
Intent: Doormaker: Attack(24)
  Defend+
    energy -1 | block +12 | exhausted: Prepared+ [0]: Draw 2 cards. Discard 2 cards. Exhaust.
  Cloak and Dagger+
    energy -1 | block +10 | exhausted: Prepared+ [0]: Draw 2 cards. Discard 2 cards. Exhaust.
  Shiv -> Doormaker[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Doormaker: hp -4
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  Dagger Spray+
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Doormaker: hp -12
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Piercing Wail

### Round 6
Intent: Doormaker: Attack(20)
  Piercing Wail
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Doormaker: Strength(3→-3), +Piercing Wail(6)
  Defend
    energy -1 | block +9
  Deadly Poison -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: hp -15, Poison(23→29)
  turn_end
  confirm_selection

### Round 7
Agent plan (hypothesis): Next turn is Hunger. Attacks and Skills will exhaust when played. Use Cloak and Dagger for expendable block.
Intent: Doormaker: Attack(13x2=26), Buff
  Neutralize+ -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: hp -4, +Weak(2)
  Survivor+
    energy -1 | block +15
  Well-Laid Plans+
  Neutralize+ -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: hp -4, Weak(2→4)
  turn_end
  Cloak and Dagger

### Round 8
Agent plan (hypothesis): Next turn is Grasp, cards cost 1 more. Retain Bouncing Flask+.
Agent plan (hypothesis): Retain Bouncing Flask+. Next turn is Scrutiny, cannot draw extra cards.
Intent: Doormaker: Attack(27)
  Deflect+
    block +11 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Backflip+
    energy -1 | block +12
  Cloak and Dagger
    energy -1 | block +10 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  Neutralize+ -> Doormaker[0]
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Doormaker: hp -4, Weak(3→5)
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  Defend
    energy -1 | block +9 | exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.
  turn_end
  Bouncing Flask+

### Round 9
Agent plan (hypothesis): Retained Bouncing Flask+ can be used next turn. Next turn is Grasp (cards cost 1 extra), so Bouncing Flask+ will cost 3.
Intent: Doormaker: Attack(22)
  Cloak and Dagger
    energy -1 | block +10
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  Defend
    energy -1 | block +9
  Deadly Poison -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(26→32)
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  turn_end
  Bouncing Flask+

### Round 10
Agent plan (hypothesis): Retain Bouncing Flask+ if possible. Enemy takes massive poison damage.
Intent: Doormaker: Attack(12x2=24), Buff
  Survivor+
    energy -1 | block +15
  Soot
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage. Lose 1 energy . Exhaust.
  Bouncing Flask+

### Round 11
Agent plan (hypothesis): Survive the hit. Doormaker will take massive poison damage next turn.
Intent: Doormaker: Attack(29)
  Neutralize+ -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4, Weak(2→4)
  Neutralize+ -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4, Weak(4→6)
  Acrobatics
    energy -1
  Predator+
  Cloak and Dagger
    energy -1 | block +10
  Shiv -> Doormaker[0]
    enemy_deltas: Doormaker: hp -4
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  turn_end
  Bouncing Flask+

### Round 12
Agent plan (hypothesis): Lethal poison secured. Doormaker falls.
Intent: Doormaker: Attack(24)
  Bubble Bubble -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: Poison(29→39)
  Bouncing Flask+
    energy -2 | enemy_deltas: Doormaker: hp -30, Poison(39→55)
  turn_end
  Survivor+
## Combat Analytics: Door (WIN - 12 rounds)

Cards played (with descriptions):
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 5 plays, 54 block
  Outbreak+ "Every 3 times you apply Poison, deal 15 damage to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards. Exhaust." -> 1 plays, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 7 plays, 30 dmg
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 10 dmg, EXHAUST
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 2 plays, 45 dmg, +32 poison
  Bubble Bubble "If the enemy has Poison, apply 10 Poison." -> 2 plays, +20 poison
  Survivor+ "Gain 15 Block. Discard 1 card." -> 3 plays, 45 block
  Deflect+ "Gain 11 Block. Lose 1 energy ." -> 2 plays, 22 block
  Defend+ "Gain 12 Block. Exhaust." -> 1 plays, 12 block, EXHAUST
  Cloak and Dagger+ "Gain 10 Block. Add 2 Shivs into your Hand. Exhaust." -> 1 plays, 10 block, EXHAUST, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 7 plays, 28 dmg, EXHAUST
  Dagger Spray+ "Deal 6 damage to ALL enemies twice. Exhaust." -> 1 plays, 12 dmg, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Defend "Gain 9 Block." -> 5 plays, 45 block
  Deadly Poison "Apply 6 Poison." -> 2 plays, 15 dmg, +12 poison
  Cloak and Dagger "Gain 10 Block. Add 1 Shiv into your Hand. Exhaust." -> 3 plays, 30 block, EXHAUST, generates 1 Shivs
  Acrobatics "Draw 3 cards. Discard 1 card. Exhaust." -> 1 plays, EXHAUST

Active powers: Thorns(3)

Token attribution (Shivs):
  Cloak and Dagger: 3 Shivs -> ~12 dmg
  Cloak and Dagger+: 2 Shivs -> ~8 dmg
  other: 2 Shivs -> ~8 dmg

Poison stacks applied per card:
  Bouncing Flask+: 32 stacks
  Bubble Bubble: 20 stacks
  Deadly Poison: 12 stacks

Enemy power timeline:
  Grasp: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:1 -> R11:- -> R12:-
  Hunger: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:1 -> R9:- -> R10:- -> R11:1 -> R12:-
  Poison: R1:- -> R2:- -> R3:- -> R4:25 -> R5:24 -> R6:23 -> R7:28 -> R8:27 -> R9:26 -> R10:31 -> R11:30 -> R12:29
  Scrutiny: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:1 -> R10:- -> R11:- -> R12:1
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:3 -> R7:3 -> R8:6 -> R9:6 -> R10:6 -> R11:9 -> R12:9
  Weak: R1:- -> R2:- -> R3:- -> R4:3 -> R5:2 -> R6:1 -> R7:- -> R8:3 -> R9:4 -> R10:3 -> R11:2 -> R12:5
Comparator (recent same-enemy comparator):
## Combat Replay: vs Door (Floor 48, boss)
Relics: Ring of the Snake, Neow's Torment, Potion Belt, Very Hot Cocoa, Pendulum, Preserved Fog, Happy Flower, Chemical X
Deck (27): Defend x4, Dagger Throw x2, Ricochet x2, Abrasive, Acrobatics+, Afterimage, Corrosive Wave+, Dash, Deadly Poison, Folly, Footwork+, Haze+, Leg Sweep+, Malaise+, Mirage, Neow's Fury, Neutralize+, Outbreak+, Precise Cut, Prepared+, Survivor, Well-Laid Plans+
Enemies: Door HP=999999999/999999999

### Round 1
Intent: Door: Summon
  Dexterity Potion
    +Dexterity(2)
  Regen Potion
    +Regen(5)
  Afterimage
    energy -1 | +Afterimage(1)
  Abrasive
    energy -3 | block +1 | Dexterity(2→3) | +Thorns(4)
  Outbreak+
    energy -1 | block +1 | +Outbreak(15)
  turn_end
    exhausted: Folly [0]: Unplayable. Innate. Ethereal. Eternal.

### Round 2
Intent: Doormaker: Attack(30)
  Acrobatics+
    energy -1
  Haze+
  Defend
    energy -1 | block +9 | exhausted: Haze+ [3]: Sly. Apply 6 Poison to ALL enemies. Exhaust.
  Malaise+ -> Doormaker[0]
    energy -1 | block +1 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Doormaker: +Strength(-4), +Weak(4)
  turn_end

### Round 3
Intent: Doormaker: Attack(15)
  Footwork+
    energy -1 | block +1 | Dexterity(3→6)
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Precise Cut -> Doormaker[0]
    block +1 | enemy_deltas: Doormaker: hp -9
  Survivor
    energy -1 | block +15
  turn_end
    hp +3

### Round 4
Intent: Doormaker: Attack(4x2=8), Buff
  Defend
    energy -2 | block +12
  Neow's Fury -> Doormaker[0]
    energy -2 | block +1 | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Lose 1 energy . Exhaust. | enemy_deltas: Doormaker: hp -10
  turn_end
  Mirage
  Leg Sweep+

### Round 5
Intent: Doormaker: Attack(21)
  Corrosive Wave+
    energy -1 | block +1 | +Corrosive Wave(3) | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust.
  Leg Sweep+ -> Doormaker[0]
    energy -2 | block +21 | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Doormaker: Weak(1→4)
  Prepared+
    enemy_deltas: Doormaker: hp -15, Poison(3→9)
  Ricochet
  Ricochet
  Precise Cut -> Doormaker[0]
    block +1 | exhausted: Ricochet*2 [2]: Sly. Deal 3 damage to a random enemy 4 times. Exhaust. | enemy_deltas: Doormaker: hp -5
  turn_end
  Mirage
  Deadly Poison

### Round 6
Intent: Doormaker: Attack(17)
  Dash -> Doormaker[0]
    energy -2 | block +17 | enemy_deltas: Doormaker: hp -10
  Deadly Poison -> Doormaker[0]
    energy -1 | block +1 | enemy_deltas: Doormaker: Poison(8→13)
  turn_end
  Mirage
  confirm

### Round 7
Intent: Doormaker: Attack(6x2=12), Buff
  Deadly Poison -> Doormaker[0]
    energy -2 | block +1 | enemy_deltas: Doormaker: Poison(12→17)
  Mirage
    energy -2 | block +24 | exhausted: Ricochet*2 [2]: Sly. Deal 3 damage to a random enemy 4 times. Lose 1 energy .
  turn_end
  Neutralize+
  Defend

### Round 8
Intent: Doormaker: Attack(24)
  Neutralize+ -> Doormaker[0]
    block +1 | exhausted: Ricochet*2 [2]: Sly. Deal 3 damage to a random enemy 4 times. Exhaust. | enemy_deltas: Doormaker: hp -4, Weak(1→3)
  Deadly Poison -> Doormaker[0]
    energy -1 | block +1 | exhausted: Ricochet*2 [2]: Sly. Deal 3 damage to a random enemy 4 times. Exhaust. | enemy_deltas: Doormaker: hp -15, Poison(16→21)
  Survivor
    energy -1 | block +14
  Dagger Throw
  Defend
    energy -1 | block +12
  turn_end
  Dash
  Defend

### Round 9
Intent: Doormaker: Attack(19)
  Dash -> Doormaker[0]
    energy -2 | block +17 | enemy_deltas: Doormaker: hp -10
  Defend
    energy -1 | block +12
  turn_end
  Dagger Throw
  Dagger Throw

### Round 10
Intent: Doormaker: Attack(9x2=18), Buff
  Defend
    energy -2 | block +12
  Defend
    energy -2 | block +12
  turn_end
  Dagger Throw
  Dagger Throw

### Round 11
Intent: Doormaker: Attack(35)
  Dash -> Doormaker[0]
    energy -2 | block +17 | exhausted: Survivor [1]: Gain 8 Block. Discard 1 card. Exhaust. | enemy_deltas: Doormaker: hp -10
  Defend
    energy -1 | block +12
  turn_end
  Dagger Throw
  Defend

### Round 12
Intent: Doormaker: Attack(29)
  Defend
    energy -1 | block +12
  Dagger Throw -> Doormaker[0]
    energy -1 | block +1 | enemy_deltas: Doormaker: hp -9
  turn_end

### Round 13
Intent: Doormaker: Attack(15x2=30), Buff
  Defend
    energy -2 | block +12
  Dagger Throw -> Doormaker[0]
    energy -1 | enemy_deltas: Doormaker: hp -9
  Defend
  turn_end
  Dagger Throw
  confirm

### Round 14
Intent: Doormaker: Attack(38)
  Defend
    energy -1 | block +12
  Dagger Throw -> Doormaker[0]
    energy -1 | block +1 | exhausted: Survivor [1]: Gain 8 Block. Discard 1 card. Exhaust. | enemy_deltas: Doormaker: hp -9
  turn_end
## Combat Analytics: Door (LOSS - 14 rounds)
Death cause: Died with HP=23, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Abrasive "Sly. Gain 1 Dexterity. Gain 4 Thorns." -> 1 plays, 1 block
  Outbreak+ "Every 3 times you apply Poison, deal 15 damage to ALL enemies." -> 1 plays, 1 block
  Acrobatics+ "Draw 4 cards. Discard 1 card. Exhaust." -> 1 plays, EXHAUST
  Defend "Gain 8 Block. Exhaust." -> 10 plays, 117 block, EXHAUST
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, 1 block, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 1 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards. Draw 2 cards the first time this is played." -> 1 plays, 1 block
  Precise Cut "Deal 9 damage. Deals 2 less damage for each other card in your Hand." -> 2 plays, 14 dmg, 2 block
  Survivor "Gain 14 Block. Discard 1 card." -> 2 plays, 29 block
  Neow's Fury "Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Lose 1 energy . Exhaust." -> 1 plays, 10 dmg, 1 block, EXHAUST
  Corrosive Wave+ "Whenever you draw a card this turn, apply 3 Poison to ALL enemies. Exhaust." -> 1 plays, 1 block, EXHAUST
  Leg Sweep+ "Apply 3 Weak. Gain 20 Block. Exhaust." -> 1 plays, 21 block, EXHAUST
  Prepared+ "Draw 2 cards. Discard 2 cards. Exhaust." -> 1 plays, 15 dmg, +6 poison, EXHAUST
  Dash "Gain 16 Block. Deal 10 damage." -> 3 plays, 30 dmg, 51 block
  Deadly Poison "Apply 5 Poison." -> 3 plays, 15 dmg, 3 block, +15 poison
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 23 Block) Lose 1 energy . Exhaust." -> 1 plays, 24 block, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak. Exhaust." -> 1 plays, 4 dmg, 1 block, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 27 dmg, 2 block

Poison stacks applied per card:
  Deadly Poison: 15 stacks
  Prepared+: 6 stacks

Enemy power timeline:
  Grasp: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:1 -> R11:- -> R12:- -> R13:1 -> R14:-
  Hunger: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:1 -> R9:- -> R10:- -> R11:1 -> R12:- -> R13:- -> R14:1
  Poison: R1:- -> R2:- -> R3:5 -> R4:4 -> R5:3 -> R6:8 -> R7:12 -> R8:16 -> R9:20 -> R10:19 -> R11:18 -> R12:17 -> R13:16 -> R14:15
  Scrutiny: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:1 -> R10:- -> R11:- -> R12:1 -> R13:- -> R14:-
  Strength: R1:- -> R2:- -> R3:-4 -> R4:-4 -> R5:-1 -> R6:-1 -> R7:-1 -> R8:2 -> R9:2 -> R10:2 -> R11:5 -> R12:5 -> R13:5 -> R14:8
  Weak: R1:- -> R2:- -> R3:3 -> R4:2 -> R5:1 -> R6:3 -> R7:2 -> R8:1 -> R9:2 -> R10:1 -> R11:- -> R12:- -> R13:- -> R14:-

## Triggered Skills This Run
- The Silent - Boss Strategy: F17(Soul Fysh: WIN), F33(The Insatiable: WIN), F48(Door: WIN)
- The Silent - Deckbuilding Principles: F2(), F3(), F4(), F5(), F6(), F8(), F11(), F13(), F13(), F14(), F15(), F17(), F18(), F19(), F20(), F22(), F22(), F23(), F30(), F31(), F33(), F35(), F37(), F38(), F39(), F43(), F44(), F45(), F46()
- The Silent - Path Selection: F1(), F1(), F2(), F3(), F6(), F11(), F11(), F18(), F18(), F20(), F23(), F24(), F26(), F27(), F29(), F30(), F34(), F34(), F35(), F35(), F36(), F37(), F41(), F44(), F45()
- The Silent - Rest & Event Decisions: F7(), F9(), F12(), F16(), F24(), F27(), F29(), F32(), F40(), F42(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.