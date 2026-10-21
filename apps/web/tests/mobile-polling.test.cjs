// The real Android repro is recorded under docs/acceptance/issue133. This fast
// guard models the native transport's measured HTTP fan-out, not a timer value.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const ts = require('typescript')

test('a restored long task leaves default request budget for cancellation', async () => {
  let now = 0, sequence = 0
  const scheduled = new Map(), requests = [], actions = []
  const cache = new Map()
  function load(file) {
    if (cache.has(file)) return cache.get(file).exports
    const module = { exports: {} }
    cache.set(file, module)
    const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
      compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
    }).outputText
    const context = {
      module, exports: module.exports, crypto: require('node:crypto').webcrypto,
      setTimeout(fn, delay) { const id = ++sequence; scheduled.set(id, { fn, at: now + delay }); return id },
      clearTimeout(id) { scheduled.delete(id) },
      require(name) {
        return name.startsWith('.') ? load(path.resolve(path.dirname(file), name + '.ts')) : require(name)
      },
    }
    vm.runInNewContext(code, context, { filename: file })
    return module.exports
  }
  function consume(count) {
    for (let index = 0; index < count; index++) {
      const inWindow = requests.filter(at => at > now - 60000).length
      if (inWindow >= 60) throw 'SERVER_BUSY'
      requests.push(now)
    }
  }
  const context = { origin: 'https://lane-e.example/', draft: 'd'.repeat(32), state: 'SERVER_CONFIRMED' }
  let job = { id: 'a'.repeat(32), state: 'QUEUED' }
  const draft = { id: context.draft, revision: 1, sources: [], candidates: [], jobs: [{ job_id: job.id, events: [] }] }
  const bridge = {
    async restore() { consume(2); return context },
    async cancel() {},
    async request(action) {
      actions.push(action)
      // AnalysisTransport.workflow reconciles capabilities and the draft first.
      consume(action === 'read' ? 2 : 3)
      if (action === 'cancel-job') job = { ...job, state: 'CANCELLED' }
      const data = action === 'read' ? draft : action === 'taxonomy' ? { data_types: [] } : job
      return { origin: context.origin, draft: context.draft, data }
    },
  }
  const { createMobileFlow } = load(path.resolve(__dirname, '../src/mobile/flow.ts'))
  const flow = createMobileFlow(bridge)
  await flow.select(true)
  while (scheduled.size) {
    const [id, timer] = [...scheduled.entries()].sort((a, b) => a[1].at - b[1].at)[0]
    if (timer.at > 180000) break
    scheduled.delete(id); now = timer.at
    await timer.fn()
  }
  assert.equal(flow.error.value, '', 'automatic native reads must not exhaust 60 requests/minute')
  assert.ok(requests.some(at => at >= 120000), 'keep reading across multiple rate-limit windows')
  assert.ok(actions.filter(action => action === 'job').length > 2, 'perform automatic progress reads')
  assert.ok(scheduled.size > 0, 'a running task still has its next automatic read scheduled')
  assert.equal(flow.job.value.id, job.id)
  await flow.control('cancel-job')
  assert.equal(flow.error.value, '', 'leave budget for a real cancel action')
  assert.equal(flow.job.value.state, 'CANCELLED')
  assert.equal(actions.filter(action => action === 'cancel-job').length, 1)
  assert.equal(actions.filter(action => action === 'start' || action === 'retry-job').length, 0)
  assert.equal(scheduled.size, 0, 'terminal cancellation stops polling')
})
