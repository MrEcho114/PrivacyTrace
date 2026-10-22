// Issue #143 browser regression: the wide-viewport hierarchy of the existing
// workbench and report viewer. It reuses the real Vue pages and the same
// deterministic API fixtures as the other browser checks; it does not scan an
// APK or contact a model.
const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawn, execFileSync } = require('node:child_process')
const { stopChildren, spawnOptions } = require('./lib/process-control.cjs')
const { resolvePort } = require('./lib/local-ports.cjs')

const root = path.resolve(__dirname, '..')
const output = path.join(root, 'tmp/issue143-hierarchy')
const screenshots = path.join(output, 'screenshots')
fs.mkdirSync(screenshots, { recursive: true })
const widths = [[1920, 1080], [1440, 900], [1280, 720]]

const policySentence = '我们会收集设备位置信息，用于附近门店推荐。'
const longPackage = 'com.example.privacytrace.hierarchy.' + 'nested.'.repeat(14) + 'longpackage'
const longUrl = 'https://example.com/' + 'policy-segment/'.repeat(24) + 'privacy.html'
const succeededJob = {
  id: 'job-143-hierarchy',
  sample_id: 'sample-143-hierarchy',
  input_mode: 'APK',
  source_origin: 'REAL_SCAN',
  state: 'SUCCEEDED',
  ruleset_version: 'ruleset-143-hierarchy',
  created_at: '2026-10-21T08:00:00Z',
  package_name: longPackage,
  version_code: 143,
  error: null,
}
const reportFixture = {
  sample: {
    name: '超长包名报告摘要示例',
    package_name: longPackage,
    version_name: '1.4.3',
    version_code: 143,
    apk_sha256: 'd'.repeat(64),
    permissions: ['android.permission.ACCESS_FINE_LOCATION'],
    dex_entries: ['classes.dex'],
  },
  job: succeededJob,
  delivery_mode: 'PERSISTED_REPLAY',
  result: {
    job_id: succeededJob.id,
    ruleset_version: 'ruleset-143-hierarchy',
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
        requires_review: false,
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
      api_call: {
        target_descriptor: 'android.location.LocationManager#requestLocationUpdates',
        rule_id: 'rule-location',
        ruleset_version: 'ruleset-143-hierarchy',
        context: { receiver: 'UNKNOWN', purpose: 'UNKNOWN', temporal_scope: 'UNKNOWN' },
      },
    },
    {
      id: 'ev-api-device',
      kind: 'API',
      status: 'STATIC_POTENTIAL',
      source: 'classes.dex',
      locator: 'Lcom/example/MainActivity;->readAndroidId()Ljava/lang/String;',
      excerpt: 'Settings.Secure.getString(cr, ANDROID_ID)',
      document_id: null,
    },
    {
      id: 'ev-sentence-location',
      kind: 'POLICY_SENTENCE',
      status: 'DECLARED',
      source: '官网隐私政策',
      locator: '第 1 段第 1 句',
      document_id: 'doc-web-1',
      start_offset: 0,
      end_offset: policySentence.length,
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
      title: '超长来源名称示例 · ' + '政策附件与适用范围'.repeat(5),
      version: '2026-10',
      captured_at: '2026-10-21T07:00:00Z',
      artifact: { text: policySentence, sha256: 'e'.repeat(64), normalization: 'NONE' },
      completeness: 'PARTIAL',
      extraction_status: 'PARTIAL',
      review_status: 'UNREVIEWED',
      attachments_status: 'NOT_CHECKED',
      applicability: { package_name: longPackage, version_codes: [143], regions: ['CN'], product_scope: null },
      evidence_id: 'ev-doc-web-1',
    },
  ],
  policy_claims: [
    {
      id: 'claim-location-1',
      document_id: 'doc-web-1',
      data_type: 'LOCATION',
      action: 'UNKNOWN',
      polarity: 'UNKNOWN',
      subject: 'UNKNOWN',
      condition: null,
      declared_purpose: null,
      declared_recipient: null,
      basis: 'POLICY_DECLARATION',
      ambiguity_flags: ['UNCLEAR_ACTION'],
      evidence_ids: ['ev-sentence-location'],
    },
  ],
  coverage: {
    status: 'PARTIAL',
    scope: 'DEX_ENTRIES',
    behavior_detection: 'LIMITED_RULE_BASED_STATIC',
    behavior_limitations: ['不覆盖反射与动态加载。'],
    limitations: ['未扫描 native 代码。'],
    scanned_dex: ['classes.dex'],
    failed_dex: [],
  },
  tools: {
    report_schema: 'issue143-hierarchy-1',
    analysis_generated_at: '2026-10-21T08:01:00Z',
    ruleset_version: 'ruleset-143-hierarchy',
    web_policy_sources: JSON.stringify([{
      title: '超长来源名称 · ' + '入口页面'.repeat(10),
      status: 'failed',
      error_code: 'FETCH_TIMEOUT',
      captured_at: null,
      sha256: null,
      url: longUrl,
      final_url: null,
      provenance: 'DIRECT_WEB_FETCH',
    }]),
  },
  reviews: [],
}
const demoReportFixture = {
  ...reportFixture,
  demo: true,
  sample: { ...reportFixture.sample, version: reportFixture.sample.version_name, input_mode: 'SYNTHETIC' },
  delivery_mode: 'LIVE_GENERATED',
}
const taxonomyFixture = {
  version: 'taxonomy-issue143',
  data_types: [
    { id: 'LOCATION', label: '位置信息', parent: null },
    { id: 'DEVICE_ID', label: '设备标识', parent: null },
  ],
}
const liveDraft = {
  id: 'a'.repeat(32),
  revision: 2,
  name: '现场材料版本',
  uploaded: true,
  apk_sha256: 'f'.repeat(64),
  sources: [{
    id: 'source-live-1',
    title: '官网政策',
    url: 'https://example.com/privacy',
    source_type: 'OFFICIAL_WEB_POLICY',
    text: policySentence,
    status: 'ready',
    version: '2026-10',
    region: 'CN',
    product: '示例应用',
    provenance: 'DIRECT_WEB_FETCH',
  }],
  candidates: [],
  jobs: [{ job_id: 'job-143-live', request_id: 'r'.repeat(32), revision: 2, events: [{ state: 'INTAKE', at: '2026-10-21T08:00:00Z' }, { state: 'STATIC_ANALYSIS', at: '2026-10-21T08:00:02Z' }] }],
}
const liveJob = {
  id: 'job-143-live',
  sample_id: 'sample-143-live',
  input_mode: 'APK',
  source_origin: 'REAL_SCAN',
  state: 'STATIC_ANALYSIS',
  ruleset_version: 'ruleset-143-hierarchy',
  created_at: '2026-10-21T08:00:00Z',
  package_name: 'com.example.live',
  version_code: 1,
  error: null,
}

