"""Batch manager for Anthropic Message Batches API — drain-only.

Historically this module submitted post-run skill discovery tasks as a
batch for 50% cost savings. After the 2026-04-23 non-combat discovery
removal, no production code submits new batches. ``check_completed`` is
retained so that legacy in-flight batches from older agent versions
(and any future Batch API consumers) still get drained when their
results are ready.

Guide consolidation and rule distillation stay synchronous so they
operate on the freshest in-memory run data.
"""

from __future__ import annotations

import json
import logging
import os
import time

import config

logger = logging.getLogger(__name__)

_PENDING_FILE = os.path.join(config.DATA_DIR, "batch_pending.json")


def _load_pending() -> list[dict]:
    if os.path.exists(_PENDING_FILE):
        try:
            with open(_PENDING_FILE) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return []


def _save_pending(pending: list[dict]) -> None:
    os.makedirs(os.path.dirname(_PENDING_FILE), exist_ok=True)
    with open(_PENDING_FILE, "w") as f:
        json.dump(pending, f, indent=2)


def check_completed() -> list[tuple[list[dict], dict[str, str]]]:
    """Check all pending batches for completion.

    Returns:
        List of (tasks_meta, results_dict) for each completed batch.
        results_dict maps custom_id → raw LLM text.
    """
    pending = _load_pending()
    if not pending:
        return []

    try:
        import anthropic
        kwargs: dict = {}
        if config.LLM_API_KEY:
            kwargs["api_key"] = config.LLM_API_KEY
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        client = anthropic.Anthropic(**kwargs)
    except Exception:
        return []

    completed: list[tuple[list[dict], dict[str, str]]] = []
    still_pending: list[dict] = []

    for entry in pending:
        batch_id = entry["batch_id"]
        try:
            batch = client.messages.batches.retrieve(batch_id)
            if batch.processing_status == "ended":
                results: dict[str, str] = {}
                for result in client.messages.batches.results(batch_id):
                    if result.result.type == "succeeded":
                        text = ""
                        for block in result.result.message.content:
                            if hasattr(block, "type") and block.type == "text":
                                text = block.text
                                break
                        results[result.custom_id] = text
                    else:
                        logger.warning(
                            "Batch result %s: %s", result.custom_id, result.result.type,
                        )
                completed.append((entry["tasks"], results))
                logger.info(
                    "Batch completed: %s (%d/%d succeeded)",
                    batch_id, len(results), len(entry["tasks"]),
                )
            else:
                still_pending.append(entry)
        except Exception as e:
            logger.warning("Batch check failed for %s: %s", batch_id, e)
            age_hours = (time.time() - entry.get("created_at", 0)) / 3600
            if age_hours < 24:
                still_pending.append(entry)
            else:
                logger.warning("Batch %s expired (%.1fh), dropping", batch_id, age_hours)

    _save_pending(still_pending)
    return completed
