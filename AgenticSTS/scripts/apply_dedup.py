"""Apply deduplication to skills.json: delete 65 redundant skills, merge content into 20 keepers.

Usage:
    python -m scripts.apply_dedup --dry-run   # Print report only
    python -m scripts.apply_dedup              # Apply changes and write file
"""

import argparse
import json
import sys
from pathlib import Path

SKILLS_PATH = Path(__file__).parent.parent / "data" / "skills" / "skills.json"

# ---------------------------------------------------------------------------
# Indices to delete (0-based in original 116-skill array)
# ---------------------------------------------------------------------------
DELETE_INDICES: set[int] = {
    1, 9, 10, 11, 12, 13, 16, 18, 19, 22, 27, 30, 32, 34, 35, 36, 40, 41,
    46, 47, 48, 49, 50, 51, 53, 54, 55, 56, 57, 58, 59, 60, 61, 62, 63,
    64, 65, 67, 69, 70, 71, 72, 73, 74, 75, 77, 78, 81, 82, 85, 86, 88,
    89, 92, 93, 94, 98, 99, 100, 103, 104, 108, 111, 112, 114, 115,
}

# ---------------------------------------------------------------------------
# Merge specifications
# ---------------------------------------------------------------------------
# Each entry: keeper_index -> dict of updates to apply.
#   - "name": new name (optional)
#   - "content": new merged content
#   - "source_indices": indices being absorbed (for stats merging)
#   - "add_enemy_names": enemy names to add to trigger
#   - "add_tags": tags to add to trigger
#   - "state_types": override state_types (optional)

