# Competitor comparison runs (Workstream C)

Tooling to drive cited open-source StS2 LLM agents with **Gemini 3.1 Pro** at **A0**
and capture every prompt/response + game I/O for the open-source dataset release and
the arXiv competitor comparison. See `docs/experiments/competitor_comparison/PLAN.md`
for the full workstream plan and `feasibility_sts2mcp_chartyr.md` for the API contract.

## Components

| File | Role |
|------|------|
| `logging_proxy.py` | OpenAI-compatible reverse proxy. Sits between any agent and our Gemini relay; tees every `/v1/chat/completions` exchange to `captures/<run_id>/llm_calls.jsonl`. Streaming-safe. Run id via `X-Run-Id` header. |
| `naive_gemini_agent.py` | The **baseline** agent: a bare accumulating-context Gemini function-calling loop over our mod's REST API. NO memory, NO skills, NO L1–L5 stack — the cleanest ablation of what our full stack adds, and the accumulating-context datapoint. Also a **building block**: the MCP host reuses its `GeminiClient`, `GameCapture`, and `_trim_messages`. |
| `mcp_gemini_host.py` | The **Gemini MCP host** (C.2b): launches a competitor's own stdio MCP server, discovers its tools, loads the competitor's own skill docs as the system prompt, and drives the run with Gemini 3.1 Pro over one accumulating transcript. Powers the **STS2MCP** and **CharTyr** cells. |

Captures land in `scripts/competitor_runs/captures/<run_id>/`.

## Naive Gemini agent

A minimal, self-contained driver (stdlib + `httpx` only; does **not** import our
`src/` stack). It mirrors the CharTyr-lineage mod contract our `src/mcp_client/`
speaks: `GET /health`, `GET /state`, `GET /actions/available`, `POST /action`, with the
`{ok, request_id, data}` / `{ok, error}` envelope and integer-index targeting
(`card_index` / `target_index` / `option_index`).

The whole point is **accumulating context**: one `messages` transcript grows for the
entire run — system prompt, then alternating assistant tool-calls and tool results,
never reset between decisions or combats. This contrasts with our own agent's bounded
per-decision composition.

