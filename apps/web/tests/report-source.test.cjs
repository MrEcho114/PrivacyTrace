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
assert.ok(typesExports.sourceStatusLabels, 'typesExports must export sourceStatusLabels')

// Compile the real selector module rather than stubbing it, so the mounted
// component is exercised against the same paging logic the browser runs.
const sdkEvidenceCode = ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/sdkEvidence.ts'), 'utf8'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } },
).outputText
const sdkEvidenceExports = {}
vm.runInNewContext(sdkEvidenceCode, { exports: sdkEvidenceExports })

function mount(jobs = [], fixture = null, overrides = {}) {
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
    jobPath: id => `/api/v1/jobs/${encodeURIComponent(id)}`,
    jobReportPath: id => `/api/v1/jobs/${encodeURIComponent(id)}/report`,
    isNotFoundFor: (cause, path) => cause instanceof Error && cause.status === 404 && cause.path === path,
    ...overrides,
  }
  let unmount
  const context = {
    exports: {}, AbortController, setTimeout, clearTimeout,
    require: name => {
      if (name === './api') return api
      if (name === './types') return typesExports
      if (name === './workflow') return { sourceStatusLabels: typesExports.sourceStatusLabels }
      if (name === './sdkEvidence') return sdkEvidenceExports
      if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount(fn) { unmount = fn } }
      throw new Error(`Unexpected import: ${name}`)
    },
  }
  vm.runInNewContext(javascript, context, { filename: file })
  const state = context.exports.default.setup({}, { expose() {} })
  return { state, requests, unmount: () => unmount() }
}

