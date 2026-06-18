from __future__ import annotations

from src.brain.evolution_engine import _is_transient
from src.brain.proxy_compat import (
    map_anthropic_tool_choice,
    map_chat_tool_choice,
    summarize_anthropic_message,
    summarize_chat_completion,
    summarize_chat_stream,
)


class _Usage:
    input_tokens = 123
    output_tokens = 45


class _TextBlock:
    type = "text"

    def __init__(self, text: str) -> None:
        self.text = text


class _ToolBlock:
    type = "tool_use"

    def __init__(self, name: str) -> None:
        self.name = name


class _Message:
    def __init__(self, content, stop_reason: str) -> None:
        self.content = content
        self.stop_reason = stop_reason
        self.usage = _Usage()


class _Function:
    def __init__(self, name: str, arguments: str) -> None:
        self.name = name
        self.arguments = arguments


class _ToolCall:
    def __init__(self, name: str, arguments: str) -> None:
        self.function = _Function(name, arguments)


class _Choice:
    def __init__(self, content: str, tool_calls, finish_reason: str) -> None:
        self.message = type("Message", (), {"content": content, "tool_calls": tool_calls})()
        self.finish_reason = finish_reason


class _Completion:
    def __init__(self, content: str, tool_calls, finish_reason: str) -> None:
        self.choices = [_Choice(content, tool_calls, finish_reason)]
        self.usage = type("Usage", (), {"prompt_tokens": 100, "completion_tokens": 50})()


class _ChunkChoice:
    def __init__(self, delta, finish_reason=None) -> None:
        self.delta = delta
        self.finish_reason = finish_reason


class _Chunk:
    def __init__(self, delta, finish_reason=None) -> None:
        self.choices = [_ChunkChoice(delta, finish_reason)]


def test_map_anthropic_tool_choice_any_can_disable_parallel():
    result = map_anthropic_tool_choice("any", disable_parallel_tool_use=True)
    assert result == {"type": "any", "disable_parallel_tool_use": True}


def test_map_chat_tool_choice_tool_uses_function_name():
    result = map_chat_tool_choice("tool")
    assert result == {"type": "function", "function": {"name": "emit_decision"}}


def test_summarize_anthropic_message_detects_proxy_like_strip():
    response = _Message(
        content=[_TextBlock("<thinking>hidden</thinking>\nNeed to act now.")],
        stop_reason="tool_use",
    )
    summary = summarize_anthropic_message(response)
    assert summary["proxy_stripped_like"] is True
    assert summary["thinking_tags_in_text"] is True


def test_summarize_anthropic_message_collects_tool_names():
    response = _Message(
        content=[_TextBlock("I will use a tool."), _ToolBlock("emit_decision")],
        stop_reason="tool_use",
    )
    summary = summarize_anthropic_message(response)
    assert summary["tool_use_count"] == 1
    assert summary["tool_use_names"] == ["emit_decision"]


def test_summarize_chat_completion_collects_tool_calls():
    response = _Completion(
        content="",
        tool_calls=[_ToolCall("emit_decision", '{"action":"proceed"}')],
        finish_reason="tool_calls",
    )
    summary = summarize_chat_completion(response)
    assert summary["tool_call_count"] == 1
    assert summary["tool_call_names"] == ["emit_decision"]
    assert summary["finish_reason"] == "tool_calls"


def test_summarize_chat_stream_reassembles_partial_tool_args():
    delta1 = type(
        "Delta",
        (),
        {
            "content": "",
            "tool_calls": [
                type(
                    "ToolDelta",
                    (),
                    {
                        "index": 0,
                        "function": type(
                            "FunctionDelta",
                            (),
                            {"name": "emit_decision", "arguments": '{"action":"pro'},
                        )(),
                    },
                )()
            ],
        },
    )()
    delta2 = type(
        "Delta",
        (),
        {
            "content": "",
            "tool_calls": [
                type(
                    "ToolDelta",
                    (),
                    {
                        "index": 0,
                        "function": type(
                            "FunctionDelta",
                            (),
                            {"name": "", "arguments": 'ceed","option_index":-1}'},
                        )(),
                    },
                )()
            ],
        },
    )()
    chunks = [_Chunk(delta1), _Chunk(delta2, finish_reason="tool_calls")]
    summary = summarize_chat_stream(chunks)
    assert summary["tool_call_count"] == 1
    assert summary["tool_call_names"] == ["emit_decision"]
    assert '"option_index":-1' in summary["tool_args_preview"]
    assert summary["finish_reason"] == "tool_calls"

# ── Evolution retry helper ─────────────────────────────────────


class TestIsTransient:
    def test_502_is_transient(self):
        assert _is_transient("Error code: 502 - upstream failed") is True

    def test_503_is_transient(self):
        assert _is_transient("Error code: 503 - service unavailable") is True

    def test_timeout_is_transient(self):
        assert _is_transient("Request timed out or interrupted") is True

    def test_504_is_transient(self):
        assert _is_transient("Error code: 504 - gateway timeout") is True

    def test_524_is_transient(self):
        assert _is_transient("Error code: 524 - A timeout occurred") is True

    def test_upstream_is_transient(self):
        assert _is_transient("Upstream request failed after retries") is True

    def test_connection_is_transient(self):
        assert _is_transient("Connection reset by peer") is True

    def test_deadline_exceeded_is_transient(self):
        assert _is_transient("rpc deadline exceeded while waiting for upstream") is True

    def test_400_not_transient(self):
        assert _is_transient("Error code: 400 - ValidationException") is False

    def test_schema_not_transient(self):
        assert _is_transient("JSON schema is invalid") is False
