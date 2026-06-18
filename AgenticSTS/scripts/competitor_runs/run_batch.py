"""Batch runner for one competitor cell (Workstream C, C.4).

Runs N **completed** games for a single MCP-host competitor (STS2MCP / CharTyr) at
fixed A0, then STOPS. The user swaps the mod and re-runs this for the next competitor.

The load-bearing methodology point (reviewer-defensible — see PROTOCOL.md):

  **The denominator is completed games, not launched games.**

  * victory / in-game defeat            -> a completed game; counted toward N.
  * agent_abort / max_steps / harness    -> NOT the baseline "losing"; the attempt is
    error / crash / no summary written      discarded and re-run, and logged in the
                                            manifest with its reason.

This mirrors our own "first ten completed games per condition" rule, so a reviewer
cannot say we counted infrastructure failures as the baseline failing. Every attempt
(completed or discarded) is recorded in ``captures/<tag>/batch_manifest.json`` for full
transparency.

This runner does NOT touch the game or the mod. Before launching it, the user must:
  1. Have removed our mod (complete-replacement rule — the host also hard-checks :8128).
  2. Have the target competitor's mod loaded and the game at the main menu / a fresh
     state, so the host's run-setup can embark a {character} A{ascension} run.

Each attempt is a FRESH host process (fresh accumulating-context transcript per game —
accumulation is within a run, reset between independent runs, which is correct).

Usage::

    # one competitor, 5 completed games, then stop:
    python -m scripts.competitor_runs.run_batch --competitor sts2mcp --n 5
    # then swap the mod and:
    python -m scripts.competitor_runs.run_batch --competitor chartyr --n 5
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

_REPO_ROOT = Path(__file__).resolve().parents[2]
CAPTURES_ROOT = Path(__file__).resolve().parent / "captures"

# Outcomes that count as a completed datapoint (enter the denominator). max_steps is the
# decision-cap outcome: the baseline survived to the cap without dying — a valid
# "floor reached under a fixed decision budget" datapoint, NOT a failure to re-run.
# Only genuine harness failures (agent_abort / no-summary) are discarded + re-run.
_COMPLETED = frozenset({"victory", "defeat", "max_steps"})
# Host exit codes that are FATAL setup errors (re-running won't help) -> stop the batch.
#   2 = no API key; 3 = our mod still loaded (complete-replacement guard).
_FATAL_EXIT = {2: "no API key (set STS2_GEMINI_API_KEY)", 3: "our mod still loaded on :8128 (remove it — complete-replacement rule)"}

# Per-competitor mod health endpoint. Used to fail fast if the GAME isn't running with
# the mod loaded — otherwise the agent flails against a dead endpoint, racking up useless
# steps and cost (observed: 96 no-op steps against a closed game).
_MOD_HEALTH = {"sts2mcp": "http://localhost:15526/", "chartyr": "http://127.0.0.1:8080/health"}


def _mod_reachable(competitor: str) -> bool:
    """True if the competitor's in-game mod HTTP endpoint answers (game is running)."""
    url = _MOD_HEALTH.get(competitor)
    if not url:
        return True
    try:
        return httpx.get(url, timeout=4.0).status_code < 500
    except Exception:  # noqa: BLE001 - any connection failure means the game/mod is down.
        return False


def _host_command(args: argparse.Namespace, run_id: str) -> list[str]:
    """Build the `python -m scripts.competitor_runs.mcp_gemini_host ...` invocation."""
    cmd = [
        sys.executable,
        "-m",
        "scripts.competitor_runs.mcp_gemini_host",
        "--competitor",
        args.competitor,
        "--run-id",
        run_id,
        "--character",
        args.character,
        "--ascension",
        str(args.ascension),
        "--model",
        args.model,
        "--proxy-url",
        args.proxy_url,
        "--max-steps",
        str(args.max_steps),
        "--action-delay",
        str(args.action_delay),
        "--experiment-tag",
        args.experiment_tag,
        "--competitor-root",
        args.competitor_root,
    ]
    if args.allow_our_mod:
        cmd.append("--allow-our-mod")
    return cmd


