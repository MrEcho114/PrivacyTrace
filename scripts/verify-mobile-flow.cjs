#!/usr/bin/env node
/**
 * Issue #144 mobile regression harness (round 2 shell).
 *
 * Keeps the round-1 invariants that the new Android shell must not regress:
 * long unbroken text at 320/390/768, 200% root font, fine-pointer hover,
 * coarse-pointer fields, soft-keyboard reservation, evidence focus/scroll
 * restore, one analysis start despite a lost response, and no browser API.
 * The full round-2 shell/touch/back matrix lives in verify-frontend-round2.cjs.
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
      { id: 'long', title: '大段政策来源', url: options.policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: options.policyText, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
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
    const restore = page.getByRole('button', { name: '恢复当前实例材料', exact: true })
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
    await page.getByRole('button', { name: '设置模型配置', exact: true }).click()
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
    await page.getByRole('button', { name: '自动准备政策并继续', exact: true }).click()
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
