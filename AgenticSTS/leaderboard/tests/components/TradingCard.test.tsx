import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { TradingCard } from '@/components/hero/TradingCard'
import type { Submission } from '@/types/submission'

const fake: Submission = {
  id: 'test-sub',
  method: {
    name: 'HCM-Agent',
    version: 'v0.3',
    authors: ['Team'],
    description_short: 'Test.',
    relics: [],
  },
  model: { provider: 'google', name: 'Gemini 3.1 Pro', id: 'g' },
  character: 'Silent',
  runs: [{
    run_index: 1, ascension: 4, outcome: 'victory',
    final_floor: 50, final_act: 3, duration_seconds: 500, per_run_score: 450,
  }],
  aggregate: {
    ceiling: 4, ceiling_consistency: 0.33, progress_score_mean: 365,
    progress_score_max: 508, avg_final_floor: 35, max_final_floor: 50,
    total_runs: 1, total_victories: 1,
  },
  cost: {
    total_usd: 12.4, total_input_tokens: 1_800_000, total_output_tokens: 600_000,
    cost_per_run_usd: 1.24, cost_per_ascension_unlocked_usd: 3.1,
  },
  submitted_at: '2026-04-17T10:00:00Z',
  verified: true,
}

describe('TradingCard', () => {
  it('renders submission name and key stats', () => {
    render(<TradingCard submission={fake} medianCostUsd={20} />)
    expect(screen.getByText(/HCM-Agent/)).toBeInTheDocument()
    expect(screen.getByText(/Gemini 3.1 Pro/)).toBeInTheDocument()
    expect(screen.getAllByText(/A4/).length).toBeGreaterThan(0)
    expect(screen.getByText(/\$12.40/)).toBeInTheDocument()
  })
})
