# Feasibility — AI-Spire & HermesBridge

**Compiled**: 2026-06-05 (controller, from direct reads of repo config/README/manifest/run-records + `paper/narrative/competitor_analysis.md`).
**Experiment**: drive each with Gemini 3.1 Pro at A0, N=5, capture all raw prompts/responses for the released dataset; compare against our frozen-A0 cells.
**Cannot launch the game from here** — verdicts are static; each repo has a user smoke-test checklist.

> ⚠️ **Global blocker #0 — installed game version.** Our last verified pin is **v0.103.1** (2026-04-17, `data/version_compatibility.json`), but today is 2026-06-05 — Steam may have auto-updated the game since. STS2 mods are Harmony-patched against specific game assemblies, so **every verdict below is conditional on what version is actually installed right now.** First action for the user: confirm the live game version (main-menu build string) and whether **our own mod still loads** on it. If the game drifted off v0.103.1, our own mod may also need a rebuild before any competitor work.

---

## AI-Spire

**1. Game-version compatibility.** README requires "v0.98+"; repo is v0.2.0 (2026-03-19). The prebuilt release DLL was compiled against an early-2026 game build. Against v0.103.1 (or a newer auto-updated build) the Harmony patches may fail to bind. **Most likely needs a rebuild from source against the installed game's assemblies** (`.csproj` has a `<Sts2Dir>` pointing at the game install; `dotnet build` relinks). Risk: MEDIUM — it's an in-process Harmony mod, and the game's combat/turn API may have shifted since v0.98.

**2. Install artifact.** Two paths: (a) prebuilt `AISpire.zip` from their Releases → drop into `{game}/mods/AISpire/`; (b) build from source — needs **.NET 9 SDK + Godot .NET SDK 4.5.1** (auto-restored), set `<Sts2Dir>` in `AISpire.csproj`, `dotnet build` (auto-copies DLL+config+data to `mods/AISpire/`). **Conflicts with our mod** (both patch the game) → must unload our mod; runs are **sequential**.

**3. Gemini wiring** (`mods/AISpire/config.json`):
```json
{
  "api_key": "<our-relay-key>",
  "api_endpoint": "http://localhost:<PROXY_PORT>/v1/chat/completions",
  "model": "gemini-3.1-pro-preview",
  "api_timeout_ms": 120000,
  "max_retries": 1,
  "enabled": true,
  "verbose_logging": true,
  "max_history_messages": 40,
  "language": "en"
}
```
- `api_endpoint` → our **logging proxy** (C.1), which forwards to the Gemini relay → every LLM call captured.
- **Bump `api_timeout_ms` 15000 → 120000.** Gemini 3.1 Pro with thinking routinely exceeds 15 s; at 15 s the call times out and **`RuleEngine` fallback fires**, contaminating the "LLM agent" signal with mechanical play. This is a fairness-critical change. Document it.
- Keep `max_history_messages: 40` — that 40-msg rolling chat IS the accumulating-context design we're comparing against. Do not change it.
- `language: en` to keep prompts/codex English (matches our setup; avoids the bilingual auto-switch).

**4. Logging integration.** All LLM I/O captured at the proxy. **Gap:** when `RuleEngine` fallback fires, no LLM call is made → it won't appear in the proxy log. Detect fallbacks via `verbose_logging` game-log lines; report the fallback count per run (ideally 0 after the timeout bump). A run with many fallbacks is not a clean LLM-agent datapoint.

**5. Character.** **Ironclad only** (README Roadmap: "Currently only Ironclad is supported … other characters coming later"). Per user decision: run Ironclad, document that the repo doesn't support Silent. Comparison is "same model, same difficulty, accumulating-context design; character differs from our Silent headline."

**6. Auto-progression.** None. AI-Spire plays whatever run is active. **User sets Ironclad + A0 in the game menu and starts the run; the AI takes over once in-game.** (Its `ScreenHandler` covers map/shop/event/reward/treasure/rest, but character-select/ascension menu handling is unconfirmed — assume manual setup.) We run **fixed-A0**, not auto-ladder.

