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
Result: VICTORY (fitness: 235.9)
Combats won: 20/20
Run duration: 5347.7s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation stage: relying on starter cards; prioritize drafting premium damage attacks to tackle Act 1 Elites, and use our map flexibility to snipe high-value nodes.
- [map] Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.
### F2
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics.
- [map] Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.
### F3
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics.
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; prioritize premium damage to clear early Act 1 threats.
- [map] Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.
### F4
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics. Prioritize cheap debuffs, retain tools, and further poison scaling.
- [map] Foundation stage: prioritizing consecutive monster encounters to draft essential frontloaded damage and defensive tools before tackling Act 1 Elites.
### F5
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics. Take cheap utility and draw like Seeker Strike.
- [card_reward] Foundation plan transitioning to Retain/Poison: use Bullet Time to cheat out retained high-cost cards (Snakebite, Predator). Prioritize card draw, Retain cards, and Dexterity scaling; avoid expensive cards unless they Retain or draw.
- [map] Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools; health is low, so targeting immediate card rewards over Unknown randomness to stabilize for the first Elite.
### F6
- [card_reward] Foundation plan: transition into poison scaling using Retain (Snakebite) and Bullet Time. Keep the deck lean, remove Strikes, and look for efficient mitigation and catalyst/multipliers.
- [map] Foundation stage: Currently relying on starter cards and critically low on HP. I am using a Winged Boots charge to path to an immediate Rest Site to stabilize. My priority is drafting frontloaded damage like Predator or Dagger Spray to make the deck viable before the next forced combat or the Act 1 Boss.
### F7
- [rest_site] Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Need to keep HP high for Elites and prioritize card draw to maximize Bullet Time.
- [map] Foundation stage: prioritizing frontloaded damage and basic block scaling while navigating Act 1 to prepare for Elites; currently following a high-sustain route to preserve HP for the boss.
### F8
- [event] Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. With Chosen Cheese, prioritize pathing through more combats later to scale Max HP, while keeping current HP safe.
- [map] Foundation stage: Utilizing Predator and Snakebites for front-loaded damage, leveraging Bullet Time to dump high-cost cards. Current priority is balancing HP for upcoming Elites while seeking card draw to make Bullet Time more consistent.
### F9
- [rest_site] Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through more combats later to scale Max HP with Chosen Cheese, while keeping current HP safe. Upgrade Bullet Time or Neutralize next.
- [map] Foundation stage: Utilizing Predator and Snakebites for frontloaded damage while Bullet Time enables high-impact turns. With Chosen Cheese, we seek combats to scale Max HP, but must prioritize efficient blocking and smithing key cards to survive upcoming Elites.
### F10
- [map] Foundation stage: Utilizing Predator and Snakebites for heavy early damage, supported by Bullet Time for high-impact turns. Transitioning to focus on Max HP scaling through Chosen Cheese while prioritizing high-value Elite encounters to secure key relics and upgrades.
### F11
- [card_reward] Committed to poison plan with Snakebites. Look for Catalyst/more poison, discard synergy for Sly cards, and well-laid plans. Keep deck lean and remove basic attacks.
- [map] Foundation stage: Utilizing Predator, Snakebites, and Bullet Time for high-impact turns while scaling Max HP through Chosen Cheese in combat. Need to prioritize defensive card drafts and a shop visit to convert gold into relics or key removals before the Act 1 boss.
### F12
- [card_reward] Committed poison plan: Retain Snakebites until Bullet Time or a safe turn to burst poison. Prioritize mitigation, draw, and removal to stall out fights while poison ticks. Skip low-impact attacks.
- [map] Foundation stage: Deck uses Bullet Time to cheat out expensive high-impact cards like Predator. Priority is upgrading Bullet Time to reduce its cost and adding more high-cost/high-impact cards to leverage the energy cheat while building block density.
### F13
- [rest_site] Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through more combats to scale Max HP with Chosen Cheese. Upgrade Neutralize next for consistency.
- [map] Foundation stage: Utilizing Predator and Snakebites for frontloaded damage with Bullet Time for hand dumping. Prioritizing standard monster combats to scale Max HP through Chosen Cheese while preserving current health for the Act 1 boss. Need more consistent block and card draw to support Bullet Time turns.
### F14
- [hand_select] Retaining Snakebite for poison stacking; discarding basic defense while Smoggy limits skill usage.
- [card_reward] Committed poison plan: retain Snakebites and look for efficient defense while passive poison kills. Use Bullet Time for heavy setup turns. Need more block scaling and maybe a discard outlet for Flick-Flack.
- [map] Foundation stage: Utilizing Predator, Snakebites, and Bullet Time for high-impact turns. Prioritize high-value shop purchases with 280+ gold and use the final rest site to upgrade a key damage or draw piece to ensure boss victory.
### F15
- [event] Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through Elites to transform Sword of Stone and combats to scale Max HP with Chosen Cheese. Upgrade Neutralize or a key draw piece next.
- [map] Foundation stage: Deck uses Predator and Snakebites for frontload, with Bullet Time for high-impact turns. Focus on upgrading core defensive and utility cards like Neutralize to improve consistency before the Act 1 boss. Maximize Chosen Cheese value by pathing through combats in Act 2.
### F16
- [rest_site] Foundation stage: Early deck relies on Predator and Snakebites for damage, with Bullet Time for explosive turns. Look for discard synergies and card draw in Act 2, and avoid adding more basic attacks.
### F17
- [card_select] Foundation plan: survive with frontload and efficient block while integrating poison and retain mechanics; look for a core scaling engine.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [card_reward] Committed poison plan: retain poison (Snakebite) and use Bullet Time+ for massive free setups. Prioritize survival with Afterimage and efficient block while poison kills. Needs draw and mitigation; skip basic attacks.
### F18
- [event] Foundation stage: Early deck relies on Predator and Snakebites for damage, with Bullet Time for explosive turns. Look for discard synergies and card draw in Act 2, and avoid adding more basic attacks. Maximize Chosen Cheese value by pathing through combats and Elites.
- [card_select] Committed poison plan: survive with Afterimage and frontload damage while applying retained poison for scaling. Needs more efficient mitigation, card draw, and removal of basic Strikes.
- [map] Foundation stage: Deck relies on Predator and Snakebites for frontload with Bullet Time for high-impact turns. Focus on scouting defensive consistency in early Act 2 hallways while pathing toward shops to convert high gold reserves into permanent power or card removals.
### F19
- [card_reward] Committed poison/retain plan: Retain Snakebites for massive burst damage on safe turns, utilizing Bullet Time to dump hands. Afterimage provides passive defense while we stall for poison kills. Seek more discard to trigger Sly, and card draw/retain pieces.
- [map] Foundation stage: Leveraging high gold at the shop to find discard synergies or defensive scaling to support Bullet Time and Predator. Avoid adding basic attacks and prioritize card quality and removals to improve draw consistency.
### F20
- [card_select] Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Remove basic attacks to improve consistency. Look for more poison scaling, block/dexterity, and discard synergy for Flick-Flack.
- [map] Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Currently seeking discard synergies and card draw to stabilize the engine while avoiding unnecessary basic attacks.
### F21
- [card_reward] Foundation plan: surviving with Predator and Snakebite poison while leveraging Bullet Time for burst turns. Prioritize draw, removals, and a consistent scaling engine.
- [map] Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Transitioning to discard and draw synergies is the priority to maximize Bullet Time and Snakebites. HP is high, so hunting for foundational synergy cards in hallway fights is the current goal while avoiding Act 2 Elites.
### F22
- [card_reward] Committed poison plan: retain Snakebite+ and use Bullet Time to play massive hands, then defend while passive poison kills. Relies on Footwork and Afterimage for block scaling; prioritize card draw and removal of basic Strikes.
- [map] Foundation stage: Deck uses Predator and Snakebites for frontload damage, supported by Bullet Time for high-impact turns. Now seeking card draw (Acrobatics, Backflip) and discard synergies to cycle into power turns faster and handle the high damage of Act 2 hallways.
### F23
- [card_reward] Committed poison plan: retain Snakebite+ and use Bouncing Flask to stack high poison on priority targets. Defend with Footwork, Afterimage, and Bullet Time while poison ticks down. Keep the deck lean and prioritize removals of Strikes.
- [map] Foundation stage: Leveraging Predator and Bullet Time for high-impact turns while seeking discard synergies and card draw. The deck currently lacks consistent block and scaling, so I am prioritizing non-combat nodes and Rest Sites in Act 2 to maintain HP for the boss.
### F24
- [map] Foundation stage: Deck uses Predator and Bullet Time for high-impact turns. Currently seeking discard synergies and improved block scaling to stabilize Act 2. Juzu Bracelet makes Unknown nodes high-value safety detours; avoid Elites until the defense is more consistent.
### F25
- [map] Foundation stage: Deck uses Bullet Time to cheat out high-cost damage like Predator and Snakebites. Need more card draw and discard synergies (like Acrobatics or Calculated Gamble) to maximize Bullet Time turns and improve defensive consistency.
### F26
- [map] Foundation stage: Deck relies on Predator and Bullet Time; seeking draw and discard synergies to maximize Bullet Time turns while avoiding Act 2 Elites.
### F27
- [rest_site] Foundation stage: relies on Snakebites, Predator, and Poison (Fumes/Flask) for damage, with Bullet Time for explosive turns. Prioritize card draw and discard synergies to cycle faster.
- [map] Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Transitioning into Act 2, I need to find consistent card draw and discard synergies to bridge the gap between heavy-hitting turns, while prioritizing HP preservation over risky Elite fights.
### F28
- [card_reward] Committed poison plan with hybrid tools: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards. Fan of Knives adds AoE capability for multi-enemy fights.
- [map] Foundation stage: Deck uses Predator and Snakebites for frontload with Bullet Time for high-impact turns. Currently seeking discard synergies and additional card draw to maximize Bullet Time value; prioritize smithing over resting to maintain momentum while HP is high.
### F29
- [rest_site] Foundation stage: Deck has a strong mix of AoE shivs (Fan of Knives, Blade Dance) and Poison (Fumes, Flask) for damage, with Footwork/Afterimage for block. Cycle aggressively using Acrobatics and Backflip. Prioritize draw and card removal.
- [map] Foundation stage: Deck uses Bullet Time to cheat out high-cost Predator and Snakebites damage, but lacks consistent block and discard scaling. Prioritize finding Acrobatics or Calculated Gamble to cycle through basics and enable Bullet Time more frequently; avoid unnecessary hallway fights to preserve health for the boss.
### F30
- [event] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites and Predator or spam Shivs with Fan of Knives and Blade Dance. Prioritize consistent card draw to reliably find Bullet Time and avoid adding more basic attacks.
- [map] Foundation stage: Deck balances Shiv/Poison damage with strong defensive tools like Footwork and Afterimage. Prioritize card draw and thinning to cycle into key powers faster; look for more Acrobatics or Backflip to stabilize the rotation.
### F31
- [card_reward] Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Keep the deck lean and remove basic attacks to improve consistency. Look for block/dexterity and discard synergy.
- [map] Foundation stage: Deck balances AoE shivs and poison for damage, supported by Footwork and After Image. Cycle through the deck with Acrobatics and Backflip while prioritizing upgrades on core powers and defensive consistency.
### F32
- [rest_site] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Keep cycling aggressively to find Bullet Time and defensive powers.
### F33
- [hand_select] Discarding Strike maintains deck quality and allows for Shiv generation while preparing to play Bullet Time+ for a zero-cost turn.
- [card_reward] Committed poison plan: retain high-yield poison like Snakebite for burst turns, stack defensive scaling (Dex, Weak) to stall. Prioritize card removal and skip non-synergistic attacks.
### F34
- [event] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Keep cycling aggressively to find Bullet Time and defensive powers.
- [map] Foundation stage: Balancing AoE shivs and poison for damage, supported by Footwork and After Image. Use Acrobatics and Backflip to cycle into core powers and defensive consistency; prioritizing upgrades on scaling pieces while using Juzu Bracelet to navigate Unknown nodes safely.
### F35
- [hand_select] Executing Bullet Time combo to set up defense and scaling.
- [card_reward] Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Retain combo pieces for big Burst or Bullet Time turns. Avoid generic attacks and prioritize basic attack removals.
- [map] Committed poison-shiv hybrid: use Bullet Time to cheat out Snakebites and Predator. Leverage Juzu Bracelet to navigate Unknown nodes safely for events and shops while avoiding unnecessary chip damage. Aiming for more defensive scaling or poison multipliers to secure the Act 3 boss kill.
### F36
- [event] Committed poison-shiv hybrid: use Bullet Time to cheat out Snakebites and Predator. Leverage Juzu Bracelet to navigate Unknown nodes safely for events and shops while avoiding unnecessary chip damage. Passive block from Sai, Gorget, and Afterimage handles incoming damage while Fumes and poison build up.
- [map] Committed poison and shiv hybrid: utilize Bullet Time to deploy high-cost cards like Snakebite and Predator while Noxious Fumes scales damage. Focus on cycling into defensive powers and keeping high HP for the boss. Avoid unnecessary elite fights despite Sword of Stone, as survival and reliable scaling are the current priorities.
### F37
- [map] Committed poison and shiv hybrid: utilize Bullet Time to cheat out Snakebite and Predator while Noxious Fumes scales; prioritize finding more defensive scaling or card draw at shops to ensure Bullet Time is consistently impactful.
### F38
- [card_select] Committed poison plan: survive with block and debuffs while stacking poison on priority targets using Snakebite and Bouncing Flask. Retain poison with Well-Laid Plans for safe turns. Use Bullet Time for expensive hands. Keep removing basic Strikes to draw scaling faster.
- [map] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost cards like Snakebite and Predator while Noxious Fumes scales. Prioritize cycling to find Bullet Time and defensive pieces; avoid adding low-impact cards.
### F39
- [card_reward] Committed poison/defense plan: rely on passive defense relics, Afterimage, and Footwork while stacking poison with Retain pieces (Snakebite+) and Noxious Fumes. Keep deck thin to draw into powers and mitigation quickly.
- [map] Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites and Predator while Fumes scales; with Juzu Bracelet, prioritize Unknown nodes to avoid chip damage and find safe utility.
### F40
- [event] Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget.
- [map] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers while Fumes provides passive scaling. Prioritize finding defensive tools to survive the setup turns and use Winged Boots charges only if a forced high-damage elite path must be avoided later.
### F41
- [map] Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites and setup powers like Noxious Fumes. Prioritize upgrades on core scaling and defensive pieces to ensure survival while poison stacks. Avoid unnecessary Elite fights in Act 3 to preserve HP for the final encounter.
### F42
- [rest_site] Committed poison/shiv hybrid: Retain combo pieces with Well-Laid Plans to cheat out high-cost cards using Bullet Time, while Noxious Fumes provides scaling. Focus on surviving and drawing aggressively while mitigating chip damage.
- [map] Committed poison-shiv hybrid: use Bullet Time to deploy Snakebites and Predator while Fumes scales. Focus on acquiring more defensive consistency or card draw to ensure Bullet Time is impactful every cycle.
### F43
- [map] Committed poison and shiv hybrid: use Bullet Time to cheat out high-cost cards like Snakebites and Predator while Fumes scales; prioritize taking Elites to finish the Sword of Stone quest before the final boss.
### F44
- [card_reward] Committed poison plan: survive with block and debuffs while stacking heavy poison via Snakebite, Bouncing Flask, and Fumes. Play Accelerant to double poison ticks. Retain key cards with Well-Laid Plans for safe, explosive turns.
- [map] Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and avoiding unnecessary damage before the final boss.
### F45
- [event] Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and avoiding unnecessary damage before the final boss.
- [map] Committed poison/shiv hybrid: Use Well-Laid Plans to set up Bullet Time turns for high impact, while Noxious Fumes provides the necessary scaling. Focus on maximizing block and draw consistency to mitigate chip damage; prioritizing safety via Unknown nodes and Rest Sites to ensure high HP for the Act 3 boss.
### F46
- [card_select] Committed poison plan: rely on passive Noxious Fumes and targeted poison application while surviving with Footwork, Afterimage, and Kunai-fueled block. Avoid adding generic attacks and prioritize card draw and removal.
- [map] Committed poison/shiv hybrid: use Well-Laid Plans to set up Bullet Time for high-impact turns while Noxious Fumes scales damage. Prioritize defensive consistency and card draw to ensure setup occurs before taking critical damage. Focus on upgrading core scaling or mitigation at the final rest site.
### F47
- [rest_site] Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and surviving the setup phase.
### F48
- [hand_select] Retaining Piercing Wail allows for perfect damage mitigation on a high-risk multi-attack turn.

