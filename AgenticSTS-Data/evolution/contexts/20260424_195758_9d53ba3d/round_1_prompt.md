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
Result: DEFEAT at Floor 17 (fitness: 71.1)
Combats won: 9/9
Run duration: 2956.7s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: prioritize drafting high-damage attacks immediately since we are thinning out starter strikes.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. Just removed 2 Strikes, need early damage urgently.
- [map] Foundation phase: prioritizing front-loaded damage and efficient block to survive the first three hallway fights. Seeking cards like Dagger Throw or Poison Stab to establish a core damage engine while keeping the deck lean for future synergy.
### F2
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F3
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F4
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a scaling engine. Take high-impact damage and cheap draw, keep options open for Shiv or Poison engines depending on upcoming drops.
### F5
- [card_reward] Foundation plan: transition into a committed Shiv engine. Prioritize Accuracy, Phantom Blades, and Afterimage. Take draw (Acrobatics) to cycle to Shiv generators faster, and skip generic non-Shiv attacks to keep the deck lean.
### F6
- [card_reward] Committed to Shivs: retain shivs for guaranteed +9 damage procs each turn. Prioritize draw, efficient block, and maybe one more Shiv generator. Avoid expensive off-plan attacks.
- [map] Foundation phase: focusing on securing high-impact damage and defensive staples. Current priority is stabilizing HP via rest sites to survive the upcoming Elite while looking for a more definitive damage engine like Poison or Shivs.
### F7
- [rest_site] Foundation Shiv/Damage deck: generate Shivs and hold them with Phantom Blades to maximize extra damage output. Needs card draw and an energy relic or reliable block engine.
### F8
- [event] Foundation: Physical damage with Phantom Blades and shivs/Neutralize. Play Phantom Blades early and aggressively use shivs for damage. Still looking for better block options or a reliable AoE tool for Act 2.
### F9
- [card_reward] Committed Shiv plan: prioritize Shiv generators (Blade Dance, Cloak and Dagger) and payoffs (Accuracy, Finisher), using Expertise to refill hand after playing out cheap cards. Needs scaling damage and block; skip high-cost cards that clunk up Expertise.
- [map] Foundation phase: currently prioritizing HP stabilization via upcoming rest sites while seeking a core engine like Poison or Shivs to provide scaling damage for the Act 1 boss.
### F10
- [map] Foundation phase: focusing on stabilizing HP via rest sites to survive the upcoming encounters while looking for a more definitive damage engine like Poison or Shivs.
### F11
- [rest_site] Foundation Shiv/Damage deck: generate Shivs and hold them with Phantom Blades to maximize extra damage output. Needs card draw and an energy relic or reliable block engine.
### F12
- [card_reward] Committed shiv plan: scale Shivs with Phantom Blades, keep generators, and block efficiently with Weak. Need more Shiv generation and draw (Acrobatics/Backflip). Skip generic attacks.
### F13
- [card_reward] Committed Shiv plan: setup Phantom Blades early, then use Blade Dance and Blade of Ink to burst enemies down. Use Expertise to cycle. Needs more Shiv generators, draw (like Acrobatics), and Accuracy; skip generic attacks.
### F14
- [event] Foundation deck focused on scaling physical damage with Phantom Blades and Blade Dance/Shivs. Prioritize card draw and block/defense to survive while Phantom Blades scales up damage. Look for strong mitigation to complement Beating Remnant.
- [map] Foundation phase: currently limping to the boss with low HP; prioritizing survival via the Unknown node to reach a Rest Site. Need to find a scaling damage source like Poison or Shivs soon, as the current deck lacks a win condition for the Act 1 boss.
### F15
- [card_reward] Committed shiv plan: use Phantom Blades to retain shivs and Fan of Knives for AoE damage output. Need Accuracy, extra energy/draw, and reliable block; avoid off-plan attacks.
### F16
- [rest_site] Committed to Shiv engine: use Blade Dance, Blade of Ink, and Fan of Knives to generate Shivs buffed by Phantom Blades. Play Phantom Blades early, then trigger the bonus damage each turn while picking off enemies. Needs block scaling and consistent draw to sustain the engine.

