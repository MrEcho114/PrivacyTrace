#!/usr/bin/env node
/**
 * Issue #144 mobile regression harness (round 2 shell).
 *
 * Keeps the round-1 invariants that the new Android shell must not regress:
 * long unbroken text at 320/390/768, 200% root font, fine-pointer hover,
 * coarse-pointer fields, soft-keyboard reservation, evidence focus/scroll
 * restore, one analysis start despite a lost response, and no browser API.
 * The full round-2 shell/touch/back matrix lives in verify-frontend-round2.cjs.
 * verifyIssueFixes() adds the #239/#243/#248/#249 mobile regressions, each on
 * its own production-Vue page with its own controlled native bridge.
 *
 * Everything runs against production Vue with a mocked native bridge; no APK,
 * model, Docker or Android device/IME execution.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const net = require('node:net')
const { spawn } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')
const { assertMobileDesign } = require('./lib/frontend-guards.cjs')
const root = path.resolve(__dirname, '..'), output = path.join(root, 'tmp/issue72-native')
fs.mkdirSync(output, { recursive: true })
const source = fs.readFileSync(path.join(__dirname, 'verify-frontend-flow.cjs'), 'utf8')
const fixtureContext = {}
vm.runInNewContext(source.slice(source.indexOf('const policySentence'), source.indexOf('const fixtureRoutes')) + '\nthis.fixtures = { reportFixture, taxonomyFixture, policySentence }', fixtureContext)
const fixtures = JSON.parse(JSON.stringify(fixtureContext.fixtures))
const longTitle = 'A'.repeat(120)
const longUrl = 'https://policy.example/' + 'a'.repeat(400)
const longPolicy = ('长政策正文保留原句、条件与不确定性，不因窄屏而截断。'.repeat(120)) + '\n' + longUrl

const pageOverflow = page => page.evaluate(() => {
  const width = innerWidth
  const inScrollContainer = element => {
    for (let parent = element.parentElement; parent; parent = parent.parentElement) {
      const overflowX = getComputedStyle(parent).overflowX
      if (overflowX === 'auto' || overflowX === 'scroll') return true
    }
    return false
  }
  const offenders = []
  for (const element of document.querySelectorAll('body *')) {
    if (!element.getClientRects().length) continue
    if (element.closest('.sr-only, dialog')) continue
    const style = getComputedStyle(element)
    if (style.position === 'fixed' || style.display === 'none' || style.visibility === 'hidden') continue
    if (inScrollContainer(element)) continue
    const rect = element.getBoundingClientRect()
    if (rect.right > width + 1 || rect.left < -1) {
      const id = element.id ? '#' + element.id : ''
      const cls = element.className && typeof element.className === 'string' ? '.' + element.className.trim().split(/\s+/)[0] : ''
      offenders.push(element.tagName.toLowerCase() + id + cls + ':' + Math.round(rect.left) + '..' + Math.round(rect.right))
    }
  }
  return { scrollWidth: document.documentElement.scrollWidth, bodyScrollWidth: document.body.scrollWidth, innerWidth: width, offenders: offenders.slice(0, 8) }
})
async function assertNoPageOverflow(page, label) {
  const measured = await pageOverflow(page)
  const viewport = page.viewportSize()
  const layout = await page.evaluate(() => ({ innerWidth, scale: window.visualViewport?.scale ?? 1 }))
  assert.equal(layout.innerWidth, viewport.width, `${label}: layout viewport ${layout.innerWidth} != ${viewport.width} (mobile shrink-to-fit)`)
  assert.equal(layout.scale, 1, `${label}: page zoomed out to fit overflowing content`)
  assert.ok(measured.scrollWidth <= measured.innerWidth, `${label}: document scrollWidth ${measured.scrollWidth} exceeds ${measured.innerWidth}`)
  assert.ok(measured.bodyScrollWidth <= measured.innerWidth, `${label}: body scrollWidth ${measured.bodyScrollWidth} exceeds ${measured.innerWidth}`)
  assert.deepEqual(measured.offenders, [], `${label}: elements protrude past the viewport`)
}
async function assertTouchTargets(page, label) {
  const measured = await page.evaluate(() => {
    const short = []
    let total = 0
    for (const element of document.querySelectorAll('.mobile-workspace button, .mobile-workspace [role="tab"], .mobile-workspace summary, .mobile-workspace .ui-button, dialog.ui-sheet button')) {
      if (!element.getClientRects().length || getComputedStyle(element).display === 'inline') continue
      const rect = element.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      total += 1
      if (rect.width < 47.5 || rect.height < 47.5) short.push((element.getAttribute('aria-label') || element.textContent || element.tagName).trim().slice(0, 24) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height))
    }
    return { total, short }
  })
  assert.ok(measured.total >= 8, `${label}: expected a representative set of touch targets, got ${measured.total}`)
  assert.deepEqual(measured.short, [], `${label}: touch targets under 48x48 CSS px`)
  return `${label}: ${measured.total} controls >= 48x48`
}
async function assertNoDocumentZoom(page, label) {
  const layout = await page.evaluate(() => ({ innerWidth, scale: window.visualViewport?.scale ?? 1 }))
  assert.equal(layout.scale, 1, `${label}: page must not be zoomed out`)
}
async function shot(page, name) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(100)
  await page.screenshot({ path: path.join(output, name), fullPage: true })
}
async function waitTitle(page, title, timeout = 10000) {
  await page.waitForFunction(expected => document.getElementById('page-title')?.textContent?.trim() === expected, title, { timeout })
}
async function checkMobileDesign(page) {
  await page.mouse.move(0, 0)
  await assertMobileDesign(page)
}

function bridge(options) {
  globalThis.isTauri = true
  const context = { origin: 'https://analysis.example/', draft: 'a'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
  const job = { ...options.reportFixture.job, id: 'b'.repeat(32), state: 'QUEUED', error: null }
  const draft = {
    id: context.draft, name: 'com.example.' + 'b'.repeat(160), uploaded: true, revision: 1, apk_sha256: 'c'.repeat(128),
    sources: [
      { id: 'policy', title: options.policyTitle, url: options.policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: options.policySentence, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
      { id: 'long', title: '示例隐私政策', url: options.policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: options.policyText, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
    ],
    candidates: [], jobs: [],
  }
  const ledger = globalThis.mobileCalls = []
  let configured = false, jobReads = 0
  const events = []
  function advanceJob() {
    jobReads += 1
    job.state = jobReads === 1 ? 'STATIC_ANALYSIS' : 'SUCCEEDED'
    events.push({ state: job.state, at: new Date(Date.UTC(2026, 9, 21, 12, jobReads)).toISOString() })
    if (draft.jobs[0]) draft.jobs[0].events = [...events]
    return job
  }
  globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
    const method = command.split('|')[1]
    ledger.push({ method, args })
    if (method === 'model_status') return { configured, endpoint: configured ? 'https://model.example/v1/chat/completions' : null }
    if (method === 'configure_model') { configured = true; return { configured, endpoint: 'https://model.example/v1/chat/completions' } }
    if (method === 'upload_selected' || method === 'refresh_upload') return context
    if (method === 'delete_upload') return { ...context, state: 'DELETED' }
    if (method === 'cancel') return
    if (method === 'collect_policy') return { text: JSON.stringify({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: { id: 'policy-collected', title: '受控政策', source_type: 'OFFICIAL_WEB_POLICY', text: options.policySentence } }] }) }
    if (method !== 'workflow') throw new Error('Unexpected native method ' + method)
    const action = args.action, input = JSON.parse(args.payload)
    let data = draft
    if (action === 'taxonomy') data = options.taxonomyFixture
    else if (action === 'read' || action === 'discover' || action === 'fetch') data = draft
    else if (action === 'import') { draft.sources.push(...input.results.map(item => ({ ...item.source, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' }))); draft.revision++ }
    else if (action === 'extract') {
      draft.candidates = [{ id: 'candidate-1', source_id: 'policy', excerpt: options.policySentence, data_type: 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }]
      draft.revision++
    }
    else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision++ }
    else if (action === 'start') {
      draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: '2026-10-21T12:00:00Z' }] })
      events.push({ state: 'QUEUED', at: '2026-10-21T12:00:00Z' })
      draft.revision++
      // The native call accepted the start but its response was lost.
      throw new Error('Simulated response loss after accepted start')
    }
    else if (action === 'job') data = { ...advanceJob() }
    else if (action === 'report') data = { ...options.reportFixture, job: { ...job }, demo: false, result: { ...options.reportFixture.result, job_id: job.id } }
    else throw new Error('Unexpected workflow action ' + action)
    return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
  } }
}

/**
 * #239/#243/#248/#249 regressions on the production mobile shell.
 *
 * Each scenario owns its own controlled bridge and page, so a failure names one
 * issue. This is the interface-contract regression ADR-0004 names: production Vue
 * plus a native bridge stand-in, not a device, real model or APK run. The bridge
 * keeps the draft and answers AnalysisTransport.workflow's envelope instead of
 * exposing a hidden flow API.
 */
