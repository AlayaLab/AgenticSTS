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
Result: DEFEAT at Floor 24 (fitness: 83.9)
Combats won: 14/14
Run duration: 4086.2s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation phase: Look for high-impact damage cards to overcome the bloated starter deck in early Act 1, and prioritize card removal at shops.
- [map] Foundation stage: focusing on securing efficient damage and block cards through early monster fights to stabilize the deck for Act 1 elites.
### F2
- [card_reward] Foundation plan: prioritizing poison scaling for the Act 1 Boss and beyond. Looking for cheap block, card draw (Acrobatics, Backflip), and secondary poison cards like Noxious Fumes or Deadly Poison to solidify the engine.
- [map] Foundation stage: prioritizing a 3-monster opening to draft core damage and block cards, stabilizing the deck's output before approaching elites or shops.
### F3
- [card_reward] Foundation plan: leaning into a Poison engine with Bouncing Flask and Deadly Poison to bypass the Soul Fysh's Intangible mechanic; prioritize block and more poison sources while looking for a Catalyst or more draw to cycle into poison stacks.
### F4
- [card_reward] Committed poison plan: use poison for damage and prioritize card draw (Acrobatics, Backflip) and block to cycle and survive while poison scales.
### F5
- [card_reward] Committed poison plan: apply poison early with Bouncing Flask and Deadly Poison, scale with Accelerant, then focus entirely on defense and draw to survive while passive damage kills. Need premium block and deck thinning; skip narrow attack synergies.
### F6
- [event] Foundation poison deck building around Bouncing Flask and Deadly Poison. Needs more block and card draw to safely play poison cards, and eventually Catalyst or more poison scaling for the boss.
- [map] Foundation stage: prioritizing a 3-monster opening to draft core damage and block cards, stabilizing the deck's output before approaching elites or shops.
### F7
- [card_reward] Committed poison plan: use block and draw to cycle into Bouncing Flask and Accelerant, relying on passive poison for damage. Needs more efficient block and deck thinning.
### F8
- [card_reward] Committed poison plan: rely on Bouncing Flask and Deadly Poison for scaling, enhanced by Accelerant. Defend and cycle with Backflip/Acrobatics. Use Ricochet + Boot synergy for massive free frontload damage by discarding it. Avoid adding more generic attacks; look for Noxious Fumes or strong block.
### F9
- [rest_site] Foundation poison deck: Bouncing Flask, Deadly Poison, and Accelerant are our win condition. We need more block and key upgrades (Accelerant, Flask) to scale better. Focus on safe poison stacking and prioritizing Accelerant.
### F11
- [map] Foundation stage: prioritizing elite rewards to secure scaling relics and damage before the boss, while maintaining enough HP to reach the late-act shop and rest site.
### F12
- [card_reward] Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs dex/block scaling or Catalyst; skip off-plan attacks and expensive cards.
### F13
- [card_reward] Committed poison plan: stack poison with Flask and Deadly Poison, then trigger with Accelerant while blocking. Use Expose to strip Artifact so poison lands cleanly. Needs premium block, card draw, and card removal for basic Strikes. Skip off-plan attacks.
### F14
- [card_reward] Committed Poison plan: cycle through the deck to apply Poison safely and burst it with Accelerant. Leverage discard outlets for Tingsha damage and to cheat out Ricochet. Avoid narrow attacks and focus on efficient draw, block, or more Poison/catalyst effects.
- [map] Foundation stage: prioritizing card removal and targeted purchases at this shop to refine the deck's output before the Act 1 boss, followed by a smith or rest depending on HP post-shop.
### F15
- [card_select] Committed poison plan: rely on Bouncing Flask, Deadly Poison, and Accelerant to kill enemies. Defend while passive poison ticks down. Keep thinning basic Strikes and prioritize block and discard synergies (Tingsha, Acrobatics).
### F16
- [rest_site] Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs a Smith on the core power or more block; skip raw attacks.
### F17
- [card_reward] Committed to a Poison/Discard hybrid plan: use discard outlets to trigger Tingsha and Sly cards for chip damage and filtering, while stacking poison and playing Accelerant for the kill. Needs more card draw, Tactician, and defensive scaling. Skip generic attacks.
### F18
- [event] Committed poison and discard hybrid deck: utilize Tools of the Trade and Tingsha for passive AoE damage, and stack poison with Bouncing Flask for boss scaling. Needs an energy relic or reliable block engine to survive long fights.
- [map] Foundation deck: currently focusing on efficient block-first play while hunting for a scaling engine like poison or shivs. Priority is surviving Act 2's high damage through card rewards and a strategic shop visit; avoid Elites until a clear win condition is established.
### F19
- [card_reward] Committed poison/discard plan: survive with block and Tingsha passive damage while setting up Bouncing Flask + Accelerant for the kill. Needs card removal and more reliable draw/discard; skip generic attacks.
### F20
- [card_reward] Committed Hybrid Poison/Discard plan: use discard outlets to cycle deck, trigger Tingsha, and play Sly cards for free frontload/AoE. Save poison (Flask, Deadly Poison, Accelerant) for scaling damage against bosses. Needs more draw/energy and poison mitigation (block).
### F22
- [hand_select] Prioritizing full block against a high-strength enemy to conserve HP.
- [card_reward] Hybrid poison/discard plan: use discard outlets to trigger Sly cards and Tingsha for damage, while stacking poison for boss scaling. Retain Piercing Wail with Well-Laid Plans to neutralize multi-hit attacks. Prioritize card removal and upgrades.
### F23
- [hand_select] Sly cards are best used as discard fodder to cheat energy costs.
- [card_reward] Committed discard/poison hybrid. Prioritize upgrading discard outlets and finding more Acrobatics/Tactician to fuel Tingsha and Sly cards, while using poison to scale boss damage.

