import { useState } from 'react'
import type {
  MonitorEvent, LlmCallData, LlmRequestStartData, LlmFirstChunkData, LlmRequestEndData,
  GameActionData, ActionResultData,
  StateData, TransitionData, CombatPlanData, CombatSummaryData,
  ContextAssemblyData, ToolCallData, ToolPreprocessingData,
  DecisionData, RunEndData, ErrorData, GamePhase,
} from '../types/events'
import { EVENT_COLORS, EVENT_LABELS, PHASE_COLORS } from '../types/events'
import { formatTimestamp, formatLatency, formatTokens, truncate } from '../utils/formatters'

interface Props {
  event: MonitorEvent
  phase?: GamePhase
  summary?: string
}

export function EventCard({ event, phase, summary }: Props) {
  const [expanded, setExpanded] = useState(false)
  const color = EVENT_COLORS[event.type] || '#64748b'
  const borderColor = phase ? PHASE_COLORS[phase] : undefined

  return (
    <div
      className="px-4 py-2 border-b border-slate-800 hover:bg-slate-800/30 transition-colors"
      style={borderColor ? { borderLeft: `3px solid ${borderColor}` } : undefined}
    >
      {/* Clickable header — only this row toggles expand/collapse */}
      <div
        className="flex items-start gap-3 cursor-pointer"
        onClick={() => setExpanded(!expanded)}
      >
        {/* Timestamp */}
        <span className="text-xs text-slate-500 font-mono w-16 shrink-0 pt-0.5">
          {formatTimestamp(event.timestamp)}
        </span>

        {/* Type badge */}
        <span
          className="text-xs font-bold px-1.5 py-0.5 rounded shrink-0"
          style={{ color, backgroundColor: `${color}22` }}
        >
          {EVENT_LABELS[event.type] || event.type.toUpperCase()}
        </span>

        {/* Summary */}
        <div className="flex-1 min-w-0 text-sm">
          <Summary event={event} />
        </div>

        {/* Expand indicator */}
        <span className="text-slate-600 text-xs shrink-0 pt-0.5">
          {expanded ? '\u2212' : '+'}
        </span>
      </div>

      {/* Inline AI summary (visible without expanding) */}
      {summary && (
        <div className="ml-[76px] text-xs text-emerald-400/80 italic mt-0.5 leading-snug">
          AI: {summary}
        </div>
      )}

      {/* Expanded detail — click here does NOT collapse, allows text selection */}
      {expanded && (
        <div className="mt-2 ml-[76px] text-xs">
          <Detail event={event} />
        </div>
      )}
    </div>
  )
}

