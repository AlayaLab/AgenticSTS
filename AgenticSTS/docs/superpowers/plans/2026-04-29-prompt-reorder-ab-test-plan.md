# B1 Prompt Reorder A/B Test — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a self-contained A/B harness that samples real `card_reward` LLM calls from `logs/run_*.jsonl`, generates a B1 variant by relocating the `## Available Cards` section to the tail of the prompt, resamples both versions against the original gameplay model, blind-judges disagreements with a stronger model, and reports pass/fail against the criteria in [docs/superpowers/specs/2026-04-29-prompt-reorder-ab-test-design.md](../specs/2026-04-29-prompt-reorder-ab-test-design.md).

**Architecture:** Pure-offline harness. Uses `src/brain/llm_caller.call_raw` for resampling (no agent loop, no game). Pure-text regex transform for the B1 variant. Judge calls a stronger model with a fixed rubric on blind A/B pairs. All output goes to a single timestamped JSON + Markdown report under `data/reports/prompt_ab/`.

**Tech Stack:** Python 3.14, asyncio, pytest, existing `src/brain/llm_caller.py` for LLM calls, existing `logs/run_*.jsonl` as data source.

---

## File Structure

**Created (new):**
- `scripts/prompt_ab_test.py` — main CLI entry point
- `scripts/_prompt_ab/__init__.py`
- `scripts/_prompt_ab/sampler.py` — load JSONL, filter card_reward calls, stratify by act
- `scripts/_prompt_ab/transform.py` — `apply_b1(user_message)` regex relocator
- `scripts/_prompt_ab/runner.py` — async fan-out: per (call, version), 3 resamples via `call_raw`
- `scripts/_prompt_ab/judge.py` — blind L2 judge with fixed rubric
- `scripts/_prompt_ab/report.py` — aggregate metrics + Markdown report writer
- `tests/scripts/__init__.py`
- `tests/scripts/test_prompt_ab_transform.py` — unit tests for `apply_b1`
- `tests/scripts/test_prompt_ab_sampler.py` — unit tests for sampler

**Modified (gated on harness pass):**
- `src/brain/prompts/reward.py` — single block relocation in `build_card_reward_prompt`

---

## Task 1: Sampler — load JSONL and filter card_reward calls

**Files:**
- Create: `scripts/_prompt_ab/__init__.py`
- Create: `scripts/_prompt_ab/sampler.py`
- Create: `tests/scripts/__init__.py`
- Create: `tests/scripts/test_prompt_ab_sampler.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_prompt_ab_sampler.py`:

```python
"""Unit tests for prompt_ab sampler."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts._prompt_ab.sampler import CardRewardSample, iter_card_reward_calls


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_iter_card_reward_calls_filters_by_header(tmp_path: Path) -> None:
    log = tmp_path / "run_test.jsonl"
    records = [
        {"event": "llm_call", "call_type": "v2_single_call", "system_prompt": "sys", "prompt": "## Card Reward\n## Available Cards\n", "response": "<decision>{\"option_index\":0}</decision>", "model": "gemini-2.5-pro", "run_id": "r1"},
        {"event": "llm_call", "call_type": "v2_single_call", "system_prompt": "sys", "prompt": "## Map Navigation\n", "response": "x", "model": "gemini-2.5-pro", "run_id": "r1"},
        {"event": "transition", "run_id": "r1"},
    ]
    _write_jsonl(log, records)

    samples = list(iter_card_reward_calls([log]))

    assert len(samples) == 1
    assert isinstance(samples[0], CardRewardSample)
    assert samples[0].run_id == "r1"
    assert samples[0].model == "gemini-2.5-pro"
    assert "## Card Reward" in samples[0].user_message
    assert "## Available Cards" in samples[0].user_message


def test_iter_card_reward_calls_skips_short_prompts(tmp_path: Path) -> None:
    log = tmp_path / "run_test.jsonl"
    short_prompt = "## Card Reward\n## Available Cards\nx"
    records = [
        {"event": "llm_call", "call_type": "v2_single_call", "system_prompt": "sys", "prompt": short_prompt, "response": "x", "model": "g", "run_id": "r1"},
    ]
    _write_jsonl(log, records)

    samples = list(iter_card_reward_calls([log], min_prompt_len=5000))

    assert samples == []


def test_iter_card_reward_calls_requires_both_headers(tmp_path: Path) -> None:
    log = tmp_path / "run_test.jsonl"
    records = [
        # Has Card Reward header but no Available Cards (e.g. potion-only state)
        {"event": "llm_call", "call_type": "v2_single_call", "system_prompt": "sys", "prompt": "## Card Reward\nx" * 3000, "response": "x", "model": "g", "run_id": "r1"},
    ]
    _write_jsonl(log, records)

    samples = list(iter_card_reward_calls([log], min_prompt_len=0))

    assert samples == []
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_prompt_ab_sampler.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'scripts._prompt_ab.sampler'`

- [ ] **Step 3: Create the package init**

Create `scripts/_prompt_ab/__init__.py`:

```python
"""A/B test harness for prompt-reorder experiments."""
```

Create `tests/scripts/__init__.py` (empty file is fine):

```python
```

- [ ] **Step 4: Implement the sampler**

Create `scripts/_prompt_ab/sampler.py`:

```python
"""Load JSONL run logs and yield card_reward llm_call samples."""
from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class CardRewardSample:
    """One card_reward llm_call extracted from a run JSONL log."""
    run_id: str
    log_path: str
    line_index: int
    system_prompt: str
    user_message: str
    original_response: str
    model: str


def iter_card_reward_calls(
    paths: Iterable[Path],
    *,
    min_prompt_len: int = 5000,
) -> Iterator[CardRewardSample]:
    """Yield CardRewardSample for every llm_call that asks the model to pick a card.

    A call qualifies if it is an `llm_call` event with `call_type == 'v2_single_call'`
    AND its user message contains both `## Card Reward` and `## Available Cards`
    headers. Empty-prompt or trivially short calls are filtered out via
    `min_prompt_len` (default 5000 chars filters smoke-test logs).
    """
    for path in paths:
        try:
            with path.open(encoding="utf-8") as f:
                for line_index, line in enumerate(f):
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        rec = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if rec.get("event") != "llm_call":
                        continue
                    if rec.get("call_type") != "v2_single_call":
                        continue
                    user_msg = rec.get("prompt") or ""
                    if "## Card Reward" not in user_msg:
                        continue
                    if "## Available Cards" not in user_msg:
                        continue
                    if len(user_msg) < min_prompt_len:
                        continue
                    yield CardRewardSample(
                        run_id=str(rec.get("run_id") or ""),
                        log_path=str(path),
                        line_index=line_index,
                        system_prompt=str(rec.get("system_prompt") or ""),
                        user_message=user_msg,
                        original_response=str(rec.get("response") or ""),
                        model=str(rec.get("model") or ""),
                    )
        except (OSError, UnicodeDecodeError):
            continue
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_prompt_ab_sampler.py -v`
Expected: 3 PASSED

- [ ] **Step 6: Commit**

```bash
git add scripts/_prompt_ab/__init__.py scripts/_prompt_ab/sampler.py tests/scripts/__init__.py tests/scripts/test_prompt_ab_sampler.py
git commit -m "feat(prompt_ab): add sampler for card_reward llm_calls"
```

---

## Task 2: Transform — apply B1 reorder

**Files:**
- Create: `scripts/_prompt_ab/transform.py`
- Create: `tests/scripts/test_prompt_ab_transform.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_prompt_ab_transform.py`:

```python
"""Unit tests for B1 prompt transform."""
from __future__ import annotations

import pytest

from scripts._prompt_ab.transform import B1TransformError, apply_b1


def test_apply_b1_relocates_available_cards_before_eval() -> None:
    src = "\n".join([
        "## Card Reward",
        "HP: 50/75",
        "",
        "## Available Cards",
        "- [index=0] Strike",
        "- [index=1] Defend",
        "",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "",
        "## Evaluation — Boss Damage Check",
        "Estimate DPS...",
        "",
        "## Decision Format (card_reward_action)",
        "Valid actions: choose_reward_card",
    ])

    out = apply_b1(src)

    # Available Cards must now precede Evaluation
    avail_pos = out.index("## Available Cards")
    eval_pos = out.index("## Evaluation — Boss Damage Check")
    assert avail_pos < eval_pos
    # Keyword Glossary must precede Available Cards (dictionary-before-use)
    glossary_pos = out.index("## Keyword Glossary")
    assert glossary_pos < avail_pos
    # All original content must still be present
    assert "- [index=0] Strike" in out
    assert "- [index=1] Defend" in out
    assert "HP: 50/75" in out
    # No content duplicated
    assert out.count("## Available Cards") == 1


def test_apply_b1_idempotent_when_already_at_tail() -> None:
    """If Available Cards already directly precedes Evaluation, leave as-is."""
    src = "\n".join([
        "## Card Reward",
        "HP: 50/75",
        "",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "",
        "## Available Cards",
        "- [index=0] Strike",
        "",
        "## Evaluation — Boss Damage Check",
        "Estimate DPS...",
    ])

    out = apply_b1(src)

    assert out == src


def test_apply_b1_raises_when_section_missing() -> None:
    src = "## Card Reward\nHP: 50/75\n## Evaluation — Boss Damage Check\n"

    with pytest.raises(B1TransformError):
        apply_b1(src)


def test_apply_b1_preserves_content_outside_moved_block() -> None:
    src = "\n".join([
        "## Expert Knowledge (retrieved skills)",
        "Some skill text spanning",
        "multiple lines.",
        "",
        "## Card Reward",
        "HP: 50/75",
        "## Current Deck (12 cards)",
        "- Strike x5",
        "## Relics: A, B, C",
        "## Available Cards",
        "- [index=0] Strike",
        "## Keyword Glossary",
        "- Block: temporary HP",
        "## Evaluation — Boss Damage Check",
        "Eval text",
        "## Decision Format (card_reward_action)",
        "Schema",
    ])

    out = apply_b1(src)

    # Header order check
    expected_order = [
        "## Expert Knowledge",
        "## Card Reward",
        "## Current Deck",
        "## Relics:",
        "## Keyword Glossary",
        "## Available Cards",
        "## Evaluation — Boss Damage Check",
        "## Decision Format",
    ]
    positions = [out.index(h) for h in expected_order]
    assert positions == sorted(positions), f"Header order broken: {positions}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_prompt_ab_transform.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement the transform**

Create `scripts/_prompt_ab/transform.py`:

```python
"""B1 transform: relocate `## Available Cards` to the tail (before Evaluation)."""
from __future__ import annotations

import re


class B1TransformError(ValueError):
    """Raised when the transform cannot find both required anchors."""


_AVAILABLE_HEADER = "## Available Cards"
_EVAL_HEADER = "## Evaluation — Boss Damage Check"


def _find_section_span(text: str, header: str) -> tuple[int, int]:
    """Return (start, end) byte offsets of the section starting at ``header``.

    The section ends just before the next top-level `## ` header or at EOF.
    The end offset is exclusive and includes the trailing blank line if present.
    """
    start = text.find(header)
    if start == -1:
        raise B1TransformError(f"section header not found: {header!r}")
    # Find next ## header after this one
    next_match = re.search(r"\n##\s", text[start + len(header):])
    if next_match is None:
        end = len(text)
    else:
        end = start + len(header) + next_match.start() + 1  # keep the trailing newline
    return start, end


def apply_b1(user_message: str) -> str:
    """Move the ``## Available Cards`` block to immediately before
    ``## Evaluation — Boss Damage Check``.

    Idempotent: if the block is already directly above the eval block, returns
    the input unchanged. Raises B1TransformError if either anchor is missing.
    """
    avail_start, avail_end = _find_section_span(user_message, _AVAILABLE_HEADER)
    eval_start = user_message.find(_EVAL_HEADER)
    if eval_start == -1:
        raise B1TransformError(f"section header not found: {_EVAL_HEADER!r}")

    # Already adjacent? (Available block ends exactly at eval block start, or
    # only whitespace between them.)
    between = user_message[avail_end:eval_start]
    if between.strip() == "":
        return user_message

    if avail_start > eval_start:
        # Already past eval — leave alone (unexpected layout, do no harm)
        return user_message

    avail_block = user_message[avail_start:avail_end]
    # Trim trailing whitespace from the moved block; we will re-add a single
    # blank line separator on insertion.
    avail_block = avail_block.rstrip() + "\n\n"

    before = user_message[:avail_start]
    middle = user_message[avail_end:eval_start]
    after = user_message[eval_start:]

    # Strip any extra trailing blank lines from the middle so we don't accumulate
    # blank lines after the move.
    middle = middle.rstrip() + "\n\n"

    return before + middle + avail_block + after
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_prompt_ab_transform.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Sanity-check on a real log entry**

Run:

```bash
python -c "
import json
from pathlib import Path
from scripts._prompt_ab.sampler import iter_card_reward_calls
from scripts._prompt_ab.transform import apply_b1
samples = list(iter_card_reward_calls([Path('logs/run_20260429_103038_40df2787.jsonl')], min_prompt_len=5000))
print(f'samples: {len(samples)}')
if samples:
    s = samples[0]
    out = apply_b1(s.user_message)
    a_pos = out.index('## Available Cards')
    e_pos = out.index('## Evaluation')
    print(f'available_pos={a_pos}, eval_pos={e_pos}, gap={e_pos - a_pos}')
    assert a_pos < e_pos
    assert len(out) == len(s.user_message), 'length must match (pure reorder)'
    print('OK')
"
```

Expected: prints `samples: N`, then `available_pos=X, eval_pos=Y, gap=Z` with `gap` < 200 (block adjacent), then `OK`.

- [ ] **Step 6: Commit**

```bash
git add scripts/_prompt_ab/transform.py tests/scripts/test_prompt_ab_transform.py
git commit -m "feat(prompt_ab): add B1 transform (relocate Available Cards to tail)"
```

---

## Task 3: Runner — async resampling against the original gameplay model

**Files:**
- Create: `scripts/_prompt_ab/runner.py`

- [ ] **Step 1: Implement the runner (no test — wraps async I/O)**

Create `scripts/_prompt_ab/runner.py`:

```python
"""Resample (system, user) prompts against the originally-recorded model.