### Combat Decision Digest (15 combats)
F2 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 56->48, loss=8, WIN)
  R1[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Defend*2->Strike | dealt=0 taken=0
  R2[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Neutralize->Strike*2->Survivor | dealt=15 taken=0
  R3[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Defend*2->Strike | dealt=0 taken=8
  R4[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Neutralize->Strike->Defend->Survivor | dealt=6 taken=0
  R5[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Strike*2 | dealt=0 taken=0

F3 [monster] multi:Toadpole+Toadpole (4R, HP 48->48, loss=0, WIN)
  R1[Toadpole: Buff+Toadpole: Atk(7)]: Neutralize->Defend->Bouncing Flask | dealt=3 taken=0
  R2[Toadpole: Atk(3x3=9)+Toadpole: Buff]: Defend*2->Strike | dealt=6 taken=0
  R3[Toadpole: Atk(7)]: Survivor->Strike*2 | dealt=12 taken=0
  R4[Toadpole: Buff]: Neutralize->Strike->Bouncing Flask | dealt=9 taken=0

F4 [monster] Sludge Spinner (4R, HP 48->48, loss=0, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Defend*2->Strike | dealt=6 taken=0
  R2[Sludge Spinner: Atk(11)]: Neutralize->Strike->Defend->Survivor | dealt=12 taken=0
  R3[Sludge Spinner: Atk(6), Buff]: Defend*2->Deadly Poison | dealt=0 taken=0
  R4[Sludge Spinner: Atk(11), Debuff]: Strike | dealt=0 taken=0

F5 [monster] multi:Calcified Cultist+Damp Cultist (4R, HP 48->45, loss=3, WIN)
  R1[Calcified Cultist: Buff+Damp Cultist: Buff]: Deadly Poison->Strike*2 | dealt=18 taken=0
  R2[Calcified Cultist: Atk(9)+Damp Cultist: Atk(1)]: Strike->Defend*2 | dealt=29 taken=0
  R3[Calcified Cultist: Atk(11)]: Neutralize->Defend->Bouncing Flask | dealt=3 taken=3
  R4[Calcified Cultist: Atk(13)]: Neutralize->Defend*2->Strike | dealt=9 taken=0

F7 [monster] Sewer Clam (5R, HP 37->33, loss=4, WIN)
  R1[Sewer Clam: Atk(10)]: Deadly Poison->Defend->Survivor | dealt=0 taken=0
  R2[Sewer Clam: Buff]: Defend*2->Neutralize->Strike | dealt=5 taken=0
  R3[Sewer Clam: Atk(14)]: Acrobatics->Defend*2 | dealt=0 taken=4
  R4[Sewer Clam: Buff]: Neutralize->Accelerant->Defend->Survivor | dealt=3 taken=0
  R5[Sewer Clam: Atk(18)]: Bouncing Flask->Deadly Poison | dealt=0 taken=0

F8 [monster] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (6R, HP 33->15, loss=18, WIN)
  R1[Two-Tailed Rat: Debuff+Two-Tailed Rat: Atk(8)+Two-Tailed Rat: Atk(6)]: Defend*3 | dealt=0 taken=0
  R2[Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Atk(8)]: Accelerant->Neutralize->Deadly Poison->Strike | dealt=5 taken=12
  R3[Two-Tailed Rat: Summon+Two-Tailed Rat: Debuff]: Strike*2->Backflip | dealt=0 taken=0
  R4[Two-Tailed Rat: Summon]: Neutralize->Backflip->Strike->Defend | dealt=11 taken=0
  R5[Two-Tailed Rat: Atk(6)+Two-Tailed Rat: Atk(6)]: Strike*2->Deadly Poison | dealt=0 taken=6
  R6[Two-Tailed Rat: Atk(8)]: Strike->Survivor->Defend | dealt=6 taken=0

F12 [elite] Skulking Colony (5R, HP 46->41, loss=5, WIN)
  R1[Skulking Colony: Atk(12)]: Neutralize->Defend*2->Acrobatics | dealt=5 taken=0
  R2[Skulking Colony: Atk(14), Defend]: Accelerant->Ricochet | dealt=15 taken=10
  R3[Skulking Colony: Atk(9), Buff]: Bouncing Flask->Survivor | dealt=0 taken=0
  R4[Skulking Colony: Atk(9x2=18)]: Acrobatics->Backflip->Survivor | dealt=0 taken=3
  R5[Skulking Colony: Atk(14)]: Deadly Poison->Strike->Defend | dealt=6 taken=0

F13 [monster] Gremlin Merc (3R, HP 41->41, loss=0, WIN)
  R1[Gremlin Merc: Atk(7x2=14)]: Neutralize->Survivor->Ricochet->Defend->Deadly Poison | dealt=25 taken=0
  R2[Gremlin Merc: Atk(6x2=12), Debuff]: Strike*3 | dealt=14 taken=0
  R3[Sneaky Gremlin: Atk(9)+Fat Gremlin: Escape]: Strike->Bouncing Flask | dealt=4 taken=0

F14 [monster] Fossil Stalker (2R, HP 41->41, loss=0, WIN)
  R1[Fossil Stalker: Atk(12)]: Neutralize->Backflip->Defend->Expose->Strike | dealt=14 taken=0
  R2[Fossil Stalker: Atk(9), Debuff]: Strike->Survivor->Ricochet->Defend | dealt=9 taken=0

F17 [boss] Soul Fysh (9R, HP 65->35, loss=30, WIN)
  R1[Soul Fysh: StatusCard(2)]: Expose->Acrobatics->Ricochet->Follow Through->Deadly Poison | dealt=20 taken=0
  R2[Soul Fysh: Atk(16)]: Backflip->Prepared->Ultimate Defend->Accelerant | dealt=0 taken=0
  R3[Soul Fysh: Atk(7), StatusCard(1)]: Neutralize->Strike->Defend*2 | dealt=11 taken=0
  R4[Soul Fysh: Buff]: Acrobatics->Backflip->Neutralize->Strike | dealt=11 taken=0
  R5[Soul Fysh: Atk(11), Debuff]: Defend*2->Survivor | dealt=0 taken=0
  R6[Soul Fysh: StatusCard(2)]: Bouncing Flask->Beckon | dealt=0 taken=6
  R7[Soul Fysh: Atk(24)]: Deadly Poison->Beckon*2 | dealt=0 taken=24
  R8[Soul Fysh: Atk(10), StatusCard(1)]: Follow Through->Deadly Poison->Ultimate Defend | dealt=7 taken=0
  R9[Soul Fysh: Buff]: Beckon*3 | dealt=0 taken=0

F19 [monster] Tunneler (7R, HP 71->58, loss=13, WIN)
  R1[Tunneler: Atk(13)]: Expose->Follow Through->Backflip->Defend | dealt=20 taken=0
  R2[Tunneler: Buff, Defend]: Neutralize->Prepared->Strike->Survivor | dealt=17 taken=0
  R3[Tunneler: Atk(23)]: Ultimate Defend->Defend->Acrobatics | dealt=0 taken=0
  R4[Tunneler: Atk(23)]: Acrobatics->Prepared->Survivor->Defend | dealt=0 taken=10
  R5[Tunneler: Atk(23)]: Defend*3 | dealt=0 taken=3
  R6[Tunneler: Atk(23)]: Neutralize->Ultimate Defend->Backflip->Tools of the Trade->Ricochet | dealt=5 taken=0
  R7[Tunneler: Atk(13)]: Prepared->Follow Through | dealt=0 taken=0

F20 [monster] Thieving Hopper (3R, HP 58->58, loss=0, WIN)
  R1[Thieving Hopper: Atk(17), CardDebuff]: Bouncing Flask->Survivor->Defend | dealt=0 taken=0
  R2[Thieving Hopper: Buff]: Expose->Backflip->Acrobatics->Neutralize->Prepared->Strike*2 | dealt=23 taken=0
  R3[Thieving Hopper: Atk(21)]: Ultimate Defend->Accelerant->Ricochet | dealt=20 taken=0

F22 [monster] Louse Progenitor (5R, HP 58->50, loss=8, WIN)
  R1[Louse Progenitor: Atk(9), Debuff]: Backflip->Neutralize->Expose->Well-Laid Plans->Tools of the Trade->Ricochet | dealt=5 taken=0
  R2[Louse Progenitor: Defend, Buff]: Bouncing Flask->Accelerant | dealt=0 taken=0
  R3[Louse Progenitor: Atk(19)]: Acrobatics->Flick-Flack+->Prepared->Survivor->Defend->Flick-Flack+ | dealt=0 taken=4
  R4[Louse Progenitor: Atk(14), Debuff]: Follow Through->Backflip->Defend | dealt=14 taken=4
  R5[Louse Progenitor: Defend, Buff]: Neutralize->Deadly Poison->Ultimate Defend->Defend | dealt=5 taken=0

F23 [monster] Spiny Toad (5R, HP 50->29, loss=21, WIN)
  R1[Spiny Toad: Buff]: Expose->Neutralize->Prepared->Backflip->Tools of the Trade->Well-Laid Plans | dealt=5 taken=0
  R2[Spiny Toad: Atk(23)]: Accelerant->Survivor->Defend->Ricochet | dealt=0 taken=10
  R3[Spiny Toad: Atk(17)]: Piercing Wail->Bouncing Flask->Flick-Flack+ | dealt=0 taken=11
  R4[Spiny Toad: Buff]: Strike*2->Defend | dealt=12 taken=0
  R5[Spiny Toad: Atk(23)]: Ultimate Defend->Survivor | dealt=0 taken=0

F24 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (7R, HP 29->0, loss=29, LOSS)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Ultimate Defend->Follow Through->Backflip->Expose->Prepared | dealt=14 taken=0
  R2[Bowlbug (Rock): Stun+Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Defend->Strike*2->Prepared | dealt=12 taken=3
  R3[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Neutralize->Acrobatics->Flick-Flack+->Strike->Defend | dealt=6 taken=1
  R4[Bowlbug (Rock): Atk(15)+Slumbering Beetle: Atk(16), Buff]: Piercing Wail->Ultimate Defend->Strike | dealt=6 taken=8
  R5[Bowlbug (Rock): Stun+Slumbering Beetle: Atk(18), Buff]: Neutralize->Acrobatics->Flick-Flack+->Backflip->Defend | dealt=5 taken=0
  R6[Bowlbug (Rock): Atk(15)+Slumbering Beetle: Atk(20), Buff]: Defend*3 | dealt=0 taken=5
  R7[Bowlbug (Rock): Stun+Slumbering Beetle: Atk(22), Buff]: Prepared*2->Defend->Tools of the Trade->Strike | dealt=12 taken=0

### Non-combat Decisions (113 decisions)
F1 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=routing,deck_building) | source=llm
  HP 56->56 | Gold 99->99 | Deck 12->14
  deck_change: added Defend, Strike
  reasoning: Large Capsule provides 2 random relics, which is a massive boost to overall run power. While adding a Strike and Defend dilutes the deck and slows down our early cycling, the long-term value of two relics significantly outweighs the downside of two extra starter cards.
  strategic_note: Foundation phase: Look for high-impact damage cards to overcome the bloated starter deck in early Act 1, and prioritize card removal at shops.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 14->14
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=1) | source=llm
  HP 56->56 | Gold 99->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Starting with the standard 3-monster opening as recommended by expert knowledge to secure early card drafts and build a foundation before hitting events or elites.
  strategic_note: Foundation stage: focusing on securing efficient damage and block cards through early monster fights to stabilize the deck for Act 1 elites.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 99->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 108->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim potion: Vulnerable Potion

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 108->108 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 48->48 | Gold 108->108 | Deck 14->15
  deck_change: picked Bouncing Flask
  reasoning: Bouncing Flask provides a massive amount of damage over time and is highly recommended against the Act 1 boss, Soul Fysh, whose Intangible mechanic makes direct damage difficult. It serves as our first scaling poison piece.
  strategic_note: Foundation plan: prioritizing poison scaling for the Act 1 Boss and beyond. Looking for cheap block, card draw (Acrobatics, Backflip), and secondary poison cards like Noxious Fumes or Deadly Poison to solidify the engine.

F2 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 48->48 | Gold 108->108 | Deck 15->15
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F2 [map] choose_map_node (option_index=0) | source=llm
  HP 48->48 | Gold 108->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the 'Strict 3-Monster Open' strategy to secure vital early card drafts and gold before hitting unknowns or shops. Silent needs a solid foundation of damage and block to survive later Act 1 elites.
  strategic_note: Foundation stage: prioritizing a 3-monster opening to draft core damage and block cards, stabilizing the deck's output before approaching elites or shops.

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 108->119 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 119->119 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] choose_reward_card (option_index=2) | source=llm
  HP 48->48 | Gold 119->119 | Deck 15->16
  deck_change: picked Deadly Poison
  reasoning: Deadly Poison reinforces the scaling damage started by Bouncing Flask and is the optimal strategy for the upcoming Soul Fysh boss, whose Intangible mechanic is bypassed by Poison. While Cloak and Dagger is a high-value card and works with Parrying Shield, committing to a Poison foundation early provides a clearer win condition for Act 1 and beyond.
  strategic_note: Foundation plan: leaning into a Poison engine with Bouncing Flask and Deadly Poison to bypass the Soul Fysh's Intangible mechanic; prioritize block and more poison sources while looking for a Catalyst or more draw to cycle into poison stacks.

F3 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 48->48 | Gold 119->119 | Deck 16->16
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F3 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 119->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Monster

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 119->127 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 127->127 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim potion: Fire Potion

F4 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 127->127 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F4 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=deck_building,combat) | source=llm
  HP 48->48 | Gold 127->127 | Deck 16->17
  deck_change: picked Acrobatics
  reasoning: Our deck has 16 cards due to Large Capsule adding extra basics. We already have Bouncing Flask and Deadly Poison for our poison damage, but we severely lack card draw to find them and cycle past our basics. Acrobatics provides excellent cycling.
  strategic_note: Committed poison plan: use poison for damage and prioritize card draw (Acrobatics, Backflip) and block to cycle and survive while poison scales.

F4 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 48->48 | Gold 127->127 | Deck 17->17
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F4 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 127->0 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Monster

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 127->139 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 45->45 | Gold 139->139 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] choose_reward_card (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 45->45 | Gold 139->139 | Deck 17->18
  deck_change: picked Accelerant
  reasoning: Accelerant is a rare power that doubles poison output per turn, making it an incredible scaling engine for our Bouncing Flask and Deadly Poison. This perfectly sets up our damage plan for the Soul Fysh boss and the rest of the run.
  strategic_note: Committed poison plan: apply poison early with Bouncing Flask and Deadly Poison, scale with Accelerant, then focus entirely on defense and draw to survive while passive damage kills. Need premium block and deck thinning; skip narrow attack synergies.

F5 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 45->45 | Gold 139->139 | Deck 18->18
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 45->45 | Gold 139->139 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Unknown

F6 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 45->37 | Gold 139->139 | Deck 18->18
  deck_change: no deck change
  reasoning: 8 HP is a very efficient price for a random relic. Getting a random forgotten card can pollute the deck with an off-class card that functions like a curse, so I will take the relic.
  strategic_note: Foundation poison deck building around Bouncing Flask and Deadly Poison. Needs more block and card draw to safely play poison cards, and eventually Catalyst or more poison scaling for the boss.

F6 [event] choose_event_option (option_index=0) | source=auto
  HP 37->37 | Gold 139->139 | Deck 18->18
  deck_change: no deck change
  reasoning: Only option: Proceed

F6 [map] choose_map_node (option_index=2) | source=llm
  HP 37->37 | Gold 139->0 | Deck 18->18
  deck_change: no deck change
  reasoning: Continuing the 3-monster opening strategy to draft core damage and block. My HP (37/70) is too low to safely path into an Elite (node 1) right now without further deck stabilization. Monster fights provide the card rewards needed to prepare for the later stages of the act.
  strategic_note: Foundation stage: prioritizing a 3-monster opening to draft core damage and block cards, stabilizing the deck's output before approaching elites or shops.

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 139->150 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 150->150 | Deck 18->18
  deck_change: no deck change
  reasoning: Claim potion: Regen Potion

F7 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 33->33 | Gold 150->150 | Deck 18->18
  deck_change: no deck change
  reasoning: Open card reward

F7 [card_reward] choose_reward_card (option_index=2, note_scope=run, note_triggers=deck_building,combat) | source=llm
  HP 33->33 | Gold 150->150 | Deck 18->19
  deck_change: picked Backflip
  reasoning: Backflip provides essential block and card draw, allowing us to cycle faster to our core poison cards (Bouncing Flask, Deadly Poison, Accelerant) while mitigating incoming damage.
  strategic_note: Committed poison plan: use block and draw to cycle into Bouncing Flask and Accelerant, relying on passive poison for damage. Needs more efficient block and deck thinning.

F7 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 33->33 | Gold 150->150 | Deck 19->19
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F7 [map] choose_map_node (option_index=0) | source=auto
  HP 33->33 | Gold 150->0 | Deck 19->19
  deck_change: no deck change
  reasoning: Only path: Monster

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 150->158 | Deck 19->19
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 158->158 | Deck 19->19
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 15->15 | Gold 158->158 | Deck 19->20
  deck_change: picked Ricochet
  reasoning: Ricochet deals 3 damage 4 times, which perfectly synergizes with our relic The Boot (increasing each hit to 5 damage for a total of 20 damage). Since we already have Survivor and Acrobatics to discard it, it will frequently be a 0-cost 20-damage frontload nuke, which we desperately need for survival at 15 HP while our poison scales.
  strategic_note: Committed poison plan: rely on Bouncing Flask and Deadly Poison for scaling, enhanced by Accelerant. Defend and cycle with Backflip/Acrobatics. Use Ricochet + Boot synergy for massive free frontload damage by discarding it. Avoid adding more generic attacks; look for Noxious Fumes or strong block.

F8 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 15->15 | Gold 158->158 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 15->15 | Gold 158->158 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F9 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 15->36 | Gold 158->158 | Deck 20->20
  deck_change: no deck change
  reasoning: HP is critically low at 15. We have an upcoming Elite at F12, so we must Rest to ensure we survive.
  strategic_note: Foundation poison deck: Bouncing Flask, Deadly Poison, and Accelerant are our win condition. We need more block and key upgrades (Accelerant, Flask) to scale better. Focus on safe poison stacking and prioritizing Accelerant.

F9 [rest_site] proceed | source=auto
  HP 36->36 | Gold 158->158 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 36->36 | Gold 158->158 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 36->36 | Gold 158->195 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 36->46 | Gold 195->195 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Pear

F10 [treasure] proceed | source=random
  HP 46->46 | Gold 195->195 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=0) | source=auto
  HP 46->46 | Gold 195->195 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Unknown

F11 [treasure] proceed | source=random
  HP 46->46 | Gold 195->195 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F11 [treasure] open_chest | source=random
  HP 46->46 | Gold 195->228 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F11 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 46->46 | Gold 228->228 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Bowler Hat

F11 [treasure] proceed | source=random
  HP 46->46 | Gold 228->228 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 46->46 | Gold 228->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Current HP is 46, which is above the 40 HP safety threshold for Silent to attempt an Act 1 Elite. Taking this fight now allows for a relic and better card rewards to prepare for the Boss, especially since a Rest Site and Shop are available later in the path to recover and spend the 228 gold.
  strategic_note: Foundation stage: prioritizing elite rewards to secure scaling relics and damage before the boss, while maintaining enough HP to reach the late-act shop and rest site.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 228->269 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 33 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 269->269 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim relic: Tingsha

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 269->269 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 41->41 | Gold 269->269 | Deck 20->20
  deck_change: no deck change
  reasoning: Our deck is strongly committed to a poison engine with Flask, Deadly Poison, and Accelerant, and has a minor discard synergy with Tingsha. Precise Cut is poor with our high card draw, Phantom Blades does nothing without Shivs, and Blur provides too little block for 1 energy without Dexterity. Skipping keeps the deck leaner to cycle back to our poison and draw cards.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe turns, then defend while passive poison kills. Needs dex/block scaling or Catalyst; skip off-plan attacks and expensive cards.

F12 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 41->41 | Gold 269->269 | Deck 20->20
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 269->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Monster

F13 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 249->249 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F13 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 41->41 | Gold 249->249 | Deck 20->21
  deck_change: picked Expose
  reasoning: The expert knowledge suggests taking exactly one copy of Expose. In a committed Poison deck, stripping Artifact is crucial so that Bouncing Flask and Deadly Poison can actually apply their stacks. Since it costs 0 and Exhausts, it is a very low-liability inclusion that solves specific problematic enemies like Spheric Guardian or Automaton.
  strategic_note: Committed poison plan: stack poison with Flask and Deadly Poison, then trigger with Accelerant while blocking. Use Expose to strip Artifact so poison lands cleanly. Needs premium block, card draw, and card removal for basic Strikes. Skip off-plan attacks.

F13 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 41->41 | Gold 249->249 | Deck 21->21
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F13 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 249->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Monster

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 249->261 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 261->261 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F14 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 41->41 | Gold 261->261 | Deck 21->21
  deck_change: no deck change
  reasoning: Our deck is currently committed to a Poison engine with Accelerant, Bouncing Flask, and Deadly Poison. We also have some discard synergy with Tingsha and Ricochet. Adding a random Shiv generator or Anticipate will only bloat the deck and make it harder to draw our core scaling cards. Soul Fysh is the boss, and Poison is the best counter since it bypasses Intangible, whereas Shivs lose significant value.
  strategic_note: Committed Poison plan: cycle through the deck to apply Poison safely and burst it with Accelerant. Leverage discard outlets for Tingsha damage and to cheat out Ricochet. Avoid narrow attacks and focus on efficient draw, block, or more Poison/catalyst effects.

F14 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 41->41 | Gold 261->261 | Deck 21->21
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F14 [map] choose_map_node (option_index=1) | source=llm
  HP 41->41 | Gold 261->261 | Deck 21->21
  deck_change: no deck change
  reasoning: With 261 gold, the shop is the highest value node to prepare for the Act 1 boss. It allows for card removal and potential relic/card purchases to shore up weaknesses before the final rest site.
  strategic_note: Foundation stage: prioritizing card removal and targeted purchases at this shop to refine the deck's output before the Act 1 boss, followed by a smith or rest depending on HP post-shop.

F15 [shop] remove_card_at_shop | source=plan
  HP 41->41 | Gold 261->261 | Deck 21->21
  deck_change: no deck change
  reasoning: Shop plan [1/4]: We have 6 Strikes due to Large Capsule; removing them is top priority to draw our poison and discard engines faster.

F15 [card_select] select_deck_card (option_index=0) | source=llm
  HP 41->41 | Gold 261->186 | Deck 21->20
  deck_change: lost Strike
  reasoning: The deck's win condition is clearly poison (Bouncing Flask, Deadly Poison, Accelerant). Strikes are the weakest cards in this setup as they don't contribute to poison and take up valuable draw that could find block or poison pieces.
  strategic_note: Committed poison plan: rely on Bouncing Flask, Deadly Poison, and Accelerant to kill enemies. Defend while passive poison ticks down. Keep thinning basic Strikes and prioritize block and discard synergies (Tingsha, Acrobatics).

F15 [shop] buy_card (option_index=5) | source=plan
  HP 41->41 | Gold 186->98 | Deck 20->21
  deck_change: bought Ultimate Defend
  reasoning: Shop plan [2/4]: Provides much-needed premium block density for surviving Soul Fysh's 16 and 24 damage swings.

F15 [shop] buy_card (option_index=2) | source=plan
  HP 41->41 | Gold 98->49 | Deck 21->22
  deck_change: bought Prepared
  reasoning: Shop plan [3/4]: Crucial 0-cost draw and discard outlet to enable Tingsha damage and trigger Sly on Ricochet.

F15 [shop] buy_card (option_index=0) | source=plan
  HP 41->41 | Gold 49->23 | Deck 22->23
  deck_change: bought Follow Through
  reasoning: Shop plan [4/4]: On sale, this is extremely efficient frontload damage (14 for 1 energy) since Ring of the Snake makes it trivial to meet the hand size requirement on turn 1.

F15 [shop] close_shop_inventory | source=plan
  HP 41->41 | Gold 23->23 | Deck 23->23
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F15 [shop] proceed | source=auto
  HP 41->41 | Gold 23->23 | Deck 23->23
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 23->23 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 41->65 | Gold 23->23 | Deck 23->23
  deck_change: no deck change
  reasoning: With 41/80 HP (51%) and the Act 1 Boss immediately next, healing 24 HP is necessary to ensure survival. While a Relic from Dig or a Smith would be nice, the risk of dying to the boss is too high.
  strategic_note: Committed poison plan: retain poison and draw pieces, stack poison on safe burst turns, then defend while passive poison kills. Needs a Smith on the core power or more block; skip raw attacks.

F16 [rest_site] proceed | source=auto
  HP 65->65 | Gold 23->23 | Deck 23->23
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 65->65 | Gold 23->0 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 23->116 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 116->116 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Speed Potion

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 35->35 | Gold 116->116 | Deck 23->23
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] choose_reward_card (option_index=0) | source=llm
  HP 35->35 | Gold 116->116 | Deck 23->24
  deck_change: picked Tools of the Trade
  reasoning: Tools of the Trade provides a consistent discard at the start of every turn, which perfectly synergizes with Tingsha for free damage and helps cycle to find our Poison cards and Accelerant. It also triggers Sly on Ricochet.
  strategic_note: Committed to a Poison/Discard hybrid plan: use discard outlets to trigger Tingsha and Sly cards for chip damage and filtering, while stacking poison and playing Accelerant for the kill. Needs more card draw, Tactician, and defensive scaling. Skip generic attacks.

F17 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 35->35 | Gold 116->116 | Deck 24->24
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 35->71 | Gold 116->116 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 71->71 | Gold 116->116 | Deck 24->24
  deck_change: no deck change
  reasoning: Pael's Legion provides massive burst block without requiring additional energy, which is perfect for surviving heavy Act 2 attacks on 3 base energy. Pael's Growth (Clone) is strong but might be too energy-intensive to utilize effectively right now.
  strategic_note: Committed poison and discard hybrid deck: utilize Tools of the Trade and Tingsha for passive AoE damage, and stack poison with Bouncing Flask for boss scaling. Needs an energy relic or reliable block engine to survive long fights.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 71->71 | Gold 116->116 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=1) | source=llm
  HP 71->71 | Gold 116->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Following the recommended path (Monster at c2, r1) to gain gold and card rewards early in Act 2. This route leads toward a shop where I can spend gold and potentially remove cards, followed by a rest site for stabilization or upgrades. Act 2 hallway fights are dangerous, but necessary to scale for the boss.
  strategic_note: Foundation deck: currently focusing on efficient block-first play while hunting for a scaling engine like poison or shivs. Priority is surviving Act 2's high damage through card rewards and a strategic shop visit; avoid Elites until a clear win condition is established.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 116->124 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 124->124 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim potion: Radiant Tincture

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 124->124 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] choose_reward_alternative (option_index=0) | source=llm
  HP 58->58 | Gold 124->124 | Deck 24->24
  deck_change: no deck change
  reasoning: None of these cards significantly improve our deck. We are building a Poison/Discard engine and already have a bloated deck (24 cards). Skip keeps the deck lean to draw our core cards (Flask, Accelerant, Discard tools) faster.
  strategic_note: Committed poison/discard plan: survive with block and Tingsha passive damage while setting up Bouncing Flask + Accelerant for the kill. Needs card removal and more reliable draw/discard; skip generic attacks.

