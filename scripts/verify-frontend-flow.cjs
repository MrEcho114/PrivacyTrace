const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawn, execFileSync } = require('node:child_process')
const crypto = require('node:crypto')
const { stopChildren, spawnOptions } = require('./lib/process-control.cjs')
const { assertDesign, assertSurface, verifyGuardFailures } = require('./lib/frontend-guards.cjs')
const { verifyInputRecovery } = require('./lib/frontend-regressions.cjs')
const design = require('./fixtures/pioneer-design.json')

const output = path.resolve('tmp/issue44-ui')
const screenshots = path.join(output, 'screenshots')
fs.mkdirSync(screenshots, { recursive: true })
async function captureWidths(page, name) {
  for (const [width, height] of [[1440, 900], [1920, 1080], [1280, 720], [768, 1024], [390, 844]]) {
    await page.setViewportSize({ width, height }); await page.evaluate(() => document.fonts.ready)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `${name} overflow at ${width}`)
    await assertDesign(page)
    await assertSurface(page, name)
    await page.evaluate(() => window.scrollTo(0, 0))
    await page.screenshot({ path: path.join(screenshots, `${name}-${width}-viewport.png`) })
    await page.screenshot({ path: path.join(screenshots, `${name}-${width}.png`), fullPage: true })
  }
  await page.setViewportSize({ width: 1440, height: 900 })
}


// Issue #72: the report view (#reports) is exercised against deterministic job fixtures; no backend is involved.
// Shapes follow apps/web/src/contracts.generated.ts so a schema drift shows up as a broken assertion, not a silent skip.
const policySentence = '我们会收集设备位置信息，用于附近门店推荐。'
const failedJob = {
  id: 'job-mobile-failed',
  sample_id: 'sample-mobile-failed',
  input_mode: 'APK',
  source_origin: 'REAL_SCAN',
  state: 'FAILED',
  ruleset_version: 'ruleset-mobile-acceptance-1',
  created_at: '2026-10-14T08:00:00Z',
  package_name: 'com.example.mobile.failed',
  version_code: 7,
  error: JSON.stringify({ code: 'DEX_UNSUPPORTED', message: 'DEX 解析中断，未生成报告。', primary_error: 'unsupported dex version 041' }),
}
const succeededJob = {
  id: 'job-mobile-succeeded',
  sample_id: 'sample-mobile-succeeded',
  input_mode: 'APK',
  source_origin: 'REAL_SCAN',
  state: 'SUCCEEDED',
  ruleset_version: 'ruleset-mobile-acceptance-1',
  created_at: '2026-10-14T08:05:00Z',
  package_name: 'com.example.mobile.ok',
  version_code: 7,
  error: null,
}
const taxonomyFixture = {
  version: 'taxonomy-mobile-acceptance',
  data_types: [{ id: 'LOCATION', label: '位置信息', parent: null }, { id: 'DEVICE_ID', label: '设备标识', parent: null }],
}
const reportFixture = {
  sample: { name: '手机端验收示例', package_name: 'com.example.mobile.ok', version_name: '1.0.7', version_code: 7, apk_sha256: 'a'.repeat(64), permissions: ['android.permission.ACCESS_FINE_LOCATION'], dex_entries: ['classes.dex'] },
  job: succeededJob,
  delivery_mode: 'PERSISTED_REPLAY',
  result: {
    job_id: succeededJob.id,
    ruleset_version: 'ruleset-mobile-acceptance-1',
    issues: [
      {
        id: 'issue-location',
        behavior_id: 'beh-location',
        data_type: 'LOCATION',
        status: 'EXACT_MATCH',
        evidence_status: 'STATIC_POTENTIAL',
        policy_document_ids: ['doc-web-1'],
        evidence_ids: ['ev-api-location', 'ev-sentence-location'],
        explanation: '官网政策按具体类型声明了位置信息，但目的与时间范围没有写清。',
        scope: 'DATA_TYPE_DISCLOSURE',
        requires_review: true,
      },
      {
        id: 'issue-device',
        behavior_id: 'beh-device',
        data_type: 'DEVICE_ID',
        status: 'NOT_DECLARED',
        evidence_status: 'STATIC_POTENTIAL',
        policy_document_ids: [],
        evidence_ids: ['ev-api-device'],
        explanation: '政策快照中没有设备标识的对应条款；缺少全文复核时不能据此断言违规。',
        scope: 'DATA_TYPE_DISCLOSURE',
        requires_review: true,
      },
    ],
  },
  evidence: [
    {
      id: 'ev-api-location',
      kind: 'API',
      status: 'STATIC_POTENTIAL',
      source: 'classes.dex',
      locator: 'Lcom/example/MainActivity;->requestLocation(Landroid/location/LocationManager;)V',
      excerpt: 'LocationManager.requestLocationUpdates(...)',
      document_id: null,
      api_call: { target_descriptor: 'android.location.LocationManager#requestLocationUpdates', rule_id: 'rule-location', ruleset_version: 'ruleset-mobile-acceptance-1', context: { receiver: 'UNKNOWN', purpose: 'UNKNOWN', temporal_scope: 'UNKNOWN' } },
    },
    {
      id: 'ev-api-device',
      kind: 'API',
      status: 'STATIC_POTENTIAL',
      source: 'classes.dex',
      locator: 'Lcom/example/MainActivity;->readAndroidId()Ljava/lang/String;',
      excerpt: 'Settings.Secure.getString(cr, ANDROID_ID)',
      document_id: null,
      api_call: { target_descriptor: 'android.provider.Settings$Secure#getString', rule_id: 'rule-device-id', ruleset_version: 'ruleset-mobile-acceptance-1', context: { receiver: 'UNKNOWN' } },
    },
    {
      id: 'ev-sentence-location',
      kind: 'POLICY_SENTENCE',
      status: 'DECLARED',
      source: '官网隐私政策',
      locator: '第 1 段第 1 句',
      document_id: 'doc-web-1',
      start_offset: 0,
      end_offset: 10,
      excerpt: policySentence,
    },
  ],
  behaviors: [
    { id: 'beh-location', data_type: 'LOCATION', action: 'ACCESS', purpose: 'UNKNOWN', recipient: 'UNKNOWN', transfer: 'UNKNOWN', temporal_scope: 'UNKNOWN', evidence_ids: ['ev-api-location'] },
    { id: 'beh-device', data_type: 'DEVICE_ID', action: 'CAPABILITY', evidence_ids: ['ev-api-device'] },
  ],
  policy_documents: [
    {
      id: 'doc-web-1',
      source_type: 'OFFICIAL_WEB_POLICY',
      title: '手机端验收示例官网政策',
      version: '2026-10',
      captured_at: '2026-10-14T07:00:00Z',
      artifact: { text: policySentence, sha256: 'b'.repeat(64), normalization: 'NONE' },
      completeness: 'PARTIAL',
      extraction_status: 'PARTIAL',
      review_status: 'UNREVIEWED',
      attachments_status: 'NOT_CHECKED',
      applicability: { package_name: 'com.example.mobile.ok', version_codes: [7], regions: ['CN'], product_scope: null },
      evidence_id: 'ev-doc-web-1',
    },
  ],
  policy_claims: [
    { id: 'claim-location-1', document_id: 'doc-web-1', data_type: 'LOCATION', action: 'UNKNOWN', polarity: 'UNKNOWN', subject: 'UNKNOWN', condition: null, declared_purpose: null, declared_recipient: null, basis: 'POLICY_DECLARATION', ambiguity_flags: ['UNCLEAR_ACTION'], evidence_ids: ['ev-sentence-location'] },
  ],
  coverage: { status: 'PARTIAL', scope: 'DEX_ENTRIES', behavior_detection: 'LIMITED_RULE_BASED_STATIC', behavior_limitations: ['不覆盖反射与动态加载。'], limitations: ['未扫描 native 代码。'], scanned_dex: ['classes.dex'], failed_dex: [] },
  tools: { report_schema: 'mobile-acceptance-1', analysis_generated_at: '2026-10-14T08:06:00Z', ruleset_version: 'ruleset-mobile-acceptance-1' },
  reviews: [],
}
// After a delete the app drops the active job and falls back to the synthetic report (App.vue:280/318),
// so the demo envelope needs a stub too or the real-request ledger would see /api/v1/demo/report.
const demoReportFixture = {
  ...reportFixture,
  demo: true,
  sample: { ...reportFixture.sample, version: reportFixture.sample.version_name, input_mode: 'SYNTHETIC' },
  delivery_mode: 'LIVE_GENERATED',
}
const fixtureRoutes = ['**/api/v1/taxonomy', '**/api/v1/demo/report', '**/api/v1/jobs', '**/api/v1/jobs/*']
const touchSelectors = ['.ui-button', '[role="tab"]', '.evidence-button', '.candidate-item', '.policy-jump-btn', '.candidate-nav button', '.source-body summary', '.job-state button', '[data-testid="retry-job"]', '[data-testid="delete-job"]', '[data-testid="delete-confirm"]']

