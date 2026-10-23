#!/usr/bin/env node
/**
 * Issue #265 — capture the mobile App screenshots used by the 10-page review deck.
 *
 * The production Vue entry (`apps/web/src/mobile/MobileApp.vue`) runs against a
 * mocked, deterministic native bridge; no Android device, APK, model, Docker or
 * backend request is involved. Two 390x844 / DPR 3 frames feed slide 2 (mobile
 * import) and slide 4 (mobile report); 320x568 / DPR 2 frames are the narrow
 * screen cross-check. Every frame is written with its own provenance block
 * (source commit, capture date, viewport, DPR, fixture, SHA-256) into
 * `showcase/privacytrace-review/capture/manifest.json`, which
 * `deck/build_deck.py` consumes instead of hand-named PNGs.
 *
 * Run from the repository root: `node scripts/capture-review-deck-shots.cjs`
 * Output: showcase/privacytrace-review/capture/
 */
const assert = require('node:assert/strict')
const crypto = require('node:crypto')
const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const vm = require('node:vm')
const { execFileSync, spawn } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')

const root = path.resolve(__dirname, '..')
const outDir = path.join(root, 'showcase/privacytrace-review/capture')
const manifestPath = path.join(outDir, 'manifest.json')
fs.mkdirSync(outDir, { recursive: true })

const UI_SCOPE = ['apps/web', 'apps/mobile', 'scripts/fixtures']
const REPO = 'MrEcho114/PrivacyTrace'
const ISSUE = 265

