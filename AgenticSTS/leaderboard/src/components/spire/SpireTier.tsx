import clsx from 'clsx'
import type { Ascension, Submission } from '@/types/submission'
import { Flag } from './Flag'

export interface SpireTierProps {
  ascension: Ascension
  label: string
  submissions: Submission[]   // submissions whose ceiling === this tier's ascension
  isPeak?: boolean            // A5 — always fog-covered in v1
  flagStartDelay?: number
}

const TIER_BG: Record<Ascension, string> = {
  0: 'from-stone-200/40 to-stone-100/20',
  1: 'from-sky-300/30 to-sky-100/10',
  2: 'from-purple-400/30 to-purple-200/10',
  3: 'from-orange-400/30 to-orange-200/10',
  4: 'from-red-500/40 via-amber-400/30 to-amber-200/10',
  5: 'from-fuchsia-500/30 via-yellow-400/20 to-cyan-300/10',
}

export function SpireTier({
  ascension,
  label,
  submissions,
  isPeak = false,
  flagStartDelay = 0,
}: SpireTierProps) {
  return (
    <div className="relative flex min-h-[108px] items-center gap-4 border-b border-[color:var(--color-accent-gold)]/30">
      <div className="w-28 shrink-0 py-4 pr-2 text-right">
        <div className="font-pixel text-[9px] text-[color:var(--color-accent-gold)]">A{ascension}</div>
        <div className="font-display text-sm leading-tight">{label}</div>
      </div>

      <div className={clsx('relative flex flex-1 flex-wrap items-center gap-3 rounded-r-lg bg-gradient-to-r px-6 py-4', TIER_BG[ascension])}>
        {isPeak && (
          <div className="absolute inset-0 flex items-center justify-center rounded-r-lg bg-[color:var(--color-bg-base)]/70 backdrop-blur-sm">
            <span className="font-display text-xl tracking-widest text-[color:var(--color-ink-secondary)]">??? The Peak ???</span>
          </div>
        )}
        {!isPeak && submissions.length === 0 && (
          <span className="font-body text-sm italic text-[color:var(--color-ink-secondary)]">— no climbers yet —</span>
        )}
        {!isPeak && submissions.map((s, i) => (
          <Flag key={s.id} submission={s} delay={flagStartDelay + i * 0.12} />
        ))}
      </div>
    </div>
  )
}