Uses src.brain.llm_caller.call_raw for transport (handles provider routing,
relay profiles, retry).
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass

from src.brain.llm_caller import call_raw

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ResampleResult:
    """One resample attempt for a (sample, version, attempt_index) tuple."""
    response_text: str
    latency_ms: float
    tokens: int
    error: str = ""


async def resample_one(
    *,
    system_prompt: str,
    user_message: str,
    model: str,
    timeout_s: float = 90.0,
) -> ResampleResult:
    """Single resample with timeout and error capture."""
    try:
        text, latency_ms, tokens = await asyncio.wait_for(
            call_raw(
                system=system_prompt,
                prompt=user_message,
                model=model,
                call_type="prompt_ab_resample",
                call_class="gameplay_strategic",
                openai_relay_profile="default",
            ),
            timeout=timeout_s,
        )
        return ResampleResult(response_text=text, latency_ms=latency_ms, tokens=tokens)
    except (asyncio.TimeoutError, Exception) as exc:  # noqa: BLE001
        logger.warning("resample failed for model=%s: %s", model, exc)
        return ResampleResult(response_text="", latency_ms=0.0, tokens=0, error=repr(exc))


async def resample_pair(
    *,
    system_prompt: str,
    user_a: str,
    user_b: str,
    model: str,
    samples_per_version: int = 3,
    concurrency: int = 4,
) -> tuple[list[ResampleResult], list[ResampleResult]]:
    """Resample A and B versions in parallel, ``samples_per_version`` each.

    Bounded concurrency keeps us under provider-side rate limits.
    """
    sem = asyncio.Semaphore(concurrency)

    async def _one(user: str) -> ResampleResult:
        async with sem:
            return await resample_one(system_prompt=system_prompt, user_message=user, model=model)

    a_tasks = [asyncio.create_task(_one(user_a)) for _ in range(samples_per_version)]
    b_tasks = [asyncio.create_task(_one(user_b)) for _ in range(samples_per_version)]
    a_results = await asyncio.gather(*a_tasks)
    b_results = await asyncio.gather(*b_tasks)
    return list(a_results), list(b_results)
```

- [ ] **Step 2: Smoke-test the runner against one real sample**

Run:

```bash
python -c "
import asyncio
from pathlib import Path
from scripts._prompt_ab.sampler import iter_card_reward_calls
from scripts._prompt_ab.transform import apply_b1
from scripts._prompt_ab.runner import resample_pair

async def main():
    samples = list(iter_card_reward_calls([Path('logs/run_20260429_103038_40df2787.jsonl')], min_prompt_len=5000))
    s = samples[0]
    a_results, b_results = await resample_pair(
        system_prompt=s.system_prompt,
        user_a=s.user_message,
        user_b=apply_b1(s.user_message),
        model=s.model,
        samples_per_version=1,
    )
    print('A:', a_results[0].response_text[:200])
    print('B:', b_results[0].response_text[:200])
    print('OK' if not (a_results[0].error or b_results[0].error) else 'ERROR')

asyncio.run(main())
"
```

Expected: prints two response previews and `OK`. If error, debug `call_raw` config (env vars, relay profile) before continuing.

- [ ] **Step 3: Commit**

```bash
git add scripts/_prompt_ab/runner.py
git commit -m "feat(prompt_ab): add async resample runner"
```

---

## Task 4: Decision parsing and L1 agreement

**Files:**
- Create: `scripts/_prompt_ab/decision.py`
- Create: `tests/scripts/test_prompt_ab_decision.py`

- [ ] **Step 1: Write the failing test**

Create `tests/scripts/test_prompt_ab_decision.py`:

```python
"""Unit tests for decision parsing helpers."""
from __future__ import annotations

