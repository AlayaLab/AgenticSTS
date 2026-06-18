# The Regent — character support plan

## Context

The agent today plays The Silent well but treats every other character as a degraded Silent: prompts/guides/skill seeds are largely Silent-flavored, and the planner has no notion of any resource other than energy. **The Regent** is the next priority because it has a fundamentally different combat economy — a second persistent resource (Stars) that lives outside the per-round energy reset and that whole archetypes are built around. Without explicit support, the LLM has no consistent framing for star-spend tradeoffs and no Regent-specific strategy memory to draw on.

**Goal**: get the agent to a point where it can run an Act 1–3 attempt with The Regent on Ascension 0–10, making coherent decisions about (a) when to spend stars vs hold them, (b) which cards to add at reward/shop based on the deck's existing star economy, and (c) how to plan a turn that balances energy + star usage.

## What's already in place (verified)

The reconnaissance found a healthy foundation:

| Surface | Status |
|---|---|
| `normalize_character()` accepts `"Regent"` / `"The Regent"` / `"摄政王"` → `"the regent"` | ✅ `src/memory/models_v2.py:47-53` |
| Memory stores keyed by character — Regent gets fresh combat / route / deck / event guides | ✅ `src/memory/guide_store.py:33-36` |
| C# mod emits `combat.player.stars` (current count) | ✅ `Game/GameStateService.cs:3209, 3477, 6598` |
| C# mod emits per-card `star_cost` and `star_costs_x` | ✅ `Game/GameStateService.cs:3574-3577, 5320-5322` |
| `--character Regent` already routed through `_ensure_run_started` | ✅ `scripts/run_agent.py:839` |
| Divine Right registered with the "+3 Stars at combat start" hint | ✅ `src/brain/prompts/_relic_fmt.py:55-58` |

**Implication**: the wire-level data flow is already there. The work is mostly *prompt scaffolding + seed knowledge + planner awareness* — not parser or schema changes.

## What's missing

