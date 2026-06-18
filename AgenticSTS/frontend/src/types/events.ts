// ── Monitor Event Envelope ────────────────────────────────
export interface MonitorEvent {
  id: string
  timestamp: number
  type: EventType
  data: Record<string, unknown>
  step: number | null
  run_id: string | null
}

// ── Event Types (aligned with backend emissions) ─────────
export type EventType =
  | 'state'
  | 'llm_call'
  | 'llm_request_start'
  | 'llm_first_chunk'
  | 'llm_request_end'
  | 'decision'
  | 'transition'
  | 'game_action'
  | 'action_result'
  | 'combat_plan'
  | 'combat_summary'
  | 'context_assembly'
  | 'tool_call'
  | 'tool_preprocessing'
  | 'run_start'
  | 'run_end'
  | 'error'
  | 'ai_summary'
  | 'postrun_llm_call'
  | 'post_run_start'
  | 'post_run_stage'
  | 'post_run_end'
  | 'evolution_round'
  | 'evolution_summary'
  | 'postrun_artifact'
  | 'monitor_init'

// ── Event Data Interfaces ────────────────────────────────
export interface LlmToolSummary {
  name: string
  description: string
  input_schema?: Record<string, unknown>
}

export interface LlmMessageLog {
  role: string
  content: string
}

export interface LlmCallData {
  call_type: string
  model: string
  tier: string
  system_prompt: string
  prompt: string
  response: string
  thinking_text: string
  latency_ms: number
  tokens: number
  input_tokens?: number
  output_tokens?: number
  cache_read_tokens: number
  stop_reason: string
  attempt: number
  think_budget: number
  tools: LlmToolSummary[] | null
  messages: LlmMessageLog[] | null
}

export interface LlmRequestStartData {
  call_type: string
  provider: string
  model: string
  tier: string
  state_type: string
  round_idx: number
  think_enabled: boolean
  tool_count: number
  message_count: number
}

export interface LlmFirstChunkData {
  call_type: string
  provider: string
  model: string
  tier: string
  state_type: string
  round_idx: number
  latency_ms: number
  chunk_meta: Record<string, unknown>
}

export interface LlmRequestEndData {
  call_type: string
  provider: string
  model: string
  tier: string
  state_type: string
  round_idx: number
  latency_ms: number
  status: string
  stop_reason: string
  tokens: number
  error?: string
}

export interface GameActionData {
  action: string
  params: Record<string, unknown>
  result_status: string
  stable: boolean
}

export interface ActionResultData {
  step: number
  action: string
  params: Record<string, unknown>
  status: string
  error?: string
  mcp_status?: string
  mcp_stable?: boolean
  mcp_message?: string
}

export interface StateData {
  step: number
  state_type: string
  summary: string
  floor?: number
  ascension?: number
  combat?: {
    round: number
    player: {
      hp: number
      max_hp: number
      block: number
      energy: number
      hand: Array<{ name: string; energy_cost: number; playable: boolean }>
    }
    enemies: Array<{ name: string; hp: number; max_hp: number }>
  }
  deck_size?: number
  player?: { hp?: number; max_hp?: number }
}

export interface TransitionData {
  type: string
  state_type: string
  summary: string
  step?: number
  floor?: number
  hp?: number
  hp_max?: number
}

export interface CombatPlanData {
  items: Array<{ type: string; card: string; card_zh?: string; target: number | null }>
  end_turn: boolean
  reasoning: string
  reasoning_zh?: string
  text?: string
  no_target_mode?: boolean
}

export interface CombatSummaryData {
  step: number
  enemy_key: string
  combat_type: string
  won: boolean
  floor: number
  total_rounds: number
  total_cards_played: number
  hp_before: number
  hp_after: number
  rounds: Array<{
    round: number
    cards_played: string[]
    potions_used: string[]
    hp_start: number
    hp_end: number
    damage_taken: number
    energy_used: number
    energy_available: number
  }>
}

export interface DecisionData {
  step: number
  floor: number
  state_type: string
  action: Record<string, unknown>
  reasoning: string
  source: string
}

export interface RunStartData {
  run_id: string
}

export interface RunEndData {
  victory: boolean
  floor: number
  fitness: number
  duration_s: number
  ascension?: number
}

export interface ErrorData {
  step: number
  error: string
}

export interface ContextAssemblyData {
  state_type: string
  skills: string
  memory_type: string
  knowledge_chars: number
  archetype: string
  boss_strategy: boolean
}

export interface ToolCallData {
  tool_name: string
  tool_input: Record<string, unknown>
  result_preview: string
  round: number
}

