// Exercise compiled App.vue setup with Vue reactivity and controlled API responses.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

const file = path.join(__dirname, '../src/App.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'report-source-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

function mount(jobs = []) {
  const requests = []
  const report = id => ({ demo: false, job: { id }, result: { issues: [] } })
  const api = {
    loadJobs: async () => ({ jobs }),
    loadTaxonomy: async () => ({ data_types: [] }),
    loadReport: async () => { requests.push(['demo']); return { demo: true } },
    loadJob: async id => { requests.push(['job', id]); return jobs.find(job => job.id === id) },
    loadJobReport: async id => { requests.push(['report', id]); return report(id) },
    cancelJob: async id => { requests.push(['cancel', id]); return { id, state: 'CANCELLED' } },
    submitReview: async id => { requests.push(['review', id]); return report(id) },
  }
  let unmount
  const context = {
    exports: {}, AbortController, setTimeout, clearTimeout,
    require: name => {
      if (name === './api') return api
      if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount(fn) { unmount = fn } }
      throw new Error(`Unexpected import: ${name}`)
    },
  }
  vm.runInNewContext(javascript, context, { filename: file })
  const state = context.exports.default.setup({}, { expose() {} })
  return { state, requests, unmount: () => unmount() }
}

test('empty job list loads the labelled synthetic example', async () => {
  const { state, requests } = mount()
  await state.reload(true)
  assert.equal(state.source.value, 'demo')
  assert.equal(state.report.value.demo, true)
  assert.deepEqual(requests, [['demo']])
})

for (const id of ['demo', 'job-demo', 'normal-job']) {
  test(`initial selection loads the real job ${id} and submits review to its raw ID`, async () => {
    const { state, requests } = mount([{ id, state: 'SUCCEEDED' }])
    await state.reload(true)
    assert.equal(state.source.value, `job:${id}`)
    assert.equal(state.report.value.demo, false)
    assert.equal(state.report.value.job.id, id)
    await state.review()
    assert.deepEqual(requests, [['job', id], ['report', id], ['review', id]])
  })
}

test('manual switching keeps real demo job and synthetic example distinct', async () => {
  const { state, requests } = mount([{ id: 'demo', state: 'SUCCEEDED' }])
  for (const source of ['job:demo', 'demo', 'job:demo']) {
    state.source.value = source
    await state.reload()
    assert.equal(state.report.value.demo, source === 'demo')
  }
  assert.deepEqual(requests, [
    ['job', 'demo'], ['report', 'demo'], ['demo'], ['job', 'demo'], ['report', 'demo'],
  ])
})

test('cancellation of a running job named demo targets the real job', async () => {
  const { state, requests, unmount } = mount([{ id: 'demo', state: 'STATIC_ANALYSIS' }])
  try {
    await state.reload(true)
    assert.equal(state.report.value, null)
    await state.cancel()
    assert.equal(state.activeJob.value.state, 'CANCELLED')
    assert.deepEqual(requests, [['job', 'demo'], ['cancel', 'demo']])
  } finally { unmount() }
})