from scripts._prompt_ab.decision import (
    DecisionVerdict,
    parse_card_reward_decision,
)


def test_parse_valid_choose_reward_card() -> None:
    text = '''Some thinking...
<decision>
{"action": "choose_reward_card", "option_index": 1, "reasoning": "fits poison plan"}
</decision>'''
    v = parse_card_reward_decision(text)
    assert v.malformed is False
    assert v.action == "choose_reward_card"
    assert v.option_index == 1
    assert v.is_skip is False


def test_parse_valid_skip_alternative() -> None:
    text = '<decision>{"action": "choose_reward_alternative", "option_index": 0, "reasoning": "no fit"}</decision>'
    v = parse_card_reward_decision(text)
    assert v.malformed is False
    assert v.action == "choose_reward_alternative"
    assert v.option_index == 0


def test_parse_missing_decision_block() -> None:
    text = "I think I'd pick option 1 because of the synergy."
    v = parse_card_reward_decision(text)
    assert v.malformed is True
    assert v.option_index is None


def test_parse_invalid_json() -> None:
    text = '<decision>{"action": "choose_reward_card", option_index: 1}</decision>'
    v = parse_card_reward_decision(text)
    assert v.malformed is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m pytest tests/scripts/test_prompt_ab_decision.py -v`
Expected: FAIL with `ModuleNotFoundError`

- [ ] **Step 3: Implement decision parsing**

Create `scripts/_prompt_ab/decision.py`:

```python
"""Parse card_reward decisions from LLM response text."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class DecisionVerdict:
    """Parsed decision from one resample response."""
    action: str = ""
    option_index: int | None = None
    is_skip: bool = False
    malformed: bool = False
    raw_decision: str = ""


_DECISION_RE = re.compile(r"<decision>\s*(\{.*?\})\s*</decision>", re.DOTALL)


def parse_card_reward_decision(response_text: str) -> DecisionVerdict:
    """Extract action + option_index from a card_reward response.

    Returns ``malformed=True`` if no <decision> block, invalid JSON, or
    missing required fields.
    """
    if not response_text:
        return DecisionVerdict(malformed=True)
    m = _DECISION_RE.search(response_text)
    if m is None:
        return DecisionVerdict(malformed=True)
    raw = m.group(1)
    try:
        obj = json.loads(raw)
    except json.JSONDecodeError:
        return DecisionVerdict(malformed=True, raw_decision=raw)
    action = str(obj.get("action") or "")
    option_index = obj.get("option_index")
    if action not in ("choose_reward_card", "choose_reward_alternative", "discard_potion"):
        return DecisionVerdict(malformed=True, raw_decision=raw)
    if action != "discard_potion":
        if not isinstance(option_index, int):
            return DecisionVerdict(malformed=True, action=action, raw_decision=raw)
    is_skip = action == "choose_reward_alternative"
    return DecisionVerdict(
        action=action,
        option_index=option_index if isinstance(option_index, int) else None,
        is_skip=is_skip,
        malformed=False,
        raw_decision=raw,
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m pytest tests/scripts/test_prompt_ab_decision.py -v`
Expected: 4 PASSED

- [ ] **Step 5: Commit**

```bash
git add scripts/_prompt_ab/decision.py tests/scripts/test_prompt_ab_decision.py
git commit -m "feat(prompt_ab): add decision parser for L1 agreement check"
```

---

## Task 5: Judge — blind L2 quality evaluation

**Files:**
- Create: `scripts/_prompt_ab/judge.py`

- [ ] **Step 1: Implement the judge (no unit test — depends on live LLM; integration covered by smoke test in Task 7)**

Create `scripts/_prompt_ab/judge.py`:

```python
"""Blind L2 quality judge for A/B response pairs."""
from __future__ import annotations

import json
import logging
import os
import random
import re
from dataclasses import dataclass

from src.brain.llm_caller import call_raw

logger = logging.getLogger(__name__)


# Judge model: defaults to Claude Opus 4.7 (analysis tier). Override with
# STS2_PROMPT_AB_JUDGE_MODEL.
_DEFAULT_JUDGE_MODEL = "claude-opus-4-7"


_JUDGE_SYSTEM = """You are a blind A/B reviewer of two responses to the same Slay the Spire 2 card-reward decision. Your job is to score each on a 4-dimension rubric and pick a winner.

You do NOT know which response was generated by which prompt variant. Be impartial and rubric-driven.

Output format (strict JSON inside <verdict>...</verdict>):
{
  "scores": {
    "option_1": {"soundness": 1-5, "coverage": 1-5, "coherence": 1-5, "risk_awareness": 1-5},
    "option_2": {"soundness": 1-5, "coverage": 1-5, "coherence": 1-5, "risk_awareness": 1-5}
  },
  "winner": "option_1" | "option_2" | "tie",
  "rationale": "<2-3 sentence explanation>"
}

