# Repository Guidelines

Short-form contributor + agent runtime guide. For the user-facing project overview see `README.md`; for full internal architecture and playbooks see `CLAUDE.md`.

## Project Structure & Module Organization

- `src/` — Python agent runtime.
  - `agent/` drives the observe → decide → act loop (`loop.py`, `state_machine.py`).
  - `brain/` builds prompts (`prompts/`), owns the V2 decision engine (`v2_engine.py`) and multi-provider LLM backend (`v2_backend.py`), orchestrates post-run self-evolution (`evolution_engine.py`), and hosts dynamic tools (`dynamic_tools.py`, `tool_preprocessor.py`, `plan_verifier.py`).
  - `memory/` is the L4 HCM: domain stores + extractors + retriever + guide consolidator + write gate.
  - `skills/` is the L5 library: `mistake_discovery.py`, `prewrite_ab.py`, `merge_pipeline.py`, `dedup.py`, `composer.py`, `seeds/`.
  - `knowledge/` is L3 static game data lookups + `injector.py` for token-budgeted prompt injection.
  - `mcp_client/` talks to the C# mod's HTTP server; `state/` wraps the Pydantic game-state payload.
  - `monitor/` + `log/` provide the WebSocket EventBus + JSONL session logger.
- `scripts/` — CLI utilities: `run_agent.py`, `inspect_memory.py`, `apply_patch.py`, `sync_upstream_data.py`, `check_mod_api_coverage.py`, plus benchmarks, backfills, and A/B scripts.
- `tests/` — pytest suite; shared fixtures in `tests/conftest.py` and `tests/fixtures/`; golden-log regression under `tests/regression/` + `tests/fixtures/golden_logs/v0.5.3/`.
- `../AgenticSTS-Mod/STS2AIAgent/` — the C# game-mod fork in a sibling repo ([`ShandaAI/AgenticSTS-Mod`](https://github.com/ShandaAI/AgenticSTS-Mod), since 2026-04-29). Clone alongside this repo.
- `frontend/` — React 19 + Vite + Tailwind monitor dashboard on `:8081`.
- `docs/`, `data/`, `logs/` — design specs, generated state, and runtime logs.

## Current Project Status (as of 2026-04-20)

- **Main in-flight work**: write-gate reap + skill-merge pipeline. `defer_to_judge` candidates are held on `WriteGate._pending_skills` and reaped after the judge flush; `MERGE` delegates to `src/skills/merge_pipeline.py::run_merge_pair` with dual-anchor A/B validation. Gated by `STS2_WRITE_GATE_REAP_ENABLED` (default off until live smoke confirms).
- **Skill discovery path** (2026-04-19): cohort-based discovery (`cohort_discovery.py`, `hypothesis_store.py`, `evidence.py`) was removed; replaced by mistake-driven discovery (`src/skills/mistake_discovery.py` + `critic_prompt.py` + `prewrite_ab.py`). Any lingering references to cohort modules are stale.
- **Prompts are immutable to postrun** (2026-04-18 PE deprecation, 33/33 A/B failures). Postrun writes only to L4 memory / L5 skills / dynamic tools. L1/L2 prompts are human-authored and change only via PR or `scripts/apply_patch.py` for game-version updates. See `docs/superpowers/specs/2026-04-18-pe-deprecation-negative-result.md`.
- **C# mod event hover path**: `GameStateService.cs` uses `EventOption.HoverTips` as the primary extraction path for offered cards/potions/relics, with reflection fallback for subclasses. Text/local-JSON parsing is reserved for random rewards only.
- **Active roadmap** (see CLAUDE.md `Active TODOs`): EventMemory/EventGuide Python pipeline, Smith card upgrade comparison, self-evolution validation runs (10–20 games), EMNLP evaluation framework.

## Build, Test, and Development Commands

```bash
# Install
pip install -e ".[dev,monitor]"

# Run
python -m scripts.run_agent --steps 500 --runs 1        # single run (needs mod + .env)
python -m scripts.run_agent --steps 500                 # infinite loop
python -m scripts.run_agent --character Regent --ascension auto

# Inspect
python -m scripts.inspect_memory                        # learned memory state

# Tests
pytest                                                  # full suite
pytest tests/regression/ -v                             # golden-log regression
pytest -k write_gate                                    # topic filter
ruff check .                                            # before any PR

# C# mod
cd ../AgenticSTS-Mod/STS2AIAgent && dotnet build -c Release
```

