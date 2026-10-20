// Real local HTTP import + Chromium UI; synthetic policies only, no model or APK.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const net = require('node:net')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')
const { assertDesign } = require('./lib/frontend-guards.cjs')
const root = path.resolve(__dirname, '..')
const output = path.join(root, 'tmp/issue72-policy-assist')
fs.mkdirSync(output, { recursive: true })
async function freePort() {
  const server = net.createServer()
  await new Promise((resolve, reject) => { server.once('error', reject); server.listen(0, '127.0.0.1', resolve) })
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
async function ready(url, child) {
  const deadline = Date.now() + 45000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('Owned acceptance server exited before startup')
    try { if ((await fetch(url)).ok) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  throw new Error('Owned acceptance server did not become ready')
}
async function main() {
  const children = []; let browser
  const checks = []; const requests = []; const errors = []
  const proof = { result: 'FAIL', scope: 'real local JSON HTTP import and Chromium; synthetic text, no APK, scan, external chat or model', checks, requests }
  try {
    const apiPort = await freePort(), webPort = await freePort()
    const api = `http://127.0.0.1:${apiPort}`, origin = `http://127.0.0.1:${webPort}`
    const store = fs.mkdtempSync(path.join(output, 'private-synthetic-'))
    function start(command, env) {
      const child = spawn(command, { ...spawnOptions(root, env), windowsHide: true })
      children.push(child)
      child.stdout.on('data', chunk => fs.appendFileSync(path.join(output, 'servers.log'), chunk))
      child.stderr.on('data', chunk => fs.appendFileSync(path.join(output, 'servers.log'), chunk))
      return child
    }
    const backend = start(`uv run --project apps/api --locked uvicorn privacytrace.main:app --host 127.0.0.1 --port ${apiPort}`, {
      PRIVACYTRACE_STORE_ROOT: store, PRIVACYTRACE_MODE: 'local', PRIVACYTRACE_STORAGE: 'json', PRIVACYTRACE_EXECUTION: 'local', PRIVACYTRACE_LLM_ENABLED: '0', PRIVACYTRACE_LLM_API_KEY: '',
    })
    const frontend = start('npm run dev', { PRIVACYTRACE_API_ORIGIN: api, PRIVACYTRACE_WEB_PORT: String(webPort) })
    await Promise.all([ready(api + '/api/v1/health', backend), ready(origin, frontend)])
    browser = await chromium.launch({ headless: true, executablePath: process.env.PRIVACYTRACE_CHROMIUM || undefined })
    const context = await browser.newContext({ permissions: ['clipboard-read', 'clipboard-write'] })
    const page = await context.newPage()
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (request.url().includes('/api/')) requests.push(new URL(request.url()).pathname) })
    await page.goto(origin)
    await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    await page.locator('.policy-assist > summary').click()
    await page.getByLabel('要查找政策的应用', { exact: true }).fill('受控示例 org.example.synthetic')
    await page.getByRole('button', { name: '复制收集指令', exact: true }).click()
    const prompt = await page.getByLabel('完整收集指令', { exact: true }).inputValue()
    const canonical = fs.readFileSync(path.join(root, 'skills/privacytrace-policy-collector/COPY.txt'), 'utf8').replaceAll('\r\n', '\n')
    assert(prompt.startsWith(canonical))
    assert.equal((await page.evaluate(() => navigator.clipboard.readText())).replaceAll('\r\n', '\n'), prompt)
    checks.push('canonical COPY.txt copied with explicit app hint')
    const raw = page.getByLabel('回填政策收集结果', { exact: true })
    async function inspect(payload) { await raw.fill(JSON.stringify(payload)); await page.getByRole('button', { name: '检查回填内容', exact: true }).click() }
    const collection = results => ({ version: 'privacytrace-policy-collector/1', results })
    const source = (id, extra = {}) => ({ id, title: '合成来源 ' + id, text: 'We access precise location.', ...extra })
    await inspect({ version: 'future/2', results: [] })
    await page.getByRole('alert').filter({ hasText: '版本不支持' }).waitFor()
    assert(!requests.some(url => url.endsWith('/import-external')))
    await inspect(collection([{ state: 'PROVIDED', source: source('provided') }, { state: 'OFFLINE', source: null }]))
    await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
    await page.getByRole('alert').filter({ hasText: '确认来源类型' }).waitFor()
    assert(!requests.some(url => url.endsWith('/import-external')))
    await page.getByLabel('合成来源 provided：来源类型', { exact: true }).selectOption('SDK_POLICY')
    async function submit(status = 200) {
      const response = page.waitForResponse(r => r.url().endsWith('/import-external') && r.request().method() === 'POST')
      await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
      const result = await response; assert.equal(result.status(), status)
      await page.waitForFunction(() => !document.querySelector('.import-grid')?.hasAttribute('inert'))
      return result.json()
    }
    let draft = await submit()
    assert.equal(draft.sources.at(-1).source_type, 'SDK_POLICY')
    assert.equal(draft.sources.at(-1).provenance, 'EXTERNAL_CHAT_EXPORT')
    assert.equal(draft.sources.at(-1).text, 'We access precise location.')
    assert.equal(draft.sources.length, 2)
    assert.equal(draft.external_imports[0].results[1].source_id, null)
    const id = draft.id
    const read = () => fetch(api + '/api/v1/web/drafts/' + id).then(r => r.json())
    checks.push('explicit source-type choice; real collector import and null-source audit')
    const before = draft.revision
    await inspect({ ...collection([{ state: 'PROVIDED', source: source('invalid', { source_type: 'SDK_POLICY' }) }]), forbidden: true })
    await submit(422)
    assert.equal((await read()).revision, before)
    checks.push('unknown fields reach existing validator; failed batch is atomic')
    await inspect({ source: source('legacy', { source_type: 'IN_APP_POLICY' }), claims: [{ excerpt: 'We access precise location.', data_type: 'PRECISE_LOCATION', polarity: 'POSITIVE', subject: 'HOST_APP', action: 'ACCESS' }], summary: 'Synthetic summary is not policy text.' })
    draft = await submit()
    assert.equal(draft.candidates.length, 1); assert.equal(draft.candidates[0].checked, false)
    assert.equal(draft.sources.at(-1).text, 'We access precise location.')
    checks.push('legacy import retains verbatim quote, separate summary and unchecked candidate')
    await inspect(collection([{ state: 'OFFLINE', source: source('link', { source_type: 'STORE_POLICY', url: 'https://example.invalid/privacy', text: '' }) }]))
    draft = await submit(); assert.equal(draft.sources.at(-1).status, 'empty'); assert.equal(draft.sources.at(-1).sha256, null)
    checks.push('offline link is not represented as retrieved text')
    await inspect(collection([{ state: 'PROVIDED', source: source('provided', { source_type: 'SDK_POLICY' }) }]))
    await submit(409)
    assert.equal((await read()).revision, draft.revision)
    checks.push('duplicate source rejected without partial write')
    await inspect(collection([{ state: 'NOT_FOUND', source: null }]))
    draft = await submit(); assert.equal(draft.sources.length, 4)
    await page.getByRole('status').filter({ hasText: '尚未取得政策正文' }).waitFor()
    checks.push('no-source result remains audit only')
    // Hold an actual successful HTTP response to exercise cancel after commit.
    let release, saved
    const committed = new Promise(resolve => { saved = resolve })
    const held = new Promise(resolve => { release = resolve })
    await page.route('**/import-external', async route => { const response = await route.fetch(); saved(); await held; await route.fulfill({ response }).catch(() => {}) })
    await inspect(collection([{ state: 'PROVIDED', source: source('late', { source_type: 'SDK_POLICY' }) }]))
    await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
    await committed
    await page.getByRole('button', { name: '取消准备请求', exact: true }).click()
    await page.getByRole('status').filter({ hasText: '当前准备请求已取消' }).waitFor()
    release(); await page.unrouteAll({ behavior: 'wait' })
    assert.equal(await page.locator('#title-late').count(), 0)
    await page.getByRole('button', { name: '重新读取材料', exact: true }).click()
    await page.locator('#title-late').waitFor()
    checks.push('cancelled late response ignored; committed server result explicitly recoverable')
    for (const width of [1440, 390]) {
      await page.setViewportSize({ width, height: 900 }); await page.evaluate(() => document.fonts.ready)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.mouse.move(0, 0)
      await page.waitForFunction(() => [...document.querySelectorAll('.ui-button.primary:not(:disabled)')].every(button => getComputedStyle(button).backgroundColor === 'rgb(51, 60, 80)'))
      await assertDesign(page)
      await page.locator('.policy-assist').scrollIntoViewIfNeeded()
      await page.screenshot({ path: path.join(output, `assist-${width}-viewport.png`) })
      await page.evaluate(() => scrollTo(0, 0))
      await page.screenshot({ path: path.join(output, `assist-${width}-full.png`), fullPage: true })
    }
    await page.evaluate(() => { document.documentElement.style.fontSize = '24px' })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    assert(await page.locator('#text-source-1').evaluate(element => element.getBoundingClientRect().width > element.closest('.source-editor').getBoundingClientRect().width * 0.75), 'large-text policy field must remain readable, not collapse beside summary metadata')
    await page.screenshot({ path: path.join(output, 'assist-390-large-text.png'), fullPage: true })
    await page.locator('#text-source-1').scrollIntoViewIfNeeded()
    await page.screenshot({ path: path.join(output, 'assist-390-large-text-viewport.png') })
    checks.push('1440/390 layouts and 150% root font fit viewport')
    await page.reload()
    await page.getByLabel('政策正文', { exact: true }).filter({ visible: true }).first().waitFor()
    assert.equal(await page.evaluate(() => localStorage.getItem('privacytrace.live.draft.v1')), id)
    assert.equal(await page.getByLabel('回填政策收集结果', { exact: true }).inputValue(), '')
    assert(!(await page.evaluate(() => JSON.stringify(localStorage))).includes('We access'))
    assert.equal(await page.locator('#title-late').count(), 1)
    assert.deepEqual(errors, [])
    assert(!requests.some(url => /settings|\/apk$|\/extract$|\/start$/.test(url)))
    const hash = require('node:crypto').createHash('sha256')
    for (const name of fs.readdirSync(path.join(root, 'apps/web/src'), { recursive: true }).filter(name => fs.statSync(path.join(root, 'apps/web/src', name)).isFile()).sort()) hash.update(name).update(fs.readFileSync(path.join(root, 'apps/web/src', name)))
    proof.result = 'PASS'; proof.source_sha256 = hash.digest('hex')
    proof.head = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim()
    proof.dirty = !!execFileSync('git', ['status', '--porcelain'], { encoding: 'utf8' }).trim()
    checks.push('reload preserves server draft only; no external text in browser storage; zero page errors')
    console.log(`Policy assist: ${checks.length} real HTTP/UI checks passed; no model or APK requests.`)
  } catch (error) { proof.failure = error.message; throw error }
  finally {
    await browser?.close()
    const survivors = await stopChildren(children)
    if (survivors.length) { proof.result = 'FAIL'; proof.cleanup = 'Owned child survived'; throw new Error(proof.cleanup) }
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(proof, null, 2))
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