Rubric:
- soundness: does the chosen card improve the deck given current state and boss matchup?
- coverage: does the response cite relevant deck dimensions (Damage/Defense/Draw/Energy), boss DPS target, and rarity?
- coherence: does it align with the Strategic Thread / build trajectory shown in the user message?
- risk_awareness: does it acknowledge what's being given up (skipped cards, deck bloat, archetype dilution)?
"""


@dataclass(frozen=True)
class JudgeVerdict:
    """One blind judge verdict for an A/B pair."""
    winner: str  # "A", "B", or "tie"
    score_a: dict[str, int]
    score_b: dict[str, int]
    rationale: str
    malformed: bool = False
    raw_response: str = ""


_VERDICT_RE = re.compile(r"<verdict>\s*(\{.*?\})\s*</verdict>", re.DOTALL)


def _build_judge_user_message(
    *,
    user_message_summary: str,
    response_a: str,
    response_b: str,
    swap: bool,
) -> tuple[str, str, str]:
    """Build user message with randomized A/B labeling.

    Returns (user_message, label_for_a, label_for_b) where labels are either
    'option_1' or 'option_2'.
    """
    if swap:
        first_resp, second_resp = response_b, response_a
        label_a, label_b = "option_2", "option_1"
    else:
        first_resp, second_resp = response_a, response_b
        label_a, label_b = "option_1", "option_2"
    user = (
        "## Decision context (excerpt of user message shown to both options)\n\n"
        + user_message_summary
        + "\n\n## option_1 response\n\n"
        + first_resp
        + "\n\n## option_2 response\n\n"
        + second_resp
        + "\n\nScore both options strictly per the rubric and emit the JSON verdict."
    )
    return user, label_a, label_b


def _truncate_user_message_for_judge(user_message: str, max_chars: int = 6000) -> str:
    """Trim user message to keep judge prompt small but informative.

    Keeps the first 4000 chars (covers headers + early context) and the last
    2000 chars (covers options + eval framework).
    """
    if len(user_message) <= max_chars:
        return user_message
    head = user_message[:4000]
    tail = user_message[-2000:]
    return head + "\n\n[... TRUNCATED ...]\n\n" + tail


async def judge_pair(
    *,
    user_message: str,
    response_a: str,
    response_b: str,
    seed: int = 0,
) -> JudgeVerdict:
    """Run one blind judge call. Position swap is RNG-controlled by ``seed``."""
    if not response_a or not response_b:
        return JudgeVerdict(winner="tie", score_a={}, score_b={}, rationale="empty response", malformed=True)

    rng = random.Random(seed)
    swap = rng.random() < 0.5

    user_summary = _truncate_user_message_for_judge(user_message)
    user_msg, label_a, label_b = _build_judge_user_message(
        user_message_summary=user_summary,
        response_a=response_a,
        response_b=response_b,
        swap=swap,
    )

    judge_model = os.environ.get("STS2_PROMPT_AB_JUDGE_MODEL", _DEFAULT_JUDGE_MODEL)
    text, _latency, _tokens = await call_raw(
        system=_JUDGE_SYSTEM,
        prompt=user_msg,
        model=judge_model,
        call_type="prompt_ab_judge",
        call_class="postrun_summary",
    )

    m = _VERDICT_RE.search(text)
    if m is None:
        return JudgeVerdict(winner="tie", score_a={}, score_b={}, rationale="no verdict block", malformed=True, raw_response=text)
    try:
        obj = json.loads(m.group(1))
    except json.JSONDecodeError:
        return JudgeVerdict(winner="tie", score_a={}, score_b={}, rationale="invalid json", malformed=True, raw_response=text)

    raw_winner = str(obj.get("winner") or "tie")
    scores = obj.get("scores") or {}
    score_first = dict(scores.get("option_1") or {})
    score_second = dict(scores.get("option_2") or {})

    if swap:
        score_a = score_second
        score_b = score_first
        if raw_winner == "option_1":
            winner = "B"
        elif raw_winner == "option_2":
            winner = "A"
        else:
            winner = "tie"
    else:
        score_a = score_first
        score_b = score_second
        if raw_winner == "option_1":
            winner = "A"
        elif raw_winner == "option_2":
            winner = "B"
        else:
            winner = "tie"

    return JudgeVerdict(
        winner=winner,
        score_a=score_a,
        score_b=score_b,
        rationale=str(obj.get("rationale") or ""),
        malformed=False,
        raw_response=text,
    )
```

- [ ] **Step 2: Commit**

```bash
git add scripts/_prompt_ab/judge.py
git commit -m "feat(prompt_ab): add blind L2 judge with position swap"
```

---

## Task 6: Report aggregation

**Files:**
- Create: `scripts/_prompt_ab/report.py`

- [ ] **Step 1: Implement the report aggregator**

Create `scripts/_prompt_ab/report.py`:

```python
"""Aggregate A/B run results into a Markdown + JSON report."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean


@dataclass
class SampleResult:
    """Aggregate per-sample outcome (after L1 + L2)."""
    run_id: str
    log_path: str
    line_index: int
    a_decisions: list[int | None]
    b_decisions: list[int | None]
    a_malformed: int
    b_malformed: int
    judge_winner: str = ""  # "A", "B", "tie", "" if not judged
    judge_score_a_total: int = 0
    judge_score_b_total: int = 0
    judge_rationale: str = ""


@dataclass
class ReportSummary:
    n_samples: int
    n_disagreements: int
    a_malformed_rate: float
    b_malformed_rate: float
    judge_a_wins: int
    judge_b_wins: int
    judge_ties: int
    judge_a_mean_total: float
    judge_b_mean_total: float
    pass_verdict: str
    notes: list[str] = field(default_factory=list)


def _decision_disagrees(a: list[int | None], b: list[int | None]) -> bool:
    """Two versions disagree if their MOST-COMMON option_index differs.

    None values are excluded; if either is all-None, treat as disagreement
    (one side is malformed).
    """
    a_clean = [x for x in a if x is not None]
    b_clean = [x for x in b if x is not None]
    if not a_clean or not b_clean:
        return True
    a_top = max(set(a_clean), key=a_clean.count)
    b_top = max(set(b_clean), key=b_clean.count)
    return a_top != b_top


def _score_total(score: dict[str, int]) -> int:
    if not score:
        return 0
    return sum(int(score.get(k, 0)) for k in ("soundness", "coverage", "coherence", "risk_awareness"))


