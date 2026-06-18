"""Run the autonomous agent for one or more game runs.

Usage:
    python -m scripts.run_agent [--steps N] [--runs N] [--character NAME]
                                [--ascension N|auto|auto-N|reset-N]
                                [--model-family gemini|gpt|qwen|claude]
                                [--no-postrun] [--no-evolution]
                                [--no-llm] [--no-memory] [--no-skills]
                                [--experiment-tag TAG]

Supports infinite looping (--runs 0) with automatic restart via MCP API
between completed runs. Abnormal agent aborts stop the session.
Requires STS2 running with the STS2-Agent mod.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from pathlib import Path

from rich.logging import RichHandler

# Add project root to path
sys.path.insert(0, ".")


_LAUNCH_GAME_REQUESTED: bool = False
_LAUNCH_GAME_PORT: int = 0
_LAUNCH_ONLY: bool = False


def _apply_pre_config_flags() -> None:
    """Promote --model-family / --no-postrun / --no-evolution / --api-port / --launch-game
    to env vars BEFORE config loads.

    config.py resolves module-level constants (MODEL_FAMILY, LLM_FAST_MODEL,
    POSTRUN_ENABLED, EVOLUTION_ENABLED, MCP_BASE_URL, ...) at import time
    from ``os.environ``. To let CLI flags control those, we must set env vars
    before the ``import config`` statement that follows.
    """
    global _LAUNCH_GAME_REQUESTED, _LAUNCH_GAME_PORT, _LAUNCH_ONLY
    pre = argparse.ArgumentParser(add_help=False)
    pre.add_argument("--model-family", type=str, default=None)
    pre.add_argument("--no-postrun", action="store_true", default=False)
    pre.add_argument("--no-evolution", action="store_true", default=False)
    pre.add_argument("--launch-game", action="store_true", default=False)
    pre.add_argument("--launch-only", action="store_true", default=False)
    pre.add_argument("--api-port", type=str, default="auto")
    pre.add_argument("--monitor-port", type=str, default="auto")
    pre.add_argument(
        "--display-language", type=str, default=None, choices=["en", "zh"]
    )
    args, _ = pre.parse_known_args()
    # --launch-only implies --launch-game (there's nothing to "only" otherwise).
    if args.launch_only:
        args.launch_game = True
        _LAUNCH_ONLY = True
    if args.model_family:
        os.environ["STS2_MODEL_FAMILY"] = args.model_family.strip().lower()
        # Explicit --model-family declares intent; any stale direct model
        # pins OR global effort tunings in .env would otherwise beat the
        # family registry silently. Reserve the slots with empty strings so
        # config.py's .env loader skips them (see _PRESERVE_IF_SET).
        # Per-family effort overrides (e.g. STS2_QWEN_EFFORT_STRATEGIC) are
        # preserved — they target a specific family deliberately.
        for _var in ("STS2_FAST_MODEL", "STS2_STRATEGIC_MODEL",
                     "STS2_ANALYSIS_MODEL", "STS2_EVOLUTION_MODEL",
                     "STS2_THINK_EFFORT_FAST", "STS2_THINK_EFFORT_STRATEGIC",
                     "STS2_THINK_EFFORT_ANALYSIS"):
            os.environ[_var] = ""
    if args.no_postrun:
        os.environ["STS2_POSTRUN_ENABLED"] = "false"
    if args.no_evolution:
        os.environ["STS2_EVOLUTION_ENABLED"] = "false"
    if args.display_language:
        os.environ["STS2_DISPLAY_LANGUAGE"] = args.display_language

    # --api-port / --launch-game: resolve port before config reads STS2_MCP_URL.
    # --api-port alone just retargets the client; --launch-game also spawns
    # the game later with STS2_API_PORT matching.
    if args.launch_game or args.api_port != "auto":
        if args.api_port == "auto":
            from src.launcher.game_launcher import pick_free_port
            port = pick_free_port()
        else:
            try:
                port = int(args.api_port)
                if not 0 < port <= 65535:
                    raise ValueError
            except ValueError:
                raise SystemExit(
                    f"--api-port must be 'auto' or 1-65535, got: {args.api_port!r}"
                )
        os.environ["STS2_MCP_URL"] = f"http://127.0.0.1:{port}"
        _LAUNCH_GAME_PORT = port
        _LAUNCH_GAME_REQUESTED = args.launch_game

    # --monitor-port: explicit integer, 'auto' (pick free when launching game,
    # else keep config default for backwards-compat).
    if args.monitor_port != "auto":
        try:
            m_port = int(args.monitor_port)
            if not 0 < m_port <= 65535:
                raise ValueError
        except ValueError:
            raise SystemExit(
                f"--monitor-port must be 'auto' or 1-65535, got: {args.monitor_port!r}"
            )
        os.environ["STS2_MONITOR_PORT"] = str(m_port)
    elif args.launch_game:
        # Multi-instance mode: give each agent its own monitor port so they
        # don't collide. Prefer the 8081-8099 range the frontend auto-scans
        # so the user doesn't have to add tabs manually.
        from src.launcher.game_launcher import pick_free_port, pick_free_port_in_range
        preferred = pick_free_port_in_range(8081, 8099)
        os.environ["STS2_MONITOR_PORT"] = str(preferred if preferred else pick_free_port())


_apply_pre_config_flags()

import config
from src.agent.loop import AgentLoop
from src.mcp_client.client import McpClient
from src.runs.history import RunRecord, RunHistoryStore
from src.runs.ascension_stats import AscensionStats
from src.storage import paths
from scripts import data_sync

# Populated by main() when --launch-game is active. Cleanup is delegated to
# ``src.launcher.game_launcher.terminate_launched_game`` (called from the
# end-of-__main__ cleanup, the post-gameplay early kill in main(), and the
# postrun watchdog in ``src/agent/loop.py``). os._exit bypasses atexit, so
# every exit path must call the terminator explicitly.
_game_proc = None

# Module-level logger for helpers called before main() configures
# RichHandler. Inside main() the local `logger = logging.getLogger("run_agent")`
# rebinds to the same underlying logger object, so log records flow through
# whichever handlers are active at call time.
_module_logger = logging.getLogger("run_agent")


def _load_ascension_stats_for_session(
    history_store: "RunHistoryStore",
    experiment_tag: str,
) -> AscensionStats:
    """Return the AscensionStats object this session should use for
    auto-progression.

    Personal play (experiment_tag empty) loads the global cache at
    runs/ascension_stats.json.

    Experiment runs (experiment_tag non-empty) instead derive a fresh
    AscensionStats from runs/history.jsonl filtered by this tag. The
    returned object is in-memory only; the post-run write at
    `record_run` + `save` is gated separately on the same flag so the
    global cache is never written by experiment runs.

    Three properties of this design:

    1. Isolation from personal play. Prior wins under the default
       (full-mode) profile_hash never bleed into an experiment's
       starting ascension, even if the experiment uses --ascension auto.
    2. Multi-agent parallel safety. The global cache (no merge driver
       in data_sync — dict_counter_merge is TODO) is never read or
       written by experiments, so concurrent agents cannot race on it.
    3. Resume correctness. A second session with the same experiment
       tag picks up where the first session left off, because the
       in-memory stats are rebuilt from the history records the first
       session already wrote (history.jsonl uses append_dedup merge
       driver and is parallel-safe).
    """
    if experiment_tag:
        matching = history_store.query(experiment_tag=experiment_tag)
        stats = AscensionStats.rebuild_from_history(matching)
        _module_logger.info(
            "Experiment run (tag=%s) — session-local ascension_stats rebuilt "
            "from %d matching history records (no disk I/O on the global cache)",
            experiment_tag, len(matching),
        )
        return stats
    return AscensionStats.load(paths.ascension_stats_file())


def setup_logging(level: str = "INFO") -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(rich_tracebacks=True, markup=True)],
    )
    # Suppress noisy httpx logs
    logging.getLogger("httpx").setLevel(logging.WARNING)


def _log_model_routing(logger: logging.Logger) -> None:
    """Emit a one-screen summary of which models will be used for each tier."""
    logger.info(
        "Model family: fast=%s strategic=%s analysis=%s",
        config._FAST_FAMILY, config._STRATEGIC_FAMILY,
        config._ANALYSIS_FAMILY if config.LLM_ANALYSIS_MODEL else "—",
    )
    logger.info(
        "Models: fast=%s (%s) strategic=%s (%s)",
        config.LLM_FAST_MODEL or "—", config.LLM_THINK_EFFORT_FAST,
        config.LLM_STRATEGIC_MODEL or "—", config.LLM_THINK_EFFORT_STRATEGIC,
    )
    if config.LLM_ANALYSIS_MODEL:
        logger.info(
            "Models: analysis=%s (%s) evolution=%s",
            config.LLM_ANALYSIS_MODEL, config.LLM_THINK_EFFORT_ANALYSIS,
            config.EVOLUTION_MODEL or "—",
        )
    postrun_on = config.postrun_effectively_enabled()
    postrun_reason = config.postrun_disabled_reason()
    logger.info(
        "Postrun: %s%s",
        "enabled" if postrun_on else "disabled",
        f" ({postrun_reason})" if not postrun_on and postrun_reason else "",
    )
    if config.MODEL_FAMILY_FALLBACK:
        logger.info("Family fallback order: %s", ", ".join(config.MODEL_FAMILY_FALLBACK))


def _map_outcome(completion_reason: str, end_reason: str, victory: bool) -> str:
    """Map agent loop reasons to a clean outcome label."""
    if victory:
        return "victory"
    if completion_reason == "completed":
        return "defeat"
    if end_reason == "max_steps":
        return "max_steps"
    if end_reason == "interrupt":
        return "interrupt"
    return "agent_abort"


def _log_run_summary(logger: logging.Logger, run_state, run_number: int) -> None:
    logger.info("=" * 50)
    logger.info(
        "Run #%d complete (subprocess-local; see history.jsonl for experiment total): %s",
        run_number, run_state.run_id,
    )
    logger.info("Character: %s", run_state.character)
    logger.info("Ascension: A%d", run_state.ascension)
    logger.info("Victory: %s", run_state.victory)
    logger.info("Final floor: %d", run_state.final_floor)
    logger.info("Final HP: %d/%d", run_state.final_hp, run_state.final_max_hp)
    logger.info("Total actions: %d", run_state.total_actions)
    logger.info("LLM calls: %d", run_state.llm_calls)
    logger.info("Fitness: %.1f", run_state.fitness())
    logger.info("Duration: %.0fs", run_state.duration_seconds)
    logger.info("=" * 50)


async def _ensure_run_started(
    client: McpClient,
    character: str | None,
    logger: logging.Logger,
    abandon_existing: bool = False,
    ascension: int | None = None,
) -> bool:
    """Make sure we're in a live run. If at menu/game_over/timeline, start a new run.

    Uses state-driven MCP actions (return_to_main_menu, open_character_select,
    select_character, embark) to navigate menu screens automatically.

    If abandon_existing=True, any saved run is abandoned rather than re-entered.
    """
    raw = await client.get_state()
    state_type = raw.get("state_type", "unknown")
    logger.info("Current state: %s", state_type)

    if state_type in client.IN_RUN_STATES and not abandon_existing:
        run_data = raw.get("run") or {}
        run_floor = run_data.get("floor", 0)
        # Safety net: any mid-run state (floor > 1) is never what a fresh
        # agent subprocess wants to inherit. It usually means a prior
        # subprocess was killed mid-run and left state behind. Abandoning
        # here prevents silent data contamination in ablation experiments.
        if run_floor > 1:
            logger.warning(
                "In-progress run at F%d — abandoning to start fresh (floor>1 safety)",
                run_floor,
            )
            abandon_existing = True
        else:
            # Character check: STS2 auto-loads saves on launch, so an F1
            # in-progress run might be a *different* character than the
            # user asked for on the CLI. Without this check the agent
            # silently plays whatever character the save has.
            if character:
                from src.memory.models_v2 import normalize_character
                requested = normalize_character(character)
                existing_raw = (
                    run_data.get("character_id")
                    or run_data.get("character_name")
                    or ""
                )
                existing = normalize_character(existing_raw) if existing_raw else ""
                if existing and existing != requested:
                    logger.warning(
                        "In-progress run is %r but --character is %r — abandoning to start fresh",
                        existing_raw, character,
                    )
                    abandon_existing = True
            if not abandon_existing:
                if ascension is not None:
                    run_asc = run_data.get("ascension", 0)
                    if run_asc != ascension:
                        logger.warning(
                            "In-progress run is A%d but target is A%d — abandoning to start fresh",
                            run_asc, ascension,
                        )
                        abandon_existing = True
                    else:
                        return True  # Fresh F1 run at matching ascension + character
                else:
                    return True  # No ascension constraint, character matched

    logger.info("Not in a run (state=%s), starting new run via MCP...", state_type)
    return await client.start_new_run(
        character=character, ascension=ascension, abandon_existing=abandon_existing,
    )


async def main(
    max_steps: int = 2000,
    max_runs: int = 0,
    character: str | None = None,
    use_llm: bool = True,
    ascension_mode: str | None = None,
    experiment_tag: str = "",
    abandon_existing: bool = False,
) -> None:
    setup_logging()
    logger = logging.getLogger("run_agent")

    # -- DLL mechanics cache (background, non-blocking) --
    # Extracts enchantment descriptions from the game DLL into
    # data/knowledge/upstream/mechanics_dll.json, used by _keyword_fmt.py as
    # a fallback for mechanics not in KW_GLOSSARY. Runs only when the DLL is
    # newer than the cache. Skipped silently if the game DLL is not found.
    try:
        import threading

        from scripts.extract_mechanics_from_dll import run as _extract_mechanics
        from scripts.extract_pck_localization import run as _extract_localization
        from scripts.generate_cards_from_dll import run as _extract_cards
        from scripts.generate_items_from_dll import run as _extract_items

        def _extract_local_knowledge() -> None:
            _extract_localization(force=False)
            _extract_cards(force=False)
            _extract_items(force=False)

        threading.Thread(
            target=_extract_mechanics,
            kwargs={"force": False},
            daemon=True,
            name="dll-mechanics-extractor",
        ).start()
        threading.Thread(
            target=_extract_local_knowledge,
            daemon=True,
            name="local-knowledge-extractor",
        ).start()
    except Exception as _e:
        logger.debug("DLL knowledge extraction skipped: %s", _e)

    mode = "LLM" if use_llm else "Random"
    skills_str = "on" if config.SKILLS_ENABLED else "off"
    memory_str = "on" if config.MEMORY_ENABLED else "off"
    runs_str = str(max_runs) if max_runs > 0 else "infinite"
    logger.info(
        "Starting agent: mode=%s, skills=%s, memory=%s, runs=%s",
        mode, skills_str, memory_str, runs_str,
    )
    _log_model_routing(logger)

    # -- Monitor server (started early so --launch-only can also verify the
    # dashboard URL end-to-end, and so the port log is visible before the
    # game takes over the terminal). --
    monitor_event_bus = None
    _monitor_status: dict | None = None
    if config.MONITOR_ENABLED:
        try:
            from src.monitor.event_bus import event_bus as _event_bus
            from src.monitor.server import start_monitor_server
            from urllib.parse import urlparse
            _event_bus.enable()
            monitor_thread = start_monitor_server(_event_bus, port=config.MONITOR_PORT)
            if monitor_thread:
                monitor_event_bus = _event_bus
                # Sync back the port the server actually bound — it may
                # differ from the requested one if two launches raced on
                # the same free port (server falls back to the next one).
                actual_port = getattr(monitor_thread, "_monitor_port", config.MONITOR_PORT)
                config.MONITOR_PORT = actual_port
                logger.info(
                    "Monitor dashboard: http://localhost:%d (WebSocket: ws://localhost:%d/ws/events)",
                    actual_port, actual_port,
                )
                # Expose instance metadata via /api/status so the frontend's
                # tab strip can show mon/game port + PID. game_pid is filled
                # in below once --launch-game spawns the process.
                _monitor_status = monitor_thread._monitor_app._monitor_status  # type: ignore[attr-defined]
                _monitor_status["monitor_port"] = actual_port
                _monitor_status["game_port"] = urlparse(config.MCP_BASE_URL).port
                _monitor_status["game_pid"] = None
        except Exception as exc:
            logger.warning("Monitor failed to start: %s", exc)

    # -- Launch game subprocess if --launch-game was passed --
    global _game_proc
    if _LAUNCH_GAME_REQUESTED:
        from src.launcher.game_launcher import (
            resolve_game_path, launch_game, wait_for_ready,
        )
        try:
            exe = resolve_game_path()
        except FileNotFoundError as exc:
            logger.error("Game launch failed: %s", exc)
            return
        logger.info("Launching game: %s (STS2_API_PORT=%d)", exe, _LAUNCH_GAME_PORT)
        _game_proc = launch_game(exe, _LAUNCH_GAME_PORT)
        if _monitor_status is not None:
            _monitor_status["game_pid"] = _game_proc.pid
        logger.info("Waiting for mod HTTP server at %s ...", config.MCP_BASE_URL)
        ready = await wait_for_ready(config.MCP_BASE_URL, timeout=120.0, proc=_game_proc)
        if not ready:
            logger.error(
                "Mod did not become ready within 120s at %s (game pid=%s, exit=%s). "
                "Check that the mod is installed and STS2_API_PORT is honored.",
                config.MCP_BASE_URL, _game_proc.pid, _game_proc.poll(),
            )
            return
        logger.info("Mod ready at %s (game pid=%d)", config.MCP_BASE_URL, _game_proc.pid)

        # Emit a one-line init event so the frontend timeline has something to
        # show in --launch-only / pre-gameplay states instead of the empty
        # placeholder. Intentionally no run_id — this is meta/lifecycle info.
        if monitor_event_bus is not None:
            try:
                monitor_event_bus.emit("monitor_init", {
                    "message": f"Agent initialized — game launched (pid {_game_proc.pid}) on port {_LAUNCH_GAME_PORT}",
                    "monitor_port": config.MONITOR_PORT,
                    "game_port": _LAUNCH_GAME_PORT,
                    "game_pid": _game_proc.pid,
                    "launch_mode": "launch-only" if _LAUNCH_ONLY else "launch-game",
                })
            except Exception:
                pass

        if _LAUNCH_ONLY:
            logger.info(
                "--launch-only: game=%s monitor=http://localhost:%d. Press Ctrl+C to terminate.",
                config.MCP_BASE_URL, config.MONITOR_PORT,
            )
            try:
                # Block until SIGINT; also exit early if the game dies on its own.
                while _game_proc.poll() is None:
                    await asyncio.sleep(1.0)
                logger.warning("Game process exited on its own (rc=%s).", _game_proc.poll())
            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.info("Ctrl+C received — shutting down.")
            return

    # Non-launch-game path: same init event, just no game_pid since we didn't
    # spawn the process ourselves.
    if monitor_event_bus is not None and not _LAUNCH_GAME_REQUESTED:
        try:
            from urllib.parse import urlparse as _urlparse
            _game_port = _urlparse(config.MCP_BASE_URL).port
            monitor_event_bus.emit("monitor_init", {
                "message": f"Agent initialized — connecting to game at {config.MCP_BASE_URL}",
                "monitor_port": config.MONITOR_PORT,
                "game_port": _game_port,
                "game_pid": None,
                "launch_mode": "connect-only",
            })
        except Exception:
            pass

    # -- Sync sibling data repo before loading any store (pull-at-start) --
    _data_sync_startup = data_sync.pull()
    if _data_sync_startup.get("status") not in (None, "disabled"):
        logger.info("data_sync pull: %s", _data_sync_startup)
    _data_repo_sha = _data_sync_startup.get("data_repo_sha", "") or ""
    _machine_id = paths.machine_id()

    # -- Run analytics --
    history_store = RunHistoryStore.load(paths.runs_history_file())
    ascension_stats = _load_ascension_stats_for_session(history_store, experiment_tag)
    model_profile = config.build_model_profile()
    profile_hash = config.model_profile_hash(model_profile)
    profile_label = config.model_profile_label(model_profile)
    logger.info("Model profile: %s [%s]", profile_label, profile_hash)
    logger.info("Run history: %d records loaded", history_store.count)

    # -- Ascension target resolution --
    ascension_target: int | None = None
    ascension_auto = False
    ascension_auto_min = 0
    ascension_reset_target: int | None = None  # consumed on first run, then auto takes over
    if ascension_mode is not None:
        mode_str = ascension_mode.strip().lower().replace(" ", "")
        if mode_str == "auto":
            ascension_auto = True
            logger.info("Ascension mode: auto (per-model progression)")
        elif mode_str.startswith("auto-") or mode_str.startswith("auto+"):
            try:
                ascension_auto_min = int(mode_str[5:])
                if ascension_auto_min < 0 or ascension_auto_min > 20:
                    raise ValueError("out of range 0-20")
                ascension_auto = True
                logger.info(
                    "Ascension mode: auto (per-model progression, floor A%d)",
                    ascension_auto_min,
                )
            except ValueError as exc:
                logger.error(
                    "Invalid --ascension value: %s (expected auto-N with 0<=N<=20): %s",
                    ascension_mode, exc,
                )
                return
        elif mode_str.startswith("reset-"):
            try:
                ascension_reset_target = int(mode_str[6:])
                if ascension_reset_target < 0 or ascension_reset_target > 20:
                    raise ValueError("out of range 0-20")
                ascension_auto = True
                logger.info(
                    "Ascension mode: reset — first run forced to A%d (ignoring stats), "
                    "subsequent runs auto-progress",
                    ascension_reset_target,
                )
            except ValueError as exc:
                logger.error(
                    "Invalid --ascension value: %s (expected reset-N with 0<=N<=20): %s",
                    ascension_mode, exc,
                )
                return
        else:
            try:
                ascension_target = int(mode_str)
                logger.info("Ascension mode: fixed A%d", ascension_target)
            except ValueError:
                logger.error(
                    "Invalid --ascension value: %s (use integer, 'auto', 'auto-N', or 'reset-N')",
                    ascension_mode,
                )
                return

    # Initialize memory system once (shared across all runs)
    memory = None
    if config.MEMORY_ENABLED:
        try:
            from src.memory.memory_manager import MemoryManager
            memory = MemoryManager()
            logger.info("Memory system active: %s", memory.stats())
        except Exception as exc:
            logger.warning("Memory system failed to initialize: %s", exc)

    # Aggregate stats across runs
    total_victories = 0
    total_defeats = 0
    total_fitness = 0.0

    async with McpClient(event_bus=monitor_event_bus) as client:
        logger.info("Connected to STS2-Agent")

        agent = AgentLoop(
            client,
            max_steps=max_steps,
            use_llm=use_llm,
            memory_manager=memory,
            experiment_tag=experiment_tag,
        )
        if monitor_event_bus:
            agent.set_event_bus(monitor_event_bus)

        run_number = 0
        while True:
            run_number += 1
            if max_runs > 0 and run_number > max_runs:
                break

            # Resolve auto-ascension for this run
            effective_ascension = ascension_target
            if ascension_reset_target is not None:
                # First run overrides stats with explicit reset target
                effective_ascension = ascension_reset_target
                from src.memory.models_v2 import normalize_character
                norm_char = normalize_character(character or "Silent")
                logger.info(
                    "Reset-ascension for %s: forcing A%d (ignoring stats this run)",
                    norm_char, effective_ascension,
                )
                ascension_reset_target = None  # consumed; subsequent runs use auto
            elif ascension_auto:
                from src.memory.models_v2 import normalize_character
                norm_char = normalize_character(character or "Silent")
                effective_ascension = max(
                    ascension_auto_min,
                    ascension_stats.next_ascension(
                        profile_hash, norm_char, max_asc=20,
                    ),
                )
                logger.info("Auto-ascension for %s: targeting A%d", norm_char, effective_ascension)

            logger.info("=" * 50)
            logger.info(
                "Starting run #%d / %s%s",
                run_number, runs_str,
                f" (A{effective_ascension})" if effective_ascension is not None else "",
            )
            logger.info("=" * 50)

            # Ensure we're in a live run (auto-start if needed).
            # Default: honor --abandon-existing only on the FIRST run of this
            # session, so a stuck-but-recoverable state from run N can be
            # re-entered cleanly by run N+1. In experiment mode the priority
            # flips: every run must start from a clean slate to keep the
            # condition reproducible (a half-finished prior run's deck/HP
            # would otherwise contaminate the next run).
            if experiment_tag:
                _abandon = abandon_existing
            else:
                _abandon = abandon_existing and run_number == 1
            if not await _ensure_run_started(
                client, character, logger, ascension=effective_ascension,
                abandon_existing=_abandon,
            ):
                logger.error("Failed to start new run. Stopping.")
                break

            # Reset agent state and play
            agent.reset_for_new_run()
            interrupted = False
            try:
                run_state = await agent.run()
            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.warning("Run interrupted — recording then running postrun")
                interrupted = True
                # agent.run()'s finally has already finalized run_state with
                # reason="interrupt"; pull it directly so we still record the
                # gameplay outcome before postrun touches anything.
                run_state = agent._run_state
                if run_state is None:
                    logger.error("Run interrupted before run_state was initialized; skipping record")
                    break

            # Record target_ascension if not yet set from game state.
            # In auto mode: use actual_ascension (game-authoritative) so history
            # accurately reflects which ascension was played, not just what the
            # stat-based formula predicted.
            # In fixed mode: use effective_ascension (the user's explicit request).
            if run_state.target_ascension is None:
                if ascension_auto and run_state.actual_ascension is not None:
                    run_state.target_ascension = run_state.actual_ascension
                elif effective_ascension is not None:
                    run_state.target_ascension = effective_ascension

            # Summary
            _log_run_summary(logger, run_state, run_number)

            # -- Record to run history --
            outcome = _map_outcome(
                agent._run_completion_reason or "",
                agent._run_end_reason or "",
                run_state.victory,
            )
            from src.memory.models_v2 import normalize_character as _norm_char
            record = RunRecord(
                run_id=run_state.run_id,
                started_at=run_state.start_time,
                ended_at=run_state.end_time or time.time(),
                profile_hash=profile_hash,
                profile_label=profile_label,
                model_profile=model_profile,
                character=_norm_char(run_state.character or character or ""),
                target_ascension=run_state.target_ascension,
                actual_ascension=run_state.actual_ascension,
                outcome=outcome,
                victory=run_state.victory,
                final_floor=run_state.final_floor,
                final_hp=run_state.final_hp,
                final_max_hp=run_state.final_max_hp,
                final_gold=run_state.final_gold,
                fitness=run_state.fitness(),
                score=run_state.final_score,
                duration_seconds=run_state.duration_seconds,
                steps=run_state.total_actions,
                llm_calls=run_state.llm_calls,
                total_actions=run_state.total_actions,
                combats_won=run_state.combats_won,
                combats_total=run_state.combats_total,
                completion_reason=agent._run_completion_reason or "",
                end_reason=agent._run_end_reason or "",
                use_llm=use_llm,
                memory_enabled=config.MEMORY_ENABLED,
                skills_enabled=config.SKILLS_ENABLED,
                experiment_tag=experiment_tag,
                data_repo_sha=_data_repo_sha,
                machine_id=_machine_id,
            )
            history_store.append(record)
            # In-memory update happens for both modes so the session summary
            # (line ~821) and same-subprocess --runs N>1 auto-progression see
            # the just-finished run. The conditional below only gates the
            # *disk write* to the global cache.
            asc_rec = ascension_stats.record_run(record)
            if experiment_tag:
                # Experiment runs do NOT persist to the global ascension_stats
                # cache. Reasons: (1) the cache is keyed by model_profile
                # hash, so an ablation condition with a unique flag set
                # would still pollute the personal stats namespace under
                # its own hash; (2) the cache has no merge driver in
                # data_sync (dict_counter_merge is TODO), so concurrent
                # parallel-agent writes would race and silently fall to
                # an orphan branch. Per-condition / per-ascension stats
                # for experiments are derived post-hoc from
                # runs/history.jsonl filtered by experiment_tag +
                # actual_ascension. Session-local in-memory stats above
                # are sufficient for the summary log + within-session
                # auto-progression because experiment subprocesses always
                # rebuild from filtered history at startup.
                logger.info(
                    "Experiment run (tag=%s) — skipping ascension_stats disk write",
                    experiment_tag,
                )
                # Re-read history.jsonl from disk so the cumulative count
                # picks up runs from sibling subprocesses (parallel-agent
                # mode) as well as this one. In-memory store would only
                # see this subprocess's contributions plus startup snapshot.
                exp_total = exp_wins = 0
                profile_total = profile_wins = 0
                try:
                    fresh_store = RunHistoryStore.load(paths.runs_history_file())
                    for r in fresh_store.query(experiment_tag=experiment_tag):
                        if r.outcome in {"agent_abort", "mcp_error", "interrupt"}:
                            continue
                        exp_total += 1
                        if r.victory:
                            exp_wins += 1
                        if r.profile_hash == profile_hash:
                            profile_total += 1
                            if r.victory:
                                profile_wins += 1
                except Exception as exc:  # noqa: BLE001
                    logger.debug("Cumulative experiment count failed: %s", exc)
                else:
                    logger.info(
                        "Experiment cumulative — tag=%s: %d runs (%dW); "
                        "this profile [%s]: %d runs (%dW)",
                        experiment_tag, exp_total, exp_wins,
                        profile_hash, profile_total, profile_wins,
                    )
            else:
                ascension_stats.save(paths.ascension_stats_file())
                logger.info(
                    "Recorded: %s A%d — %d/%d wins (best floor %d)",
                    asc_rec.character or "?", asc_rec.ascension,
                    asc_rec.wins, asc_rec.total_runs, asc_rec.best_floor,
                )

            # -- Sync this run's deltas to sibling repo (push-at-end) --
            # First push: gameplay-end. Commits whatever's currently dirty
            # (history.jsonl + any in-run skill_usage / state_snapshot writes).
            # Done BEFORE postrun so a postrun crash cannot lose the gameplay
            # outcome that was just persisted to history.jsonl.
            _push_meta = data_sync.PushMetadata(
                run_id=record.run_id,
                machine_id=paths.machine_id(),
                outcome=record.outcome or "unknown",
                floor=record.final_floor,
                ascension=record.actual_ascension,
                duration_seconds=record.duration_seconds,
                code_sha=data_sync._current_code_sha(),
                mod_version=os.getenv("STS2_MOD_VERSION", "unknown"),
                game_version=os.getenv("STS2_GAME_VERSION", "unknown"),
            )
            try:
                _push_res = data_sync.push_run(_push_meta, kind="run")
                if _push_res.get("status") not in (None, "disabled", "nochange"):
                    logger.info("data_sync push (run): %s", _push_res)
            except Exception as _sync_exc:
                logger.warning("data_sync push (run) failed (non-fatal): %s", _sync_exc)

            # -- Early game-subprocess kill --
            # Postrun (memory / skills / stub_fill / evolution) takes 20-40
            # min in self-evolve mode and never queries the game — only LLM
            # calls + JSONL log files. If we're not going to launch another
            # gameplay round (this is the last run, or it was interrupted),
            # kill the game NOW instead of after postrun. Without this, the
            # game window stays open for the entire postrun window, which
            # the user reasonably reads as "the run finished but the game
            # didn't close." Also frees RAM/GPU during the LLM-heavy
            # postrun stages, and means a postrun watchdog ``os._exit``
            # (60 min hard wall in ``_safe_post_run``) cannot orphan the
            # game on Windows. The end-of-__main__ cleanup is idempotent
            # so this kill plus that cleanup don't conflict.
            #
            # NB: ``--runs N`` (N>1) keeps the game alive across runs
            # because the MCP client reuses the same game session via
            # ``start_new_run`` on the next iteration.
            _will_launch_next_run = (
                not interrupted
                and not agent._last_run_aborted
                and (max_runs <= 0 or run_number < max_runs)
            )
            if not _will_launch_next_run:
                from src.launcher.game_launcher import terminate_launched_game
                terminate_launched_game()

            # -- Postrun (memory / skills / evolution) --
            # Run AFTER recording so any postrun failure (LLM hang, watchdog
            # os._exit, exception) cannot lose the gameplay outcome we just
            # persisted to history.jsonl + ascension_stats.
            try:
                await agent.finalize_session()
            except (KeyboardInterrupt, asyncio.CancelledError):
                logger.warning("Postrun interrupted by user")
                interrupted = True
            except Exception:
                logger.error("Postrun failed (record already saved)", exc_info=True)

            # Second push: postrun-end. Commits the L4/L5 deltas finalize_session
            # produced (memory/v2/*, skills/skills.json, evolution/*). Without
            # this, those writes stay dirty in the working tree, get quarantined
            # to an orphan branch by the next run's pull(), and never reach
            # main — every subsequent run starts with empty memory/skills,
            # silently breaking self-evolve. Non-fatal: a watchdog os._exit
            # that pre-empts this still leaves the data in the working tree
            # and the next pull() captures it on an orphan branch, matching
            # the prior (broken) behavior only for that specific failure mode.
            try:
                _postrun_push_res = data_sync.push_run(_push_meta, kind="postrun")
                if _postrun_push_res.get("status") not in (None, "disabled", "nochange"):
                    logger.info("data_sync push (postrun): %s", _postrun_push_res)
            except Exception as _sync_exc:
                logger.warning("data_sync push (postrun) failed (non-fatal): %s", _sync_exc)

            if interrupted:
                logger.warning("Run #%d ended via interrupt; stopping session", run_number)
                break

            if agent._last_run_aborted:
                logger.error(
                    "Run #%d aborted abnormally; stopping session without auto-restart.",
                    run_number,
                )
                break

            if run_state.victory:
                total_victories += 1
            else:
                total_defeats += 1
            total_fitness += run_state.fitness()

            # Check if we should continue
            if max_runs > 0 and run_number >= max_runs:
                break

            # Auto-restart: navigate from game_over → new run.
            logger.info("Initiating next run via MCP...")
            # Resolve ascension for next run (may differ in auto mode)
            next_asc = effective_ascension
            if ascension_auto and run_state.character:
                from src.memory.models_v2 import normalize_character
                norm_char = normalize_character(run_state.character)
                next_asc = max(
                    ascension_auto_min,
                    ascension_stats.next_ascension(profile_hash, norm_char, max_asc=20),
                )
            success = await client.start_new_run(character=character, ascension=next_asc)

            if not success:
                logger.error("Failed to start new run after run #%d. Stopping.", run_number)
                break

            # Brief pause before next run
            await asyncio.sleep(2.0)

    # Final aggregate summary
    total_runs = total_victories + total_defeats
    if total_runs > 0:
        logger.info("=" * 50)
        logger.info("SESSION COMPLETE: %d runs", total_runs)
        logger.info("Victories: %d | Defeats: %d", total_victories, total_defeats)
        logger.info("Win rate: %.1f%%", 100.0 * total_victories / total_runs)
        logger.info("Avg fitness: %.1f", total_fitness / total_runs)
        if memory:
            logger.info("Memory stats: %s", memory.stats())
        # Ascension progression summary
        if character:
            from src.memory.models_v2 import normalize_character
            norm_char = normalize_character(character)
            char_stats = ascension_stats.stats_for(
                profile_hash=profile_hash, character=norm_char,
            )
            if char_stats:
                cleared = ascension_stats.highest_cleared(profile_hash, norm_char)
                logger.info("Highest cleared ascension for %s [%s]: A%d", norm_char, profile_hash, cleared)
                for s in char_stats:
                    logger.info(
                        "  A%d: %d/%d wins (%.0f%%), best floor %d",
                        s.ascension, s.wins, s.total_runs, s.win_rate * 100, s.best_floor,
                    )
        logger.info("=" * 50)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run STS2 agent")
    parser.add_argument("--steps", type=int, default=10000, help="Max steps per run")
    parser.add_argument(
        "--runs", type=int, default=0,
        help="Number of runs (0 = infinite loop, default: 0)",
    )
    parser.add_argument(
        "--character", type=str, default="Silent",
        help="Character for new runs (e.g. Regent). Default: Silent.",
    )
    parser.add_argument(
        "--ascension", type=str, default=None,
        help='Ascension level: integer (0-20), "auto" for auto-progression, '
             'or "auto-N" to auto-progress with a floor of A<N> (e.g. "auto-5")',
    )
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM, use random agent")
    parser.add_argument("--no-memory", action="store_true", help="Disable memory system")
    parser.add_argument("--no-skills", action="store_true", help="Disable skill system")
    parser.add_argument(
        "--model-family", type=str, default=None,
        help=(
            "Model family: gemini (default) | gpt | qwen | claude. "
            "Sets STS2_MODEL_FAMILY before config resolves. Per-tier family + "
            "effort overrides still available via STS2_MODEL_FAMILY_FAST / "
            "STS2_<FAMILY>_EFFORT_<TIER> env vars."
        ),
    )
    parser.add_argument(
        "--no-postrun", action="store_true",
        help=(
            "Disable postrun processing (memory extraction, skill discovery, "
            "evolution, distillation). Gameplay-time JSONL logs and "
            "memory/skill reads still work. Auto-disabled when the active "
            "family has no 'analysis' tier (e.g. qwen)."
        ),
    )
    parser.add_argument(
        "--no-evolution", action="store_true",
        help="Disable self-evolution (ToolPreprocessor + PlanVerifier + dynamic tools)",
    )
    parser.add_argument(
        "--experiment-tag", type=str, default="",
        help="Tag runs with an experiment batch identifier (recorded in history.jsonl)",
    )
    parser.add_argument(
        "--abandon-existing", action="store_true",
        help=(
            "On startup, if the game has an active run, abandon it and start fresh. "
            "Essential for ablation experiments where a leftover run from a prior "
            "subprocess would contaminate the new condition."
        ),
    )
    parser.add_argument(
        "--launch-game", action="store_true",
        help=(
            "Launch STS2 as a subprocess with STS2_API_PORT set to the chosen "
            "port (see --api-port). Resolves the game path from STS2_GAME_PATH "
            "or default Steam install locations. Required when running multiple "
            "game instances on one machine so each agent owns its game."
        ),
    )
    parser.add_argument(
        "--api-port", type=str, default="auto",
        help=(
            "Mod HTTP port. 'auto' (default) picks a free port when --launch-game "
            "is set, else uses 8128. An integer retargets the client to that port "
            "and, with --launch-game, tells the mod which port to bind."
        ),
    )
    parser.add_argument(
        "--launch-only", action="store_true",
        help=(
            "Spawn the game, verify /health, then block until Ctrl+C. No agent "
            "steps are run. Implies --launch-game. Useful for verifying the "
            "launcher + STS2_API_PORT plumbing without a full agent run."
        ),
    )
    parser.add_argument(
        "--monitor-port", type=str, default="auto",
        help=(
            "Monitor dashboard port. 'auto' (default) picks a free port when "
            "--launch-game is set (so multiple agents can run simultaneously "
            "without colliding), else uses STS2_MONITOR_PORT / 8081. An integer "
            "pins the port explicitly."
        ),
    )
    parser.add_argument(
        "--display-language", type=str, default=None, choices=["en", "zh"],
        help=(
            "When 'zh', the LLM is asked to additionally emit a `reasoning_zh` "
            "field (Simplified Chinese translation of `reasoning`) for stream "
            "display. Memory + skills + parsing pipelines remain English-only."
        ),
    )
    args = parser.parse_args()
    if args.no_memory:
        config.MEMORY_ENABLED = False
    if args.no_skills:
        config.SKILLS_ENABLED = False
    try:
        asyncio.run(main(
            max_steps=args.steps,
            max_runs=args.runs,
            character=args.character,
            use_llm=not args.no_llm,
            ascension_mode=args.ascension,
            experiment_tag=args.experiment_tag,
            abandon_existing=args.abandon_existing,
        ))
        _exit_code = 0
    except KeyboardInterrupt:
        _exit_code = 130
    except BaseException:
        _module_logger.exception("Unhandled error in run_agent")
        _exit_code = 1
    # Terminate the launched game subprocess (if any) before hard-exit. os._exit
    # bypasses atexit, so this must run explicitly here. ``terminate_launched_game``
    # is idempotent — main()'s post-gameplay early kill (before postrun) usually
    # already cleared the handle, in which case this call is a no-op.
    try:
        from src.launcher.game_launcher import terminate_launched_game
        terminate_launched_game()
    except BaseException:
        pass

    # Force-exit past daemon threads (uvicorn monitor on Windows) that otherwise
    # keep the interpreter alive after asyncio.run returns. All persistent state
    # is flushed synchronously during the run, so os._exit is safe here.
    import sys as _sys
    _sys.stdout.flush()
    _sys.stderr.flush()
    os._exit(_exit_code)