function issueBridge(options) {
  globalThis.isTauri = true
  const context = { origin: 'https://analysis.example/', draft: 'i'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
  const ledger = globalThis.mobileCalls = []
  const queues = JSON.parse(JSON.stringify({ fetch: options.fetch ?? {}, extract: options.extract ?? {}, collect: options.collect ?? [] }))
  let configured = false, jobReads = 0
  const job = { id: 'j'.repeat(32), state: 'QUEUED', error: null }
  const draft = {
    id: context.draft, name: 'com.example.issue-fixes', uploaded: true, revision: 1, apk_sha256: 'd'.repeat(64),
    sources: (options.sources ?? []).map(item => ({ source_type: 'OFFICIAL_WEB_POLICY', version: 'UNKNOWN', region: '', product: '', ...item })),
    candidates: options.candidates ?? [],
    jobs: options.progress ? [{ job_id: job.id, request_id: 'r'.repeat(32), revision: 1, events: [{ state: 'QUEUED', at: '2026-10-23T00:00:00Z' }] }] : [],
  }
  const take = (kind, id) => { const list = queues[kind][id]; return Array.isArray(list) && list.length ? list.shift() : undefined }
  globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
    const method = command.split('|')[1]
    ledger.push({ method, action: args.action, args })
    if (method === 'model_status') return { configured, endpoint: configured ? 'https://model.example/v1/chat/completions' : null }
    if (method === 'configure_model') { configured = true; return { configured, endpoint: 'https://model.example/v1/chat/completions' } }
    if (method === 'upload_selected') {
      // #243 acceptance: a freshly chosen instance must start clean instead of
      // inheriting the previous material's model answer.
      if (options.newMaterial) {
        context.draft = 'n'.repeat(32); draft.id = context.draft
        draft.sources = []; draft.candidates = []; draft.jobs = []; draft.revision = 1
      }
      return context
    }
    if (method === 'refresh_upload') return context
    if (method === 'delete_upload') return { ...context, state: 'DELETED' }
    if (method === 'cancel') return
    if (method === 'collect_policy') return { text: queues.collect.length ? queues.collect.shift() : '' }
    if (method !== 'workflow') throw new Error('Unexpected native method ' + method)
    const action = args.action, input = JSON.parse(args.payload)
    let data = draft
    if (action === 'taxonomy') data = { data_types: [] }
    else if (action === 'read' || action === 'discover') data = draft
    else if (action === 'fetch') {
      const source = draft.sources.find(item => item.id === input.source)
      if (!source) throw new Error('Missing source ' + input.source)
      Object.assign(source, take('fetch', input.source) ?? { status: 'failed', error_code: 'FETCH_FAILED', text: '' })
      draft.revision += 1
    }
    else if (action === 'extract') {
      const source = draft.sources.find(item => item.id === input.source)
      if (!source) throw new Error('Missing source ' + input.source)
      const outcome = take('extract', input.source) ?? { audit: { status: 'SUCCESS' } }
      source.model_audit = outcome.audit ?? { status: 'SUCCESS' }
      draft.candidates.push(...(outcome.candidates ?? []))
      draft.revision += 1
    }
    else if (action === 'import') { draft.sources.push(...input.results.map(item => ({ ...item.source, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' }))); draft.revision += 1 }
    else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision += 1 }
    else if (action === 'start') { draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: '2026-10-23T00:00:00Z' }] }); draft.revision += 1 }
    else if (action === 'job') { jobReads += 1; if (options.advanceAfter && jobReads > options.advanceAfter) job.state = 'STATIC_ANALYSIS'; data = { ...job } }
    else throw new Error('Unexpected workflow action ' + action)
    return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
  } }
}

