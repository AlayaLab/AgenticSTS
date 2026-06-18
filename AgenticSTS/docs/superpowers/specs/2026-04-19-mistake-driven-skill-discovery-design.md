# Mistake-Driven Skill Discovery Design

**Date:** 2026-04-19
**Owner:** AgenticSTS Contributors
**Status:** proposed
**Replaces (partially):** `src/skills/cohort_discovery.py`, `src/skills/hypothesis_store.py`, `src/skills/evidence.py`

---

## 1. Motivation

### 1.1 Today's symptom

Runs on 2026-04-19 produced 94 new skills across ~5 runs (≈20 skills/run). Agent battle performance was poor. Initial hypothesis: skill explosion → prompt bloat → worse decisions.

Investigation showed the causal chain is more subtle:

- Cohort-produced skills enter at confidence 0.48; older seed and discovery skills sit at 0.60–0.99.
- `enforce_category_caps(max=15)` sorts ascending by confidence and deactivates the lowest → new cohort skills die immediately after promotion.
- Only **1** of today's 94 skills was actually injected into any live prompt.
- Therefore today's poor battle performance is **not directly** caused by skill injection. But generating 20 skills/run that instantly deactivate is still a broken pipeline that:
  - wastes postrun LLM tokens,
  - pollutes `skills.json` with inactive noise,
  - defers (or permanently hides) real improvements behind cap churn.

### 1.2 Quality audit of the 94 cohort skills

Inspecting a random sample:

- **~70%** were per-enemy playbooks ("Seapunk handling", "Punch Construct approach") that **duplicate information the live agent already sees** via intent-display + card text + relic descriptions → zero counterfactual value, pure token waste.
- **~15%** were turn-specific prescriptions ("vs X turn 1, play card Y") that are **unreproducible** because hand draws are RNG — the trigger fires but the prescribed action is literally uncallable.
- **~15%** had genuine strategic insight but were buried under the above noise.

### 1.3 Root cause — and the mismatch

Current cohort discovery is **win-pattern-driven**:
```
cluster low-loss episodes → what did agent do in these? → that becomes a skill
```

This produces *descriptive* skills ("how this fight typically gets won"). Descriptive content belongs in `combat_guide` / `CombatEpisode` memory — not in the skill layer, which exists to correct suboptimal play.

The skill layer must be **mistake-driven**:
```
find episodes where agent underperformed → was the mistake fixable? →
  was a better play NOT obvious from game rules alone? →
    skill = prescriptive rule that would steer next occurrence
```

This is the **counterfactual test**: a skill has value iff the agent would play *wrongly* without it AND *correctly* with it. If the agent already gets it right from the game mechanics alone, the skill is noise.

### 1.4 Separation of concerns (post-redesign)

| Layer | Role | Source signal |
|---|---|---|
| `combat_guide` (memory) | **Descriptive**: *"how a fight against X typically unfolds"* — turn-by-turn rhythm, intent pattern, typical safe/pressure windows | aggregated from **won** or low-loss episodes |
| `skill_library` | **Prescriptive**: *"how to fix a specific mistake pattern"* — one actionable correction tied to a round where HP was lost | **mistake-triggered** critic verdict, one candidate per over-baseline combat |

**Hard boundary rule (enforced in critic prompt §3.2 and validator §3.4):**

A skill candidate is REJECTED if its content is pure turn-by-turn description of an encounter (e.g. *"Sewer Clam attacks on odd turns, buffs on even — block on attack, output on buff"*). Such knowledge belongs in `combat_guide`, not in `skill_library`. A skill MUST be a concrete correction rule that fires when a specific precondition is met AND changes the agent's default behavior.

Litmus test for the critic: *"If the agent had this skill in its prompt on the failing round, would it have picked a DIFFERENT card or target than what it actually played?"* If no — it's a guide, not a skill.

---

## 2. Data Layer

### 2.1 Mistake filter — episode selection

For each `CombatEpisode` in the current run, compute two baselines; an episode enters the mistake-candidate set if **either** baseline is exceeded by its respective delta.

