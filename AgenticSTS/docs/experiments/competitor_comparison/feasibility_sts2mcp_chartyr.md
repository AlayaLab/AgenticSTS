# Feasibility — STS2MCP & CharTyr

**Compiled**: 2026-06-05 (controller, from direct reads of repo `.cs`/`README`/`docs/api.md`/`csproj`/manifest + `git tag` in each clone, plus our own client `src/mcp_client/` and `config.py`; cross-checked against `paper/narrative/competitor_analysis.md`).
**Experiment**: drive each with a minimal Gemini 3.1 Pro function-calling agent (accumulating context, no memory/skills) at A0, N=5, capturing all raw prompts/responses for the released dataset; compare against our frozen-A0 cells.
**Cannot launch the game from here** — verdicts are static; each repo has a user smoke-test checklist (§8).
**Both are interface-only ("bring your own agent")** — neither ships an LLM agent. A separate task builds the Gemini driver; this doc specifies the wire contract it must speak.

> ⚠️ **Global blocker #0 — installed game version.** Our last verified pin is **v0.103.1** (2026-04-17, `data/version_compatibility.json`); today is 2026-06-05, so Steam may have auto-updated the game. STS2 mods are Harmony-patched against the game's `sts2.dll` / `GodotSharp.dll` assemblies — **version coupling is the #1 load risk and every verdict below is conditional on the live build.** First user action: confirm the main-menu build string and that **our own mod still loads** on it. Neither competitor mod declares a hard version pin in its manifest/csproj — both relink against whatever `sts2.dll` is on disk at build time (STS2MCP `STS2_MCP.csproj:17-19`; CharTyr `STS2AIAgent.csproj:18-20`), so the only authoritative version signal is the live `/health` response (both surface `game_version`).

> 🟢 **HEADLINE — CharTyr-reuse verdict: COMPATIBLE (skip installing CharTyr entirely).** Our running mod on `localhost:8128` **is** a CharTyr-lineage interface — it is a fork of CharTyr's `STS2AIAgent` mod and speaks the byte-identical HTTP contract. Point the naive Gemini agent at `http://127.0.0.1:8128` and it is talking to "the CharTyr interface" with zero extra install. Evidence in §CharTyr-5 below.

---

## STS2MCP (`Gennadiyev/STS2MCP`)

Clone: last commit `2fb5390` (2026-05-13), latest tag `0.4.0`. Mod `Version = "0.4.0"`, `DefaultPort = 15526` (`McpMod.cs:22-23`). README prose: "Tested against STS2 `v0.103.2`".