def _read_summary(run_id: str) -> dict[str, Any] | None:
    """Read captures/<run_id>/run_summary.json if the host wrote one."""
    path = CAPTURES_ROOT / run_id / "run_summary.json"
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def run_batch(args: argparse.Namespace) -> int:
    tag = args.experiment_tag
    manifest_dir = CAPTURES_ROOT / tag
    manifest_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = manifest_dir / "batch_manifest.json"

    completed: list[dict[str, Any]] = []
    discarded: list[dict[str, Any]] = []
    attempt = 0
    started_at = time.time()

    # RESUME: re-attach to any runs already completed for this tag (survives reboots /
    # session restarts). Pre-loading them means a relaunch never re-runs or overwrites good
    # data — the loop below skips their attempt slots and only runs missing/partial ones.
    for _d in sorted(CAPTURES_ROOT.glob(f"{tag}-a*")):
        if not _d.is_dir():
            continue
        _s = _read_summary(_d.name)
        if _s and str(_s.get("outcome")) in _COMPLETED:
            completed.append(_s)
    if completed:
        print(f"[batch] RESUME: {len(completed)} completed run(s) already on disk: "
              f"{[s.get('run_id') for s in completed]}")

    print(
        f"[batch] competitor={args.competitor}  target N={args.n} completed games "
        f"(fixed A{args.ascension}, {args.character})  max_attempts={args.max_attempts}"
    )
    print(f"[batch] capturing under {CAPTURES_ROOT}/{tag}-aNN/  manifest -> {manifest_path}")

    if not _mod_reachable(args.competitor):
        print(f"[batch] FATAL: {args.competitor} mod not reachable at {_MOD_HEALTH.get(args.competitor)} — "
              "is the GAME running with this mod loaded? Launch it, confirm the endpoint, then re-run.")
        return 2

    while len(completed) < args.n and attempt < args.max_attempts:
        attempt += 1
        if not _mod_reachable(args.competitor):
            print(f"[batch] mod unreachable before attempt {attempt} (game closed/crashed?). Stopping batch.")
            break
        run_id = f"{tag}-a{attempt:02d}"
        # Resume: never re-run / overwrite an attempt that already completed.
        _prior = _read_summary(run_id)
        if _prior and str(_prior.get("outcome")) in _COMPLETED:
            continue
        # A partial/aborted capture dir from a crash would corrupt the re-run (the proxy
        # appends to llm_calls.jsonl by run_id); remove it so this attempt starts clean.
        _rd = CAPTURES_ROOT / run_id
        if _rd.exists():
            shutil.rmtree(_rd, ignore_errors=True)
        print(f"\n[batch] attempt {attempt} (have {len(completed)}/{args.n}) -> run_id {run_id}")
        cmd = _host_command(args, run_id)
        try:
            proc = subprocess.run(cmd, cwd=str(_REPO_ROOT))
        except KeyboardInterrupt:
            print("[batch] interrupted by user; writing partial manifest.")
            break
        code = proc.returncode

        if code in _FATAL_EXIT:
            print(f"[batch] FATAL: host exit {code} — {_FATAL_EXIT[code]}. Stopping batch.")
            discarded.append({"run_id": run_id, "attempt": attempt, "reason": f"fatal_exit_{code}", "detail": _FATAL_EXIT[code]})
            break

        summary = _read_summary(run_id)
        if summary is None:
            print(f"[batch] attempt {attempt}: no run_summary.json (host exit {code}) — discard + retry.")
            discarded.append({"run_id": run_id, "attempt": attempt, "reason": "no_summary", "exit_code": code})
            continue

        outcome = str(summary.get("outcome", "unknown"))
        if outcome in _COMPLETED:
            completed.append(summary)
            print(f"[batch] attempt {attempt}: COMPLETED outcome={outcome} floor={summary.get('final_floor')} -> counted {len(completed)}/{args.n}")
        else:
            print(f"[batch] attempt {attempt}: non-completed outcome={outcome} — discard + retry (not a baseline loss).")
            discarded.append({"run_id": run_id, "attempt": attempt, "reason": outcome, "exit_code": code})

    ended_at = time.time()
    wins = sum(1 for s in completed if s.get("outcome") == "victory")
    n_done = len(completed)
    manifest = {
        "competitor": args.competitor,
        "experiment_tag": tag,
        "target_n": args.n,
        "n_completed": n_done,
        "wins": wins,
        "win_rate": (wins / n_done) if n_done else None,
        "attempts": attempt,
        "discarded": discarded,
        "completed_run_ids": [s.get("run_id") for s in completed],
        "character": args.character,
        "ascension": args.ascension,
        "model": args.model,
        "started_at_iso": datetime.fromtimestamp(started_at, timezone.utc).isoformat(),
        "ended_at_iso": datetime.fromtimestamp(ended_at, timezone.utc).isoformat(),
        "note": (
            "Denominator = victory/defeat/max_steps. max_steps = decision-capped datapoint "
            "(played to the cap without dying; scored by floor reached). Only agent_abort / "
            "harness failures were discarded and re-run."
        ),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"[batch] DONE competitor={args.competitor}")
    print(f"[batch] completed {n_done}/{args.n}  wins={wins}  discarded={len(discarded)}  attempts={attempt}")
    print(f"[batch] manifest: {manifest_path}")
    if n_done < args.n:
        print(
            f"[batch] WARNING: only {n_done}/{args.n} completed within {args.max_attempts} "
            "attempts. Inspect the discarded reasons (mod loaded? game at menu? deps?) "
            "before raising --max-attempts."
        )
        return 1
    print(f"[batch] Swap the mod (remove this competitor's, install the next, confirm :8128 dead) and run the next competitor.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="run_batch",
        description=(
            "Run N completed games for ONE MCP-host competitor (STS2MCP/CharTyr) at "
            "fixed A0, then stop. Completed-games denominator: aborts/harness errors are "
            "re-run, not counted as losses. (Workstream C, C.4 — see PROTOCOL.md.)"
        ),
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--competitor", required=True, choices=("sts2mcp", "chartyr"))
    p.add_argument("--n", type=int, default=5, help="Target number of COMPLETED games.")
    p.add_argument(
        "--max-attempts",
        type=int,
        default=0,
        help="Cap on total host invocations (default 0 = auto: 2*N + 3).",
    )
    p.add_argument("--character", default="Silent")
    p.add_argument("--ascension", type=int, default=0)
    p.add_argument("--model", default="gemini-3.1-pro-preview")
    p.add_argument("--proxy-url", default="http://127.0.0.1:8129/v1")
    p.add_argument("--max-steps", type=int, default=2500,
                   help="Decision cap. A full STS2 run (victory or deep death) is ~1500-2000 "
                        "decisions, so 2500 lets runs reach a natural terminal; if a run still "
                        "hits the cap it counts (scored by floor reached), not re-run.")
    p.add_argument(
        "--action-delay",
        type=float,
        default=0.5,
        help="Idle pause (s) between steps. Calls are ~12s apart (latency-bound) so this "
             "is just a small buffer, not rate-limit pacing; does not affect captured data.",
    )
    p.add_argument(
        "--experiment-tag",
        default=None,
        help="Base tag (default: competitor-<key>-gemini-A0). Per-attempt run-ids are <tag>-aNN.",
    )
    p.add_argument("--competitor-root", default=str(_REPO_ROOT / "paper" / "competitors"))
    p.add_argument("--allow-our-mod", action="store_true", help="Forward to host (disables the :8128 guard — NOT recommended).")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.experiment_tag is None:
        args.experiment_tag = f"competitor-{args.competitor}-gemini-A{args.ascension}"
    if args.max_attempts <= 0:
        args.max_attempts = 2 * args.n + 3
    return run_batch(args)


if __name__ == "__main__":
    raise SystemExit(main())
