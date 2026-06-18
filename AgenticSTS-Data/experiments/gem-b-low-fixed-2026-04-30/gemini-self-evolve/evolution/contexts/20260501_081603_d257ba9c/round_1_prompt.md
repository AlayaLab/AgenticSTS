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
Result: DEFEAT at Floor 48 (fitness: 142.9)
Combats won: 23/23
Run duration: 4823.4s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: rely on basic strikes and defends. Focus on drafting damage cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.
- [map] Foundation deck: rely on basic strikes and defends. Focus on drafting efficient damage and block cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.
### F2
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine. We have Poisoned Stab, so we might lean into poison if we see strong enablers, but stay open.
### F3
- [card_reward] Foundation plan: survive with frontload damage like Blade Dance and Poisoned Stab, leaning towards Shivs. Still need better mitigation and draw to fully commit.
- [map] Foundation deck: rely on basic strikes and defends. Focus on drafting damage cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.
### F4
- [card_select] Committed shiv plan: play Blade Dance with Accuracy to burst down enemies. Prioritize more shiv generation, card draw to cycle them, and reliable defense while avoiding cards that don't scale with shivs.
### F5
- [event] Foundation deck transitioning to Shivs: rely on Blade Dance and Accuracy for damage. Focus on drafting more Shiv synergy, block, and card draw while prioritizing targeted removals of basic cards.
- [card_select] Committed shiv plan: play Blade Dance with Accuracy to deal massive damage, looking for more Shiv generators, draw, and defense. Remove Strikes at every opportunity.
### F6
- [card_reward] Committed shiv plan: play Accuracy early, then burst with Blade Dance and Leading Strike. Need card draw (Backflip, Acrobatics) and block/defense to sustain our engine.
- [map] Foundation deck: currently relying on basics. Priority is drafting front-loaded damage and efficient block to handle Act 1 elites, as Lava Rock offers no immediate combat power.
### F7
- [card_reward] Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale. Avoid generic attacks and poison cards.
### F8
- [rest_site] Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for damage. Prioritize drawing and playing Shiv generators, while drafting more block and card draw.
### F9
- [card_reward] Committed shiv plan: play Accuracy early, then generate and play Shivs for massive efficient damage. Look for card draw (Acrobatics, Backflip) to cycle the deck and find the Shiv generators faster. Avoid expensive off-plan cards.
### F10
- [map] Foundation shiv deck: use Blade Dance and Accuracy for primary scaling while prioritizing card draw and defensive layers like Piercing Wail or Leg Sweep. Target removals of basic Strikes to increase deck density.
### F11
- [card_reward] Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage. Prioritize card draw (Backflip, Acrobatics) and defensive scaling to survive longer fights, while avoiding bloat from generic damage cards.
- [map] Foundation Shiv deck: stack Shiv generation and Accuracy for damage while prioritizing block to mitigate HP loss. Currently low on HP, so I must favor ? nodes for Planisphere healing and avoid unnecessary chip damage until the next rest site.
### F12
- [map] Foundation Shiv deck: stack Accuracy and Blade Dance for scaling damage while searching for Footwork or Leg Sweep to stabilize defense. Prioritize upgrading Accuracy to maximize Shiv value and use shops for card removals or finding key draw pieces.
### F13
- [rest_site] Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw.
### F14
- [card_reward] Committed to Shiv scaling plan: use Blade Dance, Leading Strike, Accuracy, and Phantom Blades for core damage. Needs more card draw and defense to survive while setting up powers.
- [map] Foundation Shiv deck: use Blade Dance and Accuracy for primary scaling while prioritizing card draw and consistent block. Avoid unnecessary elites until the deck has more front-loaded block or reliable damage mitigation; focus on upgrading core Shiv pieces at rest sites.
### F15
- [card_reward] Committed shiv plan: play Accuracy and Phantom Blades, then spam shivs. Needs more card draw (Acrobatics/Backflip) and defensive scaling (Footwork/Afterimage); avoid bloating the deck with generic attacks.
### F16
- [rest_site] Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw.
### F17
- [card_select] Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage, supplemented by per-card damage like Serpent Form. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale.
- [card_reward] Committed Shiv plan: scale damage with Accuracy/Phantom Blades, generate massive Shivs with Blade Dance/Leading Strike, and block passively with Afterimage. Need more draw (Acrobatics/Calculated Gamble) and perhaps one more premium Shiv generator. Avoid generic frontload.
### F18
- [event] Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw. Suppress provides reliable turn 1 damage mitigation.
- [map] Foundation Shiv deck: stack Shiv generation with Accuracy and focus on high-efficiency block and card draw; prioritize upgrades for core scaling pieces and keep HP high to avoid resting.
### F19
- [card_reward] Committed Shiv plan: scale damage with Accuracy and Phantom Blades, use Afterimage to convert Shiv spam into block. Prioritize draw and card removal to find our engine pieces faster; avoid off-plan attacks.
### F20
- [card_reward] Committed shiv plan: play Phantom Blades and Accuracy, generate Shivs to trigger Afterimage block and scale damage. Still need more card draw (Acrobatics/Calculated Gamble) and deck manipulation to cycle faster.
- [map] Committed Shiv engine: prioritize Accuracy and Shiv generators like Blade Dance. Use high gold reserves to refine the deck at shops, focusing on card removal and upgraded block/draw pieces to support the high-volume offensive turns.
### F21
- [event] Committed Shiv engine: play Accuracy and Phantom Blades early, then cycle Blade Dance and Leading Strike. Prioritize card removal and block/draw at shops.
### F22
- [card_reward] Committed to Shiv scaling plan: use Blade Dance, Leading Strike, and Accuracy for core damage. Retain Shivs with Phantom Blades for burst turns. Needs more draw (Acrobatics/Calculated Gamble) to cycle faster. Avoid generic attacks.
### F23
- [card_reward] Committed to Shiv scaling plan: use Blade Dance, Leading Strike, and Accuracy for core damage. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale. Avoid generic attacks and poison cards.
- [map] Committed Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage; prioritize drawing and playing Shiv generators while drafting more block and card draw.
### F25
- [card_select] Committed Shiv plan: scale damage rapidly with Accuracy and Phantom Blades, block passively with Afterimage, and draw through the deck with Backflips. Needs more draw/discard or energy generation; avoid basic attacks.
### F26
- [map] Committed Shiv engine: play Accuracy and Phantom Blades early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drafting block and card draw while using shops for card removal to keep the deck lean; avoid elites in Act 2 to preserve HP.
### F27
- [card_reward] Committed Shiv plan: utilize Phantom Blades and Accuracy to scale Shiv damage, block with Backflips and Afterimage, and finish with Finisher. Needs more card draw (Acrobatics) and energy; skip discard synergies until multiple discard outlets are present.
### F28
- [rest_site] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.
### F29
- [card_reward] Committed Shiv plan: Generate Shivs, buff them with Accuracy and Phantom Blades, and use Afterimage/Backflips for defense. Need energy generation (Adrenaline) or strong relics; skip cards that don't directly enhance the engine or provide energy.
### F30
- [event] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.
### F32
- [rest_site] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Continue prioritizing card removal and draw.
### F33
- [card_reward] Committed shiv plan: play Phantom Blades and Accuracy for upfront damage, set up Afterimage for block, and use Envenom to scale against bosses. Need more draw/energy or cheap block to keep the engine running.
### F34
- [event] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.
- [card_select] Committed Shiv plan: scale damage with Accuracy and Phantom Blades, defend with Afterimage and Backflips. Needs energy generation (Tactician/Concentrate) or card draw; avoid non-Shiv attacks.
- [map] Committed Shiv engine: prioritize Accuracy and Phantom Blades, then cycle Blade Dance and Leading Strike. Seek block and draw while using shops to remove strikes; lean on Planisphere healing in events to avoid rest site healing in favor of upgrades.
### F35
- [card_reward] Committed Shiv scaling plan: use Shiv generators (Blade Dance, Leading Strike, Up My Sleeve) to fuel Accuracy, Phantom Blades, and Finisher for massive damage, while Afterimage provides block and Envenom stacks poison. Retain Shivs for burst turns when needed.
### F36
- [event] Committed Shiv engine: prioritize Accuracy and Phantom Blades, then cycle Blade Dance and Leading Strike. Seek block and draw while using shops to remove strikes; lean on Planisphere healing in events to avoid rest site healing in favor of upgrades.
### F38
- [card_reward] Committed shiv plan: generate massive amounts of shivs to trigger Afterimage for block, apply poison via Envenom, and deal damage via Accuracy and Phantom Blades. Look for more draw (Acrobatics, Backflip) and potentially energy generation.
### F39
- [card_select] Committed Shiv plan: scale damage with Accuracy and Phantom Blades while generating block passively with Afterimage. Spam shivs to overwhelm enemies. Skip non-shiv attacks and look for draw/energy.
### F40
- [card_reward] Committed Shiv engine: set up Accuracy, Phantom Blades, Afterimage, and Footwork, then cycle Shiv generators for massive damage. Needs rapid draw/energy; skip generic cards to avoid diluting the engine.
### F42
- [card_select] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Continue prioritizing card removal and draw.
- [card_reward] Committed Shiv engine: set up Afterimage, Accuracy, and Phantom Blades, then spam Shiv generators for massive damage and passive block. Keep looking for card draw and removal.
- [map] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Priority is now securing HP for the final gauntlet while looking for draw power to ensure key pieces are found quickly.
### F43
- [rest_site] Committed Shiv engine: set up Accuracy, Phantom Blades, and Afterimage, then use Shiv generators for block and high damage. Prioritize Footwork and Leg Sweep for survivability. Needs to remove strikes/defends.
### F44
- [card_reward] Committed Shiv/Envenom engine. Rely on Phantom Blades and Accuracy to scale Shiv damage, while Envenom stacks poison. Prioritize card draw (Acrobatics/Calculated Gamble) and energy to play our expensive setup cards. Avoid adding more 1-cost attacks.
### F45
- [card_reward] Committed Shiv plan: burst enemies down with Tracking + Suppress+ and massive Shiv generation. Prioritize draw and energy, skip non-Shiv attacks.
### F46
- [card_reward] Committed Shiv engine: retain Phantom Blades and Accuracy pieces, cycle Blade Dance and Cloak and Dagger, scale damage with Shivs and Finisher. Needs block/draw consistency; avoid off-plan damage cards.
### F47
- [rest_site] Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Boss is next, play for survival.

