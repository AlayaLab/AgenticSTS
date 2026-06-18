"""Serialization and artifact-writing helpers for the evolution stage.

Spec #4 module split: these functions used to live as methods of
EvolutionEngine. They moved here because they don't materially depend
on the class's full state — they read narrowly from the engine
instance (artifact_dir, session_logger, etc.) and write to disk / log
streams.

Each engine method now retains a 2-line delegator into the matching
function below. Tests calling engine._serialize_message(...),
engine._emit_artifact(...), etc. flow through the delegators
unchanged.
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def filter_response_content(response: Any) -> list[Any]:
    """(Extracted from EvolutionEngine._filter_response_content.)

    Filter out thinking blocks from an API response's content list.
    Returns a fallback list if all content is thinking-only.
    """
    return [
        block for block in getattr(response, "content", [])
        if not (
            (isinstance(block, dict) and block.get("type") == "thinking")
            or (hasattr(block, "type") and getattr(block, "type", None) == "thinking")
        )
    ] or [{"type": "text", "text": "(thinking only)"}]


def serialize_content(content: Any) -> Any:
    """(Extracted from EvolutionEngine._serialize_content.)

    Recursively serialize arbitrary content (lists, dicts, objects with
    __dict__, tuples, or primitives) into a JSON-safe structure. Keys
    starting with ``_`` are dropped from dict/object representations.
    """
    if isinstance(content, list):
        return [serialize_content(item) for item in content]
    if isinstance(content, dict):
        return {
            key: serialize_content(value)
            for key, value in content.items()
            if not key.startswith("_")
        }
    if hasattr(content, "__dict__"):
        return {
            key: serialize_content(value)
            for key, value in vars(content).items()
            if not key.startswith("_")
        }
    if isinstance(content, tuple):
        return [serialize_content(item) for item in content]
    return content


def serialize_message(message: dict[str, Any]) -> dict[str, Any]:
    """(Extracted from EvolutionEngine._serialize_message.)

    Serialize a single conversation message dict into a JSON-safe form,
    preserving the role and any ``_reasoning_content`` field.
    """
    payload = {"role": message.get("role", "")}
    if "_reasoning_content" in message:
        payload["_reasoning_content"] = message["_reasoning_content"]
    payload["content"] = serialize_content(message.get("content"))
    return payload


def serialize_response(response: Any) -> dict[str, Any]:
    """(Extracted from EvolutionEngine._serialize_response.)

    Serialize an API response object into a JSON-safe dict with
    stop_reason, content, and token-usage sub-dict.
    """
    usage = getattr(response, "usage", None)
    return {
        "stop_reason": getattr(response, "stop_reason", "") or "",
        "content": serialize_content(getattr(response, "content", [])),
        "usage": {
            "input_tokens": getattr(usage, "input_tokens", 0) or getattr(usage, "prompt_tokens", 0) or 0,
            "output_tokens": getattr(usage, "output_tokens", 0) or getattr(usage, "completion_tokens", 0) or 0,
            "cache_read_input_tokens": getattr(usage, "cache_read_input_tokens", 0) or 0,
        },
    }


def write_round_1_prompt_artifact(engine: Any, *, system_prompt: str, run_context: str) -> None:
    """(Extracted from EvolutionEngine._write_round_1_prompt_artifact.)

    Write the combined system prompt and round-1 user context to a
    markdown file in the engine's artifact directory. No-op if
    ``engine._artifact_dir`` is None.
    """
    if engine._artifact_dir is None:
        return
    engine._artifact_dir.mkdir(parents=True, exist_ok=True)
    prompt_path = engine._artifact_dir / "round_1_prompt.md"
    payload = (
        f"# Evolution System Prompt\n\n{system_prompt}\n\n"
        f"# Round 1 User Context\n\n{run_context}"
    )
    prompt_path.write_text(payload, encoding="utf-8")


def write_round_artifact(
    engine: Any,
    *,
    round_number: int,
    phase: str,
    messages: list[dict[str, Any]],
    model: str,
    tool_names: list[str],
    tool_choice: dict[str, Any] | None,
    response: Any | None = None,
    input_tokens: int = 0,
    output_tokens: int = 0,
    latency_ms: int = 0,
) -> None:
    """(Extracted from EvolutionEngine._write_round_artifact.)

    Write one round's request/response data (messages, model, token
    counts, latency) to a JSON file in the engine's artifact directory.
    No-op if ``engine._artifact_dir`` is None.
    """
    if engine._artifact_dir is None:
        return
    engine._artifact_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "round": round_number,
        "phase": phase,
        "model": model,
        "tool_names": tool_names,
        "tool_choice": tool_choice,
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "latency_ms": latency_ms,
        "messages": [serialize_message(message) for message in messages],
    }
    if response is not None:
        payload["response"] = serialize_response(response)
    artifact_path = engine._artifact_dir / f"round_{round_number}_messages.json"
    artifact_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def emit_artifact(
    engine: Any,
    *,
    kind: str,
    action: str = "write",
    target: str = "",
    summary: str = "",
    before: object = None,
    after: object = None,
    details: dict | None = None,
    source: str = "",
    stage: str = "evolution",
) -> None:
    """(Extracted from EvolutionEngine._emit_artifact.)

    Forward a postrun_artifact event to the session logger if present.
    Silently swallows exceptions so monitoring never crashes evolution.
    """
    sl = engine._session_logger
    if sl is None or not hasattr(sl, "log_postrun_artifact"):
        return
    try:
        sl.log_postrun_artifact(
            stage=stage,
            kind=kind,
            action=action,
            target=target,
            summary=summary,
            before=before,
            after=after,
            source=source,
            details=details,
        )
    except Exception:
        pass  # Monitoring never crashes evolution


def save_proposal(engine: Any, proposal_type: str, data: dict) -> str:
    """(Extracted from EvolutionEngine._save_proposal.)

    Save a proposal to the evolution log directory and return a success
    message string containing the written filename.
    """
    import time
    from src.storage import paths

    proposals_dir = paths.evolution_proposals_dir()
    proposals_dir.mkdir(parents=True, exist_ok=True)

    timestamp = time.time()
    # Use microsecond precision to avoid collisions within the same evolution session
    filename = f"{proposal_type}_{int(timestamp * 1000)}.json"
    filepath = proposals_dir / filename

    proposal = {
        "type": proposal_type,
        "timestamp": timestamp,
        **data,
    }
    filepath.write_text(json.dumps(proposal, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Saved evolution proposal: %s", filepath)
    return f"SUCCESS: Proposal saved to {filename} for human review."