async function verifyIssueFixes(browser, origin) {
  const sentence = fixtures.policySentence
  const collector = (title, text) => JSON.stringify({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: { id: 'policy-collected', title, source_type: 'OFFICIAL_WEB_POLICY', text } }] })
  const count = (page, action) => page.evaluate(name => globalThis.mobileCalls.filter(call => call.action === name).length, action)
  const payloadOf = (page, action) => page.evaluate(name => {
    const call = globalThis.mobileCalls.find(item => item.action === name)
    return call ? JSON.parse(call.args.payload) : null
  }, action)
  const settleCollect = (page, expected) => page.waitForFunction(value => document.querySelector('#collector-result')?.value === value, expected, { timeout: 10000 })
  const first = collector('第一次受控政策', sentence)
  const second = collector('第二次受控政策', sentence + '\n（补充一行用于区分两次收集。）')
  const scenarios = [
    {
      issue: '#239', title: 'a successful reload on the progress step resumes the poll',
      options: { sources: [{ id: 'policy', title: '有效正文来源', url: 'https://policy.example/a', text: sentence, status: 'manual' }], progress: true, advanceAfter: 1 },
      async run(page) {
        await page.getByRole('button', { name: '恢复当前材料', exact: true }).click()
        await waitTitle(page, '扫描与对照进度', 12000)
        assert.equal((await page.locator('.m-eyebrow').innerText()).trim(), '等待处理', 'restore reads the queued job once')
        const reads = await count(page, 'job')
        await page.getByRole('button', { name: '服务与存储设置' }).click()
        const sheet = page.locator('dialog.ui-sheet.m-settings-dialog')
        await sheet.waitFor({ timeout: 5000 })
        await sheet.getByRole('button', { name: '重新读取材料', exact: true }).click()
        await page.waitForFunction(() => document.querySelector('.m-eyebrow')?.textContent?.trim() === '隔离扫描 APK', null, { timeout: 20000 })
        assert.equal(await count(page, 'job'), reads + 1, 'only the resumed automatic poll reads the job, with no extra click')
      },
    },
    {
      issue: '#243', title: 'a remount and a repeated identical collect both refill the assistant box',
      options: { sources: [{ id: 'policy', title: '有效正文来源', url: 'https://policy.example/a', text: sentence, status: 'manual' }], collect: [first, first, second], newMaterial: true },
      async run(page) {
        const openModel = async () => page.getByText('使用手机上的个人模型', { exact: true }).click()
        const openAssist = async () => page.getByText('找不到政策？使用网页辅助收集', { exact: true }).click()
        await page.getByRole('button', { name: '恢复当前材料', exact: true }).click()
        await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
        await openModel()
        await page.getByRole('button', { name: '配置模型', exact: true }).click()
        await page.getByLabel('模型名称', { exact: true }).fill('compatible-chat')
        await page.getByLabel('应用名称或包名', { exact: true }).fill('com.example.mobile.ok')
        await page.getByRole('button', { name: '使用个人模型收集一次', exact: true }).click()
        await openAssist()
        await settleCollect(page, first)
        await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
        await waitTitle(page, '核对政策声明', 12000)
        await page.getByRole('button', { name: '返回上一步' }).click()
        await waitTitle(page, 'APK 与政策材料', 12000)
        await openAssist()
        assert.equal(await page.evaluate(() => document.querySelector('#collector-result')?.value), first, 'returning to the material step must refill the retained result')
        await openModel()
        await page.evaluate(() => { const box = document.querySelector('#collector-result'); box.value = ''; box.dispatchEvent(new Event('input', { bubbles: true })) })
        assert.equal(await page.evaluate(() => document.querySelector('#collector-result')?.value), '')
        await page.getByRole('button', { name: '使用个人模型收集一次', exact: true }).click()
        await settleCollect(page, first)
        await page.getByRole('button', { name: '使用个人模型收集一次', exact: true }).click()
        await settleCollect(page, second)
        await page.getByRole('button', { name: '检查回填内容', exact: true }).click()
        await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
        await page.waitForFunction(() => document.body.innerText.includes('来源和未检查候选已补入'), null, { timeout: 10000 })
        assert.equal(await count(page, 'import'), 1, 'the refilled box still imports through the production confirmation path')
        // #243 acceptance 3: deleting the old material and choosing a new instance
        // must not carry the retained answer into the new draft.
        await page.getByRole('button', { name: '删除已上传材料', exact: true }).click()
        await page.getByRole('button', { name: '选择应用并上传', exact: true }).waitFor({ timeout: 10000 })
        await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
        await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 10000 })
        await page.waitForTimeout(200)
        assert.equal(await page.evaluate(() => document.querySelector('#collector-result')?.value ?? '<missing>'), '', 'a new material instance must start with an empty assistant box')
        assert.equal(await count(page, 'import'), 1, 'the previous model answer must never be imported into the new material automatically')
        assert.equal(await page.evaluate(() => document.querySelectorAll('.m-source-row').length), 0, 'the new instance starts without the previous material sources')
      },
    },
    {
      issue: '#248', title: 'both candidate retry buttons call the bridge for the selected source',
      options: {
        sources: [
          { id: 'a', title: '有效正文来源', url: 'https://policy.example/a', text: sentence, status: 'manual', model_audit: { status: 'FAILED' } },
          { id: 'b', title: '抓取失败来源', url: 'https://policy.example/b', text: '', status: 'failed' },
        ],
        candidates: [{ id: 'c1', source_id: 'a', excerpt: sentence, data_type: 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }],
        fetch: { b: [{ status: 'failed', error_code: 'FETCH_FAILED', text: '' }] },
        extract: { a: [{ audit: { status: 'SUCCESS' } }] },
      },
      async run(page) {
        await page.getByRole('button', { name: '恢复当前材料', exact: true }).click()
        await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
        await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
        await waitTitle(page, '核对政策声明', 12000)
        await page.getByRole('tab', { name: '政策原文', exact: true }).click()
        const extract = page.getByRole('button', { name: '重新提取候选', exact: true })
        const fetch = page.getByRole('button', { name: '重新获取来源', exact: true })
        assert.equal(await extract.isDisabled(), false, 'source A keeps the extraction retry enabled')
        const extracts = await count(page, 'extract')
        await extract.click()
        await page.waitForFunction(before => globalThis.mobileCalls.filter(call => call.action === 'extract').length > before, extracts, { timeout: 10000 })
        assert.equal((await payloadOf(page, 'extract')).source, 'a', 'the extraction retry targets the selected source')
        await page.waitForFunction(() => document.body.innerText.includes('候选仍需检查'), null, { timeout: 10000 })
        await page.locator('.source-tabs button').nth(1).click()
        assert.equal(await extract.isDisabled(), true, 'a failed source must not offer candidate extraction')
        assert.equal(await fetch.isDisabled(), false)
        const fetches = await count(page, 'fetch')
        await fetch.click()
        await page.waitForFunction(before => globalThis.mobileCalls.filter(call => call.action === 'fetch').length > before, fetches, { timeout: 10000 })
        assert.equal((await payloadOf(page, 'fetch')).source, 'b', 'the fetch retry targets the selected source')
        assert.equal(await count(page, 'extract'), extracts + 1, 'fetching a source does not spend an extra model call')
        await page.waitForFunction(() => document.body.innerText.includes('仍未取得正文'), null, { timeout: 10000 })
      },
    },
    {
      issue: '#249', title: 'a material without any policy body cannot offer the start action',
      options: {
        sources: [{ id: 'empty', title: '缺正文来源', url: 'https://policy.example/empty', text: '', status: 'url_only' }],
        fetch: { empty: [{ status: 'failed', error_code: 'FETCH_FAILED', text: '' }, { status: 'ready', text: sentence }] },
        extract: { empty: [{ audit: { status: 'SUCCESS' } }] },
      },
      async run(page) {
        await page.getByRole('button', { name: '恢复当前材料', exact: true }).click()
        await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
        await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
        const alert = page.getByRole('alert')
        await alert.waitFor({ timeout: 10000 })
        assert.ok((await alert.innerText()).includes('正文'), 'the blocked start states that a policy body is required')
        assert.equal(await page.evaluate(() => document.getElementById('page-title')?.textContent?.trim()), 'APK 与政策材料', 'a body-less material stays on the material step')
        assert.equal(await count(page, 'candidates'), 0, 'no candidate save is sent for a material the server must reject')
        assert.equal(await count(page, 'start'), 0)
        await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
        await waitTitle(page, '核对政策声明', 8000)
        const start = page.getByRole('button', { name: '保存候选并开始分析', exact: true })
        assert.equal(await start.isDisabled(), true, 'the start action is disabled while every source lacks text')
        assert.ok((await page.locator('main').innerText()).includes('可对照的政策正文'), 'the candidate step explains the missing prerequisite')
        await page.getByRole('button', { name: '修改材料', exact: true }).click()
        await waitTitle(page, 'APK 与政策材料', 8000)
        await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
        await waitTitle(page, '核对政策声明', 12000)
        assert.equal(await start.isDisabled(), false, 'a fetched body restores the existing start action')
        await start.click()
        await page.waitForFunction(() => globalThis.mobileCalls.some(call => call.action === 'start'), null, { timeout: 10000 })
        assert.equal(await count(page, 'candidates'), 1)
        await waitTitle(page, '扫描与对照进度', 12000)
      },
    },
  ]
  const checks = [], failures = []
  for (const scenario of scenarios) {
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true })
    const errors = []
    try {
      const page = await context.newPage()
      page.on('pageerror', error => errors.push(error.message))
      await page.addInitScript(issueBridge, scenario.options)
      await page.goto(origin)
      await scenario.run(page)
      assert.deepEqual(errors, [], 'no page errors')
      checks.push(`${scenario.issue} ${scenario.title}`)
    } catch (error) {
      failures.push(`${scenario.issue}: ${error.message.split('\n')[0]}`)
    } finally { await context.close() }
  }
  if (failures.length) throw new Error('issue regressions failed:\n  - ' + failures.join('\n  - '))
  return checks
}

