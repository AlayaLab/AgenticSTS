import type { EventType } from '../types/events'
import { EVENT_COLORS } from '../types/events'

export type ViewMode = 'timeline' | 'combat' | 'event' | 'shop_reward' | 'rest'
export type CombatTypeFilter = 'all' | 'monster' | 'elite_boss'
export type FilterKey = EventType | 'all' | 'postrun'

interface Props {
  activeFilters: Set<FilterKey>
  onToggleFilter: (filter: FilterKey) => void
  searchQuery: string
  onSearchChange: (q: string) => void
  onClear: () => void
  viewMode: ViewMode
  onViewModeChange: (mode: ViewMode) => void
  combatTypeFilter: CombatTypeFilter
  onCombatTypeFilterChange: (f: CombatTypeFilter) => void
}

const FILTER_BUTTONS: Array<{ key: FilterKey; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'llm_call', label: 'LLM' },
  { key: 'game_action', label: 'Actions' },
  { key: 'combat_plan', label: 'Combat' },
  { key: 'decision', label: 'Decisions' },
  { key: 'state', label: 'State' },
  { key: 'transition', label: 'Transitions' },
  { key: 'postrun', label: 'Postrun' },
  { key: 'error', label: 'Errors' },
]

const VIEW_MODES: Array<{ key: ViewMode; label: string }> = [
  { key: 'timeline', label: 'Timeline' },
  { key: 'combat', label: 'Combat' },
  { key: 'event', label: 'Event' },
  { key: 'shop_reward', label: 'Shop/Reward' },
  { key: 'rest', label: 'Rest' },
]

const COMBAT_FILTERS: Array<{ key: CombatTypeFilter; label: string }> = [
  { key: 'all', label: 'All' },
  { key: 'monster', label: 'Monster' },
  { key: 'elite_boss', label: 'Elite/Boss' },
]

export function FilterBar({
  activeFilters, onToggleFilter, searchQuery, onSearchChange, onClear,
  viewMode, onViewModeChange,
  combatTypeFilter, onCombatTypeFilterChange,
}: Props) {
  const showCombatSubFilter = viewMode === 'combat'
  const showTypeFilters = viewMode === 'timeline'

  return (
    <div className="flex items-center gap-2 px-4 py-2 bg-slate-800/50 border-b border-slate-700 flex-wrap">
      {/* View mode toggle */}
      <div className="flex rounded overflow-hidden border border-slate-600 mr-2">
        {VIEW_MODES.map(({ key, label }) => (
          <button
            key={key}
            onClick={() => onViewModeChange(key)}
            className="px-2 py-1 text-xs font-medium transition-colors cursor-pointer"
            style={{
              backgroundColor: viewMode === key ? '#3b82f633' : 'transparent',
              color: viewMode === key ? '#60a5fa' : '#64748b',
            }}
          >
            {label}
          </button>
        ))}
      </div>

      {/* Combat sub-filter (monster vs elite/boss) */}
      {showCombatSubFilter && (
        <div className="flex rounded overflow-hidden border border-slate-700 mr-2">
          {COMBAT_FILTERS.map(({ key, label }) => (
            <button
              key={key}
              onClick={() => onCombatTypeFilterChange(key)}
              className="px-2 py-1 text-xs font-medium transition-colors cursor-pointer"
              style={{
                backgroundColor: combatTypeFilter === key ? '#ef444433' : 'transparent',
                color: combatTypeFilter === key ? '#f87171' : '#64748b',
              }}
            >
              {label}
            </button>
          ))}
        </div>
      )}

      {/* Type filters (timeline only) */}
      {showTypeFilters && FILTER_BUTTONS.map(({ key, label }) => {
        const active = activeFilters.has(key)
        const color = key === 'all'
          ? '#94a3b8'
          : key === 'postrun'
            ? '#f59e0b'
            : EVENT_COLORS[key as EventType]
        return (
          <button
            key={key}
            onClick={() => onToggleFilter(key)}
            className="px-3 py-1 rounded text-xs font-medium transition-colors cursor-pointer"
            style={{
              backgroundColor: active ? `${color}33` : 'transparent',
              color: active ? color : '#64748b',
              border: `1px solid ${active ? color : '#334155'}`,
            }}
          >
            {label}
          </button>
        )
      })}

      <input
        type="text"
        value={searchQuery}
        onChange={e => onSearchChange(e.target.value)}
        placeholder="Search events..."
        className="ml-auto px-3 py-1 rounded bg-slate-900 border border-slate-700 text-sm text-slate-300 placeholder-slate-600 outline-none focus:border-slate-500 w-48"
      />

      <button
        onClick={onClear}
        className="px-3 py-1 rounded text-xs text-slate-500 border border-slate-700 hover:text-slate-300 hover:border-slate-500 transition-colors cursor-pointer"
      >
        Clear
      </button>
    </div>
  )
}
