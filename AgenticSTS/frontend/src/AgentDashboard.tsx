import { useEffect, useMemo, useState, useCallback } from 'react'
import type { EventType, GamePhase, RunInfo, StateData, TransitionData, RunEndData } from './types/events'
import { useEventStream } from './hooks/useEventStream'
import { StatusBar } from './components/StatusBar'
import { FilterBar, type ViewMode, type FilterKey, type CombatTypeFilter } from './components/FilterBar'
import { RunSelector } from './components/RunSelector'
import { Timeline } from './components/Timeline'
import { CombatView } from './components/CombatView'
import { PhaseView } from './components/PhaseView'
import { stateTypeToPhase } from './utils/formatters'
import { groupCombatEncounters } from './utils/combatGrouper'
import { groupPhaseEncounters, getPhaseConfig } from './utils/phaseGrouper'

const LLM_TIMELINE_TYPES: EventType[] = [
  'llm_call',
  'llm_request_start',
  'llm_first_chunk',
  'llm_request_end',
]

const POSTRUN_EVENT_TYPES: EventType[] = [
  'postrun_llm_call',
  'post_run_start',
  'post_run_stage',
  'post_run_end',
  'evolution_round',
  'evolution_summary',
  'postrun_artifact',
]

export interface AgentDashboardProps {
  wsUrl: string
  apiBase: string
  monitorPort?: number
  gamePort?: number | null
  gamePid?: number | null
  onStatusChange?: (connected: boolean, eventCount: number) => void
}

export function AgentDashboard({ wsUrl, apiBase, monitorPort, gamePort, gamePid, onStatusChange }: AgentDashboardProps) {
  const { events, summaries, connected, clearEvents } = useEventStream(wsUrl, apiBase)
  const [activeFilters, setActiveFilters] = useState<Set<FilterKey>>(new Set(['all']))
  const [searchQuery, setSearchQuery] = useState('')
  const [selectedRunId, setSelectedRunId] = useState<string | null>(null)
  const [viewMode, setViewMode] = useState<ViewMode>('timeline')
  const [combatTypeFilter, setCombatTypeFilter] = useState<CombatTypeFilter>('all')

  useEffect(() => {
    onStatusChange?.(connected, events.length)
  }, [connected, events.length, onStatusChange])

  const runs = useMemo<RunInfo[]>(() => {
    const result: RunInfo[] = []
    for (const event of events) {
      if (event.type === 'run_start' && event.run_id) {
        result.push({ runId: event.run_id, floor: 0, ended: false })
      }
      if (event.type === 'state') {
        const sd = event.data as unknown as StateData
        if (sd.floor && result.length > 0) {
          result[result.length - 1].floor = sd.floor
        }
      }
      if (event.type === 'run_end' && result.length > 0) {
        const rd = event.data as unknown as RunEndData
        const run = result[result.length - 1]
        run.ended = true
        run.outcome = rd.victory ? 'victory' : 'defeat'
        run.fitness = rd.fitness
        if (rd.ascension != null) run.ascension = rd.ascension
        if (rd.floor) run.floor = rd.floor
      }
    }
    return result
  }, [events])

  const { phaseMap, currentPhase } = useMemo(() => {
    const map = new Map<string, GamePhase>()
    let phase: GamePhase = 'other'

    for (const event of events) {
      if (event.type === 'state') {
        const sd = event.data as unknown as StateData
        if (sd.state_type) phase = stateTypeToPhase(sd.state_type)
      } else if (event.type === 'transition') {
        const td = event.data as unknown as TransitionData
        if (td.state_type) phase = stateTypeToPhase(td.state_type)
      }
      map.set(event.id, phase)
    }

    return { phaseMap: map, currentPhase: phase }
  }, [events])

  const handleToggleFilter = useCallback((filter: FilterKey) => {
    setActiveFilters(prev => {
      const next = new Set(prev)
      if (filter === 'all') {
        return new Set(['all'])
      }
      next.delete('all')
      if (next.has(filter)) {
        next.delete(filter)
        if (next.size === 0) next.add('all')
      } else {
        next.add(filter)
      }
      return next
    })
  }, [])

  const runScopedEvents = useMemo(() => {
    let result = events

    if (selectedRunId) {
      result = result.filter(e => e.run_id === selectedRunId)
    }

    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase()
      result = result.filter(e =>
        JSON.stringify(e.data).toLowerCase().includes(q)
        || e.type.toLowerCase().includes(q),
      )
    }

    return result
  }, [events, searchQuery, selectedRunId])

  const filteredEvents = useMemo(() => {
    if (activeFilters.has('all')) return runScopedEvents
    const allowedTypes = new Set<string>(activeFilters as Set<string>)
    if (activeFilters.has('llm_call')) {
      for (const type of LLM_TIMELINE_TYPES) {
        allowedTypes.add(type)
      }
    }
    if (activeFilters.has('postrun')) {
      allowedTypes.delete('postrun')
      for (const type of POSTRUN_EVENT_TYPES) {
        allowedTypes.add(type)
      }
    }
    return runScopedEvents.filter(e => allowedTypes.has(e.type))
  }, [runScopedEvents, activeFilters])

  const encounters = useMemo(() => {
    if (viewMode !== 'combat') return []
    const all = groupCombatEncounters(runScopedEvents)
    if (combatTypeFilter === 'all') return all
    if (combatTypeFilter === 'monster') return all.filter(e => e.combatType === 'monster')
    return all.filter(e => e.combatType === 'elite' || e.combatType === 'boss')
  }, [runScopedEvents, viewMode, combatTypeFilter])

  const phaseEncounters = useMemo(() => {
    const cfg = getPhaseConfig(viewMode)
    if (!cfg) return []
    return groupPhaseEncounters(runScopedEvents, cfg.primaryStates)
  }, [runScopedEvents, viewMode])

  return (
    <div className="flex-1 flex flex-col min-h-0 bg-slate-900">
      <StatusBar
        connected={connected}
        events={events}
        currentPhase={currentPhase}
        selectedRunId={selectedRunId}
        monitorPort={monitorPort}
        gamePort={gamePort}
        gamePid={gamePid}
      />
      <RunSelector runs={runs} selectedRunId={selectedRunId} onSelectRun={setSelectedRunId} />
      <FilterBar
        activeFilters={activeFilters}
        onToggleFilter={handleToggleFilter}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onClear={clearEvents}
        viewMode={viewMode}
        onViewModeChange={setViewMode}
        combatTypeFilter={combatTypeFilter}
        onCombatTypeFilterChange={setCombatTypeFilter}
      />
      {viewMode === 'timeline' && (
        <Timeline events={filteredEvents} phaseMap={phaseMap} summaries={summaries} />
      )}
      {viewMode === 'combat' && (
        <CombatView encounters={encounters} summaries={summaries} phaseMap={phaseMap} />
      )}
      {viewMode === 'event' && (
        <PhaseView
          encounters={phaseEncounters}
          summaries={summaries}
          phaseMap={phaseMap}
          emptyLabel="No events yet"
          emptyIcon="❓"
        />
      )}
      {viewMode === 'shop_reward' && (
        <PhaseView
          encounters={phaseEncounters}
          summaries={summaries}
          phaseMap={phaseMap}
          emptyLabel="No shops or rewards yet"
          emptyIcon="\u{1F381}"
        />
      )}
      {viewMode === 'rest' && (
        <PhaseView
          encounters={phaseEncounters}
          summaries={summaries}
          phaseMap={phaseMap}
          emptyLabel="No rest sites yet"
          emptyIcon="\u{1F525}"
        />
      )}
    </div>
  )
}