### Combat Decision Digest (20 combats)
F2 [monster] Sludge Spinner (4R, HP 56->53, loss=3, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R2[Sludge Spinner: Atk(11)]: Neutralize(2dmg,1+Weak(1))->Defend(+5blk)->Strike(4dmg)->Strike(4dmg) | dealt=10 taken=3
  R3[Sludge Spinner: Atk(8), Debuff]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R4[Sludge Spinner: Atk(6), Buff]: Strike(power:-Weak) | dealt=0 taken=0

F3 [monster] multi:Toadpole+Toadpole (5R, HP 53->53, loss=0, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Strike*2->Survivor(+8blk) | dealt=0 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=9 taken=0
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Neutralize->Strike*2->Hand Trick(+7blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Toadpole: Atk(7)]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R5[Toadpole: Buff]: Strike | dealt=0 taken=0

F4 [monster] multi:Corpse Slug+Corpse Slug (4R, HP 53->43, loss=10, WIN)
  R1[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Defend(+5blk)->Strike->Strike(6dmg) | dealt=6 taken=1
  R2[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Neutralize->Predator(15dmg,power:+Draw Cards Next Turn(2))->Defend(+3blk) | dealt=15 taken=9
  R3[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Strike(1+Strength(4))->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R4[Corpse Slug: Atk(12)]: Strike | dealt=0 taken=0

F5 [monster] Gremlin Merc (9R, HP 43->29, loss=14, WIN)
  R1[Gremlin Merc: Atk(7x2=14)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=0
  R2[Gremlin Merc: Atk(6x2=12), Debuff]: Defend(+5blk)->Strike(6dmg)->Survivor(+8blk) | dealt=6 taken=0
  R3[Gremlin Merc: Atk(8), Buff]: Neutralize(2dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Dagger Throw(6dmg) | dealt=2 taken=0
  R4[Gremlin Merc: Atk(9x2=18)]: Defend(+5blk)->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R5[Gremlin Merc: Atk(8x2=16), Debuff]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Predator(15dmg,power:+Draw Cards Next Turn(2)) | dealt=18 taken=7
  R6[Gremlin Merc: Atk(10), Buff]: Survivor(+8blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R7[Gremlin Merc: Atk(11x2=22)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=7
  R8[Gremlin Merc: Atk(10x2=20), Debuff]: Strike->Predator(power:+Draw Cards Next Turn(2)) | dealt=21 taken=0
  R9[Sneaky Gremlin: Atk(9)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike | dealt=9 taken=0

F6 [monster] Haunted Ship (3R, HP 29->29, loss=0, WIN)
  R1[Haunted Ship: StatusCard(5)]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Dagger Throw(9dmg) | dealt=15 taken=0
  R2[Haunted Ship: Atk(10), Debuff]: Bullet Time(power:+No Draw(1))->Neutralize(3dmg,1+Weak(1))->Snakebite(1+Poison(7))->Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=9 taken=0
  R3[Haunted Ship: Atk(13)]: Predator(11dmg,power:+Draw Cards Next Turn(2))->Dagger Throw(6dmg) | dealt=11 taken=0

F11 [elite] Skulking Colony (6R, HP 57->47, loss=10, WIN)
  R1[Skulking Colony: Atk(12)]: Dagger Throw(9dmg)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=2
  R2[Skulking Colony: Atk(14), Defend]: Bullet Time(power:+No Draw(1))->Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Snakebite(1+Poison(7))->Snakebite(1Poison(7→14))->Strike(6dmg) | dealt=9 taken=0
  R3[Skulking Colony: Atk(9), Buff]: Predator(5dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=5 taken=1
  R4[Skulking Colony: Atk(9x2=18)]: Dagger Throw(9dmg)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=8
  R5[Skulking Colony: Atk(14)]: Bullet Time(power:+No Draw(1))->Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg)->Snakebite(1Poison(11→18))->Snakebite(1Poison(18→25)) | dealt=9 taken=0
  R6[Skulking Colony: Atk(16), Defend]: Strike | dealt=0 taken=0

F12 [monster] multi:Calcified Cultist+Damp Cultist (4R, HP 47->47, loss=0, WIN)
  R1[Calcified Cultist: Buff+Damp Cultist: Buff]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Dagger Throw(9dmg) | dealt=15 taken=0
  R2[Calcified Cultist: Atk(9)+Damp Cultist: Atk(1)]: Neutralize(3dmg,1+Weak(1))->Flick-Flack(12dmg)->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=21 taken=0
  R3[Calcified Cultist: Atk(11)+Damp Cultist: Atk(6)]: Neutralize->Defend(+5blk)->Snakebite(1Poison(5→12)) | dealt=1 taken=1
  R4[Damp Cultist: Atk(11)]: Bullet Time(power:+No Draw(1))->Snakebite(1Poison(11→18))->Flick-Flack(6dmg)->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=12 taken=0

F14 [monster] Living Fog (4R, HP 47->42, loss=5, WIN)
  R1[Living Fog: Atk(8), CardDebuff]: Survivor(+8blk)->Flick-Flack(21dmg,power:+Draw Cards Next Turn(2))->Predator | dealt=21 taken=0
  R2[Living Fog: Atk(5), Summon]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Snakebite(1+Poison(7))->Dagger Throw(9dmg) | dealt=15 taken=3
  R3[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Strike(6dmg)->Strike->Defend(+5blk) | dealt=7 taken=3
  R4[Living Fog: Atk(5), Summon]: Defend(+5blk)->Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Dagger Throw(9dmg) | dealt=9 taken=0

F17 [boss] Lagavulin Matriarch (8R, HP 63->16, loss=47, WIN)
  R1[Lagavulin Matriarch: Sleep]: Dagger Throw->Flick-Flack | dealt=0 taken=0
  R2[Lagavulin Matriarch: Atk(19)]: Neutralize(3dmg,1+Weak(1))->Snakebite(1+Poison(7))->Snakebite(1Poison(7→14))->Survivor(+8blk) | dealt=3 taken=6
  R3[Lagavulin Matriarch: Atk(9x2=18)]: Scrawl(exhaust:1)->Dagger Throw(9dmg)->Flick-Flack(1Poison(13→18))->Deadly Poison(+5blk)->Defend | dealt=0 taken=13
  R4[Lagavulin Matriarch: Atk(12), Defend]: Neutralize(3dmg,1+Weak(1))->Snakebite(1Poison(17→24))->Survivor(+8blk) | dealt=3 taken=1
  R5[Lagavulin Matriarch: Debuff, Buff]: Bullet Time+(power:+No Draw(1))->Snakebite(1Poison(23→30))->Strike->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R6[Lagavulin Matriarch: Atk(21)]: Predator(13dmg,power:+Draw Cards Next Turn(2))->Defend(+3blk)->Precise Cut(5dmg) | dealt=18 taken=18
  R7[Lagavulin Matriarch: Atk(11x2=22)]: Dagger Throw(7dmg)->Flick-Flack(1dmg,1+Weak(1))->Neutralize(+6blk)->Survivor(1Poison(28→33))->Deadly Poison | dealt=1 taken=10
  R8[Lagavulin Matriarch: Atk(14), Defend]: Survivor(+6blk)->Defend(+3blk) | dealt=0 taken=0

F19 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (4R, HP 62->55, loss=7, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Afterimage+(power:+Afterimage(1))->Bullet Time+(+1blk,power:+No Draw(1))->Flick-Flack(6dmg,+1blk)->Defend(+6blk)->Strike(6dmg,+1blk)->Survivor(+9blk) | dealt=12 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(10)]: Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Snakebite+(+1blk,1+Poison(10)) | dealt=0 taken=0
  R3[Exoskeleton: Buff+Exoskeleton: Atk(10)+Exoskeleton: Buff]: Dagger Throw->Predator(+1blk,power:+Draw Cards Next Turn(2)) | dealt=0 taken=8
  R4[Exoskeleton: Atk(10)+Exoskeleton: Buff]: Neutralize+(+1blk)->Flick-Flack(+1blk,1+Weak(2))->Strike(6dmg,+1blk)->Strike(power:-Afterimage) | dealt=6 taken=0

F21 [monster] Tunneler (3R, HP 75->74, loss=1, WIN)
  R1[Tunneler: Atk(13)]: Afterimage+(power:+Afterimage(1))->Defend(+6blk)->Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk) | dealt=16 taken=2
  R2[Tunneler: Buff, Defend]: Bullet Time+(+1blk,power:+No Draw(1))->Predator(30dmg,+2blk,power:+Draw Cards Next Turn(4),power:-Duplication)->Snakebite+(+1blk,1+Poison(10))->Snakebite+(+1blk,1Poison(10→20))->Strike(6dmg,+1blk) | dealt=36 taken=0
  R3[Tunneler: Atk(23)]: Neutralize+(+1blk,1+Weak(2))->Defend(+6blk)->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0

F22 [monster] Hunter Killer (5R, HP 74->72, loss=2, WIN)
  R1[Hunter Killer: Debuff]: Afterimage+(power:+Afterimage(1))->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2)) | dealt=15 taken=0
  R2[Hunter Killer: Atk(17)]: Defend(+6blk,power:+Strength(-1),power:+Dexterity(-1))->Acrobatics->Bullet Time+(+1blk,power:Strength(-2→-3),power:Dexterity(-2→-3),power:+No Draw(1))->Defend(+3blk,power:Strength(-3→-4),power:Dexterity(-3→-4))->Neutralize+(+1blk,power:Strength(-4→-5),power:Dexterity(-4→-5),1+Weak(2))->Defend(+1blk,power:Strength(-5→-6),power:Dexterity(-5→-6))->Snakebite+(+1blk,power:Strength(-6→-7),power:Dexterity(-6→-7),1+Poison(10))->Snakebite+(+1blk,power:Strength(-7→-8),power:Dexterity(-7→-8),1Poison(10→20))->Deadly Poison(+1blk,power:Strength(-8→-9),power:Dexterity(-8→-9),1Poison(20→25))->Dagger Throw(+1blk,power:Strength(-9→-10),power:Dexterity(-9→-10)) | dealt=0 taken=0
  R3[Hunter Killer: Atk(5x3=15)]: Strike(6dmg,+1blk,power:+Strength(-1),power:+Dexterity(-1))->Strike(5dmg,+1blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Piercing Wail(+1blk,power:Strength(-2→-3),power:Dexterity(-2→-3),2+Strength(-6),+Piercing Wail(6),exhaust:1) | dealt=11 taken=0
  R4[Hunter Killer: Atk(7x3=21)]: Defend(+6blk,power:+Strength(-1),power:+Dexterity(-1))->Defend(+5blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Strike(4dmg,+1blk,power:Strength(-2→-3),power:Dexterity(-2→-3)) | dealt=4 taken=3
  R5[Hunter Killer: Atk(17)]: none | dealt=0 taken=0

F23 [monster] multi:Chomper+Chomper (6R, HP 72->68, loss=4, WIN)
  R1[Chomper: Atk(8x2=16)+Chomper: StatusCard(3)]: Afterimage+(power:+Afterimage(1))->Defend(+6blk)->Survivor(+8blk)->Flick-Flack | dealt=6 taken=0
  R2[Chomper: StatusCard(3)+Chomper: Atk(8x2=16)]: Acrobatics->Neutralize+(4dmg,+1blk,1Artifact(2→1))->Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Dagger Throw(9dmg)->Defend(+6blk)->Strike(6dmg,+1blk) | dealt=26 taken=1
  R3[Chomper: Atk(8x2=16)+Chomper: StatusCard(3)]: Bullet Time+(+1blk,power:+No Draw(1))->Piercing Wail(+1blk,1-Artifact,exhaust:1)->Snakebite+(+1blk)->Snakebite+(+1blk)->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Strike(+1blk,1+Poison(10))->Defend(+6blk) | dealt=15 taken=4
  R4[Chomper: StatusCard(3)]: Footwork(+1blk,power:+Dexterity(2))->Dagger Throw(9dmg)->Flick-Flack(+8blk)->Defend | dealt=0 taken=0
  R5[Chomper: Atk(8x2=16)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Strike(6dmg,+1blk)->Defend(+8blk)->Survivor(+11blk) | dealt=10 taken=0
  R6[Chomper: StatusCard(3)]: Strike(power:-Afterimage,power:-Dexterity) | dealt=0 taken=0

F28 [monster] Louse Progenitor (6R, HP 78->79, loss=0, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Afterimage+(power:+Afterimage(1))->Bullet Time+(+1blk,power:+No Draw(1))->Footwork(+1blk,power:+Dexterity(2))->Neutralize+(4dmg,+1blk,2+Weak(2),-Curl Up)->Defend(+8blk)->Strike(+1blk)->Strike(+1blk) | dealt=4 taken=0
  R2[Louse Progenitor: Defend, Buff]: Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Snakebite+(+1blk,1+Poison(10))->Deadly Poison(+1blk,1Poison(10→15))->Strike(6dmg,+1blk) | dealt=22 taken=0
  R3[Louse Progenitor: Atk(19)]: Piercing Wail(+1blk,2Strength(5→-1),+Piercing Wail(6),exhaust:1)->Survivor(+7blk)->Flick-Flack(+8blk)->Defend | dealt=0 taken=0
  R4[Louse Progenitor: Atk(14), Debuff]: Backflip(+8blk)->Acrobatics+(+6blk)->Noxious Fumes(+1blk,power:+Noxious Fumes(2)) | dealt=0 taken=0
  R5[Louse Progenitor: Defend, Buff]: Backflip(+6blk)->Bullet Time+(+1blk,power:+No Draw(1))->Survivor(+7blk)->Flick-Flack(6dmg,+3blk,1Poison(14→24))->Snakebite+(6dmg,+1blk)->Strike(+6blk)->Defend(+6blk)->Defend | dealt=12 taken=0
  R6[Louse Progenitor: Atk(24)]: Neutralize+(+1blk,1+Weak(2))->Snakebite+(+1blk,1Poison(25→35))->Defend(+6blk) | dealt=0 taken=0

F31 [monster] Spiny Toad (4R, HP 89->77, loss=12, WIN)
  R1[Spiny Toad: Buff]: Bullet Time+(power:+No Draw(1))->Afterimage+(power:+Afterimage(1))->Noxious Fumes(+1blk,power:+Noxious Fumes(2))->Footwork+(+1blk,power:+Dexterity(3))->Bouncing Flask(+1blk,1+Poison(9))->Snakebite+(+1blk,1Poison(9→19)) | dealt=0 taken=0
  R2[Spiny Toad: Atk(23)]: Defend(+9blk)->Deadly Poison(+1blk,1Poison(20→25)) | dealt=0 taken=13
  R3[Spiny Toad: Atk(17)]: Acrobatics+->Flick-Flack(4dmg,+1blk,1+Weak(2))->Neutralize+(+9blk)->Defend(+9blk)->Backflip | dealt=4 taken=0
  R4[Spiny Toad: Buff]: Snakebite+(+1blk,1Poison(27→37))->Defend(+9blk) | dealt=0 taken=0

F33 [boss] multi:Crusher+Rocket (9R, HP 77->50, loss=27, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Afterimage+(power:+Afterimage(1))->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Survivor(+10blk) | dealt=0 taken=4
  R2[Crusher: Atk(4)+Rocket: Atk(27)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Bullet Time+(+1blk,power:+No Draw(1))->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Defend(+8blk)->Defend(+8blk) | dealt=19 taken=0
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Backflip(+8blk)->Footwork+(+1blk,power:Dexterity(2→5))->Defend(+11blk) | dealt=0 taken=0
  R4[Crusher: Buff+Rocket: Atk(33)]: Snakebite+(+1blk,1Poison(7→17))->Defend(+8blk) | dealt=0 taken=24
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Acrobatics+->Bullet Time+(+1blk,power:+No Draw(1))->Defend(+8blk)->Defend(+8blk)->Bouncing Flask(+1blk,1Poison(9→15),1Poison(19→22))->Deadly Poison(+1blk,1Poison(15→20))->Snakebite+(+1blk,1Poison(20→30))->Strike(4dmg,+1blk)->Blade Dance+(+1blk,exhaust:1)->Shiv(3dmg,+1blk,exhaust:1)->Shiv(3dmg,+1blk)->Shiv(3dmg,+1blk)->Shiv(3dmg,+1blk) | dealt=16 taken=0
  R6[Crusher: Atk(14)+Rocket: Atk(7)]: Strike(6dmg,+1blk)->Neutralize+(+1blk,1+Weak(2))->Defend(+11blk)->Survivor(+14blk) | dealt=6 taken=0
  R7[Crusher: Atk(4)+Rocket: Atk(30)]: Piercing Wail(+1blk,2Strength(2→-4),+Piercing Wail(6),2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Defend(+11blk)->Dagger Throw(9dmg)->Flick-Flack | dealt=0 taken=0
  R8[Crusher: Atk(12x2=24), Debuff+Rocket: Buff]: Backflip(+11blk)->Neutralize+(4dmg,+1blk,1+Weak(2))->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2)) | dealt=19 taken=0
  R9[Rocket: Atk(30)]: Defend(+11blk)->Defend(+11blk)->Defend(+11blk) | dealt=0 taken=0

F35 [monster] Devoted Sculptor (6R, HP 82->83, loss=0, WIN)
  R1[Devoted Sculptor: Buff]: Backflip(+5blk)->Afterimage+(power:+Afterimage(1))->Neutralize+(4dmg,+1blk,1+Weak(2))->Deadly Poison(+1blk,1+Poison(5)) | dealt=4 taken=0
  R2[Devoted Sculptor: Atk(9)]: Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Snakebite+(+1blk,1Poison(4→14))->Defend(+6blk)->Strike(6dmg,+1blk) | dealt=6 taken=0
  R3[Devoted Sculptor: Atk(21)]: Acrobatics+->Bullet Time+(+1blk,power:+No Draw(1))->Footwork+(+1blk,power:+Dexterity(3))->Bouncing Flask(+1blk,1Poison(16→25))->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Defend(+9blk)->Defend(+9blk) | dealt=31 taken=0
  R4[Devoted Sculptor: Atk(30)]: Defend(+9blk)->Defend(+9blk)->Strike(6dmg,+1blk) | dealt=6 taken=0
  R5[Devoted Sculptor: Atk(39)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Piercing Wail(+1blk,2Strength(27→21),+Piercing Wail(6),exhaust:1)->Defend(+9blk)->Survivor(+11blk) | dealt=4 taken=0
  R6[Devoted Sculptor: Atk(36)]: Predator(power:-Afterimage,power:-Noxious Fumes,power:-Dexterity) | dealt=0 taken=0

F39 [monster] multi:Living Shield+Turret Operator (4R, HP 83->84, loss=0, WIN)
  R1[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Bullet Time+(power:+No Draw(1))->Afterimage+(power:+Afterimage(1))->Footwork+(+1blk,power:+Dexterity(3))->Strike(6dmg,+1blk)->Strike(6dmg,+1blk)->Survivor(6dmg,+13blk) | dealt=18 taken=0
  R2[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Piercing Wail(+1blk,2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Calculated Gamble(+1blk,exhaust:1)->Defend(+9blk)->Defend(+9blk) | dealt=15 taken=0
  R3[Living Shield: Atk(6)+Turret Operator: Buff]: Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Strike(+1blk)->Noxious Fumes+(+1blk,power:+Noxious Fumes(3)) | dealt=22 taken=0
  R4[Turret Operator: Atk(4x5=20)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Defend(+9blk)->Fan of Knives(+1blk,power:+Fan of Knives(1))->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk) | dealt=20 taken=0

F44 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (7R, HP 69->61, loss=8, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Bullet Time+(power:+No Draw(1))->Afterimage+(power:+Afterimage(1))->Predator(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Malaise(+1blk,2+Strength(-1),+Weak(1),exhaust:1)->Defend(+6blk)->Survivor(+9blk) | dealt=15 taken=0
  R2[Flail Knight: Atk(8x2=16)+Spectral Knight: Atk(15)+Magi Knight: Debuff]: Dagger Throw(9dmg)->Flick-Flack(+1blk,power:+Fan of Knives(1))->Fan of Knives(12dmg,+1blk,exhaust:1)->Shiv(12dmg,+1blk)->Shiv(12dmg,+1blk)->Shiv(12dmg,+1blk)->Shiv(+1blk,exhaust:1)->Blade Dance+(12dmg,+1blk)->Shiv(12dmg,+1blk)->Shiv(12dmg,+1blk)->Shiv(12dmg,+1blk)->Shiv(+1blk,exhaust:1)->Calculated Gamble+(+1blk,2Strength(-1→-7),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Piercing Wail | dealt=96 taken=0
  R3[Flail Knight: Atk(14)+Spectral Knight: Atk(3x3=9)+Magi Knight: Atk(10)]: Backflip(+6blk)->Noxious Fumes(+1blk,power:+Noxious Fumes(2))->Defend(+6blk) | dealt=30 taken=3
  R4[Flail Knight: Atk(8x2=16)+Spectral Knight: Atk(15)+Magi Knight: Defend]: Acrobatics->Flick-Flack(3dmg,+1blk,1+Weak(1))->Neutralize(+1blk,power:+Draw Cards Next Turn(2),power:-Hex)->Predator | dealt=18 taken=0
  R5[Flail Knight: Atk(8x2=16)+Magi Knight: Atk(35)]: Bullet Time(+1blk,power:+No Draw(1))->Backflip(+6blk)->Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Strike(6dmg,+1blk) | dealt=6 taken=6
  R6[Flail Knight: Atk(14)+Magi Knight: Atk(10)]: Dagger Throw(9dmg)->Flick-Flack(+1blk,1Poison(4→11))->Snakebite | dealt=0 taken=0
  R7[Flail Knight: Atk(14)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Strike(power:-Afterimage,power:-Fan of Knives,power:-Well-Laid Plans,power:-Noxious Fumes) | dealt=4 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (8R, HP 89->89, loss=0, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Afterimage+(power:+Afterimage(1))->Neutralize+(4dmg,+1blk,1+Weak(2))->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Backflip(+6blk) | dealt=4 taken=0
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Noxious Fumes(+1blk,power:+Noxious Fumes(2))->Accelerant(+1blk,power:+Accelerant(1))->Acrobatics+->Flick-Flack+(+1blk,power:+No Draw(1))->Bullet Time+(+1blk,power:+Dexterity(3))->Footwork+(+1blk,1+Poison(6),1+Poison(3))->Bouncing Flask(15dmg,+1blk,power:+Draw Cards Next Turn(2))->Predator(+9blk)->Defend | dealt=15 taken=0
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Noxious Fumes(+1blk,power:Noxious Fumes(2→4))->Piercing Wail(+1blk,2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Deadly Poison+(+1blk,1Poison(3→10)) | dealt=0 taken=0
  R4[Torch Head Amalgam: Atk(22)+Queen: Buff, Defend]: Defend+(+9blk)->Snakebite+(+1blk,1Poison(12→22))->Calculated Gamble+(+7blk,exhaust:1)->Neutralize+(3dmg,+1blk,1+Weak(2)) | dealt=3 taken=0
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Snakebite+(+1blk,1Poison(24→34))->Survivor(+8blk) | dealt=0 taken=1
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Piercing Wail(+1blk,2Strength(3→-3),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6))->Blade Dance+(+1blk,exhaust:1)->Shiv(3dmg,+1blk,exhaust:1)->Shiv(3dmg,+1blk)->Shiv(3dmg,+1blk,power:Dexterity(3→4))->Shiv(3dmg,+1blk)->Malaise(+1blk,2Strength(-3→-4),+Weak(1),exhaust:1) | dealt=12 taken=0
  R7[Torch Head Amalgam: Atk(25)+Queen: Buff, Defend]: Acrobatics+(+6blk)->Flick-Flack+(+1blk,power:+No Draw(1))->Bullet Time+(+1blk,1Poison(14→20),1Poison(38→41))->Bouncing Flask(+1blk,power:+Fan of Knives(1))->Fan of Knives(3dmg,+1blk)->Shiv(3dmg,+1blk)->Shiv(3dmg,+1blk,power:Dexterity(4→5))->Shiv(3dmg,+1blk)->Shiv(+1blk,1Poison(41→48))->Snakebite(+1blk,1Poison(48→58))->Snakebite+(+1blk,1Poison(58→65))->Deadly Poison+(+10blk)->Defend+(6dmg,+1blk)->Dagger Throw | dealt=18 taken=0
  R8[Torch Head Amalgam: Atk(27)+Queen: Buff, Defend]: Neutralize+(3dmg,+1blk,1+Weak(2))->Backflip(+8blk)->Defend(+8blk) | dealt=3 taken=0

### Non-combat Decisions (198 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Winged Boots provides incredible map flexibility, allowing us to snipe multiple elites or campfires, or safely bypass dangerous paths if we are weak.
  strategic_note: Foundation stage: relying on starter cards; prioritize drafting premium damage attacks to tackle Act 1 Elites, and use our map flexibility to snipe high-value nodes.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Starting the recommended 4-5 monster node chain to build a foundation of damage and block cards. This route provides the most flexibility for future paths and adheres to the goal of aggressive early drafting.
  strategic_note: Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 99->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 111->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 111->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 53->53 | Gold 111->111 | Deck 12->13
  deck_change: picked Snakebite
  reasoning: Snakebite is a high-damage poison card that retains, making it an excellent standalone damage source against early Elites and the Lagavulin Matriarch. Its retain feature allows us to hold it until we have 2 spare energy, and it aligns with the recommended poison strategy.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics.

F2 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 111->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Following the Act 1 strategy of taking early monster nodes to build a card foundation. With 53 HP and only starter cards, I need to find high-impact attacks or defensive tools before the first elite or shop.
  strategic_note: Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.

F3 [card_select] select_deck_card (option_index=2) | source=llm
  HP 53->53 | Gold 111->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Hand Trick provides the most immediate block (7) to help mitigate the 14-16 incoming damage, which aligns directly with the goal of using the Skill Potion to survive the turn.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 111->129 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 129->129 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 129->129 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 53->53 | Gold 129->129 | Deck 13->14
  deck_change: picked Predator
  reasoning: Predator provides excellent upfront damage to handle early Act 1 elites like Gremlin Nob, and the 2 card draw next turn helps cycle through the deck faster.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; prioritize premium damage to clear early Act 1 threats.

F3 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 129->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the Route Intelligence and Strategic Thread to prioritize 4-5 early monster encounters. This builds a deck foundation of frontloaded damage and block before hitting Elites or shops. I have 129 gold, which is okay, but more card rewards are better than a low-resource shop visit right now.
  strategic_note: Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools before tackling Elites.

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 129->139 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 139->139 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 43->43 | Gold 139->139 | Deck 14->15
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides efficient frontload damage for early Act 1 fights while acting as a crucial discard outlet to enable future Sly mechanics or thin out hand clutter.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics. Prioritize cheap debuffs, retain tools, and further poison scaling.

F4 [map] choose_map_node (option_index=1) | source=llm
  HP 43->43 | Gold 139->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the recommended route to maximize early hallway fights. We have 43 HP, which is sufficient for another standard encounter to continue hunting for premium damage and block cards. This path leads towards a rest site for recovery or upgrades before the first Elite.
  strategic_note: Foundation stage: prioritizing consecutive monster encounters to draft essential frontloaded damage and defensive tools before tackling Act 1 Elites.

F5 [card_select] select_deck_card (option_index=2) | source=llm
  HP 36->36 | Gold 19->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Seeker Strike provides solid upfront damage (9 for 1 energy) while offering powerful targeted card selection from the draw pile. This lets us fetch our high-impact cards like Predator or Snakebite when we need them, adding massive consistency to our early game turns while dealing with Act 1 threats.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; start integrating poison and retain mechanics. Take cheap utility and draw like Seeker Strike.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 0->16 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 16->155 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 139 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 155->155 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 29->29 | Gold 155->155 | Deck 15->16
  deck_change: picked Bullet Time
  reasoning: Bullet Time is a run-defining Rare that synergizes exceptionally well with Retain mechanics like Snakebite and our Ring of the Snake starting draw. We can retain high-cost cards and play them all for free alongside Predator's high damage and card draw. While Dash provides immediate safety, Bullet Time provides a massive energy cheat engine for our upcoming poison/retain build.
  strategic_note: Foundation plan transitioning to Retain/Poison: use Bullet Time to cheat out retained high-cost cards (Snakebite, Predator). Prioritize card draw, Retain cards, and Dexterity scaling; avoid expensive cards unless they Retain or draw.

F5 [map] choose_map_node (option_index=0) | source=llm
  HP 29->29 | Gold 155->0 | Deck 16->16
  deck_change: no deck change
  reasoning: HP is critical (29/70) and I have not secured enough frontloaded damage to comfortably handle the upcoming Elites or tougher Act 1 hallway fights. While the route suggests an Unknown node, the 'Expert Knowledge' and 'Route Guide' both emphasize 4-5 early monster encounters to build a foundation. Taking the Monster at index 0 allows me to draft a card and generate gold for the upcoming shop, which is safer than an Unknown node that could potentially result in an unfavorable combat or event when my health is already low.
  strategic_note: Foundation stage: prioritizing early monster encounters to draft essential frontloaded damage and defensive tools; health is low, so targeting immediate card rewards over Unknown randomness to stabilize for the first Elite.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 155->167 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 167->167 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 29->29 | Gold 167->167 | Deck 16->17
  deck_change: picked Snakebite
  reasoning: Snakebite has Retain and pairs excellently with Bullet Time, providing consistent poison scaling. Taking a second copy solidifies our Poison foundation for the Act 1 Boss and helps us reliably stack poison when we have spare energy or draw Bullet Time.
  strategic_note: Foundation plan: transition into poison scaling using Retain (Snakebite) and Bullet Time. Keep the deck lean, remove Strikes, and look for efficient mitigation and catalyst/multipliers.

F6 [map] choose_map_node (option_index=2) | source=llm
  HP 29->29 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: My HP is extremely low at 29/70 (41%) and I have no meaningful damage cards drafted yet to handle an Act 1 Elite. The Winged Boots allow me to deviate from the recommended route to hit a Rest Site immediately. Resting here is a survival necessity to reach the upcoming mandatory Treasure and Boss, as my current deck is still just the starter cards and would likely perish in an Elite fight or even a difficult Unknown combat.
  strategic_note: Foundation stage: Currently relying on starter cards and critically low on HP. I am using a Winged Boots charge to path to an immediate Rest Site to stabilize. My priority is drafting frontloaded damage like Predator or Dagger Spray to make the deck viable before the next forced combat or the Act 1 Boss.

F7 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 29->50 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: With only 29 HP and an immediate Elite fight next, resting to reach 50 HP is necessary to survive heavy hits from Act 1 Elites like Gremlin Nob or Lagavulin.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Need to keep HP high for Elites and prioritize card draw to maximize Bullet Time.

F7 [rest_site] proceed | source=auto
  HP 50->50 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=1) | source=llm
  HP 50->50 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the Route Intelligence recommendation to take the Unknown node. My HP is at 50/70, which is healthy, but the route aims to stabilize before the upcoming Elite at row 10. Taking the Unknown node provides a chance for a beneficial event or a safe encounter before the guaranteed Rest Site at row 8.
  strategic_note: Foundation stage: prioritizing frontloaded damage and basic block scaling while navigating Act 1 to prepare for Elites; currently following a high-sustain route to preserve HP for the boss.

F8 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 50->36 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Trading 14 HP for Chosen Cheese is extremely valuable for long-term survivability. Since our next few nodes are a Shop, Treasure, and Unknown, we face no immediate combat risk and can safely take this damage. We also have a Rest Site before our next Elite if we need to heal.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. With Chosen Cheese, prioritize pathing through more combats later to scale Max HP, while keeping current HP safe.

F8 [event] choose_event_option (option_index=0) | source=auto
  HP 36->36 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F8 [map] choose_map_node (option_index=1) | source=llm
  HP 36->36 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: With 36/70 HP and an Elite fight approaching soon, I need to stabilize. This rest site is the planned step in the route and allows me to either heal or upgrade a key card like Bullet Time or Predator to increase my power level before the upcoming challenge.
  strategic_note: Foundation stage: Utilizing Predator and Snakebites for front-loaded damage, leveraging Bullet Time to dump high-cost cards. Current priority is balancing HP for upcoming Elites while seeking card draw to make Bullet Time more consistent.

F9 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 36->57 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: At 36 HP, we are at risk of dying to Gremlin Nob or an unfortunate turn against Lagavulin/Sentries, especially since our deck relies on skills like Snakebite and Bullet Time which Nob punishes heavily. Resting to 57 HP ensures we survive the upcoming Elite on F11, allowing us to upgrade safely at the F13 rest site.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through more combats later to scale Max HP with Chosen Cheese, while keeping current HP safe. Upgrade Bullet Time or Neutralize next.

F9 [rest_site] proceed | source=auto
  HP 57->57 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=1) | source=llm
  HP 57->57 | Gold 167->167 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure node. The path leads to an Elite, providing a chance to utilize the current HP buffer and test the deck's frontloaded damage (Predator, Snakebites) for Max HP scaling from Chosen Cheese.
  strategic_note: Foundation stage: Utilizing Predator and Snakebites for frontloaded damage while Bullet Time enables high-impact turns. With Chosen Cheese, we seek combats to scale Max HP, but must prioritize efficient blocking and smithing key cards to survive upcoming Elites.

F10 [treasure] open_chest | source=random
  HP 57->57 | Gold 167->213 | Deck 17->17
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 57->57 | Gold 213->213 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim: Book of Five Rings

F10 [treasure] proceed | source=random
  HP 57->57 | Gold 213->213 | Deck 17->17
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 57->57 | Gold 213->0 | Deck 17->17
  deck_change: no deck change
  reasoning: We have 57/70 HP and a strong frontloaded deck featuring Predator and Bullet Time. This is the ideal time to take an Elite fight to secure a relic and a high-rarity card reward. The route suggests this node, and we have Winged Boots if we need to escape a dangerous path later.
  strategic_note: Foundation stage: Utilizing Predator and Snakebites for heavy early damage, supported by Bullet Time for high-impact turns. Transitioning to focus on Max HP scaling through Chosen Cheese while prioritizing high-value Elite encounters to secure key relics and upgrades.

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 213->252 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 39 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 252->252 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Poison Potion

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 252->252 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim relic: Candelabra

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 252->252 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 47->47 | Gold 252->252 | Deck 17->18
  deck_change: picked Flick-Flack
  reasoning: Flick-Flack adds much-needed AoE to the deck, which we currently lack. Its Sly mechanic synergizes perfectly with our Dagger Throw and Survivor, allowing for free AoE damage while blocking or cycling.
  strategic_note: Committed to poison plan with Snakebites. Look for Catalyst/more poison, discard synergy for Sly cards, and well-laid plans. Keep deck lean and remove basic attacks.

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 47->47 | Gold 252->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the established route to maximize monster encounters for card drafts and Chosen Cheese triggers before the upcoming Elite. I have 252 gold, so I need to find a shop soon, but the immediate priority is strengthening the deck for the mid-Act 1 Elite.
  strategic_note: Foundation stage: Utilizing Predator, Snakebites, and Bullet Time for high-impact turns while scaling Max HP through Chosen Cheese in combat. Need to prioritize defensive card drafts and a shop visit to convert gold into relics or key removals before the Act 1 boss.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 252->269 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Attack Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: no deck change
  reasoning: We are pivoting into a poison strategy with 2x Snakebite and Bullet Time. None of these cards synergize with our poison engine, and Blade Dance / Phantom Blades do not fit our win condition. Keeping the deck lean ensures we draw our Snakebites, mitigation, and Bullet Time more consistently.
  strategic_note: Committed poison plan: Retain Snakebites until Bullet Time or a safe turn to burst poison. Prioritize mitigation, draw, and removal to stall out fights while poison ticks. Skip low-impact attacks.

F12 [map] choose_map_node (option_index=0) | source=llm
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the Route Intelligence to stabilize before the Elite. With 47 HP and a Bullet Time/Predator deck, an upgrade or a small heal is necessary to safely take on an Act 1 Elite. Gold is high (269), so we want to survive to hit a future shop or continue scaling with combats.
  strategic_note: Foundation stage: Deck uses Bullet Time to cheat out expensive high-impact cards like Predator. Priority is upgrading Bullet Time to reduce its cost and adding more high-cost/high-impact cards to leverage the energy cheat while building block density.

F13 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: upgraded Bullet Time->Bullet Time+
  reasoning: With 47 HP and another rest site before the boss, we are healthy enough to smith. Upgrading Bullet Time from 3 to 2 energy is a massive flexibility increase, allowing us to spend 1 energy on card draw (like Dagger Throw) before making the rest of the hand free.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through more combats to scale Max HP with Chosen Cheese. Upgrade Neutralize next for consistency.

F13 [rest_site] proceed | source=auto
  HP 47->47 | Gold 269->269 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=1) | source=llm
  HP 47->47 | Gold 269->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the Route Guide and Strategic Thread to prioritize standard monster encounters for scaling Max HP via Chosen Cheese. While I have Winged Boots and decent gold, an Elite fight here is risky given my 65% HP and the need to preserve health for the Act 1 boss. Standard fights provide safer card rewards and relic scaling.
  strategic_note: Foundation stage: Utilizing Predator and Snakebites for frontloaded damage with Bullet Time for hand dumping. Prioritizing standard monster combats to scale Max HP through Chosen Cheese while preserving current health for the Act 1 boss. Need more consistent block and card draw to support Bullet Time turns.

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 269->281 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 281->281 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 281->281 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 42->42 | Gold 281->281 | Deck 18->19
  deck_change: picked Deadly Poison
  reasoning: Deadly Poison fits into my poison strategy alongside the two Snakebites. Poison bypasses Block, which is helpful, and stacking it efficiently is key for Act bosses. It also gets me closer to the Book of Five Rings heal.
  strategic_note: Committed poison plan: retain Snakebites and look for efficient defense while passive poison kills. Use Bullet Time for heavy setup turns. Need more block scaling and maybe a discard outlet for Flick-Flack.

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 42->42 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: With 281 gold and a healthy HP pool, an Unknown node offers a high-value opportunity for a shop or a beneficial event before the final rest site. While Chosen Cheese rewards combat, the potential for a shop purchase or a card removal is more impactful for the upcoming boss fight than 1 Max HP and a standard card reward.
  strategic_note: Foundation stage: Utilizing Predator, Snakebites, and Bullet Time for high-impact turns. Prioritize high-value shop purchases with 280+ gold and use the final rest site to upgrade a key damage or draw piece to ensure boss victory.

F15 [event] choose_event_option (option_index=0) | source=llm
  HP 42->42 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: Taking Sword of Stone requires zero HP investment, allowing me to safely upgrade at the upcoming rest site. Defeating 5 Elites across Act 2 and 3 is highly achievable and provides a massive long-term power spike compared to the immediate gold.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, while Bullet Time allows explosive hand dumping. Prioritize pathing through Elites to transform Sword of Stone and combats to scale Max HP with Chosen Cheese. Upgrade Neutralize or a key draw piece next.

F15 [event] choose_event_option (option_index=0) | source=auto
  HP 42->42 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: Only option: Proceed

F15 [map] choose_map_node (option_index=0) | source=llm
  HP 42->42 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: Standard pathing to the next rest site before the boss. The choice of column index (0, 1, or 2) is functionally identical as they all lead to the boss, but I will follow the route recommendation.
  strategic_note: Foundation stage: Deck uses Predator and Snakebites for frontload, with Bullet Time for high-impact turns. Focus on upgrading core defensive and utility cards like Neutralize to improve consistency before the Act 1 boss. Maximize Chosen Cheese value by pathing through combats in Act 2.

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 42->63 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: HP is at 42/73 before the Act 1 Boss. Since our deck relies on somewhat slower damage scaling (Snakebites and Predator) and lacks significant defensive powers, the 21 HP from resting provides a crucial buffer to survive the boss's setup phase and major attacks.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, with Bullet Time for explosive turns. Look for discard synergies and card draw in Act 2, and avoid adding more basic attacks.

F16 [rest_site] proceed | source=auto
  HP 63->63 | Gold 281->281 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 63->63 | Gold 281->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [card_select] select_deck_card (option_index=2) | source=llm
  HP 57->57 | Gold 281->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Scrawl will draw a full hand of cards, giving me the best chance to find Defends or other mitigation to block the incoming 18 damage.
  strategic_note: Foundation plan: survive with frontload and efficient block while integrating poison and retain mechanics; look for a core scaling engine.

F17 [card_select] select_deck_card (option_index=0) | source=llm
  HP 43->43 | Gold 281->0 | Deck 19->19
  deck_change: no deck change
  reasoning: We did not find a Weak or Block card from the Attack potion. Precise Cut costs 0 energy, allowing us to spend all our remaining energy on block cards to mitigate the incoming 21 damage. Dagger Spray would cost 1 energy and Grand Finale is likely unplayable.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 16->16 | Gold 281->381 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 16->16 | Gold 381->381 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Duplicator

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 16->16 | Gold 381->381 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 16->16 | Gold 381->381 | Deck 19->20
  deck_change: picked Afterimage
  reasoning: Afterimage provides essential scaling defense, which perfectly complements our passive Poison strategy. It is cheap to play and synergizes well with our Bullet Time+ burst turns, allowing us to generate block while dumping our hand.
  strategic_note: Committed poison plan: retain poison (Snakebite) and use Bullet Time+ for massive free setups. Prioritize survival with Afterimage and efficient block while poison kills. Needs draw and mitigation; skip basic attacks.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 16->62 | Gold 381->381 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0) | source=llm
  HP 62->62 | Gold 381->381 | Deck 20->20
  deck_change: no deck change
  reasoning: Yummy Cookie provides 4 permanent upgrades immediately. Upgrading key cards like Predator, Neutralize, Survivor, and Afterimage will significantly boost our frontload and defensive consistency, not just for Act 2 but for the rest of the run. While Storybook synergizes with Chosen Cheese, 4 free upgrades offer an incredible and permanent power spike with zero downside.
  strategic_note: Foundation stage: Early deck relies on Predator and Snakebites for damage, with Bullet Time for explosive turns. Look for discard synergies and card draw in Act 2, and avoid adding more basic attacks. Maximize Chosen Cheese value by pathing through combats and Elites.

F18 [card_select] select_deck_card (option_index=10) | source=llm
  HP 62->62 | Gold 381->381 | Deck 20->20
  deck_change: upgraded Afterimage->Afterimage+, Neutralize->Neutralize+, Snakebite->Snakebite+; changed: +Snakebite+; -Snakebite
  reasoning: Neutralize gaining +1 Weak is premium mitigation. The two Snakebites are our primary scaling engine, so +3 Poison each significantly boosts our boss-killing potential. Afterimage gaining Innate guarantees our block scaling is active from Turn 1, taking advantage of our +2 Turn 1 draw from Ring of the Snake.
  strategic_note: Committed poison plan: survive with Afterimage and frontload damage while applying retained poison for scaling. Needs more efficient mitigation, card draw, and removal of basic Strikes.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 62->62 | Gold 381->381 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 62->62 | Gold 381->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Follows the recommended route leading to an early shop to utilize 381 gold. While Act 2 monsters are dangerous, starting with a hallway fight allows for evaluating the deck's defensive consistency before hitting a shop for key upgrades or removals.
  strategic_note: Foundation stage: Deck relies on Predator and Snakebites for frontload with Bullet Time for high-impact turns. Focus on scouting defensive consistency in early Act 2 hallways while pathing toward shops to convert high gold reserves into permanent power or card removals.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 381->391 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 391->391 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Powdered Demise

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 391->391 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 55->55 | Gold 391->391 | Deck 20->21
  deck_change: picked Blade Dance+
  reasoning: Blade Dance+ is highly efficient, providing 16 damage for 1 energy. Crucially, it synergizes extremely well with our Innate Afterimage+, turning into 5 Block and 16 damage for 1 energy, and it exhausts so it won't clutter our cycle later.
  strategic_note: Committed poison/retain plan: Retain Snakebites for massive burst damage on safe turns, utilizing Bullet Time to dump hands. Afterimage provides passive defense while we stall for poison kills. Seek more discard to trigger Sly, and card draw/retain pieces.

F19 [map] choose_map_node (option_index=3) | source=llm
  HP 55->55 | Gold 391->391 | Deck 21->21
  deck_change: no deck change
  reasoning: I have 391 gold and the route intelligence suggests aggressive spending at shops is highly effective in Act 2. This shop allows me to look for critical scaling pieces, card removal, or powerful relics to support my Bullet Time/Predator engine before a series of monster encounters.
  strategic_note: Foundation stage: Leveraging high gold at the shop to find discard synergies or defensive scaling to support Bullet Time and Predator. Avoid adding basic attacks and prioritize card quality and removals to improve draw consistency.

F20 [shop] buy_card (option_index=3) | source=plan
  HP 55->75 | Gold 391->355 | Deck 21->22
  deck_change: bought Acrobatics
  reasoning: Shop plan [1/4]: Crucial cheap draw to cycle the deck, find our Snakebites, and discard Sly cards or useless basics.

F20 [shop] remove_card_at_shop | source=plan
  HP 75->75 | Gold 355->355 | Deck 22->22
  deck_change: no deck change
  reasoning: Shop plan [2/4]: Removing a Strike increases the density of our defensive cards and poison win condition.

F20 [card_select] select_deck_card (option_index=0) | source=llm
  HP 75->75 | Gold 355->280 | Deck 22->21
  deck_change: lost Strike
  reasoning: Strikes are dead weight in our deck, which is transitioning to a poison engine with Snakebite+ and Deadly Poison. Removing a Strike increases our draw consistency for defensive cards, poison setup, and Afterimage.
  strategic_note: Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Remove basic attacks to improve consistency. Look for more poison scaling, block/dexterity, and discard synergy for Flick-Flack.

F20 [shop] buy_relic (option_index=2) | source=plan
  HP 75->75 | Gold 280->103 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Provides passive block scaling as we cycle our deck, synergizing well with Acrobatics and our thinned out deck.

F20 [shop] buy_potion (option_index=0) | source=plan
  HP 75->75 | Gold 103->54 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan [4/4]: Excellent defensive tool for the upcoming Act 2 Boss (Crusher+Rocket) or a difficult Elite.

F20 [shop] close_shop_inventory | source=plan
  HP 75->75 | Gold 54->54 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F20 [shop] proceed | source=auto
  HP 75->75 | Gold 54->54 | Deck 21->21
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F20 [map] choose_map_node (option_index=3) | source=llm
  HP 75->75 | Gold 54->0 | Deck 21->21
  deck_change: no deck change
  reasoning: With 100% HP, I can afford an Act 2 hallway fight to hunt for necessary discard and draw engine pieces as noted in the strategic thread. Expert knowledge suggests testing the deck's defensive consistency early in the act while the health buffer is full, despite the general Act 2 warning against monsters.
  strategic_note: Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Currently seeking discard synergies and card draw to stabilize the engine while avoiding unnecessary basic attacks.

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 74->74 | Gold 54->69 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 74->74 | Gold 69->69 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 74->74 | Gold 69->69 | Deck 21->22
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a premium defensive card against multi-attackers and multi-enemy encounters, which are prevalent in Act 2. It will significantly reduce damage from Crusher's multi-attacks in the upcoming boss fight.
  strategic_note: Foundation plan: surviving with Predator and Snakebite poison while leveraging Bullet Time for burst turns. Prioritize draw, removals, and a consistent scaling engine.

F21 [map] choose_map_node (option_index=2) | source=llm
  HP 74->74 | Gold 69->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended route to a monster encounter. High current HP (74/76) allows for aggressive card drafting to find the discard synergies and draw mechanics the deck currently lacks. Avoiding Elites as per Route Intelligence for Act 2 Silent.
  strategic_note: Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Transitioning to discard and draw synergies is the priority to maximize Bullet Time and Snakebites. HP is high, so hunting for foundational synergy cards in hallway fights is the current goal while avoiding Act 2 Elites.

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 72->72 | Gold 69->80 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 72->72 | Gold 80->80 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 72->72 | Gold 80->80 | Deck 22->23
  deck_change: picked Footwork
  reasoning: Footwork is premium defensive scaling, providing the Dexterity needed to make our Defends and Survivor highly effective while we wait for our Snakebite poison to kill enemies.
  strategic_note: Committed poison plan: retain Snakebite+ and use Bullet Time to play massive hands, then defend while passive poison kills. Relies on Footwork and Afterimage for block scaling; prioritize card draw and removal of basic Strikes.

F22 [map] choose_map_node (option_index=2) | source=llm
  HP 72->72 | Gold 80->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to a standard monster encounter. At 72/77 HP, I am healthy enough to handle Act 2 hallways, and I need to continue drafting cards to support my Bullet Time and Predator foundation, specifically looking for card draw or discard outlets to improve deck consistency.
  strategic_note: Foundation stage: Deck uses Predator and Snakebites for frontload damage, supported by Bullet Time for high-impact turns. Now seeking card draw (Acrobatics, Backflip) and discard synergies to cycle into power turns faster and handle the high damage of Act 2 hallways.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 80->93 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 93->93 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 93->93 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 68->68 | Gold 93->93 | Deck 23->24
  deck_change: picked Bouncing Flask
  reasoning: Bouncing Flask is a core poison generator that synergizes beautifully with Bullet Time and our existing poison package (Snakebite+, Deadly Poison). It provides excellent damage scaling against bosses and elites, and helps whittle down both enemies in the upcoming Crusher+Rocket fight.
  strategic_note: Committed poison plan: retain Snakebite+ and use Bouncing Flask to stack high poison on priority targets. Defend with Footwork, Afterimage, and Bullet Time while poison ticks down. Keep the deck lean and prioritize removals of Strikes.

F23 [map] choose_map_node (option_index=2) | source=llm
  HP 68->68 | Gold 93->93 | Deck 24->24
  deck_change: no deck change
  reasoning: Following Route Intelligence to prioritize non-combat nodes (Unknown) over Elites in Act 2 to preserve HP. The deck has solid foundation damage but lacks the defensive scaling to safely challenge Act 2 Elites without risk of significant chip damage or death.
  strategic_note: Foundation stage: Leveraging Predator and Bullet Time for high-impact turns while seeking discard synergies and card draw. The deck currently lacks consistent block and scaling, so I am prioritizing non-combat nodes and Rest Sites in Act 2 to maintain HP for the boss.

F24 [treasure] open_chest | source=random
  HP 68->68 | Gold 93->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Open chest

F24 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 68->68 | Gold 136->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim: Juzu Bracelet

F24 [treasure] proceed | source=random
  HP 68->68 | Gold 136->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Proceed from treasure

F24 [map] choose_map_node (option_index=2) | source=llm
  HP 68->68 | Gold 136->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the Route Intelligence and strategic guidelines for Act 2 Silent. Elite fights in Act 2 are high risk for this deck, which relies on Bullet Time and Predator for setup. Juzu Bracelet makes Unknown nodes significantly safer by eliminating combat encounters, allowing for events, shops, or treasures without the risk of chip damage. Choosing the recommended Unknown node (c4,r7) aligns with HP preservation goals.
  strategic_note: Foundation stage: Deck uses Predator and Bullet Time for high-impact turns. Currently seeking discard synergies and improved block scaling to stabilize Act 2. Juzu Bracelet makes Unknown nodes high-value safety detours; avoid Elites until the defense is more consistent.

F25 [shop] buy_card (option_index=4) | source=plan
  HP 68->68 | Gold 136->58 | Deck 24->25
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/2]: Core poison scaling that provides essential AoE passive damage and strips Artifact charges.

F25 [shop] buy_card (option_index=2) | source=plan
  HP 68->78 | Gold 58->33 | Deck 25->26
  deck_change: bought Backflip
  reasoning: Shop plan [2/2]: On sale, provides premium generic block and draw to cycle into our poison engine.

F25 [shop] close_shop_inventory | source=plan
  HP 78->78 | Gold 33->33 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F25 [shop] proceed | source=auto
  HP 78->78 | Gold 33->33 | Deck 26->26
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F25 [map] choose_map_node (option_index=1) | source=llm
  HP 78->78 | Gold 33->33 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to the middle Treasure node. My current deck has high frontloaded damage and Bullet Time, but Act 2 hallway fights are traditionally dangerous for Silent. I need to prioritize non-combat nodes to preserve my full health buffer for the end of the Act.
  strategic_note: Foundation stage: Deck uses Bullet Time to cheat out high-cost damage like Predator and Snakebites. Need more card draw and discard synergies (like Acrobatics or Calculated Gamble) to maximize Bullet Time turns and improve defensive consistency.

F26 [treasure] open_chest | source=random
  HP 78->78 | Gold 33->84 | Deck 26->26
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 78->78 | Gold 84->84 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim: Bowler Hat

F26 [treasure] proceed | source=random
  HP 78->78 | Gold 84->84 | Deck 26->26
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=1) | source=llm
  HP 78->78 | Gold 84->84 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. Even though I am at full HP, the Expert Knowledge for Act 2 emphasizes avoiding Elites and prioritizing non-combat nodes for the Silent. This Rest Site (c2, r9) allows me to upgrade a card to improve my engine's scaling for the upcoming Boss.
  strategic_note: Foundation stage: Deck relies on Predator and Bullet Time; seeking draw and discard synergies to maximize Bullet Time turns while avoiding Act 2 Elites.

F27 [rest_site] choose_rest_option (option_index=1, smith_card_index=14, note_scope=run, note_triggers=all) | source=llm
  HP 78->78 | Gold 84->84 | Deck 26->26
  deck_change: upgraded Acrobatics->Acrobatics+
  reasoning: HP is full, so I must smith. Acrobatics+ increases card draw from 3 to 4, which drastically improves deck consistency, hand size for Bullet Time, and helps find critical powers or discard synergies more reliably.
  strategic_note: Foundation stage: relies on Snakebites, Predator, and Poison (Fumes/Flask) for damage, with Bullet Time for explosive turns. Prioritize card draw and discard synergies to cycle faster.

F27 [rest_site] proceed | source=auto
  HP 78->78 | Gold 84->84 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=2) | source=llm
  HP 78->78 | Gold 84->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to a standard monster encounter. While Act 2 hallways are dangerous, I have full HP and a strong Bullet Time/Predator foundation. Avoiding the Elite is consistent with the Route Intelligence for Silent in Act 2, and the Shop is currently unattractive with only 84 gold.
  strategic_note: Foundation stage: Deck relies on Predator and Bullet Time for high-impact turns. Transitioning into Act 2, I need to find consistent card draw and discard synergies to bridge the gap between heavy-hitting turns, while prioritizing HP preservation over risky Elite fights.

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 79->79 | Gold 84->96 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 79->79 | Gold 96->96 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 79->79 | Gold 96->96 | Deck 26->27
  deck_change: picked Fan of Knives
  reasoning: Fan of Knives provides immediate AoE value (4 Shivs = 16 AoE damage) and scales our Blade Dance+ for the upcoming Crusher+Rocket boss fight, where whittling both enemies down evenly is crucial to handle Crab Rage.
  strategic_note: Committed poison plan with hybrid tools: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards. Fan of Knives adds AoE capability for multi-enemy fights.

F28 [map] choose_map_node (option_index=2) | source=llm
  HP 79->79 | Gold 96->96 | Deck 27->27
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. Since I am at full HP (79/79), this is a perfect opportunity to Smith and upgrade a key card like Bullet Time or Predator to improve deck scaling without risking chip damage from Act 2 hallway fights or Elites.
  strategic_note: Foundation stage: Deck uses Predator and Snakebites for frontload with Bullet Time for high-impact turns. Currently seeking discard synergies and additional card draw to maximize Bullet Time value; prioritize smithing over resting to maintain momentum while HP is high.

F29 [rest_site] choose_rest_option (option_index=1, smith_card_index=15) | source=llm
  HP 79->79 | Gold 96->96 | Deck 27->27
  deck_change: upgraded Footwork->Footwork+
  reasoning: At full HP, we definitely smith. Footwork is a premium upgrade that significantly boosts the value of every block card in the deck, which is crucial for surviving the upcoming Elite fight and Act 2 boss.
  strategic_note: Foundation stage: Deck has a strong mix of AoE shivs (Fan of Knives, Blade Dance) and Poison (Fumes, Flask) for damage, with Footwork/Afterimage for block. Cycle aggressively using Acrobatics and Backflip. Prioritize draw and card removal.

F29 [rest_site] proceed | source=auto
  HP 79->79 | Gold 96->96 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=2) | source=llm
  HP 79->79 | Gold 96->96 | Deck 27->27
  deck_change: no deck change
  reasoning: Following Route Intelligence which prioritizes non-combat chains in Act 2 to preserve HP. The Juzu Bracelet makes Unknown nodes guaranteed non-combat encounters, providing a safe path to the boss while potentially offering high-value events or card removals.
  strategic_note: Foundation stage: Deck uses Bullet Time to cheat out high-cost Predator and Snakebites damage, but lacks consistent block and discard scaling. Prioritize finding Acrobatics or Calculated Gamble to cycle through basics and enable Bullet Time more frequently; avoid unnecessary hallway fights to preserve health for the boss.

F30 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 79->89 | Gold 96->96 | Deck 27->27
  deck_change: no deck change
  reasoning: Trading a replaceable Block Potion for 10 permanent Max HP is incredibly efficient and gives us a huge buffer for the Act 2 Boss and Act 3.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites and Predator or spam Shivs with Fan of Knives and Blade Dance. Prioritize consistent card draw to reliably find Bullet Time and avoid adding more basic attacks.

F30 [event] choose_event_option (option_index=0) | source=auto
  HP 89->89 | Gold 96->96 | Deck 27->27
  deck_change: no deck change
  reasoning: Only option: Proceed

F30 [map] choose_map_node (option_index=2) | source=llm
  HP 89->89 | Gold 96->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Following the recommended route to a standard monster encounter. While the Route Intelligence suggests minimizing Act 2 monsters, I have full HP (89/89) and a solid foundation of Footwork, Afterimage, and Shiv/Poison hybrid damage. Taking the monster fight allows for a card reward to potentially find more draw or defensive consistency before the boss.
  strategic_note: Foundation stage: Deck balances Shiv/Poison damage with strong defensive tools like Footwork and Afterimage. Prioritize card draw and thinning to cycle into key powers faster; look for more Acrobatics or Backflip to stabilize the rotation.

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 77->77 | Gold 96->118 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 22 Gold

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 77->77 | Gold 118->118 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 77->77 | Gold 118->118 | Deck 27->27
  deck_change: no deck change
  reasoning: The deck is currently a well-developed poison setup with Snakebite+ x2, Noxious Fumes, and defensive scaling. None of these options (Slice+, Anticipate, Finisher) meaningfully improve our core engine. Skipping keeps the deck lean to draw Footwork+ and poison pieces faster.
  strategic_note: Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Keep the deck lean and remove basic attacks to improve consistency. Look for block/dexterity and discard synergy.

F31 [map] choose_map_node (option_index=2) | source=llm
  HP 77->77 | Gold 118->118 | Deck 27->27
  deck_change: no deck change
  reasoning: Following the recommended route to the Rest Site before the Boss. With 77/90 HP, I will most likely Smith to upgrade a key card like After Image or Footwork to maximize scaling for the Act 2 Boss.
  strategic_note: Foundation stage: Deck balances AoE shivs and poison for damage, supported by Footwork and After Image. Cycle through the deck with Acrobatics and Backflip while prioritizing upgrades on core powers and defensive consistency.

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=16) | source=llm
  HP 77->77 | Gold 118->118 | Deck 27->27
  deck_change: upgraded Noxious Fumes->Noxious Fumes+
  reasoning: With 77/90 HP, we are healthy enough to skip the minor 13 HP heal in favor of a critical upgrade before the Act 2 Boss. Noxious Fumes is our primary continuous scaling damage for the boss fight; upgrading it from 2 to 3 poison per turn represents a massive 50% increase in passive damage output over a long fight.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Keep cycling aggressively to find Bullet Time and defensive powers.

F32 [rest_site] proceed | source=auto
  HP 77->77 | Gold 118->118 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 77->77 | Gold 118->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 118->243 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 125 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 243->243 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Distilled Chaos

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 243->243 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 50->50 | Gold 243->243 | Deck 27->28
  deck_change: picked Malaise
  reasoning: Malaise is a premium defensive card against multi-hit bosses like Crusher/Rocket, Time Eater, and Awakened One. Even with 3 energy, playing it for -3 Strength is enough to cripple a dangerous multi-attacker for the rest of the fight.
  strategic_note: Committed poison plan: retain high-yield poison like Snakebite for burst turns, stack defensive scaling (Dex, Weak) to stall. Prioritize card removal and skip non-synergistic attacks.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 50->82 | Gold 243->243 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=0) | source=llm
  HP 82->82 | Gold 243->243 | Deck 28->28
  deck_change: no deck change
  reasoning: Sai provides an unconditional 7 Block every single turn, which heavily mitigates chip damage and provides massive value over long boss fights. We don't need Maul scaling (Claws), and we don't need additional rest site utility (Meat Cleaver) as our deck already has good defensive synergy with After Image and Footwork.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Keep cycling aggressively to find Bullet Time and defensive powers.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 82->82 | Gold 243->243 | Deck 28->28
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 82->82 | Gold 243->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Following the recommended route to enter the center-right column. Act 2 hallway fights are dangerous, but this path leads to a series of Unknown nodes (made safer by Juzu Bracelet) and early Shops to spend my 243 gold on scaling or removal. The goal is to reach the mid-act shops while preserving HP.
  strategic_note: Foundation stage: Balancing AoE shivs and poison for damage, supported by Footwork and After Image. Use Acrobatics and Backflip to cycle into core powers and defensive consistency; prioritizing upgrades on scaling pieces while using Juzu Bracelet to navigate Unknown nodes safely.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 243->263 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 20 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 263->263 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Powdered Demise

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 83->83 | Gold 263->263 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 83->83 | Gold 263->263 | Deck 28->29
  deck_change: picked Calculated Gamble
  reasoning: Calculated Gamble is a premium hand-cycling tool that helps us dig for our critical setup cards (Afterimage+, Footwork+, Noxious Fumes+) early in the fight. It costs 0 energy, exhausts to thin the deck afterward, and synergizes with The Abacus to accelerate shuffles for extra block.
  strategic_note: Committed poison plan: apply poison with Snakebite+ and defend with Afterimage+. Retain combo pieces for big Burst or Bullet Time turns. Avoid generic attacks and prioritize basic attack removals.

F35 [map] choose_map_node (option_index=3) | source=llm
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: Juzu Bracelet guarantees that this Unknown node will not be a combat encounter, making it a safe way to find high-value Act 3 events or items without risking chip damage. Following the recommended route to preserve HP for the final boss.
  strategic_note: Committed poison-shiv hybrid: use Bullet Time to cheat out Snakebites and Predator. Leverage Juzu Bracelet to navigate Unknown nodes safely for events and shops while avoiding unnecessary chip damage. Aiming for more defensive scaling or poison multipliers to secure the Act 3 boss kill.

F36 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: Book of Five Rings provides very limited value this late in the run since we won't be adding many more cards to our 29-card deck. Trading it for Gorget is a massive defensive upgrade, providing 4 Plating (4 passive block per turn until taking unblocked damage) in every combat. Combined with Sai, this gives us excellent passive mitigation against chip damage.
  strategic_note: Committed poison-shiv hybrid: use Bullet Time to cheat out Snakebites and Predator. Leverage Juzu Bracelet to navigate Unknown nodes safely for events and shops while avoiding unnecessary chip damage. Passive block from Sai, Gorget, and Afterimage handles incoming damage while Fumes and poison build up.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=2) | source=llm
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: Following the recommended route to prioritize Unknown nodes. With Juzu Bracelet, ? rooms are safe from monster encounters, allowing us to fish for beneficial events while preserving HP. Gold is sufficient (263) for the upcoming shops later in the path.
  strategic_note: Committed poison and shiv hybrid: utilize Bullet Time to deploy high-cost cards like Snakebite and Predator while Noxious Fumes scales damage. Focus on cycling into defensive powers and keeping high HP for the boss. Avoid unnecessary elite fights despite Sword of Stone, as survival and reliable scaling are the current priorities.

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [map] choose_map_node (option_index=2) | source=llm
  HP 83->83 | Gold 263->263 | Deck 29->29
  deck_change: no deck change
  reasoning: With 263 gold, the shop is a high-value node to hunt for scaling powers (Wraith Form, Footwork, or more Poison) or key relics to supplement the Bullet Time engine. This follows the Route Intelligence recommendation to utilize shops when gold reserves are sufficient.
  strategic_note: Committed poison and shiv hybrid: utilize Bullet Time to cheat out Snakebite and Predator while Noxious Fumes scales; prioritize finding more defensive scaling or card draw at shops to ensure Bullet Time is consistently impactful.

F38 [shop] buy_card (option_index=4) | source=plan
  HP 83->83 | Gold 263->185 | Deck 29->30
  deck_change: bought Well-Laid Plans
  reasoning: Shop plan [1/3]: Crucial setup power to hold situational answers like Piercing Wail/Malaise or combo pieces like Bullet Time.

F38 [shop] remove_card_at_shop | source=plan
  HP 83->83 | Gold 185->185 | Deck 30->30
  deck_change: no deck change
  reasoning: Shop plan [2/3]: Removing a basic Strike improves our draw density to find our poison engine faster.

F38 [card_select] select_deck_card (option_index=0) | source=llm
  HP 83->83 | Gold 185->85 | Deck 30->29
  deck_change: lost Strike
  reasoning: Strike is the lowest value card in a poison-focused deck. Removing it increases consistency and helps us draw defensive and scaling cards faster.
  strategic_note: Committed poison plan: survive with block and debuffs while stacking poison on priority targets using Snakebite and Bouncing Flask. Retain poison with Well-Laid Plans for safe turns. Use Bullet Time for expensive hands. Keep removing basic Strikes to draw scaling faster.

F38 [shop] buy_card (option_index=2) | source=plan
  HP 83->83 | Gold 85->35 | Deck 29->30
  deck_change: bought Piercing Wail
  reasoning: Shop plan [3/3]: A second Piercing Wail is incredibly valuable for Act 3 multi-attackers and the Heart.

F38 [shop] close_shop_inventory | source=plan
  HP 83->83 | Gold 35->35 | Deck 30->30
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F38 [shop] proceed | source=auto
  HP 83->83 | Gold 35->35 | Deck 30->30
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F38 [map] choose_map_node (option_index=3) | source=llm
  HP 83->83 | Gold 35->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the Route Intelligence recommendation to take a monster encounter. With 83 HP and a solid deck featuring Bullet Time and scaling damage (Poison/Shiv), I can handle Act 3 hallways to potentially gain card rewards or gold for the upcoming shop. This node (c4,r5) maintains the path toward the rest site and subsequent shop.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost cards like Snakebite and Predator while Noxious Fumes scales. Prioritize cycling to find Bullet Time and defensive pieces; avoid adding low-impact cards.

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 35->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 84->84 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 84->84 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Our deck has a solid poison core with Noxious Fumes+, 2x Snakebite+, Bouncing Flask, and Deadly Poison. We also have incredible defensive tools (Footwork+, Afterimage+, Piercing Wails, Malaise, and defensive relics). None of these cards significantly improve our deck, so skipping keeps our draws more consistent for finding our key powers and engine pieces.
  strategic_note: Committed poison/defense plan: rely on passive defense relics, Afterimage, and Footwork while stacking poison with Retain pieces (Snakebite+) and Noxious Fumes. Keep deck thin to draw into powers and mitigation quickly.

F39 [map] choose_map_node (option_index=2) | source=llm
  HP 84->84 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With Juzu Bracelet, Unknown nodes are guaranteed to be non-combat, providing a safe path to preserve HP for the Act 3 boss while looking for events that might offer upgrades or removals.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites and Predator while Fumes scales; with Juzu Bracelet, prioritize Unknown nodes to avoid chip damage and find safe utility.

F40 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 84->69 | Gold 52->52 | Deck 30->30
  deck_change: upgraded Calculated Gamble->Calculated Gamble+, Deadly Poison->Deadly Poison+
  reasoning: Big Mushroom ruins the opening hand consistency by reducing starting draw by 2, which would negate Ring of the Snake and delay critical setup. Taking 15 damage for 2 random upgrades is a highly favorable trade, and at 84 HP we can easily afford the cost before the upcoming Rest Site and Elite.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget.

F40 [event] choose_event_option (option_index=0) | source=auto
  HP 69->69 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F40 [map] choose_map_node (option_index=2) | source=llm
  HP 69->69 | Gold 52->52 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure room at c6,r7. This path leads toward a Rest Site and Shop while maintaining flexibility for the upcoming Elite, which is necessary to progress the Sword of Stone.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites, Predator, and setup powers while Fumes provides passive scaling. Prioritize finding defensive tools to survive the setup turns and use Winged Boots charges only if a forced high-damage elite path must be avoided later.

F41 [treasure] open_chest | source=random
  HP 69->69 | Gold 52->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim: Potion Belt

F41 [treasure] proceed | source=random
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=1) | source=llm
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. With 69 HP, I am healthy enough to prioritize a Smith upgrade to improve the deck's scaling before the final stretch of Act 3. Avoiding the Elite is consistent with the current strategy of minimizing chip damage and preserving health for the Act 3 boss.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out high-cost Snakebites and setup powers like Noxious Fumes. Prioritize upgrades on core scaling and defensive pieces to ensure survival while poison stacks. Avoid unnecessary Elite fights in Act 3 to preserve HP for the final encounter.

F42 [rest_site] choose_rest_option (option_index=1, smith_card_index=17, note_scope=run, note_triggers=all) | source=llm
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: upgraded Well-Laid Plans->Well-Laid Plans+
  reasoning: 69 HP is a comfortable buffer for Act 3 with our defensive package (Afterimage+, Footwork+, Malaise, Piercing Wails). Upgrading Well-Laid Plans to retain 2 cards drastically improves consistency, allowing us to hold both Bullet Time and an expensive payoff, or retain situational block/debuffs for crucial turns.
  strategic_note: Committed poison/shiv hybrid: Retain combo pieces with Well-Laid Plans to cheat out high-cost cards using Bullet Time, while Noxious Fumes provides scaling. Focus on surviving and drawing aggressively while mitigating chip damage.

F42 [rest_site] proceed | source=auto
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=2) | source=llm
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to the Shop. With 105 gold, I can potentially afford a crucial card removal, a key common relic, or a high-impact potion. Given the low HP loss in recent floors and the 'Route Intelligence' warning about Act 3 elites, I need to evaluate if I can strengthen the deck's defensive consistency or poison scaling before the next forced Elite or Boss.
  strategic_note: Committed poison-shiv hybrid: use Bullet Time to deploy Snakebites and Predator while Fumes scales. Focus on acquiring more defensive consistency or card draw to ensure Bullet Time is impactful every cycle.

F43 [shop] close_shop_inventory | source=llm
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F43 [shop] proceed | source=auto
  HP 69->69 | Gold 105->105 | Deck 30->30
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F43 [map] choose_map_node (option_index=2) | source=llm
  HP 69->69 | Gold 105->0 | Deck 30->30
  deck_change: no deck change
  reasoning: I am currently at 69/93 HP and have the Sword of Stone relic which needs 5 Elite kills to transform. Taking this Elite fight is necessary to unlock that power spike before the Act 3 boss. My Bullet Time/Snakebite engine should be able to handle the burst requirements of Act 3 Elites.
  strategic_note: Committed poison and shiv hybrid: use Bullet Time to cheat out high-cost cards like Snakebites and Predator while Fumes scales; prioritize taking Elites to finish the Sword of Stone quest before the final boss.

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 105->161 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 56 Gold

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 161->161 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim relic: Kunai

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 161->161 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F44 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 61->61 | Gold 161->161 | Deck 30->31
  deck_change: picked Accelerant
  reasoning: Accelerant is the ultimate multiplier for our heavy poison application. It makes poison tick twice per turn, effectively doubling our poison damage and drastically reducing the time needed to kill Act 3 bosses.
  strategic_note: Committed poison plan: survive with block and debuffs while stacking heavy poison via Snakebite, Bouncing Flask, and Fumes. Play Accelerant to double poison ticks. Retain key cards with Well-Laid Plans for safe, explosive turns.

F44 [map] choose_map_node (option_index=3) | source=llm
  HP 61->61 | Gold 161->161 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the Route Intelligence and strategic thread to prioritize Unknown nodes in Act 3. Juzu Bracelet makes Unknown nodes safe from monster encounters, which is critical for preserving HP for the boss given our current 65% HP. We have Winged Boots if we need to adjust pathing later, but for now, the recommended Unknown node minimizes risk.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and avoiding unnecessary damage before the final boss.

F45 [event] choose_event_option (option_index=0) | source=llm
  HP 61->61 | Gold 161->161 | Deck 31->31
  deck_change: upgraded Defend->Defend+, Flick-Flack->Flick-Flack+, Strike->Strike+; changed: +Noxious Fumes, Snakebite, Strike+; -Noxious Fumes+, Snakebite+, Strike
  reasoning: Duplicating the entire deck and gaining an Eternal curse would completely destroy the deck's consistency and draw engine. Downgrading 2 random cards and upgrading 4 random cards is a relatively minor variance play that gives a net +2 upgrades, which is vastly superior.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and avoiding unnecessary damage before the final boss.

F45 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 161->161 | Deck 31->31
  deck_change: no deck change
  reasoning: Only option: Proceed

F45 [map] choose_map_node (option_index=3) | source=llm
  HP 61->61 | Gold 161->161 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the Route Intelligence recommendation to prioritize Unknown nodes and avoid Elites in Act 3 to preserve HP for the final boss. With Juzu Bracelet, the Unknown node is guaranteed to be non-combat, providing a safe transition toward the final campfire and boss.
  strategic_note: Committed poison/shiv hybrid: Use Well-Laid Plans to set up Bullet Time turns for high impact, while Noxious Fumes provides the necessary scaling. Focus on maximizing block and draw consistency to mitigate chip damage; prioritizing safety via Unknown nodes and Rest Sites to ensure high HP for the Act 3 boss.

F46 [shop] buy_card (option_index=4) | source=plan
  HP 61->61 | Gold 161->125 | Deck 31->32
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/2]: On sale, perfectly fits our core poison scaling engine by accelerating passive damage and ticking Accelerant more effectively in long fights.

F46 [shop] remove_card_at_shop | source=plan
  HP 61->61 | Gold 125->125 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Perfectly utilizes the remaining gold to remove a base Strike, increasing the density of our defensive and scaling cards in a 31-card deck.

F46 [card_select] select_deck_card (option_index=0) | source=llm
  HP 61->61 | Gold 125->0 | Deck 32->31
  deck_change: lost Strike
  reasoning: We are heavily committed to a poison and defensive scaling engine. Unupgraded Strike is the worst card in the deck and dilutes our draws.
  strategic_note: Committed poison plan: rely on passive Noxious Fumes and targeted poison application while surviving with Footwork, Afterimage, and Kunai-fueled block. Avoid adding generic attacks and prioritize card draw and removal.

F46 [shop] close_shop_inventory | source=llm
  HP 61->61 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F46 [shop] proceed | source=auto
  HP 61->61 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F46 [map] choose_map_node (option_index=2) | source=llm
  HP 61->61 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Rest site is mandatory before the Act 3 boss. I am at 65% HP and need to decide between healing and smithing based on the final boss preview, but securing the campfire node is the priority. The route recommendation is sound as it aligns with the final path to the boss.
  strategic_note: Committed poison/shiv hybrid: use Well-Laid Plans to set up Bullet Time for high-impact turns while Noxious Fumes scales damage. Prioritize defensive consistency and card draw to ensure setup occurs before taking critical damage. Focus on upgrading core scaling or mitigation at the final rest site.

F47 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 61->89 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: With the Act 3 Boss fight immediately ahead and our deck relying on slow-scaling poison (Noxious Fumes, Snakebite, Accelerant) for damage, we need to guarantee survival during the setup phase. Healing 28 HP provides a massive buffer to absorb unavoidable damage and is far more valuable than a single card upgrade.
  strategic_note: Committed poison and shiv hybrid: Use Bullet Time to cheat out Snakebites, Predator, and setup powers, while Fumes provides passive scaling. Prioritize draw and mitigate chip damage using passive block relics like Sai and Gorget. Focus on defensive consistency and surviving the setup phase.

F47 [rest_site] proceed | source=auto
  HP 89->89 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 89->89 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 89->89 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 89->0 | Gold 0->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (7 replays)
[Selected: run_combat] Sludge Spinner (F2, monster)
Historical: loss=3 vs historical avg=0.3+/-0.5 (z=5.7, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs Sludge Spinner (Floor 2, monster)
Relics: Ring of the Snake, Winged Boots
Deck (12): Defend x5, Strike x5, Neutralize, Survivor
Enemies: Sludge Spinner HP=37/37

### Round 1
Intent: Sludge Spinner: Attack(8), Debuff
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 2
Agent plan (hypothesis): Enemy will be at 15 HP next turn, should be an easy kill since we're no longer Weak.
Intent: Sludge Spinner: Attack(11)
  Neutralize -> Sludge Spinner[0]
    enemy_deltas: Sludge Spinner: hp -2, +Weak(1)
  Defend
    energy -1 | block +5
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -4
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -4
  turn_end

### Round 3
Agent plan (hypothesis): Enemy is at 3 HP next turn, will easily die.
Intent: Sludge Spinner: Attack(8), Debuff
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 4
Intent: Sludge Spinner: Attack(6), Buff
  Strike -> Sludge Spinner[0]
    energy -1 | -Weak | enemy_deltas: Sludge Spinner: DIED
## Combat Analytics: Sludge Spinner (WIN - 4 rounds)

Cards played (with descriptions):
  Strike "Deal 6 damage." -> 7 plays, 32 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Neutralize "Deal 2 damage. Apply 1 Weak." -> 1 plays, 2 dmg
  Defend "Gain 5 Block." -> 1 plays, 5 block
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Sludge Spinner (Floor 3, monster)
Relics: Ring of the Snake, Silver Crucible
Deck (13): Defend x5, Strike x5, Neutralize, Predator+, Survivor
Enemies: Sludge Spinner HP=38/38

### Round 1
Intent: Sludge Spinner: Attack(8), Debuff
  Fruit Juice
    hp +5
  Neutralize -> Sludge Spinner[0]
    enemy_deltas: Sludge Spinner: hp -3, +Weak(1)
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -6
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 2
Intent: Sludge Spinner: Attack(6), Buff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Sludge Spinner[0]
    energy -1 | enemy_deltas: Sludge Spinner: hp -4
  turn_end

### Round 3
Intent: Sludge Spinner: Attack(14)
  Predator+ -> Sludge Spinner[0]
    energy -2 | enemy_deltas: Sludge Spinner: DIED
## Combat Analytics: Sludge Spinner (WIN - 3 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Strike "Deal 6 damage." -> 3 plays, 16 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:3

[Selected: run_combat] multi:Corpse Slug+Corpse Slug (F4, monster)
Historical: loss=10 vs historical avg=1.8+/-1.1 (z=7.6, WORSE_THAN_USUAL, n=4)
## Combat Replay: vs multi:Corpse Slug+Corpse Slug (Floor 4, monster)
Relics: Ring of the Snake, Winged Boots
Deck (14): Defend x5, Strike x5, Neutralize, Predator, Snakebite, Survivor
Enemies: Corpse Slug HP=26/26, Corpse Slug HP=27/27

### Round 1
Agent plan (hypothesis): Damage evenly so that we can burst the survivor while stunned.
Intent: Corpse Slug: Debuff, Corpse Slug: Attack(3x2=6)
  Defend
    energy -1 | block +5
  Strike -> Corpse Slug[0]
    energy -1
  Strike -> Corpse Slug[1]
    energy -1 | enemy_deltas: Corpse Slug: hp -6
  turn_end

### Round 2
Agent plan (hypothesis): Kill Slug 1 next turn to stun Slug 0.
Intent: Corpse Slug: Attack(3x2=6), Corpse Slug: Attack(8)
  Neutralize -> Corpse Slug[0]
  Predator -> Corpse Slug[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Corpse Slug: hp -15
  Defend
    energy -1 | block +3
  turn_end

### Round 3
Agent plan (hypothesis): Finish Slug 0 next turn.
Agent plan (hypothesis): Kill the Slug next turn before it attacks.
Intent: Corpse Slug: Attack(8), Corpse Slug: Debuff
  Strike -> Corpse Slug[1]
    energy -1 | enemy_deltas: Corpse Slug: hp +11, +Strength(4)
  Strike -> Corpse Slug[0]
    energy -1 | enemy_deltas: Corpse Slug: hp -6
  Strike -> Corpse Slug[0]
    energy -1 | enemy_deltas: Corpse Slug: hp -6
  turn_end

### Round 4
Intent: Corpse Slug: Attack(12)
  Strike -> Corpse Slug[0]
    energy -1 | enemy_deltas: Corpse Slug: DIED
## Combat Analytics: multi:Corpse Slug+Corpse Slug (WIN - 4 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 2 plays, 8 block
  Strike "Deal 6 damage." -> 6 plays, 18 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg

Enemy power timeline:
  Ravenous: R1:- -> R2:- -> R3:- -> R4:4
  Ravenous[0]: R1:4 -> R2:4 -> R3:4 -> R4:-
  Ravenous[1]: R1:4 -> R2:4 -> R3:4 -> R4:-
  Strength: R1:- -> R2:- -> R3:- -> R4:4
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Corpse Slug+Corpse Slug (Floor 4, monster)
Relics: Ring of the Snake, Neow's Torment
Deck (15): Defend x5, Strike x5, Dagger Throw, Neow's Fury, Neutralize, Predator, Survivor
Enemies: Corpse Slug HP=25/25, Corpse Slug HP=26/26

### Round 1
Intent: Corpse Slug: Attack(8), Corpse Slug: Debuff
  Predator -> Corpse Slug[0]
    energy -2 | +Draw Cards Next Turn(2)
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Corpse Slug: Debuff, Corpse Slug: Attack(3x2=6)
  Neutralize -> Corpse Slug[1]
    enemy_deltas: Corpse Slug: hp -3, +Weak(1)
  Dagger Throw -> Corpse Slug[1]
    energy -1 | enemy_deltas: Corpse Slug: hp -9
  Defend
  Strike -> Corpse Slug[1]
    energy -1 | enemy_deltas: Corpse Slug: hp -6
  Survivor
    energy -1 | block +6
  Defend
  turn_end

### Round 3
Intent: Corpse Slug: Attack(3x2=6), Corpse Slug: Attack(8)
  Neutralize -> Corpse Slug[0]
  Predator -> Corpse Slug[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Corpse Slug: +Strength(4)
  Dagger Throw -> Corpse Slug[0]
    energy -1 | -Frail | -Draw Cards Next Turn | enemy_deltas: Corpse Slug: DIED
## Combat Analytics: multi:Corpse Slug+Corpse Slug (WIN - 3 rounds)

Cards played (with descriptions):
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays
  Defend "Gain 5 Block." -> 1 plays, 5 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 3 dmg
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 9 dmg
  Strike "Deal 6 damage." -> 1 plays, 6 dmg
  Survivor "Gain 6 Block. Discard 1 card." -> 1 plays, 6 block

Enemy power timeline:
  Ravenous[0]: R1:4 -> R2:4 -> R3:4
  Ravenous[1]: R1:4 -> R2:4 -> R3:4

[Selected: elite] Skulking Colony (F11, elite)
## Combat Replay: vs Skulking Colony (Floor 11, elite)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings
Deck (17): Defend x5, Strike x5, Snakebite x2, Bullet Time, Dagger Throw, Neutralize, Predator, Survivor
Enemies: Skulking Colony HP=70/70

### Round 1
Agent plan (hypothesis): If Neutralize is drawn, use it to apply Weak. If Survivor, use it for 8 block. Otherwise, play 2 Defends.
Agent plan (hypothesis): Hold the Snakebites until energy is free. Poison damages on enemy turn start.
Intent: Skulking Colony: Attack(12)
  Dagger Throw -> Skulking Colony[0]
    energy -1 | enemy_deltas: Skulking Colony: hp -9
  Strike
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Skulking Colony: Attack(14), Defend
  Bullet Time
    energy -3 | +No Draw(1)
  Neutralize -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -3, +Weak(1)
  Defend
    block +5
  Defend
    block +5
  Snakebite -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: +Poison(7)
  Snakebite -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: Poison(7→14)
  Strike -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -6
  turn_end
    -No Draw

### Round 3
Intent: Skulking Colony: Attack(9), Buff
  Predator -> Skulking Colony[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Skulking Colony: hp -5, block -10
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): If Neutralize is drawn, play it to mitigate the multi-attack. Then spend remaining 2 energy on Defends.
Agent plan (hypothesis): Poison will deal 12 damage at the start of enemy turn. Will easily finish it next round.
Intent: Skulking Colony: Attack(9x2=18)
  Dagger Throw -> Skulking Colony[0]
    energy -1 | enemy_deltas: Skulking Colony: hp -9
  Strike
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Skulking Colony: Attack(14)
  Bullet Time
    energy -3 | +No Draw(1)
  Neutralize -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -3, +Weak(1)
  Defend
    block +5
  Defend
    block +5
  Strike -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -6
  Snakebite -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: Poison(11→18)
  Snakebite -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: Poison(18→25)
  turn_end
    -No Draw

### Round 6
Agent plan (hypothesis): Combat ends.
Intent: Skulking Colony: Attack(16), Defend
  Strike -> Skulking Colony[0]
    energy -1 | hp +1 | enemy_deltas: Skulking Colony: DIED
## Combat Analytics: Skulking Colony (WIN - 6 rounds)

Cards played (with descriptions):
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 18 dmg
  Defend "Gain 5 Block." -> 8 plays, 40 block
  Bullet Time "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 2 plays
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 6 dmg
  Snakebite "Retain. Apply 7 Poison." -> 4 plays, +28 poison
  Strike "Deal 6 damage." -> 3 plays, 12 dmg
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 5 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block

Poison stacks applied per card:
  Snakebite: 28 stacks

Enemy power timeline:
  Hardened Shell: R1:15 -> R2:15 -> R3:15 -> R4:15 -> R5:15 -> R6:15
  Poison: R1:- -> R2:- -> R3:13 -> R4:12 -> R5:11 -> R6:24
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs Skulking Colony (Floor 15, elite)
Relics: Ring of the Snake, New Leaf, Lantern, Bronze Scales
Deck (17): Defend x5, Strike x2, Accelerant, Alchemize, Bubble Bubble, Deflect, Echoing Slash+, Expertise, Neutralize+, Poisoned Stab, Precise Cut, Survivor
Enemies: Skulking Colony HP=70/70

### Round 1
Intent: Skulking Colony: Attack(12)
  Deflect
    block +4
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Echoing Slash+
    energy -1 | enemy_deltas: Skulking Colony: hp -13
  Precise Cut -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -2
  Expertise
    energy -1
  turn_end

### Round 2
Intent: Skulking Colony: Attack(14), Defend
  Neutralize+ -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -4, +Weak(2)
  Block Potion
    block +12
  Alchemize
    energy -1 | exhausted: Alchemize [1]: Procure a random potion. Exhaust.
  Poisoned Stab -> Skulking Colony[0]
    energy -1 | enemy_deltas: Skulking Colony: hp -6, +Poison(3)
  Strike -> Skulking Colony[0]
    energy -1 | enemy_deltas: Skulking Colony: hp -5
  turn_end

### Round 3
Intent: Skulking Colony: Attack(6), Buff
  Defend
    energy -1 | block +5
  Neutralize+ -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: block -4, Weak(1→3)
  Precise Cut -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -3, block -6
  Expertise
    energy -1
  Deflect
    block +4
  Bubble Bubble -> Skulking Colony[0]
    energy -1 | enemy_deltas: Skulking Colony: Poison(2→11)
  turn_end

### Round 4
Intent: Skulking Colony: Attack(6x2=12)
  Defend
    energy -1 | block +5
  Echoing Slash+
    energy -1 | enemy_deltas: Skulking Colony: hp -13
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 5
Intent: Skulking Colony: Attack(10)
  Deflect
    block +4
  Neutralize+ -> Skulking Colony[0]
    enemy_deltas: Skulking Colony: hp -4, Weak(1→3)
  Poisoned Stab -> Skulking Colony[0]
    energy -1 | block -4 | -Thorns | enemy_deltas: Skulking Colony: DIED
## Combat Analytics: Skulking Colony (WIN - 5 rounds)

Cards played (with descriptions):
  Deflect "Gain 4 Block." -> 3 plays, 12 block
  Defend "Gain 5 Block." -> 4 plays, 20 block
  Echoing Slash+ "Deal 13 damage to ALL enemies. Repeat this effect for each enemy killed." -> 2 plays, 26 dmg
  Precise Cut "Deal 9 damage. Deals 2 less damage for each other card in your Hand." -> 2 plays, 5 dmg
  Expertise "Draw cards until you have 6 in your Hand." -> 2 plays
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg
  Alchemize "Procure a random potion. Exhaust." -> 1 plays, EXHAUST
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 6 dmg, +3 poison
  Strike "Deal 6 damage." -> 1 plays, 5 dmg
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 1 plays, +9 poison
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block

Active powers: Thorns(3)

Poison stacks applied per card:
  Bubble Bubble: 9 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Hardened Shell: R1:15 -> R2:15 -> R3:15 -> R4:15 -> R5:15
  Poison: R1:- -> R2:- -> R3:2 -> R4:10 -> R5:9
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2
  Weak: R1:- -> R2:- -> R3:1 -> R4:2 -> R5:1

[Selected: boss] Lagavulin Matriarch (F17, boss)
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra, Sword of Stone
Deck (19): Defend x5, Strike x5, Snakebite x2, Bullet Time+, Dagger Throw, Deadly Poison, Flick-Flack, Neutralize, Predator, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Agent plan (hypothesis): Do not wake the Matriarch until we are ready to mitigate the incoming 19 damage or burst her down. Retain Snakebite.
Agent plan (hypothesis): Retained Snakebite. Prepare for her awake phase.
Intent: Lagavulin Matriarch: Sleep
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: block -9
  Flick-Flack
  turn_end

### Round 2
Agent plan (hypothesis): Boss has high poison. Play defensive and apply any more poison if possible.
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
Agent plan (hypothesis): See what we draw, prioritize blocking the 18 damage.
Agent plan (hypothesis): If we drew Bullet Time+, play it to dump hand. Otherwise, prioritize Block or Weak.
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
Agent plan (hypothesis): Enemy gets +2 Str and we lose 2 Dex. Next turn's attack will hurt. Save Attack Potion to potentially fish for Weak or Block next turn.
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
Agent plan (hypothesis): The boss will die to poison at the start of the next turn. We just need to survive this hit.
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
Comparator (recent same-enemy comparator):
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Neow's Torment, Potion Belt
Deck (22): Defend x5, Strike x4, Dagger Throw x2, Ricochet x2, Acrobatics+, Dash, Haze, Leg Sweep, Malaise+, Neow's Fury, Neutralize+, Precise Cut, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Intent: Lagavulin Matriarch: Sleep
  Mazaleth's Gift
    +Ritual(1)
  turn_end

### Round 2
Intent: Lagavulin Matriarch: Sleep
  Touch of Insanity -> Lagavulin Matriarch[0]
  Leg Sweep
  turn_end

### Round 3
Intent: Lagavulin Matriarch: Sleep
  turn_end

### Round 4
Intent: Lagavulin Matriarch: Attack(19)
  Malaise+ -> Lagavulin Matriarch[0]
    energy -3 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Lagavulin Matriarch: +Strength(-4), +Weak(4)
  turn_end

### Round 5
Intent: Lagavulin Matriarch: Attack(3x2=6)
  Neutralize+ -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -8, Weak(3→5)
  Ricochet
    energy -2 | enemy_deltas: Lagavulin Matriarch: hp -28
  Strike -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -10
  Precise Cut -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -15
  turn_end

### Round 6
Intent: Lagavulin Matriarch: Attack(6), Defend
  Dash -> Lagavulin Matriarch[0]
    energy -2 | block +10 | enemy_deltas: Lagavulin Matriarch: hp -15
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -14
  Defend
  turn_end

### Round 7
Intent: Lagavulin Matriarch: Debuff, Buff
  Acrobatics+
    energy -1
  Haze
  Leg Sweep -> Lagavulin Matriarch[0]
    block +11 | enemy_deltas: Lagavulin Matriarch: Weak(3→5)
  Neow's Fury -> Lagavulin Matriarch[0]
    energy -1 | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Lagavulin Matriarch: hp -4, block -12
  Neutralize+ -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -10, Weak(5→7)
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -15
  Defend
  turn_end

### Round 8
Intent: Lagavulin Matriarch: Attack(12)
  Neutralize+ -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -9, Weak(6→8)
  Precise Cut -> Lagavulin Matriarch[0]
    enemy_deltas: Lagavulin Matriarch: hp -12
  Acrobatics+
    energy -1
  Strike
  Leg Sweep -> Lagavulin Matriarch[0]
    block +9 | enemy_deltas: Lagavulin Matriarch: Weak(8→10)
  Dash -> Lagavulin Matriarch[0]
    energy -2 | block +8 | enemy_deltas: Lagavulin Matriarch: hp -15
  turn_end

### Round 9
Intent: Lagavulin Matriarch: Attack(5x2=10)
  Survivor
    energy -1 | block +6
  Ricochet
  Strike -> Lagavulin Matriarch[0]
    energy -1 | enemy_deltas: Lagavulin Matriarch: hp -39
  Dagger Throw -> Lagavulin Matriarch[0]
    energy -1 | block -6 | -Ritual | -Strength | -Dexterity | enemy_deltas: Lagavulin Matriarch: DIED
## Combat Analytics: Lagavulin Matriarch (WIN - 9 rounds)

Cards played (with descriptions):
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Neutralize+ "Deal 8 damage. Apply 2 Weak." -> 3 plays, 27 dmg
  Ricochet "Sly. Deal 7 damage to a random enemy 4 times." -> 1 plays, 28 dmg
  Strike "Deal 10 damage." -> 2 plays, 49 dmg
  Precise Cut "Deal 15 damage. Deals 2 less damage for each other card in your Hand." -> 2 plays, 27 dmg
  Dash "Gain 10 Block. Deal 15 damage." -> 2 plays, 30 dmg, 18 block
  Dagger Throw "Deal 14 damage. Draw 1 card. Discard 1 card." -> 3 plays, 29 dmg
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 20 block
  Neow's Fury "Deal 16 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust." -> 1 plays, 4 dmg, EXHAUST
  Survivor "Gain 6 Block. Discard 1 card." -> 1 plays, 6 block

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Plating: R1:12 -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:3 -> R9:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:-4 -> R6:-4 -> R7:-4 -> R8:-2 -> R9:-2
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:4 -> R7:3 -> R8:6 -> R9:9

[Selected: boss] multi:Crusher+Rocket (F33, boss)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Book of Five Rings, Candelabra, Sword of Stone, Yummy Cookie, The Abacus, Juzu Bracelet, Bowler Hat
Deck (27): Defend x5, Strike x4, Snakebite+ x2, Acrobatics+, Afterimage+, Backflip, Blade Dance+, Bouncing Flask, Bullet Time+, Dagger Throw, Deadly Poison, Fan of Knives, Flick-Flack, Footwork+, Neutralize+, Noxious Fumes+, Piercing Wail, Predator, Survivor
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Agent plan (hypothesis): Scaling is in place. Focus on cycling and maintaining block while dealing even damage to both enemies so they die close together.
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
Agent plan (hypothesis): Hold Snakebite+ with retain.
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
Agent plan (hypothesis): Play Bullet Time+ next to make all cards free.
Agent plan (hypothesis): Damage is evening out nicely.
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
Agent plan (hypothesis): Enemies will die to poison at the start of their next turns.
Agent plan (hypothesis): Both enemies should die to poison. Rocket dies on turn 9.
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  Backflip
    energy -1 | block +11
  Neutralize+ -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4, +Weak(2)
  Predator -> Rocket[1]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Rocket: hp -15
  turn_end

### Round 9
Agent plan (hypothesis): Combat won!
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
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Neow's Torment, Potion Belt, Very Hot Cocoa, Pendulum
Deck (26): Defend x5, Strike x3, Dagger Throw x2, Ricochet x2, Abrasive, Acrobatics+, Dash, Deadly Poison, Footwork, Haze+, Leg Sweep+, Malaise+, Neow's Fury, Neutralize+, Precise Cut, Prepared+, Survivor, Well-Laid Plans+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Radiant Tincture
    energy +1 | +Radiance(3)
  Prepared+
  Ricochet
  Haze+
  Acrobatics+
    energy -1
  Abrasive
  Colorless Potion
  Prowess
  Footwork
    energy -1 | Dexterity(1→3)
  Prowess
    Dexterity(3→4) | +Strength(1)
  Neutralize+ -> Crusher[0]
    enemy_deltas: Crusher: hp -5, +Weak(2)
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -10
  Strike
  Dash -> Crusher[0]
    energy -2 | block +14 | enemy_deltas: Crusher: hp -11
  Deadly Poison -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: Poison(6→11)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Precise Cut -> Crusher[0]
    enemy_deltas: Crusher: hp -14
  turn_end

### Round 2
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Dagger Throw -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -10
  Ricochet
  Leg Sweep+ -> Rocket[1]
    energy -2 | block +18 | enemy_deltas: Rocket: +Weak(3)
  Defend
    energy -1 | block +9
  turn_end

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Neow's Fury -> Crusher[0]
    energy -1 | exhausted: Neow's Fury [1]: Deal 10 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Crusher: hp -11
  Precise Cut -> Crusher[0]
    enemy_deltas: Crusher: hp -4
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -10
  Strike
  Survivor
    energy -1 | block +12
  Defend
  turn_end
  Defend
  Defend

### Round 4
Intent: Crusher: Buff, Rocket: Attack(37)
  Deadly Poison -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: Poison(3→8)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Malaise+
  Haze+

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Prepared+
  Haze+
  Precise Cut
  Neutralize+ -> Crusher[0]
    enemy_deltas: Crusher: hp -3, +Weak(2)
  Dash -> Crusher[0]
    energy -2 | block +10 | enemy_deltas: Crusher: hp -8
  Defend
    energy -1 | block +6
  turn_end
  Malaise+
  confirm

### Round 6
Intent: Crusher: Attack(10), Rocket: Attack(7)
  Acrobatics+
    energy -1
  Haze+
  Neutralize+ -> Rocket[1]
    enemy_deltas: Rocket: hp -5, +Weak(2)
  Dagger Throw -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -10
  Ricochet
  Precise Cut -> Rocket[1]
    enemy_deltas: Rocket: hp -2
  Survivor
    energy -1 | block +12
  Strike
  turn_end
  Malaise+
  Leg Sweep+

### Round 7
Intent: Crusher: Attack(9), Rocket: Attack(15)
  Leg Sweep+ -> Rocket[1]
    energy -2 | block +18 | enemy_deltas: Rocket: Weak(1→4)
  Defend
    energy -1 | block +9
  turn_end
  Malaise+
  Ricochet

### Round 8
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  Dash -> Rocket[1]
    energy -2 | block +14 | enemy_deltas: Rocket: hp -11
  Prepared+
  Ricochet
  Haze+
  Deadly Poison -> Rocket[0]
    energy -1 | enemy_deltas: Rocket: Poison(22→27)
  turn_end
  Malaise+
  Ricochet

### Round 9
Intent: Rocket: Attack(30)
  Acrobatics+
    energy -1
  Ricochet
  Dash -> Rocket[0]
    energy -2 | -Surrounded | -Dexterity | -Thorns | -Strength | -Well-Laid Plans | enemy_deltas: Rocket: DIED
## Combat Analytics: multi:Crusher+Rocket (WIN - 9 rounds)

Cards played (with descriptions):
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 3 plays
  Footwork "Gain 2 Dexterity." -> 1 plays
  Prowess "Gain 1 Strength. Gain 1 Dexterity." -> 1 plays
  Neutralize+ "Deal 5 damage. Apply 2 Weak." -> 3 plays, 13 dmg
  Dagger Throw "Deal 10 damage. Draw 1 card. Discard 1 card." -> 4 plays, 40 dmg
  Dash "Gain 14 Block. Deal 11 damage." -> 4 plays, 30 dmg, 38 block
  Deadly Poison "Apply 5 Poison." -> 3 plays, +15 poison
  Defend "Gain 9 Block." -> 8 plays, 60 block
  Precise Cut "Deal 14 damage. Deals 2 less damage for each other card in your Hand." -> 3 plays, 20 dmg
  Leg Sweep+ "Apply 3 Weak. Gain 18 Block." -> 2 plays, 36 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Neow's Fury "Deal 11 damage. Put 2 random cards from your Discard Pile into your Hand. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Survivor "Gain 12 Block. Discard 1 card." -> 2 plays, 24 block

Active powers: Surrounded(1)

Poison stacks applied per card:
  Deadly Poison: 15 stacks

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:26
  Poison[0]: R1:- -> R2:10 -> R3:9 -> R4:8 -> R5:7 -> R6:12 -> R7:17 -> R8:16 -> R9:-
  Poison[1]: R1:- -> R2:5 -> R3:4 -> R4:3 -> R5:7 -> R6:12 -> R7:17 -> R8:16 -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Weak: R1:- -> R2:1 -> R3:2 -> R4:1 -> R5:- -> R6:1 -> R7:1 -> R8:3 -> R9:2

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F44, elite)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 44, elite)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Candelabra, Sword of Stone, Yummy Cookie, The Abacus, Juzu Bracelet, Bowler Hat, Sai, Gorget, Fragrant Mushroom, Potion Belt
Deck (30): Defend x5, Strike x3, Piercing Wail x2, Snakebite+ x2, Acrobatics+, Afterimage+, Backflip, Blade Dance+, Bouncing Flask, Bullet Time+, Calculated Gamble+, Dagger Throw, Deadly Poison+, Fan of Knives, Flick-Flack, Footwork+, Malaise, Neutralize+, Noxious Fumes+, Predator, Survivor, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Agent plan (hypothesis): Kill Spectral Knight quickly to stop Hex from burning our deck.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Bullet Time+
    energy -2 | +No Draw(1)
  Afterimage+
    +Afterimage(1)
  Predator -> Spectral Knight[1]
    block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Spectral Knight: hp -15
  Malaise -> Flail Knight[0]
    energy -1 | block +1 | exhausted: Malaise [X]: Enemy loses X Strength. Apply X Weak. Exhaust. | enemy_deltas: Flail Knight: +Strength(-1), +Weak(1)
  Defend
    block +6
  Survivor
    block +9
  turn_end
    block +4

### Round 2
Agent plan (hypothesis): See what Gamble draws.
Agent plan (hypothesis): Spectral Knight needs to die to stop Hex.
Intent: Flail Knight: Attack(8x2=16), Spectral Knight: Attack(15), Magi Knight: Debuff
  Dagger Throw -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: hp -9
  Flick-Flack
  Fan of Knives
    energy -2 | block +1 | +Fan of Knives(1)
  Shiv
    block +1 | exhausted: Shiv [0]: Ethereal. Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Blade Dance+
    energy -1 | block +1 | exhausted: Shiv*4 [0]: Ethereal. Deal 4 damage to ALL enemies. Exhaust.
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Shiv
    block +1 | enemy_deltas: Flail Knight: hp -4; Spectral Knight: hp -4; Magi Knight: hp -4
  Calculated Gamble+
    block +1 | exhausted: Shiv*8 [0]: Ethereal. Deal 4 damage to ALL enemies. Exhaust.
  Piercing Wail
    energy -1 | block +1 | exhausted: Shiv*8 [0]: Ethereal. Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Flail Knight: Strength(-1→-7), +Piercing Wail(6); Spectral Knight: +Strength(-6), +Piercing Wail(6); Magi Knight: +Strength(-6), +Piercing Wail(6)
  turn_end
    block +3

### Round 3
Agent plan (hypothesis): Spectral Knight needs to die next turn.
Agent plan (hypothesis): Kill Spectral Knight to stop the deck burning.
Intent: Flail Knight: Attack(14), Spectral Knight: Attack(3x3=9), Magi Knight: Attack(10)
  Distilled Chaos
    block +8 | +Well-Laid Plans(1) | enemy_deltas: Magi Knight: +Poison(7)
  Explosive Ampoule
    enemy_deltas: Flail Knight: hp -10; Spectral Knight: hp -10; Magi Knight: hp -10
  Backflip
    energy -1 | block +6
  Noxious Fumes
    energy -1 | block +1 | +Noxious Fumes(2)
  Defend
    energy -1 | block +6
  turn_end
    block +2

### Round 4
Agent plan (hypothesis): Spectral Knight dies next turn, removing Hex. We'll be able to play normally again.
Intent: Flail Knight: Attack(8x2=16), Spectral Knight: Attack(15), Magi Knight: Defend
  Acrobatics
    energy -1
  Flick-Flack
  Neutralize -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -3, +Weak(1)
  Predator -> Spectral Knight[1]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | -Hex | enemy_deltas: Spectral Knight: DIED
  turn_end
    block +1
  Bullet Time

### Round 5
Agent plan (hypothesis): Magi Knight dies to poison next turn, removing Dampen.
Intent: Flail Knight: Attack(8x2=16), Magi Knight: Attack(35)
  Bullet Time
    energy -3 | block +1 | +No Draw(1)
  Backflip
    block +6
  Defend
    block +6
  Defend
    block +6
  Defend
    block +6
  Defend
    block +6
  Defend
    block +6
  Strike -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -6
  turn_end
    -No Draw

### Round 6
Agent plan (hypothesis): Fight is basically won, just let poison tick.
Intent: Flail Knight: Attack(14), Magi Knight: Attack(10)
  Dagger Throw -> Flail Knight[0]
    energy -1 | enemy_deltas: Flail Knight: hp -9
  Flick-Flack
  Snakebite -> Flail Knight[0]
    energy -2 | block +1 | enemy_deltas: Flail Knight: Poison(4→11)
  turn_end
  Acrobatics

### Round 7
Intent: Flail Knight: Attack(14)
  Neutralize+ -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -4, +Weak(2)
  Strike -> Flail Knight[0]
    energy -1 | hp +1 | block -8 | -Afterimage | -Fan of Knives | -Well-Laid Plans | -Noxious Fumes | enemy_deltas: Flail Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 7 rounds)

Cards played (with descriptions):
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 15 dmg, 2 block
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, 1 block, EXHAUST
  Defend "Gain 5 Block." -> 7 plays, 42 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 9 block
  Dagger Throw "Ethereal. Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 18 dmg
  Fan of Knives "Ethereal. Shivs now hit ALL enemies. Add 4 Shivs into your Hand." -> 1 plays, 1 block, generates 4 Shivs
  Shiv "Ethereal. Deal 4 damage to ALL enemies. Exhaust." -> 8 plays, 96 dmg, 8 block, EXHAUST
  Blade Dance+ "Ethereal. Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 block, EXHAUST, generates 4 Shivs
  Calculated Gamble+ "Retain. Ethereal. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 1 block, EXHAUST
  Piercing Wail "Ethereal. ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST
  Backflip "Ethereal. Gain 5 Block. Draw 2 cards." -> 2 plays, 12 block
  Noxious Fumes "Ethereal. At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays, 1 block
  Acrobatics "Ethereal. Draw 3 cards. Discard 1 card." -> 1 plays
  Neutralize "Ethereal. Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg, 1 block
  Bullet Time "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 2 plays, 6 dmg, 1 block
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, 1 block, +7 poison
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg, 1 block

Active powers: Plating(4)

Token attribution (Shivs):
  Fan of Knives: 4 Shivs -> ~48 dmg
  Blade Dance+: 4 Shivs -> ~48 dmg

Poison stacks applied per card:
  Distilled Chaos: 7 stacks
  Snakebite: 7 stacks
Total poison/power tick damage: 15
  Per round: R4:15

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:12
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:3 -> R6:4 -> R7:-
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:9 -> R6:10 -> R7:-
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:8 -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:-1 -> R3:-1 -> R4:-1 -> R5:-1 -> R6:-1 -> R7:-1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 43, elite)
Relics: Ring of the Snake, New Leaf, Lantern, Bronze Scales, Bellows, Pael's Tears, Pen Nib, The Chosen Cheese, Beautiful Bracelet, Gremlin Horn, Bag of Preparation
Deck (23): Defend x4, Abrasive, Accelerant+, Acrobatics+, Alchemize+, Backflip, Blade Dance, Bubble Bubble, Deadly Poison+, Deflect, Echoing Slash+, Expertise+, Leg Sweep+, Neutralize+, Outbreak, Poisoned Stab, Predator, Prepared+, Survivor, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Deflect+
    block +7
  Echoing Slash+
    energy -1 | enemy_deltas: Flail Knight: hp -13; Spectral Knight: hp -13; Magi Knight: hp -13
  Survivor+
    energy -1 | block +11
  Defend+
  Alchemize+
    exhausted: Alchemize+ [0]: Procure a random potion. Exhaust.
  Outbreak
    energy -1 | +Outbreak(11)
  Backflip+
    energy -1 | block +8
  turn_end

### Round 2
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Debuff
  Neutralize+ -> Spectral Knight[1]
    enemy_deltas: Spectral Knight: hp -4, +Weak(2)
  Prepared+
  Abrasive
  Accelerant+
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Leg Sweep+ -> Flail Knight[0]
    energy -2 | block +15 | enemy_deltas: Flail Knight: +Weak(3)
  turn_end
    exhausted: Poisoned Stab [1]: Ethereal. Deal 6 damage. Apply 3 Poison.

### Round 3
Intent: Flail Knight: Attack(9x2=18), Spectral Knight: Attack(11), Magi Knight: Attack(10)
  Shackling Potion
    enemy_deltas: Flail Knight: Strength(3→-4), +Shackling Potion(7); Spectral Knight: +Strength(-7), +Shackling Potion(7); Magi Knight: +Strength(-7), +Shackling Potion(7)
  Backflip
    energy -1 | block +6
  Survivor
    energy -1 | block +9
  Defend
  Deadly Poison -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: +Poison(5)
  turn_end
    exhausted: Poisoned Stab [1]: Ethereal. Deal 6 damage. Apply 3 Poison.

### Round 4
Intent: Flail Knight: Buff, Spectral Knight: Attack(3x3=9), Magi Knight: Defend
  Predator -> Spectral Knight[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Spectral Knight: hp -15
  Echoing Slash
    energy -1 | enemy_deltas: Flail Knight: hp -10; Spectral Knight: hp -10; Magi Knight: hp -10
  Neutralize -> Spectral Knight[1]
    enemy_deltas: Spectral Knight: hp -3, +Weak(1)
  Deflect
    block +5
  turn_end

### Round 5
Intent: Flail Knight: Attack(21), Spectral Knight: Attack(15), Magi Knight: Attack(35)
  Blessing of the Forge
  Speed Potion
    Dexterity(1→6) | +Speed Potion(5)
  Neutralize+ -> Spectral Knight[1]
    energy +1 | -Hex | enemy_deltas: Spectral Knight: DIED
  Deflect+
    block +13
  Leg Sweep+ -> Flail Knight[0]
    energy -2 | block +20 | enemy_deltas: Flail Knight: +Weak(3)
  Survivor+
    energy -1 | block +17
  Prepared
  turn_end
  Deadly Poison+
  Accelerant+

### Round 6
Intent: Flail Knight: Attack(11x2=22), Magi Knight: Attack(10)
  Neutralize+ -> Magi Knight[1]
    enemy_deltas: Magi Knight: hp -4, +Weak(2)
  Deflect+
    block +8
  Accelerant+
    energy -1 | +Accelerant(2)
  Echoing Slash
    energy -1 | enemy_deltas: Flail Knight: hp -10; Magi Knight: hp -10
  Backflip+
    energy -1 | block +9
  Survivor+
    energy -1 | block +12
  Predator
  Echoing Slash
    energy -1 | enemy_deltas: Flail Knight: hp -10; Magi Knight: hp -10
  turn_end
  Deadly Poison+
  Leg Sweep+

### Round 7
Intent: Flail Knight: Buff, Magi Knight: Defend
  Predator -> Flail Knight[0]
    energy -1 | +Draw Cards Next Turn(2) | enemy_deltas: Flail Knight: DIED
  Neutralize+ -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -4, Weak(1→3)
  Deadly Poison+ -> Magi Knight[0]
    energy -1 | enemy_deltas: Magi Knight: +Poison(7)
  turn_end
  Leg Sweep+
  Survivor+
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 7 rounds)

Cards played (with descriptions):
  Deflect+ "Gain 7 Block." -> 3 plays, 28 block
  Echoing Slash+ "Deal 13 damage to ALL enemies. Repeat this effect for each enemy killed." -> 1 plays, 39 dmg
  Survivor+ "Gain 11 Block. Discard 1 card." -> 3 plays, 40 block
  Alchemize+ "Procure a random potion. Draw 3 cards the first time this is played. Exhaust." -> 1 plays, EXHAUST
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 2 plays, 17 block
  Neutralize+ "Ethereal. Deal 4 damage. Apply 2 Weak. Draw 3 cards the first time this is played." -> 4 plays, 12 dmg
  Prepared+ "Ethereal. Draw 2 cards. Discard 2 cards." -> 1 plays
  Well-Laid Plans+ "Ethereal. At the end of your turn, Retain up to 2 cards." -> 1 plays
  Leg Sweep+ "Ethereal. Apply 3 Weak. Gain 15 Block." -> 2 plays, 35 block
  Backflip "Ethereal. Gain 6 Block. Draw 2 cards." -> 1 plays, 6 block
  Survivor "Ethereal. Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Deadly Poison "Ethereal. Apply 5 Poison." -> 1 plays, +5 poison
  Predator "Ethereal. Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 15 dmg
  Echoing Slash "Ethereal. Deal 10 damage to ALL enemies. Repeat this effect for each enemy killed." -> 3 plays, 70 dmg
  Neutralize "Ethereal. Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Deflect "Ethereal. Gain 5 Block." -> 1 plays, 5 block
  Accelerant+ "Poison is triggered 2 additional times. Draw 3 cards the first time this is played." -> 1 plays
  Deadly Poison+ "Apply 7 Poison." -> 1 plays, +7 poison

Active powers: Thorns(3)

Poison stacks applied per card:
  Deadly Poison+: 7 stacks
  Deadly Poison: 5 stacks
Total poison/power tick damage: 24
  Per round: R5:4 R7:20

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:4 -> R5:3 -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:6 -> R6:6 -> R7:6
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:2 -> R7:-
  Weak[0]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:1
  Weak[1]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
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
Agent plan (hypothesis): 2 energy remaining after this. Prioritize key drawn cards like Footwork+, Bouncing Flask, or Predator.
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
Agent plan (hypothesis): Saved Piercing Wail for another multi-attack. Keep stacking poison on Queen.
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
Agent plan (hypothesis): Torch Head is effectively crippled this turn. Next turn, focus on getting powers down or setting up Bouncing Flask.
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
Agent plan (hypothesis): Queen is taking massive poison damage. Maintain block next turn and she will die to poison.
Agent plan (hypothesis): Queen is taking massive poison damage and will die very soon.
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
- The Silent - Deckbuilding Principles: F2(), F3(), F3(), F4(), F5(), F5(), F6(), F11(), F12(), F14(), F17(), F17(), F17(), F18(), F19(), F20(), F20(), F21(), F22(), F23(), F25(), F28(), F31(), F33(), F35(), F38(), F38(), F39(), F43(), F44(), F46(), F46(), F46()
- The Silent - Path Selection: F1(), F1(), F2(), F3(), F4(), F5(), F5(), F6(), F6(), F7(), F7(), F8(), F9(), F10(), F10(), F11(), F11(), F12(), F12(), F13(), F13(), F14(), F14(), F15(), F18(), F18(), F19(), F20(), F21(), F22(), F23(), F24(), F25(), F26(), F27(), F28(), F29(), F30(), F31(), F34(), F34(), F35(), F35(), F36(), F37(), F38(), F39(), F40(), F41(), F42(), F43(), F44(), F45(), F46()
- The Silent - Rest & Event Decisions: F7(), F9(), F13(), F16(), F27(), F29(), F32(), F42(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.