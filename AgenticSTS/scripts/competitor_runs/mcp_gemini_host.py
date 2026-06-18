"""Gemini-backed MCP host that drives the STS2MCP / CharTyr competitor agents.

This reproduces each competitor's **author-intended** play path -- their own stdio
MCP server plus their own skill/strategy docs as the system prompt -- but swaps in
**Gemini 3.1 Pro** as the model (matching our paper headline) so the comparison holds
model/difficulty/game/scoring constant while letting each system use its strongest,
fairest form. The authors used an MCP client (Claude Code / Desktop) + skill docs; we
are that client, with Gemini. See ``docs/experiments/competitor_comparison/PLAN.md``
(this is the "C.2b Gemini MCP host").

Pipeline (per the plan)::

    Gemini MCP host  --(this file)-->  competitor stdio MCP server  -->  competitor C# mod
          |  OpenAI /v1/chat/completions (function-calling)
          v
    logging proxy (:8129)  -- tees LLM I/O --> captures/<run_id>/llm_calls.jsonl
          v
    Gemini relay (STS2_GEMINI_BASE_URL)

What this host does:
  * Launches a competitor's stdio MCP server (registry below) and performs the MCP
    handshake via the official ``mcp`` Python SDK (``stdio_client`` + ``ClientSession``).
  * Discovers ALL of that server's tools (``tools/list``) and maps each to a Gemini
    function-calling tool (name / description / inputSchema -> function / parameters),
    so Gemini sees exactly what the author's agent saw.
  * Loads the competitor's own skill docs verbatim and concatenates them into the
    system prompt (the docs themselves instruct character-select + embark, so Gemini
    drives run setup through the MCP tools).
  * Runs ONE accumulating ``messages`` transcript (never reset; trimmed only on clean
    turn boundaries via the reused ``_trim_messages``), dispatching each Gemini tool
    call to MCP ``tools/call`` and appending a ``role:"tool"`` result.
  * Captures LLM I/O through the proxy (``X-Run-Id``) and MCP tool I/O to
    ``captures/<run_id>/game_io.jsonl`` + a run-history-shaped ``run_summary.json``.

Reused from the sibling ``naive_gemini_agent`` module (do NOT reinvent):
  * ``GeminiClient``  -- OpenAI-compatible chat-completions through the logging proxy.
  * ``GameCapture``   -- ``game_io.jsonl`` + ``run_summary.json`` writer.
  * ``_trim_messages``-- accumulating-context trim that cuts only on ``user`` boundaries
    so tool-call / tool-result pairing is never broken (a corrupt pair => HTTP 400).

The ``GeminiClient`` is synchronous (httpx); we call it from the async run loop via
``asyncio.to_thread`` so the event loop is never blocked while the model thinks.

Dependency: the official MCP SDK -- ``pip install mcp`` (documented in the README).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import httpx

# Reuse the battle-tested building blocks from the naive agent (same package).
from scripts.competitor_runs.naive_gemini_agent import (
    GameCapture,
    GeminiClient,
    _trim_messages,
)

try:
    from mcp import ClientSession, StdioServerParameters
    from mcp.client.stdio import stdio_client
except ImportError as exc:  # pragma: no cover - surfaced as an actionable CLI error.
    raise SystemExit(
        "The MCP Python SDK is required for this host but is not installed.\n"
        "Install it with:  pip install mcp\n"
        f"(import error: {exc})"
    ) from exc

logger = logging.getLogger("mcp_gemini_host")

# Default location of the cloned competitor repos (gitignored). Overridable via
# --competitor-root so the absolute stdio launch paths resolve on any machine.
_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_COMPETITOR_ROOT = _REPO_ROOT / "paper" / "competitors"


# ---------------------------------------------------------------------------
# Per-competitor registry.
# ---------------------------------------------------------------------------
#
# Each entry resolves, given a competitor root:
#   * launch:        how to start the stdio MCP server (command/args/cwd/env).
#   * skill_docs:    paths (relative to the competitor root) whose contents are
#                    concatenated -- verbatim -- into the system prompt. These are the
#                    docs the author's README/command tells the agent to read.
#   * state_tool:    the MCP tool to poll for the current game state.
#   * state_args:    arguments for that state tool (e.g. STS2MCP wants format=json so
#                    its `state_type` field is machine-parseable).
#
# Verified facts (read 2026-06-05/06):
#   STS2MCP (mcp/server.py): FastMCP("sts2"); get_game_state(format) returns the state;
#     `state_type == "game_over"` marks run end (docs/raw-simplified.md state-type table).
#     Launched via `uv run --directory <root>/STS2MCP/mcp python server.py`
#     (its README MCP-config block uses exactly this command).
#   CharTyr (mcp_server/src/sts2_mcp/server.py): FastMCP; get_game_state() returns the
#     compact agent_view with a `screen` field; SKILL.md routes GAME_OVER ->
#     return_to_main_menu, so `screen == "GAME_OVER"` marks run end. Launched via
#     `uv run sts2-mcp-server` (pyproject script -> sts2_mcp.server:main) with cwd
#     <root>/CharTyr/mcp_server.


class CompetitorSpec:
    """Static description of one competitor's MCP server + skill docs + state tool.

    Pure data plus a couple of resolution helpers; no I/O until the caller asks.
    """

    def __init__(
        self,
        *,
        key: str,
        display_name: str,
        command: str,
        args_factory: Any,  # Callable[[Path], list[str]]
        cwd_factory: Any,  # Callable[[Path], Path | None]
        skill_docs: list[str],
        state_tool: str,
        state_args: dict[str, Any],
        default_experiment_tag: str,
        notes: str = "",
    ) -> None:
        self.key = key
        self.display_name = display_name
        self.command = command
        self._args_factory = args_factory
        self._cwd_factory = cwd_factory
        self.skill_docs = skill_docs
        self.state_tool = state_tool
        self.state_args = state_args
        self.default_experiment_tag = default_experiment_tag
        self.notes = notes

    def args(self, competitor_root: Path) -> list[str]:
        return self._args_factory(competitor_root)

    def cwd(self, competitor_root: Path) -> Path | None:
        return self._cwd_factory(competitor_root)

    def skill_doc_paths(self, competitor_root: Path) -> list[Path]:
        return [competitor_root / rel for rel in self.skill_docs]


REGISTRY: dict[str, CompetitorSpec] = {
    "sts2mcp": CompetitorSpec(
        key="sts2mcp",
        display_name="STS2MCP (Gennadiyev/STS2MCP)",
        command="uv",
        # `uv run --directory <root>/STS2MCP/mcp python server.py` -- the exact command
        # from STS2MCP/README.md's MCP-config block. `uv` reads mcp/pyproject.toml +
        # uv.lock and runs server.py in an isolated, pinned venv.
        args_factory=lambda root: [
            "run",
            "--directory",
            str(root / "STS2MCP" / "mcp"),
            "python",
            "server.py",
        ],
        cwd_factory=lambda root: None,  # --directory already targets the server dir.
        # playsts2.md is the author's "/playsts2" command; it tells the agent to read
        # AGENTS.md (general strategy + MCP tips) and GUIDE.md (hero-specific; created
        # by the agent after bosses -- absent in a fresh clone, loaded if present). The
        # README also points skill users at docs/raw-*.md (the state/action reference);
        # raw-simplified.md is the compact one.
        skill_docs=[
            "STS2MCP/.claude/commands/playsts2.md",
            "STS2MCP/AGENTS.md",
            "STS2MCP/GUIDE.md",
            "STS2MCP/docs/raw-simplified.md",
        ],
        state_tool="get_game_state",
        state_args={"format": "json"},  # so `state_type` is reliably parseable.
        default_experiment_tag="competitor-sts2mcp-gemini-A0",
        notes="Terminal when state_type == 'game_over'.",
    ),
    "chartyr": CompetitorSpec(
        key="chartyr",
        display_name="CharTyr (CharTyr/STS2-Agent)",
        command="uv",
        # `uv run sts2-mcp-server` from the mcp_server dir (pyproject console-script
        # -> sts2_mcp.server:main). cwd must be the package root so uv finds it.
        args_factory=lambda root: ["run", "sts2-mcp-server"],
        cwd_factory=lambda root: root / "CharTyr" / "mcp_server",
        # The author's skill + its references + the game-knowledge playbook. SKILL.md is
        # the entry; screen-playbooks.md gives per-screen action order; playbook.md is
        # the game-knowledge bridge. (references/cards.md etc. are absolute Mac paths in
        # the docs and not present in this clone -- we load the ones that exist.)
        skill_docs=[
            "CharTyr/skills/sts2-mcp-player/SKILL.md",
            "CharTyr/skills/sts2-mcp-player/references/screen-playbooks.md",
            "CharTyr/docs/game-knowledge/playbook.md",
        ],
        state_tool="get_game_state",
        state_args={},  # compact agent_view; no format arg.
        default_experiment_tag="competitor-chartyr-gemini-A0",
        notes="Terminal when screen == 'GAME_OVER'.",
    ),
}


# ---------------------------------------------------------------------------
# System-prompt assembly from the competitor's own skill docs.
# ---------------------------------------------------------------------------

# Prepended to the concatenated skill docs: tells Gemini it IS the MCP-client agent
# the docs assume, names the target character/ascension (the docs instruct setup), and
# sets the goal. Kept minimal so the *competitor's* docs do the strategic talking.
_HOST_PREAMBLE = (
    "You are an autonomous agent playing Slay the Spire 2 through MCP tools. The "
    "documentation below is THIS project's own player skill / strategy guide -- follow "
    "it. You drive the entire run: read the game state with the provided tools, then "
    "take exactly one legal action per turn until the run ends (victory or defeat).\n\n"
    "Target run: character = {character}, ascension = A{ascension} (singleplayer). The "
    "guide explains how to start a run -- open character select, choose {character}, "
    "set ascension to {ascension} if adjustable, then embark. Each run MUST be a FRESH "
    "singleplayer run started from character select -- do NOT continue, resume, or load a "
    "previously saved run. If the game offers 'Continue' or a run is already in progress, "
    "do NOT take it; start a new {character} A{ascension} run instead (abandon the old run "
    "if necessary). Call exactly one tool per response. After every action, "
    "read fresh state; never reuse stale indices.\n\n"
    "=== PROJECT PLAYER GUIDE (verbatim) ===\n"
)


def build_system_prompt(spec: CompetitorSpec, competitor_root: Path, *, character: str, ascension: int) -> str:
    """Concatenate the competitor's skill docs (verbatim) into one system prompt.

    Missing docs are skipped with a warning (e.g. STS2MCP's GUIDE.md only exists after
    the agent has written it; CharTyr's absolute-path game-knowledge files are not in
    this clone). At least one doc must load, else the run would not be faithful.
    """
    sections: list[str] = [
        _HOST_PREAMBLE.format(character=character, ascension=ascension)
    ]
    loaded = 0
    for path in spec.skill_doc_paths(competitor_root):
        try:
            text = path.read_text(encoding="utf-8")
        except FileNotFoundError:
            logger.warning("skill doc not found (skipping): %s", path)
            continue
        except OSError as exc:
            logger.warning("could not read skill doc %s (skipping): %s", path, exc)
            continue
        rel = path.relative_to(competitor_root) if competitor_root in path.parents else path.name
        sections.append(f"\n----- BEGIN {rel} -----\n{text}\n----- END {rel} -----\n")
        loaded += 1

    if loaded == 0:
        raise FileNotFoundError(
            f"No skill docs could be loaded for '{spec.key}'. Checked: "
            + ", ".join(str(p) for p in spec.skill_doc_paths(competitor_root))
            + ". Pass --skill-docs to override, or fix --competitor-root."
        )

    logger.info("assembled system prompt from %d skill doc(s)", loaded)
    return "".join(sections)


# ---------------------------------------------------------------------------
# MCP tools/list -> Gemini function-calling schemas.
# ---------------------------------------------------------------------------


_GEMINI_TYPES = {"string", "number", "integer", "boolean", "array", "object"}


def _gemini_safe_node(node: Any) -> dict[str, Any]:
    """Coerce one JSON-Schema node into the strict subset Gemini function-calling accepts.

    Gemini (unlike OpenAI) rejects a functionDeclaration if ANY property lacks a
    ``type``, and it does not accept ``anyOf``/``oneOf`` unions or ``["T","null"]`` type
    lists (which Python ``int | None`` params serialize to via the MCP SDK). We:
      * resolve a single concrete ``type`` (from the node, a type-list, or the first
        typed ``anyOf``/``oneOf``/``allOf`` member; default ``string``),
      * recurse into ``properties`` and ``items``,
      * keep only the supported keys (type/description/enum/properties/items/required).
    This changes only the *schema shape*, never the tool's name or meaning.
    """
    if not isinstance(node, dict):
        return {"type": "string"}

    t = node.get("type")
    merged = node
    if t is None:
        for key in ("anyOf", "oneOf", "allOf"):
            members = node.get(key)
            if isinstance(members, list):
                for m in members:
                    if isinstance(m, dict) and m.get("type") and m.get("type") != "null":
                        t = m.get("type")
                        merged = {**m, "description": node.get("description") or m.get("description")}
                        break
            if t:
                break
    if isinstance(t, list):  # e.g. ["integer", "null"]
        t = next((x for x in t if x != "null"), None)
    if t not in _GEMINI_TYPES:
        t = "string"

    out: dict[str, Any] = {"type": t}
    desc = merged.get("description") or node.get("description")
    if desc:
        out["description"] = desc
    if merged.get("enum"):
        out["enum"] = merged["enum"]
    if t == "object":
        props = merged.get("properties") or {}
        out["properties"] = {k: _gemini_safe_node(v) for k, v in props.items()}
        req = [r for r in (merged.get("required") or []) if r in out["properties"]]
        if req:
            out["required"] = req
    elif t == "array":
        out["items"] = _gemini_safe_node(merged.get("items") or {"type": "string"})
    return out


def _sanitize_input_schema(input_schema: Any) -> dict[str, Any]:
    """Coerce an MCP tool inputSchema into a Gemini-safe function-parameters object.

    Always returns a top-level ``object`` whose every (possibly nested) property has a
    concrete ``type`` — Gemini rejects the entire request otherwise (observed:
    STS2MCP ``menu_select.seed`` had no type).
    """
    if not isinstance(input_schema, dict) or not input_schema:
        return {"type": "object", "properties": {}}
    safe = _gemini_safe_node({**input_schema, "type": "object"})
    safe.setdefault("properties", {})
    return safe


def mcp_tools_to_gemini(tools: list[Any]) -> list[dict[str, Any]]:
    """Map every discovered MCP tool to an OpenAI-compatible function-tool schema.

    We expose ALL of the competitor server's tools (faithful to what the author's agent
    saw -- no filtering, no renaming).
    """
    gemini_tools: list[dict[str, Any]] = []
    for tool in tools:
        gemini_tools.append(
            {
                "type": "function",
                "function": {
                    "name": tool.name,
                    "description": (tool.description or "").strip(),
                    "parameters": _sanitize_input_schema(getattr(tool, "inputSchema", None)),
                },
            }
        )
    return gemini_tools


# ---------------------------------------------------------------------------
# MCP call-result -> a JSON-serializable payload + plain text for parsing.
# ---------------------------------------------------------------------------


def _result_to_text(call_result: Any) -> str:
    """Extract the textual content of a CallToolResult (concatenated text blocks).

    MCP results carry a ``content`` list of typed blocks; text tools (both competitors
    return JSON/markdown strings) put their payload in ``TextContent.text``. We join all
    text blocks; non-text blocks are summarized by type so nothing is silently dropped.
    """
    pieces: list[str] = []
    for block in getattr(call_result, "content", None) or []:
        btype = getattr(block, "type", None)
        if btype == "text":
            pieces.append(getattr(block, "text", "") or "")
        else:
            pieces.append(f"[non-text content: {btype}]")
    return "\n".join(p for p in pieces if p)


def _result_to_payload(call_result: Any) -> Any:
    """A JSON-friendly view of a CallToolResult for the tool message + capture.

    Prefers ``structuredContent`` when the server provides it; otherwise the text. If
    the text parses as JSON we keep it structured; else we pass the raw string through.
    Errors (``isError``) are wrapped so the model sees them as data, not a crash.
    """
    structured = getattr(call_result, "structuredContent", None)
    if structured is not None:
        payload: Any = structured
    else:
        text = _result_to_text(call_result)
        try:
            payload = json.loads(text)
        except (json.JSONDecodeError, TypeError):
            payload = text
    if getattr(call_result, "isError", False):
        return {"error": True, "result": payload}
    return payload


# ---------------------------------------------------------------------------
# Terminal / outcome detection (per competitor; best-effort victory vs defeat).
# ---------------------------------------------------------------------------

# Markers we scan for once a run is known to be over, to split victory from defeat.
_VICTORY_MARKERS = ("victory", "you win", "you won", "run complete", "ascension complete", "is_victory\": true", "\"won\": true")
_DEFEAT_MARKERS = ("defeat", "you died", "you lose", "you lost", "game over - defeat", "is_victory\": false", "\"dead\": true")


def _unwrap_state(payload: Any) -> Any:
    """Return the real state object for terminal / progress inspection.

    STS2MCP returns its state inside a single-key envelope ``{"result": "<json string>"}``
    (because ``get_game_state(format="json")`` is delivered as a TextContent blob, which
    ``_result_to_payload`` parses one level, leaving the inner JSON as a *string*). CharTyr
    returns the agent_view dict directly. Both ``detect_terminal`` and ``_extract_progress``
    look up ``state_type`` / ``run`` at the TOP level, so without this unwrap STS2MCP's
    fields are invisible — game_over is never detected (run forced to --max-steps) and
    floor/act stay 0. We unwrap the envelope (parsing the JSON string) and pass through
    anything that is already a dict or is non-JSON text (markdown) untouched.
    """
    inner = payload
    if isinstance(payload, dict) and set(payload.keys()) == {"result"}:
        inner = payload["result"]
    if isinstance(inner, str):
        s = inner.strip()
        if s[:1] in ("{", "["):
            try:
                return json.loads(s)
            except (json.JSONDecodeError, ValueError):
                return payload
        return payload  # markdown / plain text — keep original so blob scans still work
    return inner if isinstance(inner, dict) else payload


def detect_terminal(spec: CompetitorSpec, state_payload: Any) -> tuple[bool, str | None]:
    """Return ``(terminal, outcome)`` where outcome is 'victory' | 'defeat' | None.

    Terminal is screen-driven and reliable per competitor:
      * STS2MCP: state_type == 'game_over'.
      * CharTyr: screen == 'GAME_OVER'.
    Victory-vs-defeat is a best-effort keyword/field scan (neither server exposes a
    clean victory boolean in the documented state), so we record 'victory'/'defeat'
    when a marker is found and fall back to 'defeat' (the common case) otherwise. The
    caller ALWAYS independently honors --max-steps and the stuck guard, so a missed
    terminal can never hang the run.
    """
    # Normalise to a lowercase text blob for screen + marker scanning. We keep this
    # tolerant because state_payload may be a dict (json/structured) or a markdown str.
    st = _unwrap_state(state_payload)
    if isinstance(st, dict):
        screen_field = str(
            st.get("state_type")
            or st.get("screen")
            or ""
        ).strip().lower()
        blob = json.dumps(st, ensure_ascii=False).lower()
    else:
        screen_field = ""
        blob = str(st).lower()

    terminal = False
    if spec.key == "sts2mcp":
        terminal = screen_field == "game_over" or "\"state_type\": \"game_over\"" in blob
    elif spec.key == "chartyr":
        terminal = screen_field == "game_over" or "\"screen\": \"game_over\"" in blob
    # Generic safety net (covers markdown headers like "# Game Over").
    if not terminal and ("game_over" in screen_field or "game over" in blob):
        terminal = True

    if not terminal:
        return False, None

    # Classify victory vs defeat PRECISELY. Prefer the structured game_over flag
    # (CharTyr exposes game_over.is_victory). A loose substring scan is WRONG here: the
    # literal "victory" lives inside the key "is_victory", so scanning the blob would tag
    # every defeat (is_victory=false) as a win -- the exact bug that mislabeled all 5
    # CharTyr runs as victories at floor 5-6.
    if isinstance(st, dict):
        go = st.get("game_over")
        flag = None
        if isinstance(go, dict) and isinstance(go.get("is_victory"), bool):
            flag = go.get("is_victory")
        elif isinstance(st.get("is_victory"), bool):
            flag = st.get("is_victory")
        if flag is not None:
            return True, ("victory" if flag else "defeat")
    # Fallback: precise tokens only (the value `true`, never the bare word "victory").
    if ('"is_victory": true' in blob or '"won": true' in blob or "you win" in blob
            or "you won" in blob or "run complete" in blob or "ascension complete" in blob):
        return True, "victory"
    return True, "defeat"  # ambiguous terminal -> defeat (the overwhelmingly common end)


_DEAD_MARKERS = (
    "无法连接", "connection refused", "connecterror", "max retries", "cannot connect",
    "failed to establish", "connection aborted", "remote server", "[errno", "timed out",
    "connection error", "newconnectionerror", "connection reset",
)


def _is_dead_state(payload: Any) -> bool:
    """True only if a state read is a CONNECTION/transport error (game/mod unreachable).

    STS2MCP returns real state as ``{"result": "# Game State ...markdown..."}`` and CharTyr
    as a state dict, so we must NOT treat "no expected key" as dead (that false-aborts real
    runs). We flag dead ONLY when the payload contains a connection-error signature — that
    is the genuine "game closed/crashed mid-run" case the guard exists for.
    """
    blob = (payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False)).lower()
    return any(m in blob for m in _DEAD_MARKERS)


def _extract_progress(state_payload: Any, prev_floor: int, prev_act: int) -> tuple[int, int]:
    """Best-effort (floor, act) read from a state payload (dict only; else carry over).

    Both servers expose a ``run`` block with ``floor``/``act`` when in a run; absent at
    the menu. We never regress the high-water marks.
    """
    st = _unwrap_state(state_payload)
    if not isinstance(st, dict):
        return prev_floor, prev_act
    run = st.get("run")
    floor, act = prev_floor, prev_act
    if isinstance(run, dict):
        try:
            floor = max(prev_floor, int(run.get("floor", prev_floor) or prev_floor))
        except (TypeError, ValueError):
            pass
        try:
            act = max(prev_act, int(run.get("act", prev_act) or prev_act))
        except (TypeError, ValueError):
            pass
    return floor, act


# ---------------------------------------------------------------------------
# MCP session helper: launch the server, handshake, expose tools/list + tools/call.
# ---------------------------------------------------------------------------


class McpServerError(RuntimeError):
    """The MCP server could not be launched or a tools call failed unrecoverably."""


def _server_params(spec: CompetitorSpec, competitor_root: Path) -> StdioServerParameters:
    """Build StdioServerParameters for a competitor, inheriting the parent env.

    We pass the current environment through so ``uv`` / proxy settings the user has
    exported are honored by the child server process.
    """
    args = spec.args(competitor_root)
    cwd = spec.cwd(competitor_root)
    return StdioServerParameters(
        command=spec.command,
        args=args,
        cwd=str(cwd) if cwd is not None else None,
        env=dict(os.environ),
    )


def _format_launch(spec: CompetitorSpec, competitor_root: Path) -> str:
    cwd = spec.cwd(competitor_root)
    cmd = " ".join([spec.command, *spec.args(competitor_root)])
    return f"{cmd}" + (f"   (cwd={cwd})" if cwd is not None else "")


def _our_mod_reachable(url: str, timeout: float = 2.0) -> bool:
    """True if OUR mod's health endpoint answers at ``url`` (i.e. it is still loaded).

    Enforces the complete-replacement rule: a competitor run must never see our mod.
    Our mod and every competitor mod Harmony-patch the game, so only one can be in the
    game's ``mods/`` folder at a time; if ours is still serving (default :8128) the
    competitor's mod cannot own the game AND the competitor agent could read our
    enriched state. Either way the run would be contaminated, so we refuse to start.
    """
    try:
        resp = httpx.get(url, timeout=timeout)
        return resp.status_code < 500
    except Exception:  # noqa: BLE001 - any connection failure means it's not serving.
        return False


async def _call_state(
    session: ClientSession, spec: CompetitorSpec, *, timeout_s: float
) -> Any:
    """Call the competitor's state tool and return its parsed payload.

    Wrapped so a transport hiccup yields an actionable error rather than a bare
    exception bubbling through the run loop.
    """
    try:
        result = await session.call_tool(
            spec.state_tool,
            arguments=dict(spec.state_args),
            read_timeout_seconds=timedelta(seconds=timeout_s),
        )
    except Exception as exc:  # noqa: BLE001 - normalize all transport/SDK errors.
        raise McpServerError(
            f"State tool '{spec.state_tool}' failed: {exc}. Is the game running with "
            f"the {spec.display_name} mod loaded and reachable?"
        ) from exc
    return _result_to_payload(result)


# ---------------------------------------------------------------------------
# The accumulating-context run loop (async).
# ---------------------------------------------------------------------------


async def run_session(args: argparse.Namespace, spec: CompetitorSpec) -> int:
    """Drive a full run against ``spec``. Returns a process exit code."""
    api_key = args.api_key or os.environ.get("STS2_GEMINI_API_KEY", "")
    if not api_key:
        logger.error("No API key. Set STS2_GEMINI_API_KEY or pass --api-key.")
        return 2

    # Complete-replacement guard: OUR mod must be fully removed so the competitor agent
    # only ever sees the competitor's own mod (fairness + no contamination). If our mod
    # still answers on :8128 it is still loaded -- refuse to start.
    if not args.allow_our_mod:
        if await asyncio.to_thread(_our_mod_reachable, args.our_mod_url):
            logger.error(
                "OUR mod is still reachable at %s -- remove it from the game's mods/ "
                "folder before a competitor run. Complete-replacement rule: the "
                "competitor agent must never read our mod's state, and only one mod can "
                "patch the game at a time. Remove our mod, confirm %s is dead, re-run. "
                "(Override with --allow-our-mod only if you are deliberately not "
                "isolating -- not recommended.)",
                args.our_mod_url,
                args.our_mod_url,
            )
            return 3

    competitor_root = Path(args.competitor_root).resolve()
    system_prompt = build_system_prompt(
        spec, competitor_root, character=args.character, ascension=args.ascension
    )

    gemini = GeminiClient(args.proxy_url, api_key, args.model, args.run_id)
    capture = GameCapture(args.run_id)
    started_at = datetime.now(timezone.utc).timestamp()

    outcome = "agent_abort"
    final_floor = 0
    act_reached = 0
    steps = 0
    stuck_aborts = 0
    dead_states = 0
    last_call_key: str | None = None
    repeat_count = 0
    started = False  # a run only "starts" once a real in-run state is seen (terminal gate below)

    # ONE accumulating transcript for the whole run (system = competitor skill docs).
    messages: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]

    params = _server_params(spec, competitor_root)
    logger.info("launching MCP server: %s", _format_launch(spec, competitor_root))

    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                try:
                    await asyncio.wait_for(session.initialize(), timeout=args.handshake_timeout)
                except Exception as exc:  # noqa: BLE001
                    raise McpServerError(
                        f"MCP handshake (initialize) failed: {exc}. The server process "
                        f"may have crashed on startup (uv/deps?)."
                    ) from exc

                tools_result = await session.list_tools()
                discovered = list(tools_result.tools)
                tool_names = [t.name for t in discovered]
                logger.info("discovered %d MCP tools: %s", len(discovered), ", ".join(tool_names))
                if not discovered:
                    raise McpServerError("Server exposed no tools; cannot drive a run.")
                gemini_tools = mcp_tools_to_gemini(discovered)
                valid_tool_names = set(tool_names)

                # Kick off: give Gemini the goal + a first instruction. The skill docs
                # tell it to read state then drive setup; it issues the first tool call.
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            "Begin. Read the current game state with the appropriate "
                            "tool, then drive the run per the guide. Start a FRESH "
                            f"{args.character} A{args.ascension} singleplayer run from "
                            "character select. Do NOT continue or load any saved run -- if "
                            "'Continue' is offered or a run is already in progress, start a "
                            "new run instead. Call exactly one tool now."
                        ),
                    }
                )

                while steps < args.max_steps:
                    steps += 1

                    if _trim_messages(messages, args.max_context_messages):
                        logger.warning(
                            "context cap (%d) exceeded; trimmed oldest cycle(s) (now %d msgs)",
                            args.max_context_messages,
                            len(messages),
                        )

                    # 1) Ask Gemini for the next tool call (sync client off the loop).
                    try:
                        assistant = await asyncio.to_thread(
                            gemini.complete, messages, tools=gemini_tools
                        )
                    except RuntimeError as exc:
                        logger.error("LLM call failed at step %d: %s", steps, exc)
                        outcome = "agent_abort"
                        break
                    messages.append(assistant)

                    tool_calls = assistant.get("tool_calls") or []
                    if not tool_calls:
                        logger.info("step %d: model returned no tool call; reminding", steps)
                        messages.append(
                            {
                                "role": "user",
                                "content": (
                                    "You must call exactly one MCP tool to proceed "
                                    "(read state or take an action)."
                                ),
                            }
                        )
                        continue

                    chosen_action: dict[str, Any] | None = None
                    action_result: dict[str, Any] | None = None
                    latest_state_payload: Any = None

                    # 2) Dispatch each requested tool call to MCP and append a result.
                    for call in tool_calls:
                        fn = call.get("function") or {}
                        name = fn.get("name", "")
                        call_id = call.get("id", "")
                        try:
                            arguments = json.loads(fn.get("arguments") or "{}")
                        except json.JSONDecodeError:
                            arguments = {}
                        if not isinstance(arguments, dict):
                            arguments = {}

                        if name not in valid_tool_names:
                            tool_payload: Any = {
                                "error": f"unknown tool '{name}'. Valid tools: "
                                + ", ".join(sorted(valid_tool_names))
                            }
                        else:
                            try:
                                call_result = await session.call_tool(
                                    name,
                                    arguments=arguments,
                                    read_timeout_seconds=timedelta(seconds=args.tool_timeout),
                                )
                                tool_payload = _result_to_payload(call_result)
                            except Exception as exc:  # noqa: BLE001 - keep the run alive.
                                logger.warning("tool '%s' call failed: %s", name, exc)
                                tool_payload = {"error": f"tool '{name}' failed: {exc}"}

                            # Track the most recent state read for terminal detection,
                            # and record state-changing calls as the "chosen action".
                            if name == spec.state_tool:
                                latest_state_payload = tool_payload
                            else:
                                chosen_action = {"tool": name, "arguments": arguments}
                                action_result = (
                                    tool_payload
                                    if isinstance(tool_payload, dict)
                                    else {"result": tool_payload}
                                )

                        messages.append(
                            {
                                "role": "tool",
                                "tool_call_id": call_id,
                                "content": json.dumps(tool_payload, ensure_ascii=False),
                            }
                        )

                    # 3) Capture this step's game I/O.
                    capture.step(
                        state_summary=(
                            latest_state_payload
                            if isinstance(latest_state_payload, dict)
                            else {"raw": latest_state_payload}
                        )
                        if latest_state_payload is not None
                        else {},
                        available_actions=tool_names,
                        chosen_action=chosen_action,
                        action_result=action_result,
                    )

                    # 4) Terminal check. If the model didn't read state this step, poll
                    #    it ourselves so we never miss a run-over.
                    state_for_terminal = latest_state_payload
                    if state_for_terminal is None:
                        try:
                            state_for_terminal = await _call_state(
                                session, spec, timeout_s=args.tool_timeout
                            )
                        except McpServerError as exc:
                            logger.error("post-action state read failed: %s", exc)
                            outcome = "agent_abort"
                            break

                    # "started" gate: a run only truly begins once we see a real in-run state
                    # (not the main menu, not a LEFTOVER game_over from the PREVIOUS run). Until
                    # then a terminal screen is stale and must NOT end this run, and its floor
                    # must NOT be counted (else the prior run's death floor inflates final_floor).
                    _st = _unwrap_state(state_for_terminal)
                    # STS2MCP labels screens via `state_type`; CharTyr via `screen`. Check both.
                    _stype = (str(_st.get("state_type") or _st.get("screen") or "").strip().lower()
                              if isinstance(_st, dict) else "")
                    if (not started and isinstance(_st, dict)
                            and isinstance(_st.get("run"), dict)
                            and "game_over" not in _stype
                            and _stype not in ("menu", "main_menu", "character_select", "")):
                        started = True
                        final_floor, act_reached = 0, 0  # discard any pre-run leftover progress

                    if started:
                        final_floor, act_reached = _extract_progress(
                            state_for_terminal, final_floor, act_reached
                        )

                    if _is_dead_state(state_for_terminal):
                        dead_states += 1
                        if dead_states >= 5:
                            logger.error(
                                "game/mod unreachable: %d consecutive connection errors — is the "
                                "game still running with the mod? aborting run (not flailing).",
                                dead_states,
                            )
                            outcome = "agent_abort"
                            break
                    else:
                        dead_states = 0

                    terminal, term_outcome = detect_terminal(spec, state_for_terminal)
                    if terminal and started:
                        outcome = term_outcome or "defeat"
                        logger.info("run terminal: outcome=%s floor=%s", outcome, final_floor)
                        break
                    if terminal and not started:
                        logger.info(
                            "stale terminal screen before run start (leftover game_over?); "
                            "not ending — the agent must start a fresh run"
                        )

                    # 5) Stuck guard: identical tool+args repeated N times in a row.
                    if chosen_action is not None:
                        call_key = json.dumps(chosen_action, sort_keys=True)
                        if call_key == last_call_key:
                            repeat_count += 1
                        else:
                            repeat_count = 0
                            last_call_key = call_key
                        if repeat_count + 1 >= args.stuck_repeat:
                            stuck_aborts += 1
                            logger.error(
                                "stuck: identical action repeated %d times (%s); aborting cleanly",
                                repeat_count + 1,
                                call_key,
                            )
                            outcome = "agent_abort"
                            break

                    if args.action_delay > 0:
                        await asyncio.sleep(args.action_delay)
                else:
                    outcome = "max_steps"
                    logger.info("reached --max-steps (%d) without a terminal state", args.max_steps)

    except McpServerError as exc:
        logger.error("fatal MCP error: %s", exc)
        outcome = "agent_abort"
    except FileNotFoundError as exc:
        # `uv` (or the server command) not found on PATH.
        logger.error(
            "could not launch the MCP server command '%s': %s. Is `uv` installed and on "
            "PATH? (pip install uv / see the competitor README)",
            spec.command,
            exc,
        )
        outcome = "agent_abort"
    except KeyboardInterrupt:
        logger.warning("interrupted by user")
        outcome = "agent_abort"
    except Exception as exc:  # noqa: BLE001 - last-resort guard; never hang/crash dirty.
        logger.error("unexpected error driving %s: %s", spec.key, exc)
        outcome = "agent_abort"

    return _finish(capture, args, spec, started_at, outcome, final_floor, act_reached, steps, stuck_aborts, gemini)


def _finish(
    capture: GameCapture,
    args: argparse.Namespace,
    spec: CompetitorSpec,
    started_at: float,
    outcome: str,
    final_floor: int,
    act_reached: int,
    steps: int,
    stuck_aborts: int,
    gemini: GeminiClient,
) -> int:
    """Write run_summary.json (runs/history.jsonl-shaped), close the client, exit-code."""
    ended_at = datetime.now(timezone.utc).timestamp()
    summary = {
        "run_id": args.run_id,
        "competitor": spec.key,
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
    return 0 if outcome in ("victory", "defeat", "max_steps") else 1


# ---------------------------------------------------------------------------
# --dry-run: launch server + handshake + tools/list, print, exit. No game needed.
# ---------------------------------------------------------------------------


async def dry_run(args: argparse.Namespace, spec: CompetitorSpec) -> int:
    """Smoke-test the MCP wiring: launch the server, handshake, list tools, print.

    No active game is required (``tools/list`` does not need a run). Used to verify the
    competitor server starts and its tool surface is discoverable before committing to
    a real run. Failure to launch (missing uv/deps) is reported with an actionable msg.
    """
    competitor_root = Path(args.competitor_root).resolve()
    print(f"== dry-run: {spec.display_name} ==")
    print(f"competitor root : {competitor_root}")
    print(f"launch          : {_format_launch(spec, competitor_root)}")

    # Assemble the system prompt up front so doc-path problems surface even in dry-run.
    try:
        system_prompt = build_system_prompt(
            spec, competitor_root, character=args.character, ascension=args.ascension
        )
        print(f"system prompt   : assembled, {len(system_prompt):,} chars")
    except FileNotFoundError as exc:
        print(f"system prompt   : FAILED -- {exc}")
        return 1

    params = _server_params(spec, competitor_root)
    try:
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await asyncio.wait_for(session.initialize(), timeout=args.handshake_timeout)
                tools_result = await session.list_tools()
                names = [t.name for t in tools_result.tools]
                print(f"MCP handshake   : ok")
                print(f"discovered tools: {len(names)}")
                for name in names:
                    print(f"  - {name}")
                print(f"state tool      : {spec.state_tool}({spec.state_args}) -> {spec.notes}")
                print("== dry-run PASSED ==")
                return 0
    except FileNotFoundError as exc:
        print(
            f"== dry-run FAILED ==\nCould not launch '{spec.command}': {exc}.\n"
            "Is `uv` installed and on PATH? See the competitor README "
            "(pip install uv, or `brew install uv`)."
        )
        return 1
    except asyncio.TimeoutError:
        print(
            "== dry-run FAILED ==\nMCP handshake timed out. The server process likely "
            "failed to start (missing deps -- try the README's `uv run ... --help` once "
            "to install the pinned env)."
        )
        return 1
    except Exception as exc:  # noqa: BLE001 - dry-run is a smoke test; report cleanly.
        print(
            f"== dry-run FAILED ==\nServer launch / handshake error: {exc}.\n"
            "This usually means uv/deps are missing or the competitor repo is not at "
            f"--competitor-root ({competitor_root})."
        )
        return 1


# ---------------------------------------------------------------------------
# CLI.
# ---------------------------------------------------------------------------


def _default_run_id(competitor: str) -> str:
    return f"competitor-{competitor}-gemini-" + datetime.now().strftime("%Y%m%d-%H%M%S")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="mcp_gemini_host",
        description=(
            "Gemini-backed MCP host that drives the STS2MCP / CharTyr competitor agents "
            "as their authors intended (their MCP server + their skill docs), with "
            "Gemini 3.1 Pro. Captures LLM I/O (via the proxy) + MCP tool I/O for the "
            "competitor-comparison dataset. (Workstream C, C.2b.)"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument(
        "--competitor",
        required=True,
        choices=sorted(REGISTRY.keys()),
        help="Which competitor's MCP server + skill docs to drive.",
    )
    p.add_argument(
        "--competitor-root",
        default=str(DEFAULT_COMPETITOR_ROOT),
        help="Root holding the cloned competitor repos (STS2MCP/, CharTyr/).",
    )
    p.add_argument("--character", default="Silent", help="Target character (matches our headline).")
    p.add_argument("--ascension", type=int, default=0, help="Target ascension (A0 floor).")
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
        help="Trim oldest whole cycles only if the transcript exceeds this (else accumulate).",
    )
    p.add_argument(
        "--experiment-tag",
        default=None,
        help="experiment_tag for run_summary.json (default: per-competitor "
        "competitor-<key>-gemini-A0). Matches runs/history.jsonl; scripts/reproduce/* "
        "filter on it.",
    )
    p.add_argument(
        "--skill-docs",
        nargs="+",
        default=None,
        help="Override the skill-doc list (paths relative to --competitor-root, or absolute).",
    )
    p.add_argument(
        "--stuck-repeat",
        type=int,
        default=8,
        help="Abort after this many identical tool calls in a row (stuck guard).",
    )
    p.add_argument("--action-delay", type=float, default=0.6, help="Delay (s) between actions.")
    p.add_argument(
        "--our-mod-url",
        default="http://127.0.0.1:8128/health",
        help="Health URL of OUR mod. The run aborts if this responds (our mod still "
        "loaded), enforcing complete replacement so the competitor never sees our mod.",
    )
    p.add_argument(
        "--allow-our-mod",
        action="store_true",
        help="Disable the complete-replacement guard (NOT recommended; only if you are "
        "intentionally not isolating our mod).",
    )
    p.add_argument(
        "--tool-timeout",
        type=float,
        default=60.0,
        help="Per MCP tools/call timeout (s).",
    )
    p.add_argument(
        "--handshake-timeout",
        type=float,
        default=60.0,
        help="Timeout (s) for the MCP initialize handshake.",
    )
    p.add_argument(
        "--dry-run",
        action="store_true",
        help="Launch the server, handshake + tools/list, print tools + prompt length, exit. No game needed.",
    )
    return p


def _resolve_spec(args: argparse.Namespace) -> CompetitorSpec:
    spec = REGISTRY[args.competitor]
    # Apply CLI overrides onto a shallow copy so the registry stays pristine.
    if args.skill_docs is not None:
        spec = CompetitorSpec(
            key=spec.key,
            display_name=spec.display_name,
            command=spec.command,
            args_factory=spec._args_factory,
            cwd_factory=spec._cwd_factory,
            skill_docs=list(args.skill_docs),
            state_tool=spec.state_tool,
            state_args=spec.state_args,
            default_experiment_tag=spec.default_experiment_tag,
            notes=spec.notes,
        )
    return spec


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.run_id is None:
        args.run_id = _default_run_id(args.competitor)
    if args.experiment_tag is None:
        args.experiment_tag = REGISTRY[args.competitor].default_experiment_tag
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        stream=sys.stderr,
    )

    spec = _resolve_spec(args)
    coro = dry_run(args, spec) if args.dry_run else run_session(args, spec)
    try:
        return asyncio.run(coro)
    except KeyboardInterrupt:
        logger.warning("interrupted")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
