// Development walkthrough: real production Vue, mocked native bridge; no APK/model execution.
// Issue #144 adds the narrow-width, large-text, soft-keyboard, safe-area, touch-target and
// evidence-preview checks on the same page; device-only items remain NOT_RUN in the acceptance record.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const vm = require('node:vm')
const net = require('node:net')
const { spawn } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')
const root = path.resolve(__dirname, '..'), output = path.join(root, 'tmp/issue72-native')
fs.mkdirSync(output, { recursive: true })
const source = fs.readFileSync(path.join(__dirname, 'verify-frontend-flow.cjs'), 'utf8')
const fixtureContext = {}
vm.runInNewContext(source.slice(source.indexOf('const policySentence'), source.indexOf('const fixtureRoutes')) + '\nthis.fixtures = { reportFixture, taxonomyFixture, policySentence }', fixtureContext)
const fixtures = JSON.parse(JSON.stringify(fixtureContext.fixtures))
const longTitle = 'A'.repeat(120)
const longUrl = 'https://policy.example/' + 'a'.repeat(400)
const longPolicy = ('长政策正文保留原句、条件与不确定性，不因窄屏而截断。'.repeat(120)) + '\n' + longUrl

// Elements inside a local scroll container or the visually hidden table header may
// legitimately extend past the viewport; page-level overflow is what #144 forbids.
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
    if (element.closest('.report-table thead, .comparison-table thead, .sr-only, dialog')) continue
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
  assert.ok(measured.scrollWidth <= measured.innerWidth, `${label}: document scrollWidth ${measured.scrollWidth} exceeds ${measured.innerWidth}`)
  assert.ok(measured.bodyScrollWidth <= measured.innerWidth, `${label}: body scrollWidth ${measured.bodyScrollWidth} exceeds ${measured.innerWidth}`)
  assert.deepEqual(measured.offenders, [], `${label}: elements protrude past the viewport`)
}
// Below 560px the comparison/report tables are cards, so their scroll wrapper must
// not scroll at all. Wider layouts may scroll the table locally (never the page).
async function assertNoCardScroll(page, label) {
  const measured = await page.evaluate(() => {
    const box = document.querySelector('.table-scroll')
    return box ? { present: true, overflow: box.scrollWidth - box.clientWidth } : { present: false, overflow: 0 }
  })
  assert.equal(measured.present, true, `${label}: the report table scroll wrapper must exist`)
  assert.ok(measured.overflow <= 1, `${label}: the report table must not scroll horizontally in card layout (overflow ${measured.overflow}px)`)
}
async function assertTouchTargets(page, label) {
  const measured = await page.evaluate(() => {
    const short = []
    let total = 0
    for (const element of document.querySelectorAll('button, [role="tab"], summary, label.text-upload')) {
      if (!element.getClientRects().length) continue
      if (getComputedStyle(element).display === 'inline') continue
      const rect = element.getBoundingClientRect()
      if (!rect.width || !rect.height) continue
      total += 1
      if (rect.width < 43.5 || rect.height < 43.5) {
        short.push((element.id || element.textContent || element.tagName).trim().slice(0, 24) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height))
      }
    }
    return { total, short }
  })
  assert.ok(measured.total >= 8, `${label}: expected a representative set of touch targets, got ${measured.total}`)
  assert.deepEqual(measured.short, [], `${label}: touch targets under 44x44 CSS px`)
  return `${label}: ${measured.total} controls >= 44x44`
}
async function assertCardRowsContained(page, label) {
  const measured = await page.evaluate(() => {
    const rows = Array.from(document.querySelectorAll('.report-table tbody tr'))
    return {
      rows: rows.length,
      offenders: rows.flatMap(row => {
        const rowRect = row.getBoundingClientRect()
        return Array.from(row.children).filter(cell => {
          const rect = cell.getBoundingClientRect()
          return rect.right > rowRect.right + 1 || rect.width > rowRect.width + 1
        }).map(cell => (cell.getAttribute('data-label') || cell.tagName) + ':' + Math.round(cell.getBoundingClientRect().width))
      }),
    }
  })
  assert.ok(measured.rows > 0, `${label}: expected report cards to render`)
  assert.deepEqual(measured.offenders, [], `${label}: card cells must stay inside their row`)
}
// The visual viewport shrinks while the keyboard covers the page on browsers that
// do not resize the layout viewport; the fallback must publish the hidden height so
// bottom actions keep a scroll path. This simulates the measurement, not a real IME.
async function simulateKeyboard(page, label) {
  await page.locator('#candidate-quote').focus()
  const state = await page.evaluate(async () => {
    const viewport = window.visualViewport
    Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight - 460 })
    Object.defineProperty(viewport, 'scale', { configurable: true, get: () => 1 })
    viewport.dispatchEvent(new Event('resize'))
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    const root = document.documentElement
    const save = document.querySelector('#candidate-quote')
    return {
      open: root.classList.contains('keyboard-open'),
      inset: Number.parseFloat(root.style.getPropertyValue('--keyboard-inset')),
      bodyPadding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
      scrollPadding: Number.parseFloat(getComputedStyle(root).scrollPaddingBottom),
      focusRetained: document.activeElement === save,
    }
  })
  assert.equal(state.open, true, `${label}: the keyboard fallback must mark html.keyboard-open`)
  assert.equal(state.focusRetained, true, `${label}: the focused field must stay focused while the keyboard is open`)
  assert.ok(Math.abs(state.inset - 460) <= 2, `${label}: expected --keyboard-inset ~460px, got ${state.inset}`)
  assert.ok(state.bodyPadding >= 459, `${label}: body must reserve the keyboard height (got ${state.bodyPadding}px)`)
  assert.ok(state.scrollPadding >= 475, `${label}: scroll-padding-bottom must include the keyboard height (got ${state.scrollPadding}px)`)
  // A tap on a bottom action blurs the field before the keyboard animates away;
  // the reservation must survive that focus change or the target shifts.
  const blurred = await page.evaluate(async () => {
    document.activeElement?.blur()
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return {
      open: document.documentElement.classList.contains('keyboard-open'),
      padding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
    }
  })
  assert.equal(blurred.open, true, `${label}: moving focus to a bottom action must keep the reservation until the viewport restores`)
  assert.ok(blurred.padding >= 459, `${label}: the reservation was dropped too early (got ${blurred.padding}px)`)
  // Pinch-zoom also shrinks the visual viewport; it must not be read as a keyboard.
  const zoomed = await page.evaluate(async () => {
    const viewport = window.visualViewport
    Object.defineProperty(viewport, 'scale', { configurable: true, get: () => 2 })
    viewport.dispatchEvent(new Event('resize'))
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return {
      open: document.documentElement.classList.contains('keyboard-open'),
      padding: Number.parseFloat(getComputedStyle(document.body).paddingBottom),
    }
  })
  assert.equal(zoomed.open, false, `${label}: pinch zoom must not be treated as a keyboard`)
  assert.ok(zoomed.padding <= 1, `${label}: pinch zoom must not reserve keyboard space (got ${zoomed.padding}px)`)
  const reset = await page.evaluate(async () => {
    const viewport = window.visualViewport
    Object.defineProperty(viewport, 'scale', { configurable: true, get: () => 1 })
    Object.defineProperty(viewport, 'height', { configurable: true, get: () => innerHeight })
    viewport.dispatchEvent(new Event('resize'))
    await new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve)))
    return {
      open: document.documentElement.classList.contains('keyboard-open'),
      padding: parseFloat(getComputedStyle(document.body).paddingBottom),
    }
  })
  assert.equal(reset.open, false, `${label}: closing the keyboard must clear html.keyboard-open`)
  assert.ok(reset.padding <= 1, `${label}: closing the keyboard must release the reserved space`)
  // `interactive-widget=resizes-content` shrinks the layout viewport instead: the
  // save action must remain reachable in the reduced viewport.
  await page.setViewportSize({ width: 390, height: 380 })
  const reachable = await page.evaluate(() => {
    const save = document.querySelector('.candidate-editor .ui-button.primary')
    if (!save) return null
    save.scrollIntoView({ block: 'center' })
    const rect = save.getBoundingClientRect()
    return { top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: innerHeight }
  })
  assert.ok(reachable && reachable.top >= 0 && reachable.bottom <= reachable.height + 1, `${label}: the save action must stay reachable when the layout viewport shrinks (${JSON.stringify(reachable)})`)
  await page.setViewportSize({ width: 390, height: 844 })
  return `${label}: simulated keyboard reserves 460px, survives focus move, ignores pinch zoom, releases, save action reachable in a resized viewport`
}
async function verifyPreview(page, label) {
  const checks = []
  for (let round = 1; round <= 2; round += 1) {
    const trigger = page.locator('.evidence-button').first()
    await trigger.scrollIntoViewIfNeeded()
    const before = await page.evaluate(() => Math.round(scrollY))
    await trigger.click()
    await page.waitForFunction(() => document.activeElement?.id === 'evidence-panel', null, { timeout: 5000 })
    if (round === 1) {
      await page.screenshot({ path: path.join(output, 'report-preview-390.png'), fullPage: false })
      checks.push(await assertTouchTargets(page, `${label}/preview-open`))
    }
    await page.getByRole('button', { name: '收起', exact: true }).click()
    await page.waitForFunction(() => document.activeElement === document.querySelector('.report-table tbody tr .evidence-button'), null, { timeout: 5000 })
    await page.waitForFunction(target => Math.abs(Math.round(scrollY) - target) <= 2, before, { timeout: 5000 })
    const band = await page.evaluate(() => {
      const button = document.querySelector('.report-table tbody tr .evidence-button')
      const rect = button.getBoundingClientRect()
      return { top: Math.round(rect.top), bottom: Math.round(rect.bottom), height: innerHeight }
    })
    assert.ok(band.top >= 0 && band.bottom <= band.height, `${label} round ${round}: the triggering row must be back in the viewport (${JSON.stringify(band)})`)
    assert.equal(await page.locator('#evidence-panel').count(), 0, `${label} round ${round}: the evidence panel must close`)
    assert.equal(await trigger.getAttribute('aria-expanded'), 'false', `${label} round ${round}: aria-expanded must follow the preview state`)
  }
  checks.push(`${label}: opening/closing twice restores focus and the exact scroll position`)
  return checks
}
async function verifyCoarsePointer(browser, origin, bridge, fixtures) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  try {
    const page = await context.newPage()
    await page.addInitScript(bridge, fixtures)
    await page.goto(origin)
    const state = await page.evaluate(() => ({
      hoverNone: matchMedia('(hover: none)').matches,
      coarse: matchMedia('(pointer: coarse)').matches,
      viewport: document.querySelector('meta[name="viewport"]')?.getAttribute('content') || '',
    }))
    assert.equal(state.hoverNone, true, 'coarse-pointer context must report (hover: none)')
    assert.equal(state.coarse, true, 'coarse-pointer context must report (pointer: coarse)')
    assert.match(state.viewport, /viewport-fit=cover/, 'viewport meta must opt into safe-area insets')
    assert.match(state.viewport, /interactive-widget=resizes-content/, 'viewport meta must let the soft keyboard resize the layout viewport')
    const restore = page.getByRole('button', { name: '恢复当前实例材料', exact: true })
    const restingTouch = await restore.evaluate(element => getComputedStyle(element).backgroundColor)
    await restore.tap()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 5000 })
    await page.waitForTimeout(250)
    // Open the personal-model details so the field assertion reads a visible
    // text input, not the hidden content of a closed <details>.
    await page.getByText('使用手机上的个人模型', { exact: true }).tap()
    const after = await page.evaluate(() => {
      const field = document.querySelector('.mobile-field input')
      if (!field || !field.getClientRects().length) return { visible: false, fieldFontSize: 0, fieldHeight: 0 }
      const style = getComputedStyle(field)
      return { visible: true, fieldFontSize: Number.parseFloat(style.fontSize), fieldHeight: Math.round(field.getBoundingClientRect().height) }
    })
    assert.equal(after.visible, true, 'coarse pointer: the model field must be visible for the touch assertion')
    assert.ok(after.fieldFontSize >= 16, `focus must not trigger iOS zoom: field font-size ${after.fieldFontSize}px < 16px`)
    assert.ok(after.fieldHeight >= 44, `coarse pointer: field hit area must be >= 44px (got ${after.fieldHeight}px)`)
    const afterTap = await restore.evaluate(element => getComputedStyle(element).backgroundColor)
    assert.equal(afterTap, restingTouch, `touch must not leave a hover highlight behind (was ${restingTouch}, now ${afterTap})`)
    // The capability branch keeps 44px beyond the 560px breakpoint; the same
    // layouts must also stay free of page-level overflow with the larger controls.
    await page.setViewportSize({ width: 768, height: 1024 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'coarse/768')
    await page.setViewportSize({ width: 844, height: 390 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'coarse/844x390')
    const landscape = await page.evaluate(() => {
      const short = []
      let total = 0
      for (const element of document.querySelectorAll('button, [role="tab"], summary, label.text-upload, input, select, textarea')) {
        if (!element.getClientRects().length || getComputedStyle(element).display === 'inline') continue
        const rect = element.getBoundingClientRect()
        if (!rect.width || !rect.height) continue
        total += 1
        if (rect.width < 43.5 || rect.height < 43.5) short.push((element.textContent || element.tagName).trim().slice(0, 20) + ' ' + Math.round(rect.width) + 'x' + Math.round(rect.height))
      }
      return { total, short }
    })
    assert.ok(landscape.total >= 4, `coarse landscape: expected touch controls, got ${landscape.total}`)
    assert.deepEqual(landscape.short, [], 'coarse landscape: touch targets under 44x44 CSS px')
    return ['coarse pointer: 16px/44px visible fields, no sticky hover, safe-area viewport meta, tap works', `coarse pointer: ${landscape.total} controls >= 44x44 in 768/844 layouts with no page overflow`]
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
    const bridge = ({ reportFixture, taxonomyFixture, policySentence, policyText, policyTitle, policyUrl }) => {
      globalThis.isTauri = true
      const context = { origin: 'https://analysis.example/', draft: 'a'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
      const job = { ...reportFixture.job, id: 'b'.repeat(32), state: 'QUEUED' }
      const draft = { id: context.draft, name: 'com.example.' + 'b'.repeat(160), uploaded: true, revision: 1, apk_sha256: 'c'.repeat(128), sources: [
        { id: 'policy', title: policyTitle, url: policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: policySentence, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
        { id: 'long', title: '大段政策来源', url: policyUrl, source_type: 'OFFICIAL_WEB_POLICY', text: policyText, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' },
      ], candidates: [], jobs: [] }
      const ledger = globalThis.mobileCalls = []
      let configured = false, jobReads = 0
      globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
        const method = command.split('|')[1]; ledger.push({ method, args })
        if (method === 'model_status') return { configured, endpoint: configured ? 'https://model.example/v1/chat/completions' : null }
        if (method === 'configure_model') { configured = true; return { configured, endpoint: 'https://model.example/v1/chat/completions' } }
        if (method === 'upload_selected') return context
        if (method === 'refresh_upload') { jobReads = 0; job.state = 'STATIC_ANALYSIS'; return context }
        if (method === 'cancel') return
        if (method === 'collect_policy') return { text: JSON.stringify({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: { id: 'policy-collected', title: '受控政策', source_type: 'OFFICIAL_WEB_POLICY', text: policySentence } }] }) }
        if (method !== 'workflow') throw new Error('Unexpected native method ' + method)
        const action = args.action, input = JSON.parse(args.payload)
        let data = draft
        if (action === 'taxonomy') data = taxonomyFixture
        else if (action === 'import') { draft.sources.push(...input.results.map(item => ({ ...item.source, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' }))); draft.revision++ }
        else if (action === 'extract') { draft.candidates = [{ id: 'candidate', source_id: 'policy', excerpt: policySentence, data_type: 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }]; draft.revision++ }
        else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision++ }
        else if (action === 'start') {
          draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: '2026-10-20T00:00:00Z' }] })
          draft.revision++
          throw new Error('Simulated response loss after accepted start')
        }
        else if (action === 'job') { job.state = ++jobReads === 1 ? 'STATIC_ANALYSIS' : 'SUCCEEDED'; data = job }
        else if (action === 'report') { data = { ...reportFixture, job, demo: false, result: { ...reportFixture.result, job_id: job.id } } }
        else if (action !== 'read') throw new Error('Unexpected workflow action ' + action)
        return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
      } }
    }
    const bridgeFixtures = { ...fixtures, policyTitle: longTitle, policyText: longPolicy, policyUrl: longUrl }
    await page.addInitScript(bridge, bridgeFixtures)
    await page.goto(origin)
    await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor()
    for (const width of [320, 390, 768, 1440]) {
      await page.setViewportSize({ width, height: 900 }); await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, 'import')
      await page.screenshot({ path: path.join(output, `import-${width}.png`), fullPage: true })
    }
    checks.push('import: no page overflow at 320/390/768/1440 with a 120-char source title, 400-char URL and 128-char hash')
    // Desktop hover is a fine-pointer behavior and must survive the capability branch.
    await page.setViewportSize({ width: 390, height: 844 })
    const restoreButton = page.getByRole('button', { name: '恢复当前实例材料', exact: true })
    const resting = await restoreButton.evaluate(element => getComputedStyle(element).backgroundColor)
    await restoreButton.hover()
    await page.waitForTimeout(250)
    const hovered = await restoreButton.evaluate(element => getComputedStyle(element).backgroundColor)
    assert.notEqual(resting, hovered, 'fine pointers must keep hover feedback')
    await page.mouse.move(0, 0)
    checks.push('pointer: fine hover feedback preserved')
    await page.getByText('使用手机上的个人模型', { exact: true }).click()
    await page.getByRole('button', { name: '设置模型配置', exact: true }).click()
    await page.getByLabel('模型名称', { exact: true }).fill('compatible-chat')
    await page.getByLabel('应用名称或包名', { exact: true }).fill('com.example.mobile.ok')
    // The model fields are the place where a default input width used to widen the
    // grid at 200% font size; keep the same-page large-text check here.
    checks.push(await assertTouchTargets(page, 'import'))
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `import/200%/${width}`)
      await page.screenshot({ path: path.join(output, `import-200-${width}.png`), fullPage: true })
      await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    }
    checks.push('import: 200% root font keeps 320/390px free of page overflow with the model fields open')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '使用个人模型收集一次', exact: true }).click()
    await page.locator('.policy-assist > summary').click()
    await page.getByRole('button', { name: '检查回填内容', exact: true }).click()
    await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
    await page.getByText('受控政策', { exact: true }).first().waitFor()
    await page.getByRole('button', { name: '自动准备政策并继续', exact: true }).click()
    await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor()
    // The long source title must wrap in the source tab strip instead of widening the page.
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    assert.equal(await page.locator('.source-tabs button').count(), 3, 'expected the two mocked sources plus the collected one')
    await assertNoPageOverflow(page, 'candidates')
    await page.locator('.source-tabs button').nth(1).click()
    await page.getByRole('tab', { name: '政策原文', exact: true }).click()
    await page.getByText('长政策正文保留原句', { exact: false }).first().waitFor()
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 }); await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, 'candidates/long policy')
      await page.screenshot({ path: path.join(output, `candidates-long-${width}.png`), fullPage: true })
    }
    await page.locator('.source-tabs button').first().click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.getByRole('tab', { name: '候选声明', exact: false }).click()
    checks.push('candidates: 120-char source title, 400-char URL and a 4k-char policy stay inside 320/390/768px')
    // Phone landscape: same page, wider than the mobile breakpoint.
    await page.setViewportSize({ width: 844, height: 390 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'candidates/landscape')
    await page.screenshot({ path: path.join(output, 'candidates-landscape-844.png'), fullPage: true })
    checks.push('candidates: landscape 844x390 keeps the mobile flow free of page overflow')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(output, 'candidates-390.png'), fullPage: true })
    // 200% text zoom (system font size) on the same page.
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `candidates/200%/${width}`)
      await page.screenshot({ path: path.join(output, `candidates-200-${width}.png`), fullPage: true })
      await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    }
    checks.push('candidates: 200% root font keeps 320/390px free of page overflow')
    checks.push(await assertTouchTargets(page, 'candidates'))
    checks.push(await simulateKeyboard(page, 'candidates'))
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: /开始.*分析/ }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 12000 })
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.getByRole('heading', { name: '手机端验收示例', exact: true }).waitFor()
    for (const width of [320, 390, 768]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `report/${width}`)
      if (width <= 560) await assertNoCardScroll(page, `report/${width}`)
      await page.screenshot({ path: path.join(output, `report-${width}.png`), fullPage: true })
    }
    checks.push('report: no page overflow at 320/390/768 and the card layout does not scroll sideways')
    await page.setViewportSize({ width: 844, height: 390 })
    await page.evaluate(() => document.fonts.ready)
    await assertNoPageOverflow(page, 'report/landscape')
    await page.screenshot({ path: path.join(output, 'report-landscape-844.png'), fullPage: true })
    checks.push('report: landscape 844x390 keeps the evidence reachable without page overflow')
    await page.setViewportSize({ width: 390, height: 844 })
    for (const width of [320, 390]) {
      await page.setViewportSize({ width, height: 844 })
      await page.evaluate(() => { document.documentElement.style.fontSize = '32px' })
      await page.evaluate(() => document.fonts.ready)
      await assertNoPageOverflow(page, `report/200%/${width}`)
      await assertNoCardScroll(page, `report/200%/${width}`)
      await assertCardRowsContained(page, `report/200%/${width}`)
      await page.screenshot({ path: path.join(output, `report-200-${width}.png`), fullPage: true })
      await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    checks.push('report: 200% root font keeps cards inside 320px and 390px without sideways scroll')
    checks.push(...await verifyPreview(page, 'report'))
    await page.getByRole('button', { name: '恢复当前实例材料', exact: true }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor()
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.getByRole('heading', { name: '手机端验收示例', exact: true }).waitFor()
    const ledger = await page.evaluate(() => globalThis.mobileCalls)
    const save = ledger.find(call => call.method === 'workflow' && call.args.action === 'candidates')
    assert.equal(JSON.parse(save.args.payload).candidates[0].checked, false)
    assert.equal(ledger.filter(call => call.method === 'workflow' && call.args.action === 'start').length, 1, 'lost start response and running-job restore must not submit another analysis')
    assert(ledger.some(call => call.method === 'workflow' && call.args.action === 'report'))
    assert.deepEqual(api, [], 'native snapshot report must not use browser HTTP credentials')
    assert.deepEqual(errors, [])
    checks.push(...await verifyCoarsePointer(browser, origin, bridge, bridgeFixtures))
    fs.writeFileSync(path.join(output, 'walkthrough.json'), JSON.stringify({
      result: 'PASS',
      scope: 'production Vue with mocked native bridge; no APK scan, paid model, Android UI or real keyboard execution',
      viewports: [320, 390, 768, 844, 1440],
      landscape_viewport: [844, 390],
      keyboard_viewport: [390, 380],
      large_text: '200% root font size',
      checks,
      ledger,
      browser_api_requests: api,
      page_errors: errors,
      device_items: 'NOT_RUN: real Android WebView IME, display cutout safe-area and on-device touch target geometry need a connected device/emulator',
    }, null, 2))
    console.log('Mobile development walkthrough passed: accepted start response lost → read/recover existing job → automatic progress → evidence report → running-job restore with automatic progress; exactly one start, zero browser API requests.')
    console.log('Issue #144 mobile checks:', checks.length, 'assertions —', checks.join(' | '))
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
