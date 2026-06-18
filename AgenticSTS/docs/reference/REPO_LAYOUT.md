# Repository layout

Reference for the multi-repo setup and ops workflows. For module locations see [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Three-repo setup

| Repo | Local path | Contents | Notes |
|------|------------|----------|-------|
| Main agent | `AgenticSTS/` (this repo) | Python code + static data | What you're reading |
| Data sibling | `../AgenticSTS-Data/` | Dynamic memory, skills, evolution, runs | `ShandaAI/AgenticSTS:AgenticSTS-Data`; gitignored on main side |
| Mod sibling | `../AgenticSTS-Mod/` | C# mod fork | `ShandaAI/AgenticSTS:AgenticSTS-Mod`, fork of `CharTyr/STS2-Agent` |

## Setup for a new machine

```bash
git clone git@github.com:<user>/STS2Agent.git
git clone https://github.com/ShandaAI/AgenticSTS (data in AgenticSTS-Data/) ../AgenticSTS-Data
git clone git@github.com:ShandaAI/AgenticSTS:AgenticSTS-Mod.git ../AgenticSTS-Mod

export STS2_DATA_REPO=$(cd ../AgenticSTS-Data && pwd)
export STS2_MACHINE_ID=$(hostname -s)  # optional; default is auto-derived short hostname
```

## Data sibling (`ShandaAI/AgenticSTS:AgenticSTS-Data`)

As of 2026-04-22, all dynamic data lives in this sibling so multiple machines can evolve in parallel without race-conditioning a single repo.

### Layout (paths are at sibling root, no `data/` prefix)

```
memory/
  rules.json
  v2/
    combat_episodes.jsonl
    route_memories.jsonl
    card_builds.jsonl
    event_memories.jsonl
    guides.json
    card_memories.json

skills/
  skills.json
  skill_usage.jsonl

evolution/
  evolution_log.jsonl
  reap_log.jsonl
  stub_fill_log.jsonl
  tools/*.py
  proposals/
  tool_stats.json
  retirement_state.json

runs/
  history.jsonl
  ascension_stats.json

experiments/<tag>/<condition_id>/   # Per-ablation isolated data (self-evolve only)
  memory/
  skills/
  evolution/
```

### Static data (stays in main repo)

```
data/
  knowledge/                # Upstream-synced game DB (cards.md, monsters.md, ...)
  patches/                  # Authored game-update manifests (v0.103.1.yaml, ...)
  version_compatibility.json
  reports/                  # Local audit output (e.g. card note audits)
```

### Per-machine local-only (gitignored on both sides)

```
data/batch_pending.json          # Local batch state
logs/run_*.jsonl                 # Per-run JSONL logs
```

`data/skill_discovery_counter.json` was retired with the non-combat discovery pipeline (2026-04-23). File may exist on disk from older runs but is no longer read or written.

## Path resolution

Every store accessor routes through `src/storage/paths.py`:

- `STS2_DATA_REPO=<abs path>` → use sibling repo
- Unset → fall back to `<main repo>/data` (local-only development mode)
- `STS2_MACHINE_ID` defaults to short hostname; override per machine for clear provenance in commit messages

For multi-machine reconcile: per-file merge drivers (e.g. `append_dedup` for `runs/history.jsonl`) are configured in the sibling repo's `.gitattributes`. `dict_counter_merge` for `ascension_stats.json` is TODO.

## Mod sibling (`ShandaAI/AgenticSTS:AgenticSTS-Mod`)

As of 2026-04-29, the C# mod is a separate fork. The split lets the mod sync with upstream cleanly (plain `git merge upstream/main`) without dragging the outer agent repo through merges.

It used to live under `STS2-Agent-Fork/` inside this repo; that path no longer exists.

### Build

```bash
cd ../AgenticSTS-Mod/STS2AIAgent
dotnet build -c Release
```

Requires STS2 game DLLs at: `C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2/data_sts2_windows_x86_64/`. Override path: `STS2_DATA_DIR` env var before building.

### Deploy

Copy `../AgenticSTS-Mod/STS2AIAgent/bin/Release/net9.0/STS2AIAgent.dll` → game's `mods/` directory, then launch STS2.

Pre-built DLL + .pck also tracked at `../AgenticSTS-Mod/build/mods/STS2AIAgent/` for clone-and-deploy workflows.

### Custom files (our modifications)

- `Game/GameActionService.cs`
- `Game/GameStateService.cs`

### API

HTTP REST at `localhost:8128` — `GET /state`, `POST /action`, `GET /events/stream`.

Mod default port changed 8080 → 8128 on 2026-04-28 to avoid Clash / common proxy collisions. `--api-port=auto` picks any free port via `STS2_API_PORT`.

### Upstream sync workflow

In `../AgenticSTS-Mod`:

```bash
git fetch upstream                              # CharTyr/STS2-Agent
git merge upstream/main                         # resolve, commit
cd STS2AIAgent && dotnet build -c Release       # rebuild
git tag upstream-sync-$(date +%Y-%m-%d) upstream/main
git push origin main --tags
```

Why merge (not rebase): multiple machines pull from `ShandaAI/AgenticSTS:AgenticSTS-Mod`; force-pushes after rebase break their clones. See `../AgenticSTS-Mod/VENDOR.md` for the full sync workflow. Tag `fork-base` permanently anchors the merge-base commit (`30e39ea`).

### Reverse-engineering rule

For C# mod work, inspect `data_sts2_windows_x86_64/sts2.dll` with `ilspycmd` before assuming behavior is UI-only. Prefer model-level extraction over hover-node scraping; keep `../AgenticSTS-Mod/mcp_server/data/eng/*.json` as fallback only for opaque random rewards.

### Event preview

Event hover previews are sourced from `MegaCrit.Sts2.Core.Events.EventOption.HoverTips`. `NEventOptionButton.OnFocus()` only renders those tips through `NHoverTipSet.CreateAndShow(...)`. `CardHoverTip.Card` exposes a real `CardModel`; potion and relic hover tips expose `CanonicalModel`, which can be checked for `PotionModel` / `RelicModel`.

C# extraction landed: `GameStateService.cs::GetEventHoverTips` + `ExtractEventHoverTipCards/Relics/Potions` with reflection fallback for subclasses.

## Game update playbook

When STS2 releases a new version, run this pipeline:

1. **Author manifest.** Paste patch notes into a Claude session, generate `data/patches/v<new>.yaml` using the Manifest model schema. Commit.
2. **Dry run.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml --dry-run --skip-llm`. Review purge counts per store.
3. **Full apply.** `python -m scripts.apply_patch --manifest data/patches/v<new>.yaml`. Snapshots `data/` into `data.snapshots/v<old>-pre-v<new>/`, runs per-store purge by entity reference, LLM-rewrites prompts referencing changed entities (diff batch shown for review), bumps `data/version_compatibility.json`.
4. **Update game.** Steam update.
5. **Rebuild mod.** `cd ../AgenticSTS-Mod/STS2AIAgent && dotnet build -c Release`. Fix reflection fields if names changed (see `GameActionService.cs`, `GameStateService.cs`). Deploy DLL to game's `mods/`.
6. **Set mod version.** `export STS2_MOD_VERSION=v<new>-xc`; update `data/version_compatibility.json` `current.mod_version`.
7. **Resync knowledge.** `python -m scripts.sync_upstream_data --game-version v<new>` once mod has shipped new `eng/*.json`.
8. **API schema check.** With mod running: `python -m scripts.check_mod_api_coverage`. Investigate any missing/unused fields.
9. **Regression.** `python -m pytest tests/regression/ -v`. All golden log fingerprints must match.
10. **Live smoke.** `python -m scripts.run_agent --steps 50 --runs 1` — verify agent completes a short run without errors.

### Invariants the pipeline preserves

- Every persistent record traceable to `(game_version, mod_version)`.
- Snapshots under `data.snapshots/` are never overwritten.
- Pre-destructive `--dry-run` always available.
- Entity-reference purge: records that do NOT reference any changed entity are untouched. `evolution/` artifacts are individually scanned, not blanket-archived.

Pipeline modules: `src/patch/{manifest,orchestrator,purge,rewrite,snapshot,version,slug,api_coverage,review}.py`.
