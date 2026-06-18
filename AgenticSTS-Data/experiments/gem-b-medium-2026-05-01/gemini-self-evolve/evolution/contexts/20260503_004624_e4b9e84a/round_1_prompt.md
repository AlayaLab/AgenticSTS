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
Result: DEFEAT at Floor 33 (fitness: 100.4)
Combats won: 17/17
Run duration: 3553.1s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation: Need to add frontloaded damage to survive Act 1 hallways and Elites. Booming Conch gives an incredible turn 1 advantage against Elites.
- [map] Foundation: prioritizing frontloaded damage and block cards in early monster fights to stabilize for the late-act Elite and Boss; Booming Conch makes late Elites safer if we have high-impact cards to draw turn 1.
### F2
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation: prioritizing monster fights floors 1-3 to find essential frontloaded damage for Act 1 Elites; Booming Conch makes early Elites safer once damage is found.
### F3
- [card_reward] Foundation plan: taking early damage and discard enablers like Dagger Throw to leverage Flick-Flack for frontload. Focus on elite hunting with Booming Conch; look for more damage, draw, and discard synergies to build a solid core.
### F4
- [hand_select] Discarding Flick-Flack is the optimal move here to leverage its Sly effect.
- [card_reward] Foundation plan: survive with frontload damage like Leading Strike while looking for a core scaling engine, possibly in Shivs. Prioritize strong attacks for early elites, then look for draw and energy.
### F5
- [hand_select] Discarding Sly cards is a core mechanic for the Silent to cheat energy and tempo.
- [card_reward] Foundation plan: survive with frontload damage while looking for a core scaling engine, using Expose to burst priority targets. Prioritize heavy damage, efficient block, or a definitive synergy piece.
- [map] Foundation: prioritizing monster fights to find essential frontloaded damage for Act 1 Elites; Booming Conch makes the planned late Elite significantly safer once damage is found.
### F6
- [card_reward] Committed poison plan: prioritize efficient block, Dexterity, and survivability while Noxious Fumes scales and kills. Need more block and draw; skip generic attacks.
### F7
- [event] Foundation: Need to survive Act 1. Searching for good frontloaded damage or block to complement Noxious Fumes. Avoid slow setups.
### F8
- [card_reward] Foundation plan: surviving early fights. We have Noxious Fumes for scaling and Blade Dance for frontload/Joss Paper draw. Prioritize campfires for healing due to low HP, and look for efficient block and further Shiv synergies.
### F9
- [rest_site] Foundation: Deck relies on Noxious Fumes and physical damage like Shivs to clear Act 1. Needs better block density and a way to mitigate damage while poison ticks. Avoid bloated attacks.
- [map] Foundation: Noxious Fumes provides scaling, but immediate frontloaded damage is required for the upcoming Elite; Booming Conch provides a crucial turn 1 advantage. Target high-impact attacks and efficient block in card rewards. Use the upcoming Rest Sites to Smith if HP remains stable, otherwise heal to survive the Elite.
### F11
- [rest_site] Foundation: Deck relies on Noxious Fumes for slow fights and Shivs boosted by Strength for burst damage. Play Expose before Shivs to maximize burst. Needs better block density and a way to mitigate damage while poison ticks. Avoid bloated slow attacks.
- [map] Foundation: Utilizing Noxious Fumes for scaling while seeking high-impact frontloaded damage and block cards to survive Act 1 elites. Prioritizing Elite fights when a campfire is available immediately afterward to safely secure relics and rare card rewards.
### F12
- [card_reward] Foundation plan: Use Shivs and Noxious Fumes to scale damage while keeping the deck thin. Looking for a core scaling piece (like Accuracy or stronger poison synergies) and more consistent draw/mitigation. Avoid adding more disjointed synergy cards without enablers.
### F13
- [rest_site] Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Play Expose before Shivs to maximize burst. Needs better block density, card draw, and a way to mitigate damage while poison ticks. Avoid bloated slow attacks.
### F14
- [card_reward] Foundation plan: survive with frontload and efficient block. With Blade Dance and Joss Paper (draw on exhaust), we are leaning heavily towards a Shiv engine. Need more Shiv generators and payoffs (like Finisher or Accuracy). Avoid adding more narrow poison cards.
- [map] Foundation: Focusing on survival and basic deck thinning. Noxious Fumes provides scaling, but the immediate priority is finding efficient block and front-loaded damage cards while using shops to remove basic Strikes.
### F16
- [rest_site] Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Play Expose before Shivs to maximize burst. Prioritize finding better card draw and consistent block to survive while poison scales.
### F17
- [card_reward] Committed to a shiv-poison hybrid engine. Envenom turns shivs into lethal scaling. Focus on surviving early turns to play Envenom, then spam shivs while blocking. Need more draw, cheap block, and a few more shiv generators. Avoid expensive attacks.
### F18
- [event] Foundation: Deck relies on Noxious Fumes and Envenom with Shivs for scaling damage. Very Hot Cocoa provides explosive turn 1 energy, so prioritize aggressive turn 1 deployments of powers and defensive scaling. Seek more card draw to fully utilize the initial energy burst and prioritize removing Strikes.
- [map] Foundation: Relying on Noxious Fumes for scaling while prioritizing block and efficient front-loaded damage. The goal is to thin the deck at shops and use the high number of rest sites to upgrade defensive cards, ensuring we survive long enough for poison to tick down Act 2's high-damage threats.
### F19
- [card_reward] Foundation plan: survive using Envenom/Fumes while digging for card draw. With 7 energy on turn 1 from Cocoa, prioritize premium draw (Acrobatics, Backflip) and high-impact expensive cards over cheap/free cards that empty the hand.
### F20
- [card_reward] Committed to Envenom/Fumes poison engine supported by Shivs and defensive stalling. Focus on upgrading key pieces, finding efficient block, and acquiring more Shiv generation or passive defense. Avoid bloating with cards that don't directly feed the engine.
- [map] Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Use Expose before Shivs to maximize damage, and prioritize defensive play while Noxious Fumes scales in longer encounters.
### F21
- [hand_select] Focus on mitigation while poison (10 on Ovicopter) scales.
- [card_reward] Committed poison/shiv hybrid plan: Use Envenom with shiv generators and Noxious Fumes for scaling damage, while surviving with efficient block and Piercing Wail. Look for upgraded draw/discard outlets, and focus on upgrading key cards.
### F23
- [card_select] Use Shivs and Envenom to stack poison and burst down enemies. Play defensively while powers scale.
- [card_reward] Committed to Envenom/Shiv poison scaling with Noxious Fumes. Use Blade Dances to stack poison via Envenom while relying on strong block and Piercing Wails for mitigation. Prioritize finding more card draw and discard outlets.
- [map] Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We need to stabilize HP via Rest Sites and avoid risky Elites until we have more sustain or higher burst potential.
### F24
- [card_reward] Committed to Shiv/Poison hybrid via Envenom. Use Turn 1 surplus energy (Very Hot Cocoa) and draw (Expertise+) to rapidly deploy powers (Envenom, Fumes) and cycle through early attacks. Keep looking for multi-hit scaling and block solutions; remove basic Strikes/Defends.
### F25
- [rest_site] Committed poison/shiv hybrid: use Very Hot Cocoa to play Envenom/Noxious Fumes early, then burst with Shivs (buffed by Girya Strength) to stack poison rapidly. Block and survive while poison scales.
### F27
- [rest_site] Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We need to stabilize HP via Rest Sites and avoid risky Elites until we have more sustain or higher burst potential. Need more card draw to utilize Very Hot Cocoa.
### F28
- [card_reward] Committed poison/shiv plan: stack poison via Envenom and Shivs, let Noxious Fumes scale passively, and survive with Weak/efficient block. Needs focus on defense and card draw; avoid bloated damage cards.
### F29
- [rest_site] Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We rely on explosive turn 1 energy from Very Hot Cocoa to setup Envenom/Fumes or play early defensive scaling.
### F30
- [card_reward] Committed to Shiv/Poison hybrid: use Very Hot Cocoa to play Envenom/Phantom Blades turn 1, then spam retained Shivs to stack poison and trigger Joss Paper. Need draw/discard synergy and block scaling. Skip generic attacks.
### F31
- [card_reward] Committed poison/shiv plan: stack passive poison with Fumes and Envenom+Shivs, then defend heavily with Footwork, Piercing Wail, and block cards while poison finishes them.
### F32
- [rest_site] Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. Use Piercing Wails and Leg Sweep to mitigate boss burst turns. Need to remove basic Strikes in Act 3 and find more card draw to cycle faster.

