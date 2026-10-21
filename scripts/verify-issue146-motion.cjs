// Issue #146: motion calibration. Verifies the four behaviours this ticket
// actually changed, in a real browser, in both motion modes:
//   1. colour feedback has one rhythm, only touches colour properties, and the
//      pressed state wins over hover
//   2. hover feedback only exists for hover-capable pointers
//   3. drag highlight and evidence expansion do not move the content they sit in
//   4. prefers-reduced-motion drops displacement/spring motion and JS smooth scrolling
// Assertions read live computed styles and dispatched events. Durations are read
// back from the `--motion-*` tokens rather than pasted from the stylesheet, so a
// token change exercises the same contract the browser applies.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawn, execFileSync } = require('node:child_process')
const crypto = require('node:crypto')
const { stopChildren, spawnOptions } = require('./lib/process-control.cjs')

const output = path.resolve('tmp/issue146-motion')
const screenshots = path.join(output, 'screenshots')
const origin = process.env.PRIVACYTRACE_FRONTEND_URL || 'http://127.0.0.1:5184'

// Deterministic report shape follows apps/web/src/contracts.generated.ts; a drift
// shows up as a failed selector instead of a silently skipped assertion.
const job = {
  id: 'job-motion-146', sample_id: 'sample-motion-146', input_mode: 'APK', source_origin: 'REAL_SCAN',
  state: 'SUCCEEDED', ruleset_version: 'ruleset-motion-146', created_at: '2026-10-21T08:00:00Z',
  package_name: 'com.example.motion', version_code: 7, error: null,
}
const longPolicy = '我们收集位置信息用于附近门店推荐，并在设置中说明关闭方式。'.repeat(400)
const report = {
  sample: {
    name: '动效验收示例', package_name: 'com.example.motion', version_name: '1.0.0', version_code: 7,
    apk_sha256: 'a'.repeat(64), permissions: ['android.permission.ACCESS_FINE_LOCATION'], dex_entries: ['classes.dex'],
  },
  job,
  delivery_mode: 'PERSISTED_REPLAY',
  result: {
    job_id: job.id,
    ruleset_version: 'ruleset-motion-146',
    issues: [
      {
        id: 'issue-location', behavior_id: 'beh-location', data_type: 'LOCATION', status: 'EXACT_MATCH',
        evidence_status: 'STATIC_POTENTIAL', policy_document_ids: ['doc-web-1'], evidence_ids: ['ev-api-location'],
        explanation: '官网政策按具体类型声明了位置信息，但目的与时间范围没有写清。', scope: 'DATA_TYPE_DISCLOSURE', requires_review: true,
      },
      {
        id: 'issue-device', behavior_id: 'beh-device', data_type: 'DEVICE_ID', status: 'NOT_DECLARED',
        evidence_status: 'STATIC_POTENTIAL', policy_document_ids: [], evidence_ids: ['ev-api-device'],
        explanation: '政策快照中没有设备标识的对应条款；缺少全文复核时不能据此断言违规。', scope: 'DATA_TYPE_DISCLOSURE', requires_review: true,
      },
    ],
  },
  evidence: [
    {
      id: 'ev-api-location', kind: 'API', status: 'STATIC_POTENTIAL', source: 'classes.dex',
      locator: 'Lcom/example/Location;->request()V', excerpt: 'LocationManager.requestLocationUpdates(...)', document_id: null,
      api_call: { target_descriptor: 'android.location.LocationManager#requestLocationUpdates', rule_id: 'rule-location', ruleset_version: 'ruleset-motion-146', context: { receiver: 'UNKNOWN' } },
    },
    {
      id: 'ev-api-device', kind: 'API', status: 'STATIC_POTENTIAL', source: 'classes.dex',
      locator: 'Lcom/example/Device;->id()V', excerpt: 'Settings.Secure.getString(...)', document_id: null,
      api_call: { target_descriptor: 'android.provider.Settings$Secure#getString', rule_id: 'rule-device-id', ruleset_version: 'ruleset-motion-146', context: { receiver: 'UNKNOWN' } },
    },
  ],
  behaviors: [
    { id: 'beh-location', data_type: 'LOCATION', action: 'ACCESS', purpose: 'UNKNOWN', recipient: 'UNKNOWN', transfer: 'UNKNOWN', temporal_scope: 'UNKNOWN', evidence_ids: ['ev-api-location'] },
    { id: 'beh-device', data_type: 'DEVICE_ID', action: 'CAPABILITY', evidence_ids: ['ev-api-device'] },
  ],
  policy_documents: [{
    id: 'doc-web-1', source_type: 'OFFICIAL_WEB_POLICY', title: '动效验收示例政策', version: '2026-10',
    captured_at: '2026-10-21T07:00:00Z', artifact: { text: longPolicy, sha256: 'b'.repeat(64), normalization: 'NONE' },
    completeness: 'PARTIAL', extraction_status: 'PARTIAL', review_status: 'UNREVIEWED', attachments_status: 'NOT_CHECKED',
    applicability: { package_name: 'com.example.motion', version_codes: [7], regions: ['CN'], product_scope: null }, evidence_id: 'ev-doc-web-1',
  }],
  policy_claims: [],
  coverage: { status: 'PARTIAL', scope: 'DEX_ENTRIES', behavior_detection: 'LIMITED_RULE_BASED_STATIC', behavior_limitations: ['不覆盖反射与动态加载。'], limitations: ['未扫描 native 代码。'], scanned_dex: ['classes.dex'], failed_dex: [] },
  tools: { report_schema: 'motion-146', analysis_generated_at: '2026-10-21T08:01:00Z', ruleset_version: 'ruleset-motion-146' },
  reviews: [],
}
const taxonomy = { version: 'taxonomy-motion-146', data_types: [{ id: 'LOCATION', label: '位置信息', parent: null }, { id: 'DEVICE_ID', label: '设备标识', parent: null }] }