### Combat Decision Digest (10 combats)
F2 [monster] Seapunk (6R, HP 40->40, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize->Defend*2->Strike | dealt=9 taken=0
  R2[Seapunk: Atk(2x4=8)]: Strike*2->Survivor | dealt=12 taken=0
  R3[Seapunk: Buff, Defend]: Neutralize->Strike->Defend*2 | dealt=9 taken=0
  R4[Seapunk: Atk(12)]: Neutralize->Defend*2->Strike | dealt=2 taken=0
  R5[Seapunk: Atk(3x4=12)]: Strike->Defend->Survivor | dealt=6 taken=0
  R6[Seapunk: Buff, Defend]: Strike | dealt=0 taken=0

F3 [monster] multi:Toadpole+Toadpole (5R, HP 40->38, loss=2, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Neutralize->Strike->Survivor->Defend | dealt=0 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Sucker Punch->Defend*2 | dealt=0 taken=2
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Strike->Defend->Survivor | dealt=0 taken=0
  R4[Toadpole: Atk(7)]: Neutralize->Sucker Punch->Strike->Defend | dealt=17 taken=0
  R5[Toadpole: Buff]: Strike | dealt=0 taken=0

F4 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 38->37, loss=1, WIN)
  R1[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Sucker Punch->Defend->Poisoned Stab | dealt=8 taken=0
  R2[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Neutralize->Defend*2->Survivor | dealt=3 taken=0
  R3[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Defend*3 | dealt=0 taken=0
  R4[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Defend->Neutralize->Poisoned Stab->Sucker Punch | dealt=9 taken=1
  R5[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Neutralize->Strike->Poisoned Stab | dealt=6 taken=0

F5 [monster] Gremlin Merc (7R, HP 37->37, loss=0, WIN)
  R1[Gremlin Merc: Atk(7x2=14)]: Defend*3 | dealt=0 taken=0
  R2[Gremlin Merc: Atk(6x2=12), Debuff]: Neutralize->Blade Dance->Shiv*3->Defend->Survivor | dealt=15 taken=0
  R3[Gremlin Merc: Atk(8), Buff]: Neutralize->Sucker Punch->Defend*2 | dealt=8 taken=0
  R4[Gremlin Merc: Atk(6x2=12)]: Poisoned Stab->Defend->Survivor | dealt=4 taken=0
  R5[Gremlin Merc: Atk(8x2=16), Debuff]: Neutralize->Sucker Punch->Strike*2 | dealt=19 taken=0
  R6[Sneaky Gremlin: Atk(9)+Fat Gremlin: Escape]: Strike->Defend->Survivor | dealt=6 taken=0
  R7[Sneaky Gremlin: Atk(9)]: Strike | dealt=0 taken=0

F6 [monster] multi:Calcified Cultist+Seapunk (6R, HP 37->33, loss=4, WIN)
  R1[Calcified Cultist: Buff+Seapunk: Atk(11)]: Poisoned Stab->Defend*2 | dealt=6 taken=1
  R2[Calcified Cultist: Atk(9)+Seapunk: Atk(2x4=8)]: Blade Dance->Shiv*3->Sucker Punch->Defend | dealt=29 taken=0
  R3[Seapunk: Buff, Defend]: Neutralize->Sucker Punch->Survivor->Defend | dealt=11 taken=0
  R4[Seapunk: Atk(9)]: Defend*2->Poisoned Stab | dealt=0 taken=0
  R5[Seapunk: Atk(3x4=12)]: Blade of Ink->Defend->Shiv*2->Strike | dealt=18 taken=3
  R6[Seapunk: Buff, Defend]: Sucker Punch->Neutralize | dealt=8 taken=0

F9 [elite] Skulking Colony (6R, HP 27->17, loss=10, WIN)
  R1[Skulking Colony: Atk(12)]: Poisoned Stab->Defend->Survivor | dealt=6 taken=0
  R2[Skulking Colony: Atk(14), Defend]: Sucker Punch->Phantom Blades->Blade Dance | dealt=8 taken=10
  R3[Skulking Colony: Atk(9), Buff]: Neutralize+->Defend->Shiv->Strike*2->Shiv | dealt=15 taken=0
  R4[Skulking Colony: Atk(6x2=12)]: Shiv->Sucker Punch->Defend*2 | dealt=15 taken=0
  R5[Skulking Colony: Atk(10)]: Neutralize+->Strike->Defend*2 | dealt=10 taken=0
  R6[Skulking Colony: Atk(12), Defend]: Poisoned Stab->Strike | dealt=6 taken=0

F12 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (8R, HP 38->22, loss=16, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Blade Dance->Shiv*3->Defend*2 | dealt=0 taken=5
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Defend->Strike->Neutralize+->Blade of Ink->Shiv*2 | dealt=6 taken=0
  R3[Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(6)]: Phantom Blades->Sucker Punch->Survivor | dealt=8 taken=0
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(2x3=6)]: Neutralize+->Blade of Ink->Shiv->Defend->Shiv->Poisoned Stab | dealt=0 taken=1
  R5[Phantasmal Gardener: Atk(2x3=6)+Phantasmal Gardener: Atk(7)]: Defend*3 | dealt=0 taken=0
  R6[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)]: Neutralize+->Defend*2->Survivor | dealt=4 taken=0
  R7[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(2x3=6)]: Strike*2->Defend | dealt=0 taken=10
  R8[Phantasmal Gardener: Atk(11)+Phantasmal Gardener: Buff]: Strike->Blade of Ink->Shiv*2->Sucker Punch | dealt=15 taken=0

F13 [monster] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (4R, HP 22->22, loss=0, WIN)
  R1[Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Debuff]: Neutralize+->Blade of Ink->Shiv*2->Poisoned Stab->Strike | dealt=6 taken=0
  R2[Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(8)]: Blade Dance->Shiv*3->Strike->Sucker Punch | dealt=20 taken=0
  R3[Two-Tailed Rat: Summon]: Phantom Blades->Expertise->Strike | dealt=6 taken=0
  R4[Two-Tailed Rat: Debuff+Two-Tailed Rat: Atk(6)]: Sucker Punch->Blade of Ink->Shiv*2 | dealt=15 taken=0

F15 [monster] Haunted Ship (3R, HP 15->15, loss=0, WIN)
  R1[Haunted Ship: StatusCard(5)]: Phantom Blades->Blade of Ink->Shiv->Strike->Shiv | dealt=27 taken=0
  R2[Haunted Ship: Atk(7), Debuff]: Blade Dance->Shiv->Poisoned Stab->Survivor->Shiv*2 | dealt=27 taken=0
  R3[Haunted Ship: Atk(13)]: Neutralize+->Sucker Punch | dealt=3 taken=0

F17 [boss] Lagavulin Matriarch (13R, HP 36->0, loss=36, LOSS)
  R1[Lagavulin Matriarch: Sleep]: Fan of Knives | dealt=0 taken=0
  R2[Lagavulin Matriarch: Sleep]: none | dealt=0 taken=0
  R3[Lagavulin Matriarch: Sleep]: Phantom Blades->Blade of Ink | dealt=0 taken=0
  R4[Lagavulin Matriarch: Atk(19)]: Shiv->Sucker Punch->Survivor->Shiv*2 | dealt=33 taken=6
  R5[Lagavulin Matriarch: Atk(6x2=12)]: Leg Sweep->Blade Dance->Shiv*4 | dealt=25 taken=1
  R6[Lagavulin Matriarch: Atk(9), Defend]: Neutralize+->Poisoned Stab->Expertise->Shiv->Strike | dealt=29 taken=3
  R7[Lagavulin Matriarch: Debuff, Buff]: Neutralize+->Shiv->Poisoned Stab->Strike->Blade of Ink | dealt=17 taken=0
  R8[Lagavulin Matriarch: Atk(15)]: Shiv->Leg Sweep->Defend | dealt=13 taken=3
  R9[Lagavulin Matriarch: Atk(8x2=16)]: Shiv->Defend->Sucker Punch->Strike->Expertise->Survivor | dealt=23 taken=7
  R10[Lagavulin Matriarch: Atk(10), Defend]: Neutralize+->Poisoned Stab->Strike | dealt=10 taken=4
  R11[Lagavulin Matriarch: Debuff, Buff]: Blade of Ink->Shiv->Strike->Expertise | dealt=5 taken=0
  R12[Lagavulin Matriarch: Atk(17)]: Shiv->Neutralize+->Sucker Punch | dealt=15 taken=11
  R13[Lagavulin Matriarch: Atk(9x2=18)]: Leg Sweep->Survivor | dealt=0 taken=0

### Non-combat Decisions (77 decisions)
F1 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Precarious Shears offers excellent long-term deck consistency by removing 2 starter cards right away. Although losing 16 HP on Floor 1 is a steep cost, thinning the deck early makes it much easier to consistently draw the good cards we draft.
  strategic_note: Foundation phase: prioritize drafting high-damage attacks immediately since we are thinning out starter strikes.

F1 [card_select] select_deck_card (option_index=0) | source=llm
  HP 56->40 | Gold 99->99 | Deck 12->10
  deck_change: lost Strike x2
  reasoning: Strikes are the weakest cards in the starter deck, and Silent scales much better by replacing them with efficient attacks and synergy pieces. Removing two now means we must draft frontload damage immediately to survive early fights.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. Just removed 2 Strikes, need early damage urgently.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 40->40 | Gold 99->99 | Deck 10->10
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 40->40 | Gold 99->0 | Deck 10->10
  deck_change: no deck change
  reasoning: Starting with a monster to begin the recommended 3-monster opening. This secures early card rewards to define the deck's damage source before hitting events or elites.
  strategic_note: Foundation phase: prioritizing front-loaded damage and efficient block to survive the first three hallway fights. Seeking cards like Dagger Throw or Poison Stab to establish a core damage engine while keeping the deck lean for future synergy.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 99->113 | Deck 10->10
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 113->113 | Deck 10->10
  deck_change: no deck change
  reasoning: Claim potion: Potion of Binding

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 113->113 | Deck 10->10
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 40->40 | Gold 113->113 | Deck 10->11
  deck_change: picked Sucker Punch
  reasoning: In the early foundation phase of Act 1, prioritizing frontload damage is critical to survive elites. Sucker Punch adds 8 damage and applies Weak, which helps mitigate incoming damage while dealing much-needed attack damage.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F2 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 40->40 | Gold 113->113 | Deck 11->11
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 113->0 | Deck 11->11
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 113->120 | Deck 11->11
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 38->38 | Gold 120->120 | Deck 11->11
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 38->38 | Gold 120->120 | Deck 11->12
  deck_change: picked Poisoned Stab
  reasoning: The deck desperately needs damage for Act 1 Elites. Poisoned Stab provides decent frontload damage while applying poison, acting as a strong early-game damage card. Phantom Blades requires Shiv generators we don't have, and Hand Trick is defensive when we need offense.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F3 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 38->38 | Gold 120->120 | Deck 12->12
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 120->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 120->134 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 134->134 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 37->37 | Gold 134->134 | Deck 12->13
  deck_change: picked Blade Dance
  reasoning: Blade Dance provides 12 burst damage for 1 energy, which is excellent for early elites and hallways. It also serves as a premium engine piece if we find Shiv synergies like Accuracy or Fan of Knives.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a scaling engine. Take high-impact damage and cheap draw, keep options open for Shiv or Poison engines depending on upcoming drops.

F4 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 37->37 | Gold 134->134 | Deck 13->13
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 134->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 54->54 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Fire Potion

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 37->37 | Gold 54->54 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=deck_building,combat) | source=llm
  HP 37->37 | Gold 54->54 | Deck 13->14
  deck_change: picked Blade of Ink
  reasoning: Blade of Ink is a Rare card that strongly supports a Shiv-based damage plan. We already have Blade Dance, and generating more Shivs while potentially gaining Strength or bonus damage scales our multi-hit attacks exceptionally well for boss DPS races like Lagavulin.
  strategic_note: Foundation plan: transition into a committed Shiv engine. Prioritize Accuracy, Phantom Blades, and Afterimage. Take draw (Acrobatics) to cycle to Shiv generators faster, and skip generic non-Shiv attacks to keep the deck lean.

F5 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 37->37 | Gold 54->54 | Deck 14->14
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 37->37 | Gold 54->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Unknown

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 54->68 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 68->68 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 68->68 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 33->33 | Gold 68->68 | Deck 14->15
  deck_change: picked Phantom Blades
  reasoning: We already have Blade Dance and Blade of Ink. Phantom Blades provides excellent damage scaling (+9 per turn when playing a Shiv) and retain flexibility, serving as a core engine piece for a Shiv-focused build.
  strategic_note: Committed to Shivs: retain shivs for guaranteed +9 damage procs each turn. Prioritize draw, efficient block, and maybe one more Shiv generator. Avoid expensive off-plan attacks.

F6 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 33->33 | Gold 68->68 | Deck 15->15
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F6 [map] choose_map_node (option_index=0) | source=llm
  HP 33->33 | Gold 68->68 | Deck 15->15
  deck_change: no deck change
  reasoning: With 33/70 HP and an Elite fight approaching on Floor 9, a Rest Site is essential. Following the 'Rest -> Elite -> Rest' strategy is the safest way to ensure I don't die before reaching the boss. This node allows me to either heal to a safe threshold or potentially Smith if the next event (Floor 8) goes well, though healing is likely given the Silent's early fragility.
  strategic_note: Foundation phase: focusing on securing high-impact damage and defensive staples. Current priority is stabilizing HP via rest sites to survive the upcoming Elite while looking for a more definitive damage engine like Poison or Shivs.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=8, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 68->68 | Deck 15->15
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: HP is at 33 which is borderline for an upcoming Elite on F9, but upgrading Neutralize to provide 2 turns of Weak is crucial for surviving Elite fights like Lagavulin and Gremlin Nob by mitigating large hits. We will play aggressively and rely on weak application for defense.
  strategic_note: Foundation Shiv/Damage deck: generate Shivs and hold them with Phantom Blades to maximize extra damage output. Needs card draw and an energy relic or reliable block engine.

F7 [rest_site] proceed | source=auto
  HP 33->33 | Gold 68->68 | Deck 15->15
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 68->68 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Unknown

F8 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing) | source=llm
  HP 33->27 | Gold 68->110 | Deck 15->15
  deck_change: no deck change
  reasoning: Taking a small HP loss for gold is the safest and most consistent option. Adding a Clumsy curse to our deck could brick a crucial hand in an upcoming elite fight, which would likely cost more than 6 HP anyway.
  strategic_note: Foundation: Physical damage with Phantom Blades and shivs/Neutralize. Play Phantom Blades early and aggressively use shivs for damage. Still looking for better block options or a reliable AoE tool for Act 2.

F8 [event] choose_event_option (option_index=0) | source=auto
  HP 27->27 | Gold 110->110 | Deck 15->15
  deck_change: no deck change
  reasoning: Only option: Proceed

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 27->27 | Gold 110->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Elite

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 17->17 | Gold 110->139 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 29 Gold

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 17->17 | Gold 139->139 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim potion: Ship in a Bottle

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 17->17 | Gold 139->139 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim relic: Beating Remnant

F9 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 17->17 | Gold 139->139 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F9 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 17->17 | Gold 139->139 | Deck 15->16
  deck_change: picked Expertise
  reasoning: Expertise is a phenomenal draw engine for Shiv decks, as generating and playing 0-cost Shivs quickly empties the hand. Backstab is actively detrimental against the upcoming Lagavulin Matriarch boss because it forces a forced attack into our opening hand during the crucial 3-turn sleep phase setup window.
  strategic_note: Committed Shiv plan: prioritize Shiv generators (Blade Dance, Cloak and Dagger) and payoffs (Accuracy, Finisher), using Expertise to refill hand after playing out cheap cards. Needs scaling damage and block; skip high-cost cards that clunk up Expertise.

F9 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 17->17 | Gold 139->139 | Deck 16->16
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F9 [map] choose_map_node (option_index=1) | source=llm
  HP 17->17 | Gold 139->139 | Deck 16->16
  deck_change: no deck change
  reasoning: Moving to the recommended treasure node as per the planned route. The HP is currently low (17/70) following an Elite encounter, so securing the relic and then proceeding toward the rest site is essential for survival.
  strategic_note: Foundation phase: currently prioritizing HP stabilization via upcoming rest sites while seeking a core engine like Poison or Shivs to provide scaling damage for the Act 1 boss.

F10 [treasure] open_chest | source=random
  HP 17->17 | Gold 139->176 | Deck 16->16
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 17->17 | Gold 176->176 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim: Amethyst Aubergine

F10 [treasure] proceed | source=random
  HP 17->17 | Gold 176->176 | Deck 16->16
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 17->17 | Gold 176->176 | Deck 16->16
  deck_change: no deck change
  reasoning: With only 17 HP and a monster fight followed by a Rest Site, taking the Rest Site immediately at index 1 is the safer path to ensure survival. The route recommendation for a monster at c3,r10 is too risky given the current health total, especially before the Act 1 Boss and subsequent shops.
  strategic_note: Foundation phase: focusing on stabilizing HP via rest sites to survive the upcoming encounters while looking for a more definitive damage engine like Poison or Shivs.

F11 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 17->38 | Gold 176->176 | Deck 16->16
  deck_change: no deck change
  reasoning: HP is critically low at 17, and the very next floor is an Elite fight. Without healing, we are extremely likely to die.
  strategic_note: Foundation Shiv/Damage deck: generate Shivs and hold them with Phantom Blades to maximize extra damage output. Needs card draw and an energy relic or reliable block engine.

F11 [rest_site] proceed | source=auto
  HP 38->38 | Gold 176->176 | Deck 16->16
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=auto
  HP 38->38 | Gold 176->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Elite

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 176->206 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 206->221 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 221->221 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Energy Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 221->221 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim relic: Orichalcum

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 221->221 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 22->22 | Gold 221->221 | Deck 16->17
  deck_change: picked Leg Sweep
  reasoning: Leg Sweep provides premium defense and applies 2 Weak, which is essential for surviving the heavy multi-attacks from Lagavulin Matriarch and Act 2 elites. Even on 3 energy, playing Leg Sweep + a 1-cost attack/setup card is a solid turn.
  strategic_note: Committed shiv plan: scale Shivs with Phantom Blades, keep generators, and block efficiently with Weak. Need more Shiv generation and draw (Acrobatics/Backflip). Skip generic attacks.

F12 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 22->22 | Gold 221->221 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 22->22 | Gold 221->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 221->230 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 230->245 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 22->22 | Gold 245->245 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F13 [card_reward] choose_reward_alternative (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 22->22 | Gold 245->245 | Deck 17->17
  deck_change: no deck change
  reasoning: The deck has decent damage through the Phantom Blades + Shiv synergy. Adding more attack cards that don't scale or generate Shivs clutters the deck and makes it harder to cycle into our core engine pieces (Phantom Blades, Blade Dance, Blade of Ink) during the strict DPS phase of the upcoming Lagavulin Matriarch fight. We want to keep the deck lean for Expertise and fast setup.
  strategic_note: Committed Shiv plan: setup Phantom Blades early, then use Blade Dance and Blade of Ink to burst enemies down. Use Expertise to cycle. Needs more Shiv generators, draw (like Acrobatics), and Accuracy; skip generic attacks.

F13 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 22->22 | Gold 245->245 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 22->22 | Gold 245->245 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Unknown

F14 [event] choose_event_option (option_index=1) | source=llm
  HP 22->15 | Gold 245->348 | Deck 17->17
  deck_change: no deck change
  reasoning: Taking 7 damage for 111 gold is an extremely efficient trade, giving a massive economic boost for the Act 2 shop. While HP is low (22 -> 15), a campfire should be right before the Act 1 Boss to heal, and Beating Remnant prevents massive burst damage.
  strategic_note: Foundation deck focused on scaling physical damage with Phantom Blades and Blade Dance/Shivs. Prioritize card draw and block/defense to survive while Phantom Blades scales up damage. Look for strong mitigation to complement Beating Remnant.

F14 [event] choose_event_option (option_index=0) | source=auto
  HP 15->15 | Gold 348->348 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 15->15 | Gold 348->0 | Deck 17->17
  deck_change: no deck change
  reasoning: With only 15 HP, an Elite fight is suicidal regardless of the potential rewards. The Unknown node is the only safe path to the Rest Site before the boss. I have 348 gold, so if the Unknown is a Shop, I can significantly power up; if it's an Event or Monster, I have a better chance of survival than against an Elite.
  strategic_note: Foundation phase: currently limping to the boss with low HP; prioritizing survival via the Unknown node to reach a Rest Site. Need to find a scaling damage source like Poison or Shivs soon, as the current deck lacks a win condition for the Act 1 boss.

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 348->362 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 362->377 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 377->377 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 15->15 | Gold 377->377 | Deck 17->18
  deck_change: picked Fan of Knives
  reasoning: Fan of Knives is a premium engine piece that transforms our Shiv damage into AoE, which will be vital for Act 2 hallways. It synergizes perfectly with Phantom Blades, especially in the upcoming boss fight where we can play it during the 3-turn sleep phase and retain the 4 generated Shivs for massive burst when the boss wakes up.
  strategic_note: Committed shiv plan: use Phantom Blades to retain shivs and Fan of Knives for AoE damage output. Need Accuracy, extra energy/draw, and reliable block; avoid off-plan attacks.

F15 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 15->15 | Gold 377->377 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 15->15 | Gold 377->377 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 15->36 | Gold 377->377 | Deck 18->18
  deck_change: no deck change
  reasoning: With only 15 HP before the Act 1 Boss, a single big hit could be lethal. Healing restores 21 HP, putting us at 36 HP, which provides a much better buffer to survive the boss fight.
  strategic_note: Committed to Shiv engine: use Blade Dance, Blade of Ink, and Fan of Knives to generate Shivs buffed by Phantom Blades. Play Phantom Blades early, then trigger the bonus damage each turn while picking off enemies. Needs block scaling and consistent draw to sustain the engine.

F16 [rest_site] proceed | source=auto
  HP 36->36 | Gold 377->377 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 377->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Boss

## Selected Replay Package (5 replays)
[Selected: elite] Skulking Colony (F9, elite)
Historical: loss=10 vs historical avg=15.6+/-12.8 (z=-0.4, TYPICAL, n=26)
## Combat Replay: vs Skulking Colony (Floor 9, elite)
Relics: Ring of the Snake, Precarious Shears
Deck (15): Defend x5, Strike x3, Blade Dance, Blade of Ink, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Skulking Colony HP=70/70

### Round 1
Agent plan (hypothesis): Save Fire Potion for later if we miss the damage cap or need emergency lethal.
Intent: Skulking Colony: Attack(12)
  Dexterity Potion
    +Dexterity(2)
  Blade of Ink
  turn_end

### Round 2
Agent plan (hypothesis): Hold the retained Shivs to play exactly one at the start of each turn to get the +9 damage bonus, using them to efficiently hit the 20 damage cap every round.
Agent plan (hypothesis): Play exactly one Shiv per turn to get the +9 damage bonus. Prioritize blocking.
Intent: Skulking Colony: Attack(14), Defend
  turn_end

### Round 3
Agent plan (hypothesis): Hold Retained Shivs to proc the first-Shiv bonus each turn. Next turn it uses a heavy multi-attack, so prioritize drawing and playing full block.
Agent plan (hypothesis): Hold the remaining Shiv for next turn's Phantom Blades bonus. Expect a heavy multi-attack next turn.
Intent: Skulking Colony: Attack(9), Buff
  turn_end

### Round 4
Agent plan (hypothesis): Enemy HP will be 16 next turn. Finish it off. Fire Potion can guarantee the kill if needed.
Intent: Skulking Colony: Attack(6x2=12)
  turn_end

### Round 5
Agent plan (hypothesis): Finish the enemy next turn. Do not use Fire Potion unless absolutely necessary.
Intent: Skulking Colony: Attack(10)
  turn_end

### Round 6
Intent: Skulking Colony: Attack(12), Defend
  cards: Poisoned Stab, Strike, dealt=6, taken=0
## Combat Analytics: Skulking Colony (WIN - 6 rounds)

Enemy power timeline:
  Hardened Shell: R1:15 -> R2:15 -> R3:15 -> R4:15 -> R5:15 -> R6:15
  Poison: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:2

Unattributed damage (power/passive effects): 60
  Per round: R1:6 R2:8 R3:15 R4:15 R5:10 R6:6
Comparator (recent same-enemy comparator):
## Combat Replay: vs Skulking Colony (Floor 12, elite)
Relics: Ring of the Snake, Large Capsule, Shovel, Parrying Shield, The Boot, Pear, Bowler Hat
Deck (20): Defend x6, Strike x6, Accelerant, Acrobatics, Backflip, Bouncing Flask, Deadly Poison, Neutralize, Ricochet, Survivor
Enemies: Skulking Colony HP=70/70

### Round 1
Intent: Skulking Colony: Attack(12)
  Regen Potion
    +Regen(5)
  Strike
  turn_end

### Round 2
Intent: Skulking Colony: Attack(14), Defend
  turn_end

### Round 3
Intent: Skulking Colony: Attack(9), Buff
  Strike
  turn_end

### Round 4
Intent: Skulking Colony: Attack(9x2=18)
  Bouncing Flask
  Strike
  turn_end

### Round 5
Intent: Skulking Colony: Attack(14)
  turn_end
## Combat Analytics: Skulking Colony (WIN - 5 rounds)

Enemy power timeline:
  Hardened Shell: R1:15 -> R2:15 -> R3:15 -> R4:15 -> R5:15
  Poison: R1:- -> R2:- -> R3:- -> R4:7 -> R5:5
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2

Unattributed damage (power/passive effects): 26
  Per round: R1:5 R2:15 R5:6

[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F12, elite)
Historical: loss=16 vs historical avg=19.7+/-17.1 (z=-0.2, TYPICAL, n=11)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 12, elite)
Relics: Ring of the Snake, Precarious Shears, Beating Remnant, Amethyst Aubergine
Deck (16): Defend x5, Strike x3, Blade Dance, Blade of Ink, Expertise, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=28/28

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Fire Potion -> Phantasmal Gardener[2]
  turn_end

### Round 2
Agent plan (hypothesis): Enemy 2 should die this turn; enemy 3 will be Weakened. Next draw is very likely Phantom Blades from the 4-card draw pile, with extra potion block helping a setup turn.
Agent plan (hypothesis): Continue focusing Enemy 2 to eliminate the strength threat.
Agent plan (hypothesis): Enemy 2 weakened. Next turn we draw Phantom Blades hopefully.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Ship in a Bottle
    block +10 | +Block Next Turn(10)
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(6)
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): Enemy 2 is dead, Enemy 0 is weakened and poisoned. Keep focus on survival and clearing the remaining attackers.
Agent plan (hypothesis): Enemy 2 is dead, Enemy 0 is taking poison.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(2x3=6)
  turn_end

### Round 5
Agent plan (hypothesis): We reshuffle next turn and will draw a fresh hand.
Intent: Phantasmal Gardener: Attack(2x3=6), Phantasmal Gardener: Attack(7)
  turn_end

### Round 6
Agent plan (hypothesis): Continue focusing enemies down
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(2x3=6)
  turn_end

### Round 8
Agent plan (hypothesis): Fight is over.
Intent: Phantasmal Gardener: Attack(11), Phantasmal Gardener: Buff
  cards: Strike, Blade of Ink, Shiv, Shiv, Sucker Punch, dealt=15, taken=0
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 8 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:1 -> R7:- -> R8:-
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:- -> R7:- -> R8:-
  Skittish[3]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength: R1:- -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Strength[0]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:2 -> R6:2 -> R7:4 -> R8:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:2
  Strength[2]: R1:- -> R2:- -> R3:2 -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:2 -> R6:1 -> R7:1 -> R8:-
  Weak[0]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
  Weak[2]: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-

Unattributed damage (power/passive effects): 33
  Per round: R2:6 R3:8 R6:4 R8:15
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 9, elite)
Relics: Ring of the Snake, Precarious Shears
Deck (15): Strike x4, Defend x3, Dagger Spray, Defend+, Hidden Daggers, Leading Strike, Neutralize, Piercing Wail, Predator, Survivor
Enemies: Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=27/27, Phantasmal Gardener HP=26/26

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Fire Potion -> Phantasmal Gardener[3]
    enemy_deltas: Phantasmal Gardener: hp -20
  Strike
  Defend
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Dagger Spray
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff
  turn_end

### Round 4
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7)
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  turn_end

