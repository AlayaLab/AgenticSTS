"""Boss winrate split by combat-guide availability.

For each boss episode in the per-experiment isolated data dir, decide whether
a combat guide for ``(enemy_key, character)`` existed at episode time, then
aggregate winrate into ``no_guide`` vs ``has_guide`` buckets.

Source-of-truth precedence:

1. ``memory/v2/guide_consolidation_log.jsonl`` — append-only audit log written
   on every successful set_*_guide(). Use the **earliest** combat row for
   each (enemy_key, character) as the guide-availability cutoff.
2. Fallback: ``guides.json::combat_guides[*].created_at`` — unreliable for
   re-consolidated guides (the constructor resets ``created_at``); use only
   when the audit log is missing for that experiment.

Usage:
    python -m scripts.analyze_boss_guide_effect
    python -m scripts.analyze_boss_guide_effect --tag gem-b-medium-2026-05-01
    python -m scripts.analyze_boss_guide_effect --tag <a> --tag <b> --out report.md
    python -m scripts.analyze_boss_guide_effect --format json
"""
from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from src.memory.enemy_keys import normalize_enemy_key
from src.memory.models_v2 import normalize_character
from src.storage import paths


@dataclass
class GuideInfo:
    first_available_at: float  # earliest timestamp at which the guide existed
    source: str                # "consolidation_log" or "guides_json_fallback"
    episode_count: int = 0


@dataclass
class Bucket:
    n: int = 0
    wins: int = 0

    @property
    def winrate(self) -> float:
        return self.wins / self.n if self.n else 0.0


@dataclass
class ConditionResult:
    experiment: str
    condition: str
    no_guide: Bucket = field(default_factory=Bucket)
    has_guide: Bucket = field(default_factory=Bucket)
    per_boss: dict[str, dict[str, Bucket]] = field(default_factory=dict)
    total_boss_episodes: int = 0
    skipped_no_timestamp: int = 0
    guide_source: str = "none"  # consolidation_log | guides_json_fallback | none


def _guide_lookup_key(enemy_key: str, character: str) -> str:
    return f"{normalize_enemy_key(enemy_key).lower()}:{normalize_character(character)}"


def load_consolidation_log(log_path: Path) -> dict[str, GuideInfo]:
    """Earliest combat-guide row per (enemy_key, character) from the audit log."""
    out: dict[str, GuideInfo] = {}
    if not log_path.exists():
        return out
    with log_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if row.get("guide_type") != "combat":
                continue
            ts = row.get("ts")
            ek = row.get("enemy_key")
            ch = row.get("character")
            if ts is None or not ek or not ch:
                continue
            key = _guide_lookup_key(ek, ch)
            existing = out.get(key)
            if existing is None or float(ts) < existing.first_available_at:
                out[key] = GuideInfo(
                    first_available_at=float(ts),
                    source="consolidation_log",
                    episode_count=int(row.get("episode_count") or 0),
                )
    return out


def load_guides_json_fallback(guides_path: Path) -> dict[str, GuideInfo]:
    """Fallback: use ``created_at`` from guides.json. Unreliable — see module docstring."""
    out: dict[str, GuideInfo] = {}
    if not guides_path.exists():
        return out
    raw = json.loads(guides_path.read_text(encoding="utf-8"))
    combat = raw.get("combat_guides", {})
    if not isinstance(combat, dict):
        return out
    for key, val in combat.items():
        if not isinstance(val, dict):
            continue
        created = val.get("created_at")
        if created is None:
            continue
        out[key] = GuideInfo(
            first_available_at=float(created),
            source="guides_json_fallback",
            episode_count=int(val.get("episode_count") or 0),
        )
    return out


def iter_episodes(episodes_path: Path) -> Iterable[dict]:
    if not episodes_path.exists():
        return
    with episodes_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def analyze_condition(experiment: str, condition: str, cond_dir: Path) -> ConditionResult:
    result = ConditionResult(experiment=experiment, condition=condition)
    log_path = cond_dir / "memory" / "v2" / "guide_consolidation_log.jsonl"
    guides = load_consolidation_log(log_path)
    if guides:
        result.guide_source = "consolidation_log"
    else:
        guides = load_guides_json_fallback(cond_dir / "memory" / "v2" / "guides.json")
        result.guide_source = "guides_json_fallback" if guides else "none"
    episodes_path = cond_dir / "memory" / "v2" / "combat_episodes.jsonl"

    for ep in iter_episodes(episodes_path):
        if ep.get("combat_type") != "boss":
            continue
        if ep.get("is_aborted"):
            continue
        ts = ep.get("timestamp")
        if ts is None:
            result.skipped_no_timestamp += 1
            continue
        result.total_boss_episodes += 1
        enemy_key = ep.get("enemy_key", "")
        character = ep.get("character", "")
        won = bool(ep.get("won"))
        guide = guides.get(_guide_lookup_key(enemy_key, character))
        bucket_name = "has_guide" if (guide and guide.first_available_at <= float(ts)) else "no_guide"
        bucket = getattr(result, bucket_name)
        bucket.n += 1
        if won:
            bucket.wins += 1
        # per-boss breakdown for caveat-5 visibility
        boss_key = normalize_enemy_key(enemy_key) or "unknown"
        per = result.per_boss.setdefault(boss_key, {"no_guide": Bucket(), "has_guide": Bucket()})
        per[bucket_name].n += 1
        if won:
            per[bucket_name].wins += 1
    return result