F19 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 58->58 | Gold 124->124 | Deck 24->24
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 124->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 124->134 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim gold: 8 Gold

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 134->134 | Deck 23->23
  deck_change: no deck change
  reasoning: Claim potion: Potion of Binding

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 134->134 | Deck 23->24
  deck_change: picked Bouncing Flask
  reasoning: Claim specialcard: Take your stolen card back.

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 58->58 | Gold 134->134 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 58->58 | Gold 134->134 | Deck 24->25
  deck_change: picked Flick-Flack+
  reasoning: Flick-Flack++ has Sly, meaning it plays for free when discarded. With Tools of the Trade, Acrobatics, Prepared, Survivor, and Tingsha, we have a strong discard engine. This provides much-needed AoE for Act 2 hallways without costing energy.
  strategic_note: Committed Hybrid Poison/Discard plan: use discard outlets to cycle deck, trigger Tingsha, and play Sly cards for free frontload/AoE. Save poison (Flask, Deadly Poison, Accelerant) for scaling damage against bosses. Needs more draw/energy and poison mitigation (block).

F20 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 58->58 | Gold 134->134 | Deck 25->25
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 134->134 | Deck 25->25
  deck_change: no deck change
  reasoning: Only path: Shop

F21 [shop] buy_card (option_index=4) | source=plan
  HP 58->58 | Gold 134->96 | Deck 25->26
  deck_change: bought Well-Laid Plans
  reasoning: Shop plan [1/1]: On sale and one of the best utility powers for Silent. It allows us to hold discard outlets (Acrobatics, Survivor) until we draw Sly cards, or hold Sly cards until we have an outlet.

