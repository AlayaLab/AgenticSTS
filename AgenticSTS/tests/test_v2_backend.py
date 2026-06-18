from __future__ import annotations

import builtins
from types import SimpleNamespace
from unittest.mock import MagicMock

import httpx
import pytest

import config
from src.brain.v2_backend import UnparseableLLMResponse, V2Backend


@pytest.fixture()
def _no_family_keys(monkeypatch):
    """Neutralize per-model-family API keys so tests control relay routing.

    Clears both module-level constants (legacy) and env vars — ``config.
    get_model_family_relay()`` reads from ``os.environ`` directly since the
    registry refactor, so clearing attrs alone is not enough.
    """
    monkeypatch.setattr(config, "GPT_API_KEY", "")
    monkeypatch.setattr(config, "GPT_BASE_URL", "")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "")
    monkeypatch.setattr(config, "GEMINI_BASE_URL", "")
    monkeypatch.setattr(config, "QWEN_API_KEY", "")
    monkeypatch.setattr(config, "QWEN_BASE_URL", "")
    for _fam in ("GPT", "GEMINI", "QWEN", "CLAUDE"):
        monkeypatch.delenv(f"STS2_{_fam}_API_KEY", raising=False)
        monkeypatch.delenv(f"STS2_{_fam}_BASE_URL", raising=False)


class _FakeStream:
    def __init__(self, events):
        self._events = list(events)
        self.closed = False

    def __iter__(self):
        yield from self._events

    def close(self):
        self.closed = True


class _FakeHTTPStreamResponse:
    def __init__(self, lines):
        self._lines = list(lines)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        yield from self._lines


class _FakeHTTPResponse:
    def __init__(self, payload):
        self._payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self._payload


def _raise_http_status(method: str, url: str, status_code: int, text: str) -> None:
    request = httpx.Request(method, url)
    response = httpx.Response(status_code, request=request, text=text)
    raise httpx.HTTPStatusError(
        f"{status_code} error",
        request=request,
        response=response,
    )


def _make_response(stop_reason: str = "tool_use"):
    return SimpleNamespace(
        content=[],
        stop_reason=stop_reason,
        usage=SimpleNamespace(
            input_tokens=10,
            output_tokens=5,
            cache_read_input_tokens=0,
            cache_creation_input_tokens=0,
        ),
    )


def _make_backend(fake_client) -> V2Backend:
    backend = object.__new__(V2Backend)
    backend._anthropic = SimpleNamespace(
        RateLimitError=RuntimeError,
        APIError=RuntimeError,
    )
    backend._client = fake_client
    backend._opus_client = object()
    backend._openai_client = None
    backend._openai_clients = {}
    backend._openai_relay_fail_until = {}
    backend._preferred_openai_relay = ""
    backend._preferred_openai_relays = {}
    backend._last_transport_target = ""
    backend._default_model = "claude-sonnet-4-6"
    backend._last_cache_read = 0
    backend._last_cache_creation = 0
    backend._last_prefix_hash = ""
    backend._warned_cache_ignored = False
    backend._last_provider_has_visible_thinking = False
    return backend


def _make_raw_events(response, *events):
    return [
        SimpleNamespace(type="message_start", message=response),
        *events,
        SimpleNamespace(type="message_stop"),
    ]


def test_call_uses_stream_for_tool_calls_over_proxy(monkeypatch):
    response = _make_response()
    raw_stream = _FakeStream(_make_raw_events(response))
    fake_messages = SimpleNamespace(
        create=MagicMock(
            side_effect=lambda **kwargs: raw_stream if kwargs.get("stream") else response
        ),
        stream=MagicMock(return_value=raw_stream),
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    backend = _make_backend(fake_client)

    monkeypatch.setattr(config, "ANTHROPIC_BASE_URL", "https://proxy.example.com")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        think=True,
        effort="medium",
        tools=[{"name": "emit_decision"}],
        tool_choice={"type": "auto"},
        max_tokens=32,
    )

    assert result is response
    fake_messages.create.assert_called_once()
    _, kwargs = fake_messages.create.call_args
    assert kwargs["stream"] is True
    assert "Put any explanation or analysis inside the tool input fields only" in kwargs["system"]
    fake_messages.stream.assert_not_called()


