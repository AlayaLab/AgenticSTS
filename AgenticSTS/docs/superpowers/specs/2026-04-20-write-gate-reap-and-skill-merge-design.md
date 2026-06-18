# Write-Gate Judge Post-Flush Reap + Skill Merge with AB Validation — Design

**Date:** 2026-04-20
**Branch:** feature/act-boss-aware-reward-shop
**Status:** Design complete, awaiting implementation plan

## Problem

Two related TODOs currently leave the write-gate pipeline half-finished:

1. **Write-gate judge post-flush reap.** `WriteGate.filter_skill_batch` treats `defer_to_judge` as a persist-action. Deferred candidates land in `skills.json` *before* the batch LLM judge runs, and the judge's subsequent `REJECT` / `MERGE` verdicts (written to `data/evolution/judge_log.jsonl`) are never applied. Verdicts are observation-only.
2. **Skill-merge support.** Even when the judge returns `MERGE(target_id)`, no merge actually happens. `SkillLibrary` lacks a `merge_skills` operation, so the candidate is silently kept next to the target instead of being consolidated.

The consequence is a skill library that accumulates near-duplicates the gate *correctly identifies as such* but does not act on.

## Scope

**In scope:**
- Hold-and-flush architecture for `defer_to_judge` skills: persist only after the judge has returned a verdict.
- Skill-merge pipeline driven by `MERGE(target_id)` judgements: LLM-driven merge of `candidate` into `target` producing a new skill, validated by a behavioural A/B test on original gameplay prompts.
- Anchor persistence on the `Skill` model so future merges have structured evidence of "the situation this skill was discovered for".
- Log-scan fallback to recover anchors for existing skills that predate the new field.

**Out of scope (deferred to follow-up specs):**
- Merge for `verdict=contradiction, resolution=merge` **conflict pairs** (both entries already in the library — asymmetric, needs separate treatment).
- Hold-and-flush for `guide` / `rule` / `card_note` candidates — these do not currently flow through `filter_*_batch` enforcement at all.
- A/B validation for `single-card` combat anchors (requires live game-state simulation).
- Merge of non-combat candidates (no `cards_played` ground truth; downgraded to `REJECT`).
- Automatic backfill of anchors for all existing skills.

## Key Design Decisions

Captured here to preserve the decision record after brainstorming:

| Question | Choice | Rationale |
|---|---|---|
| Hold-and-flush vs reap-after-persist | **Hold-and-flush (B)** | `skills.json` is always in a judged state; avoids transient garbage on postrun crash |
| MERGE handling | **Full merge pipeline with AB validation** | Solve the companion TODO in one pass rather than dropping MERGE as REJECT |
| Anchor retrieval | **Persist `anchor_exemplars` + log-scan fallback** | Clean data flow for new skills; degradation path for existing library |
| `anchor_exemplars` size | **top-2 positive exemplars** | Enough for AB coverage (N=3 attempts per anchor × 2 anchors = 6 total) |
| Log-scan needle | **First 120 chars of `skill.content`, whitespace-normalised substring match** | Short enough to tolerate re-phrasing, long enough to avoid boilerplate collisions |
| Anchor persistence unit | **`AnchorHit` computed on demand, not persisted** | Merge is rare (0–5/postrun); log-scan cost acceptable |
| AB match criterion | **Full-sequence `cards_played` equality (prefix match allowed)** | "宁缺毋滥" — partial matches let broken merges through |
| AB attempts | **N=3 per anchor at `temperature=0.7`** | N=1 at `temp=0` has no AB meaning; T=0.7 produces a real distribution |
| AB pass threshold | **≥4/6 perfect hits** | Absolute count, not rate — empty slots count as miss |
| Judge batch failure | **Strict: drop all pending (fallback=b)** | Consistent with 宁缺毋滥; duplicates will be re-filtered next run |
| Merge LLM input | **Structured anchor summary only, not full prompt** | 4 full prompts = 30k+ tokens; concept-merge doesn't need them |
| Merge LLM escape hatch | **Allow `decision=abandon`** | Cheaper for the LLM to declare irreconcilable than force AB failure |
| `merged_trigger_tags` | **Produced by LLM, not forced union** | LLM can drop irrelevant tags when merging |
| Single-card anchor AB | **Downgrade merge → REJECT** | Would require game-state simulation |
| Non-combat candidate merge | **Downgrade merge → REJECT** | No `cards_played` ground truth |
| Pipeline scope | **Skills-only, with kind-agnostic names** | YAGNI — guides/rules/card_notes don't go through the gate yet |

