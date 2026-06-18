import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { AgentDashboard } from './AgentDashboard'
import { AgentTabs, type AgentTab } from './components/AgentTabs'

const STORAGE_KEY = 'sts2_monitor_agents_v1'
const SCAN_PORT_START = 8081
const SCAN_PORT_END = 8099
const SCAN_TIMEOUT_MS = 500
const SCAN_INTERVAL_MS = 5000

function parseAgentsParam(raw: string | null): AgentTab[] | null {
  if (!raw) return null
  const parts = raw.split(',').map(s => s.trim()).filter(Boolean)
  const agents: AgentTab[] = []
  for (const p of parts) {
    const [labelPart, portPart] = p.includes(':') ? p.split(':') : ['', p]
    const port = Number(portPart)
    if (!Number.isInteger(port) || port <= 0 || port > 65535) continue
    agents.push({
      id: crypto.randomUUID(),
      label: labelPart.trim() || `:${port}`,
      port,
    })
  }
  return agents.length > 0 ? agents : null
}

function loadStoredAgents(): AgentTab[] {
  const urlAgents = parseAgentsParam(new URLSearchParams(window.location.search).get('agents'))
  if (urlAgents) return urlAgents
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) {
      const parsed = JSON.parse(raw) as AgentTab[]
      if (Array.isArray(parsed) && parsed.length > 0) return parsed
    }
  } catch {}
  return []
}

function buildUrls(port: number): { wsUrl: string; apiBase: string } {
  const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  const host = `${window.location.hostname}:${port}`
  return {
    wsUrl: `${wsProtocol}//${host}/ws/events`,
    apiBase: `http://${host}`,
  }
}

interface DiscoveredAgent {
  port: number
  label: string
  gamePort: number | null
  gamePid: number | null
}

// Probe a single port. Returns the agent info if the port hosts an STS2
// monitor (identified by the shape of /api/status), else null.
async function probePort(host: string, port: number): Promise<DiscoveredAgent | null> {
  const ctrl = new AbortController()
  const timer = setTimeout(() => ctrl.abort(), SCAN_TIMEOUT_MS)
  try {
    const resp = await fetch(`http://${host}:${port}/api/status`, { signal: ctrl.signal })
    if (!resp.ok) return null
    const data = await resp.json()
    // Schema check: distinguishes an STS2 monitor from unrelated services on
    // the same port range.
    if (typeof data?.agent_running !== 'boolean') return null
    const character = typeof data.character === 'string' && data.character ? data.character : null
    return {
      port,
      label: character ?? `:${port}`,
      gamePort: typeof data.game_port === 'number' ? data.game_port : null,
      gamePid: typeof data.game_pid === 'number' ? data.game_pid : null,
    }
  } catch {
    return null
  } finally {
    clearTimeout(timer)
  }
}

async function scanAgents(): Promise<DiscoveredAgent[]> {
  const host = window.location.hostname || 'localhost'
  const ports: number[] = []
  for (let p = SCAN_PORT_START; p <= SCAN_PORT_END; p++) ports.push(p)
  const results = await Promise.all(ports.map(p => probePort(host, p)))
  return results.filter((x): x is DiscoveredAgent => x !== null)
}

