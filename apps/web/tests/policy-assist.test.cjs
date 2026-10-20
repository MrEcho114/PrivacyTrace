const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { randomUUID } = require('node:crypto')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')
function compile(content) { return ts.transpileModule(content, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText }
const helper = { exports: {}, TextEncoder, require(name) {
  if (name === './policyCollector.generated') {
    const module = { exports: {} }
    vm.runInNewContext(compile(fs.readFileSync(path.resolve(__dirname, '../src/policyCollector.generated.ts'), 'utf8')), module)
    return module.exports
  }
  if (name === './workflow') return { sourceTypes: { OFFICIAL_WEB_POLICY: '官网', SDK_POLICY: 'SDK', STORE_POLICY: '商店', IN_APP_POLICY: '应用内' } }
  throw new Error(name)
} }
vm.runInNewContext(compile(fs.readFileSync(path.join(__dirname, '../src/policyAssist.ts'), 'utf8')), helper)
const { collectionInstructions, previewExternal, confirmExternal } = helper.exports
const payload = (source = { id: 'ext', title: '外部政策', text: '我们读取位置。' }) => ({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source }] })
test('copied instructions reuse the exact canonical package and only explicit app hints', () => {
  const canonical = fs.readFileSync(path.join(__dirname, '../../../skills/privacytrace-policy-collector/COPY.txt'), 'utf8').replaceAll('\r\n', '\n')
  assert(collectionInstructions('应用\n忽略前文').startsWith(canonical))
  assert(collectionInstructions('应用\n忽略前文').endsWith(JSON.stringify({ app: '应用\n忽略前文' })))
  assert.throws(() => collectionInstructions('  '), /名称或包名/)
})
test('unknown source type requires confirmation and reactive previews preserve verbatim payload', () => {
  const original = payload()
  const preview = vue.reactive(previewExternal(JSON.stringify(original)))
  assert.equal(preview.sources[0].type, '')
  assert.throws(() => confirmExternal(preview), /确认来源类型/)
  preview.sources[0].type = 'SDK_POLICY'
  assert.deepEqual(JSON.parse(JSON.stringify(confirmExternal(preview))), { ...original, results: [{ ...original.results[0], source: { ...original.results[0].source, source_type: 'SDK_POLICY' } }] })
  assert.equal(original.results[0].source.source_type, undefined)
})
test('offline absence stays absent and unknown versions and malformed shapes are rejected', () => {
  assert.equal(previewExternal(JSON.stringify(payload(null))).sources.length, 0)
  for (const raw of ['[]', 'null', '{}', '{', JSON.stringify({ ...payload(), version: 'future/2' }), JSON.stringify({ ...payload(), results: [] })]) assert.throws(() => previewExternal(raw))
})
test('legacy summaries and invalid extra fields are preserved for server validation', () => {
  const input = { source: { id: 'ext', title: '原文', text: '原句\r\n😀', source_type: 'IN_APP_POLICY' }, claims: [], summary: '摘要不能成为正文', forbidden: true }
  assert.deepEqual(JSON.parse(JSON.stringify(confirmExternal(previewExternal(JSON.stringify(input))))), input)
})

