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
Result: DEFEAT at Floor 11 (fitness: 56.2)
Combats won: 2/2
Run duration: 306.6s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F6
- [card_reward] Committed shiv plan: rely on Accuracy-buffed shivs for damage and Footwork for block scaling. Prioritize card draw (Acrobatics, Backflip) to cycle through the deck and find generators, while keeping the deck lean of non-synergistic cards.
- [map] Foundation deck: currently focusing on gathering basic damage and block pieces from hallway fights to stabilize. Avoiding elites until a clear scaling or high-damage engine is established. Priority is card quality over gold for now.
### F7
- [event] Foundation phase: building around Shivs with Accuracy, Cloak and Dagger, and Hidden Daggers. Looking for more draw and block density to support the engine.
### F8
- [card_reward] Committed Shiv plan: scale damage with Accuracy and block with Footwork, using Shiv generators to trigger both. Need robust card draw to cycle quickly through the deck and find the key powers. Avoid generic attacks and prioritize card cycle/mitigation.
- [map] Foundation deck: focusing on stabilizing with basic damage and block while utilizing frequent rest sites to upgrade core cards; avoiding early elites until a scaling engine or stronger burst is found.
### F9
- [rest_site] Committed Shiv plan: scale damage with Accuracy and generate Shivs while blocking with Cloak and Dagger and Footwork. Haze provides supplemental AoE poison via discard. Need more card draw and perhaps one more defensive piece to solidify the engine.
### F10
- [map] Foundation deck: focusing on stabilizing with basic damage and block while prioritizing upgrades over low-value shops; seeking a clear damage scaling engine before the Act 1 boss.
### F11
- [rest_site] Committed Shiv plan: scale damage with Accuracy and generate Shivs while blocking with Cloak and Dagger and Footwork. Haze provides supplemental AoE poison via discard. Need more card draw and perhaps one more defensive piece to solidify the engine.

### Combat Decision Digest (2 combats)
F6 [monster] Nibbit (1R, HP 50->50, loss=0, WIN)
  R4[Nibbit: Atk(16)]: Hidden Daggers->Shiv*2 | dealt=8 taken=0

F8 [monster] Vine Shambler (5R, HP 50->39, loss=11, WIN)
  R1[Vine Shambler: Atk(7x2=14)]: Defend->Accuracy->The Hunt->Hidden Daggers->Shiv*2 | dealt=26 taken=9
  R2[Vine Shambler: Atk(9), CardDebuff]: Neutralize->Piercing Wail->Strike*2 | dealt=15 taken=2
  R3[Vine Shambler: Atk(18)]: Footwork->Cloak and Dagger->Survivor->Haze | dealt=0 taken=0
  R4[Vine Shambler: Atk(7x2=14)]: Defend*2->Strike | dealt=6 taken=0
  R5[Vine Shambler: Atk(9), CardDebuff]: Neutralize->Up My Sleeve->Shiv | dealt=3 taken=0

### Non-combat Decisions (21 decisions)
F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 0->12 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 12->12 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 50->50 | Gold 12->12 | Deck 19->20
  deck_change: picked Cloak and Dagger
  reasoning: Cloak and Dagger is an essential piece for our Shiv engine, directly benefiting from both Accuracy (Shiv damage) and Footwork (Block scaling). It also helps strip the Act 1 Boss's Slippery charges.
  strategic_note: Committed shiv plan: rely on Accuracy-buffed shivs for damage and Footwork for block scaling. Prioritize card draw (Acrobatics, Backflip) to cycle through the deck and find generators, while keeping the deck lean of non-synergistic cards.

F6 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 50->50 | Gold 12->12 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F6 [map] choose_map_node (option_index=1) | source=llm
  HP 50->50 | Gold 12->12 | Deck 20->20
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. With only 12 gold and early floor status, taking an Elite (Option 0) is premature, and the Unknown node offers potential for a beneficial event or a standard fight for card rewards without the risk of an early elite wipe.
  strategic_note: Foundation deck: currently focusing on gathering basic damage and block pieces from hallway fights to stabilize. Avoiding elites until a clear scaling or high-damage engine is established. Priority is card quality over gold for now.

F7 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 50->50 | Gold 12->12 | Deck 20->21
  deck_change: added Spoils Map
  reasoning: The Spoils Map provides an incredible economic boost in the next Act, granting 600 Gold. This far outweighs the risk of carrying an unplayable card, and the event guide highly recommends it.
  strategic_note: Foundation phase: building around Shivs with Accuracy, Cloak and Dagger, and Hidden Daggers. Looking for more draw and block density to support the engine.

F7 [event] choose_event_option (option_index=0) | source=auto
  HP 50->50 | Gold 12->12 | Deck 21->21
  deck_change: no deck change
  reasoning: Only option: Proceed

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 50->50 | Gold 12->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Monster

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 12->27 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 27->27 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 39->39 | Gold 27->27 | Deck 21->22
  deck_change: picked Cloak and Dagger
  reasoning: Deck is committed to a Shiv engine with Accuracy and has Footwork for Dexterity scaling. Cloak and Dagger synergizes perfectly with both, providing efficient block and damage. It will also be highly effective for stripping Vantom's Slippery charges.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and block with Footwork, using Shiv generators to trigger both. Need robust card draw to cycle quickly through the deck and find the key powers. Avoid generic attacks and prioritize card cycle/mitigation.

