// #274: the save's boolean is the success contract the candidate page reads.
// A busy gate, a missing draft and a bridge error must all resolve false, so the
// page never prints "已保存" for a write the service did not accept.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const ts = require('typescript')
const vue = require('vue')

function loadCreateMobileFlow() {
  const file = path.resolve(__dirname, '../src/mobile/flow.ts')
  const code = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
  }).outputText
  const module = { exports: {} }
  const context = {
    module,
    exports: module.exports,
    crypto: require('node:crypto').webcrypto,
    setTimeout,
    clearTimeout,
    require(name) {
      if (name === 'vue') return vue
      if (name === '../workflow') return { freshWorkflow: () => ({ step: 'import', maxStep: 0, sources: [], candidates: [], sourceId: '' }) }
      throw new Error(name)
    },
  }
  vm.runInNewContext(code, context, { filename: file })
  return module.exports.createMobileFlow
}

const createMobileFlow = loadCreateMobileFlow()
const DRAFT_ID = 'a'.repeat(32)

function client({ failCandidates } = {}) {
  const draft = { id: DRAFT_ID, revision: 1, name: '受控材料', uploaded: true, apk_sha256: null, sources: [], candidates: [], jobs: [] }
  const actions = []
  let block = null
  const bridge = {
    async upload() { return { origin: 'https://bridge.example/', draft: DRAFT_ID, state: 'SERVER_CONFIRMED' } },
    async restore() { return { origin: 'https://bridge.example/', draft: DRAFT_ID, state: 'SERVER_CONFIRMED' } },
    async cancel() {},
    async remove() { return { state: 'DELETED' } },
    async modelStatus() { return { configured: false, endpoint: null } },
    async configureModel() { return { configured: false, endpoint: null } },
    async collect() { return '' },
    async request(name) {
      actions.push(name)
      if (block && name === 'read') await block
      const base = { origin: 'https://bridge.example/', draft: DRAFT_ID }
      if (name === 'taxonomy') return { ...base, data: { data_types: [] } }
      if (name === 'candidates') {
        if (failCandidates) throw failCandidates
        return { ...base, data: { ...draft, revision: draft.revision + 1 } }
      }
      return { ...base, data: { ...draft } }
    },
  }
  return {
    flow: createMobileFlow(bridge),
    actions,
    count: name => actions.filter(item => item === name).length,
    holdRead() {
      let open
      block = new Promise(resolve => { open = resolve })
      return () => { block = null; open() }
    },
  }
}

test('a save without a draft resolves false and sends nothing', async () => {
  const { flow, actions } = client()
  assert.equal(await flow.save(), false)
  assert.deepEqual(actions, [], 'no request is issued before a material exists')
})

test('a candidates write rejected by the bridge resolves false and keeps the error', async () => {
  const { flow } = client({ failCandidates: 'SERVER_BUSY' })
  await flow.select()
  assert.equal(await flow.save(), false)
  assert.equal(flow.error.value, 'SERVER_BUSY')
})

test('an accepted candidates write resolves true', async () => {
  const { flow } = client()
  await flow.select()
  assert.equal(await flow.save(), true)
  assert.equal(flow.error.value, '')
})

test('a save issued while the flow is busy resolves false without a second write', async () => {
  const { flow, count, holdRead } = client()
  await flow.select()
  const releaseRead = holdRead()
  const pending = flow.refresh()
  assert.equal(await flow.save(), false, 'the busy gate is not a saved write')
  assert.equal(count('candidates'), 0, 'a gated save issues no candidates request')
  releaseRead()
  await pending
})
