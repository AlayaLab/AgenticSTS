# Ablation Baseline Design — Memoryless LLM with Human-Equivalent Information

**Date:** 2026-04-26
**Status:** Design (spec)
**Owner:** xc
**Target venue:** EMNLP

## 1. Problem

Current ablation (`scripts/run_ablation.py`) runs 4 conditions: `{qwen, gemini} × {baseline, full}`, where `baseline` only sets `--no-skills --no-memory --no-evolution --no-postrun`. Empirical result over recent batches: full vs baseline gap is either negligible (< 2-3 percentage points on win rate / floor progress) or inverted (full slightly worse). The research story — "self-evolving agent beats LLM baseline" — fails to land.

Audit of the codebase reveals the cause: **the existing flags only disable ~40% of the strategy and cross-decision state injected into LLM prompts**. The remaining ~60% — strategy heuristics hard-coded into prompt text, knowledge-DB injections that leak unseen-entity information, short-term memory that persists across decisions within a run, multi-turn combat conversation history, run-level progress summaries — stays on regardless of `--no-*` flags. The current "baseline" is therefore not a baseline; it is a near-full agent missing only some retrieval components.

## 2. Justification framing

The baseline is defined by the principle: **the agent receives the same per-decision observable information a human player has, and is otherwise memoryless**.

Operational test for any prompt content / injection: *"would a human first-time player see this on screen at this moment, and is this content a fact rather than a strategic principle?"*

- "Fact + visible on screen" → keep (e.g., card text in hand, current HP, enemy intent icon, keyword glossary text revealed by hover).
- "Strategic principle" → strip (e.g., "prefer defensive over aggressive", "save sustained-buff potions for boss", "Two-Phase deckbuilding").
- "Fact but not visible" → strip (e.g., complete monster move-set table, exact boss HP totals, "weak encounter" classification).
- "Cross-decision state accumulation" → strip (e.g., strategic_thread, combat conversation history, run progress summary, deck change tracker).

The "memoryless" qualifier is a deliberate strengthening over the literal human reference — humans remember what just happened in the current run. We strip within-run state because:

1. The paper's contribution claim is "training-free self-evolution via retrieval-augmented skills + hierarchical categorical memory". Within-run state machinery (StM strategic_thread, CombatConversation, RunContextView) is part of that contribution stack — it should be ablated, not assumed.
2. Treating the baseline as "single-shot LLM with full observation" matches the standard ReAct-without-memory baseline used in agent research (Voyager, ExpeL, Reflexion, AgentBench).

This framing produces a clean claim: any gap between baseline and full is attributable to the agent system the paper proposes, not to information advantages or undisclosed engineering.

## 3. Scope

This spec defines **plan A**: a binary baseline-vs-full ablation that establishes the gap before drilling into per-component contributions.

A later spec ("plan C") will introduce intermediate gradient conditions:

- T0 = baseline (this spec)
- T1 = T0 + L5 seed skills (human-authored strategies)
- T2 = T1 + L4 cross-run memory
- T3 = T2 + L5 evolved skills + dynamic tools (self-evolution)
- T_full ≈ T3

Plan C is out of scope here. Plan A's only deliverable is T0 and the runner that compares T0 vs T_full.

## 4. Baseline (T0) definition

The baseline retains:

| Layer | Content |
|---|---|
| Task / I/O | `_SYSTEM_BASE` (identity + JSON output schema + plan-array execution order constraint) |
| State observation | Live MCP payload rendering — current HP, gold, energy, hand, deck, relics, enemies (HP bars / intent icons / visible powers), shop items, event options with on-screen costs/rewards, map nodes |
| Visible entity metadata | Card text / cost / type / rarity for cards in hand, deck, reward, shop, selection (UI-equivalent); potion descriptions for held / shop potions; relic descriptions for held / offered relics; enchantment descriptions for offered enchantments |
| Keyword glossary | `format_keyword_glossary` — UI hover equivalent |
| Static query tools | The 5 query tools and 1 decision tool the V2 engine exposes (perception layer, not knowledge) |
| Mechanics minimal core | Turn structure, hand reset / hand size 10 / block reset / energy reset, intent visibility, draw-effect immediacy, draw-pile-as-forecast, plan-array I/O constraint |