async function waitFor(check, message, timeout = 5000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await check()) return
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  assert.fail(message)
}
// The narrow layout hides the header visually (clip) instead of removing it, so assert geometry and roles, not display.
const reportTableHeader = page => page.evaluate(() => {
  const table = document.querySelector('.report-table')
  const head = table ? table.querySelector('thead') : null
  if (!head) return { present: false, thCount: 0, thDisplay: 'absent', width: 0, height: 0, roles: {} }
  const headers = Array.from(head.querySelectorAll('th'))
  const body = table.querySelector('tbody')
  const row = body ? body.querySelector('tr') : null
  const cell = body ? body.querySelector('td') : null
  const rect = head.getBoundingClientRect()
  const round = value => Math.round(value * 10) / 10
  return {
    present: true,
    thCount: headers.length,
    thDisplay: headers.length ? getComputedStyle(headers[0]).display : 'absent',
    width: round(rect.width),
    height: round(rect.height),
    roles: {
      table: table.getAttribute('role'),
      thead: head.getAttribute('role'),
      tbody: body ? body.getAttribute('role') : null,
      th: headers.length ? headers[0].getAttribute('role') : null,
      scope: headers.length ? headers[0].getAttribute('scope') : null,
      row: row ? row.getAttribute('role') : null,
      cell: cell ? cell.getAttribute('role') : null,
    },
  }
})
// The inline row evidence is narrow-only by design (ExampleReport.vue v-if inlineEvidence): above
// 560px the row button opens the standalone #example-evidence section; below 560px that section is
// absent and the selected row expands in place. Pin both sides so nobody renders both presentations.
async function assertReportRowToggle(page, label) {
  const width = page.viewportSize().width
  const state = await page.evaluate(() => {
    const shown = element => Boolean(element) && getComputedStyle(element).display !== 'none' && element.getClientRects().length > 0
    const row = document.querySelector('.comparison-table td.row-evidence')
    const desktop = document.querySelector('.comparison-table td[data-label="依据"] .desktop-toggle')
    const mobile = document.querySelector('.comparison-table td[data-label="依据"] .mobile-toggle')
    return {
      row: row ? getComputedStyle(row).display : 'absent',
      rowVisible: shown(row),
      desktop: desktop ? getComputedStyle(desktop).display : 'absent',
      desktopVisible: shown(desktop),
      mobile: mobile ? getComputedStyle(mobile).display : 'absent',
      mobileVisible: shown(mobile),
    }
  })
  if (width > design.mobileButton.maxWidth) {
    assert.ok(state.row === 'absent' || state.row === 'none', label + ': the inline row evidence must not render on desktop (display=' + state.row + ')')
    assert.equal(state.rowVisible, false, label + ': the inline row evidence must not be reachable on desktop')
    assert.equal(state.desktopVisible, true, label + ': the desktop toggle is the visible affordance on desktop')
    assert.equal(state.mobile, 'none', label + ': the mobile toggle stays hidden on desktop (display=' + state.mobile + ')')
  } else {
    assert.notEqual(state.row, 'absent', label + ': the selected row must render its inline evidence cell at ' + width + 'px')
    assert.equal(state.rowVisible, true, label + ': the row must expand in place at ' + width + 'px (display=' + state.row + ')')
    assert.equal(state.mobileVisible, true, label + ': the mobile toggle is the visible affordance at ' + width + 'px')
    assert.equal(state.desktop, 'none', label + ': the desktop toggle stays hidden at ' + width + 'px (display=' + state.desktop + ')')
  }
  return state
}
const tabState = page => page.evaluate(() => ['tab-original', 'tab-candidates'].map(id => {
  const element = document.getElementById(id)
  if (!element) return { id, missing: true }
  return { id, tabIndex: element.tabIndex, selected: element.getAttribute('aria-selected') }
}))
const panelState = page => page.evaluate(() => ['panel-original', 'panel-candidates'].map(id => {
  const element = document.getElementById(id)
  if (!element) return { id, missing: true }
  return { id, role: element.getAttribute('role'), labelledby: element.getAttribute('aria-labelledby'), visible: element.getClientRects().length > 0 }
}))

