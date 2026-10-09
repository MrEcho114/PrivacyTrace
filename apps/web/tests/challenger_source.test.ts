import test from 'node:test'
import assert from 'node:assert'
import { parseSource, serializeSource, type ReportSource } from '../src/types.ts'

test('R4 Edge Case: Job IDs serialization and parse round-trips', () => {
  const cases = [
    { kind: 'job', id: 'demo' } as ReportSource,
    { kind: 'job', id: 'demo:synthetic' } as ReportSource,
    { kind: 'job', id: 'job:demo' } as ReportSource,
    { kind: 'job', id: 'job:job:demo' } as ReportSource,
    { kind: 'job', id: 'regular-uuid-1234' } as ReportSource,
    { kind: 'demo' } as ReportSource,
  ]

  for (const c of cases) {
    const serialized = serializeSource(c)
    const parsed = parseSource(serialized)
    assert.deepStrictEqual(parsed, c, `Round-trip failed for ${JSON.stringify(c)}: serialized=${serialized}`)
  }
})

test('R4 Edge Case: Select option values are distinct with no collisions', () => {
  const jobs = [
    { id: 'demo' },
    { id: 'demo:synthetic' },
    { id: 'job:demo' },
  ]

  const syntheticOptionValue = serializeSource({ kind: 'demo' })
  const jobOptionValues = jobs.map(j => serializeSource({ kind: 'job', id: j.id }))

  const allValues = [syntheticOptionValue, ...jobOptionValues]
  const uniqueValues = new Set(allValues)

  assert.strictEqual(allValues.length, 4)
  assert.strictEqual(uniqueValues.size, 4, 'All select option values must be pairwise distinct')

  assert.strictEqual(syntheticOptionValue, 'demo:synthetic')
  assert.strictEqual(jobOptionValues[0], 'job:demo')
  assert.strictEqual(jobOptionValues[1], 'job:demo:synthetic')
  assert.strictEqual(jobOptionValues[2], 'job:job:demo')
})

test('R4 Edge Case: API routing for edge-case job IDs', async () => {
  const edgeJobIds = ['demo', 'demo:synthetic', 'job:demo']

  for (const jobId of edgeJobIds) {
    const requests: string[] = []
    const originalFetch = globalThis.fetch

    const encodedId = encodeURIComponent(jobId)
    globalThis.fetch = (async (input: RequestInfo | URL) => {
      const url = String(input)
      requests.push(url)
      if (url.endsWith(`/api/v1/jobs/${encodedId}/report`)) {
        return new Response(JSON.stringify({ demo: false, sample: { name: `Real Job ${jobId}` } }), { status: 200 })
      }
      if (url.endsWith(`/api/v1/jobs/${encodedId}`)) {
        return new Response(JSON.stringify({ id: jobId, state: 'SUCCEEDED' }), { status: 200 })
      }
      return new Response(JSON.stringify({}), { status: 200 })
    }) as typeof fetch

    try {
      const { loadJob, loadJobReport } = await import('../src/api.ts')
      const signal = new AbortController().signal

      const source: ReportSource = { kind: 'job', id: jobId }
      if (source.kind === 'job') {
        await loadJob(source.id, signal)
        await loadJobReport(source.id, signal)
      }

      // Verify exact URLs (properly URI-encoded)
      assert(
        requests.some(r => r.endsWith(`/api/v1/jobs/${encodedId}`)),
        `Must request /api/v1/jobs/${encodedId}`
      )
      assert(
        requests.some(r => r.endsWith(`/api/v1/jobs/${encodedId}/report`)),
        `Must request /api/v1/jobs/${encodedId}/report`
      )
      // Must NOT request synthetic demo endpoint
      assert(
        !requests.some(r => r.includes('/api/v1/demo/report')),
        `Must never request /api/v1/demo/report for job ID ${jobId}`
      )
    } finally {
      globalThis.fetch = originalFetch
    }
  }
})
