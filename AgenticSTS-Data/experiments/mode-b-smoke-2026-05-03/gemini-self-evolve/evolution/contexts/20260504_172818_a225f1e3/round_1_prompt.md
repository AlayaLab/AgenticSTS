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
Result: DEFEAT at Floor 48 (fitness: 140.6)
Combats won: 22/22
Run duration: 5594.6s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: Looking for high-damage attacks to clear Act 1 elites and block scaling. Play safe and prioritize upgrades at rest sites.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation phase: prioritized drafting high-impact front-loaded damage and draw/discard pieces to handle Act 1 elites. Focusing on building a consistent deck through early hallway fights while maintaining enough HP to upgrade at rest sites.
### F2
- [card_reward] Foundation plan: prioritize high-impact damage attacks to survive Act 1 elites while we search for a scaling engine. Avoid adding too many skills until our damage is sufficient.
### F3
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; lean towards Shiv synergies given our early picks. Take cheap draw or high-impact damage, skip narrow synergies until an engine piece is secured.
### F4
- [card_reward] Committed to multi-play/Shiv engine: rely on Strangle and Shiv generation for damage scaling. Prioritize 0-cost attacks, cheap draw, and multi-play payoffs. Skip poison and slow, expensive powers.
- [map] Foundation phase: prioritizing hallway fights for front-loaded damage (Dagger Throw, Poisoned Stab) and defensive consistency (Acrobatics, Backflip) to handle Act 1 elites. I will delay the first elite until late act and prioritize upgrades over resting to secure long-term scaling.
### F5
- [card_reward] Foundation phase: Build around Strangle and Shivs for burst damage. Skip poison and narrow synergies. Look for more 0-cost cards, card draw, and reliable multi-hit attacks.
### F6
- [card_reward] Committed shiv/strangle plan: use Strangle, Leading Strike, and Infinite Blades to overwhelm enemies with many card plays. Need card draw, burst shiv generation, and efficient mitigation to support the engine. Skip poison and alternate archetypes.
### F7
- [rest_site] Foundation phase: Building around Strangle and Shiv generation for burst damage. Play Strangle early in the turn, followed by 0-cost cards like Shivs and Neutralize to maximize HP loss. Need card draw (Acrobatics, Backflip) to fuel Strangle turns and more consistent block.
### F8
- [card_reward] Committed card spam/Shiv plan: use Strangle+ as the core damage engine, fueled by Shivs (Leading Strike, Infinite Blades) and free cycle (Adrenaline). Needs more Shiv generation, draw, and permanent scaling (Accuracy/Footwork); skip slow mechanics like poison.
- [map] Foundation phase: prioritizing high-impact upgrades at rest sites to compensate for lack of elite-slaying burst. Seeking efficient block and draw-discard synergies to stabilize the mid-game while preserving HP for the Act 1 boss.
### F9
- [rest_site] Foundation phase: Building around Strangle and Shiv generation. Play Strangle early, fueled by Adrenaline+ and 0-cost cards. Need more card draw to reliably assemble Strangle burst turns and better mitigation for consistency.
### F11
- [card_reward] Committed to attack/Shiv multi-hit plan powered by Strangle+; prioritize card draw, cheap attacks, and direct burst scaling like Accuracy or Phantom Blades. Skip poison and heavy attacks.
- [map] Foundation phase: prioritized high-damage attacks for Act 1 elites. Currently transitioning into finding consistent block and draw while maintaining enough health to aggressively upgrade at rest sites.
### F12
- [event] Foundation phase: Building around Strangle+ and Shiv generation, fueled by Adrenaline+ and 0-cost attacks. Prioritize card draw to consistently assemble Strangle turns and find better block mitigation. Avoid taking too much damage to allow upgrading at rest sites.
- [map] Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts before the Act 1 boss.
### F13
- [rest_site] Foundation phase: Building around Strangle+ and Shiv generation. Use potions from Tiny Mailbox to burst down elites or sustain through tough fights while searching for more card draw to consistently trigger Strangle.
### F14
- [card_reward] Committed to a Shiv/Strangle burst damage plan. Prioritize cheap card draw, energy generation, and efficient block to survive while setting up Strangle combos. Avoid adding heavy, non-synergistic attacks.
### F15
- [card_reward] Committed Strangle/Shiv plan: setup Strangle and play as many cards as possible in a single turn. Prioritize cheap attacks, Shiv generators, and cycle (like Backflip) to maximize Strangle triggers. Needs efficient block and burst scaling; avoid slow poison or unrelated archetypes.
### F16
- [rest_site] Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts.
### F17
- [card_reward] Committed Strangle/Shiv multi-play plan. Fuel Strangle with 0-cost cards like Shivs generated from Storm of Steel, Leading Strike, and Infinite Blades. Prioritize cheap draw to find combo pieces and relics like Shuriken/Kunai to scale the multiple attacks. Avoid slow poison or heavy, expensive cards.
### F18
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation, so we can focus on finding more card draw and defensive scaling to reliably set up our Strangle combo.
- [map] Foundation phase: Strangle and Shiv scaling. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently hunting for Acrobatics and defensive consistency to safely set up Strangle bursts; will pivot to non-combat nodes once the draw engine is stabilized to leverage Planisphere healing.
### F19
- [card_reward] Committed Shiv/Strangle engine: stockpile Shivs using Phantom Blades' retain, then unleash them all on Strangle+ burst turns. Prioritize card draw to find the combo and block/weakness to survive while setting up. Skip poison and off-plan attacks.
### F20
- [card_select] Committed to Shiv/multi-play scaling with Phantom Blades and Strangle. Prioritize playing powers early and retaining Shivs for Strangle burst turns. Remove Strikes aggressively and look for more cheap draw (Acrobatics) and defense.
### F21
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Use Foul Potions strictly for gold at merchants unless lethal AoE is absolutely necessary to survive a fight.
### F22
- [map] Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns, utilizing Planisphere to sustain HP through Unknown nodes while hunting for defensive consistency and card draw.
### F23
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Use Foul Potions strictly for gold at merchants unless lethal AoE is absolutely necessary to survive a fight.
### F24
- [card_reward] Committed Strangle/Shiv plan: setup Strangle+ early, then spam zero-cost cards (Shivs, Purity, Adrenaline) to trigger massive passive damage. Defend heavily on off-turns. Prioritize card draw and card removals to increase the density of zero-cost plays.
### F25
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.
- [card_select] Committed Phantom Blades engine: prioritize cheap card draw to find setup powers early, remove basic Strikes, and rely on multi-hit attacks (Shivs, Storm of Steel, Follow Through) scaled by Phantom Blades for damage. Avoid alternate scaling archetypes.
### F26
- [map] Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts.
### F27
- [rest_site] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress+ gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.
### F28
- [card_select] Committed Strangle/Phantom Blades attack plan: hold cheap attacks and Retain cards for Strangle burst turns. Prioritize energy generation and card draw to set up powers quickly; avoid adding any poison cards.
- [card_reward] Committed Shiv/Strangle plan: Use Strangle+ and Phantom Blades for scaling burst damage via Shivs. Keep the deck lean to find powers/Strangle quickly. Prioritize removals and high-value draw/defense, avoiding off-plan attacks.
- [map] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.
### F29
- [card_reward] Committed Shiv/Direct scaling plan: establish Phantom Blades and Infinite Blades, use Strangle+ for burst, and defend efficiently while scaling. Need more multi-hit attacks/Shiv generation and to remove Strikes.
### F30
- [card_reward] Committed shiv plan: rely on Phantom Blades and Shiv generation to deal steady damage while blocking safely. Prioritize draw and mitigation; skip generic attacks and alternate scaling.
- [map] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ for burst. Suppress provides critical turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle; favor safe paths to preserve HP for the boss.
### F31
- [card_reward] Committed Shiv/Strangle plan: prioritize drawing and playing Strangle and Phantom Blades, then spam Shivs to scale damage quickly. Retain Shivs with Phantom Blades if Strangle is not yet drawn. Keep the deck lean and remove basic Strikes.
### F32
- [rest_site] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress+ gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.
### F33
- [card_reward] Committed shiv/attack plan: setup Phantom Blades and Strangle, then play cheap attacks and Shivs for burst damage. Prioritize finding our scaling early; use Tools of the Trade and draw skills to dig through statuses. Need basic Strike removals.
### F34
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ and massive Swift draw to enable explosive burst turns. Play 0-cost Swift-enchanted cards to cycle rapidly and find Strangle+, then dump Shivs. Prioritize card removal and block density now that draw is completely solved.
- [card_select] Committed Shiv/Strangle plan: Use 0-cost Swift enchantments to rapidly cycle the deck, find Phantom Blades and Strangle early, and overwhelm enemies with massive bursts of free attacks. Need consistent discard or energy to sustain the massive card draw.
- [map] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ for burst. Suppress provides critical turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle; shift towards non-combat nodes once the defense is stable to utilize Planisphere healing.
### F35
- [hand_select] Maximize turn 1 scaling with Infinite Blades and Strangle+.
- [card_reward] Committed to Shivs and Strangle scaling. Prioritize cards that generate Shivs, draw, and cycle to trigger Strangle multiple times. Skip poison and alternate scaling.
### F36
- [card_reward] Committed Shiv/Strangle plan: burst damage with Strangle+ and Shivs, scaling first Shiv via Phantom Blades. Keep the deck lean and prioritize block/draw to survive Queen's 20 block/turn and Amalgam's scaling.
- [map] Foundation Shiv and Strangle deck: uses Adrenaline+ for acceleration and Suppress+ for early mitigation. Focus on finding consistent block and additional Shiv generation or scaling to close out long fights; avoid high-attrition Act 3 elites unless necessary for power.
### F37
- [card_select] Committed Shiv/Strangle plan: prioritize setting up Phantom Blades and Strangle early, then cycle rapidly to generate Shivs for massive burst damage. Keep relying on Fasten + Defends for block scaling. Avoid drafting generic attacks.
### F38
- [hand_select] Discarding Defend to keep more impactful setup cards like Infinite Blades and Fasten, while preparing for a Shiv-heavy offense.
- [card_reward] Committed Shiv plan: scale damage with Phantom Blades and Strangle by playing multiple Shivs per turn. Focus on rapid card cycle to find setup powers early, and use Fasten and dexterity for block. Avoid adding non-Shiv damage cards to keep draws consistent.
- [map] Foundation shiv and strangle deck: prioritize turn 1 burst with Adrenaline+ and Suppress+ mitigation. Scaling relies on shiv generation and Strangle+ for high single-target damage. Currently seeking consistent block and draw to survive between burst turns while using ? nodes to sustain health via Planisphere.
### F39
- [event] Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ and massive Swift draw to enable explosive burst turns. Seek consistent block and prioritize card removal.
- [map] Foundation shiv and strangle deck: prioritize front-loaded damage from Shivs while utilizing Strangle+ for scaling and Suppress+ for turn 1 safety. Plan is to use Adrenaline+ to cycle into burst turns; need more consistent block or scaling like Accuracy to solidify the endgame against the Act 3 boss.
### F40
- [map] Foundation shiv and burst deck: Use Adrenaline+ and Suppress+ to control the opening turn, setting up Strangle+ for high-impact shiv damage. Seek more defensive consistency or cycle (Acrobatics) to bridge the gap between burst turns; avoid high-attrition Act 3 elites if possible.
### F43
- [rest_site] Committed Strangle/Shiv engine: play Strangle on turns with massive card draw/shiv generation for lethal burst damage, while using Swift block cards and Retain mechanics to survive. Need consistent draw to reliably pair Strangle with Storm of Steel or Leading Strike.
- [map] Foundation phase: leveraging Strangle+ and Shivs with high draw (Adrenaline+, Swift) for burst damage. Seeking reliable block and card removal to survive late-act attrition while avoiding Elites to preserve HP for the boss.
### F44
- [card_reward] Committed Shiv plan: stack burst damage with Phantom Blades and generate Shivs while defending with efficient block. Retain Piercing Wails for multi-attack turns. Needs Well-Laid Plans and more draw; avoid bloating with non-synergy attacks.
- [map] Foundation phase focusing on Strangle and Shiv burst enabled by Adrenaline and high draw. Prioritizing Unknown nodes to leverage Planisphere healing and minimize chip damage before the final boss. Need more consistent block and potentially one more scaling piece to solidify the late game.
### F45
- [event] Committed Strangle/Shiv engine: use massive card draw and Swift cards to build explosive burst turns with Strangle and Shivs, while utilizing Retain and persistent block to survive off-turns. Prioritize consistent block scaling and setup pieces, avoiding raw attacks that clutter the deck.
### F46
- [hand_select] Prioritizing skills and draw over basic strikes to set up the scaling engine.
- [hand_select] Tools of the Trade draw/discard triggered. Clearing space and mitigating damage from Burns.
- [hand_select] Prioritize surviving the 40 damage hit. Leg Sweep + Backflip + Survivor is the goal.
- [hand_select] Enemy is at low HP (31) and not attacking this turn. I should focus on cycling to my damage cards (Shivs) while mitigating the Burn damage.
- [card_reward] Committed Shiv/Strangle plan: setup Phantom Blades, Strangle, and Infinite Blades early, then rapid cycle for massive burst damage and passive Strangle procs. Retain Shivs for key burst turns.
### F47
- [rest_site] Committed Strangle/Shiv engine: play Strangle on turns with massive card draw/shiv generation for lethal burst damage, while using Swift block cards and Retain mechanics to survive. Need consistent draw to reliably pair Strangle with Storm of Steel or Leading Strike.
### F48
- [card_select] Committed shiv plan: rely on Phantom Blades and Up My Sleeve+ for damage scaling, support with draw and dexterity. Prioritize block and scaling setup in early turns, avoid off-plan poison cards.
- [hand_select] Prioritizing survival with Piercing Wail while setting up a massive Shiv hand.
- [hand_select] Discarding Strike to keep cards that offer better value/scaling for the kill.

