// Run the compiled component action: an unchecked candidate must not block start.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

const file = path.join(__dirname, '../src/LiveWorkflow.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'live-start-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

// #167: go() indexes the shared workflow step keys, and the component renders
// frontendCopy/policyStateLine from the real copy module.
const copyCode = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/copy.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const copyExports = {}
vm.runInNewContext(copyCode, { exports: copyExports })

test('start accepts an unchecked candidate and sends checked=false', async () => {
  const draft = {
    id: 'fixture', revision: 2, jobs: [], uploaded: true,
    sources: [{ id: 'policy', title: 'Policy', status: 'manual', text: 'Policy text.',
      error_code: null, source_type: 'OFFICIAL_WEB_POLICY', version: 'UNKNOWN',
      region: '', product: '', package_name: '', version_code: null,
      captured_at: null, sha256: null, final_url: null, provenance: 'MANUAL_INPUT',
      model_audit: {} }],
    candidates: [{ id: 'c1', source_id: 'policy', excerpt: 'Policy text.',
      data_type: 'CONTACTS', polarity: 'UNKNOWN', subject: 'UNKNOWN', action: 'UNKNOWN',
      condition: null, declared_purpose: null, declared_recipient: null,
      ambiguity_flags: [], start_offset: 0, checked: false }],
  }
  const calls = []
  const context = {
    exports: {}, AbortController, setTimeout, clearTimeout,
    crypto: { randomUUID: () => 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa' },
    localStorage: { setItem() {}, removeItem() {} },
    require(name) {
      if (name === 'vue') {
        return { ...vue, onMounted() {}, onBeforeUnmount() {}, nextTick() {} }
      }
      if (name === './liveApi') return {
        async createDraft() { return draft },
        async uploadApk() { return draft },
        async fetchSource() { return draft },
        async extractSource() { return draft },
        displaySourceUrl: value => value,
        async saveCandidates(id, payload) {
          calls.push(['save', payload.candidates.map(item => item.checked)])
          return { ...draft, revision: 3, candidates: payload.candidates }
        },
        async startScan(id, payload) {
          calls.push(['start', payload])
          return { id: 'job-1', state: 'SUCCEEDED' }
        },
        async readDraft() { return { ...draft, revision: 3 } },
      }
      if (name === './api') return {
        async loadJob() { return { id: 'job-1', state: 'SUCCEEDED' } },
        async loadTaxonomy() { return { data_types: [] } },
        async cancelJob() { return {} },
      }
      if (name === './workflow') {
        return { quoteExists: () => true, sourceStatusLabel: () => '手动补入正文', steps: ['import', 'candidates', 'progress', 'report'] }
      }
      if (name === './copy') return copyExports
      if (name === './reportUi') return { reportRowNumber: (index) => index < 0 ? '--' : String(index + 1).padStart(2, '0') }
      if (name.endsWith('.vue')) return {}
      throw new Error(`Unexpected import: ${name}`)
    },
  }
  vm.runInNewContext(javascript, context, { filename: file })
  const workflow = {
    example: false, step: 'candidates', maxStep: 1, sourceId: 'policy',
    sources: [{ id: 'policy', title: 'Policy', url: '', type: 'OFFICIAL_WEB_POLICY',
      text: 'Policy text.', status: 'manual', version: 'UNKNOWN', region: '', product: '',
      complete: false }],
    candidates: [{ id: 'c1', sourceId: 'policy', quote: 'Policy text.',
      dataType: 'CONTACTS', polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: '',
      checked: false, action: 'UNKNOWN', purpose: '', recipient: '', startOffset: 0 }],
    stage: 0, outcome: 'idle', filter: '', evidenceId: '',
  }
  const state = context.exports.default.setup({ state: workflow }, { expose() {}, emit() {} })
  state.draft.value = draft
  await state.begin()
  assert.equal(state.error.value, '')
  assert.deepEqual(calls.map(item => item[0]), ['save', 'start'])
  assert.deepEqual(calls[0][1], [false])
})