| Name | Definition | Source |
|---|---|---|
| **Baseline A** (per-enemy) | `median(loss_ratio)` over historical episodes for the same `enemy_key_lookup(enemy)` (all acts, all characters) | `combat_store.get_by_enemy(enemy_key)` (existing) |
| **Baseline B** (pool) | `mean(loss_ratio)` over same `act × combat_type × character`, most recent 10, excluding current run | `combat_store.recent_by_act_type(act, combat_type, character, limit=10, exclude_run_id)` (**new**) |

`loss_ratio = total_damage_taken / max(hp_before, 1)` (already in `cohort_utils.loss_ratio`, migrated to `mistake_discovery.py`).

Delta thresholds (`δ_enemy`, `δ_pool`) derive from `combat_quality` quality thresholds (clean 0.05 for monster, 0.10 elite, 0.20 boss). Concretely:
- `δ_enemy = δ_pool = 0.10` for monster, `0.15` for elite, `0.20` for boss.

Sample-count gating:
- Baseline A requires ≥3 historical episodes; otherwise A is inactive for this check.
- Baseline B requires ≥3 episodes in the pool; otherwise B is inactive.
- If both inactive → episode is **not** a mistake candidate (insufficient prior data).

Win/loss is **not** a gate. A lost episode can trigger on either baseline (or both). A won episode with high `loss_ratio` can also trigger.

### 2.2 Round snapshot — context for critic

The critic LLM receives the same information the live agent saw. Field list derived from actual live prompts in `logs/run_20260419_161622_c3915aa9.jsonl`:

```
## Combat Start
encounter_type: monster|elite|boss
act: int | floor: int
character: silent | hp_before: 56/70
gold: int | potion_slots: used/max

## Enemies (at combat start)
- <name> [index=i]: HP n/max

## Current Deck (N cards)
  [Attack] Strike x5, Neutralize(cost=0), ...
  [Skill] Defend x5, Survivor(cost=1), ...
  [Curse] Ascender's Bane(cost=-1), ...

## Relics
- <name> — <description>
- ...

## Card Mechanics (subset referenced this combat)
  <card_name>: <effect text>    # from GameKnowledge.card_lookup, only cards
                                # appearing in deck/hand/discard this combat

## Per-Round Trace
### Round 1
State: Energy e/max, HP h/max, Block b
Hand: <card_name>[, ...] (N playable)
Piles: Draw n | Discard n | Exhaust n
Usable Potions: <potion_name>[, ...]
Enemy intents: <enemy> → <parsed_intent>
Incoming: d (after block: d)
Agent plan: [<card>→<target>, ...]
Outcome: damage_taken=d, hp_after=h, quality=<clean|acceptable|ugly>
Strategic note: "..."

### Round 2
...
```

### 2.3 Schema changes

**`CombatEpisode`** (`src/memory/models_v2.py`) — add:
- `deck_snapshot: list[str] = []` — combat-start deck, each entry formatted `"Name(cost=c, upgraded)"` or equivalent
- `relic_snapshot: list[str] = []` — combat-start relics, each `"Name (description)"`
- `retrieved_skill_ids: list[str] = []` — distinct skills injected into any prompt during this combat (for post-write lifecycle)

**`CombatRound`** — add (currently only has `cards_played`, `enemy_intents`, `situation_tag`):
- `energy_before: int`
- `hp_before: int`, `block_before: int`
- `hand: list[str]` — round-start hand, formatted with cost
- `draw_pile_size: int`, `discard_pile_size: int`, `exhaust_pile_size: int`
- `usable_potions: list[str]`
- `incoming_damage: int`
- `agent_plan: list[str]` — raw plan strings
- `damage_taken: int` (already computed by `combat_delta`, just needs to be attached)
- `llm_call_seq: int = -1` — index of this round's `llm_call` event in the run log (for prewrite validator to fetch raw prompt)

All new fields default-value backward compatible; old JSONL loads without error.

### 2.4 New API — `combat_store.recent_by_act_type`

```python
def recent_by_act_type(
    self,
    act: int,
    combat_type: str,
    character: str,
    limit: int = 10,
    exclude_run_id: str | None = None,
) -> list[CombatEpisode]:
    """Most-recent episodes at same act × combat_type × character,
    excluding `exclude_run_id`. Used for Baseline B."""
```

Lives in `src/memory/combat_store.py`. Baseline median/mean computation is **not** added to combat_store — it stays in `mistake_discovery.py` to keep the store focused on retrieval.

---

## 3. Critic LLM

### 3.1 Invocation

