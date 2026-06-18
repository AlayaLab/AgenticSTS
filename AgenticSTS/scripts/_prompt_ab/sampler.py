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
