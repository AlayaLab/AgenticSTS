# Competitor runs — current state & resume (2026-06-06)

## BLOCKER: LLM relay credit exhausted (needs user action)

The whole competitor pipeline is built and **validated end-to-end**, but the runs are
blocked purely on **LLM credit**:

- **a relay** (`STS2_GEMINI_BASE_URL=https://proxy.example.com`, key `…cfv0UW`): billing API
  reports `hard_limit_usd = 2261.04`, `total_usage = $2261.04` → **~$0 remaining**.
  Calls return `403 pre_consume_token_quota_failed` ("token quota is not enough").
- **a relay** (`STS2_a relay_GEMINI_*`): balance `¥-2.69` (negative).

A full A0 run via the naive/MCP agent makes ~hundreds of Gemini calls (~$1–5/run); N=5 ×
3 mods ≈ $20–70 of spend the accounts can't cover. **Pacing/backoff cannot fix a
zero-balance account.**

### To unblock (any one of):
1. Top up / raise the a relay quota on the existing key, **or**
2. Restore the a relay balance (then set the proxy to use it — see below), **or**
3. Put a different **funded** Gemini-capable credential in `.env`
   (`STS2_GEMINI_BASE_URL` + `STS2_GEMINI_API_KEY`, or a direct Google key + adjust the
   proxy upstream).

## Everything else is READY (validated)

- **Smoke proof**: `smoke-sts2mcp-03` ran **12 clean steps** (menu_select → combat →
  play cards), **12/12 LLM calls 200 with tool_calls, 0 errors, no stuck**, logs recorded
  perfectly (`captures/smoke-sts2mcp-03/{llm_calls,game_io}.jsonl`). The pipeline works;
  it only ran out of credit.
- **3 mods built + staged** (`paper/competitors/_staged_mods/{sts2mcp,chartyr,aispire}/`).
  STS2MCP currently installed in the game `mods/`; game is running.
- **Harness**: proxy (`:8129`, `/v1` upstream, retry+backoff on 403/429/5xx, Gemini schema
  sanitizer), `mcp_gemini_host`, `run_batch` (paced 3 s), `mod_swap.ps1`, `inspect_capture.py`.

## Resume (once credit is available)

```powershell
# (if proxy not running) start it:
python -m scripts.competitor_runs.logging_proxy --port 8129
# game running + STS2MCP mod loaded (mod_swap -Competitor sts2mcp), then:
python -m scripts.competitor_runs.run_batch --competitor sts2mcp --n 5
python -m scripts.competitor_runs.inspect_capture competitor-sts2mcp-gemini-A0-a01   # spot-check logs
# then swap + repeat:
.\scripts\competitor_runs\mod_swap.ps1 -Competitor chartyr   # restart game after swap
python -m scripts.competitor_runs.run_batch --competitor chartyr --n 5
# AI-Spire (Ironclad): mod_swap aispire, restart game, MANUALLY start an Ironclad A0 run
#   (AI-Spire has no menu-navigation code — it only plays an already-started run),
#   then it self-plays via config.json -> proxy.
```

## Fixes applied this session (for the record / patches_applied.md)
- Proxy upstream: append `/v1/chat/completions` (a relay 307'd on bare `/chat/completions`).
- `.env` bootstrap for the standalone tools (`_bootstrap.py`).
- Gemini function-call **schema sanitizer** (recursive; STS2MCP `menu_select.seed` had no `type`).
- **Retry + exponential backoff** on transient relay errors (403/429/5xx/timeout) in `GeminiClient`.
- Pacing (`--action-delay 3` default in `run_batch`).
- `mods/` cleanup of ~35 stale `STS2AIAgent.dll.bak*` files; `mod_swap` glob-clear.
- AI-Spire compat: `Description` → `DynamicDescription` ×4 (game privatised `Description`).