### Combat Decision Digest (18 combats)
F2 [monster] Nibbit (5R, HP 56->46, loss=10, WIN)
  R1[Nibbit: Atk(12)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=0
  R2[Nibbit: Atk(6), Defend]: Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R3[Nibbit: Buff]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Nibbit: Atk(14)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=21 taken=10
  R5[Nibbit: Atk(8), Defend]: Strike | dealt=0 taken=0

F3 [monster] Fuzzy Wurm Crawler (5R, HP 46->40, loss=6, WIN)
  R1[Fuzzy Wurm Crawler: Atk(4)]: Strike(6dmg)->Strike(6dmg)->Defend(+5blk) | dealt=12 taken=0
  R2[Fuzzy Wurm Crawler: Buff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Flick-Flack(6dmg) | dealt=21 taken=0
  R3[Fuzzy Wurm Crawler: Atk(11)]: Defend(+5blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=6
  R4[Fuzzy Wurm Crawler: Atk(11)]: Defend(+5blk)->Strike(6dmg)->Survivor(+8blk) | dealt=6 taken=0
  R5[Fuzzy Wurm Crawler: Buff]: Neutralize(3dmg,1+Weak(1))->Strike | dealt=3 taken=0

F4 [monster] Shrinker Beetle (3R, HP 40->40, loss=0, WIN)
  R1[Shrinker Beetle: DebuffStrong]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=21 taken=0
  R2[Shrinker Beetle: Atk(7)]: Dagger Throw(6dmg)->Flick-Flack(+5blk)->Defend(+5blk)->Defend | dealt=0 taken=0
  R3[Shrinker Beetle: Atk(13)]: Neutralize(2dmg,1+Weak(1))->Dagger Throw(6dmg)->Flick-Flack | dealt=2 taken=0

F5 [monster] multi:Assassin Raider+Crossbow Raider+Tracker Raider (3R, HP 40->38, loss=2, WIN)
  R1[Tracker Raider: Debuff+Crossbow Raider: Defend+Assassin Raider: Atk(11)]: Dagger Throw(9dmg)->Flick-Flack(3dmg)->Leading Strike(exhaust:1)->Shiv(6dmg)->Strike(4dmg)->Shiv | dealt=15 taken=0
  R2[Tracker Raider: Atk(1x8=8)+Crossbow Raider: Atk(14)]: Neutralize(1+Weak(1))->Strike->Defend(+3blk)->Defend(+3blk) | dealt=5 taken=2
  R3[Tracker Raider: Atk(1x8=8)]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike(power:-Frail) | dealt=11 taken=0

F6 [monster] Vine Shambler (5R, HP 38->30, loss=8, WIN)
  R1[Vine Shambler: Atk(6x2=12)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg) | dealt=14 taken=0
  R2[Vine Shambler: Atk(8), CardDebuff]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R3[Vine Shambler: Atk(16)]: Expose(1+Vulnerable(2),exhaust:1)->Survivor(+8blk)->Flick-Flack(18dmg)->Strike | dealt=18 taken=8
  R4[Vine Shambler: Atk(6x2=12)]: Neutralize(4dmg,1+Weak(1))->Survivor(+8blk)->Flick-Flack(18dmg)->Strike(+5blk)->Defend | dealt=22 taken=0
  R5[Vine Shambler: Atk(8), CardDebuff]: Strike | dealt=0 taken=0

F8 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (M)+Twig Slime (S) (5R, HP 30->16, loss=14, WIN)
  R1[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Twig Slime (S): Atk(4)+Leaf Slime (S): StatusCard(1)]: Neutralize(3dmg,1+Weak(1))->Dagger Throw->Leading Strike(3dmg)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Survivor(+8blk) | dealt=14 taken=0
  R2[Twig Slime (M): Atk(11)+Leaf Slime (M): Atk(8)+Leaf Slime (S): Atk(3)]: Flick-Flack(12dmg)->Defend(+5blk)->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=15 taken=14
  R3[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)]: Expose(1+Vulnerable(2),exhaust:1)->Strike(9dmg)->Strike(9dmg) | dealt=18 taken=0
  R4[Twig Slime (M): Atk(11)+Leaf Slime (M): Atk(8)]: Survivor(+8blk)->Slimed(exhaust:1)->Neutralize(3dmg,1+Weak(1))->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg) | dealt=14 taken=0
  R5[Leaf Slime (M): StatusCard(2)]: Slimed->Flick-Flack(6dmg)->Strike(power:-Noxious Fumes) | dealt=6 taken=0

F12 [elite] Bygone Effigy (3R, HP 37->37, loss=0, WIN)
  R1[Bygone Effigy: Sleep]: Expose(1+Vulnerable(2),exhaust:1)->Leading Strike(9dmg)->Shiv(12dmg,exhaust:1)->Shiv(13dmg)->Blade Dance(exhaust:1)->Shiv(15dmg)->Shiv(16dmg)->Shiv(17dmg)->Dagger Throw(32dmg) | dealt=82 taken=0
  R2[Bygone Effigy: Buff]: Noxious Fumes(power:+Noxious Fumes(2))->Neutralize(9dmg,1+Weak(1)) | dealt=9 taken=0
  R3[Bygone Effigy: Atk(23)]: Neutralize(6dmg,1+Weak(1))->Strike(power:-Strength,power:-Noxious Fumes) | dealt=6 taken=0

F14 [monster] multi:Slithering Strangler+Twig Slime (S)+Twig Slime (S) (3R, HP 37->35, loss=2, WIN)
  R1[Twig Slime (S): Atk(4)+Twig Slime (S): Atk(4)+Slithering Strangler: Debuff]: Expose(exhaust:1)->Flick-Flack(16dmg)->Strike->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=19 taken=0
  R2[Slithering Strangler: Atk(12)]: Leading Strike(5dmg)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=17 taken=2
  R3[Slithering Strangler: Debuff]: Neutralize(5dmg,1+Weak(1))->Blade Dance(exhaust:1)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Strike(power:-Strength,power:-Noxious Fumes,power:-Constrict) | dealt=23 taken=0

F17 [boss] multi:Kin Follower+Kin Follower+Kin Priest (6R, HP 56->11, loss=45, WIN)
  R1[Kin Follower: Buff+Kin Follower: Atk(5)+Kin Priest: Atk(8), Debuff]: Expose(1+Vulnerable(2),exhaust:1)->Leading Strike(7dmg)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Dash(18dmg,+10blk) | dealt=43 taken=3
  R2[Kin Follower: Atk(7)+Kin Follower: Atk(2x2=4)+Kin Priest: Atk(8), Debuff]: Blade Dance(exhaust:1)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Dagger Throw(16dmg)->Flick-Flack(12dmg)->Strike | dealt=39 taken=19
  R3[Kin Follower: Atk(4x2=8)+Kin Follower: Buff+Kin Priest: Atk(3x3=9)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk) | dealt=3 taken=4
  R4[Kin Follower: Buff+Kin Follower: Atk(7)+Kin Priest: Buff]: Dash(18dmg,+10blk)->Strike(12dmg) | dealt=30 taken=0
  R5[Kin Follower: Atk(9)+Kin Follower: Atk(4x2=8)+Kin Priest: Atk(10), Debuff]: Survivor(+8blk)->Strike(12dmg)->Strike(12dmg) | dealt=24 taken=19
  R6[Kin Follower: Atk(6x2=12)+Kin Follower: Buff+Kin Priest: Atk(10), Debuff]: Neutralize(7dmg,1+Weak(1))->Leading Strike(7dmg)->Shiv(9dmg)->Shiv(power:-Strength,power:-Frail) | dealt=23 taken=0

F19 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton (2R, HP 58->58, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff]: Expose(exhaust:1)->Blade Dance(exhaust:1)->Leading Strike->Shiv(exhaust:1)->Shiv*2->Strike*3->Shiv->Shiv(6dmg)->Strike(8dmg) | dealt=14 taken=0
  R2[Exoskeleton: Atk(10)]: Flick-Flack(8dmg)->Strike(power:-Strength) | dealt=8 taken=0

F20 [monster] Tunneler (6R, HP 58->45, loss=13, WIN)
  R1[Tunneler: Atk(13)]: Envenom(power:+Envenom(1))->Noxious Fumes(power:+Noxious Fumes(2))->Neutralize(5dmg,2+Poison(1),+Weak(1))->Dash(12dmg,+10blk,1Poison(1→2))->Strike(8dmg,1Poison(2→3))->Survivor(+8blk) | dealt=25 taken=0
  R2[Tunneler: Buff, Defend]: Expose(1+Vulnerable(2),exhaust:1)->Strike(12dmg,1Poison(4→5))->Strike(12dmg,1Poison(5→6)) | dealt=24 taken=0
  R3[Tunneler: Atk(23)]: Leg Sweep(+11blk,1+Weak(2))->Defend(+5blk) | dealt=0 taken=1
  R4[Tunneler: Atk(17)]: Dagger Throw->Defend(+5blk)->Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv*2 | dealt=0 taken=12
  R5[Tunneler: Atk(23)]: Strike(1-Burrowed)->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R6[Tunneler: Atk(13)]: Strike(8dmg,1Poison(10→11))->Flick-Flack(power:-Strength,power:-Envenom,power:-Noxious Fumes) | dealt=8 taken=0

F21 [monster] Ovicopter (8R, HP 45->31, loss=14, WIN)
  R1[Ovicopter: Summon]: Envenom(power:+Envenom(1))->Neutralize(5dmg,2+Poison(1),+Weak(1))->Strike(8dmg,1Poison(1→2))->Strike(8dmg,1Poison(2→3)) | dealt=21 taken=0
  R2[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(16)]: Leg Sweep(+11blk,1+Weak(2))->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=0 taken=1
  R3[Hatchling: Atk(4)+Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(5), Debuff]: Dash(+10blk)->Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv->Shiv(6dmg,1Poison(3→4)) | dealt=6 taken=3
  R4[Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Summon]: Expose(1+Vulnerable(2),exhaust:1)->Survivor(+8blk)->Flick-Flack(20dmg,+5blk,1Poison(3→4),1Poison(5→6))->Defend(16dmg,1Poison(6→7))->Dagger Throw | dealt=36 taken=0
  R5[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Atk(24)]: Dash(+10blk)->Strike(2+Hatch(1),Poison(5→2)) | dealt=0 taken=8
  R6[Hatchling: Atk(4)+Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(5), Debuff]: Leading Strike->Shiv*2->Neutralize->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=2
  R7[Hatchling: Atk(6)+Hatchling: Atk(6)+Ovicopter: Summon]: Dagger Throw(11dmg,1Poison(3→4))->Leading Strike->Shiv->Neutralize(5dmg,2Poison(4→5),+Weak(1))->Shiv(6dmg,1Poison(10→11))->Defend(+5blk) | dealt=11 taken=0
  R8[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(24)]: Survivor(+8blk)->Flick-Flack(24dmg,1Poison(2→3),1Poison(12→14))->Strike(8dmg,1Poison(14→15))->Strike | dealt=32 taken=0

F23 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (1R, HP 31->31, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Defend(+5blk)->Fan of Knives(power:+Fan of Knives(1))->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg)->Flick-Flack(power:-Strength,power:-Fan of Knives) | dealt=24 taken=0

F24 [monster] Louse Progenitor (6R, HP 31->18, loss=13, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Blade Dance(exhaust:1)->Shiv(6dmg,1-Curl Up,exhaust:1)->Expose(1+Vulnerable(2),exhaust:1)->Shiv(9dmg)->Shiv(9dmg)->Strike(12dmg)->Survivor(+8blk)->Flick-Flack(12dmg,+5blk)->Defend | dealt=48 taken=0
  R2[Louse Progenitor: Defend, Buff]: Envenom(power:+Envenom(1))->Leading Strike(7dmg,1+Poison(1))->Shiv(9dmg,1Poison(1→2))->Shiv(9dmg,1Poison(2→3)) | dealt=25 taken=0
  R3[Louse Progenitor: Atk(19)]: Dagger Throw->Dash(5dmg,+7blk,1Poison(2→3)) | dealt=5 taken=12
  R4[Louse Progenitor: Atk(14), Debuff]: Piercing Wail+(2Strength(5→-3),+Piercing Wail(8),exhaust:1)->Defend(+5blk)->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=0 taken=1
  R5[Louse Progenitor: Defend, Buff]: Neutralize(5dmg,2Poison(3→4),+Weak(1))->Piercing Wail+(2Strength(5→-3),+Piercing Wail(8))->Ricochet(20dmg,1Poison(4→8)) | dealt=25 taken=0
  R6[Louse Progenitor: Atk(24)]: Strike->Dash(12dmg,+7blk,1Poison(9→10)) | dealt=12 taken=0

F28 [elite] Infested Prism (6R, HP 39->32, loss=7, WIN)
  R1[Infested Prism: Atk(22)]: Envenom+(power:+Envenom(2))->Neutralize(5dmg,+1energy,2+Poison(2),+Weak(1))->Defend(+5blk)->Defend(+5blk)->Defend(+5blk)->Strike(8dmg,1Poison(2→4))->Expertise+->Blade Dance(exhaust:1)->Shiv(6dmg,1Poison(4→6),exhaust:1)->Shiv(6dmg,1Poison(6→8))->Shiv(6dmg,1Poison(8→10)) | dealt=31 taken=1
  R2[Infested Prism: Atk(16), Defend]: Strike(8dmg,1Poison(9→11))->Noxious Fumes(power:+Noxious Fumes(2))->Piercing Wail+(2+Strength(-8),+Piercing Wail(8),exhaust:1)->Piercing Wail+(2Strength(-8→-16),Piercing Wail(8→16)) | dealt=8 taken=0
  R3[Infested Prism: Atk(9x3=27)]: Expose(1+Vulnerable(2),exhaust:1)->Ricochet(28dmg,+1energy,1Poison(12→20))->Leg Sweep(+11blk,1+Weak(2))->Defend(+5blk) | dealt=28 taken=2
  R4[Infested Prism: Buff, Defend]: Strike(12dmg,1Poison(21→23))->Strike(12dmg,1Poison(23→25))->Leg Sweep(+11blk,1Weak(1→3)) | dealt=24 taken=0
  R5[Infested Prism: Atk(19)]: Neutralize(1Weak(2→3))->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=4
  R6[Infested Prism: Atk(15), Defend]: Leading Strike(5dmg,1Poison(27→29))->Shiv(6dmg,1Poison(29→31))->Shiv(6dmg,1Poison(31→33))->Ricochet(power:-Strength,power:-Envenom,power:-Noxious Fumes) | dealt=17 taken=0

F30 [elite] Entomancer (5R, HP 53->40, loss=13, WIN)
  R1[Entomancer: Atk(3x7=21)]: Piercing Wail+(2+Strength(-16),+Piercing Wail(16),exhaust:1)->Expose(1+Vulnerable(2),exhaust:1)->Survivor(+8blk)->Dagger Throw(16dmg)->Expertise+->Leg Sweep(+11blk,1+Weak(2))->Blade Dance(exhaust:1)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Neutralize(7dmg,1Weak(2→3))->Shiv(9dmg) | dealt=34 taken=0
  R2[Entomancer: Atk(13)]: Strike(12dmg)->Strike(12dmg) | dealt=24 taken=13
  R3[Entomancer: Buff]: Envenom+(power:+Envenom(2))->Deflect(+4blk)->Leading Strike(5dmg,1+Poison(2))->Shiv(6dmg,1Poison(2→4))->Shiv(6dmg,1Poison(4→6)) | dealt=17 taken=0
  R4[Entomancer: Atk(4x7=28)]: Piercing Wail+(2Strength(1→-7),+Piercing Wail(8))->Noxious Fumes(power:+Noxious Fumes(2))->Defend(+5blk) | dealt=0 taken=0
  R5[Entomancer: Atk(19)]: Blade Dance->Shiv(6dmg,1Poison(6→8))->Shiv(6dmg,1Poison(8→10))->Shiv(6dmg,1Poison(10→12))->Ricochet(20dmg,1Poison(12→20)) | dealt=38 taken=0

F31 [monster] Spiny Toad (4R, HP 47->46, loss=1, WIN)
  R1[Spiny Toad: Buff]: Phantom Blades(power:+Phantom Blades(9))->Dagger Throw(11dmg)->Flick-Flack(5dmg,1+Weak(2))->Neutralize(12dmg,+10blk)->Dash(8dmg)->Strike(+4blk)->Deflect | dealt=25 taken=0
  R2[Spiny Toad: Atk(17)]: Expose(1+Vulnerable(2),exhaust:1)->Leg Sweep(+11blk,1Weak(1→3))->Defend(+5blk) | dealt=0 taken=1
  R3[Spiny Toad: Atk(12)]: Defend(+5blk)->Blade Dance(exhaust:1)->Blade Dance->Shiv(22dmg,exhaust:1)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg)->Shiv(9dmg) | dealt=67 taken=0
  R4[Spiny Toad: Buff]: Leading Strike(5dmg)->Shiv(power:-Strength,power:-Phantom Blades) | dealt=5 taken=0

F33 [boss] multi:Crusher+Rocket (9R, HP 69->0, loss=69, LOSS)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Footwork(power:+Dexterity(2))->Noxious Fumes(power:+Noxious Fumes(2))->Piercing Wail+(2+Strength(-16),+Piercing Wail(16),2+Strength(-16),+Piercing Wail(16),exhaust:1)->Expose(1+Vulnerable(2),exhaust:1)->Blade Dance(exhaust:1)->Ricochet(24dmg)->Shiv(9dmg,exhaust:1)->Shiv(9dmg)->Strike(12dmg)->Shiv(9dmg) | dealt=63 taken=0
  R2[Crusher: Atk(4)+Rocket: Atk(27)]: Phantom Blades(power:+Phantom Blades(9))->Blade Dance->Strike(8dmg)->Shiv(15dmg)->Shiv(6dmg)->Shiv(6dmg) | dealt=35 taken=24
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Dagger Throw(11dmg)->Flick-Flack(12dmg,+12blk)->Dash | dealt=12 taken=0
  R4[Crusher: Buff+Rocket: Atk(49)]: Neutralize(3dmg,1+Weak(1))->Survivor(+7blk)->Expertise+->Piercing Wail+(2+Strength(-8),+Piercing Wail(8),2Strength(2→-6),+Piercing Wail(8))->Deflect(+4blk) | dealt=3 taken=7
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike(6dmg)->Flick-Flack(12dmg) | dealt=21 taken=5
  R6[Crusher: Atk(14)+Rocket: Atk(7)]: Dagger Throw->Defend(+7blk)->Survivor(+10blk) | dealt=0 taken=4
  R7[Crusher: Atk(6)+Rocket: Atk(30)]: Dash(12dmg,+12blk)->Defend(+7blk) | dealt=12 taken=10
  R8[Crusher: Atk(12x2=24), Debuff+Rocket: Buff]: Flick-Flack(16dmg)->Strike(2Strength(2→8),-Crab Rage)->Defend(+7blk) | dealt=17 taken=0
  R9[Rocket: Atk(41)]: Strike(8dmg)->Deflect(+6blk)->Strike(8dmg)->Survivor(+10blk) | dealt=16 taken=0

### Non-combat Decisions (131 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Booming Conch provides massive turn 1 consistency during critical Elite fights. Combined with Ring of the Snake, this allows us to see 9 cards on turn 1, almost guaranteeing a good setup. Past experience also shows this as the most successful choice.
  strategic_note: Foundation: Need to add frontloaded damage to survive Act 1 hallways and Elites. Booming Conch gives an incredible turn 1 advantage against Elites.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=2) | source=llm
  HP 56->56 | Gold 99->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Starting with a monster node to acquire cards and gold as per the early deck building strategy. Column 4 (c4,r1) is the recommended path and allows for a late Elite fight, which synergizes well with the Booming Conch relic while keeping early-game risk low.
  strategic_note: Foundation: prioritizing frontloaded damage and block cards in early monster fights to stabilize for the late-act Elite and Boss; Booming Conch makes late Elites safer if we have high-impact cards to draw turn 1.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 99->110 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 110->110 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 46->46 | Gold 110->110 | Deck 13->14
  deck_change: picked Flick-Flack
  reasoning: Flick-Flack provides early AoE damage which is crucial for Act 1 hallway fights and Slime Boss, and its Sly mechanic combos perfectly with our starting Survivor for high-value early turns (8 block and 6 AoE damage for 1 energy).
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F2 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 110->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Taking a monster fight on Floor 2 is superior to an early shop with only 110 gold. Silent needs to find frontloaded damage cards (like Dagger Throw or Poisoned Stab) early to prepare for the first Elite, and 110 gold is insufficient to guarantee a significant power spike from a shop. I will follow the 'Early Deck Building' strategy of taking monster nodes to see card rewards and accumulate more gold before visiting a shop later.
  strategic_note: Foundation: prioritizing monster fights floors 1-3 to find essential frontloaded damage for Act 1 Elites; Booming Conch makes early Elites safer once damage is found.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 110->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 117->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 117->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 40->40 | Gold 117->117 | Deck 14->15
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides solid frontloaded damage and a crucial discard outlet. This directly enables Flick-Flack (Sly) to be played for free while cycling our deck, providing a great early power spike for Act 1.
  strategic_note: Foundation plan: taking early damage and discard enablers like Dagger Throw to leverage Flick-Flack for frontload. Focus on elite hunting with Booming Conch; look for more damage, draw, and discard synergies to build a solid core.

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 117->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 117->132 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 132->132 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 132->132 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 40->40 | Gold 132->132 | Deck 15->16
  deck_change: picked Leading Strike
  reasoning: Leading Strike provides 11 total damage for 1 energy across 3 hits, which significantly boosts early-game damage output and serves as an excellent foundation for future Shiv or multi-hit synergies.
  strategic_note: Foundation plan: survive with frontload damage like Leading Strike while looking for a core scaling engine, possibly in Shivs. Prioritize strong attacks for early elites, then look for draw and energy.

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 132->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 132->144 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 144->144 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 38->38 | Gold 144->144 | Deck 16->17
  deck_change: picked Expose
  reasoning: Expose provides excellent 0-cost utility by stripping Artifact/Block and applying Vulnerable. It exhausts, so it won't clog the deck, and dramatically increases our single-target burst damage against Elites and Bosses, complementing our physical attacks and Shivs.
  strategic_note: Foundation plan: survive with frontload damage while looking for a core scaling engine, using Expose to burst priority targets. Prioritize heavy damage, efficient block, or a definitive synergy piece.