async function verifyCoarsePointer(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  try {
    const page = await context.newPage()
    await page.addInitScript(bridge, { ...fixtures, policyTitle: longTitle, policyText: longPolicy, policyUrl: longUrl })
    await page.goto(origin)
    const state = await page.evaluate(() => ({
      hoverNone: matchMedia('(hover: none)').matches,
      coarse: matchMedia('(pointer: coarse)').matches,
      viewport: document.querySelector('meta[name="viewport"]')?.getAttribute('content') || '',
    }))
    assert.equal(state.hoverNone, true, 'coarse-pointer context must report (hover: none)')
    assert.equal(state.coarse, true, 'coarse-pointer context must report (pointer: coarse)')
    assert.match(state.viewport, /viewport-fit=cover/, 'viewport meta must opt into safe-area insets')
    assert.match(state.viewport, /interactive-widget=resizes-content/, 'viewport meta must resize for the soft keyboard')
    // Touch presses must not leave a sticky hover highlight on controls that stay
    // mounted across the tap (the settings icon button).
    const settings = page.getByRole('button', { name: '服务与存储设置' })
    const resting = await settings.evaluate(element => getComputedStyle(element).backgroundColor)
    await settings.tap()
    await page.locator('dialog.ui-sheet.m-settings-dialog').waitFor({ timeout: 5000 })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    const after = await settings.evaluate(element => getComputedStyle(element).backgroundColor)
    assert.equal(after, resting, 'touch must not leave a hover highlight behind')
    const restore = page.getByRole('button', { name: '恢复当前材料', exact: true })
    await restore.tap()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
    await page.waitForTimeout(200)
    await page.getByText('使用手机上的个人模型', { exact: true }).tap()
    const field = await page.evaluate(() => {
      const input = document.querySelector('.mobile-field input')
      const rect = input.getBoundingClientRect()
      return { size: Number.parseFloat(getComputedStyle(input).fontSize), height: Math.round(rect.height) }
    })
    assert.ok(field.size >= 16, `coarse pointer: field font-size ${field.size}px < 16px`)
    assert.ok(field.height >= 48, `coarse pointer: field height ${field.height}px < 48px`)
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'coarse/768')
    await page.setViewportSize({ width: 844, height: 390 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'coarse/844x390')
    return ['coarse pointer: tap works without sticky hover, 16px/48px visible fields, 768/844 layouts overflow-free']
  } finally { await context.close() }
}

