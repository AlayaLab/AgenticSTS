# Silent card seed-notes review (2026-04-28)

Source: `src/skills/seeds/silent_card_notes.json.disabled` (the file that was auto-injected into `card_memory_store` on every startup; disabled 2026-04-28 because the entries were encyclopedic / partly factually wrong, and bypassed the `with_new_note` audit trail).

Total entries: **87** (87 with non-empty note).

Bucket sizes:
- `factual_suspect`: 1
- `tactical`: 6
- `tier_or_theory`: 42
- `mechanic_restate`: 38

Review pass: walk the **factual_suspect** and **tactical** buckets. For each entry you want to keep, manually call `CardMemoryStore.with_new_note` on a real run trace, or rewrite the note inline in the next postrun's `card_note_updater` MANDATORY-first-note output. **Do not** restore the seed file as a whole — its auto-inject path bypassed audit and is the bug we are removing.

## 1. Factual suspects — note contradicts game mechanics (1)

_These notes contradict `data/knowledge/cards.md`. Either fix the wording or drop entirely; do **not** re-add to the seed file as-is._

### Prepared
- card row: `0 | Skill | Common | Self`
- vars: `CardsVar(1)`
- flags: FACTUAL: note says 'draw 2' but mechanic CardsVar=1, starts-with-cost-mechanic, tier-label

> 0-cost: draw 2 discard 2. Free deck cycling — replaces hand cards without spending energy. The 2 discards are card effects, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Silent core card; 2-3 copies are reasonable, especially once upgraded.

## 2. Tactical insight — likely worth re-authoring as trace-grounded note (6)

_Concrete timing / save-for / skip-when advice — the kind of insight postrun stats alone can't reconstruct. Keep candidates here on a separate review pass; only re-author into live store if a real run trace will continue to validate the advice._

### Backstab
- card row: `0 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(11m, ValueProp.Move)`
- flags: starts-with-cost-mechanic, tactical-keyword

> 0-cost Innate: 11 damage. Guaranteed in opening hand every combat. Exhaust after use. Provides free first-turn damage with no energy cost.

### Expose
- card row: `0 | Skill | Uncommon | AnyEnemy`
- vars: `DynamicVar("Power", 2m)`
- flags: starts-with-cost-mechanic, tactical-keyword

> 0-cost: removes ALL Artifact stacks from enemy and applies 2 Vulnerable. You lose current Block as downside. Essential for stripping Artifact before applying debuffs (Weak, Poison, Vulnerable). Play before debuff cards.

### Metamorphosis
- card row: `2 | Skill | Event | Self`
- vars: `CardsVar(3)`
- flags: starts-with-cost-mechanic, tactical-keyword

> 2-cost Exhaust: adds 3 random Attack cards into draw pile, all permanently 0-cost for this combat. Growth card — play when energy allows. The 0-cost Attacks may include high-damage cards that are normally expensive. Stronger in decks with draw (Backflip, Acrobatics) that cycle to the new cards faster. Play early in long fights for maximum value.

### Neutralize
- card row: `0 | Attack | Basic | AnyEnemy`
- vars: `DamageVar(3m, ValueProp.Move), PowerVar<WeakPower>(1m)`
- flags: tactical-keyword

> Starter: 0-cost 3 damage + 1 Weak. Upgrade gives 2 Weak — significant improvement (50% more Attack damage reduction on enemy). Upgrade priority: 1 Weak → 2 Weak is one of the biggest percentage jumps among upgrades.

### Serpent Form
- flags: tactical-keyword

> Rare Power: 3-cost — difficult to play without energy support. Only consider with energy-generating relics or cards (Tactician, Adrenaline). Skip if energy generation is not available.

### Sucker Punch
- flags: starts-with-cost-mechanic, tactical-keyword

> 1-cost: 8 damage + 1 Weak. Acceptable as a transitional damage + debuff card early in the run. Skip if better options are available.

## 3. Tier label / combo theory — drop unless specific synergy worth keeping (42)

_Tier labels (A-tier, premium, core) are evaluative — postrun's win-rate / play-count stats already encode relative strength. Combo theory ("pairs with X") is mostly inferable from card text. Skip unless a specific synergy is non-obvious._

