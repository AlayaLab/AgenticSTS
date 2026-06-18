"""A/B test: compact re-plan prompts vs. full logged history.

Hypothesis: the current re-plan keeps the (now-stale) Round N State
message and the executed plan in-context, adding ~3k chars of
redundant/delta-duplicated content. We can reconstruct a single
"current state" user message from the latest re-plan content and drop
the stale turns, cutting input tokens substantially without changing
the decision.

For each sampled re-plan call we issue two variants:

  - original : use the exact 5-message history logged at runtime
               (combat_start, "ok", stale Round State, assistant plan,
               Re-plan delta).
  - compact  : combat_start + a single reconstructed user message that
               starts from msg[4] (the re-plan delta) and re-injects
               the Key Effects glossary and Strategic Thread lines that
               the slim re-plan path strips.

Usage:
    python -m scripts.test_replan_compact_ab \
        --log logs/run_20260417_050958_0d6882de.jsonl \
        --samples 10 --runs 1
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import config  # noqa: E402  (populates env)
from src.brain.prompts._keyword_fmt import KW_GLOSSARY  # noqa: E402
from src.brain.v2_backend import V2Backend  # noqa: E402


DECISION_RE = re.compile(r"<decision>\s*(\{.*?\})\s*</decision>", re.DOTALL)


def load_replan_calls(
    log_path: Path,
    limit: int,
    *,
    stage: str | None = None,
    offset: int = 0,
    min_round: int | None = None,
) -> list[dict]:
    """Collect `limit` replan LLM calls (v2_single_call) from the log.

    Filters:
      stage: require 'Boss stage: <stage>' in msg[0] (e.g. 'final_boss').
      offset: skip this many matching samples before collecting.
      min_round: require Round >= min_round in the re-plan header.
    """
    out: list[dict] = []
    skipped = 0
    with open(log_path, "r", encoding="utf-8") as f:
        for lineno, line in enumerate(f, 1):
            try:
                e = json.loads(line)
            except Exception:
                continue
            if e.get("event") != "llm_call":
                continue
            if e.get("call_type") != "v2_single_call":
                continue
            msgs = e.get("messages") or []
            if len(msgs) < 5:
                continue  # need the full 5-turn replan shape
            last_user = next(
                (m for m in reversed(msgs) if m.get("role") == "user"),
                None,
            )
            if not last_user:
                continue
            c = last_user.get("content", "")
            if not (isinstance(c, str) and "Re-plan" in c):
                continue
            if stage:
                cs = msgs[0].get("content", "")
                if isinstance(cs, list):
                    cs = "".join(p.get("text", "") for p in cs if isinstance(p, dict))
                if f"Boss stage: {stage}" not in cs:
                    continue
            if min_round is not None:
                m = re.search(r"Round (\d+) Re-plan", c)
                if not m or int(m.group(1)) < min_round:
                    continue
            if skipped < offset:
                skipped += 1
                continue
            out.append({"lineno": lineno, "record": e})
            if len(out) >= limit:
                break
    return out


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(p.get("text", "") for p in content if isinstance(p, dict))
    return str(content)


def extract_section(text: str, header: str) -> str:
    """Extract a single top-level ('## ') section, inclusive of its header."""
    lines = text.splitlines()
    out: list[str] = []
    capturing = False
    for ln in lines:
        if ln.strip() == header:
            capturing = True
            out.append(ln)
            continue
        if capturing:
            if ln.startswith("## "):
                break
            out.append(ln)
    while out and not out[-1].strip():
        out.pop()
    return "\n".join(out).strip()


def build_key_effects_from_scratch(haystack: str) -> str:
    """Scan raw text for known keywords and emit a fresh glossary block."""
    lower = haystack.lower()
    hits = [f"- {desc}" for kw, desc in KW_GLOSSARY.items() if kw in lower]
    if not hits:
        return ""
    return "\n".join(["## Key Effects (active this combat)", *hits])


def build_compact_user_message(round_state: str, replan_text: str) -> str:
    """Stitch an enriched current-state message from the replan delta.

    Starts from the re-plan message (which already carries the latest
    hand / enemies / piles / computed insights / re-plan context) and
    splices back the Strategic Thread block and Key Effects glossary
    that the slim re-plan path removes.
    """
    strat = extract_section(round_state, "## Strategic Thread")
    glossary = extract_section(round_state, "## Key Effects (active this combat)")
    if not glossary:
        glossary = build_key_effects_from_scratch(replan_text)

    parts = [replan_text.rstrip()]
    if glossary:
        parts += ["", glossary]
    if strat:
        parts += ["", strat]
    return "\n".join(parts)


def parse_plan(text: str) -> dict | None:
    m = DECISION_RE.search(text or "")
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def plan_signature(plan: dict | None) -> tuple[str, tuple[str, ...]]:
    """A coarse equivalence key: end_turn flag + ordered card names."""
    if not plan:
        return ("no-plan", ())
    actions = plan.get("plan") or []
    sig_parts: list[str] = []
    for a in actions:
        kind = a.get("type", "?")
        if kind == "card":
            sig_parts.append(a.get("card") or "?")
        elif kind == "potion":
            sig_parts.append("pot:" + (a.get("potion") or "?"))
        else:
            sig_parts.append(kind)
    return (str(bool(plan.get("end_turn"))), tuple(sig_parts))


def run_once(
    backend: V2Backend,
    *,
    system: str,
    messages: list[dict],
    provider: str,
    model: str,
    effort: str,
) -> dict:
    t0 = time.monotonic()
    resp = backend.call(
        system=system,
        messages=messages,
        provider=provider,
        model=model,
        think=True,
        effort=effort,
        tools=None,
        max_tokens=8192,
        openai_relay_profile="default",
    )
    latency_ms = (time.monotonic() - t0) * 1000
    text_parts: list[str] = []
    for block in resp.content:
        if getattr(block, "type", None) == "text":
            text_parts.append(block.text)
    full_text = "\n".join(text_parts)
    plan = parse_plan(full_text)
    return {
        "input_tokens": resp.usage.input_tokens,
        "output_tokens": resp.usage.output_tokens,
        "latency_ms": round(latency_ms, 1),
        "stop_reason": resp.stop_reason,
        "text": full_text,
        "plan": plan,
        "signature": plan_signature(plan),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="AB-test compact replan prompts")
    parser.add_argument(
        "--log",
        default="logs/run_20260417_050958_0d6882de.jsonl",
    )
    parser.add_argument("--samples", type=int, default=10)
    parser.add_argument("--runs", type=int, default=1, help="Runs per variant per sample")
    parser.add_argument("--provider", default="openai_compatible")
    parser.add_argument("--model", default=None)
    parser.add_argument("--effort", default="medium")
    parser.add_argument(
        "--stage",
        default=None,
        help="Filter to a specific boss stage (e.g. 'final_boss').",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip this many matching samples before collecting.",
    )
    parser.add_argument(
        "--min-round",
        type=int,
        default=None,
        dest="min_round",
        help="Only collect re-plans whose Round number >= this value.",
    )
    args = parser.parse_args()

    log_path = Path(args.log)
    if not log_path.is_absolute():
        log_path = ROOT / log_path
    samples = load_replan_calls(
        log_path,
        args.samples,
        stage=args.stage,
        offset=args.offset,
        min_round=args.min_round,
    )
    if not samples:
        print("No replan samples found.")
        return

    print("=== Re-plan Compact AB Test ===")
    print(f"Log: {log_path.name}  samples: {len(samples)}  runs/variant: {args.runs}")
    print(f"Provider: {args.provider}  effort: {args.effort}")
    print()

    backend = V2Backend()
    results: list[dict] = []

    for idx, sample in enumerate(samples, 1):
        rec = sample["record"]
        msgs = rec.get("messages") or []
        system = rec.get("system_prompt") or ""
        model = args.model or rec.get("model") or "gemini-3.1-pro-preview"

        combat_start = _text(msgs[0].get("content"))
        round_state = _text(msgs[2].get("content"))
        assistant_plan = _text(msgs[3].get("content"))
        replan_text = _text(msgs[4].get("content"))

        original_messages = [
            {"role": "user", "content": combat_start},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            {"role": "user", "content": round_state},
            {"role": "assistant", "content": [{"type": "text", "text": assistant_plan}]},
            {"role": "user", "content": replan_text},
        ]

        compact_user = build_compact_user_message(round_state, replan_text)
        compact_messages = [
            {"role": "user", "content": combat_start},
            {"role": "assistant", "content": [{"type": "text", "text": "ok"}]},
            {"role": "user", "content": compact_user},
        ]

        orig_chars = sum(len(_text(m.get("content"))) for m in original_messages)
        comp_chars = sum(len(_text(m.get("content"))) for m in compact_messages)
        delta_pct = 100 * (orig_chars - comp_chars) / orig_chars if orig_chars else 0

        print(
            f"[{idx}/{len(samples)}] log line {sample['lineno']}  "
            f"chars orig={orig_chars} compact={comp_chars} "
            f"(-{orig_chars - comp_chars}, {delta_pct:.1f}%)"
        )

        for variant, msgs_variant in [
            ("original", original_messages),
            ("compact", compact_messages),
        ]:
            for run_i in range(args.runs):
                try:
                    r = run_once(
                        backend,
                        system=system,
                        messages=msgs_variant,
                        provider=args.provider,
                        model=model,
                        effort=args.effort,
                    )
                except Exception as exc:
                    print(f"    {variant} run {run_i+1}: ERROR {type(exc).__name__}: {exc}")
                    results.append({"sample": idx, "variant": variant, "error": str(exc)})
                    continue
                results.append({
                    "sample": idx,
                    "variant": variant,
                    "run": run_i + 1,
                    **r,
                })
                print(
                    f"    {variant:8s} run {run_i+1}: in={r['input_tokens']}  "
                    f"out={r['output_tokens']}  lat={r['latency_ms']:.0f}ms  "
                    f"sig={r['signature']}"
                )
        print()

    # Aggregate
    print("=== Aggregate ===")
    by_variant: dict[str, list[dict]] = {}
    for r in results:
        if "error" in r:
            continue
        by_variant.setdefault(r["variant"], []).append(r)

    for variant, rows in by_variant.items():
        if not rows:
            continue
        avg_in = sum(r["input_tokens"] or 0 for r in rows) / len(rows)
        avg_out = sum(r["output_tokens"] or 0 for r in rows) / len(rows)
        avg_lat = sum(r["latency_ms"] for r in rows) / len(rows)
        print(
            f"{variant:8s}  n={len(rows):3d}  "
            f"avg_in={avg_in:7.0f}  avg_out={avg_out:6.0f}  avg_lat={avg_lat:6.0f}ms"
        )

    # Decision agreement between variants (per sample, run 1 only)
    print()
    print("=== Plan Agreement (run 1) ===")
    orig_sig: dict[int, tuple] = {}
    comp_sig: dict[int, tuple] = {}
    for r in results:
        if "error" in r or r.get("run") != 1:
            continue
        if r["variant"] == "original":
            orig_sig[r["sample"]] = r["signature"]
        elif r["variant"] == "compact":
            comp_sig[r["sample"]] = r["signature"]
    match = diff = 0
    for s in sorted(set(orig_sig) & set(comp_sig)):
        o = orig_sig[s]
        c = comp_sig[s]
        if o == c:
            match += 1
            marker = "="
        else:
            diff += 1
            marker = "DIFF"
        print(f"  sample {s}: {marker}")
        if o != c:
            print(f"     original: {o}")
            print(f"     compact : {c}")
    print(f"match: {match}  diff: {diff}")


if __name__ == "__main__":
    main()
