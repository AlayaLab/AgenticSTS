import { describe, it, expect, vi, beforeEach } from 'vitest'
import { loadSubmissions } from '@/data/loadSubmissions'

const validBundle = {
  schema_version: '1.0',
  built_at: '2026-04-17T12:00:00Z',
  submissions: [],
}

describe('loadSubmissions', () => {
  beforeEach(() => {
    vi.restoreAllMocks()
  })

  it('fetches /data/submissions.json and returns parsed bundle', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => validBundle,
    })
    vi.stubGlobal('fetch', fetchMock)

    const bundle = await loadSubmissions()
    expect(fetchMock).toHaveBeenCalledWith('/data/submissions.json')
    expect(bundle.schema_version).toBe('1.0')
  })

  it('throws if HTTP fails', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: false, status: 500 }))
    await expect(loadSubmissions()).rejects.toThrow(/HTTP 500/)
  })

  it('throws on schema validation failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ schema_version: '9.9', built_at: '', submissions: [] }),
    }))
    await expect(loadSubmissions()).rejects.toThrow()
  })
})
