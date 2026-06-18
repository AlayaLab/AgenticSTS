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
Result: VICTORY (fitness: 235.5)
Combats won: 28/28
Run duration: 6339.6s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean.
- [card_select] Foundation plan: rely on The Bomb for early AoE and delayed burst damage, prioritizing defensive cards and cheap attacks to survive until it detonates. We still need a cohesive scaling engine and reliable immediate upfront damage for fights like Gremlin Nob.
- [map] Foundation phase: currently relying on basic strikes and defends. The priority is to draft high-impact frontloaded attacks or poison scaling while keeping the deck lean enough to find key cards consistently.
### F2
- [card_reward] Foundation plan: survive with frontload damage (like The Bomb and Dagger Spray) and efficient block while looking for a real scaling engine; take cheap draw or high-impact single-target damage, skip narrow synergy pieces.
- [map] Foundation phase: prioritizing a monster streak to draft frontloaded damage and essential block cards while hoarding gold for more impactful later shops.
### F3
- [card_reward] Foundation plan: survive with The Bomb and efficient block while looking for a primary scaling engine. Prioritize finding premium mitigation and draw to stall out fights while The Bomb ticks down.
### F4
- [card_reward] Foundation plan: Survive with frontload and mitigation. Now we have Noxious Fumes and The Bomb, so our win condition relies on stalling out fights safely. Prioritize block, draw, and maybe one strong frontload attack for elites.
### F5
- [card_reward] Foundation plan: Survive with efficient block and wait out Noxious Fumes and The Bomb; use Well-Laid Plans to hold the right answers for heavy-hitting turns.
### F6
- [card_reward] Committed poison plan: rely on Noxious Fumes and Outbreak for damage, prioritizing multi-hit poison applications like Bouncing Flask and efficient block to stall out fights. Needs single-target poison burst and block.
- [map] Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean. I'm prioritizing a monster streak to draft frontloaded damage and essential block cards while hoarding gold for more impactful later shops.
### F7
- [rest_site] Foundation phase: leveraging The Bomb and Noxious Fumes for delayed AoE/scaling while defending. Upgraded Neutralize provides vital extended mitigation. Need a bit more block to survive setup turns.
### F8
- [card_select] Committed poison plan: rely on Noxious Fumes and Outbreak to scale damage, holding combo pieces with Well-Laid Plans. We still need solid block/mitigation to survive while poison ticks, and need to prioritize removals of strikes.
- [card_reward] Committed poison plan: retain poison pieces (Noxious Fumes, Outbreak) and play them early, then defend while passive poison and AoE kills. Needs dex/block scaling and more poison applicators; skip generic attacks and focus on removals.
- [map] Foundation phase: currently relying on basic cards and seeking high-impact frontloaded attacks or poison scaling. Prioritizing Rest Sites to safely navigate early Elites while looking for a definitive deck core.
### F9
- [rest_site] Foundation phase: leveraging Noxious Fumes, Outbreak, and The Bomb for massive delayed AoE and poison scaling. Keep the deck lean, block aggressively during setup turns, and let passive damage clear enemies. Prioritize acquiring more reliable block and card draw.
### F10
- [map] Foundation phase: currently relying on basic cards and seeking high-impact frontloaded attacks or poison scaling. Prioritizing one more monster fight to find a core card before the upcoming Elite and leveraging our gold at a future shop or for late-act scaling.
### F11
- [hand_select] Conserving damage options for the turn Horn Cleat protects us.
- [card_reward] Committed poison plan: rely on Noxious Fumes and Outbreak to deal AoE damage while picking cheap poison applications. Defend and stall until passive damage and Outbreak procs finish the fight. Need more block/mitigation and card draw.
- [map] Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean. Seeking a high-impact relic or card from this Elite to commit to a specific scaling strategy.
### F12
- [hand_select] Enemy has 19 HP, The Bomb deals 30. Combat should end this turn.
- [card_reward] Committed poison/stall plan: stall encounters with Noxious Fumes+, Outbreak, and The Bomb while focusing on survival. Use Well-Laid Plans to retain key mitigation like Piercing Wail for big attacks. Needs more card draw, efficient block, and poison application; skip generic damage attacks.
- [map] Foundation phase: currently relying on basics and minor synergies while hunting for a high-impact attack or scaling power. Prioritizing survival and card quality over early elites until a clear engine is established.
### F13
- [rest_site] Committed poison/AoE plan: utilize Noxious Fumes, Outbreak, and The Bomb for massive delayed damage, while blocking and controlling with Piercing Wail and Well-Laid Plans. Needs reliable energy/draw and to avoid adding more slow setup powers.
### F14
- [card_reward] Committed poison plan: Use Noxious Fumes and Deadly Poison to stack poison rapidly, feeding Outbreak for massive AoE burst damage. Retain combo pieces with Well-Laid Plans. Priority is efficient card draw and Dexterity/Block scaling to survive while poison ticks; skip generic attacks entirely.
### F15
- [card_reward] Committed poison plan: stack poison and survive while Noxious Fumes, Outbreak, and The Bomb deal damage. Prioritize efficient block, draw/discard synergies, and defense scaling; skip basic attacks and off-plan synergies.
### F16
- [rest_site] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.
### F17
- [card_reward] Committed poison plan: stack poison and play Accelerant, then defend while passive poison kills. Needs dex/block scaling, draw, and deck thinning; skip off-plan attacks and expensive generic cards.
### F18
- [event] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Now with 4 energy, prioritize high-value block cards (from any class) and card draw to consistently set up powers early.
- [map] Foundation phase: relying on basics while hunting for high-impact frontloaded attacks or a scaling engine. Prioritizing hallway fights to draft essential cards, then aiming to pivot towards non-combat nodes to preserve HP for the boss.
### F19
- [card_reward] Committed poison plan: rely on Noxious Fumes, Outbreak, and The Bomb to scale damage. Needs more block, dexterity, and card draw to survive. Prioritize removals for Strikes.
- [map] Committed poison and stall plan: utilize Noxious Fumes, Outbreak, and The Bomb for scaling damage while maximizing block with Afterimage. The deck currently lacks sufficient card draw and high-value block cards to safely handle Act 2 hallway chains, so I will prioritize events and shops to find defensive pieces and card draw.
### F20
- [card_reward] Committed poison plan: rely on Noxious Fumes, Outbreak, and Snakebite to scale damage. Prioritize efficient draw and mitigation; remove basic Strikes and Defends to thin the deck.
- [map] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.
### F21
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison safely, and use Mirage or Piercing Wail for burst mitigation. Needs more draw/deck thinning to reach engines faster.
- [map] Committed poison/stall plan: rely on Noxious Fumes and The Bomb while blocking with Afterimage. Use the high gold reserve to hunt for card draw, dexterity, or 'Blur' to bridge the gap between defensive turns. Avoid basic attacks and minimize hallway combat to preserve HP for the boss.
### F22
- [card_select] Committed poison plan: rely on Noxious Fumes, Deadly Poison, and Accelerant to stack and multiply poison damage while defending with Afterimage, Backflip, and basic block. Remove Strikes at every opportunity to improve draw consistency. Look for more block and draw; skip generic attacks.
### F23
- [card_reward] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks and clunky expensive cards.
### F24
- [hand_select] Reducing a 2-cost Retain card to 0 cost provides recurring value every time it is played, fitting the stall/poison archetype.
- [card_reward] Committed poison/stall plan: stall with block and Piercing Wail while Noxious Fumes, Outbreak, and The Bomb deal damage. Needs card draw and block; avoid basic attacks and non-poison damage.
### F25
- [card_reward] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Now with 4 energy, prioritize high-value block cards and card draw to consistently set up powers early; avoid unnecessary attacks.
### F27
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Use premium draw like Guiding Star and Backflip to cycle fast. Need more efficient block and deck thinning.
### F28
- [hand_select] Well-Laid Plans allows keeping The Bomb for the perfect opening without sacrificing next turn's draw.
- [card_reward] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize high-value block cards and card draw to consistently set up powers early.
### F29
- [hand_select] Building a wall for Turn 2.
- [hand_select] Enemy dies to poison next turn. Retaining the better defensive/utility card.
- [card_reward] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize draw and hand manipulation to find core cards quickly.
- [map] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F30
- [card_reward] Committed poison/stall plan: rely on Fumes, Outbreak, and The Bomb for damage. Use Glacier, Afterimage, and defensive skills to survive. Avoid adding more attacks; prioritize removals and block.
### F31
- [event] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize high-value block cards and card draw to consistently set up powers early.
- [event] Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.
### F32
- [rest_site] Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F33
- [hand_select] Multi-attacks are the perfect target for Strength reduction.
- [card_reward] Committed poison plan: survive using Unmovable, Piercing Wail, and efficient block while stacking poison with Fumes and Deadly Poison. Use Well-Laid Plans to set up big Accelerant/Outbreak burst turns. Skip off-plan attacks and remove Strikes.
### F34
- [event] Committed poison/stall plan: utilize Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Stun enemies on critical turns to buy time. Needs more block and card draw; avoid basic attacks.
- [map] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F35
- [card_reward] Committed poison plan: rely on Noxious Fumes, Deadly Poison, and Accelerant to stack and multiply poison damage while defending with Afterimage, Backflip, and basic block. Remove Strikes at every opportunity to improve draw consistency. Look for more block and draw; skip generic attacks and narrow synergies.
- [map] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for scaling damage while prioritizing Afterimage for block. Seeking card draw and high-quality defensive skills; with Meal Ticket and The Courier, shops are high-priority for both health sustain and discount scaling pieces.
### F36
- [event] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for scaling damage while prioritizing Afterimage for block. Seeking card draw and high-quality defensive skills; with Meal Ticket and The Courier, shops are high-priority for both health sustain and discount scaling pieces.
- [map] Committed poison/stall plan: use Noxious Fumes and The Bomb for damage while leveraging Afterimage for defense. Prioritize purchasing card draw, high-quality defensive skills, or poison accelerators at the shop to stabilize the scaling phase; avoid drafting basic attacks.
### F37
- [card_select] Committed poison plan: stack poison and survive with efficient block while passive damage and Outbreak kills. Remove Strikes and prioritize draw/block.
- [map] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw (Acrobatics, Backflip) and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F38
- [card_reward] Committed poison plan: rely on Noxious Fumes, Snakebite, and Accelerant to stack poison on the primary target. Defend heavily with Glacier, Unmovable, and Piercing Wail during dangerous multi-attack turns. Deck is large, avoid adding more cards unless they are premium draw or critical mitigation.
- [map] Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F39
- [event] Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F40
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison and Outbreak kills. Needs card draw; skip basic attacks and low-impact cards.
### F41
- [map] Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F42
- [card_reward] Committed poison/stall plan: prioritize surviving with efficient block and Piercing Wails while Noxious Fumes and Outbreak scale for the kill. Keep deck lean by skipping generic additions; still looking for premium block or draw.
- [map] Committed poison/stall plan: utilizing Noxious Fumes and The Bomb for damage while relying on Afterimage for block. Currently seeking additional card draw and high-quality defensive skills to bridge the gap during the scaling phase; avoid drafting basic attacks.
### F43
- [map] Committed poison/stall plan: stack poison with Noxious Fumes and Outbreak while generating block through Afterimage and defensive skills. Prioritize finding more card draw and high-quality block to survive the setup phase; skip basic attacks and low-impact damage.
### F44
- [rest_site] Committed poison/stall plan: utilize Noxious Fumes, Accelerant, and Outbreak for rapidly scaling damage while prioritizing Afterimage and Mirage for block. Use well-laid plans to hold key defensive or poison cards. Avoid basic attacks.
- [map] Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.
### F45
- [event] Committed poison/stall plan: utilize Noxious Fumes, Accelerant, and Outbreak for rapidly scaling damage while prioritizing Afterimage, Unmovable, and Mirage for block. Use well-laid plans to hold key defensive or poison cards. Avoid basic attacks. Maintain HP for the boss.
### F46
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison, defend while passive poison kills. Needs block scaling and draw; remove curses/strikes.
### F47
- [rest_site] Committed poison/stall plan: utilize Noxious Fumes and Accelerant for scaling damage, prioritizing Afterimage, Mirage, and Well-Laid Plans to hold defensive answers for big attacks.
### F48
- [hand_select] Amalgam is stunned, no immediate danger. Looking for scaling or block.
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

### Combat Decision Digest (28 combats)
F2 [monster] Fuzzy Wurm Crawler (3R, HP 56->56, loss=0, WIN)
  R1[Fuzzy Wurm Crawler: Atk(4)]: Neutralize(3dmg,1+Weak(1))->The Bomb(power:+The Bomb(3))->Defend(+5blk) | dealt=3 taken=0
  R2[Fuzzy Wurm Crawler: Buff]: Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R3[Fuzzy Wurm Crawler: Atk(11)]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0

F3 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (S) (5R, HP 56->56, loss=0, WIN)
  R1[Twig Slime (S): Atk(4)+Leaf Slime (M): StatusCard(2)+Leaf Slime (S): StatusCard(1)]: Strike(6dmg)->Strike(6dmg)->Neutralize->Defend(+5blk) | dealt=15 taken=0
  R2[Twig Slime (S): Atk(4)+Leaf Slime (M): Atk(8)]: Strike(6dmg)->Strike->Survivor(+8blk) | dealt=9 taken=0
  R3[Leaf Slime (M): StatusCard(2)]: Strike(6dmg)->Strike(6dmg)->Dagger Spray(8dmg) | dealt=20 taken=0
  R4[Leaf Slime (M): Atk(8)]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R5[Leaf Slime (M): StatusCard(2)]: Neutralize(3dmg,1+Weak(1))->Strike | dealt=3 taken=0

