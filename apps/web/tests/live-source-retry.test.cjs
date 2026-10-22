// Run the compiled component action: a failed refresh must not trigger extraction.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { randomUUID } = require('node:crypto')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

const file = path.join(__dirname, '../src/LiveWorkflow.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'live-source-retry-test' })
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

for (const status of ['manual', 'ready']) {
  for (const failedRefresh of [true, false]) {
    test(`${status} source refresh ${failedRefresh ? 'failure preserves candidates' : 'success extracts new text'}`, async () => {
      const draft = { id: 'fixture', revision: 2, jobs: [],
        sources: [{ id: 'policy', title: 'Policy', status, text: 'Retained policy text.',
          error_code: failedRefresh ? 'FETCH_TIMEOUT' : null }],
        candidates: [{ id: 'retained', source_id: 'policy', excerpt: 'Retained policy text.' }],
      }
      const calls = []
      const context = { exports: {}, AbortController, setTimeout, clearTimeout, crypto: { randomUUID },
        localStorage: { setItem() {} },
        require(name) {
          if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount() {} }
          if (name === './liveApi') return {
            async fetchSource() { calls.push('fetch'); return draft },
            async reserveExtraction(_draft, _source, revision, id) {
              return { attempt_id: id, state: 'RESERVED', revision }
            },
            async extractSource() {
              calls.push('extract')
              return { ...draft, candidates: [{ ...draft.candidates[0], id: 'replacement' }] }
            },
          }
          if (name === './workflow') return { steps: ['import', 'candidates', 'progress', 'report'] }
          if (name === './copy') return copyExports
          if (name === './api' || name.endsWith('.vue')) return {}
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
