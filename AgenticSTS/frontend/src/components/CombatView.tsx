import { useState } from 'react'
import type { CombatEncounter, CombatRound } from '../types/events'
import { EventCard } from './EventCard'
import type { GamePhase } from '../types/events'

interface Props {
  encounters: CombatEncounter[]
  summaries: Map<string, string>
  phaseMap: Map<string, GamePhase>
}

export function CombatView({ encounters, summaries, phaseMap }: Props) {
  if (encounters.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600">
        <div className="text-center">
          <div className="text-4xl mb-3">&#x2694;</div>
          <div className="text-lg">No combat encounters yet</div>
          <div className="text-sm mt-1">Combat events will be grouped here as they occur</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 overflow-y-auto">
      {encounters.map((encounter, i) => (
        <EncounterCard
          key={encounter.id}
          encounter={encounter}
          index={i}
          summaries={summaries}
          phaseMap={phaseMap}
        />
      ))}
    </div>
  )
}

function EncounterCard({ encounter, index, summaries, phaseMap }: {
  encounter: CombatEncounter
  index: number
  summaries: Map<string, string>
  phaseMap: Map<string, GamePhase>
}) {
  const [expanded, setExpanded] = useState(false)
  const outcomeColor = encounter.outcome === 'victory'
    ? 'text-green-400'
    : encounter.outcome === 'defeat'
      ? 'text-red-400'
      : 'text-blue-400'
  const outcomeLabel = encounter.outcome
    ? encounter.outcome.toUpperCase()
    : 'IN PROGRESS'

  // Total HP delta \u2014 prefer combatSummary, fall back to scanning rounds.
  let hpBefore: number | undefined
  let hpAfter: number | undefined
  if (encounter.combatSummary) {
    hpBefore = encounter.combatSummary.hp_before
    hpAfter = encounter.combatSummary.hp_after
  } else {
    hpBefore = encounter.rounds[0]?.hpBefore
    for (let i = encounter.rounds.length - 1; i >= 0; i--) {
      const v = encounter.rounds[i].hpAfter
      if (v != null) { hpAfter = v; break }
    }
  }
  const hpDelta = hpBefore != null && hpAfter != null ? hpAfter - hpBefore : null
  const hpDeltaColor = hpDelta == null
    ? 'text-slate-500'
    : hpDelta < 0 ? 'text-red-400' : hpDelta > 0 ? 'text-green-400' : 'text-slate-500'
  const ctLabel = encounter.combatType === 'elite'
    ? 'ELITE'
    : encounter.combatType === 'boss'
      ? 'BOSS'
      : null

  return (
    <div className="border-b border-slate-700">
      {/* Encounter header */}
      <div
        className="px-4 py-3 bg-slate-800/50 hover:bg-slate-800/70 cursor-pointer flex items-center gap-3 transition-colors"
        style={{ borderLeft: '3px solid #ef4444' }}
        onClick={() => setExpanded(!expanded)}
      >
        <span className="text-sm font-medium text-slate-200">
          &#x2694; Combat #{index + 1}: {encounter.enemyNames}
        </span>
        {ctLabel && (
          <span className="text-xs font-bold text-orange-400">[{ctLabel}]</span>
        )}
        <span className="text-xs text-slate-500">Floor {encounter.floor}</span>
        <span className="text-xs text-slate-500">{encounter.rounds.length}R</span>
        <span className={`text-xs font-bold ${outcomeColor}`}>{outcomeLabel}</span>
        {hpBefore != null && hpAfter != null && (
          <span className="text-xs text-slate-500">
            HP {hpBefore} &rarr; {hpAfter}
            {hpDelta != null && (
              <span className={`ml-1 ${hpDeltaColor}`}>
                ({hpDelta >= 0 ? '+' : ''}{hpDelta})
              </span>
            )}
          </span>
        )}
        {encounter.cardReward && (
          <span className="text-xs text-blue-300">
            \ud83c\udf81 {encounter.cardReward}
          </span>
        )}
        <span className="ml-auto text-slate-600 text-xs">{expanded ? '\u2212' : '+'}</span>
      </div>

      {/* Rounds */}
      {!expanded && (
        <div className="px-4 py-1.5 space-y-0.5">
          {encounter.rounds.map(round => (
            <RoundSummary key={round.roundNumber} round={round} />
          ))}
        </div>
      )}

      {/* Expanded: show all raw events per round */}
      {expanded && (
        <div className="divide-y divide-slate-800/50">
          {encounter.rounds.map(round => (
            <div key={round.roundNumber}>
              <div className="px-4 py-1 bg-slate-900/50 text-xs text-slate-500 font-medium">
                Round {round.roundNumber}
                {round.hpBefore != null && round.hpAfter != null && (
                  <span className="ml-2">
                    HP: {round.hpBefore} &rarr; {round.hpAfter}
                    {' '}({round.hpAfter - round.hpBefore >= 0 ? '+' : ''}{round.hpAfter - round.hpBefore})
                  </span>
                )}
              </div>
              {round.events.map(event => (
                <EventCard
                  key={event.id}
                  event={event}
                  phase={phaseMap.get(event.id)}
                  summary={summaries.get(event.id)}
                />
              ))}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}

function RoundSummary({ round }: { round: CombatRound }) {
  const hpDelta = round.hpBefore != null && round.hpAfter != null
    ? round.hpAfter - round.hpBefore
    : null
  const hpColor = hpDelta != null
    ? hpDelta < 0 ? 'text-red-400' : hpDelta > 0 ? 'text-green-400' : 'text-slate-500'
    : 'text-slate-500'

  return (
    <div className="text-xs text-slate-400 flex items-center gap-2">
      <span className="text-slate-500 w-8">R{round.roundNumber}</span>
      {round.planSummary && (
        <span className="text-cyan-400">{round.planSummary}</span>
      )}
      {!round.planSummary && round.actions.length > 0 && (
        <span className="text-orange-300">{round.actions.join(' \u2192 ')}</span>
      )}
      {hpDelta != null && (
        <span className={hpColor}>{hpDelta >= 0 ? '+' : ''}{hpDelta} HP</span>
      )}
    </div>
  )
}