**1. Game-version compatibility.** README claims **v0.103.2** — one patch *newer* than our v0.103.1 pin, and the most current of any competitor. No hard pin in manifest/csproj; the prebuilt release DLL is a "platform-agnostic .NET assembly" (same DLL on Win/Linux/macOS per README) compiled against an early-May game build. Against the live build it *probably* binds (v0.103.2 ≈ our v0.103.1, both May-2026 era), but the only proof is the `/` health string (`{"message":"Hello from STS2 MCP v0.3.4","status":"ok"}` shape — note README example lags the code's `0.4.0`). Risk: **LOW-MEDIUM** — closest-tracking competitor, but still Harmony-patched, so re-verify on the live build. Rebuild path exists if it fails to bind (see §2).

**2. Install artifact.** Prebuilt: grab `STS2_MCP.dll` + `STS2_MCP.json` from Releases → copy to `{game}/mods/`; enable mods in-game (consent dialog on first launch); HTTP server auto-starts on `localhost:15526` (port overridable via `STS2_MCP.conf` `{"port":N}`, auto-created on first run, `McpMod.cs:37-79`). Build-from-source: **.NET 9 SDK**, `build.ps1 -GameDir "<install>"` (or `$env:STS2_GAME_DIR`), copies `out/STS2_MCP/STS2_MCP.dll` + renamed manifest to `mods/`. **Conflicts with our mod** — both are in-process mods that start `HttpListener`s and Harmony-patch; ports differ (15526 vs 8128) so no port clash, but running both simultaneously double-patches the game. Treat as **mutually exclusive → sequential**: unload our mod (or its `.dll` from `mods/`) before installing STS2MCP. The optional Python MCP server (`mcp/`, `uv`-managed) is **not needed** for a custom Gemini driver — it only exists to wrap the REST API as stdio-MCP for Claude Desktop/Code.

**3. API/MCP surface for a Gemini driver.** Plain localhost **REST** (also CORS-open: `Access-Control-Allow-Origin: *`, `McpMod.cs:181`). **No auth.** Port **15526**. This is a *different contract* from CharTyr/ours — a Gemini driver needs a **bespoke client**.

- **State read**: `GET /api/v1/singleplayer` → full singleplayer game state (markdown via `?format=markdown`). `GET /api/v1/multiplayer` for co-op (hard-gated: SP endpoint returns 409 during MP runs and vice-versa, `McpMod.cs:198-232`). Profile/durable context: `GET /api/v1/profile`, `GET /api/v1/compendium`, `GET /api/v1/wiki?query=`, `GET /api/v1/profiles`. Health: `GET /` (NOT `/health`).
- **Actions**: `POST /api/v1/singleplayer` with `{"action": "<verb>", ...}`. Verb set (`McpMod.Actions.cs:61-91`): `play_card`, `use_potion`, `discard_potion`, `end_turn`, `choose_map_node`, `choose_event_option`, `advance_dialogue`, `choose_rest_option`, `shop_purchase`, `claim_reward`, `select_card_reward`, `skip_card_reward`, `proceed`, `select_card`, `confirm_selection`, `cancel_selection`, `select_bundle`/`confirm_bundle_selection`/`cancel_bundle_selection`, `combat_select_card`/`combat_confirm_selection`, `select_relic`/`skip_relic_selection`, `claim_treasure_relic`, `crystal_sphere_*`. **Menu/lifecycle** uses a *single* `menu_select` verb with an `option` string (`continue`/`main_menu`/`yes`/`no`/`advance`/`standard`/character-select/etc., `McpMod.Actions.cs:1079+`) routed by scene-tree introspection — NOT discrete per-action verbs.
- **Two contract quirks the driver must handle**: (a) targeting is **by `entity_id` string** (e.g. `"jaw_worm_0"` or a numeric combat-id), NOT by enemy index — `play_card` takes `{"card_index", "target": "<entity_id>"}` (`McpMod.Actions.cs:128-137`, `ResolveTarget` 1053-1077). (b) Action params use mixed key names: `index` for most selections, `card_index` for card plays, `slot` for potions. Responses are bare `{"status":"ok","message":...}` or `{"error":...}` — **no `{ok,request_id,data}` envelope, no post-action `state` snapshot** (driver must re-`GET` state after every action).
- Transport: plain REST (no SSE/event stream). The optional `mcp/server.py` is `FastMCP` over **stdio** targeting `http://localhost:15526/api/v1/singleplayer` — irrelevant to a direct REST driver.

**4. Logging integration.** Our OpenAI-compatible logging proxy fronts Gemini, so **all LLM I/O is auto-captured** regardless of which game interface is used — confirmed, this is interface-agnostic (the proxy sits between the agent and the model, not between the agent and the game). Structured game-state worth capturing alongside the dataset: the `GET /api/v1/singleplayer` JSON snapshot per decision (it carries `run_id` seed, floor, deck, relics, enemy intents). **Gap**: STS2MCP's mod emits no run-keyed JSONL of its own (`verbose`-style logs only go to the Godot console), so per-decision state logging is the driver's responsibility — have the Gemini driver persist each `GET` snapshot next to the prompt/response.

**5. CharTyr-reuse verdict.** N/A for STS2MCP — different lineage, different contract (15526, `/api/v1/singleplayer`, `menu_select`, entity-id targeting, no envelope). Cannot be served by our 8128 mod. If we want the STS2MCP cell, we must install STS2MCP's mod and write a STS2MCP-specific client.

**6. Character + ascension.** Interface exposes menu control via `menu_select` (character-select options + `embark`/seed, multiplayer host/join, FTUE dismissal) — so character choice is *scriptable* but through the opaque `option`-string path, and **there is no explicit `increase_ascension`/`decrease_ascension` verb** in the action switch (unlike CharTyr). Safest for a minimal Gemini driver: **user sets character + A0 in the game menu pre-launch**, then the agent drives the active run. Confirm A0 is the default ascension on a fresh profile (it is, unless a prior run bumped it).

**7. Effort + verdict.** **NEEDS-WORK.** The interface is healthy, current (v0.103.2), and richly documented, but a Gemini driver needs a **bespoke REST client** (distinct endpoints, `menu_select` menu model, entity-id targeting, no response envelope, re-GET-after-action). That client does not exist in our codebase — our `src/mcp_client/` speaks the CharTyr/8128 contract only. Rough effort: **~0.5–1 day** to write + smoke-test a STS2MCP client adapter, plus the sequential mod-swap (unload ours, install theirs) for each session. Worth it only if we specifically want a *second, independent* interface lineage in the comparison (STS2MCP is the "REST-only, BYO-agent, benchmark-aspirant" cell). If the goal is just "a CharTyr-lineage cell," **skip STS2MCP and use our 8128 mod** (see CharTyr §5).

**8. User smoke-test checklist (STS2MCP).**
1. Confirm live game version: launch STS2, read the main-menu build string; note whether it matches/exceeds v0.103.2.
2. Ensure our own mod's `.dll` is **removed** from `{game}/mods/` (avoid double-patch), then copy STS2MCP's `STS2_MCP.dll` + `STS2_MCP.json` into `{game}/mods/`.
3. Launch the game; Settings → Mods → confirm STS2MCP is listed and enabled (accept the first-launch consent dialog).
4. Health: in PowerShell, `Invoke-RestMethod http://localhost:15526/` → expect `{"message":"Hello from STS2 MCP v0.4.0","status":"ok"}`. If "connection refused", mods aren't enabled.
5. Set character + Ascension 0 in the game menu; start a run; advance into the first combat.
6. State read: `Invoke-RestMethod http://localhost:15526/api/v1/singleplayer` → confirm a combat payload with `hand`, `enemies` (note each enemy's `entity_id`), `energy`.
7. One action round-trip: `Invoke-RestMethod -Method Post -Uri http://localhost:15526/api/v1/singleplayer -Body '{"action":"end_turn"}' -ContentType 'application/json'` → expect `{"status":"ok",...}`; re-GET state and confirm the turn advanced.
8. (Targeting check) `POST {"action":"play_card","card_index":0,"target":"<entity_id from step 6>"}` → confirm a card resolves against the named enemy.

---

## CharTyr (`CharTyr/STS2-Agent`)

Clone: last commit `2617fb1` (2026-05-17, "Release v0.7.2"), latest tag `v0.7.2`. Mod `ModVersion = "0.7.2"`, `ProtocolVersion = "2026-03-11-v1"`, `DefaultPort = 8080` (`Router.cs:14-16`, `HttpServer.cs:9-10`). **This is the upstream of our `../AgenticSTS-Mod` fork.** AGPL-3.0-only.

**1. Game-version compatibility.** No hard pin; csproj relinks against the on-disk `sts2.dll` (`STS2AIAgent.csproj:18-20`). `docs/api.md` health *example* shows a stale `game_version: v0.98.2`, but the code reads the **live** version at runtime (`Router.cs:45`: `ReleaseInfoManager.Instance.ReleaseInfo?.Version`), so `/health` always reports truth. Tag history runs to v0.7.2 (2026-05-17). Risk: **LOW for the reuse path** — we don't need CharTyr's prebuilt DLL at all; our fork is already built against the version we last verified. If the live game drifted off v0.103.1, the relevant question is whether **our fork** still binds, not CharTyr's release (see §5 + blocker #0).

**2. Install artifact.** Prebuilt: `STS2AIAgent.dll` + `STS2AIAgent.pck` + `mod_id.json` → `{game}/mods/`; HTTP auto-starts on `127.0.0.1:8080` (overridable via `STS2_API_PORT` env, `HttpServer.cs:166-177`). Build-from-source: **.NET 9 SDK**, `scripts/build-mod.ps1 -Configuration Release` (set `STS2_DATA_DIR` or edit `local.props`). Optional Python `mcp_server/` (`uv`) wraps it as stdio/HTTP MCP — **not needed** for our reuse path or a direct REST driver. **Conflict**: identical-lineage to our mod → never run CharTyr's mod *and* ours together (same code, same listener). For the reuse path there is **nothing to install** — our mod is already deployed on 8128.

**3. API/MCP surface for a Gemini driver.** Plain localhost **REST + SSE**. Port **8080** (CharTyr default) / **8128** (our fork). **No auth** on the local mod (the *optional* `network_server.py` Tailscale wrapper adds a bearer token + `streamable-http` MCP on 8765 — irrelevant locally). Unified `{ok, request_id, data}` / `{ok, error:{code,message,details,retryable}}` envelope on every response (`Router.cs:36-182`).

- **Endpoints** (`Router.cs`): `GET /health`; `GET /state` (full snapshot, `state_version=6`); `GET /actions/available` (legal-action hints w/ `requires_target`/`requires_index`); `GET /data/<collection>` (static card/relic/monster/potion/event metadata); `GET /events/stream` (SSE, 15 s heartbeats — push notifications, NOT full state; client re-GETs `/state`); `POST /action`.
- **Action verbs** (`GameActionService.ExecuteAsync` switch, `GameActionService.cs:94-147`): `play_card`, `end_turn`, `use_potion`, `discard_potion`, `choose_map_node`, `choose_event_option`, `choose_rest_option`, `open_shop_inventory`/`close_shop_inventory`/`buy_card`/`buy_relic`/`buy_potion`/`remove_card_at_shop`, `claim_reward`/`choose_reward_card`/`skip_reward_cards`/`collect_rewards_and_proceed`/`resolve_rewards`, `select_deck_card`/`close_cards_view`/`confirm_selection`, `open_chest`/`choose_treasure_relic`, `choose_capstone_option`, `choose_bundle`/`confirm_bundle`, `proceed`, plus **discrete menu/lifecycle verbs**: `continue_run`/`abandon_run`/`return_to_main_menu`/`open_character_select`/`select_character`/`embark`/`open_timeline`/`close_main_menu_submenu`/`choose_timeline_epoch`/`confirm_timeline_overlay`/`confirm_modal`/`dismiss_modal`, and **`increase_ascension`/`decrease_ascension`**. (Multiplayer + `run_console_command` debug verbs also present; the latter gated off by default.)
- **Targeting is by index** (`target_index` into `combat.enemies[]`), `card_index` into `combat.hand[]`, `option_index` for selections — clean integer indices, no entity-id strings. Each `POST /action` returns `{action,status,stable,message,state}` — **the post-action state snapshot is embedded**, so the driver doesn't need a separate re-GET after actions.

**4. Logging integration.** Our OpenAI-compatible logging proxy fronts Gemini → **all LLM I/O auto-captured** (interface-agnostic; confirmed). Structured game-state worth capturing alongside: the `state` block returned inside every `POST /action` response and each `GET /state` (carries `run_id` seed, floor, deck, relics, `combat.enemies[].intents[]` with `total_damage`, ascension + `ascension_effects[]`). This is the richest of the four competitors for dataset purposes. Bonus: our fork on 8128 already emits per-run telemetry through `src/mcp_client/`'s event bus / monitor hooks if `STS2_MONITOR_ENABLED` is on — but for the *naive* agent we only need the proxy capture + the per-decision `state` JSON.

**5. CharTyr-reuse verdict — COMPATIBLE (point the agent at our 8128 mod; do NOT install CharTyr).**

Decision evidence — our client side vs. CharTyr's mod API:

| Dimension | Our client (`src/mcp_client/`, `config.py`) | CharTyr mod (`STS2AIAgent/Server/`, `Game/`) | Match |
|---|---|---|---|
| Base URL | `http://127.0.0.1:8128` (`config.py:78`, env `STS2_MCP_URL`) | `127.0.0.1:8080` default, **`STS2_API_PORT` override** (`HttpServer.cs:166-177`) | ✅ port is just an env var; our fork moved it to 8128 |
| Health | `GET /health`, expects `{ok, data:{mod_version,protocol_version}}` (`client.py:87-100`) | `GET /health` → exactly that shape (`Router.cs:33-51`) | ✅ |
| State read | `GET /state`, unwraps `{ok, data}` (`client.py:104-122`) | `GET /state` → `{ok, request_id, data}` (`Router.cs:53-65`) | ✅ |
| Action | `POST /action` w/ `{action,...}`, unwraps `{ok,data}` / `{ok,error:{code,message,retryable}}` (`client.py:128-212`) | `POST /action` → identical envelope (`Router.cs:120-138`, `Router.cs:161-182`) | ✅ |
| Avail. actions | `GET /actions/available` (`client.py:624-634`) | `GET /actions/available` (`Router.cs:67-79`) | ✅ |
| SSE | `GET /events/stream` (`sse_client.py:86`) | `GET /events/stream`, SSE + heartbeat (`Router.cs:113-118`, `197-257`) | ✅ |
| Action verbs | `actions.py` builders: `play_card`/`end_turn`/`use_potion`/`choose_map_node`/`buy_*`/`resolve_rewards`/`select_character`/`embark`/`increase_ascension`/… | every one present in `ExecuteAsync` switch (`GameActionService.cs:94-147`) | ✅ full superset |
| Targeting | `target_index` / `card_index` / `option_index` (integer) | same (`GameActionService.cs` `ResolveCardTarget` 590-657) | ✅ |
| Error envelope | `{code,message,retryable}` (`McpActionError`) | CharTyr's own Py client uses identical `Sts2ApiError{status_code,code,message,details,retryable}` (`mcp_server/.../client.py:42-56`) | ✅ |

Our `src/mcp_client/client.py` docstring even names it ("STS2-Agent REST API (CharTyr v0.5.2)"). Our mod is a **fork of this exact mod** (per `CLAUDE.md` / CHANGELOG 2026-04-29 split from `STS2-Agent-Fork`). Conclusion: **our running 8128 mod IS the CharTyr-lineage interface.** For the "CharTyr cell," install nothing — set the Gemini driver's base URL to `http://127.0.0.1:8128` and run. (Caveat: our fork is at mod version `v0.5.4-xc` per `version_compatibility.json`, ahead of the contract our client was first written against and behind CharTyr's public v0.7.2 — but the *contract* surface our client uses is unchanged across these, and our fork is the one we've actually validated on the live game. If you want the *pristine upstream* CharTyr behavior rather than our fork, install CharTyr's v0.7.2 DLL on a different port — but that's a different question than "can we reuse," and reuse is **yes**.)

**6. Character + ascension.** **Fully exposed as discrete verbs** — `open_character_select` → `select_character{option_index}` → (`increase_ascension`/`decrease_ascension` to reach A0) → `embark` (`GameActionService.cs:128/135/136/129`). Our own `client.py:start_new_run()` (lines 317-622) already drives this exact menu flow including ascension adjustment via `character_select.{ascension,can_increase_ascension,max_ascension}` fields. So for the reuse path, character + A0 selection can be **either scripted (our existing menu driver) or set manually in-menu** — both work. For the *minimal* Gemini agent that has no menu logic, simplest is: user sets Silent + A0 in-menu, agent takes over the active run.

**7. Effort + verdict.** **GO (via reuse).** This is the lowest-effort cell of all four competitors *because we skip the install*: no mod build, no mod swap, no new client. Point the naive Gemini driver at `http://127.0.0.1:8128`, reuse the documented contract (`docs/api.md` is the spec; our `src/mcp_client/actions.py` is a ready-made verb reference), set Silent + A0, run N=5. Rough effort: **~1–2 h** (just wiring the Gemini function-calling tool schemas to the 5-read + `POST /action` surface and confirming the round-trip; the separate "build the Gemini agent" task does most of this). Only conditional: blocker #0 — confirm our fork still loads on the live game build. If you additionally want pristine-upstream CharTyr v0.7.2 (not our fork) as a distinct datapoint, that's NEEDS-WORK (~0.5 day: build/install v0.7.2 on a separate port, sequential with our mod) — but it is **not required** to claim a CharTyr-lineage cell.

**8. User smoke-test checklist (CharTyr-via-reuse, the recommended path).**
1. Confirm live game version (main-menu build string) vs v0.103.1.
2. Confirm **our** mod is installed in `{game}/mods/` and the game is running (no CharTyr install needed).
3. Health: `Invoke-RestMethod http://127.0.0.1:8128/health` → expect `{"ok":true,"data":{"service":"sts2-ai-agent","mod_version":"...","protocol_version":"...","game_version":"<live>","status":"ready"}}`. Verify `game_version` matches step 1 — this is the authoritative version check.
4. In-menu: select **Silent**, set **Ascension 0**, embark; advance into the first combat. (Or script it: `open_character_select` → `select_character` → `embark`.)
5. State read: `Invoke-RestMethod http://127.0.0.1:8128/state` → confirm `data.screen=="COMBAT"`, `data.combat.hand[]` with `index`+`playable`, `data.combat.enemies[]` with `index`+`intents[]`.
6. Legal-action hint (optional): `Invoke-RestMethod http://127.0.0.1:8128/actions/available` → confirm `play_card`/`end_turn` listed.
7. One action round-trip: `Invoke-RestMethod -Method Post -Uri http://127.0.0.1:8128/action -Body '{"action":"end_turn"}' -ContentType 'application/json'` → expect `{"ok":true,"data":{"action":"end_turn","status":"completed","stable":true,"state":{...}}}`; confirm the embedded `state.turn` advanced (no separate GET needed).
8. (Targeting check) `POST {"action":"play_card","card_index":0,"target_index":0}` → confirm a card resolves against `enemies[0]` and the returned `state` reflects it.

> Pristine-upstream-CharTyr variant (only if explicitly wanted): build CharTyr v0.7.2 (`scripts/build-mod.ps1`), set `$env:STS2_API_PORT=8081`, install its DLL+pck+`mod_id.json` to `mods/` **after unloading our mod** (sequential), then repeat steps 3–8 against `:8081`. The `/health` will report `mod_version:"0.7.2"`.

---

## Summary table

| Dimension | **STS2MCP** | **CharTyr** |
|---|---|---|
| Clone state | `2fb5390`, tag `0.4.0` (2026-05-13) | `2617fb1`, tag `v0.7.2` (2026-05-17) |
| Lineage vs us | independent | **our mod is a fork of it** |
| Game ver (claimed) | v0.103.2 (README) | live via `/health`; api.md example stale (v0.98.2) |
| Game ver pin in build | none (relinks `sts2.dll`) | none (relinks `sts2.dll`) |
| Transport | plain REST (CORS-open) | REST + SSE |
| Port / auth | 15526 / none | 8080 (CharTyr) · **8128 (our fork)** / none |
| Response envelope | bare `{status,message}` / `{error}`; **no embedded state** | `{ok,request_id,data}`; **`POST /action` embeds new state** |
| State read | `GET /api/v1/singleplayer` | `GET /state` (+`/actions/available`, `/data/*`, `/events/stream`) |
| Menu model | single `menu_select{option}` (scene-tree) | discrete verbs (`select_character`, `embark`, …) |
| Targeting | **by `entity_id` string** | **by integer `target_index`** |
| Ascension control | none explicit (set in-menu) | **`increase_ascension`/`decrease_ascension` verbs** |
| Char/asc setup | manual in-menu (recommended) | scriptable OR manual |
| Need a new client? | **Yes** (bespoke REST adapter) | **No** — reuse `src/mcp_client/` on 8128 |
| LLM logging | proxy captures all I/O (interface-agnostic) | same |
| **CharTyr-reuse** | N/A (incompatible lineage) | **COMPATIBLE — use our 8128 mod, install nothing** |
| Verdict | **NEEDS-WORK** (~0.5–1 day: write+test client; sequential mod swap) | **GO via reuse** (~1–2 h; conditional on blocker #0) |
| Can user smoke-test today? | Yes, if they install STS2MCP's mod (sequential w/ ours) | **Yes immediately** — our mod is already on 8128 |

**Bottom line.** For a CharTyr-lineage cell, **reuse our 8128 mod — GO, install nothing** (contract is byte-identical; evidence in CharTyr §5). STS2MCP is a healthy, current, but *separate* interface (different port/endpoints/envelope/targeting) that is **NEEDS-WORK**: worth it only if we want a second independent interface lineage in the comparison, and it requires a bespoke REST client plus a sequential mod swap. Both verdicts are conditional on blocker #0 — confirm the live game version and that our own mod still loads before any session.
