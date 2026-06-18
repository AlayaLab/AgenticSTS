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
Result: VICTORY (fitness: 238.1)
Combats won: 1/1
Run duration: 825.1s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F48
- [card_select] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.
- [hand_select] Tactician++ is a priority discard to regain energy. Flick-Flack++ is also a good Sly target, but energy is more flexible here.

### Combat Decision Digest (1 combats)
F48 [boss] Door (8R, HP 60->22, loss=38, WIN)
  R1[Door: Summon]: Infinite Blades | dealt=0 taken=0
  R2[Doormaker: Atk(30)]: Adrenaline->Poisoned Stab->Mirage+->Shiv->Expertise+->Neutralize+->Backflip+->Dagger Throw->Tactician+->Accelerant+->Bubble Bubble | dealt=14 taken=1
  R3[Doormaker: Atk(18)]: Shiv->Leg Sweep->Backflip+->Tools of the Trade+ | dealt=4 taken=0
  R4[Doormaker: Atk(7x2=14), Buff]: Noxious Fumes+->Shiv->Flick-Flack+ | dealt=4 taken=14
  R5[Doormaker: Atk(24)]: Corrosive Wave+->Calculated Gamble+->Backflip+->Defend+ | dealt=0 taken=0
  R6[Doormaker: Atk(27)]: Shiv->Leg Sweep->Deadly Poison | dealt=4 taken=9
  R7[Doormaker: Atk(9x2=18), Buff]: Malaise->Backstab->Shiv*2 | dealt=19 taken=14
  R8[Doormaker: Atk(24)]: Shiv->Echoing Slash->Deadly Poison->Survivor | dealt=14 taken=0

### Non-combat Decisions (3 decisions)
F48 [card_select] select_deck_card (option_index=2) | source=llm
  HP 60->60 | Gold 24->0 | Deck 32->32
  deck_change: no deck change
  reasoning: Adrenaline costs 0, draws 2 cards, and provides 1 energy. This helps us dig deeper into our deck to find block cards like Backflip, Leg Sweep, or Survivor to mitigate the 30 incoming damage.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs dex/block scaling; skip off-plan attacks and expensive cards.

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 22->22 | Gold 24->24 | Deck 32->32
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 22->0 | Gold 24->24 | Deck 32->32
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (1 replays)
[Selected: boss] Door (F48, boss)
Historical: loss=38 vs historical avg=36.0+/-13.2 (z=0.2, TYPICAL, n=4)
## Combat Replay: vs Door (Floor 48, boss)
Relics: Ring of the Snake, Cursed Pearl, Mercury Hourglass, The Courier, Astrolabe, Pollinous Core, Book of Five Rings, Delicate Frond, Petrified Toad, Vexing Puzzlebox, Pendulum
Deck (32): Backflip+ x2, Deadly Poison x2, Defend x2, Defend+ x2, Accelerant+, Anticipate+, Backstab, Bubble Bubble, Calculated Gamble, Calculated Gamble+, Corrosive Wave+, Dagger Throw, Dash+, Echoing Slash, Expertise+, Flick-Flack+, Greed, Leg Sweep, Malaise, Mirage+, Neutralize+, Noxious Fumes, Noxious Fumes+, Poisoned Stab, Survivor, Tactician+, Tools of the Trade+, Well-Laid Plans+
Enemies: Door HP=999999999/999999999

### Round 1
Agent plan (hypothesis): Next round Doormaker is summoned. Begin applying poison and damage. Save Exhaust cards for Hunger phase if possible.
Agent plan (hypothesis): Doormaker spawns next turn. Prepare for the Hunger phase.
Intent: Door: Summon
  turn_end

### Round 2
Agent plan (hypothesis): Need to block 30 damage. Look for Leg Sweep, Survivor, or Blur.
Agent plan (hypothesis): Look for a discard outlet (Survivor, Gamble) for Tactician++, or play out hand and use Expertise++.
Agent plan (hypothesis): If we draw Gamble or Survivor, discard Tactician for energy. Otherwise play the Defends.
Agent plan (hypothesis): See what we draw, then play Accelerant++ and maybe Flick-Flack++ or Defend++.
Agent plan (hypothesis): Poison scaling established. Next round is Scrutiny, no card draw.
Intent: Doormaker: Attack(30)
  Skill Potion
  Adrenaline
  Speed Potion
    +Dexterity(5) | +Speed Potion(5)
  Tactician+
  turn_end

