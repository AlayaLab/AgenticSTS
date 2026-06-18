# Competitor Comparison — Results (STS2MCP, CharTyr)

**Status:** complete for 2 of the 3 candidate competitors (AI-Spire skipped — see §7).
**Date:** 2026-06-09. **Machine-readable:** `RESULTS.json` (this dir). **Protocol:** `PROTOCOL.md`.

---

## 1. Headline

Two open-source accumulating-context StS2 agents, run **faithfully** (their own code + their own
skill docs) on **Gemini 3.1 Pro** at **Ascension 0, The Silent**, N=5 completed games each:

| Agent | Memory model | Wins | Mean floor | Median floor | Mean score¹ | Bosses (Σ) | Mean decisions/run |
|---|---|---|---|---|---|---|---|
| **Ours** (`full-frozen` cell) | bounded typed per-decision retrieval | **6/10**² | — | — | **82.1** | — | ~570 |
| **STS2MCP** (Gennadiyev) | full accumulating transcript | **0/5** | 17.6 | 17 | 21.1 | 1 | 625 |
| **CharTyr** (CharTyr/STS2-Agent) | full accumulating transcript | **0/5** | 5.6 | 6 | 5.6 | 0 | 106 |

¹ Paper score: `100` if victory else `floor + (52/3)·bosses`; bosses = 0 (floor<18), 1 (<34), 2 (else), 3 (win).
² Ours from the submitted paper's fixed-A0 matrix (3/10→6/10 with L5); same character/ascension/backbone.

**Takeaway:** both accumulating-context competitors win 0/5 at A0 Silent, with an observed gradient —
ours (6/10) > STS2MCP (reaches Act 2, 1 boss across 5) > CharTyr (dies in Act 1). Under these
disclosed, non-matched operational settings (different patch, routing, thinking effort, decision
batching, and prompt cadence — see §Setup), the public transcript-agent baselines did not reach the
same long-horizon endpoints. This is an operational comparison of shipped systems, not a controlled
ablation isolating the memory contract; that matched comparison is left to follow-up work.

---

## 2. Setup (faithful replication)

- **Backbone:** all STRATEGIC decisions on `gemini-3.1-pro-preview` for every agent; our agent
  additionally routes trivial decisions to `gemini-3.1-flash-lite-preview` (fast tier) and sets
  explicit thinking effort (low/medium), while competitors run at the provider default with no
  thinking parameter (their author-intended configuration). Competitor traffic flows via an
  OpenAI-compatible relay through a transparent logging proxy (`logging_proxy.py`, `:8129`) that
  captures every `/v1/chat/completions` exchange.
- **Game build:** our cells (2026-05-08..14) ran on Slay the Spire 2 `v0.103.1`; the game received a
  minor patch on 2026-05-30 (`v0.103.3` — content `.pck` + `sts2.dll` replaced, no further update
  since), so the competitor runs (2026-06-08..10) ran on `v0.103.3`. Competitor mods were *compiled*
  against the `v0.103.1`-pinned reference assemblies (see `build_guide.md`) and loaded/ran cleanly on
  the live `v0.103.3` game. The two batches therefore differ by two minor patches of the same
  `v0.103.x` line — same character, ascension, and decision surface; a same-build re-verification of
  our own stack on `v0.103.3` is recorded in `runs/history.jsonl` (smoke run, 2026-06-12).
- **Condition:** singleplayer, **The Silent, Ascension 0**, fresh run each game.
- **Driver:** each competitor's *author-intended* setup — their MCP server + their own skill/strategy
  docs as the system prompt, an LLM driving via their tools (`mcp_gemini_host.py`). STS2MCP docs =
  `playsts2.md` + `AGENTS.md` + `docs/raw-simplified.md`; CharTyr docs = `SKILL.md` +
  `screen-playbooks.md` + `playbook.md`. **No content from our project is injected** (verified: a leak
  scan for 20 of our-project markers over the full request found none).
- **Complete replacement:** exactly one mod loaded at a time; our mod (`:8128`) hard-confirmed dead
  before every run (the host aborts otherwise). STS2MCP serves `:15526`, CharTyr `:8080`.
- **Denominator = completed games** (victory / defeat / decision-capped), matching our own "first N
  completed per condition" rule; harness failures (aborts, crashes) are re-run, never counted as losses.
- **Decision cap:** 2500 (a full StS2 run is ~1500–2000 decisions; the cap lets runs reach a natural
  terminal). All 10 runs ended in a **natural in-game defeat** well under the cap — none hit it.

---

## 3. Results (per run)

**STS2MCP** — N=5, 0 wins, all natural defeats:

| run | outcome | floor | bosses | score | decisions |
|---|---|---|---|---|---|
| a01 | defeat | 28 | 1 | 45.3 | 1103 |
| a02 | defeat | 11 | 0 | 11.0 | 468 |
| a03 | defeat | 15 | 0 | 15.0 | 477 |
| a04 | defeat | 17 | 0 | 17.0 | 594 |
| a05 | defeat | 17 | 0 | 17.0 | 483 |

STS2MCP plays competently through Act 1 (a01 cleared the Act-1 boss, died at floor 28 in Act 2); high
variance (floor 11–28). Plays slowly (~35 decisions/floor) and re-reads state frequently.

**CharTyr** — N=5, 0 wins, all natural defeats:

| run | outcome | floor | bosses | score | decisions |
|---|---|---|---|---|---|
| a01 | defeat | 6 | 0 | 6.0 | 89 |
| a02 | defeat | 5 | 0 | 5.0 | 130 |
| a03 | defeat | 6 | 0 | 6.0 | 113 |
| a04 | defeat | 6 | 0 | 6.0 | 101 |
| a05 | defeat | 5 | 0 | 5.0 | 95 |