Deploy the mod DLL + `.pck` to the game's `mods/` directory; the game must be closed while copying (the DLL is locked while STS2 is running).

## C# Mod Reverse Engineering

For any C# mod work, prefer reverse-engineering `sts2.dll` via `ilspycmd` (install via `dotnet tool install -g ilspycmd`) before assuming behavior is UI-only. Favor model-level extraction (`CardModel`, `RelicModel`, `PotionModel`, `EventOption.HoverTips`) over UI-node scraping. Use the upstream mod's `mcp_server/data/eng/*.json` localization (from CharTyr/STS2-Agent; not bundled in the trimmed `AgenticSTS-Mod/`) only as fallback for opaque random rewards. Reflection-based probes (`GameStateService` uses them for event-option fields) break silently across game updates — re-verify after any `sts2.dll` change.

## Coding Style & Naming Conventions

- Python: 4-space indent, Ruff-enforced (`pyproject.toml`), 100-char lines, `E/F/I/W` + import sort. `snake_case` for modules/functions/files, `PascalCase` for classes.
- Keep prompt builders under `src/brain/prompts/` (private formatters underscore-prefixed). Keep memory stores under `src/memory/`, skills under `src/skills/`.
- Immutability: game-state and memory records are frozen dataclasses. Create new objects rather than mutating.
- Short files are welcome (high cohesion, low coupling). Target 200–400 lines per file; split at 800.
- No comments that restate what the code does. Comments explain WHY — hidden constraints, workarounds, invariants.
- No mechanical fallbacks for shop/rest/card/event/map decisions — LLM must decide. Treasure and hand_select may use mechanical logic.

## Testing Guidelines

- Add new tests as `tests/test_*.py`; focus on observable behavior.
- Decision logic, parsers, memory extraction, and MCP/mod API contract changes **must** include at least one pytest case or a script-based regression check.
- `pytest-cov` is available but no minimum threshold is enforced. Treat meaningful coverage as required on the critical paths (skill discovery, write gate, merge pipeline, state parser).
- When a golden log breaks, investigate the decision count / state-type delta before updating the fingerprint. Don't rubber-stamp regression updates.

## Commit & Pull Request Guidelines

- Conventional-commit prefixes: `feat:`, `fix:`, `docs:`, `refactor:`, `test:`, `chore:`, `perf:`, `ci:`.
- Scope each commit to one concern. One logical change per PR.
- PRs should explain gameplay or API impact, list commands run for validation, and link related specs in `docs/superpowers/`. Include screenshots or log snippets for prompt/overlay/MCP changes.
- L1/L2 prompt edits require an explicit justification paragraph — the immutability rule applies to postrun, but human edits still need to state what broke and how the edit fixes it. Back changes with a test case when possible.
- Hooks are not skipped (`--no-verify`) without explicit opt-in.

## Security & Configuration Tips

- All credentials live in `.env` (see `.env.example` for the template). `.env` is in `.gitignore`; never commit it.
- Endpoints and models are configured via environment variables read in `config.py` — e.g. `ANTHROPIC_BASE_URL`, `ANTHROPIC_API_KEY`, `STS2_GEMINI_API_KEY`, `STS2_FAST_MODEL`, `STS2_STRATEGIC_MODEL`, `LLM_PROVIDER`.
- Changing `STS2_FAST_MODEL` / `STS2_STRATEGIC_MODEL` / `STS2_ANALYSIS_MODEL` rehashes the model profile and resets ascension progression to A0 for the new profile. This is intentional — don't hack around it.
- `data.snapshots/` is write-once (patch-pipeline output). Never overwrite, delete, or commit.
- Do not commit secrets, local logs, or per-run evolution caches. See the `data/` table in `README.md` for the commit-vs-ignore rule per subdirectory.

## Agent Usage (Claude Code / Codex / Sonnet Teams)

For repository exploration of unfamiliar subsystems, prefer dispatching the `Explore` agent (sonnet) in parallel across disjoint domains over sequential reads — skills / memory / write-gate / evolution / prompts / mcp / C# mod / frontend are independent enough to investigate concurrently. Follow the `superpowers:dispatching-parallel-agents` pattern: one agent per independent domain, each with a self-contained prompt and a fixed word-count target for the report.

For new features: brainstorm → plan (`superpowers:write-plan`) → TDD (`superpowers:test-driven-development`) → implement → `superpowers:requesting-code-review`. Skip any step only with explicit reason.
