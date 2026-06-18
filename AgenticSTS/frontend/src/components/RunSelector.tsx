import type { RunInfo } from '../types/events'

interface Props {
  runs: RunInfo[]
  selectedRunId: string | null
  onSelectRun: (runId: string | null) => void
}

export function RunSelector({ runs, selectedRunId, onSelectRun }: Props) {
  if (runs.length === 0) return null

  return (
    <div className="flex items-center gap-2 px-4 py-1.5 bg-slate-800/30 border-b border-slate-700 overflow-x-auto">
      <span className="text-xs text-slate-500 shrink-0">Runs:</span>

      {/* All runs tab */}
      <RunTab
        label="All"
        active={selectedRunId === null}
        borderColor="#94a3b8"
        onClick={() => onSelectRun(null)}
      />

      {/* Per-run tabs */}
      {runs.map((run, i) => {
        const borderColor = run.outcome === 'victory'
          ? '#22c55e'
          : run.outcome === 'defeat'
            ? '#ef4444'
            : '#3b82f6'
        const label = `Run ${i + 1} (F${run.floor}${run.outcome ? ` ${run.outcome.toUpperCase()}` : '...'})`
        return (
          <RunTab
            key={run.runId}
            label={label}
            active={selectedRunId === run.runId}
            borderColor={borderColor}
            onClick={() => onSelectRun(run.runId)}
          />
        )
      })}
    </div>
  )
}

function RunTab({ label, active, borderColor, onClick }: {
  label: string
  active: boolean
  borderColor: string
  onClick: () => void
}) {
  return (
    <button
      onClick={onClick}
      className="px-2.5 py-1 rounded text-xs font-medium transition-colors cursor-pointer shrink-0"
      style={{
        backgroundColor: active ? `${borderColor}22` : 'transparent',
        color: active ? borderColor : '#64748b',
        border: `1px solid ${active ? borderColor : '#334155'}`,
      }}
    >
      {label}
    </button>
  )
}