async function main() {
  const server = net.createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  const child = spawn('npm run dev', { ...spawnOptions(root, { PRIVACYTRACE_WEB_PORT: String(port) }), windowsHide: true, stdio: 'ignore' })
  let browser
  const checks = []
  try {
    const origin = `http://127.0.0.1:${port}`
    const deadline = Date.now() + 45000
    while (true) {
      try { if ((await fetch(origin)).ok) break } catch {}
      if (child.exitCode !== null || Date.now() > deadline) throw new Error('Owned Vite did not start')
      await new Promise(resolve => setTimeout(resolve, 150))
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    const errors = [], api = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) api.push(request.url()) })
    await page.addInitScript(bridge, { ...fixtures, policyTitle: longTitle, policyText: longPolicy, policyUrl: longUrl })
    await page.goto(origin)
    await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
    // #169 mobile brand slot: the import step shows the same-origin symbol in the
    // 48x48 app-bar slot (no letter placeholder); later steps keep the back button.
    const mobileBrand = await page.evaluate(async () => {
      const slot = document.querySelector('.m-appbar-brand')
      const image = slot?.querySelector('img.brand-mark-image')
      if (!image) return null
      let decoded = false
      try { await image.decode(); decoded = true } catch {}
      const rect = image.getBoundingClientRect()
      return {
        complete: image.complete, currentSrc: image.currentSrc,
        naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
        width: Math.round(rect.width), height: Math.round(rect.height),
        slotText: (slot.textContent || '').trim(), decoded,
      }
    })
    assert.ok(mobileBrand, 'mobile import must render the brand slot')
    assert.equal(mobileBrand.complete, true, 'mobile brand image must finish loading')
    assert.ok(mobileBrand.currentSrc.endsWith('/brand/privacy-trace-symbol.svg'), `mobile brand must resolve the same-origin symbol (got ${mobileBrand.currentSrc})`)
    assert.ok(mobileBrand.naturalWidth > 0 && mobileBrand.naturalHeight > 0, 'mobile brand image must decode to real pixels')
    assert.ok(mobileBrand.width > 0 && mobileBrand.height > 0, 'mobile brand slot renders a positive box')
    assert.equal(mobileBrand.slotText, '', 'mobile brand slot must not keep a letter placeholder')
    assert.equal(mobileBrand.decoded, true, 'mobile brand img.decode() must resolve')
    const mobileSymbol = await page.request.get(origin + '/brand/privacy-trace-symbol.svg')
    assert.equal(mobileSymbol.status(), 200, 'the mobile shell must load the same-origin brand symbol')
    assert.ok((await mobileSymbol.body()).toString('utf8').includes('<svg'), 'the brand symbol must be SVG markup')
    checks.push('brand: mobile import slot decodes the same-origin symbol with no letter placeholder')
    await checkMobileDesign(page)
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `import/${width}`)
      await assertNoDocumentZoom(page, `import/${width}`)
      await shot(page, `round2-import-${width}.png`)
    }
    checks.push('import: 120-char title, 400-char URL and 128-char hash stay inside 320/390/768 without mobile shrink-to-fit')
    // Fine pointer keeps hover feedback (capability branch, not a global kill).
    await page.setViewportSize({ width: 390, height: 844 })
    const refresh = page.getByRole('button', { name: '重新读取材料', exact: true }).last()
    const rest = await refresh.evaluate(element => getComputedStyle(element).backgroundColor)
    await refresh.hover()
    await page.waitForTimeout(200)
    const hovered = await refresh.evaluate(element => getComputedStyle(element).backgroundColor)
    assert.notEqual(rest, hovered, 'fine pointers must keep hover feedback')
    await page.mouse.move(0, 0)
    checks.push('pointer: fine hover feedback preserved through the (hover:hover) and (pointer:fine) gate')
    await page.getByText('使用手机上的个人模型', { exact: true }).click()
    await page.getByRole('button', { name: '配置模型', exact: true }).click()
    await page.getByLabel('模型名称', { exact: true }).fill('compatible-chat')
    await page.getByLabel('应用名称或包名', { exact: true }).fill('com.example.mobile.ok')
    checks.push(await assertTouchTargets(page, 'import'))
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `import/200%/${width}`)
      await shot(page, `round2-import-200-${width}.png`)
      await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    }
    checks.push('import: 200% root font keeps 320/390 free of page overflow with the model fields open')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
    await waitTitle(page, '核对政策声明', 12000)
    assert.equal(await page.locator('.m-appbar-brand').count(), 0, 'non-import steps replace the brand slot with the back button')
    assert.equal(await page.getByRole('button', { name: '返回上一步' }).count(), 1, 'non-import steps keep the back arrow')
    assert.equal(await page.evaluate(() => document.querySelectorAll('.mobile-panel-tabs button').length), 2, 'candidates: Android segmented control must render')
    await checkMobileDesign(page)
    await page.locator('.source-tabs button').nth(1).click()
    await page.getByRole('tab', { name: '政策原文', exact: true }).click()
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `candidates/long/${width}`)
      await shot(page, `round2-candidates-long-${width}.png`)
    }
    await page.locator('.source-tabs button').first().click()
    await page.getByRole('tab', { name: '候选声明', exact: false }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    checks.push(await assertTouchTargets(page, 'candidates'))
    // Soft-keyboard fallback: the hidden height is reserved and the focused field
    // can be scrolled above it; this simulates the measurement, not a real IME.
    await page.locator('#candidate-quote').focus()
    const keyboard = await page.evaluate(async () => {
      const viewport = window.visualViewport
      Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight - 460 })
      Object.defineProperty(viewport, 'scale', { configurable: true, get: () => 1 })
      viewport.dispatchEvent(new Event('resize'))
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      const root = document.documentElement
      return {
        open: root.classList.contains('keyboard-open'),
        inset: Number.parseFloat(root.style.getPropertyValue('--keyboard-inset')),
        bodyPadding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
        scrollPadding: Number.parseFloat(getComputedStyle(root).scrollPaddingBottom),
        focusRetained: document.activeElement === document.querySelector('#candidate-quote'),
      }
    })
    assert.equal(keyboard.open, true, 'keyboard fallback must mark html.keyboard-open')
    assert.ok(Math.abs(keyboard.inset - 460) <= 2, `expected --keyboard-inset ~460px, got ${keyboard.inset}`)
    assert.ok(keyboard.bodyPadding >= 459, `body must reserve the keyboard height (got ${keyboard.bodyPadding})`)
    assert.ok(keyboard.scrollPadding >= 475, `scroll-padding-bottom must include the keyboard (got ${keyboard.scrollPadding})`)
    assert.equal(keyboard.focusRetained, true, 'the focused field must keep focus')
    const keyboardReach = await page.evaluate(() => {
      const field = document.querySelector('#candidate-quote')
      field.scrollIntoView({ block: 'center' })
      const rect = field.getBoundingClientRect()
      const bar = document.querySelector('.m-actionbar').getBoundingClientRect()
      return { bottom: Math.round(rect.bottom), keyboardTop: innerHeight - 460, barTop: Math.round(bar.top) }
    })
    assert.ok(keyboardReach.bottom <= keyboardReach.keyboardTop, 'the focused field must scroll above the keyboard')
    assert.ok(keyboardReach.barTop <= keyboardReach.keyboardTop + 1, 'the fixed action bar must lift above the keyboard')
    await shot(page, 'round2-keyboard-390.png')
    const reset = await page.evaluate(async () => {
      const viewport = window.visualViewport
      Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight })
      viewport.dispatchEvent(new Event('resize'))
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      return {
        open: document.documentElement.classList.contains('keyboard-open'),
        padding: parseFloat(getComputedStyle(document.body).paddingBottom),
        barBottom: Math.round(document.querySelector('.m-actionbar').getBoundingClientRect().bottom),
      }
    })
    assert.equal(reset.open, false, 'closing the keyboard must clear html.keyboard-open')
    assert.ok(reset.padding <= 1, 'closing the keyboard must release the reserved space')
    assert.ok(Math.abs(reset.barBottom - 844) <= 1, 'the action bar must return to the bottom edge')
    checks.push('soft keyboard: --keyboard-inset reserves the IME height, lifts the action bar, keeps the field reachable, releases on close')
    await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click()
    await waitTitle(page, '扫描与对照进度', 12000)
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 12000 })
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告', 12000)
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `report/${width}`)
      await shot(page, `round2-report-${width}.png`)
    }
    const reportText = await page.evaluate(() => document.body.innerText)
    assert.ok(reportText.includes('PARTIAL'), 'report must keep the PARTIAL coverage wording')
    checks.push('report: no page overflow at 320/390/768; PARTIAL coverage stays visible')
    await page.setViewportSize({ width: 320, height: 844 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'report/200%/320')
    await shot(page, 'round2-report-200-320.png')
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    await page.setViewportSize({ width: 390, height: 844 })
    checks.push('report: 200% root font keeps the mobile report inside 320px')
    // Inline evidence: open twice, return to the row, exact scroll position.
    await page.evaluate(() => window.scrollTo(0, 0))
    for (let round = 1; round <= 2; round += 1) {
      const trigger = page.locator('.m-issue-list .evidence-button').first()
      await trigger.scrollIntoViewIfNeeded()
      const before = await page.evaluate(() => Math.round(scrollY))
      await trigger.click()
      const panel = page.locator('.report-evidence-inline #evidence-panel')
      await panel.waitFor({ timeout: 5000 })
      assert.equal(await page.evaluate(() => Boolean(document.activeElement?.closest('.report-evidence-inline #evidence-panel'))), true, `round ${round}: focus must move into the inline evidence panel`)
      assert.equal(await page.locator('dialog.ui-sheet.m-evidence-sheet').count(), 0, `round ${round}: no sheet may open over the report`)
      if (round === 1) {
        await shot(page, 'round2-report-preview-390.png')
        checks.push(await assertTouchTargets(page, 'evidence-inline'))
      }
      await panel.getByRole('button', { name: '返回刚才的操作', exact: true }).click()
      await page.waitForTimeout(250)
      assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('.m-issue-list .evidence-button')), true, `round ${round}: focus must return to the triggering row`)
      assert.ok(Math.abs(await page.evaluate(() => Math.round(scrollY)) - before) <= 2, `round ${round}: returning must restore the exact scroll position`)
    }
    checks.push('inline evidence: opening twice keeps the section, restores focus and the exact scroll position')
    const ledger = await page.evaluate(() => globalThis.mobileCalls)
    assert.equal(ledger.filter(call => call.method === 'workflow' && call.args.action === 'start').length, 1, 'a lost start response must not submit a second analysis')
    const save = ledger.find(call => call.method === 'workflow' && call.args.action === 'candidates')
    assert.equal(JSON.parse(save.args.payload).candidates[0].checked, false)
    assert(ledger.some(call => call.method === 'workflow' && call.args.action === 'report'))
    assert.deepEqual(api, [], 'the native shell must not use browser HTTP credentials')
    assert.deepEqual(errors, [])
    checks.push('native bridge: exactly one start after a lost response, candidate payload and report read recorded, zero browser API requests')
    checks.push(...await verifyIssueFixes(browser, origin))
    checks.push(...await verifyCoarsePointer(browser, origin))
    fs.writeFileSync(path.join(output, 'walkthrough.json'), JSON.stringify({
      result: 'PASS',
      scope: 'production Vue mobile shell with mocked native bridge; no APK scan, paid model, Android WebView or real keyboard execution',
      viewports: [320, 390, 768],
      landscape_viewport: [844, 390],
      keyboard_viewport: [390, 380],
      large_text: '200% root font size',
      checks,
      ledger,
      browser_api_requests: api,
      page_errors: errors,
      device_items: 'NOT_RUN: real Android WebView/APK, real IME, display cutout safe-area, system font scaling/pinch zoom, TalkBack',
    }, null, 2))
    console.log('Mobile shell regression harness passed (round 1 invariants on the round-2 shell).')
    console.log('Issue #144 mobile checks:', checks.length, 'groups —')
    for (const check of checks) console.log('  - ' + check)
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