def discover_conditions(experiments_root: Path, tags: list[str] | None) -> list[tuple[str, str, Path]]:
    if not experiments_root.is_dir():
        return []
    out: list[tuple[str, str, Path]] = []
    for tag_dir in sorted(experiments_root.iterdir()):
        if not tag_dir.is_dir():
            continue
        if tags and tag_dir.name not in tags:
            continue
        for cond_dir in sorted(tag_dir.iterdir()):
            if cond_dir.is_dir():
                out.append((tag_dir.name, cond_dir.name, cond_dir))
    return out


def render_markdown(results: list[ConditionResult]) -> str:
    if not results:
        return "_No boss episodes found._\n"
    lines: list[str] = ["# Boss Winrate: No-Guide vs. Has-Guide", ""]
    lines.append("| Experiment | Condition | Source | Bucket | N | Wins | Winrate |")
    lines.append("|---|---|---|---|---:|---:|---:|")
    for r in results:
        for name, b in (("no_guide", r.no_guide), ("has_guide", r.has_guide)):
            wr = f"{b.winrate:.1%}" if b.n else "—"
            lines.append(
                f"| {r.experiment} | {r.condition} | {r.guide_source} | {name} | {b.n} | {b.wins} | {wr} |"
            )
    if any(r.guide_source == "guides_json_fallback" for r in results):
        lines.append("")
        lines.append(
            "> **Warning:** rows marked `guides_json_fallback` use `guides.json::created_at`, "
            "which is reset on every re-consolidation. has_guide counts will be biased low. "
            "Once `guide_consolidation_log.jsonl` accumulates enough rows, those experiments "
            "will switch to the reliable source."
        )
    lines.append("")
    lines.append("## Per-boss breakdown")
    lines.append("")
    lines.append("| Experiment | Condition | Boss | no_guide n/W | has_guide n/W |")
    lines.append("|---|---|---|---:|---:|")
    for r in results:
        for boss, buckets in sorted(r.per_boss.items()):
            ng, hg = buckets["no_guide"], buckets["has_guide"]
            ng_cell = f"{ng.n}/{ng.wins} ({ng.winrate:.0%})" if ng.n else "—"
            hg_cell = f"{hg.n}/{hg.wins} ({hg.winrate:.0%})" if hg.n else "—"
            lines.append(f"| {r.experiment} | {r.condition} | {boss} | {ng_cell} | {hg_cell} |")
    skipped = sum(r.skipped_no_timestamp for r in results)
    if skipped:
        lines.append("")
        lines.append(f"_Skipped {skipped} boss episodes with missing timestamp._")
    return "\n".join(lines) + "\n"


def render_json(results: list[ConditionResult]) -> str:
    payload = []
    for r in results:
        payload.append({
            "experiment": r.experiment,
            "condition": r.condition,
            "guide_source": r.guide_source,
            "no_guide": {"n": r.no_guide.n, "wins": r.no_guide.wins, "winrate": r.no_guide.winrate},
            "has_guide": {"n": r.has_guide.n, "wins": r.has_guide.wins, "winrate": r.has_guide.winrate},
            "per_boss": {
                boss: {
                    name: {"n": bucket.n, "wins": bucket.wins, "winrate": bucket.winrate}
                    for name, bucket in buckets.items()
                }
                for boss, buckets in r.per_boss.items()
            },
            "total_boss_episodes": r.total_boss_episodes,
            "skipped_no_timestamp": r.skipped_no_timestamp,
        })
    return json.dumps(payload, indent=2)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--tag", action="append", default=None, help="Experiment tag (repeatable). Default: all under experiments/.")
    p.add_argument("--experiments-root", type=Path, default=None, help="Override experiments/ root (default: <data_root>/experiments).")
    p.add_argument("--format", choices=("markdown", "json"), default="markdown")
    p.add_argument("--out", type=Path, default=None, help="Write to file instead of stdout.")
    args = p.parse_args(argv)

    root = args.experiments_root or (paths.data_root() / "experiments")
    conditions = discover_conditions(root, args.tag)
    if not conditions:
        print(f"No experiment conditions found under {root}", file=sys.stderr)
        return 1

    results = [analyze_condition(tag, cond, d) for tag, cond, d in conditions]
    text = render_json(results) if args.format == "json" else render_markdown(results)
    if args.out:
        args.out.write_text(text, encoding="utf-8")
        print(f"Wrote {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
