import type { Submission } from '@/types/submission'
import { RunStrip } from '@/components/shared/RunStrip'
import clsx from 'clsx'

const PROVIDER_EMOJI: Record<Submission['model']['provider'], string> = {
  google: '💠', openai: '⚡', anthropic: '✶', qwen: '◈', other: '◉',
}

export interface LeaderboardTableProps {
  submissions: Submission[]
}

function rankMedal(rank: number): string {
  if (rank === 1) return '🏆'
  if (rank === 2) return '🥈'
  if (rank === 3) return '🥉'
  return String(rank)
}

export function LeaderboardTable({ submissions }: LeaderboardTableProps) {
  const ranked = [...submissions].sort((a, b) => {
    if (b.aggregate.ceiling !== a.aggregate.ceiling) return b.aggregate.ceiling - a.aggregate.ceiling
    return b.aggregate.progress_score_mean - a.aggregate.progress_score_mean
  })

  return (
    <div className="overflow-x-auto rounded-lg border border-[color:var(--color-ink-secondary)]/20">
      <table className="w-full min-w-[960px] text-left">
        <thead className="bg-[color:var(--color-bg-raised)] font-pixel text-[9px] uppercase tracking-wider">
          <tr>
            <th className="px-4 py-3">Rank</th>
            <th className="px-4 py-3">Submission</th>
            <th className="px-4 py-3">Model</th>
            <th className="px-4 py-3">Char</th>
            <th className="px-4 py-3">Ceiling</th>
            <th className="px-4 py-3">Score</th>
            <th className="px-4 py-3">Cost</th>
            <th className="px-4 py-3">Runs (10)</th>
          </tr>
        </thead>
        <tbody className="font-mono text-sm">
          {ranked.map((s, i) => (
            <tr
              key={s.id}
              className={clsx(
                'border-t border-[color:var(--color-ink-secondary)]/10 transition',
                'hover:bg-[color:var(--color-bg-raised)]',
              )}
            >
              <td className="px-4 py-3 text-2xl">{rankMedal(i + 1)}</td>
              <td className="px-4 py-3">
                <div className="font-display text-base leading-tight">
                  {s.method.name} {s.method.version}
                </div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  by {s.method.authors.join(', ')}
                </div>
              </td>
              <td className="px-4 py-3">
                <span className="mr-2">{PROVIDER_EMOJI[s.model.provider]}</span>
                {s.model.name}
              </td>
              <td className="px-4 py-3">{s.character}</td>
              <td className="px-4 py-3">
                <div className="font-pixel text-xs text-[color:var(--color-accent-gold)]">A{s.aggregate.ceiling}</div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  {s.aggregate.total_victories}/{s.aggregate.total_runs} ✓
                </div>
              </td>
              <td className="px-4 py-3">{s.aggregate.progress_score_mean.toFixed(0)}</td>
              <td className="px-4 py-3">
                <div>${s.cost.total_usd.toFixed(2)}</div>
                <div className="text-xs text-[color:var(--color-ink-secondary)]">
                  ${s.cost.cost_per_ascension_unlocked_usd.toFixed(2)}/A
                </div>
              </td>
              <td className="px-4 py-3">
                <RunStrip runs={s.runs} />
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