function Summary({ event }: { event: MonitorEvent }) {
  const d = event.data

  switch (event.type) {
    case 'llm_call': {
      const data = d as unknown as LlmCallData
      const model = data.model?.split('-').slice(-2).join('-') || 'unknown'
      return (
        <span className="text-slate-300">
          <span className="text-blue-400 font-medium">[{model}]</span>
          {' '}{data.call_type}
          {data.attempt > 1 && <span className="text-yellow-400"> (retry #{data.attempt})</span>}
          <span className="text-slate-500"> &middot; {formatLatency(data.latency_ms)} &middot; {formatTokens(data.tokens)} tok</span>
        </span>
      )
    }

    case 'llm_request_start': {
      const data = d as unknown as LlmRequestStartData
      const model = data.model?.split('-').slice(-2).join('-') || 'unknown'
      return (
        <span className="text-slate-300">
          <span className="text-blue-300 font-medium">[{model}]</span>
          {' '}{data.call_type}
          <span className="text-slate-500">
            {' '}&middot; {data.state_type}
            {' '}&middot; R{data.round_idx}
            {' '}&middot; {data.tool_count} tools
            {' '}&middot; {data.message_count} msgs
          </span>
          {data.think_enabled && <span className="text-cyan-300"> &middot; think</span>}
        </span>
      )
    }

    case 'llm_first_chunk': {
      const data = d as unknown as LlmFirstChunkData
      const model = data.model?.split('-').slice(-2).join('-') || 'unknown'
      const transport = typeof data.chunk_meta?.transport === 'string'
        ? data.chunk_meta.transport
        : ''
      return (
        <span className="text-slate-300">
          <span className="text-sky-300 font-medium">[{model}]</span>
          {' '}first chunk
          <span className="text-slate-500"> &middot; {formatLatency(data.latency_ms)}</span>
          {transport && <span className="text-slate-500"> &middot; {transport}</span>}
        </span>
      )
    }

    case 'llm_request_end': {
      const data = d as unknown as LlmRequestEndData
      const model = data.model?.split('-').slice(-2).join('-') || 'unknown'
      const statusColor = data.status === 'ok' ? 'text-green-400' : 'text-red-400'
      return (
        <span className="text-slate-300">
          <span className="text-blue-400 font-medium">[{model}]</span>
          {' '}<span className={statusColor}>{data.status}</span>
          <span className="text-slate-500">
            {' '}&middot; {formatLatency(data.latency_ms)}
            {' '}&middot; {formatTokens(data.tokens)} tok
          </span>
          {data.error && <span className="text-red-400"> &middot; {truncate(data.error, 80)}</span>}
        </span>
      )
    }

    case 'game_action': {
      const data = d as unknown as GameActionData
      const params = Object.entries(data.params || {})
        .filter(([k]) => k !== 'action')
        .map(([k, v]) => `${k}=${v}`)
        .join(', ')
      return (
        <span className="text-orange-300">
          {data.action}
          {params && <span className="text-slate-400">({params})</span>}
        </span>
      )
    }

    case 'action_result': {
      const data = d as unknown as ActionResultData
      const statusColor = data.status === 'ok' ? 'text-green-400' : 'text-red-400'
      return (
        <span className="text-orange-200">
          {data.action}
          <span className={statusColor}> {data.status}</span>
          {data.error && <span className="text-red-400"> {truncate(data.error, 60)}</span>}
        </span>
      )
    }

    case 'state': {
      const data = d as unknown as StateData
      const combat = data.combat
      if (combat) {
        const enemies = combat.enemies?.map(e => `${e.name}(${e.hp})`).join(', ') || ''
        return (
          <span className="text-slate-400">
            Floor {data.floor} &middot; R{combat.round} &middot; E:{combat.player.energy} &middot; HP:{combat.player.hp}/{combat.player.max_hp}
            {combat.player.block > 0 && ` \u00B7 Block:${combat.player.block}`}
            {enemies && <span className="text-slate-500"> &middot; {truncate(enemies, 60)}</span>}
          </span>
        )
      }
      return <span className="text-slate-400">{data.summary || data.state_type}</span>
    }

    case 'transition': {
      const data = d as unknown as TransitionData
      return <span className="text-purple-300">{data.type} &middot; {data.summary || data.state_type}</span>
    }

    case 'combat_plan': {
      const data = d as unknown as CombatPlanData
      const items = data.items?.map(i => i.card || i.type).join(' \u2192 ') || 'empty'
      return <span className="text-cyan-300">{items}{data.end_turn ? ' \u2192 END' : ''}</span>
    }

    case 'combat_summary': {
      const data = d as unknown as CombatSummaryData
      const outcome = data.won ? 'WON' : 'LOST'
      const outcomeColor = data.won ? 'text-green-400' : 'text-red-400'
      const hpDelta = data.hp_after - data.hp_before
      const hpStr = hpDelta >= 0 ? `+${hpDelta}` : `${hpDelta}`
      return (
        <span className="text-cyan-200">
          {data.enemy_key} &middot; <span className={outcomeColor}>{outcome}</span>
          {' '}&middot; {data.total_rounds}R &middot; {data.total_cards_played} cards
          <span className="text-slate-500"> &middot; HP {hpStr}</span>
        </span>
      )
    }

    case 'context_assembly': {
      const data = d as unknown as ContextAssemblyData
      const parts = []
      if (data.skills) parts.push('skills')
      if (data.memory_type !== 'none') parts.push(`memory(${data.memory_type})`)
      if (data.knowledge_chars > 0) parts.push(`knowledge(${data.knowledge_chars}c)`)
      if (data.archetype) parts.push('archetype')
      if (data.boss_strategy) parts.push('boss')
      return <span className="text-teal-400">{data.state_type} &middot; {parts.join(' + ') || 'empty'}</span>
    }

    case 'tool_call': {
      const data = d as unknown as ToolCallData
      const inputStr = Object.entries(data.tool_input || {})
        .map(([k, v]) => `${k}=${typeof v === 'string' ? truncate(v, 30) : v}`)
        .join(', ')
      return (
        <span className="text-indigo-300">
          {data.tool_name}
          {inputStr && <span className="text-slate-400">({inputStr})</span>}
          {data.result_preview && <span className="text-slate-500"> &rarr; {truncate(data.result_preview, 80)}</span>}
        </span>
      )
    }

    case 'tool_preprocessing': {
      const data = d as unknown as ToolPreprocessingData
      return (
        <span className="text-teal-300">
          {data.state_type} &middot; {data.hint_count} tools
          <span className="text-slate-500"> &middot; {data.tools.join(', ')} &middot; {data.chars}c</span>
        </span>
      )
    }

    case 'decision': {
      const data = d as unknown as DecisionData
      const action = typeof data.action === 'object' ? JSON.stringify(data.action) : String(data.action)
      return (
        <span className="text-purple-300">
          [{data.source}] {truncate(action, 60)}
          {data.reasoning && <span className="text-slate-500"> &mdash; {truncate(data.reasoning, 80)}</span>}
        </span>
      )
    }

    case 'run_start':
      return <span className="text-yellow-300">Run started: {d.run_id as string}</span>

    case 'run_end': {
      const data = d as unknown as RunEndData
      const asc = data.ascension != null ? `A${data.ascension}` : null
      return (
        <span className={data.victory ? 'text-green-400' : 'text-red-400'}>
          {data.victory ? '\uD83C\uDFC6 VICTORY' : '\uD83D\uDC80 DEFEAT'}
          {asc && <> &middot; <span className="text-amber-400">{asc}</span></>}
          {' '}&middot; Floor {data.floor} &middot; Fitness: {data.fitness?.toFixed(1)}
          <span className="text-slate-500"> &middot; {data.duration_s?.toFixed(0)}s</span>
        </span>
      )
    }

    case 'error': {
      const data = d as unknown as ErrorData
      return <span className="text-red-400">{truncate(data.error || 'Unknown error', 120)}</span>
    }

    case 'postrun_llm_call': {
      const model = ((d.model as string) || 'unknown').split('-').slice(-2).join('-')
      const tok = ((d.input_tokens as number) || 0) + ((d.output_tokens as number) || 0)
      const preview = truncate((d.response as string) || '', 80)
      return (
        <span className="text-slate-300">
          <span className="text-amber-400 font-medium">[{model}]</span>
          {' '}{d.call_type as string}
          <span className="text-slate-500"> &middot; {formatLatency((d.latency_ms as number) || 0)} &middot; {formatTokens(tok)} tok</span>
          {preview && <span className="text-slate-400"> &mdash; {preview}</span>}
        </span>
      )
    }

    case 'post_run_start':
      return <span className="text-amber-300">Postrun started{d.completion_reason ? ` (reason: ${d.completion_reason as string})` : ''}</span>

    case 'post_run_stage': {
      const stage = d.stage as string
      const status = d.status as string
      const color = status === 'done' ? 'text-green-400'
        : status === 'failed' ? 'text-red-400'
        : status === 'skipped' ? 'text-slate-500' : 'text-amber-300'
      return (
        <span className="text-slate-300">
          <span className="text-amber-200 font-medium">{stage}</span>
          {' '}<span className={color}>{status}</span>
          {d.error ? <span className="text-red-400"> &mdash; {truncate(d.error as string, 100)}</span> : null}
        </span>
      )
    }

    case 'post_run_end':
      return <span className="text-amber-300">Postrun finished</span>

    case 'evolution_round': {
      const roundIdx = (d.round as number) ?? 0
      const phase = (d.phase as string) || ''
      const model = ((d.model as string) || '').split('-').slice(-2).join('-')
      const inTok = (d.input_tokens as number) || 0
      const outTok = (d.output_tokens as number) || 0
      const tools = (d.tool_names as string[] | undefined) || []
      return (
        <span className="text-slate-300">
          <span className="text-fuchsia-400 font-medium">round {roundIdx}{phase ? ` (${phase})` : ''}</span>
          {' '}<span className="text-slate-500">[{model}]</span>
          {tools.length > 0 && <span className="text-slate-400"> tools: {tools.join(', ')}</span>}
          <span className="text-slate-500"> &middot; {formatLatency((d.latency_ms as number) || 0)} &middot; {formatTokens(inTok + outTok)} tok</span>
        </span>
      )
    }

    case 'evolution_summary': {
      const rounds = (d.total_rounds as number) ?? 0
      const actions = (d.actions_taken as number) ?? 0
      const inTok = (d.total_input_tokens as number) || 0
      const outTok = (d.total_output_tokens as number) || 0
      return (
        <span className="text-slate-300">
          <span className="text-fuchsia-400 font-medium">{rounds} rounds</span>, {actions} actions
          <span className="text-slate-500"> &middot; {formatTokens(inTok + outTok)} tok</span>
        </span>
      )
    }

    case 'postrun_artifact': {
      const stage = (d.stage as string) || ''
      const kind = (d.kind as string) || ''
      const action = (d.action as string) || 'write'
      const target = (d.target as string) || ''
      const summary = (d.summary as string) || ''
      return (
        <span className="text-slate-300">
          <span className="text-lime-400 font-medium">{stage}</span>
          <span className="text-slate-500"> / </span>
          <span className="text-lime-300">{kind}</span>
          <span className="text-slate-500"> {action}</span>
          {target && <span className="text-slate-200"> &mdash; {target}</span>}
          {summary && <span className="text-slate-500"> &middot; {truncate(summary, 100)}</span>}
        </span>
      )
    }

    case 'monitor_init': {
      const msg = typeof d.message === 'string' ? d.message : 'Agent initialized'
      const monPort = typeof d.monitor_port === 'number' ? d.monitor_port : null
      const gamePort = typeof d.game_port === 'number' ? d.game_port : null
      const gamePid = typeof d.game_pid === 'number' ? d.game_pid : null
      return (
        <span className="text-sky-300">
          {msg}
          {(monPort || gamePort || gamePid) && (
            <span className="text-slate-500">
              {' '}&middot;{' '}
              {monPort && <span className="tabular-nums">mon:{monPort}</span>}
              {gamePort && <span className="tabular-nums ml-2">game:{gamePort}</span>}
              {gamePid && <span className="tabular-nums ml-2">pid:{gamePid}</span>}
            </span>
          )}
        </span>
      )
    }

    default:
      return <span className="text-slate-400">{JSON.stringify(d).slice(0, 100)}</span>
  }
}

function Detail({ event }: { event: MonitorEvent }) {
  const d = event.data

  switch (event.type) {
    case 'llm_call': {
      const data = d as unknown as LlmCallData
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Model: <span className="text-slate-300">{data.model}</span></span>
            <span>Tier: <span className="text-slate-300">{data.tier}</span></span>
            <span>Latency: <span className="text-slate-300">{formatLatency(data.latency_ms)}</span></span>
            <span>Tokens: <span className="text-slate-300">{data.tokens}</span></span>
            {(data.input_tokens || data.output_tokens) ? (
              <span className="text-slate-500">
                (In <span className="text-slate-300">{data.input_tokens ?? 0}</span>
                {' '}/ Out <span className="text-slate-300">{data.output_tokens ?? 0}</span>)
              </span>
            ) : null}
            {data.cache_read_tokens > 0 && (
              <span>Cache: <span className="text-green-400">{data.cache_read_tokens}</span></span>
            )}
            <span>Stop: <span className="text-slate-300">{data.stop_reason || 'stop'}</span></span>
            {data.think_budget > 0 && (
              <span>Think budget: <span className="text-slate-300">{data.think_budget}</span></span>
            )}
          </div>

          {data.tools && data.tools.length > 0 && (
            <div>
              <div className="text-slate-500 mb-1">Tools ({data.tools.length}):</div>
              <div className="bg-slate-900 p-2 rounded space-y-1">
                {data.tools.map((t, i) => (
                  <details key={i} className="group">
                    <summary className="cursor-pointer text-amber-300 hover:text-amber-200">
                      {t.name}
                      <span className="text-slate-500"> — {t.description}</span>
                    </summary>
                    {t.input_schema && (
                      <pre className="mt-1 ml-4 text-slate-400 text-[10px] max-h-48 overflow-y-auto whitespace-pre-wrap">
                        {JSON.stringify(t.input_schema, null, 2)}
                      </pre>
                    )}
                  </details>
                ))}
              </div>
            </div>
          )}

          <div>
            <div className="text-slate-500 mb-1">System prompt:</div>
            <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {data.system_prompt}
            </pre>
          </div>

          {data.messages && data.messages.length > 0 && (
            <div>
              <div className="text-slate-500 mb-1">Messages ({data.messages.length} turns):</div>
              <div className="space-y-1">
                {data.messages.map((msg, i) => (
                  <div key={i}>
                    <div className="text-slate-500 text-[10px] uppercase tracking-wider">{msg.role}</div>
                    <pre className={`bg-slate-900 p-2 rounded overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap ${
                      msg.role === 'user' ? 'text-blue-300' : msg.role === 'assistant' ? 'text-green-300' : 'text-slate-400'
                    }`}>
                      {msg.content}
                    </pre>
                  </div>
                ))}
              </div>
            </div>
          )}

          {data.thinking_text && (
            <div>
              <div className="text-slate-500 mb-1">Thinking:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {data.thinking_text}
              </pre>
            </div>
          )}

          <div>
            <div className="text-slate-500 mb-1">Prompt (latest user message):</div>
            <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-blue-300 max-h-64 overflow-y-auto whitespace-pre-wrap">
              {data.prompt}
            </pre>
          </div>

          <div>
            <div className="text-slate-500 mb-1">Response:</div>
            <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-green-300 max-h-64 overflow-y-auto whitespace-pre-wrap">
              {data.response}
            </pre>
          </div>
        </div>
      )
    }

    case 'llm_request_start': {
      const data = d as unknown as LlmRequestStartData
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Provider: <span className="text-slate-300">{data.provider}</span></span>
            <span>Model: <span className="text-slate-300">{data.model}</span></span>
            <span>Tier: <span className="text-slate-300">{data.tier}</span></span>
            <span>State: <span className="text-slate-300">{data.state_type}</span></span>
            <span>Round: <span className="text-slate-300">{data.round_idx}</span></span>
          </div>
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Call: <span className="text-slate-300">{data.call_type}</span></span>
            <span>Thinking: <span className="text-slate-300">{data.think_enabled ? 'on' : 'off'}</span></span>
            <span>Tools: <span className="text-slate-300">{data.tool_count}</span></span>
            <span>Messages: <span className="text-slate-300">{data.message_count}</span></span>
          </div>
        </div>
      )
    }

    case 'llm_first_chunk': {
      const data = d as unknown as LlmFirstChunkData
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Provider: <span className="text-slate-300">{data.provider}</span></span>
            <span>Model: <span className="text-slate-300">{data.model}</span></span>
            <span>Tier: <span className="text-slate-300">{data.tier}</span></span>
            <span>Latency: <span className="text-slate-300">{formatLatency(data.latency_ms)}</span></span>
          </div>
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>State: <span className="text-slate-300">{data.state_type}</span></span>
            <span>Round: <span className="text-slate-300">{data.round_idx}</span></span>
            <span>Call: <span className="text-slate-300">{data.call_type}</span></span>
          </div>
          <div>
            <div className="text-slate-500 mb-1">Chunk metadata:</div>
            <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
              {JSON.stringify(data.chunk_meta || {}, null, 2)}
            </pre>
          </div>
        </div>
      )
    }

    case 'llm_request_end': {
      const data = d as unknown as LlmRequestEndData
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Provider: <span className="text-slate-300">{data.provider}</span></span>
            <span>Model: <span className="text-slate-300">{data.model}</span></span>
            <span>Tier: <span className="text-slate-300">{data.tier}</span></span>
            <span>Status: <span className={data.status === 'ok' ? 'text-green-400' : 'text-red-400'}>{data.status}</span></span>
          </div>
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>State: <span className="text-slate-300">{data.state_type}</span></span>
            <span>Round: <span className="text-slate-300">{data.round_idx}</span></span>
            <span>Latency: <span className="text-slate-300">{formatLatency(data.latency_ms)}</span></span>
            <span>Tokens: <span className="text-slate-300">{data.tokens}</span></span>
            <span>Stop: <span className="text-slate-300">{data.stop_reason || 'n/a'}</span></span>
          </div>
          {data.error && (
            <div>
              <div className="text-slate-500 mb-1">Error:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-red-300 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {data.error}
              </pre>
            </div>
          )}
        </div>
      )
    }

    case 'state': {
      const data = d as unknown as StateData
      return (
        <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-64 overflow-y-auto whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      )
    }

    case 'combat_plan': {
      const data = d as unknown as CombatPlanData
      // Prefer Chinese fields when present (server-side enrichment when
      // STS2_DISPLAY_LANGUAGE=zh): card_zh per item, reasoning_zh, plus a
      // pre-baked `text` summary. UI labels translate based on whether any
      // item carries card_zh — that signals the server expects zh display.
      const zhMode = !!(data.reasoning_zh || data.items?.some(it => it.card_zh))
      const labels = zhMode
        ? { reasoning: '推理', card: '卡牌', potion: '药水', target: '目标', endTurn: '结束回合' }
        : { reasoning: 'Reasoning', card: 'card', potion: 'potion', target: 'target', endTurn: 'End Turn' }
      const typeLabel = (t: string) => labels[t as 'card' | 'potion'] ?? t
      return (
        <div className="space-y-1">
          <div className="text-slate-400">
            {labels.reasoning}: {zhMode ? (data.reasoning_zh || data.reasoning) : data.reasoning}
          </div>
          <div className="space-y-0.5">
            {data.items?.map((item, i) => (
              <div key={i} className="text-cyan-300">
                {i + 1}. [{typeLabel(item.type)}] {(zhMode && item.card_zh) || item.card}
                {item.target != null && (
                  <span className="text-slate-400"> &rarr; {labels.target} {item.target}</span>
                )}
              </div>
            ))}
            {data.end_turn && <div className="text-yellow-400">&rarr; {labels.endTurn}</div>}
          </div>
        </div>
      )
    }

    case 'combat_summary': {
      const data = d as unknown as CombatSummaryData
      return (
        <div className="space-y-1">
          <div className="text-slate-400">
            {data.enemy_key} ({data.combat_type}) &middot; Floor {data.floor}
            &middot; {data.won ? 'Victory' : 'Defeat'}
            &middot; HP: {data.hp_before} &rarr; {data.hp_after}
          </div>
          <div className="space-y-0.5">
            {data.rounds?.map((r, i) => (
              <div key={i} className="text-slate-400">
                R{r.round}: {r.cards_played?.length ?? 0} cards
                {r.cards_played?.length > 0 && <span className="text-cyan-300"> ({r.cards_played.join(', ')})</span>}
                , -{r.damage_taken} dmg, HP {r.hp_start}&rarr;{r.hp_end}
                {r.potions_used?.length > 0 && <span className="text-purple-300"> +{r.potions_used.length} pot ({r.potions_used.join(', ')})</span>}
              </div>
            ))}
          </div>
        </div>
      )
    }

    case 'action_result': {
      const data = d as unknown as ActionResultData
      return (
        <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
          {JSON.stringify(data, null, 2)}
        </pre>
      )
    }

    case 'context_assembly': {
      const data = d as unknown as ContextAssemblyData
      return (
        <div className="space-y-1 text-slate-400">
          <div>State: {data.state_type}</div>
          <div>Memory: {data.memory_type}</div>
          <div>Knowledge: {data.knowledge_chars} chars</div>
          {data.skills && <div>Skills: {data.skills}</div>}
          {data.archetype && <div>Archetype: {data.archetype}</div>}
          <div>Boss strategy: {data.boss_strategy ? 'yes' : 'no'}</div>
        </div>
      )
    }

    case 'tool_call': {
      const data = d as unknown as ToolCallData
      return (
        <div className="space-y-1">
          <div className="text-slate-400">Tool: <span className="text-indigo-300">{data.tool_name}</span> (round {data.round})</div>
          <div>
            <div className="text-slate-500 mb-1">Input:</div>
            <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-32 overflow-y-auto whitespace-pre-wrap">
              {JSON.stringify(data.tool_input, null, 2)}
            </pre>
          </div>
          {data.result_preview && (
            <div>
              <div className="text-slate-500 mb-1">Result (preview):</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-green-300 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {data.result_preview}
              </pre>
            </div>
          )}
        </div>
      )
    }

    case 'tool_preprocessing': {
      const data = d as unknown as ToolPreprocessingData
      return (
        <div className="space-y-1 text-slate-400">
          <div>State: {data.state_type}</div>
          <div>Tools executed: {data.hint_count}</div>
          <div>Total hint chars: {data.chars}</div>
          <div className="space-y-0.5 mt-1">
            {data.tools.map((tool, i) => (
              <div key={i} className="text-teal-300">{i + 1}. {tool}</div>
            ))}
          </div>
        </div>
      )
    }

    case 'postrun_llm_call': {
      const inTok = (d.input_tokens as number) || 0
      const outTok = (d.output_tokens as number) || 0
      const systemPrompt = (d.system_prompt as string) || ''
      const prompt = (d.prompt as string) || ''
      const response = (d.response as string) || ''
      const thinking = (d.thinking_text as string) || ''
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Type: <span className="text-amber-300">{d.call_type as string}</span></span>
            <span>Model: <span className="text-slate-300">{d.model as string}</span></span>
            {d.provider ? <span>Provider: <span className="text-slate-300">{d.provider as string}</span></span> : null}
            {d.effort ? <span>Effort: <span className="text-slate-300">{d.effort as string}</span></span> : null}
            <span>Latency: <span className="text-slate-300">{formatLatency((d.latency_ms as number) || 0)}</span></span>
            <span>In: <span className="text-slate-300">{inTok.toLocaleString()}</span></span>
            <span>Out: <span className="text-slate-300">{outTok.toLocaleString()}</span></span>
            {d.error ? <span>Error: <span className="text-red-400">{d.error as string}</span></span> : null}
          </div>

          {systemPrompt && (
            <div>
              <div className="text-slate-500 mb-1">System prompt:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {systemPrompt}
              </pre>
            </div>
          )}

          {prompt && (
            <div>
              <div className="text-slate-500 mb-1">Prompt:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-blue-300 max-h-96 overflow-y-auto whitespace-pre-wrap">
                {prompt}
              </pre>
            </div>
          )}

          {thinking && (
            <div>
              <div className="text-slate-500 mb-1">Thinking:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {thinking}
              </pre>
            </div>
          )}

          {response && (
            <div>
              <div className="text-slate-500 mb-1">Response:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-green-300 max-h-96 overflow-y-auto whitespace-pre-wrap">
                {response}
              </pre>
            </div>
          )}
        </div>
      )
    }

    case 'evolution_round': {
      const inTok = (d.input_tokens as number) || 0
      const outTok = (d.output_tokens as number) || 0
      const systemPrompt = (d.system_prompt as string) || ''
      const responseText = (d.response_text as string) || ''
      const thinking = (d.thinking_text as string) || ''
      const rawMessages = (d.messages as Array<{ role: string; content: unknown; _reasoning_content?: string }> | undefined) || []
      const toolUses = (d.tool_uses as Array<{ id?: string; name?: string; input?: unknown }> | undefined) || []
      const renderMessageContent = (content: unknown): string => {
        if (typeof content === 'string') return content
        if (Array.isArray(content)) {
          return content.map((b) => {
            if (typeof b === 'string') return b
            if (b && typeof b === 'object') {
              const blk = b as Record<string, unknown>
              if (blk.type === 'text') return (blk.text as string) || ''
              if (blk.type === 'tool_use') return `[tool_use:${blk.name}] ${JSON.stringify(blk.input ?? {}, null, 2).slice(0, 2000)}`
              if (blk.type === 'tool_result') {
                const inner = blk.content
                const text = Array.isArray(inner)
                  ? inner.map((x: unknown) => (x && typeof x === 'object' && 'text' in (x as Record<string, unknown>) ? String((x as Record<string, unknown>).text) : String(x))).join('\n')
                  : String(inner ?? '')
                return `[tool_result ${String(blk.tool_use_id ?? '').slice(0, 8)}] ${text}`
              }
              if (blk.type === 'thinking') return `[thinking] ${(blk.thinking as string) || (blk.text as string) || ''}`
              return JSON.stringify(blk)
            }
            return String(b)
          }).join('\n')
        }
        return JSON.stringify(content)
      }
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Round: <span className="text-fuchsia-300">{(d.round as number) ?? 0}</span></span>
            <span>Phase: <span className="text-slate-300">{(d.phase as string) || 'n/a'}</span></span>
            <span>Model: <span className="text-slate-300">{d.model as string}</span></span>
            {d.provider ? <span>Provider: <span className="text-slate-300">{d.provider as string}</span></span> : null}
            <span>In: <span className="text-slate-300">{inTok.toLocaleString()}</span></span>
            <span>Out: <span className="text-slate-300">{outTok.toLocaleString()}</span></span>
            <span>Stop: <span className="text-slate-300">{(d.stop_reason as string) || 'n/a'}</span></span>
            <span>Latency: <span className="text-slate-300">{formatLatency((d.latency_ms as number) || 0)}</span></span>
          </div>

          {systemPrompt && (
            <div>
              <div className="text-slate-500 mb-1">System prompt:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {systemPrompt}
              </pre>
            </div>
          )}

          {rawMessages.length > 0 && (
            <div>
              <div className="text-slate-500 mb-1">Messages ({rawMessages.length} turns):</div>
              <div className="space-y-1">
                {rawMessages.map((msg, i) => (
                  <div key={i}>
                    <div className="text-slate-500 text-[10px] uppercase tracking-wider">{msg.role}</div>
                    <pre className={`bg-slate-900 p-2 rounded overflow-x-auto max-h-64 overflow-y-auto whitespace-pre-wrap ${
                      msg.role === 'user' ? 'text-blue-300' : msg.role === 'assistant' ? 'text-green-300' : 'text-slate-400'
                    }`}>
                      {renderMessageContent(msg.content)}
                    </pre>
                    {msg._reasoning_content ? (
                      <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-500 max-h-32 overflow-y-auto whitespace-pre-wrap">
                        [reasoning] {msg._reasoning_content}
                      </pre>
                    ) : null}
                  </div>
                ))}
              </div>
            </div>
          )}

          {thinking && (
            <div>
              <div className="text-slate-500 mb-1">Thinking:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {thinking}
              </pre>
            </div>
          )}

          {responseText && (
            <div>
              <div className="text-slate-500 mb-1">Response text:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-green-300 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {responseText}
              </pre>
            </div>
          )}

          {toolUses.length > 0 && (
            <div>
              <div className="text-slate-500 mb-1">Tool uses ({toolUses.length}):</div>
              <div className="space-y-1">
                {toolUses.map((tu, i) => (
                  <details key={i} className="bg-slate-900 p-2 rounded">
                    <summary className="cursor-pointer text-amber-300 hover:text-amber-200">
                      {tu.name || '<unnamed>'}
                    </summary>
                    <pre className="mt-1 ml-4 text-slate-400 text-[10px] max-h-48 overflow-y-auto whitespace-pre-wrap">
                      {JSON.stringify(tu.input ?? {}, null, 2)}
                    </pre>
                  </details>
                ))}
              </div>
            </div>
          )}
        </div>
      )
    }

    case 'post_run_stage': {
      return (
        <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
          {JSON.stringify(d, null, 2)}
        </pre>
      )
    }

    case 'evolution_summary': {
      return (
        <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-96 overflow-y-auto whitespace-pre-wrap">
          {JSON.stringify(d, null, 2)}
        </pre>
      )
    }

    case 'postrun_artifact': {
      const before = d.before
      const after = d.after
      const details = d.details
      const renderValue = (v: unknown): string => {
        if (v == null) return ''
        if (typeof v === 'string') return v
        return JSON.stringify(v, null, 2)
      }
      return (
        <div className="space-y-2">
          <div className="flex gap-4 text-slate-500 flex-wrap">
            <span>Stage: <span className="text-lime-300">{d.stage as string}</span></span>
            <span>Kind: <span className="text-lime-300">{d.kind as string}</span></span>
            <span>Action: <span className="text-slate-300">{d.action as string}</span></span>
            {d.target ? <span>Target: <span className="text-slate-300">{d.target as string}</span></span> : null}
            {d.source ? <span>Source: <span className="text-slate-300">{d.source as string}</span></span> : null}
          </div>
          {d.summary ? (
            <div className="text-slate-300">{d.summary as string}</div>
          ) : null}
          {before != null && (
            <div>
              <div className="text-slate-500 mb-1">Before:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-red-300 max-h-64 overflow-y-auto whitespace-pre-wrap">
                {renderValue(before)}
              </pre>
            </div>
          )}
          {after != null && (
            <div>
              <div className="text-slate-500 mb-1">After:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-green-300 max-h-96 overflow-y-auto whitespace-pre-wrap">
                {renderValue(after)}
              </pre>
            </div>
          )}
          {details != null && (
            <div>
              <div className="text-slate-500 mb-1">Details:</div>
              <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
                {renderValue(details)}
              </pre>
            </div>
          )}
        </div>
      )
    }

    default:
      return (
        <pre className="bg-slate-900 p-2 rounded overflow-x-auto text-slate-400 max-h-48 overflow-y-auto whitespace-pre-wrap">
          {JSON.stringify(d, null, 2)}
        </pre>
      )
  }
}
