import { describe, it, expect } from 'vitest'
import { submissionBundleSchema, submissionSchema } from '@/data/schemas'
import { readFileSync } from 'node:fs'
import { resolve } from 'node:path'

const validRun = {
  run_index: 1,
  ascension: 4,
  outcome: 'victory',
  final_floor: 50,
  final_act: 3,
  duration_seconds: 420,
  per_run_score: 450,
}

const validSubmission = {
  id: 'fake-hcm-gemini-v03',
  method: {
    name: 'HCM-Agent',
    version: 'v0.3',
    authors: ['Team Sneko'],
    description_short: 'Training-free HCM + skills + evolution',
    relics: [
      { id: 'memory-store', label: 'Memory Store', description: 'Retains episodic memory.' },
    ],
  },
  model: {
    provider: 'google',
    name: 'Gemini 3.1 Pro',
    id: 'gemini-3.1-pro-preview',
  },
  character: 'Silent',
  runs: [validRun],
  aggregate: {
    ceiling: 4,
    ceiling_consistency: 0.2,
    progress_score_mean: 250,
    progress_score_max: 450,
    avg_final_floor: 35,
    max_final_floor: 50,
    total_runs: 1,
    total_victories: 1,
  },
  cost: {
    total_usd: 12.4,
    total_input_tokens: 1_800_000,
    total_output_tokens: 600_000,
    cost_per_run_usd: 12.4,
    cost_per_ascension_unlocked_usd: 3.1,
  },
  submitted_at: '2026-04-17T10:00:00Z',
  verified: true,
}

describe('submissionSchema', () => {
  it('accepts a valid submission', () => {
    expect(() => submissionSchema.parse(validSubmission)).not.toThrow()
  })

  it('rejects ascension > 5', () => {
    expect(() => submissionSchema.parse({
      ...validSubmission,
      aggregate: { ...validSubmission.aggregate, ceiling: 6 },
    })).toThrow()
  })

  it('rejects unknown outcome', () => {
    expect(() => submissionSchema.parse({
      ...validSubmission,
      runs: [{ ...validRun, outcome: 'banana' }],
    })).toThrow()
  })

  it('rejects missing method.relics', () => {
    const bad: Record<string, unknown> = JSON.parse(JSON.stringify(validSubmission))
    const method = bad.method as Record<string, unknown>
    delete method.relics
    expect(() => submissionSchema.parse(bad)).toThrow()
  })
})

describe('submissionBundleSchema', () => {
  it('accepts a valid bundle', () => {
    expect(() => submissionBundleSchema.parse({
      schema_version: '1.0',
      built_at: '2026-04-17T10:00:00Z',
      submissions: [validSubmission],
    })).not.toThrow()
  })

  it('rejects unsupported schema_version', () => {
    expect(() => submissionBundleSchema.parse({
      schema_version: '2.0',
      built_at: '2026-04-17T10:00:00Z',
      submissions: [],
    })).toThrow()
  })
})

describe('fixture submissions.json', () => {
  it('validates against submissionBundleSchema', () => {
    const raw = readFileSync(
      resolve(__dirname, '../public/data/submissions.json'),
      'utf-8',
    )
    const data = JSON.parse(raw)
    expect(() => submissionBundleSchema.parse(data)).not.toThrow()
  })
})
