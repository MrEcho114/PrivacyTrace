// #274: the candidate page must print "已保存" only for a write the service
// accepted, and the 已检查 flag must follow that same accepted snapshot.
// A failure keeps the reader's edits and shows the not-persisted wording.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const { test } = require('node:test')
const { parse, compileScript } = require('@vue/compiler-sfc')
const ts = require('typescript')
const vue = require('vue')

function compile(content) {
  return ts.transpileModule(content, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } }).outputText
}

const file = path.join(__dirname, '../src/pages/CandidatePage.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const script = compile(compileScript(descriptor, { id: 'candidate-save-test' }).content)

const copyExports = {}
vm.runInNewContext(compile(fs.readFileSync(path.join(__dirname, '../src/copy.ts'), 'utf8')), { exports: copyExports })

const sourceTypes = { OFFICIAL_WEB_POLICY: '官网', SDK_POLICY: 'SDK', STORE_POLICY: '商店', IN_APP_POLICY: '应用内' }
const dataTypes = { LOCATION: '位置' }
const quoteExists = (candidate, sources) => {
  const source = sources.find(item => item.id === candidate.sourceId)
  return !!source && !!source.text && !!candidate.quote && source.text.includes(candidate.quote)
}

function harness(persist) {
  const workflow = {
    step: 'candidates',
    example: false,
    sourceId: 'seed',
    sources: [{ id: 'seed', title: '隐私政策', type: 'OFFICIAL_WEB_POLICY', url: '', text: '我们会在您同意后读取设备位置信息，用于附近门店推荐。', status: 'ready', version: 'v1', region: '', product: '', complete: false }],
    candidates: [{
      id: 'c1', sourceId: 'seed', quote: '我们会在您同意后读取设备位置信息', dataType: 'LOCATION', polarity: 'AFFIRMED',
      subject: 'APP', condition: '', checked: false, action: 'ACCESS', purpose: '', recipient: '',
    }],
  }
  const context = {
    exports: {}, Error, AbortController, setTimeout, clearTimeout,
    require(name) {
      if (name === 'vue') return vue
      if (name.endsWith('.vue')) return {}
      if (name === '../copy') return copyExports
      if (name === '../workflow') return { dataTypes, quoteExists, sourceTypes }
      throw new Error(name)
    },
  }
  vm.runInNewContext(script, context, { filename: file })
  return context.exports.default.setup({ state: workflow, persist, typeLabels: dataTypes }, { expose() {}, emit() {} })
}

test('a rejected save keeps the edit and withholds the success wording', async () => {
  const page = harness(async () => false)
  assert.equal(page.notice.value, '', 'the page must start without a save notice')
  page.chosen.value.purpose = '附近门店推荐'
  await page.save()
  assert.equal(page.notice.value, copyExports.copy.saveNotPersisted)
  assert.equal(page.chosen.value.checked, false, 'a rejected write cannot leave the candidate checked')
  assert.equal(page.chosen.value.purpose, '附近门店推荐', 'the edit stays for the retry')
})

test('an accepted save marks the candidate checked and reports success', async () => {
  const page = harness(async () => true)
  page.chosen.value.purpose = '附近门店推荐'
  await page.save()
  assert.equal(page.notice.value, copyExports.copy.saved)
  assert.equal(page.chosen.value.checked, true)
})

test('a throwing persist is treated as a rejected save, not a success', async () => {
  const page = harness(async () => { throw new Error('SERVER_BUSY') })
  await page.save()
  assert.equal(page.notice.value, copyExports.copy.saveNotPersisted)
  assert.equal(page.chosen.value.checked, false)
})

test('the candidate is still marked checked while the write is in flight', async () => {
  let release
  const page = harness(() => new Promise(resolve => { release = resolve }))
  const pending = page.save()
  assert.equal(page.chosen.value.checked, true, 'the pending snapshot carries the check flag')
  assert.equal(page.notice.value, '', 'no success wording before the service answers')
  release(true)
  await pending
  assert.equal(page.notice.value, copyExports.copy.saved)
})
