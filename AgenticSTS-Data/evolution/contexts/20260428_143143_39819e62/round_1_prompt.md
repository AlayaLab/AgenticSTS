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
Result: DEFEAT at Floor 33 (fitness: 111.8)
Combats won: 1/1
Run duration: 1049.3s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F31
- [card_reward] Committed to hybrid poison/shiv stall plan: stall with Fumes, Snecko Skull, and efficient block (Piercing Wail, Shadowmeld) while using shivs and early attacks for frontload. Focus on thinning the deck or adding more draw to cycle defensive tools faster.
### F32
- [rest_site] Hybrid poison/shiv deck: use Noxious Fumes for scaling damage and shivs/attacks for immediate impact, playing defensive skills to block and draw. Focus on surviving while poison ticks down the Act 2 boss.

### Combat Decision Digest (2 combats)
F31 [monster] Chomper (3R, HP 53->54, loss=0, WIN)
  R2[Chomper: Atk(8x2=16)]: Cloak and Dagger->Shiv->Defend->Survivor | dealt=4 taken=0
  R3[Chomper: StatusCard({CardCount})]: Noxious Fumes->Neutralize+->Deflect->Volley+ | dealt=32 taken=0
  R4[Chomper: Atk(6x2=12)]: Slice->Strike | dealt=6 taken=0

F33 [boss] multi:Crusher+Rocket (9R, HP 72->0, loss=72, LOSS)
  R1[Crusher: Atk(18)+Rocket: Atk(3)]: Assassinate->Strike*3->Defend*2->Survivor | dealt=45 taken=0
  R2[Crusher: Atk(4)+Rocket: Atk(27)]: Cloak and Dagger->Shiv->Expertise+->Noxious Fumes | dealt=4 taken=18
  R3[Crusher: Atk(9x2=18), Debuff+Rocket: Buff]: Shadowmeld+->Piercing Wail->Noxious Fumes->Backflip->Neutralize+ | dealt=4 taken=0
  R4[Crusher: Buff+Rocket: Atk(24)]: Flechettes->Deflect->Defend->Exterminate->Slice | dealt=26 taken=18
  R5[Crusher: Atk(21), Defend+Rocket: Sleep]: Shadowmeld+->Survivor->Flechettes->Strike | dealt=4 taken=2
  R6[Crusher: Atk(14)+Rocket: Atk(7)]: Deflect->Cloak and Dagger->Defend->Exterminate->Shiv | dealt=12 taken=6
  R7[Crusher: Atk(6)+Rocket: Atk(30)]: Defend->Flick-Flack->Leading Strike->Shiv*2 | dealt=38 taken=12
  R8[Crusher: Atk(12x2=24), Debuff+Rocket: Buff]: Backflip*2->Neutralize+->Slice->Defend | dealt=10 taken=0
  R9[Crusher: Buff+Rocket: Atk(52)]: Strike->Survivor->Defend | dealt=4 taken=0

### Non-combat Decisions (9 decisions)
F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 89->105 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: {gold} Gold

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 105->105 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F31 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 54->54 | Gold 105->105 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F31 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 54->54 | Gold 105->105 | Deck 27->28
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a premium defensive tool, especially valuable against multi-attack enemies. The upcoming boss features heavy hitting attacks, and mitigating a multi-attack turn buys us crucial time for our Noxious Fumes and Snecko Skull poison to scale. It exhausts, meaning it doesn't clutter our deck in long fights.
  strategic_note: Committed to hybrid poison/shiv stall plan: stall with Fumes, Snecko Skull, and efficient block (Piercing Wail, Shadowmeld) while using shivs and early attacks for frontload. Focus on thinning the deck or adding more draw to cycle defensive tools faster.

F31 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 54->54 | Gold 105->105 | Deck 28->28
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 105->105 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 54->72 | Gold 105->105 | Deck 28->28
  deck_change: no deck change
  reasoning: With the Act 2 Boss next and 18 HP missing, healing is the safest play to maximize survival chances. A larger health buffer is more valuable than a single upgrade right now.
  strategic_note: Hybrid poison/shiv deck: use Noxious Fumes for scaling damage and shivs/attacks for immediate impact, playing defensive skills to block and draw. Focus on surviving while poison ticks down the Act 2 boss.

F32 [rest_site] proceed | source=auto
  HP 72->72 | Gold 105->105 | Deck 28->28
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 72->72 | Gold 105->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Boss

## Selected Replay Package (1 replays)
[Selected: boss, death] multi:Crusher+Rocket (F33, boss)
Historical: loss=72 vs historical avg=35.7+/-16.0 (z=2.3, WORSE_THAN_USUAL, n=35)
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Ring of the Snake, Phial Holster, Meal Ticket, Potion Belt, Reptile Trinket, Very Hot Cocoa, Snecko Skull, Ripple Basin, Anchor, The Chosen Cheese, Akabeko
Deck (28): Defend x5, Strike x4, Backflip x2, Noxious Fumes x2, Assassinate, Blade of Ink, Cloak and Dagger, Deflect, Expertise+, Exterminate, Flechettes, Flick-Flack, Leading Strike, Neutralize+, Piercing Wail, Shadowmeld+, Slice, Survivor, Volley+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  turn_end

### Round 2
Intent: Crusher: Attack(4), Rocket: Attack(27)
  turn_end

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  turn_end

