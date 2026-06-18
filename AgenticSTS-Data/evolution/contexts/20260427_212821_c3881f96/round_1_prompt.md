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
Result: DEFEAT at Floor 9 (fitness: 64.1)
Combats won: 4/4
Run duration: 2115.7s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: currently relying on starting cards, prioritize finding strong early attacks and block cards while using Winged Boots to optimize our path for maximum campfires and Elites.
- [map] Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.
### F2
- [card_reward] Foundation phase: prioritize high-impact damage for early elites while looking for a core scaling engine (Poison or Shivs). Retain survival cards. Skip narrow synergy pieces without enablers.
- [map] Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.
### F3
- [event] Foundation phase: currently relying on starting cards, prioritize finding strong early attacks and block cards while using Winged Boots to optimize our path for maximum campfires and Elites.
- [map] Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.
### F4
- [card_reward] Foundation phase: prioritize high-impact damage and early scaling pieces like discard outlets to survive early elites. Look for Sly cards to abuse discard.
- [map] Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.
### F5
- [card_reward] Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; we have strong single-target poison now, need AoE or efficient defense next.
- [map] I am currently in the foundation stage, prioritizing strong early-game damage and defensive utility; I will use this shop to remove a basic card and look for a premium scaling or front-loaded damage card to stabilize before taking on elites.
### F6
- [card_select] Foundation plan: transition into a committed Poison build since we have Bouncing Flask and Deadly Poison. Prioritize survival with efficient block, AoE (if needed), and card draw to cycle our poison quickly. Avoid adding generic attacks that dilute the deck.
- [map] Building a foundation deck by prioritizing card removal and early upgrades, focusing on solid damage cards to handle elites and high-value hallway fights while maintaining health.
### F7
- [rest_site] Poison-based plan utilizing Bouncing Flask and Deadly Poison for scaling damage, while defending and applying Weak. Ricochet provides extra damage via Sly when discarded. Needs more block and card draw; avoid raw attacks.
- [map] I am in the foundation stage, prioritizing strong early-game damage and defensive utility; I will focus on acquiring efficient attacks and block cards to stabilize before taking on elites.
### F8
- [card_reward] Foundation plan: use discard outlets to cheat out Sly cards for efficient upfront damage/AoE, while leaning on Bouncing Flask for boss scaling. Still looking for a cohesive scaling engine; prioritize cheap draw and card removal over narrow synergy pieces.
- [map] Building a foundation deck by prioritizing card removal and early upgrades, focusing on solid damage cards to handle elites and high-value hallway fights while maintaining health.