const checks = []
async function mockReports(page, ledger) {
  await page.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomy }))
  await page.route('**/api/v1/demo/report', route => route.fulfill({ json: { ...report, demo: true } }))
  await page.route('**/api/v1/jobs/*/report', route => { ledger.push(route.request().url()); return route.fulfill({ json: report }) })
  await page.route('**/api/v1/jobs', route => { ledger.push(route.request().url()); return route.fulfill({ json: { jobs: [job] } }) })
  await page.route('**/api/v1/jobs/*', route => route.fulfill({ json: job }))
  await page.route('**/api/v1/web/settings', route => route.fulfill({ json: { model: { enabled: false, api_base: '', model: '', key_configured: false } } }))
}

// Budget guard: any element that actually transitions must name its properties
// (never `all`) and stay inside the 300ms UI budget.
async function auditTransitions(page, label) {
  const violations = await page.evaluate(() => {
    const bad = []
    for (const element of document.querySelectorAll('*')) {
      const style = getComputedStyle(element)
      const durations = style.transitionDuration.split(',').map(value => parseFloat(value) || 0)
      if (Math.max(...durations) <= 0) continue
      const properties = style.transitionProperty.split(',').map(value => value.trim())
      const ms = Math.max(...durations) * 1000
      if (properties.includes('all')) bad.push({ selector: element.tagName + '.' + (element.className || ''), reason: 'transition: all', ms })
      if (ms > 300) bad.push({ selector: element.tagName + '.' + (element.className || ''), reason: 'over budget', ms })
    }
    return bad
  })
  assert.deepEqual(violations, [], label + ': every active transition must name its properties and stay under 300ms')
}

async function runWorkflowExample(page) {
  await page.getByRole('button', { name: '体验示例', exact: true }).first().click()
  await page.getByRole('button', { name: '检查候选', exact: true }).click()
  await page.getByRole('button', { name: '进入流程演示' }).click()
  for (let index = 0; index < 4; index++) await page.getByRole('button', { name: '进入下一阶段' }).click()
  await page.getByRole('button', { name: '完成当前阶段' }).click()
  await page.getByRole('button', { name: '查看报告', exact: true }).click()
  await page.getByRole('heading', { name: '分析报告', exact: true }).waitFor()
}