async function ready(origin, child, log) {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error(log())
    try { if ((await fetch(origin)).ok) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  throw new Error('Frontend startup timed out: ' + log())
}

async function fontsReady(page) {
  await page.evaluate(() => document.fonts.ready)
}

async function captureWidths(page, name, options = {}) {
  const captured = []
  for (const [width, height] of widths) {
    await page.setViewportSize({ width, height })
    await fontsReady(page)
    assert.equal(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, `${name} overflows at ${width}`)
    // Round 2 keeps the 36px desktop action contract: a mobile 44/48px touch
    // rule that leaks into the wide viewport would change this computed value.
    const control = await page.evaluate(() => {
      const button = document.querySelector('.ui-button')
      return button ? getComputedStyle(button).minHeight : ''
    })
    assert.equal(control, '36px', `${name}: wide viewports keep the 36px button contract at ${width}px (got ${control || 'no .ui-button'})`)
    if (options.focus) {
      await page.evaluate(selector => document.querySelector(selector)?.scrollIntoView({ block: 'start' }), options.focus)
    } else {
      await page.evaluate(() => window.scrollTo(0, 0))
    }
    const file = path.join(screenshots, `${name}-${width}.png`)
    await page.screenshot({ path: file })
    captured.push(path.relative(root, file).replaceAll('\\', '/'))
  }
  await page.setViewportSize({ width: 1440, height: 900 })
  return captured
}

async function openExample(page, origin) {
  await page.goto(origin)
  await page.getByRole('heading', { name: 'APK 与政策材料', exact: true }).waitFor({ timeout: 15000 })
  await fontsReady(page)
  await page.getByRole('button', { name: '体验示例', exact: true }).click()
  await page.getByRole('heading', { name: 'APK 与政策材料', exact: true }).waitFor()
}

async function main() {
  // The old fixed 5189 lands inside the Windows Hyper-V/WinNAT reserved range,
  // so allocate a bindable port unless an externally served frontend is chosen.
  const port = process.env.PRIVACYTRACE_FRONTEND_URL ? undefined : await resolvePort('PRIVACYTRACE_WEB_PORT')
  const origin = process.env.PRIVACYTRACE_FRONTEND_URL || `http://127.0.0.1:${port}`
  const children = []
  let browser
  const checks = []
  try {
    if (!process.env.PRIVACYTRACE_FRONTEND_URL) {
      const child = spawn('npm run dev', spawnOptions(root, { PRIVACYTRACE_WEB_PORT: String(port) }))
      children.push(child)
      let serverLog = ''
      child.stdout.on('data', chunk => { serverLog += chunk })
      child.stderr.on('data', chunk => { serverLog += chunk })
      await ready(origin, child, () => serverLog)
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const evidence = { screenshots: [], checks }

    // 1. Example flow: import, candidates, progress, report.
    const example = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const errors = []
    example.on('pageerror', error => errors.push(error.message))
    await openExample(example, origin)

    // Import keeps the APK action reachable beside a long file name and shows
    // the completeness/review boundary next to every source.
    await example.locator('input[accept=".apk"]').setInputFiles({
      name: 'paperboat-' + 'very-long-sample-name-'.repeat(8) + '.apk',
      mimeType: 'application/octet-stream',
      buffer: Buffer.from('synthetic name only; not uploaded'),
    })
    const importState = await example.evaluate(() => {
      const drop = document.querySelector('.file-drop')
      const name = drop?.querySelector('strong')
      const action = drop?.querySelector('.ui-button')
      const notes = Array.from(document.querySelectorAll('.source-editor .source-notes')).map(node => node.textContent || '')
      const rect = drop?.getBoundingClientRect()
      return {
        nameFits: !!name && !!drop && name.scrollWidth <= drop.clientWidth + 1,
        actionVisible: !!action && action.getBoundingClientRect().width > 0 && (!rect || action.getBoundingClientRect().top < rect.bottom),
        notes,
      }
    })
    assert.equal(importState.nameFits, true, 'import: a long APK name must wrap inside the drop zone')
    assert.equal(importState.actionVisible, true, 'import: the select-APK action must stay visible under a long file name')
    assert.ok(importState.notes.length >= 1, 'import: every source needs a visible completeness/review note')
    for (const note of importState.notes) {
      for (const text of ['正文完整度未知', '来源未复核', '附件未检查', '适用范围不明']) {
        assert.ok(note.includes(text), `import: source notes missing ${text}`)
      }
    }
    checks.push('import: long APK name keeps its action; source notes carry completeness/review/attachment state')
    evidence.screenshots.push(...await captureWidths(example, 'example-import'))
    checks.push('wide desktop: 1920/1440/1280 keep the 36px action contract; no mobile touch rule leaks in')

    // Candidates: one persistent source context strip above both panels.
    await example.getByRole('button', { name: '检查候选', exact: true }).click()
    await example.getByRole('heading', { name: '核对政策声明', exact: true }).waitFor()
    const contextText = await example.locator('[data-testid="candidate-source-context"]').innerText()
    for (const text of ['官网政策', '示例 1.0', '正文完整度未知', '来源未复核', '附件未检查', '适用范围不明']) {
      assert.ok(contextText.includes(text), `candidates: source context missing ${text}`)
    }
    assert.equal(contextText.includes('纸舟地图隐私政策'), false, 'candidates: the source title stays in the tab row, not repeated in the context strip')
    assert.equal(await example.locator('.source-tabs').getByText('纸舟地图隐私政策', { exact: false }).count(), 1, 'candidates: the source tab keeps the selected source title')
    assert.equal(await example.locator('[data-testid="candidate-source-context"]').isVisible(), true, 'candidates: source context must stay visible')
    assert.equal(await example.locator('#panel-original p.field-help').filter({ hasText: '纸舟地图隐私政策' }).count(), 0, 'candidates: the source identity must not be repeated inside the reading panel')
    checks.push('candidates: one source identity and one compact context strip replace the repeated panel header')
    evidence.screenshots.push(...await captureWidths(example, 'example-candidates'))

    // Progress: the current-stage card aligns to the top of the rail and keeps
    // a discrete stage count instead of a percentage or ETA.
    await example.getByRole('button', { name: '进入流程演示', exact: true }).click()
    await example.getByRole('heading', { name: '扫描与对照进度', exact: true }).waitFor()
    const progressState = await example.evaluate(() => {
      const panel = document.querySelector('.progress-panel')
      const preview = document.querySelector('.stage-preview')
      if (!panel || !preview) return { top: 999, text: '' }
      const first = preview.firstElementChild
      return {
        top: first ? first.getBoundingClientRect().top - preview.getBoundingClientRect().top : 999,
        text: preview.textContent || '',
      }
    })
    assert.ok(progressState.top <= 32, `progress: current-stage content must align to the panel top (got ${progressState.top}px)`)
    assert.match(progressState.text, /阶段 1 \/ 5/, 'progress: the discrete stage count must be visible')
    assert.equal(/ETA|预计|%/.test(progressState.text), false, 'progress: no percentage or ETA may be invented')
    checks.push('progress: stage card is top-aligned and carries the discrete stage count only')
    evidence.screenshots.push(...await captureWidths(example, 'example-progress'))

    for (let index = 0; index < 4; index++) {
      await example.getByRole('button', { name: '进入下一阶段', exact: true }).click()
    }
    await example.getByRole('button', { name: '完成当前阶段', exact: true }).click()
    await example.getByRole('button', { name: '查看报告', exact: true }).click()
    await example.getByRole('heading', { name: 'APP 隐私收集越权报告', exact: true }).waitFor()
    // #165: the per-source summary grid was replaced by one collapsed fact list
    // inside the evidence region. Open it and assert one row per source, each
    // carrying the unified #167 source-state line, while material identity rows
    // stay separate facts. The evidence region itself is permanent and unique.
    await example.locator('.report-info > summary').click()
    const sourceTitles = ['纸舟地图隐私政策', '云点统计服务说明']
    const infoState = await example.evaluate(titles => {
      const details = document.querySelector('.report-info')
      const rows = details ? Array.from(details.querySelectorAll('dl > div')) : []
      const titleOf = row => row.querySelector('dt')?.textContent?.trim() ?? ''
      const sourceRows = rows.filter(row => titles.includes(titleOf(row)))
      return {
        open: Boolean(details?.open),
        rows: rows.length,
        sourceRows: sourceRows.length,
        stateLines: sourceRows.map(row => row.querySelector('dd')?.textContent?.trim() ?? ''),
        materialRows: rows.filter(row => ['材料', '应用包名'].includes(titleOf(row))).length,
      }
    }, sourceTitles)
    assert.equal(infoState.open, true, 'report: the source fact list must open on demand')
    assert.equal(infoState.sourceRows, 2, 'report: the collapsed fact list keeps one row per policy source')
    assert.equal(infoState.materialRows, 1, 'report: only the package identity row remains; the duplicate 材料 row is gone')
    assert.equal(await example.locator('.report-info').getByText('人工构造示例').count(), 0, 'report: the retired 人工构造示例 marker must not return')
    assert.ok(infoState.stateLines.every(line => line.includes('来源未复核')), 'report: every source row keeps the unified 来源未复核 state line')
    await example.locator('.comparison-table tbody tr').first().getByRole('button').first().click()
    await example.locator('#example-evidence-title').waitFor()
    assert.equal(await example.locator('#example-evidence').isVisible(), true, 'report: evidence drill-down stays explicit')
    assert.equal(await example.locator('#example-evidence').count(), 1, 'report: exactly one permanent evidence region')
    assert.equal(await example.locator('.report-columns').getAttribute('data-layout'), 'columns', 'report: 1440px keeps the columns layout')
    checks.push('report: one collapsed source fact list, unified state per source and the explicit evidence region')
    evidence.screenshots.push(...await captureWidths(example, 'example-report'))

    // 2. Real/persisted report viewer with long package name, URL and hash.
    const reports = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    reports.on('pageerror', error => errors.push(error.message))
    await reports.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomyFixture }))
    await reports.route('**/api/v1/demo/report', route => route.fulfill({ json: demoReportFixture }))
    await reports.route('**/api/v1/jobs/*/report', route => route.fulfill({ json: reportFixture }))
    await reports.route('**/api/v1/jobs', route => route.fulfill({ json: { jobs: [succeededJob] } }))
    await reports.route('**/api/v1/jobs/*', route => route.fulfill({ json: succeededJob }))
    await reports.goto(origin + '/#reports')
    await reports.locator('.report-table tbody tr').first().waitFor({ timeout: 15000 })
    await fontsReady(reports)
    assert.equal(await reports.locator('#page-title').innerText(), '本机存档报告')
    // #167/#165 embedded mode: the archive view owns the only h1 and brand bar,
    // so App.vue must not render its own .intro hero or .topbar inside it.
    assert.equal(await reports.locator('.workspace-content .shell .intro').count(), 0, 'reports: the embedded viewer must not render a second hero')
    assert.equal(await reports.locator('.workspace-content .shell h1').count(), 0, 'reports: the embedded viewer must not render a second page title')
    assert.equal(await reports.locator('.workspace-content .shell > header.topbar').count(), 0, 'reports: the embedded viewer must not render a second top bar')
    assert.equal(await reports.locator('.workspace-content .shell .topbar').count(), 0, 'reports: the embedded viewer must not render a second brand bar')
    assert.equal(await reports.locator('.workspace-content h1').count(), 1, 'reports: the workbench page title must be the only h1')

    const styleState = await reports.evaluate(() => {
      const root = getComputedStyle(document.documentElement)
      const role = name => root.getPropertyValue(name).trim().toLowerCase()
      const rgb = hex => `rgb(${[1, 3, 5].map(offset => parseInt(hex.slice(offset, offset + 2), 16)).join(', ')})`
      const style = selector => {
        const element = document.querySelector(selector)
        return element ? getComputedStyle(element) : null
      }
      const sample = document.querySelector('.sample-card')
      const provenance = document.querySelector('.report-provenance')
      const table = document.querySelector('.report-table')
      const firstEvidence = document.querySelector('.report-table tbody tr .evidence-button')
      const select = document.querySelector('#report-source')
      const refresh = document.querySelector('.report-source-bar > .ui-button')
      const metrics = document.querySelector('.metrics')
      const tableRect = table?.getBoundingClientRect()
      const evidenceRect = firstEvidence?.getBoundingClientRect()
      return {
        roles: { surface: rgb(role('--surface')), mint: rgb(role('--mint')), notice: rgb(role('--notice')), canvas: rgb(role('--canvas')), control: rgb(role('--control')) },
        identityBeforeMeta: !!sample && !!provenance && !!(sample.compareDocumentPosition(provenance) & Node.DOCUMENT_POSITION_FOLLOWING),
        introCount: document.querySelectorAll('.workspace-content .shell .intro').length,
        embeddedMainCount: document.querySelectorAll('.workspace-content .shell main').length,
        embeddedHeadingCount: document.querySelectorAll('.workspace-content .shell h1').length,
        topbarCount: document.querySelectorAll('.workspace-content .shell .topbar').length,
        h1Count: document.querySelectorAll('.workspace-content h1').length,
        sourceBar: !!select?.closest('.report-source-bar'),
        refreshHeight: refresh ? Math.round(refresh.getBoundingClientRect().height) : 0,
        sectionBackground: style('.report-section')?.backgroundColor || '',
        sectionHeadingSize: style('.report-section h2')?.fontSize || '',
        clearBackground: style('.tag.clear')?.backgroundColor || '',
        reviewBackground: style('.tag.review')?.backgroundColor || '',
        headerBackground: style('.report-table th')?.backgroundColor || '',
        selectBorder: select ? getComputedStyle(select).borderTopColor : '',
        metricsColumns: metrics ? getComputedStyle(metrics).gridTemplateColumns.split(' ').filter(Boolean).length : 0,
        evidenceInside: !!tableRect && !!evidenceRect && evidenceRect.right <= tableRect.right + 1,
        overflow: document.documentElement.scrollWidth <= window.innerWidth,
      }
    })
    assert.equal(styleState.identityBeforeMeta, true, 'reports: report identity must precede archive/job metadata')
    assert.equal(styleState.introCount, 0, 'reports: embedded mode must not render the viewer hero at all')
    assert.equal(styleState.topbarCount, 0, 'reports: embedded mode must not render a second brand bar')
    assert.equal(styleState.h1Count, 1, 'reports: embedded mode keeps exactly one h1')
    assert.equal(styleState.sourceBar, true, 'reports: source selection and refresh share one toolbar')
    assert.equal(styleState.refreshHeight >= 34 && styleState.refreshHeight <= 40, true, `reports: refresh must use the 36px action contract (got ${styleState.refreshHeight}px)`)
    assert.equal(styleState.sectionBackground, styleState.roles.surface, 'reports: report panels must consume the Pioneer surface role')
    assert.equal(styleState.sectionHeadingSize, '16px', 'reports: report panel headings must share the workbench scale')
    assert.equal(styleState.clearBackground, styleState.roles.mint, 'reports: declared status must use the mint role')
    assert.equal(styleState.reviewBackground, styleState.roles.notice, 'reports: review status must use the notice role')
    assert.equal(styleState.headerBackground, styleState.roles.canvas, 'reports: table headers must use the canvas role')
    assert.equal(styleState.selectBorder, styleState.roles.control, 'reports: the source select must use the control border role')
    assert.equal(styleState.metricsColumns, 3, 'reports: the three metrics must share one summary strip')
    assert.equal(styleState.evidenceInside, true, 'reports: a long locator must not push the evidence action out of the table')
    assert.equal(styleState.overflow, true, 'reports: long package names, URLs and hashes must not overflow the page')
    checks.push('reports: identity precedes metadata; toolbar, panel scale, status roles, metrics and long-text bounds hold')
    evidence.screenshots.push(...await captureWidths(reports, 'reports'))

    // Open the evidence panel to prove the drill-down hierarchy still works.
    await reports.locator('.report-table tbody tr .evidence-button').first().click()
    await reports.locator('#evidence-panel').waitFor()
    assert.equal(await reports.locator('#evidence-panel .section-heading h2').isVisible(), true)
    assert.equal(await reports.locator('#evidence-panel .policy-jump-btn').first().isVisible(), true)
    checks.push('reports: code/policy evidence drill-down and full-text jump remain reachable')
    evidence.screenshots.push(...await captureWidths(reports, 'reports-evidence', { focus: '#evidence-panel' }))

    // 3. Real progress template (mocked draft + running job, no Docker/model).
    const live = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    live.on('pageerror', error => errors.push(error.message))
    live.on('request', request => {
      if (request.url().includes('/api/v1/web/drafts/') && request.method() === 'POST') throw new Error('The live progress fixture must be read-only')
    })
    await live.addInitScript(id => localStorage.setItem('privacytrace.live.draft.v1', id), liveDraft.id)
    await live.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomyFixture }))
    await live.route('**/api/v1/web/drafts/*', route => route.fulfill({ json: liveDraft }))
    await live.route('**/api/v1/jobs/*', route => route.fulfill({ json: liveJob }))
    await live.goto(origin)
    await live.getByRole('heading', { name: '扫描与对照进度', exact: true }).waitFor({ timeout: 15000 })
    await fontsReady(live)
    assert.equal(await live.locator('.material-panel .page-heading').count(), 0, 'live progress: the page heading must sit outside the material panel')
    assert.equal(await live.locator('.progress-summary').filter({ hasText: '隔离扫描' }).count(), 1, 'live progress: the real discrete state must stay visible')
    assert.equal(await live.locator('.progress-summary .hash').innerText(), liveJob.id, 'live progress: the job id stays readable as evidence')
    assert.equal(await live.locator('.stage-list li').count(), 2, 'live progress: recorded events keep their timeline')
    assert.equal(await live.getByRole('button', { name: '取消分析', exact: true }).isVisible(), true, 'live progress: cancel stays reachable')
    assert.equal(await live.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), true, 'live progress: no horizontal overflow')
    // The real view intentionally focuses the page heading for keyboard users;
    // the screenshot records the resting hierarchy rather than the focus ring.
    await live.evaluate(() => { if (document.activeElement instanceof HTMLElement) document.activeElement.blur() })
    checks.push('live progress: heading, discrete state, job id, event timeline and cancel action stay in hierarchy')
    evidence.screenshots.push(...await captureWidths(live, 'live-progress'))

    // The report step keeps the same material-version action reachable under
    // the page heading after a finished live job.
    const liveReport = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    liveReport.on('pageerror', error => errors.push(error.message))
    await liveReport.addInitScript(id => localStorage.setItem('privacytrace.live.draft.v1', id), liveDraft.id)
    await liveReport.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomyFixture }))
    await liveReport.route('**/api/v1/demo/report', route => route.fulfill({ json: demoReportFixture }))
    await liveReport.route('**/api/v1/web/drafts/*', route => route.fulfill({ json: {
      ...liveDraft,
      jobs: [{ ...liveDraft.jobs[0], events: [...liveDraft.jobs[0].events, { state: 'SUCCEEDED', at: '2026-10-21T08:00:05Z' }] }],
    } }))
    await liveReport.route('**/api/v1/jobs/*/report', route => route.fulfill({ json: reportFixture }))
    await liveReport.route('**/api/v1/jobs', route => route.fulfill({ json: { jobs: [{ ...liveJob, state: 'SUCCEEDED' }] } }))
    await liveReport.route('**/api/v1/jobs/*', route => route.fulfill({ json: { ...liveJob, state: 'SUCCEEDED' } }))
    await liveReport.goto(origin)
    await liveReport.getByRole('heading', { name: '扫描与对照进度', exact: true }).waitFor({ timeout: 15000 })
    await liveReport.getByRole('button', { name: '查看报告', exact: true }).click()
    await liveReport.getByRole('heading', { name: 'APP 隐私收集越权报告', exact: true }).waitFor()
    await liveReport.locator('.report-table tbody tr').first().waitFor({ timeout: 15000 })
    assert.equal(await liveReport.locator('.report-table tbody tr').first().isVisible(), true, 'live report: the saved report table stays visible')
    assert.equal(await liveReport.getByRole('button', { name: '新建材料版本', exact: true }).isVisible(), true, 'live report: the material-version action stays reachable after a finished job')
    checks.push('live report: page identity precedes the material-version action and the saved report stays readable')
    evidence.screenshots.push(...await captureWidths(liveReport, 'live-report'))

    // 4. Read-only offline package entry: same viewer, injected presentation
    // meta and saved-report endpoints, no workbench shell.
    const offline = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    offline.on('pageerror', error => errors.push(error.message))
    await offline.route(origin + '/', async route => {
      const response = await route.fetch()
      const body = (await response.text()).replace('<head>', '<head><meta name="privacytrace-presentation" content="offline">')
      await route.fulfill({ response, body })
    })
    await offline.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomyFixture }))
    await offline.route('**/api/v1/demo/report', route => route.fulfill({ json: demoReportFixture }))
    await offline.route('**/api/v1/jobs/*/report', route => route.fulfill({ json: {
      ...reportFixture,
      tools: { ...reportFixture.tools, presentation_mode: 'OFFLINE_REPLAY', offline_package_built_at: '2026-10-21T08:02:00Z' },
    } }))
    await offline.route('**/api/v1/jobs', route => route.fulfill({ json: { jobs: [succeededJob] } }))
    await offline.route('**/api/v1/jobs/*', route => route.fulfill({ json: succeededJob }))
    await offline.goto(origin)
    await offline.getByText('OFFLINE REPLAY · 离线回放').waitFor({ timeout: 15000 })
    await offline.locator('.report-table tbody tr').first().waitFor()
    assert.equal(await offline.locator('.workbench').count(), 0, 'offline: the read-only package must not mount the workbench shell')
    assert.equal(await offline.locator('#report-source').isVisible(), true, 'offline: saved-report selection stays reachable')
    assert.equal(await offline.locator('.sample-card .badge.persisted_replay').isVisible(), true, 'offline: the persisted-replay delivery badge stays visible')
    // #169 offline top bar: same-origin brand symbol in .topbar .brand-icon, no
    // letter placeholder. The symbol request must return real SVG markup.
    const offlineBrand = await offline.evaluate(async () => {
      const slot = document.querySelector('.topbar .brand-icon')
      const image = slot?.querySelector('img.brand-mark-image')
      if (!image) return null
      let decoded = false
      try { await image.decode(); decoded = true } catch {}
      const rect = image.getBoundingClientRect()
      const slotRect = slot.getBoundingClientRect()
      return {
        complete: image.complete, currentSrc: image.currentSrc,
        naturalWidth: image.naturalWidth, naturalHeight: image.naturalHeight,
        width: Math.round(rect.width), height: Math.round(rect.height),
        slotWidth: Math.round(slotRect.width), slotHeight: Math.round(slotRect.height),
        slotText: (slot.textContent || '').trim(), decoded,
      }
    })
    assert.ok(offlineBrand, 'offline: the top bar must render the brand icon slot')
    assert.equal(offlineBrand.complete, true, 'offline: the brand image must finish loading')
    assert.ok(offlineBrand.currentSrc.endsWith('/brand/privacy-trace-symbol.svg'), `offline: the brand image resolves the same-origin symbol (got ${offlineBrand.currentSrc})`)
    assert.ok(offlineBrand.naturalWidth > 0 && offlineBrand.naturalHeight > 0, 'offline: the brand image must decode to real pixels')
    assert.ok(offlineBrand.width > 0 && offlineBrand.height > 0, 'offline: the brand icon renders a positive box')
    assert.equal(offlineBrand.slotText, '', 'offline: the brand slot must not keep a letter placeholder')
    assert.equal(offlineBrand.decoded, true, 'offline: brand img.decode() must resolve')
    const offlineSymbol = await offline.request.get(origin + '/brand/privacy-trace-symbol.svg')
    assert.equal(offlineSymbol.status(), 200, 'offline: the same-origin brand symbol must return 200')
    assert.ok((await offlineSymbol.body()).toString('utf8').includes('<svg'), 'offline: the brand symbol must be SVG markup')
    checks.push('offline: single top bar with the same-origin brand symbol and no letter placeholder')
    checks.push('offline: the injected read-only package mounts the existing report viewer without the workbench shell')
    evidence.screenshots.push(...await captureWidths(offline, 'offline-reports'))

    assert.deepEqual(errors, [], 'no page errors may be raised by the hierarchy changes')
    const result = {
      result: 'PASS',
      captured_at: new Date().toISOString(),
      commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', cwd: root }).trim(),
      dirty: !!execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8', cwd: root }).trim(),
      scope: 'synthetic example flow + mocked persisted report + mocked live draft; no real scan, model or Docker',
      widths: widths.map(([width, height]) => `${width}x${height}`),
      checks,
      screenshots: evidence.screenshots,
      errors,
    }
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(result, null, 2))
    console.log('Issue #143 hierarchy checks passed:', checks.length)
    for (const check of checks) console.log(' -', check)
  } finally {
    await browser?.close()
    const survivors = await stopChildren(children)
    if (survivors.length) throw new Error('This test left a server process running')
  }
}

main().catch(error => {
  console.error(error)
  try {
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({
      result: 'FAIL',
      failure: error && error.message ? error.message : String(error),
      at: new Date().toISOString(),
    }, null, 2))
  } catch {}
  process.exitCode = 1
})