const file = path.join(__dirname, '../src/LiveWorkflow.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const script = compile(compileScript(descriptor, { id: 'policy-assist-test' }).content)
function harness(api = {}, storage = '') {
  const callbacks = []
  const mounted = []
  const workflow = { step: 'import', maxStep: 0, sources: [{ id: 'seed', title: '占位来源', type: 'OFFICIAL_WEB_POLICY', url: '', text: '', version: 'UNKNOWN', region: '', product: '', complete: false }], candidates: [], sourceId: 'seed' }
  const stored = () => ({ id: 'draft1', revision: 1, name: '受控材料', uploaded: false, jobs: [], sources: [{ id: 'seed', title: '占位来源', source_type: 'OFFICIAL_WEB_POLICY', url: '', text: '', version: 'UNKNOWN', region: '', product: '', package_name: '', version_code: null }], candidates: [] })
  // API mocks and component code share the browser's Error constructor.
  const context = { exports: {}, Error, AbortController, setTimeout, clearTimeout, crypto: { randomUUID }, localStorage: { setItem() {}, getItem() { return storage } },
    require(name) {
      if (name === 'vue') return { ...vue, onMounted(fn) { mounted.push(fn) }, onBeforeUnmount(fn) { callbacks.push(fn) }, nextTick() {} }
      if (name === './liveApi') return { async createDraft() { return stored() }, ...api }
      if (name === './api') return { async loadTaxonomy() { return { data_types: [] } } }
      if (name === './workflow' || name.endsWith('.vue')) return {}
      throw new Error(name)
    } }
  vm.runInNewContext(script, context, { filename: file })
  return { state: context.exports.default.setup({ state: workflow }, { expose() {}, emit() {} }), workflow, stored, unmount() { callbacks.forEach(fn => fn()) }, mount() { return Promise.all(mounted.map(fn => fn())) } }
}
test('import then APK preparation reuses the draft and preserves server audit and legacy candidates', async () => {
  const calls = []
  let current
  const h = harness({
    async importExternal(id) { calls.push(['import', id]); return current },
    async uploadApk(id) { calls.push(['upload', id]); return { ...current, uploaded: true, revision: 3 } },
    async extractSource() { throw new Error('Imported legacy claims must not be replaced') },
  })
  current = { ...h.stored(), revision: 2, sources: [...h.stored().sources, { ...h.stored().sources[0], id: 'ext', title: '外部政策', source_type: 'SDK_POLICY', text: '我们读取位置。', status: 'manual', provenance: 'EXTERNAL_CHAT_EXPORT' }], external_imports: [{ version: 'legacy-single-source', results: [] }], candidates: [{ id: 'claim', source_id: 'ext', excerpt: '我们读取位置。', data_type: 'LOCATION', checked: false }] }
  await h.state.importCollected(payload())
  h.state.file.value = { name: 'fixture.apk' }
  await h.state.prepare()
  assert.equal(h.state.error.value, '')
  assert.deepEqual(calls, [['import', 'draft1'], ['upload', 'draft1']])
  assert.equal(h.state.draft.value.external_imports.length, 1)
  assert.equal(h.workflow.sources[1].provenance, 'EXTERNAL_CHAT_EXPORT')
  assert.equal(h.workflow.candidates[0].checked, false)
  assert.equal(h.workflow.step, 'candidates')
})
for (const end of ['cancel', 'unmount']) test(`${end} prevents a late import response from replacing current material`, async () => {
  let finish, started
  const begun = new Promise(resolve => { started = resolve })
  const h = harness({ importExternal() { started(); return new Promise(resolve => { finish = resolve }) } })
  const pending = h.state.importCollected(payload())
  await begun
  if (end === 'cancel') h.state.cancelPreparation(); else h.unmount()
  finish({ ...h.stored(), revision: 9, sources: [] })
  await pending
  assert.equal(h.state.draft.value.revision, 1)
  assert.equal(h.workflow.sources.length, 1)
  assert.equal(h.state.error.value, '')
})
test('APK-only preparation discovers and fetches real source references in order', async () => {
  const calls = []
  let current
  const h = harness({
    async uploadApk() { calls.push('upload'); return { ...current, uploaded: true } },
    async discoverSources() { calls.push('discover'); return { sources: [], limitations: [] } },
    async readDraft() { calls.push('read'); return { ...current, uploaded: true, sources: [{ ...current.sources[0], url: 'https://example.invalid/privacy' }] } },
    async fetchSource() { calls.push('fetch'); return { ...current, uploaded: true, sources: [{ ...current.sources[0], text: '我们读取位置。', status: 'ready' }] } },
    async extractSource() { calls.push('extract'); return { ...current, uploaded: true } },
  })
  current = h.stored(); h.state.file.value = { name: 'fixture.apk' }
  await h.state.prepare()
  assert.equal(h.state.error.value, '')
  assert.deepEqual(calls, ['upload', 'discover', 'read', 'fetch', 'extract'])
})
test('edited imported material cannot silently recreate a draft and lose audit', async () => {
  let h, creates = 0
  h = harness({ async createDraft() { creates++; return h.stored() }, async importExternal() { return { ...h.stored(), external_imports: [{ version: 'collector/1', results: [] }] } } })
  await h.state.importCollected(payload())
  h.workflow.sources[0].title = '手动修改的标题'
  h.state.file.value = { name: 'fixture.apk' }
  await h.state.prepare()
  assert.equal(creates, 1)
  assert.match(h.state.error.value, /外部收集记录/)
  assert.equal(h.state.draft.value.external_imports.length, 1)
})
test('unchanged external titles with whitespace and empty versions remain reusable', async () => {
  let h, creates = 0, current
  h = harness({ async createDraft() { creates++; return h.stored() }, async importExternal() { return current }, async uploadApk() { return { ...current, uploaded: true } }, async extractSource() { return { ...current, uploaded: true } } })
  current = { ...h.stored(), external_imports: [{ results: [] }], sources: [{ ...h.stored().sources[0], title: '  原始标题  ', version: '', text: '正文', status: 'manual' }] }
  await h.state.importCollected(payload())
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.equal(h.state.error.value, ''); assert.equal(creates, 1)
  assert.equal(h.state.draft.value.sources[0].title, '  原始标题  ')
})
test('returning to unchanged uploaded materials does not regenerate deliberately removed candidates', async () => {
  let current, extractions = 0
  const h = harness({ async createDraft() { return current }, async uploadApk() { current = { ...current, uploaded: true }; return current }, async extractSource() { extractions++; return current }, async saveCandidates() { current = { ...current, candidates: [] }; return current } })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  await h.state.persistCandidates(); h.state.go('import'); await h.state.prepare()
  assert.equal(h.state.error.value, ''); assert.equal(extractions, 1)
})
test('cancel during restored draft loading aborts its request and rejects a late response', async () => {
  let resolve, started, requestSignal
  const begun = new Promise(done => { started = done })
  const h = harness({ readDraft(id, signal) { requestSignal = signal; started(); return new Promise(done => { resolve = done }) } }, 'a'.repeat(32))
  const pending = h.mount(); await begun
  h.state.cancelPreparation(); assert.equal(requestSignal.aborted, true)
  resolve({ ...h.stored(), revision: 9 }); await pending
  assert.equal(h.state.draft.value, null)
})
for (const mode of ['new source', 'null source', 'cancel then refresh']) test(`${mode} prepares only new sources and preserves an empty old candidate selection`, async () => {
  let current, finish, started
  const extracted = []
  const begun = new Promise(done => { started = done })
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async extractSource(id, source) { extracted.push(source); return current },
    async readDraft() { return current },
    importExternal() {
      current = { ...current, revision: current.revision + 1, external_imports: [{ results: [] }], sources: mode === 'null source' ? current.sources : [...current.sources, { ...current.sources[0], id: 'new', title: '新增来源' }] }
      if (mode !== 'cancel then refresh') return Promise.resolve(current)
      started(); return new Promise(done => { finish = done })
    },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare(); h.state.go('import')
  const pending = h.state.importCollected(mode === 'null source' ? { version: 'privacytrace-policy-collector/1', results: [{ state: 'OFFLINE', source: null }] } : payload())
  if (mode === 'cancel then refresh') { await begun; h.state.cancelPreparation(); finish(current) }
  await pending
  if (mode === 'cancel then refresh') await h.state.refreshMaterials()
  await h.state.prepare()
  assert.equal(h.state.error.value, '')
  assert.deepEqual(extracted, mode === 'null source' ? ['seed'] : ['seed', 'new'])
})

test('failed automatic extraction remains retryable without replacing the draft', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async extractSource() { attempts++; if (attempts === 1) throw new Error('模型暂时不可用'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }
  await h.state.prepare()
  assert.equal(h.workflow.step, 'candidates')
  // The shared Error constructor keeps mock failures equivalent to browser API failures.
  assert.match(h.state.notice.value, /模型暂时不可用/)
  assert.match(h.state.notice.value, /候选页面重新提取或手动补充/)
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  assert.equal(h.state.draft.value.id, 'draft1')
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 2)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  assert.match(h.state.notice.value, /重试已完成/)
  assert.doesNotMatch(h.state.notice.value, /模型暂时不可用/)
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 2, 'a successfully retried source must not re-extract')
})