Three tools are exposed to the model: `get_state()`, `get_available_actions()`, and
`take_action(verb, params)`. The system prompt is deliberately neutral ("You are
playing Slay the Spire 2. Win the run. Use the provided tools…") — no strategy, card
knowledge, or memory.

### Usage

```bash
# 0. Start the logging proxy (separate terminal). Needs STS2_GEMINI_BASE_URL +
#    STS2_GEMINI_API_KEY in .env (the proxy resolves the upstream Gemini relay).
python -m scripts.competitor_runs.logging_proxy --port 8129

# 1. Smoke-test connectivity BEFORE committing to a full run. Hits the mod's
#    /health and does a trivial 1-message Gemini call through the proxy, prints
#    both, and exits. (Needs the game+mod up for the /health half; the LLM half
#    needs only the proxy.)
python -m scripts.competitor_runs.naive_gemini_agent --dry-run

# 2. Full run. Start StS2 with our mod, set Silent + A0 in-menu (or let the agent
#    script setup), then:
python -m scripts.competitor_runs.naive_gemini_agent \
    --character Silent --ascension 0 \
    --mod-url http://127.0.0.1:8128 \
    --proxy-url http://127.0.0.1:8129/v1 \
    --model gemini-3.1-pro-preview \
    --run-id charext-naive-gemini-001 \
    --condition-tag competitor-charterext-gemini-A0
```

The API key is read from `--api-key` or `$STS2_GEMINI_API_KEY`. The run id is sent on
the `X-Run-Id` header so the proxy tags LLM captures to the same `captures/<run_id>/`
directory the agent writes game I/O to.

### Run setup (character / ascension / embark)

The agent makes a **best-effort** attempt to script menu setup via the discrete
`open_character_select` → `select_character{option_index}` → `embark` verbs (with
`increase_ascension` / `decrease_ascension` to reach the target). **A0 is the ascension
floor**, so on a fresh profile no ascension change is needed. If a saved run exists it
`continue_run`s into it. If the menu state can't be scripted, **start the run manually
in-game (character + A0 + embark)** and the agent takes over as soon as it detects an
active (non-menu) screen.

### Captures

| File | Written by | Contents |
|------|-----------|----------|
| `captures/<run_id>/llm_calls.jsonl` | proxy | one record per LLM completion (verbatim request + assembled response) |
| `captures/<run_id>/game_io.jsonl` | agent | one record per step: `{seq, ts, state_summary, available_actions, chosen_action, action_result}` |
| `captures/<run_id>/run_summary.json` | agent | run-history-shaped summary: `outcome` (victory/defeat/agent_abort/max_steps), `final_floor`, `act_reached`, `character`, `ascension`, `model`, `condition_tag`, `steps`, `started_at`, `ended_at`, `stuck_aborts` |

### Termination & safety

- Ends on **victory**, **death**, or `--max-steps` (default 800).
- **Stuck guard**: aborts cleanly (`outcome=agent_abort`) after the same action body
  repeats `--stuck-repeat` times in a row (default 8) — it never hangs.
- **Context cap**: `--max-context-messages` (default 400) trims only the *oldest*
  non-system messages if exceeded, logging when it fires. Default behaviour is to
  accumulate.

### Notes / caveats

- This is **our** minimal driver over the CharTyr interface, not a published agent —
  frame it as "a baseline agent over their interface" (see PLAN.md fairness caveats).
- Same model, same difficulty (A0), same scoring across all competitor cells — those
  are the controlled variables.

## Gemini MCP host (STS2MCP / CharTyr)

`mcp_gemini_host.py` drives the **STS2MCP** and **CharTyr** competitor agents **as their
authors intended** — each competitor's *own* stdio MCP server plus its *own*
skill/strategy docs as the system prompt — but with **Gemini 3.1 Pro** as the model
(matching our paper headline). The authors play these through an MCP client (Claude Code
/ Desktop) + skill docs; this host *is* that client, with Gemini swapped in, so the
comparison holds model / difficulty (A0) / game / scoring constant while each system uses
its strongest, fairest form. See `docs/experiments/competitor_comparison/PLAN.md` (C.2b).

### Dependency

Uses the official **MCP Python SDK** as the stdio client (`stdio_client` + `ClientSession`):

```bash
pip install mcp
```

Each competitor server is launched with **`uv`** (it reads the competitor's pinned
`pyproject.toml`/`uv.lock` and runs the server in an isolated venv), so `uv` must be on
PATH — see each competitor's README (`pip install uv`, or `brew install uv` on macOS).
The competitor repos must be cloned under `--competitor-root` (default
`paper/competitors/`, gitignored): `STS2MCP/` and `CharTyr/`.

### Per-competitor registry (verified)

| `--competitor` | Server launch | Skill docs → system prompt | Terminal detection |
|---|---|---|---|
| `sts2mcp` | `uv run --directory <root>/STS2MCP/mcp python server.py` | `.claude/commands/playsts2.md` + `AGENTS.md` + `GUIDE.md` (created by the agent after bosses — absent in a fresh clone, loaded if present) + `docs/raw-simplified.md` | `get_game_state(format="json")` → `state_type == "game_over"` |
| `chartyr` | `uv run sts2-mcp-server` (cwd `<root>/CharTyr/mcp_server`) | `skills/sts2-mcp-player/SKILL.md` + `references/screen-playbooks.md` + `docs/game-knowledge/playbook.md` | `get_game_state()` → `screen == "GAME_OVER"` |

The host exposes **all** of each server's discovered tools to Gemini (10 for CharTyr's
guided profile; 64 for STS2MCP including the `mp_*` multiplayer set) — faithful to what
the author's agent saw. Victory-vs-defeat is a best-effort keyword/field scan once a run
is known over (neither server exposes a clean victory boolean in its documented state);
`--max-steps` and the stuck guard are always honored independently, so a missed terminal
never hangs the run.

### Usage

