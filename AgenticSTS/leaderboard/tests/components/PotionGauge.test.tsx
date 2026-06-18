import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { PotionGauge } from '@/components/shared/PotionGauge'

describe('PotionGauge', () => {
  it('shows 3 full bottles for cheapest (well below median)', () => {
    render(<PotionGauge costUsd={4} medianUsd={20} />)
    expect(screen.getByLabelText(/3 \/ 3/)).toBeInTheDocument()
  })

  it('shows 2 bottles for around-median', () => {
    render(<PotionGauge costUsd={20} medianUsd={20} />)
    expect(screen.getByLabelText(/2 \/ 3/)).toBeInTheDocument()
  })

  it('shows 1 bottle for far above median', () => {
    render(<PotionGauge costUsd={80} medianUsd={20} />)
    expect(screen.getByLabelText(/1 \/ 3/)).toBeInTheDocument()
  })
})