F21 [shop] close_shop_inventory | source=plan
  HP 58->58 | Gold 96->96 | Deck 26->26
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F21 [shop] proceed | source=auto
  HP 58->58 | Gold 96->96 | Deck 26->26
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 58->58 | Gold 96->0 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: Monster

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 96->104 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 50->50 | Gold 104->104 | Deck 26->26
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] choose_reward_card (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 50->50 | Gold 104->104 | Deck 26->27
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is a massive defensive tool against the Act 2 boss, Knowledge Demon, which relies on heavy multi-hit attacks. With Well-Laid Plans in the deck, we can easily retain it for the exact turn we need it.
  strategic_note: Hybrid poison/discard plan: use discard outlets to trigger Sly cards and Tingsha for damage, while stacking poison for boss scaling. Retain Piercing Wail with Well-Laid Plans to neutralize multi-hit attacks. Prioritize card removal and upgrades.

F22 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 50->50 | Gold 104->104 | Deck 27->27
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F22 [map] choose_map_node (option_index=0) | source=auto
  HP 50->50 | Gold 104->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Monster

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 104->117 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 29->29 | Gold 117->117 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] choose_reward_card (option_index=1) | source=llm
  HP 29->29 | Gold 117->117 | Deck 27->28
  deck_change: picked Prepared
  reasoning: With Tingsha and Sly cards (Flick-Flack, Ricochet), 0-cost discard outlets are essentially free damage and combo enablers. Even unupgraded, another Prepared helps trigger these effects consistently.
  strategic_note: Committed discard/poison hybrid. Prioritize upgrading discard outlets and finding more Acrobatics/Tactician to fuel Tingsha and Sly cards, while using poison to scale boss damage.