```bash
# 0. Start the logging proxy (separate terminal; same as for the naive agent).
python -m scripts.competitor_runs.logging_proxy --port 8129

# 1. Smoke-test the MCP wiring — NO game required. Launches the competitor's server,
#    does the handshake + tools/list, prints the discovered tool names and the
#    assembled system-prompt length, then exits. Fails with an actionable message if
#    `uv`/deps are missing.
python -m scripts.competitor_runs.mcp_gemini_host --dry-run --competitor chartyr
python -m scripts.competitor_runs.mcp_gemini_host --dry-run --competitor sts2mcp

# 2. Full run. Start StS2 with THAT competitor's mod loaded (see the competitor's own
#    build/install README), then let Gemini drive setup (character select + embark) and
#    play. The skill docs instruct the setup; pass the target character/ascension:
python -m scripts.competitor_runs.mcp_gemini_host \
    --competitor chartyr \
    --character Silent --ascension 0 \
    --proxy-url http://127.0.0.1:8129/v1 \
    --model gemini-3.1-pro-preview \
    --run-id competitor-chartyr-gemini-001
    # --experiment-tag defaults to competitor-chartyr-gemini-A0

python -m scripts.competitor_runs.mcp_gemini_host \
    --competitor sts2mcp \
    --character Silent --ascension 0 \
    --run-id competitor-sts2mcp-gemini-001
```

The API key is read from `--api-key` or `$STS2_GEMINI_API_KEY`. The run id is sent on the
`X-Run-Id` header so the proxy tags LLM captures into the same `captures/<run_id>/`
directory the host writes game I/O to. Use `--competitor-root` if the competitor clones
live elsewhere, and `--skill-docs <paths…>` to override which docs become the system prompt.

### Accumulating context

ONE `messages` transcript grows for the whole run: `system` = the competitor's
concatenated skill docs, then alternating assistant tool-calls and `role:"tool"` results,
**never reset** between decisions or combats. `--max-context-messages` (default 400)
trims only the *oldest whole cycles* (reusing the naive agent's `_trim_messages`, which
cuts only on `user` boundaries so tool-call/result pairing is never broken). This
contrasts with our own agent's bounded per-decision composition.

### Captures

| File | Written by | Contents |
|------|-----------|----------|
| `captures/<run_id>/llm_calls.jsonl` | proxy | one record per Gemini completion (verbatim request + response) |
| `captures/<run_id>/game_io.jsonl` | host | one record per step: `{seq, ts, state_summary, available_actions, chosen_action, action_result}` (MCP tool calls/results) |
| `captures/<run_id>/run_summary.json` | host | run-history-shaped: `competitor`, `outcome` (victory/defeat/agent_abort/max_steps), `final_floor`, `act_reached`, `character`, `ascension`, `model`, `experiment_tag`, `steps`, timings, `stuck_aborts` |

### Termination & safety

- Ends on **victory**, **defeat** (per the competitor's state tool), or `--max-steps`
  (default 800).
- **Stuck guard**: aborts cleanly (`outcome=agent_abort`) after the same tool+args repeat
  `--stuck-repeat` times in a row (default 8).
- **Timeouts everywhere**: `--handshake-timeout` (initialize) and `--tool-timeout` (per
  `tools/call`) — the host never hangs.
- The synchronous `GeminiClient` is called via `asyncio.to_thread`, so the async event
  loop is never blocked while the model thinks.

### Notes / caveats

- Each competitor uses **its own** server + skill docs (its strongest, fairest form) — the
  comparison is "their full system vs ours," not a single-variable ablation (PLAN.md
  fairness caveats). Held constant: model (Gemini 3.1 Pro), difficulty (A0), game, scoring.
- STS2MCP's `GUIDE.md` is **written by the agent after boss fights** and is absent in a
  fresh clone; the host loads it only if present (a warning is logged otherwise). This is
  the author-intended behavior (the `/playsts2` command tells the agent to create it).
- CharTyr's `docs/game-knowledge/*.md` cross-references (cards.md, monsters.md, …) use
  absolute Mac paths in the upstream docs and are not in this clone — the host loads the
  docs that exist (`SKILL.md`, `screen-playbooks.md`, `playbook.md`).
