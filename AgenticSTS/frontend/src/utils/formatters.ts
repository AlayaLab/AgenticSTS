export function formatTimestamp(ts: number): string {
  const d = new Date(ts * 1000)
  return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function formatLatency(ms: number): string {
  if (ms < 1000) return `${Math.round(ms)}ms`
  return `${(ms / 1000).toFixed(1)}s`
}

export function formatTokens(n: number): string {
  if (n < 1000) return String(n)
  return `${(n / 1000).toFixed(1)}k`
}

export function truncate(s: string, max: number): string {
  if (s.length <= max) return s
  return s.slice(0, max) + '…'
}

import type { GamePhase } from '../types/events'

const COMBAT_STATE_TYPES = new Set(['monster', 'elite', 'boss', 'hand_select'])

const STATE_TYPE_TO_PHASE: Record<string, GamePhase> = {
  monster: 'combat',
  elite: 'combat',
  boss: 'combat',
  hand_select: 'combat',
  map: 'map',
  shop: 'shop',
  event: 'event',
  rest_site: 'rest',
  card_reward: 'card_reward',
  card_select: 'card_select',
  treasure: 'treasure',
}

export function stateTypeToPhase(stateType: string): GamePhase {
  return STATE_TYPE_TO_PHASE[stateType] ?? 'other'
}

export { COMBAT_STATE_TYPES }
