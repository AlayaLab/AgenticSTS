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
Result: DEFEAT at Floor 3 (fitness: 60.1)
Combats won: 1/1
Run duration: 329.9s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: rely on strikes and defends while looking for early high-damage attacks and basic block. We have Silver Crucible, so the first 3 card rewards will be upgraded, making early combat much easier.
- [map] Foundation deck: leverage Silver Crucible to pick three high-impact upgraded cards from the first three combats, prioritizing a mix of upfront damage and solid block while remaining open to archetype-defining cards.
### F2
- [card_reward] Foundation plan: survive with frontload damage while looking for a core engine. Use Well-Laid Plans+ to retain key attacks or block for when they are needed. Prioritize high-impact damage next to handle early elites.

### Combat Decision Digest (1 combats)
F2 [monster] multi:Toadpole+Toadpole (6R, HP 70->69, loss=1, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Strike*2 | dealt=3 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R3[Toadpole: Atk(7)+Toadpole: Atk(3x3=9)]: Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=1
  R4[Toadpole: Buff+Toadpole: Atk(7)]: Strike(6dmg)->Strike->Neutralize(3dmg,1+Weak(1))->Strike(6dmg) | dealt=15 taken=0
  R5[Toadpole: Atk(3x3=9)]: Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R6[Toadpole: Atk(7)]: Strike | dealt=0 taken=0

### Non-combat Decisions (8 decisions)
F1 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Silver Crucible provides a massive early game tempo spike by upgrading the first 3 card rewards, allowing us to take harder paths and more Elites in Act 1. The trade-off of an empty chest is well worth the immediate power.
  strategic_note: Foundation deck: rely on strikes and defends while looking for early high-damage attacks and basic block. We have Silver Crucible, so the first 3 card rewards will be upgraded, making early combat much easier.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 70->70 | Gold 99->99 | Deck 12->12
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 70->70 | Gold 99->0 | Deck 12->12
  deck_change: no deck change
  reasoning: Starting the act with a hallway fight. With the Silver Crucible relic, my first three card rewards will be upgraded, so I want to hit three monster combats early to secure strong, upgraded foundation cards before encountering harder challenges or shops.
  strategic_note: Foundation deck: leverage Silver Crucible to pick three high-impact upgraded cards from the first three combats, prioritizing a mix of upfront damage and solid block while remaining open to archetype-defining cards.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 69->69 | Gold 99->109 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 69->69 | Gold 109->109 | Deck 12->12
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 69->69 | Gold 109->109 | Deck 12->12
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 69->69 | Gold 109->109 | Deck 12->13
  deck_change: picked Well-Laid Plans+
  reasoning: Well-Laid Plans+ is one of the most powerful and flexible cards in the game, allowing us to retain up to 2 cards every turn. Even though we urgently need damage for Act 1, an upgraded WLP is too strong to pass up and will fit perfectly into whatever engine we eventually build.
  strategic_note: Foundation plan: survive with frontload damage while looking for a core engine. Use Well-Laid Plans+ to retain key attacks or block for when they are needed. Prioritize high-impact damage next to handle early elites.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 69->69 | Gold 109->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Only path: Monster

## Selected Replay Package (0 replays)
(no replay package available)

## Triggered Skills This Run
- Core Combat Principles: F2(Toadpole: WIN), F3(Seapunk: )
- Deck Building Across the Run: F2()
- Map Routing and Path Planning: F1(), F1()
- Silent - Combat Sequencing: F2(Toadpole: WIN), F3(Seapunk: )
- Silent - Draft and Shop Rules: F2()
- Silent - Route Priorities: F1(), F1()

## Dynamic Tools
- block_sufficiency_check: 21589 calls, 21589 successes
- poison_block_survival_plan: 6542 calls, 6542 successes
- poison_kill_and_survive_check: 21042 calls, 21042 successes
- poison_survival_analysis: 23452 calls, 22355 successes
- poison_turns_to_kill: 23495 calls, 22355 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.