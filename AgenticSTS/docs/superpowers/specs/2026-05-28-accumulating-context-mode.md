# Accumulating-Context Mode Design

**Date:** 2026-05-28
**Status:** Design (pre-implementation)
**Scope:** arXiv-version 6th ablation cell `accum-context-A0`. Unblocks Workstream B.1 in [paper/post_submission_plan.md](../../../paper/post_submission_plan.md).
**Owner of follow-up coding:** main session (this memo is design-only — no source edits).

## 1. Problem Statement

The submitted EMNLP paper's central architectural claim is the **bounded-memory contract**: every decision $d$ at state $s_d$ sees a freshly composed user message $u_d = \pi(L_1, L_2(s_d), L_3(s_d), L_4(s_d), L_5(s_d))$ sent as `<sys, u_d>`. **No raw cross-decision transcript is appended.** ([architecture.tex](../../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/architecture.tex), §4.1; combat truncation executed at [conversation.py:343-377](../../../src/brain/conversation.py).)

[limitations.tex](../../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/limitations.tex) names *same-codebase accumulating-context variant* as the cleanest direct comparison and notes the release was organized so one further row in the matrix can run it. The arXiv version will add `accum-context-A0` as the 6th cell, matched against `mode-a` (same prompts, same hand-authored $L_5$, same fixed-$A_0$ Gemini 3.1 Pro, $N{=}10$, score formula `s = 100 if victory else floor + (52/3)·bosses`). The only delta is the **interface**: typed per-decision retrieval → accumulating raw transcript.

This memo answers the three architectural questions in [post_submission_plan.md](../../../paper/post_submission_plan.md) §B that block coding:

- **Q1**: Where and how to disable the combat truncation point.
- **Q2**: How to think about prompt-cache invalidation and the "10× token cost" estimate.
- **Q3**: What semantic accumulation unit best matches the paper's target counterfactual.

## 2. Current State Analysis

### 2.1 Where context is composed

Two assembly sites; both produce a *fresh* user message per call. No `_messages` cache lives on `V2Engine`.

**Non-combat** — [v2_engine.py:474-569](../../../src/brain/v2_engine.py):

```python
sections = [skill_context, memory_context, knowledge_context, extra_context, state_prompt, schema_hint]
user_content = "\n\n".join(sections)
messages = [{"role": "user", "content": user_content}]   # ← Always exactly 1 entry
```

`decide_noncombat` is the entry point for map / shop / reward / event / rest / treasure / card_select / hand_select / intermission state types. Each call rebuilds `messages` from scratch.

**Combat** — [v2_engine.py:571-630](../../../src/brain/v2_engine.py) calls `_single_call` with `messages=conversation.llm_messages`, which is the truncation property at [conversation.py:343-377](../../../src/brain/conversation.py):

```python
@property
def llm_messages(self) -> list[dict[str, Any]]:
    # Always returns exactly [combat_start, "ok", latest_user_state]
    ...
    return [
        self._messages[0],                                          # combat_start (cache anchor)
        {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
        self._messages[last_user_idx],                              # latest re-injected round state
    ]
```

Internal `_messages` accumulates the full record (plans, validation errors, results, compression artefacts) — the truncation is the **load** point, not the **store** point. `add_round_state` ([conversation.py:843-1000](../../../src/brain/conversation.py)) re-injects Strategic Thread, combat rules, enemy patterns, potions, and keyword glossary into *every* round-state user message, so the truncated 3-message view is self-contained.

