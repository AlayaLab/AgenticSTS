import { submissionBundleSchema } from './schemas'
import type { SubmissionBundle } from '@/types/submission'

export async function loadSubmissions(
  url = '/data/submissions.json',
): Promise<SubmissionBundle> {
  const res = await fetch(url)
  if (!res.ok) throw new Error(`HTTP ${res.status} loading submissions`)
  const raw = await res.json()
  return submissionBundleSchema.parse(raw) as SubmissionBundle
}
