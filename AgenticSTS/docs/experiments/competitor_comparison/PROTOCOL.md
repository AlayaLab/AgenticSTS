# Competitor baseline — run protocol (reviewer-grade)

Workstream C. This is the methodology a reviewer must accept for the competitor rows to
be a *fair baseline* and the released trajectories to be *useful data*. It pairs with
`PLAN.md` (scope), `build_guide.md` (build + isolation), and the harness in
`scripts/competitor_runs/`.

## One mod at a time

Each competitor cell runs alone: only that competitor's own mod is loaded; **our mod is
fully removed** (complete-replacement — see `build_guide.md` §protocol; the MCP host
hard-aborts if `:8128` answers). Reasons: (a) only one mod can Harmony-patch the game at
a time; (b) the competitor agent must read only the competitor's state, never our mod's
enrichments (those are our contribution). Run N=5 for one mod, **stop**, swap the mod,
run the next.

## The denominator is COMPLETED games (the load-bearing rule)

Win rate = victories / **completed** games, where a completed game is one that ran to an
in-game terminal:

| Outcome | Meaning | Counts? |
|---|---|---|
| `victory` | won the run | ✅ completed, counted |
| `defeat` | died in-game | ✅ completed, counted |
| `agent_abort` | the agent/driver gave up, got stuck, or our host errored | ❌ re-run |
| `max_steps` | hit the step cap without a natural end | ❌ re-run |
| harness error / no summary / mod crash / IPC fault | infrastructure, not gameplay | ❌ re-run |

Infrastructure failures are **not** counted as the baseline "losing" — they are discarded
and re-run until N=5 clean completed games are collected. This mirrors our own paper's
"first ten completed games per condition" rule. **Every attempt — completed or
discarded, with its reason — is recorded** in `captures/<tag>/batch_manifest.json`, so a
reviewer can see we did not hide aborts or count infra failures as losses.
`run_batch.py` enforces all of this automatically.

## Faithful to each competitor (don't cripple the baseline)

Each competitor runs in its **strongest, author-intended form**: its own mod, its own
skill/strategy docs as the system prompt (STS2MCP `playsts2.md`/`AGENTS.md`/`GUIDE.md`;
CharTyr `SKILL.md`/playbooks), its own tool surface, its own learning loop (e.g. STS2MCP
updates `GUIDE.md` after bosses). The **only** substitution is the model (Gemini 3.1 Pro,
matching our headline) and minimal mechanical compatibility patches to load on the
current build (every patch documented; no logic changes). We are the MCP client the
authors assumed (they used Claude Code/Desktop) — with Gemini.

## Held constant vs documented deviations

| Held constant | Documented deviation |
|---|---|
| Model: Gemini 3.1 Pro | AI-Spire character = Ironclad (repo supports only Ironclad); others = Silent |
| Difficulty: fixed A0 | Game build: competitors on the 2026-05-30 build; our 298 data on v0.103.1 (04-17). Treated as minor, not discussed in paper. |
| Scoring: `s=100` victory else `floor + (52/3)·bosses` | Interface: in-process (AI-Spire) vs REST/MCP (others) vs file-IPC (HermesBridge) — part of each system's identity |
| N=5 completed games | AI-Spire RuleEngine fallback: timeout raised to 120 s; fallback firings counted (a high-fallback run is not a clean LLM datapoint) |

## Fixed A0, not ascension-auto

Every run targets A0 (a fresh A0 game each time). We do **not** use ascension-auto
(advance-on-win) for the headline competitor rows: our headline is the fixed-A0 5-cell
table, so competitor rows must be fixed-A0 to slot in; advance-on-win would muddy the A0
denominator, and weak baselines do not climb anyway. (An ascension-ladder competitor
stream could be added later as a separate, non-headline comparison.)

## Capture (what makes the data useful)

Per run: `captures/<run_id>/` with `llm_calls.jsonl` (every raw prompt/response via the
logging proxy), `game_io.jsonl` (per-step state + tool call + result), `run_summary.json`
(runs/history.jsonl-shaped: outcome / final_floor / character / ascension / model /
`experiment_tag`). Released with the dataset; condition tag `competitor-<repo>-gemini-A0`.
The proxy capture is what lets a reviewer audit the *actual* prompts each baseline saw.

## Per-competitor procedure

**STS2MCP / CharTyr (MCP-host competitors):**
1. Remove our mod; confirm `:8128/health` dead. Build + install the competitor mod
   (`build_guide.md`). Start the game; confirm the competitor's own health endpoint
   (15526 / 8080). Leave it at the main menu.
2. Start the logging proxy: `python -m scripts.competitor_runs.logging_proxy`.
3. `python -m scripts.competitor_runs.run_batch --competitor sts2mcp --n 5`
   (or `chartyr`). It runs fresh A0 games until 5 complete, re-running aborts, then stops
   and writes the manifest. Swap the mod and repeat for the other.
4. If auto-embark between games fails (some menus may need a click), the manifest shows
   the discarded attempt's reason; start a fresh A0 run manually and the next attempt
   takes over.

**AI-Spire (native, Ironclad):** remove our mod; build + install AI-Spire; point its
`config.json` at the proxy (`api_endpoint` → `:8129`, `api_timeout_ms` 120000). Start an
Ironclad A0 run; it plays. After it ends, start the next A0 run (AI-Spire plays the
active run; batching is manual). 5 completed games; count RuleEngine fallbacks from its
verbose log.

**HermesBridge (Silent, stateless):** remove our mod; build + install; drive with OpenCode
(or equivalent) configured to Gemini via the proxy base URL, pointed at `SKILL.md`. 5
completed games. (Lowest priority; if the build is too costly, cite its existing Gemini
runs instead.)

## Anticipated reviewer objections → answers

- *"You counted infra failures as the baseline losing."* → No: denominator is completed
  games; aborts/errors are re-run and the full attempt manifest is released.
- *"You crippled the baselines."* → No: each runs its own mod + skill docs + learning
  loop; only the model is swapped (to ours) and minimal load-patches applied (listed).
- *"N=5 is too small."* → It is a diagnostic stream (like our cross-backbone N=5), read
  with Wilson CIs and corroborated by AGI-Eval's 0/45 frontier result on AI-Spire. If a
  competitor unexpectedly performs near ours, N is raised before any claim.
- *"Different game version than your data."* → One minor patch (05-30) after our 04-17
  data; judged immaterial to A0 difficulty; competitors all share the current build.
- *"The MCP driver is yours, not theirs."* → For STS2MCP/CharTyr the authors' intended
  driver IS a generic MCP client + their skill docs; we reproduce exactly that with
  Gemini. AI-Spire/HermesBridge use the authors' own agent/spec.
