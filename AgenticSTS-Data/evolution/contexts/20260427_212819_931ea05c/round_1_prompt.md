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

You just completed a Slay the Spire 2 run as the ironclad.
Result: DEFEAT at Floor 8 (fitness: 68.2)
Combats won: 2/2
Run duration: 805.9s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.
- [map] Early act deck-building phase: prioritizing strong attack and block commons to stabilize the deck while seeking a damage engine for elite fights, avoiding over-commitment to archetypes until the first rare or key synergy appears.
### F2
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F3
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F4
- [event] Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.
- [card_select] Foundation phase: prioritize early frontload damage to handle elites while keeping efficient block. Still looking for a scaling engine; remove Strikes to draw our better attacks.
### F5
- [card_select] Foundation phase: rely on frontload damage (Sword Boomerang, Molten Fist) and Vulnerable synergy while seeking a real scaling engine. Prioritize elites to leverage Booming Conch.
- [map] Building a balanced Ironclad deck focused on high-damage attacks to capitalize on Burning Blood sustain, while prioritizing card removal at shops to keep the deck lean and reliable.
### F6
- [event] Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.
- [map] Building a balanced Ironclad deck focused on high-damage attacks to capitalize on Burning Blood sustain, while prioritizing card removal at shops to keep the deck lean and reliable.
### F7
- [rest_site] Foundation deck focused on scaling Vulnerable with Bash and Molten Fist for burst damage. Missing card draw and AoE. Avoid taking too many generic attacks; look for strong block or scaling powers.

### Combat Decision Digest (3 combats)
F2 [monster] multi:Toadpole+Toadpole (4R, HP 80->79, loss=1, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Bash->Defend | dealt=0 taken=2
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike*3 | dealt=6 taken=4
  R3[Toadpole: Atk(3x3=9)]: Defend*2->Strike | dealt=6 taken=1
  R4[Toadpole: Atk(7)]: Strike*2 | dealt=6 taken=0

F3 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 79->80, loss=0, WIN)
  R1[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Defend*2->Sword Boomerang | dealt=9 taken=4
  R2[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Defend*2->Strike | dealt=6 taken=0
  R3[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Defend*2->Strike | dealt=6 taken=0
  R4[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike->Sword Boomerang->Strike | dealt=15 taken=0
  R5[Corpse Slug: Atk(7x2=14)]: Strike*2 | dealt=6 taken=0

F8 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (8R, HP 80->0, loss=80, LOSS)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Defend*2->Strike | dealt=0 taken=5
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Bash+->Defend | dealt=10 taken=12
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)]: Defend*3 | dealt=0 taken=4
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(3x3=9)]: Bash+->Strike | dealt=18 taken=13
  R5[Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff]: Defend*3 | dealt=0 taken=10
  R6[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Atk(9)]: Strike->Defend*2 | dealt=0 taken=8
  R7[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Buff]: Defend*2->Strike | dealt=0 taken=8
  R8[Phantasmal Gardener: Atk(11)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)]: Bash+->Molten Fist | dealt=19 taken=0

### Non-combat Decisions (30 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 80->80 | Gold 99->99 | Deck 10->10
  deck_change: no deck change
  reasoning: Booming Conch provides a permanent, run-long benefit in Elite fights, which are the most dangerous encounters and the key to snowballing. Drawing 2 extra cards on turn 1 significantly reduces the chance of a bad opening hand against Elites. Lost Coffer is only a one-time bonus, and Silver Crucible's downside of losing the first chest is too steep a cost.
  strategic_note: Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 80->80 | Gold 99->99 | Deck 10->10
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 80->80 | Gold 99->0 | Deck 10->10
  deck_change: no deck change
  reasoning: Following the aggressive early-act strategy to build the deck and earn gold for a shop, taking the monster node at [1,1] to initiate the run with immediate card rewards.
  strategic_note: Early act deck-building phase: prioritizing strong attack and block commons to stabilize the deck while seeking a damage engine for elite fights, avoiding over-commitment to archetypes until the first rare or key synergy appears.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 79->79 | Gold 99->112 | Deck 10->10
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 79->79 | Gold 112->112 | Deck 10->10
  deck_change: no deck change
  reasoning: Claim potion: Swift Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 79->79 | Gold 112->112 | Deck 10->10
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 79->79 | Gold 112->112 | Deck 10->11
  deck_change: picked Sword Boomerang
  reasoning: Floor 2 requires adding damage to deal with upcoming Elites and harder hallway fights. Sword Boomerang provides 9 base damage for 1 energy (better than a Strike), synergizes with Bash's Vulnerable, and scales exceptionally well with any future Strength gains.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F2 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 79->79 | Gold 112->112 | Deck 11->11
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 79->79 | Gold 112->0 | Deck 11->11
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 80->80 | Gold 112->124 | Deck 11->11
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 80->80 | Gold 124->124 | Deck 11->11
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 80->80 | Gold 124->124 | Deck 11->12
  deck_change: picked Molten Fist
  reasoning: Molten Fist provides excellent frontload damage (10 base, 15 under Vulnerable) and combos perfectly with Bash, doubling its 2 Vulnerable to 4 and keeping targets vulnerable for the entire fight. It also exhausts itself, keeping our deck thin for subsequent cycles.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F3 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 80->80 | Gold 124->124 | Deck 12->12
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 80->80 | Gold 124->124 | Deck 12->12
  deck_change: no deck change
  reasoning: Only path: Unknown

