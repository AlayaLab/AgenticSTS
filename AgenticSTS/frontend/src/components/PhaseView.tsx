import { useState } from 'react'
import type { GamePhase, PhaseEncounter } from '../types/events'
import { PHASE_COLORS } from '../types/events'
import { EventCard } from './EventCard'

interface Props {
  encounters: PhaseEncounter[]
  summaries: Map<string, string>
  phaseMap: Map<string, GamePhase>
  emptyLabel: string
  emptyIcon?: string
}

const KIND_LABEL: Record<PhaseEncounter['kind'], string> = {
  event: 'Event',
  shop: 'Shop',
  card_reward: 'Card Reward',
  rest: 'Rest',
}

const KIND_ICON: Record<PhaseEncounter['kind'], string> = {
  event: '❓',
  shop: '\u{1F6D2}',
  card_reward: '\u{1F381}',
  rest: '\u{1F525}',
}

const KIND_TO_PHASE: Record<PhaseEncounter['kind'], GamePhase> = {
  event: 'event',
  shop: 'shop',
  card_reward: 'card_reward',
  rest: 'rest',
}

export function PhaseView({ encounters, summaries, phaseMap, emptyLabel, emptyIcon = '\u{1F4DC}' }: Props) {
  if (encounters.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600">
        <div className="text-center">
          <div className="text-4xl mb-3">{emptyIcon}</div>
          <div className="text-lg">{emptyLabel}</div>
          <div className="text-sm mt-1">Encounters will appear here as they occur</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {encounters.map((enc, i) => (
        <PhaseCard
          key={enc.id}
          encounter={enc}
          index={i}
          summaries={summaries}
          phaseMap={phaseMap}
        />
      ))}
    </div>
  )
}

function PhaseCard({ encounter, index, summaries, phaseMap }: {
  encounter: PhaseEncounter
  index: number
  summaries: Map<string, string>
  phaseMap: Map<string, GamePhase>
}) {
  const [expanded, setExpanded] = useState(false)
  const phase = KIND_TO_PHASE[encounter.kind]
  const color = PHASE_COLORS[phase]
  const label = KIND_LABEL[encounter.kind]
  const icon = KIND_ICON[encounter.kind]
  const hpDelta = encounter.hpBefore != null && encounter.hpAfter != null
    ? encounter.hpAfter - encounter.hpBefore
    : null
  const hpColor = hpDelta == null
    ? 'text-slate-500'
    : hpDelta < 0 ? 'text-red-400' : hpDelta > 0 ? 'text-green-400' : 'text-slate-500'

  return (
    <div className="border-b border-slate-700">
      <div
        className="px-4 py-3 bg-slate-800/50 hover:bg-slate-800/70 cursor-pointer flex items-center gap-3 transition-colors"
        style={{ borderLeft: `3px solid ${color}` }}
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-sm font-medium text-slate-200">
          {icon} {label} #{index + 1}
          {encounter.title && <span className="text-slate-400 ml-2">{encounter.title}</span>}
        </span>
        <span className="text-xs text-slate-500">Floor {encounter.floor}</span>
        <span className="text-xs text-slate-500">{encounter.events.length} events</span>
        {hpDelta != null && (
          <span className={`text-xs ${hpColor}`}>
            HP {encounter.hpBefore} &rarr; {encounter.hpAfter} ({hpDelta >= 0 ? '+' : ''}{hpDelta})
          </span>
        )}
        <span className="ml-auto text-slate-600 text-xs">{expanded ? '−' : '+'}</span>
      </div>

      {!expanded && encounter.decision && (
        <div className="px-4 py-1.5 text-xs text-slate-400">
          <span className="text-slate-500">decision: </span>
          <span className="text-purple-300">{encounter.decision}</span>
        </div>
      )}

      {expanded && (
        <div className="divide-y divide-slate-800/50">
          {encounter.events.map(event => (
            <EventCard
              key={event.id}
              event={event}
              phase={phaseMap.get(event.id)}
              summary={summaries.get(event.id)}
            />
          ))}
        </div>
      )}
    </div>
  )
}
