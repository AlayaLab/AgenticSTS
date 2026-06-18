"""Uniform LLM-capture proxy for competitor comparison runs.

An OpenAI-compatible reverse proxy that sits between any competitor agent
(AI-Spire's C# client, our naive Gemini MCP agent, OpenCode driving
HermesBridge, ...) and our real Gemini relay. Every ``/v1/chat/completions``
exchange is logged to disk as one JSONL record so that all competitor
trajectories carry identical, complete prompt/response capture regardless
of each agent's own (often absent) logging.

This is the dataset-capture mechanism for Workstream C. The captured
records are the released-dataset payload for competitor cells.

Usage
-----
    # upstream Gemini relay comes from the same .env the agent uses
    python -m scripts.competitor_runs.logging_proxy --port 8129

    # then point the competitor agent at the proxy, e.g. AI-Spire config.json:
    #   "api_endpoint": "http://localhost:8129/v1/chat/completions"
    #   "model": "gemini-3.1-pro-preview"
    # and tag each run via the X-Run-Id request header (or PROXY_RUN_ID env).

Captured files
--------------
    captures/<run_id>/llm_calls.jsonl   one record per completion
    captures/<run_id>/meta.json         run-level metadata (model, start, counts)

Each llm_calls.jsonl record:
    {
      "seq": 1,
      "run_id": "...",
      "ts_request": "<iso8601>",
      "ts_response": "<iso8601>",
      "latency_ms": 1234,
      "request": { ...verbatim OpenAI-compatible request body... },
      "response": { ...assembled response body... },
      "streamed": true/false,
      "status_code": 200,
      "usage": { ...token usage if present... },
      "error": null
    }

Design notes
------------
* Streaming (``text/event-stream``) is teed: chunks forward to the caller
  in real time while a copy is assembled for the log, so the proxy never
  changes the agent's observed behaviour.
* The upstream relay + key are read from the env the rest of the project
  uses (``STS2_GEMINI_BASE_URL`` / ``STS2_GEMINI_API_KEY``), with explicit
  overrides (``COMPETITOR_PROXY_UPSTREAM_URL`` / ``..._KEY``).
* No dependency beyond what the repo already pins: ``fastapi`` + ``uvicorn``
  (``.[monitor]`` extra) and ``httpx`` (base).
"""

from __future__ import annotations

import argparse
import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse

from scripts.competitor_runs import _bootstrap as _bootstrap  # noqa: F401  (loads .env)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


def _utcnow_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _resolve_upstream() -> tuple[str, str]:
    """Return (chat_completions_url, api_key) for the upstream Gemini relay.

    Precedence: explicit COMPETITOR_PROXY_UPSTREAM_* overrides, then the
    project's standard STS2_GEMINI_* env vars.
    """
    url = os.environ.get("COMPETITOR_PROXY_UPSTREAM_URL")
    key = os.environ.get("COMPETITOR_PROXY_UPSTREAM_KEY") or os.environ.get(
        "STS2_GEMINI_API_KEY", ""
    )
    if not url:
        base = os.environ.get("STS2_GEMINI_BASE_URL", "").rstrip("/")
        if not base:
            raise SystemExit(
                "No upstream configured. Set COMPETITOR_PROXY_UPSTREAM_URL "
                "(full /chat/completions URL) or STS2_GEMINI_BASE_URL in .env."
            )
        # Mirror the main app's endpoint logic (v2_backend._get_openai_endpoint):
        # relays like proxy.example.com expose the OpenAI-compatible API under /v1, so a
        # bare base must get /v1/chat/completions (a plain /chat/completions 307s to
        # a login page).
        if base.endswith("/chat/completions"):
            url = base
        elif base.endswith("/v1"):
            url = base + "/chat/completions"
        else:
            url = base + "/v1/chat/completions"
    if not key:
        raise SystemExit(
            "No upstream API key. Set COMPETITOR_PROXY_UPSTREAM_KEY or "
            "STS2_GEMINI_API_KEY in .env."
        )
    return url, key