F4 [monster] Shrinker Beetle (3R, HP 56->54, loss=2, WIN)
  R1[Shrinker Beetle: DebuffStrong]: The Bomb(power:+The Bomb(3))->Strike(6dmg)->Neutralize(3dmg,1+Weak(1)) | dealt=9 taken=0
  R2[Shrinker Beetle: Atk(7)]: Defend(+5blk)->Strike(4dmg)->Strike(4dmg) | dealt=8 taken=2
  R3[Shrinker Beetle: Atk(13)]: Backflip(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0

F5 [monster] multi:Nibbit+Nibbit (3R, HP 54->54, loss=0, WIN)
  R1[Nibbit: Atk(6), Defend+Nibbit: Buff]: The Bomb(power:+The Bomb(3))->Survivor(+8blk) | dealt=0 taken=0
  R2[Nibbit: Buff+Nibbit: Atk(14)]: Backflip(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Nibbit: Atk(14)+Nibbit: Atk(8), Defend]: Neutralize->Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0

F6 [monster] multi:Leaf Slime (M)+Leaf Slime (S)+Twig Slime (M)+Twig Slime (S) (3R, HP 54->44, loss=10, WIN)
  R1[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Twig Slime (S): Atk(4)+Leaf Slime (S): Atk(3)]: The Bomb(power:+The Bomb(3))->Survivor(+8blk) | dealt=0 taken=0
  R2[Twig Slime (M): Atk(11)+Leaf Slime (M): Atk(8)+Twig Slime (S): Atk(4)+Leaf Slime (S): StatusCard(1)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Noxious Fumes(power:+Noxious Fumes(2)) | dealt=3 taken=10
  R3[Twig Slime (M): StatusCard(1)+Leaf Slime (M): StatusCard(2)+Twig Slime (S): Atk(4)+Leaf Slime (S): Atk(3)]: Defend(+5blk)->Backflip(+5blk)->Neutralize(3dmg,1+Weak(1))->Dagger Spray(24dmg) | dealt=35 taken=0

F8 [elite] Phrog Parasite (6R, HP 44->39, loss=5, WIN)
  R1[Phrog Parasite: StatusCard(3)]: The Bomb(power:+The Bomb(3))->Outbreak(power:+Outbreak(11)) | dealt=0 taken=0
  R2[Phrog Parasite: Atk(4x4=16)]: Defend(+5blk)->Dagger Spray(8dmg)->Survivor(+8blk) | dealt=8 taken=3
  R3[Phrog Parasite: StatusCard(3)]: Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=10 taken=0
  R4[Phrog Parasite: Atk(3x4=12)]: Noxious Fumes(power:+Noxious Fumes(2))->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=2
  R5[Phrog Parasite: StatusCard(3)]: Backflip(+5blk)->Flash of Steel->Dagger Spray(8dmg)->Survivor(+8blk) | dealt=12 taken=0
  R6[Wriggler: Buff, StatusCard(1)+Wriggler: Atk(6)]: Neutralize+->Strike(power:-Outbreak,power:-Well-Laid Plans,power:-Noxious Fumes) | dealt=0 taken=0

F11 [monster] multi:Axe Raider+Crossbow Raider+Tracker Raider (3R, HP 39->36, loss=3, WIN)
  R1[Tracker Raider: Debuff+Axe Raider: Atk(5), Defend+Crossbow Raider: Defend]: Defend(+5blk)->Well-Laid Plans(power:+Well-Laid Plans(1))->Strike(6dmg) | dealt=6 taken=0
  R2[Tracker Raider: Atk(1x8=8)+Axe Raider: Atk(5), Defend+Crossbow Raider: Atk(14)]: Noxious Fumes+(power:+Noxious Fumes(3))->Neutralize+(4dmg,1+Weak(2))->Defend(+3blk)->Defend(+3blk) | dealt=4 taken=3
  R3[Tracker Raider: Atk(1x8=8)+Axe Raider: Atk(12)+Crossbow Raider: Defend]: Echoing Slash(power:-Well-Laid Plans,power:-Frail,power:-Noxious Fumes) | dealt=0 taken=0

F12 [elite] Byrdonis (4R, HP 36->29, loss=7, WIN)
  R1[Byrdonis: Atk(17)]: Neutralize+(4dmg,1+Weak(2))->Defend(+7blk)->Well-Laid Plans(power:+Well-Laid Plans(1))->Outbreak(power:+Outbreak(11)) | dealt=4 taken=5
  R2[Byrdonis: Atk(3x3=9)]: The Bomb(power:+The Bomb(3))->Deadly Poison(1+Poison(5)) | dealt=0 taken=0
  R3[Byrdonis: Atk(19)]: Noxious Fumes+(power:+Noxious Fumes(3))->Survivor(+10blk)->Defend(+7blk) | dealt=0 taken=2
  R4[Byrdonis: Atk(6x3=18)]: Backflip(+7blk)->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=0

F14 [monster] Mawler (5R, HP 50->50, loss=0, WIN)
  R1[Mawler: Atk(4x2=8)]: Neutralize+(4dmg,1+Weak(2))->Well-Laid Plans(power:+Well-Laid Plans(1))->Defend(+5blk)->Defend(+5blk) | dealt=4 taken=0
  R2[Mawler: Atk(10)]: Deadly Poison(1+Poison(5))->Dagger Spray(8dmg)->Strike(6dmg) | dealt=14 taken=0
  R3[Mawler: Debuff]: Noxious Fumes+(power:+Noxious Fumes(3))->Strike(6dmg) | dealt=6 taken=0
  R4[Mawler: Atk(21)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Backflip(+5blk)->Neutralize+(4dmg,1+Weak(2))->Defend(+5blk) | dealt=4 taken=0
  R5[Mawler: Atk(4x2=8)]: Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0

F15 [monster] multi:Flyconid+Leaf Slime (M) (4R, HP 50->38, loss=12, WIN)
  R1[Leaf Slime (M): StatusCard(2)+Flyconid: Atk(11)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Defend(+5blk)->Strike(6dmg) | dealt=6 taken=0
  R2[Leaf Slime (M): Atk(8)+Flyconid: Debuff]: Backflip(+5blk)->Neutralize+(4dmg,1+Weak(2))->Deadly Poison(1+Poison(5))->Strike(6dmg) | dealt=10 taken=0
  R3[Leaf Slime (M): StatusCard(2)+Flyconid: Atk(12)]: Dagger Spray(16dmg)->Deadly Poison(1Poison(4→9))->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=16 taken=12
  R4[Leaf Slime (M): Atk(12)+Flyconid: Atk(12), Debuff]: Echoing Slash(power:-Vulnerable,power:-Well-Laid Plans) | dealt=0 taken=0

F17 [boss] Ceremonial Beast (7R, HP 59->45, loss=14, WIN)
  R1[Ceremonial Beast: Buff]: Outbreak(power:+Outbreak(11))->Deadly Poison(1+Poison(5))->Deadly Poison(1Poison(5→10)) | dealt=0 taken=0
  R2[Ceremonial Beast: Atk(18), Buff]: Backflip(+5blk)->Noxious Fumes+(power:+Noxious Fumes(3))->Strike(6dmg) | dealt=6 taken=0
  R3[Ceremonial Beast: Atk(20), Buff]: Neutralize+(4dmg,1+Weak(2))->The Bomb(power:+The Bomb(3))->Echoing Slash(10dmg)->Defend(+5blk)->Defend(+5blk) | dealt=14 taken=5
  R4[Ceremonial Beast: Atk(16), Buff]: Afterimage(power:+Afterimage(1))->Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Defend(+6blk) | dealt=0 taken=9
  R5[Ceremonial Beast: Stun]: Dagger Spray(8dmg,+1blk)->Strike(6dmg,+1blk)->Strike(6dmg,+1blk) | dealt=20 taken=0
  R6[Ceremonial Beast: Debuff]: Backflip(+6blk)->Deadly Poison(+1blk,1Poison(23→28))->Echoing Slash(10dmg,+1blk) | dealt=10 taken=0
  R7[Ceremonial Beast: Atk(15)]: Strike(power:-Outbreak,power:-Noxious Fumes,power:-Afterimage,power:-Well-Laid Plans,power:-Ringing) | dealt=0 taken=0

F19 [monster] Tunneler (5R, HP 65->63, loss=2, WIN)
  R1[Tunneler: Atk(13)]: Well-Laid Plans(power:+Well-Laid Plans(1))->Accelerant(power:+Accelerant(1))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Defend(+5blk) | dealt=0 taken=2
  R2[Tunneler: Buff, Defend]: Afterimage(power:+Afterimage(1))->The Bomb(+1blk,power:+The Bomb(3))->Deadly Poison(+1blk,1+Poison(5)) | dealt=0 taken=0
  R3[Tunneler: Atk(23)]: Neutralize+(+1blk,1+Weak(2))->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Deadly Poison(+1blk,1Poison(3→8))->Defend(+6blk)->Survivor(+9blk) | dealt=0 taken=0
  R4[Tunneler: Atk(17)]: Defend(+6blk)->Defend(+6blk)->Dagger Spray(+1blk)->Strike(+1blk) | dealt=0 taken=0
  R5[Tunneler: Atk(13)]: Strike(power:-Well-Laid Plans,power:-Accelerant,power:-Afterimage,power:-Noxious Fumes) | dealt=0 taken=0

F20 [monster] Thieving Hopper (3R, HP 63->59, loss=4, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: The Bomb(power:+The Bomb(3))->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=4
  R2[Thieving Hopper: Buff]: Neutralize+(4dmg,1+Weak(2))->Strike(6dmg)->Strike(6dmg)->Strike(6dmg)->Deadly Poison(1+Poison(5)) | dealt=22 taken=0
  R3[Thieving Hopper: Atk(15)]: Afterimage(power:+Afterimage(1))->Piercing Wail(+1blk,2+Strength(-6),+Piercing Wail(6),exhaust:1)->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0

F21 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (5R, HP 59->59, loss=0, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(8)]: Backflip(+5blk)->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(10)+Exoskeleton: Buff]: Neutralize+->Strike(6dmg)->Strike(6dmg)->Strike(2+Strength(2),+Weak(2))->Piercing Wail(2Strength(2→-4),+Piercing Wail(6),exhaust:1) | dealt=12 taken=0
  R3[Exoskeleton: Buff+Exoskeleton: Atk(10)+Exoskeleton: Buff]: Afterimage(power:+Afterimage(1))->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Defend(+6blk)->Survivor(+9blk) | dealt=0 taken=0
  R4[Exoskeleton: Atk(3x3=9)+Exoskeleton: Buff+Exoskeleton: Atk(12)]: Accelerant(+1blk,power:+Accelerant(1))->Strike(6dmg,+1blk)->Strike(+1blk,1Strength(4→2))->Defend(+6blk) | dealt=6 taken=0
  R5[Exoskeleton: Atk(10)+Exoskeleton: Atk(12)]: Echoing Slash(power:-Afterimage,power:-Noxious Fumes,power:-Accelerant) | dealt=0 taken=0

F23 [monster] Spiny Toad (4R, HP 70->68, loss=2, WIN)
  R1[Spiny Toad: Buff]: Noxious Fumes+(power:+Noxious Fumes(3))->Outbreak(power:+Outbreak(11))->Neutralize+(4dmg,1+Weak(2))->Backflip(+6blk)->Deadly Poison(1+Poison(5)) | dealt=4 taken=0
  R2[Spiny Toad: Atk(17)]: Afterimage(power:+Afterimage(1))->Dodge and Roll(+6blk,power:+Block Next Turn(5))->Mirage(+9blk,exhaust:1)->Defend(+7blk) | dealt=0 taken=0
  R3[Spiny Toad: Atk(17)]: Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Defend(+7blk)->Dagger Spray(8dmg,+1blk)->Strike(6dmg,+1blk) | dealt=14 taken=2
  R4[Spiny Toad: Buff]: Accelerant(+1blk,power:+Accelerant(1))->Snakebite(+1blk,1Poison(11→18))->Deadly Poison(11dmg,+1blk,1Poison(18→23)) | dealt=11 taken=0

F24 [elite] Infested Prism (6R, HP 68->52, loss=16, WIN)
  R1[Infested Prism: Atk(22)]: Strike(6dmg)->Dagger Spray(8dmg)->Backflip(+6blk)->Noxious Fumes+(power:+Noxious Fumes(3))->Survivor(+9blk) | dealt=14 taken=7
  R2[Infested Prism: Atk(16), Defend]: Afterimage(power:+Afterimage(1))->Echoing Slash(10dmg,+1blk)->Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Backflip(+7blk)->Outbreak(+1blk,power:+Outbreak(11)) | dealt=10 taken=0
  R3[Infested Prism: Atk(9x3=27)]: Neutralize+(+1blk,1+Weak(2))->Snakebite(+1blk,1Poison(5→12))->Deadly Poison(2dmg,+1blk,1Poison(12→17))->Mirage(+19blk,exhaust:1)->Dodge and Roll(+6blk,power:+Block Next Turn(5))->Defend(+7blk) | dealt=2 taken=0
  R4[Infested Prism: Buff, Defend]: Strike(6dmg,+1blk)->Strike(6dmg,+1blk)->Deadly Poison(+1blk,1Poison(19→24)) | dealt=12 taken=0
  R5[Infested Prism: Atk(26)]: Backflip(+7blk)->Strike(+1blk)->Snakebite(+1blk,1Poison(26→33))->Accelerant(+1blk,power:+Accelerant(1))->Piercing Wail(+1blk,2Strength(4→-2),+Piercing Wail(6),exhaust:1) | dealt=0 taken=9
  R6[Infested Prism: Atk(20), Defend]: Neutralize+(4dmg,+1blk,+1energy,1+Weak(2))->Backflip(+7blk)->Defend(+7blk)->Dodge and Roll(+6blk,power:+Block Next Turn(5)) | dealt=4 taken=0

F25 [monster] The Obscura (5R, HP 52->39, loss=13, WIN)
  R1[The Obscura: Summon]: Afterimage(power:+Afterimage(1))->Backflip(+7blk)->The Bomb(+1blk,power:+The Bomb(3)) | dealt=0 taken=0
  R2[Parafright: Atk(16)+The Obscura: Atk(10)]: Backflip(+7blk)->Dagger Spray(16dmg,+1blk)->Accelerant(+1blk,power:+Accelerant(1))->Survivor(+9blk) | dealt=16 taken=0
  R3[Parafright: Atk(16)+The Obscura: Buff]: Deadly Poison(+1blk,1+Poison(5))->Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Defend(+7blk)->Defend(+7blk) | dealt=0 taken=0
  R4[Parafright: Atk(19)+The Obscura: Atk(9), Defend]: Dodge and Roll(+6blk,power:+Block Next Turn(5))->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Snakebite(+1blk,1Poison(3→10)) | dealt=0 taken=13
  R5[Parafright: Atk(19)+The Obscura: Buff]: Neutralize+(4dmg,+1blk,1+Weak(2))->Strike(6dmg,+1blk)->Echoing Slash(22dmg,+1blk,2-Poison,-Weak)->Outbreak(+1blk,power:+Outbreak(11)) | dealt=32 taken=0

F27 [monster] Louse Progenitor (5R, HP 39->35, loss=4, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Accelerant(power:+Accelerant(1))->Neutralize+(6dmg,2+Weak(2),-Curl Up)->Echoing Slash(1dmg)->Deadly Poison(1+Poison(5))->Survivor(+9blk) | dealt=7 taken=0
  R2[Louse Progenitor: Defend, Buff]: Well-Laid Plans(power:+Well-Laid Plans(1))->Deadly Poison(1Poison(3→8))->Backflip(+4blk)->Noxious Fumes+(power:+Noxious Fumes(3)) | dealt=0 taken=0
  R3[Louse Progenitor: Atk(19)]: Afterimage(power:+Afterimage(1))->Backflip(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=4
  R4[Louse Progenitor: Atk(14), Debuff]: Outbreak(+1blk,power:+Outbreak(11))->Snakebite(+1blk,1Poison(10→17))->Mirage(+19blk,exhaust:1) | dealt=0 taken=0
  R5[Louse Progenitor: Defend, Buff]: Backflip(+5blk)->Echoing Slash(10dmg,+1blk)->Strike(6dmg,+1blk)->Defend(+5blk) | dealt=16 taken=0

F28 [elite] Entomancer (5R, HP 35->35, loss=0, WIN)
  R1[Entomancer: Atk(3x7=21)]: Backflip(+6blk)->Neutralize+(6dmg,1+Weak(2))->Dodge and Roll(+5blk,power:+Block Next Turn(5))->Defend(+6blk)->Well-Laid Plans(power:+Well-Laid Plans(1)) | dealt=6 taken=0
  R2[Entomancer: Atk(13)]: Deadly Poison(1+Poison(5))->Snakebite(1Poison(5→12))->Accelerant(power:+Accelerant(1)) | dealt=0 taken=0
  R3[Entomancer: Buff]: Afterimage(power:+Afterimage(1))->The Bomb(+1blk,power:+The Bomb(3)) | dealt=0 taken=0
  R4[Entomancer: Atk(4x7=28)]: Deadly Poison(+1blk,1Poison(8→13))->Mirage(+15blk,exhaust:1)->Backflip(+7blk)->Survivor(+9blk) | dealt=0 taken=0
  R5[Entomancer: Atk(19)]: Deadly Poison(+1blk,1Poison(11→16))->Piercing Wail(+1blk,2Strength(1→-5),+Piercing Wail(6),exhaust:1)->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Outbreak(+1blk,power:+Outbreak(11)) | dealt=0 taken=0

F29 [monster] Ovicopter (4R, HP 35->35, loss=0, WIN)
  R1[Ovicopter: Summon]: Well-Laid Plans(power:+Well-Laid Plans(1))->Snakebite(1Poison(4→11))->Dodge and Roll(+5blk,power:+Block Next Turn(5)) | dealt=0 taken=0
  R2[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(16)]: Afterimage(power:+Afterimage(1))->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Neutralize+(4dmg,+1blk,1+Weak(2))->Strike(6dmg,+1blk)->Defend(+7blk)->Survivor(+9blk) | dealt=10 taken=0
  R3[Hatchling: Atk(4)+Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(5), Debuff]: Strike(+1blk)->Echoing Slash(40dmg,+1blk)->Piercing Wail(+1blk,2+Strength(-6),+Piercing Wail(6),exhaust:1)->Accelerant(+1blk,power:+Accelerant(1)) | dealt=58 taken=0
  R4[Ovicopter: Summon]: Strike(6dmg,+1blk)->Deadly Poison(+1blk,1Poison(13→18))->Deadly Poison(+1blk,1Poison(18→23))->Defend(+7blk) | dealt=6 taken=0

F30 [monster] multi:Myte+Myte (4R, HP 35->35, loss=0, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Backflip(+6blk)->Backflip(+6blk)->Afterimage(power:+Afterimage(1))->Deadly Poison(+1blk) | dealt=0 taken=0
  R2[Myte: Atk(13)+Myte: StatusCard(2)]: Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Toxic(+1blk,exhaust:1)->Toxic(+1blk)->Deadly Poison(+1blk) | dealt=0 taken=0
  R3[Myte: Atk(4), Buff+Myte: Atk(15)]: Mirage(+22blk,exhaust:1)->Accelerant(+1blk,power:+Accelerant(1))->Toxic(+1blk)->Toxic(+1blk) | dealt=0 taken=0
  R4[Myte: Atk(6), Buff]: Neutralize+(4dmg,+1blk,1+Weak(2))->Defend(+7blk)->Snakebite(+1blk,1Poison(6→13))->Strike(6dmg,+1blk) | dealt=10 taken=0

F33 [boss] The Insatiable (7R, HP 38->35, loss=3, WIN)
  R1[The Insatiable: Buff, StatusCard(6)]: Well-Laid Plans(power:+Well-Laid Plans(1))->Accelerant(power:+Accelerant(1))->Dodge and Roll(+5blk,power:+Block Next Turn(5))->Strike(12dmg)->Neutralize+(9dmg,1+Weak(2)) | dealt=41 taken=0
  R2[The Insatiable: Atk(6x2=12)]: Backflip(+6blk)->Afterimage(power:+Afterimage(1))->Calculated Gamble(+1blk,exhaust:1)->Noxious Fumes+(+1blk,power:+Noxious Fumes(3))->Deadly Poison(+1blk,1Poison(2→7)) | dealt=0 taken=0
  R3[The Insatiable: Atk(28)]: Backflip(+7blk)->Outbreak(+1blk,power:+Outbreak(11))->Survivor(+9blk)->Defend(+7blk) | dealt=0 taken=3
  R4[The Insatiable: Buff]: Frantic Escape(+1blk,1Sandpit(2→3))->Deadly Poison(+1blk,1Poison(9→14))->Snakebite(11dmg,+1blk,1Poison(14→21)) | dealt=11 taken=0
  R5[The Insatiable: Atk(10x2=20)]: The Bomb(+1blk,power:+The Bomb(3))->Mirage(+24blk,exhaust:1)->Dodge and Roll(+6blk,power:+Block Next Turn(5)) | dealt=0 taken=0
  R6[The Insatiable: Atk(10x2=20)]: Piercing Wail(+1blk,2Strength(2→-4),+Piercing Wail(6),exhaust:1)->Frantic Escape(+1blk,1Sandpit(1→2))->Frantic Escape(+1blk,1Sandpit(2→3)) | dealt=0 taken=0
  R7[The Insatiable: Atk(30)]: Backflip(+7blk)->Dagger Spray(12dmg,+1blk)->Deadly Poison(+1blk,1Poison(24→29))->Defend(+7blk) | dealt=12 taken=0

F35 [monster] multi:Living Shield+Turret Operator (4R, HP 63->63, loss=0, WIN)
  R1[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Noxious Fumes+(power:+Noxious Fumes(3))->Backflip(+6blk)->Neutralize+(1+Weak(2))->Dodge and Roll(+5blk,power:+Block Next Turn(5))->Backflip(+6blk) | dealt=0 taken=0
  R2[Living Shield: Atk(6)+Turret Operator: Atk(2x5=10)]: Snakebite(1Poison(6→13))->The Bomb(power:+The Bomb(3)) | dealt=0 taken=0
  R3[Living Shield: Atk(6)+Turret Operator: Buff]: Afterimage(power:+Afterimage(1))->Defend(+7blk)->Calculated Gamble(+1blk,exhaust:1)->Dagger Spray(8dmg,+1blk)->Defend(+7blk) | dealt=8 taken=0
  R4[Living Shield: Atk(6)+Turret Operator: Atk(4x5=20)]: Mirage(+29blk,exhaust:1)->Survivor(+9blk)->Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Accelerant(+1blk,power:+Accelerant(1)) | dealt=0 taken=0

F38 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (3R, HP 67->67, loss=0, WIN)
  R1[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff]: Afterimage(power:+Afterimage(1))->Cloak and Dagger(+8blk)->Shiv(+1blk,exhaust:1)->Snakebite(+1blk) | dealt=0 taken=0
  R2[Scroll of Biting: Atk(14)+Scroll of Biting: Atk(7x2=14)]: Backflip(+7blk)->Calculated Gamble(+1blk,exhaust:1)->Backflip(+7blk)->Noxious Fumes(+1blk,power:+Noxious Fumes(2))->Deadly Poison(+1blk,1Poison(3→8)) | dealt=0 taken=0
  R3[Scroll of Biting: Buff+Scroll of Biting: Atk(16)]: Defend(+7blk)->Dagger Spray(8dmg,+1blk)->Echoing Slash(power:-Dexterity,power:-Plating,power:-Afterimage,power:-Noxious Fumes) | dealt=8 taken=0

F39 [monster] Battle Friend V1.0 (2R, HP 67->67, loss=0, WIN)
  R1[Battle Friend V1.0: Unknown]: Shiv+(9dmg,exhaust:1)->Shiv+(9dmg)->Shiv+(9dmg)->Snakebite(1Poison(4→11))->Strike(9dmg) | dealt=36 taken=0
  R2[Battle Friend V1.0: Unknown]: Whistle(power:-Dexterity,power:-Plating) | dealt=0 taken=0

F40 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (6R, HP 67->62, loss=5, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Noxious Fumes(power:+Noxious Fumes(2))->Well-Laid Plans(power:+Well-Laid Plans(1))->Cloak and Dagger(+9blk)->Shiv(6dmg,exhaust:1)->Survivor(+11blk) | dealt=6 taken=0
  R2[Flail Knight: Buff+Spectral Knight: Atk(15)+Magi Knight: Debuff]: Afterimage(power:+Afterimage(1))->Unmovable(+1blk,power:+Unmovable(1))->Calculated Gamble(+1blk,exhaust:1)->Defend(+17blk) | dealt=0 taken=0
  R3[Flail Knight: Atk(12x2=24)+Spectral Knight: Atk(3x3=9)+Magi Knight: Atk(10)]: Mirage(+43blk,exhaust:1)->Defend(+9blk)->The Bomb(+1blk,power:+The Bomb(3)) | dealt=0 taken=0
  R4[Flail Knight: Atk(18)+Spectral Knight: Atk(15)+Magi Knight: Defend]: Piercing Wail(+1blk,2Strength(3→-3),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),exhaust:1)->Neutralize(3dmg,+1blk,1+Weak(1))->Whistle(33dmg,+1blk,exhaust:1) | dealt=36 taken=5
  R5[Flail Knight: Atk(18)+Spectral Knight: Atk(15)+Magi Knight: Atk(35)]: Deadly Poison(+1blk,1Poison(8→13))->Glacier(+24blk)->Piercing Wail(+1blk,2Strength(3→-3),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6),2+Strength(-6),+Piercing Wail(6)) | dealt=0 taken=0
  R6[Flail Knight: Buff]: Strike(6dmg,+1blk)->Backflip(+17blk)->Strike(power:-Dexterity,power:-Noxious Fumes,power:-Well-Laid Plans,power:-Afterimage,power:-Unmovable) | dealt=6 taken=0

F42 [monster] Frog Knight (6R, HP 62->62, loss=0, WIN)
  R1[Frog Knight: Atk(13), Debuff]: Glacier(+12blk)->Accelerant(power:+Accelerant(1))->Defend(+6blk) | dealt=0 taken=0
  R2[Frog Knight: Atk(21)]: Afterimage(power:+Afterimage(1))->Noxious Fumes(+1blk,power:+Noxious Fumes(2))->Noxious Fumes+(+1blk,power:Noxious Fumes(2→5))->Defend(+5blk) | dealt=0 taken=0
  R3[Frog Knight: Buff]: Well-Laid Plans(+1blk,power:+Well-Laid Plans(1))->Backflip(+5blk)->Snakebite(+1blk,1Poison(5→12)) | dealt=0 taken=0
  R4[Frog Knight: Atk(18), Debuff]: Piercing Wail+(+1blk,2Strength(5→-3),+Piercing Wail(8),exhaust:1)->Backflip(+7blk)->Outbreak(+1blk,power:+Outbreak(11))->Cloak and Dagger(+8blk)->Shiv(+1blk,exhaust:1) | dealt=0 taken=0
  R5[Frog Knight: Atk(26)]: Whistle(24dmg,+1blk,exhaust:1)->Deadly Poison(+1blk,1Poison(18→23)) | dealt=24 taken=0
  R6[Frog Knight: Atk(26)]: Neutralize+(4dmg,+1blk,1+Weak(2))->Deadly Poison(+1blk,1Poison(26→31))->Mirage(+25blk,exhaust:1) | dealt=4 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (7R, HP 70->55, loss=15, WIN)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Outbreak(power:+Outbreak(11))->Unmovable(power:+Unmovable(1))->Deadly Poison(1Poison(4→9)) | dealt=0 taken=14
  R2[Torch Head Amalgam: Atk(18)+Queen: Debuff]: Noxious Fumes+(power:+Noxious Fumes(3))->Afterimage(power:+Afterimage(1)) | dealt=0 taken=1
  R3[Torch Head Amalgam: Atk(12x3=36)+Queen: Buff, Defend]: Whistle(24dmg,+1blk,exhaust:1)->Accelerant+(+1blk,power:+Accelerant(2))->Noxious Fumes(+1blk,power:Noxious Fumes(3→5))->Defend(+10blk) | dealt=24 taken=0
  R4[Torch Head Amalgam: Atk(13x3=39)+Queen: Buff, Defend]: Piercing Wail+(+1blk,2Strength(1→-7),+Piercing Wail(8),2+Strength(-8),+Piercing Wail(8),exhaust:1)->Snakebite(11dmg,+1blk,1Poison(12→19))->Backflip(+10blk)->Malaise(+1blk,2Strength(-8→-10),+Weak(2),exhaust:1) | dealt=11 taken=0
  R5[Torch Head Amalgam: Atk(24)+Queen: Buff, Defend]: Calculated Gamble(+1blk,exhaust:1)->Mirage(+47blk,exhaust:1)->Well-Laid Plans+(+1blk,power:+Well-Laid Plans(2))->Backflip(+5blk)->Deadly Poison(11dmg,+1blk,1Poison(21→26)) | dealt=11 taken=0
  R6[Torch Head Amalgam: Atk(25)+Queen: Buff, Defend]: Glacier(+16blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R7[Torch Head Amalgam: Atk(18x3=54)+Queen: Buff, Defend]: Neutralize+(+1blk,1+Weak(2))->Snakebite(+1blk,1Poison(30→37))->Hologram(+6blk)->Deadly Poison(19dmg,+1blk,1Poison(37→42)) | dealt=19 taken=0

### Non-combat Decisions (217 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Lead Paperweight provides a colorless card to kickstart the deck without any negative trade-offs, avoiding the dead draw of a curse from Hefty Tablet. Colorless cards often provide excellent utility or damage for Act 1.
  strategic_note: Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean.

F1 [card_select] select_deck_card (option_index=1) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->14
  deck_change: added The Bomb
  reasoning: In the early foundation phase, we urgently need high-impact damage to survive Act 1 elites and hallways. The Bomb deals 40 AoE damage, which practically solves many early encounters (like Jaw Worm, Sentries, or Slime Boss splits) by allowing us to simply play it and turtle for three turns until it detonates.
  strategic_note: Foundation plan: rely on The Bomb for early AoE and delayed burst damage, prioritizing defensive cards and cheap attacks to survive until it detonates. We still need a cohesive scaling engine and reliable immediate upfront damage for fights like Gremlin Nob.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting the Act 1 monster streak to secure foundational cards. This path aligns with the Route Intelligence to draft early front-loaded damage and build a core deck before the first Elite.
  strategic_note: Foundation phase: currently relying on basic strikes and defends. The priority is to draft high-impact frontloaded attacks or poison scaling while keeping the deck lean enough to find key cards consistently.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->111 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 111->111 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 56->56 | Gold 111->111 | Deck 14->15
  deck_change: picked Dagger Spray
  reasoning: Dagger Spray provides immediate frontloaded AoE damage, which is crucial for early Act 1 hallways and Elites like Sentries. Since Blade Dance is a Skill, it triggers Gremlin Nob's enrage, making Dagger Spray (an Attack) a safer early damage pick. It also pairs well with any future Strength/Prowess scaling.
  strategic_note: Foundation plan: survive with frontload damage (like The Bomb and Dagger Spray) and efficient block while looking for a real scaling engine; take cheap draw or high-impact single-target damage, skip narrow synergy pieces.

F2 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 111->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the monster streak strategy to draft foundational cards early in Act 1. 111 gold is insufficient to guarantee a high-impact shop purchase, so securing card rewards to stabilize the deck is the priority.
  strategic_note: Foundation phase: prioritizing a monster streak to draft frontloaded damage and essential block cards while hoarding gold for more impactful later shops.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 111->124 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 124->124 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 56->56 | Gold 124->124 | Deck 15->16
  deck_change: picked Backflip
  reasoning: Backflip is a premium draw and block tool that fits into any deck. Since we already have The Bomb for massive delayed damage and Dagger Spray for AoE, cycling through our deck quickly to find these key cards and blocking while we wait for The Bomb to detonate is an excellent strategy.
  strategic_note: Foundation plan: survive with The Bomb and efficient block while looking for a primary scaling engine. Prioritize finding premium mitigation and draw to stall out fights while The Bomb ticks down.

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 124->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 124->134 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 134->134 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 54->54 | Gold 134->134 | Deck 16->17
  deck_change: picked Noxious Fumes
  reasoning: Noxious Fumes is a premium scaling power that provides passive AoE damage, helping solve boss fights. It synergizes well with our strategy of stalling with defensive cards while The Bomb and Poison tick down.
  strategic_note: Foundation plan: Survive with frontload and mitigation. Now we have Noxious Fumes and The Bomb, so our win condition relies on stalling out fights safely. Prioritize block, draw, and maybe one strong frontload attack for elites.

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 134->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 134->148 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 148->148 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 54->54 | Gold 148->148 | Deck 17->18
  deck_change: picked Well-Laid Plans
  reasoning: Well-Laid Plans is a premium power that allows us to retain situational cards like defensive pieces or The Bomb until the optimal turn, synergizing perfectly with our delayed scaling damage.
  strategic_note: Foundation plan: Survive with efficient block and wait out Noxious Fumes and The Bomb; use Well-Laid Plans to hold the right answers for heavy-hitting turns.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 148->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 148->157 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 157->157 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Colorless Potion

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 157->157 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 44->44 | Gold 157->157 | Deck 18->19
  deck_change: picked Outbreak
  reasoning: Outbreak is a strong uncommon power that scales exceptionally well with Poison. We already have Noxious Fumes, which will steadily trigger Outbreak over time (and much faster in multi-enemy fights, giving us needed AoE). This firmly sets us on a Poison-based engine path.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Outbreak for damage, prioritizing multi-hit poison applications like Bouncing Flask and efficient block to stall out fights. Needs single-target poison burst and block.

F6 [map] choose_map_node (option_index=1) | source=llm
  HP 44->44 | Gold 157->157 | Deck 19->19
  deck_change: no deck change
  reasoning: My HP is currently 44/70 (63%) after five consecutive monster fights. While not critically low, the next node is an Elite, and following the route's advice to use a Rest Site as a buffer before an Elite is the safest way to ensure I can either upgrade a key card or heal if I feel vulnerable. Given my current health, I'll likely use this to Smith and improve my deck's output for the upcoming fight.
  strategic_note: Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean. I'm prioritizing a monster streak to draft frontloaded damage and essential block cards while hoarding gold for more impactful later shops.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=10, note_scope=run, note_triggers=all) | source=llm
  HP 44->44 | Gold 157->157 | Deck 19->19
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With another rest site immediately following the upcoming Elite, we can afford to Smith now and heal later. Upgrading Neutralize to 2 turns of Weak provides excellent, cost-free damage mitigation which is especially critical against Lagavulin and Nob. This helps preserve our remaining HP pool during the Elite fight.
  strategic_note: Foundation phase: leveraging The Bomb and Noxious Fumes for delayed AoE/scaling while defending. Upgraded Neutralize provides vital extended mitigation. Need a bit more block to survive setup turns.

F7 [rest_site] proceed | source=auto
  HP 44->44 | Gold 157->157 | Deck 19->19
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 44->44 | Gold 157->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Elite

F8 [card_select] select_deck_card (option_index=0) | source=llm
  HP 39->39 | Gold 157->0 | Deck 19->19
  deck_change: no deck change
  reasoning: We did not find Purity from the Colorless Potion. Flash of Steel is the best generic option here, providing 5 free damage and drawing a card to replace itself.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Outbreak to scale damage, holding combo pieces with Well-Laid Plans. We still need solid block/mitigation to survive while poison ticks, and need to prioritize removals of strikes.

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 157->184 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 27 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 184->184 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 184->184 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim relic: Mercury Hourglass

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 184->184 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 39->39 | Gold 184->184 | Deck 19->20
  deck_change: picked Echoing Slash
  reasoning: Echoing Slash provides premium frontloaded AoE damage, which is excellent for dealing with multi-enemy encounters like Gremlins or Slime Boss splits. While we have The Bomb and Outbreak, Echoing Slash's immediate impact helps preserve HP early in the run.
  strategic_note: Committed poison plan: retain poison pieces (Noxious Fumes, Outbreak) and play them early, then defend while passive poison and AoE kills. Needs dex/block scaling and more poison applicators; skip generic attacks and focus on removals.

F8 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 184->184 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site after an Elite encounter. At 56% HP, this provides a necessary buffer to either heal or smith a foundational card before the next Elite on Floor 11.
  strategic_note: Foundation phase: currently relying on basic cards and seeking high-impact frontloaded attacks or poison scaling. Prioritizing Rest Sites to safely navigate early Elites while looking for a definitive deck core.

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=14, note_scope=run, note_triggers=all) | source=llm
  HP 39->39 | Gold 184->184 | Deck 20->20
  deck_change: upgraded Noxious Fumes->Noxious Fumes+
  reasoning: With 39 HP and an upcoming Treasure then a regular Monster, we are safe enough to Smith, especially since another Rest Site is available at F13. Upgrading Noxious Fumes significantly accelerates our long-term damage scaling for the Act Boss and tougher single targets, synergizing perfectly with our defensive posture and Outbreak.
  strategic_note: Foundation phase: leveraging Noxious Fumes, Outbreak, and The Bomb for massive delayed AoE and poison scaling. Keep the deck lean, block aggressively during setup turns, and let passive damage clear enemies. Prioritize acquiring more reliable block and card draw.

F9 [rest_site] proceed | source=auto
  HP 39->39 | Gold 184->184 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 184->184 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 39->39 | Gold 184->220 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 39->39 | Gold 220->220 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Horn Cleat

F10 [treasure] proceed | source=random
  HP 39->39 | Gold 220->220 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 39->39 | Gold 220->0 | Deck 20->20
  deck_change: no deck change
  reasoning: The route intelligence and my current HP (39/70) suggest taking a monster encounter first. Jumping straight into an Elite at 56% HP without a strong deck foundation is risky. Taking the monster fight allows for one more card reward to strengthen the deck before the forced Elite later in the path.
  strategic_note: Foundation phase: currently relying on basic cards and seeking high-impact frontloaded attacks or poison scaling. Prioritizing one more monster fight to find a core card before the upcoming Elite and leveraging our gold at a future shop or for late-act scaling.

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 220->235 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 235->235 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 235->235 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 36->36 | Gold 235->235 | Deck 20->21
  deck_change: picked Deadly Poison
  reasoning: Deadly Poison is a highly efficient 1-cost poison applier that perfectly supports our Outbreak engine. Since Outbreak triggers based on the number of times we apply poison rather than the amount, a cheaper application card is preferable to the 2-cost Snakebite, especially on 3 energy.
  strategic_note: Committed poison plan: rely on Noxious Fumes and Outbreak to deal AoE damage while picking cheap poison applications. Defend and stall until passive damage and Outbreak procs finish the fight. Need more block/mitigation and card draw.

F11 [map] choose_map_node (option_index=1) | source=llm
  HP 36->36 | Gold 235->0 | Deck 21->21
  deck_change: no deck change
  reasoning: I am following the recommended route to take an Elite fight. With 235 gold and a Rest Site immediately following this node, I can afford to take some damage here to secure a relic and a higher-quality card reward to define the deck's direction. My HP is at 51%, which is risky but manageable for an Act 1 Elite given the upcoming heal.
  strategic_note: Foundation phase: relying on basic strikes and defends. Need to find a strong early attack or macro synergy to build around while keeping the deck lean. Seeking a high-impact relic or card from this Elite to commit to a specific scaling strategy.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 235->265 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 265->265 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim relic: Meal Ticket

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 265->265 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 29->29 | Gold 265->265 | Deck 21->22
  deck_change: picked Piercing Wail
  reasoning: Our deck has successfully transitioned into a poison and AoE stall strategy using Noxious Fumes+, Outbreak, and The Bomb. Piercing Wail is a premium mitigation tool that fits perfectly into a stall plan, effectively countering multi-attacks from elites and the Act 1 boss while keeping us alive for our passive damage to scale.
  strategic_note: Committed poison/stall plan: stall encounters with Noxious Fumes+, Outbreak, and The Bomb while focusing on survival. Use Well-Laid Plans to retain key mitigation like Piercing Wail for big attacks. Needs more card draw, efficient block, and poison application; skip generic damage attacks.

F12 [map] choose_map_node (option_index=1) | source=llm
  HP 29->29 | Gold 265->265 | Deck 22->22
  deck_change: no deck change
  reasoning: With 29/70 HP and no substantial upgrades yet, a Rest Site is mandatory to prepare for the final stretch of Act 1. This follows the route intelligence to buffer before the final encounters and allows for a Smith to increase deck quality if I feel safe, though a heal is likely needed given the low HP.
  strategic_note: Foundation phase: currently relying on basics and minor synergies while hunting for a high-impact attack or scaling power. Prioritizing survival and card quality over early elites until a clear engine is established.

F13 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 29->50 | Gold 265->265 | Deck 22->22
  deck_change: no deck change
  reasoning: With 29 HP, we are at risk of taking lethal damage in the upcoming Act 1 hard pool hallway fights (e.g., gremlin gang or slaver/slime). Healing now gives us a comfortable 50 HP buffer, and we have another rest site right before the boss to Smith.
  strategic_note: Committed poison/AoE plan: utilize Noxious Fumes, Outbreak, and The Bomb for massive delayed damage, while blocking and controlling with Piercing Wail and Well-Laid Plans. Needs reliable energy/draw and to avoid adding more slow setup powers.

F13 [rest_site] proceed | source=auto
  HP 50->50 | Gold 265->265 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 50->50 | Gold 265->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 265->279 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 279->279 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 50->50 | Gold 279->279 | Deck 22->23
  deck_change: picked Deadly Poison
  reasoning: The deck is firmly committed to a Poison engine with Outbreak and Noxious Fumes. A second Deadly Poison provides essential single-target scaling and increases the frequency of Outbreak triggers for AoE damage.
  strategic_note: Committed poison plan: Use Noxious Fumes and Deadly Poison to stack poison rapidly, feeding Outbreak for massive AoE burst damage. Retain combo pieces with Well-Laid Plans. Priority is efficient card draw and Dexterity/Block scaling to survive while poison ticks; skip generic attacks entirely.

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 50->50 | Gold 279->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Monster

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 279->287 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 287->287 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Poison Potion

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 287->287 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 38->38 | Gold 287->287 | Deck 23->24
  deck_change: picked Afterimage
  reasoning: Afterimage is a premium rare scaling power that provides crucial passive block. It is vital for surviving multi-hit boss attacks and stalling out fights while our passive damage sources (Poison, Outbreak, The Bomb) scale up.
  strategic_note: Committed poison plan: stack poison and survive while Noxious Fumes, Outbreak, and The Bomb deal damage. Prioritize efficient block, draw/discard synergies, and defense scaling; skip basic attacks and off-plan synergies.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 287->287 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 38->59 | Gold 287->287 | Deck 24->24
  deck_change: no deck change
  reasoning: At 38/70 HP, facing the Act 1 Boss next, the setup turns for our slow-scaling poison/bomb engine will likely result in taking significant damage. Healing restores 21 HP, putting us at a much safer 59 HP to survive the boss.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.

F16 [rest_site] proceed | source=auto
  HP 59->59 | Gold 287->287 | Deck 24->24
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 287->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 287->362 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 362->362 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Touch of Insanity

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 362->362 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 45->45 | Gold 362->362 | Deck 24->25
  deck_change: picked Accelerant
  reasoning: Accelerant is a core scaling piece for a poison deck. Since we already have Noxious Fumes+, Outbreak, and 2x Deadly Poison, Accelerant effectively doubles our passive damage output against bosses and tough Act 2 elites.
  strategic_note: Committed poison plan: stack poison and play Accelerant, then defend while passive poison kills. Needs dex/block scaling, draw, and deck thinning; skip off-plan attacks and expensive generic cards.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 45->65 | Gold 362->362 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=0) | source=llm
  HP 65->65 | Gold 362->362 | Deck 25->25
  deck_change: no deck change
  reasoning: The deck desperately needs more energy to comfortably play its setup powers (Afterimage, Noxious Fumes, Outbreak) and especially The Bomb (2 energy). Prismatic Gem provides a permanent +1 Energy per turn. While mixed card pools can dilute class synergies, our poison engine is already mostly complete. We just need generic block and draw, which all classes can provide.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Now with 4 energy, prioritize high-value block cards (from any class) and card draw to consistently set up powers early.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 65->65 | Gold 362->362 | Deck 25->25
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 65->65 | Gold 362->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Following the recommended route to enter Act 2 via a hallway fight (c3,r1). This allows me to test the deck's foundation and find core scaling or frontloaded damage needed for this act's increased difficulty.
  strategic_note: Foundation phase: relying on basics while hunting for high-impact frontloaded attacks or a scaling engine. Prioritizing hallway fights to draft essential cards, then aiming to pivot towards non-combat nodes to preserve HP for the boss.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 362->376 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 376->376 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 376->376 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 63->63 | Gold 376->376 | Deck 25->25
  deck_change: no deck change
  reasoning: None of the offered cards support the poison engine. Taunt+ applies Vulnerable which doesn't benefit poison or The Bomb. Reflex has almost no discard synergy in the deck, and Slice is unnecessary low-impact damage. Skipping to keep the deck lean.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Outbreak, and The Bomb to scale damage. Needs more block, dexterity, and card draw to survive. Prioritize removals for Strikes.

F19 [map] choose_map_node (option_index=0) | source=llm
  HP 63->63 | Gold 376->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Following the Act 2 route guide which prioritizes non-combat nodes (Unknowns) to preserve HP and avoid dangerous hallway attrition. My deck is currently committed to a poison/stall game plan with The Bomb and Noxious Fumes, so I need to avoid high-damage encounters while looking for defensive upgrades or events.
  strategic_note: Committed poison and stall plan: utilize Noxious Fumes, Outbreak, and The Bomb for scaling damage while maximizing block with Afterimage. The deck currently lacks sufficient card draw and high-value block cards to safely handle Act 2 hallway chains, so I will prioritize events and shops to find defensive pieces and card draw.

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 376->390 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F20 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 59->59 | Gold 390->390 | Deck 24->25
  deck_change: picked Well-Laid Plans
  reasoning: Claim specialcard: Take your stolen card back.

F20 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 59->59 | Gold 390->390 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 59->59 | Gold 390->390 | Deck 25->26
  deck_change: picked Snakebite
  reasoning: Snakebite provides high-burst poison application that we can hold onto until we have spare energy or an optimal moment to stack poison for Outbreak/Accelerant. With the extra energy from Prismatic Gem, playing 2-cost cards is much easier. It fits perfectly into our committed poison engine.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Outbreak, and Snakebite to scale damage. Prioritize efficient draw and mitigation; remove basic Strikes and Defends to thin the deck.

F20 [map] choose_map_node (option_index=0) | source=llm
  HP 59->59 | Gold 390->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which prioritizes non-combat nodes (Unknowns, Events, Treasures) over regular combats to preserve HP and avoid the high attrition of Act 2 hallway fights. My current deck is scaling-oriented (Poison/The Bomb) and benefits from avoiding chip damage before reaching shops where Meal Ticket can provide value.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 390->401 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F21 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 401->401 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F21 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 59->59 | Gold 401->401 | Deck 26->27
  deck_change: picked Mirage
  reasoning: Mirage offers incredible defensive scaling for heavy poison decks. Since our core engine relies on Noxious Fumes+, Deadly Poison, and Snakebite to stack poison, Mirage will routinely generate massive amounts of block for just 1 energy, providing the burst defense needed to survive multi-enemy fights and heavy-hitting bosses while the poison ticks down.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison safely, and use Mirage or Piercing Wail for burst mitigation. Needs more draw/deck thinning to reach engines faster.

F21 [map] choose_map_node (option_index=0) | source=llm
  HP 59->70 | Gold 401->401 | Deck 27->27
  deck_change: no deck change
  reasoning: With 401 gold and the Meal Ticket relic, visiting a shop now provides both significant scaling opportunities and a 15 HP heal. The Act 2 route intelligence strongly advises avoiding regular combats to preserve HP, and this shop allows me to convert my gold lead into the defensive stability or draw power the deck currently lacks.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes and The Bomb while blocking with Afterimage. Use the high gold reserve to hunt for card draw, dexterity, or 'Blur' to bridge the gap between defensive turns. Avoid basic attacks and minimize hallway combat to preserve HP for the boss.

F22 [shop] buy_relic (option_index=1) | source=plan
  HP 70->70 | Gold 401->230 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [1/6]: Passive Dexterity is fantastic for a deck utilizing multiple Defends, Backflip, and our newly acquired Dodge and Roll.

F22 [shop] remove_card_at_shop | source=plan
  HP 70->70 | Gold 230->230 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [2/6]: Removing a Strike increases the density of our poison engine and defensive tools.

F22 [card_select] select_deck_card (option_index=0) | source=llm
  HP 70->70 | Gold 230->155 | Deck 27->26
  deck_change: lost Strike
  reasoning: Strikes are completely obsolete in our dedicated poison scaling deck. Removing them increases the consistency of drawing our key poison and defensive tools.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Deadly Poison, and Accelerant to stack and multiply poison damage while defending with Afterimage, Backflip, and basic block. Remove Strikes at every opportunity to improve draw consistency. Look for more block and draw; skip generic attacks.

F22 [shop] buy_card (option_index=2) | source=plan
  HP 70->70 | Gold 155->104 | Deck 26->27
  deck_change: bought Backflip
  reasoning: Shop plan [3/6]: Premium draw and block card that fits perfectly into our survival plan.

F22 [shop] discard_potion (option_index=1) | source=plan
  HP 70->70 | Gold 104->104 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan: discard Flex Potion

F22 [shop] buy_potion (option_index=1) | source=plan
  HP 70->70 | Gold 104->55 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [5/6]: An emergency burst of card draw can be life-saving against status floods or for digging to a specific block card.

F22 [shop] buy_card (option_index=3) | source=plan
  HP 70->70 | Gold 55->7 | Deck 27->28
  deck_change: bought Dodge and Roll
  reasoning: Shop plan [6/6]: Double-dips on our new Oddly Smooth Stone Dexterity buff, providing highly efficient mitigation over two turns.

F22 [shop] close_shop_inventory | source=plan
  HP 70->70 | Gold 7->7 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F22 [shop] proceed | source=auto
  HP 70->70 | Gold 7->7 | Deck 28->28
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 7->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 7->16 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 16->16 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 68->68 | Gold 16->16 | Deck 28->28
  deck_change: no deck change
  reasoning: Capacitor does nothing without orb generation. Mangle is too expensive at 3 energy for a 1-turn strength down when we already have Piercing Wail. Pale Blue Dot is unlikely to trigger consistently in a deck without many zero-cost cards or massive draw. Skipping to keep the deck lean and draw our poison scaling faster.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks and clunky expensive cards.

F23 [map] choose_map_node (option_index=0) | source=auto
  HP 68->68 | Gold 16->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Elite

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 16->48 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 32 Gold

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 48->48 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Heart of Iron

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 48->48 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim relic: Bag of Marbles

F24 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 48->48 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F24 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 52->52 | Gold 48->48 | Deck 28->28
  deck_change: no deck change
  reasoning: The deck is firmly committed to a poison and stall strategy. Chaos and Focused Strike use Orbs which we have no synergy for, and Dagger Throw+, while providing cycle, costs energy and dilutes our draws for our core poison and block cards. Skipping to keep the deck as lean as possible at 28 cards.
  strategic_note: Committed poison/stall plan: stall with block and Piercing Wail while Noxious Fumes, Outbreak, and The Bomb deal damage. Needs card draw and block; avoid basic attacks and non-poison damage.

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 48->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Monster

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 48->63 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F25 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 63->63 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F25 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 39->39 | Gold 63->63 | Deck 28->28
  deck_change: no deck change
  reasoning: Our deck is currently committed to a poison and stall plan. We have 4 energy, so playing powers is not an issue, making Synthesis+ unnecessary. Boost Away adds negative status to our deck, and Snap+ is an off-synergy attack. Skipping to keep the deck lean and improve our chances of drawing our key poison and block cards.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Now with 4 energy, prioritize high-value block cards and card draw to consistently set up powers early; avoid unnecessary attacks.

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 63->63 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 39->39 | Gold 63->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 39->39 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim: The Courier

F26 [treasure] proceed | source=random
  HP 39->39 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 98->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Monster

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 98->109 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 109->109 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Cure All

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 109->109 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F27 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 35->35 | Gold 109->109 | Deck 28->29
  deck_change: picked Guiding Star
  reasoning: Guiding Star is an exceptionally efficient card for 1 energy, providing both solid frontload damage to handle immediate threats and drawing 2 cards to help cycle into our poison and defensive core.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Use premium draw like Guiding Star and Backflip to cycle fast. Need more efficient block and deck thinning.

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 35->35 | Gold 109->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Elite

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 109->139 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 139->139 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim relic: Twisted Funnel

F28 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 139->139 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F28 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 35->35 | Gold 139->139 | Deck 29->30
  deck_change: picked Guiding Star
  reasoning: Guiding Star provides premium card draw for 1 energy while dealing 12 damage, which helps us cycle through our 29-card deck to find crucial scaling powers like Noxious Fumes and Outbreak faster. With 4 energy from Prismatic Gem, we have the energy to support more card draw.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize high-value block cards and card draw to consistently set up powers early.

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 35->35 | Gold 139->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Only path: Monster

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 139->146 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 146->146 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 146->146 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F29 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 35->35 | Gold 146->146 | Deck 30->31
  deck_change: picked Calculated Gamble
  reasoning: Calculated Gamble is a premium hand-cycling tool that costs 0 energy. It will be incredibly valuable against the upcoming Act Boss (The Insatiable) to discard the 6 status cards added on Turn 1 and draw into our critical defensive and poison scaling cards.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize draw and hand manipulation to find core cards quickly.

F29 [map] choose_map_node (option_index=0) | source=llm
  HP 35->35 | Gold 146->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Taking the standard monster encounter at index 0 as it is the safer path toward the boss. With 35 HP and a defensive/poison-scaling deck, an Act 2 Elite (index 1) is extremely risky and could end the run before reaching the final rest site.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 146->153 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 153->153 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim potion: Fire Potion

F30 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 153->153 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F30 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 35->35 | Gold 153->153 | Deck 31->32
  deck_change: picked Glacier
  reasoning: With Prismatic Gem granting an extra energy, 2-cost cards are easier to play. Glacier provides immediate block and channels 2 Frost orbs, which will generate 4 passive block every turn. This perfectly fits our poison/stall strategy, giving us long-term mitigation to survive while our poison and The Bomb scale.
  strategic_note: Committed poison/stall plan: rely on Fumes, Outbreak, and The Bomb for damage. Use Glacier, Afterimage, and defensive skills to survive. Avoid adding more attacks; prioritize removals and block.

F30 [map] choose_map_node (option_index=0) | source=auto
  HP 35->35 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Unknown

F31 [event] choose_event_option (option_index=1) | source=llm
  HP 35->30 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: We have 35 HP and a rest site coming up next floor. Reaching deeper for 5 HP is a low cost to potentially get a much better reward than 35 gold.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Prioritize high-value block cards and card draw to consistently set up powers early.

F31 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 30->24 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Gold does not help against the upcoming Act 2 Boss since the next floor is a Rest Site. Losing 6 HP to reach deeper may yield a relic or immediate power upgrade that improves our chances against the boss.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.

F31 [event] choose_event_option (option_index=1) | source=llm
  HP 24->17 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Trading 7 HP for a relic is an excellent deal, especially for a stall/poison deck where fights frequently last 4+ turns. Pollinous Core will consistently provide extra draw in the boss fights. The HP loss is acceptable since the next floor is a guaranteed Rest Site before the Act 2 boss.
  strategic_note: Committed poison/stall plan: rely on Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Needs more block and card draw; avoid basic attacks.

F31 [event] choose_event_option (option_index=0) | source=auto
  HP 17->17 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 17->17 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 17->38 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: HP is critically low at 17/70 before an Act 2 boss. Healing is strictly necessary to survive the boss's opening turns while setting up our slow poison and stall engine.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F32 [rest_site] proceed | source=auto
  HP 38->38 | Gold 153->153 | Deck 32->32
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 153->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 153->228 | Deck 32->32
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 228->228 | Deck 32->32
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 35->35 | Gold 228->228 | Deck 32->33
  deck_change: picked Unmovable
  reasoning: Our deck is fully committed to a poison win condition, meaning we need reliable long-term block scaling to survive while poison ticks up. Unmovable provides massive block value each turn (especially with Mirage, Survivor, or Glacier) and is easy to put into play since we have 4 energy from Prismatic Gem.
  strategic_note: Committed poison plan: survive using Unmovable, Piercing Wail, and efficient block while stacking poison with Fumes and Deadly Poison. Use Well-Laid Plans to set up big Accelerant/Outbreak burst turns. Skip off-plan attacks and remove Strikes.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 35->63 | Gold 228->228 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 63->63 | Gold 228->228 | Deck 33->34
  deck_change: added Whistle
  reasoning: Our deck wins through Poison and stalling. A card that Stuns an enemy buys an entire free turn for Noxious Fumes and The Bomb to tick, completely neutralizing a big attack. With 4 energy, we can afford the 3 cost, making Whistle incredibly valuable for this strategy.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, Outbreak, and The Bomb for damage while blocking with Afterimage and defensive skills. Stun enemies on critical turns to buy time. Needs more block and card draw; avoid basic attacks.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 63->63 | Gold 228->228 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=2) | source=llm
  HP 63->63 | Gold 228->0 | Deck 34->34
  deck_change: no deck change
  reasoning: Following the recommended route to a monster node. While Act 2 hallways are dangerous, I have 90% HP and need to test my poison/stall engine against Act 2 scaling before hitting the shop. Meal Ticket and The Courier make shops high-value, so getting to the shop at r3 with maximum gold and a health buffer is the priority.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 228->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 63->63 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: The deck is heavily committed to a Poison scaling engine (Noxious Fumes+, Accelerant, Outbreak, Twisted Funnel). None of the offered cards (Doom mechanics or Shiv generation) synergize with our poison plan, and at 34 cards, we need to keep the deck lean to consistently draw our key defensive and scaling pieces.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Deadly Poison, and Accelerant to stack and multiply poison damage while defending with Afterimage, Backflip, and basic block. Remove Strikes at every opportunity to improve draw consistency. Look for more block and draw; skip generic attacks and narrow synergies.

F35 [map] choose_map_node (option_index=0) | source=llm
  HP 63->63 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Following the recommended route of prioritizing Unknown nodes in Act 3 to avoid combat attrition. With Meal Ticket and The Courier, I am heading toward a shop with 240 gold to maximize value and sustain.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for scaling damage while prioritizing Afterimage for block. Seeking card draw and high-quality defensive skills; with Meal Ticket and The Courier, shops are high-priority for both health sustain and discount scaling pieces.

F36 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 63->63 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: We are at 63/70 HP, so healing to full is mostly wasted and Royal Poison's permanent penalty is terrible. Picking a fight costs 11 HP for a random relic, which is an excellent trade, especially since we are about to enter a shop and trigger Meal Ticket to heal back to full anyway.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for scaling damage while prioritizing Afterimage for block. Seeking card draw and high-quality defensive skills; with Meal Ticket and The Courier, shops are high-priority for both health sustain and discount scaling pieces.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 63->52 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Continue

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 52->52 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=1) | source=llm
  HP 52->67 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Moving to the shop aligns with the Route Intelligence and maximizes relic synergies. With 240 gold and The Courier, I can afford multiple discounted items and the shop will restock. Additionally, Meal Ticket will heal me for 15 HP, which is crucial as I am currently at 52 HP (below the 60 HP safety threshold for Act 3).
  strategic_note: Committed poison/stall plan: use Noxious Fumes and The Bomb for damage while leveraging Afterimage for defense. Prioritize purchasing card draw, high-quality defensive skills, or poison accelerators at the shop to stabilize the scaling phase; avoid drafting basic attacks.

F37 [shop] remove_card_at_shop | source=plan
  HP 67->67 | Gold 240->240 | Deck 34->34
  deck_change: no deck change
  reasoning: Shop plan [1/5]: Removing a Strike increases the density of our poison cards and defensive tools, which is crucial against the upcoming boss.

F37 [card_select] select_deck_card (option_index=0) | source=llm
  HP 67->67 | Gold 240->160 | Deck 34->33
  deck_change: lost Strike
  reasoning: Strikes are completely obsolete damage that dilutes our critical poison scaling and block cards. Removing them improves the density of our core engine.
  strategic_note: Committed poison plan: stack poison and survive with efficient block while passive damage and Outbreak kills. Remove Strikes and prioritize draw/block.

F37 [shop] buy_card (option_index=4) | source=plan
  HP 67->67 | Gold 160->100 | Deck 33->34
  deck_change: bought Noxious Fumes
  reasoning: Shop plan [2/5]: Our primary win condition is passive poison scaling. Stacking another Noxious Fumes accelerates our AoE damage and powers up Mirage faster.

F37 [shop] buy_card (option_index=2) | source=plan
  HP 67->67 | Gold 100->60 | Deck 34->35
  deck_change: bought Snakebite
  reasoning: Shop plan [3/5]: Applies a huge chunk of poison and Retains so we can guarantee a strong Outbreak trigger or burst target setup on the exact turn we have Accelerant.

F37 [shop] buy_card (option_index=3) | source=plan
  HP 67->67 | Gold 60->40 | Deck 35->36
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [4/5]: Provides cheap block that scales wonderfully with Unmovable and triggers Afterimage twice.

F37 [shop] buy_potion (option_index=0) | source=plan
  HP 67->67 | Gold 40->0 | Deck 36->36
  deck_change: no deck change
  reasoning: Shop plan [5/5]: Adds 20 frontload damage, which could be necessary to quickly push an elite or deal with a dangerous hallway fight while poison ramps up.

F37 [shop] close_shop_inventory | source=plan
  HP 67->67 | Gold 0->0 | Deck 36->36
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F37 [shop] proceed | source=auto
  HP 67->67 | Gold 0->0 | Deck 36->36
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F37 [map] choose_map_node (option_index=0) | source=llm
  HP 67->67 | Gold 0->0 | Deck 36->36
  deck_change: no deck change
  reasoning: While the route intelligence suggests events, the strategic thread notes a need for card draw and defensive skills to round out the poison/stall engine. Taking a monster node here allows for a card reward to address these gaps before a potential streak of events. My HP is very high (67/70), so the risk of combat attrition is minimal.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw (Acrobatics, Backflip) and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 67->67 | Gold 0->13 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 67->67 | Gold 13->13 | Deck 36->36
  deck_change: no deck change
  reasoning: Claim potion: Cunning Potion

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 67->67 | Gold 13->13 | Deck 36->36
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 67->67 | Gold 13->13 | Deck 36->37
  deck_change: picked Piercing Wail+
  reasoning: Piercing Wail+ is a premium defensive tool, specifically countering the upcoming Act 3 Boss's massive 3-hit multi-attacks on turns 3, 6, and 9. It will keep us alive while our passive poison engine ramps up.
  strategic_note: Committed poison plan: rely on Noxious Fumes, Snakebite, and Accelerant to stack poison on the primary target. Defend heavily with Glacier, Unmovable, and Piercing Wail during dangerous multi-attack turns. Deck is large, avoid adding more cards unless they are premium draw or critical mitigation.

F38 [map] choose_map_node (option_index=0) | source=llm
  HP 67->67 | Gold 13->13 | Deck 37->37
  deck_change: no deck change
  reasoning: Following Act 3 Route Intelligence which prioritizes chaining events (Unknown nodes) over monster encounters to minimize health attrition. Although I have low gold, the poison/stall deck is vulnerable to Act 3 hallways, and preserving HP for the boss is the priority.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F39 [event] choose_event_option (option_index=0) | source=llm
  HP 67->67 | Gold 13->0 | Deck 37->37
  deck_change: no deck change
  reasoning: Our deck relies heavily on slow poison scaling, so dealing 150 or 300 damage in 3 turns is a significant risk of failing the damage check and facing lethal humiliation. Fighting the 75 HP dummy for a potion is extremely safe given our passive damage and guarantees we survive to the Elite.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 67->67 | Gold 13->13 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim potion: Gambler's Brew

F39 [event] choose_event_option (option_index=0) | source=auto
  HP 67->67 | Gold 13->13 | Deck 37->37
  deck_change: no deck change
  reasoning: Only option: Proceed

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 67->67 | Gold 13->0 | Deck 37->37
  deck_change: no deck change
  reasoning: Only path: Elite

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 13->42 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim gold: 29 Gold

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 42->42 | Deck 37->37
  deck_change: no deck change
  reasoning: Claim relic: Amethyst Aubergine

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 42->42 | Deck 37->37
  deck_change: no deck change
  reasoning: Open card reward

F40 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 62->62 | Gold 42->42 | Deck 37->38
  deck_change: picked Hologram
  reasoning: Hologram provides excellent utility for a 1-cost investment, allowing us to retrieve critical, situational tools from our discard pile like Piercing Wail for heavy multi-attack turns or Outbreak to finish off bosses. Since it exhausts, it won't permanently bloat our large deck.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison and Outbreak kills. Needs card draw; skip basic attacks and low-impact cards.

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 62->62 | Gold 42->42 | Deck 38->38
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 62->62 | Gold 42->74 | Deck 38->38
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 62->62 | Gold 74->74 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim: Pendulum

F41 [treasure] proceed | source=random
  HP 62->62 | Gold 74->74 | Deck 38->38
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=llm
  HP 62->62 | Gold 74->0 | Deck 38->38
  deck_change: no deck change
  reasoning: Act 3 Elites are high-risk for a stall-oriented deck relying on Noxious Fumes and The Bomb. Preserving 62 HP is critical for the final boss, and standard monster encounters are safer for gathering gold before the floor 47 shop where Courier and Meal Ticket provide high value.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, The Bomb, and Outbreak for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 74->88 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 88->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Open card reward

F42 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 62->62 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: None of these cards improve the core poison/stall engine. True Grit exhausts randomly which is too risky for our key combo pieces, Taunt's vulnerable is useless since we rely on poison and The Bomb, and Iteration is highly situational. Skipping to keep the deck leaner.
  strategic_note: Committed poison/stall plan: prioritize surviving with efficient block and Piercing Wails while Noxious Fumes and Outbreak scale for the kill. Keep deck lean by skipping generic additions; still looking for premium block or draw.

F42 [map] choose_map_node (option_index=1) | source=llm
  HP 62->62 | Gold 103->103 | Deck 38->38
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. Act 3 hallway fights can be very punishing for a slow-scaling poison/stall deck, so prioritizing events is the safest way to preserve HP for the final boss. The path ahead also includes a Shop where Meal Ticket will provide healing.
  strategic_note: Committed poison/stall plan: utilizing Noxious Fumes and The Bomb for damage while relying on Afterimage for block. Currently seeking additional card draw and high-quality defensive skills to bridge the gap during the scaling phase; avoid drafting basic attacks.

F43 [treasure] open_chest | source=random
  HP 62->62 | Gold 103->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Open chest

F43 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Claim: Ice Cream

F43 [treasure] proceed | source=random
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Proceed from treasure

F43 [map] choose_map_node (option_index=1) | source=llm
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Following the recommended route to a Rest Site. Act 3 Elites are extremely dangerous for a stall-oriented deck, and preserving HP for the boss is the priority according to expert knowledge. The Rest Site provides a safe transition to the upcoming Shop where I can leverage Meal Ticket and The Courier.
  strategic_note: Committed poison/stall plan: stack poison with Noxious Fumes and Outbreak while generating block through Afterimage and defensive skills. Prioritize finding more card draw and high-quality block to survive the setup phase; skip basic attacks and low-impact damage.

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=18, note_scope=run, note_triggers=all) | source=llm
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: upgraded Accelerant->Accelerant+
  reasoning: With 62/70 HP, resting would mostly overheal and waste the fire. We have a powerful engine upgrade available in Accelerant, which scales our poison damage drastically (from 2x to 3x triggers per turn), giving us the burst damage needed to quickly execute Act 3 elites and the boss.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, Accelerant, and Outbreak for rapidly scaling damage while prioritizing Afterimage and Mirage for block. Use well-laid plans to hold key defensive or poison cards. Avoid basic attacks.

F44 [rest_site] proceed | source=auto
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=llm
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Following the established Act 3 strategy of avoiding Elites to preserve health for the final boss. With 62 HP and a defensive poison/stall deck, the Unknown node offers a safer path towards the final Shop and Rest Site. The Elite at this stage poses a high risk of chip damage that could jeopardize the run's conclusion.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and The Bomb for damage while prioritizing Afterimage for block. Currently looking for additional card draw and high-quality defensive skills to survive the scaling phase; avoid drafting basic attacks.

F45 [event] choose_event_option (option_index=0) | source=llm
  HP 62->62 | Gold 136->136 | Deck 38->38
  deck_change: no deck change
  reasoning: Option 1 is not allowed, so I must accept serving as the Decider.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, Accelerant, and Outbreak for rapidly scaling damage while prioritizing Afterimage, Unmovable, and Mirage for block. Use well-laid plans to hold key defensive or poison cards. Avoid basic attacks. Maintain HP for the boss.

F45 [event] choose_event_option (option_index=1) | source=llm
  HP 62->62 | Gold 136->436 | Deck 38->39
  deck_change: added Regret
  reasoning: Taking 300 gold for a curse is an easy choice because the very next floor is a Shop. I can immediately pay to remove the Regret and use the remaining ~200+ net gold, enhanced by The Courier's 20% discount, to buy powerful relics or potions for the Act 3 Boss.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes, Accelerant, and Outbreak for rapidly scaling damage while prioritizing Afterimage, Unmovable, and Mirage for block. Use well-laid plans to hold key defensive or poison cards. Avoid basic attacks. Maintain HP for the boss.

F45 [event] choose_event_option (option_index=0) | source=auto
  HP 62->62 | Gold 436->436 | Deck 39->39
  deck_change: no deck change
  reasoning: Only option: Proceed

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 62->70 | Gold 436->436 | Deck 39->39
  deck_change: no deck change
  reasoning: Only path: Shop

F46 [shop] buy_card (option_index=3) | source=plan
  HP 70->70 | Gold 436->316 | Deck 39->40
  deck_change: bought Malaise
  reasoning: Shop plan [1/3]: Incredible mitigation tool, especially against multi-attackers like the Torch Head Amalgam.

F46 [shop] buy_relic (option_index=2) | source=plan
  HP 70->70 | Gold 316->134 | Deck 40->40
  deck_change: no deck change
  reasoning: Shop plan [2/3]: Synergizes perfectly with Malaise to provide huge permanent Strength loss and Weakness for free.

F46 [shop] remove_card_at_shop | source=plan
  HP 70->70 | Gold 134->134 | Deck 40->40
  deck_change: no deck change
  reasoning: Shop plan [3/3]: Removing the Regret curse to prevent taking massive chip damage from large hand sizes.

F46 [card_select] select_deck_card (option_index=0) | source=llm
  HP 70->70 | Gold 134->34 | Deck 40->39
  deck_change: lost Regret
  reasoning: Regret is a curse that drains HP based on hand size and dilutes our draws. Removing it is the obvious choice.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison, defend while passive poison kills. Needs block scaling and draw; remove curses/strikes.

F46 [shop] close_shop_inventory | source=llm
  HP 70->70 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F46 [shop] proceed | source=auto
  HP 70->70 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=18, note_scope=run, note_triggers=combat) | source=llm
  HP 70->70 | Gold 34->34 | Deck 39->39
  deck_change: upgraded Well-Laid Plans->Well-Laid Plans+
  reasoning: We are at full HP, so we must smith. Well-Laid Plans+ is a premier upgrade, allowing us to retain 2 cards instead of 1. This is critical in our 39-card deck for holding key defensive skills like Mirage, Piercing Wail, or Malaise until the exact turn the boss uses a heavy attack.
  strategic_note: Committed poison/stall plan: utilize Noxious Fumes and Accelerant for scaling damage, prioritizing Afterimage, Mirage, and Well-Laid Plans to hold defensive answers for big attacks.

F47 [rest_site] proceed | source=auto
  HP 70->70 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 34->0 | Deck 39->39
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [card_select] select_deck_card (option_index=1) | source=llm
  HP 55->55 | Gold 34->0 | Deck 39->39
  deck_change: no deck change
  reasoning: Retrieving Deadly Poison to push the Queen's Poison to 42. With Accelerant(2), 42 * 3 = 126 damage at the start of her turn, which is exact lethal and ends the combat.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 55->55 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 55->0 | Gold 34->34 | Deck 39->39
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (8 replays)
[Selected: elite] Phrog Parasite (F8, elite)
## Combat Replay: vs Phrog Parasite (Floor 8, elite)
Relics: Ring of the Snake, Lead Paperweight
Deck (19): Defend x5, Strike x5, Ascender's Bane, Backflip, Dagger Spray, Neutralize+, Noxious Fumes, Outbreak, Survivor, The Bomb, Well-Laid Plans
Enemies: Phrog Parasite HP=62/62

### Round 1
Intent: Phrog Parasite: StatusCard(3)
  The Bomb
    energy -2 | +The Bomb(3)
  Outbreak
    energy -1 | +Outbreak(11)
  turn_end
    The Bomb(3→2)

### Round 2
Agent plan (hypothesis): The Bomb is ticking down. Prepare to transition the boss at a favorable time.
Intent: Phrog Parasite: Attack(4x4=16)
  Defend
    energy -1 | block +5
  Dagger Spray
    energy -1 | enemy_deltas: Phrog Parasite: hp -8
  Survivor
    energy -1 | block +8
  Strike
  turn_end
    The Bomb(2→1)

### Round 3
Intent: Phrog Parasite: StatusCard(3)
  Neutralize+ -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: hp -4, +Weak(2)
  Strike -> Phrog Parasite[0]
    energy -1 | enemy_deltas: Phrog Parasite: hp -6
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end
  Defend

### Round 4
Agent plan (hypothesis): Use Dagger Spray to kill the Phrog next turn—if it kills the Phrog on the first hit, the second hit will hit the newly spawned Wrigglers! Retain key AoE or setup cards if possible.
Intent: Phrog Parasite: Attack(3x4=12)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
  Backflip

### Round 5
Agent plan (hypothesis): If we find Purity, use it on Infections. Then Dagger Spray and Survivor.
Intent: Phrog Parasite: StatusCard(3)
  Backflip
    energy -1 | block +5
  Colorless Potion
  Flash of Steel
  Flash of Steel -> Phrog Parasite[0]
    enemy_deltas: Phrog Parasite: DIED
  Dagger Spray
    energy -1 | enemy_deltas: Wriggler: hp -8
  Survivor
    energy -1 | block +8
  Infection
  turn_end
  Strike

### Round 6
Intent: Wriggler: Buff, StatusCard(1), Wriggler: Attack(6)
  Neutralize+ -> Wriggler[0]
  Strike -> Wriggler[0]
    energy -1 | -Outbreak | -Well-Laid Plans | -Noxious Fumes | enemy_deltas: Wriggler: DIED
## Combat Analytics: Phrog Parasite (WIN - 6 rounds)

Cards played (with descriptions):
  The Bomb "At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 2 plays, 16 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Strike "Deal 6 damage." -> 2 plays, 6 dmg
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Flash of Steel "Deal 5 damage. Draw 1 card." -> 1 plays

Enemy power timeline:
  Infested: R1:4 -> R2:4 -> R3:4 -> R4:4 -> R5:4 -> R6:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:2
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-

Unattributed damage (power/passive effects): 4
  Per round: R5:4
Comparator (recent same-enemy comparator):
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

[Selected: elite] Byrdonis (F12, elite)
## Combat Replay: vs Byrdonis (Floor 12, elite)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat
Deck (21): Defend x5, Strike x5, Ascender's Bane, Backflip, Dagger Spray, Deadly Poison, Echoing Slash, Neutralize+, Noxious Fumes+, Outbreak, Survivor, The Bomb, Well-Laid Plans
Enemies: Byrdonis HP=81/84

### Round 1
Agent plan (hypothesis): Horn Cleat will provide 14 Block next turn. Use Deadly Poison to stack poison. Retain high value cards.
Intent: Byrdonis: Attack(17)
  Dexterity Potion
    +Dexterity(2)
  Neutralize+ -> Byrdonis[0]
    enemy_deltas: Byrdonis: hp -4, +Weak(2)
  Defend
    energy -1 | block +7
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Outbreak
    energy -1 | +Outbreak(11)
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Deadly Poison

### Round 2
Agent plan (hypothesis): Hold the Energy Potion for a burst turn or when needed for emergency block.
Intent: Byrdonis: Attack(3x3=9)
  The Bomb
    energy -2 | +The Bomb(3)
  Deadly Poison -> Byrdonis[0]
    energy -1 | enemy_deltas: Byrdonis: +Poison(5)
  turn_end
    The Bomb(3→2)
  Defend

### Round 3
Agent plan (hypothesis): The Bomb counts down to 1 this turn and will explode at the end of next turn. We just need to survive one more round.
Intent: Byrdonis: Attack(19)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Survivor
    energy -1 | block +10
  Dagger Spray
  Defend
    energy -1 | block +7
  turn_end
    The Bomb(2→1)
  Defend

### Round 4
Agent plan (hypothesis): The Bomb explodes this turn. Next turn, poison will tick down their remaining HP.
Intent: Byrdonis: Attack(6x3=18)
  Backflip
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  turn_end
  Defend
## Combat Analytics: Byrdonis (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  Defend "Gain 7 Block." -> 4 plays, 28 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  The Bomb "At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 1 plays, +5 poison
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Survivor "Gain 10 Block. Discard 1 card." -> 1 plays, 10 block
  Backflip "Gain 7 Block. Draw 2 cards." -> 1 plays, 7 block

Poison stacks applied per card:
  Deadly Poison: 5 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:4 -> R4:6
  Strength: R1:- -> R2:1 -> R3:2 -> R4:3
  Territorial: R1:1 -> R2:1 -> R3:1 -> R4:1
  Weak: R1:- -> R2:1 -> R3:- -> R4:-

[Selected: boss] Ceremonial Beast (F17, boss)
## Combat Replay: vs Ceremonial Beast (Floor 17, boss)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket
Deck (24): Defend x5, Strike x5, Deadly Poison x2, Afterimage, Ascender's Bane, Backflip, Dagger Spray, Echoing Slash, Neutralize+, Noxious Fumes+, Outbreak, Piercing Wail, Survivor, The Bomb, Well-Laid Plans
Enemies: Ceremonial Beast HP=249/252

### Round 1
Agent plan (hypothesis): Energy Potion saved for a big block/setup turn.
Intent: Ceremonial Beast: Buff
  Outbreak
    energy -1 | +Outbreak(11)
  Deadly Poison -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: +Poison(5)
  Deadly Poison -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: Poison(5→10)
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Intent: Ceremonial Beast: Attack(18), Buff
  Backflip
    energy -1 | block +5
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Strike -> Ceremonial Beast[0]
    energy -1 | enemy_deltas: Ceremonial Beast: hp -6
  turn_end

### Round 3
Agent plan (hypothesis): The Bomb will detonate in 3 turns. Keep blocking until the stun.
Intent: Ceremonial Beast: Attack(20), Buff
  Energy Potion
    energy +2
  Poison Potion -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: Poison(11→17)
  Neutralize+ -> Ceremonial Beast[0]
    enemy_deltas: Ceremonial Beast: hp -4, +Weak(2)
  The Bomb
    energy -2 | +The Bomb(3)
  Echoing Slash
    energy -1 | enemy_deltas: Ceremonial Beast: hp -10
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
    The Bomb(3→2)

### Round 4
Agent plan (hypothesis): The boss will stun soon. Keep surviving.
Intent: Ceremonial Beast: Attack(16), Buff
  Afterimage
    energy -1 | +Afterimage(1)
  Well-Laid Plans
    energy -1 | block +1 | +Well-Laid Plans(1)
  Defend
    energy -1 | block +6
  turn_end
    The Bomb(2→1)
  Strike

### Round 5
Intent: Ceremonial Beast: Stun
  Dagger Spray
    energy -1 | block +1 | enemy_deltas: Ceremonial Beast: hp -8
  Strike -> Ceremonial Beast[0]
    energy -1 | block +1 | enemy_deltas: Ceremonial Beast: hp -6
  Strike -> Ceremonial Beast[0]
    energy -1 | block +1 | enemy_deltas: Ceremonial Beast: hp -6
  turn_end
  Piercing Wail

### Round 6
Agent plan (hypothesis): Use remaining energy on damage or poison to accelerate the kill.
Agent plan (hypothesis): Boss is almost dead.
Intent: Ceremonial Beast: Debuff
  Backflip
    energy -1 | block +6
  Deadly Poison -> Ceremonial Beast[0]
    energy -1 | block +1 | enemy_deltas: Ceremonial Beast: Poison(23→28)
  Echoing Slash
    energy -1 | block +1 | enemy_deltas: Ceremonial Beast: hp -10
  turn_end
  The Bomb

### Round 7
Agent plan (hypothesis): Boss defeated.
Intent: Ceremonial Beast: Attack(15)
  Strike -> Ceremonial Beast[0]
    energy -1 | -Outbreak | -Noxious Fumes | -Afterimage | -Well-Laid Plans | -Ringing | enemy_deltas: Ceremonial Beast: DIED
## Combat Analytics: Ceremonial Beast (WIN - 7 rounds)

Cards played (with descriptions):
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 3 plays, 1 block, +15 poison
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 11 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Strike "Deal 6 damage." -> 4 plays, 18 dmg, 2 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 4 dmg
  The Bomb "At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays
  Echoing Slash "Deal 10 damage to ALL enemies. Repeat this effect for each enemy killed." -> 2 plays, 20 dmg, 1 block
  Defend "Gain 5 Block." -> 3 plays, 16 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays, 1 block
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg, 1 block

Poison stacks applied per card:
  Deadly Poison: 15 stacks
  Poison Potion: 6 stacks

Enemy power timeline:
  Plow: R1:- -> R2:150 -> R3:150 -> R4:150 -> R5:- -> R6:- -> R7:-
  Poison: R1:- -> R2:9 -> R3:11 -> R4:19 -> R5:21 -> R6:23 -> R7:30
  Strength: R1:- -> R2:- -> R3:2 -> R4:4 -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:-

[Selected: elite] Infested Prism (F24, elite)
## Combat Replay: vs Infested Prism (Floor 24, elite)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket, Prismatic Gem, Oddly Smooth Stone
Deck (28): Defend x5, Strike x4, Backflip x2, Deadly Poison x2, Accelerant, Afterimage, Ascender's Bane, Dagger Spray, Dodge and Roll, Echoing Slash, Mirage, Neutralize+, Noxious Fumes+, Outbreak, Piercing Wail, Snakebite, Survivor, The Bomb, Well-Laid Plans
Enemies: Infested Prism HP=197/200

### Round 1
Agent plan (hypothesis): If we don't draw Neutralize+, we will play Noxious Fumes+, Defend, and Survivor to reach 21 block (taking 1 damage). Save Piercing Wail for the multi-attack on Turn 3.
Agent plan (hypothesis): Ascender's Bane exhausts naturally.
Intent: Infested Prism: Attack(22)
  Swift Potion
  Strike -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6
  Dagger Spray
    energy -1 | enemy_deltas: Infested Prism: hp -8
  Backflip
    energy -1 | block +6
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Survivor
    energy -1 | block +9
  Defend
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Retain Snakebite.
Intent: Infested Prism: Attack(16), Defend
  Afterimage
    energy -1 | +Afterimage(1)
  Echoing Slash
    block +1 | enemy_deltas: Infested Prism: hp -10
  Well-Laid Plans
    energy -1 | block +1 | +Well-Laid Plans(1)
  Backflip
    energy -1 | block +7
  Outbreak
    energy -1 | block +1 | +Outbreak(11)
  turn_end
  Dodge and Roll

### Round 3
Agent plan (hypothesis): Strike is retained to guarantee Vital Spark energy on Turn 4.
Intent: Infested Prism: Attack(9x3=27)
  Touch of Insanity -> Infested Prism[0]
  Snakebite
  Neutralize+ -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: block -4, +Weak(2)
  Snakebite -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: Poison(5→12)
  Deadly Poison -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: hp -2, block -9, Poison(12→17)
  Mirage
    energy -1 | block +19 | exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 17 Block) Exhaust.
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(5)
  Defend
    energy -1 | block +7
  turn_end
  Strike

### Round 4
Agent plan (hypothesis): Enemy attacks for 26 next turn. Vital Spark will be available again.
Intent: Infested Prism: Buff, Defend
  Strike -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: hp -6
  Strike -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: hp -6
  Deadly Poison -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: Poison(19→24)
  turn_end
  Defend

### Round 5
Agent plan (hypothesis): If we draw Neutralize, use it to apply Weak! Then block the rest.
Agent plan (hypothesis): Poison is huge, Accelerant will melt the enemy next turn.
Intent: Infested Prism: Attack(26)
  Backflip
    energy -1 | block +7
  Strike -> Infested Prism[0]
    energy -1 | block +1 | enemy_deltas: Infested Prism: block -6
  Snakebite -> Infested Prism[0]
    block +1 | enemy_deltas: Infested Prism: Poison(26→33)
  Accelerant
    energy -1 | block +1 | +Accelerant(1)
  Piercing Wail
    energy -1 | block +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Infested Prism: Strength(4→-2), +Piercing Wail(6)
  turn_end
  Dodge and Roll

### Round 6
Intent: Infested Prism: Attack(20), Defend
  Neutralize+ -> Infested Prism[0]
    energy +1 | block +1 | enemy_deltas: Infested Prism: hp -4, +Weak(2)
  Backflip
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(5)
  turn_end
  Deadly Poison
## Combat Analytics: Infested Prism (WIN - 6 rounds)

Cards played (with descriptions):
  Strike "Deal 6 damage." -> 4 plays, 18 dmg, 3 block
  Dagger Spray "Deal 4 damage to ALL enemies twice." -> 1 plays, 8 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 4 plays, 27 block
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Echoing Slash "Deal 10 damage to ALL enemies. Repeat this effect for each enemy killed." -> 1 plays, 10 dmg, 1 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays, 1 block
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays, 1 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg, 2 block
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, 2 block, +14 poison
  Deadly Poison "Apply 5 Poison." -> 2 plays, 2 dmg, 2 block, +10 poison
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 18 Block) Exhaust." -> 1 plays, 19 block, EXHAUST
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 2 plays, 12 block
  Defend "Gain 6 Block." -> 2 plays, 14 block
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 1 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST

