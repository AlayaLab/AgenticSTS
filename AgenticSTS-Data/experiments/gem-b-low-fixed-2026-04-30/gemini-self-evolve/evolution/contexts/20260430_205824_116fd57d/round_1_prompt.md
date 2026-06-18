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
Result: DEFEAT at Floor 17 (fitness: 71.6)
Combats won: 6/6
Run duration: 1115.3s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation: Looking to build an early damage engine for Act 1 elites while leveraging our 2 random relics. Avoid adding too many cheap attacks later to thin the bloated deck.
- [map] Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.
### F2
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a scaling engine. Take high-impact damage or cheap draw, skip narrow synergy pieces for now. With huge turn-1 draw, prioritize frontloaded damage to end fights fast.
### F3
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a scaling engine. Prioritize 1-cost attacks or setup cards since Turn 1 gives us 9 cards. Use Predator to smooth out Turn 2 draw.
### F4
- [event] Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.
### F5
- [card_reward] Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills (Blade Dance, Bouncing Flask) to double, and 1-cost attacks to use alongside our massive Turn 1 draw.
### F6
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F7
- [event] Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.
- [card_select] Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills to double, and 1-cost attacks to use alongside our massive Turn 1 draw.
- [map] Foundation: Farming early card rewards to build a damage engine while Tungsten Rod mitigates chip damage. Prioritizing consistent card quality and key upgrades to stabilize before facing the late-act Elite and Boss.
### F8
- [map] Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.
### F9
- [rest_site] Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and Predators for card advantage and heavy damage.
### F11
- [rest_site] Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage.
### F12
- [card_reward] Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills (Blade Dance, Bouncing Flask) to double, and 1-cost attacks to use alongside our massive Turn 1 draw.
- [map] Foundation: Utilizing Tungsten Rod to farm early hallway fights while hunting for a scaling damage engine. Prioritizing Smiths to improve card efficiency, aiming for one safe Elite kill before the Act 1 boss.
### F13
- [rest_site] Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage. Needs consistent card draw and energy to reliably play the expensive Predators.
### F14
- [card_reward] Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills to double, and 1-cost attacks to use alongside our massive Turn 1 draw.
- [map] Foundation: Focusing on high-value monster rewards and Tungsten Rod for chip mitigation. Transitioning to an elite fight now to secure a power spike before the boss, relying on the subsequent campfire to stabilize HP.
### F15
- [card_reward] Foundation plan: survive with high draw, Burst, and Predator+. Focus on energy generation and consistent block to support our expensive attacks.
### F16
- [rest_site] Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage. Needs consistent card draw and energy to reliably play the expensive Predators.

