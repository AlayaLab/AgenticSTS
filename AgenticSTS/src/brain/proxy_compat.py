"""Helpers for probing proxy compatibility across Claude API variants."""

from __future__ import annotations

from typing import Any

DEFAULT_TOOL_NAME = "emit_decision"


def build_decision_schema() -> dict[str, Any]:
    """Return a compact schema shared by tool and JSON-output probes."""
    return {
        "type": "object",
        "properties": {
            "action": {
                "type": "string",
                "description": "Chosen action name.",
            },
            "option_index": {
                "type": "integer",
                "description": "Index for actions that require a choice; use -1 when unused.",
            },
            "reasoning": {
                "type": "string",
                "description": "One short sentence explaining the choice.",
            },
        },
        "required": ["action", "option_index", "reasoning"],
        "additionalProperties": False,
    }


def build_anthropic_tool(
    *,
    tool_name: str = DEFAULT_TOOL_NAME,
    strict: bool = False,
    eager_input_streaming: bool = False,
) -> dict[str, Any]:
    """Build a simple Anthropic tool for structured-decision probes."""
    tool: dict[str, Any] = {
        "name": tool_name,
        "description": (
            "Return the final decision as structured data. "
            "Do not explain outside the tool call."
        ),
        "input_schema": build_decision_schema(),
    }
    if strict:
        tool["strict"] = True
    if eager_input_streaming:
        tool["eager_input_streaming"] = True
    return tool


def build_openai_tool(
    *,
    tool_name: str = DEFAULT_TOOL_NAME,
    strict: bool = False,
) -> dict[str, Any]:
    """Build the OpenAI-compatible equivalent of :func:`build_anthropic_tool`."""
    function_def: dict[str, Any] = {
        "name": tool_name,
        "description": (
            "Return the final decision as structured data. "
            "Do not explain outside the tool call."
        ),
        "parameters": build_decision_schema(),
    }
    if strict:
        function_def["strict"] = True
    return {
        "type": "function",
        "function": function_def,
    }


def build_json_output_format() -> dict[str, Any]:
    """Build a native Claude structured-output config fragment."""
    return {
        "type": "json_schema",
        "schema": build_decision_schema(),
    }


def map_anthropic_tool_choice(
    mode: str,
    *,
    tool_name: str = DEFAULT_TOOL_NAME,
    disable_parallel_tool_use: bool = False,
) -> dict[str, Any]:
    """Map a friendly CLI mode to Anthropic ``tool_choice``."""
    if mode == "auto":
        return {"type": "auto"}
    if mode == "any":
        result: dict[str, Any] = {"type": "any"}
        if disable_parallel_tool_use:
            result["disable_parallel_tool_use"] = True
        return result
    if mode == "tool":
        result = {"type": "tool", "name": tool_name}
        if disable_parallel_tool_use:
            result["disable_parallel_tool_use"] = True
        return result
    if mode == "none":
        return {"type": "none"}
    raise ValueError(f"Unsupported Anthropic tool_choice mode: {mode}")


def map_chat_tool_choice(
    mode: str,
    *,
    tool_name: str = DEFAULT_TOOL_NAME,
) -> str | dict[str, Any]:
    """Map a friendly CLI mode to OpenAI-compatible ``tool_choice``."""
    if mode == "auto":
        return "auto"
    if mode == "any":
        return "required"
    if mode == "tool":
        return {"type": "function", "function": {"name": tool_name}}
    if mode == "none":
        return "none"
    raise ValueError(f"Unsupported chat/completions tool_choice mode: {mode}")


def build_thinking_config(
    mode: str,
    *,
    budget_tokens: int,
    display: str,
) -> dict[str, Any] | None:
    """Build an Anthropic thinking config for messages or compat calls."""
    if mode == "off":
        return None
    if mode == "adaptive":
        result: dict[str, Any] = {"type": "adaptive"}
    elif mode == "enabled":
        result = {"type": "enabled", "budget_tokens": budget_tokens}
    else:
        raise ValueError(f"Unsupported thinking mode: {mode}")

    if display != "default":
        result["display"] = display
    return result


def merge_output_config(
    *,
    effort: str = "",
    json_format: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    """Merge optional output-config fragments into one dict."""
    result: dict[str, Any] = {}
    if effort:
        result["effort"] = effort
    if json_format is not None:
        result["format"] = json_format
    return result or None


def to_jsonable(value: Any) -> Any:
    """Best-effort conversion for SDK objects when saving probe results."""
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): to_jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [to_jsonable(item) for item in value]
    if hasattr(value, "model_dump"):
        return to_jsonable(value.model_dump())
    if hasattr(value, "to_dict"):
        return to_jsonable(value.to_dict())
    if hasattr(value, "__dict__"):
        return to_jsonable({
            key: item for key, item in vars(value).items() if not key.startswith("_")
        })
    return repr(value)


def summarize_anthropic_message(response: Any) -> dict[str, Any]:
    """Summarize a Messages API response in a proxy-debug-friendly format."""
    content = list(getattr(response, "content", []) or [])
    text_blocks: list[str] = []
    tool_names: list[str] = []
    block_types: list[str] = []
    thinking_count = 0

    for block in content:
        block_type = _block_type(block)
        block_types.append(block_type)
        if block_type == "text":
            text = _block_text(block)
            if text:
                text_blocks.append(text)
        elif block_type == "tool_use":
            name = _block_attr(block, "name")
            if isinstance(name, str) and name:
                tool_names.append(name)
        elif block_type == "thinking":
            thinking_count += 1

    all_text = "\n\n".join(text_blocks)
    usage = getattr(response, "usage", None)
    input_tokens = getattr(usage, "input_tokens", None)
    output_tokens = getattr(usage, "output_tokens", None)

    return {
        "stop_reason": getattr(response, "stop_reason", None),
        "block_types": block_types,
        "tool_use_count": len(tool_names),
        "tool_use_names": tool_names,
        "thinking_count": thinking_count,
        "text_block_count": len(text_blocks),
        "text_preview": _preview(all_text),
        "thinking_tags_in_text": "<thinking>" in all_text,
        "proxy_stripped_like": (
            getattr(response, "stop_reason", None) == "tool_use"
            and not tool_names
        ),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
    }