Active powers: Dexterity(1)

Poison stacks applied per card:
  Snakebite: 14 stacks
  Deadly Poison: 10 stacks

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:5 -> R4:19 -> R5:26 -> R6:34
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:4
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Infested Prism (Floor 25, elite)
Relics: Ring of the Snake, Neow's Torment, The Chosen Cheese, Vexing Puzzlebox, Very Hot Cocoa
Deck (27): Defend x5, Strike x4, Poisoned Stab x2, Acrobatics, Backflip, Bubble Bubble, Burst, Dagger Spray+, Dagger Throw, Footwork+, Haze, Neow's Fury, Neutralize+, Outbreak, Predator+, Prepared+, Snakebite, Survivor, Untouchable+
Enemies: Infested Prism HP=200/200

### Round 1
Intent: Infested Prism: Attack(22)
  Neutralize+ -> Infested Prism[0]
    energy +1 | enemy_deltas: Infested Prism: hp -4, +Weak(2)
  Outbreak
    energy -1 | +Outbreak(11)
  Escape Plan
  Dexterity Potion
    +Dexterity(2)
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Defend
    energy -1 | block +7
  Dagger Spray+
    energy -1 | enemy_deltas: Infested Prism: hp -12
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  turn_end

### Round 2
Intent: Infested Prism: Attack(12), Defend
  Footwork+
    energy -1 | Dexterity(2→5)
  Poisoned Stab -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -6, +Poison(3)
  Untouchable+
    energy -2 | block +13
  turn_end