## High-Level Flow

```
postrun:
  1. memory extract
  2. rule distill
  3. guide consolidation
  4. skill discovery
     ├─ combat_discovery → filter_skill_batch → (kept → add_batch + save)
     │                                          (held → pending buffer, NO save)
     └─ noncombat_discovery → 同上
  5. write_gate.flush_judge_round
     ├─ batch LLM judges pending + conflict_pairs
     ├─ parse verdicts → ResolvedJudgements
     │   ├─ to_release  (ADD/UPDATE)  → skill_library.add_batch
     │   ├─ to_drop     (REJECT)      → merge_log entry
     │   └─ to_merge    (MERGE)       → parallel merge_pipeline
     │       └─ per pair: merge LLM → AB harness → pass=replace / fail=drop
     ├─ on any changes → skill_library.save (second and final)
     └─ on judge error → drop-all pending (strict fallback)
  6. self-evolution (reads post-flush skill_library state)
```

**Invariants preserved:**
- `skills.json` at any persisted state contains only judged entries.
- `defer_to_judge` candidates never touch disk until verdict returns.
- Any downstream failure (judge, merge LLM, AB) defaults to the conservative option (drop candidate, keep target).

## Data Model Changes

### `Skill.anchor_exemplars` (new field)

```python
# src/skills/models.py
@dataclass(frozen=True)
class Skill:
    ...
    anchor_exemplars: tuple[RoundExemplar, ...] = ()
    # Representative positive examples backing this skill, used by merge AB.
    # Set at discovery time from SkillEvidenceCard.positive_examples[:2].
    # Empty for seed skills and for discovered skills that predate this field.
```

`Skill.to_dict` / `from_dict` handle the new field; `data_schema_version` bumps from **2 → 3**. Old files read `anchor_exemplars = ()` (graceful default, no migration script).

### Discovery wiring

In `loop.py` at current line ~3589 and ~4064:

```python
new_skills, evidence_cards = await discover_skills(...)
new_skills = _attach_anchors(new_skills, evidence_cards)  # NEW
# rest of filter_skill_batch pipeline unchanged
```

`_attach_anchors` zips `evidence_cards` with `new_skills` by `candidate_name`, writes `card.positive_examples[:2]` to each skill's `anchor_exemplars`. If a candidate has fewer than 2 positive examples, attach whatever is available (0 or 1 is allowed; merge AB simply has a lower anchor budget for that skill).

### `AnchorHit` (new type, transient)

```python
# src/memory/anchor_resolver.py
@dataclass(frozen=True)
class AnchorHit:
    exemplar: RoundExemplar       # structured metadata
    prompt_messages: list[dict]   # full messages from log_llm_call
    decision_output: dict         # extracted from log_decision (card_name / plan / etc)
    tier: str                     # "fast" | "strategic" | "analysis" — reconstructed from system prompt
    source: str                   # "persisted" | "log_scan"
```

Not persisted. Produced by `resolve_anchors_for_skill(skill, max=2)`:

1. If `skill.anchor_exemplars` non-empty → for each exemplar, scan `logs/run_<exemplar.run_id>.jsonl` for the `log_llm_call` entry at `step ≈ exemplar.round_num` and the `log_decision` entry at the same step. Build `AnchorHit` with `source="persisted"`.
2. Else (empty anchors) → scan `logs/run_<rid>.jsonl` for each `rid in skill.source_run_ids`, substring-match `skill.content[:120]` (whitespace-normalised) against the user message in each `log_llm_call`. Pair with the decision output at the same step. Build `AnchorHit` with `source="log_scan"`. Stop at 2 hits.
3. Else → return `[]`. The merge is downgraded to REJECT.

