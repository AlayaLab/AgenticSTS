# Competitor mod patches applied (paper transparency)

Every edit made to a competitor's ORIGINAL source to build it against the current
Slay the Spire 2 build (Steam build `23478716`, 2026-05-30; our 298-run data was on
v0.103.1, 04-17). **Compatibility-only edits — no agent logic, prompts, strategy, or
memory changed.** Built with .NET 9 SDK against the live `data_sts2_windows_x86_64`
assemblies. Listed here so a reviewer can audit exactly what we changed.

## STS2MCP (Gennadiyev/STS2MCP)
- **Source edits: NONE.** `build.ps1 -GameDir "<install>"` compiled clean (0 warnings,
  0 errors) against the live assemblies. DLL → `out/STS2_MCP/STS2_MCP.dll`.
- MCP server env: `uv` venv already resolved (`mcp/` pinned deps); `--dry-run` lists 64
  tools. No changes.

## AI-Spire (biolbe1230/ai-spire)
- **Source edits: 1 compatibility rename, 4 sites**, all in
  `Scripts/AI/GameStateExtractor.cs`:
  `relic.Description` / `potion.Description` → `relic.DynamicDescription` /
  `potion.DynamicDescription` (lines 74, 96, 512, 528).
  - **Why:** on the 2026-05-30 build, `MegaCrit.Sts2.Core.Models.RelicModel` and
    `PotionModel` no longer expose a *public* `Description` getter (CS1061). Reflection
    of the live `sts2.dll` (via `tools/inspect/InspectAsm`) confirms both types still
    carry `Description : LocString` **and** `DynamicDescription : LocString`;
    `DynamicDescription` is the public accessor (it also resolves dynamic vars). This is
    a pure member-name compatibility swap — the relic/potion description text is still
    read; no behavior change.
- **Config:** created `config.json` from `config.example.json` (the repo ships only the
  example): `api_endpoint` → our logging proxy `http://localhost:8129/v1/chat/completions`,
  `model` `gemini-3.1-pro-preview`, `api_timeout_ms` **120000** (was 15000 — Gemini
  thinking exceeds 15 s; the raised timeout prevents the RuleEngine fallback from
  contaminating the LLM signal), `max_history_messages` **40** (unchanged — their
  accumulating-context design), `language` `en`. `api_key` is a placeholder
  (`PROXY-INJECTS-REAL-KEY`) — the proxy injects the real key, so no secret lives in the
  clone. These are configuration values the repo intends users to set, not code changes.
- Build: `dotnet build AISpire.csproj -c Release -p:Sts2Dir="<install>"` → 0 warnings,
  0 errors; auto-installs to `<game>/mods/AISpire/`.

## CharTyr (CharTyr/STS2-Agent)
- **DLL source edits: NONE.** `dotnet build STS2AIAgent/STS2AIAgent.csproj -c Release`
  compiled clean (default `Sts2DataDir` already points at the live assemblies). DLL →
  `STS2AIAgent/bin/Release/net9.0/STS2AIAgent.dll`.
- **`.pck` (Godot-packed manifest): PENDING** — `build-mod.ps1` needs the Godot 4.5
  editor to pack `mod_manifest.json` into `STS2AIAgent.pck`, and Godot is not installed.
  Resolution options under evaluation (download release `.pck` vs install Godot 4.5).
  No code change involved either way.

## HermesBridge (hiKareeem/ClaudePlaysTheSpire)
- **Not yet built.** Highest effort (BaseLib `[3.0.7,3.0.8)` + Godot.NET SDK + 56 Harmony
  bindings against game 0.104.0; OpenCode driver). Deferred — or cite its existing
  Gemini runs. Patches (if built) will be recorded here.

---

**Reviewer summary:** of the three competitors built, two needed **zero** source edits;
one (AI-Spire) needed a single mechanical member rename (×4) because the game privatised
`Description`. No agent/decision logic was altered in any competitor. All edits are the
"smallest change to load on the current build," per the project's stated methodology.
