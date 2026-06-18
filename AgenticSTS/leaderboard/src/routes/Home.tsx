import { useEffect, useState } from 'react'
import { HeroSection } from '@/components/hero/HeroSection'
import { TheSpire } from '@/components/spire/TheSpire'
import { CeilingCostScatter } from '@/components/scatter/CeilingCostScatter'
import { LeaderboardSection } from '@/components/leaderboard/LeaderboardSection'
import { loadSubmissions } from '@/data/loadSubmissions'
import type { SubmissionBundle } from '@/types/submission'

export function Home() {
  const [bundle, setBundle] = useState<SubmissionBundle | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadSubmissions().then(setBundle).catch((e) => setError(String(e)))
  }, [])

  if (error) {
    return <p className="p-16 text-center text-[color:var(--color-danger)]">Error: {error}</p>
  }
  if (!bundle) {
    return <p className="p-16 text-center font-body">Loading the Spire…</p>
  }

  return (
    <>
      <HeroSection submissions={bundle.submissions} />
      <div id="spire"><TheSpire submissions={bundle.submissions} /></div>
      <CeilingCostScatter submissions={bundle.submissions} />
      <div id="leaderboard"><LeaderboardSection submissions={bundle.submissions} /></div>
    </>
  )
}