The baseline strips:

1. **Strategy heuristics in prompts** — see §5.1 line-level list.
2. **Strategy hint injections** — `_relic_fmt.format_relic_hints`, `_card_clarifications.format_card_notes`, `_card_clarifications.get_inline_warning`.
3. **Non-visible knowledge DB content** — `inject_event_knowledge` "Known Outcomes", `inject_combat_knowledge` enemy move-set + HP range section, `inject_encounter_knowledge` weak-encounter classification, `format_upcoming_boss_guide` boss strategy injection.
4. **Boss HP target numbers** — the 200 / 400 / 600 constants in `BOSS_HP_TARGETS` are not surfaced to the LLM.
5. **All cross-run knowledge** — L4 memory, L5 skills (including human-authored seeds), evolved tools.
6. **All within-run accumulators** — STM strategic_thread, STM combat / route / deck trackers' contribution to working_context, CombatConversation multi-turn history, RunContextView `format_run_summary`.
7. **Postrun stages** — memory extraction, skill discovery, evolution, judge.

## 5. Strip list (line-level reference)

### 5.1 Prompt files — strategy text removal

Each item below is gated by `config.PROMPT_VARIANT == "baseline"`. Default value `"full"` preserves current behavior bit-for-bit.

| File | Section to strip |
|---|---|
| `src/brain/prompts/system.py` | `SYSTEM_COMBAT.## HP Conservation` (entire block) |
| `src/brain/prompts/system.py` | `SYSTEM_COMBAT_BOSS.## Boss Fight Strategy` (entire block, including the "HP fully restores after Act boss" mechanics line) |
| `src/brain/prompts/system.py` | `SYSTEM_DECKBUILD.## Card & Deck Philosophy` + `## Strategic Deckbuilding: The Two-Phase Framework` + `## Output: strategic_note` (replace with `## Deckbuilding Decision\nYou are evaluating cards to add to, modify, or remove from your deck.\nChoose based on the information available below.`) |
| `src/brain/prompts/system.py` | `SYSTEM_STRATEGIC.## Run-Wide Strategy` + `## Output: strategic_note` (replace with `## Strategic Decision\nYou are making a run-level decision (rest / map / event).\nChoose based on the information available below.`) |
| `src/brain/prompts/system.py` | `_SYSTEM_BASE` JSON example — remove `strategic_note` field from the map example, append `Do not include strategic_note in your output.` to the closing line |
| `src/brain/prompts/reward.py` | `## Evaluation — Boss Damage Check` block (lines 161-180) and the `BOSS_HP_TARGETS` lookup it depends on |
| `src/brain/prompts/reward.py` | `## Build Trajectory Check` block (lines 184-190) |
| `src/brain/prompts/shop.py` | `## Guide` block (lines 218-229) and the `BOSS_HP_TARGETS` lookup |
| `src/brain/prompts/rest.py` | All advisory text after numeric heal calculations: lines 147 "You should heal before…", 149 "Strongly consider healing unless…", 151 "HP is relatively healthy. Smith if there is…", 156 "Weigh that against upgrading…", 232 "Boss is next — HP matters more…", 235 "At this HP level, you are at serious risk…", 238 "Review the Smith upgradeable cards above to assess…" |
| `src/brain/prompts/rest.py` | Keep numeric-only single-line: `Healing restores X HP (Y HP currently missing).` |
| `src/brain/prompts/event.py` | Final 2 advisory lines (lines 167-168: "Evaluate each option's risk vs reward…" and the boss-HP-aware card-pick guidance) |
| `src/brain/prompts/potion.py` | Inside `## Threat Assessment`: keep the numeric line `HP: x/y (z%) | Incoming damage: a (after block: b)`. Strip the `LETHAL` / `CRITICAL HP` / `Incoming X = Y% of HP -- defensive potions are valuable` advisory lines (114-120). |
| `src/brain/prompts/potion.py` | `## Potion Decision Framework` block (lines 123-148) — entire table + USE/SAVE rules + golden rule |
| `src/brain/prompts/hand_select.py` | `## Tactical Flags` section (lines 230-262) — Sly priority + Sandpit warning |
| `src/brain/prompts/hand_select.py` | Replace priority groupings in `## Cards You Can Select` with a flat list. Lines 184-223 condense into the same `for c in selectable_cards: lines.append(_format_card_line(c))` loop the exhaust branch already uses. |
| `src/brain/prompts/hand_select.py` | Mode-aware hint at the end (lines 277-290): keep the mechanic statement (`Exhaust = GONE forever this combat.` / `Discard = temporary.` / `Retain = keep for next turn (free extras — you still draw 5 normally; hand cap 10).`). Strip the strategy advice (`Exhaust Curses/Status first…`, `Retain every non-harmful card unless…`, `Do NOT retain: Status cards, Curses, …`). |
| `src/brain/prompts/card_select.py` | End hint (lines 304-310) — the upgrade / remove / generic guidance line |
| `src/brain/prompts/card_select.py` | `build_pack_selection_prompt` end line 167 — "Prefer the pack that best fits the deck's current win condition…" |
| `src/brain/prompts/treasure.py` | Final 2 lines (49-50) — "Almost always take a relic…" / "Energy/draw relics are S-tier…" |