F5 [map] choose_map_node (option_index=2) | source=llm
  HP 38->38 | Gold 144->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Continuing the recommended route to find essential frontloaded damage. At 38 HP, I can safely take another hallway fight to improve the deck's card quality before the path moves towards the first Rest Site and Elite.
  strategic_note: Foundation: prioritizing monster fights to find essential frontloaded damage for Act 1 Elites; Booming Conch makes the planned late Elite significantly safer once damage is found.

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 144->154 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 30->30 | Gold 154->154 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 30->30 | Gold 154->154 | Deck 17->18
  deck_change: picked Noxious Fumes
  reasoning: Noxious Fumes provides the necessary multiplicative scaling for boss and elite fights. This transitions the deck from Foundation to a committed Poison/Defensive stalling engine.
  strategic_note: Committed poison plan: prioritize efficient block, Dexterity, and survivability while Noxious Fumes scales and kills. Need more block and draw; skip generic attacks.

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 154->154 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Unknown

F7 [event] choose_event_option (option_index=1) | source=llm
  HP 30->30 | Gold 154->13 | Deck 18->18
  deck_change: no deck change
  reasoning: Paying 141 gold for a random relic is a solid conversion of gold to immediate power, especially since a shop is still 8 floors away and I might not accumulate enough gold to buy a premium relic there anyway. Removing 2 cards for a curse that costs 1 energy to exhaust slows down early turns, which is risky right now.
  strategic_note: Foundation: Need to survive Act 1. Searching for good frontloaded damage or block to complement Noxious Fumes. Avoid slow setups.

F7 [event] choose_event_option (option_index=0) | source=auto
  HP 30->30 | Gold 13->13 | Deck 18->18
  deck_change: no deck change
  reasoning: Only option: Proceed

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 13->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Unknown

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 16->16 | Gold 13->23 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F8 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 16->16 | Gold 23->23 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 16->16 | Gold 23->23 | Deck 18->19
  deck_change: picked Blade Dance
  reasoning: Blade Dance provides 12 damage for 1 energy (3 Shivs) which is excellent frontload to help survive early fights. Additionally, playing Blade Dance and its 3 Shivs triggers Exhaust 4 times, which heavily fuels our Joss Paper relic for card draw.
  strategic_note: Foundation plan: surviving early fights. We have Noxious Fumes for scaling and Blade Dance for frontload/Joss Paper draw. Prioritize campfires for healing due to low HP, and look for efficient block and further Shiv synergies.

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 16->16 | Gold 23->23 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: RestSite

F9 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 16->37 | Gold 23->23 | Deck 19->19
  deck_change: no deck change
  reasoning: At 16 HP, we are in lethal range for standard Act 1 hallway fights. Healing to 37 HP is mandatory to survive the upcoming F12 and F14 monster encounters.
  strategic_note: Foundation: Deck relies on Noxious Fumes and physical damage like Shivs to clear Act 1. Needs better block density and a way to mitigate damage while poison ticks. Avoid bloated attacks.

F9 [rest_site] proceed | source=auto
  HP 37->37 | Gold 23->23 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=llm
  HP 37->37 | Gold 23->23 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the established route to collect a Treasure relic before the mandatory Rest Site and Elite fight. HP is currently at a manageable 53%, allowing for potential smithing if the chest provides a defensive boost.
  strategic_note: Foundation: Noxious Fumes provides scaling, but immediate frontloaded damage is required for the upcoming Elite; Booming Conch provides a crucial turn 1 advantage. Target high-impact attacks and efficient block in card rewards. Use the upcoming Rest Sites to Smith if HP remains stable, otherwise heal to survive the Elite.

F10 [treasure] open_chest | source=random
  HP 37->37 | Gold 23->61 | Deck 19->19
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 37->37 | Gold 61->61 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim: Girya

F10 [treasure] proceed | source=random
  HP 37->37 | Gold 61->61 | Deck 19->19
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 61->61 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: RestSite

F11 [rest_site] choose_rest_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 37->37 | Gold 61->61 | Deck 19->19
  deck_change: no deck change
  reasoning: We have Girya and multiple Shiv generators (Blade Dance, Leading Strike), meaning Strength significantly boosts our damage output. 37 HP is enough to take on an Act 1 Elite, and we have another rest site immediately after the Elite if we need to heal. Training now gives us the burst damage needed to quickly kill Gremlin Nob or Sentries.
  strategic_note: Foundation: Deck relies on Noxious Fumes for slow fights and Shivs boosted by Strength for burst damage. Play Expose before Shivs to maximize burst. Needs better block density and a way to mitigate damage while poison ticks. Avoid bloated slow attacks.

F11 [rest_site] proceed | source=auto
  HP 37->37 | Gold 61->61 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=1) | source=llm
  HP 37->37 | Gold 61->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Choosing the Elite fight to leverage the Booming Conch relic which provides extra draw at the start of Elite combats. Although HP is at 37, there is a Rest Site immediately following this node to recover if the fight is difficult. Skipping Elites in Act 1 often leads to being underpowered for the boss.
  strategic_note: Foundation: Utilizing Noxious Fumes for scaling while seeking high-impact frontloaded damage and block cards to survive Act 1 elites. Prioritizing Elite fights when a campfire is available immediately afterward to safely secure relics and rare card rewards.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 61->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim relic: Potion Belt

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Deck currently only has two discard outlets (Dagger Throw, Survivor), so adding a second Sly card (Ricochet) risks clogging our hand. Memento Mori doesn't have enough discard support. Snakebite splits focus from our Shiv/hybrid setup. Skipping keeps the deck lean for drawing our actual scaling cards like Noxious Fumes and Blade Dance.
  strategic_note: Foundation plan: Use Shivs and Noxious Fumes to scale damage while keeping the deck thin. Looking for a core scaling piece (like Accuracy or stronger poison synergies) and more consistent draw/mitigation. Avoid adding more disjointed synergy cards without enablers.

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: RestSite

F13 [rest_site] choose_rest_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Training Girya for +1 Strength scales perfectly with our multi-hit and Shiv-generating attacks (Blade Dance, Leading Strike, Flick-Flack), providing more overall damage across the deck than a single card upgrade. We have 37 HP and another Rest Site at F16, so we can survive F14 and heal before the boss if necessary.
  strategic_note: Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Play Expose before Shivs to maximize burst. Needs better block density, card draw, and a way to mitigate damage while poison ticks. Avoid bloated slow attacks.

F13 [rest_site] proceed | source=auto
  HP 37->37 | Gold 91->91 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 91->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 91->106 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 106->106 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 35->35 | Gold 106->106 | Deck 19->20
  deck_change: picked Dash
  reasoning: Our deck currently lacks efficient defense. Dash provides a great compression of block and damage, which will be essential for stabilizing in the upcoming Act 1 boss fight and surviving Act 2 hallway fights. Our current scaling relies on Noxious Fumes and Shivs; Dash helps buy time for these to work.
  strategic_note: Foundation plan: survive with frontload and efficient block. With Blade Dance and Joss Paper (draw on exhaust), we are leaning heavily towards a Shiv engine. Need more Shiv generators and payoffs (like Finisher or Accuracy). Avoid adding more narrow poison cards.

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 35->35 | Gold 106->106 | Deck 20->20
  deck_change: no deck change
  reasoning: The route recommends a Shop, and I have 106 gold which is enough for a key common card, a cheap relic, or a card removal. My HP is at 50%, and following the shop with a Rest Site will prepare me for the Act 1 Boss. Taking an Elite at floor 14 with 35 HP is too risky for the Silent without more front-loaded damage.
  strategic_note: Foundation: Focusing on survival and basic deck thinning. Noxious Fumes provides scaling, but the immediate priority is finding efficient block and front-loaded damage cards while using shops to remove basic Strikes.

F15 [shop] buy_card (option_index=2) | source=plan
  HP 35->35 | Gold 106->33 | Deck 20->21
  deck_change: bought Leg Sweep
  reasoning: Shop plan [1/1]: Premium mitigation for the upcoming Act 1 boss fight, applying Weak and heavy block. This gives us much more survivability than removing a single Strike.