function App() {
  const [agents, setAgents] = useState<AgentTab[]>(loadStoredAgents)
  const [activeId, setActiveId] = useState<string>(() => agents[0]?.id ?? '')
  const [status, setStatus] = useState<Record<string, { connected: boolean; eventCount: number }>>({})
  const [scanning, setScanning] = useState(true)
  const didInitialScan = useRef(false)

  // Persist on any agent-list change so manually-added tabs survive reloads.
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(agents))
    } catch {}
  }, [agents])

  // Keep activeId pointing at a valid tab.
  useEffect(() => {
    if (agents.length === 0) {
      if (activeId !== '') setActiveId('')
    } else if (!agents.find(a => a.id === activeId)) {
      setActiveId(agents[0].id)
    }
  }, [agents, activeId])

  // Merge freshly-discovered agents into the tab list, deduping by port.
  // Existing tabs (manual or previously discovered) are preserved; we only
  // ever *add* on rescan so that a transient scan miss doesn't yank a tab.
  // game_pid / game_port on existing tabs get refreshed so they update once
  // the backend finishes launching the game.
  const mergeDiscoveries = useCallback((discovered: DiscoveredAgent[]) => {
    setAgents(prev => {
      const byPort = new Map<number, AgentTab>()
      for (const a of prev) byPort.set(a.port, a)
      let changed = false
      for (const d of discovered) {
        const existing = byPort.get(d.port)
        if (!existing) {
          byPort.set(d.port, {
            id: crypto.randomUUID(),
            label: d.label,
            port: d.port,
            gamePort: d.gamePort,
            gamePid: d.gamePid,
          })
          changed = true
        } else if (existing.gamePort !== d.gamePort || existing.gamePid !== d.gamePid) {
          byPort.set(d.port, { ...existing, gamePort: d.gamePort, gamePid: d.gamePid })
          changed = true
        }
      }
      if (!changed) return prev
      return Array.from(byPort.values()).sort((a, b) => a.port - b.port)
    })
  }, [])

  // Initial scan + periodic rescans.
  useEffect(() => {
    let cancelled = false
    const runScan = async () => {
      const discovered = await scanAgents()
      if (cancelled) return
      mergeDiscoveries(discovered)
      if (!didInitialScan.current) {
        didInitialScan.current = true
        setScanning(false)
      }
    }
    runScan()
    const timer = setInterval(runScan, SCAN_INTERVAL_MS)
    return () => {
      cancelled = true
      clearInterval(timer)
    }
  }, [mergeDiscoveries])

  const handleRemove = useCallback((id: string) => {
    setAgents(prev => prev.filter(a => a.id !== id))
    setStatus(prev => {
      const next = { ...prev }
      delete next[id]
      return next
    })
  }, [])

  const handleRename = useCallback((id: string, label: string) => {
    setAgents(prev => prev.map(a => (a.id === id ? { ...a, label } : a)))
  }, [])

  // Status callback factory — one stable function per agent id so downstream
  // effects don't re-fire every render.
  const statusCallbacks = useMemo(() => {
    const m = new Map<string, (connected: boolean, eventCount: number) => void>()
    for (const a of agents) {
      m.set(a.id, (connected, eventCount) => {
        setStatus(prev => {
          const cur = prev[a.id]
          if (cur && cur.connected === connected && cur.eventCount === eventCount) {
            return prev
          }
          return { ...prev, [a.id]: { connected, eventCount } }
        })
      })
    }
    return m
  }, [agents])

  return (
    <div className="h-screen flex flex-col bg-slate-900">
      <AgentTabs
        agents={agents}
        activeId={activeId}
        status={status}
        onSelect={setActiveId}
        onRemove={handleRemove}
        onRename={handleRename}
      />
      <div className="flex-1 relative min-h-0">
        {agents.length === 0 ? (
          <div className="absolute inset-0 flex items-center justify-center text-slate-400">
            <div className="text-center">
              <div className="text-lg mb-2">
                {scanning ? 'Detecting agents…' : 'No STS2 agents detected'}
              </div>
              <div className="text-sm text-slate-500">
                Scanning localhost ports {SCAN_PORT_START}–{SCAN_PORT_END} every 5 s.
                Start an agent with <code className="px-1 py-0.5 bg-slate-800 rounded">--launch-game</code>{' '}
                and it will appear automatically.
              </div>
            </div>
          </div>
        ) : (
          agents.map(a => {
            const { wsUrl, apiBase } = buildUrls(a.port)
            const isActive = a.id === activeId
            return (
              // Keep every dashboard mounted so its WebSocket stays live in
              // the background; just hide inactive ones with CSS.
              <div
                key={a.id}
                className="absolute inset-0 flex flex-col"
                style={{ display: isActive ? 'flex' : 'none' }}
              >
                <AgentDashboard
                  wsUrl={wsUrl}
                  apiBase={apiBase}
                  monitorPort={a.port}
                  gamePort={a.gamePort}
                  gamePid={a.gamePid}
                  onStatusChange={statusCallbacks.get(a.id)}
                />
              </div>
            )
          })
        )}
      </div>
    </div>
  )
}

export default App
