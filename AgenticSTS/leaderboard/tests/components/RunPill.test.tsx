import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { RunPill } from '@/components/shared/RunPill'
import type { RunSummary } from '@/types/submission'

const mk = (overrides: Partial<RunSummary>): RunSummary => ({
  run_index: 1,
  ascension: 0,
  outcome: 'defeat',
  final_floor: 10,
  final_act: 1,
  duration_seconds: 100,
  per_run_score: 0,
  ...overrides,
})

describe('RunPill', () => {
  it('shows A4 and checkmark for A4 victory', () => {
    render(<RunPill run={mk({ ascension: 4, outcome: 'victory', final_floor: 50, final_act: 3 })} />)
    expect(screen.getByText(/A4/)).toBeInTheDocument()
    expect(screen.getByText(/✓/)).toBeInTheDocument()
  })

  it('shows A2 and floor number for A2 defeat on floor 28', () => {
    render(<RunPill run={mk({ ascension: 2, outcome: 'defeat', final_floor: 28, final_act: 2 })} />)
    expect(screen.getByText(/A2/)).toBeInTheDocument()
    expect(screen.getByText(/28/)).toBeInTheDocument()
  })

  it('shows "—" for abort', () => {
    render(<RunPill run={mk({ ascension: 3, outcome: 'abort' })} />)
    expect(screen.getByText(/A3/)).toBeInTheDocument()
    expect(screen.getByText(/—/)).toBeInTheDocument()
  })
})
