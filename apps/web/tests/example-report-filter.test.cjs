// Exercise the compiled ExampleReport setup so filter changes and the selected
// evidence row cannot disagree in either the standalone or inline presentation.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

const file = path.join(__dirname, '../src/pages/ExampleReport.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'example-report-filter-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

// #167: the report reads its heading, table labels and unified source state
// from the real copy module; the old mock only knew the deleted legacy keys.
const copyCode = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/copy.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const copyExports = {}
vm.runInNewContext(copyCode, { exports: copyExports })

const exampleRows = [
  { id: 'host-row', type: '位置信息', source: 'host', signal: '', status: '', tone: 'success', explanation: '', locator: '', code: '', quote: '' },
  { id: 'sdk-row', type: '设备标识', source: 'sdk', signal: '', status: '', tone: 'wait', explanation: '', locator: '', code: '', quote: '' },
]
const exampleSources = [
  { id: 'host', title: '官网', version: '1', text: '' },
  { id: 'sdk', title: 'SDK', version: '1', text: '' },
]

function mount() {
  const state = vue.reactive({ filter: 'all', evidenceId: '' })
  const context = {
    exports: {},
    require: name => {
      if (name === '../components/UiButton.vue' || name === '../components/StatusTag.vue') return { default: {} }
      if (name === '../copy') return copyExports
      if (name === '../workflow') return { exampleRows, exampleSources }
      if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount() {} }
      throw new Error(`Unexpected import: ${name}`)
    },
  }
  vm.runInNewContext(javascript, context, { filename: file })
  const exposed = context.exports.default.setup({ state }, { expose() {} })
  return { state, exposed }
}

for (const mode of ['desktop', 'narrow']) {
  test(`filtering out the selected evidence clears it in the ${mode} presentation`, async () => {
    const { state, exposed } = mount()
    exposed.inlineEvidence.value = mode === 'narrow'
    state.evidenceId = 'sdk-row'
    exposed.fullText.value = true
    state.filter = 'host'
    await vue.nextTick()
    assert.equal(state.evidenceId, '')
    assert.equal(exposed.fullText.value, false)
    assert.equal(exposed.selected.value, undefined)
  })
}

test('keeping the selected evidence visible keeps its expanded state', async () => {
  const { state, exposed } = mount()
  state.evidenceId = 'host-row'
  state.filter = 'host'
  await vue.nextTick()
  assert.equal(state.evidenceId, 'host-row')
  assert.equal(exposed.selected.value.id, 'host-row')
})