def test_call_reassembles_thinking_text_and_tool_use_from_raw_stream(monkeypatch):
    response = _make_response(stop_reason=None)
    response.content = []
    raw_stream = _FakeStream(
        _make_raw_events(
            response,
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=SimpleNamespace(type="thinking", thinking="", signature=""),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="thinking_delta", thinking="Need a safe line. "),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="signature_delta", signature="sig_123"),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=1,
                content_block=SimpleNamespace(type="text", text="", citations=None),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(type="text_delta", text="Choosing the direct action."),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=2,
                content_block=SimpleNamespace(
                    type="tool_use",
                    id="toolu_123",
                    name="emit_decision",
                    input={},
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=2,
                delta=SimpleNamespace(type="input_json_delta", partial_json='{"action":"pro'),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=2,
                delta=SimpleNamespace(
                    type="input_json_delta",
                    partial_json='ceed","option_index":-1,"reasoning":"safe line"}',
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=0,
                delta=SimpleNamespace(type="thinking_delta", thinking="Confirm and commit."),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(
                    stop_reason="tool_use",
                    stop_sequence=None,
                    container=None,
                ),
                usage=SimpleNamespace(
                    input_tokens=111,
                    output_tokens=42,
                    cache_read_input_tokens=7,
                    cache_creation_input_tokens=3,
                    server_tool_use=None,
                ),
            ),
        )
    )
    fake_messages = SimpleNamespace(
        create=MagicMock(
            side_effect=lambda **kwargs: raw_stream if kwargs.get("stream") else response
        ),
        stream=MagicMock(),
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    backend = _make_backend(fake_client)

    monkeypatch.setattr(config, "ANTHROPIC_BASE_URL", "https://proxy.example.com")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        tools=[{"name": "emit_decision"}],
        tool_choice={"type": "auto"},
        think=True,
        effort="medium",
        max_tokens=32,
    )

    assert result is response
    assert [block.type for block in result.content] == ["thinking", "text", "tool_use"]
    assert result.content[0].thinking == "Need a safe line. Confirm and commit."
    assert result.content[0].signature == "sig_123"
    assert result.content[1].text == "Choosing the direct action."
    assert result.content[2].name == "emit_decision"
    assert result.content[2].input == {
        "action": "proceed",
        "option_index": -1,
        "reasoning": "safe line",
    }
    assert result.stop_reason == "tool_use"
    assert result.usage.input_tokens == 111
    assert result.usage.output_tokens == 42
    assert result.usage.cache_read_input_tokens == 7
    assert result.usage.cache_creation_input_tokens == 3


def test_call_strips_empty_text_block_before_tool_use(monkeypatch):
    response = _make_response(stop_reason=None)
    response.content = []
    raw_stream = _FakeStream(
        _make_raw_events(
            response,
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=SimpleNamespace(type="text", text="", citations=None),
            ),
            SimpleNamespace(
                type="content_block_start",
                index=1,
                content_block=SimpleNamespace(
                    type="tool_use",
                    id="toolu_456",
                    name="emit_decision",
                    input={},
                ),
            ),
            SimpleNamespace(
                type="content_block_delta",
                index=1,
                delta=SimpleNamespace(
                    type="input_json_delta",
                    partial_json='{"action":"proceed","option_index":-1,"reasoning":"safe"}',
                ),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(
                    stop_reason="tool_use",
                    stop_sequence=None,
                    container=None,
                ),
                usage=SimpleNamespace(
                    input_tokens=20,
                    output_tokens=10,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                    server_tool_use=None,
                ),
            ),
        )
    )
    fake_messages = SimpleNamespace(
        create=MagicMock(
            side_effect=lambda **kwargs: raw_stream if kwargs.get("stream") else response
        ),
        stream=MagicMock(),
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    backend = _make_backend(fake_client)

    monkeypatch.setattr(config, "ANTHROPIC_BASE_URL", "https://proxy.example.com")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        think=True,
        effort="medium",
        tools=[{"name": "emit_decision"}],
        tool_choice={"type": "auto"},
        max_tokens=32,
    )

    assert [block.type for block in result.content] == ["tool_use"]
    assert result.content[0].input["action"] == "proceed"