F23 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 29->29 | Gold 117->117 | Deck 28->28
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F23 [map] choose_map_node (option_index=0) | source=auto
  HP 29->29 | Gold 117->0 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Monster

## Selected Replay Package (4 replays)
[Selected: run_combat] multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (F8, monster)
Historical: loss=18 vs historical avg=6.6+/-6.3 (z=1.8, WORSE_THAN_USUAL, n=36)
## Combat Replay: vs multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (Floor 8, monster)
Relics: Ring of the Snake, Large Capsule, Shovel, Parrying Shield, The Boot
Deck (19): Defend x6, Strike x6, Accelerant, Acrobatics, Backflip, Bouncing Flask, Deadly Poison, Neutralize, Survivor
Enemies: Two-Tailed Rat HP=17/17, Two-Tailed Rat HP=19/19, Two-Tailed Rat HP=18/18

### Round 1
Intent: Two-Tailed Rat: Debuff, Two-Tailed Rat: Attack(8), Two-Tailed Rat: Attack(6)
  turn_end

### Round 2
Agent plan (hypothesis): Accelerant is active. Bouncing Flask will deal massive damage next turn.
Intent: Two-Tailed Rat: Attack(6), Two-Tailed Rat: Attack(6), Two-Tailed Rat: Attack(8)
  turn_end

### Round 3
Agent plan (hypothesis): Saved HP by preventing a summon. Accelerant will help kill the remaining rat next turn with Poison.
Intent: Two-Tailed Rat: Summon, Two-Tailed Rat: Debuff
  turn_end

### Round 4
Agent plan (hypothesis): If you draw Bouncing Flask, play it for 18 poison damage (lethal). If Deadly Poison, play it and Strike.
Agent plan (hypothesis): Kill the summoned rat quickly or finish off this one.
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
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (Floor 8, monster)
Relics: Ring of the Snake, Hefty Tablet, Sword of Stone
Deck (18): Defend x5, Strike x5, Assassinate, Dagger Spray, Fan of Knives+, Injury, Leading Strike, Neutralize, Strangle, Survivor
Enemies: Two-Tailed Rat HP=17/17, Two-Tailed Rat HP=19/19, Two-Tailed Rat HP=21/21

### Round 1
Intent: Two-Tailed Rat: Attack(6), Two-Tailed Rat: Debuff, Two-Tailed Rat: Attack(8)
  Injury
  turn_end

### Round 2
Intent: Two-Tailed Rat: Attack(8), Two-Tailed Rat: Attack(6)
  cards: Fan of Knives+, Shiv, Shiv, Shiv, Shiv, dealt=12, taken=0
## Combat Analytics: multi:Two-Tailed Rat+Two-Tailed Rat+Two-Tailed Rat (WIN - 2 rounds)

Unattributed damage (power/passive effects): 20
  Per round: R1:8 R2:12

[Selected: elite] Skulking Colony (F12, elite)
Historical: loss=5 vs historical avg=16.0+/-12.8 (z=-0.9, TYPICAL, n=25)
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
Agent plan (hypothesis): Accelerant is active. Focus on full defense next turn (Backflip/Defends) while waiting to draw Poison.
Intent: Skulking Colony: Attack(14), Defend
  turn_end

### Round 3
Agent plan (hypothesis): Poison is ticking well now. Focus entirely on blocking next turn.
Intent: Skulking Colony: Attack(9), Buff
  Strike
  turn_end

### Round 4
Agent plan (hypothesis): Look for Neutralize and block cards to survive this turn.
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
Comparator (recent same-enemy comparator):
## Combat Replay: vs Skulking Colony (Floor 13, elite)
Relics: Ring of the Snake, Neow's Bones, Hefty Tablet, Precarious Shears, Book of Five Rings
Deck (20): Defend x5, Strike x4, Backflip, Blade of Ink, Cloak and Dagger, Clumsy, Dagger Throw, Expose, Leading Strike, Neutralize+, Precise Cut, Ricochet, Survivor
Enemies: Skulking Colony HP=70/70

### Round 1
Intent: Skulking Colony: Attack(12)
  turn_end

### Round 2
Intent: Skulking Colony: Attack(14), Defend
  turn_end
    exhausted: Shiv [0费]：Deal 4 damage. Exhaust.

### Round 3
Intent: Skulking Colony: Attack(9), Buff
  Ricochet
  turn_end

### Round 4
Intent: Skulking Colony: Attack(6x2=12)
  Strike
  turn_end

### Round 5
Intent: Skulking Colony: Attack(14)
  turn_end

### Round 6
Intent: Skulking Colony: Attack(12), Defend
  turn_end

### Round 7
Intent: Skulking Colony: Attack(8), Buff
  cards: Expose, Leading Strike, Shiv, Shiv, dealt=10, taken=0
## Combat Analytics: Skulking Colony (WIN - 7 rounds)

Enemy power timeline:
  Hardened Shell: R1:15 -> R2:15 -> R3:15 -> R4:15 -> R5:15 -> R6:15 -> R7:15
  Strength: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2 -> R7:2
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:1 -> R7:2

Unattributed damage (power/passive effects): 56
  Per round: R2:10 R3:5 R4:6 R5:15 R6:10 R7:10

[Selected: boss] Soul Fysh (F17, boss)
Historical: loss=30 vs historical avg=20.8+/-10.2 (z=0.9, TYPICAL, n=26)
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Large Capsule, Shovel, Parrying Shield, The Boot, Pear, Bowler Hat, Tingsha
Deck (23): Defend x6, Strike x5, Accelerant, Acrobatics, Backflip, Bouncing Flask, Deadly Poison, Expose, Follow Through, Neutralize, Prepared, Ricochet, Survivor, Ultimate Defend
Enemies: Soul Fysh HP=211/211

### Round 1
Agent plan (hypothesis): Poison started. Prepare block for heavy swings and keep applying poison.
Intent: Soul Fysh: StatusCard(2)
  Ricochet
  turn_end

### Round 2
Intent: Soul Fysh: Attack(16)
  Beckon
  turn_end

### Round 3
Agent plan (hypothesis): We are keeping HP high and using Parrying Shield effectively. Draw pile will reshuffle next turn.
Intent: Soul Fysh: Attack(7), StatusCard(1)
  turn_end

### Round 4
Agent plan (hypothesis): Enemy attacks next turn, prepare to block and apply poison.
Intent: Soul Fysh: Buff
  Strike
  turn_end

### Round 5
Agent plan (hypothesis): Intangible wears off next turn. Prepare to stack Poison and block the heavy swings.
Agent plan (hypothesis): Next turn the enemy is no longer Intangible. Stack poison aggressively.
Intent: Soul Fysh: Attack(11), Debuff
  Strike
  turn_end

### Round 6
Intent: Soul Fysh: StatusCard(2)
  turn_end

### Round 7
Agent plan (hypothesis): Traded 5 HP to significantly increase poison stacking.
Intent: Soul Fysh: Attack(24)
  turn_end

### Round 8
Agent plan (hypothesis): Enemy is very close to dying to poison, just need to survive one more turn.
Intent: Soul Fysh: Attack(10), StatusCard(1)
  turn_end

### Round 9
Intent: Soul Fysh: Buff
  turn_end
## Combat Analytics: Soul Fysh (WIN - 9 rounds)

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:4 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:7 -> R8:10 -> R9:13
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-

Unattributed damage (power/passive effects): 49
  Per round: R1:20 R3:11 R4:11 R8:7
Comparator (recent same-enemy comparator):
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Hefty Tablet, Sword of Stone, Game Piece
Deck (24): Defend x5, Strike x5, Accuracy, Assassinate, Cloak and Dagger, Dagger Spray, Dash, Fan of Knives+, Infinite Blades, Leading Strike, Neutralize, Phantom Blades, Spoils Map, Strangle+, Survivor, Up My Sleeve
Enemies: Soul Fysh HP=211/211

### Round 1
Intent: Soul Fysh: StatusCard(2)
  Dexterity Potion
    +Dexterity(2)
  Gigantification Potion
    +Gigantification(1)
  turn_end

### Round 2
Intent: Soul Fysh: Attack(16)
  Beckon
  turn_end

### Round 3
Intent: Soul Fysh: Attack(7), StatusCard(1)
  turn_end

### Round 4
Intent: Soul Fysh: Buff
  turn_end

### Round 5
Intent: Soul Fysh: Attack(11), Debuff
  turn_end

### Round 6
Intent: Soul Fysh: StatusCard(2)
  Bottled Potential
## Combat Analytics: Soul Fysh (WIN - 6 rounds)

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:-

Unattributed damage (power/passive effects): 210
  Per round: R1:79 R2:3 R3:13 R4:57 R6:58

