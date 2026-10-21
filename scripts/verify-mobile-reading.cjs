#!/usr/bin/env node
// Production Vue, deterministic report + mocked native bridge. No Android/IME,
// model, APK or Docker execution. Reuse the round-2 journey instead of creating
// another test-only analysis pipeline.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const net = require('node:net')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')

const root = path.resolve(__dirname, '..')
const harness = fs.readFileSync(path.join(__dirname, 'verify-frontend-round2.cjs'), 'utf8')
const mainOffset = harness.indexOf('async function main()')
assert.ok(mainOffset > 0, 'round-2 fixture helpers must be available')
// Load the trusted repository helpers in this realm: their strict assertions
// compare Playwright arrays with literal arrays, so a separate VM realm would
// incorrectly reject two empty arrays because their prototypes differ.
const loadHelpers = new Function('require', '__dirname', harness.slice(0, mainOffset).replace(/^#![^\n]*\n/, '') + '\nreturn { bridge, bridgeFixtures, selectAndPrepare, waitTitle, assertNoPageOverflow, assertTouchTargets }')
const { bridge, bridgeFixtures, selectAndPrepare, waitTitle, assertNoPageOverflow, assertTouchTargets } = loadHelpers(require, __dirname)
const evidenceDir = process.env.PRIVACYTRACE_READING_EVIDENCE || path.join(root, 'tmp/mobile-reading')
fs.mkdirSync(evidenceDir, { recursive: true })
const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim()
const dirty = !!execFileSync('git', ['status', '--porcelain', '--untracked-files=no'], { cwd: root, encoding: 'utf8' }).trim()
const checks = [], captures = [], errors = []

async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(async () => {
    const finite = document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity)
    await Promise.all(finite.map(animation => animation.finished.catch(() => {})))
  })
  const file = name + '.png'
  await page.screenshot({ path: path.join(evidenceDir, file), fullPage: false })
  captures.push({ file, viewport: page.viewportSize(), source_sha: sha, dirty, platform: 'Chromium + mocked native bridge + fixed report' })
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
    const deadline = Date.now() + 45000
    while (true) {
      try { if ((await fetch(origin)).ok) break } catch {}
      if (child.exitCode !== null || Date.now() > deadline) throw new Error('Owned Vite did not start')
      await new Promise(resolve => setTimeout(resolve, 150))
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const context = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(bridge, bridgeFixtures)
    await page.goto(origin)
    await selectAndPrepare(page)
    const material = page.getByRole('region', { name: '当前分析材料' })
    const collapsedHeight = await material.evaluate(element => element.getBoundingClientRect().height)
    assert.ok(collapsedHeight <= 86, `closed material identity must remain one compact row, got ${collapsedHeight}px`)
    await assertTouchTargets(page, 'reading/candidates/390')
    await assertNoPageOverflow(page, 'reading/candidates/390')
    await capture(page, 'candidates-390')
    await material.locator('summary').click()
    assert.ok(await material.getByText('https://analysis.example/', { exact: true }).isVisible(), 'material details must reveal the actual analysis service')
    assert.ok(await material.getByText('com.example.' + 'b'.repeat(160), { exact: true }).last().isVisible(), 'the full material name must remain reachable')
    await assertNoPageOverflow(page, 'reading/material-details')
    await material.locator('summary').click()
    checks.push('one compact material row; full identity and actual instance remain reachable')

    await page.getByRole('button', { name: '服务与存储设置', exact: true }).click()
    const settings = page.locator('dialog.m-settings-dialog')
    await settings.waitFor()
    assert.ok(await settings.getByText('https://analysis.example/', { exact: true }).isVisible())
    assert.doesNotMatch(await settings.innerText(), /保存在本机服务|本机运行/)
    assert.match(await settings.innerText(), /保存在本机/ , 'model credentials still have their device-local explanation')
    await capture(page, 'settings-390')
    await page.keyboard.press('Escape')
    checks.push('settings distinguish remote material storage from device-local model credentials')

    await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click()
    await waitTitle(page, '分析进度', 12000)
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 10000 })
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await waitTitle(page, '对照报告', 12000)
    const summary = page.getByRole('region', { name: '报告摘要' })
    assert.equal(await page.getByRole('heading', { name: bridgeFixtures.reportFixture.sample.name, exact: true }).count(), 1, 'the report must present the application identity only once')
    const firstIssue = page.locator('.m-issue-list .evidence-button').first()
    const issueBounds = await firstIssue.boundingBox()
    assert.ok(issueBounds && issueBounds.y >= 0 && issueBounds.y + issueBounds.height < 844, 'a complete conclusion and its evidence action must fit in the first 390x844 viewport')
    assert.match(await summary.innerText(), /REAL_SCAN/)
    assert.match(await summary.innerText(), /REPLAY/)
    assert.match(await summary.innerText(), /不证明实际采集/)
    await capture(page, 'report-390')
    checks.push('report shows one identity, independent origin/delivery labels, and a complete evidence action above the fold')

    await summary.locator('summary').focus()
    await page.keyboard.press('Enter')
    assert.ok(await summary.getByText(bridgeFixtures.reportFixture.sample.package_name, { exact: true }).isVisible())
    assert.ok(await summary.getByText('https://analysis.example/', { exact: true }).isVisible())
    assert.match(await summary.innerText(), /更不是合法性判断/)
    await assertNoPageOverflow(page, 'reading/report-details')
    await capture(page, 'report-details-390')
    await summary.locator('summary').click()
    checks.push('keyboard disclosure reveals full package, instance, timestamps and the original scope disclaimer')

    for (const width of [320, 768]) {
      await page.setViewportSize({ width, height: width === 320 ? 568 : 1024 })
      await assertNoPageOverflow(page, `reading/report/${width}`)
      await capture(page, `report-${width}`)
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await assertNoPageOverflow(page, 'reading/report/200%')
    await capture(page, 'report-390-large-text')
    await summary.locator('summary').click()
    await assertNoPageOverflow(page, 'reading/report-details/200%')
    await summary.locator('summary').click()
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await summary.locator('summary').click()
    assert.equal(await summary.getByText('https://analysis.example/', { exact: true }).isVisible(), true)
    await page.keyboard.press('Tab')
    checks.push('320/768/200% text and reduced motion preserve content and disclosure access')

    const desktop = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    desktop.on('pageerror', error => errors.push(error.message))
    await desktop.goto(origin)
    await desktop.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    assert.equal(await desktop.locator('.mobile-report-summary').count(), 0, 'desktop must not inherit the mobile report summary')
    await capture(desktop, 'desktop-import-1440')
    checks.push('desktop entry stays on its original layout')
    assert.deepEqual(errors, [])
    fs.writeFileSync(path.join(evidenceDir, 'verification.json'), JSON.stringify({ source_sha: sha, dirty, captured_at: new Date().toISOString(), checks, captures, errors, platform: 'Chromium with deterministic fixtures and mocked native bridge; Android/real IME/TalkBack NOT_RUN' }, null, 2) + '\n')
    console.log(`${checks.length} reading checks passed; ${captures.length} screenshots; source ${sha}; dirty=${dirty}`)
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