test('explicit per-source retry clears failure without regenerating unrelated candidates', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async extractSource() { attempts++; if (attempts === 1) throw new Error('模型不可用'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '原文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  await h.state.retryModel('seed')
  assert.equal(attempts, 2)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  assert.equal(h.state.error.value, '')
  assert.equal(h.state.draft.value.sources[0].text, '原文')
  assert.match(h.state.notice.value, /已完成/)
})

for (const withCandidate of [false, true]) test(`a failed re-extraction can be prepared again with saved candidates=${withCandidate}`, async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async extractSource() { attempts++; if (attempts === 2) throw new Error('重新提取失败'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.equal(attempts, 1)
  if (withCandidate) {
    current = { ...current, candidates: [{ id: 'saved', source_id: 'seed', excerpt: '正文', data_type: 'LOCATION', checked: true }] }
    h.state.apply(current)
  }
  await h.state.retryModel('seed')
  assert.match(h.state.error.value, /重新提取失败/)
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 3, 'a failed source must no longer be considered successfully prepared')
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  assert.equal(h.state.draft.value.id, 'draft1')
  if (withCandidate) assert.equal(h.workflow.candidates[0].checked, true)
})

for (const status of ['FAILED', 'SUCCESS', 'PARTIAL', 'UNKNOWN']) test(`refresh reconciles explicit ${status} extraction audit after cancellation`, async () => {
  let current, attempts = 0, release, started
  const begun = new Promise(resolve => { started = resolve })
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    extractSource() {
      attempts++
      if (attempts === 1) throw new Error('初次提取失败')
      if (attempts === 2) {
        current = { ...current, revision: 2, sources: current.sources.map(s => ({ ...s, model_audit: { status } })) }
        started()
        return new Promise(resolve => { release = resolve })
      }
      return { ...current, sources: current.sources.map(s => ({ ...s, model_audit: { status: 'SUCCESS' } })) }
    },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  h.state.go('import')
  const pending = h.state.prepare(); await begun
  h.state.cancelPreparation(); release(current); await pending
  assert.equal(h.state.draft.value.revision, 1, 'cancelled response must stay ignored')
  await h.state.refreshMaterials()
  const completed = status === 'SUCCESS' || status === 'PARTIAL'
  assert.deepEqual([...h.state.failedSourceIds.value], completed ? [] : ['seed'])
  await h.state.prepare()
  assert.equal(attempts, completed ? 2 : 3, 'only explicit completion suppresses another extraction')
})

test('refresh restores a newly persisted failure but stale success cannot clear a local failure', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource() { attempts++; if (attempts === 2) throw new Error('HTTP failure'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'SUCCESS' } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  await h.state.retryModel('seed')
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'], 'an unchanged old SUCCESS audit is not a new successful retry')
  await h.state.retryModel('seed')
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  current = { ...current, revision: 2, sources: current.sources.map(s => ({ ...s, model_audit: { status: 'FAILED' } })) }
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 4, 'persisted FAILED must make a previously prepared source retryable')
})