function git(...args) {
  return execFileSync('git', args, { cwd: root }).toString().trim()
}
function sha256(buffer) {
  return crypto.createHash('sha256').update(buffer).digest('hex')
}
function localDate(date) {
  const pad = value => String(value).padStart(2, '0')
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`
}

// The capture must describe the UI that is actually in the tree. Refuse to run
// over uncommitted frontend edits, so a dirty worktree cannot silently produce
// screenshots that no commit owns.
const sourceCommit = git('rev-parse', 'HEAD')
const sourceCommitShort = git('rev-parse', '--short=7', 'HEAD')
const dirtyUi = git('status', '--porcelain', '--', ...UI_SCOPE)
assert.equal(dirtyUi, '', `refusing to capture over uncommitted UI changes (${UI_SCOPE.join(', ')}):\n${dirtyUi}`)
const capturedAt = new Date()
const captureDate = localDate(capturedAt)
const capturedAtIso = capturedAt.toISOString()

// Reuse the deterministic report/taxonomy fixtures from the desktop harness so
// the mobile report is the same acceptance fixture, only relabelled as the
// synthetic sample it actually is (the raw fixture is source_origin REAL_SCAN).
const source = fs.readFileSync(path.join(__dirname, 'verify-frontend-flow.cjs'), 'utf8')
const fixtureContext = {}
vm.runInNewContext(
  source.slice(source.indexOf('const policySentence'), source.indexOf('const fixtureRoutes')) +
    '\nthis.fixtures = { reportFixture, taxonomyFixture, policySentence }',
  fixtureContext,
)
const base = JSON.parse(JSON.stringify(fixtureContext.fixtures))
const policySentence = base.policySentence
const packageName = 'com.example.synthetic.location'
const sampleName = '合成示例 · 位置信息'
const policySources = [
  {
    id: 'policy-web',
    title: '官网隐私政策 · 全文快照',
    url: 'https://example.com/privacy',
    source_type: 'OFFICIAL_WEB_POLICY',
    text: policySentence,
    status: 'manual',
    version: 'UNKNOWN',
    provenance: 'EXTERNAL_CHAT_EXPORT',
  },
  {
    id: 'policy-in-app',
    title: '应用内政策 · 手动补入',
    url: 'https://example.com/in-app-policy',
    source_type: 'IN_APP_POLICY',
    text: '我们会在您使用附近门店功能时读取设备位置信息。',
    status: 'manual',
    version: 'UNKNOWN',
    provenance: 'EXTERNAL_CHAT_EXPORT',
  },
]
const reportFixture = {
  ...base.reportFixture,
  sample: {
    ...base.reportFixture.sample,
    name: sampleName,
    package_name: packageName,
    version_name: '1.0.7',
  },
  job: {
    ...base.reportFixture.job,
    sample_id: 'sample-synthetic-location',
    package_name: packageName,
    source_origin: 'SYNTHETIC',
  },
  delivery_mode: 'PERSISTED_REPLAY',
}
const bridgeFixture = { reportFixture, taxonomyFixture: base.taxonomyFixture, policySentence, packageName, policySources }

// Mocked Tauri command surface (same shape as verify-frontend-round2.cjs).
function bridge(options) {
  globalThis.isTauri = true
  const context = { origin: 'https://analysis.example/', draft: 'a'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
  const job = { ...options.reportFixture.job, id: 'b'.repeat(32), state: 'QUEUED', error: null }
  const draft = {
    id: context.draft,
    name: options.packageName,
    uploaded: true,
    revision: 1,
    apk_sha256: 'c'.repeat(128),
    sources: options.policySources.map(item => ({ ...item })),
    candidates: [],
    jobs: [],
  }
  let jobReads = 0
  const events = []
  function advanceJob() {
    jobReads += 1
    job.state = jobReads === 1 ? 'STATIC_ANALYSIS' : 'SUCCEEDED'
    events.push({ state: job.state, at: new Date(Date.UTC(2026, 9, 23, 12, jobReads)).toISOString() })
    if (draft.jobs[0]) draft.jobs[0].events = [...events]
    return job
  }
  globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
    const method = command.split('|')[1]
    if (method === 'upload_selected' || method === 'refresh_upload') return context
    if (method === 'delete_upload') return { ...context, state: 'DELETED' }
    if (method === 'model_status') return { configured: false, endpoint: null }
    if (method === 'cancel') return
    if (method !== 'workflow') throw new Error('Unexpected native method ' + method)
    const action = args.action
    const input = JSON.parse(args.payload)
    let data = draft
    if (action === 'taxonomy') data = options.taxonomyFixture
    else if (action === 'read' || action === 'discover' || action === 'fetch') data = draft
    else if (action === 'extract') {
      draft.candidates = [{ id: 'candidate-1', source_id: 'policy-web', excerpt: options.policySentence, data_type: 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }]
      draft.revision++
    } else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision++ }
    else if (action === 'start') {
      draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: '2026-10-23T12:00:00Z' }] })
      events.push({ state: 'QUEUED', at: '2026-10-23T12:00:00Z' })
      draft.revision++
      data = { ...job }
    } else if (action === 'job') data = { ...advanceJob() }
    else if (action === 'report') data = { ...options.reportFixture, job: { ...job }, demo: false, result: { ...options.reportFixture.result, job_id: job.id } }
    else if (action === 'cancel-job') { job.state = 'CANCELLED'; data = { ...job } }
    else if (action === 'retry-job') { job.id = 'd'.repeat(32); job.state = 'QUEUED'; data = { ...job } }
    else throw new Error('Unexpected workflow action ' + action)
    return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
  } }
}

const screens = []
async function shot(page, file, meta) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(180)
  const target = path.join(outDir, file)
  await page.screenshot({ path: target, animations: 'disabled' })
  const buffer = fs.readFileSync(target)
  const viewport = page.viewportSize()
  const dpr = await page.evaluate(() => window.devicePixelRatio)
  const size = await page.evaluate(() => ({ width: document.documentElement.scrollWidth, height: document.documentElement.scrollHeight }))
  screens.push({
    file,
    scenario: meta.scenario,
    state: meta.state,
    viewport: `${viewport.width}x${viewport.height}`,
    device_scale_factor: dpr,
    pixel_size: `${Math.round(viewport.width * dpr)}x${Math.round(viewport.height * dpr)}`,
    page_scroll_height: size.height,
    platform: 'Chromium headless viewport simulation (not Android WebView, not a device)',
    bridge: 'mocked Tauri native bridge (`__TAURI_INTERNALS__.invoke`); no backend request',
    fixture: 'deterministic report/taxonomy acceptance fixture relabelled SYNTHETIC + fixed policy sources; no APK/model/Docker/device execution',
    source_commit: sourceCommit,
    captured_at: capturedAtIso,
    capture_date: captureDate,
    bytes: buffer.length,
    sha256: sha256(buffer),
  })
}

async function waitTitle(page, title, timeout = 12000) {
  await page.waitForFunction(expected => document.getElementById('page-title')?.textContent?.trim() === expected, title, { timeout })
}

async function runDesktopWidth(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 3 })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(bridge, bridgeFixture)
  await page.goto(origin)
  await page.getByRole('button', { name: '选择应用并上传', exact: true }).waitFor({ timeout: 10000 })

  // Slide 2 — mobile import step with a selected, synthetic material.
  await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
  await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
  await waitTitle(page, 'APK 与政策材料')
  await page.evaluate(() => window.scrollTo(0, 0))
  assert.equal(await page.evaluate(() => document.querySelectorAll('.m-source-row').length), 2, 'the import step must show both policy sources')
  const importText = await page.evaluate(() => document.querySelector('.mobile-workspace')?.innerText || '')
  assert.match(importText, /com\.example\.synthetic\.location/, 'import screenshot must carry the synthetic package name')
  await shot(page, 'mobile-import-390x844-dpr3.png', { scenario: 'import', state: 'material selected + two policy sources, fixed synthetic demo data' })
  screens[screens.length - 1].asserted_text = ['APK 与政策材料', '当前分析材料', '政策来源', packageName]

  // Slide 4 — mobile report reached through candidates → progress → report.
  await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
  await waitTitle(page, '核对政策声明')
  await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click()
  await waitTitle(page, '扫描与对照进度')
  await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 15000 })
  await page.getByRole('button', { name: '查看报告', exact: true }).click()
  await waitTitle(page, 'APP 隐私收集越权报告')
  await page.evaluate(() => window.scrollTo(0, 0))
  const reportText = await page.evaluate(() => document.querySelector('.mobile-workspace')?.innerText || '')
  assert.match(reportText, /人工示例 · SYNTHETIC/, 'report screenshot must be labelled SYNTHETIC, never REAL_SCAN')
  assert.match(reportText, /持久化回放 · REPLAY/, 'report screenshot must be labelled as a persisted replay')
  assert.doesNotMatch(reportText, /REAL_SCAN/, 'report screenshot must not claim a real APK scan')
  assert.equal(errors.length, 0, `page errors during capture: ${errors.join('; ')}`)
  await shot(page, 'mobile-report-390x844-dpr3.png', { scenario: 'report', state: 'synthetic sample, persisted replay, two issues' })
  screens[screens.length - 1].asserted_text = ['APP 隐私收集越权报告', sampleName, '人工示例 · SYNTHETIC', '持久化回放 · REPLAY']
  await context.close()
}

async function runNarrow(browser, origin) {
  const context = await browser.newContext({ viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true, deviceScaleFactor: 2 })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', error => errors.push(error.message))
  await page.addInitScript(bridge, bridgeFixture)
  await page.goto(origin)
  await page.getByRole('button', { name: '选择应用并上传', exact: true }).waitFor({ timeout: 10000 })
  await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
  await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
  await waitTitle(page, 'APK 与政策材料')
  await page.evaluate(() => window.scrollTo(0, 0))
  const overflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }))
  assert.ok(overflow.scrollWidth <= overflow.innerWidth, `320px import step must not scroll horizontally (${overflow.scrollWidth} > ${overflow.innerWidth})`)
  await shot(page, 'mobile-import-320x568-dpr2.png', { scenario: 'import', state: 'narrow-screen cross-check with selected material' })

  await page.getByRole('button', { name: '准备政策并继续', exact: true }).click()
  await waitTitle(page, '核对政策声明')
  await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click()
  await waitTitle(page, '扫描与对照进度')
  await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 15000 })
  await page.getByRole('button', { name: '查看报告', exact: true }).click()
  await waitTitle(page, 'APP 隐私收集越权报告')
  await page.evaluate(() => window.scrollTo(0, 0))
  const reportOverflow = await page.evaluate(() => ({ scrollWidth: document.documentElement.scrollWidth, innerWidth: window.innerWidth }))
  assert.ok(reportOverflow.scrollWidth <= reportOverflow.innerWidth, `320px report must not scroll horizontally (${reportOverflow.scrollWidth} > ${reportOverflow.innerWidth})`)
  assert.equal(errors.length, 0, `page errors during narrow capture: ${errors.join('; ')}`)
  await shot(page, 'mobile-report-320x568-dpr2.png', { scenario: 'report', state: 'narrow-screen cross-check of the report' })
  await context.close()
}

async function main() {
  const probe = net.createServer()
  await new Promise(resolve => probe.listen(0, '127.0.0.1', resolve))
  const port = probe.address().port
  await new Promise(resolve => probe.close(resolve))
  const child = spawn('npm run dev', { ...spawnOptions(root, { PRIVACYTRACE_WEB_PORT: String(port) }), windowsHide: true, stdio: 'ignore' })
  let browser
  try {
    const origin = `http://127.0.0.1:${port}`
    const deadline = Date.now() + 60000
    while (true) {
      try { if ((await fetch(origin)).ok) break } catch {}
      if (child.exitCode !== null || Date.now() > deadline) throw new Error('Owned Vite did not start')
      await new Promise(resolve => setTimeout(resolve, 150))
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    await runDesktopWidth(browser, origin)
    await runNarrow(browser, origin)

    const manifest = {
      schema: 'privacytrace/review-deck-shots@1',
      issue: ISSUE,
      repository: REPO,
      purpose: 'UI screens consumed by showcase/privacytrace-review/deck/build_deck.py for the 10-page review deck (v0.2)',
      generated_by: 'scripts/capture-review-deck-shots.cjs',
      generated_at: capturedAtIso,
      capture_date: captureDate,
      source_commit: sourceCommit,
      source_commit_short: sourceCommitShort,
      source_ui_scope: UI_SCOPE,
      source_note: 'Source commit is the frozen main baseline at capture time; apps/web and apps/mobile were unmodified in the worktree.',
      platform: 'Chromium headless viewport simulation; not Android WebView and not a device run',
      fixture: 'production Vue mobile shell + mocked Tauri native bridge + deterministic synthetic fixture; no APK, model, Docker or backend',
      device_items: 'NOT_RUN',
      screens,
    }
    fs.writeFileSync(manifestPath, JSON.stringify(manifest, null, 2) + '\n', 'utf8')
    console.log(JSON.stringify({ ok: true, manifest: path.relative(root, manifestPath), source_commit: sourceCommitShort, screens: screens.map(screen => `${screen.file} ${screen.pixel_size} ${screen.sha256.slice(0, 12)}`) }, null, 2))
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}

main().catch(error => { console.error(error); process.exitCode = 1 })
