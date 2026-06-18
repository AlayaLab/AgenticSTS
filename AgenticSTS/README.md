# AgenticSTS — the agent

The Python agent component of the [AgenticSTS monorepo](../README.md): a long-horizon
LLM agent that plays **Slay the Spire 2** through an in-game HTTP mod under a
**bounded memory contract** — every decision prompt is freshly composed by typed
retrieval from five knowledge layers; no raw cross-decision transcript is ever appended.

> Start with the [monorepo README](../README.md) for the paper framing, headline
> results, and the quick start. This file documents the agent itself: architecture,
> subsystems, configuration, data layout, and the operational playbooks.

---

## The bounded memory contract

Each decision `d` receives a fresh user message

```
u_d = π(L1, L2(s_d), L3(s_d), L4(s_d), L5(s_d))
```

assembled from five typed layers. With capped top-k retrieval per layer, the prompt
size is **independent of run length** — a transcript-appending interface grows
Ω(d·s̄) instead.

| Layer | Contents | Mutability | Path |
|---|---|---|---|
| **L1** | Role + protocol system prompts (COMBAT / COMBAT_BOSS / DECKBUILD / STRATEGIC) | Immutable | `src/brain/prompts/` |
| **L2** | State-typed decision prompts: schemas + legal action formats (reward, shop, map, event, …) | Immutable | `src/brain/prompts/` |
| **L3** | Game knowledge: cards, relics, monsters, events, keywords (patch-refreshed) | Static | `src/knowledge/`, `data/knowledge/` |
| **L4** | Episodic memory: postrun summaries keyed by (character × ascension × act × enemy) | Postrun-writable | `src/memory/` |
| **L5** | Skill library: triggered strategic guides with explicit trigger + prose policy | Gated-writable | `src/skills/` |