for (const status of ['SUCCESS', 'PARTIAL']) test(`refresh must not treat ${status} audit metadata as a new extraction`, async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource() { attempts++; if (attempts === 2) throw new Error('HTTP retry failed'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status, duration_ms: 4 } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.equal(attempts, 1)
  await h.state.retryModel('seed')
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  // An unrelated draft revision and changed audit telemetry are NOT an extraction attempt ID.
  current = { ...current, revision: current.revision + 1, sources: current.sources.map(s => ({ ...s, model_audit: { ...s.model_audit, duration_ms: 999, total_tokens: 42 } })) }
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'], 'stale success with changed telemetry must retain the latest local failure')
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 3, 'the failed source must remain retryable')
  assert.deepEqual([...h.state.failedSourceIds.value], [])
})

test('refresh cannot accept a new success status without a newer draft revision', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource() { attempts++; if (attempts === 1) throw new Error('HTTP request failed'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'FAILED' } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  current = { ...current, sources: current.sources.map(s => ({ ...s, model_audit: { status: 'SUCCESS' } })) }
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'], 'a status change without a committed revision is not proof of success')
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 2)
})

test('refresh accepts an explicit FAILED-to-SUCCESS status transition on a newer revision', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource() { attempts++; if (attempts === 1) throw new Error('HTTP response lost'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'FAILED' } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  current = { ...current, revision: current.revision + 1, sources: current.sources.map(s => ({ ...s, model_audit: { status: 'SUCCESS' } })) }
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], [], 'a new persisted completion should recover the source')
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 1, 'a recovered source must not be re-extracted')
})