def summarize_anthropic_stream(events: list[Any]) -> dict[str, Any]:
    """Summarize Anthropic streaming events."""
    event_types: list[str] = []
    block_start_types: list[str] = []
    delta_types: list[str] = []
    text_fragments: list[str] = []
    tool_json_fragments: list[str] = []

    for event in events:
        event_type = _block_attr(event, "type") or type(event).__name__
        event_types.append(str(event_type))

        if event_type == "content_block_start":
            block = _block_attr(event, "content_block")
            block_start_types.append(_block_type(block))
        elif event_type == "content_block_delta":
            delta = _block_attr(event, "delta")
            delta_type = _block_attr(delta, "type") or type(delta).__name__
            delta_types.append(str(delta_type))
            if delta_type == "text_delta":
                text = _block_attr(delta, "text")
                if isinstance(text, str) and text:
                    text_fragments.append(text)
            elif delta_type == "input_json_delta":
                partial_json = _block_attr(delta, "partial_json")
                if isinstance(partial_json, str) and partial_json:
                    tool_json_fragments.append(partial_json)

    return {
        "event_types": event_types,
        "content_block_start_types": block_start_types,
        "delta_types": delta_types,
        "text_preview": _preview("".join(text_fragments)),
        "tool_json_preview": _preview("".join(tool_json_fragments)),
        "thinking_delta_seen": "thinking_delta" in delta_types,
        "tool_json_delta_seen": "input_json_delta" in delta_types,
    }


def summarize_chat_completion(response: Any) -> dict[str, Any]:
    """Summarize an OpenAI-compatible chat/completions response."""
    choice = _first_choice(response)
    message = _block_attr(choice, "message")
    content = _block_attr(message, "content")
    if not isinstance(content, str):
        content = ""

    tool_calls = list(_block_attr(message, "tool_calls") or [])
    tool_names: list[str] = []
    tool_args: list[str] = []
    for tool_call in tool_calls:
        function = _block_attr(tool_call, "function")
        name = _block_attr(function, "name")
        if isinstance(name, str) and name:
            tool_names.append(name)
        arguments = _block_attr(function, "arguments")
        if isinstance(arguments, str) and arguments:
            tool_args.append(arguments)

    usage = _block_attr(response, "usage")
    return {
        "finish_reason": _block_attr(choice, "finish_reason"),
        "content_preview": _preview(content),
        "tool_call_count": len(tool_calls),
        "tool_call_names": tool_names,
        "tool_args_preview": _preview("\n".join(tool_args)),
        "thinking_tags_in_content": "<thinking>" in content,
        "prompt_tokens": _block_attr(usage, "prompt_tokens"),
        "completion_tokens": _block_attr(usage, "completion_tokens"),
    }


def summarize_chat_stream(chunks: list[Any]) -> dict[str, Any]:
    """Summarize OpenAI-compatible chat/completions streaming chunks."""
    content_parts: list[str] = []
    tool_calls: dict[int, dict[str, str]] = {}
    finish_reason = None

    for chunk in chunks:
        choice = _first_choice(chunk)
        if choice is None:
            continue
        finish_reason = _block_attr(choice, "finish_reason") or finish_reason
        delta = _block_attr(choice, "delta")
        content = _block_attr(delta, "content")
        if isinstance(content, str) and content:
            content_parts.append(content)

        for tool_delta in list(_block_attr(delta, "tool_calls") or []):
            index = _block_attr(tool_delta, "index")
            if not isinstance(index, int):
                index = 0
            entry = tool_calls.setdefault(index, {"name": "", "arguments": ""})
            function = _block_attr(tool_delta, "function")
            name = _block_attr(function, "name")
            if isinstance(name, str) and name:
                entry["name"] = name
            arguments = _block_attr(function, "arguments")
            if isinstance(arguments, str) and arguments:
                entry["arguments"] += arguments

    return {
        "chunk_count": len(chunks),
        "finish_reason": finish_reason,
        "content_preview": _preview("".join(content_parts)),
        "tool_call_count": len(tool_calls),
        "tool_call_names": [entry["name"] for _, entry in sorted(tool_calls.items())],
        "tool_args_preview": _preview(
            "\n".join(entry["arguments"] for _, entry in sorted(tool_calls.items()))
        ),
        "thinking_tags_in_content": "<thinking>" in "".join(content_parts),
    }


def _preview(text: str, *, limit: int = 240) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 3] + "..."


def _block_type(block: Any) -> str:
    block_type = _block_attr(block, "type")
    if isinstance(block_type, str) and block_type:
        return block_type
    return type(block).__name__


def _block_text(block: Any) -> str:
    text = _block_attr(block, "text")
    if isinstance(text, str):
        return text
    return ""


def _block_attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _first_choice(response: Any) -> Any:
    choices = list(_block_attr(response, "choices") or [])
    if not choices:
        return None
    return choices[0]