Because context reaches the model only through these named slots, **any single layer
can be ablated in isolation** — that is what makes the five-cell evaluation matrix
possible (see the monorepo README's Results section).

**Why L1/L2 are immutable.** A prompt-evolution pipeline once proposed 33
postrun-authored patches to L1/L2; **all 33 failed A/B validation**
(`docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`). Postrun LLM
critiques are reliable only when confined to the retrieval-augmented layers (L4/L5),
not the authoring-layer prompts. Humans can still edit L1/L2 via PR.

**No similarity-RAG over raw logs.** Near-identical-looking game states can have
opposite strategic meanings (card order, relic combos, route history), so the agent
retrieves *summaries and triggered guides*, never nearest-neighbor log snippets.

**Combat is the only intra-fight stateful object**, and even there the LLM sees
exactly 3 messages per round (`combat_start`, `"ok"`, latest user state) — earlier
rounds re-enter only through typed state and the Strategic Thread
(`src/brain/conversation.py`).

## Decision flow

```
observe (GET /state) ──> parse (frozen Pydantic GameState)
        ──> route by state type ──> compose u_d from L1..L5
        ──> LLM decision (tiered) ──> validate ──> act (POST /action)
```

A dispatcher routes each decision to one of four model tiers:

| Tier | Used for |
|---|---|
| `fast` | Trivial combat plays (≤2 playable cards), map steps, hand-select, treasure |
| `strategic` | Combat plans, shops, events, rest, card rewards, routing |
| `analysis` | Postrun memory extraction, guide consolidation, skill discovery |
| `evolution` | Postrun self-evolution tool-use loop |

The four L1 system prompts are static and prompt-cacheable; all per-run state lives in
the user message. Result: a median of ~67 strategic LLM calls per run instead of one
call per in-game action.

## Postrun pipeline (between runs, no gradients)

After each completed run, in order:

1. **Memory extract + guide consolidation** (cadence-gated) → L4
2. **Non-combat scoring + mistake-driven combat skill discovery** → L5 candidates
3. **Mode B stub fill** (`STS2_SEED_STUB_FILL_ENABLED`) — fills character-parametric
   skill templates → L5
4. **Self-evolution engine** (`STS2_EVOLUTION_ENABLED`) — write/query/dynamic-tool stages

L5 writes pass a 4-level write gate (exact → cosine → trigger Jaccard → LLM judge) and
a pre-write A/B replay gate (B=3 resample, strict 2/3 + zero-harmful). Mistake-driven
discovery (`src/skills/mistake_discovery.py`) flags combats whose `loss_ratio` exceeds
enemy/act baselines and routes them through an LLM critic before any write is proposed.

## Key subsystems

| Path | Purpose |
|---|---|
| `src/agent/loop.py` | Core observe → retrieve → decide → act loop; stuck recovery; postrun orchestration |
| `src/brain/v2_engine.py` | Sole decision engine; tier routing; decision JSON extraction |
| `src/brain/v2_backend.py` | Multi-provider backend (Anthropic + OpenAI-compatible relays) |
| `src/brain/conversation.py` | Bounded combat conversation (3 messages/round) |
| `src/brain/prompts/` | L1/L2 prompts + formatters |
| `src/brain/evolution_engine.py` | Postrun three-stage dispatch (write → query → dynamic) |
| `src/brain/dynamic_tools.py` | AST-sandboxed agent-authored Python tools (postrun-only; never exposed to gameplay) |
| `src/memory/` | L4 stores, extractors, retriever, guide consolidator, write gate |
| `src/skills/` | L5 library, mistake-driven discovery, dedup cascade, merge pipeline, replay evaluator |
| `src/skills/seeds/` | Cold-start seed skill files — the agent works with just these |
| `src/knowledge/` | L3 lookups (cards, monsters, potions, relics, events, keywords) |
| `src/mcp_client/` | HTTP client + SSE event stream to the C# mod |
| `src/state/` | Frozen Pydantic `GameState` + parser |
| `src/monitor/` | EventBus + FastAPI WebSocket server (dashboard backend, :8081) |
| `src/runs/` | Run history + ascension auto-progression stats |
| `scripts/run_agent.py` | Main CLI entry point |
| `scripts/run_ablation.py` | Five-condition ablation orchestrator with per-condition data isolation |
| `scripts/reproduce/` | Recompute the paper's tables/figures from the released archive |
| `scripts/competitor_runs/` | Faithful drivers + capture proxy for the accumulating-context baselines (STS2MCP, CharTyr) |
| `scripts/apply_patch.py` | Game-update patch pipeline |
| `scripts/inspect_memory.py` | Learned-store inspector |
| `external_calibration/` | Cached external difficulty anchors (AGI-Eval, community stats) with provenance |

## Configuration

Pick a model family and all four tiers resolve from the registry:

```bash
python -m scripts.run_agent --model-family gemini    # default
python -m scripts.run_agent --model-family gpt | qwen | deepseek | claude
```

| Family | fast | strategic | analysis |
|---|---|---|---|
| `gemini` (default) | `gemini-3.1-flash-lite-preview` (low) | `gemini-3.1-pro-preview` (medium) | `gemini-3.1-pro-preview` (high) |
| `gpt` | `gpt-5.4-mini` (low) | `gpt-5.4` (medium) | `gpt-5.4-thinking` (high) |
| `qwen` | `qwen3.5-27b` (off) | `qwen3.5-27b` (on) | routes to gemini |
| `deepseek` | `deepseek-v4-flash` (off) | `deepseek-v4-flash` (high) | routes to gemini |
| `claude` | `claude-haiku-4-5` (low) | `claude-sonnet-4-6` (medium) | `claude-sonnet-4-6` (high) |

Escape hatches: per-tier family override (`STS2_MODEL_FAMILY_FAST`), per-family effort
(`STS2_QWEN_EFFORT_STRATEGIC`), direct model override (`STS2_FAST_MODEL`), per-family
credentials (`STS2_GPT_API_KEY`, `STS2_GPT_BASE_URL`, …). Families without an
`analysis` tier auto-disable postrun.

Essentials (full list in `.env.example`):

```bash
ANTHROPIC_BASE_URL=...           # your provider or relay
ANTHROPIC_API_KEY=...
STS2_GEMINI_API_KEY=...          # or GPT / Anthropic native — whichever you have

STS2_DATA_REPO=../AgenticSTS-Data   # route learned stores to the data package
STS2_POSTRUN_ENABLED=true           # false = frozen-store evaluation mode
STS2_EVOLUTION_ENABLED=true
STS2_MONITOR_ENABLED=false
```

Switching the strategic/fast model **rehashes the model profile**, which resets
ascension progression to A0 for the new profile — intentional (a weaker model should
not inherit a stronger model's ascension credits).

## Data layout

With `STS2_DATA_REPO` set, all learned stores live in
[`../AgenticSTS-Data/`](../AgenticSTS-Data) (memory / skills / evolution / runs —
the released research artifact, CC-BY-4.0). Unset, they fall back to `data/` here for
local-only development.

Static data in this directory:

| Path | Notes |
|---|---|
| `data/knowledge/` | L3 game data. **Partially regenerated, not redistributed** — see [`data/knowledge/README.md`](data/knowledge/README.md): AGPL upstream files via `scripts/sync_upstream_data.py`, mechanics extracts via `scripts/extract_mechanics_from_dll.py` (requires owning the game) |
| `data/patches/` | Game-update manifests (YAML) |
| `data/version_compatibility.json` | Current `(game_version, mod_version)` pair |
| `.env` | Secrets — never committed; use `.env.example` |

## Game update playbook

When a new STS2 version ships:

```bash
python -m scripts.apply_patch --manifest data/patches/v<new>.yaml --dry-run   # 1. preview
python -m scripts.apply_patch --manifest data/patches/v<new>.yaml             # 2. snapshot + purge + LLM rewrite
cd ../AgenticSTS-Mod/STS2AIAgent && dotnet build -c Release                   # 3. rebuild + deploy mod
python -m scripts.sync_upstream_data --game-version v<new>                    # 4. resync L3
python -m scripts.check_mod_api_coverage                                      # 5. API coverage (mod running)
python -m pytest tests/regression/ -v                                         # 6. regression
python -m scripts.run_agent --steps 50 --runs 1                               # 7. live smoke
```

Invariants: every persistent record is traceable to a `(game_version, mod_version)`
pair; `--dry-run` never writes; entity-reference purge touches only records that
reference a changed entity.

## Testing

```bash
pytest                          # full suite
pytest tests/regression/ -v     # golden-log regression only
pytest -k write_gate            # topic filter
```

Golden logs live under `tests/fixtures/golden_logs/`; each has a checked-in
fingerprint — mismatched decision/error counts fail the build.

## Paper-relevant pointers

- **Reproduce the paper's tables/figures**: `scripts/reproduce/` (reads the released archive in `../AgenticSTS-Data/`)
- **Competitor baselines (accumulating-context)**: `scripts/competitor_runs/README.md` + `docs/experiments/competitor_comparison/RESULTS.md`
- **Prompt-evolution negative result (why L1/L2 are immutable)**: `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`
- **Write gate + retriever design**: `docs/superpowers/specs/2026-04-18-write-gate-and-retriever-filter-design.md`
- **Mistake-driven skill discovery**: `docs/superpowers/specs/2026-04-19-mistake-driven-skill-discovery-design.md`

## Contributing

See `AGENTS.md` for conventions. In short: one branch per concern,
conventional-commit prefixes, Ruff + pytest green before pushing. Changes to L1/L2
prompts require a written justification in the PR description.

## License

**Apache-2.0** (see [`LICENSE`](LICENSE)). The license of this directory does not
extend to [`../AgenticSTS-Mod/`](../AgenticSTS-Mod) (AGPL-3.0, inherited from
upstream) or [`../AgenticSTS-Data/`](../AgenticSTS-Data) (CC-BY-4.0) — see the
[monorepo README](../README.md#-license).
