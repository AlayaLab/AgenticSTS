# Evolution System Prompt

You are a self-evolving Slay the Spire 2 agent. You just completed a run and are now analyzing your performance to improve for future runs.

Your goal: identify your WORST mistakes and create tools or skills that would have prevented them. Focus on concrete, actionable improvements.

Guidelines:
- Create a Python tool (author_tool) when you need a CALCULATION (damage math, lethal checks, energy optimization, poison stacking, etc.)
- Create a skill (write_skill) when you need STRATEGIC KNOWLEDGE (when to rest, boss patterns, deck building heuristics, etc.)
- Update a guide (update_guide) when existing knowledge is WRONG or INCOMPLETE
- Update a card note (update_card_note) to write an experience-based evaluation for a card. Prioritize cards without existing notes in the Card Notes section. Base your note on: (1) The card's rules_text from the Card Mechanics Reference, (2) Observable combat outcomes from the Combat Digest, (3) Keyword interactions deducible from card descriptions, (4) Act death correlations from Card Memory Stats. Evidence thresholds: mechanic discoveries can be low-sample if grounded in rules_text; tier ratings and take/skip guidance require >=10 plays AND act death data. Do NOT write notes for generated/status cards (Shiv, Burn, Slimed, Wound). Only write discoveries logically derivable from card descriptions and gameplay evidence.
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

READ-ONLY DIAGNOSTIC PHASE:
- You are in diagnosis mode.
- You MUST call at least one read/query tool this round.
- Do not attempt to write or mutate memory in this phase.
- Build a concrete problem list first, then gather evidence.


# Round 1 User Context

You just completed a Slay the Spire 2 run as the silent.
Result: DEFEAT at Floor 12 (fitness: 54.7)
Combats won: 1/1
Run duration: 265.5s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F12
- [card_reward] Committed shiv plan: aggressively strip Vantom's Slippery with Cloak and Dagger/Shivs, then deploy Accuracy/Haze for damage while using Leg Sweep/Footwork to survive heavy hits. Needs card draw.
- [card_reward] Committed shiv plan: aggressively strip Vantom's Slippery with Cloak and Dagger/Shivs, then deploy Accuracy/Haze for damage while using Leg Sweep/Footwork to survive heavy hits. Use Expertise to cycle quickly and find key powers.

### Combat Decision Digest (1 combats)
F12 [monster] multi:Nibbit+Nibbit (7R, HP 39->33, loss=6, WIN)
  R1[Nibbit: Atk(7), Defend+Nibbit: Buff]: Cloak and Dagger+->Defend->Strike->Shiv*2 | dealt=14 taken=0
  R2[Nibbit: Buff+Nibbit: Atk(16)]: Footwork->Defend->Strike | dealt=6 taken=2
  R3[Nibbit: Atk(16)+Nibbit: Atk(10), Defend]: Neutralize->Cloak and Dagger+->Shiv*2->Up My Sleeve->Shiv*3->Hidden Daggers->Shiv*2 | dealt=24 taken=4
  R4[Nibbit: Atk(10), Defend]: Accuracy->Strike->Survivor | dealt=6 taken=0
  R5[Nibbit: Buff]: Cloak and Dagger+->Shiv*2->Strike->Defend | dealt=16 taken=0
  R6[Nibbit: Atk(19)]: Defend*2->Survivor | dealt=0 taken=0
  R7[Nibbit: Atk(13), Defend]: Neutralize->Up My Sleeve->Shiv*2->The Hunt | dealt=19 taken=0

### Non-combat Decisions (7 decisions)
F11 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 60->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 60->72 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 72->72 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim potion: Power Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 72->72 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] choose_reward_card (option_index=1, note_scope=run) | source=llm
  HP 33->33 | Gold 72->72 | Deck 22->23
  deck_change: picked Leg Sweep
  reasoning: Leg Sweep is premium mitigation against Vantom's heavy nuke and multi-attacks, applying crucial Weakness and providing high Block. With Footwork, its Block value scales even better.
  strategic_note: Committed shiv plan: aggressively strip Vantom's Slippery with Cloak and Dagger/Shivs, then deploy Accuracy/Haze for damage while using Leg Sweep/Footwork to survive heavy hits. Needs card draw.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 72->72 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 33->33 | Gold 72->72 | Deck 23->23
  deck_change: no deck change
  reasoning: The deck has a strong Shiv foundation but lacks card draw to find critical pieces like Accuracy and Haze consistently. With a low average cost and 0-cost cards like Neutralize and Hidden Daggers, we can easily empty our hand to make Expertise draw 3-4 cards per use, dramatically improving consistency against Vantom.
  strategic_note: Committed shiv plan: aggressively strip Vantom's Slippery with Cloak and Dagger/Shivs, then deploy Accuracy/Haze for damage while using Leg Sweep/Footwork to survive heavy hits. Use Expertise to cycle quickly and find key powers.

