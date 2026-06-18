"""Parse raw MCP JSON into typed GameState.

Parses the upstream STS2-Agent ``/state`` payload directly into
``UpstreamGameState`` and wraps it in ``GameState`` for convenience.
"""

from __future__ import annotations

import logging

from pydantic import ValidationError

from src.mcp_client.upstream_models import UpstreamGameState
from src.state.game_state import GameState
from src.state.upstream_game_state import UpstreamStateView

logger = logging.getLogger(__name__)


def unwrap_state_payload(raw_json: dict) -> dict:
    """Return the ``/state.data`` object from either raw payload or envelope."""
    if not isinstance(raw_json, dict):
        raise StateParseError(
            f"Game state payload must be a dict, got {type(raw_json).__name__}"
        )
    if "screen" in raw_json:
        return raw_json
    data = raw_json.get("data")
    if isinstance(data, dict):
        return data
    return raw_json


def parse_state(raw_json: dict) -> GameState:
    """Convert raw JSON from McpClient.get_state() into a GameState."""
    try:
        payload = unwrap_state_payload(raw_json)
        upstream = UpstreamGameState.model_validate(payload)
        return GameState.from_upstream(upstream)
    except ValidationError as e:
        logger.error("Failed to parse game state: %s", e)
        raise StateParseError(f"Invalid game state JSON: {e}") from e


def safe_parse_state(raw_json: dict) -> GameState | None:
    """Like parse_state but returns None on failure."""
    try:
        return parse_state(raw_json)
    except StateParseError:
        return None


def parse_upstream_state_payload(raw_json: dict) -> UpstreamGameState:
    """Validate the upstream ``/state.data`` payload into the raw model."""
    try:
        payload = unwrap_state_payload(raw_json)
        return UpstreamGameState.model_validate(payload)
    except ValidationError as e:
        logger.error("Failed to parse upstream game state: %s", e)
        raise StateParseError(f"Invalid upstream game state JSON: {e}") from e


def parse_upstream_game_state(raw_json: dict) -> UpstreamStateView:
    """Parse upstream payload into the Phase 2 convenience view."""
    return UpstreamStateView.from_payload(parse_upstream_state_payload(raw_json))


class StateParseError(Exception):
    """Game state JSON could not be parsed."""