### Round 3
Agent plan (hypothesis): Scrutiny means no card draw. Next turn is Grasp (cards cost +1 energy?), prepare for it.
Intent: Doormaker: Attack(18)
  turn_end
  Leg Sweep

### Round 4
Agent plan (hypothesis): Next turn is Hunger - expect a 30+ damage attack. Save block/weakness cards.
Intent: Doormaker: Attack(7x2=14), Buff
  turn_end
  Flick-Flack+

### Round 5
Agent plan (hypothesis): Play block cards drawn from Gamble.
Agent plan (hypothesis): If we get Gamble, use it to draw and stack poison.
Agent plan (hypothesis): Blocked fully this turn.
Intent: Doormaker: Attack(24)
  Speed Potion
    +Dexterity(5) | +Speed Potion(5)
  turn_end
  Calculated Gamble

### Round 6
Agent plan (hypothesis): Grasp phase next round! Cards will cost 1 more energy. Ensure we have high-impact plays.
Intent: Doormaker: Attack(27)
  turn_end
  Greed

### Round 7
Agent plan (hypothesis): Next round is Hunger, Doormaker will gain 3 Strength and hit for massive damage. Need to secure lethal or full block.
Agent plan (hypothesis): Survive the incoming 14 damage. Next turn is Hunger phase, need to block massive damage or kill.
Intent: Doormaker: Attack(9x2=18), Buff
  turn_end
  Anticipate+

### Round 8
Intent: Doormaker: Attack(24)
  Defend
  turn_end
## Combat Analytics: Door (WIN - 8 rounds)

Enemy power timeline:
  Grasp: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1 -> R8:-
  Hunger: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:1
  Poison: R1:- -> R2:- -> R3:9 -> R4:6 -> R5:6 -> R6:27 -> R7:32 -> R8:32
  Scrutiny: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:3 -> R7:3 -> R8:3
  Weak: R1:- -> R2:- -> R3:1 -> R4:2 -> R5:1 -> R6:- -> R7:1 -> R8:3

Unattributed damage (power/passive effects): 59
  Per round: R2:14 R3:4 R4:4 R6:4 R7:19 R8:14
Comparator (recent same-enemy comparator):
## Combat Replay: vs Door (Floor 48, boss)
Relics: Ring of the Snake, Golden Pearl, The Chosen Cheese, Bellows, Horn Cleat, Kusarigama, Biiig Hug, Amethyst Aubergine, Lord's Parasol, Pantograph, Regal Pillow, Burning Sticks, Red Mask, Planisphere, The Abacus, Bag of Preparation, Intimidating Helmet, Fragrant Mushroom, Eternal Feather
Deck (37): Blade Dance x3, Defend x3, Afterimage+ x2, Expose x2, Volley x2, Accuracy, Acrobatics, Alchemize+, Backflip, Blade of Ink, Calculated Gamble, Cloak and Dagger, Cloak and Dagger+, Expertise+, Fan of Knives, Flick-Flack, Footwork+, Leading Strike, Leading Strike+, Murder, Neutralize+, Peck, Phantom Blades, Pinpoint, Precise Cut, Prepared, Rolling Boulder, Speedster, Survivor, Well-Laid Plans+
Enemies: Door HP=999999999/999999999

### Round 1
Intent: Door: Summon
  Dexterity Potion
    +Dexterity(2)
  Dexterity Potion
    Dexterity(2→4)
  turn_end

### Round 2
Intent: Doormaker: Attack(30)
  turn_end

### Round 3
Intent: Doormaker: Attack(18)
  Acrobatics
  Poison Potion -> Doormaker[0]
    enemy_deltas: Doormaker: +Poison(6)
  turn_end

### Round 4
Intent: Doormaker: Attack(10x2=20), Buff
  turn_end

### Round 5
Intent: Doormaker: Attack(33)
  turn_end

### Round 6
Intent: Doormaker: Attack(27)
  Volley
  turn_end

### Round 7
Intent: Doormaker: Attack(9x2=18), Buff
  turn_end

### Round 8
Intent: Doormaker: Attack(36)
  Flick-Flack+
  turn_end

### Round 9
Intent: Doormaker: Attack(30)
  turn_end

### Round 10
Intent: Doormaker: Attack(12x2=24), Buff
  cards: Murder, dealt=0, taken=0
