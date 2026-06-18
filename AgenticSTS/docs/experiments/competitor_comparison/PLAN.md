# Workstream C — Competitor comparison runs

**Goal**: run the cited open-source STS2 LLM agents **as their authors intended**, with **Gemini 3.1 Pro** at **A0**, **N=5** each, capturing all raw prompts/responses + game I/O. Serves (1) the **dataset** (diverse agent trajectories on the same game+model) and (2) the **arXiv comparison** rows vs our frozen-A0 cells.

**Status**: feasibility + author-intended-driver investigation complete (2026-06-05). Harness build in progress. No runs yet.

**Revised 2026-06-05** after user direction — supersedes the earlier "reuse our mod" plan.

---

## Decisions locked (user)

1. **Build each competitor's ORIGINAL mod from their source** — do NOT reuse our mod. Our mod is enhanced, and those enhancements are part of *our* contribution; using their unmodified mod keeps the comparison "their full system vs ours."
2. **Game-version coupling is not a fairness concern** — the version moved little, and our tested version may even be slightly harder. We will NOT discuss the version delta in the paper. We only make the **smallest possible compatibility edits** to each competitor mod so it loads on the current game version — **no substantive logic changes**, and **every edit documented** (paper transparency / appendix).
3. **Faithful agent path**: STS2MCP and CharTyr are driven by an MCP client + the authors' own skill/strategy docs (the authors used Claude Code/Desktop). We reproduce this with a **Gemini MCP host** (same pattern, Gemini for same-model fairness). AI-Spire is a self-contained mod (Gemini via its `config.json`). HermesBridge uses OpenCode + `SKILL.md` over file-IPC.
4. AI-Spire runs **Ironclad** as-shipped (its only character); documented. STS2MCP/CharTyr/HermesBridge run **Silent** (matches our headline).
5. **N=5** per cell. Compared (never pooled) against our existing frozen-A0 cells.
6. Fairness fixes approved (AI-Spire timeout→120 s + log RuleEngine fallbacks).

---

## What each competitor actually is (author-intended driver)

| Repo | Mod / interface | Author-intended agent | Skill/strategy docs | Learns? |
|---|---|---|---|---|
| **AI-Spire** | in-process C# mod (Harmony), own LLM client | the mod itself (config.json → OpenAI-compatible API) | prompt templates in `PromptBuilder.cs` | no |
| **STS2MCP** | C# mod (REST 15526) + Python MCP server (`mcp/server.py`, stdio) | **MCP client** (Claude Code/Desktop) | `.claude/commands/playsts2.md` + `AGENTS.md` + `GUIDE.md` | **yes** (updates GUIDE.md after bosses) |
| **CharTyr** | C# mod (HTTP 8080) + Python MCP server (`mcp_server/`, stdio or HTTP 8765) | **MCP client** | `skills/sts2-mcp-player/SKILL.md` + `references/` + `docs/game-knowledge/` | no (static docs) |
| **HermesBridge** | C# mod + file-IPC (`%APPDATA%`) | external coding agent (OpenCode) | `SKILL.md` | no |

---

## Cells we aim to produce

| Cell (experiment_tag) | Mod | Driver | Char | Context |
|---|---|---|---|---|
| `competitor-aispire-gemini-A0` | AI-Spire (built, patched) | native, Gemini via config.json | Ironclad | accumulating (40-msg) |
| `competitor-sts2mcp-gemini-A0` | STS2MCP (built, patched) | Gemini MCP host + playsts2/AGENTS/GUIDE | Silent | accumulating |
| `competitor-chartyr-gemini-A0` | CharTyr (built, patched) | Gemini MCP host + SKILL/playbooks | Silent | accumulating |
| `competitor-hermesbridge-gemini-A0` | HermesBridge (built, patched) | OpenCode + Gemini + SKILL.md | Silent | per-tick stateless |

All A0, N=5, Gemini 3.1 Pro, routed through the logging proxy. Each competitor uses **its own** strategy docs / learning loop (its strongest, fairest form). We hold constant: **model, difficulty, game, scoring** (`52/3`, victory=100).

---

## Harness