const waitForPanel = (page, id, visible) => waitFor(async () => {
  const panel = (await panelState(page)).find(item => item.id === id)
  return Boolean(panel) && panel.visible === visible
}, id + ' visibility did not settle to ' + visible)

// Touch targets only have to reach the mobile minimum, and only below the breakpoint declared in the design fixture.
async function assertTouchTargets(page, label) {
  const width = page.viewportSize().width
  assert.ok(width <= design.mobileButton.maxWidth, label + ': touch targets are asserted at or below ' + design.mobileButton.maxWidth + 'px, got ' + width)
  const measured = await page.evaluate(({ selectors, minHeight }) => {
    const short = []
    let total = 0
    for (const selector of selectors) {
      for (const element of document.querySelectorAll(selector)) {
        if (!element.getClientRects().length) continue
        total += 1
        const height = Math.round(element.getBoundingClientRect().height * 10) / 10
        if (height < minHeight) short.push(selector + ' => ' + height + 'px')
      }
    }
    return { short, total }
  }, { selectors: touchSelectors, minHeight: design.mobileButton.minHeight })
  assert.ok(measured.total > 0, label + ': no interactive target matched the touch list')
  assert.deepEqual(measured.short, [], label + ': touch targets under ' + design.mobileButton.minHeight + 'px at ' + width + 'px wide')
  return [label + ': ' + measured.total + ' interactive targets at or above ' + design.mobileButton.minHeight + 'px']
}

async function assertRovingTabs(page, expected, label, options = {}) {
  const tabs = await tabState(page)
  for (const tab of tabs) assert.equal(!tab.missing, true, label + ': missing #' + tab.id)
  assert.equal(tabs.filter(tab => tab.tabIndex === 0).length, 1, label + ': roving tabindex must leave exactly one tab stop')
  for (const tab of tabs) {
    const active = tab.id === 'tab-' + expected
    assert.equal(tab.selected, String(active), label + ': ' + tab.id + ' aria-selected must follow the active tab')
    assert.equal(tab.tabIndex, active ? 0 : -1, label + ': ' + tab.id + ' tabindex must rove')
  }
  if (options.focus !== false) assert.equal(await page.evaluate(() => document.activeElement ? document.activeElement.id : ''), 'tab-' + expected, label + ': focus must follow the active tab')
  const panels = await panelState(page)
  for (const panel of panels) {
    assert.equal(!panel.missing, true, label + ': missing #' + panel.id)
    assert.equal(panel.role, 'tabpanel', label + ': ' + panel.id + ' must keep role=tabpanel')
    assert.equal(panel.labelledby, panel.id === 'panel-original' ? 'tab-original' : 'tab-candidates', label + ': ' + panel.id + ' must be labelled by its own tab')
    assert.equal(panel.visible, panel.id === 'panel-' + expected, label + ': only panel-' + expected + ' may render at 390px (' + panel.id + ' visible=' + panel.visible + ')')
  }
}

