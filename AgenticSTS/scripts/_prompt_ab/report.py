"""Aggregate A/B run results into a Markdown + JSON report."""
from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from statistics import mean


@dataclass
class SampleResult:
    """Aggregate per-sample outcome (after L1 + L2)."""
    run_id: str
    log_path: str
    line_index: int
    a_decisions: list[int | None]
    b_decisions: list[int | None]
    a_malformed: int
    b_malformed: int
    judge_winner: str = ""  # "A", "B", "tie", "" if not judged
    judge_score_a_total: int = 0
    judge_score_b_total: int = 0
    judge_rationale: str = ""


@dataclass
class ReportSummary:
    n_samples: int
    n_disagreements: int
    a_malformed_rate: float
    b_malformed_rate: float
    judge_a_wins: int
    judge_b_wins: int
    judge_ties: int
    judge_a_mean_total: float
    judge_b_mean_total: float
    pass_verdict: str
    notes: list[str] = field(default_factory=list)


def _decision_disagrees(a: list[int | None], b: list[int | None]) -> bool:
    """Two versions disagree if their MOST-COMMON option_index differs.

    None values are excluded; if either is all-None, treat as disagreement.
    """
    a_clean = [x for x in a if x is not None]
    b_clean = [x for x in b if x is not None]
    if not a_clean or not b_clean:
        return True
    a_top = max(set(a_clean), key=a_clean.count)
    b_top = max(set(b_clean), key=b_clean.count)
    return a_top != b_top


def _score_total(score: dict[str, int]) -> int:
    if not score:
        return 0
    return sum(int(score.get(k, 0)) for k in ("soundness", "coverage", "coherence", "risk_awareness"))


def summarize(samples: Iterable[SampleResult]) -> ReportSummary:
    samples = list(samples)
    n = len(samples)
    disagreements = sum(1 for s in samples if _decision_disagrees(s.a_decisions, s.b_decisions))

    total_a_attempts = sum(len(s.a_decisions) for s in samples)
    total_b_attempts = sum(len(s.b_decisions) for s in samples)
    a_malformed = sum(s.a_malformed for s in samples) / max(total_a_attempts, 1)
    b_malformed = sum(s.b_malformed for s in samples) / max(total_b_attempts, 1)

    judged = [s for s in samples if s.judge_winner in ("A", "B", "tie")]
    a_wins = sum(1 for s in judged if s.judge_winner == "A")
    b_wins = sum(1 for s in judged if s.judge_winner == "B")
    ties = sum(1 for s in judged if s.judge_winner == "tie")

    judge_a_total_mean = mean([s.judge_score_a_total for s in judged]) if judged else 0.0
    judge_b_total_mean = mean([s.judge_score_b_total for s in judged]) if judged else 0.0

    notes: list[str] = []
    pass_verdict = "INCONCLUSIVE"

    if b_malformed - a_malformed > 0.10:
        pass_verdict = "REJECT"
        notes.append(
            f"B malformed-rate +{(b_malformed - a_malformed) * 100:.1f}pp vs A "
            "— rejection threshold is 10pp"
        )
    elif judge_b_total_mean + 1.0 < judge_a_total_mean and judged:
        pass_verdict = "REJECT"
        notes.append(
            f"B mean total score {judge_b_total_mean:.2f} < A "
            f"{judge_a_total_mean:.2f} by >1 point"
        )
    elif disagreements / max(n, 1) < 0.20 and n > 0:
        pass_verdict = "QUALITY-NEUTRAL"
        notes.append(
            f"A/B agree on {(1 - disagreements / n) * 100:.0f}% of samples "
            "— change is essentially silent"
        )
    elif b_wins + a_wins == 0:
        pass_verdict = "INCONCLUSIVE"
        notes.append("no judge verdicts available")
    else:
        b_win_rate = b_wins / max(b_wins + a_wins, 1)
        if b_win_rate >= 0.55 and (b_wins + a_wins) >= 15:
            pass_verdict = "PASS"
            notes.append(
                f"B wins {b_wins}/{b_wins + a_wins} non-tie disagreements "
                f"({b_win_rate:.2f})"
            )
        elif b_win_rate <= 0.45:
            pass_verdict = "REJECT"
            notes.append(f"B loses majority of disagreements: {b_win_rate:.2f}")
        else:
            pass_verdict = "MIXED"
            notes.append(
                f"B win rate {b_win_rate:.2f} on {b_wins + a_wins} disagreements "
                "— borderline"
            )

    return ReportSummary(
        n_samples=n,
        n_disagreements=disagreements,
        a_malformed_rate=a_malformed,
        b_malformed_rate=b_malformed,
        judge_a_wins=a_wins,
        judge_b_wins=b_wins,
        judge_ties=ties,
        judge_a_mean_total=judge_a_total_mean,
        judge_b_mean_total=judge_b_total_mean,
        pass_verdict=pass_verdict,
        notes=notes,
    )


def write_report(
    *,
    out_dir: Path,
    samples: list[SampleResult],
    summary: ReportSummary,
    timestamp: str,
) -> tuple[Path, Path]:
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"prompt_ab_b1_{timestamp}.json"
    md_path = out_dir / f"prompt_ab_b1_{timestamp}.md"

    json_path.write_text(
        json.dumps(
            {"summary": asdict(summary), "samples": [asdict(s) for s in samples]},
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    lines = [
        f"# Prompt Reorder B1 — A/B Report ({timestamp})",
        "",
        f"**Verdict: {summary.pass_verdict}**",
        "",
        "## Summary",
        f"- Samples: {summary.n_samples}",
        f"- Disagreements (top-of-3 differs): {summary.n_disagreements}",
        f"- Malformed rate — A: {summary.a_malformed_rate:.2%}, "
        f"B: {summary.b_malformed_rate:.2%}",
        f"- Judge wins — A: {summary.judge_a_wins}, "
        f"B: {summary.judge_b_wins}, tie: {summary.judge_ties}",
        f"- Judge mean score (out of 20) — A: {summary.judge_a_mean_total:.2f}, "
        f"B: {summary.judge_b_mean_total:.2f}",
        "",
        "## Notes",
    ]
    for n in summary.notes:
        lines.append(f"- {n}")
    md_path.write_text("\n".join(lines), encoding="utf-8")

    return json_path, md_path