def summarize(samples: Iterable[SampleResult]) -> ReportSummary:
    samples = list(samples)
    n = len(samples)
    disagreements = sum(1 for s in samples if _decision_disagrees(s.a_decisions, s.b_decisions))

    total_a_attempts = sum(len(s.a_decisions) for s in samples)
    total_b_attempts = sum(len(s.b_decisions) for s in samples)
    a_malformed = sum(s.a_malformed for s in samples) / max(total_a_attempts, 1)
    b_malformed = sum(s.b_malformed for s in samples) / max(total_b_attempts, 1)

    judged = [s for s in samples if s.judge_winner in ("A", "B", "tie")]
    a_wins = sum(1 for s in judged if s.judge_winner == "A")
    b_wins = sum(1 for s in judged if s.judge_winner == "B")
    ties = sum(1 for s in judged if s.judge_winner == "tie")

    judge_a_total_mean = mean([s.judge_score_a_total for s in judged]) if judged else 0.0
    judge_b_total_mean = mean([s.judge_score_b_total for s in judged]) if judged else 0.0

    notes: list[str] = []
    pass_verdict = "INCONCLUSIVE"

    # Apply pass criteria from the spec
    if b_malformed - a_malformed > 0.10:
        pass_verdict = "REJECT"
        notes.append(f"B malformed-rate +{(b_malformed - a_malformed) * 100:.1f}pp vs A — rejection threshold is 10pp")
    elif judge_b_total_mean + 1.0 < judge_a_total_mean and judged:
        pass_verdict = "REJECT"
        notes.append(f"B mean total score {judge_b_total_mean:.2f} < A {judge_a_total_mean:.2f} by >1 point")
    elif disagreements / max(n, 1) < 0.20 and n > 0:
        pass_verdict = "QUALITY-NEUTRAL"
        notes.append(f"A/B agree on {(1 - disagreements / n) * 100:.0f}% of samples — change is essentially silent")
    elif b_wins + a_wins == 0:
        pass_verdict = "INCONCLUSIVE"
        notes.append("no judge verdicts available")
    else:
        b_win_rate = b_wins / max(b_wins + a_wins, 1)
        if b_win_rate >= 0.55 and (b_wins + a_wins) >= 15:
            pass_verdict = "PASS"
            notes.append(f"B wins {b_wins}/{b_wins + a_wins} non-tie disagreements ({b_win_rate:.2f})")
        elif b_win_rate <= 0.45:
            pass_verdict = "REJECT"
            notes.append(f"B loses majority of disagreements: {b_win_rate:.2f}")
        else:
            pass_verdict = "MIXED"
            notes.append(f"B win rate {b_win_rate:.2f} on {b_wins + a_wins} disagreements — borderline")

    return ReportSummary(
        n_samples=n,
        n_disagreements=disagreements,
        a_malformed_rate=a_malformed,
        b_malformed_rate=b_malformed,
        judge_a_wins=a_wins,
        judge_b_wins=b_wins,
        judge_ties=ties,
        judge_a_mean_total=judge_a_total_mean,
        judge_b_mean_total=judge_b_total_mean,
        pass_verdict=pass_verdict,
        notes=notes,
    )