export interface ToolPreprocessingData {
  state_type: string
  tools: string[]
  hint_count: number
  chars: number
}

export interface AiSummaryData {
  parent_id: string
  summary: string
}

// ── Event Display Config ─────────────────────────────────
export const EVENT_COLORS: Record<EventType, string> = {
  state: '#64748b',
  llm_call: '#3b82f6',
  llm_request_start: '#60a5fa',
  llm_first_chunk: '#38bdf8',
  llm_request_end: '#2563eb',
  decision: '#8b5cf6',
  transition: '#a855f7',
  game_action: '#f97316',
  action_result: '#fb923c',
  combat_plan: '#06b6d4',
  combat_summary: '#22d3ee',
  context_assembly: '#14b8a6',
  tool_call: '#818cf8',
  tool_preprocessing: '#2dd4bf',
  run_start: '#eab308',
  run_end: '#eab308',
  error: '#ef4444',
  ai_summary: '#10b981',
  postrun_llm_call: '#f59e0b',
  post_run_start: '#f59e0b',
  post_run_stage: '#fbbf24',
  post_run_end: '#f59e0b',
  evolution_round: '#d946ef',
  evolution_summary: '#c026d3',
  postrun_artifact: '#84cc16',
  monitor_init: '#38bdf8',
}

export const EVENT_LABELS: Record<EventType, string> = {
  state: 'STATE',
  llm_call: 'LLM',
  llm_request_start: 'LLM START',
  llm_first_chunk: 'FIRST CHUNK',
  llm_request_end: 'LLM END',
  decision: 'DECISION',
  transition: 'TRANSITION',
  game_action: 'ACTION',
  action_result: 'RESULT',
  combat_plan: 'PLAN',
  combat_summary: 'COMBAT END',
  context_assembly: 'CONTEXT',
  tool_call: 'TOOL',
  tool_preprocessing: 'PREPROCESS',
  run_start: 'RUN START',
  run_end: 'RUN END',
  error: 'ERROR',
  ai_summary: 'AI SUMMARY',
  postrun_llm_call: 'POSTRUN LLM',
  post_run_start: 'POSTRUN START',
  post_run_stage: 'POSTRUN STAGE',
  post_run_end: 'POSTRUN END',
  evolution_round: 'EVOLUTION',
  evolution_summary: 'EVOLUTION SUMMARY',
  postrun_artifact: 'ARTIFACT',
  monitor_init: 'INIT',
}

// ── Game Phase Types (Phase 1) ───────────────────────────
export type GamePhase =
  | 'combat'
  | 'map'
  | 'shop'
  | 'event'
  | 'rest'
  | 'card_reward'
  | 'card_select'
  | 'treasure'
  | 'other'

export const PHASE_COLORS: Record<GamePhase, string> = {
  combat: '#ef4444',
  map: '#14b8a6',
  shop: '#8b5cf6',
  event: '#f59e0b',
  rest: '#22c55e',
  card_reward: '#3b82f6',
  card_select: '#6366f1',
  treasure: '#eab308',
  other: '#64748b',
}

export const PHASE_LABELS: Record<GamePhase, string> = {
  combat: 'COMBAT',
  map: 'MAP',
  shop: 'SHOP',
  event: 'EVENT',
  rest: 'REST',
  card_reward: 'REWARD',
  card_select: 'SELECT',
  treasure: 'TREASURE',
  other: '\u2014',
}

// ── Run Info (Phase 2) ───────────────────────────────────
export interface RunInfo {
  runId: string
  floor: number
  outcome?: 'victory' | 'defeat'
  fitness?: number
  ascension?: number
  ended: boolean
}

// ── Combat Grouping (Phase 4) ────────────────────────────
export type CombatType = 'monster' | 'elite' | 'boss'

export interface CombatEncounter {
  id: string
  enemyNames: string
  floor: number
  rounds: CombatRound[]
  outcome?: 'victory' | 'defeat'
  combatSummary?: CombatSummaryData
  combatType?: CombatType
  cardReward?: string
}

export interface CombatRound {
  roundNumber: number
  events: MonitorEvent[]
  planSummary?: string
  actions: string[]
  hpBefore?: number
  hpAfter?: number
}

// ── Non-combat phase encounters ──────────────────────────
export type PhaseEncounterKind = 'event' | 'shop' | 'card_reward' | 'rest'

export interface PhaseEncounter {
  id: string
  kind: PhaseEncounterKind
  floor: number
  events: MonitorEvent[]
  title?: string
  decision?: string
  hpBefore?: number
  hpAfter?: number
}