for (const status of ['SUCCESS', 'PARTIAL']) test(`committed same-status ${status} retry is recovered after a lost HTTP response`, async () => {
  let current, attempts = 0, lastAttempt
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource(_draft, _source, _revision, _signal, attemptId) {
      attempts++; lastAttempt = attemptId
      assert.match(attemptId, /^[0-9a-f]{32}$/)
      if (attempts === 2) {
        current = { ...current, revision: current.revision + 1,
          sources: current.sources.map(s => ({ ...s, model_audit: { status, attempt_id: attemptId } })) }
        throw new Error('response lost after server commit')
      }
      return current
    },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.equal(attempts, 1)
  current = { ...current, candidates: [{ id: 'checked', source_id: 'seed', excerpt: '正文', data_type: 'LOCATION', checked: true }] }
  h.state.apply(current)
  await h.state.retryModel('seed')
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], [], 'matching committed success must recover without status change')
  assert.equal(h.state.draft.value.sources[0].model_audit.attempt_id, lastAttempt)
  assert.equal(h.workflow.candidates[0].checked, true)
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 2, 'recovering a committed attempt must not repeat model extraction')
})

test('mismatched committed attempt cannot clear newer local HTTP failure', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource() { attempts++; if (attempts === 2) throw new Error('transport failed'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'SUCCESS' } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  await h.state.retryModel('seed')
  current = { ...current, revision: current.revision + 1,
    sources: current.sources.map(s => ({ ...s, model_audit: { status: 'PARTIAL', attempt_id: 'f'.repeat(32) } })) }
  await h.state.refreshMaterials()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'], 'different tagged result must not erase the local failed attempt')
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 3, 'failed source must remain retryable')
})

test('cancel ignores delayed response while explicit refresh recovers matching same-status success', async () => {
  let current, attempts = 0, release, started
  const begun = new Promise(resolve => { started = resolve })
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async readDraft() { return current },
    async extractSource(_draft, _source, _revision, _signal, attemptId) {
      attempts++
      if (attempts === 2) {
        current = { ...current, revision: current.revision + 1,
          sources: current.sources.map(s => ({ ...s, model_audit: { status: 'SUCCESS', attempt_id: attemptId } })) }
        started()
        return new Promise(resolve => { release = resolve })
      }
      return current
    },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'SUCCESS' } }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  const pending = h.state.retryModel('seed'); await begun
  h.state.cancelPreparation()
  release(current); await pending
  assert.equal(h.state.draft.value.revision, 1, 'a late response cannot apply itself')
  await h.state.refreshMaterials()
  assert.equal(h.state.draft.value.revision, 2)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 2, 'reconciliation must not call the model again')
})

