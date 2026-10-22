#!/usr/bin/env node
/**
 * #167 / #165 copy + layout contract in a real Chromium session.
 *
 * Covers the six product faces (import / candidates / progress / sample report /
 * settings / archive) and the five required viewports plus 200% root text:
 *   - exactly one #page-title per face, with the adopted four-step/report/archive
 *     names;
 *   - exactly one nav.flow-nav with four steps and one aria-current=step, no
 *     horizontal scroll at or below 896px;
 *   - exactly one "示例体验 · 固定材料" marker, and none of the retired example
 *     markers;
 *   - comparison table headers 数据类型/证据, every cell labelled, no 依据/隐私数据;
 *   - the unified source-state line on import, candidates and report, never
 *     "已复核" next to an unknown/partial fact;
 *   - one h1, one red primary, one evidence region, aria-pressed/aria-controls
 *     selection and the 返回刚才的操作 focus restore in the sample report;
 *   - no horizontal scroll at 1440/1280/768/390/320 and at 200% root text.
 *
 * Real dev server (own port) unless PRIVACYTRACE_FRONTEND_URL points at one.
 * Chromium only; no APK, model, backend or Android device is executed.
 */
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const net = require('node:net')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')

const root = path.resolve(__dirname, '..')
const output = path.join(root, 'docs/acceptance/issue165')
const screenshots = path.join(output, 'screenshots')
fs.mkdirSync(screenshots, { recursive: true })

const steps = ['APK 与政策材料', '核对政策声明', '扫描与对照进度', '对照报告']
const reportTitle = 'APP 隐私收集越权报告'
const archiveTitle = '本机存档报告'
const unifiedLine = '来源未复核 · 正文完整度未知 · 附件未检查'
const retiredMarkers = ['固定示例内容', '示例阶段已切换', '仅示例有效']
const viewports = [[1440, 900], [1280, 720], [768, 1024], [390, 844], [320, 640]]
const checks = []
const captures = []
const errors = []
const requests = []
const apiRequestLedger = []

async function fontsReady(page) {
  await page.evaluate(() => document.fonts.ready)
}
async function capture(page, name, fullPage = false) {
  await fontsReady(page)
  const file = name + '.png'
  await page.screenshot({ path: path.join(screenshots, file), fullPage })
  captures.push(file)
}
async function assertNoOverflow(page, label) {
  const measured = await page.evaluate(() => ({
    innerWidth: window.innerWidth,
    documentWidth: document.documentElement.scrollWidth,
    bodyWidth: document.body.scrollWidth,
  }))
  assert.ok(measured.documentWidth <= measured.innerWidth, `${label}: document scrollWidth ${measured.documentWidth} > viewport ${measured.innerWidth}`)
  assert.ok(measured.bodyWidth <= measured.innerWidth, `${label}: body scrollWidth ${measured.bodyWidth} > viewport ${measured.innerWidth}`)
  checks.push(`no horizontal overflow: ${label}`)
}
async function assertPageTitle(page, expected, label) {
  const state = await page.evaluate(() => ({
    titles: [...document.querySelectorAll('#page-title')].map((element) => element.textContent.trim()),
    headings: [...document.querySelectorAll('h1')].map((element) => element.textContent.trim()),
  }))
  assert.equal(state.titles.length, 1, `${label}: exactly one #page-title`)
  assert.equal(state.titles[0], expected, `${label}: #page-title is driven by frontendCopy.pageTitles`)
  assert.equal(state.headings.length, 1, `${label}: exactly one h1`)
  assert.equal(state.headings[0], expected, `${label}: the h1 carries the page identity`)
  checks.push(`${label}: single #page-title = ${expected}`)
}
async function flowNavState(page) {
  return page.evaluate(() => ({
    navs: document.querySelectorAll('nav.flow-nav').length,
    legacyNavs: document.querySelectorAll('.step-nav').length,
    buttons: [...document.querySelectorAll('nav.flow-nav button')].map((button) => ({
      text: (button.textContent || '').replace(/\s+/g, ' ').trim(),
      current: button.getAttribute('aria-current'),
      disabled: button.disabled,
    })),
    currentSteps: document.querySelectorAll('nav.flow-nav button[aria-current="step"]').length,
  }))
}
async function assertFlowNav(page, expectedIndex, label) {
  const state = await flowNavState(page)
  assert.equal(state.navs, 1, `${label}: exactly one nav.flow-nav`)
  assert.equal(state.legacyNavs, 0, `${label}: the deleted .step-nav must not render`)
  assert.equal(state.buttons.length, 4, `${label}: four flow steps`)
  state.buttons.forEach((button, index) => {
    assert.ok(button.text.includes(steps[index]), `${label}: step ${index + 1} text must include ${steps[index]} (got ${button.text})`)
  })
  assert.equal(state.currentSteps, 1, `${label}: exactly one aria-current=step`)
  if (expectedIndex != null) {
    assert.equal(state.buttons[expectedIndex].current, 'step', `${label}: step ${expectedIndex + 1} is current`)
  }
  checks.push(`${label}: one four-step flow nav, current step ${expectedIndex == null ? 'none' : expectedIndex + 1}`)
}
async function assertSingleMarker(page, label) {
  assert.equal(await page.getByText('示例体验 · 固定材料', { exact: true }).count(), 1, `${label}: exactly one global example marker`)
  for (const marker of retiredMarkers) {
    assert.equal(await page.getByText(marker, { exact: false }).count(), 0, `${label}: retired marker ${marker} must not return`)
  }
  checks.push(`${label}: single 示例体验 · 固定材料 marker, no retired example markers`)
}
async function assertUnifiedStateLine(page, selector, label) {
  const text = await page.locator(selector).first().innerText()
  assert.equal(text.replace(/\s+/g, ' ').trim(), unifiedLine, `${label}: source-state line must use the unified #167 format`)
  assert.doesNotMatch(text, /已复核/, `${label}: an unknown review fact must never read 已复核`)
  checks.push(`${label}: unified source-state line ${unifiedLine}`)
}