### Combat Decision Digest (24 combats)
F2 [monster] Sludge Spinner (4R, HP 56->56, loss=0, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R2[Sludge Spinner: Atk(6), Buff]: Defend(+5blk)->Defend(+5blk)->Strike(4dmg) | dealt=4 taken=0
  R3[Sludge Spinner: Atk(11), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R4[Sludge Spinner: Atk(9), Buff]: Strike(power:-Weak) | dealt=0 taken=0

F3 [monster] multi:Corpse Slug+Corpse Slug (4R, HP 56->53, loss=3, WIN)
  R1[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Neutralize->Strike->Strike(6dmg)->Survivor(+8blk) | dealt=6 taken=0
  R2[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Defend(+3blk)->Poisoned Stab(6dmg,1+Poison(3))->Strike | dealt=6 taken=3
  R3[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike->Strike(1+Strength(4))->Strike(6dmg) | dealt=6 taken=0
  R4[Corpse Slug: Atk(12)]: Neutralize(power:-Frail) | dealt=0 taken=0

F6 [monster] Seapunk (4R, HP 53->53, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Defend(+5blk)->Defend(+5blk) | dealt=15 taken=0
  R2[Seapunk: Atk(2x4=8)]: Poisoned Stab(6dmg,1+Poison(3))->Strike(6dmg)->Survivor(+8blk) | dealt=12 taken=0
  R3[Seapunk: Buff, Defend]: Poisoned Stab(6dmg,1Poison(2→5))->Defend(+5blk)->Defend(+5blk) | dealt=6 taken=0
  R4[Seapunk: Atk(12)]: Neutralize(1+Weak(1))->Strike(2dmg)->Strike | dealt=2 taken=0

F7 [monster] Punch Construct (4R, HP 53->44, loss=9, WIN)
  R1[Punch Construct: Defend]: Neutralize(3dmg,1-Artifact)->Poisoned Stab(6dmg,1+Poison(3))->Strike(6dmg)->Strike(6dmg) | dealt=21 taken=0
  R2[Punch Construct: Atk(14)]: Defend(+5blk)->Defend(+5blk)->Blade Dance(exhaust:1)->Shiv(exhaust:1)->Shiv->Shiv(2dmg) | dealt=2 taken=4
  R3[Punch Construct: Atk(5x2=10), Debuff]: Defend(+5blk)->Poisoned Stab(6dmg,1Poison(1→4))->Accuracy(power:+Accuracy(4)) | dealt=6 taken=5
  R4[Punch Construct: Defend]: Leading Strike(2dmg)->Shiv(6dmg)->Shiv(6dmg) | dealt=14 taken=0

F9 [monster] multi:Corpse Slug+Corpse Slug+Corpse Slug (4R, HP 44->42, loss=2, WIN)
  R1[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Blade Dance+(exhaust:1)->Shiv(exhaust:1)->Shiv*3->Neutralize->Strike(1+Strength(4))->Strike(6dmg) | dealt=6 taken=0
  R2[Corpse Slug: Atk(12)+Corpse Slug: Debuff]: Defend(+5blk)->Defend(+5blk)->Accuracy(power:+Accuracy(4)) | dealt=0 taken=2
  R3[Corpse Slug: Debuff+Corpse Slug: Atk(7x2=14)]: Neutralize(3dmg,1+Weak(1))->Leading Strike(3dmg)->Shiv(8dmg)->Shiv(2Strength(4→8),-Weak)->Strike(6dmg)->Strike(6dmg) | dealt=26 taken=0
  R4[Corpse Slug: Debuff]: Strike(6dmg)->Poisoned Stab(6dmg,1+Poison(3))->Defend(+3blk) | dealt=12 taken=0

F11 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (5R, HP 42->35, loss=7, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Accuracy(power:+Accuracy(4))->Blade Dance+(exhaust:1)->Shiv(exhaust:1)->Shiv*3->Survivor(+8blk) | dealt=0 taken=0
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(7)]: Neutralize(3dmg,1+Weak(1))->Leading Strike->Shiv(5dmg)->Shiv(8dmg)->Poisoned Stab(6dmg,1+Poison(3))->Strike(6dmg) | dealt=28 taken=7
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)]: Neutralize->Poisoned Stab->Strike->Survivor(+8blk) | dealt=0 taken=0
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff]: Leading Strike->Strike->Shiv*2->Leading Strike(3dmg)->Shiv(2dmg)->Shiv(8dmg) | dealt=13 taken=0
  R5[Phantasmal Gardener: Atk(7)]: Leading Strike(3dmg)->Shiv(2dmg)->Shiv(8dmg)->Poisoned Stab(power:-Accuracy) | dealt=13 taken=0

F14 [monster] Haunted Ship (2R, HP 40->40, loss=0, WIN)
  R1[Haunted Ship: StatusCard(5)]: Backflip(+5blk)->Strike(9dmg)->Blade Dance+(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg) | dealt=25 taken=0
  R2[Haunted Ship: Atk(10), Debuff]: Neutralize(3dmg,1+Weak(1))->Leading Strike(6dmg)->Shiv(4dmg)->Shiv(4dmg)->Leading Strike(6dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike | dealt=31 taken=0

F15 [monster] Sewer Clam (2R, HP 40->40, loss=0, WIN)
  R1[Sewer Clam: Atk(10)]: Phantom Blades(power:+Phantom Blades(9))->Neutralize(1+Weak(1))->Blade Dance+(exhaust:1)->Shiv(8dmg,exhaust:1)->Survivor(+8blk) | dealt=8 taken=0
  R2[Sewer Clam: Buff]: Backflip(+5blk)->Accuracy+(power:+Accuracy(6))->Leading Strike->Shiv(17dmg)->Shiv(10dmg)->Shiv(10dmg)->Shiv(10dmg)->Shiv(power:-Phantom Blades,power:-Accuracy) | dealt=47 taken=0

F17 [boss] Soul Fysh (6R, HP 61->48, loss=13, WIN)
  R1[Soul Fysh: StatusCard(2)]: Neutralize(3dmg,1+Weak(1))->Blade Dance+(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Leading Strike(6dmg)->Shiv(4dmg)->Shiv(4dmg)->Strike(9dmg) | dealt=52 taken=0
  R2[Soul Fysh: Atk(16)]: Serpent Form(power:+Serpent Form(4))->Backflip(4dmg,+5blk)->Beckon(4dmg)->Leading Strike(10dmg)->Shiv(8dmg)->Shiv(8dmg) | dealt=34 taken=11
  R3[Soul Fysh: Atk(7), StatusCard(1)]: Accuracy+(4dmg,power:+Accuracy(6))->Phantom Blades(4dmg,power:+Phantom Blades(9))->Defend(4dmg,+5blk) | dealt=12 taken=2
  R4[Soul Fysh: Buff]: Leading Strike(10dmg)->Shiv(23dmg)->Shiv(14dmg)->Poisoned Stab(10dmg,1+Poison(3))->Beckon(4dmg) | dealt=61 taken=0
  R5[Soul Fysh: Atk(11), Debuff]: Neutralize(2dmg,1+Weak(1))->Leading Strike(2dmg)->Shiv(2dmg)->Shiv(2dmg)->Defend(1dmg,+5blk)->Survivor(1dmg,+8blk) | dealt=10 taken=0
  R6[Soul Fysh: StatusCard(2)]: Neutralize(7dmg,1+Weak(1))->Strike(power:-Serpent Form,power:-Accuracy,power:-Phantom Blades,power:-Vulnerable) | dealt=7 taken=0

F19 [monster] Thieving Hopper (4R, HP 65->63, loss=2, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Suppress+(17dmg,1+Weak(5))->Backflip(+5blk)->Phantom Blades(power:+Phantom Blades(9))->Defend(+5blk) | dealt=17 taken=2
  R2[Thieving Hopper: Buff]: Poisoned Stab(6dmg,1+Poison(3))->Leading Strike(6dmg)->Shiv(13dmg,exhaust:1)->Shiv(4dmg)->Strike(9dmg) | dealt=38 taken=0
  R3[Thieving Hopper: Atk(15)]: Backflip(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R4[Thieving Hopper: Atk(10)]: Suppress+(8dmg,2Weak(2→7),Flutter(5→4))->Blade Dance+(exhaust:1)->Shiv(6dmg,1Flutter(4→3))->Shiv(2dmg,1Flutter(3→2))->Shiv(2dmg,1Flutter(2→1))->Shiv(power:-Phantom Blades) | dealt=18 taken=0

F20 [monster] Tunneler (2R, HP 63->59, loss=4, WIN)
  R1[Tunneler: Atk(13)]: Suppress+(17dmg,1+Weak(5))->Phantom Blades(power:+Phantom Blades(9))->Defend(+5blk)->Blade Dance+(exhaust:1)->Shiv(13dmg,exhaust:1) | dealt=30 taken=4
  R2[Tunneler: Buff, Defend]: Accuracy+(power:+Accuracy(6))->Poisoned Stab(6dmg,1+Poison(3))->Leading Strike+(9dmg)->Shiv(19dmg)->Shiv(10dmg)->Shiv(10dmg)->Shiv(power:-Phantom Blades,power:-Accuracy) | dealt=54 taken=0

F22 [monster] multi:Exoskeleton+Exoskeleton+Exoskeleton+Exoskeleton (3R, HP 70->62, loss=8, WIN)
  R1[Exoskeleton: Atk(1x3=3)+Exoskeleton: Atk(8)+Exoskeleton: Buff+Exoskeleton: Atk(1x3=3)]: Suppress+->Blade Dance+(exhaust:1)->Shiv(exhaust:1)->Shiv*2->Leading Strike(6dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv->Defend(+5blk) | dealt=23 taken=0
  R2[Exoskeleton: Atk(8)+Exoskeleton: Atk(3x3=9)]: Afterimage(power:+Afterimage(1))->Leading Strike(6dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Defend(+6blk) | dealt=14 taken=8
  R3[Exoskeleton: Buff+Exoskeleton: Atk(10)]: Dagger Spray+(+1blk,1-Strength)->Strike(power:-Afterimage) | dealt=0 taken=0

F23 [monster] multi:Myte+Myte (3R, HP 62->49, loss=13, WIN)
  R1[Myte: StatusCard(2)+Myte: Atk(4), Buff]: Suppress+(17dmg,1+Weak(5))->Backflip(+5blk)->Accuracy+(power:+Accuracy(6))->Leading Strike+(9dmg)->Shiv(10dmg,exhaust:1)->Shiv(10dmg) | dealt=46 taken=0
  R2[Myte: Atk(13)+Myte: StatusCard(2)]: Expose(exhaust:1)->Leading Strike(6dmg)->Shiv(10dmg)->Shiv->Toxic(exhaust:1)->Toxic | dealt=16 taken=13
  R3[Myte: Atk(4), Buff+Myte: Atk(11)]: Survivor(+8blk)->Dagger Spray+(3+Vulnerable(1),-Weak,-Strength)->Blade Dance+(exhaust:1)->Shiv(15dmg)->Shiv(15dmg)->Shiv(power:-Accuracy) | dealt=30 taken=0

F27 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (7R, HP 70->70, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Suppress+(17dmg,1+Weak(5))->Backflip(+5blk)->Cloak and Dagger(+6blk)->Shiv(4dmg,exhaust:1)->Blade Dance+(exhaust:1)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg)->Shiv(4dmg) | dealt=37 taken=0
  R2[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Afterimage(power:+Afterimage(1))->Survivor(+8blk)->Poisoned Stab(4dmg,+1blk,1+Poison(3)) | dealt=4 taken=0
  R3[Bowlbug (Rock): Atk(11)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Leg Sweep(+12blk,1Weak(3→5))->Leading Strike(6dmg,+1blk)->Shiv(+1blk)->Shiv(6dmg,+1blk) | dealt=14 taken=0
  R4[Bowlbug (Rock): Stun+Slumbering Beetle: Atk(16), Buff]: Backflip(+6blk)->Backflip+(+9blk)->Suppress+(+1blk)->Accuracy+(+1blk,power:+Accuracy(6)) | dealt=19 taken=0
  R5[Slumbering Beetle: Atk(18), Buff]: Leg Sweep(+12blk,1+Weak(2))->Leading Strike+(9dmg,+1blk)->Shiv(10dmg,+1blk)->Shiv(10dmg,+1blk) | dealt=29 taken=0
  R6[Slumbering Beetle: Atk(15), Buff]: Backflip(+6blk)->Leading Strike(6dmg,+1blk)->Shiv(10dmg,+1blk)->Shiv(10dmg,+1blk)->Survivor(+8blk) | dealt=26 taken=0
  R7[Slumbering Beetle: Atk(22), Buff]: Leading Strike(6dmg,+1blk)->Shiv(10dmg,+1blk)->Shiv(power:-Thorns,power:-Afterimage,power:-Accuracy) | dealt=16 taken=0

F29 [monster] Ovicopter (3R, HP 70->62, loss=8, WIN)
  R1[Ovicopter: Summon]: Suppress+(17dmg,1+Weak(5))->Backflip(+5blk)->Cloak and Dagger+(+6blk)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Finisher+(24dmg) | dealt=49 taken=0
  R2[Tough Egg: Summon+Tough Egg: Summon+Tough Egg: Summon+Ovicopter: Atk(12)]: Afterimage(power:+Afterimage(1))->Phantom Blades(+1blk,power:+Phantom Blades(9))->Leading Strike+(9dmg,+1blk)->Shiv(13dmg,+1blk)->Shiv(4dmg,+1blk) | dealt=26 taken=8
  R3[Hatchling: Atk(4)+Hatchling: Atk(4)+Hatchling: Atk(4)+Ovicopter: Atk(5), Debuff]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Accuracy+(+1blk,power:+Accuracy(6))->Blade Dance+(+1blk,exhaust:1)->Shiv(28dmg,+1blk)->Shiv(15dmg,+1blk)->Shiv(power:-Thorns,power:-Afterimage,power:-Phantom Blades,power:-Accuracy) | dealt=43 taken=0

F33 [boss] multi:Crusher+Rocket (8R, HP 58->39, loss=19, WIN)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Afterimage+(power:+Afterimage(1))->Phantom Blades(+1blk,power:+Phantom Blades(9))->Suppress+(17dmg,+1blk,1+Weak(5))->Backflip(+8blk) | dealt=17 taken=3
  R2[Crusher: Atk(3)+Rocket: Atk(27)]: Defend(+8blk)->Cloak and Dagger+(+9blk)->Shiv(13dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Blade Dance+(+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Finisher+(48dmg,+1blk) | dealt=81 taken=0
  R3[Crusher: Atk(6x2=12), Debuff+Rocket: Buff]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Accuracy+(+1blk,power:+Accuracy(6))->Dagger Spray+(30dmg,+1blk)->Defend(+8blk) | dealt=30 taken=1
  R4[Crusher: Buff+Rocket: Atk(33)]: Backflip(+6blk)->Backflip+(+8blk)->Leading Strike+(10dmg,+1blk)->Shiv(21dmg,+1blk)->Shiv(11dmg,+1blk) | dealt=42 taken=16
  R5[Crusher: Atk(15), Defend+Rocket: Sleep]: Suppress+(12dmg,+1blk,1Weak(1→6))->Cloak and Dagger+(+7blk)->Shiv(14dmg,+1blk)->Shiv(7dmg,+1blk)->Defend(+6blk)->Backflip(+6blk) | dealt=33 taken=0
  R6[Crusher: Atk(10)+Rocket: Atk(7)]: Leading Strike(6dmg,+1blk)->Shiv(19dmg,+1blk)->Shiv(10dmg,+1blk)->Finisher+(+1blk,2Strength(2→8),-Crab Rage)->Leg Sweep(+14blk,1Weak(5→7)) | dealt=49 taken=0
  R7[Crusher: Atk(9)]: Backflip+(+11blk)->Suppress+(17dmg,+1blk,1Weak(6→11))->Cloak and Dagger+(+9blk)->Shiv(19dmg,+1blk)->Shiv(10dmg,+1blk)->Strike(9dmg,+1blk)->Finisher+(32dmg,+1blk) | dealt=87 taken=0
  R8[Crusher: Atk(10x2=20), Debuff]: Leading Strike(6dmg,+1blk)->Shiv(19dmg,+1blk)->Shiv(power:-Thorns,power:-Surrounded,power:-Dexterity,power:-Afterimage,power:-Phantom Blades,power:-Accuracy) | dealt=25 taken=0

F35 [monster] Devoted Sculptor (4R, HP 64->65, loss=0, WIN)
  R1[Devoted Sculptor: Buff]: Suppress+(17dmg,1+Weak(5))->Afterimage+(power:+Afterimage(1))->Phantom Blades(+1blk,power:+Phantom Blades(9))->Accuracy+(+1blk,power:+Accuracy(6)) | dealt=17 taken=0
  R2[Devoted Sculptor: Atk(9)]: Backflip+(+9blk)->Leading Strike(6dmg,+1blk)->Shiv(19dmg,+1blk,exhaust:1)->Shiv(10dmg,+1blk)->Finisher+(24dmg,+1blk) | dealt=59 taken=0
  R3[Devoted Sculptor: Atk(15)]: Backflip(+6blk)->Defend(+6blk)->Leading Strike(6dmg,+1blk)->Shiv(19dmg,+1blk)->Shiv(10dmg,+1blk) | dealt=35 taken=0
  R4[Devoted Sculptor: Atk(22)]: Expose(+1blk,1+Vulnerable(2),exhaust:1)->Leading Strike+(13dmg,+1blk)->Shiv(28dmg,+1blk)->Shiv(power:-Thorns,power:-Afterimage,power:-Phantom Blades,power:-Accuracy) | dealt=41 taken=0

F38 [monster] multi:Scroll of Biting+Scroll of Biting+Scroll of Biting (2R, HP 72->73, loss=0, WIN)
  R1[Scroll of Biting: Atk(5x2=10)+Scroll of Biting: Buff+Scroll of Biting: Atk(14)]: Afterimage+(power:+Afterimage(1))->Expose(+1blk,exhaust:1)->Accuracy+(+1blk,power:+Accuracy(6))->Suppress+(17dmg,+1blk,1+Weak(5))->Leading Strike(+1blk)->Shiv(+1blk,exhaust:1)->Shiv(1dmg,+1blk) | dealt=18 taken=0
  R2[Scroll of Biting: Atk(7x2=14)+Scroll of Biting: Buff]: Phantom Blades(+1blk,power:+Phantom Blades(9))->Leading Strike(+1blk)->Shiv(+1blk)->Shiv(1dmg,+1blk)->Leading Strike+(9dmg,+1blk)->Shiv(power:-Afterimage,power:-Accuracy,power:-Phantom Blades) | dealt=10 taken=0

F40 [monster] multi:The Forgotten+The Lost (5R, HP 73->66, loss=7, WIN)
  R1[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Afterimage+(power:+Afterimage(1))->Suppress+(17dmg,+1blk,1+Weak(5))->Backflip(+6blk)->Accuracy+(+1blk,power:+Accuracy(6)) | dealt=17 taken=0
  R2[The Lost: Atk(4x2=8)+The Forgotten: Atk(15)]: Footwork(+1blk,power:-Dexterity)->Cloak and Dagger+(+7blk)->Shiv(8dmg,+1blk,exhaust:1)->Shiv(9dmg,+1blk)->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(8dmg,+1blk)->Shiv(9dmg,+1blk)->Shiv(8dmg,+1blk)->Shiv(9dmg,+1blk) | dealt=52 taken=8
  R3[The Lost: Debuff, Buff+The Forgotten: Debuff, Defend, Buff]: Expose(1dmg,+1blk,1+Vulnerable(2),exhaust:1)->Phantom Blades(+1blk,power:+Phantom Blades(9))->Leading Strike(6dmg,+1blk)->Shiv(1dmg,+1blk,power:-Strength)->Shiv(11dmg,+1blk)->Finisher+(24dmg,+1blk) | dealt=61 taken=0
  R4[The Forgotten: Atk(17)]: Leg Sweep(+10blk,1+Weak(2))->Blade Dance+(+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk) | dealt=44 taken=0
  R5[The Forgotten: Debuff, Defend, Buff]: Leading Strike(6dmg,+1blk)->Shiv(power:-Afterimage,power:-Accuracy,power:-Phantom Blades,power:-Dexterity) | dealt=6 taken=0

F42 [elite] multi:Flail Knight+Magi Knight+Spectral Knight (9R, HP 66->36, loss=30, WIN)
  R1[Flail Knight: Atk(15)+Spectral Knight: Debuff+Magi Knight: Atk(6), Defend]: Afterimage+(power:+Afterimage(1))->Suppress+(17dmg,+1blk,1+Weak(5))->Leg Sweep(+12blk,1+Weak(2)) | dealt=17 taken=0
  R2[Flail Knight: Atk(6x2=12)+Spectral Knight: Atk(15)+Magi Knight: Debuff]: Accuracy+(+1blk,power:+Accuracy(6))->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(11dmg,+1blk,exhaust:1)->Shiv(10dmg,+1blk)->Shiv(10dmg,+1blk)->Shiv(11dmg,+1blk)->Cloak and Dagger+(+7blk)->Shiv(11dmg,+1blk)->Shiv(10dmg,+1blk) | dealt=64 taken=12
  R3[Flail Knight: Buff+Spectral Knight: Atk(15)+Magi Knight: Atk(10)]: Expose(1dmg,+1blk,1+Vulnerable(2),exhaust:1)->Leading Strike(6dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk)->Dagger Spray(20dmg,+1blk,power:-Hex)->Survivor(+8blk) | dealt=54 taken=0
  R4[Flail Knight: Atk(9x2=18)+Magi Knight: Defend]: Backflip(+6blk)->Defend(+6blk)->Defend(+6blk) | dealt=0 taken=0
  R5[Flail Knight: Buff+Magi Knight: Atk(35)]: Backflip(+6blk)->Backflip(+6blk)->Backflip(+6blk)->Survivor(+8blk) | dealt=0 taken=4
  R6[Flail Knight: Atk(21)+Magi Knight: Atk(10)]: Suppress(11dmg,+1blk,1+Weak(3))->Footwork(+1blk,power:+Dexterity(2))->Cloak and Dagger(+9blk)->Shiv(11dmg,+1blk)->Blade Dance(1dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(11dmg,+1blk) | dealt=56 taken=9
  R7[Flail Knight: Atk(11x2=22)+Magi Knight: Defend]: Leading Strike(6dmg,+1blk)->Shiv(1dmg,+1blk)->Shiv(11dmg,+1blk)->Poisoned Stab(6dmg,+1blk,1+Poison(3))->Defend(+8blk) | dealt=32 taken=0
  R8[Magi Knight: Atk(35)]: Backflip(+8blk)->Cloak and Dagger(+9blk)->Shiv(6dmg,+1blk)->Survivor(+10blk) | dealt=6 taken=6
  R9[Magi Knight: Atk(10)]: Suppress(11dmg,+1blk,1+Weak(3))->Leading Strike(6dmg,+1blk)->Shiv(11dmg,+1blk)->Shiv(power:-Afterimage,power:-Accuracy,power:-Dampen,power:-Dexterity) | dealt=28 taken=0

F44 [elite] Soul Nexus (9R, HP 58->47, loss=11, WIN)
  R1[Soul Nexus: Atk(29)]: Afterimage+(power:+Afterimage(1))->Suppress+(17dmg,+1blk,1+Weak(5))->Backflip(+6blk)->Defend(+6blk) | dealt=17 taken=0
  R2[Soul Nexus: Atk(13), DebuffStrong]: Leg Sweep(+12blk,1Weak(4→6))->Phantom Blades(+1blk,power:+Phantom Blades(9)) | dealt=0 taken=0
  R3[Soul Nexus: Atk(6x4=24)]: Backflip+(+9blk)->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(10dmg,+1blk,exhaust:1)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Survivor(+8blk) | dealt=23 taken=1
  R4[Soul Nexus: Atk(20), DebuffStrong]: Expose(1dmg,+1blk,1+Vulnerable(2),exhaust:1)->Footwork(+1blk,power:+Dexterity(2))->Cloak and Dagger+(+9blk)->Shiv(15dmg,+1blk)->Shiv(5dmg,+1blk)->Backflip(+8blk) | dealt=21 taken=0
  R5[Soul Nexus: Atk(32)]: Suppress+(19dmg,+1blk,1Weak(3→8))->Backflip(+8blk)->Leading Strike(6dmg,+1blk)->Shiv(15dmg,+1blk)->Shiv(5dmg,+1blk)->Survivor(+10blk) | dealt=45 taken=9
  R6[Soul Nexus: Atk(20), DebuffStrong]: Leg Sweep(+14blk,1Weak(7→9))->Blade Dance+(1dmg,+1blk)->Shiv(10dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk)->Shiv(4dmg,+1blk) | dealt=23 taken=1
  R7[Soul Nexus: Atk(6x4=24)]: Backflip(+8blk)->Cloak and Dagger+(+9blk)->Shiv(10dmg,+1blk)->Shiv(4dmg,+1blk)->Defend(+8blk) | dealt=14 taken=0
  R8[Soul Nexus: Atk(32)]: Backflip+(+11blk)->Defend(+8blk)->Defend(+8blk) | dealt=0 taken=1
  R9[Soul Nexus: Atk(13), DebuffStrong]: Suppress+(17dmg,+1blk,1Weak(6→11))->Cloak and Dagger+(+9blk)->Shiv(14dmg,+1blk)->Shiv(5dmg,+1blk)->Leading Strike(6dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Finisher+(power:-Afterimage,power:-Phantom Blades,power:-Dexterity) | dealt=52 taken=0

F45 [monster] Frog Knight (5R, HP 47->47, loss=0, WIN)
  R1[Frog Knight: Atk(13), Debuff]: Afterimage+(power:+Afterimage(1))->Suppress+(2dmg,+1blk,1+Weak(5))->Phantom Blades(+1blk,power:+Phantom Blades(9))->Backflip(+6blk) | dealt=2 taken=0
  R2[Frog Knight: Atk(15)]: Leg Sweep(+9blk,1Weak(4→6))->Phantom Blades(+1blk,power:Phantom Blades(9→18)) | dealt=0 taken=1
  R3[Frog Knight: Buff]: Expose(1dmg,+1blk,1+Vulnerable(2),exhaust:1)->Envenom(+1blk,power:+Envenom(1))->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(34dmg,+1blk,1+Poison(1),exhaust:1)->Shiv(7dmg,+1blk,1Poison(1→2))->Shiv(7dmg,+1blk,1Poison(2→3))->Shiv(7dmg,+1blk,1Poison(3→4))->Blade Dance+(1dmg,+1blk)->Shiv(7dmg,+1blk,1Poison(4→5))->Shiv(7dmg,+1blk,1Poison(5→6))->Shiv(7dmg,+1blk,1Poison(6→7))->Shiv(7dmg,+1blk,1Poison(7→8)) | dealt=86 taken=0
  R4[Frog Knight: Atk(30)]: Footwork(+1blk,power:+Dexterity(2))->Cloak and Dagger+(+9blk)->Shiv(25dmg,+1blk,1Poison(7→8))->Shiv(11dmg,+1blk,1Poison(8→9))->Backflip(+8blk) | dealt=36 taken=0
  R5[Frog Knight: Atk(13), Debuff]: Cloak and Dagger+(+9blk)->Leading Strike(+1blk)->Shiv(17dmg,+1blk,1Poison(8→9))->Shiv(5dmg,+1blk,1Poison(9→10))->Shiv(5dmg,+1blk,1Poison(10→11))->Shiv(5dmg,+1blk,1Poison(11→12))->Dagger Spray+(12dmg,+1blk,1Poison(12→14)) | dealt=44 taken=0

F46 [elite] Mecha Knight (7R, HP 47->32, loss=15, WIN)
  R1[Mecha Knight: Atk(25)]: Suppress+(17dmg,1Artifact(3→2))->Afterimage+(power:+Afterimage(1))->Backflip(+6blk)->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(5dmg,+1blk,exhaust:1)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk) | dealt=38 taken=4
  R2[Mecha Knight: StatusCard(4)]: Expose(1dmg,+1blk,2+Vulnerable(2),-Artifact,exhaust:1)->Backflip(+6blk)->Phantom Blades(+1blk,power:+Phantom Blades(9))->Blade Dance+(1dmg,+1blk)->Shiv(20dmg,+1blk)->Shiv(7dmg,+1blk)->Shiv(7dmg,+1blk)->Shiv(7dmg,+1blk) | dealt=43 taken=0
  R3[Mecha Knight: Defend, Buff]: Cloak and Dagger+(+7blk)->Shiv(20dmg,+1blk)->Shiv(7dmg,+1blk)->Poisoned Stab(9dmg,+1blk,1+Poison(3))->Finisher+(36dmg,+1blk) | dealt=72 taken=0
  R4[Mecha Knight: Atk(40)]: Cloak and Dagger+(+12blk)->Defend(+11blk)->Leading Strike(+1blk)->Shiv(11dmg,+1blk)->Shiv(8dmg,+1blk)->Shiv(8dmg,+1blk)->Shiv(8dmg,+1blk) | dealt=35 taken=12
  R5[Mecha Knight: StatusCard(4)]: Footwork(+1blk,power:+Dexterity(2))->Cloak and Dagger+(+9blk)->Leading Strike(6dmg,+1blk)->Shiv(14dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk) | dealt=35 taken=0
  R6[Mecha Knight: Defend, Buff]: Suppress+(17dmg,+1blk,1+Weak(5))->Leading Strike+(9dmg,+1blk)->Shiv(14dmg,+1blk)->Shiv(5dmg,+1blk)->Cloak and Dagger+(+9blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Backflip(+8blk) | dealt=55 taken=0
  R7[Mecha Knight: Atk(33)]: Backflip(+8blk)->Backflip+(+11blk)->Leading Strike(4dmg,+1blk)->Shiv(power:-Afterimage,power:-Phantom Blades,power:-Dexterity,power:-Strength,power:-Reptile Trinket) | dealt=4 taken=0

F48 [boss] multi:Queen+Torch Head Amalgam (9R, HP 55->0, loss=55, LOSS)
  R1[Torch Head Amalgam: Atk(18)+Queen: CardDebuff]: Footwork(power:+Dexterity(2))->Afterimage+(power:+Afterimage(1))->Suppress+(17dmg,+1blk,1+Weak(5))->Backflip+(+11blk)->Cloak and Dagger+(+9blk)->Shiv(5dmg,+1blk,exhaust:1)->Shiv(5dmg,+1blk) | dealt=27 taken=0
  R2[Torch Head Amalgam: Atk(13)+Queen: Debuff]: Backflip(+8blk)->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk)->Leading Strike(6dmg,+1blk)->Shiv(5dmg,+1blk)->Shiv(5dmg,+1blk) | dealt=37 taken=0
  R3[Torch Head Amalgam: Atk(9x3=27)+Queen: Buff, Defend]: Backflip(+6blk)->Accuracy+(+1blk,power:+Accuracy(6))->Defend(+6blk) | dealt=0 taken=10
  R4[Torch Head Amalgam: Atk(16)+Queen: Buff, Defend]: Expose(1dmg,+1blk,1+Vulnerable(2),exhaust:1)->Envenom(+1blk,power:+Envenom(1))->Cloak and Dagger+(+7blk)->Shiv(12dmg,+1blk,1+Poison(1))->Shiv(12dmg,+1blk,1Poison(1→2))->Leading Strike+(10dmg,+1blk,1Poison(2→3))->Shiv(12dmg,+1blk,1Poison(3→4))->Shiv(12dmg,+1blk,1Poison(4→5)) | dealt=59 taken=2
  R5[Torch Head Amalgam: Atk(18)+Queen: Buff, Defend]: Cloak and Dagger+(+7blk)->Shiv(+1blk)->Shiv(4dmg,+1blk,1Poison(4→5))->Backflip(+6blk)->Finisher+(18dmg,+1blk,1Poison(5→7)) | dealt=22 taken=2
  R6[Torch Head Amalgam: Atk(16x3=48)+Queen: Buff, Defend]: Suppress+(12dmg,+1blk,2+Poison(1),+Weak(5))->Backflip+(+8blk)->Defend(+6blk)->Survivor(+7blk) | dealt=12 taken=13
  R7[Torch Head Amalgam: Atk(20)+Queen: Buff, Defend]: Leg Sweep(+10blk,1+Weak(2))->Blade Dance+(1dmg,+1blk,exhaust:1)->Shiv(+1blk)->Shiv(1dmg,+1blk)->Shiv(3dmg,+1blk,1Poison(5→6))->Shiv(8dmg,+1blk,1Poison(6→7)) | dealt=13 taken=5
  R8[Torch Head Amalgam: Atk(21)+Queen: Buff, Defend]: Backflip+(+8blk)->Backflip(+6blk)->Cloak and Dagger+(+7blk)->Shiv(8dmg,+1blk,1+Poison(1))->Shiv(8dmg,+1blk,1Poison(1→2)) | dealt=16 taken=0
  R9[Torch Head Amalgam: Atk(15x3=45)+Queen: Buff, Defend]: Cloak and Dagger+(+7blk)->Leading Strike(4dmg,+1blk,1Poison(1→2))->Leading Strike+(6dmg,+1blk,1Poison(2→3))->Shiv(7dmg,+1blk,1Poison(3→4))->Shiv(7dmg,+1blk,1Poison(4→5))->Shiv(8dmg,+1blk,1Poison(5→6))->Shiv(8dmg,+1blk,1Poison(6→7))->Shiv(8dmg,+1blk,1Poison(7→8))->Shiv(8dmg,+1blk,1Poison(8→9)) | dealt=56 taken=0

### Non-combat Decisions (202 decisions)
F1 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Lava Rock provides excellent long-term scaling by granting an extra boss relic. While it offers no immediate combat power, the payoff at the end of Act 1 is incredibly strong for the rest of the run.
  strategic_note: Foundation deck: rely on basic strikes and defends. Focus on drafting damage cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=2) | source=llm
  HP 56->56 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Following the recommended route to start with monster combats. Early monsters are essential for building the deck's damage potential and securing gold before the mid-act shops and elites.
  strategic_note: Foundation deck: rely on basic strikes and defends. Focus on drafting efficient damage and block cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 111->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim potion: Power Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 111->111 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 56->56 | Gold 111->111 | Deck 12->13
  deck_change: picked Poisoned Stab
  reasoning: Poisoned Stab offers immediate frontload damage plus poison scaling, which is exactly what we need on Floor 2 to start taking down Act 1 hallway fights and elites efficiently. It gives the best damage-to-energy ratio early on.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine. We have Poisoned Stab, so we might lean into poison if we see strong enablers, but stay open.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 111->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 111->119 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 119->119 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 53->53 | Gold 119->119 | Deck 13->14
  deck_change: picked Blade Dance
  reasoning: Blade Dance provides 12 damage for 1 energy, which is excellent frontload for Act 1 and a core engine piece for Shiv strategies.
  strategic_note: Foundation plan: survive with frontload damage like Blade Dance and Poisoned Stab, leaning towards Shivs. Still need better mitigation and draw to fully commit.

F3 [map] choose_map_node (option_index=1) | source=llm
  HP 53->53 | Gold 119->119 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended path to hit an early shop. With 119 gold, I can afford a card removal to thin the deck of basics or pick up a key uncommon card/potion to prepare for upcoming elites. While early, this allows for immediate deck refinement before the mid-act difficulty spike.
  strategic_note: Foundation deck: rely on basic strikes and defends. Focus on drafting damage cards to survive Act 1 elites, since our Ancient Relic provides no immediate combat benefit.

F4 [shop] buy_card (option_index=4) | source=plan
  HP 53->53 | Gold 119->80 | Deck 14->15
  deck_change: bought Accuracy
  reasoning: Shop plan [1/2]: On sale and synergizes perfectly with our existing Blade Dance, establishing a powerful core engine early in Act 1.

F4 [shop] remove_card_at_shop | source=plan
  HP 53->53 | Gold 80->80 | Deck 15->15
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Removing a Strike increases the frequency of drawing our key cards like Blade Dance, Accuracy, and Survivor.

F4 [card_select] select_deck_card (option_index=0) | source=llm
  HP 53->53 | Gold 80->5 | Deck 15->14
  deck_change: lost Strike
  reasoning: Strikes are the weakest cards in the deck, especially since we are assembling a Shiv engine with Blade Dance and Accuracy. Removing a Strike improves the consistency of drawing our better damage and block cards.
  strategic_note: Committed shiv plan: play Blade Dance with Accuracy to burst down enemies. Prioritize more shiv generation, card draw to cycle them, and reliable defense while avoiding cards that don't scale with shivs.

F4 [shop] close_shop_inventory | source=llm
  HP 53->53 | Gold 5->5 | Deck 14->14
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F4 [shop] proceed | source=auto
  HP 53->53 | Gold 5->5 | Deck 14->14
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 5->5 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Unknown

F5 [event] choose_event_option (option_index=1) | source=llm
  HP 53->53 | Gold 5->5 | Deck 14->14
  deck_change: no deck change
  reasoning: Removing a basic card (Strike) improves the consistency of drawing our better cards like Blade Dance and Poisoned Stab.
  strategic_note: Foundation deck transitioning to Shivs: rely on Blade Dance and Accuracy for damage. Focus on drafting more Shiv synergy, block, and card draw while prioritizing targeted removals of basic cards.

F5 [card_select] select_deck_card (option_index=0) | source=llm
  HP 53->53 | Gold 5->5 | Deck 14->13
  deck_change: lost Strike
  reasoning: Strikes are poor damage cards and dilute our draws. Since we already have Blade Dance and Accuracy as a core shiv engine, we want to remove a Strike to draw our key cards faster.
  strategic_note: Committed shiv plan: play Blade Dance with Accuracy to deal massive damage, looking for more Shiv generators, draw, and defense. Remove Strikes at every opportunity.

F5 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 5->5 | Deck 13->13
  deck_change: no deck change
  reasoning: Only option: Proceed

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 5->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Only path: Monster

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 5->15 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 15->15 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Powdered Demise

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 15->15 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 53->53 | Gold 15->15 | Deck 13->14
  deck_change: picked Leading Strike
  reasoning: Leading Strike is a direct synergy with Accuracy, providing more Shivs to take advantage of our core scaling piece. With Accuracy played, it deals 19 damage for 1 energy.
  strategic_note: Committed shiv plan: play Accuracy early, then burst with Blade Dance and Leading Strike. Need card draw (Backflip, Acrobatics) and block/defense to sustain our engine.

F6 [map] choose_map_node (option_index=0) | source=llm
  HP 53->53 | Gold 15->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to the Unknown node. At 53 HP, I am healthy enough to bypass the Rest Site and seek an event that might provide a deck upgrade or gold, keeping on track for the late-act Elite and Shop.
  strategic_note: Foundation deck: currently relying on basics. Priority is drafting front-loaded damage and efficient block to handle Act 1 elites, as Lava Rock offers no immediate combat power.

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 15->25 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 44->44 | Gold 25->25 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F7 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 44->44 | Gold 25->25 | Deck 14->14
  deck_change: no deck change
  reasoning: None of these cards support the Shiv/Accuracy engine. Precise Cut is anti-synergistic with Shiv-generating cards filling the hand, Slice is low-impact, and Tactician is a curse without more discard outlets (we only have Survivor). Skipping to keep the deck lean.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale. Avoid generic attacks and poison cards.

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 44->44 | Gold 25->25 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: RestSite

F8 [rest_site] choose_rest_option (option_index=1, smith_card_index=11, note_scope=run, note_triggers=all) | source=llm
  HP 44->44 | Gold 25->25 | Deck 14->14
  deck_change: upgraded Blade Dance->Blade Dance+
  reasoning: With 44 HP, we are safe enough to Smith. Upgrading Blade Dance gives us an extra Shiv, which synergizes perfectly with Accuracy and significantly increases our burst damage.
  strategic_note: Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for damage. Prioritize drawing and playing Shiv generators, while drafting more block and card draw.

F8 [rest_site] proceed | source=auto
  HP 44->44 | Gold 25->25 | Deck 14->14
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 44->44 | Gold 25->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Monster

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 25->39 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 42->42 | Gold 39->39 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F9 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 42->42 | Gold 39->39 | Deck 14->15
  deck_change: picked Leading Strike
  reasoning: We have committed to a Shiv engine with Accuracy and Blade Dance+. Leading Strike feeds this engine perfectly, generating 2 Shivs which will deal 8 damage each with Accuracy active, resulting in 19 total damage for 1 energy.
  strategic_note: Committed shiv plan: play Accuracy early, then generate and play Shivs for massive efficient damage. Look for card draw (Acrobatics, Backflip) to cycle the deck and find the Shiv generators faster. Avoid expensive off-plan cards.

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 42->42 | Gold 39->39 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 42->42 | Gold 39->71 | Deck 15->15
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 42->42 | Gold 71->71 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim: Centennial Puzzle

F10 [treasure] proceed | source=random
  HP 42->42 | Gold 71->71 | Deck 15->15
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=llm
  HP 42->42 | Gold 71->0 | Deck 15->15
  deck_change: no deck change
  reasoning: We have 42 HP and a solid Shiv foundation (Blade Dance+, Accuracy). While the route guide suggests caution with elites, we have the necessary damage density to take one down at this stage of Act 1, and the treasure chest just provided a power spike or resources. Defeating an elite now is crucial for scaling into the late game and the boss.
  strategic_note: Foundation shiv deck: use Blade Dance and Accuracy for primary scaling while prioritizing card draw and defensive layers like Piercing Wail or Leg Sweep. Target removals of basic Strikes to increase deck density.

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 71->102 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 31 Gold

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 102->102 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim relic: Planisphere

F11 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 102->102 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F11 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 35->35 | Gold 102->102 | Deck 15->16
  deck_change: picked Backflip
  reasoning: The deck is committed to a Shiv scaling plan with Accuracy and Blade Dance. To keep the engine running and find our scaling pieces consistently, we desperately need draw. Backflip provides essential card draw while adding block, directly addressing a critical weakness in our current deck.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage. Prioritize card draw (Backflip, Acrobatics) and defensive scaling to survive longer fights, while avoiding bloat from generic damage cards.

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 35->40 | Gold 102->102 | Deck 16->16
  deck_change: no deck change
  reasoning: With 35 HP, I need to stabilize before the next mandatory combats. The Planisphere relic makes the Unknown node particularly valuable here as it provides a guaranteed 5 HP heal regardless of the event, which is safer than taking a Monster fight at this health level.
  strategic_note: Foundation Shiv deck: stack Shiv generation and Accuracy for damage while prioritizing block to mitigate HP loss. Currently low on HP, so I must favor ? nodes for Planisphere healing and avoid unnecessary chip damage until the next rest site.

F12 [treasure] open_chest | source=random
  HP 40->40 | Gold 102->133 | Deck 16->16
  deck_change: no deck change
  reasoning: Open chest

F12 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 40->40 | Gold 133->133 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim: Strike Dummy

F12 [treasure] proceed | source=random
  HP 40->40 | Gold 133->133 | Deck 16->16
  deck_change: no deck change
  reasoning: Proceed from treasure

F12 [map] choose_map_node (option_index=0) | source=llm
  HP 40->40 | Gold 133->133 | Deck 16->16
  deck_change: no deck change
  reasoning: With 40 HP and a deck still in the early stages of transitioning to a Shiv core, the Rest Site is the much safer and more productive option over an Elite. My current route guidelines advise limiting elites and prioritizing late-act upgrades. The Rest Site allows me to Smith a key card like Accuracy or Blade Dance, providing a permanent power spike for the upcoming Boss fight and final hallway combats.
  strategic_note: Foundation Shiv deck: stack Accuracy and Blade Dance for scaling damage while searching for Footwork or Leg Sweep to stabilize defense. Prioritize upgrading Accuracy to maximize Shiv value and use shops for card removals or finding key draw pieces.

F13 [rest_site] choose_rest_option (option_index=1, smith_card_index=11, note_scope=run, note_triggers=all) | source=llm
  HP 40->40 | Gold 133->133 | Deck 16->16
  deck_change: upgraded Accuracy->Accuracy+
  reasoning: Upgrading Accuracy increases Shiv damage significantly, which is our main engine for damage output. With 40 HP and another rest site before the boss, we can afford to upgrade now and potentially heal later if we take damage in the upcoming hallways.
  strategic_note: Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw.

F13 [rest_site] proceed | source=auto
  HP 40->40 | Gold 133->133 | Deck 16->16
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 133->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 133->148 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 148->148 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 148->148 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 40->40 | Gold 148->148 | Deck 16->17
  deck_change: picked Phantom Blades
  reasoning: Phantom Blades is a premium Shiv scaling power. It perfectly complements our existing Accuracy+, Blade Dance+, and Leading Strikes, providing huge frontloaded damage and combo potential by retaining unused shivs for later turns.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance, Leading Strike, Accuracy, and Phantom Blades for core damage. Needs more card draw and defense to survive while setting up powers.

F14 [map] choose_map_node (option_index=1) | source=llm
  HP 40->40 | Gold 148->0 | Deck 17->17
  deck_change: no deck change
  reasoning: With 40 HP and a deck still in its foundation phase, taking an elite fight (index 0) right before the boss is too risky. The monster node (index 1) provides a safer path to the final rest site, allowing for a crucial upgrade or necessary heal before the Act 1 boss.
  strategic_note: Foundation Shiv deck: use Blade Dance and Accuracy for primary scaling while prioritizing card draw and consistent block. Avoid unnecessary elites until the deck has more front-loaded block or reliable damage mitigation; focus on upgrading core Shiv pieces at rest sites.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 148->155 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F15 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 40->40 | Gold 155->155 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 40->40 | Gold 155->155 | Deck 17->18
  deck_change: picked Backflip
  reasoning: We are heavily committed to a Shiv engine (Accuracy+, Phantom Blades) but have a 17-card deck with only one draw card. Backflip provides crucial cycle to find our engine pieces faster while giving generic block.
  strategic_note: Committed shiv plan: play Accuracy and Phantom Blades, then spam shivs. Needs more card draw (Acrobatics/Backflip) and defensive scaling (Footwork/Afterimage); avoid bloating the deck with generic attacks.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 155->155 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 40->61 | Gold 155->155 | Deck 18->18
  deck_change: no deck change
  reasoning: With the Act 1 Boss immediately ahead and 40/70 HP, I need to heal to ensure survival. Healing for 21 HP brings me to 61/70, significantly improving my chances against the boss's heavy attacks.
  strategic_note: Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw.

F16 [rest_site] proceed | source=auto
  HP 61->61 | Gold 155->155 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 61->61 | Gold 155->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [card_select] select_deck_card (option_index=1) | source=llm
  HP 61->61 | Gold 155->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Serpent Form is a massive scaling power that pairs perfectly with shivs and zero-cost cards. Since it came from a Power Potion, it will cost 0 to play this turn, providing an immediate and massive boost to our damage output against the Act 1 Boss.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance and Accuracy for core damage, supplemented by per-card damage like Serpent Form. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale.

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 155->230 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 230->230 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 230->230 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim relic: Book of Five Rings

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 230->230 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim relic: Molten Egg

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 230->230 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 48->48 | Gold 230->230 | Deck 18->19
  deck_change: picked Afterimage
  reasoning: Afterimage is the premier defensive engine for a Shiv deck. With Blade Dance+ and Leading Strikes, we will be playing a massive volume of cards every turn, allowing Afterimage to passively generate enough block to survive Act 2 and 3 fights while we deal damage.
  strategic_note: Committed Shiv plan: scale damage with Accuracy/Phantom Blades, generate massive Shivs with Blade Dance/Leading Strike, and block passively with Afterimage. Need more draw (Acrobatics/Calculated Gamble) and perhaps one more premium Shiv generator. Avoid generic frontload.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 48->65 | Gold 230->230 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 65->65 | Gold 230->230 | Deck 19->19
  deck_change: changed: +Suppress+; -Neutralize
  reasoning: Archaic Tooth transforms Neutralize into Suppress, an Innate 0-cost attack that deals 11 damage and applies 3 Weak. This provides incredible consistent mitigation on turn 1 of every combat, which is extremely valuable in Act 2 to prevent taking damage while setting up our Shiv engine (Accuracy+, Phantom Blades, Afterimage).
  strategic_note: Committed to Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drawing and playing Shiv generators while drafting more block and card draw. Suppress provides reliable turn 1 damage mitigation.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 65->65 | Gold 230->230 | Deck 19->19
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 65->65 | Gold 230->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Following the recommended route to accumulate gold and card rewards. My current HP is high (65/70), making hallway fights the best way to strengthen the deck before the upcoming shop and rest sites.
  strategic_note: Foundation Shiv deck: stack Shiv generation with Accuracy and focus on high-efficiency block and card draw; prioritize upgrades for core scaling pieces and keep HP high to avoid resting.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 230->242 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 242->242 | Deck 18->19
  deck_change: picked Accuracy+
  reasoning: Claim specialcard: Take your stolen card back.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 63->63 | Gold 242->242 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 63->63 | Gold 242->242 | Deck 19->20
  deck_change: picked Leading Strike+
  reasoning: Leading Strike+ comes upgraded thanks to Molten Egg and benefits massively from Strike Dummy (+3 damage on the base hit), Accuracy+ (+6 damage per Shiv), Phantom Blades, and Afterimage (3 cards played = 3 block). It perfectly feeds our core Shiv engine.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and Phantom Blades, use Afterimage to convert Shiv spam into block. Prioritize draw and card removal to find our engine pieces faster; avoid off-plan attacks.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 63->63 | Gold 242->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 242->249 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 249->249 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 59->70 | Gold 249->249 | Deck 20->21
  deck_change: picked Dagger Spray+
  reasoning: The deck currently lacks AoE damage, which is critical for Act 2 fights like Slavers, Gremlin Leader, and multi-enemy hallways. Thanks to Molten Egg, Dagger Spray is pre-upgraded, providing 12 AoE damage for 1 energy, perfectly filling that gap.
  strategic_note: Committed shiv plan: play Phantom Blades and Accuracy, generate Shivs to trigger Afterimage block and scale damage. Still need more card draw (Acrobatics/Calculated Gamble) and deck manipulation to cycle faster.

F20 [map] choose_map_node (option_index=1) | source=llm
  HP 70->70 | Gold 249->249 | Deck 21->21
  deck_change: no deck change
  reasoning: With 249 gold and the Planisphere relic, Unknown nodes are high value. Planisphere provides 5 HP sustain per ?, helping maintain health for the upcoming shop and upgrades. The Monster node at index 0 is less optimal than fishing for a beneficial event or an easy chest/shop encounter given our current resources.
  strategic_note: Committed Shiv engine: prioritize Accuracy and Shiv generators like Blade Dance. Use high gold reserves to refine the deck at shops, focusing on card removal and upgraded block/draw pieces to support the high-volume offensive turns.

F21 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 70->70 | Gold 249->349 | Deck 21->21
  deck_change: no deck change
  reasoning: Taking the guaranteed 100 Gold is risk-free and sets us up with 349 Gold for the upcoming shop at Floor 25, allowing for a key relic purchase or card removals.
  strategic_note: Committed Shiv engine: play Accuracy and Phantom Blades early, then cycle Blade Dance and Leading Strike. Prioritize card removal and block/draw at shops.

F21 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 349->349 | Deck 21->21
  deck_change: no deck change
  reasoning: Only option: Proceed

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 349->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Monster

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 349->364 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 364->364 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 62->62 | Gold 364->364 | Deck 21->22
  deck_change: picked Expose
  reasoning: Expose is a 0-cost card that strips Artifact and Block, while applying Vulnerable to set up our massive Shiv burst turns. It covers a utility gap since we currently have no Vulnerable or Artifact stripping.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance, Leading Strike, and Accuracy for core damage. Retain Shivs with Phantom Blades for burst turns. Needs more draw (Acrobatics/Calculated Gamble) to cycle faster. Avoid generic attacks.

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 62->62 | Gold 364->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 364->375 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 49->49 | Gold 375->375 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 49->49 | Gold 375->375 | Deck 22->23
  deck_change: picked Backflip+
  reasoning: Backflip+ provides exactly what the Shiv engine needs: efficient block and card draw to find our powers and Shiv generators faster.
  strategic_note: Committed to Shiv scaling plan: use Blade Dance, Leading Strike, and Accuracy for core damage. Needs card draw, defense (Afterimage/Footwork), and more Shiv generation to scale. Avoid generic attacks and poison cards.

F23 [map] choose_map_node (option_index=1) | source=llm
  HP 49->54 | Gold 375->375 | Deck 23->23
  deck_change: no deck change
  reasoning: With 375 Gold and Planisphere, prioritizing Unknowns and Shops is the optimal path to avoid high-damage Act 2 hallways while scaling through card removals and relics. Healing 5 HP per Unknown room via Planisphere makes this route extremely safe.
  strategic_note: Committed Shiv engine: play Accuracy early, then cycle Blade Dance and Leading Strike for massive damage; prioritize drawing and playing Shiv generators while drafting more block and card draw.

F24 [treasure] open_chest | source=random
  HP 54->54 | Gold 375->411 | Deck 23->23
  deck_change: no deck change
  reasoning: Open chest

F24 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 54->54 | Gold 411->411 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim: Potion Belt

F24 [treasure] proceed | source=random
  HP 54->54 | Gold 411->411 | Deck 23->23
  deck_change: no deck change
  reasoning: Proceed from treasure

F24 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 411->411 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Shop

F25 [shop] buy_card (option_index=4) | source=plan
  HP 54->54 | Gold 411->372 | Deck 23->24
  deck_change: bought Phantom Blades
  reasoning: Shop plan [1/6]: Sale item and incredible synergy. A second Phantom Blades adds another +9 damage to the first Shiv played each turn, heavily scaling our burst.

F25 [shop] buy_card (option_index=0) | source=plan
  HP 54->54 | Gold 372->298 | Deck 24->25
  deck_change: bought Finisher+
  reasoning: Shop plan [2/6]: Huge damage payoff for our Shiv turns. Already upgraded, so it deals 8 damage per attack played.

F25 [shop] buy_card (option_index=3) | source=plan
  HP 54->70 | Gold 298->223 | Deck 25->26
  deck_change: bought Leg Sweep
  reasoning: Shop plan [3/6]: Premium damage mitigation. 2 Weak and 11 Block solves many heavy-hitting boss turns.

F25 [shop] buy_card (option_index=2) | source=plan
  HP 70->70 | Gold 223->174 | Deck 26->27
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [4/6]: Provides more Shiv generation for Finisher/Phantom Blades and triggers Afterimage.

F25 [shop] remove_card_at_shop | source=plan
  HP 70->70 | Gold 174->174 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [5/6]: Remove a Strike to increase consistency.

F25 [card_select] select_deck_card (option_index=0) | source=llm
  HP 70->70 | Gold 174->74 | Deck 27->26
  deck_change: lost Strike
  reasoning: We are heavily committed to a Shiv engine (Phantom Blades, Accuracy, Afterimage, Blade Dance). Strike, even with Strike Dummy, is an inefficient use of energy and hand space compared to generating and scaling Shivs or playing block.
  strategic_note: Committed Shiv plan: scale damage rapidly with Accuracy and Phantom Blades, block passively with Afterimage, and draw through the deck with Backflips. Needs more draw/discard or energy generation; avoid basic attacks.

F25 [shop] buy_potion (option_index=1) | source=plan
  HP 70->70 | Gold 74->22 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan [6/6]: We have an empty potion slot, good for stripping artifact or adding extra damage.

F25 [shop] close_shop_inventory | source=plan
  HP 70->70 | Gold 22->22 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F25 [shop] proceed | source=auto
  HP 70->70 | Gold 22->22 | Deck 26->26
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F25 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 22->22 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Treasure

F26 [treasure] open_chest | source=random
  HP 70->70 | Gold 22->53 | Deck 26->26
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 70->70 | Gold 53->53 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim: Bronze Scales

F26 [treasure] proceed | source=random
  HP 70->70 | Gold 53->53 | Deck 26->26
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=1) | source=llm
  HP 70->70 | Gold 53->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the Route Intelligence for Act 2 which prioritizes avoiding Elites to preserve health. Although I am at full HP, Act 2 elites can be extremely punishing for setup-heavy decks like this Shiv engine (Accuracy/Phantom Blades). The Monster node provides gold and a card reward with lower risk than the Elite, keeping me healthy for the upcoming nodes.
  strategic_note: Committed Shiv engine: play Accuracy and Phantom Blades early, then cycle Blade Dance and Leading Strike for massive damage. Prioritize drafting block and card draw while using shops for card removal to keep the deck lean; avoid elites in Act 2 to preserve HP.

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 53->67 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Touch of Insanity

F27 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F27 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: no deck change
  reasoning: The offered cards all rely on the Sly mechanic (discarding to play for free), but our deck only has Survivor as a discard outlet. Without more discard support like Acrobatics or Prepared, Tactician and Haze are dead 3-cost draws, and Flick-Flack is mediocre. Skipping to keep the deck focused on the core Shiv engine.
  strategic_note: Committed Shiv plan: utilize Phantom Blades and Accuracy to scale Shiv damage, block with Backflips and Afterimage, and finish with Finisher. Needs more card draw (Acrobatics) and energy; skip discard synergies until multiple discard outlets are present.

F27 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: RestSite

F28 [rest_site] choose_rest_option (option_index=1, smith_card_index=18, note_scope=run, note_triggers=all) | source=llm
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: upgraded Cloak and Dagger->Cloak and Dagger+
  reasoning: At full HP, so we must Smith. Upgrading Cloak and Dagger doubles its Shiv generation from 1 to 2, which has massive synergy with our Accuracy, Phantom Blades, Finisher, and Afterimage.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.

F28 [rest_site] proceed | source=auto
  HP 70->70 | Gold 67->67 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F28 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 67->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 67->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F29 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 62->62 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F29 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 62->62 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: The deck currently has 26 cards with 3 Backflips already. With only 3 energy and no consistent energy generation (like Adrenaline or Tactician), adding more 1-cost draw or block cards will lead to hand clutter and energy starvation. Skipping keeps the deck focused on our existing Shiv engine and limits bloat.
  strategic_note: Committed Shiv plan: Generate Shivs, buff them with Accuracy and Phantom Blades, and use Afterimage/Backflips for defense. Need energy generation (Adrenaline) or strong relics; skip cards that don't directly enhance the engine or provide energy.

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 62->67 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Unknown

F30 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 67->53 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: We have plenty of HP (67/70) and a rest site coming up before the boss. Taking 14 damage for a relic that provides steady Max HP scaling throughout Act 3 is an excellent trade. Gorge would likely just bloat our refined Shiv engine with unnecessary common cards.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.

F30 [event] choose_event_option (option_index=0) | source=auto
  HP 53->53 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F30 [map] choose_map_node (option_index=0) | source=auto
  HP 53->53 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Unknown

F31 [event] choose_event_option (option_index=0) | source=auto
  HP 53->58 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=1, smith_card_index=14, note_scope=run, note_triggers=all) | source=llm
  HP 58->58 | Gold 82->82 | Deck 26->26
  deck_change: upgraded Afterimage->Afterimage+
  reasoning: Missing only 12 HP, so resting wastes a lot of the heal. Upgrading Afterimage to gain Innate is incredibly valuable for our Shiv engine, as it guarantees we start generating block on turn 1, which will save more than 12 HP against the Act 2 boss.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Continue prioritizing card removal and draw.

F32 [rest_site] proceed | source=auto
  HP 58->58 | Gold 82->82 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 82->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 82->157 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 157->157 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 39->39 | Gold 157->157 | Deck 26->27
  deck_change: picked Envenom
  reasoning: Envenom provides incredible scaling damage by turning every Shiv we play into poison, allowing us to melt bosses easily. We have multiple Leading Strikes, Blade Dance, and Cloak and Dagger to generate tons of Shivs.
  strategic_note: Committed shiv plan: play Phantom Blades and Accuracy for upfront damage, set up Afterimage for block, and use Envenom to scale against bosses. Need more draw/energy or cheap block to keep the engine running.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 39->64 | Gold 157->157 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 64->64 | Gold 157->157 | Deck 27->27
  deck_change: no deck change
  reasoning: Preserved Fog removes 3 basic cards (Strikes/Defends), significantly improving deck consistency and allowing us to draw our key powers and Shiv generators much faster. The innate Folly curse is easily managed since we have Ring of the Snake for extra Turn 1 draw, and the curse exhausts itself Ethereally at the end of the turn.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators like Blade Dance and Cloak and Dagger for massive damage and block. Continue prioritizing card removal and draw.

F34 [card_select] select_deck_card (option_index=0) | source=llm
  HP 64->64 | Gold 157->157 | Deck 27->25
  deck_change: changed: +Folly; -Defend, Strike x2
  reasoning: Removing the remaining Strikes to improve deck consistency, and one Defend to further thin basic cards. This maximizes the draw probability of our core Shiv engine pieces like Blade Dance, Leading Strike, Accuracy, and Phantom Blades.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and Phantom Blades, defend with Afterimage and Backflips. Needs energy generation (Tactician/Concentrate) or card draw; avoid non-Shiv attacks.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 64->64 | Gold 157->157 | Deck 25->25
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=4) | source=llm
  HP 64->64 | Gold 157->0 | Deck 25->25
  deck_change: no deck change
  reasoning: Following the recommended path towards a high-density non-combat route. Planisphere makes '?' rooms valuable for healing, and the upcoming shop allows for card removal or key power upgrades to solidify the Shiv engine.
  strategic_note: Committed Shiv engine: prioritize Accuracy and Phantom Blades, then cycle Blade Dance and Leading Strike. Seek block and draw while using shops to remove strikes; lean on Planisphere healing in events to avoid rest site healing in favor of upgrades.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 157->168 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 65->65 | Gold 168->168 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 65->65 | Gold 168->168 | Deck 25->26
  deck_change: picked Up My Sleeve+
  reasoning: Up My Sleeve+ generates 4 Shivs, which perfectly fuels our Accuracy+, Phantom Blades, Envenom, and Afterimage+. Its cost reduction makes it an excellent addition for boss fights.
  strategic_note: Committed Shiv scaling plan: use Shiv generators (Blade Dance, Leading Strike, Up My Sleeve) to fuel Accuracy, Phantom Blades, and Finisher for massive damage, while Afterimage provides block and Envenom stacks poison. Retain Shivs for burst turns when needed.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 65->70 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Unknown

F36 [event] choose_event_option (option_index=1) | source=llm
  HP 70->70 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Forgotten Soul is a free, albeit minor, damage boost. Adding a Curse for Soul's Power isn't necessary since we already have ample Shiv generation from Leading Strikes, Cloak and Dagger, and Up My Sleeve.
  strategic_note: Committed Shiv engine: prioritize Accuracy and Phantom Blades, then cycle Blade Dance and Leading Strike. Seek block and draw while using shops to remove strikes; lean on Planisphere healing in events to avoid rest site healing in favor of upgrades.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Unknown

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 70->72 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [event] choose_event_option (option_index=0) | source=auto
  HP 72->72 | Gold 168->168 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F37 [map] choose_map_node (option_index=0) | source=auto
  HP 72->72 | Gold 168->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 73->73 | Gold 168->181 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 73->73 | Gold 181->181 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim potion: Liquid Memories

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 73->73 | Gold 181->181 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 73->73 | Gold 181->181 | Deck 26->27
  deck_change: picked Blade Dance+
  reasoning: We are heavily committed to a Shiv engine with Accuracy+, Phantom Blades x2, Envenom, Afterimage+, and Finisher+. Blade Dance+ provides 4 Shivs for 1 energy, triggering Afterimage+ 5 times and dealing massive damage with our buffs.
  strategic_note: Committed shiv plan: generate massive amounts of shivs to trigger Afterimage for block, apply poison via Envenom, and deal damage via Accuracy and Phantom Blades. Look for more draw (Acrobatics, Backflip) and potentially energy generation.

F38 [map] choose_map_node (option_index=0) | source=auto
  HP 73->73 | Gold 181->181 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Shop

F39 [shop] buy_card (option_index=4) | source=plan
  HP 73->73 | Gold 181->144 | Deck 27->28
  deck_change: bought Footwork
  reasoning: Shop plan [1/2]: On sale and absolutely premium for our deck. Dexterity scales our basic block and Cloak and Dagger, providing excellent layered defense alongside Afterimage+.

F39 [shop] remove_card_at_shop | source=plan
  HP 73->73 | Gold 144->144 | Deck 28->28
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Removing a basic Defend increases our consistency in drawing our core shiv engine, Afterimage, and Footwork.

F39 [card_select] select_deck_card (option_index=0) | source=llm
  HP 73->73 | Gold 144->19 | Deck 28->27
  deck_change: lost Defend
  reasoning: Folly is not available to remove, so I will remove a basic Defend. Our deck generates massive block through Afterimage+, Cloak and Dagger+, Backflips, and Leg Sweep, making basic Defends the weakest links that slow down drawing our core Shiv engine.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and Phantom Blades while generating block passively with Afterimage. Spam shivs to overwhelm enemies. Skip non-shiv attacks and look for draw/energy.

F39 [shop] close_shop_inventory | source=llm
  HP 73->73 | Gold 19->19 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F39 [shop] proceed | source=auto
  HP 73->73 | Gold 19->19 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 73->73 | Gold 19->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Unknown

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 19->34 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F40 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 34->34 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F40 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 66->66 | Gold 34->34 | Deck 27->27
  deck_change: no deck change
  reasoning: None of the offered cards significantly improve our committed Shiv engine. We have plenty of block from Afterimage and Footwork, and our damage comes from Accuracy/Phantom Blades + Shivs. Skipping keeps the deck lean to draw our core scaling pieces faster against the upcoming Act 3 boss.
  strategic_note: Committed Shiv engine: set up Accuracy, Phantom Blades, Afterimage, and Footwork, then cycle Shiv generators for massive damage. Needs rapid draw/energy; skip generic cards to avoid diluting the engine.

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 34->34 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 66->66 | Gold 34->72 | Deck 27->27
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 66->66 | Gold 72->72 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim: Ripple Basin

F41 [treasure] proceed | source=random
  HP 66->66 | Gold 72->72 | Deck 27->27
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=auto
  HP 66->66 | Gold 72->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Elite

F42 [card_select] select_deck_card (option_index=0) | source=llm
  HP 54->54 | Gold 72->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Retrieving Backflip to draw 2 cards and gain block for 0 cost, as per the plan with Liquid Memories.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Continue prioritizing card removal and draw.

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 72->98 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 98->98 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 98->98 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim relic: Reptile Trinket

F42 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 98->98 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F42 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 36->36 | Gold 98->98 | Deck 27->28
  deck_change: picked Cloak and Dagger+
  reasoning: Cloak and Dagger+ fits perfectly into our committed Shiv engine. It provides much-needed block while generating Shivs that synergize with Accuracy, Phantom Blades, Afterimage, and Envenom.
  strategic_note: Committed Shiv engine: set up Afterimage, Accuracy, and Phantom Blades, then spam Shiv generators for massive damage and passive block. Keep looking for card draw and removal.

F42 [map] choose_map_node (option_index=1) | source=llm
  HP 36->36 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: With 36/75 HP and a 'Committed Shiv engine', I need to reach the next Elite/Boss safely. The route guide suggests avoiding combats in Act 3 when possible, and my current HP is below the safe threshold for a regular monster fight that might chip me down further. Resting now ensures I can survive the upcoming forced Elite or reach the subsequent rest site to upgrade a key card like Accuracy.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Priority is now securing HP for the final gauntlet while looking for draw power to ensure key pieces are found quickly.

F43 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 36->58 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: With 36 HP and back-to-back Elites coming up, resting to 58 HP ensures we don't die to a bad turn 2 against Reptomancer or Nemesis. We can smith at the final rest site before the boss.
  strategic_note: Committed Shiv engine: set up Accuracy, Phantom Blades, and Afterimage, then use Shiv generators for block and high damage. Prioritize Footwork and Leg Sweep for survivability. Needs to remove strikes/defends.

F43 [rest_site] proceed | source=auto
  HP 58->58 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F43 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 98->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Elite

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 98->131 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 33 Gold

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 131->131 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 131->131 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim relic: Art of War

F44 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 131->131 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F44 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 47->47 | Gold 131->131 | Deck 28->28
  deck_change: no deck change
  reasoning: We already have three copies of Leading Strike and plenty of other Shiv generators (Blade Dance, Cloak and Dagger, Up My Sleeve) but only 3 energy per turn. Adding another 1-cost attack would bloat the deck without improving our core dimensions of draw or energy.
  strategic_note: Committed Shiv/Envenom engine. Rely on Phantom Blades and Accuracy to scale Shiv damage, while Envenom stacks poison. Prioritize card draw (Acrobatics/Calculated Gamble) and energy to play our expensive setup cards. Avoid adding more 1-cost attacks.

F44 [map] choose_map_node (option_index=0) | source=auto
  HP 47->47 | Gold 131->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Monster

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 131->143 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 143->143 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim potion: Speed Potion

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 47->47 | Gold 143->143 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 47->47 | Gold 143->143 | Deck 28->29
  deck_change: picked Tracking
  reasoning: Tracking doubles our attack damage against Weak targets. Since we have Suppress+ (Innate, 0 cost, applies 5 Weak) and a ton of Shiv generation with Accuracy+ and Phantom Blades, Tracking acts as a massive multiplicative damage scaler that will let us burst down Act 3 bosses and elites quickly.
  strategic_note: Committed Shiv plan: burst enemies down with Tracking + Suppress+ and massive Shiv generation. Prioritize draw and energy, skip non-Shiv attacks.

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 47->47 | Gold 143->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Elite

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 143->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 32 Gold

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim relic: Lantern

F46 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 32->32 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F46 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 32->32 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Our deck is a committed Shiv engine with plenty of damage scaling (Accuracy, Phantom Blades, Envenom, Finisher). None of the offered cards (Snakebite+, Precise Cut+, Slice+) improve the deck's core strategy. Precise Cut and Slice conflict with our Shiv generation, and Snakebite is too expensive for a non-poison deck. Skipping to keep the deck lean and consistent.
  strategic_note: Committed Shiv engine: retain Phantom Blades and Accuracy pieces, cycle Blade Dance and Cloak and Dagger, scale damage with Shivs and Finisher. Needs block/draw consistency; avoid off-plan damage cards.

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 32->32 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 32->55 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Boss is the next floor, and we are at 41% HP. Healing is crucial to survive the final gauntlet, bringing us up to 55 HP.
  strategic_note: Committed Shiv engine: play Accuracy, Phantom Blades, and Afterimage early, then cycle Shiv generators for massive damage and block. Boss is next, play for survival.

F47 [rest_site] proceed | source=auto
  HP 55->55 | Gold 175->175 | Deck 29->29
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 55->55 | Gold 175->0 | Deck 29->29
  deck_change: no deck change
  reasoning: Only path: Boss

## Selected Replay Package (8 replays)
[Selected: run_combat] Punch Construct (F7, monster)
Historical: loss=9 vs historical avg=2.7+/-3.1 (z=2.0, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs Punch Construct (Floor 7, monster)
Relics: Ring of the Snake, Lava Rock
Deck (14): Defend x5, Strike x3, Accuracy, Blade Dance, Leading Strike, Neutralize, Poisoned Stab, Survivor
Enemies: Punch Construct HP=55/55

### Round 1
Agent plan (hypothesis): Enemy attacks heavily next turn, save block cards.
Intent: Punch Construct: Defend
  Neutralize -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -3, -Artifact
  Poisoned Stab -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6, +Poison(3)
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6
  turn_end

### Round 2
Agent plan (hypothesis): Enemy attacks for 10 and debuffs next turn. Prepare to block and finish them off.
Intent: Punch Construct: Attack(14)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Blade Dance
    energy -1 | exhausted: Blade Dance [1]: Add 3 Shivs into your Hand. Exhaust.
  Shiv -> Punch Construct[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Punch Construct: block -4
  Shiv -> Punch Construct[0]
    enemy_deltas: Punch Construct: block -4
  Shiv -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -2, block -2
  turn_end

### Round 3
Agent plan (hypothesis): Enemy defends next turn. Secure the kill with the remaining attacks.
Intent: Punch Construct: Attack(5x2=10), Debuff
  Defend
    energy -1 | block +5
  Poisoned Stab -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6, Poison(1→4)
  Accuracy
    energy -1 | +Accuracy(4)
  turn_end

### Round 4
Agent plan (hypothesis): Combat ends.
Intent: Punch Construct: Defend
  Leading Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -2
  Shiv -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -6
  Shiv -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -6
  turn_end
## Combat Analytics: Punch Construct (WIN - 4 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 1 plays, 3 dmg
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 2 plays, 12 dmg, +6 poison
  Strike "Deal 6 damage." -> 2 plays, 12 dmg
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 5 plays, 14 dmg, EXHAUST
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 1 plays, 2 dmg, generates 2 Shivs

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~8 dmg
  Leading Strike: 2 Shivs -> ~6 dmg

Poison stacks applied per card:
  Poisoned Stab: 6 stacks

Enemy power timeline:
  Artifact: R1:1 -> R2:- -> R3:- -> R4:-
  Poison: R1:- -> R2:2 -> R3:1 -> R4:3
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Punch Construct (Floor 6, monster)
Relics: Ring of the Snake, Precise Scissors, Bag of Preparation
Deck (15): Defend x5, Strike x4, Cloak and Dagger, Clumsy, Neutralize, Pounce, Sucker Punch, Survivor
Enemies: Punch Construct HP=55/55

### Round 1
Intent: Punch Construct: Defend
  Neutralize -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -3, -Artifact
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Punch Construct[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Punch Construct: hp -4
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6
  turn_end
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.

### Round 2
Intent: Punch Construct: Attack(14)
  Sucker Punch -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: block -8, +Weak(1)
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 3
Intent: Punch Construct: Attack(5x2=10), Debuff
  Pounce -> Punch Construct[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Punch Construct: hp -12
  Defend
    block +5 | -Free Skill
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Punch Construct: Defend
  Sucker Punch -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -6, +Weak(1)
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -4
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: hp -4
  turn_end

### Round 5
Intent: Punch Construct: Attack(14)
  Neutralize -> Punch Construct[0]
    enemy_deltas: Punch Construct: block -3, +Weak(1)
  Pounce -> Punch Construct[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Punch Construct: hp -5, block -7
  Cloak and Dagger
    block +6 | -Free Skill
  Shiv -> Punch Construct[0]
    enemy_deltas: Punch Construct: hp -4
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Punch Construct: Attack(5x2=10), Debuff
  Strike -> Punch Construct[0]
    energy -1 | enemy_deltas: Punch Construct: DIED
## Combat Analytics: Punch Construct (WIN - 6 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 3 dmg
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 2 plays, 12 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 8 dmg, EXHAUST
  Strike "Deal 6 damage." -> 5 plays, 20 dmg
  Sucker Punch "Deal 8 damage. Apply 1 Weak." -> 2 plays, 6 dmg
  Defend "Gain 5 Block." -> 4 plays, 20 block
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 2 plays, 17 dmg

Token attribution (Shivs):
  Cloak and Dagger: 2 Shivs -> ~8 dmg

Enemy power timeline:
  Artifact: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-

[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F11, elite)
Historical: loss=7 vs historical avg=0.3+/-0.5 (z=14.1, WORSE_THAN_USUAL, n=3)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 11, elite)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle
Deck (15): Defend x5, Strike x3, Leading Strike x2, Accuracy, Blade Dance+, Neutralize, Poisoned Stab, Survivor
Enemies: Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=30/30

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Accuracy
    energy -1 | +Accuracy(4)
  Blade Dance+
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust.
  Shiv -> Phantasmal Gardener[2]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Shiv -> Phantasmal Gardener[2]
  Shiv -> Phantasmal Gardener[2]
  Shiv -> Phantasmal Gardener[2]
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 2
Agent plan (hypothesis): Poison kills before attack intents resolve.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(7)
  Neutralize -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -3, block +6, +Weak(1)
  Leading Strike -> Phantasmal Gardener[2]
    energy -1 | enemy_deltas: Phantasmal Gardener: block -3
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -5, block -3
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -8
  Poisoned Stab -> Phantasmal Gardener[2]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, +Poison(3)
  Strike -> Phantasmal Gardener[2]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3)
  Neutralize -> Phantasmal Gardener[0]
  Poisoned Stab -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 4
Agent plan (hypothesis): Skittish pops after first damage, use big hits after.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  Leading Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block +6
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -2, block -6
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -8
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(7)
  Leading Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block +6
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -2, block -6
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -8
  Poisoned Stab -> Phantasmal Gardener[0]
    energy -1 | -Accuracy | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 5 rounds)

Cards played (with descriptions):
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Shiv "Deal 8 damage. Exhaust." -> 12 plays, 33 dmg, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 2 plays, 3 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 4 plays, 6 dmg, generates 2 Shivs
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 3 plays, 6 dmg, +3 poison
  Strike "Deal 6 damage." -> 3 plays, 6 dmg

Token attribution (Shivs):
  Leading Strike: 8 Shivs -> ~22 dmg
  Blade Dance+: 4 Shivs -> ~11 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:2 -> R5:-
  Skittish: R1:- -> R2:- -> R3:- -> R4:- -> R5:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:-
  Skittish[2]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:-
  Skittish[3]: R1:6 -> R2:- -> R3:- -> R4:- -> R5:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:2 -> R5:2
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 14, elite)
Relics: Ring of the Snake, Precise Scissors, Bag of Preparation, Oddly Smooth Stone
Deck (19): Defend x5, Strike x4, Assassinate+, Cloak and Dagger, Clumsy, Footwork+, Leading Strike, Leg Sweep, Neutralize+, Pounce, Sucker Punch, Survivor
Enemies: Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=27/27

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Gigantification Potion
    +Gigantification(1)
  Assassinate+ -> Phantasmal Gardener[3]
    -Gigantification | exhausted: Assassinate+ [0]: Innate. Deal 13 damage. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Phantasmal Gardener: hp +2
  Footwork+
    energy -1 | Dexterity(1→4)
  Leg Sweep -> Phantasmal Gardener[2]
    energy -2 | block +15 | enemy_deltas: Phantasmal Gardener: +Weak(2)
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(0x3=0)
  Cloak and Dagger
    energy -1 | block +10
  Shiv -> Phantasmal Gardener[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Strike -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  turn_end
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff
  Neutralize+ -> Phantasmal Gardener[0]
  Strike -> Phantasmal Gardener[0]
    energy -1
  Pounce -> Phantasmal Gardener[0]
    energy -2 | +Free Skill(1)
  Survivor
    block +12 | -Free Skill
  turn_end

### Round 4
Intent: Phantasmal Gardener: Attack(6), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7)
  Pounce -> Phantasmal Gardener[0]
    energy -2 | +Free Skill(1)
  Strike -> Phantasmal Gardener[0]
    energy -1
  Survivor
    block +12 | -Free Skill
  Defend
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  Defend
    energy -1 | block +9
  Defend
    energy -1 | block +9
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  turn_end

### Round 6
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(3x3=9)
  Neutralize+ -> Phantasmal Gardener[0]
  Leg Sweep -> Phantasmal Gardener[1]
    energy -2 | block +15 | enemy_deltas: Phantasmal Gardener: +Weak(2)
  Sucker Punch -> Phantasmal Gardener[0]
    energy -1
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(2x3=6), Phantasmal Gardener: Buff
  Cloak and Dagger
    energy -1 | block +10
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  Strike -> Phantasmal Gardener[0]
    energy -1
  turn_end

### Round 8
Intent: Phantasmal Gardener: Attack(9)
  Sucker Punch -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -8, block +6, +Weak(1)
  Pounce -> Phantasmal Gardener[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Phantasmal Gardener: hp -6, block -6
  Defend
    block +9 | -Free Skill
  turn_end

### Round 9
Intent: Phantasmal Gardener: Attack(11)
  Leg Sweep -> Phantasmal Gardener[0]
    energy -2 | block +15 | enemy_deltas: Phantasmal Gardener: +Weak(2)
  Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block +6
  turn_end

### Round 10
Intent: Phantasmal Gardener: Attack(3x3=9)
  Defend
    energy -1 | block +9
  Leading Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block +6
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: block -4
  Shiv -> Phantasmal Gardener[0]
    enemy_deltas: Phantasmal Gardener: hp -2, block -2
  Neutralize+ -> Phantasmal Gardener[0]
    block -9 | -Dexterity | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 10 rounds)

Cards played (with descriptions):
  Assassinate+ "Innate. Deal 39 damage. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Leg Sweep "Apply 2 Weak. Gain 15 Block." -> 3 plays, 45 block
  Cloak and Dagger "Gain 10 Block. Add 1 Shiv into your Hand." -> 2 plays, 20 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 8 plays, 2 dmg, EXHAUST
  Strike "Deal 6 damage." -> 6 plays, 6 dmg
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays
  Pounce "Deal 12 damage. The next Skill you play costs 0 energy ." -> 3 plays, 6 dmg
  Survivor "Gain 12 Block. Discard 1 card." -> 2 plays, 24 block
  Defend "Gain 9 Block." -> 4 plays, 36 block
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 3 dmg, generates 2 Shivs
  Sucker Punch "Deal 8 damage. Apply 1 Weak." -> 2 plays, 8 dmg

Active powers: Dexterity(1)

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~2 dmg
  Cloak and Dagger: 2 Shivs -> ~0 dmg

Enemy power timeline:
  Skittish: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:6 -> R9:6 -> R10:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:- -> R9:- -> R10:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:- -> R9:- -> R10:-
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Skittish[3]: R1:6 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:4 -> R9:4 -> R10:4
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:- -> R10:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:1
  Weak[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2 -> R8:- -> R9:- -> R10:-
  Weak[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:-

[Selected: boss] Soul Fysh (F17, boss)
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy
Deck (18): Defend x5, Strike x3, Backflip x2, Leading Strike x2, Accuracy+, Blade Dance+, Neutralize, Phantom Blades, Poisoned Stab, Survivor
Enemies: Soul Fysh HP=211/211

### Round 1
Intent: Soul Fysh: StatusCard(2)
  Powdered Demise -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: +Demise(9)
  Explosive Ampoule
    enemy_deltas: Soul Fysh: hp -10
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -3, +Weak(1)
  Blade Dance+
    energy -1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust.
  Shiv -> Soul Fysh[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  turn_end

### Round 2
Agent plan (hypothesis): We are getting good damage output with Serpent Form. Prioritize playing 0-cost cards and scaling powers as we draw them.
Agent plan (hypothesis): Continue aggressively attacking and using 0 cost cards for Serpent Form.
Intent: Soul Fysh: Attack(16)
  Power Potion
  Serpent Form
  Serpent Form
    +Serpent Form(4)
  Backflip
    energy -1 | block +5 | enemy_deltas: Soul Fysh: hp -4
  Beckon
    energy -1 | enemy_deltas: Soul Fysh: hp -4
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -10
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -8
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -8
  turn_end

### Round 3
Agent plan (hypothesis): Shivs scale hard now. Next turn enemy buffs.
Intent: Soul Fysh: Attack(7), StatusCard(1)
  Accuracy+
    energy -1 | +Accuracy(6) | enemy_deltas: Soul Fysh: hp -4
  Phantom Blades
    energy -1 | +Phantom Blades(9) | enemy_deltas: Soul Fysh: hp -4
  Defend
    energy -1 | block +5 | enemy_deltas: Soul Fysh: hp -4
  turn_end

### Round 4
Agent plan (hypothesis): Soul Fysh will be Intangible next turn. Demise and Poison will do a lot of work.
Intent: Soul Fysh: Buff
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -10
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -23
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -14
  Poisoned Stab -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -10, +Poison(3)
  Beckon
    energy -1 | enemy_deltas: Soul Fysh: hp -4
  turn_end

### Round 5
Agent plan (hypothesis): The enemy will have very little HP left and lose Intangible next turn, allowing for an easy lethal.
Intent: Soul Fysh: Attack(11), Debuff
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -2, +Weak(1)
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -2
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -2
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -2
  Defend
    energy -1 | block +5 | enemy_deltas: Soul Fysh: hp -1
  Survivor
    energy -1 | block +8 | enemy_deltas: Soul Fysh: hp -1
  turn_end

### Round 6
Agent plan (hypothesis): Beat Act 1!
Intent: Soul Fysh: StatusCard(2)
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -7, +Weak(1)
  Strike -> Soul Fysh[0]
    energy -1 | -Serpent Form | -Accuracy | -Phantom Blades | -Vulnerable | enemy_deltas: Soul Fysh: DIED
## Combat Analytics: Soul Fysh (WIN - 6 rounds)

Cards played (with descriptions):
  Neutralize "Deal 3 damage. Apply 1 Weak." -> 3 plays, 12 dmg
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 12 plays, 81 dmg, EXHAUST
  Leading Strike "Deal 6 damage. Add 2 Shivs into your Hand." -> 4 plays, 28 dmg, generates 2 Shivs
  Strike "Deal 9 damage." -> 2 plays, 9 dmg
  Serpent Form "Whenever you play a card, deal 4 damage to a random enemy." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 4 dmg, 5 block
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 2 plays, 8 dmg
  Accuracy+ "Shivs deal 6 additional damage." -> 1 plays, 4 dmg
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 4 dmg
  Defend "Gain 5 Block." -> 2 plays, 5 dmg, 10 block
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 10 dmg, +3 poison
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 1 dmg, 8 block

Token attribution (Shivs):
  Leading Strike: 8 Shivs -> ~54 dmg
  Blade Dance+: 4 Shivs -> ~27 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Demise: R1:- -> R2:9 -> R3:9 -> R4:9 -> R5:9 -> R6:9
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1
Comparator (recent same-enemy comparator):
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Neow's Torment, Red Mask, Juzu Bracelet
Deck (19): Defend x5, Strike x4, Dagger Throw, Expose, Flick-Flack, Haze, Leading Strike, Malaise, Neow's Fury+, Neutralize+, Noxious Fumes+, Survivor
Enemies: Soul Fysh HP=211/211

### Round 1
Intent: Soul Fysh: StatusCard(2)
  Regen Potion
    +Regen(5)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(3)
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -3
  Shiv -> Soul Fysh[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Malaise -> Soul Fysh[0]
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: Weak(1→2), +Strength(-1)
  turn_end

### Round 2
Intent: Soul Fysh: Attack(11)
  Dagger Throw -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Haze
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 3
Intent: Soul Fysh: Attack(6), StatusCard(1)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Beckon
    energy -1
  Defend
    energy -1 | block +5
  Flick-Flack
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end

### Round 4
Intent: Soul Fysh: Buff
  Expose -> Soul Fysh[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: +Vulnerable(2)
  Neow's Fury+ -> Soul Fysh[0]
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -21
  Flick-Flack
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Soul Fysh: Attack(10), Debuff
  Survivor
    energy -1 | block +8
  Haze
  Defend
    energy -1 | block +5 | enemy_deltas: Soul Fysh: Poison(13→17)
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -1
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -1
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -1
  turn_end

### Round 6
Intent: Soul Fysh: StatusCard(2)
  Beckon
    energy -1
  Dagger Throw -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Beckon
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end

### Round 7
Intent: Soul Fysh: Attack(22)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Defend
    energy -1 | block +5
  Beckon
    energy -1
  Beckon
    energy -1
  turn_end

### Round 8
Intent: Soul Fysh: Attack(6), StatusCard(1)
  Defend
    energy -1 | block +5
  Beckon
    energy -1
  Dagger Throw -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Beckon
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, Weak(1→3)
  turn_end

### Round 9
Intent: Soul Fysh: Buff
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -3
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Flick-Flack
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  turn_end
## Combat Analytics: Soul Fysh (WIN - 9 rounds)

Cards played (with descriptions):
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies." -> 1 plays
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 7 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 18 dmg, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, EXHAUST
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 27 dmg
  Defend "Gain 5 Block." -> 6 plays, 30 block, +4 poison
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 12 dmg
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 5 plays
  Flick-Flack "Sly. Deal 6 damage to ALL enemies." -> 3 plays, 21 dmg
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Neow's Fury+ "Deal 14 damage. Put 3 random cards from your Discard Pile into your Hand. Exhaust." -> 1 plays, 21 dmg, EXHAUST
  Strike "Deal 6 damage." -> 2 plays, 12 dmg

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~18 dmg

Poison stacks applied per card:
  Defend: 4 stacks

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:3 -> R3:9 -> R4:11 -> R5:13 -> R6:19 -> R7:21 -> R8:23 -> R9:25
  Strength: R1:- -> R2:-1 -> R3:-1 -> R4:-1 -> R5:-1 -> R6:-1 -> R7:-1 -> R8:-1 -> R9:-1
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:1 -> R2:1 -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:2

[Selected: boss] multi:Crusher+Rocket (F33, boss)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy, Book of Five Rings, Molten Egg, Archaic Tooth, Potion Belt, Bronze Scales, The Chosen Cheese
Deck (26): Defend x5, Backflip x2, Leading Strike x2, Phantom Blades x2, Strike x2, Accuracy+, Afterimage+, Backflip+, Blade Dance+, Cloak and Dagger+, Dagger Spray+, Expose, Finisher+, Leading Strike+, Leg Sweep, Poisoned Stab, Suppress+, Survivor
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Dexterity Potion
    +Dexterity(2)
  Afterimage+
    energy -1 | +Afterimage(1)
  Phantom Blades
    energy -1 | block +1 | +Phantom Blades(9)
  Suppress+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -17, +Weak(5)
  Backflip
    energy -1 | block +8
  turn_end

### Round 2
Agent plan (hypothesis): Finisher+ is now free. Rocket is taking huge damage.
Intent: Crusher: Attack(3), Rocket: Attack(27)
  Touch of Insanity
  Finisher+
  Defend
    energy -1 | block +8
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Rocket[1]
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Rocket: hp -13
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4
  Blade Dance+
    energy -1 | block +1 | exhausted: Shiv*2 [0]: Retain. Deal 4 damage. Exhaust.
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -4
  Finisher+ -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -48
  turn_end

### Round 3
Agent plan (hypothesis): Scaling is online.
Intent: Crusher: Attack(6x2=12), Debuff, Rocket: Buff
  Expose -> Rocket[1]
    block +1 | exhausted: Shiv*6 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Rocket: +Vulnerable(2)
  Accuracy+
    energy -1 | block +1 | +Accuracy(6)
  Dagger Spray+
    energy -1 | block +1 | enemy_deltas: Crusher: hp -12; Rocket: hp -18
  Defend
    energy -1 | block +8
  turn_end

### Round 4
Agent plan (hypothesis): Rocket is low HP, focus him down next turn.
Intent: Crusher: Buff, Rocket: Attack(33)
  Backflip
    energy -1 | block +6
  Backflip+
    energy -1 | block +8
  Leading Strike+ -> Rocket[1]
    energy -1 | block +1 | enemy_deltas: Rocket: hp -10
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -21
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -11
  turn_end

### Round 5
Agent plan (hypothesis): We will kill Rocket soon, but we need to ensure we can handle Crusher's resulting buff when it happens.
Intent: Crusher: Attack(15), Defend, Rocket: Sleep
  Suppress+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -12, Weak(1→6)
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -14
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -7
  Defend
    energy -1 | block +6
  Backflip
    energy -1 | block +6
  turn_end

### Round 6
Agent plan (hypothesis): Rocket dies, Crusher gets massive block but we scale.
Intent: Crusher: Attack(10), Rocket: Attack(7)
  Leading Strike -> Rocket[1]
    energy -1 | block +1 | enemy_deltas: Rocket: hp -6
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -19
  Shiv -> Rocket[1]
    block +1 | enemy_deltas: Rocket: hp -10
  Finisher+ -> Rocket[1]
    block +1 | enemy_deltas: Crusher: block +99, Strength(2→8), -Crab Rage; Rocket: DIED
  Leg Sweep -> Crusher[0]
    energy -2 | block +14 | enemy_deltas: Crusher: Weak(5→7)
  turn_end

### Round 7
Intent: Crusher: Attack(9)
  Poison Potion -> Crusher[0]
    enemy_deltas: Crusher: +Poison(6)
  Backflip+
    energy -1 | block +11
  Suppress+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -17, Weak(6→11)
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -19
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -10
  Strike -> Crusher[0]
    energy -1 | block +1 | enemy_deltas: Crusher: hp -9
  Finisher+ -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -32
  turn_end

### Round 8
Intent: Crusher: Attack(10x2=20), Debuff
  Leading Strike -> Crusher[0]
    energy -1 | block +1 | enemy_deltas: Crusher: hp -6
  Shiv -> Crusher[0]
    block +1 | enemy_deltas: Crusher: hp -19
  Shiv -> Crusher[0]
    hp +1 | block -2 | -Thorns | -Surrounded | -Dexterity | -Afterimage | -Phantom Blades | -Accuracy | enemy_deltas: Crusher: DIED
## Combat Analytics: multi:Crusher+Rocket (WIN - 8 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 1 block
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 3 plays, 46 dmg, 3 block
  Backflip "Gain 7 Block. Draw 2 cards." -> 3 plays, 20 block
  Defend "Gain 7 Block." -> 3 plays, 22 block
  Cloak and Dagger+ "Gain 8 Block. Add 2 Shivs into your Hand." -> 3 plays, 25 block, generates 2 Shivs
  Shiv "Retain. Deal 13 damage. Exhaust." -> 16 plays, 163 dmg, 15 block, EXHAUST
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 block, EXHAUST, generates 4 Shivs
  Finisher+ "Deal 8 damage for each Attack already played this turn. (Hits 6 times)" -> 3 plays, 80 dmg, 3 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST
  Accuracy+ "Shivs deal 6 additional damage." -> 1 plays, 1 block
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 1 plays, 30 dmg, 1 block
  Backflip+ "Gain 7 Block. Draw 2 cards." -> 2 plays, 19 block
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 1 plays, 10 dmg, 1 block, generates 2 Shivs
  Leading Strike "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 12 dmg, 2 block, generates 2 Shivs
  Leg Sweep "Apply 2 Weak. Gain 13 Block." -> 1 plays, 14 block
  Strike "Deal 9 damage." -> 1 plays, 9 dmg, 1 block

Active powers: Thorns(3), Surrounded(1)

Token attribution (Shivs):
  Cloak and Dagger+: 6 Shivs -> ~61 dmg
  Blade Dance+: 4 Shivs -> ~41 dmg
  Leading Strike: 4 Shivs -> ~41 dmg
  Leading Strike+: 2 Shivs -> ~20 dmg

Poison stacks applied per card:
  Poison Potion: 6 stacks
Total poison/power tick damage: 14
  Per round: R6:14

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:5
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:8 -> R8:8
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:- -> R8:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:- -> R8:-
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:5 -> R7:6 -> R8:10

[Selected: elite] multi:Flail Knight+Magi Knight+Spectral Knight (F42, elite)
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 42, elite)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy, Book of Five Rings, Molten Egg, Archaic Tooth, Potion Belt, The Chosen Cheese, Preserved Fog, Forgotten Soul, Anchor, Ripple Basin
Deck (27): Defend x3, Backflip x2, Blade Dance+ x2, Leading Strike x2, Phantom Blades x2, Accuracy+, Afterimage+, Backflip+, Cloak and Dagger+, Dagger Spray+, Envenom, Expose, Finisher+, Folly, Footwork, Leading Strike+, Leg Sweep, Poisoned Stab, Suppress+, Survivor, Up My Sleeve+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Agent plan (hypothesis): Will need to focus down Spectral Knight to avoid card exhaust next turn.
Intent: Flail Knight: Attack(15), Spectral Knight: Debuff, Magi Knight: Attack(6), Defend
  Afterimage+
    energy -1 | +Afterimage(1)
  Suppress+ -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -17, +Weak(5)
  Leg Sweep -> Magi Knight[2]
    energy -2 | block +12 | enemy_deltas: Magi Knight: +Weak(2)
  turn_end
    exhausted: Folly [0]: Unplayable. Innate. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Select a Shiv generator from discard with Liquid Memories to finish off Spectral Knight.
Intent: Flail Knight: Attack(6x2=12), Spectral Knight: Attack(15), Magi Knight: Debuff
  Accuracy+
    energy -1 | block +1 | +Accuracy(6)
  Blade Dance+
    energy -1 | block +1 | exhausted: Folly [0]: Unplayable. Innate. Ethereal. Eternal. | enemy_deltas: Flail Knight: hp -1
  Shiv -> Spectral Knight[1]
    block +1 | exhausted: Shiv [0]: Ethereal. Deal 4 damage. Exhaust. | enemy_deltas: Spectral Knight: hp -11
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Spectral Knight: hp -10; Magi Knight: block -1
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Spectral Knight: hp -10; Magi Knight: block -1
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Flail Knight: hp -1; Spectral Knight: hp -10
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Flail Knight: hp -1; Spectral Knight: hp -10
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Spectral Knight: hp -10; Magi Knight: block -1
  turn_end
    exhausted: Shiv*6 [0]: Ethereal. Deal 4 damage. Exhaust.

### Round 3
Agent plan (hypothesis): Now focus on taking down Magi Knight before its turn 5 massive attack.
Intent: Flail Knight: Buff, Spectral Knight: Attack(15), Magi Knight: Attack(10)
  Expose -> Magi Knight[2]
    block +1 | exhausted: Shiv*6 [0]: Ethereal. Deal 4 damage. Exhaust. | enemy_deltas: Magi Knight: hp -1, +Vulnerable(2)
  Leading Strike -> Spectral Knight[1]
    energy -1 | block +1 | enemy_deltas: Spectral Knight: hp -6
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Flail Knight: hp -1; Spectral Knight: hp -10
  Shiv -> Spectral Knight[1]
    block +1 | enemy_deltas: Spectral Knight: hp -11
  Dagger Spray
    energy -1 | block +1 | -Hex | enemy_deltas: Flail Knight: hp -8; Spectral Knight: DIED; Magi Knight: hp -12
  Survivor
    energy -1 | block +8
  Finisher
  turn_end

### Round 4
Agent plan (hypothesis): Use Liquid Memories on a Shiv generator next turn to burst down Magi Knight before its big attack.
Agent plan (hypothesis): Use Liquid Memories on a Shiv generator next turn to kill Magi Knight before the big attack.
Intent: Flail Knight: Attack(9x2=18), Magi Knight: Defend
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
    block +4

### Round 5
Intent: Flail Knight: Buff, Magi Knight: Attack(35)
  Backflip
    energy -1 | block +6
  Backflip
    energy -1 | block +6
  Liquid Memories
  Backflip
  Backflip
    block +6
  Survivor
    energy -1 | block +8
  Envenom
  turn_end
    block +4

### Round 6
Intent: Flail Knight: Attack(21), Magi Knight: Attack(10)
  Suppress -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -11, +Weak(3)
  Footwork
    energy -1 | block +1 | +Dexterity(2)
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -11
  Blade Dance
    energy -1 | block +1 | enemy_deltas: Flail Knight: hp -1
  Shiv -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -10; Magi Knight: hp -1
  Shiv -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -11
  Shiv -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: hp -11
  turn_end

### Round 7
Agent plan (hypothesis): Magi Knight is the last one standing, keep up the weak and focus damage.
Intent: Flail Knight: Attack(11x2=22), Magi Knight: Defend
  Leading Strike -> Flail Knight[0]
    energy -1 | block +1 | enemy_deltas: Flail Knight: hp -6
  Shiv -> Flail Knight[0]
    block +1 | enemy_deltas: Flail Knight: DIED; Magi Knight: hp -1
  Shiv -> Magi Knight[0]
    block +1 | enemy_deltas: Magi Knight: hp -11
  Poisoned Stab -> Magi Knight[0]
    energy -1 | block +1 | enemy_deltas: Magi Knight: hp -6, +Poison(3)
  Defend
    energy -1 | block +8
  turn_end

### Round 8
Intent: Magi Knight: Attack(35)
  Backflip
    energy -1 | block +8
  Cloak and Dagger
    energy -1 | block +9
  Shiv -> Magi Knight[0]
    block +1 | enemy_deltas: Magi Knight: hp -6, block -5
  Survivor
    energy -1 | block +10
  Envenom
  turn_end

### Round 9
Agent plan (hypothesis): Finally finished off the Magi Knight.
Intent: Magi Knight: Attack(10)
  Suppress -> Magi Knight[0]
    block +1 | enemy_deltas: Magi Knight: hp -11, +Weak(3)
  Leading Strike -> Magi Knight[0]
    energy -1 | block +1 | enemy_deltas: Magi Knight: hp -6
  Shiv -> Magi Knight[0]
    block +1 | enemy_deltas: Magi Knight: hp -11
  Shiv -> Magi Knight[0]
    hp +1 | block -3 | -Afterimage | -Accuracy | -Dampen | -Dexterity | enemy_deltas: Magi Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 9 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 1 plays, 17 dmg, 1 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 12 block
  Accuracy+ "Ethereal. Shivs deal 6 additional damage." -> 1 plays, 1 block
  Blade Dance+ "Ethereal. Add 4 Shivs into your Hand. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST, generates 4 Shivs
  Shiv "Ethereal. Deal 10 damage. Exhaust." -> 17 plays, 158 dmg, 16 block, EXHAUST
  Cloak and Dagger+ "Ethereal. Gain 6 Block. Add 2 Shivs into your Hand." -> 1 plays, 7 block, generates 2 Shivs
  Expose "Ethereal. Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST
  Leading Strike "Ethereal. Deal 6 damage. Add 2 Shivs into your Hand." -> 3 plays, 18 dmg, 3 block, generates 2 Shivs
  Dagger Spray "Ethereal. Deal 4 damage to ALL enemies twice." -> 1 plays, 20 dmg, 1 block
  Survivor "Gain 8 Block. Discard 1 card." -> 3 plays, 26 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 5 plays, 32 block
  Defend "Gain 5 Block." -> 3 plays, 20 block
  Suppress "Innate. Deal 11 damage. Apply 3 Weak." -> 2 plays, 22 dmg, 2 block
  Footwork "Gain 2 Dexterity." -> 1 plays, 1 block
  Cloak and Dagger "Gain 8 Block. Add 1 Shiv into your Hand." -> 2 plays, 18 block, generates 1 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST, generates 3 Shivs
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 6 dmg, 1 block, +3 poison

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~56 dmg
  Blade Dance+: 4 Shivs -> ~37 dmg
  Blade Dance: 3 Shivs -> ~28 dmg
  Cloak and Dagger+: 2 Shivs -> ~19 dmg
  Cloak and Dagger: 2 Shivs -> ~19 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks
Total poison/power tick damage: 13
  Per round: R3:5 R7:8

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2 -> R9:1
  Strength: R1:- -> R2:- -> R3:- -> R4:3 -> R5:3 -> R6:6 -> R7:6 -> R8:- -> R9:-
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:- -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:2 -> R8:- -> R9:-
  Weak[0]: R1:- -> R2:4 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak[2]: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Flail Knight+Magi Knight+Spectral Knight (Floor 42, elite)
Relics: Ring of the Snake, Winged Boots, Gambling Chip, Very Hot Cocoa, Strawberry, Red Mask, Vajra, Toxic Egg, Iron Club, Oddly Smooth Stone
Deck (30): Defend x5, Backflip x2, Blade Dance+ x2, Strike x2, Accuracy+, Assassinate, Backflip+, Blur, Cloak and Dagger+, Dagger Spray, Deflect+, Expose, Mad Science+, Malaise, Neutralize+, Phantom Blades, Piercing Wail, Predator, Serpent Form, Strangle, Survivor, Ultimate Strike, Well-Laid Plans+
Enemies: Flail Knight HP=101/101, Spectral Knight HP=93/93, Magi Knight HP=82/82

### Round 1
Intent: Flail Knight: Attack(11), Spectral Knight: Debuff, Magi Knight: Attack(4), Defend
  Strength Potion
    Strength(1→3)
  Assassinate -> Flail Knight[0]
    exhausted: Assassinate [0]: Innate. Deal 10 damage. Apply 1 Vulnerable. Exhaust. | enemy_deltas: Flail Knight: hp -13, +Vulnerable(1)
  Mad Science+
    energy -1 | block +9
  Phantom Blades
    energy -1 | +Phantom Blades(9)
  Neutralize+ -> Spectral Knight[1]
    enemy_deltas: Spectral Knight: hp -7, Weak(1→3)
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Flail Knight[0]
    exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Flail Knight: hp -24
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Blade Dance+
    energy -1 | exhausted: Shiv*2 [0]: Retain. Deal 4 damage. Exhaust.
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Shiv -> Flail Knight[0]
    enemy_deltas: Flail Knight: hp -10
  Ultimate Strike -> Spectral Knight[1]
    energy -1 | enemy_deltas: Spectral Knight: hp -17
  Backflip
    energy -1 | block +6
  Strike -> Flail Knight[0]
    energy -1 | enemy_deltas: Flail Knight: hp -13
  turn_end

### Round 2
Intent: Flail Knight: Attack(15), Spectral Knight: Attack(11), Magi Knight: Debuff
  Expose -> Spectral Knight[1]
    exhausted: Shiv*6 [0]: Retain. Ethereal. Deal 4 damage. Exhaust. | enemy_deltas: Spectral Knight: +Vulnerable(2)
  Dagger Spray
    energy -1 | enemy_deltas: Flail Knight: DIED; Spectral Knight: hp -20; Magi Knight: hp -9, block -5
  Piercing Wail
    energy -1 | exhausted: Shiv*6 [0]: Retain. Ethereal. Deal 4 damage. Exhaust. | enemy_deltas: Spectral Knight: +Strength(-6), +Piercing Wail(6); Magi Knight: +Strength(-6), +Piercing Wail(6)
  Accuracy+
    energy -1 | +Accuracy(6)
  turn_end
    exhausted: Well-Laid Plans+ [1]: Ethereal. At the end of your turn, Retain up to 2 cards.

### Round 3
Intent: Spectral Knight: Attack(11), Magi Knight: Attack(10)
  Deflect
    block +5
  Backflip
    energy -1 | block +6
  Blade Dance
    energy -1
  Shiv -> Spectral Knight[0]
    enemy_deltas: Spectral Knight: hp -33
  Shiv -> Spectral Knight[0]
    -Hex | enemy_deltas: Spectral Knight: DIED
  Shiv -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -13
  Strike -> Magi Knight[0]
    energy -1 | enemy_deltas: Magi Knight: hp -9
  turn_end

### Round 4
Intent: Magi Knight: Defend
  Cloak and Dagger
    energy -1 | block +7
  Shiv -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -22
  Backflip
    energy -1 | block +6
  Deflect
    block +5
  Neutralize -> Magi Knight[0]
    enemy_deltas: Magi Knight: hp -6, +Weak(1)
  Strike -> Magi Knight[0]
    energy -1 | enemy_deltas: Magi Knight: hp -9
  turn_end

### Round 5
Intent: Magi Knight: Attack(35)
  Energy Potion
    energy +2
  Mad Science
    energy -1 | block +9
  Ultimate Strike -> Magi Knight[0]
    energy -1 | enemy_deltas: Magi Knight: hp -12, block -5
  Dagger Spray
    energy -1 | block -9 | -Strength | -Dexterity | -Phantom Blades | -Accuracy | -Dampen | enemy_deltas: Magi Knight: DIED
## Combat Analytics: multi:Flail Knight+Magi Knight+Spectral Knight (WIN - 5 rounds)

Cards played (with descriptions):
  Assassinate "Innate. Deal 13 damage. Apply 1 Vulnerable. Exhaust." -> 1 plays, 13 dmg, EXHAUST
  Mad Science+ "Innate. Gain 9 Block. Draw 3 cards." -> 1 plays, 9 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays
  Neutralize+ "Deal 7 damage. Apply 2 Weak." -> 1 plays, 7 dmg
  Cloak and Dagger+ "Gain 7 Block. Add 2 Shivs into your Hand." -> 1 plays, 7 block, generates 2 Shivs
  Shiv "Retain. Deal 16 damage. Exhaust." -> 10 plays, 142 dmg, EXHAUST
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Ultimate Strike "Deal 17 damage." -> 2 plays, 29 dmg
  Backflip "Gain 6 Block. Draw 2 cards." -> 3 plays, 18 block
  Strike "Deal 9 damage." -> 3 plays, 31 dmg
  Expose "Ethereal. Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Dagger Spray "Ethereal. Deal 7 damage to ALL enemies twice." -> 2 plays, 29 dmg
  Piercing Wail "Ethereal. ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Accuracy+ "Ethereal. Shivs deal 6 additional damage." -> 1 plays
  Deflect "Ethereal. Gain 5 Block." -> 2 plays, 10 block
  Blade Dance "Ethereal. Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Cloak and Dagger "Gain 7 Block. Add 1 Shiv into your Hand." -> 1 plays, 7 block, generates 1 Shivs
  Neutralize "Deal 6 damage. Apply 1 Weak." -> 1 plays, 6 dmg
  Mad Science "Gain 9 Block. Draw 3 cards." -> 1 plays, 9 block

Active powers: Strength(1), Dexterity(1)

Token attribution (Shivs):
  Blade Dance+: 4 Shivs -> ~57 dmg
  Blade Dance: 3 Shivs -> ~43 dmg
  Cloak and Dagger+: 2 Shivs -> ~28 dmg
  Cloak and Dagger: 1 Shivs -> ~14 dmg

Enemy power timeline:
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:-
  Weak: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:-
  Weak[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Weak[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-

Unattributed damage (power/passive effects): 17
  Per round: R2:1 R3:16

[Selected: elite] Soul Nexus (F44, elite)
## Combat Replay: vs Soul Nexus (Floor 44, elite)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy, Book of Five Rings, Molten Egg, Archaic Tooth, Potion Belt, The Chosen Cheese, Preserved Fog, Forgotten Soul, Anchor, Ripple Basin, Reptile Trinket
Deck (28): Defend x3, Backflip x2, Blade Dance+ x2, Cloak and Dagger+ x2, Leading Strike x2, Phantom Blades x2, Accuracy+, Afterimage+, Backflip+, Dagger Spray+, Envenom, Expose, Finisher+, Folly, Footwork, Leading Strike+, Leg Sweep, Poisoned Stab, Suppress+, Survivor, Up My Sleeve+
Enemies: Soul Nexus HP=234/234

### Round 1
Agent plan (hypothesis): The enemy will apply Vulnerable and Weak next turn, followed by a heavy multi-attack on turn 3. Need to setup Accuracy and phantom blades to scale shivs.
Agent plan (hypothesis): We avoided taking damage turn 1. Next turn Soul Nexus applies Vuln/Weak and attacks moderately.
Intent: Soul Nexus: Attack(29)
  Afterimage+
    energy -1 | +Afterimage(1)
  Suppress+ -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -17, +Weak(5)
  Backflip
    energy -1 | block +6
  Defend
    energy -1 | block +6
  turn_end
    exhausted: Folly [0]: Unplayable. Innate. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Phantom Blades is online. Prepare to block the heavy multi-attack next turn.
Intent: Soul Nexus: Attack(13), DebuffStrong
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +12 | enemy_deltas: Soul Nexus: Weak(4→6)
  Phantom Blades
    energy -1 | block +1 | +Phantom Blades(9)
  turn_end
    block +4

### Round 3
Intent: Soul Nexus: Attack(6x4=24)
  Backflip+
    energy -1 | block +9
  Blade Dance+
    energy -1 | block +1 | exhausted: Folly [0]: Unplayable. Innate. Ethereal. Eternal. | enemy_deltas: Soul Nexus: hp -1
  Shiv -> Soul Nexus[0]
    block +1 | exhausted: Shiv [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Soul Nexus: hp -10
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Survivor
    energy -1 | block +8
  Envenom
  turn_end

### Round 4
Agent plan (hypothesis): See what Backflip draws, play any 0-cost cards for Afterimage block/damage.
Intent: Soul Nexus: Attack(20), DebuffStrong
  Expose -> Soul Nexus[0]
    block +1 | exhausted: Shiv*4 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Soul Nexus: hp -1, +Vulnerable(2)
  Footwork
    energy -1 | block +1 | +Dexterity(2)
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -15
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -5
  Backflip
    energy -1 | block +8
  turn_end

### Round 5
Agent plan (hypothesis): Soul Nexus will restart its debuff sequence soon.
Intent: Soul Nexus: Attack(32)
  Suppress+ -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -19, Weak(3→8)
  Backflip
    energy -1 | block +8
  Leading Strike -> Soul Nexus[0]
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -6
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -15
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -5
  Survivor
    energy -1 | block +10
  Poisoned Stab
  turn_end

### Round 6
Agent plan (hypothesis): We took 1 damage to get massive block. Enemy has Weak for 9 turns now.
Intent: Soul Nexus: Attack(20), DebuffStrong
  Leg Sweep -> Soul Nexus[0]
    energy -2 | block +14 | enemy_deltas: Soul Nexus: Weak(7→9)
  Blade Dance+
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -1
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -10
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  turn_end

### Round 7
Agent plan (hypothesis): See what Backflip draws to maximize block for the incoming 24 damage.
Agent plan (hypothesis): Blocked the heavy hit. Continue scaling and setting up for the final burst.
Intent: Soul Nexus: Attack(6x4=24)
  Backflip
    energy -1 | block +8
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -10
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4
  Defend
    energy -1 | block +8
  turn_end

### Round 8
Agent plan (hypothesis): Need 32 block.
Agent plan (hypothesis): Need more block or kill soon.
Intent: Soul Nexus: Attack(32)
  Backflip+
    energy -1 | block +11
  Defend
    energy -1 | block +8
  Defend
    energy -1 | block +8
  turn_end
    block +4

### Round 9
Intent: Soul Nexus: Attack(13), DebuffStrong
  Suppress+ -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -17, Weak(6→11)
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -14
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -5
  Leading Strike -> Soul Nexus[0]
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -6
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -5
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -5
  Finisher+ -> Soul Nexus[0]
    energy -1 | hp +1 | block -15 | -Afterimage | -Phantom Blades | -Dexterity | enemy_deltas: Soul Nexus: DIED
## Combat Analytics: Soul Nexus (WIN - 9 rounds)

Cards played (with descriptions):
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 3 plays, 53 dmg, 3 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 4 plays, 30 block
  Defend "Gain 5 Block." -> 4 plays, 30 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 2 plays, 26 block
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 1 block
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 2 plays, 20 block
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 2 plays, 2 dmg, 2 block, EXHAUST, generates 4 Shivs
  Shiv "Retain. Deal 9 damage. Exhaust." -> 18 plays, 127 dmg, 18 block, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 18 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST
  Footwork "Gain 2 Dexterity." -> 1 plays, 1 block
  Cloak and Dagger+ "Gain 8 Block. Add 2 Shivs into your Hand." -> 3 plays, 27 block, generates 2 Shivs
  Leading Strike "Deal 4 damage. Add 2 Shivs into your Hand." -> 2 plays, 12 dmg, 2 block, generates 2 Shivs
  Finisher+ "Deal 8 damage for each Attack already played this turn. (Hits 6 times)" -> 1 plays

Token attribution (Shivs):
  Blade Dance+: 8 Shivs -> ~56 dmg
  Cloak and Dagger+: 6 Shivs -> ~42 dmg
  Leading Strike: 4 Shivs -> ~28 dmg

Enemy power timeline:
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:4 -> R3:5 -> R4:4 -> R5:3 -> R6:7 -> R7:8 -> R8:7 -> R9:6
Comparator (recent same-enemy comparator):
## Combat Replay: vs Soul Nexus (Floor 40, elite)
Relics: Ring of the Snake, Winged Boots, Chandelier, Tea of Discourtesy, Planisphere, Book of Five Rings, White Beast Statue, Archaic Tooth, Daughter of the Wind, Vexing Puzzlebox, Strawberry, Preserved Fog, History Course, Gorget
Deck (30): Defend x5, Backflip+ x2, Acrobatics+, Backflip, Burst, Dagger Spray, Dagger Throw, Dagger Throw+, Envenom, Flick-Flack, Folly, Footwork+, Haze+, Leading Strike, Leading Strike+, Malaise+, Piercing Wail, Predator, Prepared, Prepared+, Serpent Form+, Suppress+, Survivor, Volley, Well-Laid Plans
Enemies: Soul Nexus HP=234/234

### Round 1
Intent: Soul Nexus: Attack(29)
  Envenom
    energy -2 | +Envenom(1)
  Suppress+ -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -17, +Poison(1), +Weak(5)
  Leg Sweep -> Soul Nexus[0]
    block +11 | enemy_deltas: Soul Nexus: Weak(5→7)
  Backflip+
    energy -1 | block +8
  Volley
    block +1
  turn_end
    block +4

### Round 2
Intent: Soul Nexus: Attack(13), DebuffStrong
  Backflip+
    energy -1 | block +8
  Footwork+
    energy -1 | +Dexterity(3)
  Leading Strike+ -> Soul Nexus[0]
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -6, Poison(3→4)
  Shiv -> Soul Nexus[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Nexus: hp -4, Poison(4→5)
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -4, Poison(5→6)
  turn_end
    block +3

### Round 3
Intent: Soul Nexus: Attack(6x4=24)
  Prepared
  Defend
  Malaise+ -> Soul Nexus[0]
    energy -6 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Nexus: Weak(5→12), +Strength(-7)
  turn_end
    block +2

### Round 4
Intent: Soul Nexus: Attack(7), DebuffStrong
  Defend
    energy -1 | block +8
  Well-Laid Plans
    energy -1 | +Well-Laid Plans(1)
  Dagger Throw+ -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -9, Poison(5→6)
  Haze+
  turn_end
    block +2
  Serpent Form+
  Defend

### Round 5
Intent: Soul Nexus: Attack(0x4=0)
  Predator -> Soul Nexus[0]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Nexus: hp -11, Poison(12→13)
  Acrobatics+
    energy -1
  Serpent Form+
  Prepared+
  Volley
  Defend
  Suppress+ -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -12, Weak(14→19), Poison(13→14)
  Prepared
  Burst
  turn_end
  Backflip+
  Defend

### Round 6
Intent: Soul Nexus: Attack(7), DebuffStrong
  Backflip+
    energy -1 | block +11
  Leading Strike -> Soul Nexus[0]
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -2, Poison(13→14)
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -3, Poison(14→15)
  Shiv -> Soul Nexus[0]
    block +1 | enemy_deltas: Soul Nexus: hp -3, Poison(15→16)
  Dagger Spray
    energy -1 | block +1 | enemy_deltas: Soul Nexus: hp -6, Poison(16→18)
  turn_end
  Piercing Wail

### Round 7
Intent: Soul Nexus: Attack(0x4=0)
  Touch of Insanity
  Serpent Form+
  Serpent Form+
    +Serpent Form(6)
  Prepared+
  Haze+
  Defend
  Backflip
    energy -1 | block +8 | enemy_deltas: Soul Nexus: hp -6
  Dagger Throw -> Soul Nexus[0]
    energy -1 | enemy_deltas: Soul Nexus: hp -6, Poison(25→26)
  Defend
  turn_end
  Piercing Wail
## Combat Analytics: Soul Nexus (WIN - 7 rounds)

Cards played (with descriptions):
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 29 dmg, 2 block, +2 poison
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 3 plays, 27 block
  Volley "Deal 10 damage to a random enemy X times." -> 1 plays, 1 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 1 plays, 6 dmg, 1 block, +1 poison, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 4 plays, 14 dmg, 4 block, +4 poison, EXHAUST
  Prepared "Draw 1 card. Discard 1 card." -> 2 plays
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Defend "Gain 8 Block." -> 1 plays, 8 block
  Well-Laid Plans "At the end of your turn, Retain up to 1 card." -> 1 plays
  Dagger Throw+ "Deal 9 damage. Draw 1 card. Discard 1 card." -> 1 plays, 9 dmg, +1 poison
  Predator "Deal 11 damage. Next turn, draw 2 cards." -> 1 plays, 11 dmg, 1 block, +1 poison
  Acrobatics+ "Draw 4 cards. Discard 1 card." -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 1 plays, 2 dmg, 1 block, +1 poison, generates 2 Shivs
  Dagger Spray "Deal 3 damage to ALL enemies twice." -> 1 plays, 6 dmg, 1 block, +2 poison
  Serpent Form+ "Whenever you play a card, deal 6 damage to a random enemy." -> 1 plays
  Backflip "Gain 8 Block. Draw 2 cards." -> 1 plays, 6 dmg, 8 block
  Dagger Throw "Deal 6 damage. Draw 1 card. Discard 1 card." -> 1 plays, 6 dmg, +1 poison

Active powers: Plating(4)

Token attribution (Shivs):
  Leading Strike+: 2 Shivs -> ~7 dmg
  Leading Strike: 2 Shivs -> ~7 dmg

Poison stacks applied per card:
  Shiv: 4 stacks
  Suppress+: 2 stacks
  Dagger Spray: 2 stacks
  Leading Strike+: 1 stacks
  Dagger Throw+: 1 stacks
  Predator: 1 stacks
  Leading Strike: 1 stacks
  Dagger Throw: 1 stacks

Enemy power timeline:
  Poison: R1:- -> R2:3 -> R3:6 -> R4:5 -> R5:12 -> R6:13 -> R7:19
  Strength: R1:- -> R2:- -> R3:- -> R4:-11 -> R5:-11 -> R6:-11 -> R7:-11
  Weak: R1:- -> R2:6 -> R3:5 -> R4:15 -> R5:14 -> R6:18 -> R7:17

[Selected: elite] Mecha Knight (F46, elite)
## Combat Replay: vs Mecha Knight (Floor 46, elite)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy, Book of Five Rings, Molten Egg, Archaic Tooth, Potion Belt, The Chosen Cheese, Preserved Fog, Forgotten Soul, Anchor, Ripple Basin, Reptile Trinket, Art of War
Deck (29): Defend x3, Backflip x2, Blade Dance+ x2, Cloak and Dagger+ x2, Leading Strike x2, Phantom Blades x2, Accuracy+, Afterimage+, Backflip+, Dagger Spray+, Envenom, Expose, Finisher+, Folly, Footwork, Leading Strike+, Leg Sweep, Poisoned Stab, Suppress+, Survivor, Tracking, Up My Sleeve+
Enemies: Mecha Knight HP=300/300

### Round 1
Agent plan (hypothesis): Need 8 more block after this.
Agent plan (hypothesis): Survive the heavy hits and keep stacking Shivs.
Intent: Mecha Knight: Attack(25)
  Suppress+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -17, Artifact(3→2)
  Afterimage+
    energy -1 | +Afterimage(1)
  Backflip
    energy -1 | block +6
  Blade Dance+
    energy -1 | block +1 | exhausted: Blade Dance+ [1]: Add 4 Shivs into your Hand. Exhaust. | enemy_deltas: Mecha Knight: hp -1
  Shiv -> Mecha Knight[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  turn_end
    exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.

### Round 2
Agent plan (hypothesis): Status cards incoming. We will have strong Shivs and Finisher coming up.
Intent: Mecha Knight: StatusCard(4)
  Expose -> Mecha Knight[0]
    block +1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -1, +Vulnerable(2), -Artifact
  Backflip
    energy -1 | block +6
  Phantom Blades
    energy -1 | block +1 | +Phantom Blades(9)
  Blade Dance+
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -1
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -20
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -7
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -7
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -7
  turn_end

### Round 3
Agent plan (hypothesis): Turn 4 is the heavy attack (30+). We will need massive block.
Intent: Mecha Knight: Defend, Buff
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -20
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -7
  Poisoned Stab -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -9, +Poison(3)
  Finisher+ -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -36
  turn_end

### Round 4
Agent plan (hypothesis): Survive the big hit, next turn is status flood.
Intent: Mecha Knight: Attack(40)
  Speed Potion
    +Dexterity(5) | +Speed Potion(5) | +Strength(3) | +Reptile Trinket(3)
  Cloak and Dagger+
    energy -1 | block +12
  Defend
    energy -1 | block +11
  Leading Strike -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: block -9
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -11, block -6
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -8
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -8
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -8
  turn_end

### Round 5
Agent plan (hypothesis): Status flood incoming. Prepare for Turn 7 heavy attack.
Intent: Mecha Knight: StatusCard(4)
  Footwork
    energy -1 | block +1 | +Dexterity(2)
  Cloak and Dagger+
    energy -1 | block +9
  Leading Strike -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -6
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -14
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  turn_end

### Round 6
Agent plan (hypothesis): Kill next turn.
Intent: Mecha Knight: Defend, Buff
  Suppress+ -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -17, +Weak(5)
  Leading Strike+ -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -9
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -14
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Shiv -> Mecha Knight[0]
    block +1 | enemy_deltas: Mecha Knight: hp -5
  Backflip
    energy -1 | block +8
  turn_end

### Round 7
Agent plan (hypothesis): Check if we drew Leading Strike or Finisher+ for lethal.
Agent plan (hypothesis): Check drawn cards for lethal or more block.
Intent: Mecha Knight: Attack(33)
  Backflip
    energy -1 | block +8
  Backflip+
    energy -1 | block +11
  Explosive Ampoule
    +Strength(3) | +Reptile Trinket(3) | enemy_deltas: Mecha Knight: block -10
  Leading Strike -> Mecha Knight[0]
    energy -1 | block +1 | enemy_deltas: Mecha Knight: hp -4, block -5
  Shiv -> Mecha Knight[0]
    hp +1 | block -20 | -Afterimage | -Phantom Blades | -Dexterity | -Strength | -Reptile Trinket | enemy_deltas: Mecha Knight: DIED
## Combat Analytics: Mecha Knight (WIN - 7 rounds)

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 34 dmg, 1 block
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Backflip "Gain 5 Block. Draw 2 cards." -> 4 plays, 28 block
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 2 plays, 2 dmg, 2 block, EXHAUST, generates 4 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 23 plays, 181 dmg, 22 block, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST
  Phantom Blades "Shivs gain Retain. The first Shiv you play each turn deals 9 additional damage." -> 1 plays, 1 block
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 4 plays, 37 block, generates 2 Shivs
  Poisoned Stab "Deal 6 damage. Apply 3 Poison." -> 1 plays, 9 dmg, 1 block, +3 poison
  Finisher+ "Deal 8 damage for each Attack already played this turn. (Hits 3 times)" -> 1 plays, 36 dmg, 1 block
  Defend "Gain 10 Block." -> 1 plays, 11 block
  Leading Strike "Deal 9 damage. Add 2 Shivs into your Hand." -> 3 plays, 10 dmg, 3 block, generates 2 Shivs
  Footwork "Gain 2 Dexterity." -> 1 plays, 1 block
  Leading Strike+ "Deal 9 damage. Add 2 Shivs into your Hand." -> 1 plays, 9 dmg, 1 block, generates 2 Shivs
  Backflip+ "Gain 10 Block. Draw 2 cards." -> 1 plays, 11 block

Token attribution (Shivs):
  Blade Dance+: 8 Shivs -> ~63 dmg
  Cloak and Dagger+: 8 Shivs -> ~63 dmg
  Leading Strike: 5 Shivs -> ~39 dmg
  Leading Strike+: 2 Shivs -> ~16 dmg

Poison stacks applied per card:
  Poisoned Stab: 3 stacks

Enemy power timeline:
  Artifact: R1:3 -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Poison: R1:- -> R2:- -> R3:- -> R4:2 -> R5:1 -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5 -> R7:10
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:4
Comparator (recent same-enemy comparator):
## Combat Replay: vs Mecha Knight (Floor 43, elite)
Relics: Ring of the Snake, Neow's Torment, Red Mask, Juzu Bracelet, Pael's Blood, Captain's Wheel, Chemical X, Festive Popper, Meal Ticket, Anchor, Throwing Axe, Venerable Tea Set, Bag of Preparation
Deck (26): Defend x5, Strike x3, Adrenaline+, Backflip+, Bubble Bubble+, Clumsy, Dagger Throw, Deadly Poison, Escape Plan, Expose, Flick-Flack, Haze, Leading Strike, Malaise+, Neow's Fury+, Neutralize+, Noxious Fumes+, Outbreak+, Poisoned Stab+, Survivor
Enemies: Mecha Knight HP=291/300

### Round 1
Intent: Mecha Knight: Attack(25)
  Noxious Fumes+
    energy -1 | +Noxious Fumes(6)
  Outbreak+
    energy -1 | +Outbreak(15)
  Survivor
    energy -1 | block +8
  Haze
  Adrenaline+
    energy +2 | exhausted: Adrenaline+ [0]: Gain 2 energy . Draw 2 cards. Exhaust. | enemy_deltas: Mecha Knight: Artifact(2→1)
  Escape Plan
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -9
  Strike
  Malaise+ -> Mecha Knight[0]
    energy -3 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Mecha Knight: +Weak(6), -Artifact
  turn_end
    exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust.

### Round 2
Intent: Mecha Knight: StatusCard(4)
  Backflip+
    energy -1 | block +8
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4, Weak(5→7)
  Deadly Poison -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(6→11)
  Neow's Fury+ -> Mecha Knight[0]
    energy -1 | exhausted: Neow's Fury+ [1]: Deal 14 damage. Put 3 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Mecha Knight: hp -14
  turn_end

### Round 3
Intent: Mecha Knight: Defend, Buff
  Expose -> Mecha Knight[0]
    exhausted: Neow's Fury+ [1]: Deal 14 damage. Put 3 random cards from your Discard Pile into your Hand. Exhaust. | enemy_deltas: Mecha Knight: +Vulnerable(2)
  Poisoned Stab+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -12, Poison(16→20)
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -13
  Flick-Flack
  Leading Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -4
  Shiv -> Mecha Knight[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Mecha Knight: hp -6
  Shiv -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -6
  turn_end

### Round 4
Intent: Mecha Knight: Attack(30)
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: block -6, Weak(5→7)
  Escape Plan
  Shackling Potion
    enemy_deltas: Mecha Knight: Strength(5→-2), +Shackling Potion(7)
  Bubble Bubble+ -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6, block -9, Poison(25→37)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end

### Round 5
Intent: Mecha Knight: StatusCard(4)
  Deadly Poison -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: Poison(42→47)
  Survivor
    energy -1 | block +8
  Haze
  Backflip+
    energy -1 | block +8 | enemy_deltas: Mecha Knight: hp -15, Poison(47→51)
  turn_end

### Round 6
Intent: Mecha Knight: Defend, Buff
  Dagger Throw -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -9
  Flick-Flack
  Neutralize+ -> Mecha Knight[0]
    enemy_deltas: Mecha Knight: hp -4, Weak(5→7)
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  Strike -> Mecha Knight[0]
    energy -1 | enemy_deltas: Mecha Knight: hp -6
  turn_end
## Combat Analytics: Mecha Knight (WIN - 6 rounds)

Cards played (with descriptions):
  Noxious Fumes+ "At the start of your turn, apply 3 Poison to ALL enemies. Perfect Fit." -> 1 plays
  Outbreak+ "Every 3 times you apply Poison, deal 15 damage to ALL enemies." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 2 plays
  Dagger Throw "Deal 9 damage. Draw 1 card. Discard 1 card." -> 3 plays, 31 dmg
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, EXHAUST
  Backflip+ "Gain 8 Block. Draw 2 cards." -> 2 plays, 15 dmg, 16 block, +4 poison
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 3 plays, 8 dmg
  Deadly Poison "Apply 5 Poison." -> 2 plays, +10 poison
  Neow's Fury+ "Deal 14 damage. Put 3 random cards from your Discard Pile into your Hand. Exhaust." -> 1 plays, 14 dmg, EXHAUST
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Poisoned Stab+ "Deal 8 damage. Apply 4 Poison." -> 1 plays, 12 dmg, +4 poison
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 1 plays, 4 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 12 dmg, EXHAUST
  Bubble Bubble+ "If the enemy has Poison, apply 12 Poison." -> 1 plays, 6 dmg, +12 poison
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Strike "Deal 6 damage." -> 2 plays, 12 dmg

Token attribution (Shivs):
  Leading Strike: 2 Shivs -> ~12 dmg

Poison stacks applied per card:
  Bubble Bubble+: 12 stacks
  Deadly Poison: 10 stacks
  Poisoned Stab+: 4 stacks
  Backflip+: 4 stacks

Enemy power timeline:
  Artifact: R1:2 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Poison: R1:- -> R2:6 -> R3:16 -> R4:25 -> R5:42 -> R6:56
  Strength: R1:- -> R2:- -> R3:- -> R4:5 -> R5:5 -> R6:5
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:-
  Weak: R1:- -> R2:5 -> R3:6 -> R4:5 -> R5:6 -> R6:5

[Selected: boss, death] multi:Queen+Torch Head Amalgam (F48, boss)
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Lava Rock, Centennial Puzzle, Planisphere, Strike Dummy, Book of Five Rings, Molten Egg, Archaic Tooth, Potion Belt, The Chosen Cheese, Preserved Fog, Forgotten Soul, Anchor, Ripple Basin, Reptile Trinket, Art of War, Lantern
Deck (29): Defend x3, Backflip x2, Blade Dance+ x2, Cloak and Dagger+ x2, Leading Strike x2, Phantom Blades x2, Accuracy+, Afterimage+, Backflip+, Dagger Spray+, Envenom, Expose, Finisher+, Folly, Footwork, Leading Strike+, Leg Sweep, Poisoned Stab, Suppress+, Survivor, Tracking, Up My Sleeve+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Footwork
    energy -1 | +Dexterity(2)
  Afterimage+
    energy -1 | +Afterimage(1)
  Suppress+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -17, +Weak(5)
  Backflip+
    energy -1 | block +11
  Cloak and Dagger+
    energy -1 | block +9
  Shiv -> Queen[1]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Queen: hp -5
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.

### Round 2
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Backflip
    energy -1 | block +8
  Blade Dance+
    energy -1 | block +1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -1
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  Leading Strike -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -6
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -5
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -4
  turn_end

### Round 3
Intent: Torch Head Amalgam: Attack(9x3=27), Queen: Buff, Defend
  Backflip
    energy -1 | block +6
  Accuracy+
    energy -1 | block +1 | +Accuracy(6)
  Defend
    energy -1 | block +6
  turn_end
    block +4

### Round 4
Intent: Torch Head Amalgam: Attack(16), Queen: Buff, Defend
  Expose -> Queen[1]
    block +1 | exhausted: Shiv*8 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -1; Queen: block -20, +Vulnerable(2)
  Envenom
    energy -2 | block +1 | +Envenom(1)
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -12, +Poison(1)
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -11, Poison(1→2)
  Leading Strike+ -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -10, Poison(2→3)
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -12, Poison(3→4)
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -12, Poison(4→5)
  turn_end

### Round 5
Intent: Torch Head Amalgam: Attack(18), Queen: Buff, Defend
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: block -12
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -3, block -8, Poison(4→5)
  Backflip
    energy -1 | block +6
  Finisher+ -> Queen[1]
    energy -1 | block +1 | enemy_deltas: Queen: hp -18, Poison(5→7)
  turn_end

### Round 6
Intent: Torch Head Amalgam: Attack(16x3=48), Queen: Buff, Defend
  Suppress+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -12, +Poison(1), +Weak(5)
  Backflip+
    energy -1 | block +8
  Defend
    energy -1 | block +6
  Survivor
    energy -1 | block +7
  Phantom Blades
  turn_end

### Round 7
Intent: Torch Head Amalgam: Attack(20), Queen: Buff, Defend
  Leg Sweep -> Queen[1]
    energy -2 | block +10 | enemy_deltas: Queen: +Weak(2)
  Blade Dance+
    energy -1 | block +1 | exhausted: Shiv*14 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -1
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: block -8
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: block -7
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -1; Queen: hp -2, block -5, Poison(5→6)
  Shiv -> Queen[1]
    block +1 | enemy_deltas: Queen: hp -8, Poison(6→7)
  turn_end

### Round 8
Intent: Torch Head Amalgam: Attack(21), Queen: Buff, Defend
  Backflip+
    energy -1 | block +8
  Backflip
    energy -1 | block +6
  Cloak and Dagger+
    energy -1 | block +7
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, +Poison(1)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, Poison(1→2)
  turn_end

### Round 9
Intent: Torch Head Amalgam: Attack(15x3=45), Queen: Buff, Defend
  Cloak and Dagger+
    energy -1 | block +7
  Leading Strike -> Torch Head Amalgam[0]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -4, Poison(1→2)
  Leading Strike+ -> Torch Head Amalgam[0]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -6, Poison(2→3)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -7, Poison(3→4); Queen: block -1
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -7, Poison(4→5); Queen: block -1
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, Poison(5→6)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, Poison(6→7)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, Poison(7→8)
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -8, Poison(8→9)
  turn_end
## Combat Analytics: multi:Queen+Torch Head Amalgam (LOSS - 9 rounds)
Death cause: Died with HP=23, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Footwork "Gain 2 Dexterity." -> 1 plays
  Afterimage+ "Innate. Whenever you play a card, gain 1 Block." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 29 dmg, 2 block, +1 poison
  Backflip+ "Gain 10 Block. Draw 2 cards." -> 3 plays, 27 block
  Cloak and Dagger+ "Gain 8 Block. Add 2 Shivs into your Hand." -> 5 plays, 37 block, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 26 plays, 166 dmg, 26 block, +15 poison, EXHAUST
  Backflip "Gain 7 Block. Draw 2 cards. Bound" -> 4 plays, 26 block
  Blade Dance+ "Add 4 Shivs into your Hand. Bound Exhaust." -> 2 plays, 2 dmg, 2 block, EXHAUST, generates 4 Shivs
  Leading Strike "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 10 dmg, 2 block, +1 poison, generates 2 Shivs
  Accuracy+ "Shivs deal 6 additional damage. Bound" -> 1 plays, 1 block
  Defend "Gain 5 Block." -> 2 plays, 12 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 dmg, 1 block, EXHAUST
  Envenom "Whenever an Attack deals unblocked damage, apply 1 Poison." -> 1 plays, 1 block
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 16 dmg, 2 block, +2 poison, generates 2 Shivs
  Finisher+ "Deal 6 damage for each Attack already played this turn. (Hits 2 times)" -> 1 plays, 18 dmg, 1 block, +2 poison
  Survivor "Gain 7 Block. Discard 1 card." -> 1 plays, 7 block
  Leg Sweep "Apply 2 Weak. Gain 9 Block." -> 1 plays, 10 block

Token attribution (Shivs):
  Cloak and Dagger+: 10 Shivs -> ~64 dmg
  Blade Dance+: 8 Shivs -> ~51 dmg
  Leading Strike: 4 Shivs -> ~26 dmg
  Leading Strike+: 4 Shivs -> ~26 dmg

Poison stacks applied per card:
  Shiv: 15 stacks
  Leading Strike+: 2 stacks
  Finisher+: 2 stacks
  Suppress+: 1 stacks
  Leading Strike: 1 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:6 -> R7:5 -> R8:6 -> R9:-
  Poison[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  Poison[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:5
  Strength: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:6
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:2 -> R5:1 -> R6:- -> R7:4 -> R8:- -> R9:2
  Weak[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:3 -> R9:-
  Weak[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:1 -> R9:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Queen+Torch Head Amalgam (Floor 48, boss)
Relics: Ring of the Snake, Winged Boots, Chandelier, Tea of Discourtesy, Planisphere, Book of Five Rings, White Beast Statue, Archaic Tooth, Daughter of the Wind, Vexing Puzzlebox, Strawberry, Preserved Fog, History Course, Gorget, Bronze Scales, Regal Pillow, Whetstone
Deck (33): Defend x5, Backflip+ x2, Acrobatics+, Backflip, Blur, Burst, Dagger Spray, Dagger Throw, Dagger Throw+, Envenom+, Flick-Flack+, Folly, Footwork+, Haze+, Hidden Daggers, Leading Strike, Leading Strike+, Malaise+, Piercing Wail, Piercing Wail+, Predator+, Prepared, Prepared+, Serpent Form+, Suppress+, Survivor, Volley, Well-Laid Plans+
Enemies: Torch Head Amalgam HP=199/199, Queen HP=400/400

### Round 1
Intent: Torch Head Amalgam: Attack(18), Queen: CardDebuff
  Power Potion
  Accelerant
  Serpent Form+
    energy -3 | +Serpent Form(6)
  Suppress+ -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -23, +Weak(5)
  Anticipate
    +Dexterity(2) | +Anticipate(2) | enemy_deltas: Torch Head Amalgam: hp -6
  Accelerant
    +Accelerant(1) | enemy_deltas: Torch Head Amalgam: hp -6
  turn_end
    block +4

### Round 2
Intent: Torch Head Amalgam: Attack(13), Queen: Debuff
  Prepared
  Flick-Flack+
  Defend
    energy -1 | block +7 | enemy_deltas: Torch Head Amalgam: hp -6
  Malaise+ -> Torch Head Amalgam[0]
    energy -2 | exhausted: Malaise+ [X]: Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -6, Weak(4→7), +Strength(-3)
  turn_end
    block +3

### Round 3
Intent: Torch Head Amalgam: Attack(5x3=15), Queen: Buff, Defend
  Piercing Wail+
    energy -1 | exhausted: Piercing Wail+ [1]: ALL enemies lose 8 Strength this turn. Bound Exhaust. | enemy_deltas: Torch Head Amalgam: hp -6, Strength(-3→-11), +Piercing Wail(8); Queen: Strength(-7→-15), +Piercing Wail(8)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2) | enemy_deltas: Torch Head Amalgam: hp -6
  Dagger Spray
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -12; Queen: hp -6
  turn_end
    block +2
  Dagger Throw+
  Leading Strike

### Round 4
Intent: Torch Head Amalgam: Attack(13), Queen: Buff, Defend
  Explosive Ampoule
    enemy_deltas: Torch Head Amalgam: hp -10; Queen: hp -2, block -8
  Hidden Daggers
  Haze+
  Defend
  Leading Strike -> Torch Head Amalgam[0]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -8; Queen: hp -12, +Poison(6)
  Shiv -> Torch Head Amalgam[0]
    block +1 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Torch Head Amalgam: hp -3; Queen: hp -6
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -9
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: hp -6
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: hp -6
  Prepared+
  Blur
  Dagger Throw
  Leading Strike+ -> Torch Head Amalgam[0]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -4; Queen: hp -6
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -9
  Shiv -> Torch Head Amalgam[0]
    block +1 | enemy_deltas: Torch Head Amalgam: hp -3; Queen: hp -6
  Dagger Throw+ -> Torch Head Amalgam[0]
    energy -1 | block +1 | enemy_deltas: Torch Head Amalgam: hp -9; Queen: hp -6
  turn_end
    block +1
  Volley

### Round 5
Intent: Queen: Buff
  Acrobatics+
    energy -1
  Suppress+
  Leading Strike+ -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -5, block -5
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9
  Hidden Daggers
  Backflip+
  Defend
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9
  Backflip+
    energy -1 | block +6 | enemy_deltas: Queen: hp -6
  turn_end
  Blur
  Piercing Wail

### Round 6
Intent: Queen: Attack(0x5=0)
  Envenom+
    energy -2 | +Envenom(2) | enemy_deltas: Queen: hp -6
  Prepared
  Flick-Flack+
  Leading Strike -> Queen[0]
    energy -1 | block +1 | enemy_deltas: Queen: hp -8, Poison(4→6)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9, Poison(6→8)
  Shiv -> Queen[0]
    block +1 | enemy_deltas: Queen: hp -9, Poison(8→10)
  turn_end
  Blur
  Piercing Wail

### Round 7
Intent: Queen: Attack(11)
  Prepared+
  Haze+
  Dagger Spray
  Footwork+
    energy -1 | +Dexterity(3) | enemy_deltas: Queen: hp -6
  Predator+ -> Queen[0]
    energy -2 | block +1 | +Draw Cards Next Turn(2) | enemy_deltas: Queen: hp -21, Poison(16→18)
  turn_end
  Blur
  Piercing Wail

### Round 8
Intent: Queen: Buff
  Dagger Spray
    energy -1 | block +1 | enemy_deltas: Queen: hp -12, Poison(18→22)
  Acrobatics+
    energy -1
  Leading Strike
  Anticipate
    Dexterity(3→5) | +Anticipate(2) | enemy_deltas: Queen: hp -6
  Dagger Throw+ -> Queen[0]
    energy -1 | enemy_deltas: Queen: hp -9, Poison(22→24)
  Defend
  turn_end
  Blur
  Piercing Wail
## Combat Analytics: multi:Queen+Torch Head Amalgam (WIN - 8 rounds)

Cards played (with descriptions):
  Serpent Form+ "Whenever you play a card, deal 6 damage to a random enemy. Draw 2 cards the first time this is played." -> 1 plays
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 1 plays, 23 dmg, 1 block
  Anticipate "Gain 2 Dexterity this turn." -> 2 plays, 12 dmg
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 6 dmg
  Prepared "Draw 1 card. Discard 1 card. Bound" -> 2 plays
  Defend "Gain 7 Block. Bound" -> 1 plays, 6 dmg, 7 block
  Malaise+ "Enemy loses X+1 Strength. Apply X+1 Weak. Exhaust." -> 1 plays, 6 dmg, EXHAUST
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Bound Exhaust." -> 1 plays, 6 dmg, EXHAUST
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 6 dmg
  Dagger Spray "Deal 3 damage to ALL enemies twice." -> 2 plays, 30 dmg, 2 block, +4 poison
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 2 plays, generates 2 Shivs
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 2 plays, 28 dmg, 2 block, +8 poison, generates 2 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 12 plays, 108 dmg, 12 block, +4 poison, EXHAUST
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Leading Strike+ "Deal 4 damage. Add 2 Shivs into your Hand." -> 2 plays, 15 dmg, 2 block, generates 2 Shivs
  Dagger Throw+ "Deal 9 damage. Draw 1 card. Discard 1 card." -> 2 plays, 24 dmg, 1 block, +2 poison
  Acrobatics+ "Draw 4 cards. Discard 1 card. Bound" -> 2 plays
  Backflip+ "Gain 6 Block. Draw 2 cards." -> 1 plays, 6 dmg, 6 block
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison. Bound" -> 1 plays, 6 dmg
  Footwork+ "Gain 3 Dexterity." -> 1 plays, 6 dmg
  Predator+ "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 21 dmg, 1 block, +2 poison

Active powers: Plating(4), Thorns(3)

Token attribution (Shivs):
  Hidden Daggers: 4 Shivs -> ~36 dmg
  Leading Strike: 4 Shivs -> ~36 dmg
  Leading Strike+: 4 Shivs -> ~36 dmg

Poison stacks applied per card:
  Leading Strike: 8 stacks
  Shiv: 4 stacks
  Dagger Spray: 4 stacks
  Predator+: 2 stacks
  Dagger Throw+: 2 stacks

Enemy power timeline:
  Minion: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:4 -> R6:2 -> R7:10 -> R8:18
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:-7 -> R6:-5 -> R7:-5 -> R8:-5
  Strength[0]: R1:- -> R2:- -> R3:-3 -> R4:-2 -> R5:- -> R6:- -> R7:- -> R8:-
  Strength[1]: R1:- -> R2:- -> R3:-7 -> R4:-7 -> R5:- -> R6:- -> R7:- -> R8:-
  Weak: R1:- -> R2:4 -> R3:- -> R4:- -> R5:5 -> R6:4 -> R7:3 -> R8:2
  Weak[0]: R1:- -> R2:- -> R3:6 -> R4:5 -> R5:- -> R6:- -> R7:- -> R8:-
  Weak[1]: R1:- -> R2:- -> R3:7 -> R4:6 -> R5:- -> R6:- -> R7:- -> R8:-

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F11(Phantasmal Gardener: WIN), F17(Soul Fysh: WIN), F33(Crusher: WIN), F42(Flail Knight: ), F44(Soul Nexus: WIN), F46(Mecha Knight: WIN), F48(Torch Head Amalgam: )
- Core Combat Principles: F2(Sludge Spinner: WIN), F3(Corpse Slug: WIN), F6(Seapunk: WIN), F7(Punch Construct: WIN), F9(Corpse Slug: WIN), F11(Phantasmal Gardener: WIN), F14(Haunted Ship: WIN), F15(Sewer Clam: WIN), F17(Soul Fysh: WIN), F19(Thieving Hopper: WIN), F20(Tunneler: WIN), F22(Exoskeleton: WIN), F23(Myte: WIN), F27(Bowlbug (Rock): ), F29(Ovicopter: WIN), F33(Crusher: WIN), F35(Devoted Sculptor: WIN), F38(Scroll of Biting: WIN), F40(The Lost: ), F42(Flail Knight: ), F44(Soul Nexus: WIN), F45(Frog Knight: WIN), F46(Mecha Knight: WIN), F48(Torch Head Amalgam: )
- Deck Building Across the Run: F2(), F3(), F4(), F4(), F4(), F5(), F6(), F7(), F9(), F11(), F14(), F15(), F17(), F17(), F19(), F20(), F22(), F23(), F25(), F25(), F27(), F29(), F33(), F34(), F35(), F38(), F39(), F39(), F39(), F40(), F42(), F42(), F44(), F45(), F46()
- Map Routing and Path Planning: F1(), F1(), F3(), F6(), F10(), F11(), F12(), F14(), F18(), F18(), F20(), F23(), F23(), F26(), F34(), F34(), F42(), F42()
- Rest Site and Event Decisions: F8(), F13(), F16(), F28(), F32(), F43(), F47()
- Silent - Combat Sequencing: F2(Sludge Spinner: WIN), F3(Corpse Slug: WIN), F6(Seapunk: WIN), F7(Punch Construct: WIN), F9(Corpse Slug: WIN), F11(Phantasmal Gardener: WIN), F14(Haunted Ship: WIN), F15(Sewer Clam: WIN), F17(Soul Fysh: WIN), F19(Thieving Hopper: WIN), F20(Tunneler: WIN), F22(Exoskeleton: WIN), F23(Myte: WIN), F27(Bowlbug (Rock): ), F29(Ovicopter: WIN), F33(Crusher: WIN), F35(Devoted Sculptor: WIN), F38(Scroll of Biting: WIN), F40(The Lost: ), F42(Flail Knight: ), F44(Soul Nexus: WIN), F45(Frog Knight: WIN), F46(Mecha Knight: WIN), F48(Torch Head Amalgam: )
- Silent - Draft and Shop Rules: F2(), F3(), F4(), F4(), F4(), F5(), F6(), F7(), F9(), F11(), F14(), F15(), F17(), F17(), F19(), F20(), F22(), F23(), F25(), F25(), F27(), F29(), F33(), F34(), F35(), F38(), F39(), F39(), F39(), F40(), F42(), F42(), F44(), F45(), F46()
- Silent - Route Priorities: F1(), F1(), F3(), F6(), F10(), F11(), F12(), F14(), F18(), F18(), F20(), F23(), F23(), F26(), F34(), F34(), F42(), F42()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.