# STS2 Strategy Reference

Consolidated from CharTyr STS2-Agent upstream documentation.
Used to populate system prompts and combat reasoning.

---

## General Strategy

### Core Principles
1. **HP is a resource, not a score.** Take calculated damage to deal more.
2. **Deck quality > deck size.** Skip mediocre rewards. Lean decks draw key cards more often.
3. **Front-load damage.** Kill enemies fast — reduce total incoming damage.
4. **Read intents.** Sleep/Buff → go all-out offense. Attack → balance block and damage. Debuff → usually offense turn.
5. **Planning ahead.** Consider future floors, boss difficulty, act structure.

### Combat Sequencing
1. Play 0-cost utility/setup cards FIRST.
2. Play skills before attacks — Slow stacks, Monologue Strength all reward this.
3. Play biggest attacks LAST to benefit from full buff/debuff stacking.
4. Check enemy HP — if you can kill this turn, skip blocking entirely.
5. Buff potions (Flex etc.) should be used BEFORE playing cards.

### Card Index Warning (CRITICAL)
Playing a card removes it from hand and shifts all higher indices down by 1.
- After playing index 2, what was index 3 becomes index 2.
- Re-check state between plays, or play highest index first.

### Map Pathing
- Elites give relics — fight when >70% HP.
- Rest before Boss if <80% HP.
- Unknown nodes are safer than Elites at medium HP.
- Shops with 100+ gold.
- Don't add cards just to add cards.

### Boss Fights
- Kill the leader, not the minions (Minion power: flee when leader dies).
- Use potions aggressively — they don't carry between acts.
- Boss fights scale over time — end them quickly.

### Potion Rules
- Don't hoard. Dying with full potions is the worst outcome.
- Buff potions on turns with multiple attacks.
- Fruit Juice (+5 Max HP permanent): use early in any combat.

---

## The Regent — Star Mechanic

Stars = secondary resource (shown as ★N cost). Required by powerful cards.

### Sources
- **Divine Right** (starting relic): 3 stars at combat start each fight.
- **Venerate+**: 1E → 3 stars
- **Gather Light**: 1E → 7 block + 1 star (strictly better Defend)
- **Solar Strike**: 1E → 8 dmg + 1 star
- **Shining Strike**: 1E → 6-8 dmg + 2 stars, returns to draw pile next cycle

### Key Star-Cost Cards
| Card | Cost | Effect |
|------|------|--------|
| Falling Star+ | 0E + 2★ | 11 dmg + Weak + Vulnerable. MVP. Play after skills. |
| Crescent Spear | 1E + 1★ | 15 + 2 per star-cost card in deck. Count carefully. |
| Reflect | 1E + 3★ | 17 block + reflects blocked dmg. Game-changing vs multi-attackers. |
| Particle Wall | 0E + 2★ | 9 block, returns to hand. Loop for massive block. |
| Radiate | 0E | 3 × (stars gained this turn) to ALL enemies. Play last. |
| Monologue | 0E | +1 Strength per card played this turn. Play FIRST. |
| Quasar+ | 0E + 2★ | Adds upgraded colorless to hand (not deck). Boosts Crescent count. |
| Tyranny | Power | Start of turn draw 1, exhaust 1. Strong vs. status-card enemies. |

### Combat Sequencing (Regent)
1. **Monologue FIRST** if in hand → every subsequent card = +1 Strength
2. **Star generators** (Venerate, Gather Light, Solar Strike) → unlock star cards
3. **Radiate** → play AFTER all star generation (hits = stars gained this turn)
4. **Falling Star+** → Weak/Vulnerable before big attacks
5. **Crescent Spear / Guiding Star** → biggest hits last

### Star Budget Planning
- Stars carry over between turns within a combat. Unspent stars persist.
- Stars do NOT carry between combats.
- Radiate counts stars GAINED this turn — Divine Right's 3 combat-start stars count on Turn 1.
- Tyranny exhaust: exhaust unplayable high-star-cost cards first (Reflect 3★, Astral Pulse 3★).
- Below ~15 HP with no block generators: block first, offense second.

### Slow Debuff (Enemy Power)
- Each card played makes enemy take 10% more Attack damage that turn.
- Against Slow enemies: play as many non-attack cards BEFORE attacks as possible.
- Radiate benefits enormously from high Slow stacks.

---

## Act 1 Boss: Kin Priest
- 190 HP + two Minion followers (~55-60 HP each)
- **Ignore followers — they flee when the Priest dies.**
- Followers: alternate Buff (+2 Strength) and Attack
- Priest: alternate Attack+Debuff (Frail/Weak) and Buff (+2 Strength)
- Reflect is very strong — reflects multi-enemy attacks
- Use Flex Potion + Monologue together for burst turns

## Act 2 Elite: Decimillipede
- Three segments (Front/Middle/Back) with Reattach: revives in 2 turns if any other segment alive
- Cannot permanently kill a segment while others live
- Strategy: whittle all segments down, then kill two simultaneously (AoE), then burst the third before others revive

## Act 2 Elite: Infested Prism
- Vital Spark: first attack damage each turn grants +1 energy → always include one attack
- Attack pattern: Turn 1 = 16, Turn 2 = 16 + block (~16), Turn 3+ = 9×3 = 27
- Apply Weak before each round of attacks (Falling Star+)
- Particle Wall loop ideal: Venerate+(3★) → Particle Wall × 3 (0E+2★ each, returns) → 27 block

---

## API Reference (Key Points)

Full API docs: CharTyr STS2-Agent upstream (localhost:8080)

### State Types
`monster` / `elite` / `boss` | `hand_select` | `combat_rewards` | `card_reward`
`map` | `rest_site` | `shop` | `event` | `card_select` | `relic_select` | `treasure` | `overlay` | `menu`

### Key Action Gotchas
- `proceed` does NOT work for events — use `choose_event_option` with the Proceed option index
- Card removal in shop is a separate item type (`card_removal`) — usually very high value
- `combat_select_card` vs `select_card`: former is in-combat hand select, latter is deck select screen
- Rewards: claim gold/potion/relic first, then card (opening card changes state to `card_reward`)
- Shop auto-opens inventory when state is queried; `proceed` auto-closes and exits