async function verifyPointerFeedback(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const ledger = []
  const page = await context.newPage()
  await mockReports(page, ledger)
  await page.goto(origin)
  await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor({ timeout: 15000 })
  await page.evaluate(() => document.fonts.ready)

  const gate = await page.evaluate(() => matchMedia('(hover: hover) and (pointer: fine)').matches)
  assert.equal(gate, true, 'desktop pointer must match the hover gate')
  checks.push('pointer: desktop reports (hover: hover) and (pointer: fine)')

  const button = page.getByRole('button', { name: '项目设置', exact: true })
  const base = await button.evaluate(element => getComputedStyle(element).backgroundColor)
  await button.hover()
  await page.waitForTimeout(250)
  const hovered = await button.evaluate(element => getComputedStyle(element).backgroundColor)
  assert.notEqual(hovered, base, 'a hover-capable pointer must still get hover feedback')
  const timing = await button.evaluate(element => {
    const style = getComputedStyle(element)
    const token = getComputedStyle(document.documentElement).getPropertyValue('--motion-color').trim()
    const toMs = value => value.endsWith('ms') ? parseFloat(value) : parseFloat(value) * 1000
    const durations = style.transitionDuration.split(',').map(value => toMs(value.trim()))
    return { property: style.transitionProperty, durations, tokenMs: toMs(token), rawToken: token }
  })
  assert.equal(timing.property, 'background-color, border-color', 'colour feedback animates colour properties only')
  assert.ok(timing.durations.every(ms => ms === timing.tokenMs), 'every colour transition must use the shared --motion-color token (got ' + JSON.stringify(timing.durations) + ' vs ' + timing.rawToken + ')')
  await page.screenshot({ path: path.join(screenshots, 'feedback-hover-1440.png') })
  checks.push('feedback: hover keeps the shared --motion-color colour fade; colour properties only')

  // The press offset has no transition, so the pressed state exists in the same
  // frame as pointerdown instead of easing in behind the colour change.
  const box = await button.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  const pressed = await button.evaluate(element => {
    const style = getComputedStyle(element)
    return { transform: style.transform, transition: style.transitionProperty }
  })
  await page.screenshot({ path: path.join(screenshots, 'feedback-pressed-1440.png') })
  await page.mouse.up()
  assert.equal(pressed.transform, 'matrix(1, 0, 0, 1, 0, 1)', 'press feedback must be visible immediately')
  assert.equal(/transform/.test(pressed.transition), false, 'the press offset must not be eased')
  // Releasing on the trigger opened the settings dialog; close it before the next probe.
  if (await page.getByRole('dialog').count()) await page.keyboard.press('Escape')
  await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
  checks.push('feedback: press offset is immediate and never transitions')

  // Drag highlight must not reflow the drop zone it highlights.
  const fileDrop = page.locator('.file-drop')
  const geometry = () => fileDrop.evaluate(element => {
    const rect = element.getBoundingClientRect()
    const inner = element.querySelector('strong').getBoundingClientRect()
    return { height: Math.round(rect.height), innerTop: Math.round(inner.top), border: getComputedStyle(element).borderTopWidth }
  })
  const before = await geometry()
  await fileDrop.evaluate(element => element.classList.add('drag-active'))
  const after = await geometry()
  await page.screenshot({ path: path.join(screenshots, 'drag-active-1440.png') })
  await fileDrop.evaluate(element => element.classList.remove('drag-active'))
  assert.equal(after.innerTop - before.innerTop, 0, 'the drag highlight must not move the label by a pixel')
  assert.equal(after.height - before.height, 0, 'the drag highlight must not change the drop zone height')
  assert.equal(after.border, before.border, 'the drag highlight must not widen the border')
  checks.push('drag: highlight keeps geometry (no border-width reflow)')

  await page.getByRole('button', { name: '项目设置', exact: true }).click()
  await page.getByRole('dialog').waitFor()
  const dialog = await page.getByRole('dialog').evaluate(element => {
    const style = getComputedStyle(element)
    return { animation: style.animationName, opacity: style.opacity, duration: style.transitionDuration }
  })
  assert.equal(dialog.animation, 'none', 'the settings dialog opens without an entry animation')
  assert.equal(dialog.opacity, '1', 'the settings dialog is fully readable when it appears')
  await page.screenshot({ path: path.join(screenshots, 'settings-dialog-1440.png') })
  await page.keyboard.press('Escape')
  checks.push('dialog: explicit open stays instant and fully readable')

  await auditTransitions(page, 'desktop import')
  // Short colour fades may still be finishing when the pointer moves; what must
  // not exist is an animation that keeps running once the page is idle.
  await page.waitForFunction(() => document.getAnimations().length === 0, null, { timeout: 2000 })
  assert.deepEqual(await page.evaluate(() => document.getAnimations().length), 0, 'idle pages must not keep running animations')
  // Guard proof: the audit has to reject the defect it exists to catch, or it is
  // only restating the stylesheet back at itself.
  const auditProbe = await page.addStyleTag({ content: 'button { transition: all 400ms !important; }' })
  try {
    await assert.rejects(() => auditTransitions(page, 'guard proof'), 'the budget audit must reject transition:all over 300ms')
  } finally { await auditProbe.evaluate(element => element.remove()) }
  checks.push('budget: no transition:all, no over-300ms transition, no idle animation (rejects the injected defect)')
  await context.close()
}