### Round 6
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(3x3=9)
  turn_end
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (LOSS - 7 rounds)
Death cause: Killed by damage. HP 5 -> 0, took 0 damage.

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:- -> R7:-
  Skittish[3]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:4
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:- -> R7:-

Unattributed damage (power/passive effects): 21
  Per round: R1:4 R2:4 R3:6 R4:3 R7:4

[Selected: run_combat] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (F13, monster)
Historical: loss=0 vs historical avg=6.9+/-6.5 (z=-1.1, BETTER_THAN_USUAL, n=37)
## Combat Replay: vs multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (Floor 13, monster)
Relics: Ring of the Snake, Precarious Shears, Beating Remnant, Amethyst Aubergine, Orichalcum
Deck (17): Defend x5, Strike x3, Blade Dance, Blade of Ink, Expertise, Leg Sweep, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Two-Tailed Rat HP=18/18, Two-Tailed Rat HP=21/21, Two-Tailed Rat HP=20/20

### Round 1
Agent plan (hypothesis): Swarm encounter: focus down rats one by one.
Intent: Two-Tailed Rat: Attack(8), Two-Tailed Rat: Attack(6), Two-Tailed Rat: Debuff
  turn_end
    block +6

### Round 2
Intent: Two-Tailed Rat: Attack(8), Two-Tailed Rat: Attack(8)
  turn_end
    block +6

