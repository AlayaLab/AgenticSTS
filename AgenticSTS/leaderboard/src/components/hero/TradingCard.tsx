import type { Submission } from '@/types/submission'
import { RarityBorder } from '@/components/shared/RarityBorder'
import { RunStrip } from '@/components/shared/RunStrip'
import { PotionGauge } from '@/components/shared/PotionGauge'
import { motion } from 'motion/react'
import { useReducedMotion } from '@/hooks/useReducedMotion'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠',
  openai: '⚡',
  anthropic: '✶',
  qwen: '◈',
  other: '◉',
}

function flavorText(sub: Submission): string {
  const { ceiling, total_victories } = sub.aggregate
  if (ceiling === 5) return '"Peak of the Spire beckons."'
  if (ceiling === 4) return '"Conquered the Heart — almost."'
  if (ceiling === 3) return '"A steady climber."'
  if (ceiling === 2) return '"Knows the early floors."'
  if (ceiling === 1) return '"Breached the colosseum."'
  if (total_victories > 0) return '"Survived the tutorial."'
  return '"The Spire endures."'
}

function Stars({ ceiling }: { ceiling: number }) {
  const filled = ceiling
  return (
    <span className="font-mono text-sm tracking-wider">
      {'★'.repeat(filled)}{'☆'.repeat(5 - filled)}
    </span>
  )
}

export interface TradingCardProps {
  submission: Submission
  medianCostUsd: number
  delay?: number
}

export function TradingCard({ submission, medianCostUsd, delay = 0 }: TradingCardProps) {
  const { method, model, aggregate, cost } = submission
  const reduced = useReducedMotion()

  return (
    <motion.div
      initial={reduced ? false : { opacity: 0, y: 40, rotateY: 30 }}
      animate={{ opacity: 1, y: 0, rotateY: 0 }}
      transition={{ duration: reduced ? 0 : 0.6, delay: reduced ? 0 : delay, ease: [0.22, 1, 0.36, 1] }}
      whileHover={reduced ? undefined : { y: -8, rotateY: 4, rotateX: -2 }}
      style={{ perspective: 1000 }}
      className="w-[280px] shrink-0"
    >
      <RarityBorder ceiling={aggregate.ceiling} className="bg-[color:var(--color-bg-raised)] p-4">
        <div className="mt-3 flex h-44 items-center justify-center rounded-lg bg-gradient-to-br from-[color:var(--color-bg-base)] to-[color:var(--color-bg-raised)] text-6xl">
          {PROVIDER_EMOJI[model.provider]}
        </div>

        <div className="mt-3">
          <h3 className="font-display text-lg leading-tight">
            {method.name} <span className="text-[color:var(--color-ink-secondary)]">{method.version}</span>
          </h3>
          <p className="font-body text-sm text-[color:var(--color-ink-secondary)]">{model.name}</p>
        </div>

        <dl className="mt-3 space-y-1 text-sm">
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">CEILING</dt>
            <dd>A{aggregate.ceiling} <Stars ceiling={aggregate.ceiling} /></dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">SCORE</dt>
            <dd>{aggregate.progress_score_mean.toFixed(0)} / 600</dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">COST</dt>
            <dd>${cost.total_usd.toFixed(2)}</dd>
          </div>
          <div className="flex justify-between font-mono">
            <dt className="text-[color:var(--color-ink-secondary)]">$/A</dt>
            <dd>${cost.cost_per_ascension_unlocked_usd.toFixed(2)}</dd>
          </div>
        </dl>

        <div className="mt-3 flex justify-center">
          <PotionGauge costUsd={cost.total_usd} medianUsd={medianCostUsd} />
        </div>

        <div className="mt-3">
          <RunStrip runs={submission.runs} />
        </div>

        <p className="mt-3 italic font-body text-xs text-center text-[color:var(--color-ink-secondary)]">
          {flavorText(submission)}
        </p>
      </RarityBorder>
    </motion.div>
  )
}