1. **Star resource is invisible in most prompts**. The C# mod emits `stars` but the prompt builders don't surface "Stars: N" the way they surface energy. The LLM is forced to fish the value out of the raw payload, and reasoning about a resource the prompt doesn't name is unreliable.
2. **Per-card star cost isn't rendered alongside energy cost**. The mod's `FormatCardCost` already does `1/★1` notation when both costs are present (we fixed this earlier), but Python's pile/hand/deck formatters don't always show it consistently.
3. **No Regent seed skills, no Regent deck guide, no Regent card notes** in `src/skills/seeds/`.
4. **Combat planner is star-blind**. The planner doesn't currently verify energy budget either (per the explorer report), but stars are *persistent* — a Regent agent that miscounts energy loses one turn; one that miscounts stars can soft-lock or burn its win condition. Worth handling.
5. **Reward / shop / card-select prompts** don't include a "deck star economy" snapshot, so the LLM has no signal to evaluate a star-providing vs star-consuming candidate against the existing deck's balance.
6. **Boss-strategy / route prompts** don't fold in the Regent's specific power curve (Acts that favor early star-stockpiling vs spend-heavy mid-act).
7. **Forge / Sovereign Blade is invisible to the agent.** Forge is the Regent's second flagship mechanic and is fundamentally unlike anything the Silent or generic-state prompt scaffolding handles:
   - **Sovereign Blade** is a 2-energy Colorless Token Attack (base 10 damage) that *cannot be in the deck normally* — it only enters the hand when a Forge card is played for the first time in a combat.
   - Each *subsequent* Forge play adds damage to **all copies** of the Sovereign Blade in play, hand, draw, discard, **and exhaust**. So Forge stacks compound across the entire combat — but only on whichever Sovereign Blade is currently "alive".
   - If the Sovereign Blade is exhausted or transformed and a *new* Forge is played, a fresh 10-damage Sovereign Blade spawns; **the previous Forge investment is lost**. Power cards like Seeking Edge and Sword Sage still apply to the new copy.
   - This creates a deck-state pseudo-resource (Sovereign Blade's *current* damage) that persists across rounds within a combat and is invisible until a Forge is played. The agent must (a) recognize when its deck is a "Forge deck" archetype, (b) order Forge plays *before* spending the Sovereign Blade for maximum value, (c) avoid exhausting/transforming the Sovereign Blade prematurely, and (d) value Forge-bearing cards proportional to expected total Forge stacks per combat — an evaluation that's archetype- and Act-dependent.

   None of this is currently surfaced. The mod *does* emit Sovereign Blade as a card in hand/discard/etc. (it's just a token card with `card_id == "sovereign_blade"`) and its `damage` field reflects the current Forged value, so the wire data is there — but no prompt narrates it, and no scoring rule values Forge cards differently than vanilla attacks.

## Approach (5 phases, deliver-in-order)

### Phase 1 — Visibility (~1–2 hrs, no LLM cost)

Make stars and per-card star costs visible in every prompt the LLM reads in combat / deck-building / shop / rewards. This is pure formatting; no logic change.

- **`src/brain/prompts/system.py` (COMBAT, COMBAT_BOSS)**: extend the resource-line template from `Energy: N/M` to `Energy: N/M | Stars: K` when `gs.character == "the regent"` (or unconditionally when stars > 0 — cleaner and helps any future star-using character).
- **`src/brain/prompts/_pile_fmt.py` + `_deck_fmt.py`**: when rendering a card, include `[N/★K]` when both costs are present, `[★K]` when star-only. The mod already emits this format inside `line` but our compact pile formatter only shows the name; extend `format_pile_compact` to optionally include cost.
- **`src/brain/prompts/hand_select.py` / `card_select.py` / `reward.py` / `shop.py`**: in any "deck snapshot" section, render each card's star cost when non-zero.
- **Update `src/brain/prompts/_relic_fmt.py:55-58`** Divine Right hint from "can play Star-cost cards early" to a more actionable line: `"+3 Stars at combat start. Stars persist across rounds; spend opportunistically on Star-cost cards but don't waste them on suboptimal targets when energy alone covers the line."`

**Verification**: launch with `--character Regent`, capture one full prompt sent to the LLM, confirm `Stars: K` appears in the combat resource header and at least one card shows `★N` notation.

### Phase 2 — Seed knowledge (~3–5 hrs, depends on quality of writing)

Create the Regent equivalents of the existing Silent seeds. Memory stores already key on `(key:character)` so these will load alongside Silent skills without conflict.

- **`src/skills/seeds/regent_a10_guide.json`** — mirror of `silent_a10_guide.json`. Cover: Act 1 priorities (build star floor), Act 2 (decide star archetype: spender vs hoarder), Act 3 boss matchups, key relics for Regent. ~800–1500 words.
- **`src/skills/seeds/regent_card_notes.json`** — mirror of `silent_card_notes.json`. Tier each Regent card with:
  - tier (S/A/B/C/D)
  - star economy: `"provider"` / `"consumer"` / `"both"` / `"neutral"`
  - one-line "why" + "synergy" + "anti-synergy"
  - This is the largest writing chunk; sourcing data from `data/knowledge/localization/eng/cards.json` (already loaded) for the canonical card list. Filter to Regent-pool cards by character key from the upstream cards DB.
- **`src/skills/seeds/regent_starting_deck.json`** (new): note how the starting deck's star floor works, which two starter Strikes are likely to be removed first, and which 1-energy card upgrades unlock the most star-spend lines.
- Optional: extract a Regent boss guide section into `src/skills/seeds/regent_boss_strategy.json` covering Act 1/2/3 boss matchups specifically (Architect, Bowlbug, Jaw Worm Avatar, etc.) with Regent-relevant prep advice.

**Verification**: `python -m scripts.inspect_memory` shows the Regent seeds loaded; `LocaleTranslator` already covers the entity names so the seeds can use English card/relic names verbatim.

### Phase 3 — Star-aware deck-building heuristics in prompts (~2–3 hrs)

Augment reward / shop / card-select prompts so the LLM gets an *explicit star-economy summary* of the current deck instead of having to infer it from the card list each call.

- **New helper** `src/brain/prompts/_star_economy_fmt.py`:
  - Takes a `RunState` deck (or `gs.run.deck`).
  - Walks each card, classifies it as `provider` / `consumer` / `both` / `neutral` using a small static table indexed by `card_id` (auto-generated from `regent_card_notes.json` so we maintain it in one place).
  - Emits a 3–4 line summary like:
    ```
    ## Deck star economy
    Providers (avg +1.2/play): 4 cards [Crown's Decree+, ...]
    Consumers (avg -1.0/play): 6 cards [Royal Edict, ...]
    Net per cycle: +0.5 stars (sustainable)
    Ratio: 0.67 (lean spender)
    ```
- **Wire into**: `reward.py` (when evaluating a card add), `shop.py` (same), `card_select.py` (transform/upgrade choice), `rest.py` (upgrade choice — upgrades often shift a card's star profile).
- **Gate**: only emit when `gs.character == "the regent"` to keep Silent prompts unchanged.

**Verification**: log a `card_reward` decision while running Regent and confirm the deck star economy block appears.

### Phase 4 — Combat planner star awareness (~3–4 hrs)

The planner today doesn't verify energy, but the system prompt's "use ALL your energy" rule plus the LLM's own arithmetic keeps energy plans coherent enough for Silent. Stars need stronger backing because (a) miscounted stars carry across turns, and (b) some Regent cards are X-star, where the model's count translates directly into damage / scaling.

Two-part addition:

1. **Pre-LLM hint** — in `src/brain/tool_preprocessor.py` (the existing pre-LLM hint pipeline), add a Regent-only hint that emits `"Stars before turn: K. After your planned plays, stars left: <computed if plan parses>"`. The pre-LLM hint is descriptive; the LLM can use it to sanity-check.
2. **Post-plan verification** — in `src/brain/plan_verifier.py` (the existing post-plan verifier — same shape as energy_check would be), add a `star_check` rule that simulates the plan's net star delta against the current count and flags `severity=high` if it goes negative. Wire into the existing `needs_replan` flow so a star-violating plan is rejected before execution.

Use the same star-classification table from Phase 3 (single source of truth: `regent_card_notes.json`) to compute deltas.

**Verification**: unit test `tests/test_plan_verifier_star_check.py` with a hand-built Regent CombatPlan that overspends stars; expect `needs_replan=True`. Then a smoke-mode run against a known fight (architect / bowlbug) and inspect the trace to confirm `star_check` runs.

### Phase 4.5 — Forge / Sovereign Blade awareness (~½–1 day)

Treat Forge as a third resource alongside energy + stars. Three small additions cover it; same pattern as star economy so we reuse the classification table mechanism.

**Static classification** (extend `regent_card_notes.json` schema with one extra field per card):
```json
{
  "name": "Tempering Strike+",
  "card_id": "tempering_strike",
  "tier": "A",
  "star_role": "neutral",
  "forge_role": "forge"  // "forge" | "blade_synergy" | "blade_buff" | null
}
```
- `forge`: card has the Forge keyword (creates / stacks the Sovereign Blade).
- `blade_synergy`: pays off when Sovereign Blade is in play (e.g. doubles its damage, retains it, fetches it).
- `blade_buff`: power card that buffs newly-Forged Sovereign Blades (Seeking Edge, Sword Sage).
- `null`: no Forge interaction.

**Combat prompt — Forge state block** (`src/brain/prompts/_forge_fmt.py`, new):
- Detect Sovereign Blade across `hand + draw + discard + exhaust` piles using `card_id == "sovereign_blade"`.
- Render a 2–4 line block in combat prompts:
  ```
  ## Sovereign Blade
  Status: in_hand (damage 14)
  Forge cards remaining this combat: 3 in deck (avg buff +2 each → projected 20 dmg)
  Buffs active: Seeking Edge (1), Sword Sage (0)
  Risk: don't exhaust or transform — would reset to 10 dmg.
  ```
- Wire into `system.py` COMBAT/COMBAT_BOSS templates after the resource header, gated on `gs.character == "the regent"` AND (Sovereign Blade present OR the deck contains a Forge card). Off-Regent Silent runs are unaffected.

**Deck-economy block extension** (Phase 3's `_star_economy_fmt.py` becomes `_regent_economy_fmt.py`): when in zh/Regent mode, add a Forge sub-section to the deck snapshot:
```
## Deck Forge profile
Forge cards: 5 (Tempering Strike+, ...)
Blade synergy: 2 (Royal Cut, ...)
Blade buffs: 1 (Seeking Edge)
Archetype: Forge-stack (heavy Forge, low spender mix)
```
The "Archetype" line lets reward/shop prompts evaluate candidates against the deck's identity, not just raw card power. Scoring heuristic for new card add: a Forge card in a Forge-stack deck is +1 tier; a Forge card in a deck with no blade-synergy is at base tier; a card that exhausts/transforms cards is *anti-tier* if a buffed Sovereign Blade is in play.

**Plan verifier — Sovereign Blade safety check** (`src/brain/plan_verifier.py`, extend the existing `star_check` from Phase 4):
- New `forge_safety_check` rule: if the current state contains a Sovereign Blade with `damage > 10` (i.e. has been Forged at least once) AND the proposed plan plays a card that exhausts or transforms a hand card AND that target is the Sovereign Blade, flag `severity=high` and force replan with a hint: `"Don't exhaust the buffed Sovereign Blade; consider another exhaust target or skip this Forge stack."`.
- Edge case: when the LLM *intentionally* exhausts an unbuffed Sovereign Blade to spawn a fresh one with new buff stacks, allow it (the verifier should only fire when current SB damage > 10 unless a Sword Sage / Seeking Edge will reapply).

**Verification**:
- Unit test `tests/test_plan_verifier_forge_safety.py` with synthetic states (Sovereign Blade at 14 damage in hand, plan exhausts it → expect needs_replan).
- Live smoke: a Regent run that picks up at least one Forge card; inspect the combat trace for the "Sovereign Blade" prompt block and confirm the LLM references it in `reasoning`.

### Phase 5 — End-to-end smoke + ascension progression (~1 hr)

- `python -m scripts.run_agent --steps 5000 --runs 1 --character Regent --ascension 0 --no-postrun --display-language zh`
- Confirm the agent:
  - sees stars in its prompt header,
  - picks at least one Regent card from a card_reward and reasons about star economy in `reasoning`,
  - completes Act 1 without a star-related stuck recovery,
  - emits `combat_plan` events whose summed star cost stays ≤ available stars,
  - on a combat where a Forge card is played, sees the "Sovereign Blade" prompt block and the LLM references its buffed damage in `reasoning`,
  - never plays an exhaust/transform card targeting a Forge-buffed Sovereign Blade unless explicitly justified.
- Run 3–5 short ladder runs at A0–A2 to make sure no regression for Silent. Then attempt A5 / A10.

## Critical files (all writes localized)

- `src/brain/prompts/system.py` — combat resource line + Sovereign Blade block hookup
- `src/brain/prompts/_pile_fmt.py`, `_deck_fmt.py` — star cost rendering
- `src/brain/prompts/_relic_fmt.py` — Divine Right hint refresh
- `src/brain/prompts/_regent_economy_fmt.py` (new) — combined star + Forge profile (was tentatively `_star_economy_fmt.py`)
- `src/brain/prompts/_forge_fmt.py` (new) — Sovereign Blade combat-state block
- `src/brain/prompts/{reward,shop,card_select,rest}.py` — wire deck-economy block
- `src/skills/seeds/regent_a10_guide.json` (new)
- `src/skills/seeds/regent_card_notes.json` (new) — schema includes `star_role` + `forge_role`
- `src/skills/seeds/regent_starting_deck.json` (new)
- `src/brain/tool_preprocessor.py` — Regent-only star hint + Forge state hint
- `src/brain/plan_verifier.py` — `star_check` rule + `forge_safety_check` rule
- `tests/test_plan_verifier_star_check.py` (new)
- `tests/test_plan_verifier_forge_safety.py` (new)

## Out of scope

- New *characters* beyond Regent (Necrobinder etc.) — same template will apply but each gets its own seeds.
- Card-pool filtering (`card_lookup.py` doesn't filter by character today; we don't need to change that — the game itself gates rewards/shop pools).
- Deep dynamic deck-building memory (the mistake-driven skill discovery loop will pick up Regent-specific lessons over time once we have seeds + visibility).
- Translating Regent-specific labels in mod prompts (already covered by the existing English-on-wire / locale-translator pipeline).

## Estimated effort

- Phase 1 (Visibility): ½ day
- Phase 2 (Seeds — now also covers Forge classification per card): 1 day thorough; 4 hrs minimal
- Phase 3 (Deck economy summary — star + Forge profile in one block): ½ day
- Phase 4 (Star planner verification): ½ day + tests
- **Phase 4.5 (Forge / Sovereign Blade awareness): ½–1 day** including the `_forge_fmt.py` block, the archetype-aware reward scoring tier-up rule, and the `forge_safety_check` verifier
- Phase 5 (Smoke + ladder): ½ day live testing

**Total ~3.5–4 days** to ship a credible Regent agent across both Star and Forge axes. Phase 1 alone still gets a 50–60% improvement at 5% of the effort and is the right first slice. Phases 4 and 4.5 are independently shippable; 4.5 only matters once a Forge card has been added to the deck, so the agent will benefit from earlier phases even before 4.5 lands.
