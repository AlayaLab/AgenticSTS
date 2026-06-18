"""FastAPI server for real-time agent monitoring.

Runs in a daemon thread alongside the agent process.
Provides WebSocket streaming and REST endpoints.

Frontend: run `cd frontend && npm run dev` separately.
Vite proxies /ws and /api to this server automatically.
"""

import asyncio
import json
import logging
import threading
from typing import Any

# NOTE: Do NOT use `from __future__ import annotations` in this module.
# It makes type hints lazy strings, and FastAPI cannot resolve `ws: WebSocket`
# when WebSocket is imported inside a function scope → WebSocket 403.

logger = logging.getLogger(__name__)


def create_monitor_app(event_bus: Any) -> Any:
    """Create FastAPI app wired to the given EventBus."""
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect
    from fastapi.middleware.cors import CORSMiddleware

    app = FastAPI(title="STS2 Agent Monitor", version="1.0.0")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )

    _status: dict = {
        "agent_running": False,
        "character": None,
        "run_id": None,
        "ascension": None,
        "total_tokens": 0,
        "total_calls": 0,
    }

    @app.get("/api/status")
    async def get_status() -> dict:
        return {
            **_status,
            "event_count": event_bus.event_count,
            "subscribers": event_bus.subscriber_count,
        }

    @app.get("/api/events/history")
    async def get_history(after_id: str | None = None) -> list[dict]:
        return event_bus.get_history(after_id=after_id)

    @app.websocket("/ws/events")
    async def websocket_events(ws: WebSocket) -> None:
        await ws.accept()
        sub = event_bus.subscribe()
        logger.info("WebSocket client connected")
        try:
            loop = asyncio.get_event_loop()
            while True:
                event = await loop.run_in_executor(None, sub.get)
                try:
                    await ws.send_text(json.dumps(event.to_dict(), ensure_ascii=False))
                except Exception:
                    break
        except WebSocketDisconnect:
            pass
        except Exception as e:
            logger.debug("WebSocket error: %s", e)
        finally:
            event_bus.unsubscribe(sub)
            logger.info("WebSocket client disconnected")

    # Start AI summarizer if enabled
    @app.on_event("startup")
    async def _start_summarizer() -> None:
        import config as _cfg

        if _cfg.MONITOR_SUMMARY_ENABLED:
            try:
                from src.monitor.summarizer import EventSummarizer

                summarizer = EventSummarizer(event_bus)
                summarizer.start()
                app._summarizer = summarizer  # type: ignore[attr-defined]
                logger.info("AI summarizer started (model=%s)", _cfg.MONITOR_SUMMARY_MODEL)
            except Exception as exc:
                logger.warning("Failed to start AI summarizer: %s", exc)

    # Serve built React frontend if available
    _mount_frontend(app)

    app._monitor_status = _status  # type: ignore[attr-defined]
    return app


def _mount_frontend(app: Any) -> None:
    """Mount built React frontend (frontend/dist/) for production use.

    In dev mode, use `cd frontend && npm run dev` instead (Vite proxy).
    """
    from pathlib import Path

    from fastapi.staticfiles import StaticFiles

    dist_path = Path(__file__).resolve().parent.parent.parent / "frontend" / "dist"
    if not dist_path.is_dir():
        return

    # Mount at "/" with html=True for SPA fallback (serves index.html for unknown paths)
    app.mount("/", StaticFiles(directory=str(dist_path), html=True), name="static")


def start_monitor_server(
    event_bus: Any,
    port: int = 8081,
    host: str = "0.0.0.0",
    fallback_range: tuple[int, int] = (8081, 8099),
) -> threading.Thread | None:
    """Start the monitor FastAPI server in a daemon thread.

    Binds the listening socket in the calling thread before handing its fd to
    uvicorn. This eliminates the race where two concurrent process-launches
    pick the same free port from a "probe then close" scanner — with the fd
    handed directly to uvicorn, whoever binds first owns the port, and the
    loser can fall back to the next free port in ``fallback_range`` without
    a race window.
    """
    try:
        import socket as _socket
        import uvicorn  # noqa: F401
        from fastapi import FastAPI  # noqa: F401
    except ImportError:
        logger.warning(
            "Monitor server requires 'fastapi', 'uvicorn', and 'websockets'. "
            "Install with: pip install -e '.[monitor]'"
        )
        return None

    # Bind a real listen socket up-front so there's no gap between "we think
    # this port is free" and "uvicorn asks the kernel for it."
    lo, hi = fallback_range
    ordered = [port] + [p for p in range(lo, hi + 1) if p != port]
    sock: _socket.socket | None = None
    actual_port: int | None = None
    for candidate in ordered:
        try:
            s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
            s.setsockopt(_socket.SOL_SOCKET, _socket.SO_REUSEADDR, 1)
            s.bind((host, candidate))
            s.listen(128)
            sock = s
            actual_port = candidate
            break
        except OSError:
            continue
    if sock is None or actual_port is None:
        logger.warning(
            "Monitor server could not bind any port in %d..%d (requested %d).",
            lo, hi, port,
        )
        return None

    app = create_monitor_app(event_bus)

    # uvicorn's ``fd=`` path calls ``socket.fromfd(fd, AF_UNIX, ...)`` which
    # raises AttributeError on Windows because ``socket.AF_UNIX`` is not
    # always present. Fall back to host/port binding there: we close the
    # probe socket and let uvicorn re-bind. A tiny TOCTOU window remains
    # between close and uvicorn.run, but on a single-user dev box the race
    # with concurrent launches is tolerable. POSIX keeps the race-free
    # fd= handoff.
    import sys as _sys
    use_fd = _sys.platform != "win32"
    fd = sock.fileno() if use_fd else None
    if not use_fd:
        sock.close()
        sock = None

    def _run() -> None:
        # Hand the pre-bound fd to uvicorn. The server keeps the socket alive
        # for the lifetime of the daemon thread. On Windows, uvicorn re-binds
        # host:port itself (see comment above).
        kwargs: dict = {"log_level": "warning", "access_log": False}
        if use_fd:
            kwargs["fd"] = fd
        else:
            kwargs["host"] = host
            kwargs["port"] = actual_port
        uvicorn.run(app, **kwargs)

    thread = threading.Thread(target=_run, daemon=True, name="monitor-server")
    thread.start()
    if actual_port != port:
        logger.warning(
            "Monitor server: requested port %d was busy; bound %d instead.",
            port, actual_port,
        )
    logger.info("Monitor server started on http://%s:%d", host, actual_port)
    thread._monitor_app = app  # type: ignore[attr-defined]
    thread._monitor_port = actual_port  # type: ignore[attr-defined]
    thread._monitor_sock = sock  # keep socket referenced  # type: ignore[attr-defined]
    return thread
