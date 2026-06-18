import type { Aggregate, Ascension, RunSummary } from '@/types/submission'

/**
 * Per-run progress score.
 *
 * Formula: ascension * 100 + (50 if victory else final_floor)
 *
 * Reasoning: Each ascension tier is worth 100 "progress units" (since reaching
 * A_n requires having beaten A_(n-1)). Victory is worth +50, equivalent to
 * completing the ~50-floor tower. Aborts are excluded (return 0).
 */
export function perRunScore(run: RunSummary): number {
  if (run.outcome === 'abort') return 0
  return run.ascension * 100 + (run.outcome === 'victory' ? 50 : run.final_floor)
}

/** Filter out aborts — they don't count toward any aggregate statistic. */
export function filterScorableRuns(runs: readonly RunSummary[]): RunSummary[] {
  return runs.filter((r) => r.outcome !== 'abort')
}

/** Highest ascension with at least one victory. Returns 0 if no victories. */
export function ceiling(runs: readonly RunSummary[]): Ascension {
  const victories = runs.filter((r) => r.outcome === 'victory')
  if (victories.length === 0) return 0
  const maxA = Math.max(...victories.map((r) => r.ascension))
  return maxA as Ascension
}

/** Win rate among runs that attempted the given ascension. 0 if no attempts. */
export function consistencyAtCeiling(runs: readonly RunSummary[], c: Ascension): number {
  const attempts = runs.filter((r) => r.ascension === c && r.outcome !== 'abort')
  if (attempts.length === 0) return 0
  const wins = attempts.filter((r) => r.outcome === 'victory').length
  return wins / attempts.length
}

/** Compute all aggregate stats for a submission from its runs. */
export function aggregateFromRuns(runs: readonly RunSummary[]): Aggregate {
  const scorable = filterScorableRuns(runs)
  const scores = scorable.map(perRunScore)
  const floors = scorable.map((r) => r.final_floor)
  const c = ceiling(scorable)

  const mean = (xs: number[]) => (xs.length === 0 ? 0 : xs.reduce((a, b) => a + b, 0) / xs.length)
  const max = (xs: number[]) => (xs.length === 0 ? 0 : Math.max(...xs))

  return {
    ceiling: c,
    ceiling_consistency: consistencyAtCeiling(scorable, c),
    progress_score_mean: mean(scores),
    progress_score_max: max(scores),
    avg_final_floor: mean(floors),
    max_final_floor: max(floors),
    total_runs: scorable.length,
    total_victories: scorable.filter((r) => r.outcome === 'victory').length,
  }
}