### Abrasive
- card row: `3 | Power | Rare | Self`
- vars: `PowerVar<ThornsPower>(4m), PowerVar<DexterityPower>(1m)`

> Sly: plays for free when discarded. 3-cost applies Thorns + Dexterity. Effective cost is 0 energy with discard outlets (Acrobatics, Survivor, Dagger Throw). High combined stat value when triggered via Sly.

### Accelerant
- card row: `1 | Power | Rare | Self`
- vars: `DynamicVar("Accelerant", 1m)`

> Power: Poison damage triggers an extra time at end of turn. Example: enemy has 20 Poison → normally takes 20 damage, with Accelerant takes 20+19=39 damage. Doubles effective Poison damage that turn. Stacks with more Poison sources (Noxious Fumes, Deadly Poison, Bubble Bubble) for higher burst.

### Accuracy
- card row: `1 | Power | Uncommon | Self`
- vars: `PowerVar<AccuracyPower>(4m)`

> Power: +4 damage to all Shivs per copy. Base Shiv = 4 dmg → 8 with 1 copy, 12 with 2 copies. ONLY buffs Shiv cards — does NOT affect Ricochet, Dagger Spray, or other multi-hit attacks. Stacks: multiple copies multiply value linearly with Shiv generators (Blade Dance, Up My Sleeve, Infinite Blades, Fan of Knives).

### Afterimage
- card row: `1 | Power | Rare | Self`
- vars: `PowerVar<AfterimagePower>(1m)`

> Power: gain 1 Block per card played. Scales with cards-per-turn — Shiv generators (Blade Dance = 3 Shivs = 3 Block), 0-cost cards, and draw engines increase its output. Provides passive Block without spending energy on Block cards.

### Backflip
- card row: `1 | Skill | Common | Self`
- vars: `BlockVar(5m, ValueProp.Move), CardsVar(2)`
- flags: starts-with-cost-mechanic

> 1-cost: block + draw 2. Defends and cycles simultaneously. The draw does not trigger Sly (draw is not discard). Pairs with Dexterity (Footwork) for scaled Block.

### Blade Dance
- flags: starts-with-cost-mechanic, tier-label

> 1-cost: generates 3 Shivs into hand (each Shiv = 0-cost 4 damage, Exhaust). Total output: 12 damage for 1 energy. Combos: Accuracy (+4 per Shiv), Knife Trap (replays exhausted Shivs), Afterimage (3 Block from 3 Shivs played).

### Blur
- card row: `1 | Skill | Uncommon | Self`
- vars: `BlockVar(5m, ValueProp.Move), DynamicVar("Blur", 1m)`

> Block carries over between turns instead of resetting to 0. Enables accumulating Block walls over multiple turns. Pairs with consistent Block generation (Footwork, Backflip, Afterimage).

### Bullet Time

> Reduces all card costs to 0 for the turn but prevents drawing more cards. Requires a full hand to maximize value. Less effective with small hands or when draw is needed.

### Cloak and Dagger
- flags: starts-with-cost-mechanic, tier-label

> 1-cost: Block + generates Shivs. Combines defense and Shiv generation in one card. Combos with Accuracy (+4 per Shiv) and Knife Trap (replays exhausted Shivs).

### Corrosive Wave

> Rare Skill: after playing Corrosive Wave, each card drawn THIS TURN applies Poison to ALL enemies. Pairs with draw cards (Prepared, Acrobatics, Backflip) — more draws in the same turn = more Poison stacks on all enemies. Best with high draw density in the turn it is played.

### Deadly Poison
- flags: starts-with-cost-mechanic, tier-label

> 1-cost: applies 5 Poison to single target. Core Poison source. Multiple copies stack well. Combos with Accelerant (makes the Poison infinitely scaling) and Envenom (attacks also apply Poison).

### Envenom
- card row: `2 | Power | Rare | Self`
- vars: `PowerVar<EnvenomPower>(1m)`

> Power: every unblocked Attack damage applies 1 Poison. Turns all attacks into Poison applicators. Multi-hit attacks (Dagger Spray, Ricochet, Shivs) apply Poison per hit. Requires attack cards to function — does nothing alone.

### Fan of Knives