F4 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=deck_building) | source=llm
  HP 80->80 | Gold 124->124 | Deck 12->12
  deck_change: no deck change
  reasoning: Removing a basic Strike or Defend is highly valuable for improving deck consistency early in the run, whereas upgrading random cards risks hitting basics with low impact.
  strategic_note: Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.

F4 [card_select] select_deck_card (option_index=0) | source=llm
  HP 80->80 | Gold 124->124 | Deck 12->11
  deck_change: lost Strike
  reasoning: Standard early Act 1 removal for Ironclad is a Strike. We have already added Molten Fist and Sword Boomerang, which provide better damage, so removing a Strike improves our average card quality and draw density while keeping our block intact.
  strategic_note: Foundation phase: prioritize early frontload damage to handle elites while keeping efficient block. Still looking for a scaling engine; remove Strikes to draw our better attacks.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 80->80 | Gold 124->124 | Deck 11->11
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 80->80 | Gold 124->124 | Deck 11->11
  deck_change: no deck change
  reasoning: Only path: Shop

F5 [shop] remove_card_at_shop | source=plan
  HP 80->80 | Gold 124->124 | Deck 11->11
  deck_change: no deck change
  reasoning: Shop plan [1/2]: Thinning a starter card (Strike) improves the consistency of drawing our better cards like Bash and Molten Fist.

F5 [card_select] select_deck_card (option_index=0) | source=llm
  HP 80->80 | Gold 124->49 | Deck 11->10
  deck_change: lost Strike
  reasoning: Removing a Strike to thin the deck and draw our better attacks (Molten Fist, Sword Boomerang) more consistently. We have enough damage to afford a Strike removal.
  strategic_note: Foundation phase: rely on frontload damage (Sword Boomerang, Molten Fist) and Vulnerable synergy while seeking a real scaling engine. Prioritize elites to leverage Booming Conch.

F5 [shop] buy_potion (option_index=2) | source=plan
  HP 80->80 | Gold 49->1 | Deck 10->10
  deck_change: no deck change
  reasoning: Shop plan [2/2]: A Block Potion is excellent insurance for upcoming Elite fights, which we need to tackle for relics and card rewards.

F5 [shop] close_shop_inventory | source=plan
  HP 80->80 | Gold 1->1 | Deck 10->10
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F5 [shop] proceed | source=auto
  HP 80->80 | Gold 1->1 | Deck 10->10
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F5 [map] choose_map_node (option_index=1) | source=llm
  HP 80->80 | Gold 1->1 | Deck 10->10
  deck_change: no deck change
  reasoning: The route through the Unknown node leads to a Shop and potentially an Elite, which is crucial for early power spikes and relic acquisition to justify an aggressive, Burning Blood-fueled playstyle.
  strategic_note: Building a balanced Ironclad deck focused on high-damage attacks to capitalize on Burning Blood sustain, while prioritizing card removal at shops to keep the deck lean and reliable.

F6 [event] choose_event_option (option_index=0) | source=llm
  HP 80->80 | Gold 1->56 | Deck 10->10
  deck_change: no deck change
  reasoning: Taking an Eternal curse like Greed is run-ruining, as it can never be removed from the deck and will constantly act as a dead draw. We will take the safe gold from the first chest.
  strategic_note: Foundation phase: relying on Bash and Strikes. Focus on picking up high-damage attacks to clear Act 1 elites, leveraging the extra turn 1 draw from Booming Conch to set up quickly.

F6 [event] choose_event_option (option_index=0) | source=auto
  HP 80->80 | Gold 56->56 | Deck 10->10
  deck_change: no deck change
  reasoning: Only option: Proceed