### Round 3
Intent: Infested Prism: Attack(9x3=27)
  Burst
    energy -1 | +Burst(1)
  Backflip
    energy -1 | block +20 | -Burst
  Survivor
    energy -1 | block +13
  Haze
  turn_end
    enemy_deltas: Infested Prism: Poison(2→6)

### Round 4
Intent: Infested Prism: Buff, Defend
  Touch of Insanity
  Predator+
  Predator+ -> Infested Prism[0]
    energy +1 | +Draw Cards Next Turn(2) | enemy_deltas: Infested Prism: hp -20
  Snakebite -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: hp -11, Poison(5→12)
  Dagger Throw -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -9
  Untouchable+
  Strike -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: hp -6
  turn_end

### Round 5
Intent: Infested Prism: Attack(26)
  Poisoned Stab -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: block -6, Poison(11→14)
  Dagger Spray+
    energy -1 | enemy_deltas: Infested Prism: block -12
  Defend
    energy -1 | block +10
  turn_end

### Round 6
Intent: Infested Prism: Attack(20), Defend
  Predator+ -> Infested Prism[0]
    energy +1 | +Draw Cards Next Turn(2) | enemy_deltas: Infested Prism: hp -20
  Burst
    energy -1 | +Burst(1)
  Escape Plan
    block +8 | -Burst
  Defend
    energy -1 | block +10
  Snakebite -> Infested Prism[0]
    energy -2 | enemy_deltas: Infested Prism: Poison(13→20)
  turn_end

