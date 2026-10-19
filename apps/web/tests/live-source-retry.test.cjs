// Run the compiled component action: a failed refresh must not trigger extraction.
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
const compiled = compileScript(descriptor, { id: 'live-source-retry-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

for (const status of ['manual', 'ready']) {
  for (const failedRefresh of [true, false]) {
    test(`${status} source refresh ${failedRefresh ? 'failure preserves candidates' : 'success extracts new text'}`, async () => {
      const draft = { id: 'fixture', revision: 2, jobs: [],
        sources: [{ id: 'policy', title: 'Policy', status, text: 'Retained policy text.',
          error_code: failedRefresh ? 'FETCH_TIMEOUT' : null }],
        candidates: [{ id: 'retained', source_id: 'policy', excerpt: 'Retained policy text.' }],
      }
      const calls = []
      const context = { exports: {}, AbortController, setTimeout, clearTimeout,
        localStorage: { setItem() {} },
        require(name) {
          if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount() {} }
          if (name === './liveApi') return {
            async fetchSource() { calls.push('fetch'); return draft },
            async extractSource() {
              calls.push('extract')
              return { ...draft, candidates: [{ ...draft.candidates[0], id: 'replacement' }] }
            },
          }
          if (name === './api' || name === './workflow' || name.endsWith('.vue')) return {}
          throw new Error(`Unexpected import: ${name}`)
        },
      }
      vm.runInNewContext(javascript, context, { filename: file })
      const workflow = { sources: [], candidates: [] }
      const state = context.exports.default.setup({ state: workflow }, { expose() {}, emit() {} })
      state.draft.value = draft
      await state.retrySource('policy')
      assert.equal(state.error.value, '')
      assert.deepEqual(calls, failedRefresh ? ['fetch'] : ['fetch', 'extract'])
      assert.equal(workflow.candidates[0].id, failedRefresh ? 'retained' : 'replacement')
      assert.equal(workflow.sources[0].errorCode, failedRefresh ? 'FETCH_TIMEOUT' : null)
    })
  }
}
