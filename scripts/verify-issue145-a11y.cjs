const { chromium } = require('playwright')
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const { spawn, execFileSync } = require('node:child_process')
const { stopChildren, spawnOptions } = require('./lib/process-control.cjs')

const output = path.resolve('tmp/issue145-a11y')
fs.mkdirSync(path.join(output, 'screenshots'), { recursive: true })
const checkpoint = message => console.log('[issue145]', message)

const policySentence = '我们会收集设备位置信息，用于附近门店推荐。'
const runningJob = {
  id: 'job-running', sample_id: 'sample-running', input_mode: 'APK', source_origin: 'REAL_SCAN',
  state: 'STATIC_ANALYSIS', ruleset_version: 'ruleset-issue145', created_at: '2026-10-21T08:00:00Z',
  package_name: 'com.example.running', version_code: 8, error: null,
}
const failedJob = {
  id: 'job-a11y-failed', sample_id: 'sample-a11y-failed', input_mode: 'APK', source_origin: 'REAL_SCAN',
  state: 'FAILED', ruleset_version: 'ruleset-issue145', created_at: '2026-10-21T08:05:00Z',
  package_name: 'com.example.failed', version_code: 7,
  error: JSON.stringify({ code: 'DEX_UNSUPPORTED', message: 'DEX 解析中断，未生成报告。', primary_error: 'unsupported dex version 041' }),
}
const succeededJob = {
  id: 'job-a11y-succeeded', sample_id: 'sample-a11y-succeeded', input_mode: 'APK', source_origin: 'REAL_SCAN',
  state: 'SUCCEEDED', ruleset_version: 'ruleset-issue145', created_at: '2026-10-21T08:10:00Z',
  package_name: 'com.example.ok', version_code: 7, error: null,
}
const taxonomy = { version: 'taxonomy-issue145', data_types: [{ id: 'LOCATION', label: '位置信息', parent: null }, { id: 'DEVICE_ID', label: '设备标识', parent: null }] }
const report = {
  sample: { name: '无障碍验收示例', package_name: 'com.example.ok', version_name: '1.0.7', version_code: 7, apk_sha256: 'a'.repeat(64), permissions: ['android.permission.ACCESS_FINE_LOCATION'], dex_entries: ['classes.dex'] },
  job: succeededJob, delivery_mode: 'PERSISTED_REPLAY',
  result: { job_id: succeededJob.id, ruleset_version: 'ruleset-issue145', issues: [
    { id: 'issue-location', behavior_id: 'beh-location', data_type: 'LOCATION', status: 'EXACT_MATCH', evidence_status: 'STATIC_POTENTIAL', policy_document_ids: ['doc-web-1'], evidence_ids: ['ev-api-location', 'ev-sentence-location'], explanation: '官网政策按具体类型声明了位置信息，但目的与时间范围没有写清。', scope: 'DATA_TYPE_DISCLOSURE', requires_review: true },
    { id: 'issue-device', behavior_id: 'beh-device', data_type: 'DEVICE_ID', status: 'NOT_DECLARED', evidence_status: 'STATIC_POTENTIAL', policy_document_ids: [], evidence_ids: ['ev-api-device'], explanation: '政策快照中没有设备标识的对应条款。', scope: 'DATA_TYPE_DISCLOSURE', requires_review: true },
  ] },
  evidence: [
    { id: 'ev-api-location', kind: 'API', status: 'STATIC_POTENTIAL', source: 'classes.dex', locator: 'Lcom/example/MainActivity;->requestLocation()V', excerpt: 'LocationManager.requestLocationUpdates(...)', document_id: null, api_call: { target_descriptor: 'android.location.LocationManager#requestLocationUpdates', rule_id: 'rule-location', ruleset_version: 'r', context: { receiver: 'UNKNOWN' } } },
    { id: 'ev-api-device', kind: 'API', status: 'STATIC_POTENTIAL', source: 'classes.dex', locator: 'Lcom/example/MainActivity;->readAndroidId()V', excerpt: 'Settings.Secure.getString(cr, ANDROID_ID)', document_id: null, api_call: { target_descriptor: 'android.provider.Settings$Secure#getString', rule_id: 'rule-device', ruleset_version: 'r', context: {} } },
    { id: 'ev-sentence-location', kind: 'POLICY_SENTENCE', status: 'DECLARED', source: '官网隐私政策', locator: '第 1 段第 1 句', document_id: 'doc-web-1', start_offset: 0, end_offset: 10, excerpt: policySentence },
  ],
  behaviors: [
    { id: 'beh-location', data_type: 'LOCATION', action: 'ACCESS', purpose: 'UNKNOWN', recipient: 'UNKNOWN', transfer: 'UNKNOWN', temporal_scope: 'UNKNOWN', evidence_ids: ['ev-api-location'] },
    { id: 'beh-device', data_type: 'DEVICE_ID', action: 'CAPABILITY', evidence_ids: ['ev-api-device'] },
  ],
  policy_documents: [{ id: 'doc-web-1', source_type: 'OFFICIAL_WEB_POLICY', title: '验收示例官网政策', version: '2026-10', captured_at: '2026-10-21T07:00:00Z', artifact: { text: policySentence, sha256: 'b'.repeat(64), normalization: 'NONE' }, completeness: 'PARTIAL', extraction_status: 'PARTIAL', review_status: 'UNREVIEWED', attachments_status: 'NOT_CHECKED', applicability: {}, evidence_id: 'ev-doc-web-1' }],
  policy_claims: [], coverage: { status: 'PARTIAL', scope: 'DEX_ENTRIES', behavior_detection: 'LIMITED_RULE_BASED_STATIC', behavior_limitations: [], limitations: [], scanned_dex: ['classes.dex'], failed_dex: [] },
  tools: { report_schema: 'issue145', analysis_generated_at: '2026-10-21T08:11:00Z', ruleset_version: 'r', web_policy_sources: JSON.stringify([{ title: '示例官网政策', status: 'failed', error_code: 'FETCH_FAILED', url: 'https://example.com/privacy' }]) }, reviews: [],
}
const demoReport = { ...report, demo: true, sample: { ...report.sample, version: report.sample.version_name, input_mode: 'SYNTHETIC' }, delivery_mode: 'LIVE_GENERATED' }
const contrast = (a, b) => {
  const parse = value => {
    const rgb = /rgba?\(([^)]+)\)/.exec(value)
    if (rgb) return rgb[1].split(',').slice(0, 3).map(part => Number(part.trim()) / 255)
    const hex = value.trim().replace('#', '')
    const full = hex.length === 3 ? hex.split('').map(c => c + c).join('') : hex
    return full.match(/../g).map(part => parseInt(part, 16) / 255)
  }
  const luminance = value => parse(value).map(v => v <= 0.03928 ? v / 12.92 : Math.pow((v + 0.055) / 1.055, 2.4)).reduce((sum, v, i) => sum + v * [0.2126, 0.7152, 0.0722][i], 0)
  const l1 = luminance(a), l2 = luminance(b)
  return Math.round(((Math.max(l1, l2) + 0.05) / (Math.min(l1, l2) + 0.05)) * 100) / 100
}
const liveRegions = page => page.evaluate(() => Array.from(document.querySelectorAll('[role="status"],[role="alert"],[aria-live]')).map(element => ({
  role: element.getAttribute('role'),
  live: element.getAttribute('aria-live'),
  text: (element.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 160),
  interactive: Array.from(element.querySelectorAll('button,a,input,select,textarea,[role="button"],[tabindex]:not([tabindex="-1"])')).map(item => item.textContent?.trim() || item.tagName),
})))
const active = page => page.evaluate(() => {
  const element = document.activeElement
  return element ? { tag: element.tagName, id: element.id, cls: String(element.className).slice(0, 80), testid: element.getAttribute('data-testid'), text: (element.innerText || element.value || '').replace(/\s+/g, ' ').trim().slice(0, 80) } : null
})
async function waitFor(check, message, timeout = 8000) {
  const deadline = Date.now() + timeout
  while (Date.now() < deadline) {
    if (await check()) return
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  assert.fail(message)
}
function assertNoInteractiveLive(regions, label) {
  const bad = regions.filter(region => region.interactive.length)
  assert.deepEqual(bad, [], label + ': live regions must not contain interactive controls: ' + JSON.stringify(bad))
}

async function main() {
  const port = Number(process.env.PRIVACYTRACE_WEB_PORT || 5184)
  if (!Number.isInteger(port) || port < 1 || port > 65535) throw new Error('Invalid PRIVACYTRACE_WEB_PORT')
  const origin = process.env.PRIVACYTRACE_FRONTEND_URL || `http://127.0.0.1:${port}`
  const children = []
  let browser
  const checks = []
  const screenshots = path.join(output, 'screenshots')
  try {
    if (!process.env.PRIVACYTRACE_FRONTEND_URL) {
      try { await fetch(origin, { signal: AbortSignal.timeout(1000) }); throw new Error(`Port ${port} is already occupied. Set PRIVACYTRACE_FRONTEND_URL for an explicitly chosen server.`) }
      catch (error) { if (!['TypeError', 'TimeoutError'].includes(error.name)) throw error }
      const child = spawn('npm run dev', spawnOptions(path.resolve(__dirname, '..'), { PRIVACYTRACE_WEB_PORT: String(port) }))
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
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    const errors = []
    page.on('pageerror', error => errors.push(error.message))

    // Mutable fixtures below are the state transitions being verified.
    const deleted = new Set()
    let jobsFail = false
    let holdJobs = true
    let runningState = 'STATIC_ANALYSIS'
    let runningReport = false
    let deleteCalls = 0
    let draftCalls = 0
    const jobsPayload = () => ({ jobs: [runningJob, failedJob, succeededJob].filter(job => !deleted.has(job.id)).map(job => job.id === runningJob.id ? { ...job, state: runningState } : job) })
    const delay = ms => new Promise(resolve => setTimeout(resolve, ms))
    await page.route('**/api/v1/jobs', async route => {
      if (jobsFail) return route.fulfill({ status: 503, body: 'unavailable' })
      if (holdJobs) { holdJobs = false; await delay(900) }
      return route.fulfill({ json: jobsPayload() })
    })
    await page.route('**/api/v1/jobs/job-running', async route => {
      await delay(150)
      return route.fulfill({ json: { ...runningJob, state: runningState } })
    })
    await page.route('**/api/v1/jobs/job-running/report', route => route.fulfill({ json: report }))
    await page.route('**/api/v1/jobs/job-a11y-failed', route => {
      if (route.request().method() === 'DELETE') { deleteCalls += 1; deleted.add(failedJob.id); return route.fulfill({ json: { status: 'deleted', job_id: failedJob.id } }) }
      return route.fulfill({ json: failedJob })
    })
    await page.route('**/api/v1/jobs/job-a11y-failed/report', route => route.fulfill({ status: 404, body: 'missing' }))
    await page.route('**/api/v1/jobs/job-a11y-succeeded', route => route.fulfill({ json: succeededJob }))
    await page.route('**/api/v1/jobs/job-a11y-succeeded/report', route => route.fulfill({ json: report }))
    await page.route('**/api/v1/demo/report', route => route.fulfill({ json: demoReport }))
    await page.route('**/api/v1/taxonomy', route => route.fulfill({ json: taxonomy }))
    await page.route('**/api/v1/health', route => route.fulfill({ json: { status: 'ok' } }))
    await page.route('**/api/v1/web/taxonomy', route => route.fulfill({ json: taxonomy }))
    await page.route('**/api/v1/web/settings', route => route.fulfill({ json: { enabled: false, api_base: '', model: '', key_configured: false, max_apk_bytes: 157286400 } }))
    await page.route('**/api/v1/web/drafts', async route => { draftCalls += 1; await delay(1500); return route.fulfill({ status: 503, body: 'interrupted' }) })

    await page.goto(origin)
    checkpoint('app loaded')
    await page.getByRole('button', { name: '已有报告', exact: true }).click()
    checkpoint('reports view opened')
    await waitFor(async () => page.locator('.state').count().then(count => count > 0), 'reports loading state did not render')
    checkpoint('loading state visible')
    const loadingRegions = await liveRegions(page)
    assertNoInteractiveLive(loadingRegions, 'initial loading')
    assert.ok(loadingRegions.some(region => region.text.includes('正在加载')), 'loading status text must be exposed to assistive technology')
    checks.push('initial loading: role=status text exists and no interactive control sits in a live region')

    await page.locator('.job-state').waitFor({ timeout: 10000 })
    checkpoint('job state visible')
    const stability = { samples: 0, missing: 0 }
    const stopAt = Date.now() + 4200
    while (Date.now() < stopAt) {
      stability.samples += 1
      if (!await page.locator('.job-state').count()) stability.missing += 1
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    assert.equal(stability.missing, 0, 'polling must not unmount the job card between refreshes: ' + JSON.stringify(stability))
    assert.equal(await page.locator('#job-announcement').innerText(), '', 'unchanged polls must not announce a state update')
    checks.push('polling: job card stayed mounted across ' + stability.samples + ' samples and no repeated status announcement')
    checkpoint('polling stability checked')

    await page.locator('.job-state button', { hasText: '取消任务' }).focus()
    runningState = 'FAILED'
    await waitFor(async () => (await page.locator('.job-state').innerText()).includes('分析失败'), 'running job did not reach the failed state')
    assert.ok((await active(page)).cls.includes('job-state'), 'a terminal poll that removes the focused cancel button must focus the job state, got ' + JSON.stringify(await active(page)))
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'reports-failed-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    runningState = 'CANCELLED'
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await waitFor(async () => (await page.locator('.job-state').innerText()).includes('已取消'), 'job state did not become cancelled')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'reports-cancelled-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    checks.push('terminal transition: focus moves from the removed cancel button to the job state')

    runningState = 'EVALUATING'
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await waitFor(async () => (await page.locator('.job-state').innerText()).includes('规则对照'), 'job state did not refresh in place')
    assert.ok((await page.locator('#job-announcement').innerText()).includes('任务状态更新'), 'a real state transition must be announced once')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'reports-running-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    const announced = await page.locator('#job-announcement').innerText()
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await delay(700)
    assert.equal(await page.locator('#job-announcement').innerText(), announced, 're-reading the same state must not repeat the announcement')
    assert.equal((await active(page)).text, '刷新任务与报告', 'an in-place refresh must not move focus to the document body')
    checks.push('state changes: one polite announcement; unchanged refreshes stay silent and keep focus')

    await page.locator('#report-source').selectOption('demo:synthetic')
    await page.locator('.evidence-button').first().waitFor({ timeout: 10000 })
    const aiDisclosure = await page.locator('.ai-disclosure').evaluate(element => {
      const isTransparent = color => !color || color === 'transparent' || /rgba\([^)]*,\s*0\)/.test(color)
      let background = getComputedStyle(element).backgroundColor
      let node = element
      while (isTransparent(background) && node.parentElement) {
        node = node.parentElement
        background = getComputedStyle(node).backgroundColor
      }
      return { color: getComputedStyle(element).color, background: isTransparent(background) ? 'rgb(246, 245, 241)' : background }
    })
    const aiRatio = contrast(aiDisclosure.color, aiDisclosure.background)
    assert.ok(aiRatio >= 4.5, 'AI disclosure text contrast is below 4.5:1: ' + JSON.stringify({ aiDisclosure, aiRatio }))
    checks.push('AI disclosure contrast: ' + aiRatio)
    const triggerText = await page.locator('.evidence-button').first().innerText()
    await page.locator('.evidence-button').first().click()
    assert.equal((await active(page)).id, 'evidence-panel', 'opening evidence must focus the evidence panel')
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'evidence-open-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await delay(700)
    assert.equal(await page.locator('#evidence-panel').count(), 1, 'an in-place refresh must not close the open evidence panel')
    assert.notEqual((await active(page)).tag, 'BODY', 'an in-place refresh must not drop focus to the body')
    await page.getByRole('button', { name: '收起', exact: true }).click()
    assert.equal((await active(page)).text, triggerText, 'closing evidence must return focus to its trigger')
    checks.push('evidence: in-place refresh keeps the panel and reading position; close restores trigger focus')
    checkpoint('evidence focus checked')

    await page.locator('#report-source').selectOption('job:job-a11y-failed')
    await page.getByTestId('delete-job').waitFor({ timeout: 10000 })
    await page.getByTestId('delete-job').focus()
    await page.keyboard.press('Enter')
    assert.equal((await active(page)).testid, 'delete-confirm', 'opening delete confirmation must focus the confirm control')
    assert.equal(await page.locator('.job-delete-confirm').getAttribute('role'), 'group')
    assert.equal(await page.locator('#job-delete-warning').innerText().then(text => text.length > 0), true)
    const describedby = await page.locator('.job-delete-confirm').getAttribute('aria-describedby')
    assert.ok(describedby && await page.locator('#' + describedby).count(), 'delete confirmation must be described by its warning')
    await page.screenshot({ path: path.join(screenshots, 'delete-confirm-focus-1440.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.locator('.job-delete-confirm').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(screenshots, 'delete-confirm-focus-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.keyboard.press('Escape')
    assert.equal(await page.getByTestId('delete-confirm').count(), 0, 'Escape must close delete confirmation')
    assert.equal((await active(page)).testid, 'delete-job', 'closing delete confirmation must return focus to the delete trigger')
    await page.keyboard.press('Enter')
    await page.keyboard.press('Tab')
    assert.equal((await active(page)).text, '取消删除', 'Tab must move from confirm to cancel inside the confirmation group')
    await page.keyboard.press('Enter')
    assert.equal((await active(page)).testid, 'delete-job', 'cancel must return focus to the delete trigger')
    await page.keyboard.press('Enter')
    await page.getByTestId('delete-confirm').click()
    await waitFor(async () => deleteCalls === 1, 'delete request was not sent')
    await waitFor(async () => !(await page.locator('#report-source option').evaluateAll(options => options.some(option => option.value === 'job:job-a11y-failed'))), 'deleted job stayed in the source picker')
    assert.equal((await active(page)).id, 'job-message', 'delete result message should receive focus')
    assert.ok((await active(page)).text.includes('已从本机记录中删除'), 'delete result must be focused and readable')
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await delay(1700)
    assert.equal(await page.locator('#report-source option').evaluateAll(options => options.some(option => option.value === 'job:job-a11y-failed')), false, 'a later poll must not revive the deleted job')
    checks.push('delete confirmation: named group, open focus, Escape/Tab order, focus return, result focus, no revival')
    checkpoint('delete confirmation checked')

    jobsFail = true
    await page.getByRole('button', { name: '刷新任务与报告', exact: true }).click()
    await page.locator('.state.error').waitFor({ timeout: 10000 })
    const errorRegions = await liveRegions(page)
    assertNoInteractiveLive(errorRegions, 'reload error')
    assert.ok(errorRegions.some(region => region.role === 'alert' && region.text.includes('503')), 'reload failure must be announced as an alert')
    jobsFail = false
    await page.getByRole('button', { name: '重试', exact: true }).focus()
    await page.keyboard.press('Enter')
    await waitFor(async () => await page.locator('.state.error').count() === 0, 'retry did not clear the error state')
    const retryFocus = await active(page)
    assert.notEqual(retryFocus.tag, 'BODY', 'a successful page retry must restore focus from the removed retry button')
    assert.ok(retryFocus.cls.includes('job-state') || retryFocus.text === '刷新任务与报告', 'retry focus went to an unexpected target: ' + JSON.stringify(retryFocus))
    checks.push('error state: alert text outside controls; retry recovers and restores focus')
    checkpoint('error state checked')

    await page.getByRole('button', { name: '项目设置', exact: true }).focus()
    await page.keyboard.press('Enter')
    const dialog = page.getByRole('dialog', { name: '服务与存储设置', exact: true })
    await dialog.waitFor()
    await waitFor(async () => await page.locator('#app').getAttribute('aria-hidden') === 'true', 'the page behind a modal must be hidden from assistive technology')
    assert.equal(await dialog.getAttribute('aria-modal'), 'true')
    assert.equal((await active(page)).id, 'settings-close', 'settings dialog must open on its close control')
    const descriptionId = await dialog.getAttribute('aria-describedby')
    assert.ok(descriptionId && await page.locator('#' + descriptionId).innerText(), 'settings dialog needs an accessible description')
    for (let index = 0; index < 8; index++) {
      await page.keyboard.press('Tab')
      assert.equal(await dialog.evaluate(element => element.contains(document.activeElement)), true, 'Tab must stay inside the settings dialog')
    }
    await page.screenshot({ path: path.join(screenshots, 'settings-dialog-1440.png') })
    await dialog.evaluate(element => element.scrollTo(0, 0))
    await page.screenshot({ path: path.join(screenshots, 'settings-dialog-top-1440.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await dialog.evaluate(element => element.scrollTo(0, 0))
    await page.screenshot({ path: path.join(screenshots, 'settings-dialog-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    await page.keyboard.press('Escape')
    await waitFor(async () => await dialog.count() === 0, 'Escape did not close settings')
    assert.equal((await active(page)).text, '项目设置', 'closing settings must return focus to the trigger')
    checks.push('settings: accessible name/description, initial focus, focus trap, Escape and focus return')
    checkpoint('settings dialog checked')

    await page.locator('#report-source').selectOption('job:job-a11y-succeeded')
    await page.locator('.coverage-card').filter({ hasText: '输入来源状态' }).waitFor({ timeout: 10000 })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'reports-partial-sources-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })

    await page.getByRole('button', { name: '新建对照', exact: true }).click()
    await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    const fileInput = page.locator('input[accept=".apk"]')
    await fileInput.setInputFiles({ name: 'not-an-apk.txt', mimeType: 'text/plain', buffer: Buffer.from('not an apk') })
    await page.locator('#apk-file-error').waitFor()
    assert.equal(await fileInput.getAttribute('aria-invalid'), 'true', 'file error must mark the file input invalid')
    assert.equal(await fileInput.getAttribute('aria-describedby'), 'apk-file-error', 'file error must be linked from the file input')
    const fileErrorRegions = await liveRegions(page)
    assertNoInteractiveLive(fileErrorRegions, 'file error')
    const fileSession = await page.context().newCDPSession(page)
    const fileTree = await fileSession.send('Accessibility.getFullAXTree')
    const allFileNodes = fileTree.nodes.map(node => ({ role: node.role?.value, name: node.name?.value }))
    assert.ok(allFileNodes.some(node => node.name && node.name.includes('文件格式不支持')), 'the accessibility tree must expose the file error text')
    assert.ok(allFileNodes.some(node => node.role === 'alert'), 'the accessibility tree must expose the file error as an alert')
    await page.screenshot({ path: path.join(screenshots, 'import-file-error-1440.png') })
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => document.fonts.ready)
    await page.screenshot({ path: path.join(screenshots, 'import-file-error-390.png') })
    await page.setViewportSize({ width: 1440, height: 900 })
    await fileInput.focus()
    const fileDropFocus = await page.locator('.file-drop').evaluate(element => {
      const style = getComputedStyle(element)
      return { outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth }
    })
    assert.notEqual(fileDropFocus.outlineStyle, 'none', 'the hidden file input needs a visible focus indicator on its drop area')
    assert.ok(parseFloat(fileDropFocus.outlineWidth) >= 2, 'file drop focus outline is too thin: ' + JSON.stringify(fileDropFocus))
    await fileInput.setInputFiles({ name: 'sample.apk', mimeType: 'application/octet-stream', buffer: Buffer.from('synthetic name only') })
    await waitFor(async () => await page.locator('#apk-file-error').count() === 0, 'valid file did not clear the file error')
    checks.push('import: APK error is linked to its input and exposed without embedding controls in the alert')
    checkpoint('import file error checked')

    await page.getByRole('button', { name: '获取政策并检查候选', exact: true }).click()
    await page.locator('.busy-notice').waitFor({ timeout: 5000 })
    const busyRegions = await liveRegions(page)
    assertNoInteractiveLive(busyRegions, 'busy state')
    assert.ok(busyRegions.some(region => region.text.includes('正在处理当前请求')), 'busy text must be exposed')
    await page.screenshot({ path: path.join(screenshots, 'busy-state-1440.png') })
    await page.getByRole('button', { name: '取消准备请求', exact: true }).click()
    await waitFor(async () => await page.locator('.busy-notice').count() === 0, 'busy state did not clear after stop')
    assert.ok((await page.locator('.notice').innerText()).includes('当前准备请求已取消'), 'stop must leave a persistent, readable result')
    assert.notEqual((await active(page)).tag, 'BODY', 'stop must restore focus away from the document body')
    checks.push('busy: text-only status, stop outside live area, persistent cancellation notice and focus recovery (draft calls=' + draftCalls + ')')

    // Contrast and visible focus are measured from computed styles on the live page.
    checkpoint('busy state checked')
    const measurements = await page.evaluate(() => {
      const style = getComputedStyle(document.documentElement)
      const value = name => style.getPropertyValue(name).trim()
      const placeholder = document.querySelector('.ui-field input')
      return {
        tokens: { muted: value('--muted'), surface: value('--surface'), canvas: value('--canvas'), ink: value('--ink'), control: value('--control'), navy: value('--navy'), success: value('--success'), mint: value('--mint'), error: value('--error'), rose: value('--rose'), onAction: value('--on-action'), danger: value('--danger') },
        placeholder: placeholder ? getComputedStyle(placeholder, '::placeholder').color : null,
        sampleSurface: getComputedStyle(document.querySelector('.material-panel') || document.body).backgroundColor,
      }
    })
    const ratios = {
      'muted/surface': contrast(measurements.tokens.muted, measurements.tokens.surface),
      'muted/canvas': contrast(measurements.tokens.muted, measurements.tokens.canvas),
      'ink/surface': contrast(measurements.tokens.ink, measurements.tokens.surface),
      'success/mint': contrast(measurements.tokens.success, measurements.tokens.mint),
      'error/rose': contrast(measurements.tokens.error, measurements.tokens.rose),
      'control/surface': contrast(measurements.tokens.control, measurements.tokens.surface),
      'navy/canvas': contrast(measurements.tokens.navy, measurements.tokens.canvas),
      'on-action/navy': contrast(measurements.tokens.onAction, measurements.tokens.navy),
      'on-action/danger': contrast(measurements.tokens.onAction, measurements.tokens.danger),
    }
    for (const [pair, minimum] of [['muted/surface', 4.5], ['muted/canvas', 4.5], ['ink/surface', 4.5], ['success/mint', 4.5], ['error/rose', 4.5], ['control/surface', 3], ['navy/canvas', 3], ['on-action/navy', 4.5], ['on-action/danger', 4.5]]) {
      assert.ok(ratios[pair] >= minimum, pair + ' contrast ' + ratios[pair] + ' is below ' + minimum)
    }
    if (measurements.placeholder) {
      const rgb = measurements.placeholder.match(/\d+(\.\d+)?/g).slice(0, 3).map(Number)
      const hex = '#' + rgb.map(part => Math.round(part).toString(16).padStart(2, '0')).join('')
      ratios['placeholder/surface'] = contrast(hex, measurements.tokens.surface)
      assert.ok(ratios['placeholder/surface'] >= 4.5, 'placeholder contrast ' + ratios['placeholder/surface'] + ' is below 4.5')
    }
    await page.locator('#page-title').focus()
    await page.keyboard.press('Tab')
    let focusOutline = null
    for (let index = 0; index < 12; index++) {
      const current = await page.evaluate(() => {
        const element = document.activeElement
        const style = getComputedStyle(element)
        const isTransparent = color => !color || color === 'transparent' || /rgba\([^)]*,\s*0\)/.test(color)
        let background = getComputedStyle(element).backgroundColor
        let node = element
        // The focus ring is drawn outside the control (offset), so its contrast
        // is against the surrounding surface, not the control's own fill.
        while ((isTransparent(background) || node === element) && node.parentElement) {
          node = node.parentElement
          background = getComputedStyle(node).backgroundColor
        }
        return { tag: element.tagName, outlineStyle: style.outlineStyle, outlineWidth: style.outlineWidth, outlineColor: style.outlineColor, background: isTransparent(background) ? 'rgb(255, 255, 255)' : background, text: (element.innerText || '').trim().slice(0, 40) }
      })
      if (current.tag === 'BUTTON' || current.tag === 'A') { focusOutline = current; break }
      await page.keyboard.press('Tab')
    }
    assert.ok(focusOutline && focusOutline.outlineStyle !== 'none' && parseFloat(focusOutline.outlineWidth) >= 2, 'keyboard focus must expose a visible outline: ' + JSON.stringify(focusOutline))
    ratios['focus-outline/background'] = contrast(focusOutline.outlineColor, focusOutline.background)
    assert.ok(ratios['focus-outline/background'] >= 3, 'focus outline contrast is below 3:1')
    checks.push('contrast: ' + Object.entries(ratios).map(([pair, value]) => pair + '=' + value).join(', '))
    checkpoint('contrast and visible focus checked')

    // Chromium accessibility tree is a semantics check, not a substitute for a real screen reader.
    const session = await page.context().newCDPSession(page)
    const tree = await session.send('Accessibility.getFullAXTree')
    const roles = tree.nodes.map(node => ({ role: node.role?.value, name: node.name?.value })).filter(node => node.role && node.name)
    assert.ok(roles.some(node => node.role === 'heading' && node.name.includes('导入分析材料')), 'AX tree lost the import heading')
    assert.deepEqual(errors, [], 'browser page errors: ' + JSON.stringify(errors))

    jobsFail = true
    await page.reload()
    await page.getByRole('button', { name: '已有报告', exact: true }).click()
    await page.locator('.state.error').waitFor({ timeout: 10000 })
    await page.getByRole('button', { name: '重试', exact: true }).focus()
    jobsFail = false
    await page.keyboard.press('Enter')
    await waitFor(async () => await page.locator('.state.error').count() === 0, 'initial-load retry did not clear the error')
    assert.notEqual((await active(page)).tag, 'BODY', 'initial-load retry must restore focus from the removed retry button')
    checks.push('initial load failure: retry clears the error and restores focus')

    jobsFail = true
    await page.locator('#report-source').selectOption('job:job-running')
    await page.locator('.state.error').waitFor({ timeout: 10000 })
    await page.getByRole('button', { name: '重试', exact: true }).focus()
    jobsFail = false
    await page.keyboard.press('Enter')
    await waitFor(async () => await page.locator('.state.error').count() === 0, 'source-switch retry did not clear the error')
    assert.notEqual((await active(page)).tag, 'BODY', 'source-switch retry must restore focus from the removed retry button')
    checks.push('source switch failure: retry keeps the selected source and restores focus')

    const result = {
      result: 'PASS', commit: execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
      dirty: !!execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim(),
      scope: 'browser keyboard/focus/state semantics and ARIA on deterministic fixtures; no real scan, model, screen reader or device',
      viewport: [[1440, 900], [390, 844]], checks, contrast: ratios, measurements,
      ax_tree_sample: roles.filter(node => ['heading', 'alert', 'status', 'dialog', 'group', 'region'].includes(node.role)).slice(0, 40),
      limitations: ['No NVDA/VoiceOver or real Android device run', 'Fixtures are mocked; no real APK scan or model call', 'No visual design sign-off by the user'],
      errors,
    }
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(result, null, 2))
    console.log('Issue 145 accessibility checks passed:', checks.length)
    for (const check of checks) console.log(' -', check)
    console.log('Contrast:', ratios)
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