`_format_card_line` retains `cost / type / rarity` — these are UI-visible (card frames show rarity color, cost in corner, type by icon).

### 5.2 Hint injections — gated removal

Gated by `config.PROMPT_HINT_FILTER` (default `false`):

- Skip every call to `_relic_fmt.format_relic_hints(...)`.
- Skip every call to `_card_clarifications.format_card_notes(...)`.
- `_card_clarifications.get_inline_warning(card_name)` returns `""`.

### 5.3 Knowledge DB — gated removal

Gated by `config.KNOWLEDGE_STRICT` (default `false`):

- `src/knowledge/injector.py::inject_event_knowledge` returns `""` (the `## Known Outcomes` section duplicates live MCP option descriptions per audit; Ancient-event `pages` data, if ever wired, becomes a leak vector).
- `src/knowledge/injector.py::_build_monster_info` returns `[]` (strips the `## Enemy Patterns` section that lists every monster's full move set + HP range).
- `src/knowledge/injector.py::inject_encounter_knowledge` returns `""` (strips the `weak encounter` classification and pre-revealed encounter composition).
- `src/brain/prompts/_boss_guide_fmt.format_upcoming_boss_guide` returns `[]`. (Already neutralized by `--no-memory` because its `guide_store` argument is sourced from `MemoryManager`. Adding a hard gate makes the strip explicit and survives any future code refactor that decouples guide_store from memory.)

`inject_combat_knowledge`'s `## Card Mechanics` section for hand cards stays — these mirror UI text. Same for `## Potion Mechanics` (held potions, UI tooltip equivalent) and `inject_keyword_glossary` (UI hover equivalent).

### 5.4 Cross-decision state — new gates

| Flag | Default | Effect when `false` |
|---|---|---|
| `config.STM_ENABLED` | `true` | `AgentLoop._get_short_term_ref()` and `AgentLoop._hcm_short_term()` return `None`. STM internal updates still run (so postrun extraction, if ever turned on, is unaffected); only prompt-side reads are bypassed. Consumers: route Scenario A prompt's `strategic_thread` argument; `format_working_context`'s `short_term_hints`; `RunContextView`'s deck/route formatters. |
| `config.COMBAT_CONVERSATION_ENABLED` | `true` | When `false`, `V2Engine` never persists `_v2_combat_conversation` across turns. Each turn builds a fresh single-message conversation (system + current user message). `add_combat_start` / `add_execution_result` / `generate_combat_summary` become no-ops. `_strategic_notes` accumulator is not used. |
| `config.RUN_CONTEXT_ENABLED` | `true` | `RunContextView.format_run_summary()` returns `""`. The view object is still constructed (preserves init order and reset hooks), but emits nothing for prompt injection. |

### 5.5 Boss HP constants

Gated by `config.INCLUDE_BOSS_HP` (default `true`):

When `false`, the `BOSS_HP_TARGETS` dictionary in `_card_clarifications.py` is not imported by `reward.py` / `shop.py`, and any prompt segment that would render the `Act 1 ≈ 200 / Act 2 ≈ 400 / Act 3 ≈ 600` numbers is skipped. (After §5.1 strips those segments under `PROMPT_VARIANT=baseline`, this flag becomes redundant in practice but stays as an independent safety in case future prompt edits reintroduce the constants.)

## 6. Full-run safety

Every flag introduced defaults to current behavior:

- `PROMPT_VARIANT="full"` → no prompt sections changed.
- `PROMPT_HINT_FILTER=false` → all hint calls fire as before.
- `KNOWLEDGE_STRICT=false` → all injectors return as before.
- `STM_ENABLED=true`, `COMBAT_CONVERSATION_ENABLED=true`, `RUN_CONTEXT_ENABLED=true` → all current paths active.
- `INCLUDE_BOSS_HP=true` → constants imported and rendered.

`scripts/run_ablation.py::Condition.to_env_overrides()` is the single point that sets ablation env. The baseline condition gets the additional overrides; the full condition does not. No default code path changes. Existing runs (single, infinite-loop, watchdog routines) continue with full behavior.

The flag list is added to `config.py`'s `_PRESERVE_IF_SET` block alongside `STS2_SKILLS_ENABLED` etc., so `.env` cannot override the values the ablation runner sets.

## 7. Implementation tasks

Tasks are sequenced — each is independent enough to land in isolation, but later tasks assume earlier flag scaffolding.

1. **Add config flags and `_PRESERVE_IF_SET` registration.**
   - File: `config.py`
   - New constants: `PROMPT_VARIANT`, `PROMPT_HINT_FILTER`, `KNOWLEDGE_STRICT`, `STM_ENABLED`, `COMBAT_CONVERSATION_ENABLED`, `RUN_CONTEXT_ENABLED`, `INCLUDE_BOSS_HP`.
   - All loaded from `STS2_*` env vars with defaults preserving current behavior.
   - Append flag names to `_PRESERVE_IF_SET`.
   - Surface in `config.build_model_profile()` so `RunRecord.model_profile` records the active configuration per run.

2. **Prompt-text strip — system.py.**
   - Add `SYSTEM_COMBAT_BASELINE`, `SYSTEM_COMBAT_BOSS_BASELINE`, `SYSTEM_DECKBUILD_BASELINE`, `SYSTEM_STRATEGIC_BASELINE` constants.
   - Update `_STATE_SYSTEM_MAP` selection and `get_system_prompt(state_type)` to read `config.PROMPT_VARIANT` and pick the matching variant.
   - Update `_SYSTEM_BASE` to gate the `strategic_note` example field on `PROMPT_VARIANT`.

3. **Prompt-text strip — reward / shop / rest / event / potion / hand_select / card_select / treasure.**
   - Each file gets a single `if config.PROMPT_VARIANT != "baseline":` guard around the strategy block(s) listed in §5.1. Strict prefer-deletion-over-comment style: blocks live in their original places, just gated.
   - `hand_select.py` priority grouping: extract the flat-list path into a helper `_render_selectable_cards_flat(selectable_cards) -> list[str]` and call it under baseline. Discard / retain modes use the helper; full mode keeps the existing grouping path.

4. **Hint-injection gate.**
   - Each call site of `format_relic_hints` / `format_card_notes` / `get_inline_warning` becomes `if not config.PROMPT_HINT_FILTER: <call>`.
   - Call sites: `reward.py`, `shop.py`, `rest.py`, `map.py` (relic hints only), and inline-warning inside reward/shop's per-card line builder.

5. **Knowledge-DB strict mode.**
   - `src/knowledge/injector.py`: top-of-function early returns guarded by `config.KNOWLEDGE_STRICT` for `inject_event_knowledge`, `inject_encounter_knowledge`. For `_build_monster_info`, return `[]` when strict.
   - `src/brain/prompts/_boss_guide_fmt.format_upcoming_boss_guide`: top-of-function `if config.KNOWLEDGE_STRICT: return []`.

6. **STM gate.**
   - `src/agent/loop.py`: wrap `_get_short_term_ref` and `_hcm_short_term` returns in `if not config.STM_ENABLED: return None`.
   - Confirm that the `is None` guard at every consumer (route prompt builder, `format_working_context` short-term-hint section, RunContextView `_format_deck_changes` / `_format_route`) already handles the None case gracefully — quick read of the files in §5.4 says yes; verify with grep at implementation time.

7. **CombatConversation gate.**
   - `src/agent/loop.py` and `src/brain/v2_engine.py`: at the entry points where `_v2_combat_conversation` is created (lines around 2342, 2422), gate creation on `config.COMBAT_CONVERSATION_ENABLED`. When disabled, the variable stays `None`; downstream `if self._v2_combat_conversation:` guards already handle that path.
   - Audit: ensure the V2 combat plan loop can run a single round without conversation. If the engine currently assumes a non-None conversation, add a stub that builds a fresh single-message context per turn.

8. **RunContextView gate.**
   - `src/brain/run_context.py::RunContextView.format_run_summary`: `if not config.RUN_CONTEXT_ENABLED: return ""` at the top.

9. **Boss-HP gate.**
   - `src/brain/prompts/_card_clarifications.py`: `BOSS_HP_TARGETS` stays defined (lifecycle-of-imports unaffected). reward.py / shop.py wrap their boss-HP-rendering code in `if config.INCLUDE_BOSS_HP:` (in addition to §5.1's `PROMPT_VARIANT` gate; the two together mean baseline never sees the numbers).

10. **Ablation runner extensions.**
    - `scripts/run_ablation.py::Condition`: add fields `prompt_variant: str = "full"`, `hint_filter: bool = False`, `knowledge_strict: bool = False`, `stm: bool = True`, `combat_conv: bool = True`, `run_ctx: bool = True`, `boss_hp: bool = True`.
    - `to_env_overrides()` adds the corresponding `STS2_*` env entries.
    - `build_condition_matrix()`: new baseline preset enables strict mode on every new flag. Full preset uses defaults (current behavior).
    - `condition_id` strings: `f"{model}-baseline-strict"` and `f"{model}-full"` so historical `*-baseline` records under prior tags do not silently merge with the new stricter baseline.

11. **Testing.**
    - Unit: `tests/prompts/test_baseline_variants.py` — for each prompt builder, snapshot the `baseline` and `full` outputs against a fixture GameState; assert `baseline` does not contain any of: `Two-Phase`, `Boss Damage Check`, `Build Trajectory`, `HP Conservation`, `Strategic Thread`, `Tactical Flags`, `## Guide`, `## Potion Decision Framework`, `Boss HP`, `200`, `400`, `600` (numeric HP target check).
    - Unit: `tests/config/test_flag_defaults.py` — assert all new flags default to current behavior; toggle each individually and verify the relevant prompt / injector output diff.
    - Integration: short `--no-llm` smoke run with `STS2_PROMPT_VARIANT=baseline STS2_KNOWLEDGE_STRICT=true STS2_PROMPT_HINT_FILTER=true STS2_STM_ENABLED=false STS2_COMBAT_CONVERSATION_ENABLED=false STS2_RUN_CONTEXT_ENABLED=false STS2_INCLUDE_BOSS_HP=false` to confirm the agent does not crash on missing context. Random-fallback path is fine — we are testing absence-of-crashes.

## 8. Experiment protocol

1. Tag: `abl-2026-04-26-baseline-strict`.
2. Conditions: `{qwen, gemini} × {baseline-strict, full}`, 4 conditions.
3. Runs per condition: 20 (was 10; doubled because A vs B distinction may be small and we need statistical power for `gemini-baseline-strict` vs `gemini-full`).
4. Character: Silent. Ascension: `auto` (start at the highest cleared + 1 per family + character key).
5. Steps: 5000 (effectively run-to-victory-or-defeat).
6. Postrun: off in all conditions (knowledge snapshot frozen).
7. Reporting metrics:
   - Win rate (Act 3 boss kill).
   - Highest floor reached.
   - HP retention curve per floor.
   - Combat win rate breakdown by room type (monster / elite / boss).
   - Decision latency and token usage (cost confound check).

Statistical test: Welch's t-test on win rate per condition pair, 95% CI. Bootstrap floor-progress mean with 10000 resamples.

## 9. Validation criteria

The implementation is correct when:

- All new flags toggle independently without regressions (unit tests pass).
- Full run with default flags produces a `RunRecord.model_profile` snapshot bit-identical to a pre-implementation full run on the same seed (smoke test with fixed seed if available).
- Baseline-strict run completes a smoke episode without unhandled exceptions on `--no-llm` random-fallback path.
- A baseline-strict prompt rendered for `card_reward` matches the §10 sample below modulo dynamic state values.

## 10. Sample baseline-strict prompt

The full text below is what the LLM receives for a `card_reward` decision in baseline-strict mode (system + state, no skill / memory / hint / boss-guide injection). It is the contract the implementation must produce:

```
[SYSTEM]
You are an autonomous Slay the Spire 2 agent playing a complete run. You make every decision to maximize your chance of defeating the Act 3 boss.

## Output Format
Think through your decision, then output your choice in a <decision> tag containing valid JSON.

[examples — strategic_note removed]

The JSON must match the schema for the current decision type. Every decision requires a "reasoning" field. Do not include `strategic_note` in your output.

## Deckbuilding Decision
You are evaluating cards to add to, modify, or remove from your deck.
Choose based on the information available below.

[USER]
## Card Reward
HP: 56/70 (80%) | Gold: 95
Act: 1 | Floor: 7

## Deck (12 cards)
- Strike x5: Deal 6 damage.
- Defend x4: Gain 5 Block.
- Bash: Deal 8 damage. Apply 2 Vulnerable.
- Acrobatics: Draw 3 cards. Discard a card from your hand.
- Survivor: Gain 6 Block. Discard a card from your hand.

## Relics: Ring of the Snake

## Available Cards
- [index=0] Backflip (1E, Skill, Common): Gain 5 Block. Draw 2 cards. [5 block]
- [index=1] Dagger Throw (1E, Attack, Common): Deal 9 damage. Draw a card. Discard a card. [9 dmg]
- [index=2] Heavy Blade+ (2E, Attack, Common): Deal 14 damage. Strength affects Heavy Blade 5 times. [14 dmg]
- [ALT index=3] Skip: Take no card

## Keyword Glossary
- Block: Reduces damage taken until end of next turn.
- Vulnerable: Take 50% more attack damage.
- ...
```

Notably absent: any text suggesting how to weigh damage / defense / draw / energy, any boss-HP target, any past-encounter pattern, any retrieved skill, any strategic thread, any 4-dimension framework, any pivot rule.

## 11. Plan C preview

Once plan A confirms a baseline-vs-full gap, plan C inserts the gradient. Mapping (for reference, not implementation here):

- T0 = baseline-strict (this spec).
- T1 = T0 + L5 seed skills only (`STS2_SKILLS_ENABLED=true`, but with a separate config to load only seeds and not evolved or postrun-discovered skills). Tests "does human-authored strategic knowledge help".
- T2 = T1 + L4 cross-run memory (`STS2_MEMORY_ENABLED=true`, postrun still off so memory is whatever was accumulated pre-experiment-freeze). Tests "does retrieval-augmented experience help on top of seeds".
- T3 = T2 + evolved skills + dynamic tools + postrun on (`STS2_EVOLUTION_ENABLED=true`, `STS2_POSTRUN_ENABLED=true`). Tests "does autonomous self-evolution add measurable value beyond what humans can hand-author".

Plan C requires (a) the seed-only skill loader (refactor `SkillLibrary._load` to filter by source), (b) an experiment-tag-scoped frozen memory snapshot mechanism so T2 reads a stable L4 across all T2 runs, (c) the same frozen-snapshot mechanism for T3's L5_evolved. None of these block plan A.

## 12. Open questions / known limitations

1. **Asymmetry between full's prompts and T1's seeds.** Full mode keeps the strategy heuristics in prompts (Two-Phase Framework, Boss Damage Check, etc.). T1 has L5 seeds turned on. If the seed JSON files do not contain the same strategic content as the prompts, T1 receives strictly less strategy than full minus everything-but-prompts. In plan C this means T1 → T_full has two confounded sources of gain (more seeds + the prompt-embedded strategy that survives ablation in full mode). Resolution: in plan C, either (a) migrate the prompt strategy into seed skills so full = baseline + seeds + memory + evolution, eliminating the prompt confound, or (b) accept the confound and report it. Decision deferred to plan C spec.
2. **`Boss HP fully restores after Act boss` strip is aggressive.** A first-time human player does not know this; we strip it from `SYSTEM_COMBAT_BOSS_BASELINE`. Consequence: baseline likely plays Act bosses conservatively (treats them like elites). This is the intended baseline behavior. If the resulting baseline is so weak that even win rate floors do not differ between baseline and full (i.e., both rarely beat Act 1 boss), we may need to revisit — the gap should be visible at the floor-progress and combat-win-rate levels, not only at the run-completion level.
3. **Sandpit warning strip.** `hand_select.py`'s `Sandpit on the enemy counts down to 0 = INSTANT DEATH` is a legitimate mechanic warning. Stripping it under baseline means baseline must derive Sandpit lethality from the enemy's `Sandpit(N)` power line and the relevant cards' rules text. The information is present; only the explicit warning is removed. This is consistent with the framing (no pre-digested strategy).
4. **`Queue plays for generated cards` retained.** The line is an I/O contract — the `plan` array executes in order, so failing to pre-queue Shivs from Cloak and Dagger means the agent's plan fails to play them. This is not strategic advice ("you should be aggressive") but a constraint imposed by the V2Engine plan-execution model. Retained.
5. **STM internal updates still run when `STM_ENABLED=false`.** The tracker objects continue accumulating per-floor data; they are simply not read into prompts. This preserves the option of postrun extraction in a future experiment without re-instrumenting the agent. The cost is small (in-memory dict updates).

## 13. Files touched

- `config.py` — flag definitions, `_PRESERVE_IF_SET`, snapshot.
- `src/brain/prompts/system.py` — 4 baseline variants + dispatcher.
- `src/brain/prompts/reward.py` — gated strategy blocks.
- `src/brain/prompts/shop.py` — gated strategy blocks.
- `src/brain/prompts/rest.py` — gated advisory text.
- `src/brain/prompts/event.py` — gated trailing guidance.
- `src/brain/prompts/potion.py` — gated framework table + assessment labels.
- `src/brain/prompts/hand_select.py` — flat-list helper, gated tactical flags + mode hints.
- `src/brain/prompts/card_select.py` — gated trailing hint.
- `src/brain/prompts/treasure.py` — gated trailing hint.
- `src/brain/prompts/_boss_guide_fmt.py` — `KNOWLEDGE_STRICT` early return.
- `src/knowledge/injector.py` — `KNOWLEDGE_STRICT` early returns in 3 functions.
- `src/agent/loop.py` — STM gate at `_get_short_term_ref` / `_hcm_short_term`; CombatConversation creation gates.
- `src/brain/v2_engine.py` — single-turn fallback when CombatConversation disabled.
- `src/brain/run_context.py` — `RUN_CONTEXT_ENABLED` early return.
- `scripts/run_ablation.py` — `Condition` extensions, env override extensions, condition-id rename.
- `tests/prompts/test_baseline_variants.py` — new.
- `tests/config/test_flag_defaults.py` — new.
