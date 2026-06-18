import { z } from 'zod'

export const ascensionSchema = z.union([
  z.literal(0), z.literal(1), z.literal(2),
  z.literal(3), z.literal(4), z.literal(5),
])

export const runOutcomeSchema = z.enum(['victory', 'defeat', 'abort'])

export const runSummarySchema = z.object({
  run_index: z.number().int().min(1),
  ascension: ascensionSchema,
  outcome: runOutcomeSchema,
  final_floor: z.number().int().min(0),
  final_act: z.union([z.literal(1), z.literal(2), z.literal(3)]),
  death_cause: z.string().optional(),
  duration_seconds: z.number().nonnegative(),
  per_run_score: z.number().nonnegative(),
  run_log_url: z.string().url().optional(),
})

export const relicSchema = z.object({
  id: z.string().min(1),
  label: z.string().min(1),
  description: z.string(),
})

export const methodInfoSchema = z.object({
  name: z.string().min(1),
  version: z.string().min(1),
  authors: z.array(z.string()).min(1),
  description_short: z.string(),
  github_url: z.string().url().optional(),
  paper_url: z.string().url().optional(),
  relics: z.array(relicSchema),
})

export const modelInfoSchema = z.object({
  provider: z.enum(['anthropic', 'openai', 'google', 'qwen', 'other']),
  name: z.string().min(1),
  id: z.string().min(1),
  tier_breakdown: z.record(z.enum(['fast', 'strategic', 'analysis']), z.string()).optional(),
})

export const characterSchema = z.enum(['Silent', 'Regent', 'Watcher', 'Defect', 'Ironclad'])

export const aggregateSchema = z.object({
  ceiling: ascensionSchema,
  ceiling_consistency: z.number().min(0).max(1),
  progress_score_mean: z.number().nonnegative(),
  progress_score_max: z.number().nonnegative(),
  avg_final_floor: z.number().nonnegative(),
  max_final_floor: z.number().nonnegative(),
  total_runs: z.number().int().nonnegative(),
  total_victories: z.number().int().nonnegative(),
})

export const costSchema = z.object({
  total_usd: z.number().nonnegative(),
  total_input_tokens: z.number().int().nonnegative(),
  total_output_tokens: z.number().int().nonnegative(),
  cost_per_run_usd: z.number().nonnegative(),
  cost_per_ascension_unlocked_usd: z.number().nonnegative(),
})

export const submissionSchema = z.object({
  id: z.string().min(1),
  method: methodInfoSchema,
  model: modelInfoSchema,
  character: characterSchema,
  runs: z.array(runSummarySchema).min(1),
  aggregate: aggregateSchema,
  cost: costSchema,
  submitted_at: z.string(),
  verified: z.boolean(),
})

export const submissionBundleSchema = z.object({
  schema_version: z.literal('1.0'),
  built_at: z.string(),
  submissions: z.array(submissionSchema),
})