### Round 3
Agent plan (hypothesis): If we draw Blade Dance, it's a guaranteed kill. Otherwise, consider using the Energy Potion to play Strike + drawn attacks.
Agent plan (hypothesis): Kill the original rat next turn before the summon gets out of hand.
Intent: Two-Tailed Rat: Summon
  turn_end
    block +6

### Round 4
Agent plan (hypothesis): Combat over
Intent: Two-Tailed Rat: Debuff, Two-Tailed Rat: Attack(6)
  cards: Sucker Punch, Blade of Ink, Shiv, Shiv, dealt=15, taken=0
## Combat Analytics: multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (WIN - 4 rounds)

Unattributed damage (power/passive effects): 47
  Per round: R1:6 R2:20 R3:6 R4:15
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (Floor 8, monster)
Relics: Ring of the Snake, Large Capsule, Shovel, Parrying Shield, The Boot
Deck (19): Defend x6, Strike x6, Accelerant, Acrobatics, Backflip, Bouncing Flask, Deadly Poison, Neutralize, Survivor
Enemies: Two-Tailed Rat HP=17/17, Two-Tailed Rat HP=19/19, Two-Tailed Rat HP=18/18

### Round 1
Intent: Two-Tailed Rat: Debuff, Two-Tailed Rat: Attack(8), Two-Tailed Rat: Attack(6)
  turn_end