async function textStep(page, buttonName, expectedTitle, index, label) {
  await page.getByRole('button', { name: buttonName, exact: true }).click()
  await page.waitForFunction((expected) => document.getElementById('page-title')?.textContent?.trim() === expected, expectedTitle, { timeout: 10000 })
  await assertPageTitle(page, expectedTitle, label)
  await assertFlowNav(page, index, label)
}

async function freePort() {
  const server = net.createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise((resolve) => server.close(resolve))
  return port
}

async function main() {
  const children = []
  let browser
  const proof = {
    result: 'FAIL',
    scope: 'real Chromium against the Vue dev build; example materials only, no APK scan, model, backend or Android device',
    viewports: viewports.map(([width, height]) => `${width}x${height}`),
    largeText: '200% root font size at 390/320',
    checks,
    screenshots: captures,
    pageErrors: errors,
    browserApiRequests: apiRequestLedger,
  }
  try {
    let origin = process.env.PRIVACYTRACE_FRONTEND_URL
    if (!origin) {
      const port = await freePort()
      origin = `http://127.0.0.1:${port}`
      const child = spawn('npm run dev', { ...spawnOptions(root, { PRIVACYTRACE_WEB_PORT: String(port) }), windowsHide: true })
      children.push(child)
      child.stdout.resume(); child.stderr.resume()
      const deadline = Date.now() + 45000
      while (true) {
        if (child.exitCode !== null || Date.now() > deadline) throw new Error('Owned Vite did not start')
        try { if ((await fetch(origin)).ok) break } catch {}
        await new Promise((resolve) => setTimeout(resolve, 150))
      }
      checks.push(`owned dev server started on ${origin}`)
    } else {
      checks.push(`reused frontend at ${origin}`)
    }

    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    page.on('pageerror', (error) => errors.push(error.message))
    page.on('request', (request) => {
      const url = new URL(request.url())
      if (!url.pathname.startsWith('/api/')) return
      requests.push(url.pathname)
      if (!['/api/v1/health', '/api/v1/taxonomy', '/api/v1/web/settings'].includes(url.pathname)) apiRequestLedger.push(url.pathname)
    })

    await page.goto(origin)
    await page.getByRole('heading', { name: 'APK 与政策材料', exact: true }).waitFor({ timeout: 15000 })
    await fontsReady(page)

    // ---- import ------------------------------------------------------------
    await assertPageTitle(page, 'APK 与政策材料', 'import')
    await assertFlowNav(page, 0, 'import')
    await assertNoOverflow(page, 'import@1440')
    // The single global example marker only exists in the example state.
    await page.getByRole('button', { name: '体验示例', exact: true }).click()
    await page.waitForFunction(() => document.querySelector('.shell-demo')?.textContent?.includes('示例体验 · 固定材料'), null, { timeout: 5000 })
    await assertSingleMarker(page, 'import')
    const importLines = await page.locator('.source-notes').allInnerTexts()
    assert.ok(importLines.length >= 1, 'import: every source needs a visible state line')
    for (const line of importLines) assert.ok(line.replace(/\s+/g, ' ').includes(unifiedLine), `import: source note must carry the unified line (got ${line})`)
    assert.ok((await page.locator('body').innerText()).includes('适用范围不明'), 'import: unknown applicability stays explicit')
    checks.push('import: unified source-state line + 适用范围不明 on every source')
    await capture(page, 'import-1440')

    // ---- candidates --------------------------------------------------------
    await textStep(page, '检查候选', '核对政策声明', 1, 'candidates')
    await assertNoOverflow(page, 'candidates@1440')
    const contextText = (await page.locator('[data-testid="candidate-source-context"]').innerText()).replace(/\s+/g, ' ')
    assert.ok(contextText.includes(unifiedLine), `candidates: source context must carry the unified line (got ${contextText})`)
    assert.doesNotMatch(contextText, /已复核/, 'candidates: an unknown review fact must never read 已复核')
    checks.push('candidates: unified source-state line in the source context strip')
    await capture(page, 'candidates-1440')

    // ---- progress ----------------------------------------------------------
    await textStep(page, '进入流程演示', '扫描与对照进度', 2, 'progress')
    await assertNoOverflow(page, 'progress@1440')
    const stageText = await page.locator('.stage-list').innerText()
    for (const stage of ['核对材料', '隔离扫描 APK', '装载政策原文', '规则对照', '生成报告']) {
      assert.ok(stageText.includes(stage), `progress: the adopted stage ${stage} must render`)
    }
    assert.equal(await page.getByText('纸舟地图', { exact: true }).count(), 0, 'progress: the sample app name must not pose as the stage title')
    checks.push('progress: nine-stage vocabulary renders, no 纸舟地图 stage title')
    await capture(page, 'progress-1440')

    // ---- sample report -----------------------------------------------------
    for (let index = 0; index < 4; index++) await page.getByRole('button', { name: '进入下一阶段', exact: true }).click()
    await page.getByRole('button', { name: '完成当前阶段', exact: true }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.waitForFunction((expected) => document.getElementById('page-title')?.textContent?.trim() === expected, reportTitle, { timeout: 10000 })
    await assertPageTitle(page, reportTitle, 'report')
    await assertFlowNav(page, 3, 'report')
    await assertSingleMarker(page, 'report')

    const headers = await page.locator('.comparison-table thead th').allInnerTexts()
    assert.deepEqual(headers.map((text) => text.trim()), ['数据类型', '证据'], 'report: comparison headers are 数据类型/证据')
    const cells = await page.locator('.comparison-table tbody td').evaluateAll((nodes) => nodes.map((node) => ({
      label: (node.getAttribute('data-label') || '').trim(),
      text: (node.textContent || '').trim(),
    })))
    assert.ok(cells.length >= 2, 'report: the comparison table has cells')
    for (const cell of cells) assert.ok(cell.label.length > 0, `report: every comparison cell needs data-label (got ${JSON.stringify(cell)})`)
    for (const cell of cells) {
      assert.notEqual(cell.label, '依据', 'report: the retired 依据 column label must not return')
      assert.notEqual(cell.label, '隐私数据', 'report: the retired 隐私数据 column label must not return')
    }
    assert.equal(await page.locator('.comparison-table').getByText('依据', { exact: true }).count(), 0, 'report: no 依据 text inside the comparison table')
    checks.push('report: headers 数据类型/证据, every td labelled, retired 依据/隐私数据 gone')

    const reportStateLine = (await page.locator('.report-source-state').innerText()).replace(/\s+/g, ' ')
    assert.ok(reportStateLine.includes(unifiedLine), `report: report source state must carry the unified line (got ${reportStateLine})`)
    assert.doesNotMatch(reportStateLine, /已复核/, 'report: the summary must never read 已复核')
    await page.locator('.report-info > summary').click()
    const infoRows = await page.locator('.report-info dl > div').evaluateAll((nodes) => nodes.map((node) => ({
      title: (node.querySelector('dt')?.textContent || '').trim(),
      state: (node.querySelector('dd')?.textContent || '').replace(/\s+/g, ' ').trim(),
    })))
    const sourceRows = infoRows.filter((row) => ['纸舟地图隐私政策', '云点统计服务说明'].includes(row.title))
    assert.equal(sourceRows.length, 2, 'report: one fact row per policy source')
    for (const row of sourceRows) {
      assert.ok(row.state.includes('来源未复核'), `report: source ${row.title} keeps 来源未复核 (got ${row.state})`)
      assert.ok(row.state.includes('附件未检查'), `report: source ${row.title} keeps 附件未检查`)
      assert.doesNotMatch(row.state, /来源已复核/, 'report: text availability must not promote the source to 已复核')
    }
    checks.push('report: expanded source facts keep the unified line and never claim 已复核')

    assert.equal(await page.locator('#example-evidence').count(), 1, 'report: exactly one evidence region')
    assert.equal(await page.locator('.report-action .ui-button.primary').count(), 1, 'report: exactly one red primary action')
    const selected = page.locator('.comparison-table [aria-pressed="true"]')
    assert.equal(await selected.count(), 1, 'report: exactly one row is the current selection')
    assert.equal(await selected.getAttribute('aria-controls'), 'example-evidence', 'report: the selected row controls the evidence region')
    const secondRowButton = page.locator('.comparison-table tbody tr').nth(1).getByRole('button').first()
    await secondRowButton.click()
    await page.waitForFunction(() => document.querySelector('#example-evidence-title')?.textContent.includes('设备标识'))
    assert.equal(await page.locator('.comparison-table [aria-pressed="true"]').count(), 1, 'report: switching keeps one current selection')
    assert.equal(await secondRowButton.getAttribute('aria-pressed'), 'true', 'report: the clicked row becomes current')
    assert.ok((await page.locator('.report-action .action-label').innerText()).includes('设备标识'), 'report: the primary action names the selected object')
    await page.locator('#example-evidence').getByRole('button', { name: '返回刚才的操作', exact: true }).click()
    assert.equal(await secondRowButton.evaluate((element) => element === document.activeElement), true, 'report: 返回刚才的操作 restores the triggering row focus')
    checks.push('report: one h1/primary/evidence region, aria-pressed+aria-controls selection, 返回刚才的操作 focus restore')
    await capture(page, 'report-1440', true)

    // ---- five viewports + 200% root text -----------------------------------
    for (const [width, height] of viewports) {
      await page.setViewportSize({ width, height })
      await fontsReady(page)
      const expectedLayout = width <= 896 ? 'stacked' : 'columns'
      await page.waitForFunction((expected) => document.querySelector('.report-columns')?.getAttribute('data-layout') === expected, expectedLayout, { timeout: 5000 })
      await assertNoOverflow(page, `report@${width}`)
      const layout = await page.locator('.report-columns').getAttribute('data-layout')
      assert.equal(layout, expectedLayout, `report@${width}: report-columns data-layout follows the 896px breakpoint`)
      assert.equal(await page.locator('#example-evidence').count(), 1, `report@${width}: one evidence region`)
      assert.equal(await page.locator('.report-action .ui-button.primary').count(), 1, `report@${width}: one red primary action`)
      const railRows = await page.evaluate(() => new Set([...document.querySelectorAll('nav.flow-nav button')].map((button) => Math.round(button.getBoundingClientRect().top))).size)
      assert.equal(railRows, width <= 896 ? 1 : 4, `report@${width}: the same flow DOM is one horizontal row below 896px and a sidebar column above it`)
      await assertFlowNav(page, 3, `report@${width}`)
      await capture(page, `report-${width}`)
    }
    for (const width of [390, 320]) {
      await page.setViewportSize({ width, height: 844 })
      const zoom = await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
      try {
        await fontsReady(page)
        await assertNoOverflow(page, `report@${width} 200%`)
        const primary = page.locator('.report-action .ui-button.primary')
        assert.equal(await primary.isVisible(), true, `report@${width} 200%: the red primary stays visible`)
        await capture(page, `report-${width}-200`)
      } finally {
        await zoom.evaluate((element) => element.remove())
      }
    }
    await page.setViewportSize({ width: 1440, height: 900 })

    // ---- settings ----------------------------------------------------------
    await page.getByRole('button', { name: '项目设置', exact: true }).click()
    const dialog = page.getByRole('dialog', { name: '服务与存储设置', exact: true })
    await dialog.waitFor()
    assert.equal(await page.locator('h1').count(), 1, 'settings: opening the dialog keeps one h1')
    await assertNoOverflow(page, 'settings@1440')
    await capture(page, 'settings-1440')
    await page.setViewportSize({ width: 390, height: 844 })
    await assertNoOverflow(page, 'settings@390')
    await capture(page, 'settings-390')
    await page.keyboard.press('Escape')
    await page.setViewportSize({ width: 1440, height: 900 })
    await dialog.waitFor({ state: 'detached' })
    checks.push('settings: modal keeps one h1 and no horizontal overflow at 1440/390')

    // The example flow must stay offline; the archive view below legitimately
    // reads the saved job list, so snapshot the flow ledger before it opens.
    const exampleFlowApi = apiRequestLedger.splice(0)
    assert.deepEqual(exampleFlowApi, [], 'the example flow must not call scan/report APIs: ' + JSON.stringify(exampleFlowApi))

    // ---- archive -----------------------------------------------------------
    await page.locator('.nav-item').filter({ hasText: '已有报告' }).click()
    await page.waitForFunction((expected) => document.getElementById('page-title')?.textContent?.trim() === expected, archiveTitle, { timeout: 10000 })
    await assertPageTitle(page, archiveTitle, 'archive')
    const archiveNav = await flowNavState(page)
    assert.equal(archiveNav.navs, 1, 'archive: exactly one nav.flow-nav')
    assert.equal(archiveNav.currentSteps, 0, 'archive: no workflow step is current in the archive view')
    assert.equal(await page.locator('.workspace-content .shell .topbar').count(), 0, 'archive: the embedded viewer renders no second brand bar')
    assert.equal(await page.locator('.workspace-content .shell main > .intro').count(), 0, 'archive: the embedded viewer renders no second hero')
    await assertNoOverflow(page, 'archive@1440')
    await capture(page, 'archive-1440')
    await page.setViewportSize({ width: 390, height: 844 })
    await assertNoOverflow(page, 'archive@390')
    await capture(page, 'archive-390')
    checks.push('archive: single h1 本机存档报告, one flow nav, no duplicated brand hero, no overflow at 1440/390')

    const archiveApi = apiRequestLedger.splice(0)
    assert.ok(archiveApi.every((pathname) => pathname.startsWith('/api/v1/jobs')), 'the archive view may only read saved job data: ' + JSON.stringify(archiveApi))
    assert.deepEqual(errors, [], 'browser page errors: ' + JSON.stringify(errors))
    proof.result = 'PASS'
    proof.commit = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8', cwd: root }).trim()
    proof.dirty = Boolean(execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8', cwd: root }).trim())
    proof.recordedApiRequests = requests
    proof.archiveApiRequests = archiveApi
    console.log(`Copy contract passed: ${checks.length} checks, ${captures.length} screenshots -> docs/acceptance/issue165/`)
  } finally {
    await browser?.close()
    const survivors = await stopChildren(children)
    if (survivors.length) { proof.result = 'FAIL'; proof.cleanup = 'owned child survived' }
    fs.writeFileSync(path.join(output, 'copy-contract.json'), JSON.stringify(proof, null, 2) + '\n')
    if (survivors.length) throw new Error('The copy-contract run left a server process running')
  }
}

main().catch((error) => {
  console.error(error)
  process.exitCode = 1
})
