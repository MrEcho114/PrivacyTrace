#!/usr/bin/env node
// Production Vue + deterministic native bridge. This checks UI contracts only;
// Android WebView, system font scaling, IME and TalkBack are not exercised.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const net = require('node:net')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')
const root = path.resolve(__dirname, '..')
const source = fs.readFileSync(path.join(__dirname, 'verify-frontend-round2.cjs'), 'utf8')
const helpers = new Function('require', '__dirname', source.slice(0, source.indexOf('async function main()')).replace(/^#![^\n]*\n/, '') + '\nreturn { bridge, bridgeFixtures, waitTitle, assertNoPageOverflow }')(require, __dirname)
const output = process.env.PRIVACYTRACE_REFINEMENTS_EVIDENCE || path.join(root, 'tmp/issue295-refinements')
fs.mkdirSync(output, { recursive: true })
const checks = [], captures = [], errors = []
const sha = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim()
const dirty = Boolean(execFileSync('git', ['status', '--porcelain'], { cwd: root, encoding: 'utf8' }).trim())

async function capture(page, name) {
  await page.evaluate(() => document.fonts.ready)
  await page.evaluate(async () => {
    await Promise.all(document.getAnimations().filter(animation => animation.effect?.getTiming().iterations !== Infinity).map(animation => animation.finished.catch(() => {})))
  })
  await page.screenshot({ path: path.join(output, name + '.png') })
  await page.screenshot({ path: path.join(output, name + '-full.png'), fullPage: true })
  captures.push({ file: name + '.png', viewport: page.viewportSize(), root_font: await page.evaluate(() => getComputedStyle(document.documentElement).fontSize) })
}
async function assertDeleteControlsReachable(page) {
  for (const name of ['确认删除候选', '取消删除']) {
    const button = page.getByRole('button', { name, exact: true })
    const visible = await button.evaluate(element => {
      const rect = element.getBoundingClientRect()
      const barTop = document.querySelector('.m-actionbar').getBoundingClientRect().top
      const target = document.elementFromPoint(rect.x + rect.width / 2, rect.y + rect.height / 2)
      return rect.top >= 0 && rect.bottom <= barTop && element.contains(target)
    })
    assert.equal(visible, true, `${name} must be visible and clickable above the fixed action bar`)
  }
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
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const page = await browser.newPage({ viewport: { width: 320, height: 568 }, hasTouch: true, isMobile: true, deviceScaleFactor: 1 })
    page.on('pageerror', error => errors.push(error.message))
    await page.addInitScript(helpers.bridge, helpers.bridgeFixtures)
    await page.addInitScript(() => {
      // Inject failures at the existing native seam; keep the real Vue/flow.
      globalThis.rejectSave = false
      const invoke = globalThis.__TAURI_INTERNALS__.invoke
      globalThis.__TAURI_INTERNALS__.invoke = async (command, args = {}) => {
        if (globalThis.rejectSave && args.action === 'candidates') throw new Error('SERVER_BUSY')
        return invoke(command, args)
      }
      globalThis.rejectClipboard = true
      Object.defineProperty(navigator, 'clipboard', { configurable: true, value: {
        writeText: async value => {
          if (globalThis.rejectClipboard) throw new Error('Permission denied')
          globalThis.copiedHash = value
        },
      } })
    })
    await page.goto(origin)
    await page.getByRole('button', { name: '选择应用', exact: true }).click()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor()
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await page.evaluate(() => document.fonts.ready)
    await page.evaluate(() => window.scrollTo(0, 0))
    await capture(page, 'import-320-200')
    await page.getByRole('button', { name: '准备政策', exact: true }).click()
    await helpers.waitTitle(page, '核对政策声明')
    await page.evaluate(() => window.scrollTo(0, 0))
    await capture(page, 'candidates-320-200')
    const name = page.locator('.source-context-title')
    const text = name.locator('.m-readable-name-text')
    const nameSize = await name.evaluate(element => {
      const content = element.querySelector('.m-readable-name-text') || element
      return { height: content.getBoundingClientRect().height, line: parseFloat(getComputedStyle(content).lineHeight) }
    })
    assert.ok(nameSize.height <= nameSize.line * 2 + 1, `long source name must initially fit two lines (${nameSize.height}px / ${nameSize.line}px)`)
    const expand = name.getByRole('button', { name: '展开完整名称', exact: true })
    await expand.click()
    assert.equal(await text.innerText(), helpers.bridgeFixtures.policyTitle)
    assert.equal(await text.evaluate(el => el.scrollHeight <= el.clientHeight + 1), true, 'expanded title must expose every line')
    await name.getByRole('button', { name: '收起名称', exact: true }).click()
    assert.equal(await expand.getAttribute('aria-expanded'), 'false')
    await page.evaluate(() => window.scrollTo(0, 350))
    assert.ok(await page.locator('.m-appbar').evaluate(el => el.getBoundingClientRect().bottom <= 0), 'large app bar must scroll away instead of covering the reading area')
    await helpers.assertNoPageOverflow(page, 'refinements/candidates/320/200%')
    checks.push('320/200% long source title: two-line preview, full expansion, collapse; oversized header scrolls away')

    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => { document.documentElement.style.fontSize = ''; window.scrollTo(0, 0) })
    await capture(page, 'candidates-390')
    const firstCandidate = await page.locator('.candidate-item').first().boundingBox()
    const actionbar = await page.locator('.m-actionbar').boundingBox()
    assert.ok(firstCandidate && actionbar && firstCandidate.y + firstCandidate.height + 48 <= actionbar.y, 'first candidate summary must leave one touch row of reading space above the primary action at 390px')
    // Switching sources must reset expansion and keep identical source types distinct.
    await name.getByRole('button', { name: '展开完整名称' }).click()
    await page.locator('.source-tabs button').nth(1).click()
    assert.equal(await page.locator('.source-context-title').innerText(), '示例隐私政策')
    await page.locator('.source-tabs button').first().click()
    assert.equal(await name.getByRole('button', { name: '展开完整名称' }).getAttribute('aria-expanded'), 'false')
    checks.push('390px candidate summary above the fold; source changes retain identity and reset disclosure')

    await page.locator('#candidate-purpose').fill('保留这段尚未保存的修改')
    await page.evaluate(() => { globalThis.rejectSave = true })
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.getByText(/本次保存未获得确认/).waitFor()
    assert.equal(await page.locator('#candidate-purpose').inputValue(), '保留这段尚未保存的修改')
    assert.equal(await page.getByText('已保存', { exact: true }).count(), 0)
    assert.equal(await page.locator('[role="alert"]').filter({ hasText: 'SERVER_BUSY' }).count(), 1, 'the flow error must be announced once')
    await capture(page, 'save-rejected-390')
    await page.evaluate(() => { globalThis.rejectSave = false })
    await page.getByRole('button', { name: '保存候选', exact: true }).click()
    await page.getByText('已保存', { exact: true }).waitFor()
    assert.equal(await page.evaluate(() => globalThis.mobileCalls.filter(call => call.args.action === 'start').length), 0, 'saving a candidate must not start an analysis')
    assert.equal(await page.locator('#candidate-purpose').inputValue(), '保留这段尚未保存的修改')
    const writesBeforeDelete = await page.evaluate(() => globalThis.mobileCalls.filter(call => call.args.action === 'candidates').length)
    await page.getByRole('button', { name: '删除候选', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'confirm-delete-candidate')
    await assertDeleteControlsReachable(page)
    await capture(page, 'candidate-delete-confirm-390')
    await page.getByRole('button', { name: '取消删除', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'delete-candidate')
    assert.equal(await page.evaluate(() => globalThis.mobileCalls.filter(call => call.args.action === 'candidates').length), writesBeforeDelete)
    assert.equal(await page.locator('#candidate-purpose').inputValue(), '保留这段尚未保存的修改')
    checks.push('delete confirmation names its scope; cancelling retains edits, sends no write and restores focus')
    await page.setViewportSize({ width: 320, height: 568 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '200%' })
    await page.getByRole('button', { name: '删除候选', exact: true }).click()
    await assertDeleteControlsReachable(page)
    await capture(page, 'candidate-delete-confirm-320-200')
    await page.getByRole('button', { name: '取消删除', exact: true }).click()
    await page.setViewportSize({ width: 390, height: 844 })
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    await page.getByRole('button', { name: '保存并分析', exact: true }).click()
    await helpers.waitTitle(page, '扫描与对照进度')
    assert.equal(await page.evaluate(() => globalThis.mobileCalls.filter(call => call.args.action === 'start').length), 1)
    checks.push('native save rejected then retried: edits retained, no false success, one flow error; only 保存并分析 creates a job')

    await page.getByRole('button', { name: 'APK 与政策材料', exact: true }).click()
    await helpers.waitTitle(page, 'APK 与政策材料')
    const hash = page.locator('.m-hash').first()
    await hash.locator('summary').click()
    await hash.getByRole('button', { name: '复制完整值', exact: true }).click()
    await hash.getByRole('status').filter({ hasText: '未能复制' }).waitFor()
    assert.equal(await hash.locator('.m-hash-full').innerText(), 'c'.repeat(128), 'copy failure must retain the full selectable hash')
    await capture(page, 'hash-copy-failed-390')
    await page.evaluate(() => { globalThis.rejectClipboard = false })
    await hash.getByRole('button', { name: '复制完整值', exact: true }).click()
    await hash.getByRole('status').filter({ hasText: '已复制' }).waitFor()
    assert.equal(await page.evaluate(() => globalThis.copiedHash), 'c'.repeat(128))
    checks.push('clipboard denial is visible and retry copies the entire hash')
    await hash.locator('summary').click()
    await page.evaluate(() => window.scrollTo(0, 0))
    await capture(page, 'import-390')
    const writesBeforeRemoval = await page.evaluate(() => globalThis.mobileCalls.length)
    await page.getByRole('button', { name: '删除已上传材料', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'm-confirm-remove')
    await capture(page, 'material-delete-confirm-390')
    await page.getByRole('button', { name: '取消', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'm-remove')
    assert.equal(await page.evaluate(() => globalThis.mobileCalls.length), writesBeforeRemoval, 'cancelling deletion must not call the bridge')
    await page.getByRole('button', { name: '服务与存储设置', exact: true }).click()
    const settings = page.getByRole('dialog')
    await settings.getByRole('button', { name: '删除已上传材料', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'm-settings-confirm-remove')
    await settings.getByRole('button', { name: '取消', exact: true }).click()
    assert.equal(await page.evaluate(() => document.activeElement.id), 'm-settings-remove')
    checks.push('material deletion in import and settings focuses confirmation; cancelling restores trigger without deleting')
    assert.deepEqual(errors, [])
  } finally {
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify({ source_sha: sha, dirty, captured_at: new Date().toISOString(), platform: 'Chromium + mocked native bridge; Android/IME/TalkBack NOT_RUN', checks, captures, errors }, null, 2) + '\n')
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
  console.log(`${checks.length} refinement checks passed; ${captures.length} screenshots; source ${sha}; dirty=${dirty}`)
}
main().catch(error => { console.error(error); process.exitCode = 1 })