### Round 2
Intent: Two-Tailed Rat: Attack(6), Two-Tailed Rat: Attack(6), Two-Tailed Rat: Attack(8)
  turn_end

### Round 3
Intent: Two-Tailed Rat: Summon, Two-Tailed Rat: Debuff
  turn_end

### Round 4
Intent: Two-Tailed Rat: Summon
  turn_end

### Round 5
Intent: Two-Tailed Rat: Attack(6), Two-Tailed Rat: Attack(6)
  turn_end

### Round 6
Intent: Two-Tailed Rat: Attack(8)
  Acrobatics
  turn_end
## Combat Analytics: multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (WIN - 6 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:3

Unattributed damage (power/passive effects): 22
  Per round: R2:5 R4:11 R6:6

[Selected: run_combat] Haunted Ship (F15, monster)
Historical: loss=0 vs historical avg=9.3+/-7.4 (z=-1.2, BETTER_THAN_USUAL, n=30)
## Combat Replay: vs Haunted Ship (Floor 15, monster)
Relics: Ring of the Snake, Precarious Shears, Beating Remnant, Amethyst Aubergine, Orichalcum
Deck (17): Defend x5, Strike x3, Blade Dance, Blade of Ink, Expertise, Leg Sweep, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Haunted Ship HP=63/63

### Round 1
Agent plan (hypothesis): Phantom Blades is active; Shivs now retain and the first one each turn deals +9 damage.
Agent plan (hypothesis): We retained a Shiv. Keep looking for burst combos.
Agent plan (hypothesis): We will have full energy next turn to deal with the incoming attacks.
Intent: Haunted Ship: StatusCard(5)
  turn_end
    block +6

### Round 2
Agent plan (hypothesis): Retaining Shivs with Phantom Blades allows splitting the +9 damage bonus across multiple turns.
Intent: Haunted Ship: Attack(7), Debuff
  Strike
  turn_end