### Combat Decision Digest (23 combats)
F2 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (S) (6R, HP 56->56, loss=0, WIN)
  R1[Leaf Slime (S): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Twig Slime (S): Atk(4)]: Fasten(power:+Fasten(5))->Strike(6dmg)->Strike->Neutralize(3dmg,1+Weak(1)) | dealt=14 taken=0
  R2[Leaf Slime (S): Atk(3)+Leaf Slime (M): Atk(8)]: Defend(+10blk)->Defend(+10blk)->Strike(6dmg) | dealt=6 taken=0
  R3[Leaf Slime (S): StatusCard(1)+Leaf Slime (M): StatusCard(2)]: Strike->Strike(6dmg) | dealt=11 taken=0
  R4[Leaf Slime (M): Atk(8)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Defend(+10blk) | dealt=15 taken=0
  R5[Leaf Slime (M): StatusCard(2)]: Strike(6dmg)->Slimed(exhaust:1)->Slimed | dealt=6 taken=0
  R6[Leaf Slime (M): Atk(8)]: Neutralize(3dmg,1+Weak(1))->Strike(power:-Fasten) | dealt=3 taken=0

F3 [monster] Shrinker Beetle (5R, HP 56->56, loss=0, WIN)
  R1[Shrinker Beetle: DebuffStrong]: Fasten(power:+Fasten(5))->Strike(6dmg)->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=15 taken=0
  R2[Shrinker Beetle: Atk(7)]: Defend(+10blk)->Strike(4dmg)->Strike(4dmg) | dealt=8 taken=0
  R3[Shrinker Beetle: Atk(13)]: Defend(+10blk)->Defend(+10blk)->Strike(4dmg) | dealt=4 taken=0
  R4[Shrinker Beetle: Atk(7)]: Neutralize(2dmg,1+Weak(1))->Defend(+10blk)->Follow Through(4dmg)->Strike(4dmg) | dealt=10 taken=0
  R5[Shrinker Beetle: Atk(13)]: Strike(power:-Fasten,power:-Shrink) | dealt=0 taken=0

F4 [monster] Fuzzy Wurm Crawler (5R, HP 56->55, loss=1, WIN)
  R1[Fuzzy Wurm Crawler: Atk(4)]: Defend(+5blk)->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Strike(6dmg) | dealt=17 taken=0
  R2[Fuzzy Wurm Crawler: Buff]: Neutralize(3dmg,1+Weak(1))->Fasten(power:+Fasten(5)) | dealt=3 taken=0
  R3[Fuzzy Wurm Crawler: Atk(11)]: Defend(+10blk)->Follow Through(7dmg)->Strike(6dmg) | dealt=13 taken=1
  R4[Fuzzy Wurm Crawler: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Defend(+10blk) | dealt=3 taken=0
  R5[Fuzzy Wurm Crawler: Buff]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike(6dmg)->Strike(power:-Fasten) | dealt=17 taken=0

F5 [monster] Mawler (4R, HP 55->54, loss=1, WIN)
  R1[Mawler: Atk(4x2=8)]: Strangle(8dmg,1+Strangle(2))->Leading Strike(5dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Survivor(+8blk) | dealt=25 taken=0
  R2[Mawler: Atk(14)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Mawler: Atk(4x2=8)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=15 taken=1
  R4[Mawler: Atk(14)]: Strangle(8dmg,1+Strangle(2))->Strike | dealt=28 taken=0

F6 [monster] Fogmog (5R, HP 54->43, loss=11, WIN)
  R1[Fogmog: Summon]: Strangle(8dmg,1+Strangle(2))->Leading Strike(5dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Strike(8dmg) | dealt=33 taken=0
  R2[Eye With Teeth: StatusCard(3)+Fogmog: Atk(8), Buff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=9 taken=0
  R3[Eye With Teeth: StatusCard(3)+Fogmog: Atk(15)]: Follow Through(7dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=7 taken=2
  R4[Eye With Teeth: StatusCard(3)+Fogmog: Atk(9), Buff]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike(6dmg)->Strike(6dmg) | dealt=23 taken=9
  R5[Eye With Teeth: StatusCard(3)+Fogmog: Atk(16)]: Strangle(6dmg) | dealt=0 taken=0

F8 [monster] multi:Fuzzy Wurm Crawler+Shrinker Beetle (7R, HP 43->43, loss=0, WIN)
  R1[Shrinker Beetle: DebuffStrong+Fuzzy Wurm Crawler: Atk(4)]: Follow Through(14dmg)->Strangle+(10dmg,1+Strangle(3))->Defend(3dmg,+5blk) | dealt=27 taken=0
  R2[Shrinker Beetle: Atk(7)+Fuzzy Wurm Crawler: Buff]: Fasten(power:+Fasten(5))->Defend(+10blk)->Leading Strike(2dmg)->Shiv(2dmg,exhaust:1)->Shiv(2dmg) | dealt=6 taken=0
  R3[Shrinker Beetle: Atk(13)+Fuzzy Wurm Crawler: Atk(11)]: Strike(4dmg)->Neutralize(power:-Shrink)->Defend(+10blk)->Survivor(+8blk) | dealt=5 taken=0
  R4[Fuzzy Wurm Crawler: Atk(11)]: Strangle+(10dmg,1+Strangle(3))->Defend(3dmg,+10blk)->Survivor(+8blk) | dealt=13 taken=0
  R5[Fuzzy Wurm Crawler: Buff]: Infinite Blades(power:+Infinite Blades(1))->Follow Through(7dmg)->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=16 taken=0
  R6[Fuzzy Wurm Crawler: Atk(18)]: Defend(+10blk)->Defend(+10blk)->Strike(6dmg)->Shiv(4dmg) | dealt=10 taken=0
  R7[Fuzzy Wurm Crawler: Atk(18)]: Shiv(4dmg)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(power:-Fasten,power:-Infinite Blades) | dealt=11 taken=0

F11 [monster] Vine Shambler (4R, HP 43->43, loss=0, WIN)
  R1[Vine Shambler: Atk(6x2=12)]: Strangle+(10dmg,1+Strangle(3))->Leading Strike(6dmg)->Shiv(7dmg,exhaust:1)->Shiv(7dmg)->Survivor(+8blk) | dealt=30 taken=0
  R2[Vine Shambler: Atk(5), CardDebuff]: Adrenaline+(+2energy,exhaust:1)->Fasten(power:+Fasten(5))->Infinite Blades(power:+Infinite Blades(1))->Strike(6dmg)->Defend(+10blk)->Defend(+10blk) | dealt=6 taken=0
  R3[Vine Shambler: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Defend(+10blk)->Shiv(4dmg) | dealt=7 taken=0
  R4[Vine Shambler: Atk(4x2=8)]: Shiv(4dmg)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(power:-Fasten,power:-Infinite Blades) | dealt=11 taken=0

F14 [elite] Bygone Effigy (4R, HP 56->43, loss=13, WIN)
  R1[Bygone Effigy: Sleep]: Neutralize(3dmg,1+Weak(1))->Fasten(power:+Fasten(5))->Predator(18dmg,power:+Draw Cards Next Turn(2)) | dealt=21 taken=0
  R2[Bygone Effigy: Buff]: Adrenaline+(+2energy,exhaust:1)->Strangle+(11dmg,1+Strangle(3))->Leading Strike(6dmg)->Shiv(8dmg,exhaust:1)->Infinite Blades(3dmg,power:+Infinite Blades(1))->Strike(12dmg)->Strike(12dmg) | dealt=62 taken=0
  R3[Bygone Effigy: Atk(23)]: Defend(+10blk)->Shiv(4dmg)->Strike(7dmg)->Strike(7dmg) | dealt=18 taken=13
  R4[Bygone Effigy: Atk(23)]: Strangle+(10dmg,1+Strangle(3))->Neutralize(6dmg,1+Weak(1))->Leading Strike(6dmg)->Shiv(power:-Fasten,power:-Infinite Blades) | dealt=22 taken=0

F15 [monster] multi:Inklet+Inklet+Inklet (3R, HP 43->43, loss=0, WIN)
  R1[Inklet: Atk(3)+Inklet: Atk(2x3=6)+Inklet: Atk(3)]: Neutralize->Follow Through->Strike->Survivor(+8blk) | dealt=0 taken=0
  R2[Inklet: Atk(10)+Inklet: Atk(10)]: Strangle+->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Inklet: Atk(3)]: Leading Strike(1dmg,1-Slippery)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Strike | dealt=9 taken=0

F17 [boss] multi:Kin Follower+Kin Follower+Kin Priest (6R, HP 64->32, loss=32, WIN)
  R1[Kin Follower: Buff+Kin Follower: Atk(5)+Kin Priest: Atk(8), Debuff]: Infinite Blades(power:+Infinite Blades(1))->Predator(17dmg,power:+Draw Cards Next Turn(2)) | dealt=17 taken=13
  R2[Kin Follower: Atk(7)+Kin Follower: Atk(2x2=4)+Kin Priest: Atk(8), Debuff]: Adrenaline+(+2energy,exhaust:1)->Strangle+(12dmg,1+Strangle(3))->Shiv(9dmg,exhaust:1)->Backflip(3dmg,+3blk)->Follow Through(21dmg)->Strike(11dmg)->Survivor(+6blk) | dealt=56 taken=10
  R3[Kin Follower: Atk(4x2=8)+Kin Follower: Buff+Kin Priest: Atk(3x3=9)]: Fasten(power:+Fasten(5))->Predator(12dmg,power:+Draw Cards Next Turn(2))->Neutralize(3dmg,1+Weak(1))->Shiv(4dmg) | dealt=19 taken=2
  R4[Kin Follower: Buff+Kin Follower: Atk(7)+Kin Priest: Buff]: Strangle+(12dmg,1+Strangle(3))->Follow Through(21dmg)->Shiv(9dmg)->Defend(3dmg,+10blk) | dealt=45 taken=0
  R5[Kin Follower: Atk(9)+Kin Follower: Atk(4x2=8)+Kin Priest: Atk(10), Debuff]: Defend(+10blk)->Defend(+10blk)->Leading Strike(5dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg) | dealt=23 taken=7
  R6[Kin Follower: Atk(6x2=12)+Kin Follower: Buff+Kin Priest: Atk(10), Debuff]: Follow Through(18dmg)->Strike(8dmg)->Shiv(power:-Strength,power:-Infinite Blades,power:-Fasten,power:-Frail) | dealt=26 taken=0

F19 [monster] Tunneler (5R, HP 62->62, loss=0, WIN)
  R1[Tunneler: Atk(13)]: Suppress(11dmg,1+Weak(3))->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Defend(+5blk)->Defend(+5blk) | dealt=22 taken=0
  R2[Tunneler: Buff, Defend]: Fasten(power:+Fasten(5))->Backflip(+5blk)->Follow Through(7dmg) | dealt=7 taken=0
  R3[Tunneler: Atk(17)]: Adrenaline+(+2energy,exhaust:1)->Strangle+(1+Strangle(3))->Predator(3dmg,power:+Draw Cards Next Turn(2))->Defend(3dmg,+10blk)->Defend(3dmg,+10blk) | dealt=9 taken=0
  R4[Tunneler: Atk(23)]: Suppress(4dmg,2+Weak(3),-Burrowed)->Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=22 taken=0
  R5[Tunneler: Atk(9)]: Strangle+(10dmg,1+Strangle(3))->Leading Strike(6dmg)->Shiv(7dmg)->Shiv(power:-Fasten) | dealt=23 taken=0

F24 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (5R, HP 70->56, loss=14, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Suppress->Backflip(+5blk)->Phantom Blades(power:+Phantom Blades(9))->Survivor(+8blk) | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(10)]: Predator(9dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=9 taken=13
  R3[Exoskeleton: Buff+Exoskeleton: Atk(2x3=6)+Exoskeleton: Buff]: Adrenaline+(+2energy,exhaust:1)->Strangle+(9dmg,1+Strangle(3))->Follow Through(3dmg)->Strike(3dmg)->Fasten(power:+Fasten(5),2-Strength,-Strangle)->Strike(6dmg) | dealt=21 taken=0
  R4[Exoskeleton: Atk(3x3=9)]: Purity->Predator(9dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=9 taken=1
  R5[Exoskeleton: Atk(10)]: Strangle+(9dmg,1+Strangle(3))->Strike(power:-Phantom Blades,power:-Fasten) | dealt=9 taken=0

F28 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (6R, HP 61->61, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Adrenaline+(+2energy,exhaust:1)->Suppress+(25dmg,1+Weak(5))->Phantom Blades(power:+Phantom Blades(9))->Leading Strike(4dmg)->Shiv(exhaust:1)->Escape Plan(+3blk)->Predator(22dmg,power:+Draw Cards Next Turn(2))->Shiv(6dmg)->Storm of Steel | dealt=74 taken=0
  R2[Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Follow Through(10dmg)->Shiv->Backflip(+5blk)->Fasten(power:+Fasten(5)) | dealt=13 taken=0
  R3[Slumbering Beetle: Sleep]: Infinite Blades(power:+Infinite Blades(1))->Defend(+10blk) | dealt=0 taken=0
  R4[Slumbering Beetle: Atk(16), Buff]: Purity->Backflip(+5blk)->Deflect(+4blk)->Defend(+10blk) | dealt=0 taken=0
  R5[Slumbering Beetle: Atk(18), Buff]: Defend(+10blk)->Defend(+10blk)->Leading Strike(3dmg)->Shiv(13dmg)->Shiv(4dmg) | dealt=20 taken=0
  R6[Slumbering Beetle: Atk(20), Buff]: Strangle+(10dmg,1+Strangle(3))->Suppress+(20dmg,1+Weak(5))->Follow Through(17dmg)->Shiv(16dmg)->Shiv(power:-Phantom Blades,power:-Fasten,power:-Infinite Blades) | dealt=63 taken=0

F29 [monster] The Obscura (3R, HP 61->46, loss=15, WIN)
  R1[The Obscura: Summon]: Escape Plan(+3blk)->Suppress+(25dmg,1+Weak(5))->Follow Through(20dmg)->Strike(9dmg)->Storm of Steel->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Shiv(6dmg) | dealt=72 taken=0
  R2[Parafright: Atk(16)+The Obscura: Atk(7)]: Adrenaline+(+2energy,exhaust:1)->Fasten(power:+Fasten(5))->Infinite Blades(power:+Infinite Blades(1))->Phantom Blades(power:+Phantom Blades(9))->Survivor(+8blk) | dealt=0 taken=15
  R3[Parafright: Atk(16)+The Obscura: Buff]: Strangle+(10dmg,1+Strangle(3))->Leading Strike(6dmg)->Shiv(16dmg)->Shiv(7dmg)->Shiv(7dmg)->Strike(21dmg) | dealt=46 taken=0

F30 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (6R, HP 46->39, loss=7, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Suppress+(9dmg,1+Weak(5))->Strangle+->Leading Strike(4dmg)->Shiv(6dmg,exhaust:1)->Shiv(1-Weak)->Purity->Defend(+5blk) | dealt=19 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Atk(3x3=9)]: Backflip(+5blk)->Deflect+(+7blk)->Defend(+5blk)->Phantom Blades(power:+Phantom Blades(9)) | dealt=0 taken=0
  R3[Exoskeleton: Buff+Exoskeleton: Atk(10)]: Escape Plan(+3blk)->Fasten(power:+Fasten(5)) | dealt=0 taken=7
  R4[Exoskeleton: Atk(10)+Exoskeleton: Buff]: Leg Sweep(+11blk)->Infinite Blades(power:+Infinite Blades(1)) | dealt=0 taken=0
  R5[Exoskeleton: Buff+Exoskeleton: Atk(12)]: Adrenaline+(+2energy,exhaust:1)->Backflip(+5blk)->Escape Plan(+3blk)->Defend(+10blk)->Shiv(9dmg)->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=21 taken=0
  R6[Exoskeleton: Atk(5x3=15)+Exoskeleton: Buff]: Follow Through->Strangle+->Shiv(6dmg,1+Strangle(3))->Strike(power:-Phantom Blades,power:-Fasten,power:-Infinite Blades) | dealt=6 taken=0

F31 [monster] Spiny Toad (6R, HP 39->39, loss=0, WIN)
  R1[Spiny Toad: Buff]: Suppress+(25dmg,1+Weak(5))->Phantom Blades(power:+Phantom Blades(9))->Predator(22dmg,power:+Draw Cards Next Turn(2)) | dealt=47 taken=0
  R2[Spiny Toad: Atk(17)]: Escape Plan->Purity->Piercing Wail+(2+Strength(-8),+Piercing Wail(8),exhaust:1)->Leg Sweep(+11blk,1Weak(4→6)) | dealt=0 taken=0
  R3[Spiny Toad: Atk(12)]: Strangle+(10dmg,1+Strangle(3))->Defend(3dmg,+5blk)->Survivor(+8blk) | dealt=13 taken=0
  R4[Spiny Toad: Buff]: Adrenaline+(+2energy,exhaust:1)->Infinite Blades(power:+Infinite Blades(1))->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R5[Spiny Toad: Atk(17)]: Escape Plan(+3blk)->Survivor(+8blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R6[Spiny Toad: Atk(12)]: Follow Through(14dmg)->Suppress+(17dmg,1Weak(2→7))->Shiv(power:-Phantom Blades,power:-Infinite Blades) | dealt=31 taken=0

F33 [boss] The Insatiable (11R, HP 60->14, loss=46, WIN)
  R1[The Insatiable: Buff, StatusCard(6)]: Strangle+(15dmg,1+Strangle(3))->Suppress+(28dmg,1+Weak(5))->Phantom Blades(3dmg,power:+Phantom Blades(9))->Escape Plan(3dmg)->Fasten(3dmg,power:+Fasten(5)) | dealt=52 taken=0
  R2[The Insatiable: Atk(6x2=12)]: Purity->Leg Sweep(+11blk,1Weak(4→6))->Follow Through(7dmg) | dealt=7 taken=1
  R3[The Insatiable: Atk(21)]: Deflect+(+7blk)->Defend(+10blk)->Frantic Escape(1Sandpit(3→4))->Frantic Escape(1Sandpit(4→5))->Predator(15dmg,power:+Draw Cards Next Turn(2)) | dealt=15 taken=4
  R4[The Insatiable: Buff]: Adrenaline+(+2energy,exhaust:1)->Infinite Blades(power:+Infinite Blades(1))->Leading Strike+(6dmg)->Shiv(13dmg,exhaust:1)->Shiv(4dmg)->Backflip(+5blk)->Frantic Escape(1Sandpit(4→5)) | dealt=23 taken=0
  R5[The Insatiable: Atk(7x2=14)]: Defend(+10blk)->Leading Strike(3dmg)->Shiv(13dmg)->Shiv(4dmg)->Shiv(4dmg)->Storm of Steel->Shiv(4dmg)->Shiv(4dmg) | dealt=32 taken=4
  R6[The Insatiable: Atk(7x2=14)]: Escape Plan(+3blk)->Shiv(13dmg)->Frantic Escape(1Sandpit(3→4))->Defend(+10blk) | dealt=13 taken=1
  R7[The Insatiable: Atk(22)]: Follow Through(14dmg)->Suppress+(17dmg,1Weak(1→6))->Shiv(13dmg)->Frantic Escape(1Sandpit(3→4))->Strike(6dmg) | dealt=50 taken=22
  R8[The Insatiable: Buff]: Strangle+(10dmg,1+Strangle(3))->Shiv(16dmg)->Frantic Escape(3dmg,1Sandpit(3→4))->Defend(3dmg,+10blk) | dealt=32 taken=0
  R9[The Insatiable: Atk(9x2=18)]: Deflect+(+7blk)->Defend(+10blk)->Predator(15dmg,power:+Draw Cards Next Turn(2))->Shiv(13dmg) | dealt=28 taken=1
  R10[The Insatiable: Atk(9x2=18)]: Follow Through(14dmg)->Leading Strike+(6dmg)->Defend(+10blk)->Deflect+(+7blk)->Shiv(13dmg)->Shiv(4dmg)->Shiv(4dmg) | dealt=53 taken=13
  R11[The Insatiable: Atk(24)]: Shiv(13dmg)->Backflip(+5blk)->Strike(power:-Phantom Blades,power:-Fasten,power:-Infinite Blades) | dealt=13 taken=0

F35 [monster] multi:Living Shield+Turret Operator (2R, HP 58->58, loss=0, WIN)
  R1[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Follow Through(20dmg)->Suppress+(25dmg,1+Weak(5))->Purity->Adrenaline+(+2energy,exhaust:1)->Leading Strike+(9dmg)->Shiv(exhaust:1)->Shiv->Leg Sweep(+11blk,1+Weak(2))->Tools of the Trade(power:+Tools of the Trade(1)) | dealt=55 taken=0
  R2[Turret Operator: Atk(2x5=10)]: Deflect+(+7blk)->Strangle+(10dmg,1+Strangle(3))->Escape Plan(3dmg,+3blk)->Leading Strike(6dmg)->Shiv(7dmg)->Shiv(7dmg)->Storm of Steel(3dmg)->Shiv(power:-Tools of the Trade) | dealt=36 taken=0

F36 [monster] Devoted Sculptor (3R, HP 58->57, loss=1, WIN)
  R1[Devoted Sculptor: Buff]: Suppress+(25dmg,1+Weak(5))->Leading Strike+(9dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Deflect+(+7blk)->Storm of Steel->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg) | dealt=100 taken=0
  R2[Devoted Sculptor: Atk(9)]: Adrenaline+(+2energy,exhaust:1)->Escape Plan->Escape Plan+->Infinite Blades(power:+Infinite Blades(1))->Tools of the Trade(power:+Tools of the Trade(1))->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=17 taken=1
  R3[Devoted Sculptor: Atk(15)]: Strangle+(10dmg,1+Strangle(3))->Suppress+(20dmg,1Weak(3→8))->Follow Through(10dmg)->Shiv(power:-Infinite Blades,power:-Tools of the Trade) | dealt=40 taken=0

F38 [monster] multi:Cubex Construct+Cubex Construct+Punch Construct (5R, HP 62->56, loss=6, WIN)
  R1[Punch Construct: Defend+Cubex Construct: Buff+Cubex Construct: Buff]: Suppress+->Strangle+->Leading Strike->Shiv(exhaust:1)->Shiv->Purity->Storm of Steel->Shiv*2 | dealt=0 taken=0
  R2[Punch Construct: Atk(14)+Cubex Construct: Atk(9), Buff]: Escape Plan+->Escape Plan->Phantom Blades(power:+Phantom Blades(9))->Strike(6dmg)->Defend(+5blk)->Up My Sleeve+->Shiv(13dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Deflect+(+7blk)->Defend(+5blk) | dealt=31 taken=6
  R3[Punch Construct: Atk(5x2=10), Debuff+Cubex Construct: Atk(11), Buff]: Adrenaline+(+2energy,exhaust:1)->Escape Plan+(+5blk)->Leading Strike+(6dmg)->Shiv(13dmg)->Shiv(4dmg)->Predator(power:+Draw Cards Next Turn(2))->Blur+(+8blk,power:+Blur(1))->Tools of the Trade(power:+Tools of the Trade(1)) | dealt=34 taken=0
  R4[Punch Construct: Defend]: Escape Plan(+3blk)->Fasten(power:+Fasten(5))->Infinite Blades(power:+Infinite Blades(1))->Suppress+(12dmg,1+Weak(5))->Up My Sleeve+->Shiv(9dmg)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg) | dealt=30 taken=0
  R5[Punch Construct: Atk(10)]: Strangle+(1+Strangle(3))->Follow Through(17dmg)->Shiv(power:-Phantom Blades,power:-Tools of the Trade,power:-Fasten,power:-Infinite Blades) | dealt=17 taken=0

F44 [monster] Fabricator (2R, HP 70->70, loss=0, WIN)
  R1[Fabricator: Summon]: Suppress+(25dmg,1+Weak(5))->Strangle+(15dmg,1+Strangle(3))->Defend+(3dmg,+9blk)->Defend(3dmg,+6blk)->Adrenaline+(3dmg,+2energy,exhaust:1)->Deflect+(3dmg,+8blk)->Blur+(3dmg,+9blk,power:+Blur(1))->Storm of Steel(3dmg)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg) | dealt=130 taken=0
  R2[Noisebot: StatusCard(2)+Zapbot: Atk(16)+Fabricator: Summon]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Leading Strike+(6dmg)->Shiv(power:-Dexterity) | dealt=17 taken=0

F46 [elite] Mecha Knight (9R, HP 70->45, loss=25, WIN)
  R1[Mecha Knight: Atk(25)]: Tools of the Trade+(power:+Tools of the Trade(1))->Suppress+(17dmg,1Artifact(2→1))->Escape Plan+->Strangle+(10dmg,1-Artifact)->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Defend(+6blk) | dealt=38 taken=19
  R2[Mecha Knight: StatusCard(4)]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Blur+(+9blk,power:+Blur(1)) | dealt=15 taken=0
  R3[Mecha Knight: Defend, Buff]: Follow Through(14dmg)->Purity+->Phantom Blades(power:+Phantom Blades(9),exhaust:1)->Escape Plan(+4blk)->Strike(6dmg) | dealt=20 taken=0
  R4[Mecha Knight: Atk(40)]: Backflip(+6blk)->Leg Sweep(+12blk,1+Weak(2)) | dealt=0 taken=2
  R5[Mecha Knight: StatusCard(4)]: Adrenaline+(+2energy,exhaust:1)->Suppress+(25dmg,1Weak(1→6))->Purity->Deflect+(+8blk)->Strangle+(15dmg,1+Strangle(3))->Fasten(3dmg,power:+Fasten(5))->Backflip(3dmg,+6blk)->Escape Plan(3dmg)->Leading Strike(7dmg)->Shiv(22dmg)->Shiv(9dmg)->Storm of Steel(3dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg) | dealt=135 taken=0
  R6[Mecha Knight: Defend, Buff]: Follow Through(20dmg)->Escape Plan+->Predator(22dmg,power:+Draw Cards Next Turn(2)) | dealt=42 taken=0
  R7[Mecha Knight: Atk(33)]: Leading Strike+->Shiv(13dmg)->Shiv(6dmg)->Defend+(+14blk)->Defend(+11blk) | dealt=19 taken=4
  R8[Mecha Knight: StatusCard(4)]: Escape Plan(+4blk)->Infinite Blades(power:+Infinite Blades(1))->Strike(6dmg)->Deflect+(+8blk) | dealt=6 taken=0
  R9[Mecha Knight: Defend, Buff]: Follow Through(14dmg)->Shiv(power:-Dexterity,power:-Tools of the Trade,power:-Phantom Blades,power:-Fasten,power:-Infinite Blades) | dealt=14 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (11R, HP 66->0, loss=66, LOSS)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Suppress+(25dmg,1+Weak(5))->Tools of the Trade+(power:+Tools of the Trade(1))->Phantom Blades(power:+Phantom Blades(9))->Infinite Blades+(power:+Infinite Blades(1))->Blur+(+9blk,power:+Blur(1)) | dealt=25 taken=4
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Survivor(+9blk)->Adrenaline+(+2energy,exhaust:1)->Fasten(power:+Fasten(5))->Escape Plan+(+6blk)->Shiv(13dmg,exhaust:1)->Backflip(+6blk)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Storm of Steel->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg) | dealt=48 taken=0
  R3[Torch Head Amalgam: Atk(9x3=27)+Queen: Buff, Defend]: Strangle+(7dmg,1+Strangle(3))->Piercing Wail+(3dmg,2+Strength(-8),+Piercing Wail(8),2+Strength(-8),+Piercing Wail(8),exhaust:1)->Leading Strike+(7dmg)->Shiv(12dmg)->Shiv(6dmg) | dealt=35 taken=0
  R4[Torch Head Amalgam: Atk(16)+Queen: Buff, Defend]: Up My Sleeve+->Untouchable(+5blk)->Infinite Blades(power:Infinite Blades(1→2))->Shiv*3 | dealt=0 taken=3
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Strangle+(1+Strangle(3))->Defend+(3dmg,+10blk)->Defend(3dmg,+8blk)->Shiv(3dmg)->Shiv(3dmg)->Shiv(5dmg)->Shiv(6dmg) | dealt=23 taken=0
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Piercing Wail+(2Strength(3→-5),+Piercing Wail(8),2+Strength(-8),+Piercing Wail(8),exhaust:1)->Defend(+8blk)->Shiv->Backflip(+4blk)->Suppress+(12dmg,1+Weak(5)) | dealt=12 taken=0
  R7[Torch Head Amalgam: Atk(20)+Queen: Buff, Defend]: Shiv->Escape Plan+->Deflect+(+6blk)->Escape Plan(+3blk)->Defend(+8blk)->Predator(power:+Draw Cards Next Turn(2))->Untouchable | dealt=0 taken=0
  R8[Torch Head Amalgam: Atk(21)+Queen: Buff, Defend]: Defend+(+10blk)->Shiv*3 | dealt=0 taken=6
  R9[Torch Head Amalgam: Atk(15x3=45)+Queen: Buff, Defend]: Escape Plan+(+4blk)->Purity->Defend(+8blk)->Leg Sweep(+9blk,1Weak(2→4)) | dealt=0 taken=24
  R10[Torch Head Amalgam: Atk(23)+Queen: Buff, Defend]: Up My Sleeve+->Shiv*4 | dealt=0 taken=23
  R11[Torch Head Amalgam: Atk(24)+Queen: Buff, Defend]: Suppress+(12dmg,1Weak(2→7))->Shiv(9dmg)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg)->Shiv(3dmg) | dealt=36 taken=0

### Non-combat Decisions (199 decisions)
F1 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Cursed Pearl gives an Eternal curse, which permanently hinders draw consistency and cannot be removed. Booming Conch only helps in Elite combats. Lead Paperweight offers a colorless card which provides a safe, immediate boost to our starting deck without long-term drawbacks.
  strategic_note: Foundation phase: Looking for high-damage attacks to clear Act 1 elites and block scaling. Play safe and prioritize upgrades at rest sites.

F1 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->14
  deck_change: added Fasten
  reasoning: Fasten provides permanent defensive scaling by buffing our 5 starting Defends. While we need damage early, Discovery is too RNG-reliant and costs 1 Energy just to generate a random free card. Fasten gives us massive block value that will stay relevant for the entire run.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting the Act 1 hallway chain to secure front-loaded damage and block cards before the first elite. This follows the Route Intelligence recommendation to farm early monsters.
  strategic_note: Foundation phase: prioritized drafting high-impact front-loaded damage and draw/discard pieces to handle Act 1 elites. Focusing on building a consistent deck through early hallway fights while maintaining enough HP to upgrade at rest sites.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 108->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Beetle Juice

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 108->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 56->56 | Gold 108->108 | Deck 14->15
  deck_change: picked Follow Through
  reasoning: Our deck severely lacks damage right now, having only base Strikes and Neutralize. Follow Through provides frontloaded damage, which is crucial for early Act 1 elites. Thanks to Ring of the Snake, we often have enough cards in hand on turn 1 to trigger its double-hit condition for 14 damage.
  strategic_note: Foundation plan: prioritize high-impact damage attacks to survive Act 1 elites while we search for a scaling engine. Avoid adding too many skills until our damage is sufficient.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 108->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Unknown

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 108->115 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 115->115 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 56->56 | Gold 115->115 | Deck 15->16
  deck_change: picked Leading Strike
  reasoning: Leading Strike provides excellent early frontload damage (11 damage for 1 energy across 3 hits) while planting the seeds for a Shiv-based scaling engine. It is more efficient than Pounce and scales incredibly well with future relic and card synergies like Accuracy, Shuriken, or Nunchaku.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; lean towards Shiv synergies given our early picks. Take cheap draw or high-impact damage, skip narrow synergies until an engine piece is secured.

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 115->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 115->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 129->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Fire Potion

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 129->129 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 55->55 | Gold 129->129 | Deck 16->17
  deck_change: picked Strangle
  reasoning: Strangle provides massive scaling for multi-play strategies. We already have Leading Strike to generate Shivs, and Strangle will rapidly scale our burst damage to burst down Act 1 threats and elites. Abrasive is too inconsistent right now with only Survivor as a discard outlet.
  strategic_note: Committed to multi-play/Shiv engine: rely on Strangle and Shiv generation for damage scaling. Prioritize 0-cost attacks, cheap draw, and multi-play payoffs. Skip poison and slow, expensive powers.

F4 [map] choose_map_node (option_index=0) | source=llm
  HP 55->55 | Gold 129->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the strategy of early hallway farming (Node 4 of 5-6 total) to secure front-loaded damage and block before the mid-act elites. HP is currently healthy (79%), making a combat preferable over an Unknown node to guarantee a card reward.
  strategic_note: Foundation phase: prioritizing hallway fights for front-loaded damage (Dagger Throw, Poisoned Stab) and defensive consistency (Acrobatics, Backflip) to handle Act 1 elites. I will delay the first elite until late act and prioritize upgrades over resting to secure long-term scaling.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 129->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 54->54 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: The current deck is leaning towards a Shiv/Attack strategy with Strangle and Leading Strike. Dodge and Roll is weak without Dexterity, Deadly Poison hybridizes our damage engine unnecessarily, and Prepared is hand-size negative without upgrades or discard synergies. Skipping keeps the deck lean to draw our core damage cards more frequently.
  strategic_note: Foundation phase: Build around Strangle and Shivs for burst damage. Skip poison and narrow synergies. Look for more 0-cost cards, card draw, and reliable multi-hit attacks.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 143->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 143->155 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 155->155 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Swift Potion

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 155->155 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 43->43 | Gold 155->155 | Deck 17->18
  deck_change: picked Infinite Blades
  reasoning: Infinite Blades perfectly aligns with our Strangle, providing a continuous stream of 0-cost cards to trigger its passive damage effect while slowly building into a dedicated Shiv scaling engine.
  strategic_note: Committed shiv/strangle plan: use Strangle, Leading Strike, and Infinite Blades to overwhelm enemies with many card plays. Need card draw, burst shiv generation, and efficient mitigation to support the engine. Skip poison and alternate archetypes.

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 155->155 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: RestSite

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 43->43 | Gold 155->155 | Deck 18->18
  deck_change: upgraded Strangle->Strangle+
  reasoning: With 43 HP and another Rest Site coming up on Floor 9, we are very safe to Smith. Upgrading Strangle significantly improves our single-target burst, synergizing perfectly with our low-cost cards and Shiv generation to melt high-HP Act 1 threats.
  strategic_note: Foundation phase: Building around Strangle and Shiv generation for burst damage. Play Strangle early in the turn, followed by 0-cost cards like Shivs and Neutralize to maximize HP loss. Need card draw (Acrobatics, Backflip) to fuel Strangle turns and more consistent block.

F7 [rest_site] proceed | source=auto
  HP 43->43 | Gold 155->155 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 155->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 155->166 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 166->166 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 43->43 | Gold 166->166 | Deck 18->19
  deck_change: picked Adrenaline
  reasoning: Adrenaline is a premium tempo tool that fits into any deck, but is exceptionally powerful with Strangle+, as it counts as a card play, generates energy, and draws more cards to trigger Strangle+ even more.
  strategic_note: Committed card spam/Shiv plan: use Strangle+ as the core damage engine, fueled by Shivs (Leading Strike, Infinite Blades) and free cycle (Adrenaline). Needs more Shiv generation, draw, and permanent scaling (Accuracy/Footwork); skip slow mechanics like poison.

F8 [map] choose_map_node (option_index=1) | source=llm
  HP 43->43 | Gold 166->166 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. At 43/70 HP, a Smith upgrade is preferable to strengthen the deck for the upcoming elite, but having the option to Rest if a bad combat occurs later is vital. Upgrading a key damage or block card now will reduce future chip damage.
  strategic_note: Foundation phase: prioritizing high-impact upgrades at rest sites to compensate for lack of elite-slaying burst. Seeking efficient block and draw-discard synergies to stabilize the mid-game while preserving HP for the Act 1 boss.

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=16) | source=llm
  HP 43->43 | Gold 166->166 | Deck 19->19
  deck_change: upgraded Adrenaline->Adrenaline+
  reasoning: HP is at 43/70 and the next node is a Treasure, so resting is unnecessary. Upgrading Adrenaline yields a massive power spike, providing an extra energy to play Strangle along with multiple attacks or setup powers on a crucial early turn.
  strategic_note: Foundation phase: Building around Strangle and Shiv generation. Play Strangle early, fueled by Adrenaline+ and 0-cost cards. Need more card draw to reliably assemble Strangle burst turns and better mitigation for consistency.

F9 [rest_site] proceed | source=auto
  HP 43->43 | Gold 166->166 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 166->166 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 43->43 | Gold 166->204 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 43->43 | Gold 204->204 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim: Tiny Mailbox

F10 [treasure] proceed | source=random
  HP 43->43 | Gold 204->204 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 204->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 204->212 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 212->212 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 43->43 | Gold 212->212 | Deck 19->20
  deck_change: picked Predator
  reasoning: Predator provides excellent upfront damage and crucial card draw for the next turn, which is extremely valuable for finding our Strangle+ and Shiv generators consistently.
  strategic_note: Committed to attack/Shiv multi-hit plan powered by Strangle+; prioritize card draw, cheap attacks, and direct burst scaling like Accuracy or Phantom Blades. Skip poison and heavy attacks.

F11 [map] choose_map_node (option_index=2) | source=llm
  HP 43->43 | Gold 212->212 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. This preserves HP and potentially provides a beneficial event before the upcoming Rest Site and Elite. With 43 HP, I am healthy enough to take the Elite at Node 13, but taking the Unknown first is safer than an immediate Elite or using a Rest Site too early.
  strategic_note: Foundation phase: prioritized high-damage attacks for Act 1 elites. Currently transitioning into finding consistent block and draw while maintaining enough health to aggressively upgrade at rest sites.

F12 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 43->35 | Gold 212->311 | Deck 20->20
  deck_change: no deck change
  reasoning: Trading 8 HP for 99 Gold is extremely high value. Although there are no shops left in Act 1, carrying over 300+ gold into Act 2 will allow us to buy powerful relics or card removals. We have enough HP (35 after the event) and a Rest Site before the boss to stabilize if needed.
  strategic_note: Foundation phase: Building around Strangle+ and Shiv generation, fueled by Adrenaline+ and 0-cost attacks. Prioritize card draw to consistently assemble Strangle turns and find better block mitigation. Avoid taking too much damage to allow upgrading at rest sites.

F12 [event] choose_event_option (option_index=0) | source=auto
  HP 35->35 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F12 [map] choose_map_node (option_index=1) | source=llm
  HP 35->35 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: With 35 HP and an Elite fight immediately following this node, the Rest Site is essential. It allows for a Heal to ensure survival against the Elite or a Smith to increase deck power if I feel confident. Taking an Unknown here is unnecessarily risky given the upcoming combat path.
  strategic_note: Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts before the Act 1 boss.

F13 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 35->56 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: Resting not only heals us up to 56 HP for the upcoming Elite, but also triggers Tiny Mailbox to generate 2 random potions. These potions will be crucial for taking down the Elite and ensuring we survive the rest of the Act smoothly.
  strategic_note: Foundation phase: Building around Strangle+ and Shiv generation. Use potions from Tiny Mailbox to burst down elites or sustain through tough fights while searching for more card draw to consistently trigger Strangle.

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F13 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 56->56 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F13 [rest_site] proceed | source=auto
  HP 56->56 | Gold 311->311 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 311->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Elite

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 311->337 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 337->337 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 337->337 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim relic: Planisphere

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 337->337 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 43->43 | Gold 337->337 | Deck 20->21
  deck_change: picked Leg Sweep
  reasoning: Leg Sweep is a premium defensive card that applies Weak and provides significant block in a single card, which is highly valuable for the Act 1 Boss and Act 2 hallways. Grand Finale requires too much deck manipulation, and I don't need another Follow Through.
  strategic_note: Committed to a Shiv/Strangle burst damage plan. Prioritize cheap card draw, energy generation, and efficient block to survive while setting up Strangle combos. Avoid adding heavy, non-synergistic attacks.

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 337->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Monster

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 337->352 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 352->352 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 43->43 | Gold 352->352 | Deck 21->22
  deck_change: picked Backflip
  reasoning: Backflip provides essential cycle to find our core engine pieces (Strangle, Infinite Blades) faster while adding some block. It also fuels Strangle on the turns we play it, as drawing 2 cards often yields more 0-cost options like Shivs.
  strategic_note: Committed Strangle/Shiv plan: setup Strangle and play as many cards as possible in a single turn. Prioritize cheap attacks, Shiv generators, and cycle (like Backflip) to maximize Strangle triggers. Needs efficient block and burst scaling; avoid slow poison or unrelated archetypes.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 352->352 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 43->64 | Gold 352->352 | Deck 22->22
  deck_change: no deck change
  reasoning: With Tiny Mailbox, resting generates 2 random potions which provides a massive power spike for the upcoming Act 1 Boss fight. Additionally, healing 21 HP puts us at a much safer 64/70 HP.
  strategic_note: Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts.

F16 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 352->352 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F16 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 64->64 | Gold 352->352 | Deck 22->22
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F16 [rest_site] proceed | source=auto
  HP 64->64 | Gold 352->352 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 64->64 | Gold 352->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 352->427 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 427->427 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 427->427 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 32->32 | Gold 427->427 | Deck 22->23
  deck_change: picked Storm of Steel
  reasoning: Storm of Steel perfectly fits our committed Strangle+ and Shiv trajectory. It converts dead draws into 0-cost Shivs, massively fueling Strangle's multi-play damage trigger. It provides excellent burst scaling and synergizes well with our high starting hand size from Ring of the Snake.
  strategic_note: Committed Strangle/Shiv multi-play plan. Fuel Strangle with 0-cost cards like Shivs generated from Storm of Steel, Leading Strike, and Infinite Blades. Prioritize cheap draw to find combo pieces and relics like Shuriken/Kunai to scale the multiple attacks. Avoid slow poison or heavy, expensive cards.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 32->62 | Gold 427->427 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 62->62 | Gold 427->427 | Deck 23->23
  deck_change: changed: +Suppress; -Neutralize
  reasoning: Archaic Tooth replaces our unupgraded Neutralize with Suppress, giving us an Innate, 0-cost source of 11 damage and 3 Weak. This provides a massive, guaranteed defensive and offensive spike on Turn 1 of every combat, which is invaluable for surviving Act 2 hallway fights. Since we have Ring of the Snake, the Innate draw cost is easily mitigated.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation, so we can focus on finding more card draw and defensive scaling to reliably set up our Strangle combo.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 62->62 | Gold 427->427 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=0) | source=llm
  HP 62->62 | Gold 427->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended path to engage a monster node. While the route guide suggests 'Absolute Pacifism' for Act 2, my deck currently lacks the defensive engine and card draw necessary to survive the boss. I need to take a few early hallway fights to draft Acrobatics, Calculated Gamble, or more block before pivoting to the non-combat nodes.
  strategic_note: Foundation phase: Strangle and Shiv scaling. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently hunting for Acrobatics and defensive consistency to safely set up Strangle bursts; will pivot to non-combat nodes once the draw engine is stabilized to leverage Planisphere healing.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 427->438 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 438->438 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 62->62 | Gold 438->438 | Deck 23->24
  deck_change: picked Phantom Blades
  reasoning: We are clearly moving into a Phase 2 committed Shiv/Strangle engine. Phantom Blades provides massive damage scaling (+9 to the first Shiv each turn) and its Retain effect allows us to stockpile Shivs from Infinite Blades and Leading Strike until we draw Strangle+, creating devastating burst turns.
  strategic_note: Committed Shiv/Strangle engine: stockpile Shivs using Phantom Blades' retain, then unleash them all on Strangle+ burst turns. Prioritize card draw to find the combo and block/weakness to survive while setting up. Skip poison and off-plan attacks.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 62->62 | Gold 438->438 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Shop

F20 [shop] buy_relic (option_index=1) | source=plan
  HP 62->62 | Gold 438->160 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan [1/3]: Provides immense Turn 1 consistency, allowing us to find our key setup pieces (Strangle, Phantom Blades, Suppress) and immediately bypass dead draws.

F20 [shop] buy_card (option_index=5) | source=plan
  HP 62->62 | Gold 160->76 | Deck 24->25
  deck_change: bought Purity
  reasoning: Shop plan [2/3]: Directly counters The Insatiable's Turn 1 status flood by retaining in hand and exhausting the statuses, or thinning out basic Strikes/Defends to cycle our Strangle+ faster.

F20 [shop] remove_card_at_shop | source=plan
  HP 62->62 | Gold 76->76 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan [3/3]: Removing a Strike increases the density of our Strangle+ engine and Shiv generators.

F20 [card_select] select_deck_card (option_index=0) | source=llm
  HP 62->62 | Gold 76->1 | Deck 25->24
  deck_change: lost Strike
  reasoning: Strikes are the weakest cards in the deck, providing minimal damage and actively impeding our ability to draw our core scaling pieces like Phantom Blades, Strangle, and Adrenaline.
  strategic_note: Committed to Shiv/multi-play scaling with Phantom Blades and Strangle. Prioritize playing powers early and retaining Shivs for Strangle burst turns. Remove Strikes aggressively and look for more cheap draw (Acrobatics) and defense.

F20 [shop] close_shop_inventory | source=llm
  HP 62->62 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F20 [shop] proceed | source=auto
  HP 62->62 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 62->67 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Unknown

F21 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 67->67 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Grabbing the Foul Potions provides massive economic value. Even if we have to discard one due to potion slots, holding onto them to sell to the Merchant for 100 Gold each is incredibly strong for setting up late-game relic or card purchases.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Use Foul Potions strictly for gold at merchants unless lethal AoE is absolutely necessary to survive a fight.

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 67->67 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Foul Potion

F21 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 67->67 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F21 [event] choose_event_option (option_index=0) | source=auto
  HP 67->67 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 67->70 | Gold 1->1 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Unknown

F22 [treasure] open_chest | source=random
  HP 70->70 | Gold 1->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Open chest

F22 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 70->70 | Gold 36->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim: Bag of Marbles

F22 [treasure] proceed | source=random
  HP 70->70 | Gold 36->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Proceed from treasure

F22 [map] choose_map_node (option_index=1) | source=llm
  HP 70->70 | Gold 36->36 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the Route Intelligence for 'Absolute Pacifism' in Act 2 to minimize attrition. Planisphere provides 5 HP heal per Unknown node, making this path extremely safe while preserving HP for upgrades at rest sites.
  strategic_note: Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns, utilizing Planisphere to sustain HP through Unknown nodes while hunting for defensive consistency and card draw.

F23 [event] choose_event_option (option_index=0) | source=llm
  HP 70->70 | Gold 36->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Taking a guaranteed 100 Gold with zero HP risk is a great outcome here, especially since we only have 36 Gold and need to build up funds for a future shop. While our deck is at full health and could likely handle the fight, avoiding unnecessary damage preserves our HP for the rest of the act.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Use Foul Potions strictly for gold at merchants unless lethal AoE is absolutely necessary to survive a fight.

F23 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 136->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F23 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 136->136 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Monster

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 136->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F24 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 56->56 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: We are on 3 energy and already have one Leg Sweep plus an innate Suppress for Weak application. Ricochet and Untouchable are both 2-cost cards that rely heavily on discard synergy (Sly), but our only repeatable discard outlets are Survivor and Storm of Steel (and Gambling Chip on turn 1). Adding them would bloat the deck with dead draws, slowing down our ability to find Strangle+ and Shiv generation.
  strategic_note: Committed Strangle/Shiv plan: setup Strangle+ early, then spam zero-cost cards (Shivs, Purity, Adrenaline) to trigger massive passive damage. Defend heavily on off-turns. Prioritize card draw and card removals to increase the density of zero-cost plays.

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 56->61 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Unknown

F25 [event] choose_event_option (option_index=0) | source=llm
  HP 61->61 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Taking the free choice of 5 random class cards gives us a high chance to find exactly what our deck needs (card draw, defensive consistency, or another combo piece) without costing any HP.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.

F25 [card_select] select_deck_card (option_index=3) | source=llm
  HP 61->61 | Gold 144->144 | Deck 24->25
  deck_change: added Escape Plan
  reasoning: Escape Plan is a 0-cost cycle card that helps us dig through the deck faster to find our crucial setup powers (Phantom Blades, Infinite Blades, Fasten). The occasional free block is a nice bonus.
  strategic_note: Committed Phantom Blades engine: prioritize cheap card draw to find setup powers early, remove basic Strikes, and rely on multi-hit attacks (Shivs, Storm of Steel, Follow Through) scaled by Phantom Blades for damage. Avoid alternate scaling archetypes.

F25 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 144->144 | Deck 25->25
  deck_change: no deck change
  reasoning: Only option: Proceed

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 144->144 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 61->61 | Gold 144->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim: Toxic Egg

F26 [treasure] proceed | source=random
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=1) | source=llm
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Following the recommended Absolute Pacifism route for Act 2 to minimize attrition. The Rest Site fulfills the mandatory quota and allows for a high-value upgrade since my current HP is high (87%).
  strategic_note: Foundation phase: Scaling through Strangle and Shiv generation. The deck relies on Adrenaline+ to kickstart high-card-play turns. Currently looking for additional card draw and defensive consistency to safely set up Strangle bursts.

F27 [rest_site] choose_rest_option (option_index=1, smith_card_index=18) | source=llm
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: upgraded Suppress->Suppress+
  reasoning: Missing only 9 HP makes resting highly inefficient right now. We have another Rest Site at F32 right before the boss to trigger Tiny Mailbox for potions. Smithing Suppress gives us 5 turns of Weak on turn 1 for 0 energy, providing massive, guaranteed mitigation for the remaining Act 2 fights.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress+ gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.

F27 [rest_site] proceed | source=auto
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 177->177 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Monster

F28 [card_select] select_deck_card (option_index=0) | source=llm
  HP 61->61 | Gold 177->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Bubble Bubble is useless with zero poison in the deck. Between Deflect and Anticipate, Deflect guarantees 4 block for 0 energy without requiring other block cards to be played, providing safe, immediate mitigation.
  strategic_note: Committed Strangle/Phantom Blades attack plan: hold cheap attacks and Retain cards for Strangle burst turns. Prioritize energy generation and card draw to set up powers quickly; avoid adding any poison cards.

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 177->187 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 187->187 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 61->61 | Gold 187->187 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 61->61 | Gold 187->187 | Deck 25->25
  deck_change: no deck change
  reasoning: None of the offered cards significantly advance our core Shiv/Strangle engine. Memento Mori is too clunky without Acrobatics/Prepared, as Storm of Steel discards it. Ricochet is often a dead draw at 2 cost without a discard outlet in the same hand. Skipping keeps the deck lean to draw into Phantom Blades, Strangle, and Infinite Blades faster.
  strategic_note: Committed Shiv/Strangle plan: Use Strangle+ and Phantom Blades for scaling burst damage via Shivs. Keep the deck lean to find powers/Strangle quickly. Prioritize removals and high-value draw/defense, avoiding off-plan attacks.

F28 [map] choose_map_node (option_index=1) | source=llm
  HP 61->61 | Gold 187->187 | Deck 25->25
  deck_change: no deck change
  reasoning: While the route intelligence suggests monster fights, I am deviating toward the monster node instead of the elite. My deck relies on Strangle+ and Shivs, which requires setup time. Act 2 elites like Gremlin Leader or Slavers can punish a deck that lacks consistent turn 1-2 AOE or massive block. Taking the monster node preserves HP and follows the 'Absolute Pacifism' strategy for Act 2 mentioned in the guide, reducing attrition before the final stretch.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 187->197 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 197->197 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F29 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 46->46 | Gold 197->197 | Deck 25->26
  deck_change: picked Deflect+
  reasoning: Deflect+ is a 0-cost skill that provides efficient block. On 3 energy, 0-cost cards are highly valuable, especially since they trigger Strangle+ without consuming energy and help mitigate damage while we set up our Shiv engine.
  strategic_note: Committed Shiv/Direct scaling plan: establish Phantom Blades and Infinite Blades, use Strangle+ for burst, and defend efficiently while scaling. Need more multi-hit attacks/Shiv generation and to remove Strikes.

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 197->197 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 197->209 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F30 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 39->39 | Gold 209->209 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 39->39 | Gold 209->209 | Deck 26->27
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is an incredible defensive tool against multi-hit attacks. The upcoming Act 2 Boss uses an 8x2 multi-hit and scales Strength, making this card a lifesaver. It also Exhausts to keep the deck lean.
  strategic_note: Committed shiv plan: rely on Phantom Blades and Shiv generation to deal steady damage while blocking safely. Prioritize draw and mitigation; skip generic attacks and alternate scaling.

F30 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 209->209 | Deck 27->27
  deck_change: no deck change
  reasoning: With 39 HP, an Elite fight is too risky this late in Act 2. Taking the monster node follows the pacifist route intelligence as closely as possible while ensuring I reach the final rest site with enough HP to survive the boss or potentially upgrade.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ for burst. Suppress provides critical turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle; favor safe paths to preserve HP for the boss.

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 209->222 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F31 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 39->39 | Gold 222->222 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 39->39 | Gold 222->222 | Deck 27->28
  deck_change: picked Leading Strike+
  reasoning: We are committed to a Shiv strategy utilizing Strangle and Phantom Blades. Leading Strike+ provides highly efficient fuel for Strangle (3 card plays for 1 energy) while benefiting from our Shiv scaling.
  strategic_note: Committed Shiv/Strangle plan: prioritize drawing and playing Strangle and Phantom Blades, then spam Shivs to scale damage quickly. Retain Shivs with Phantom Blades if Strangle is not yet drawn. Keep the deck lean and remove basic Strikes.

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 222->222 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 39->60 | Gold 222->222 | Deck 28->28
  deck_change: no deck change
  reasoning: Resting not only heals 21 HP right before the Act 2 Boss (taking us to a much safer 60/70), but it also triggers Tiny Mailbox, generating 2 random potions. Having extra potions and health for the boss fight is significantly more valuable than a single card upgrade here.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ to enable big burst turns. Suppress+ gives guaranteed turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle bursts.

F32 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 60->60 | Gold 222->222 | Deck 28->28
  deck_change: no deck change
  reasoning: All rewards claimed, proceed

F32 [rest_site] proceed | source=auto
  HP 60->60 | Gold 222->222 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 222->222 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 14->14 | Gold 222->297 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 14->14 | Gold 297->297 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 14->14 | Gold 297->297 | Deck 28->29
  deck_change: picked Tools of the Trade
  reasoning: Tools of the Trade provides passive card draw and discard every turn. This is highly valuable for mitigating the severe 6-card Status flood from the upcoming Act 2 Boss (The Insatiable) and helps consistently cycle to our key cards like Phantom Blades and Strangle+. We avoid Envenom as it is too slow and expensive at 2 energy for our 3-energy deck.
  strategic_note: Committed shiv/attack plan: setup Phantom Blades and Strangle, then play cheap attacks and Shivs for burst damage. Prioritize finding our scaling early; use Tools of the Trade and draw skills to dig through statuses. Need basic Strike removals.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 14->58 | Gold 297->297 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 58->58 | Gold 297->297 | Deck 29->29
  deck_change: no deck change
  reasoning: Beautiful Bracelet allows us to enchant 3 cards with Swift 3 (draw 3 cards the first time played). Because we have an Innate 0-cost card (Suppress+) and several other 0-cost cards like Adrenaline+ and Escape Plan, we can gain an explosive amount of free card draw to reliably find our Strangle+ and Shiv generators on turn 1 or 2.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ and massive Swift draw to enable explosive burst turns. Play 0-cost Swift-enchanted cards to cycle rapidly and find Strangle+, then dump Shivs. Prioritize card removal and block density now that draw is completely solved.

F34 [card_select] select_deck_card (option_index=15) | source=llm
  HP 58->58 | Gold 297->297 | Deck 29->29
  deck_change: no deck change
  reasoning: Enchanting 0-cost cards with Swift 3 (draw 3 cards) is insanely powerful because it provides free hand-replenishment. Suppress+ is Innate and costs 0, guaranteeing a massive turn 1 cycle. Deflect+ is a reusable 0-cost block that now acts as a primary draw engine. Adrenaline+ becomes an explosive burst, giving 2 energy and drawing 5 cards total to fuel our Strangle and Shiv plays.
  strategic_note: Committed Shiv/Strangle plan: Use 0-cost Swift enchantments to rapidly cycle the deck, find Phantom Blades and Strangle early, and overwhelm enemies with massive bursts of free attacks. Need consistent discard or energy to sustain the massive card draw.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 58->58 | Gold 297->297 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 58->58 | Gold 297->297 | Deck 29->29
  deck_change: no deck change
  reasoning: Following the recommended route to a standard monster fight. While the route guide suggests absolute pacifism in Act 2, I need to balance that with the reality that I have 297 gold and Planisphere (which heals in ? rooms). Taking a few early fights to find better defensive cards before shifting to the ? chain is a sound compromise to ensure I can handle the Act 2 boss.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ for burst. Suppress provides critical turn 1 mitigation. Prioritize defensive consistency and card draw to safely set up Strangle; shift towards non-combat nodes once the defense is stable to utilize Planisphere healing.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 297->305 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 305->305 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim potion: Snecko Oil

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 305->305 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 58->58 | Gold 305->305 | Deck 29->30
  deck_change: picked Escape Plan+
  reasoning: Escape Plan+ is 0-cost free cycle that triggers Strangle+ and sometimes provides 5 block. We are fully committed to Shivs and Strangle, so we avoid hybridizing with the poison cards (Noxious Fumes/Poisoned Stab).
  strategic_note: Committed to Shivs and Strangle scaling. Prioritize cards that generate Shivs, draw, and cycle to trigger Strangle multiple times. Skip poison and alternate scaling.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 305->305 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Monster

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 305->318 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 57->57 | Gold 318->318 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F36 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 57->57 | Gold 318->318 | Deck 30->30
  deck_change: no deck change
  reasoning: The deck is at 30 cards and already has a solid engine with Strangle+, Phantom Blades, and Shiv generators. Ricochet+ has some synergy with our discard outlets (Gambling Chip, Tools of the Trade, Storm of Steel) but is a dead draw if we lack a discard option and doesn't scale well enough to justify bloating the deck further right before the boss.
  strategic_note: Committed Shiv/Strangle plan: burst damage with Strangle+ and Shivs, scaling first Shiv via Phantom Blades. Keep the deck lean and prioritize block/draw to survive Queen's 20 block/turn and Amalgam's scaling.

F36 [map] choose_map_node (option_index=1) | source=llm
  HP 57->62 | Gold 318->318 | Deck 30->30
  deck_change: no deck change
  reasoning: Planisphere makes Unknown nodes highly efficient for both health sustain and event-based power spikes. Given our solid gold reserve (318), we want to reach the mid-act shops while staying healthy for the boss.
  strategic_note: Foundation Shiv and Strangle deck: uses Adrenaline+ for acceleration and Suppress+ for early mitigation. Focus on finding consistent block and additional Shiv generation or scaling to close out long fights; avoid high-attrition Act 3 elites unless necessary for power.

F37 [shop] buy_card (option_index=3) | source=plan
  HP 62->62 | Gold 318->280 | Deck 30->31
  deck_change: bought Blur+
  reasoning: Shop plan [1/4]: Massive value on sale. Carrying over block is essential to survive the Amalgam's scaling multi-attacks, especially once we are Frail.

F37 [shop] buy_card (option_index=5) | source=plan
  HP 62->62 | Gold 280->193 | Deck 31->32
  deck_change: bought Purity+
  reasoning: Shop plan [2/4]: Incredible deck-thinning tool for boss fights. Exhausting up to 5 Strikes/Defends will drastically improve our draw quality and consistency.

F37 [shop] buy_card (option_index=2) | source=plan
  HP 62->62 | Gold 193->121 | Deck 32->33
  deck_change: bought Up My Sleeve+
  reasoning: Shop plan [3/4]: Generates 4 Shivs to feed our Phantom Blades scaling engine. Excellent burst generation.

F37 [shop] remove_card_at_shop | source=plan
  HP 62->62 | Gold 121->121 | Deck 33->33
  deck_change: no deck change
  reasoning: Shop plan [4/4]: Removing a Strike to further thin the deck and ensure we draw into our Shiv generators and defense.

F37 [card_select] select_deck_card (option_index=0) | source=llm
  HP 62->62 | Gold 121->21 | Deck 33->32
  deck_change: lost Strike
  reasoning: Strike is severely obsolete in Act 3. Removing it increases the consistency of drawing our key scaling pieces like Phantom Blades, Strangle, and our defensive cards.
  strategic_note: Committed Shiv/Strangle plan: prioritize setting up Phantom Blades and Strangle early, then cycle rapidly to generate Shivs for massive burst damage. Keep relying on Fasten + Defends for block scaling. Avoid drafting generic attacks.

F37 [shop] close_shop_inventory | source=llm
  HP 62->62 | Gold 21->21 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F37 [shop] proceed | source=auto
  HP 62->62 | Gold 21->21 | Deck 32->32
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 62->62 | Gold 21->21 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Monster

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 21->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 56->56 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Our deck is currently at 32 cards and relies on finding key engine pieces like Phantom Blades, Strangle, and Fasten as quickly as possible. Grand Finale is too difficult to set up consistently, Dagger Spray is unnecessary, and while Flick-Flack+ has nice synergy with Gambling Chip and Tools of the Trade, adding more non-core attacks dilutes our draw consistency. Skipping keeps the deck lean.
  strategic_note: Committed Shiv plan: scale damage with Phantom Blades and Strangle by playing multiple Shivs per turn. Focus on rapid card cycle to find setup powers early, and use Fasten and dexterity for block. Avoid adding non-Shiv damage cards to keep draws consistent.

F38 [map] choose_map_node (option_index=0) | source=llm
  HP 56->61 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Choosing the Unknown node to trigger Planisphere healing and follow the pacifist routing strategy for Act 3, minimizing attrition before the boss.
  strategic_note: Foundation shiv and strangle deck: prioritize turn 1 burst with Adrenaline+ and Suppress+ mitigation. Scaling relies on shiv generation and Strangle+ for high single-target damage. Currently seeking consistent block and draw to survive between burst turns while using ? nodes to sustain health via Planisphere.

F39 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 61->61 | Gold 32->32 | Deck 32->32
  deck_change: upgraded Defend->Defend+, Tools of the Trade->Tools of the Trade+; changed: +Defend+, Strangle; -Defend, Strangle+
  reasoning: Shatter duplicates the deck which destroys all consistency, especially given we have specific draw synergies and setup. It also adds a terrible Eternal curse. Touch a Mirror provides a net positive of two upgrades, and with 22 unupgraded cards, the odds of hitting crucial upgrades (like Adrenaline+ or Suppress+) with the downgrades are acceptable compared to the alternative.
  strategic_note: Foundation phase: Building around Strangle+ and Shivs, using Adrenaline+ and massive Swift draw to enable explosive burst turns. Seek consistent block and prioritize card removal.

F39 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

F39 [map] choose_map_node (option_index=1) | source=llm
  HP 61->61 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 3 which advises avoiding elites, especially since my deck currently relies on Strangle and Shivs which can be punished by Act 3 elites (e.g., Nemesis/Giant Head/Reptomancer). The Unknown node also triggers Planisphere for a 5 HP heal, which is better than risking health against an Elite.
  strategic_note: Foundation shiv and strangle deck: prioritize front-loaded damage from Shivs while utilizing Strangle+ for scaling and Suppress+ for turn 1 safety. Plan is to use Adrenaline+ to cycle into burst turns; need more consistent block or scaling like Accuracy to solidify the endgame against the Act 3 boss.

F40 [event] choose_event_option (option_index=0) | source=auto
  HP 61->66 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

F40 [map] choose_map_node (option_index=0) | source=llm
  HP 66->66 | Gold 32->32 | Deck 32->32
  deck_change: no deck change
  reasoning: Moving towards the Treasure node to continue the established path toward the next Shop and Rest Site. While the current route includes a late Elite, I will look for opportunities to path around it later to follow the 'Avoid Act 3 Elites' guidance.
  strategic_note: Foundation shiv and burst deck: Use Adrenaline+ and Suppress+ to control the opening turn, setting up Strangle+ for high-impact shiv damage. Seek more defensive consistency or cycle (Acrobatics) to bridge the gap between burst turns; avoid high-attrition Act 3 elites if possible.

F41 [treasure] open_chest | source=random
  HP 66->66 | Gold 32->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim: Oddly Smooth Stone

F41 [treasure] proceed | source=random
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Shop

F42 [shop] close_shop_inventory | source=llm
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F42 [shop] proceed | source=auto
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: RestSite

F43 [rest_site] choose_rest_option (option_index=1, smith_card_index=10, note_scope=run, note_triggers=all) | source=llm
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: upgraded Strangle->Strangle+
  reasoning: Upgrading Strangle increases its per-card damage scaling from 2 to 3, which represents a massive damage increase for our Shiv and 0-cost heavy deck. We can use our next rest site at F47 to trigger Tiny Mailbox for potions immediately before the Act 3 Boss.
  strategic_note: Committed Strangle/Shiv engine: play Strangle on turns with massive card draw/shiv generation for lethal burst damage, while using Swift block cards and Retain mechanics to survive. Need consistent draw to reliably pair Strangle with Storm of Steel or Leading Strike.

F43 [rest_site] proceed | source=auto
  HP 66->66 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F43 [map] choose_map_node (option_index=0) | source=llm
  HP 66->70 | Gold 68->68 | Deck 32->32
  deck_change: no deck change
  reasoning: Following the recommended route to avoid Act 3 Elites, which are high-risk for Silent. Entering an Unknown node also triggers Planisphere, healing 5 HP.
  strategic_note: Foundation phase: leveraging Strangle+ and Shivs with high draw (Adrenaline+, Swift) for burst damage. Seeking reliable block and card removal to survive late-act attrition while avoiding Elites to preserve HP for the boss.

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 68->77 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 77->77 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 77->77 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F44 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 70->70 | Gold 77->77 | Deck 32->33
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is incredible mitigation against multi-attackers like the Act 3 Boss's Torch Head Amalgam, which scales Strength every round and unleashes deadly 3-hit attacks. Having a second copy increases the chance of drawing it on those critical turns.
  strategic_note: Committed Shiv plan: stack burst damage with Phantom Blades and generate Shivs while defending with efficient block. Retain Piercing Wails for multi-attack turns. Needs Well-Laid Plans and more draw; avoid bloating with non-synergy attacks.

F44 [map] choose_map_node (option_index=0) | source=llm
  HP 70->70 | Gold 77->77 | Deck 33->33
  deck_change: no deck change
  reasoning: The route recommends the Unknown node, and Planisphere provides a 5 HP heal for entering it. Given the strategy to minimize attrition in Act 3 and the high risk of Act 3 Elites, staying on the path of least resistance while gaining passive health is optimal.
  strategic_note: Foundation phase focusing on Strangle and Shiv burst enabled by Adrenaline and high draw. Prioritizing Unknown nodes to leverage Planisphere healing and minimize chip damage before the final boss. Need more consistent block and potentially one more scaling piece to solidify the late game.

F45 [event] choose_event_option (option_index=0) | source=llm
  HP 70->70 | Gold 77->77 | Deck 33->33
  deck_change: no deck change
  reasoning: Planisphere is completely useless for the rest of the run since there are no more ? rooms. Trading a dead relic for Sturdy Clamp, a powerful defensive Rare relic that lets up to 10 block persist across turns, is a massive free upgrade for the final fights.
  strategic_note: Committed Strangle/Shiv engine: use massive card draw and Swift cards to build explosive burst turns with Strangle and Shivs, while utilizing Retain and persistent block to survive off-turns. Prioritize consistent block scaling and setup pieces, avoiding raw attacks that clutter the deck.

F45 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 77->77 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 77->77 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Elite

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 77->103 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 103->103 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim relic: Pendulum

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 103->103 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 45->45 | Gold 103->103 | Deck 33->34
  deck_change: picked Infinite Blades+
  reasoning: Infinite Blades+ is Innate and provides a passive, continuous stream of 0-cost Shivs every turn. This perfectly fuels our Strangle+ triggers and gives us more targets for Phantom Blades damage scaling.
  strategic_note: Committed Shiv/Strangle plan: setup Phantom Blades, Strangle, and Infinite Blades early, then rapid cycle for massive burst damage and passive Strangle procs. Retain Shivs for key burst turns.

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 45->45 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 45->66 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: With the Act 3 Boss next floor, healing for 21 HP is crucial. Furthermore, Tiny Mailbox triggers upon resting to provide 2 random potions, which will be incredibly valuable for surviving and bursting down the boss.
  strategic_note: Committed Strangle/Shiv engine: play Strangle on turns with massive card draw/shiv generation for lethal burst damage, while using Swift block cards and Retain mechanics to survive. Need consistent draw to reliably pair Strangle with Storm of Steel or Leading Strike.

F47 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F47 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F47 [rest_site] proceed | source=auto
  HP 66->66 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 103->103 | Deck 34->34
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [card_select] select_deck_card (option_index=1) | source=llm
  HP 62->62 | Gold 103->0 | Deck 34->34
  deck_change: no deck change
  reasoning: We played the Skill Potion to find block or energy to mitigate the incoming 8 damage. Untouchable provides 6 Block for 0 energy this turn, helping us survive while still allowing us to play our key powers.
  strategic_note: Committed shiv plan: rely on Phantom Blades and Up My Sleeve+ for damage scaling, support with draw and dexterity. Prioritize block and scaling setup in early turns, avoid off-plan poison cards.

## Selected Replay Package (8 replays)
[Selected: run_combat] Mawler (F5, monster)
Historical: loss=1 vs historical avg=8.2+/-3.6 (z=-2.0, BETTER_THAN_USUAL, n=4)
## Combat Replay: vs Mawler (Floor 5, monster)
Relics: Ring of the Snake, Lead Paperweight
Deck (17): Defend x5, Strike x5, Ascender's Bane, Fasten, Follow Through, Leading Strike, Neutralize, Strangle, Survivor
Enemies: Mawler HP=72/72

### Round 1
Intent: Mawler: Attack(4x2=8)
  Strangle -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -8, +Strangle(2)
  Leading Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -5
  Shiv -> Mawler[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mawler: hp -6
  Shiv -> Mawler[0]
    enemy_deltas: Mawler: hp -6
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 2
Agent plan (hypothesis): Continue blocking safely and chipping away with attacks when energy permits.
Intent: Mawler: Attack(14)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Intent: Mawler: Attack(4x2=8)
  Neutralize -> Mawler[0]
    enemy_deltas: Mawler: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.

### Round 4
Intent: Mawler: Attack(14)
  Fire Potion -> Mawler[0]
    enemy_deltas: Mawler: hp -20
  Strangle -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -8, +Strangle(2)
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: DIED
## Combat Analytics: Mawler (WIN - 4 rounds)

Cards played (with descriptions):
  Strangle "Deal 8 damage. Whenever you play a card this turn, the enemy loses 2 HP." -> 2 plays, 16 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 5 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 12 dmg, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Defend "Gain 5 Block." -> 4 plays, 20 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Strike "Deal 6 damage." -> 3 plays, 12 dmg

Token attribution (Shivs):
  Leading Strike: 2 Shivs -> ~12 dmg
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Mawler (Floor 8, monster)
Relics: Ring of the Snake, Golden Pearl
Deck (16): Defend x5, Strike x5, Blade Dance, Blur, Cloak and Dagger, Neutralize, Phantom Blades, Survivor
Enemies: Mawler HP=72/72

### Round 1
Intent: Mawler: Attack(4x2=8)
  Cloak and Dagger
    energy -1 | block +6
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Mawler[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mawler: hp -4
  Shiv -> Mawler[0]
    enemy_deltas: Mawler: hp -4
  Shiv -> Mawler[0]
    enemy_deltas: Mawler: hp -4
  Shiv -> Mawler[0]
    enemy_deltas: Mawler: hp -4
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 2
Intent: Mawler: Debuff
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  Neutralize -> Mawler[0]
    enemy_deltas: Mawler: hp -3, +Weak(1)
  turn_end

### Round 3
Intent: Mawler: Attack(21)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Neutralize -> Mawler[0]
    enemy_deltas: Mawler: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Blur
    energy -1 | block +5 | +Blur(1)
  turn_end

### Round 4
Intent: Mawler: Attack(6x2=12)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Mawler: Attack(21)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Mawler[0]
    enemy_deltas: Mawler: hp -13
  Blur
    energy -1 | block +5 | +Blur(1)
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 6
Intent: Mawler: Attack(4x2=8)
  Neutralize -> Mawler[0]
    enemy_deltas: Mawler: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Mawler[0]
    energy -1 | enemy_deltas: Mawler: hp -6
  turn_end

### Round 7
Intent: Mawler: Attack(14)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Mawler[0]
    block -6 | -Phantom Blades | enemy_deltas: Mawler: DIED
## Combat Analytics: Mawler (WIN - 7 rounds)

Cards played (with descriptions):
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 3 plays, 18 block, generates 1 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 29 dmg, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Strike "Deal 6 damage." -> 4 plays, 24 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 3 plays, 9 dmg
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage. Draw 2 cards the first time this is played." -> 1 plays
  Defend "Gain 5 Block." -> 6 plays, 30 block
  Blur "Gain 5 Block. Block is not removed at the start of your next turn." -> 2 plays, 10 block

Token attribution (Shivs):
  Cloak and Dagger: 3 Shivs -> ~14 dmg
  Blade Dance: 3 Shivs -> ~14 dmg

[Selected: elite] Bygone Effigy (F14, elite)
Historical: loss=13 vs historical avg=6.3+/-7.6 (z=0.9, TYPICAL, n=3)
## Combat Replay: vs Bygone Effigy (Floor 14, elite)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox
Deck (20): Defend x5, Strike x5, Adrenaline+, Ascender's Bane, Fasten, Follow Through, Infinite Blades, Leading Strike, Neutralize, Predator, Strangle+, Survivor
Enemies: Bygone Effigy HP=127/127

### Round 1
Agent plan (hypothesis): Effigy buffs next turn. Go all out on damage next turn.
Intent: Bygone Effigy: Sleep
  Neutralize -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -3, +Weak(1)
  Fasten
    energy -1 | +Fasten(5)
  Predator -> Bygone Effigy[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Bygone Effigy: hp -18
  turn_end

### Round 2
Agent plan (hypothesis): Effigy attacks for 23 next turn. Prioritize blocking with Fasten-boosted Defends while letting Infinite Blades and residual attacks chip it down.
Intent: Bygone Effigy: Buff
  Adrenaline+
    energy +2 | exhausted: Adrenaline+ [0]: Gain 2 energy . Draw 2 cards. Exhaust.
  Strangle+ -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -11, +Strangle(3)
  Swift Potion
  Explosive Ampoule
    enemy_deltas: Bygone Effigy: hp -10
  Leading Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -6
  Shiv -> Bygone Effigy[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bygone Effigy: hp -8
  Infinite Blades
    energy -1 | +Infinite Blades(1) | enemy_deltas: Bygone Effigy: hp -3
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -12
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -12
  turn_end
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.

### Round 3
Agent plan (hypothesis): We will take 13 damage, but next turn we should draw into strong enough attacks to finish it off.
Intent: Bygone Effigy: Attack(23)
  Defend
    energy -1 | block +10
  Shiv -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -4
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  turn_end

### Round 4
Agent plan (hypothesis): We survived the damage race. Good combo sequence.
Agent plan (hypothesis): Combat ends.
Intent: Bygone Effigy: Attack(23)
  Strangle+ -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -10, +Strangle(3)
  Neutralize -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -6, +Weak(1)
  Leading Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -6
  Shiv -> Bygone Effigy[0]
    -Fasten | -Infinite Blades | enemy_deltas: Bygone Effigy: DIED
## Combat Analytics: Bygone Effigy (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 9 dmg
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 18 dmg
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 21 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 2 plays, 12 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, 3 dmg, generates 1 Shivs
  Strike "Deal 6 damage." -> 4 plays, 38 dmg
  Defend "Gain 10 Block." -> 1 plays, 10 block

Token attribution (Shivs):
  Leading Strike: 2 Shivs -> ~8 dmg
  other: 1 Shivs -> ~4 dmg

Enemy power timeline:
  Slow: R1:1 -> R2:1 -> R3:1 -> R4:1
  Strength: R1:- -> R2:- -> R3:10 -> R4:10
Comparator (recent same-enemy comparator):
## Combat Replay: vs Bygone Effigy (Floor 12, elite)
Relics: Ring of the Snake, Booming Conch, Unsettling Lamp
Deck (18): Defend x5, Strike x4, Dash, Dodge and Roll, Footwork, Leading Strike, Leg Sweep, Neutralize+, Noxious Fumes+, Poisoned Stab, Survivor
Enemies: Bygone Effigy HP=127/127

### Round 1
Intent: Bygone Effigy: Sleep
  Footwork
    energy -1 | +Dexterity(2)
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -6
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  turn_end

### Round 2
Intent: Bygone Effigy: Buff
  Neutralize+ -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -4, +Weak(4)
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -6
  Dash -> Bygone Effigy[0]
    energy -2 | block +12 | enemy_deltas: Bygone Effigy: hp -12
  turn_end

### Round 3
Intent: Bygone Effigy: Attack(17)
  Dexterity Potion
    Dexterity(2→4)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Leg Sweep -> Bygone Effigy[0]
    energy -2 | block +15 | enemy_deltas: Bygone Effigy: Weak(3→5)
  turn_end

### Round 4
Intent: Bygone Effigy: Attack(17)
  Dodge and Roll
    energy -1 | block +8 | +Block Next Turn(8)
  Dash -> Bygone Effigy[0]
    energy -2 | block +14 | enemy_deltas: Bygone Effigy: hp -11
  turn_end

### Round 5
Intent: Bygone Effigy: Attack(17)
  Neutralize+ -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -4, Weak(3→5)
  Defend
    energy -1 | block +9
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  Survivor
    energy -1 | block +12
  turn_end

### Round 6
Intent: Bygone Effigy: Attack(17)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  turn_end

### Round 7
Intent: Bygone Effigy: Attack(17)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Poisoned Stab -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7, Poison(9→12)
  turn_end

### Round 8
Intent: Bygone Effigy: Attack(17)
  Neutralize+ -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -4, Weak(2→4)
  Dodge and Roll
    energy -1 | block +8 | +Block Next Turn(8)
  Defend
    energy -1 | block +9
  Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -7
  turn_end

### Round 9
Intent: Bygone Effigy: Attack(17)
  Neutralize+ -> Bygone Effigy[0]
    block -8 | -Dexterity | -Noxious Fumes | enemy_deltas: Bygone Effigy: DIED
## Combat Analytics: Bygone Effigy (WIN - 9 rounds)

Cards played (with descriptions):
  Footwork "Gain 2 Dexterity." -> 1 plays
  Strike "Deal 6 damage." -> 6 plays, 40 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 4 plays, 12 dmg
  Dash "Gain 12 Block. Deal 10 damage." -> 2 plays, 23 dmg, 26 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 15 Block." -> 1 plays, 15 block
  Dodge and Roll "Gain 8 Block. Next turn, gain 8 Block." -> 2 plays, 16 block
  Defend "Gain 9 Block." -> 6 plays, 54 block
  Survivor "Gain 12 Block. Discard 1 card." -> 1 plays, 12 block
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 7 dmg, +3 poison

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:3 -> R5:5 -> R6:7 -> R7:9 -> R8:14 -> R9:16
  Slow: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Strength: R1:- -> R2:- -> R3:10 -> R4:10 -> R5:10 -> R6:10 -> R7:10 -> R8:10 -> R9:10
  Weak: R1:- -> R2:- -> R3:3 -> R4:4 -> R5:3 -> R6:4 -> R7:3 -> R8:2 -> R9:3

[Selected: boss] multi:Kin Follower+Kin Follower+Kin Priest (F17, boss)
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Planisphere
Deck (22): Defend x5, Strike x5, Adrenaline+, Ascender's Bane, Backflip, Fasten, Follow Through, Infinite Blades, Leading Strike, Leg Sweep, Neutralize, Predator, Strangle+, Survivor
Enemies: Kin Follower HP=58/58, Kin Follower HP=59/59, Kin Priest HP=190/190

### Round 1
Agent plan (hypothesis): Turn 2 will have Adrenaline+ and Strangle+. Start with Strangle+, dump 0-cost cards (including the Shiv), and scale damage. Be ready to use the Block Potion on Turn 3 when Frail heavily impacts our Defends.
Intent: Kin Follower: Buff, Kin Follower: Attack(5), Kin Priest: Attack(8), Debuff
  Strength Potion
    +Strength(2)
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Predator -> Kin Priest[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Kin Priest: hp -17
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Look for Strangle+ to scale damage.
Agent plan (hypothesis): We will have 3 energy after Backflip to block or play additional drawn damage (like Follow Through).
Intent: Kin Follower: Attack(7), Kin Follower: Attack(2x2=4), Kin Priest: Attack(8), Debuff
  Adrenaline+
    energy +2 | exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Strangle+ -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12, +Strangle(3)
  Shiv -> Kin Priest[2]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Kin Priest: hp -9
  Backflip
    energy -1 | block +3 | enemy_deltas: Kin Priest: hp -3
  Follow Through -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -21
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -11
  Survivor
    energy -1 | block +6
  Defend
  turn_end

### Round 3
Agent plan (hypothesis): We've scaled our defense with Fasten. Focus entirely on the Priest with Strangle and multi-hits. Look for Leg Sweep to heavily mitigate the Priest's incoming attacks.
Intent: Kin Follower: Attack(4x2=8), Kin Follower: Buff, Kin Priest: Attack(3x3=9)
  Block Potion
    block +12
  Fasten
    energy -1 | +Fasten(5)
  Predator -> Kin Priest[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Kin Priest: hp -12
  Neutralize -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -3, +Weak(1)
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -4
  turn_end

### Round 4
Agent plan (hypothesis): Keep pushing damage on the Priest. He's getting close to dead.
Intent: Kin Follower: Buff, Kin Follower: Attack(7), Kin Priest: Buff
  Strangle+ -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12, +Strangle(3)
  Follow Through -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -21
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Defend
    energy -1 | block +10 | enemy_deltas: Kin Priest: hp -3
  turn_end

### Round 5
Agent plan (hypothesis): Priest will be at 27 HP next turn. Focus all damage on the Priest to secure the kill and force the minions to flee.
Intent: Kin Follower: Attack(9), Kin Follower: Attack(4x2=8), Kin Priest: Attack(10), Debuff
  Defend
    energy -1 | block +10
  Defend
    energy -1 | block +10
  Leading Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -5
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -6
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -6
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -6
  turn_end

### Round 6
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(10), Debuff
  Follow Through -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -18
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -8
  Shiv -> Kin Priest[2]
    -Strength | -Infinite Blades | -Fasten | -Frail | enemy_deltas: Kin Follower: DIED; Kin Priest: DIED
## Combat Analytics: multi:Kin Follower+Kin Follower+Kin Priest (WIN - 6 rounds)

Cards played (with descriptions):
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Predator "Deal 17 damage. Next turn, draw 2 cards." -> 2 plays, 29 dmg
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Deal 12 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 24 dmg
  Shiv "Deal 6 damage. Exhaust." -> 7 plays, 40 dmg, EXHAUST
  Backflip "Gain 3 Block. Draw 2 cards." -> 1 plays, 3 dmg, 3 block
  Follow Through "Deal 9 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 3 plays, 60 dmg
  Strike "Deal 8 damage." -> 2 plays, 19 dmg
  Survivor "Gain 6 Block. Discard 1 card." -> 1 plays, 6 block
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Defend "Gain 10 Block." -> 3 plays, 3 dmg, 30 block
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 1 plays, 5 dmg, generates 2 Shivs

Token attribution (Shivs):
  other: 5 Shivs -> ~29 dmg
  Leading Strike: 2 Shivs -> ~11 dmg

Enemy power timeline:
  Minion[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Minion[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker
Deck (22): Defend x5, Strike x5, Piercing Wail x2, Acrobatics, Bubble Bubble, Dagger Spray, Deadly Poison, Expertise, Haze, Neutralize+, Noxious Fumes+, Predator+, Survivor
Enemies: Kin Follower HP=58/58, Kin Follower HP=59/59, Kin Priest HP=190/190

### Round 1
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

[Selected: run_combat] multi:Exoskeleton+Exoskeleton+Exoskeleton (F24, monster)
Historical: loss=14 vs historical avg=3.0+/-4.0 (z=2.8, WORSE_THAN_USUAL, n=8)
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton (Floor 24, monster)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Planisphere, Archaic Tooth, Gambling Chip, Bag of Marbles
Deck (24): Defend x5, Strike x4, Adrenaline+, Ascender's Bane, Backflip, Fasten, Follow Through, Infinite Blades, Leading Strike, Leg Sweep, Phantom Blades, Predator, Purity, Storm of Steel, Strangle+, Suppress, Survivor
Enemies: Exoskeleton HP=25/25, Exoskeleton HP=24/24, Exoskeleton HP=26/26

### Round 1
Agent plan (hypothesis): Phantom Blades is up, prioritize generating Shivs and holding them for the +9 damage proc.
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff
  Suppress -> Exoskeleton[1]
  Backflip
    energy -1 | block +5
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 2
Intent: Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(10)
  Predator -> Exoskeleton[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Exoskeleton: hp -9
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Agent plan (hypothesis): Only Exo[0] remains.
Agent plan (hypothesis): Exo[0] is alone, build up Shivs next turn.
Agent plan (hypothesis): We will have full energy next turn to generate Shivs and finish it off.
Intent: Exoskeleton: Buff, Exoskeleton: Attack(2x3=6), Exoskeleton: Buff
  Adrenaline+
    energy +2 | exhausted: Adrenaline+ [0]: Gain 2 energy . Draw 2 cards. Exhaust.
  Strangle+ -> Exoskeleton[2]
    energy -1 | enemy_deltas: Exoskeleton: hp -9, +Strangle(3)
  Follow Through -> Exoskeleton[1]
    energy -1 | enemy_deltas: Exoskeleton: hp -3
  Strike -> Exoskeleton[1]
    energy -1 | enemy_deltas: Exoskeleton: hp -3
  Fasten
    energy -1 | +Fasten(5) | enemy_deltas: Exoskeleton: hp +23, -Strength, -Strangle
  Strike -> Exoskeleton[0]
    energy -1 | enemy_deltas: Exoskeleton: hp -6
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 4
Intent: Exoskeleton: Attack(3x3=9)
  Purity
  Strike
  Strike
  confirm
    exhausted: Strike [1]: Deal 6 damage.
  Predator -> Exoskeleton[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Exoskeleton: hp -9
  Survivor
    energy -1 | block +8
  turn_end

### Round 5
Agent plan (hypothesis): Combat ends.
Intent: Exoskeleton: Attack(10)
  Strangle+ -> Exoskeleton[0]
    energy -1 | enemy_deltas: Exoskeleton: hp -9, +Strangle(3)
  Strike -> Exoskeleton[0]
    energy -1 | -Phantom Blades | -Fasten | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton (WIN - 5 rounds)

Cards played (with descriptions):
  Suppress "Innate. Deal 11 damage. Apply 3 Weak." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 18 dmg
  Defend "Gain 5 Block." -> 1 plays, 5 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 18 dmg
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 1 plays, 3 dmg
  Strike "Deal 6 damage." -> 3 plays, 9 dmg
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Purity "Retain. Exhaust up to 3 cards in your Hand. Exhaust." -> 1 plays, EXHAUST

Enemy power timeline:
  Hard to Kill: R1:- -> R2:- -> R3:- -> R4:9 -> R5:9
  Hard to Kill[0]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Hard to Kill[1]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Hard to Kill[2]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:2 -> R5:2
  Strength[1]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Vulnerable[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton (Floor 21, monster)
Relics: Ring of the Snake, Golden Pearl, Nunchaku, The Chosen Cheese, Pael's Blood, Daughter of the Wind
Deck (21): Defend x5, Strike x4, Abrasive, Backflip, Blade Dance, Bouncing Flask+, Dash, Leading Strike, Malaise, Neutralize+, Noxious Fumes+, Phantom Blades, Ricochet, Survivor
Enemies: Exoskeleton HP=25/25, Exoskeleton HP=24/24, Exoskeleton HP=27/27

### Round 1
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff
  Neutralize+ -> Exoskeleton[1]
    energy +1 | block +1
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Exoskeleton[1]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Exoskeleton[1]
    block +1
  Shiv -> Exoskeleton[1]
    block +1
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(10)
  Backflip
    energy -1 | block +5
  Dash -> Exoskeleton[2]
    energy -2 | block +11 | enemy_deltas: Exoskeleton: hp -9
  turn_end

### Round 3
Intent: Exoskeleton: Buff, Exoskeleton: Attack(3x3=9), Exoskeleton: Buff
  Strike -> Exoskeleton[1]
    energy -1 | block +1
  Leading Strike -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -3
  Shiv -> Exoskeleton[1]
    block +1 | enemy_deltas: Exoskeleton: hp -4
  Shiv -> Exoskeleton[1]
    block +1 | enemy_deltas: Exoskeleton: hp -4
  Survivor
    energy -1 | block +8
  Ricochet
  turn_end
    block +1

### Round 4
Intent: Exoskeleton: Attack(3x3=9)
  Strike -> Exoskeleton[0]
    block +1 | enemy_deltas: Exoskeleton: hp -6
  Strike -> Exoskeleton[0]
    energy -1 | hp +1 | block -1 | -Noxious Fumes | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 1 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 5 plays, 8 dmg, 5 block, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Dash "Gain 10 Block. Deal 10 damage." -> 1 plays, 9 dmg, 11 block
  Strike "Deal 6 damage." -> 3 plays, 6 dmg, 2 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, 1 block, generates 2 Shivs
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~5 dmg
  Leading Strike: 2 Shivs -> ~3 dmg

Enemy power timeline:
  Hard to Kill: R1:- -> R2:- -> R3:- -> R4:9
  Hard to Kill[0]: R1:9 -> R2:9 -> R3:9 -> R4:-
  Hard to Kill[1]: R1:9 -> R2:9 -> R3:9 -> R4:-
  Hard to Kill[2]: R1:9 -> R2:9 -> R3:9 -> R4:-
  Poison: R1:- -> R2:- -> R3:- -> R4:7
  Poison[0]: R1:- -> R2:3 -> R3:5 -> R4:-
  Poison[1]: R1:- -> R2:3 -> R3:5 -> R4:-
  Poison[2]: R1:- -> R2:3 -> R3:5 -> R4:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:2
  Strength[1]: R1:- -> R2:- -> R3:2 -> R4:-
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:-

[Selected: run_combat] Spiny Toad (F31, monster)
Historical: loss=0 vs historical avg=7.7+/-7.6 (z=-1.0, BETTER_THAN_USUAL, n=3)
## Combat Replay: vs Spiny Toad (Floor 31, monster)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Planisphere, Archaic Tooth, Gambling Chip, Bag of Marbles, Toxic Egg
Deck (27): Defend x5, Strike x4, Adrenaline+, Ascender's Bane, Backflip, Deflect+, Escape Plan, Fasten, Follow Through, Infinite Blades, Leading Strike, Leg Sweep, Phantom Blades, Piercing Wail+, Predator, Purity, Storm of Steel, Strangle+, Suppress+, Survivor
Enemies: Spiny Toad HP=117/117

### Round 1
Agent plan (hypothesis): Thorns is active next turn. Focus entirely on blocking and do NOT play attacks unless they are 1-shotting the enemy or necessary. Thorns hurts.
Intent: Spiny Toad: Buff
  Suppress+ -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -25, +Weak(5)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Predator -> Spiny Toad[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Spiny Toad: hp -22
  turn_end

### Round 2
Agent plan (hypothesis): Next turn Thorns drops, safe to attack.
Intent: Spiny Toad: Attack(17)
  Escape Plan
  Purity
  Strike
  Leading Strike
  confirm
    exhausted: Strike [1]: Deal 6 damage.
  Piercing Wail+
    energy -1 | exhausted: Strike [1]: Deal 6 damage. | enemy_deltas: Spiny Toad: +Strength(-8), +Piercing Wail(8)
  Leg Sweep -> Spiny Toad[0]
    energy -2 | block +11 | enemy_deltas: Spiny Toad: Weak(4→6)
  turn_end

### Round 3
Intent: Spiny Toad: Attack(12)
  Strangle+ -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -10, +Strangle(3)
  Defend
    energy -1 | block +5 | enemy_deltas: Spiny Toad: hp -3
  Survivor
    energy -1 | block +8
  Ascender's Bane
  turn_end

### Round 4
Intent: Spiny Toad: Buff
  Adrenaline+
    energy +2 | exhausted: Strike [1]: Deal 6 damage.
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Strike -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -6
  Strike -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -6
  turn_end

### Round 5
Intent: Spiny Toad: Attack(17)
  Escape Plan
    block +3
  Survivor
    energy -1 | block +8
  Ascender's Bane
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Spiny Toad: Attack(12)
  Follow Through -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -14
  Suppress+ -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -17, Weak(2→7)
  Shiv -> Spiny Toad[0]
    -Phantom Blades | -Infinite Blades | enemy_deltas: Spiny Toad: DIED
## Combat Analytics: Spiny Toad (WIN - 6 rounds)

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 42 dmg
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 22 dmg
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 3 block
  Purity "Retain. Exhaust up to 3 cards in your Hand. Exhaust." -> 1 plays, EXHAUST
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Defend "Gain 5 Block." -> 3 plays, 3 dmg, 15 block
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 1 plays, 14 dmg
  Shiv "Retain. Deal 13 damage. Exhaust." -> 1 plays, EXHAUST

Token attribution (Shivs):
  other: 1 Shivs -> ~0 dmg

Enemy power timeline:
  Thorns: R1:- -> R2:5 -> R3:- -> R4:- -> R5:5 -> R6:-
  Vulnerable: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Weak: R1:- -> R2:4 -> R3:5 -> R4:4 -> R5:3 -> R6:2
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Spiny Toad (Floor 30, monster)
Relics: Ring of the Snake, Small Capsule, Regal Pillow, Prayer Wheel, Lantern, Archaic Tooth, Meal Ticket
Deck (33): Defend x5, Strike x5, Afterimage x2, Burst x2, Dodge and Roll x2, Acrobatics, Acrobatics+, Calculated Gamble, Cloak and Dagger+, Deflect, Escape Plan, Escape Plan+, Footwork, Footwork+, Leading Strike, Noxious Fumes+, Piercing Wail, Snakebite, Sucker Punch+, Suppress+, Survivor, Well-Laid Plans+
Enemies: Spiny Toad HP=118/118

### Round 1
Intent: Spiny Toad: Buff
  Suppress+ -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -17, +Weak(5)
  Burst
    energy -1 | +Burst(1)
  Cloak and Dagger+
    energy -1 | block +12 | -Burst
  Shiv -> Spiny Toad[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Spiny Toad: hp -4
  Shiv -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -4
  Shiv -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -4
  Shiv -> Spiny Toad[0]
    enemy_deltas: Spiny Toad: hp -4
  Strike -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -6
  Strike -> Spiny Toad[0]
    energy -1 | enemy_deltas: Spiny Toad: hp -6
  turn_end

### Round 2
Intent: Spiny Toad: Attack(17)
  Deflect
    block +4
  Acrobatics
    energy -1
  Snakebite
  Acrobatics+
    energy -1
  Sucker Punch+
  Survivor
    energy -1 | block +8
  Defend
  Calculated Gamble
    exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  turn_end

### Round 3
Intent: Spiny Toad: Attack(12)
  Escape Plan+
  Afterimage
    energy -1 | +Afterimage(1)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end

### Round 4
Intent: Spiny Toad: Buff
  Escape Plan
    block +4
  Escape Plan+
    block +6
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Leading Strike -> Spiny Toad[0]
    energy -1 | block +1 | enemy_deltas: Spiny Toad: hp -3
  Shiv -> Spiny Toad[0]
    block +1 | enemy_deltas: Spiny Toad: hp -4
  Shiv -> Spiny Toad[0]
    block +1 | enemy_deltas: Spiny Toad: hp -4
  Strike -> Spiny Toad[0]
    energy -1 | block +1 | enemy_deltas: Spiny Toad: hp -6
  turn_end
  Strike
  Piercing Wail

### Round 5
Intent: Spiny Toad: Attack(17)
  Footwork
    energy -1 | block +1 | +Dexterity(2)
  Cloak and Dagger+
    energy -1 | block +9
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(6)
  turn_end
  Piercing Wail
  Defend

### Round 6
Intent: Spiny Toad: Attack(17)
  Suppress+ -> Spiny Toad[0]
    block +1 | enemy_deltas: Spiny Toad: hp -17, +Weak(5)
  Noxious Fumes+
    energy -1 | block +1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +8
  Sucker Punch+ -> Spiny Toad[0]
    energy -1 | block +1 | enemy_deltas: Spiny Toad: hp -10, Weak(5→7)
  turn_end
  Piercing Wail
  Acrobatics

### Round 7
Intent: Spiny Toad: Buff
  Burst
    energy -1 | block +1 | +Burst(1)
  Acrobatics
    energy -1 | -Burst
  Strike
  Defend
  Afterimage
    energy -1 | block +1 | Afterimage(1→2)
  Deflect
    block +8
  turn_end
  Piercing Wail
  Burst

### Round 8
Intent: Spiny Toad: Attack(17)
  Footwork+
    energy -1 | block +2 | Dexterity(2→5)
  Piercing Wail
    energy -1 | block +2 | exhausted: Shiv*6 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Spiny Toad: +Strength(-6), +Piercing Wail(6)
  Dodge and Roll
    energy -1 | block +11 | +Block Next Turn(9)
  turn_end
  Burst
  Acrobatics+

### Round 9
Intent: Spiny Toad: Attack(12)
  Suppress+ -> Spiny Toad[0]
    block +2 | enemy_deltas: Spiny Toad: hp -17, Weak(4→9)
  Defend
    energy -1 | block +12
  Dodge and Roll
    energy -1 | block +11 | +Block Next Turn(9)
  turn_end
  Burst
  Acrobatics+
## Combat Analytics: Spiny Toad (WIN - 9 rounds)

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 3 plays, 51 dmg, 3 block
  Burst "This turn, your next Skill is played an extra time." -> 2 plays, 1 block
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 2 plays, 21 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 24 dmg, 2 block, EXHAUST
  Strike "Deal 6 damage." -> 3 plays, 18 dmg, 1 block
  Deflect "Gain 4 Block." -> 2 plays, 12 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 5 Block." -> 2 plays, 6 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 2 plays, 1 block
  Defend "Gain 5 Block." -> 4 plays, 32 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 4 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, 1 block, generates 2 Shivs
  Footwork "Gain 2 Dexterity." -> 1 plays, 1 block
  Dodge and Roll "Gain 6 Block. Next turn, gain 6 Block." -> 3 plays, 29 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 1 block
  Sucker Punch+ "Deal 10 damage. Apply 2 Weak." -> 1 plays, 10 dmg, 1 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 2 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 2 block, EXHAUST

Token attribution (Shivs):
  Cloak and Dagger+: 2 Shivs -> ~8 dmg
  other: 2 Shivs -> ~8 dmg
  Leading Strike: 2 Shivs -> ~8 dmg

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:3 -> R8:5 -> R9:7
  Thorns: R1:- -> R2:5 -> R3:- -> R4:- -> R5:5 -> R6:- -> R7:- -> R8:5 -> R9:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:6 -> R8:5 -> R9:4

[Selected: boss] The Insatiable (F33, boss)
Historical: loss=46 vs historical avg=16.7+/-7.4 (z=4.0, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Planisphere, Archaic Tooth, Gambling Chip, Bag of Marbles, Toxic Egg
Deck (28): Defend x5, Strike x4, Adrenaline+, Ascender's Bane, Backflip, Deflect+, Escape Plan, Fasten, Follow Through, Infinite Blades, Leading Strike, Leading Strike+, Leg Sweep, Phantom Blades, Piercing Wail+, Predator, Purity, Storm of Steel, Strangle+, Suppress+, Survivor
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Strangle+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -15, +Strangle(3)
  Suppress+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -28, +Weak(5)
  Phantom Blades
    energy -1 | +Phantom Blades(9) | enemy_deltas: The Insatiable: hp -3
  Escape Plan
    enemy_deltas: The Insatiable: hp -3
  Fasten
    energy -1 | +Fasten(5) | enemy_deltas: The Insatiable: hp -3
  turn_end

### Round 2
Agent plan (hypothesis): Next turn is a heavy attack (21 damage because of Weak). Keep cycling for scaling and Shivs.
Intent: The Insatiable: Attack(6x2=12)
  Purity
  Strike
  Strike
  confirm
    exhausted: Strike [1]: Deal 6 damage.
  Leg Sweep -> The Insatiable[0]
    energy -2 | block +11 | enemy_deltas: The Insatiable: Weak(4→6)
  Follow Through -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -7
  turn_end

### Round 3
Agent plan (hypothesis): Sandpit timer extended. Next turn boss buffs, focus on scaling or raw damage. Draw pile has Adrenaline+ and Infinite Blades.
Intent: The Insatiable: Attack(21)
  Energy Potion
    energy +2
  Deflect+
    block +7
  Defend
    energy -1 | block +10
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  Predator -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -15
  turn_end

### Round 4
Agent plan (hypothesis): Infinite Blades guarantees a Shiv every turn, so no need to retain Shivs unless preparing for a massive Strangle burst. Sandpit clock is extended.
Agent plan (hypothesis): Continue generating and playing Shivs to trigger Phantom Blades buff. Keep an eye on Sandpit timer.
Intent: The Insatiable: Buff
  Adrenaline+
    energy +2 | exhausted: Strike*2 [1]: Deal 6 damage.
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Leading Strike+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -6
  Shiv -> The Insatiable[0]
    exhausted: Strike*2 [1]: Deal 6 damage. | enemy_deltas: The Insatiable: hp -13
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Backflip
    energy -1 | block +5
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  turn_end
    exhausted: Strike*2 [1]: Deal 6 damage.

### Round 5
Agent plan (hypothesis): Sandpit is ticking down, prioritize damage where possible.
Intent: The Insatiable: Attack(7x2=14)
  Defend
    energy -1 | block +10
  Leading Strike -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -3
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Storm of Steel
    energy -1
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  turn_end

### Round 6
Agent plan (hypothesis): Continue managing Sandpit timer.
Intent: The Insatiable: Attack(7x2=14)
  Escape Plan
    block +3
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  Frantic Escape
    energy -2 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Defend
    energy -1 | block +10
  turn_end

### Round 7
Agent plan (hypothesis): Sandpit timer extended. Boss will buff next turn.
Intent: The Insatiable: Attack(22)
  Follow Through -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -14
  Suppress+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -17, Weak(1→6)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Strike -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -6
  turn_end

### Round 8
Intent: The Insatiable: Buff
  Strangle+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -10, +Strangle(3)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -16
  Frantic Escape
    energy -1 | enemy_deltas: The Insatiable: hp -3, Sandpit(3→4)
  Defend
    energy -1 | block +10 | enemy_deltas: The Insatiable: hp -3
  turn_end

### Round 9
Agent plan (hypothesis): Sandpit will drop to 2, keep looking for Lethal or Frantic Escapes to stall if necessary.
Intent: The Insatiable: Attack(9x2=18)
  Deflect+
    block +7
  Defend
    energy -1 | block +10
  Predator -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -15
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  turn_end

### Round 10
Agent plan (hypothesis): Kill the boss next turn before Sandpit hits 0.
Intent: The Insatiable: Attack(9x2=18)
  Foul Potion
    hp -12 | enemy_deltas: The Insatiable: hp -12
  Follow Through -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -14
  Leading Strike+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -6
  Defend
    energy -1 | block +10
  Deflect+
    block +7
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -4
  turn_end

### Round 11
Agent plan (hypothesis): We won!
Intent: The Insatiable: Attack(24)
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -13
  Backflip
    energy -1 | block +5
  Strike -> The Insatiable[0]
    energy -1 | block -5 | -Phantom Blades | -Fasten | -Infinite Blades | enemy_deltas: The Insatiable: DIED
## Combat Analytics: The Insatiable (WIN - 11 rounds)

Cards played (with descriptions):
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 25 dmg
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 45 dmg
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 3 dmg
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 3 dmg, 3 block
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays, 3 dmg
  Purity "Retain. Exhaust up to 3 cards in your Hand. Exhaust." -> 1 plays, EXHAUST
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 3 plays, 35 dmg
  Deflect+ "Gain 7 Block." -> 3 plays, 21 block
  Defend "Gain 10 Block." -> 6 plays, 3 dmg, 60 block
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 6 plays, 3 dmg
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 30 dmg
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 12 dmg, generates 2 Shivs
  Shiv "Retain. Deal 13 damage. Exhaust." -> 15 plays, 135 dmg, EXHAUST
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 10 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, generates 2 Shivs
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, generates 1 Shivs
  Strike "Deal 6 damage." -> 2 plays, 6 dmg

Token attribution (Shivs):
  other: 8 Shivs -> ~72 dmg
  Leading Strike+: 3 Shivs -> ~27 dmg
  Leading Strike: 2 Shivs -> ~18 dmg
  Infinite Blades: 1 Shivs -> ~9 dmg
  Storm of Steel: 1 Shivs -> ~9 dmg

Enemy power timeline:
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:4 -> R5:4 -> R6:3 -> R7:3 -> R8:3 -> R9:3 -> R10:2 -> R11:1
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4 -> R11:4
  Vulnerable: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:-
  Weak: R1:- -> R2:4 -> R3:5 -> R4:4 -> R5:3 -> R6:2 -> R7:1 -> R8:5 -> R9:4 -> R10:3 -> R11:2
Comparator (recent better same-enemy comparator):
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Small Capsule, Regal Pillow, Prayer Wheel, Lantern, Archaic Tooth, Meal Ticket
Deck (35): Defend x5, Strike x5, Afterimage x2, Burst x2, Dodge and Roll x2, Footwork+ x2, Acrobatics, Acrobatics+, Backflip+, Calculated Gamble, Cloak and Dagger+, Deflect, Escape Plan, Escape Plan+, Leading Strike, Noxious Fumes+, Piercing Wail, Prepared+, Snakebite, Sucker Punch+, Suppress+, Survivor, Well-Laid Plans+
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Suppress+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -17, +Weak(5)
  Afterimage
    energy -1 | +Afterimage(1)
  Acrobatics+
    energy -1
  Strike
  Noxious Fumes+
    energy -1 | block +1 | +Noxious Fumes(3)
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(4)
  turn_end

### Round 2
Intent: The Insatiable: Attack(6x2=12)
  Footwork+
    energy -1 | block +1 | +Dexterity(3)
  Escape Plan
    block +7
  Escape Plan+
    block +9
  Deflect
    block +8
  Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -6
  Defend
    energy -1 | block +9
  turn_end

### Round 3
Intent: The Insatiable: Attack(21)
  Footwork+
    energy -1 | block +1 | Dexterity(3→6)
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Defend
    energy -1 | block +12
  turn_end

### Round 4
Intent: The Insatiable: Buff
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Leading Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -3
  Shiv -> The Insatiable[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -4
  turn_end
  Defend
  confirm

### Round 5
Intent: The Insatiable: Attack(7x2=14)
  Orobic Acid
  Speedster
    block +1 | +Speedster(2)
  Corrosive Wave
    block +1 | +Corrosive Wave(2)
  Predator -> The Insatiable[0]
    block +1 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -15
  Afterimage
    energy -1 | block +1 | Afterimage(1→2)
  Prepared+
    enemy_deltas: The Insatiable: hp -4, Poison(9→13)
  Sucker Punch+
  Frantic Escape
  Defend
    energy -1 | block +13
  Defend
    energy -1 | block +13
  turn_end
  Survivor
  confirm

### Round 6
Intent: The Insatiable: Attack(10x2=20)
  Sucker Punch+ -> The Insatiable[0]
    energy -1 | block +2 | enemy_deltas: The Insatiable: hp -10, +Weak(2)
  Burst
    energy -1 | block +2 | +Burst(1)
  Backflip+
    energy -1 | block +32 | -Burst | enemy_deltas: The Insatiable: hp -8
  Suppress+ -> The Insatiable[0]
    block +2 | enemy_deltas: The Insatiable: hp -17, Weak(2→7)
  Escape Plan
    block +11 | enemy_deltas: The Insatiable: hp -2
  Escape Plan+
    block +13 | enemy_deltas: The Insatiable: hp -2
  Calculated Gamble
    block +2 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -16
  Prepared+
    enemy_deltas: The Insatiable: hp -4
  Defend
  Defend
  turn_end
  Frantic Escape
  Acrobatics+

### Round 7
Intent: The Insatiable: Attack(22)
  Liquid Memories
  Burst
  Burst
    block +2 | +Burst(1)
  Dodge and Roll
    energy -1 | block +24 | +Block Next Turn(20) | -Burst
  Frantic Escape
    energy -1 | block +2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Acrobatics+
    energy -1 | enemy_deltas: The Insatiable: hp -8
  Strike
  Deflect
    block +12
  turn_end
  Acrobatics
  Burst

### Round 8
Intent: The Insatiable: Buff
  Escape Plan
    block +11 | enemy_deltas: The Insatiable: hp -2
  Frantic Escape
    energy -1 | block +2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Burst
    energy -1 | block +2 | +Burst(1)
  Dodge and Roll
    energy -1 | block +24 | +Block Next Turn(20) | -Burst
  turn_end
  Acrobatics
  Burst

### Round 9
Intent: The Insatiable: Attack(9x2=18)
  Escape Plan+
    block +2 | enemy_deltas: The Insatiable: hp -2
  Burst
    energy -1 | block +2 | +Burst(1)
  Acrobatics
    energy -1 | -Burst | enemy_deltas: The Insatiable: hp -6
  Predator
  Strike
  Suppress+ -> The Insatiable[0]
    block +2 | enemy_deltas: The Insatiable: hp -17, Weak(4→9)
  Frantic Escape
    energy -1 | block +2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  turn_end
  Cloak and Dagger+
  Frantic Escape

### Round 10
Intent: The Insatiable: Attack(9x2=18)
  Frantic Escape
    energy -2 | block +2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Deflect
    block +12
  Cloak and Dagger+
    energy -1 | block +14
  Shiv -> The Insatiable[0]
    block +2 | enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    block +2 | enemy_deltas: The Insatiable: hp -4
  turn_end
  Defend
  Survivor

### Round 11
Intent: The Insatiable: Attack(24)
  Frantic Escape
    energy -1 | block +2 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Defend
    energy -1 | block +13
  Survivor
    energy -1 | block +14
  Acrobatics+
  turn_end
  Dodge and Roll
  Leading Strike

### Round 12
Intent: The Insatiable: Buff
  Sucker Punch+ -> The Insatiable[0]
    energy -1 | block +2 | enemy_deltas: The Insatiable: hp -10, Weak(6→8)
  Leading Strike -> The Insatiable[0]
    energy -1 | block -2 | -Afterimage | -Noxious Fumes | -Dexterity | -Well-Laid Plans | -Speedster | enemy_deltas: The Insatiable: DIED
## Combat Analytics: The Insatiable (WIN - 12 rounds)

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 3 plays, 51 dmg, 4 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 2 plays, 1 block
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 2 plays, 8 dmg
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 1 block
  Dodge and Roll "Gain 4 Block. Next turn, gain 4 Block." -> 3 plays, 53 block
  Footwork+ "Gain 3 Dexterity." -> 2 plays, 2 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 6 Block." -> 3 plays, 4 dmg, 29 block
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 8 Block." -> 3 plays, 4 dmg, 24 block
  Deflect "Gain 7 Block." -> 3 plays, 32 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg, 1 block
  Defend "Gain 8 Block." -> 5 plays, 60 block
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 7 plays, 12 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 2 plays, 3 dmg, 1 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 16 dmg, 6 block, EXHAUST
  Speedster "Whenever you draw a card during your turn, deal 2 damage to ALL enemies." -> 1 plays, 1 block
  Corrosive Wave "Whenever you draw a card this turn, apply 2 Poison to ALL enemies." -> 1 plays, 1 block
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg, 1 block
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays, 8 dmg, +4 poison
  Sucker Punch+ "Deal 10 damage. Apply 2 Weak." -> 2 plays, 20 dmg, 4 block
  Burst "This turn, your next Skill is played an extra time." -> 4 plays, 8 block
  Backflip+ "Gain 14 Block. Draw 2 cards." -> 1 plays, 8 dmg, 32 block
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 16 dmg, 2 block, EXHAUST
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays, 6 dmg
  Cloak and Dagger+ "Gain 12 Block. Add 2 Shivs into your Hand." -> 1 plays, 14 block, generates 2 Shivs
  Survivor "Gain 14 Block. Discard 1 card." -> 1 plays, 14 block

Token attribution (Shivs):
  Leading Strike: 2 Shivs -> ~8 dmg
  Cloak and Dagger+: 2 Shivs -> ~8 dmg

Poison stacks applied per card:
  Prepared+: 4 stacks

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:15 -> R7:17 -> R8:19 -> R9:21 -> R10:23 -> R11:25 -> R12:27
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:3 -> R5:3 -> R6:2 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4 -> R10:4 -> R11:4 -> R12:4
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:6 -> R8:5 -> R9:4 -> R10:8 -> R11:7 -> R12:6

[Selected: elite] Mecha Knight (F46, elite)
Historical: loss=25 vs historical avg=27.0+/-15.5 (z=-0.1, TYPICAL, n=3)
## Combat Replay: vs Mecha Knight (Floor 46, elite)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Archaic Tooth, Gambling Chip, Bag of Marbles, Toxic Egg, Beautiful Bracelet, Oddly Smooth Stone, Sturdy Clamp
Deck (33): Defend x3, Strike x3, Defend+ x2, Piercing Wail+ x2, Adrenaline+, Ascender's Bane, Backflip, Blur+, Deflect+, Escape Plan, Escape Plan+, Fasten, Follow Through, Infinite Blades, Leading Strike, Leading Strike+, Leg Sweep, Phantom Blades, Predator, Purity, Purity+, Storm of Steel, Strangle+, Suppress+, Survivor, Tools of the Trade+, Up My Sleeve+
Enemies: Mecha Knight HP=300/300

### Round 1
Agent plan (hypothesis): If we draw Adrenaline or Deflect+, use them to keep drawing and generating block.
Agent plan (hypothesis): Need to draw more block or weak next turn to survive the incoming multi-attacks.
Intent: Mecha Knight: Attack(25)
  Tools of the Trade+
    +Tools of the Trade(1)
  Suppress+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -17, Artifact(2→1)
  Escape Plan+
  Strangle+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -10, -Artifact
  Leading Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -3
  Shiv -> Mecha Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Defend
    energy -1 | block +6
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Strike

### Round 2
Agent plan (hypothesis): Save Purity+ to exhaust the Dazed/Wounds Mecha Knight puts in our deck.
Intent: Mecha Knight: StatusCard(4)
  Predator -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -15
  Blur+
    energy -1 | block +9 | +Blur(1)
  turn_end
  Burn

### Round 3
Agent plan (hypothesis): Turn 4 is a huge attack (40 dmg), be ready to defend.
Intent: Mecha Knight: Defend, Buff
  Follow Through -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -14
  Purity+
  Burn
  Burn
  Burn
  confirm
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Phantom Blades
    energy -1 | +Phantom Blades(9) | exhausted: Shiv*2 [0]: Retain. Deal 4 damage. Exhaust.
  Escape Plan
    block +4
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  turn_end
  Fasten

### Round 4
Agent plan (hypothesis): Save Purity to purge the statuses. Keep looking for Phantom Blades + Strangle turns to burst him down.
Agent plan (hypothesis): Use Purity to clear the upcoming status cards.
Intent: Mecha Knight: Attack(40)
  Backflip
    energy -1 | block +6
  Leg Sweep -> Mecha Knight[0]
    energy -2 | block +12 | enemy_deltas: Mecha Knight: +Weak(2)
  turn_end
  Infinite Blades

### Round 5
Agent plan (hypothesis): We'll re-evaluate the hand after the draw from Deflect+. Look for Strangle or more draw.
Agent plan (hypothesis): He's putting statuses into our deck. Prepare to cycle and finish him before the big hit on turn 7.
Intent: Mecha Knight: StatusCard(4)
  Vulnerable Potion -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: +Vulnerable(3)
  Adrenaline+
    energy +2 | exhausted: Shiv*2 [0]: Retain. Deal 4 damage. Exhaust.
  Suppress+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -25, Weak(1→6)
  Purity
  Burn
  Strike
  confirm
  Deflect+
    block +8
  Strangle+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -15, +Strangle(3)
  Fasten
    energy -1 | +Fasten(5) | enemy_deltas: Mecha Knight: hp -3
  Backflip
    energy -1 | block +6 | enemy_deltas: Mecha Knight: hp -3
  Escape Plan
    enemy_deltas: Mecha Knight: hp -3
  Leading Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -7
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -22
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  Storm of Steel
    energy -1 | enemy_deltas: Mecha Knight: hp -3
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9
  turn_end
    enemy_deltas: Mecha Knight: -Strangle
  Burn

### Round 6
Agent plan (hypothesis): If we draw Leading Strike+ or Survivor, we might pivot from Predator, but Predator's next-turn draw is very valuable for the upcoming Turn 7 45-damage hit.
Agent plan (hypothesis): Turn 7 will be a massive attack (base 25 + 5 Str = 30, x1.5 from vulnerable? Wait, we are not vulnerable, but enemy has 5 Str). Defend heavily next turn. With 10 cards drawn, we should have plenty of options.
Intent: Mecha Knight: Defend, Buff
  Follow Through -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -20
  Escape Plan+
  Predator -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -22
  turn_end
  Strike

### Round 7
Agent plan (hypothesis): Enemy will apply status cards next turn. Finish him off quickly.
Intent: Mecha Knight: Attack(33)
  Leading Strike+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: block -9
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -13, block -6
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -6
  Defend+
    energy -1 | block +14
  Defend
    energy -1 | block +11
  turn_end
  Burn

### Round 8
Agent plan (hypothesis): Evaluate drawn card to push for lethal or discard Burns.
Agent plan (hypothesis): We will take 4 damage from Burns. Next turn, use generated Shivs to finish him off.
Intent: Mecha Knight: StatusCard(4)
  Escape Plan
    block +4
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  Deflect+
    block +8
  turn_end
  Burn

### Round 9
Agent plan (hypothesis): Good kill.
Intent: Mecha Knight: Defend, Buff
  Follow Through -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -14
  Shiv -> Mecha Knight[0]
    block -8 | -Dexterity | -Tools of the Trade | -Phantom Blades | -Fasten | -Infinite Blades | enemy_deltas: Mecha Knight: DIED
## Combat Analytics: Mecha Knight (WIN - 9 rounds)

Cards played (with descriptions):
  Tools of the Trade+ "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak. Draw 3 cards the first time this is played." -> 2 plays, 42 dmg
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 6 Block." -> 2 plays
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 25 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 2 plays, 10 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 12 plays, 103 dmg, EXHAUST
  Defend "Gain 6 Block." -> 2 plays, 17 block
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 37 dmg
  Blur+ "Gain 9 Block. Block is not removed at the start of your next turn." -> 1 plays, 9 block
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 3 plays, 48 dmg
  Purity+ "Retain. Exhaust up to 5 cards in your Hand. Exhaust." -> 1 plays, EXHAUST
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Escape Plan "Draw 1 card. If you draw a Skill, gain 4 Block." -> 3 plays, 3 dmg, 8 block
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 2 plays, 3 dmg, 12 block
  Leg Sweep "Apply 2 Weak. Gain 12 Block." -> 1 plays, 12 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Draw 3 cards the first time this is played. Exhaust." -> 1 plays, EXHAUST
  Purity "Retain. Exhaust up to 3 cards in your Hand. Exhaust." -> 1 plays, EXHAUST
  Deflect+ "Gain 8 Block. Draw 3 cards the first time this is played." -> 2 plays, 16 block
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays, 3 dmg
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, 3 dmg, generates 1 Shivs
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 1 plays, generates 2 Shivs
  Defend+ "Gain 14 Block." -> 1 plays, 14 block
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs

Active powers: Dexterity(1)

Token attribution (Shivs):
  other: 5 Shivs -> ~43 dmg
  Leading Strike: 4 Shivs -> ~34 dmg
  Leading Strike+: 2 Shivs -> ~17 dmg
  Storm of Steel: 1 Shivs -> ~9 dmg

Enemy power timeline:
  Artifact: R1:2 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10 -> R8:10 -> R9:10
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:1 -> R8:- -> R9:-
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:5 -> R7:4 -> R8:3 -> R9:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs Mecha Knight (Floor 45, elite)
Relics: Ring of the Snake, Neow's Torment, Shuriken, Art of War, Amethyst Aubergine, Very Hot Cocoa, Old Coin, Centennial Puzzle, Pear, Delicate Frond, Oddly Smooth Stone, Miniature Cannon
Deck (35): Defend x5, Strike x4, Deadly Poison x2, Piercing Wail x2, Acrobatics, Backflip, Bouncing Flask, Calculated Gamble+, Cloak and Dagger, Corrosive Wave, Corrosive Wave+, Dagger Spray, Deflect, Footwork+, Malaise+, Neow's Fury, Neutralize+, Noxious Fumes+, Outbreak, Piercing Wail+, Poisoned Stab, Predator, Reflex, Survivor, Well-Laid Plans, Well-Laid Plans+
Enemies: Mecha Knight HP=300/300

### Round 1
Intent: Mecha Knight: Attack(25)
  Dexterity Potion
    Dexterity(1→3)
  Corrosive Wave
    energy -1 | +Corrosive Wave(2)
  Reflex
    energy -3 | enemy_deltas: Mecha Knight: Artifact(3→1)
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  turn_end

### Round 2
Intent: Mecha Knight: StatusCard(4)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -7, -Artifact
  Backflip
    energy -1 | block +8
  Deadly Poison -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: +Poison(5)
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Mecha Knight[0]
    +Strength(1) | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -4
  Deflect
    block +7
  turn_end

### Round 3
Intent: Mecha Knight: Defend, Buff
  Deadly Poison -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(4→9)
  Acrobatics
    energy -1
  Burn
  Poisoned Stab -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -7, Poison(9→12)
  turn_end

### Round 4
Intent: Mecha Knight: Attack(40)
  Weak Potion -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: +Weak(3)
  Footwork+
    energy -1 | Dexterity(3→6)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Survivor
    energy -1 | block +14
  Outbreak
  turn_end
  Malaise+
  confirm

### Round 5
Intent: Mecha Knight: StatusCard(4)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Calculated Gamble+
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Deflect
    block +10
  Poisoned Stab -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -7, Poison(10→13)
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -7
  Strike -> Mecha Knight[0]
    energy -1 | Strength(1→2) | enemy_deltas: Mecha Knight: hp -7
  turn_end
  Well-Laid Plans
  Defend

### Round 6
Intent: Mecha Knight: Defend, Buff
  Defend
    energy -1 | block +11
  Backflip
    energy -1 | block +11
  Acrobatics
    energy -1
  Burn
  turn_end
  Piercing Wail
  confirm

### Round 7
Intent: Mecha Knight: Attack(45)
  Weak Potion -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: +Weak(3)
  Piercing Wail
    energy -1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: Strength(10→4), +Piercing Wail(6)
  Piercing Wail
    energy -1 | enemy_deltas: Mecha Knight: Strength(4→-2), Piercing Wail(6→12)
  Cloak and Dagger
    energy -1 | block +12
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: block -6
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: block -8
  turn_end

### Round 8
Intent: Mecha Knight: StatusCard(4)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -9, Weak(2→4)
  Outbreak
    energy -1 | +Outbreak(11)
  Bouncing Flask
    energy -2 | enemy_deltas: Mecha Knight: hp -11, Poison(19→28)
  turn_end
  Deadly Poison
  Corrosive Wave

### Round 9
Intent: Mecha Knight: Defend, Buff
  Defend
    energy -1 | block +22
  Predator -> Mecha Knight[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Mecha Knight: hp -17
  turn_end
  Corrosive Wave
  Corrosive Wave+

### Round 10
Intent: Mecha Knight: Attack(37)
  Piercing Wail+
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: Strength(15→7), +Piercing Wail(8)
  Defend
    energy -1 | block +11
  Malaise+ -> Mecha Knight[0]
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: Strength(7→5), Weak(2→4)
  turn_end
  Corrosive Wave+
  Deadly Poison
## Combat Analytics: Mecha Knight (LOSS - 10 rounds)
Death cause: Died with HP=7, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Corrosive Wave "Whenever you draw a card this turn, apply 2 Poison to ALL enemies." -> 1 plays
  Reflex "Sly. Draw 2 cards." -> 1 plays
  Defend "Gain 8 Block." -> 6 plays, 68 block
  Neutralize+ "Deal 7 damage. Apply 2 Weak." -> 2 plays, 16 dmg
  Backflip "Gain 8 Block. Draw 2 cards." -> 2 plays, 19 block
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Strike "Deal 6 damage." -> 4 plays, 20 dmg
  Cloak and Dagger "Gain 9 Block. Add 1 Shiv into your Hand." -> 2 plays, 21 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 4 dmg, EXHAUST
  Deflect "Gain 7 Block." -> 2 plays, 17 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 2 plays
  Poisoned Stab "Deal 7 damage. Apply 3 Poison." -> 2 plays, 14 dmg, +6 poison
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Survivor "Gain 14 Block. Discard 1 card." -> 1 plays, 14 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Draw 2 cards the first time this is played." -> 1 plays
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Bouncing Flask "Apply 3 Poison to a random enemy 3 times." -> 1 plays, 11 dmg, +9 poison
  Predator "Deal 17 damage. Next turn, draw 2 cards." -> 1 plays, 17 dmg
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST

Active powers: Dexterity(1)

Token attribution (Shivs):
  Cloak and Dagger: 2 Shivs -> ~4 dmg

Poison stacks applied per card:
  Deadly Poison: 10 stacks
  Bouncing Flask: 9 stacks
  Poisoned Stab: 6 stacks

Enemy power timeline:
  Artifact: R1:3 -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Poison: R1:- -> R2:- -> R3:4 -> R4:11 -> R5:10 -> R6:15 -> R7:17 -> R8:19 -> R9:30 -> R10:32
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10 -> R8:10 -> R9:10 -> R10:15
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:2 -> R9:3 -> R10:2

[Selected: boss, death] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Lead Paperweight, Tiny Mailbox, Archaic Tooth, Gambling Chip, Bag of Marbles, Toxic Egg, Beautiful Bracelet, Oddly Smooth Stone, Sturdy Clamp, Pendulum
Deck (34): Defend x3, Strike x3, Defend+ x2, Piercing Wail+ x2, Adrenaline+, Ascender's Bane, Backflip, Blur+, Deflect+, Escape Plan, Escape Plan+, Fasten, Follow Through, Infinite Blades, Infinite Blades+, Leading Strike, Leading Strike+, Leg Sweep, Phantom Blades, Predator, Purity, Purity+, Storm of Steel, Strangle+, Suppress+, Survivor, Tools of the Trade+, Up My Sleeve+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -25, +Weak(5)
  Tools of the Trade+
    +Tools of the Trade(1)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Infinite Blades+
    energy -1 | +Infinite Blades(1)
  Blur+
    energy -1 | block +9 | +Blur(1)
  turn_end
  Strike

### Round 2
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Survivor
    energy -1 | block +9
  Ascender's Bane
  Adrenaline+
    energy +2 | exhausted: Adrenaline+ [0]: Gain 2 energy . Draw 2 cards. Exhaust.
  Fasten
    energy -1 | +Fasten(5)
  Escape Plan+
    block +6
  Shiv -> Queen[1]
    exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Queen: hp -13
  Backflip
    energy -1 | block +6
  Leading Strike -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Storm of Steel
    energy -1
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -4
  turn_end
  Shiv

### Round 3
Intent: Torch Head Amalgam: Attack(9x3=27), Queen: Buff, Defend
  Strangle+ -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -7, +Strangle(3)
  Piercing Wail+
    energy -1 | exhausted: Shiv*9 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: +Strength(-8), +Piercing Wail(8); Queen: hp -3, +Strength(-8), +Piercing Wail(8)
  Leading Strike+ -> Queen[1]
    energy -1 | enemy_deltas: Queen: hp -7
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -12
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -6
  turn_end
  Strike

### Round 4
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Skill Potion
  Untouchable
  Up My Sleeve+
    energy -2
  Untouchable
    block +5
  Infinite Blades
    energy -1 | Infinite Blades(1→2)
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -9
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  turn_end
    exhausted: Shiv*14 [0]: Retain. Deal 4 damage. Exhaust.
  Follow Through

### Round 5
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Strangle+ -> Queen[1]
    energy -1 | enemy_deltas: Queen: block -7, +Strangle(3)
  Defend+
    energy -1 | block +10 | enemy_deltas: Queen: hp -3
  Defend
    energy -1 | block +8 | enemy_deltas: Queen: hp -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -3, block -9
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -3, block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -5, block -1
  Shiv -> Queen[1]
    enemy_deltas: Queen: hp -6
  turn_end
  Shiv

### Round 6
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  Piercing Wail+
    energy -1 | exhausted: Shiv*18 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: Strength(3→-5), +Piercing Wail(8); Queen: +Strength(-8), +Piercing Wail(8)
  Defend
    energy -1 | block +8
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -9
  Backflip
    energy -1 | block +4
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, +Weak(5)
  turn_end
  Strike

### Round 7
Intent: Torch Head Amalgam: Attack(20), Queen: Buff, Defend
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -9
  Escape Plan+
  Deflect+
    block +6
  Escape Plan
    block +3
  Defend
    energy -1 | block +8
  Predator -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: block -11
  turn_end
  Untouchable

### Round 8
Intent: Torch Head Amalgam: Attack(21), Queen: Buff, Defend
  Defend+
    energy -1 | block +10
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -9
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  turn_end
  Strike

### Round 9
Intent: Torch Head Amalgam: Attack(15x3=45), Queen: Buff, Defend
  Escape Plan+
    block +4
  Purity
  Strike
  confirm
    exhausted: Strike [1]: Deal 6 damage.
  Defend
    energy -1 | block +8
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +9 | enemy_deltas: Torch Head Amalgam: Weak(2→4)
  turn_end
  Storm of Steel

### Round 10
Intent: Torch Head Amalgam: Attack(23), Queen: Buff, Defend
  Up My Sleeve+
    energy -1
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -9
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    enemy_deltas: Queen: block -3
  turn_end
  Strike

### Round 11
Intent: Torch Head Amalgam: Attack(24), Queen: Buff, Defend
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(2→7)
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -9
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -3
  Shiv -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -3
  turn_end
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 11 rounds)
Death cause: Died with HP=6, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak. Draw 3 cards the first time this is played." -> 3 plays, 49 dmg
  Tools of the Trade+ "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Infinite Blades+ "Innate. At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Blur+ "Gain 9 Block. Block is not removed at the start of your next turn." -> 1 plays, 9 block
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Draw 3 cards the first time this is played. Exhaust." -> 1 plays, EXHAUST
  Fasten "Gain an additional 5 Block from Defend cards." -> 1 plays
  Escape Plan+ "Draw 1 card. If you draw a Skill, gain 6 Block." -> 3 plays, 10 block
  Shiv "Retain. Deal 13 damage. Exhaust." -> 33 plays, 104 dmg, EXHAUST
  Backflip "Gain 6 Block. Draw 2 cards." -> 2 plays, 10 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, generates 2 Shivs
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, generates 1 Shivs
  Strangle+ "Deal 7 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 7 dmg
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 2 plays, 3 dmg, EXHAUST
  Leading Strike+ "Deal 4 damage. Add 2 Shivs into your Hand. Bound" -> 1 plays, 7 dmg, generates 2 Shivs
  Up My Sleeve+ "Add 4 Shivs into your Hand. Reduce this card's cost by 1." -> 2 plays, generates 4 Shivs
  Untouchable "Sly. Gain 5 Block." -> 1 plays, 5 block
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand. Bound" -> 1 plays, generates 1 Shivs
  Defend+ "Gain 10 Block. Bound" -> 2 plays, 3 dmg, 20 block
  Defend "Gain 8 Block." -> 4 plays, 3 dmg, 32 block
  Deflect+ "Gain 6 Block. Draw 3 cards the first time this is played." -> 1 plays, 6 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 3 block
  Predator "Deal 11 damage. Next turn, draw 2 cards." -> 1 plays
  Purity "Retain. Exhaust up to 3 cards in your Hand. Exhaust." -> 1 plays, EXHAUST
  Leg Sweep "Apply 2 Weak. Gain 9 Block." -> 1 plays, 9 block

Active powers: Dexterity(1)

Token attribution (Shivs):
  other: 21 Shivs -> ~66 dmg
  Up My Sleeve+: 7 Shivs -> ~22 dmg
  Leading Strike: 2 Shivs -> ~6 dmg
  Leading Strike+: 2 Shivs -> ~6 dmg
  Storm of Steel: 1 Shivs -> ~3 dmg

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:6 -> R10:7 -> R11:8
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:4 -> R8:3 -> R9:2 -> R10:3 -> R11:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Winged Boots, Pantograph, Stone Cracker, Pael's Blood, Pendulum, Bag of Marbles, Amethyst Aubergine, Delicate Frond, Orrery, Venerable Tea Set, Regal Pillow, Strike Dummy, Snecko Skull
Deck (37): Defend x5, Piercing Wail x3, Calculated Gamble+ x2, Footwork+ x2, Strike x2, Acrobatics, Acrobatics+, Assassinate, Automation, Backflip, Backflip+, Bouncing Flask, Bubble Bubble, Corrosive Wave+, Dagger Spray, Deadly Poison, Escape Plan+, Expertise, Fasten, Haze, Master of Strategy, Neutralize+, Noxious Fumes, Noxious Fumes+, Predator+, Skewer, Survivor, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
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

## Triggered Skills This Run
- The Silent - Combat Principles: F2(Leaf Slime (S): ), F3(Shrinker Beetle: WIN), F4(Fuzzy Wurm Crawler: WIN), F5(Mawler: WIN), F6(Fogmog: WIN), F8(Shrinker Beetle: ), F11(Vine Shambler: WIN), F14(Bygone Effigy: WIN), F15(Inklet: WIN), F19(Tunneler: WIN), F24(Exoskeleton: WIN), F28(Bowlbug (Rock): ), F29(The Obscura: WIN), F30(Exoskeleton: WIN), F31(Spiny Toad: WIN), F35(Living Shield: ), F36(Devoted Sculptor: WIN), F38(Punch Construct: WIN), F44(Fabricator: WIN), F46(Mecha Knight: WIN)
- The Silent - Deckbuilding Principles: F1(), F2(), F3(), F4(), F5(), F6(), F8(), F11(), F14(), F15(), F17(), F19(), F20(), F20(), F20(), F24(), F25(), F28(), F28(), F29(), F30(), F31(), F33(), F34(), F35(), F36(), F37(), F37(), F37(), F38(), F42(), F44(), F46(), F48()
- The Silent - Path Selection: F1(), F1(), F4(), F8(), F11(), F11(), F12(), F12(), F18(), F18(), F22(), F26(), F28(), F30(), F30(), F34(), F34(), F36(), F36(), F38(), F39(), F40(), F43(), F44()
- The Silent - Rest & Event Decisions: F7(), F9(), F13(), F16(), F27(), F32(), F43(), F47()
- Tunneler Burrowed Stun: F19(Tunneler: WIN)

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.