## Combat Analytics: Door (WIN - 10 rounds)

Poison stacks applied per card:
  Poison Potion: 6 stacks
Total poison/power tick damage: 379
  Per round: R2:30 R3:37 R4:31 R5:56 R6:67 R7:27 R8:49 R9:82

Enemy power timeline:
  Grasp: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:1
  Hunger: R1:- -> R2:1 -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:1 -> R9:- -> R10:-
  Poison: R1:- -> R2:- -> R3:- -> R4:5 -> R5:4 -> R6:3 -> R7:2 -> R8:1 -> R9:- -> R10:-
  Scrutiny: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:1 -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:3 -> R6:3 -> R7:3 -> R8:6 -> R9:6 -> R10:6
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:2 -> R10:1
  Weak: R1:1 -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:1

## Existing Combat Guides (relevant enemies)
[Guide: Door] WR=100%, 5 episodes, confidence=0.90, v3
  - **Phase Navigation:** Doormaker operates on a strict 3-round cycle. You must adapt your sequencing to each phase's debilitating debuff.
- **Hunger (R2, R5, R8):** Attacks and Skills Exhaust when played. Play only expendable cards or essential Powers. Doormaker permanently gains 3 Strength at the start of R5, R8, and beyond.
- **Scrutiny (R3, R6, R9):** Card draw is disabled. You cannot cycle your deck to find specific answers, so maximize the value of your base hand against the 24+ damage attack.
- **Grasp (R4, R7, R10):** Every card played drains 1 Energy. Sequence high-cost, high-impact cards first. Avoid playing cheap cards early in the turn, as they will instantly consume the Energy needed for your major plays.
- **Damage Race:** By Round 8, Doormaker has +6 Strength, making the Hunger single-hits (36) and Grasp multi-attacks (16x2) extremely difficult to block. Mitigate with Weakness early, but prioritize lethal damage before the scaling overwhelms you.

## Relevant Deck Guides
[Deck Guide: poison] memories=35, confidence=0.80, v7
  - **Size & Scaling:** Target 21-30+ cards. Noxious Fumes+ and Accelerant are your premier damage scalers. Avoid overly thin decks (<18 cards), which lack the raw block and draw to survive Act 2 bosses.