test('persisted failed extraction audit remains retryable after page restoration', async () => {
  let current, attempts = 0
  const h = harness({
    async readDraft() { return current },
    async extractSource() {
      attempts++
      current = { ...current, sources: current.sources.map(s => ({ ...s, model_audit: { status: 'SUCCEEDED' } })) }
      return current
    },
  }, 'a'.repeat(32))
  current = { ...h.stored(), uploaded: true, sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual', model_audit: { status: 'FAILED' } }] }
  await h.mount()
  assert.equal(h.workflow.step, 'candidates')
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  h.state.go('import'); await h.state.prepare()
  assert.equal(attempts, 1)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
})

test('cancelled extraction must not mark sources as failed or accept late responses', async () => {
  let current, resolve, started
  const begun = new Promise(done => { started = done })
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    extractSource() { started(); return new Promise(done => { resolve = done }) },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }
  const pending = h.state.prepare(); await begun
  h.state.cancelPreparation()
  resolve({ ...current, revision: 9, sources: [] })
  await pending
  assert.equal(h.state.draft.value.revision, 1)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  assert.equal(h.workflow.step, 'import')
})

test('seven appended sources fill the eight-slot draft; eight fail before creating it', async () => {
  const incoming = count => ({ version: 'privacytrace-policy-collector/1', results: Array.from({ length: count }, (_, index) => ({ state: 'PROVIDED', source: { id: 'ext-' + index, title: '外部 ' + index, source_type: 'SDK_POLICY', text: '原句' } })) })
  let imports = 0
  const h = harness({
    async importExternal(_id, input) {
      imports++
      return { ...h.stored(), revision: 2, sources: [...h.stored().sources, ...input.results.map(result => ({ ...result.source, status: 'manual' }))] }
    },
  })
  await h.state.importCollected(incoming(7))
  assert.equal(imports, 1)
  assert.equal(h.state.draft.value.sources.length, 8)
  let creates = 0, rejected = 0
  const blocked = harness({ async createDraft() { creates++; return blocked.stored() }, async importExternal() { rejected++; return blocked.stored() } })
  await blocked.state.importCollected(incoming(8))
  assert.match(blocked.state.error.value, /最多 8 份来源/)
  assert.equal(creates, 0, 'capacity errors must not create a stray draft')
  assert.equal(rejected, 0)
  assert.equal(blocked.workflow.sources.length, 1)
})

test('source-less audit does not consume another slot or modify existing candidates', async () => {
  const h = harness({ async importExternal() { return { ...h.stored(), revision: 2, external_imports: [{ results: [{ state: 'OFFLINE', source_id: null }] }] } } })
  await h.state.importCollected({ version: 'privacytrace-policy-collector/1', results: [{ state: 'OFFLINE', source: null }] })
  assert.equal(h.state.error.value, '')
  assert.equal(h.state.draft.value.sources.length, 1)
  assert.equal(h.state.draft.value.external_imports.length, 1)
})

test('retrying source fetch clears the stale extraction-failure marker on success', async () => {
  let current, attempts = 0
  const h = harness({
    async createDraft() { return current },
    async uploadApk() { current = { ...current, uploaded: true }; return current },
    async fetchSource() { return current },
    async extractSource() { attempts++; if (attempts === 1) throw new Error('第一次提取失败'); return current },
  })
  current = { ...h.stored(), sources: [{ ...h.stored().sources[0], text: '正文', status: 'manual' }] }
  h.state.file.value = { name: 'fixture.apk' }; await h.state.prepare()
  assert.deepEqual([...h.state.failedSourceIds.value], ['seed'])
  await h.state.retrySource('seed')
  assert.equal(attempts, 2)
  assert.deepEqual([...h.state.failedSourceIds.value], [])
  assert.equal(h.state.error.value, '')
  assert.equal(h.state.draft.value.sources[0].text, '正文')
  assert.match(h.state.notice.value, /重新获取和候选提取已完成/)
})
