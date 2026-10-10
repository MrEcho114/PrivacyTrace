// Actual browser check of source-built reports. No synthetic report seeding.
const assert = require('node:assert/strict')
const fs = require('node:fs')
const net = require('node:net')
const path = require('node:path')
const { spawn, execFileSync } = require('node:child_process')
const root = path.resolve(__dirname, '..')
const { chromium } = require(path.join(root, 'tmp/pt910-playwright/node_modules/playwright'))
const output = path.join(root, 'tmp/pt910-acceptance/browser')
const python = path.join(root, 'apps/api/.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
const store = path.join(root, 'data/pt910-ci-jobs')
const children = []
const logs = []

async function available(port) {
  await new Promise((resolve, reject) => {
    const server = net.createServer()
    server.once('error', reject)
    server.listen(port, '127.0.0.1', () => server.close(resolve))
  })
}

function start(command, args, cwd, name) {
  const child = spawn(command, args, { cwd, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'] })
  const log = fs.createWriteStream(path.join(output, name + '.log'))
  child.stdout.pipe(log)
  child.stderr.pipe(log)
  child.on('error', error => { child.startError = error })
  children.push(child)
  logs.push(log)
  return child
}

async function ready(url, child) {
  for (let attempt = 0; attempt < 120; attempt++) {
    if (child.startError || child.exitCode !== null) throw child.startError ?? new Error('Server exited')
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 250))
  }
  throw new Error('Server did not become ready: ' + url)
}

async function main() {
  await Promise.all([available(8000), available(5173)])
  fs.mkdirSync(output, { recursive: true })
  const receipt = { commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    browser: null, cases: [], pageErrors: [], consoleErrors: [], status: 'FAILED' }
  let browser
  try {
    const api = start(python, ['-c',
      'from pathlib import Path; import sys,uvicorn; from privacytrace.main import create_app; uvicorn.run(create_app(store_root=Path(sys.argv[1])),host="127.0.0.1",port=8000)',
      store], root, 'api')
    await ready('http://127.0.0.1:8000/api/v1/health', api)
    const web = start(process.execPath, [path.join(root, 'node_modules/vite/bin/vite.js'),
      '--host', '127.0.0.1', '--port', '5173', '--strictPort'], path.join(root, 'apps/web'), 'web')
    await ready('http://127.0.0.1:5173', web)
    browser = await chromium.launch({ headless: true })
    receipt.browser = await browser.version()
    const page = await browser.newPage({ viewport: { width: 1440, height: 1000 } })
    page.on('pageerror', error => receipt.pageErrors.push(error.message))
    page.on('console', event => { if (event.type() === 'error') receipt.consoleErrors.push(event.text()) })
    await page.goto('http://127.0.0.1:5173', { waitUntil: 'networkidle' })
    for (const [id, type, expected, text] of [
      ['C02', 'CAMERA', 'EXACT_MATCH', '具体类型已声明'],
      ['C06', 'MICROPHONE', 'INSUFFICIENT_EVIDENCE', '证据不足'],
    ]) {
      const reportResponse = await fetch('http://127.0.0.1:8000/api/v1/jobs/pt910-' + id + '/report')
      assert.equal(reportResponse.status, 200)
      const report = await reportResponse.json()
      const accessIds = new Set(report.behaviors.filter(b => b.action === 'ACCESS' && b.data_type === type).map(b => b.id))
      const index = report.result.issues.findIndex(i => accessIds.has(i.behavior_id))
      assert.ok(index >= 0)
      assert.equal(report.result.issues[index].status, expected)
      await page.locator('#report-source').selectOption('job:pt910-' + id)
      await page.getByRole('heading', { name: report.sample.name, exact: true }).waitFor()
      assert.match(await page.locator('aside.demo-note').innerText(), new RegExp('受控源码场景 ' + id))
      const row = page.locator('tbody tr').nth(index)
      assert.ok((await row.innerText()).includes(text))
      await row.getByRole('button').click()
      await page.locator('#evidence-panel').waitFor()
      assert.match(await page.locator('#evidence-panel').innerText(), /目标：/)
      const sourceSentence = id === 'C02' ? '本场景声明访问相机。' : '本场景声明访问麦克风。'
      assert.ok((await page.locator('#evidence-panel').innerText()).includes(sourceSentence))
      if (id === 'C06') assert.match(await page.locator('.explanation').innerText(), /适用范围尚未确认/)
      await page.locator('details.provenance > summary').click()
      await page.locator('details.provenance article details > summary').first().click()
      assert.ok((await page.locator('details.provenance article pre').innerText()).includes(sourceSentence))
      await page.screenshot({ path: path.join(output, id + '.png'), fullPage: true })
      receipt.cases.push({ case_id: id, status: expected, job_id: report.job.id,
        apk_sha256: report.sample.apk_sha256, evidence_navigation: 'PASSED', policy_text: 'PASSED' })
    }
    assert.deepEqual(receipt.pageErrors, [])
    assert.deepEqual(receipt.consoleErrors, [])
    receipt.status = 'PASSED'
    console.log(JSON.stringify(receipt))
  } finally {
    if (browser) await browser.close()
    for (const child of children) if (child.exitCode === null) child.kill()
    for (const log of logs) log.end()
    fs.writeFileSync(path.join(output, 'receipt.json'), JSON.stringify(receipt, null, 2) + '\n')
  }
}
main().catch(error => { console.error(error); process.exitCode = 1 })
