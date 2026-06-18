export type Ascension = 0 | 1 | 2 | 3 | 4 | 5

export type RunOutcome = 'victory' | 'defeat' | 'abort'

export interface RunSummary {
  run_index: number           // 1-based position within the submission's run sequence
  ascension: Ascension
  outcome: RunOutcome
  final_floor: number         // 1..50-ish; undefined death floor = 0
  final_act: 1 | 2 | 3
  death_cause?: string
  duration_seconds: number
  per_run_score: number
  run_log_url?: string
}

export interface Relic {
  id: string                  // 'memory-store' | 'skill-library' | 'evolution-engine' | ...
  label: string
  description: string
}

export interface MethodInfo {
  name: string
  version: string
  authors: string[]
  description_short: string
  github_url?: string
  paper_url?: string
  relics: Relic[]
}

export interface ModelInfo {
  provider: 'anthropic' | 'openai' | 'google' | 'qwen' | 'other'
  name: string
  id: string
  tier_breakdown?: Partial<Record<'fast' | 'strategic' | 'analysis', string>>
}

export type Character = 'Silent' | 'Regent' | 'Watcher' | 'Defect' | 'Ironclad'

export interface Aggregate {
  ceiling: Ascension
  ceiling_consistency: number     // 0..1
  progress_score_mean: number
  progress_score_max: number
  avg_final_floor: number
  max_final_floor: number
  total_runs: number
  total_victories: number
}

export interface Cost {
  total_usd: number
  total_input_tokens: number
  total_output_tokens: number
  cost_per_run_usd: number
  cost_per_ascension_unlocked_usd: number
}

export interface Submission {
  id: string
  method: MethodInfo
  model: ModelInfo
  character: Character
  runs: RunSummary[]
  aggregate: Aggregate
  cost: Cost
  submitted_at: string           // ISO timestamp
  verified: boolean
}

export interface SubmissionBundle {
  schema_version: '1.0'
  built_at: string
  submissions: Submission[]
}
