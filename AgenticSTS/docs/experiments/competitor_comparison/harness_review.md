# Harness correctness review — competitor_runs (logging_proxy + naive_gemini_agent)

**Reviewer focus**: mid-run failure modes that would waste a sequential ~1-hour game run. Correctness, not style.
**Date**: 2026-06-05
**Files**: `scripts/competitor_runs/logging_proxy.py` (355 L), `scripts/competitor_runs/naive_gemini_agent.py` (893 L)
**Reference contract**: `src/mcp_client/{client,actions}.py`, `src/mcp_client/upstream_models.py`, `src/state/upstream_game_state.py`, `scripts/reproduce/_lib.py`.

Both files `python -m py_compile` clean. No tests exist for either.

---

## Verdict (read first)

**Would this survive a real 1-hour run? Borderline NO as written — one CRITICAL will 400-kill any long run the moment the context cap trips.**

The dominant risk is **C1 (context-trim breaks tool-call/tool-result pairing)**. With `--max-context-messages 400` and ~3-4 messages/step, the cap is hit around step ~110-130 — well inside a 1-hour Silent run (runs routinely reach 200-800 steps). When it trips, the trim slices an arbitrary count off the front of the transcript, almost always orphaning a `tool` message or stranding an `assistant` tool-call with no result. The very next Gemini call returns HTTP 400, the agent treats it as a fatal LLM error (`outcome=agent_abort`), and the whole hour is lost with no terminal game state. This is exactly the "looks fine in --dry-run, dies mid-run" failure the review was asked to catch.

