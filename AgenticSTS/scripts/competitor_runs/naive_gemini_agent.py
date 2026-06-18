"""Naive accumulating-context Gemini agent for Slay the Spire 2 (Workstream C baseline).

The BASELINE competitor agent: it drives our existing CharTyr-lineage game mod's
REST API (``localhost:8128``) with a bare Gemini function-calling loop. NO memory,
NO skill library, NO L1-L5 prompt stack -- just a neutral system prompt plus ONE
accumulating ``messages`` transcript that grows for the whole run (every assistant
tool-call and every tool result appended, never reset). It is the cleanest ablation
of what our full agent stack adds, and doubles as the accumulating-context datapoint
contrasting our bounded per-decision composition. It is deliberately *not* a published
agent -- it is our minimal driver over the CharTyr interface (PLAN.md "Fairness caveats").

API contract mirrored from ``src/mcp_client/`` (the authoritative reference):
  * GET  /health            -> {"ok": true, "data": {...}}                       (client.py:87-100)
  * GET  /state             -> {"ok": true, "request_id": ..., "data": {...}}    (client.py:104-122)
  * GET  /actions/available -> {"ok": true, "data": {...}}                       (client.py:624-634)
  * POST /action {"action": "<verb>", ...} -> {"ok": true, "data": {"action","status","stable","state"}}
        / {"ok": false, "error": {"code","message","retryable"}}                 (client.py:128-191)
  Targeting is by integer index: ``card_index`` (combat.hand), ``target_index``
  (combat.enemies), ``option_index`` (menu/reward/shop/event/rest/map/card selections)
  -- src/mcp_client/actions.py. Run-setup verbs: open_character_select /
  select_character{option_index} / increase_ascension / decrease_ascension / embark
  (actions.py:183-205). See README.md for usage; --dry-run smoke-tests connectivity.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import random
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from scripts.competitor_runs import _bootstrap as _bootstrap  # noqa: F401  (loads .env)

logger = logging.getLogger("naive_gemini_agent")

CAPTURES_ROOT = Path(__file__).resolve().parent / "captures"

# Screen strings (UPPERCASE) that mean we are still sitting at the menu and need
# run setup before the agent can drive an in-game run. Mirrors the upstream
# ``screen`` field (src/state/upstream_game_state.py derive_state_type).
MENU_SCREENS = frozenset({"MAIN_MENU", "CHARACTER_SELECT", "TIMELINE", "UNKNOWN", ""})


# ---------------------------------------------------------------------------
# Minimal REST client for our mod (fresh; mirrors src/mcp_client contract).
# ---------------------------------------------------------------------------


class ModApiError(RuntimeError):
    """The mod returned ``{ok: false, error}`` or an unexpected HTTP status."""

    def __init__(self, message: str, *, code: str = "unknown", retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.retryable = retryable


class ModClient:
    """Tiny synchronous client for the STS2-Agent REST mod.

    Only the four endpoints the naive agent needs, with the ``{ok, data}``
    envelope unwrapped and clear errors raised on failure.
    """

    def __init__(self, base_url: str, timeout: float = 30.0) -> None:
        self._base = base_url.rstrip("/")
        self._http = httpx.Client(timeout=timeout)

    def close(self) -> None:
        self._http.close()

    def _unwrap(self, resp: httpx.Response, what: str) -> dict[str, Any]:
        """Validate the {ok, data} / {ok, error} envelope and return data."""
        if not resp.content:
            raise ModApiError(f"Empty response from mod for {what} (HTTP {resp.status_code})")
        try:
            envelope = resp.json()
        except json.JSONDecodeError as exc:
            raise ModApiError(
                f"Non-JSON response from mod for {what}: {resp.text[:200]}"
            ) from exc
        if not isinstance(envelope, dict):
            raise ModApiError(f"Unexpected response shape from mod for {what}: {envelope!r}")
        if not envelope.get("ok"):
            error = envelope.get("error", {}) or {}
            raise ModApiError(
                f"{error.get('code', 'unknown')}: {error.get('message', 'unknown error')}",
                code=error.get("code", "unknown"),
                retryable=bool(error.get("retryable", False)),
            )
        return envelope.get("data", {}) or {}

    def health(self) -> dict[str, Any]:
        """GET /health -> data block (raises on unreachable / not-ok)."""
        try:
            resp = self._http.get(f"{self._base}/health")
        except httpx.ConnectError as exc:
            raise ModApiError(
                f"Cannot reach mod at {self._base}. Is StS2 running with our mod "
                f"on this port? (set --mod-url)"
            ) from exc
        return self._unwrap(resp, "/health")

    def get_state(self) -> dict[str, Any]:
        """GET /state -> the full game-state payload (the ``data`` block)."""
        try:
            resp = self._http.get(f"{self._base}/state")
        except httpx.ConnectError as exc:
            raise ModApiError("Mod not reachable on /state. Is StS2 running?") from exc
        resp.raise_for_status()
        return self._unwrap(resp, "/state")

    def get_available_actions(self) -> dict[str, Any]:
        """GET /actions/available -> hint block. Empty dict if unavailable."""
        try:
            resp = self._http.get(f"{self._base}/actions/available")
            resp.raise_for_status()
            return self._unwrap(resp, "/actions/available")
        except (httpx.HTTPError, ModApiError):
            return {}

    def post_action(self, action_body: dict[str, Any]) -> dict[str, Any]:
        """POST /action -> {action, status, stable, state}. Raises ModApiError on game error."""
        verb = action_body.get("action", "?")
        try:
            resp = self._http.post(f"{self._base}/action", json=action_body)
        except httpx.ConnectError as exc:
            raise ModApiError(f"Mod not reachable for action '{verb}'") from exc
        except httpx.TimeoutException as exc:
            raise ModApiError(
                f"read_timeout: action '{verb}' timed out", code="read_timeout", retryable=True
            ) from exc
        return self._unwrap(resp, f"action '{verb}'")


# ---------------------------------------------------------------------------
# Run setup: drive the menu to an active A0 run (best-effort; mirrors
# client.start_new_run's available_actions-driven flow, minus our stack).
# ---------------------------------------------------------------------------


def ensure_run_active(
    client: ModClient,
    character: str,
    ascension: int,
    *,
    max_attempts: int = 30,
    step_delay: float = 1.5,
) -> bool:
    """Best-effort: from the menu, select character + ascension and embark.

    Returns True once the game reports a non-menu screen (an active run). If the
    API cannot fully script setup, the user is expected to start the run manually
    (Silent + A0 + embark) and this returns True as soon as a run is detected.
    """
    for attempt in range(1, max_attempts + 1):
        try:
            state = client.get_state()
        except ModApiError as exc:
            logger.warning("run-setup: cannot read state (%s); retrying", exc)
            _sleep(step_delay)
            continue

        screen = str(state.get("screen", "")).upper()
        avail = state.get("available_actions", []) or []

        # Already in a run (any non-menu screen, or a populated run block).
        if screen not in MENU_SCREENS or state.get("run"):
            logger.info("run-setup: active run detected (screen=%s)", screen)
            return True

        logger.info("run-setup [%d/%d]: screen=%s actions=%s", attempt, max_attempts, screen, avail)

        try:
            if "continue_run" in avail:
                # A saved run exists; embarking fresh would clobber it. Prefer to
                # take it over (the user is responsible for starting an A0 run).
                client.post_action({"action": "continue_run"})
                _sleep(step_delay)
                return True
            if "embark" in avail and _character_ready(state, character) and _ascension_ok(
                client, state, ascension
            ):
                client.post_action({"action": "embark"})
                _sleep(3.0)
                return True
            if "select_character" in avail:
                idx = _character_index(state, character)
                if idx is not None:
                    client.post_action({"action": "select_character", "option_index": idx})
                else:
                    logger.warning("run-setup: character '%s' not in list; selecting first", character)
                    client.post_action({"action": "select_character", "option_index": 0})
            elif "open_character_select" in avail:
                client.post_action({"action": "open_character_select"})
            elif "confirm_modal" in avail:
                client.post_action({"action": "confirm_modal"})
            elif "close_main_menu_submenu" in avail:
                client.post_action({"action": "close_main_menu_submenu"})
            elif avail:
                logger.warning("run-setup: unhandled menu actions %s; waiting", avail)
            else:
                logger.info("run-setup: no actions on screen=%s; waiting for manual setup", screen)
        except ModApiError as exc:
            logger.warning("run-setup attempt %d failed: %s", attempt, exc)

        _sleep(step_delay)

    logger.error(
        "run-setup: could not reach an active run after %d attempts. Start the run "
        "manually in-game (%s, A%d, embark) and re-run.",
        max_attempts,
        character,
        ascension,
    )
    return False


def _character_index(state: dict[str, Any], character: str) -> int | None:
    """Find the option_index of ``character`` in the character_select block."""
    cs = state.get("character_select", {}) or {}
    for ch in cs.get("characters", []) or []:
        cid = str(ch.get("character_id", "")).lower()
        name = str(ch.get("name", "")).lower()
        if character.lower() in (cid, name):
            return int(ch.get("index", 0))
    return None


def _character_ready(state: dict[str, Any], character: str) -> bool:
    """True if the desired character is the currently selected one."""
    cs = state.get("character_select", {}) or {}
    selected = str(cs.get("selected_character_id", "") or "").lower()
    if selected and selected == character.lower():
        return True
    for ch in cs.get("characters", []) or []:
        cid = str(ch.get("character_id", "")).lower()
        name = str(ch.get("name", "")).lower()
        if character.lower() in (cid, name) and ch.get("is_selected"):
            return True
    return False


def _ascension_ok(client: ModClient, state: dict[str, Any], ascension: int) -> bool:
    """Nudge ascension toward the target; return True only when it already matches.

    A0 is the floor, so on a fresh profile no change is needed. Returns False
    (after issuing one inc/dec) so the caller re-reads state and re-checks.
    """
    cs = state.get("character_select", {}) or {}
    current = int(cs.get("ascension", 0))
    target = min(ascension, int(cs.get("max_ascension", 20)))
    if current == target:
        return True
    try:
        if target > current and cs.get("can_increase_ascension"):
            client.post_action({"action": "increase_ascension"})
        elif target < current and cs.get("can_decrease_ascension"):
            client.post_action({"action": "decrease_ascension"})
        else:
            logger.warning(
                "run-setup: cannot adjust ascension %d -> %d (treating current as acceptable)",
                current,
                target,
            )
            return True
    except ModApiError as exc:
        logger.warning("run-setup: ascension adjust failed (%s)", exc)
        return True
    _sleep(0.3)
    return False


# ---------------------------------------------------------------------------
# Gemini via OpenAI-compatible chat-completions + tools (through the proxy).
# ---------------------------------------------------------------------------


# The three tools exposed to Gemini. Schemas are faithful to the mod API:
# take_action mirrors POST /action (verb + integer-index params).
TOOLS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "get_state",
            "description": "Read the full current game state (screen, run, combat, map, "
            "rewards, etc.) as JSON.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_available_actions",
            "description": "List the action verbs that are legal right now, with parameter "
            "hints (which need an index/target).",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "take_action",
            "description": (
                "Execute one game action. 'verb' is the action name (e.g. play_card, "
                "end_turn, choose_map_node, choose_event_option, choose_rest_option, "
                "buy_card, buy_relic, buy_potion, claim_reward, choose_reward_card, "
                "skip_reward_cards, resolve_rewards, select_deck_card, confirm_selection, "
                "open_chest, choose_treasure_relic, use_potion, proceed). 'params' carries "
                "integer indices the verb needs: card_index (into combat.hand), target_index "
                "(into combat.enemies), option_index (for map/reward/shop/event/rest/card "
                "selections). Omit params for verbs that take none (e.g. end_turn, proceed)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "verb": {"type": "string", "description": "The action verb."},
                    "params": {
                        "type": "object",
                        "description": "Integer-index parameters for the verb, e.g. "
                        '{"card_index": 0, "target_index": 1} or {"option_index": 2}.',
                        "properties": {
                            "card_index": {"type": "integer"},
                            "target_index": {"type": "integer"},
                            "option_index": {"type": "integer"},
                        },
                    },
                },
                "required": ["verb"],
            },
        },
    },
]

SYSTEM_PROMPT = (
    "You are playing Slay the Spire 2. Win the run. Use the provided tools to read "
    "the game state and take legal actions. Call get_state and get_available_actions "
    "to see what is happening and what is legal, then call take_action to act. "
    "Targeting and selections use integer indices from the state. Keep going until "
    "the run ends (victory or death)."
)


class GeminiClient:
    """Thin OpenAI-compatible chat-completions client pointed at the proxy."""

    def __init__(self, base_url: str, api_key: str, model: str, run_id: str, timeout: float = 600.0) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._http = httpx.Client(
            timeout=httpx.Timeout(timeout, connect=15.0),
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "X-Run-Id": run_id,  # proxy tags captures by this header
            },
        )

    def close(self) -> None:
        self._http.close()

    # HTTP statuses worth retrying — relay rate/burst throttling (a relay returns 403
    # under load), plus the usual transient server/timeout codes. A 400 (e.g. a bad
    # tool schema) is NOT retryable and fails fast.
    _RETRYABLE = frozenset({403, 408, 409, 425, 429, 500, 502, 503, 504})

    def complete(
        self,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict] | None = None,
        max_retries: int = 6,
    ) -> dict[str, Any]:
        """One non-streaming chat-completion (with backoff on transient relay errors).

        Returns the assistant message dict. Retries transient failures (403/429/5xx/
        timeout/connect) with exponential backoff so a flaky relay does not kill a whole
        run; a non-retryable error (e.g. 400) or exhausted retries raises RuntimeError.
        """
        body: dict[str, Any] = {"model": self._model, "messages": messages}
        if tools is not None:
            body["tools"] = tools
            body["tool_choice"] = "auto"

        last_err = "unknown"
        for attempt in range(max_retries):
            try:
                resp = self._http.post(self._url, json=body)
            except (httpx.ConnectError, httpx.TimeoutException, httpx.ReadError) as exc:
                last_err = f"{type(exc).__name__}"
                logger.warning(
                    "LLM transport error %s (attempt %d/%d); backing off",
                    last_err, attempt + 1, max_retries,
                )
                self._sleep_backoff(attempt)
                continue

            if resp.status_code == 200:
                try:
                    data = resp.json()
                except json.JSONDecodeError as exc:
                    raise RuntimeError(f"LLM returned non-JSON: {resp.text[:400]}") from exc
                choices = data.get("choices") or []
                if not choices:
                    raise RuntimeError(f"LLM response had no choices: {json.dumps(data)[:400]}")
                return choices[0].get("message", {}) or {}

            if resp.status_code in self._RETRYABLE:
                last_err = f"HTTP {resp.status_code}: {resp.text[:160]}"
                logger.warning(
                    "LLM transient %s (attempt %d/%d); backing off",
                    resp.status_code, attempt + 1, max_retries,
                )
                self._sleep_backoff(attempt)
                continue

            # Non-retryable (4xx other than the throttling codes) — fail fast.
            raise RuntimeError(f"LLM returned HTTP {resp.status_code}: {resp.text[:400]}")

        raise RuntimeError(f"LLM failed after {max_retries} attempts; last error: {last_err}")

    @staticmethod
    def _sleep_backoff(attempt: int) -> None:
        """Exponential backoff with jitter, capped at ~30s (2,4,8,16,30,30...)."""
        time.sleep(min(2 ** (attempt + 1), 30) + random.uniform(0, 1.0))


# ---------------------------------------------------------------------------
# Game-state summarization for the transcript + capture.
# ---------------------------------------------------------------------------


def summarize_state(state: dict[str, Any]) -> dict[str, Any]:
    """Compact, faithful summary of the raw /state payload for prompts + logs.

    Pulls the screen, run vitals, and (if present) a terse combat snapshot. This
    is *presentation* only -- no strategy, no card knowledge is injected.
    """
    summary: dict[str, Any] = {
        "screen": state.get("screen"),
        "in_combat": state.get("in_combat", False),
        "turn": state.get("turn"),
        "act": state.get("act"),
        "available_actions": state.get("available_actions", []),
    }
    run = state.get("run") or {}
    if run:
        summary["run"] = {
            "character": run.get("character_name") or run.get("character_id"),
            "floor": run.get("floor"),
            "ascension": run.get("ascension"),
            "hp": f"{run.get('current_hp')}/{run.get('max_hp')}",
            "gold": run.get("gold"),
            "relics": [r.get("name") for r in (run.get("relics") or [])],
            "deck_size": len(run.get("deck") or []),
            "potions": [p.get("name") for p in (run.get("potions") or []) if p.get("name")],
        }
    combat = state.get("combat") or {}
    if combat:
        player = combat.get("player") or {}
        summary["combat"] = {
            "player": {
                "hp": f"{player.get('current_hp')}/{player.get('max_hp')}",
                "block": player.get("block"),
                "energy": player.get("energy"),
            },
            "hand": [
                {
                    "index": c.get("index"),
                    "name": c.get("name"),
                    "cost": c.get("energy_cost"),
                    "playable": c.get("playable"),
                    "requires_target": c.get("requires_target"),
                    "valid_targets": c.get("valid_target_indices"),
                }
                for c in (combat.get("hand") or [])
            ],
            "enemies": [
                {
                    "index": e.get("index"),
                    "name": e.get("name"),
                    "hp": f"{e.get('current_hp')}/{e.get('max_hp')}",
                    "block": e.get("block"),
                    "alive": e.get("is_alive"),
                    "intents": [
                        {"type": i.get("intent_type"), "dmg": i.get("total_damage")}
                        for i in (e.get("intents") or [])
                    ],
                }
                for e in (combat.get("enemies") or [])
            ],
        }
    # Generic selection/reward/shop/event/map/rest screens: forward the agent_view
    # block verbatim if present (compact text the mod already prepared), else the
    # relevant raw block.
    agent_view = state.get("agent_view") or {}
    for key in ("map", "reward", "shop", "event", "rest", "selection", "chest", "game_over"):
        if agent_view.get(key) is not None:
            summary.setdefault("views", {})[key] = agent_view[key]
        elif state.get(key) is not None and key not in summary:
            summary.setdefault("views", {})[key] = state[key]
    return summary


def is_terminal(state: dict[str, Any]) -> tuple[bool, str | None]:
    """Return (terminal, outcome) where outcome is 'victory'|'defeat'|None.

    Mirrors derive_state_type: game_over.is_victory decides the outcome.
    """
    go = state.get("game_over")
    if go is not None:
        return True, ("victory" if go.get("is_victory") else "defeat")
    screen = str(state.get("screen", "")).upper()
    if screen in ("GAME_OVER", "VICTORY", "DEFEAT"):
        return True, ("victory" if screen == "VICTORY" else "defeat")
    return False, None


# ---------------------------------------------------------------------------
# Capture: per-step game_io.jsonl + final run_summary.json.
# ---------------------------------------------------------------------------


class GameCapture:
    """Writes captures/<run_id>/game_io.jsonl (one record/step) + run_summary.json."""

    def __init__(self, run_id: str, root: Path = CAPTURES_ROOT) -> None:
        self._dir = root / run_id
        self._dir.mkdir(parents=True, exist_ok=True)
        self._io_path = self._dir / "game_io.jsonl"
        self._seq = 0

    def step(
        self,
        *,
        state_summary: dict[str, Any],
        available_actions: Any,
        chosen_action: dict[str, Any] | None,
        action_result: dict[str, Any] | None,
    ) -> None:
        self._seq += 1
        record = {
            "seq": self._seq,
            "ts": time.time(),
            "state_summary": state_summary,
            "available_actions": available_actions,
            "chosen_action": chosen_action,
            "action_result": action_result,
        }
        with open(self._io_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")

    def summary(self, payload: dict[str, Any]) -> None:
        with open(self._dir / "run_summary.json", "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)


# ---------------------------------------------------------------------------
# The accumulating-context run loop.
# ---------------------------------------------------------------------------


def _trim_messages(messages: list[dict[str, Any]], cap: int) -> bool:
    """Drop the OLDEST whole decision-cycles if over ``cap``. Returns True if trimmed.

    The transcript is ``system`` then repeating cycles of ``user`` (state) ->
    ``assistant`` (tool_calls) -> one ``tool`` per call. We must NEVER cut inside
    a cycle: a leading ``tool`` with no preceding ``assistant``, or an
    ``assistant`` tool_call with no following ``tool`` result, makes the next
    chat-completions call HTTP 400. So we only cut at a ``user`` boundary: find
    the first ``user`` message at/after the overflow point and delete ``[1:cut]``.
    The kept region is then ``system`` + a suffix that starts on a clean cycle
    boundary (still valid because every retained assistant tool_call keeps its
    following tool results). If no safe boundary exists, we keep accumulating
    rather than risk corrupting the transcript.
    """
    if len(messages) <= cap:
        return False
    overflow = len(messages) - cap
    cut: int | None = None
    for idx in range(1 + overflow, len(messages)):
        if messages[idx].get("role") == "user":
            cut = idx
            break
    if cut is None or cut <= 1:
        return False  # no clean boundary -> accumulate (a big prompt beats a 400)
    del messages[1:cut]
    return True


def run(args: argparse.Namespace) -> int:
    """Drive a full run. Returns process exit code."""
    api_key = args.api_key or os.environ.get("STS2_GEMINI_API_KEY", "")
    if not api_key:
        logger.error("No API key. Set STS2_GEMINI_API_KEY or pass --api-key.")
        return 2

    mod = ModClient(args.mod_url)
    gemini = GeminiClient(args.proxy_url, api_key, args.model, args.run_id)
    capture = GameCapture(args.run_id)
    started_at = time.time()

    outcome = "agent_abort"
    final_floor = 0
    act_reached = 0
    stuck_aborts = 0
    steps = 0
    last_action_key: str | None = None
    repeat_count = 0

    # ONE accumulating transcript for the whole run (the whole point).
    messages: list[dict[str, Any]] = [{"role": "system", "content": SYSTEM_PROMPT}]

    try:
        # Health gate before doing anything expensive.
        health = mod.health()
        logger.info(
            "mod health: game_version=%s mod_version=%s",
            health.get("game_version"),
            health.get("mod_version"),
        )

        if not ensure_run_active(mod, args.character, args.ascension):
            outcome = "agent_abort"
            return _finish(capture, args, started_at, outcome, final_floor, act_reached, steps, stuck_aborts, gemini, mod)

        while steps < args.max_steps:
            steps += 1
            try:
                state = mod.get_state()
            except ModApiError as exc:
                logger.error("get_state failed at step %d: %s", steps, exc)
                outcome = "agent_abort"
                break

            terminal, term_outcome = is_terminal(state)
            run_block = state.get("run") or {}
            final_floor = run_block.get("floor", final_floor) or final_floor
            act_reached = state.get("act", act_reached) or act_reached
            if terminal:
                go = state.get("game_over") or {}
                final_floor = go.get("floor", final_floor) or final_floor
                outcome = term_outcome or "defeat"
                logger.info("run terminal: outcome=%s floor=%s", outcome, final_floor)
                capture.step(
                    state_summary=summarize_state(state),
                    available_actions=state.get("available_actions", []),
                    chosen_action=None,
                    action_result={"terminal": True, "outcome": outcome},
                )
                break

            summary = summarize_state(state)
            avail = mod.get_available_actions()  # hints (best-effort)

            # Append the fresh state as a user turn to the growing transcript.
            user_content = (
                "Current game state:\n"
                + json.dumps(summary, ensure_ascii=False)
                + "\n\nLegal-action hints:\n"
                + json.dumps(avail, ensure_ascii=False)
                + "\n\nChoose exactly one tool call to take the next action."
            )
            messages.append({"role": "user", "content": user_content})
            if _trim_messages(messages, args.max_context_messages):
                logger.warning(
                    "context cap (%d) exceeded; trimmed oldest messages (now %d)",
                    args.max_context_messages,
                    len(messages),
                )

            # Ask Gemini for a tool call.
            try:
                assistant = gemini.complete(messages, tools=TOOLS)
            except RuntimeError as exc:
                logger.error("LLM call failed at step %d: %s", steps, exc)
                outcome = "agent_abort"
                break
            messages.append(assistant)

            tool_calls = assistant.get("tool_calls") or []
            if not tool_calls:
                # No tool call -> nudge once via a tool-less reminder, then continue.
                logger.info("step %d: model returned no tool call; reminding", steps)
                messages.append(
                    {
                        "role": "user",
                        "content": "You must call exactly one tool (get_state, "
                        "get_available_actions, or take_action) to proceed.",
                    }
                )
                continue

            chosen_action: dict[str, Any] | None = None
            action_result: dict[str, Any] | None = None

            # Execute each requested tool call and append a matching tool result.
            for call in tool_calls:
                fn = (call.get("function") or {})
                name = fn.get("name", "")
                call_id = call.get("id", "")
                try:
                    arguments = json.loads(fn.get("arguments") or "{}")
                except json.JSONDecodeError:
                    arguments = {}

                tool_payload: Any
                if name == "get_state":
                    tool_payload = summarize_state(mod.get_state())
                elif name == "get_available_actions":
                    tool_payload = mod.get_available_actions()
                elif name == "take_action":
                    verb = arguments.get("verb", "")
                    params = arguments.get("params") or {}
                    if not verb:
                        tool_payload = {"error": "take_action requires a 'verb'"}
                    else:
                        body = {"action": verb, **{k: v for k, v in params.items() if v is not None}}
                        chosen_action = body
                        try:
                            result = mod.post_action(body)
                            action_result = {
                                "status": result.get("status"),
                                "stable": result.get("stable"),
                                "message": result.get("message"),
                            }
                            tool_payload = action_result
                        except ModApiError as exc:
                            action_result = {"error": str(exc), "code": exc.code, "retryable": exc.retryable}
                            tool_payload = action_result
                else:
                    tool_payload = {"error": f"unknown tool '{name}'"}

                messages.append(
                    {
                        "role": "tool",
                        "tool_call_id": call_id,
                        "content": json.dumps(tool_payload, ensure_ascii=False),
                    }
                )

            # Per-step game-I/O capture (records the action this step, if any).
            capture.step(
                state_summary=summary,
                available_actions=state.get("available_actions", []),
                chosen_action=chosen_action,
                action_result=action_result,
            )

            # Stuck detection: same action body repeated N times in a row.
            if chosen_action is not None:
                action_key = json.dumps(chosen_action, sort_keys=True)
                if action_key == last_action_key:
                    repeat_count += 1
                else:
                    repeat_count = 0
                    last_action_key = action_key
                if repeat_count + 1 >= args.stuck_repeat:
                    stuck_aborts += 1
                    logger.error(
                        "stuck: identical action repeated %d times (%s); aborting run cleanly",
                        repeat_count + 1,
                        action_key,
                    )
                    outcome = "agent_abort"
                    break

            _sleep(args.action_delay)

        else:
            outcome = "max_steps"
            logger.info("reached --max-steps (%d) without terminal state", args.max_steps)

    except ModApiError as exc:
        logger.error("fatal mod error: %s", exc)
        outcome = "agent_abort"
    except KeyboardInterrupt:
        logger.warning("interrupted by user")
        outcome = "agent_abort"

    return _finish(
        capture, args, started_at, outcome, final_floor, act_reached, steps, stuck_aborts, gemini, mod
    )


def _finish(
    capture: GameCapture,
    args: argparse.Namespace,
    started_at: float,
    outcome: str,
    final_floor: int,
    act_reached: int,
    steps: int,
    stuck_aborts: int,
    gemini: GeminiClient,
    mod: ModClient,
) -> int:
    """Write run_summary.json, close clients, and return an exit code."""
    ended_at = time.time()
    summary = {
        "run_id": args.run_id,
        "outcome": outcome,
        "victory": outcome == "victory",
        "final_floor": final_floor,
        "act_reached": act_reached,
        "character": args.character,
        "ascension": args.ascension,
        "model": args.model,
        "experiment_tag": args.experiment_tag,
        "steps": steps,
        "started_at": started_at,
        "ended_at": ended_at,
        "duration_seconds": round(ended_at - started_at, 1),
        "stuck_aborts": stuck_aborts,
        "started_at_iso": datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
        "ended_at_iso": datetime.now(timezone.utc).isoformat(),
    }
    capture.summary(summary)
    logger.info("run finished: %s", json.dumps(summary))
    gemini.close()
    mod.close()
    return 0 if outcome in ("victory", "defeat", "max_steps") else 1


# ---------------------------------------------------------------------------
# --dry-run self-test: mod /health + a trivial 1-message Gemini call.
# ---------------------------------------------------------------------------


def dry_run(args: argparse.Namespace) -> int:
    """Smoke connectivity: mod /health + a 1-message Gemini round-trip via proxy."""
    api_key = args.api_key or os.environ.get("STS2_GEMINI_API_KEY", "")
    ok = True

    print("== mod /health ==")
    mod = ModClient(args.mod_url)
    try:
        health = mod.health()
        print(json.dumps(health, indent=2, ensure_ascii=False))
    except ModApiError as exc:
        ok = False
        print(f"FAIL: {exc}")
    finally:
        mod.close()

    print("\n== Gemini 1-message call (via proxy) ==")
    if not api_key:
        ok = False
        print("FAIL: no API key (set STS2_GEMINI_API_KEY or --api-key)")
    else:
        gemini = GeminiClient(args.proxy_url, api_key, args.model, args.run_id)
        try:
            msg = gemini.complete(
                [{"role": "user", "content": "Reply with exactly: OK"}]
            )
            print(json.dumps({"content": msg.get("content"), "role": msg.get("role")}, indent=2))
        except RuntimeError as exc:
            ok = False
            print(f"FAIL: {exc}")
        finally:
            gemini.close()

    print(f"\n== dry-run {'PASSED' if ok else 'FAILED'} ==")
    return 0 if ok else 1


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _sleep(seconds: float) -> None:
    """Blocking sleep wrapper (kept tiny so the loop reads cleanly)."""
    if seconds > 0:
        time.sleep(seconds)


def _default_run_id() -> str:
    return "naive-gemini-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="naive_gemini_agent",
        description=(
            "Naive accumulating-context Gemini agent that plays Slay the Spire 2 over "
            "our mod's REST API. Baseline for Workstream C competitor comparison."
        ),
    )
    p.add_argument("--character", default="Silent", help="Character to play (default: Silent).")
    p.add_argument("--ascension", type=int, default=0, help="Target ascension (default: 0 = A0 floor).")
    p.add_argument("--mod-url", default="http://127.0.0.1:8128", help="Game mod REST base URL.")
    p.add_argument(
        "--proxy-url",
        default="http://127.0.0.1:8129/v1",
        help="OpenAI-compatible LLM base URL (the logging proxy).",
    )
    p.add_argument("--model", default="gemini-3.1-pro-preview", help="Model id sent to the proxy.")
    p.add_argument("--api-key", default=None, help="LLM API key (else $STS2_GEMINI_API_KEY).")
    p.add_argument("--run-id", default=None, help="Run id (default: timestamped). Tags captures via X-Run-Id.")
    p.add_argument("--max-steps", type=int, default=800, help="Hard step cap before max_steps abort.")
    p.add_argument(
        "--max-context-messages",
        type=int,
        default=400,
        help="Trim oldest non-system messages only if the transcript exceeds this (default accumulate).",
    )
    p.add_argument(
        "--stuck-repeat",
        type=int,
        default=8,
        help="Abort after this many identical actions in a row (stuck guard).",
    )
    p.add_argument("--action-delay", type=float, default=0.6, help="Delay (s) between actions.")
    p.add_argument(
        "--experiment-tag",
        default="competitor-chartyr-gemini-A0",
        help="experiment_tag written to run_summary.json. Matches the "
        "runs/history.jsonl schema; scripts/reproduce/* filter on this field, so "
        "competitor runs are only visible to analysis if it is set.",
    )
    p.add_argument("--dry-run", action="store_true", help="Smoke-test mod /health + Gemini, then exit.")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.run_id is None:
        args.run_id = _default_run_id()
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )
    if args.dry_run:
        return dry_run(args)
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