def test_call_uses_create_without_tools(monkeypatch):
    response = _make_response(stop_reason="end_turn")
    fake_messages = SimpleNamespace(
        create=MagicMock(return_value=response),
        stream=MagicMock(return_value=_FakeStream(_make_raw_events(response))),
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    backend = _make_backend(fake_client)

    monkeypatch.setattr(config, "ANTHROPIC_BASE_URL", "https://proxy.example.com")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        max_tokens=32,
    )

    assert result is response
    fake_messages.create.assert_called_once()
    _, kwargs = fake_messages.create.call_args
    assert "tool input fields only" not in kwargs["system"]
    fake_messages.stream.assert_not_called()


def test_call_reports_first_chunk_for_raw_stream(monkeypatch):
    response = _make_response(stop_reason=None)
    response.content = []
    raw_stream = _FakeStream(
        _make_raw_events(
            response,
            SimpleNamespace(
                type="content_block_start",
                index=0,
                content_block=SimpleNamespace(type="text", text="", citations=None),
            ),
            SimpleNamespace(
                type="message_delta",
                delta=SimpleNamespace(stop_reason="end_turn", stop_sequence=None, container=None),
                usage=SimpleNamespace(
                    input_tokens=10,
                    output_tokens=5,
                    cache_read_input_tokens=0,
                    cache_creation_input_tokens=0,
                    server_tool_use=None,
                ),
            ),
        )
    )
    fake_messages = SimpleNamespace(
        create=MagicMock(
            side_effect=lambda **kwargs: raw_stream if kwargs.get("stream") else response
        ),
        stream=MagicMock(),
    )
    fake_client = SimpleNamespace(messages=fake_messages)
    backend = _make_backend(fake_client)
    seen = []

    monkeypatch.setattr(config, "ANTHROPIC_BASE_URL", "https://proxy.example.com")

    backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="anthropic",
        think=True,
        effort="medium",
        tools=[{"name": "emit_decision"}],
        tool_choice={"type": "auto"},
        on_first_chunk=seen.append,
    )

    assert seen == [{"transport": "anthropic_stream", "event_type": "content_block_start"}]


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_reassembles_streamed_tool_calls(monkeypatch):
    stream_lines = [
        (
            'data: {"choices":[{"delta":{"content":"<think>check sequencing</think>\\n"},'
            '"finish_reason":null}]}'
        ),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
            '"function":{"name":"emit_decision"}}]}}]}'
        ),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":'
            '{"arguments":"{\\"action\\":\\"pro"}}]}}]}'
        ),
        (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"function":{"arguments":'
            '"ceed\\",\\"option_index\\":-1,\\"reasoning\\":\\"safe line\\"}"}}]},'
            '"finish_reason":"tool_calls"}],"usage":{"prompt_tokens":21,"completion_tokens":9}}'
        ),
        "data: [DONE]",
    ]
    fake_http = SimpleNamespace(
        stream=MagicMock(return_value=_FakeHTTPStreamResponse(stream_lines)),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="kimi-k2.5",
        tools=[{"name": "emit_decision", "input_schema": {"type": "object"}}],
        tool_choice={"type": "auto"},
        max_tokens=64,
    )

    # <think> tags are stripped from content, leaving only the tool_use block
    assert [block.type for block in result.content] == ["tool_use"]
    assert result.content[0].id == "call_1"
    assert result.content[0].name == "emit_decision"
    assert result.content[0].input == {
        "action": "proceed",
        "option_index": -1,
        "reasoning": "safe line",
    }
    # Reasoning captured in _reasoning_content attribute
    assert "check sequencing" in getattr(result, "_reasoning_content", "")
    assert result.stop_reason == "tool_use"
    assert result.usage.input_tokens == 21
    assert result.usage.output_tokens == 9

    fake_http.stream.assert_called_once()
    _, kwargs = fake_http.stream.call_args
    assert kwargs["json"]["tool_choice"] == "auto"
    assert kwargs["json"]["messages"][0]["role"] == "system"


