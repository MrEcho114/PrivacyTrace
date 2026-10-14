// Actual browser -> HTTP intake -> policy/model seam -> restricted Docker -> persisted report.
// Default policy/DNS/model fixtures are explicit. --public uses public HTML and a real configured model.
const fs = require('node:fs')
const path = require('node:path')
const os = require('node:os')
const assert = require('node:assert/strict')
const { spawn, execFileSync } = require('node:child_process')
const { chromium } = require('playwright')
const { spawnOptions, stopChildren } = require('./lib/process-control.cjs')
const { assertDesign } = require('./lib/frontend-guards.cjs')
const root = path.resolve(__dirname, '..')
const publicMode = process.argv.includes('--public')
const apiPort = Number(process.env.PRIVACYTRACE_LIVE_API_PORT || 8134)
const webPort = Number(process.env.PRIVACYTRACE_LIVE_WEB_PORT || 5284)
const api = `http://127.0.0.1:${apiPort}`
const web = `http://127.0.0.1:${webPort}`
const output = path.join(root, 'tmp/issue44-live-proof', publicMode ? 'public' : 'fixtures')
const widths = [[1440, 900], [1920, 1080], [1280, 720], [768, 1024], [390, 844]]
async function ready(url, child) {
  const deadline = Date.now() + 30000
  while (Date.now() < deadline) {
    if (child.exitCode !== null) throw new Error('Owned service exited during startup')
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return } catch {}
    await new Promise(resolve => setTimeout(resolve, 200))
  }
  throw new Error('Owned service startup timed out')
}
async function main() {
  fs.mkdirSync(output, { recursive: true })
  const store = fs.mkdtempSync(path.join(os.tmpdir(), 'privacytrace-live-'))
  const children = []; let browser
  const errors = []; let proof = { passed: false, commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(), policy_model_mode: publicMode ? 'PUBLIC_HTML_AND_REAL_MODEL' : 'LOCAL_HTTP_FIXTURES_WITH_TEST_DNS_TARGET', apk_mode: 'CONSTRUCTED_BINARY_APK_ON_ORDINARY_LANE', scanner: 'RESTRICTED_DOCKER' }
  try {
    for (const url of [api + '/api/v1/health', web]) { try { await fetch(url, { signal: AbortSignal.timeout(1000) }); throw new Error('Acceptance port occupied: ' + url) } catch (e) { if (!['TypeError', 'TimeoutError'].includes(e.name)) throw e } }
    const apk = path.join(store, 'constructed.apk')
    execFileSync('uv', ['run', '--project', 'apps/api', '--locked', 'python', '-c', "import sys;sys.path.insert(0,'apps/api/tests');from pathlib import Path;from apk_fixture_builder import apk;apk(Path(sys.argv[1]))", apk], { cwd: root, stdio: 'pipe' })
    const modelEnv = publicMode ? {
      PRIVACYTRACE_LLM_ENABLED: '1', PRIVACYTRACE_LLM_API_BASE: process.env.PRIVACYTRACE_LLM_API_BASE || 'https://api.deepseek.com',
      PRIVACYTRACE_LLM_MODEL: process.env.PRIVACYTRACE_LLM_MODEL || 'deepseek-flash', PRIVACYTRACE_LLM_API_KEY: process.env.PRIVACYTRACE_LLM_API_KEY || process.env.DEEPSEEK_API_KEY || '',
    } : { PRIVACYTRACE_LLM_ENABLED: '1', PRIVACYTRACE_LLM_API_BASE: api + '/v1', PRIVACYTRACE_LLM_MODEL: 'http-fixture', PRIVACYTRACE_LLM_API_KEY: '' }
    const backend = spawn(`uv run --project apps/api --locked uvicorn ${publicMode ? 'privacytrace.main:app' : 'live_acceptance_app:app --app-dir scripts'} --host 127.0.0.1 --port ${apiPort}`, spawnOptions(root, { ...modelEnv, PRIVACYTRACE_STORE_ROOT: store, PRIVACYTRACE_LIVE_API_PORT: String(apiPort) }))
    children.push(backend)
    // Logs contain only paths/statuses; never response bodies or credentials. Retain locally on failure.
    backend.stdout.on('data', c => fs.appendFileSync(path.join(output, 'server.log'), c))
    backend.stderr.on('data', c => fs.appendFileSync(path.join(output, 'server.log'), c))
    await ready(api + '/api/v1/health', backend)
    const frontend = spawn('npm run dev', spawnOptions(root, { PRIVACYTRACE_API_ORIGIN: api, PRIVACYTRACE_WEB_PORT: String(webPort) }))
    children.push(frontend); frontend.stdout.resume(); frontend.stderr.resume(); await ready(web, frontend)
    browser = await chromium.launch({ headless: true })
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
    page.on('pageerror', e => errors.push(e.message))
    await page.goto(web); await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor()
    await page.locator('input[accept=".apk"]').setInputFiles(apk)
    await page.getByLabel('来源名称', { exact: true }).first().fill(publicMode ? 'GKD 公开政策' : '人工政策 A')
    await page.getByLabel('政策网址', { exact: true }).first().fill(publicMode ? 'https://gkd.li/guide/privacy' : 'http://policy.privacytrace.test/policy/host')
    await page.getByRole('button', { name: '添加政策来源', exact: true }).click()
    await page.getByLabel('来源名称', { exact: true }).nth(1).fill(publicMode ? 'Mozilla 网站政策' : '人工政策 B')
    await page.getByLabel('来源类型', { exact: true }).nth(1).selectOption(publicMode ? 'OFFICIAL_WEB_POLICY' : 'SDK_POLICY')
    await page.getByLabel('政策网址', { exact: true }).nth(1).fill(publicMode ? 'https://www.mozilla.org/en-US/privacy/websites/' : 'http://policy.privacytrace.test/policy/sdk')
    await page.getByRole('button', { name: '添加政策来源', exact: true }).click()
    await page.getByLabel('来源名称', { exact: true }).nth(2).fill('失败来源保留')
    await page.getByLabel('政策网址', { exact: true }).nth(2).fill('http://127.0.0.1/private')
    await page.getByRole('button', { name: '获取政策并检查候选', exact: true }).click()
    await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor({ timeout: 90000 })
    await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).waitFor({ state: 'visible' })
    await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'), null, { timeout: 240000 })
    const draftId = await page.evaluate(() => localStorage.getItem('privacytrace.live.draft.v1'))
    const read = () => fetch(api + '/api/v1/web/drafts/' + draftId).then(r => r.json())
    let draft = await read()
    proof.sources = draft.sources.map(s => ({ title: s.title, status: s.status, model_audit: s.model_audit }))
    proof.candidates = draft.candidates.length
    assert.equal(draft.sources.length, 3)
    assert.equal(draft.sources.filter(s => s.status === 'ready').length, 2)
    assert.equal(draft.sources[2].status, 'failed')
    assert(draft.sources.filter(s => s.status === 'ready').every(s => s.model_audit?.attempts > 0), 'model seam must execute requests')
    await page.locator('.source-tabs button').first().click()
    await page.waitForFunction(() => {
      const button = document.querySelector('.flow-footer .primary:not(:disabled)')
      return button && getComputedStyle(button).backgroundColor === 'rgb(51, 60, 80)'
    })
    for (const [width, height] of widths) {
      await page.setViewportSize({ width, height }); await page.evaluate(() => document.fonts.ready)
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
      await page.screenshot({ path: path.join(output, `candidates-${width}.png`), fullPage: true }); await assertDesign(page)
    }
    await page.setViewportSize({ width: 1440, height: 900 })
    const count = draft.candidates.length
    assert(count > 0, 'at least one verified model candidate must reach the editor')
    if (!publicMode) {
      await page.locator('.source-tabs button').first().click()
      await page.locator('.candidate-item').first().click()
      await page.getByLabel('条件', { exact: true }).fill('拍照时')
      await page.getByRole('button', { name: '保存候选', exact: true }).click()
      await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'))
      await page.getByRole('button', { name: '添加候选', exact: true }).click()
      await page.getByLabel('政策原句', { exact: true }).fill('我们不会读取联系人。')
      await page.getByLabel('数据类型', { exact: true }).selectOption('CONTACTS')
      await page.getByLabel('声明方式', { exact: true }).selectOption('NEGATED')
      await page.getByLabel('声明主体', { exact: true }).selectOption('APP')
      await page.getByRole('button', { name: '保存候选', exact: true }).click()
      await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'))
      assert.equal((await read()).candidates.length, count + 1)
      await page.getByRole('button', { name: '删除候选', exact: true }).click()
      await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'))
      assert.equal((await read()).candidates.length, count)
    }
    for (const source of draft.sources.slice(0, 2)) {
      await page.locator('.source-tabs button').filter({ hasText: source.title }).click()
      const items = page.locator('.candidate-item')
      for (let i = 0; i < await items.count(); i++) {
        await items.nth(i).click()
        await page.getByRole('button', { name: '定位原句', exact: true }).click()
        assert(await page.locator('#candidate-quote-mark').evaluate(e => document.activeElement === e))
        await page.getByRole('button', { name: '保存候选', exact: true }).click()
        await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'))
      }
    }
    draft = await read(); assert(draft.candidates.every(c => c.checked))
    await page.reload(); await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor()
    await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click()
    await page.getByRole('heading', { name: '分析进度', exact: true }).waitFor()
    await page.reload(); await page.getByRole('heading', { name: '分析进度', exact: true }).waitFor()
    if (!publicMode) {
      await page.getByRole('button', { name: '取消分析', exact: true }).click()
      await page.getByRole('button', { name: '重新创建分析', exact: true }).waitFor()
      const cancelledDraft = await read()
      const cancelledJob = await fetch(api + '/api/v1/jobs/' + cancelledDraft.jobs[0].job_id).then(r => r.json())
      assert.equal(cancelledJob.state, 'CANCELLED')
      assert.equal(cancelledDraft.jobs.length, 1)
      await page.getByRole('button', { name: '重新创建分析', exact: true }).click()
    }
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 180000 })
    draft = await read(); const run = draft.jobs.at(-1); const job = await fetch(api + '/api/v1/jobs/' + run.job_id).then(r => r.json())
    assert.equal(job.state, 'SUCCEEDED', job.error)
    const report = await fetch(api + '/api/v1/jobs/' + job.id + '/report').then(r => r.json())
    assert.equal(report.policy_documents.length, 2)
    assert(report.policy_documents.every(d => d.review_status === 'UNREVIEWED' && d.completeness === 'PARTIAL' && d.attachments_status === 'NOT_CHECKED'))
    assert.equal(JSON.parse(report.tools.web_policy_sources).length, 3)
    assert.equal(JSON.parse(report.tools.web_policy_sources)[2].status, 'failed')
    assert(report.policy_claims.length > 0)
    assert.equal(report.delivery_mode, 'PERSISTED_REPLAY')
    assert.equal(draft.jobs.length, publicMode ? 1 : 2, 'refresh must not submit another scan')
    if (!publicMode) {
      const negative = report.policy_claims.find(c => c.data_type === 'CONTACTS')
      assert.equal(negative.polarity, 'NEGATIVE'); assert.equal(negative.subject, 'HOST_APP')
      const conditional = report.policy_claims.find(c => c.data_type === 'CAMERA')
      assert.equal(conditional.condition, '拍照时')
      const third = report.policy_claims.find(c => c.data_type === 'DEVICE_IDENTIFIER')
      assert.equal(third.subject, 'THIRD_PARTY'); assert.equal(third.document_id, 'web-' + draft.sources[1].id)
      for (const claim of report.policy_claims) {
        const doc = report.policy_documents.find(d => d.id === claim.document_id)
        for (const id of claim.evidence_ids) { const evidence = report.evidence.find(e => e.id === id); assert.equal(evidence.excerpt, [...doc.artifact.text].slice(evidence.start_offset, evidence.end_offset).join('')) }
      }
    }
    const isolation = JSON.parse(fs.readFileSync(report.tools.isolation_receipt, 'utf8'))
    assert(isolation.container_created && isolation.input_removed && isolation.cleanup_verified)
    await page.getByRole('button', { name: '查看报告', exact: true }).click()
    await page.getByRole('heading', { name: /^DEX 处理范围/ }).waitFor()
    const evidenceButton = page.locator('.evidence-button').first()
    await evidenceButton.click()
    await page.locator('#evidence-panel').waitFor()
    for (const [width, height] of widths) { await page.setViewportSize({ width, height }); assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)); await page.screenshot({ path: path.join(output, `report-${width}.png`), fullPage: true }) }
    assert.equal(errors.length, 0)
    if (!publicMode) {
      await page.setViewportSize({ width: 1440, height: 900 })
      await page.getByRole('button', { name: '新建材料版本', exact: true }).click()
      await page.locator('input[accept=".apk"]').setInputFiles(apk)
      const failedSource = page.locator('.source-editor').filter({ hasText: '失败来源保留' }).first()
      await failedSource.locator('summary').first().click()
      await failedSource.getByLabel('政策正文', { exact: true }).fill('手动补入：我们不会读取联系人。<script>window.privacytraceAttack=1</script>')
      await failedSource.getByRole('button', { name: '使用这份正文', exact: true }).click()
      await page.getByRole('button', { name: '获取政策并检查候选', exact: true }).click()
      await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor()
      await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'))
      const fallbackId = await page.evaluate(() => localStorage.getItem('privacytrace.live.draft.v1'))
      const fallback = await fetch(api + '/api/v1/web/drafts/' + fallbackId).then(r => r.json())
      assert.equal(fallback.sources[2].status, 'manual')
      assert.equal(await page.evaluate(() => window.privacytraceAttack), undefined)
      await page.getByRole('button', { name: '修改材料', exact: true }).click()
      await page.getByLabel('政策正文', { exact: true }).first().fill('修改后的政策正文')
      assert.equal(await page.getByRole('button', { name: '2 检查候选', exact: true }).isDisabled(), true)
      proof.browser_recovery = ['candidate edit/add/delete persisted', 'cancel then new retry job', 'manual text replaces failed source', 'material edits invalidate later steps', 'policy HTML rendered as text']
    }
    proof = { ...proof, passed: true, draft_revision: draft.revision, job_id: job.id, sources: draft.sources.map(s => ({ title: s.title, status: s.status, requested_url: s.url, final_url: s.final_url, hash: s.sha256, captured_at: s.captured_at, model_audit: s.model_audit })), candidates: count, events: run.events, isolation: { container_created: isolation.container_created, input_removed: isolation.input_removed, cleanup_verified: isolation.cleanup_verified }, page_errors: errors, viewports: widths.map(w => w[0]) }
    console.log(`Live flow passed (${proof.policy_model_mode}): ${count} candidates, two captured policies, retained failure, actual Docker, refreshed job and stored report.`)
  } finally {
    fs.writeFileSync(path.join(output, 'verification.json'), JSON.stringify(proof, null, 2))
    if (browser) await browser.close()
    const survivors = await stopChildren(children)
    // Delete only this newly allocated temporary store after every owned child stopped.
    if (!survivors.length && path.basename(store).startsWith('privacytrace-live-') && path.dirname(store) === os.tmpdir()) fs.rmSync(store, { recursive: true, force: true })
    else if (survivors.length) throw new Error('Owned acceptance children still running; private store preserved')
  }
}
main().catch(e => { console.error(e.message); process.exitCode = 1 })
