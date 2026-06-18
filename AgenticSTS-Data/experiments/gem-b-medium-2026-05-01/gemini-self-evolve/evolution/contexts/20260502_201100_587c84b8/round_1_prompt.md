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
Result: VICTORY (fitness: 235.5)
Combats won: 17/17
Run duration: 5690.8s

## Full-run Decision Digest

## Strategic Thread (agent intent at decision time — hypotheses, not ground truth)
### F1
- [event] Foundation deck: looking for early damage cards and elite-killing tools, relying on massive turn 1 draw from Booming Conch + Ring of the Snake to dominate Elite fights.
- [map] Foundation deck: using turn 1 draw from Ring of the Snake and Booming Conch to find high-impact damage and block early; prioritizing monster fights floors 1-3 to find essential attacks before the first elite.
### F2
- [card_reward] Foundation plan: prioritize frontload damage and efficient AoE to survive Act 1 elites. Leverage massive turn 1 draw from Booming Conch + Ring of the Snake to burst threats early.
### F3
- [card_reward] Foundation phase: prioritize immediate frontload damage and efficient block to survive Act 1. Look for high-impact attacks or poison/shiv engine starters. Avoid expensive or purely synergistic cards until a core engine is established.
- [map] Foundation deck: leveraging turn 1 draw from Booming Conch and Ring of the Snake to find early damage and block; prioritizing card quality and removals to prepare for the late-act Elite and Boss.
### F4
- [event] Foundation deck: looking for early damage cards and elite-killing tools, relying on massive turn 1 draw from Booming Conch + Ring of the Snake to dominate Elite fights.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. Use Survivor to trigger Flick-Flack for free AoE.
- [map] Foundation deck: leveraging turn 1 draw from Booming Conch and Ring of the Snake to find early damage and block; prioritizing card quality and removals to prepare for the late-act Elite and Boss.
### F5
- [card_reward] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine. Expose into Skewer is our primary burst combo; look for card draw to assemble it more consistently and skip narrow synergy pieces until we find a core engine.
### F6
- [event] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer) and powerful basic upgrades; prioritize securing more elite-killing tools and card removals.
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
### F7
- [map] Foundation deck: focusing on high-value card rewards and gold accumulation to prepare for the mid-act Elite; leveraging Booming Conch for strong turn-1 starts while prioritizing defensive consistency.
### F8
- [card_reward] Foundation plan: survive with frontload (Dash, Skewer) and efficient block while looking for a real scaling engine (poison or discard/shivs). Keep options open.
### F9
- [rest_site] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer+) and basic upgrades; prioritize securing more elite-killing tools and card removals.
### F10
- [map] Foundation deck: using massive turn 1 draw from Booming Conch and Ring of the Snake to find Skewer or key block cards; prioritizing upgrades at Rest Sites and card removals at the upcoming Shop to refine the draw pool for Elite and Boss scaling.
### F11
- [rest_site] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer+ and Dash+) and basic upgrades; prioritize securing more elite-killing tools and card removals.
- [map] Foundation deck: using high turn 1 draw from Booming Conch and Ring of the Snake to find key cards early; prioritize Elite rewards and card removals at shops to thin the deck for consistent damage.
### F12
- [card_reward] Foundation plan: Survive Act 1 with frontload damage (Dash+, Skewer+) while taking generic efficient mitigation and draw (Backflip). Still looking for a core scaling engine, so skip narrow synergies until we find a payoff.
### F13
- [card_select] Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.
- [map] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to find key damage like Skewer; prioritize securing more scaling and card removals while maintaining enough HP to survive the Act 1 boss.
### F14
- [event] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to find key damage like Skewer; prioritize securing more scaling and card removals while maintaining enough HP to survive the Act 1 boss.
- [map] Foundation deck: utilizing Booming Conch and Ring of the Snake for heavy turn 1 draw to find Skewer+ and Dash+; the goal is to survive to the Act 1 boss with enough HP to leverage these front-loaded damage pieces.
### F16
- [rest_site] Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage like Skewer+ and Dash+; prioritize surviving the Act 1 boss, then focus on securing scaling tools, card removals, and block.
### F17
- [card_reward] Committed Tracking/Attacks plan: Prioritize drafting consistent sources of Weakness and efficient attacks (especially Shivs and multi-hits) to capitalize on Tracking's double damage. Needs more draw to consistently assemble the combo; avoid bloated non-synergistic skills.
### F18
- [event] Foundation deck: utilizing massive card draw from relics (Ring of the Snake, Pael's Blood) to quickly cycle and find key front-loaded damage (Skewer+, Dash+) while scaling with Tracking. Needs more energy generation and consistent block engine for Act 2 Boss.
- [map] Foundation phase: currently prioritizing monster fights to build card quality and gold. The goal is to establish a solid defensive core or scaling damage engine before the mid-act shops. Use HP as a resource to secure better cards, but prioritize upgrades at future rest sites to ensure survival against the Act 2 boss.
### F19
- [card_reward] Committed to physical damage scaled by Tracking and Vulnerable. Look for multi-hit attacks, Weak sources, and draw. Use Well-Laid Plans to hold Expose, Tracking, and big attacks for a burst turn. Avoid poison or disjointed mechanics.
### F20
- [card_reward] Foundation plan: utilize Tracking and physical damage (Shivs, Skewer) as our core engine. Use Prepared+ to cycle past curses and set up heavy attack turns on Weak enemies.
### F21
- [event] Foundation deck: utilizing massive card draw from relics to quickly cycle and find key front-loaded damage (Skewer+, Dash+) and AoE (Exterminate) while scaling with Tracking. Needs more energy generation and consistent block engine for Act 2 Boss.
### F22
- [hand_select] Multi-hit cards are useless while the Tender debuff is active.
- [card_reward] Committed to Shiv/Weak synergy with Tracking and Expose. Prioritize applying Weak with Inky Shivs or Neutralize before unloading other attacks for double damage. Focus on adding more Shiv generation and card draw to find combo pieces faster.
- [map] Foundation phase: currently prioritizing survival through high-variance Act 2 events while avoiding chip damage from hallway fights. Need to stabilize HP at the upcoming rest sites and look for high-impact defensive scaling or reliable card draw to capitalize on Booming Conch in future elite encounters.
### F23
- [hand_select] Retaining block allows for a more aggressive turn next round or guaranteed safety if the Bowlbug's attack scales.
- [hand_select] Well-Laid Plans allows retaining these for free. Using the full capacity to ensure a strong following turn.
- [card_reward] Committed to Shiv/Fan synergy with Well-Laid Plans utility. Keep retaining key defensive/burst cards like Piercing Wail for exact enemy burst turns. Look for Accuracy or strong scaling damage pieces next; prioritize upgrading Shiv generators and removing basics.
### F24
- [rest_site] Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs consistent block engine and energy generation for the Act 2 Boss.
- [map] Foundation deck: currently prioritizing survival and pathing through safe nodes to reach rest sites. Need to stabilize HP and find a definitive scaling engine (poison or shivs) before the next boss.
### F25
- [event] Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs consistent block engine and energy generation for the Act 2 Boss.
- [card_select] Committed shiv/attack plan: generate shivs to trigger Ornamental Fan for block while using Exterminate and Skewer for AoE/burst damage. Needs more draw/discard tools and remove Strikes.
- [map] Foundation deck: utilizing card draw from relics to cycle for front-loaded damage while scaling with Tracking. Needs better block to protect the low HP pool; prioritising survival and healing at rest sites before seeking removals or defensive upgrades at upcoming shops.
### F27
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Act 2 Boss.
- [map] Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs a reliable block engine or sustain as HP is low (30/70); prioritize finding defensive solutions or card removal in the upcoming shop.
### F28
- [card_select] Committed Shiv/Tracking plan: Apply Weak to enemies, then use Shivs and attacks to deal double damage. Keep deck thin of curses and unplayable cards to find Tracking and Weak applications faster.
- [map] Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking; priority is now survival and reaching the Act 2 boss through rest sites.
### F29
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Act 2 Boss.
### F30
- [map] Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Seeking more consistent block and a finisher to convert draw into damage.
### F32
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Boss.
### F33
- [card_select] Committed to Shiv/Fan synergy with Well-Laid Plans utility. Keep retaining key defensive/burst cards like Piercing Wail for exact enemy burst turns. Look for Accuracy or strong scaling damage pieces next; prioritize upgrading Shiv generators and removing basics.
- [hand_select] Flick-Flack provides free chip damage. Keeping Expose and Defends to ensure survival and setup for the Vulnerable/Tracking burst.
- [hand_select] Maximizing synergy with Tracking and Shiv-generation for burst damage.
- [card_select] Committed to Shiv/Fan synergy with Well-Laid Plans utility. Retain key defensive and burst cards to survive exact enemy burst turns. Needs Accuracy or strong scaling damage pieces; prioritize upgrading Shiv generators and removing basics.
- [card_reward] Foundation plan: cycle quickly with draw and 0-cost utility to generate shivs and trigger Fan/Letter Opener. Adrenaline helps immensely. Still looking for definitive scaling (like Accuracy or Finisher) for shivs.
### F34
- [event] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. With Brilliant Scarf, plan turns so the 5th card played is the most expensive one (e.g., Dash+). Needs consistent block engine and energy generation for the Boss.
- [map] Foundation deck focusing on draw and Tracking scaling; prioritize gold generation through monster fights to afford shop removals/relics, then leverage HP and rest sites to survive into the late game.
### F35
- [hand_select] Hold Piercing Wail for a turn where the enemy actually attacks.
- [hand_select] Flick-Flack helps chip down the sculptor towards lethal range while maintaining defense.
- [card_reward] Foundation plan: Use frontload, Shivs, and Sly mechanics to deal damage while leveraging multi-play relics like Ornamental Fan and Letter Opener for defense and AoE.
### F36
- [event] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail), then burst enemies with multi-hits like Exterminate and Skewer. With Brilliant Scarf, plan turns so the 5th card played is the most expensive one (e.g., Dash+). Needs consistent block engine and energy generation for the Boss.
- [map] Committed Tracking deck: find Tracking and Weakness pieces early, then use multi-hit cards like Exterminate and Skewer to close fights. Needs more consistent block and energy generation for the final boss; avoid elites and farm gold in hallway fights to maximize shop value.
### F37
- [card_reward] Committed to attack/skill spam with Fan and Scarf, but rely on Footwork for block scaling. Play Footwork early in long fights, then spam Shivs to trigger Fan and Letter Opener.
- [map] Committed Tracking deck: cycle cards to find Tracking and multi-hit finishers like Exterminate and Skewer while maintaining Weakness. Prioritizing gold gain from hallway fights for a late-act shop to finalize the block engine or find energy relics/cards.
### F38
- [hand_select] Well-Laid Plans is allowing us to hold onto high-impact defensive and utility cards.
- [card_reward] Committed to Shivs/Attacks with Fan and Tracking+ engine. Spam Shivs on weak enemies for double damage and trigger Fan for block. Look for draw and more ways to leverage 0-cost attacks.
- [map] Committed Tracking deck: use card draw to find Tracking and Weak applicators like Blade of Ink, then burst with multi-hits. Needs a more robust block engine and energy generation for the final boss; prioritize card rewards that offer defense or energy.
### F39
- [card_reward] Committed shiv plan: use Blade Dance and Cloak and Dagger to generate shivs, triggering Fan and Letter Opener. Use Tracking+ on key targets for double attack damage. Retain burst damage or combo pieces with Well-Laid Plans. Skip off-plan cards to maintain consistency.
### F40
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Boss.
### F41
- [map] Committed Tracking deck: cycle cards to find Tracking and Weak applicators while using Brilliant Scarf to discount high-impact finishers like Dash+ or Skewer. Prioritize consistent block to survive until energy generation is found for the Boss; avoid Act 3 Elites to preserve HP for the final Shop and Boss marathon.
### F42
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators (Blade of Ink, Neutralize), then burst enemies with multi-hits. Plan turns to make the 5th card played the most expensive one via Brilliant Scarf. Needs consistent energy and block engine for the Boss.
### F43
- [map] Committed Tracking deck: find Tracking and Weak applicators to survive, then burst with multi-hits like Skewer. Optimize Brilliant Scarf by playing the high-cost finisher as the 5th card. Prioritize upgrading Tracking and energy-efficient block cards to ensure the engine scales for the Act 3 boss.
### F44
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators, generating Shivs (especially Inky Shivs) to trigger Tracking and burst enemies with multi-hits. Needs consistent block engine and energy generation for the Boss.
- [map] Committed Tracking deck: cycle for Tracking and Weak applicators while timing the 5th card played (Brilliant Scarf) for high-impact cards like Dash+. The deck needs more consistent block scaling and energy generation for the Boss; avoid Act 3 elites to preserve HP.
### F45
- [hand_select] Prioritize high damage while Tracking is active. Discarding basic Strikes thins the hand for better options next turn.
- [card_reward] Committed Shiv/Tracking plan: use weak sources (Expose, Neutralize, Blade of Ink) to double attack damage via Tracking+, then burst with Shivs while triggering Ornamental Fan for defense. Skip bloat to keep drawing the core setup.
### F47
- [rest_site] Committed Tracking deck: use card draw to find Tracking and Weak applicators, generating Shivs to trigger Tracking and burst enemies with multi-hits. Set up double Footwork for scaling block against the boss.
### F48
- [hand_select] Discarding Flick-Flack to maximize energy efficiency and board damage while clearing a dead card from the hand.
- [hand_select] Exterminate is extremely powerful here due to Tracking and multi-hit scaling.
- [hand_select] Enemy is currently Intangible, so saving high-impact attacks for the turn it wears off is crucial.