F15 [shop] close_shop_inventory | source=plan
  HP 35->35 | Gold 33->33 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F15 [shop] proceed | source=auto
  HP 35->35 | Gold 33->33 | Deck 21->21
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 35->35 | Gold 33->33 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 35->56 | Gold 33->33 | Deck 21->21
  deck_change: no deck change
  reasoning: With 35/70 HP (50%) and the Act 1 Boss next, healing 21 HP is necessary to ensure survival. While Training for more Strength or upgrading Noxious Fumes would be nice, dying to the boss because I lacked the HP buffer is the main risk here.
  strategic_note: Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Play Expose before Shivs to maximize burst. Prioritize finding better card draw and consistent block to survive while poison scales.

F16 [rest_site] proceed | source=auto
  HP 56->56 | Gold 33->33 | Deck 21->21
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 33->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 11->11 | Gold 33->108 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 11->11 | Gold 108->108 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Weak Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 11->11 | Gold 108->108 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 11->11 | Gold 108->108 | Deck 21->22
  deck_change: picked Envenom
  reasoning: We are transitioning into a Shiv-Poison engine. Envenom serves as our core scaling mechanic by turning our Shiv generators (Blade Dance, Leading Strike) into reliable poison application. Accelerant is a payoff that needs an engine first, and Shadow Step is too clunky for our current draw situation.
  strategic_note: Committed to a shiv-poison hybrid engine. Envenom turns shivs into lethal scaling. Focus on surviving early turns to play Envenom, then spam shivs while blocking. Need more draw, cheap block, and a few more shiv generators. Avoid expensive attacks.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 11->58 | Gold 108->108 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0) | source=llm
  HP 58->58 | Gold 108->108 | Deck 22->22
  deck_change: no deck change
  reasoning: Very Hot Cocoa offers 4 extra energy on turn 1. Combined with our Ring of the Snake (draw 2 additional cards turn 1), this lets us play our entire opening hand, easily deploying expensive powers like Envenom and setting up our scaling immediately without sacrificing block.
  strategic_note: Foundation: Deck relies on Noxious Fumes and Envenom with Shivs for scaling damage. Very Hot Cocoa provides explosive turn 1 energy, so prioritize aggressive turn 1 deployments of powers and defensive scaling. Seek more card draw to fully utilize the initial energy burst and prioritize removing Strikes.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 58->58 | Gold 108->108 | Deck 22->22
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 58->58 | Gold 108->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Pathing toward the right side of the map to align with the recommended route. This path leads to a high frequency of rest sites (4 total) and two elites, which maximizes our chances of using the Booming Conch relic while providing safety for Act 2 scaling.
  strategic_note: Foundation: Relying on Noxious Fumes for scaling while prioritizing block and efficient front-loaded damage. The goal is to thin the deck at shops and use the high number of rest sites to upgrade defensive cards, ensuring we survive long enough for poison to tick down Act 2's high-damage threats.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 108->123 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 123->123 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 58->58 | Gold 123->123 | Deck 22->22
  deck_change: no deck change
  reasoning: Hidden Daggers causes massive card disadvantage which we cannot afford without better draw engines (like Acrobatics). Slice+ is minor chip damage. Expose+ is redundant since we already have an Expose. Skipping to keep the deck focused on finding draw and heavier scaling for our 7 energy Turn 1s.
  strategic_note: Foundation plan: survive using Envenom/Fumes while digging for card draw. With 7 energy on turn 1 from Cocoa, prioritize premium draw (Acrobatics, Backflip) and high-impact expensive cards over cheap/free cards that empty the hand.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 123->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 123->137 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 137->137 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Power Potion

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 137->137 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 45->45 | Gold 137->137 | Deck 22->22
  deck_change: no deck change
  reasoning: Our deck has a clear Poison/Shiv hybrid engine forming with Envenom, Noxious Fumes, and Blade Dance. None of the offered cards strongly support this: Reflex lacks enough discard enablers (only 2 in deck), Snakebite is too energy-intensive, and Deflect is too low-impact. Skipping to keep the deck consistent.
  strategic_note: Committed to Envenom/Fumes poison engine supported by Shivs and defensive stalling. Focus on upgrading key pieces, finding efficient block, and acquiring more Shiv generation or passive defense. Avoid bloating with cards that don't directly feed the engine.

F20 [map] choose_map_node (option_index=1) | source=llm
  HP 45->45 | Gold 137->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Following the recommended path to reach the Shop with more gold. 45 HP is sufficient to handle a hallway fight, and the gold from this combat will likely enable a more impactful purchase at the upcoming floor 21 shop.
  strategic_note: Foundation: Deck uses Noxious Fumes for slow fights and Shivs boosted by Girya Strength for burst damage. Use Expose before Shivs to maximize damage, and prioritize defensive play while Noxious Fumes scales in longer encounters.

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 137->144 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 144->144 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 31->31 | Gold 144->144 | Deck 22->23
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is an incredibly powerful defensive tool that shines against multi-attacks (like Book of Stabbing or Birds) and multiple enemies (like Slavers or Gremlin Leader), which are very common in Act 2. Since we are at 31 HP and need strong mitigation to survive, taking an upgraded Piercing Wail is highly valuable.
  strategic_note: Committed poison/shiv hybrid plan: Use Envenom with shiv generators and Noxious Fumes for scaling damage, while surviving with efficient block and Piercing Wail. Look for upgraded draw/discard outlets, and focus on upgrading key cards.

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 31->31 | Gold 144->144 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Shop

F22 [shop] buy_card (option_index=2) | source=plan
  HP 31->31 | Gold 144->92 | Deck 23->24
  deck_change: bought Blade Dance
  reasoning: Shop plan [1/2]: Directly fuels our Envenom scaling engine. 3 Shivs equals 3 hits, which translates to 12 damage and 3 extra poison for 1 energy.

F22 [shop] buy_card (option_index=1) | source=plan
  HP 31->31 | Gold 92->43 | Deck 24->25
  deck_change: bought Ricochet
  reasoning: Shop plan [2/2]: Another phenomenal Envenom trigger, providing 4 hits (4 poison). Its Sly mechanic pairs perfectly with our Dagger Throw and Survivor for 0-energy multi-hit damage.

F22 [shop] close_shop_inventory | source=plan
  HP 31->31 | Gold 43->43 | Deck 25->25
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F22 [shop] proceed | source=auto
  HP 31->31 | Gold 43->43 | Deck 25->25
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 31->31 | Gold 43->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [card_select] select_deck_card (option_index=0) | source=llm
  HP 31->31 | Gold 43->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Fan of Knives provides 4 immediate Shivs for burst damage to help kill Enemy 1, and makes all future Shivs hit all enemies, which is excellent since we have 2 Blade Dances in the deck and multiple enemies in this combat.
  strategic_note: Use Shivs and Envenom to stack poison and burst down enemies. Play defensively while powers scale.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 43->51 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 51->51 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 51->51 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 31->31 | Gold 51->51 | Deck 25->26
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is an incredibly strong defensive tool against Act 2 and Act 3 multi-attackers (Book of Stabbing, Slavers, Byrds, Reptomancer). Having a second upgraded copy provides crucial mitigation to survive heavy-hitting turns while our poison and shivs scale.
  strategic_note: Committed to Envenom/Shiv poison scaling with Noxious Fumes. Use Blade Dances to stack poison via Envenom while relying on strong block and Piercing Wails for mitigation. Prioritize finding more card draw and discard outlets.

F23 [map] choose_map_node (option_index=1) | source=llm
  HP 31->31 | Gold 51->0 | Deck 26->26
  deck_change: no deck change
  reasoning: HP is at 31 (44%), which is too low to risk an Elite fight (option 0) immediately. Pathing to the Unknown node leads toward a Rest Site and Treasure, providing opportunities to recover HP and upgrade cards before the late-Act Elite fights. The route intelligence suggests avoiding Elites with low HP.
  strategic_note: Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We need to stabilize HP via Rest Sites and avoid risky Elites until we have more sustain or higher burst potential.

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 18->18 | Gold 51->61 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 18->18 | Gold 61->61 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Touch of Insanity

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 18->18 | Gold 61->61 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F24 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 18->18 | Gold 61->61 | Deck 26->27
  deck_change: picked Expertise+
  reasoning: Expertise+ is an incredibly powerful draw card for this deck, especially because Very Hot Cocoa gives us 7 Energy on turn 1. We can easily dump our 7-card opening hand (from Ring of the Snake) and use Expertise+ to refill and continue playing cards with our surplus energy. It also synergizes perfectly with our Shiv generators (Blade Dance, Leading Strike) and 0-cost cards like Neutralize and Expose.
  strategic_note: Committed to Shiv/Poison hybrid via Envenom. Use Turn 1 surplus energy (Very Hot Cocoa) and draw (Expertise+) to rapidly deploy powers (Envenom, Fumes) and cycle through early attacks. Keep looking for multi-hit scaling and block solutions; remove basic Strikes/Defends.

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 18->18 | Gold 61->61 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: RestSite

F25 [rest_site] choose_rest_option (option_index=1, smith_card_index=20, note_scope=run, note_triggers=all) | source=llm
  HP 18->18 | Gold 61->61 | Deck 27->27
  deck_change: upgraded Envenom->Envenom+
  reasoning: Since there are no combats before the next rest site (F26 is a Treasure, F27 is a Rest Site), I can safely skip healing here and Smith instead. Envenom+ doubles the poison applied by every unblocked attack, which turns our Shivs into massive scaling damage for Elites and Bosses. I will heal at F27 before fighting the F28 Elite.
  strategic_note: Committed poison/shiv hybrid: use Very Hot Cocoa to play Envenom/Noxious Fumes early, then burst with Shivs (buffed by Girya Strength) to stack poison rapidly. Block and survive while poison scales.

F25 [rest_site] proceed | source=auto
  HP 18->18 | Gold 61->61 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 18->18 | Gold 61->61 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 18->18 | Gold 61->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 18->18 | Gold 94->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim: White Beast Statue

F26 [treasure] proceed | source=random
  HP 18->18 | Gold 94->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=auto
  HP 18->18 | Gold 94->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: RestSite

F27 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 18->39 | Gold 94->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Facing an Act 2 Elite next floor with only 18 HP is highly lethal. High burst fights like Slavers or Book of Stabbing can easily deal over 18 damage on turn 1 or 2. Healing to 39 HP is absolutely required to survive the elite encounter.
  strategic_note: Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We need to stabilize HP via Rest Sites and avoid risky Elites until we have more sustain or higher burst potential. Need more card draw to utilize Very Hot Cocoa.

F27 [rest_site] proceed | source=auto
  HP 39->39 | Gold 94->94 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 94->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Elite

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 94->123 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 29 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 123->123 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Fortifier

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 123->123 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim relic: Unsettling Lamp

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 123->123 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 32->32 | Gold 123->123 | Deck 27->28
  deck_change: picked Deflect
  reasoning: Deflect is a 0-cost block card. Since our deck relies on expensive setup cards like Envenom+ and Leg Sweep, having free mitigation allows us to survive while deploying our powers. 0-cost cards also synergize well with Expertise+ for hand cycling.
  strategic_note: Committed poison/shiv plan: stack poison via Envenom and Shivs, let Noxious Fumes scale passively, and survive with Weak/efficient block. Needs focus on defense and card draw; avoid bloated damage cards.

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 32->32 | Gold 123->123 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: RestSite

F29 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 32->53 | Gold 123->123 | Deck 28->28
  deck_change: no deck change
  reasoning: Facing an Act 2 Elite next with only 32 HP (46%) is highly risky, especially against high-burst enemies like Slavers or Gremlin Leader. Resting gives us the buffer needed to survive the Elite fight, and we can still Smith or Train at the final Rest Site before the Boss.
  strategic_note: Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. We rely on explosive turn 1 energy from Very Hot Cocoa to setup Envenom/Fumes or play early defensive scaling.

F29 [rest_site] proceed | source=auto
  HP 53->53 | Gold 123->123 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 123->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Elite

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 123->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Liquid Bronze

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->47 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim relic: Strawberry

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 149->149 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 47->47 | Gold 149->149 | Deck 28->29
  deck_change: picked Phantom Blades
  reasoning: Phantom Blades is a core scaling card for Shivs. It provides +9 damage to the first Shiv each turn and adds Retain to all Shivs, giving us incredible flexibility. Since we rely heavily on Envenom+ for our win condition, Retain allows us to hold generated Shivs until we can safely play Envenom, maximizing our poison application without wasting attacks. It only costs 1 energy compared to Tracking's 2 energy, making it much easier to deploy in our 3-energy deck.
  strategic_note: Committed to Shiv/Poison hybrid: use Very Hot Cocoa to play Envenom/Phantom Blades turn 1, then spam retained Shivs to stack poison and trigger Joss Paper. Need draw/discard synergy and block scaling. Skip generic attacks.

