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
Result: VICTORY (fitness: 235.3)
Combats won: 23/23
Run duration: 7624.1s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: relying on basic strikes and defends. Look for early premium damage cards to take on elites, and lean into whatever the random rare card dictates.
- [map] Foundation phase: relying on basic strikes and defends; looking for early premium damage cards to take on elites, and leaning into whatever the random rare card dictates.
### F2
- [card_reward] Foundation plan: survive with frontload damage like Leading Strike while looking for a reliable poison applicator to pair with Accelerant. Avoid taking conditional poison cards until we have a base applicator.
### F3
- [event] Foundation phase: relying on basic strikes/defends, looking for early premium damage. Avoiding permanent curses is critical.
### F4
- [card_reward] Foundation plan: build around shiv generation and attack spam for Finisher burst, looking for a core scaling engine like Accuracy or more shiv generators. Keep deck lean and add block.
### F5
- [card_reward] Foundation plan transitioning to Shivs: prioritize 0-cost cards, Shiv generation, and multi-play payoffs like Strangle/Finisher. Need block/dex scaling and draw to support the high-cycle damage engine.
### F6
- [event] Foundation phase: relying on basic strikes/defends, with powerful burst combos through Retain on Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle.
- [card_select] Foundation plan: currently leaning into a Shiv/spam engine with Leading Strike, Strangle, and Finisher. Need efficient card draw and block to support playing multiple cards per turn. Look for discard/draw synergies and avoid heavy, expensive cards.
### F7
- [card_reward] Committed Shiv/Strangle plan: retain Strangle and Leading Strike for burst turns with Finisher. We need reliable block, more draw, and more Shiv generation to scale this engine.
- [map] Foundation phase: relying on basic strikes and defends; looking for early premium damage cards to take on elites, and leaning into whatever the random rare card dictates.
### F8
- [rest_site] Foundation phase: relying on basic strikes/defends, with powerful burst combos through Retain on Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle.
### F9
- [card_reward] Committed Shiv/Strangle plan: stack Shiv generators and cheap cycle cards in hand, play Strangle+, then dump all 0-cost attacks and finish with Finisher. Avoid expensive cards that clog the Strangle turn.
### F10
- [map] Foundation phase: leveraging Retain on Finisher and Strangle for burst windows. Seeking multi-hit cards or poison to scale damage, while prioritizing upgrades to improve damage-per-energy efficiency before the late-act Elite.
### F11
- [rest_site] Foundation phase: relying on basic strikes/defends, with burst combos through Retain on Leading Strike/Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle. Prioritize removing basic strikes to improve combo consistency.
- [map] Foundation phase: relying on basic strikes/defends with burst potential from Finisher and Strangle. Seeking shiv generation or poison to scale damage, while prioritizing card removals at shops to increase draw consistency for high-impact turns.
### F12
- [card_select] Committed shiv/strangle plan: use Leading Strikes and shivs to trigger Strangle and Envenom heavily. Accelerant synergizes with Envenom. Need defensive scaling, draw, and energy; avoid adding more low-impact attacks.
### F13
- [card_reward] Engine established: Use Strangle+ and Shivs (Leading Strike, Finisher) alongside Envenom for massive burst turns. Prioritize defense, draw, and energy to support this engine. Skip off-plan expensive attacks.
### F14
- [event] Foundation phase: relying on burst combos through Retain on Leading Strike/Strangle. Look for poison to enable Accelerant or more shiv generation. Upgraded Uncommon Power provides scaling for Act 1 Boss and beyond.
### F15
- [card_select] Foundation phase: relying on basic strikes/defends, with burst combos through Retain on Leading Strike/Finisher/Strangle.
- [card_reward] Committed to Strangle/Shiv/Envenom engine. Retain combo pieces to unleash burst turns, while Envenom stacks poison for long fights. Need more draw, Shiv generators, and efficient block. Avoid expensive non-combo cards.
### F16
- [rest_site] Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
### F17
- [card_select] Committed Envenom/Poison plan: use Leading Strike to generate Shivs, stack poison with Envenom, and burst with Accelerant. Needs cheap draw, energy, and mitigation; avoid off-plan damage.
- [card_reward] Foundation plan: Use Shivs and low-cost attacks to fuel Strangle and Afterimage, cycling with Escape Plan and Unceasing Top. Prioritize exhaust/discard outlets and 0-cost cards; skip heavy, expensive cards that break Unceasing Top.
### F18
- [event] Foundation phase: relying on burst combos through Retain (Leading Strike, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
- [map] Foundation phase: leveraging Finisher and Strangle for burst damage while hunting for Shiv generation or Poison to scale. Card removal is a priority to increase the density of high-impact cards, so I am pathing to accumulate gold and card rewards early in the act.
### F19
- [card_reward] Committed shiv/strangle/envenom plan: play shivs with Strangle+ and Envenom for massive damage, while Afterimage provides sustained defense. Needs more draw (Acrobatics/Backflip) to find powers and cycle shiv generators quickly. Avoid bulky high-cost cards.
- [map] Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
### F20
- [event] Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
- [map] Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
### F21
- [map] Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.
### F22
- [event] Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.
- [card_select] Committed engine plan: play Strangle, Envenom, and Afterimage, then spam Shivs and cheap attacks to trigger Strangle and Envenom simultaneously. Prioritize efficient block and draw to find powers quickly. Remove Strikes when possible.
- [map] Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.
### F23
- [card_reward] Committed to Envenom/Shiv/Strangle plan: setup Envenom and Afterimage, generate Shivs to apply poison and proc Strangle/Finisher. WLP holds combo pieces. Need more draw/cycling to find powers faster; skip non-synergistic attacks.
- [map] Foundation Retain-burst deck: using Envenom and Accelerant to enable poison and high-damage finishers. Focus on upgrading core scaling cards and removing basic Strikes to increase draw consistency for setup turns.
### F24
- [rest_site] Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.
### F25
- [card_reward] Committed poison/shiv hybrid: use Shivs from Leading Strike/Hidden Daggers to apply Envenom poison and stack Afterimage block. Use Hidden Daggers to clear hand clutter and enable Unceasing Top. Dig for Envenom+ early.
### F26
- [map] Foundation poison/retain plan: using Envenom and Accelerant to scale damage while retaining key cards for burst turns. Currently low on HP and missing reliable block; prioritizing safe nodes and upgrades over elites to ensure I reach the boss.
### F27
- [map] Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows; prioritize stabilizing HP before the next Elite.
### F28
- [rest_site] Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.
### F29
- [card_reward] Committed Envenom/Poison plan: use Leading Strike to generate Shivs, stack poison with Envenom, and burst with Accelerant. Need card draw and removal to find Envenom faster.
- [map] Foundation poison and retain strategy: leveraging Envenom and Accelerant for burst scaling while using Retain to time damage. Seeking more efficient block and card removals to shorten the time to reach key powers and protect against chip damage during setup.
### F30
- [card_reward] Committed to Envenom/Shiv poison scaling engine. Snecko Skull + Envenom+ makes every unblocked hit apply 3 Poison. Focus on drawing Envenom fast, retaining key pieces with WLP, and bursting with Shivs + Strangle. Skip generic damage; prioritize card draw, mitigation, and key upgrades.
- [map] Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.
### F31
- [card_reward] Committed Shiv/Poison hybrid plan: setup Envenom+, generate and play as many Shivs as possible, then use Knife Trap as a massive physical and Poison burst finisher. Focus on finding more card draw and block.
### F32
- [rest_site] Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.
### F33
- [card_select] Committed plan: Use Envenom and Afterimage with attacks to build poison and block. Play zero cost utility and cycle efficiently.
- [card_reward] Committed poison/shiv hybrid: use shivs to stack poison via Envenom+ and Snecko Skull, then finish with Accelerant+ or Strangle+. Retain key combo pieces with Well-Laid Plans. Skip pure physical attacks.
### F34
- [event] Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Apparitions and Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Ensure card draw is high to find Apparitions early; prioritize removing basic strikes.
- [map] Foundation phase: leveraging Envenom and Accelerant for Retain-based burst scaling. The deck needs better block density to survive setup turns and aggressive card removal of basic strikes at upcoming shops to increase draw consistency.
### F35
- [card_reward] Committed Shiv-Poison engine: use Envenom+ and Snecko Skull to make Shivs apply mass poison, then use Accelerant+ to burst. Retain Shiv generators for a huge Envenom turn.
### F36
- [hand_select] Holding Accelerant+ until I can stack more poison.
- [card_reward] Committed Envenom/Shiv/Poison engine: generate Shivs to stack poison via Envenom and trigger Strangle/Finisher, then use Accelerant+ or Knife Trap for burst. Prioritize fast draw and removal of basics; avoid expensive cards that disrupt Unceasing Top.
- [map] Committed poison/shiv hybrid: use Well-Laid Plans to hold Shivs for Envenom/Accelerant bursts. Prioritize shops for removals and high-value block/draw cards, and avoid Act 3 elites to preserve HP for the final boss.
### F37
- [card_reward] Committed Shiv/Poison engine: generate shivs to stack poison via Envenom and scale burst damage with Phantom Blades, Strangle, and Knife Trap. Prioritize cheap draw and block.
### F39
- [card_reward] Committed Shiv/Poison hybrid: play Envenom and Phantom Blades early, generate Shivs to stack poison and build Knife Trap damage, then finish with Accelerant or Knife Trap. Need to keep the deck thin to reliably find Apparitions and powers; prioritize card removal and high-impact draw/synergy pieces over basic attacks.
- [map] Committed Retain/Poison plan: use Well-Laid Plans to hold Shivs for Envenom/Accelerant bursts. Currently in survival mode due to low HP; prioritizing rest and avoiding Elites until stabilized.
### F40
- [rest_site] Committed to Retain/Poison burst plan: hold Apparitions and Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Ensure card draw is high to find Apparitions early; prioritize removing basic strikes.
### F41
- [map] Committed poison/retain plan: use Well-Laid Plans to hold Apparitions for key turns while Envenom and Shivs stack poison. Prioritize finding more draw to cycle into Apparitions quickly and remove remaining Strikes to increase deck density.
### F43
- [hand_select] Building hand for the incoming turn 4 attack.
- [card_reward] Committed plan: Use Envenom+ and Afterimage with Shivs to build poison and block. Prioritize drawing into powers and retain Apparitions for safety. Avoid adding generic cards that bloat the deck.
- [map] Committed poison-retain plan: use Well-Laid Plans to time Apparitions and Shivs with Envenom/Accelerant. Prioritize high draw to find intangibility pieces early. Focus on upgrading engine pieces at rest sites and removing basic strikes at shops.
### F44
- [rest_site] Committed poison/shiv burst plan: get Envenom and Phantom Blades down, retain Apparitions for safety, then spam shivs to stack poison and burst it with Accelerant. Upgraded Afterimage provides crucial passive block.
### F45
- [hand_select] Bursting an Apparition is a key survival strategy in this deck.
- [card_reward] Committed plan: Use Envenom and Afterimage with attacks to build poison and block. Play zero cost utility and cycle efficiently. Retain key cards, dump hand for Storm of Steel, then Unceasing Top keeps the turn going.
- [card_reward] Committed plan: Use Envenom and Afterimage with Shivs to build poison and block. Play zero cost utility and cycle efficiently. Keep deck lean, avoid expensive cards without discard/sly synergy.
- [map] Committed poison/retain plan: Use Well-Laid Plans to hold Apparitions for high-damage turns and stack poison via Envenom and Shivs. Prioritize card draw to find defensive pieces early and use Prayer Wheel monster rewards to hunt for catalysts or additional scaling. Avoid Act 3 elites to ensure survival to the boss.
### F46
- [card_reward] Committed Shiv/Poison hybrid plan: use Apparitions to survive while scaling damage through Phantom Blades, Envenom+, and Snecko Skull. Keep the deck lean and avoid adding unnecessary cards.
- [card_reward] Committed poison/shiv plan: Use shivs for immediate burst and Envenom stacking. Defend with Apparitions and Afterimage+. Accelerate boss kills with Bouncing Flask and Accelerant.
### F47
- [rest_site] Committed poison/shiv burst plan: get Envenom and Phantom Blades down, retain Apparitions for safety, then spam shivs to stack poison and burst it with Accelerant. Upgraded Afterimage provides crucial passive block. Avoid raw attacks; needs more draw.

### Combat Decision Digest (23 combats)
F2 [monster] Sludge Spinner (5R, HP 56->54, loss=2, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R2[Sludge Spinner: Atk(6), Buff]: Defend(+5blk)->Strike(4dmg)->Strike(4dmg) | dealt=8 taken=1
  R3[Sludge Spinner: Atk(11), Debuff]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=1
  R4[Sludge Spinner: Atk(9), Buff]: Neutralize(2dmg,1+Weak(1))->Strike(4dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R5[Sludge Spinner: Atk(17)]: Strike | dealt=0 taken=0

F4 [monster] multi:Toadpole+Toadpole (4R, HP 54->49, loss=5, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Leading Strike->Shiv(exhaust:1)->Shiv->Strike->Defend(+5blk) | dealt=0 taken=2
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike->Strike(6dmg) | dealt=6 taken=2
  R3[Toadpole: Atk(3x3=9)]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=1
  R4[Toadpole: Atk(7)]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike | dealt=11 taken=0

F5 [monster] multi:Corpse Slug+Corpse Slug (4R, HP 49->49, loss=0, WIN)
  R1[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Neutralize->Accelerant(power:+Accelerant(1))->Strike(6dmg)->Survivor(+8blk) | dealt=6 taken=0
  R3[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Strike(6dmg)->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Finisher(1+Strength(4)) | dealt=17 taken=0
  R4[Corpse Slug: Atk(7x2=14)]: Strike(power:-Accelerant,power:-Frail) | dealt=0 taken=0

F7 [monster] multi:Calcified Cultist+Seapunk (5R, HP 49->38, loss=11, WIN)
  R1[Calcified Cultist: Buff+Seapunk: Atk(11)]: Strangle(8dmg,1+Strangle(2))->Leading Strike(5dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Neutralize(5dmg,1+Weak(1))->Defend(2dmg,+5blk) | dealt=32 taken=3
  R2[Calcified Cultist: Atk(9)+Seapunk: Atk(2x4=8)]: Strike(6dmg)->Strike->Strike(6dmg) | dealt=17 taken=8
  R3[Seapunk: Buff, Defend]: Strike(6dmg)->Finisher(6dmg) | dealt=12 taken=0
  R4[Seapunk: Atk(12)]: Neutralize(1+Weak(1))->Leading Strike->Shiv(3dmg)->Shiv(4dmg)->Defend(+5blk)->Defend(+5blk) | dealt=7 taken=0
  R5[Seapunk: Atk(3x4=12)]: Strangle(8dmg,1+Strangle(2))->Strike | dealt=8 taken=0

F9 [monster] Sewer Clam (3R, HP 38->38, loss=0, WIN)
  R1[Sewer Clam: Atk(10)]: Strangle+(2dmg,1+Strangle(3))->Neutralize(6dmg,1+Weak(1))->Leading Strike(6dmg)->Shiv(7dmg,exhaust:1)->Shiv(7dmg)->Survivor(+8blk) | dealt=28 taken=0
  R2[Sewer Clam: Buff]: Strike->Strike(4dmg) | dealt=4 taken=0
  R3[Sewer Clam: Atk(14)]: Strike->Leading Strike(2dmg)->Shiv(4dmg)->Shiv(4dmg)->Finisher | dealt=10 taken=0

F13 [monster] Living Fog (3R, HP 38->30, loss=8, WIN)
  R1[Living Fog: Atk(8), CardDebuff]: Envenom(power:+Envenom(1))->Defend(+5blk) | dealt=0 taken=3
  R2[Living Fog: Atk(5), Summon]: Expose(1+Vulnerable(2),exhaust:1)->Leading Strike(4dmg,1+Poison(1))->Shiv(6dmg,1Poison(1→2),exhaust:1)->Shiv(6dmg,1Poison(2→3))->Accelerant(power:+Accelerant(1))->Strike(9dmg,1Poison(3→4)) | dealt=25 taken=5
  R3[Gas Bomb: DeathBlow(8)+Living Fog: Atk(8)]: Strangle+(15dmg,2Poison(2→3),+Strangle(3))->Leading Strike(7dmg,1Poison(3→4))->Shiv(9dmg,1Poison(4→5))->Shiv(9dmg,1Poison(5→6))->Strike(power:-Envenom,power:-Smoggy,power:-Accelerant) | dealt=40 taken=0

F15 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (6R, HP 30->23, loss=7, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Leg Sweep(+11blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(0x3=0)+Phantasmal Gardener: Atk(7)]: Expose(1+Vulnerable(2),exhaust:1)->Strangle+(15dmg,1+Strangle(3))->Leading Strike(3dmg)->Shiv(7dmg,exhaust:1)->Neutralize+(4+Weak(1),-Strength,-Vulnerable,-Strangle)->Defend(+5blk)->Shiv | dealt=25 taken=0
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(0x3=0)+Phantasmal Gardener: Buff]: Scrawl(exhaust:1)->Survivor(+8blk)->Strike*2 | dealt=0 taken=0
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)]: Strangle+->Leading Strike->Shiv->Shiv(4dmg)->Strike | dealt=4 taken=7
  R5[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(9)]: Neutralize+(4dmg,1+Weak(2))->Leading Strike->Shiv*2->Survivor(+8blk)->Defend(+5blk) | dealt=4 taken=0
  R6[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(2x3=6)]: Strangle+->Leading Strike->Shiv->Shiv(4dmg)->Finisher | dealt=4 taken=0

F17 [boss] Waterfall Giant (6R, HP 59->24, loss=35, WIN)
  R1[Waterfall Giant: Buff]: Envenom(power:+Envenom(1))->Strike(6dmg,1+Poison(1))->Neutralize+(4dmg,2Poison(1→2),+Weak(2)) | dealt=10 taken=0
  R2[Waterfall Giant: Atk(11), Debuff, Buff]: Accelerant(power:+Accelerant(1))->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=1
  R3[Waterfall Giant: Atk(10), Buff]: Expose(1+Vulnerable(2),exhaust:1)->Strangle+(11dmg,2+Poison(1),+Strangle(3))->Escape Plan(3dmg)->Leading Strike(6dmg,1Poison(1→2))->Shiv(7dmg,1Poison(2→3),exhaust:1)->Shiv(7dmg,1Poison(3→4))->Jackpot(31dmg,1Poison(4→5))->Backstab(15dmg,1Poison(5→6),exhaust:1)->Precise Cut(6dmg,1Poison(6→7))->Finisher(45dmg,1Poison(7→14)) | dealt=131 taken=10
  R4[Waterfall Giant: Heal, Buff]: Strike(9dmg,1Poison(12→13))->Strike(9dmg,1Poison(13→14))->Defend(+5blk) | dealt=18 taken=0
  R5[Waterfall Giant: Atk(20), Buff]: Defend(+5blk)->Defend(+5blk)->Leading Strike(3dmg,1Poison(12→13))->Shiv(4dmg,1Poison(13→14))->Shiv(4dmg,1Poison(14→15)) | dealt=11 taken=0
  R6[Waterfall Giant: DeathBlow(24)]: none | dealt=0 taken=24

F19 [monster] Thieving Hopper (5R, HP 60->58, loss=2, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=2
  R2[Thieving Hopper: Buff]: Expose(1+Vulnerable(2),exhaust:1)->Strangle+(15dmg,1+Strangle(3))->Leading Strike(7dmg)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Strike(12dmg) | dealt=52 taken=0
  R3[Thieving Hopper: Atk(21)]: Afterimage(power:+Afterimage(1))->Leg Sweep(+12blk,1+Weak(2))->Leading Strike(2dmg,+1blk,1Flutter(5→4))->Shiv(3dmg,+1blk,1Flutter(4→3))->Shiv(3dmg,+1blk,1Flutter(3→2)) | dealt=8 taken=0
  R4[Thieving Hopper: Atk(10)]: Neutralize+(2dmg,+1blk,2Flutter(2→1),Weak(1→3))->Escape Plan(+1blk)->Defend(+6blk)->Strike(3dmg,+1blk,1-Flutter)->Strike(6dmg,+1blk) | dealt=11 taken=0
  R5[Thieving Hopper: Escape]: Neutralize+(4dmg,+1blk,1Weak(2→4))->Leading Strike(3dmg,+1blk)->Shiv(power:-Afterimage) | dealt=7 taken=0

F23 [monster] multi:Bowlbug (Egg)+Bowlbug (Rock) (4R, HP 53->47, loss=6, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Egg): Atk(7), Defend]: Expose(1+Vulnerable(2),exhaust:1)->Escape Plan->Neutralize+(4dmg,1+Weak(2))->Backflip(+5blk)->Leading Strike(4dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Strike | dealt=26 taken=6
  R2[Bowlbug (Rock): Atk(11)]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=11 taken=0
  R3[Bowlbug (Rock): Stun]: Strangle+(10dmg,1+Strangle(3))->Leg Sweep(3dmg,+11blk,1+Weak(2))->Defend(3dmg,+5blk) | dealt=16 taken=0
  R4[Bowlbug (Rock): Atk(11)]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike | dealt=11 taken=0

F25 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (5R, HP 47->36, loss=11, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Neutralize+->Escape Plan(+3blk)->Leg Sweep(+11blk,1+Weak(2))->Backflip(+5blk) | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(10)+Exoskeleton: Buff]: Afterimage(power:+Afterimage(1))->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Defend(+6blk) | dealt=0 taken=11
  R3[Exoskeleton: Buff+Exoskeleton: Atk(10)+Exoskeleton: Buff+Exoskeleton: Atk(10)]: Leading Strike(+1blk)->Shiv(+1blk,exhaust:1)->Shiv(+1blk)->Leading Strike(+1blk)->Shiv(+1blk)->Shiv(+1blk)->Finisher(3dmg,+1blk)->Strike(6dmg,+1blk) | dealt=9 taken=0
  R4[Exoskeleton: Atk(10)+Exoskeleton: Atk(12)]: Escape Plan(+1blk)->Strangle+(9dmg,+1blk,1+Strangle(3))->Strike(9dmg,+1blk)->Expose(+1blk,2Strength(4→2),-Strangle,exhaust:1)->Defend(+6blk)->Finisher(12dmg,+1blk) | dealt=30 taken=0
  R5[Exoskeleton: Buff]: Leading Strike(3dmg,+1blk)->Neutralize+(4dmg,+1blk,1+Weak(2))->Shiv(4dmg,+1blk)->Shiv(power:-Afterimage,power:-Well-Laid Plans) | dealt=11 taken=0

F29 [elite] Infested Prism (7R, HP 70->68, loss=2, WIN)
  R1[Infested Prism: Atk(22)]: Neutralize+(4dmg,+1energy,1+Weak(2))->Expose(1+Vulnerable(2),exhaust:1)->Well-Laid Plans+(+7blk,power:+Well-Laid Plans(2))->Backflip(+5blk)->Survivor+(+11blk)->Leading Strike(4dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Hidden Daggers+->Shiv+(9dmg,exhaust:1)->Shiv+(9dmg) | dealt=38 taken=0
  R2[Infested Prism: Atk(12), Defend]: Strangle+(15dmg,1+Strangle(3))->Defend(3dmg,+5blk)->Defend(3dmg,+5blk)->Strike(12dmg) | dealt=33 taken=2
  R3[Infested Prism: Atk(9x3=27)]: Afterimage(power:+Afterimage(1))->Leg Sweep(+12blk,1+Weak(2))->Escape Plan(+4blk)->Defend(+6blk) | dealt=0 taken=0
  R4[Infested Prism: Buff, Defend]: Envenom+(+1blk,power:+Envenom(2))->Accelerant(+1blk,power:+Accelerant(1))->Hidden Daggers+->Shiv+(6dmg,+1blk,+1energy,1+Poison(2))->Shiv+(6dmg,+1blk,1Poison(2→4))->Backflip(+6blk)->Finisher(12dmg,+1blk,1Poison(4→8)) | dealt=24 taken=0
  R5[Infested Prism: Atk(26)]: Neutralize+(+1blk,1+Weak(2))->Escape Plan(+4blk)->Leading Strike(+1blk)->Shiv(+1blk)->Shiv(+1blk)->Strike(1dmg,+1blk,1Poison(6→8))->Defend(+6blk)->Defend(+6blk)->Defend(+6blk) | dealt=1 taken=0
  R6[Infested Prism: Atk(15), Defend]: Strangle+(10dmg,+1blk,2Poison(6→8),+Strangle(3))->Leading Strike(6dmg,+1blk,1Poison(8→10))->Shiv(7dmg,+1blk,1Poison(10→12))->Shiv(7dmg,+1blk,1Poison(12→14))->Leg Sweep(3dmg,+12blk,1Weak(1→3))->Survivor+(+11blk) | dealt=33 taken=0
  R7[Infested Prism: Atk(9x3=27)]: Escape Plan(+1blk)->Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Defend(+6blk)->Neutralize+(+1blk,1Weak(2→4)) | dealt=0 taken=0

F30 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (5R, HP 68->68, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Strangle+(10dmg,1+Strangle(3))->Leading Strike(6dmg)->Hidden Daggers+->Shiv(7dmg,exhaust:1)->Shiv(7dmg)->Shiv+(9dmg,exhaust:1)->Shiv+->Finisher(36dmg) | dealt=79 taken=0
  R2[Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Escape Plan(+3blk)->Leg Sweep(+11blk,1+Weak(2))->Well-Laid Plans+(+7blk,power:+Well-Laid Plans(2)) | dealt=0 taken=0
  R3[Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Afterimage(power:+Afterimage(1))->Envenom+(+1blk,power:+Envenom(2))->Strike(+1blk) | dealt=6 taken=0
  R4[Slumbering Beetle: Atk(16), Buff]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Neutralize+(6dmg,+1blk,2+Poison(3),+Weak(2))->Leading Strike(4dmg,+1blk,1Poison(3→6))->Shiv(6dmg,+1blk,1Poison(6→9))->Shiv(6dmg,+1blk,1Poison(9→12))->Accelerant(+1blk,power:+Accelerant(1))->Survivor+(+11blk)->Backflip(+6blk) | dealt=22 taken=0
  R5[Slumbering Beetle: Atk(13), Buff]: Leading Strike(4dmg,+1blk,1Poison(10→13))->Shiv(6dmg,+1blk,1Poison(13→16))->Shiv(6dmg,+1blk,1Poison(16→19))->Strike(9dmg,+1blk,1Poison(19→22))->Finisher(power:-Well-Laid Plans,power:-Afterimage,power:-Envenom,power:-Accelerant) | dealt=25 taken=0

F31 [monster] multi:Myte+Myte (5R, HP 68->68, loss=0, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Afterimage(+7blk,power:+Afterimage(1))->Escape Plan(+4blk)->Leading Strike(3dmg,+1blk)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Finisher(18dmg,+1blk) | dealt=29 taken=0
  R2[Myte: Atk(13)+Myte: StatusCard(2)]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Strangle+(15dmg,+1blk,1+Strangle(3))->Hidden Daggers+->Shiv+(12dmg,+1blk,exhaust:1)->Shiv+(+1blk,3-Strength,-Vulnerable,-Strangle)->Leg Sweep(+12blk,1+Weak(2)) | dealt=27 taken=0
  R3[Myte: Atk(3), Buff]: Envenom+(+1blk,power:+Envenom(2))->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Backflip(+6blk) | dealt=0 taken=0
  R4[Myte: StatusCard(2)]: Leading Strike(3dmg,+1blk,1+Poison(3))->Shiv(4dmg,+1blk,1Poison(3→6))->Shiv(4dmg,+1blk,1Poison(6→9))->Neutralize+(4dmg,+1blk,2Poison(9→12),+Weak(2))->Accelerant(+1blk,power:+Accelerant(1))->Defend(+6blk)->Defend(+6blk) | dealt=15 taken=0
  R5[Myte: Atk(11)]: Hidden Daggers+->Shiv+(6dmg,+1blk,1Poison(10→13))->Shiv+(6dmg,+1blk,1Poison(13→16))->Leading Strike(3dmg,+1blk,1Poison(16→19))->Shiv(4dmg,+1blk,1Poison(19→22))->Shiv(4dmg,+1blk,1Poison(22→25))->Strike(power:-Afterimage,power:-Envenom,power:-Well-Laid Plans,power:-Accelerant) | dealt=23 taken=0

F33 [boss] The Insatiable (8R, HP 68->35, loss=33, WIN)
  R1[The Insatiable: Buff, StatusCard(6)]: Expose(1+Vulnerable(2),exhaust:1)->Strangle+(15dmg,1+Strangle(3))->Afterimage(3dmg,+7blk,power:+Afterimage(1))->Neutralize+(9dmg,+1blk,1+Weak(2))->Escape Plan(3dmg,+4blk)->Strike(12dmg,+1blk) | dealt=42 taken=0
  R2[The Insatiable: Atk(6x2=12)]: Accelerant+(+1blk,power:+Accelerant(2))->Leading Strike(4dmg,+1blk)->Shiv(6dmg,+1blk,exhaust:1)->Shiv(6dmg,+1blk)->Frantic Escape(+1blk,1Sandpit(4→5))->Hidden Daggers+(+1blk)->Shiv+(9dmg,+1blk,exhaust:1)->Shiv+(9dmg,+1blk) | dealt=34 taken=4
  R3[The Insatiable: Atk(28)]: Envenom+(+1blk,power:+Envenom(2))->Defend(+6blk)->Survivor+(+11blk) | dealt=0 taken=9
  R4[The Insatiable: Buff]: Frantic Escape(+1blk,1Sandpit(3→4))->Frantic Escape(+1blk,1Sandpit(4→5))->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0
  R5[The Insatiable: Atk(10x2=20)]: Hand Trick(+7blk)->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Leading Strike(3dmg,+1blk,1+Poison(3))->Shiv(4dmg,+1blk,1Poison(3→6))->Shiv(4dmg,+1blk,1Poison(6→9))->Defend(+6blk)->Defend(+6blk) | dealt=11 taken=0
  R6[The Insatiable: Atk(10x2=20)]: Escape Plan(+1blk)->Frantic Escape(+1blk,1Sandpit(3→4))->Frantic Escape(+1blk,1Sandpit(4→5)) | dealt=0 taken=17
  R7[The Insatiable: Atk(30)]: Leg Sweep(+12blk,1+Weak(2))->Knife Trap(28dmg,+7blk,1Poison(3→21)) | dealt=28 taken=3
  R8[The Insatiable: Buff]: Strangle+(10dmg,+1blk,2Poison(18→21),+Strangle(3))->Hidden Daggers+->Shiv+(9dmg,+1blk,1Poison(21→24))->Shiv+(9dmg,+1blk,1Poison(24→27))->Finisher(21dmg,+1blk,1Poison(27→36))->Backflip(3dmg,+6blk)->Strike(9dmg,+1blk,1Poison(36→39)) | dealt=61 taken=0

F35 [monster] Devoted Sculptor (6R, HP 61->37, loss=24, WIN)
  R1[Devoted Sculptor: Buff]: Strike(6dmg) | dealt=6 taken=0
  R2[Devoted Sculptor: Atk(12)]: Leg Sweep(+11blk,1+Weak(2))->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg) | dealt=11 taken=0
  R3[Devoted Sculptor: Atk(15)]: Afterimage(+7blk,power:+Afterimage(1))->Expose(+1blk,1+Vulnerable(2),exhaust:1)->Defend(+6blk)->Strike(9dmg,+1blk)->Hidden Daggers+(+1blk)->Shiv+(9dmg,+1blk,exhaust:1)->Shiv+(9dmg,+1blk)->Apparition(+1blk,power:+Intangible(1)) | dealt=27 taken=0
  R4[Devoted Sculptor: Atk(30)]: Envenom+(+1blk,power:+Envenom(2))->Neutralize+(6dmg,+1blk,2+Poison(3),+Weak(2))->Knife Trap(30dmg,+5blk,1Poison(3→15)) | dealt=36 taken=15
  R5[Devoted Sculptor: Atk(29)]: Strangle+(10dmg,+1blk,2Poison(14→17),+Strangle(3))->Leading Strike(6dmg,+1blk,1Poison(17→20))->Shiv(7dmg,+1blk,1Poison(20→23))->Shiv(7dmg,+1blk,1Poison(23→26))->Escape Plan(3dmg,+4blk)->Leg Sweep(3dmg,+12blk,1Weak(1→3)) | dealt=36 taken=9
  R6[Devoted Sculptor: Atk(36)]: Strike(power:-Afterimage,power:-Envenom) | dealt=0 taken=0

F36 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (6R, HP 37->37, loss=0, WIN)
  R1[Scroll of Biting: Buff+Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)]: Neutralize+(4dmg,1+Weak(2))->Leg Sweep(+11blk)->Backflip(+5blk)->Hidden Daggers+->Shiv+(6dmg,exhaust:1)->Shiv+(6dmg) | dealt=16 taken=0
  R2[Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Buff+Scroll of Biting: Atk(3x2=6)]: Burst(power:+Burst(1))->Apparition(power:+Intangible(2),power:-Burst,exhaust:1)->Defend(+5blk) | dealt=0 taken=0
  R3[Scroll of Biting: Atk(1x2=2)+Scroll of Biting: Atk(1x2=2)+Scroll of Biting: Atk(1)]: Afterimage(+7blk,power:+Afterimage(1))->Apparition(+1blk,power:Intangible(1→2))->Leading Strike(3dmg,+1blk)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Leading Strike(3dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(+1blk,1+Strength(2)) | dealt=18 taken=0
  R4[Scroll of Biting: Atk(1)+Scroll of Biting: Atk(1)]: Strangle+(10dmg,+1blk,1+Strangle(3))->Well-Laid Plans+(3dmg,+1blk,power:+Well-Laid Plans(2))->Apparition(3dmg,+1blk,power:Intangible(1→2))->Strike(9dmg,+1blk)->Escape Plan(3dmg,+1blk) | dealt=28 taken=0
  R5[Scroll of Biting: Buff+Scroll of Biting: Buff]: Expose(+1blk,exhaust:1)->Envenom+(+1blk,power:+Envenom(2))->Leading Strike(+1blk)->Shiv(+1blk,2+Vulnerable(2),+Poison(3))->Shiv(6dmg,+1blk,1Poison(3→6))->Accelerant+(+1blk,power:+Accelerant(2)) | dealt=6 taken=0
  R6[Scroll of Biting: Atk(9x2=18)]: Strike(9dmg,+1blk,1Poison(3→6))->Finisher(power:-Afterimage,power:-Well-Laid Plans,power:-Envenom,power:-Accelerant) | dealt=9 taken=0

F37 [monster] Slimed Berserker (5R, HP 37->23, loss=14, WIN)
  R1[Slimed Berserker: StatusCard(10)]: Envenom+(+7blk,power:+Envenom(2))->Leading Strike(3dmg,1+Poison(3))->Shiv(4dmg,1Poison(3→6),exhaust:1)->Shiv(4dmg,1Poison(6→9))->Hidden Daggers+->Shiv+(6dmg,1Poison(9→12),exhaust:1)->Shiv+(6dmg,1Poison(12→15)) | dealt=23 taken=0
  R2[Slimed Berserker: Atk(4x4=16)]: Burst(power:+Burst(1))->Defend(+10blk,power:-Burst)->Survivor+(+11blk) | dealt=0 taken=0
  R3[Slimed Berserker: Debuff, Buff]: Expose(1+Vulnerable(2),exhaust:1)->Escape Plan(+3blk)->Leg Sweep(+11blk,1+Weak(2))->Leading Strike(4dmg,1Poison(13→16))->Shiv(6dmg,1Poison(16→19))->Shiv(6dmg,1Poison(19→22)) | dealt=16 taken=0
  R4[Slimed Berserker: Atk(24)]: Backflip(+5blk)->Defend(+5blk)->Strangle+(11dmg,2Poison(21→24),+Strangle(3))->Leading Strike(6dmg,1Poison(24→27))->Shiv(7dmg,1Poison(27→30))->Shiv(7dmg,1Poison(30→33))->Hidden Daggers+(3dmg)->Shiv+(9dmg,1Poison(33→36))->Shiv+(9dmg,1Poison(36→39)) | dealt=52 taken=14
  R5[Slimed Berserker: StatusCard(10)]: Accelerant+(power:+Accelerant(2))->Afterimage(power:+Afterimage(1))->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Neutralize+(3dmg,+1blk,2Poison(38→41),+Weak(2))->Strike(4dmg,+1blk,1Poison(41→44)) | dealt=7 taken=0

F39 [monster] multi:Axebot+Axebot (9R, HP 23->15, loss=8, WIN)
  R1[Axebot: Atk(5x2=10)+Axebot: Atk(8), Debuff]: Phantom Blades(+7blk,power:+Phantom Blades(9))->Phantom Blades(power:Phantom Blades(9→18))->Neutralize+->Defend(+5blk)->Defend(+5blk)->Expose(exhaust:1) | dealt=0 taken=0
  R2[Axebot: Atk(6), Debuff+Axebot: Atk(5x2=10)]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Survivor+(+8blk)->Hidden Daggers+->Shiv+(exhaust:1) | dealt=0 taken=8
  R3[Axebot: Atk(8), Debuff+Axebot: Buff]: Afterimage(power:+Afterimage(1))->Shiv+(+1blk)->Leading Strike(+1blk)->Shiv(+1blk,exhaust:1)->Shiv(+1blk) | dealt=0 taken=0
  R4[Axebot: Buff+Axebot: Atk(9x2=18)]: Burst(+1blk,power:+Burst(1))->Apparition(+2blk,power:+Intangible(2),power:-Burst)->Backflip(+6blk)->Defend(+6blk) | dealt=0 taken=0
  R5[Axebot: Atk(1x2=2)+Axebot: Atk(1x2=2)]: Escape Plan(+1blk)->Strangle+(+1blk)->Leading Strike(+1blk)->Shiv(+1blk)->Shiv(+1blk)->Knife Trap(+7blk) | dealt=0 taken=0
  R6[Axebot: Atk(6x2=12)+Axebot: Atk(12), Debuff]: Apparition(+1blk,power:+Intangible(1))->Envenom+(+1blk,power:+Envenom(2))->Accelerant+(+1blk,power:+Accelerant(2)) | dealt=0 taken=0
  R7[Axebot: Buff+Axebot: Atk(9x2=18)]: Leg Sweep(+9blk,1+Weak(2))->Defend(+4blk)->Defend(+4blk)->Hidden Daggers+->Shiv+(+1blk)->Shiv+(4dmg,+1blk,1+Poison(3))->Hidden Daggers+(+1blk)->Shiv+(4dmg,+1blk,1Poison(3→6))->Shiv+(4dmg,+1blk,1Poison(6→9)) | dealt=12 taken=0
  R8[Axebot: Buff]: Neutralize+(+1blk,4Stock(2→1),-Strength,-Weak,-Poison)->Leading Strike(3dmg,+1blk,1+Poison(3))->Shiv(22dmg,+1blk,1Poison(3→6))->Shiv(4dmg,+1blk,1Poison(6→9))->Leading Strike(3dmg,+1blk,1Poison(9→12))->Shiv(4dmg,+1blk,1Poison(12→15))->Shiv(4dmg,+1blk,1Poison(15→18))->Finisher(+1blk,2-Stock,-Poison)->Strike(6dmg,+1blk,1+Poison(3)) | dealt=46 taken=0
  R9[Axebot: Atk(9), Debuff]: Strangle+(+1blk,1+Strangle(3))->Burst(3dmg,+1blk,power:+Burst(1))->Backflip(6dmg,+12blk,power:-Burst)->Escape Plan(3dmg,+4blk)->Leading Strike(6dmg,+1blk,1+Poison(3))->Shiv(power:-Phantom Blades,power:-Well-Laid Plans,power:-Afterimage,power:-Envenom,power:-Accelerant) | dealt=18 taken=0

F43 [elite] Mecha Knight (7R, HP 48->33, loss=15, WIN)
  R1[Mecha Knight: Atk(25)]: Apparition(power:+Intangible(1),exhaust:1)->Well-Laid Plans+(+7blk,power:+Well-Laid Plans(2))->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Strike(6dmg) | dealt=17 taken=0
  R2[Mecha Knight: StatusCard(4)]: Neutralize+(4dmg,1Artifact(3→2))->Hidden Daggers+->Shiv+(6dmg,exhaust:1)->Shiv+(6dmg)->Strike(6dmg)->Knife Trap(20dmg) | dealt=42 taken=0
  R3[Mecha Knight: Defend, Buff]: Afterimage(power:+Afterimage(1))->Leading Strike(3dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Survivor+(+11blk)->Defend(+6blk) | dealt=11 taken=0
  R4[Mecha Knight: Atk(40)]: Backflip(+6blk)->Escape Plan(+1blk)->Leg Sweep(+12blk,1Artifact(2→1))->Defend(+6blk) | dealt=0 taken=15
  R5[Mecha Knight: StatusCard(4)]: Expose(+1blk,2+Vulnerable(2),-Artifact,exhaust:1)->Strangle+(15dmg,+1blk,1+Strangle(3))->Envenom+(3dmg,+1blk,power:+Envenom(2))->Leading Strike(7dmg,+1blk,1+Poison(3))->Shiv(9dmg,+1blk,1Poison(3→6))->Shiv(9dmg,+1blk,1Poison(6→9))->Hidden Daggers+(3dmg,+1blk)->Shiv+(12dmg,+1blk,1Poison(9→12))->Shiv+(12dmg,+1blk,1Poison(12→15)) | dealt=70 taken=0
  R6[Mecha Knight: Defend, Buff]: Hidden Daggers+->Phantom Blades(+1blk,power:+Phantom Blades(9))->Shiv+(22dmg,+1blk,1Poison(14→17))->Shiv+(9dmg,+1blk,1Poison(17→20))->Finisher(18dmg,+1blk,1Poison(20→26)) | dealt=49 taken=0
  R7[Mecha Knight: Atk(45)]: Neutralize+(+1blk,1+Weak(2))->Accelerant+(+1blk,power:+Accelerant(2))->Defend(+6blk)->Defend(+6blk)->Survivor+(+11blk)->Hidden Daggers+(+1blk)->Shiv+(4dmg,+1blk,1Poison(25→28))->Shiv+(6dmg,+1blk,1Poison(28→31)) | dealt=10 taken=0

F45 [monster] Fabricator (6R, HP 33->33, loss=0, WIN)
  R1[Fabricator: Summon]: Afterimage+(+7blk,power:+Afterimage(1))->Leading Strike(3dmg,+1blk)->Shiv(4dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Strike(6dmg,+1blk)->Survivor+(+11blk) | dealt=17 taken=0
  R2[Noisebot: StatusCard(2)+Stabbot: Atk(11), Debuff+Fabricator: Atk(18), Summon]: Backflip(+6blk)->Neutralize+(4dmg,+1blk,1+Weak(2))->Leg Sweep(+12blk,1+Weak(2))->Phantom Blades(+1blk,power:+Phantom Blades(9))->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2)) | dealt=4 taken=0
  R3[Noisebot: StatusCard(2)+Stabbot: Atk(8), Debuff+Fabricator: Atk(8)+Zapbot: Atk(16)]: Strangle+(10dmg,+1blk,1+Strangle(3))->Defend(3dmg,+4blk)->Hidden Daggers+->Shiv+(+1blk,exhaust:1)->Leading Strike(3dmg,+1blk)->Shiv+(6dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(+1blk)->Finisher(36dmg,+1blk) | dealt=73 taken=0
  R4[Noisebot: StatusCard(2)+Fabricator: Summon]: Strike(6dmg,+1blk)->Defend(+6blk)->Defend(+6blk) | dealt=6 taken=0
  R5[Noisebot: StatusCard(2)+Noisebot: StatusCard(2)+Fabricator: Atk(11)+Stabbot: Atk(11), Debuff]: Apparition(+1blk,power:+Intangible(1))->Accelerant+(+1blk,power:+Accelerant(2))->Leading Strike(3dmg,+1blk)->Shiv(13dmg,+1blk)->Shiv(+1blk)->Hidden Daggers+(+1blk)->Shiv+(6dmg,+1blk)->Shiv+(6dmg,+1blk)->Phantom Blades(+1blk,power:Phantom Blades(9→18))->Expose(+1blk,1+Vulnerable(2),exhaust:1) | dealt=32 taken=0
  R6[Noisebot: StatusCard(2)+Noisebot: StatusCard(2)+Fabricator: Summon]: Escape Plan(+4blk)->Burst(+1blk,power:+Burst(1))->Knife Trap(power:-Afterimage,power:-Phantom Blades,power:-Well-Laid Plans,power:-Accelerant,power:-Burst) | dealt=0 taken=0

F46 [monster] Globe Head (3R, HP 33->33, loss=0, WIN)
  R1[Globe Head: Atk(13), Debuff]: Apparition(power:+Intangible(1),exhaust:1)->Afterimage+(+6blk,power:+Afterimage(1))->Envenom+(power:+Envenom(2))->Hidden Daggers+->Shiv+(6dmg,+1blk,1+Poison(3),exhaust:1)->Shiv+(6dmg,+1blk,1Poison(3→6)) | dealt=12 taken=0
  R2[Globe Head: Atk(6x3=18)]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Storm of Steel(+1blk)->Shiv(6dmg,+1blk,1Poison(5→8),exhaust:1)->Shiv(6dmg,+1blk,1Poison(8→11))->Shiv(6dmg,+1blk,1Poison(11→14))->Strangle+(15dmg,+1blk,2Poison(14→17),+Strangle(3))->Strike(12dmg,+1blk,1Poison(17→20))->Leg Sweep(3dmg,+9blk,1+Weak(2)) | dealt=48 taken=0
  R3[Globe Head: Atk(12), Buff]: Apparition(+1blk,power:+Intangible(1))->Leading Strike(4dmg,+1blk,1Poison(19→22))->Shiv(6dmg,+1blk,1Poison(22→25))->Shiv(6dmg,+1blk,1Poison(25→28))->Leading Strike(4dmg,+1blk,1Poison(28→31))->Shiv(6dmg,+1blk,1Poison(31→34))->Shiv(6dmg,+1blk,1Poison(34→37)) | dealt=32 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (10R, HP 61->18, loss=43, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Afterimage+(+7blk,power:+Afterimage(1))->Leg Sweep(+12blk,1+Weak(2))->Strangle+(10dmg,+1blk,1+Strangle(3))->Hidden Daggers+->Haze | dealt=16 taken=0
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Escape Plan(+4blk)->Bouncing Flask+(+1blk,1Poison(4→12),1Poison(4→12))->Survivor+(+11blk)->Hidden Daggers+(+1blk)->Shiv+(6dmg,+1blk,exhaust:1)->Shiv+(6dmg,+1blk)->Strike(6dmg,+1blk)->Defend(+6blk) | dealt=18 taken=0
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Neutralize+(3dmg,+1blk,1+Weak(2))->Leading Strike(2dmg,+1blk)->Shiv(3dmg,+1blk,exhaust:1)->Shiv(3dmg,+1blk)->Leading Strike(2dmg,+1blk)->Shiv(3dmg,+1blk)->Shiv(3dmg,+1blk) | dealt=19 taken=20
  R4[Torch Head Amalgam: Atk(16)+Queen: Buff, Defend]: Accelerant+(+1blk,power:+Accelerant(2))->Apparition(+1blk,power:+Intangible(1),exhaust:1)->Expose(+1blk,1+Vulnerable(2),exhaust:1) | dealt=0 taken=0
  R5[Torch Head Amalgam: Atk(24)+Queen: Buff, Defend]: Backflip(+4blk)->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Defend(+4blk)->Leading Strike(+1blk)->Shiv(+1blk)->Shiv(+1blk) | dealt=0 taken=12
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Envenom+(+1blk,power:+Envenom(2))->Apparition(+1blk,power:+Intangible(1))->Storm of Steel(+2blk,1Poison(4→9),1Poison(4→9))->Shiv(3dmg,+1blk,1Poison(9→12))->Shiv(3dmg,+1blk,1Poison(12→15))->Shiv(3dmg,+1blk,1Poison(15→18))->Shiv(3dmg,+1blk,1Poison(18→21)) | dealt=12 taken=0
  R7[Torch Head Amalgam: Atk(27)+Queen: Buff, Defend]: Neutralize+(3dmg,+1blk,2Poison(18→21),+Weak(2))->Leg Sweep(+9blk,1Weak(2→4))->Defend(+4blk) | dealt=3 taken=0
  R8[Queen: Atk(7x5=35)]: Survivor+(+8blk)->Defend(+4blk)->Leading Strike(2dmg,+1blk,1Poison(3→6))->Shiv+(4dmg,+1blk,1Poison(6→9))->Shiv(3dmg,+1blk,1Poison(9→12))->Shiv(3dmg,+1blk,1Poison(12→15)) | dealt=12 taken=18
  R9[Queen: Atk(25)]: Escape Plan(+1blk)->Leading Strike(2dmg,+1blk,1Poison(12→15))->Shiv(3dmg,+1blk,1Poison(15→18))->Shiv(3dmg,+1blk,1Poison(18→21))->Strike(4dmg,+1blk,1Poison(21→24))->Finisher(16dmg,+1blk,1Poison(24→36))->Hidden Daggers+->Shiv+(4dmg,+1blk,1Poison(36→39))->Shiv+(4dmg,+1blk,1Poison(39→42)) | dealt=36 taken=0
  R10[Queen: Buff]: Strangle+(7dmg,+1blk,2Poison(39→42),+Strangle(3))->Leading Strike(5dmg,+1blk,1Poison(42→45))->Shiv(6dmg,+1blk,1Poison(45→48))->Shiv(6dmg,+1blk,1Poison(48→51)) | dealt=24 taken=0

### Non-combat Decisions (197 decisions)
F1 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->14
  deck_change: added Accelerant
  reasoning: Arcane Scroll provides a random Rare card which often acts as an immediate power spike or run-defining anchor for the Silent, letting us path aggressively in Act 1.
  strategic_note: Foundation phase: relying on basic strikes and defends. Look for early premium damage cards to take on elites, and lean into whatever the random rare card dictates.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting the Act 1 gauntlet of monsters to build gold and draft early damage cards as per the Route Intelligence recommendations.
  strategic_note: Foundation phase: relying on basic strikes and defends; looking for early premium damage cards to take on elites, and leaning into whatever the random rare card dictates.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 99->109 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 109->109 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 109->109 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 54->54 | Gold 109->109 | Deck 14->15
  deck_change: picked Leading Strike
  reasoning: We are in Phase 1 (Foundation) and desperately need frontload damage for Act 1. While we have Accelerant and want to build a poison engine, Bubble Bubble is literally a curse until we find our first poison applicator. Leading Strike provides 11 damage for 1 energy, which helps us survive early hallway fights and Elites while we look for a reliable poison source.
  strategic_note: Foundation plan: survive with frontload damage like Leading Strike while looking for a reliable poison applicator to pair with Accelerant. Avoid taking conditional poison cards until we have a base applicator.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 109->109 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Unknown

F3 [event] choose_event_option (option_index=0) | source=llm
  HP 54->54 | Gold 109->166 | Deck 15->15
  deck_change: no deck change
  reasoning: Greed is an Eternal curse, meaning it can never be removed from the deck. A permanent dead draw for the entire run is not worth 331 gold, especially this early when deck consistency is crucial. 57 gold for free is the safe and correct play.
  strategic_note: Foundation phase: relying on basic strikes/defends, looking for early premium damage. Avoiding permanent curses is critical.

F3 [event] choose_event_option (option_index=0) | source=auto
  HP 54->54 | Gold 166->166 | Deck 15->15
  deck_change: no deck change
  reasoning: Only option: Proceed

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 166->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 166->178 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 178->178 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 49->49 | Gold 178->178 | Deck 15->16
  deck_change: picked Finisher
  reasoning: Finisher synergizes perfectly with Leading Strike and Neutralize, providing a massive burst damage combo for just 1 energy (up to 24 damage with Neutralize + Leading Strike + 2 Shivs). This solves our immediate damage needs and fits the shiv trajectory.
  strategic_note: Foundation plan: build around shiv generation and attack spam for Finisher burst, looking for a core scaling engine like Accuracy or more shiv generators. Keep deck lean and add block.

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 178->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 178->192 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 192->192 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 49->49 | Gold 192->192 | Deck 16->17
  deck_change: picked Strangle
  reasoning: Strangle is a phenomenal damage multiplier for decks that play many cards per turn, acting as a core payoff for Shivs. We already have Leading Strike and Neutralize, and we need raw damage to survive Act 1 elites and burst down the Waterfall Giant before its explosion scales out of control. Tools of the Trade is a strong Rare, but we desperately need immediate damage scaling, not passive filtering.
  strategic_note: Foundation plan transitioning to Shivs: prioritize 0-cost cards, Shiv generation, and multi-play payoffs like Strangle/Finisher. Need block/dex scaling and draw to support the high-cycle damage engine.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 192->192 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Unknown

F6 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 49->49 | Gold 192->93 | Deck 17->17
  deck_change: no deck change
  reasoning: Enchanting 2 cards with Steady (Retain) for 99 gold provides incredible consistency. We can retain combo-reliant damage cards like Finisher and Strangle until we draw our enabler (Leading Strike), guaranteeing massive burst damage turns for upcoming Elites.
  strategic_note: Foundation phase: relying on basic strikes/defends, with powerful burst combos through Retain on Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle.

F6 [card_select] select_deck_card (option_index=13) | source=llm
  HP 49->49 | Gold 93->93 | Deck 17->17
  deck_change: no deck change
  reasoning: Leading Strike generates 0-cost cards, which perfectly fuels Strangle's per-card-played damage. Enchanting both of our core engine pieces gives us the best chance to increase their efficiency or damage output.
  strategic_note: Foundation plan: currently leaning into a Shiv/spam engine with Leading Strike, Strangle, and Finisher. Need efficient card draw and block to support playing multiple cards per turn. Look for discard/draw synergies and avoid heavy, expensive cards.

F6 [event] choose_event_option (option_index=0) | source=auto
  HP 49->49 | Gold 93->93 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 49->49 | Gold 93->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 93->101 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 101->101 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F7 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 38->38 | Gold 101->101 | Deck 17->18
  deck_change: picked Leading Strike
  reasoning: Our deck has a core Strangle and Finisher engine, which heavily relies on playing multiple cards/attacks per turn. A second Leading Strike provides essential fuel (Shivs) to maximize these burst damage turns.
  strategic_note: Committed Shiv/Strangle plan: retain Strangle and Leading Strike for burst turns with Finisher. We need reliable block, more draw, and more Shiv generation to scale this engine.

F7 [map] choose_map_node (option_index=0) | source=llm
  HP 38->38 | Gold 101->101 | Deck 18->18
  deck_change: no deck change
  reasoning: Current HP (38/70) is low enough that a rest site is necessary for safety before the next string of encounters, especially given the 'Crucial First Rest' intelligence. Following the recommended route also leads toward a shop with more gold and a treasure chest.
  strategic_note: Foundation phase: relying on basic strikes and defends; looking for early premium damage cards to take on elites, and leaning into whatever the random rare card dictates.

F8 [rest_site] choose_rest_option (option_index=1, smith_card_index=15, note_scope=run, note_triggers=all) | source=llm
  HP 38->38 | Gold 101->101 | Deck 18->18
  deck_change: upgraded Strangle->Strangle+
  reasoning: HP is safe enough to survive the upcoming hallway fight, and we have another rest site at F11 before the elite. Strangle is our main retained burst card, and increasing the HP loss per card played from 2 to 3 creates massive scaling damage when combined with Leading Strikes and Shivs.
  strategic_note: Foundation phase: relying on basic strikes/defends, with powerful burst combos through Retain on Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle.

F8 [rest_site] proceed | source=auto
  HP 38->38 | Gold 101->101 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 101->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 101->114 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 114->114 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Fysh Oil

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 114->114 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F9 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 38->38 | Gold 114->114 | Deck 18->19
  deck_change: picked Expose
  reasoning: Expose is a 0-cost card that applies Vulnerable and strips block, which is excellent for setting up our massive burst turns with Strangle+, Shivs, and Finisher. Being 0-cost means it fuels Strangle+ for free while amplifying the damage of our Shivs and Finisher.
  strategic_note: Committed Shiv/Strangle plan: stack Shiv generators and cheap cycle cards in hand, play Strangle+, then dump all 0-cost attacks and finish with Finisher. Avoid expensive cards that clog the Strangle turn.

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 114->114 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 38->38 | Gold 114->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim: Regal Pillow

F10 [treasure] proceed | source=random
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: I am at 38/70 HP and have an elite fight coming up later in the act. The route recommends a Rest Site here, which is essential to either stabilize my health or, ideally, upgrade a key card like Finisher or Strangle to improve my burst potential. Following the 'Crucial First Rest' intelligence helps ensure survival through the mid-act.
  strategic_note: Foundation phase: leveraging Retain on Finisher and Strangle for burst windows. Seeking multi-hit cards or poison to scale damage, while prioritizing upgrades to improve damage-per-energy efficiency before the late-act Elite.

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=10) | source=llm
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: Upgrading Neutralize to apply 2 Weak instead of 1 is one of the highest-value early upgrades, significantly reducing incoming damage for the upcoming Elite and Boss. While we have Regal Pillow, 38 HP is enough to traverse the Shop and ? nodes safely, and we can heal at the Rest Site on Floor 16 after the Elite if needed.
  strategic_note: Foundation phase: relying on basic strikes/defends, with burst combos through Retain on Leading Strike/Finisher/Strangle. Look for poison to enable Accelerant or more shiv/multi-attack cards for Finisher/Strangle. Prioritize removing basic strikes to improve combo consistency.

F11 [rest_site] proceed | source=auto
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=1) | source=llm
  HP 38->38 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the planned route to the Shop. With 150 gold and 38 HP, this is a critical opportunity to remove a basic card (Strike) and look for a key engine piece (shiv generation or poison) or a high-impact relic. This visit precedes a stretch of unknowns and an elite, so strengthening the deck now is vital.
  strategic_note: Foundation phase: relying on basic strikes/defends with burst potential from Finisher and Strangle. Seeking shiv generation or poison to scale damage, while prioritizing card removals at shops to increase draw consistency for high-impact turns.

F12 [shop] buy_card (option_index=4) | source=plan
  HP 38->38 | Gold 150->75 | Deck 19->20
  deck_change: bought Envenom
  reasoning: Shop plan [1/2]: Envenom turns our Leading Strikes (Shivs) into a massive poison engine, instantly unlocking our win condition and making our Accelerant highly valuable.

F12 [shop] remove_card_at_shop | source=plan
  HP 38->38 | Gold 75->75 | Deck 20->20
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Removing a Strike increases the consistency of drawing our key engine pieces (Envenom, Strangle, Leading Strike).

F12 [card_select] select_deck_card (option_index=0) | source=llm
  HP 38->38 | Gold 75->0 | Deck 20->19
  deck_change: lost Strike
  reasoning: Strikes are our weakest cards and do not synergize with our Strangle, Envenom, or Shiv cards. Removing a Strike improves consistency for drawing our core combo pieces.
  strategic_note: Committed shiv/strangle plan: use Leading Strikes and shivs to trigger Strangle and Envenom heavily. Accelerant synergizes with Envenom. Need defensive scaling, draw, and energy; avoid adding more low-impact attacks.

F12 [shop] close_shop_inventory | source=llm
  HP 38->38 | Gold 0->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F12 [shop] proceed | source=auto
  HP 38->38 | Gold 0->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 0->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Unknown

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 0->14 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 14->14 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F13 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 30->30 | Gold 14->14 | Deck 19->20
  deck_change: picked Leg Sweep
  reasoning: Leg Sweep provides excellent defensive value and Weak application, which will help us survive the heavy attacks from the upcoming boss and Act 2 elites. Our damage engine (Envenom, Strangle, Leading Strikes, Finisher) is coming together, but our defense is currently just basic Defends and Survivor.
  strategic_note: Engine established: Use Strangle+ and Shivs (Leading Strike, Finisher) alongside Envenom for massive burst turns. Prioritize defense, draw, and energy to support this engine. Skip off-plan expensive attacks.

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 14->14 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Unknown

F14 [event] choose_event_option (option_index=1) | source=llm
  HP 30->30 | Gold 14->14 | Deck 20->20
  deck_change: no deck change
  reasoning: Trading the Fysh Oil for an Upgraded Uncommon Power is excellent long-term value. Silent's uncommon powers (Footwork, Noxious Fumes, Well-Laid Plans, Accuracy) are incredibly strong and synergize well with our Envenom, Accelerant, and Shiv cards.
  strategic_note: Foundation phase: relying on burst combos through Retain on Leading Strike/Strangle. Look for poison to enable Accelerant or more shiv generation. Upgraded Uncommon Power provides scaling for Act 1 Boss and beyond.

F14 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 30->30 | Gold 14->14 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F14 [event] choose_event_option (option_index=0) | source=auto
  HP 30->30 | Gold 14->14 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 14->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Elite

F15 [card_select] select_deck_card (option_index=2) | source=llm
  HP 30->30 | Gold 14->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Scrawl will draw cards until the hand is full, giving us a massive number of options to block the incoming 7 damage and deal as much damage as possible this turn.
  strategic_note: Foundation phase: relying on basic strikes/defends, with burst combos through Retain on Leading Strike/Finisher/Strangle.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 23->23 | Gold 14->47 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 33 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 23->23 | Gold 47->47 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 23->23 | Gold 47->47 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim relic: Unceasing Top

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 23->23 | Gold 47->47 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 23->23 | Gold 47->47 | Deck 20->21
  deck_change: picked Escape Plan
  reasoning: Escape Plan is a 0-cost card that replaces itself, effectively thinning the deck while providing a free card play to trigger Strangle's effect. It occasionally provides block and helps cycle through our 20-card deck to find core pieces like Envenom and Strangle.
  strategic_note: Committed to Strangle/Shiv/Envenom engine. Retain combo pieces to unleash burst turns, while Envenom stacks poison for long fights. Need more draw, Shiv generators, and efficient block. Avoid expensive non-combo cards.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 23->23 | Gold 47->47 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 23->59 | Gold 47->47 | Deck 21->21
  deck_change: no deck change
  reasoning: Boss is next and 23 HP is far too low to survive the Act 1 boss fight. With Regal Pillow, resting provides an extra 15 HP, healing for a total of 36 HP to bring us up to a safe 59 HP.
  strategic_note: Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F16 [rest_site] proceed | source=auto
  HP 59->59 | Gold 47->47 | Deck 21->21
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 47->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [card_select] select_deck_card (option_index=2) | source=llm
  HP 58->58 | Gold 47->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Jackpot costs 0 this turn thanks to the Colorless Potion. It deals 25 base damage, acts as an attack to trigger Strangle, and adds 3 more 0-cost cards to the hand. These generated cards will provide even more Strangle triggers and fuel Finisher for massive burst damage on this pivotal boss turn.
  strategic_note: Committed Envenom/Poison plan: use Leading Strike to generate Shivs, stack poison with Envenom, and burst with Accelerant. Needs cheap draw, energy, and mitigation; avoid off-plan damage.

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 24->24 | Gold 47->122 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 24->24 | Gold 122->122 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 24->24 | Gold 122->122 | Deck 21->22
  deck_change: picked Afterimage
  reasoning: Afterimage provides crucial passive block scaling for a deck that relies heavily on playing multiple cards per turn (Shivs via Leading Strike, Strangle, Escape Plan). It combos incredibly well with Shivs and Unceasing Top to turn offensive engine turns into massive block turns, solving defense for the rest of the run.
  strategic_note: Foundation plan: Use Shivs and low-cost attacks to fuel Strangle and Afterimage, cycling with Escape Plan and Unceasing Top. Prioritize exhaust/discard outlets and 0-cost cards; skip heavy, expensive cards that break Unceasing Top.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 24->60 | Gold 122->122 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 122->122 | Deck 22->22
  deck_change: no deck change
  reasoning: With 3 energy and a heavy setup/combo deck featuring Envenom (2), Leg Sweep (2), and a need to string together multiple cheap attacks (Strangle, Leading Strike, Finisher), we desperately need energy. Pael's Flesh provides a delayed but massive +1 energy starting on turn 3 with no downside, perfectly aligning with when our setup is complete and we are ready to unleash burst damage.
  strategic_note: Foundation phase: relying on burst combos through Retain (Leading Strike, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 122->122 | Deck 22->22
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 60->60 | Gold 122->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended route towards the Monster node at (c4, r1). Act 2 starts are notoriously difficult, and I need to gather more card rewards to solidify my damage engine before hitting shops or elites. This path keeps me flexible for the middle of the act.
  strategic_note: Foundation phase: leveraging Finisher and Strangle for burst damage while hunting for Shiv generation or Poison to scale. Card removal is a priority to increase the density of high-impact cards, so I am pathing to accumulate gold and card rewards early in the act.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 122->137 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 137->137 | Deck 21->22
  deck_change: picked Finisher
  reasoning: Claim specialcard: Take your stolen card back.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 137->137 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 58->58 | Gold 137->137 | Deck 22->23
  deck_change: picked Backflip
  reasoning: The deck has established a strong Shiv engine with Strangle+, Envenom, and Afterimage, but severely lacks card draw to find these core pieces quickly. Backflip provides essential cycle and defense while keeping the deck flowing.
  strategic_note: Committed shiv/strangle/envenom plan: play shivs with Strangle+ and Envenom for massive damage, while Afterimage provides sustained defense. Needs more draw (Acrobatics/Backflip) to find powers and cycle shiv generators quickly. Avoid bulky high-cost cards.

F19 [map] choose_map_node (option_index=1) | source=llm
  HP 58->58 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which mandates avoiding combats and elites early to preserve HP. The Unknown node offers the possibility of an event or treasure, both of which are generally safer than a hallway monster given Silent's need to stabilize her defense in Act 2.
  strategic_note: Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F20 [event] choose_event_option (option_index=1) | source=llm
  HP 58->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Losing 5 HP is a very minor cost for a Colorless card reward. Colorless cards like Finesse or Flash of Steel are extremely valuable for a deck relying on 0-cost cycling, Strangle procs, and Afterimage, especially with Unceasing Top.
  strategic_note: Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F20 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F20 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F20 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. Act 2 hallway fights are notoriously dangerous for decks that are still in the foundation phase; Unknown nodes provide a chance for events, shops, or treasures that can strengthen the deck without the high HP risk of a combat.
  strategic_note: Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F21 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Only option: Proceed

F21 [map] choose_map_node (option_index=0) | source=llm
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. Act 2 hallway fights are notoriously dangerous for Silent, and the current deck needs more refinement (removals and block) before taking on more combats. Unknown nodes provide opportunities for events that can remove cards, grant relics, or provide gold without the high HP risk of a combat node.
  strategic_note: Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.

F22 [event] proceed | source=auto
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Event finished, proceed

F22 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 53->53 | Gold 137->137 | Deck 23->23
  deck_change: no deck change
  reasoning: Removing a basic Strike is exactly what the deck needs to improve consistency for drawing our Retain combo pieces and key powers. Enlightenment would just clutter the deck since most of our cards are already 1-cost or 0-cost.
  strategic_note: Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.

F22 [card_select] select_deck_card (option_index=0) | source=llm
  HP 53->53 | Gold 137->12 | Deck 23->22
  deck_change: lost Strike
  reasoning: Strike is our weakest card, providing only 6 base damage for 1 energy. Removing it improves consistency for our Strangle, Shivs, and Envenom synergy.
  strategic_note: Committed engine plan: play Strangle, Envenom, and Afterimage, then spam Shivs and cheap attacks to trigger Strangle and Envenom simultaneously. Prioritize efficient block and draw to find powers quickly. Remove Strikes when possible.

F22 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 12->12 | Deck 22->22
  deck_change: no deck change
  reasoning: Only option: Proceed

F22 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 12->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which prioritizes avoiding combats and elites to preserve HP. The 'Unknown' node (c6,r5) offers a chance for an event, shop, or treasure, which is safer than a guaranteed Monster fight at this stage of Act 2.
  strategic_note: Foundation phase: relying on Retain burst combos (Leading Strike, Finisher, Strangle) enabled by Envenom + Accelerant for poison scaling. Needs card removals for basic strikes and more draw/block to survive setup turns.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 12->25 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 25->25 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 47->47 | Gold 25->25 | Deck 22->23
  deck_change: picked Well-Laid Plans+
  reasoning: Well-Laid Plans+ is an excellent enabler for our combo-heavy deck. It allows us to hold Finisher or Strangle until we have our Shiv generators, or hold defensive cards like Leg Sweep for big attacks. It also helps manage hands during the Act 2 boss status flood.
  strategic_note: Committed to Envenom/Shiv/Strangle plan: setup Envenom and Afterimage, generate Shivs to apply poison and proc Strangle/Finisher. WLP holds combo pieces. Need more draw/cycling to find powers faster; skip non-synergistic attacks.

F23 [map] choose_map_node (option_index=0) | source=llm
  HP 47->47 | Gold 25->25 | Deck 23->23
  deck_change: no deck change
  reasoning: Following the established route to a Rest Site. With 47 HP and a deck still in the 'foundation' phase, taking an elite fight right now is unnecessarily risky. The Rest Site allows for a critical upgrade to improve deck scaling or stability before the upcoming mandatory combats.
  strategic_note: Foundation Retain-burst deck: using Envenom and Accelerant to enable poison and high-damage finishers. Focus on upgrading core scaling cards and removing basic Strikes to increase draw consistency for setup turns.

F24 [rest_site] choose_rest_option (option_index=1, smith_card_index=13, note_scope=run, note_triggers=all) | source=llm
  HP 47->47 | Gold 25->25 | Deck 23->23
  deck_change: upgraded Envenom->Envenom+
  reasoning: With 47/70 HP and Regal Pillow, resting would over-heal and waste value. We have an elite fight coming up eventually, but can survive the next monster. Upgrading Envenom is arguably the most impactful upgrade for our deck: it doubles our poison output from all attacks, turning our Shiv-generators (Leading Strike) into incredible scaling engines. This solidifies our boss-killing capability.
  strategic_note: Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.

F24 [rest_site] proceed | source=auto
  HP 47->47 | Gold 25->25 | Deck 23->23
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 47->47 | Gold 25->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Monster

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 25->39 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 39->39 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Fairy in a Bottle

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 39->39 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F25 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 36->36 | Gold 39->39 | Deck 23->24
  deck_change: picked Hidden Daggers
  reasoning: Hidden Daggers costs 0, fuels our Envenom+/Afterimage+/Finisher engine by generating 2 Shivs, and crucially allows us to discard unplayable or expensive cards to empty our hand and trigger Unceasing Top.
  strategic_note: Committed poison/shiv hybrid: use Shivs from Leading Strike/Hidden Daggers to apply Envenom poison and stack Afterimage block. Use Hidden Daggers to clear hand clutter and enable Unceasing Top. Dig for Envenom+ early.

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 39->39 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 36->36 | Gold 39->74 | Deck 24->24
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 36->36 | Gold 74->74 | Deck 24->24
  deck_change: upgraded Hidden Daggers->Hidden Daggers+, Survivor->Survivor+
  reasoning: Claim: War Paint

F26 [treasure] proceed | source=random
  HP 36->36 | Gold 74->74 | Deck 24->24
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=llm
  HP 36->36 | Gold 74->74 | Deck 24->24
  deck_change: no deck change
  reasoning: With 36 HP and a deck still in the foundation phase, an Elite fight is too risky. The Unknown node at c4,r9 is the safest path toward the next Rest Site where I can upgrade or heal before the mandatory Elite at the end of the act. The route intelligence confirms avoiding Elites in early Act 2 is mandatory for survival.
  strategic_note: Foundation poison/retain plan: using Envenom and Accelerant to scale damage while retaining key cards for burst turns. Currently low on HP and missing reliable block; prioritizing safe nodes and upgrades over elites to ensure I reach the boss.

F27 [treasure] proceed | source=random
  HP 36->36 | Gold 74->74 | Deck 24->24
  deck_change: no deck change
  reasoning: Proceed from treasure

F27 [treasure] open_chest | source=random
  HP 36->36 | Gold 74->108 | Deck 24->24
  deck_change: no deck change
  reasoning: Open chest

F27 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 36->36 | Gold 108->108 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim: Permafrost

F27 [treasure] proceed | source=random
  HP 36->36 | Gold 108->108 | Deck 24->24
  deck_change: no deck change
  reasoning: Proceed from treasure

F27 [map] choose_map_node (option_index=0) | source=llm
  HP 36->36 | Gold 108->108 | Deck 24->24
  deck_change: no deck change
  reasoning: With 36/70 HP and an Elite fight approaching in two floors, a Rest Site is mandatory to ensure survival. While I usually prefer Smithing, the current HP total is dangerously low for Act 2 Elites, and I need a buffer to avoid a premature end to the run. This aligns with the 'Strict HP Thresholds' route intelligence.
  strategic_note: Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows; prioritize stabilizing HP before the next Elite.

F28 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 36->70 | Gold 108->108 | Deck 24->24
  deck_change: no deck change
  reasoning: I am at 36 HP facing an Act 2 Elite on the next floor. With Regal Pillow, resting heals me for 36 HP, bringing me to full health and guaranteeing survival against high burst damage from elites like Slavers or Gremlin Leader.
  strategic_note: Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.

F28 [rest_site] proceed | source=auto
  HP 70->70 | Gold 108->108 | Deck 24->24
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 108->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Elite

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 108->137 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 29 Gold

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 137->137 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 137->137 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim relic: Snecko Skull

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 137->137 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F29 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 68->68 | Gold 137->137 | Deck 24->24
  deck_change: no deck change
  reasoning: Our engine revolves around Envenom+ and Shivs. We already have Snecko Skull to amplify Envenom. Snakebite is too expensive at 2 energy, and Skewer doesn't synergize as well as our existing Shiv generators for Envenom and Strangle. Skipping to keep the deck lean and improve our chances of drawing our core setup early.
  strategic_note: Committed Envenom/Poison plan: use Leading Strike to generate Shivs, stack poison with Envenom, and burst with Accelerant. Need card draw and removal to find Envenom faster.

F29 [map] choose_map_node (option_index=1) | source=llm
  HP 68->68 | Gold 137->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the recommended route to a Monster node. With 68 HP and 137 gold, I need to accumulate more gold and potentially find a high-impact card reward before the final rest site and boss. The unknown node is a gamble, whereas a monster fight provides predictable resources (gold/cards/potions) to refine the deck.
  strategic_note: Foundation poison and retain strategy: leveraging Envenom and Accelerant for burst scaling while using Retain to time damage. Seeking more efficient block and card removals to shorten the time to reach key powers and protect against chip damage during setup.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 137->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 68->68 | Gold 144->144 | Deck 24->24
  deck_change: no deck change
  reasoning: With Envenom+ and Snecko Skull, our primary win condition is multi-hit attacks (like Shivs from Leading Strike and our upgraded Hidden Daggers). We need to keep the deck lean to draw our key powers (Envenom, WLP, Afterimage) quickly. Adding Slice or an unupgraded Hidden Daggers bloats the deck and reduces our consistency without adding enough value.
  strategic_note: Committed to Envenom/Shiv poison scaling engine. Snecko Skull + Envenom+ makes every unblocked hit apply 3 Poison. Focus on drawing Envenom fast, retaining key pieces with WLP, and bursting with Shivs + Strangle. Skip generic damage; prioritize card draw, mitigation, and key upgrades.

F30 [map] choose_map_node (option_index=1) | source=llm
  HP 68->68 | Gold 144->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Act 2 elites are extremely dangerous and my current foundation deck relies on setup turns (Envenom/Accelerant). My priority is surviving to the boss with high HP. A standard monster fight is safer and provides gold for future shops and card rewards to stabilize my defense, whereas an Elite could easily end the run or force a rest instead of a smith.
  strategic_note: Foundation phase: relying on Retain burst combos enabled by Envenom and Accelerant for scaling. Needs card removals for basic strikes and more consistent block to survive setup turns while waiting for burst windows.

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 144->154 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F31 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 68->68 | Gold 154->154 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 68->68 | Gold 154->154 | Deck 24->25
  deck_change: picked Knife Trap
  reasoning: Knife Trap is the ultimate Phase 2 payoff for our deck. We have Envenom+ and Snecko Skull, meaning every Shiv played applies 3 Poison. Replaying all exhausted Shivs with Knife Trap will deal massive physical burst damage and stack an incredible amount of Poison simultaneously, easily solving boss scaling.
  strategic_note: Committed Shiv/Poison hybrid plan: setup Envenom+, generate and play as many Shivs as possible, then use Knife Trap as a massive physical and Poison burst finisher. Focus on finding more card draw and block.

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 68->68 | Gold 154->154 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=8, note_scope=run, note_triggers=all) | source=llm
  HP 68->68 | Gold 154->154 | Deck 25->25
  deck_change: upgraded Accelerant->Accelerant+
  reasoning: With 68/70 HP, resting would only heal 2 HP which is a massive waste of a rest site. The Act 2 boss is next, so we should upgrade a high-impact card. Accelerant+ doubles its effect, triggering Poison 2 additional times instead of 1. Since our main damage scaling relies on Envenom -> Shivs -> Accelerant, this upgrade drastically increases our burst damage against the boss.
  strategic_note: Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Need consistent block and card draw to survive setup turns; remove basic strikes.

F32 [rest_site] proceed | source=auto
  HP 68->68 | Gold 154->154 | Deck 25->25
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 68->68 | Gold 154->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 55->55 | Gold 154->0 | Deck 25->25
  deck_change: no deck change
  reasoning: We are facing a boss and looking for block or utility to mitigate 20 incoming damage. Blade Dance adds shivs, which can give block via Afterimage, but we need 1 energy for it. Expose costs 0 and strips artifact/block, applying vulnerable, which might increase our damage but provides no block. Hand Trick costs 1 and provides 7 block. Since the goal of the potion was to find block or utility, and we need block, Hand Trick is a block card. However, Blade Dance + Afterimage + Envenom gives 3 damage instances, 3 poison, and 3 block. Wait, I only have 1 energy? No, the context says 'Using Skill Potion to find more block or utility'. But my cards in hand are Leading Strike, Shivs, Knife Trap. Let's look at the options. Blade Dance generates 3 shivs. Each shiv gives 1 block from Afterimage (assuming it's in play). Hand Trick gives 7 block for 1 energy. If I have 0 energy, Expose is the only playable one. Wait, if Expose is taken, I can play it for 0. Let's take Hand Trick for the guaranteed 7 block, or Expose for vulnerable. Actually, Expose might strip block and apply vuln, which helps damage. If I need block, Hand Trick gives 7. Let's take Blade Dance, which gives 3 block (via Afterimage) and 12 damage (plus poison from Envenom) for 1 energy. Hand Trick is probably safer if we need raw block.
  strategic_note: Committed plan: Use Envenom and Afterimage with attacks to build poison and block. Play zero cost utility and cycle efficiently.

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 154->229 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 229->229 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Fairy in a Bottle

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 229->229 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 35->35 | Gold 229->229 | Deck 25->26
  deck_change: picked Burst
  reasoning: Burst is highly versatile and extremely powerful in this deck. We can Burst Accelerant+ to trigger poison 4 additional times for massive burst damage, Burst Backflip for draw and block, or Burst Leg Sweep for 22 Block and 4 Weak. It gives us the flexibility to double our output where we need it most.
  strategic_note: Committed poison/shiv hybrid: use shivs to stack poison via Envenom+ and Snecko Skull, then finish with Accelerant+ or Strangle+. Retain key combo pieces with Well-Laid Plans. Skip pure physical attacks.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 35->63 | Gold 229->229 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=combat,deck_building,routing) | source=llm
  HP 63->61 | Gold 229->229 | Deck 26->29
  deck_change: added Apparition x3
  reasoning: Apparitions are incredibly powerful for a deck that needs setup time. Combined with Well-Laid Plans to retain them for crucial turns and Burst to double their effect, they provide nearly impenetrable defense while setting up Envenom and After Image. Fiddle disables our Unceasing Top, Backflip, and Escape Plan draw, and Lord's Parasol relies on hitting a Merchant which isn't guaranteed.
  strategic_note: Committed to Retain/Poison burst plan: use Well-Laid Plans to hold Apparitions and Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Ensure card draw is high to find Apparitions early; prioritize removing basic strikes.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 61->61 | Gold 229->229 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=2) | source=llm
  HP 61->61 | Gold 229->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Following the recommended route towards the column 5 monster node. This path leads toward the double shop strategy identified in the route intelligence, which is critical for card removal and finding better block options while I have over 200 gold. The high HP (61/61) allows for taking these early combats safely to build gold for those shops.
  strategic_note: Foundation phase: leveraging Envenom and Accelerant for Retain-based burst scaling. The deck needs better block density to survive setup turns and aggressive card removal of basic strikes at upcoming shops to increase draw consistency.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 229->239 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 239->239 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 37->37 | Gold 239->239 | Deck 29->30
  deck_change: picked Leading Strike
  reasoning: Leading Strike generates 2 Shivs, which act as massive poison applicators with Envenom+ and Snecko Skull, and provide fuel for Knife Trap and Strangle+. We need maximum Shivs to burst the Act 3 boss before Turn 3.
  strategic_note: Committed Shiv-Poison engine: use Envenom+ and Snecko Skull to make Shivs apply mass poison, then use Accelerant+ to burst. Retain Shiv generators for a huge Envenom turn.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 239->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Monster

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 239->253 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F36 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 253->253 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F36 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 37->37 | Gold 253->253 | Deck 30->31
  deck_change: picked Hidden Daggers+
  reasoning: Hidden Daggers+ is a 0-cost card that fuels our primary damage synergies: it generates Attacks for Finisher and Strangle, applies 6 Poison with Envenom (thanks to Snecko Skull), and adds more Shivs to the Exhaust pile for Knife Trap. It also helps empty our hand of basics/curses to trigger Unceasing Top.
  strategic_note: Committed Envenom/Shiv/Poison engine: generate Shivs to stack poison via Envenom and trigger Strangle/Finisher, then use Accelerant+ or Knife Trap for burst. Prioritize fast draw and removal of basics; avoid expensive cards that disrupt Unceasing Top.

F36 [map] choose_map_node (option_index=0) | source=llm
  HP 37->37 | Gold 253->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With 253 gold, I need to prioritize reaching the shops early in Act 3 to spend my gold on deck refinement and key pieces for the poison/shiv engine, while avoiding unnecessary hallway chip damage.
  strategic_note: Committed poison/shiv hybrid: use Well-Laid Plans to hold Shivs for Envenom/Accelerant bursts. Prioritize shops for removals and high-value block/draw cards, and avoid Act 3 elites to preserve HP for the final boss.

F37 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 23->23 | Gold 253->268 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F37 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 23->23 | Gold 268->268 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F37 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 23->23 | Gold 268->268 | Deck 31->32
  deck_change: picked Phantom Blades
  reasoning: Phantom Blades is a core payoff for Shivs, granting them Retain (excellent for setting up massive Strangle/Envenom burst turns) and providing consistent passive scaling damage.
  strategic_note: Committed Shiv/Poison engine: generate shivs to stack poison via Envenom and scale burst damage with Phantom Blades, Strangle, and Knife Trap. Prioritize cheap draw and block.

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 23->23 | Gold 268->268 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Shop

F38 [shop] buy_relic (option_index=1) | source=plan
  HP 23->23 | Gold 268->93 | Deck 32->32
  deck_change: no deck change
  reasoning: Shop plan [1/2]: Extra energy on turn 1 is crucial for maximizing our large turn 1 hand (from Ring of the Snake) and setting up our powers before the Queen debuffs us.

F38 [shop] buy_card (option_index=4) | source=plan
  HP 23->23 | Gold 93->20 | Deck 32->33
  deck_change: bought Phantom Blades
  reasoning: Shop plan [2/2]: Provides massive scaling for our shivs. Having a second copy ensures we find it early and doubles the stacking damage buff.

F38 [shop] close_shop_inventory | source=plan
  HP 23->23 | Gold 20->20 | Deck 33->33
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F38 [shop] proceed | source=auto
  HP 23->23 | Gold 20->20 | Deck 33->33
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 23->23 | Gold 20->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Monster

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 20->33 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F39 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 15->15 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 15->15 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: The deck is already at 33 cards with 3 copies of Leading Strike and 2 copies of Hidden Daggers+. Adding another Shiv generator dilutes the draw pool for critical powers (Envenom+, Afterimage, Phantom Blades) and survivability (Apparitions). Keeping the deck lean is more important than marginal damage increases at this stage.
  strategic_note: Committed Shiv/Poison hybrid: play Envenom and Phantom Blades early, generate Shivs to stack poison and build Knife Trap damage, then finish with Accelerant or Knife Trap. Need to keep the deck thin to reliably find Apparitions and powers; prioritize card removal and high-impact draw/synergy pieces over basic attacks.

F39 [map] choose_map_node (option_index=0) | source=llm
  HP 15->15 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: With 15/61 HP, taking an Elite fight is suicidal. I must rest at the upcoming Rest Site to survive the next floor and prepare for the Act 3 boss. My gold is currently low (33), but the route contains more shops where I can spend gold earned from hallway fights.
  strategic_note: Committed Retain/Poison plan: use Well-Laid Plans to hold Shivs for Envenom/Accelerant bursts. Currently in survival mode due to low HP; prioritizing rest and avoiding Elites until stabilized.

F40 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 15->48 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: With only 15 HP and an upcoming Elite fight at Floor 43, resting is mandatory to avoid dying to a bad draw. Regal Pillow makes the rest highly efficient, healing us up to a safe 48 HP.
  strategic_note: Committed to Retain/Poison burst plan: hold Apparitions and Shiv generators until Envenom is in play, then burst and trigger poison with Accelerant. Ensure card draw is high to find Apparitions early; prioritize removing basic strikes.

F40 [rest_site] proceed | source=auto
  HP 48->48 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 33->33 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 48->48 | Gold 33->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 48->48 | Gold 69->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim: Prayer Wheel

F41 [treasure] proceed | source=random
  HP 48->48 | Gold 69->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=llm
  HP 48->48 | Gold 69->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Following the recommended route to the shop. Although I only have 69 gold, the route intelligence for Act 3 strongly emphasizes shops as the primary win condition and explicitly warns against Elites to preserve HP for the boss. I have Prayer Wheel for monster rewards later, so I should save HP now and see if there is a cheap removal or key common/uncommon at the shop.
  strategic_note: Committed poison/retain plan: use Well-Laid Plans to hold Apparitions for key turns while Envenom and Shivs stack poison. Prioritize finding more draw to cycle into Apparitions quickly and remove remaining Strikes to increase deck density.

F42 [shop] close_shop_inventory | source=llm
  HP 48->48 | Gold 69->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F42 [shop] proceed | source=auto
  HP 48->48 | Gold 69->69 | Deck 33->33
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 69->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Elite

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 69->101 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 32 Gold

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim relic: Candelabra

F43 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F43 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: no deck change
  reasoning: The deck is currently at 33 cards and relies heavily on finding key powers like Envenom+ and Afterimage. None of the offered cards significantly accelerate this game plan or solve a critical weakness, so skipping is the best way to maintain deck consistency.
  strategic_note: Committed plan: Use Envenom+ and Afterimage with Shivs to build poison and block. Prioritize drawing into powers and retain Apparitions for safety. Avoid adding generic cards that bloat the deck.

F43 [map] choose_map_node (option_index=1) | source=llm
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: no deck change
  reasoning: With 33/61 HP and Apparitions in the deck, reaching the boss with enough HP and upgraded key cards is the priority. This Rest Site allows for a Smith to upgrade a critical card like Envenom or Accelerant, or a heal if necessary. Avoiding the Monster at index 0 preserves HP and follows the successful pattern of minimizing non-boss chip damage in Act 3.
  strategic_note: Committed poison-retain plan: use Well-Laid Plans to time Apparitions and Shivs with Envenom/Accelerant. Prioritize high draw to find intangibility pieces early. Focus on upgrading engine pieces at rest sites and removing basic strikes at shops.

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=13, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: upgraded Afterimage->Afterimage+
  reasoning: With Regal Pillow, we can fully heal at the next Rest Site (F47) before the Boss, so Smithing here is safe. Afterimage+ becomes Innate, guaranteeing we have our passive block engine online from Turn 1, which is critical for surviving Act 3 fights while we set up our Poison/Shiv combo.
  strategic_note: Committed poison/shiv burst plan: get Envenom and Phantom Blades down, retain Apparitions for safety, then spam shivs to stack poison and burst it with Accelerant. Upgraded Afterimage provides crucial passive block.

F44 [rest_site] proceed | source=auto
  HP 33->33 | Gold 101->101 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 101->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Monster

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 101->116 | Deck 33->33
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F45 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 33->33 | Gold 116->116 | Deck 33->33
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 116->116 | Deck 33->34
  deck_change: picked Storm of Steel
  reasoning: Storm of Steel generates a massive number of Shivs, which synergize perfectly with our Envenom+, Afterimage+, Phantom Blades, and Knife Trap. It also empties the hand, allowing us to easily trigger Unceasing Top for extra draw.
  strategic_note: Committed plan: Use Envenom and Afterimage with attacks to build poison and block. Play zero cost utility and cycle efficiently. Retain key cards, dump hand for Storm of Steel, then Unceasing Top keeps the turn going.

F45 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 33->33 | Gold 116->116 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 33->33 | Gold 116->116 | Deck 34->35
  deck_change: picked Haze
  reasoning: Haze is a strong Sly card that synergizes exceptionally well with our Snecko Skull (applies 5 poison) and our discard outlets (Hidden Daggers+, Storm of Steel, Survivor+). Well-Laid Plans can also hold it until we find a discard outlet, providing massive free AoE poison and accelerating our Accelerant+ plays.
  strategic_note: Committed plan: Use Envenom and Afterimage with Shivs to build poison and block. Play zero cost utility and cycle efficiently. Keep deck lean, avoid expensive cards without discard/sly synergy.

F45 [map] choose_map_node (option_index=0) | source=llm
  HP 33->33 | Gold 116->0 | Deck 35->35
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 3, which explicitly advises avoiding elites to preserve HP for the boss. My current HP is 33/61, and I have Apparitions in the deck; taking an elite fight here is high risk. The Monster node provides more card selection value due to Prayer Wheel, helping find final pieces for the poison/retain engine.
  strategic_note: Committed poison/retain plan: Use Well-Laid Plans to hold Apparitions for high-damage turns and stack poison via Envenom and Shivs. Prioritize card draw to find defensive pieces early and use Prayer Wheel monster rewards to hunt for catalysts or additional scaling. Avoid Act 3 elites to ensure survival to the boss.

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 116->130 | Deck 35->35
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 130->130 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] choose_reward_alternative (option_index=0, note_scope=run, note_triggers=deck_building) | source=llm
  HP 33->33 | Gold 130->130 | Deck 35->35
  deck_change: no deck change
  reasoning: Our deck is already 35 cards thick and has strong core scaling with Phantom Blades, Envenom+, and Snecko Skull alongside Shivs and Poison. Adding another common attack or slow power will only dilute our ability to draw our key defensive cards (Apparitions) and core engines on crucial turns.
  strategic_note: Committed Shiv/Poison hybrid plan: use Apparitions to survive while scaling damage through Phantom Blades, Envenom+, and Snecko Skull. Keep the deck lean and avoid adding unnecessary cards.

F46 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 33->33 | Gold 130->130 | Deck 35->35
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 130->130 | Deck 35->36
  deck_change: picked Bouncing Flask+
  reasoning: Bouncing Flask+ applies massive poison quickly, especially with Snecko Skull (4 procs means 4 extra poison applied). This dramatically accelerates our passive boss damage while we defend with Apparitions and Afterimage.
  strategic_note: Committed poison/shiv plan: Use shivs for immediate burst and Envenom stacking. Defend with Apparitions and Afterimage+. Accelerate boss kills with Bouncing Flask and Accelerant.

F46 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 33->33 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=deck_building) | source=llm
  HP 33->61 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: With 33/61 HP and the Act 3 Boss up next, HP is paramount. Although we have Apparitions, a bad draw order on turn 1 or 2 could result in taking significant damage before we set up our Intangible and passive block engine. Resting guarantees we have a much larger HP buffer to survive the early turns of the boss fight.
  strategic_note: Committed poison/shiv burst plan: get Envenom and Phantom Blades down, retain Apparitions for safety, then spam shivs to stack poison and burst it with Accelerant. Upgraded Afterimage provides crucial passive block. Avoid raw attacks; needs more draw.

F47 [rest_site] proceed | source=auto
  HP 61->61 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 130->0 | Deck 36->36
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 18->18 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 18->0 | Gold 130->130 | Deck 36->36
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (9 replays)
[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F15, elite)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 15, elite)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow
Deck (20): Defend x5, Strike x4, Leading Strike x2, Accelerant, Ascender's Bane, Envenom, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor
Enemies: Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=27/27

### Round 1
Agent plan (hypothesis): If potion doesn't help with block/setup, use Leg Sweep on enemy 2 and Defend to fully block. Retain Leading Strike.
Agent plan (hypothesis): Leading Strike retained for future burst turns.
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Leg Sweep -> Phantasmal Gardener[2]
    energy -2 | block +11
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Agent plan (hypothesis): Hold the other Leading Strike with Retain for a future Strangle or Finisher combo. Keep eliminating scaling enemies first.
Agent plan (hypothesis): Continue isolating and bursting down the remaining enemies using retained combo pieces.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(0x3=0), Phantasmal Gardener: Attack(7)
  Expose -> Phantasmal Gardener[3]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Phantasmal Gardener: +Vulnerable(2)
  Strangle+ -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -15, block +6, +Strangle(3)
  Leading Strike -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block -4
  Shiv -> Phantasmal Gardener[3]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Phantasmal Gardener: hp -7, block -2
  Neutralize+ -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp +28, +Weak(1), -Strength, -Vulnerable, -Strangle
  Defend
    energy -1 | block +5
  Shiv -> Phantasmal Gardener[1]
  turn_end

### Round 3
Agent plan (hypothesis): Finish the turn by blocking the 7 incoming damage and attacking.
Agent plan (hypothesis): Ascender's Bane is exhausted. Target 0 should be focused down.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(0x3=0), Phantasmal Gardener: Buff
  Colorless Potion
  Scrawl
  Scrawl
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Survivor
    energy -1 | block +8
  Defend
  Strike -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.

### Round 4
Agent plan (hypothesis): Enemy 0 removed. Focus on remaining enemies.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7)
  Strangle+ -> Phantasmal Gardener[0]
    energy -1
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6
  Strike -> Phantasmal Gardener[1]
    energy -1 | enemy_deltas: Phantasmal Gardener: block -6
  turn_end

### Round 5
Agent plan (hypothesis): Continue focusing one enemy down to reduce the incoming damage next turn.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  Neutralize+ -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6, +Weak(2)
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  Survivor
    energy -1 | block +8
  Strike
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(2x3=6)
  Strangle+ -> Phantasmal Gardener[0]
    energy -1
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6
  Finisher -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 6 rounds)

Cards played (with descriptions):
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 3 plays, 15 dmg
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 4 plays, 3 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 8 plays, 15 dmg, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Scrawl "Draw cards until your Hand is full. Exhaust." -> 1 plays, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Strike "Deal 6 damage." -> 3 plays
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 4 times)" -> 1 plays

Token attribution (Shivs):
  Leading Strike: 8 Shivs -> ~15 dmg

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:-
  Skittish[3]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:-
  Weak: R1:- -> R2:1 -> R3:1 -> R4:- -> R5:- -> R6:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 15, elite)