### Combat Decision Digest (17 combats)
F2 [monster] Sludge Spinner (4R, HP 56->55, loss=1, WIN)
  R1[Sludge Spinner: Atk(8), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike(6dmg)->Strike(6dmg)->Defend(+5blk) | dealt=15 taken=1
  R2[Sludge Spinner: Atk(11)]: Strike(4dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=4 taken=0
  R3[Sludge Spinner: Atk(6), Buff]: Survivor(+8blk)->Strike(6dmg)->Strike(6dmg) | dealt=12 taken=0
  R4[Sludge Spinner: Atk(11), Debuff]: Neutralize(3dmg,1+Weak(1))->Strike | dealt=3 taken=0

F3 [monster] Seapunk (4R, HP 55->55, loss=0, WIN)
  R1[Seapunk: Atk(11)]: Neutralize(3dmg,1+Weak(1))->Defend(+5blk)->Defend(+5blk)->Strike(6dmg) | dealt=9 taken=0
  R2[Seapunk: Atk(2x4=8)]: Strike(6dmg)->Defend(+5blk)->Survivor(+8blk) | dealt=6 taken=0
  R3[Seapunk: Buff, Defend]: Neutralize(3dmg,1+Weak(1))->Flick-Flack(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=21 taken=0
  R4[Seapunk: Atk(12)]: Strike->Strike(5dmg)->Strike | dealt=5 taken=0

F5 [monster] multi:Corpse Slug+Corpse Slug (5R, HP 55->51, loss=4, WIN)
  R1[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Defend(+5blk)->Defend(+5blk)->Flick-Flack(6dmg) | dealt=6 taken=4
  R2[Corpse Slug: Atk(8)+Corpse Slug: Debuff]: Expose(exhaust:1)->Neutralize->Defend(+5blk)->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=0
  R3[Corpse Slug: Debuff+Corpse Slug: Atk(3x2=6)]: Strike->Strike(6dmg)->Survivor(+6blk) | dealt=6 taken=0
  R4[Corpse Slug: Atk(3x2=6)+Corpse Slug: Atk(8)]: Strike(1+Strength(4))->Strike(6dmg) | dealt=6 taken=0
  R5[Corpse Slug: Atk(12)]: Neutralize(5dmg,1+Weak(1))->Strike(power:-Frail) | dealt=5 taken=0

F8 [monster] multi:Calcified Cultist+Seapunk (5R, HP 51->48, loss=3, WIN)
  R1[Calcified Cultist: Buff+Seapunk: Atk(11)]: Neutralize(5dmg,1+Weak(1))->Defend(+5blk)->Skewer(16dmg) | dealt=21 taken=3
  R2[Calcified Cultist: Atk(9)+Seapunk: Atk(2x4=8)]: Expose(1+Vulnerable(2),exhaust:1)->Strike(9dmg)->Defend(+5blk)->Defend(+5blk)->Survivor(+8blk)->Flick-Flack | dealt=24 taken=0
  R3[Calcified Cultist: Atk(11)+Seapunk: Buff, Defend]: Neutralize->Strike(6dmg)->Strike(6dmg)->Strike(6dmg) | dealt=25 taken=0
  R4[Seapunk: Atk(12)]: Defend(+5blk)->Strike->Survivor(+8blk) | dealt=0 taken=0
  R5[Seapunk: Atk(3x4=12)]: Neutralize(5dmg,1+Weak(1))->Skewer | dealt=5 taken=0

F12 [elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (7R, HP 48->41, loss=7, WIN)
  R1[Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(5)+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Buff]: Defend(+5blk)->Defend(+5blk)->Skewer+(11dmg) | dealt=11 taken=5
  R2[Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Atk(7)]: Expose(1+Vulnerable(2),exhaust:1)->Survivor(+8blk)->Flick-Flack(2-Strength,-Vulnerable)->Strike+(+5blk)->Defend | dealt=0 taken=0
  R3[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(1x3=3)+Phantasmal Gardener: Buff]: Neutralize->Dash+(+13blk)->Strike | dealt=0 taken=0
  R4[Phantasmal Gardener: Atk(9)+Phantasmal Gardener: Buff+Phantasmal Gardener: Atk(7)]: Strike->Defend(+5blk)->Strike+(9dmg) | dealt=9 taken=2
  R5[Phantasmal Gardener: Atk(7)+Phantasmal Gardener: Atk(9)]: Survivor(+8blk)->Flick-Flack->Skewer+ | dealt=0 taken=0
  R6[Phantasmal Gardener: Atk(9)]: Defend(+5blk)->Defend(+10blk)->Strike(6dmg) | dealt=6 taken=0
  R7[Phantasmal Gardener: Atk(3x3=9)]: Skewer+ | dealt=0 taken=0

F17 [boss] Soul Fysh (11R, HP 62->19, loss=43, WIN)
  R1[Soul Fysh: StatusCard(2)]: Neutralize(10dmg,1+Weak(1))->Leading Strike(8dmg)->Shiv(9dmg,+4blk,exhaust:1)->Shiv(9dmg)->Backflip(+5blk)->Expose(1+Vulnerable(2),exhaust:1)->Strike+(21dmg) | dealt=57 taken=0
  R2[Soul Fysh: Atk(16)]: Blade Dance(exhaust:1)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg,+4blk)->Skewer+(32dmg) | dealt=50 taken=12
  R3[Soul Fysh: Atk(7), StatusCard(1)]: Strike(6dmg)->Strike(6dmg)->Survivor+(+11blk) | dealt=12 taken=0
  R4[Soul Fysh: Buff]: Neutralize(5dmg,1+Weak(1))->Leading Strike(3dmg)->Shiv(4dmg,+4blk)->Shiv(4dmg)->Dash+(13dmg,+13blk) | dealt=29 taken=6
  R5[Soul Fysh: Atk(11), Debuff]: Backflip(+5blk)->Defend(+5blk)->Beckon | dealt=0 taken=1
  R6[Soul Fysh: StatusCard(2)]: Strike(6dmg)->Strike+(9dmg)->Survivor+(+11blk)->Flick-Flack | dealt=21 taken=0
  R7[Soul Fysh: Atk(24)]: Beckon*3 | dealt=0 taken=24
  R8[Soul Fysh: Atk(10), StatusCard(1)]: Neutralize(5dmg,1+Weak(1))->Defend(+10blk)->Strike+(9dmg)->Strike(6dmg,+4blk) | dealt=20 taken=0
  R9[Soul Fysh: Buff]: Strike(6dmg)->Strike+(9dmg)->Beckon | dealt=15 taken=0
  R10[Soul Fysh: Atk(11), Debuff]: Survivor+(+11blk)->Dash+(1dmg,+13blk) | dealt=1 taken=0
  R11[Soul Fysh: StatusCard(2)]: Skewer+(power:-Vulnerable) | dealt=0 taken=0

F19 [monster] multi:Bowlbug (Egg)+Bowlbug (Rock) (5R, HP 59->59, loss=0, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Egg): Atk(7), Defend]: Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Shiv(4dmg,+4blk)->Defend(+10blk)->Survivor+(+11blk) | dealt=12 taken=0
  R2[Bowlbug (Rock): Stun+Bowlbug (Egg): Atk(7), Defend]: Expose(1+Vulnerable(2),exhaust:1)->Strike->Strike+(9dmg)->Defend(+5blk) | dealt=18 taken=0
  R3[Bowlbug (Rock): Atk(15)]: Neutralize(5dmg,1+Weak(1))->Dash+(13dmg,+13blk)->Leading Strike(3dmg,+4blk)->Shiv(4dmg)->Shiv(4dmg) | dealt=29 taken=0
  R4[Bowlbug (Rock): Stun]: Strike(6dmg) | dealt=6 taken=0
  R5[Bowlbug (Rock): Atk(15)]: Flick-Flack | dealt=0 taken=0

F20 [monster] Tunneler (4R, HP 59->59, loss=0, WIN)
  R1[Tunneler: Atk(13)]: Neutralize(5dmg,1+Weak(1))->Leading Strike(3dmg)->Shiv(4dmg,+4blk,exhaust:1)->Shiv(4dmg)->Backflip(+5blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=16 taken=0
  R2[Tunneler: Buff, Defend]: Expose(1+Vulnerable(2),exhaust:1)->Skewer+(48dmg) | dealt=48 taken=0
  R3[Tunneler: Atk(23)]: Blade Dance(exhaust:1)->Shiv*2->Shiv(+4blk)->Dash+(5dmg,+13blk,1-Burrowed) | dealt=5 taken=0
  R4[Tunneler: Atk(13)]: Skewer+(power:-Well-Laid Plans) | dealt=0 taken=0

F22 [monster] Hunter Killer (8R, HP 59->31, loss=28, WIN)
  R1[Hunter Killer: Debuff]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Strike(6dmg)->Strike+(9dmg) | dealt=15 taken=0
  R2[Hunter Killer: Atk(7x3=21)]: Expose(power:+Strength(-1),power:+Dexterity(-1),1+Vulnerable(2),exhaust:1)->Neutralize(6dmg,power:Strength(-1→-2),power:Dexterity(-1→-2),1+Weak(1))->Tracking(power:Strength(-2→-3),power:Dexterity(-2→-3),power:+Tracking(2))->Prepared+->Flick-Flack(12dmg,+4blk,power:Strength(-5→-6),power:Dexterity(-5→-6))->Strike+ | dealt=18 taken=11
  R3[Hunter Killer: Atk(17)]: Dash+(19dmg,+13blk,power:+Strength(-1),power:+Dexterity(-1))->Defend(+4blk,power:Strength(-1→-2),power:Dexterity(-1→-2)) | dealt=19 taken=0
  R4[Hunter Killer: Atk(7x3=21)]: Defend(+9blk,power:+Strength(-2),power:+Dexterity(-2))->Backflip(+3blk,power:Strength(-2→-3),power:Dexterity(-2→-3))->Neutralize(2dmg,power:Strength(-3→-4),power:Dexterity(-3→-4),1+Weak(1))->Strike(4dmg,power:Strength(-4→-5),power:Dexterity(-4→-5)) | dealt=6 taken=3
  R5[Hunter Killer: Atk(7x3=21)]: Defend(+5blk,power:+Strength(-1),power:+Dexterity(-1))->Defend+(+7blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Strike(4dmg,power:Strength(-2→-3),power:Dexterity(-2→-3)) | dealt=4 taken=9
  R6[Hunter Killer: Atk(17)]: Dash+(13dmg,+13blk,power:+Strength(-1),power:+Dexterity(-1))->Survivor+(+10blk) | dealt=13 taken=0
  R7[Hunter Killer: Atk(7x3=21)]: Defend+(+8blk,power:+Strength(-1),power:+Dexterity(-1))->Defend(+4blk,power:Strength(-1→-2),power:Dexterity(-1→-2))->Blade Dance(power:Strength(-2→-3),power:Dexterity(-2→-3),exhaust:1)->Shiv(1dmg,power:Strength(-3→-4),power:Dexterity(-3→-4),exhaust:1)->Shiv(power:Strength(-4→-5),power:Dexterity(-4→-5))->Shiv(+4blk,power:Strength(-5→-6),power:Dexterity(-5→-6)) | dealt=1 taken=5
  R8[Hunter Killer: Atk(17)]: Neutralize(5dmg,power:+Strength(-1),power:+Dexterity(-1),1+Weak(1))->Skewer+(power:-Well-Laid Plans,power:-Tender,power:-Tracking,power:-Strength,power:-Dexterity) | dealt=5 taken=0

F23 [monster] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (10R, HP 31->15, loss=16, WIN)
  R1[Bowlbug (Rock): Atk(15)+Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Expose(1+Vulnerable(2),exhaust:1)->Skewer+ | dealt=45 taken=0
  R2[Bowlbug (Silk): Atk(4x2=8)+Slumbering Beetle: Sleep]: Well-Laid Plans+(power:+Well-Laid Plans(2))->Blade Dance(exhaust:1)->Shiv(3dmg,exhaust:1)->Shiv(3dmg)->Shiv(3dmg,+4blk)->Leading Strike(2dmg)->Shiv(3dmg)->Shiv(3dmg,+4blk) | dealt=17 taken=0
  R3[Bowlbug (Silk): Debuff+Slumbering Beetle: Sleep]: Backflip(+5blk)->Prepared+->Flick-Flack->Blade of Ink(6dmg,1+Weak(1),exhaust:1)->Shiv(6dmg,+4blk,1Weak(1→2))->Shiv->Strike+ | dealt=18 taken=0
  R4[Slumbering Beetle: Atk(16), Buff]: Neutralize(1+Weak(1))->Survivor+(+11blk)->Flick-Flack(11dmg,+17blk)->Dash+ | dealt=11 taken=0
  R5[Slumbering Beetle: Atk(18), Buff]: Backflip(+5blk)->Prepared+->Defend(+5blk)->Defend(+5blk) | dealt=0 taken=3
  R6[Slumbering Beetle: Atk(20), Buff]: Dash+(13dmg,+13blk)->Defend(+10blk) | dealt=13 taken=0
  R7[Slumbering Beetle: Atk(22), Buff]: Backflip(+5blk)->Prepared+->Flick-Flack(5dmg,1+Weak(1))->Neutralize(+5blk)->Defend(+5blk)->Defend | dealt=5 taken=1
  R8[Slumbering Beetle: Atk(24), Buff]: Blade of Ink->Shiv(6dmg,1+Weak(1))->Shiv(6dmg,1Weak(1→2))->Survivor+(+11blk)->Defend(+5blk) | dealt=12 taken=2
  R9[Slumbering Beetle: Atk(19), Buff]: Neutralize(5dmg,1Weak(1→2))->Backflip(+5blk)->Leading Strike(3dmg)->Shiv(4dmg,+4blk)->Shiv(4dmg)->Strike(6dmg) | dealt=22 taken=10
  R10[Slumbering Beetle: Atk(21), Buff]: Skewer+(power:-Well-Laid Plans) | dealt=0 taken=0

F33 [boss] Knowledge Demon (7R, HP 70->60, loss=10, WIN)
  R1[Knowledge Demon: Debuff]: Tracking+(power:+Tracking(2))->Blade of Ink->Shiv(6dmg,1+Weak(1),exhaust:1)->Shiv(12dmg,1Weak(1→2))->Exterminate(88dmg,+4blk) | dealt=106 taken=0
  R2[Knowledge Demon: Atk(12)]: Dash+(26dmg,+15blk)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Prepared+->Flick-Flack(1+Vulnerable(2),exhaust:1)->Expose | dealt=26 taken=3
  R3[Knowledge Demon: Atk(8x3=24)]: Neutralize(7dmg,1+Weak(1))->Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Leading Strike(9dmg)->Shiv(12dmg,+4blk,exhaust:1)->Shiv(12dmg)->Blade Dance(exhaust:1)->Shiv(12dmg)->Shiv(12dmg,+4blk)->Shiv(12dmg) | dealt=76 taken=1
  R4[Knowledge Demon: Atk(11), Heal, Buff]: Deflect(+6blk)->Backflip(+7blk)->Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg,+4blk)->Skewer+(11dmg) | dealt=22 taken=0
  R5[Knowledge Demon: Debuff]: Neutralize(5dmg,1+Weak(1))->Prepared+->Blade of Ink->Cloak and Dagger(5dmg,+8blk)->Shiv(12dmg,1Weak(1→2))->Shiv(12dmg,+4blk,1Weak(2→3))->Shiv(8dmg)->Exterminate(24dmg) | dealt=66 taken=0
  R6[Knowledge Demon: Atk(14)]: Blade of Ink->Shiv(12dmg,1Weak(2→3))->Shiv(12dmg,1Weak(3→4))->Leading Strike(6dmg,+4blk)->Shiv(8dmg)->Shiv(8dmg)->Survivor+(+13blk)->Flick-Flack | dealt=46 taken=6
  R7[Knowledge Demon: Atk(7x3=21)]: Neutralize(10dmg,1Weak(3→4))->Dash+(26dmg,+15blk)->Strike+(power:-Dexterity,power:-Tracking,power:-Disintegration,power:-Well-Laid Plans) | dealt=36 taken=0

F35 [monster] Devoted Sculptor (2R, HP 68->68, loss=0, WIN)
  R1[Devoted Sculptor: Buff]: Adrenaline(+1energy,exhaust:1)->Well-Laid Plans+(power:+Well-Laid Plans(2))->Expose(1+Vulnerable(2),exhaust:1)->Blade of Ink(5dmg)->Strike+(13dmg)->Exterminate(64dmg)->Shiv(9dmg,+4blk,1+Weak(1),exhaust:1)->Shiv(9dmg,1Weak(1→2)) | dealt=100 taken=0
  R2[Devoted Sculptor: Atk(9)]: Blade Dance(exhaust:1)->Shiv(6dmg,exhaust:1)->Shiv(6dmg)->Shiv(6dmg,+4blk)->Dash+(19dmg,+13blk)->Backflip(+5blk)->Prepared+->Flick-Flack(power:-Well-Laid Plans)->Skewer+ | dealt=37 taken=0

F37 [monster] multi:Living Shield+Turret Operator (4R, HP 68->68, loss=0, WIN)
  R1[Living Shield: Atk(4)+Turret Operator: Atk(2x5=10)]: Cloak and Dagger(+6blk)->Blade Dance(exhaust:1)->Shiv(4dmg,exhaust:1)->Shiv(4dmg)->Dash+(13dmg,+17blk)->Shiv(4dmg)->Shiv(4dmg)->Flick-Flack(6dmg,+4blk) | dealt=35 taken=0
  R2[Living Shield: Atk(6)+Turret Operator: Atk(3x5=15)]: Leading Strike(3dmg)->Shiv(4dmg)->Shiv(4dmg,+4blk)->Deflect(+4blk)->Survivor+(+11blk)->Defend+(5dmg,+8blk)->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=16 taken=0
  R3[Living Shield: Atk(6)+Turret Operator: Buff]: Neutralize->Adrenaline(+1energy,exhaust:1)->Backflip(+5blk)->Blade of Ink->Shiv(1+Weak(1),exhaust:1)->Shiv(+4blk,1Weak(1→2)) | dealt=4 taken=0
  R4[Turret Operator: Atk(3x5=15)]: Expose(1+Vulnerable(2),exhaust:1)->Tracking+(power:+Tracking(2))->Exterminate(power:-Well-Laid Plans,power:-Tracking) | dealt=0 taken=0

F38 [monster] Fabricator (3R, HP 68->64, loss=4, WIN)
  R1[Fabricator: Atk(13), Summon]: Neutralize(5dmg,1Weak(1→2))->Cloak and Dagger(+6blk)->Shiv(4dmg,exhaust:1)->Blade of Ink->Dash+(13dmg,+17blk)->Shiv(6dmg,1Weak(2→3),exhaust:1)->Shiv(6dmg,1Weak(3→4))->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=34 taken=0
  R2[Stabbot: Atk(11), Debuff+Fabricator: Atk(13), Summon]: Adrenaline(+1energy,exhaust:1)->Footwork(power:+Dexterity(2))->Deflect(+6blk)->Defend(10dmg,+14blk)->Tracking+(power:+Tracking(2))->Flick-Flack(18dmg) | dealt=28 taken=4
  R3[Stabbot: Atk(11), Debuff+Zapbot: Atk(16)+Fabricator: Atk(13), Summon]: Exterminate(88dmg)->Skewer+(power:-Well-Laid Plans,power:-Dexterity,power:-Tracking,power:-Frail) | dealt=119 taken=0

F39 [monster] multi:Cubex Construct+Cubex Construct+Punch Construct (4R, HP 64->60, loss=4, WIN)
  R1[Punch Construct: Defend+Cubex Construct: Buff+Cubex Construct: Buff]: Adrenaline(+1energy,exhaust:1)->Tracking+(power:+Tracking(2))->Survivor+(+11blk)->Flick-Flack(12dmg)->Leading Strike(+17blk)->Dash+(exhaust:1)->Shiv->Shiv(+4blk)->Strike(10dmg,+4blk)->Deflect | dealt=22 taken=0
  R2[Punch Construct: Atk(14)+Cubex Construct: Atk(9), Buff+Cubex Construct: Atk(9), Buff]: Blade Dance+(exhaust:1)->Cloak and Dagger(+6blk)->Shiv*2->Defend(5dmg,+10blk)->Shiv(+4blk)->Shiv*2->Well-Laid Plans+(power:+Well-Laid Plans(2)) | dealt=5 taken=3
  R3[Punch Construct: Atk(5x2=10), Debuff+Cubex Construct: Atk(11), Buff]: Expose(1+Vulnerable(2),exhaust:1)->Blade of Ink->Shiv(9dmg,1+Weak(1),exhaust:1)->Shiv(18dmg,1Weak(1→2))->Defend(10dmg,+5blk)->Strike+(9dmg,+4blk)->Skewer+->Prepared+ | dealt=63 taken=1
  R4[Punch Construct: Defend]: Neutralize(3dmg,1+Weak(1))->Blade Dance(exhaust:1)->Shiv(6dmg)->Shiv(6dmg,+4blk)->Shiv(6dmg)->Exterminate(power:-Tracking,power:-Well-Laid Plans,power:-Weak) | dealt=21 taken=0

F45 [monster] Globe Head (3R, HP 60->52, loss=8, WIN)
  R1[Globe Head: Atk(9), Debuff]: Blade of Ink+->Shiv(6dmg,1Weak(1→2),exhaust:1)->Shiv(6dmg,1Weak(2→3))->Shiv(6dmg,+4blk,1Weak(3→4))->Tracking+(power:+Tracking(2))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Survivor+(+11blk) | dealt=18 taken=8
  R2[Globe Head: Atk(4x3=12)]: Piercing Wail(2+Strength(-6),+Piercing Wail(6),exhaust:1)->Adrenaline+(+2energy,exhaust:1)->Deflect(5dmg,+3blk)->Prepared+->Dash+(26dmg,+9blk)->Blade Dance+(exhaust:1)->Defend(5dmg,+6blk)->Shiv(8dmg,exhaust:1)->Shiv(8dmg,+4blk)->Shiv(8dmg)->Shiv(8dmg)->Cloak and Dagger(+4blk)->Shiv(8dmg,+4blk)->Strike+(18dmg) | dealt=94 taken=0
  R3[Globe Head: Atk(12), Buff]: Neutralize(10dmg,1Weak(2→3))->Skewer+(power:-Tracking,power:-Well-Laid Plans,power:-Frail) | dealt=10 taken=0

F48 [boss] Test Subject (12R, HP 52->43, loss=9, WIN)
  R1[Test Subject #C64: Atk(15)]: Expose(2+Vulnerable(2),+Strength(2),exhaust:1)->Blade of Ink+(1Strength(2→4))->Shiv(12dmg,1Weak(1→2),exhaust:1)->Shiv(12dmg,1Weak(2→3))->Dash+(22dmg,+17blk)->Footwork+(power:+Dexterity(3))->Well-Laid Plans+(power:+Well-Laid Plans(2))->Deflect(5dmg,+7blk,1Strength(4→6))->Shiv(12dmg,1Weak(3→4)) | dealt=63 taken=0
  R2[Test Subject #C64: Atk(15), Debuff]: Neutralize(10dmg,1Weak(3→4))->Exterminate(27dmg,4-Enrage,-Weak,-Vulnerable,-Strength) | dealt=10 taken=0
  R3[Test Subject #C64: Atk(10x3=30)]: Footwork+(power:Dexterity(3→6))->Cloak and Dagger(+12blk)->Shiv(6dmg,exhaust:1)->Blade Dance(exhaust:1)->Shiv(6dmg)->Shiv(6dmg,+4blk)->Shiv(6dmg) | dealt=24 taken=0
  R4[Test Subject #C64: Atk(10x4=40)]: Adrenaline+(+2energy,exhaust:1)->Prepared+->Flick-Flack(5dmg,2+Strength(-6),+Piercing Wail(6),exhaust:1)->Piercing Wail(power:+Tracking(2))->Tracking+(+11blk)->Backflip(5dmg)->Leading Strike(6dmg,+4blk)->Shiv(6dmg)->Shiv(8dmg)->Strike(+11blk)->Defend->Prepared+(7dmg,1+Weak(1))->Flick-Flack->Neutralize->Skewer+ | dealt=37 taken=0
  R5[Test Subject #C64: Atk(10x5=50)]: Blade Dance+(exhaust:1)->Shiv(6dmg)->Shiv(6dmg)->Shiv(6dmg,+4blk)->Dash+(15dmg,+19blk)->Survivor+(+17blk)->Defend(5dmg,+11blk) | dealt=38 taken=0
  R6[Test Subject #C64: Atk(10x6=60)]: Blade of Ink+->Shiv(8dmg,1+Weak(1))->Shiv(16dmg,1Weak(1→2))->Shiv(16dmg,+4blk,1Weak(2→3))->Exterminate(40dmg,1-Weak) | dealt=40 taken=0
  R7[Test Subject #C64: Atk(10x3=30)]: Neutralize(1dmg,1+Weak(1))->Shiv(1dmg)->Defend+(+14blk)->Defend(1dmg,+22blk)->Cloak and Dagger(+12blk)->Shiv(1dmg,+4blk) | dealt=4 taken=0
  R8[Test Subject #C64: Atk(45)]: Blade of Ink+->Shiv(8dmg,1+Weak(1))->Shiv(16dmg,1Weak(1→2))->Shiv(16dmg,+4blk,1Weak(2→3))->Dash+(30dmg,+19blk)->Backflip(+11blk)->Exterminate(40dmg) | dealt=110 taken=0
  R9[Test Subject #C64: StatusCard(3), Buff]: Deflect(+10blk)->Leading Strike(1dmg)->Shiv(1dmg)->Shiv(1dmg,+4blk)->Survivor+(+17blk)->Defend(1dmg,+11blk) | dealt=4 taken=0
  R10[Test Subject #C64: Atk(9x3=27)]: Deflect(+10blk)->Neutralize(14dmg,1Weak(1→2))->Strike(16dmg)->Leading Strike(10dmg,+4blk)->Strike+(22dmg)->Shiv(12dmg)->Shiv(12dmg,+4blk)->Skewer+(26dmg) | dealt=112 taken=9
  R11[Test Subject #C64: Atk(35)]: Prepared+->Survivor+(+17blk)->Defend(1dmg,+11blk)->Defend(+22blk) | dealt=1 taken=0
  R12[Test Subject #C64: StatusCard(3), Buff]: Blade of Ink+->Shiv(8dmg,1+Weak(1))->Shiv(16dmg,1Weak(1→2))->Shiv(16dmg,+4blk,1Weak(2→3))->Exterminate(power:-Strength,power:-Dexterity,power:-Well-Laid Plans,power:-Tracking) | dealt=40 taken=0

### Non-combat Decisions (185 decisions)
F1 [event] choose_event_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Booming Conch combined with Ring of the Snake gives 9 cards on turn 1 against Elites. Turn 1 consistency is critical in Elite fights, allowing me to play my best powers or burst damage immediately.
  strategic_note: Foundation deck: looking for early damage cards and elite-killing tools, relying on massive turn 1 draw from Booming Conch + Ring of the Snake to dominate Elite fights.

F1 [event] choose_event_option (option_index=0) | source=auto
  HP 56->56 | Gold 99->99 | Deck 13->13
  deck_change: no deck change
  reasoning: Only option: Proceed

F1 [map] choose_map_node (option_index=0) | source=llm
  HP 56->56 | Gold 99->0 | Deck 13->13
  deck_change: no deck change
  reasoning: Starting the recommended monster-farming sequence to build deck strength and gold. This path leads to a late Act 1 elite, which maximizes the value of Booming Conch once the deck has more damage cards, while minimizing early risk.
  strategic_note: Foundation deck: using turn 1 draw from Ring of the Snake and Booming Conch to find high-impact damage and block early; prioritizing monster fights floors 1-3 to find essential attacks before the first elite.

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 99->114 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim gold: 15 Gold

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 114->114 | Deck 13->13
  deck_change: no deck change
  reasoning: Claim potion: Cure All

F2 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 114->114 | Deck 13->13
  deck_change: no deck change
  reasoning: Open card reward

F2 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 55->55 | Gold 114->114 | Deck 13->14
  deck_change: picked Flick-Flack
  reasoning: We desperately need damage on Floor 2, and Flick-Flack is the only attack offered. It provides much-needed AoE for Act 1 multi-enemy fights and Sentries, and synergizes perfectly with our starting Survivor for a free 6 AoE damage play.
  strategic_note: Foundation plan: prioritize frontload damage and efficient AoE to survive Act 1 elites. Leverage massive turn 1 draw from Booming Conch + Ring of the Snake to burst threats early.

F2 [map] choose_map_node (option_index=0) | source=auto
  HP 55->55 | Gold 114->0 | Deck 14->14
  deck_change: no deck change
  reasoning: Only path: Monster

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 114->128 | Deck 14->14
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F3 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 55->55 | Gold 128->128 | Deck 14->14
  deck_change: no deck change
  reasoning: Open card reward

F3 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 55->55 | Gold 128->128 | Deck 14->15
  deck_change: picked Expose
  reasoning: We are in Phase 1 (Foundation) and urgently need damage for Act 1 Elites. While Burst is a powerful Rare for future scaling, we currently have no good skills to duplicate, making it a dead draw. Expose costs 0, acts as a temporary damage multiplier via Vulnerable, strips early Block/Artifact, and exhausts itself to keep the deck lean.
  strategic_note: Foundation phase: prioritize immediate frontload damage and efficient block to survive Act 1. Look for high-impact attacks or poison/shiv engine starters. Avoid expensive or purely synergistic cards until a core engine is established.

F3 [map] choose_map_node (option_index=1) | source=llm
  HP 55->55 | Gold 128->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the recommended route to an Unknown node. I have 128 gold and 55 HP, making an early shop less ideal than an event that could provide a card removal, transformation, or a powerful relic. I want to save gold for a high-impact shop later in the act while building deck strength through events or monsters before the mandatory elite.
  strategic_note: Foundation deck: leveraging turn 1 draw from Booming Conch and Ring of the Snake to find early damage and block; prioritizing card quality and removals to prepare for the late-act Elite and Boss.

F4 [event] choose_event_option (option_index=0) | source=llm
  HP 55->55 | Gold 128->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Enchanting an attack with Sharp 2 is highly valuable early in Act 1. I plan to enchant Flick-Flack, increasing its AoE damage from 6 to 8, which will significantly improve my performance in multi-enemy hallway fights and against Gremlin/Slime elites.
  strategic_note: Foundation deck: looking for early damage cards and elite-killing tools, relying on massive turn 1 draw from Booming Conch + Ring of the Snake to dominate Elite fights.

F4 [card_select] select_deck_card (option_index=5) | source=llm
  HP 55->55 | Gold 128->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Upgrading Neutralize gives +1 Weak duration, making it apply 2 turns of Weak for 0 energy. This is a critical early upgrade for surviving Elite fights, providing cheap and reliable mitigation.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces. Use Survivor to trigger Flick-Flack for free AoE.

F4 [event] choose_event_option (option_index=0) | source=auto
  HP 55->55 | Gold 128->128 | Deck 15->15
  deck_change: no deck change
  reasoning: Only option: Proceed

F4 [map] choose_map_node (option_index=1) | source=llm
  HP 55->55 | Gold 128->0 | Deck 15->15
  deck_change: no deck change
  reasoning: Following the established route to maximize monster encounters for card rewards and gold before the first rest site. The deck needs more foundational damage and block before hitting the late-act Elite.
  strategic_note: Foundation deck: leveraging turn 1 draw from Booming Conch and Ring of the Snake to find early damage and block; prioritizing card quality and removals to prepare for the late-act Elite and Boss.

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 128->138 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim gold: 10 Gold

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 138->138 | Deck 15->15
  deck_change: no deck change
  reasoning: Claim potion: Flex Potion

F5 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 51->51 | Gold 138->138 | Deck 15->15
  deck_change: no deck change
  reasoning: Open card reward

F5 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 51->51 | Gold 138->138 | Deck 15->16
  deck_change: picked Skewer
  reasoning: We lack significant frontload damage. Skewer is a flexible X-cost attack that synergizes excellently with Expose (apply 2 Vulnerable for 0 energy) to provide burst damage, helping us take down Act 1 Elites.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine. Expose into Skewer is our primary burst combo; look for card draw to assemble it more consistently and skip narrow synergy pieces until we find a core engine.

F5 [map] choose_map_node (option_index=0) | source=auto
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Unknown

F6 [event] choose_event_option (option_index=0) | source=llm
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: We are at a comfortable 51/70 HP and have multiple Rest Sites coming up on our route. Taking the Spiral enchant on a Strike or Defend gives us a highly efficient 1-cost card (12 damage or 10 block) that will greatly help in early and mid-Act 1 combats without needing to rest.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer) and powerful basic upgrades; prioritize securing more elite-killing tools and card removals.

F6 [card_select] select_deck_card (option_index=5) | source=llm
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: Strikes are our highest priority for removal, so enchanting one is risky since we'd eventually want to remove it. Defends stay in the deck longer and are more useful, making them a safer target for an enchantment.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F6 [event] choose_event_option (option_index=0) | source=auto
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F6 [map] choose_map_node (option_index=0) | source=auto
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: Only path: Unknown

F7 [event] choose_event_option (option_index=0) | source=auto
  HP 51->51 | Gold 138->138 | Deck 16->16
  deck_change: no deck change
  reasoning: Only option: Proceed

F7 [map] choose_map_node (option_index=1) | source=llm
  HP 51->51 | Gold 138->0 | Deck 16->16
  deck_change: no deck change
  reasoning: Choosing the monster fight to accumulate gold and card rewards before the upcoming shop and elite. 51 HP is healthy enough for a hallway encounter, and early card quality is essential to utilize the Booming Conch's turn 1 draw bonus in the upcoming elite fight.
  strategic_note: Foundation deck: focusing on high-value card rewards and gold accumulation to prepare for the mid-act Elite; leveraging Booming Conch for strong turn-1 starts while prioritizing defensive consistency.

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 138->150 | Deck 16->16
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F8 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 48->48 | Gold 150->150 | Deck 16->16
  deck_change: no deck change
  reasoning: Open card reward

F8 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 48->48 | Gold 150->150 | Deck 16->17
  deck_change: picked Dash
  reasoning: Dash compresses efficient block and damage into a single card draw, which is perfect for surviving Act 1 encounters. We are still in the Foundation phase and need solid standalone tools.
  strategic_note: Foundation plan: survive with frontload (Dash, Skewer) and efficient block while looking for a real scaling engine (poison or discard/shivs). Keep options open.

F8 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 150->150 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: RestSite

F9 [rest_site] choose_rest_option (option_index=1, smith_card_index=14, note_scope=run, note_triggers=all) | source=llm
  HP 48->48 | Gold 150->150 | Deck 17->17
  deck_change: upgraded Skewer->Skewer+
  reasoning: With 48 HP and another rest site coming up right after the treasure chest, healing is unnecessary. Skewer is our main burst damage card, and upgrading it increases its damage by 3 per energy spent, significantly improving our ability to burst down enemies and elites.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer+) and basic upgrades; prioritize securing more elite-killing tools and card removals.

F9 [rest_site] proceed | source=auto
  HP 48->48 | Gold 150->150 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F9 [map] choose_map_node (option_index=0) | source=auto
  HP 48->48 | Gold 150->150 | Deck 17->17
  deck_change: no deck change
  reasoning: Only path: Treasure

F10 [treasure] open_chest | source=random
  HP 48->48 | Gold 150->185 | Deck 17->17
  deck_change: no deck change
  reasoning: Open chest

F10 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 48->48 | Gold 185->185 | Deck 17->17
  deck_change: upgraded Strike->Strike+; changed: +Strike+; -Strike
  reasoning: Claim: Whetstone

F10 [treasure] proceed | source=random
  HP 48->48 | Gold 185->185 | Deck 17->17
  deck_change: no deck change
  reasoning: Proceed from treasure

F10 [map] choose_map_node (option_index=1) | source=llm
  HP 48->48 | Gold 185->185 | Deck 17->17
  deck_change: no deck change
  reasoning: Following the recommended path to a Rest Site. With 48/70 HP and an Elite fight approaching in two nodes, I need to Smith a key card (likely Skewer or a defense card) to ensure I can take the Elite with minimal HP loss. The Booming Conch relic makes Elites more manageable, but Act 1 Silent still struggles with burst damage early on.
  strategic_note: Foundation deck: using massive turn 1 draw from Booming Conch and Ring of the Snake to find Skewer or key block cards; prioritizing upgrades at Rest Sites and card removals at the upcoming Shop to refine the draw pool for Elite and Boss scaling.

F11 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 48->48 | Gold 185->185 | Deck 17->17
  deck_change: upgraded Dash->Dash+
  reasoning: With 48 HP we have plenty of health to Smith. Upgrading Dash to Dash+ adds 3 damage and 3 block, making it an incredibly efficient 2-cost play (13 damage, 13 block). This raw stat increase is extremely valuable for surviving the Act 1 Boss and elite fights.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage (like Skewer+ and Dash+) and basic upgrades; prioritize securing more elite-killing tools and card removals.

F11 [rest_site] proceed | source=auto
  HP 48->48 | Gold 185->185 | Deck 17->17
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F11 [map] choose_map_node (option_index=0) | source=llm
  HP 48->48 | Gold 185->0 | Deck 17->17
  deck_change: no deck change
  reasoning: With 48 HP and the Booming Conch relic providing extra draw specifically for Elite combats, I am well-positioned to take this fight. Securing a relic and a potential rare card is necessary to scale for the Act 1 boss, and the upcoming shop allows me to spend the accumulated 185 gold and potential elite winnings immediately.
  strategic_note: Foundation deck: using high turn 1 draw from Booming Conch and Ring of the Snake to find key cards early; prioritize Elite rewards and card removals at shops to thin the deck for consistent damage.

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 185->215 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim gold: 30 Gold

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 215->215 | Deck 17->17
  deck_change: no deck change
  reasoning: Claim relic: Lasting Candy

F12 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 215->215 | Deck 17->17
  deck_change: no deck change
  reasoning: Open card reward

F12 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 41->41 | Gold 215->215 | Deck 17->18
  deck_change: picked Backflip
  reasoning: The deck currently lacks any repeatable card draw to cycle through our deck and find key cards like Dash+ and Skewer+. Backflip is a premium common card that provides generic mitigation and card draw, fitting perfectly into our Phase 1 foundation.
  strategic_note: Foundation plan: Survive Act 1 with frontload damage (Dash+, Skewer+) while taking generic efficient mitigation and draw (Backflip). Still looking for a core scaling engine, so skip narrow synergies until we find a payoff.

F12 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 215->215 | Deck 18->18
  deck_change: no deck change
  reasoning: Only path: Shop

F13 [shop] buy_card (option_index=3) | source=plan
  HP 41->41 | Gold 215->190 | Deck 18->19
  deck_change: bought Blade Dance
  reasoning: Shop plan [1/3]: On sale and a premium high-efficiency damage card. Fits well with Expose (Vulnerable) and starts our transition into Shivs.

F13 [shop] buy_card (option_index=1) | source=plan
  HP 41->41 | Gold 190->139 | Deck 19->20
  deck_change: bought Leading Strike
  reasoning: Shop plan [2/3]: Another efficient source of physical damage and Shivs. Helps increase our overall damage output and sets us up for future Shiv or attack synergies.

F13 [shop] remove_card_at_shop | source=plan
  HP 41->41 | Gold 139->139 | Deck 20->20
  deck_change: no deck change
  reasoning: Shop plan [3/3]: Removing a basic Strike thins the deck, making it easier to draw our upgraded attacks, Block cards, and new Shiv generators consistently.

F13 [card_select] select_deck_card (option_index=0) | source=llm
  HP 41->41 | Gold 139->39 | Deck 20->19
  deck_change: lost Strike
  reasoning: Standard card removal. Removing an unupgraded Strike is the best way to thin the deck and improve the consistency of drawing our better cards like Dash+, Skewer+, and our Shiv generators.
  strategic_note: Foundation plan: survive with frontload and efficient block while looking for a real scaling engine; take cheap draw or high-impact damage, skip narrow synergy pieces.

F13 [shop] close_shop_inventory | source=llm
  HP 41->41 | Gold 39->39 | Deck 19->19
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F13 [shop] proceed | source=auto
  HP 41->41 | Gold 39->39 | Deck 19->19
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F13 [map] choose_map_node (option_index=1) | source=llm
  HP 41->41 | Gold 39->39 | Deck 19->19
  deck_change: no deck change
  reasoning: I have 39 gold and 41 HP. Taking an Elite (index 0) right after a shop where I couldn't buy anything meaningful is risky, especially since I just fought an Elite and two Rest Sites are coming up. The Unknown node (index 1) follows the recommended route and provides a safer path to the boss while potentially offering an event that grants more value than a low-HP elite fight.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to find key damage like Skewer; prioritize securing more scaling and card removals while maintaining enough HP to survive the Act 1 boss.

F14 [event] choose_event_option (option_index=0) | source=llm
  HP 41->41 | Gold 39->39 | Deck 19->20
  deck_change: added Injury
  reasoning: With 41 HP right before the Act 1 Boss, taking a difficult fight against Punch Constructs could force a rest or even be fatal. Taking the Injury curse for a random relic is safer; we have Ring of the Snake and Survivor to mitigate the curse during the Boss fight.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to find key damage like Skewer; prioritize securing more scaling and card removals while maintaining enough HP to survive the Act 1 boss.

F14 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 41->41 | Gold 39->39 | Deck 20->20
  deck_change: upgraded Defend->Defend+, Survivor->Survivor+
  reasoning: Claim relic: War Paint

F14 [event] choose_event_option (option_index=0) | source=auto
  HP 41->41 | Gold 39->39 | Deck 20->20
  deck_change: no deck change
  reasoning: Only option: Proceed

F14 [map] choose_map_node (option_index=0) | source=llm
  HP 41->41 | Gold 39->39 | Deck 20->20
  deck_change: no deck change
  reasoning: With 41 HP and having already faced one Elite this Act, an Unknown node is safer than a Monster or another Elite. This preserves HP for the final Rest Site and the Act 1 Boss, following the recommended route.
  strategic_note: Foundation deck: utilizing Booming Conch and Ring of the Snake for heavy turn 1 draw to find Skewer+ and Dash+; the goal is to survive to the Act 1 boss with enough HP to leverage these front-loaded damage pieces.

F15 [treasure] open_chest | source=random
  HP 41->41 | Gold 39->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Open chest

F15 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 41->41 | Gold 76->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim: Ornamental Fan

F15 [treasure] proceed | source=random
  HP 41->41 | Gold 76->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Proceed from treasure

F15 [map] choose_map_node (option_index=0) | source=auto
  HP 41->41 | Gold 76->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: RestSite

F16 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 41->62 | Gold 76->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Boss is next and we are at 59% HP. Healing 21 HP to reach 62/70 will significantly increase survivability against the Act 1 Boss.
  strategic_note: Foundation deck: leveraging massive turn 1 draw from Booming Conch and Ring of the Snake to quickly find key damage like Skewer+ and Dash+; prioritize surviving the Act 1 boss, then focus on securing scaling tools, card removals, and block.

F16 [rest_site] proceed | source=auto
  HP 62->62 | Gold 76->76 | Deck 20->20
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F16 [map] choose_map_node (option_index=0) | source=auto
  HP 62->62 | Gold 76->0 | Deck 20->20
  deck_change: no deck change
  reasoning: Only path: Boss

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 19->19 | Gold 76->151 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 19->19 | Gold 151->151 | Deck 20->20
  deck_change: no deck change
  reasoning: Claim potion: Bottled Potential

F17 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 19->19 | Gold 151->151 | Deck 20->20
  deck_change: no deck change
  reasoning: Open card reward

F17 [card_reward] resolve_rewards (option_index=0) | source=llm
  HP 19->19 | Gold 151->151 | Deck 20->21
  deck_change: picked Tracking
  reasoning: Tracking is a potent scaling engine that doubles our Attack damage against Weak targets. While we currently only have Neutralize to apply Weak, we can actively draft cards like Leg Sweep, Sucker Punch, and Crippling Cloud in Act 2. With our Shiv generators, Skewer+, and Expose (Vulnerable stacks multiplicatively with Tracking), this provides the boss-killing scaling we desperately need.
  strategic_note: Committed Tracking/Attacks plan: Prioritize drafting consistent sources of Weakness and efficient attacks (especially Shivs and multi-hits) to capitalize on Tracking's double damage. Needs more draw to consistently assemble the combo; avoid bloated non-synergistic skills.

F17 [map] choose_map_node (option_index=0) | source=auto
  HP 19->59 | Gold 151->151 | Deck 21->21
  deck_change: no deck change
  reasoning: Only path: Ancient

F18 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=deck_building) | source=llm
  HP 59->59 | Gold 151->151 | Deck 21->21
  deck_change: no deck change
  reasoning: Pael's Blood provides an unconditional +1 draw every turn, which gives us incredible consistency for the rest of the run. While Tears offers strong energy scaling for Skewer, the setup requirement can be clunky, and Tooth is a temporary boost that pollutes the deck later. Card draw is universally powerful.
  strategic_note: Foundation deck: utilizing massive card draw from relics (Ring of the Snake, Pael's Blood) to quickly cycle and find key front-loaded damage (Skewer+, Dash+) while scaling with Tracking. Needs more energy generation and consistent block engine for Act 2 Boss.

F18 [event] choose_event_option (option_index=0) | source=auto
  HP 59->59 | Gold 151->151 | Deck 21->21
  deck_change: no deck change
  reasoning: Only option: Proceed

F18 [map] choose_map_node (option_index=2) | source=llm
  HP 59->59 | Gold 151->0 | Deck 21->21
  deck_change: no deck change
  reasoning: Choosing the recommended route at column 5 to begin building deck strength for Act 2. HP is healthy (59/70), and starting with monsters provides gold and card rewards needed before hitting shops and rest sites. This path leads toward a treasure and multiple rest sites which aligns with the winning patterns for Act 2.
  strategic_note: Foundation phase: currently prioritizing monster fights to build card quality and gold. The goal is to establish a solid defensive core or scaling damage engine before the mid-act shops. Use HP as a resource to secure better cards, but prioritize upgrades at future rest sites to ensure survival against the Act 2 boss.

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 151->162 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 162->162 | Deck 21->21
  deck_change: no deck change
  reasoning: Claim potion: Dexterity Potion

F19 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 162->162 | Deck 21->21
  deck_change: no deck change
  reasoning: Open card reward

F19 [card_reward] resolve_rewards (option_index=3) | source=llm
  HP 59->59 | Gold 162->162 | Deck 21->22
  deck_change: picked Well-Laid Plans+
  reasoning: Well-Laid Plans+ is an incredibly powerful tool for holding combo pieces like Tracking, Expose, and Skewer+ for massive burst turns. It also holds defensive cards like Survivor+ or Dash+ exactly when needed. Being upgraded already makes it an easy pick.
  strategic_note: Committed to physical damage scaled by Tracking and Vulnerable. Look for multi-hit attacks, Weak sources, and draw. Use Well-Laid Plans to hold Expose, Tracking, and big attacks for a burst turn. Avoid poison or disjointed mechanics.

F19 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 162->0 | Deck 22->22
  deck_change: no deck change
  reasoning: Only path: Monster

F20 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 59->59 | Gold 162->169 | Deck 22->22
  deck_change: no deck change
  reasoning: Claim gold: 7 Gold

F20 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 59->59 | Gold 169->169 | Deck 22->22
  deck_change: no deck change
  reasoning: Open card reward

F20 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 59->59 | Gold 169->169 | Deck 22->23
  deck_change: picked Prepared+
  reasoning: Prepared+ is an exceptional 0-cost hand filter that helps cycle past our curses (Injury, Ascender's Bane), triggers our Sly card (Flick-Flack) for free, and digs for our win condition (Tracking + heavy attacks).
  strategic_note: Foundation plan: utilize Tracking and physical damage (Shivs, Skewer) as our core engine. Use Prepared+ to cycle past curses and set up heavy attack turns on Weak enemies.

F20 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 169->169 | Deck 23->23
  deck_change: no deck change
  reasoning: Only path: Unknown

F21 [event] choose_event_option (option_index=0) | source=llm
  HP 59->59 | Gold 169->169 | Deck 23->24
  deck_change: added Exterminate
  reasoning: Exterminate is a fantastic 1-cost AoE card that deals 12 damage to all enemies and hits 4 times, making it incredibly effective against Act 2 Byrds (knocking them down instantly) and multi-enemy encounters like Slavers and Gremlin Leader.
  strategic_note: Foundation deck: utilizing massive card draw from relics to quickly cycle and find key front-loaded damage (Skewer+, Dash+) and AoE (Exterminate) while scaling with Tracking. Needs more energy generation and consistent block engine for Act 2 Boss.

F21 [event] choose_event_option (option_index=0) | source=auto
  HP 59->59 | Gold 169->169 | Deck 24->24
  deck_change: no deck change
  reasoning: Only option: Proceed

F21 [map] choose_map_node (option_index=0) | source=auto
  HP 59->59 | Gold 169->0 | Deck 24->24
  deck_change: no deck change
  reasoning: Only path: Monster

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 169->182 | Deck 24->24
  deck_change: no deck change
  reasoning: Claim gold: 13 Gold

F22 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 31->31 | Gold 182->182 | Deck 24->24
  deck_change: no deck change
  reasoning: Open card reward

F22 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 31->31 | Gold 182->182 | Deck 24->25
  deck_change: picked Blade of Ink
  reasoning: Blade of Ink generates Inky Shivs which apply Weak. This perfectly enables Tracking, allowing all subsequent attacks to deal double damage. Combined with Expose for Vulnerable, this provides massive multiplicative damage scaling for our deck's shivs.
  strategic_note: Committed to Shiv/Weak synergy with Tracking and Expose. Prioritize applying Weak with Inky Shivs or Neutralize before unloading other attacks for double damage. Focus on adding more Shiv generation and card draw to find combo pieces faster.

F22 [map] choose_map_node (option_index=0) | source=llm
  HP 31->31 | Gold 182->0 | Deck 25->25
  deck_change: no deck change
  reasoning: HP is dangerously low (31/70) for Act 2 hallway fights. The Unknown node provides a much higher chance of survival or a non-combat event compared to a guaranteed Monster encounter, aligning with the survival-focused routing strategy for this act.
  strategic_note: Foundation phase: currently prioritizing survival through high-variance Act 2 events while avoiding chip damage from hallway fights. Need to stabilize HP at the upcoming rest sites and look for high-impact defensive scaling or reliable card draw to capitalize on Booming Conch in future elite encounters.

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 182->193 | Deck 25->25
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F23 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 15->15 | Gold 193->193 | Deck 25->25
  deck_change: no deck change
  reasoning: Open card reward

F23 [card_reward] resolve_rewards (option_index=2) | source=llm
  HP 15->15 | Gold 193->193 | Deck 25->26
  deck_change: picked Piercing Wail
  reasoning: Piercing Wail is exceptional mitigation against multi-hit attacks. We have Well-Laid Plans+, which allows us to retain Piercing Wail precisely for the Knowledge Demon's brutal Turn 3 multi-attack, effectively neutralizing the fight's biggest defensive check. It also exhausts, so it won't bloat the deck on subsequent cycles.
  strategic_note: Committed to Shiv/Fan synergy with Well-Laid Plans utility. Keep retaining key defensive/burst cards like Piercing Wail for exact enemy burst turns. Look for Accuracy or strong scaling damage pieces next; prioritize upgrading Shiv generators and removing basics.

F23 [map] choose_map_node (option_index=0) | source=auto
  HP 15->15 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: RestSite

F24 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 15->36 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: HP is critically low at 15/70. An upcoming hallway fight or dangerous event could easily end the run. Resting provides 21 HP, ensuring survival for the next node.
  strategic_note: Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs consistent block engine and energy generation for the Act 2 Boss.

F24 [rest_site] proceed | source=auto
  HP 36->36 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F24 [map] choose_map_node (option_index=0) | source=llm
  HP 36->36 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: HP is at 36 (51%), which is dangerously low for Act 2. My current route intelligence and strategy for Act 2 emphasize avoiding elites and combats when HP is below 50. Taking the Unknown node instead of the Elite is essential for survival, aiming to reach the upcoming Rest Site and Treasure to stabilize. The Booming Conch relic is strong, but I cannot afford to risk an Elite fight at this health threshold.
  strategic_note: Foundation deck: currently prioritizing survival and pathing through safe nodes to reach rest sites. Need to stabilize HP and find a definitive scaling engine (poison or shivs) before the next boss.

F25 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 36->30 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Push costs only 6 HP and adds 8 burst damage to an attack for the rest of the run. We have multiple Rest Sites upcoming to heal the HP loss, and keeping Bottled Potential is better for the Act 2 Boss than 10 Max HP.
  strategic_note: Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs consistent block engine and energy generation for the Act 2 Boss.

F25 [card_select] select_deck_card (option_index=8) | source=llm
  HP 30->30 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Exterminate is a multi-hit AoE attack (deals 3 damage 4 times). Any damage-oriented enchantment will scale incredibly well with the multiple hits, making it the highest impact target.
  strategic_note: Committed shiv/attack plan: generate shivs to trigger Ornamental Fan for block while using Exterminate and Skewer for AoE/burst damage. Needs more draw/discard tools and remove Strikes.

F25 [event] choose_event_option (option_index=0) | source=auto
  HP 30->30 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Only option: Proceed

F25 [map] choose_map_node (option_index=0) | source=llm
  HP 30->30 | Gold 193->193 | Deck 26->26
  deck_change: no deck change
  reasoning: Following the established route to reach a mandatory Rest Site. At 30 HP, I need the heal before the next potential combat, and the treasure node provides a relic boost without risk.
  strategic_note: Foundation deck: utilizing card draw from relics to cycle for front-loaded damage while scaling with Tracking. Needs better block to protect the low HP pool; prioritising survival and healing at rest sites before seeking removals or defensive upgrades at upcoming shops.

F26 [treasure] open_chest | source=random
  HP 30->30 | Gold 193->231 | Deck 26->26
  deck_change: no deck change
  reasoning: Open chest

F26 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: no deck change
  reasoning: Claim: Letter Opener

F26 [treasure] proceed | source=random
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: no deck change
  reasoning: Proceed from treasure

F26 [map] choose_map_node (option_index=0) | source=auto
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: no deck change
  reasoning: Only path: RestSite

F27 [rest_site] choose_rest_option (option_index=1, smith_card_index=12) | source=llm
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: upgraded Tracking->Tracking+
  reasoning: We have two consecutive non-combat nodes coming up (Shop then another Rest Site), so our current 30 HP is perfectly safe. Upgrading Tracking to reduce its cost from 2 to 1 is a massive consistency boost, making it much easier to play our key scaling power on the turn it is drawn.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Act 2 Boss.

F27 [rest_site] proceed | source=auto
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F27 [map] choose_map_node (option_index=0) | source=llm
  HP 30->30 | Gold 231->231 | Deck 26->26
  deck_change: no deck change
  reasoning: With 231 gold and 30/70 HP, visiting a shop is significantly safer and more productive than a monster fight. I need to look for sustain, damage mitigation, or card removal to stabilize before the Act 2 boss.
  strategic_note: Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Needs a reliable block engine or sustain as HP is low (30/70); prioritize finding defensive solutions or card removal in the upcoming shop.

F28 [shop] buy_card (option_index=3) | source=plan
  HP 30->30 | Gold 231->207 | Deck 26->27
  deck_change: bought Cloak and Dagger
  reasoning: Shop plan [1/3]: Highly efficient at generating both Fan/Letter Opener triggers while providing immediate block.

F28 [shop] remove_card_at_shop | source=plan
  HP 30->30 | Gold 207->207 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan [2/3]: Removing the Injury curse significantly improves deck consistency and cycling speed.

F28 [card_select] select_deck_card (option_index=0) | source=llm
  HP 30->30 | Gold 207->57 | Deck 27->26
  deck_change: lost Injury
  reasoning: Injury is a curse that clogs the deck. Removing it significantly improves our consistency for finding our key Tracking and Shiv engines.
  strategic_note: Committed Shiv/Tracking plan: Apply Weak to enemies, then use Shivs and attacks to deal double damage. Keep deck thin of curses and unplayable cards to find Tracking and Weak applications faster.

F28 [shop] buy_card (option_index=2) | source=plan
  HP 30->30 | Gold 57->9 | Deck 26->27
  deck_change: bought Deflect
  reasoning: Shop plan [3/3]: A free 0-cost skill that provides block and increments the count for both Ornamental Fan and Letter Opener without costing energy.

F28 [shop] close_shop_inventory | source=plan
  HP 30->30 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F28 [shop] proceed | source=auto
  HP 30->30 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F28 [map] choose_map_node (option_index=1) | source=llm
  HP 30->30 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: With only 30 HP, attempting an Act 2 Elite is extremely risky despite the Booming Conch synergy. Taking the Rest Site follows the survival-oriented route intelligence for Act 2 and ensures I can reach the boss.
  strategic_note: Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking; priority is now survival and reaching the Act 2 boss through rest sites.

F29 [rest_site] choose_rest_option (option_index=0, note_scope=run, note_triggers=all) | source=llm
  HP 30->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: At 30 HP, facing an Act 2 Elite next is extremely risky since they can deal 30+ damage on turn 1 (e.g., Slavers, Book of Stabbing). Healing to 51 HP provides the necessary buffer to survive, and we have another Rest Site at Floor 32 to Smith before the boss.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Act 2 Boss.

F29 [rest_site] proceed | source=auto
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F29 [map] choose_map_node (option_index=0) | source=auto
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Unknown

F30 [shop] close_shop_inventory | source=llm
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F30 [shop] proceed | source=auto
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F30 [map] choose_map_node (option_index=1) | source=llm
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Following the recommended route to the Shop. Although I only have 9 gold, visiting a shop allows for a potential free card removal event or seeing a key card I might be able to afford if a rare event occurs, and more importantly, it avoids a potentially lethal Act 2 hallway fight at 51 HP before the final rest site.
  strategic_note: Foundation deck: utilizing massive card draw from relics to cycle and find key front-loaded damage while scaling with Tracking. Seeking more consistent block and a finisher to convert draw into damage.

F31 [shop] close_shop_inventory | source=llm
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Shop plan: nothing to buy —

F31 [shop] proceed | source=auto
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F31 [map] choose_map_node (option_index=0) | source=auto
  HP 51->51 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: RestSite

F32 [rest_site] choose_rest_option (option_index=0) | source=llm
  HP 51->70 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: With the Act 2 boss next, going in with full HP (70/70) provides maximum safety against heavy hits. While upgrades like Blade of Ink or Blade Dance are tempting, an extra 19 HP acts as a full buffer for a bad turn.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Boss.

F32 [rest_site] proceed | source=auto
  HP 70->70 | Gold 9->9 | Deck 27->27
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F32 [map] choose_map_node (option_index=0) | source=auto
  HP 70->70 | Gold 9->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Only path: Boss

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 70->70 | Gold 9->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Disintegration behaves like a Burn (take 6 damage at the end of the turn), which is a manageable penalty compared to Mind Rot's draw reduction, especially in a draw-dependent Shiv deck. We have the HP to tank the 6 damage if we happen to draw it and end our turn.
  strategic_note: Committed to Shiv/Fan synergy with Well-Laid Plans utility. Keep retaining key defensive/burst cards like Piercing Wail for exact enemy burst turns. Look for Accuracy or strong scaling damage pieces next; prioritize upgrading Shiv generators and removing basics.

F33 [card_select] select_deck_card (option_index=0) | source=llm
  HP 66->66 | Gold 9->0 | Deck 27->27
  deck_change: no deck change
  reasoning: Sloth severely limits the number of cards we can play, which is devastating for a Shiv deck that relies on playing many cards per turn to trigger Ornamental Fan and Letter Opener. Disintegration just deals 7 damage, which is a manageable penalty compared to losing our entire engine.
  strategic_note: Committed to Shiv/Fan synergy with Well-Laid Plans utility. Retain key defensive and burst cards to survive exact enemy burst turns. Needs Accuracy or strong scaling damage pieces; prioritize upgrading Shiv generators and removing basics.

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 9->84 | Deck 27->27
  deck_change: no deck change
  reasoning: Claim gold: 75 Gold

F33 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 84->84 | Deck 27->27
  deck_change: no deck change
  reasoning: Open card reward

F33 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 60->60 | Gold 84->84 | Deck 27->28
  deck_change: picked Adrenaline
  reasoning: Adrenaline is a supreme zero-cost energy and draw generator. It fits any deck perfectly, helping cycle through our 27-card deck faster, giving energy to play Skewer or our 2-cost Dash, and fueling our Letter Opener/Ornamental Fan synergies by giving us more cards and energy.
  strategic_note: Foundation plan: cycle quickly with draw and 0-cost utility to generate shivs and trigger Fan/Letter Opener. Adrenaline helps immensely. Still looking for definitive scaling (like Accuracy or Finisher) for shivs.

F33 [map] choose_map_node (option_index=0) | source=auto
  HP 60->68 | Gold 84->84 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Ancient

F34 [event] choose_event_option (option_index=2, note_scope=run, note_triggers=all) | source=llm
  HP 68->68 | Gold 84->84 | Deck 28->28
  deck_change: no deck change
  reasoning: With a deck heavily focused on Shivs (Blade Dance, Blade of Ink, Cloak and Dagger, Leading Strike), playing 5 cards in a turn is trivial. Brilliant Scarf will consistently provide extra energy, effectively functioning as an energy relic that lets us play high-impact cards like Dash+ or card draw for free.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. With Brilliant Scarf, plan turns so the 5th card played is the most expensive one (e.g., Dash+). Needs consistent block engine and energy generation for the Boss.

F34 [event] choose_event_option (option_index=0) | source=auto
  HP 68->68 | Gold 84->84 | Deck 28->28
  deck_change: no deck change
  reasoning: Only option: Proceed

F34 [map] choose_map_node (option_index=1) | source=llm
  HP 68->68 | Gold 84->0 | Deck 28->28
  deck_change: no deck change
  reasoning: High HP (68/70) allows for monster fights to accumulate gold and card rewards. Following the recommended path to build resources for the late-act shop while staying safe.
  strategic_note: Foundation deck focusing on draw and Tracking scaling; prioritize gold generation through monster fights to afford shop removals/relics, then leverage HP and rest sites to survive into the late game.

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 84->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Claim gold: 14 Gold

F35 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Open card reward

F35 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 68->68 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: The deck is at 28 cards and functions reasonably well with its current block and shiv/sly engine. None of these cards dramatically improve our output. Ricochet lacks enough discard enablers, Precise Cut clashes with our draw/retain, and we already have sufficient block tools, so we skip to keep the deck lean.
  strategic_note: Foundation plan: Use frontload, Shivs, and Sly mechanics to deal damage while leveraging multi-play relics like Ornamental Fan and Letter Opener for defense and AoE.

F35 [map] choose_map_node (option_index=0) | source=auto
  HP 68->68 | Gold 98->98 | Deck 28->28
  deck_change: no deck change
  reasoning: Only path: Unknown

F36 [event] choose_event_option (option_index=1, note_scope=run, note_triggers=all) | source=llm
  HP 68->68 | Gold 98->98 | Deck 28->29
  deck_change: added Clumsy
  reasoning: Adding an Ethereal curse (Clumsy) is a very minor penalty compared to the immense value of a random relic. Clumsy exhausts itself if drawn, and we have incredible card draw and discard options to mitigate the dead draw anyway.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail), then burst enemies with multi-hits like Exterminate and Skewer. With Brilliant Scarf, plan turns so the 5th card played is the most expensive one (e.g., Dash+). Needs consistent block engine and energy generation for the Boss.

F36 [event] choose_event_option (option_index=0) | source=auto
  HP 68->68 | Gold 98->98 | Deck 29->29
  deck_change: no deck change
  reasoning: Only option: Proceed

F36 [map] choose_map_node (option_index=0) | source=llm
  HP 68->68 | Gold 98->0 | Deck 29->29
  deck_change: no deck change
  reasoning: With 68 HP and only 98 gold, I need to prioritize monster fights to accumulate gold for the floor 45 shop and refine the deck with card rewards. Following the planned route through three monsters is the most efficient way to scale for the Act 3 boss.
  strategic_note: Committed Tracking deck: find Tracking and Weakness pieces early, then use multi-hit cards like Exterminate and Skewer to close fights. Needs more consistent block and energy generation for the final boss; avoid elites and farm gold in hallway fights to maximize shop value.

F37 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 98->109 | Deck 29->29
  deck_change: no deck change
  reasoning: Claim gold: 11 Gold

F37 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 68->68 | Gold 109->109 | Deck 29->29
  deck_change: no deck change
  reasoning: Open card reward

F37 [card_reward] resolve_rewards (option_index=3) | source=llm
  HP 68->68 | Gold 109->109 | Deck 29->30
  deck_change: picked Footwork
  reasoning: Footwork provides essential Dexterity scaling, giving us much-needed survivability for Act 3 bosses by boosting our Defends, Backflip, Survivor, and Cloak and Dagger.
  strategic_note: Committed to attack/skill spam with Fan and Scarf, but rely on Footwork for block scaling. Play Footwork early in long fights, then spam Shivs to trigger Fan and Letter Opener.

F37 [map] choose_map_node (option_index=1) | source=llm
  HP 68->68 | Gold 109->0 | Deck 30->30
  deck_change: no deck change
  reasoning: Following the planned route to a Monster node. With 109 gold, I need to accumulate more gold through hallway fights to make the upcoming Shop (floor 46) impactful. The deck is currently at high HP (97%), making it safe to take combats to fish for better block cards and gold.
  strategic_note: Committed Tracking deck: cycle cards to find Tracking and multi-hit finishers like Exterminate and Skewer while maintaining Weakness. Prioritizing gold gain from hallway fights for a late-act shop to finalize the block engine or find energy relics/cards.

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 109->121 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 121->121 | Deck 30->30
  deck_change: no deck change
  reasoning: Claim potion: Strength Potion

F38 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 64->64 | Gold 121->121 | Deck 30->30
  deck_change: no deck change
  reasoning: Open card reward

F38 [card_reward] resolve_rewards (option_index=1) | source=llm
  HP 64->64 | Gold 121->121 | Deck 30->31
  deck_change: picked Blade Dance+
  reasoning: Blade Dance+ generates 4 Shivs, which instantly triggers our Ornamental Fan for block and fuels Brilliant Scarf. With Tracking+ and our many sources of Weak, Shivs deal double damage, making Blade Dance+ an incredible damage and defense tool.
  strategic_note: Committed to Shivs/Attacks with Fan and Tracking+ engine. Spam Shivs on weak enemies for double damage and trigger Fan for block. Look for draw and more ways to leverage 0-cost attacks.

F38 [map] choose_map_node (option_index=0) | source=llm
  HP 64->64 | Gold 121->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Continuing the planned route through standard monsters. The deck is healthy (91% HP) and needs to accumulate gold and card rewards to find more energy or block before the boss. Route index 0 leads towards the planned path of shops and rest sites.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators like Blade of Ink, then burst with multi-hits. Needs a more robust block engine and energy generation for the final boss; prioritize card rewards that offer defense or energy.

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 121->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 9 Gold

F39 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F39 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Our deck is firmly committed to a Shiv strategy with Letter Opener and Ornamental Fan. We have zero Poison synergy for Haze+ or Outbreak, Untouchable+ is too low impact (8 block for a 2-cost or discard trigger), and Follow Through is unnecessary attack bloat. Skipping keeps our deck focused on finding and cycling our core Shiv generators and Tracking+.
  strategic_note: Committed shiv plan: use Blade Dance and Cloak and Dagger to generate shivs, triggering Fan and Letter Opener. Use Tracking+ on key targets for double attack damage. Retain burst damage or combo pieces with Well-Laid Plans. Skip off-plan cards to maintain consistency.

F39 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: RestSite

F40 [rest_site] choose_rest_option (option_index=1, smith_card_index=17, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: upgraded Adrenaline->Adrenaline+
  reasoning: HP is at 60/70 (86%), so we can safely Smith. Adrenaline provides 2 Energy instead of 1 when upgraded, offering a massive tempo boost to play drawn cards, set up powers like Tracking or Footwork, and fuel X-cost cards like Skewer.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Neutralize, Piercing Wail, Blade of Ink), then burst enemies with multi-hits like Exterminate and Skewer. Needs consistent block engine and energy generation for the Boss.

F40 [rest_site] proceed | source=auto
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F40 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 130->130 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Treasure

F41 [treasure] open_chest | source=random
  HP 60->60 | Gold 130->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Open chest

F41 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim: Joss Paper

F41 [treasure] proceed | source=random
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Proceed from treasure

F41 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the established route and strategic guidance for Act 3, which strongly advises avoiding Act 3 Elites. Despite having Booming Conch for Elite fights, the risk of a catastrophic health loss or run-ending encounter in Act 3 outweighs the reward, especially since we have 162 gold and need to preserve HP for the upcoming Shop and Boss.
  strategic_note: Committed Tracking deck: cycle cards to find Tracking and Weak applicators while using Brilliant Scarf to discount high-impact finishers like Dash+ or Skewer. Prioritize consistent block to survive until energy generation is found for the Boss; avoid Act 3 Elites to preserve HP for the final Shop and Boss marathon.

F42 [rest_site] choose_rest_option (option_index=1, smith_card_index=17) | source=llm
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: upgraded Footwork->Footwork+
  reasoning: Missing only 10 HP, so Smithing is far better than Resting. Footwork+ gives 3 Dexterity instead of 2, significantly improving our block output for the upcoming Elite and Boss fights, which is crucial for survival.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators (Blade of Ink, Neutralize), then burst enemies with multi-hits. Plan turns to make the 5th card played the most expensive one via Brilliant Scarf. Needs consistent energy and block engine for the Boss.

F42 [rest_site] proceed | source=auto
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F42 [map] choose_map_node (option_index=0) | source=auto
  HP 60->60 | Gold 162->162 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Unknown

F43 [treasure] open_chest | source=random
  HP 60->60 | Gold 162->201 | Deck 31->31
  deck_change: no deck change
  reasoning: Open chest

F43 [treasure] choose_treasure_relic (option_index=0) | source=random
  HP 60->60 | Gold 201->201 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim: Captain's Wheel

F43 [treasure] proceed | source=random
  HP 60->60 | Gold 201->201 | Deck 31->31
  deck_change: no deck change
  reasoning: Proceed from treasure

F43 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 201->201 | Deck 31->31
  deck_change: no deck change
  reasoning: With 60/70 HP, I can safely use this Rest Site to Smith. Upgrading a core piece of the Tracking/Brilliant Scarf engine is more valuable than the gold from a hallway fight, especially since I already have 201 gold for the upcoming shop.
  strategic_note: Committed Tracking deck: find Tracking and Weak applicators to survive, then burst with multi-hits like Skewer. Optimize Brilliant Scarf by playing the high-cost finisher as the 5th card. Prioritize upgrading Tracking and energy-efficient block cards to ensure the engine scales for the Act 3 boss.

F44 [rest_site] choose_rest_option (option_index=1, smith_card_index=13, note_scope=run, note_triggers=all) | source=llm
  HP 60->60 | Gold 201->201 | Deck 31->31
  deck_change: upgraded Blade of Ink->Blade of Ink+
  reasoning: HP is high (60/70) and there is another rest site before the boss, so Smithing is the clear choice. Upgrading Blade of Ink increases its yield from 2 to 3 Inky Shivs. Since Inky Shivs apply Weak and deal damage, this provides an extra stack of Weak, triggers Tracking, and increases total damage output significantly for 1 energy.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators, generating Shivs (especially Inky Shivs) to trigger Tracking and burst enemies with multi-hits. Needs consistent block engine and energy generation for the Boss.

F44 [rest_site] proceed | source=auto
  HP 60->60 | Gold 201->201 | Deck 31->31
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F44 [map] choose_map_node (option_index=0) | source=llm
  HP 60->60 | Gold 201->0 | Deck 31->31
  deck_change: no deck change
  reasoning: Following the Act 3 strategy to avoid elites, which are highly lethal regardless of current HP. Taking the monster node provides gold for the upcoming shop while preserving health for the Act 3 boss.
  strategic_note: Committed Tracking deck: cycle for Tracking and Weak applicators while timing the 5th card played (Brilliant Scarf) for high-impact cards like Dash+. The deck needs more consistent block scaling and energy generation for the Boss; avoid Act 3 elites to preserve HP.

F45 [combat_rewards] claim_reward (option_index=0) | source=random
  HP 52->52 | Gold 201->213 | Deck 31->31
  deck_change: no deck change
  reasoning: Claim gold: 12 Gold

F45 [combat_rewards] claim_reward (option_index=1) | source=random
  HP 52->52 | Gold 213->213 | Deck 31->31
  deck_change: no deck change
  reasoning: Open card reward

F45 [card_reward] resolve_rewards (option_index=-1) | source=llm
  HP 52->52 | Gold 213->213 | Deck 31->31
  deck_change: no deck change
  reasoning: The deck currently has 31 cards and a highly functional Shiv/Fan/Tracking engine. We already have 5 reliable Shiv generators and adequate frontload (Skewer+, Exterminate, Dash+). Adding unupgraded Pinpoint or another Leading Strike would bloat the deck right before the boss without significantly improving our win condition.
  strategic_note: Committed Shiv/Tracking plan: use weak sources (Expose, Neutralize, Blade of Ink) to double attack damage via Tracking+, then burst with Shivs while triggering Ornamental Fan for defense. Skip bloat to keep drawing the core setup.

F45 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 213->213 | Deck 31->31
  deck_change: no deck change
  reasoning: Only path: Shop

F46 [shop] buy_card (option_index=4) | source=plan
  HP 52->52 | Gold 213->141 | Deck 31->32
  deck_change: bought Footwork
  reasoning: Shop plan [1/2]: Provides essential defensive scaling. We have one Footwork+ already, but another copy ensures we can block late-game boss damage consistently.

F46 [shop] buy_card (option_index=3) | source=plan
  HP 52->52 | Gold 141->62 | Deck 32->33
  deck_change: bought Expertise
  reasoning: Shop plan [2/2]: Top-tier hand refill. With our many 0-cost cards, Shiv generators, and energy from Adrenaline+, we can easily empty our hand to draw 3-5 cards.

F46 [shop] close_shop_inventory | source=plan
  HP 52->52 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Shop plan complete — leaving

F46 [shop] proceed | source=auto
  HP 52->52 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Leave shop after closing inventory

F46 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: RestSite

F47 [rest_site] choose_rest_option (option_index=1, smith_card_index=16, note_scope=run, note_triggers=all) | source=llm
  HP 52->52 | Gold 62->62 | Deck 33->33
  deck_change: upgraded Footwork->Footwork+
  reasoning: Upgrading our second Footwork gives us an extra point of Dexterity for the upcoming boss fight. Over a long encounter, +1 Dex will generate significantly more than the 18 HP we would recover by resting.
  strategic_note: Committed Tracking deck: use card draw to find Tracking and Weak applicators, generating Shivs to trigger Tracking and burst enemies with multi-hits. Set up double Footwork for scaling block against the boss.

F47 [rest_site] proceed | source=auto
  HP 52->52 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Auto-proceed from rest (option already used)

F47 [map] choose_map_node (option_index=0) | source=auto
  HP 52->52 | Gold 62->0 | Deck 33->33
  deck_change: no deck change
  reasoning: Only path: Boss

F48 [combat_rewards] collect_rewards_and_proceed | source=random
  HP 43->43 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Collect all rewards and proceed

F48 [event] choose_event_option (option_index=0) | source=auto
  HP 43->0 | Gold 62->62 | Deck 33->33
  deck_change: no deck change
  reasoning: Only option: Proceed

## Selected Replay Package (6 replays)
[Selected: elite] multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (F12, elite)
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 12, elite)
Relics: Ring of the Snake, Booming Conch, Whetstone
Deck (17): Defend x5, Strike x3, Strike+ x2, Ascender's Bane, Dash+, Expose, Flick-Flack, Neutralize, Skewer+, Survivor
Enemies: Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=31/31, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=27/27

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Skewer+ -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -11, block +6
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.

### Round 2
Agent plan (hypothesis): Sly cards like Flick-Flack are incredible for tempo when combo'd with Survivor.
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(7)
  Expose -> Phantasmal Gardener[3]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Phantasmal Gardener: +Vulnerable(2)
  Survivor
    energy -1 | block +8
  Flick-Flack
  Strike+ -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp +8, block +6, -Strength, -Vulnerable
  Defend
    energy -1 | block +5
  turn_end

### Round 3
Agent plan (hypothesis): Saved the potion, killed the Strength-scaled enemy, and took zero damage.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Buff
  Neutralize -> Phantasmal Gardener[0]
  Dash+ -> Phantasmal Gardener[0]
    energy -2 | block +13
  Strike -> Phantasmal Gardener[0]
    energy -1
  turn_end

### Round 4
Agent plan (hypothesis): Saved Flex Potion for the upcoming draw of Dash+ and Neutralize. Focus Enemy 2 next.
Agent plan (hypothesis): Saved Flex Potion. Focus on Enemy 1 next turn.
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7)
  Strike -> Phantasmal Gardener[0]
    energy -1
  Defend
    energy -1 | block +5
  Strike+ -> Phantasmal Gardener[1]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -9, block +6
  turn_end

### Round 5
Agent plan (hypothesis): Saved Flex potion again. Down to one enemy.
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  Survivor
    energy -1 | block +8
  Flick-Flack
  Skewer+ -> Phantasmal Gardener[1]
    energy -2 | enemy_deltas: Phantasmal Gardener: hp +4, block +6
  turn_end

### Round 6
Agent plan (hypothesis): Saved Flex potion for the kill next turn.
Intent: Phantasmal Gardener: Attack(9)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +10
  Strike -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -6, block +6
  turn_end

### Round 7
Intent: Phantasmal Gardener: Attack(3x3=9)
  Skewer+ -> Phantasmal Gardener[0]
    energy -3 | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 7 rounds)

Cards played (with descriptions):
  Defend "Gain 5 Block." -> 6 plays, 35 block
  Skewer+ "Deal 11 damage X times." -> 3 plays, 11 dmg
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Strike+ "Deal 9 damage." -> 2 plays, 9 dmg
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 1 plays
  Dash+ "Gain 13 Block. Deal 13 damage." -> 1 plays, 13 block
  Strike "Deal 6 damage." -> 3 plays, 6 dmg

Enemy power timeline:
  Skittish: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:6 -> R7:6
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:- -> R7:-
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:- -> R7:-
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:- -> R7:-
  Skittish[3]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:2 -> R7:2
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:- -> R7:-
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:- -> R7:-
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:- -> R7:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (Floor 15, elite)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow
Deck (20): Defend x5, Strike x4, Leading Strike x2, Accelerant, Ascender's Bane, Envenom, Expose, Finisher, Leg Sweep, Neutralize+, Strangle+, Survivor
Enemies: Phantasmal Gardener HP=26/26, Phantasmal Gardener HP=28/28, Phantasmal Gardener HP=30/30, Phantasmal Gardener HP=27/27

### Round 1
Intent: Phantasmal Gardener: Attack(1x3=3), Phantasmal Gardener: Attack(5), Phantasmal Gardener: Attack(7), Phantasmal Gardener: Buff
  Leg Sweep -> Phantasmal Gardener[2]
    energy -2 | block +11
  Defend
    energy -1 | block +5
  turn_end

### Round 2
Intent: Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(0x3=0), Phantasmal Gardener: Attack(7)
  Expose -> Phantasmal Gardener[3]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Phantasmal Gardener: +Vulnerable(2)
  Strangle+ -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -15, block +6, +Strangle(3)
  Leading Strike -> Phantasmal Gardener[3]
    energy -1 | enemy_deltas: Phantasmal Gardener: hp -3, block -4
  Shiv -> Phantasmal Gardener[3]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Phantasmal Gardener: hp -7, block -2
  Neutralize+ -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp +28, +Weak(1), -Strength, -Vulnerable, -Strangle
  Defend
    energy -1 | block +5
  Shiv -> Phantasmal Gardener[1]
  turn_end

### Round 3
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(0x3=0), Phantasmal Gardener: Buff
  Colorless Potion
  Scrawl
  Scrawl
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Survivor
    energy -1 | block +8
  Defend
  Strike -> Phantasmal Gardener[0]
    energy -1
  Strike -> Phantasmal Gardener[0]
    energy -1
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.

### Round 4
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Buff, Phantasmal Gardener: Attack(7)
  Strangle+ -> Phantasmal Gardener[0]
    energy -1
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[2]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6
  Strike -> Phantasmal Gardener[1]
    energy -1 | enemy_deltas: Phantasmal Gardener: block -6
  turn_end

### Round 5
Intent: Phantasmal Gardener: Attack(7), Phantasmal Gardener: Attack(9)
  Neutralize+ -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6, +Weak(2)
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[0]
  Survivor
    energy -1 | block +8
  Strike
  Defend
    energy -1 | block +5
  turn_end

### Round 6
Intent: Phantasmal Gardener: Attack(9), Phantasmal Gardener: Attack(2x3=6)
  Strangle+ -> Phantasmal Gardener[0]
    energy -1
  Leading Strike -> Phantasmal Gardener[0]
    energy -1
  Shiv -> Phantasmal Gardener[0]
  Shiv -> Phantasmal Gardener[1]
    enemy_deltas: Phantasmal Gardener: hp -4, block +6
  Finisher -> Phantasmal Gardener[0]
    energy -1 | enemy_deltas: Phantasmal Gardener: DIED
## Combat Analytics: multi:Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener+Phantasmal Gardener (WIN - 6 rounds)

Cards played (with descriptions):
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Defend "Gain 5 Block." -> 3 plays, 15 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 3 plays, 15 dmg
  Leading Strike "Retain. Deal 3 damage. Add 2 Shivs into your Hand." -> 4 plays, 3 dmg, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 8 plays, 15 dmg, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 4 dmg
  Scrawl "Draw cards until your Hand is full. Exhaust." -> 1 plays, EXHAUST
  Survivor "Gain 8 Block. Discard 1 card." -> 2 plays, 16 block
  Strike "Deal 6 damage." -> 3 plays
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 4 times)" -> 1 plays

Token attribution (Shivs):
  Leading Strike: 8 Shivs -> ~15 dmg

Enemy power timeline:
  Skittish[0]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6
  Skittish[1]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:6 -> R6:6
  Skittish[2]: R1:6 -> R2:6 -> R3:6 -> R4:6 -> R5:- -> R6:-
  Skittish[3]: R1:6 -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:-
  Strength: R1:- -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:-
  Strength[0]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:2 -> R6:2
  Strength[1]: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2
  Strength[2]: R1:- -> R2:- -> R3:- -> R4:2 -> R5:- -> R6:-
  Weak: R1:- -> R2:1 -> R3:1 -> R4:- -> R5:- -> R6:1

[Selected: boss] Soul Fysh (F17, boss)
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan
Deck (20): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Dash+, Defend+, Expose, Flick-Flack, Injury, Leading Strike, Neutralize, Skewer+, Survivor+
Enemies: Soul Fysh HP=211/211

### Round 1
Agent plan (hypothesis): Continue using attacks drawn by Backflip.
Agent plan (hypothesis): Soul Fysh will be vulnerable next turn as well.
Intent: Soul Fysh: StatusCard(2)
  Flex Potion -> Soul Fysh[0]
    +Strength(5) | +Flex Potion(5)
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -10, +Weak(1)
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -8
  Shiv -> Soul Fysh[0]
    block +4 | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -9
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -9
  Backflip
    energy -1 | block +5
  Expose -> Soul Fysh[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: +Vulnerable(2)
  Strike+ -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -21
  turn_end

### Round 2
Agent plan (hypothesis): Ascender's Bane will exhaust.
Intent: Soul Fysh: Attack(16)
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -6
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -6
  Shiv -> Soul Fysh[0]
    block +4 | enemy_deltas: Soul Fysh: hp -6
  Skewer+ -> Soul Fysh[0]
    energy -2 | enemy_deltas: Soul Fysh: hp -32
  turn_end
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust.

### Round 3
Intent: Soul Fysh: Attack(7), StatusCard(1)
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Survivor+
    energy -1 | block +11
  Defend
  turn_end

### Round 4
Intent: Soul Fysh: Buff
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -5, +Weak(1)
  Leading Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -3
  Shiv -> Soul Fysh[0]
    block +4 | enemy_deltas: Soul Fysh: hp -4
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4
  Dash+ -> Soul Fysh[0]
    energy -2 | block +13 | enemy_deltas: Soul Fysh: hp -13
  turn_end

### Round 5
Agent plan (hypothesis): The boss will shuffle status cards next turn.
Intent: Soul Fysh: Attack(11), Debuff
  Backflip
    energy -1 | block +5
  Defend
    energy -1 | block +5
  Beckon
    energy -1
  turn_end

### Round 6
Agent plan (hypothesis): Boss uses a heavy attack next turn while we are Vulnerable. Need mitigation.
Intent: Soul Fysh: StatusCard(2)
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Strike+ -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Survivor+
    energy -1 | block +11
  Flick-Flack
  turn_end
    block +4 | enemy_deltas: Soul Fysh: hp -6

### Round 7
Agent plan (hypothesis): Survive the heavy attack, then focus on bursting the boss down next turn as it will have low HP.
Intent: Soul Fysh: Attack(24)
  Beckon
    energy -1
  Beckon
    energy -1
  Beckon
    energy -1
  turn_end

### Round 8
Agent plan (hypothesis): Boss buffs next turn, we should easily find lethal with 22 HP remaining.
Intent: Soul Fysh: Attack(10), StatusCard(1)
  Neutralize -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -5, +Weak(1)
  Defend
    energy -1 | block +10
  Strike+ -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Strike -> Soul Fysh[0]
    energy -1 | block +4 | enemy_deltas: Soul Fysh: hp -6
  turn_end

### Round 9
Intent: Soul Fysh: Buff
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Strike+ -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -9
  Beckon
    energy -1
  turn_end

### Round 10
Agent plan (hypothesis): Boss is Intangible, survive and kill next turn.
Intent: Soul Fysh: Attack(11), Debuff
  Survivor+
    energy -1 | block +11
  Beckon
  Dash+ -> Soul Fysh[0]
    energy -2 | block +13 | enemy_deltas: Soul Fysh: hp -1
  turn_end

### Round 11
Agent plan (hypothesis): Fight is over.
Intent: Soul Fysh: StatusCard(2)
  Skewer+ -> Soul Fysh[0]
    energy -3 | -Vulnerable | enemy_deltas: Soul Fysh: DIED
## Combat Analytics: Soul Fysh (WIN - 11 rounds)

Cards played (with descriptions):
  Neutralize "Deal 10 damage. Apply 1 Weak." -> 3 plays, 20 dmg
  Leading Strike "Deal 8 damage. Add 2 Shivs into your Hand." -> 2 plays, 11 dmg, generates 2 Shivs
  Shiv "Deal 9 damage. Exhaust." -> 7 plays, 44 dmg, 12 block, EXHAUST
  Backflip "Gain 5 Block. Draw 2 cards." -> 2 plays, 10 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Strike+ "Deal 14 damage." -> 4 plays, 48 dmg
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Skewer+ "Deal 11 damage X times." -> 2 plays, 32 dmg
  Strike "Deal 6 damage." -> 5 plays, 30 dmg, 4 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 3 plays, 33 block
  Dash+ "Gain 13 Block. Deal 13 damage." -> 2 plays, 14 dmg, 26 block
  Defend "Gain 5 Block." -> 2 plays, 15 block
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 5 plays

Token attribution (Shivs):
  Leading Strike: 4 Shivs -> ~25 dmg
  Blade Dance: 3 Shivs -> ~19 dmg

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:1 -> R11:-
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Soul Fysh (Floor 17, boss)
Relics: Ring of the Snake, Neow's Bones, New Leaf, Small Capsule, Centennial Puzzle, The Chosen Cheese, Pendulum
Deck (20): Defend x5, Strike x4, Ascender's Bane, Backflip, Backstab, Bouncing Flask+, Cloak and Dagger, Dagger Spray, Flick-Flack, Neutralize+, Predator, Survivor, Tools of the Trade
Enemies: Soul Fysh HP=211/211

### Round 1
Intent: Soul Fysh: StatusCard(2)
  Vulnerable Potion -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: +Vulnerable(3)
  Backstab -> Soul Fysh[0]
    exhausted: Backstab [0]: Innate. Deal 11 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -16
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  Survivor
    energy -1 | block +8
  Flick-Flack
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -18
  turn_end
  Ascender's Bane

### Round 2
Intent: Soul Fysh: Attack(16)
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Soul Fysh[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Soul Fysh: hp -6
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +10
  turn_end
  Beckon

### Round 3
Intent: Soul Fysh: Attack(7), StatusCard(1)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -6, +Weak(2)
  Backflip
    energy -1 | block +5
  Bouncing Flask+
    energy -2 | enemy_deltas: Soul Fysh: +Poison(12)
  turn_end
  Flick-Flack

### Round 4
Intent: Soul Fysh: Buff
  Survivor
    energy -1 | block +8
  Beckon
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Defend
    energy -1 | block +5
  turn_end
    exhausted: Shiv [0]: Deal 4 damage. Exhaust.
  Strike

### Round 5
Intent: Soul Fysh: Attack(11), Debuff
  Defend
    energy -1 | block +5
  Cloak and Dagger
    energy -1 | block +6
  Shiv -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -1
  Defend
    energy -1 | block +10
  turn_end
  Flick-Flack

### Round 6
Intent: Soul Fysh: StatusCard(2)
  Neutralize+ -> Soul Fysh[0]
    enemy_deltas: Soul Fysh: hp -4, +Weak(2)
  Predator -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -15
  Beckon
    energy -1
  turn_end
  Beckon

### Round 7
Intent: Soul Fysh: Attack(18)
  Speed Potion
    +Dexterity(5) | +Speed Potion(5)
  Bouncing Flask+
    energy -2 | enemy_deltas: Soul Fysh: Poison(8→20)
  Survivor
    energy -1 | block +13
  Beckon
  turn_end
  Flick-Flack

### Round 8
Intent: Soul Fysh: Attack(10), StatusCard(1)
  Predator -> Soul Fysh[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Soul Fysh: hp -15
  Survivor
    energy -1 | block +8
  Beckon
  turn_end
  Beckon

### Round 9
Intent: Soul Fysh: Buff
  Strike -> Soul Fysh[0]
    energy -1 | enemy_deltas: Soul Fysh: hp -6
  Bouncing Flask+
    energy -2 | enemy_deltas: Soul Fysh: Poison(18→30)
  turn_end
## Combat Analytics: Soul Fysh (WIN - 9 rounds)

Cards played (with descriptions):
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 16 dmg, EXHAUST
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Survivor "Gain 8 Block. Discard 1 card." -> 4 plays, 37 block
  Strike "Deal 6 damage." -> 3 plays, 30 dmg
  Cloak and Dagger "Gain 6 Block. Add 1 Shiv into your Hand." -> 2 plays, 12 block, generates 1 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 2 plays, 7 dmg, EXHAUST
  Defend "Gain 5 Block." -> 5 plays, 35 block
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 10 dmg
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 5 block
  Bouncing Flask+ "Apply 3 Poison to a random enemy 4 times." -> 3 plays, +36 poison
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 2 plays, 30 dmg
  Beckon "At the end of your turn, if this is in your Hand, lose 6 HP." -> 1 plays

Token attribution (Shivs):
  Cloak and Dagger: 2 Shivs -> ~7 dmg

Poison stacks applied per card:
  Bouncing Flask+: 36 stacks

Enemy power timeline:
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:-
  Poison: R1:- -> R2:- -> R3:- -> R4:11 -> R5:10 -> R6:9 -> R7:8 -> R8:19 -> R9:18
  Vulnerable: R1:- -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:-
  Weak: R1:- -> R2:- -> R3:- -> R4:1 -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:-

[Selected: run_combat] Hunter Killer (F22, monster)
Historical: loss=28 vs historical avg=8.8+/-4.9 (z=3.9, WORSE_THAN_USUAL, n=5)
## Combat Replay: vs Hunter Killer (Floor 22, monster)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood
Deck (24): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Dash+, Defend+, Expose, Exterminate, Flick-Flack, Injury, Leading Strike, Neutralize, Prepared+, Skewer+, Survivor+, Tracking, Well-Laid Plans+
Enemies: Hunter Killer HP=121/121

### Round 1
Agent plan (hypothesis): Retain Neutralize and Expose. Ascender's Bane will exhaust.
Intent: Hunter Killer: Debuff
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Strike -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -6
  Strike+ -> Hunter Killer[0]
    energy -1 | enemy_deltas: Hunter Killer: hp -9
  turn_end
    exhausted: Ascender's Bane [0]: Unplayable. Ethereal. Eternal.
  Neutralize
  Expose

### Round 2
Agent plan (hypothesis): Continue focusing on heavy, single-hit attacks and avoiding multi-hit combos while Tender is active.
Intent: Hunter Killer: Attack(7x3=21)
  Expose -> Hunter Killer[0]
    +Strength(-1) | +Dexterity(-1) | exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Hunter Killer: +Vulnerable(2)
  Neutralize -> Hunter Killer[0]
    Strength(-1→-2) | Dexterity(-1→-2) | enemy_deltas: Hunter Killer: hp -6, +Weak(1)
  Tracking
    energy -2 | Strength(-2→-3) | Dexterity(-2→-3) | +Tracking(2)
  Prepared+
  Flick-Flack
  Injury
  Strike+ -> Hunter Killer[0]
    energy -1 | block +4 | Strength(-5→-6) | Dexterity(-5→-6) | enemy_deltas: Hunter Killer: hp -12
  turn_end
  Blade Dance
  Leading Strike

### Round 3
Agent plan (hypothesis): We will reshuffle next turn. Look for Neutralize and Tracking synergies.
Intent: Hunter Killer: Attack(17)
  Dash+ -> Hunter Killer[0]
    energy -2 | block +13 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -19
  Defend
    energy -1 | block +4 | Strength(-1→-2) | Dexterity(-1→-2)
  turn_end
  Blade Dance
  Skewer+

### Round 4
Agent plan (hypothesis): We will retain Skewer+ automatically and hopefully draw Neutralize next turn to land a massive Weakened Skewer+ hit.
Agent plan (hypothesis): Retain Skewer+ with Well-Laid Plans.
Intent: Hunter Killer: Attack(7x3=21)
  Defend
    energy -1 | block +9 | +Strength(-2) | +Dexterity(-2)
  Backflip
    energy -1 | block +3 | Strength(-2→-3) | Dexterity(-2→-3)
  Neutralize -> Hunter Killer[0]
    Strength(-3→-4) | Dexterity(-3→-4) | enemy_deltas: Hunter Killer: hp -2, +Weak(1)
  Strike -> Hunter Killer[0]
    energy -1 | Strength(-4→-5) | Dexterity(-4→-5) | enemy_deltas: Hunter Killer: hp -4
  turn_end
  Blade Dance
  Skewer+

### Round 5
Agent plan (hypothesis): Continue retaining Skewer+ until we draw Neutralize to land a massive Weakened hit.
Intent: Hunter Killer: Attack(7x3=21)
  Defend
    energy -1 | block +5 | +Strength(-1) | +Dexterity(-1)
  Defend+
    energy -1 | block +7 | Strength(-1→-2) | Dexterity(-1→-2)
  Strike -> Hunter Killer[0]
    energy -1 | Strength(-2→-3) | Dexterity(-2→-3) | enemy_deltas: Hunter Killer: hp -4
  turn_end
  Blade Dance
  Skewer+

### Round 6
Agent plan (hypothesis): Retain Skewer+. Neutralize is in the draw pile for next turn.
Intent: Hunter Killer: Attack(17)
  Dash+ -> Hunter Killer[0]
    energy -2 | block +13 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -13
  Survivor+
    energy -1 | block +10
  Injury
  turn_end
  Blade Dance
  Skewer+

### Round 7
Intent: Hunter Killer: Attack(7x3=21)
  Defend+
    energy -1 | block +8 | +Strength(-1) | +Dexterity(-1)
  Defend
    energy -1 | block +4 | Strength(-1→-2) | Dexterity(-1→-2)
  Blade Dance
    energy -1 | Strength(-2→-3) | Dexterity(-2→-3) | exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust.
  Shiv -> Hunter Killer[0]
    Strength(-3→-4) | Dexterity(-3→-4) | exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Hunter Killer: hp -1
  Shiv -> Hunter Killer[0]
    Strength(-4→-5) | Dexterity(-4→-5)
  Shiv -> Hunter Killer[0]
    block +4 | Strength(-5→-6) | Dexterity(-5→-6)
  turn_end
  Skewer+
  Exterminate

### Round 8
Intent: Hunter Killer: Attack(17)
  Neutralize -> Hunter Killer[0]
    +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -5, +Weak(1)
  Skewer+ -> Hunter Killer[0]
    energy -3 | -Well-Laid Plans | -Tender | -Tracking | -Strength | -Dexterity | enemy_deltas: Hunter Killer: DIED
## Combat Analytics: Hunter Killer (WIN - 8 rounds)

Cards played (with descriptions):
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Strike "Deal 6 damage." -> 3 plays, 14 dmg
  Strike+ "Deal 9 damage." -> 2 plays, 21 dmg, 4 block
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Neutralize "Deal 4 damage. Apply 1 Weak." -> 3 plays, 13 dmg
  Tracking "Weak enemies take double damage from Attacks." -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 1 plays
  Dash+ "Gain 13 Block. Deal 13 damage." -> 2 plays, 32 dmg, 26 block
  Defend "Gain 4 Block." -> 4 plays, 22 block
  Backflip "Gain 3 Block. Draw 2 cards." -> 1 plays, 3 block
  Defend+ "Gain 7 Block." -> 2 plays, 15 block
  Survivor+ "Gain 10 Block. Discard 1 card." -> 1 plays, 10 block
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 1 damage. Exhaust." -> 3 plays, 1 dmg, 4 block, EXHAUST
  Skewer+ "Deal 10 damage X times." -> 1 plays

Token attribution (Shivs):
  Blade Dance: 3 Shivs -> ~1 dmg

Enemy power timeline:
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:-
Comparator (recent better same-enemy comparator):
## Combat Replay: vs Hunter Killer (Floor 31, monster)
Relics: Ring of the Snake, Neow's Bones, New Leaf, Small Capsule, Centennial Puzzle, The Chosen Cheese, Pendulum, Radiant Pearl, Snecko Skull, Orichalcum, Unceasing Top
Deck (25): Defend x5, Strike x3, Afterimage, Ascender's Bane, Backflip, Backstab, Bouncing Flask+, Calculated Gamble, Cloak and Dagger, Dagger Spray+, Expertise+, Flick-Flack, Neutralize+, Piercing Wail, Predator, Strangle+, Survivor, Tools of the Trade, Well-Laid Plans
Enemies: Hunter Killer HP=121/121

### Round 1
Intent: Hunter Killer: Debuff
  Luminesce
    energy +2 | exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust.
  Backstab -> Hunter Killer[0]
    exhausted: Luminesce [0]: Retain. Gain 2 energy . Exhaust. | enemy_deltas: Hunter Killer: hp -11
  Predator -> Hunter Killer[0]
    energy -2 | +Draw Cards Next Turn(2) | enemy_deltas: Hunter Killer: hp -15
  Dagger Spray+
    energy -1 | enemy_deltas: Hunter Killer: hp -12
  Tools of the Trade
    energy -1 | +Tools of the Trade(1)
  Expertise+
    energy -1
  Neutralize+ -> Hunter Killer[0]
    enemy_deltas: Hunter Killer: hp -4, +Weak(2)
  turn_end
    block +6
  Flick-Flack

### Round 2
Intent: Hunter Killer: Attack(5x3=15)
  Defend
    energy -1 | block +7 | Strength(-1→-3) | Dexterity(-1→-3)
  Bouncing Flask+
    energy -2 | Strength(-3→-4) | Dexterity(-3→-4) | enemy_deltas: Hunter Killer: +Poison(16)
  turn_end
  Strike

### Round 3
Intent: Hunter Killer: Attack(7x3=21)
  Strangle+ -> Hunter Killer[0]
    energy -1 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -10, +Strangle(3)
  Neutralize+ -> Hunter Killer[0]
    Strength(-1→-2) | Dexterity(-1→-2) | enemy_deltas: Hunter Killer: hp -6, +Weak(2)
  Piercing Wail
    energy -1 | Strength(-2→-3) | Dexterity(-2→-3) | exhausted: Piercing Wail [1]: ALL enemies lose 6 Strength this turn. Exhaust. | enemy_deltas: Hunter Killer: hp -3, +Strength(-6), +Piercing Wail(6)
  Afterimage
    energy -1 | Strength(-3→-4) | Dexterity(-3→-4) | +Afterimage(1) | enemy_deltas: Hunter Killer: hp -3
  turn_end
    block +6
  Strike

### Round 4
Intent: Hunter Killer: Attack(12)
  Dagger Spray+
    energy -1 | block +1 | +Strength(-1) | +Dexterity(-1) | enemy_deltas: Hunter Killer: hp -12
  Survivor
    energy -1 | block +7
  Defend
  turn_end
## Combat Analytics: Hunter Killer (WIN - 4 rounds)

Cards played (with descriptions):
  Luminesce "Retain. Gain 2 energy . Exhaust." -> 1 plays, EXHAUST
  Backstab "Innate. Deal 11 damage. Exhaust." -> 1 plays, 11 dmg, EXHAUST
  Predator "Deal 15 damage. Next turn, draw 2 cards." -> 1 plays, 15 dmg
  Dagger Spray+ "Deal 6 damage to ALL enemies twice." -> 2 plays, 24 dmg, 1 block
  Tools of the Trade "At the start of your turn, draw 1 card and discard 1 card." -> 1 plays
  Expertise+ "Draw cards until you have 7 in your Hand." -> 1 plays
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 2 plays, 10 dmg
  Defend "Gain 4 Block. Replay 1." -> 1 plays, 7 block
  Bouncing Flask+ "Apply 4 Poison to a random enemy 4 times." -> 1 plays, +16 poison
  Strangle+ "Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 3 dmg, EXHAUST
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays, 3 dmg
  Survivor "Gain 7 Block. Discard 1 card." -> 1 plays, 7 block

Poison stacks applied per card:
  Bouncing Flask+: 16 stacks

Enemy power timeline:
  Poison: R1:- -> R2:- -> R3:15 -> R4:14
  Weak: R1:- -> R2:1 -> R3:- -> R4:1

[Selected: run_combat] multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (F23, monster)
Historical: loss=16 vs historical avg=6.8+/-5.9 (z=1.6, WORSE_THAN_USUAL, n=5)
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 23, monster)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood
Deck (25): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Blade of Ink, Dash+, Defend+, Expose, Exterminate, Flick-Flack, Injury, Leading Strike, Neutralize, Prepared+, Skewer+, Survivor+, Tracking, Well-Laid Plans+
Enemies: Bowlbug (Rock) HP=45/45, Bowlbug (Silk) HP=41/41, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Expose -> Bowlbug (Rock)[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Bowlbug (Rock): +Vulnerable(2)
  Skewer+ -> Bowlbug (Rock)[0]
    energy -3 | enemy_deltas: Bowlbug (Rock): DIED
  turn_end

### Round 2
Agent plan (hypothesis): The Beetle will wake up if damaged 3 times, keep targeting the Bowlbug.
Intent: Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Blade Dance
    energy -1 | exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust.
  Shiv -> Bowlbug (Silk)[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bowlbug (Silk): hp -3
  Shiv -> Bowlbug (Silk)[0]
    enemy_deltas: Bowlbug (Silk): hp -3
  Shiv -> Bowlbug (Silk)[0]
    block +4 | enemy_deltas: Bowlbug (Silk): hp -3
  Leading Strike -> Bowlbug (Silk)[0]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -2
  Shiv -> Bowlbug (Silk)[0]
    enemy_deltas: Bowlbug (Silk): hp -3
  Shiv -> Bowlbug (Silk)[0]
    block +4 | enemy_deltas: Bowlbug (Silk): hp -3
  turn_end
  Survivor+
  Defend

### Round 3
Agent plan (hypothesis): Retain Dash+ for damage/block next turn. Kill Silk Bug quickly.
Intent: Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Backflip
    energy -1 | block +5
  Prepared+
  Flick-Flack
  Injury
  Blade of Ink
    energy -1
  Shiv -> Bowlbug (Silk)[0]
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bowlbug (Silk): hp -6, +Weak(1)
  Shiv -> Bowlbug (Silk)[0]
    block +4 | enemy_deltas: Bowlbug (Silk): hp -6, Weak(1→2)
  Strike+ -> Bowlbug (Silk)[0]
    energy -1 | enemy_deltas: Bowlbug (Silk): DIED
  turn_end
    exhausted: Shiv*5 [0]: Deal 4 damage. Exhaust.
  Dash+
  confirm

### Round 4
Intent: Slumbering Beetle: Attack(16), Buff
  Neutralize -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: block -5, +Weak(1)
  Survivor+
    energy -1 | block +11
  Flick-Flack
  Dash+ -> Slumbering Beetle[0]
    energy -2 | block +17 | enemy_deltas: Slumbering Beetle: hp -11, block -8
  turn_end
  Defend
  Backflip

### Round 5
Agent plan (hypothesis): Play block cards to hit 18. If you fall short, retain Skewer+ for next turn damage.
Agent plan (hypothesis): If Defend+ is drawn, play it and another Defend for 18 block total.
Intent: Slumbering Beetle: Attack(18), Buff
  Backflip
    energy -1 | block +5
  Prepared+
  Strike
  Strike+
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
  Skewer+
  Tracking

### Round 6
Agent plan (hypothesis): Retain Skewer+ for burst damage. Prepare to apply Weak to activate Tracking next turn.
Intent: Slumbering Beetle: Attack(20), Buff
  Dash+ -> Slumbering Beetle[0]
    energy -2 | block +13 | enemy_deltas: Slumbering Beetle: hp -13
  Defend
    energy -1 | block +10
  turn_end
  Skewer+
  Tracking

### Round 7
Agent plan (hypothesis): Retain Skewer+ for burst damage or Tracking if you have energy. Beetle is gaining Strength fast, need to kill soon.
Intent: Slumbering Beetle: Attack(22), Buff
  Backflip
    energy -1 | block +5
  Prepared+
  Flick-Flack
  Injury
  Neutralize -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -5, +Weak(1)
  Defend
    energy -1 | block +5
  Defend
    energy -1 | block +5
  turn_end
  Skewer+
  Tracking

### Round 8
Agent plan (hypothesis): Retain Skewer+ to burst the Beetle next turn before its Strength scaling overwhelms us.
Intent: Slumbering Beetle: Attack(24), Buff
  Blade of Ink
    energy -1
  Shiv -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -6, +Weak(1)
  Shiv -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -6, Weak(1→2)
  Survivor+
    energy -1 | block +11
  Exterminate
  Defend
    energy -1 | block +5
  turn_end
  Skewer+
  Tracking

### Round 9
Agent plan (hypothesis): Retain Skewer+ for the guaranteed 33 damage kill next turn.
Intent: Slumbering Beetle: Attack(19), Buff
  Neutralize -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -5, Weak(1→2)
  Backflip
    energy -1 | block +5
  Leading Strike -> Slumbering Beetle[0]
    energy -1 | enemy_deltas: Slumbering Beetle: hp -3
  Shiv -> Slumbering Beetle[0]
    block +4 | enemy_deltas: Slumbering Beetle: hp -4
  Shiv -> Slumbering Beetle[0]
    enemy_deltas: Slumbering Beetle: hp -4
  Strike -> Slumbering Beetle[0]
    energy -1 | enemy_deltas: Slumbering Beetle: hp -6
  turn_end
  Skewer+
  Flick-Flack

### Round 10
Intent: Slumbering Beetle: Attack(21), Buff
  Skewer+ -> Slumbering Beetle[0]
    energy -3 | -Well-Laid Plans | enemy_deltas: Slumbering Beetle: DIED
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 10 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Skewer+ "Deal 11 damage X times." -> 2 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Shiv "Deal 3 damage. Exhaust." -> 11 plays, 47 dmg, 16 block, EXHAUST
  Leading Strike "Deal 2 damage. Add 2 Shivs into your Hand." -> 2 plays, 5 dmg, generates 2 Shivs
  Backflip "Gain 5 Block. Draw 2 cards." -> 4 plays, 20 block
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 2 plays
  Strike+ "Deal 9 damage." -> 1 plays
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 3 plays, 10 dmg
  Survivor+ "Gain 11 Block. Discard 1 card." -> 2 plays, 22 block
  Dash+ "Gain 13 Block. Deal 13 damage." -> 2 plays, 24 dmg, 30 block
  Defend "Gain 5 Block." -> 6 plays, 35 block
  Strike "Deal 6 damage." -> 1 plays, 6 dmg

Token attribution (Shivs):
  Leading Strike: 4 Shivs -> ~17 dmg
  other: 4 Shivs -> ~17 dmg
  Blade Dance: 3 Shivs -> ~13 dmg

Enemy power timeline:
  Imbalanced: R1:1 -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:4 -> R7:6 -> R8:8 -> R9:10 -> R10:12
  Weak: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:1 -> R10:1

Unattributed damage (power/passive effects): 51
  Per round: R1:45 R3:6
Comparator (recent better same-enemy comparator):
## Combat Replay: vs multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (Floor 30, monster)
Relics: Ring of the Snake, Arcane Scroll, Regal Pillow, Unceasing Top, Pael's Flesh, War Paint, Permafrost, Snecko Skull
Deck (24): Defend x5, Strike x3, Leading Strike x2, Accelerant, Afterimage, Ascender's Bane, Backflip, Envenom+, Escape Plan, Expose, Finisher, Hidden Daggers+, Leg Sweep, Neutralize+, Strangle+, Survivor+, Well-Laid Plans+
Enemies: Bowlbug (Rock) HP=46/46, Bowlbug (Silk) HP=42/42, Slumbering Beetle HP=86/86

### Round 1
Intent: Bowlbug (Rock): Attack(15), Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Strangle+ -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -10, +Strangle(3)
  Leading Strike -> Bowlbug (Rock)[0]
    energy -1 | enemy_deltas: Bowlbug (Rock): hp -6
  Hidden Daggers+
  Strike
  Defend
  Shiv -> Bowlbug (Rock)[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Bowlbug (Rock): hp -7
  Shiv -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): hp -7
  Shiv+ -> Bowlbug (Rock)[0]
    exhausted: Shiv+ [0]: Deal 6 damage. Exhaust. | enemy_deltas: Bowlbug (Rock): hp -9
  Shiv+ -> Bowlbug (Rock)[0]
    enemy_deltas: Bowlbug (Rock): DIED
  Finisher -> Bowlbug (Silk)[0]
    energy -1 | enemy_deltas: Bowlbug (Silk): hp -36
  turn_end
    exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust.

### Round 2
Intent: Bowlbug (Silk): Attack(4x2=8), Slumbering Beetle: Sleep
  Escape Plan
    block +3
  Leg Sweep -> Bowlbug (Silk)[0]
    energy -2 | block +11 | enemy_deltas: Bowlbug (Silk): +Weak(2)
  Well-Laid Plans+
    energy -1 | block +7 | +Well-Laid Plans(2)
  turn_end
  Envenom+
  Backflip

### Round 3
Intent: Bowlbug (Silk): Debuff, Slumbering Beetle: Sleep
  Afterimage
    energy -1 | +Afterimage(1)
  Envenom+
    energy -2 | block +1 | +Envenom(2)
  Strike -> Bowlbug (Silk)[0]
    energy -1 | block +1 | enemy_deltas: Bowlbug (Silk): DIED
  turn_end
  Backflip
  Survivor+

### Round 4
Intent: Slumbering Beetle: Attack(16), Buff
  Expose -> Slumbering Beetle[0]
    block +1 | exhausted: Shiv+*2 [0]: Deal 6 damage. Exhaust. | enemy_deltas: Slumbering Beetle: block -13, +Vulnerable(2)
  Neutralize+ -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, +Poison(3), +Weak(2)
  Leading Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -4, Poison(3→6)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(6→9)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(9→12)
  Accelerant
    energy -1 | block +1 | +Accelerant(1)
  Survivor+
    energy -1 | block +11
  Defend
  Backflip
    energy -1 | block +6
  turn_end
  Defend
  Leading Strike

### Round 5
Intent: Slumbering Beetle: Attack(13), Buff
  Leading Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -4, Poison(10→13)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(13→16)
  Shiv -> Slumbering Beetle[0]
    block +1 | enemy_deltas: Slumbering Beetle: hp -6, Poison(16→19)
  Strike -> Slumbering Beetle[0]
    energy -1 | block +1 | enemy_deltas: Slumbering Beetle: hp -9, Poison(19→22)
  Finisher -> Slumbering Beetle[0]
    energy -1 | block -4 | -Well-Laid Plans | -Afterimage | -Envenom | -Accelerant | enemy_deltas: Slumbering Beetle: DIED
## Combat Analytics: multi:Bowlbug (Rock)+Bowlbug (Silk)+Slumbering Beetle (WIN - 5 rounds)

Cards played (with descriptions):
  Strangle+ "Retain. Deal 10 damage. Whenever you play a card this turn, the enemy loses 3 HP." -> 1 plays, 10 dmg
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 14 dmg, 2 block, +6 poison, generates 2 Shivs
  Hidden Daggers+ "Discard 2 cards. Add 2 Shivs+ into your Hand." -> 1 plays, generates 2 Shivs
  Shiv "Deal 4 damage. Exhaust." -> 6 plays, 38 dmg, 4 block, +12 poison, EXHAUST
  Shiv+ "Deal 6 damage. Exhaust." -> 2 plays, 9 dmg, EXHAUST
  Finisher "Deal 6 damage for each Attack already played this turn. (Hits 6 times)" -> 2 plays, 36 dmg
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 1 plays, 3 block
  Leg Sweep "Apply 2 Weak. Gain 11 Block." -> 1 plays, 11 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays, 7 block
  Afterimage "Whenever you play a card, gain 1 Block." -> 1 plays
  Envenom+ "Whenever an Attack deals unblocked damage, apply 2 Poison." -> 1 plays, 1 block
  Strike "Deal 6 damage." -> 2 plays, 9 dmg, 2 block, +3 poison
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, 1 block, EXHAUST
  Neutralize+ "Deal 4 damage. Apply 2 Weak." -> 1 plays, 6 dmg, 1 block, +3 poison
  Accelerant "Poison is triggered 1 additional time." -> 1 plays, 1 block
  Survivor+ "Gain 11 Block. Discard 1 card." -> 1 plays, 11 block
  Backflip "Gain 5 Block. Draw 2 cards." -> 1 plays, 6 block

Token attribution (Shivs):
  Leading Strike: 6 Shivs -> ~35 dmg
  Hidden Daggers+: 2 Shivs -> ~12 dmg

Poison stacks applied per card:
  Shiv: 12 stacks
  Leading Strike: 6 stacks
  Neutralize+: 3 stacks
  Strike: 3 stacks
Total poison/power tick damage: 10
  Per round: R1:4 R3:6

Enemy power timeline:
  Imbalanced: R1:1 -> R2:- -> R3:- -> R4:- -> R5:-
  Plating: R1:15 -> R2:14 -> R3:13 -> R4:- -> R5:-
  Poison: R1:- -> R2:- -> R3:- -> R4:- -> R5:10
  Slumber: R1:3 -> R2:2 -> R3:1 -> R4:- -> R5:-
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1
  Weak: R1:- -> R2:- -> R3:1 -> R4:- -> R5:1

[Selected: boss] Knowledge Demon (F33, boss)
Historical: loss=10 vs historical avg=34.2+/-16.1 (z=-1.5, BETTER_THAN_USUAL, n=4)
## Combat Replay: vs Knowledge Demon (Floor 33, boss)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood, Letter Opener
Deck (27): Defend x4, Strike x2, Strike+ x2, Ascender's Bane, Backflip, Blade Dance, Blade of Ink, Cloak and Dagger, Dash+, Defend+, Deflect, Expose, Exterminate, Flick-Flack, Leading Strike, Neutralize, Piercing Wail, Prepared+, Skewer+, Survivor+, Tracking+, Well-Laid Plans+
Enemies: Knowledge Demon HP=379/379

### Round 1
Intent: Knowledge Demon: Debuff
  Dexterity Potion
    +Dexterity(2)
  Tracking+
    energy -1 | +Tracking(2)
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: hp -6, +Weak(1)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(1→2)
  Exterminate
    energy -1 | block +4 | enemy_deltas: Knowledge Demon: hp -88
  turn_end
  Disintegration
    +Disintegration(6)

### Round 2
Agent plan (hypothesis): Retain key cards for next turn's 3-hit multi-attack.
Intent: Knowledge Demon: Attack(12)
  Dash+ -> Knowledge Demon[0]
    energy -2 | block +15 | enemy_deltas: Knowledge Demon: hp -26
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Prepared+
  Flick-Flack
  Strike
  Expose -> Knowledge Demon[0]
    exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: +Vulnerable(2)
  turn_end
  Defend
  Defend

### Round 3
Agent plan (hypothesis): Retain Backflip if possible to draw next turn.
Intent: Knowledge Demon: Attack(8x3=24)
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, +Weak(1)
  Piercing Wail
    energy -1 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: +Strength(-6), +Piercing Wail(6)
  Leading Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9
  Shiv -> Knowledge Demon[0]
    block +4 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  Blade Dance
    energy -1 | exhausted: Shiv*2 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -12
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12
  turn_end
  Defend
  Backflip

### Round 4
Agent plan (hypothesis): Look for Weak applicators and high-damage attacks to burst the boss down. Disintegration deals 5 end-of-turn damage.
Intent: Knowledge Demon: Attack(11), Heal, Buff
  Deflect
    block +6
  Backflip
    energy -1 | block +7
  Leading Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -3
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -4
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -4
  Skewer+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -11
  turn_end
    exhausted: Shiv*7 [0]: Deal 4 damage. Exhaust.
  Survivor+
  Defend+

### Round 5
Agent plan (hypothesis): We will take 5 damage from Disintegration at the end of the turn, but HP is healthy. Retain a high value card next turn.
Agent plan (hypothesis): Retained Dash+ to handle next turn's incoming damage.
Intent: Knowledge Demon: Debuff
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5, +Weak(1)
  Prepared+
  Strike+
  Strike+
  Blade of Ink
    energy -1
  Cloak and Dagger
    energy -1 | block +8 | enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(1→2)
  Shiv -> Knowledge Demon[0]
    block +4 | enemy_deltas: Knowledge Demon: hp -12, Weak(2→3)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Exterminate
    energy -1 | enemy_deltas: Knowledge Demon: hp -24
  turn_end
  Survivor+
  Dash+
  Disintegration
    Disintegration(6→13)

### Round 6
Agent plan (hypothesis): Retain Dash+ for next turn to handle the 18 incoming damage and push for the kill.
Intent: Knowledge Demon: Attack(14)
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(2→3)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -12, Weak(3→4)
  Leading Strike -> Knowledge Demon[0]
    energy -1 | block +4 | enemy_deltas: Knowledge Demon: hp -6
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -8
  Survivor+
    energy -1 | block +13
  Flick-Flack
  turn_end
    block +4 | enemy_deltas: Knowledge Demon: hp -12
  Dash+
  Defend

### Round 7
Agent plan (hypothesis): We defeated the Act 2 boss!
Intent: Knowledge Demon: Attack(7x3=21)
  Neutralize -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -10, Weak(3→4)
  Dash+ -> Knowledge Demon[0]
    energy -2 | block +15 | enemy_deltas: Knowledge Demon: hp -26
  Strike+ -> Knowledge Demon[0]
    energy -1 | block -15 | -Dexterity | -Tracking | -Disintegration | -Well-Laid Plans | enemy_deltas: Knowledge Demon: DIED
## Combat Analytics: Knowledge Demon (WIN - 7 rounds)

Cards played (with descriptions):
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 3 plays
  Shiv "Deal 6 damage. Apply 1 Weak. Exhaust." -> 16 plays, 158 dmg, 16 block, EXHAUST
  Exterminate "Deal 11 damage 4 times to ALL enemies." -> 2 plays, 112 dmg, 4 block
  Dash+ "Gain 15 Block. Deal 13 damage." -> 2 plays, 52 dmg, 30 block
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Neutralize "Deal 5 damage. Apply 1 Weak." -> 3 plays, 22 dmg
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 18 dmg, 4 block, generates 2 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Deflect "Gain 6 Block." -> 1 plays, 6 block
  Backflip "Gain 7 Block. Draw 2 cards." -> 1 plays, 7 block
  Skewer+ "Deal 11 damage X times." -> 1 plays, 11 dmg
  Cloak and Dagger "Gain 8 Block. Add 1 Shiv into your Hand." -> 1 plays, 5 dmg, 8 block, generates 1 Shivs
  Survivor+ "Gain 13 Block. Discard 1 card." -> 1 plays, 13 block
  Strike+ "Deal 9 damage." -> 1 plays

Token attribution (Shivs):
  other: 6 Shivs -> ~59 dmg
  Leading Strike: 6 Shivs -> ~59 dmg
  Blade Dance: 3 Shivs -> ~30 dmg
  Cloak and Dagger: 1 Shivs -> ~10 dmg

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:- -> R4:- -> R5:2 -> R6:2 -> R7:2
  Vulnerable: R1:- -> R2:- -> R3:1 -> R4:- -> R5:- -> R6:- -> R7:-
  Weak: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:2 -> R7:3
Comparator (recent worse/typical same-enemy comparator):
## Combat Replay: vs Knowledge Demon (Floor 33, boss)
Relics: Ring of the Snake, Arcane Scroll, Happy Flower, Pael's Claw, The Chosen Cheese, Bronze Scales, Vajra
Deck (23): Defend x5, Escape Plan x2, Ascender's Bane, Blade of Ink, Dagger Throw, Deflect+, Flick-Flack, Grand Finale, Leading Strike+, Malaise, Neutralize+, Pounce, Skewer+, Strangle, Strike, Sucker Punch+, Survivor+, Toric Toughness
Enemies: Knowledge Demon HP=379/379

### Round 1
Intent: Knowledge Demon: Debuff
  Leading Strike+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  Shiv -> Knowledge Demon[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Dagger Throw -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10
  Flick-Flack
  Strike -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  turn_end
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust.
  Disintegration
    +Disintegration(6)

### Round 2
Intent: Knowledge Demon: Attack(17)
  Strangle -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9, +Strangle(2)
  Defend
    energy -1 | block +7 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Knowledge Demon: hp -2
  Malaise -> Knowledge Demon[0]
    energy -2 | exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Knowledge Demon: hp -2, +Strength(-2), +Weak(2)
  turn_end

### Round 3
Intent: Knowledge Demon: Attack(4x3=12)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5, Weak(1→3)
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    exhausted: Shiv*2 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Knowledge Demon: hp -7, Weak(3→4)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, Weak(4→5)
  Sucker Punch+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -11, Weak(5→7)
  Survivor+
    energy -1 | block +11
  turn_end
    block -6

### Round 4
Intent: Knowledge Demon: Attack(6), Heal, Buff
  Grand Finale
    enemy_deltas: Knowledge Demon: hp -61
  Deflect+
    block +7
  Escape Plan
    block +3
  Escape Plan
  Dagger Throw -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10
  Defend
  Leading Strike+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Defend
    energy -1 | block +9 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  turn_end
    block -6

### Round 5
Intent: Knowledge Demon: Debuff
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2)
  Flick-Flack
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  Defend
    energy -1 | block +9
  turn_end
  Disintegration
    Disintegration(6→13)

### Round 6
Intent: Knowledge Demon: Attack(12)
  Strangle -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9, +Strangle(2)
  Blade of Ink
    energy -1 | enemy_deltas: Knowledge Demon: hp -2
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -9, Weak(4→5)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -9, Weak(5→6)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, Weak(6→8)
  Deflect+
    block +7 | enemy_deltas: Knowledge Demon: hp -2
  Survivor+
    energy -1 | block +11 | enemy_deltas: Knowledge Demon: hp -2
  turn_end
    enemy_deltas: Knowledge Demon: -Strangle

### Round 7
Intent: Knowledge Demon: Attack(6x3=18)
  Pounce -> Knowledge Demon[0]
    energy -2 | +Free Skill(1) | enemy_deltas: Knowledge Demon: hp -13
  Defend
    block +9 | -Free Skill
  Blade of Ink
    energy -1
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, Weak(7→8)
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, Weak(8→9)
  turn_end

### Round 8
Intent: Knowledge Demon: Attack(8), Heal, Buff
  Escape Plan
  Deflect+
    block +7
  Dagger Throw -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10
  Strike
  Leading Strike+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Survivor+
    energy -1 | block +11
  turn_end
    block -13

### Round 9
Intent: Knowledge Demon: Debuff
  Escape Plan
  Strangle -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9, +Strangle(2)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -7, Weak(7→9)
  Toric Toughness
    energy -2 | block +5 | +Toric Toughness(2) | enemy_deltas: Knowledge Demon: hp -2
  turn_end
  Waste Away
    +Waste Away(1)

### Round 10
Intent: Knowledge Demon: Attack(14)
  Deflect+
    block +7
  Leading Strike+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -7
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Shiv -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5
  Survivor+
    energy -1 | block +11
  Grand Finale
  turn_end

### Round 11
Intent: Knowledge Demon: Attack(7x3=21)
  Neutralize+ -> Knowledge Demon[0]
    enemy_deltas: Knowledge Demon: hp -5, Weak(7→9)
  Strangle -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -9, +Strangle(2)
  Dagger Throw -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -10
  Flick-Flack
  Escape Plan
    block +3 | enemy_deltas: Knowledge Demon: hp -2
  Sucker Punch+ -> Knowledge Demon[0]
    energy -1 | enemy_deltas: Knowledge Demon: hp -13, Weak(9→11)
  turn_end
## Combat Analytics: Knowledge Demon (LOSS - 11 rounds)
Death cause: Killed by damage. HP 2 -> 0, took 0 damage.

Cards played (with descriptions):
  Leading Strike+ "Deal 7 damage. Add 2 Shivs into your Hand." -> 4 plays, 28 dmg, generates 2 Shivs
  Shiv "Deal 5 damage. Exhaust." -> 14 plays, 86 dmg, EXHAUST
  Dagger Throw "Deal 10 damage. Draw 1 card. Discard 1 card." -> 4 plays, 40 dmg
  Strike "Deal 7 damage." -> 1 plays, 7 dmg
  Strangle "Deal 9 damage. Whenever you play a card this turn, the enemy loses 2 HP." -> 4 plays, 36 dmg
  Defend "Gain 7 Block. Permanently increase this card's Block by 1. Exhaust." -> 4 plays, 2 dmg, 34 block, EXHAUST
  Malaise "Enemy loses X Strength. Apply X Weak. Exhaust." -> 1 plays, 2 dmg, EXHAUST
  Neutralize+ "Deal 5 damage. Apply 2 Weak." -> 4 plays, 24 dmg
  Blade of Ink "Add 2 Inky Shivs into your Hand." -> 3 plays, 2 dmg
  Sucker Punch+ "Deal 11 damage. Apply 2 Weak." -> 2 plays, 24 dmg
  Survivor+ "Gain 11 Block. Discard 1 card." -> 4 plays, 2 dmg, 44 block
  Grand Finale "Can only be played if there are no cards in your Draw Pile. Deal 61 damage to ALL enemies." -> 1 plays, 61 dmg
  Deflect+ "Gain 7 Block." -> 4 plays, 2 dmg, 28 block
  Escape Plan "Draw 1 card. If you draw a Skill, gain 3 Block." -> 5 plays, 2 dmg, 6 block
  Toric Toughness "Gain 5 Block. Gain 5 Block at the start of the next 2 turns." -> 2 plays, 2 dmg, 10 block
  Flick-Flack "Sly. Deal 7 damage to ALL enemies." -> 1 plays, 7 dmg
  Pounce "Deal 13 damage. The next Skill you play costs 0 energy ." -> 1 plays, 13 dmg

Active powers: Thorns(3), Strength(1)

Token attribution (Shivs):
  Leading Strike+: 8 Shivs -> ~49 dmg
  other: 6 Shivs -> ~37 dmg

Enemy power timeline:
  Strength: R1:- -> R2:- -> R3:-2 -> R4:-2 -> R5:- -> R6:- -> R7:- -> R8:- -> R9:2 -> R10:2 -> R11:2
  Weak: R1:- -> R2:- -> R3:1 -> R4:6 -> R5:5 -> R6:4 -> R7:7 -> R8:8 -> R9:7 -> R10:8 -> R11:7

[Selected: boss] Test Subject (F48, boss)
Historical: loss=9 vs historical avg=29.3+/-22.4 (z=-0.9, TYPICAL, n=3)
## Combat Replay: vs Test Subject (Floor 48, boss)
Relics: Ring of the Snake, Booming Conch, Whetstone, Lasting Candy, War Paint, Ornamental Fan, Pael's Blood, Letter Opener, Brilliant Scarf, Red Mask, Joss Paper, Captain's Wheel
Deck (33): Defend x4, Footwork+ x2, Strike x2, Strike+ x2, Adrenaline+, Ascender's Bane, Backflip, Blade Dance, Blade Dance+, Blade of Ink+, Cloak and Dagger, Clumsy, Dash+, Defend+, Deflect, Expertise, Expose, Exterminate, Flick-Flack, Leading Strike, Neutralize, Piercing Wail, Prepared+, Skewer+, Survivor+, Tracking+, Well-Laid Plans+
Enemies: Test Subject #C64 HP=100/100

### Round 1
Agent plan (hypothesis): Boss revives with new powers and cleansed debuffs/buffs on death. Prepare to hold Piercing Wail with WLP for the heavy multi-attacks in Phase 2.
Agent plan (hypothesis): Hold Blade Dance via WLP for next turn. Next turn we will likely trigger phase 2.
Agent plan (hypothesis): Hold Exterminate and Blade Dance to quickly end Phase 1 next turn and prepare for Phase 2's heavy hitting attacks.
Intent: Test Subject #C64: Attack(15)
  Strength Potion
    +Strength(2)
  Expose -> Test Subject #C64[0]
    exhausted: Expose [0]: Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust. | enemy_deltas: Test Subject #C64: +Vulnerable(2), +Strength(2)
  Blade of Ink+
    energy -1 | enemy_deltas: Test Subject #C64: Strength(2→4)
  Shiv -> Test Subject #C64[0]
    exhausted: Shiv [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Test Subject #C64: hp -12, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12, Weak(2→3)
  Dash+ -> Test Subject #C64[0]
    block +17 | enemy_deltas: Test Subject #C64: hp -22
  Footwork+
    energy -1 | +Dexterity(3)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Deflect
    block +7 | enemy_deltas: Test Subject #C64: hp -5, Strength(4→6)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12, Weak(3→4)
  turn_end
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Blade Dance
  Exterminate

### Round 2
Intent: Test Subject #C64: Attack(15), Debuff
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -10, Weak(3→4)
  Exterminate
    energy -1 | enemy_deltas: Test Subject #C64: hp -27, -Enrage, -Weak, -Vulnerable, -Strength, DIED
  turn_end
  Blade Dance
  Blade Dance+

### Round 3
Agent plan (hypothesis): Continue using free cards and scaling damage.
Intent: Test Subject #C64: Attack(10x3=30)
  Footwork+
    energy -1 | Dexterity(3→6)
  Cloak and Dagger
    energy -1 | block +12
  Shiv -> Test Subject #C64[0]
    exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust. | enemy_deltas: Test Subject #C64: hp -6
  Blade Dance
    energy -1 | exhausted: Shiv*3 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  turn_end
  Blade Dance+
  Backflip

### Round 4
Agent plan (hypothesis): Hold key defensive skills for phase 3 where Nemesis makes the boss intangible.
Agent plan (hypothesis): Damage heavily mitigated.
Agent plan (hypothesis): Phase 2 multi-attacks will increase in hit count. Try to end this phase quickly.
Intent: Test Subject #C64: Attack(10x4=40)
  Adrenaline+
    energy +2 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust.
  Prepared+
  Flick-Flack
  Ascender's Bane
  Piercing Wail
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C64: hp -5, +Strength(-6), +Piercing Wail(6)
  Tracking+
    energy -1 | +Tracking(2)
  Backflip
    block +11
  Leading Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -5
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -8
  Defend
    energy -1 | block +11
  Prepared+
  Flick-Flack
  Strike
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -7, +Weak(1)
  Skewer+ -> Test Subject #C64[0]
  turn_end
  Blade Dance+
  Strike+

### Round 5
Agent plan (hypothesis): Retain Exterminate to push through Phase 2. Next turn, use card draw to find Weak sources to double its damage.
Agent plan (hypothesis): Retain Exterminate for the next turn to burst the boss with Tracking.
Intent: Test Subject #C64: Attack(10x5=50)
  Blade Dance+
    energy -1 | exhausted: Shiv*6 [0]: Deal 4 damage. Exhaust.
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -6
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -6
  Dash+ -> Test Subject #C64[0]
    block +19 | enemy_deltas: Test Subject #C64: hp -15
  Survivor+
    energy -1 | block +17
  Ascender's Bane
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -5
  turn_end
  Exterminate
  Defend

### Round 6
Agent plan (hypothesis): Boss revives with Nemesis (Intangible). Set up defense and retain block cards for the heavy attacks.
Intent: Test Subject #C64: Attack(10x6=60)
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Exterminate
    enemy_deltas: Test Subject #C64: hp -40, -Weak, DIED
  turn_end
  Defend+
  Cloak and Dagger

### Round 7
Intent: Test Subject #C64: Attack(10x3=30)
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1
  Defend+
    energy -1 | block +14
  Defend
    energy -1 | block +22 | enemy_deltas: Test Subject #C64: hp -1
  Cloak and Dagger
    energy -1 | block +12
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -1
  turn_end
  Blade of Ink+
  Strike+

### Round 8
Agent plan (hypothesis): Next turn the boss is Intangible and might attack or add statuses. Focus on block and set up.
Intent: Test Subject #C64: Attack(45)
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Dash+ -> Test Subject #C64[0]
    block +19 | enemy_deltas: Test Subject #C64: hp -30
  Backflip
    energy -1 | block +11
  Exterminate
    energy -1 | enemy_deltas: Test Subject #C64: hp -40
  turn_end
  Leading Strike
  Expertise

### Round 9
Agent plan (hypothesis): Retain Skewer+ and an offensive utility for next turn.
Agent plan (hypothesis): Boss is vulnerable next turn. Unleash Skewer+.
Intent: Test Subject #C64: StatusCard(3), Buff
  Deflect
    block +10
  Leading Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -1
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -1
  Survivor+
    block +17
  Defend
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -1
  turn_end
    exhausted: Shiv*9 [0]: Deal 6 damage. Apply 1 Weak. Exhaust.
  Expertise
  Skewer+

### Round 10
Agent plan (hypothesis): Boss will be Intangible next turn, prioritize defense and setup. Following turn, boss will be vulnerable and easy to kill.
Intent: Test Subject #C64: Attack(9x3=27)
  Deflect
    block +10
  Neutralize -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -14, Weak(1→2)
  Strike -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -16
  Leading Strike -> Test Subject #C64[0]
    energy -1 | block +4 | enemy_deltas: Test Subject #C64: hp -10
  Strike+ -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -22
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -12
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -12
  Skewer+ -> Test Subject #C64[0]
    energy -1 | enemy_deltas: Test Subject #C64: hp -26
  turn_end
  Expertise
  Strike+

### Round 11
Agent plan (hypothesis): Next turn the boss loses Intangible. Look to apply Weak and unleash burst damage to finish the 70 HP.
Agent plan (hypothesis): Next turn burst the boss.
Intent: Test Subject #C64: Attack(35)
  Prepared+
  Burn
  Strike
  Survivor+
    energy -1 | block +17
  Strike+
  Defend
    energy -1 | block +11 | enemy_deltas: Test Subject #C64: hp -1
  Defend
    energy -1 | block +22
  turn_end
  Expertise
  Exterminate

### Round 12
Agent plan (hypothesis): We did it.
Intent: Test Subject #C64: StatusCard(3), Buff
  Blade of Ink+
    energy -1
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -8, +Weak(1)
  Shiv -> Test Subject #C64[0]
    enemy_deltas: Test Subject #C64: hp -16, Weak(1→2)
  Shiv -> Test Subject #C64[0]
    block +4 | enemy_deltas: Test Subject #C64: hp -16, Weak(2→3)
  Exterminate
    block -4 | -Strength | -Dexterity | -Well-Laid Plans | -Tracking | enemy_deltas: Test Subject #C64: DIED
## Combat Analytics: Test Subject (WIN - 12 rounds)

Cards played (with descriptions):
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Blade of Ink+ "Add 3 Inky Shivs into your Hand." -> 4 plays
  Shiv "Deal 8 damage. Apply 1 Weak. Exhaust." -> 27 plays, 238 dmg, 36 block, EXHAUST
  Dash+ "Gain 13 Block. Deal 15 damage." -> 3 plays, 67 dmg, 55 block
  Footwork+ "Gain 3 Dexterity." -> 2 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Deflect "Gain 7 Block." -> 3 plays, 5 dmg, 27 block
  Neutralize "Deal 7 damage. Apply 1 Weak." -> 4 plays, 32 dmg
  Exterminate "Deal 13 damage 4 times to ALL enemies." -> 4 plays, 107 dmg
  Cloak and Dagger "Gain 12 Block. Add 1 Shiv into your Hand." -> 2 plays, 24 block, generates 1 Shivs
  Blade Dance "Add 3 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 3 Shivs
  Adrenaline+ "Gain 2 energy . Draw 2 cards. Exhaust." -> 1 plays, EXHAUST
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 3 plays
  Piercing Wail "ALL enemies lose 6 Strength this turn. Exhaust." -> 1 plays, 5 dmg, EXHAUST
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays
  Backflip "Gain 11 Block. Draw 2 cards." -> 2 plays, 22 block
  Leading Strike "Deal 5 damage. Add 2 Shivs into your Hand." -> 3 plays, 16 dmg, 4 block, generates 2 Shivs
  Strike "Deal 8 damage." -> 2 plays, 24 dmg
  Defend "Gain 11 Block." -> 6 plays, 8 dmg, 88 block
  Skewer+ "Deal 13 damage X times." -> 2 plays, 26 dmg
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 1 plays, EXHAUST, generates 4 Shivs
  Survivor+ "Gain 17 Block. Discard 1 card." -> 3 plays, 51 block
  Defend+ "Gain 14 Block." -> 1 plays, 14 block
  Strike+ "Deal 11 damage." -> 1 plays, 22 dmg

Token attribution (Shivs):
  other: 13 Shivs -> ~115 dmg
  Leading Strike: 6 Shivs -> ~53 dmg
  Blade Dance: 3 Shivs -> ~26 dmg
  Blade Dance+: 3 Shivs -> ~26 dmg
  Cloak and Dagger: 2 Shivs -> ~18 dmg

Enemy power timeline:
  Adaptable: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Enrage: R1:2 -> R2:2 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:1 -> R10:- -> R11:1 -> R12:-
  Nemesis: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1 -> R9:1 -> R10:1 -> R11:1 -> R12:1
  Painful Stabs: R1:- -> R2:- -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Strength: R1:- -> R2:6 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:2 -> R11:2 -> R12:2
  Vulnerable: R1:- -> R2:1 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:- -> R11:- -> R12:-
  Weak: R1:1 -> R2:3 -> R3:- -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:2 -> R10:1 -> R11:1 -> R12:-
Comparator (recent same-enemy comparator):
## Combat Replay: vs Test Subject (Floor 48, boss)
Relics: Ring of the Snake, Small Capsule, Candelabra, Venerable Tea Set, Kunai, Archaic Tooth, War Paint, Preserved Fog, Meat on the Bone
Deck (32): Defend x4, Blade Dance+ x3, Flick-Flack x2, Knife Trap+ x2, Backflip+, Calculated Gamble, Cloak and Dagger+, Dagger Throw, Dodge and Roll+, Expose, Folly, Footwork+, Hidden Daggers, Leading Strike, Leading Strike+, Leg Sweep+, Phantom Blades+, Piercing Wail+, Prepared+, Ricochet, Suppress+, Survivor, Tracking+, Untouchable, Well-Laid Plans+
Enemies: Test Subject #C62 HP=100/100

### Round 1
Intent: Test Subject #C62: Attack(20)
  Suppress+ -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -17, +Weak(5)
  Power Potion
  Accuracy
  Accuracy
    +Accuracy(4)
  Cloak and Dagger+
    energy -1 | block +6 | enemy_deltas: Test Subject #C62: +Strength(2)
  Shiv -> Test Subject #C62[0]
    exhausted: Shiv [0]: Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C62: hp -8
  Shiv -> Test Subject #C62[0]
    +Dexterity(1) | enemy_deltas: Test Subject #C62: hp -8
  Prepared+
  Untouchable
  Folly
  Survivor
    energy -1 | block +9
  Knife Trap+
  turn_end

### Round 2
Intent: Test Subject #C62: Attack(16), Debuff
  Footwork+
    energy -1 | Dexterity(1→4)
  Well-Laid Plans+
    energy -1 | +Well-Laid Plans(2)
  Leading Strike+ -> Test Subject #C62[0]
    energy -1 | enemy_deltas: Test Subject #C62: hp -6
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -8
  Shiv -> Test Subject #C62[0]
    Dexterity(4→5) | enemy_deltas: Test Subject #C62: hp -8
  Blade Dance+
    energy -1 | exhausted: Shiv*4 [0]: Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C62: Strength(8→10)
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -8
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -8
  Shiv -> Test Subject #C62[0]
    Dexterity(5→6) | enemy_deltas: Test Subject #C62: hp -8
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -8
  turn_end
  Calculated Gamble
  confirm

### Round 3
Intent: Test Subject #C62: Attack(33)
  Phantom Blades+
    energy -1 | +Phantom Blades(12)
  Hidden Daggers
  Ricochet
  Calculated Gamble
  Blade Dance+
    energy -1 | enemy_deltas: Test Subject #C62: hp -6, Strength(10→14)
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -1, -Enrage, -Weak, -Strength, DIED
  turn_end
  Defend
  confirm

### Round 4
Intent: Test Subject #C62: Attack(10x3=30)
  Expose -> Test Subject #C62[0]
    exhausted: Shiv*9 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C62: +Vulnerable(2)
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -30
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    Dexterity(6→7) | enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Leading Strike -> Test Subject #C62[0]
    energy -1 | Dexterity(7→8) | enemy_deltas: Test Subject #C62: hp -4
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Blade Dance+
    energy -1
  Shiv -> Test Subject #C62[0]
    Dexterity(8→9) | enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -12
  Shiv -> Test Subject #C62[0]
    Dexterity(9→10) | enemy_deltas: Test Subject #C62: hp -12
  Defend
    energy -1 | block +15
  turn_end
  Flick-Flack
  confirm

### Round 5
Intent: Test Subject #C62: Attack(10x4=40)
  Piercing Wail+
    energy -1 | exhausted: Shiv*20 [0]: Retain. Deal 4 damage. Exhaust. | enemy_deltas: Test Subject #C62: +Strength(-8), +Piercing Wail(8)
  Backflip+
    energy -1 | block +18
  Tracking+
    energy -1 | +Tracking(2)
  turn_end
  Leg Sweep+
  Dagger Throw

### Round 6
Intent: Test Subject #C62: Attack(10x5=50)
  Knife Trap+ -> Test Subject #C62[0]
    energy -2 | Dexterity(10→16) | enemy_deltas: Test Subject #C62: hp -46, DIED
  Dodge and Roll+
    energy -1 | block +22 | +Block Next Turn(22)
  turn_end
  Leg Sweep+
  Backflip+

### Round 7
Intent: Test Subject #C62: Attack(10x3=30)
  Suppress+ -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -1, +Weak(5)
  Backflip+
    energy -1 | block +24
  Leading Strike+ -> Test Subject #C62[0]
    energy -1 | enemy_deltas: Test Subject #C62: hp -1
  Defend
    energy -1 | block +21
  turn_end
  Leg Sweep+
  Ricochet

### Round 8
Intent: Test Subject #C62: Attack(33)
  Leg Sweep+ -> Test Subject #C62[0]
    energy -2 | block +30 | enemy_deltas: Test Subject #C62: Weak(4→7)
  Cloak and Dagger+
    energy -1 | block +22
  Shiv -> Test Subject #C62[0]
    exhausted: Shiv+*20 [0]: Retain. Deal 6 damage. Exhaust. | enemy_deltas: Test Subject #C62: hp -40
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    Dexterity(16→17) | enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Hidden Daggers
  Ricochet
  Wound
  turn_end
    exhausted: Shiv+*20 [0]: Retain. Deal 6 damage. Exhaust. | enemy_deltas: Test Subject #C62: hp -12
  confirm_selection

### Round 9
Intent: Test Subject #C62: StatusCard(3), Buff
  Leading Strike -> Test Subject #C62[0]
    energy -1 | enemy_deltas: Test Subject #C62: hp -1
  Prepared+
  Untouchable
  Knife Trap+
  turn_end
  Calculated Gamble
  Hidden Daggers

### Round 10
Intent: Test Subject #C62: Attack(9x3=27)
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -40
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    Dexterity(17→18) | enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Cloak and Dagger+
    energy -1 | block +24
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    Dexterity(18→19) | enemy_deltas: Test Subject #C62: hp -16
  Hidden Daggers
  Wound
  Defend
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Backflip+
    energy -1 | block +27
  Leading Strike -> Test Subject #C62[0]
    energy -1 | Dexterity(19→20) | enemy_deltas: Test Subject #C62: hp -6
  Shiv -> Test Subject #C62[0]
    enemy_deltas: Test Subject #C62: hp -16
  Shiv -> Test Subject #C62[0]
    hp +12 | block -51 | -Accuracy | -Dexterity | -Well-Laid Plans | -Phantom Blades | -Tracking | enemy_deltas: Test Subject #C62: DIED
## Combat Analytics: Test Subject (WIN - 10 rounds)

Cards played (with descriptions):
  Suppress+ "Innate. Deal 17 damage. Apply 5 Weak." -> 2 plays, 18 dmg
  Accuracy "Shivs deal 4 additional damage." -> 1 plays
  Cloak and Dagger+ "Gain 6 Block. Add 2 Shivs into your Hand." -> 3 plays, 52 block, generates 2 Shivs
  Shiv "Deal 8 damage. Exhaust." -> 34 plays, 471 dmg, EXHAUST
  Prepared+ "Draw 2 cards. Discard 2 cards." -> 2 plays
  Survivor "Gain 9 Block. Discard 1 card." -> 1 plays, 9 block
  Footwork+ "Gain 3 Dexterity." -> 1 plays
  Well-Laid Plans+ "At the end of your turn, Retain up to 2 cards." -> 1 plays
  Leading Strike+ "Deal 6 damage. Add 2 Shivs into your Hand." -> 2 plays, 7 dmg, generates 2 Shivs
  Blade Dance+ "Add 4 Shivs into your Hand. Exhaust." -> 3 plays, 6 dmg, EXHAUST, generates 4 Shivs
  Phantom Blades+ "Shivs gain Retain. The first Shiv you play each turn deals 12 additional damage." -> 1 plays
  Hidden Daggers "Discard 2 cards. Add 2 Shivs into your Hand." -> 3 plays, generates 2 Shivs
  Expose "Remove all Artifact and Block from the enemy. Apply 2 Vulnerable. Exhaust." -> 1 plays, EXHAUST
  Leading Strike "Deal 3 damage. Add 2 Shivs into your Hand." -> 3 plays, 11 dmg, generates 2 Shivs
  Defend "Gain 15 Block." -> 2 plays, 36 block
  Piercing Wail+ "ALL enemies lose 8 Strength this turn. Exhaust." -> 1 plays, EXHAUST
  Backflip+ "Gain 18 Block. Draw 2 cards." -> 3 plays, 69 block
  Tracking+ "Weak enemies take double damage from Attacks." -> 1 plays
  Knife Trap+ "Upgrade and play every Shiv in your Exhaust Pile on the enemy. (Plays 20 Shivs)" -> 1 plays, 46 dmg, EXHAUST
  Dodge and Roll+ "Gain 22 Block. Next turn, gain 22 Block." -> 1 plays, 22 block
  Leg Sweep+ "Apply 3 Weak. Gain 30 Block." -> 1 plays, 30 block

Token attribution (Shivs):
  other: 9 Shivs -> ~125 dmg
  Blade Dance+: 8 Shivs -> ~111 dmg
  Cloak and Dagger+: 6 Shivs -> ~83 dmg
  Hidden Daggers: 5 Shivs -> ~69 dmg
  Leading Strike: 4 Shivs -> ~55 dmg
  Leading Strike+: 2 Shivs -> ~28 dmg

Enemy power timeline:
  Adaptable: R1:1 -> R2:1 -> R3:1 -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:-
  Enrage: R1:2 -> R2:2 -> R3:2 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Intangible: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:- -> R9:1 -> R10:-
  Nemesis: R1:- -> R2:- -> R3:- -> R4:- -> R5:- -> R6:- -> R7:1 -> R8:1 -> R9:1 -> R10:1
  Painful Stabs: R1:- -> R2:- -> R3:- -> R4:1 -> R5:1 -> R6:1 -> R7:- -> R8:- -> R9:- -> R10:-
  Strength: R1:- -> R2:8 -> R3:10 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:- -> R9:- -> R10:2
  Vulnerable: R1:- -> R2:- -> R3:- -> R4:- -> R5:1 -> R6:- -> R7:- -> R8:- -> R9:- -> R10:-
  Weak: R1:- -> R2:4 -> R3:3 -> R4:- -> R5:- -> R6:- -> R7:- -> R8:4 -> R9:6 -> R10:5

## Triggered Skills This Run
- Boss and Elite Fight Strategy: F12(Phantasmal Gardener: WIN), F17(Soul Fysh: WIN), F33(Knowledge Demon: WIN), F48(Test Subject #C64: WIN)
- Core Combat Principles: F2(Sludge Spinner: WIN), F3(Seapunk: WIN), F5(Corpse Slug: WIN), F8(Calcified Cultist: ), F12(Phantasmal Gardener: WIN), F17(Soul Fysh: WIN), F19(Bowlbug (Rock): WIN), F20(Tunneler: WIN), F22(Hunter Killer: WIN), F23(Bowlbug (Rock): ), F33(Knowledge Demon: WIN), F35(Devoted Sculptor: WIN), F37(Living Shield: ), F38(Fabricator: WIN), F39(Punch Construct: WIN), F45(Globe Head: WIN), F48(Test Subject #C64: WIN)
- Deck Building Across the Run: F2(), F3(), F4(), F5(), F6(), F8(), F12(), F13(), F13(), F13(), F17(), F19(), F20(), F22(), F23(), F25(), F28(), F28(), F30(), F31(), F33(), F33(), F33(), F35(), F37(), F38(), F39(), F45(), F46()
- Map Routing and Path Planning: F1(), F1(), F3(), F4(), F7(), F10(), F11(), F13(), F14(), F18(), F18(), F22(), F24(), F25(), F27(), F28(), F30(), F34(), F34(), F36(), F36(), F37(), F38(), F41(), F43(), F44()
- Poison Deck Thinning & Focus: F31()
- Rest Site and Event Decisions: F9(), F11(), F16(), F24(), F27(), F29(), F32(), F40(), F42(), F44(), F47()
- Silent - Combat Sequencing: F2(Sludge Spinner: WIN), F3(Seapunk: WIN), F5(Corpse Slug: WIN), F8(Calcified Cultist: ), F12(Phantasmal Gardener: WIN), F17(Soul Fysh: WIN), F19(Bowlbug (Rock): WIN), F20(Tunneler: WIN), F22(Hunter Killer: WIN), F23(Bowlbug (Rock): ), F33(Knowledge Demon: WIN), F35(Devoted Sculptor: WIN), F37(Living Shield: ), F38(Fabricator: WIN), F39(Punch Construct: WIN), F45(Globe Head: WIN), F48(Test Subject #C64: WIN)
- Silent - Draft and Shop Rules: F2(), F3(), F4(), F5(), F6(), F8(), F12(), F13(), F13(), F13(), F17(), F19(), F20(), F22(), F23(), F25(), F28(), F28(), F30(), F31(), F33(), F33(), F33(), F35(), F37(), F38(), F39(), F45(), F46()
- Silent - Route Priorities: F1(), F1(), F3(), F4(), F7(), F10(), F11(), F13(), F14(), F18(), F18(), F22(), F24(), F25(), F27(), F28(), F30(), F34(), F34(), F36(), F36(), F37(), F38(), F41(), F43(), F44()
- act1_mandatory_elites_shops: F1(), F1(), F3(), F4(), F7(), F10(), F11(), F13(), F14(), F18(), F18(), F22(), F24(), F25(), F27(), F28(), F30(), F34(), F34(), F36(), F36(), F37(), F38(), F41(), F43(), F44()
- act1_max_hp_event_trap: F1(), F4(), F6(), F14(), F18(), F21(), F25(), F34(), F36()

## Dynamic Tools

## Focus
Use rounds 1-2 to diagnose the biggest failures with evidence. From round 3 onward, write the smallest number of high-value improvements that fix the observed mistakes. When the cross-run pattern is unclear, run get_performance_stats first to ground your proposal in measurable data instead of guessing.