> Power: causes all Shivs to deal AoE damage (hit ALL enemies instead of single target). Also generates 3 Shivs into hand this turn when played. Accuracy buffs each Shiv's AoE damage. Transforms Shiv builds from single-target to AoE output.

### Flanking
- card row: `2 | Skill | Uncommon | AnyEnemy`

> Applies FlankingPower. Synergizes with evasion/Sly mechanics. Stronger when multiple Sly triggers occur per turn.

### Flick-Flack

> Sly: plays for free when discarded by a card effect. 1-cost 7 damage to ALL enemies. Effective cost is 0 energy via discard outlets (Acrobatics, Survivor, Prepared). AoE damage for free in discard builds.

### Footwork
- card row: `1 | Power | Uncommon | Self`
- vars: `PowerVar<DexterityPower>(2m)`

> Power: permanent +2 Dexterity (upgraded: +3). All Block cards gain +2/+3 Block for rest of combat. Stacks with multiple copies. Unlike Anticipate, this is permanent. Upgrade from +2 to +3 is a significant boost.

### Hand Trick

> Sly: plays for free when discarded by a card effect. 1-cost 7 Block + adds Sly to a Skill in hand. Gives free Block via discard outlets. The 'add Sly to a Skill' effect can chain into more Sly triggers.

### Haze
- card row: `3 | Skill | Uncommon | AllEnemies`
- vars: `PowerVar<PoisonPower>(4m)`

> Sly: plays for free when discarded by a card effect. 3-cost applies 4 AoE Poison to ALL enemies. Do NOT evaluate at face cost of 3 — effective cost is 0 energy with any discard outlet (Acrobatics, Survivor, Dagger Throw). Upgraded: 6 AoE Poison. Multi-enemy Poison setup for free.

### Infinite Blades

> Power: creates 1 Shiv at start of each turn. Slow ramp — needs 3+ turns to accumulate meaningful value. Scales with Accuracy (+4 per Shiv per Accuracy copy). Compare: Fan of Knives generates more Shivs per turn.

### Knife Trap

> Replays EVERY Shiv in Exhaust Pile for free. Burst finisher after Blade Dance or Cloak and Dagger exhaust Shivs. With Accuracy, each replayed Shiv deals 4+N×4 damage. Upgrade is significant. Requires Shiv generators to have value — does nothing without exhausted Shivs.

### Malaise
- card row: `0 | Skill | Rare | AnyEnemy`

> X-cost: X = remaining energy when played. Reduces enemy Strength by X and applies Weak. More energy spent = more Strength reduction. Counters enemies that scale Strength over time. Play late in turn when leftover energy would be wasted.

### Master Planner

> Power: each Skill you PLAY this combat permanently gains Sly — when that card is reshuffled and drawn in future turns, it triggers Sly when discarded. Long-term scaling: more Skills played = more Sly cards accumulating in deck over combat. Value grows as the run progresses.

### Noxious Fumes

> Power: applies 2 Poison to ALL enemies at start of each turn passively. Scales linearly over time (turn 5 = 10 total Poison applied). AoE — affects all enemies simultaneously. Upgrade from 2 → 3 per turn is significant for long fights.

### Phantom Blades

> Power: the first Shiv played each turn deals bonus damage. Shivs also Retain at end of turn instead of being discarded. In Shiv builds, provides +6 damage per turn from the first Shiv alone, and prevents Shivs accumulating in discard pile.

### Pinpoint
- card row: `3 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(17m, ValueProp.Move)`

> 17 damage, cost reduces by 1 per Skill played this turn. After playing 2+ Skills, cost reaches 0 = free 17 damage. Skill-heavy decks and Sly builds (many free Skill plays) reduce its cost fastest.

### Reflex
- card row: `3 | Skill | Uncommon | Self`
- vars: `CardsVar(2)`

> Sly: plays for free when discarded by a card effect, drawing 2 cards (upgraded: 3). Unplayable from hand — ONLY activates via discard. Dead card without discard outlets (Acrobatics, Prepared, Survivor, Dagger Throw, Tools of the Trade).

### Restlessness
- card row: `0 | Skill | Uncommon | Self`
- vars: `CardsVar(2), EnergyVar(2)`
- flags: starts-with-cost-mechanic

