import { describe, it, expect } from 'vitest'
import { render } from '@testing-library/react'
import { RunStrip } from '@/components/shared/RunStrip'
import type { RunSummary } from '@/types/submission'

const mkRuns = (n: number): RunSummary[] =>
  Array.from({ length: n }, (_, i) => ({
    run_index: i + 1,
    ascension: 0,
    outcome: 'defeat',
    final_floor: 10,
    final_act: 1,
    duration_seconds: 100,
    per_run_score: 10,
  }))

describe('RunStrip', () => {
  it('renders N pills for N runs', () => {
    const { container } = render(<RunStrip runs={mkRuns(10)} />)
    const pills = container.querySelectorAll('[title]')
    expect(pills.length).toBe(10)
  })
})
