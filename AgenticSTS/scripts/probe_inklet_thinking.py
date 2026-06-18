from __future__ import annotations

import argparse
import json
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import config
from src.brain.v2_backend import V2Backend

_SYSTEM_PROFILE_SUFFIXES = {
    "baseline": "",
    "think_before_tool": (
        "\n\n## Thinking Rule\n"
        "- Before any tool call, reason carefully in thinking blocks about sequencing, "
        "tradeoffs, and resource preservation.\n"
        "- Compare at least two candidate lines internally before deciding.\n"
        "- After thinking, call exactly one decision tool.\n"
    ),
}


@dataclass
class RunStats:
    mode: str
    effort: str
    system_profile: str
    run_index: int
    block_types: list[str]
    thinking_chars: int
    text_chars: int
    tool_use_count: int
    tool_use_names: list[str]
    raw_thinking_start: bool
    raw_thinking_delta_chars: int
    raw_signature_delta_count: int
    raw_tool_use_start: bool
    raw_tool_json_chars: int
    raw_text_start: bool
    raw_text_delta_chars: int
    stop_reason: str | None
    input_tokens: int | None
    output_tokens: int | None

    @property
    def final_has_nonempty_thinking(self) -> bool:
        return self.thinking_chars > 0

    @property
    def final_has_tool_use(self) -> bool:
        return self.tool_use_count > 0

    @property
    def final_success(self) -> bool:
        return self.final_has_nonempty_thinking and self.final_has_tool_use

    @property
    def raw_has_nonempty_thinking(self) -> bool:
        return self.raw_thinking_delta_chars > 0

    @property
    def raw_has_signature_delta(self) -> bool:
        return self.raw_signature_delta_count > 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Probe Inklet fixture through V2Backend.call() and raw SSE capture.",
    )
    parser.add_argument(
        "--fixture",
        default="tests/fixtures/inklet_slippery_prompt.json",
        help="Path to the fixture JSON.",
    )
    parser.add_argument(
        "--runs",
        type=int,
        default=6,
        help="Number of runs per thinking mode.",
    )
    parser.add_argument(
        "--modes",
        nargs="+",
        default=["adaptive", "enabled"],
        choices=["adaptive", "enabled"],
        help="Thinking modes to test.",
    )
    parser.add_argument(
        "--model",
        default="",
        help=(
            "Optional model override. Defaults to fixture metadata.original_model "
            "or config.LLM_MODEL."
        ),
    )
    parser.add_argument(
        "--effort",
        default="medium",
        choices=["low", "medium", "high", "max"],
        help="Effort for adaptive thinking.",
    )
    parser.add_argument(
        "--efforts",
        nargs="+",
        choices=["low", "medium", "high", "max"],
        default=[],
        help="Optional list of efforts to test. Overrides --effort when provided.",
    )
    parser.add_argument(
        "--system-profiles",
        nargs="+",
        choices=sorted(_SYSTEM_PROFILE_SUFFIXES),
        default=["baseline"],
        help="System prompt variants to test.",
    )
    parser.add_argument(
        "--think-budget",
        type=int,
        default=4000,
        help="Budget tokens for enabled thinking.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=2048,
        help="Base max_tokens argument passed to V2Backend.call().",
    )
    parser.add_argument(
        "--save-json",
        default="",
        help="Optional output path for the full probe results JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    fixture = json.loads(Path(args.fixture).read_text(encoding="utf-8"))
    system = fixture["system_prompt"]
    messages = fixture["messages"]
    tools = fixture["tools"]
    metadata = fixture.get("metadata", {})
    model = args.model or metadata.get("original_model") or config.LLM_MODEL
    efforts = args.efforts or [args.effort]

    backend = V2Backend()
    all_stats: list[RunStats] = []

    original_think_type = config.LLM_THINK_TYPE
    try:
        for mode in args.modes:
            config.LLM_THINK_TYPE = mode
            for effort in efforts:
                for system_profile in args.system_profiles:
                    label = f"{mode} effort={effort} profile={system_profile}"
                    print(f"\n=== {label} model={model} runs={args.runs} ===")
                    for run_index in range(1, args.runs + 1):
                        stats = run_once(
                            backend=backend,
                            system=apply_system_profile(system, system_profile),
                            messages=messages,
                            tools=tools,
                            model=model,
                            mode=mode,
                            effort=effort,
                            system_profile=system_profile,
                            run_index=run_index,
                            think_budget=args.think_budget,
                            max_tokens=args.max_tokens,
                        )
                        all_stats.append(stats)
                        print(format_run(stats))

                    print(
                        format_summary(
                            label,
                            [
                                s
                                for s in all_stats
                                if s.mode == mode
                                and s.effort == effort
                                and s.system_profile == system_profile
                            ],
                        )
                    )
    finally:
        config.LLM_THINK_TYPE = original_think_type

    if args.save_json:
        out_path = Path(args.save_json)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(
                {
                    "fixture": str(Path(args.fixture)),
                    "model": model,
                    "runs": args.runs,
                    "modes": args.modes,
                    "efforts": efforts,
                    "system_profiles": args.system_profiles,
                    "results": [stats.__dict__ for stats in all_stats],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"\nSaved JSON to {out_path}")

    return 0


def run_once(
    *,
    backend: V2Backend,
    system: str,
    messages: list[dict[str, Any]],
    tools: list[dict[str, Any]],
    model: str,
    mode: str,
    effort: str,
    system_profile: str,
    run_index: int,
    think_budget: int,
    max_tokens: int,
) -> RunStats:
    client = backend._get_client(model)
    original_create = client.messages.create
    recorded_events: list[Any] = []

    class RecordingStream:
        def __init__(self, inner: Any) -> None:
            self._inner = inner

        def __iter__(self):
            for event in self._inner:
                recorded_events.append(event)
                yield event

        def close(self) -> None:
            close = getattr(self._inner, "close", None)
            if callable(close):
                close()

        def __getattr__(self, name: str) -> Any:
            return getattr(self._inner, name)

    def create_wrapper(*args: Any, **kwargs: Any) -> Any:
        result = original_create(*args, **kwargs)
        if kwargs.get("stream"):
            return RecordingStream(result)
        return result

    client.messages.create = create_wrapper
    try:
        response = backend.call(
            system=system,
            messages=messages,
            model=model,
            think=True,
            think_budget=think_budget,
            effort=effort,
            tools=tools,
            tool_choice={"type": "auto"},
            max_tokens=max_tokens,
        )
    finally:
        client.messages.create = original_create

    return build_stats(
        mode=mode,
        effort=effort,
        system_profile=system_profile,
        run_index=run_index,
        response=response,
        events=recorded_events,
    )


def build_stats(
    *,
    mode: str,
    effort: str,
    system_profile: str,
    run_index: int,
    response: Any,
    events: list[Any],
) -> RunStats:
    block_types: list[str] = []
    thinking_chars = 0
    text_chars = 0
    tool_use_count = 0
    tool_use_names: list[str] = []

    for block in list(getattr(response, "content", []) or []):
        block_type = getattr(block, "type", None) or type(block).__name__
        block_types.append(str(block_type))
        if block_type == "thinking":
            thinking_chars += len(getattr(block, "thinking", "") or "")
        elif block_type == "text":
            text_chars += len(getattr(block, "text", "") or "")
        elif block_type == "tool_use":
            tool_use_count += 1
            name = getattr(block, "name", "")
            if name:
                tool_use_names.append(name)

    raw_thinking_start = False
    raw_thinking_delta_chars = 0
    raw_signature_delta_count = 0
    raw_tool_use_start = False
    raw_tool_json_chars = 0
    raw_text_start = False
    raw_text_delta_chars = 0

    for event in events:
        event_type = getattr(event, "type", None)
        if event_type == "content_block_start":
            block = getattr(event, "content_block", None)
            block_type = getattr(block, "type", None)
            if block_type == "thinking":
                raw_thinking_start = True
            elif block_type == "tool_use":
                raw_tool_use_start = True
            elif block_type == "text":
                raw_text_start = True
        elif event_type == "content_block_delta":
            delta = getattr(event, "delta", None)
            delta_type = getattr(delta, "type", None)
            if delta_type == "thinking_delta":
                raw_thinking_delta_chars += len(getattr(delta, "thinking", "") or "")
            elif delta_type == "signature_delta":
                raw_signature_delta_count += 1
            elif delta_type == "input_json_delta":
                raw_tool_json_chars += len(getattr(delta, "partial_json", "") or "")
            elif delta_type == "text_delta":
                raw_text_delta_chars += len(getattr(delta, "text", "") or "")

    usage = getattr(response, "usage", None)
    return RunStats(
        mode=mode,
        effort=effort,
        system_profile=system_profile,
        run_index=run_index,
        block_types=block_types,
        thinking_chars=thinking_chars,
        text_chars=text_chars,
        tool_use_count=tool_use_count,
        tool_use_names=tool_use_names,
        raw_thinking_start=raw_thinking_start,
        raw_thinking_delta_chars=raw_thinking_delta_chars,
        raw_signature_delta_count=raw_signature_delta_count,
        raw_tool_use_start=raw_tool_use_start,
        raw_tool_json_chars=raw_tool_json_chars,
        raw_text_start=raw_text_start,
        raw_text_delta_chars=raw_text_delta_chars,
        stop_reason=getattr(response, "stop_reason", None),
        input_tokens=getattr(usage, "input_tokens", None),
        output_tokens=getattr(usage, "output_tokens", None),
    )


def format_run(stats: RunStats) -> str:
    return (
        f"run={stats.run_index} stop={stats.stop_reason} blocks={stats.block_types} "
        "final("
        f"thinking={stats.thinking_chars},text={stats.text_chars},tool={stats.tool_use_count}"
        ") "
        f"raw(th_start={stats.raw_thinking_start},th_delta={stats.raw_thinking_delta_chars},"
        f"sig={stats.raw_signature_delta_count},tool_start={stats.raw_tool_use_start},"
        f"tool_json={stats.raw_tool_json_chars},text_start={stats.raw_text_start},"
        f"text_delta={stats.raw_text_delta_chars}) "
        f"tok_in={stats.input_tokens} tok_out={stats.output_tokens}"
    )


def format_summary(label: str, stats_list: list[RunStats]) -> str:
    counter = Counter(tuple(s.block_types) for s in stats_list)
    total = len(stats_list)
    final_success = sum(s.final_success for s in stats_list)
    raw_thinking = sum(s.raw_has_nonempty_thinking for s in stats_list)
    raw_signature = sum(s.raw_has_signature_delta for s in stats_list)
    raw_tool = sum(s.raw_tool_use_start for s in stats_list)
    return (
        f"summary[{label}] final thinking+tool={final_success}/{total} | "
        f"raw nonempty thinking={raw_thinking}/{total} | raw signature={raw_signature}/{total} | "
        f"raw tool_use={raw_tool}/{total} | "
        f"block_shapes={dict(counter)}"
    )


def apply_system_profile(system: str, profile: str) -> str:
    suffix = _SYSTEM_PROFILE_SUFFIXES[profile]
    if not suffix:
        return system
    if suffix.strip() in system:
        return system
    return system + suffix


if __name__ == "__main__":
    raise SystemExit(main())