**7. Verdict: NEEDS-WORK → GO.** Blocker = rebuild against the installed game version (only if the prebuilt DLL won't load). Effort: ~1–2 h if the .NET toolchain is present and the game API hasn't shifted much; more if combat-API patches broke. Once it loads, Gemini wiring is a 1-line config edit.

**8. User smoke-test checklist.**
1. Confirm installed StS2 version (main-menu build string). Note it.
2. Try the **prebuilt** `AISpire.zip` first: extract to `{game}/mods/AISpire/`, set `config.json` (table above, proxy endpoint).
3. Launch game with **our mod removed/disabled**. Watch the mod-loader log for "AISpire loaded" vs a binding/Harmony exception.
4. If it fails to load → build from source: install .NET 9 SDK, set `<Sts2Dir>` in `AISpire.csproj`, `dotnet build`, re-launch.
5. Start an **Ironclad A0** run from the menu.
6. Enter the first combat. Confirm: (a) the in-game overlay shows AI reasoning, (b) a `/v1/chat/completions` request lands in the proxy log, (c) the AI plays a card and ends the turn.
7. Check the game verbose log for `RuleEngine` fallback messages — there should be ~none with the 120 s timeout. If frequent, the proxy/endpoint is misconfigured.
8. If 1 combat completes cleanly → GO for the N=5 batch.

---

## HermesBridge

**1. Game-version compatibility.** Run records show **`game_version: 0.104.0`**, `bridge_version: v0.1.5` — newer than our v0.103.1 pin. The mod likely targets 0.104.x and **may not load on v0.103.1**. This is the central risk and cuts both ways: if the user's game auto-updated to 0.104.x, HermesBridge may load but **our own mod (built for 0.103.1) may not**. Resolving this may force a choice between game versions. Risk: HIGH (version fork).

**2. Install artifact.** C# mod (`HermesBridge.dll`) on the BaseLib loader; prebuilt likely in repo/releases, else build from source (.NET 9). Installs to `mods/`. **Conflicts with our mod** → sequential.

**3. Gemini wiring.** HermesBridge ships **no LLM binding** — the "agent" is an external coding-agent loop (they used **OpenCode** with `gemini-3.1-pro-preview` via the github-copilot provider; see `run07` front-matter) reading `SKILL.md` and driving via file-IPC (`state.json` → `commands.json` → `result.json` under `%APPDATA%\SlayTheSpire2\hermesbridge\`). To run Gemini: configure **OpenCode** (or equivalent agentic harness) with our Gemini relay as the model backend, point it at `SKILL.md`. Proven to work (run07 exists).

**4. Logging integration.** Their existing Gemini runs captured **zero tokens** (`tokens_total: 0` — copilot didn't expose usage), so their on-disk runs are **not dataset-grade** (no prompt/response capture). To get clean data we must route OpenCode's Gemini calls through **our logging proxy** (set OpenCode's model base URL to the proxy). Feasible only if OpenCode allows a custom OpenAI-compatible base URL. Confirm during setup.

**5. Character.** All 5 including **Silent** — so HermesBridge *can* match our headline character (unlike AI-Spire). But note HermesBridge is **per-tick stateless** (it explicitly forbids accumulation), so it is *not* an accumulating-context comparator — it's philosophically closer to us. Its value here is a "stateless, no-memory, frontier-driven" external datapoint on the matching character.

**6. Auto-progression.** The coding agent can drive menus via bridge commands (`SelectMapNode`, etc.), so it can in principle set up and start an A0 run; in practice the user sets Silent + A0 and lets the agent play. Fixed-A0.

**7. Verdict: NEEDS-WORK, possibly NO-GO.** Two stacked blockers: (a) **game-version fork** (0.104 mod vs 0.103.1 game/our-mod) — must be resolved first; (b) OpenCode+Gemini+proxy driver setup. If the version conflict can't be reconciled without breaking our own mod, defer HermesBridge. Effort: HIGH. **Note:** they already have 5 Gemini-3.1-Pro runs (incl. Silent) we can **cite** even if we don't re-run — but those lack prompt logs, so they're comparison context, not dataset material.

**8. User smoke-test checklist.**
1. Confirm installed game version. **Decision gate:** does our own mod still load on it? If the game is on 0.104.x and our mod is broken, this is a bigger issue than HermesBridge.
2. Install HermesBridge mod; launch game; confirm "HermesBridge loaded" + `state.json` appears under `%APPDATA%\SlayTheSpire2\hermesbridge\`.
3. Install OpenCode; configure model = our Gemini relay via the logging proxy base URL; verify a trivial Gemini call lands in the proxy log.
4. Point OpenCode at `SKILL.md`; start a Silent A0 run.
5. Confirm one combat: agent writes `commands.json`, mod responds `result.json`, proxy captures the Gemini prompt/response.
6. If clean → GO; else defer and fall back to citing their existing Gemini runs.

---

## Summary

| Repo | Verdict | Biggest blocker | Effort | Character | Context style |
|---|---|---|---|---|---|
| **AI-Spire** | NEEDS-WORK → GO | Rebuild vs installed game version (if prebuilt won't load) | ~1–2 h | Ironclad only | **Accumulating (40-msg)** — the comparator we want |
| **HermesBridge** | NEEDS-WORK / maybe NO-GO | Game-version fork (0.104 mod vs 0.103.1 game/our-mod) + OpenCode driver | HIGH | all 5 (Silent ✓) | Per-tick stateless (not a contrast) |

**Recommendation:** AI-Spire is the priority — it's the canonical accumulating-context agent, Gemini drops in via one config edit, and it gives the contrast the paper wants. HermesBridge is gated on the game-version fork; if resolving it would break our own mod, defer it and cite their existing Gemini runs instead. **Both depend on first confirming the live game version and that our own mod still loads.**