[Selected: death] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (F24, monster)
Historical: loss=29 vs historical avg=9.5+/-11.3 (z=1.7, WORSE_THAN_USUAL, n=32)
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 24, monster)
Relics: Ring of the Snake, Large Capsule, Shovel, Parrying Shield, The Boot, Pear, Bowler Hat, Tingsha, Pael's Legion
Deck (28): Defend x6, Strike x5, Prepared x2, Accelerant, Acrobatics, Backflip, Bouncing Flask, Deadly Poison, Expose, Flick-Flack+, Follow Through, Neutralize, Piercing Wail, Ricochet, Survivor, Tools of the Trade, Ultimate Defend, Well-Laid Plans
Enemies: Bowlbug (Rock) HP=46/46, Bowlbug (Silk) HP=41/41, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Defend
  turn_end

### Round 2
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Strike
  turn_end

### Round 3
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Flick-Flack+
  turn_end

### Round 4
Intent: Bowlbug (Rock): Attack(15), Slumbering Beetle: Attack(16), Buff
  turn_end

### Round 5
Intent: Bowlbug (Rock): Stun, Slumbering Beetle: Attack(18), Buff
  Flick-Flack+
  turn_end

### Round 6
Intent: Bowlbug (Rock): Attack(15), Slumbering Beetle: Attack(20), Buff
  Speed Potion
    +Dexterity(5) | +Speed Potion(5)
  turn_end

### Round 7
Intent: Bowlbug (Rock): Stun, Slumbering Beetle: Attack(22), Buff
  Strike
  Accelerant
  turn_end
    enemy_deltas: Slumbering Beetle: hp -6
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (LOSS - 7 rounds)
Death cause: Died with HP=12, damage_taken=0. Likely mechanic kill.

Enemy power timeline:
  Imbalanced: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:1
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:- -> R6:- -> R7:-
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:4 -> R7:6
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-

Unattributed damage (power/passive effects): 49
  Per round: R1:14 R2:12 R3:6 R4:6 R5:5 R7:6
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 30, monster)
Relics: Ring of the Snake, Leafy Poultice, Byrdpip, Kusarigama, Pael's Flesh, Art of War, Red Mask
Deck (28): Defend x4, Backflip x2, Phantom Blades x2, Strike x2, Acrobatics, Blade Dance, Byrd Swoop, Dagger Throw, Escape Plan, Flick-Flack, Leading Strike, Neutralize, Nightmare, Peck, Piercing Wail, Prepared+, Reflex, Ricochet, Shadow Step+, Shadowmeld+, Survivor, Well-Laid Plans
Enemies: Bowlbug (Rock) HP=48/48, Bowlbug (Silk) HP=40/40, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(11), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Entropic Brew
  turn_end

### Round 2
Intent: Bowlbug (Rock): Attack(11), Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  turn_end
  Reflex

### Round 3
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Reflex
  Nightmare
  Shadow Step+
  Defend
  Defend
  turn_end
  Acrobatics

### Round 4
Intent: Bowlbug (Rock): Stun, Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(16), Buff
  turn_end
  Acrobatics

### Round 5
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Attack(18), Buff
  Flick-Flack
  Ricochet
  turn_end

### Round 6
Intent: Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Attack(20), Buff
  cards: Backflip, Shadowmeld+, Escape Plan, Leading Strike, Shiv, Shiv, Peck, Strike, dealt=53, taken=0
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 6 rounds)

Enemy power timeline:
  Imbalanced: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:-
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:- -> R6:-
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:4
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:-
  Weak[0]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Weak[1]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-
  Weak[2]: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:-

Unattributed damage (power/passive effects): 123
  Per round: R1:17 R5:53 R6:53

## Existing Combat Guides (relevant enemies)
[Guide: Fossil Stalker] WR=100%, 43 episodes, confidence=0.90, v33
  - **Respect the LATCH_MOVE:** Overplaying Strikes and Shivs during the `LATCH_MOVE` phase is the primary cause of HP loss (averaging 8.5 damage taken). Pivot entirely to Block cards like Defend, Survivor, and Backflip during this window.
- **Beat the Round 4 Clock:** Fossil Stalker begins scaling Strength aggressively starting in Round 4. Establish Poison early (Deadly Poison, Poisoned Stab) or use dense upfront attacks (Strangle, Predator) to secure a Round 3 or 4 kill before its damage outpaces your block.
- **Maintain Weakness:** The enemy's base attacks hit for 9-15 damage even before scaling. Consistently cycle Neutralize and Leg Sweep to keep the enemy weakened and offset these heavy hits.
- **Block While Poison Ticks:** Low-HP-loss patterns show a heavy reliance on defensive cards (playing Defend far more often than basic Strikes). Apply your damage engine early, then shift energy entirely toward survival, letting unattributed poison damage secure the kill.
[Guide: Gremlin Merc] WR=92%, 37 episodes, confidence=0.90, v28
  - **Prioritize Block Over Greed:** The Merc routinely hits for 12-14 damage (6x2 or 7x2). High-loss rounds consistently show players taking 9+ damage by aggressively spamming low-impact attacks (Strikes, Shivs) to race the Thievery mechanic. Always block its multi-hits first.
- **Mitigate the Turn 4 Spike:** On Round 4, the Merc gains +2 Strength, turning its multi-hits into massive threats. Retain `Neutralize` (Weak), `Piercing Wail`, and high-value block cards specifically for this turn.
- **Burst Early or Wait it Out:** The cleanest fights (0 damage taken) use heavy upfront burst (`Assassinate`, `Predator+`, `Fan of Knives`) to kill the Merc in 2-3 rounds before it can scale. 
- **Exploit the Escape Phase:** If you lack early burst, focus entirely on survival. By Turn 5, the Merc drops its buffs and transitions to an escape phase (`Heist`), becoming completely passive and allowing you to safely finish it off.
[Guide: Louse Progenitor] WR=91%, 47 episodes, confidence=0.90, v35
  - **Pop Curl Up Early:** The Progenitor starts with 14 Curl Up. Strike it with your weakest attack (like Neutralize or a single Shiv) early on Turn 1 to trigger the block, then break it so your heavier attacks land unmitigated.
- **Exploit Setup Turns:** Turn 1 (Curl Up) and Turn 3 (Strength buff) are low-threat windows. Use these turns to safely deploy powers like Noxious Fumes, Footwork, or Caltrops without bleeding HP.
- **Mitigate Escalation:** The boss gains +5 Strength every three turns (Turns 3, 6, 9). Chain Weakness starting on Turn 3 to survive its boosted 14-19 damage swings, and save Piercing Wail for its heaviest multi-attacks.
- **Race the Clock:** While mitigation is possible (as seen in 10-round wins), the fight becomes highly lethal past Turn 6. Accelerate your damage using Shiv burst (Blade Dance, Storm of Steel) or fast poison scaling to finish the fight by Turn 4 or 5.
[Guide: Sewer Clam] WR=94%, 33 episodes, confidence=0.90, v24
  - **Prioritize Poison Early:** Use non-damaging buff turns (R1, R3) to apply Poison (Deadly Poison, Poisoned Stab) or setup Powers (Footwork, Noxious Fumes). Poison ignores the high starting Plating (8-9), providing the most efficient scaling.
- **Hold Multi-hits for Round 4+:** Plating decays by 1 each turn. Shivs and multi-hit cards (Blade Dance, Dagger Spray) are significantly more effective once Plating has dropped to 5 or lower. Early Shiv usage is a primary cause of low damage efficiency.
- **Full Block on Attack Turns:** The Clam alternates between buffs and heavy hits. In R2 (10 dmg) and R4 (14 dmg), prioritize Block and Weakness (Neutralize, Leg Sweep) over chip damage. Data shows average losses of 9.5 HP when players greedily play Strikes/Shivs during these turns.
- **Counter Strength Scaling:** The enemy gains +4 Strength every odd turn. Applying Weakness specifically for even-numbered rounds is critical to survive the scaling attack damage (10 -> 14 -> 18).
[Guide: Skulking Colony] WR=73%, 26 episodes, confidence=0.90, v20
  - **Respect the HP Cap:** Skulking Colony's Hardened Shell power strictly caps the HP it can lose each turn at 20. Never over-commit energy to burst damage once you are near this limit; pivot entirely to defense, setup, or applying debuffs.
- **Survive the Early Volley:** Rounds 1 and 2 feature heavy single-hit attacks, causing many early losses. Prioritize immediate mitigation rather than trying to rush the kill, as the HP cap guarantees a multi-round encounter.
- **Mitigate Multi-Attack Spikes:** The Colony uses a Buff intent on R3 and R7 to gain Strength, immediately followed by massive multi-attacks on R4 (e.g., 9x2) and R8 (e.g., 12x2). Time your Weak applications or save your strongest block tools specifically for R4 and R8 to neutralize its scaled damage.
[Guide: Sludge Spinner] WR=100%, 68 episodes, confidence=0.90, v41
  - **Respect Early Attacks:** Sludge Spinner frequently attacks for 8-11 damage in the opening rounds. Prioritize full-blocking with `Survivor` and `Defend`; high-damage rounds occur almost exclusively when overplaying `Strike` and ignoring defense.