F6 [map] choose_map_node (option_index=1) | source=llm
  HP 80->80 | Gold 56->56 | Deck 10->10
  deck_change: no deck change
  reasoning: Resting at floor 6 with 80/80 HP is a massive waste of resources, but the provided route forces a RestSite here. Since I am full HP, I will Smith (upgrade) a key card to increase my combat efficiency, adhering to the strategy that upgrading is better than healing.
  strategic_note: Building a balanced Ironclad deck focused on high-damage attacks to capitalize on Burning Blood sustain, while prioritizing card removal at shops to keep the deck lean and reliable.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=7) | source=llm
  HP 80->80 | Gold 56->56 | Deck 10->10
  deck_change: upgraded Bash->Bash+
  reasoning: HP is at maximum, so we Smith. Bash+ increases Vulnerable duration to 3 turns, which pairs excellently with Molten Fist (doubling Vulnerable) and is crucial for burning down Act 1 Elites.
  strategic_note: Foundation deck focused on scaling Vulnerable with Bash and Molten Fist for burst damage. Missing card draw and AoE. Avoid taking too many generic attacks; look for strong block or scaling powers.

F7 [rest_site] proceed | source=auto
  HP 80->80 | Gold 56->56 | Deck 10->10
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 80->80 | Gold 56->0 | Deck 10->10
  deck_change: no deck change
  reasoning: Only path: Elite

## Selected Replay Package (1 replays)
[Selected: elite, death] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F8, elite)
Historical: loss=80 vs historical avg=16.7+/-16.6 (z=3.8, WORSE_THAN_USUAL, n=14)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 8, elite)
Relics: Burning Blood, Booming Conch
Deck (10): Defend x4, Strike x3, Bash+, Molten Fist, Sword Boomerang
Enemies: Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=31/31

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end

### Round 4
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(3x3=9)
  Block Potion
    block +12
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff
  turn_end

### Round 6
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Attack(9)
  Swift Potion
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Buff
  turn_end

### Round 8
Intent: Phantasmal Gardener: Attack(11), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (LOSS - 8 rounds)
Death cause: Died with HP=20, damage_taken=0. Likely mechanic kill.

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[3]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:- -> R8:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:2 -> R6:2 -> R7:4 -> R8:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:2 -> R8:4
  Strength[3]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:2 -> R6:4 -> R7:- -> R8:-
  Vulnerable: R1:- -> R2:- -> R3:2 -> R4:1 -> R5:3 -> R6:2 -> R7:- -> R8:-

Unattributed damage (power/passive effects): 47
  Per round: R2:10 R4:18 R8:19
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 14, elite)
Relics: Ring of the Snake, Phial Holster, The Chosen Cheese, Strike Dummy
Deck (21): Defend x5, Strike x5, Piercing Wail x2, Accuracy, Ascender's Bane, Backstab, Blade Dance+, Dagger Spray, Fan of Knives, Neutralize, Survivor, Up My Sleeve
Enemies: Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=32/32, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=31/31

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Fysh Oil
    +Strength(1) | +Dexterity(1)
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Block Potion
    block +12
  turn_end
    exhausted: Shiv*7 [0费]：Deal 4 damage. Exhaust.

### Round 3
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  Defend
  turn_end

### Round 4
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(3x3=9)
  cards: Strike, Fan of Knives, Shiv, Shiv, Shiv, Shiv, dealt=30, taken=0
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 4 rounds)

Enemy power timeline:
  Skittish[0]: R1:7 -> R2:7 -> R3:7 -> R4:7
  Skittish[1]: R1:7 -> R2:7 -> R3:7 -> R4:7
  Skittish[2]: R1:7 -> R2:7 -> R3:7 -> R4:7
  Skittish[3]: R1:7 -> R2:7 -> R3:- -> R4:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2

Unattributed damage (power/passive effects): 30
  Per round: R4:30

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F8(Phantasmal Gardener: )
- Core Combat Principles: F2(Toadpole: WIN), F3(Corpse Slug: WIN), F8(Phantasmal Gardener: )
- Deck Building Across the Run: F2(), F3(), F4(), F5(), F5()
- Map Routing and Path Planning: F1(), F1(), F5(), F6()
- Never Smith Upgraded Cards: F7()
- Rest Site and Event Decisions: F7()
- Silent - Combat Sequencing: F2(Toadpole: WIN), F3(Corpse Slug: WIN), F8(Phantasmal Gardener: )
- Silent - Draft and Shop Rules: F2(), F3(), F4(), F5(), F5()
- Silent - Route Priorities: F1(), F1(), F5(), F6()

## Dynamic Tools
- block_sufficiency_check: 21154 calls, 21154 successes
- poison_block_survival_plan: 6107 calls, 6107 successes
- poison_kill_and_survive_check: 20607 calls, 20607 successes
- poison_survival_analysis: 23017 calls, 21920 successes
- poison_turns_to_kill: 23060 calls, 21920 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.