function http404(path) {
  const failure = new Error('服务返回 404，请确认后端正在运行。')
  failure.status = 404
  failure.path = path
  return failure
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

test('a 404 from the job entity removes it and falls back to the synthetic example', async () => {
  const { state } = mount([{ id: 'gone', state: 'SUCCEEDED' }], null, {
    loadJob: async () => { throw http404('/api/v1/jobs/gone') },
  })
  await state.reload(true)
  assert.equal(state.source.value.kind, 'demo')
  assert.deepEqual(state.jobs.value, [])
  assert.deepEqual(Array.from(state.removedJobIds.value), ['gone'])
  assert.equal(state.error.value, '任务已删除，界面已移除该任务。')
})

test('a missing report keeps the job and its list entry visible', async () => {
  const job = { id: 'kept', state: 'SUCCEEDED' }
  const { state } = mount([job], null, {
    loadJobReport: async () => { throw http404('/api/v1/jobs/kept/report') },
  })
  await state.reload(true)
  assert.equal(state.source.value.kind, 'job')
  assert.deepEqual(state.jobs.value.map(item => item.id), ['kept'])
  assert.equal(state.activeJob.value.id, 'kept')
  assert.equal(state.report.value, null)
  assert.deepEqual(Array.from(state.removedJobIds.value), [])
  assert.match(state.error.value, /报告不可用/)
})

for (const [label, override] of [
  ['job list', { loadJobs: async () => { throw http404('/api/v1/jobs') } }],
  ['taxonomy', { loadTaxonomy: async () => { throw http404('/api/v1/taxonomy') } }],
]) {
  test(`a 404 from the ${label} does not remove the selected job`, async () => {
    const job = { id: 'kept', state: 'SUCCEEDED' }
    const { state } = mount([job], null, override)
    state.jobs.value = [job]
    state.source.value = { kind: 'job', id: 'kept' }
    await state.reload()
    assert.deepEqual(state.jobs.value.map(item => item.id), ['kept'])
    assert.equal(state.source.value.kind, 'job')
    assert.deepEqual(Array.from(state.removedJobIds.value), [])
    assert.match(state.error.value, /请求失败|服务返回 404/)
  })
}

test('a removed job stays hidden when a stale list still contains it', async () => {
  const job = { id: 'deleted', state: 'SUCCEEDED' }
  const { state } = mount([job])
  state.removedJobIds.value = ['deleted']
  await state.reload()
  assert.deepEqual(state.jobs.value, [])
  assert.equal(state.source.value.kind, 'demo')
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

function sdkFixture(evidence, limitations = []) {
  return {
    demo: false,
    job: { id: 'sdk-job', input_mode: 'APK', ruleset_version: '0.3.0' },
    sample: {
      name: 'SDK fixture', package_name: 'example.sdk', apk_sha256: 'c'.repeat(64),
      version_code: 1, permissions: [], dex_entries: ['classes.dex'],
    },
    coverage: {
      status: 'COMPLETE', scanned_dex: ['classes.dex'], failed_dex: [],
      limitations: [], behavior_limitations: [],
      sdk_attribution_limitations: limitations,
    },
    tools: {}, reviews: [], behaviors: [], policy_documents: [], policy_claims: [],
    // No issues: nothing cites this evidence, which is exactly the reported gap.
    result: { issues: [] },
    evidence,
  }
}

function sdkEvidenceRecord(index) {
  return {
    id: 'ev-sdk-' + index, kind: 'SDK', status: 'STATIC_POTENTIAL',
    source: 'classes.dex',
    locator: 'apk_sha256=' + 'c'.repeat(64) + ';dex=classes.dex;class=com.example.C' + index,
    excerpt: 'com.example.C' + index + ' matches published package prefix com.example of Example SDK (Example Ltd); attribution only, not evidence of collection or transfer.',
  }
}

test('SDK evidence is rendered even when no issue cites it', async () => {
  // The reported P1: selectedEvidence only shows issue-cited records, so SDK
  // evidence had no way into the page at all.
  const fixture = sdkFixture([sdkEvidenceRecord(1), sdkEvidenceRecord(2)])
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  assert.equal(state.selected.value, null)
  const output = await html(state)
  assert.match(output, /第三方 SDK 归属/)
  assert.equal((output.match(/class="evidence-card"/g) ?? []).length, 2)
  assert.match(output, /com\.example\.C1/)
  assert.match(output, /com\.example\.C2/)
})

test('only SDK records reach the SDK panel', async () => {
  const fixture = sdkFixture([
    sdkEvidenceRecord(1),
    { id: 'ev-manifest-1', kind: 'MANIFEST', status: 'STATIC_POTENTIAL',
      source: 'AndroidManifest.xml', locator: 'MANIFEST_SENTINEL', excerpt: 'MANIFEST_SENTINEL' },
  ])
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  assert.deepEqual(state.sdkEvidence.value.map((item) => item.id), ['ev-sdk-1'])
  const output = await html(state)
  assert.doesNotMatch(output, /MANIFEST_SENTINEL/)
})

test('zero SDK hits states the limit instead of implying the APK is clean', async () => {
  const fixture = sdkFixture([])
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  const output = await html(state)
  assert.match(output, /第三方 SDK 归属/)
  assert.match(output, /未命中当前有限的签名规则集/)
  assert.match(output, /没有命中不代表 APK 不含第三方 SDK/)
  assert.equal((output.match(/class="evidence-card"/g) ?? []).length, 0)
})

test('a large SDK result is paginated without losing or repeating entries', async () => {
  const total = 30
  const fixture = sdkFixture(Array.from({ length: total }, (_, i) => sdkEvidenceRecord(i)))
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  assert.equal(state.sdkPageTotal.value, 2)

  let output = await html(state)
  assert.equal((output.match(/class="evidence-card"/g) ?? []).length, 25)
  assert.match(output, /共 30 条 · 第 1 \/ 2 页/)
  assert.match(output, /com\.example\.C0/)
  assert.doesNotMatch(output, /com\.example\.C29/)

  state.sdkPage.value = 1
  output = await html(state)
  assert.equal((output.match(/class="evidence-card"/g) ?? []).length, 5)
  assert.match(output, /com\.example\.C29/)
  assert.doesNotMatch(output, /com\.example\.C0\b/)
})

test('switching the report resets the SDK page but changing the issue does not', async () => {
  const fixture = sdkFixture(Array.from({ length: 30 }, (_, i) => sdkEvidenceRecord(i)))
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  state.sdkPage.value = 1
  state.selected.value = { id: 'issue-x', data_type: 'CAMERA', evidence_ids: [] }
  assert.equal(state.sdkPage.value, 1, 'issue selection must not move the page')
  await state.reload(true)
  assert.equal(state.sdkPage.value, 0, 'a new report starts on page 1')
})

test('the panel stays visible when nothing was truncated', async () => {
  // A capped run adds a limitation note; an uncapped run must still show the panel.
  const fixture = sdkFixture([sdkEvidenceRecord(1)])
  const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
  await state.reload(true)
  assert.deepEqual(state.realReport.value.coverage.sdk_attribution_limitations, [])
  const output = await html(state)
  assert.match(output, /第三方 SDK 归属/)
  assert.match(output, /不参与政策一致性判定/)
})

test('failed controlled source APK keeps its provenance without a report', async () => {
  const { state } = mount([{ id: 'failed-controlled', state: 'FAILED',
    input_mode: 'CONTROLLED_APK', source_origin: 'CONTROLLED' }])
  await state.reload(true)
  assert.equal(state.report.value, null)
  assert.equal(state.sourceInfo.value.label, 'CONTROLLED_APK · 自建受控场景')
})

test('historical unknown and UI fixture reports do not claim an actual CLI scan', async () => {
  for (const origin of ['UNKNOWN', 'CONTROLLED']) {
    const fixture = sdkFixture([])
    fixture.job.source_origin = origin
    fixture.job.created_at = '2026-10-09T00:00:00Z'
    const { state } = mount([{ id: 'sdk-job', state: 'SUCCEEDED' }], fixture)
    await state.reload(true)
    const output = await html(state)
    assert.match(output, /记录创建时点/)
    assert.match(output, /未留存分析生成时点/)
    assert.doesNotMatch(output, /CLI 实际扫描生成/)
  }
})
