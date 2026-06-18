import { useState } from 'react'

export interface AgentTab {
  id: string
  label: string
  port: number
  gamePort?: number | null
  gamePid?: number | null
}

export interface AgentTabsProps {
  agents: AgentTab[]
  activeId: string
  status: Record<string, { connected: boolean; eventCount: number }>
  onSelect: (id: string) => void
  onRemove: (id: string) => void
  onRename: (id: string, label: string) => void
}

export function AgentTabs({ agents, activeId, status, onSelect, onRemove, onRename }: AgentTabsProps) {
  const [renamingId, setRenamingId] = useState<string | null>(null)
  const [renameValue, setRenameValue] = useState('')

  const submitRename = () => {
    if (renamingId && renameValue.trim()) {
      onRename(renamingId, renameValue.trim())
    }
    setRenamingId(null)
    setRenameValue('')
  }

  return (
    <div className="flex items-stretch bg-slate-800 border-b border-slate-700 overflow-x-auto">
      {agents.map(a => {
        const s = status[a.id] ?? { connected: false, eventCount: 0 }
        const isActive = a.id === activeId
        const isRenaming = renamingId === a.id
        return (
          <div
            key={a.id}
            className={`group flex items-center gap-2 px-4 py-2 border-r border-slate-700 cursor-pointer min-w-0 ${
              isActive ? 'bg-slate-900 text-white' : 'text-slate-400 hover:bg-slate-700/60 hover:text-white'
            }`}
            onClick={() => !isRenaming && onSelect(a.id)}
          >
            <span className={s.connected ? 'text-emerald-400' : 'text-red-400'} title={s.connected ? 'connected' : 'disconnected'}>●</span>
            {isRenaming ? (
              <input
                autoFocus
                className="bg-slate-950 text-white px-1 py-0.5 text-sm w-28 border border-slate-600 rounded outline-none"
                value={renameValue}
                onChange={e => setRenameValue(e.target.value)}
                onBlur={submitRename}
                onKeyDown={e => {
                  if (e.key === 'Enter') submitRename()
                  else if (e.key === 'Escape') { setRenamingId(null); setRenameValue('') }
                }}
                onClick={e => e.stopPropagation()}
              />
            ) : (
              <span
                className="truncate max-w-[12rem]"
                onDoubleClick={e => { e.stopPropagation(); setRenamingId(a.id); setRenameValue(a.label) }}
                title="Double-click to rename"
              >
                {a.label}
              </span>
            )}
            {a.gamePid != null ? (
              <span className="text-xs text-slate-500 tabular-nums" title={`Game PID · mon:${a.port}${a.gamePort ? ` game:${a.gamePort}` : ''}`}>
                pid:{a.gamePid}
              </span>
            ) : (
              <span className="text-xs text-slate-600 tabular-nums" title={`Monitor port${a.gamePort ? ` · game:${a.gamePort}` : ''}`}>
                :{a.port}
              </span>
            )}
            <span className="text-xs text-slate-600 tabular-nums ml-1" title="Event count">{s.eventCount}</span>
            {!isRenaming && (
              <button
                className="ml-1 text-slate-500 hover:text-red-400 opacity-0 group-hover:opacity-100 transition"
                onClick={e => { e.stopPropagation(); onRemove(a.id) }}
                title="Remove tab"
              >
                ×
              </button>
            )}
          </div>
        )
      })}
    </div>
  )
}