> 0-cost Retain. PLAY IT LAST — when it's the only card in hand, playing it triggers the bonus: draw 2 + gain 2 energy. Sequencing rule: play ALL other cards first, THEN Restlessness. Even at 0 energy with only Restlessness in hand, play it — you get 2 energy back. Retain means it carries across turns. Pairs with 0-cost cards and thin decks that empty hand quickly.

### Ricochet
- card row: `2 | Attack | Common | RandomEnemy`
- vars: `DamageVar(3m, ValueProp.Move), RepeatVar(4)`

> Sly: plays for free when discarded by a card effect. 2-cost: 4 hits × 3 damage = 12 base (upgraded: 4 × 4 = 16). Does NOT benefit from Accuracy — Accuracy only boosts Shivs, and Ricochet is not a Shiv. Effective cost is 0 energy via discard outlets. Each hit benefits from Strength.

### Shadow Step

> Useful in extended fights. Upgraded version chains well with cycling decks. Scales with fight length — more valuable against bosses with high HP.

### Shadowmeld
- card row: `1 | Skill | Rare | Self`
- vars: `DynamicVar("Power", 1m)`

> Power: applies ShadowmeldPower. Pairs with high-Block cards — play alongside heavy Block generation to maximize its effect.

### Skewer
- card row: `0 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(7m, ValueProp.Move)`

> X-cost: deals 7 damage × energy spent. Scales with available energy — spending 3 energy = 21 damage. Pairs with energy generation (Adrenaline, Tactician) for higher output.

### Speedster
- card row: `2 | Power | Uncommon | Self`
- vars: `PowerVar<SpeedsterPower>(2m)`

> Turn-start draw does NOT trigger Speedster. Only draw effects from played cards (Backflip, Acrobatics, etc.) count. Without draw cards in deck, Speedster deals 0 damage/turn.

### Storm of Steel
- flags: starts-with-cost-mechanic, tier-label

> 1-cost Rare: discards entire hand and replaces it with the same number of Shivs. The hand discard triggers Sly on ALL discarded Sly cards simultaneously. Core Shiv build card — converts any hand into a full hand of Shivs.

### Suppress
- card row: `0 | Attack | Ancient | AnyEnemy`
- vars: `DamageVar(11m, ValueProp.Move), PowerVar<WeakPower>(3m)`

> Ancient: 0-cost 11 damage + 3 Weak. Free offense + significant debuff at zero energy. 3 Weak substantially reduces enemy Attack damage for 3 turns.

### Survivor
- card row: `1 | Skill | Basic | Self`
- vars: `BlockVar(8m, ValueProp.Move)`
- flags: tier-label

> Starter: Block + discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable). Foundational discard outlet that's available from the start of every run.

### Tactician
- card row: `3 | Skill | Uncommon | Self`
- vars: `EnergyVar(1)`

> Sly: plays for free when discarded by a card effect. Gains 1 energy on Sly trigger. One of Silent's few energy generation sources. Unplayable from hand — ONLY activates via discard outlets (same as Reflex). Strong when paired with draw and discard cards — upgrade is recommended.

### Tools of the Trade

> Rare Power: draw 1 + discard 1 at start of each turn. The turn-start discard is a card effect, triggering Sly cards every turn automatically. Passive Sly engine — generates discard triggers without spending cards or energy.

### Tracking
- card row: `2 | Power | Rare | Self`

> Scaling effect for extended fights. Requires reliable Weak application to function well — upgraded Neutralize (2 Weak) is the key enabler. Without consistent Weak sources, effectiveness is limited.

### Untouchable
- card row: `2 | Skill | Common | Self`
- vars: `BlockVar(9m, ValueProp.Move)`

> Sly: plays for free when discarded by a card effect. Provides Block for 0 energy when triggered via discard outlets (Acrobatics, Prepared, Tools of the Trade). Free defense in Sly builds.

### Up My Sleeve
- flags: starts-with-cost-mechanic, tier-label