F30 [map] choose_map_node (option_index=0) | source=auto
  HP 47->47 | Gold 149->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Monster

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 149->156 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 156->156 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim potion: Powdered Demise

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 156->156 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 46->46 | Gold 156->156 | Deck 29->30
  deck_change: picked Footwork
  reasoning: Footwork provides essential defensive scaling for our poison/shiv hybrid plan, allowing us to survive longer boss fights like Crusher/Rocket while Noxious Fumes and Envenom tick down their health.
  strategic_note: Committed poison/shiv plan: stack passive poison with Fumes and Envenom+Shivs, then defend heavily with Footwork, Piercing Wail, and block cards while poison finishes them.

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 156->156 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 46->69 | Gold 156->156 | Deck 30->30
  deck_change: no deck change
  reasoning: With 46/77 HP and the Act 2 Boss immediately next, healing provides a guaranteed 23 HP buffer. Since HP restores fully after the boss, surviving this fight is the only priority. 46 HP is risky against Act 2 boss burst turns, so taking the safe heal over an upgrade or Lift ensures we don't die to a bad draw.
  strategic_note: Foundation deck: stalling with Noxious Fumes and bursting with Girya-boosted Shivs. Use Piercing Wails and Leg Sweep to mitigate boss burst turns. Need to remove basic Strikes in Act 3 and find more card draw to cycle faster.

F32 [rest_site] proceed | source=auto
  HP 69->69 | Gold 156->156 | Deck 30->30
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 69->69 | Gold 156->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Boss

## Selected Replay Package (8 replays)
[Selected: run_combat] Nibbit (F2, monster)
Historical: loss=10 vs historical avg=1.1+/-1.8 (z=4.9, WORSE_THAN_USUAL, n=7)
## Combat Replay: vs Nibbit (Floor 2, monster)
Relics: Ring of the Snake, Booming Conch
Deck (13): Defend x5, Strike x5, Ascender's Bane, Neutralize, Survivor
Enemies: Nibbit HP=47/47

### Round 1
Agent plan (hypothesis): Nibbit attacks for 6 and blocks for 5 next turn.
Intent: Nibbit: Attack(12)
  Neutralize -> Nibbit[0]
    enemy_deltas: Nibbit: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Nibbit: Attack(6), Defend
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 3
Agent plan (hypothesis): Nibbit will do a heavy attack next turn, but we should draw our strikes to push damage.
Intent: Nibbit: Buff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Agent plan (hypothesis): Nibbit will have 5 HP next turn, easy kill.
Intent: Nibbit: Attack(14)
  Neutralize -> Nibbit[0]
    enemy_deltas: Nibbit: hp -3, +Weak(1)
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  turn_end

### Round 5
Agent plan (hypothesis): Combat ends.
Intent: Nibbit: Attack(8), Defend
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: DIED
## Combat Analytics: Nibbit (WIN - 5 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 6 dmg
  Defend "Gain 5 Block." -> 5 plays, 25 block
  Strike "Deal 6 damage." -> 7 plays, 36 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Nibbit (Floor 6, monster)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation
Deck (17): Defend x6, Strike x5, Ascender's Bane, Blade Dance, Neutralize, Peck, Skewer, Survivor
Enemies: Nibbit HP=44/44

