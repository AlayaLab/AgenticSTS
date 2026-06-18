"""V2 LLM backend — returns Anthropic-shaped message objects.

Unlike the V1 AnthropicBackend (in reasoner.py) which extracts text/tool_use
into a (str, float, int) tuple, this backend returns the complete Message.
This enables:
  - Multi-turn conversations (pass assistant messages back as-is)
  - Tool-use agent loops (inspect tool_use blocks, build tool_result responses)
  - Rich stop_reason handling (end_turn vs tool_use)

Configuration is read from config.py (same as V1):
  LLM_API_KEY, ANTHROPIC_BASE_URL, LLM_MODEL, LLM_MAX_TOKENS, LLM_TEMPERATURE
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import threading
import time
from types import SimpleNamespace
from typing import TYPE_CHECKING, Any, Callable

import httpx

import config

if TYPE_CHECKING:
    import anthropic

logger = logging.getLogger(__name__)

# Module-level jiter availability check (used for partial JSON recovery)
try:
    from jiter import from_json as _jiter_from_json

    _JITER_AVAILABLE = True
except ImportError:
    _jiter_from_json = None  # type: ignore[assignment]
    _JITER_AVAILABLE = False

_PROXY_TOOL_REASONING_GUARD = (
    "\n\n## Tool Output Rule\n"
    "- Do not output visible text blocks before or alongside a tool call.\n"
    "- Put any explanation or analysis inside the tool input fields only.\n"
    "- If the decision tool exposes reasoning or analysis fields, fill them in there.\n"
    "- Call exactly one tool when you are ready to commit.\n"
)


class UnparseableLLMResponse(RuntimeError):
    """LLM stream returned a response that won't pass the decision parser.

    Raised by the streaming path when:
      - <decision> opened but never closed (proxy ate finish_reason chunk), or
      - visible content empty despite output tokens (thinking burned them all).

    Classified as HARD by ``LLMRouter.classify_failure`` via the
    ``"unparseable response"`` marker — the message string the raise site
    builds always begins with ``"unparseable response (...)"`` so the
    router's text-marker scan catches it without an isinstance import.
    HARD means: switch model on first occurrence (gemini-pro → flash →
    gpt-5.4) instead of retrying the same model.

    Originally classified as SOFT under the assumption that "same Gemini
    usually succeeds on retry."  Empirically false on proxy.example.com (run
    20260428_024454: 37 unparseable / 685 steps doubled total LLM time vs
    a comparable F48 victory without the detector).  Switching after first
    failure costs 1 extra call instead of 2-3.
    """


class V2Backend:
    """Anthropic backend that returns the full ``anthropic.Message``.

    Features:
      - Extended thinking with per-call ``budget_tokens``
      - Tool use with ``tools`` / ``tool_choice`` parameters
      - Per-call model routing (pass any model string)
      - Rate-limit retry with brief backoff
    """

    def __init__(self) -> None:
        self._anthropic: Any | None = None
        self._client: anthropic.Anthropic | None = None
        self._opus_client: anthropic.Anthropic | None = None

        self._default_model: str = config.LLM_MODEL
        self._openai_client: httpx.Client | None = None
        self._openai_clients: dict[str, httpx.Client] = {}
        self._openai_relay_fail_until: dict[str, float] = {}
        self._preferred_openai_relay: str = ""
        self._preferred_openai_relays: dict[str, str] = {}
        self._last_transport_target: str = ""
        self._last_cache_read: int = 0
        self._last_cache_creation: int = 0
        self._last_prefix_hash: str = ""
        self._warned_cache_ignored: bool = False
        self._last_provider_has_visible_thinking: bool = False

    @staticmethod
    def _make_client(
        _anthropic: Any,
        *,
        api_key: str,
        base_url: str,
        disable_cache: bool,
    ) -> anthropic.Anthropic:
        """Create an Anthropic client with the given credentials."""
        kwargs: dict[str, Any] = {}
        if api_key:
            kwargs["api_key"] = api_key
        if base_url:
            kwargs["base_url"] = base_url
        if disable_cache:
            kwargs["default_headers"] = {
                "Cache-Control": "no-cache",
                "Pragma": "no-cache",
            }
        # 300s timeout — Opus + thinking + large context can take 3-5 min through proxies
        # SDK auto-retries on timeout, wasting tokens on duplicate calls, so be generous
        kwargs["timeout"] = _anthropic.Timeout(timeout=300.0, connect=30.0)
        kwargs["max_retries"] = 1
        return _anthropic.Anthropic(**kwargs)

    @staticmethod
    def _make_http_client(
        *,
        api_key: str,
    ) -> httpx.Client:
        """Create an HTTP client for OpenAI-compatible chat relays."""
        headers = {"Content-Type": "application/json"}
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        return httpx.Client(
            headers=headers,
            timeout=httpx.Timeout(
                connect=30.0,
                read=config.OPENAI_COMPAT_READ_TIMEOUT_SEC,
                write=30.0,
                pool=config.OPENAI_COMPAT_TIMEOUT_SEC,
            ),
            follow_redirects=True,
        )

    @staticmethod
    def _resolve_per_call_timeout(tier: str | None) -> httpx.Timeout | None:
        """Per-tier read timeout override for openai-compatible calls.

        Fast tier returns a tighter ``httpx.Timeout`` (read =
        ``OPENAI_COMPAT_FAST_READ_TIMEOUT_SEC``, default 45s) so a stuck
        upstream connection is killed in seconds instead of inheriting the
        client-level read timeout sized for strategic-tier thinking calls.
        Returns ``None`` for non-fast tiers (use the client default).
        """
        if (tier or "").strip().lower() != "fast":
            return None
        fast_read = config.OPENAI_COMPAT_FAST_READ_TIMEOUT_SEC
        if fast_read <= 0 or fast_read >= config.OPENAI_COMPAT_READ_TIMEOUT_SEC:
            return None
        return httpx.Timeout(
            connect=30.0,
            read=fast_read,
            write=30.0,
            pool=config.OPENAI_COMPAT_TIMEOUT_SEC,
        )

    def _ensure_runtime_state(self) -> None:
        """Populate attributes when tests instantiate via ``object.__new__``."""
        if not hasattr(self, "_anthropic"):
            self._anthropic = None
        if not hasattr(self, "_client"):
            self._client = None
        if not hasattr(self, "_opus_client"):
            self._opus_client = None
        if not hasattr(self, "_openai_client"):
            self._openai_client = None
        if not hasattr(self, "_openai_clients"):
            self._openai_clients = {}
        if not hasattr(self, "_openai_relay_fail_until"):
            self._openai_relay_fail_until = {}
        if not hasattr(self, "_preferred_openai_relay"):
            self._preferred_openai_relay = ""
        if not hasattr(self, "_preferred_openai_relays"):
            self._preferred_openai_relays = {}
        if not hasattr(self, "_last_transport_target"):
            self._last_transport_target = ""
        if not hasattr(self, "_default_model"):
            self._default_model = config.LLM_MODEL
        if not hasattr(self, "_last_cache_read"):
            self._last_cache_read = 0
        if not hasattr(self, "_last_cache_creation"):
            self._last_cache_creation = 0
        if not hasattr(self, "_last_prefix_hash"):
            self._last_prefix_hash = ""
        if not hasattr(self, "_warned_cache_ignored"):
            self._warned_cache_ignored = False
        if not hasattr(self, "_last_provider_has_visible_thinking"):
            self._last_provider_has_visible_thinking = False

    def _ensure_anthropic_module(self) -> Any:
        """Import Anthropic lazily so OpenAI-only runtime does not require it."""
        self._ensure_runtime_state()
        if self._anthropic is None:
            import anthropic as _anthropic

            self._anthropic = _anthropic
        return self._anthropic

    def _ensure_anthropic_clients(self) -> None:
        """Create Anthropic SDK clients only when Anthropic routing is used."""
        self._ensure_runtime_state()
        _anthropic = self._ensure_anthropic_module()

        if self._client is None:
            self._client = self._make_client(
                _anthropic,
                api_key=config.LLM_API_KEY,
                base_url=config.ANTHROPIC_BASE_URL,
                disable_cache=config.ANTHROPIC_DISABLE_CACHE,
            )

        if config.OPUS_API_KEY and self._opus_client is None:
            self._opus_client = self._make_client(
                _anthropic,
                api_key=config.OPUS_API_KEY,
                base_url=config.OPUS_BASE_URL,
                disable_cache=config.OPUS_DISABLE_CACHE,
            )
            logger.info(
                "V2Backend: Opus client configured (base_url=%s)",
                config.OPUS_BASE_URL or "Anthropic default",
            )

    def _is_anthropic_rate_limit_error(self, exc: Exception) -> bool:
        self._ensure_runtime_state()
        if self._anthropic is None:
            return False
        err_type = getattr(self._anthropic, "RateLimitError", None)
        return isinstance(exc, err_type) if isinstance(err_type, type) else False

    def _is_anthropic_api_error(self, exc: Exception) -> bool:
        self._ensure_runtime_state()
        if self._anthropic is None:
            return False
        err_type = getattr(self._anthropic, "APIError", None)
        return isinstance(exc, err_type) if isinstance(err_type, type) else False

    def _get_client(self, model: str) -> anthropic.Anthropic:
        """Select the appropriate client based on the model name.

        Routing logic:
        - ``claude-opus-4-6-thinking`` → default client (a relay, gameplay)
        - ``claude-opus-4-6`` (plain) → opus client (AWS relay, post-run)
        The ``-thinking`` suffix marks models intended for the default channel.
        """
        self._ensure_anthropic_clients()
        if (
            self._opus_client
            and "opus" in model.lower()
            and "thinking" not in model.lower()
        ):
            return self._opus_client
        assert self._client is not None
        return self._client

    @staticmethod
    def _openai_relay_key(relay: dict[str, str]) -> str:
        # api_key fingerprint is part of the cache key so that env-driven
        # credential rotation (.env edited mid-process, or the user fixing a
        # stale key) invalidates the cached httpx.Client — whose
        # Authorization header is baked in at construction time.
        name = (relay.get("name") or "").strip()
        base_url = (relay.get("base_url") or "").strip()
        api_key = (relay.get("api_key") or "").strip()
        key_fp = (
            hashlib.sha1(api_key.encode("utf-8")).hexdigest()[:8]
            if api_key else "noauth"
        )
        return f"{name}|{base_url}|{key_fp}"

    @staticmethod
    def _normalize_openai_profile(profile: str | None) -> str:
        return config.normalize_openai_compat_profile(profile)

    def _openai_scoped_relay_key(self, relay: dict[str, str], profile: str | None = None) -> str:
        key = self._openai_relay_key(relay)
        use_profile = self._normalize_openai_profile(profile)
        if use_profile == "default":
            return key
        return f"{use_profile}|{key}"

    def _get_preferred_openai_relay(self, profile: str | None = None) -> str:
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        if use_profile == "default":
            return self._preferred_openai_relay
        return self._preferred_openai_relays.get(use_profile, "")

    def _set_preferred_openai_relay(self, relay_key: str, profile: str | None = None) -> None:
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        if use_profile == "default":
            self._preferred_openai_relay = relay_key
        else:
            self._preferred_openai_relays[use_profile] = relay_key

    def _clear_preferred_openai_relay(self, relay_key: str, profile: str | None = None) -> None:
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        if use_profile == "default":
            if self._preferred_openai_relay == relay_key:
                self._preferred_openai_relay = ""
            return
        if self._preferred_openai_relays.get(use_profile) == relay_key:
            self._preferred_openai_relays.pop(use_profile, None)

    def _get_openai_client(
        self,
        relay: dict[str, str] | None = None,
        *,
        profile: str | None = None,
    ) -> httpx.Client:
        """Return the HTTP client for a specific OpenAI-compatible relay."""
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        relays = config.get_openai_compat_relays(use_profile)
        target = relay or (relays[0] if relays else None)
        if target is None:
            raise RuntimeError("No OpenAI-compatible relay configured")

        target_key = self._openai_scoped_relay_key(target, use_profile)
        primary_key = self._openai_scoped_relay_key(relays[0], use_profile) if relays else target_key
        api_key = target.get("api_key", "")

        # Backwards compatibility for tests and the legacy single-relay path.
        if use_profile == "default" and target_key == primary_key:
            if self._openai_client is None:
                self._openai_client = self._make_http_client(api_key=api_key)
            return self._openai_client

        client = self._openai_clients.get(target_key)
        if client is None:
            client = self._make_http_client(api_key=api_key)
            self._openai_clients[target_key] = client
        return client

    @staticmethod
    def _get_openai_endpoint(
        relay: dict[str, str] | None = None,
        *,
        profile: str | None = None,
    ) -> str:
        """Build the OpenAI-compatible chat/completions endpoint."""
        base = (
            (relay or {}).get("base_url")
            or config.get_openai_compat_base_url(profile)
            or config.LLM_BASE_URL
        ).rstrip("/")
        if base.endswith("/chat/completions"):
            return base
        if base.endswith("/v1"):
            return f"{base}/chat/completions"
        return f"{base}/v1/chat/completions"

    def _prioritize_openai_relays(
        self,
        relays: list[dict[str, str]],
        *,
        profile: str | None = None,
    ) -> list[dict[str, str]]:
        """Move the last successful relay to the front, preserving config order."""
        preferred_key = self._get_preferred_openai_relay(profile)
        if not relays or not preferred_key:
            return list(relays)

        preferred: list[dict[str, str]] = []
        others: list[dict[str, str]] = []
        for relay in relays:
            if self._openai_scoped_relay_key(relay, profile) == preferred_key:
                preferred.append(relay)
            else:
                others.append(relay)
        return preferred + others

    def _get_openai_relay_candidates(self, *, profile: str | None = None) -> list[dict[str, str]]:
        """Return relay candidates, preferring healthy and recently successful ones."""
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        relays = list(config.get_openai_compat_relays(use_profile))
        if not relays:
            return []

        now = time.monotonic()
        healthy: list[dict[str, str]] = []
        cooling: list[dict[str, str]] = []
        for relay in relays:
            fail_until = self._openai_relay_fail_until.get(
                self._openai_scoped_relay_key(relay, use_profile),
                0.0,
            )
            if fail_until > now:
                cooling.append(relay)
            else:
                healthy.append(relay)

        if healthy:
            return self._prioritize_openai_relays(healthy, profile=use_profile)

        logger.warning(
            "V2Backend: all OpenAI-compatible relays are in cooldown for profile=%s; "
            "retrying configured list",
            use_profile,
        )
        return self._prioritize_openai_relays(relays, profile=use_profile)

    @staticmethod
    def _extract_http_error_text(exc: httpx.HTTPError) -> str:
        response = getattr(exc, "response", None)
        if response is None:
            return ""
        try:
            return response.text or ""
        except Exception:
            return ""

    @classmethod
    def _format_http_error_for_log(cls, exc: httpx.HTTPError) -> str:
        """Format an HTTP error with a compact response-body preview for logs."""
        body = " ".join(cls._extract_http_error_text(exc).split())
        if not body:
            return str(exc)
        if len(body) > 400:
            body = body[:397] + "..."
        return f"{exc} | body={body}"

    @classmethod
    def _is_openai_failover_error(cls, exc: Exception) -> bool:
        """Whether an OpenAI-compatible error should trigger relay failover."""
        if isinstance(exc, httpx.TimeoutException):
            return True
        if isinstance(exc, httpx.RequestError) and not isinstance(exc, httpx.HTTPStatusError):
            return True
        if not isinstance(exc, httpx.HTTPStatusError):
            return False

        status = exc.response.status_code
        body = cls._extract_http_error_text(exc).lower()
        if status in {401, 403, 429, 500, 502, 503, 504}:
            return True
        if status != 400:
            return False

        # Content-filter rejections are permanent for the given prompt — retrying
        # the same relay won't help.  Let the caller fall through to the model
        # fallback chain instead.
        if "content_filter" in body:
            return False

        markers = (
            "api key",
            "api_key",
            "invalid api",
            "insufficient_quota",
            "quota exceeded",
            "check quota",
            "quota",
            "billing",
            "resource has been exhausted",
            "permission denied",
            "suspended",
            "upstream_error",
            "invalid project resource name",
            "consumer suspended",
            "consumer has no access",
            "consumer not entitled",
            "plan and billing details",
        )
        return any(marker in body for marker in markers)

    def _mark_openai_relay_failed(
        self,
        relay: dict[str, str],
        exc: Exception,
        *,
        profile: str | None = None,
    ) -> None:
        """Cooldown a failing relay so later calls prefer healthier alternatives."""
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        relay_key = self._openai_scoped_relay_key(relay, use_profile)
        cooldown = max(config.OPENAI_COMPAT_FAILOVER_COOLDOWN_SEC, 0.0)
        if cooldown > 0:
            self._openai_relay_fail_until[relay_key] = time.monotonic() + cooldown
        self._clear_preferred_openai_relay(relay_key, use_profile)
        logger.warning(
            "V2Backend: cooling down OpenAI relay %s (profile=%s) for %.0fs after error: %s",
            relay.get("name") or self._get_openai_endpoint(relay, profile=use_profile),
            use_profile,
            cooldown,
            self._format_http_error_for_log(exc) if isinstance(exc, httpx.HTTPError) else exc,
        )

    def _mark_openai_relay_success(
        self,
        relay: dict[str, str],
        *,
        profile: str | None = None,
    ) -> None:
        """Remember the last working relay so later calls stick to it."""
        self._ensure_runtime_state()
        use_profile = self._normalize_openai_profile(profile)
        relay_key = self._openai_scoped_relay_key(relay, use_profile)
        self._set_preferred_openai_relay(relay_key, use_profile)
        self._openai_relay_fail_until.pop(relay_key, None)
        self._last_transport_target = (
            relay.get("name") or self._get_openai_endpoint(relay, profile=use_profile)
        )

    @staticmethod
    def _is_gemini_model(model: str) -> bool:
        """Return True for Gemini models routed through OpenAI-compatible relays."""
        return "gemini" in (model or "").lower()

    @staticmethod
    def _is_gpt5_model(model: str) -> bool:
        """Return True for GPT-5-family models routed through OpenAI-compatible relays."""
        value = (model or "").strip().lower()
        return value.startswith("gpt-5")

    @staticmethod
    def _normalize_openai_reasoning_effort(*, think: bool, effort: str) -> str:
        """Map internal effort names to the OpenAI-compatible reasoning payload."""
        if not think:
            return "none"
        value = (effort or "medium").strip().lower()
        if value == "max":
            return "xhigh"
        if value in {"none", "low", "medium", "high", "xhigh"}:
            return value
        return "medium"

    @staticmethod
    def _build_gemini_extra_body(
        *,
        effort: str,
        relay_base_url: str = "",
    ) -> dict[str, Any]:
        """Return the Gemini-specific OpenAI compatibility payload extension.

        The relay we use behaves much better when Google parameters are nested
        under ``extra_body`` rather than placed at the top level.

        ``thinking_budget`` is only included when the relay is known to
        support it.  Some relays reject requests that set both
        ``thinking_level`` and ``thinking_budget`` simultaneously.

        ``include_thoughts`` defaults to False (server-side thinking only,
        not streamed) — see ``STS2_GEMINI_INCLUDE_THOUGHTS`` env override.
        Empirical (2026-04-28 probe + log analysis): ``include_thoughts=True``
        makes proxy.example.com stream both ``reasoning_content`` and ``content``
        deltas through the same proxy buffer, and intermittently drops the
        visible-content portion entirely (text_len=0, reasoning_len>0,
        completion_tokens>0).  Setting to False keeps the model's reasoning
        depth identical but only streams the final visible answer, halving
        proxy buffer pressure and turning the failure mode into a
        properly-empty response that the existing empty-response handler
        catches.  Decision quality is unchanged because we never consume
        ``reasoning_content`` for downstream logic — the strategic_note is
        extracted from the visible ``<decision>{...}</decision>`` JSON.
        """
        import os as _os
        include_thoughts_default = _os.getenv(
            "STS2_GEMINI_INCLUDE_THOUGHTS", "false",
        ).lower() in ("1", "true", "yes")
        thinking_level = {"low": "low", "medium": "medium", "high": "high"}.get(
            effort,
            "medium",
        )
        thinking_config: dict[str, Any] = {
            "thinking_level": thinking_level,
            "include_thoughts": include_thoughts_default,
        }
        # Only add thinking_budget on relays known to accept it.  Some relays
        # reject requests that set both thinking_level and thinking_budget, so
        # this is gated by an explicit capability flag rather than vendor name.
        relay_supports_budget = _os.getenv(
            "STS2_RELAY_SUPPORTS_THINKING_BUDGET", "",
        ).lower() in ("1", "true", "yes")
        if relay_supports_budget:
            thinking_budget = {"low": 4096, "medium": 8192, "high": 16384}.get(
                thinking_level, 8192,
            )
            thinking_config["thinking_budget"] = thinking_budget
        return {
            "google": {
                "thinking_config": thinking_config,
            },
        }

    @classmethod
    def _should_stream_openai_compatible(
        cls,
        *,
        model: str,
        tools: list[dict[str, Any]] | None,
        think: bool = False,
    ) -> bool:
        """Prefer streaming only for tool-using calls.

        Streaming through the relay is 3x slower and intermittently returns empty
        responses (0tok, stop=None).  We previously kept Gemini+thinking on
        streaming to capture reasoning_content, but the upstream no longer emits
        thinking deltas, so non-streaming is uniformly more reliable.
        """
        if bool(tools):
            return True
        return False

    @staticmethod
    def _maybe_add_proxy_tool_reasoning_guard(
        *,
        system: str,
        tools: list[dict[str, Any]] | None,
    ) -> str:
        """Bias proxy calls away from free-form text before tool_use.

        Some Anthropic-compatible proxies strip later content blocks when the
        model emits visible ``text`` before ``tool_use``.  A small system-level
        guard keeps the response as a single tool block while still allowing
        compact visible rationale inside tool input fields.

        Applied to ALL tool-bearing calls through the proxy (both thinking and
        non-thinking), since the proxy block-stripping issue is independent of
        whether extended thinking is enabled.
        """
        if not (config.ANTHROPIC_BASE_URL and tools):
            return system
        if _PROXY_TOOL_REASONING_GUARD.strip() in system:
            return system
        return system + _PROXY_TOOL_REASONING_GUARD

    @staticmethod
    def _call_via_raw_stream(
        client: anthropic.Anthropic,
        kwargs: dict[str, Any],
        on_first_chunk: Callable[[dict[str, Any]], None] | None = None,
    ) -> anthropic.Message:
        """Consume raw SSE events and manually rebuild the final message.

        Some Anthropic-compatible proxies emit enough SSE data for raw
        streaming to work, while the SDK's higher-level accumulator either
        drops later blocks or raises on out-of-order indices.  We therefore
        reconstruct the message ourselves from ``message_start``,
        ``content_block_start`` / ``content_block_delta``, and ``message_delta``.
        """
        raw_stream = client.messages.create(**kwargs, stream=True)
        message = None
        blocks: dict[int, Any] = {}
        first_chunk_seen = False
        stats = {
            "thinking_start": False,
            "thinking_delta_chars": 0,
            "tool_use_start": False,
            "tool_json_chars": 0,
            "text_start": False,
            "text_delta_chars": 0,
        }
        try:
            for event in raw_stream:
                event_type = getattr(event, "type", None)
                if (
                    on_first_chunk is not None
                    and not first_chunk_seen
                    and event_type in {
                        "content_block_start",
                        "content_block_delta",
                        "message_delta",
                    }
                ):
                    first_chunk_seen = True
                    on_first_chunk({
                        "transport": "anthropic_stream",
                        "event_type": event_type,
                    })
                message = V2Backend._process_stream_event(
                    event, message, blocks, stats, kwargs,
                )
        finally:
            close = getattr(raw_stream, "close", None)
            if callable(close):
                close()

        if message is None:
            raise AssertionError("Raw stream ended without message_start")

        message.content = V2Backend._assemble_final_blocks(blocks)
        V2Backend._log_stream_thinking_stats(kwargs=kwargs, message=message, stats=stats)
        return message

    @staticmethod
    def _process_stream_event(
        event: Any,
        message: Any,
        blocks: dict[int, Any],
        stats: dict[str, Any],
        kwargs: dict[str, Any],
    ) -> Any:
        """Dispatch a single SSE event, returning the (possibly new) message."""
        event_type = getattr(event, "type", None)

        if event_type == "message_start":
            message = getattr(event, "message", None) or message
            if message is None:
                message = V2Backend._make_fallback_message(kwargs)
            V2Backend._ensure_message_usage(message)
            for index, block in enumerate(list(getattr(message, "content", []) or [])):
                blocks[index] = block
            return message

        if message is None:
            message = V2Backend._make_fallback_message(kwargs)

        if event_type == "content_block_start":
            V2Backend._handle_block_start(event, blocks, stats)
        elif event_type == "content_block_delta":
            V2Backend._handle_block_delta(event, blocks, stats)
        elif event_type == "message_delta":
            V2Backend._handle_message_delta(event, message)

        return message

    @staticmethod
    def _handle_block_start(
        event: Any, blocks: dict[int, Any], stats: dict[str, Any],
    ) -> None:
        """Process a content_block_start event."""
        index = V2Backend._safe_index(getattr(event, "index", None), blocks)
        incoming = getattr(event, "content_block", None)
        if incoming is None:
            return
        incoming_type = getattr(incoming, "type", None)
        if incoming_type == "thinking":
            stats["thinking_start"] = True
        elif incoming_type == "tool_use":
            stats["tool_use_start"] = True
        elif incoming_type == "text":
            stats["text_start"] = True
        existing = blocks.get(index)
        if existing is not None:
            blocks[index] = V2Backend._merge_stream_block(existing, incoming)
        else:
            blocks[index] = incoming

    @staticmethod
    def _handle_block_delta(
        event: Any, blocks: dict[int, Any], stats: dict[str, Any],
    ) -> None:
        """Process a content_block_delta event."""
        index = V2Backend._safe_index(getattr(event, "index", None), blocks)
        delta = getattr(event, "delta", None)
        if delta is None:
            return
        delta_type = getattr(delta, "type", None)
        if delta_type == "thinking_delta":
            stats["thinking_delta_chars"] += len(getattr(delta, "thinking", "") or "")
        elif delta_type == "input_json_delta":
            stats["tool_json_chars"] += len(getattr(delta, "partial_json", "") or "")
        elif delta_type == "text_delta":
            stats["text_delta_chars"] += len(getattr(delta, "text", "") or "")
        block = blocks.get(index)
        if block is None:
            block = V2Backend._make_placeholder_block(delta)
            blocks[index] = block
        V2Backend._apply_block_delta(block, delta)

    @staticmethod
    def _handle_message_delta(event: Any, message: Any) -> None:
        """Process a message_delta event (stop reason + usage updates)."""
        delta = getattr(event, "delta", None)
        if delta is not None:
            message.stop_reason = getattr(delta, "stop_reason", None)
            message.stop_sequence = getattr(delta, "stop_sequence", None)
            container = getattr(delta, "container", None)
            if container is not None:
                message.container = container
        usage = V2Backend._ensure_message_usage(message)
        delta_usage = getattr(event, "usage", None)
        if delta_usage is not None:
            if getattr(delta_usage, "input_tokens", None) is not None:
                usage.input_tokens = delta_usage.input_tokens
            if getattr(delta_usage, "output_tokens", None) is not None:
                usage.output_tokens = delta_usage.output_tokens
            if getattr(delta_usage, "cache_creation_input_tokens", None) is not None:
                usage.cache_creation_input_tokens = (
                    delta_usage.cache_creation_input_tokens
                )
            if getattr(delta_usage, "cache_read_input_tokens", None) is not None:
                usage.cache_read_input_tokens = delta_usage.cache_read_input_tokens
            if getattr(delta_usage, "server_tool_use", None) is not None:
                usage.server_tool_use = delta_usage.server_tool_use

    @staticmethod
    def _assemble_final_blocks(blocks: dict[int, Any]) -> list[Any]:
        """Finalize and order accumulated content blocks."""
        ordered = [
            V2Backend._finalize_stream_block(block)
            for _, block in sorted(blocks.items())
            if block is not None
        ]
        if len(ordered) > 1:
            ordered = [b for b in ordered if not V2Backend._is_empty_text_block(b)]
        return ordered

    @staticmethod
    def _make_fallback_message(kwargs: dict[str, Any]) -> Any:
        return SimpleNamespace(
            id=None,
            container=None,
            content=[],
            model=kwargs.get("model"),
            role="assistant",
            stop_reason=None,
            stop_sequence=None,
            type="message",
            usage=SimpleNamespace(
                input_tokens=0,
                output_tokens=0,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
                server_tool_use=None,
                service_tier=None,
                inference_geo=None,
                cache_creation=None,
            ),
        )

    @staticmethod
    def _ensure_message_usage(message: Any) -> Any:
        usage = getattr(message, "usage", None)
        if usage is None:
            usage = SimpleNamespace()
            message.usage = usage
        defaults = {
            "input_tokens": 0,
            "output_tokens": 0,
            "cache_read_input_tokens": 0,
            "cache_creation_input_tokens": 0,
            "server_tool_use": None,
            "service_tier": None,
            "inference_geo": None,
            "cache_creation": None,
        }
        for name, value in defaults.items():
            if not hasattr(usage, name):
                setattr(usage, name, value)
        return usage

    @staticmethod
    def _safe_index(index: Any, blocks: dict[int, Any]) -> int:
        if isinstance(index, int) and index >= 0:
            return index
        return len(blocks)

    @staticmethod
    def _make_placeholder_block(delta: Any) -> Any:
        delta_type = getattr(delta, "type", None)
        if delta_type == "input_json_delta":
            return SimpleNamespace(type="tool_use", id="", name="", input={})
        if delta_type in {"thinking_delta", "signature_delta"}:
            return SimpleNamespace(type="thinking", thinking="", signature="")
        return SimpleNamespace(type="text", text="", citations=None)

    @staticmethod
    def _merge_stream_block(existing: Any, incoming: Any) -> Any:
        existing_type = getattr(existing, "type", None)
        incoming_type = getattr(incoming, "type", None)
        if existing_type != incoming_type:
            return incoming

        if incoming_type == "text":
            existing_text = getattr(existing, "text", "") or ""
            if existing_text:
                incoming.text = existing_text + (getattr(incoming, "text", "") or "")
            existing_citations = getattr(existing, "citations", None)
            incoming_citations = getattr(incoming, "citations", None)
            if existing_citations and not incoming_citations:
                incoming.citations = existing_citations
        elif incoming_type == "thinking":
            existing_thinking = getattr(existing, "thinking", "") or ""
            if existing_thinking:
                incoming.thinking = existing_thinking + (getattr(incoming, "thinking", "") or "")
            existing_signature = getattr(existing, "signature", "") or ""
            if existing_signature and not getattr(incoming, "signature", ""):
                incoming.signature = existing_signature
        elif incoming_type == "tool_use":
            if getattr(existing, "id", "") and not getattr(incoming, "id", ""):
                incoming.id = existing.id
            if getattr(existing, "name", "") and not getattr(incoming, "name", ""):
                incoming.name = existing.name
            existing_input = getattr(existing, "input", None)
            if (
                isinstance(existing_input, dict)
                and existing_input
                and not getattr(incoming, "input", None)
            ):
                incoming.input = existing_input
            raw_json = getattr(existing, "_sts2_input_json", "")
            if raw_json:
                setattr(incoming, "_sts2_input_json", raw_json)
        return incoming

    @staticmethod
    def _apply_block_delta(block: Any, delta: Any) -> None:
        delta_type = getattr(delta, "type", None)
        block_type = getattr(block, "type", None)

        if delta_type == "text_delta":
            if block_type != "text":
                return
            current = getattr(block, "text", "") or ""
            block.text = current + (getattr(delta, "text", "") or "")
            return

        if delta_type == "input_json_delta":
            if block_type != "tool_use":
                return
            current = getattr(block, "_sts2_input_json", "")
            setattr(
                block,
                "_sts2_input_json",
                current + (getattr(delta, "partial_json", "") or ""),
            )
            return

        if delta_type == "thinking_delta":
            if block_type != "thinking":
                return
            current = getattr(block, "thinking", "") or ""
            block.thinking = current + (getattr(delta, "thinking", "") or "")
            return

        if delta_type == "signature_delta":
            if block_type != "thinking":
                return
            block.signature = getattr(delta, "signature", "") or ""
            return

        if delta_type == "citations_delta":
            if block_type != "text":
                return
            citations = list(getattr(block, "citations", None) or [])
            citation = getattr(delta, "citation", None)
            if citation is not None:
                citations.append(citation)
                block.citations = citations

    @staticmethod
    def _finalize_stream_block(block: Any) -> Any:
        if getattr(block, "type", None) != "tool_use":
            return block

        raw_json = getattr(block, "_sts2_input_json", "")
        if not raw_json:
            return block

        parsed = V2Backend._parse_streamed_tool_input(raw_json)
        if isinstance(parsed, dict):
            block.input = parsed
        else:
            logger.warning(
                "V2Backend: streamed tool input did not parse as an object; keeping empty input"
            )
            block.input = {}
        return block

    @staticmethod
    def _parse_streamed_tool_input(raw_json: str) -> Any:
        try:
            return json.loads(raw_json)
        except json.JSONDecodeError:
            if _JITER_AVAILABLE:
                try:
                    return _jiter_from_json(raw_json.encode("utf-8"), partial_mode=True)
                except Exception:
                    pass
            logger.warning(
                "V2Backend: failed to parse streamed tool JSON: %s",
                raw_json[:200],
            )
            return {}

    @staticmethod
    def _is_empty_text_block(block: Any) -> bool:
        if getattr(block, "type", None) != "text":
            return False
        text = getattr(block, "text", "") or ""
        citations = getattr(block, "citations", None)
        return not text.strip() and not citations

    @staticmethod
    def _log_stream_thinking_stats(
        *,
        kwargs: dict[str, Any],
        message: Any,
        stats: dict[str, Any],
    ) -> None:
        if kwargs.get("thinking") is None or not kwargs.get("tools"):
            return

        final_thinking_chars = 0
        for block in list(getattr(message, "content", []) or []):
            if getattr(block, "type", None) == "thinking":
                final_thinking_chars += len(getattr(block, "thinking", "") or "")

        if stats["thinking_delta_chars"] > 0 and final_thinking_chars == 0:
            logger.warning(
                "V2Backend: raw stream had thinking deltas (%d chars) "
                "but final response has no thinking block",
                stats["thinking_delta_chars"],
            )
            return

        if stats["thinking_delta_chars"] == 0:
            logger.debug(
                "V2Backend: raw stream had no thinking deltas "
                "(thinking_start=%s text_start=%s text_chars=%d "
                "tool_use_start=%s tool_json_chars=%d)",
                stats["thinking_start"],
                stats["text_start"],
                stats["text_delta_chars"],
                stats["tool_use_start"],
                stats["tool_json_chars"],
            )

    # ── OpenAI-compatible helpers ──────────────────────────────

    @staticmethod
    def _block_attr(block: Any, name: str) -> Any:
        if isinstance(block, dict):
            return block.get(name)
        return getattr(block, name, None)

    @staticmethod
    def _block_type(block: Any) -> str:
        block_type = V2Backend._block_attr(block, "type")
        if isinstance(block_type, str) and block_type:
            return block_type
        return type(block).__name__

    @staticmethod
    def _iter_content_blocks(content: Any) -> list[Any]:
        if content is None:
            return []
        if isinstance(content, list):
            return list(content)
        return [content]

    @staticmethod
    def _collect_text_content(content: Any) -> str:
        if isinstance(content, str):
            return content

        parts: list[str] = []
        for block in V2Backend._iter_content_blocks(content):
            block_type = V2Backend._block_type(block)
            if block_type == "text":
                text = V2Backend._block_attr(block, "text")
                if isinstance(text, str) and text:
                    parts.append(text)
        return "\n\n".join(parts)

    @staticmethod
    def _normalize_openai_tools(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for tool in tools:
            if tool.get("type") == "function" and "function" in tool:
                normalized.append(tool)
                continue

            function_def: dict[str, Any] = {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool.get("input_schema", {}),
            }
            if "strict" in tool:
                function_def["strict"] = tool["strict"]
            normalized.append({
                "type": "function",
                "function": function_def,
            })
        return normalized

    @staticmethod
    def _map_openai_tool_choice(tool_choice: dict[str, Any] | None) -> str | dict[str, Any] | None:
        if not tool_choice:
            return None

        choice_type = tool_choice.get("type")
        if choice_type == "auto":
            return "auto"
        if choice_type == "any":
            return "required"
        if choice_type == "none":
            return "none"
        if choice_type == "tool":
            return {
                "type": "function",
                "function": {"name": tool_choice["name"]},
            }
        return None

    @staticmethod
    def _to_openai_messages(system: str, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = [{"role": "system", "content": system}]

        for message in messages:
            role = message.get("role")
            content = message.get("content")

            if role == "system":
                text = V2Backend._collect_text_content(content)
                if text:
                    result.append({"role": "system", "content": text})
                continue

            if role == "user":
                if isinstance(content, str):
                    result.append({"role": "user", "content": content})
                    continue

                blocks = V2Backend._iter_content_blocks(content)
                tool_results = [
                    block for block in blocks if V2Backend._block_type(block) == "tool_result"
                ]
                text = V2Backend._collect_text_content(blocks)
                if text:
                    result.append({"role": "user", "content": text})
                for block in tool_results:
                    tool_content = V2Backend._block_attr(block, "content")
                    if not isinstance(tool_content, str):
                        tool_content = json.dumps(tool_content, ensure_ascii=False)
                    result.append({
                        "role": "tool",
                        "tool_call_id": V2Backend._block_attr(block, "tool_use_id") or "",
                        "content": tool_content,
                    })
                continue

            if role == "assistant":
                if isinstance(content, str):
                    result.append({"role": "assistant", "content": content})
                    continue

                blocks = V2Backend._iter_content_blocks(content)
                text = V2Backend._collect_text_content(blocks)
                tool_calls: list[dict[str, Any]] = []
                for index, block in enumerate(blocks):
                    if V2Backend._block_type(block) != "tool_use":
                        continue
                    tool_input = V2Backend._block_attr(block, "input")
                    if isinstance(tool_input, str):
                        arguments = tool_input
                    else:
                        arguments = json.dumps(tool_input or {}, ensure_ascii=False)
                    tool_calls.append({
                        "id": V2Backend._block_attr(block, "id") or f"tool_call_{index}",
                        "type": "function",
                        "function": {
                            "name": V2Backend._block_attr(block, "name") or "",
                            "arguments": arguments,
                        },
                    })

                if text or tool_calls:
                    entry: dict[str, Any] = {"role": "assistant", "content": text or None}
                    if tool_calls:
                        entry["tool_calls"] = tool_calls
                    # Pass back reasoning_content for kimi multi-turn
                    reasoning = message.get("_reasoning_content", "")
                    if reasoning:
                        entry["reasoning_content"] = reasoning
                    result.append(entry)
                continue

            if isinstance(content, str):
                result.append({"role": role or "user", "content": content})

        return result

    def _make_openai_message(
        self,
        *,
        model: str,
        finish_reason: str | None,
        text_content: str,
        tool_calls: list[dict[str, Any]],
        usage: dict[str, Any] | None,
    ) -> Any:
        message = self._make_fallback_message({"model": model})
        message.stop_reason = self._map_finish_reason(finish_reason, tool_calls)

        content_blocks: list[Any] = []
        if text_content:
            content_blocks.append(SimpleNamespace(
                type="text",
                text=text_content,
                citations=None,
            ))

        for index, tool_call in enumerate(tool_calls):
            raw_arguments = tool_call.get("arguments", "")
            tool_input = (
                raw_arguments
                if isinstance(raw_arguments, dict)
                else self._parse_streamed_tool_input(raw_arguments or "")
            )
            if not isinstance(tool_input, dict):
                tool_input = {}
            content_blocks.append(SimpleNamespace(
                type="tool_use",
                id=tool_call.get("id") or f"tool_call_{index}",
                name=tool_call.get("name") or "",
                input=tool_input,
            ))

        message.content = content_blocks
        usage_obj = self._ensure_message_usage(message)
        usage_data = usage or {}
        usage_obj.input_tokens = usage_data.get("prompt_tokens", 0) or 0
        usage_obj.output_tokens = usage_data.get("completion_tokens", 0) or 0
        # Read cached_tokens from providers that support it (e.g. kimi-k2.5).
        # Location varies: top-level (Moonshot native) or nested in
        # prompt_tokens_details (OpenAI-compat proxies).
        cached = usage_data.get("cached_tokens", 0) or 0
        if not cached:
            ptd = usage_data.get("prompt_tokens_details") or {}
            if isinstance(ptd, dict):
                cached = ptd.get("cached_tokens", 0) or 0
        usage_obj.cache_read_input_tokens = cached
        usage_obj.cache_creation_input_tokens = 0
        return message

    @staticmethod
    def _map_finish_reason(
        finish_reason: str | None,
        tool_calls: list[dict[str, Any]],
    ) -> str | None:
        if finish_reason == "tool_calls":
            return "tool_use"
        if finish_reason in {"stop", "eos"}:
            return "end_turn"
        if finish_reason:
            return finish_reason
        if tool_calls:
            return "tool_use"
        return None

    def _call_openai_compatible(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        model: str,
        think: bool,
        effort: str,
        tools: list[dict[str, Any]] | None,
        tool_choice: dict[str, Any] | None,
        max_tokens: int | None,
        temperature: float | None,
        on_first_chunk: Callable[[dict[str, Any]], None] | None = None,
        openai_relay_profile: str = "default",
        response_format: dict[str, Any] | None = None,
        tier: str | None = None,
    ) -> Any:
        use_tools = bool(tools)
        is_kimi = "kimi" in model.lower()
        is_gemini = self._is_gemini_model(model)
        is_gpt5 = self._is_gpt5_model(model)
        is_qwen = "qwen" in model.lower()
        is_deepseek = "deepseek" in model.lower()
        use_stream = self._should_stream_openai_compatible(model=model, tools=tools, think=think)
        # Provider capability flags for downstream logic
        # kimi and some GPT-5 relays expose reasoning_content; gemini proxy thinking stays server-side.
        self._last_provider_has_visible_thinking = is_kimi or is_gpt5 or is_deepseek
        payload: dict[str, Any] = {
            "model": model,
            "messages": self._to_openai_messages(system, messages),
            "max_tokens": max_tokens or config.LLM_MAX_TOKENS,
            "temperature": (
                temperature if temperature is not None else config.LLM_TEMPERATURE
            ),
        }
        if is_kimi:
            # kimi-k2.5 thinking requires temperature=1.0; non-thinking=0.6
            payload["temperature"] = 1.0 if think else 0.6
            # kimi thinking toggle (enabled by default, explicit is safer)
            payload["thinking"] = {"type": "enabled" if think else "disabled"}
            # kimi thinking needs max_tokens >= 16000 to avoid truncation
            if think:
                payload["max_tokens"] = max(payload["max_tokens"], 16000)
        elif is_gpt5:
            # some relays use the legacy top-level reasoning_effort parameter
            # (o1/o3 style), NOT the nested reasoning:{effort:...} format.
            gpt5_effort = self._normalize_openai_reasoning_effort(
                think=think,
                effort=effort,
            )
            if gpt5_effort != "none":
                payload["reasoning_effort"] = gpt5_effort
            if think:
                payload["max_tokens"] = max(
                    payload["max_tokens"],
                    {"low": 8192, "medium": 12000, "high": 16000, "xhigh": 32000}.get(
                        gpt5_effort,
                        12000,
                    ),
                )
        elif is_gemini and think:
            # Resolve relay base_url to decide whether thinking_budget is safe
            _family_relay = config.get_model_family_relay(model)
            _relay_url = (_family_relay or {}).get("base_url", "") if _family_relay else ""
            if not _relay_url:
                _relay_url = config.get_openai_compat_base_url(openai_relay_profile)
            payload["extra_body"] = self._build_gemini_extra_body(
                effort=effort, relay_base_url=_relay_url,
            )
            # Gemini thinking tokens count toward max_tokens output budget.
            # thinking_budget caps the thinking portion; max_tokens must be
            # thinking_budget + visible output headroom to avoid stop=length.
            # Headroom budget (max_tokens - thinking_budget):
            #   low:    8192 -  4096 =  4096 visible
            #   medium: 16000 - 8192 =  7808 visible (bumped 2026-04-26 — 12000 cap
            #           hit stop=length on shop_plan with full context)
            #   high:   24000 - 16384 = 7616 visible (bumped for analysis-tier parity)
            payload["max_tokens"] = max(
                payload["max_tokens"],
                {"low": 8192, "medium": 16000, "high": 24000}.get(
                    (effort or "medium").strip().lower(),
                    16000,
                ),
            )
        elif is_qwen:
            # Qwen enable_thinking policy: effort=low → OFF (fast tier);
            # medium/high → ON (strategic/analysis). Smoke-test data
            # (2026-04-20, DashScope): thinking=off tool_use ≈ 1.8s vs
            # thinking=on ≈ 25s.
            eff = (effort or "").strip().lower()
            enable_thinking = bool(think) and eff != "low"
            # Relay-specific key format:
            #   DashScope (dashscope.aliyuncs.com): extra_body={"enable_thinking": ...}
            #   SiliconFlow (api.siliconflow.cn):   chat_template_kwargs={"enable_thinking": ...}
            _family_relay = config.get_model_family_relay(model)
            _relay_url = ((_family_relay or {}).get("base_url", "")
                          or config.get_openai_compat_base_url(openai_relay_profile))
            is_dashscope = "dashscope" in _relay_url.lower()
            extra_body = payload.get("extra_body", {}) or {}
            if is_dashscope:
                extra_body["enable_thinking"] = enable_thinking
            else:
                # SiliconFlow / vLLM-style: nested under chat_template_kwargs.
                tpl_kwargs = dict(extra_body.get("chat_template_kwargs", {}) or {})
                tpl_kwargs["enable_thinking"] = enable_thinking
                extra_body["chat_template_kwargs"] = tpl_kwargs
                if enable_thinking:
                    # thinking_budget honored by some vLLM relays; harmless
                    # on SiliconFlow which ignores it.
                    extra_body["thinking_budget"] = {
                        "low": 4096, "medium": 8192, "high": 16384,
                    }.get(eff or "medium", 8192)
            payload["extra_body"] = extra_body
            if enable_thinking:
                # Reasoning tokens count toward max_tokens on both relays;
                # give enough headroom for reasoning + visible content.
                payload["max_tokens"] = max(
                    payload["max_tokens"],
                    {"low": 8192, "medium": 20000, "high": 32000}.get(
                        eff or "medium", 20000,
                    ),
                )
        elif is_deepseek:
            # DeepSeek V4 (api.deepseek.com) — OpenAI-compatible with thinking
            # toggle. Policy:
            #   effort=low  → thinking disabled (fast tier; no reasoning)
            #   effort=high → thinking enabled, reasoning_effort="high" (default)
            #   effort=max  → thinking enabled, reasoning_effort="max"
            # Thinking mode forbids temperature/top_p/presence_penalty/frequency_penalty.
            eff = (effort or "medium").strip().lower()
            enable_thinking = bool(think) and eff != "low"
            payload["thinking"] = {"type": "enabled" if enable_thinking else "disabled"}
            if enable_thinking:
                ds_effort = "max" if eff == "max" else "high"
                payload["reasoning_effort"] = ds_effort
                # Strip unsupported sampling params when thinking is on.
                payload.pop("temperature", None)
                payload["max_tokens"] = max(
                    payload["max_tokens"],
                    {"high": 16000, "max": 32000}.get(ds_effort, 16000),
                )
        elif think and effort:
            payload["max_tokens"] = max(
                payload["max_tokens"],
                {"low": 8192, "medium": 12000, "high": 16000, "max": 32000}.get(effort, 12000),
            )
        # Qwen json_object mode: inject response_format only when thinking is OFF.
        # (Qwen docs: thinking mode + structured output are incompatible.)
        if is_qwen and response_format and not enable_thinking:
            payload["response_format"] = response_format
        if use_tools:
            payload["tools"] = self._normalize_openai_tools(tools or [])
            mapped_choice = self._map_openai_tool_choice(tool_choice)
            if mapped_choice is not None:
                payload["tool_choice"] = mapped_choice

        relay_candidates = self._get_openai_relay_candidates(profile=openai_relay_profile)

        # ── Model-family credential override ──
        # If the user configured STS2_GPT_API_KEY / STS2_GEMINI_API_KEY /
        # STS2_QWEN_API_KEY, that family-specific relay takes priority over
        # the generic profile relay. This ensures that when the router
        # falls back from GPT → Gemini, each model hits the right API key.
        # Computed before the empty-list check so a family-only config (no
        # generic STS2_OPENAI_COMPAT_BASE_URL) still resolves a candidate.
        family_relay = config.get_model_family_relay(model)
        if family_relay:
            # Put family relay first; keep profile relays as failover.
            relay_candidates = [family_relay] + [
                r for r in relay_candidates
                if r.get("api_key") != family_relay.get("api_key")
            ]

        if not relay_candidates:
            family = config._detect_model_family(model) if model else ""
            hint = (
                f"set STS2_{family.upper()}_BASE_URL/_API_KEY"
                if family
                else "set STS2_<FAMILY>_BASE_URL/_API_KEY or STS2_OPENAI_COMPAT_BASE_URL"
            )
            raise RuntimeError(
                f"No OpenAI-compatible relay configured for model={model!r} ({hint})"
            )

        last_exc: Exception | None = None
        for idx, relay in enumerate(relay_candidates):
            relay_label = relay.get("name") or self._get_openai_endpoint(
                relay,
                profile=openai_relay_profile,
            )
            try:
                if use_stream:
                    result = self._call_openai_stream(
                        payload,
                        relay=relay,
                        on_first_chunk=on_first_chunk,
                        capture_reasoning=is_kimi or is_gemini or is_gpt5,
                        openai_relay_profile=openai_relay_profile,
                        tier=tier,
                    )
                else:
                    result = self._call_openai_json(
                        payload,
                        relay=relay,
                        parse_think_tags=(is_gemini or is_gpt5 or is_qwen) and think,
                        openai_relay_profile=openai_relay_profile,
                        tier=tier,
                    )
                self._mark_openai_relay_success(relay, profile=openai_relay_profile)
                return result
            except httpx.HTTPError as exc:
                last_exc = exc
                should_failover = self._is_openai_failover_error(exc)
                if should_failover:
                    self._mark_openai_relay_failed(relay, exc, profile=openai_relay_profile)
                if should_failover and idx < len(relay_candidates) - 1:
                    next_relay = relay_candidates[idx + 1]
                    next_label = next_relay.get("name") or self._get_openai_endpoint(
                        next_relay,
                        profile=openai_relay_profile,
                    )
                    logger.warning(
                        "V2Backend: switching OpenAI relay %s -> %s (profile=%s) after %s",
                        relay_label,
                        next_label,
                        openai_relay_profile,
                        exc,
                    )
                    continue
                raise

        if last_exc is not None:
            raise last_exc
        raise RuntimeError("OpenAI-compatible call failed without a captured exception")

    def _call_openai_json(
        self,
        payload: dict[str, Any],
        *,
        relay: dict[str, str] | None = None,
        parse_think_tags: bool = False,
        openai_relay_profile: str = "default",
        tier: str | None = None,
    ) -> Any:
        client = self._get_openai_client(relay, profile=openai_relay_profile)
        post_kwargs: dict[str, Any] = {"json": payload}
        per_call_timeout = self._resolve_per_call_timeout(tier)
        if per_call_timeout is not None:
            post_kwargs["timeout"] = per_call_timeout
        response = client.post(
            self._get_openai_endpoint(relay, profile=openai_relay_profile),
            **post_kwargs,
        )
        response.raise_for_status()
        data = response.json()
        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        tool_calls = []
        for index, tool_call in enumerate(message.get("tool_calls") or []):
            function = tool_call.get("function") or {}
            tool_calls.append({
                "id": tool_call.get("id") or f"tool_call_{index}",
                "name": function.get("name") or "",
                "arguments": function.get("arguments") or "",
            })
        raw_content = message.get("content") or ""
        reasoning = ""

        # Gemini: thinking inlined as <think>...</think> in content
        if parse_think_tags and "<think>" in raw_content:
            reasoning, raw_content = self._split_think_tags(raw_content)
        # Kimi: reasoning_content is a separate field
        if not reasoning:
            reasoning = message.get("reasoning_content") or ""

        msg = self._make_openai_message(
            model=payload["model"],
            finish_reason=choice.get("finish_reason"),
            text_content=raw_content,
            tool_calls=tool_calls,
            usage=data.get("usage"),
        )
        if reasoning:
            msg._reasoning_content = reasoning
        return msg

    @staticmethod
    def _split_think_tags(content: str) -> tuple[str, str]:
        """Extract <think>...</think> from content.

        Returns (thinking_text, remaining_content).
        """
        import re
        think_match = re.search(r"<think>(.*?)</think>", content, re.DOTALL)
        if not think_match:
            return "", content
        thinking = think_match.group(1).strip()
        remaining = re.sub(r"<think>.*?</think>\s*", "", content, flags=re.DOTALL).strip()
        return thinking, remaining

    def _call_openai_stream(
        self,
        payload: dict[str, Any],
        *,
        relay: dict[str, str] | None = None,
        on_first_chunk: Callable[[dict[str, Any]], None] | None = None,
        capture_reasoning: bool = False,
        openai_relay_profile: str = "default",
        tier: str | None = None,
    ) -> Any:
        client = self._get_openai_client(relay, profile=openai_relay_profile)
        payload = dict(payload)
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

        text_parts: list[str] = []
        reasoning_parts: list[str] | None = [] if capture_reasoning else None
        tool_calls: dict[int, dict[str, str]] = {}
        finish_reason: str | None = None
        usage: dict[str, Any] | None = None
        first_chunk_seen = False

        stream_kwargs: dict[str, Any] = {"json": payload}
        per_call_timeout = self._resolve_per_call_timeout(tier)
        if per_call_timeout is not None:
            stream_kwargs["timeout"] = per_call_timeout

        with client.stream(
            "POST",
            self._get_openai_endpoint(relay, profile=openai_relay_profile),
            **stream_kwargs,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                if not line:
                    continue
                if line.startswith("data: "):
                    line = line[6:]
                if line == "[DONE]":
                    break
                try:
                    data = json.loads(line)
                except json.JSONDecodeError:
                    continue

                if on_first_chunk is not None and not first_chunk_seen:
                    first_chunk_seen = True
                    on_first_chunk({
                        "transport": "openai_stream",
                        "line_preview": line[:120],
                    })

                if data.get("usage"):
                    usage = data["usage"]
                choices = data.get("choices") or []
                if not choices:
                    continue
                choice = choices[0]
                finish_reason = choice.get("finish_reason") or finish_reason
                delta = choice.get("delta") or {}

                content = delta.get("content")
                if isinstance(content, str) and content:
                    text_parts.append(content)

                # Capture reasoning_content from kimi-k2.5 thinking
                if reasoning_parts is not None:
                    reasoning = delta.get("reasoning_content")
                    if isinstance(reasoning, str) and reasoning:
                        reasoning_parts.append(reasoning)

                for tool_delta in delta.get("tool_calls") or []:
                    index = tool_delta.get("index", 0)
                    entry = tool_calls.setdefault(index, {"id": "", "name": "", "arguments": ""})
                    if tool_delta.get("id"):
                        entry["id"] = tool_delta["id"]
                    function = tool_delta.get("function") or {}
                    if function.get("name"):
                        entry["name"] = function["name"]
                    if function.get("arguments"):
                        entry["arguments"] += function["arguments"]

        reasoning_text = "".join(reasoning_parts) if reasoning_parts else ""
        full_text = "".join(text_parts)

        # Gemini relays may inline thinking as <think>...</think> in the
        # content stream instead of using reasoning_content deltas.  Split
        # them out so that _extract_thinking() can surface the thinking text.
        if not reasoning_text and "<think>" in full_text:
            think_reasoning, full_text = self._split_think_tags(full_text)
            if think_reasoning:
                reasoning_text = think_reasoning

        sorted_tools = [entry for _, entry in sorted(tool_calls.items())]

        # ── proxy.example.com / some relays unparseable-response detection ──────
        # Two empirical failure modes (2026-04-28 log analysis) that produce
        # missing-decision warnings on the Gemini 3.1 Pro strategic tier:
        #
        # CASE A: stream [DONE] without finish_reason chunk; <decision> opened
        # but never closed.  Original empirical evidence: 112/114 missing-
        # decision warnings correlated with empty finish_reason on previous
        # runs that had partial visible output.
        #
        # CASE B: visible text channel is empty despite the response having
        # consumed output tokens.  Gemini via some relays spent the entire output
        # budget on reasoning_content (server-side thinking) and emitted no
        # visible answer.  Confirmed in run_20260428_013322: raw_len=0 across
        # 9/9 warnings while completion_tokens=4311.
        #
        # Both shapes will fail extract_decision at the V2Engine layer.
        # Raising here triggers LLMRouter model_switch (gemini → gpt-5.4 on
        # a clean context) which costs ~20s on a fresh model vs ~35s for a
        # repair turn on the same corrupted Gemini state.
        completion_tokens = (
            (usage or {}).get("completion_tokens") or 0
        ) if isinstance(usage, dict) else 0
        case_a_truncated = (
            not finish_reason
            and "<decision>" in full_text
            and "</decision>" not in full_text
        )
        case_b_empty_visible = (
            not full_text.strip()
            and (bool(reasoning_text) or completion_tokens > 0)
        )
        if not sorted_tools and (case_a_truncated or case_b_empty_visible):
            reason = "truncated_decision" if case_a_truncated else "empty_visible_with_tokens"
            # Diagnostic detail at DEBUG only — call_raw logs a WARNING per
            # retry attempt with the same essentials, so emitting a second
            # WARNING here would double the user-visible noise on every
            # retry of a transient proxy-truncation event.
            logger.debug(
                "V2Backend: unparseable response (%s) "
                "model=%s finish=%s text_len=%d reasoning_len=%d completion_tok=%d",
                reason,
                payload.get("model", "?"),
                finish_reason or "(empty)",
                len(full_text),
                len(reasoning_text),
                completion_tokens,
            )
            # HARD failure: classify_failure picks up the "unparseable
            # response" marker in the message text, so the router switches
            # to the next model in the chain on the first occurrence.
            # Same-model retry was the original design but the empirical
            # success rate (run 20260428_024454: 37 fails, retries took
            # 2-3 attempts each) made it ~2x worse than the older
            # V2Engine repair-turn path, so we fall over fast instead.
            raise UnparseableLLMResponse(
                f"unparseable response ({reason}): model={payload.get('model','?')} "
                f"finish={finish_reason or 'none'} text_len={len(full_text)} "
                f"reasoning_len={len(reasoning_text)} completion_tok={completion_tokens}",
            )

        if not full_text and not sorted_tools:
            # Reachable only when reasoning_text and completion_tokens are
            # both empty — i.e. the stream really delivered nothing.
            # Existing behavior preserved: warn and return empty msg
            # (caller's repair turn will handle it).
            logger.warning(
                "V2Backend: OpenAI-compatible stream returned empty response "
                "(0 text chunks, 0 tool calls, finish_reason=%s, model=%s)",
                finish_reason,
                payload.get("model", "?"),
            )
        msg = self._make_openai_message(
            model=payload["model"],
            finish_reason=finish_reason,
            text_content=full_text,
            tool_calls=sorted_tools,
            usage=usage,
        )
        # Attach reasoning_content for multi-turn passback
        if reasoning_text:
            msg._reasoning_content = reasoning_text
        return msg

    # ── Synchronous call ────────────────────────────────────────

    def call(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        think: bool = False,
        think_budget: int = 0,
        effort: str = "",
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        on_first_chunk: Callable[[dict[str, Any]], None] | None = None,
        openai_relay_profile: str = "default",
        response_format: dict[str, Any] | None = None,
        tier: str | None = None,
    ) -> anthropic.Message:
        """Send a request to Claude and return the full Message object.

        Args:
            system: System prompt text.
            messages: Full conversation history (list of role/content dicts).
            model: Model ID override. Defaults to ``config.LLM_MODEL``.
            think: Whether to enable extended thinking.
            think_budget: Token budget for extended thinking. Used with
                ``LLM_THINK_TYPE=enabled`` (legacy). Ignored for adaptive.
            effort: Effort level for adaptive thinking (``"low"``, ``"medium"``,
                ``"high"``). Used with ``LLM_THINK_TYPE=adaptive``.
            tools: List of Anthropic tool schemas.
            tool_choice: Tool choice parameter (``auto``, ``none``, or forced).
            max_tokens: Override ``config.LLM_MAX_TOKENS``.
            temperature: Override ``config.LLM_TEMPERATURE``.

        Returns:
            The full ``anthropic.Message`` response object.

        Raises:
            anthropic.RateLimitError: After a brief backoff (caller should retry).
            anthropic.APIError: For non-rate-limit API errors.
        """
        t0 = time.monotonic()
        self._ensure_runtime_state()
        use_model = model or self._default_model
        use_provider = config.normalize_provider(provider or config.LLM_PROVIDER)
        client: Any | None = None

        # Prompt caching is provider-specific in the current routing setup:
        # - Anthropic SDK calls may be forced to no-cache via
        #   STS2_ANTHROPIC_DISABLE_CACHE / STS2_OPUS_DISABLE_CACHE, which adds
        #   Cache-Control headers in _make_client().
        # - OpenAI-compatible calls (for example kimi-k2.5 gameplay routing)
        #   do not send an explicit cache toggle here; they rely on whatever
        #   prompt caching the upstream relay/provider applies automatically.
        kwargs: dict[str, Any] = {
            "model": use_model,
            "messages": messages,
        }

        kwargs["system"] = self._maybe_add_proxy_tool_reasoning_guard(
            system=system,
            tools=tools,
        )
        self._last_cache_read = 0
        self._last_cache_creation = 0
        self._last_prefix_hash = ""
        self._last_transport_target = ""

        # Extended thinking — choose between adaptive (4.6+) and legacy (enabled + budget)
        if think:
            think_type = config.LLM_THINK_TYPE

            if think_type == "adaptive":
                # Adaptive thinking: Claude decides when/how much to think.
                # Controlled by effort level, NOT budget_tokens.
                kwargs["thinking"] = {"type": "adaptive"}
                use_effort = effort or "medium"
                kwargs["output_config"] = {"effort": use_effort}
                # max_tokens covers both thinking + response text
                _effort_max = {"low": 8192, "medium": 12000, "high": 16000, "max": 32000}
                base_max = max_tokens or config.LLM_MAX_TOKENS
                kwargs["max_tokens"] = max(base_max, _effort_max.get(use_effort, 12000))
            else:
                # Legacy: type=enabled + budget_tokens (deprecated on 4.6 but functional)
                budget = think_budget if think_budget > 0 else 4000
                kwargs["thinking"] = {
                    "type": "enabled",
                    "budget_tokens": budget,
                }
                base_max = max_tokens or config.LLM_MAX_TOKENS
                kwargs["max_tokens"] = budget + base_max

            # Anthropic requires temperature=1.0 when thinking is enabled
            kwargs["temperature"] = 1.0
        else:
            kwargs["max_tokens"] = max_tokens or config.LLM_MAX_TOKENS
            kwargs["temperature"] = (
                temperature if temperature is not None else config.LLM_TEMPERATURE
            )

        # Tool use
        if tools:
            kwargs["tools"] = tools
            if tool_choice:
                # With thinking enabled, only "auto" or "none" is allowed
                if think and tool_choice.get("type") == "tool":
                    kwargs["tool_choice"] = {"type": "auto"}
                else:
                    kwargs["tool_choice"] = tool_choice

        try:
            if use_provider == "anthropic":
                client = self._get_client(use_model)
                self._last_transport_target = (
                    config.OPUS_BASE_URL
                    if client is self._opus_client and config.OPUS_BASE_URL
                    else (config.ANTHROPIC_BASE_URL or "Anthropic default endpoint")
                )
                # Some Anthropic-compatible proxies mishandle non-streaming aggregation
                # and drop later content blocks (for example thinking/tool_use).
                # Streaming returns the correct final message on those proxies, so only
                # use it for tool-bearing calls over a custom base URL.
                use_stream = bool(tools and config.ANTHROPIC_BASE_URL)
                if use_stream:
                    response = self._call_via_raw_stream(
                        client,
                        kwargs,
                        on_first_chunk=on_first_chunk,
                    )
                else:
                    response = client.messages.create(**kwargs)
            elif use_provider == "openai_compatible":
                use_stream = bool(tools)
                response = self._call_openai_compatible(
                    system=kwargs["system"],
                    messages=messages,
                    model=use_model,
                    think=think,
                    effort=effort,
                    tools=tools,
                    tool_choice=tool_choice,
                    max_tokens=kwargs.get("max_tokens"),
                    temperature=kwargs.get("temperature"),
                    on_first_chunk=on_first_chunk,
                    openai_relay_profile=openai_relay_profile,
                    response_format=response_format,
                    tier=tier,
                )
            else:
                raise ValueError(f"Unsupported V2 provider: {use_provider}")
        except AssertionError as exc:
            if "Raw stream ended without message_start" not in str(exc):
                raise  # Re-raise unrelated assertions
            # Proxy returned empty stream — fall back to non-streaming call.
            logger.warning(
                "V2Backend: streaming returned empty response, falling back to non-streaming"
            )
            if client is None:
                raise
            response = client.messages.create(**kwargs)
        except httpx.HTTPError as exc:
            err = self._format_http_error_for_log(exc)
            logger.error("V2Backend OpenAI-compatible HTTP error: %s", err)
            raise
        except Exception as exc:
            if self._is_anthropic_rate_limit_error(exc):
                logger.warning("V2Backend rate limited: %s — caller should retry", exc)
                time.sleep(2)  # Brief backoff
                raise
            if self._is_anthropic_api_error(exc):
                logger.error("V2Backend API error: %s", exc)
                raise
            raise

        latency_ms = (time.monotonic() - t0) * 1000

        # Logging
        usage = response.usage
        total_tokens = usage.input_tokens + usage.output_tokens
        cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
        cache_creation = getattr(usage, "cache_creation_input_tokens", 0) or 0
        self._last_cache_read = cache_read
        self._last_cache_creation = cache_creation

        if (
            config.ANTHROPIC_DISABLE_CACHE
            and cache_creation > 0
            and not self._warned_cache_ignored
        ):
            logger.warning(
                "V2Backend: upstream still reported cache creation (%d tokens) even though "
                "STS2_ANTHROPIC_DISABLE_CACHE is enabled. This usually means the proxy at %s "
                "is auto-injecting prompt cache server-side.",
                cache_creation,
                config.ANTHROPIC_BASE_URL or "Anthropic default endpoint",
            )
            self._warned_cache_ignored = True

        tags = []
        if think:
            tags.append("THINK")
        if tools:
            tags.append("TOOL")
        if use_stream:
            tags.append("STREAM")
        tag_str = " ".join(f"[{t}]" for t in tags)
        if tag_str:
            tag_str = " " + tag_str

        logger.info(
            "V2Backend%s: provider=%s model=%s target=%s %.0fms %dtok "
            "(cache_read=%d cache_create=%d prefix=%s) stop=%s",
            tag_str,
            use_provider,
            use_model,
            self._last_transport_target or "-",
            latency_ms,
            total_tokens,
            cache_read,
            cache_creation,
            self._last_prefix_hash or "-",
            response.stop_reason,
        )

        return response

    # ── Async wrapper ───────────────────────────────────────────

    async def acall(
        self,
        *,
        system: str,
        messages: list[dict[str, Any]],
        provider: str | None = None,
        model: str | None = None,
        think: bool = False,
        think_budget: int = 0,
        effort: str = "",
        tools: list[dict[str, Any]] | None = None,
        tool_choice: dict[str, Any] | None = None,
        max_tokens: int | None = None,
        temperature: float | None = None,
        on_first_chunk: Callable[[dict[str, Any]], None] | None = None,
        openai_relay_profile: str = "default",
        allow_hedge: bool = True,
        response_format: dict[str, Any] | None = None,
        tier: str | None = None,
    ) -> anthropic.Message:
        """Async version of :meth:`call` with optional hedged racing.

        When hedging is enabled (``config.OPENAI_COMPAT_HEDGE_ENABLED``) and
        the provider is ``openai_compatible``, a second identical request is
        launched if the first chunk does not arrive within
        ``config.OPENAI_COMPAT_FIRST_CHUNK_DEADLINE_SEC``.  The first request
        to fully complete wins; the other is discarded.

        Args:
            allow_hedge: When ``False``, hedging is suppressed regardless of
                config.  The health-aware router sets this to ``False`` when
                the selected model's circuit breaker is not CLOSED, to avoid
                generating duplicate traffic on a model that recently failed.
        """
        call_kwargs: dict[str, Any] = dict(
            system=system,
            messages=messages,
            provider=provider,
            model=model,
            think=think,
            think_budget=think_budget,
            effort=effort,
            tools=tools,
            tool_choice=tool_choice,
            max_tokens=max_tokens,
            temperature=temperature,
            openai_relay_profile=openai_relay_profile,
            response_format=response_format,
            tier=tier,
        )

        resolved_provider = config.normalize_provider(provider or config.LLM_PROVIDER)
        hedge_eligible = (
            allow_hedge
            and config.OPENAI_COMPAT_HEDGE_ENABLED
            and resolved_provider == "openai_compatible"
            and config.OPENAI_COMPAT_FIRST_CHUNK_DEADLINE_SEC > 0
            and openai_relay_profile != "postrun"
        )

        if not hedge_eligible:
            return await asyncio.to_thread(
                self.call, **call_kwargs, on_first_chunk=on_first_chunk,
            )

        # ── Hedged racing ──────────────────────────────────────────
        first_chunk_event = threading.Event()
        original_cb = on_first_chunk

        def _primary_first_chunk_cb(meta: dict[str, Any]) -> None:
            first_chunk_event.set()
            if original_cb:
                original_cb(meta)

        loop = asyncio.get_running_loop()

        def _run_primary() -> anthropic.Message:
            try:
                return self.call(**call_kwargs, on_first_chunk=_primary_first_chunk_cb)
            finally:
                # Ensure the event is set even for non-streaming calls
                # (where on_first_chunk is never invoked by the transport).
                first_chunk_event.set()

        # Launch primary request in thread pool
        primary_future = loop.run_in_executor(None, _run_primary)

        # Wait for first chunk OR deadline
        deadline = config.OPENAI_COMPAT_FIRST_CHUNK_DEADLINE_SEC
        got_chunk = await asyncio.to_thread(first_chunk_event.wait, deadline)

        if got_chunk:
            # First chunk arrived in time — just await primary completion
            return await asyncio.wrap_future(primary_future)

        # Deadline exceeded — check if primary already finished (error or fast completion)
        if primary_future.done():
            return primary_future.result()

        logger.warning(
            "V2Backend: first chunk deadline (%.0fs) exceeded — launching hedge request",
            deadline,
        )

        def _hedge_first_chunk_cb(meta: dict[str, Any]) -> None:
            if original_cb:
                meta = {**meta, "hedge": True}
                original_cb(meta)

        hedge_future = loop.run_in_executor(
            None,
            lambda: self.call(**call_kwargs, on_first_chunk=_hedge_first_chunk_cb),
        )

        # Race primary vs hedge — first to complete wins
        primary_task = asyncio.ensure_future(asyncio.wrap_future(primary_future))
        hedge_task = asyncio.ensure_future(asyncio.wrap_future(hedge_future))

        done, pending = await asyncio.wait(
            {primary_task, hedge_task},
            return_when=asyncio.FIRST_COMPLETED,
        )

        winner = done.pop()
        winner_label = "primary" if winner is primary_task else "hedge"

        # Cancel the loser — the underlying thread will eventually finish on its
        # own (we cannot forcibly kill it), but we drop the result.
        for loser in pending:
            loser.cancel()
            loser_label = "hedge" if loser is hedge_task else "primary"
            logger.info(
                "V2Backend: hedged race won by %s — discarding %s",
                winner_label,
                loser_label,
            )

        # Propagate exception if the winner failed
        return winner.result()

    # ── Helpers ─────────────────────────────────────────────────

    @staticmethod
    def extract_text(response: anthropic.Message) -> str:
        """Extract the first text block from a Message, or empty string."""
        for block in response.content:
            if V2Backend._block_type(block) == "text":
                text = V2Backend._block_attr(block, "text")
                if isinstance(text, str) and text.strip():
                    return text.strip()
        return ""

    @staticmethod
    def extract_tool_uses(response: anthropic.Message) -> list[dict[str, Any]]:
        """Extract all tool_use blocks from a Message.

        Returns a list of dicts with keys: ``id``, ``name``, ``input``.
        """
        results: list[dict[str, Any]] = []
        for block in response.content:
            if V2Backend._block_type(block) == "tool_use":
                results.append({
                    "id": V2Backend._block_attr(block, "id"),
                    "name": V2Backend._block_attr(block, "name"),
                    "input": V2Backend._block_attr(block, "input"),
                })
        return results

    @staticmethod
    def build_tool_result(
        tool_use_id: str,
        content: str,
        *,
        is_error: bool = False,
    ) -> dict[str, Any]:
        """Build a ``tool_result`` message block for multi-turn tool use.

        Args:
            tool_use_id: The ``id`` from the tool_use block in the response.
            content: The result text to return to Claude.
            is_error: Whether this result represents an error.

        Returns:
            A dict suitable for appending to the messages list as a
            ``{"role": "user", "content": [...]}`` block.
        """
        return {
            "type": "tool_result",
            "tool_use_id": tool_use_id,
            "content": content,
            "is_error": is_error,
        }
