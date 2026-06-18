import { useCallback, useEffect, useRef, useState } from 'react'
import type { MonitorEvent, AiSummaryData } from '../types/events'

interface UseEventStreamReturn {
  events: MonitorEvent[]
  summaries: Map<string, string>
  connected: boolean
  clearEvents: () => void
}

export function useEventStream(wsUrl: string, apiBase: string): UseEventStreamReturn {
  const [events, setEvents] = useState<MonitorEvent[]>([])
  const [summaries, setSummaries] = useState<Map<string, string>>(new Map())
  const [connected, setConnected] = useState(false)
  const seenIds = useRef(new Set<string>())
  const lastSeenId = useRef<string | null>(null)
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>(undefined)
  const reconnectDelay = useRef(1000)

  const addEvent = useCallback((event: MonitorEvent) => {
    if (seenIds.current.has(event.id)) return
    seenIds.current.add(event.id)
    lastSeenId.current = event.id

    // Intercept ai_summary: store in summaries map, don't add to timeline
    if (event.type === 'ai_summary') {
      const data = event.data as unknown as AiSummaryData
      if (data.parent_id && data.summary) {
        setSummaries(prev => {
          const next = new Map(prev)
          next.set(data.parent_id, data.summary)
          return next
        })
      }
      return
    }

    setEvents(prev => [...prev, event])
  }, [])

  const connect = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return

    const ws = new WebSocket(wsUrl)
    wsRef.current = ws

    ws.onopen = () => {
      setConnected(true)
      reconnectDelay.current = 1000

      // Catch up via history endpoint using stable ref
      const afterId = lastSeenId.current
      const historyUrl = afterId
        ? `${apiBase}/api/events/history?after_id=${afterId}`
        : `${apiBase}/api/events/history`

      fetch(historyUrl)
        .then(r => r.json())
        .then((history: MonitorEvent[]) => {
          for (const e of history) addEvent(e)
        })
        .catch(() => {})
    }

    ws.onmessage = (msg) => {
      try {
        const event: MonitorEvent = JSON.parse(msg.data)
        addEvent(event)
      } catch {
        // Ignore malformed messages
      }
    }

    ws.onclose = () => {
      setConnected(false)
      wsRef.current = null
      // Exponential backoff reconnect
      reconnectTimer.current = setTimeout(() => {
        reconnectDelay.current = Math.min(reconnectDelay.current * 2, 30000)
        connect()
      }, reconnectDelay.current)
    }

    ws.onerror = () => {
      ws.close()
    }
  }, [wsUrl, apiBase, addEvent])

  useEffect(() => {
    connect()
    return () => {
      clearTimeout(reconnectTimer.current)
      wsRef.current?.close()
    }
  }, [connect])

  const clearEvents = useCallback(() => {
    setEvents([])
    setSummaries(new Map())
    seenIds.current.clear()
    lastSeenId.current = null
  }, [])

  return { events, summaries, connected, clearEvents }
}