CharTyr dies early in Act 1 (floor 5–6) every run. Its tool interface returns frequent
`invalid_action` / `invalid_target` (HTTP 409) errors that the agent does not recover from well,
compounding into early death — a property of CharTyr's agent + interface, faithfully reproduced.

---

## 4. Cost

- **Total experiment spend (relay billing):** **$300.57** — includes all debugging/restart overhead
  (several crashes/reboots, one discarded mislabeled run, harness iteration). Per-*valid*-run cost is
  much lower (CharTyr runs are short, ~106 decisions → cheap; STS2MCP's deep runs dominate spend).
- **Exact token counts per run** are in `RESULTS.json` (released): STS2MCP ≈ 464M total prompt+completion
  tokens over 5 runs; CharTyr ≈ 84M. Provider-reported cache hits cover **90% (STS2MCP) / 82% (CharTyr)**
  of prompt tokens, so report cost under TWO conventions: **raw ingested context** (the volume the model
  attends to) and **fresh non-cached tokens** (the defensible billing-side cost). Fresh-token cost per
  score point: ours ≈ 6.4k (estimated, paper Fig-3 5k/call convention) vs STS2MCP 422k / CharTyr 571k
  (~66–90×). Even pricing EVERY recorded action of ours as a full 5k strategic call (upper bound), the
  gap stays ≥ 7×. See `paper/arxiv_2026/competitor_comparison/metrics.json` for both conventions per run.
- **Note for the paper:** the accumulating-context design's per-decision latency and token use grow with
  the run; this is itself evidence for the bounded-memory contract (our agent's context does not grow
  unboundedly across decisions).

---

## 5. Harness fixes (transparency)

All fixes below are in **our driver/harness** (`mcp_gemini_host.py`), **not** in competitor code — the
competitors' agent logic and skill docs are untouched, so faithfulness is preserved. They correct how we
*read/record* the competitors' output, not how they play:

1. **State unwrap** — STS2MCP returns state as `{"result": "<json string>"}`; terminal/floor detection
   now unwraps it (`_unwrap_state`). Before this, `game_over` was never detected (runs forced to the cap)
   and floor recorded as 0.
2. **Victory/defeat classification** — use the structured `game_over.is_victory` flag. A prior substring
   scan matched `"victory"` inside the key `"is_victory"`, mislabeling **all** CharTyr defeats as wins;
   corrected from ground truth (no re-run — the runs are real early deaths).
3. **"Started" gate** — a run's terminal/floor is only honored once a real in-run state is seen (not the
   menu, not a *leftover* `game_over`/`GAME_OVER` from the previous run). Handles both STS2MCP
   (`state_type`) and CharTyr (`screen`). Prevents the previous run's death screen from being re-counted.
4. **Fresh-run mandate** — the host prompt requires a new run from character-select; never `continue` a
   saved run. Plus per-run save cleanup. Prevents cross-run contamination.
5. **Resume + detached execution** — `run_batch` re-attaches to completed runs on disk (never
   re-runs/overwrites good data); proxy+batch run as detached OS processes that survive Claude-session
   restarts. Makes the multi-hour runs robust to interruptions (reboots still require a manual relaunch,
   which then resumes automatically).

---

## 6. Faithfulness & limitations

- **Faithful:** competitors run their own code + their own author-written skill docs, their own MCP
  tools, same backbone as ours. Only minimal load-compatibility was needed to run on the current game
  build; no substantive logic changes.
- **N=5 per competitor** (vs N=10 for our headline fixed-A0 cells) — smaller sample; reported as such.
- **Character = The Silent, A0** for matched comparison (our headline character).
- **CharTyr a02–a05 outcome inference:** a01's defeat is confirmed from its captured
  `game_over.is_victory=false`; a02–a05's terminal state landed on a host-side poll (not captured in
  `game_io`), so their defeat is established from floor 5–6 (a victory requires ~floor 50) plus the
  absence of any `is_victory:true` anywhere in their captures. All raw captures are released for audit.
- **Decision-economy asymmetry:** competitors issue one LLM call per decision (by design); our agent
  drives ~570 actions/run with ~100 strategic calls (plan execution, fast tier, heuristics). Part of the
  speed/cost gap is therefore decision batching — reported as a property of the memory-architecture
  package, not of the backbone.
- **Wall-clock decomposition:** 96% of competitor wall-clock is provider-reported LLM latency (sum of
  per-call `latency_ms` vs `duration_seconds`), with a fixed inter-action delay (ours 0.6s, competitors
  0.5s — slightly favoring competitors); our durations exclude postrun (disabled for frozen cells). All
  runs serialized on the same machine.
- **AI-Spire skipped** (user decision): it is a self-contained in-process mod with no menu navigation
  (manual per-run start) and is likely Ironclad-only (character mismatch). Two competitors + our naive
  accumulating-context baseline are sufficient for the comparison.

---

## 7. Released artifacts (per run, under `scripts/competitor_runs/captures/<run_id>/`)

- `llm_calls.jsonl` — every Gemini request/response (full prompts + responses + token usage + latency).
- `game_io.jsonl` — per-step game state, chosen action, action result.
- `run_summary.json` — outcome, final floor, act, steps, duration (CharTyr outcomes carry
  `outcome_corrected` + `correction_note`).
- `captures/<tag>/batch_manifest.json` — per-competitor batch manifest (denominator, discards).
- `RESULTS.json` (this dir) — consolidated per-run + aggregate stats.