### Combat Decision Digest (7 combats)
F2 [monster] multi:Toadpole+Toadpole (7R, HP 56->56, loss=0, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike*2 | dealt=3 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Defend(+5blk)->Defend(+5blk)->Survivor(+8blk) | dealt=0 taken=0
  R4[Toadpole: Buff+Toadpole: Atk(7)]: Strike(6dmg)->Strike(6dmg)->Neutralize->Defend(+5blk) | dealt=12 taken=0
  R5[Toadpole: Atk(3x3=9)]: Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R6[Toadpole: Atk(7)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Defend(+5blk)->Defend(+5blk) | dealt=9 taken=0
  R7[Toadpole: Buff]: Strike | dealt=0 taken=0

F3 [monster] multi:Corpse Slug+Corpse Slug (3R, HP 56->56, loss=0, WIN)
  R1[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Neutralize(3dmg,1+Weak(1))->Survivor(+8blk)->Flick-Flack(12dmg)->Strike(6dmg)->Strike | dealt=21 taken=0
  R2[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike(1+Strength(4))->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R3[Corpse Slug: Atk(7x2=14)]: Strike(6dmg)->Survivor(+6blk)->Flick-Flack | dealt=6 taken=0

F5 [monster] Seapunk (3R, HP 43->43, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Survivor(+8blk) | dealt=15 taken=0
  R2[Seapunk: Atk(2x4=8)]: Defend(+5blk)->Predator(15dmg,power:+Draw Cards Next Turn(2)) | dealt=15 taken=1
  R3[Seapunk: Buff, Defend]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Neutralize(power:-Draw Cards Next Turn) | dealt=15 taken=0

F12 [monster] Punch Construct (4R, HP 43->36, loss=7, WIN)
  R1[Punch Construct: Defend]: Neutralize+(7dmg,1-Artifact)->Predator(15dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=28 taken=0
  R2[Punch Construct: Atk(14)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Punch Construct: Atk(5x2=10), Debuff]: Predator(15dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=21 taken=8
  R4[Punch Construct: Defend]: Neutralize+(5dmg,1+Weak(2))->Strike(power:-Weak) | dealt=5 taken=0

F14 [monster] Haunted Ship (2R, HP 36->37, loss=0, WIN)
  R1[Haunted Ship: StatusCard(5)]: Neutralize+(7dmg,1+Weak(2))->Predator+(23dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=36 taken=0
  R2[Haunted Ship: Atk(7), Debuff]: Strike(6dmg)->Strike(6dmg)->Flick-Flack | dealt=22 taken=0

F15 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (5R, HP 37->36, loss=1, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Predator+(power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=0 taken=2
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(7)]: Neutralize+(7dmg,1+Weak(2))->Predator+(17dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk)->Flick-Flack | dealt=24 taken=0
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)]: Predator+(power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=0 taken=0
  R4[Phantasmal Gardener: Buff]: Strike(6dmg)->Predator+(17dmg,power:+Draw Cards Next Turn(2)) | dealt=23 taken=0
  R5[Phantasmal Gardener: Atk(7)]: Neutralize+ | dealt=0 taken=0

F17 [boss] Waterfall Giant (14R, HP 58->0, loss=58, LOSS)
  R1[Waterfall Giant: Buff]: Neutralize+(7dmg,1+Weak(2))->Predator+(23dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=36 taken=0
  R2[Waterfall Giant: Atk(11), Debuff, Buff]: Acrobatics->Predator+(23dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=23 taken=2
  R3[Waterfall Giant: Atk(10), Buff]: Neutralize+(5dmg,1+Weak(2))->Predator+(17dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=22 taken=1
  R4[Waterfall Giant: Heal, Buff]: Acrobatics->Flick-Flack(7dmg,1Weak(1→3))->Neutralize+(23dmg,power:+Draw Cards Next Turn(2))->Predator+ | dealt=30 taken=0
  R5[Waterfall Giant: Atk(15), Buff]: Defend(+5blk)->Survivor(+8blk)->Strike(6dmg) | dealt=6 taken=1
  R6[Waterfall Giant: Atk(9), Buff]: Backflip(+5blk)->Strike(6dmg)->Survivor(+8blk) | dealt=6 taken=0
  R7[Waterfall Giant: Atk(15), Debuff, Buff]: Predator+(23dmg,power:+Draw Cards Next Turn(2))->Defend(+5blk) | dealt=23 taken=9
  R8[Waterfall Giant: Atk(10), Buff]: Neutralize+(5dmg,1+Weak(2))->Acrobatics->Predator+(17dmg,power:+Draw Cards Next Turn(2)) | dealt=22 taken=6
  R9[Waterfall Giant: Heal, Buff]: Neutralize+(7dmg,1Weak(1→3))->Strike(6dmg)->Strike(12dmg)->Survivor(+8blk)->Flick-Flack | dealt=31 taken=0
  R10[Waterfall Giant: Atk(18), Buff]: Neutralize+(7dmg,1Weak(2→4))->Burst(power:+Burst(1))->Defend(+10blk,power:-Burst)->Defend(+5blk) | dealt=7 taken=2
  R11[Waterfall Giant: Atk(9), Buff]: Predator+(23dmg,power:+Draw Cards Next Turn(2))->Survivor(+8blk) | dealt=23 taken=0
  R12[Waterfall Giant: Atk(11), Debuff, Buff]: Predator+(23dmg,power:+Draw Cards Next Turn(2))->Strike(6dmg) | dealt=29 taken=10
  R13[Waterfall Giant: Atk(7), Buff]: Flick-Flack(4dmg)->Strike(1-Weak) | dealt=4 taken=0
  R14[Waterfall Giant: DeathBlow(48)]: none | dealt=0 taken=0

### Non-combat Decisions (64 decisions)
F1 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->14
  deck_change: added Defend, Strike
  reasoning: Trading 2 starter cards added to the deck for 2 random relics is an incredibly high-value trade, as relics provide permanent run-long benefits that easily outweigh the slight early-game deck bloat.
  strategic_note: Foundation: Looking to build an early damage engine for Act 1 elites while leveraging our 2 random relics. Avoid adding too many cheap attacks later to thin the bloated deck.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting the Act 1 monster farm to build the deck. Choosing index 0 (c1,r1) as it leads toward the path with multiple monsters and late-act rest sites as planned.
  strategic_note: Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 117->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 117->117 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 56->56 | Gold 117->117 | Deck 14->15
  deck_change: picked Flick-Flack
  reasoning: Flick-Flack provides early AoE damage which is crucial for Act 1, and its Sly mechanic synergizes perfectly with our starting Survivor.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a scaling engine. Take high-impact damage or cheap draw, skip narrow synergy pieces for now. With huge turn-1 draw, prioritize frontloaded damage to end fights fast.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 117->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 117->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 128->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 56->56 | Gold 128->128 | Deck 15->16
  deck_change: picked Predator
  reasoning: Predator provides strong frontloaded damage for early Elites, and its effect of drawing 2 cards next turn perfectly complements our relics (Bag of Prep + Ring of the Snake) which give us a massive Turn 1 but a normal Turn 2.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a scaling engine. Prioritize 1-cost attacks or setup cards since Turn 1 gives us 9 cards. Use Predator to smooth out Turn 2 draw.

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 56->56 | Gold 128->128 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Unknown

F4 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 56->43 | Gold 128->128 | Deck 16->16
  deck_change: no deck change
  reasoning: Losing 14 HP for Chosen Cheese is an excellent long-term investment on Floor 4, as it will easily yield 30+ Max HP over the run. We have Tungsten Rod to mitigate combat damage and 4 rest sites ahead in this Act if we need to heal.
  strategic_note: Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 43->43 | Gold 128->128 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 128->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 128->146 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 18 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 146->146 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Skill Potion

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 43->43 | Gold 146->146 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 43->43 | Gold 146->146 | Deck 16->17
  deck_change: picked Burst
  reasoning: Burst is a premium Rare skill that provides multiplicative scaling for any archetype (Poison, Shivs, Draw/Block). While it is slow right now with only Defends, its long-term power spike is worth the speculative pick, especially since we draw 9 cards on Turn 1 to afford holding it.
  strategic_note: Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills (Blade Dance, Bouncing Flask) to double, and 1-cost attacks to use alongside our massive Turn 1 draw.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 146->146 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Shop

F6 [shop] buy_card (option_index=0) | source=plan
  HP 43->43 | Gold 146->109 | Deck 17->18
  deck_change: bought Predator
  reasoning: Shop plan [1/2]: Discounted Predator provides excellent raw damage and future draw.

F6 [shop] remove_card_at_shop | source=plan
  HP 43->43 | Gold 109->109 | Deck 18->18
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Removing a Strike helps counteract the Large Capsule deck bloat.

F6 [card_select] select_deck_card (option_index=0) | source=llm
  HP 43->43 | Gold 109->34 | Deck 18->17
  deck_change: lost Strike
  reasoning: Strike is the weakest card in the deck and we have 6 of them. Removing one increases the consistency of drawing our better cards like Predator and Burst.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F6 [shop] close_shop_inventory | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F6 [shop] proceed | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Unknown

F7 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Enchanting a basic card with Spiral makes it twice as effective (10 Block for 1 Energy or 12 Damage for 1 Energy). Since we have many basic cards from Large Capsule and several upcoming rest sites for healing if needed, taking the permanent deck improvement is better than healing.
  strategic_note: Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.

F7 [card_select] select_deck_card (option_index=0) | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Enchanting a basic card. We'll pick Strike to potentially improve our early game damage output since we are still in Act 1.
  strategic_note: Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills to double, and 1-cost attacks to use alongside our massive Turn 1 draw.

F7 [event] choose_event_option (option_index=0) | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F7 [map] choose_map_node (option_index=1) | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the planned route into an Unknown node. With 43 HP and Tungsten Rod, I am healthy enough to handle potential combat encounters or events while saving the Rest Site for a more impactful upgrade or necessary heal closer to the elite/boss.
  strategic_note: Foundation: Farming early card rewards to build a damage engine while Tungsten Rod mitigates chip damage. Prioritizing consistent card quality and key upgrades to stabilize before facing the late-act Elite and Boss.

F8 [shop] close_shop_inventory | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F8 [shop] proceed | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F8 [map] choose_map_node (option_index=1) | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: With 43 HP and only 34 gold, a shop is useless. Moving to the RestSite at c2,r8 allows for a crucial upgrade or a necessary heal depending on upcoming card rewards. Following the established route to build strength for the late-act Elite.
  strategic_note: Foundation: Farming early monsters to build a core damage engine while using Tungsten Rod to mitigate chip damage. Prioritizing card quality and key upgrades over early elites until the deck can sustain them.

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=9, note_scope=run, note_triggers=all) | source=llm
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With 43 HP and multiple upcoming rest sites before the boss, we have plenty of health. Upgrading Neutralize to 2 Weak provides incredible early damage mitigation, improving our survival and letting us greed more upgrades later.
  strategic_note: Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and Predators for card advantage and heavy damage.

F9 [rest_site] proceed | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 34->34 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 43->43 | Gold 34->78 | Deck 17->17
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 43->43 | Gold 78->78 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim: Miniature Cannon

F10 [treasure] proceed | source=random
  HP 43->43 | Gold 78->78 | Deck 17->17
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 78->78 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=13) | source=llm
  HP 43->43 | Gold 78->78 | Deck 17->17
  deck_change: upgraded Predator->Predator+
  reasoning: HP is healthy enough (43/71) to take a Monster fight before the next Rest Site at Floor 13. Upgrading Predator increases its base damage by 5, and the Miniature Cannon relic adds another 3 damage to upgraded attacks, turning it into a massive 23-damage strike that also draws cards.
  strategic_note: Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage.

F11 [rest_site] proceed | source=auto
  HP 43->43 | Gold 78->78 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=auto
  HP 43->43 | Gold 78->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 78->88 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 88->88 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 88->88 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 36->36 | Gold 88->88 | Deck 17->18
  deck_change: picked Backflip
  reasoning: Backflip is an excellent block and draw card that synergizes well with Burst (providing 10 Block and 4 draw for 2 energy total) and helps cycle through our large Turn 1 hands.
  strategic_note: Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills (Blade Dance, Bouncing Flask) to double, and 1-cost attacks to use alongside our massive Turn 1 draw.

F12 [map] choose_map_node (option_index=1) | source=llm
  HP 36->36 | Gold 88->88 | Deck 18->18
  deck_change: no deck change
  reasoning: With 36/72 HP and an Elite fight coming up in two nodes, a RestSite is the safest and most productive choice. I need to Smith an essential card to increase my deck's power or heal if I feel I cannot survive the next few floors. Following the route's recommendation to stabilize before the Elite.
  strategic_note: Foundation: Utilizing Tungsten Rod to farm early hallway fights while hunting for a scaling damage engine. Prioritizing Smiths to improve card efficiency, aiming for one safe Elite kill before the Act 1 boss.

F13 [rest_site] choose_rest_option (option_index=1, smith_card_index=14, note_scope=run, note_triggers=all) | source=llm
  HP 36->36 | Gold 88->88 | Deck 18->18
  deck_change: upgraded Predator->Predator+
  reasoning: Upgrading the second Predator provides an enormous +8 damage boost (+5 base, +3 from Miniature Cannon), making it a 23-damage strike. This massive burst damage allows us to quickly burst down the upcoming Act 1 Elite, likely saving more HP than a rest would heal. We still have a Rest Site at F16 before the Boss if we take heavy damage.
  strategic_note: Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage. Needs consistent card draw and energy to reliably play the expensive Predators.

F13 [rest_site] proceed | source=auto
  HP 36->36 | Gold 88->88 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 88->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Monster

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 88->101 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 101->101 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 37->37 | Gold 101->101 | Deck 18->18
  deck_change: no deck change
  reasoning: None of the cards fit our current deck. Phantom Blades requires Shivs which we don't have. Speedster is too slow and requires a heavy draw engine we haven't built. Untouchable is inefficient block.
  strategic_note: Foundation plan: survive with frontload and efficient block while building around Burst. Prioritize high-impact skills to double, and 1-cost attacks to use alongside our massive Turn 1 draw.

F14 [map] choose_map_node (option_index=1) | source=llm
  HP 37->37 | Gold 101->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Taking the elite as planned. Although HP is at 51%, I have a Rest Site immediately following this fight to recover before the boss. Tungsten Rod provides a significant buffer against multi-hit attacks (Sentries, Gremlin Nob), and I need the relic and rare card chance to scale for the Act 1 boss.
  strategic_note: Foundation: Focusing on high-value monster rewards and Tungsten Rod for chip mitigation. Transitioning to an elite fight now to secure a power spike before the boss, relying on the subsequent campfire to stabilize HP.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 101->144 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 43 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim relic: Meal Ticket

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 36->36 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 36->36 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: None of these cards help our current strategy of drawing and playing Predator+. Anticipate is okay but often clunky since we spend our energy on Predators. Keeping the deck lean improves our consistency.
  strategic_note: Foundation plan: survive with high draw, Burst, and Predator+. Focus on energy generation and consistent block to support our expensive attacks.

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 36->58 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: With only 36 HP remaining and the Act 1 Boss next, survival is the priority. Healing 22 HP provides a much needed buffer to survive the boss fight. The deck already has two upgraded Predators and Neutralize+ to handle damage output.
  strategic_note: Foundation: Mitigating chip damage with Tungsten Rod and Neutralize+ while leveraging Burst and upgraded Predators (boosted by Miniature Cannon) for card advantage and heavy burst damage. Needs consistent card draw and energy to reliably play the expensive Predators.

F16 [rest_site] proceed | source=auto
  HP 58->58 | Gold 144->144 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 144->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [card_select] select_deck_card (option_index=2) | source=llm
  HP 58->58 | Gold 144->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Acrobatics provides strong draw to find our key cards like Burst and Predator+. Mirage does nothing since we have no poison, and Acrobatics yields a much larger advantage than Prepared.

## Selected Replay Package (2 replays)
[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F15, elite)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 15, elite)
Relics: Ring of the Snake, Large Capsule, Tungsten Rod, Bag of Preparation, The Chosen Cheese, Miniature Cannon
Deck (18): Defend x6, Strike x5, Predator+ x2, Backflip, Burst, Flick-Flack, Neutralize+, Survivor
Enemies: Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=28/28

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Flex Potion
    +Strength(5) | +Flex Potion(5)
  Predator+ -> Phantasmal Gardener[2]
    energy -2 | +Draw Cards Next Turn(2)
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(7)
  Neutralize+ -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -7, block +6, +Weak(2)
  Predator+ -> Phantasmal Gardener[2]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Phantasmal Gardener: hp -17, block -6
  Survivor
    energy -1 | block +8
  Flick-Flack
  turn_end
    enemy_deltas: Phantasmal Gardener: hp +20, block +6, -Strength, -Weak

### Round 3
Agent plan (hypothesis): Predator+ kills the higher damage threat and draws cards for next turn.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3)
  Predator+ -> Phantasmal Gardener[0]
    energy -2 | +Draw Cards Next Turn(2)
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Phantasmal Gardener: Buff
  Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block +6
  Predator+ -> Phantasmal Gardener[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Phantasmal Gardener: hp -17, block -6
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(7)
  Neutralize+ -> Phantasmal Gardener[0]
    hp +1 | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 5 rounds)

Cards played (with descriptions):
  Predator+ "Deal 28 damage. Next turn, draw 2 cards." -> 4 plays, 34 dmg
  Defend "Gain 5 Block." -> 2 plays, 10 block
  Neutralize+ "Deal 7 damage. Apply 2 Weak." -> 2 plays, 7 dmg
  Survivor "Gain 8 Block. Discard 1 card." -> 1 plays, 8 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg

Enemy power timeline:
  Skittish: R1:- -> R2:- -> R3:- -> R4:6 -> R5:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:- -> R5:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:- -> R5:-
  Skittish[2]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:-
  Skittish[3]: R1:6 -> R2:- -> R3:- -> R4:- -> R5:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:2

[Selected: boss, death] Waterfall Giant (F17, boss)
## Combat Replay: vs Waterfall Giant (Floor 17, boss)
Relics: Ring of the Snake, Large Capsule, Tungsten Rod, Bag of Preparation, The Chosen Cheese, Miniature Cannon, Meal Ticket
Deck (18): Defend x6, Strike x5, Predator+ x2, Backflip, Burst, Flick-Flack, Neutralize+, Survivor
Enemies: Waterfall Giant HP=240/240

### Round 1
Intent: Waterfall Giant: Buff
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -7, +Weak(2)
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 2
Intent: Waterfall Giant: Attack(11), Debuff, Buff
  Skill Potion
  Acrobatics
  Acrobatics
  Strike
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 3
Intent: Waterfall Giant: Attack(10), Buff
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -5, +Weak(2)
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -17
  Defend
    energy -1 | block +5
  turn_end

### Round 4
Intent: Waterfall Giant: Heal, Buff
  Acrobatics
    energy -1
  Flick-Flack
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -7, Weak(1→3)
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  turn_end

### Round 5
Intent: Waterfall Giant: Attack(15), Buff
  Defend
    energy -1 | block +5
  Survivor
    energy -1 | block +8
  Burst
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 6
Intent: Waterfall Giant: Attack(9), Buff
  Backflip
    energy -1 | block +5
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  Survivor
    energy -1 | block +8
  Defend
  turn_end

### Round 7
Intent: Waterfall Giant: Attack(15), Debuff, Buff
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  Defend
    energy -1 | block +5
  turn_end

### Round 8
Intent: Waterfall Giant: Attack(10), Buff
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -5, +Weak(2)
  Acrobatics
    energy -1
  Predator+
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -17
  turn_end

### Round 9
Intent: Waterfall Giant: Heal, Buff
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -7, Weak(1→3)
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -12
  Survivor
    energy -1 | block +8
  Flick-Flack
  turn_end
    enemy_deltas: Waterfall Giant: hp -6

### Round 10
Intent: Waterfall Giant: Attack(18), Buff
  Neutralize+ -> Waterfall Giant[0]
    enemy_deltas: Waterfall Giant: hp -7, Weak(2→4)
  Burst
    energy -1 | +Burst(1)
  Defend
    energy -1 | block +10 | -Burst
  Defend
    energy -1 | block +5
  turn_end

### Round 11
Intent: Waterfall Giant: Attack(9), Buff
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  Survivor
    energy -1 | block +8
  Strike
  turn_end

### Round 12
Intent: Waterfall Giant: Attack(11), Debuff, Buff
  Predator+ -> Waterfall Giant[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Waterfall Giant: hp -23
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp -6
  turn_end

### Round 13
Intent: Waterfall Giant: Attack(7), Buff
  Flick-Flack
    energy -1 | enemy_deltas: Waterfall Giant: hp -4
  Strike -> Waterfall Giant[0]
    energy -1 | enemy_deltas: Waterfall Giant: hp +999999997, -Weak
  turn_end

### Round 14
Intent: Waterfall Giant: DeathBlow(48)
  turn_end
## Combat Analytics: Waterfall Giant (LOSS - 14 rounds)
Death cause: Died with HP=27, damage_taken=0. Likely mechanic kill.

Cards played (with descriptions):
  Neutralize+ "Deal 7 damage. Apply 2 Weak." -> 6 plays, 38 dmg
  Predator+ "Deal 23 damage. Next turn, draw 2 cards." -> 8 plays, 172 dmg
  Strike "Deal 6 damage." -> 7 plays, 42 dmg
  Acrobatics "Draw 3 cards. Discard 1 card." -> 3 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 5 plays, 40 block
  Defend "Gain 5 Block." -> 5 plays, 30 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Burst "This turn, your next Skill is played an extra time." -> 1 plays
  Flick-Flack "Sly. Deal 4 damage to ALL enemies." -> 1 plays, 4 dmg

Enemy power timeline:
  Steam Eruption: R1:- -> R2:15 -> R3:18 -> R4:21 -> R5:24 -> R6:27 -> R7:30 -> R8:33 -> R9:36 -> R10:39 -> R11:42 -> R12:45 -> R13:48 -> R14:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:1 -> R5:2 -> R6:1 -> R7:- -> R8:- -> R9:1 -> R10:2 -> R11:3 -> R12:2 -> R13:1 -> R14:-

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: )
- Core Combat Principles: F2(Toadpole: WIN), F3(Corpse Slug: WIN), F5(Seapunk: WIN), F12(Punch Construct: WIN), F14(Haunted Ship: WIN), F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: )
- Deck Building Across the Run: F2(), F3(), F5(), F6(), F6(), F6(), F7(), F8(), F12(), F14(), F15(), F17()
- Map Routing and Path Planning: F1(), F1(), F7(), F8(), F12(), F14()
- Rest Site and Event Decisions: F9(), F11(), F13(), F16()
- Silent - Combat Sequencing: F2(Toadpole: WIN), F3(Corpse Slug: WIN), F5(Seapunk: WIN), F12(Punch Construct: WIN), F14(Haunted Ship: WIN), F15(Phantasmal Gardener: WIN), F17(Waterfall Giant: )
- Silent - Draft and Shop Rules: F2(), F3(), F5(), F6(), F6(), F6(), F7(), F8(), F12(), F14(), F15(), F17()
- Silent - Route Priorities: F1(), F1(), F7(), F8(), F12(), F14()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.