## Pending Buffer

### Placement

Field on `WriteGate`:

```python
class WriteGate:
    def __init__(self, ...):
        ...
        self._pending_skills: dict[str, PendingSkillCandidate] = {}

@dataclass
class PendingSkillCandidate:
    skill: Skill
    request_id: str           # matches JudgeQueue cand_XXXX
    target_hint: str | None   # WriteGate's top-neighbor id (informational)
    run_id: str
```

### Interface change

`_PERSIST_ACTIONS` shrinks:

```python
_PERSIST_ACTIONS: frozenset[str] = frozenset({"accept", "update"})
# defer_to_judge handled internally in filter_skill_batch
```

`filter_skill_batch` signature changes:

```python
def filter_skill_batch(
    self, new_skills, existing_skills, *, run_id=""
) -> tuple[
    list[Skill],                           # kept — caller persists immediately
    list[tuple[Skill, GateDecision]],      # dropped — rejected/merged, log only
    list[tuple[Skill, GateDecision]],      # held  — deferred, WriteGate retains
]:
    ...
    for new in new_skills:
        decision = self.check_and_log(cand, existing_entries)
        if decision.action in {"accept", "update"}:
            kept.append(new)
        elif decision.action == "defer_to_judge":
            self._pending_skills[req_id] = PendingSkillCandidate(...)
            held.append((new, decision))
        else:
            dropped.append((new, decision))
    return kept, dropped, held
```

### Caller (`loop.py`)

```python
new_skills, dropped, held = self._write_gate.filter_skill_batch(...)
if held:
    logger.info("write_gate held %d skills for judge", len(held))
# kept → add_batch + save (unchanged)
# held → WriteGate's internal state; released later by flush_judge_round
```

### Lifecycle

- In-memory only, process-lifetime = postrun. Cleared at end of `flush_judge_round` regardless of outcome.
- Ctrl+C mid-postrun → buffer lost; candidates re-discovered next run.

## Merge LLM Call

### Triggering

For each `(candidate, target_id)` in `ResolvedJudgements.to_merge`, start one async task. All tasks `asyncio.gather`-ed with `return_exceptions=True`.

### Model

`analysis` tier (Gemini 3.1 Pro, `thinking=high`) via `_get_v2_tier("analysis")`. Consistent with skill discovery, which is the closest cousin task.

### Prompt

**System (static, cacheable):**

```
你是技能库合并员。你会收到两条在 trigger 上高度重合、但内容可能互补或矛盾的技能，
以及每条技能在真实对局中生效的"代表性情形"。你的任务是产出一条合并后的技能，
使其对两种情形都能推导出正确的决策。

硬性要求：
- 输出单一 JSON 对象，无任何额外文本、无 markdown 代码围栏
- 合并后的 content 必须同时覆盖情形A和情形B（包含足够的条件分支或通用规则）
- 保持 trigger 最小化：不超过两条 skill 的 trigger 并集
- content 控制在 400 字符以内
- 如果判断两条技能无法合理合并（本质矛盾），返回 "decision": "abandon" + 原因

输出 schema:
{
  "decision": "merged" | "abandon",
  "merged_content": "...",
  "merged_trigger_tags": ["state_types:combat", ...],
  "merged_category": "combat" | "deck_building" | ...,
  "merged_priority": 50,
  "rationale": "...",
  "abandon_reason": ""
}
```

**User (per call):**