async function verifyMobilePanels(page) {
  const checks = []
  await page.setViewportSize({ width: 390, height: 844 })
  await page.evaluate(() => document.fonts.ready)
  const tablist = page.locator('.mobile-panel-tabs')
  assert.equal(await tablist.count(), 1, 'candidate view needs one .mobile-panel-tabs')
  assert.equal(await tablist.getAttribute('role'), 'tablist', 'candidate tabs need role=tablist')
  assert.equal(await tablist.getAttribute('aria-label'), '检查候选视图', 'candidate tablist aria-label drifted')
  assert.equal(await page.getByRole('tab').count(), 2, 'candidate view must expose exactly two role=tab elements')
  const original = page.locator('#tab-original')
  const candidates = page.locator('#tab-candidates')
  assert.equal(await original.count(), 1, 'missing #tab-original')
  assert.equal(await candidates.count(), 1, 'missing #tab-candidates')
  assert.equal(await original.getAttribute('aria-controls'), 'panel-original', '#tab-original must control panel-original')
  assert.equal(await candidates.getAttribute('aria-controls'), 'panel-candidates', '#tab-candidates must control panel-candidates')
  assert.equal((await original.innerText()).includes('政策原文'), true, '#tab-original must read 政策原文')
  assert.equal((await candidates.innerText()).includes('候选声明'), true, '#tab-candidates must read 候选声明')
  // The product default is the candidate list, not the original text (apps/web/src/pages/CandidatePage.vue:14),
  // so pin that before touching any input and start every keyboard step from a known active tab.
  await waitForPanel(page, 'panel-candidates', true)
  await assertRovingTabs(page, 'candidates', 'initial', { focus: false })
  checks.push(...await assertTouchTargets(page, 'candidates/候选声明'))
  await original.click()
  await waitForPanel(page, 'panel-original', true)
  await assertRovingTabs(page, 'original', 'click #tab-original')
  await page.keyboard.press('ArrowRight')
  await waitForPanel(page, 'panel-candidates', true)
  await assertRovingTabs(page, 'candidates', 'ArrowRight')
  await page.keyboard.press('ArrowLeft')
  await waitForPanel(page, 'panel-original', true)
  await assertRovingTabs(page, 'original', 'ArrowLeft')
  await page.keyboard.press('End')
  await waitForPanel(page, 'panel-candidates', true)
  await assertRovingTabs(page, 'candidates', 'End')
  await page.keyboard.press('Home')
  await waitForPanel(page, 'panel-original', true)
  await assertRovingTabs(page, 'original', 'Home')
  checks.push(...await assertTouchTargets(page, 'candidates/政策原文'))
  await page.keyboard.press('Enter')
  await waitForPanel(page, 'panel-original', true)
  await assertRovingTabs(page, 'original', 'Enter on #tab-original')
  return checks
}