```
  competitor agent
    │  AI-Spire: C# HTTP client          STS2MCP/CharTyr: Gemini MCP host
    │  → OpenAI /v1/chat/completions     → MCP stdio tools + their skill docs → OpenAI /v1/chat/completions
    ▼
  logging proxy  (scripts/competitor_runs/logging_proxy.py :8129)  ── tees → captures/<run_id>/llm_calls.jsonl
    ▼
  our Gemini relay (STS2_GEMINI_BASE_URL)
```

- **C.1 logging proxy** (built, reviewed, fixed): uniform LLM-I/O capture for every cell. Streaming-safe (preserves `tool_calls`), run-id via `X-Run-Id`.
- **C.2b Gemini MCP host** (in progress): launches a competitor's stdio MCP server, discovers its tools, loads the competitor's own skill docs as the system prompt, drives with Gemini function-calling + accumulating context, captures MCP tool I/O. Powers the STS2MCP + CharTyr cells.
- **C.2 naive agent** (built): now a building block (its `GeminiClient`/`GameCapture`/trim are reused by the MCP host); no longer a standalone cell.
- **AI-Spire**: native; just point `config.json` at the proxy. Game I/O from its `verbose_logging` + whatever it puts in prompts.

---

## Critical path

1. **Build the competitor mods** (C.3b guide): minimal compat patches → load on current game version. User-side (toolchain + game), guided by the build doc.
2. **C.2b Gemini MCP host**: build + `--dry-run` (launch a server, `tools/list`, print discovered tools — no game needed).
3. **Per-cell smoke** (user): one short run each, confirm proxy + game I/O capture.
4. **N=5 batches** (user-in-loop, sequential ~1 hr/run; `agent-watchdog`/`/loop` can babysit).
5. **C.5 normalize + C.6 analyze**: fold competitor trajectories into the dataset; compute comparison rows.

---

## Fairness caveats to document (arXiv methods/limitations)

- **Each competitor uses its own mod + its own strategy docs + its own learning loop** — the comparison is "their full system vs ours," not a controlled single-variable ablation. Held constant: model (Gemini 3.1 Pro), difficulty (A0), game, scoring.
- **Minimal compatibility patches**: list every edit made to each competitor mod to load on the current game version; all are mechanical (symbol/signature/version-guard), none change agent logic. (Version delta itself not discussed — per decision #2.)
- **Character**: AI-Spire is Ironclad-only (documented); the others run Silent (matched to our headline).
- **AI-Spire timeout/fallback**: bumped to 120 s; RuleEngine-fallback firings counted and reported (a high-fallback run is not a clean LLM datapoint).
- **Interface differences** (in-process vs REST/MCP vs file-IPC) change latency/state granularity — part of each system's identity, not controlled.

---

## Isolation — complete replacement (MANDATORY)

Every competitor run uses ONLY that competitor's own mod; **our mod is fully removed** so the competitor agent reads only the competitor's state, never ours (fairness + no contamination — our mod's enrichments are our contribution). Only one mod can Harmony-patch the game at a time, so it is also a hard requirement. Per run: remove our mod from `<game>/mods/`, confirm `:8128/health` is dead, install only the target mod, confirm its own endpoint. The **Gemini MCP host enforces this** (aborts, exit 3, if `:8128` answers — override `--allow-our-mod`); for AI-Spire/HermesBridge (driven outside the host) apply manually. Each competitor server targets its own mod port (STS2MCP :15526, CharTyr :8080) — verified, no path to :8128. Full steps in `build_guide.md` § "Complete-replacement protocol".

## Operational division of labor

- **Me**: proxy, MCP host, configs, capture/normalization/analysis, build + patch guide. All no-game code/docs.
- **User**: build each competitor mod, run the game (sequential, ~1 hr/run, N=5/cell). I cannot launch Steam / watch a mod play.

---

## Dataset format

Per competitor run: `captures/<run_id>/` with `llm_calls.jsonl` (proxy), `game_io.jsonl` (MCP host) or native game log (AI-Spire), `meta.json`, and a `run_summary.json` matching our `runs/history.jsonl` schema (outcome/final_floor/character/ascension/model/**experiment_tag**) so competitor rows slot into `scripts/reproduce/*`. Tags: `competitor-<repo>-gemini-A0`.

---

## Open items

- Build feasibility per mod (C.3b) — minimal-patch points for the current game version.
- HermesBridge driver: OpenCode+Gemini through the proxy (confirm custom base-URL support) vs a file-IPC Gemini driver.
- N=5 sequential game-time budget (~5 hrs/cell of user keyboard time).
