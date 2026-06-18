"""Shared brain data models used by V2Engine and the agent loop.

Extracted from reasoner.py (LLMDecision) and strategy_selector.py (DecisionSource)
to decouple shared types from V1-only modules before V1 deletion.
"""

from __future__ import annotations

from enum import Enum


class DecisionSource(Enum):
    LLM = "llm"
    RANDOM = "random"


class LLMDecision:
    """Parsed LLM response."""

    __slots__ = (
        "action_name",
        "params",
        "reasoning",
        "reasoning_zh",
        "raw_text",
        "prompt_text",
        "latency_ms",
        "tokens_used",
        "strategic_note",
    )

    def __init__(
        self,
        action_name: str,
        params: dict,
        reasoning: str,
        raw_text: str = "",
        prompt_text: str = "",
        latency_ms: float = 0.0,
        tokens_used: int = 0,
        strategic_note: str = "",
        reasoning_zh: str = "",
    ) -> None:
        self.action_name = action_name
        self.params = params
        self.reasoning = reasoning
        self.reasoning_zh = reasoning_zh
        self.raw_text = raw_text
        self.prompt_text = prompt_text
        self.latency_ms = latency_ms
        self.tokens_used = tokens_used
        if not strategic_note and isinstance(params, dict):
            raw = params.get("strategic_note", "")
            strategic_note = raw if isinstance(raw, str) else ""
        self.strategic_note = strategic_note

    # Params that must be int (LLMs sometimes return them as strings)
    _INT_PARAMS = frozenset({"card_index", "index", "option_index", "target_index"})

    def to_action(self) -> dict:
        """Convert to action dict for McpClient.post_action()."""
        base: dict = {"action": self.action_name}
        for k, v in self.params.items():
            if v is None:
                continue
            if k in self._INT_PARAMS and isinstance(v, str):
                try:
                    v = int(v)
                except ValueError:
                    pass
            base[k] = v
        return base

    def __repr__(self) -> str:
        return f"LLMDecision({self.action_name!r}, params={self.params})"
