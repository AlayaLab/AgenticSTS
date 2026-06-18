import { describe, it, expect } from 'vitest'
import {
  perRunScore,
  ceiling,
  consistencyAtCeiling,
  aggregateFromRuns,
  filterScorableRuns,
} from '@/data/scoring'
import type { RunSummary } from '@/types/submission'

function mk(overrides: Partial<RunSummary>): RunSummary {
  return {
    run_index: 1,
    ascension: 0,
    outcome: 'defeat',
    final_floor: 10,
    final_act: 1,
    duration_seconds: 100,
    per_run_score: 0,
    ...overrides,
  }
}

describe('perRunScore', () => {
  it('A0 defeat f12 = 12', () => {
    expect(perRunScore(mk({ ascension: 0, outcome: 'defeat', final_floor: 12 }))).toBe(12)
  })
  it('A0 victory = 50', () => {
    expect(perRunScore(mk({ ascension: 0, outcome: 'victory', final_floor: 50 }))).toBe(50)
  })
  it('A4 victory = 450', () => {
    expect(perRunScore(mk({ ascension: 4, outcome: 'victory', final_floor: 50 }))).toBe(450)
  })
  it('A5 defeat f8 = 508 (higher than A4 victory 450)', () => {
    const a5 = perRunScore(mk({ ascension: 5, outcome: 'defeat', final_floor: 8 }))
    const a4v = perRunScore(mk({ ascension: 4, outcome: 'victory', final_floor: 50 }))
    expect(a5).toBe(508)
    expect(a5).toBeGreaterThan(a4v)
  })
  it('abort returns 0 (excluded from scoring)', () => {
    expect(perRunScore(mk({ ascension: 3, outcome: 'abort', final_floor: 22 }))).toBe(0)
  })
})

describe('filterScorableRuns', () => {
  it('excludes aborts', () => {
    const runs = [
      mk({ outcome: 'victory' }),
      mk({ outcome: 'defeat' }),
      mk({ outcome: 'abort' }),
    ]
    expect(filterScorableRuns(runs).length).toBe(2)
  })
})

describe('ceiling', () => {
  it('returns 0 when no victories', () => {
    expect(ceiling([mk({ ascension: 3, outcome: 'defeat' })])).toBe(0)
  })
  it('returns highest A with victory', () => {
    const runs = [
      mk({ ascension: 0, outcome: 'victory' }),
      mk({ ascension: 2, outcome: 'victory' }),
      mk({ ascension: 3, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 5, outcome: 'defeat' }),
    ]
    expect(ceiling(runs)).toBe(4)
  })
  it('ignores aborts', () => {
    expect(ceiling([mk({ ascension: 4, outcome: 'abort' })])).toBe(0)
  })
})

describe('consistencyAtCeiling', () => {
  it('0 if no attempts at that ceiling', () => {
    expect(consistencyAtCeiling([mk({ ascension: 2, outcome: 'victory' })], 4)).toBe(0)
  })
  it('fraction of victories among attempts at that A', () => {
    const runs = [
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 4, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'defeat' }),
      mk({ ascension: 4, outcome: 'victory' }),
      mk({ ascension: 4, outcome: 'defeat' }),
    ]
    expect(consistencyAtCeiling(runs, 4)).toBeCloseTo(0.4)
  })
})

describe('aggregateFromRuns', () => {
  it('computes all fields, ignoring aborts', () => {
    const runs = [
      mk({ ascension: 0, outcome: 'victory', final_floor: 50 }),   // score 50
      mk({ ascension: 1, outcome: 'victory', final_floor: 50 }),   // 150
      mk({ ascension: 2, outcome: 'defeat', final_floor: 34 }),    // 234
      mk({ ascension: 3, outcome: 'abort', final_floor: 1 }),      // excluded
    ]
    const agg = aggregateFromRuns(runs)
    expect(agg.ceiling).toBe(1)
    expect(agg.total_runs).toBe(3)
    expect(agg.total_victories).toBe(2)
    expect(agg.progress_score_max).toBe(234)
    expect(agg.progress_score_mean).toBeCloseTo((50 + 150 + 234) / 3)
    expect(agg.avg_final_floor).toBeCloseTo((50 + 50 + 34) / 3)
    expect(agg.max_final_floor).toBe(50)
  })
})