def test_call_openai_compatible_reports_first_chunk(monkeypatch):
    stream_lines = [
        'data: {"choices":[{"delta":{"content":"hello"},"finish_reason":null}]}',
        "data: [DONE]",
    ]
    fake_http = SimpleNamespace(
        stream=MagicMock(return_value=_FakeHTTPStreamResponse(stream_lines)),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http
    seen = []

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="kimi-k2.5",
        tools=[{"name": "emit_decision", "input_schema": {"type": "object"}}],
        tool_choice={"type": "auto"},
        on_first_chunk=seen.append,
    )

    assert seen
    assert seen[0]["transport"] == "openai_stream"


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_gpt5_sets_reasoning_effort(monkeypatch):
    fake_http = SimpleNamespace(
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 18, "completion_tokens": 6},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gpt-5.4",
        think=True,
        effort="high",
        max_tokens=64,
    )

    assert result.content[0].text == "done"
    fake_http.post.assert_called_once()
    _, kwargs = fake_http.post.call_args
    payload = kwargs["json"]
    assert payload["reasoning_effort"] == "high"
    assert payload["max_tokens"] >= 16000


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_gpt5_thinking_alias_can_disable_reasoning(monkeypatch):
    fake_http = SimpleNamespace(
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gpt-5.4-thinking",
        think=False,
    )

    fake_http.post.assert_called_once()
    _, kwargs = fake_http.post.call_args
    payload = kwargs["json"]
    assert "reasoning_effort" not in payload  # "none" means reasoning disabled — key is omitted


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_uses_post_for_gemini_non_tool_requests(monkeypatch):
    """Strategic Gemini calls (non-tool) go through the non-streaming POST
    path. Streaming through the relay added 3x latency and intermittently
    returned empty responses, so it is now reserved for tool-use calls.
    """
    fake_http = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "done"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 2},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gemini-3.1-pro-preview",
        think=True,
        effort="high",
    )

    assert result.content[0].text == "done"
    assert result.stop_reason == "end_turn"
    fake_http.post.assert_called_once()
    fake_http.stream.assert_not_called()
    _, kwargs = fake_http.post.call_args
    payload = kwargs["json"]
    assert payload.get("stream") is not True
    assert payload["extra_body"]["google"]["thinking_config"]["thinking_level"] == "high"
    # Default off — server still thinks at the requested level, just doesn't
    # stream thoughts, so the proxy never has reasoning_content + content
    # interleaving to drop.  Override via STS2_GEMINI_INCLUDE_THOUGHTS=true.
    assert payload["extra_body"]["google"]["thinking_config"]["include_thoughts"] is False


def test_gemini_extra_body_include_thoughts_env_override(monkeypatch):
    """STS2_GEMINI_INCLUDE_THOUGHTS=true flips include_thoughts back on for
    debugging when the user wants to see Gemini's reasoning_content stream."""
    monkeypatch.setenv("STS2_GEMINI_INCLUDE_THOUGHTS", "true")
    body = V2Backend._build_gemini_extra_body(effort="medium", relay_base_url="https://proxy.example.com")
    assert body["google"]["thinking_config"]["include_thoughts"] is True

    monkeypatch.setenv("STS2_GEMINI_INCLUDE_THOUGHTS", "false")
    body = V2Backend._build_gemini_extra_body(effort="medium", relay_base_url="https://proxy.example.com")
    assert body["google"]["thinking_config"]["include_thoughts"] is False

    # Default (env unset) is False.
    monkeypatch.delenv("STS2_GEMINI_INCLUDE_THOUGHTS", raising=False)
    body = V2Backend._build_gemini_extra_body(effort="medium", relay_base_url="https://proxy.example.com")
    assert body["google"]["thinking_config"]["include_thoughts"] is False


