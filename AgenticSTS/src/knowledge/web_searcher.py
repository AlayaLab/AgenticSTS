"""Web search via Claude API — proactive knowledge acquisition.

Uses Claude's built-in web_search tool to fetch game strategy guides,
card tier lists, boss strategies, etc. Results are cached to disk
to avoid redundant searches across runs.

Model: Opus 4.6 for deep analysis of search results.
"""

from __future__ import annotations

import hashlib
import json
import logging
import time
from pathlib import Path

import config

logger = logging.getLogger(__name__)

_CACHE_DIR = Path(config.DATA_DIR) / "knowledge" / "web_cache"
_GUIDES_DIR = Path(config.DATA_DIR) / "knowledge" / "guides"

# Cache TTL: 7 days (strategies don't change that fast)
_CACHE_TTL_SECONDS = 7 * 24 * 3600

# Web search tool definition (basic version — proxy-compatible)
_WEB_SEARCH_TOOL = {
    "type": "web_search_20250305",
    "name": "web_search",
    "max_uses": 5,
}


def _cache_key(query: str) -> str:
    """Deterministic cache key from query string."""
    return hashlib.sha256(query.encode()).hexdigest()[:16]


def _read_cache(query: str) -> str | None:
    """Read cached result if fresh enough."""
    key = _cache_key(query)
    path = _CACHE_DIR / f"{key}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if time.time() - data.get("timestamp", 0) < _CACHE_TTL_SECONDS:
            return data.get("result", "")
    except (json.JSONDecodeError, OSError):
        pass
    return None


def _write_cache(query: str, result: str) -> None:
    """Write result to disk cache."""
    _CACHE_DIR.mkdir(parents=True, exist_ok=True)
    key = _cache_key(query)
    path = _CACHE_DIR / f"{key}.json"
    data = {"query": query, "result": result, "timestamp": time.time()}
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


class WebSearcher:
    """Claude-powered web search for STS2 strategy knowledge.

    Uses Opus 4.6 with web_search tool for deep analysis.
    Results are cached to data/knowledge/web_cache/.
    """

    def __init__(self) -> None:
        self._client = None
        self._anthropic = None

    def _ensure_client(self) -> None:
        """Lazy-init Anthropic client."""
        if self._client is not None:
            return
        import anthropic
        self._anthropic = anthropic
        kwargs: dict = {}
        if config.LLM_API_KEY:
            kwargs["api_key"] = config.LLM_API_KEY
        if config.ANTHROPIC_BASE_URL:
            kwargs["base_url"] = config.ANTHROPIC_BASE_URL
        self._client = anthropic.Anthropic(**kwargs)

    def _call_with_search(
        self, system: str, user: str, *, max_searches: int = 5,
    ) -> str:
        """Call Claude with web search tool enabled.

        Returns the text content from Claude's response (after it has
        searched the web and synthesized results).
        """
        self._ensure_client()
        t0 = time.monotonic()

        search_tool = {**_WEB_SEARCH_TOOL, "max_uses": max_searches}
        model = config.WEB_SEARCH_MODEL

        try:
            response = self._client.messages.create(
                model=model,
                max_tokens=8192,
                temperature=1.0,  # required for thinking-capable models
                system=[{"type": "text", "text": system}],
                messages=[{"role": "user", "content": user}],
                tools=[search_tool],
            )
        except Exception as e:
            logger.warning("Web search API call failed: %s", e)
            return ""

        latency = (time.monotonic() - t0) * 1000

        # Extract text blocks from response
        text_parts: list[str] = []
        for block in response.content:
            if hasattr(block, "type") and block.type == "text":
                text_parts.append(block.text)

        result = "\n".join(text_parts).strip()

        # Log usage
        usage = response.usage
        search_count = 0
        if hasattr(usage, "server_tool_use") and usage.server_tool_use:
            search_count = getattr(usage.server_tool_use, "web_search_requests", 0)
        tokens = usage.input_tokens + usage.output_tokens

        logger.info(
            "Web search: model=%s %.0fms %dtok %d searches",
            model, latency, tokens, search_count,
        )
        return result

    # ── Public search methods ──────────────────────────────────

    def search_boss_strategy(self, boss_name: str, character: str) -> str:
        """Search for specific boss fight strategy.

        Returns strategy text. Cached for 7 days.
        """
        query = f"sts2_boss_{boss_name.lower()}_{character.lower()}"
        cached = _read_cache(query)
        if cached:
            logger.info("Boss strategy cache hit: %s vs %s", boss_name, character)
            return cached

        system = (
            "You are a Slay the Spire 2 expert. Search for boss fight strategies "
            "and provide actionable combat advice. Output ONLY valid JSON."
        )
        user = (
            f"Search for Slay the Spire 2 boss strategy: how to beat {boss_name} "
            f"as {character}. Then produce a JSON object:\n"
            f'{{\n'
            f'  "boss": "{boss_name}",\n'
            f'  "character": "{character}",\n'
            f'  "boss_mechanics": "what the boss does (attack patterns, phases)",\n'
            f'  "strategy": "how to beat it (3-5 sentences)",\n'
            f'  "priority_cards": ["cards that are especially good in this fight"],\n'
            f'  "cards_to_avoid_playing": ["cards that are bad in this fight"],\n'
            f'  "hp_threshold": "minimum HP recommended before this fight",\n'
            f'  "potion_advice": "when to use potions"\n'
            f'}}'
        )

        result = self._call_with_search(system, user, max_searches=3)
        if result:
            _write_cache(query, result)
        return result

    @staticmethod
    def format_boss_strategy(raw_json: str) -> str:
        """Parse boss strategy JSON into a prompt-friendly markdown section.

        Returns empty string if parsing fails. Truncates to ~400 tokens.
        """
        if not raw_json:
            return ""
        try:
            # Try JSON parse
            data = json.loads(raw_json.strip())
        except json.JSONDecodeError:
            # Try extracting JSON from text
            start = raw_json.find("{")
            end = raw_json.rfind("}")
            if start == -1 or end == -1:
                return ""
            try:
                data = json.loads(raw_json[start:end + 1])
            except json.JSONDecodeError:
                return ""

        lines = ["## Boss Strategy (web research)"]
        if data.get("boss_mechanics"):
            lines.append(f"**Mechanics**: {data['boss_mechanics']}")
        if data.get("strategy"):
            lines.append(f"**Strategy**: {data['strategy']}")
        if data.get("priority_cards"):
            cards = ", ".join(data["priority_cards"][:8])
            lines.append(f"**Priority cards**: {cards}")
        if data.get("cards_to_avoid_playing"):
            avoid = ", ".join(data["cards_to_avoid_playing"][:5])
            lines.append(f"**Avoid playing**: {avoid}")
        if data.get("potion_advice"):
            lines.append(f"**Potions**: {data['potion_advice']}")

        result = "\n".join(lines)
        # Truncate to ~400 tokens (~1600 chars)
        if len(result) > 1600:
            result = result[:1600] + "..."
        return result