### Round 1
Intent: Nibbit: Attack(12)
  Peck -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: hp -6
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Nibbit: Attack(6), Defend
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Nibbit[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Nibbit: hp -4
  Shiv -> Nibbit[0]
    enemy_deltas: Nibbit: hp -4
  Shiv -> Nibbit[0]
    enemy_deltas: Nibbit: hp -4
  turn_end

### Round 3
Intent: Nibbit: Buff
  Neutralize -> Nibbit[0]
    enemy_deltas: Nibbit: block -3, +Weak(1)
  Skewer -> Nibbit[0]
    energy -3 | enemy_deltas: Nibbit: hp -22, block -2
  turn_end

### Round 4
Intent: Nibbit: Attack(14)
  Strike -> Nibbit[0]
    energy -1 | enemy_deltas: Nibbit: DIED
## Combat Analytics: Nibbit (WIN - 4 rounds)

Cards played (with descriptions):
  Peck "Deal 2 damage 3 times." -> 1 plays, 6 dmg
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 3 plays, 12 dmg, EXHAUST
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays
  Skewer "Deal 8 damage X times." -> 1 plays, 22 dmg
  Strike "Deal 6 damage." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~12 dmg

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:- -> R4:2

[Selected: elite] Bygone Effigy (F12, elite)
## Combat Replay: vs Bygone Effigy (Floor 12, elite)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya
Deck (19): Defend x5, Strike x5, Ascender's Bane, Blade Dance, Dagger Throw, Expose, Flick-Flack, Leading Strike, Neutralize, Noxious Fumes, Survivor
Enemies: Bygone Effigy HP=132/132

### Round 1
Agent plan (hypothesis): Effigy should be nearly dead or dead. Next turn finish it off.
Agent plan (hypothesis): Play any 0-cost cards drawn by Dagger Throw, then end turn.
Intent: Bygone Effigy: Sleep
  Strength Potion
    Strength(1→3)
  Expose -> Bygone Effigy[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Bygone Effigy: +Vulnerable(2)
  Leading Strike -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -9
  Shiv -> Bygone Effigy[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bygone Effigy: hp -12
  Shiv -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -13
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -15
  Shiv -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -16
  Shiv -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -17
  Dagger Throw -> Bygone Effigy[0]
    energy -1 | enemy_deltas: Bygone Effigy: hp -32
  Defend
  turn_end

### Round 2
Agent plan (hypothesis): Enemy is almost dead, kill next turn.
Intent: Bygone Effigy: Buff
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Neutralize -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -9, +Weak(1)
  turn_end
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust.

### Round 3
Intent: Bygone Effigy: Attack(23)
  Neutralize -> Bygone Effigy[0]
    enemy_deltas: Bygone Effigy: hp -6, +Weak(1)
  Strike -> Bygone Effigy[0]
    energy -1 | -Strength | -Noxious Fumes | enemy_deltas: Bygone Effigy: DIED
## Combat Analytics: Bygone Effigy (WIN - 3 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 6 damage. Add 2 Shivs into your Hand." -> 1 plays, 9 dmg, generates 2 Shivs
  Shiv "Deal 7 damage. Exhaust." -> 5 plays, 73 dmg, EXHAUST
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Dagger Throw "Deal 12 damage. Draw 1 card. Discard 1 card." -> 1 plays, 32 dmg
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Neutralize "Deal 6 damage. Apply 1 Weak." -> 2 plays, 15 dmg
  Strike "Deal 9 damage." -> 1 plays

Active powers: Strength(1)

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~44 dmg
  Leading Strike: 2 Shivs -> ~29 dmg

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:2
  Slow: R1:1 -> R2:1 -> R3:1
  Strength: R1:- -> R2:- -> R3:10
  Vulnerable: R1:- -> R2:1 -> R3:-

[Selected: boss] multi:Kin Follower+Kin Follower+Kin Priest (F17, boss)
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt
Deck (21): Defend x5, Strike x5, Ascender's Bane, Blade Dance, Dagger Throw, Dash, Expose, Flick-Flack, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Survivor
Enemies: Kin Follower HP=63/63, Kin Follower HP=62/62, Kin Priest HP=199/199

### Round 1
Agent plan (hypothesis): Continue focusing the Priest. Noxious Fumes is skipped to maximize burst while Vulnerable is up.
Intent: Kin Follower: Buff, Kin Follower: Attack(5), Kin Priest: Attack(8), Debuff
  Expose -> Kin Priest[2]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Kin Priest: +Vulnerable(2)
  Leading Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -7
  Shiv -> Kin Priest[2]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Kin Priest: hp -9
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Dash -> Kin Priest[2]
    energy -2 | block +10 | enemy_deltas: Kin Priest: hp -18
  turn_end

### Round 2
Agent plan (hypothesis): Save Vulnerable potion for next turn when the Priest's vulnerability expires.
Intent: Kin Follower: Attack(7), Kin Follower: Attack(2x2=4), Kin Priest: Attack(8), Debuff
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Dagger Throw -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -16
  Flick-Flack
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12
  turn_end

### Round 3
Agent plan (hypothesis): Ascender's Bane is exhausted. Next turn, Priest and Follower 0 are buffing, so we have a massive offensive window. Use the Vulnerable Potion and go all out on damage against the Priest.
Intent: Kin Follower: Attack(4x2=8), Kin Follower: Buff, Kin Priest: Attack(3x3=9)
  Neutralize -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust.

### Round 4
Agent plan (hypothesis): The Priest is Vulnerable for 3 turns. Go all-in on damage next turn to finish him off before the massive multi-attacks.
Intent: Kin Follower: Buff, Kin Follower: Attack(7), Kin Priest: Buff
  Vulnerable Potion -> Kin Priest[2]
    enemy_deltas: Kin Priest: +Vulnerable(3)
  Dash -> Kin Priest[2]
    energy -2 | block +10 | enemy_deltas: Kin Priest: hp -18
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12
  turn_end

### Round 5
Agent plan (hypothesis): If Dagger Throw is drawn, use it to draw the final card in the pile. If not, prioritize Dash and Neutralize for max damage while Weakened.
Intent: Kin Follower: Attack(9), Kin Follower: Attack(4x2=8), Kin Priest: Attack(10), Debuff
  Survivor
    energy -1 | block +8
  Defend
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -12
  turn_end

### Round 6
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(10), Debuff
  Neutralize -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -7, +Weak(1)
  Leading Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -7
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -9
  Shiv -> Kin Priest[2]
    -Strength | -Frail | enemy_deltas: Kin Follower: DIED; Kin Priest: DIED
## Combat Analytics: multi:Kin Follower+Kin Follower+Kin Priest (WIN - 6 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 2 plays, 14 dmg, generates 2 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 7 plays, 54 dmg, EXHAUST
  Dash "Gain 10 Block. Deal 12 damage." -> 2 plays, 36 dmg, 20 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 1 plays, 16 dmg
  Strike "Deal 8 damage." -> 4 plays, 48 dmg
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 10 dmg
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block

Active powers: Strength(2)

Token attribution (Shivs):
  Leading Strike: 4 Shivs -> ~31 dmg
  Blade Dance: 3 Shivs -> ~23 dmg

Enemy power timeline:
  Minion[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Minion[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:2 -> R6:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Kin Follower+Kin Follower+Kin Priest (Floor 17, boss)
Relics: Ring of the Snake, Golden Pearl, War Paint, Stone Cracker
Deck (24): Strike x5, Defend x4, Ascender's Bane, Backflip, Blade Dance+, Dagger Spray, Dagger Throw, Defend+, Hand of Greed+, Leg Sweep, Neutralize+, Piercing Wail+, Ricochet, Spoils Map, Strangle, Survivor, Tools of the Trade+
Enemies: Kin Follower HP=58/58, Kin Follower HP=59/59, Kin Priest HP=190/190

### Round 1
Intent: Kin Follower: Buff, Kin Follower: Attack(5), Kin Priest: Attack(8), Debuff
  Strangle+ -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -10, +Strangle(3)
  Blade Dance+
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust. | enemy_deltas: Kin Priest: hp -3
  Shiv -> Kin Priest[2]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Kin Priest: hp -7
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -7
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -7
  Shiv -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -7
  Defend
    energy -1 | block +5 | enemy_deltas: Kin Priest: hp -3
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.

### Round 2
Intent: Kin Follower: Attack(7), Kin Follower: Attack(2x2=4), Kin Priest: Attack(8), Debuff
  Piercing Wail+
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Kin Follower: +Strength(-8), +Piercing Wail(8); Kin Priest: +Strength(-8), +Piercing Wail(8)
  Dagger Throw -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -9
  Ricochet
  Defend
    energy -1 | block +3
  turn_end

### Round 3
Intent: Kin Follower: Attack(4x2=8), Kin Follower: Buff, Kin Priest: Attack(3x3=9)
  Neutralize+ -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -3, +Weak(2)
  Defend
    energy -1 | block +5
  Dagger Spray
    energy -1 | enemy_deltas: Kin Follower: hp -6; Kin Priest: hp -6
  Strike -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -4
  turn_end

### Round 4
Intent: Kin Follower: Buff, Kin Follower: Attack(7), Kin Priest: Buff
  Tools of the Trade+
    +Tools of the Trade(1)
  Hand of Greed+ -> Kin Priest[2]
    energy -2 | enemy_deltas: Kin Priest: hp -25
  Backflip
    energy -1 | block +5
  turn_end
  Strike

### Round 5
Intent: Kin Follower: Attack(9), Kin Follower: Attack(4x2=8), Kin Priest: Attack(10), Debuff
  Neutralize+ -> Kin Priest[2]
    enemy_deltas: Kin Priest: hp -4, +Weak(2)
  Hand of Greed+ -> Kin Priest[2]
    energy -2 | enemy_deltas: Kin Priest: hp -25
  Defend
    energy -1 | block +5
  turn_end
  Ricochet

### Round 6
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(7), Debuff
  Dagger Throw -> Kin Priest[2]
    energy -1 | enemy_deltas: Kin Priest: hp -9
  Strike
  Defend
    energy -1 | block +3
  Defend
    energy -1 | block +3
  turn_end
  Strike

### Round 7
Intent: Kin Follower: Buff, Kin Follower: Attack(9), Kin Priest: Attack(5x3=15)
  Backflip
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  Defend
    energy -1 | block +5
  turn_end
  Ricochet

### Round 8
Intent: Kin Follower: Attack(11), Kin Follower: Attack(6x2=12), Kin Priest: Buff
  Neutralize+ -> Kin Follower[1]
    enemy_deltas: Kin Follower: hp -4, +Weak(2)
  Leg Sweep -> Kin Follower[0]
    energy -2 | block +11
  Defend
    energy -1 | block +5
  turn_end
  Strike

### Round 9
Intent: Kin Follower: Attack(6x2=12), Kin Follower: Buff, Kin Priest: Attack(12), Debuff
  Hand of Greed+ -> Kin Priest[2]
    energy -2 | enemy_deltas: Kin Priest: hp -25
  Defend
    energy -1 | block +5
  turn_end
## Combat Analytics: multi:Kin Follower+Kin Follower+Kin Priest (LOSS - 9 rounds)
Death cause: Died with HP=8, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 3 dmg, EXHAUST, generates 4 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 28 dmg, EXHAUST
  Defend "Gain 5 Block." -> 9 plays, 3 dmg, 39 block
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 18 dmg
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 3 plays, 11 dmg
  Dagger Spray "Deal 3 damage to ALL enemies twice." -> 1 plays, 12 dmg
  Strike "Deal 4 damage." -> 1 plays, 4 dmg
  Tools of the Trade+ "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Hand of Greed+ "Deal 25 damage. If Fatal, gain 25 Gold." -> 3 plays, 75 dmg
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 10 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block

Token attribution (Shivs):
  Blade Dance+: 4 Shivs -> ~28 dmg

Enemy power timeline:
  Minion[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Minion[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:4 -> R6:4 -> R7:4 -> R8:6 -> R9:6
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:4 -> R8:4 -> R9:4
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:-
  Weak[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  Weak[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1

[Selected: run_combat] Tunneler (F20, monster)
Historical: loss=13 vs historical avg=0.2+/-0.4 (z=32.0, WORSE_THAN_USUAL, n=5)
## Combat Replay: vs Tunneler (Floor 20, monster)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt, Very Hot Cocoa
Deck (22): Defend x5, Strike x5, Ascender's Bane, Blade Dance, Dagger Throw, Dash, Envenom, Expose, Flick-Flack, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Survivor
Enemies: Tunneler HP=92/92

### Round 1
Agent plan (hypothesis): Scaling powers are down. Next turn is a safe window (enemy buffs/defends).
Intent: Tunneler: Attack(13)
  Envenom
    energy -2 | +Envenom(1)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Neutralize -> Tunneler[0]
    enemy_deltas: Tunneler: hp -5, +Poison(1), +Weak(1)
  Dash -> Tunneler[0]
    energy -2 | block +10 | enemy_deltas: Tunneler: hp -12, Poison(1→2)
  Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: hp -8, Poison(2→3)
  Survivor
    energy -1 | block +8
  turn_end

### Round 2
Agent plan (hypothesis): Enemy attacks heavily next turn, prioritize drawing block or applying weak.
Intent: Tunneler: Buff, Defend
  Expose -> Tunneler[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Tunneler: +Vulnerable(2)
  Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: hp -12, Poison(4→5)
  Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: hp -12, Poison(5→6)
  turn_end

### Round 3
Agent plan (hypothesis): Continue blocking and letting poison chip away HP.
Intent: Tunneler: Attack(23)
  Leg Sweep -> Tunneler[0]
    energy -2 | block +11 | enemy_deltas: Tunneler: +Weak(2)
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust.

### Round 4
Agent plan (hypothesis): If we draw a block card, play it. Otherwise, minimize damage taken.
Agent plan (hypothesis): Enemy takes 10 poison damage next turn.
Intent: Tunneler: Attack(17)
  Dagger Throw -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: block -11
  Strike
  Defend
    energy -1 | block +5
  Blade Dance
    energy -1 | exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust.
  Shiv -> Tunneler[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Tunneler: block -6
  Shiv -> Tunneler[0]
    enemy_deltas: Tunneler: block -6
  Shiv -> Tunneler[0]
    enemy_deltas: Tunneler: block -6
  turn_end

### Round 5
Agent plan (hypothesis): If stunned, enemy skips its turn. It will take 11 poison damage on its turn.
Intent: Tunneler: Attack(23)
  Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: block -8, -Burrowed
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 6
Intent: Tunneler: Attack(13)
  Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: hp -8, Poison(10→11)
  Flick-Flack
    energy -1 | -Strength | -Envenom | -Noxious Fumes | enemy_deltas: Tunneler: DIED
## Combat Analytics: Tunneler (WIN - 6 rounds)

Cards played (with descriptions):
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 1 plays, 5 dmg, +1 poison
  Dash "Gain 10 Block. Deal 12 damage." -> 1 plays, 12 dmg, 10 block, +1 poison
  Strike "Deal 8 damage." -> 5 plays, 40 dmg, +4 poison
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 3 plays, EXHAUST
  Flick-Flack "Sly. Deal 8 damage to ALL enemies." -> 1 plays

Active powers: Strength(2)

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~0 dmg

Poison stacks applied per card:
  Strike: 4 stacks
  Neutralize: 1 stacks
  Dash: 1 stacks

Enemy power timeline:
  Burrowed: R1:- -> R2:- -> R3:1 -> R4:1 -> R5:1 -> R6:-
  Poison: R1:- -> R2:4 -> R3:7 -> R4:8 -> R5:9 -> R6:10
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Tunneler (Floor 20, monster)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood
Deck (22): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Dash+, Defend+, Expose, Flick-Flack, Injury, Leading Strike, Neutralize, Skewer+, Survivor+, Tracking, Well-Laid Plans+
Enemies: Tunneler HP=87/87

### Round 1
Intent: Tunneler: Attack(13)
  Neutralize -> Tunneler[0]
    enemy_deltas: Tunneler: hp -5, +Weak(1)
  Leading Strike -> Tunneler[0]
    energy -1 | enemy_deltas: Tunneler: hp -3
  Shiv -> Tunneler[0]
    block +4 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Tunneler: hp -4
  Shiv -> Tunneler[0]
    enemy_deltas: Tunneler: hp -4
  Backflip
    energy -1 | block +5
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  turn_end
  Skewer+
  Survivor+

### Round 2
Intent: Tunneler: Buff, Defend
  Expose -> Tunneler[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Tunneler: +Vulnerable(2)
  Skewer+ -> Tunneler[0]
    energy -3 | enemy_deltas: Tunneler: hp -48
  turn_end
  Tracking
  Dash+

### Round 3
Intent: Tunneler: Attack(23)
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Tunneler[0]
    enemy_deltas: Tunneler: block -6
  Shiv -> Tunneler[0]
    enemy_deltas: Tunneler: block -6
  Shiv -> Tunneler[0]
    block +4 | enemy_deltas: Tunneler: block -6
  Dash+ -> Tunneler[0]
    energy -2 | block +13 | enemy_deltas: Tunneler: hp -5, block -14, -Burrowed
  turn_end
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust.
  Strike+
  Tracking

### Round 4
Intent: Tunneler: Attack(13)
  Skewer+ -> Tunneler[0]
    energy -3 | -Well-Laid Plans | enemy_deltas: Tunneler: DIED
## Combat Analytics: Tunneler (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 1 plays, 5 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 3 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 5 plays, 8 dmg, 8 block, EXHAUST
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Skewer+ "Deal 11 damage X times." -> 2 plays, 48 dmg
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Dash+ "Gain 13 Block. Deal 13 damage." -> 1 plays, 5 dmg, 13 block

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~5 dmg
  Leading Strike: 2 Shivs -> ~3 dmg

Enemy power timeline:
  Burrowed: R1:- -> R2:- -> R3:1 -> R4:-
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:-

[Selected: run_combat] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (F23, monster)
Historical: loss=0 vs historical avg=8.0+/-6.7 (z=-1.2, BETTER_THAN_USUAL, n=6)
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (Floor 23, monster)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt, Very Hot Cocoa
Deck (25): Defend x5, Strike x5, Blade Dance x2, Ascender's Bane, Dagger Throw, Dash, Envenom, Expose, Flick-Flack, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Piercing Wail+, Ricochet, Survivor
Enemies: Exoskeleton HP=26/26, Exoskeleton HP=29/29, Exoskeleton HP=28/28, Exoskeleton HP=25/25

### Round 1
Agent plan (hypothesis): Fan of Knives is incredible with Strength and Shiv generators against multi-enemy fights.
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(8)
  Power Potion
  Fan of Knives
  Defend
    energy -1 | block +5
  Fan of Knives
    +Fan of Knives(1)
  Shiv
    exhausted: Shiv [0]: Deal 4 damage to ALL enemies. Exhaust. | enemy_deltas: Exoskeleton: hp -6
  Shiv
    enemy_deltas: Exoskeleton: hp -6
  Shiv
    enemy_deltas: Exoskeleton: hp -6
  Shiv
    enemy_deltas: Exoskeleton: hp -6
  Flick-Flack
    energy -1 | block -5 | -Strength | -Fan of Knives | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (WIN - 1 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 1 plays, 5 block
  Fan of Knives "Shivs now hit ALL enemies. Add 4 Shivs into your Hand." -> 1 plays, generates 4 Shivs
  Shiv "Deal 6 damage to ALL enemies. Exhaust." -> 4 plays, 24 dmg, EXHAUST
  Flick-Flack "Sly. Deal 8 damage to ALL enemies." -> 1 plays

Active powers: Strength(2)

Token attribution (Shivs):
  Fan of Knives: 4 Shivs -> ~24 dmg

Enemy power timeline:
  Hard to Kill[0]: R1:9
  Hard to Kill[1]: R1:9
  Hard to Kill[2]: R1:9
  Hard to Kill[3]: R1:9
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (Floor 25, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh
Deck (23): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor, Well-Laid Plans+
Enemies: Exoskeleton HP=24/24, Exoskeleton HP=26/26, Exoskeleton HP=25/25, Exoskeleton HP=28/28

### Round 1
Intent: Exoskeleton: Attack(1x3=3), Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(8)
  Neutralize+ -> Exoskeleton[1]
  Escape Plan
    block +3
  Leg Sweep -> Exoskeleton[3]
    energy -2 | block +11 | enemy_deltas: Exoskeleton: +Weak(2)
  Backflip
    energy -1 | block +5
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Exoskeleton: Attack(8), Exoskeleton: Buff, Exoskeleton: Attack(10), Exoskeleton: Buff
  Afterimage
    energy -1 | +Afterimage(1)
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Defend
    energy -1 | block +6
  turn_end
  Finisher
  Strike

### Round 3
Intent: Exoskeleton: Buff, Exoskeleton: Attack(10), Exoskeleton: Buff, Exoskeleton: Attack(10)
  Leading Strike -> Exoskeleton[1]
    energy -1 | block +1
  Shiv -> Exoskeleton[1]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Exoskeleton[1]
    block +1
  Leading Strike -> Exoskeleton[1]
    energy -1 | block +1
  Shiv -> Exoskeleton[1]
    block +1
  Shiv -> Exoskeleton[1]
    block +1
  Finisher -> Exoskeleton[2]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -3
  Strike -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -6
  turn_end
  Defend
  Survivor

### Round 4
Intent: Exoskeleton: Attack(10), Exoskeleton: Attack(12)
  Escape Plan
    block +1
  Strangle+ -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -9, +Strangle(3)
  Strike -> Exoskeleton[1]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -9
  Expose -> Exoskeleton[1]
    block +1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Exoskeleton: hp +23, Strength(4→2), -Strangle
  Defend
    energy -1 | block +6
  Finisher -> Exoskeleton[0]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -12
  turn_end
  Survivor
  Envenom+

### Round 5
Intent: Exoskeleton: Buff
  Leading Strike -> Exoskeleton[0]
    energy -1 | block +1 | enemy_deltas: Exoskeleton: hp -3
  Neutralize+ -> Exoskeleton[0]
    block +1 | enemy_deltas: Exoskeleton: hp -4, +Weak(2)
  Shiv -> Exoskeleton[0]
    block +1 | enemy_deltas: Exoskeleton: hp -4
  Shiv -> Exoskeleton[0]
    block -3 | -Afterimage | -Well-Laid Plans | enemy_deltas: Exoskeleton: DIED
## Combat Analytics: multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (WIN - 5 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg, 1 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 4 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Defend "Gain 5 Block." -> 2 plays, 12 block
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 3 dmg, 3 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 4 dmg, 5 block, EXHAUST
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 6 times)" -> 2 plays, 15 dmg, 2 block
  Strike "Deal 6 damage." -> 2 plays, 15 dmg, 2 block
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 9 dmg, 1 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~4 dmg

Enemy power timeline:
  Hard to Kill: R1:- -> R2:- -> R3:- -> R4:- -> R5:9
  Hard to Kill[0]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:-
  Hard to Kill[1]: R1:9 -> R2:9 -> R3:9 -> R4:9 -> R5:-
  Hard to Kill[2]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Hard to Kill[3]: R1:9 -> R2:9 -> R3:9 -> R4:- -> R5:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:-
  Strength[1]: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:-
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:- -> R5:-
  Weak[1]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-
  Weak[3]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-

[Selected: elite] Infested Prism (F28, elite)
Historical: loss=7 vs historical avg=3.0+/-2.2 (z=1.8, WORSE_THAN_USUAL, n=4)
## Combat Replay: vs Infested Prism (Floor 28, elite)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt, Very Hot Cocoa, White Beast Statue
Deck (27): Defend x5, Strike x5, Blade Dance x2, Piercing Wail+ x2, Ascender's Bane, Dagger Throw, Dash, Envenom+, Expertise+, Expose, Flick-Flack, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Ricochet, Survivor
Enemies: Infested Prism HP=215/215

### Round 1
Agent plan (hypothesis): If Ascender's Bane is drawn, use Dagger Throw to discard it.
Agent plan (hypothesis): Expect a cycle where we need to heavily block the upcoming multi-attack on turn 3.
Intent: Infested Prism: Attack(22)
  Envenom+
    energy -2 | +Envenom(2)
  Neutralize -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -5, +Poison(2), +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -8, Poison(2→4)
  Expertise+
    energy -1
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Infested Prism[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: hp -6, Poison(4→6)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Poison(6→8)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Poison(8→10)
  turn_end

### Round 2
Agent plan (hypothesis): Turn 3 will be a heavy multi-attack, be ready to block.
Intent: Infested Prism: Attack(16), Defend
  Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -8, Poison(9→11)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Piercing Wail+
    energy -1 | exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: +Strength(-8), +Piercing Wail(8)
  Piercing Wail+
    energy -1 | enemy_deltas: Infested Prism: Strength(-8→-16), Piercing Wail(8→16)
  turn_end

### Round 3
Agent plan (hypothesis): Enemy will be Weakened and heavily Poisoned. Next turn is their buff/defend turn.
Intent: Infested Prism: Attack(9x3=27)
  Touch of Insanity -> Infested Prism[0]
  Ricochet
  Expose -> Infested Prism[0]
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Infested Prism: block -16, +Vulnerable(2)
  Ricochet
    energy +1 | enemy_deltas: Infested Prism: hp -28, Poison(12→20)
  Leg Sweep -> Infested Prism[0]
    energy -2 | block +11 | enemy_deltas: Infested Prism: +Weak(2)
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.

### Round 4
Agent plan (hypothesis): Enemy gains Strength this turn and attacks hard next turn. It will be heavily weakened.
Intent: Infested Prism: Buff, Defend
  Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -12, Poison(21→23)
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -12, Poison(23→25)
  Leg Sweep -> Infested Prism[0]
    energy -2 | block +11 | enemy_deltas: Infested Prism: Weak(1→3)
  turn_end

### Round 5
Agent plan (hypothesis): Survive the multi-attack next cycle if it lives that long. Keep applying poison.
Intent: Infested Prism: Attack(19)
  Neutralize -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -5, Weak(2→3)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Infested Prism: Attack(15), Defend
  Leading Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -5, Poison(27→29)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Poison(29→31)
  Shiv -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, Poison(31→33)
  Ricochet
    -Strength | -Envenom | -Noxious Fumes | enemy_deltas: Infested Prism: DIED
## Combat Analytics: Infested Prism (WIN - 6 rounds)

Cards played (with descriptions):
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 2 plays, 5 dmg, +2 poison
  Defend "Gain 5 Block." -> 7 plays, 35 block
  Strike "Deal 8 damage." -> 4 plays, 40 dmg, +8 poison
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 5 plays, 30 dmg, +10 poison, EXHAUST
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Ricochet "Sly. Deal 5 damage to a random enemy 4 times." -> 2 plays, 28 dmg, +8 poison
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 22 block
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 1 plays, 5 dmg, +2 poison, generates 2 Shivs

Active powers: Strength(2)

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~18 dmg
  Leading Strike: 2 Shivs -> ~12 dmg

Poison stacks applied per card:
  Shiv: 10 stacks
  Strike: 8 stacks
  Ricochet: 8 stacks
  Neutralize: 2 stacks
  Leading Strike: 2 stacks

Enemy power timeline:
  Poison: R1:- -> R2:9 -> R3:12 -> R4:21 -> R5:26 -> R6:27
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:4
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:2
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Infested Prism (Floor 29, elite)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost
Deck (24): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Hidden Daggers+, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Infested Prism HP=200/200

### Round 1
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

[Selected: elite] Entomancer (F30, elite)
Historical: loss=13 vs historical avg=15.8+/-9.0 (z=-0.3, TYPICAL, n=4)
## Combat Replay: vs Entomancer (Floor 30, elite)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt, Very Hot Cocoa, White Beast Statue, Unsettling Lamp
Deck (28): Defend x5, Strike x5, Blade Dance x2, Piercing Wail+ x2, Ascender's Bane, Dagger Throw, Dash, Deflect, Envenom+, Expertise+, Expose, Flick-Flack, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Ricochet, Survivor
Enemies: Entomancer HP=155/155

### Round 1
Agent plan (hypothesis): Play out scaling powers or big attacks with the remaining 3 energy. Be mindful of Dazed added to the draw pile by Dagger Throw.
Agent plan (hypothesis): Watch out for the draw pile filling with Dazed. Prepare for the heavy attack next turn.
Intent: Entomancer: Attack(3x7=21)
  Piercing Wail+
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust. | enemy_deltas: Entomancer: +Strength(-16), +Piercing Wail(16)
  Expose -> Entomancer[0]
    exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust. | enemy_deltas: Entomancer: +Vulnerable(2)
  Survivor
    energy -1 | block +8
  Strike
  Dagger Throw -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -16
  Defend
  Expertise+
    energy -1
  Leg Sweep -> Entomancer[0]
    energy -2 | block +11 | enemy_deltas: Entomancer: +Weak(2)
  Blade Dance
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust.
  Shiv -> Entomancer[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Entomancer: hp -9
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -9
  Neutralize -> Entomancer[0]
    enemy_deltas: Entomancer: hp -7, Weak(2→3)
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -9
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.

### Round 2
Intent: Entomancer: Attack(13)
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -12
  Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -12
  turn_end
    exhausted: Shiv*3 [0]: Deal 4 damage. Exhaust.

### Round 3
Agent plan (hypothesis): Enemy will attack heavily next turn (escalating multi-attack). Be prepared to block.
Intent: Entomancer: Buff
  Envenom+
    energy -2 | +Envenom(2)
  Deflect
    block +4
  Leading Strike -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -5, +Poison(2)
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, Poison(2→4)
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, Poison(4→6)
  turn_end

### Round 4
Agent plan (hypothesis): Next turn is a single heavy attack, be prepared to block it. Poison scaling will now accelerate with Fumes.
Intent: Entomancer: Attack(4x7=28)
  Piercing Wail+
    energy -1 | enemy_deltas: Entomancer: Strength(1→-7), +Piercing Wail(8)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Entomancer: Attack(19)
  Blade Dance
    energy -1
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, Poison(6→8)
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, Poison(8→10)
  Shiv -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, Poison(10→12)
  Ricochet
    energy -2 | enemy_deltas: Entomancer: hp -20, Poison(12→20)
  turn_end
## Combat Analytics: Entomancer (WIN - 5 rounds)

Cards played (with descriptions):
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 1 plays, 16 dmg
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 2 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 6 damage. Exhaust." -> 8 plays, 57 dmg, +10 poison, EXHAUST
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 1 plays, 7 dmg
  Strike "Deal 8 damage." -> 2 plays, 24 dmg
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays
  Deflect "Gain 4 Block." -> 1 plays, 4 block
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 1 plays, 5 dmg, +2 poison, generates 2 Shivs
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Defend "Gain 5 Block." -> 1 plays, 5 block
  Ricochet "Sly. Deal 5 damage to a random enemy 4 times." -> 1 plays, 20 dmg, +8 poison

Active powers: Strength(2)

Token attribution (Shivs):
  Blade Dance: 6 Shivs -> ~43 dmg
  Leading Strike: 2 Shivs -> ~14 dmg

Poison stacks applied per card:
  Shiv: 10 stacks
  Ricochet: 8 stacks
  Leading Strike: 2 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2
  Poison: R1:- -> R2:- -> R3:- -> R4:5 -> R5:6
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-
  Weak: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Entomancer (Floor 28, elite)
Relics: Ring of the Snake, Large Capsule, Meat on the Bone, Bag of Preparation, Gambling Chip, Permafrost, Pantograph, Very Hot Cocoa, Razor Tooth
Deck (31): Defend x6, Strike x5, Dodge and Roll x2, Acrobatics, Ascender's Bane, Backflip, Backflip+, Blade Dance, Deadly Poison, Deflect, Expertise+, Footwork+, Neutralize+, Nightmare, Noxious Fumes+, Peck, Poisoned Stab, Pounce, Skewer+, Survivor, Well-Laid Plans
Enemies: Entomancer HP=145/145

### Round 1
Intent: Entomancer: Attack(3x7=21)
  Footwork+
    energy -1 | block +7 | +Dexterity(3)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Defend
    energy -1 | block +8
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Acrobatics
    energy -1
  Skewer+
  Backflip+
    energy -1 | block +11
  Neutralize+ -> Entomancer[0]
    enemy_deltas: Entomancer: hp -4, +Weak(2)
  Poisoned Stab -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: hp -6, +Poison(3)
  turn_end

### Round 2
Intent: Entomancer: Attack(13)
  Deflect
    block +7
  Expertise+
    energy -1
  Dodge and Roll
    energy -1 | block +7 | +Block Next Turn(7)
  Defend
    energy -1 | block +8
  turn_end
    exhausted: Dazed [0]: Unplayable. Ethereal.

### Round 3
Intent: Entomancer: Buff
  Backflip
    energy -1 | block +8
  Pounce -> Entomancer[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Entomancer: hp -12
  turn_end
    exhausted: Dazed*2 [0]: Unplayable. Ethereal.

### Round 4
Intent: Entomancer: Attack(4x7=28)
  Deadly Poison -> Entomancer[0]
    -Free Skill | enemy_deltas: Entomancer: Poison(9→14)
  Defend
    energy -1 | block +8
  Defend+
    energy -1 | block +11
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end

### Round 5
Intent: Entomancer: Attack(19)
  Acrobatics+
    energy -1
  Nightmare
  Neutralize+ -> Entomancer[0]
    enemy_deltas: Entomancer: hp -4, +Weak(2)
  Dodge and Roll+
    energy -1 | block +9 | +Block Next Turn(9)
  Survivor
    energy -1 | block +11
  Strike
  turn_end
  Poisoned Stab+

### Round 6
Intent: Entomancer: Buff
  Pounce+ -> Entomancer[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Entomancer: hp -18
  Backflip+
    block +11 | -Free Skill
  Dodge and Roll+
    energy -1 | block +9 | +Block Next Turn(9)
  turn_end
  Backflip+

### Round 7
Intent: Entomancer: Attack(5x7=35)
  Deflect+
    block +10
  Backflip+
    energy -1 | block +11
  Defend
    energy -1 | block +8
  turn_end
  Expertise+

### Round 8
Intent: Entomancer: Attack(20)
  Defend
    energy -1 | block +8
  Defend+
    energy -1 | block +11
  turn_end
  Expertise+
## Combat Analytics: Entomancer (WIN - 8 rounds)

Cards played (with descriptions):
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 7 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Defend "Gain 8 Block." -> 5 plays, 40 block
  Dodge and Roll "Gain 7 Block. Next turn, gain 7 Block." -> 2 plays, 14 block
  Acrobatics "Draw 3 cards. Discard 1 card." -> 1 plays
  Backflip+ "Gain 11 Block. Draw 2 cards." -> 3 plays, 33 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 8 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, +3 poison
  Deflect "Gain 7 Block." -> 1 plays, 7 block
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Backflip "Gain 8 Block. Draw 2 cards." -> 1 plays, 8 block
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 1 plays, 12 dmg
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Defend+ "Gain 11 Block." -> 2 plays, 22 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Dodge and Roll+ "Gain 9 Block. Next turn, gain 9 Block." -> 2 plays, 18 block
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Pounce+ "Deal 18 damage. The next Skill you play costs 0 energy ." -> 1 plays, 18 dmg
  Deflect+ "Gain 10 Block." -> 1 plays, 10 block

Poison stacks applied per card:
  Deadly Poison: 5 stacks
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2 -> R6:2 -> R7:3 -> R8:3
  Poison: R1:- -> R2:5 -> R3:7 -> R4:9 -> R5:16 -> R6:18 -> R7:20 -> R8:22
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:1 -> R7:2 -> R8:2
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:-

[Selected: boss, death] multi:Crusher+Rocket (F33, boss)
Historical: loss=69 vs historical avg=18.0+/-12.0 (z=4.2, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Booming Conch, Joss Paper, Girya, Potion Belt, Very Hot Cocoa, White Beast Statue, Unsettling Lamp, Strawberry
Deck (30): Defend x5, Strike x5, Blade Dance x2, Piercing Wail+ x2, Ascender's Bane, Dagger Throw, Dash, Deflect, Envenom+, Expertise+, Expose, Flick-Flack, Footwork, Leading Strike, Leg Sweep, Neutralize, Noxious Fumes, Phantom Blades, Ricochet, Survivor
Enemies: Crusher HP=219/219, Rocket HP=209/209

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Liquid Bronze
    +Thorns(3)
  Powdered Demise -> Crusher[0]
    enemy_deltas: Crusher: +Demise(9)
  Footwork
    energy -1 | +Dexterity(2)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Piercing Wail+
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust. | enemy_deltas: Crusher: +Strength(-16), +Piercing Wail(16); Rocket: +Strength(-16), +Piercing Wail(16)
  Expose -> Crusher[0]
    exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust. | enemy_deltas: Crusher: +Vulnerable(2)
  Blade Dance
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Exhaust.
  Ricochet
    energy -2 | enemy_deltas: Crusher: hp -14; Rocket: hp -10
  Shiv -> Crusher[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Crusher: hp -9
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -9
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -12
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -9
  turn_end

### Round 2
Intent: Crusher: Attack(4), Rocket: Attack(27)
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Blade Dance
    energy -1
  Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -8
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -15
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -6
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -6
  turn_end
    exhausted: Shiv*6 [0]: Retain. Deal 4 damage. Exhaust.

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -11
  Flick-Flack
  Dash -> Crusher[0]
    energy -2 | block +12 | enemy_deltas: Crusher: hp -12
  turn_end

### Round 4
Intent: Crusher: Buff, Rocket: Attack(49)
  Neutralize -> Rocket[1]
    enemy_deltas: Rocket: hp -3, +Weak(1)
  Survivor
    energy -1 | block +7
  Defend
  Expertise+
    energy -1
  Piercing Wail+
    energy -1 | enemy_deltas: Crusher: +Strength(-8), +Piercing Wail(8); Rocket: Strength(2→-6), +Piercing Wail(8)
  Deflect
    block +4
  turn_end

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Neutralize -> Crusher[0]
    enemy_deltas: Crusher: hp -3, +Weak(1)
  Defend
    energy -1 | block +5
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -6
  Flick-Flack
    energy -1 | enemy_deltas: Crusher: hp -6; Rocket: hp -6
  turn_end

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: block -11
  Strike
  Defend
    energy -1 | block +7
  Survivor
    energy -1 | block +10
  Strike
  turn_end

### Round 7
Intent: Crusher: Attack(6), Rocket: Attack(30)
  Dash -> Rocket[1]
    energy -2 | block +12 | enemy_deltas: Rocket: hp -12
  Defend
    energy -1 | block +7
  turn_end

### Round 8
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  Flick-Flack
    energy -1 | enemy_deltas: Crusher: hp -8; Rocket: hp -8
  Strike -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: DIED; Rocket: block +99, Strength(2→8), -Crab Rage
  Defend
    energy -1 | block +7
  turn_end

### Round 9
Intent: Rocket: Attack(41)
  Strike -> Rocket[0]
    energy -1 | enemy_deltas: Rocket: hp -8
  Deflect
    block +6
  Strike -> Rocket[0]
    energy -1 | enemy_deltas: Rocket: hp -8
  Survivor
    energy -1 | block +10
  turn_end
## Combat Analytics: multi:Crusher+Rocket (LOSS - 9 rounds)
Death cause: Died with HP=19, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Footwork "Gain 2 Dexterity." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 2 plays, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 2 plays, EXHAUST, generates 3 Shivs
  Ricochet "Sly. Deal 5 damage to a random enemy 4 times." -> 1 plays, 24 dmg
  Shiv "Deal 6 damage. Exhaust." -> 6 plays, 54 dmg, EXHAUST
  Strike "Deal 8 damage." -> 6 plays, 42 dmg
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Dagger Throw "Deal 11 damage. Draw 1 card. Discard 1 card." -> 2 plays, 11 dmg
  Dash "Gain 12 Block. Deal 12 damage." -> 2 plays, 24 dmg, 24 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 6 dmg
  Survivor "Gain 7 Block. Discard 1 card." -> 3 plays, 27 block
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Deflect "Gain 4 Block." -> 2 plays, 10 block
  Defend "Gain 5 Block." -> 4 plays, 26 block
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 2 plays, 28 dmg

Active powers: Strength(2), Surrounded(1)

Token attribution (Shivs):
  Blade Dance: 6 Shivs -> ~54 dmg

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:-
  Demise: R1:- -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:9 -> R7:9 -> R8:9 -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:9
  Poison[0]: R1:- -> R2:2 -> R3:3 -> R4:4 -> R5:5 -> R6:6 -> R7:7 -> R8:8 -> R9:-
  Poison[1]: R1:- -> R2:2 -> R3:3 -> R4:4 -> R5:5 -> R6:6 -> R7:7 -> R8:8 -> R9:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:-
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-

Unattributed damage (power/passive effects): 1
  Per round: R8:1
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Small Capsule, Candelabra, Venerable Tea Set, Kunai, Archaic Tooth, War Paint
Deck (28): Defend x5, Blade Dance+ x3, Strike x3, Knife Trap+ x2, Backflip, Calculated Gamble, Cloak and Dagger+, Dagger Throw, Expose, Flick-Flack, Hidden Daggers, Leading Strike, Leading Strike+, Phantom Blades+, Piercing Wail+, Ricochet, Suppress+, Survivor, Well-Laid Plans+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Mazaleth's Gift
    +Ritual(1)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Cloak and Dagger+
    energy -1 | block +6
  Suppress+ -> Crusher[0]
    enemy_deltas: Crusher: hp -17, +Weak(5)
  Shiv -> Rocket[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    +Dexterity(1) | enemy_deltas: Rocket: hp -4
  Defend
    energy -1 | block +6
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -9
  Ricochet
  Strike -> Crusher[0]
    energy -1 | Dexterity(1→2) | enemy_deltas: Crusher: hp -6
  turn_end
  Strike
  confirm

### Round 2
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Expose -> Rocket[1]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Rocket: +Vulnerable(2)
  Gambler's Brew
  Strike
  Defend
  Defend
  Defend
  confirm
  Blade Dance+
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    Dexterity(2→3) | enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Blade Dance+
    energy -1
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    Dexterity(3→4) | enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -7
  Backflip
    energy -1 | block +9
  Survivor
    energy -1 | block +12
  Calculated Gamble
  turn_end
  Knife Trap+
  Piercing Wail+

### Round 3
Intent: Crusher: Attack(6x2=12), Debuff, Rocket: Buff
  Phantom Blades+
    energy -1 | +Phantom Blades(12)
  Blade Dance+
    energy -1
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -27
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -9
  Shiv -> Rocket[1]
    Dexterity(4→5) | enemy_deltas: Rocket: hp -9
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -9
  Hidden Daggers
  Knife Trap+
  Leading Strike
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -9
  Shiv -> Crusher[0]
    Dexterity(5→6) | enemy_deltas: Crusher: hp -6
  Defend
    energy -1 | block +11
  turn_end
  Piercing Wail+
  confirm

### Round 4
Intent: Crusher: Buff, Rocket: Attack(49)
  Piercing Wail+
    energy -1 | exhausted: Shiv*16 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Crusher: +Strength(-8), +Piercing Wail(8); Rocket: Strength(2→-6), +Piercing Wail(8)
  Leading Strike+ -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -6
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -14
  Shiv -> Rocket[1]
    Dexterity(6→7) | enemy_deltas: Rocket: hp -5
  Leading Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    enemy_deltas: Rocket: hp -5
  Shiv -> Rocket[1]
    Dexterity(7→8) | enemy_deltas: Rocket: hp -5
  turn_end
  Knife Trap+
  Flick-Flack

### Round 5
Intent: Crusher: Attack(15), Defend, Rocket: Sleep
  Backflip
    energy -1 | block +9
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -9
  Ricochet
  Defend
    energy -1 | block +9
  Hidden Daggers
  Flick-Flack
  Strike
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -15
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -6
  turn_end
  Knife Trap+
  Knife Trap+

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  Defend
    energy -1 | block +14
  Strike -> Rocket[1]
    energy -1 | enemy_deltas: Rocket: hp -11
  Survivor
    energy -1 | block +17
  Defend
  turn_end
  Knife Trap+
  Knife Trap+

### Round 7
Intent: Crusher: Attack(9), Rocket: Attack(20)
  Suppress+ -> Crusher[0]
    enemy_deltas: Crusher: hp -23, +Weak(5)
  Cloak and Dagger+
    energy -1 | block +15
  Shiv -> Crusher[0]
    enemy_deltas: Crusher: hp -22
  Dagger Throw -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -15
  Strike
  Survivor
    energy -1 | block +18
  Knife Trap+
  Shiv -> Rocket[1]
    enemy_deltas: Crusher: block +99, Strength(2→8), -Crab Rage; Rocket: DIED
  Calculated Gamble
    exhausted: Shiv*24 [0]: Retain. Deal 4 damage. Exhaust.
  turn_end
  Defend
  confirm

### Round 8
Intent: Crusher: Attack(10x2=20), Debuff
  Leading Strike+ -> Crusher[0]
    energy -1 | enemy_deltas: Crusher: hp -13
  Ricochet
    energy -2 | enemy_deltas: Crusher: hp -40
  Shiv -> Crusher[0]
    -Surrounded | -Ritual | -Well-Laid Plans | -Dexterity | -Strength | -Phantom Blades | enemy_deltas: Crusher: DIED
## Combat Analytics: multi:Crusher+Rocket (WIN - 8 rounds)

Cards played (with descriptions):
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 2 plays, 21 block, generates 2 Shivs
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 40 dmg
  Shiv "Deal 4 damage. Exhaust." -> 25 plays, 205 dmg, EXHAUST
  Defend "Gain 6 Block." -> 4 plays, 40 block
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 33 dmg
  Strike "Deal 6 damage." -> 2 plays, 17 dmg
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 3 plays, EXHAUST, generates 4 Shivs
  Backflip "Gain 9 Block. Draw 2 cards." -> 2 plays, 18 block
  Survivor "Gain 12 Block. Discard 1 card." -> 3 plays, 47 block
  Phantom Blades+ "Shivs gain Retain. The first Shiv you play each turn deals 12 additional damage." -> 1 plays
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 2 plays, generates 2 Shivs
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 19 dmg, generates 2 Shivs
  Leading Strike "Deal 4 damage. Add 2 Shivs into your Hand." -> 1 plays, 4 dmg, generates 2 Shivs
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, EXHAUST
  Ricochet "Sly. Deal 10 damage to a random enemy 4 times." -> 1 plays, 40 dmg

Active powers: Surrounded(1)

Token attribution (Shivs):
  Blade Dance+: 12 Shivs -> ~98 dmg
  Cloak and Dagger+: 4 Shivs -> ~33 dmg
  Hidden Daggers: 4 Shivs -> ~33 dmg
  Leading Strike+: 3 Shivs -> ~25 dmg
  Leading Strike: 2 Shivs -> ~16 dmg

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:8
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:-
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:- -> R8:4

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F12(Bygone Effigy: WIN), F17(Kin Follower: WIN), F28(Infested Prism: WIN), F30(Entomancer: WIN), F33(Crusher: )
- Core Combat Principles: F2(Nibbit: WIN), F3(Fuzzy Wurm Crawler: WIN), F4(Shrinker Beetle: WIN), F5(Tracker Raider: WIN), F6(Vine Shambler: WIN), F8(Twig Slime (M): ), F12(Bygone Effigy: WIN), F14(Twig Slime (S): ), F17(Kin Follower: WIN), F19(Exoskeleton: WIN), F20(Tunneler: WIN), F21(Ovicopter: WIN), F23(Exoskeleton: WIN), F24(Louse Progenitor: WIN), F28(Infested Prism: WIN), F30(Entomancer: WIN), F31(Spiny Toad: WIN), F33(Crusher: )
- Deck Building Across the Run: F2(), F3(), F4(), F5(), F6(), F8(), F12(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F23(), F23(), F24(), F28(), F30(), F31()
- Map Routing and Path Planning: F1(), F1(), F2(), F5(), F9(), F11(), F14(), F18(), F18(), F20(), F23()
- Rest Site and Event Decisions: F9(), F11(), F13(), F16(), F25(), F27(), F29(), F32()
- Silent - Combat Sequencing: F2(Nibbit: WIN), F3(Fuzzy Wurm Crawler: WIN), F4(Shrinker Beetle: WIN), F5(Tracker Raider: WIN), F6(Vine Shambler: WIN), F8(Twig Slime (M): ), F12(Bygone Effigy: WIN), F14(Twig Slime (S): ), F17(Kin Follower: WIN), F19(Exoskeleton: WIN), F20(Tunneler: WIN), F21(Ovicopter: WIN), F23(Exoskeleton: WIN), F24(Louse Progenitor: WIN), F28(Infested Prism: WIN), F30(Entomancer: WIN), F31(Spiny Toad: WIN), F33(Crusher: )
- Silent - Draft and Shop Rules: F2(), F3(), F4(), F5(), F6(), F8(), F12(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F23(), F23(), F24(), F28(), F30(), F31()
- Silent - Route Priorities: F1(), F1(), F2(), F5(), F9(), F11(), F14(), F18(), F18(), F20(), F23()
- act1_mandatory_elites_shops: F1(), F1(), F2(), F5(), F9(), F11(), F14(), F18(), F18(), F20(), F23()
- act1_max_hp_event_trap: F1(), F7(), F18()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.