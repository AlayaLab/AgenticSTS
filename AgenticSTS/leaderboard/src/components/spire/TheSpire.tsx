import type { Ascension, Submission } from '@/types/submission'
import { SpireTier } from './SpireTier'

const TIERS: { a: Ascension; label: string; isPeak?: boolean }[] = [
  { a: 5, label: "THE PEAK",         isPeak: true },
  { a: 4, label: "HEART OF THE SPIRE" },
  { a: 3, label: "CHAMPION'S GATE" },
  { a: 2, label: "COLOSSEUM" },
  { a: 1, label: "FIRST ELITE" },
  { a: 0, label: "EXORDIUM" },
]

export interface TheSpireProps {
  submissions: Submission[]
}

export function TheSpire({ submissions }: TheSpireProps) {
  const byCeiling = new Map<Ascension, Submission[]>()
  for (const tier of TIERS) byCeiling.set(tier.a, [])
  for (const s of submissions) {
    const list = byCeiling.get(s.aggregate.ceiling)
    if (list) list.push(s)
  }

  return (
    <section className="px-6 py-24">
      <h2 className="mb-12 text-center font-display text-4xl md:text-5xl">The Spire</h2>
      <p className="mx-auto mb-12 max-w-2xl text-center font-body text-[color:var(--color-ink-secondary)]">
        Each submission plants its flag at the highest ascension it has conquered.
        The peak awaits its first climber.
      </p>

      <div className="mx-auto max-w-5xl overflow-hidden rounded-xl border border-[color:var(--color-accent-gold)]/40 bg-[color:var(--color-bg-raised)]">
        {TIERS.map((tier, i) => (
          <SpireTier
            key={tier.a}
            ascension={tier.a}
            label={tier.label}
            isPeak={tier.isPeak}
            submissions={byCeiling.get(tier.a) ?? []}
            flagStartDelay={0.2 + i * 0.15}
          />
        ))}
      </div>
    </section>
  )
}
