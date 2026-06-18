import clsx from 'clsx'
import type { RunSummary } from '@/types/submission'

const RARITY_BG: Record<number, string> = {
  0: 'bg-[color:var(--color-rarity-common)]',
  1: 'bg-[color:var(--color-rarity-uncommon)]',
  2: 'bg-[color:var(--color-rarity-rare)]',
  3: 'bg-[color:var(--color-rarity-elite)]',
  4: 'bg-gradient-to-br from-[color:var(--color-rarity-legendary-from)] to-[color:var(--color-rarity-legendary-to)]',
  5: 'bg-gradient-to-br from-fuchsia-500 via-yellow-400 to-cyan-400 animate-pulse',
}

function saturationClass(outcome: RunSummary['outcome'], finalAct: RunSummary['final_act']): string {
  if (outcome === 'victory') return 'opacity-100 ring-2 ring-[color:var(--color-accent-gold)]'
  if (outcome === 'abort') return 'opacity-30 border border-dashed border-[color:var(--color-ink-secondary)]'
  // defeat: saturation by act
  if (finalAct === 3) return 'opacity-80'
  if (finalAct === 2) return 'opacity-55'
  return 'opacity-30'
}

export interface RunPillProps {
  run: RunSummary
  onMouseEnter?: () => void
}

export function RunPill({ run, onMouseEnter }: RunPillProps) {
  const label =
    run.outcome === 'victory' ? '✓' :
    run.outcome === 'abort' ? '—' :
    String(run.final_floor)

  const title =
    run.outcome === 'victory' ? `A${run.ascension} Victory — Run ${run.run_index}` :
    run.outcome === 'abort'   ? `A${run.ascension} Aborted — Run ${run.run_index}` :
                                `A${run.ascension}, died floor ${run.final_floor}` +
                                (run.death_cause ? ` (${run.death_cause})` : '') +
                                ` — Run ${run.run_index}`

  return (
    <div
      onMouseEnter={onMouseEnter}
      title={title}
      className={clsx(
        'inline-flex h-7 w-9 flex-col items-center justify-center rounded text-center transition-transform hover:scale-110',
        RARITY_BG[run.ascension],
        saturationClass(run.outcome, run.final_act),
      )}
    >
      <span className="font-pixel text-[8px] leading-none text-white drop-shadow">A{run.ascension}</span>
      <span className="font-mono text-[10px] leading-none text-white drop-shadow">{label}</span>
    </div>
  )
}
