import test from 'node:test'
import assert from 'node:assert'
import { parseSource, serializeSource, type ReportSource } from '../src/types.ts'

test('ReportSource namespace serialization and parsing', () => {
  // 1. Synthetic demo
  assert.strictEqual(serializeSource({ kind: 'demo' }), 'demo:synthetic')
  assert.deepStrictEqual(parseSource('demo:synthetic'), { kind: 'demo' })
  assert.deepStrictEqual(parseSource('demo'), { kind: 'demo' })

  // 2. Normal job
  assert.strictEqual(serializeSource({ kind: 'job', id: 'job-123' }), 'job:job-123')
  assert.deepStrictEqual(parseSource('job:job-123'), { kind: 'job', id: 'job-123' })

  // 3. Collision proof: job named "demo"
  assert.strictEqual(serializeSource({ kind: 'job', id: 'demo' }), 'job:demo')
  assert.deepStrictEqual(parseSource('job:demo'), { kind: 'job', id: 'demo' })
  assert.notDeepStrictEqual(parseSource('job:demo'), { kind: 'demo' })
})

test('Disjoint namespace prevents routing collision for job named demo', async () => {
  const requests: string[] = []
  const originalFetch = globalThis.fetch
  globalThis.fetch = (async (input: RequestInfo | URL) => {
    const url = String(input)
    requests.push(url)
    if (url.includes('/api/v1/jobs/demo/report')) {
      return new Response(JSON.stringify({ demo: false, sample: { name: 'Real App' } }), { status: 200 })
    }
    if (url.includes('/api/v1/jobs/demo')) {
      return new Response(JSON.stringify({ id: 'demo', state: 'SUCCEEDED' }), { status: 200 })
    }
    if (url.includes('/api/v1/demo/report')) {
      return new Response(JSON.stringify({ demo: true, sample: { name: 'Synthetic App' } }), { status: 200 })
    }
    return new Response(JSON.stringify({}), { status: 200 })
  }) as typeof fetch

  try {
    const { loadJob, loadJobReport, loadReport } = await import('../src/api.ts')
    const signal = new AbortController().signal

    // Dispatch job named "demo"
    const jobSource: ReportSource = { kind: 'job', id: 'demo' }
    if (jobSource.kind === 'job') {
      await loadJob(jobSource.id, signal)
      await loadJobReport(jobSource.id, signal)
    }

    assert(requests.some(r => r.endsWith('/api/v1/jobs/demo')), 'Must request /api/v1/jobs/demo')
    assert(requests.some(r => r.endsWith('/api/v1/jobs/demo/report')), 'Must request /api/v1/jobs/demo/report')
    assert(!requests.some(r => r.endsWith('/api/v1/demo/report')), 'Must NOT request /api/v1/demo/report')

    // Reset and dispatch demo
    requests.length = 0
    const demoSource: ReportSource = { kind: 'demo' }
    if (demoSource.kind === 'demo') {
      await loadReport(signal)
    }

    assert(requests.some(r => r.endsWith('/api/v1/demo/report')), 'Must request /api/v1/demo/report')
    assert(!requests.some(r => r.endsWith('/api/v1/jobs/demo')), 'Must NOT request job endpoints')
  } finally {
    globalThis.fetch = originalFetch
  }
})
