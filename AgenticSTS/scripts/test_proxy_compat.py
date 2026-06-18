"""Probe Claude proxy compatibility across messages, streaming, and chat/completions."""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from typing import Any

import anthropic
from openai import OpenAI

import config
from src.brain.proxy_compat import (
    DEFAULT_TOOL_NAME,
    build_anthropic_tool,
    build_json_output_format,
    build_openai_tool,
    build_thinking_config,
    map_anthropic_tool_choice,
    map_chat_tool_choice,
    merge_output_config,
    summarize_anthropic_message,
    summarize_anthropic_stream,
    summarize_chat_completion,
    summarize_chat_stream,
    to_jsonable,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Probe a Claude-compatible proxy through native Messages, native streaming, "
            "and OpenAI-compatible chat/completions."
        )
    )
    parser.add_argument(
        "--transport",
        choices=[
            "messages",
            "messages_stream",
            "messages_raw_stream",
            "chat",
            "chat_stream",
            "all",
        ],
        default="all",
        help="Which protocol path to test.",
    )
    parser.add_argument(
        "--mode",
        choices=["tool", "json"],
        default="tool",
        help="Use tools/tool_calls or text JSON output.",
    )
    parser.add_argument("--model", default=config.LLM_MODEL, help="Model name to probe.")
    parser.add_argument(
        "--anthropic-base-url",
        default=config.ANTHROPIC_BASE_URL or "https://api.anthropic.com",
        help="Base URL for Anthropic SDK calls.",
    )
    parser.add_argument(
        "--chat-base-url",
        default="",
        help="Base URL for OpenAI-compatible chat/completions. Defaults to <anthropic>/v1/.",
    )
    parser.add_argument(
        "--api-key",
        default=config.LLM_API_KEY,
        help="API key used for both paths. Defaults to ANTHROPIC_API_KEY/LLM_API_KEY.",
    )
    parser.add_argument("--system", default="", help="Optional system prompt.")
    parser.add_argument("--prompt", default="", help="Inline user prompt.")
    parser.add_argument(
        "--prompt-file",
        default="",
        help="Optional UTF-8 file containing the user prompt.",
    )
    parser.add_argument(
        "--tool-choice",
        choices=["auto", "any", "tool", "none"],
        default="auto",
        help="Tool-choice mode for tool probes.",
    )
    parser.add_argument(
        "--disable-parallel-tool-use",
        action="store_true",
        help="Set disable_parallel_tool_use/parallel_tool_calls=false where supported.",
    )
    parser.add_argument(
        "--thinking",
        choices=["off", "adaptive", "enabled"],
        default="off",
        help="Thinking mode to test.",
    )
    parser.add_argument(
        "--thinking-display",
        choices=["default", "summarized", "omitted"],
        default="default",
        help="Thinking display mode for native Messages requests.",
    )
    parser.add_argument(
        "--think-budget",
        type=int,
        default=2048,
        help="Budget tokens for thinking=enabled.",
    )
    parser.add_argument(
        "--effort",
        choices=["low", "medium", "high", "max"],
        default="high",
        help="Effort level for thinking=adaptive.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=4096,
        help="max_tokens / max_completion_tokens value.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.0,
        help="Temperature for non-thinking probes. Thinking probes force 1.0 on Messages.",
    )
    parser.add_argument(
        "--strict-tool",
        action="store_true",
        help="Mark the test tool strict when the transport supports it.",
    )
    parser.add_argument(
        "--eager-input-streaming",
        action="store_true",
        help="Enable eager_input_streaming on the Anthropic test tool.",
    )
    parser.add_argument(
        "--chat-response-format",
        choices=["none", "json_object"],
        default="none",
        help="response_format for chat/completions JSON probes.",
    )
    parser.add_argument(
        "--save-dir",
        default="",
        help="Optional directory to save raw responses/events as JSON.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    if not args.api_key:
        print("Missing API key. Set ANTHROPIC_API_KEY or pass --api-key.", file=sys.stderr)
        return 2

    prompt = load_prompt(args)
    anthropic_base_url = args.anthropic_base_url.strip()
    chat_base_url = args.chat_base_url.strip() or _default_chat_base_url(anthropic_base_url)

    anthropic_client = anthropic.Anthropic(
        api_key=args.api_key,
        base_url=anthropic_base_url,
        timeout=anthropic.Timeout(timeout=300.0, connect=30.0),
        max_retries=0,
    )
    chat_client = OpenAI(
        api_key=args.api_key,
        base_url=chat_base_url,
        max_retries=0,
        timeout=300.0,
    )

    results: list[dict[str, Any]] = []

    for transport in expand_transports(args.transport):
        started = time.monotonic()
        try:
            if transport == "messages":
                result = run_messages_probe(anthropic_client, args, prompt)
            elif transport == "messages_stream":
                result = run_messages_stream_probe(anthropic_client, args, prompt)
            elif transport == "messages_raw_stream":
                result = run_messages_raw_stream_probe(anthropic_client, args, prompt)
            elif transport == "chat":
                result = run_chat_probe(chat_client, args, prompt)
            elif transport == "chat_stream":
                result = run_chat_stream_probe(chat_client, args, prompt)
            else:
                raise ValueError(f"Unknown transport: {transport}")
        except Exception as exc:
            result = {
                "transport": transport,
                "status": "error",
                "error": repr(exc),
            }
        result["elapsed_ms"] = round((time.monotonic() - started) * 1000, 1)
        results.append(result)

        print(f"\n=== {transport} ===")
        print(json.dumps(result, ensure_ascii=False, indent=2))

    if args.save_dir:
        save_results(results, Path(args.save_dir))

    return 0


def load_prompt(args: argparse.Namespace) -> str:
    prompt = ""
    if args.prompt_file:
        prompt = Path(args.prompt_file).read_text(encoding="utf-8")
    elif args.prompt:
        prompt = args.prompt

    if not prompt.strip():
        prompt = (
            "Pick the best action for this turn. "
            "Action should be `proceed` unless there is a compelling reason otherwise."
        )

    if args.mode == "tool":
        prompt = (
            f"{prompt.strip()}\n\n"
            f"Return the answer by calling the `{DEFAULT_TOOL_NAME}` tool."
        )
    else:
        prompt = (
            f"{prompt.strip()}\n\n"
            "Return only a JSON object matching the requested schema. "
            "Do not include markdown or prose."
        )
    return prompt


def expand_transports(value: str) -> list[str]:
    if value == "all":
        return ["messages", "messages_stream", "messages_raw_stream", "chat", "chat_stream"]
    return [value]


def run_messages_probe(
    client: anthropic.Anthropic,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    request = build_messages_request(args, prompt)
    response = client.messages.create(**request)
    return {
        "transport": "messages",
        "status": "ok",
        "summary": summarize_anthropic_message(response),
        "request": redact_request(request),
        "raw_response": to_jsonable(response),
    }


def run_messages_stream_probe(
    client: anthropic.Anthropic,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    request = build_messages_request(args, prompt)
    events: list[Any] = []
    with client.messages.stream(**request) as stream:
        for event in stream:
            events.append(event)
        final_message = stream.get_final_message()

    return {
        "transport": "messages_stream",
        "status": "ok",
        "stream_summary": summarize_anthropic_stream(events),
        "final_message_summary": summarize_anthropic_message(final_message),
        "request": redact_request(request),
        "raw_events": to_jsonable(events),
        "raw_final_message": to_jsonable(final_message),
    }


def run_messages_raw_stream_probe(
    client: anthropic.Anthropic,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    request = build_messages_request(args, prompt)
    raw_stream = client.messages.create(**request, stream=True)
    events: list[Any] = []
    final_message = None
    try:
        for event in raw_stream:
            events.append(event)
            if getattr(event, "type", None) == "message_stop":
                final_message = getattr(event, "message", None) or final_message
    finally:
        close = getattr(raw_stream, "close", None)
        if callable(close):
            close()

    result: dict[str, Any] = {
        "transport": "messages_raw_stream",
        "status": "ok",
        "stream_summary": summarize_anthropic_stream(events),
        "request": redact_request(request),
        "raw_events": to_jsonable(events),
    }
    if final_message is not None:
        result["final_message_summary"] = summarize_anthropic_message(final_message)
        result["raw_final_message"] = to_jsonable(final_message)
    return result


def run_chat_probe(
    client: OpenAI,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    request = build_chat_request(args, prompt, stream=False)
    response = client.chat.completions.create(**request)
    return {
        "transport": "chat",
        "status": "ok",
        "summary": summarize_chat_completion(response),
        "request": redact_request(request),
        "raw_response": to_jsonable(response),
    }


def run_chat_stream_probe(
    client: OpenAI,
    args: argparse.Namespace,
    prompt: str,
) -> dict[str, Any]:
    request = build_chat_request(args, prompt, stream=True)
    chunks = list(client.chat.completions.create(**request))
    return {
        "transport": "chat_stream",
        "status": "ok",
        "summary": summarize_chat_stream(chunks),
        "request": redact_request(request),
        "raw_chunks": to_jsonable(chunks),
    }


def build_messages_request(args: argparse.Namespace, prompt: str) -> dict[str, Any]:
    request: dict[str, Any] = {
        "model": args.model,
        "max_tokens": args.max_tokens,
        "messages": [{"role": "user", "content": prompt}],
    }
    if args.system:
        request["system"] = args.system

    thinking = build_thinking_config(
        args.thinking,
        budget_tokens=args.think_budget,
        display=args.thinking_display,
    )
    json_format = build_json_output_format() if args.mode == "json" else None
    request["output_config"] = merge_output_config(
        effort=args.effort if args.thinking == "adaptive" else "",
        json_format=json_format,
    )
    if request["output_config"] is None:
        request.pop("output_config")

    if thinking is not None:
        request["thinking"] = thinking
        request["temperature"] = 1.0
    else:
        request["temperature"] = args.temperature

    if args.mode == "tool":
        request["tools"] = [
            build_anthropic_tool(
                strict=args.strict_tool,
                eager_input_streaming=args.eager_input_streaming,
            )
        ]
        request["tool_choice"] = map_anthropic_tool_choice(
            args.tool_choice,
            disable_parallel_tool_use=args.disable_parallel_tool_use,
        )
    return request


def build_chat_request(
    args: argparse.Namespace,
    prompt: str,
    *,
    stream: bool,
) -> dict[str, Any]:
    messages = []
    if args.system:
        messages.append({"role": "system", "content": args.system})
    messages.append({"role": "user", "content": prompt})

    request: dict[str, Any] = {
        "model": args.model,
        "messages": messages,
        "max_tokens": args.max_tokens,
        "stream": stream,
        "temperature": 1.0 if args.thinking != "off" else args.temperature,
    }

    if args.mode == "tool":
        request["tools"] = [build_openai_tool(strict=args.strict_tool)]
        request["tool_choice"] = map_chat_tool_choice(args.tool_choice)
        request["parallel_tool_calls"] = not args.disable_parallel_tool_use
    elif args.chat_response_format == "json_object":
        request["response_format"] = {"type": "json_object"}

    extra_body: dict[str, Any] = {}
    thinking = build_thinking_config(
        args.thinking,
        budget_tokens=args.think_budget,
        display=args.thinking_display,
    )
    if thinking is not None:
        extra_body["thinking"] = thinking
    if args.thinking == "adaptive":
        extra_body["output_config"] = {"effort": args.effort}
    if extra_body:
        request["extra_body"] = extra_body
    return request


def redact_request(request: dict[str, Any]) -> dict[str, Any]:
    """Keep the request visible without dumping very long prompt bodies."""
    redacted = to_jsonable(request)
    messages = redacted.get("messages")
    if isinstance(messages, list):
        for message in messages:
            content = message.get("content")
            if isinstance(content, str) and len(content) > 500:
                message["content"] = content[:497] + "..."
    system = redacted.get("system")
    if isinstance(system, str) and len(system) > 500:
        redacted["system"] = system[:497] + "..."
    return redacted


def save_results(results: list[dict[str, Any]], save_dir: Path) -> None:
    save_dir.mkdir(parents=True, exist_ok=True)
    timestamp = time.strftime("%Y%m%d-%H%M%S")
    out_path = save_dir / f"proxy_probe_{timestamp}.json"
    out_path.write_text(
        json.dumps(results, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"\nSaved raw probe output to {out_path}")


def _default_chat_base_url(anthropic_base_url: str) -> str:
    base = anthropic_base_url.rstrip("/")
    if base.endswith("/v1"):
        return base + "/"
    return base + "/v1/"


if __name__ == "__main__":
    raise SystemExit(main())