- One critic call per mistake episode.
- **All mistake episodes in parallel** via `asyncio.gather`.
- Tier: `analysis` (Gemini 3.1 Pro, `effort=high`), same as `distill_rules` / `guide_consolidator`.
- Input: §2.2 snapshot + baseline comparison.
- Output: §3.3 JSON.

### 3.2 Prompt skeleton

```
You are a Slay the Spire 2 critic. One past combat underperformed.
Decide if a reusable SKILL would have helped, OR if it was unavoidable.

## Mistake Signal
- Enemy: {enemy_name} ({combat_type}, act {act}, character {character})
- This run: loss_ratio = {actual:.2f}  ({dmg_taken} damage on {hp_before} HP)
- Baseline A (this enemy, historical median over N={n_A} fights): {baseline_A:.2f}
- Baseline B (act {act} × {combat_type} × {character}, last {n_B}): {baseline_B:.2f}
- Exceeded: A by {δA:+.2f} | B by {δB:+.2f}

{full combat context from §2.2}

## Counterfactual Test (MANDATORY)
For each round where HP was lost or a better play existed:
1. What did agent actually do? (see "Agent plan")
2. What COULD agent have done with the SAME hand/energy/intents/potions?
3. Would an average STS2 player naturally make the better choice from
   game mechanics alone, or would they need explicit guidance?

Decision rules:
- Agent's plan was already optimal for this hand/energy/intent     → no_skill_needed, reason="bad_luck"
- Better play existed but required mechanic never surfaced by game → no_skill_needed, reason="unavoidable"
- The "fix" would just describe enemy rhythm without a concrete      → no_skill_needed, reason="descriptive_rhythm"
  corrective card/target pick agent should have made
- Better play existed AND a reusable rule would catch it next time → skill_needed

## Skill Scope (if you propose one)
The skill must GENERALIZE across future combats AND be PRESCRIPTIVE (change behavior).
- GOOD: "vs {enemy}, do X" / "vs {enemy}, do NOT do Y"
- GOOD: "holding {card}, use it as X"
- GOOD: "in act 1 shops, skip card rewards if gold < 50 and no removal yet"
- BAD:  "vs {enemy} turn 1 play Strike then Defend" (hand/intent RNG — not reproducible)
- BAD:  anything already obvious from card text or enemy intent display

## HARD BOUNDARY — Skill vs Memory (descriptive rhythm is NOT a skill)
If your proposed "skill" is a turn-by-turn description of how the enemy behaves,
with no concrete correction the agent must apply, it is NOT a skill — it is a
`combat_guide` entry, which the memory system already produces from won episodes.
REJECT and return no_skill_needed, reason="descriptive_rhythm".
- BAD (descriptive — goes in guide, not skill):
    "Sewer Clam attacks on odd turns, buffs on even; block on attack, output on buff"
    "Haunted Ship's turn 2 is a safe window; use it for setup"
    "Exploit Turn 1 opener, then pivot on the debuff turn"
- GOOD (prescriptive — agent would change a card pick):
    "vs Sewer Clam, do NOT apply Poison on buff turns (wastes Shiv energy);
     save Shivs for attack turns so Weak extends to the hit"
Litmus test: would agent have picked a DIFFERENT card / target / target-order
on the failing round if this skill were in its prompt?
If no — reason="descriptive_rhythm".

Content budget: <=80 words, prescriptive tone, cite trigger conditions inline.

If skill_needed, you MUST:
- list the round indices where the mistake happened in mistake_round_indices
- write what the agent SHOULD have done in expected_correction (<=30 words)

## Output (strict JSON, no prose before or after)
<schema>
```

### 3.3 Output JSON schema