def test_call_openai_compatible_post_ok_when_analysis_prose_no_decision(monkeypatch, _no_family_keys):
    """gpt-5.4 non-thinking emits analysis prose with no <decision> tag.
    V2Engine repair turn handles this — backend should not preempt.

    Strategic non-tool calls go through the POST path under the new
    streaming policy. Mock post explicitly so we exercise that path
    rather than letting the call fall through to a bare MagicMock.
    """
    fake_http = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {
                    "message": {"content": "I need more info before deciding."},
                    "finish_reason": "stop",
                },
            ],
            "usage": {"prompt_tokens": 8, "completion_tokens": 6},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http
    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gpt-5.4",  # non-Gemini → no reasoning capture
        think=False,
    )
    fake_http.post.assert_called_once()
    fake_http.stream.assert_not_called()
    assert "<decision>" not in result.content[0].text
    assert "I need more info" in result.content[0].text


def test_call_openai_compatible_post_does_not_raise_when_completely_empty(monkeypatch, _no_family_keys):
    """An empty response body (no content, no completion tokens) should not
    raise — caller handles via repair turn. Guards against treating slow
    relay drains as hard failures.
    """
    fake_http = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": ""}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 10, "completion_tokens": 0},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http
    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gemini-3.1-pro-preview",
        think=True,
        effort="medium",
    )
    # _make_openai_message returns empty content list when text is empty.
    text = result.content[0].text if result.content else ""
    assert text == ""
    fake_http.post.assert_called_once()
    fake_http.stream.assert_not_called()