### Round 7
Intent: Infested Prism: Attack(13x3=39)
  Neutralize+ -> Infested Prism[0]
    enemy_deltas: Infested Prism: block -4, +Weak(2)
  Bubble Bubble -> Infested Prism[0]
    energy -1 | enemy_deltas: Infested Prism: block -11, Poison(19→28)
  Backflip
    energy -1 | block +10
  Fire Potion -> Infested Prism[0]
    enemy_deltas: Infested Prism: hp -19, block -1
  Defend
    energy -1 | block +10
  turn_end
## Combat Analytics: Infested Prism (WIN - 7 rounds)

Cards played (with descriptions):
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays, 8 block
  Defend "Gain 7 Block." -> 6 plays, 51 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 2 plays, 12 dmg
  Strike "Deal 6 damage." -> 3 plays, 18 dmg
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 6 dmg, +6 poison
  Untouchable+ "Sly. Gain 13 Block." -> 1 plays, 13 block
  Burst "This turn, your next Skill is played an extra time." -> 2 plays
  Backflip "Gain 10 Block. Draw 2 cards." -> 2 plays, 30 block
  Survivor "Gain 13 Block. Discard 1 card." -> 1 plays, 13 block
  Predator+ "Deal 20 damage. Next turn, draw 2 cards." -> 2 plays, 40 dmg
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, 11 dmg, +14 poison
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg
  Bubble Bubble "If the enemy has Poison, apply 9 Poison." -> 1 plays, +9 poison

