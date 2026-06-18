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
Result: VICTORY (fitness: 239.6)
Combats won: 24/24
Run duration: 6685.1s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: Looking for frontloaded damage and AoE to survive early Act 1 Elites, leveraging Winged Boots for optimal pathing.
- [map] Foundation phase: Prioritize frontloaded damage and AoE in early card rewards to survive Act 1 elites; use Winged Boots later to snipe optimal nodes or bypass forced damage.
### F2
- [card_reward] Foundation plan: currently holding a strong poison payoff (Bubble Bubble), so prioritize finding a cheap poison applicator (Deadly Poison, Poisoned Stab). Need frontload damage for Act 1 elites and avoid taking conflicting archetypes.
- [map] Foundation phase: searching for high-impact frontloaded damage and AoE to safely tackle upcoming Act 1 elites while leveraging Winged Boots for pathing flexibility.
### F3
- [card_reward] Foundation plan: survive with frontload damage and AoE while looking for a primary poison enabler (like Deadly Poison) to turn on Bubble Bubble. Keep the deck lean and prioritize early damage before committing to scaling defense or cycle.
- [map] Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE for Act 1 elites while using Winged Boots as a safety net for later pathing adjustments.
### F4
- [card_reward] Committed poison plan: use Deadly Poison to set up Bubble Bubble for massive poison damage, then defend. Needs more draw/discard to align the combo and strong mitigation. Avoid generic attacks.
- [map] Foundation phase: searching for frontloaded damage and AoE to handle Act 1 Elites; prioritize card rewards that solve Gremlin Nob and Sentries while using rest sites for upgrades.
### F5
- [map] Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE before the first Elite, utilizing the healthy HP buffer to avoid early shops or excessive unknowns.
### F6
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling and more cycle; skip off-plan attacks and expensive cards.
- [map] Foundation phase: prioritize high-impact upgrades at rest sites to secure the mid-act Elite; currently seeking front-loaded damage and AoE to stabilize the deck.
### F7
- [rest_site] Foundation phase transitioning to poison control: use Predator and Dagger Spray to clear Act 1 hallway/elite threats while setting up Noxious Fumes and Bubble Bubble for boss scaling. Needs more block and card removal to survive later turns.
- [map] Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE for upcoming Elites. Currently seeking core damage cards to complement the basic Silent kit before using gold at the Floor 12 shop.
### F8
- [card_reward] Committed poison plan: apply poison with Noxious Fumes, Deadly Poison, and Bubble Bubble, then stall with advanced defense like Piercing Wail. Needs more draw and block scaling; avoid adding generic attacks.
- [map] Foundation phase: Urgently seeking a rest to stabilize low HP before the next elite; looking for poison or shiv scaling to transition from basic survival to a cohesive game plan.
### F9
- [rest_site] Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs more block and draw; skip raw attacks.
- [map] Foundation phase: Urgently need to stabilize HP and find frontloaded damage or AoE. The deck is currently vulnerable; prioritizing survival through the next Rest Site to prepare for the mid-act Elite.
### F10
- [map] Foundation phase: searching for frontloaded damage and AoE to stabilize; prioritizing survivability via rest sites before Elites while Winged Boots allow for flexible pathing.
### F11
- [rest_site] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more block and draw; skip raw attacks.
- [map] Foundation phase: Seeking frontloaded damage and AoE to safely navigate Act 1 Elites. Using HP as a resource enabled by Pantograph, prioritizing relics over safety until a coherent engine (Shiv or Poison) is established. Avoid hoarding gold and aim for a final shop before the boss.
### F12
- [hand_select] Prioritizing removing self-damage status cards over playable cards, especially since I need energy for Dagger Spray to clear the low-HP Wrigglers.
- [card_reward] Committed poison plan: stack poison with Fumes and Bubble Bubble, prioritize discard outlets to enable Sly cards like Haze, and focus on surviving while passive damage scales. Avoid narrow attacks; need more cycle, discard, and robust block.
- [map] Foundation phase: searching for high-impact frontloaded damage and AoE to secure a clean Slime Boss split. Prioritizing hallway fights to build deck density before the final rest site; Pantograph allows for more aggressive pathing by providing a heal before the boss.
### F13
- [card_reward] Committed poison plan: stack poison with Fumes/Bubble on safe burst turns, then defend with Wail/Survivor while passive poison kills. Needs dex/block scaling and Strike removals; skip off-plan attacks.
- [map] Foundation phase: pursuing frontloaded damage and AOE to handle Act 1 hallways and the boss; Pantograph allows for more aggressive floor choices by providing a heal before the boss, so prioritizing card rewards over defensive events.
### F14
- [card_reward] Committed poison plan: rely on Noxious Fumes+ and Bubble Bubble to scale damage while surviving with Piercing Wail and basic block. Priority now is removing basic Strikes/Defends and finding more card draw to accelerate setup.
- [map] Foundation phase: searching for frontloaded damage and AoE to stabilize; prioritizing safe hallway fights over risky elites at low HP while relying on Pantograph for boss sustain.
### F15
- [card_reward] Committed poison plan: apply poison with Fumes+, Bubble Bubble, and Deadly Poison, then focus purely on survival. Cycle aggressively to find Piercing Wails for big multi-attacks. Needs block scaling like Footwork and more removals; skip generic attacks and narrow synergies.
- [map] Foundation phase: Seeking defensive scaling and energy relics. Currently pivoting to survival mode for the Act 1 boss; rely on Pantograph for a safe HP buffer and use this rest site to heal or upgrade a key defensive card if HP feels sufficient.
### F16
- [rest_site] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.
### F17
- [card_reward] Committed poison plan: rely on Noxious Fumes+, Bubble Bubble, and Haze to kill, using Piercing Wail and block to survive. Need upgraded defense and energy/draw; remove Strikes. Play Assassinate + Predator turn 1 for immediate threat removal.
### F18
- [event] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more block and card removals; avoid basic attacks.
- [map] Foundation phase: The deck is currently seeking defensive scaling and reliable energy. I will use early Act 2 hallway fights to identify gaps in damage or mitigation before using my 303 gold at an upcoming shop to pivot into a committed build.
### F19
- [card_reward] Committed poison plan: apply poison with Fumes/Deadly Poison/Haze, scale with Bubble Bubble, and use Piercing Wails/Survivor to survive. Need scaling defense (Footwork/Leg Sweep) and more cycle/energy. Skip off-plan attacks.
- [map] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and consistent block; prioritize removing basic strikes at shops.
### F20
- [event] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and consistent block; prioritize removing basic strikes at shops.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while defending with Weakness; currently targeting shops to convert high gold into card draw, block, and poison scaling while removing basic Strikes.
### F21
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more efficient cycle; avoid adding attacks.
- [map] Committed poison plan: use Noxious Fumes and Bubble Bubble to scale damage while prioritizing block and Weakness. Current priority is finding card draw and premium block like Leg Sweep or Blur; avoid elites until mitigation is stronger.
### F22
- [card_select] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.
- [card_reward] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and scaling block; prioritize removing basic strikes.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while prioritizing Weak and Piercing Wails for survival. Needs more card draw and consistent block; seek removals for basic strikes at shops and card rewards that enhance defensive rotation.
### F23
- [card_reward] Committed poison plan: survive with Piercing Wail and Fasten while stacking poison via Fumes, Flask, and Bubble Bubble. Use Acrobatics to dig for key pieces and discard Haze for free triggers. Avoid adding raw attacks.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Current priorities are card draw to find scaling faster and additional block; Winged Boots are reserved to bypass the floor 31 Elite if HP is low.
### F24
- [event] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [map] Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.
### F25
- [rest_site] Committed poison plan: rely on Noxious Fumes, Bouncing Flask, and Bubble Bubble to stack poison, then defend with Fasten-boosted Defends and Piercing Wails. Needs more card draw to consistently set up the engine and remove basic strikes.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F26
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F27
- [card_reward] Committed poison plan: survive with scaling block (Footwork, Fasten) and Piercing Wails while passive poison kills. Retain draw to find defensive answers and setup pieces faster.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F28
- [hand_select] Executing the 'Sly' mechanic to maximize value from Acrobatics and progress the poison strategy.
- [card_reward] Committed poison plan: stack passive poison with Fumes and Flask, scale block with Footwork and Fasten, and aggressively cycle the deck with Acrobatics and Backflip. Keep the deck lean by removing basic attacks, and rely on poison for damage.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F29
- [rest_site] Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Look for more reliable draw to setup powers faster and remove basic strikes.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F30
- [card_reward] Committed poison plan: setup Noxious Fumes and apply poison while using Dexterity and Weak to survive. Draw heavily to bypass boss statuses and find Frantic Escapes. Skip off-plan cards to keep the deck consistent.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F31
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F32
- [rest_site] Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Look for more reliable draw to setup powers faster and remove basic strikes.
### F33
- [hand_select] Prioritizing survival and death timer management over chip damage.
- [card_reward] Committed poison plan: apply poison rapidly with Bouncing Flask, Deadly Poison, and Corrosive Wave combined with heavy draw cycle, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails.
### F34
- [event] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Use the infinite potion generation from Delicate Frond to solve immediate energy or scaling needs every combat.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.
### F35
- [card_select] Committed poison plan: apply poison rapidly with Bouncing Flask and Deadly Poison, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails. Prioritize draw to cycle past status floods and skip generic attacks.
- [card_reward] Committed poison plan: apply poison rapidly with Bouncing Flask and Deadly Poison, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails. Prioritize draw to cycle past status floods and trigger Corrosive Wave.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; seek more draw to accelerate setup and prioritize removals of basic strikes.
### F36
- [event] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; sell Foul Potions at the upcoming shop for massive gold, then prioritize strike removals and premium relics. Delicate Frond provides infinite potions to solve immediate problems.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Prioritize high-value card draw and removals at the next shop to accelerate power setup.
### F37
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritize finding more draw and removing basic strikes to accelerate power setup.
### F38
- [hand_select] Maximize survival and poison application. Corrosive Wave is already active, so the second copy is current dead weight compared to 10 block Defends.
- [card_reward] Committed poison plan: survive with Piercing Wails and immense Dexterity from Footwork while passive Poison (Noxious Fumes, Bubble Bubble) scales. Keep cycling to find setup pieces early and stall.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritising shops to remove Strikes and find more draw/burst potential.
### F39
- [card_reward] Committed poison plan: survive with massive block from Footwork+ and Piercing Wails while Noxious Fumes and Bubble Bubble kill the boss. Cycle aggressively to find powers early. Skip raw attacks.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks.
- [card_reward] Committed poison plan: survive with high block/dexterity while Noxious Fumes and Bubble Bubble scale to kill. Prioritize card removal (Strikes) and avoid adding more attacks.
- [card_reward] Committed poison plan: stack poison with Fumes, Flask, and Corrosive Wave while blocking heavily with Footwork, Backflip, and Piercing Wail. Prioritize draw and cycle to find key setup pieces quickly, and avoid adding unrelated attacks or bloat.
- [card_select] Committed poison plan: setup Noxious Fumes, Footwork, and Fasten, then cycle with Acrobatics and Backflip to apply more poison and block. Keep removing Strikes.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Needs more draw to setup powers faster and removals for basic strikes; take Elites now to find high-impact relics or rare cards.
### F40
- [card_select] Committed poison plan: rely on Noxious Fumes, Footwork, and defensive skills to outlast enemies while passive poison scales. Focus on draw, block, and poison application; avoid unrelated attacks or narrow synergies.
- [hand_select] Retaining key poison applicators to ensure consistent damage scaling.
- [card_reward] Committed poison plan: rely on AoE poison (Fumes, Haze, Corrosive Wave) and Bubble Bubble to bypass the Queen's 20 block per turn. Prioritize surviving with Footwork and cheap block while passive poison scales. Avoid adding expensive or single-target cards since energy is limited to 3.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritize survival and finding a source of Burst or more Catalyst to accelerate scaling.
### F41
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Current priority is survival via Rest Sites; once stabilized, seek draw to set up powers faster and more removals for basic Strikes.
### F42
- [rest_site] Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Draw through the deck using Acrobatics and Calculated Gamble to accelerate poison and Automation energy.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending. Use the Delicate Frond's infinite potion generation to mitigate damage and overcome Elites. Prioritize block and poison scaling over raw attacks, using the Pantograph heal to offset health loss from aggressive routing.
### F43
- [hand_select] Executing the Sly trigger on Haze maximizes poison output for 0 energy cost.
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [map] Committed poison plan: use Noxious Fumes and Bouncing Flask for scaling while prioritizing defense and Delicate Frond potion generation. Removing remaining Strikes and finding more efficient block or card draw are the current priorities to ensure consistency against high-damage Act 3 enemies.
### F44
- [rest_site] Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Draw through the deck using Acrobatics and Calculated Gamble to accelerate poison and Automation energy.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending. Delicate Frond provides infinite potions to solve immediate problems; prioritize strike removals and premium relics in future shops.
### F45
- [hand_select] Retaining these allows for a more explosive or defensive turn next round, fitting the poison/defensive strategy.
- [hand_select] Well-Laid Plans allows us to carry over our best setup/draw cards to ensure we can react to incoming damage or finish the constructs with poison.
- [card_reward] Committed poison plan: survive with high block/dexterity while cycling rapidly to stack poison. Use Corrosive Wave combined with Calculated Gamble+ and Acrobatics for massive AoE poison application. Bubble Bubble acts as a strong multiplier. Avoid adding attacks; prioritize cheap block, energy generation, and cycle to keep the engine moving.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; use Delicate Frond for tactical potion generation and prioritize defensive upgrades to let poison tick. Scaling is solid, seeking premium relics from elites to secure the final boss kill.
### F46
- [hand_select] Retaining Piercing Wail ensures survival next turn regardless of draw. Haze synergy with Acrobatics+ provides free scaling.
- [hand_select] Continuing to cycle the deck for setup and defensive scaling while handling statuses.
- [card_reward] Committed poison plan: apply poison with Fumes and Flask, stack it rapidly with Bubble Bubble and Snecko Skull. Survive with Footwork, extensive cycle, and Piercing Wail to negate multi-hit threats. Hold Wails for dangerous multi-hit turns.
- [map] Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; use Delicate Frond's infinite potions to bridge defensive gaps and accelerate kills. Priority is removing strikes and upgrading core poison/block pieces before the boss.
### F47
- [rest_site] Committed poison/draw plan: stack poison with Noxious Fumes, Bubble Bubble, and Corrosive Wave while drawing heavily. Use Calculated Gamble and Acrobatics to trigger Corrosive Wave and Automation. Play defensively with Fasten and Piercing Wail while poison scales.