// Hover and :active have the same specificity for the danger role, so this pins
// the cascade order that makes a held button show its pressed colour, not hover.
async function verifyPressedOverridesHover(browser) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } })
  const page = await context.newPage()
  await mockReports(page, [])
  await page.goto(origin)
  await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor({ timeout: 15000 })
  await page.getByRole('button', { name: '体验示例', exact: true }).first().click()
  await page.getByRole('button', { name: '检查候选', exact: true }).click()
  await page.getByRole('heading', { name: '检查政策候选' }).waitFor()
  await page.locator('.candidate-item').first().click()
  const danger = page.getByRole('button', { name: '删除候选', exact: true })
  const candidates = await page.locator('.candidate-item').count()
  await danger.hover()
  await page.waitForTimeout(250)
  const hovered = await danger.evaluate(element => getComputedStyle(element).backgroundColor)
  assert.equal(hovered, 'rgb(147, 67, 66)', 'hovering a danger button must use the --error role')
  const box = await danger.boundingBox()
  await page.mouse.move(box.x + box.width / 2, box.y + box.height / 2)
  await page.mouse.down()
  // The colour itself is eased, so let the fade finish before reading which rule won.
  // The press offset is asserted separately as an immediate, untransitioned change.
  await page.waitForTimeout(250)
  const pressed = await danger.evaluate(element => getComputedStyle(element).backgroundColor)
  // Guard proof: appending the same hover rule after the :active rules reproduces
  // the cascade bug this assertion exists to catch, so the probe is not vacuous.
  const badOrder = await page.addStyleTag({ content: '.ui-button.danger:hover:not(:disabled) { background: var(--error); }' })
  await page.waitForTimeout(250)
  const lateHover = await danger.evaluate(element => getComputedStyle(element).backgroundColor)
  await badOrder.evaluate(element => element.remove())
  // Leave the button before releasing so the click (and the delete) never fires.
  await page.mouse.move(4, 4)
  await page.mouse.up()
  assert.equal(pressed, 'rgb(235, 218, 218)', 'holding a danger button must override hover with the --rose pressed role')
  assert.equal(lateHover, 'rgb(147, 67, 66)', 'a hover rule declared after :active must win, so the press assertion can fail')
  assert.equal(await page.locator('.candidate-item').count(), candidates, 'the press probe must not delete a candidate')
  await context.close()
  checks.push('feedback: pressed colour overrides hover (danger role, same specificity; later hover rule would win)')
}

async function verifyTouchPointer(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true })
  const page = await context.newPage()
  await mockReports(page, [])
  await page.goto(origin)
  await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor({ timeout: 15000 })
  const gate = await page.evaluate(() => matchMedia('(hover: hover) and (pointer: fine)').matches)
  assert.equal(gate, false, 'a touch pointer must not match the hover gate')
  const button = page.getByRole('button', { name: '项目设置', exact: true })
  const base = await button.evaluate(element => getComputedStyle(element).backgroundColor)
  await button.hover()
  await page.waitForTimeout(250)
  const hovered = await button.evaluate(element => getComputedStyle(element).backgroundColor)
  assert.equal(hovered, base, 'a touch tap must not leave a stuck hover highlight')
  // Guard proof: an ungated hover rule is observable here, so the assertion above
  // would fail if someone dropped the media query.
  const hoverProbe = await page.addStyleTag({ content: 'button:hover { background: rgb(1, 2, 3) !important; }' })
  try {
    await button.hover()
    await page.waitForTimeout(250)
    assert.notEqual(await button.evaluate(element => getComputedStyle(element).backgroundColor), base, 'the touch probe must still be able to see hover styling')
  } finally { await hoverProbe.evaluate(element => element.remove()) }
  checks.push('pointer: touch device gets no sticky hover feedback (probe detects an ungated rule)')
  await context.close()
}

