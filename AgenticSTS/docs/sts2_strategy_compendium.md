# Slay the Spire 2 — Comprehensive Strategy Compendium

> Compiled from extensive web research (March 2026). All information is specific to
> Slay the Spire 2 (Early Access, released March 5, 2026). This document is intended
> as a knowledge base for the STS2 autonomous agent.

---

## Table of Contents

1. [Combat Fundamentals](#1-combat-fundamentals)
2. [Card Evaluation Framework](#2-card-evaluation-framework)
3. [Character Guides & Deck Archetypes](#3-character-guides--deck-archetypes)
4. [Boss Guide (All Acts)](#4-boss-guide-all-acts)
5. [Elite Enemy Guide](#5-elite-enemy-guide)
6. [STS2-Specific Mechanics](#6-sts2-specific-mechanics)
7. [Potion Strategy](#7-potion-strategy)
8. [Shop & Gold Management](#8-shop--gold-management)
9. [Map Routing & Path Planning](#9-map-routing--path-planning)
10. [Card Tier Lists by Character](#10-card-tier-lists-by-character)
11. [Potion Tier List](#11-potion-tier-list)
12. [Sources](#12-sources)

---

## 1. Combat Fundamentals

### 1.1 Energy System

- Players gain **3 Energy per turn** by default.
- Each card has an Energy cost (0-4+). You can play any number of cards as long as you have enough Energy.
- **Unused Energy is lost** at end of turn (unless specific relics/cards preserve it).
- Zero-cost cards (Offering, Prepared, Claw) are extremely valuable because they provide value without consuming Energy.
- Card draw and Energy have a "yin-yang relationship": excess draw without Energy is pointless; abundant Energy without cards is wasted.

### 1.2 Card Draw

- Players draw **5 cards per turn** by default.
- Card draw is one of the most powerful effects in the game. Powers and relics that increase draw are generally the strongest available.
- The faster you cycle through your deck, the more often you see your best cards.
- **Ring of the Snake** (Silent's starting relic) draws 2 extra cards at combat start, emphasizing draw's importance.

### 1.3 Block Mechanics

- Block absorbs incoming damage before HP is reduced.
- **Block resets at the start of your next turn** (exceptions: Barricade, Plating, certain relics).
- **Plating** provides a set amount of Block at end of turn automatically; reduced by 1 at start of turn.
- Effective blocking requires timing: stack Block on the turn enemies attack, not on turns they buff.

### 1.4 Damage Calculation

Damage resolution sequence:
1. Attack card is played
2. Modifiers apply (Strength, Vulnerable, Weak, Focus)
3. Block absorbs damage first
4. Remaining damage reduces enemy HP

Key modifiers:
- **Strength**: Adds flat damage to each attack hit (+X per hit for multi-hit cards)
- **Dexterity**: Adds flat Block to each block-gaining card
- **Vulnerable**: Target takes **50% more damage** from Attacks
- **Weak**: Attacker deals **25% less damage** with Attacks
- **Focus**: Increases effectiveness of all Orb passive and evoke effects (Defect)

### 1.5 Turn Sequencing Strategy

**General priority order each turn:**

1. **Read enemy intents** - Determine if enemies are attacking, buffing, or debuffing
2. **If enemies attack**: Prioritize Block first, then spend remaining Energy on Attacks
3. **If enemies buff/debuff**: This is your damage window - attack with everything
4. **Play Powers early** - Powers provide lasting benefits; play them on safe turns
5. **Play draw cards before attack cards** - Draw first to see your full options
6. **Apply debuffs before dealing damage** - Vulnerable before big attacks
7. **Use Strength buffs before multi-hit attacks** - Strength applies per hit

**Key sequencing rules:**
- It is acceptable to spend an entire turn blocking and deal zero damage
- Enemies that buff themselves are giving you a free damage turn
- Save your strongest block cards and potions for predicted high-damage turns

### 1.6 Enemy Intents

- Enemies display their intended action above their heads each turn
- Intent types: Attack (sword icon with damage number), Defend (shield icon), Buff (upward arrow), Debuff (downward arrow), Unknown (question mark)
- **Multi-hit intents** show as "Nx" (e.g., "6x3" means 6 damage, 3 times)
- Learning enemy patterns allows you to predict danger 2-3 turns in advance
- Boss patterns repeat in fixed cycles - learn the cycle to know when to block vs attack

### 1.7 Multi-Enemy Combat

- **Evaluate which enemy is the biggest threat** and prioritize killing it first
- Use AoE (area-of-effect) attacks when facing multiple enemies to manage the group
- Sometimes eliminating one enemy quickly reduces total incoming damage more than AoE
- **Character-specific AoE tools**:
  - Ironclad: Whirlwind (scales with Energy and Strength)
  - Silent: Corpse Explosion, Crippling Cloud, Piercing Wail (debuff all)
  - Regent: Stars archetype has many AoE options
  - Defect: Electrodynamics (Lightning hits all enemies), Tesla Coil
  - Necrobinder: Negative Pulse, Deathbringer

### 1.8 Lethal Calculation

Before ending your turn, always check:
1. Can you kill an enemy this turn? (Reduces incoming damage next turn)
2. Will the enemy kill you next turn? (Do you have enough Block?)
3. Is the enemy applying a dangerous buff that must be prevented?

**Priority**: Killing an enemy > Blocking if the enemy would deal more total damage over remaining turns than you'd take this turn.

### 1.9 Scaling and Win Conditions

- Enemies strengthen over time (typically gaining Strength every 3-4 turns)
- Your deck must have a **scaling mechanism** to keep up:
  - Strength stacking (Demon Form)
  - Poison/Doom accumulation
  - Focus + Orbs (Defect)
  - Block accumulation (Barricade builds)
  - Powers like Genesis, Defragment
  - Scaling cards: Kingly Punch, Rampage
- Without scaling, fights drag on and enemies eventually overwhelm you

---

## 2. Card Evaluation Framework

### 2.1 When to Add a Card

Ask these questions before accepting a card reward:
1. Does this card solve an immediate problem in my deck? (No AoE, no card draw, no block, etc.)
2. Does this card synergize with cards I already have?
3. Does this card function independently, without requiring another specific card?
4. Will this card still be good in Act 3?

**If the answer to all is "no", SKIP the card reward.**

### 2.2 When to Skip Card Rewards

- **Skip freely** - A lean deck beats a bloated one every time
- Skip if the card only works in a "dream draw" scenario
- Skip if the card only helps against one specific enemy
- Skip if the card needs support cards you don't have yet
- **Ideal deck size**: 20-25 cards by end of Act 3

### 2.3 What Makes a Card "Good"

**Early game (Act 1)**:
- Front-loaded damage (cards that deal immediate damage without setup)
- Basic AoE for multi-enemy fights
- Cards that remove Strikes/Defends from your deck (via Exhaust)
- Cards that function without synergy

**Mid game (Act 2)**:
- Scaling cards (Strength, Poison, Focus)
- Cards that support your emerging archetype
- Draw/energy generation
- Defensive cards that scale (Footwork, Metallicize)

**Late game (Act 3 / Boss prep)**:
- Cards that complete your win condition
- Answers to specific boss mechanics
- Cards that don't dilute your deck's consistency

### 2.4 Card Synergy Concepts

- **Archetype focus**: Most successful decks focus on one mechanic (Poison, Strength, Exhaust, Orbs, Stars, Doom)
- **Hybrid flexibility**: Maintain a primary win condition with backup options
- **Draw + Energy balance**: Extra draw needs extra Energy; extra Energy needs extra draw
- **Relic awareness**: Check acquired relics before card selection. A relic can make a mediocre card excellent:
  - Ruined Helmet transforms Inflame from +2 to +4 Strength
  - Shuriken/Kunai/Ornamental Fan reward zero-cost card spam
  - Data Disk gives Focus for Defect

### 2.5 Card Removal Priority

**Remove in this order:**
1. **Curses** - Always remove curses first
2. **Basic Strikes** - Almost always worse than any acquired Attack card
3. **Basic Defends** - Once you have better defensive options
4. **Cards that don't fit your archetype** - Early picks that no longer serve your strategy

### 2.6 Upgrade Priority

When upgrading at Rest Sites or events:
1. **Core win condition cards** (e.g., Demon Form, Defragment, Catalyst)
2. **Draw/Energy cards** (e.g., Adrenaline, Offering)
3. **Defense cards** (e.g., Barricade, Footwork)
4. Cards you play every combat > cards you play sometimes

---

## 3. Character Guides & Deck Archetypes

### 3.1 Characters in STS2

| Character | Starting Relic | HP | Playstyle |
|-----------|---------------|-----|-----------|
| Ironclad | Burning Blood (heal 6 HP after combat) | High | Aggressive, Strength scaling |
| Silent | Ring of the Snake (draw 2 extra at combat start) | Medium | Card draw, Poison, Shivs, Sly discard |
| Defect | Cracked Core (Channel 1 Lightning at combat start) | Medium | Orb management, Focus scaling |
| Regent | Divine Right (gain 3 Stars at combat start) | Medium | Stars resource, Forge/Sovereign Blade |
| Necrobinder | Bound Phylactery (Summon 1 at start of turn) | Low | Osty companion, Doom, Souls |

**Note**: The Watcher from STS1 is NOT in STS2. The two new characters are Regent and Necrobinder.

### 3.2 Ironclad

**Starting Relic**: Burning Blood - heals 6 HP after every combat. Most forgiving for beginners.

#### Archetype 1: Vulnerable Build
Exploits the Vulnerable debuff (50% more damage). Ironclad gains unique bonuses from Vulnerable that other characters cannot access.
- **Key cards**: Molten Fist, Tremble, Taunt, Dismantle, Uppercut, Bash (upgraded)
- **Scaling**: Dominate (for long fights), Cruelty, Colossus
- **Warning**: Don't become too aggressive - maintain adequate Block coverage

#### Archetype 2: Body Slam Build
Accumulate massive Block, then convert it to damage via Body Slam.
- **Core Block cards**: Shrug It Off (block + draw), Blood Wall, Flame Barrier
- **Scaling**: Unmovable (enhances Defend cards), Crimson Mantle, Impervious
- **Win condition**: Body Slam deals damage equal to current Block
- **Strength**: Exceptional survivability

#### Archetype 3: Exhaust Build
Remove cards from deck during combat to thin out weak cards and enable combos. Highest skill ceiling.
- **Early Exhaust**: True Grit, Burning Pact, Evil Eye (16 block), Forgotten Ritual (3 Energy)
- **Engine**: Corruption (Skills cost 0 but Exhaust), Dark Embrace (draw on Exhaust), Feel No Pain (Block on Exhaust)
- **Finishers**: Ashen Strike (scales with Exhaust pile), Fiend Fire, Pact's End
- **Support**: Second Wind (removes status cards), Juggernaut (damage on Exhaust)

**General Ironclad Tips**:
- The three archetypes can and should be blended together
- Ironclad doesn't need big finisher cards to win runs
- Burning Blood makes early-game aggression safe

### 3.3 Silent

**Starting Relic**: Ring of the Snake - draw 2 extra cards at start of combat. Core identity = card draw.

#### Archetype 1: Sly Build (Strongest)
The Sly keyword plays cards for free when discarded from hand. "The most powerful keyword in STS2."
- **Discard tools**: Acrobatics, Dagger Throw, Prepared, Calculated Gamble
- **Sly payoffs**: Ricochet, Flick-Flack, Untouchable, Abrasive, Hand Trick, Reflex, Tactician
- **Strategy**: Build discard tools first, then add high-cost Sly cards

#### Archetype 2: Poison Build
Poison depletes enemy HP over multiple turns. Scales exponentially with doublers.
- **Stacking**: Poisoned Stab, Bouncing Flask, Noxious Fumes (passive per turn), Deadly Poison
- **Multiplier**: Catalyst (doubles all Poison on target), Accelerant
- **Support**: Envenom, Corrosive Wave, Mirage
- **Warning**: Don't fill deck with Poison cards in Act 1 - prioritize survivability with Dash, Backflip, Footwork

#### Archetype 3: Shiv Build
Zero-cost Shiv attacks for chip damage, amplified by Accuracy.
- **Generators**: Blade Dance (multiple Shivs), Cloak and Dagger, Infinite Blades (Shiv per turn)
- **Amplifier**: Accuracy (increases all Shiv damage), stacks multiplicatively
- **Defense**: After Image (Block per card played - amazing with Shiv spam)
- **Finisher**: Finisher (damage per card played this turn)

**General Silent Tips**:
- S-tier universal cards: Acrobatics, Piercing Wail, Well-Laid Plans, Adrenaline, Tools of the Trade, Wraith Form
- Silent struggles with Block - invest in Dexterity (Footwork)
- Sly naturally combines with both Poison and Shiv builds
- Discard strategies remain functional even with larger decks

### 3.4 Defect

**Starting Relic**: Cracked Core - Channel 1 Lightning Orb at combat start.

#### Orb System
- Start with 3 empty orb slots
- **Channel**: Places orb in first empty slot (left to right)
- **Evoke**: When slots are full, channeling a new orb pushes out the rightmost orb, triggering its Evoke effect
- Each orb has a **passive effect** (end of turn) and a **burst Evoke effect**

#### Orb Types
| Orb | Passive | Evoke |
|-----|---------|-------|
| Lightning | Zap random enemy (3+Focus damage) | Heavy damage to random enemy (8+Focus) |
| Frost | Gain Block (2+Focus) | Large Block gain (5+Focus) |
| Dark | Increase stored damage each turn (+6+Focus) | Nuke lowest HP enemy (stored damage) |
| Plasma | Gain 1 Energy | Gain 2 Energy |
| Glass | Damage all enemies (decreases per turn) | Damage all enemies |

#### Focus is Critical
- Focus directly increases both passive and evoke values of ALL orbs
- **Defragment** is the single most important card - take as many as possible
- Without Focus cards, orbs hit like "wet noodles" by Act 3

#### Archetype 1: Orb Build (Most Reliable)
Frost for defense, Lightning for damage, Focus for scaling.
- **Early cards**: Ball Lightning, Cold Snap, Coolheaded (best Common), Barrage, Compile Driver
- **Focus**: Defragment (take every copy), Modded, Biased Cognition (+4 Focus burst)
- **Scaling**: Loop, Capacitor (more slots), Thunder, Hailstorm
- **Finishers**: Multi-Cast, Voltaic, Shatter (evoke all orbs at once)
- **Key synergy**: Synchronize rewards diverse orb types

#### Archetype 2: Claw Deck
Spam zero-cost attacks. Fun and viable.
- **Core**: Claw (grows stronger each play), Momentum Strike, FTL, Flash of Steel
- **Draw engine**: Scrape (key cycling tool), Skim, Hologram (recycle Claw)
- **Payoffs**: All for One (return zero-cost cards to hand), Feral (Echo for 0-cost), Panache
- **Warning**: Don't take every 0-cost card - bloating makes Claw harder to find
- **Hybrid tip**: Stack some Frost orbs for passive Block even in Claw builds

### 3.5 Regent

**Starting Relic**: Divine Right - gain 3 Stars at combat start.

#### Stars Mechanic
- Stars are a secondary resource (separate from Energy)
- Stars do NOT reset at end of turn
- No cap on Stars held
- Generated through specific cards; spent to play powerful Star-cost cards

#### Archetype 1: Sovereign Blade / Forge Build
The Sovereign Blade is a retained attack card that grows stronger through Forge.
- **Forge**: First use adds Sovereign Blade to hand; subsequent Forges increase its damage
- **Early cards**: Cosmic Indifference (return blade), Wrought in War (damage + Forge)
- **Scaling**: Beat into Shape (Forge generation), Conqueror (doubling), Furnace (passive Forge)
- **Multi-enemy answer**: Seeking Edge (permanent solution)
- **Key relic**: Fencing Manual (improves blade playability turn 1)
- **Weakness**: Limited AoE options - supplement with Star generators for Falling Star/Gamma Blast

#### Archetype 2: Stars Build
Establish a Star engine to play powerful cards at minimal Energy.
- **Generators**: Gather Light (Block + Stars), Hidden Cache (high Star output), Solar Strike, Shining Strike, Genesis (solves Star generation alone)
- **Payoffs**: Alignment (Stars to Energy), Cloak of Stars (0-cost Block), Dying Star (AoE Block scaling)
- **Utility**: Glow (draw), Convergence (full-hand Retain + self-refund), Reflect (Block + damage counter)
- **Scaling**: The Smith (independent win condition), Gamma Blast (Vulnerable)
- **Key relics**: Lunar Pastry (passive Stars), Mini Regent (Strength from Star spending)

**General Regent Tips**:
- **Pick a lane**: Don't mix Stars and Forge heavily - results in bloated, inconsistent deck
- Don't commit too early; maintain flexible generic options
- Prevent deck clogging by limiting pure Star generators
- Include moderate Star generation even in Forge builds for Vulnerability application

### 3.6 Necrobinder

**Starting Relic**: Bound Phylactery - Summon 1 at start of turn (summons/heals Osty).

#### Core Mechanics
- **Osty**: Skeletal companion that absorbs damage. Osty's HP stacks permanently within combat (doesn't reset like Block).
- **Doom**: Death-mark mechanic. If Doom >= enemy HP at end of enemy's turn, enemy dies. Delayed but high value.
- **Souls**: Zero-cost skill cards that draw 2 and Exhaust. Generated by various cards.

#### Archetype 1: Osty/Summon Build (Most Practical)
Uses Osty as primary defense while dealing damage through Osty attacks.
- **Summon cards**: Pull Aggro (11 effective Block), Reanimate (burst Summon)
- **Osty attacks**: Snap (cheap, Retain), Rattle (multi-attack + combo), Fetch (0-cost, cycles), Sic 'Em (scales with Summon)
- **Scaling**: Flatten (scales with Osty attack count), Necro Mastery (defense to AoE)
- **Healing**: Spur (healing contingent on Osty alive)
- **Key relic**: Bone Flute (consistent Block)

#### Archetype 2: Doom Build
Applies Doom to execute enemies regardless of remaining HP.
- **Stacking**: Blight Strike, Defile, Scourge (13 damage + draw), Negative Pulse (AoE Doom)
- **Scaling**: Deathbringer (AoE Doom + Weak), No Escape (single-target acceleration), Time's Up (finisher)
- **Defense**: Death's Door (Block from Doom cards), Delay (Block + Energy refund), Shroud (Doom to Block)
- **Finisher**: End of Days (solves the waiting problem), Oblivion
- **Important**: Include Souls for draw to find Doom cards faster
- **Key relics**: Book Repair Knife (healing), Undying Sigil (Weak on final turn)

#### Archetype 3: Soul/Exhaust Cycling Build
Thin deck to 5-10 cards for pseudo-infinite loops.
- **Key cards**: Haunt (6 HP loss per Soul played), Dark Pact (Exhaust to draw), Soul Siphon (Energy while cycling)
- **Goal**: Draft two Haunts + small curated deck = chain zero-cost Souls while enemies melt

**General Necrobinder Tips**:
- Necrobinder has lowest HP - Osty is essential for survival
- Pure Doom builds need reliable Block plans for delayed execution turns
- Splash a small Soul package for draw in any archetype
- Consider Seance (card removal) and Dredge (replay important cards) for consistency

---

## 4. Boss Guide (All Acts)

### 4.1 Act 1a: Overgrowth Bosses

#### Vantom (Hard)
- **Cycle**: Strict 4-turn pattern centered on Slippery debuff
- **Turn 1**: ~9 damage + Slippery (limits attacks to max 1 damage per hit for 9 instances)
- **Turn 2**: Tail growth with damage scaling
- **Turn 3**: 25+ damage slam (**kill turn** - save best Block + potions)
- **Turn 4**: Self-buff (your damage window), cycle resets
- **Strategy**: Chip damage turns 1-2 while clearing Slippery with weak attacks. Turn 3 = full defense. Turn 4 = full offense. Lucky Tonic can skip bad turns.

#### Ceremonial Beast (Medium)
- **Mechanics**: Stun trigger below 150 HP; Ringing (restricts to 1 card per turn); gains +2 permanent Strength per cycle
- **Turn 1**: Plow (self-buff for stun)
- **Turn 2**: 18 damage + 2 Strength
- **Turn 3-5**: Ringing or damage cycle
- **Strategy**: Control stun timing by managing damage around 150 HP threshold. Burst during Ringing when boss weakens. Don't let fight drag - Strength stacking becomes unmanageable.

#### Kin Priest (Medium)
- **Mechanics**: Ritual-based, rewards aggressive play
- **Strategy**: Front-load damage. Use potions early. Buff removal helps if available.

### 4.2 Act 1b: Underdocks Bosses

#### Soul Fysh (Medium)
- **Mechanics**: Beckon status cards (1 Energy, 6 unblockable damage if unexhausted); Intangible phases
- **Turn 1**: Beckon cards placed in discard/draw
- **Turn 2**: 15+ damage (damage window)
- **Turn 3**: <10 damage + status (best damage window)
- **Turn 4**: Gains Intangible (all damage reduced to 1 - don't waste attacks)
- **Turn 5**: Intangible continues, 10+ damage + 3 Vulnerable
- **Strategy**: Exhaust Beckon via Acrobatics/Burning Pact. Damage on turns 2-3. Don't attack turns 4-5.

#### Lagavulin Matriarch (Medium)
- **Mechanics**: Sleeping phase, then wakes and applies debuffs
- **Strategy**: Use sleeping turns for Powers and scaling. Rush aggressively once awake - extended fights worsen from debuffs. Consider early wake-up if your build is slow.

### 4.3 Act 2: Hive Bosses

#### Knowledge Demon (Very Hard)
- **HP**: 380+. Forces debuff choices every cycle. Heals. Gains +2 permanent Strength per cycle.
- **Turn 1**: Demonic Choice (Disintegration: 6 damage/turn OR Mind Rot: draw 1 less card)
- **Turn 2**: Blast (16-18 damage)
- **Turn 3**: Barrage (3x ~8 = ~24 total damage)
- **Turn 4**: Rejuvenating Runes (~11 damage, boss heals, +2 Strength)
- **Later choices**: Sloth (max 3 cards/turn) or Sap (reduced max Energy) - much more punishing
- **Strategy**: Aggressive play mandatory - passive decks lose to healing + Strength. Take Disintegration if you can kill fast. Use multi-hit attacks against you (Barrage) with Thorns/Flame Barrier for counter-damage.

#### The Insatiable (Very Hard)
- **Mechanics**: Sandpit timer starts at 4, decrements each turn. Timer = 0 means instant death.
- **DPS Race**: Must kill in 4-5 turns
- **Frantic Escape cards**: Extend timer by 1 when played. ALWAYS play them - timer extension > card conservation
- **Strategy**: Heavy single-turn damage (Hellraiser, burst combos). Don't exhaust randomly (preserve Frantic Escapes). Decks lacking 4-5 turn burst typically fail here.

#### Kaiser Crab (Hard)
- **Mechanics**: Two separate claws - Crusher (199 HP, tankier, buffs defense) and Rocket (189 HP, meaner attacks)
- **Strategy**: Focus Rocket first (higher threat). AoE hits both claws. Poison works wonders against high HP. Armor-piercing and Block-bypassing effects (Poison, Doom) are essential. Burst before armor walls develop.

### 4.4 Act 3: Glory Bosses

#### Doormaker (Very Hard)
- **Two-phase loop**: Phase 1 (The Door: 155 HP) -> Phase 2 (Doormaker: stunned then attacks 30+, gains 3 Strength, flees) -> Door respawns at full HP with accumulated Strength
- **Key mechanics**:
  - When Door dies, all debuffs vanish - must reapply to each new Door
  - **Retaliation**: Every 4th attack card in a single turn triggers 15 free damage from Doormaker. Keep attacks to 3 per turn.
  - Poison carries over between phases (good for Silent/Regent)
- **Strategy**: Steer card picks toward high-damage single-turn combinations. Use stun turn in Phase 2 for peak damage. Kill door in 2-3 turns to prevent Strength accumulation. Use potions aggressively per cycle. Block-heavy cards (Reflect) survive 30+ damage turns.

#### Test Subject C10 (Very Hard)
- **Three phases with escalating HP**:
  - Phase 1 (100 HP): Gains 2 Strength per Skill played. **Use Attacks only, avoid Skills.**
  - Phase 2 (200 HP): Inserts Wound cards on unblocked damage. **Maintain full Block coverage.**
  - Phase 3 (300 HP): Intangible every other turn. **Damage only on non-Intangible turns.**
- **Critical**: DoT (Poison/Doom) resets between phases - avoid these builds here
- **Strategy**: Scaling powers (Demon Form) outperform burst. Phase 1 = attacks only. Phase 2 = consistent blocking. Phase 3 = passive defense (Frost Orbs, armor retention).

### 4.5 The Architect (Post-Act 3)
- Scripted story event, not actual combat
- Outcome predetermined regardless of deck/HP
- No preparation necessary

### 4.6 Universal Boss Principles

- Learn repeating turn cycles to predict danger 2-3 turns ahead
- Deploy potions on boss fights (highest-stakes encounters)
- Construct decks addressing specific act boss demands
- Don't waste Block on setup/buff turns - use those for Powers, debuffs, or damage
- Check which boss you'll face BEFORE planning your route

---

## 5. Elite Enemy Guide

### 5.1 Act 1 (Overgrowth) Elites

| Elite | Key Mechanic | Strategy |
|-------|-------------|----------|
| Bygone Effigy | Sleeps Turn 1; takes increasing damage per card played | Set up Powers while sleeping; spam many cards per turn for bonus damage |
| Byrdonis | Gains Strength each turn | Kill quickly before Strength snowballs |
| Phrog Parasite | Summons enemies after death; applies status cards | Prepare for multi-phase fight; manage status cards |

### 5.2 Act 1 (Underdocks) Elites

| Elite | Key Mechanic | Strategy |
|-------|-------------|----------|
| Phantasmal Gardener | Gains Block on first damage each turn | Use one big attack per turn, not many small ones |
| Skulking Colony | Hardened Shell (limits damage per turn); status cards | Sustained damage over many turns; manage status |
| Terror Eel | High damage; Stunned when HP drops below threshold | Burst to trigger stun, then deal damage during stun |

### 5.3 Act 2 (Hive) Elites

| Elite | Key Mechanic | Strategy |
|-------|-------------|----------|
| Decimillipede | Segment-based revival | Kill segments efficiently |
| Entomancer | Deck pollution (Dazed cards) | Exhaust/remove Dazed cards |
| Infested Prism | Energy-granting abilities | Manage the trade-off |

### 5.4 Act 3 (Glory) Elites

| Elite | Key Mechanic | Strategy |
|-------|-------------|----------|
| Knight Trio | Three-enemy encounter | AoE priority; focus highest threat |
| Mecha Knight | Heavily armored | Block-bypassing damage (Poison, Doom) |
| Soul Nexus | Debuff application | Artifact or debuff removal |

### 5.5 General Elite Strategy

- Target 1-2 elites per Act for relic rewards
- Place Rest Sites before Elite encounters when possible
- Elites drop relics - relics are the primary way to scale passive power
- Early relics dramatically increase win chances
- Act 2 elites are significantly harder than Act 1

---

## 6. STS2-Specific Mechanics

### 6.1 New Keywords

| Keyword | Effect |
|---------|--------|
| **Sly** | Card plays for free when discarded from hand (Silent's signature) |
| **Doom** | At end of enemy turn, if Doom >= HP, enemy dies (Necrobinder's signature) |
| **Forge** | First use adds Sovereign Blade; subsequent uses increase its damage (Regent) |
| **Summon** | Summon Osty with X HP; if already summoned, raise Max HP by X (Necrobinder) |
| **Stars** | Secondary resource for Regent; generated and spent by specific cards; persists between turns |
| **Pierce** | Enemy attacks that bypass Block entirely |
| **Corrosion** | Reduces maximum HP at end of every turn |
| **Replay** | Plays card an additional time |
| **Plating** | Gain Block at end of turn; Plating reduced by 1 at start of turn |
| **Bound** | Can only play one Bound card per turn |
| **Smoggy** | Limited to playing one Skill per turn |
| **Confused** | Card costs randomize from 0 to 3 when drawn |

### 6.2 Returning Keywords (Potentially Changed)

| Keyword | Effect |
|---------|--------|
| Innate | Start each combat with this card in hand |
| Ethereal | If in hand at end of turn, Exhausted |
| Exhaust | Removed from deck until end of combat |
| Retain | Not discarded at end of turn |
| Sly | Discards from hand before turn-end, then plays for free |
| Transform | Card becomes a random card of any rarity |
| Vulnerable | Take 50% more damage from Attacks |
| Weak | Deal 25% less damage with Attacks |
| Intangible | All damage and HP loss reduced to 1 this turn |
| Artifact | Negates debuffs |
| Thorns | Deal damage back when hit by attack |

### 6.3 Orb System (Defect)

| Orb | Passive (End of Turn) | Evoke (When Pushed Out) |
|-----|----------------------|------------------------|
| Lightning | 3+Focus damage to random enemy | 8+Focus damage to random enemy |
| Frost | 2+Focus Block | 5+Focus Block |
| Dark | Stores 6+Focus damage (increases each turn) | All stored damage to lowest HP enemy |
| Plasma | Gain 1 Energy | Gain 2 Energy |
| Glass | Damage all enemies (decreases per turn) | Damage all enemies |

**Glass Orb** is new to STS2.

### 6.4 Enchantment System

- Enchantments are special modifiers that attach to individual cards
- Found through Unknown (?) room events and certain relics
- Persist until end of run (unlike Afflictions)
- Represent powerful bonuses with trade-offs

**Known Enchantments**:
- **Corrupted**: +50% card damage, but lose 3 HP each play
- **Adroit**: Additional Block when played
- **Perfect Fit**: Card goes to top of draw pile instead of shuffling
- **Soul's Power**: Removes Exhaust keyword (card is reusable)
- **Glam**: Adds Replay (plays again once per combat)
- **Momentum**: Increases attack damage each time played in combat

### 6.5 Other New Systems

- **Quest Cards**: Unplayable cards acquired from events, used at different events for massive payoffs
- **Enchantments**: See above - card modification system beyond simple upgrades
- **Dynamic Enemy AI**: Some enemies react to your board state mid-turn
- **Multi-Phase Boss Fights**: Act 2-3 bosses have distinct phases
- **Elite Reinforcements**: Some elites spawn minions if fights drag
- **Co-op Multiplayer**: Two-player mode with shared health pool

---

## 7. Potion Strategy

### 7.1 When to Use Potions

**Use potions when they change the outcome of a fight:**
- Preventing lethal damage
- Letting you safely kill an elite
- Preserving enough HP to take a riskier path
- Avoiding a rest that could be an upgrade instead

**Don't hoard potions for bosses exclusively.** If a potion prevents 15+ damage in a hallway fight, use it. That HP is worth more than the hypothetical boss usage.

### 7.2 Potion Slot Management

- You have **3 potion slots**
- Empty slots are wasted value - always pick up potions when offered
- If belt is full, treat the weakest potion as "free to upgrade" - use it aggressively so drops can replace it
- Before entering a fight where you might gain potions, use a weak potion to free a slot

### 7.3 Character-Specific Potion Strategy

- **Strength potions**: Incredible on multi-hit decks (Ironclad, Silent Shiv)
- **Focus potions**: Amazing on Defect
- **Block potions**: Good for any character, especially before big damage turns
- **Dexterity potions**: Scale with number of Block cards played per turn

### 7.4 Boss Fight Potion Usage

- Use potions proactively on critical boss turns (e.g., Vantom Turn 3, Knowledge Demon choice turns)
- Fairy in a Bottle acts as a safety net - save it for emergencies
- Duplicator on a key Power = double the scaling

### 7.5 Path Planning with Potions

- Potions let you safely choose riskier routes (extra elites, event-heavy paths)
- Before committing to a tough path, count how many emergencies your potions can cover
- Mass Block potions for multi-enemy fights, Vulnerable for burst turns, debuffs for bosses

---

## 8. Shop & Gold Management

### 8.1 Shop Spending Priority

1. **Card Removal** - Essential. Remove Strikes/Defends every shop visit.
2. **Key Relics** - Synergistic relics define runs
3. **Strategic Cards** - Only if they solve immediate problems
4. **Potions** - Generally lowest priority (valued at ~10 HP; 50 gold goes further on card removal)

### 8.2 Gold Earning Strategy

- Standard fights: 10-20 Gold
- Elite fights: 30-40 Gold + Relic
- Aim for 150+ Gold before first shop (3-5 standard combats in Act 1)
- Hunt Elites for both Gold and Relics
- Draft Hand of Greed for bonus gold on killing blows

### 8.3 Critical Gold Mistakes

- **Never take Ectoplasm** (boss relic: +1 Energy but permanently prevents all Gold gain)
- Don't waste gold on cards that don't fit your deck
- Save gold for card removal when nothing else is essential
- Looter enemies (Act 2) steal 15 Gold per hit - kill them fast, don't play a slow scaling game

---

## 9. Map Routing & Path Planning

### 9.1 General Routing Principles

1. **Check the boss first** - Tailor all decisions to that encounter
2. **Act 1: Aggressive pathing** - Fight normal enemies for gold/cards, then elites
3. **Place Rest Sites before Elites** when possible
4. **Balance**: Normal fights, Unknown rooms, Elites, Rest Sites
5. **Hover over map icons** to highlight all instances of that type

### 9.2 Rest Site Strategy

- **Default choice: Upgrade** (offense solves problems permanently; healing delays death)
- Only Rest if the next fight would kill you
- Target cards that provide the most impact for upgrade
- Some relics (Miniature Tent) allow both healing and upgrading
- Goal: Smith (upgrade) at least twice per run through deliberate pathing

### 9.3 Act-Specific Routing

**Act 1**:
- Find damage cards ASAP - basic Strikes can't handle Elites/Bosses
- Fight several normal enemies early for gold and cards
- Target 1-2 elites for relics
- Ensure rest site before boss

**Act 2**:
- Elites are significantly harder - be selective
- Focus on completing your archetype
- Shop visits for card removal

**Act 3**:
- Finalize your deck
- Remove any remaining Strikes/Defends
- Ensure win condition is consistent before boss

### 9.4 Unknown Room Value

- Events can provide: free card removal, free relics, healing, card transformation
- Unknown rooms are safer than elites but less predictable
- Best for decks that need specific fixes (removal, healing) without fighting

---

## 10. Card Tier Lists by Character

### 10.1 Ironclad Card Tiers

**S-Tier**: Expect a Fight, Offering, Battle Trance, Bloodletting, Headbutt, Colossus, Unmovable, Feed, Body Slam, Second Wind, Feel No Pain, Thrash, Brand, Dark Embrace, Barricade, Demon Form, Break

**A-Tier**: Inferno, Rupture, Taunt, Impervious, Flame Barrier, Pyre, Ashen Strike, Burning Pact, Pact's End, Fiend Fire, Aggression, Stoke, Spite, Pillage, Evil Eye, Crimson Mantle, Vicious, Primal Force, Armaments, Shrug It Off, True Grit, Whirlwind, Dismantle

**B-Tier**: Breakthrough, Hemokinesis, Pommel Strike, Blood Wall, Molten Fist, Stomp, Bludgeon, Perfected Strike, Infernal Blade, Juggling, Tremble, Uppercut, Dominate, Forgotten Ritual, Stone Armor, Cruelty, Hellraiser

**C-Tier**: Anger, Iron Wave, Twin Strike, Havoc, Bully, Howl from Beyond, Rage, Inflame, Conflagration

**D-Tier**: Sword Boomerang, Thunderclap, Grapple, Rampage, Fight Me!, Mangle

### 10.2 Silent Card Tiers

**S-Tier**: Adrenaline, Well-Laid Plans, Calculated Gamble, Acrobatics, Prepared, Reflex, Untouchable, Piercing Wail, Tools of the Trade, The Hunt, Expose, Speedster, Burst, Serpent Form, Master Planner, Wraith Form, Abrasive

**A-Tier**: Tactician, Afterimage, Blur, Pinpoint, Footwork, Corrosive Wave, Tracking, Malaise, Assassinate, Escape Plan, Dagger Throw, Finisher, Hidden Daggers, Noxious Fumes, Knife Trap, Envenom

**B-Tier**: Backflip, Leg Sweep, Predator, Backstab, Haze, Flick Flack, Ricochet, Blade Dance, Leading Strike, Follow Through, Flechettes, Precise Cut, Dash, Untouchable, Prepared, Cloak and Dagger, Strangle, Accuracy

**C-Tier and below**: Slice, Deflect, Snakebite, and other situational picks

### 10.3 Regent Card Tiers

**S-Tier**: Void Form, Big Bang, Genesis, Child of the Stars, Convergence, Glow, Reflect, Guards, Foregone Conclusion

**A-Tier**: Comet, Gamma Blast, Shining Strike, Dying Star, Seven Stars, Charge, Glimmer, Neutron Aegis, Particle Wall, Bombardment, Royalties

**B-Tier**: Hidden Cache, Gather Light, Solar Strike, Cloak of Stars, Cosmic Indifference, Summon Forth, Bulwark, Guiding Star, Photon Cut, Glitterstream, Astral Pulse, Crush Under

### 10.4 Necrobinder Card Tiers

**S-Tier**: Demesne, Capture Spirit, Undeath, Friendship, Seance, Dredge, Cleanse, Borrowed Time, Neurosurge

**A-Tier**: Graveblast, Lethality, High Five, Fetch, Sic Em, Rattle, Sacrifice, Necro Mastery, Death's Door, Death March, Reanimate, Debilitate, Putrefy, Devour Life, Shared Fate, Transfigure, Call of the Void, Parse

**B-Tier**: Spur, Pull Aggro, Flatten, Delay, Severance, Snap, Grave Warden, Enfeebling Touch, Bone Shards, Scourge, Negative Pulse, Defile, Reave, Drain Power, Poke

### 10.5 Defect Card Tiers

**S-Tier**: Echo Form, Spinner, Defragment, Supercritical, Glacier, Skim, Double Energy, Modded, Genetic Algorithm

**A-Tier**: Hologram, Glasswork, Chill, Compact, Buffer, Coolant, Machine Learning, Shatter, Rainbow, Consuming Shadow, Multi-Cast, Signal Boost, Reboot

**B-Tier**: Coolheaded, Turbo, Chaos, Fusion, Shadow Shield, Darkness, Boot Sequence, Compile Driver, Charge Battery, Leap, Lightning Rod, Tesla Coil, Ball Lightning, Go for the Eyes, FTL, Rip and Tear, White Noise, Sunder

---

## 11. Potion Tier List

### S-Tier (Best)
- Duplicator
- Fairy in a Bottle (revive at 30% HP on death)
- Fruit Juice
- Ghost in a Jar

### A-Tier (Very Strong)
- Beetle Juice, Block Potion, Bottled Potential, Clarity Extract, Cure All
- Droplet of Precognition, Dexterity Potion, Gigantification Potion
- Heart of Iron, Liquid Memories, Poison Potion, Pot of Ghouls
- Powdered Demise, Power Potion, Regen Potion, Ship in a Bottle
- Stable Serum, Touch of Insanity

### B-Tier (Solid)
- Ashwater, Blood Potion, Colorless Potion, Distilled Chaos
- Fire Potion, Energy Potion, Fysh Oil, Gambler's Brew
- Lucky Tonic, Mazaleth's Gift, Attack Potion, Radiant Tincture
- Skill Potion, Strength Potion, Swift Potion, Weak Potion

### C-Tier (Situational)
- Bone Brew, Fortifier, Focus Potion, Explosive Ampoule
- Essence of Darkness, Cunning Potion, Blessing of the Forge
- Entropic Brew, King's Courage, Orobic Acid, Potion of Binding
- Potion of Doom, Shackling Potion, Speed Potion, Star Potion
- Vulnerable Potion

### D-Tier (Weak)
- Flex Potion, Cosmic Concoction, Liquid Bronze
- Potion of Capacity, Snecko Oil, Soldier's Stew

---

## 12. Sources

### Strategy Guides
- [Mobalytics STS2 Beginner Guide](https://mobalytics.gg/slay-the-spire-2/guides/beginner-guide)
- [NeonLightsMedia Beginner's Guide: How to Survive Act 1](https://www.neonlightsmedia.com/blog/slay-the-spire-2-beginners-guide-survival)
- [GameRant: Best Tips & Tricks for Beginners](https://gamerant.com/slay-the-spire-2-best-tips-tricks-beginners/)
- [GameGuidesBox: Complete Guide](https://gameguidesbox.com/guides/slay-the-spire-2-complete-guide/)
- [STS2 Builds Guide](https://www.sts2builds.com/en)

### Character Guides
- [Mobalytics Ironclad Guide](https://mobalytics.gg/slay-the-spire-2/characters/ironclad-guide)
- [PCGamesN Ironclad Guide](https://www.pcgamesn.com/slay-the-spire-2/ironclad)
- [Mobalytics Silent Guide](https://mobalytics.gg/slay-the-spire-2/characters/silent-guide)
- [PCGamesN Silent Guide](https://www.pcgamesn.com/slay-the-spire-2/silent)
- [Mobalytics Defect Guide](https://mobalytics.gg/slay-the-spire-2/characters/defect-guide)
- [NeonLightsMedia Defect Guide](https://www.neonlightsmedia.com/blog/slay-the-spire-2-defect-guide-builds)
- [Mobalytics Regent Guide](https://mobalytics.gg/slay-the-spire-2/characters/regent-guide)
- [PCGamesN Regent Guide](https://www.pcgamesn.com/slay-the-spire-2/regent)
- [TheGamer Regent Beginner's Guide](https://www.thegamer.com/slay-the-spire-2-the-regent-beginners-tips-tricks-forge-star-colorless-guide/)
- [Mobalytics Necrobinder Guide](https://mobalytics.gg/slay-the-spire-2/characters/necrobinder-guide)
- [PCGamesN Necrobinder Guide](https://www.pcgamesn.com/slay-the-spire-2/necrobinder)
- [TheGamer Necrobinder Beginner's Guide](https://www.thegamer.com/slay-the-spire-2-the-necrobinder-beginners-tips-tricks-doom-souls-etheral-guide/)

### Boss Guides
- [SlashSkill: Every Boss, Attack Patterns, and How to Beat Them](https://www.slashskill.com/slay-the-spire-2-boss-guide-every-boss-attack-patterns-and-how-to-beat-them/)
- [Games.gg: Act 2 Bosses Guide](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-act-2-bosses-guide/)
- [Games.gg: How to Beat Doormaker](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-act-3-how-to-beat-doormaker/)
- [NeonLightsMedia: Test Subject Boss Guide](https://www.neonlightsmedia.com/blog/slay-the-spire-2-test-subject-boss-guide)
- [PC Gamer: Doormaker Boss Guide](https://www.pcgamer.com/games/roguelike/slay-the-spire-2-doormaker/)

### Elite Guides
- [GamerBlurb: Every Elite Enemy in Each Act](https://gamerblurb.com/articles/slay-the-spire-2-elites-guide-every-elite-enemy-in-each-act)
- [STS2.space: Elite Enemies Guide](https://slaythespire2.space/guides/elites/)

### Tier Lists
- [Mobalytics Card Tier List](https://mobalytics.gg/slay-the-spire-2/tier-lists/cards)
- [Mobalytics Potion Tier List](https://mobalytics.gg/slay-the-spire-2/tier-lists/potions)
- [Mobalytics Relic Tier List](https://mobalytics.gg/slay-the-spire-2/tier-lists/relics)
- [STS2Guide Card Tier List](https://slaythespire2guide.com/cards-tier-list.html)

### Mechanics & Systems
- [Mobalytics Keywords Guide](https://mobalytics.gg/slay-the-spire-2/guides/keywords)
- [XMODhub: New Mechanics Guide](https://www.xmodhub.com/info/xmod-blog/slay-the-spire-2-new-mechanics-guide/)
- [Mobalytics Enchantments Guide](https://mobalytics.gg/slay-the-spire-2/guides/enchantments)
- [GamerBlurb Enchantments Guide](https://gamerblurb.com/articles/slay-the-spire-2-enchantments-full-list-effects)
- [DTGRE: Combat Guide (Damage, Block & Doom)](https://www.dtgre.com/2026/03/slay-the-spire-2-combat-guide-damage-block-doom.html)

### Potions & Items
- [GamerBlurb: Full Potions List and Best Potions](https://gamerblurb.com/articles/slay-the-spire-2-potions-guide-full-list-and-best-potions)
- [STS2.gg Potions Guide](https://slaythespire2.gg/potions)

### Ascension & Advanced
- [NeonLightsMedia: Ascension Levels Guide](https://www.neonlightsmedia.com/blog/slay-the-spire-2-ascension-guide-levels)
- [The Escapist: Ascension Levels and Tips](https://www.escapistmagazine.com/news-ascension-level-slay-the-spire-2-tips/)
- [CasualGameGuides: When to Skip Cards](https://casualgameguides.com/walkthroughs/slay-the-spire-2/consistent-deck-and-skip-cards)

### Events
- [TheGamer: Every Event and Best Choice](https://www.thegamer.com/slay-the-spire-2-events-guide-all-events-best-choices-strategy/)
- [Mobalytics Events List](https://mobalytics.gg/slay-the-spire-2/encounters/events)