### Round 3
Agent plan (hypothesis): Clean kill achieved using available damage.
Intent: Haunted Ship: Attack(13)
  cards: Neutralize+, Sucker Punch, dealt=3, taken=0
## Combat Analytics: Haunted Ship (WIN - 3 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:2
  Weak: R1:- -> R2:1 -> R3:-

Unattributed damage (power/passive effects): 57
  Per round: R1:27 R2:27 R3:3
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Haunted Ship (Floor 5, monster)
Relics: Ring of the Snake, Leafy Poultice
Deck (15): Defend x4, Strike x4, Accelerant, Anticipate, Dash, Deadly Poison, Neutralize, Phantom Blades, Survivor
Enemies: Haunted Ship HP=63/63

### Round 1
Intent: Haunted Ship: StatusCard(5)
  turn_end

### Round 2
Intent: Haunted Ship: Attack(10), Debuff
  turn_end

### Round 3
Intent: Haunted Ship: Attack(4x3=12)
  Skill Potion
  Dodge and Roll
  turn_end
    exhausted: Dazed [0费]：Unplayable. Ethereal.

### Round 4
Intent: Haunted Ship: Attack(10), Debuff
  Dazed
  turn_end

### Round 5
Intent: Haunted Ship: Attack(4x3=12)
  turn_end

### Round 6
Intent: Haunted Ship: Attack(10), Debuff
  cards: Neutralize, dealt=0, taken=0
## Combat Analytics: Haunted Ship (WIN - 6 rounds)

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:- -> R4:3 -> R5:1 -> R6:-

Unattributed damage (power/passive effects): 47
  Per round: R1:15 R2:10 R3:4 R4:10 R5:8

[Selected: boss, death] Lagavulin Matriarch (F17, boss)
Historical: loss=36 vs historical avg=30.5+/-19.8 (z=0.3, TYPICAL, n=33)
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Precarious Shears, Beating Remnant, Amethyst Aubergine, Orichalcum
Deck (18): Defend x5, Strike x3, Blade Dance, Blade of Ink, Expertise, Fan of Knives, Leg Sweep, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Intent: Lagavulin Matriarch: Sleep
  turn_end
    block +6

### Round 2
Intent: Lagavulin Matriarch: Sleep
  turn_end
    block +6

### Round 3
Intent: Lagavulin Matriarch: Sleep
  turn_end
    block +6

### Round 4
Intent: Lagavulin Matriarch: Attack(19)
  Strike
  turn_end

### Round 5
Intent: Lagavulin Matriarch: Attack(6x2=12)
  turn_end

### Round 6
Intent: Lagavulin Matriarch: Attack(9), Defend
  turn_end
    block +6

### Round 7
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
    block +6

### Round 8
Intent: Lagavulin Matriarch: Attack(15)
  turn_end

### Round 9
Intent: Lagavulin Matriarch: Attack(8x2=16)
  Energy Potion
    energy +2
  Strike
  turn_end

### Round 10
Intent: Lagavulin Matriarch: Attack(10), Defend
  turn_end
    block +6

### Round 11
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
    block +6

### Round 12
Intent: Lagavulin Matriarch: Attack(17)
  turn_end
    block +6

### Round 13
Intent: Lagavulin Matriarch: Attack(9x2=18)
  Strike
  turn_end
## Combat Analytics: Lagavulin Matriarch (LOSS - 13 rounds)
Death cause: Killed by damage. HP 1 -> 0, took 0 damage.

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:-
  Plating: R1:12 -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:2 -> R8:4 -> R9:3 -> R10:2 -> R11:4 -> R12:3 -> R13:2
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2 -> R9:2 -> R10:2 -> R11:2 -> R12:4 -> R13:4
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:7 -> R10:8 -> R11:9 -> R12:9 -> R13:12

Unattributed damage (power/passive effects): 170
  Per round: R4:33 R5:25 R6:29 R7:17 R8:13 R9:23 R10:10 R11:5 R12:15
Comparator (recent same-enemy comparator):
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Neow's Bones, Hefty Tablet, Precarious Shears, Book of Five Rings, Mango
Deck (22): Defend x5, Strike x4, Accuracy, Backflip, Blade of Ink, Cloak and Dagger, Clumsy, Dagger Throw, Expose, Leading Strike, Leg Sweep, Neutralize+, Precise Cut, Ricochet, Survivor
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Intent: Lagavulin Matriarch: Sleep
  turn_end

### Round 2
Intent: Lagavulin Matriarch: Sleep
  turn_end
    exhausted: Clumsy [0费]：Unplayable. Ethereal.

### Round 3
Intent: Lagavulin Matriarch: Sleep
  turn_end

### Round 4
Intent: Lagavulin Matriarch: Attack(14)
  Ricochet
  Strike
  turn_end

### Round 5
Intent: Lagavulin Matriarch: Attack(6x2=12)
  turn_end

### Round 6
Intent: Lagavulin Matriarch: Attack(9), Defend
  turn_end

### Round 7
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end

### Round 8
Intent: Lagavulin Matriarch: Attack(15)
  turn_end

### Round 9
Intent: Lagavulin Matriarch: Attack(8x2=16)
  Ricochet
  Strike
  turn_end

### Round 10
Intent: Lagavulin Matriarch: Attack(10), Defend
  Energy Potion
    energy +2
## Combat Analytics: Lagavulin Matriarch (WIN - 10 rounds)

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Plating: R1:12 -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2 -> R9:2 -> R10:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:-
  Weak: R1:- -> R2:- -> R3:- -> R4:3 -> R5:2 -> R6:3 -> R7:4 -> R8:5 -> R9:4 -> R10:5

Unattributed damage (power/passive effects): 189
  Per round: R3:32 R4:19 R5:30 R6:40 R8:19 R9:25 R10:24

## Existing Combat Guides (relevant enemies)
[Guide: Gremlin Merc] WR=92%, 37 episodes, confidence=0.90, v28
  - **Prioritize Block Over Greed:** The Merc routinely hits for 12-14 damage (6x2 or 7x2). High-loss rounds consistently show players taking 9+ damage by aggressively spamming low-impact attacks (Strikes, Shivs) to race the Thievery mechanic. Always block its multi-hits first.
- **Mitigate the Turn 4 Spike:** On Round 4, the Merc gains +2 Strength, turning its multi-hits into massive threats. Retain `Neutralize` (Weak), `Piercing Wail`, and high-value block cards specifically for this turn.
- **Burst Early or Wait it Out:** The cleanest fights (0 damage taken) use heavy upfront burst (`Assassinate`, `Predator+`, `Fan of Knives`) to kill the Merc in 2-3 rounds before it can scale. 
- **Exploit the Escape Phase:** If you lack early burst, focus entirely on survival. By Turn 5, the Merc drops its buffs and transitions to an escape phase (`Heist`), becoming completely passive and allowing you to safely finish it off.
[Guide: Haunted Ship] WR=93%, 30 episodes, confidence=0.90, v22
  - **Burst for Clean Kills:** Rapid 3-round finishes consistently yield the cleanest fights (0 HP lost). Utilize efficient burst combinations (e.g., Blade Dance, Pinpoint, Flechettes) to burst the Ship down before its dangerous later cycles begin.