F8 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 39->39 | Gold 27->27 | Deck 22->22
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F8 [map] choose_map_node (option_index=0) | source=llm
  HP 39->39 | Gold 27->27 | Deck 22->22
  deck_change: no deck change
  reasoning: Current HP (39/70) is moderate, but the path ahead contains three rest sites and no elites, providing ample opportunity to upgrade key cards or heal if necessary. Choosing the Rest Site allows for an immediate Smith to strengthen the deck's foundation for upcoming hallway fights.
  strategic_note: Foundation deck: focusing on stabilizing with basic damage and block while utilizing frequent rest sites to upgrade core cards; avoiding early elites until a scaling engine or stronger burst is found.

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=17, note_scope=run, note_triggers=all) | source=llm
  HP 39->39 | Gold 27->27 | Deck 22->22
  deck_change: upgraded Cloak and Dagger->Cloak and Dagger+
  reasoning: With 3 more rest sites before the boss and 39 HP, we can safely upgrade here. Upgrading Cloak and Dagger doubles its Shiv output from 1 to 2, which synergizes incredibly well with our Accuracy power and adds significant flexibility for both offense and defense.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and generate Shivs while blocking with Cloak and Dagger and Footwork. Haze provides supplemental AoE poison via discard. Need more card draw and perhaps one more defensive piece to solidify the engine.

F9 [rest_site] proceed | source=auto
  HP 39->39 | Gold 27->27 | Deck 22->22
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 27->27 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 39->39 | Gold 27->60 | Deck 22->22
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 39->39 | Gold 60->60 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim: Permafrost

F10 [treasure] proceed | source=random
  HP 39->39 | Gold 60->60 | Deck 22->22
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 39->39 | Gold 60->60 | Deck 22->22
  deck_change: no deck change
  reasoning: With 39 HP and only 60 gold, a shop is currently low value as I cannot afford meaningful relics or card removals. The Rest Site is necessary to either heal if the deck feels shaky or, ideally, Smith a key card to increase power for the upcoming monsters. Following the route's recommendation to stabilize before the final stretch of the act.
  strategic_note: Foundation deck: focusing on stabilizing with basic damage and block while prioritizing upgrades over low-value shops; seeking a clear damage scaling engine before the Act 1 boss.

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=17) | source=llm
  HP 39->39 | Gold 60->60 | Deck 22->22
  deck_change: no deck change
  reasoning: HP is safe enough (39/70) for a regular monster fight, and there are two more rest sites before the Act 1 Boss to heal if needed. Upgrading Cloak and Dagger provides an additional Shiv per play, effectively adding 4 base damage (plus 4 more from Accuracy) while retaining its defensive value. This significantly improves our damage output and engine consistency.
  strategic_note: Committed Shiv plan: scale damage with Accuracy and generate Shivs while blocking with Cloak and Dagger and Footwork. Haze provides supplemental AoE poison via discard. Need more card draw and perhaps one more defensive piece to solidify the engine.

## Selected Replay Package (0 replays)
(no replay package available)

## Existing Combat Guides (relevant enemies)
[Guide: Nibbit] WR=99%, 77 episodes, confidence=0.90, v51
  - **Respect Heavy Attacks:** Prioritize full block (Defend, Survivor, Neutralize) against Nibbit's heavy attacks (12-14 damage, BUTT_MOVE). Almost all HP loss (averaging 9.9 per round) occurs when players greed for damage with Strikes on these turns.
- **Exploit Passive Windows:** Nibbit frequently spends turns using Buffs or Defends. Use these strictly safe windows to deploy setup cards (Noxious Fumes, Accuracy) or aggressively unload your damage without needing to block.
- **Beat the Enrage Safely:** Nibbit gains +2 Strength on Round 4 and scales further on Round 7. Aim to finish the fight in 3-5 rounds using poison or frontloaded attacks (Assassinate, Predator, Shivs), but do not sacrifice your HP to race the timer.
- **Mitigate Scaling:** Apply Weak via Neutralize to significantly reduce the threat of Nibbit's heavy hits, especially once the Round 4 Strength buff activates.
[Guide: Vine Shambler] WR=100%, 31 episodes, confidence=0.90, v23
  - **Prioritize Mitigation on Attack Turns:** The Vine Shambler threatens substantial upfront damage through 16-damage single strikes and 12-damage (6x2) multi-hits. On these turns, survival is paramount—focus entirely on applying Weak (Neutralize) and stacking block (Defend, Survivor).