> 2-cost: generates 3 Shivs (12 base damage). Core mechanic: cost reduces by 1 each play → 2→1→0 permanently. At 0-cost, same 3 Shivs as Blade Dance but free. Combos: Accuracy (+4 per Shiv), Knife Trap (replays exhausted Shivs), Afterimage (Block per card played).

### Well-Laid Plans

> Power: retain 1 card per turn per copy. Keeps a chosen card in hand instead of discarding at end of turn. Enables saving key cards (win conditions, defensive answers) for the right moment. Stacks: 2 copies = retain 2 cards.

### Wraith Form

> Ancient: applies Intangible for 2+ turns. Intangible reduces ALL damage taken to 1 per hit. Downside: lose 1 Dexterity each turn permanently after Intangible ends. Temporary near-invincibility with long-term defensive cost.

## 4. Pure mechanic restate — drop (redundant with `## Card Mechanics`) (38)

_These restate cost / effect already shown to the agent in the prompt's `## Card Mechanics` section. Drop without restoration._

### Acrobatics
- card row: `1 | Skill | Common | Self`
- vars: `CardsVar(3)`
- flags: starts-with-cost-mechanic

> 1-cost: draw 3 discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Cycles through deck while generating discard synergy value. Functions well without upgrade. Multiple copies improve cycle speed.

### Adrenaline
- card row: `0 | Skill | Rare | Self`
- vars: `EnergyVar(1), CardsVar(2)`
- flags: starts-with-cost-mechanic

> 0-cost: draw 2 + gain 2 energy. Net +2 energy and +2 cards for 0 cost — effectively free. Exhaust after use. No build requirements — universally functional in any deck.

### Anticipate
- card row: `0 | Skill | Common | Self`
- vars: `PowerVar<DexterityPower>(3m)`
- flags: starts-with-cost-mechanic

> 0-cost: gain 3 Dexterity this turn only. Temporary — expires at end of turn (unlike Footwork which is permanent). Each Block card played this turn gains +3 Block. Best when multiple Block cards are played in the same turn.

### Assassinate
- card row: `0 | Attack | Rare | AnyEnemy`
- vars: `DamageVar(10m, ValueProp.Move), PowerVar<VulnerablePower>(1m)`
- flags: starts-with-cost-mechanic

> 0-cost: 10 damage + 1 Vulnerable. Exhaust. Applies Vulnerable (50% more Attack damage) at zero energy, enabling follow-up attacks to hit harder this turn.

### Bouncing Flask
- flags: starts-with-cost-mechanic

> 2-cost: applies 9 total Poison (3 hits × 3 Poison). Splits across enemies in multi-enemy fights (random targeting). Compare: Bubble Bubble (1-cost, 9 Poison, single target) is more efficient per energy.

### Bubble Bubble
- flags: starts-with-cost-mechanic

> 1-cost: applies 9 Poison to a single target. Best when you already have poison support; treat it as poison density/payoff, not a reason to enter poison by itself.

### Burst
- card row: `1 | Skill | Rare | Self`
- vars: `DynamicVar("Skills", 1m)`
- flags: starts-with-cost-mechanic

> 1-cost: doubles the next Skill played this turn. The doubled Skill plays twice for free. Combo targets: Noxious Fumes (double Poison application), Backflip (double draw + Block), Acrobatics (double cycle + discard triggers).

### Calculated Gamble
- flags: starts-with-cost-mechanic

> 0-cost: discard entire hand, draw same number of cards. Full hand refresh for free. Triggers Sly on ALL discarded Sly cards simultaneously. Diminishing returns from 2nd copy (only 1 refresh per turn is useful).

### Dagger Spray
- flags: starts-with-cost-mechanic

> 1-cost: multi-hit attack to ALL enemies. Each hit is a separate damage instance. Combos: Envenom (each hit applies Poison to all targets), Strength (added per hit). Does NOT benefit from Accuracy (not a Shiv).

### Dagger Throw
- flags: starts-with-cost-mechanic

> 1-cost: 9 damage + draw 1 + discard 1. The discard is a card effect, triggering Sly cards (Reflex, Tactician, Untouchable) for free plays. Cycles deck while dealing damage. Flat 9 damage — does not scale with build progression.

