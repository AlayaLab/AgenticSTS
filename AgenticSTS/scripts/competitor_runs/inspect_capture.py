"""Quick health summary of one competitor run's captured logs (Workstream C).

Verifies a run recorded normally and didn't get stuck:
  * llm_calls.jsonl  (proxy)  -> count, any non-200, any empty/no-toolcall replies
  * game_io.jsonl    (host)   -> per-step tool + result status, repeated-action (stuck) scan
  * run_summary.json (host)   -> outcome / floor / steps

Usage:  python -m scripts.competitor_runs.inspect_capture <run_id> [<run_id> ...]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

CAPTURES = Path(__file__).resolve().parent / "captures"

# Estimated Gemini 3.1 Pro price (USD per 1M tokens) for a rough $/run figure. The
# token counts below are the hard, provider-reported data; the $ is an estimate at this
# rate. Calibrate against the relay billing delta once a valid key is available, then
# update these two constants. (Set via env COMPETITOR_PRICE_IN / _OUT to override.)
import os as _os
PRICE_IN_PER_M = float(_os.environ.get("COMPETITOR_PRICE_IN", "1.25"))
PRICE_OUT_PER_M = float(_os.environ.get("COMPETITOR_PRICE_OUT", "10.0"))


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    return out


def inspect(run_id: str) -> None:
    d = CAPTURES / run_id
    print(f"\n===== {run_id} =====")
    if not d.exists():
        print(f"  (no capture dir at {d})")
        return

    llm = _load_jsonl(d / "llm_calls.jsonl")
    bad = [c for c in llm if c.get("status_code") != 200 or c.get("error")]
    empties = 0
    toolcalls = 0
    for c in llm:
        try:
            msg = c["response"]["choices"][0]["message"]
            if msg.get("tool_calls"):
                toolcalls += 1
            elif not (msg.get("content") or "").strip():
                empties += 1
        except (KeyError, IndexError, TypeError):
            pass
    print(f"  llm_calls: {len(llm)}  (non-200/err: {len(bad)}, with tool_calls: {toolcalls}, empty-no-tool: {empties})")
    for c in bad[:3]:
        print(f"    ! call seq={c.get('seq')} status={c.get('status_code')} err={c.get('error')}")

    # --- token usage + estimated cost (the useful dataset statistic) ---
    ti = to = tr = ttot = 0
    for c in llm:
        u = (c.get("response") or {}).get("usage") or {}
        ti += int(u.get("prompt_tokens", 0) or 0)
        to += int(u.get("completion_tokens", 0) or 0)
        tr += int((u.get("completion_tokens_details") or {}).get("reasoning_tokens", 0) or 0)
        ttot += int(u.get("total_tokens", 0) or 0)
    est = ti / 1e6 * PRICE_IN_PER_M + to / 1e6 * PRICE_OUT_PER_M
    print(f"  tokens: prompt={ti:,} completion={to:,} (reasoning={tr:,}) total={ttot:,}")
    print(f"  est_cost=${est:.3f}  (@ ${PRICE_IN_PER_M}/M in, ${PRICE_OUT_PER_M}/M out — estimate)")

    gio = _load_jsonl(d / "game_io.jsonl")
    actions = []
    for r in gio:
        ca = r.get("chosen_action") or {}
        tool = ca.get("tool") or ca.get("action")
        ar = r.get("action_result")
        status = ar.get("status") if isinstance(ar, dict) else None
        err = (ar.get("error") if isinstance(ar, dict) else None)
        actions.append(tool)
        flag = " ERR" if err else ""
        print(f"    step {r.get('seq')}: tool={tool} status={status}{flag}")
    # stuck scan: longest run of identical consecutive actions
    longest = run = 1
    for i in range(1, len(actions)):
        run = run + 1 if actions[i] == actions[i - 1] and actions[i] is not None else 1
        longest = max(longest, run)
    print(f"  game_io steps: {len(gio)}  (max identical-action streak: {longest})")

    summ = d / "run_summary.json"
    if summ.exists():
        s = json.loads(summ.read_text(encoding="utf-8"))
        print(f"  summary: outcome={s.get('outcome')} floor={s.get('final_floor')} "
              f"act={s.get('act_reached')} steps={s.get('steps')} stuck_aborts={s.get('stuck_aborts')}")
    else:
        print("  summary: (run still in progress — no run_summary.json yet)")


def main(argv: list[str] | None = None) -> int:
    args = argv if argv is not None else sys.argv[1:]
    if not args:
        # default: list capture dirs
        dirs = sorted(p.name for p in CAPTURES.iterdir() if p.is_dir()) if CAPTURES.exists() else []
        print("run ids:", ", ".join(dirs) or "(none)")
        return 0
    for run_id in args:
        inspect(run_id)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