Poison stacks applied per card:
  Snakebite: 14 stacks
  Bubble Bubble: 9 stacks
  Poisoned Stab: 6 stacks
  turn_end: 4 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:2 -> R4:5 -> R5:11 -> R6:13 -> R7:19
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:4 -> R7:4
  Vital Spark: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-

[Selected: elite] Entomancer (F28, elite)
## Combat Replay: vs Entomancer (Floor 28, elite)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket, Prismatic Gem, Oddly Smooth Stone, Bag of Marbles, The Courier
Deck (29): Defend x5, Strike x4, Backflip x2, Deadly Poison x2, Accelerant, Afterimage, Ascender's Bane, Dagger Spray, Dodge and Roll, Echoing Slash, Guiding Star, Mirage, Neutralize+, Noxious Fumes+, Outbreak, Piercing Wail, Snakebite, Survivor, The Bomb, Well-Laid Plans
Enemies: Entomancer HP=142/145

### Round 1
Agent plan (hypothesis): Hold Accelerant. Enemy is Weak for 2 turns.
Intent: Entomancer: Attack(3x7=21)
  Backflip
    energy -1 | block +6
  Neutralize+ -> Entomancer[0]
    enemy_deltas: Entomancer: hp -6, +Weak(2)
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  Defend
    energy -1 | block +6
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  turn_end
  Accelerant

