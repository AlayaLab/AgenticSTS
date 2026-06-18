import clsx from 'clsx'

export interface PotionGaugeProps {
  /** Cost in USD for this submission. */
  costUsd: number
  /** Median cost across all submissions (for relative scaling). */
  medianUsd: number
}

/** 3 bottles = cheaper than half of median, 2 = roughly median, 1 = far above */
function bottlesFor(costUsd: number, medianUsd: number): 1 | 2 | 3 {
  const ratio = costUsd / medianUsd
  if (ratio <= 0.5) return 3
  if (ratio <= 1.5) return 2
  return 1
}

function Bottle({ filled }: { filled: boolean }) {
  return (
    <svg viewBox="0 0 16 24" width="16" height="24" aria-hidden="true">
      <rect x="6" y="1" width="4" height="3" rx="1" fill="currentColor" opacity="0.6" />
      <rect x="5" y="4" width="6" height="2" fill="currentColor" opacity="0.4" />
      <path
        d="M 4 6 L 12 6 L 13 10 Q 14 14 13 18 Q 12 22 8 22 Q 4 22 3 18 Q 2 14 3 10 Z"
        fill={filled ? 'currentColor' : 'none'}
        stroke="currentColor"
        strokeWidth="1"
      />
    </svg>
  )
}

export function PotionGauge({ costUsd, medianUsd }: PotionGaugeProps) {
  const filled = bottlesFor(costUsd, medianUsd)
  return (
    <div
      aria-label={`Cost efficiency: ${filled} / 3 potions`}
      className={clsx('inline-flex gap-0.5', {
        'text-[color:var(--color-success)]': filled === 3,
        'text-[color:var(--color-accent-gold)]': filled === 2,
        'text-[color:var(--color-danger)]': filled === 1,
      })}
    >
      {[0, 1, 2].map((i) => (
        <Bottle key={i} filled={i < filled} />
      ))}
    </div>
  )
}