- **The Discard Synergy:** Discard is highly effective for utility. A robust discard engine (Calculated Gamble, Tactician, Acrobatics) perfectly fuels the heavy draw/energy needs of a poison deck. Only avoid mixing poison with discard-damage (Sly attacks) to prevent dead hands.
- **Mitigation is Mandatory:** Poison is inherently slow. Basic Defends aren't enough; heavily prioritize premium mitigation (Leg Sweep, Piercing Wail) and card cycle (Backflip) to stall effectively.
- **Hybridizing Offense:** Early Shivs can provide necessary upfront damage and immediate pressure while waiting for your long-term poison to scale.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- Greed: Greed gives a massive gold injection but CANNOT be removed at shops. If you take this curse, you must commit to managing it in combat via discard (Acrobatics, Dagger Throw) or exhaust (Purity). Do not take it expecting an easy early shop removal.
- Noxious Fumes: Power: applies 2 Poison to ALL enemies at start of each turn passively. Scales linearly over time (turn 5 = 10 total Poison applied). AoE — affects all enemies simultaneously. Upgrade from 2 → 3 per turn is significant for long fights.
- Backstab: 0-cost Innate: 11 damage. Guaranteed in opening hand every combat. Exhaust after use. Provides free first-turn damage with no energy cost.
- Deadly Poison: 1-cost: applies 5 Poison to single target. Core Poison source. Multiple copies stack well. Combos with Accelerant (makes the Poison infinitely scaling) and Envenom (attacks also apply Poison).
- Mirage: 1-cost: Block equal to Poison stacks on the target enemy. Effective only in Poison builds with high stack counts. Useless without Poison on the enemy.
- Leg Sweep: 2-cost: high Block + applies Weak. Scales with Dexterity for the Block portion. Pounce reduces the next Skill cost to 0 — play Pounce before Leg Sweep to play it for free.
- Calculated Gamble: 0-cost: discard entire hand, draw same number of cards. Full hand refresh for free. Triggers Sly on ALL discarded Sly cards simultaneously. Diminishing returns from 2nd copy (only 1 refresh per turn is useful).
- Accelerant: Power: Poison damage triggers an extra time at end of turn. Example: enemy has 20 Poison → normally takes 20 damage, with Accelerant takes 20+19=39 damage. Doubles effective Poison damage that turn. Stacks with more Poison sources (Noxious Fumes, Deadly Poison, Bubble Bubble) for higher burst.
- Flick-Flack: Sly: plays for free when discarded by a card effect. 1-cost 7 damage to ALL enemies. Effective cost is 0 energy via discard outlets (Acrobatics, Survivor, Prepared). AoE damage for free in discard builds.
- Echoing Slash: 1-cost: 10 damage to ALL enemies. AoE attack. Scales with Strength.
- Tactician: Tactician is powerful only with several reliable discard effects or full-hand refresh. In light-discard decks it is effectively an unplayable curse-like draw and makes key defensive turns worse. Do not treat it as generic energy in Shiv/cycle lists unless discard support is already dense.
- Dash: Premium A-tier attack+block. Best on real damage turns or to tempo while defending; avoid spending it just to answer printed damage under Intangible or other temporary mitigation.
- Anticipate: 0-cost: gain 3 Dexterity this turn only. Temporary — expires at end of turn (unlike Footwork which is permanent). Each Block card played this turn gains +3 Block. Best when multiple Block cards are played in the same turn.
- Backflip: 1-cost: block + draw 2. Defends and cycles simultaneously. The draw does not trigger Sly (draw is not discard). Pairs with Dexterity (Footwork) for scaled Block.
- Dagger Throw: 1-cost: 9 damage + draw 1 + discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Cycles deck while dealing damage. Flat 9 damage — does not scale with build progression.
- Expertise: 1-cost: draw up to 6 cards (fills hand to 6). Massive hand refill in one action. Less effective if hand is already near full. Enables combo turns by providing many card options at once.
- Tools of the Trade: Rare Power: draw 1 + discard 1 at start of each turn. The turn-start discard is a card effect, triggering Sly cards every turn automatically. Passive Sly engine — generates discard triggers without spending cards or energy.
- Poisoned Stab: B tier: reliable hybrid frontload+poison. Strong in mixed Shiv/block decks and early boss fights; take when you need steady scaling without full poison commitment, skip once better poison engines or a
- Corrosive Wave: Rare Skill: after playing Corrosive Wave, each card drawn THIS TURN applies Poison to ALL enemies. Pairs with draw cards (Prepared, Acrobatics, Backflip) — more draws in the same turn = more Poison stacks on all enemies. Best with high draw density in the turn it is played.
- Well-Laid Plans: A-tier control enabler: retains 1/2 cards each turn. CRITICAL for surviving strict boss cycles (Lagavulin Matriarch, Skulking Colony). Do not just retain random cards—specifically hold your highest impact mitigation (Neutralize+, Piercing Wail, Leg Sweep) to precisely counter predictable multi-hit/strength spikes. Also excellent for holding burst pieces until lethal is achievable.
- Malaise: X-cost: Consumes ALL remaining energy to reduce Strength & apply Weak. NEVER play two in one turn (the 2nd uses 0 energy and does nothing). Do NOT sequence this last after playing your hand. If you need mitigation, play 0-cost cards, then play Malaise immediately to invest maximum energy. Playing it for 0 or 1 energy against a scaling boss is a massive waste of mitigation.
- Bubble Bubble: Bubble Bubble provides pure Poison density (9 poison for 1 energy). NEVER pick this if your primary win condition relies on physical damage (Accuracy + Shivs), even if you have incidental poison like Envenom. It acts as a curse in physical decks, causing fatal deck bloat and preventing you from drawing your actual scaling and defensive tools during critical Act 2/3 fights.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Defend |  | 7349 | 3 | 16455 | 9544 | 518 | 26W|A1:16,A2:34,A3:13,inc:10
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3948 | 0 | 3462 | 160 | 4494 | 26W|A1:16,A2:33,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2406 | 5 | 3511 | 1404 | 10 | 26W|A1:16,A2:34,A3:14,inc:10
- Greed | Greed gives a massive gold injection but CANNOT be | 0 | 0 | 73 | 73 | 0 | 2W|A1:0,A2:1,A3:0
- Noxious Fumes | Power: applies 2 Poison to ALL enemies at start of | 481 | 0 | 589 | 182 | 45 | 13W|A1:0,A2:9,A3:7,inc:2
- Backstab | 0-cost Innate: 11 damage. Guaranteed in opening ha | 421 | 0 | 422 | 6 | 1169 | 12W|A1:3,A2:12,A3:3,inc:2
- Deadly Poison | 1-cost: applies 5 Poison to single target. Core Po | 741 | 2 | 1053 | 419 | 153 | 11W|A1:1,A2:16,A3:6,inc:2
- Mirage | 1-cost: Block equal to Poison stacks on the target | 67 | 0 | 111 | 57 | 0 | 3W|A1:0,A2:3,A3:3
- Leg Sweep | 2-cost: high Block + applies Weak. Scales with Dex | 390 | 2 | 552 | 220 | 13 | 8W|A1:3,A2:8,A3:5,inc:3
- Calculated Gamble | 0-cost: discard entire hand, draw same number of c | 311 | 0 | 435 | 190 | 186 | 12W|A1:2,A2:12,A3:10,inc:4
- Accelerant | Power: Poison damage triggers an extra time at end | 110 | 0 | 157 | 69 | 2 | 6W|A1:0,A2:6,A3:1,inc:1
- Flick-Flack | Sly: plays for free when discarded by a card effec | 570 | 332 | 727 | 288 | 560 | 11W|A1:7,A2:12,A3:3,inc:3
- Echoing Slash | 1-cost: 10 damage to ALL enemies. AoE attack. Scal | 131 | 0 | 183 | 73 | 496 | 6W|A1:0,A2:2,A3:1
- Tactician | Tactician is powerful only with several reliable d | 92 | 91 | 105 | 55 | 0 | 4W|A1:0,A2:4,A3:1,inc:1
- Dash | Premium A-tier attack+block. Best on real damage t | 315 | 0 | 395 | 117 | 754 | 5W|A1:2,A2:9,A3:6
- Anticipate | 0-cost: gain 3 Dexterity this turn only. Temporary | 207 | 1 | 181 | 21 | 46 | 2W|A1:0,A2:6,A3:1,inc:1
- Backflip | 1-cost: block + draw 2. Defends and cycles simulta | 1704 | 0 | 1906 | 452 | 387 | 21W|A1:6,A2:22,A3:10,inc:3
- Dagger Throw | 1-cost: 9 damage + draw 1 + discard 1. The discard | 1075 | 0 | 1308 | 394 | 2191 | 14W|A1:4,A2:16,A3:5,inc:6
- Expertise | 1-cost: draw up to 6 cards (fills hand to 6). Mass | 229 | 0 | 429 | 225 | 52 | 9W|A1:2,A2:5,A3:5,inc:3
- Tools of the Trade | Rare Power: draw 1 + discard 1 at start of each tu | 104 | 0 | 138 | 61 | 8 | 5W|A1:0,A2:4,A3:3,inc:1
- Poisoned Stab | B tier: reliable hybrid frontload+poison. Strong i | 673 | 0 | 905 | 309 | 1760 | 4W|A1:4,A2:12,A3:4,inc:3
- Corrosive Wave | Rare Skill: after playing Corrosive Wave, each car | 72 | 1 | 119 | 61 | 11 | 5W|A1:0,A2:1,A3:2
- Well-Laid Plans | A-tier control enabler: retains 1/2 cards each tur | 370 | 0 | 527 | 219 | 26 | 16W|A1:3,A2:15,A3:7,inc:1
- Malaise | X-cost: Consumes ALL remaining energy to reduce St | 118 | 0 | 179 | 89 | 29 | 9W|A1:0,A2:6,A3:4,inc:1
- Bubble Bubble | Bubble Bubble provides pure Poison density (9 pois | 120 | 1 | 208 | 113 | 35 | 3W|A1:0,A2:4,A3:2,inc:1

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F48(Door: WIN)
- Core Combat Principles: F48(Door: WIN)
- Deck Building Across the Run: F48()
- High incoming turns are mitigation checks: F48(Door: WIN)
- Silent - Combat Sequencing: F48(Door: WIN)
- Silent - Draft and Shop Rules: F48()

## Dynamic Tools
- block_sufficiency_check: 19479 calls, 19479 successes
- poison_block_survival_plan: 4432 calls, 4432 successes
- poison_kill_and_survive_check: 18932 calls, 18932 successes
- poison_survival_analysis: 21342 calls, 20245 successes
- poison_turns_to_kill: 21385 calls, 20245 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.