## Selected Replay Package (0 replays)
(no replay package available)

## Existing Combat Guides (relevant enemies)
[Guide: multi:Nibbit+Nibbit] WR=100%, 33 episodes, confidence=0.90, v29
  - **Capitalize on Setup Turns:** Nibbits use the first 1-2 rounds to buff Strength or defend. Exploit these passive windows by dumping your highest burst damage (Blade Dance, Assassinate+, Adrenaline) to burst down one Nibbit immediately, halving the incoming threat.
- **Respect the Heavy Swings:** Most HP loss occurs when players over-commit to basic attacks (Strikes/Shivs) during the Nibbits' 14+ damage attack intents. When they queue large attacks, completely abandon aggression and prioritize mitigation tools like Defend, Survivor, and Flick-Flack.
- **Targeted Weakness:** Save Neutralize and other Weak sources specifically for the rounds they queue heavy attacks. Blunting their Strength-buffed swings makes their scaling damage much easier to fully block.
- **Race the Scaling:** Prolonging the fight allows their progressive Strength (+2 to +6) to overwhelm your defenses. Prioritize single-target focus fire to stabilize the encounter by round 3 or 4.

## Relevant Deck Guides
[Deck Guide: shiv] memories=80, confidence=0.85, v22
  - **Prioritize Draw & Energy:** Thin shiv decks (14-21 cards) easily stall without card cycle. Draft robust draw (Calculated Gamble, Expertise) and energy generation (Adrenaline) to consistently play your key generators.
