# Write Gate + Retriever Scope Filter — Design Spec

**Date:** 2026-04-18
**Status:** Draft (awaiting review)
**Scope:** Dedup / conflict / invalid-content avoidance for L4 memory and L5 skills. Decision-type-aware retrieval filtering. Log-grounded A/B validation before promotion.
**Not in scope:** L1/L2 prompt slimming (separate TODO); cross-model generalization experiments (C2); benchmark leaderboard (C3); personality analysis (C4).

---

## 1. TL;DR

Empirical dumps (`logs/run_20260418_053004_*.jsonl`) confirmed the STS2 agent's postrun-generated content duplicates static prompts and competes with itself across stores. The deprecated Prompt Evolution pipeline (0/33 promote rate, [pe-deprecation spec](2026-04-18-pe-deprecation-negative-result.md)) demonstrated that LLM-authored prompt edits are unreliable; however, skills and memory entries remain the agent's primary evolution surface and currently lack a comparable write gate. This spec defines an eight-part pipeline that gates every postrun-proposed L4/L5 entry through a cheap embedding-and-Jaccard cascade, a batch LLM conflict judge, lifecycle management, retrieval scope filtering, and log-grounded A/B replay.

The design contributes four empirically-grounded novel claims that current literature (Voyager, ExpeL, EvolveR, EvoSkill, WebXSkill) does not cover:

1. **Unconditional-overlap check against L1/L2/L3** — L1 system prompts, L2 state-template static text, and L3 knowledge-injector constants are embedded once at startup into a span index; any new skill/memory/rule with embedding similarity ≥ threshold against any indexed span is rejected as "already always-present in the prompt".
2. **Trigger-conditional dedup** — same content under the same trigger merges, same content under different triggers coexists.
3. **Cross-store conflict resolution** across skills / guides / rules / card memory.
4. **Log-grounded A/B replay** — new skill/memory must be validated against the exact prompt that produced the learning signal.

**Infrastructure posture**: one embedding model (`text-embedding-3-large` via the existing OpenAI-compatible GPT relay at `STS2_GPT_BASE_URL`), one **fast-tier** LLM judge per postrun for the cascade classifier and the Phase 2 pair preference, and **strategic-tier** LLM sampling for Phase 2 A/B completions so the grading runs on the same model distribution that serves production. Measured per-postrun cost ≤ $0.03 (dominated by strategic sampling). Embedding probe results in §4.6; tier rationale in §13.1.

## 2. Motivation

Three pieces of empirical evidence drive this work:

- **Duplication present in production** (this repo, 2026-04-18 dumps). `## Card-Specific Insights` and `## Card Experience Notes` carried identical text via independent injection paths; `## Strategy Skills` + `## Expert Knowledge` rendered as back-to-back headers with no content between; "block priority" appeared simultaneously in system prompt, Combat Guide, Expert Skill `Core Combat Principles`, and Strategy Rules (4 sources). The first two were fixed in `7a40024`; the rest need structural prevention.
- **Bloat degrades performance** ([Memory Management 2025](https://arxiv.org/html/2505.16067v1)). EHRAgent 16.89% → 13.04% with 24× memory bloat; AgentDriver 40.53% → 32.48% with 12× bloat. Selective addition + combined deletion recovers ~10 pp.
- **LLM-authored prompt edits fail** (this repo, PE deprecation). 33/33 postrun prompt patches failed A/B validation (30/33 INVALID_B). Skills and memory avoid this failure mode because they add retrieval content, not modify output-shaping prompts — but only if the write gate also validates them against real decision traces.

## 3. Architecture Foundation — Five-Layer Contract

All postrun-writable content must fit one of these five layers. **Content type determines the write channel, not the writer.** The postrun evolution LLM cannot write to L1/L2/L3 through any path.

| Layer | Owns | Writeable by |
|---|---|---|
| **L1 system prompts** (`src/brain/prompts/system.py`) | Universal game mechanics (turn structure, block/energy reset, intent types, output JSON schema) | Human + `scripts/apply_patch.py` (game version patches) |
| **L2 state-specific prompt templates** (`src/brain/prompts/{reward,shop,rest,...}.py` static portions) | Decision-type schema fields, output format directives | Human + game-version patch |
| **L3 knowledge injectors** (`knowledge/injector.py`, `_keyword_fmt.py`, `_relic_fmt.py`, `_card_clarifications.py`, `enemy_pattern_injector.py`) | Facts about entities in the current game state (card rules_text, enemy move lists, keyword definitions, relic synergies) | DB auto-rebuild on game patch |
| **L4 memory** (`memory/*_store.py` — guides, rules, episodes, card memory, event memory) | Episodic facts, per-entity longitudinal statistics, consolidated guides scoped to `(character, context_key)` | postrun discovery / consolidation via write gate |
| **L5 skills** (`skills/library.py`) | Trigger-matched tactical patterns ("when hand has X + intents Y → play Z") | postrun discovery via write gate |

Dynamic tools (`data/evolution/tools/*.py`) are AST-sandboxed Python computational functions authored by `author_tool` — orthogonal to this spec and retain their existing validation path.

**Hard rule**: L5 skills must have non-empty triggers (state tags, threat level, hand capabilities, or enemy intents). A skill without a trigger is a mechanism and belongs in L1, not L5.

## 4. Write Gate — Four-Level Cascade

Every new L4 / L5 entry flows through this cascade before persistence.

### 4.1 Level 1 — Exact key match

If `(name, scope_key)` matches an existing entry → `UPDATE(target_id)` (merge evidence, increment confidence, do not create new row). O(1) lookup.

### 4.2 Level 2 — Trigger-tag Jaccard

Compute Jaccard similarity over the candidate's trigger tags (`state_tags ∪ threat_levels ∪ hand_capabilities ∪ enemy_intents ∪ deck_stage`) against every existing L4/L5 entry's trigger set. Precompute and cache.

- `J ≥ 0.60`: existing entry is "same-trigger-context candidate"; carry forward to Level 3 as the primary merge target.
- `J < 0.60`: no same-trigger entry; the candidate is a distinct-trigger variant even if content overlaps.

### 4.3 Level 3 — Embedding similarity

Candidate content (skill `content`, guide text, rule text) is embedded via `text-embedding-3-large` through the OpenAI-compatible relay at `STS2_GPT_BASE_URL`. 3072 dims. Empirical calibration in §4.6 drove the specific thresholds below; they differ from `text-embedding-3-small` thresholds published by EvolveR etc. because 3-large has naturally lower absolute cosines on the same text pairs.

**Against L1 / L2 / L3 pre-indexed static text** (unconditional injections — see §4.5 for index definition):

| Max span cosine | Action |
|---|---|
| `≥ 0.70` | `REJECT` — L1/L2/L3 already covers this content unconditionally. Record rejection reason as `l1_overlap` with the offending span for diagnosis. |
| `[0.55, 0.70)` | Defer to Level 4 batch judge with the offending span as context. |
| `< 0.55` | ACCEPT this layer-overlap check (still proceeds through L4/L5 comparison below). |

**Against existing L4 / L5 entries** (trigger-conditional injections):

| Max cosine | Trigger Jaccard (§4.2) | Action |
|---|---|---|
| `≥ 0.85` | any | `REJECT` — auto-duplicate |
| `[0.70, 0.85)` | `≥ 0.60` | `MERGE(target_id)` — same trigger + similar content |
| `[0.70, 0.85)` | `< 0.60` | `ACCEPT` — distinct-trigger context variant |
| `[0.55, 0.70)` | any | Defer to Level 4 batch judge |
| `< 0.55` | any | `ACCEPT` |

### 4.4 Level 4 — Batch LLM judge at end of postrun

All candidates deferred from Level 3 are accumulated during the postrun evolution stage, then submitted as a **single batch LLM call** at the fast tier at the end. Input per candidate: the candidate, its top-3 nearest L4/L5 neighbors, any L1/L2/L3 span above 0.55, and the cross-store conflicts identified in §5.

Output schema (per candidate):

```json
{
  "candidate_id": "...",
  "decision": "ADD" | "UPDATE" | "MERGE" | "REJECT",
  "target_id": "..." | null,
  "reason": "short explanation"
}
```

Batching keeps cost bounded at one LLM call per postrun regardless of candidate volume.

### 4.5 L1/L2/L3 static span index

On process start (and whenever `scripts/apply_patch.py` bumps the game version), build an in-memory index:

- **L1 source**: each of the 4 system prompts in `src/brain/prompts/system.py` (`COMBAT`, `COMBAT_BOSS`, `DECKBUILD`, `STRATEGIC`), split at `##` / `**` boundaries into 150–300 token spans.
- **L2 source**: static string literals in `src/brain/prompts/{reward,shop,rest,event,map,potion,card_select,hand_select,treasure}.py` — everything appended via `lines.append(...)` that is not an f-string interpolation of game state. Collect per file, split at blank lines.
- **L3 source**: human-written constants in `_keyword_fmt.py`, `_relic_fmt.py`, `_card_clarifications.py`, and the descriptive strings inside `knowledge/injector.py`. Runtime DB lookups (card HP, enemy name) are **not** indexed — those are data, not rules.

Store in `data/evolution/l1_l2_l3_index.json` with structure `{span_hash: {text, layer, source_file, embedding}}`. Rebuild on startup if any source file hash changes.

API:

```python
# src/memory/write_gate.py
class StaticSpanIndex:
    def rebuild_if_stale(self) -> None: ...
    def max_similarity(self, embedding: list[float]) -> tuple[float, str]:
        """Return (max_cosine, offending_span_text) against all indexed spans."""
```

### 4.6 Empirical embedding probe (calibration basis for §4.3 thresholds)

Run `python -m scripts.probe_embedding` to reproduce. The probe embeds 8 representative strings covering the patterns that actually occur in our system (L1 mechanic restatement, card-note paraphrase, unrelated skills, same-trigger-different-content, etc.) and prints the full cosine matrix.

Results on the relay at `https://proxy.example.com/v1`, model `text-embedding-3-large`, 3072 dims, 174 input tokens, 2.38 s latency, ≈ $0.00005 for the whole probe:

| Pair (kind) | Cosine | Expected |
|---|---|---|
| L1 mechanic vs skill restating L1 | **0.72** | HIGH — correctly distinguished |
| Card note vs near-paraphrase card note | **0.77** | HIGH — correctly distinguished |
| L1 mechanic vs unrelated rest-site skill | 0.24 | LOW — correctly rejected |
| Deck guide vs L1 mechanic | 0.21 | LOW — correctly rejected |
| Combat skill vs rest skill (different scope, same structure) | 0.32 | LOW — correctly rejected |

Key empirical fact: with `text-embedding-3-large`, **semantic restatements sit around 0.70–0.77**, not the 0.85–0.93 region published for `text-embedding-3-small`. We chose 3-large because its tighter separation at the ambiguity boundary makes the Level 4 judge's workload smaller; thresholds in §4.3 were recalibrated accordingly.

The 8-case probe is too small to finalize thresholds. Commit 1 of the implementation includes a calibration step: label 100–200 real postrun candidates as `dup / maybe / novel` and pick thresholds on the ROC — values in §4.3 are the starting point, not the shipped values.

## 5. Cross-Store Conflict Detection

Beyond candidate-vs-candidate dedup, the gate scans the **entire L4 + L5 state** for mutually contradictory entries at the same time.

### 5.1 Structural check (cheap, deterministic)

For each pair `(entry_a, entry_b)` where `trigger_jaccard(a, b) ≥ 0.60`:

- Extract action predicates via regex on `content`: `(prefer|avoid|always|never|if …then)` phrases.
- If two entries share a trigger but assign opposing action predicates on the same noun phrase → flag as `disputed` pair.

### 5.2 Semantic check (batch LLM, in §4.4)

The same end-of-postrun batch judge receives the `disputed` pairs. Output:

```json
{
  "pair": [id_a, id_b],
  "verdict": "contradiction" | "complementary" | "redundant",
  "resolution": "keep_higher_confidence" | "merge" | "both_coexist"
}
```

Action on `contradiction`: the lower-confidence entry is tagged `disputed=true`; the retriever (§7) only returns the higher-confidence one until more evidence resolves the tie.

This is novel claim #3 — published skill-library methods handle dedup within a single store; none handle cross-store contradiction across skills, guides, rules, and card memory.

## 6. Lifecycle Management

Gating admission is not enough. Three mechanisms prevent long-term drift:

### 6.1 Pareto frontier per cohort

Cohort key: `(character, decision_type, deck_stage)`. Each cohort holds at most `k = 3` skills/guides. A candidate that would exceed `k` must beat the weakest frontier member on the §8 A/B replay score; otherwise reject.

### 6.2 EvolveR-style confidence prune

Lifecycle score `s = (c_succ + 1) / (c_use + 2)`. Entries with `s < 0.30` AND `c_use ≥ 10` are auto-demoted to `archive` (not deleted — kept for negative-result analysis). Published threshold from [EvolveR 2025](https://arxiv.org/html/2510.16079v1).

### 6.3 Proposal-history injection

Every postrun discovery prompt is augmented with the last `N = 20` candidate proposals and their final dispositions (`ADD` / `UPDATE` / `MERGE` / `REJECT` + short reason). Zero runtime cost; [EvoSkill 2026](https://arxiv.org/html/2603.02766v1) reports this alone "prevents redundant proposals."

## 7. Retriever Scope Filter

Strategic Thread notes carry a scope prefix (`[event]`, `[map]`, `[shop]`, `[card_reward]`, `[rest]`, `[combat]`, `[deck_building]`, `[routing]`, `[run]`). The current retriever injects all notes regardless of current decision type, so combat prompts receive event/map notes and vice versa.

**Decision-type → allowed-scopes matrix**:

| Current decision | Allowed scopes |
|---|---|
| `combat` / `combat_boss` | combat, deck_building, run |
| `card_reward` | card_reward, deck_building, combat, run |
| `shop` | shop, deck_building, card_reward, run |
| `rest_site` | rest, combat, deck_building, run |
| `event` | event, deck_building, run |
| `map` / `route_select` | map, routing, combat, run |
| `card_select` / `hand_select` | combat, deck_building, run |
| `treasure` | deck_building, run |
| `potion` | combat, run |

Implementation: `src/memory/retriever.py` add `_filter_scope_by_decision_type(hints: list[str], decision_type: str) -> list[str]`, called inside `query_for_decision()` before returning `short_term_hints`. Scope prefixes with no match to the matrix are dropped silently; notes lacking any scope tag are always kept (backward compat with un-tagged legacy content).

Apply the same matrix to `strategic_rule_hints` from rule_store where rules have scope metadata.

## 8. Log-Grounded A/B Replay

Every candidate that passes §4 (and, for postrun batches, §5) enters a two-phase A/B validation against the exact log event that produced its learning signal.

### 8.1 Source binding

Each candidate `c` carries `source_log_event = (run_id, step, state_type)` — the `llm_call` event whose reasoning was cited as justification during discovery. If discovery did not cite a specific event (e.g. aggregated-statistic skill), set `source_log_event = NULL` and use the most recent 5 `llm_call` events for the same `state_type` as fallback cases.

### 8.2 Phase 1 — Structure check (deterministic)

1. Reconstruct `prompt_A` = the original `(system_prompt, messages)` from the log event.
2. Simulate retrieval: generate `prompt_B` by re-running the retrieval pipeline with `c` eligible. Assert `c` is actually retrieved for this state — otherwise the skill's trigger is not matched by the very case it came from, which is itself a rejection condition (`trigger_mismatch_with_source`).
3. Diff `prompt_A` and `prompt_B`. Let `delta = prompt_B \ prompt_A`.
4. For each line in `delta`, compute embedding (same `text-embedding-3-large`) and check max cosine against:
   - Every other section already in `prompt_A` (would be a duplicate with different packaging).
   - Every line elsewhere in `prompt_B` (would mean another retrieval path already supplies this).
5. If any cosine ≥ 0.70 → `REJECT` with reason `phase1_duplicate(section_name)`. Same calibrated threshold as §4.3 L1/L2/L3 reject.
6. Run §5.1 structural conflict check between `c.content` and all other content injected into `prompt_B` that shares trigger overlap. Flag conflicts → REJECT.

Phase 1 runs as part of the end-of-postrun batch (in parallel with §4.4 judge) — no extra LLM cost.

### 8.3 Phase 2 — Quality check (LLM calls)

Only candidates passing Phase 1 proceed.

1. For each candidate and its A/B prompt pair, call the **tier that originally produced the source log event** with `N = 3` samples per side (6 calls total per candidate). When available, use `source.model` verbatim; otherwise fall back to strategic tier (`STS2_STRATEGIC_MODEL`, default `gemini-3.1-pro-preview`). Sampling with fast tier is **not** acceptable here: the whole point of Phase 2 is to check whether the skill changes decisions on the same model distribution that serves production — a fast-tier sample cannot validate a strategic-tier decision.
2. Parse each response through the decision-schema parser (same parser used at runtime, `allow_fallback=False`). Count `valid_A` and `valid_B`.
3. **Hard reject** if `valid_B < N` (i.e. any invalid B response). This encodes the hard-won PE lesson: never promote a change that destabilizes output.
4. Submit the `N × N = 9` cross-pair comparisons to a **fast tier** judge in a batch call with schema `{BETTER_B | SAME | WORSE_B}`. The judge stays fast tier because its job — relative preference classification — does not require strategic-tier reasoning depth.
5. Aggregate across all 9 judgments: promote iff `count(BETTER_B) ≥ 2 AND count(WORSE_B) ≤ 1`.

Budget: 6 strategic-tier calls + 9 fast-tier calls × (candidates passing Phase 1). Typical postrun produces ~10 candidates of which ~3-5 reach Phase 2 after Level 4 cascade + Phase 1, so expected budget is 18–30 strategic-tier calls + 27–45 fast-tier calls per postrun. Dominant cost is the strategic sampling: at Gemini 3.1 Pro ≈ $1.25/1M input and ~800 tokens per call that is ≈ $0.03 per postrun (still well under the overall per-run compute cost of gameplay).

### 8.4 Why this A/B is not PE resurrected

Documented negative result from `2026-04-18-pe-deprecation-negative-result.md`: 30/33 patches died on INVALID_B because the LLM author lacked a model of prompt-to-output mapping. Three differences here prevent the same failure mode:

| | PE A/B (removed) | Skill/Memory A/B (this spec) |
|---|---|---|
| Edit target | Prompt source code (.py files) — changes what the LLM must output | Retrieval-layer content added to user message — does not alter schema instructions |
| Test binding | Patches sampled against arbitrary cases | Each candidate tied to the exact log event that produced its learning signal |
| Structural gate | None — only response-quality judge | Phase 1 rejects duplicates / conflicts before any LLM call |
| Invalid-B handling | Logged then judged | Hard reject (returns candidate to Level 4 judge's rejection set) |

## 9. Legacy Seed Cleanup

One-time pass at the first run after this spec lands:

1. Embed every `src/skills/seeds/*.json` skill and every consolidated guide in `memory/guide_store.*` with `text-embedding-3-large`.
2. Run §4.3's L1/L2/L3 check against each. For any legacy entry with cosine ≥ 0.70 vs L1/L2/L3:
   - Set `confidence = 0.30` (so new skills can outcompete it on the Pareto frontier).
   - Set `legacy = true` metadata.
   - Do NOT delete — retained for ablation comparisons.
3. Report the count and file list to `data/evolution/legacy_demotion_2026-04-18.log`.

Does not touch L1/L2 itself — that is the separately tracked "L1/L2 slimming" TODO.

## 10. Novel Claims for Paper

Four claims, each supported by specific spec sections:

1. **Unconditional-layer overlap check** (§4.3, §4.5). Literature surveyed ([Voyager](https://arxiv.org/abs/2305.16291), [ExpeL](https://arxiv.org/html/2308.10144v2), [EvolveR](https://arxiv.org/html/2510.16079v1), [EvoSkill](https://arxiv.org/html/2603.02766v1), [WebXSkill](https://arxiv.org/html/2604.13318)) treats skill library and system prompt as independent stores. We pre-index L1/L2/L3 and reject any candidate that restates always-present content.
2. **Trigger-conditional dedup** (§4.2, §4.3). Same content under same trigger → merge; same content under disjoint triggers → coexist. Prior work flattens this distinction or does not model triggers at all.
3. **Cross-store conflict resolution** (§5). Existing methods handle within-store dedup only; no published method resolves contradictions across skills/guides/rules/card memory.
4. **Log-grounded A/B replay** (§8). Every candidate is validated against the exact prompt event that produced it. [PromptBreeder](https://arxiv.org/abs/2309.16797) and [EvoSkill](https://arxiv.org/html/2603.02766v1) A/B-test prompts against accuracy benchmarks; we A/B-test skills/memory against their original decision context, with a hard Phase 1 structure gate.

The 33/0 result from the deprecated PE pipeline (see `2026-04-18-pe-deprecation-negative-result.md`) is motivation: it shows why source-code prompt edits fail, and why validating retrieval-layer additions with the same rigor is the correct next design.

## 11. Implementation Sequence

Four commits, each independently testable.

**Commit 1 — `feat(write_gate): static span index + cascade levels 1-3`**
- `src/memory/write_gate.py` new module with `StaticSpanIndex`, `WriteGate` (levels 1-3 only, level 4 short-circuits to ACCEPT).
- Embedding client wrapper reusing `V2Backend` where possible; fall back to `text-embedding-3-small` via OpenAI-compatible relay.
- Integration: hook into `src/skills/discovery.py`, `src/memory/guide_consolidator.py`, `src/memory/rule_distiller.py` at persist time.
- Tests: exact-match, Jaccard edge cases, L1 overlap with synthetic spans.
- Ship: run a real postrun, diff skill/rule write rates, confirm no false rejects on existing content.

**Commit 2 — `feat(write_gate): batch judge + cross-store conflict + lifecycle`**
- Level 4 batch LLM judge with structured output schema.
- §5 cross-store conflict detection (structural + LLM).
- §6 Pareto frontier, confidence prune, proposal history injection.
- Tests: batch judge on synthetic conflict pairs; Pareto frontier eviction; prune threshold.

**Commit 3 — `feat(retriever): scope filter + legacy seed demotion`**
- §7 retriever scope filter in `src/memory/retriever.py`.
- §9 one-shot legacy demotion pass as CLI: `python -m scripts.demote_overlapping_seeds`.
- Tests: scope filter matrix correctness; fallback for un-tagged notes.

**Commit 4 — `feat(ab_replay): log-grounded skill/memory A/B`**
- §8 Phase 1 (deterministic) + Phase 2 (LLM).
- Invalid-B hard reject.
- Tests: Phase 1 on synthetic prompt deltas; Phase 2 with mocked LLM backend.
- **Gate test**: re-run the PE-era log pool through Phase 2 to confirm the invalid-B filter catches all 30 known bad patches (regression against PE failure mode).

After commit 4, Section 2/3/6/8 are live. Skills/memory written during the subsequent run go through the full pipeline.

## 12. What This Spec Does Not Cover

- **L1/L2 slimming** — migrating heuristics from static prompts to seed skills. Separate TODO in `CLAUDE.md`.
- **Cross-model generalization** — running the pipeline on GPT-5.4, Gemini 3.1, Qwen 3.5. Separate experiment spec (C2).
- **Personality analysis** — gameplay-trace behavioral dimensions. Separate experiment spec (C4).
- **Benchmark leaderboard** — STS2-Bench packaging. Separate deliverable (C3).
- **Dynamic tool validation** — `author_tool` has its own AST-sandbox + TEST_CASES path, not affected by this gate.

## 13. Decisions and Thresholds to Tune

### 13.1 Settled decisions (previously open questions)

1. **Embedding provider**: `text-embedding-3-large` (3072 dims, $0.26/1M tokens) via the OpenAI-compatible GPT relay at `STS2_GPT_BASE_URL`. The probe in §4.6 confirmed the relay serves this model correctly and produced expected-shape cosines on our workload. Chosen over the cheaper `3-small` because its tighter similarity band at the boundary region reduces the Level 4 judge's workload; per-postrun embedding cost remains < $0.0001. If accuracy is excessive, downgrade to `text-embedding-3-small` via the same relay without code change.
2. **Judge LLM tier**: **fast tier** (Gemini 3.1 Flash Lite) for the Level 4 write-gate cascade classifier and the Phase 2 pair preference judge. Classification-style tasks (ADD/UPDATE/MERGE/REJECT and BETTER_B/SAME/WORSE_B) do not require analysis-tier reasoning depth; fast tier cuts cost ~3×. **Phase 2 decision sampling is the exception**: the A and B completions must be drawn from the same tier that serves production for this state type, otherwise the quality signal measures a different model than the deployed one. ``make_sampler_for_event`` uses the source log event's exact model when present; default fallback is strategic tier (`STS2_STRATEGIC_MODEL`). Revised 2026-04-18 from the original "fast tier everywhere" answer.
3. **Phase 2 binding fallback**: on `source_log_event = NULL` (aggregated-statistic candidates), use the 5 most recent logged `llm_call` events of the same `state_type` as replay cases. Maintains uniform gating at the cost of weaker grounding — acceptable because aggregated-statistic candidates are a minority of postrun proposals.

### 13.2 Starting thresholds (recalibrate in commit 1 with 100–200 labeled candidates)

| Parameter | Spec starting value | Source |
|---|---|---|
| L1/L2/L3 overlap reject cosine | `0.70` | §4.6 probe with `text-embedding-3-large` |
| L1/L2/L3 LLM-judge zone | `[0.55, 0.70)` | §4.6 probe |
| L4/L5 auto-reject cosine | `0.85` | §4.6 probe |
| L4/L5 MERGE / coexist band | `[0.70, 0.85)` split on trigger Jaccard | §4.6 probe + WebXSkill structure |
| L4/L5 LLM-judge zone | `[0.55, 0.70)` | §4.6 probe |
| Trigger Jaccard same-context | `0.60` | WebXSkill / SAGE precedent |
| Pareto slot `k` | `3` | [EvoSkill](https://arxiv.org/html/2603.02766v1) |
| Confidence prune threshold | `0.30` | [EvolveR](https://arxiv.org/html/2510.16079v1) |
| Proposal-history window `N` | `20` | reasonable default, tune against LLM context budget |
| A/B replay samples `N` per side | `3` | user decision |
| A/B promote rule | `count(BETTER_B) ≥ 2 AND count(WORSE_B) ≤ 1` across 9 judgments | analogous to deleted PE defaults |
| Embedding model | `text-embedding-3-large` via `STS2_GPT_BASE_URL` | §13.1 |