- **Beat the Strength Clock:** The enemy buffs itself with +3 Strength between Rounds 3 and 5. Aim to close out the fight in 3-4 rounds using early burst sequences or `Shiv` generators to completely bypass this dangerous phase.
- **Tactical Neutralize Timing:** Hold `Neutralize` for the enemy's 11-damage attacks, or apply it immediately after the Spinner gains its +3 Strength to blunt the incoming amplified damage if the fight extends past Round 4.
[Guide: Soul Fysh] WR=89%, 27 episodes, confidence=0.90, v22
  - **Strict 5-Turn Cycle:** Soul Fysh follows a rigid repeating pattern. Plan around its exact turn order.
- **The Vulnerable Trap:** The boss applies Vulnerable(3) on Turn 5 (R5, R10). This debuff perfectly aligns to amplify the Turn 2 Heavy Attack in the next cycle (R7, R12), boosting it from 16 to 24 damage. These amplified hits are the primary cause of losses.
- **Respect the Heavy Swings:** Always save your best defensive tools or debuffs like Weak for Turns 2, 7, and 12.
- **Exploit Intangible Windows:** The enemy gains Intangible on Turn 5s (R5, R10). Direct damage is mitigated to 1, making this an ideal turn for defense and setup. Poison bypasses Intangible completely, ticking for full damage.
- **Punish Low-Pressure Turns:** Turns 1, 3, and 4 (e.g., R1, R3, R4) feature low incoming damage, focusing on status cards and buffs. Use these windows to safely push frontloaded damage or deploy scaling powers.
[Guide: Spiny Toad] WR=93%, 56 episodes, confidence=0.90, v44
  - **Exploit Safe Windows (R1, R3, R4):** The Toad starts without Thorns. Aggressively unleash your multi-hit cards (Blade Dance, Dagger Spray, Backstab) to burst it down or establish your scaling while it is safe.
- **Respect the Thorns (R2 & R5):** The enemy gains 5 Thorns on Rounds 2 and 5. Halt all multi-hit attacks unless you have lethal. Transition to pure defense, Poison application (Deadly Poison, Noxious Fumes), or playing setup powers. The heaviest HP losses happen when blindly playing Shivs into active Thorns.
- **Mitigate Heavy Spikes:** The Toad frequently hits for massive chunks (17 or 23 damage) and possesses a Spike Explosion move. Prioritize applying Weak (Neutralize+) and utilizing high-value block cards (Survivor, Leg Sweep) to survive these turns. HP preservation is much more critical than dealing minor chip damage during these spikes.
- **Poison Bypasses Thorns:** Because Thorns only reflect direct attack damage, stacking Poison is an excellent way to maintain consistent DPS through the Toad's defensive rounds without taking recoil damage.
[Guide: Thieving Hopper] WR=100%, 66 episodes, confidence=0.90, v49
  - **Burst for a 2-Round Kill:** The absolute cleanest wins completely bypass the Hopper's mechanics by frontloading massive damage (e.g., Adrenaline, Blade Dance, Backstab) to kill it by Turn 2. Turn 1 applies zero pressure, giving you a free setup window.
- **Overblock on Turns 2 and 4:** If you cannot secure an early kill, you must heavily defend on Turns 2 and 4. Combat data shows players take severe damage (avg 10.6) by greeding low-impact attacks like Shivs instead of playing Defends and Neutralize.
- **Strip Flutter Safely:** Turn 3 is another non-attacking round, but the Hopper gains 5 stacks of Flutter. Strip this hit-based shielding using multi-hit cards (Shivs) before landing your high-damage attacks.
- **Leverage Poison for Slower Decks:** If your deck lacks upfront burst, utilize the completely safe Turns 1 and 3 to stack Poison. Poison damage completely ignores the Hopper's Flutter stacks and guarantees steady damage while you block its heavy swings.
[Guide: Tunneler] WR=99%, 68 episodes, confidence=0.90, v46
  - **Exploit the R1-R2 Opening:** Tunneler is only vulnerable to direct damage in the first two rounds. Aim for a 'Round 2 Burst' using draw-chains (`Acrobatics`, `Calculated Gamble`) and front-loaded damage (`Backstab`, `Assassinate`, `Ricochet`) to end the fight before it burrows.
- **Poison is Mandatory for Long Fights:** If lethal isn't certain by Round 2, prioritize applying heavy Poison (`Bouncing Flask`, `Deadly Poison`). Poison is the primary way to deal damage during the Burrowed phase (Rounds 3-5) when the enemy is immune to direct attacks.
- **Mitigate the 23-Damage Spike:** Most HP loss occurs during the 23-damage attack intent. Save high-impact defensive tools like `Neutralize+`, `Leg Sweep`, or `Piercing Wail` specifically for this turn; do not waste Weakness on the Tunneler's buff or 13-damage turns.
- **Plating vs. Shivs:** Tunneler’s Plating(4) makes basic Shivs and multi-attacks inefficient. Unless you have significant scaling (`Accuracy+`, `Envenom`), rely on high-damage single hits or Poison to bypass the armor penalty.
[Guide: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle] WR=94%, 33 episodes, confidence=0.90, v28
  - Slumbering Beetle (not Rock) holds the Plating and Slumber mechanics. It sleeps for 3 turns but wakes early if it takes HP loss 3 times. Avoid multi-hit or chip damage on the Beetle while it sleeps.
- Bowlbug (Rock) possesses Imbalanced: fully blocking its attacks guarantees it will be Stunned the next turn. Prioritize full blocks on Rock to neutralize its threat.
- Bowlbug (Silk) alternates between applying Weak and attacking for 4x2. Use the 3-turn sleep window to eliminate Rock and Silk.
- Turn 4 initiates the primary danger window when the Beetle naturally awakens. It attacks every turn and scales linearly (+2 Strength per turn). Burst it down immediately once awake.
- Beware of Turn 5: If Bowlbug (Rock) is alive and not stunned, its 15-damage attack aligns with the Beetle's 18-damage attack for a massive 33-damage spike.
[Guide: multi:Calcified Cultist+Damp Cultist] WR=92%, 36 episodes, confidence=0.90, v29
  - **Exploit Round 1 Setup:** Both cultists spend the first turn buffing and will not attack. Dedicate all your energy to frontloaded attacks, AoE like `Dagger Spray`, and generating Shivs. Do not play block cards on turn 1.
- **Focus the Damp Cultist:** The Damp Cultist's Ritual gives it +5 Strength per turn, compared to the Calcified Cultist's +2. Focus all single-target damage to eliminate the Damp Cultist by round 3 or 4 before its damage output becomes unblockable.
- **Mitigate with Weak:** Use `Neutralize` or other sources of Weak on the Damp Cultist starting on round 2. This drastically reduces its inflated incoming damage and buys you an extra turn to finish it off.
- **Beat the Enrage Timer:** If the fight stretches to round 6 or 7, both cultists will unleash `DARK_STRIKE_MOVE`, an overwhelming attack responsible for almost all high-loss rounds and deaths. Prioritize burst damage over long-term scaling to end the fight quickly.
[Guide: multi:Corpse Slug+Corpse Slug] WR=100%, 71 episodes, confidence=0.90, v50
  - **Control the Kill:** The defining mechanic is their enrage. Killing one slug immediately grants the survivor +4 Strength. Whittle both down evenly to secure a simultaneous kill, or ensure you have immediate lethal on the remaining slug.
- **Leverage AoE:** Multi-target attacks like Dagger Spray, Omnislice, and Ricochet excel at dealing even damage across both targets, naturally setting up a double-kill to bypass the dangerous solo phase.
- **Respect the Enrage:** High-damage rounds heavily correlate with playing aggressive, Strike-heavy turns against a solo, enraged slug. If forced into this phase without lethal, stop attacking and pivot entirely to Survivor, Defends, and Weak to survive the +4 Strength GLOMP attacks.
- **Mitigate the Duo Phase:** While both are alive, their base attacks are weak (3x2 or 8 damage). Target Neutralize on the 3x2 multi-hit intent to halve its damage, making it trivial to full-block while setting up your kills.
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
[Deck Guide: poison] memories=34, confidence=0.80, v5
  - **Size & Core Scaling:** Target a 21-22 card deck. Overly thin decks (~15 cards) consistently fail because they lack the mitigation and draw required to survive Act 2/3. Rely on Noxious Fumes+ as your primary scaler.
- **Mitigation & Cycle:** Basic Defends fail while waiting for poison ticks. Prioritize premium mitigation (Suppress+, Leg Sweep, Piercing Wail) and robust cycling (Backflip, Acrobatics) to survive deep rounds.
- **Focused Secondary Plans:** Supplement poison with either Shivs (for immediate offensive pressure) or heavy debuff control (Haze+). Avoid splitting focus into Discard/Sly synergies, which severely dilute your draws.
- **Removals & Upgrades:** Aggressively remove basic Strikes to improve your defensive consistency. Upgrade Noxious Fumes early to accelerate your damage clock.