### Combat Decision Digest (24 combats)
F2 [monster] Shrinker Beetle (4R, HP 56->56, loss=0, WIN)
  R1[Shrinker Beetle: DebuffStrong]: Strike(6dmg)->Strike(6dmg)->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=21 taken=0
  R2[Shrinker Beetle: Atk(7)]: Strike(4dmg)->Strike(4dmg)->Survivor(+8blk) | dealt=8 taken=0
  R3[Shrinker Beetle: Atk(13)]: Neutralize(2dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(4dmg) | dealt=6 taken=0
  R4[Shrinker Beetle: Atk(7)]: Strike(4dmg)->Strike(power:-Shrink) | dealt=4 taken=0

F3 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (S) (6R, HP 56->55, loss=1, WIN)
  R1[Twig Slime (S): Atk(4)+Leaf Slime (M): StatusCard(2)+Leaf Slime (S): StatusCard(1)]: Neutralize(3dmg,1+Weak(1))->Strike->Strike(6dmg)->Strike(6dmg) | dealt=20 taken=0
  R2[Leaf Slime (M): Atk(8)+Leaf Slime (S): Atk(3)]: Strike->Defend(+5blk)->Defend(+5blk) | dealt=3 taken=0
  R3[Leaf Slime (M): StatusCard(2)]: Strike(6dmg)->Slimed(exhaust:1) | dealt=6 taken=0
  R4[Leaf Slime (M): Atk(8)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=15 taken=1
  R5[Leaf Slime (M): StatusCard(2)]: Strike(6dmg)->Strike(6dmg)->Slimed | dealt=12 taken=0
  R6[Leaf Slime (M): Atk(8)]: Strike | dealt=0 taken=0

F4 [monster] Nibbit (4R, HP 55->55, loss=0, WIN)
  R1[Nibbit: Atk(12)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Survivor(+8blk)->Strike(6dmg) | dealt=9 taken=0
  R2[Nibbit: Atk(6), Defend]: Dagger Spray(8dmg)->Defend(+5blk)->Defend(+5blk) | dealt=8 taken=0
  R3[Nibbit: Buff]: Dagger Spray(3dmg)->Strike(6dmg) | dealt=9 taken=0
  R4[Nibbit: Atk(14)]: Strike(6dmg)->Strike(6dmg)->Strike | dealt=12 taken=0

F6 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (M)+Twig Slime (S) (5R, HP 55->49, loss=6, WIN)
  R1[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Twig Slime (S): Atk(4)+Leaf Slime (S): Atk(3)]: Predator(power:+Draw Cards Next Turn(2))->Neutralize(3dmg,1+Weak(1))->Defend(+5blk) | dealt=14 taken=0
  R2[Twig Slime (M): Atk(11)+Leaf Slime (M): Atk(8)+Leaf Slime (S): StatusCard(1)]: Dagger Spray(24dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=24 taken=6
  R3[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Leaf Slime (S): Atk(3)]: Strike->Deadly Poison(1+Poison(5))->Strike(6dmg) | dealt=9 taken=0
  R4[Twig Slime (M): Atk(11)+Leaf Slime (M): Atk(8)]: Predator(power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=13 taken=0
  R5[Leaf Slime (M): StatusCard(2)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Dagger Spray | dealt=9 taken=0

F8 [monster] multi:Fuzzy Wurm Crawler+Shrinker Beetle (8R, HP 49->24, loss=25, WIN)
  R1[Shrinker Beetle: DebuffStrong+Fuzzy Wurm Crawler: Atk(4)]: Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R2[Shrinker Beetle: Atk(7)+Fuzzy Wurm Crawler: Buff]: Neutralize(2dmg,1+Weak(1))->Defend(+5blk)->Predator+(14dmg,power:+Draw Cards Next Turn(2)) | dealt=16 taken=0
  R3[Shrinker Beetle: Atk(13)+Fuzzy Wurm Crawler: Atk(11)]: Survivor(+8blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=6
  R4[Shrinker Beetle: Atk(7)+Fuzzy Wurm Crawler: Atk(11)]: Predator+(power:+Draw Cards Next Turn(2),power:-Shrink)->Defend(+5blk) | dealt=10 taken=6
  R5[Fuzzy Wurm Crawler: Buff]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=29 taken=0
  R6[Fuzzy Wurm Crawler: Atk(18)]: Survivor(+8blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R7[Fuzzy Wurm Crawler: Atk(18)]: Defend(+5blk)->Dagger Spray(8dmg)->Strike(6dmg) | dealt=14 taken=13
  R8[Fuzzy Wurm Crawler: Buff]: Acrobatics->Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike | dealt=9 taken=0

F12 [elite] Phrog Parasite (6R, HP 45->42, loss=3, WIN)
  R1[Phrog Parasite: StatusCard(3)]: Deadly Poison(1+Poison(5))->Strike(6dmg)->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=15 taken=0
  R2[Phrog Parasite: Atk(4x4=16)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Noxious Fumes+(power:+Noxious Fumes(3))->Bubble Bubble(1Poison(4→13)) | dealt=0 taken=0
  R3[Phrog Parasite: StatusCard(3)]: Acrobatics->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R4[Phrog Parasite: Atk(4x4=16)]: none | dealt=0 taken=3
  R5[Wriggler: Stun+Wriggler: Stun+Wriggler: Stun+Wriggler: Stun]: Predator+(power:+Draw Cards Next Turn(2))->Dagger Spray(8dmg) | dealt=8 taken=0
  R6[Wriggler: Atk(6)+Wriggler: Atk(6)+Wriggler: Buff, StatusCard(1)]: Acrobatics->Dagger Spray(power:-Noxious Fumes) | dealt=0 taken=0

F13 [monster] multi:Slithering Strangler+Snapping Jaxfruit (5R, HP 42->32, loss=10, WIN)
  R1[Snapping Jaxfruit: Atk(3), Buff+Slithering Strangler: Debuff]: Neutralize+(4dmg,1+Weak(2))->Dagger Spray(16dmg)->Strike(6dmg)->Defend(+5blk) | dealt=26 taken=0
  R2[Snapping Jaxfruit: Atk(3), Buff+Slithering Strangler: Atk(12)]: Predator+(power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=13 taken=7
  R3[Slithering Strangler: Debuff]: Noxious Fumes+(power:+Noxious Fumes(3))->Deadly Poison(1+Poison(5))->Bubble Bubble+(1Poison(5→17)) | dealt=0 taken=3
  R4[Slithering Strangler: Atk(12)]: Defend(+5blk)->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R5[Slithering Strangler: Debuff]: Dagger Spray(8dmg)->Strike(power:-Constrict,power:-Noxious Fumes) | dealt=8 taken=0

F14 [monster] multi:Flyconid+Leaf Slime (M) (4R, HP 32->29, loss=3, WIN)
  R1[Leaf Slime (M): StatusCard(2)+Flyconid: Atk(8), Debuff]: Acrobatics->Haze(+5blk)->Defend(16dmg)->Dagger Spray | dealt=16 taken=3
  R2[Leaf Slime (M): Atk(8)+Flyconid: Debuff]: Noxious Fumes+(power:+Noxious Fumes(3))->Defend(+3blk)->Survivor(+6blk) | dealt=0 taken=0
  R3[Leaf Slime (M): StatusCard(2)+Flyconid: Atk(16)]: Neutralize(3dmg,1+Weak(1))->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Bubble Bubble(1Poison(5→14)) | dealt=23 taken=0
  R4[Leaf Slime (M): Atk(12)]: Predator+(power:-Noxious Fumes,power:-Vulnerable) | dealt=0 taken=0

F15 [monster] Vine Shambler (4R, HP 29->22, loss=7, WIN)
  R1[Vine Shambler: Atk(6x2=12)]: Predator+(20dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=20 taken=7
  R2[Vine Shambler: Atk(8), CardDebuff]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Deadly Poison(1+Poison(5)) | dealt=3 taken=0
  R3[Vine Shambler: Atk(16)]: Acrobatics->Haze+(2+Strength(-8),+Piercing Wail(8),exhaust:1)->Piercing Wail+(+8blk)->Survivor | dealt=0 taken=0
  R4[Vine Shambler: Atk(6x2=12)]: Neutralize(3dmg,1+Weak(1))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Strike(6dmg)->Strike(6dmg) | dealt=15 taken=0

F17 [boss] multi:Kin Follower+Kin Follower+Kin Priest (8R, HP 47->3, loss=44, WIN)
  R1[Kin Follower: Buff+Kin Follower: Atk(5)+Kin Priest: Atk(8), Debuff]: Survivor(+10blk)->Expertise->Defend(+7blk) | dealt=0 taken=0
  R2[Kin Follower: Atk(7)+Kin Follower: Atk(2x2=4)+Kin Priest: Atk(8), Debuff]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Neutralize+(4dmg,1+Weak(2))->Defend(+5blk)->Strike(6dmg) | dealt=10 taken=0
  R3[Kin Follower: Atk(4x2=8)+Kin Follower: Buff+Kin Priest: Atk(2x3=6)]: Noxious Fumes+(power:+Noxious Fumes(3))->Predator+(15dmg,power:+Draw Cards Next Turn(2)) | dealt=35 taken=14
  R4[Kin Follower: Buff+Kin Follower: Atk(7)+Kin Priest: Buff]: Neutralize+(4dmg,1+Weak(2))->Acrobatics->Deadly Poison(1Poison(3→8))->Defend(+7blk) | dealt=4 taken=0
  R5[Kin Follower: Atk(9)+Kin Follower: Atk(4x2=8)+Kin Priest: Atk(7), Debuff]: Haze(1Poison(5→9),1Poison(10→14))->Expertise->Bubble Bubble+(1Poison(14→26))->Defend(+7blk) | dealt=0 taken=17
  R6[Kin Follower: Atk(6x2=12)+Kin Follower: Buff+Kin Priest: Atk(10), Debuff]: Neutralize+->Defend(+5blk)->Deadly Poison(1Poison(28→33))->Strike(6dmg) | dealt=6 taken=13
  R7[Kin Follower: Buff+Kin Follower: Atk(9)+Kin Priest: Atk(5x3=15)]: Piercing Wail(2Strength(4→-2),+Piercing Wail(6),2Strength(2→-4),+Piercing Wail(6))->Defend(+7blk)->Survivor(+10blk) | dealt=0 taken=0
  R8[Kin Follower: Atk(11)+Kin Follower: Atk(6x2=12)+Kin Priest: Buff]: Expertise->Acrobatics->Haze(16dmg)->Dagger Spray | dealt=16 taken=0

F19 [monster] Thieving Hopper (3R, HP 56->53, loss=3, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Deadly Poison+(1+Poison(7))->Survivor(+8blk)->Haze(3Poison(7→11),+Strength(-6),+Piercing Wail(6),exhaust:1)->Piercing Wail | dealt=10 taken=3
  R2[Thieving Hopper: Buff]: Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Bubble Bubble+(1Poison(10→22))->Defend(+5blk) | dealt=10 taken=0
  R3[Thieving Hopper: Atk(15)]: Predator+(10dmg,power:+Draw Cards Next Turn(2),1Flutter(5→4))->Defend(+5blk) | dealt=10 taken=0

F22 [monster] Tunneler (6R, HP 53->51, loss=2, WIN)
  R1[Tunneler: Atk(13)]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Fasten(power:+Fasten(5))->Defend(+10blk)->Defend(+10blk) | dealt=10 taken=0
  R2[Tunneler: Buff, Defend]: Noxious Fumes+(power:+Noxious Fumes(3))->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=0
  R3[Tunneler: Atk(23)]: Neutralize+(1+Weak(2))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Acrobatics->Haze(+10blk)->Defend | dealt=0 taken=2
  R4[Tunneler: Atk(17)]: Deadly Poison(1Poison(9→14))->Defend(+10blk)->Survivor(+8blk) | dealt=0 taken=0
  R5[Tunneler: Atk(23)]: Neutralize+(1+Weak(2))->Defend(+10blk)->Defend(+10blk)->Defend+(+13blk) | dealt=0 taken=0
  R6[Tunneler: Atk(17)]: Pounce(power:+Free Skill(1))->Defend(+10blk,power:-Free Skill)->Dagger Spray->Strike(2dmg,1-Burrowed)->Strike(6dmg) | dealt=8 taken=0

F23 [monster] multi:Myte+Myte (5R, HP 51->39, loss=12, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Noxious Fumes(power:+Noxious Fumes(2))->Deadly Poison(1+Poison(5))->Bubble Bubble(1Poison(5→14)) | dealt=16 taken=3
  R2[Myte: Atk(13)+Myte: StatusCard(2)]: Noxious Fumes+(power:Noxious Fumes(2→5))->Survivor(+8blk)->Defend(+5blk) | dealt=0 taken=5
  R3[Myte: Atk(4), Buff+Myte: Atk(15)]: Strike+(9dmg)->Defend(+5blk)->Toxic(exhaust:1) | dealt=9 taken=4
  R4[Myte: StatusCard(2)]: Acrobatics->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=0
  R5[Myte: Atk(15)]: Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Strike+(9dmg)->Strike(power:-Noxious Fumes) | dealt=19 taken=0

F27 [monster] Spiny Toad (5R, HP 39->39, loss=0, WIN)
  R1[Spiny Toad: Buff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Fasten(power:+Fasten(5))->Noxious Fumes(power:+Noxious Fumes(2))->Acrobatics+->Haze->Skewer+ | dealt=16 taken=0
  R2[Spiny Toad: Atk(17)]: Noxious Fumes+(power:Noxious Fumes(2→5))->Defend(+10blk)->Survivor(+8blk) | dealt=0 taken=0
  R3[Spiny Toad: Atk(17)]: Bubble Bubble(1Poison(9→18))->Defend(+10blk)->Defend(+10blk) | dealt=0 taken=0
  R4[Spiny Toad: Buff]: Neutralize+(4dmg,1+Weak(2))->Skewer+(33dmg) | dealt=37 taken=0
  R5[Spiny Toad: Atk(17)]: Defend(+10blk)->Defend+(+13blk) | dealt=0 taken=0

F28 [monster] Hunter Killer (7R, HP 39->32, loss=7, WIN)
  R1[Hunter Killer: Debuff]: Assassinate(10dmg,1+Vulnerable(1),exhaust:1)->Deadly Poison(1+Poison(5))->Dagger Spray(12dmg)->Strike(9dmg) | dealt=31 taken=0
  R2[Hunter Killer: Atk(7x3=21)]: Footwork(power:+Dexterity(1),power:+Strength(-1))->Defend(+6blk,power:Strength(-1→-2),power:-Dexterity)->Piercing Wail(power:Strength(-2→-3),power:+Dexterity(-1),2+Strength(-6),+Piercing Wail(6),exhaust:1) | dealt=0 taken=0
  R3[Hunter Killer: Atk(17)]: Survivor(+10blk)->Defend(+6blk,power:Strength(-1→-2),power:-Dexterity)->Bubble Bubble(power:Strength(-2→-3),power:+Dexterity(-1),1Poison(3→12)) | dealt=0 taken=1
  R4[Hunter Killer: Atk(7x3=21)]: Neutralize+(4dmg,power:Dexterity(2→1),power:+Strength(-1),1+Weak(2))->Fasten+(power:Strength(-1→-2),power:+Fasten(7),power:-Dexterity)->Defend(+12blk,power:Strength(-2→-3),power:+Dexterity(-1)) | dealt=4 taken=3
  R5[Hunter Killer: Atk(5x3=15)]: Piercing Wail(power:Dexterity(2→1),power:+Strength(-1),2+Strength(-6),+Piercing Wail(6))->Deadly Poison(power:Strength(-1→-2),power:-Dexterity,1Poison(10→15))->Acrobatics+->Haze | dealt=0 taken=0
  R6[Hunter Killer: Atk(17)]: Defend(+14blk,power:Dexterity(2→1),power:+Strength(-1))->Dagger Spray(6dmg,power:Strength(-1→-2),power:-Dexterity)->Bubble Bubble(power:Strength(-2→-3),power:+Dexterity(-1),1Poison(18→27)) | dealt=6 taken=3
  R7[Hunter Killer: Atk(7x3=21)]: Neutralize+(power:-Tender,power:-Fasten,power:-Dexterity) | dealt=0 taken=0

F30 [elite] Infested Prism (6R, HP 53->51, loss=2, WIN)
  R1[Infested Prism: Atk(22)]: Assassinate(10dmg,+1energy,1+Vulnerable(1),exhaust:1)->Fasten(power:+Fasten(5))->Survivor(+8blk)->Haze(+10blk,1+Poison(4))->Defend(+10blk)->Defend | dealt=10 taken=0
  R2[Infested Prism: Atk(16), Defend]: Neutralize+(4dmg,+1energy,1+Weak(2))->Predator+(20dmg,power:+Draw Cards Next Turn(2))->Bubble Bubble+(1Poison(3→15))->Defend(+10blk) | dealt=24 taken=2
  R3[Infested Prism: Atk(6x3=18)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Piercing Wail(2Strength(-6→-12),Piercing Wail(6→12))->Noxious Fumes+(power:+Noxious Fumes(3))->Skewer | dealt=0 taken=0
  R4[Infested Prism: Buff, Defend]: Footwork(power:+Dexterity(2))->Noxious Fumes(power:Noxious Fumes(3→5))->Deadly Poison(1Poison(22→27)) | dealt=0 taken=0
  R5[Infested Prism: Atk(26)]: Neutralize+(1+Weak(2))->Predator+(4dmg,power:+Draw Cards Next Turn(2))->Defend(+12blk)->Defend(+12blk) | dealt=4 taken=0
  R6[Infested Prism: Atk(15), Defend]: Strike(6dmg)->Backflip(+7blk)->Dagger Spray(8dmg)->Bubble Bubble+(1Poison(35→47))->Skewer | dealt=24 taken=0

F33 [boss] The Insatiable (9R, HP 70->45, loss=25, WIN)
  R1[The Insatiable: Buff, StatusCard(6)]: Assassinate(15dmg,1Vulnerable(1→2),exhaust:1)->Neutralize+(6dmg,1+Weak(2))->Acrobatics->Haze(+5blk)->Backflip(1Poison(4→9))->Deadly Poison | dealt=21 taken=0
  R2[The Insatiable: Atk(6x2=12)]: Fasten(power:+Fasten(5))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Bubble Bubble(1Poison(8→17)) | dealt=0 taken=2
  R3[The Insatiable: Atk(28)]: Footwork+(power:+Dexterity(3))->Noxious Fumes+(power:+Noxious Fumes(3))->Defend(+13blk) | dealt=0 taken=8
  R4[The Insatiable: Buff]: Neutralize+(4dmg,1Weak(2→4))->Acrobatics+->Frantic Escape(1Sandpit(2→3))->Frantic Escape(1Sandpit(3→4)) | dealt=4 taken=0
  R5[The Insatiable: Atk(7x2=14)]: Bouncing Flask(1Poison(20→29))->Bubble Bubble(1Poison(29→38)) | dealt=0 taken=14
  R6[The Insatiable: Atk(7x2=14)]: Defend(+13blk)->Frantic Escape(1Sandpit(2→3))->Frantic Escape(1Sandpit(3→4)) | dealt=0 taken=1
  R7[The Insatiable: Atk(22)]: Acrobatics->Defend(+13blk)->Defend(+13blk) | dealt=0 taken=0
  R8[The Insatiable: Buff]: Frantic Escape(1Sandpit(2→3))->Deadly Poison(1Poison(44→49)) | dealt=0 taken=0
  R9[The Insatiable: Atk(12x2=24)]: Neutralize+(4dmg,1+Weak(2))->Acrobatics+->Haze(1Poison(55→64))->Bubble Bubble | dealt=4 taken=0

F35 [monster] Devoted Sculptor (6R, HP 65->60, loss=5, WIN)
  R1[Devoted Sculptor: Buff]: Assassinate(15dmg,1Vulnerable(1→2),exhaust:1)->Jack of All Trades(exhaust:1)->Predator+(30dmg,power:+Draw Cards Next Turn(2))->Fasten(power:+Fasten(5)) | dealt=45 taken=0
  R2[Devoted Sculptor: Atk(12)]: Neutralize+(6dmg,1+Weak(2))->Deadly Poison(1+Poison(5))->Noxious Fumes+(power:+Noxious Fumes(3))->Defend(+10blk) | dealt=6 taken=0
  R3[Devoted Sculptor: Atk(15)]: Footwork+(power:+Dexterity(3))->Bubble Bubble(1Poison(7→16))->Defend(+13blk) | dealt=0 taken=2
  R4[Devoted Sculptor: Atk(30)]: Defend(+13blk)->Defend(+13blk)->Defend(+13blk) | dealt=0 taken=0
  R5[Devoted Sculptor: Atk(39)]: Neutralize+(4dmg,1+Weak(2))->Defend(+13blk)->Defend(+13blk)->Deadly Poison(1Poison(20→25)) | dealt=4 taken=3
  R6[Devoted Sculptor: Atk(36)]: Skewer(24dmg) | dealt=24 taken=0

F38 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (5R, HP 54->42, loss=12, WIN)
  R1[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff]: Assassinate(exhaust:1)->Predator+(power:+Draw Cards Next Turn(2))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Neutralize+ | dealt=0 taken=0
  R2[Scroll of Biting: Atk(10)+Scroll of Biting: Atk(7x2=14)]: Noxious Fumes+(power:+Noxious Fumes(3))->Backflip(+5blk)->Defend(+5blk) | dealt=0 taken=2
  R3[Scroll of Biting: Buff+Scroll of Biting: Atk(16)]: Acrobatics->Piercing Wail(2Strength(2→-4),+Piercing Wail(6))->Escape Plan+->Noxious Fumes+(power:Noxious Fumes(3→6))->Skewer | dealt=0 taken=10
  R4[Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Buff]: Fasten(power:+Fasten(5))->Defend(+10blk)->Backflip(+5blk) | dealt=0 taken=0
  R5[Scroll of Biting: Atk(16)+Scroll of Biting: Atk(9x2=18)]: Neutralize+(4dmg,1+Weak(2))->Escape Plan+(+5blk)->Corrosive Wave(power:+Corrosive Wave(2))->Acrobatics(1Poison(13→19))->Defend(+10blk) | dealt=4 taken=0

F40 [elite] Soul Nexus (9R, HP 42->5, loss=37, WIN)
  R1[Soul Nexus: Atk(29)]: Assassinate(15dmg,1Vulnerable(1→2),exhaust:1)->Escape Plan+(+5blk)->Backflip(+5blk)->Deadly Poison+(1+Poison(7))->Bubble Bubble(1Poison(7→16))->Mirage(+16blk,exhaust:1) | dealt=15 taken=3
  R2[Soul Nexus: Atk(18), DebuffStrong]: Neutralize+(6dmg,1+Weak(2))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Defend(+5blk)->Defend(+5blk) | dealt=6 taken=3
  R3[Soul Nexus: Atk(32)]: Master of Strategy(exhaust:1)->Footwork+(power:+Dexterity(3))->Calculated Gamble+(exhaust:1)->Backflip+(+11blk)->Defend(+8blk) | dealt=0 taken=13
  R4[Soul Nexus: Atk(27), DebuffStrong]: Escape Plan+->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Acrobatics+->Footwork+(power:Dexterity(3→6)) | dealt=0 taken=18
  R5[Soul Nexus: Atk(9x4=36)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6))->Bubble Bubble(1Poison(12→21))->Backflip(+11blk) | dealt=0 taken=0
  R6[Soul Nexus: Atk(27), DebuffStrong]: Neutralize+(3dmg,1+Weak(2))->Fasten(power:+Fasten(5))->Backflip+(+14blk)->Defend(+16blk) | dealt=3 taken=0
  R7[Soul Nexus: Atk(6x4=24)]: Defend(+16blk)->Defend(+16blk)->Bubble Bubble(1Poison(19→28)) | dealt=0 taken=0
  R8[Soul Nexus: Atk(43)]: Defend(+16blk)->Backflip(+11blk)->Escape Plan+(+11blk)->Survivor(+14blk)->Haze | dealt=0 taken=0
  R9[Soul Nexus: Atk(6x4=24)]: Neutralize+(4dmg,1+Weak(2))->Bouncing Flask(1Poison(30→39))->Bubble Bubble(1Poison(39→48)) | dealt=4 taken=0

F43 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (4R, HP 39->39, loss=0, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Neutralize+(6dmg,1+Weak(2))->Assassinate(15dmg,1Vulnerable(1→2),exhaust:1)->Footwork+(power:+Dexterity(3))->Noxious Fumes+(power:+Noxious Fumes(3))->Dagger Spray(36dmg)->Defend+(+11blk)->Survivor(+11blk) | dealt=57 taken=0
  R2[Flail Knight: Buff+Spectral Knight: Atk(15)+Magi Knight: Debuff]: Corrosive Wave+(power:+Corrosive Wave(3))->Escape Plan+(+8blk,1Poison(3→6),1Poison(3→6),1Poison(3→6))->Acrobatics+(1Poison(6→18),1Poison(6→18),1Poison(6→18))->Haze(+8blk,1Poison(22→28),1Poison(22→28),1Poison(22→28))->Backflip->Skewer | dealt=0 taken=0
  R3[Flail Knight: Atk(12x2=24)+Spectral Knight: Atk(15)+Magi Knight: Atk(10)]: Footwork(power:Dexterity(3→5))->Deadly Poison(1Poison(30→35))->Master of Strategy(exhaust:1)->Defend(+10blk) | dealt=0 taken=0
  R4[Flail Knight: Atk(18)+Spectral Knight: Atk(3x3=9)+Magi Knight: Defend]: Skewer | dealt=25 taken=0

F45 [monster] multi:Cubex Construct+Cubex Construct+Punch Construct (5R, HP 66->66, loss=0, WIN)
  R1[Punch Construct: Defend+Cubex Construct: Buff+Cubex Construct: Buff]: Assassinate(exhaust:1)->Noxious Fumes(power:+Noxious Fumes(2))->Fasten(power:+Fasten(5))->Calculated Gamble+(exhaust:1)->Noxious Fumes+(power:Noxious Fumes(2→5))->Neutralize+->Backflip+(+8blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=0 taken=0
  R2[Punch Construct: Atk(14)+Cubex Construct: Atk(6), Buff+Cubex Construct: Atk(9), Buff]: Escape Plan+(+5blk)->Acrobatics->Haze(+13blk)->Defend+(+13blk)->Defend+ | dealt=0 taken=0
  R3[Punch Construct: Atk(5x2=10), Debuff+Cubex Construct: Atk(11), Buff+Cubex Construct: Atk(11), Buff]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),2Strength(4→-2),+Piercing Wail(6),exhaust:1)->Master of Strategy(exhaust:1)->Footwork+(power:+Dexterity(3))->Defend(+13blk) | dealt=0 taken=0
  R4[Punch Construct: Defend+Cubex Construct: Atk(11x2=22)+Cubex Construct: Atk(11x2=22)]: Neutralize+(3dmg,1+Weak(2))->Escape Plan+->Backflip(+8blk)->Backflip+(+11blk)->Bubble Bubble(1Poison(17→26)) | dealt=23 taken=0
  R5[Punch Construct: Atk(14)+Cubex Construct: Atk(9), Buff]: none | dealt=0 taken=0

F46 [elite] Mecha Knight (9R, HP 66->58, loss=8, WIN)
  R1[Mecha Knight: Atk(25)]: Assassinate(10dmg,1Artifact(2→1),exhaust:1)->Footwork+(power:+Dexterity(3))->Calculated Gamble+(1-Artifact,exhaust:1)->Master of Strategy(exhaust:1)->Escape Plan+(+8blk)->Backflip(+8blk)->Backflip+(+11blk)->Skewer | dealt=10 taken=0
  R2[Mecha Knight: StatusCard(4)]: Noxious Fumes(power:+Noxious Fumes(2))->Predator+(60dmg,power:+Draw Cards Next Turn(2),power:-Gigantification)->Neutralize+(4dmg,1+Weak(2)) | dealt=64 taken=0
  R3[Mecha Knight: Defend, Buff]: Fasten(power:+Fasten(5))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Calculated Gamble+->Bubble Bubble(1Poison(2→11)) | dealt=0 taken=2
  R4[Mecha Knight: Atk(40)]: Defend(+13blk)->Defend(+13blk)->Defend(+13blk) | dealt=0 taken=3
  R5[Mecha Knight: StatusCard(4)]: Noxious Fumes+(power:Noxious Fumes(2→5))->Neutralize+(4dmg,1+Weak(2))->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=24 taken=0
  R6[Mecha Knight: Defend, Buff]: Escape Plan+(+8blk)->Bouncing Flask(1Poison(17→26))->Acrobatics | dealt=0 taken=2
  R7[Mecha Knight: Atk(45)]: Neutralize+(1+Weak(2))->Backflip(+8blk)->Defend(+13blk)->Survivor(+11blk) | dealt=0 taken=1
  R8[Mecha Knight: StatusCard(4)]: Bubble Bubble(1Poison(34→43))->Predator+(20dmg,power:+Draw Cards Next Turn(2)) | dealt=20 taken=0
  R9[Mecha Knight: Defend, Buff]: Defend(+13blk)->Defend(+13blk)->Backflip+(+11blk) | dealt=0 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (6R, HP 66->51, loss=15, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Assassinate(18dmg,1Vulnerable(1→2),exhaust:1)->Automation(power:+Automation(1))->Acrobatics+->Fasten(power:+Fasten(5))->Noxious Fumes(power:+Noxious Fumes(2))->Defend+(+13blk) | dealt=38 taken=5
  R2[Torch Head Amalgam: Atk(18)+Queen: Debuff]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Bubble Bubble(1Poison(3→13))->Defend(+10blk)->Strike(16dmg) | dealt=16 taken=8
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Master of Strategy(exhaust:1)->Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Acrobatics->Haze+(power:+Dexterity(3))->Footwork+(+8blk)->Backflip+(4dmg,1+Weak(2))->Neutralize+ | dealt=4 taken=0
  R4[Torch Head Amalgam: Atk(16)+Queen: Buff, Defend]: Corrosive Wave+(power:+Corrosive Wave(3))->Footwork+(power:Dexterity(3→6))->Noxious Fumes+(power:Noxious Fumes(2→5),1Poison(14→22),1Poison(24→32))->Escape Plan+(1Poison(22→26),1Poison(32→36))->Calculated Gamble+(+1energy,1Poison(26→58),1Poison(36→68),exhaust:1)->Neutralize+(4dmg,1Weak(1→3))->Acrobatics+(1Poison(58→74),1Poison(68→84))->Haze+(+14blk)->Defend+ | dealt=4 taken=2
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Backflip+(+10blk)->Defend+(+14blk)->Deadly Poison(1Poison(96→102))->Bubble Bubble(1Poison(102→112)) | dealt=0 taken=0
  R6[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Calculated Gamble+(+1energy,1Poison(91→98),1Poison(117→124))->Piercing Wail(2Strength(3→-3),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6)) | dealt=0 taken=0

### Non-combat Decisions (222 decisions)
F1 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Winged Boots provides immense pathing flexibility, allowing us to hunt extra Elites, reach specific Campfires or Shops, or dodge bad pathing entirely. This run-long utility outweighs a single card remove or a random rare coupled with a curse.
  strategic_note: Foundation phase: Looking for frontloaded damage and AoE to survive early Act 1 Elites, leveraging Winged Boots for optimal pathing.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=2) | source=llm
  HP 56->56 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Starting the run by following the recommended route through a monster node. Early hallway fights are essential for the Silent to find frontloaded damage cards (like Poisoned Stab or Dagger Throw) before facing Act 1 elites.
  strategic_note: Foundation phase: Prioritize frontloaded damage and AoE in early card rewards to survive Act 1 elites; use Winged Boots later to snipe optimal nodes or bypass forced damage.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 111->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 56->56 | Gold 111->111 | Deck 12->13
  deck_change: picked Bubble Bubble
  reasoning: Bubble Bubble is an extremely powerful Uncommon for Poison builds. While it's currently unplayable without a base poison source, taking it on Floor 2 allows us to pivot into a Poison trajectory early. We must prioritize finding a poison applicator (Deadly Poison, Snakebite, Poisoned Stab) immediately.
  strategic_note: Foundation plan: currently holding a strong poison payoff (Bubble Bubble), so prioritize finding a cheap poison applicator (Deadly Poison, Poisoned Stab). Need frontload damage for Act 1 elites and avoid taking conflicting archetypes.

F2 [map] choose_map_node (option_index=2) | source=llm
  HP 56->56 | Gold 111->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Early Act 1 requires drafting frontloaded damage cards to prepare for elites. Following the recommended route to maximize card reward opportunities while HP is high.
  strategic_note: Foundation phase: searching for high-impact frontloaded damage and AoE to safely tackle upcoming Act 1 elites while leveraging Winged Boots for pathing flexibility.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 111->129 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 129->129 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 55->55 | Gold 129->129 | Deck 13->14
  deck_change: picked Dagger Spray
  reasoning: Dagger Spray is excellent early AoE damage, solving immediate combat problems against multi-enemy Act 1 hallways and elites like Sentries or Slime Boss. It bridges the gap while we look for a primary poison source to activate Bubble Bubble.
  strategic_note: Foundation plan: survive with frontload damage and AoE while looking for a primary poison enabler (like Deadly Poison) to turn on Bubble Bubble. Keep the deck lean and prioritize early damage before committing to scaling defense or cycle.

F3 [map] choose_map_node (option_index=3) | source=llm
  HP 55->55 | Gold 129->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node. Early Act 1 requires building a damage foundation through card rewards before tackling elites. I have 129 gold, which is not enough for a high-impact shop visit this early, especially with Winged Boots available to pivot later if needed.
  strategic_note: Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE for Act 1 elites while using Winged Boots as a safety net for later pathing adjustments.

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 129->148 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 19 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 148->148 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 55->55 | Gold 148->148 | Deck 14->15
  deck_change: picked Deadly Poison
  reasoning: Deadly Poison perfectly enables Bubble Bubble, creating a highly efficient poison engine that will solve Act 1 bosses and elites. We are now committed to poison scaling.
  strategic_note: Committed poison plan: use Deadly Poison to set up Bubble Bubble for massive poison damage, then defend. Needs more draw/discard to align the combo and strong mitigation. Avoid generic attacks.

F4 [map] choose_map_node (option_index=3) | source=llm
  HP 55->55 | Gold 148->148 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the recommended route to find an Unknown node after three consecutive hallway fights. This mimics past successful patterns to break up chip damage while searching for deck-defining events or early gold/relics before the first Elite.
  strategic_note: Foundation phase: searching for frontloaded damage and AoE to handle Act 1 Elites; prioritize card rewards that solve Gremlin Nob and Sentries while using rest sites for upgrades.

F5 [shop] buy_card (option_index=4) | source=plan
  HP 55->55 | Gold 148->74 | Deck 15->16
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [1/2]: Core scaling engine for poison. With Deadly Poison and Bubble Bubble already in the deck, this moves us into Phase 2 committed poison.

F5 [shop] buy_card (option_index=0) | source=plan
  HP 55->55 | Gold 74->37 | Deck 16->17
  deck_change: bought Predator
  reasoning: Shop plan [2/2]: Incredible sale value. Solves Act 1 frontload damage needs and provides crucial next-turn draw to cycle back to our poison skills.

F5 [shop] close_shop_inventory | source=plan
  HP 55->55 | Gold 37->37 | Deck 17->17
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F5 [shop] proceed | source=auto
  HP 55->55 | Gold 37->37 | Deck 17->17
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F5 [map] choose_map_node (option_index=3) | source=llm
  HP 55->55 | Gold 37->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the recommended route to secure a monster fight. I need to find frontloaded damage and AoE cards to handle the upcoming Floor 11 Elite, and my current HP (79%) is sufficient to handle hallway attrition. This path also leads directly to a rest site for a potential upgrade.
  strategic_note: Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE before the first Elite, utilizing the healthy HP buffer to avoid early shops or excessive unknowns.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 37->50 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 50->50 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 50->50 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 49->49 | Gold 50->50 | Deck 17->18
  deck_change: picked Acrobatics
  reasoning: Acrobatics provides crucial cycle for our 17-card deck, helping us find our poison core (Noxious Fumes, Deadly Poison, Bubble Bubble) and key defensive cards faster. As an Uncommon, it is harder to find than Piercing Wail later.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling and more cycle; skip off-plan attacks and expensive cards.

F6 [map] choose_map_node (option_index=3) | source=llm
  HP 49->49 | Gold 50->50 | Deck 18->18
  deck_change: no deck change
  reasoning: Moving to the campfire as recommended by the route. At 70% HP, this provides a safe opportunity to Smith and upgrade a key card like Neutralize or a damage dealer, strengthening the deck for the upcoming Elite fight later in the act. The shop is skipped due to low gold (50), and taking an Elite now is too risky without further deck development.
  strategic_note: Foundation phase: prioritize high-impact upgrades at rest sites to secure the mid-act Elite; currently seeking front-loaded damage and AoE to stabilize the deck.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=16, note_scope=run, note_triggers=deck_building) | source=llm
  HP 49->49 | Gold 50->50 | Deck 18->18
  deck_change: upgraded Predator->Predator+
  reasoning: With a healthy 49 HP, we can afford to upgrade instead of heal. Predator+ provides a massive 20-damage burst which is critical for taking down early elites like Gremlin Nob and Lagavulin before they can deal fatal damage.
  strategic_note: Foundation phase transitioning to poison control: use Predator and Dagger Spray to clear Act 1 hallway/elite threats while setting up Noxious Fumes and Bubble Bubble for boss scaling. Needs more block and card removal to survive later turns.

F7 [rest_site] proceed | source=auto
  HP 49->49 | Gold 50->50 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=3) | source=llm
  HP 49->49 | Gold 50->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Following the recommended route to take a hallway fight. I need to see more card rewards to secure frontloaded damage and AoE before the upcoming Elites on Floors 11 and 14. 49 HP is sufficient to handle a standard combat.
  strategic_note: Foundation phase: prioritizing hallway fights to draft frontloaded damage and AoE for upcoming Elites. Currently seeking core damage cards to complement the basic Silent kit before using gold at the Floor 12 shop.

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 24->24 | Gold 50->69 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 19 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 24->24 | Gold 69->69 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 24->24 | Gold 69->69 | Deck 18->19
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail provides unmatched mitigation against multi-hit attacks, which is critical for surviving Elites and Bosses. Our deck already has a strong poison core (Noxious Fumes, Deadly Poison, Bubble Bubble), so covering our defensive weakness is the priority.
  strategic_note: Committed poison plan: apply poison with Noxious Fumes, Deadly Poison, and Bubble Bubble, then stall with advanced defense like Piercing Wail. Needs more draw and block scaling; avoid adding generic attacks.

F8 [map] choose_map_node (option_index=3) | source=llm
  HP 24->24 | Gold 69->69 | Deck 19->19
  deck_change: no deck change
  reasoning: My HP is critical at 24/70 (34%) and I have an Elite coming up soon in the recommended route. Although the route suggests an Unknown, I am using Winged Boots to jump to a Rest Site immediately. Resting is necessary to survive the upcoming Elite and ensure I can convert current gold and card rewards into a winning Act 1 finish.
  strategic_note: Foundation phase: Urgently seeking a rest to stabilize low HP before the next elite; looking for poison or shiv scaling to transition from basic survival to a cohesive game plan.

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 24->24 | Gold 69->69 | Deck 19->19
  deck_change: upgraded Noxious Fumes->Noxious Fumes+
  reasoning: The route plan shows the next combat is not until F12 (Elite), with a Treasure (F10) and another Rest Site (F11) coming up first. Smithing here is optimal because if the Treasure yields a healing relic (like Regal Pillow, Meat on the Bone, or Blood Vial), we avoid wasting its value, and we can still choose to heal at F11 right before the Elite if our HP remains critical. Upgrading Noxious Fumes accelerates our poison engine substantially, synergizing with Bubble Bubble to burst down Elites.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs more block and draw; skip raw attacks.

F9 [rest_site] proceed | source=auto
  HP 24->24 | Gold 69->69 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=2) | source=llm
  HP 24->24 | Gold 69->69 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the recommended route to the treasure node. My HP is critically low (24/70), so I need the upcoming Rest Site (r10) to heal before facing the Elite at r11. Winged Boots provide flexibility, but the current path toward the Rest Site is the safest way to stabilize.
  strategic_note: Foundation phase: Urgently need to stabilize HP and find frontloaded damage or AoE. The deck is currently vulnerable; prioritizing survival through the next Rest Site to prepare for the mid-act Elite.

F10 [treasure] open_chest | source=random
  HP 24->24 | Gold 69->118 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 24->24 | Gold 118->118 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim: Pantograph

F10 [treasure] proceed | source=random
  HP 24->24 | Gold 118->118 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=2) | source=llm
  HP 24->24 | Gold 118->118 | Deck 19->19
  deck_change: no deck change
  reasoning: With 24/70 HP, I must rest before the upcoming Elite at r11. This Rest Site is the core of the planned route and will allow me to take the Elite fight safely.
  strategic_note: Foundation phase: searching for frontloaded damage and AoE to stabilize; prioritizing survivability via rest sites before Elites while Winged Boots allow for flexible pathing.

F11 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 24->45 | Gold 118->118 | Deck 19->19
  deck_change: no deck change
  reasoning: HP is critically low at 24/70, and the very next node is an Act 1 Elite. Resting to 45 HP is necessary to survive the burst damage from Elites like Gremlin Nob or Lagavulin, especially with 3 monster fights following it.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more block and draw; skip raw attacks.

F11 [rest_site] proceed | source=auto
  HP 45->45 | Gold 118->118 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=3) | source=llm
  HP 45->45 | Gold 118->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Taking the Elite at (c3, r11) as recommended by the route. With 45 HP and Pantograph's 25 HP heal before the boss, I can afford the health cost of an Elite fight to secure a relic and higher-rarity card reward. Winged Boots provide flexibility to avoid subsequent hazards if this fight goes poorly.
  strategic_note: Foundation phase: Seeking frontloaded damage and AoE to safely navigate Act 1 Elites. Using HP as a resource enabled by Pantograph, prioritizing relics over safety until a coherent engine (Shiv or Poison) is established. Avoid hoarding gold and aim for a final shop before the boss.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 118->157 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 39 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 157->157 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Fire Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 157->157 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim relic: Stone Cracker

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 157->157 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 42->42 | Gold 157->157 | Deck 19->20
  deck_change: picked Haze
  reasoning: Haze fits our committed Poison plan perfectly, providing burst AoE poison. While its 3-energy cost is high, its Sly keyword means we can play it for free when discarded by Acrobatics or Survivor. We will prioritize picking up more discard outlets to enable it consistently.
  strategic_note: Committed poison plan: stack poison with Fumes and Bubble Bubble, prioritize discard outlets to enable Sly cards like Haze, and focus on surviving while passive damage scales. Avoid narrow attacks; need more cycle, discard, and robust block.

F12 [map] choose_map_node (option_index=2) | source=llm
  HP 42->42 | Gold 157->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the route intelligence to reach 6 hallway fights for essential card drafting. 157 gold is slightly low for a shop visit if I want to afford a relic or multiple high-impact cards, so taking the monster node first to increase gold and card selection is better. Winged Boots and Pantograph provide a safety net for the upcoming boss.
  strategic_note: Foundation phase: searching for high-impact frontloaded damage and AoE to secure a clean Slime Boss split. Prioritizing hallway fights to build deck density before the final rest site; Pantograph allows for more aggressive pathing by providing a heal before the boss.

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 157->173 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 173->173 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F13 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 32->32 | Gold 173->173 | Deck 20->21
  deck_change: picked Piercing Wail
  reasoning: We are committed to a poison engine, which relies on stalling while passive damage ticks. Piercing Wail is premium mitigation that completely shuts down multi-hit attacks, and because it exhausts, it won't clog our deck on later cycles. Having a second copy increases our chances of drawing it on crucial boss turns.
  strategic_note: Committed poison plan: stack poison with Fumes/Bubble on safe burst turns, then defend with Wail/Survivor while passive poison kills. Needs dex/block scaling and Strike removals; skip off-plan attacks.

F13 [map] choose_map_node (option_index=1) | source=llm
  HP 32->32 | Gold 173->0 | Deck 21->21
  deck_change: no deck change
  reasoning: With 32 HP and Pantograph's 25 HP boss heal, I have a safe buffer for the boss but need to ensure the deck is strong enough to minimize chip damage in the final hallways. Choosing the monster node to hunt for a final damage or scaling piece before the last campfire upgrade. Staying on the recommended route to reach the final Rest Site at floor 15.
  strategic_note: Foundation phase: pursuing frontloaded damage and AOE to handle Act 1 hallways and the boss; Pantograph allows for more aggressive floor choices by providing a heal before the boss, so prioritizing card rewards over defensive events.

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 173->192 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 19 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 192->192 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Touch of Insanity

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 192->192 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 29->29 | Gold 192->192 | Deck 21->21
  deck_change: no deck change
  reasoning: Our deck already has strong poison application with Noxious Fumes+, Deadly Poison, and Haze to enable Bubble Bubble. Adding more common cards like Poisoned Stab or a 3rd Piercing Wail will only bloat the deck, making it harder to draw our key engine pieces and our single strong frontload card (Predator+). Skipping is best to maintain deck consistency.
  strategic_note: Committed poison plan: rely on Noxious Fumes+ and Bubble Bubble to scale damage while surviving with Piercing Wail and basic block. Priority now is removing basic Strikes/Defends and finding more card draw to accelerate setup.

F14 [map] choose_map_node (option_index=1) | source=llm
  HP 29->29 | Gold 192->0 | Deck 21->21
  deck_change: no deck change
  reasoning: With 29 HP, taking another Elite (index 0 or 3) is too risky before the final rest site. The monster node (index 1) follows the recommended route, allowing for a card reward and gold while preserving HP to reach the campfire and the boss, where Pantograph will provide a significant heal.
  strategic_note: Foundation phase: searching for frontloaded damage and AoE to stabilize; prioritizing safe hallway fights over risky elites at low HP while relying on Pantograph for boss sustain.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 192->203 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F15 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 22->22 | Gold 203->203 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 22->22 | Gold 203->203 | Deck 21->22
  deck_change: picked Expertise
  reasoning: We are fully committed to a poison win condition (Fumes+, Bubble Bubble, Haze, Deadly Poison). To make this engine work, we need to cycle quickly to our poison appliers and defensive tools like Piercing Wail. Expertise provides strong, cheap card draw that helps us assemble our turns consistently.
  strategic_note: Committed poison plan: apply poison with Fumes+, Bubble Bubble, and Deadly Poison, then focus purely on survival. Cycle aggressively to find Piercing Wails for big multi-attacks. Needs block scaling like Footwork and more removals; skip generic attacks and narrow synergies.

F15 [map] choose_map_node (option_index=0) | source=llm
  HP 22->22 | Gold 203->203 | Deck 22->22
  deck_change: no deck change
  reasoning: I am at 22/70 HP and have the Act 1 Boss coming up next. I must rest to ensure I survive the boss, especially since Pantograph will provide an additional 25 HP heal at the start of the fight. This node is also the most direct path to the boss.
  strategic_note: Foundation phase: Seeking defensive scaling and energy relics. Currently pivoting to survival mode for the Act 1 boss; rely on Pantograph for a safe HP buffer and use this rest site to heal or upgrade a key defensive card if HP feels sufficient.

F16 [rest_site] choose_rest_option (option_index=1, smith_card_index=10, note_scope=run, note_triggers=deck_building) | source=llm
  HP 22->22 | Gold 203->203 | Deck 22->22
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With Pantograph, we will heal 25 HP at the start of the boss fight, bringing us to a very comfortable 47 HP. This allows us to greed a crucial upgrade. Neutralize+ provides 2 turns of Weak, which is exceptional mitigation for any Act 1 boss, effectively saving more HP over the fight than a rest would provide.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.

F16 [rest_site] proceed | source=auto
  HP 22->22 | Gold 203->203 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 22->47 | Gold 203->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 3->3 | Gold 203->303 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 3->3 | Gold 303->303 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Attack Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 3->3 | Gold 303->303 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 3->3 | Gold 303->303 | Deck 22->23
  deck_change: picked Assassinate
  reasoning: We are fully committed to a poison engine, but Act 2 hallways demand immediate frontload damage to survive before poison scales. Assassinate provides 0-cost Innate damage and Vulnerable, which combos perfectly with Predator+ on turn 1 to burst down dangerous targets. Since it Exhausts, it doesn't clutter our deck in long boss fights.
  strategic_note: Committed poison plan: rely on Noxious Fumes+, Bubble Bubble, and Haze to kill, using Piercing Wail and block to survive. Need upgraded defense and energy/draw; remove Strikes. Play Assassinate + Predator turn 1 for immediate threat removal.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 3->56 | Gold 303->303 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 303->303 | Deck 23->23
  deck_change: no deck change
  reasoning: Pael's Blood provides a permanent +1 card draw every turn. Since our deck relies on setting up Noxious Fumes and finding specific defensive pieces like Piercing Wail on the exact right turns, extra draw is incredibly valuable and immediately boosts our consistency across every combat.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more block and card removals; avoid basic attacks.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 303->303 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 303->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node. With 303 gold and Winged Boots, I have significant flexibility to pivot later, but early Act 2 requires testing the deck's combat readiness to see if I need more front-loaded damage or defensive scaling. The route leads into a Shop where I can spend my high gold balance.
  strategic_note: Foundation phase: The deck is currently seeking defensive scaling and reliable energy. I will use early Act 2 hallway fights to identify gaps in damage or mitigation before using my 303 gold at an upcoming shop to pivot into a committed build.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 303->319 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 319->319 | Deck 22->23
  deck_change: picked Expertise
  reasoning: Claim specialcard: Take your stolen card back.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: We are fully committed to a poison strategy with Noxious Fumes, Bubble Bubble, Deadly Poison, and Haze. None of the offered cards (Slice, Up My Sleeve, Strangle) support poison scaling or provide defense/draw. Skipping keeps the deck lean to draw our poison engines and cycle cards faster.
  strategic_note: Committed poison plan: apply poison with Fumes/Deadly Poison/Haze, scale with Bubble Bubble, and use Piercing Wails/Survivor to survive. Need scaling defense (Footwork/Leg Sweep) and more cycle/energy. Skip off-plan attacks.

F19 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which prioritizes non-combat nodes to preserve HP. With 319 gold and Winged Boots charges, taking the Unknown node leads into a high-value Shop where I can spend my gold to scale the poison engine and improve defense.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and consistent block; prioritize removing basic strikes at shops.

F20 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: Enchanting our only Power (Noxious Fumes+) with Swift 2 means we draw 2 cards when we play our main scaling condition, effectively turning it into a draw engine on our setup turn and mitigating its tempo loss.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and consistent block; prioritize removing basic strikes at shops.

F20 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F20 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 319->319 | Deck 23->23
  deck_change: no deck change
  reasoning: I have 319 gold, making this shop extremely high value. According to the Route Intelligence, shops should be prioritized with 150+ gold. I need to spend this gold to find card draw, better block, or powerful poison-synergy relics/cards to stabilize for the rest of Act 2.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while defending with Weakness; currently targeting shops to convert high gold into card draw, block, and poison scaling while removing basic Strikes.

F21 [shop] buy_card (option_index=3) | source=plan
  HP 53->53 | Gold 319->247 | Deck 23->24
  deck_change: bought Bouncing Flask
  reasoning: Shop plan [1/4]: Top-tier poison generator that perfectly fuels our Bubble Bubble engine and provides massive single-target scaling for bosses.

F21 [shop] buy_card (option_index=5) | source=plan
  HP 53->53 | Gold 247->159 | Deck 24->25
  deck_change: bought Fasten
  reasoning: Shop plan [2/4]: We have 5 basic Defends. Fasten effectively gives +5 block to all of them, providing critical defensive scaling to survive Act 2 and Act 3 damage while poison ticks.

F21 [shop] remove_card_at_shop | source=plan
  HP 53->53 | Gold 159->159 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Removing a Strike increases the density of our poison, block, and draw cards. Essential for consistency.

F21 [card_select] select_deck_card (option_index=0) | source=llm
  HP 53->53 | Gold 159->84 | Deck 25->24
  deck_change: lost Strike
  reasoning: We are fully committed to a poison scaling engine. Basic Strikes are useless for damage and only clutter our draws, preventing us from finding our poison and defense cards.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs more efficient cycle; avoid adding attacks.

F21 [shop] buy_potion (option_index=1) | source=plan
  HP 53->53 | Gold 84->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan [4/4]: Excellent burst application for an elite fight or to set up a massive Turn 1 Bubble Bubble.

F21 [shop] close_shop_inventory | source=plan
  HP 53->53 | Gold 36->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F21 [shop] proceed | source=auto
  HP 53->53 | Gold 36->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F21 [map] choose_map_node (option_index=0) | source=llm
  HP 53->53 | Gold 36->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node to hunt for card draw or more robust block, as the poison engine is established but the deck needs better cycling and mitigation to survive Act 2 hallways.
  strategic_note: Committed poison plan: use Noxious Fumes and Bubble Bubble to scale damage while prioritizing block and Weakness. Current priority is finding card draw and premium block like Leg Sweep or Blur; avoid elites until mitigation is stronger.

F22 [card_select] select_deck_card (option_index=2) | source=llm
  HP 51->51 | Gold 36->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Pounce deals 12 unconditional damage, which combined with Dagger Spray and Strikes is enough to break Tunneler's 24 block.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 36->54 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 54->54 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 54->54 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 51->51 | Gold 54->54 | Deck 24->25
  deck_change: picked Noxious Fumes
  reasoning: A second Noxious Fumes significantly accelerates our AoE poison scaling and improves consistency. Since the Act 2 boss floods the deck with status cards, having strong passive damage already in play will let us focus purely on survival and managing the boss mechanics without needing to constantly draw our damage cards.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and scaling block; prioritize removing basic strikes.

F22 [map] choose_map_node (option_index=0) | source=llm
  HP 51->51 | Gold 54->0 | Deck 25->25
  deck_change: no deck change
  reasoning: The deck is currently a 'committed poison plan' but lacks sufficient defense and card draw to handle Act 2's aggressive hallways safely. Following the route's recommendation for a monster fight provides a necessary card reward opportunity to find essential block or draw pieces (like Blur, Acrobatics, or Backflip) before the mid-act elites and boss. While an Unknown node could offer a skip, the deck is not yet strong enough to stop developing its core engine.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while prioritizing Weak and Piercing Wails for survival. Needs more card draw and consistent block; seek removals for basic strikes at shops and card rewards that enhance defensive rotation.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 54->71 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 17 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 71->71 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 39->39 | Gold 71->71 | Deck 25->26
  deck_change: picked Acrobatics
  reasoning: The deck is fully committed to a Poison engine and needs cycle to consistently find key mitigation (Piercing Wails, Fasten) and multipliers (Bubble Bubble). Acrobatics also provides a discard outlet to trigger Haze (Sly) for free AoE poison. With 25 cards, more draw is always welcome.
  strategic_note: Committed poison plan: survive with Piercing Wail and Fasten while stacking poison via Fumes, Flask, and Bubble Bubble. Use Acrobatics to dig for key pieces and discard Haze for free triggers. Avoid adding raw attacks.

F23 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Follows the recommended route to minimize attrition in Act 2. With 39 HP and an upcoming rest site at floor 25, taking an Unknown node is safer than a hallway fight and more efficient than resting early. Pantograph provides a buffer for the boss, allowing more aggressive upgrading at campfires if HP remains stable.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Current priorities are card draw to find scaling faster and additional block; Winged Boots are reserved to bypass the floor 31 Elite if HP is low.

F24 [event] choose_event_option (option_index=1) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Our deck relies on poison for damage, so giving an attack Corrupted is mostly useless and actively harms us with the unblockable damage. Transforming a basic Strike is a fantastic opportunity to thin a bad card and potentially gain something useful for our engine.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F24 [card_select] select_deck_card (option_index=0) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: changed: +Skewer; -Strike
  reasoning: Transforming a basic Strike, as our deck is fully committed to a Poison engine and Strike provides almost no value.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F24 [event] choose_event_option (option_index=0) | source=auto
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F24 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the recommended route to a RestSite. At 56% HP, this node allows me to either upgrade a key poison piece for faster scaling or heal to sustain through the upcoming hallway fights. Pantograph provides a safety net for the boss, but Act 2 hallways require high current HP to survive.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Bubble Bubble to stack poison, then defend with Weak and Piercing Wails. Needs more card draw and block; remove basic strikes.

F25 [rest_site] choose_rest_option (option_index=1, smith_card_index=12, note_scope=run, note_triggers=all) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: upgraded Acrobatics->Acrobatics+
  reasoning: With 39 HP, we have enough health to survive upcoming hallway fights, and we have another rest site before the F30 Elite. Upgrading Acrobatics significantly improves our deck's consistency and velocity, helping us quickly find our poison win condition and block cards, while also providing better chances to trigger Haze's Sly effect.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Bouncing Flask, and Bubble Bubble to stack poison, then defend with Fasten-boosted Defends and Piercing Wails. Needs more card draw to consistently set up the engine and remove basic strikes.

F25 [rest_site] proceed | source=auto
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F25 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 71->71 | Deck 26->26
  deck_change: no deck change
  reasoning: Standard pathing to the next floor. All options are Treasure rooms, so index 0 is chosen to maintain the most flexible connectivity for the upcoming nodes as per the route recommendation.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F26 [treasure] open_chest | source=random
  HP 39->39 | Gold 71->118 | Deck 26->26
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 39->39 | Gold 118->118 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim: Pendulum

F26 [treasure] proceed | source=random
  HP 39->39 | Gold 118->118 | Deck 26->26
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 118->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Current HP (39/70) is too low to risk back-to-back Elites without more stabilization. Following the route to the Monster node provides a chance for card rewards and gold while preserving HP for the upcoming mandated Elite and Boss. Winged Boots are available for emergency pathing later if needed.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 118->133 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 133->133 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F27 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 39->39 | Gold 133->133 | Deck 26->27
  deck_change: picked Footwork
  reasoning: Footwork is the premier defensive scaler for a poison deck. We already have incredible poison scaling with Fumesx2, Flask, Bubble Bubble, and Deadly Poison, so survival is our only remaining challenge. Footwork pairs well with our 5 Defends and Survivor to keep us alive while poison does the work.
  strategic_note: Committed poison plan: survive with scaling block (Footwork, Fasten) and Piercing Wails while passive poison kills. Retain draw to find defensive answers and setup pieces faster.

F27 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 133->0 | Deck 27->27
  deck_change: no deck change
  reasoning: I have 133 gold, which is slightly below the 150+ threshold for a high-impact shop. The route recommends a Monster fight here to build deck strength and gather more gold before the next Elite and Boss. My HP is 39/70, which is healthy enough for a standard Act 2 hallway fight, especially with Pantograph providing a safety net for the boss.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 133->149 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 149->149 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 149->149 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 32->32 | Gold 149->149 | Deck 27->28
  deck_change: picked Backflip
  reasoning: Backflip provides sustained card draw and block, which scales perfectly with our Footwork and helps cycle our large 27-card deck to find our poison core and defensive tools. Calculated Gamble is also strong, but Backflip is reusable and provides essential block for extended boss fights.
  strategic_note: Committed poison plan: stack passive poison with Fumes and Flask, scale block with Footwork and Fasten, and aggressively cycle the deck with Acrobatics and Backflip. Keep the deck lean by removing basic attacks, and rely on poison for damage.

F28 [map] choose_map_node (option_index=0) | source=llm
  HP 32->32 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Current HP is 46%, which is dangerous for Act 2 hallways or elites. The route intelligence suggests prioritizing rest sites and avoiding elites in Act 2 when possible. Taking the RestSite allows for either a necessary heal or an upgrade to improve my defensive/poison scaling before the next sequence of floors. This also aligns with the route guide recommendation.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F29 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 32->53 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: With 32 HP going into an Act 2 Elite (Slavers, Gremlin Leader, or Book of Stabbing), we are at risk of dying to a bad turn 1 draw, especially against Slavers. Healing provides a 21 HP buffer to guarantee we survive. We have another Rest Site before the boss, and Pantograph will heal us at the boss itself, allowing us to smith there.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Look for more reliable draw to setup powers faster and remove basic strikes.

F29 [rest_site] proceed | source=auto
  HP 53->53 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=llm
  HP 53->53 | Gold 149->0 | Deck 28->28
  deck_change: no deck change
  reasoning: With 53 HP and a decent poison foundation, I need to transition from passive hallway scaling to elite-slaying power. Pantograph provides a 25 HP cushion for the Act boss, making it safer to take elite chip damage now for a chance at a relic and rare card. Following the Route Intelligence while Winged Boots remains available for emergency path correction if the elite fight goes poorly.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 149->186 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 37 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 186->186 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 186->186 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim relic: Bag of Marbles

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 186->186 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 51->51 | Gold 186->186 | Deck 28->28
  deck_change: no deck change
  reasoning: We are committed to a Poison core. Abrasive requires discard outlets to be played effectively via Sly, and with only 3 discard effects in a 28-card deck, it risks being a dead draw too often. Boss 2 floods the deck with statuses, so keeping the deck as lean as possible is critical. Skip is the best choice to ensure consistent draw of our poison setup and defensive cards.
  strategic_note: Committed poison plan: setup Noxious Fumes and apply poison while using Dexterity and Weak to survive. Draw heavily to bypass boss statuses and find Frantic Escapes. Skip off-plan cards to keep the deck consistent.

F30 [map] choose_map_node (option_index=0) | source=llm
  HP 51->51 | Gold 186->186 | Deck 28->28
  deck_change: no deck change
  reasoning: Following the recommended route to the Unknown node. With the Act 2 boss approaching and Pantograph providing a 25 HP cushion, an Unknown node offers a chance for a high-value event or a safe bypass of a potentially high-attrition hallway fight. This preserves HP for the final Rest Site upgrade/rest before the boss.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F31 [treasure] open_chest | source=random
  HP 51->51 | Gold 186->237 | Deck 28->28
  deck_change: no deck change
  reasoning: Open chest

F31 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 51->51 | Gold 237->237 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim: Amethyst Aubergine

F31 [treasure] proceed | source=random
  HP 51->51 | Gold 237->237 | Deck 28->28
  deck_change: no deck change
  reasoning: Proceed from treasure

F31 [map] choose_map_node (option_index=0) | source=llm
  HP 51->51 | Gold 237->237 | Deck 28->28
  deck_change: no deck change
  reasoning: Moving to the final rest site before the Act 2 boss. With Pantograph providing 25 HP at the start of the boss fight, I am effectively at full health, allowing me to Smith and upgrade a key card rather than resting.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=22) | source=llm
  HP 51->51 | Gold 237->237 | Deck 28->28
  deck_change: upgraded Footwork->Footwork+
  reasoning: With Pantograph, we will heal 25 HP at the start of the boss fight, which will fully heal us from 51 HP to our max of 70 HP. Resting here would provide exactly zero value. We Smith Footwork for a permanent +1 Dexterity boost, which significantly improves our mitigation engine for the boss fight.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Look for more reliable draw to setup powers faster and remove basic strikes.

F32 [rest_site] proceed | source=auto
  HP 51->51 | Gold 237->237 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 51->70 | Gold 237->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 237->337 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 100 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 337->352 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 352->352 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 352->352 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 45->45 | Gold 352->352 | Deck 28->29
  deck_change: picked Corrosive Wave
  reasoning: Our deck has a massive amount of draw (Acrobatics x2, Backflip, Expertise) and we are heavily committed to Poison. Corrosive Wave turns our cycle cards into massive AoE Poison generation for just 1 energy, providing excellent scaling and AoE for Act 3.
  strategic_note: Committed poison plan: apply poison rapidly with Bouncing Flask, Deadly Poison, and Corrosive Wave combined with heavy draw cycle, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 45->65 | Gold 352->352 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1) | source=llm
  HP 65->65 | Gold 352->352 | Deck 29->29
  deck_change: no deck change
  reasoning: Delicate Frond effectively gives 2-3 random potions every single combat, providing immense flexibility, burst potential, healing, and energy across all remaining fights including the Act 3 Boss.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Use the infinite potion generation from Delicate Frond to solve immediate energy or scaling needs every combat.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 65->65 | Gold 352->352 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=2) | source=llm
  HP 65->65 | Gold 352->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Following the recommended route to a monster node. With 352 gold and Winged Boots, I am well-positioned to find a high-value shop later or bypass dangerous nodes if necessary, but I need to see card rewards now to find better poison scaling or defensive consistency for Act 2.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bubble Bubble while mitigating damage with Piercing Wail and Weakness. Focus on card draw and block; transform or remove basic strikes at every opportunity.

F35 [card_select] select_deck_card (option_index=0) | source=llm
  HP 65->65 | Gold 352->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Jack of All Trades costs 0 and replaces itself with another Colorless card, giving us a flexible option for this turn without spending energy.
  strategic_note: Committed poison plan: apply poison rapidly with Bouncing Flask and Deadly Poison, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails. Prioritize draw to cycle past status floods and skip generic attacks.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 352->370 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 370->385 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 385->385 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 60->60 | Gold 385->385 | Deck 29->30
  deck_change: picked Escape Plan+
  reasoning: Escape Plan+ provides free draw, which triggers Corrosive Wave for 0 energy while helping us cycle deeper into our deck to find our poison core and setup pieces.
  strategic_note: Committed poison plan: apply poison rapidly with Bouncing Flask and Deadly Poison, scale with Bubble Bubble, and defend using Fasten-buffed Defends and Piercing Wails. Prioritize draw to cycle past status floods and trigger Corrosive Wave.

F35 [map] choose_map_node (option_index=3) | source=llm
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route towards the Unknown node. With 385 gold and solid HP, I want to navigate towards the upcoming shop and elites to finalize the deck's scaling. The Unknown nodes in Act 3 can provide powerful events or relics that complement the poison engine.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; seek more draw to accelerate setup and prioritize removals of basic strikes.

F36 [event] choose_event_option (option_index=0) | source=llm
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: Foul Potions can be thrown at the Merchant for 100 Gold each. Since there is a Shop coming up at F39, taking the 3 Foul Potions guarantees a massive 300 Gold payout. We will happily forego Delicate Frond generations for a few floors to secure this wealth.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; sell Foul Potions at the upcoming shop for massive gold, then prioritize strike removals and premium relics. Delicate Frond provides infinite potions to solve immediate problems.

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Foul Potion

F36 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=3) | source=llm
  HP 60->60 | Gold 385->385 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With 385 gold, I want to preserve resources for the upcoming shop at Floor 39 while avoiding unnecessary chip damage from early Act 3 hallway fights, as the deck's poison ramp-up can be slow. Winged Boots provide flexibility if this path becomes dangerous later.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Prioritize high-value card draw and removals at the next shop to accelerate power setup.

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 60->54 | Gold 385->429 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 54->54 | Gold 429->429 | Deck 30->30
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [map] choose_map_node (option_index=2) | source=llm
  HP 54->54 | Gold 429->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With 429 gold, I am heading toward the Shop on floor 39 to finalize the deck's scaling and removal needs before the upcoming Elites. The current poison engine is solid but needs more draw or high-quality defense to handle Act 3's high damage floor.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritize finding more draw and removing basic strikes to accelerate power setup.

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 429->445 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 16 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 445->460 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 460->460 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Mazaleth's Gift

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 460->460 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 42->42 | Gold 460->460 | Deck 30->31
  deck_change: picked Footwork+
  reasoning: Our deck is completely committed to Poison scaling for damage, but we need immense defensive scaling to survive the Act 3 Boss's scaling multi-attacks and permanent Vulnerability. A second upgraded Footwork gives +3 Dexterity, pushing our defensive output to levels where we can easily block the Torch Head Amalgam while our passive poison kills the Queen.
  strategic_note: Committed poison plan: survive with Piercing Wails and immense Dexterity from Footwork while passive Poison (Noxious Fumes, Bubble Bubble) scales. Keep cycling to find setup pieces early and stall.

F38 [map] choose_map_node (option_index=2) | source=llm
  HP 42->42 | Gold 460->460 | Deck 31->31
  deck_change: no deck change
  reasoning: With 460 gold, the shop is a high-priority node to convert wealth into immediate power (removals, scaling relics, or defensive powers) before the upcoming Elite fights. This aligns with the route recommendation and the strategy of using shops to stabilize and improve the deck's consistency for the endgame.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritising shops to remove Strikes and find more draw/burst potential.

F39 [shop] open_shop_inventory | source=heuristic
  HP 42->42 | Gold 460->560 | Deck 31->31
  deck_change: no deck change
  reasoning: Throw 1 Foul Potion at merchant for 100 gold, then open shop

F39 [shop] buy_relic (option_index=2) | source=plan
  HP 42->42 | Gold 560->387 | Deck 31->31
  deck_change: no deck change
  reasoning: Shop plan [1/4]: Orrery provides 5 card rewards, giving us multiple chances to find premium poison or defensive scaling cards.

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 42->42 | Gold 387->387 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 42->42 | Gold 387->387 | Deck 31->32
  deck_change: picked Backflip+
  reasoning: Backflip+ provides essential card draw and solid block, which scales perfectly with our two Footwork+ copies. Cycle is crucial to assemble our Noxious Fumes and defensive scaling before the Queen inflicts her debilitating permanent debuffs.
  strategic_note: Committed poison plan: survive with massive block from Footwork+ and Piercing Wails while Noxious Fumes and Bubble Bubble kill the boss. Cycle aggressively to find powers early. Skip raw attacks.

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 42->42 | Gold 387->387 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 42->42 | Gold 387->387 | Deck 32->33
  deck_change: picked Well-Laid Plans+
  reasoning: Well-Laid Plans+ is exceptional for our committed poison deck. It allows us to hold critical defensive cards like Piercing Wail for the Amalgam's multi-attack turns (R3, R6, R9) and align poison combo pieces like Bubble Bubble.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks.

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 42->42 | Gold 387->387 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 42->42 | Gold 387->387 | Deck 33->34
  deck_change: picked Calculated Gamble+
  reasoning: Calculated Gamble+ is incredible for large decks (33 cards), offering free hand-cycling to dig for our critical scaling cards like Footwork and Noxious Fumes. The upgrade adds Retain, allowing us to hold it for a turn where we draw a hand full of basics.
  strategic_note: Committed poison plan: survive with high block/dexterity while Noxious Fumes and Bubble Bubble scale to kill. Prioritize card removal (Strikes) and avoid adding more attacks.

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 42->42 | Gold 387->387 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 42->42 | Gold 387->387 | Deck 34->34
  deck_change: no deck change
  reasoning: We are fully committed to a poison and defense/cycle engine. None of these cards advance our game plan, and with a 34-card deck, keeping it lean to find our key powers (Footwork, Noxious Fumes) and cycle cards faster is the best choice.
  strategic_note: Committed poison plan: stack poison with Fumes, Flask, and Corrosive Wave while blocking heavily with Footwork, Backflip, and Piercing Wail. Prioritize draw and cycle to find key setup pieces quickly, and avoid adding unrelated attacks or bloat.

F39 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 42->42 | Gold 387->387 | Deck 34->34
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F39 [shop] buy_card (option_index=6) | source=plan
  HP 42->42 | Gold 387->208 | Deck 34->35
  deck_change: bought Master of Strategy
  reasoning: Shop plan [2/4]: Free draw 3 is exceptionally strong for finding our poison and footwork engine pieces quickly.

F39 [shop] remove_card_at_shop | source=plan
  HP 42->42 | Gold 208->208 | Deck 35->35
  deck_change: no deck change
  reasoning: Shop plan [3/4]: Removing a Strike increases the consistency of drawing our mitigation and poison scaling.

F39 [card_select] select_deck_card (option_index=0) | source=llm
  HP 42->42 | Gold 208->108 | Deck 35->34
  deck_change: lost Strike
  reasoning: Strike is the weakest remaining card in the deck. We are heavily committed to Poison scaling and have Footwork and Fasten, which make Defends highly valuable, whereas Strikes do almost nothing for our win condition.
  strategic_note: Committed poison plan: setup Noxious Fumes, Footwork, and Fasten, then cycle with Acrobatics and Backflip to apply more poison and block. Keep removing Strikes.

F39 [shop] buy_card (option_index=5) | source=plan
  HP 42->42 | Gold 108->19 | Deck 34->35
  deck_change: bought Automation
  reasoning: Shop plan [4/4]: With our heavy card draw engine (Acrobatics, Expertise, Predator), Automation will trigger frequently to offset energy bottlenecks.

F39 [shop] close_shop_inventory | source=plan
  HP 42->42 | Gold 19->19 | Deck 35->35
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F39 [shop] proceed | source=auto
  HP 42->42 | Gold 19->19 | Deck 35->35
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F39 [map] choose_map_node (option_index=2) | source=llm
  HP 42->42 | Gold 19->0 | Deck 35->35
  deck_change: no deck change
  reasoning: The route recommends the Elite at (c4,r6). Despite being at 64% HP, I have Pantograph for the boss heal and Winged Boots for pathing flexibility if this fight goes poorly. An Elite reward is necessary to scale my poison deck's power for the Act 3 boss.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Needs more draw to setup powers faster and removals for basic strikes; take Elites now to find high-impact relics or rare cards.

F40 [card_select] select_deck_card (option_index=1) | source=llm
  HP 42->42 | Gold 19->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Mirage is an incredible block card in our poison deck. Even if the current poison stacks aren't huge yet, it scales directly with our main win condition. The other options are shiv-focused, which we have zero synergy for.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Footwork, and defensive skills to outlast enemies while passive poison scales. Focus on draw, block, and poison application; avoid unrelated attacks or narrow synergies.

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 5->5 | Gold 19->54 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 35 Gold

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 5->5 | Gold 54->69 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 5->5 | Gold 69->69 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim potion: Ghost in a Jar

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 5->5 | Gold 69->69 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim relic: Venerable Tea Set

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 5->5 | Gold 69->69 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F40 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 5->5 | Gold 69->69 | Deck 35->35
  deck_change: no deck change
  reasoning: Our deck is firmly committed to an AoE poison strategy with Noxious Fumes, Haze, and Corrosive Wave. The upcoming boss has a minion (Amalgam), which makes the random targeting of Bouncing Flask+ very unreliable and weak for focusing the Queen. With only 3 base energy, skipping keeps our deck lean and ensures we draw our key AoE poison and block cards more consistently.
  strategic_note: Committed poison plan: rely on AoE poison (Fumes, Haze, Corrosive Wave) and Bubble Bubble to bypass the Queen's 20 block per turn. Prioritize surviving with Footwork and cheap block while passive poison scales. Avoid adding expensive or single-target cards since energy is limited to 3.

F40 [map] choose_map_node (option_index=1) | source=llm
  HP 5->5 | Gold 69->69 | Deck 35->35
  deck_change: no deck change
  reasoning: I am at critical HP (5/66) and must reach the upcoming Rest Site to survive. Taking the Treasure node at column 4, row 7 keeps me on the path toward the next Rest Site without encountering any mandatory combats beforehand.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail; prioritize survival and finding a source of Burst or more Catalyst to accelerate scaling.

F41 [treasure] open_chest | source=random
  HP 5->5 | Gold 69->116 | Deck 35->35
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 5->5 | Gold 116->116 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim: Regal Pillow

F41 [treasure] proceed | source=random
  HP 5->5 | Gold 116->116 | Deck 35->35
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=3) | source=llm
  HP 5->5 | Gold 116->116 | Deck 35->35
  deck_change: no deck change
  reasoning: I am at 5/66 HP, which is critical. I must take the immediate Rest Site to heal (Rest) before attempting any more combats. The Winged Boots allow me to jump to index 3 (RestSite) even if it weren't normally connected, though the current route suggests it as the standard path regardless. Survival is the absolute priority.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending with Footwork and Piercing Wail. Current priority is survival via Rest Sites; once stabilized, seek draw to set up powers faster and more removals for basic Strikes.

F42 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 5->39 | Gold 116->116 | Deck 35->35
  deck_change: no deck change
  reasoning: At 5 HP facing an Act 3 Elite, a bad opening draw means instant death. Resting heals 34 HP thanks to Regal Pillow, providing the necessary buffer to survive until our block engine and powers are fully online.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Draw through the deck using Acrobatics and Calculated Gamble to accelerate poison and Automation energy.

F42 [rest_site] proceed | source=auto
  HP 39->39 | Gold 116->116 | Deck 35->35
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=1) | source=llm
  HP 39->39 | Gold 116->0 | Deck 35->35
  deck_change: no deck change
  reasoning: This elite node is the next step in the planned route and essential for securing a relic to scale for the Act 3 boss. With Pantograph providing a 25 HP heal before the boss, I can afford to take more damage now to build power. The Winged Boots are available if I need to skip subsequent nodes later.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending. Use the Delicate Frond's infinite potion generation to mitigate damage and overcome Elites. Prioritize block and poison scaling over raw attacks, using the Pantograph heal to offset health loss from aggressive routing.

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 116->158 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 42 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 158->173 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim relic: Strike Dummy

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 39->39 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: Our deck is already at 35 cards with a solid poison engine, ample draw, and one copy of Well-Laid Plans+. A second WLP+ is unnecessary overkill, Snakebite is too energy-heavy at 2 cost on 3 base energy, and Expertise risks being a dead draw since our hand will often be full from retain and our existing cycle package. Skipping keeps the deck lean.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F43 [map] choose_map_node (option_index=2) | source=llm
  HP 39->39 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: With 39/66 HP and an Elite fight potentially looming in the future, following the route to a Rest Site is the safest path to ensure I have the health or upgrades needed for the Act 3 boss. Pantograph provides a 25 HP cushion for the boss, but I still need to survive the intervening floors.
  strategic_note: Committed poison plan: use Noxious Fumes and Bouncing Flask for scaling while prioritizing defense and Delicate Frond potion generation. Removing remaining Strikes and finding more efficient block or card draw are the current priorities to ensure consistency against high-damage Act 3 enemies.

F44 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 39->66 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: With 39 HP going into an Elite fight in Act 3, resting is the safer play, especially since Regal Pillow makes the rest highly efficient (healing 34 HP to full). We have another rest site before the boss to Smith if needed, and surviving this immediate threat is priority.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes, Bouncing Flask, and Bubble Bubble while defending with Fasten, Footwork, and Piercing Wail. Draw through the deck using Acrobatics and Calculated Gamble to accelerate poison and Automation energy.

F44 [rest_site] proceed | source=auto
  HP 66->66 | Gold 173->173 | Deck 35->35
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=2) | source=llm
  HP 66->66 | Gold 173->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Following the recommended route to a hallway fight. The deck is in a strong position with full HP and a functional poison engine, but could benefit from more card rewards to find additional scaling or high-quality defensive tools before the final boss. I have Winged Boots if I need to bypass a dangerous node later.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending. Delicate Frond provides infinite potions to solve immediate problems; prioritize strike removals and premium relics in future shops.

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 173->187 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 187->202 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 202->202 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 202->202 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 66->66 | Gold 202->202 | Deck 35->36
  deck_change: picked Calculated Gamble+
  reasoning: Calculated Gamble+ is an incredible enabler for our deck. It triggers Corrosive Wave for massive AoE poison, cycles through our large deck to find Footwork and Noxious Fumes, helps trigger Automation for energy, and can discard Haze for free poison. The built-in Retain lets us hold it for the perfect combo turn.
  strategic_note: Committed poison plan: survive with high block/dexterity while cycling rapidly to stack poison. Use Corrosive Wave combined with Calculated Gamble+ and Acrobatics for massive AoE poison application. Bubble Bubble acts as a strong multiplier. Avoid adding attacks; prioritize cheap block, energy generation, and cycle to keep the engine moving.

F45 [map] choose_map_node (option_index=0) | source=llm
  HP 66->66 | Gold 202->0 | Deck 36->36
  deck_change: no deck change
  reasoning: With 100% HP and a committed poison engine featuring Noxious Fumes and Bouncing Flask, I am strong enough to take on an Act 3 Elite for a relic and card reward. Pantograph provides a 25 HP safety net for the boss, making the potential HP loss in this elite fight acceptable. I have Winged Boots if I need to bypass future dangerous nodes to reach the rest site.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; use Delicate Frond for tactical potion generation and prioritize defensive upgrades to let poison tick. Scaling is solid, seeking premium relics from elites to secure the final boss kill.

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 202->237 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim gold: 35 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 237->252 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 252->252 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim relic: Snecko Skull

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 252->252 | Deck 36->36
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 58->58 | Gold 252->252 | Deck 36->37
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is exceptional mitigation against the upcoming Act 3 Boss (Amalgam's scaling multi-hits) and we have a large enough deck (36 cards) to support a third copy, especially since it exhausts and we have Well-Laid Plans to hold it.
  strategic_note: Committed poison plan: apply poison with Fumes and Flask, stack it rapidly with Bubble Bubble and Snecko Skull. Survive with Footwork, extensive cycle, and Piercing Wail to negate multi-hit threats. Hold Wails for dangerous multi-hit turns.

F46 [map] choose_map_node (option_index=0) | source=llm
  HP 58->58 | Gold 252->252 | Deck 37->37
  deck_change: no deck change
  reasoning: Standard pathing to the boss. I have 58/66 HP and Pantograph will heal me for 25 at the start of the boss fight, putting me effectively at full health. I will use this rest site to upgrade a key card to maximize my damage or mitigation for the final encounter.
  strategic_note: Committed poison plan: stack poison with Noxious Fumes and Bouncing Flask while defending; use Delicate Frond's infinite potions to bridge defensive gaps and accelerate kills. Priority is removing strikes and upgrading core poison/block pieces before the boss.

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=22, note_scope=run, note_triggers=all) | source=llm
  HP 58->58 | Gold 252->252 | Deck 37->37
  deck_change: upgraded Corrosive Wave->Corrosive Wave+
  reasoning: We are at 58/66 HP and have Pantograph, which will heal us for 25 at the start of the boss fight, easily capping our HP. Resting would be completely wasted. Corrosive Wave is our best remaining upgrade, as the extra 1 poison per drawn card translates to massive scaling with our Acrobatics, Master of Strategy, and Calculated Gambles.
  strategic_note: Committed poison/draw plan: stack poison with Noxious Fumes, Bubble Bubble, and Corrosive Wave while drawing heavily. Use Calculated Gamble and Acrobatics to trigger Corrosive Wave and Automation. Play defensively with Fasten and Piercing Wail while poison scales.

F47 [rest_site] proceed | source=auto
  HP 58->58 | Gold 252->252 | Deck 37->37
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 58->66 | Gold 252->0 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 51->51 | Gold 252->252 | Deck 37->37
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 51->0 | Gold 252->252 | Deck 37->37
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (8 replays)
[Selected: elite] Phrog Parasite (F12, elite)
## Combat Replay: vs Phrog Parasite (Floor 12, elite)
Relics: Ring of the Snake, Winged Boots, Pantograph
Deck (19): Defend x5, Strike x5, Acrobatics, Bubble Bubble, Dagger Spray, Deadly Poison, Neutralize, Noxious Fumes+, Piercing Wail, Predator+, Survivor
Enemies: Phrog Parasite HP=61/61

### Round 1
Agent plan (hypothesis): Next turn is the 4x4 multi-attack. Will need to block or use Piercing Wail/Dagger Spray. Keep an eye on AoE for when the Wrigglers spawn.
Intent: Phrog Parasite: StatusCard(3)
  Deadly Poison -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: +Poison(5)
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  Neutralize -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -3, +Weak(1)
  turn_end

### Round 2
Intent: Phrog Parasite: Attack(4x4=16)
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Phrog Parasite: +Strength(-6), +Piercing Wail(6)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Bubble Bubble -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: Poison(4→13)
  turn_end

### Round 3
Agent plan (hypothesis): If it dies to poison, Wrigglers spawn instantly and we'll have a clean Turn 4 with full energy to hit them.
Agent plan (hypothesis): Phrog Parasite dies at the start of next turn to Noxious Fumes. Have AoE ready for the Wrigglers.
Intent: Phrog Parasite: StatusCard(3)
  Acrobatics
    energy -1
  Infection
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  turn_end

### Round 4
Intent: Phrog Parasite: Attack(4x4=16)
  turn_end

### Round 5
Intent: Wriggler: Stun, Wriggler: Stun, Wriggler: Stun, Wriggler: Stun
  Predator+ -> Wriggler[1]
    energy -2 | +Draw Cards Next Turn(2)
  Dagger Spray
    energy -1 | enemy_deltas: Wriggler: hp -8
  turn_end

### Round 6
Intent: Wriggler: Attack(6), Wriggler: Attack(6), Wriggler: Buff, StatusCard(1)
  Acrobatics
    energy -1
  Infection
  Dagger Spray
    energy -1 | -Noxious Fumes | enemy_deltas: Wriggler: DIED
## Combat Analytics: Phrog Parasite (WIN - 6 rounds)

Cards played (with descriptions):
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Strike "Deal 6 damage." -> 4 plays, 24 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 1 plays, +9 poison
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 2 plays, 8 dmg

Poison stacks applied per card:
  Bubble Bubble: 9 stacks
  Deadly Poison: 5 stacks

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:4 -> R5:- -> R6:-
  Poison: R1:- -> R2:4 -> R3:15 -> R4:17 -> R5:- -> R6:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:5
  Poison[3]: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Phrog Parasite (Floor 13, elite)
Relics: Ring of the Snake, Precarious Shears, Festive Popper
Deck (14): Defend x4, Strike x2, Accuracy, Blade of Ink+, Cloak and Dagger+, Guilty, Infinite Blades, Neutralize, Pinpoint, Survivor
Enemies: Phrog Parasite HP=53/62

### Round 1
Intent: Phrog Parasite: StatusCard(3)
  Power Potion
  Envenom
  Envenom
    +Envenom(1)
  Accuracy
    energy -1 | +Accuracy(4)
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6, +Poison(1)
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6, Poison(1→2)
  turn_end

### Round 2
Intent: Phrog Parasite: Attack(4x4=16)
  Flex Potion
    +Strength(5) | +Flex Potion(5)
  Blade of Ink+
    energy -1
  Neutralize -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -8, Poison(1→2), +Weak(1)
  Shiv -> Phrog Parasite[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Phrog Parasite: hp -15, Poison(2→3), Weak(1→2)
  Shiv -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -15, Poison(3→4), Weak(2→3)
  Shiv -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: DIED
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Survivor
    energy -1 | block +8
  turn_end
    -Flex Potion

### Round 3
Intent: Wriggler: Attack(6), Wriggler: Buff, StatusCard(1), Wriggler: Attack(6), Wriggler: Buff, StatusCard(1)
  Cloak and Dagger+
    energy -1 | block +6
  Neutralize -> Wriggler[0]
  Shiv -> Wriggler[0]
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Wriggler[0]
  Shiv -> Wriggler[1]
  Survivor
    energy -1 | block +8
  Guilty
  turn_end

### Round 4
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1), Wriggler: Attack(8)
  Potion of Binding
    enemy_deltas: Wriggler: +Weak(1), +Vulnerable(1)
  Shiv -> Wriggler[0]
  Strike -> Wriggler[0]
    energy -1
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Wriggler: Attack(8), Wriggler: Buff, StatusCard(1)
  Blade of Ink+
    energy -1
  Shiv -> Wriggler[0]
  Shiv -> Wriggler[0]
  Shiv -> Wriggler[0]
    enemy_deltas: Wriggler: hp -10, +Poison(1), +Weak(1)
  Shiv -> Wriggler[0]
    -Envenom | -Accuracy | -Infinite Blades | enemy_deltas: Wriggler: DIED
## Combat Analytics: Phrog Parasite (WIN - 5 rounds)

Cards played (with descriptions):
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Strike "Deal 6 damage." -> 3 plays, 12 dmg, +2 poison
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 2 plays
  Neutralize "Deal 8 damage. Apply 1 Weak." -> 2 plays, 8 dmg, +1 poison
  Shiv "Deal 15 damage. Apply 1 Weak. Exhaust." -> 11 plays, 40 dmg, +3 poison, EXHAUST
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 1 plays, 6 block, generates 2 Shivs
  Defend "Gain 5 Block." -> 2 plays, 10 block

Token attribution (Shivs):
  other: 8 Shivs -> ~29 dmg
  Cloak and Dagger+: 2 Shivs -> ~7 dmg
  Infinite Blades: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Shiv: 3 stacks
  Strike: 2 stacks
  Neutralize: 1 stacks
Total poison/power tick damage: 1
  Per round: R2:1

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:- -> R4:- -> R5:-
  Poison: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:-

[Selected: boss] multi:Kin Follower+Kin Follower+Kin Priest (F17, boss)
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker
Deck (22): Defend x5, Strike x5, Piercing Wail x2, Acrobatics, Bubble Bubble, Dagger Spray, Deadly Poison, Expertise, Haze, Neutralize+, Noxious Fumes+, Predator+, Survivor
Enemies: Kin Follower HP=58/58, Kin Follower HP=59/59, Kin Priest HP=190/190

### Round 1
Agent plan (hypothesis): Hold Touch of Insanity for Haze or Predator when needed.
Intent: Kin Follower: Buff, Kin Follower: Attack(5), Kin Priest: Attack(8), Debuff
  Dexterity Potion
    +Dexterity(2)
  Survivor
    energy -1 | block +10
  Strike
  Expertise
    energy -1
  Defend
    energy -1 | block +7
  turn_end

### Round 2
Agent plan (hypothesis): Saved Touch of Insanity for a high-cost card like Haze or Predator. Priest will be weakened for its multi-attack next turn.
Intent: Kin Follower: Attack(7), Kin Follower: Attack(2x2=4), Kin Priest: Attack(8), Debuff
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Kin Follower: +Strength(-6), +Piercing Wail(6); Kin Priest: +Strength(-6), +Piercing Wail(6)
  Neutralize+ -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -4, +Weak(2)
  Defend
    energy -1 | block +5
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -6
  turn_end

### Round 3
Intent: Kin Follower: Attack(4x2=8), Kin Follower: Buff, Kin Priest: Attack(2x3=6)
  Fire Potion -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -20
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Predator+ -> Kin Priest[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Kin Priest: hp -15
  turn_end

### Round 4
Agent plan (hypothesis): Hold Touch of Insanity for a high impact card like Predator or Haze. Priest is buffing this turn, expect heavy damage next.
Intent: Kin Follower: Buff, Kin Follower: Attack(7), Kin Priest: Buff
  Neutralize+ -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -4, +Weak(2)
  Acrobatics
    energy -1
  Strike
  Deadly Poison -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: Poison(3→8)
  Defend
    energy -1 | block +7
  turn_end

### Round 5
Intent: Kin Follower: Attack(9), Kin Follower: Attack(4x2=8), Kin Priest: Attack(7), Debuff
  Touch of Insanity
  Haze
  Haze
    enemy_deltas: Kin Follower: Poison(5→9); Kin Priest: Poison(10→14)
  Expertise
    energy -1
  Bubble Bubble+ -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: Poison(14→26)
  Defend
    energy -1 | block +7
  turn_end

### Round 6
Agent plan (hypothesis): Survived! Keep stacking poison on the Priest, hopefully it dies soon.
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(10), Debuff
  Neutralize+ -> Kin Follower[0]
  Defend
    energy -1 | block +5
  Deadly Poison -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: Poison(28→33)
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -6
  turn_end

### Round 7
Intent: Kin Follower: Buff, Kin Follower: Attack(9), Kin Priest: Attack(5x3=15)
  Piercing Wail
    energy -1 | enemy_deltas: Kin Follower: Strength(4→-2), +Piercing Wail(6); Kin Priest: Strength(2→-4), +Piercing Wail(6)
  Defend
    energy -1 | block +7
  Survivor
    energy -1 | block +10
  Predator+
  turn_end

### Round 8
Intent: Kin Follower: Attack(11), Kin Follower: Attack(6x2=12), Kin Priest: Buff
  Expertise
    energy -1
  Acrobatics
    energy -1
  Haze
  Dagger Spray
    energy -1 | enemy_deltas: Kin Follower: hp -8; Kin Priest: hp -8
  turn_end
## Combat Analytics: multi:Kin Follower+Kin Follower+Kin Priest (WIN - 8 rounds)

Cards played (with descriptions):
  Survivor "Gain 10 Block. Discard 1 card." -> 2 plays, 20 block
  Expertise "Draw cards until you have 6 in your Hand." -> 3 plays
  Defend "Gain 7 Block." -> 6 plays, 38 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Predator+ "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Haze "Sly. Apply 4 Poison to ALL enemies." -> 1 plays, +8 poison
  Bubble Bubble+ "If the enemy has Poison, apply 12 Poison." -> 1 plays, +12 poison
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 16 dmg

Poison stacks applied per card:
  Bubble Bubble+: 12 stacks
  Deadly Poison: 10 stacks
  Haze: 8 stacks

Enemy power timeline:
  Minion[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1
  Minion[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:3 -> R5:5 -> R6:11 -> R7:13 -> R8:15
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:3 -> R5:5 -> R6:11 -> R7:13 -> R8:15
  Poison[2]: R1:- -> R2:- -> R3:- -> R4:3 -> R5:10 -> R6:28 -> R7:35 -> R8:37
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:4 -> R7:4 -> R8:6
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:4 -> R8:4
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:1 -> R6:- -> R7:1 -> R8:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Precarious Shears, Festive Popper, Pen Nib, Pocketwatch
Deck (16): Defend x4, Strike x2, Accuracy, Blade of Ink+, Cloak and Dagger+, Guilty, Hidden Daggers, Infinite Blades, Neutralize, Piercing Wail, Pinpoint, Survivor
Enemies: Kin Follower HP=49/58, Kin Follower HP=50/59, Kin Priest HP=181/190

### Round 1
Intent: Kin Follower: Buff, Kin Follower: Attack(5), Kin Priest: Attack(8), Debuff
  Accuracy
    energy -1 | +Accuracy(4)
  Blade of Ink+
    energy -1
  Shiv -> Kin Follower[1]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Kin Follower: hp -10, +Weak(1)
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -10, +Weak(1)
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -10, Weak(1→2)
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 2
Intent: Kin Follower: Attack(7), Kin Follower: Attack(2x2=4), Kin Priest: Attack(6), Debuff
  Piercing Wail
    energy -1 | exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Kin Follower: +Strength(-6), +Piercing Wail(6); Kin Priest: +Strength(-6), +Piercing Wail(6)
  Cloak and Dagger+
    energy -1 | block +4
  Defend
    energy -1 | block +3
  Shiv -> Kin Priest[2]
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Hidden Daggers
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  turn_end

### Round 3
Intent: Kin Follower: Attack(4x2=8), Kin Follower: Buff, Kin Priest: Attack(3x3=9)
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -9
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Neutralize -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -2, +Weak(1)
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Kin Follower: Buff, Kin Follower: Attack(7), Kin Priest: Buff
  Blade of Ink+
    energy -1
  Survivor
    energy -1 | block +8
  Strike
  Pinpoint -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -15
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -10, +Weak(1)
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -10, Weak(1→2)
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -10, Weak(2→3)
  turn_end

### Round 5
Intent: Kin Follower: Attack(9), Kin Follower: Attack(4x2=8), Kin Priest: Attack(7), Debuff
  Cloak and Dagger+
    energy -1 | block +6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Hidden Daggers
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -16
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  turn_end

### Round 6
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(7), Debuff
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -8
  Pinpoint -> Kin Priest[2]
    energy -3 | -Accuracy | -Infinite Blades | -Frail | enemy_deltas: Kin Follower: DIED; Kin Priest: DIED
## Combat Analytics: multi:Kin Follower+Kin Follower+Kin Priest (WIN - 6 rounds)

Cards played (with descriptions):
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 2 plays
  Shiv "Deal 10 damage. Apply 1 Weak. Exhaust." -> 17 plays, 156 dmg, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Cloak and Dagger+ "Gain 4 Block. Add 2 Shivs into your Hand." -> 2 plays, 10 block, generates 2 Shivs
  Defend "Gain 3 Block." -> 4 plays, 18 block
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 2 plays, generates 2 Shivs
  Strike "Deal 9 damage." -> 1 plays, 9 dmg
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Neutralize "Deal 2 damage. Apply 1 Weak." -> 1 plays, 2 dmg
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 2 plays, 15 dmg

Token attribution (Shivs):
  other: 9 Shivs -> ~83 dmg
  Cloak and Dagger+: 4 Shivs -> ~37 dmg
  Hidden Daggers: 4 Shivs -> ~37 dmg

Enemy power timeline:
  Minion[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Minion[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:2 -> R6:1

[Selected: elite] Infested Prism (F30, elite)
Historical: loss=2 vs historical avg=3.0+/-2.2 (z=-0.5, TYPICAL, n=3)
## Combat Replay: vs Infested Prism (Floor 30, elite)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum
Deck (28): Defend x5, Strike x3, Piercing Wail x2, Acrobatics, Acrobatics+, Assassinate, Backflip, Bouncing Flask, Bubble Bubble, Dagger Spray, Deadly Poison, Expertise, Fasten, Footwork, Haze, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor
Enemies: Infested Prism HP=200/200

### Round 1
Agent plan (hypothesis): Hold potions until Turn 3's dangerous multi-attack unless necessary. Use one before the fight ends to open a slot for the Elite drop.
Intent: Infested Prism: Attack(22)
  Assassinate -> Infested Prism[0]
    energy +1 | exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Infested Prism: hp -10, +Vulnerable(1)
  Fasten
    energy -1 | +Fasten(5)
  Survivor
    energy -1 | block +8
  Haze
  Defend
    energy -1 | block +10 | enemy_deltas: Infested Prism: +Poison(4)
  Defend
    energy -1 | block +10
  turn_end

### Round 2
Agent plan (hypothesis): Turn 3 is multi-attack. You will draw 9 cards. Use Piercing Wail or maximum block/weak.
Intent: Infested Prism: Attack(16), Defend
  Neutralize+ -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4, +Weak(2)
  Predator+ -> Infested Prism[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Infested Prism: hp -20
  Bubble Bubble+ -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: Poison(3→15)
  Defend
    energy -1 | block +10
  turn_end

### Round 3
Intent: Infested Prism: Attack(6x3=18)
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Infested Prism: +Strength(-6), +Piercing Wail(6)
  Piercing Wail
    energy -1 | enemy_deltas: Infested Prism: Strength(-6→-12), Piercing Wail(6→12)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Skewer -> Infested Prism[0]
  turn_end

### Round 4
Agent plan (hypothesis): Enemy attacks for 17 or 26 next turn. Prioritize block and weakness.
Intent: Infested Prism: Buff, Defend
  Poison Potion -> Infested Prism[0]
    enemy_deltas: Infested Prism: Poison(16→22)
  Footwork
    energy -1 | +Dexterity(2)
  Noxious Fumes
    energy -1 | Noxious Fumes(3→5)
  Deadly Poison -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: Poison(22→27)
  turn_end

### Round 5
Intent: Infested Prism: Attack(26)
  Neutralize+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -4, +Weak(2)
  Predator+ -> Infested Prism[0]
    energy -1 | +Draw Cards Next Turn(2) | enemy_deltas: Infested Prism: hp -4, block -16
  Defend
    energy -1 | block +12
  Defend
    energy -1 | block +12
  turn_end

### Round 6
Agent plan (hypothesis): Next turn, deal the remaining ~13 damage to get enemy HP below poison threshold, ensuring it dies at the start of its turn before attacking.
Agent plan (hypothesis): Fight should end before enemy acts.
Intent: Infested Prism: Attack(15), Defend
  Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6
  Backflip
    energy -1 | block +7
  Dagger Spray
    energy -1 | enemy_deltas: Infested Prism: hp -8
  Bubble Bubble+ -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: Poison(35→47)
  Explosive Ampoule
    enemy_deltas: Infested Prism: hp -10
  Skewer -> Infested Prism[0]
  turn_end
## Combat Analytics: Infested Prism (WIN - 6 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 10 dmg, EXHAUST
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Defend "Gain 10 Block." -> 5 plays, 54 block, +4 poison
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 24 dmg
  Bubble Bubble+ "If the enemy has Poison, apply 12 Poison." -> 2 plays, +24 poison
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Skewer "Deal 8 damage X times." -> 2 plays
  Footwork "Gain 2 Dexterity." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Strike "Deal 6 damage." -> 1 plays, 6 dmg
  Backflip "Gain 7 Block. Draw 2 cards." -> 1 plays, 7 block
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg

Poison stacks applied per card:
  Bubble Bubble+: 24 stacks
  Poison Potion: 6 stacks
  Deadly Poison: 5 stacks
  Defend: 4 stacks

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:14 -> R4:16 -> R5:31 -> R6:35
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:4
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1
Comparator (recent same-enemy comparator):
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

[Selected: boss] The Insatiable (F33, boss)
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine
Deck (28): Defend x5, Strike x3, Piercing Wail x2, Acrobatics, Acrobatics+, Assassinate, Backflip, Bouncing Flask, Bubble Bubble, Dagger Spray, Deadly Poison, Expertise, Fasten, Footwork+, Haze, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor
Enemies: The Insatiable HP=321/321

### Round 1
Agent plan (hypothesis): Prioritize getting Noxious Fumes and Footwork into play.
Agent plan (hypothesis): If we draw a 1-cost power, play it. Otherwise, spend the last energy on poison or whatever is best.
Agent plan (hypothesis): Boss adds 6 statuses, draw past them.
Intent: The Insatiable: Buff, StatusCard(6)
  Assassinate -> The Insatiable[0]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: The Insatiable: hp -15, Vulnerable(1→2)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -6, +Weak(2)
  Acrobatics
    energy -1
  Haze
  Backflip
    energy -1 | block +5
  Deadly Poison -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(4→9)
  turn_end

### Round 2
Agent plan (hypothesis): Sandpit will drop to 3 next turn. Expect a 21-damage attack next turn, but with Fasten active, Defends will block for 10 each.
Intent: The Insatiable: Attack(6x2=12)
  Fasten
    energy -1 | +Fasten(5)
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: The Insatiable: +Strength(-6), +Piercing Wail(6)
  Bubble Bubble -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(8→17)
  turn_end

### Round 3
Agent plan (hypothesis): Play Frantic Escapes next turn while the boss buffs.
Intent: The Insatiable: Attack(28)
  Weak Potion -> The Insatiable[0]
    enemy_deltas: The Insatiable: +Weak(3)
  Footwork+
    energy -1 | +Dexterity(3)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +13
  turn_end

### Round 4
Agent plan (hypothesis): Sandpit will be pushed to 4 before decreasing to 3.
Intent: The Insatiable: Buff
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4, Weak(2→4)
  Acrobatics+
    energy -1
  Predator+
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  turn_end

### Round 5
Agent plan (hypothesis): Prioritize finding and playing Frantic Escape cards while stacking Poison. We need this boss dead ASAP before Sandpit hits 0.
Intent: The Insatiable: Attack(7x2=14)
  Bouncing Flask
    energy -2 | enemy_deltas: The Insatiable: Poison(20→29)
  Bubble Bubble -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(29→38)
  turn_end

### Round 6
Agent plan (hypothesis): Sandpit will be at 4, dropping to 3 next turn. Poison is ticking heavily.
Intent: The Insatiable: Attack(7x2=14)
  Defend
    energy -1 | block +13
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  turn_end

### Round 7
Agent plan (hypothesis): If we draw Neutralize+, prioritize it. Play Frantic Escape if energy permits, but survival is more important right now.
Agent plan (hypothesis): Continue defending while poison ticks. Sandpit is at 3, so we have some breathing room.
Intent: The Insatiable: Attack(22)
  Acrobatics
    energy -1
  Strike
  Defend
    energy -1 | block +13
  Defend
    energy -1 | block +13
  turn_end

### Round 8
Agent plan (hypothesis): Continue stalling and playing Frantic Escapes as needed; Poison will kill in 2-3 turns.
Intent: The Insatiable: Buff
  Frantic Escape
    energy -2 | enemy_deltas: The Insatiable: Sandpit(2→3)
  Deadly Poison -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(44→49)
  turn_end

### Round 9
Agent plan (hypothesis): Boss defeated.
Intent: The Insatiable: Attack(12x2=24)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4, +Weak(2)
  Acrobatics+
    energy -1
  Haze
  Bubble Bubble -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: Poison(55→64)
  turn_end
## Combat Analytics: The Insatiable (WIN - 9 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 15 dmg, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 14 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 3 plays, +27 poison
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Defend "Gain 13 Block." -> 4 plays, 52 block
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 5 plays
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, +9 poison

Poison stacks applied per card:
  Bubble Bubble: 27 stacks
  Deadly Poison: 10 stacks
  Bouncing Flask: 9 stacks

Enemy power timeline:
  Poison: R1:- -> R2:8 -> R3:16 -> R4:18 -> R5:20 -> R6:40 -> R7:42 -> R8:44 -> R9:51
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:3 -> R6:2 -> R7:3 -> R8:2 -> R9:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4
  Vulnerable: R1:1 -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:2 -> R5:3 -> R6:2 -> R7:1 -> R8:- -> R9:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Drake, Precarious Shears, Festive Popper, Pen Nib, Pocketwatch, Touch of Orobas, War Paint, Strawberry
Deck (28): Defend x4, Footwork+ x2, Accuracy+, Backflip, Blade Dance, Blade Dance+, Blade of Ink+, Calculated Gamble, Cloak and Dagger+, Conflagration, Dodge and Roll+, Hidden Daggers, Infinite Blades, Knife Trap, Leading Strike, Neutralize+, Piercing Wail+, Pinpoint, Predator, Rage+, Scrawl, Strangle+, Strike, Survivor
Enemies: The Insatiable HP=312/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Power Potion
  Envenom
  Strangle+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -10, +Strangle(3)
  Envenom
    +Envenom(1) | enemy_deltas: The Insatiable: hp -3
  Infinite Blades
    energy -1 | +Infinite Blades(1) | enemy_deltas: The Insatiable: hp -3
  Blade of Ink+
    energy -1 | enemy_deltas: The Insatiable: hp -3
  Shiv -> The Insatiable[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: The Insatiable: hp -9, +Poison(1), +Weak(1)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -9, Poison(1→2), Weak(1→2)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -9, Poison(2→3), Weak(2→3)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -7, Poison(3→4), Weak(3→5)
  turn_end

### Round 2
Intent: The Insatiable: Attack(6x2=12)
  Accuracy+
    energy -1 | +Accuracy(6)
  Footwork+
    energy -1 | +Dexterity(3)
  Blade Dance
    energy -1 | exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> The Insatiable[0]
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: The Insatiable: hp -10, Poison(3→4)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(4→5)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(5→6)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(6→7)
  turn_end

### Round 3
Intent: The Insatiable: Attack(21)
  Rage+
    +Rage(5)
  Shiv -> The Insatiable[0]
    block +5 | enemy_deltas: The Insatiable: hp -20, Poison(6→7)
  Strike -> The Insatiable[0]
    energy -1 | block +5 | enemy_deltas: The Insatiable: hp -6, Poison(7→8)
  Conflagration
    energy -1 | block +5 | enemy_deltas: The Insatiable: hp -12, Poison(8→9)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  turn_end

### Round 4
Intent: The Insatiable: Buff
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(8→9)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(9→10)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -10, Poison(10→11)
  Knife Trap -> The Insatiable[0]
    energy -2 | enemy_deltas: The Insatiable: hp -126, Poison(11→22), Weak(2→5)
  turn_end
## Combat Analytics: The Insatiable (WIN - 4 rounds)

Cards played (with descriptions):
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays, 3 dmg
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, 3 dmg, generates 1 Shivs
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 1 plays, 3 dmg
  Shiv "Deal 6 damage. Apply 1 Weak. Exhaust." -> 11 plays, 117 dmg, 5 block, +11 poison, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 7 dmg, +1 poison
  Accuracy+ "Shivs deal 6 additional damage." -> 1 plays
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Rage+ "Whenever you play an Attack this turn, gain 5 Block." -> 1 plays
  Strike "Deal 6 damage." -> 1 plays, 6 dmg, 5 block, +1 poison
  Conflagration "Deal 12 damage to ALL enemies. Deals 2 additional damage for each other Attack you've played this turn." -> 1 plays, 12 dmg, 5 block, +1 poison
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 1 plays
  Cloak and Dagger+ "Gain 9 Block. Add 2 Shivs into your Hand." -> 1 plays, 9 block, generates 2 Shivs
  Knife Trap "Play every Shiv in your Exhaust Pile on the enemy. (Plays 11 Shivs)" -> 1 plays, 126 dmg, +11 poison, EXHAUST

Token attribution (Shivs):
  other: 5 Shivs -> ~53 dmg
  Blade Dance: 3 Shivs -> ~32 dmg
  Cloak and Dagger+: 2 Shivs -> ~21 dmg
  Infinite Blades: 1 Shivs -> ~11 dmg

Poison stacks applied per card:
  Shiv: 11 stacks
  Knife Trap: 11 stacks
  Neutralize+: 1 stacks
  Strike: 1 stacks
  Conflagration: 1 stacks

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:6 -> R4:8
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:3
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2

[Selected: elite] Soul Nexus (F40, elite)
## Combat Replay: vs Soul Nexus (Floor 40, elite)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine, Delicate Frond, Orrery
Deck (35): Defend x5, Footwork+ x2, Piercing Wail x2, Strike x2, Acrobatics, Acrobatics+, Assassinate, Automation, Backflip, Backflip+, Bouncing Flask, Bubble Bubble, Calculated Gamble+, Corrosive Wave, Dagger Spray, Deadly Poison, Escape Plan+, Expertise, Fasten, Haze, Master of Strategy, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor, Well-Laid Plans+
Enemies: Soul Nexus HP=234/234

### Round 1
Agent plan (hypothesis): If we find Weak or good block, use it. Then play Footwork+ and Survivor if energy permits.
Agent plan (hypothesis): We skipped Footwork this cycle to mitigate more damage and start poison scaling.
Intent: Soul Nexus: Attack(29)
  Assassinate -> Soul Nexus[0]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Soul Nexus: hp -15, Vulnerable(1→2)
  Escape Plan+
    block +5
  Backflip
    energy -1 | block +5
  Skill Potion
  Mirage
  Deadly Poison+ -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: +Poison(7)
  Bubble Bubble -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: Poison(7→16)
  Mirage
    block +16 | exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 16 Block) Exhaust.
  turn_end

### Round 2
Intent: Soul Nexus: Attack(18), DebuffStrong
  Neutralize+ -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -6, +Weak(2)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
  Piercing Wail
  Piercing Wail

### Round 3
Agent plan (hypothesis): Retain Acrobatics+ with Well-Laid Plans.
Intent: Soul Nexus: Attack(32)
  Master of Strategy
    exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 14 Block) Exhaust.
  Footwork+
    energy -1 | +Dexterity(3)
  Calculated Gamble+
    exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 14 Block) Exhaust.
  Backflip+
    energy -1 | block +11
  Defend
    energy -1 | block +8
  turn_end
  Acrobatics+
  Noxious Fumes+

### Round 4
Agent plan (hypothesis): See what Acrobatics+ draws, then block the remaining damage.
Agent plan (hypothesis): Retain Bubble Bubble or another key card to burst damage next turn.
Intent: Soul Nexus: Attack(27), DebuffStrong
  Escape Plan+
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Soul Nexus: +Strength(-6), +Piercing Wail(6)
  Acrobatics+
    energy -1
  Skewer
  Footwork+
    energy -1 | Dexterity(3→6)
  turn_end
  Bubble Bubble
  Bouncing Flask

### Round 5
Agent plan (hypothesis): Hold Bouncing Flask for next turn's burst.
Intent: Soul Nexus: Attack(9x4=36)
  Piercing Wail
    energy -1 | enemy_deltas: Soul Nexus: +Strength(-6), +Piercing Wail(6)
  Bubble Bubble -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: Poison(12→21)
  Backflip
    energy -1 | block +11
  turn_end
  Bouncing Flask
  Corrosive Wave

### Round 6
Agent plan (hypothesis): Retain a key card
Intent: Soul Nexus: Attack(27), DebuffStrong
  Neutralize+ -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -3, +Weak(2)
  Fasten
    energy -1 | +Fasten(5)
  Backflip+
    energy -1 | block +14
  Defend
    energy -1 | block +16
  turn_end
  Bubble Bubble
  Noxious Fumes+

### Round 7
Agent plan (hypothesis): Retain Backflip for the next turn if prompted.
Intent: Soul Nexus: Attack(6x4=24)
  Defend
    energy -1 | block +16
  Defend
    energy -1 | block +16
  Bubble Bubble -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: Poison(19→28)
  turn_end
  Backflip
  Noxious Fumes+

### Round 8
Agent plan (hypothesis): Perfectly blocked, no damage taken.
Agent plan (hypothesis): Survive perfect block, enemy poison 31
Intent: Soul Nexus: Attack(43)
  Defend
    energy -1 | block +16
  Backflip
    energy -1 | block +11
  Escape Plan+
    block +11
  Survivor
    energy -1 | block +14
  Haze
  turn_end
    enemy_deltas: Soul Nexus: Poison(27→31)
  Noxious Fumes+
  Acrobatics+

### Round 9
Intent: Soul Nexus: Attack(6x4=24)
  Neutralize+ -> Soul Nexus[0]
    enemy_deltas: Soul Nexus: hp -4, +Weak(2)
  Bouncing Flask
    energy -2 | enemy_deltas: Soul Nexus: Poison(30→39)
  Bubble Bubble -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: Poison(39→48)
  turn_end
  Defend
  Noxious Fumes+
## Combat Analytics: Soul Nexus (WIN - 9 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 15 dmg, EXHAUST
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 5 Block." -> 3 plays, 16 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 3 plays, 27 block
  Deadly Poison+ "Apply 7 Poison." -> 1 plays, +7 poison
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 4 plays, +36 poison
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 16 Block) Exhaust." -> 1 plays, 16 block, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 13 dmg
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Defend "Gain 5 Block." -> 7 plays, 82 block
  Master of Strategy "Draw 3 cards. Exhaust." -> 1 plays, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 2 plays
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Backflip+ "Gain 11 Block. Draw 2 cards." -> 2 plays, 25 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Survivor "Gain 14 Block. Discard 1 card." -> 1 plays, 14 block
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, +9 poison

Poison stacks applied per card:
  Bubble Bubble: 36 stacks
  Bouncing Flask: 9 stacks
  Deadly Poison+: 7 stacks
  turn_end: 4 stacks

Enemy power timeline:
  Poison: R1:- -> R2:15 -> R3:14 -> R4:13 -> R5:12 -> R6:20 -> R7:19 -> R8:27 -> R9:30
  Vulnerable: R1:1 -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:-

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F43, elite)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 43, elite)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine, Delicate Frond, Orrery, Venerable Tea Set, Regal Pillow
Deck (35): Defend x5, Footwork+ x2, Piercing Wail x2, Strike x2, Acrobatics, Acrobatics+, Assassinate, Automation, Backflip, Backflip+, Bouncing Flask, Bubble Bubble, Calculated Gamble+, Corrosive Wave, Dagger Spray, Deadly Poison, Escape Plan+, Expertise, Fasten, Haze, Master of Strategy, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Agent plan (hypothesis): We need to block 17 damage. Defend+ and Survivor will easily cover it with the Dexterity boost.
Agent plan (hypothesis): We are fully blocked. Next turn Spectral Knight applies Hex.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Mazaleth's Gift
    +Ritual(1)
  Neutralize+ -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -6, +Weak(2)
  Assassinate -> Spectral Knight[1]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Spectral Knight: hp -15, Vulnerable(1→2)
  Footwork+
    energy -1 | +Dexterity(3)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Dagger Spray
    energy -1 | enemy_deltas: Flail Knight: hp -12; Spectral Knight: hp -12; Magi Knight: hp -12
  Defend+
    energy -1 | block +11
  Survivor
    energy -1 | block +11
  Strike
  turn_end

### Round 2
Agent plan (hypothesis): If we drew Calculated Gamble+, use it to stack even more poison and dig for Block/WLP+. Otherwise use the last energy for Backflip or another defensive option if needed.
Agent plan (hypothesis): Continue chaining 0-cost draws if possible to maximize AoE poison.
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Debuff
  Corrosive Wave+
    energy -1 | +Corrosive Wave(3)
  Escape Plan+
    block +8 | enemy_deltas: Flail Knight: Poison(3→6); Spectral Knight: Poison(3→6); Magi Knight: Poison(3→6)
  Acrobatics+
    energy -1 | enemy_deltas: Flail Knight: Poison(6→18); Spectral Knight: Poison(6→18); Magi Knight: Poison(6→18)
  Haze
  Backflip
    energy -1 | block +8 | enemy_deltas: Flail Knight: Poison(22→28); Spectral Knight: Poison(22→28); Magi Knight: Poison(22→28)
  Skewer -> Spectral Knight[1]
  turn_end
    exhausted: Well-Laid Plans+ [1]: Ethereal. At the end of your turn, Retain up to 2 cards.

### Round 3
Agent plan (hypothesis): Enemies will take massive poison damage next turn. Spectral and Magi should be very low or dead.
Intent: Flail Knight: Attack(12x2=24), Spectral Knight: Attack(15), Magi Knight: Attack(10)
  Ghost in a Jar
    +Intangible(1)
  Footwork
    energy -1 | Dexterity(3→5)
  Deadly Poison -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: Poison(30→35)
  Master of Strategy
    exhausted: Well-Laid Plans [1]: Ethereal. At the end of your turn, Retain up to 1 card.
  Defend
    energy -1 | block +10
  turn_end
    exhausted: Well-Laid Plans [1]: Ethereal. At the end of your turn, Retain up to 1 card.

### Round 4
Intent: Flail Knight: Attack(18), Spectral Knight: Attack(3x3=9), Magi Knight: Defend
  Skewer -> Flail Knight[0]
    energy -3 | enemy_deltas: Flail Knight: DIED
  turn_end
    exhausted: Well-Laid Plans [1]: Ethereal. At the end of your turn, Retain up to 1 card.
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 6 dmg
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 15 dmg, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 36 dmg
  Defend+ "Gain 11 Block." -> 1 plays, 11 block
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Corrosive Wave+ "Ethereal. Whenever you draw a card this turn, apply 3 Poison to ALL enemies." -> 1 plays
  Escape Plan+ "Ethereal. Draw 1 card. If you draw a Skill, gain 8 Block." -> 1 plays, 8 block, +9 poison
  Acrobatics+ "Ethereal. Draw 4 cards. Discard 1 card." -> 1 plays, +36 poison
  Backflip "Ethereal. Gain 8 Block. Draw 2 cards." -> 1 plays, 8 block, +18 poison
  Skewer "Ethereal. Deal 9 damage X times." -> 2 plays
  Footwork "Ethereal. Gain 2 Dexterity." -> 1 plays
  Deadly Poison "Ethereal. Apply 5 Poison." -> 1 plays, +5 poison
  Master of Strategy "Ethereal. Draw 3 cards. Exhaust." -> 1 plays, EXHAUST
  Defend "Ethereal. Gain 10 Block." -> 1 plays, 10 block

Poison stacks applied per card:
  Acrobatics+: 36 stacks
  Backflip: 18 stacks
  Escape Plan+: 9 stacks
  Deadly Poison: 5 stacks
Total poison/power tick damage: 25
  Per round: R4:25

Enemy power timeline:
  Poison[0]: R1:- -> R2:3 -> R3:30 -> R4:32
  Poison[1]: R1:- -> R2:3 -> R3:30 -> R4:37
  Poison[2]: R1:- -> R2:3 -> R3:30 -> R4:32
  Strength: R1:- -> R2:- -> R3:3 -> R4:3
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:-
  Vulnerable[2]: R1:1 -> R2:- -> R3:- -> R4:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 40, elite)
Relics: Ring of the Snake, Winged Boots, Mango, War Paint, Tea of Discourtesy, Archaic Tooth, Strawberry, Unceasing Top, Oddly Smooth Stone, Miniature Tent, Signet Ring, Happy Flower, Petrified Toad
Deck (31): Defend x4, Bubble Bubble x2, Accelerant+, Acrobatics+, Adrenaline+, Backflip+, Calculated Gamble, Cloak and Dagger, Dagger Throw, Dagger Throw+, Dark Shackles, Deadly Poison+, Defend+, Dodge and Roll, Exterminate, Haze, Haze+, Malaise+, Mirage, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Snakebite, Suppress, Survivor, Well-Laid Plans
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
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

[Selected: elite] Mecha Knight (F46, elite)
## Combat Replay: vs Mecha Knight (Floor 46, elite)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine, Delicate Frond, Orrery, Venerable Tea Set, Regal Pillow, Strike Dummy
Deck (36): Defend x5, Calculated Gamble+ x2, Footwork+ x2, Piercing Wail x2, Strike x2, Acrobatics, Acrobatics+, Assassinate, Automation, Backflip, Backflip+, Bouncing Flask, Bubble Bubble, Corrosive Wave, Dagger Spray, Deadly Poison, Escape Plan+, Expertise, Fasten, Haze, Master of Strategy, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor, Well-Laid Plans+
Enemies: Mecha Knight HP=300/300

### Round 1
Agent plan (hypothesis): Re-plan after drawing to use 2 energy optimally for block.
Agent plan (hypothesis): Depending on draw, use Weak Potion if needed.
Agent plan (hypothesis): We need 6 more block after Backflip+. If no better block/weak is drawn, play Survivor or Defend.
Intent: Mecha Knight: Attack(25)
  Assassinate -> Mecha Knight[0]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Mecha Knight: hp -10, Artifact(2→1)
  Footwork+
    energy -1 | +Dexterity(3)
  Calculated Gamble+
    exhausted: Calculated Gamble+ [0]: Retain. Discard your Hand, then draw that many cards. Exhaust. | enemy_deltas: Mecha Knight: -Artifact
  Master of Strategy
    exhausted: Master of Strategy [0]: Draw 3 cards. Exhaust.
  Escape Plan+
    block +8
  Backflip
    energy -1 | block +8
  Backflip+
    energy -1 | block +11
  Skewer -> Mecha Knight[0]
  turn_end

### Round 2
Intent: Mecha Knight: StatusCard(4)
  Gigantification Potion
    +Gigantification(1)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Predator+ -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | -Gigantification | enemy_deltas: Mecha Knight: hp -60
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4, +Weak(2)
  turn_end

### Round 3
Agent plan (hypothesis): Retain Piercing Wail+ to mitigate the incoming 40+ damage attack.
Intent: Mecha Knight: Defend, Buff
  Fasten
    energy -1 | +Fasten(5)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Calculated Gamble+
  Bubble Bubble -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(2→11)
  turn_end
  Piercing Wail+
  Deadly Poison+

### Round 4
Intent: Mecha Knight: Attack(40)
  Defend
    energy -1 | block +13
  Defend
    energy -1 | block +13
  Defend
    energy -1 | block +13
  turn_end
  Piercing Wail+
  Haze

### Round 5
Agent plan (hypothesis): Survivor discarding Haze is likely the best line for 1 energy.
Agent plan (hypothesis): Retain Piercing Wail+. Next turn is buff/defend, then Turn 7 is the huge 40+ damage attack.
Intent: Mecha Knight: StatusCard(4)
  Noxious Fumes+
    energy -1 | Noxious Fumes(2→5)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4, +Weak(2)
  Predator+ -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -20
  turn_end
  Piercing Wail+
  Bouncing Flask

### Round 6
Agent plan (hypothesis): Retain Piercing Wail+. Next turn is the 40+ damage attack.
Agent plan (hypothesis): Retain Piercing Wail+ for turn 7.
Intent: Mecha Knight: Defend, Buff
  Escape Plan+
    block +8
  Bouncing Flask
    energy -2 | enemy_deltas: Mecha Knight: Poison(17→26)
  Acrobatics
    energy -1
  Burn
  turn_end
  Piercing Wail+
  Backflip

### Round 7
Agent plan (hypothesis): Retain Piercing Wail+ and Predator/Flask.
Intent: Mecha Knight: Attack(45)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: block -4, +Weak(2)
  Backflip
    energy -1 | block +8
  Defend
    energy -1 | block +13
  Survivor
    energy -1 | block +11
  Burn
  turn_end
  Piercing Wail+
  Predator+

### Round 8
Intent: Mecha Knight: StatusCard(4)
  Bubble Bubble -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(34→43)
  Predator+ -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -20
  turn_end
  Piercing Wail+
  Backflip+

### Round 9
Intent: Mecha Knight: Defend, Buff
  Defend
    energy -1 | block +13
  Defend
    energy -1 | block +13
  Backflip+
    energy -1 | block +11
  turn_end
  Piercing Wail+
  Strike
## Combat Analytics: Mecha Knight (WIN - 9 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 10 dmg, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 2 plays, EXHAUST
  Master of Strategy "Draw 3 cards. Exhaust." -> 1 plays, EXHAUST
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 8 Block." -> 2 plays, 16 block
  Backflip "Gain 8 Block. Draw 2 cards." -> 2 plays, 16 block
  Backflip+ "Gain 11 Block. Draw 2 cards." -> 2 plays, 22 block
  Skewer "Deal 8 damage X times." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Predator+ "Deal 60 damage. Next turn, draw 2 cards." -> 3 plays, 100 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 2 plays, +18 poison
  Defend "Gain 13 Block." -> 6 plays, 78 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, +9 poison
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block

Poison stacks applied per card:
  Bubble Bubble: 18 stacks
  Bouncing Flask: 9 stacks

Enemy power timeline:
  Artifact: R1:2 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:2 -> R4:12 -> R5:13 -> R6:17 -> R7:30 -> R8:34 -> R9:47
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10 -> R8:10 -> R9:10
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:1 -> R9:-
Comparator (recent same-enemy comparator):
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

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine, Delicate Frond, Orrery, Venerable Tea Set, Regal Pillow, Strike Dummy, Snecko Skull
Deck (37): Defend x5, Piercing Wail x3, Calculated Gamble+ x2, Footwork+ x2, Strike x2, Acrobatics, Acrobatics+, Assassinate, Automation, Backflip, Backflip+, Bouncing Flask, Bubble Bubble, Corrosive Wave+, Dagger Spray, Deadly Poison, Escape Plan+, Expertise, Fasten, Haze, Master of Strategy, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Agent plan (hypothesis): We have 3 energy left to block the 18 incoming damage. Hold Piercing Wail if possible, as it's better for the Amalgam's multi-attack turns.
Agent plan (hypothesis): Saved Piercing Wails for the Amalgam's multi-attack turns.
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Strength Potion
    +Strength(2)
  Fire Potion -> Queen[1]
    enemy_deltas: Queen: hp -20
  Assassinate -> Queen[1]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Queen: hp -18, Vulnerable(1→2)
  Automation
    energy -1 | +Automation(1)
  Acrobatics+
    energy -1
  Predator+
  Fasten
    energy -1 | +Fasten(5)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Defend+
    energy -1 | block +13
  turn_end

### Round 2
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Bubble Bubble -> Queen[1]
    energy -1 | enemy_deltas: Queen: Poison(3→13)
  Defend
    energy -1 | block +10
  Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -16
  turn_end
  Haze+
  Survivor

### Round 3
Agent plan (hypothesis): If we draw a good 1-cost block or Neutralize, we can play it. We still need to block 18.
Agent plan (hypothesis): Blocked all damage, scaling Dexterity for future turns.
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Master of Strategy
    exhausted: Master of Strategy [0]: Draw 3 cards. Bound Exhaust.
  Piercing Wail
    energy -1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Torch Head Amalgam: +Strength(-6), +Piercing Wail(6); Queen: +Strength(-6), +Piercing Wail(6)
  Acrobatics
  Haze+
  Footwork+
    energy -1 | +Dexterity(3)
  Backflip+
    energy -1 | block +8
  Neutralize+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4, +Weak(2)
  turn_end
  Escape Plan+
  Footwork+

### Round 4
Agent plan (hypothesis): Play any 0-cost cards drawn, then play Calculated Gamble+. You will have 1 Energy left to play defensive cards drawn from the Gamble.
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Corrosive Wave+
    energy -1 | +Corrosive Wave(3)
  Footwork+
    energy -1 | Dexterity(3→6)
  Noxious Fumes+
    energy -1 | Noxious Fumes(2→5) | enemy_deltas: Torch Head Amalgam: Poison(14→22); Queen: Poison(24→32)
  Escape Plan+
    enemy_deltas: Torch Head Amalgam: Poison(22→26); Queen: Poison(32→36)
  Calculated Gamble+
    energy +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Torch Head Amalgam: Poison(26→58); Queen: Poison(36→68)
  Neutralize+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4, Weak(1→3)
  Acrobatics+
    energy -1 | enemy_deltas: Torch Head Amalgam: Poison(58→74); Queen: Poison(68→84)
  Haze+
  Defend+
    energy -1 | block +14
  turn_end
  Bouncing Flask
  Piercing Wail

### Round 5
Agent plan (hypothesis): Hold onto block and cycle for the multi-attack next turn.
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Backflip+
    energy -1 | block +10
  Defend+
    energy -1 | block +14
  Deadly Poison -> Queen[1]
    energy -1 | enemy_deltas: Queen: Poison(96→102)
  Bubble Bubble -> Queen[1]
    energy -1 | enemy_deltas: Queen: Poison(102→112)
  turn_end
  Piercing Wail
  Acrobatics+

### Round 6
Agent plan (hypothesis): Lethal achieved via Poison.
Agent plan (hypothesis): gg
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Calculated Gamble+
    energy +1 | enemy_deltas: Torch Head Amalgam: Poison(91→98); Queen: Poison(117→124)
  Piercing Wail
    energy -1 | enemy_deltas: Torch Head Amalgam: Strength(3→-3), +Piercing Wail(6); Queen: +Strength(-6), +Piercing Wail(6)
  turn_end
  Expertise
  Corrosive Wave+
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 6 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 12 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 18 dmg, EXHAUST
  Automation "Every 10 cards you draw, gain 1 energy ." -> 1 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays, +32 poison
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Defend+ "Gain 13 Block." -> 3 plays, 41 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards. Bound" -> 1 plays
  Bubble Bubble "If the enemy has Poison, apply 10 Poison." -> 2 plays, +20 poison
  Defend "Gain 10 Block." -> 1 plays, 10 block
  Strike "Deal 11 damage." -> 1 plays, 16 dmg
  Master of Strategy "Draw 3 cards. Bound Exhaust." -> 1 plays, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Footwork+ "Gain 3 Dexterity. Bound" -> 2 plays
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 2 plays, 18 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 8 dmg
  Corrosive Wave+ "Whenever you draw a card this turn, apply 3 Poison to ALL enemies." -> 1 plays
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played. Bound" -> 1 plays, +16 poison
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 8 Block." -> 1 plays, +8 poison
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 2 plays, +78 poison, EXHAUST
  Deadly Poison "Apply 6 Poison." -> 1 plays, +6 poison

Poison stacks applied per card:
  Calculated Gamble+: 78 stacks
  Acrobatics+: 32 stacks
  Bubble Bubble: 20 stacks
  Noxious Fumes+: 16 stacks
  Escape Plan+: 8 stacks
  Deadly Poison: 6 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Poison[0]: R1:- -> R2:3 -> R3:5 -> R4:14 -> R5:86 -> R6:91
  Poison[1]: R1:- -> R2:3 -> R3:15 -> R4:24 -> R5:96 -> R6:117
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Drake, Precarious Shears, Festive Popper, Pen Nib, Touch of Orobas, War Paint, Strawberry, Distinguished Cape, Akabeko, Regal Pillow, Ripple Basin, Pendulum
Deck (37): Defend x4, Apparition x3, Blade Dance x2, Cloak and Dagger+ x2, Footwork+ x2, Piercing Wail+ x2, Accuracy+, Backflip, Blade Dance+, Blade of Ink+, Bullet Time+, Calculated Gamble, Conflagration+, Dodge and Roll, Dodge and Roll+, Hidden Daggers, Infinite Blades, Knife Trap+, Leading Strike, Leading Strike+, Neutralize+, Pinpoint, Predator, Rage+, Scrawl+, Shockwave, Strangle+, Survivor
Enemies: Torch Head Amalgam HP=190/199, Queen HP=391/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Duplicator
    +Duplication(1)
  Footwork+
    energy -1 | +Dexterity(6) | -Duplication
  Footwork+
    energy -1 | Dexterity(6→9)
  Apparition
    energy -1 | +Intangible(1) | exhausted: Apparition [1]: Ethereal. Gain 1 Intangible. Exhaust.
  turn_end
    block +4

### Round 2
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  Scrawl+
    energy -1 | exhausted: Scrawl+ [1]: Retain. Draw cards until your Hand is full. Exhaust.
  Bullet Time+
    energy -2 | +No Draw(1)
  Dodge and Roll+
    block +15 | +Block Next Turn(15)
  Backflip
    block +14
  Neutralize+ -> Torch Head Amalgam[0]
    -Vigor | enemy_deltas: Torch Head Amalgam: hp -12, +Weak(2)
  Cloak and Dagger+
    block +15
  Shiv -> Queen[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Leading Strike+ -> Queen[1]
    enemy_deltas: Queen: hp -6
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Conflagration+
    enemy_deltas: Torch Head Amalgam: hp -48; Queen: hp -48
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.

### Round 3
Intent: Torch Head Amalgam: Attack(9x3=27), Queen: Buff, Defend
  Accuracy+
    energy -1 | +Accuracy(6)
  Dodge and Roll
    energy -1 | block +9 | +Block Next Turn(9)
  Defend
    energy -1 | block +10
  Hidden Daggers
  Blade of Ink+
  Blade Dance+
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -7
  turn_end

### Round 4
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  Colorless Potion
  Production
  Production
    energy +2 | exhausted: Shiv*6 [0]: Deal 4 damage. Exhaust.
  Shockwave
    energy -2 | exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust. | enemy_deltas: Torch Head Amalgam: +Weak(3), +Vulnerable(3); Queen: +Weak(3), +Vulnerable(3)
  Leading Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -11
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -5, block -6
  Predator -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -16
  turn_end

### Round 5
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Rage+
    +Rage(5)
  Cloak and Dagger+
    energy -1 | block +11
  Apparition
    energy -1 | +Intangible(1)
  Strangle+ -> Queen[1]
    energy -1 | block +5 | enemy_deltas: Queen: block -11, +Strangle(3)
  Shiv -> Queen[1]
    block +5 | enemy_deltas: Queen: hp -5, block -9
  Pinpoint -> Queen[1]
    block +5 | enemy_deltas: Queen: hp -36
  Shiv -> Queen[1]
    block +5 | enemy_deltas: Queen: hp -14
  turn_end

### Round 6
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Cloak and Dagger+
    energy -1 | block +11
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -11
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -2, block -9
  Predator -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -16
  turn_end

### Round 7
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  Backflip
    energy -1 | block +10
  Bullet Time+
    energy -2 | +No Draw(1)
  Strangle+ -> Queen[1]
    enemy_deltas: Queen: block -7, +Strangle(3)
  Cloak and Dagger+
    block +11 | enemy_deltas: Queen: hp -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -3, block -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4, block -6
  Defend
    block +10 | enemy_deltas: Queen: hp -3
  Defend
    block +10 | enemy_deltas: Queen: hp -3
  Survivor
    block +12
  Conflagration+
  turn_end

### Round 8
Intent: Torch Head Amalgam: Attack(28), Queen: Buff, Defend
  Rage+
    +Rage(5)
  Defend
    energy -1 | block +10
  Blade Dance
    energy -1 | exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust.
  Shiv -> Queen[1]
    block +5 | enemy_deltas: Queen: block -7
  Shiv -> Queen[1]
    block +5 | enemy_deltas: Queen: block -7
  Shiv -> Queen[1]
    block +5 | enemy_deltas: Queen: hp -9, block -6
  turn_end

### Round 9
Intent: Torch Head Amalgam: Attack(21x3=63), Queen: Buff, Defend
  Piercing Wail+
    energy -1 | exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust. | enemy_deltas: Torch Head Amalgam: Strength(6→-2), +Piercing Wail(8); Queen: +Strength(-8), +Piercing Wail(8)
  Dodge and Roll+
    energy -1 | block +11 | +Block Next Turn(11)
  Dodge and Roll
    energy -1 | block +9 | Block Next Turn(11→20)
  turn_end
    block +4

### Round 10
Intent: Torch Head Amalgam: Attack(31), Queen: Buff, Defend
  Blade of Ink+
    energy -1
  Strangle+ -> Queen[1]
    energy -1 | enemy_deltas: Queen: block -7, +Strangle(3)
  Shiv -> Torch Head Amalgam[0]
    exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -9, +Weak(1); Queen: hp -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -3, block -9, +Weak(1)
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -8, block -4, Weak(1→2)
  Defend
    energy -1 | block +10 | enemy_deltas: Queen: hp -3
  turn_end

### Round 11
Intent: Torch Head Amalgam: Attack(33), Queen: Buff, Defend
  Piercing Wail+
    energy -1 | exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust. | enemy_deltas: Torch Head Amalgam: +Piercing Wail(8), -Strength; Queen: +Strength(-8), +Piercing Wail(8)
  Defend
    energy -1 | block +10
  Hidden Daggers
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -7
  turn_end

### Round 12
Intent: Torch Head Amalgam: Attack(25x3=75), Queen: Buff, Defend
  Backflip
    energy -1 | block +10
  Bullet Time+
    energy -2 | +No Draw(1)
  Blade Dance+
    exhausted: Shockwave [2]: Apply 3 Weak and Vulnerable to ALL enemies. Exhaust.
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -1, block -6
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -15
  Predator -> Queen[1]
    +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -11
  Pinpoint -> Queen[1]
    enemy_deltas: Queen: hp -11
  Defend
    block +10
  turn_end
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 12 rounds)
Death cause: Died with HP=14, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 2 plays
  Apparition "Ethereal. Gain 1 Intangible. Exhaust." -> 2 plays, EXHAUST
  Scrawl+ "Retain. Draw cards until your Hand is full. Exhaust." -> 1 plays, EXHAUST
  Bullet Time+ "You cannot draw additional cards this turn. ALL cards in your Hand are free to play this turn." -> 3 plays
  Dodge and Roll+ "Gain 15 Block. Next turn, gain 15 Block." -> 2 plays, 26 block
  Backflip "Gain 14 Block. Draw 2 cards." -> 3 plays, 34 block
  Neutralize+ "Deal 12 damage. Apply 2 Weak." -> 1 plays, 12 dmg
  Cloak and Dagger+ "Gain 15 Block. Add 2 Shivs into your Hand." -> 4 plays, 3 dmg, 48 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 26 plays, 111 dmg, 25 block, EXHAUST
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand. Bound" -> 1 plays, 6 dmg, generates 2 Shivs
  Conflagration+ "Deal 48 damage to ALL enemies. Deals 3 additional damage for each other Attack you've played this turn." -> 1 plays, 96 dmg
  Accuracy+ "Shivs deal 6 additional damage. Bound" -> 1 plays
  Dodge and Roll "Gain 9 Block. Next turn, gain 9 Block." -> 2 plays, 18 block
  Defend "Gain 10 Block." -> 7 plays, 9 dmg, 70 block
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 2 plays, generates 2 Shivs
  Production "Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Shockwave "Apply 3 Weak and Vulnerable to ALL enemies. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 1 plays, generates 2 Shivs
  Predator "Deal 11 damage. Next turn, draw 2 cards. Bound" -> 3 plays, 43 dmg
  Rage+ "Whenever you play an Attack this turn, gain 5 Block. Bound" -> 2 plays
  Strangle+ "Deal 7 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 3 plays, 5 block
  Pinpoint "Deal 22 damage. Costs 1 less 1 energy for each Skill played this turn." -> 2 plays, 47 dmg, 5 block
  Survivor "Gain 12 Block. Discard 1 card." -> 1 plays, 12 block
  Blade Dance "Add 3 Shivs into your Hand. Bound Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Blade of Ink+ "Add 3 Inky Shivs into your Hand. Bound" -> 1 plays
  Blade Dance+ "Add 4 Shivs into your Hand. Bound Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs

Active powers: Vigor(8)

Token attribution (Shivs):
  Cloak and Dagger+: 8 Shivs -> ~34 dmg
  Hidden Daggers: 4 Shivs -> ~17 dmg
  Blade Dance+: 4 Shivs -> ~17 dmg
  Blade Dance: 3 Shivs -> ~13 dmg
  other: 3 Shivs -> ~13 dmg
  Leading Strike+: 2 Shivs -> ~9 dmg
  Leading Strike: 2 Shivs -> ~9 dmg

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:6 -> R10:7 -> R11:8 -> R12:9
  Vulnerable[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Vulnerable[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:1 -> R12:-
  Weak[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Weak[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-

## Triggered Skills This Run
- The Silent - Boss Strategy: F17(Kin Follower: WIN), F33(The Insatiable: WIN), F48(Torch Head Amalgam: WIN)
- The Silent - Combat Principles: F2(Shrinker Beetle: WIN), F3(Twig Slime (S): ), F4(Nibbit: WIN), F6(Twig Slime (M): ), F8(Shrinker Beetle: ), F12(Phrog Parasite: ), F13(Snapping Jaxfruit: ), F14(Leaf Slime (M): WIN), F15(Vine Shambler: WIN), F19(Thieving Hopper: WIN), F22(Tunneler: WIN), F23(Myte: WIN), F27(Spiny Toad: WIN), F28(Hunter Killer: WIN), F30(Infested Prism: WIN), F35(Devoted Sculptor: WIN), F38(Scroll of Biting: WIN), F40(Soul Nexus: WIN), F43(Flail Knight: ), F45(Punch Construct: ), F46(Mecha Knight: WIN)
- The Silent - Deckbuilding Principles: F2(), F3(), F4(), F5(), F6(), F8(), F12(), F13(), F14(), F15(), F17(), F19(), F21(), F21(), F22(), F22(), F23(), F24(), F27(), F28(), F30(), F33(), F35(), F35(), F38(), F39(), F39(), F39(), F39(), F39(), F39(), F40(), F40(), F43(), F45(), F46()
- The Silent - Path Selection: F1(), F1(), F2(), F3(), F4(), F5(), F6(), F7(), F8(), F8(), F9(), F9(), F10(), F10(), F11(), F12(), F13(), F14(), F15(), F18(), F18(), F19(), F20(), F21(), F22(), F23(), F24(), F25(), F26(), F27(), F28(), F29(), F30(), F31(), F34(), F34(), F35(), F35(), F36(), F37(), F38(), F39(), F40(), F40(), F41(), F41(), F42(), F43(), F44(), F45(), F45(), F46(), F46()
- The Silent - Rest & Event Decisions: F7(), F9(), F11(), F16(), F25(), F29(), F32(), F42(), F44(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.