The static prefix `[combat_start, "ok"]` serves as a cache anchor — see [MEMORY_SYSTEM.md §combat decisions](../../reference/MEMORY_SYSTEM.md#combat-decisions).

### 2.2 Compression and `_messages` shape

[conversation.py:511-668](../../../src/brain/conversation.py) `compress_history(keep_recent=1)` runs automatically when `_round_count > 3`. It rewrites `_messages` into `[combat_start, summary_user, "ok", recent_rounds...]`. In bounded mode this is wasted work (truncation already drops the prefix), but the work is real and changes the shape of `_messages`.

`_round_msg_starts: list[int]` and `_round_summaries: list[str]` track round boundaries — used only by compression today, but useful for any "render full transcript" path.

### 2.3 Prompt caching wiring

Two backends, both reached through `V2Backend.acall(system, messages, ...)`:

- **OpenAI-compatible relay** (current Gemini / GPT / Qwen / DeepSeek path) — [v2_backend.py:1257-1750](../../../src/brain/v2_backend.py): system is a plain string in `{"role": "system", "content": system}`; no explicit `cache_control` markers. Prompt caching is *automatic at the relay* (Gemini's implicit prefix cache; OpenAI's `cached_tokens` field). Usage rows already capture `cached_tokens` → `usage_obj.cache_read_input_tokens` ([v2_backend.py:1230-1240](../../../src/brain/v2_backend.py)).
- **Anthropic SDK direct** ([v2_backend.py:1797-1830](../../../src/brain/v2_backend.py)): `system` is passed via `kwargs["system"]` with implicit caching governed by `STS2_ANTHROPIC_DISABLE_CACHE`. No explicit ephemeral breakpoint on messages.

Per [evolution_engine.py:341-349](../../../src/brain/evolution_engine.py), explicit `cache_control: ephemeral` is used in postrun flows (Turn 1/2/3 of memory extraction), **not** in gameplay decisions. So the "ephemeral" mention in CLAUDE.md refers to a postrun pattern; gameplay relies on automatic relay-level prefix caching for the (stable) combat-start prefix.

### 2.4 Cross-decision state today

[MEMORY_SYSTEM.md §What does cross decision boundaries](../../reference/MEMORY_SYSTEM.md#what-does-cross-decision-boundaries) — three things, none of which is `messages`:

1. **In-prompt rebuilt state** (Strategic Thread, retriever output, card notes) — re-rendered per call into the fresh user message.
2. **Within-decision repair turn** in `_single_call` — bounded by one decision.
3. **Cached metadata** on `V2Engine` (only `_backend`, `_executor`, `_session_logger`).

So adding "accumulating context" is structurally new: we must introduce a conversation-like object that **persists across decisions** for the first time on the non-combat path.

## 3. Q-by-Q Option Comparison

### Q1 — CombatConversation truncation point

The truncation lives at [conversation.py:343-377](../../../src/brain/conversation.py). Three ways to flip it:

| Option | Sketch | Pros | Cons |
|---|---|---|---|
| **(a) `llm_messages` conditional** | Top-of-property `if config.ACCUM_CONTEXT: return self._messages` else current 3-msg truncation. Disable `compress_history` call site too. | Single load-point flip. No new classes / wrappers / AgentLoop wiring. Mirrors existing ablation flags (`STS2_PROMPT_VARIANT`, `STS2_COMBAT_CONVERSATION_ENABLED`, `STS2_STM_ENABLED`). | Docstring becomes conditional ("returns 3 msgs OR full history"). `_messages` accumulation has compression-shaped artefacts unless compression is also gated. |
| **(b) V2Engine wrapper** | `V2Engine.generate_combat_plan` reads `messages = conversation.full_messages if accum else conversation.llm_messages`. Add `full_messages` property; leave `llm_messages` untouched. | Keeps `llm_messages`'s "bounded by construction" guarantee. Separates dispatch concern from storage. | Two properties to maintain in parallel. Caller must remember to pick the right one — easy to drift. Doesn't help non-combat path (Q3) at all. |
| **(c) `AccumCombatConversation` subclass** | New class overrides `llm_messages` and (if needed) `compress_history` / `add_round_state`. Factory in `AgentLoop` picks the class via env var. | Cleanest OO; `llm_messages` docstring stays accurate per class. | New class hierarchy. AgentLoop factory change. Still doesn't address non-combat (Q3). Repeats the field surface area for marginal benefit on a one-shot research cell. |

### Q2 — Prompt cache invalidation

Three positions:

| Option | Sketch | Pros | Cons |
|---|---|---|---|
| **(a) No special handling — measure as-is** | Let cache misses happen. The relay's implicit prefix cache will cover stable prefixes when present (e.g., `combat_start` still anchors the front; mid-combat the prefix `[round_1..round_{N-1}]` is stable across re-plans within one round). Log `cached_tokens` per call. | Honest baseline: "what does naive transcript-appending cost?" is exactly the question. Already-instrumented (`cache_read_input_tokens` logged in [history.jsonl](../../../runs/history.jsonl) row by row). No code changes needed. | Token cost could be high. If a single run exceeds D-B4's 5M soft cap, we burn budget without an abort path. |
| **(b) Insert explicit `cache_control: ephemeral` breakpoint at the end of the stable prefix** | When using Anthropic SDK directly, mark the boundary between "frozen history" and "this turn's new content" with `cache_control: {type: ephemeral}`. | Could reduce cost 2-5× per call on stable prefixes. | Only works on Anthropic SDK direct; current Gemini OAI-compat relay ignores the marker. Requires backend-conditional logic. **Defeats the point of measuring** — if we caching-engineer the accum cell, we're no longer testing "naive transcript-appending". |
| **(c) Hard cap at K turns / sliding window** | Drop oldest exchanges once cumulative tokens exceed a threshold (e.g., 100k). | Bounds per-call cost. | Not "accumulating context" anymore — it's a different cell (sliding-window baseline). Doesn't answer the limitation paragraph's question. |

The plan doc's "10×" estimate is a *worst-case no-cache* upper bound. A `mode-a` run uses ~70 strategic LLM calls; naive cumulative input growth $\sum_{i=1}^d i\bar s \approx d^2 \bar s / 2$ gives ~35× the per-call mean, but per-run input tokens scale only linearly with $d$ at the *call-count* level — the multiplier on **per-call** cost is what matters for rate limits and latency. Realistic with relay-level caching on stable prefixes: 3–6× per-run input-token cost, 10–20× peak per-call cost in the final third of the run. The figure-3 token-audit pipeline ([reproduce_fig_3.py](../../../scripts/reproduce/) per A.4) is positioned to measure this empirically — we should let it.

### Q3 — Non-combat "对话历史" semantics

The plan doc says "every prior `<user, assistant>` exchange in the same run accumulates into the next prompt". Three readings:

| Option | Sketch | Maps to which prior-work baseline |
|---|---|---|
| **(a) Global run-scoped transcript** | One conversation object across all strategic-tier decisions in a run (map, shop, reward, event, rest, combat plans, intermission, deckbuild). Mechanical / fast-tier decisions still don't enter — the LLM never made them, so they don't belong in the LLM's history either. | Closest counterfactual to "raw cross-decision transcript" in [architecture.tex](../../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/architecture.tex) §4.1 and ReAct/Reflexion literature ("growing log of earlier states, tool calls, and self-critiques"). |
| **(b) Per-state-type bucket** | One conversation per state type. Map decisions see prior map decisions only; combat plans see prior combat plans only; etc. | Cheaper (shorter histories). But no published baseline uses this — it's a new interface, not a comparator. |
| **(c) Sliding window of last K turns** | Drop oldest exchange when len > K. | Matches AI-Spire's 40-msg window specifically. A separate cell, not the right target for the bounded-contract attack. |

The paper's bounded-contract claim in [§4.1](../../../paper/STS2Agent__A_Bounded_Memory_Testbed_for_Long_Horizon_LLM_Agents/sections_v2/architecture.tex) is positioned against "unbounded transcript that grows because the run has been long". Option (a) is the cleanest direct counterfactual. Combat plans are part of this global stream — when a combat plan call fires, the LLM sees `[all_prior_strategic_decisions_in_run] + [combat_start + this round's state]`.

Subtle point: in option (a) the combat conversation **subsumes into** the global stream rather than living as a separate object. Each combat round's user message gets appended to the global conversation; each combat-plan assistant response is also appended. When the next non-combat decision fires (e.g., map after combat ends), it sees the full combat as part of its prefix.

Per-decision re-injection (Strategic Thread, rules, patterns) stays ON in the accum cell. This is honest: "disable only the truncation; everything else identical to mode-a". Suppressing re-injection would be a second confound. The redundancy ("transcript already contains last round's Strategic Thread; new round re-injects another copy") is part of what makes naive transcript-appending suboptimal, and the experiment should expose that.

## 4. Recommended Approach

### Q1 → **Option (a)**: `llm_messages` conditional + gated `compress_history`

Rationale:
- The truncation is a load-point conditional, not a structural property. Other ablation flags in the codebase (`STS2_PROMPT_VARIANT`, `STS2_COMBAT_CONVERSATION_ENABLED`, `STS2_STM_ENABLED`) follow exactly this pattern: one env var, conditional behavior at the consumption site, no new classes.
- The cell is a one-shot research artefact, not a new permanent code path. A subclass adds class-hierarchy surface area that has to be maintained forever for a flag that only matters during this experiment and any close follow-up.
- Wrapper (option b) doesn't help the non-combat path. Subclass (option c) does, but only by reproducing the pattern for `NonCombatConversation` — at which point the diff is bigger than (a) for the same outcome.
- Docstring concern is real but mitigated by an explicit "see paper §X — counterfactual cell" comment with link to this memo.

Specifically: at [conversation.py:343](../../../src/brain/conversation.py) add a `config.ACCUM_CONTEXT` check at the top of `llm_messages`; return `self._messages` (or a small wrapper that ensures alternation) when true. At [conversation.py:885](../../../src/brain/conversation.py) gate `self.compress_history(keep_recent=1)` on `not config.ACCUM_CONTEXT`.

### Q2 → **Option (a)**: no special handling, measure as-is, soft 5M-token warning

Rationale:
- The token cost growth is the **measurement**, not a bug. Engineering it away contaminates the comparator. The whole reason `limitations.tex` flagged this as the "cleanest follow-up" is precisely to quantify what the bounded contract is buying.
- Existing `cache_read_input_tokens` logging is sufficient. Per-call rows in `runs/history.jsonl` already let A.4's `reproduce_fig_3.py` audit token growth — the same script extended with the new condition tag produces the bounded-vs-accum overlay figure.
- D-B4's recommendation (warn at 5M tokens, don't abort) is correct: aborts skew the win-rate denominator. The cell's denominator is "10 starts at $A_0$", same as `mode-a`.

We should add one new diagnostic to the run-level postrun log: peak per-call input tokens within the run. Already covered indirectly by the per-call rows, but a single peak number simplifies cell comparison in `tab:fivecond` rows.

### Q3 → **Option (a)**: global run-scoped transcript including combat decisions

Rationale:
- Closest counterfactual to the paper's stated target — "raw cross-decision transcript" — and to the ReAct/Reflexion comparator citations.
- Worst-case for token cost, which is the **point** of measuring.
- Combat plans subsume into the global stream rather than living parallel; this matches how a human (or AI-Spire) would view the run as one continuous history.
- If empirically the global stream blows the 5M cap on the first run, option (b) is the documented fallback. We can ship `accum-context-A0` as global and follow up with `accum-context-bucketed-A0` if needed.

## 5. Implementation Task Breakdown (B.1 — ~2 days)

Sequenced for one engineer, mostly in [src/brain/](../../../src/brain/). No paper edits; no test work (B.2 is separate); no run kickoff (B.3 is separate).

### B.1.1 — Config + experiment-tag plumbing (~1h)
- Add `STS2_ACCUM_CONTEXT` env var to [config.py](../../../config.py) (or wherever `STS2_PROMPT_VARIANT` lives), default `false`, exposed as `config.ACCUM_CONTEXT: bool`.
- In [scripts/run_ablation.py](../../../scripts/run_ablation.py), register a new condition `accum-context-A0` that sets `ACCUM_CONTEXT=true` plus the mode-a flag pack (skills on, $L_4$ off, postrun off, `PROMPT_VARIANT=full`).
- In `runs/history.jsonl` row writer, add `accum_context: bool` to the `model_profile` snapshot so recompute scripts can filter cleanly.
- Validate at startup that `ACCUM_CONTEXT=true` is mutually exclusive with `STS2_COMBAT_CONVERSATION_ENABLED=false` (the latter literally discards combat state per turn — incompatible).

### B.1.2 — `RunLevelConversation` skeleton (~3h)
New class in [src/brain/conversation.py](../../../src/brain/conversation.py) (same file, alongside `CombatConversation`):
- `_messages: list[dict]` mirrors the existing pattern. Methods: `append_user(text)`, `append_assistant(content)`, `messages` property (read-only copy), `messages_mut` (for V2Engine internals if needed for query tool round-trips — match existing `CombatConversation` surface).
- No truncation, no compression. Document in module docstring: "Lives on `AgentLoop` only when `config.ACCUM_CONTEXT=true`. Persists across all strategic-tier decisions in one run."
- Enforce Anthropic alternating-role invariant via merge-on-consecutive-user (reuse `_append_user` pattern from `CombatConversation`).

### B.1.3 — AgentLoop wiring (~2h)
- In [src/agent/loop.py](../../../src/agent/loop.py), instantiate `self._accum_conversation: RunLevelConversation | None = RunLevelConversation() if config.ACCUM_CONTEXT else None` at run start; reset on `reset_run()`.
- Pass it as new optional parameter `accum_conversation: RunLevelConversation | None = None` into `V2Engine.decide_noncombat` and `V2Engine.generate_combat_plan`.

### B.1.4 — `V2Engine.decide_noncombat` accum branch (~2h)
At [v2_engine.py:474-569](../../../src/brain/v2_engine.py):
- When `accum_conversation is not None`:
  - Build `user_content` exactly as today (no change to composition — same `sections` list, same `schema_hint`).
  - **Before** the call: append the fresh `user_content` onto `accum_conversation` via `append_user`.
  - Pass `accum_conversation.messages` (the full list) as `messages=` to `_single_call`.
  - **After** the call (success only): append the assistant response (raw text or content blocks) via `append_assistant`.
- Bounded path: unchanged.

### B.1.5 — `V2Engine.generate_combat_plan` accum branch (~2h)
At [v2_engine.py:571-630](../../../src/brain/v2_engine.py):
- When `accum_conversation is not None`:
  - The latest combat round-state user message is already in `combat_conversation._messages[-1]` (or merged into it) after `add_round_state` ran.
  - Append that round-state text onto `accum_conversation` instead of consuming it via `combat_conversation.llm_messages`.
  - Pass `accum_conversation.messages` as `messages=`.
  - After call, append the assistant plan onto `accum_conversation` as well.
- Bounded path: unchanged. `combat_conversation` still exists (used for `_record_round_summary`, `_strategic_notes`, postrun trace rendering) — it just isn't the LLM-load source.

### B.1.6 — `CombatConversation.llm_messages` + compression gate (~30min)
- At [conversation.py:343-377](../../../src/brain/conversation.py): add `if config.ACCUM_CONTEXT:` short-circuit that returns the unfiltered `_messages` (still respecting alternation by filtering empty assistant blocks).
- At [conversation.py:885](../../../src/brain/conversation.py): gate `self.compress_history(keep_recent=1)` on `not config.ACCUM_CONTEXT`.
- This branch should rarely fire in B.1.5 (the accum path bypasses `llm_messages`), but the conditional handles cases where someone calls `combat_conversation.llm_messages` directly (postrun renderers).

### B.1.7 — Combat round → global stream bridging (~1h)
- Decide explicitly: does the **combat_start** block go into `accum_conversation`? Recommendation: **yes**, exactly once when `add_combat_start` runs, appended via `accum_conversation.append_user(combat_start_text)`. This gives the global stream the same self-contained combat preamble the bounded path gets.
- Verify that `add_round_state` re-injection still produces self-contained per-round text (it should — re-injection is unaware of accum mode).

### B.1.8 — Cache + token logging diagnostics (~1h)
- In [v2_engine.py:_single_call](../../../src/brain/v2_engine.py), add a `WARNING` log when an individual call's input tokens exceed a config-driven threshold (default 1M). Don't abort.
- In the run summary writer, capture `peak_input_tokens_single_call` per run.

### B.1.9 — Smoke test (~1h, not B.2's full unit test)
Run `python -m scripts.run_agent --steps 80 --character Silent --no-postrun` with `STS2_ACCUM_CONTEXT=true` against a fixed seed. Verify:
- `accum_conversation._messages` grows monotonically; len matches strategic-call count × 2.
- No Anthropic alternation errors.
- `cached_tokens` reported on later calls.
- A second run with `STS2_ACCUM_CONTEXT=false` produces a `runs/history.jsonl` row identical in shape to existing `mode-a` rows, confirming the flag is opt-in.

### B.1.10 — Doc update (~30min)
- One paragraph in [docs/reference/MEMORY_SYSTEM.md](../../reference/MEMORY_SYSTEM.md) under "per-decision stateless context composition" — note `STS2_ACCUM_CONTEXT` as the documented escape hatch with pointer to this memo.
- One row in [docs/reference/ABLATION.md](../../reference/ABLATION.md) ablation matrix table — new cell `accum-context-A0`, what's flipped.

**Total: ~14h ≈ 2 days of focused work.** B.2 (unit tests), B.3 (pilot $N{=}2$), B.4 (full $N{=}10$), and B.5 (analysis row in `tab:fivecond`) follow per [post_submission_plan.md](../../../paper/post_submission_plan.md) §B.

## 6. Open Questions Surfaced

These are NOT blockers for B.1 coding but should be answered before B.3 pilot:

- **OQ-1**: Does `STS2_ACCUM_CONTEXT=true` interact safely with the existing `_v2_combat_conversation` save/quit replay path (Strategic Thread snapshotting on reload)? Best handled empirically during pilot.
- **OQ-2**: Should `accum_conversation` be persisted across save/quit replays the same way `_strategic_notes` is? Recommendation: yes, snapshot + restore — otherwise replays produce a discontinuous history. Implement only if pilot encounters save/quit during the cell.
- **OQ-3**: Postrun extraction and Mode B fill use their own LLM calls outside `V2Engine.decide_noncombat`. They should NOT contaminate the gameplay accum stream. Verify in B.1.4 that those paths take `accum_conversation=None`.

## 7. Anti-Patterns

- ❌ Adding `cache_control: ephemeral` markers in the accum cell to "fix" token cost. The cost is the measurement. (Engineering it away contaminates the comparator and gives the bounded contract an unfair efficiency win.)
- ❌ Suppressing per-round re-injection (Strategic Thread / rules / patterns) in accum mode. This would be a second variable on top of the truncation flip; the matched comparator wants "disable only truncation".
- ❌ Bucketing per state type unless global mode demonstrably exceeds the 5M soft cap on every pilot run.
- ❌ Modifying `mode-a` runs to compare against the new cell — `mode-a` is frozen at SHA `1888a62` and is the published baseline.
- ❌ Treating `accum-context-A0` as a permanent code path. The flag exists for one cell. If the experiment lands, the flag stays as a documented escape hatch; if it gets superseded, the flag is removable.