- **Exploit Debuff Windows:** The enemy periodically uses a completely passive `CardDebuff` intent. Treat this as your primary offensive window. Unload Shivs, play Blade Dance, or stack Poison freely without needing to spend energy on block.
- **Avoid Greedy Aggression:** Data shows high-loss rounds (averaging 8.7 damage taken) consistently stem from over-committing to offensive cards (Shivs, Strikes) during attack turns. Never attempt to race the enemy's damage unless you have a guaranteed lethal burst.
- **Leverage Passive Damage:** Poison is highly effective in this encounter. Stacking Poison early allows you to maintain steady damage output while dedicating your energy to turtling during the Shambler's heavy attack cycles.

## Relevant Deck Guides
[Deck Guide: shiv] memories=80, confidence=0.85, v22
  - **Mandatory Card Draw:** Thin decks (14-21 cards) consistently fail without sustained card draw. Prioritize heavy cycle to reliably access your damage engines and defensive tools each turn.
- **Commit to Shiv Scaling:** Do not split focus. Mixing Shivs with slow poison (like Noxious Fumes) leaves you without enough burst for mid-game damage checks. Draft Accuracy early to scale effectively.
- **Robust Defensive Layers:** Basic Defends are insufficient. You must secure strong block scaling alongside Footwork and reliable mitigation (like Piercing Wail) to survive late-game elites.
- **Solve Early AoE:** Pure single-target Shiv builds are highly vulnerable to multi-enemy encounters (e.g., Entomancer). Secure upfront AoE damage early in Act 1 before fully committing to Shiv generation.

## Strategy Rules
(no rules available)

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
- Cloak and Dagger: 1-cost: Block + generates Shivs. Combines defense and Shiv generation in one card. Combos with Accuracy (+4 per Shiv) and Knife Trap (replays exhausted Shivs).

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Strike |  | 5780 | 0 | 12183 | 6669 | 8994 | 19W|A1:15,A2:31,A3:13,inc:8
- Defend |  | 7038 | 3 | 15738 | 9118 | 518 | 22W|A1:15,A2:31,A3:13,inc:9
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3763 | 0 | 3299 | 150 | 4494 | 22W|A1:15,A2:30,A3:14,inc:9
- Survivor | C-tier starter block. Fine early and with discard  | 2277 | 5 | 3353 | 1355 | 10 | 22W|A1:15,A2:31,A3:14,inc:9
- Ascender's Bane |  | 0 | 0 | 349 | 349 | 0 | 3W|A1:6,A2:8,A3:5,inc:2
- The Hunt | 1-cost: if the killing blow on an enemy comes from | 37 | 0 | 50 | 21 | 43 | 1W|A1:1,A2:2,A3:0,inc:1
- Injury |  | 0 | 0 | 1 | 1 | 0 | 0W|A1:0,A2:0,A3:0,inc:1
- Hidden Daggers | 0-cost Attack: 8 damage. Sly: plays for free when  | 321 | 0 | 291 | 59 | 24 | 6W|A1:1,A2:7,A3:4,inc:5
- Footwork | Power: permanent +2 Dexterity (upgraded: +3). All  | 582 | 0 | 575 | 105 | 64 | 14W|A1:2,A2:17,A3:8,inc:7
- Accuracy | Power: +4 damage to all Shivs per copy. Base Shiv  | 329 | 0 | 360 | 99 | 12 | 14W|A1:0,A2:9,A3:8,inc:4
- Piercing Wail | A-tier defense. Its value multiplies per enemy att | 479 | 0 | 1055 | 645 | 67 | 16W|A1:4,A2:16,A3:12,inc:6
- Up My Sleeve | 2-cost Skill: Generates 3 Shivs (Upgraded: 4). Cos | 217 | 0 | 384 | 194 | 5 | 4W|A1:2,A2:6,A3:5,inc:1
- Haze | Haze is a payoff for real discard density, not a g | 135 | 113 | 212 | 117 | 5 | 5W|A1:1,A2:4,A3:2,inc:3
- Cloak and Dagger | 1-cost: Block + generates Shivs. Combines defense  | 1406 | 4 | 1442 | 271 | 92 | 14W|A1:3,A2:17,A3:9,inc:7
- Spoils Map |  | 0 | 0 | 7 | 7 | 0 | 0W|A1:0,A2:1,A3:0

## Triggered Skills This Run
- Avoid Accidental Forced Elites: F6(), F6(), F8(), F10()
- Core Combat Principles: F6(Nibbit: WIN), F8(Vine Shambler: WIN)
- Deck Building Across the Run: F6(), F8()
- Map Routing and Path Planning: F6(), F6(), F8(), F10()
- Rest Site and Event Decisions: F9(), F11()
- Silent - Combat Sequencing: F6(Nibbit: WIN), F8(Vine Shambler: WIN)
- Silent - Draft and Shop Rules: F6(), F8()
- Silent - Route Priorities: F6(), F6(), F8(), F10()

## Dynamic Tools
- block_sufficiency_check: 18242 calls, 18242 successes
- poison_block_survival_plan: 3195 calls, 3195 successes
- poison_kill_and_survive_check: 17695 calls, 17695 successes
- poison_survival_analysis: 20105 calls, 19008 successes
- poison_turns_to_kill: 20148 calls, 19008 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.