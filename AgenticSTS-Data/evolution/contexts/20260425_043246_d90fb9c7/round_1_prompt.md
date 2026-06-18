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
Result: DEFEAT at Floor 17 (fitness: 74.9)
Combats won: 7/7
Run duration: 3780.5s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: Look for early premium damage cards to handle Act 1 Elites, and use the starting potion to secure a safe elite takedown.
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a core scaling engine (Shivs or Poison). Take cheap draw or high-impact damage; skip narrow synergy pieces without enablers.
- [map] Foundation deck: currently basic Silent starters, prioritizing early hallway fights to find damage and block scaling before the first elite.
### F2
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F3
- [event] Foundation phase: Look for early premium damage cards to handle Act 1 Elites, prioritizing card removal for long-term consistency.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F4
- [card_select] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine. We have some shiv generation, so look out for Accuracy or ninja relics, but stay open to other scaling if offered.
- [map] Foundation deck: Focus on acquiring 2-3 high-impact damage cards and efficient block to handle early elites; prioritize card rewards and gold over risky early elite fights.
### F5
- [card_reward] Foundation plan: survive with frontload damage while setting up Footwork for block scaling. We are leaning towards Shivs (have Blade Dance, C&D) but need a payoff like Accuracy, Phantom Blades, or Kunai/Shuriken to fully commit. Look for more damage to secure Act 1 Elites.
### F6
- [card_reward] Foundation plan: building around Shivs for damage and Footwork for defense. Looking for a core Shiv engine piece like Accuracy to commit. Continue taking efficient draw and frontload damage; avoid bloating the deck with slow or off-plan cards.
### F7
- [card_reward] Foundation plan: survive early fights with efficient damage and defense while looking for a core scaling engine (like Accuracy or poison). Use WLP to retain high-impact mitigation or combo pieces for the exact turn they are needed.
### F8
- [rest_site] Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.
- [map] Foundation deck: Focus on acquiring 2-3 high-impact damage cards and efficient block to handle early elites; prioritize card rewards and gold over risky early elite fights.
### F9
- [event] Foundation phase: We have defensive scaling with Footwork and WLP, but need strong damage to comfortably handle Act 1 elites and the boss. Look for high-impact attacks or poison, and prioritize upgrading key pieces.
### F10
- [map] Foundation deck: prioritizing high-impact damage and efficient block; use this Rest Site to upgrade a key card like Neutralize or a strong attack to prepare for the upcoming Elite.
### F11
- [rest_site] Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.
### F12
- [card_reward] Foundation plan: survive with efficient block (Footwork++) and frontload (Dash, Blade Dance) while seeking a core damage engine (like Accuracy/Phantom Blades for Shivs or Poison). Use WLP to hold key cards for optimal turns.
- [map] Foundation deck focusing on core damage and block: prioritize HP maintenance and key upgrades to safely navigate the remaining Act 1 elites and prepare for the boss. Current goal is to reach the boss with enough HP to win, using rest sites to smith unless HP drops below safe thresholds.
### F13
- [rest_site] Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.
### F14
- [hand_select] Dash++ is particularly good for maintaining block while finishing off enemies.
- [card_reward] Foundation plan: surviving with Footwork++, Dash++, and Malaise while looking for a real scaling damage engine like accuracy or poison. Prioritize finding a primary damage condition and avoid adding more defensive bloat.
### F15
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F16
- [rest_site] Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.
### F17
- [hand_select] Well-Laid Plans allows me to carry over resources. Survivor is flexible defensive value.
- [hand_select] Conserving block for the next attack cycle since I have -3 Dexterity and need the heavy block cards.