- **Exploit Utility Turns:** The Ship frequently spends turns applying debuffs, inserting Status cards, or prepping RAMMING SPEED. Capitalize on these zero-pressure windows to safely unleash your heaviest damage or establish Poison scaling.
- **Respect the Multi-Hit:** When the Ship readies its 6x3 multi-hit or 10-damage single hit, defensive sequencing is mandatory. Apply Weak (Neutralize) early and secure full block before spending any remaining energy on cheap attacks like Shivs or Strikes. High HP loss occurs strictly when over-aggressing during these attack windows.
[Guide: Lagavulin Matriarch] WR=56%, 34 episodes, confidence=0.90, v33
  - **Maximize the Sleep Phase:** Use the first 3 turns entirely for setting up Powers, filtering your deck, and retaining crucial cards. Do not deal unblocked damage to her HP, as this immediately breaks her Asleep status and forces her to attack.
- **Race Against the Siphon:** Once she awakens, the fight becomes a strict DPS race. Every 4th turn she is awake, she will permanently siphon your stats (-2 Str/Dex) and gain +2 Strength. You must finish the fight before compounding Dexterity debuffs cripple your ability to block.
- **Mitigate Multi-Hits:** Her second awake turn is always a multi-hit attack (base 9x2). Because this scales twice as fast from her Strength buffs, apply Weak strictly on these turns to maximize your damage mitigation.
- **Time Your Burst:** Her Plating disappears as soon as she wakes up. Unload all your accumulated damage, Shivs, and Poison starting on turn 4 (or the turn you intentionally wake her) to capitalize on her 0 Block.
[Guide: Seapunk] WR=98%, 66 episodes, confidence=0.90, v39
  - **Prioritize Block Over Strikes:** High HP loss (8.9 avg) occurs when over-committing to Strikes during Seapunk's 11-damage or 2x4 attack turns. Always prioritize full-blocking with Defends and Survivor; your damage should come from passive scaling or burst during safe windows.
- **Timed Neutralization:** Use Neutralize specifically to mitigate multi-hits and heavy 11-damage strikes. This brings incoming damage into a range where basic Defends can fully negate the hit, preventing chip damage.
- **Exploit Non-Attack Windows:** Seapunk frequently uses turns to Buff or Defend. These are your only opportunities to play setup cards like Afterimage or high-cost Poison like Bouncing Flask without taking damage.
- **The Turn 4 Deadline:** Seapunk scales Strength on Turn 4 (and again on Turn 7). Aim for a burst finish by Round 3 using Blade Dance or Assassinate. If the fight persists, transition into a pure defensive posture while Poison or existing Shiv scaling finishes the enemy.
- **Manage Sea Kick:** Watch for the SEA_KICK_MOVE; failure to block effectively during this pattern is a primary driver of high-damage rounds and losses.
[Guide: Skulking Colony] WR=74%, 27 episodes, confidence=0.90, v21
  - **Observe the Damage Cap:** Hardened Shell limits HP loss to 20 per turn. Once you reach this threshold, stop attacking and focus entirely on defense, setup, or applying debuffs like Poison and Weak.
- **Prepare for R1:** Statistics show a high loss rate on Round 1. Prioritize immediate block to survive the opening 11-12 damage hit.
- **The 4-Round Rhythm:** The enemy buffs its Strength on R3 and R7. This is always followed by a multi-attack on R4 and R8. Save your highest value mitigation (Weakness or large block) specifically for these multi-hit windows.
- **Minimum Duration:** Because of the HP cap and 70 total HP, the fight cannot end before Round 4. Plan your resources for a medium-length engagement; do not attempt to 'burst' the enemy down in the first two turns.
[Guide: multi:Calcified Cultist+Seapunk] WR=100%, 5 episodes, confidence=0.90, v3
  - **Prioritize the Cultist:** The Calcified Cultist gains Ritual(2) on Round 1 and attacks every turn afterward, gaining 2 Strength per round. This creates an immediate damage check; focus on eliminating it quickly.
- **Track Seapunk's 3-Turn Cycle:** The Seapunk predictably loops a heavy single attack, a 4-hit multi-attack, and a defensive buff turn that grants it Block and 1 Strength.
- **Anticipate Synchronized Attacks:** Rounds 1 and 2 feature attacks from both enemies. Round 2 is particularly dangerous, combining the Cultist's first strike with the Seapunk's multi-attack.
- **Exploit Multi-Attack Weakness:** Apply Weak to the Seapunk during its multi-attack turns (Rounds 2, 5, 8). Because the damage reduction applies independently to each of the 4 hits, Weak drastically minimizes its threat even after it scales its Strength.
[Guide: multi:Corpse Slug+Corpse Slug] WR=100%, 71 episodes, confidence=0.90, v50
  - **Control the Kill:** The defining mechanic is their enrage. Killing one slug immediately grants the survivor +4 Strength. Whittle both down evenly to secure a simultaneous kill, or ensure you have immediate lethal on the remaining slug.
- **Leverage AoE:** Multi-target attacks like Dagger Spray, Omnislice, and Ricochet excel at dealing even damage across both targets, naturally setting up a double-kill to bypass the dangerous solo phase.
- **Respect the Enrage:** High-damage rounds heavily correlate with playing aggressive, Strike-heavy turns against a solo, enraged slug. If forced into this phase without lethal, stop attacking and pivot entirely to Survivor, Defends, and Weak to survive the +4 Strength GLOMP attacks.
- **Mitigate the Duo Phase:** While both are alive, their base attacks are weak (3x2 or 8 damage). Target Neutralize on the 3x2 multi-hit intent to halve its damage, making it trivial to full-block while setting up your kills.
[Guide: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener] WR=92%, 12 episodes, confidence=0.90, v10
  - **The Staggered Cycle:** Each Gardener follows a strict 4-turn loop: Attack(5) -> Attack(7) -> Attack(1x3) -> Buff (+2 Strength). They spawn at different steps in this cycle, so exactly one Gardener will buff each turn while three attack.
- **Skittish Clarification:** Disregard previous guides claiming Skittish deals passive damage. The `Skittish` power strictly grants the enemy Block the first time they are hit each turn. Lead with a heavy attack to punch through this Block efficiently.
- **Targeting Priority:** Burst down a single Gardener at a time to permanently remove incoming attacks. Prioritize eliminating or applying Weakness to Gardeners that are about to use their multi-hit Attack(1x3), as this attack scales aggressively (a Gardener with +4 Strength hits for 5x3).
- **Damage Race:** Because their damage floor permanently rises every 4 turns, you must aggressively reduce their numbers. Spreading damage is a guaranteed path to being overwhelmed.
[Guide: multi:Toadpole+Toadpole] WR=99%, 73 episodes, confidence=0.90, v45
  - **Round 1 Burst:** Both Toadpoles start without Thorns. Unleash your highest damage physical attacks immediately (Neutralize, Slice, etc.) to focus-fire one target, securing an early advantage before defenses go up.
- **Thorns Management:** Toadpoles gain Thorns (2) on Round 2, which typically lasts through Round 3 (and reapplies around Round 5). Do not play Shivs or low-damage attacks into Thorns, as recoil damage is the primary driver of high HP loss.
- **Defensive Pivot (Rounds 2-3):** During Thorns cycles, prioritize survival. Apply Weakness (Neutralize) to the Toadpole intending the 3x3 multi-attack, and use Survivor/Defend to fully block incoming damage.
- **Safe Windows & Poison:** Wait for Thorns to expire on Round 4 to resume physical aggression and dump Shivs. Alternatively, use Poison (which bypasses Thorns entirely) to whittle them down safely while you focus strictly on blocking.
[Guide: multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat] WR=97%, 37 episodes, confidence=0.90, v26
  - **Prevent the Swarm Cascade:** The defining threat of this encounter is the rats' ability to use "Call for Backup" (starting around Round 3). They can summon new rats even if the initial three are alive, growing the swarm to 4 or 5 enemies. You must aggressively focus down targets one by one to keep their numbers in check.