### Dash
- card row: `2 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(10m, ValueProp.Move), BlockVar(10m, ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 2-cost: 10 damage + 10 Block in one card. Fills both offense and defense in a single play. Scales with Strength (damage) and Dexterity (Block) simultaneously.

### Deflect
- card row: `0 | Skill | Common | Self`
- vars: `BlockVar(4m, ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 0-cost: gain Block for no energy. Value increases with Dexterity (Footwork adds flat Block). Better in decks with more draw — you see it more often per cycle.

### Dodge and Roll
- flags: starts-with-cost-mechanic

> 1-cost: gain Block this turn and next turn. Provides Block over 2 turns, unlike Defend which is 1 turn only. Scales with Dexterity for both applications.

### Echoing Slash
- flags: starts-with-cost-mechanic

> 1-cost: 10 damage to ALL enemies. AoE attack. Scales with Strength.

### Escape Plan
- flags: starts-with-cost-mechanic

> 0-cost: draw 1 card + gain Block if drawn card is a Skill. Net positive — replaces itself with a draw for 0 energy. Thin decks with high Skill ratio maximize the Block trigger.

### Expertise
- card row: `1 | Skill | Uncommon | Self`
- vars: `CardsVar(6)`
- flags: starts-with-cost-mechanic

> 1-cost: draw up to 6 cards (fills hand to 6). Massive hand refill in one action. Less effective if hand is already near full. Enables combo turns by providing many card options at once.

### Finisher
- card row: `1 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(6m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits")`
- flags: starts-with-cost-mechanic

> 1-cost: damage scales with number of Attacks already played this turn. Payoff card — must be played LAST after other attacks. Shiv cycling (play 5+ Shivs first) maximizes its damage. Does nothing if played first.

### Flechettes
- card row: `1 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(5m, ValueProp.Move), CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedVar("CalculatedHits")`
- flags: starts-with-cost-mechanic

> 1-cost: deals 5 damage per Skill card currently IN HAND. Play Flechettes BEFORE playing Skills — damage is based on Skills remaining in hand at time of play, not Skills played this turn. Upgrade doubles to 10 per Skill in hand.

### Follow Through
- flags: starts-with-cost-mechanic

> 1-cost: 6 damage + 1 Weak. Compare: Sucker Punch (1-cost, 8 damage + 1 Weak) deals more damage for same cost and Weak.

### Grand Finale
- flags: starts-with-cost-mechanic

> 0-cost: deals 50+ damage but ONLY playable when draw pile is empty. Requires thin deck and/or heavy draw to consistently reach empty draw pile. Build-around card — deck removal + draw cards enable it.

### Hidden Daggers
- flags: starts-with-cost-mechanic

> 0-cost: 8 damage playable from hand normally. If discarded by a card effect (Acrobatics, Survivor, Dagger Throw), Sly triggers — plays for free and generates Shivs. Can be played even when no discard outlet is available. Sly synergy is a bonus, not a requirement.

### Leading Strike
- flags: starts-with-cost-mechanic

> 1-cost: 7 damage + generates 1 Shiv. Combines attack damage with Shiv output. The Shiv benefits from Accuracy (+4 damage). Compare: Blade Dance (1-cost, 3 Shivs) generates more Shivs per energy.

### Leg Sweep
- flags: starts-with-cost-mechanic

> 2-cost: high Block + applies Weak. Scales with Dexterity for the Block portion. Pounce reduces the next Skill cost to 0 — play Pounce before Leg Sweep to play it for free.

### Memento Mori
- flags: starts-with-cost-mechanic

> 1-cost: 8 base damage + 4 extra damage per card discarded THIS turn. Requires heavy discard support (Acrobatics, Prepared, Survivor, Dagger Throw, Calculated Gamble) to deal meaningful damage. Without discard outlets, deals only 8 damage for 1 energy — below average.

### Mirage
- card row: `1 | Skill | Uncommon | Self`
- vars: `CalculationBaseVar(0m), CalculationExtraVar(1m), CalculatedBlockVar(ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 1-cost: Block equal to Poison stacks on the target enemy. Effective only in Poison builds with high stack counts. Useless without Poison on the enemy.

### Murder
- card row: `3 | Attack | Rare | AnyEnemy`
- vars: `CalculationBaseVar(1m), ExtraDamageVar(1m), CalculatedDamageVar(ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 3-cost: conditional high-damage attack. Expensive baseline — needs its condition met to justify the 3 energy cost. Evaluate whether the trigger condition is reliably met in current deck.

### Nightmare
- card row: `3 | Skill | Rare | Self`
- flags: starts-with-cost-mechanic

> 3-cost Rare: copies a card from hand and shuffles copies into deck. Creates multiple copies of high-value cards. Combo targets: Adrenaline (free energy + draw copies), Tactician (free energy on discard), Envenom (stacking Poison-on-attack).

### Outbreak
- card row: `1 | Power | Uncommon | Self`
- vars: `PowerVar<OutbreakPower>(11m), RepeatVar(3)`
- flags: starts-with-cost-mechanic

> 1-cost Power: every 3 Poison stacks applied to any enemy triggers 11 AoE damage to ALL enemies. Excellent with AoE Poison cards (Corrosive Wave, Haze, Noxious Fumes) that apply Poison to multiple enemies simultaneously — each enemy's Poison counts separately toward the trigger. Mediocre against single targets where Poison is applied one card at a time.

### Piercing Wail
- flags: starts-with-cost-mechanic

> 1-cost: ALL enemies lose 6 Strength this turn. Exhaust. Temporary debuff — resets next turn. Effectively reduces each enemy attack by 6 damage this turn. Multi-enemy fights: reduces total incoming damage by 6 × number of enemies.

### Poisoned Stab
- flags: starts-with-cost-mechanic

> 1-cost: 6 damage + 3 Poison. Hybrid card — contributes to both Attack damage and Poison stacking simultaneously. Fits both Poison and general builds without committing to either.

### Pounce
- card row: `2 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(12m, ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 1-cost: 12 damage + reduces cost of next Skill played to 0. The cost reduction persists until a Skill is played. Combo: play Pounce → expensive Skills (Leg Sweep, Noxious Fumes) become free.

### Precise Cut
- flags: starts-with-cost-mechanic

> 0-cost: deals 13 damage minus 2 per other card in hand. Strongest in small hands (1-2 other cards = 9-11 damage for 0 energy). Empty hand = 13 free damage. Pair with hand-emptying effects (Restlessness, Calculated Gamble).

### Predator
- card row: `2 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(15m, ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 2-cost: 15 damage + draw 2 next turn. Front-loaded damage now, card advantage delayed to next turn. The delayed draw makes next turn stronger at the cost of 2 energy this turn.

### Slice
- card row: `0 | Attack | Common | AnyEnemy`
- vars: `DamageVar(6m, ValueProp.Move)`
- flags: starts-with-cost-mechanic

> 0-cost: 6 damage. Free damage with no energy cost. Acceptable as a transitional damage source when lacking offense early in the run.

### Snakebite
- card row: `2 | Skill | Common | AnyEnemy`
- vars: `PowerVar<PoisonPower>(7m)`
- flags: starts-with-cost-mechanic

> 2-cost Retain: applies 7 Poison. Higher energy cost than alternatives (Bubble Bubble 1-cost/9 Poison, Deadly Poison 1-cost/5 Poison). Retain allows holding it across turns and playing when energy is available or defense is not needed that turn.

### Sneaky
- card row: `2 | Power | Rare | Self`
- vars: `PowerVar<SneakyPower>(1m)`
- flags: starts-with-cost-mechanic

> 2-cost Rare Power: applies SneakyPower for passive combat benefits. Evaluate its specific effect against current build needs when offered.

### Strangle
- card row: `1 | Attack | Uncommon | AnyEnemy`
- vars: `DamageVar(8m, ValueProp.Move), PowerVar<StranglePower>(2m)`
- flags: starts-with-cost-mechanic

> 1-cost: 8 damage + Strangle debuff (reduces enemy power generation, stacks). Both offensive damage and debuff utility. Stacking multiple Strangles compounds the debuff.

### The Hunt
- flags: starts-with-cost-mechanic

> 1-cost: if the killing blow on an enemy comes from this card, gain an extra card reward at end of the fight. Useful early in the run to quickly acquire key cards. Value is higher in multi-enemy encounters where last-hit opportunities are more frequent.