async function verifyMobileReport(page, requests) {
  const checks = []
  const mocked = []
  const deletedIds = []
  const deleteIds = []
  const liveJobs = () => [succeededJob, failedJob].filter(job => !deletedIds.includes(job.id))
  try {
    await page.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomyFixture }))
    await page.route('**/api/v1/demo/report', route => {
      mocked.push(route.request().method() + ' ' + new URL(route.request().url()).pathname)
      return route.fulfill({ json: demoReportFixture })
    })
    await page.route('**/api/v1/jobs/*/report', route => route.fulfill({ json: reportFixture }))
    await page.route('**/api/v1/jobs', route => route.fulfill({ json: { jobs: liveJobs() } }))
    await page.route('**/api/v1/jobs/*', route => {
      const request = route.request()
      const pathname = new URL(request.url()).pathname
      const target = decodeURIComponent(pathname.split('/').pop())
      mocked.push(request.method() + ' ' + pathname)
      if (request.method() === 'DELETE') {
        deleteIds.push(target)
        deletedIds.push(target)
        return route.fulfill({ json: { status: 'deleted', job_id: target } })
      }
      const job = liveJobs().find(item => item.id === target)
      return job ? route.fulfill({ json: job }) : route.fulfill({ status: 404, json: { detail: 'JOB_NOT_FOUND' } })
    })
    await page.locator('.nav-item').filter({ hasText: '已有报告' }).click()
    await page.locator('.report-table tbody tr').first().waitFor({ timeout: 5000 })
    assert.equal(await page.evaluate(() => location.hash), '#reports', 'the report view must be reachable at #reports')
    checks.push('#reports: renders a deterministic SUCCEEDED job')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.evaluate(() => document.fonts.ready)
    const desktopHead = await reportTableHeader(page)
    assert.equal(desktopHead.present, true, 'reports: missing .report-table thead')
    assert.equal(desktopHead.thCount, 4, 'reports: the report table must keep four column headers')
    assert.notEqual(desktopHead.thDisplay, 'none', 'reports: the column headers must stay in the accessibility tree')
    assert.ok(desktopHead.width > 1, 'reports: the column header must be laid out at 1440px (width ' + desktopHead.width + 'px)')
    assert.deepEqual(desktopHead.roles, { table: 'table', thead: 'rowgroup', tbody: 'rowgroup', th: 'columnheader', scope: 'col', row: 'row', cell: 'cell' }, 'reports: the report table must expose explicit table roles')
    await page.locator('.report-table tbody tr').first().locator('.evidence-button').click()
    await waitFor(async () => {
      const top = await page.evaluate(() => {
        const panel = document.getElementById('evidence-panel')
        return panel ? Math.round(panel.getBoundingClientRect().top) : null
      })
      return top !== null && top >= 0 && top <= 48
    }, 'reports: #evidence-panel must scroll to the start of the viewport at 1440px (rect.top within 0..48)')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'reports overflow at 1440')
    await captureWidths(page, 'reports')
    checks.push('reports: evidence panel scrolls into view at 1440px')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    const mobileHead = await reportTableHeader(page)
    assert.equal(mobileHead.present, true, 'reports: the report table keeps its header markup at 390px')
    assert.equal(mobileHead.thCount, 4, 'reports: the stacked cards must keep four column headers')
    assert.notEqual(mobileHead.thDisplay, 'none', 'reports: 390px must hide the header visually, not remove it from the accessibility tree')
    assert.ok(mobileHead.width <= 1 && mobileHead.height <= 1, 'reports: the column header must be visually hidden at 390px (got ' + mobileHead.width + 'x' + mobileHead.height + 'px)')
    const unlabeled = await page.evaluate(() => Array.from(document.querySelectorAll('.report-table td')).filter(cell => !(cell.getAttribute('data-label') || '').trim()).map(cell => cell.className || 'td'))
    assert.deepEqual(unlabeled, [], 'reports: every report cell needs data-label at 390px')
    const stacked = await page.evaluate(() => {
      const row = document.querySelector('.report-table tbody tr')
      return row ? new Set(Array.from(row.children).map(cell => Math.round(cell.getBoundingClientRect().top))).size : 0
    })
    assert.ok(stacked >= 2, 'reports: report rows must stack into cards at 390px (found ' + stacked + ' shared cell row)')
    const innerOverflow = await page.evaluate(() => {
      const box = document.querySelector('.table-scroll')
      return box ? box.scrollWidth - box.clientWidth : 0
    })
    assert.ok(innerOverflow <= 1, 'reports: the report table must not scroll horizontally at 390px (overflow ' + innerOverflow + 'px)')
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'reports overflow at 390')
    assert.equal(await page.locator('.report-table').getByText('待复核').first().isVisible(), true, 'reports: requires_review rows must show 待复核 at 390px')
    assert.equal(await page.evaluate(() => {
      const panel = document.getElementById('evidence-panel')
      return panel ? panel.innerText.includes('UNKNOWN') : false
    }), true, 'reports: the evidence panel must keep UNKNOWN labels at 390px')
    checks.push('reports: 390px card layout, no horizontal scroll, 待复核 and UNKNOWN copy visible')
    const zoom = await page.addStyleTag({ content: 'html{font-size:150%}' })
    try {
      await page.evaluate(() => document.fonts.ready)
      assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'reports overflow at 390 with a 150% root font size')
    } finally { await zoom.evaluate(element => element.remove()) }
    checks.push('reports: a 150% root font size does not overflow 390px')
    checks.push(...await assertTouchTargets(page, 'reports'))
    await page.locator('#report-source').selectOption('job:' + failedJob.id)
    const jobState = page.locator('.job-state')
    await jobState.locator('[data-testid="retry-job"]').waitFor({ timeout: 5000 })
    assert.equal((await jobState.locator('[data-testid="retry-job"]').innerText()).includes('重试为新的分析'), true, 'reports: the retry control must read 重试为新的分析')
    assert.equal((await jobState.locator('[data-testid="delete-job"]').innerText()).includes('删除任务'), true, 'reports: the delete control must read 删除任务')
    assert.equal(await jobState.locator('[data-testid="retry-job"]').isVisible(), true, 'reports: retry must be visible on a FAILED job')
    assert.equal(await jobState.locator('[data-testid="delete-job"]').isVisible(), true, 'reports: delete must be visible on a FAILED job')
    assert.equal(await page.locator('.report-table').count(), 0, 'reports: a FAILED job must not render the report table')
    checks.push(...await assertTouchTargets(page, 'reports/终态任务'))
    await jobState.locator('[data-testid="delete-job"]').click()
    await jobState.locator('[data-testid="delete-confirm"]').waitFor({ timeout: 5000 })
    assert.deepEqual(deleteIds, [], 'reports: 删除任务 must not send DELETE before its confirmation step')
    assert.equal((await jobState.locator('[data-testid="delete-confirm"]').innerText()).includes('确认删除'), true, 'reports: the confirmation control must read 确认删除')
    checks.push(...await assertTouchTargets(page, 'reports/终态任务'))
    const sent = page.waitForRequest(request => request.method() === 'DELETE' && request.url().includes('/api/v1/jobs/'), { timeout: 5000 })
    await jobState.locator('[data-testid="delete-confirm"]').click()
    const request = await sent
    const target = new URL(request.url()).pathname.split('/').pop()
    assert.equal(target, failedJob.id, 'reports: delete must target ' + failedJob.id + ', got ' + request.url())
    await waitFor(() => page.evaluate(id => !Array.from(document.querySelectorAll('#report-source option')).some(option => option.value === 'job:' + id), failedJob.id), 'reports: the deleted job must leave the report list')
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    // Longer than the 1500ms job poll, so a resurrected job would show up in the source picker.
    await new Promise(resolve => setTimeout(resolve, 1700))
    assert.equal(await page.evaluate(id => Array.from(document.querySelectorAll('#report-source option')).some(option => option.value === 'job:' + id), failedJob.id), false, 'reports: a deleted job must not be revived by a later poll')
    assert.deepEqual(deleteIds, [failedJob.id], 'reports: exactly one DELETE for the removed job')
    checks.push('reports: two-step delete sends DELETE /api/v1/jobs/' + failedJob.id + ' and does not revive')
  } finally {
    for (const pattern of fixtureRoutes) await page.unroute(pattern)
    await page.setViewportSize({ width: 1440, height: 900 })
    // Mocked transport never reaches the network, so it is recorded separately from the real-request ledger.
    for (let index = requests.length - 1; index >= 0; index--) {
      const url = requests[index]
      if (url.includes('/api/v1/jobs') || url.includes('/api/v1/demo/report')) requests.splice(index, 1)
    }
  }
  return { checks, mocked }
}