Relics: Ring of the Snake, Arcane Scroll, Fresnel Lens, Strike Dummy
Deck (19): Defend x5, Strike x4, Blade Dance, Burst, Calculated Gamble+, Dagger Throw, Flick-Flack, Hidden Daggers, Neutralize+, Phantom Blades, Ricochet, Survivor
Enemies: Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=26/26

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Shackling Potion
    enemy_deltas: Phantasmal Gardener: +Strength(-7), +Shackling Potion(7)
  Dagger Throw -> Phantasmal Gardener[1]
    energy -1
  Defend
  Burst
    energy -1 | +Burst(1)
  Blade Dance
    energy -1 | -Burst | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Neutralize+ -> Phantasmal Gardener[1]
  Shiv -> Phantasmal Gardener[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Phantasmal Gardener[1]
  Shiv -> Phantasmal Gardener[1]
  Shiv -> Phantasmal Gardener[1]
  Shiv -> Phantasmal Gardener[1]
  Shiv -> Phantasmal Gardener[1]
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Hidden Daggers
  Ricochet
  Flick-Flack
  Defend
    energy -1 | block +5
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -13
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -4
  Strike -> Phantasmal Gardener[2]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp +25, -Strength
  Calculated Gamble+
    exhausted: Shiv*8 [0]: Retain. Deal 4 damage. Exhaust.
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Strike -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  Survivor
    energy -1 | block +8
  Burst
  turn_end

### Round 4
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(7)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Neutralize+ -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6, +Weak(2)
  Hidden Daggers
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Attack(6)
  Flick-Flack
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block +6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Phantasmal Gardener: Attack(3x3=9)
  Neutralize+ -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6, +Weak(2)
  Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 7
Intent: Phantasmal Gardener: Buff
  Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -9, block +6
  Hidden Daggers
  Defend
  Survivor
  Shiv -> Phantasmal Gardener[0]
    -Phantom Blades | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 7 rounds)

