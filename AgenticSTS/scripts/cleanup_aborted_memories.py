from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path

import config
from src.storage import paths

_NATURAL_TERMINAL_STATES = {"victory", "game_over"}
_INCOMPLETE_HINTS = (
    "fatal",
    "aborting",
    "abort",
    "max steps",
    "max_steps",
    "interrupt",
    "loop_exit",
    "llm decision failed",
    "terminating run",
)
_MEMORY_FILES = (
    "combat_episodes.jsonl",
    "route_memories.jsonl",
    "card_builds.jsonl",
)


@dataclass(frozen=True)
class LegacyIncompleteRun:
    run_id: str
    log_path: Path
    reason: str


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    records: list[dict] = []
    with path.open("r", encoding="utf-8") as handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            records.append(json.loads(line))
    return records


def _write_jsonl(path: Path, records: list[dict]) -> None:
    text = "\n".join(json.dumps(record, ensure_ascii=False) for record in records)
    if text:
        text += "\n"
    path.write_text(text, encoding="utf-8")


def _record_has_hint(record: dict, *, tail_only: bool = False) -> bool:
    haystacks = []
    if isinstance(record.get("error"), str):
        haystacks.append(record["error"].lower())
    if isinstance(record.get("end_reason"), str):
        haystacks.append(record["end_reason"].lower())
    if not haystacks and tail_only:
        return False
    return any(hint in haystack for haystack in haystacks for hint in _INCOMPLETE_HINTS)


def classify_legacy_incomplete_run(log_path: Path) -> LegacyIncompleteRun | None:
    records = _load_jsonl(log_path)
    if not records:
        return None

    run_id = ""
    for record in records:
        if isinstance(record.get("run_id"), str) and record["run_id"].strip():
            run_id = record["run_id"].strip()
            break
    if not run_id:
        return None

    has_run_end = any(record.get("event") == "run_end" for record in records)
    if not has_run_end:
        return None

    saw_natural_terminal = any(
        record.get("event") == "state"
        and record.get("state_type") in _NATURAL_TERMINAL_STATES
        for record in records
    )
    if saw_natural_terminal:
        return None

    run_end_abort = any(
        record.get("event") == "run_end"
        and (
            record.get("completion_reason") == "aborted"
            or _record_has_hint(record)
        )
        for record in records
    )
    tail_records = records[-6:]
    tail_incomplete_signal = any(_record_has_hint(record, tail_only=True) for record in tail_records)

    if not run_end_abort and not tail_incomplete_signal:
        return None

    reason = "run_end_aborted" if run_end_abort else "tail_incomplete_signal"
    return LegacyIncompleteRun(run_id=run_id, log_path=log_path, reason=reason)


def find_legacy_incomplete_runs(log_dir: Path) -> list[LegacyIncompleteRun]:
    candidates: list[LegacyIncompleteRun] = []
    for path in sorted(log_dir.glob("run_*.jsonl")):
        candidate = classify_legacy_incomplete_run(path)
        if candidate is not None:
            candidates.append(candidate)
    return candidates


def cleanup_memory_records(
    run_ids: set[str],
    memory_dir: Path,
    *,
    apply: bool,
) -> tuple[dict[str, int], dict[str, dict[str, int]]]:
    total_counts: dict[str, int] = {}
    per_run_counts: dict[str, dict[str, int]] = {run_id: {} for run_id in run_ids}
    for filename in _MEMORY_FILES:
        path = memory_dir / filename
        records = _load_jsonl(path)
        removed_by_run = {
            run_id: sum(1 for record in records if record.get("run_id") == run_id)
            for run_id in run_ids
        }
        kept = [record for record in records if record.get("run_id") not in run_ids]
        removed = len(records) - len(kept)
        total_counts[filename] = removed
        for run_id, count in removed_by_run.items():
            per_run_counts.setdefault(run_id, {})[filename] = count
        if apply and removed > 0:
            _write_jsonl(path, kept)
    return total_counts, per_run_counts


def _per_run_total(counts: dict[str, int]) -> int:
    return sum(counts.get(filename, 0) for filename in _MEMORY_FILES)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Remove legacy aborted run records from V2 memory stores.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Write changes instead of running in dry-run mode.",
    )
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path(config.LOG_DIR),
        help="Directory containing run_*.jsonl logs.",
    )
    parser.add_argument(
        "--memory-dir",
        type=Path,
        default=paths.memory_v2_dir(),
        help="Directory containing combat_episodes.jsonl / route_memories.jsonl / card_builds.jsonl.",
    )
    parser.add_argument(
        "--show-zero",
        action="store_true",
        help="Also print candidate logs whose target memory records are already gone.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    candidates = find_legacy_incomplete_runs(args.logs_dir)
    run_ids = {candidate.run_id for candidate in candidates}
    total_counts, per_run_counts = cleanup_memory_records(run_ids, args.memory_dir, apply=args.apply)
    mode = "apply" if args.apply else "dry-run"

    if not candidates:
        print(f"[{mode}] no legacy incomplete runs found")
        return 0

    actionable = [
        candidate for candidate in candidates
        if _per_run_total(per_run_counts.get(candidate.run_id, {})) > 0
    ]
    display_candidates = candidates if args.show_zero else actionable

    if not display_candidates:
        print(
            f"[{mode}] no deletable legacy incomplete records found "
            f"({len(candidates)} candidate logs already clean)"
        )
        print(
            f"[{mode}] total combat={total_counts['combat_episodes.jsonl']} "
            f"route={total_counts['route_memories.jsonl']} "
            f"build={total_counts['card_builds.jsonl']}"
        )
        return 0

    for candidate in display_candidates:
        print(
            f"[{mode}] run_id={candidate.run_id} "
            f"log={candidate.log_path.name} "
            f"reason={candidate.reason} "
            f"combat={per_run_counts[candidate.run_id].get('combat_episodes.jsonl', 0)} "
            f"route={per_run_counts[candidate.run_id].get('route_memories.jsonl', 0)} "
            f"build={per_run_counts[candidate.run_id].get('card_builds.jsonl', 0)}"
        )
    if not args.show_zero and len(actionable) < len(candidates):
        print(
            f"[{mode}] hidden already-clean candidates={len(candidates) - len(actionable)} "
            "(use --show-zero to list them)"
        )
    print(
        f"[{mode}] total combat={total_counts['combat_episodes.jsonl']} "
        f"route={total_counts['route_memories.jsonl']} "
        f"build={total_counts['card_builds.jsonl']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