def test_call_openai_compatible_translates_tool_history(monkeypatch):
    fake_http = SimpleNamespace(
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 30, "completion_tokens": 10},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = fake_http

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    backend.call(
        system="sys",
        messages=[
            {"role": "user", "content": "look up map"},
            {"role": "assistant", "content": [
                SimpleNamespace(
                    type="tool_use",
                    id="tool_1",
                    name="search_map",
                    input={"floor": 5},
                ),
            ]},
            {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": "tool_1", "content": "safe path"},
            ]},
        ],
        provider="openai_compatible",
        model="kimi-k2.5",
    )

    fake_http.post.assert_called_once()
    _, kwargs = fake_http.post.call_args
    payload_messages = kwargs["json"]["messages"]
    assert payload_messages[0] == {"role": "system", "content": "sys"}
    assert payload_messages[1] == {"role": "user", "content": "look up map"}
    assert payload_messages[2]["role"] == "assistant"
    assert payload_messages[2]["tool_calls"][0]["id"] == "tool_1"
    assert payload_messages[2]["tool_calls"][0]["function"]["name"] == "search_map"
    assert payload_messages[3] == {
        "role": "tool",
        "tool_call_id": "tool_1",
        "content": "safe path",
    }


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_fails_over_to_next_relay_on_upstream_quota(monkeypatch):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            429,
            "status_code=429, Resource has been exhausted (e.g. check quota).",
        )),
    )
    good_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "done"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "bad|https://bad-relay.example/v1|sk-bad;good|https://good-relay.example/v1|sk-good",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: bad_client if api_key == "sk-bad" else good_client),
    )
    # Ensure non-zero cooldown so the failing relay key is recorded in _openai_relay_fail_until
    monkeypatch.setattr(config, "OPENAI_COMPAT_FAILOVER_COOLDOWN_SEC", 30.0)

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gemini-3.1-pro-preview",
        think=True,
    )

    assert result.content[0].text == "done"
    assert bad_client.post.call_count == 1
    assert good_client.post.call_count == 1
    assert bad_client.stream.call_count == 0
    assert good_client.stream.call_count == 0
    assert backend._last_transport_target == "good"
    assert any(
        key.startswith("bad|https://bad-relay.example/v1")
        for key in backend._openai_relay_fail_until
    )


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_does_not_fail_over_on_generic_400(monkeypatch):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            400,
            '{"error":"invalid request body"}',
        )),
    )
    good_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "should not be used"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "bad|https://bad-relay.example/v1|sk-bad;good|https://good-relay.example/v1|sk-good",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: bad_client if api_key == "sk-bad" else good_client),
    )

    try:
        backend.call(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            provider="openai_compatible",
            model="gemini-3.1-pro-preview",
            think=True,
        )
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 400
    else:
        raise AssertionError("Expected HTTPStatusError for generic 400 request failure")

    assert bad_client.post.call_count == 1
    assert good_client.post.call_count == 0
    assert bad_client.stream.call_count == 0
    assert good_client.stream.call_count == 0


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_does_not_fail_over_on_ambiguous_consumer_400(monkeypatch):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            400,
            '{"error":"invalid consumer request body"}',
        )),
    )
    good_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "should not be used"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "bad|https://bad-relay.example/v1|sk-bad;good|https://good-relay.example/v1|sk-good",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: bad_client if api_key == "sk-bad" else good_client),
    )

    try:
        backend.call(
            system="sys",
            messages=[{"role": "user", "content": "hi"}],
            provider="openai_compatible",
            model="gemini-3.1-pro-preview",
            think=True,
        )
    except httpx.HTTPStatusError as exc:
        assert exc.response.status_code == 400
    else:
        raise AssertionError("Expected HTTPStatusError for ambiguous 400 request failure")

    assert bad_client.post.call_count == 1
    assert good_client.post.call_count == 0
    assert bad_client.stream.call_count == 0
    assert good_client.stream.call_count == 0
    assert backend._openai_relay_fail_until == {}


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_fails_over_on_billing_400(monkeypatch):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            400,
            '{"error":"See plan and billing details for this consumer."}',
        )),
    )
    good_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "done"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "bad|https://bad-relay.example/v1|sk-bad;good|https://good-relay.example/v1|sk-good",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: bad_client if api_key == "sk-bad" else good_client),
    )

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gemini-3.1-pro-preview",
        think=True,
    )

    assert result.content[0].text == "done"
    assert bad_client.post.call_count == 1
    assert good_client.post.call_count == 1
    assert bad_client.stream.call_count == 0
    assert good_client.stream.call_count == 0


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_fails_over_on_upstream_project_400(monkeypatch):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            400,
            (
                '{"error":{"message":"Invalid project resource name '
                'projects/projects/random-358d005f/locations/global",'
                '"type":"upstream_error","param":"","code":400}}'
            ),
        )),
    )
    good_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [
                {"message": {"content": "done"}, "finish_reason": "stop"},
            ],
            "usage": {"prompt_tokens": 12, "completion_tokens": 4},
        })),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "bad|https://bad-relay.example/v1|sk-bad;good|https://good-relay.example/v1|sk-good",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: bad_client if api_key == "sk-bad" else good_client),
    )

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gemini-3.1-pro-preview",
        think=True,
    )

    assert result.content[0].text == "done"
    assert bad_client.post.call_count == 1
    assert good_client.post.call_count == 1
    assert bad_client.stream.call_count == 0
    assert good_client.stream.call_count == 0


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_logs_http_error_body(monkeypatch, caplog):
    bad_client = SimpleNamespace(
        stream=MagicMock(),
        post=MagicMock(side_effect=lambda url, json: _raise_http_status(
            "POST",
            url,
            400,
            '{"error":"invalid request body","detail":"tool schema mismatch"}',
        )),
    )
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._openai_client = bad_client

    monkeypatch.setattr(config, "OPENAI_COMPAT_BASE_URL", "https://relay.example/v1")

    with caplog.at_level("ERROR"):
        try:
            backend.call(
                system="sys",
                messages=[{"role": "user", "content": "hi"}],
                provider="openai_compatible",
                model="gemini-3.1-pro-preview",
                think=True,
            )
        except httpx.HTTPStatusError as exc:
            assert exc.response.status_code == 400
        else:
            raise AssertionError("Expected HTTPStatusError for logged 400 request failure")

    assert bad_client.post.call_count == 1
    assert bad_client.stream.call_count == 0
    assert "invalid request body" in caplog.text
    assert "tool schema mismatch" in caplog.text


def test_backend_init_does_not_import_anthropic_until_needed(monkeypatch):
    real_import = builtins.__import__
    seen: list[str] = []

    def guarded_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "anthropic":
            seen.append(name)
            raise AssertionError("anthropic import should be lazy")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    backend = V2Backend()

    assert backend._anthropic is None
    assert backend._client is None
    assert backend._opus_client is None
    assert seen == []