async function main() {
  const origin = process.env.PRIVACYTRACE_FRONTEND_URL || 'http://127.0.0.1:5184'
  const children = []
  let browser
  try {
    if (!process.env.PRIVACYTRACE_FRONTEND_URL) {
      try { await fetch(origin, { signal: AbortSignal.timeout(1000) }); throw new Error('Port 5184 is already occupied. Set PRIVACYTRACE_FRONTEND_URL only for an explicitly chosen server.') }
      catch (error) { if (!['TypeError', 'TimeoutError'].includes(error.name)) throw error }
      const child = spawn('npm run dev', spawnOptions(path.resolve(__dirname, '..'), { PRIVACYTRACE_WEB_PORT: '5184' }))
      children.push(child)
      let serverLog = ''
      child.stdout.on('data', chunk => { serverLog += chunk })
      child.stderr.on('data', chunk => { serverLog += chunk })
      const deadline = Date.now() + 30000
      let ready = false
      while (Date.now() < deadline) {
        if (child.exitCode !== null) throw new Error(serverLog)
        try { const response = await fetch(origin); if (response.ok) { ready = true; break } } catch {}
        await new Promise(resolve => setTimeout(resolve, 200))
      }
      if (!ready) throw new Error('Frontend startup timed out: ' + serverLog)
    }
    browser = await chromium.launch({ headless: true })
    const inputRegressions = await verifyInputRecovery(browser, origin)
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const errors = []; const requests = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (request.url().includes('/api/')) requests.push(request.url()) })
    await page.goto(origin)
    await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor({ timeout: 5000 })
    await page.evaluate(() => document.fonts.ready)
    const guardRegressions = await verifyGuardFailures(page)
    await page.evaluate(() => window.scrollTo(0, 0))
    const skipLink = page.getByRole('link', { name: '跳到内容', exact: true })
    assert.equal(await skipLink.evaluate(element => getComputedStyle(element).opacity), '0')
    await page.keyboard.press('Tab')
    assert.equal(await skipLink.evaluate(element => element === document.activeElement && getComputedStyle(element).opacity === '1'), true)
    await page.keyboard.press('Enter')
    assert.equal(await page.locator('#workspace-content').evaluate(element => element === document.activeElement), true)
    assert.equal(await page.getByRole('button', { name: '体验示例', exact: true }).count(), 1)
    await page.locator('input[accept=".apk"]').setInputFiles({ name: 'invalid.txt', mimeType: 'text/plain', buffer: Buffer.from('example') })
    await page.getByRole('alert').filter({ hasText: '文件格式不支持' }).waitFor()
    await page.locator('input[accept=".apk"]').setInputFiles({ name: 'example.apk', mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic name only; never scanned') })
    await page.getByText('example.apk', { exact: true }).waitFor()
    assert.equal(await page.getByRole('button', { name: '获取政策并检查候选', exact: true }).isDisabled(), true)
    await page.locator('.apk-panel').getByRole('button', { name: '体验示例', exact: true }).click()
    await page.evaluate(() => document.fonts.ready)
    await page.getByLabel('政策网址', { exact: true }).first().fill('https://example.com/' + 'a'.repeat(1800))
    await captureWidths(page, 'import')
    await page.getByRole('button', { name: '检查候选', exact: true }).click()
    await page.getByRole('heading', { name: '检查政策候选' }).waitFor()
    await page.locator('.candidate-item').first().click()
    const originalQuote = await page.getByLabel('政策原句', { exact: true }).inputValue()
    assert.equal(await page.locator('#candidate-quote-mark').innerText(), originalQuote)
    await page.getByRole('button', { name: '定位原句', exact: true }).click()
    assert.equal(await page.locator('#candidate-quote-mark').evaluate(element => element === document.activeElement), true)
    await page.getByLabel('声明方式', { exact: true }).selectOption('NEGATED')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.getByRole('status').filter({ hasText: '已保存' }).waitFor()
    await page.getByLabel('政策原句', { exact: true }).fill('<script>window.attack = 1</script>')
    assert.equal(await page.getByRole('button', { name: '保存候选', exact: true }).isDisabled(), true)
    assert.equal(await page.evaluate(() => window.attack), undefined)
    await page.getByLabel('政策原句', { exact: true }).fill(originalQuote)
    await page.getByLabel('条件', { exact: true }).fill('PRIVATE_FREE_TEXT_44')
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.reload()
    await page.getByRole('heading', { name: '检查政策候选' }).waitFor()
    assert.equal(await page.getByLabel('声明方式', { exact: true }).inputValue(), 'NEGATED')
    assert.equal(await page.evaluate(() => localStorage.getItem('privacytrace.example.v1').includes('PRIVATE_FREE_TEXT_44')), false)
    await page.getByRole('button', { name: '添加候选', exact: true }).click()
    await page.getByLabel('政策原句', { exact: true }).fill(originalQuote)
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    assert.equal(await page.locator('.candidate-item').count(), 4)
    await page.getByRole('button', { name: '删除候选', exact: true }).click()
    assert.equal(await page.locator('.candidate-item').count(), 3)
    await page.getByRole('button', { name: '云点统计服务说明', exact: true }).click()
    assert.equal(await page.locator('.candidate-item').count(), 1)
    await page.getByRole('button', { name: '纸舟地图隐私政策', exact: true }).click()
    await captureWidths(page, 'candidates')
    await page.getByRole('button', { name: '修改材料', exact: true }).click()
    const firstSource = page.locator('.source-editor').first()
    await firstSource.locator('summary').first().click()
    await firstSource.getByRole('button', { name: '体验来源失败' }).click()
    await firstSource.getByRole('alert').waitFor()
    await page.getByRole('button', { name: '检查候选', exact: true }).click()
    await page.locator('.original-panel').getByText('示例来源获取失败').waitFor()
    await page.locator('.original-panel').getByRole('button', { name: '重试示例来源' }).click()
    await page.getByRole('button', { name: '添加候选' }).waitFor()
    await page.getByRole('button', { name: '修改材料', exact: true }).click()
    await page.getByRole('button', { name: '添加政策来源', exact: true }).click()
    const manualSource = page.locator('.source-editor').last()
    await manualSource.locator('summary').first().click()
    await manualSource.getByLabel('政策正文', { exact: true }).fill('<img src=x onerror="window.attack=1">\n人工补入的测试文字')
    await manualSource.getByRole('button', { name: '使用这份正文', exact: true }).click()
    await page.getByRole('button', { name: '检查候选', exact: true }).click()
    assert.equal(await page.locator('.original-panel img').count(), 0)
    assert.equal(await page.evaluate(() => window.attack), undefined)
    await page.getByRole('button', { name: '纸舟地图隐私政策', exact: true }).click()
    await page.getByRole('button', { name: '进入流程演示', exact: true }).click()
    await page.getByText('阶段与来源详情', { exact: true }).click()
    await page.getByRole('button', { name: '标记当前阶段失败' }).click()
    await page.getByRole('alert').filter({ hasText: '示例阶段失败' }).waitFor()
    await page.screenshot({ path: path.join(screenshots, 'failure-1440.png'), fullPage: true })
    await page.getByRole('button', { name: '重试', exact: true }).click()
    await page.getByRole('button', { name: '取消', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: '已取消' }).waitFor()
    await page.getByRole('button', { name: '重试', exact: true }).click()
    await captureWidths(page, 'progress')
    for (let index = 0; index < 4; index++) await page.getByRole('button', { name: '进入下一阶段', exact: true }).click()
    await page.getByRole('button', { name: '完成当前阶段', exact: true }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.getByRole('heading', { name: '分析报告', exact: true }).waitFor()
    await page.getByLabel('报告来源筛选').selectOption('sdk')
    assert.equal(await page.locator('.comparison-table tbody tr').count(), 1)
    await page.getByLabel('报告来源筛选').selectOption('all')
    await page.getByRole('button', { name: '查看线索详情：位置信息', exact: true }).click()
    assert.equal(await page.locator('#example-evidence-title').evaluate(element => element === document.activeElement), true)
    await page.getByRole('button', { name: '查看示例全文', exact: true }).click()
    assert.equal(await page.locator('#example-evidence mark').innerText(), originalQuote)
    await assertReportRowToggle(page, 'report 桌面行内证据')
    await captureWidths(page, 'report')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await assertReportRowToggle(page, 'report 窄屏行内证据')
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.getByLabel('报告来源筛选').selectOption('sdk')
    await page.locator('#example-evidence').getByRole('button', { name: '关闭', exact: true }).click()
    assert.equal(await page.locator('#page-title').evaluate(element => element === document.activeElement), true)
    await page.getByLabel('报告来源筛选').selectOption('all')
    const deviceEvidenceButton = page.getByRole('button', { name: '查看线索详情：设备标识', exact: true })
    await deviceEvidenceButton.click()
    await page.locator('#example-evidence').getByRole('button', { name: '关闭', exact: true }).click()
    assert.equal(await deviceEvidenceButton.evaluate(element => element === document.activeElement), true)
    await page.getByRole('button', { name: '项目设置', exact: true }).click()
    await page.getByRole('dialog').waitFor()
    assert.equal(await page.locator('#model-key').getAttribute('type'), 'password')
    assert.equal(await page.locator('#model-key').inputValue(), '')
    await page.route('**/api/v1/health', route => route.fulfill({ json: { status: 'ok' } }))
    await page.getByRole('button', { name: '测试连接', exact: true }).click()
    await page.getByText('分析服务有响应', { exact: true }).waitFor()
    await captureWidths(page, 'settings')
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press('Tab')
      assert.equal(await page.getByRole('dialog').evaluate(element => element.contains(document.activeElement)), true)
    }
    await page.unroute('**/api/v1/health')
    await page.route('**/api/v1/health', route => route.fulfill({ status: 503, body: 'unavailable' }))
    await page.getByRole('button', { name: '测试连接', exact: true }).click()
    await page.getByText('未连接分析服务', { exact: true }).waitFor()
    await page.keyboard.press('Escape')
    assert.equal(await page.getByRole('button', { name: '项目设置', exact: true }).evaluate(element => element === document.activeElement), true)
    assert.equal(requests.filter(url => !url.endsWith('/health') && !url.endsWith('/taxonomy') && !url.endsWith('/web/settings')).length, 0, 'example flow must never send scan or policy requests')
    await page.getByRole('button', { name: '项目设置', exact: true }).click()
    await page.getByRole('button', { name: '清除示例草稿', exact: true }).click()
    assert.equal(await page.evaluate(() => localStorage.getItem('privacytrace.example.v1')), null)
    await page.keyboard.press('Escape')
    await page.reload()
    await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    // No selected file or real input survives refresh.
    assert.equal(await page.locator('input[accept=".apk"]').evaluate(element => element.files.length), 0)
    await page.getByLabel('政策正文', { exact: true }).fill('PRIVATE_POLICY_44')
    await page.reload()
    assert.equal(await page.getByLabel('政策正文', { exact: true }).inputValue(), '')
    // Complete step navigation using the keyboard alone.
    await page.locator('.apk-panel').getByRole('button', { name: '体验示例' }).focus()
    await page.keyboard.press('Enter')
    await page.getByRole('button', { name: '检查候选', exact: true }).focus(); await page.keyboard.press('Enter')
    await page.getByRole('heading', { name: '检查政策候选' }).waitFor()
    await page.getByRole('button', { name: '进入流程演示' }).focus(); await page.keyboard.press('Enter')
    for (let index = 0; index < 4; index++) { await page.getByRole('button', { name: '进入下一阶段' }).focus(); await page.keyboard.press('Enter') }
    await page.getByRole('button', { name: '完成当前阶段' }).focus(); await page.keyboard.press('Enter')
    await page.getByRole('button', { name: '查看报告', exact: true }).focus(); await page.keyboard.press('Enter')
    await page.getByRole('heading', { name: '分析报告', exact: true }).waitFor()
    await page.emulateMedia({ reducedMotion: 'reduce' })
    assert.equal(await page.locator('.workbench').evaluate(element => getComputedStyle(element).animationName), 'none')
    // Deliver screenshots of the fixed example after adversarial edits are cleared.
    await page.getByRole('button', { name: '新材料', exact: true }).click()
    await page.getByRole('button', { name: '体验示例', exact: true }).click()
    await captureWidths(page, 'import')
    await page.getByRole('button', { name: '检查候选', exact: true }).click()
    await captureWidths(page, 'candidates')
    const mobileChecks = await verifyMobilePanels(page)
    await page.getByRole('button', { name: '修改材料', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    mobileChecks.push(...await assertTouchTargets(page, 'import'))
    const reportChecks = await verifyMobileReport(page, requests)
    mobileChecks.push(...reportChecks.checks)
    assert.deepEqual(errors, [])
    const sourceFiles = fs.readdirSync(path.resolve('apps/web/src'), { recursive: true }).filter(file => fs.statSync(path.join('apps/web/src', file)).isFile()).sort()
    const sourceHash = crypto.createHash('sha256')
    for (const file of sourceFiles) sourceHash.update(file).update(fs.readFileSync(path.join('apps/web/src', file)))
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({ result: 'PASS', commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(), dirty: !!execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim(), source_sha256: sourceHash.digest('hex'), scope: 'synthetic frontend interactions; health response mocked', viewports: [1440, 1920, 1280, 768, 390], guard_regressions: guardRegressions, input_regressions: inputRegressions, mobile_ui: mobileChecks, mocked_requests: reportChecks.mocked, errors, requests }, null, 2))
    console.log('Input recovery:', inputRegressions.join(', '))
    console.log('Frontend flow: import, quote validation, enum edits, add/delete, source switching, persistence isolation, cancellation/retry, report evidence, responsive layouts, focus and settings passed.')
    console.log('Reports flow:', reportChecks.checks.length + reportChecks.mocked.length, 'mocked report requests,', mobileChecks.length, 'mobile assertions passed.')
  } finally { await browser?.close(); const survivors = await stopChildren(children); if (survivors.length) throw new Error('This test left a server process running') }
}
main().catch(error => {
  console.error(error)
  // A failing run must leave the same record shape its consumer reads, naming the first failed assertion.
  try { fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({ result: 'FAIL', failure: error && error.message ? error.message : String(error), at: new Date().toISOString() }, null, 2)) } catch {}
  process.exitCode = 1
})