async function verifyReducedMotion(browser, reduce) {
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: reduce ? 'reduce' : 'no-preference' })
  await context.addInitScript(() => {
    window.__scrollCalls = []
    const original = Element.prototype.scrollIntoView
    Element.prototype.scrollIntoView = function (options) {
      window.__scrollCalls.push(options && options.behavior ? options.behavior : 'auto(default)')
      return original.apply(this, arguments)
    }
  })
  const page = await context.newPage()
  const ledger = []
  await mockReports(page, ledger)
  await page.goto(origin + '/#reports')
  await page.locator('.report-table tbody tr').first().waitFor({ timeout: 15000 })
  await page.evaluate(() => document.fonts.ready)

  const evidenceButton = page.locator('.report-table tbody tr').first().locator('.evidence-button')
  await evidenceButton.click()
  const state = await page.evaluate(() => {
    const panel = document.getElementById('evidence-panel')
    const style = panel ? getComputedStyle(panel) : null
    return {
      calls: window.__scrollCalls,
      opacity: style ? style.opacity : null,
      animation: style ? style.animationName : null,
      transition: style ? style.transitionDuration : null,
      text: panel ? panel.innerText.length : 0,
    }
  })
  assert.equal(state.calls.at(-1), reduce ? 'auto' : 'smooth', 'evidence scroll must follow the reduced-motion preference')
  assert.equal(state.opacity, '1', 'the evidence panel must be readable before any scroll finishes')
  assert.equal(state.animation, 'none', 'no animation may gate the evidence panel')
  assert.ok(state.text > 0, 'the evidence panel must render its content synchronously')
  if (reduce) {
    assert.equal(state.transition, '0s', 'reduced motion turns transitions off instead of slowing them')
    assert.deepEqual(await page.evaluate(() => document.getAnimations().length), 0, 'reduced motion must leave no animation running')
  }
  // Both modes settle to the same frame before capture, so the two screenshots are
  // directly comparable: the preference changes how the scroll happens, not the result.
  await page.waitForTimeout(400)
  await page.screenshot({ path: path.join(screenshots, reduce ? 'reports-evidence-reduced-1440.png' : 'reports-evidence-1440.png') })
  checks.push(reduce
    ? 'reduced motion: evidence scroll is instant (behavior=auto), transitions off, panel readable'
    : 'normal motion: evidence scroll animates (behavior=smooth), panel readable immediately')

  // Continuous toggling: rapid open/close must settle in the real state, leave no
  // duplicate panel and issue no duplicate report request.
  const requestsBefore = ledger.length
  const issueRows = page.locator('.report-table tbody tr')
  for (let cycle = 0; cycle < 3; cycle++) {
    await issueRows.nth(0).locator('.evidence-button').click()
    await issueRows.nth(1).locator('.evidence-button').click()
    await page.getByRole('button', { name: '收起', exact: true }).click()
    assert.equal(await page.locator('#evidence-panel').count(), 0, 'closing must remove the panel instead of fading it out')
    assert.equal(await issueRows.nth(1).locator('.evidence-button').getAttribute('aria-expanded'), 'false', 'closed rows must report collapsed state')
  }
  assert.equal(await page.locator('#evidence-panel').count(), 0)
  assert.equal(ledger.length, requestsBefore, 'opening and closing evidence must not re-trigger report requests')
  checks.push('continuity: 3 rounds of open-row/open-other-row/close (9 clicks, 3 closes) settle closed with no duplicate request')

  // Low-performance simulation: the panel still appears readable, not half-faded.
  const cdp = await context.newCDPSession(page)
  await cdp.send('Emulation.setCPUThrottlingRate', { rate: 6 })
  try {
    const started = Date.now()
    await issueRows.nth(0).locator('.evidence-button').click()
    await page.waitForFunction(() => {
      const panel = document.getElementById('evidence-panel')
      return panel && getComputedStyle(panel).opacity === '1' && panel.innerText.length > 0
    }, null, { timeout: 5000 })
    const elapsed = Date.now() - started
    assert.ok(elapsed < 2000, 'a throttled device must still show the evidence promptly (took ' + elapsed + 'ms)')
    checks.push('low performance: 6x CPU throttle shows evidence at full opacity in ' + elapsed + 'ms')
  } finally {
    await cdp.send('Emulation.setCPUThrottlingRate', { rate: 1 })
  }

  // Long text: expand the report provenance so the 10 KB policy body actually
  // renders, then assert it stays readable and never scrolls sideways.
  await page.locator('.provenance > summary').click()
  await page.locator('.provenance article details > summary').first().click()
  await page.waitForFunction(() => {
    const pre = document.querySelector('.provenance article details pre')
    return Boolean(pre) && pre.textContent.length > 4000
  }, null, { timeout: 5000 })
  const longText = await page.evaluate(() => {
    const pre = document.querySelector('.provenance article details pre')
    return {
      length: pre.textContent.length,
      preScrollWidth: pre.scrollWidth,
      preClientWidth: pre.clientWidth,
      documentOverflow: document.documentElement.scrollWidth - window.innerWidth,
    }
  })
  assert.ok(longText.length > 4000, 'the long policy body must render in full')
  assert.ok(longText.documentOverflow <= 0, 'long policy text must not widen the document (overflow ' + longText.documentOverflow + 'px)')
  assert.ok(longText.preScrollWidth <= longText.preClientWidth + 1, 'long policy text must wrap inside its block instead of scrolling sideways')
  checks.push('long text: ' + longText.length + '-character policy renders without widening the document or scrolling sideways')

  // Visibility change: returning from a hidden tab must not leave a half-applied state.
  await page.waitForFunction(() => document.getAnimations().length === 0, null, { timeout: 2000 })
  const requestsBeforeRestore = ledger.length
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'hidden' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  await page.evaluate(() => {
    Object.defineProperty(document, 'visibilityState', { configurable: true, get: () => 'visible' })
    document.dispatchEvent(new Event('visibilitychange'))
  })
  const restored = await page.evaluate(() => {
    const panel = document.getElementById('evidence-panel')
    return { present: Boolean(panel), opacity: panel ? getComputedStyle(panel).opacity : null, animations: document.getAnimations().length, text: panel ? panel.innerText.length : 0 }
  })
  assert.equal(restored.present, true, 'the open evidence panel must survive a visibility round trip')
  assert.equal(restored.opacity, '1', 'returning to the tab must not leave a half-faded panel')
  assert.ok(restored.text > 0, 'returning to the tab must not blank the panel content')
  assert.equal(restored.animations, 0, 'a visibility round trip must not restart animations')
  assert.equal(ledger.length, requestsBeforeRestore, 'a visibility round trip must not re-trigger report requests')
  checks.push('background restore: visibility round trip keeps the panel readable and issues no new request (DOM-level simulation, not a real suspend)')

  await auditTransitions(page, 'reports view')
  await context.close()
}