## Card Notes (seen this run)
- Neutralize: A-tier starter; upgrade is premium. Save for big attack turns and boss burst checks. 0-cost Weak often beats a Strike; don’t fire it on non-attack intents unless it changes lethal.
- Survivor: C-tier starter block. Fine early and with discard synergies, but with Well-Laid Plans do not auto-retain it over rarer swing cards, scaling, or premium defense.
- Deadly Poison: 1-cost: applies 5 Poison to single target. Core Poison source. Multiple copies stack well. Combos with Accelerant (makes the Poison infinitely scaling) and Envenom (attacks also apply Poison).
- Acrobatics: A-: premium filtering; much better with Runic Pyramid, discard synergies, or retained junk. On dangerous turns play it before filler attacks to dig for block or Wail. Take often.
- Accelerant: Power: Poison damage triggers an extra time at end of turn. Example: enemy has 20 Poison → normally takes 20 damage, with Accelerant takes 20+19=39 damage. Doubles effective Poison damage that turn. Stacks with more Poison sources (Noxious Fumes, Deadly Poison, Bubble Bubble) for higher burst.
- Backflip: 1-cost: block + draw 2. Defends and cycles simultaneously. The draw does not trigger Sly (draw is not discard). Pairs with Dexterity (Footwork) for scaled Block.
- Ricochet: Sly: plays for free when discarded by a card effect. 2-cost: 4 hits × 3 damage = 12 base (upgraded: 4 × 4 = 16). Does NOT benefit from Accuracy — Accuracy only boosts Shivs, and Ricochet is not a Shiv. Effective cost is 0 energy via discard outlets. Each hit benefits from Strength.
- Expose: Expose removes ALL Block and Artifact. Do NOT waste it on Turn 1 against bosses that generate massive shields on Turn 2 (e.g., Ceremonial Beast's 150-Block Plow). Hold it until the enemy actually has the block or artifact you need to strip. Do not burn it blindly just for 2 Vulnerable.
- Prepared: 0-cost draw/discard glue. Excellent first copy in discard decks because both discards are card effects that trigger Sly cards like Reflex, Tactician, Abrasive, and Flick-Flack. Later copies need real payoffs and enough defense; in large decks, extra Prepared can become hand-fixing without improving survival or damage on its own.
- Follow Through: 1-cost: 6 damage + 1 Weak. Compare: Sucker Punch (1-cost, 8 damage + 1 Weak) deals more damage for same cost and Weak.
- Tools of the Trade: Rare Power: draw 1 + discard 1 at start of each turn. The turn-start discard is a card effect, triggering Sly cards every turn automatically. Passive Sly engine — generates discard triggers without spending cards or energy.
- Bouncing Flask: 2-cost: applies 9 total Poison (3 hits × 3 Poison). Splits across enemies in multi-enemy fights (random targeting). Compare: Bubble Bubble (1-cost, 9 Poison, single target) is more efficient per energy.
- Flick-Flack: Sly: plays for free when discarded by a card effect. 1-cost 7 damage to ALL enemies. Effective cost is 0 energy via discard outlets (Acrobatics, Survivor, Prepared). AoE damage for free in discard builds.
- Well-Laid Plans: A-tier control enabler: retains 1/2 cards each turn. CRITICAL for surviving strict boss cycles (Lagavulin Matriarch, Skulking Colony). Do not just retain random cards—specifically hold your highest impact mitigation (Neutralize+, Piercing Wail, Leg Sweep) to precisely counter predictable multi-hit/strength spikes. Also excellent for holding burst pieces until lethal is achievable.
- Piercing Wail: A-tier defense. Its value multiplies per enemy attack instance. Against a single attack, it mitigates 6 damage (worse than Survivor). Against a 3x3 attack, it mitigates 18 damage. Save/retain it specifically for the scariest multi-hit turns. Do not waste it on single heavy hits unless lethal is imminent. Outstanding in boss fights and multi-enemy encounters.

## Card Memory Stats (seen this run)
card | note preview | plays | sly | draws | unplayed | dmg | outcomes
- Strike |  | 6001 | 0 | 12623 | 6901 | 8994 | 21W|A1:15,A2:34,A3:13,inc:9
- Defend |  | 7296 | 3 | 16324 | 9466 | 518 | 25W|A1:15,A2:34,A3:13,inc:10
- Neutralize | A-tier starter; upgrade is premium. Save for big a | 3923 | 0 | 3434 | 156 | 4494 | 25W|A1:15,A2:33,A3:14,inc:10
- Survivor | C-tier starter block. Fine early and with discard  | 2389 | 5 | 3490 | 1399 | 10 | 25W|A1:15,A2:34,A3:14,inc:10
- Deadly Poison | 1-cost: applies 5 Poison to single target. Core Po | 739 | 2 | 1049 | 417 | 153 | 10W|A1:1,A2:16,A3:6,inc:2
- Acrobatics | A-: premium filtering; much better with Runic Pyra | 1165 | 1 | 1422 | 446 | 243 | 18W|A1:6,A2:20,A3:7,inc:5
- Accelerant | Power: Poison damage triggers an extra time at end | 109 | 0 | 157 | 69 | 2 | 5W|A1:0,A2:6,A3:1,inc:1
- Backflip | 1-cost: block + draw 2. Defends and cycles simulta | 1701 | 0 | 1905 | 452 | 387 | 20W|A1:6,A2:22,A3:10,inc:3
- Ricochet | Sly: plays for free when discarded by a card effec | 480 | 334 | 692 | 328 | 506 | 7W|A1:5,A2:9,A3:2,inc:2
- Expose | Expose removes ALL Block and Artifact. Do NOT wast | 279 | 1 | 253 | 22 | 12 | 8W|A1:4,A2:10,A3:4,inc:2
- Ultimate Defend |  | 16 | 0 | 19 | 5 | 0 | 0W|A1:0,A2:1,A3:2
- Prepared | 0-cost draw/discard glue. Excellent first copy in  | 484 | 2 | 468 | 92 | 53 | 8W|A1:4,A2:9,A3:2
- Follow Through | 1-cost: 6 damage + 1 Weak. Compare: Sucker Punch ( | 145 | 0 | 196 | 70 | 264 | 2W|A1:0,A2:3,A3:1,inc:1
- Tools of the Trade | Rare Power: draw 1 + discard 1 at start of each tu | 103 | 0 | 137 | 61 | 8 | 4W|A1:0,A2:4,A3:3,inc:1
- Bouncing Flask | 2-cost: applies 9 total Poison (3 hits × 3 Poison) | 172 | 1 | 334 | 191 | 92 | 4W|A1:2,A2:8,A3:5,inc:1
- Flick-Flack | Sly: plays for free when discarded by a card effec | 569 | 331 | 726 | 287 | 560 | 10W|A1:7,A2:12,A3:3,inc:3
- Well-Laid Plans | A-tier control enabler: retains 1/2 cards each tur | 370 | 0 | 525 | 217 | 26 | 15W|A1:3,A2:15,A3:7,inc:1
- Piercing Wail | A-tier defense. Its value multiplies per enemy att | 489 | 0 | 1081 | 663 | 67 | 18W|A1:4,A2:18,A3:12,inc:7

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F12(Skulking Colony: WIN), F17(Soul Fysh: WIN)
- Core Combat Principles: F2(Corpse Slug: WIN), F3(Toadpole: WIN), F4(Sludge Spinner: WIN), F5(Calcified Cultist: WIN), F7(Sewer Clam: WIN), F8(Two-Tailed Rat: WIN), F12(Skulking Colony: WIN), F13(Gremlin Merc: ), F14(Fossil Stalker: WIN), F17(Soul Fysh: WIN), F19(Tunneler: WIN), F20(Thieving Hopper: WIN), F22(Louse Progenitor: WIN), F23(Spiny Toad: WIN), F24(Bowlbug (Rock): )
- Deck Building Across the Run: F2(), F3(), F4(), F5(), F7(), F8(), F12(), F13(), F14(), F15(), F15(), F17(), F19(), F20(), F21(), F22(), F23()
- Map Routing and Path Planning: F1(), F1(), F2(), F6(), F6(), F11(), F11(), F14(), F18(), F18()
- Never Smith Upgraded Cards: F9(), F16()
- Rest Site and Event Decisions: F9(), F16()
- Silent - Combat Sequencing: F2(Corpse Slug: WIN), F3(Toadpole: WIN), F4(Sludge Spinner: WIN), F5(Calcified Cultist: WIN), F7(Sewer Clam: WIN), F8(Two-Tailed Rat: WIN), F12(Skulking Colony: WIN), F13(Gremlin Merc: ), F14(Fossil Stalker: WIN), F17(Soul Fysh: WIN), F19(Tunneler: WIN), F20(Thieving Hopper: WIN), F22(Louse Progenitor: WIN), F23(Spiny Toad: WIN), F24(Bowlbug (Rock): )
- Silent - Draft and Shop Rules: F2(), F3(), F4(), F5(), F7(), F8(), F12(), F13(), F14(), F15(), F15(), F17(), F19(), F20(), F21(), F22(), F23()
- Silent - Route Priorities: F1(), F1(), F2(), F6(), F6(), F11(), F11(), F14(), F18(), F18()

## Dynamic Tools
- block_sufficiency_check: 19347 calls, 19347 successes
- poison_block_survival_plan: 4300 calls, 4300 successes
- poison_kill_and_survive_check: 18800 calls, 18800 successes
- poison_survival_analysis: 21210 calls, 20113 successes
- poison_turns_to_kill: 21253 calls, 20113 successes
- silent_exact_mitigation_line: 4724 calls, 4724 successes

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When a guide or card note is outdated, update it directly instead of inventing duplicate knowledge.