def write_report(
    *,
    out_dir: Path,
    samples: list[SampleResult],
    summary: ReportSummary,
    timestamp: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"prompt_ab_b1_{timestamp}.json"
    md_path = out_dir / f"prompt_ab_b1_{timestamp}.md"

    json_path.write_text(
        json.dumps(
            {"summary": asdict(summary), "samples": [asdict(s) for s in samples]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Prompt Reorder B1 — A/B Report ({timestamp})",
        "",
        f"**Verdict: {summary.pass_verdict}**",
        "",
        "## Summary",
        f"- Samples: {summary.n_samples}",
        f"- Disagreements (top-of-3 differs): {summary.n_disagreements}",
        f"- Malformed rate — A: {summary.a_malformed_rate:.2%}, B: {summary.b_malformed_rate:.2%}",
        f"- Judge wins — A: {summary.judge_a_wins}, B: {summary.judge_b_wins}, tie: {summary.judge_ties}",
        f"- Judge mean score (out of 20) — A: {summary.judge_a_mean_total:.2f}, B: {summary.judge_b_mean_total:.2f}",
        "",
        "## Notes",
    ]
    for n in summary.notes:
        lines.append(f"- {n}")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path
```

- [ ] **Step 2: Commit**

```bash
git add scripts/_prompt_ab/report.py
git commit -m "feat(prompt_ab): add report aggregation with pass/fail criteria"
```

---

## Task 7: CLI entry point and end-to-end smoke run

**Files:**
- Create: `scripts/prompt_ab_test.py`

- [ ] **Step 1: Implement the CLI**

Create `scripts/prompt_ab_test.py`:

```python
"""B1 prompt reorder A/B test driver.

Usage:
    python -m scripts.prompt_ab_test --n 30 --logs-glob 'logs/run_*.jsonl'
"""
from __future__ import annotations

import argparse
import asyncio
import datetime as dt
import logging
import random
from collections import Counter
from pathlib import Path

from scripts._prompt_ab.decision import parse_card_reward_decision
from scripts._prompt_ab.judge import judge_pair
from scripts._prompt_ab.report import SampleResult, summarize, write_report
from scripts._prompt_ab.runner import resample_pair
from scripts._prompt_ab.sampler import iter_card_reward_calls
from scripts._prompt_ab.transform import apply_b1


logger = logging.getLogger(__name__)


def _stratify_by_act(samples: list, n: int, seed: int) -> list:
    """Sort samples into per-act buckets, then round-robin sample up to n."""
    rng = random.Random(seed)

    def _act_for(s) -> str:
        m = s.user_message
        for marker in ("Act: 1 |", "Act: 2 |", "Act: 3 |"):
            if marker in m:
                return marker[5]
        return "?"

    buckets: dict[str, list] = {"1": [], "2": [], "3": [], "?": []}
    for s in samples:
        buckets[_act_for(s)].append(s)
    for v in buckets.values():
        rng.shuffle(v)

    out: list = []
    while len(out) < n:
        added = 0
        for act in ("1", "2", "3", "?"):
            if buckets[act] and len(out) < n:
                out.append(buckets[act].pop())
                added += 1
        if added == 0:
            break
    return out


async def _run(args: argparse.Namespace) -> int:
    logs = sorted(Path().glob(args.logs_glob))
    if not logs:
        print(f"no logs match {args.logs_glob}")
        return 2

    all_samples = list(iter_card_reward_calls(logs, min_prompt_len=args.min_prompt_len))
    print(f"found {len(all_samples)} card_reward calls in {len(logs)} log files")
    if not all_samples:
        return 2

    selected = _stratify_by_act(all_samples, args.n, seed=args.seed)
    act_dist = Counter(
        next((c for c in ("1", "2", "3") if f"Act: {c} |" in s.user_message), "?")
        for s in selected
    )
    print(f"selected {len(selected)} samples (act distribution: {dict(act_dist)})")

    results: list[SampleResult] = []
    for idx, s in enumerate(selected, 1):
        try:
            user_b = apply_b1(s.user_message)
        except Exception as exc:  # noqa: BLE001
            print(f"  [{idx}/{len(selected)}] transform failed: {exc} — skipping")
            continue

        a_results, b_results = await resample_pair(
            system_prompt=s.system_prompt,
            user_a=s.user_message,
            user_b=user_b,
            model=s.model,
            samples_per_version=args.samples_per_version,
            concurrency=args.concurrency,
        )

        a_decisions = [parse_card_reward_decision(r.response_text) for r in a_results]
        b_decisions = [parse_card_reward_decision(r.response_text) for r in b_results]
        a_indices = [d.option_index for d in a_decisions]
        b_indices = [d.option_index for d in b_decisions]
        a_malformed = sum(1 for d in a_decisions if d.malformed)
        b_malformed = sum(1 for d in b_decisions if d.malformed)

        sr = SampleResult(
            run_id=s.run_id,
            log_path=s.log_path,
            line_index=s.line_index,
            a_decisions=a_indices,
            b_decisions=b_indices,
            a_malformed=a_malformed,
            b_malformed=b_malformed,
        )

        # Run judge if there's at least one valid response on each side
        if a_results[0].response_text and b_results[0].response_text:
            verdict = await judge_pair(
                user_message=s.user_message,
                response_a=a_results[0].response_text,
                response_b=b_results[0].response_text,
                seed=args.seed + idx,
            )
            sr.judge_winner = verdict.winner
            sr.judge_score_a_total = sum(int(v) for v in verdict.score_a.values())
            sr.judge_score_b_total = sum(int(v) for v in verdict.score_b.values())
            sr.judge_rationale = verdict.rationale

        results.append(sr)
        print(
            f"  [{idx}/{len(selected)}] A={a_indices} B={b_indices} "
            f"malformed=A{a_malformed}/B{b_malformed} judge={sr.judge_winner or '-'}"
        )

    summary = summarize(results)
    timestamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    out_dir = Path("data/reports/prompt_ab")
    json_path, md_path = write_report(
        out_dir=out_dir, samples=results, summary=summary, timestamp=timestamp
    )

    print()
    print(f"VERDICT: {summary.pass_verdict}")
    print(f"  disagreements: {summary.n_disagreements}/{summary.n_samples}")
    print(f"  judge wins — A: {summary.judge_a_wins}, B: {summary.judge_b_wins}, tie: {summary.judge_ties}")
    print(f"  mean score — A: {summary.judge_a_mean_total:.2f}, B: {summary.judge_b_mean_total:.2f}")
    print(f"  malformed — A: {summary.a_malformed_rate:.2%}, B: {summary.b_malformed_rate:.2%}")
    for n in summary.notes:
        print(f"  - {n}")
    print()
    print(f"json: {json_path}")
    print(f"md:   {md_path}")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description="B1 prompt reorder A/B test")
    p.add_argument("--n", type=int, default=30, help="number of samples (default 30)")
    p.add_argument("--logs-glob", default="logs/run_*.jsonl")
    p.add_argument("--min-prompt-len", type=int, default=5000)
    p.add_argument("--samples-per-version", type=int, default=3)
    p.add_argument("--concurrency", type=int, default=4)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING)
    return asyncio.run(_run(args))


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 2: Smoke run with N=2 to validate the pipeline end-to-end**

Run: `python -m scripts.prompt_ab_test --n 2 --samples-per-version 1 --concurrency 2 -v`

Expected:
- prints "found N card_reward calls in M log files" with N > 100
- prints "selected 2 samples"
- prints two `[i/2]` progress lines with decisions and judge verdict
- prints final VERDICT line
- writes a JSON + MD file under `data/reports/prompt_ab/`

If any step errors, fix the bug before continuing. Common issues: env vars missing (ANTHROPIC_API_KEY), relay-profile mismatch, model string not recognized.

- [ ] **Step 3: Commit**

```bash
git add scripts/prompt_ab_test.py
git commit -m "feat(prompt_ab): CLI entry point and end-to-end harness"
```

---

## Task 8: Full A/B run with N=30

- [ ] **Step 1: Run the full harness**

Run: `python -m scripts.prompt_ab_test --n 30 -v`

Expected runtime: ~5-10 minutes depending on provider latency.
Expected output: `VERDICT: PASS | REJECT | QUALITY-NEUTRAL | MIXED | INCONCLUSIVE` and a report file.

- [ ] **Step 2: Inspect the report**

Read `data/reports/prompt_ab/prompt_ab_b1_<timestamp>.md`.

- [ ] **Step 3: Decide based on verdict**

- **PASS** or **QUALITY-NEUTRAL**: proceed to Task 9 (apply B1 to production).
- **MIXED**: review the per-sample JSON, look at the rationale field for losses, decide whether to:
  - Refine B1 (e.g. also move Keyword Glossary up) and re-run
  - Run a larger N (50+) for tighter CI
  - Bring back to brainstorming for B2 design
- **REJECT**: stop. Do NOT modify reward.py. Document the failure in a follow-up note.
- **INCONCLUSIVE**: increase `--n` and `--samples-per-version`, re-run.

- [ ] **Step 4: Commit the report (regardless of verdict)**

```bash
git add data/reports/prompt_ab/
git commit -m "data(prompt_ab): B1 A/B test results — verdict <PASS/REJECT/...>"
```

---

## Task 9 (gated on PASS or QUALITY-NEUTRAL): apply B1 to production

**Files:**
- Modify: `src/brain/prompts/reward.py` — `build_card_reward_prompt`

- [ ] **Step 1: Locate the two relevant blocks**

Open `src/brain/prompts/reward.py` and find the section that builds `## Available Cards` (currently around lines 87-148, starts with `if rw.pending_card_choice:` and `lines.append("## Available Cards")`).

Note the section ends right before `# Keyword glossary` (currently line ~167).

The `## Evaluation — Boss Damage Check` section starts at the comment `# Boss damage check` (currently line ~175).

- [ ] **Step 2: Move the Available Cards block**

The required end state inside `if rw.pending_card_choice:` is:

```
## Available Cards    →  KEEP keyword glossary RIGHT BEFORE Available Cards
                        ↓ (new placement)
                     →  KEEP card clarification notes after Available Cards
                     →  KEEP Boss Damage Check + Build Trajectory after that
```

Concretely, restructure the inside of `if rw.pending_card_choice:` so the order is:

```
1. Keyword Glossary        (was after Available Cards)
2. Card Clarification Notes (already there)
3. Available Cards          (was before Glossary — moved down)
4. Boss Damage Check        (unchanged position relative to file)
5. Build Trajectory Check   (unchanged)
```

Wait — the spec said move Available Cards BEFORE Eval, KEEPING Glossary BEFORE Available Cards. So the actual move is: Glossary stays, Available Cards moves to after Glossary, Card Clarification Notes (which were after the eval blocks) move up to right before Eval too — OR stay at the very end.

Re-read the spec. Spec says final order: `Keyword Glossary → Available Cards → Boss Damage Check → Build Trajectory → Decision Format`.

Implement that. The current order inside `if rw.pending_card_choice:` is: build Available Cards loop → Glossary → Boss Damage Check → Build Trajectory → Card Clarification Notes.

**New order**: Glossary → Available Cards loop → Boss Damage Check → Build Trajectory → Card Clarification Notes (kept at tail; clarifications are reference material).

Edit the function body so the section starting with `lines.append("## Available Cards")` is moved to AFTER the keyword glossary block but BEFORE the `# Boss damage check` block.

- [ ] **Step 3: Run the existing prompt tests**

Run: `python -m pytest tests/prompts/ -v`

Expected: all PASS (these tests are mostly baseline-variant tests; reorder shouldn't affect them). If any fail because they assert specific section ordering, update the assertion to match the new order.

- [ ] **Step 4: Run regression / golden tests**

Run: `python -m pytest tests/regression/ -v`

Expected: any failure here means a golden snapshot needs regenerating. Inspect the diff manually first — every diff should be a pure reorder (no content additions/removals). If diffs look correct, regenerate snapshots per the project's regen procedure (see `tests/regression/test_fingerprint.py` for hints).

- [ ] **Step 5: Smoke run**

Run: `python -m scripts.run_agent --steps 50 --runs 1 --no-postrun --abandon-existing`

Expected: agent completes 50 steps without exception. No silent fallbacks triggered for `card_reward`. The new prompt order should be visible in `logs/run_*.jsonl` for any card_reward decision encountered.

- [ ] **Step 6: Spot-check one card_reward prompt from the smoke run**

Run:

```bash
python -c "
import json, glob
latest = sorted(glob.glob('logs/run_*.jsonl'))[-1]
with open(latest, encoding='utf-8') as f:
    for line in f:
        r = json.loads(line)
        if r.get('event') == 'llm_call' and '## Card Reward' in (r.get('prompt') or ''):
            p = r['prompt']
            avail = p.find('## Available Cards')
            eval_ = p.find('## Evaluation — Boss Damage Check')
            print(f'available_pos={avail}, eval_pos={eval_}, gap={eval_ - avail}')
            assert avail < eval_, 'B1 not applied!'
            assert 0 < eval_ - avail < 500, 'gap too large — Glossary may have moved unexpectedly'
            print('B1 applied correctly.')
            break
"
```

Expected: prints `B1 applied correctly.`

- [ ] **Step 7: Commit**

```bash
git add src/brain/prompts/reward.py tests/
git commit -m "feat(prompts): apply B1 — relocate Available Cards to tail in card_reward

A/B test (N=30) verdict: <PASS or QUALITY-NEUTRAL>. See
data/reports/prompt_ab/prompt_ab_b1_<timestamp>.md
and docs/superpowers/specs/2026-04-29-prompt-reorder-ab-test-design.md."
```

---

## Self-Review

**Spec coverage:**
- ✅ Sampler (Task 1) — covers spec §A/B Harness Design / Sample selection
- ✅ Transform (Task 2) — covers spec §Treatment construction
- ✅ Runner (Task 3) — covers spec §Sampling and judging — gameplay model resamples
- ✅ Decision parsing + L1 (Task 4) — covers spec §L1 — decision agreement
- ✅ Judge (Task 5) — covers spec §L2 — blind LLM judge with rubric and position swap
- ✅ Report (Task 6) — covers spec §Pass criteria with explicit thresholds
- ✅ End-to-end CLI (Task 7) — wires everything together
- ✅ Full run (Task 8) — produces the report
- ✅ Production change (Task 9) — gated on verdict per spec §Rollout Plan
- ✅ Non-goals respected — combat/shop/rest/event/map prompts NOT touched

**Placeholder scan:**
- ✅ No "TBD", "TODO", "implement later"
- ✅ Every code step shows complete code
- ✅ Every test step shows complete test code with assertions
- ✅ Every command shows expected output

**Type consistency:**
- `CardRewardSample` (sampler) — used identically in runner / CLI
- `ResampleResult` (runner) — used identically in CLI
- `DecisionVerdict` (decision) — used identically in CLI
- `JudgeVerdict` (judge) — used identically in CLI
- `SampleResult` / `ReportSummary` (report) — used identically in CLI
- All field names consistent across files
- `apply_b1`, `judge_pair`, `resample_pair`, `iter_card_reward_calls`, `parse_card_reward_decision` — names match between definition and usage

**Risk items addressed:**
- Empty-response handling in judge (returns malformed=True, winner="tie")
- Timeout in resample_one
- Glob no-match in CLI returns exit 2
- Position swap controlled by seed (deterministic + reproducible)
- Concurrency limited via Semaphore
- Stratification across acts so a single act doesn't dominate
