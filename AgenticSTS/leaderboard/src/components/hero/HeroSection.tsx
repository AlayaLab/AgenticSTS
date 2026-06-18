import type { Submission } from '@/types/submission'
import { TradingCard } from './TradingCard'
import { HeroHeadline } from './HeroHeadline'

export interface HeroSectionProps {
  submissions: Submission[]
}

function median(xs: number[]): number {
  if (xs.length === 0) return 1
  const s = [...xs].sort((a, b) => a - b)
  const mid = Math.floor(s.length / 2)
  return s.length % 2 === 0 ? (s[mid - 1] + s[mid]) / 2 : s[mid]
}

function rankedTop3(subs: Submission[]): Submission[] {
  return [...subs]
    .sort((a, b) => {
      if (b.aggregate.ceiling !== a.aggregate.ceiling) return b.aggregate.ceiling - a.aggregate.ceiling
      return b.aggregate.progress_score_mean - a.aggregate.progress_score_mean
    })
    .slice(0, 3)
}

export function HeroSection({ submissions }: HeroSectionProps) {
  const top3 = rankedTop3(submissions)
  const medianCost = median(submissions.map((s) => s.cost.total_usd))

  return (
    <section className="px-6 pb-24 pt-16 md:pt-32">
      <HeroHeadline />
      <div className="mx-auto mt-16 flex max-w-6xl flex-wrap justify-center gap-8">
        {top3.map((s, i) => (
          <TradingCard key={s.id} submission={s} medianCostUsd={medianCost} delay={1.2 + i * 0.2} />
        ))}
      </div>
    </section>
  )
}
