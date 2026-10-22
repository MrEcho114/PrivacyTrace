import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import vm from 'node:vm'
import { parse, compileScript, compileTemplate } from '@vue/compiler-sfc'
import { renderToString } from '@vue/server-renderer'
import ts from 'typescript'
import * as vue from 'vue'
import { sourceStatusLabel, sourceStatusLabels, type SourceStatus } from '../src/types.ts'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)

test('sourceStatusLabels dictionary maps all statuses and marks url_only distinctly', () => {
  const statuses: SourceStatus[] = ['ready', 'manual', 'empty', 'failed', 'url_only']
  for (const status of statuses) {
    assert.equal(typeof sourceStatusLabels[status], 'string')
    assert.ok(sourceStatusLabels[status].length > 0)
  }
  assert.equal(sourceStatusLabels.url_only, '仅有链接，尚无正文')
  assert.equal(sourceStatusLabels.ready, '已获取网页正文')
  assert.equal(sourceStatusLabels.manual, '手动补入正文')
  assert.equal(sourceStatusLabels.empty, '尚无正文')
  assert.equal(sourceStatusLabels.failed, '来源获取失败')
  assert.notEqual(sourceStatusLabels.url_only, sourceStatusLabels.ready)
  assert.equal(sourceStatusLabel('url_only'), '仅有链接，尚无正文')
  assert.equal(sourceStatusLabel('future_unknown_status'), '未知状态')
  assert.equal(sourceStatusLabel(null), '未知状态')
})

// Genuine component rendering verification:
// Mount and render App.vue with real report fixtures containing web_policy_sources
// across all five statuses, ensuring falsifiability against template regressions.
const file = path.join(__dirname, '../src/App.vue')
const { descriptor } = parse(fs.readFileSync(file, 'utf8'), { filename: file })
const compiled = compileScript(descriptor, { id: 'source-status-test' })
const javascript = ts.transpileModule(compiled.content, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText

const typesCode = ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/types.ts'), 'utf8'), {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText
const typesExports: Record<string, unknown> = {}
vm.runInNewContext(typesCode, { exports: typesExports })

const sdkEvidenceCode = ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/sdkEvidence.ts'), 'utf8'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } },
).outputText
const sdkEvidenceExports: Record<string, unknown> = {}
vm.runInNewContext(sdkEvidenceCode, { exports: sdkEvidenceExports })

// #167: App.vue takes the report title and the unified policy state line from
// the copy module; compile the real module instead of stubbing its text.
const copyCode = ts.transpileModule(
  fs.readFileSync(path.join(__dirname, '../src/copy.ts'), 'utf8'),
  { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS } },
).outputText
const copyExports: Record<string, unknown> = {}
vm.runInNewContext(copyCode, { exports: copyExports })
assert.ok(copyExports.frontendCopy, 'copyExports must export frontendCopy')
assert.equal(typeof copyExports.policyStateLine, 'function', 'copyExports must export policyStateLine')

const templateCode = compileTemplate({
  source: descriptor.template.content,
  filename: file,
  id: 'source-status-test',
  compilerOptions: { bindingMetadata: compiled.bindings },
}).code
const templateContext = {
  exports: {} as { render?: (...args: unknown[]) => unknown },
  require: (name: string) => {
    if (name === 'vue') return vue
    if (name === '../reportUi') return { reportRowNumber: (index: number) => index < 0 ? '--' : String(index + 1).padStart(2, '0') }
    throw new Error(`Unexpected import in template: ${name}`)
  },
}
vm.runInNewContext(ts.transpileModule(templateCode, {
  compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.CommonJS },
}).outputText, templateContext)

