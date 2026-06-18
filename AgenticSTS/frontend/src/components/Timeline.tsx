import { useRef, useCallback, useState } from 'react'
import { Virtuoso, type VirtuosoHandle } from 'react-virtuoso'
import type { MonitorEvent, GamePhase } from '../types/events'
import { EventCard } from './EventCard'

interface Props {
  events: MonitorEvent[]
  phaseMap: Map<string, GamePhase>
  summaries: Map<string, string>
}

export function Timeline({ events, phaseMap, summaries }: Props) {
  const virtuosoRef = useRef<VirtuosoHandle>(null)
  const [atBottom, setAtBottom] = useState(true)
  const [showJumpButton, setShowJumpButton] = useState(false)

  const handleAtBottomChange = useCallback((bottom: boolean) => {
    setAtBottom(bottom)
    if (bottom) setShowJumpButton(false)
  }, [])

  // Show "new events" button when not at bottom and new events arrive
  const prevCountRef = useRef(events.length)
  if (events.length > prevCountRef.current && !atBottom) {
    if (!showJumpButton) setShowJumpButton(true)
  }
  prevCountRef.current = events.length

  const jumpToBottom = useCallback(() => {
    virtuosoRef.current?.scrollToIndex({ index: events.length - 1, behavior: 'smooth' })
    setShowJumpButton(false)
  }, [events.length])

  if (events.length === 0) {
    return (
      <div className="flex-1 flex items-center justify-center text-slate-600">
        <div className="text-center">
          <div className="text-4xl mb-3">🎮</div>
          <div className="text-lg">Waiting for events...</div>
          <div className="text-sm mt-1">Start the agent with STS2_MONITOR_ENABLED=true</div>
        </div>
      </div>
    )
  }

  return (
    <div className="flex-1 relative">
      <Virtuoso
        ref={virtuosoRef}
        data={events}
        itemContent={(_index, event) => (
          <EventCard
            event={event}
            phase={phaseMap.get(event.id)}
            summary={summaries.get(event.id)}
          />
        )}
        followOutput="smooth"
        atBottomStateChange={handleAtBottomChange}
        atBottomThreshold={100}
        overscan={200}
      />

      {showJumpButton && (
        <button
          onClick={jumpToBottom}
          className="absolute bottom-4 left-1/2 -translate-x-1/2 px-4 py-2 bg-blue-600 text-white rounded-full text-sm shadow-lg hover:bg-blue-500 transition-colors cursor-pointer animate-bounce"
        >
          New events ↓
        </button>
      )}
    </div>
  )
}
