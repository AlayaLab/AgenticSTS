"""Async HTTP client for STS2-Agent REST API (CharTyr v0.5.2).

Endpoints:
  GET  /health         — health check
  GET  /state          — full game state
  POST /action         — execute game action
  GET  /events/stream  — SSE event notifications
"""

from __future__ import annotations

import asyncio
import logging
import time

import httpx

import config
from src.mcp_client import cjk_audit

logger = logging.getLogger(__name__)


class McpClient:
    """Async client wrapping the STS2-Agent REST API.

    All game state reads and action executions go through this client.
    Uses httpx.AsyncClient with connection pooling.
    """

    def __init__(
        self,
        base_url: str = config.MCP_BASE_URL,
        timeout: float = config.MCP_TIMEOUT,
        event_bus: object | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._client: httpx.AsyncClient | None = None
        self._sse_stream = None  # SseStateStream, lazily initialized
        self._event_bus = event_bus
        self._current_run_id: str | None = None

    async def connect(self) -> None:
        """Create the HTTP client, verify reachability, and optionally start SSE."""
        self._client = httpx.AsyncClient(timeout=self._timeout)
        if not await self.health_check():
            logger.warning("STS2-Agent not reachable at %s", self._base_url)
            return

        # Try to establish SSE connection for event-triggered state refreshes
        if config.SSE_ENABLED:
            try:
                from src.mcp_client.sse_client import SseStateStream
                self._sse_stream = SseStateStream(base_url=self._base_url)
                await self._sse_stream.connect()
                if self._sse_stream.is_connected:
                    logger.info("SSE stream connected — using event-triggered state refreshes")
                else:
                    self._sse_stream = None
                    logger.info("SSE unavailable — falling back to polling")
            except Exception as e:
                self._sse_stream = None
                logger.info("SSE init failed (%s) — falling back to polling", e)

    async def close(self) -> None:
        if self._sse_stream:
            await self._sse_stream.close()
            self._sse_stream = None
        if self._client:
            await self._client.aclose()
            self._client = None

    async def __aenter__(self) -> McpClient:
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    def set_run_id(self, run_id: str | None) -> None:
        """Set current run_id for monitor event tagging."""
        self._current_run_id = run_id

    # ── Core API ──────────────────────────────────────────────

    async def health_check(self) -> bool:
        """Check if the game mod's HTTP server is responding."""
        try:
            resp = await self._get_client().get(f"{self._base_url}/health")
            if resp.status_code == 200:
                data = resp.json()
                if data.get("ok"):
                    logger.info(
                        "STS2-Agent connected: mod=%s protocol=%s",
                        data.get("data", {}).get("mod_version", "?"),
                        data.get("data", {}).get("protocol_version", "?"),
                    )
                    return True
            return False
        except httpx.ConnectError:
            return False

    async def get_state(self, fmt: str = "json") -> dict:
        """GET game state. Returns the state payload dict.

        Unwraps the {ok, request_id, data} envelope from the new API.
        Raises McpError on HTTP errors or connection failures.
        """
        try:
            resp = await self._get_client().get(f"{self._base_url}/state")
            resp.raise_for_status()
            envelope = resp.json()
            if not envelope.get("ok"):
                error = envelope.get("error", {})
                raise McpError(
                    f"State error: {error.get('message', 'unknown')} "
                    f"(code={error.get('code')})"
                )
            data = envelope.get("data", {})
            cjk_audit.audit("get_state", data)
            return data
        except httpx.ConnectError as e:
            raise McpError("Game not reachable. Is STS2 running with the mod?") from e
        except httpx.HTTPStatusError as e:
            raise McpError(f"HTTP {e.response.status_code}: {e.response.text}") from e

    async def post_action(self, action_body: dict) -> dict:
        """POST an action to the game. Returns response dict.

        action_body should come from src.mcp_client.actions builders.
        Unwraps the {ok, data} envelope; data contains {action, status, stable, state}.
        """
        try:
            resp = await self._get_client().post(
                f"{self._base_url}/action",
                json=action_body,
            )
            if not resp.content:
                raise McpError(
                    f"Empty response from game for action "
                    f"'{action_body.get('action', '?')}' "
                    f"(HTTP {resp.status_code})"
                )
            try:
                envelope = resp.json()
            except Exception as exc:
                raise McpError(
                    f"Invalid JSON from game for action "
                    f"'{action_body.get('action', '?')}': "
                    f"{resp.text[:200]}"
                ) from exc

            if not envelope.get("ok"):
                error = envelope.get("error", {})
                msg = error.get("message", "Unknown action error")
                code = error.get("code", "unknown")
                retryable = error.get("retryable", False)
                raise McpActionError(
                    f"{code}: {msg}",
                    code=code,
                    retryable=retryable,
                )

            data = envelope.get("data", {})
            cjk_audit.audit(
                f"post_action:{action_body.get('action', '?')}", data
            )

            # Log stability info
            if not data.get("stable", True):
                logger.debug(
                    "Action '%s' pending (not yet stable): %s",
                    action_body.get("action"), data.get("message", ""),
                )

            # Emit game_action to monitor (single source of truth)
            if self._event_bus is not None:
                try:
                    self._event_bus.emit("game_action", {
                        "action": action_body.get("action", "unknown"),
                        "params": {
                            k: v for k, v in action_body.items() if k != "action"
                        },
                        "result_status": data.get("status", ""),
                        "stable": data.get("stable", True),
                    }, run_id=self._current_run_id)
                except Exception:
                    pass  # Monitor never crashes agent

            return data
        except httpx.ConnectError as e:
            raise McpError("Game not reachable") from e
        except httpx.TimeoutException as e:
            raise McpActionError(
                f"read_timeout: timed out waiting for action "
                f"'{action_body.get('action', '?')}' response",
                code="read_timeout",
                retryable=True,
            ) from e
        except httpx.HTTPStatusError as e:
            # Try to parse error from response body
            try:
                envelope = e.response.json()
                error = envelope.get("error", {})
                raise McpActionError(
                    f"{error.get('code', 'http_error')}: {error.get('message', e.response.text)}",
                    code=error.get("code", "http_error"),
                    retryable=error.get("retryable", False),
                ) from e
            except (ValueError, KeyError):
                raise McpError(f"HTTP {e.response.status_code}: {e.response.text}") from e

    async def wait_for_state_change(
        self,
        prev_state_type: str,
        timeout: float = config.STATE_CHANGE_TIMEOUT,
        poll_interval: float = config.MCP_POLL_INTERVAL,
    ) -> dict:
        """Wait until state_type changes from prev_state_type.

        Uses SSE event notifications when available (~120ms), falls back to polling.
        Returns the new state dict. Raises McpTimeout if timeout exceeded.
        """
        remaining = timeout

        # Try SSE first
        if self._sse_stream and self._sse_stream.is_connected:
            from src.mcp_client.sse_client import wait_for_state_change_sse
            sse_started = time.monotonic()
            try:
                result = await wait_for_state_change_sse(
                    self._sse_stream,
                    self.get_state,
                    prev_state_type,
                    timeout,
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.info("SSE state-change wait failed (%s) — falling back to polling", e)
            remaining = max(0.0, timeout - (time.monotonic() - sse_started))
            if remaining <= 0:
                raise McpTimeout(
                    f"State did not change from '{prev_state_type}' within {timeout:.1f}s"
                )

        # Fallback: polling
        from src.state.state_parser import safe_parse_state
        t0 = time.monotonic()
        while time.monotonic() - t0 < remaining:
            raw_state = await self.get_state()
            gs = safe_parse_state(raw_state)
            if gs is not None and gs.state_type != prev_state_type:
                return raw_state
            await asyncio.sleep(poll_interval)

        raise McpTimeout(
            f"State did not change from '{prev_state_type}' "
            f"within {timeout:.1f}s"
        )

    async def wait_for_play_phase(
        self,
        timeout: float = config.STATE_CHANGE_TIMEOUT,
        poll_interval: float = config.MCP_POLL_INTERVAL,
    ) -> dict:
        """Wait until it's the player's turn (is_play_phase=True).

        Uses SSE event notifications when available (~120ms), falls back to polling.
        """
        remaining = timeout

        # Try SSE first
        if self._sse_stream and self._sse_stream.is_connected:
            from src.mcp_client.sse_client import wait_for_play_phase_sse
            sse_started = time.monotonic()
            try:
                result = await wait_for_play_phase_sse(
                    self._sse_stream,
                    self.get_state,
                    timeout,
                )
                if result is not None:
                    return result
            except Exception as e:
                logger.info("SSE play-phase wait failed (%s) — falling back to polling", e)
            remaining = max(0.0, timeout - (time.monotonic() - sse_started))
            if remaining <= 0:
                raise McpTimeout(f"Play phase not reached within {timeout:.1f}s")

        # Fallback: polling
        from src.state.state_parser import safe_parse_state
        t0 = time.monotonic()
        while time.monotonic() - t0 < remaining:
            raw_state = await self.get_state()
            gs = safe_parse_state(raw_state)
            if gs is not None:
                if gs.is_play_phase:
                    return raw_state
                if not gs.is_combat:
                    return raw_state  # combat ended
            await asyncio.sleep(poll_interval)

        raise McpTimeout(f"Play phase not reached within {timeout:.1f}s")

    # ── Multi-run ─────────────────────────────────────────────

    IN_RUN_STATES = frozenset({
        "map", "monster", "elite", "boss", "event",
        "rest_site", "shop", "combat_rewards", "card_reward",
        "card_select", "relic_select", "treasure", "hand_select",
        "cards_view", "bundle_select", "crystal_sphere",
        "combat_hand_select",
    })

    async def start_new_run(
        self,
        character: str | None = None,
        ascension: int | None = None,
        max_attempts: int = 30,
        step_delay: float = 1.5,
        abandon_existing: bool = False,
    ) -> bool:
        """State-driven flow using available_actions for menu navigation.

        If abandon_existing=True and a saved run exists (continue_run available),
        the existing run is abandoned instead of re-entered.  Use this after an
        abnormal abort to avoid re-entering a stuck game state.

        Returns True if a new run was successfully started.
        """
        from src.mcp_client import actions as act
        from src.state.state_parser import safe_parse_state

        for attempt in range(1, max_attempts + 1):
            try:
                raw_state = await self.get_state()
                gs = safe_parse_state(raw_state)
                st = gs.state_type if gs else "unknown"
                avail = gs.available_actions if gs else raw_state.get("available_actions", [])

                # Already in a run — only re-enter if we are NOT abandoning
                if st in self.IN_RUN_STATES:
                    if abandon_existing:
                        # Need to get out of the in-run state first via save_and_quit
                        logger.info(
                            "abandon_existing=True but in-run state=%s; calling save_and_quit",
                            st,
                        )
                        try:
                            await self.post_action(act.save_and_quit())
                        except Exception:
                            pass
                        await asyncio.sleep(1.5)
                        continue
                    logger.info("Already in run (state=%s)", st)
                    return True

                logger.info(
                    "start_new_run [%d/%d]: state=%s actions=%s",
                    attempt, max_attempts, st, avail,
                )

                # Dispatch based on available_actions (primary) or state_type (fallback)

                # If ascension is specified, don't silently continue a saved run
                # (its ascension may not match the target)
                if "continue_run" in avail and ascension is not None and not abandon_existing:
                    logger.info(
                        "Saved run exists but --ascension=%d specified; abandoning saved run",
                        ascension,
                    )
                    abandon_existing = True

                if "continue_run" in avail:
                    if abandon_existing and "abandon_run" in avail:
                        logger.info(
                            "abandon_existing=True: abandoning saved run instead of continuing"
                        )
                        await self.post_action(act.abandon_run())
                        await asyncio.sleep(1.5)
                        abandon_existing = False  # run abandoned, proceed normally
                        continue
                    elif abandon_existing:
                        # abandon_run not yet available — go to main menu first
                        logger.info(
                            "abandon_existing=True: navigating to main menu to access abandon_run"
                        )
                        try:
                            await self.post_action(act.return_to_main_menu())
                        except Exception:
                            pass
                        await asyncio.sleep(1.5)
                        continue
                    logger.info("Existing run detected, continuing...")
                    await self.post_action(act.continue_run())
                    await asyncio.sleep(1.5)
                    return True

                elif "return_to_main_menu" in avail:
                    await self.post_action(act.return_to_main_menu())

                elif "confirm_modal" in avail:
                    await self.post_action(act.confirm_modal())

                elif "confirm_timeline_overlay" in avail:
                    await self.post_action(act.confirm_timeline_overlay())

                elif "choose_timeline_epoch" in avail:
                    if "close_main_menu_submenu" in avail:
                        await self.post_action(act.close_main_menu_submenu())
                    else:
                        await self.post_action(act.choose_timeline_epoch())

                elif "select_character" in avail and character:
                    # Check if the desired character is already selected
                    char_select = raw_state.get("character_select", {})
                    selected_id = (char_select.get("selected_character_id") or "").lower()
                    already_selected = selected_id == character.lower()
                    # Also check is_selected flag on characters list
                    if not already_selected:
                        chars = char_select.get("characters", [])
                        for ch in chars:
                            cid = (ch.get("character_id") or "").lower()
                            cname = (ch.get("name") or "").lower()
                            if (
                                (cid == character.lower() or cname == character.lower())
                                and ch.get("is_selected")
                            ):
                                already_selected = True
                                break

                    if already_selected and "embark" in avail:
                        # -- Ascension adjustment (before embark) --
                        if ascension is not None:
                            char_select = raw_state.get("character_select", {})
                            current_asc = char_select.get("ascension", 0)
                            max_asc = char_select.get("max_ascension", 20)
                            target_asc = min(ascension, max_asc)
                            if current_asc != target_asc:
                                if target_asc > current_asc and char_select.get("can_increase_ascension", False):
                                    logger.info("Adjusting ascension %d -> %d (incrementing)", current_asc, target_asc)
                                    await self.post_action(act.increase_ascension())
                                    await asyncio.sleep(0.3)
                                    continue
                                elif target_asc < current_asc and char_select.get("can_decrease_ascension", False):
                                    logger.info("Adjusting ascension %d -> %d (decrementing)", current_asc, target_asc)
                                    await self.post_action(act.decrease_ascension())
                                    await asyncio.sleep(0.3)
                                    continue
                                else:
                                    logger.warning(
                                        "Cannot adjust ascension from %d to %d (can_inc=%s, can_dec=%s)",
                                        current_asc, target_asc,
                                        char_select.get("can_increase_ascension"),
                                        char_select.get("can_decrease_ascension"),
                                    )
                        # Desired character already selected → embark
                        logger.info("Character '%s' already selected, embarking", character)
                        await self.post_action(act.embark())
                        await asyncio.sleep(3.0)
                        return True

                    # Select the requested character
                    chars = char_select.get("characters", [])
                    logger.info(
                        "Character select: looking for '%s' in %s",
                        character,
                        [(ch.get("character_id"), ch.get("name"), ch.get("index")) for ch in chars],
                    )
                    matched = False
                    for ch in chars:
                        if (ch.get("character_id") or "").lower() == character.lower():
                            await self.post_action(
                                act.select_character(option_index=ch.get("index", 0))
                            )
                            matched = True
                            break
                        if (ch.get("name") or "").lower() == character.lower():
                            await self.post_action(
                                act.select_character(option_index=ch.get("index", 0))
                            )
                            matched = True
                            break
                    if not matched:
                        logger.warning("Character '%s' not found, using first", character)
                        await self.post_action(act.select_character(option_index=0))

                elif "embark" in avail:
                    # -- Ascension adjustment (before embark) --
                    if ascension is not None:
                        char_select = raw_state.get("character_select", {})
                        current_asc = char_select.get("ascension", 0)
                        max_asc = char_select.get("max_ascension", 20)
                        target_asc = min(ascension, max_asc)
                        if current_asc != target_asc:
                            if target_asc > current_asc and char_select.get("can_increase_ascension", False):
                                logger.info("Adjusting ascension %d -> %d (incrementing)", current_asc, target_asc)
                                await self.post_action(act.increase_ascension())
                                await asyncio.sleep(0.3)
                                continue
                            elif target_asc < current_asc and char_select.get("can_decrease_ascension", False):
                                logger.info("Adjusting ascension %d -> %d (decrementing)", current_asc, target_asc)
                                await self.post_action(act.decrease_ascension())
                                await asyncio.sleep(0.3)
                                continue
                            else:
                                logger.warning(
                                    "Cannot adjust ascension from %d to %d (can_inc=%s, can_dec=%s)",
                                    current_asc, target_asc,
                                    char_select.get("can_increase_ascension"),
                                    char_select.get("can_decrease_ascension"),
                                )
                    # Character selected (or no preference) → start the run
                    await self.post_action(act.embark())
                    await asyncio.sleep(3.0)
                    return True

                elif "select_character" in avail:
                    # No character preference → select first
                    await self.post_action(act.select_character(option_index=0))

                elif "open_character_select" in avail:
                    await self.post_action(act.open_character_select())

                elif "close_main_menu_submenu" in avail:
                    await self.post_action(act.close_main_menu_submenu())

                elif "proceed" in avail:
                    # Intermediate screen (e.g. discard_potion dialog) — advance
                    logger.info("Advancing through intermediate state=%s via proceed", st)
                    await self.post_action(act.proceed())

                elif avail:
                    logger.warning(
                        "Unrecognized menu actions: %s (state=%s)", avail, st,
                    )
                    # Try common fallbacks
                    if st in ("game_over", "victory"):
                        await self.post_action(act.return_to_main_menu())
                    else:
                        await self.post_action(act.open_character_select())

                else:
                    # No available_actions — fall back to state_type dispatch
                    if st in ("game_over", "victory"):
                        await self.post_action(act.return_to_main_menu())
                    elif st == "overlay":
                        try:
                            await self.post_action(act.confirm_modal())
                        except McpActionError:
                            try:
                                await self.post_action(act.return_to_main_menu())
                            except McpActionError:
                                pass
                    elif st in ("timeline", "timeline_unlock", "epoch_inspect"):
                        await self.post_action(act.close_main_menu_submenu())
                    elif st == "character_select":
                        # -- Ascension adjustment (before embark) --
                        if ascension is not None:
                            char_select = raw_state.get("character_select", {})
                            current_asc = char_select.get("ascension", 0)
                            max_asc = char_select.get("max_ascension", 20)
                            target_asc = min(ascension, max_asc)
                            if current_asc != target_asc:
                                if target_asc > current_asc and char_select.get("can_increase_ascension", False):
                                    logger.info("Adjusting ascension %d -> %d (incrementing)", current_asc, target_asc)
                                    await self.post_action(act.increase_ascension())
                                    await asyncio.sleep(0.3)
                                    continue
                                elif target_asc < current_asc and char_select.get("can_decrease_ascension", False):
                                    logger.info("Adjusting ascension %d -> %d (decrementing)", current_asc, target_asc)
                                    await self.post_action(act.decrease_ascension())
                                    await asyncio.sleep(0.3)
                                    continue
                                else:
                                    logger.warning(
                                        "Cannot adjust ascension from %d to %d (can_inc=%s, can_dec=%s)",
                                        current_asc, target_asc,
                                        char_select.get("can_increase_ascension"),
                                        char_select.get("can_decrease_ascension"),
                                    )
                        await self.post_action(act.embark())
                        await asyncio.sleep(3.0)
                        return True
                    elif st == "menu":
                        await self.post_action(act.open_character_select())
                    elif st == "unknown":
                        # Persistent unknown state — after a few waits, force exit via
                        # return_to_main_menu (game may be on an unrecognized screen from
                        # an aborted run). Ignore errors if the action isn't valid here.
                        if attempt >= 5:
                            logger.info(
                                "state=unknown persists (attempt %d), trying return_to_main_menu",
                                attempt,
                            )
                            try:
                                await self.post_action(act.return_to_main_menu())
                            except (McpActionError, McpError):
                                try:
                                    await self.post_action(act.save_and_quit())
                                except (McpActionError, McpError):
                                    pass
                        else:
                            logger.info(
                                "state=unknown with no actions, waiting (attempt %d/4)...",
                                attempt,
                            )
                    else:
                        logger.warning("Unknown state '%s', trying open_character_select", st)
                        await self.post_action(act.open_character_select())

            except McpActionError as e:
                logger.debug("start_new_run step %d action error: %s", attempt, e)
            except McpError as e:
                logger.warning("start_new_run step %d MCP error: %s", attempt, e)

            await asyncio.sleep(step_delay)

        logger.error("start_new_run failed after %d attempts", max_attempts)
        return False

    async def get_available_actions(self) -> dict:
        """Get available actions with parameter hints (v0.5.3+).
        Returns empty dict if endpoint not available (v0.5.2 compat).
        """
        try:
            resp = await self._get_client().get(f"{self._base_url}/actions/available")
            resp.raise_for_status()
            envelope = resp.json()
            return envelope.get("data", {}) if envelope.get("ok") else {}
        except Exception:
            return {}

    # ── Helpers ───────────────────────────────────────────────

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise McpError("Client not connected. Call connect() first.")
        return self._client


# ── Exceptions ────────────────────────────────────────────────


class McpError(Exception):
    """Base error for MCP client operations."""


class McpActionError(McpError):
    """The game returned an error for an action."""

    def __init__(self, message: str, code: str = "unknown", retryable: bool = False):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class McpTimeout(McpError):
    """Polling timed out waiting for state change."""
