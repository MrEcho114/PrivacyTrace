// Exercise compiled App.vue setup with Vue reactivity and controlled API responses.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript, compileTemplate } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

const file = path.join(__dirname, '../src/App.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'report-source-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

const typesCode = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/types.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const typesExports = {}
vm.runInNewContext(typesCode, { exports: typesExports })

function mount(jobs = [], fixture = null) {
  const requests = []
  const report = id => fixture ?? ({ demo: false, job: { id }, result: { issues: [] } })
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
      if (name === './types') return typesExports
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
  assert.equal(state.source.value.kind, 'demo')
  assert.equal(state.selectedSourceKey.value, 'demo:synthetic')
  assert.equal(state.report.value.demo, true)
  assert.deepEqual(requests, [['demo']])
})

for (const id of ['demo', 'job-demo', 'normal-job']) {
  test(`initial selection loads the real job ${id} and submits review to its raw ID`, async () => {
    const { state, requests } = mount([{ id, state: 'SUCCEEDED' }])
    await state.reload(true)
    assert.equal(state.source.value.kind, 'job')
    assert.equal(state.selectedSourceKey.value, `job:${id}`)
    assert.equal(state.report.value.demo, false)
    assert.equal(state.report.value.job.id, id)
    await state.review()
    assert.deepEqual(requests, [['job', id], ['report', id], ['review', id]])
  })
}

test('manual switching keeps real demo job and synthetic example distinct', async () => {
  const { state, requests } = mount([{ id: 'demo', state: 'SUCCEEDED' }])
  for (const source of ['job:demo', 'demo:synthetic', 'job:demo']) {
    state.selectedSourceKey.value = source
    await state.reload()
    assert.equal(state.report.value.demo, source === 'demo:synthetic')
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

const templateCode = compileTemplate({
  source: descriptor.template.content, filename: file, id: 'report-source-test',
  compilerOptions: { bindingMetadata: compiled.bindings },
}).code
const templateContext = { exports: {}, require: name => {
  if (name === 'vue') return vue
  throw new Error(name)
} }
vm.runInNewContext(ts.transpileModule(templateCode, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText, templateContext)
const { renderToString } = require('@vue/server-renderer')
async function html(state) {
  const setup = vue.proxyRefs(state)
  return renderToString(vue.createSSRApp({
    render() { return templateContext.exports.render(setup, [], {}, setup, {}, {}) },
  }))
}

test('candidate navigation is paginated and full artifacts are rendered once on demand', async () => {
  const doc = { id: 'policy-1', title: 'Fixture policy', version: '1', captured_at: '2026',
    source_type: 'APP_POLICY', artifact: { text: 'FULL_ARTIFACT_SENTINEL' + 'x'.repeat(199978), sha256: 'a'.repeat(64) },
    completeness: 'COMPLETE', extraction_status: 'PARTIAL', review_status: 'UNREVIEWED',
    attachments_status: 'NOT_CHECKED', applicability: {} }
  const issue = { id: 'issue-1', data_type: 'CAMERA', status: 'INSUFFICIENT_EVIDENCE',
    explanation: 'Controlled facts only', evidence_ids: [], policy_document_ids: ['policy-1'] }
  const fixture = { demo: false, job: { id: 'large', input_mode: 'APK', ruleset_version: '0.3.0' },
    sample: { name: 'Fixture', package_name: 'example.fixture', apk_sha256: 'b'.repeat(64),
      version_code: 1, permissions: [], dex_entries: [] },
    coverage: { status: 'COMPLETE', scanned_dex: [], failed_dex: [],
      limitations: [], behavior_limitations: [] }, tools: {}, reviews: [],
    result: { issues: [issue] }, evidence: [], behaviors: [],
    policy_documents: [doc], policy_claims: Array.from({ length: 2000 }, (_, i) => ({
      id: 'claim-' + i, data_type: 'CAMERA', document_id: 'policy-1', evidence_ids: [],
    })) }
  const { state } = mount([{ id: 'large', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  state.selected.value = issue
  let output = await html(state)
  assert.equal((output.match(/class="evidence-card"/g) ?? []).length, 20)
  assert.equal((output.match(/FULL_ARTIFACT_SENTINEL/g) ?? []).length, 0)
  state.openPolicy('policy-1')
  output = await html(state)
  assert.equal((output.match(/FULL_ARTIFACT_SENTINEL/g) ?? []).length, 1)
  state.provenanceToggle({ target: { open: false } })
  state.openPolicy('policy-1')
  output = await html(state)
  assert.equal((output.match(/FULL_ARTIFACT_SENTINEL/g) ?? []).length, 1)
  assert.equal(state.provenanceOpen.value, true)
  state.policyToggle({ target: { open: false } }, 'policy-1')
  assert.equal(state.provenanceOpen.value, true)
  assert.equal((await html(state)).includes('FULL_ARTIFACT_SENTINEL'), false)
  state.candidatePage.value = 1
  output = await html(state)
  assert.match(output, /claim-20/)
  assert.doesNotMatch(output, /claim-0 ·/)
})