### Round 2
Intent: Entomancer: Attack(13)
  Deadly Poison -> Entomancer[0]
    energy -1 | enemy_deltas: Entomancer: +Poison(5)
  Snakebite -> Entomancer[0]
    energy -2 | enemy_deltas: Entomancer: Poison(5→12)
  Accelerant
    energy -1 | +Accelerant(1)
  turn_end
  The Bomb

### Round 3
Intent: Entomancer: Buff
  Afterimage
    energy -1 | +Afterimage(1)
  The Bomb
    energy -2 | block +1 | +The Bomb(3)
  turn_end
    The Bomb(3→2)
  Defend

### Round 4
Agent plan (hypothesis): Enemy takes poison damage and bomb will go off next turn.
Intent: Entomancer: Attack(4x7=28)
  Deadly Poison -> Entomancer[0]
    energy -1 | block +1 | enemy_deltas: Entomancer: Poison(8→13)
  Mirage
    energy -1 | block +15 | exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 13 Block) Exhaust.
  Backflip
    energy -1 | block +7
  Survivor
    energy -1 | block +9
  Ascender's Bane
  turn_end
    The Bomb(2→1)
  Guiding Star

### Round 5
Intent: Entomancer: Attack(19)
  Deadly Poison -> Entomancer[0]
    energy -1 | block +1 | enemy_deltas: Entomancer: Poison(11→16)
  Piercing Wail
    energy -1 | block +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Entomancer: Strength(1→-5), +Piercing Wail(6)
  Noxious Fumes+
    energy -1 | block +1 | +Noxious Fumes(3)
  Outbreak
    energy -1 | block +1 | +Outbreak(11)
  turn_end
  Guiding Star
## Combat Analytics: Entomancer (WIN - 5 rounds)

Cards played (with descriptions):
  Backflip "Gain 6 Block. Draw 2 cards." -> 2 plays, 13 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 6 dmg
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 1 plays, 5 block
  Defend "Gain 6 Block." -> 1 plays, 6 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 3 plays, 2 block, +15 poison
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, +7 poison
  Accelerant "Poison is triggered 1 additional time." -> 1 plays
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  The Bomb "At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays, 1 block
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 14 Block) Exhaust." -> 1 plays, 15 block, EXHAUST
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 1 block
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays, 1 block

Active powers: Dexterity(1)

Poison stacks applied per card:
  Deadly Poison: 15 stacks
  Snakebite: 7 stacks

Enemy power timeline:
  Personal Hive: R1:1 -> R2:1 -> R3:1 -> R4:2 -> R5:2
  Poison: R1:- -> R2:- -> R3:10 -> R4:8 -> R5:11
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1
  Vulnerable: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Entomancer (Floor 30, elite)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese
Deck (32): Defend x5, Strike x5, Dagger Throw x2, Leg Sweep x2, Accuracy, Backstab, Blade Dance, Cloak and Dagger+, Dagger Spray, Dodge and Roll, Expertise+, Finesse, Lantern Key, Leading Strike, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Entomancer HP=145/145

### Round 1
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

[Selected: boss] The Insatiable (F33, boss)
## Combat Replay: vs The Insatiable (Floor 33, boss)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket, Prismatic Gem, Oddly Smooth Stone, Bag of Marbles, The Courier, Twisted Funnel, Pollinous Core
Deck (32): Defend x5, Strike x4, Backflip x2, Deadly Poison x2, Guiding Star x2, Accelerant, Afterimage, Ascender's Bane, Calculated Gamble, Dagger Spray, Dodge and Roll, Echoing Slash, Glacier, Mirage, Neutralize+, Noxious Fumes+, Outbreak, Piercing Wail, Snakebite, Survivor, The Bomb, Well-Laid Plans
Enemies: The Insatiable HP=318/321

### Round 1
Intent: The Insatiable: Buff, StatusCard(6)
  Strength Potion
    +Strength(2)
  Fire Potion -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -20
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Accelerant
    energy -1 | +Accelerant(1)
  Dodge and Roll
    energy -1 | block +5 | +Block Next Turn(5)
  Strike -> The Insatiable[0]
    energy -1 | enemy_deltas: The Insatiable: hp -12
  Neutralize+ -> The Insatiable[0]
    enemy_deltas: The Insatiable: hp -9, +Weak(2)
  turn_end
  Defend

### Round 2
Agent plan (hypothesis): Look for Noxious Fumes and Outbreak to start stacking poison.
Intent: The Insatiable: Attack(6x2=12)
  Backflip
    energy -1 | block +6
  Afterimage
    energy -1 | +Afterimage(1)
  Calculated Gamble
    block +1 | exhausted: Calculated Gamble [0]: Discard your Hand, then draw that many cards. Exhaust.
  Noxious Fumes+
    energy -1 | block +1 | +Noxious Fumes(3)
  Deadly Poison -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: Poison(2→7)
  turn_end
  Dagger Spray

### Round 3
Intent: The Insatiable: Attack(28)
  Backflip
    energy -1 | block +7
  Outbreak
    energy -1 | block +1 | +Outbreak(11)
  Survivor
    energy -1 | block +9
  Strike
  Defend
    energy -1 | block +7
  turn_end
  Defend

### Round 4
Agent plan (hypothesis): Retain Piercing Wail for the multi-attack next turn. Keep pushing poison.
Intent: The Insatiable: Buff
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  Deadly Poison -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: Poison(9→14)
  Snakebite -> The Insatiable[0]
    energy -2 | block +1 | enemy_deltas: The Insatiable: hp -11, Poison(14→21)
  turn_end
    exhausted: Calculated Gamble [0]: Discard your Hand, then draw that many cards. Exhaust.
  Piercing Wail

### Round 5
Intent: The Insatiable: Attack(10x2=20)
  The Bomb
    energy -2 | block +1 | +The Bomb(3)
  Mirage
    energy -1 | block +24 | exhausted: Mirage [1]: Gain Block equal to Poison on ALL enemies. (Gain 22 Block) Exhaust.
  Dodge and Roll
    energy -1 | block +6 | +Block Next Turn(5)
  turn_end
    The Bomb(3→2)
  Piercing Wail

### Round 6
Agent plan (hypothesis): Sandpit is managed. Poison is extremely high (ticks for 50 next turn due to Accelerant). We just need to survive.
Intent: The Insatiable: Attack(10x2=20)
  Piercing Wail
    energy -1 | block +1 | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: The Insatiable: Strength(2→-4), +Piercing Wail(6)
  Frantic Escape
    energy -2 | block +1 | enemy_deltas: The Insatiable: Sandpit(1→2)
  Frantic Escape
    energy -1 | block +1 | enemy_deltas: The Insatiable: Sandpit(2→3)
  turn_end
    The Bomb(2→1)
  Defend

### Round 7
Agent plan (hypothesis): Boss is dead.
Intent: The Insatiable: Attack(30)
  Backflip
    energy -1 | block +7
  Dagger Spray
    energy -1 | block +1 | enemy_deltas: The Insatiable: hp -12
  Deadly Poison -> The Insatiable[0]
    energy -1 | block +1 | enemy_deltas: The Insatiable: Poison(24→29)
  Defend
    energy -1 | block +7
  turn_end
  Defend
## Combat Analytics: The Insatiable (WIN - 7 rounds)

Cards played (with descriptions):
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Accelerant "Poison is triggered 1 additional time." -> 1 plays
  Dodge and Roll "Gain 5 Block. Next turn, gain 5 Block." -> 2 plays, 11 block
  Strike "Deal 8 damage." -> 1 plays, 12 dmg
  Neutralize+ "Deal 6 damage. Apply 2 Weak." -> 1 plays, 9 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 3 plays, 20 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Calculated Gamble "Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 1 block, EXHAUST
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays, 1 block
  Deadly Poison "Apply 5 Poison." -> 3 plays, 3 block, +15 poison
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays, 1 block
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Defend "Gain 6 Block." -> 2 plays, 14 block
  Frantic Escape "Get farther away. Increase Sandpit by 1. Increase the cost of this card by 1." -> 3 plays, 3 block
  Snakebite "Retain. Apply 7 Poison." -> 1 plays, 11 dmg, 1 block, +7 poison
  The Bomb "At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays, 1 block
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 23 Block) Exhaust." -> 1 plays, 24 block, EXHAUST
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 1 block, EXHAUST
  Dagger Spray "Deal 6 damage to ALL enemies twice." -> 1 plays, 12 dmg, 1 block

