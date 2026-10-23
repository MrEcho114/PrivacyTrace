#!/usr/bin/env node
/**
 * Issue #144 round 2 — Android portrait shell, evidence sheet and mobile flow.
 *
 * Browser-level verification of the Tauri Android entry (`MobileApp.vue`):
 * 390x844 main flow, 320x568 / 768x1024 / 844x390 boundaries, 200% root font,
 * simulated soft keyboard, hardware back + scroll restoration, evidence sheet
 * focus/close, 48px targets, 16px inputs, no horizontal overflow, settings page
 * and reduced-motion. The native bridge is mocked; no APK, model, Docker or
 * Android device is executed. Chromium viewport simulation is NOT device proof.
 *
 * Run from the repository root: `node scripts/verify-frontend-round2.cjs`
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const net = require('node:net')
const { execFileSync, spawn } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')

const root = path.resolve(__dirname, '..')
// #165: the #144 round-2 screenshots under docs/acceptance/issue144 are historical
// evidence and keep their original SHA/state. Re-runs write to tmp/ instead; the
// #165 acceptance record references the new captures from docs/acceptance/issue165.
const evidenceDir = path.join(root, 'tmp/issue144-round2/evidence')
fs.mkdirSync(evidenceDir, { recursive: true })
const sourceSha = execFileSync('git', ['rev-parse', '--short=12', 'HEAD'], { cwd: root }).toString().trim()
const capturedAt = new Date().toISOString()

// Reuse the deterministic report/taxonomy fixtures from the desktop harness.
const source = fs.readFileSync(path.join(__dirname, 'verify-frontend-flow.cjs'), 'utf8')
const fixtureContext = {}
vm.runInNewContext(source.slice(source.indexOf('const policySentence'), source.indexOf('const fixtureRoutes')) + '\nthis.fixtures = { reportFixture, taxonomyFixture, policySentence }', fixtureContext)
const fixtures = JSON.parse(JSON.stringify(fixtureContext.fixtures))
const longTitle = 'A'.repeat(120)
const longUrl = 'https://policy.example/' + 'a'.repeat(400)
const longPolicy = ('长政策正文保留原句、条件与不确定性，不因窄屏而截断。'.repeat(120)) + '\n' + longUrl
const bridgeFixtures = { ...fixtures, policyTitle: longTitle, policyText: longPolicy, policyUrl: longUrl }

const captions = []
const checks = []
const output = path.join(root, 'tmp/issue144-round2')
fs.mkdirSync(output, { recursive: true })

// ---------------------------------------------------------------- assertions
async function pageOverflow(page) {
  return page.evaluate(() => {
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
}
async function assertNoPageOverflow(page, label) {
  const measured = await pageOverflow(page)
  const viewport = page.viewportSize()
  const layout = await page.evaluate(() => ({ innerWidth: window.innerWidth, scale: window.visualViewport?.scale ?? 1 }))
  assert.equal(layout.innerWidth, viewport.width, `${label}: layout viewport is ${layout.innerWidth}px, not ${viewport.width}px (mobile shrink-to-fit means content overflowed)`)
  assert.equal(layout.scale, 1, `${label}: the page must not be zoomed out to fit overflowing content (scale ${layout.scale})`)
  assert.ok(measured.scrollWidth <= measured.innerWidth, `${label}: document scrollWidth ${measured.scrollWidth} exceeds ${measured.innerWidth}`)
  assert.ok(measured.bodyScrollWidth <= measured.innerWidth, `${label}: body scrollWidth ${measured.bodyScrollWidth} exceeds ${measured.innerWidth}`)
  assert.deepEqual(measured.offenders, [], `${label}: elements protrude past the viewport`)
  const sheet = await page.evaluate(() => {
    const body = document.querySelector('dialog.ui-sheet .ui-sheet-body')
    return body ? { overflow: body.scrollWidth - body.clientWidth } : null
  })
  if (sheet) assert.ok(sheet.overflow <= 1, `${label}: sheet body scrolls horizontally (${sheet.overflow}px)`)
}
async function assertTouchTargets(page, label) {
  const measured = await page.evaluate(() => {
    const short = []
    let total = 0
    const selector = [
      '.mobile-workspace button', '.mobile-workspace [role="tab"]', '.mobile-workspace summary',
      '.mobile-workspace label.text-upload', '.mobile-workspace .ui-button',
      '.mobile-workspace input:not([type="checkbox"]):not([type="radio"]):not([type="file"])',
      '.mobile-workspace select', '.mobile-workspace textarea',
      'dialog.ui-sheet button',
    ].join(',')
    for (const element of document.querySelectorAll(selector)) {
      if (!element.getClientRects().length) continue
      const style = getComputedStyle(element)
      if (style.display === 'none' || style.visibility === 'hidden') continue
      const rect = element.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      total += 1
      if (rect.width < 47.5 || rect.height < 47.5) {
        const name = (element.getAttribute('aria-label') || element.id || element.textContent || element.tagName).trim().slice(0, 26)
        short.push(name + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height))
      }
    }
    return { total, short }
  })
  assert.ok(measured.total >= 8, `${label}: expected a representative set of touch targets, got ${measured.total}`)
  assert.deepEqual(measured.short, [], `${label}: touch targets under 48x48 CSS px`)
  return `${label}: ${measured.total} controls >= 48x48`
}
async function assertFieldText(page, label) {
  const measured = await page.evaluate(() => {
    const fields = [...document.querySelectorAll('.mobile-workspace input:not([type="checkbox"]):not([type="radio"]):not([type="file"]), .mobile-workspace select, .mobile-workspace textarea')]
      .filter(element => element.getClientRects().length && getComputedStyle(element).display !== 'none')
    return fields.map(element => ({
      id: element.id || element.tagName.toLowerCase(),
      size: Number.parseFloat(getComputedStyle(element).fontSize),
    }))
  })
  assert.ok(measured.length > 0, `${label}: expected visible form fields`)
  const small = measured.filter(field => field.size < 15.5)
  assert.deepEqual(small, [], `${label}: text fields below 16px would trigger WebView zoom`)
  return `${label}: ${measured.length} visible fields >= 16px`
}
async function assertSingleTitle(page, expected, label) {
  const state = await page.evaluate(() => ({
    h1Count: document.querySelectorAll('h1').length,
    titles: [...document.querySelectorAll('#page-title')].map(element => element.textContent.trim()),
    headingBlocks: [...document.querySelectorAll('.page-heading')].filter(element => element.getClientRects().length).length,
  }))
  assert.equal(state.titles.length, 1, `${label}: exactly one #page-title must exist`)
  assert.equal(state.titles[0], expected, `${label}: page title ${JSON.stringify(state.titles[0])} != ${JSON.stringify(expected)}`)
  assert.equal(state.h1Count, 1, `${label}: the app bar must be the only h1 (found ${state.h1Count})`)
  assert.equal(state.headingBlocks, 0, `${label}: no duplicated .page-heading in the shell`)
}
async function shot(page, name, meta) {
  await page.evaluate(() => document.fonts.ready)
  await page.waitForTimeout(150)
  await page.screenshot({ path: path.join(evidenceDir, name), animations: 'disabled' })
  const viewport = page.viewportSize()
  captions.push({
    file: name,
    viewport: `${viewport.width}x${viewport.height}`,
    ...meta,
    platform: 'Chromium headless browser simulation (not Android WebView / device)',
    fixture: 'mocked native bridge + deterministic report/taxonomy fixture; no APK/model/Docker execution',
    source_sha: sourceSha,
    captured_at: capturedAt,
  })
}
async function waitTitle(page, title, timeout = 8000) {
  await page.waitForFunction(expected => document.getElementById('page-title')?.textContent?.trim() === expected, title, { timeout })
}
async function hardwareBack(page) {
  await page.evaluate(() => history.back())
  await page.waitForTimeout(300)
}
const focusedTitle = page => page.evaluate(() => document.activeElement?.id === 'page-title')
const focusedMeta = page => page.evaluate(() => document.activeElement?.getAttribute('aria-label') || document.activeElement?.id || document.activeElement?.tagName)

// ------------------------------------------------------------------ bridge
// Mocked Tauri command surface. `options.failJob` drives the FAILED progress state.
function bridge(options) {
  globalThis.isTauri = true
  const context = { origin: 'https://analysis.example/', draft: 'a'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
  const job = { ...options.reportFixture.job, id: 'b'.repeat(32), state: 'QUEUED', error: null }
  const draft = {
    id: context.draft,
    name: 'com.example.' + 'b'.repeat(160),
    uploaded: true,
    revision: 1,
    apk_sha256: 'c'.repeat(128),
    sources: [
      { id: 'policy', title: options.policyTitle, url: options.policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: options.policySentence, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
      { id: 'long', title: '示例隐私政策', url: options.policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: options.policyText, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
    ],
    candidates: [],
    jobs: [],
  }
  const ledger = globalThis.mobileCalls = []
  let configured = false, jobReads = 0
  const events = []
  function advanceJob() {
    jobReads += 1
    if (options.failJob) {
      job.state = 'FAILED'
      job.error = JSON.stringify({ code: 'SCAN_FAILED', message: '模拟扫描失败：证据不足以生成报告。' })
    } else {
      job.state = jobReads === 1 ? 'STATIC_ANALYSIS' : 'SUCCEEDED'
    }
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
      data = { ...job }
    }
    else if (action === 'job') data = { ...advanceJob() }
    else if (action === 'report') data = { ...options.reportFixture, job: { ...job }, demo: false, result: { ...options.reportFixture.result, job_id: job.id } }
    else if (action === 'cancel-job') { job.state = 'CANCELLED'; events.push({ state: 'CANCELLED', at: '2026-10-21T12:10:00Z' }); if (draft.jobs[0]) draft.jobs[0].events = [...events]; data = { ...job } }
    else if (action === 'retry-job') { job.id = 'd'.repeat(32); job.state = 'QUEUED'; job.error = null; events.length = 0; events.push({ state: 'QUEUED', at: '2026-10-21T12:11:00Z' }); data = { ...job } }
    else throw new Error('Unexpected workflow action ' + action)
    return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
  } }
}

async function selectAndPrepare(page) {
  await page.getByRole('button', { name: '选择应用', exact: true }).click()
  await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
  await page.getByRole('button', { name: '准备政策', exact: true }).click()
  await waitTitle(page, '核对政策声明', 12000)
}

async function openInlineEvidence(page) {
  const trigger = page.locator('.m-issue-list .evidence-button').first()
  await trigger.scrollIntoViewIfNeeded()
  const before = await page.evaluate(() => Math.round(scrollY))
  await trigger.click()
  const panel = page.locator('#evidence-panel')
  await panel.waitFor({ timeout: 5000 })
  // #295: the evidence panel is much shorter now, so opening it really scrolls the
  // reading region into view. Wait for that entrance scroll to settle before
  // returning; a tap during the animation is not the reading scenario under test.
  await page.waitForTimeout(700)
  const state = await page.evaluate(() => ({
    inline: Boolean(document.querySelector('.report-evidence-inline #evidence-panel')),
    dialogs: document.querySelectorAll('dialog.ui-sheet').length,
    overlays: document.querySelectorAll('.ui-sheet-overlay').length,
    focusInside: Boolean(document.activeElement?.closest('#evidence-panel')),
    returnLabel: [...document.querySelectorAll('#evidence-panel button')].find(button => button.textContent.trim() === '返回刚才的操作')?.textContent.trim(),
    current: document.querySelectorAll('.m-issue-row.report-row-current').length,
  }))
  assert.equal(state.inline, true, 'inline evidence: the panel renders below the issue list')
  assert.equal(state.dialogs, 0, 'inline evidence: no sheet or dialog may open')
  assert.equal(state.overlays, 0, 'inline evidence: no scrim overlay may render')
  assert.equal(state.focusInside, true, 'inline evidence: focus must move into the panel')
  assert.equal(state.returnLabel, '返回刚才的操作', 'inline evidence: the return control must be 返回刚才的操作')
  assert.equal(state.current, 1, 'inline evidence: exactly one row carries the current marker')
  assert.equal(await page.evaluate(() => document.querySelector('.report-evidence-inline').innerText.includes('UNKNOWN')), true, 'inline evidence: UNKNOWN wording must stay visible')
  return { trigger, before, panel }
}

async function main() {
  const server = net.createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  const child = spawn('npm run dev', { ...spawnOptions(root, { PRIVACYTRACE_WEB_PORT: String(port) }), windowsHide: true, stdio: 'ignore' })
  let browser
  try {
    const origin = `http://127.0.0.1:${port}`
    const deadline = Date.now() + 45000
    while (true) {
      try { if ((await fetch(origin)).ok) break } catch {}
      if (child.exitCode !== null || Date.now() > deadline) throw new Error('Owned Vite did not start')
      await new Promise(resolve => setTimeout(resolve, 150))
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    const page = await context.newPage()
    const errors = [], api = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) api.push(request.url()) })
    await page.addInitScript(bridge, bridgeFixtures)
    await page.goto(origin)
    await page.getByRole('button', { name: '选择应用', exact: true }).waitFor({ timeout: 10000 })

    // ---- shell frame at 390x844 -------------------------------------------
    const frame = await page.evaluate(() => {
      const appbar = document.querySelector('.m-appbar')
      const title = document.getElementById('page-title')
      const rail = [...document.querySelectorAll('.m-steps button')]
      const actionbar = document.querySelector('.m-actionbar')
      const primary = actionbar?.querySelector('.ui-button.primary')
      const viewport = document.querySelector('meta[name="viewport"]')?.getAttribute('content') || ''
      const theme = document.querySelector('meta[name="theme-color"]')?.getAttribute('content')
      const style = title ? getComputedStyle(title) : null
      return {
        appbarHeight: Math.round(appbar.getBoundingClientRect().height),
        titleFont: style?.fontFamily || '',
        titleSize: style?.fontSize || '',
        railCount: rail.length,
        railRows: new Set(rail.map(button => Math.round(button.getBoundingClientRect().top))).size,
        railDisabled: rail.map(button => button.disabled),
        current: rail.filter(button => button.getAttribute('aria-current') === 'step').length,
        back: Boolean(document.querySelector('.m-appbar button[aria-label="返回上一步"]')),
        settingsSize: (() => { const button = document.querySelector('.m-appbar button[aria-label="服务与存储设置"]'); const rect = button.getBoundingClientRect(); return [Math.round(rect.width), Math.round(rect.height)] })(),
        actionbarPosition: actionbar ? getComputedStyle(actionbar).position : '',
        actionbarBottom: actionbar ? Math.round(actionbar.getBoundingClientRect().bottom) : 0,
        primaryHeight: primary ? Math.round(primary.getBoundingClientRect().height) : 0,
        primaryDisabled: primary ? primary.disabled : null,
        primaryActions: actionbar ? actionbar.querySelectorAll('.ui-button.primary').length : 0,
        prepareDisabled: actionbar ? [...actionbar.querySelectorAll('.ui-button')].every(button => button.disabled) : null,
        viewport, theme,
        appbarColor: getComputedStyle(appbar).backgroundColor,
        shellHeight: Math.round(document.querySelector('.mobile-workspace').getBoundingClientRect().height),
        skip: Boolean(document.querySelector('.skip-link')),
        navLabel: document.querySelector('.m-steps')?.getAttribute('aria-label'),
        actionbarLabel: actionbar?.getAttribute('aria-label'),
        titleOutline: title ? getComputedStyle(title).outlineStyle : '',
      }
    })
    assert.ok(frame.appbarHeight >= 56, `app bar must be at least 56px (got ${frame.appbarHeight})`)
    assert.match(frame.titleFont, /Noto Serif SC/, 'app bar title must use the Pioneer serif')
    assert.equal(frame.titleSize, '20px', `app bar title must be 20px (got ${frame.titleSize})`)
    assert.equal(frame.railCount, 4, 'the step rail must have four steps')
    assert.equal(frame.railRows, 1, 'the step rail must stay on one row at 390px')
    assert.equal(frame.current, 1, 'exactly one step has aria-current=step')
    assert.deepEqual(frame.railDisabled, [false, true, true, true], 'future steps must be disabled before a material is selected')
    assert.equal(frame.back, false, 'import is the root step: no back arrow')
    assert.deepEqual(frame.settingsSize, [48, 48], `settings icon button must be 48x48 (got ${frame.settingsSize.join('x')})`)
    // #295: the empty material state has no fixed bar — the empty-state card owns
    // the single primary CTA, so nothing competes with it at 200% font.
    assert.equal(frame.actionbarPosition, '', 'the empty import state must not mount the fixed action bar')
    assert.equal(frame.primaryActions, 0, 'no red primary action before a material is selected')
    assert.equal(frame.primaryDisabled, null, 'the empty state keeps no primary action to disable')
    const emptyCta = await page.evaluate(() => {
      const primaries = [...document.querySelectorAll('.m-empty-card .ui-button.primary')]
      return primaries.length ? { count: primaries.length, height: Math.round(primaries[0].getBoundingClientRect().height) } : null
    })
    assert.ok(emptyCta, 'the empty state must expose one primary CTA inside the card')
    assert.equal(emptyCta.count, 1, 'the empty state keeps exactly one primary CTA')
    assert.ok(emptyCta.height >= 48, `the empty CTA must stay at least 48px (got ${emptyCta.height})`)
    assert.match(frame.viewport, /viewport-fit=cover/, 'viewport meta must opt into safe-area insets')
    assert.match(frame.viewport, /interactive-widget=resizes-content/, 'viewport meta must resize for the soft keyboard')
    assert.doesNotMatch(frame.viewport, /user-scalable=no|maximum-scale=1/, 'zoom must stay available')
    assert.equal(frame.theme, '#f5f4ed', 'theme-color must match the Claude canvas (--mt-bg)')
    assert.equal(frame.appbarColor, 'rgb(250, 249, 245)', 'app bar must use Claude --mt-surface')
    assert.ok(frame.shellHeight >= 844, `shell must fill 100dvh (got ${frame.shellHeight})`)
    assert.equal(frame.skip, true, 'the shell must keep the skip link')
    assert.equal(frame.navLabel, '创建流程', 'the step rail must be a labelled navigation landmark')
    assert.equal(frame.titleOutline, 'none', 'programmatic title focus must not paint a control-like focus ring')
    await assertSingleTitle(page, 'APK 与政策材料', 'import/empty')
    await assertNoPageOverflow(page, 'import/empty/390')
    await shot(page, '390-import-empty.png', { scenario: 'import', state: 'no material selected' })
    checks.push('390x844 shell: 56px serif app bar, one-row 4-step rail, empty-state primary CTA, 48px targets, 100dvh, viewport/theme/zoom contract')

    // ---- import selected ---------------------------------------------------
    await page.getByRole('button', { name: '选择应用', exact: true }).click()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 8000 })
    await assertSingleTitle(page, 'APK 与政策材料', 'import/selected')
    const selectedFrame = await page.evaluate(() => {
      const primaries = [...document.querySelectorAll('.m-actionbar .ui-button.primary')]
      const primary = primaries[0]
      return primary ? { count: primaries.length, height: Math.round(primary.getBoundingClientRect().height), disabled: primary.disabled } : null
    })
    assert.ok(selectedFrame, 'the actionable import state must expose one red primary action')
    assert.equal(selectedFrame.count, 1, 'exactly one red primary action in the action bar')
    assert.ok(selectedFrame.height >= 48, `the actionable primary must be at least 48px tall (got ${selectedFrame.height})`)
    assert.equal(selectedFrame.disabled, false, 'the actionable primary must be enabled once a material is selected')
    const barState = await page.evaluate(() => {
      const bar = document.querySelector('.m-actionbar')
      return { position: getComputedStyle(bar).position, bottom: Math.round(bar.getBoundingClientRect().bottom), label: bar.getAttribute('aria-label'), buttons: bar.querySelectorAll('.ui-button').length }
    })
    assert.equal(barState.position, 'fixed', 'the action bar must be fixed once a material is selected')
    assert.ok(Math.abs(barState.bottom - 844) <= 1, `action bar must sit on the bottom edge (bottom ${barState.bottom})`)
    assert.equal(barState.label, '当前步骤操作', 'the fixed action bar must expose a group label')
    assert.equal(barState.buttons, 1, 'the material step keeps exactly one bar action (准备政策)')
    assert.equal(await page.evaluate(() => document.querySelectorAll('.m-source-row').length), 2, 'both policy sources must render as collapsible rows')
    assert.equal(await page.evaluate(() => document.querySelectorAll('.m-steps button[disabled]').length), 2, 'candidates becomes reachable, progress/report stay disabled')
    await assertNoPageOverflow(page, 'import/selected/390')
    await page.getByText('使用手机上的个人模型', { exact: true }).click()
    checks.push(await assertFieldText(page, 'import/selected/390'))
    await assertTouchTargets(page, 'import/selected/390')
    await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, '390-import-selected.png', { scenario: 'import', state: 'material selected + policy sources' })

    // ---- settings page-like sheet -----------------------------------------
    const settingsTrigger = page.getByRole('button', { name: '服务与存储设置' })
    await settingsTrigger.click()
    const settings = page.locator('dialog.ui-sheet.m-settings-dialog')
    await settings.waitFor({ timeout: 5000 })
    const settingsState = await page.evaluate(() => {
      const dialog = document.querySelector('dialog.ui-sheet.m-settings-dialog')
      const body = dialog.querySelector('.ui-sheet-body')
      return {
        detail: dialog.classList.contains('ui-sheet--detail'),
        height: Math.round(dialog.getBoundingClientRect().height),
        title: dialog.querySelector('.ui-sheet-title')?.textContent?.trim(),
        close: dialog.querySelector('.ui-sheet-close')?.getAttribute('aria-label'),
        scrollable: getComputedStyle(body).overflowY === 'auto' && getComputedStyle(body).overscrollBehavior === 'contain',
        focusInside: Boolean(document.activeElement?.closest('dialog.ui-sheet.m-settings-dialog')),
        // #167 de-duplicated the repeated evidence-boundary section; the sheet now
        // carries exactly the model and the material/storage facts.
        sections: [...dialog.querySelectorAll('.m-settings-section h2')].map(heading => heading.textContent?.trim()),
      }
    })
    assert.equal(settingsState.detail, true, 'settings must use the page-like full-screen sheet variant')
    assert.ok(settingsState.height >= 843, `settings must fill the viewport (got ${settingsState.height})`)
    assert.equal(settingsState.title, '服务与存储设置', 'settings title must stay 服务与存储设置')
    assert.equal(settingsState.close, '关闭', 'settings close control must be labelled 关闭')
    assert.equal(settingsState.scrollable, true, 'settings body must scroll')
    assert.equal(settingsState.focusInside, true, 'settings focus must move into the dialog')
    assert.deepEqual(settingsState.sections, ['模型连接', '材料与存储'], 'settings must keep the model and material/storage sections once each')
    await assertNoPageOverflow(page, 'settings/390')
    await shot(page, '390-settings.png', { scenario: 'settings', state: 'page-like full-screen dialog' })
    await page.keyboard.press('Escape')
    await page.waitForTimeout(200)
    assert.equal(await settings.count(), 0, 'Escape must close the settings dialog')
    assert.equal(await focusedMeta(page), '服务与存储设置', 'closing settings must return focus to its trigger')
    // Hardware back closes the settings overlay without changing steps.
    await settingsTrigger.click()
    await settings.waitFor()
    await hardwareBack(page)
    assert.equal(await settings.count(), 0, 'hardware back must close the settings dialog first')
    await waitTitle(page, 'APK 与政策材料')
    checks.push('settings: full-screen page-like sheet, scroll body, Escape/hardware back close, focus returns to trigger')

    // ---- candidates --------------------------------------------------------
    await page.getByRole('button', { name: '准备政策', exact: true }).click()
    await waitTitle(page, '核对政策声明', 12000)
    await assertSingleTitle(page, '核对政策声明', 'candidates')
    assert.equal(await page.evaluate(() => Boolean(document.querySelector('.m-context'))), true, 'candidates must show the compact material context row')
    assert.equal(await page.evaluate(() => document.querySelector('.m-context').textContent.includes('材料版本')), true, 'context row must show the material revision')
    assert.equal(await page.evaluate(() => document.querySelectorAll('.flow-footer').length), 0, 'the candidate page footer must be gone inside the shell')
    const segmented = await page.evaluate(() => {
      const tabs = document.querySelector('.mobile-panel-tabs')
      const rect = tabs.getBoundingClientRect()
      return { visible: Boolean(tabs.getClientRects().length), width: Math.round(rect.width), buttons: tabs.querySelectorAll('button').length, selected: tabs.querySelector('button.selected')?.textContent?.trim() }
    })
    assert.equal(segmented.visible, true, 'mobile candidates must show the Android segmented control')
    assert.equal(segmented.buttons, 2, 'the segmented control keeps both candidate tabs')
    assert.ok(segmented.selected?.includes('候选声明'), 'the candidate tab is selected by default')
    const row = await page.evaluate(() => {
      const item = document.querySelector('.candidate-item')
      const rect = item.getBoundingClientRect()
      return { height: Math.round(rect.height), chevron: Boolean(item.querySelector('.candidate-chevron')), quoteSize: Number.parseFloat(getComputedStyle(document.querySelector('#candidate-quote')).fontSize) }
    })
    assert.ok(row.height >= 48, `candidate list rows must be at least 48px (got ${row.height})`)
    assert.equal(row.chevron, true, 'candidate rows must show the chevron')
    assert.ok(row.quoteSize >= 16, `candidate fields must be 16px (got ${row.quoteSize})`)
    await assertNoPageOverflow(page, 'candidates/390')
    checks.push(await assertTouchTargets(page, 'candidates/390'))
    checks.push(await assertFieldText(page, 'candidates/390'))
    await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, '390-candidates.png', { scenario: 'candidates', state: 'one extracted candidate + editor' })
    // Hardware-keyboard users must see where focus is: the global focus ring must
    // survive the shell's sticky/fixed layers and not be replaced by a bare colour.
    await page.keyboard.press('Tab')
    const focusRing = await page.evaluate(() => {
      const element = document.activeElement
      const style = getComputedStyle(element)
      return { tag: element.tagName, width: Number.parseFloat(style.outlineWidth), style: style.outlineStyle, offset: Number.parseFloat(style.outlineOffset) }
    })
    assert.ok(focusRing.width >= 2 && focusRing.style !== 'none', `keyboard focus must keep a visible ring (got ${focusRing.style} ${focusRing.width}px on ${focusRing.tag})`)
    assert.ok(focusRing.offset >= 0, 'the focus ring must not be clipped by the sticky app bar')
    checks.push('keyboard focus: global focus ring stays visible on the first focusable control')

    // ---- hardware back + scroll restoration (candidates <-> import) --------
    await page.evaluate(() => window.scrollTo(0, 320))
    await page.waitForTimeout(150)
    await hardwareBack(page)
    await waitTitle(page, 'APK 与政策材料')
    assert.equal(await focusedTitle(page), true, 'hardware back must focus the app bar title')
    await page.evaluate(() => history.forward())
    await page.waitForTimeout(400)
    await waitTitle(page, '核对政策声明')
    const restored = await page.evaluate(() => Math.round(scrollY))
    assert.ok(Math.abs(restored - 320) <= 4, `forward navigation must restore the candidates scroll position (got ${restored})`)
    assert.equal(await focusedTitle(page), true, 'forward navigation must focus the app bar title')
    checks.push('hardware back: candidate -> import, title focus, forward restores the exact per-step scroll position')

    // ---- progress + polling stability -------------------------------------
    await page.getByRole('button', { name: '保存并分析', exact: true }).click()
    await waitTitle(page, '扫描与对照进度', 12000)
    // The real mobile flow records discrete server stages: the first automatic
    // poll is 10s after the start (FIRST_POLL_MS), so wait for that poll instead
    // of a static fake stage list.
    await page.getByText('隔离扫描 APK', { exact: false }).first().waitFor({ timeout: 20000 })
    const progress = await page.evaluate(() => ({
      context: Boolean(document.querySelector('.m-context')),
      dots: document.querySelectorAll('.m-timeline-dot').length,
      status: document.querySelector('.m-status-card [role="status"]')?.textContent?.trim(),
      back: Boolean(document.querySelector('.m-appbar button[aria-label="返回上一步"]')),
    }))
    assert.equal(progress.context, true, 'progress must keep the compact context row')
    assert.ok(progress.dots >= 2, 'progress must render the Android timeline with event dots')
    assert.ok(progress.status, 'progress stage text must expose role=status')
    assert.equal(progress.back, true, 'progress shows the back arrow')
    await assertNoPageOverflow(page, 'progress/390')
    await shot(page, '390-progress.png', { scenario: 'progress', state: 'static analysis stage, timeline and polling' })
    // Polling must not move the reader or steal focus.
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.getByRole('button', { name: '服务与存储设置' }).focus()
    // The second automatic poll (25s interval, +jitter) reaches SUCCEEDED and
    // exposes the report action; wait for the real polling contract, not a
    // static control, then assert it moved neither scroll nor focus.
    await page.waitForFunction(() => [...document.querySelectorAll('.m-actionbar .ui-button')].some(button => button.textContent.includes('查看报告')), null, { timeout: 45000 })
    assert.equal(await page.evaluate(() => Math.round(scrollY)), 0, 'data polling must not reset the scroll position')
    assert.equal(await focusedMeta(page), '服务与存储设置', 'data polling must not steal focus')
    checks.push('progress: timeline/status semantics; automatic polling keeps scroll and focus')

    // hardware back progress -> candidates, forward, then open the report
    await hardwareBack(page)
    await waitTitle(page, '核对政策声明')
    await page.evaluate(() => history.forward())
    await waitTitle(page, '扫描与对照进度')
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告', 12000)
    const reportState = await page.evaluate(() => ({
      actionbar: Boolean(document.querySelector('.m-actionbar')),
      rows: document.querySelectorAll('.m-issue-list .evidence-button').length,
      partial: document.body.innerText.includes('PARTIAL'),
      h1: document.querySelectorAll('h1').length,
    }))
    assert.equal(reportState.actionbar, false, 'the report step has no fixed action bar')
    assert.ok(reportState.rows >= 2, 'the report must render issue rows as tappable buttons')
    assert.equal(reportState.partial, true, 'PARTIAL coverage must stay visible')
    assert.equal(reportState.h1, 1, 'the report keeps exactly one h1 (the app bar)')
    await assertNoPageOverflow(page, 'report/390')
    checks.push(await assertTouchTargets(page, 'report/390'))
    await shot(page, '390-report.png', { scenario: 'report', state: 'PARTIAL coverage, issue list, evidence entry points' })
    // The provenance disclosure keeps the unified source-state facts, on demand:
    // #167 replaced the raw UNREVIEWED/NOT_CHECKED labels with the canonical line,
    // and missing facts stay unknown rather than being promoted to reviewed.
    const summary = page.locator('.provenance > summary').first()
    await summary.scrollIntoViewIfNeeded()
    await page.waitForTimeout(150)
    await summary.click()
    await page.waitForTimeout(150)
    const provenanceText = await page.locator('.provenance').innerText()
    assert.ok(provenanceText.includes('来源未复核'), 'expanded provenance must keep the 来源未复核 fact')
    assert.ok(provenanceText.includes('附件未检查'), 'expanded provenance must keep the 附件未检查 fact')
    assert.ok(provenanceText.includes('正文不完整'), 'expanded provenance must map PARTIAL completeness to 正文不完整')
    assert.ok(provenanceText.includes('提取 PARTIAL'), 'expanded provenance must keep the extraction status as a separate fact')
    assert.ok(!provenanceText.includes('来源已复核'), 'a PARTIAL extraction must never be promoted to 来源已复核')
    checks.push('report: PARTIAL coverage visible; 来源未复核/正文完整度未知/附件未检查 facts stay in the expandable provenance section')

    // ---- inline evidence below the issue list -----------------------------
    const { trigger, before, panel } = await openInlineEvidence(page)
    assert.equal(await page.evaluate(() => document.querySelectorAll('#evidence-panel').length), 1, 'inline evidence renders exactly one evidence panel')
    assert.ok(await page.evaluate(() => Boolean(document.querySelector('.report-evidence-inline .evidence-panel'))), 'the inline region must contain the extracted EvidencePanel')
    const panelA11y = await page.evaluate(() => {
      const region = document.querySelector('.report-evidence-inline')
      const heading = region.querySelector('.section-heading h2')
      return {
        tag: region.tagName,
        label: region.getAttribute('aria-label'),
        title: heading?.textContent?.trim() ?? '',
        focusables: region.querySelectorAll('button, [href], input, select, textarea, [tabindex]:not([tabindex="-1"])').length,
      }
    })
    assert.equal(panelA11y.tag, 'SECTION', 'inline evidence must stay a section, not a dialog')
    assert.equal(panelA11y.label, '当前条目证据', 'inline evidence must be labelled 当前条目证据')
    assert.ok(panelA11y.title.includes('位置信息'), 'inline evidence must be titled by its issue')
    assert.ok(panelA11y.focusables >= 2, 'inline evidence must expose focusable content controls')
    checks.push(await assertTouchTargets(page, 'evidence-inline/390'))
    await assertNoPageOverflow(page, 'evidence-inline/390')
    await shot(page, '390-evidence-inline.png', { scenario: 'evidence', state: 'inline evidence below the issue list' })
    await panel.getByRole('button', { name: '返回刚才的操作', exact: true }).click()
    await page.waitForTimeout(150)
    assert.equal(await page.evaluate(() => document.activeElement === document.querySelector('.m-issue-list .evidence-button')), true, 'returning must restore focus to the triggering issue row')
    const restore = await page.evaluate(() => Math.round(scrollY))
    assert.ok(Math.abs(restore - before) <= 2, `returning must restore the report scroll position (before ${before}, after ${restore})`)
    assert.equal(await page.evaluate(() => document.querySelectorAll('.m-issue-row.report-row-current').length), 1, 'returning keeps exactly one current row')
    // No modal exists, so Escape must not dismiss the reading region.
    await page.keyboard.press('Escape')
    await page.waitForTimeout(100)
    assert.equal(await page.locator('#evidence-panel').count(), 1, 'Escape must not dismiss the inline evidence')
    await hardwareBack(page)
    await waitTitle(page, '扫描与对照进度')
    checks.push('inline evidence: section below the list, focus in and back to trigger, exact scroll restore, no dialog/overlay, hardware back steps')

    // ---- in-app back arrow: report -> progress ----------------------------
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告')
    await page.getByRole('button', { name: '返回上一步' }).click()
    await waitTitle(page, '扫描与对照进度')
    assert.equal(await focusedTitle(page), true, 'the in-app back arrow must focus the page title')
    checks.push('in-app back arrow: report -> progress with title focus')

    // ---- 320x568 ----------------------------------------------------------
    await page.setViewportSize({ width: 320, height: 568 })
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.getByRole('button', { name: '更换材料', exact: true }).click()
    await waitTitle(page, 'APK 与政策材料')
    await page.evaluate(() => window.scrollTo(0, 0))
    await assertNoPageOverflow(page, 'import/320')
    await shot(page, '320-import.png', { scenario: 'import', state: '320px narrowest boundary with selected material' })
    await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
    await waitTitle(page, '核对政策声明')
    const rail320 = await page.evaluate(() => {
      const buttons = [...document.querySelectorAll('.m-steps button')]
      return { rows: new Set(buttons.map(button => Math.round(button.getBoundingClientRect().top))).size, scroll: document.documentElement.scrollWidth }
    })
    assert.equal(rail320.rows, 1, 'the step rail must stay one row at 320px')
    await assertNoPageOverflow(page, 'candidates/320')
    await shot(page, '320-candidates.png', { scenario: 'candidates', state: '320px segmented control and list rows' })
    await page.getByRole('button', { name: '扫描与对照进度', exact: true }).click()
    await waitTitle(page, '扫描与对照进度')
    await assertNoPageOverflow(page, 'progress/320')
    await shot(page, '320-progress.png', { scenario: 'progress', state: '320px timeline' })
    await page.getByRole('button', { name: '对照报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告')
    await assertNoPageOverflow(page, 'report/320')
    await shot(page, '320-report.png', { scenario: 'report', state: '320px report cards' })
    checks.push('320x568: one-row rail + import/candidates/progress/report without horizontal overflow')

    // ---- 768x1024 --------------------------------------------------------
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.getByRole('button', { name: 'APK 与政策材料', exact: true }).click()
    await waitTitle(page, 'APK 与政策材料')
    await page.evaluate(() => window.scrollTo(0, 0))
    await assertNoPageOverflow(page, 'import/768')
    await shot(page, '768-import.png', { scenario: 'import', state: '768px tablet in the mobile shell' })
    await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
    await waitTitle(page, '核对政策声明')
    const segmented768 = await page.evaluate(() => Boolean(document.querySelector('.mobile-panel-tabs')?.getClientRects().length))
    assert.equal(segmented768, true, 'the segmented control must stay visible on a 768px touch tablet')
    await assertNoPageOverflow(page, 'candidates/768')
    await shot(page, '768-candidates.png', { scenario: 'candidates', state: '768px segmented control' })
    await page.getByRole('button', { name: '对照报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告')
    await assertNoPageOverflow(page, 'report/768')
    await shot(page, '768-report.png', { scenario: 'report', state: '768px report' })
    checks.push('768x1024: shell rails stay one row, segmented control stays active, no page overflow')

    // ---- 844x390 landscape ----------------------------------------------
    await page.setViewportSize({ width: 844, height: 390 })
    await page.getByRole('button', { name: 'APK 与政策材料', exact: true }).click()
    await waitTitle(page, 'APK 与政策材料')
    await page.evaluate(() => window.scrollTo(0, 0))
    await assertNoPageOverflow(page, 'import/844x390')
    const landscape = await page.evaluate(() => {
      const actionbar = document.querySelector('.m-actionbar').getBoundingClientRect()
      return { actionbarVisible: actionbar.top >= 0 && actionbar.bottom <= innerHeight + 1, actionbarHeight: Math.round(actionbar.height) }
    })
    assert.equal(landscape.actionbarVisible, true, 'the action bar must stay reachable in landscape')
    assert.ok(landscape.actionbarHeight >= 64, `landscape action bar must keep its 64px minimum (got ${landscape.actionbarHeight})`)
    await shot(page, '844x390-import.png', { scenario: 'import', state: 'phone landscape' })
    await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
    await waitTitle(page, '核对政策声明')
    await assertNoPageOverflow(page, 'candidates/844x390')
    await shot(page, '844x390-candidates.png', { scenario: 'candidates', state: 'phone landscape segmented control' })
    await page.getByRole('button', { name: '对照报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告')
    await assertNoPageOverflow(page, 'report/844x390')
    await shot(page, '844x390-report.png', { scenario: 'report', state: 'phone landscape report' })
    checks.push('844x390 landscape: safe-area shell, one-row rail, fixed 64px action bar, no horizontal overflow')

    // ---- 200% root font --------------------------------------------------
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
    await page.getByRole('button', { name: 'APK 与政策材料', exact: true }).click()
    await waitTitle(page, 'APK 与政策材料')
    await page.evaluate(() => window.scrollTo(0, 0))
    const largeText = await page.evaluate(() => {
      const bar = document.querySelector('.m-actionbar')
      const main = document.querySelector('.m-main')
      return { bar: Math.round(bar.getBoundingClientRect().height), padding: Math.round(Number.parseFloat(getComputedStyle(main).paddingBottom)) }
    })
    assert.ok(largeText.bar > 64, `the action bar must grow with 200% text (got ${largeText.bar}px)`)
    assert.ok(largeText.padding >= largeText.bar + 16, `the content must reserve the grown action bar (padding ${largeText.padding}, bar ${largeText.bar})`)
    await assertNoPageOverflow(page, 'import/200%')
    await shot(page, '390-import-200.png', { scenario: 'import', state: '200% root font (system text scaling), selected material' })
    await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
    await waitTitle(page, '核对政策声明')
    await assertNoPageOverflow(page, 'candidates/200%')
    await shot(page, '390-candidates-200.png', { scenario: 'candidates', state: '200% root font segmented control and rows' })
    await page.getByRole('button', { name: '对照报告', exact: true }).click()
    await waitTitle(page, 'APP 隐私收集越权报告')
    await assertNoPageOverflow(page, 'report/200%')
    await shot(page, '390-report-200.png', { scenario: 'report', state: '200% root font report cards and evidence rows' })
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    checks.push('200% root font: import/candidates/report stay inside 390x844 without horizontal overflow')

    // ---- simulated soft keyboard ----------------------------------------
    await page.getByRole('button', { name: '核对政策声明', exact: true }).click()
    await waitTitle(page, '核对政策声明')
    await page.locator('#candidate-quote').focus()
    const keyboard = await page.evaluate(async () => {
      const viewport = window.visualViewport
      Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight - 460 })
      Object.defineProperty(viewport, 'scale', { configurable: true, get: () => 1 })
      viewport.dispatchEvent(new Event('resize'))
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      const root = document.documentElement
      const field = document.querySelector('#candidate-quote')
      const bar = document.querySelector('.m-actionbar')
      return {
        open: root.classList.contains('keyboard-open'),
        inset: Number.parseFloat(root.style.getPropertyValue('--keyboard-inset')),
        barBottom: Math.round(bar.getBoundingClientRect().bottom),
        viewportBottom: innerHeight - 460,
        focusRetained: document.activeElement === field,
        bodyPadding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
      }
    })
    assert.equal(keyboard.open, true, 'the keyboard fallback must mark html.keyboard-open')
    assert.ok(Math.abs(keyboard.inset - 460) <= 2, `expected --keyboard-inset ~460px, got ${keyboard.inset}`)
    assert.ok(Math.abs(keyboard.barBottom - keyboard.viewportBottom) <= 2, `the action bar must lift above the keyboard (bar ${keyboard.barBottom}, keyboard top ${keyboard.viewportBottom})`)
    assert.equal(keyboard.focusRetained, true, 'the focused field must keep focus while the keyboard is open')
    assert.ok(keyboard.bodyPadding >= 459, `the page must reserve the keyboard height (got ${keyboard.bodyPadding})`)
    const keyboardReach = await page.evaluate(() => {
      const field = document.querySelector('#candidate-quote')
      field.scrollIntoView({ block: 'center' })
      const rect = field.getBoundingClientRect()
      const bar = document.querySelector('.m-actionbar').getBoundingClientRect()
      return { top: Math.round(rect.top), bottom: Math.round(rect.bottom), keyboardTop: innerHeight - 460, barTop: Math.round(bar.top) }
    })
    assert.ok(keyboardReach.top >= 0 && keyboardReach.bottom <= keyboardReach.keyboardTop, `the focused field must scroll above the keyboard (${keyboardReach.top}..${keyboardReach.bottom}, keyboard top ${keyboardReach.keyboardTop})`)
    assert.ok(keyboardReach.barTop <= keyboardReach.keyboardTop + 1, `the action bar must stay above the keyboard (bar ${keyboardReach.barTop}, keyboard top ${keyboardReach.keyboardTop})`)
    await shot(page, '390-keyboard.png', { scenario: 'candidates', state: 'simulated 460px visual-viewport keyboard (not a real IME); focused field scrolled above it' })
    const keyboardReset = await page.evaluate(async () => {
      const viewport = window.visualViewport
      Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight })
      viewport.dispatchEvent(new Event('resize'))
      await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
      return {
        open: document.documentElement.classList.contains('keyboard-open'),
        barBottom: Math.round(document.querySelector('.m-actionbar').getBoundingClientRect().bottom),
      }
    })
    assert.equal(keyboardReset.open, false, 'closing the keyboard must clear html.keyboard-open')
    assert.ok(Math.abs(keyboardReset.barBottom - 844) <= 1, 'the action bar must return to the bottom edge')
    checks.push('soft keyboard: --keyboard-inset lifts the fixed action bar, keeps the focused field, releases on close')

    // ---- reduced motion --------------------------------------------------
    await page.emulateMedia({ reducedMotion: 'reduce' })
    const motion = await page.evaluate(() => ({
      media: matchMedia('(prefers-reduced-motion: reduce)').matches,
      buttonTransition: getComputedStyle(document.querySelector('.m-actionbar .ui-button')).transitionDuration,
      chevronTransition: getComputedStyle(document.querySelector('.candidate-chevron')).transitionDuration,
      scrollBehavior: getComputedStyle(document.documentElement).scrollBehavior,
    }))
    assert.equal(motion.media, true, 'the reduced-motion media query must apply')
    assert.ok(['0s', '0.01ms', '1e-05s'].includes(motion.buttonTransition), `buttons must not animate under reduced motion (got ${motion.buttonTransition})`)
    assert.ok(['0s', '0.01ms', '1e-05s'].includes(motion.chevronTransition), `chevrons must not animate under reduced motion (got ${motion.chevronTransition})`)
    assert.equal(motion.scrollBehavior, 'auto', 'reduced motion must not force smooth scrolling')
    await page.evaluate(() => window.scrollTo(0, 0))
    await shot(page, '390-reduced-motion.png', { scenario: 'candidates', state: 'prefers-reduced-motion: reduce' })
    await page.emulateMedia({ reducedMotion: 'no-preference' })
    checks.push('reduced motion: transitions/keyframes disabled, scroll stays instant')

    // ---- failure state (fresh page, same mocked bridge) -------------------
    const failContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    const failPage = await failContext.newPage()
    failPage.on('pageerror', error => errors.push('failure-page: ' + error.message))
    await failPage.addInitScript(bridge, { ...bridgeFixtures, failJob: true })
    await failPage.goto(origin)
    await selectAndPrepare(failPage)
    await failPage.getByRole('button', { name: '保存并分析', exact: true }).click()
    await waitTitle(failPage, '扫描与对照进度', 12000)
    // The first automatic poll is 10s after start; the mocked bridge reports the
    // failure on that poll. Wait for the real poll instead of a static banner.
    await failPage.getByText('本次分析未完成', { exact: false }).first().waitFor({ timeout: 20000 })
    const failure = await failPage.evaluate(() => ({
      alert: Boolean(document.querySelector('.m-status-card [role="alert"]')),
      retry: [...document.querySelectorAll('.m-actionbar .ui-button')].some(button => button.textContent.includes('重新分析')),
      report: [...document.querySelectorAll('.m-actionbar .ui-button')].every(button => !button.textContent.includes('查看报告')),
    }))
    assert.equal(failure.alert, true, 'the failed progress state must expose role=alert')
    assert.equal(failure.retry, true, 'a terminal failure must offer 重新分析')
    assert.equal(failure.report, true, 'a failed job must not offer 查看报告')
    await assertNoPageOverflow(failPage, 'progress/failed/390')
    await shot(failPage, '390-progress-failed.png', { scenario: 'progress/failed', state: 'mock job FAILED: alert + retry action' })
    await failContext.close()
    checks.push('failure: SIMULATED job failure stays on progress with role=alert, no report action, retry offered')

    // ---- static platform assertions --------------------------------------
    const mobileCss = fs.readFileSync(path.join(root, 'apps/web/src/mobile/mobile.css'), 'utf8')
    for (const fragment of ['100dvh', 'env(safe-area-inset-top', 'env(safe-area-inset-bottom', 'var(--keyboard-inset', 'overscroll-behavior', '-webkit-tap-highlight-color', 'touch-action: manipulation', '@media (hover: hover) and (pointer: fine)', 'var(--m-touch', 'prefers-reduced-motion']) {
      assert.ok(mobileCss.includes(fragment), `mobile.css is missing ${fragment}`)
    }
    assert.ok(!/transition\s*:\s*all/.test(mobileCss), 'mobile.css must not use transition: all')
    assert.doesNotMatch(mobileCss, /user-scalable\s*=\s*no/, 'mobile.css must not disable zoom')
    const mobileApp = fs.readFileSync(path.join(root, 'apps/web/src/mobile/MobileApp.vue'), 'utf8')
    assert.match(mobileApp, /m-busy-notice"><span role="status">/, 'busy text must sit in a text-only status span')
    assert.doesNotMatch(mobileApp, /role="status">[^<]*<UiButton/, 'a stop button must not be nested in a live region')
    const uiSheet = fs.readFileSync(path.join(root, 'apps/web/src/components/UiSheet.vue'), 'utf8')
assert.match(uiSheet, /var\(--(m|ui)-scrim\)/, 'the remaining settings sheet must keep the shared scrim token')
const evidencePanel = fs.readFileSync(path.join(root, 'apps/web/src/components/EvidencePanel.vue'), 'utf8')
    assert.doesNotMatch(evidencePanel, /aria-live/, 'the evidence panel must not be a live region containing controls')
    checks.push('mobile.css: 100dvh, safe-area, keyboard inset, overscroll/tap/16px/hover gating, no transition:all')

    // ---- ledger + artefact record ----------------------------------------
    const ledger = await page.evaluate(() => globalThis.mobileCalls)
    const bridgeMethods = new Set(ledger.map(call => call.method))
    for (const method of ['upload_selected', 'workflow', 'model_status']) assert.ok(bridgeMethods.has(method), `the mobile flow must go through the mocked native bridge (missing ${method})`)
    assert.deepEqual(api, [], 'the Tauri shell must not call browser /api endpoints')
    assert.deepEqual(errors, [])
    const walkthrough = {
      result: 'PASS',
      issue: 144,
      round: 2,
      source_sha: sourceSha,
      captured_at: capturedAt,
      platform: 'Chromium headless browser simulation, 390x844/320x568/768x1024/844x390, deviceScaleFactor 1',
      scope: 'production Vue mobile shell + mocked native bridge + deterministic fixtures; no APK scan, model, Docker, Android device or real IME execution',
      checks,
      captions,
      ledger_summary: { calls: ledger.length, methods: [...bridgeMethods].sort() },
      browser_api_requests: api,
      page_errors: errors,
      device_items: 'NOT_RUN: real Android WebView/APK, real soft keyboard IME, display cutout safe-area, system font scaling/pinch zoom, TalkBack, Tauri APK build — no adb/emulator/SDK on this host',
    }
    fs.writeFileSync(path.join(evidenceDir, 'mobile-round2-walkthrough.json'), JSON.stringify(walkthrough, null, 2) + '\n')

    console.log('Issue #144 round-2 mobile shell passed (Chromium simulation, mocked native bridge):')
    for (const check of checks) console.log('  - ' + check)
    console.log(`\n${captions.length} screenshots + walkthrough written to tmp/issue144-round2/evidence/ (the historical #144 record under docs/acceptance/issue144 is unchanged)`)
    console.log(`source SHA ${sourceSha}; Android device items NOT_RUN.`)
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
