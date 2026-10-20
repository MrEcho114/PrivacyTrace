// Development walkthrough: real production Vue, mocked native bridge; no APK/model execution.
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
async function main() {
  const server = net.createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
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
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
    const errors = [], api = []
    page.on('pageerror', error => errors.push(error.message))
    page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) api.push(request.url()) })
    await page.addInitScript(({ reportFixture, taxonomyFixture, policySentence }) => {
      globalThis.isTauri = true
      const context = { origin: 'https://analysis.example/', draft: 'a'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false }
      const job = { ...reportFixture.job, id: 'b'.repeat(32), state: 'QUEUED' }
      const draft = { id: context.draft, name: 'com.example.mobile.ok', uploaded: true, revision: 1, apk_sha256: 'a'.repeat(64), sources: [], candidates: [], jobs: [] }
      const ledger = globalThis.mobileCalls = []
      let configured = false
      globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
        const method = command.split('|')[1]; ledger.push({ method, args })
        if (method === 'model_status') return { configured, endpoint: configured ? 'https://model.example/v1/chat/completions' : null }
        if (method === 'configure_model') { configured = true; return { configured, endpoint: 'https://model.example/v1/chat/completions' } }
        if (method === 'upload_selected' || method === 'refresh_upload') return context
        if (method === 'cancel') return
        if (method === 'collect_policy') return { text: JSON.stringify({ version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: { id: 'policy', title: '受控政策', source_type: 'OFFICIAL_WEB_POLICY', text: policySentence } }] }) }
        if (method !== 'workflow') throw new Error('Unexpected native method ' + method)
        const action = args.action, input = JSON.parse(args.payload)
        let data = draft
        if (action === 'taxonomy') data = taxonomyFixture
        else if (action === 'import') { draft.sources.push(...input.results.map(item => ({ ...item.source, status: 'manual', version: 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' }))); draft.revision++ }
        else if (action === 'extract') { draft.candidates = [{ id: 'candidate', source_id: 'policy', excerpt: policySentence, data_type: 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }]; draft.revision++ }
        else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision++ }
        else if (action === 'start') { draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: '2026-10-20T00:00:00Z' }] }); data = job }
        else if (action === 'job') { job.state = 'SUCCEEDED'; data = job }
        else if (action === 'report') { data = { ...reportFixture, job, demo: false, result: { ...reportFixture.result, job_id: job.id } } }
        else if (action !== 'read') throw new Error('Unexpected workflow action ' + action)
        return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) }
      } }
    }, fixtures)
    await page.goto(origin)
    await page.getByRole('button', { name: '选择应用并上传', exact: true }).click()
    await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor()
    await page.getByText('使用手机上的个人模型', { exact: true }).click()
    await page.getByRole('button', { name: '设置模型配置', exact: true }).click()
    await page.getByLabel('模型名称', { exact: true }).fill('compatible-chat')
    await page.getByLabel('应用名称或包名', { exact: true }).fill('com.example.mobile.ok')
    await page.getByRole('button', { name: '使用个人模型收集一次', exact: true }).click()
    await page.locator('.policy-assist > summary').click()
    await page.getByRole('button', { name: '检查回填内容', exact: true }).click()
    await page.getByRole('button', { name: '确认并补入材料', exact: true }).click()
    await page.getByText('受控政策', { exact: true }).first().waitFor()
    for (const width of [390, 1440]) {
      await page.setViewportSize({ width, height: 900 }); await page.evaluate(() => document.fonts.ready)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.screenshot({ path: path.join(output, `import-${width}.png`), fullPage: true })
    }
    await page.setViewportSize({ width: 390, height: 844 })
    await page.getByRole('button', { name: '自动准备政策并继续', exact: true }).click()
    await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor()
    await page.screenshot({ path: path.join(output, 'candidates-390.png'), fullPage: true })
    await page.evaluate(() => { document.documentElement.style.fontSize = '24px' })
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
    await page.screenshot({ path: path.join(output, 'candidates-large-text.png'), fullPage: true })
    await page.evaluate(() => { document.documentElement.style.fontSize = '' })
    await page.getByRole('button', { name: /开始.*分析/ }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 12000 })
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.getByRole('heading', { name: '手机端验收示例', exact: true }).waitFor()
    await page.locator('.evidence-button').first().click()
    await page.screenshot({ path: path.join(output, 'report-390.png'), fullPage: true })
    await page.getByRole('button', { name: '恢复当前实例材料', exact: true }).click()
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor()
    const ledger = await page.evaluate(() => globalThis.mobileCalls)
    const save = ledger.find(call => call.method === 'workflow' && call.args.action === 'candidates')
    assert.equal(JSON.parse(save.args.payload).candidates[0].checked, false)
    assert(ledger.some(call => call.method === 'workflow' && call.args.action === 'report'))
    assert.deepEqual(api, [], 'native snapshot report must not use browser HTTP credentials')
    assert.deepEqual(errors, [])
    fs.writeFileSync(path.join(output, 'walkthrough.json'), JSON.stringify({ result: 'PASS', scope: 'production Vue with mocked native bridge; no APK scan, paid model, or Android UI execution', ledger, browser_api_requests: api, page_errors: errors }, null, 2))
    console.log('Mobile development walkthrough passed: upload → model/JSON → prepare → unchecked candidates → analysis → evidence report → restore; zero browser API requests.')
  } finally {
    await browser?.close()
    if ((await stopChildren([child])).length) throw new Error('Owned Vite did not stop')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
