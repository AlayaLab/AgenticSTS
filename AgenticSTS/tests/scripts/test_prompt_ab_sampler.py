"""Unit tests for prompt_ab sampler."""
from __future__ import annotations

import json
from pathlib import Path

from scripts._prompt_ab.sampler import CardRewardSample, iter_card_reward_calls


def _write_jsonl(path: Path, records: list[dict]) -> None:
    with path.open("w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r) + "\n")


def test_iter_card_reward_calls_filters_by_header(tmp_path: Path) -> None:
    log = tmp_path / "run_test.jsonl"
    long_prompt = "## Card Reward\n## Available Cards\n" + ("x" * 6000)
    records = [
        {
            "event": "llm_call",
            "call_type": "v2_single_call",
            "system_prompt": "sys",
            "prompt": long_prompt,
            "response": '<decision>{"option_index":0}</decision>',
            "model": "gemini-2.5-pro",
            "run_id": "r1",
        },
        {
            "event": "llm_call",
            "call_type": "v2_single_call",
            "system_prompt": "sys",
            "prompt": "## Map Navigation\n" + ("x" * 6000),
            "response": "x",
            "model": "gemini-2.5-pro",
            "run_id": "r1",
        },
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
        {
            "event": "llm_call",
            "call_type": "v2_single_call",
            "system_prompt": "sys",
            "prompt": short_prompt,
            "response": "x",
            "model": "g",
            "run_id": "r1",
        },
    ]
    _write_jsonl(log, records)

    samples = list(iter_card_reward_calls([log], min_prompt_len=5000))

    assert samples == []


def test_iter_card_reward_calls_requires_both_headers(tmp_path: Path) -> None:
    log = tmp_path / "run_test.jsonl"
    # Has Card Reward header but no Available Cards (e.g. potion-only state)
    prompt = "## Card Reward\n" + ("x" * 6000)
    records = [
        {
            "event": "llm_call",
            "call_type": "v2_single_call",
            "system_prompt": "sys",
            "prompt": prompt,
            "response": "x",
            "model": "g",
            "run_id": "r1",
        },
    ]
    _write_jsonl(log, records)

    samples = list(iter_card_reward_calls([log], min_prompt_len=0))

    assert samples == []