Everything else is survivable-but-degrading (capture-fidelity gaps, a schema field the recompute scripts won't read, a couple of run-setup edge cases). Fix C1 before any real run; fix H1/H2 before trusting the captured dataset.

**Score: 72 / 100.** Solid, faithful-to-contract skeleton (envelope handling, verbs, targeting fields, terminal detection, timeouts, stuck guard all correct), but the single accumulation bug is run-fatal and the dataset-join field is wrong.

CRITICAL: **1**  ·  HIGH: **3**  ·  MEDIUM: **5**  ·  LOW: **4**

---

## CRITICAL

### C1 — Context trim orphans tool-call/tool-result pairs → next Gemini call HTTP 400 → run aborts mid-game
`naive_gemini_agent.py:529-541` (`_trim_messages`), invoked at `:618`.

```python
def _trim_messages(messages, cap) -> bool:
    if len(messages) <= cap:
        return False
    overflow = len(messages) - cap
    del messages[1 : 1 + overflow]   # blind slice from front of post-system region
    return True
```

The transcript grows as `[system, user₁, assistant₁(tool_calls), tool₁, user₂, assistant₂, tool₂, …]` (assistant tool-call messages and their `role:"tool"` replies are appended at `:632` and `:687-693`). `del messages[1:1+overflow]` removes a raw count from index 1 with **no regard for message boundaries**. Two guaranteed-fatal outcomes:

1. **Orphaned tool result**: the slice ends between an `assistant(tool_calls)` and its `tool` reply — the surviving `tool` message references a `tool_call_id` that no longer has a preceding assistant tool-call. The chat-completions API rejects this (`tool` message must follow the assistant message that issued the call).
2. **Dangling tool-call**: the slice removes an `assistant` that carried `tool_calls` but leaves the matching `tool` removed/half-removed, or leaves an assistant tool-call as the *last* message with no following result.

Either shape → the next `gemini.complete()` (`:627`) gets HTTP 400 → caught at `:628` → `outcome="agent_abort"`, `break`. The docstring even claims "Trims tool-call/result pairs together where possible" but the implementation does no such pairing.

**Why it WILL fire in a real run** (not theoretical): default cap 400; each step appends 1 user + 1 assistant + N tool messages (≥3). 400/3 ≈ 133 steps to first trip; Silent A0 runs are routinely 200-800 steps. So a clean run that should reach a boss instead 400-dies around the act-1/act-2 boundary, producing an `agent_abort` record that the recompute scripts **discard** (`_lib.py:345` ABORT_OUTCOMES) — i.e. a wasted hour that yields zero usable data.

**Fix** — trim in whole *rounds* and never leave a hanging tool-call. Drop from the front only at a `user`-message boundary, taking the full `user → assistant → tool*` group:

```python
def _trim_messages(messages, cap) -> bool:
    if len(messages) <= cap:
        return False
    # Walk forward from index 1, removing complete (user, assistant, tool*) groups
    # until under cap. Never split a group; never leave a trailing assistant tool-call.
    i = 1
    while len(messages) > cap and i < len(messages):
        # advance to next user boundary after the first group
        j = i + 1
        while j < len(messages) and messages[j].get("role") in ("assistant", "tool"):
            j += 1
        del messages[i:j]          # remove one whole group
    return True
```

A pragmatic alternative that is also safe: only ever trim when `messages[-1]` is a `tool` (end of a completed round), and remove from the front up to the next `user` boundary. Whatever the strategy, add a guard/assert that after trimming, (a) no `tool` message lacks a preceding `assistant` with a matching id, and (b) the last message is not an assistant carrying unanswered `tool_calls`. **This single bug is the whole "survive a real run" question.**

---

## HIGH

### H1 — `run_summary.json` uses `condition_tag`, but the recompute/dataset scripts key on `experiment_tag`
`naive_gemini_agent.py:762` writes `"condition_tag": args.condition_tag`. PLAN.md:103 and the README:79 promise the summary "slots into the recompute scripts." It does not: `scripts/reproduce/_lib.py:365` filters cells by `r.get("experiment_tag")` and `:368` sorts by `r.get("started_at")`. A competitor record with only `condition_tag` is invisible to `filter_cell` (matches nothing) and to the comparison rows.

Also missing vs the `runs/history.jsonl` fields CLAUDE.md lists (outcome / target_ascension / actual_ascension / experiment_tag / experiment_condition_id): there is no `experiment_tag`, no `actual_ascension`, no `target_ascension`. `derived_score_for` (`_lib.py:139`) only needs `outcome`+`final_floor` (both present, correct), so scoring works *if* the record is selected — but selection is by `experiment_tag`, which is absent.

**Fix**: emit `experiment_tag` (set it = `condition_tag`, or add a separate `--experiment-tag`) and add `target_ascension`/`actual_ascension` (= `args.ascension`, since A0 is fixed). Keep `condition_tag` too if you like. Minimal: `summary["experiment_tag"] = args.condition_tag`. Without this the captured runs cannot be folded into Table-2-style comparison without a manual post-hoc rewrite.

### H2 — Proxy SSE assembly drops tool-call deltas → streamed competitor captures lose the actual decision
`logging_proxy.py:148-200` (`_assemble_stream`). The assembler concatenates only `delta.get("content")` (`:182-183`) and ignores `delta.get("tool_calls")`. For a function-calling agent that streams (AI-Spire's native client, and any OpenAI-streaming competitor), the *entire decision* lives in `delta.tool_calls`, not in `content`. The assembled `response.choices[0].message` will therefore be `{"role":"assistant","content":""}` with **no `tool_calls`** — the released dataset record shows the model "said nothing" on every tool turn. This silently guts the capture fidelity for exactly the streaming cell the proxy exists to serve.

(Does NOT affect the naive Gemini agent: `GeminiClient.complete` never sets `stream`, so it hits the non-streaming path `:291-327`, which logs `resp.json()` verbatim — faithful. So this is a dataset-fidelity bug for *other* cells, not a naive-agent run-killer. Still HIGH because the proxy's stated purpose is "identical, complete capture regardless of agent.")

**Fix**: in the SSE loop, also accumulate `delta.tool_calls` by `index` (id/name/arguments concatenation, standard OpenAI streaming reassembly) and emit a `tool_calls` array on the assembled message. Also capture `finish_reason == "tool_calls"`.

### H3 — Proxy returns 502 to a *non-streaming* upstream failure, but a *streaming* upstream failure forwards a truncated 200 stream with no error surfaced to the caller
`logging_proxy.py:254-289`. On the streaming path, if the upstream errors mid-stream (`:265` except), the proxy has already begun yielding `200 text/event-stream`; it swallows the exception, records `error` in the JSONL (good), but the **caller sees a silently truncated stream with HTTP 200 and no `[DONE]`** — no error token, no status change. A competitor client that trusts the stream will parse a partial/empty completion and make a bad decision, or hang waiting for `[DONE]`. The non-streaming path correctly returns 502 (`:323-326`); the streaming path cannot (headers already sent) but should at least emit a terminal SSE error event so the client can distinguish "model finished" from "upstream died."

(Again: not a naive-agent killer since it's non-streaming, but it corrupts streaming competitor runs without any signal. Capture integrity itself is fine — the record is written in `finally`.)

**Fix**: on mid-stream exception, `yield` a synthetic `data: {"error":{"message": ...}}\n\n` (or at minimum a final `data: [DONE]`) before the generator returns, so streaming clients see a clean terminus.

---

## MEDIUM

### M1 — Multiple `take_action` calls in one model turn all execute, but only the LAST is captured to game_io and the stuck detector
`naive_gemini_agent.py:651-701`. The loop executes **every** tool call (correct for the LLM contract — each gets a `tool` reply). But `chosen_action`/`action_result` are overwritten each iteration (`:672, :675-683`), and `capture.step` (`:696`) records only the final one. If Gemini emits two `take_action`s in a turn (e.g. `play_card` then `end_turn`), both hit the live game, the game advances two steps, but `game_io.jsonl` logs one — desyncing the per-step capture from reality and mis-feeding stuck detection (`:704-719`, which only sees the last action). For a dataset whose whole point is faithful game I/O, this is a real integrity gap.

**Fix**: either (a) capture a `step` per executed `take_action` (move `capture.step` inside the loop for action calls), or (b) instruct/enforce one tool call per turn (the user prompt already says "exactly one tool call" at `:615`, but nothing enforces it — Gemini can and does batch).

### M2 — Proxy in-memory `seq` counter is not concurrency- or restart-safe
`logging_proxy.py:112,119-122`. `next_seq` reads-increments a plain dict with no lock. FastAPI/uvicorn can interleave `async` requests; two near-simultaneous completions on the same `run_id` can race the dict and produce a duplicate or non-monotonic `seq`. Also, if the proxy is restarted mid-batch the counter resets to 0 (re-derives from nothing, not from the existing JSONL), so `seq` restarts at 1 within an already-populated file. For the naive agent (strictly serial calls) this won't bite; for a parallel/batched competitor it can. Records are append-only so nothing is *lost*, but `seq` monotonicity (an explicit review criterion) is not guaranteed.

**Fix**: seed `_seq[run_id]` from the existing line count on first touch, and guard `next_seq` with an `asyncio.Lock` (or accept it and document "serial callers only").

### M3 — `act_reached` / `final_floor` never populated on a pre-combat menu abort, and `final_floor` can regress to 0
`naive_gemini_agent.py:591,595`. `final_floor = run_block.get("floor", final_floor) or final_floor` — the `or final_floor` guards a literal `0`/`None`, good. But on the terminal branch `:595`, `final_floor = go.get("floor", final_floor) or final_floor`: `RawGameOverPayload.floor` is `int | None` and is frequently `None` at death, so this falls back to the last in-run floor — correct. The subtle issue: if death is detected on the *first* loop (e.g. agent takes over a dead run), `final_floor` is still 0 and `act_reached` 0, producing a score-0 record indistinguishable from "never started." Minor, but worth a floor-from-`run` fallback before the terminal check. Low-frequency.

### M4 — `summarize_state` reads top-level `turn`/`act`/`in_combat`, which are present, but `combat.player` HP fields can render `"None/None"`
`naive_gemini_agent.py:428-431,447`. `f"{player.get('current_hp')}/{player.get('max_hp')}"` yields the string `"None/None"` if the combat block exists but `player` is the default-empty object (e.g. a transient mid-resolve state). Harmless to the game (presentation only) but pollutes the prompt and the dataset with `"None/None"` HP. Same pattern for enemies `:448`. Consider guarding with `if player:` or `?? "?"`. Cosmetic / dataset-cleanliness.

### M5 — Run-setup `_ascension_ok` issues an inc/dec then returns False, but the outer loop re-reads only after `step_delay`; on `embark`-available-but-ascension-mismatch it loops without an explicit cap on ascension nudges
`naive_gemini_agent.py:186-188,249-276`. The flow mirrors `client.start_new_run` reasonably. But `_ascension_ok` is called **inside the `embark` guard's `and` chain** (`:186-188`): if `_character_ready` is true and `embark` is available but ascension ≠ target, `_ascension_ok` fires one inc/dec and returns False, so the `embark` branch is skipped this attempt — fine, it re-checks next loop. The risk: each ascension nudge consumes one of the 30 `max_attempts` (`:161`) at 1.5 s each. Reaching A10 from A0 would need 10 attempts just for ascension before embarking; default 30 attempts is enough for A0 (the only target here) but would silently fail for higher ascensions with no distinct error. Since this harness is A0-only (`--ascension 0` default, PLAN locks A0), it's fine *as configured* — flag it so nobody reuses it for a laddered cell.

---

## LOW

### L1 — Dead/incorrect screen branch in `is_terminal`
`naive_gemini_agent.py:480` checks `screen in ("GAME_OVER","VICTORY","DEFEAT")`. The mod never emits those `screen` strings (verified: `derive_state_type` in `src/state/upstream_game_state.py:153-223` maps game-over via the `game_over` block, and `screen` is one of MAIN_MENU/COMBAT/MAP/EVENT/REST/SHOP/REWARD/CARD_SELECTION/CARDS_VIEW/CHEST/CHARACTER_SELECT/TIMELINE/MODAL). Harmless because `:477` (`game_over` block) catches the real signal first, but the branch is misleading dead code. Drop it or comment that it's a defensive fallback.

### L2 — `MENU_SCREENS` includes `"UNKNOWN"`/`""` so a transient unknown screen mid-run is misread as "still at menu"
`naive_gemini_agent.py:46,173`. In `ensure_run_active` this only matters during setup (before the run loop), and the `or state.get("run")` clause rescues it (a populated `run` block ⇒ treated as active). So no live-run impact. Noted for completeness.

### L3 — `GeminiClient` has no retry on a transient 429/503 from the relay
`naive_gemini_agent.py:367-391`. Any non-200 (`:382`) raises → caught at `:628` → `agent_abort`. A single transient 429 (rate limit) from the Gemini relay mid-run kills the whole hour. The production client doesn't retry LLM calls either, but the production orchestrator has `_force_unstick` resilience; here there's none. Consider one bounded retry with backoff on 429/500/502/503. (Not CRITICAL because the relay is local and usually reliable, but it's a cheap insurance against a wasted hour.)

### L4 — File size: 893 L vs the 800-L house limit (CLAUDE.md coding-style)
`naive_gemini_agent.py` is 893 lines. There is a clean, non-churn split: extract the REST layer (`ModApiError`, `ModClient`, `ensure_run_active`, `_character_index/_character_ready/_ascension_ok`, `summarize_state`, `is_terminal`, `MENU_SCREENS`) into `scripts/competitor_runs/_mod_client.py` (~330 L), leaving the Gemini loop + capture + CLI (~560 L) in the main file. This mirrors the repo's own `src/mcp_client/` (client vs actions split) and is a genuine cohesion win, not churn. The proxy (355 L) is fine. **Recommend the split** but it is not a correctness issue.

---

## Confirmed-correct (checked against the reference, no action needed)

- **Envelope handling** (`naive_gemini_agent.py:77-96`) matches `src/mcp_client/client.py:128-191`: unwraps `{ok,data}`, raises on `ok:false` with `code/message/retryable`, handles empty body and non-JSON. Faithful.
- **Endpoint paths + verbs**: `/health`, `/state`, `/actions/available`, `POST /action` all correct. Run-setup verbs (`open_character_select`, `select_character{option_index}`, `increase_ascension`/`decrease_ascension`, `embark`, `continue_run`, `confirm_modal`, `close_main_menu_submenu`) all exist in `src/mcp_client/actions.py:183-225`. No guessed verb names. The `take_action` tool-description verb list (`:308-318`) maps cleanly to `actions.py`.
- **Targeting fields**: `card_index` / `target_index` / `option_index` match `actions.py` exactly. Body construction `{"action": verb, **params}` (`:671`) matches the production wire format.
- **Terminal detection** (`is_terminal:471-482`): `game_over.is_victory` is the right signal (`upstream_models.py:651`, `derive_state_type:155`). Correct.
- **State field names in `summarize_state`**: `run.character_name`, `run.floor`, `run.gold`, `run.relics[].name`, `run.potions[].name`, `combat.player.{current_hp,max_hp,block,energy}`, `combat.hand[].{index,name,energy_cost,playable,requires_target,valid_target_indices}`, `combat.enemies[].{index,name,current_hp,max_hp,block,is_alive,intents[].{intent_type,total_damage}}`, `character_select.{selected_character_id,ascension,max_ascension,can_increase_ascension,can_decrease_ascension,characters[].{index,character_id,name,is_selected}}` — **all verified against `upstream_models.py`.** No field-name drift. (`agent_view` forwarding at `:462-467` uses keys that mostly exist on `AgentViewPayload`; `selection`/`game_over` exist, `reward`/`shop`/`event`/`rest`/`map`/`chest` exist. Fine.)
- **Timeouts**: agent LLM client 600 s read / 15 s connect (`:356`); mod client 30 s (`:70`) with explicit `TimeoutException → retryable read_timeout` (`:134-137`) mirroring `client.py:194-200`. Proxy upstream 600 s / 15 s connect (`logging_proxy.py:213`). No unbounded waits — no network-stall hang.
- **Stuck guard** (`:703-719`): identical-action-body repeat counter, clean `agent_abort`, never hangs. Correct.
- **Capture written on error**: proxy writes the JSONL record in `finally` (streaming `:267-285`) and unconditionally on the non-streaming path (`:305-321`) even on upstream 5xx/timeout. One record per call. ✔ (the `error` field is populated). 
- **run_id resolution** (`logging_proxy.py:215-220`): header `x-run-id` → `PROXY_RUN_ID` env → `"default"`. Correct precedence; the agent sends `X-Run-Id` (`:360`). Header names are case-insensitive in Starlette so `x-run-id` lookup works.
- **Non-streaming capture fidelity**: logs `resp.json()` verbatim (`:299`), with `_raw_text` fallback on non-JSON (`:301`). Faithful for the naive agent.
- **`--dry-run`**: hits mod `/health` + a 1-message Gemini round-trip, no game loop. Safe smoke test as documented.

---

## Priority order for the fix pass

1. **C1** — rewrite `_trim_messages` to trim whole rounds (run-fatal; do before any real run).
2. **H1** — add `experiment_tag` (+`actual/target_ascension`) to `run_summary.json` (else the data can't be used).
3. **H2** — capture streamed `tool_calls` in the proxy (before the AI-Spire cell).
4. **M1** — capture one game_io step per executed `take_action` (or enforce single tool call).
5. **H3 / M2 / L3** — streaming error terminus, seq lock+seed, one LLM retry — harden before scaling to parallel/other cells.
6. **L4** — optional `_mod_client.py` split.
