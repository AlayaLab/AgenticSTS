import { useMemo, useState } from 'react'
import type { Submission } from '@/types/submission'
import { LeaderboardTable } from './LeaderboardTable'
import { LeaderboardTabs, type LeaderboardTab } from './LeaderboardTabs'

export interface LeaderboardSectionProps {
  submissions: Submission[]
}

const OUR_METHOD_NAME = 'HCM-Agent'

function filterForTab(subs: Submission[], tab: LeaderboardTab): Submission[] {
  if (tab === 'models') {
    // Models view: fix method = ours, compare LLMs
    return subs.filter((s) => s.method.name === OUR_METHOD_NAME)
  }
  // Methods view (default): everyone
  // Characters view: disabled in MVP, never reaches here
  return subs
}

export function LeaderboardSection({ submissions }: LeaderboardSectionProps) {
  const [tab, setTab] = useState<LeaderboardTab>('methods')
  const filtered = useMemo(() => filterForTab(submissions, tab), [submissions, tab])

  const helpText =
    tab === 'methods' ? 'Every method × model × character submission, sorted by ceiling.' :
    tab === 'models'  ? `Head-to-head comparison of LLMs running the ${OUR_METHOD_NAME} pipeline.` :
                        ''

  return (
    <section className="px-6 py-24">
      <h2 className="mb-8 text-center font-display text-4xl md:text-5xl">Leaderboard</h2>
      <div className="mx-auto max-w-6xl">
        <LeaderboardTabs active={tab} onChange={setTab} />
        <p className="mt-4 font-body text-sm text-[color:var(--color-ink-secondary)]">{helpText}</p>
        <div className="mt-6">
          <LeaderboardTable submissions={filtered} />
        </div>
      </div>
    </section>
  )
}