@pytest.mark.usefixtures("_no_family_keys")
def test_call_openai_compatible_postrun_profile_uses_postrun_relay(monkeypatch):
    gameplay_client = SimpleNamespace(post=MagicMock(), stream=MagicMock())
    postrun_client = SimpleNamespace(
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [{"message": {"content": "postrun ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 3},
        })),
        stream=MagicMock(),
    )
    backend = _make_backend(SimpleNamespace(messages=None))

    monkeypatch.setenv("STS2_OPENAI_COMPAT_RELAYS", "game|https://game.example/v1|sk-game")
    monkeypatch.setenv(
        "STS2_POSTRUN_OPENAI_COMPAT_RELAYS",
        "post|https://postrun.example/v1|sk-postrun",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(
            lambda *, api_key: gameplay_client if api_key == "sk-game" else postrun_client
        ),
    )

    result = backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gpt-5.4-thinking",
        think=True,
        openai_relay_profile="postrun",
    )

    assert result.content[0].text == "postrun ok"
    assert gameplay_client.post.call_count == 0
    assert postrun_client.post.call_count == 1
    assert backend._last_transport_target == "post"


@pytest.mark.usefixtures("_no_family_keys")
def test_openai_relay_state_is_profile_scoped(monkeypatch):
    postrun_client = SimpleNamespace(
        post=MagicMock(return_value=_FakeHTTPResponse({
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 4, "completion_tokens": 2},
        })),
        stream=MagicMock(),
    )
    # Keys now include an api_key fingerprint so credential rotation
    # invalidates the cached httpx.Client. Pre-seed the gameplay-scoped
    # state with the gameplay relay's key fingerprint (sk-game).
    gameplay_key = "shared|https://shared.example/v1|0758c23d"
    postrun_key = f"postrun|{gameplay_key.rsplit('|', 1)[0]}|4bf899f7"
    backend = _make_backend(SimpleNamespace(messages=None))
    backend._preferred_openai_relay = gameplay_key
    backend._openai_relay_fail_until[gameplay_key] = float("inf")

    monkeypatch.setenv(
        "STS2_OPENAI_COMPAT_RELAYS",
        "shared|https://shared.example/v1|sk-game",
    )
    monkeypatch.setenv(
        "STS2_POSTRUN_OPENAI_COMPAT_RELAYS",
        "shared|https://shared.example/v1|sk-postrun",
    )
    monkeypatch.setattr(
        V2Backend,
        "_make_http_client",
        staticmethod(lambda *, api_key: postrun_client),
    )

    backend.call(
        system="sys",
        messages=[{"role": "user", "content": "hi"}],
        provider="openai_compatible",
        model="gpt-5.4-thinking",
        openai_relay_profile="postrun",
    )

    assert postrun_client.post.call_count == 1
    assert backend._preferred_openai_relay == gameplay_key
    assert backend._preferred_openai_relays["postrun"] == postrun_key
    assert backend._openai_relay_fail_until[gameplay_key] == float("inf")


def test_openai_relay_key_includes_api_key_fingerprint():
    """Rotating an api_key on the same name+base_url must produce a new key.

    This is what lets env-driven credential rotation invalidate the cached
    httpx.Client (which bakes the Authorization header in at construction).
    """
    relay_a = {
        "name": "fam",
        "base_url": "https://relay.example/v1",
        "api_key": "sk-old",
    }
    relay_b = dict(relay_a, api_key="sk-new")

    key_a = V2Backend._openai_relay_key(relay_a)
    key_b = V2Backend._openai_relay_key(relay_b)

    assert key_a != key_b
    # Same api_key still produces the same key (cache hits stay hot).
    assert key_a == V2Backend._openai_relay_key(dict(relay_a))
    # Empty api_key falls back to a stable sentinel rather than crashing.
    assert V2Backend._openai_relay_key({"name": "fam", "base_url": "https://x/v1"}).endswith(
        "|noauth",
    )