Cards played (with descriptions):
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays
  Burst "This turn, your next Skill is played an extra time." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg
  Shiv "Deal 4 damage. Exhaust." -> 11 plays, 17 dmg, EXHAUST
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage. Draw 2 cards the first time this is played." -> 1 plays
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 3 plays, generates 2 Shivs
  Defend "Gain 5 Block." -> 7 plays, 35 block
  Strike "Deal 9 damage." -> 5 plays, 12 dmg
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 1 plays, 6 dmg

Token attribution (Shivs):
  Hidden Daggers: 5 Shivs -> ~8 dmg
  Blade Dance: 3 Shivs -> ~5 dmg
  other: 3 Shivs -> ~5 dmg

Enemy power timeline:
  Skittish: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:6 -> R7:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:- -> R7:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:- -> R7:-
  Skittish[2]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Skittish[3]: R1:6 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:2 -> R7:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:- -> R7:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:- -> R7:-
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:1

[Selected: boss] Waterfall Giant (F17, boss)
## Combat Replay: vs Waterfall Giant (Floor 17, boss)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top
Deck (21): Defend x5, Strike x4, Leading Strike x2, Accelerant, Ascender's Bane, Envenom, Escape Plan, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor
Enemies: Waterfall Giant HP=240/240

### Round 1
Agent plan (hypothesis): Hold Retain cards for a big Strangle turn.
Intent: Waterfall Giant: Buff
  Envenom
    energy -2 | +Envenom(1)
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6, +Poison(1)
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -4, Poison(1→2), +Weak(2)
  turn_end