### Combat Decision Digest (4 combats)
F2 [monster] multi:Toadpole+Toadpole (7R, HP 70->66, loss=4, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Defend*2->Strike | dealt=0 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike->Neutralize->Defend->Survivor | dealt=9 taken=0
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Defend*2->Neutralize->Strike | dealt=0 taken=4
  R4[Toadpole: Buff+Toadpole: Atk(7)]: Strike*2->Survivor | dealt=0 taken=0
  R5[Toadpole: Buff]: Strike->Defend*2 | dealt=6 taken=0
  R6[Toadpole: Atk(3x3=9)]: Defend->Survivor | dealt=0 taken=0
  R7[Toadpole: Atk(7)]: Neutralize->Strike | dealt=3 taken=0

F4 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 60->58, loss=2, WIN)
  R1[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Neutralize->Defend->Deadly Poison->Strike | dealt=9 taken=0
  R2[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Survivor->Defend*2 | dealt=0 taken=2
  R3[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Neutralize->Defend*2->Strike | dealt=6 taken=0
  R4[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Strike*2->Deadly Poison | dealt=6 taken=0
  R5[Corpse Slug: Debuff]: Strike | dealt=0 taken=0

F5 [monster] Sludge Spinner (4R, HP 58->58, loss=0, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Strike*2->Survivor->Hidden Daggers->Shiv*2 | dealt=20 taken=0
  R2[Sludge Spinner: Atk(6), Buff]: Neutralize->Defend->Strike*2 | dealt=10 taken=0
  R3[Sludge Spinner: Atk(11), Debuff]: Deadly Poison->Survivor->Defend | dealt=0 taken=0
  R4[Sludge Spinner: Atk(14)]: Neutralize->Strike | dealt=2 taken=0

F8 [monster] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (6R, HP 58->53, loss=5, WIN)
  R1[Two-Tailed Rat: Debuff+Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(6)]: Neutralize+->Strike->Defend->Survivor | dealt=0 taken=0
  R2[Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(4)+Two-Tailed Rat: Debuff]: Backflip->Hidden Daggers->Ricochet->Strike->Deadly Poison->Shiv*2 | dealt=0 taken=5
  R3[Two-Tailed Rat: Summon+Two-Tailed Rat: Atk(8)]: Backflip->Defend*2 | dealt=0 taken=0
  R4[Two-Tailed Rat: Summon]: Neutralize+->Strike->Deadly Poison->Defend | dealt=10 taken=0
  R5[Two-Tailed Rat: Debuff+Two-Tailed Rat: Atk(6)]: Hidden Daggers->Shiv*2->Strike | dealt=0 taken=0
  R6[Two-Tailed Rat: Atk(8)]: Neutralize+->Deadly Poison->Backflip->Strike | dealt=4 taken=0

### Non-combat Decisions (37 decisions)
F1 [event] choose_event_option (option_index=1) | source=llm
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Winged Boots provides incredible routing flexibility in Act 1, allowing us to snipe high-value nodes like early campfires for upgrades or Elites when we are strong, or dodge fights if our HP gets low. The score and event guide strongly support this pick for maximizing our snowball potential.
  strategic_note: Foundation phase: currently relying on starting cards, prioritize finding strong early attacks and block cards while using Winged Boots to optimize our path for maximum campfires and Elites.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 70->70 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Starting at the leftmost monster node (c1,r1) sets up a flexible path to hit early shops. Since I have 99 gold, I want to reach a shop quickly to remove Strikes or add key cards, and the c1,r1 node offers the most flexibility to pivot toward a shop-heavy path in the early act.
  strategic_note: Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 99->112 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 66->66 | Gold 112->112 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 66->66 | Gold 112->112 | Deck 12->13
  deck_change: picked Deadly Poison
  reasoning: Floor 2: we need damage. Deadly Poison is efficient, low-cost damage that scales well against early Elites like Lagavulin, and starts us toward a potential poison engine.
  strategic_note: Foundation phase: prioritize high-impact damage for early elites while looking for a core scaling engine (Poison or Shivs). Retain survival cards. Skip narrow synergy pieces without enablers.

F2 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 66->66 | Gold 112->112 | Deck 13->13
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F2 [map] choose_map_node (option_index=0) | source=llm
  HP 66->66 | Gold 112->112 | Deck 13->13
  deck_change: no deck change
  reasoning: The route planning prioritizes flexibility and pathing toward early shops. Moving to the first unknown node keeps the options open while adhering to the strategy of navigating toward early-act shops for deck thinning.
  strategic_note: Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.

F3 [event] choose_event_option (option_index=0) | source=llm
  HP 66->60 | Gold 112->172 | Deck 13->13
  deck_change: no deck change
  reasoning: Trading 6 HP for a solid amount of Gold is very efficient early on. It avoids adding a curse to our deck, which would hurt our draw consistency before early Elites, and brings our Gold total close to shop relic or multiple-purchase thresholds.
  strategic_note: Foundation phase: currently relying on starting cards, prioritize finding strong early attacks and block cards while using Winged Boots to optimize our path for maximum campfires and Elites.

F3 [event] choose_event_option (option_index=0) | source=auto
  HP 60->60 | Gold 172->172 | Deck 13->13
  deck_change: no deck change
  reasoning: Only option: Proceed

F3 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 172->0 | Deck 13->13
  deck_change: no deck change
  reasoning: The route suggests a monster fight which is standard for early Act 1 to build gold and card rewards. My HP is healthy enough to handle another hallway fight before considering more specialized nodes.
  strategic_note: Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 172->184 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 184->184 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 58->58 | Gold 184->184 | Deck 13->14
  deck_change: picked Hidden Daggers
  reasoning: Expert knowledge flags Hidden Daggers as a premium must-pick card that sets up future discard and Sly synergies while providing free damage via Shivs. While Sucker Punch offers immediate attack damage, Hidden Daggers provides 0-energy scaling potential.
  strategic_note: Foundation phase: prioritize high-impact damage and early scaling pieces like discard outlets to survive early elites. Look for Sly cards to abuse discard.

F4 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 58->58 | Gold 184->184 | Deck 14->14
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F4 [map] choose_map_node (option_index=1) | source=llm
  HP 58->58 | Gold 184->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Following the recommended route to take a Monster node for card rewards and gold to prepare for upcoming shops and elites.
  strategic_note: Currently in the foundation stage, prioritizing strong early-game damage and defensive utility to survive hallways while pathing toward early shops for critical deck thinning and engine-building.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 184->199 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 199->199 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Heart of Iron

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 199->199 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 58->58 | Gold 199->199 | Deck 14->15
  deck_change: picked Bouncing Flask
  reasoning: Bouncing Flask provides exceptional single-target damage for Elites and the Waterfall Giant boss. With Deadly Poison and Hidden Daggers, our single-target burst is getting strong enough to handle Act 1 challenges.
  strategic_note: Foundation plan: survive with frontload damage and efficient block while looking for a real scaling engine; we have strong single-target poison now, need AoE or efficient defense next.

F5 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 58->58 | Gold 199->199 | Deck 15->15
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F5 [map] choose_map_node (option_index=1) | source=llm
  HP 58->58 | Gold 199->199 | Deck 15->15
  deck_change: no deck change
  reasoning: Visiting the shop now is optimal. With 199 gold, I can secure critical deck thinning (removing a Strike or Defend) or purchase a high-impact early game relic/card, which aligns with the 'Early Shop Power' priority. Delaying the shop risk losing utility if a card reward doesn't provide enough offense for the upcoming elites.
  strategic_note: I am currently in the foundation stage, prioritizing strong early-game damage and defensive utility; I will use this shop to remove a basic card and look for a premium scaling or front-loaded damage card to stabilize before taking on elites.

F6 [shop] buy_card (option_index=2) | source=plan
  HP 58->58 | Gold 199->174 | Deck 15->16
  deck_change: bought Backflip
  reasoning: Shop plan [1/3]: On sale, excellent efficient block and much-needed card draw.

F6 [shop] remove_card_at_shop | source=plan
  HP 58->58 | Gold 174->174 | Deck 16->16
  deck_change: no deck change
  reasoning: Shop plan [2/3]: Removing a Strike increases the density of our better cards like Bouncing Flask and Backflip.

F6 [card_select] select_deck_card (option_index=0) | source=llm
  HP 58->58 | Gold 174->99 | Deck 16->15
  deck_change: lost Strike
  reasoning: Strikes are our weakest basic cards, especially since we have begun drafting poison (Deadly Poison, Bouncing Flask) as our main source of damage. Removing a Strike improves the consistency of drawing our core scaling cards and mitigation.
  strategic_note: Foundation plan: transition into a committed Poison build since we have Bouncing Flask and Deadly Poison. Prioritize survival with efficient block, AoE (if needed), and card draw to cycle our poison quickly. Avoid adding generic attacks that dilute the deck.

F6 [shop] buy_card (option_index=0) | source=plan
  HP 58->58 | Gold 99->47 | Deck 15->16
  deck_change: bought Ricochet
  reasoning: Shop plan [3/3]: Provides 12 damage and synergizes beautifully with Survivor and Hidden Daggers as a Sly card (plays for free on discard).

F6 [shop] close_shop_inventory | source=plan
  HP 58->58 | Gold 47->47 | Deck 16->16
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F6 [shop] proceed | source=auto
  HP 58->58 | Gold 47->47 | Deck 16->16
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F6 [map] choose_map_node (option_index=4) | source=llm
  HP 58->58 | Gold 47->47 | Deck 16->16
  deck_change: no deck change
  reasoning: The route recommends moving toward the Rest Site at c6,r6 to secure an early upgrade, which is crucial for strengthening the deck's foundation for future Act 1 challenges.
  strategic_note: Building a foundation deck by prioritizing card removal and early upgrades, focusing on solid damage cards to handle elites and high-value hallway fights while maintaining health.

F7 [rest_site] choose_rest_option (option_index=1, smith_card_index=9) | source=llm
  HP 58->58 | Gold 47->47 | Deck 16->16
  deck_change: upgraded Neutralize->Neutralize+
  reasoning: HP is high (58/70), so resting would waste most of the heal. Upgrading Neutralize to apply 2 Weak is a premium Act 1 upgrade that significantly improves damage mitigation against Elites and Bosses.
  strategic_note: Poison-based plan utilizing Bouncing Flask and Deadly Poison for scaling damage, while defending and applying Weak. Ricochet provides extra damage via Sly when discarded. Needs more block and card draw; avoid raw attacks.

F7 [rest_site] proceed | source=auto
  HP 58->58 | Gold 47->47 | Deck 16->16
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F7 [map] choose_map_node (option_index=2) | source=llm
  HP 58->58 | Gold 47->0 | Deck 16->16
  deck_change: no deck change
  reasoning: The route plan indicates moving toward a Monster node to build deck strength and earn gold before the upcoming Shop and mid-act encounters. The path is safe given my current HP.
  strategic_note: I am in the foundation stage, prioritizing strong early-game damage and defensive utility; I will focus on acquiring efficient attacks and block cards to stabilize before taking on elites.

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 47->60 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 53->53 | Gold 60->60 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 53->53 | Gold 60->60 | Deck 16->17
  deck_change: picked Flick-Flack
  reasoning: Flick-Flack provides desperately needed AoE for early hallway fights and synergizes perfectly with our discard outlets (Hidden Daggers, Survivor) to be played for free via its Sly mechanic.
  strategic_note: Foundation plan: use discard outlets to cheat out Sly cards for efficient upfront damage/AoE, while leaning on Bouncing Flask for boss scaling. Still looking for a cohesive scaling engine; prioritize cheap draw and card removal over narrow synergy pieces.

F8 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 53->53 | Gold 60->60 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F8 [map] choose_map_node (option_index=2) | source=llm
  HP 53->53 | Gold 60->0 | Deck 17->17
  deck_change: no deck change
  reasoning: I have 53 HP, which is sufficient to challenge an Act 1 Elite for scaling rewards. Taking the Elite now aligns with the 'Rest Site Buffers' strategy, as the RestSite at index 3 is available afterward to recover HP and upgrade cards.
  strategic_note: Building a foundation deck by prioritizing card removal and early upgrades, focusing on solid damage cards to handle elites and high-value hallway fights while maintaining health.

## Selected Replay Package (0 replays)
(no replay package available)

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F9(Phantasmal Gardener: )
- Core Combat Principles: F2(Toadpole: WIN), F4(Corpse Slug: WIN), F5(Sludge Spinner: WIN), F8(Two-Tailed Rat: WIN), F9(Phantasmal Gardener: )
- Deck Building Across the Run: F2(), F4(), F5(), F6(), F6(), F8()
- Map Routing and Path Planning: F1(), F1(), F2(), F2(), F3(), F4(), F5(), F6(), F6(), F7(), F8()
- Never Smith Upgraded Cards: F7()
- Rest Site and Event Decisions: F7()
- Silent - Combat Sequencing: F2(Toadpole: WIN), F4(Corpse Slug: WIN), F5(Sludge Spinner: WIN), F8(Two-Tailed Rat: WIN), F9(Phantasmal Gardener: )
- Silent - Draft and Shop Rules: F2(), F4(), F5(), F6(), F6(), F8()
- Silent - Route Priorities: F1(), F1(), F2(), F2(), F3(), F4(), F5(), F6(), F6(), F7(), F8()
- Sly Discard Synergies: F2(), F4(), F5(), F6(), F8()

## Dynamic Tools
- block_sufficiency_check: 21173 calls, 21173 successes
- poison_block_survival_plan: 6126 calls, 6126 successes
- poison_kill_and_survive_check: 20626 calls, 20626 successes
- poison_survival_analysis: 23036 calls, 21939 successes
- poison_turns_to_kill: 23079 calls, 21939 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.