const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')
function compile(content) { return ts.transpileModule(content, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText }
const helper = { exports: {}, TextEncoder, require(name) {
  if (name.endsWith('?raw')) return { default: fs.readFileSync(path.resolve(__dirname, '../src', name.replace('?raw', '')), 'utf8') }
  if (name === './workflow') return { sourceTypes: { OFFICIAL_WEB_POLICY: '官网', SDK_POLICY: 'SDK', STORE_POLICY: '商店', IN_APP_POLICY: '应用内' } }
  throw new Error(name)
} }
vm.runInNewContext(compile(fs.readFileSync(path.join(__dirname, '../src/policyAssist.ts'), 'utf8')), helper)
const { collectionInstructions, previewExternal, confirmExternal } = helper.exports
const payload = (source = { id: 'ext', title: '外部政策', text: '我们读取位置。' }) => ({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source }] })
test('copied instructions reuse the exact canonical package and only explicit app hints', () => {
  const canonical = fs.readFileSync(path.join(__dirname, '../../../skills/privacytrace-policy-collector/COPY.txt'), 'utf8')
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
  const context = { exports: {}, AbortController, setTimeout, clearTimeout, localStorage: { setItem() {}, getItem() { return storage } },
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