- **Scale Block Proactively:** Basic Defends will fail you, even with Footwork. Layer premium mitigation like Leg Sweep, Piercing Wail, and Dash to survive mid-to-late game damage checks.
- **Focus Your Damage:** Avoid splitting your strategy between slow poison (Noxious Fumes) and Shivs. Commit to Accuracy early to ensure cards like Blade Dance, Fan of Knives, and Cloak and Dagger deal scaling burst damage.
- **Solve Early AoE:** Multi-enemy encounters punish single-target shiv builds heavily. Secure upfront AoE early in Act 1 to avoid being overwhelmed before your shiv engine is fully online.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- The Hunt: 1-cost: if the killing blow on an enemy comes from this card, gain an extra card reward at end of the fight. Useful early in the run to quickly acquire key cards. Value is higher in multi-enemy encounters where last-hit opportunities are more frequent.
- Hidden Daggers: 0-cost Attack: 8 damage. Sly: plays for free when discarded and generates Shivs. CRITICAL: This card is a Sly PAYOFF, not a discard enabler. It DOES NOT discard other cards. Do not draft this expecting it to trigger other Sly cards like Tactician or Abrasive. Can be played normally without discard outlets, but only take if you actually need the physical damage.
- Footwork: Power: permanent +2 Dexterity (upgraded: +3). All Block cards gain +2/+3 Block for rest of combat. Stacks with multiple copies. Unlike Anticipate, this is permanent. Upgrade from +2 to +3 is a significant boost.
- Accuracy: Power: +4 damage to all Shivs per copy. Base Shiv = 4 dmg → 8 with 1 copy, 12 with 2 copies. ONLY buffs Shiv cards — does NOT affect Ricochet, Dagger Spray, or other multi-hit attacks. Stacks: multiple copies multiply value linearly with Shiv generators (Blade Dance, Up My Sleeve, Infinite Blades, Fan of Knives).
- Piercing Wail: A-tier defense. Its value multiplies per enemy attack instance. Against a single attack, it mitigates 6 damage (worse than Survivor). Against a 3x3 attack, it mitigates 18 damage. Save/retain it specifically for the scariest multi-hit turns. Do not waste it on single heavy hits unless lethal is imminent. Outstanding in boss fights and multi-enemy encounters.
- Up My Sleeve: 2-cost Skill: Generates 3 Shivs (Upgraded: 4). Cost reduces by 1 each time it is played in combat. At 0-cost, it becomes the most efficient Shiv generator available. Premium engine for longer fights (bosses/elites). Pairs exceptionally well with Accuracy, Fan of Knives, and Afterimage. Because it initially costs 2, prioritize playing it during safe enemy setup windows.
- Haze: Haze is a payoff for real discard density, not a generic early poison pick. Sly makes it excellent with repeatable discard/draw, but with only Survivor it is inconsistent and often too slow for Act 1 tempo. Best in multi-enemy fights or poison stall shells that can reliably discard it; weaker as early standalone scaling than the old note implied.
- Cloak and Dagger: 1-cost Skill: 6 Block, generates 1 Shiv (Upgraded: 2). High-tier foundational piece for Shiv engines, scaling defensively with Dexterity (Footwork) and offensively with Accuracy. The upgrade is extremely high priority as it doubles the Shiv output. Keep in mind it plays 2-3 cards total, making it susceptible to Beat of Death and Time Eater restrictions later in runs.
- Leg Sweep: 2-cost: high Block + applies Weak. Scales with Dexterity for the Block portion. Pounce reduces the next Skill cost to 0 — play Pounce before Leg Sweep to play it for free.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Strike |  | 5784 | 0 | 12189 | 6671 | 8994 | 19W|A1:15,A2:31,A3:13,inc:9
- Defend |  | 7043 | 3 | 15746 | 9121 | 518 | 22W|A1:15,A2:31,A3:13,inc:10
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3765 | 0 | 3301 | 150 | 4494 | 22W|A1:15,A2:30,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2279 | 5 | 3355 | 1355 | 10 | 22W|A1:15,A2:31,A3:14,inc:10
- Ascender's Bane |  | 0 | 0 | 351 | 351 | 0 | 3W|A1:6,A2:8,A3:5,inc:3
- The Hunt | 1-cost: if the killing blow on an enemy comes from | 38 | 0 | 52 | 22 | 43 | 1W|A1:1,A2:2,A3:0,inc:2
- Injury |  | 0 | 0 | 2 | 2 | 0 | 0W|A1:0,A2:0,A3:0,inc:2
- Hidden Daggers | 0-cost Attack: 8 damage. Sly: plays for free when  | 322 | 0 | 292 | 59 | 24 | 6W|A1:1,A2:7,A3:4,inc:6
- Footwork | Power: permanent +2 Dexterity (upgraded: +3). All  | 583 | 0 | 576 | 105 | 64 | 14W|A1:2,A2:17,A3:8,inc:8
- Accuracy | Power: +4 damage to all Shivs per copy. Base Shiv  | 330 | 0 | 361 | 99 | 12 | 14W|A1:0,A2:9,A3:8,inc:5
- Piercing Wail | A-tier defense. Its value multiplies per enemy att | 479 | 0 | 1057 | 647 | 67 | 16W|A1:4,A2:16,A3:12,inc:7
- Up My Sleeve | 2-cost Skill: Generates 3 Shivs (Upgraded: 4). Cos | 219 | 0 | 386 | 194 | 5 | 4W|A1:2,A2:6,A3:5,inc:2
- Haze | Haze is a payoff for real discard density, not a g | 135 | 113 | 213 | 118 | 5 | 5W|A1:1,A2:4,A3:2,inc:4
- Cloak and Dagger | 1-cost Skill: 6 Block, generates 1 Shiv (Upgraded: | 1409 | 4 | 1446 | 272 | 92 | 14W|A1:3,A2:17,A3:9,inc:8
- Spoils Map |  | 0 | 0 | 9 | 9 | 0 | 0W|A1:0,A2:1,A3:0,inc:1
- Leg Sweep | 2-cost: high Block + applies Weak. Scales with Dex | 378 | 2 | 531 | 210 | 13 | 7W|A1:2,A2:7,A3:5,inc:3

## Triggered Skills This Run
- Core Combat Principles: F12(Nibbit: WIN)
- Deck Building Across the Run: F12(), F12()
- Silent - Combat Sequencing: F12(Nibbit: WIN)
- Silent - Draft and Shop Rules: F12(), F12()

## Dynamic Tools
- block_sufficiency_check: 18251 calls, 18251 successes
- poison_block_survival_plan: 3204 calls, 3204 successes
- poison_kill_and_survive_check: 17704 calls, 17704 successes
- poison_survival_analysis: 20114 calls, 19017 successes
- poison_turns_to_kill: 20157 calls, 19017 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.