```
### Skill A (existing, id=<target_id>)
category: <target.category>
trigger: [<target.trigger tags>]
content: <target.content>

情形A（代表性正例 anchor #1）:
- enemy: <anchor_A.enemy_key>, round <anchor_A.round_num>, threat=<threat_level>
- 当时打出的牌序列: <anchor_A.cards_played>
- 对局结果: hp_lost=<N>, outcome_quality=<q>

### Skill B (candidate, name=<candidate.name>)
category: <candidate.category>
trigger: [<candidate.trigger tags>]
content: <candidate.content>

情形B（代表性正例 anchor #1）:
- ...

产出合并后的 skill。
```

Only `anchor[0]` used in the merge prompt (structured summary). Full `anchor.prompt_messages` is reserved for the AB harness.

### Failure handling

- JSON decode fail / missing field / `decision=abandon` → merge dropped, target untouched, candidate dropped. `merge_log.jsonl.outcome = "dropped_merge_abandon"` (or `"dropped_exception"`).

## AB Harness

### Scope gate

Before starting AB, check both anchors:

1. `resolve_anchors_for_skill(target)` returns `[]` → `outcome = "dropped_anchor_failed"`, merge dropped.
2. `resolve_anchors_for_skill(candidate)` returns `[]` → same.
3. Any anchor's `state_type` is non-combat → `outcome = "dropped_non_combat"`, merge dropped.
4. Any anchor's `decision_output` shows the tool used was `play_card` (single-card mode), not `execute_combat_plan` → `outcome = "dropped_single_card"`, merge dropped. Detection reads the `tool_use` block in the logged assistant message (see `session_logger.log_llm_call`'s structured content extraction).

### Prompt rebuild