function mount(jobs: Array<{ id: string; state: string }> = [], fixture: Record<string, unknown> | null = null) {
  const requests: Array<[string, ...unknown[]]> = []
  const report = (id: string) => fixture ?? ({ demo: false, job: { id }, result: { issues: [] } })
  const api = {
    loadJobs: async () => ({ jobs }),
    loadTaxonomy: async () => ({ data_types: [] }),
    loadReport: async () => { requests.push(['demo']); return { demo: true } },
    loadJob: async (id: string) => { requests.push(['job', id]); return jobs.find(job => job.id === id) },
    loadJobReport: async (id: string) => { requests.push(['report', id]); return report(id) },
    cancelJob: async (id: string) => { requests.push(['cancel', id]); return { id, state: 'CANCELLED' } },
    submitReview: async (id: string) => { requests.push(['review', id]); return report(id) },
  }
  let unmount: (() => void) | undefined
  const context = {
    exports: {} as { default: { setup: (...args: unknown[]) => Record<string, unknown> } },
    AbortController, setTimeout, clearTimeout,
    require: (name: string) => {
      if (name === './api') return api
      if (name === './types') return typesExports
      if (name === './copy') return copyExports
      if (name === './workflow') return { sourceStatusLabels: typesExports.sourceStatusLabels }
      if (name === './sdkEvidence') return sdkEvidenceExports
      if (name === './reportUi') return { reportRowNumber: (index: number) => index < 0 ? '--' : String(index + 1).padStart(2, '0') }
      // Component imports are used by the template/render path, not by setup();
      // the mount helper exercises setup only (issue #144 extraction).
      // BrandMark renders in the top bar, so give it a stub instead of
      // `undefined` to keep the render path warning-free.
      if (name === './components/BrandMark.vue') return { name: 'BrandMark', render: () => null }
      if (name.startsWith('./components/')) return {}
      if (name === 'vue') return { ...vue, onMounted() {}, onBeforeUnmount(fn: () => void) { unmount = fn } }
      throw new Error(`Unexpected import: ${name}`)
    },
  }
  vm.runInNewContext(javascript, context, { filename: file })
  const state = context.exports.default.setup({}, { expose() {} })
  return { state, requests, unmount: () => unmount?.() }
}

async function renderHtml(state: Record<string, unknown>) {
  const setup = vue.proxyRefs(state)
  return renderToString(vue.createSSRApp({
    render() {
      return templateContext.exports.render!(setup, [], {}, setup, {}, {})
    },
  }))
}

test('App.vue genuinely renders url_only as "仅有链接，尚无正文" and does not claim body acquired', async () => {
  const fixture = {
    demo: false,
    job: { id: 'status-test-job', input_mode: 'APK', ruleset_version: '0.3.0', state: 'SUCCEEDED' },
    sample: {
      name: 'Status Test App', package_name: 'com.example.statustest',
      apk_sha256: 'a'.repeat(64), version_code: 1, permissions: [], dex_entries: [],
    },
    coverage: { status: 'COMPLETE', scanned_dex: [], failed_dex: [], limitations: [], behavior_limitations: [] },
    tools: {
      web_policy_sources: JSON.stringify([
        { title: '官网隐私政策链接', status: 'url_only', url: 'https://example.com/privacy', provenance: 'MANIFEST_METADATA' },
        { title: '第三方SDK说明正文', status: 'ready', url: 'https://example.com/sdk-privacy', provenance: 'DIRECT_WEB_FETCH' },
        { title: '外部收集正文', status: 'ready', url: 'https://example.com/collected', provenance: 'EXTERNAL_CHAT_EXPORT' },
        { title: '合规人员手工录入', status: 'manual', provenance: 'MANUAL_INPUT' },
        { title: '空正文候选条目', status: 'empty' },
        { title: '远端抓取超时条目', status: 'failed', error_code: 'FETCH_TIMEOUT' },
        { title: '未知状态条目', status: 'future_unknown_status' },
      ]),
    },
    reviews: [],
    result: { issues: [] },
    evidence: [],
    behaviors: [],
    policy_documents: [],
    policy_claims: [],
  }

  const { state, unmount } = mount([{ id: 'status-test-job', state: 'SUCCEEDED' }], fixture)
  try {
    await (state.reload as (silent?: boolean) => Promise<void>)(true)
    const html = await renderHtml(state)

    // Positive assertion: url_only displays canonical Chinese label and origin
    assert.match(html, /官网隐私政策链接<\/strong> · 仅有链接，尚无正文 · Manifest 发现/)

    // Negative assertion: url_only MUST NOT fall through to '已获取正文' or '已获取网页正文'
    assert.doesNotMatch(html, /官网隐私政策链接<\/strong> · 已获取正文/)
    assert.doesNotMatch(html, /官网隐私政策链接<\/strong> · 已获取网页正文/)

    // Verify all other status labels are also genuinely rendered by App.vue
    assert.match(html, /第三方SDK说明正文<\/strong> · 已获取网页正文 · 后端抓取/)
    assert.match(html, /外部收集正文<\/strong> · 已获取网页正文 · 外部导入/)
    assert.match(html, /合规人员手工录入<\/strong> · 手动补入正文 · 手动输入/)
    assert.match(html, /空正文候选条目<\/strong> · 尚无正文/)
    assert.match(html, /远端抓取超时条目<\/strong> · 来源获取失败/)
    assert.match(html, /未知状态条目<\/strong> · 未知状态/)
    assert.match(html, /FETCH_TIMEOUT/)
  } finally {
    unmount()
  }
})