class CaptureWriter:
    """Append-only JSONL writer, one directory per run_id."""

    def __init__(self, root: Path) -> None:
        self._root = root
        self._seq: dict[str, int] = {}

    def _run_dir(self, run_id: str) -> Path:
        d = self._root / run_id
        d.mkdir(parents=True, exist_ok=True)
        return d

    def next_seq(self, run_id: str) -> int:
        n = self._seq.get(run_id, 0) + 1
        self._seq[run_id] = n
        return n

    def write_call(self, run_id: str, record: dict[str, Any]) -> None:
        path = self._run_dir(run_id) / "llm_calls.jsonl"
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def touch_meta(self, run_id: str, model: str) -> None:
        path = self._run_dir(run_id) / "meta.json"
        if path.exists():
            return
        meta = {
            "run_id": run_id,
            "model": model,
            "started_at": _utcnow_iso(),
            "proxy": "competitor_runs.logging_proxy",
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(meta, f, indent=2)


# ---------------------------------------------------------------------------
# SSE assembly (OpenAI streaming -> single assembled response body)
# ---------------------------------------------------------------------------


def _assemble_stream(chunks: list[bytes]) -> dict[str, Any]:
    """Reassemble an OpenAI-style SSE stream into a single response dict.

    Best-effort: concatenates delta.content across choices[0] and captures
    the final usage block if the upstream emits one. Never raises — capture
    must not crash the proxy.
    """
    text = b"".join(chunks).decode("utf-8", errors="replace")
    content_parts: list[str] = []
    # tool_calls stream as fragments keyed by index; id/name arrive once,
    # function.arguments arrives in pieces that must be concatenated in order.
    tool_calls_acc: dict[int, dict[str, Any]] = {}
    role = "assistant"
    finish_reason: str | None = None
    usage: dict[str, Any] | None = None
    model: str | None = None
    n_events = 0

    for line in text.splitlines():
        line = line.strip()
        if not line or not line.startswith("data:"):
            continue
        payload = line[len("data:"):].strip()
        if payload == "[DONE]":
            break
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            continue
        n_events += 1
        model = obj.get("model", model)
        if obj.get("usage"):
            usage = obj["usage"]
        for choice in obj.get("choices", []):
            delta = choice.get("delta", {})
            if delta.get("role"):
                role = delta["role"]
            if delta.get("content"):
                content_parts.append(delta["content"])
            for tc in delta.get("tool_calls", []) or []:
                idx = tc.get("index", 0)
                slot = tool_calls_acc.setdefault(
                    idx,
                    {"id": None, "type": "function", "function": {"name": "", "arguments": ""}},
                )
                if tc.get("id"):
                    slot["id"] = tc["id"]
                if tc.get("type"):
                    slot["type"] = tc["type"]
                fn = tc.get("function", {}) or {}
                if fn.get("name"):
                    slot["function"]["name"] = fn["name"]
                if fn.get("arguments"):
                    slot["function"]["arguments"] += fn["arguments"]
            if choice.get("finish_reason"):
                finish_reason = choice["finish_reason"]

    message: dict[str, Any] = {"role": role, "content": "".join(content_parts)}
    if tool_calls_acc:
        message["tool_calls"] = [tool_calls_acc[k] for k in sorted(tool_calls_acc)]
    assembled: dict[str, Any] = {
        "model": model,
        "choices": [{"index": 0, "message": message, "finish_reason": finish_reason}],
    }
    if usage:
        assembled["usage"] = usage
    assembled["_stream_event_count"] = n_events
    return assembled


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------


def build_app(captures_root: Path) -> FastAPI:
    app = FastAPI(title="competitor-runs logging proxy")
    upstream_url, upstream_key = _resolve_upstream()
    writer = CaptureWriter(captures_root)
    # Long timeout: Gemini 3.1 Pro with thinking can take >60s; never cut off.
    client = httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=15.0))

    def _run_id(request: Request, body: dict[str, Any]) -> str:
        return (
            request.headers.get("x-run-id")
            or os.environ.get("PROXY_RUN_ID")
            or "default"
        )

    @app.get("/health")
    async def health() -> dict[str, Any]:
        return {"ok": True, "upstream": upstream_url, "captures": str(captures_root)}

    @app.post("/v1/chat/completions")
    @app.post("/chat/completions")
    async def chat_completions(request: Request):  # noqa: ANN201
        raw = await request.body()
        try:
            body = json.loads(raw)
        except json.JSONDecodeError:
            return JSONResponse(
                {"error": "proxy: request body is not valid JSON"}, status_code=400
            )

        run_id = _run_id(request, body)
        model = str(body.get("model", "unknown"))
        writer.touch_meta(run_id, model)
        seq = writer.next_seq(run_id)
        wants_stream = bool(body.get("stream", False))

        fwd_headers = {
            "Authorization": f"Bearer {upstream_key}",
            "Content-Type": "application/json",
        }
        ts_request = _utcnow_iso()
        t0 = time.monotonic()

        # --- streaming path -------------------------------------------------
        if wants_stream:
            collected: list[bytes] = []

            async def event_stream():
                status_code = 200
                error: str | None = None
                try:
                    async with client.stream(
                        "POST", upstream_url, headers=fwd_headers, content=raw
                    ) as resp:
                        status_code = resp.status_code
                        async for chunk in resp.aiter_bytes():
                            collected.append(chunk)
                            yield chunk
                except Exception as exc:  # capture must not crash the caller
                    error = f"{type(exc).__name__}: {exc}"
                    # Give a streaming client a terminus instead of a silent cut-off.
                    terminus = (
                        "data: "
                        + json.dumps({"error": {"message": error}})
                        + "\n\ndata: [DONE]\n\n"
                    )
                    yield terminus.encode("utf-8")
                finally:
                    latency_ms = int((time.monotonic() - t0) * 1000)
                    assembled = _assemble_stream(collected) if collected else None
                    writer.write_call(
                        run_id,
                        {
                            "seq": seq,
                            "run_id": run_id,
                            "ts_request": ts_request,
                            "ts_response": _utcnow_iso(),
                            "latency_ms": latency_ms,
                            "request": body,
                            "response": assembled,
                            "streamed": True,
                            "status_code": status_code,
                            "usage": (assembled or {}).get("usage"),
                            "error": error,
                        },
                    )

            return StreamingResponse(
                event_stream(), media_type="text/event-stream"
            )

        # --- non-streaming path --------------------------------------------
        status_code = 200
        error: str | None = None
        resp_body: dict[str, Any] | None = None
        try:
            resp = await client.post(upstream_url, headers=fwd_headers, content=raw)
            status_code = resp.status_code
            try:
                resp_body = resp.json()
            except json.JSONDecodeError:
                resp_body = {"_raw_text": resp.text}
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

        latency_ms = int((time.monotonic() - t0) * 1000)
        writer.write_call(
            run_id,
            {
                "seq": seq,
                "run_id": run_id,
                "ts_request": ts_request,
                "ts_response": _utcnow_iso(),
                "latency_ms": latency_ms,
                "request": body,
                "response": resp_body,
                "streamed": False,
                "status_code": status_code,
                "usage": (resp_body or {}).get("usage") if resp_body else None,
                "error": error,
            },
        )

        if error is not None:
            return JSONResponse(
                {"error": f"proxy upstream failure: {error}"}, status_code=502
            )
        return JSONResponse(resp_body, status_code=status_code)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8129)
    parser.add_argument(
        "--captures",
        default=str(Path(__file__).resolve().parent / "captures"),
        help="Directory root for per-run capture files.",
    )
    args = parser.parse_args()

    import uvicorn

    captures_root = Path(args.captures)
    captures_root.mkdir(parents=True, exist_ok=True)
    app = build_app(captures_root)
    print(f"[competitor-proxy] capturing to {captures_root}")
    print(f"[competitor-proxy] point agents at http://{args.host}:{args.port}/v1/chat/completions")
    uvicorn.run(app, host=args.host, port=args.port, log_level="info")


if __name__ == "__main__":
    main()