async function verifyNarrowEvidence(browser) {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 } })
  const page = await context.newPage()
  await mockReports(page, [])
  await page.goto(origin)
  await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor({ timeout: 15000 })
  await page.evaluate(() => document.fonts.ready)
  await runWorkflowExample(page)
  const rowButton = page.locator('.comparison-table tbody tr').first().getByRole('button').first()
  await rowButton.click()
  const inline = await page.evaluate(() => {
    const cell = document.querySelector('.comparison-table td.row-evidence')
    if (!cell) return { present: false }
    const style = getComputedStyle(cell)
    return { present: true, animation: style.animationName, opacity: style.opacity, transform: style.transform, text: cell.innerText.length }
  })
  assert.equal(inline.present, true, 'the narrow layout must expand the row in place')
  assert.equal(inline.animation, 'none', 'the expanded row must not fade in from invisible')
  assert.equal(inline.opacity, '1', 'the expanded row is readable on the first frame')
  assert.equal(inline.text > 0, true, 'the expanded row must render its evidence immediately')
  assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'the narrow evidence row must not overflow the page')
  // The page-level check cannot see content clipped by the table's own scroll box,
  // so measure the expanded cell itself.
  const clipping = await page.evaluate(() => {
    const cell = document.querySelector('.comparison-table td.row-evidence')
    const pre = cell ? cell.querySelector('pre') : null
    return {
      cellScroll: cell ? cell.scrollWidth : 0,
      cellClient: cell ? cell.clientWidth : 0,
      preScroll: pre ? pre.scrollWidth : 0,
      preClient: pre ? pre.clientWidth : 0,
    }
  })
  assert.ok(clipping.cellScroll <= clipping.cellClient + 1, 'the expanded row must not scroll sideways (cell ' + clipping.cellScroll + ' > ' + clipping.cellClient + ')')
  assert.ok(clipping.preScroll <= clipping.preClient + 1, 'evidence code blocks must wrap inside the expanded row (pre ' + clipping.preScroll + ' > ' + clipping.preClient + ')')
  await page.screenshot({ path: path.join(screenshots, 'inline-evidence-390.png') })
  checks.push('narrow evidence: expands in place with no entry animation and readable on the first frame')

  // Long text must not change the answer: the row is present, unclipped and readable.
  await rowButton.click()
  assert.equal(await page.locator('.comparison-table td.row-evidence').count(), 0, 'collapsing must remove the expanded row')
  checks.push('narrow evidence: collapse is immediate and leaves no empty cell')
  await context.close()
}

