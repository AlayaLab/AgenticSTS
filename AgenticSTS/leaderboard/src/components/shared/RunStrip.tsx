import type { RunSummary } from '@/types/submission'
import { RunPill } from './RunPill'

export interface RunStripProps {
  runs: RunSummary[]
}

export function RunStrip({ runs }: RunStripProps) {
  return (
    <div className="flex flex-wrap gap-1">
      {runs.map((r) => (
        <RunPill key={r.run_index} run={r} />
      ))}
    </div>
  )
}