### Combat Decision Digest (8 combats)
F2 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 56->46, loss=10, WIN)
  R1[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Neutralize->Strike*2->Survivor | dealt=9 taken=0
  R2[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Defend*2->Strike | dealt=0 taken=8
  R3[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Defend*2->Blade Dance->Shiv*3 | dealt=8 taken=2
  R4[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Strike*2->Survivor | dealt=6 taken=0
  R5[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Neutralize->Strike | dealt=0 taken=0

F5 [monster] Seapunk (4R, HP 46->46, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize->Cloak and Dagger->Shiv->Blade Dance->Shiv*3->Defend | dealt=19 taken=0
  R2[Seapunk: Atk(2x4=8)]: Survivor->Dagger Throw->Strike | dealt=6 taken=0
  R3[Seapunk: Buff, Defend]: Cloak and Dagger->Shiv->Defend*2 | dealt=4 taken=0
  R4[Seapunk: Atk(12)]: Neutralize->Strike*2 | dealt=2 taken=0

F6 [monster] Sludge Spinner (3R, HP 46->46, loss=0, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize->Dagger Throw->Strike->Survivor | dealt=9 taken=0
  R2[Sludge Spinner: Atk(11)]: Cloak and Dagger->Defend->Blade Dance->Shiv*4 | dealt=12 taken=0
  R3[Sludge Spinner: Atk(6), Buff]: Strike*2 | dealt=6 taken=0

F7 [monster] Fossil Stalker (5R, HP 46->46, loss=0, WIN)
  R1[Fossil Stalker: Atk(12)]: Neutralize->Backflip->Footwork->Cloak and Dagger->Shiv | dealt=7 taken=0
  R2[Fossil Stalker: Atk(12)]: Defend*2->Blade Dance->Shiv*3 | dealt=12 taken=0
  R3[Fossil Stalker: Atk(9), Debuff]: Strike->Dagger Throw->Survivor | dealt=6 taken=0
  R4[Fossil Stalker: Atk(3x2=6)]: Neutralize->Strike->Defend*2 | dealt=9 taken=0
  R5[Fossil Stalker: Atk(9), Debuff]: Strike*2 | dealt=6 taken=0

F12 [monster] Sewer Clam (6R, HP 40->40, loss=0, WIN)
  R1[Sewer Clam: Atk(10)]: Backflip->Strike*2 | dealt=4 taken=0
  R2[Sewer Clam: Buff]: Neutralize+->Dagger Throw->Footwork+->Defend | dealt=0 taken=0
  R3[Sewer Clam: Atk(10)]: Well-Laid Plans->Neutralize+->Strike->Survivor | dealt=3 taken=0
  R4[Sewer Clam: Buff]: Dagger Throw->Cloak and Dagger->Shiv->Defend | dealt=4 taken=0
  R5[Sewer Clam: Atk(13)]: Backflip->Defend->Neutralize+->Blade Dance->Shiv*3 | dealt=11 taken=0
  R6[Sewer Clam: Buff]: Cloak and Dagger->Shiv->Strike->Dagger Throw | dealt=16 taken=0

F14 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (9R, HP 40->39, loss=1, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Footwork+->Defend->Neutralize+->Blade Dance->Shiv*3 | dealt=0 taken=0
  R2[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Well-Laid Plans->Dash+ | dealt=13 taken=1
  R3[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(9)]: Cloak and Dagger->Backflip->Strike->Shiv | dealt=6 taken=0
  R4[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(3x3=9)]: Dash+->Cloak and Dagger->Shiv | dealt=0 taken=0
  R5[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(9)]: Neutralize+->Dagger Throw->Defend*2 | dealt=4 taken=0
  R6[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Atk(2x3=6)]: Cloak and Dagger->Shiv->Dash+ | dealt=0 taken=0
  R7[Phantasmal Gardener: Atk(3x3=9)+Phantasmal Gardener: Buff]: Backflip->Dagger Throw->Strike | dealt=6 taken=0
  R8[Phantasmal Gardener: Atk(9)]: Dash+->Neutralize+->Strike | dealt=17 taken=0
  R9[Phantasmal Gardener: Atk(8)]: Neutralize+ | dealt=0 taken=0

F15 [monster] Punch Construct (5R, HP 39->33, loss=6, WIN)
  R1[Punch Construct: Defend]: Footwork+->Neutralize+->Strike->Survivor | dealt=10 taken=0
  R2[Punch Construct: Atk(14)]: Well-Laid Plans->Defend->Blade Dance->Shiv*3 | dealt=2 taken=6
  R3[Punch Construct: Atk(5x2=10), Debuff]: Dash+->Dagger Throw | dealt=13 taken=0
  R4[Punch Construct: Defend]: Backflip->Cloak and Dagger->Shiv->Dagger Throw | dealt=3 taken=0
  R5[Punch Construct: Atk(14)]: Neutralize+->Strike*3 | dealt=6 taken=0

F17 [boss] Lagavulin Matriarch (24R, HP 54->0, loss=54, LOSS)
  R1[Lagavulin Matriarch: Sleep]: Backflip->Dagger Throw->Defend | dealt=0 taken=0
  R2[Lagavulin Matriarch: Sleep]: Footwork+->Well-Laid Plans->Strike | dealt=0 taken=0
  R3[Lagavulin Matriarch: Sleep]: Cloak and Dagger->Shiv->Defend->Survivor | dealt=0 taken=0
  R4[Lagavulin Matriarch: Atk(19)]: Neutralize+->Dash+->Strike | dealt=23 taken=0
  R5[Lagavulin Matriarch: Atk(6x2=12)]: Piercing Wail->Blade Dance->Shiv*3->Dagger Throw | dealt=22 taken=4
  R6[Lagavulin Matriarch: Atk(12), Defend]: Cloak and Dagger->Shiv->Backflip->Neutralize+->Cloak and Dagger->Shiv | dealt=12 taken=0
  R7[Lagavulin Matriarch: Debuff, Buff]: Strike*3 | dealt=6 taken=0
  R8[Lagavulin Matriarch: Atk(21)]: Backflip->Dash+ | dealt=11 taken=1
  R9[Lagavulin Matriarch: Atk(11x2=22)]: Survivor->Malaise | dealt=0 taken=3
  R10[Lagavulin Matriarch: Atk(9), Defend]: Neutralize+->Cloak and Dagger->Shiv->Defend->Strike | dealt=8 taken=0
  R11[Lagavulin Matriarch: Debuff, Buff]: Dagger Throw->Strike*2 | dealt=3 taken=0
  R12[Lagavulin Matriarch: Atk(15)]: Backflip->Dash+ | dealt=9 taken=0
  R13[Lagavulin Matriarch: Atk(11x2=22)]: Neutralize+->Cloak and Dagger->Shiv->Defend->Survivor | dealt=0 taken=0
  R14[Lagavulin Matriarch: Atk(10), Defend]: Dash+->Dagger Throw | dealt=9 taken=0
  R15[Lagavulin Matriarch: Debuff, Buff]: Backflip->Cloak and Dagger->Neutralize+->Shiv->Strike | dealt=0 taken=0
  R16[Lagavulin Matriarch: Atk(17)]: Neutralize+->Cloak and Dagger->Shiv->Defend->Survivor | dealt=0 taken=7
  R17[Lagavulin Matriarch: Atk(9x2=18)]: Dash+->Backflip | dealt=7 taken=6
  R18[Lagavulin Matriarch: Atk(12), Defend]: Neutralize+->Backflip->Cloak and Dagger->Shiv->Defend | dealt=0 taken=5
  R19[Lagavulin Matriarch: Debuff, Buff]: Dagger Throw | dealt=0 taken=0
  R20[Lagavulin Matriarch: Atk(18)]: Dash+->Survivor | dealt=5 taken=7
  R21[Lagavulin Matriarch: Atk(15x2=30)]: Neutralize+->Backflip->Cloak and Dagger->Shiv->Dagger Throw | dealt=0 taken=9
  R22[Lagavulin Matriarch: Atk(13), Defend]: Backflip->Dash+ | dealt=5 taken=5
  R23[Lagavulin Matriarch: Debuff, Buff]: Neutralize+->Cloak and Dagger->Shiv->Strike*2 | dealt=0 taken=0
  R24[Lagavulin Matriarch: Atk(20)]: Dagger Throw->Survivor->Defend | dealt=0 taken=0

### Non-combat Decisions (74 decisions)
F1 [event] choose_event_option (option_index=0) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Lost Coffer is the statistically safest and highest-scoring Neow option here. Gaining an immediate card reward and a potion gives a strong jump-start for the first few hallway fights and the first Elite without introducing the major downside of a Curse from Neow's Bones.
  strategic_note: Foundation phase: Look for early premium damage cards to handle Act 1 Elites, and use the starting potion to secure a safe elite takedown.

F1 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F1 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F1 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->14
  deck_change: picked Blade Dance
  reasoning: Floor 1 requires frontloaded damage for upcoming hallway and elite fights. Blade Dance provides 12 damage for 1 energy and serves as a premium foundation for Shiv synergies. Outbreak is useless without existing poison cards.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a core scaling engine (Shivs or Poison). Take cheap draw or high-impact damage; skip narrow synergy pieces without enablers.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting with a monster fight to gain gold and card rewards as per the early-act strategy. This path leads toward a shop and allows for card accumulation before the first elite.
  strategic_note: Foundation deck: currently basic Silent starters, prioritizing early hallway fights to find damage and block scaling before the first elite.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 99->114 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 114->114 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 46->46 | Gold 114->114 | Deck 14->15
  deck_change: picked Dagger Throw
  reasoning: Dagger Throw provides early attack damage that bypasses Gremlin Nob's anti-skill enrage, while its draw and discard effect accelerates our deck cycling and helps filter out dead cards like Ascender's Bane.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F2 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 46->46 | Gold 114->114 | Deck 15->15
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 114->114 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Unknown

F3 [event] choose_event_option (option_index=1) | source=llm
  HP 46->46 | Gold 114->114 | Deck 15->15
  deck_change: no deck change
  reasoning: Early card removal provides excellent long-term scaling and deck consistency. Removing a Strike improves the chance to draw our better attacks like Blade Dance and Dagger Throw.
  strategic_note: Foundation phase: Look for early premium damage cards to handle Act 1 Elites, prioritizing card removal for long-term consistency.

F3 [card_select] select_deck_card (option_index=0) | source=llm
  HP 46->46 | Gold 114->114 | Deck 15->14
  deck_change: lost Strike
  reasoning: Removing a basic Strike improves the overall card quality and draw consistency of the deck. We have added Blade Dance and Dagger Throw for damage, so we can afford to lose a Strike.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F3 [event] choose_event_option (option_index=0) | source=auto
  HP 46->46 | Gold 114->114 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 114->114 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Shop

F4 [shop] buy_card (option_index=3) | source=plan
  HP 46->46 | Gold 114->89 | Deck 14->15
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [1/2]: On-sale foundational engine piece for a Shiv/Retain strategy that also provides efficient block.

F4 [shop] remove_card_at_shop | source=plan
  HP 46->46 | Gold 89->89 | Deck 15->15
  deck_change: no deck change
  reasoning: Shop plan [2/2]: Thinning a Strike makes our deck more consistent and cycles back to our better damage cards faster.

F4 [card_select] select_deck_card (option_index=0) | source=llm
  HP 46->46 | Gold 89->14 | Deck 15->14
  deck_change: lost Strike
  reasoning: Strike is the least efficient card in our deck, offering only 6 damage for 1 energy. We have better attacks now (Blade Dance, Dagger Throw) so removing a Strike improves our average card quality and draw consistency.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine. We have some shiv generation, so look out for Accuracy or ninja relics, but stay open to other scaling if offered.

F4 [shop] close_shop_inventory | source=llm
  HP 46->46 | Gold 14->14 | Deck 14->14
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F4 [shop] proceed | source=auto
  HP 46->46 | Gold 14->14 | Deck 14->14
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F4 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 14->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Both available nodes are monsters. I am following the route to collect card rewards and gold. This path leads towards a rest site and eventually an elite, allowing me to build foundational deck strength before the Act 1 boss.
  strategic_note: Foundation deck: Focus on acquiring 2-3 high-impact damage cards and efficient block to handle early elites; prioritize card rewards and gold over risky early elite fights.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 14->23 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 23->23 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 23->23 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 46->46 | Gold 23->23 | Deck 14->15
  deck_change: picked Footwork
  reasoning: Footwork is a premium defensive scaling Power for Silent. It synergizes perfectly with our Cloak and Dagger and Defends, and gives us an excellent setup card to play during the Lagavulin Matriarch's 3-turn sleep phase.
  strategic_note: Foundation plan: survive with frontload damage while setting up Footwork for block scaling. We are leaning towards Shivs (have Blade Dance, C&D) but need a payoff like Accuracy, Phantom Blades, or Kunai/Shuriken to fully commit. Look for more damage to secure Act 1 Elites.

F5 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 46->46 | Gold 23->23 | Deck 15->15
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 23->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Only path: Unknown

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 23->35 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F6 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 35->35 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F6 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 46->46 | Gold 35->35 | Deck 15->16
  deck_change: picked Backflip
  reasoning: Backflip is a premium draw and block card that synergizes perfectly with our Footwork pick, providing scaled block while helping us cycle to our damage sources and setup powers.
  strategic_note: Foundation plan: building around Shivs for damage and Footwork for defense. Looking for a core Shiv engine piece like Accuracy to commit. Continue taking efficient draw and frontload damage; avoid bloating the deck with slow or off-plan cards.

F6 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 46->46 | Gold 35->35 | Deck 16->16
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 35->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 35->42 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 46->46 | Gold 42->42 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F7 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 46->46 | Gold 42->42 | Deck 16->17
  deck_change: picked Well-Laid Plans
  reasoning: Well-Laid Plans is an incredible consistency tool and a premium power for Silent. It allows us to hold crucial defensive cards for high-damage enemy turns, or retain combo pieces and burst damage (like Blade Dance) for the right moment. It is specifically critical for setting up during the Lagavulin Matriarch's sleep phase.
  strategic_note: Foundation plan: survive early fights with efficient damage and defense while looking for a core scaling engine (like Accuracy or poison). Use WLP to retain high-impact mitigation or combo pieces for the exact turn they are needed.

F7 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 46->46 | Gold 42->42 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 42->42 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F8 [rest_site] choose_rest_option (option_index=1, smith_card_index=8) | source=llm
  HP 46->46 | Gold 42->42 | Deck 17->17
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: With 46 HP and another rest site at Floor 11 before the next Elite, I can comfortably Smith. Neutralize+ is one of the best early upgrades, extending the Weak duration to 2 turns and providing excellent mitigation for both Elites and the Boss.
  strategic_note: Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.

F8 [rest_site] proceed | source=auto
  HP 46->46 | Gold 42->42 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F8 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 42->42 | Deck 17->17
  deck_change: no deck change
  reasoning: HP is at 46 (66%). Taking an elite right now without a potion or a significant damage upgrade is too risky for the Silent. The Unknown node at (c2,r8) allows me to potentially find a favorable event, a shop, or a manageable hallway fight to further refine the deck before the mandatory elite later in the act. Staying on the recommended path preserves HP for future upgrades.
  strategic_note: Foundation deck: Focus on acquiring 2-3 high-impact damage cards and efficient block to handle early elites; prioritize card rewards and gold over risky early elite fights.

F9 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 46->40 | Gold 42->108 | Deck 17->17
  deck_change: no deck change
  reasoning: Taking 'This' provides a safe and efficient trade of 6 HP for Gold. Given we have 46 HP and Act 1 elites ahead, taking a guaranteed benefit without adding a curse to the deck keeps our consistency high.
  strategic_note: Foundation phase: We have defensive scaling with Footwork and WLP, but need strong damage to comfortably handle Act 1 elites and the boss. Look for high-impact attacks or poison, and prioritize upgrading key pieces.

F9 [event] choose_event_option (option_index=0) | source=auto
  HP 40->40 | Gold 108->108 | Deck 17->17
  deck_change: no deck change
  reasoning: Only option: Proceed

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 108->108 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 40->40 | Gold 108->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 40->40 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim: Anchor

F10 [treasure] proceed | source=random
  HP 40->40 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=llm
  HP 40->40 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: With 40/70 HP and an Elite fight approaching in four floors, the Rest Site is the superior choice to either Smith for permanent deck power or Heal if necessary. Following the established route ensures I have the strength to handle the upcoming Elite and Boss.
  strategic_note: Foundation deck: prioritizing high-impact damage and efficient block; use this Rest Site to upgrade a key card like Neutralize or a strong attack to prepare for the upcoming Elite.

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 40->40 | Gold 143->143 | Deck 17->17
  deck_change: upgraded Footwork->Footwork+
  reasoning: HP is at 40/70, which is comfortable enough for the next hallway fight, and we have two more rest sites before the boss. Upgrading Footwork to +3 Dexterity significantly increases our survivability, making every block card in the deck much stronger.
  strategic_note: Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.

F11 [rest_site] proceed | source=auto
  HP 40->40 | Gold 143->143 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 143->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 143->156 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 156->156 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim potion: Block Potion

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 40->40 | Gold 156->156 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 40->40 | Gold 156->156 | Deck 17->18
  deck_change: picked Dash
  reasoning: Dash provides an excellent mix of block and damage in a single card, which is extremely efficient for Act 1 and Act 2. With Footwork++ it scales even better for defense. Our damage is slightly low, and Dash provides consistent frontload without conditional requirements.
  strategic_note: Foundation plan: survive with efficient block (Footwork++) and frontload (Dash, Blade Dance) while seeking a core damage engine (like Accuracy/Phantom Blades for Shivs or Poison). Use WLP to hold key cards for optimal turns.

F12 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 40->40 | Gold 156->156 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F12 [map] choose_map_node (option_index=0) | source=llm
  HP 40->40 | Gold 156->156 | Deck 18->18
  deck_change: no deck change
  reasoning: With 40/70 HP and an Elite fight approaching on floor 13/14, I need to use this Rest Site to stabilize. The route intelligence suggests protecting HP for boss entry and elites. Since I have 156 gold and some card rewards from previous floors, I need to ensure I am healthy enough to take the upcoming Elite safely or use the campfire to upgrade a key damage/block card if I feel confident. Given the 'foundation deck' strategy, survival is the priority to reach the boss.
  strategic_note: Foundation deck focusing on core damage and block: prioritize HP maintenance and key upgrades to safely navigate the remaining Act 1 elites and prepare for the boss. Current goal is to reach the boss with enough HP to win, using rest sites to smith unless HP drops below safe thresholds.

F13 [rest_site] choose_rest_option (option_index=1, smith_card_index=14) | source=llm
  HP 40->40 | Gold 156->156 | Deck 18->18
  deck_change: upgraded Dash->Dash+
  reasoning: 40 HP is enough to survive an Act 1 Elite with our current defensive core (Footwork++ and Dash). Upgrading Dash provides an immediate +3 damage and +3 block, which is a massive tempo swing against Elites like Nob and Lagavulin. We can heal at the F16 rest site if the Elite fight drains our health.
  strategic_note: Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.

F13 [rest_site] proceed | source=auto
  HP 40->40 | Gold 156->156 | Deck 18->18
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 40->40 | Gold 156->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Elite

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 156->182 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 26 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 182->182 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim relic: Lucky Fysh

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 39->39 | Gold 182->182 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 39->39 | Gold 182->197 | Deck 18->19
  deck_change: picked Malaise
  reasoning: Malaise is a premium defensive card that trivializes multi-hit attacks and strength-scaling enemies. The upcoming Lagavulin Matriarch boss has a dangerous multi-hit attack and gains Strength over time. Malaise provides a massive defensive safety net alongside Footwork++.
  strategic_note: Foundation plan: surviving with Footwork++, Dash++, and Malaise while looking for a real scaling damage engine like accuracy or poison. Prioritize finding a primary damage condition and avoid adding more defensive bloat.

F14 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 39->39 | Gold 197->197 | Deck 19->19
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F14 [map] choose_map_node (option_index=0) | source=auto
  HP 39->39 | Gold 197->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 197->209 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 209->209 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim potion: Explosive Ampoule

F15 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 209->209 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F15 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 33->33 | Gold 209->224 | Deck 19->20
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a premium defensive card that synergizes perfectly with Well-Laid Plans to neutralize devastating multi-hit attacks, such as those from the upcoming Lagavulin Matriarch boss and Act 2 elites.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F15 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 33->33 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 33->54 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: With only 33 HP going into the Act 1 Boss, resting is necessary to survive the incoming burst damage (like Slime Crush or Guardian's Fierce Bash). We have good defense with Footwork++ and Malaise, but we cannot risk dying to a bad draw.
  strategic_note: Foundation deck focused on scaling defense with Footwork and setting up damage. Play Footwork early, use Well-Laid Plans to hold crucial block or damage cards, and whittle enemies down with Shivs and regular attacks. Seek a strong damage engine or poison to complement the defensive core.

F16 [rest_site] proceed | source=auto
  HP 54->54 | Gold 224->224 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 54->54 | Gold 224->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Boss

## Selected Replay Package (2 replays)
[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F14, elite)
Historical: loss=1 vs historical avg=19.4+/-16.4 (z=-1.1, BETTER_THAN_USUAL, n=12)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 14, elite)
Relics: Ring of the Snake, Lost Coffer, Anchor
Deck (18): Defend x5, Strike x3, Ascender's Bane, Backflip, Blade Dance, Cloak and Dagger, Dagger Throw, Dash+, Footwork+, Neutralize+, Survivor, Well-Laid Plans
Enemies: Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=27/27

### Round 1
Agent plan (hypothesis): Continue focusing one Gardener at a time to minimize Skittish value.
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Flex Potion
    +Strength(5) | +Flex Potion(5)
  turn_end
    exhausted: Shiv*3 [0费]：Deal 4 damage. Exhaust.

### Round 2
Agent plan (hypothesis): Retain Backflip to use its draw next turn.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  turn_end
  Backflip

### Round 3
Agent plan (hypothesis): Continue focusing down enemy 2.
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end
  Dash+

### Round 4
Agent plan (hypothesis): Retain Dagger Throw to help cycle next turn.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(3x3=9)
  turn_end
  Dagger Throw

### Round 5
Agent plan (hypothesis): Blocked all damage.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  Strike
  turn_end
  Survivor

### Round 6
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(2x3=6)
  turn_end
  Survivor

### Round 7
Agent plan (hypothesis): If you draw attacks to deal 12 EHP to Enemy 0, kill it. Otherwise, play Survivor to fully block.
Agent plan (hypothesis): Hold useful cards with WLP
Agent plan (hypothesis): Retain Dash+.
Intent: Phantasmal Gardener: Attack(3x3=9), Phantasmal Gardener: Buff
  Defend
  turn_end
  Dash+

### Round 8
Intent: Phantasmal Gardener: Attack(9)
  turn_end
  Cloak and Dagger

### Round 9
Intent: Phantasmal Gardener: Attack(8)
  cards: Neutralize+, dealt=0, taken=0
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 9 rounds)

Enemy power timeline:
  Skittish: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:6 -> R9:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:- -> R9:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6 -> R7:6 -> R8:- -> R9:-
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Skittish[3]: R1:6 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:4 -> R9:4
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:2 -> R8:- -> R9:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:1 -> R7:- -> R8:- -> R9:1

Unattributed damage (power/passive effects): 46
  Per round: R2:13 R3:6 R5:4 R7:6 R8:17
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 12, elite)
Relics: Ring of the Snake, Precarious Shears, Beating Remnant, Amethyst Aubergine
Deck (16): Defend x5, Strike x3, Blade Dance, Blade of Ink, Expertise, Neutralize+, Phantom Blades, Poisoned Stab, Sucker Punch, Survivor
Enemies: Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=29/29, Phantasmal Gardener HP=28/28

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Fire Potion -> Phantasmal Gardener[2]
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Ship in a Bottle
    block +10 | +Block Next Turn(10)
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(6)
  Strike
  turn_end

### Round 4
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(2x3=6)
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(2x3=6), Phantasmal Gardener: Attack(7)
  turn_end

### Round 6
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(9)
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(2x3=6)
  turn_end

### Round 8
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

[Selected: boss, death] Lagavulin Matriarch (F17, boss)
Historical: loss=54 vs historical avg=30.7+/-19.6 (z=1.2, TYPICAL, n=34)
## Combat Replay: vs Lagavulin Matriarch (Floor 17, boss)
Relics: Ring of the Snake, Lost Coffer, Anchor, Lucky Fysh
Deck (20): Defend x5, Strike x3, Ascender's Bane, Backflip, Blade Dance, Cloak and Dagger, Dagger Throw, Dash+, Footwork+, Malaise, Neutralize+, Piercing Wail, Survivor, Well-Laid Plans
Enemies: Lagavulin Matriarch HP=222/222

### Round 1
Intent: Lagavulin Matriarch: Sleep
  Strike
  turn_end

### Round 2
Intent: Lagavulin Matriarch: Sleep
  turn_end
  Dash+

### Round 3
Intent: Lagavulin Matriarch: Sleep
  Dash+
  turn_end
    exhausted: Shiv [0费]：Deal 4 damage. Exhaust.
  Piercing Wail

### Round 4
Intent: Lagavulin Matriarch: Attack(19)
  turn_end
  Piercing Wail

### Round 5
Intent: Lagavulin Matriarch: Attack(6x2=12)
  Explosive Ampoule
    enemy_deltas: Lagavulin Matriarch: hp -10
  Strike
  turn_end
  Cloak and Dagger

### Round 6
Intent: Lagavulin Matriarch: Attack(12), Defend
  turn_end
  Defend

### Round 7
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
  Dash+

### Round 8
Intent: Lagavulin Matriarch: Attack(21)
  turn_end
  Malaise

### Round 9
Intent: Lagavulin Matriarch: Attack(11x2=22)
  Strike
  turn_end
  Defend

### Round 10
Intent: Lagavulin Matriarch: Attack(9), Defend
  turn_end
  Defend

### Round 11
Intent: Lagavulin Matriarch: Debuff, Buff
  Defend
  turn_end
  Survivor

### Round 12
Intent: Lagavulin Matriarch: Attack(15)
  turn_end
  Survivor

### Round 13
Intent: Lagavulin Matriarch: Attack(11x2=22)
  Strike
  turn_end
  Dagger Throw

### Round 14
Intent: Lagavulin Matriarch: Attack(10), Defend
  Strike
  turn_end
  Defend

### Round 15
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
  Survivor

### Round 16
Intent: Lagavulin Matriarch: Attack(17)
  Defend
  turn_end
  Defend

### Round 17
Intent: Lagavulin Matriarch: Attack(9x2=18)
  turn_end
  Defend

### Round 18
Intent: Lagavulin Matriarch: Attack(12), Defend
  turn_end
  Dagger Throw

### Round 19
Intent: Lagavulin Matriarch: Debuff, Buff
  Strike
  turn_end
  Dash+

### Round 20
Intent: Lagavulin Matriarch: Attack(18)
  Defend
  turn_end
  Cloak and Dagger

### Round 21
Intent: Lagavulin Matriarch: Attack(15x2=30)
  Block Potion
    block +12
  Strike
  turn_end
  Defend

### Round 22
Intent: Lagavulin Matriarch: Attack(13), Defend
  turn_end
  Survivor

### Round 23
Intent: Lagavulin Matriarch: Debuff, Buff
  turn_end
  Survivor

### Round 24
Intent: Lagavulin Matriarch: Attack(20)
  Strike
  Strike
  turn_end
  Cloak and Dagger
## Combat Analytics: Lagavulin Matriarch (LOSS - 24 rounds)
Death cause: Died with HP=7, damage_taken=0. Likely mechanic kill.

Enemy power timeline:
  Asleep: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:- -> R20:- -> R21:- -> R22:- -> R23:- -> R24:-
  Plating: R1:12 -> R2:11 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:- -> R13:- -> R14:- -> R15:- -> R16:- -> R17:- -> R18:- -> R19:- -> R20:- -> R21:- -> R22:- -> R23:- -> R24:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:2 -> R9:2 -> R10:- -> R11:- -> R12:2 -> R13:2 -> R14:2 -> R15:2 -> R16:4 -> R17:4 -> R18:4 -> R19:4 -> R20:6 -> R21:6 -> R22:6 -> R23:6 -> R24:8
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:1 -> R8:- -> R9:- -> R10:1 -> R11:2 -> R12:1 -> R13:- -> R14:1 -> R15:- -> R16:1 -> R17:2 -> R18:1 -> R19:2 -> R20:1 -> R21:- -> R22:1 -> R23:- -> R24:1

Unattributed damage (power/passive effects): 110
  Per round: R4:23 R5:12 R6:12 R7:6 R8:11 R10:8 R11:3 R12:9 R14:9 R17:7 R20:5 R22:5
Comparator (recent same-enemy comparator):
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

## Existing Combat Guides (relevant enemies)
[Guide: Fossil Stalker] WR=100%, 43 episodes, confidence=0.90, v33
  - **Respect the LATCH_MOVE:** Overplaying Strikes and Shivs during the `LATCH_MOVE` phase is the primary cause of HP loss (averaging 8.5 damage taken). Pivot entirely to Block cards like Defend, Survivor, and Backflip during this window.
- **Beat the Round 4 Clock:** Fossil Stalker begins scaling Strength aggressively starting in Round 4. Establish Poison early (Deadly Poison, Poisoned Stab) or use dense upfront attacks (Strangle, Predator) to secure a Round 3 or 4 kill before its damage outpaces your block.
- **Maintain Weakness:** The enemy's base attacks hit for 9-15 damage even before scaling. Consistently cycle Neutralize and Leg Sweep to keep the enemy weakened and offset these heavy hits.
- **Block While Poison Ticks:** Low-HP-loss patterns show a heavy reliance on defensive cards (playing Defend far more often than basic Strikes). Apply your damage engine early, then shift energy entirely toward survival, letting unattributed poison damage secure the kill.
[Guide: Lagavulin Matriarch] WR=54%, 35 episodes, confidence=0.90, v35
  - **Maximize the Sleep Phase:** She begins Asleep with Plating 12 (reducing by 1 each turn). Use these 3 free turns purely for setup. Avoid dealing unblocked damage, as losing any HP immediately breaks her sleep and starts her attack cycle.
- **The Awake Cycle:** Once awake, she strictly loops a 4-turn sequence: Heavy Attack (19) -> Multi-hit Attack (9x2) -> Attack (12) + Block (10) -> Siphon Stats.
- **Siphon Scaling:** On the 4th turn of her cycle, she drains your stats (-2 Strength, -2 Dexterity) and buffs herself (+2 Strength). This permanent swing makes every subsequent cycle exponentially harder.
- **DPS Race:** This fight is a strict timer. Do not try to stall or out-block her once she is awake, as your Dexterity will collapse while her Strength scales. Burst her down before or immediately after the first Siphon turn.
- **Multi-hit Penalty:** Keep in mind that negative Strength disproportionately penalizes your multi-hit attacks. Unload your rapid-hit damage before the first Siphon debuff hits.
[Guide: Punch Construct] WR=98%, 41 episodes, confidence=0.90, v34
  - **Strip Artifact First:** The Construct always starts with 1 Artifact. Lead with a low-value debuff (like Neutralize) on Turn 1 before attempting to apply key debuffs like Weakness or Poison.
- **Burst Quickly:** You can end the fight flawlessly in 2-3 rounds by playing setup cards (Accuracy, Blade of Ink, Predator) on Turn 1, then unleashing Shivs and burst damage on Turn 2.
- **Respect Heavy Attacks:** If a fast kill isn't guaranteed, prioritize full block during the 14-damage and 'STRONG_PUNCH' intents. High HP loss happens almost exclusively when players overextend with attacks (Shivs, Strikes) during these turns.
- **Exploit Passive Windows:** The Construct will periodically use 'Defend' or 'Debuff' intents. Use these completely safe turns to deploy powers (Footwork), play card draw, or apply stacking Poison without bleeding HP.
[Guide: Seapunk] WR=98%, 66 episodes, confidence=0.90, v39
  - **Prioritize Block Over Strikes:** High HP loss (8.9 avg) occurs when over-committing to Strikes during Seapunk's 11-damage or 2x4 attack turns. Always prioritize full-blocking with Defends and Survivor; your damage should come from passive scaling or burst during safe windows.
- **Timed Neutralization:** Use Neutralize specifically to mitigate multi-hits and heavy 11-damage strikes. This brings incoming damage into a range where basic Defends can fully negate the hit, preventing chip damage.
- **Exploit Non-Attack Windows:** Seapunk frequently uses turns to Buff or Defend. These are your only opportunities to play setup cards like Afterimage or high-cost Poison like Bouncing Flask without taking damage.
- **The Turn 4 Deadline:** Seapunk scales Strength on Turn 4 (and again on Turn 7). Aim for a burst finish by Round 3 using Blade Dance or Assassinate. If the fight persists, transition into a pure defensive posture while Poison or existing Shiv scaling finishes the enemy.
- **Manage Sea Kick:** Watch for the SEA_KICK_MOVE; failure to block effectively during this pattern is a primary driver of high-damage rounds and losses.
[Guide: Sewer Clam] WR=94%, 33 episodes, confidence=0.90, v24
  - **Prioritize Poison Early:** Use non-damaging buff turns (R1, R3) to apply Poison (Deadly Poison, Poisoned Stab) or setup Powers (Footwork, Noxious Fumes). Poison ignores the high starting Plating (8-9), providing the most efficient scaling.
- **Hold Multi-hits for Round 4+:** Plating decays by 1 each turn. Shivs and multi-hit cards (Blade Dance, Dagger Spray) are significantly more effective once Plating has dropped to 5 or lower. Early Shiv usage is a primary cause of low damage efficiency.
- **Full Block on Attack Turns:** The Clam alternates between buffs and heavy hits. In R2 (10 dmg) and R4 (14 dmg), prioritize Block and Weakness (Neutralize, Leg Sweep) over chip damage. Data shows average losses of 9.5 HP when players greedily play Strikes/Shivs during these turns.
- **Counter Strength Scaling:** The enemy gains +4 Strength every odd turn. Applying Weakness specifically for even-numbered rounds is critical to survive the scaling attack damage (10 -> 14 -> 18).
[Guide: Sludge Spinner] WR=100%, 68 episodes, confidence=0.90, v41
  - **Respect Early Attacks:** Sludge Spinner frequently attacks for 8-11 damage in the opening rounds. Prioritize full-blocking with `Survivor` and `Defend`; high-damage rounds occur almost exclusively when overplaying `Strike` and ignoring defense.
- **Beat the Strength Clock:** The enemy buffs itself with +3 Strength between Rounds 3 and 5. Aim to close out the fight in 3-4 rounds using early burst sequences or `Shiv` generators to completely bypass this dangerous phase.
- **Tactical Neutralize Timing:** Hold `Neutralize` for the enemy's 11-damage attacks, or apply it immediately after the Spinner gains its +3 Strength to blunt the incoming amplified damage if the fight extends past Round 4.
[Guide: multi:Corpse Slug+Corpse Slug] WR=100%, 76 episodes, confidence=0.90, v51
  - **Control the Kill:** The defining mechanic is the Ravenous power. Whittle both slugs down evenly to secure a simultaneous kill, or ensure you can defeat the second slug immediately after the first dies.
- **Exploit the Stun:** When one slug dies, the survivor spends its next turn eating the corpse, rendering it Stunned. Use this free turn to safely finish off the survivor or heavily prepare your defenses.
- **Respect the Enrage:** If forced into the solo phase without lethal, expect significantly higher damage (e.g., 7x2 multi-hits or 12-damage single hits). Prioritize defensive mitigation over aggressive plays.
- **Manage Frail:** The slugs routinely use a debuff intent to apply Frail. Avoid transitioning into the dangerous enraged phase while severely Frail, as you will need your block cards functioning at full capacity to survive.
[Guide: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener] WR=92%, 13 episodes, confidence=0.90, v12
  - **The Staggered Cycle:** Gardeners follow a strict 4-turn loop: Attack(5) -> Attack(7) -> Attack(1x3) -> Buff (+2 Str). They are staggered, so one buffs while three attack.
- **Skittish Mechanic:** Skittish(6) grants 6 Block the *first* time a Gardener is hit each turn. Spreading attacks across multiple enemies triggers Skittish multiple times, severely reducing your net damage.
- **Combat Tactics:** Focus ALL your damage on a single target until it dies. When attacking your chosen target, always lead with a single attack of 7+ damage to cleanly break the Skittish block before playing multi-hits or low-damage attacks.
- **Target Priority:** Burst down the Gardener about to use its multi-hit attack, as multi-hits scale disproportionately with their accumulated Strength buffs.

## Relevant Deck Guides
[Deck Guide: shiv] memories=88, confidence=0.86, v29
  - Winning Shiv decks were focused mid-size lists (about 23-24 cards) with lots of cheap Shiv generation plus draw/cycle, not oversized piles or tiny underbuilt decks.
- Prioritize `Blade Dance`, `Cloak and Dagger`, `Acrobatics`, `Calculated Gamble`, and `Backflip`; add `Accuracy`/`Phantom Blades` once you already make enough Shivs.
- `Afterimage` was the best defensive payoff in wins, especially upgraded/Innate; `Footwork` is a solid backup, but clunky expensive defense underperformed.
- Best upgrades: `Afterimage+`, `Blade Dance+`, `Cloak and Dagger+`, `Neutralize+`, then your main scaling power.
- Only hybrid into Poison via `Envenom` (great with `Snecko Skull`). Avoid slow poison cards and filler attacks that don’t help Shiv volume or cycling.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- Blade Dance: Premium Shiv engine. Best generator for Accuracy, Fan of Knives, Phantom Blades, Envenom, and Kunai-style scaling. In Shiv decks it is usually stronger than basic attacks or flat-damage filler; upgrade and protect it on remove/transform screens unless you already have redundant generation.
- Dagger Throw: 1-cost: 9 damage + draw 1 + discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Cycles deck while dealing damage. Flat 9 damage — does not scale with build progression.
- Cloak and Dagger: 1-cost Skill: 6 Block, generates 1 Shiv (Upgraded: 2). High-tier foundational piece for Shiv engines, scaling defensively with Dexterity (Footwork) and offensively with Accuracy. The upgrade is extremely high priority as it doubles the Shiv output. Keep in mind it plays 2-3 cards total, making it susceptible to Beat of Death and Time Eater restrictions later in runs.
- Footwork: Power: permanent +2 Dexterity (upgraded: +3). All Block cards gain +2/+3 Block for rest of combat. Stacks with multiple copies. Unlike Anticipate, this is permanent. Upgrade from +2 to +3 is a significant boost.
- Backflip: 1-cost: block + draw 2. Defends and cycles simultaneously. The draw does not trigger Sly (draw is not discard). Pairs with Dexterity (Footwork) for scaled Block.
- Well-Laid Plans: A-tier control enabler: retains 1/2 cards each turn. CRITICAL for surviving strict boss cycles (Lagavulin Matriarch, Skulking Colony). Do not just retain random cards—specifically hold your highest impact mitigation (Neutralize+, Piercing Wail, Leg Sweep) to precisely counter predictable multi-hit/strength spikes. Also excellent for holding burst pieces until lethal is achievable.
- Dash: Premium A-tier attack+block. Best on real damage turns or to tempo while defending; avoid spending it just to answer printed damage under Intangible or other temporary mitigation.
- Malaise: X-cost: Consumes ALL remaining energy to reduce Strength & apply Weak. NEVER play two in one turn (the 2nd uses 0 energy and does nothing). Do NOT sequence this last after playing your hand. If you need mitigation, play 0-cost cards, then play Malaise immediately to invest maximum energy. Playing it for 0 or 1 energy against a scaling boss is a massive waste of mitigation.
- Piercing Wail: A-tier defense. Its value multiplies per enemy attack instance. Against a single attack, it mitigates 6 damage (worse than Survivor). Against a 3x3 attack, it mitigates 18 damage. Save/retain it specifically for the scariest multi-hit turns. Do not waste it on single heavy hits unless lethal is imminent. Outstanding in boss fights and multi-enemy encounters.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Strike |  | 6078 | 0 | 12784 | 6986 | 8994 | 22W|A1:17,A2:34,A3:13,inc:9
- Defend |  | 7386 | 3 | 16596 | 9649 | 518 | 27W|A1:17,A2:34,A3:13,inc:10
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 4003 | 0 | 3508 | 162 | 4494 | 27W|A1:17,A2:33,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2432 | 5 | 3557 | 1427 | 10 | 27W|A1:17,A2:34,A3:14,inc:10
- Ascender's Bane |  | 0 | 0 | 359 | 359 | 0 | 3W|A1:7,A2:8,A3:5,inc:3
- Blade Dance | Premium Shiv engine. Best generator for Accuracy,  | 1174 | 0 | 1222 | 222 | 22 | 16W|A1:10,A2:19,A3:10,inc:4
- Dagger Throw | 1-cost: 9 damage + draw 1 + discard 1. The discard | 1107 | 0 | 1347 | 406 | 2191 | 15W|A1:5,A2:16,A3:5,inc:6
- Cloak and Dagger | 1-cost Skill: 6 Block, generates 1 Shiv (Upgraded: | 1491 | 4 | 1537 | 295 | 92 | 17W|A1:4,A2:18,A3:9,inc:8
- Footwork | Power: permanent +2 Dexterity (upgraded: +3). All  | 611 | 0 | 604 | 112 | 64 | 17W|A1:3,A2:18,A3:8,inc:8
- Backflip | 1-cost: block + draw 2. Defends and cycles simulta | 1736 | 0 | 1945 | 461 | 387 | 22W|A1:7,A2:22,A3:10,inc:3
- Well-Laid Plans | A-tier control enabler: retains 1/2 cards each tur | 374 | 0 | 531 | 219 | 26 | 16W|A1:4,A2:15,A3:7,inc:1
- Dash | Premium A-tier attack+block. Best on real damage t | 327 | 0 | 410 | 121 | 754 | 5W|A1:3,A2:9,A3:6
- Malaise | X-cost: Consumes ALL remaining energy to reduce St | 119 | 0 | 184 | 93 | 29 | 9W|A1:1,A2:6,A3:4,inc:1
- Piercing Wail | A-tier defense. Its value multiplies per enemy att | 502 | 0 | 1101 | 670 | 67 | 19W|A1:5,A2:18,A3:12,inc:7

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F14(Phantasmal Gardener: WIN), F17(Lagavulin Matriarch: )
- Core Combat Principles: F2(Corpse Slug: WIN), F5(Seapunk: WIN), F6(Sludge Spinner: WIN), F7(Fossil Stalker: WIN), F12(Sewer Clam: WIN), F14(Phantasmal Gardener: WIN), F15(Punch Construct: WIN), F17(Lagavulin Matriarch: )
- Deck Building Across the Run: F1(), F2(), F3(), F4(), F4(), F4(), F5(), F6(), F7(), F12(), F14(), F15()
- Ignore Minor Relic Distractions: F1(), F2(), F4(), F4(), F5(), F6(), F7(), F12(), F14(), F15()
- Map Routing and Path Planning: F1(), F1(), F4(), F8(), F10(), F12()
- Never Smith Upgraded Cards: F8(), F11(), F13(), F16()
- Rest Site and Event Decisions: F8(), F11(), F13(), F16()
- Silent - Combat Sequencing: F2(Corpse Slug: WIN), F5(Seapunk: WIN), F6(Sludge Spinner: WIN), F7(Fossil Stalker: WIN), F12(Sewer Clam: WIN), F14(Phantasmal Gardener: WIN), F15(Punch Construct: WIN), F17(Lagavulin Matriarch: )
- Silent - Draft and Shop Rules: F1(), F2(), F3(), F4(), F4(), F4(), F5(), F6(), F7(), F12(), F14(), F15()
- Silent - Route Priorities: F1(), F1(), F4(), F8(), F10(), F12()

## Dynamic Tools
- block_sufficiency_check: 19732 calls, 19732 successes
- poison_block_survival_plan: 4685 calls, 4685 successes
- poison_kill_and_survive_check: 19185 calls, 19185 successes
- poison_survival_analysis: 21595 calls, 20498 successes
- poison_turns_to_kill: 21638 calls, 20498 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.