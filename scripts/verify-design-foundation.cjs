const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const crypto = require('node:crypto')
const { spawn } = require('node:child_process')
const { chromium } = require('playwright')
const { stopChildren, spawnOptions } = require('./lib/process-control.cjs')

const root = path.resolve(__dirname, '..')
const output = path.join(root, 'tmp/concept-foundation')
fs.mkdirSync(output, { recursive: true })
const port = process.env.PRIVACYTRACE_DESIGN_PORT || '5192'
const origin = 'http://127.0.0.1:' + port
const checks = []
const captures = []
function check(name, condition) { assert.ok(condition, name); checks.push(name) }
async function capture(page, name, fullPage = true) {
  const filename = name + '.png'
  await page.screenshot({ path: path.join(output, filename), fullPage })
  captures.push({ file: filename, viewport: page.viewportSize(),
    sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(output, filename))).digest('hex') })
}
async function noOverflow(page, label) {
  const dimensions = await page.evaluate(() => ({ width: innerWidth, scroll: document.documentElement.scrollWidth }))
  check('no overflow: ' + label + ' ' + JSON.stringify(dimensions), dimensions.scroll <= dimensions.width)
}
async function designContract(page) {
  const actual = await page.evaluate(() => {
    const style = selector => getComputedStyle(document.querySelector(selector))
    return {
      body: style('body').backgroundColor,
      paper: style('.pt-panel').backgroundColor,
      header: style('.pt-masthead').backgroundColor,
      primary: style('.ui-button.primary').backgroundColor,
      ink: style('.ui-button.primary').color,
      stripes: [...document.querySelectorAll('.pt-identity i')].map(item => getComputedStyle(item).backgroundColor),
      priority: [...document.querySelectorAll('.pt-priority-stripe i')].map(item => getComputedStyle(item).backgroundColor),
      priorityCount: document.querySelectorAll('.pt-priority-stripe').length,
      displayFont: style('h1').fontFamily,
      bodyFont: style('.pt-subtitle').fontFamily,
      codeFont: style('.pt-code').fontFamily,
      panelBorder: style('.pt-panel').borderTopWidth,
      radius: style('.pt-panel').borderTopLeftRadius,
    }
  })
  assert.ok(['rgba(0, 0, 0, 0)', 'rgb(255, 255, 255)'].includes(actual.body), 'body paper')
  assert.equal(actual.paper, 'rgb(255, 255, 255)', 'white content panels')
  assert.equal(actual.header, 'rgb(236, 229, 214)', 'cream header only')
  assert.equal(actual.primary, 'rgb(214, 58, 44)', 'source-bound primary red')
  assert.equal(actual.ink, 'rgb(255, 255, 255)', 'primary white text')
  assert.deepEqual(actual.stripes, ['rgb(76, 90, 104)', 'rgb(122, 127, 78)', 'rgb(210, 168, 94)', 'rgb(168, 67, 47)'])
  assert.deepEqual(actual.priority, actual.stripes, 'highest-information panel uses approved four-colour marker')
  assert.equal(actual.priorityCount, 1, 'exactly one highest-information region per page')
  assert.ok(actual.displayFont.startsWith('"Noto Serif SC"'), 'Pioneer display serif reused')
  assert.ok(actual.bodyFont.startsWith('"Noto Sans SC"'), 'Pioneer body sans reused')
  assert.ok(actual.codeFont.startsWith('Consolas'), 'Pioneer code mono reused')
  assert.equal(actual.panelBorder, '1px'); assert.equal(actual.radius, '0px')
}
async function main() {
  const server = spawn(process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'), 'preview', '--host', '127.0.0.1', '--port', port, '--strictPort'],
    { ...spawnOptions(path.join(root, 'apps/web')), shell: false, windowsHide: true })
  let log = ''
  server.stdout.on('data', chunk => { log += chunk })
  server.stderr.on('data', chunk => { log += chunk })
  let browser
  const errors = [], apiRequests = []
  try {
    let ready = false
    for (let i = 0; i < 100; i++) {
      try { if (log.includes(origin) && (await fetch(origin + '/design.html')).ok) { ready = true; break } } catch {}
      if (server.exitCode != null) throw new Error(log)
      await new Promise(resolve => setTimeout(resolve, 100))
    }
    assert.ok(ready, 'owned built preview starts: ' + log)
    browser = await chromium.launch({ headless: true })
    const page = await browser.newPage()
    page.on('pageerror', error => errors.push(String(error)))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api')) apiRequests.push(request.url()) })
    for (const [width, height] of [[1440, 1096], [1280, 720], [768, 1024], [390, 844], [320, 740]]) {
      await page.setViewportSize({ width, height })
      for (const gallery of [false, true]) {
        const label = (gallery ? 'components' : 'report') + '-' + width
        await page.goto(origin + '/design.html' + (gallery ? '?view=components' : ''))
        await page.evaluate(() => document.fonts.ready)
        await noOverflow(page, label)
        await designContract(page)
        checks.push('computed visual contract: ' + label)
        await capture(page, label)
        if (!gallery) {
          await capture(page, label + '-viewport', false)
          const evidence = page.getByRole('region', { name: '证据详情', exact: true })
          const trigger = page.getByRole('button', { name: '查看对应证据 ：设备标识', exact: true })
          if (width === 1280) {
            const first = await page.getByRole('button', { name: '查看对应证据 ：位置信息', exact: true }).boundingBox()
            check('1280 first full finding action in first fold', first && first.y + first.height <= height)
          }
          if (width <= 390) {
            const target = await page.getByRole('button', { name: '查看证据与政策原文', exact: true }).boundingBox()
            check(width + ' touch target >=48', target && target.height >= 48)
          }
          await trigger.click()
          await page.getByRole('heading', { name: '设备标识的对应证据' }).waitFor()
          check(label + ' selected evidence contains manifest', (await evidence.innerText()).includes('清单权限能力'))
          check(label + ' excludes other finding evidence', !(await evidence.innerText()).includes('LocationManager'))
          check(label + ' focus moved to evidence', await evidence.evaluate(el => el === document.activeElement))
          const box = await evidence.boundingBox()
          check(label + ' evidence scrolled into view', box && box.y >= 0 && box.y < height)
          await page.getByRole('button', { name: '返回刚才的操作' }).click()
          check(label + ' return restores trigger focus', await trigger.evaluate(el => el === document.activeElement))
          await page.getByRole('button', { name: '查看证据与政策原文', exact: true }).click()
          check(label + ' primary opens policy', await page.locator('.pt-policy-details').evaluate(el => el.open))
          check(label + ' policy retains unknown/review/attachment boundaries', (await evidence.innerText()).includes('附件') && (await evidence.innerText()).includes('UNREVIEWED'))
        }
      }
    }
    for (const state of ['empty', 'unknown', 'long']) {
      await page.setViewportSize({ width: 320, height: 740 })
      await page.goto(origin + '/design.html?state=' + state)
      await page.evaluate(() => document.fonts.ready)
      await noOverflow(page, state)
      if (state === 'empty') check('empty disables action and metrics zero', await page.getByRole('button', { name: '查看证据与政策原文', exact: true }).isDisabled() && (await page.locator('.pt-metric-value').allTextContents()).every(text => text === '00'))
      if (state === 'unknown') check('unknown source and delivery not promoted', (await page.locator('.pt-title-row .status-tag').innerText()).includes('UNKNOWN'))
      if (state === 'unknown') check('unknown finding review remains unknown', (await page.locator('.pt-findings .pt-tags').allTextContents()).every(text => text.includes('UNKNOWN') && !text.includes('UNREVIEWED')))
      await capture(page, state + '-320')
    }
    for (const width of [390, 320]) {
      for (const gallery of [false, true]) {
        await page.setViewportSize({ width, height: 844 })
        await page.goto(origin + '/design.html' + (gallery ? '?view=components' : '?state=long'))
        await page.addStyleTag({ content: 'html { font-size: 200% !important; }' })
        await noOverflow(page, '200% ' + width + (gallery ? ' gallery' : ' report'))
        const readable = await page.locator(gallery ? '.pt-swatches li' : '.pt-metrics > div').evaluateAll(cells => cells.every(cell => cell.getBoundingClientRect().width >= Math.min(5.5 * parseFloat(getComputedStyle(document.documentElement).fontSize), cell.parentElement.getBoundingClientRect().width - 2)))
        check('large text readable cells ' + width + (gallery ? ' gallery' : ' report'), readable)
        await capture(page, 'large-text-' + width + (gallery ? '-gallery' : '-report'))
      }
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.goto(origin + '/design.html?view=components')
    await page.getByRole('button', { name: '校验示例字段' }).click()
    check('field error association', await page.locator('#design-note').getAttribute('aria-invalid') === 'true' && await page.locator('#design-note').getAttribute('aria-describedby') === 'design-note-help')
    await page.locator('#design-note').fill('材料备注')
    await page.getByRole('status').waitFor()
    check('field correction announced', !(await page.locator('#design-note').getAttribute('aria-invalid')))
    await page.getByRole('button', { name: '演示等待状态' }).click()
    check('busy state disabled and announced', await page.locator('[aria-busy="true"]').isDisabled())
    await page.getByRole('button', { name: '结束等待演示' }).click()
    check('waiting demo explicitly cancellable', await page.locator('[aria-busy="true"]').count() === 0)
    await page.goto(origin + '/design.html')
    await page.keyboard.press('Tab')
    check('keyboard skip link', await page.getByRole('link', { name: '跳到主要内容' }).evaluate(el => el === document.activeElement))
    await page.keyboard.press('Enter')
    check('skip link focus main', await page.locator('main').evaluate(el => el === document.activeElement))
    await page.emulateMedia({ reducedMotion: 'reduce' })
    await page.getByRole('button', { name: '查看对应证据 ：位置信息', exact: true }).click()
    check('reduced motion evidence focus', await page.locator('.pt-evidence-target').evaluate(el => el === document.activeElement && getComputedStyle(el).scrollBehavior === 'auto'))
    // Prove this guard rejects actual source drift; do not regenerate all contracts.
    for (const content of ['.pt-panel { background:#ece5d6 !important }', '.ui-button.primary { background:blue !important }', '.pt-identity i { background:black !important }', '.pt-priority-stripe i { background:black !important }', 'h1 { font-family:Arial !important }']) {
      const style = await page.addStyleTag({ content })
      await assert.rejects(() => designContract(page))
      await style.evaluate(el => el.remove())
      checks.push('negative visual drift rejected: ' + content)
    }
    check('independent preview makes no API calls', apiRequests.length === 0)
    check('no browser errors', errors.length === 0)
    // Ensure the existing built app still resolves; no design root or styles leak.
    await page.goto(origin + '/')
    await page.locator('#app').waitFor()
    check('original runtime entry preserved', await page.locator('.pt-foundation').count() === 0)
    const sourcePaths = ['apps/web/design.html', 'apps/web/vite.config.ts', 'package.json', 'scripts/verify-design-foundation.cjs',
      ...fs.readdirSync(path.join(root, 'apps/web/src/design')).map(name => 'apps/web/src/design/' + name)]
    const sources = sourcePaths.sort().map(file => ({ file, sha256: crypto.createHash('sha256').update(fs.readFileSync(path.join(root, file))).digest('hex') }))
    const result = { kind: 'Built Chromium / synthetic design fixtures', generatedAt: new Date().toISOString(), sources, checks, captures, apiRequests, errors,
      notRun: ['Android APK/WebView', 'physical device', 'IME/safe-area/TalkBack', 'real scan or model service'] }
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(result, null, 2) + '\n')
    console.log(JSON.stringify({ passed: checks.length, screenshots: captures.length, evidence: 'tmp/concept-foundation/verification.json' }))
  } finally {
    await browser?.close()
    const survivors = await stopChildren([server])
    assert.equal(survivors.length, 0, 'owned preview cleaned up')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