async function main() {
  fs.mkdirSync(screenshots, { recursive: true })
  const children = []
  let browser
  try {
    if (!process.env.PRIVACYTRACE_FRONTEND_URL) {
      try { await fetch(origin, { signal: AbortSignal.timeout(1000) }); throw new Error('Port 5184 is already occupied. Set PRIVACYTRACE_FRONTEND_URL only for an explicitly chosen server.') }
      catch (error) { if (!['TypeError', 'TimeoutError'].includes(error.name)) throw error }
      const child = spawn('npm run dev', spawnOptions(path.resolve(__dirname, '..'), { PRIVACYTRACE_WEB_PORT: '5184' }))
      children.push(child)
      let log = ''
      child.stdout.on('data', chunk => { log += chunk })
      child.stderr.on('data', chunk => { log += chunk })
      const deadline = Date.now() + 30000
      let ready = false
      while (Date.now() < deadline) {
        if (child.exitCode !== null) throw new Error(log)
        try { const response = await fetch(origin); if (response.ok) { ready = true; break } } catch {}
        await new Promise(resolve => setTimeout(resolve, 200))
      }
      if (!ready) throw new Error('Frontend startup timed out: ' + log)
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    await verifyPointerFeedback(browser)
    await verifyPressedOverridesHover(browser)
    await verifyTouchPointer(browser)
    await verifyReducedMotion(browser, false)
    await verifyReducedMotion(browser, true)
    await verifyNarrowEvidence(browser)
    const sourceFiles = fs.readdirSync(path.resolve('apps/web/src'), { recursive: true })
      .filter(file => fs.statSync(path.join('apps/web/src', file)).isFile()).sort()
    const sourceHash = crypto.createHash('sha256')
    for (const file of sourceFiles) sourceHash.update(file).update(fs.readFileSync(path.join('apps/web/src', file)))
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({
      result: 'PASS',
      commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      dirty: Boolean(execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim()),
      source_sha256: sourceHash.digest('hex'),
      scope: 'motion feedback, hover gating, reduced motion and evidence expansion; API responses mocked',
      modes: ['hover: hover / pointer: fine', 'touch (hasTouch+isMobile)', 'prefers-reduced-motion: no-preference', 'prefers-reduced-motion: reduce', 'CPU throttle 6x'],
      checks,
    }, null, 2))
    console.log('Motion checks passed:', checks.length)
    for (const check of checks) console.log(' -', check)
  } finally {
    await browser?.close()
    const survivors = await stopChildren(children)
    if (survivors.length) throw new Error('This test left a server process running')
  }
}
main().catch(error => {
  console.error(error)
  try { fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({ result: 'FAIL', failure: error && error.message ? error.message : String(error), at: new Date().toISOString() }, null, 2)) } catch {}
  process.exitCode = 1
})
