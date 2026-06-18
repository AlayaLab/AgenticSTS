"""Minimal example that mirrors the repo's current LLM API path.

Current effective defaults in this workspace:
  - provider: openai_compatible
  - base_url: https://proxy.example.com
  - model: gpt-5.4 (from config default when .env does not override it)

This script uses the real in-repo ``V2Backend`` so you can see the same
routing/config path the agent uses today.

Run:
    python -m scripts.example_current_api_call
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


# Replace this before making a real request.
PROVIDER = "openai_compatible"
BASE_URL = "https://proxy.example.com"
MODEL = "gpt-5.4"
API_KEY = "<your-openai-compatible-api-key>"  # never commit a real key

# ``think=True`` on GPT-5 adds ``reasoning_effort`` in the current backend.
THINK = True
EFFORT = "medium"

SYSTEM_PROMPT = "You are a concise assistant. Answer in Chinese in one short paragraph."
USER_PROMPT = "简要说明这个仓库当前是怎么调用 LLM API 的。"


def resolve_openai_endpoint(base_url: str) -> str:
    """Match ``V2Backend._get_openai_endpoint()``."""
    base = base_url.rstrip("/")
    if base.endswith("/chat/completions"):
        return base
    if base.endswith("/v1"):
        return f"{base}/chat/completions"
    return f"{base}/v1/chat/completions"


def build_payload_preview() -> dict[str, object]:
    """Build a preview matching the current GPT-5 OpenAI-compatible path."""
    max_tokens = 4096
    temperature = 0
    reasoning_effort = None

    if THINK:
        temperature = 1.0
        if MODEL.startswith("gpt-5"):
            reasoning_effort = EFFORT
            max_tokens = max(
                max_tokens,
                {
                    "low": 8192,
                    "medium": 12000,
                    "high": 16000,
                    "xhigh": 32000,
                }.get(EFFORT, 12000),
            )

    payload: dict[str, object] = {
        "model": MODEL,
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": USER_PROMPT},
        ],
        "max_tokens": max_tokens,
        "temperature": temperature,
    }
    if reasoning_effort:
        payload["reasoning_effort"] = reasoning_effort
    return payload


def extract_text(response: object) -> str:
    parts: list[str] = []
    for block in getattr(response, "content", []) or []:
        text = getattr(block, "text", None)
        if isinstance(text, str) and text:
            parts.append(text)
    return "\n".join(parts).strip()


def main() -> None:
    os.environ["LLM_PROVIDER"] = PROVIDER
    os.environ["OPENAI_COMPAT_BASE_URL"] = BASE_URL
    os.environ["OPENAI_COMPAT_API_KEY"] = API_KEY
    os.environ["LLM_MODEL"] = MODEL

    endpoint = resolve_openai_endpoint(BASE_URL)
    payload_preview = build_payload_preview()

    print("Current-style config:")
    print(json.dumps({
        "provider": PROVIDER,
        "base_url": BASE_URL,
        "resolved_endpoint": endpoint,
        "model": MODEL,
        "api_key": API_KEY,
        "think": THINK,
        "effort": EFFORT,
    }, ensure_ascii=False, indent=2))
    print()
    print("Approx HTTP request body:")
    print(json.dumps(payload_preview, ensure_ascii=False, indent=2))
    print()

    if "REPLACE_WITH_YOUR" in API_KEY:
        print("API_KEY 还是占位符，当前只展示配置和请求体预览。")
        print("把脚本顶部的 API_KEY 改成真实值后，再运行就会真的发请求。")
        return

    import config  # noqa: PLC0415
    from src.brain.v2_backend import V2Backend  # noqa: PLC0415

    backend = V2Backend()
    response = backend.call(
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": USER_PROMPT}],
        provider=PROVIDER,
        model=MODEL,
        think=THINK,
        effort=EFFORT,
        max_tokens=config.LLM_MAX_TOKENS,
    )

    usage = getattr(response, "usage", None)
    print("Response text:")
    print(extract_text(response))
    print()
    print("Usage:")
    print(json.dumps({
        "input_tokens": getattr(usage, "input_tokens", 0) if usage else 0,
        "output_tokens": getattr(usage, "output_tokens", 0) if usage else 0,
        "stop_reason": getattr(response, "stop_reason", None),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