- **Anticipate Frail:** Rats frequently use "Screech" to apply Frail. Expect your block cards to be 25% less effective. Relying solely on basic block cards will lead to heavy chip damage during synchronized attack turns.
- **Capitalize on Round 1:** The initial turn usually features staggered intents (one 8-damage attack, one 6-damage attack, and one debuff). Use this relatively low-pressure window to quickly eliminate a rat or deploy crucial setup cards before the summoning begins.
- **Watch for Spikes:** The fight's difficulty fluctuates wildly depending on intent alignment. If multiple rats queue up 6-8 damage attacks simultaneously, prioritize full defense or bursting down one of the attackers.

## Relevant Deck Guides
[Deck Guide: shiv] memories=86, confidence=0.90, v26
  - **Core Engine & Upgrades:** `Phantom Blades` and `Accuracy` are mandatory for scaling damage. Prioritize upgrading generators like `Cloak and Dagger` and draw engines like `Acrobatics`.
- **Passive Defense:** Winning decks rely heavily on `Afterimage` (Innate is premium) and attack-trigger relics (Kunai, Ornamental Fan) to survive, rather than using high-cost block cards that choke your turns.
- **Energy & Cycle:** Sustaining your zero-cost engine requires intense draw (`Acrobatics`, `Expertise`, `Calculated Gamble`). You must secure immediate energy like `Adrenaline`; energy starvation is the primary cause of defeat in mid-game.
- **Avoid Anti-Synergies:** Keep decks lean (21-24 cards). Strictly avoid `Art of War` (which natively clashes with Shiv spam), expensive filler, and hybridizing with Poison or Sly sub-themes.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- Sucker Punch: 1-cost: 8 damage + 1 Weak. Acceptable as a transitional damage + debuff card early in the run. Skip if better options are available.
- Poisoned Stab: B tier: reliable hybrid frontload+poison. Strong in mixed Shiv/block decks and early boss fights; take when you need steady scaling without full poison commitment, skip once better poison engines or a
- Blade Dance: Premium Shiv engine. Best generator for Accuracy, Fan of Knives, Phantom Blades, Envenom, and Kunai-style scaling. In Shiv decks it is usually stronger than basic attacks or flat-damage filler; upgrade and protect it on remove/transform screens unless you already have redundant generation.
- Phantom Blades: Power: Your first Shiv played each turn deals bonus damage (+6). ALL Shivs Retain. This is primarily a combo/burst enabler, not just passive scaling. By hoarding 0-cost Shivs in hand over multiple turns, you can unleash massive zero-energy burst to push specific boss phases, bypass alternating immunities (like Test Subject's Nemesis), or secure lethal. High priority in Shiv decks.
- Expertise: 1-cost: draw up to 6 cards (fills hand to 6). Massive hand refill in one action. Less effective if hand is already near full. Enables combo turns by providing many card options at once.
- Leg Sweep: 2-cost: high Block + applies Weak. Scales with Dexterity for the Block portion. Pounce reduces the next Skill cost to 0 — play Pounce before Leg Sweep to play it for free.
- Fan of Knives: Power: causes all Shivs to deal AoE damage (hit ALL enemies instead of single target). Also generates 3 Shivs into hand this turn when played. Accuracy buffs each Shiv's AoE damage. Transforms Shiv builds from single-target to AoE output.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Strike |  | 6035 | 0 | 12696 | 6940 | 8994 | 21W|A1:16,A2:34,A3:13,inc:9
- Defend |  | 7348 | 3 | 16449 | 9539 | 518 | 25W|A1:16,A2:34,A3:13,inc:10
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3947 | 0 | 3462 | 160 | 4494 | 25W|A1:16,A2:33,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2405 | 5 | 3508 | 1402 | 10 | 25W|A1:16,A2:34,A3:14,inc:10
- Sucker Punch | 1-cost: 8 damage + 1 Weak. Acceptable as a transit | 211 | 0 | 246 | 71 | 657 | 4W|A1:5,A2:3,A3:3
- Poisoned Stab | B tier: reliable hybrid frontload+poison. Strong i | 672 | 0 | 904 | 309 | 1760 | 3W|A1:4,A2:12,A3:4,inc:3
- Blade Dance | Premium Shiv engine. Best generator for Accuracy,  | 1165 | 0 | 1211 | 220 | 22 | 15W|A1:9,A2:19,A3:10,inc:4
- Blade of Ink |  | 31 | 0 | 39 | 10 | 0 | 1W|A1:1,A2:1,A3:0,inc:1
- Phantom Blades | Power: Your first Shiv played each turn deals bonu | 310 | 0 | 359 | 109 | 20 | 11W|A1:2,A2:12,A3:8,inc:2
- Expertise | 1-cost: draw up to 6 cards (fills hand to 6). Mass | 228 | 0 | 428 | 225 | 52 | 8W|A1:2,A2:5,A3:5,inc:3
- Leg Sweep | 2-cost: high Block + applies Weak. Scales with Dex | 388 | 2 | 549 | 219 | 13 | 7W|A1:3,A2:8,A3:5,inc:3
- Fan of Knives | Power: causes all Shivs to deal AoE damage (hit AL | 154 | 0 | 224 | 90 | 9 | 8W|A1:1,A2:3,A3:2,inc:3

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F9(Skulking Colony: WIN), F12(Phantasmal Gardener: WIN), F17(Lagavulin Matriarch: )
- Core Combat Principles: F2(Seapunk: WIN), F3(Toadpole: WIN), F4(Corpse Slug: WIN), F5(Gremlin Merc: ), F6(Calcified Cultist: ), F9(Skulking Colony: WIN), F12(Phantasmal Gardener: WIN), F13(Two-Tailed Rat: WIN), F15(Haunted Ship: WIN), F17(Lagavulin Matriarch: )
- Deck Building Across the Run: F1(), F2(), F3(), F4(), F5(), F6(), F9(), F12(), F13(), F15()
- Ignore Minor Relic Distractions: F2(), F3(), F4(), F5(), F6(), F9(), F12(), F13(), F15()
- Map Routing and Path Planning: F1(), F1(), F6(), F9(), F10(), F14(), F14()
- Never Smith Upgraded Cards: F7(), F11(), F16()
- Rest Site and Event Decisions: F7(), F11(), F16()
- Silent - Combat Sequencing: F2(Seapunk: WIN), F3(Toadpole: WIN), F4(Corpse Slug: WIN), F5(Gremlin Merc: ), F6(Calcified Cultist: ), F9(Skulking Colony: WIN), F12(Phantasmal Gardener: WIN), F13(Two-Tailed Rat: WIN), F15(Haunted Ship: WIN), F17(Lagavulin Matriarch: )
- Silent - Draft and Shop Rules: F1(), F2(), F3(), F4(), F5(), F6(), F9(), F12(), F13(), F15()
- Silent - Route Priorities: F1(), F1(), F6(), F9(), F10(), F14(), F14()

## Dynamic Tools
- block_sufficiency_check: 19457 calls, 19457 successes
- poison_block_survival_plan: 4410 calls, 4410 successes
- poison_kill_and_survive_check: 18910 calls, 18910 successes
- poison_survival_analysis: 21320 calls, 20223 successes
- poison_turns_to_kill: 21363 calls, 20223 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.