Active powers: Dexterity(1)

Poison stacks applied per card:
  Deadly Poison: 15 stacks
  Snakebite: 7 stacks

Enemy power timeline:
  Poison: R1:4 -> R2:2 -> R3:8 -> R4:9 -> R5:22 -> R6:23 -> R7:24
  Sandpit: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:2 -> R6:1 -> R7:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2
  Vulnerable: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
Comparator (recent same-enemy comparator):
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
Intent: The Insatiable: Buff
  Backflip+
    energy -1 | block +12
  Predator+ -> The Insatiable[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: The Insatiable: hp -20
  turn_end
  Backflip+

### Round 5
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

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F40, elite)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 40, elite)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket, Prismatic Gem, Oddly Smooth Stone, Bag of Marbles, The Courier, Twisted Funnel, Pollinous Core, Tanx's Whistle, Gorget
Deck (37): Defend x5, Strike x3, Backflip x2, Deadly Poison x2, Guiding Star x2, Snakebite x2, Accelerant, Afterimage, Ascender's Bane, Calculated Gamble, Cloak and Dagger, Dagger Spray, Dodge and Roll, Echoing Slash, Glacier, Mirage, Neutralize+, Noxious Fumes, Noxious Fumes+, Outbreak, Piercing Wail, Piercing Wail+, Survivor, The Bomb, Unmovable, Well-Laid Plans, Whistle
Enemies: Flail Knight HP=98/101, Spectral Knight HP=90/93, Magi Knight HP=79/82

### Round 1
Agent plan (hypothesis): Spectral Knight applies Hex, focus it down first. Magi Knight Turn 5 nuke is coming.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Dexterity Potion
    Dexterity(1→3)
  Noxious Fumes
    energy -1 | +Noxious Fumes(2)
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Spectral Knight[1]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Spectral Knight: hp -6
  Survivor
    energy -1 | block +11
  Strike
  turn_end
    block +4
  Dodge and Roll

### Round 2
Agent plan (hypothesis): We have 1 energy left to spend on the newly drawn hand.
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Debuff
  Afterimage
    energy -1 | +Afterimage(1)
  Unmovable
    energy -2 | block +1 | +Unmovable(1)
  Calculated Gamble
    block +1 | exhausted: Shiv [0]: Ethereal. Deal 4 damage. Exhaust.
  Defend
    energy -1 | block +17
  turn_end
    block +3

### Round 3
Intent: Flail Knight: Attack(12x2=24), Spectral Knight: Attack(3x3=9), Magi Knight: Attack(10)
  Mirage
    energy -1 | block +43 | exhausted: Strike [1]: Ethereal. Deal 6 damage.
  Defend
    energy -1 | block +9
  The Bomb
    energy -2 | block +1 | +The Bomb(3)
  turn_end
    block +2

### Round 4
Intent: Flail Knight: Attack(18), Spectral Knight: Attack(15), Magi Knight: Defend
  Piercing Wail
    energy -1 | block +1 | exhausted: Strike [1]: Ethereal. Deal 6 damage. | enemy_deltas: Flail Knight: Strength(3→-3), +Piercing Wail(6); Spectral Knight: +Strength(-6), +Piercing Wail(6); Magi Knight: +Strength(-6), +Piercing Wail(6)
  Neutralize -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -3, +Weak(1)
  Whistle -> Spectral Knight[1]
    energy -3 | block +1 | exhausted: Whistle [3]: Ethereal. Deal 33 damage. Stun the enemy. Exhaust. | enemy_deltas: Spectral Knight: hp -33
  turn_end
    block +1

### Round 5
Agent plan (hypothesis): Retain Defend with Well-Laid Plans.
Intent: Flail Knight: Attack(18), Spectral Knight: Attack(15), Magi Knight: Attack(35)
  Deadly Poison -> Magi Knight[2]
    energy -1 | block +1 | enemy_deltas: Magi Knight: Poison(8→13)
  Glacier
    energy -2 | block +24
  Piercing Wail
    energy -1 | block +1 | enemy_deltas: Flail Knight: Strength(3→-3), +Piercing Wail(6); Spectral Knight: +Strength(-6), +Piercing Wail(6); Magi Knight: +Strength(-6), +Piercing Wail(6)
  turn_end
  Defend

### Round 6
Agent plan (hypothesis): Fight over.
Intent: Flail Knight: Buff
  Strike -> Flail Knight[0]
    energy -1 | block +1 | enemy_deltas: Flail Knight: hp -6
  Backflip
    energy -1 | block +17
  Strike -> Flail Knight[0]
    energy -1 | block -18 | -Dexterity | -Noxious Fumes | -Well-Laid Plans | -Afterimage | -Unmovable | enemy_deltas: Flail Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 6 rounds)

Cards played (with descriptions):
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Cloak and Dagger "Gain 9 Block. Add 1 Shiv into your Hand." -> 1 plays, 9 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 1 plays, 6 dmg, EXHAUST
  Survivor "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Afterimage "Ethereal. Whenever you play a card, gain 1 Block." -> 1 plays
  Unmovable "Ethereal. The first time you gain Block from a card each turn, double the amount gained." -> 1 plays, 1 block
  Calculated Gamble "Ethereal. Discard your Hand, then draw that many cards. Exhaust." -> 1 plays, 1 block, EXHAUST
  Defend "Ethereal. Gain 16 Block." -> 2 plays, 26 block
  Mirage "Ethereal. Gain Block equal to Poison on ALL enemies. (Gain 42 Block) Exhaust." -> 1 plays, 43 block, EXHAUST
  The Bomb "Ethereal. At the end of 3 turns, deal 40 damage to ALL enemies." -> 1 plays, 1 block
  Piercing Wail "Ethereal. ALL enemies lose 6 Strength this turn. Exhaust." -> 2 plays, 2 block, EXHAUST
  Neutralize "Ethereal. Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg, 1 block
  Whistle "Ethereal. Deal 33 damage. Stun the enemy. Exhaust." -> 1 plays, 33 dmg, 1 block, EXHAUST
  Deadly Poison "Ethereal. Apply 5 Poison." -> 1 plays, 1 block, +5 poison
  Glacier "Ethereal. Gain 18 Block. Channel 2 Frost." -> 1 plays, 24 block
  Strike "Deal 6 damage." -> 2 plays, 6 dmg, 1 block
  Backflip "Gain 16 Block. Draw 2 cards." -> 1 plays, 17 block

Active powers: Dexterity(1), Plating(4)

Token attribution (Shivs):
  Cloak and Dagger: 1 Shivs -> ~6 dmg

Poison stacks applied per card:
  Deadly Poison: 5 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:9
  Poison[0]: R1:4 -> R2:5 -> R3:6 -> R4:7 -> R5:8 -> R6:-
  Poison[1]: R1:4 -> R2:5 -> R3:6 -> R4:7 -> R5:8 -> R6:-
  Poison[2]: R1:4 -> R2:5 -> R3:6 -> R4:7 -> R5:8 -> R6:-
  Strength: R1:- -> R2:- -> R3:3 -> R4:3 -> R5:3 -> R6:3
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Vulnerable[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 44, elite)
Relics: Ring of the Snake, Winged Boots, The Chosen Cheese, Candelabra, Sword of Stone, Yummy Cookie, The Abacus, Juzu Bracelet, Bowler Hat, Sai, Gorget, Fragrant Mushroom, Potion Belt
Deck (30): Defend x5, Strike x3, Piercing Wail x2, Snakebite+ x2, Acrobatics+, Afterimage+, Backflip, Blade Dance+, Bouncing Flask, Bullet Time+, Calculated Gamble+, Dagger Throw, Deadly Poison+, Fan of Knives, Flick-Flack, Footwork+, Malaise, Neutralize+, Noxious Fumes+, Predator, Survivor, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
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

[Selected: boss] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Lead Paperweight, Mercury Hourglass, Horn Cleat, Meal Ticket, Prismatic Gem, Oddly Smooth Stone, Bag of Marbles, The Courier, Twisted Funnel, Pollinous Core, Tanx's Whistle, Gorget, Amethyst Aubergine, Pendulum, Ice Cream, Chemical X
Deck (39): Defend x5, Strike x3, Backflip x2, Deadly Poison x2, Guiding Star x2, Snakebite x2, Accelerant+, Afterimage, Ascender's Bane, Calculated Gamble, Cloak and Dagger, Dagger Spray, Dodge and Roll, Echoing Slash, Glacier, Hologram, Malaise, Mirage, Neutralize+, Noxious Fumes, Noxious Fumes+, Outbreak, Piercing Wail, Piercing Wail+, Survivor, The Bomb, Unmovable, Well-Laid Plans+, Whistle
Enemies: Torch Head Amalgam HP=196/199, Queen HP=397/400

### Round 1
Agent plan (hypothesis): Use Gambler's Brew next turn to discard the bound cards and dig for Noxious Fumes, Well-Laid Plans, or Afterimage.
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Outbreak
    energy -1 | +Outbreak(11)
  Unmovable
    energy -2 | +Unmovable(1)
  Deadly Poison -> Queen[1]
    energy -1 | enemy_deltas: Queen: Poison(4→9)
  turn_end
    block +4

### Round 2
Agent plan (hypothesis): Use remaining 2 energy to play a Block card and trigger Unmovable to fully mitigate the remaining 4 damage.
Intent: Torch Head Amalgam: Attack(18), Queen: Debuff
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Afterimage
    energy -1 | +Afterimage(1)
  turn_end
    block +3

### Round 3
Intent: Torch Head Amalgam: Attack(12x3=36), Queen: Buff, Defend
  Whistle -> Torch Head Amalgam[0]
    energy -3 | block +1 | exhausted: Whistle [3]: Deal 33 damage. Stun the enemy. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -24
  Accelerant+
    energy -1 | block +1 | +Accelerant(2)
  Gambler's Brew
  Guiding Star
  Neutralize+
  confirm
  Noxious Fumes
    energy -1 | block +1 | Noxious Fumes(3→5)
  Defend
    energy -1 | block +10
  turn_end
    block +2

### Round 4
Intent: Torch Head Amalgam: Attack(13x3=39), Queen: Buff, Defend
  Piercing Wail+
    energy -1 | block +1 | exhausted: Whistle [3]: Deal 33 damage. Stun the enemy. Exhaust. | enemy_deltas: Torch Head Amalgam: Strength(1→-7), +Piercing Wail(8); Queen: +Strength(-8), +Piercing Wail(8)
  Snakebite -> Queen[1]
    energy -2 | block +1 | enemy_deltas: Torch Head Amalgam: hp -11; Queen: block -11, Poison(12→19)
  Backflip
    energy -1 | block +10
  Malaise -> Queen[1]
    block +1 | exhausted: Whistle [3]: Deal 33 damage. Stun the enemy. Exhaust. | enemy_deltas: Queen: Strength(-8→-10), +Weak(2)
  turn_end
    block +1

### Round 5
Agent plan (hypothesis): We will have WLP+ active, use it to hold key defensive cards or Accelerant if we draw it.
Agent plan (hypothesis): Retained 2 Defends for the incoming multi-attack next turn.
Intent: Torch Head Amalgam: Attack(24), Queen: Buff, Defend
  Calculated Gamble
    block +1 | exhausted: Whistle [3]: Deal 33 damage. Stun the enemy. Exhaust.
  Mirage
    energy -1 | block +47 | exhausted: Whistle [3]: Deal 33 damage. Stun the enemy. Exhaust.
  Well-Laid Plans+
    energy -1 | block +1 | +Well-Laid Plans(2)
  Backflip
    energy -1 | block +5
  Deadly Poison -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -11; Queen: block -11, Poison(21→26)
  turn_end
  Defend
  Defend

### Round 6
Intent: Torch Head Amalgam: Attack(25), Queen: Buff, Defend
  Glacier
    energy -2 | block +16
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
    block +2
  Neutralize+
  Hologram

### Round 7
Intent: Torch Head Amalgam: Attack(18x3=54), Queen: Buff, Defend
  Neutralize+ -> Queen[1]
    block +1 | enemy_deltas: Queen: block -3, +Weak(2)
  Snakebite -> Queen[1]
    energy -2 | block +1 | enemy_deltas: Queen: Poison(30→37)
  Hologram
    energy -1 | block +6
  Deadly Poison
  Deadly Poison -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -11; Queen: hp -8, block -3, Poison(37→42)
  turn_end
    block +2
  Cloak and Dagger
  Guiding Star
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 7 rounds)

Cards played (with descriptions):
  Outbreak "Every 3 times you apply Poison, deal 11 damage to ALL enemies." -> 1 plays
  Unmovable "The first time you gain Block from a card each turn, double the amount gained." -> 1 plays
  Deadly Poison "Apply 5 Poison." -> 3 plays, 30 dmg, 2 block, +15 poison
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Afterimage "Whenever you play a card, gain 1 Block. Bound" -> 1 plays
  Whistle "Deal 24 damage. Stun the enemy. Exhaust." -> 1 plays, 24 dmg, 1 block, EXHAUST
  Accelerant+ "Poison is triggered 2 additional times." -> 1 plays, 1 block
  Noxious Fumes "At the start of your turn, apply 2 Poison to ALL enemies." -> 1 plays, 1 block
  Defend "Gain 9 Block." -> 3 plays, 20 block
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Bound Exhaust." -> 1 plays, 1 block, EXHAUST
  Snakebite "Retain. Apply 7 Poison." -> 2 plays, 11 dmg, 2 block, +14 poison
  Backflip "Gain 9 Block. Draw 2 cards." -> 2 plays, 15 block
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, 1 block, EXHAUST
  Calculated Gamble "Discard your Hand, then draw that many cards. Bound Exhaust." -> 1 plays, 1 block, EXHAUST
  Mirage "Gain Block equal to Poison on ALL enemies. (Gain 46 Block) Exhaust." -> 1 plays, 47 block, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 1 block
  Glacier "Gain 10 Block. Channel 2 Frost. Bound" -> 1 plays, 16 block
  Neutralize+ "Deal 3 damage. Apply 2 Weak." -> 1 plays, 1 block
  Hologram "Gain 6 Block. Put a card from your Discard Pile into your Hand. Exhaust." -> 1 plays, 6 block, EXHAUST

Active powers: Dexterity(1), Plating(4)

Poison stacks applied per card:
  Deadly Poison: 15 stacks
  Snakebite: 14 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Poison[0]: R1:4 -> R2:3 -> R3:5 -> R4:7 -> R5:9 -> R6:11 -> R7:13
  Poison[1]: R1:4 -> R2:8 -> R3:10 -> R4:12 -> R5:21 -> R6:28 -> R7:30
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:-2 -> R6:-2 -> R7:-2
  Vulnerable[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Vulnerable[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Lead Paperweight, Ripple Basin, Ice Cream, Lantern, Nunchaku, Very Hot Cocoa, Pen Nib, Candelabra, The Chosen Cheese, Happy Flower, Spiked Gauntlets, Tough Bandages, Strike Dummy, Bag of Preparation, Eternal Feather, Regal Pillow
Deck (34): Defend x5, Strike x3, Cloak and Dagger+ x2, Dagger Throw x2, Finesse x2, Leg Sweep x2, Accuracy+, Adrenaline, Adrenaline+, Backstab, Blade Dance, Dagger Spray, Dodge and Roll, Expertise+, Leading Strike, Murder, Neutralize+, Noxious Fumes, Piercing Wail, Poisoned Stab, Predator+, Prowess+, Storm of Steel, Survivor
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
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

## Triggered Skills This Run
- The Silent - Deckbuilding Principles: F1(), F2(), F3(), F4(), F5(), F6(), F8(), F8(), F11(), F12(), F14(), F15(), F17(), F19(), F20(), F21(), F22(), F22(), F23(), F24(), F25(), F27(), F28(), F29(), F30(), F33(), F35(), F37(), F37(), F38(), F40(), F42(), F46(), F46(), F46(), F48()
- The Silent - Path Selection: F1(), F1(), F2(), F6(), F8(), F10(), F10(), F11(), F11(), F12(), F12(), F18(), F18(), F19(), F20(), F21(), F29(), F29(), F34(), F34(), F35(), F35(), F36(), F37(), F38(), F41(), F42(), F43(), F44()
- The Silent - Rest & Event Decisions: F7(), F9(), F13(), F16(), F32(), F44(), F47()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.