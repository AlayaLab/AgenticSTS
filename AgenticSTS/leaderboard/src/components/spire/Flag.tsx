import clsx from 'clsx'
import type { Submission } from '@/types/submission'
import { motion } from 'motion/react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠',
  openai: '⚡',
  anthropic: '✶',
  qwen: '◈',
  other: '◉',
}

const CEILING_GLOW: Record<number, string> = {
  0: 'shadow-[0_0_8px_rgba(176,168,158,0.5)]',
  1: 'shadow-[0_0_12px_rgba(95,168,211,0.6)]',
  2: 'shadow-[0_0_16px_rgba(155,89,182,0.6)]',
  3: 'shadow-[0_0_20px_rgba(230,126,34,0.7)]',
  4: 'shadow-[0_0_28px_rgba(244,196,48,0.8)]',
  5: 'shadow-[0_0_32px_rgba(236,72,153,0.9)]',
}

export interface FlagProps {
  submission: Submission
  delay?: number
}

export function Flag({ submission, delay = 0 }: FlagProps) {
  const { method, model, aggregate } = submission
  const reduced = useReducedMotion()

  return (
    <motion.div
      initial={reduced ? false : { y: 120, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      transition={{ duration: reduced ? 0 : 0.9, delay: reduced ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduced ? undefined : { y: -6, scale: 1.05 }}
      className="group relative flex flex-col items-center"
    >
      <div
        className={clsx(
          'flex h-12 w-12 items-center justify-center rounded-full border-2 border-[color:var(--color-accent-gold)] bg-[color:var(--color-bg-raised)] text-2xl',
          CEILING_GLOW[aggregate.ceiling],
        )}
      >
        {PROVIDER_EMOJI[model.provider]}
      </div>
      <div className="mt-1 max-w-[90px] truncate rounded bg-[color:var(--color-bg-raised)] px-2 py-0.5 font-pixel text-[7px] text-[color:var(--color-ink-primary)]">
        {method.name}
      </div>
      <div className="pointer-events-none absolute left-full top-0 ml-4 hidden w-56 rounded-lg border border-[color:var(--color-ink-secondary)] bg-[color:var(--color-bg-raised)] p-3 shadow-xl group-hover:block">
        <p className="font-display text-sm">{method.name} {method.version}</p>
        <p className="font-body text-xs text-[color:var(--color-ink-secondary)]">{model.name}</p>
        <p className="mt-2 font-mono text-xs">
          Ceiling A{aggregate.ceiling} · {(aggregate.ceiling_consistency * 100).toFixed(0)}% consistent
        </p>
        <p className="font-mono text-xs">Score {aggregate.progress_score_mean.toFixed(0)}</p>
      </div>
    </motion.div>
  )
}