MERGE_SPECS: dict[int, dict] = {
    68: {
        "name": "Silent combat: poison, shiv, and multi-enemy strategy",
        "source_indices": [36, 40, 46, 49, 51, 53, 55, 57, 60, 63, 65, 70, 71, 114],
        "content": (
            "Silent combat revolves around three strategic modes: poison control, "
            "shiv burst, and multi-enemy prioritization.\n\n"
            "**Poison control (boss/elite fights)**:\n"
            "- Stack poison aggressively in the first 3-4 turns via Deadly Poison, "
            "Noxious Fumes, Bouncing Flask, Envenom\n"
            "- Once poison is ticking, evaluate whether existing stacks will kill "
            "the enemy. If poison is lethal within 2-3 turns, STOP adding poison "
            "and switch entirely to block/survival\n"
            "- Poison bypasses block entirely -- prioritize poison over direct "
            "damage against high-block enemies (Hard to Kill, Exoskeleton)\n"
            "- When deciding between a poison card and a block card, consider: "
            "can you survive long enough for poison to finish the kill? If yes, "
            "block. If no, more poison is wasted\n\n"
            "**Shiv burst (when Accuracy/Blade Dance/Finisher online)**:\n"
            "- Shiv damage = (base + Accuracy bonus) x shiv count. With Accuracy+2, "
            "6 shivs = 24 damage in one turn\n"
            "- Shiv burst beats poison when you need to kill one enemy THIS turn "
            "(e.g., summoner about to spawn, or enemy with lethal attack next turn)\n"
            "- Shivs are attacks -- they benefit from Strength and Vulnerable on target\n\n"
            "**Multi-enemy fights**:\n"
            "- Kill-one-fast strategy: focus ALL damage on the squishiest high-damage "
            "enemy to reduce total incoming damage permanently\n"
            "- Poison ticks on ALL enemies -- if running poison, apply to all then "
            "let ticks do the work while you block\n"
            "- AoE cards (Die Die Die, Dagger Spray) are efficient at 3+ enemies, "
            "but single-target focus-fire is usually faster for 2 enemies"
        ),
    },
    31: {
        "name": "Multi-enemy combat: offense windows and kill priority",
        "source_indices": [32, 50, 69],
        "content": (
            "In multi-enemy fights, offense is survival. Turtling behind block "
            "loses the attrition war because total incoming damage exceeds your "
            "block capacity every turn.\n\n"
            "**Offense windows -- non-attack intents are FREE turns**:\n"
            "- Before allocating energy, read ALL enemy intents. Non-attack intents "
            "(Buff, Debuff, Stun, Sleep) deal ZERO damage\n"
            "- If total incoming is <=8: FREE OFFENSE TURN. Play at most 1 block "
            "card. Spend remaining energy on attacks targeting one enemy\n"
            "- If only 1 of 3 enemies is attacking: block for that enemy only, "
            "spend remaining energy on offense\n\n"
            "**Kill priority -- reduce total DPT permanently**:\n"
            "- Focus fire the enemy with the best (damage_per_turn / HP) ratio. "
            "Usually the lower-HP, higher-damage enemy\n"
            "- Dead enemies deal zero damage. Each kill reduces incoming by 8-15/turn\n"
            "- Split damage across enemies is almost always wrong\n\n"
            "**Anti-turtling check (after round 2)**:\n"
            "- If no enemy is below 50% HP after 2 rounds, you are in a DEATH SPIRAL\n"
            "- Total enemy DPT stays constant while your HP decreases each turn\n"
            "- Pure blocking only delays death by 1-2 turns. Immediately switch to "
            "all-offense targeting the squishiest enemy"
        ),
    },
    38: {
        "name": "Low HP multi-enemy emergency protocol",
        "source_indices": [10],
        "content": (
            "When entering a multi-enemy fight at LOW HP (below 50% max HP), "
            "immediately assess the attrition math:\n\n"
            "1. **Calculate net damage**: Sum all enemy damage per turn, subtract "
            "your realistic block per turn. If net damage > 0, you have a CLOCK.\n"
            "2. **Turns to die** = Your HP / net damage per turn. If <=3, this is "
            "an EMERGENCY.\n"
            "3. **Pick ONE focus target** -- the enemy with the best "
            "(damage_per_turn / turns_to_kill) ratio. Usually the lower-HP, "
            "higher-damage enemy.\n"
            "4. **DO NOT split damage** across enemies. Every point of split damage "
            "is wasted -- it doesn't reduce incoming DPT until the enemy dies.\n\n"
            "**Emergency actions at <=25% HP or <=20 HP**:\n"
            "- Use ALL potions immediately -- damage potions on focus target, "
            "block potions for survival, AoE potions to soften all enemies\n"
            "- Prioritize AoE attacks if available (Die Die Die, Dagger Spray) to "
            "pressure multiple enemies simultaneously\n"
            "- NEVER play powers or setup cards on turn 1 unless you have confirmed "
            "you survive the turn with remaining energy spent on block\n"
            "- Calculate total incoming from ALL enemies FIRST. 3 enemies each "
            "hitting 10-12 = 30-36 total incoming"
        ),
    },
    80: {
        "name": "Summoner fight race priority",
        "source_indices": [73, 77],
        "add_enemy_names": ["Obscura"],
        "content": (
            "When fighting a SUMMONER enemy (one that spawns new minions each turn "
            "-- Fabricator, Louse Progenitor, Obscura, or any enemy with \"Summon\" "
            "intent), treat it as an URGENT RACE:\n\n"
            "1. **Kill the summoner ASAP** -- Every turn the summoner lives adds "
            "+10-18 damage per turn permanently. After 3 turns you face 45+ incoming "
            "damage and WILL die. Focus ALL damage on the summoner, not minions "
            "(unless a minion dies to 1 free attack).\n\n"
            "2. **DO NOT play long-term setup cards** -- Noxious Fumes, Infinite "
            "Blades, Envenom are too slow. The fight must end in 4-5 turns.\n\n"
            "3. **Specific summoners**:\n"
            "   - **Fabricator**: creates constructs. Focus Fabricator, ignore constructs.\n"
            "   - **Louse Progenitor**: spawns Louse minions every few turns. "
            "Lice deal 5-8 each; board floods fast. Pure DPS race.\n"
            "   - **Obscura**: summons Parafrights. Focus Obscura, ignore Parafrights.\n\n"
            "4. **Use potions aggressively** -- burst damage potions and buff potions "
            "turn 1. This fight is a sprint, not a marathon.\n\n"
            "5. **Only clean up minions** when a single AoE card can kill them as "
            "a side effect, or when a minion will kill you this turn."
        ),
    },
    83: {
        "name": "Defensive priority when incoming damage exceeds HP safety threshold",
        "source_indices": [78, 94],
        "content": (
            "**CRITICAL RULE: When incoming damage this turn exceeds 33% of your "
            "current HP, MAXIMIZE BLOCK unless one of these exceptions applies:**\n\n"
            "1. You can KILL the enemy this turn (dead enemies deal 0 damage)\n"
            "2. You have a potion that provides enough block/intangible\n"
            "3. Poison will kill before next attack (note: poison ticks at START "
            "of enemy turn, not before their attack this turn)\n\n"
            "**Threshold rules:**\n"
            "- Incoming >= 50% of HP: Block is THE priority. Spend at most 1 energy "
            "on offense.\n"
            "- Incoming >= 33% of HP: Must play at least 1 block card before offense.\n"
            "- Incoming >= 25% of HP (mandatory block): always play at least one "
            "block card when incoming is a quarter of your HP.\n\n"
            "**Never play Powers when facing lethal:**\n"
            "- When incoming_damage > (current_block + current_HP), every energy "
            "MUST go toward immediate block generation\n"
            "- Powers (Footwork, Infinite Blades, Noxious Fumes) provide ZERO "
            "block the turn they are played. They are dead cards on lethal turns.\n"
            "- Only exception: you have excess energy after maxing all possible block"
        ),
    },
    109: {
        "name": "Living Fog Smoggy mechanic",
        "source_indices": [81, 88],
        "add_enemy_names": ["Gas Bomb"],
        "content": (
            "**Living Fog** is an Act 1 enemy that applies the **Smoggy** debuff, "
            "which LIMITS you to playing only 1 Skill card per turn. This is "
            "devastating for skill-heavy decks.\n\n"
            "**Key mechanics:**\n"
            "- Turn 1: Living Fog attacks + applies Smoggy\n"
            "- Turn 2: Living Fog attacks + summons a Gas Bomb minion\n"
            "- Turn 3+: Both attack; Living Fog may summon more Gas Bombs\n\n"
            "**Why this is a rush-down fight:**\n"
            "- Smoggy limits skills to 1/turn. Most block comes from Skills "
            "(Defend, Survivor, Cloak and Dagger). With only 1 skill, you get ~5 "
            "block vs 16+ incoming once Gas Bomb spawns = taking 11+ damage/turn.\n"
            "- CardDebuff cost increases mean more cards become unplayable each "
            "turn. After 3-4 turns you will have dead turns and die.\n\n"
            "**Combat priorities under Smoggy:**\n"
            "1. Kill Living Fog FAST before it summons. Front-load ALL damage "
            "in rounds 1-2.\n"
            "2. Use your 1 skill slot on the highest-value skill (Leg Sweep > "
            "Backflip > Defend).\n"
            "3. Prioritize Attack cards since they are unlimited under Smoggy.\n"
            "4. Use potions aggressively -- damage potions to end the fight quickly."
        ),
    },
    107: {
        "name": "Sloth play-limit prioritization",
        "source_indices": [108],
        "add_enemy_names": ["Knowledge Demon"],
        "content": (
            "When you have the SLOTH debuff (limits card plays per turn to 3), "
            "radically change your play priority:\n\n"
            "**CRITICAL: Each play slot is extremely precious. Do NOT waste slots "
            "on low-impact cards.**\n\n"
            "Priority order for 3 plays:\n"
            "1. BURST + high-value Skill (Leg Sweep, Backflip, Defend) -- Burst "
            "doubles the skill, getting 2-for-1 value.\n"
            "2. LEG SWEEP -- Gives block AND Weak in one play. Effectively replaces "
            "2 cards.\n"
            "3. BACKFLIP -- Gives block AND draws 2 cards.\n"
            "4. High-damage attacks (Predator, Eviscerate) over multiple small attacks.\n"
            "5. Never waste a slot on Strike when better options exist.\n\n"
            "**Powers-first strategy (before debuff lands):**\n"
            "In the first 3-4 turns BEFORE Sloth is applied, prioritize playing "
            "Power cards:\n"
            "1. Noxious Fumes -- #1 priority. Free poison every turn = your win "
            "condition when plays are limited.\n"
            "2. Footwork -- Free dexterity means every block card gives more, "
            "crucial when limited to 3 plays.\n"
            "3. Accuracy -- Valuable only with shiv generators.\n"
            "4. Infinite Blades -- Free shiv each turn bypasses play limit.\n\n"
            "Once Sloth lands, powers become traps (waste 1 of 3 precious slots "
            "for future value you may not survive to use)."
        ),
    },
    52: {
        "name": "Silent archetype commitment by floor 8-10",
        "source_indices": [54, 104],
        "content": (
            "The Silent CANNOT win Act 2+ with a \"balanced\" deck that has a bit "
            "of everything. All 5 recent Silent runs that died at Floor 18 had a "
            "\"balanced\" archetype. The starter deck is weak -- it needs a focused "
            "scaling plan.\n\n"
            "**By floor 8-10, commit to ONE primary archetype:**\n"
            "1. **Poison**: Prioritize Deadly Poison, Noxious Fumes, Bouncing "
            "Flask, Crippling Cloud, Catalyst. Goal: stack poison fast, then "
            "turtle. Requires 3+ poison-applying sources before scaling cards "
            "(Catalyst, Outbreak) become effective.\n"
            "2. **Shivs**: Prioritize Blade Dance, Accuracy, Cloak and Dagger, "
            "Infinite Blades. Goal: burst damage with Accuracy bonus.\n"
            "3. **Discard**: Prioritize Survivor, Calculated Gamble, Reflex, "
            "Sneaky Strike. Goal: cycle deck fast for key cards.\n\n"
            "**Act 2 readiness check (before leaving Act 1):**\n"
            "- Must have a scaling win condition online or nearly online\n"
            "- Must have AoE or multi-target capability for Act 2 multi-enemy fights\n"
            "- Must have at least 2 block sources beyond basic Defend\n"
            "- If missing any of these, route through shops and card rewards urgently\n\n"
            "**\"Balanced\" is a trap**: taking one poison card, one shiv card, "
            "and one discard card gives you three weak half-strategies instead of "
            "one strong focused strategy."
        ),
    },
    4: {
        "name": "Deck Building Across the Run",
        "source_indices": [9, 99, 103],
        "content": (
            "Low-quality cards are worse than not having them -- they dilute your "
            "draws and waste turns. (1) Act 1 (<15 cards): ADD good cards "
            "aggressively -- your 10-card starter CANNOT beat bosses. Take anything "
            "better than Strike (6 dmg) or Defend (5 block). Prioritize AoE, card "
            "draw, energy generation. (2) Act 2 (15-25 cards): BUILD your archetype. "
            "Only take cards that support your emerging strategy. Skip off-archetype "
            "cards even if they look strong in isolation. (3) Act 3 (20+ cards): BE "
            "SELECTIVE. Only take cards that complete your win condition. Skip freely. "
            "(4) Card removal at shops is almost always the #1 purchase. Remove "
            "Strikes first, then Defends, then off-archetype cards. Budget 75-100g.\n\n"
            "**Additional rules:**\n"
            "- Avoid quest/non-combat cards (e.g. Spoils Map) in thin decks -- they "
            "are dead draws in combat. Only take in 25+ card decks with solid synergy.\n"
            "- When deck is >50% basics, adding a strong uncommon is better than "
            "skipping to 'stay thin'. The problem is card quality, not deck size.\n"
            "- Open card rewards before claiming gold when deck lacks a win condition "
            "-- a single strong uncommon is worth more than 20 gold.\n"
            "(5) Upgrade priority: cards with cost reduction (2->1, 1->0) or doubled "
            "effects first, then core Powers you play every combat."
        ),
    },
    17: {
        "name": "Card selection requires playable energy curve",
        "source_indices": [13, 27, 34, 86, 92],
        "add_tags": ["energy_curve", "dead_turns", "0-cost"],
        "content": (
            "When adding cards, ensure your deck maintains a playable energy curve "
            "with your starting energy (3 for most characters).\n\n"
            "**Rules:**\n"
            "- After EVERY card addition, verify the deck can play 2-3 cards per "
            "turn with current energy. If not, the card you just added is a mistake.\n"
            "- Cap 2-cost cards: with base 3 energy and no energy relics, more than "
            "2-3 two-cost cards creates dead turns. Drawing two 2-cost cards + any "
            "other card = only 1 playable card that turn.\n"
            "- 0-cost cards fix energy starvation: if the deck is producing dead "
            "turns, acquiring a 0-cost card (Piercing Wail, Slice) immediately "
            "eliminates the problem. Prioritize 0-cost over saving gold for removal.\n"
            "- Fix playability BEFORE investing in archetype payoffs. A Finisher "
            "that deals 30+ damage is worthless if you can't play cards 60% of turns.\n"
            "- After every card reward, mentally simulate: can I play at least 2-3 "
            "cards per turn on opening hands? If no, skip or take cheaper cards."
        ),
    },
    14: {
        "name": "Dead turn pattern = abort current strategy",
        "source_indices": [18, 93],
        "add_tags": ["dead_turns", "emergency_pivot"],
        "state_types": ["card_reward", "rest_site", "shop"],
        "content": (
            "If you experience 2+ dead turns (ending turn with no plays) in early "
            "Act 1, your current deck strategy has FAILED. This is a run-threatening "
            "emergency.\n\n"
            "**Immediate actions:**\n"
            "1. At the next card reward, IGNORE synergy and long-term plans. Take "
            "the cheapest, most immediately playable card (0-1 cost attacks or skills).\n"
            "2. Skip all card rewards that cost 2+ energy until the problem is fixed.\n"
            "3. Route toward shops/events that offer card removal.\n"
            "4. Prioritize card removal at every opportunity.\n\n"
            "**Track dead turn rate as a health metric:**\n"
            "- If dead turns occur in more than one combat by floor 10, every other "
            "strategic goal (archetype building, scaling, elite hunting) is "
            "subordinate to eliminating dead turns.\n"
            "- Adding more cards to an already unplayable deck makes the problem "
            "worse by diluting the energy curve further.\n"
            "- The pivot must happen at floor 2-3 card rewards, not floor 8."
        ),
    },
    26: {
        "name": "Early card rewards must fix immediate deck weaknesses before scaling",
        "source_indices": [35, 74],
        "add_tags": ["energy_solution", "shop_priority"],
        "content": (
            "In the first 3-5 floors, prioritize cards that solve your deck's "
            "immediate combat deficiencies (energy efficiency, damage output, card "
            "draw) over long-term scaling powers like Infinite Blades or Footwork.\n\n"
            "If your deck is producing dead turns where you pass with no playable "
            "cards, adding a 1-cost power that generates future value doesn't fix "
            "the root problem -- you need 0-cost attacks, card draw, or energy "
            "generation.\n\n"
            "**Energy solutions > scaling cards:**\n"
            "- At shops, before buying scaling cards, audit the deck's energy curve. "
            "If 3+ cards cost 2 energy with no energy relics, prioritize card "
            "removal of expensive basics over buying scaling.\n"
            "- Energy relics (Lantern, etc.) are highest priority shop purchases "
            "when dead turns are occurring. Buying Lantern at floor 21 is far too "
            "late when dead turns started at floor 3.\n"
            "- Spending 76g on Footwork while the deck trends toward unplayable "
            "hands is a losing trade -- removing a Strike for ~50g improves average "
            "hand playability more."
        ),
    },
    42: {
        "name": "Shop removal priority and deck bloat threshold",
        "source_indices": [112],
        "add_tags": ["deck_bloat", "basics_ratio"],
        "content": (
            "At shops, if your deck is still over 40% basic cards (Strikes/Defends), "
            "card removal must be the first purchase before any new cards. Each "
            "removal improves every future draw for the rest of the run, while "
            "adding another card to a bloated deck actively dilutes your key cards.\n\n"
            "**Deck bloat threshold:** When deck exceeds 18 cards with 55%+ basics, "
            "stop adding cards entirely. Skip all card rewards until you can access "
            "a shop for removal or find a card removal event. The only exception is "
            "cards that provide card draw or deck cycling, which directly address "
            "the bloat problem.\n\n"
            "Budget gold specifically for removal -- skip discount cards if it means "
            "affording removal at the next shop."
        ),
    },
    102: {
        "name": "Silent Act 1 scaling audit - must have scaling by floor 10-12",
        "source_indices": [100],
        "content": (
            "## Silent Scaling Requirement for Act 1\n\n"
            "**The Problem**: In 4 of 5 recent Silent losses, Strike was the "
            "most-played card. These decks had no scaling and died to bosses/elites "
            "with high HP.\n\n"
            "**Scaling sources for Silent** (in priority order):\n"
            "1. **Poison powers**: Noxious Fumes (best -- passive scaling every "
            "turn), Envenom\n"
            "2. **Poison cards**: Deadly Poison, Bouncing Flask, Catalyst\n"
            "3. **Shiv scaling**: Accuracy + shiv generators (Blade Dance, Cloak "
            "and Dagger)\n"
            "4. **Defensive scaling**: Footwork, After Image\n\n"
            "**Floor 10-12 checkpoint**: If your deck has NO scaling source by "
            "floor 10-12, treat the next card reward as CRITICAL. Take any scaling "
            "card even if it doesn't match your ideal archetype. A lone Noxious "
            "Fumes or single Blade Dance is better than continuing with pure "
            "Strikes.\n\n"
            "**When offered archetype-starting cards before floor 10**, take them "
            "even as 'lone seeds' -- they become the foundation for future picks. "
            "A single strong uncommon is worth more than waiting for the perfect "
            "synergy package."
        ),
    },
    21: {
        "name": "Greed curse = all cards cost +1 energy",
        "source_indices": [22],
        "add_tags": ["deck_verification"],
        "content": (
            "Greed curse increases ALL card costs by 1 energy, not just a few "
            "cards. With 3 starting energy, this makes most starter decks "
            "completely unplayable (Strikes cost 2, Defends cost 2). Before "
            "accepting any curse, calculate whether your deck remains functional.\n\n"
            "Greed specifically requires either 4+ energy or immediate curse "
            "removal access.\n\n"
            "**Verify playability immediately after acquiring any energy-affecting "
            "curse:** Check energy costs against available energy. If the deck is "
            "unplayable, your only options are: immediate shop for removal, "
            "immediate rest site for deck surgery, or restart the run. Never "
            "proceed to combat with an untested cursed deck."
        ),
    },
    23: {
        "name": "Silver Crucible event prioritization in early Act 1",
        "source_indices": [75, 85],
        "add_tags": ["upgraded_cards", "starting-deck", "combat_readiness"],
        "content": (
            "When offered Silver Crucible on floor 1, take the 3 upgraded card "
            "rewards option. Three upgraded cards significantly improve deck quality "
            "through Act 1, providing better damage, block, or utility than starter "
            "cards.\n\n"
            "**Why upgraded cards win:** Upgraded cards improve damage output, "
            "block efficiency, and energy curves immediately, making Act 1 combats "
            "and elites significantly more manageable. The power spike from three "
            "quality upgraded cards carries through multiple encounters and "
            "compensates for one missed chest reward.\n\n"
            "**Immediate combat readiness value:** The upgraded card rewards arrive "
            "gradually, but they directly improve your next 2-3 fights. The empty "
            "chest downside is minimal compared to the cumulative power spike."
        ),
    },
    110: {
        "name": "Act 1 HP conservation before boss",
        "source_indices": [89, 115],
        "state_types": ["event"],
        "content": (
            "**In Act 1, conserve HP aggressively in the floors before the boss "
            "fight (typically floors 6-8).**\n\n"
            "**Rules:**\n"
            "1. NEVER accept event options that cost more than 20% of your max HP "
            "when the boss fight is within 2-3 floors.\n"
            "2. If an event option costs HP AND you don't have a rest site between "
            "now and the boss, strongly prefer the safe/free option.\n"
            "3. Calculate: \"After this HP cost, will I have enough HP to survive "
            "the boss?\"\n\n"
            "**HP thresholds for event decisions:**\n"
            "- Below 30% HP: NEVER take event options that cost HP unless the reward "
            "is game-winning. Leave/skip is almost always correct.\n"
            "- Below 40% HP: Only take HP-costing options if the reward is exceptional "
            "(free relic, curse removal). NEVER take HP-costing options when the boss "
            "is the next fight.\n"
            "- Check event costs carefully when HP < 40% -- a 43 HP treasure cost "
            "can end a run if boss is 2 floors away."
        ),
    },
    113: {
        "name": "Minimum deck size for forced discard events",
        "source_indices": [111],
        "content": (
            "Avoid events that force you to discard multiple cards if your deck is "
            "at or below 10 cards total. Small decks become unplayable when forced "
            "to remove cards, especially if you must discard key damage or block "
            "cards.\n\n"
            "If you encounter such an event with a small deck, choose the "
            "alternative option even if it seems worse (take damage, lose gold, etc.) "
            "rather than risk making your deck unplayable.\n\n"
            "**After any forced discard:** Immediately verify your remaining deck "
            "can still function in combat. Check that you have enough attacks to "
            "kill enemies and enough skills to survive. If the forced discard left "
            "you with an unplayable deck, path to a shop or card reward to restore "
            "combat capability before taking any fights."
        ),
    },
    96: {
        "name": "Heal before boss - HP threshold",
        "source_indices": [11],
        "state_types": ["rest_site"],
        "content": (
            "At rest sites in the last 2 floors before a boss fight:\n\n"
            "**Always HEAL if HP is below 50% of max HP.** No upgrade is worth "
            "entering a boss fight at low HP.\n\n"
            "Boss fights typically last 10-12 rounds. Even with good block, you "
            "WILL take chip damage. A boss dealing 20+ on a turn where you don't "
            "draw block is common.\n\n"
            "**Specific thresholds:**\n"
            "- HP < 40%: MUST heal. No exceptions.\n"
            "- HP 40-50%: Heal unless the upgrade is game-changing (Footwork+, "
            "Noxious Fumes+).\n"
            "- HP > 50%: Smith (upgrade) is usually better.\n\n"
            "**Act 3 specifics:** HP management is even more critical in Act 3. "
            "If HP <= 40% of max HP at a rest site in Act 3, ALWAYS heal -- no "
            "upgrade is worth dying to the next fight. Healing 30% of max HP is "
            "the difference between surviving a big hit and dying."
        ),
    },
    15: {
        "name": "Floor 1 elite avoidance without combat-ready deck",
        "source_indices": [16, 98],
        "add_tags": ["silent_elite_gate"],
        "content": (
            "Never path to an elite fight on floors 1-3 with an unmodified starting "
            "deck. You need at least one combat win to add damage cards or remove "
            "strikes/defends before facing elites. Elite fights require 2-3x the "
            "damage output of normal hallway fights.\n\n"
            "**Ensure first combat path exists:** On floor 1, always ensure your "
            "chosen path includes at least one normal combat before any elite, "
            "event, or shop. Normal combats are the only guaranteed way to add "
            "cards early.\n\n"
            "**Silent elite readiness gate (Act 1):**\n"
            "- HP Gate: Need at least 50% HP to fight Act 1 elites. At 50-55% you "
            "are on the edge -- only acceptable with a strong deck.\n"
            "- Deck Power Gate: Act 1 elites like Terror Eel have 140 HP with "
            "scaling damage. Can your deck deal 140 damage in 6-7 turns (~20+ "
            "damage/turn)?\n"
            "- Scaling Gate: If your only damage source is basic Strikes, skip the "
            "elite. Strikes deal ~18 damage/turn with 3 energy, needing 8+ turns "
            "while taking escalating damage.\n"
            "- Silent specifically needs 50% HP + a scaling source to consider "
            "Act 1 elites."
        ),
    },
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _merge_stats(keeper: dict, sources: list[dict]) -> None:
    """Update keeper with highest confidence/usage/success from merged sources."""
    all_skills = [keeper] + sources
    keeper["confidence"] = max(s["confidence"] for s in all_skills)
    keeper["usage_count"] = max(s["usage_count"] for s in all_skills)
    keeper["success_count"] = max(s["success_count"] for s in all_skills)


def _merge_trigger(keeper: dict, sources: list[dict], spec: dict) -> None:
    """Merge trigger fields from sources into keeper."""
    trigger = keeper["trigger"]

    # Merge enemy_names (union)
    all_enemy_names: set[str] = set(trigger.get("enemy_names", []))
    for s in sources:
        all_enemy_names.update(s["trigger"].get("enemy_names", []))
    all_enemy_names.update(spec.get("add_enemy_names", []))
    trigger["enemy_names"] = sorted(all_enemy_names)

    # Merge tags (union)
    all_tags: set[str] = set(trigger.get("tags", []))
    for s in sources:
        all_tags.update(s["trigger"].get("tags", []))
    all_tags.update(spec.get("add_tags", []))
    trigger["tags"] = sorted(all_tags)

    # Override state_types if specified
    if "state_types" in spec:
        trigger["state_types"] = spec["state_types"]


def apply_dedup(skills: list[dict], dry_run: bool = False) -> list[dict]:
    """Apply deduplication: merge content into keepers, then delete extras."""
    assert len(skills) == 116, f"Expected 116 skills, got {len(skills)}"

    # Phase 1: Apply merges to keeper skills (in-place on copies)
    merged_keepers: dict[int, dict] = {}
    for keeper_idx, spec in MERGE_SPECS.items():
        keeper = json.loads(json.dumps(skills[keeper_idx]))  # deep copy
        source_indices = spec.get("source_indices", [])
        source_skills = [skills[i] for i in source_indices]

        # Update name if specified
        if "name" in spec:
            keeper["name"] = spec["name"]

        # Update content
        keeper["content"] = spec["content"]

        # Merge stats
        _merge_stats(keeper, source_skills)

        # Merge trigger fields
        _merge_trigger(keeper, source_skills, spec)

        # Bump version
        keeper["version"] = keeper.get("version", 1) + 1

        merged_keepers[keeper_idx] = keeper

    # Phase 2: Build final list (skip deleted indices, use merged keepers)
    result = []
    deleted_count = 0
    merged_count = 0
    kept_count = 0

    for i, skill in enumerate(skills):
        if i in DELETE_INDICES:
            deleted_count += 1
            continue
        if i in merged_keepers:
            result.append(merged_keepers[i])
            merged_count += 1
        else:
            result.append(skill)
            kept_count += 1

    return result, {
        "original": len(skills),
        "deleted": deleted_count,
        "merged": merged_count,
        "kept_unchanged": kept_count,
        "final": len(result),
    }


def print_report(
    skills: list[dict],
    result: list[dict],
    stats: dict,
    dry_run: bool,
) -> None:
    """Print a summary of the deduplication operation."""
    mode = "DRY RUN" if dry_run else "APPLIED"
    print(f"\n{'='*60}")
    print(f"  Skills Deduplication Report ({mode})")
    print(f"{'='*60}")
    print(f"  Original skills:    {stats['original']}")
    print(f"  Deleted:            {stats['deleted']}")
    print(f"  Merged (updated):   {stats['merged']}")
    print(f"  Kept unchanged:     {stats['kept_unchanged']}")
    print(f"  Final skills:       {stats['final']}")
    print(f"{'='*60}")

    # Show merge details
    print(f"\n  Merge operations ({stats['merged']} keepers updated):")
    print(f"  {'-'*56}")
    for keeper_idx in sorted(MERGE_SPECS.keys()):
        spec = MERGE_SPECS[keeper_idx]
        old_name = skills[keeper_idx]["name"]
        new_name = spec.get("name", old_name)
        absorbed = len(spec.get("source_indices", []))
        name_changed = " (renamed)" if old_name != new_name else ""
        print(f"    [{keeper_idx:3d}] {new_name[:55]}{name_changed}")
        print(f"           absorbed {absorbed} skills, "
              f"content: {len(spec['content'])} chars")

    # Show deleted indices
    print(f"\n  Deleted indices ({stats['deleted']}):")
    deleted_sorted = sorted(DELETE_INDICES)
    for i in range(0, len(deleted_sorted), 10):
        chunk = deleted_sorted[i:i+10]
        print(f"    {', '.join(str(x) for x in chunk)}")

    if not dry_run:
        print(f"\n  Written to: {SKILLS_PATH}")
    else:
        print("\n  No changes written (--dry-run mode)")
    print()


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply skill deduplication")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print report without writing changes",
    )
    args = parser.parse_args()

    # Read
    if not SKILLS_PATH.exists():
        print(f"ERROR: {SKILLS_PATH} not found", file=sys.stderr)
        sys.exit(1)

    with open(SKILLS_PATH, "r", encoding="utf-8") as f:
        skills = json.load(f)

    print(f"Read {len(skills)} skills from {SKILLS_PATH}")

    # Validate
    if len(skills) != 116:
        print(
            f"ERROR: Expected 116 skills, got {len(skills)}. "
            "This script is designed for the current 116-skill file.",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate delete indices don't overlap with keeper indices
    keeper_indices = set(MERGE_SPECS.keys())
    overlap = DELETE_INDICES & keeper_indices
    if overlap:
        print(
            f"ERROR: Indices {overlap} appear in both DELETE and MERGE lists",
            file=sys.stderr,
        )
        sys.exit(1)

    # Validate all source indices are in the delete list
    for keeper_idx, spec in MERGE_SPECS.items():
        for src_idx in spec.get("source_indices", []):
            if src_idx not in DELETE_INDICES:
                print(
                    f"WARNING: Source index {src_idx} (merged into [{keeper_idx}]) "
                    f"is NOT in the delete list -- it will remain as a separate skill",
                    file=sys.stderr,
                )

    # Apply
    result, stats = apply_dedup(skills, dry_run=args.dry_run)

    # Report
    print_report(skills, result, stats, dry_run=args.dry_run)

    # Write
    if not args.dry_run:
        with open(SKILLS_PATH, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"Successfully wrote {len(result)} skills to {SKILLS_PATH}")


if __name__ == "__main__":
    main()