```python
def build_replay_prompt(
    anchor: AnchorHit,
    original_skill: Skill,
    merged_skill: Skill,
) -> list[dict]:
    """
    Deep-copy anchor.prompt_messages; in the user message, locate the
    `### {original_skill.name}` marker inside the `## Strategy Skills` block
    and replace that entire subsection with:
        ### {merged_skill.name}\n{merged_skill.content}
    Other skills in the block remain untouched.

    Fallback: if the `### {name}` anchor is missing (skill content was
    re-phrased between discovery and merge), do a substring-match on the
    first 120 chars of original_skill.content (whitespace-normalised),
    replacing from the match start to the next `###` or section end.

    Hard fail: if neither anchor strategy succeeds, return None.
    """
```

Hard-fail on a single anchor → that anchor's 3 attempts all count as miss (denominator stays at 6).

### Replay call

```python
async def replay_once(
    anchor: AnchorHit, prompt: list[dict]
) -> ABResult:
    client = v2_backend_for_tier(anchor.tier)
    response = await client.chat_completions(
        messages=prompt,
        temperature=0.7,
        max_tokens=<tier default>,
    )
    replay_cards = extract_cards_played(response, anchor.tier)
    # For plan-tier: extract plan.cards
    # For single-card: extract card_name (but we never get here; pre-filtered)
    match = (replay_cards[:len(anchor.expected_cards)]
             == anchor.expected_cards)
    return ABResult(anchor_id=..., attempt_idx=..., replay_cards=replay_cards,
                    expected_cards=anchor.expected_cards, match=match, error=None)
```

Timeout / API error → `ABResult(match=False, error=str(e))`. No retry.

### Scoring

```python
results = await asyncio.gather(*[
    replay_once(a, p) for a in (anchor_A, anchor_B)
    for _ in range(STS2_MERGE_AB_N_PER_ANCHOR)  # default 3
], return_exceptions=True)
# Exceptions → match=False

hits = sum(1 for r in results if isinstance(r, ABResult) and r.match)
threshold = STS2_MERGE_AB_THRESHOLD  # default 4
passed = hits >= threshold

if passed:
    skill_library.replace(target_id, merged_skill)
    outcome = "replaced"
else:
    outcome = "dropped_ab_fail"
```

`skill_library.replace(old_id, new_skill)` — new method on `SkillLibrary`. Semantically it performs, in a single lock:
- Find old skill by `old_id`.
- Set `old.active=False`, `old.status="deactivated"`, `old.superseded_by=new_skill.skill_id`, append to the library's deactivated set (retained for audit, skipped by the retriever).
- `new_skill.source = "merged"`, `new_skill.source_run_ids = old.source_run_ids + candidate.source_run_ids` (de-duplicated), `new_skill.anchor_exemplars = (old.anchor_exemplars[0:1] + candidate.anchor_exemplars[0:1])[:2]` (so next-merge has fresh anchors), `new_skill.version = 1` (fresh), `new_skill.confidence = 0.7` (neutral seed).
- Add new skill to active set.

The old skill is not physically deleted — `merge_log.jsonl` plus `old.superseded_by` give a full audit trail.

### Parallelism

- Each pair: 6 replay calls in parallel (`asyncio.gather`).
- Multiple pairs: outer `asyncio.gather` across all `to_merge` pairs.
- Failure of one pair does not abort others.

## Postrun Ordering

Current order remains 1–6. Only step 5 gains behaviour:

```
5. write_gate.flush_judge_round:
   a. batch LLM judge → raw verdicts
   b. parse → ResolvedJudgements
   c. asyncio.gather over to_merge → merge_pipeline per pair
   d. collect releases (ADD/UPDATE + merge-passes)
   e. skill_library.add_batch(releases) + skill_library.save() if changes
   f. log merge_log.jsonl + judge_log.jsonl
   g. clear pending buffer
```

**Failure paths:**
- Judge batch error → goto (g), clear pending, skip (c)–(e). Merge_log not written. `judge_log.jsonl` records `fallback_triggered=true` so operators can detect the event.
- Individual merge pair exception → pair marked `dropped_exception`; others proceed.
- `skill_library.save()` OS error (disk full, permission) → logged warning, but pending buffer is still cleared. Risk: accept/update from step 4 persisted in the first save are on disk; merge releases from step 5 are in memory only and lost. Next postrun will re-propose and re-judge. This is the same failure mode as today's `save()` losses and does not worsen.

**Evolution step (6)** reads post-flush library, unaffected by pending buffer state.

## Observability

### `write_gate_log.jsonl` (unchanged)
Same fields. `action=defer_to_judge` semantics shift: it now means "held", not "persisted-inline".

### `judge_log.jsonl` (additions)
```jsonc
{
  ...existing fields,
  "pending_before_flush": 12,
  "resolved": {"release": 4, "drop": 5, "merge_attempted": 3},
  "fallback_triggered": false
}
```

### `merge_log.jsonl` (new)

One line per merge pair, regardless of outcome:

```jsonc
{
  "ts": 1713578400.123,
  "round_id": "postrun_<run_id>",
  "pair": {
    "target_id": "skill_a1b2c3",
    "candidate_name": "prioritize_weak_kin_priest",
    "candidate_run_id": "20260420_143210"
  },
  "anchor_resolution": {
    "target_source": "persisted" | "log_scan" | "failed",
    "candidate_source": "persisted" | "log_scan" | "failed",
    "target_anchors_found": 2,
    "candidate_anchors_found": 2
  },
  "merge_llm": {
    "decision": "merged" | "abandon",
    "abandon_reason": "",
    "merged_content_preview": "<first 120 chars>...",
    "merged_trigger_tag_count": 5,
    "latency_ms": 3421,
    "error": ""
  },
  "ab": {
    "attempted": true,
    "attempts": [
      {"anchor_id": "A#1", "attempt": 0, "match": true,
       "expected_cards": [...], "replay_cards": [...]},
      ...
    ],
    "hits": 4,
    "threshold": 4,
    "passed": true
  },
  "outcome": "replaced" | "dropped_ab_fail" | "dropped_merge_abandon"
           | "dropped_anchor_failed" | "dropped_single_card"
           | "dropped_non_combat" | "dropped_exception",
  "error": ""
}
```

### Runtime INFO

```
write_gate.flush: held=12 release=4 drop=5 merge=3
merge_pipeline: 3 pairs → 1 replaced, 2 dropped (ab_fail=1 abandon=1)
```

## Environment Variables

```bash
STS2_WRITE_GATE_REAP_ENABLED=false  # Master switch, default OFF initially.
                                     # true: hold-and-flush + merge-with-AB active.
                                     # false: existing inline-persist behaviour (observation mode).

STS2_MERGE_AB_THRESHOLD=4            # Min perfect hits out of 6 to pass AB.
STS2_MERGE_AB_N_PER_ANCHOR=3         # Replays per anchor (total = 2 × this).
STS2_MERGE_ANCHOR_NEEDLE_LEN=120     # Log-scan substring length.
```

The master switch lets us deploy the code, observe `merge_log.jsonl` on a small number of real runs, then flip default to `true` once stable. Default on PR land: `false`.

## Backwards Compatibility

- `Skill` schema: new optional field, old files load with `anchor_exemplars=()`. `data_schema_version: 2 → 3` (informational; no migration required).
- `filter_skill_batch` signature change: 2-tuple → 3-tuple. Breaking for any direct caller; currently only `loop.py` calls it (two sites, both updated in the same commit).
- `flush_judge_round` return type expands (`ResolvedJudgements`). Currently only `loop.py` calls it.
- No `data.snapshots/` needed — this is schema evolution of code, not of game content.

## Testing Strategy

### Unit
- `anchor_resolver`: three paths (persisted / log_scan / failed), each with fixtures.
- `PendingBuffer`: `release(request_id)`, `drop(request_id)`, clear semantics.
- `replay_prompt_builder`: primary anchor `### {name}` match + fallback substring match + hard-fail path.
- AB scoring: match computation across edge cases (exact, prefix, mismatch, empty replay, exception).
- `merge_llm_output_parser`: JSON decode + schema validation + `abandon` path.
- `SkillLibrary.replace(old_id, new_skill)`: atomic swap with `superseded_by` audit trail.

### Integration
- End-to-end `flush_judge_round` with 3 MERGE verdicts, mocked judge + mocked gameplay LLM producing canned replay outputs.
- Fallback: judge returns `error != ""` → pending cleared, library unchanged.
- AB fail: mocked gameplay LLM returns wrong card sequence → `merge_log` shows `dropped_ab_fail`, target unchanged.
- Anchor resolution failure: skill with empty `anchor_exemplars` and no matching log → `dropped_anchor_failed`.

### Live
- No automated live test. One manual postrun with `STS2_WRITE_GATE_REAP_ENABLED=true`, observe `merge_log.jsonl`. Success criteria: at least one `outcome=replaced` and one non-replaced outcome recorded without harness crashes.

## Regression Risks

- **Existing-skill cold start.** Current library has zero `anchor_exemplars`. For the first few postruns after deploy, MERGE verdicts will almost always fail anchor resolution → dropped as REJECT. Mitigation: this matches `STS2_WRITE_GATE_REAP_ENABLED=false` default behaviour; when we flip to `true`, we accept some knowledge attrition in exchange for library cleanliness. Discovery re-proposes strong candidates later.
- **Log-scan miss rate.** If `skill.content` is re-phrased after discovery, needle substring match fails. Mitigation: needle length configurable via `STS2_MERGE_ANCHOR_NEEDLE_LEN`; if production data shows <30% hit rate in `merge_log.jsonl`'s `anchor_resolution.*_source` field, add a one-time anchor-backfill script as follow-up.
- **Gameplay LLM at temp=0.7 is non-deterministic.** A merged skill may pass AB one run and fail the next. Mitigation: the ≥4/6 threshold tolerates one miss per anchor; if variance is higher in practice, raise N to 5 per anchor.

## Follow-Up TODOs (not in this spec)

- Conflict-pair merge (both entries already in library).
- Anchor backfill script for pre-existing skills.
- Guide / rule / card_note hold-and-flush.
- Single-card anchor AB via game-state simulation.
- Post-flush judge result audit dashboard (aggregate merge success rates, abandon rates, AB variance).