```json
{
  "analysis": "2-3 sentences on what went wrong in this combat",
  "decision": "skill_needed" | "no_skill_needed",
  "reason": "bad_luck" | "unavoidable_mechanic" | "descriptive_rhythm" | "skill_would_help",
  "skill": {
    "name": "short descriptive name, <=8 words",
    "content": "prescriptive rule, <=80 words",
    "category": "combat" | "boss" | "map" | "event" | "rest" | "deck_building" | "shop",
    "trigger": {
      "state_types": ["monster"|"elite"|"boss"|...],
      "enemy_names": ["..."],
      "character": "silent" | null,
      "min_act": 1|2|3 | null,
      "max_act": 1|2|3 | null,
      "requires_cards": ["card_name", ...],
      "requires_hand_capabilities": ["can_apply_weak"|"can_block_8_plus"|...],
      "hp_below": 0.0..1.0 | null,
      "hp_above": 0.0..1.0 | null,
      "any_of_relics": ["relic_name", ...],
      "requires_enemy_powers": ["Strength"|"Weak"|...]
    },
    "counterfactual_note": "1 sentence: what specifically would have gone better",
    "mistake_round_indices": [int, ...],
    "expected_correction": "<=30 words: what agent SHOULD have done"
  }
}
```

`skill = null` when `decision == "no_skill_needed"`.

### 3.4 Validator

Pre-parse validator drops malformed candidates (no retry, no LLM round-trip):

| Field | Rule |
|---|---|
| `name` | non-empty, ≤ 60 chars |
| `content` | non-empty, word_count ≤ 80 |
| `category` | must be in `_CANONICAL_CATEGORIES` |
| `trigger.state_types` | each value in `_CANONICAL_STATES` |
| `trigger.enemy_names` | must overlap with `episode.enemy_name` or its lookup alias |
| `trigger.character` | must equal `episode.character` |
| `trigger` | at least one non-null dimension (avoid universal triggers) |
| `counterfactual_note` | non-empty |
| `mistake_round_indices` | non-empty, all indices valid for episode, and each referenced `CombatRound.llm_call_seq >= 0` (prompt is fetchable from log) |
| `expected_correction` | non-empty, ≤ 30 words |
| `content` shape | MUST contain at least one imperative cue word (`do`, `do not`, `avoid`, `prefer`, `use`, `save`, `skip`, `play`, `block`, `target`, `hold`) **AND** must NOT be purely descriptive rhythm. Regex soft-check for descriptive giveaways: if `content` matches `/(attacks on|buffs on|follows .* pattern|consistently (opens|alternates)|safe window)/i` AND lacks an imperative cue → reject with reason="descriptive_rhythm" (re-label decision to `no_skill_needed`). Intent: defense-in-depth beyond the critic's own judgement. |

### 3.5 Initial confidence + provenance

- `source = "mistake_driven"` (new `SkillSource` enum value)
- Initial `confidence = 0.40 + 0.05 × helps_round_count` after §4 A/B validation (0.45–0.55 typical)

---

## 4. Pre-Write A/B Validation

### 4.1 Core flow

```
For each candidate skill from critic (one per mistake episode):
  For each round_idx in candidate.mistake_round_indices:
    1. Fetch original prompt from logs/run_{run_id}.jsonl at llm_call_seq
       (resolved via CombatRound.llm_call_seq)
    2. Prompt_A = original prompt (already has its own Expert Knowledge section
                  from live retrieval)
    3. Prompt_B = inject_candidate_into_prompt(Prompt_A, candidate_skill)
    4. decision_A = already logged llm_call.response (no re-run needed)
    5. decisions_B = asyncio.gather N=3 strategic-tier calls with Prompt_B
    6. Judge LLM (analysis tier, one call):
         input  = {decision_A, decisions_B, expected_correction, counterfactual_note}
         output = {verdict, hit_count_B, rationale}

  Aggregate across all rounds the candidate claims to fix:
    helps  →  +1
    harmful → -1
    unclear →  0

  Total >= 1 → WRITE (confidence = 0.40 + 0.05 × helps_rounds)
  Total <= 0 → DROP (logged to judge_log.jsonl with full context)
```

### 4.2 Prompt injection helper

