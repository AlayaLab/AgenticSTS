import type { MonitorEvent, StateData, GamePhase } from '../types/events'
import { PHASE_COLORS, PHASE_LABELS } from '../types/events'

interface Props {
  connected: boolean
  events: MonitorEvent[]
  currentPhase: GamePhase
  selectedRunId: string | null
  monitorPort?: number
  gamePort?: number | null
  gamePid?: number | null
}

export function StatusBar({ connected, events, currentPhase, selectedRunId, monitorPort, gamePort, gamePid }: Props) {
  // Scope to selected run if one is chosen
  const scopedEvents = selectedRunId
    ? events.filter(e => e.run_id === selectedRunId)
    : events

  // Derive status from latest scoped events
  const latestState = findLast(scopedEvents, e => e.type === 'state')
  const stateData = latestState?.data as StateData | undefined

  const floor = stateData?.floor ?? '\u2014'
  const ascension = stateData?.ascension
  const combatPlayer = stateData?.combat?.player
  const nonCombatPlayer = stateData?.player
  const hp = combatPlayer?.hp ?? nonCombatPlayer?.hp ?? '\u2014'
  const maxHp = combatPlayer?.max_hp ?? nonCombatPlayer?.max_hp ?? '\u2014'
  const step = latestState?.step ?? '\u2014'

  // Use envelope run_id (not data.run_id which may be absent on run_end)
  const latestRunEvent = findLast(scopedEvents, e => e.type === 'run_start' || e.type === 'run_end')
  const runId = latestRunEvent?.run_id ?? undefined

  // Count LLM calls and total tokens (scoped). Split input/output when available;
  // fall back to combined `tokens` for legacy records without the split fields.
  const llmEvents = scopedEvents.filter(e => e.type === 'llm_call')
  const llmInputTokens = llmEvents.reduce((sum, e) => sum + ((e.data.input_tokens as number) || 0), 0)
  const llmOutputTokens = llmEvents.reduce((sum, e) => sum + ((e.data.output_tokens as number) || 0), 0)
  const llmSplitTotal = llmInputTokens + llmOutputTokens
  const llmCombinedTokens = llmEvents.reduce((sum, e) => sum + ((e.data.tokens as number) || 0), 0)
  const totalTokens = llmSplitTotal > 0 ? llmSplitTotal : llmCombinedTokens

  // Count post-run LLM calls and tokens (always split).  Includes both postrun_llm_call
  // (consolidation/distillation/discovery) and evolution_round (self-evolution) events.
  const postrunEvents = scopedEvents.filter(e => e.type === 'postrun_llm_call' || e.type === 'evolution_round')
  const postrunInputTokens = postrunEvents.reduce((sum, e) => sum + ((e.data.input_tokens as number) || 0), 0)
  const postrunOutputTokens = postrunEvents.reduce((sum, e) => sum + ((e.data.output_tokens as number) || 0), 0)
  const postrunTokens = postrunInputTokens + postrunOutputTokens

  const phaseColor = PHASE_COLORS[currentPhase]

  return (
    <div className="flex items-center gap-4 px-4 py-2 bg-slate-800 border-b border-slate-700 text-sm flex-wrap">
      <div className="flex items-center gap-1.5">
        <div
          className={`w-2 h-2 rounded-full ${connected ? 'bg-green-400' : 'bg-red-400'} ${connected ? 'animate-pulse' : ''}`}
        />
        <span className={connected ? 'text-green-400' : 'text-red-400'}>
          {connected ? 'Connected' : 'Disconnected'}
        </span>
      </div>

      {(monitorPort || gamePort || gamePid != null) && (
        <div className="flex items-center gap-2 text-xs text-slate-500 tabular-nums border-l border-slate-700 pl-3">
          {monitorPort != null && <span title="Monitor port">mon:{monitorPort}</span>}
          {gamePort != null && <span title="Game API port">game:{gamePort}</span>}
          {gamePid != null && <span title="Game process PID">pid:{gamePid}</span>}
        </div>
      )}

      {runId && <span className="text-slate-400">Run: <span className="text-slate-200">{runId}</span></span>}
      {ascension != null && <span className="text-amber-400 font-medium">A{ascension}</span>}
      <span className="text-slate-400">Floor: <span className="text-slate-200">{floor}</span></span>
      <span className="text-slate-400">HP: <span className="text-slate-200">{hp}/{maxHp}</span></span>

      {/* Phase badge */}
      <span
        className="text-xs font-bold px-1.5 py-0.5 rounded"
        style={{ color: phaseColor, backgroundColor: `${phaseColor}22` }}
      >
        {PHASE_LABELS[currentPhase]}
      </span>

      <span className="text-slate-400">Step: <span className="text-slate-200">{step}</span></span>

      <div className="ml-auto flex items-center gap-4">
        <span className="text-slate-400">LLM: <span className="text-blue-400">{llmEvents.length}</span></span>
        <span className="text-slate-400">Tokens: <span className="text-blue-400">{totalTokens.toLocaleString()}</span></span>
        {llmSplitTotal > 0 && (
          <span className="text-slate-500 text-xs">
            (In <span className="text-blue-300">{llmInputTokens.toLocaleString()}</span>
            {' '}/ Out <span className="text-blue-300">{llmOutputTokens.toLocaleString()}</span>)
          </span>
        )}
        {postrunEvents.length > 0 && (
          <>
            <span className="text-slate-600">|</span>
            <span className="text-slate-400">PostRun: <span className="text-amber-400">{postrunEvents.length}</span></span>
            <span className="text-slate-400">Tokens: <span className="text-amber-400">{postrunTokens.toLocaleString()}</span></span>
            {postrunTokens > 0 && (
              <span className="text-slate-500 text-xs">
                (In <span className="text-amber-300">{postrunInputTokens.toLocaleString()}</span>
                {' '}/ Out <span className="text-amber-300">{postrunOutputTokens.toLocaleString()}</span>)
              </span>
            )}
          </>
        )}
      </div>
    </div>
  )
}

/** Find last element matching predicate (Array.findLast not available in all targets). */
function findLast<T>(arr: T[], pred: (item: T) => boolean): T | undefined {
  for (let i = arr.length - 1; i >= 0; i--) {
    if (pred(arr[i])) return arr[i]
  }
  return undefined
}
