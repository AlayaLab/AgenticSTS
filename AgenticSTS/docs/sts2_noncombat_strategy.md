# Slay the Spire 2 — Non-Combat Decision Strategy Guide

Compiled from extensive web research (March 2026). All information pertains to **Slay the Spire 2** (Early Access, released March 5, 2026), not the original STS1.

---

## Table of Contents

1. [Map Structure and Mechanics](#1-map-structure-and-mechanics)
2. [Map Routing / Pathing Strategy](#2-map-routing--pathing-strategy)
3. [Rest Site Decisions](#3-rest-site-decisions)
4. [Shop Strategy](#4-shop-strategy)
5. [Event Strategy](#5-event-strategy)
6. [Relic and Treasure Strategy](#6-relic-and-treasure-strategy)
7. [Ancients (Boss Relics Replacement)](#7-ancients-boss-relics-replacement)
8. [New Mechanics Unique to STS2](#8-new-mechanics-unique-to-sts2)
9. [Character-Specific Non-Combat Notes](#9-character-specific-non-combat-notes)
10. [Ascension Modifiers](#10-ascension-modifiers)
11. [Sources](#11-sources)

---

## 1. Map Structure and Mechanics

### Acts and Biomes

STS2 has **3 Acts** per run, with approximately 45-50 total encounters. Each act has **two biome variants** (alternate acts), though only Act 1's alternate is available in early access:

| Act | Primary Biome | Alternate Biome | Status |
|-----|---------------|-----------------|--------|
| Act 1 | Overgrowth | Underdocks | Both available |
| Act 2 | Hive | TBD | Only Hive available |
| Act 3 | Glory | TBD | Only Glory available |

### Map Node Types

The map contains **7 types of locations**:

1. **Monster Encounter (Normal)** — Standard combat, rewards gold + card choice + possible potion
2. **Elite Encounter** — Harder combat, rewards relic + gold + card choice + possible potion
3. **Rest Site (Campfire)** — Rest (heal 30% max HP) or Smith (upgrade a card)
4. **Unknown (?)** — Can contain: Event (most likely), Monster, Shop, or Treasure
5. **Treasure Room** — Contains a relic (guaranteed)
6. **Merchant (Shop)** — Buy cards, relics, potions; remove cards
7. **Boss Encounter** — End-of-act boss fight

### Map Structure (inherited from STS1 engine)

- Each act has approximately 15-17 floors
- Up to 6 nodes per floor in a horizontal row
- Nodes connect via 1-3 paths entering/exiting
- Floor 1: always normal combat encounters
- Mid-act floor: guaranteed Treasure Room
- Pre-boss floor: guaranteed Rest Site
- Branching paths force meaningful route decisions

### Unknown Room (?) Probabilities

- **Events** have the highest spawn chance
- **Treasure**: 2% base chance, +2% each time a ? room does not contain treasure
- **Shop**: 3% base chance, +3% each time a ? room does not contain shop
- **Monster**: fills remaining probability
- **Juzu Bracelet** relic: prevents monster encounters in ? rooms
- At higher ascensions, **Deadly Events** modifier can spawn Elites in ? rooms

### Bosses by Act

**Act 1 — Overgrowth:**
- Vantom (serpent, applies Slippery debuff, huge tail slam)
- The Kin / Kin Priest (summons healing adds)
- Ceremonial Beast (inflicts debuffs when health drops)

**Act 1 — Underdocks:**
- Soul Fysh
- Waterfall Giant
- Lagavulin Matriarch

**Act 2 — Hive:**
- Kaiser Crab (layers block, claw barrages)
- Knowledge Demon (forces debuff choices, heals, gains permanent Strength)
- The Insatiable (Sandpit stacks, ramps Strength)

**Act 3 — Glory:**
- Test Subject (Enrage: gains 2 Strength per Skill played; phase transition cleanses all debuffs)

### Elites by Act

**Act 1 — Overgrowth:** Bygone Effigy, Byrdonis, Phrog Parasite
**Act 1 — Underdocks:** Phantasmal Gardener, Skulking Colony, Terror Eel
**Act 2 — Hive:** Decimillipede, Entomancer, Infested Prism
**Act 3 — Glory:** Knight Trio, Mecha Knight, Soul Nexus

---

## 2. Map Routing / Pathing Strategy

### Core Routing Principles

1. **Check the boss first.** Every pathing decision should be tailored to surviving that specific boss encounter. Know the boss before choosing your route.

2. **Target 2-3 elite fights in Act 1.** Elites drop relics, which provide the passive scaling needed to survive later acts. Avoiding elites creates a power deficit that compounds across the run.

3. **Place Campfires before Elites.** Plot routes so a rest site appears directly before an elite node, giving you the option to upgrade a critical card right before the hard fight.

4. **HP is a resource, not a score.** Every point above zero is available to spend for advantages elsewhere. Low-HP pathing enables choosing beneficial events and smithing instead of healing.

5. **Path toward shops when gold allows.** If Neow's bonus gives significant gold, confirm a merchant appears on your route before accepting the blessing.

### Act-by-Act Pathing

**Act 1 — Building Foundations:**
- Fight several normal enemies early to accumulate gold and card rewards
- Aim for 2-3 elite fights (relics are essential)
- Prioritize frontloaded damage cards so you can safely fight elites
- Path through at least 2 campfires for upgrades
- Almost any Common attack card outperforms starter Strikes for elite kills

**Act 2 — Scaling Phase:**
- Deck must be dealing "real damage" by now or you will struggle
- Bosses have permanent scaling and punish passive play
- Continue hunting elites but be more selective based on deck strength
- Route toward shops for card removal and key relic purchases

**Act 3 — Win Condition:**
- Fully scaled builds with clear win conditions required
- Boss encounters test whether your deck has a specific plan
- Treasure rooms and remaining shops are final optimization opportunities

### When to Visit Unknown (?) Rooms

- **Weak deck?** Visit unknowns — the potential upside (events, free card removal, treasures) outweighs the risk
- **Strong deck?** Weigh the cost carefully — a bad monster fight could cost significant HP
- Early in the run, unknowns are generally good for their event/treasure potential
- Unknown rooms can provide card removal (some events offer free card removal)

### When to Visit Shops

- Path toward shops when you have 150+ gold
- Save gold for the shop if you need card removal (75g first, 100g subsequent)
- Don't visit a shop when broke unless you have Membership Card or Courier

### Balancing Risk vs Reward

- More elites = more relics = stronger run, BUT more HP spent
- The sweet spot is 2-3 elites per act with rest sites buffering between them
- If deck is weak (lacking damage), avoid extra elites and focus on building through normal fights and events
- If deck is strong (reliable damage + block), push for more elites aggressively

---

## 3. Rest Site Decisions

### Standard Options

| Option | Effect | Availability |
|--------|--------|-------------|
| **Rest** | Heal 30% of max HP | Always |
| **Smith** | Upgrade one card | Always |
| **Recall** | Obtain the Ruby Key | Only if Act 4 unlocked |

### Relic-Granted Options

| Option | Relic Required | Effect |
|--------|---------------|--------|
| **Lift** | Girya | Gain 1 Strength (up to 3 uses) |
| **Dig** | Shovel | Dig for a relic |
| **Toke** | Peace Pipe | Remove a card from deck |
| **Cook** | Meat Cleaver | Remove 2 cards, gain 9 max HP |
| **Hatch** | Byrdonis Egg (quest) | Hatch egg into Byrd Swoop (14 dmg, 0 cost) |

Note: **Miniature Tent** relic lets you perform multiple campfire actions at once.

### Relic Modifiers

- **Dream Catcher**: Adds a card reward screen after Resting
- **Regal Pillow**: Resting heals an additional 15 HP
- **Stone Humidifier** (Neow blessing): Gain 5 max HP per Rest Site visit

### When to Smith vs Rest — Decision Framework

**Smith (Upgrade) is the default.** Community consensus and every major guide agrees:

> "Prioritize Smith over resting unless your HP is critically low."

> "Offense solves problems permanently, while healing just delays your inevitable death."

**Why upgrading is usually better:**
- Upgraded cards shorten future fights, meaning less total damage taken across the rest of the run
- Healing 30% max HP only buys 1-2 more fights at the cost of a power spike that compounds across the entire act
- Card upgrades can double a card's effectiveness (e.g., reducing cost to 0, doubling damage)

**When to Rest instead:**
- HP is critically low AND the next fight would likely kill you
- Entering the Act boss at critically low health AND your deck is already strong
- You have no meaningful upgrade targets left
- Dream Catcher relic makes resting give a card reward too (making rest less of a "waste")

**Upgrade targets (priority order):**
1. Cards that solve your deck's biggest weakness RIGHT NOW
2. Cards that become dramatically better when upgraded (cost reduction to 0, doubled effect)
3. Core win-condition cards (scaling powers, key attacks)
4. High-frequency cards you play every combat
5. NEVER upgrade cards you plan to remove soon (Strikes, Defends)

**Target: Smith at least twice per run** through deliberate campfire pathing. Three times is better if the map allows.

### HP Thresholds (Heuristic)

- **Above 60% HP**: Almost always Smith
- **40-60% HP**: Smith unless the next encounter is an elite/boss you might lose
- **Below 40% HP**: Consider resting, especially if the next encounter is dangerous
- **Below 25% HP**: Almost always Rest (unless Regal Pillow makes a small rest meaningless and the upgrade is game-changing)

### Pre-Boss Rest Strategy

- If your deck is strong enough to beat the boss, Smith for the compounding upgrade
- If the boss specifically counters your deck weakness, Smith the card that addresses it
- If you are genuinely at risk of dying to the boss, Rest
- Remember: the Ancient at the start of the next act provides some healing (heals 80% missing HP at Ascension 2+, full heal at Ascension 0-1)

---

## 4. Shop Strategy

### What the Shop Sells

- **5 Character cards**: 2 Attacks, 2 Skills, 1 Power (one random card has 50% discount)
- **2 Colorless cards**: 1 Uncommon, 1 Rare
- **3 Relics**: right-most is always a Shop-exclusive relic
- **3 Potions**
- **Card Removal service**: once per shop visit

### Card Removal Cost

| Removal # | Cost |
|-----------|------|
| 1st | 75 Gold |
| 2nd | 100 Gold |
| 3rd+ | 100 Gold (continues at 100) |

### Purchase Priority (High to Low)

1. **Card Removal** (75-100g) — Almost always the best purchase. Removing a Strike or Defend permanently improves deck quality by increasing the chance of drawing your powerful cards. "The more basic cards you delete, the faster you draw the incredibly powerful attacks and powers."

2. **Build-defining Relics** — Relics compound across the entire run. A relic that synergizes with your deck's direction provides more value than any single card. Prioritize relics over individual card buys when gold allows.

3. **Key Cards** — Only buy a card that directly addresses your deck's most critical weakness or perfectly completes a synergy. Never impulse-buy.

4. **Potions** — Buy when belt is not full and you are about to face an elite/boss, or when the potion specifically enables a fight you would otherwise lose.

5. **Marginal Cards/Relics** — Skip anything that doesn't solve an immediate problem.

### Gold Management by Act

**Act 1 (Target: 150-300 gold by first shop):**
- Fight 3-5 standard combats before first shop to build gold
- Standard fights grant 10-20 gold each
- Elite fights grant 30-40 gold plus a relic
- First shop priority: card removal (75g), then assess relic/card offerings

**Act 2 (250-400 gold is comfortable):**
- Continue building through elites and normal fights
- Reserve ~50 gold for future removes or potions unless buying a game-winning item
- Don't blow gold on mediocre cards — saving for a later shop with better offerings pays off

**Act 3 (Spend what you have):**
- Final optimization — buy what completes your build
- Card removal still valuable for consistency
- No reason to save gold past the last shop

### Gold Spending Heuristics

- **Under 200 gold**: Hyper-efficient spending only. Card removal (75g) is almost always best value.
- **200-400 gold**: Establish purchase hierarchy based on deck state. What is your greatest weakness?
- **400+ gold**: Can afford relic + removal, or relic + key card.
- **Always reserve ~50g** for emergency purchases unless spending on something game-winning.

### Shop-Related Relics

- **Membership Card**: 50% discount on all shop purchases
- **The Courier**: When you buy an item, it is replaced by a random item of the same type; all purchases get 20% discount
- **Maw Bank**: Gain 12 gold each time you visit a non-shop location (lose all banked gold on shop visit)
- **Old Coin**: Gain 300 gold immediately

### The Fake Merchant (Act 3 Special Event)

- Appears in Act 3 as a special event
- Sells **Knockoff Relics** — budget versions of standard relics with reduced effects
- Knockoff relics stack with genuine relics
- **Foul Potion trick**: Throw a Foul Potion at the Fake Merchant to start a fight. Defeating him yields 300 Gold + his entire knockoff relic inventory for free.
- Examples: Heart of Iron??? (7 Plating), Anchor??? (4 Block at combat start), Orichalcum??? (3 Block)

---

## 5. Event Strategy

### How Events Work

- Events appear primarily in Unknown (?) rooms
- Events have the highest spawn chance among ? room outcomes
- Each act/biome has its own pool of events
- Some events are shared across multiple acts
- Most events offer 2-3 choices with different risk/reward profiles

### General Event Principles

1. **Evaluate based on current deck state** — An event that offers card removal is amazing for a bloated deck but worthless for a thin one
2. **HP cost events are acceptable** when the reward is strong enough and you have HP to spare
3. **Gold rewards are worth more early** (before shops) and less late (after last shop)
4. **Card transformation is risky** — random results can hurt more than help
5. **Free relics are almost always worth the cost** — relics compound across the entire run
6. **Quest cards are dead draws** — only accept if your deck can handle the dead weight until the quest completes

### Complete Event List by Act

#### Shared Events (appear in multiple acts)

| Event | Acts | Choices | Recommendation |
|-------|------|---------|----------------|
| **Brain Leech** | 1a, 1b, 2 | — | — |
| **Crystal Sphere** | 2, 3 | Pay for 3 Divinations OR pay more for 6 (with Debt) | 3 Divinations is safer |
| **Potion Courier** | 2, 3 | — | — |
| **Self-Help Book** | 1a, 1b, 2 | Enchant with Sharp 2, Nimble 2, or Swift 2 | Sharp or Nimble preferred |
| **Slippery Bridge** | 1a, 2, 3 | Card removed OR lose HP to reroll | Can reroll repeatedly |
| **Symbiote** | 2, 3 | Enchant attack with Corrupted OR Transform card | Transform if struggling with HP |
| **The Future of Potions?** | 2, 3 | — | — |
| **The Legends Were True** | 1a, 1b | Receive map OR lose HP for random potion | Map is almost always better |
| **This or That?** | 1a, 2 | Lose 6 HP for 48 gold OR add Clumsy + random relic | Relic option (relic value outweighs Clumsy) |

#### Act 1a — Overgrowth Events

| Event | Choices | Recommendation |
|-------|---------|----------------|
| **Aroma of Chaos** | — | — |
| **Byrdonis Nest** | Gain 7 Max HP OR Take Byrdonis Egg quest | Early run: egg (hatches into 14 dmg 0-cost card); Late run: HP |
| **Dense Vegetation** | Remove card for 11 HP OR Heal 19 HP but fight | Remove if HP allows |
| **Jungle Maze Adventure** | — | — |
| **Morphic Grove** | Lose 100 gold to transform cards OR Gain 5 Max HP | Gain 5 Max HP (avoid transformation RNG) |
| **Room Full of Cheese** | Choose 2 of 8 cards OR Lose 14 HP for Chosen Cheese | Depends on HP |
| **Sapphire Seed** | Heal 9 HP + upgrade card OR Enchant with Sown | Heal + upgrade is generally better |
| **Tablet of Truth** | Lose 3 Max HP to upgrade random card OR Heal 20 HP | Upgrade (better long-term value) |
| **The Sunken Statue** | Get Sword of Stone relic OR 115 gold for 7 HP | Sword if you plan 5+ elite kills |
| **Wellspring** | Random potion OR Remove card (adds Guilty for 5 combats) | Remove if troublesome card exists |
| **Whispering Hollow** | Lose 50 gold for 2 potions OR Lose 9 HP to transform | Potions unless full on potion slots |
| **Wood Carvings** | — | — |

#### Act 1b — Underdocks Events

| Event | Notes |
|-------|-------|
| **Abyssal Baths** | Multi-part encounter |
| **Doors of Light and Dark** | — |
| **Sunken Treasury** | — |

#### Act 2 — Hive Events

| Event | Key Details |
|-------|-------------|
| **Bugslayer** | Add Exterminate (AoE) OR Squash (single-target) |
| **Colossal Flower** | Multi-part encounter |
| **Doll Room** | Pick from 3 relics: Daughter of the Wind, Mr. Struggles, Bing Bong |
| **Field of Man-Sized Holes** | Remove 2 cards + add Normality OR Enchant with Perfect Hit |
| **Infested Automaton** | — |
| **Mysterious Knight** | Grants Lantern Key quest item (needed for Act 3 War Historian) |
| **Stone of All Time** | — |
| **Tea Master** | — |
| **The Lost Wisp** | — |
| **Welcome to Wongo's** | — |
| **Zen Weaver** | — |

#### Act 3 — Glory Events

| Event | Key Details |
|-------|-------------|
| **Battleworn Dummy** | Fight dummy at different HP levels for rewards |
| **Fake Merchant** | Knockoff relics shop; Foul Potion trick for free loot |
| **Grave of the Forgotten** | — |
| **Hungry for Mushrooms** | — |
| **Ranwid the Elder** | — |
| **Relic Trader** | — |
| **The Round Tea Party** | — |
| **The Trial** | Guilty: gain 10 HP; Innocent: gain 300 gold + Regret curse. Choose Guilty if low HP. |
| **Tinker Time** | Multi-part encounter |
| **War Historian, Repy** | Requires Lantern Key from Act 2 Mysterious Knight |

### Quest Cards

Quest Cards are **Unplayable** cards obtained from specific events that become dead draws in combat until their condition is fulfilled:

| Quest | Source | Condition | Reward |
|-------|--------|-----------|--------|
| **Byrdonis Egg** | Byrdonis Nest event | Visit Rest Site, choose "Hatch" | Byrd Swoop (14 dmg, 0 cost) |
| **Spoils Map** | Spoils Map event | Complete quest objective | 600 Gold |
| **Lantern Key** | Mysterious Knight (Act 2) | Defeat Flail Knight | Access to War Historian in Act 3 |

**Quest Card Strategy**: Only accept quest cards if your deck can handle a dead draw for several combats. In thin decks (15-18 cards), a dead draw is more punishing. In larger decks (25+), the dead draw is more tolerable.

---

## 6. Relic and Treasure Strategy

### How Relics Work

- Relics provide permanent passive bonuses for the entire run
- **Sources**: Elite defeats (guaranteed), Treasure Rooms, Shops, Events, Ancients (boss relics)
- Some relics have **Durability** (limited activations per combat)
- Relics are the primary way passive power scales

### Relic Tier List (Universal — All Characters)

**S-Tier (18 relics — always pick):**
Anchor, Bag of Preparation, Funerary Mask, Gambling Chip, Ghost Seed, Gorget, History Course, Horn Cleat, Ice Cream, Lizard Tail, Mango, Mercury Hourglass, Molten Egg, Mr. Struggles, Razor Tooth, Red Mask, Toxic Egg, Tuning Fork

**A-Tier (47 relics — almost always pick):**
Amethyst Aubergine, Art of War, Bellows, Big Hat, Byrdpip, Captain's Wheel, Charon's Ashes, Festive Popper, Fragrant Mushroom, Frozen Egg, Gremlin Horn, Happy Flower, Lantern, Lava Lamp, Lee's Waffle, Lost Wisp, Lunar Pastry, Maw Bank, Meal Ticket, Meat on the Bone, Membership Card, Mummified Hand, Pantograph, Pear, Pen Nib, Pocketwatch, Prayer Wheel, Shovel, Stone Calendar, Stone Cracker, Sturdy Clamp, The Chosen Cheese, Tungsten Rod, Unsettling Lamp, Vajra, Vambrace, Venerable Tea Set, War Paint, Whetstone, White Star, Wongo's Mystery Ticket

**B-Tier (64 relics — solid but situational):**
Akabeko, Bag of Marbles, Blood Vial, Bone Tea, Bowler Hat, Bread, Bronze Scales, Candelabra, Centennial Puzzle, Chandelier, Cloak Clasp, Data Disk, Demon Tongue, Dolly's Mirror, Dragon Fruit, Dream Catcher, Ember Tea, Eternal Feather, Fresnel Lens, Game Piece, Girya, Hand Drill, Kunai, Kusarigama, Lasting Candy, Letter Opener, Lucky Fysh, Miniature Tent, Ninja Scroll, Nunchaku, Oddly Smooth Stone, Old Coin, Orichalcum, Ornamental Fan, Orrery, Paper Krane, Pendulum, Petrified Toad, Pollinous Core, Regal Pillow, Ringing Triangle, Runic Capacitor, Shuriken, Sling of Courage, Sparkling Rouge, Strawberry, Sword of Stone, The Abacus, The Boot, The Courier, Tough Bandages, Vexing Puzzlebox, White Beast Statue, Wing Charm

**C-Tier (48 relics — requires specific synergy):**
Beating Remnant, Belt Buckle, Big Mushroom, Bone Flute, Bookmark, Brimstone, Burning Sticks, Cauldron, Chemical X, Darkstone Periapt, Daughter of the Wind, Dingy Rug, Emotion Chip, Fencing Manual, Forgotten Soul, Galactic Dust, Gnarled Hammer, Gold-Plated Cables, Helical Dart, Ivory Tile, Joss Paper, Juzu Bracelet, Kifuda, Metronome, Miniature Cannon, Mini Regent, Mystic Lighter, Paper Phrog, Permafrost, Planisphere, Potion Belt, Power Cell, Punch Dagger, Rainbow Ring, Red Skull, Reptile Trinket, Ripple Basin, Royal Stamp, Ruined Helmet, Self-Forming Clay, Snecko Skull, Strike Dummy, Tingsha, Tiny Mailbox, Vitruvian Minion

**D-Tier (8 relics — avoid if possible):**
Bing Bong, Book of Five Rings, Book Repair Knife, Intimidating Helmet, Parrying Shield, Regalite, Royal Poison, Screaming Flagon

### What Makes a Relic Good?

The best relics do at least one of three things:
1. **Generate energy** (enable playing more cards per turn)
2. **Scale passively** without requiring card plays
3. **Protect from new STS2 status effects** (Pierce, Corrosion)

### Durability Mechanic

Some STS2 relics have **Durability** — limited activations per combat. A relic with 1-2 Durability may excel against hallway enemies but underperform against bosses where fights last 8+ turns. Always factor Durability into evaluation.

### Treasure Room Strategy

- Treasure Rooms contain 1 guaranteed relic
- The mid-act Treasure Room is always guaranteed on the map
- Always path through the Treasure Room unless it forces an extremely dangerous route
- Some Ancient blessings affect treasure (e.g., Silver Crucible makes first chest empty)

### Character-Specific Relic Highlights

| Character | Key Relics |
|-----------|-----------|
| Ironclad | Red Skull (+3 Str below 50% HP), Self-Forming Clay (Block on HP loss) |
| Silent | Snecko Skull (extra Poison), Kunai (Dexterity after attacks) |
| Defect | Data Disk (extra Focus), Emotion Chip (passive Orb on damage) |
| Regent | Lunar Pastry (boosts Royal abilities) |
| Necrobinder | Bone Flute (+2 Block when Osty attacks), Undying Sigil (Doom targets deal 50% less) |

---

## 7. Ancients (Boss Relics Replacement)

### How Ancients Work

Ancients are STS2's replacement for Boss Relics. They are NPCs that appear at the **start of each act**, offering powerful blessings — many with significant downsides. You MUST pick one of 3 randomly offered blessings (no skip option, unlike STS1 boss relics).

Key differences from STS1 Boss Relics:
- Cannot skip — must choose one
- Some blessings have devastating downsides
- 3 options offered (from a pool of 10-20)
- Different Ancients appear in different acts
- They define your run's strategy alongside your deck

### Act 1 — Neow (Always)

Neow offers 20 possible blessings. Key picks:

| Blessing | Effect | Evaluation |
|----------|--------|------------|
| Precise Scissors | Remove 1 card | Always good (free deck thinning) |
| Pomander | Upgrade a card | Solid early boost |
| Nutritious Oyster | Gain max HP | Safe, scaling value |
| Golden Pearl | Gain 150 Gold | Enables early shop power spike |
| Cursed Pearl | Gain 333 Gold + Greed curse | High risk/reward |
| Lava Rock | Act 1 Boss drops 2 Relics | Excellent long-term value |
| Arcane Scroll | Random Rare Card | Can be build-defining |
| Silver Crucible | First 3 card rewards upgraded; first chest empty | Strong if treasure isn't on your route |
| Stone Humidifier | +5 Max HP per Rest Site | Compounds across the run |
| Leafy Poultice | Transform 1 Strike + 1 Defend, lose 10 Max HP | Risky but removes bad cards |
| Precarious Shears | Deck thinning with damage cost | — |

### Act 2 Ancients (One of Three)

**Orobas** — Card quality and potions:
- Prismatic Gem: +1 energy per turn (S-tier)
- Glass Eye: 2 Common + 2 Uncommon + 1 Rare card
- Sea Glass: View 15 cards from another character, add any
- Alchemical Coffer: +4 Potion slots with random potions

**Pael** — Energy and card manipulation:
- Pael's Blood: Draw 1 extra card per turn
- Pael's Tears: Unspent energy gives 2 bonus next turn
- Pael's Wings: Sacrifice card rewards to gain Relics
- Pael's Eye: Exhaust hand for extra turn if ending with no cards
- Pael's Flesh: Extra energy starting turn 3

**Tezcatara** — Fire-themed energy:
- Very Hot Cocoa: Start combats with 4 extra energy (huge burst)
- Pumpkin Candle: +energy per turn, extinguishes at Act 3 start
- Golden Compass: Replace Act 2 map with special single path
- Seal of Gold: Spend 5 Gold per turn for 1 energy
- Nutritious Soup: Enchant all Strikes with Tezcatara's Ember

### Act 3 Ancients (One of Four)

**Darv** (12 blessings — familiar STS1 boss relics):
- Pandora's Box: Transform ALL Strikes and Defends
- Runic Pyramid: Do not discard hand at turn end
- Snecko Eye: Draw 2 extra, start Confused
- Velvet Choker: +1 energy, max 6 cards per turn
- Ectoplasm: +1 energy, cannot gain Gold (AVOID if gold matters)
- Philosopher's Stone: +1 energy, enemies start with 1 Strength
- Sozu: +1 energy, no more potions
- Empty Cage: Remove 2 cards
- Black Star: Elites drop extra relic
- Astrolabe: Transform 3 cards, then upgrade them

**Nonupeipe** — Scaling and utility:
- Jewelry Box: Add 1 Apotheosis to deck (upgrades ALL cards in combat)
- Looming Fruit: +31 Max HP
- Signet Ring: Gain 999 Gold
- Brilliant Scarf: Every 5th card played is free
- Diamond Diadem: Half damage when playing 2 or fewer cards per turn
- Fur Coat: Mark 7 combats where enemies start with 1 HP

**Tanx** — Attack-focused:
- Throwing Axe: First card each combat plays twice
- Crossbow: Free random Attack added to hand each turn
- Spiked Gauntlet: +1 energy, Powers cost 1 more
- Iron Club: Draw 1 card per 4 played

**Vakuu** — Versatile:
- Distinguished Cape: Lose 9 Max HP, add 3 Apparitions
- Whispering Earring: +energy per turn, Vakuu plays your first turn
- Music Box: Ethereal copy of first Attack played each turn
- Lord's Parasol: Obtain everything from Merchant immediately
- Fiddle: Draw 2 extra, cannot draw during turns

---

## 8. New Mechanics Unique to STS2

### Pierce
- Enemy buff that causes attacks to **bypass Block entirely**
- Cannot be mitigated by armor/block stacking
- Counter with **Weak debuff** (reduces damage) or burst kills
- Changes defensive strategy: against Pierce enemies, offense > defense

### Corrosion
- Status effect that **reduces maximum HP at end of each turn**
- Cannot be blocked, stalled, or out-sustained
- Requires **frontloaded burst damage** to end fights quickly
- Relics that speed up combat (energy, free damage) become more valuable
- High-block relics lose value against Corrosion enemies

### Durability
- Limits relic/card activations **per combat**
- A relic with 1-2 Durability may dominate hallway fights but underwhelm against bosses
- Factor Durability into relic evaluation — boss performance matters most

### Enchantments
- Permanent modifiers that attach to individual cards for the entire run
- Can be obtained through events and encounters
- Some are pure bonuses, others have tradeoffs

| Enchantment | Effect |
|-------------|--------|
| **Sharp** | Increases attack damage |
| **Nimble** / **Adroit** | Increases Block generation |
| **Corrupted** | +50% damage, but costs HP per play |
| **Instinct** | Reduces energy cost by 1 |
| **Glam** | Card replays once per combat (Replay) |
| **Perfect Fit** | Card goes to top of draw pile instead of shuffling in |
| **Soul's Power** | Removes Exhaust keyword (card can be replayed) |
| **Slither** | Randomizes cost between 0-3 each draw |
| **Sown** | (From Sapphire Seed event) |
| **Goopy** | (From Pael's Claw blessing) |
| **Swift** | (From Self-Help Book event) |

### Afflictions (Negative Enchantments)
- Unlike Enchantments, Afflictions are negative permanent modifiers
- Applied by enemies and certain events
- Cannot be removed once applied

### Quest Cards
- Unplayable cards that are dead draws until their condition is met
- Obtained from specific events
- Risk: dead draw in combat; Reward: powerful payoff
- Only accept if deck can tolerate dead weight

### Alternate Acts (Biome Variants)
- Each act can have 2 different biome versions
- Different enemies, elites, bosses, and events per variant
- Currently only Act 1 has both variants (Overgrowth and Underdocks)

---

## 9. Character-Specific Non-Combat Notes

### Ironclad
- **Starting Relic**: Burning Blood (heals 6 HP after every combat)
- Built-in sustain makes aggressive pathing safer
- Strength-scaling decks are most consistent
- **Top upgrade targets**: Offering, Battle Trance, Colossus, Expect a Fight
- Can take more HP damage from events due to post-combat healing

### Silent
- Discard synergies and **Sly** keyword (discarded Sly cards play for free)
- Wraith Form + draw tools for consistent clears
- Poison stacking is harder than STS1 (no Catalyst equivalent found)
- **Top upgrade targets**: Adrenaline, Well-Laid Plans, Calculated Gamble, The Hunt
- Potions are extra valuable (Dexterity, Weak, Swift potions)

### Regent
- **Stars mechanic**: Stars persist between turns (no cap), start with 3 via Divine Right relic
- Two archetypes: **Stars** (Star generation + powerful Star-cost cards) and **Forge** (Sovereign Blade scaling)
- Don't spend Stars reactively — accumulate for bigger payoffs
- Don't overcommit to archetype early; pick generic options
- **Top upgrade targets**: Void Form, Big Bang, Genesis, Convergence, Glow

### Necrobinder
- **Osty**: Skeletal companion that absorbs damage; starts at 1 HP per combat
- **Doom**: Death-mark mechanic — executes enemies at or below their Doom stacks
- **Souls**: Colorless 0-cost Exhaust cards that draw 2
- **Blood Magic**: Spends HP for power
- Lowest HP pool — buff Osty early or take direct damage
- **Top upgrade targets**: Demesne, Capture Spirit, Undeath, Friendship, Seance

### Defect
- **Echo Form** is the single most important card to prioritize
- Orb mechanics remain central
- Avoid conflicting cards (Consume vs. Hyperbeam)
- **Top upgrade targets**: Echo Form, Defragment, Spinner, Glacier, Supercritical

### General Deck Building Rules (All Characters)

- **Ideal deck size**: 20-25 cards by Act 1 boss
- **Skip card rewards** that don't address current weaknesses
- Build foundation first (reliable damage + consistent block + answer to high-attack enemies), then layer synergies
- "Every card added to the deck dilutes your draw pool"
- Experienced players may run 30+ cards if filled with strong synergies
- STS2 rewards "flexible, well-rounded decks far more than the original did"

---

## 10. Ascension Modifiers

STS2 has 10 Ascension levels (vs STS1's 20):

| Level | Name | Effect | Strategy Impact |
|-------|------|--------|-----------------|
| 1 | Swarming Elites | More elites spawn on map | Must path more carefully around elites |
| 2 | Weary Traveler | Boss Ancients heal only 80% of missing HP | Less post-boss recovery |
| 3 | Poverty | Enemies/chests drop 25% less Gold | Card removal and shop purchases more precious |
| 4 | Tight Belt | Start with 1 less potion slot | Use potions more aggressively, fewer to save |
| 5 | Ascender's Bane | Start with unremovable Curse | Dead draw every combat; prioritize deck thinning |
| 6 | Gloom | Fewer Rest Sites on map | Each campfire is more valuable; Smith vs Rest harder |
| 7 | Scarcity | Rare/Upgraded cards appear less in rewards | Must adapt to what you're offered |
| 8 | Tough Enemies | Enemies have more HP and defense | Relic scaling more important; must hunt elites |
| 9 | Deadly Enemies | Enemies deal more damage | Block generation and burst damage more critical |
| 10 | Double Boss | Two bosses back-to-back at end of Act 3 | Must build for sustained fights, not one-trick decks |

### Ascension Strategy Adjustments

- **Levels 1-3**: Hunt elites aggressively; treat HP as currency for strength gains
- **Level 4**: Use potions proactively during elite fights, not bosses
- **Level 5**: Prioritize card removal to thin deck against the permanent curse
- **Level 7+**: Focus on tight 20-card decks; build around what you find, not what you want
- **Level 8+**: Elites and relics become mandatory — passive scaling from relics is the only way to match enemy scaling
- **Level 10**: Deck must have a sustainable win condition, not a one-shot combo

---

## 11. Sources

### Comprehensive Guides
- [Mobalytics STS2 Beginner Guide](https://mobalytics.gg/slay-the-spire-2/guides/beginner-guide)
- [GAMES.GG Ascension Guide](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-ascension-guide/)
- [GAMES.GG Beginner Tips](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-beginner-tips-and-tricks/)
- [NeonLightsMedia Beginner's Guide: How to Survive Act 1](https://www.neonlightsmedia.com/blog/slay-the-spire-2-beginners-guide-survival)
- [NeonLightsMedia Ascension Levels 1-10](https://www.neonlightsmedia.com/blog/slay-the-spire-2-ascension-guide-levels)
- [GameRant Beginner Tips & Tricks](https://gamerant.com/slay-the-spire-2-best-tips-tricks-beginners/)
- [TheGamer 8 Beginner Tips](https://www.thegamer.com/slay-the-spire-2-6-beginner-tips-tricks-cards-best-characters-status-efects-guide/)
- [Pro Game Guides Beginner's Guide](https://progameguides.com/slay-the-spire-2/slay-the-spire-2-beginners-guide/)

### Events
- [TheGamer Complete Guide to Events](https://www.thegamer.com/slay-the-spire-2-events-guide-all-events-best-choices-strategy/)
- [Mobalytics Events Database](https://mobalytics.gg/slay-the-spire-2/encounters/events)
- [Destructoid All Events and Choices](https://www.destructoid.com/all-events-and-choices-in-slay-the-spire-2/)

### Relics
- [Mobalytics Relic Tier List](https://mobalytics.gg/slay-the-spire-2/tier-lists/relics)
- [Pro Game Guides Relics Tier List](https://progameguides.com/slay-the-spire-2/slay-the-spire-2-relics-tier-list/)
- [GAMES.GG Relics Tier List](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-relics-tier-list/)
- [GamerBlurb Boss Relics](https://gamerblurb.com/articles/slay-the-spire-2-boss-relics-full-list-and-best-picks)
- [SlashSkill Best Relics](https://www.slashskill.com/slay-the-spire-2-best-relics-every-relic-tier-listed-and-ranked/)

### Ancients
- [TheGamer Complete Guide to Ancients](https://www.thegamer.com/slay-the-spire-2-ancients-blessings-offerings-list-guide/)
- [Mobalytics Ancients Guide](https://mobalytics.gg/slay-the-spire-2/guides/ancients)
- [GAMES.GG Ancients Guide](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-ancients-guide/)
- [NeonLightsMedia Ancients Guide](https://www.neonlightsmedia.com/blog/slay-the-spire-2-all-ancients-relics-guide)

### Cards & Characters
- [Mobalytics Card Tier List](https://mobalytics.gg/slay-the-spire-2/tier-lists/cards)
- [Mobalytics Regent Guide](https://mobalytics.gg/slay-the-spire-2/characters/regent-guide)
- [Mobalytics Necrobinder Guide](https://mobalytics.gg/slay-the-spire-2/characters/necrobinder-guide)

### Elites & Bosses
- [GamerBlurb Elites Guide](https://gamerblurb.com/articles/slay-the-spire-2-elites-guide-every-elite-enemy-in-each-act)
- [Mobalytics Bosses Database](https://mobalytics.gg/slay-the-spire-2/encounters/bosses)
- [TposeGaming Bosses Guide](https://tposegaming.com/slay-the-spire-2-bosses/)

### New Mechanics
- [Mobalytics Enchantments Guide](https://mobalytics.gg/slay-the-spire-2/guides/enchantments)
- [GAMES.GG Enchantment Guide](https://games.gg/slay-the-spire-2/guides/slay-the-spire-2-enchantment-guide/)
- [XModHub New Mechanics Explained](https://www.xmodhub.com/info/xmod-blog/slay-the-spire-2-new-mechanics-guide/)

### Shops & Economy
- [AllThings.how Gold Economy Guide](https://allthings.how/slay-the-spire-2-gold-economy-every-way-to-stack-your-wallet/)
- [NeonLightsMedia Fake Merchant Guide](https://www.neonlightsmedia.com/blog/slay-the-spire-2-fake-merchant-guide)

### Quest Cards
- [Mobalytics Quest Cards Guide](https://mobalytics.gg/slay-the-spire-2/guides/quest-cards)
- [TheGamer Quest Cards Guide](https://www.thegamer.com/slay-the-spire-2-quest-cards-byrdonis-egg-spoils-map-lantern-key-explained-guide/)

### Alternate Acts
- [Mobalytics Alternate Acts Guide](https://mobalytics.gg/slay-the-spire-2/guides/alternate-acts)

### Community Discussions
- [Steam: Are we not supposed to fight elites?](https://steamcommunity.com/app/2868840/discussions/0/802341195824214578/)
- [Steam: The Special Path in Act 2](https://steamcommunity.com/app/2868840/discussions/0/802341528343304130/)

### Wiki
- [Slay the Spire Wiki — STS2 Main](https://slaythespire.wiki.gg/wiki/Slay_the_Spire_2:Main)
- [STS2 Wiki Unofficial](https://sts2.wiki/)