### Round 4
Intent: Crusher: Buff, Rocket: Attack(24)
  turn_end

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  Strike
  turn_end
    -融入暗影

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  turn_end

### Round 7
Intent: Crusher: Attack(6), Rocket: Attack(30)
  Block Potion
    block +12 | +力量(3) | +爬行动物饰品(3)
  turn_end

### Round 8
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  turn_end

### Round 9
Intent: Crusher: Buff, Rocket: Attack(52)
  Strike
  turn_end
## Combat Analytics: multi:Crusher+Rocket (LOSS - 9 rounds)
Death cause: Died with HP=16, damage_taken=0. Likely mechanic kill.

Active powers: 遭到包围(1), 活力(8)

Enemy power timeline:
  中毒[0]: R1:- -> R2:- -> R3:3 -> R4:7 -> R5:11 -> R6:15 -> R7:19 -> R8:23 -> R9:27
  中毒[1]: R1:- -> R2:- -> R3:3 -> R4:7 -> R5:11 -> R6:15 -> R7:19 -> R8:23 -> R9:27
  力量: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  力量[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:2
  力量[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:4
  后方攻击[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  后方攻击[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  虚弱: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1
  蟹之怒[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1
  蟹之怒[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1

Unattributed damage (power/passive effects): 147
  Per round: R1:45 R2:4 R3:4 R4:26 R5:4 R6:12 R7:38 R8:10 R9:4
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Crusher+Rocket (Floor 33, boss)
Relics: Burning Blood, Golden Pearl, The Chosen Cheese, Membership Card, Kusarigama, Eternal Feather, Meat on the Bone, Sand Castle, Gorget, Kunai, Mummified Hand, Happy Flower
Deck (29): Defend x3, Strike x3, Strike+ x2, Bash+, Battle Trance+, Blood Wall, Breakthrough+, Burning Pact+, Colossus, Defend+, Demon Form+, Dominate+, Expertise+, Fight Me!, Inferno, Lantern Key, Pommel Strike+, Pyre+, Seeker Strike, Sword Boomerang+, True Grit+, Twin Strike+, Unrelenting, Whirlwind+
Enemies: Crusher HP=209/209, Rocket HP=199/199

### Round 1
Intent: Crusher: Attack(18), Rocket: Attack(3)
  Colorless Potion
  Flash of Steel
  Inferno
    exhausted: Inferno [1费]：At the start of your turn, lose 1 HP. Whenever you lose HP on your turn, deal 6 damage to ALL enemies.
  Lantern Key
  turn_end
    block +4

### Round 2
Intent: Crusher: Attack(4), Rocket: Attack(27)
  Strike
    exhausted: Strike [1费]：Deal 6 damage.
  turn_end
    block +3

### Round 3
Intent: Crusher: Attack(9x2=18), Debuff, Rocket: Buff
  turn_end
    block +2

### Round 4
Intent: Crusher: Buff, Rocket: Attack(49)
  turn_end
    block +1

### Round 5
Intent: Crusher: Attack(21), Defend, Rocket: Sleep
  turn_end

### Round 6
Intent: Crusher: Attack(14), Rocket: Attack(7)
  Burning Pact+
  Speed Potion
    Dexterity(3→8) | +Speed Potion(5)
  Strike
  turn_end

### Round 7
Intent: Crusher: Attack(9), Rocket: Attack(21)
  turn_end

### Round 8
Intent: Crusher: Attack(12x2=24), Debuff, Rocket: Buff
  turn_end

### Round 9
Intent: Crusher: Buff, Rocket: Attack(54)
  turn_end

### Round 10
Intent: Crusher: Attack(22), Defend
  Fight Me!
    exhausted: Strike*2 [1费]：Deal 6 damage.
  turn_end

### Round 11
Intent: Crusher: Attack(22)
  cards: Flash of Steel, Twin Strike+, Strike, dealt=16, taken=0
## Combat Analytics: multi:Crusher+Rocket (WIN - 11 rounds)

Active powers: Plating(4), Surrounded(1)

Enemy power timeline:
  Back Attack: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:1 -> R11:1
  Back Attack[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:- -> R11:-
  Back Attack[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:- -> R11:-
  Crab Rage[0]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:- -> R11:-
  Crab Rage[1]: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1 -> R8:1 -> R9:1 -> R10:- -> R11:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:10 -> R11:10
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2 -> R9:2 -> R10:- -> R11:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:3 -> R8:3 -> R9:5 -> R10:- -> R11:-
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:-

Unattributed damage (power/passive effects): 368
  Per round: R1:5 R3:43 R4:8 R5:56 R6:24 R7:50 R8:85 R9:57 R10:24 R11:16

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F33(Crusher: )
- Core Combat Principles: F31(Chomper: WIN), F33(Crusher: )
- Deck Building Across the Run: F31()
- Never Smith Upgraded Cards: F32()
- Rest Site and Event Decisions: F32()
- Silent - Combat Sequencing: F31(Chomper: WIN), F33(Crusher: )
- Silent - Draft and Shop Rules: F31()
- Sly Discard Synergies: F31()

## Dynamic Tools
- block_sufficiency_check: 21395 calls, 21395 successes
- poison_block_survival_plan: 6348 calls, 6348 successes
- poison_kill_and_survive_check: 20848 calls, 20848 successes
- poison_survival_analysis: 23258 calls, 22161 successes
- poison_turns_to_kill: 23301 calls, 22161 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.