```python
# src/skills/composer.py
def inject_candidate_into_prompt(prompt: str, candidate: Skill) -> str:
    """Append candidate to existing `## Expert Knowledge` block,
    or prepend a fresh block if none exists.
    Candidate is marked '(candidate — under evaluation)' so later analysis can
    distinguish it from retrieved skills in audit logs."""
```

### 4.3 Judge prompt

```
You proposed this skill for an STS2 combat:

{candidate.name}: {candidate.content}

Your stated correction:
"{expected_correction}"
"{counterfactual_note}"

## A (original decision, no skill)
{decision_A plan + reasoning excerpt}

## B (re-decided with skill injected, 3 samples)
Sample 1: {decision_B1}
Sample 2: {decision_B2}
Sample 3: {decision_B3}

Did the skill steer the agent toward the correction you proposed?

Output strict JSON:
{
  "verdict": "skill_helps" | "skill_unclear" | "skill_harmful",
  "hit_count_B": 0..3,
  "rationale": "<=2 sentences"
}

skill_helps:    >=2/3 B samples clearly follow expected_correction AND differ from A
skill_unclear:  1/3 or ambiguous
skill_harmful:  0/3, or B samples perform objectively worse than A
```

### 4.4 Data dependency on raw prompt

Prompt_A is read **verbatim** from the live run's log (`logs/run_{run_id}.jsonl`). This is byte-exact and sidesteps reconstruction drift. `llm_call.prompt` is already captured (verified against today's logs).

Mapping from `CombatRound` to log entry: `CombatRound.llm_call_seq` (new field, filled by `combat_extractor` by incrementing a counter over `llm_call` events seen during that combat).

### 4.5 Parallelism

Everything inside A/B is parallelized with `asyncio.gather`:

- Per-candidate: N=3 strategic calls + 1 judge call fan out in parallel (4 tasks per candidate).
- Across candidates: all candidates run concurrently.

Expected overhead: 30–60s per run, comparable to `evolution_engine`. Cost is acceptable given user directive "speed > cost".

### 4.6 Feature flag

`STS2_MISTAKE_VALIDATION_ENABLED` (default `true`). Disable = skip A/B, critic output goes through cascade-dedup then directly to library (consensus-free fallback, for ablation).

---

## 5. Pipeline Integration

### 5.1 Post-run chain

Current (`src/agent/loop.py` around line 4077):

```
memory extract → distill_rules → guide_consolidator
  → skill_discovery (cohort)      ← removed
  → evolution_engine
  → sweep_retirements
  → enforce_category_caps
```

New:

```
memory extract → distill_rules → guide_consolidator
  → mistake_driven_discovery      ← new, every run
  → evolution_engine
  → update_skill_usage_from_run   ← new (post-write lifecycle, §6)
  → sweep_retirements
  → enforce_category_caps
```

### 5.2 New module — `src/skills/mistake_discovery.py`

```python
async def run_mistake_discovery(
    *,
    this_run_episodes: list[CombatEpisode],
    combat_store: CombatMemoryStore,
    skill_library: SkillLibrary,
    write_gate: WriteGate,                   # existing src/memory/write_gate.py
    knowledge: GameKnowledge,
    llm_caller: LLMCaller,                   # analysis tier
    log_path: Path,                          # logs/run_{id}.jsonl for prompt A
    run_id: str,
    character: str,
) -> MistakeDiscoveryResult:
    # 1. For each episode compute Baseline A + B via combat_store
    # 2. Filter to mistake candidates (either baseline exceeded by δ)
    # 3. Build snapshot context per candidate
    # 4. asyncio.gather critic calls (parallel)
    # 5. Validate schema (drop malformed)
    # 6. Cascade dedup via write_gate.filter_skill_batch(candidates, existing)
    #    - ACCEPT / DEFER_TO_JUDGE → proceed to A/B
    #    - REJECT_{EXACT,JACCARD,EMBEDDING} → drop, record reason
    # 7. Pre-write A/B validation (§4) — asyncio.gather across all candidates
    # 8. Persist survivors with source="mistake_driven", confidence=0.40+0.05*helps
    # 9. Emit `mistake_discovery_verdict` events for monitor
    # 10. Return result for logging
```

### 5.3 WriteGate integration (existing cascade)

`src/memory/write_gate.py` is already at 3.5/4 levels — do **not** build new. Integration points:

- `WriteGate.observe_skill_batch(candidates, existing)` — runs exact / Jaccard / embedding
- `WriteGate.filter_skill_batch(candidates, existing)` — returns verdicts
- L4 (LLM judge) is observation-only today — deferred candidates still persist, but judge verdicts are logged to `judge_log.jsonl` for downstream analysis.
- The pre-write A/B layer (§4) acts as a second independent filter on top of cascade: **cascade checks "is it duplicate?"; A/B checks "is it useful?"**. Both must pass for a skill to land.
- When the separate "judge post-flush reap" TODO lands, cascade becomes a hard gate and A/B is unchanged.

### 5.4 Logging

Per-episode verdict event (new):

```json
{
  "event": "mistake_discovery_verdict",
  "run_id": "...",
  "episode_id": "...",
  "enemy": "Fuzzy Wurm Crawler",
  "loss_ratio": 0.38,
  "baseline_A": 0.15,
  "baseline_B": 0.18,
  "critic_decision": "skill_needed",
  "cascade_verdict": "ACCEPT" | "REJECT_EMBEDDING" | "DEFER_TO_JUDGE" | ...,
  "ab_verdict": "skill_helps" | "skill_unclear" | "skill_harmful" | null,
  "skill_id": "mistake_2026_04_19_abc123" | null
}
```

Consumed by `.memory-audit-cursor`, monitor UI, and `scripts/audit_skill_library.py`.

### 5.5 Feature flag

`STS2_MISTAKE_DISCOVERY_ENABLED` (default `true`). When off, falls back to seeds + non-combat discovery only.

---

## 6. Post-Write Lifecycle

Simplified from the original multi-store design because §4 A/B already filters pre-write.

### 6.1 Signal

At end of each combat in a live run, for every skill that was actually injected (`CombatEpisode.retrieved_skill_ids`), compare combat's `loss_ratio` against that combat's Baseline A / B:

- `loss_ratio <= baseline - δ` → `improved` (confidence × 1.10, cap 1.0)
- `baseline - δ < loss_ratio < baseline + δ` → `unchanged` (confidence × 0.98)
- `loss_ratio >= baseline + δ` → `worse` (confidence × 0.85)

### 6.2 Retirement

Replaces current `sweep_retirements` coarse run-level win/loss signal:

- `confidence < 0.30` AND `usage_count >= 10` → deactivated
- 3 consecutive runs injected with 0 `improved` outcomes → deactivated
- Seed skills never deactivate; only confidence decays (floor 0.40)

### 6.3 Module — `src/skills/lifecycle.py` (new)

```python
def update_skill_usage_from_run(
    *,
    this_run_episodes: list[CombatEpisode],
    skill_library: SkillLibrary,
    combat_store: CombatMemoryStore,
) -> None:
    """Attribute outcomes per combat baseline; update confidence;
    write audit trail to skill_usage.jsonl."""
```

Does **not** introduce a separate store — updates `Skill.confidence` / `Skill.usage_count` in place and appends to `data/skills/skill_usage.jsonl`.

---

## 7. Cleanup

### 7.1 Delete

| File | Reason |
|---|---|
| `src/skills/cohort_discovery.py` | Replaced by `mistake_discovery.py` |
| `src/skills/hypothesis_store.py` | Pre-write corroborate lifecycle replaced by critic one-shot verdict |
| `src/skills/evidence.py` | `RoundExemplar` unused once cohort is gone |
| `src/skills/cohort_utils.py` | `loss_ratio` helper migrated into `mistake_discovery.py`; clustering code unused |

### 7.2 Modify

| File | Change |
|---|---|
| `src/agent/loop.py` | Replace post-run chain per §5.1 |
| `src/skills/models.py` | Drop `threat_levels` / `intent_classes` / `deck_stages` / `tags` from `SkillTrigger`; add `requires_enemy_powers`; add `"mistake_driven"` to `SkillSource` |
| `src/skills/library.py` | Drop `hypothesis_store` imports; drop filters keyed on removed trigger fields |
| `src/skills/composer.py` | Drop filter branches keyed on removed fields; add `inject_candidate_into_prompt` helper |
| `src/skills/discovery.py` | Drop writes to removed trigger fields; keep non-combat bypass path |
| `src/skills/dedup.py` | Keep (still used by `discovery.py`) |
| `src/memory/models_v2.py` | Add `CombatEpisode` and `CombatRound` new fields per §2.3 |
| `src/memory/combat_store.py` | Add `recent_by_act_type()` |
| `src/memory/combat_extractor.py` | Populate new `CombatEpisode` / `CombatRound` fields |
| `src/memory/situation.py` | Keep `HandCapabilities`; drop `threat_level` / `intent_class` / `deck_stage` computation |
| `src/memory/write_gate.py::_trigger_tags()` | Drop 4 removed fields from trigger flat-set; keep `state_types` / `enemy_names` / `hand_capabilities`; add `requires_enemy_powers`. Jaccard threshold stays at 0.60 initially — re-tune only if over-dedup observed. |

### 7.3 One-shot migration — `scripts/migrate_skills_mistake_driven.py`

```python
def migrate():
    lib = SkillLibrary.load(...)
    kept = []
    for s in lib.skills:
        if s.source == "seed":
            kept.append(s); continue
        if s.source == "discovery" and s.category in {"map","event","rest","deck_building"}:
            kept.append(s); continue
        # drop everything else: all combat skills from cohort/evolved output,
        # including today's (2026-04-19) 94 polluters. No migration to
        # combat_guide — descriptive rhythm lives in memory from now on,
        # and the memory layer re-derives guides from won episodes naturally.
    lib.skills = kept
    # Migrate triggers on survivors: strip removed fields
    for s in lib.skills:
        s.trigger = s.trigger.model_copy(
            update={"threat_levels": None, "intent_classes": None,
                    "deck_stages": None, "tags": None}
        )
    lib.save(...)
```

Writes backup to `data/skills/skills.json.pre-mistake-driven.bak` before overwriting.

**Expected kept count** (based on 2026-04-19 state, 122 total skills): 8 seed + 5 non-combat discovered (map/event/rest/deck_building) = **13 skills kept**, **109 dropped** (including today's 94 cohort output + all prior evolved/discovered combat skills).

Expected after migration: ~30 seed skills + a few dozen non-combat discovery skills; all cohort + today's 94 polluters gone.

### 7.4 Archive

- `data/skills/hypothesis_store.jsonl` (if present) → `data.snapshots/2026-04-19-pre-mistake-driven/`, then delete source.
- `data/skills/judge_log.jsonl` — keep (cascade dedup still uses it).

### 7.5 Test file changes

| File | Action |
|---|---|
| `tests/test_cohort_discovery.py` | Delete |
| `tests/test_hypothesis_store.py` | Delete (if exists) |
| `tests/test_evidence.py` | Delete (if exists) |
| `tests/test_situation.py` | Strip threat/intent/deck_stage tests, keep `HandCapabilities` |
| `tests/test_skill_composer.py` | Strip assertions on removed trigger fields |
| `tests/test_mistake_discovery.py` | New (§8) |
| `tests/test_prewrite_validator.py` | New (§8) |
| `tests/test_models_v2_migration.py` | New or extend |
| `tests/test_migrate_skills_mistake_driven.py` | New |

---

## 8. Testing Strategy

### 8.1 Unit — `tests/test_mistake_discovery.py`

| Test | Covers |
|---|---|
| `test_baseline_a_per_enemy_median` | 5-sample median; <3 samples → inactive |
| `test_baseline_b_recent_by_act_type` | act/type/character filter, limit=10, `exclude_run_id` |
| `test_mistake_filter_triggers_either_baseline` | A-only / B-only / both / neither |
| `test_mistake_filter_skips_when_both_baselines_inactive` | <3 samples each side → no candidate |
| `test_critic_output_schema_valid` | Well-formed JSON accepted |
| `test_critic_output_schema_invalid_rejected` | Each validator rule from §3.4 |
| `test_critic_skill_needed_requires_round_indices` | Empty `mistake_round_indices` → drop |
| `test_inject_candidate_into_prompt_existing_block` | Appends to existing `## Expert Knowledge` |
| `test_inject_candidate_into_prompt_no_block` | Inserts fresh block |
| `test_judge_verdict_aggregation` | Single-round + multi-round voting |
| `test_prewrite_validator_drops_when_judge_harmful` | harmful → DROP |
| `test_prewrite_validator_writes_when_helps` | helps → WRITE with correct confidence |
| `test_post_write_lifecycle_uses_combat_baseline` | `record_outcome` uses per-combat baseline, not whole-run win/loss |

All LLM calls mocked via `unittest.mock.AsyncMock` with fixture JSON.

### 8.2 Serialization / migration — `tests/test_models_v2_migration.py`

| Test | Covers |
|---|---|
| `test_combat_episode_new_fields_roundtrip` | `deck_snapshot` / `relic_snapshot` / `retrieved_skill_ids` |
| `test_combat_round_new_fields_roundtrip` | `hp_before` / `hand` / `agent_plan` / `llm_call_seq` / ... |
| `test_legacy_combat_episode_loads` | Old JSONL loads with defaults |
| `test_skill_trigger_drops_removed_fields` | Old JSON with `threat_levels` etc. loads and discards silently |

### 8.3 Cleanup script — `tests/test_migrate_skills_mistake_driven.py`

| Test | Covers |
|---|---|
| `test_migration_keeps_seeds` | `source=seed` preserved |
| `test_migration_keeps_noncombat_discovery` | `source=discovery` + non-combat category preserved |
| `test_migration_removes_cohort_skills` | `source=cohort` fully dropped |
| `test_migration_strips_removed_trigger_fields` | Remaining skills have removed fields nulled |
| `test_migration_writes_backup` | `.pre-mistake-driven.bak` exists |

### 8.4 Integration — `tests/test_mistake_discovery_integration.py`

End-to-end with mocked LLM:
- Temporary `CombatMemoryStore` + `SkillLibrary` + synthetic `logs/run_<id>.jsonl`
- 2 normal episodes + 1 mistake episode
- Mock critic → valid skill candidate
- Mock redecide LLM → decisions matching `expected_correction`
- Mock judge → `skill_helps`
- Run `run_mistake_discovery` → assert skill persisted, audit logs populated

### 8.5 Regression

Add schema change to `tests/regression/` — one recent successful run log, update fingerprint hash for new `CombatEpisode` fields, verify old logs still deserialize.

### 8.6 Live smoke (manual)

```bash
# Step 1: data structure sanity (no LLM)
python -m scripts.run_agent --steps 50 --runs 1 --no-llm

# Step 2: full run
python -m scripts.run_agent --steps 500 --runs 1 --character Silent

# Step 3: inspect
python -m scripts.inspect_memory
# Verify data/skills/skills.json:
#   - today's 94 cohort entries gone
#   - new source=mistake_driven entries look reasonable
#   - judge_log.jsonl has verdict distribution
```

**Acceptance:** run completes, new skills ≤ 5 per run, ≥1 new skill injected into a subsequent run's prompt.

### 8.7 Out of scope (follow-up specs)

- Full cascade L4 enforcement ("judge post-flush reap" — separate TODO)
- Non-combat mistake-driven discovery (needs non-combat baseline definition)
- Live boss replay validation (`STS2_SKILL_EVAL` still disabled)

---

## 9. Open items / risks

- **Raw prompt dependency**: A/B needs `logs/run_{run_id}.jsonl` intact. If log rotation deletes the file before postrun runs, A/B degrades. Mitigation: postrun always runs within the same process before log rotation; no action unless log retention policy changes.
- **Jaccard dedup regression from trigger-field removal**: dimensions drop from 7 to 4. May produce false-positive dupe rejections (two distinct per-enemy skills both at `state_types=[monster]` Jaccard=1.0). Mitigation: start with current threshold 0.60, monitor `judge_log.jsonl` for over-rejection pattern; lower to 0.50 if needed.
- **Baseline δ tuning**: initial values from `combat_quality` thresholds may be too strict or too loose. Monitor `mistake_discovery_verdict` distribution over first week; adjust deltas per combat_type if candidate volume is consistently 0 (too strict) or >5/run (too loose).
- **L4 judge observation-only limitation**: deferred candidates currently persist regardless of judge verdict. A/B validation is the safety net — malformed skills still get filtered by "is it useful?" even if dedup misses.

---

## 10. Terminology glossary

| Term | Meaning |
|---|---|
| **mistake episode** | `CombatEpisode` whose `loss_ratio` exceeds Baseline A or Baseline B by δ |
| **mistake round** | Within a mistake episode, a specific round the critic flagged (`mistake_round_indices`) |
| **counterfactual test** | Whether a better play existed AND required explicit guidance beyond game mechanics |
| **Baseline A** | Per-enemy historical median `loss_ratio` |
| **Baseline B** | Same act × combat_type × character, most recent 10, mean `loss_ratio` |
| **cascade dedup** | Existing 4-level filter in `src/memory/write_gate.py`: exact → Jaccard → embedding → LLM judge |
| **pre-write A/B** | This design's §4 validation: inject candidate into original round prompt, resample N=3, LLM judge decides |
| **post-write lifecycle** | Per-combat baseline outcome tracking → `Skill.confidence` update → retirement |
