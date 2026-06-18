# Competitor mod — build + minimal-compatibility-patch guide (C.3b)

**Compiled**: 2026-06-05 (controller, from direct reads of each clone's `*.csproj` / `*.props` / build scripts / `ModEntry`-equivalent / Harmony patches / README / CHANGELOG / manifest, cross-referenced against our own sibling fork `../AgenticSTS-Mod` which is built and verified against the current pin). **Cannot build or launch anything here** — every command below runs on the user's Windows machine + game install.

**Purpose**: get each cited competitor's **ORIGINAL** StS2 mod to compile and load on the current game version with the **smallest possible documented edits** and **NO substantive logic changes**. This is the build companion to `feasibility_aispire_hermesbridge.md` and `feasibility_sts2mcp_chartyr.md` (which cover the Gemini/driver wiring); this doc covers toolchain → build cmd → install → confirm-loaded → likely breakage points → MCP server setup.

---

## Global preconditions (apply to all four)

> ✅ **Game version — resolved (2026-06-06).** Install at `C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2`, last updated **2026-05-30** (Steam `buildid 23478716`; `pck`/`sts2.dll` rewritten that day; exe still the 04-17 file). Our **298 paper runs were v0.103.1** (04-17 build). The exact current marketing version is **not stored as readable text** (the pck's `v0.92.1/02-27-2026` menu label is a stale leftover; assemblies are placeholder-versioned `0.1.0.0`) — read it at runtime via `Invoke-RestMethod http://127.0.0.1:8128/health` → `game_version` (our mod) or a competitor health endpoint. Per project decision, the v0.103.1 → 5-30 delta is treated as **minor — not a fairness concern, and not discussed in the paper**; build each competitor mod against the **current (5-30) on-disk assemblies** so all cells share one build. Breakage analysis below assumes a **v0.103.x–v0.104.x** target.

**Common toolchain (every repo needs):**
- **.NET 9 SDK** — <https://dotnet.microsoft.com/download/dotnet/9.0>. `dotnet --version` should report `9.x`. (The user's `reference_windows_python.md` confirms real toolchains are installed; verify `dotnet` is on PATH.)
- **Slay the Spire 2 installed** — every csproj links against the on-disk game assemblies in `<game>/data_sts2_windows_x86_64/`: `sts2.dll`, `0Harmony.dll`, and (3 of 4 repos) `GodotSharp.dll`. **There is no NuGet package for these — the build relinks against whatever `sts2.dll` is physically present.** This is why a *rebuild* (not the prebuilt release) is the safe path: it binds to the live assemblies.

**Game-assembly reference pattern (identical across repos, learned from our verified fork `../AgenticSTS-Mod/STS2AIAgent/STS2AIAgent.csproj:17-30`):**
```xml
<Reference Include="sts2">       <HintPath>$(Sts2DataDir)/sts2.dll</HintPath>       <Private>false</Private> </Reference>
<Reference Include="0Harmony">   <HintPath>$(Sts2DataDir)/0Harmony.dll</HintPath>   <Private>false</Private> </Reference>
<Reference Include="GodotSharp"> <HintPath>$(Sts2DataDir)/GodotSharp.dll</HintPath> <Private>false</Private> </Reference>
```
Our fork builds cleanly against v0.103.1 with exactly this — so a competitor that fails to build is failing on a **renamed/moved game symbol**, not on the reference mechanism.

**Mod-loader entry pattern (the current-version contract, confirmed by all four + our fork):** every mod's entry class is `[ModInitializer("<MethodName>")]` from `MegaCrit.Sts2.Core.Modding`, and (except STS2MCP, which is purely HTTP) calls `Godot.Bridge.ScriptManagerBridge.LookupScriptsInAssembly(assembly)` + `new Harmony(id).PatchAll()`. This pattern is stable across v0.103–v0.104, so the **entry/init surface itself is low-risk**; breakage lives in the specific game types each mod's patches/state-readers touch.

**Complete-replacement (isolation) protocol — MANDATORY per competitor run.** Every cell runs with ONLY the competitor's own mod present, so its agent reads **only the competitor's mod state, never ours** — fairness (their system as-shipped) and no contamination from our mod's enrichments (which are our own contribution). All four — and our mod — Harmony-patch the same game and only one can patch at a time, so this is also a hard technical requirement. Before each run:
1. **Remove our mod** from `<game>/mods/` (delete/move its `.dll`/`.pck`/manifest) — not just "don't point at it"; remove it so it cannot load.
2. **Confirm it's gone**: `Invoke-RestMethod http://127.0.0.1:8128/health` must FAIL (connection refused). If it answers, our mod is still loaded.
3. **Install only the target competitor's mod**; confirm via that competitor's own check (§4 per repo): 15526 (STS2MCP) / 8080 (CharTyr) / overlay (AI-Spire) / `%APPDATA%\…\hermesbridge\state.json` (HermesBridge).
4. The **Gemini MCP host enforces this automatically** — it aborts (exit 3) if `:8128` answers, unless `--allow-our-mod`. AI-Spire & HermesBridge are driven outside the host, so apply steps 1–2 manually for those.

Ports differ (8128 ours / 8129 our LLM proxy / 15526 STS2MCP / 8080 CharTyr / 8765 CharTyr-MCP-HTTP) so there's no port clash — but double-patching the game is unsupported, so still run **one mod at a time, sequentially**.

**Triage recipe (use when any build/load fails — you cannot pre-verify symbols without the live assemblies):**
1. `dotnet build … -c Release` → read the **first** `CS0117`/`CS1061`/`CS0246`/`CS0234` compiler error. It names the exact missing **member / type / namespace** the live `sts2.dll` no longer exposes under that name.
2. Open the cited file:line, find the renamed/moved symbol, apply the **smallest** edit (rename to the new symbol, fix the changed method signature, or wrap in a reflection/`try-catch` fallback). Record it in the per-repo "Edits applied" list (see template at the end).
3. If the build **succeeds but the mod throws at load/runtime** (Harmony `HarmonyException`/`MissingMethodException` in `<game>` logs, or the health/IPC check fails), the broken target is a **Harmony `[HarmonyPatch(typeof(X), nameof(X.Y))]`** whose `X`/`Y` changed — the game log line names it. Same minimal-edit rule.
4. Re-build, re-deploy, re-run the confirm-loaded check. Each repo's confirm check is in its §4.

---

## 1. AI-Spire

`paper/competitors/AI-Spire/` — in-process C# Harmony mod with its own LLM client (no MCP server). Manifest `AISpire.json` (`version 1.0`, `has_dll:true`, `has_pck:false`). README "v0.98+"; repo era early-2026 → **oldest codebase of the four → highest breakage risk.**

### 1.1 Build toolchain
- **.NET 9 SDK** (common).
- **Godot .NET SDK 4.5.1** — the csproj's `Sdk="Godot.NET.Sdk/4.5.1"` (`AISpire.csproj:1`). Auto-restored via NuGet on first `dotnet build`; no separate Godot editor install needed for the DLL build.
- **No `uv`/Python** — AI-Spire has no MCP server; it calls the LLM directly via `Scripts/AI/LLMClient.cs`.
- The bundled `spire-codex/` game-data dir is **vendored and fully populated** (verified: `spire-codex/data/en/*.json` + `spire-codex/data/zhs/*.json` present; no live `.gitmodules`). No `git submodule update` needed.

### 1.2 Build command + where the game path is set
Game path is hardcoded in **`AISpire.csproj:10`** (`<Sts2Dir>`), default `D:\SteamLibrary\steamapps\common\Slay the Spire 2`. There is no env-var override and no build script — edit the csproj, then:
```powershell
# 1. Set your install path in AISpire.csproj line 10:
#    <Sts2Dir>C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2</Sts2Dir>
# 2. Create the config the post-build copy step requires (gitignored — see 1.5):
Copy-Item .\config.example.json .\config.json
# 3. Build (relinks against $(Sts2Dir)\data_sts2_windows_x86_64\sts2.dll + 0Harmony.dll):
dotnet build -c Release
```
The csproj's `Copy Mod` target (`AISpire.csproj:32-49`, `AfterTargets="PostBuildEvent"`) **auto-installs** on a successful build: it `MakeDir`s `$(Sts2Dir)\mods\AISpire\` and copies the DLL, `AISpire.json`, `config.json`, and the `spire-codex` `data\en\` + `data\zhs\` JSON. No manual install step.

### 1.3 Install steps (manifest convention)
Auto-installed by the build (1.2). Final layout under `<game>/mods/AISpire/` (README_EN.md:40-59):
```
AISpire/  ├─ AISpire.dll  ├─ AISpire.json (manifest, kept as-is — NOT renamed)  ├─ config.json  └─ data/{en,zhs}/*.json
```
Manifest convention: ships as `AISpire.json` and stays `AISpire.json` (its `id` is `"AISpire"`). Unlike STS2MCP, **no manifest rename**.

### 1.4 Confirm-loaded check
No HTTP endpoint. Two signals: (a) the **in-game overlay** — a semi-transparent panel top-center shows AI reasoning once in combat (`Scripts/AI/AIOverlay.cs`, init'd in `Entry.Init`); (b) the mod-loader log line `[AISpire] Mod initialized! AI player ready.` (`Scripts/Entry.cs:34`). If neither appears, the mod failed to load — check the game log for a Harmony binding exception and apply the triage recipe.

### 1.5 Likely minimal-patch points (core deliverable)
The entire game-API surface is in **`Scripts/Entry.cs`** (3 Harmony patches) + the state-reader `Scripts/AI/GameStateExtractor.cs`. AI-Spire binds **directly** to typed game symbols (no reflection fallbacks anywhere — unlike CharTyr/HermesBridge), so any renamed symbol is a hard compile or load failure. Ranked by risk:

| # | File:line | Symbol the mod assumes | Why fragile / likely break | Smallest fix |
|---|---|---|---|---|
| **1 (highest)** | `Scripts/Entry.cs:41,69,95` | `MegaCrit.Sts2.Core.Hooks.Hook.AfterPlayerTurnStart`, `.AfterCombatVictory`, `.AfterRoomEntered` (3 `[HarmonyPatch(typeof(Hook), nameof(Hook.X))]`) | These are the **only triggers** for the whole agent. If MegaCrit renamed a `Hook` member or changed its signature between v0.98-era and live, `nameof(Hook.X)` is a **compile error** (best case) or Harmony fails to bind at load (silent no-op agent). Highest-value target. | Rename to the current `Hook` member (compiler/Harmony names it). If a hook was removed, repoint the `[HarmonyPatch]` to the nearest surviving combat-turn-start / post-combat / room-entered hook — **mechanical repoint only, no logic change.** |
| 2 | `Scripts/Entry.cs:44,72,98` (Postfix params) | `CombatState`, `Player`, `IRunState`, `CombatRoom`, `AbstractRoom` param types on the Postfixes | Harmony matches Postfix params by name+type to the patched method. A changed param list on the hook → Harmony bind failure at load even if it compiles. | Match the Postfix signature to the live hook's params (drop/rename/reorder to match). |
| 3 | `Scripts/Entry.cs:49,76` | `LocalContext.GetMe(combatState)` / `GetMe(runState)` (`MegaCrit.Sts2.Core.Context`) | Local-player resolver; used in all 3 patches. A rename/overload change breaks every patch body. | Rename to the current accessor. |
| 4 | `Scripts/AI/GameStateExtractor.cs` (namespaces `…Entities.Creatures/Players/Cards/Powers`, `…MonsterMoves.Intents`, `…Combat`, `…Models`) | Reads hand/enemies/powers/relics/intents off live types | Combat/intent data model is the most-churned area across patches (see HermesBridge's v0.104.0 `Creature.CombatState` break, CharTyr's v0.7.1 boss-id move — §3/§4). Property renames here surface as `CS1061` at compile. | Per failing property: rename to the new member, or guard with a null-safe read. No re-derivation of values. |

**Certainty caveat:** I cannot confirm which `Hook`/`CombatState` members the live `sts2.dll` exposes without the assembly. **Build first; the first compiler error names the break.** Given AI-Spire is the oldest and has zero defensive reflection, budget for 1-4 above to all need touching if the live build is v0.104.x.

### 1.6 MCP server setup
N/A — AI-Spire has no MCP server. Gemini wiring is a `config.json` edit only (see `feasibility_aispire_hermesbridge.md` §3: `api_endpoint` → logging proxy, `api_timeout_ms` 15000→**120000**).

---

## 2. STS2MCP

`paper/competitors/STS2MCP/` — C# mod (localhost REST :15526) + optional Python MCP server (`mcp/`, stdio). Manifest `mod_manifest.json` (`id "STS2_MCP"`, `version 0.4.0`, `has_pck:false`, `affects_gameplay:false`). **README: "Tested against STS2 `v0.103.2`"** — closest-tracking of all four to our v0.103.1 pin → **lowest version risk.**

### 2.1 Build toolchain
- **.NET 9 SDK** (common). README "For Developers" requires only ".NET 9 SDK and the base game."
- **No Godot SDK** — csproj is `Sdk="Microsoft.NET.Sdk"` (`STS2_MCP.csproj:1`), DLL-only, `has_pck:false`. References `sts2.dll` + `GodotSharp.dll` + `0Harmony.dll` (`STS2_MCP.csproj:16-29`).
- **`uv` + Python 3.11+** — only for the **optional** MCP server (`mcp/`), not for the mod build. (Not needed for our Gemini-driver path per `feasibility_sts2mcp_chartyr.md` §2 — but documented in §2.6 since the MCP host could use it.)

### 2.2 Build command + where the game path is set
Game path: `build.ps1 -GameDir` param, falling back to `$env:STS2_GAME_DIR` (`build.ps1:20-43`); the csproj default is `STS2GameDir` (`STS2_MCP.csproj:8`). The script validates `sts2.dll` exists and that `dotnet` is on PATH before building.
```powershell
# Recommended (PowerShell, the supported path):
.\build.ps1 -GameDir "C:\Program Files (x86)\Steam\steamapps\common\Slay the Spire 2"
# or set once:  $env:STS2_GAME_DIR = "...\Slay the Spire 2"; .\build.ps1
```
Builds `STS2_MCP.dll` into `out/STS2_MCP/` (`build.ps1:66,73`). Does **not** auto-install (build.ps1 prints the copy instructions; install is manual — §2.3).

### 2.3 Install steps (manifest convention)
Manual copy (README "Build & Install", lines 140-145; macOS note line 178-179):
```
out/STS2_MCP/STS2_MCP.dll   ->  <game>/mods/STS2_MCP.dll
mod_manifest.json           ->  <game>/mods/STS2_MCP.json     # RENAMED
```
**Manifest convention: `mod_manifest.json` is renamed to `STS2_MCP.json`** on copy — "the game's mod loader expects the manifest filename to match the mod ID" (README:179). Files go **flat into `<game>/mods/`** (not a subfolder), per README:23 and :143-145.

### 2.4 Confirm-loaded check
HTTP health on **port 15526** (`McpMod.cs:23` `DefaultPort = 15526`; overridable via auto-created `STS2_MCP.conf` `{"port":N}`, `McpMod.cs:37-79`):
```powershell
Invoke-RestMethod http://localhost:15526/        # README uses: curl -s http://localhost:15526/
# expect: {"message":"Hello from STS2 MCP v0.4.0","status":"ok"}   (README example string lags at v0.3.4)
```
"Connection refused" → mods not enabled in-game (Settings → Mods; first-launch consent dialog).

### 2.5 Likely minimal-patch points (core deliverable)
STS2MCP is **mostly safe** (v0.103.2 ≈ live). The mod is REST-first; only `TryApplyHarmonyPatches()` does any patching, and it's already wrapped so failures are non-fatal. Game-API touch points are concentrated in the **state builder** (`McpMod.StateBuilder.cs`, ~101 KB — the largest read surface) and **action executor** (`McpMod.Actions.cs`, ~81 KB). Ranked:

| # | File:line | Symbol / surface | Why fragile | Smallest fix |
|---|---|---|---|---|
| **1 (highest)** | `McpMod.cs:285-287` | `MegaCrit.Sts2.Core.Runs.RunManager.Instance.IsInProgress` + `.NetService.Type.IsMultiplayer()` | Used on **every** request (the SP/MP 409 gate). Already in a `try { … } catch { return false; }` (`McpMod.cs:281-289`) so a break **degrades to "treat as singleplayer"** rather than crashing — but if `RunManager`/`NetService` was renamed it's a **compile error** that blocks the whole build. | Rename to current `RunManager`/`NetService` member. The existing `catch` already covers runtime drift. |
| 2 | `McpMod.cs:88-90` | `(SceneTree)Engine.GetMainLoop()` + `tree.Connect(SceneTree.SignalName.ProcessFrame, …)` (Godot, not sts2) | Main-thread marshalling. `GodotSharp.dll` API is far more stable than `sts2.dll`, but a Godot 4.5.x minor bump could rename `SignalName.ProcessFrame`. | Rename to current Godot signal constant. |
| 3 | `McpMod.StateBuilder.cs` (combat/run/map/shop readers) | Live combat/run/enemy/intent types (`BuildGameState`/`BuildMultiplayerGameState`) | Same combat-data-model churn that broke HermesBridge's `Creature.CombatState` at v0.104.0 (§5) — if live is v0.104.x, expect 1-N property renames here as `CS1061`. | Per failing property: rename / null-guard. No value re-derivation. |
| 4 | `McpMod.Actions.cs` (action verbs) | Card-play / target / potion APIs | Action dispatch touches mutable combat APIs; lower-traffic than the reader but same churn class. | Rename to current member per compiler error. |

**Certainty caveat:** because STS2MCP tracks v0.103.2, if the live build is still v0.103.x I expect **zero or near-zero** edits (it may build and load unchanged). If the live build jumped to v0.104.x, items 1/3 are the candidates. Build first.

### 2.6 MCP server setup (port 15526 REST / stdio MCP)
The mod **is** the REST server on 15526. The optional Python wrapper exposes it as stdio-MCP (README "MCP server setup", lines 71-105):
```powershell
# one-time dep install + run (uv reads mcp/pyproject.toml + mcp/uv.lock):
uv run --directory <repo>/STS2MCP/mcp python server.py --help
uv run --directory <repo>/STS2MCP/mcp python server.py        # stdio MCP; --host/--port to override
```
For our Gemini MCP host: either drive the REST API on **15526** directly (recommended — `feasibility_sts2mcp_chartyr.md` §3 documents the bespoke client contract: `GET /api/v1/singleplayer`, `POST /api/v1/singleplayer {action}`, entity-id targeting, no response envelope), or launch this stdio server as the MCP tool source. Health is `GET /` (NOT `/health`).

---

## 3. CharTyr

`paper/competitors/CharTyr/` — C# mod (localhost REST + SSE :8080) + Python MCP server (`mcp_server/`, stdio or HTTP :8765). Manifest `mod_id.json` + `mod_manifest.json` (`id "STS2AIAgent"`, `has_pck:true`, `has_dll:true`). **CHANGELOG: "Verified against StS2 `v0.103.2`" (v0.7.0); latest v0.7.1 2026-05-12.** AGPL-3.0-only.

> 🟢 **Reuse note (from `feasibility_sts2mcp_chartyr.md` §5): our running mod on `:8128` IS the CharTyr-lineage interface** — `../AgenticSTS-Mod` is a fork of this exact `STS2AIAgent` mod, byte-identical HTTP contract, **already built + verified on the live game**. For a CharTyr-lineage cell you can **install nothing** and point the driver at `http://127.0.0.1:8128`. The build steps below are for the **pristine-upstream v0.7.2** variant only (if explicitly wanted as a distinct datapoint). **Our fork's `STS2AIAgent.csproj` is the proof-of-build reference for the current version.**

### 3.1 Build toolchain
- **.NET 9 SDK** (common). `build-and-env.md` §1: ".NET SDK (建议与项目当前目标框架匹配)" = net9.0.
- **Godot .NET SDK 4.5.1 / Godot 4.5.x editor (with mono) — REQUIRED for the PCK.** Unlike the others, CharTyr ships a `.pck` and `build-mod.ps1` invokes a **headless Godot** to pack it (`build-mod.ps1:130`: `& $GodotExe --headless --path tools/pck_builder --script tools/pck_builder/build_pck.gd -- <manifest> <out.pck>`). The PCK is **minimal** — `build_pck.gd` packs only `mod_manifest.json` into `res://mod_manifest.json` (verified `tools/pck_builder/build_pck.gd:20`) — so **any Godot 4.5.x console/headless build works**; it needs no game assets. The script auto-discovers Godot via `-GodotExe`, `$env:GODOT_BIN`, `Get-Command Godot*`, or WinGet/Program Files paths (`build-mod.ps1:43-78`); if none found it throws "Godot executable not found."
- **`uv` + Python 3.11+** — for the MCP server (`mcp_server/`, §3.6). Not needed for the mod DLL/PCK build.

> **Godot-free alternative (from our fork):** `../AgenticSTS-Mod/VENDOR.md` records a cherry-picked commit *"feat(mod): Python PCK generator, remove Godot build dependency on macOS"* — our fork added a Python PCK packer to avoid the Godot dependency. If installing Godot is undesirable, the user can copy that Python packer from `../AgenticSTS-Mod/tools/` (or reuse our fork's already-built `.pck`, since the PCK only contains the manifest and is version-agnostic). For the pristine-CharTyr variant, the stock path is the Godot one above.

### 3.2 Build command + where the game path is set
Game path: `build-mod.ps1 -GameRoot` (default `C:/Program Files (x86)/Steam/steamapps/common/Slay the Spire 2`, `build-mod.ps1:4`); the data dir for assembly refs comes from `$env:STS2_DATA_DIR` or the csproj default (`STS2AIAgent.csproj:12-14`), optionally overridden by a `local.props` (`STS2AIAgent/local.props.example`).
```powershell
# Recommended (build-and-env.md §3):
powershell -ExecutionPolicy Bypass -File ".\scripts\build-mod.ps1" -Configuration Release
# optional: -GameRoot "...\Slay the Spire 2"  -GodotExe "C:\path\to\Godot_console.exe"
# optional: set $env:STS2_DATA_DIR or copy STS2AIAgent/local.props.example -> local.props and set <Sts2DataDir>
```
The script builds the DLL (`dotnet build STS2AIAgent/STS2AIAgent.csproj`), packs the PCK via Godot, and **auto-installs** all three artifacts into `<GameRoot>/mods/` (`build-mod.ps1:144-148`).

### 3.3 Install steps (manifest convention)
Auto-installed by `build-mod.ps1` into `<game>/mods/` (flat), three files (README "Install The Mod", lines 20-40):
```
STS2AIAgent.dll  +  STS2AIAgent.pck  +  mod_id.json
```
**Manifest convention: ships `mod_id.json` (the loader manifest) alongside the `.pck`-embedded `mod_manifest.json`.** The build explicitly **deletes** any legacy `STS2AIAgent.json` from the mods dir (`build-mod.ps1:150-153`) — do not hand-create one. (Note: `mod_id.json` version `0.5.4` vs `mod_manifest.json` version `0.7.2` in the clone — cosmetic drift; the loader keys on `id`.)

### 3.4 Confirm-loaded check
HTTP health on **port 8080** (`Router.cs:15` `ModVersion = "0.7.2"`; `HttpServer.cs` default 8080, overridable via `STS2_API_PORT`):
```powershell
Invoke-RestMethod http://127.0.0.1:8080/health      # README: http://127.0.0.1:8080/health
# expect: {"ok":true,"data":{"service":"sts2-ai-agent","mod_version":"0.7.2",
#          "protocol_version":"2026-03-11-v1","game_version":"<LIVE>","status":"ready"}}
```
The `game_version` field is read **live** at runtime (`Router.cs:45`: `ReleaseInfoManager.Instance.ReleaseInfo?.Version ?? "unknown"`) — this is the authoritative live-version probe for any of these mods. (For the reuse path, hit `:8128` instead.)

### 3.5 Likely minimal-patch points (core deliverable)
CharTyr is **defensively coded** — `GameStateService.cs` (~203 KB) already uses **17 reflection calls** (`GetMethod`/`GetProperty`/`GetField`) to tolerate version drift, so much of the state surface degrades gracefully rather than failing to compile. Its own v0.7.1 CHANGELOG is a worked example of the exact minimal-patch pattern we want. Ranked:

| # | File:line | Symbol / surface | Why fragile | Smallest fix |
|---|---|---|---|---|
| **1 (highest)** | `Game/GameStateService.cs` — boss resolution | `RunState.Act.BossEncounter.Id.Entry` | **Already broke once**: CharTyr v0.7.1 (2026-05-12, CHANGELOG:7-8) "Switched boss resolution to `RunState.Act.BossEncounter.Id.Entry` with a **compatibility fallback for older runtime layouts**." This nested path is the single most-churned accessor in the repo's own history. If live moved it again, `/state` `run.boss_id` returns null or throws. | Add/extend the same try-multiple-paths fallback CharTyr already uses (read new path, fall back to old). **Mechanical accessor swap — exactly the edit CharTyr itself shipped.** |
| 2 | `Server/Router.cs:45` | `MegaCrit.Sts2.Core.Debug.ReleaseInfoManager.Instance.ReleaseInfo.Version` | Drives the health endpoint's `game_version`. Already null-safe (`?? "unknown"`) so a *property* break degrades to "unknown"; but a *type/namespace* rename (`ReleaseInfoManager`) is a compile error. | Rename to current type; the `?.`/`??` already guards runtime. |
| 3 | `Game/GameActionService.cs` (~171 KB, action verbs incl. `ResolveCardTarget`) | Card-play / target / reward / shop / rest APIs | Largest mutating surface; touches combat + room APIs. Reflection covers some; direct typed calls (e.g. `MegaCrit.Sts2.Core.GameActions`) would surface as `CS1061`/`CS0117`. | Per compiler error: rename, or convert a direct call to the reflection pattern already used elsewhere in the file. |
| 4 | combat/enemy/intent readers in `GameStateService.cs` | live `CombatState`/`Creature`/intent types | Same v0.104.0 combat-model churn class as HermesBridge §5. | Rename / null-guard per error. |

**Certainty caveat:** CharTyr's reflection-heavy design + v0.103.2 verification means it's **likely to build with few edits**; item 1 (boss-id path) is the highest-probability single break because it already moved once. **For the comparison, prefer the reuse path (`:8128`, build nothing) unless pristine-upstream v0.7.2 is explicitly required.**

### 3.6 MCP server setup (port 8080 REST / 8765 HTTP MCP / stdio)
The mod is the REST+SSE server on **8080**. The Python `mcp_server/` wraps it (FastMCP; `mcp_server/pyproject.toml` → entry points `sts2-mcp-server` stdio + `sts2-network-mcp-server` HTTP):
```powershell
# stdio (recommended; build-and-env.md §4):
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-stdio.ps1"     # runs: uv sync; uv run sts2-mcp-server
# network (HTTP MCP on 8765, talks to mod API on 8080):
powershell -ExecutionPolicy Bypass -File ".\scripts\start-mcp-network.ps1"   # uv run sts2-network-mcp-server --host 127.0.0.1 --port 8765 --path /mcp --api-base-url http://127.0.0.1:8080
```
Ports: **8080** = mod REST (`STS2_API_BASE_URL` default `http://127.0.0.1:8080`), **8765** = network MCP HTTP (`/mcp`, `/healthz`), **stdio** = default MCP transport. Our Gemini MCP host launches `uv run sts2-mcp-server` (stdio) or drives the 8080 REST directly. Quick import self-check: `uv run python -c "from sts2_mcp.server import create_server; create_server(); print('MCP_IMPORT_OK')"` (build-and-env.md §5).

---

## 4. HermesBridge

`paper/competitors/HermesBridge/` — C# mod + **file-IPC** (no HTTP, no port). Manifest `HermesBridge.json` (`id "HermesBridge"`, `version v0.2.0`, `has_pck:false`, `affects_gameplay:false`, **`dependencies:["BaseLib"]`**). **CHANGELOG + AGENTS.md + run records: targets StS2 `v0.104.0`** (v0.1.3 was the explicit "v0.104.0 compat patch") → **newer than our v0.103.1 pin**; the version-fork risk cuts both ways (see `feasibility_aispire_hermesbridge.md` §HermesBridge-1).

### 4.1 Build toolchain
- **.NET 9 SDK** (common).
- **Godot .NET SDK 4.5.1** — csproj `Sdk="Godot.NET.Sdk/4.5.1"` (`HermesBridge.csproj:1`). Auto-restored. **Godot editor NOT required** for the shipped build: README "Build from source" (lines 114-129) says Godot 4.5 is "only required if you want to pack `.pck` assets; **not needed for the DLL-only build this mod currently ships**" (`has_pck:false`). The PckPacker package reference is commented out (`HermesBridge.csproj:38-39`).
- **NuGet packages (auto-restored, network needed on first build) — this is HermesBridge's distinctive risk:**
  - **`Alchyr.Sts2.BaseLib` `[3.0.7,3.0.8)`** (`HermesBridge.csproj:35`) — the **BaseLib third-party mod loader**, a hard runtime dependency (manifest `dependencies:["BaseLib"]`). The user must **also install BaseLib into `<game>/mods/`** (README "Install (users)" step 1 → <https://github.com/Alchyr/BaseLib-StS2>) or the mod won't load.
  - `Krafs.Publicizer` `2.3.0` (accesses private game members; `Publicize` itemgroup is `Condition="false"` so currently inert).
  - `Alchyr.Sts2.ModAnalyzers` `*`.
- **No `uv`/Python for the mod.** The repo's drivers are PowerShell (`autopilot-lib.ps1`) + an agent `SKILL.md`; there are `tests-python/` but they're not part of the mod build.

### 4.2 Build command + where the game path is set
Game path: **auto-discovered** by `Sts2PathDiscovery.props` (imported at `HermesBridge.csproj:2`) — reads the Steam registry (`HKLM\…\Uninstall\Steam App 2868840`, `HKCU\…\Valve\Steam@SteamPath`) and common install dirs, setting `$(Sts2Path)`, `$(Sts2DataDir)`, `$(ModsPath)` (`Sts2PathDiscovery.props:14-28`). Override via `local.props` or `/p:Sts2Path=...`. The build **errors early** if the data dir isn't found (`HermesBridge.csproj:68-72` `CheckDependencyPaths`).
```powershell
# README "Build from source" (stop the game first — build copies into mods/):
Get-Process -Name 'SlayTheSpire2' -EA SilentlyContinue | Stop-Process -Force
dotnet build .\HermesBridge.csproj -c Release
# if auto-discovery misses your install:  dotnet build .\HermesBridge.csproj -c Release /p:Sts2Path="C:\path\to\Slay the Spire 2"
```
The `CopyToModsFolderOnBuild` target (`HermesBridge.csproj:74-78`, `AfterTargets="PostBuildEvent"`) **auto-installs** `HermesBridge.dll` + `HermesBridge.json` into `$(ModsPath)HermesBridge/`.

### 4.3 Install steps (manifest convention)
Auto-installed by the build into `<game>/mods/HermesBridge/` (README "Install (users)", lines 46-57):
```
HermesBridge/  ├─ HermesBridge.dll  └─ HermesBridge.json   (+ BaseLib installed separately into mods/)
```
**Manifest convention: ships `HermesBridge.json` as-is** (kept, not renamed; the csproj copies `$(AssemblyName).json`). **Prerequisite: BaseLib must be installed in `mods/` first** (manifest `dependencies:["BaseLib"]`).

### 4.4 Confirm-loaded check
No HTTP — **file-IPC**. Signals (README lines 62-66):
1. `%APPDATA%\SlayTheSpire2\logs\godot.log` contains `HermesBridge loaded` + `--- RUNNING MODDED! ---` (the BaseLib "modded" banner).
2. `%APPDATA%\SlayTheSpire2\hermesbridge\state.json` **appears** once you reach the main menu (written by `MainMenuReadyPatch` → `BridgeSnapshotWriter`). If `state.json` never appears, the mod loaded but a startup patch threw — check `%APPDATA%\SlayTheSpire2\hermesbridge\trace.log`.

### 4.5 Likely minimal-patch points (core deliverable)
HermesBridge has the **largest Harmony footprint of the four — 38 patch files in `HermesBridgeCode/Patches/` carrying 56 distinct `[HarmonyPatch(typeof(N…), nameof(…))]` bindings** (most files patch one method; `SmithFlowDiagnosticPatch.cs` alone patches 13), each against a specific game screen/room/node class. **This is the biggest breakage surface in the whole comparison**: every renamed screen/room type is a separate compile-or-load break. It's *partially* mitigated — the mod targets v0.104.0 (so if the live build IS v0.104.x it likely loads as-is) and already uses defensive reflection in spots (e.g. `GameOverScreenReadyPatch.cs:65` reflectively finds `ReturnToMainMenu` with a `NGame.Instance` fallback; `BridgeStateExtractor.SafeGetCombatState` swallows `MissingMethodException`). Ranked:

| # | File:line | Symbol / surface | Why fragile | Smallest fix |
|---|---|---|---|---|
| **1 (highest)** | `HermesBridgeCode/Patches/*.cs` (38 files, 56 patch bindings) — `NMainMenu._Ready`, `NMapScreen.SetMap`, `NRestSiteRoom.UpdateRestSiteOptions`, `NGameOverScreen._Ready`, `NMerchant…`, `NRewards…`, `NCardReward…`, `NEventRoom…`, `NTreasureRoom…`, etc. | Each Harmony patch binds to a named **`N…` screen/room/node type + method** (e.g. `[HarmonyPatch(typeof(NMapScreen), nameof(NMapScreen.SetMap))]`, `MapScreenSetMapPatch.cs:13`) | If MegaCrit renamed any patched type/method between v0.104.0 and a *different* live build (older v0.103.x **or** newer), `nameof(…)` is a compile error, or Harmony throws at `PatchAll()`. 56 independent bindings = highest aggregate risk. **If live ≠ v0.104.x this is where most edits land.** | Per failing patch: rename `typeof(X)`/`nameof(X.Y)` to the current type/method. If a screen was removed/renamed wholesale, repoint to the surviving equivalent — **mechanical retarget, no dispatcher logic change.** |
| 2 | `HermesBridgeCode/BridgeStateExtractor.cs:49-57` | `SafeGetCombatState(room, player)` → `room?.CombatState` / `player?.Creature?.CombatState` | **Already broke once**: v0.1.3 CHANGELOG (line 45) "Game v0.104.0 broke `Creature.CombatState` access (returned null/threw)" → they added this `MissingMethodException`-swallowing fallback. If the live build differs again, the *fallback target* itself could move. | Extend the existing fallback chain with the new accessor path; the `try/catch(MissingMethodException)` scaffold is already there. |
| 3 | `HermesBridgeCode/BridgeSingleton.cs` + `BridgeCommandDispatcher.cs` (~154 KB) | `RunManager`/`NMapScreen.Instance`/`NGame.Instance` + the full `case "PlayCard"/"EndTurn"/…` command surface against live combat/run APIs | The command dispatcher mutates game state (play/end-turn/select); same combat-model churn class. `BridgeSingleton.PushCurrentMap/Run/RestSite` read live singletons. | Per compiler error: rename to current member, or wrap in the reflection/`try-catch` pattern already used elsewhere in the file. |
| 4 | `HermesBridge.csproj:35` | `Alchyr.Sts2.BaseLib` `[3.0.7,3.0.8)` version pin | If BaseLib 3.0.7 was compiled against an incompatible game build, or a newer BaseLib is needed for the live game, restore/load fails. **This is a dependency-version risk the other three don't have** (they use the native `ModInitializer` loader directly). | Bump the version range to a BaseLib release matching the live game (smallest edit: widen `[3.0.7,3.0.8)` to the compatible version), and install that BaseLib build into `mods/`. |

**Certainty caveat:** HermesBridge is the **highest-risk build** of the four — most Harmony targets *and* a third-party loader dependency. If the live game is exactly v0.104.x it may load with zero edits (it was built for v0.104.0); if it's v0.103.x or a newer build, expect item 1 (some subset of the 37 patches) plus possibly item 4. **Build first; the compiler + `trace.log` enumerate the exact targets.** Per `feasibility_aispire_hermesbridge.md` §HermesBridge-7, if reconciling the version fork would break our own mod, **defer HermesBridge and cite their existing Gemini runs** instead.

### 4.6 MCP server setup
N/A — no MCP server, no HTTP. The "agent" is an external coding-agent loop (OpenCode + `SKILL.md`) reading/writing JSON under `%APPDATA%\SlayTheSpire2\hermesbridge\` (`state.json` ← mod, `commands.json` → mod, `result.json` ← mod). Gemini wiring = point OpenCode's model backend at our logging proxy (see `feasibility_aispire_hermesbridge.md` §HermesBridge-3/4).

---

## Summary table

| Repo | Toolchain | Build command | Install files → `<game>/mods/` | Most-likely breakage point (vs live build) |
|---|---|---|---|---|
| **AI-Spire** | .NET 9 SDK + Godot.NET SDK 4.5.1 (NuGet). No `uv`. | edit `<Sts2Dir>` in `AISpire.csproj:10`; `Copy-Item config.example.json config.json`; `dotnet build -c Release` (auto-installs) | `AISpire/`: `AISpire.dll` + `AISpire.json` (kept) + `config.json` + `data/{en,zhs}/*.json` | **`Hook.AfterPlayerTurnStart` / `.AfterCombatVictory` / `.AfterRoomEntered`** (`Scripts/Entry.cs:41,69,95`) — the 3 Harmony triggers; oldest codebase, zero reflection fallbacks → hard compile/load break if any `Hook` member moved |
| **STS2MCP** | .NET 9 SDK. `uv`+Py3.11 only for optional MCP. No Godot. | `.\build.ps1 -GameDir "<install>"` (or `$env:STS2_GAME_DIR`) → `out/STS2_MCP/`; **manual** copy | flat: `STS2_MCP.dll` + `mod_manifest.json`→**`STS2_MCP.json`** (renamed) | **`RunManager.Instance.IsInProgress` / `.NetService.Type.IsMultiplayer()`** (`McpMod.cs:285-287`) — hit on every request; already `try/catch`-guarded at runtime, but a type rename blocks the build. Lowest overall risk (tracks v0.103.2) |
| **CharTyr** | .NET 9 SDK + **Godot 4.5.x (headless, for PCK)** + `uv`+Py3.11 (MCP). | `.\scripts\build-mod.ps1 -Configuration Release` (auto-installs DLL+PCK+manifest) | flat: `STS2AIAgent.dll` + `STS2AIAgent.pck` + `mod_id.json` | **`RunState.Act.BossEncounter.Id.Entry`** boss resolution (`Game/GameStateService.cs`) — **already moved once in v0.7.1**; extend its existing compat fallback. *(Or skip install: reuse our `:8128` fork.)* |
| **HermesBridge** | .NET 9 SDK + Godot.NET SDK 4.5.1 (NuGet) + **`Alchyr.Sts2.BaseLib [3.0.7,3.0.8)`** loader (NuGet + install BaseLib in `mods/`). No `uv` for mod. | stop game; `dotnet build .\HermesBridge.csproj -c Release` (auto-discovers install, auto-installs) | `HermesBridge/`: `HermesBridge.dll` + `HermesBridge.json` (kept) **+ BaseLib separately** | **56 `[HarmonyPatch(typeof(N…screen/room), nameof(…))]` bindings across 38 files** in `HermesBridgeCode/Patches/` — largest patch surface; built for v0.104.0 so a *different* live build breaks some subset. Secondary: BaseLib version pin (`HermesBridge.csproj:35`) |

### Confirm-loaded checks (one line each)
- **AI-Spire**: in-game overlay shows AI reasoning + log `[AISpire] Mod initialized!` (no endpoint).
- **STS2MCP**: `Invoke-RestMethod http://localhost:15526/` → `{"message":"Hello from STS2 MCP v0.4.0","status":"ok"}`.
- **CharTyr**: `Invoke-RestMethod http://127.0.0.1:8080/health` → `{"ok":true,"data":{…,"game_version":"<live>","status":"ready"}}` (reuse path: `:8128`).
- **HermesBridge**: `godot.log` shows `HermesBridge loaded` + `--- RUNNING MODDED! ---`; `%APPDATA%\SlayTheSpire2\hermesbridge\state.json` appears at the main menu.

### Per-repo "Edits applied" log (fill during build — paper-transparency requirement)
For each compatibility edit, record: `repo | file:line | old symbol/signature → new symbol/signature | category (rename / signature-fix / version-guard / dependency-bump) | one-line reason`. All edits must be **mechanical** (no agent/decision/prompt/memory/strategy changes). This list is the appendix artifact promised in `PLAN.md` §"Fairness caveats" and decision #2.

---

## Cross-repo notes & provenance

- **Version provenance** (build target each repo last verified against — informs *expected* edit count, NOT a fairness claim per `PLAN.md` decision #2): AI-Spire ~v0.98-era (oldest), STS2MCP v0.103.2, CharTyr v0.103.2 (v0.7.0), HermesBridge v0.104.0. Our pin: v0.103.1.
- **Why rebuild over prebuilt release**: none of the four pins a hard game version in its manifest/csproj — all relink against the on-disk `sts2.dll` at build time. A fresh `dotnet build` against the live assemblies is the only way to guarantee binding; prebuilt release DLLs were compiled against the authors' build and may silently fail to bind.
- **Lowest-effort path overall**: CharTyr-via-reuse (build nothing, drive our `:8128` fork). STS2MCP & AI-Spire are independent builds; HermesBridge is the riskiest (most Harmony targets + BaseLib).
- **Our fork as reference**: `../AgenticSTS-Mod` (a CharTyr fork, built + verified on the live game) is the canonical example of the current-version build pattern — its `STS2AIAgent.csproj`, `VENDOR.md` (Python PCK generator, upstream-sync workflow), and the fact that it compiles are the strongest evidence for what the live `sts2.dll` exposes. **Do not modify it.**
- **Real-world minimal-patch precedents** (both are exactly the kind of edit this guide authorizes): CharTyr v0.7.1 (boss-id accessor move + compat fallback) and HermesBridge v0.1.3 (`SafeGetCombatState` swallowing `MissingMethodException` after v0.104.0 broke `Creature.CombatState`). The combat/run data model is the most-churned area across all four — expect breakage there first if the live build is v0.104.x.