### Round 2
Agent plan (hypothesis): Hold the colorless potion for the Strangle combo turn to get extra triggers.
Intent: Waterfall Giant: Attack(11), Debuff, Buff
  Accelerant
    energy -1 | +Accelerant(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Agent plan (hypothesis): After picking the colorless card, the combo is Expose -> Strangle -> Escape Plan -> Leading Strike -> Shivs -> (colorless card if attack) -> Finisher.
Agent plan (hypothesis): Play any generated 0-cost attacks, then Finisher.
Agent plan (hypothesis): We will take 10 damage but the giant's HP is dropping fast. Prepare for the explosion.
Intent: Waterfall Giant: Attack(10), Buff
  Colorless Potion
  Jackpot
  Expose -> Waterfall Giant[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Waterfall Giant: +Vulnerable(2)
  Strangle+ -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -11, +Poison(1), +Strangle(3)
  Escape Plan
    enemy_deltas: Waterfall Giant: hp -3
  Leading Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6, Poison(1→2)
  Shiv -> Waterfall Giant[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Waterfall Giant: hp -7, Poison(2→3)
  Shiv -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -7, Poison(3→4)
  Jackpot -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -31, Poison(4→5)
  Backstab -> Waterfall Giant[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Waterfall Giant: hp -15, Poison(5→6)
  Precise Cut -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -6, Poison(6→7)
  Finisher -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -45, Poison(7→14)
  turn_end

### Round 4
Agent plan (hypothesis): Kill the Giant next turn (R5) so it explodes at the end of R6. Save block cards on R6 to survive the 24-damage explosion.
Intent: Waterfall Giant: Heal, Buff
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -9, Poison(12→13)
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -9, Poison(13→14)
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.

### Round 5
Agent plan (hypothesis): Survive the explosion next turn!
Intent: Waterfall Giant: Attack(20), Buff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Leading Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -3, Poison(12→13)
  Shiv -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -4, Poison(13→14)
  Shiv -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -4, Poison(14→15)
  turn_end

### Round 6
Intent: Waterfall Giant: DeathBlow(24)
  turn_end
## Combat Analytics: Waterfall Giant (WIN - 6 rounds)

Cards played (with descriptions):
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays
  Strike "Deal 6 damage." -> 3 plays, 24 dmg, +3 poison
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg, +1 poison
  Accelerant "Poison is triggered 1 additional time." -> 1 plays
  Defend "Gain 5 Block." -> 5 plays, 25 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Retain. Deal 7 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 11 dmg, +1 poison
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 3 dmg
  Leading Strike "Retain. Deal 2 damage. Add 2 Shivs into your Hand." -> 2 plays, 9 dmg, +2 poison, generates 2 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 4 plays, 22 dmg, +4 poison, EXHAUST
  Jackpot "Deal 18 damage. Add 3 random 0 energy cards into your Hand." -> 1 plays, 31 dmg, +1 poison
  Backstab "Innate. Deal 8 damage. Exhaust." -> 1 plays, 15 dmg, +1 poison, EXHAUST
  Precise Cut "Deal 2 damage. Deals 2 less damage for each other card in your Hand." -> 1 plays, 6 dmg, +1 poison
  Finisher "Deal 4 damage for each Attack already played this turn. (Hits 7 times)" -> 1 plays, 45 dmg, +7 poison

Token attribution (Shivs):
  Leading Strike: 4 Shivs -> ~22 dmg

Poison stacks applied per card:
  Finisher: 7 stacks
  Shiv: 4 stacks
  Strike: 3 stacks
  Leading Strike: 2 stacks
  Neutralize+: 1 stacks
  Strangle+: 1 stacks
  Jackpot: 1 stacks
  Backstab: 1 stacks
  Precise Cut: 1 stacks

Enemy power timeline:
  Poison: R1:- -> R2:1 -> R3:- -> R4:12 -> R5:12 -> R6:-
  Steam Eruption: R1:- -> R2:15 -> R3:18 -> R4:21 -> R5:24 -> R6:-
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Waterfall Giant (Floor 17, boss)
Relics: Ring of the Snake, Cursed Pearl, Potion Belt, Membership Card, Prayer Wheel, Ornamental Fan, Fresnel Lens
Deck (25): Defend x5, Strike x4, Accuracy, Blade Dance, Calculated Gamble, Cloak and Dagger, Dagger Spray+, Escape Plan, Expose, Fan of Knives, Follow Through, Greed, Neutralize, Phantom Blades, Spoils Map, Strangle, Survivor, Up My Sleeve
Enemies: Waterfall Giant HP=240/240

### Round 1
Intent: Waterfall Giant: Buff
  Neutralize -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -3, +Weak(1)
  Fan of Knives
    energy -2 | +Fan of Knives(1)
  Shiv
    exhausted: Shiv [0]: Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Waterfall Giant: hp -4
  Shiv
    block +4 | enemy_deltas: Waterfall Giant: hp -4
  Shiv
    enemy_deltas: Waterfall Giant: hp -4
  Shiv
    enemy_deltas: Waterfall Giant: hp -4
  Dagger Spray+
    energy -1 | block +4 | enemy_deltas: Waterfall Giant: hp -12
  turn_end

### Round 2
Intent: Waterfall Giant: Attack(15), Debuff, Buff
  Weak Potion -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: +Weak(3)
  Expose -> Waterfall Giant[0]
    exhausted: Shiv*4 [0]: Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Waterfall Giant: +Vulnerable(2)
  Accuracy
    energy -1 | +Accuracy(4)
  Follow Through -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -10
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Intent: Waterfall Giant: Attack(7), Buff
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Blade Dance
    energy -1 | exhausted: Shiv*4 [0]: Retain. Deal 4 damage to ALL enemies. Exhaust.
  Survivor
    energy -1 | block +8
  Spoils Map
  Shiv
    enemy_deltas: Waterfall Giant: hp -19
  Shiv
    enemy_deltas: Waterfall Giant: hp -9
  Shiv
    block +4 | enemy_deltas: Waterfall Giant: hp -9
  turn_end

### Round 4
Intent: Waterfall Giant: Heal, Buff
  Escape Plan
  Calculated Gamble
    exhausted: Shiv*7 [0]: Retain. Deal 4 damage to ALL enemies. Exhaust.
  Strangle -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -8, +Strangle(2)
  Up My Sleeve
    energy -2 | enemy_deltas: Waterfall Giant: hp -2
  Shiv
    enemy_deltas: Waterfall Giant: hp -19
  Shiv
    block +4 | enemy_deltas: Waterfall Giant: hp -10
  Shiv
    enemy_deltas: Waterfall Giant: hp -10
  turn_end

### Round 5
Intent: Waterfall Giant: Attack(20), Buff
  Escape Plan
  Skill Potion
  Tactician
  Neutralize -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Dagger Spray+
    energy -1 | enemy_deltas: Waterfall Giant: hp -12
  Strike -> Waterfall Giant[0]
    energy -1 | block +4 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 6
Intent: Waterfall Giant: Attack(13), Buff
  Survivor
    energy -1 | block +8
  Spoils Map
  Defend
    energy -1 | block +5
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 7
Intent: Waterfall Giant: Attack(15), Debuff, Buff
  Cloak and Dagger
    energy -1 | block +6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Shiv
    enemy_deltas: Waterfall Giant: hp -17
  turn_end

### Round 8
Intent: Waterfall Giant: Attack(10), Buff
  Strangle -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6, +Strangle(2)
  Neutralize -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -4, +Weak(1)
  Follow Through -> Waterfall Giant[0]
    energy -1 | block +4 | enemy_deltas: Waterfall Giant: hp -7
  Survivor
    energy -1 | block +8 | enemy_deltas: Waterfall Giant: hp -2
  turn_end
    enemy_deltas: Waterfall Giant: -Strangle

### Round 9
Intent: Waterfall Giant: Heal, Buff
  Escape Plan
  Dagger Spray+
    energy -1 | enemy_deltas: Waterfall Giant: hp -12
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  Strike -> Waterfall Giant[0]
    energy -1 | block +4 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 10
Intent: Waterfall Giant: Attack(25), Buff
  Escape Plan
    block +3
  Up My Sleeve
    energy -1
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 11
Intent: Waterfall Giant: Attack(13), Buff
  Shiv
    enemy_deltas: Waterfall Giant: hp -17
  Shiv
    enemy_deltas: Waterfall Giant: hp -8
  Shiv
    block +4 | enemy_deltas: Waterfall Giant: hp -8
  turn_end

### Round 12
Intent: Waterfall Giant: Attack(15), Debuff, Buff
  Follow Through -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -7
  Strangle -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -8, +Strangle(2)
  Strike -> Waterfall Giant[0]
    energy -1 | block +4 | enemy_deltas: Waterfall Giant: hp +999999991, -Strangle
  turn_end

### Round 13
Intent: Waterfall Giant: DeathBlow(45)
  Dexterity Potion
    +Dexterity(2)
  Speed Potion
    Dexterity(2→7) | +Speed Potion(5)
  Neutralize -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -3, +Weak(1)
  Cloak and Dagger
    energy -1 | block +13
  Shiv
    enemy_deltas: Waterfall Giant: hp -17
  Defend
    energy -1 | block +12
  Defend
    energy -1 | block +12
  turn_end
## Combat Analytics: Waterfall Giant (WIN - 13 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 4 plays, 13 dmg
  Fan of Knives "Shivs now hit ALL enemies. Add 4 Shivs into your Hand." -> 1 plays, generates 4 Shivs
  Shiv "Deal 4 damage to ALL enemies. Exhaust." -> 15 plays, 159 dmg, 16 block, EXHAUST
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 3 plays, 36 dmg, 4 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 3 plays, 24 dmg, 4 block
  Defend "Gain 5 Block." -> 9 plays, 59 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Survivor "Gain 8 Block. Discard 1 card." -> 3 plays, 2 dmg, 24 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 4 plays, 3 block
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Strangle "Deal 8 damage. Whenever you play a card this turn, the enemy loses 2 HP." -> 3 plays, 22 dmg
  Up My Sleeve "Add 3 Shivs into your Hand. Reduce this card's cost by 1." -> 2 plays, 2 dmg, generates 3 Shivs
  Strike "Deal 6 damage." -> 5 plays, 24 dmg, 12 block
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 2 plays, 19 block, generates 1 Shivs

Token attribution (Shivs):
  Fan of Knives: 4 Shivs -> ~42 dmg
  Blade Dance: 3 Shivs -> ~32 dmg
  Up My Sleeve: 3 Shivs -> ~32 dmg
  other: 3 Shivs -> ~32 dmg
  Cloak and Dagger: 2 Shivs -> ~21 dmg

Enemy power timeline:
  Steam Eruption: R1:- -> R2:15 -> R3:18 -> R4:21 -> R5:24 -> R6:27 -> R7:30 -> R8:33 -> R9:36 -> R10:39 -> R11:42 -> R12:45 -> R13:-
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:-
  Weak: R1:- -> R2:- -> R3:2 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:-

[Selected: run_combat] Thieving Hopper (F19, monster)
Historical: loss=2 vs historical avg=9.5+/-4.9 (z=-1.5, BETTER_THAN_USUAL, n=6)
## Combat Replay: vs Thieving Hopper (Floor 19, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh
Deck (22): Defend x5, Strike x4, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Envenom, Escape Plan, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor
Enemies: Thieving Hopper HP=79/79

### Round 1
Intent: Thieving Hopper: Attack(17), CardDebuff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Agent plan (hypothesis): Hopper will have 50% damage reduction next turn but will be low HP and we get an extra energy.
Intent: Thieving Hopper: Buff
  Expose -> Thieving Hopper[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Thieving Hopper: +Vulnerable(2)
  Strangle+ -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -15, +Strangle(3)
  Leading Strike -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -7
  Shiv -> Thieving Hopper[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Thieving Hopper: hp -9
  Shiv -> Thieving Hopper[0]
    enemy_deltas: Thieving Hopper: hp -9
  Strike -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -12
  turn_end

### Round 3
Intent: Thieving Hopper: Attack(21)
  Afterimage
    energy -1 | +Afterimage(1)
  Leg Sweep -> Thieving Hopper[0]
    energy -2 | block +12 | enemy_deltas: Thieving Hopper: +Weak(2)
  Leading Strike -> Thieving Hopper[0]
    energy -1 | block +1 | enemy_deltas: Thieving Hopper: hp -2, Flutter(5→4)
  Shiv -> Thieving Hopper[0]
    block +1 | enemy_deltas: Thieving Hopper: hp -3, Flutter(4→3)
  Shiv -> Thieving Hopper[0]
    block +1 | enemy_deltas: Thieving Hopper: hp -3, Flutter(3→2)
  turn_end

### Round 4
Agent plan (hypothesis): If Survivor is drawn, discard Ascender's Bane to enable Unceasing Top.
Intent: Thieving Hopper: Attack(10)
  Neutralize+ -> Thieving Hopper[0]
    block +1 | enemy_deltas: Thieving Hopper: hp -2, Flutter(2→1), Weak(1→3)
  Escape Plan
    block +1
  Defend
    energy -1 | block +6
  Strike -> Thieving Hopper[0]
    energy -1 | block +1 | enemy_deltas: Thieving Hopper: hp -3, -Flutter
  Strike -> Thieving Hopper[0]
    energy -1 | block +1 | enemy_deltas: Thieving Hopper: hp -6
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.

### Round 5
Agent plan (hypothesis): Hopper killed, retrieved stolen card.
Agent plan (hypothesis): Combat ends.
Intent: Thieving Hopper: Escape
  Neutralize+ -> Thieving Hopper[0]
    block +1 | enemy_deltas: Thieving Hopper: hp -4, Weak(2→4)
  Leading Strike -> Thieving Hopper[0]
    energy -1 | block +1 | enemy_deltas: Thieving Hopper: hp -3
  Shiv -> Thieving Hopper[0]
    block -2 | -Afterimage | enemy_deltas: Thieving Hopper: DIED
## Combat Analytics: Thieving Hopper (WIN - 5 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 4 plays, 21 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 15 dmg
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 12 dmg, 2 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 5 plays, 24 dmg, 2 block, EXHAUST
  Strike "Deal 6 damage." -> 3 plays, 21 dmg, 2 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 12 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 6 dmg, 2 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 1 block

Token attribution (Shivs):
  Leading Strike: 5 Shivs -> ~24 dmg

Enemy power timeline:
  Escape Artist: R1:5 -> R2:4 -> R3:3 -> R4:2 -> R5:1
  Flutter: R1:- -> R2:- -> R3:5 -> R4:2 -> R5:-
  Swipe: R1:- -> R2:1 -> R3:1 -> R4:1 -> R5:1
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Thieving Hopper (Floor 21, monster)
Relics: Ring of the Snake, Neow's Bones, New Leaf, Small Capsule, Centennial Puzzle, The Chosen Cheese, Pendulum, Radiant Pearl
Deck (22): Defend x5, Strike x4, Afterimage, Ascender's Bane, Backflip, Backstab, Bouncing Flask+, Cloak and Dagger, Dagger Spray, Flick-Flack, Neutralize+, Piercing Wail, Predator, Survivor, Tools of the Trade
Enemies: Thieving Hopper HP=79/79

### Round 1
Intent: Thieving Hopper: Attack(17), CardDebuff
  Luminesce
    energy +2 | exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.
  Neutralize+ -> Thieving Hopper[0]
    enemy_deltas: Thieving Hopper: hp -4, +Weak(2)
  Backstab -> Thieving Hopper[0]
    exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust. | enemy_deltas: Thieving Hopper: hp -11
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Thieving Hopper[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Thieving Hopper: hp -4
  Strike -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -6
  Strike -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -6
  Survivor
    energy -1 | block +8
  turn_end

### Round 2
Intent: Thieving Hopper: Buff
  Dagger Spray
    energy -1 | enemy_deltas: Thieving Hopper: hp -8
  Flick-Flack
    energy -1 | enemy_deltas: Thieving Hopper: hp -6
  Strike -> Thieving Hopper[0]
    energy -1 | enemy_deltas: Thieving Hopper: hp -6
  turn_end
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.

### Round 3
Intent: Thieving Hopper: Attack(21)
  Bouncing Flask+
    energy -2 | enemy_deltas: Thieving Hopper: +Poison(12)
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Thieving Hopper: Attack(14)
  Bouncing Flask+
    energy -2 | enemy_deltas: Thieving Hopper: Poison(11→23)
  Defend
    energy -1 | block +10
  turn_end
## Combat Analytics: Thieving Hopper (WIN - 4 rounds)

Cards played (with descriptions):
  Luminesce "Retain. Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 1 plays, 6 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 4 dmg, EXHAUST
  Strike "Deal 6 damage." -> 3 plays, 18 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 1 plays, 6 dmg
  Bouncing Flask+ "Apply 3 Poison to a random enemy 4 times." -> 2 plays, +24 poison
  Defend "Gain 5 Block." -> 2 plays, 15 block

Token attribution (Shivs):
  Cloak and Dagger: 1 Shivs -> ~4 dmg

Poison stacks applied per card:
  Bouncing Flask+: 24 stacks

Enemy power timeline:
  Escape Artist: R1:5 -> R2:4 -> R3:3 -> R4:2
  Flutter: R1:- -> R2:- -> R3:5 -> R4:5
  Poison: R1:- -> R2:- -> R3:- -> R4:11
  Swipe: R1:- -> R2:1 -> R3:1 -> R4:1
  Weak: R1:- -> R2:1 -> R3:- -> R4:-

[Selected: elite] Infested Prism (F29, elite)
Historical: loss=2 vs historical avg=3.3+/-2.5 (z=-0.5, TYPICAL, n=3)
## Combat Replay: vs Infested Prism (Floor 29, elite)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost
Deck (24): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Hidden Daggers+, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Infested Prism HP=200/200

### Round 1
Agent plan (hypothesis): We need 11 more block. Depending on what we draw, we can either play Survivor, Leg Sweep, Defend, or just Leading Strike + Shivs and hold cards.
Agent plan (hypothesis): Maximized damage while fully blocking. Continue prioritizing powers.
Intent: Infested Prism: Attack(22)
  Neutralize+ -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4, +Weak(2)
  Expose -> Infested Prism[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Infested Prism: +Vulnerable(2)
  Well-Laid Plans+
    energy -1 | block +7 | +Well-Laid Plans(2)
  Backflip
    energy -1 | block +5
  Survivor+
    energy -1 | block +11
  Defend
  Leading Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -4
  Shiv -> Infested Prism[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: hp -6
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6
  Hidden Daggers+
  Shiv+ -> Infested Prism[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Infested Prism: hp -9
  Shiv+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -9
  turn_end
  Defend
  confirm

### Round 2
Agent plan (hypothesis): Retain Finisher with WLP. Strangle+ is played to deal solid damage and utilize energy efficiently while keeping HP high.
Intent: Infested Prism: Attack(12), Defend
  Strangle+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -15, +Strangle(3)
  Defend
    energy -1 | block +5 | enemy_deltas: Infested Prism: hp -3
  Defend
    energy -1 | block +5 | enemy_deltas: Infested Prism: hp -3
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -12
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.
  Finisher
  confirm

### Round 3
Agent plan (hypothesis): Retain Envenom+ to play next turn when the enemy buffs.
Intent: Infested Prism: Attack(9x3=27)
  Afterimage
    energy -1 | +Afterimage(1)
  Leg Sweep -> Infested Prism[0]
    energy -2 | block +12 | enemy_deltas: Infested Prism: +Weak(2)
  Escape Plan
    block +4
  Defend
    energy -1 | block +6
  turn_end
  Finisher
  Envenom+

### Round 4
Agent plan (hypothesis): Play any drawn 0-cost attacks before Finisher. Retain Finisher if we somehow can't play it.
Agent plan (hypothesis): Retain Defend for next turn.
Intent: Infested Prism: Buff, Defend
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Accelerant
    energy -1 | block +1 | +Accelerant(1)
  Hidden Daggers+
  Strike
  Strike
  Shiv+ -> Infested Prism[0]
    energy +1 | block +1 | enemy_deltas: Infested Prism: hp -6, +Poison(2)
  Shiv+ -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -6, Poison(2→4)
  Backflip
    energy -1 | block +6
  Finisher -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: hp -12, Poison(4→8)
  turn_end
  Defend
  Strike

### Round 5
Agent plan (hypothesis): We are fully blocking and slowly stacking poison. Keep pushing through the block to apply Envenom.
Intent: Infested Prism: Attack(26)
  Neutralize+ -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: block -4, +Weak(2)
  Escape Plan
    block +4
  Leading Strike -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: block -3
  Shiv -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: block -4
  Shiv -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: block -4
  Strike -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -1, block -5, Poison(6→8)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Defend
  confirm

### Round 6
Intent: Infested Prism: Attack(15), Defend
  Strangle+ -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -10, Poison(6→8), +Strangle(3)
  Leading Strike -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: hp -6, Poison(8→10)
  Shiv -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -7, Poison(10→12)
  Shiv -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -7, Poison(12→14)
  Leg Sweep -> Infested Prism[0]
    energy -2 | block +12 | enemy_deltas: Infested Prism: hp -3, Weak(1→3)
  Survivor+
    energy -1 | block +11
  Defend
  turn_end
  Defend
  confirm

### Round 7
Agent plan (hypothesis): Fight won.
Intent: Infested Prism: Attack(9x3=27)
  Escape Plan
    block +1
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Neutralize+ -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: block -4, Weak(2→4)
  turn_end
  Backflip
  confirm
## Combat Analytics: Infested Prism (WIN - 7 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 4 dmg, 2 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 7 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 11 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 2 plays, 22 block
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 10 dmg, 2 block, +2 poison, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 26 dmg, 4 block, +4 poison, EXHAUST
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 2 plays, generates 2 Shivs
  Shiv+ "Deal 6 damage. Exhaust." -> 4 plays, 30 dmg, 2 block, +4 poison, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 25 dmg, 1 block, +2 poison
  Defend "Gain 5 Block." -> 10 plays, 6 dmg, 58 block
  Strike "Deal 6 damage." -> 2 plays, 13 dmg, 1 block, +2 poison
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 3 dmg, 24 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 3 plays, 9 block
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 1 block
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 1 block
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 2 times)" -> 1 plays, 12 dmg, 1 block, +4 poison

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~34 dmg
  Hidden Daggers+: 4 Shivs -> ~22 dmg

Poison stacks applied per card:
  Shiv+: 4 stacks
  Finisher: 4 stacks
  Shiv: 4 stacks
  Strike: 2 stacks
  Strangle+: 2 stacks
  Leading Strike: 2 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:6 -> R6:6 -> R7:12
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:4 -> R7:4
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:2
Comparator (recent same-enemy comparator):
## Combat Replay: vs Infested Prism (Floor 24, elite)
Relics: Ring of the Snake, Arcane Scroll, Happy Flower, Pael's Claw, The Chosen Cheese
Deck (20): Defend x5, Ascender's Bane, Blade of Ink, Deflect+, Escape Plan, Flick-Flack, Grand Finale, Guilty, Malaise, Neutralize+, Pounce, Skewer+, Strike, Sucker Punch+, Survivor+, Toric Toughness
Enemies: Infested Prism HP=200/200

### Round 1
Intent: Infested Prism: Attack(22)
  Clarity Extract
    +Clarity(3)
  Neutralize+ -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4, +Weak(2)
  Escape Plan
    block +3
  Defend
    energy -1 | block +7 | exhausted: Defend [1]: Gain 8 Block. Permanently increase this card's Block by 1. Exhaust.
  Malaise -> Infested Prism[0]
    energy -4 | exhausted: Malaise [X]: Enemy loses X Strength. Apply X Weak. Exhaust. | enemy_deltas: Infested Prism: Weak(2→6), +Strength(-4)
  turn_end

### Round 2
Intent: Infested Prism: Attack(9), Defend
  Blade of Ink
    energy -1
  Shiv -> Infested Prism[0]
    energy +1 | exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Infested Prism: hp -6, Weak(5→6)
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  Survivor+
    energy -1 | block +11
  Ascender's Bane
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Weak(6→7)
  turn_end

### Round 3
Intent: Infested Prism: Attack(3x3=9)
  Deflect+
    block +7
  Skewer+ -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: hp -17, block -16
  turn_end

### Round 4
Intent: Infested Prism: Buff, Defend
  Escape Plan
  Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6
  Pounce -> Infested Prism[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Infested Prism: hp -12
  Survivor+
    block +11 | -Free Skill
  Flick-Flack
  Defend
    energy -1 | block +6 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Infested Prism: hp -6
  turn_end
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.

### Round 5
Intent: Infested Prism: Attack(16)
  Grand Finale
    energy +1 | enemy_deltas: Infested Prism: hp -40, block -20
  Neutralize+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -4, Weak(4→6)
  Blade of Ink
    energy -1
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Weak(6→7)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Weak(7→8)
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  Defend
    energy -1 | block +7
  turn_end

### Round 6
Intent: Infested Prism: Attack(12), Defend
  Pounce -> Infested Prism[0]
    energy -1 | +Free Skill(1) | enemy_deltas: Infested Prism: hp -12
  Toric Toughness
    block +5 | Toric Toughness(1→2) | -Free Skill
  Defend
    energy -1 | block +6
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  turn_end

### Round 7
Intent: Infested Prism: Attack(6x3=18)
  Escape Plan
  Blade of Ink
    energy -1
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -6, Weak(6→7)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -6, Weak(7→8)
  Survivor+
    energy -1 | block +11
  Flick-Flack
  Skewer+ -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: hp -35, block -4
  turn_end

### Round 8
Intent: Infested Prism: Buff, Defend
  Neutralize+ -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4, Weak(7→9)
  Sucker Punch+ -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -10, Weak(9→11)
  Skewer+ -> Infested Prism[0]
    energy -3 | hp +1 | block -5 | enemy_deltas: Infested Prism: DIED
## Combat Analytics: Infested Prism (WIN - 8 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 12 dmg
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 3 plays, 3 block
  Defend "Gain 7 Block. Permanently increase this card's Block by 1. Exhaust." -> 4 plays, 6 dmg, 26 block, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 3 plays
  Shiv "Deal 6 damage. Apply 1 Weak. Exhaust." -> 6 plays, 24 dmg, EXHAUST
  Toric Toughness "Gain 5 Block. Gain 5 Block at the start of the next 2 turns." -> 3 plays, 15 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 3 plays, 33 block
  Deflect+ "Gain 7 Block." -> 1 plays, 7 block
  Skewer+ "Deal 11 damage X times." -> 3 plays, 52 dmg
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 2 plays, 24 dmg
  Grand Finale "Can only be played if there are no cards in your Draw Pile. Deal 60 damage to ALL enemies." -> 1 plays, 40 dmg
  Sucker Punch+ "Deal 10 damage. Apply 2 Weak." -> 1 plays, 10 dmg

Token attribution (Shivs):
  other: 6 Shivs -> ~24 dmg

Enemy power timeline:
  Strength: R1:- -> R2:-4 -> R3:-4 -> R4:-4 -> R5:- -> R6:- -> R7:- -> R8:-
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1
  Weak: R1:- -> R2:5 -> R3:6 -> R4:5 -> R5:4 -> R6:7 -> R7:6 -> R8:7

[Selected: run_combat] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (F30, monster)
Historical: loss=0 vs historical avg=8.5+/-5.4 (z=-1.6, BETTER_THAN_USUAL, n=4)
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 30, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull
Deck (24): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Hidden Daggers+, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Bowlbug (Rock) HP=46/46, Bowlbug (Silk) HP=42/42, Slumbering Beetle HP=86/86

### Round 1
Agent plan (hypothesis): Ascender's bane exhausted. Finish off Silk next turn before Beetle wakes.
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Strangle+ -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -10, +Strangle(3)
  Leading Strike -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -6
  Hidden Daggers+
  Strike
  Defend
  Shiv -> Bowlbug (Rock)[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bowlbug (Rock): hp -7
  Shiv -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): hp -7
  Shiv+ -> Bowlbug (Rock)[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Bowlbug (Rock): hp -9
  Shiv+ -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): DIED
  Finisher -> Bowlbug (Silk)[0]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -36
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.

### Round 2
Agent plan (hypothesis): Retain Envenom+ and any other high-value combo pieces. Next turn brings 4 energy, giving us time to set up Envenom before the Beetle wakes up.
Agent plan (hypothesis): Retain Envenom+ and Backflip. Setup Envenom next turn and prepare to burst the Beetle.
Intent: Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Escape Plan
    block +3
  Leg Sweep -> Bowlbug (Silk)[0]
    energy -2 | block +11 | enemy_deltas: Bowlbug (Silk): +Weak(2)
  Well-Laid Plans+
    energy -1 | block +7 | +Well-Laid Plans(2)
  turn_end
  Envenom+
  Backflip

### Round 3
Agent plan (hypothesis): Use Retain for Backflip and Leading Strike. Beetle wakes up next turn, burst it down.
Intent: Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Afterimage
    energy -1 | +Afterimage(1)
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Strike -> Bowlbug (Silk)[0]
    energy -1 | block +1 | enemy_deltas: Bowlbug (Silk): DIED
  turn_end
  Backflip
  Survivor+

### Round 4
Agent plan (hypothesis): Beetle is heavily poisoned and Weakened. Prepare to finish it off next turn.
Intent: Slumbering Beetle: Attack(16), Buff
  Expose -> Slumbering Beetle[0]
    block +1 | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Slumbering Beetle: block -13, +Vulnerable(2)
  Neutralize+ -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, +Poison(3), +Weak(2)
  Leading Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -4, Poison(3→6)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(6→9)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(9→12)
  Accelerant
    energy -1 | block +1 | +Accelerant(1)
  Survivor+
    energy -1 | block +11
  Defend
  Backflip
    energy -1 | block +6
  turn_end
  Defend
  Leading Strike

### Round 5
Agent plan (hypothesis): Fight complete, zero damage taken.
Intent: Slumbering Beetle: Attack(13), Buff
  Leading Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -4, Poison(10→13)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(13→16)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(16→19)
  Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -9, Poison(19→22)
  Finisher -> Slumbering Beetle[0]
    energy -1 | block -4 | -Well-Laid Plans | -Afterimage | -Envenom | -Accelerant | enemy_deltas: Slumbering Beetle: DIED
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 5 rounds)

Cards played (with descriptions):
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 14 dmg, 2 block, +6 poison, generates 2 Shivs
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 1 plays, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 38 dmg, 4 block, +12 poison, EXHAUST
  Shiv+ "Deal 6 damage. Exhaust." -> 2 plays, 9 dmg, EXHAUST
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 6 times)" -> 2 plays, 36 dmg
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 3 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 7 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 2 plays, 9 dmg, 2 block, +3 poison
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 6 dmg, 1 block, +3 poison
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 1 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 6 block

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~35 dmg
  Hidden Daggers+: 2 Shivs -> ~12 dmg

Poison stacks applied per card:
  Shiv: 12 stacks
  Leading Strike: 6 stacks
  Neutralize+: 3 stacks
  Strike: 3 stacks
Total poison/power tick damage: 10
  Per round: R1:4 R3:6

Enemy power timeline:
  Imbalanced: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:10
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:1
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 28, monster)
Relics: Ring of the Snake, Arcane Scroll, Happy Flower, Pael's Claw, The Chosen Cheese, Bronze Scales, Vajra
Deck (22): Defend x5, Escape Plan x2, Ascender's Bane, Blade of Ink, Dagger Throw, Deflect+, Flick-Flack, Grand Finale, Guilty, Malaise, Neutralize+, Pounce, Skewer+, Strike, Sucker Punch+, Survivor+, Toric Toughness
Enemies: Bowlbug (Rock) HP=46/46, Bowlbug (Silk) HP=40/40, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Escape Plan
  Neutralize+ -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): hp -5, +Weak(2)
  Deflect+
    block +7
  Pounce -> Bowlbug (Silk)[1]
    energy -2 | +Free Skill(1) | enemy_deltas: Bowlbug (Silk): hp -13
  Toric Toughness
    block +5 | +Toric Toughness(2) | -Free Skill
  Blade of Ink
    energy -1
  Shiv -> Bowlbug (Silk)[1]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Bowlbug (Silk): hp -7, +Weak(1)
  Shiv -> Bowlbug (Silk)[1]
    enemy_deltas: Bowlbug (Silk): hp -7, Weak(1→2)
  turn_end

### Round 2
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(3x2=6), Slumbering Beetle: Sleep
  Defend
    energy -1 | block +6 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Dagger Throw -> Bowlbug (Silk)[1]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -7
  Guilty
  Malaise -> Slumbering Beetle[2]
    energy -2 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Slumbering Beetle: +Strength(-2), +Weak(2)
  turn_end
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.

### Round 3
Intent: Bowlbug (Rock): Attack(15), Slumbering Beetle: Sleep
  Escape Plan
  Sucker Punch+ -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -11, +Weak(2)
  Defend
    energy -1 | block +8 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Skewer+ -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -12
  turn_end

### Round 4
Intent: Bowlbug (Rock): Stun, Slumbering Beetle: Attack(14), Buff
  Escape Plan
    block +3
  Survivor+
    energy -1 | block +11
  Flick-Flack
  Blade of Ink
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -7; Slumbering Beetle: block -7
  Shiv -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): DIED
  Shiv -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -1, block -6, +Weak(1)
  Strike -> Slumbering Beetle[0]
    energy -1 | enemy_deltas: Slumbering Beetle: hp -7
  turn_end

### Round 5
Intent: Slumbering Beetle: Attack(16), Buff
  Poison Potion -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: +Poison(6)
  Deflect+
    block +7
  Skewer+ -> Slumbering Beetle[0]
    energy -4 | enemy_deltas: Slumbering Beetle: hp -48
  turn_end

### Round 6
Intent: Slumbering Beetle: Attack(18), Buff
  Defend
    energy -1 | block +7 | exhausted: Shiv*4 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Defend
    energy -1 | block +7
  Neutralize+ -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -5, +Weak(2)
  Dagger Throw -> Slumbering Beetle[0]
    energy -1 | enemy_deltas: Slumbering Beetle: hp -10
  Toric Toughness
  Escape Plan
  turn_end
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 6 rounds)

Cards played (with descriptions):
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 4 plays, 3 block
  Neutralize+ "Deal 5 damage. Apply 2 Weak." -> 2 plays, 10 dmg
  Deflect+ "Gain 7 Block." -> 2 plays, 14 block
  Pounce "Deal 13 damage. The next Skill you play costs 0 energy ." -> 1 plays, 13 dmg
  Toric Toughness "Gain 5 Block. Gain 5 Block at the start of the next 2 turns." -> 1 plays, 5 block
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 2 plays, 7 dmg
  Shiv "Deal 7 damage. Apply 1 Weak. Exhaust." -> 4 plays, 15 dmg, EXHAUST
  Defend "Gain 6 Block. Permanently increase this card's Block by 1. Exhaust." -> 4 plays, 28 block, EXHAUST
  Dagger Throw "Deal 7 damage. Draw 1 card. Discard 1 card." -> 2 plays, 17 dmg
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Sucker Punch+ "Deal 11 damage. Apply 2 Weak." -> 1 plays, 11 dmg
  Skewer+ "Deal 12 damage X times." -> 2 plays, 60 dmg
  Survivor+ "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Strike "Deal 7 damage." -> 1 plays, 7 dmg

Active powers: Thorns(3), Strength(1)

Token attribution (Shivs):
  other: 4 Shivs -> ~15 dmg

Poison stacks applied per card:
  Poison Potion: 6 stacks
Total poison/power tick damage: 5
  Per round: R4:5

Enemy power timeline:
  Imbalanced: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:- -> R6:-
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:- -> R6:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:5
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:- -> R3:-2 -> R4:-2 -> R5:- -> R6:2
  Weak: R1:- -> R2:- -> R3:1 -> R4:1 -> R5:- -> R6:-
  Weak[0]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-
  Weak[1]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-

[Selected: boss] The Insatiable (F33, boss)
Historical: loss=33 vs historical avg=25.7+/-20.7 (z=0.4, TYPICAL, n=3)
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull
Deck (25): Defend x5, Strike x3, Leading Strike x2, Accelerant+, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Hidden Daggers+, Knife Trap, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Expose -> The Insatiable[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: The Insatiable: +Vulnerable(2)
  Strangle+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -15, +Strangle(3)
  Afterimage
    energy -1 | block +7 | +Afterimage(1) | enemy_deltas: The Insatiable: hp -3
  Neutralize+ -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -9, +Weak(2)
  Escape Plan
    block +4 | enemy_deltas: The Insatiable: hp -3
  Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -12
  turn_end

### Round 2
Intent: The Insatiable: Attack(6x2=12)
  Accelerant+
    energy -1 | block +1 | +Accelerant(2)
  Leading Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -4
  Shiv -> The Insatiable[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -6
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -6
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  Hidden Daggers+
    block +1
  Shiv+ -> The Insatiable[0]
    block +1 | exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: The Insatiable: hp -9
  Shiv+ -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -9
  turn_end

### Round 3
Intent: The Insatiable: Attack(28)
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Defend
    energy -1 | block +6
  Survivor+
    energy -1 | block +11
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): Ascender's Bane will exhaust, freeing up Unceasing Top for future turns. Boss starts multi-attacking next turn.
Intent: The Insatiable: Buff
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.

### Round 5
Agent plan (hypothesis): Retain Knife Trap. Envenom and Accelerant will stack poison rapidly. Keep generating and playing Shivs.
Intent: The Insatiable: Attack(10x2=20)
  Skill Potion
  Hand Trick
  Hand Trick
    block +7
  Defend
    block +1
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Leading Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -3, +Poison(3)
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -4, Poison(3→6)
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -4, Poison(6→9)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
  Knife Trap
  confirm

### Round 6
Agent plan (hypothesis): If we draw Leg Sweep or Neutralize, use them for mitigation. Consider Frantic Escape (1) and Knife Trap.
Agent plan (hypothesis): Sandpit will be extended, and we start dealing more poison damage.
Intent: The Insatiable: Attack(10x2=20)
  Escape Plan
    block +1
  Frantic Escape
    energy -2 | block +1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  Frantic Escape
    energy -2 | block +1 | enemy_deltas: The Insatiable: Sandpit(4→5)
  turn_end
  Knife Trap
  Defend

### Round 7
Agent plan (hypothesis): Poison is stacking fast with Envenom and Accelerant. Keep generating Shivs to ramp it up.
Intent: The Insatiable: Attack(30)
  Leg Sweep -> The Insatiable[0]
    energy -2 | block +12 | enemy_deltas: The Insatiable: +Weak(2)
  Knife Trap -> The Insatiable[0]
    energy -2 | block +7 | enemy_deltas: The Insatiable: hp -28, Poison(3→21)
  turn_end
  Backflip
  Hidden Daggers+

### Round 8
Agent plan (hypothesis): Boss is dead
Intent: The Insatiable: Buff
  Strangle+ -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -10, Poison(18→21), +Strangle(3)
  Hidden Daggers+
  Frantic Escape
  Survivor+
  Shiv+ -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -9, Poison(21→24)
  Shiv+ -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -9, Poison(24→27)
  Finisher -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -21, Poison(27→36)
  Backflip
    energy -1 | block +6 | enemy_deltas: The Insatiable: hp -3
  Strike -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -9, Poison(36→39)
  turn_end
  Defend
  Strike
## Combat Analytics: The Insatiable (WIN - 8 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 25 dmg, 1 block, +3 poison
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays, 3 dmg, 7 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 9 dmg, 1 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 3 dmg, 5 block
  Strike "Deal 6 damage." -> 2 plays, 21 dmg, 2 block, +3 poison
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays, 1 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 2 plays, 7 dmg, 2 block, +3 poison, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 20 dmg, 4 block, +6 poison, EXHAUST
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 5 plays, 5 block
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 2 plays, 1 block, generates 2 Shivs
  Shiv+ "Deal 6 damage. Exhaust." -> 4 plays, 36 dmg, 4 block, +6 poison, EXHAUST
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 1 block
  Defend "Gain 5 Block." -> 5 plays, 30 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Hand Trick "Gain 7 Block. Add Sly to a Skill in your Hand this turn." -> 1 plays, 7 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 12 block
  Knife Trap "Play every Shiv in your Exhaust Pile on the enemy. (Plays 6 Shivs)" -> 1 plays, 28 dmg, 7 block, +18 poison, EXHAUST
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 3 times)" -> 1 plays, 21 dmg, 1 block, +9 poison
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 3 dmg, 6 block

Token attribution (Shivs):
  Leading Strike: 4 Shivs -> ~28 dmg
  Hidden Daggers+: 4 Shivs -> ~28 dmg

Poison stacks applied per card:
  Knife Trap: 18 stacks
  Finisher: 9 stacks
  Shiv: 6 stacks
  Shiv+: 6 stacks
  Leading Strike: 3 stacks
  Strangle+: 3 stacks
  Strike: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:6 -> R7:3 -> R8:18
  Sandpit: R1:- -> R2:4 -> R3:4 -> R4:3 -> R5:4 -> R6:3 -> R7:4 -> R8:3
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Neow's Bones, New Leaf, Small Capsule, Centennial Puzzle, The Chosen Cheese, Pendulum, Radiant Pearl, Snecko Skull, Orichalcum, Unceasing Top
Deck (26): Defend x5, Strike x3, Afterimage, Ascender's Bane, Backflip, Backstab, Bouncing Flask+, Calculated Gamble, Cloak and Dagger, Dagger Spray+, Expertise+, Flick-Flack, Leading Strike+, Neutralize+, Piercing Wail, Predator, Strangle+, Survivor, Tools of the Trade, Well-Laid Plans
Enemies: The Insatiable HP=321/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Fysh Oil
    +Strength(1) | +Dexterity(1)
  Luminesce
    energy +2 | exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Predator -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -16
  Backstab -> The Insatiable[0]
    exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust. | enemy_deltas: The Insatiable: hp -12
  Leading Strike+ -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -7
  Shiv -> The Insatiable[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -5
  Shiv -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -5
  Dagger Spray+
    energy -1 | enemy_deltas: The Insatiable: hp -14
  turn_end
    block +6
  Neutralize+

### Round 2
Intent: The Insatiable: Attack(8x2=16)
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -5, +Weak(2)
  Afterimage
    energy -1 | +Afterimage(1)
  Cloak and Dagger
    energy -1 | block +8
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -5
  Defend
    energy -1 | block +7
  turn_end
  Calculated Gamble

### Round 3
Intent: The Insatiable: Attack(21)
  Defend
    energy -1 | block +14
  Backflip
    energy -1 | block +7
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(3→4)
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.
  Calculated Gamble

### Round 4
Intent: The Insatiable: Buff
  Tools of the Trade
    energy -1 | block +1 | +Tools of the Trade(1)
  Calculated Gamble
    block +2 | exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: hp -7
  Bouncing Flask+
    energy -2 | block +1 | enemy_deltas: The Insatiable: +Poison(16)
  turn_end
  Strangle+
  Defend

### Round 5
Intent: The Insatiable: Attack(10x2=20)
  Strangle+ -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -11, +Strangle(3)
  Leading Strike+ -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -10
  Cloak and Dagger
    energy -1 | block +8 | enemy_deltas: The Insatiable: hp -3
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  turn_end
  Survivor
  Strike

### Round 6
Intent: The Insatiable: Attack(10x2=20)
  Survivor
    energy -1 | block +9
  Frantic Escape
  Piercing Wail
    energy -1 | block +1 | exhausted: Shiv*6 [0]: Deal 4 damage. Exhaust. | enemy_deltas: The Insatiable: Strength(2→-4), +Piercing Wail(6)
  Neutralize+ -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -5, +Weak(2)
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(1→2)
  turn_end
  Defend
  Strike

### Round 7
Intent: The Insatiable: Attack(22)
  Backflip
    energy -1 | block +7
  Defend
    energy -1 | block +14
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(1→2)
  turn_end
  Defend
  Flick-Flack

### Round 8
Intent: The Insatiable: Buff
  Frantic Escape
    energy -2 | block +1 | enemy_deltas: The Insatiable: Sandpit(1→2)
  turn_end
  Cloak and Dagger
  Strike

### Round 9
Intent: The Insatiable: Attack(12x2=24)
  Strangle+ -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -11, +Strangle(3)
  Leading Strike+ -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -10
  Cloak and Dagger
    energy -1 | block +8 | enemy_deltas: The Insatiable: hp -3
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  Shiv -> The Insatiable[0]
    block +1 | enemy_deltas: The Insatiable: hp -8
  turn_end
  Survivor
## Combat Analytics: The Insatiable (LOSS - 9 rounds)
Death cause: Sandpit timer reached 0. HP was 48 when killed.

Cards played (with descriptions):
  Luminesce "Retain. Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Predator "Deal 16 damage. Next turn, draw 2 cards." -> 1 plays, 16 dmg
  Backstab "Innate. Deal 12 damage. Exhaust." -> 1 plays, 12 dmg, EXHAUST
  Leading Strike+ "Deal 7 damage. Add 2 Shivs into your Hand." -> 3 plays, 27 dmg, 2 block, generates 2 Shivs
  Shiv "Deal 5 damage. Exhaust." -> 9 plays, 63 dmg, 7 block, EXHAUST
  Dagger Spray+ "Deal 7 damage to ALL enemies twice." -> 1 plays, 14 dmg
  Neutralize+ "Deal 5 damage. Apply 2 Weak." -> 2 plays, 10 dmg, 1 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Cloak and Dagger "Gain 7 Block. Add 1 Shiv into your Hand." -> 3 plays, 6 dmg, 24 block, generates 1 Shivs
  Defend "Gain 6 Block." -> 3 plays, 35 block
  Backflip "Gain 6 Block. Draw 2 cards." -> 2 plays, 14 block
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 4 plays, 4 block
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays, 1 block
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 7 dmg, 2 block, EXHAUST
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 1 plays, 1 block, +16 poison
  Strangle+ "Deal 11 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 22 dmg, 2 block
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST

Token attribution (Shivs):
  Leading Strike+: 6 Shivs -> ~42 dmg
  Cloak and Dagger: 3 Shivs -> ~21 dmg

Poison stacks applied per card:
  Bouncing Flask+: 16 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:15 -> R6:14 -> R7:13 -> R8:12 -> R9:11
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:3 -> R5:2 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:-

[Selected: run_combat] multi:Axebot+Axebot (F39, monster)
Historical: loss=8 vs historical avg=1.3+/-1.9 (z=3.5, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs multi:Axebot+Axebot (Floor 39, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull, Distinguished Cape, Lantern
Deck (33): Defend x5, Apparition x3, Leading Strike x3, Strike x3, Hidden Daggers+ x2, Phantom Blades x2, Accelerant+, Afterimage, Ascender's Bane, Backflip, Burst, Envenom+, Escape Plan, Expose, Finisher, Knife Trap, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Axebot HP=41/41, Axebot HP=40/40

### Round 1
Agent plan (hypothesis): We've safely set up both Phantom Blades. Next turn we look to start generating Shivs or setting up Envenom if drawn. Focus on Axebot 0.
Intent: Axebot: Attack(5x2=10), Axebot: Attack(8), Debuff
  Phantom Blades
    energy -1 | block +7 | +Phantom Blades(9)
  Phantom Blades
    energy -1 | Phantom Blades(9→18)
  Neutralize+ -> Axebot[0]
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Expose -> Axebot[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust.
  turn_end

### Round 2
Agent plan (hypothesis): Axebot 0 will revive with 1 Strength after the next hit. Use the retained Shiv+ to trigger the revive immediately next turn.
Intent: Axebot: Attack(6), Debuff, Axebot: Attack(5x2=10)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Survivor+
    energy -1 | block +8
  Finisher
  Hidden Daggers+
  Shiv+ -> Axebot[0]
    exhausted: Shiv+ [0]: Retain. Deal 6 damage. Exhaust.
  turn_end

### Round 3
Agent plan (hypothesis): Retain Apparition to survive the 5-Strength Axebot phase.
Intent: Axebot: Attack(8), Debuff, Axebot: Buff
  Afterimage
    energy -1 | +Afterimage(1)
  Shiv+ -> Axebot[0]
    block +1
  Leading Strike -> Axebot[0]
    energy -1 | block +1
  Shiv -> Axebot[0]
    block +1 | exhausted: Shiv+*2 [0]: Retain. Deal 6 damage. Exhaust.
  Shiv -> Axebot[0]
    block +1
  turn_end
    exhausted: Shiv+*2 [0]: Retain. Deal 6 damage. Exhaust.
  Burst
  Defend

### Round 4
Agent plan (hypothesis): Retain Leg Sweep to apply Weak when Intangible runs out, or just use Intangible to tank next turn's big hits.
Intent: Axebot: Buff, Axebot: Attack(9x2=18)
  Burst
    energy -1 | block +1 | +Burst(1)
  Apparition
    energy -1 | block +2 | +Intangible(2) | -Burst
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
    exhausted: Shiv+*2 [0]: Retain. Deal 6 damage. Exhaust.
  Accelerant+
  Leg Sweep

### Round 5
Agent plan (hypothesis): Axebot 0 is now in its final Stock(0) 5-Strength form. We will need Apparition or high Block next turn.
Intent: Axebot: Attack(1x2=2), Axebot: Attack(1x2=2)
  Escape Plan
    block +1
  Strangle+ -> Axebot[0]
    energy -1 | block +1
  Leading Strike -> Axebot[0]
    energy -1 | block +1
  Shiv -> Axebot[0]
    block +1
  Shiv -> Axebot[0]
    block +1
  Knife Trap -> Axebot[0]
    energy -2 | block +7
  turn_end
  Accelerant+
  Leg Sweep

### Round 6
Agent plan (hypothesis): Retain Leg Sweep if possible to handle Axebot 1's heavy attacks once Intangible wears off.
Intent: Axebot: Attack(6x2=12), Axebot: Attack(12), Debuff
  Apparition
    energy -1 | block +1 | +Intangible(1)
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Accelerant+
    energy -1 | block +1 | +Accelerant(2)
  turn_end
  Leg Sweep
  Defend

### Round 7
Intent: Axebot: Buff, Axebot: Attack(9x2=18)
  Leg Sweep -> Axebot[1]
    energy -2 | block +9 | enemy_deltas: Axebot: +Weak(2)
  Defend
    energy -1 | block +4
  Defend
    energy -1 | block +4
  Hidden Daggers+
  Knife Trap
  Strike
  Shiv+ -> Axebot[0]
    block +1
  Shiv+ -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, +Poison(3)
  Hidden Daggers+
    block +1
  Shiv+ -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, Poison(3→6)
  Shiv+ -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, Poison(6→9)
  turn_end
  Leading Strike
  confirm

### Round 8
Agent plan (hypothesis): The final form is now active and will attack heavily next turn. Prepare to survive.
Intent: Axebot: Buff
  Neutralize+ -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp +38, Stock(2→1), -Strength, -Weak, -Poison
  Leading Strike -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: hp -3, +Poison(3)
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -22, Poison(3→6)
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, Poison(6→9)
  Leading Strike -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: hp -3, Poison(9→12)
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, Poison(12→15)
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -4, Poison(15→18)
  Finisher -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: hp +38, -Stock, -Poison
  Strike -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: hp -6, +Poison(3)
  turn_end
  Defend
  confirm

### Round 9
Agent plan (hypothesis): Combat should end.
Agent plan (hypothesis): Combat ends.
Intent: Axebot: Attack(9), Debuff
  Strangle+ -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: block -10, +Strangle(3)
  Burst
    energy -1 | block +1 | +Burst(1) | enemy_deltas: Axebot: hp -3
  Backflip
    energy -1 | block +12 | -Burst | enemy_deltas: Axebot: hp -6
  Escape Plan
    block +4 | enemy_deltas: Axebot: hp -3
  Leading Strike -> Axebot[0]
    energy -1 | block +1 | enemy_deltas: Axebot: hp -6, +Poison(3)
  Shiv -> Axebot[0]
    block -19 | -Phantom Blades | -Well-Laid Plans | -Afterimage | -Envenom | -Accelerant | enemy_deltas: Axebot: DIED
## Combat Analytics: multi:Axebot+Axebot (WIN - 9 rounds)

Cards played (with descriptions):
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 2 plays, 7 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 1 block
  Defend "Gain 5 Block." -> 5 plays, 24 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Survivor+ "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 3 plays, 1 block, generates 2 Shivs
  Shiv+ "Retain. Deal 18 damage. Exhaust." -> 6 plays, 12 dmg, 5 block, +9 poison, EXHAUST
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 5 plays, 12 dmg, 5 block, +9 poison, generates 2 Shivs
  Shiv "Retain. Deal 3 damage. Exhaust." -> 9 plays, 34 dmg, 8 block, +12 poison, EXHAUST
  Burst "This turn, your next Skill is played an extra time." -> 2 plays, 3 dmg, 2 block
  Apparition "Ethereal. Gain 1 Intangible. Exhaust." -> 2 plays, 3 block, EXHAUST
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 6 dmg, 18 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 3 dmg, 5 block
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 2 block
  Knife Trap "Play every Shiv in your Exhaust Pile on the enemy. (Plays 6 Shivs)" -> 1 plays, 7 block, EXHAUST
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 1 block
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays, 1 block
  Leg Sweep "Apply 2 Weak. Gain 8 Block." -> 1 plays, 9 block
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 7 times)" -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg, 1 block, +3 poison

Token attribution (Shivs):
  Leading Strike: 9 Shivs -> ~28 dmg
  Hidden Daggers+: 5 Shivs -> ~15 dmg
  other: 1 Shivs -> ~3 dmg

Poison stacks applied per card:
  Shiv: 12 stacks
  Shiv+: 9 stacks
  Leading Strike: 9 stacks
  Strike: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:6 -> R9:-
  Stock: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Stock[0]: R1:2 -> R2:2 -> R3:2 -> R4:1 -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Stock[1]: R1:2 -> R2:2 -> R3:2 -> R4:2 -> R5:2 -> R6:- -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:4 -> R9:1
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:1 -> R5:5 -> R6:1 -> R7:1 -> R8:- -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:4 -> R5:4 -> R6:4 -> R7:4 -> R8:- -> R9:-
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Axebot+Axebot (Floor 37, monster)
Relics: Ring of the Snake, Cursed Pearl, Potion Belt, Membership Card, Prayer Wheel, Ornamental Fan, Fresnel Lens, Very Hot Cocoa, Oddly Smooth Stone, Venerable Tea Set, Bag of Marbles, Pendulum, Iron Club
Deck (42): Defend x5, Blade Dance x3, Backflip x2, Piercing Wail+ x2, Strike x2, Accuracy, Accuracy+, Afterimage+, Alchemize+, Blade Dance+, Blur+, Calculated Gamble, Cloak and Dagger, Dagger Spray+, Dramatic Entrance, Envenom, Escape Plan, Expertise, Expose, Fan of Knives, Finisher, Follow Through, Greed, Infinite Blades+, Master of Strategy, Neutralize, Phantom Blades, Piercing Wail, Secret Technique, Strangle+, Survivor, Tools of the Trade, Up My Sleeve
Enemies: Axebot HP=43/43, Axebot HP=42/42

### Round 1
Intent: Axebot: Buff, Axebot: Attack(8), Debuff
  Follow Through -> Axebot[1]
    energy -1 | enemy_deltas: Axebot: hp -20
  Afterimage+
    energy -1 | +Afterimage(1)
  Accuracy+
    energy -1 | block +1 | +Accuracy(6)
  Phantom Blades
    energy -1 | block +1 | +Phantom Blades(9)
  Infinite Blades+
    energy -1 | block +1 | +Infinite Blades(1)
  Dramatic Entrance
    block +1 | exhausted: Dramatic Entrance [0]: Innate. Deal 11 damage to ALL enemies. Exhaust. | enemy_deltas: Axebot: hp -16
  Strangle+ -> Axebot[0]
    energy -1 | block +5
  Dagger Spray+
    energy -1 | block +1 | enemy_deltas: Axebot: hp +28, Stock(2→1), -Vulnerable
  turn_end

### Round 2
Intent: Axebot: Attack(9), Debuff, Axebot: Attack(9), Debuff
  Shiv -> Axebot[1]
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Axebot: hp -9, block -10
  Secret Technique
  Master of Strategy
  Master of Strategy
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust.
  Escape Plan
    block +1
  Backflip
    energy -1 | block +9
  Neutralize -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp -3, +Weak(1)
  Calculated Gamble
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust.
  Expose -> Axebot[0]
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust.
  Accuracy
    energy -1 | block +1 | Accuracy(6→10)
  Blade Dance
    energy -1 | block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust.
  Shiv -> Axebot[0]
    block +5
  Shiv -> Axebot[0]
    block +1
  Shiv -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp -14
  turn_end

### Round 3
Intent: Axebot: Buff, Axebot: Attack(6x2=12)
  Shiv -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp +35, -Stock, -Strength
  Blade Dance
    energy -1 | block +1
  Blade Dance
    energy -1 | block +1
  Shiv -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[1]
    block +5 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[1]
    block +1 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[1]
    block +5 | enemy_deltas: Axebot: hp +39, block +10, +Strength(1)
  Blade Dance+
    energy -1 | block +1 | exhausted: Shiv*10 [0]: Retain. Deal 4 damage. Exhaust.
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: block -10
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[0]
    block +5 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -10
  Shiv -> Axebot[0]
    block +1 | enemy_deltas: Axebot: hp -10
  turn_end

### Round 4
Intent: Axebot: Attack(10x2=20)
  Shiv -> Axebot[0]
    -Dexterity | -Afterimage | -Accuracy | -Phantom Blades | -Infinite Blades | enemy_deltas: Axebot: DIED
## Combat Analytics: multi:Axebot+Axebot (WIN - 4 rounds)

Cards played (with descriptions):
  Follow Through "Deal 7 damage. If you have 5 or more other cards in your Hand, hits an additional time." -> 1 plays, 20 dmg
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Accuracy+ "Shivs deal 6 additional damage." -> 1 plays, 1 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 1 block
  Infinite Blades+ "Innate. At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, 1 block, generates 1 Shivs
  Dramatic Entrance "Innate. Deal 11 damage to ALL enemies. Exhaust." -> 1 plays, 16 dmg, 1 block, EXHAUST
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 5 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 1 plays, 1 block
  Shiv "Retain. Deal 19 damage. Exhaust." -> 16 plays, 103 dmg, 31 block, EXHAUST
  Secret Technique "Put a Skill from your Draw Pile into your Hand. Exhaust." -> 1 plays, EXHAUST
  Master of Strategy "Draw 3 cards. Exhaust." -> 1 plays, 1 block, EXHAUST
  Escape Plan "Draw 1 card. If you draw a Skill, gain 4 Block." -> 1 plays, 1 block
  Backflip "Gain 8 Block. Draw 2 cards." -> 1 plays, 9 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg, 1 block
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 1 block, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST
  Accuracy "Shivs deal 4 additional damage." -> 1 plays, 1 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 3 plays, 3 block, EXHAUST, generates 3 Shivs
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 block, EXHAUST, generates 4 Shivs

Active powers: Dexterity(1)

Token attribution (Shivs):
  Blade Dance: 9 Shivs -> ~58 dmg
  Blade Dance+: 4 Shivs -> ~26 dmg
  other: 3 Shivs -> ~19 dmg

Enemy power timeline:
  Stock: R1:- -> R2:- -> R3:1 -> R4:-
  Stock[0]: R1:2 -> R2:1 -> R3:- -> R4:-
  Stock[1]: R1:2 -> R2:1 -> R3:- -> R4:-
  Strength: R1:- -> R2:- -> R3:- -> R4:5
  Strength[0]: R1:- -> R2:1 -> R3:1 -> R4:-
  Strength[1]: R1:- -> R2:1 -> R3:1 -> R4:-
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:-

[Selected: elite] Mecha Knight (F43, elite)
## Combat Replay: vs Mecha Knight (Floor 43, elite)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull, Distinguished Cape, Lantern, Prayer Wheel
Deck (33): Defend x5, Apparition x3, Leading Strike x3, Strike x3, Hidden Daggers+ x2, Phantom Blades x2, Accelerant+, Afterimage, Ascender's Bane, Backflip, Burst, Envenom+, Escape Plan, Expose, Finisher, Knife Trap, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Mecha Knight HP=300/300

### Round 1
Agent plan (hypothesis): Retain Apparition and Hidden Daggers+. Make sure to use Apparition on Turn 4 (when the heavy attack + Strength scaling happens).
Intent: Mecha Knight: Attack(25)
  Apparition
    energy -1 | +Intangible(1) | exhausted: Apparition [1]: Ethereal. Gain 1 Intangible. Exhaust.
  Well-Laid Plans+
    energy -1 | block +7 | +Well-Laid Plans(2)
  Leading Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -3
  Shiv -> Mecha Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  turn_end
  Knife Trap
  Hidden Daggers+

### Round 2
Agent plan (hypothesis): Apparition will be retained. Turn 4 is the big attack.
Intent: Mecha Knight: StatusCard(4)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4, Artifact(3→2)
  Hidden Daggers+
  Defend
  Defend
  Shiv+ -> Mecha Knight[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -6
  Shiv+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -6
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  Knife Trap -> Mecha Knight[0]
    energy -2 | enemy_deltas: Mecha Knight: hp -20
  turn_end

### Round 3
Intent: Mecha Knight: Defend, Buff
  Afterimage
    energy -1 | +Afterimage(1)
  Leading Strike -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -3
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -4
  Survivor+
    energy -1 | block +11
  Burn
  Defend
    energy -1 | block +6
  turn_end
  Defend
  confirm

### Round 4
Agent plan (hypothesis): See what we draw
Agent plan (hypothesis): Retain Leading Strike for Shiv generation once Envenom is in play.
Intent: Mecha Knight: Attack(40)
  Backflip
    energy -1 | block +6
  Escape Plan
    block +1
  Leg Sweep -> Mecha Knight[0]
    energy -2 | block +12 | enemy_deltas: Mecha Knight: Artifact(2→1)
  Defend
    energy -1 | block +6
  turn_end
  Envenom+
  Leading Strike

### Round 5
Agent plan (hypothesis): We applied a ton of poison and set up our primary scaling. Expect a massive attack on Turn 7 (cycle round 4). We need to retain defense or Apparition for that turn.
Intent: Mecha Knight: StatusCard(4)
  Expose -> Mecha Knight[0]
    block +1 | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Mecha Knight: +Vulnerable(2), -Artifact
  Strangle+ -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -15, +Strangle(3)
  Envenom+
    energy -2 | block +1 | +Envenom(2) | enemy_deltas: Mecha Knight: hp -3
  Leading Strike -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -7, +Poison(3)
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -9, Poison(3→6)
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -9, Poison(6→9)
  Hidden Daggers+
    block +1 | enemy_deltas: Mecha Knight: hp -3
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -12, Poison(9→12)
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -12, Poison(12→15)
  turn_end
    exhausted: Shiv+*4 [0]: Deal 6 damage. Exhaust.

### Round 6
Agent plan (hypothesis): Retain Defends to prepare for the massive attack next turn. We've stacked a lot of poison so a kill may be within reach.
Intent: Mecha Knight: Defend, Buff
  Hidden Daggers+
  Burn
  Burn
  Phantom Blades
    energy -1 | block +1 | +Phantom Blades(9)
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -22, Poison(14→17)
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -9, Poison(17→20)
  Finisher -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -18, Poison(20→26)
  turn_end
  Defend
  Defend

### Round 7
Agent plan (hypothesis): Accelerant+ completely destroys bosses and elites when enough poison is stacked.
Intent: Mecha Knight: Attack(45)
  Neutralize+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: block -4, +Weak(2)
  Accelerant+
    energy -1 | block +1 | +Accelerant(2)
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Survivor+
    energy -1 | block +11
  Defend
  Hidden Daggers+
    block +1
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -4, block -11, Poison(25→28)
  Shiv+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -6, Poison(28→31)
  turn_end
  Burst
  confirm
## Combat Analytics: Mecha Knight (WIN - 7 rounds)

Cards played (with descriptions):
  Apparition "Ethereal. Gain 1 Intangible. Exhaust." -> 1 plays, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 7 block
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 13 dmg, 2 block, +3 poison, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 34 dmg, 4 block, +6 poison, EXHAUST
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg, 1 block
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 4 plays, 3 dmg, 2 block, generates 2 Shivs
  Shiv+ "Deal 6 damage. Exhaust." -> 8 plays, 77 dmg, 6 block, +18 poison, EXHAUST
  Knife Trap "Play every Shiv in your Exhaust Pile on the enemy. (Plays 4 Shivs)" -> 1 plays, 20 dmg, EXHAUST
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Survivor+ "Gain 11 Block. Discard 1 card." -> 2 plays, 22 block
  Defend "Gain 5 Block." -> 4 plays, 24 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 6 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 1 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 12 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 15 dmg, 1 block
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 3 dmg, 1 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 1 block
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 2 times)" -> 1 plays, 18 dmg, 1 block, +6 poison
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays, 1 block

Token attribution (Shivs):
  Hidden Daggers+: 8 Shivs -> ~63 dmg
  Leading Strike: 6 Shivs -> ~48 dmg

Poison stacks applied per card:
  Shiv+: 18 stacks
  Shiv: 6 stacks
  Finisher: 6 stacks
  Leading Strike: 3 stacks

Enemy power timeline:
  Artifact: R1:3 -> R2:3 -> R3:2 -> R4:2 -> R5:1 -> R6:- -> R7:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:14 -> R7:25
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Mecha Knight (Floor 43, elite)
Relics: Ring of the Snake, Arcane Scroll, Fresnel Lens, Oddly Smooth Stone, Radiant Pearl, Amethyst Aubergine, Pendulum, Throwing Axe, Game Piece, Red Mask
Deck (30): Defend x5, Blade Dance x2, Phantom Blades x2, Strike x2, Abrasive, Blur+, Burst+, Calculated Gamble+, Cloak and Dagger, Cloak and Dagger+, Dagger Throw, Flick-Flack, Hidden Daggers, Infinite Blades, Leg Sweep, Neutralize+, Prepared+, Reflex+, Ricochet, Ricochet+, Survivor, Tracking+, Untouchable
Enemies: Mecha Knight HP=300/300

### Round 1
Intent: Mecha Knight: Attack(25)
  Blur+
    energy -1 | block +22 | +Blur(2)
  Hidden Daggers
  Abrasive
  Flick-Flack
  Tracking+
    energy -1 | +Tracking(2) | enemy_deltas: Mecha Knight: hp -6
  Luminesce
    energy +2 | exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.
  Defend
    energy -1 | block +7
  Shiv -> Mecha Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -9
  Leg Sweep
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  Calculated Gamble+
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  turn_end

### Round 2
Intent: Mecha Knight: StatusCard(4)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Retain. Deal 4 damage. Exhaust.
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -13
  Cloak and Dagger
    energy -1 | block +10
  turn_end

### Round 3
Intent: Mecha Knight: Defend, Buff
  Phantom Blades
    energy -1 | Phantom Blades(9→18)
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -22
  Prepared+
  Ricochet
  Burn
  Survivor
    energy -1 | block +10
  Burn
  Cloak and Dagger+
    energy -1 | block +10
  turn_end

### Round 4
Intent: Mecha Knight: Attack(40)
  Speed Potion
    Dexterity(2→7) | +Speed Potion(5)
  Defend
    energy -1 | block +12
  Fortifier
    block +24
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: block -4, Artifact(2→1)
  Infinite Blades
    energy -1 | +Infinite Blades(1)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: block -4, -Artifact
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -15, block -7
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  turn_end

### Round 5
Intent: Mecha Knight: StatusCard(4)
  Leg Sweep -> Mecha Knight[0]
    energy -2 | block +15 | enemy_deltas: Mecha Knight: +Weak(2)
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -44
  Hidden Daggers
  Ricochet
  Burn
  Defend
    energy -1 | block +7 | enemy_deltas: Mecha Knight: hp -6
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -8
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -8
  turn_end

### Round 6
Intent: Mecha Knight: Defend, Buff
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -18
  Burn
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -44
  Blade Dance
    energy -1
  Survivor
    energy -1 | block +10
  Burn
  turn_end

### Round 7
Intent: Mecha Knight: Attack(45)
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -7, block -15
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Cloak and Dagger+
    energy -1 | block +10
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4
  Blur+
    energy -1 | block +12 | +Blur(1)
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  turn_end

### Round 8
Intent: Mecha Knight: StatusCard(4)
  Shiv -> Mecha Knight[0]
    -Dexterity | -Thorns | -Tracking | -Phantom Blades | -Infinite Blades | enemy_deltas: Mecha Knight: DIED
## Combat Analytics: Mecha Knight (WIN - 8 rounds)

Cards played (with descriptions):
  Blur+ "Gain 11 Block. Block is not removed at the start of your next turn." -> 2 plays, 34 block
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 2 plays, generates 2 Shivs
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays, 6 dmg
  Luminesce "Retain. Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Defend "Gain 7 Block." -> 3 plays, 6 dmg, 26 block
  Shiv "Deal 4 damage. Exhaust." -> 19 plays, 201 dmg, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 27 dmg
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Calculated Gamble+ "Retain. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage. Draw 2 cards the first time this is played." -> 2 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 2 plays, EXHAUST, generates 3 Shivs
  Cloak and Dagger "Gain 10 Block. Add 1 Shiv into your Hand." -> 1 plays, 10 block, generates 1 Shivs
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 1 plays
  Survivor "Gain 10 Block. Discard 1 card." -> 2 plays, 20 block
  Cloak and Dagger+ "Gain 10 Block. Add 2 Shivs into your Hand." -> 2 plays, 20 block, generates 2 Shivs
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays
  Infinite Blades "At the start of your turn, add 1 Shiv into your Hand." -> 1 plays, generates 1 Shivs
  Leg Sweep "Apply 2 Weak. Gain 15 Block." -> 1 plays, 15 block

Active powers: Dexterity(1)

Token attribution (Shivs):
  other: 9 Shivs -> ~95 dmg
  Hidden Daggers: 4 Shivs -> ~42 dmg
  Cloak and Dagger+: 3 Shivs -> ~32 dmg
  Blade Dance: 2 Shivs -> ~21 dmg
  Infinite Blades: 1 Shivs -> ~11 dmg

Enemy power timeline:
  Artifact: R1:2 -> R2:2 -> R3:2 -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10 -> R8:10
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:-

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull, Distinguished Cape, Lantern, Prayer Wheel, Candelabra
Deck (36): Defend x5, Apparition x3, Leading Strike x3, Strike x3, Hidden Daggers+ x2, Phantom Blades x2, Accelerant+, Afterimage+, Ascender's Bane, Backflip, Bouncing Flask+, Burst, Envenom+, Escape Plan, Expose, Finisher, Haze, Knife Trap, Leg Sweep, Neutralize+, Storm of Steel, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Afterimage+
    energy -1 | block +7 | +Afterimage(1)
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +12 | enemy_deltas: Torch Head Amalgam: +Weak(2)
  Strangle+ -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -10, +Strangle(3)
  Hidden Daggers+
  Haze
  Apparition
  turn_end
    block +2 | enemy_deltas: Queen: hp -6, +Poison(5)

### Round 2
Agent plan (hypothesis): Turn 3 will provide 6 energy total thanks to Pael's Flesh, Lantern, and Candelabra. Use this massive energy boost to set up remaining powers (Envenom, Well-Laid Plans) or burst damage if the hand allows. Queen will start gaining 20 block per turn now.
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Escape Plan
    block +4
  Bouncing Flask+
    energy -2 | block +1 | enemy_deltas: Torch Head Amalgam: Poison(4→12); Queen: Poison(4→12)
  Survivor+
    energy -1 | block +11
  Defend
  Hidden Daggers+
    block +1
  Shiv+ -> Queen[1]
    block +1 | exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Queen: hp -6
  Shiv+ -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -6
  Strike -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -6
  Defend
    energy -1 | block +6
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Neutralize+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, +Weak(2)
  Leading Strike -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -2
  Shiv -> Queen[1]
    block +1 | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Queen: hp -3
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -3
  Leading Strike -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -2
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -3
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -3
  turn_end

### Round 4
Agent plan (hypothesis): We are scaling poison nicely. Keep focusing down the Queen.
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Accelerant+
    energy -1 | block +1 | +Accelerant(2)
  Apparition
    energy -1 | block +1 | +Intangible(1) | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.
  Expose -> Queen[1]
    block +1 | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Queen: block -20, +Vulnerable(2)
  turn_end

### Round 5
Agent plan (hypothesis): If we draw Apparition, play it immediately.
Agent plan (hypothesis): Retain Storm of Steel and Phantom Blades if WLP allows.
Intent: Torch Head Amalgam: Attack(24), Queen: Buff, Defend
  Backflip
    energy -1 | block +4
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Defend
    energy -1 | block +4
  Leading Strike -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: block -3
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: block -4
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: block -4
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.
  Phantom Blades
  Storm of Steel

### Round 6
Agent plan (hypothesis): Massive value turn. The Queen is gaining block but Poison bypasses it completely. Keep defending and playing setup cards.
Agent plan (hypothesis): Shivs stack poison fast thanks to Envenom and Snecko Skull.
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Apparition
    energy -1 | block +1 | +Intangible(1)
  Storm of Steel
    energy -1 | block +2 | enemy_deltas: Torch Head Amalgam: Poison(4→9); Queen: Poison(4→9)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, Poison(9→12)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, Poison(12→15)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, Poison(15→18)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, Poison(18→21)
  turn_end
  Defend
  confirm

### Round 7
Agent plan (hypothesis): Retain Shiv+ so it loses Bound next turn and can be used for free poison.
Intent: Torch Head Amalgam: Attack(27), Queen: Buff, Defend
  Neutralize+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3, Poison(18→21), +Weak(2)
  Leg Sweep -> Torch Head Amalgam[0]
    energy -2 | block +9 | enemy_deltas: Torch Head Amalgam: Weak(2→4)
  Defend
    energy -1 | block +4
  turn_end
  Shiv+
  Strike

### Round 8
Agent plan (hypothesis): Retain the Bound Leading Strike so it's unbound next turn.
Intent: Queen: Attack(7x5=35)
  Survivor+
    energy -1 | block +8
  Hidden Daggers+
  Defend
    energy -1 | block +4
  Leading Strike -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -2, Poison(3→6)
  Shiv+ -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -4, Poison(6→9)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -3, Poison(9→12)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -3, Poison(12→15)
  turn_end
  Strike
  confirm

### Round 9
Agent plan (hypothesis): Fairy will proc, Queen dies next turn from massive Poison.
Intent: Queen: Attack(25)
  Escape Plan
    block +1
  Leading Strike -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -2, Poison(12→15)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -3, Poison(15→18)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -3, Poison(18→21)
  Strike -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -4, Poison(21→24)
  Finisher -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -16, Poison(24→36)
  Hidden Daggers+
  Burst
  Shiv+
  Shiv+ -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -4, Poison(36→39)
  Shiv+ -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -4, Poison(39→42)
  turn_end
  Leading Strike
  confirm

### Round 10
Agent plan (hypothesis): gg
Agent plan (hypothesis): We won!
Intent: Queen: Buff
  Strangle+ -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -7, Poison(39→42), +Strangle(3)
  Leading Strike -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -5, Poison(42→45)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -6, Poison(45→48)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -6, Poison(48→51)
  turn_end
  Backflip
  Defend
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 10 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays, 7 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 21 block
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 2 plays, 17 dmg, 2 block, +3 poison
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 3 plays, 1 block, generates 2 Shivs
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block. Bound" -> 2 plays, 5 block
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 1 plays, 1 block, +16 poison
  Survivor+ "Gain 11 Block. Discard 1 card." -> 2 plays, 19 block
  Shiv+ "Deal 6 damage. Exhaust." -> 5 plays, 24 dmg, 5 block, +9 poison, EXHAUST
  Strike "Deal 6 damage." -> 2 plays, 10 dmg, 2 block, +3 poison
  Defend "Gain 5 Block." -> 4 plays, 18 block
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 2 plays, 6 dmg, 2 block, +3 poison
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand. Bound" -> 6 plays, 13 dmg, 6 block, +9 poison, generates 2 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 16 plays, 48 dmg, 16 block, +30 poison, EXHAUST
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays, 1 block
  Apparition "Ethereal. Gain 1 Intangible. Exhaust." -> 2 plays, 2 block, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Bound Exhaust." -> 1 plays, 1 block, EXHAUST
  Backflip "Gain 3 Block. Draw 2 cards. Bound" -> 1 plays, 4 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison. Bound" -> 1 plays, 1 block
  Storm of Steel "Discard your Hand. Add 1 Shiv into your Hand for each card discarded." -> 1 plays, 2 block, +10 poison, generates 1 Shivs
  Finisher "Deal 4 damage for each Attack already played this turn. (Hits 4 times)" -> 1 plays, 16 dmg, 1 block, +12 poison

Token attribution (Shivs):
  Leading Strike: 12 Shivs -> ~41 dmg
  Hidden Daggers+: 4 Shivs -> ~14 dmg
  other: 4 Shivs -> ~14 dmg
  Storm of Steel: 1 Shivs -> ~3 dmg

Poison stacks applied per card:
  Shiv: 30 stacks
  Bouncing Flask+: 16 stacks
  Finisher: 12 stacks
  Storm of Steel: 10 stacks
  Leading Strike: 9 stacks
  Shiv+: 9 stacks
  turn_end: 5 stacks
  Neutralize+: 3 stacks
  Strike: 3 stacks
  Strangle+: 3 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:- -> R9:- -> R10:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:3 -> R9:12 -> R10:39
  Poison[0]: R1:- -> R2:4 -> R3:11 -> R4:10 -> R5:7 -> R6:4 -> R7:18 -> R8:- -> R9:- -> R10:-
  Poison[1]: R1:- -> R2:4 -> R3:11 -> R4:10 -> R5:7 -> R6:4 -> R7:6 -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:2 -> R9:2 -> R10:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Small Capsule, Eternal Feather, Pantograph, Archaic Tooth, Book of Five Rings, Music Box, Chandelier, Stone Cracker, Akabeko
Deck (34): Defend x5, Backflip x2, Bouncing Flask+ x2, Piercing Wail+ x2, Strike x2, Ascender's Bane, Backflip+, Blur, Burst, Clumsy, Dagger Throw, Deadly Poison, Deadly Poison+, Footwork, Footwork+, Haze+, Malaise+, Outbreak+, Predator, Predator+, Prepared+, Reflex+, Slice, Suppress+, Survivor+, Tools of the Trade+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Attack Potion
  Pinpoint
  Suppress+ -> Torch Head Amalgam[0]
    -Vigor | enemy_deltas: Torch Head Amalgam: hp -25, +Weak(5)
  Suppress+ -> Queen[1]
    enemy_deltas: Queen: hp -17, +Weak(5)
  Blur+
    energy -1 | block +8 | +Blur(1)
  Predator+ -> Queen[1]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -20
  Pinpoint -> Queen[1]
    enemy_deltas: Queen: hp -15
  turn_end
    exhausted: Clumsy [0]: Unplayable. Ethereal.

### Round 2
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Footwork
    energy -1 | +Dexterity(2)
  Prepared+
  Strike
  Outbreak+
  Footwork+
    energy -1 | Dexterity(2→5)
  Backflip
    energy -1 | block +10
  Malaise+ -> Torch Head Amalgam[0]
    exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Torch Head Amalgam: Weak(4→5), +Strength(-1)
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(7x3=21), Queen: Buff, Defend
  Deadly Poison+ -> Queen[1]
    energy -1 | enemy_deltas: Queen: +Poison(7)
  Piercing Wail+
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust. | enemy_deltas: Torch Head Amalgam: Strength(-1→-9), +Piercing Wail(8); Queen: +Strength(-8), +Piercing Wail(8)
  Tools of the Trade+
    +Tools of the Trade(1)
  turn_end
  Ascender's Bane

### Round 4
Intent: Torch Head Amalgam: Attack(15), Queen: Buff, Defend
  Backflip+
    energy -1 | block +9
  Defend
    energy -1 | block +7
  Strike+ -> Torch Head Amalgam[0]
    energy -1 | enemy_deltas: Torch Head Amalgam: hp -6
  Slice -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4
  turn_end
    exhausted: Strike+ [1]: Ethereal. Deal 9 damage.
  Predator

### Round 5
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Slice -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4
  Outbreak+
    energy -1 | +Outbreak(15)
  Deadly Poison -> Queen[1]
    energy -1 | enemy_deltas: Queen: Poison(5→10)
  Slice -> Queen[1]
    enemy_deltas: Queen: block -4
  Survivor+
    energy -1 | block +12
  turn_end
  Ascender's Bane

### Round 6
Intent: Torch Head Amalgam: Attack(11x3=33), Queen: Buff, Defend
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(1→6)
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(6→11)
  Prepared+
  Strike+
  Pinpoint
  Backflip
    energy -1 | block +7
  Blur+
    energy -1 | block +9 | +Blur(1)
  Defend
    energy -1 | block +7
  turn_end
  Burst

### Round 7
Intent: Torch Head Amalgam: Attack(19), Queen: Buff, Defend
  Backflip
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end
  Reflex+

### Round 8
Intent: Torch Head Amalgam: Attack(20), Queen: Buff, Defend
  Suppress+ -> Queen[1]
    enemy_deltas: Queen: block -12, +Weak(5)
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(9→14)
  Burst
    energy -1 | +Burst(1)
  Backflip+
    energy -1 | block +18 | -Burst
  Blur+
    energy -1 | block +9 | +Blur(1)
  turn_end
    exhausted: Strike+ [1]: Ethereal. Deal 9 damage.
  Strike

### Round 9
Intent: Torch Head Amalgam: Attack(14x3=42), Queen: Buff, Defend
  Slice -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(13→18)
  Dagger Throw -> Torch Head Amalgam[0]
    energy -1 | enemy_deltas: Torch Head Amalgam: hp -6
  Predator
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end
    exhausted: Strike+ [1]: Ethereal. Deal 9 damage.
  Pinpoint

### Round 10
Intent: Torch Head Amalgam: Attack(22), Queen: Buff, Defend
  Defend
    energy -1 | block +7
  Survivor+
    energy -1 | block +12
  Prepared+
  turn_end
  Haze+

### Round 11
Intent: Torch Head Amalgam: Attack(23), Queen: Buff, Defend
  Defend
    energy -1 | block +7
  Suppress+ -> Queen[1]
    enemy_deltas: Queen: hp -7, block -5, Weak(2→7)
  Suppress+ -> Queen[1]
    enemy_deltas: Queen: hp -12, Weak(7→12)
  Slice -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -4
  turn_end
    exhausted: Suppress+ [0]: Innate. Ethereal. Deal 17 damage. Apply 5 Weak.
  Strike

### Round 12
Intent: Torch Head Amalgam: Attack(18x3=54), Queen: Buff, Defend
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(15→20)
  Backflip
    energy -1 | block +7
  Suppress+ -> Torch Head Amalgam[0]
    enemy_deltas: Torch Head Amalgam: hp -12, Weak(20→25)
  Defend
    energy -1 | block +7
  turn_end
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 12 rounds)
Death cause: Killed by damage. HP 4 -> 0, took 0 damage.

Cards played (with descriptions):
  Suppress+ "Innate. Deal 25 damage. Apply 5 Weak." -> 11 plays, 133 dmg
  Blur+ "Gain 8 Block. Block is not removed at the start of your next turn." -> 3 plays, 26 block
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 1 plays, 20 dmg
  Pinpoint "Deal 15 damage. Costs 1 less 1 energy for each Skill played this turn." -> 1 plays, 15 dmg
  Footwork "Gain 2 Dexterity. Bound" -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Backflip "Gain 10 Block. Draw 2 cards." -> 4 plays, 31 block
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Deadly Poison+ "Apply 7 Poison. Bound" -> 1 plays, +7 poison
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Tools of the Trade+ "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Backflip+ "Gain 9 Block. Draw 2 cards. Bound" -> 2 plays, 27 block
  Defend "Gain 7 Block. Bound" -> 9 plays, 63 block
  Strike+ "Deal 6 damage." -> 1 plays, 6 dmg
  Slice "Deal 4 damage." -> 5 plays, 16 dmg
  Outbreak+ "Every 3 times you apply Poison, deal 15 damage to ALL enemies." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Survivor+ "Gain 12 Block. Discard 1 card. Bound" -> 2 plays, 24 block
  Burst "This turn, your next Skill is played an extra time." -> 1 plays
  Dagger Throw "Deal 6 damage. Draw 1 card. Discard 1 card." -> 1 plays, 6 dmg

Active powers: Vigor(8)

Poison stacks applied per card:
  Deadly Poison+: 7 stacks
  Deadly Poison: 5 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1
  Poison: R1:- -> R2:- -> R3:- -> R4:6 -> R5:5 -> R6:9 -> R7:8 -> R8:7 -> R9:6 -> R10:5 -> R11:- -> R12:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:6 -> R12:5
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:4 -> R12:9
  Strength: R1:- -> R2:- -> R3:-1 -> R4:- -> R5:1 -> R6:2 -> R7:3 -> R8:4 -> R9:5 -> R10:6 -> R11:7 -> R12:8
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:10 -> R8:9 -> R9:- -> R10:- -> R11:- -> R12:-
  Weak[0]: R1:- -> R2:4 -> R3:4 -> R4:3 -> R5:2 -> R6:- -> R7:- -> R8:- -> R9:13 -> R10:17 -> R11:16 -> R12:15
  Weak[1]: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:4 -> R10:3 -> R11:2 -> R12:11

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: WIN), F29(Infested Prism: WIN), F33(The Insatiable: WIN), F43(Mecha Knight: WIN), F48(Torch Head Amalgam: )
- Core Combat Principles: F2(Sludge Spinner: WIN), F4(Toadpole: WIN), F5(Corpse Slug: WIN), F7(Calcified Cultist: ), F9(Sewer Clam: WIN), F13(Living Fog: WIN), F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: WIN), F19(Thieving Hopper: WIN), F23(Bowlbug (Rock): WIN), F25(Exoskeleton: WIN), F29(Infested Prism: WIN), F30(Bowlbug (Rock): ), F31(Myte: WIN), F33(The Insatiable: WIN), F35(Devoted Sculptor: WIN), F36(Scroll of Biting: WIN), F37(Slimed Berserker: WIN), F39(Axebot: WIN), F43(Mecha Knight: WIN), F45(Fabricator: WIN), F46(Globe Head: WIN), F48(Torch Head Amalgam: )
- Deck Building Across the Run: F2(), F4(), F5(), F6(), F7(), F9(), F12(), F12(), F12(), F13(), F15(), F15(), F17(), F17(), F19(), F22(), F23(), F25(), F29(), F30(), F31(), F33(), F33(), F35(), F36(), F37(), F38(), F39(), F42(), F43(), F45(), F45(), F46(), F46()
- Map Routing and Path Planning: F1(), F1(), F7(), F10(), F11(), F18(), F18(), F19(), F20(), F21(), F22(), F23(), F26(), F27(), F29(), F30(), F34(), F34(), F36(), F36(), F39(), F39(), F41(), F43(), F45()
- Rest Site and Event Decisions: F8(), F11(), F16(), F24(), F28(), F32(), F40(), F44(), F47()
- Silent - Combat Sequencing: F2(Sludge Spinner: WIN), F4(Toadpole: WIN), F5(Corpse Slug: WIN), F7(Calcified Cultist: ), F9(Sewer Clam: WIN), F13(Living Fog: WIN), F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: WIN), F19(Thieving Hopper: WIN), F23(Bowlbug (Rock): WIN), F25(Exoskeleton: WIN), F29(Infested Prism: WIN), F30(Bowlbug (Rock): ), F31(Myte: WIN), F33(The Insatiable: WIN), F35(Devoted Sculptor: WIN), F36(Scroll of Biting: WIN), F37(Slimed Berserker: WIN), F39(Axebot: WIN), F43(Mecha Knight: WIN), F45(Fabricator: WIN), F46(Globe Head: WIN), F48(Torch Head Amalgam: )
- Silent - Draft and Shop Rules: F2(), F4(), F5(), F6(), F7(), F9(), F12(), F12(), F12(), F13(), F15(), F15(), F17(), F17(), F19(), F22(), F23(), F25(), F29(), F30(), F31(), F33(), F33(), F35(), F36(), F37(), F38(), F39(), F42(), F43(), F45(), F45(), F46(), F46()
- Silent - Route Priorities: F1(), F1(), F7(), F10(), F11(), F18(), F18(), F19(), F20(), F21(), F22(), F23(), F26(), F27(), F29(), F30(), F34(), F34(), F36(), F36(), F39(), F39(), F41(), F43(), F45()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.