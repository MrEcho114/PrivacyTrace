// Real browser, production HTTP intake, authored local policy HTTP, real model,
// and restricted Docker. Captures are editorial replay of this recorded run.
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const { spawn, execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const { spawnOptions, stopChildren } = require('../../scripts/lib/process-control.cjs');
const root = path.resolve(__dirname, '../..');
const work = path.join(root, 'tmp/issue45-capture');
const assets = path.join(__dirname, 'assets/stills');
const apiPort = 8155, webPort = 5355;
const api = `http://127.0.0.1:${apiPort}`, web = `http://127.0.0.1:${webPort}`;
const hash = value => crypto.createHash('sha256').update(value).digest('hex');
async function ready(url, child) {
  for (let i = 0; i < 150; i++) {
    if (child.exitCode !== null) throw Error('Owned filming service exited');
    try { if ((await fetch(url, { signal: AbortSignal.timeout(1000) })).ok) return; } catch {}
    await new Promise(resolve => setTimeout(resolve, 200));
  }
  throw Error('Owned filming service did not become ready');
}
async function main() {
  if (!process.env.DEEPSEEK_API_KEY) throw Error('Existing authorized DeepSeek environment credential is required; no key value is printed or stored in the film.');
  fs.mkdirSync(work, { recursive: true }); fs.mkdirSync(assets, { recursive: true });
  const store = fs.mkdtempSync(path.join(work, 'store-'));
  const children = [], captures = [], errors = [];
  let browser, draft, report, job;
  const proof = { passed: false, source_commit: execFileSync('git', ['rev-parse', 'HEAD'], { cwd: root, encoding: 'utf8' }).trim(),
    recorded_at: new Date().toISOString(), policy_source_mode: 'AUTHORED_LOCAL_HTTP_FIXTURES_WITH_TEST_DNS',
    model_mode: 'REAL_DEEPSEEK_REQUEST', model: 'deepseek-flash', apk_mode: 'CONSTRUCTED_BINARY_ORDINARY_UPLOAD', scanner: 'RESTRICTED_DOCKER', captures, page_errors: errors };
  try {
    for (const url of [api + '/api/v1/health', web]) {
      try { await fetch(url, { signal: AbortSignal.timeout(1000) }); throw Error('Filming port occupied'); }
      catch (e) { if (!['TypeError', 'TimeoutError'].includes(e.name)) throw e; }
    }
    const apk = path.join(store, '受控位置样本.apk');
    execFileSync('uv', ['run', '--project', 'apps/api', '--locked', 'python', '-c',
      "import sys;sys.path.insert(0,'apps/api/tests');from pathlib import Path;from apk_fixture_builder import apk;apk(Path(sys.argv[1]),permission='android.permission.ACCESS_FINE_LOCATION')", apk], { cwd: root, stdio: 'pipe' });
    proof.apk_sha256 = hash(fs.readFileSync(apk));
    const backend = spawn(`uv run --project apps/api --locked uvicorn capture_app:app --app-dir showcase/privacytrace --host 127.0.0.1 --port ${apiPort}`,
      { ...spawnOptions(root, { PRIVACYTRACE_STORE_ROOT: store, PRIVACYTRACE_FILM_API_PORT: String(apiPort), PRIVACYTRACE_LLM_ENABLED: '1',
        PRIVACYTRACE_LLM_API_BASE: 'https://api.deepseek.com', PRIVACYTRACE_LLM_MODEL: 'deepseek-flash', PRIVACYTRACE_LLM_API_KEY: process.env.DEEPSEEK_API_KEY }), windowsHide: true });
    children.push(backend);
    backend.stdout.on('data', c => fs.appendFileSync(path.join(work, 'backend.log'), c));
    backend.stderr.on('data', c => fs.appendFileSync(path.join(work, 'backend.log'), c));
    await ready(api + '/api/v1/health', backend);
    const frontend = spawn('npm run dev', { ...spawnOptions(root, { PRIVACYTRACE_API_ORIGIN: api, PRIVACYTRACE_WEB_PORT: String(webPort) }), windowsHide: true });
    children.push(frontend); frontend.stdout.resume(); frontend.stderr.resume(); await ready(web, frontend);
    browser = await chromium.launch({ headless: true });
    const page = await browser.newPage({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    page.on('pageerror', e => errors.push(e.message));
    async function shot(name, section) {
      await page.evaluate(() => document.fonts.ready);
      const target = section ? page.locator(section) : page;
      if (section) await target.scrollIntoViewIfNeeded();
      const file = path.join(assets, name + '.png');
      await target.screenshot({ path: file, animations: 'disabled' });
      captures.push({ file: 'assets/stills/' + name + '.png', sha256: hash(fs.readFileSync(file)),
        viewport: [1440, 900], section: section || 'viewport', recorded_at: new Date().toISOString(), draft_revision: draft?.revision ?? null });
    }
    await page.goto(web); await page.getByRole('heading', { name: '导入分析材料', exact: true }).waitFor();
    await page.locator('input[accept=".apk"]').setInputFiles(apk);
    await page.getByLabel('来源名称', { exact: true }).first().fill('受控宿主政策');
    await page.getByLabel('政策网址', { exact: true }).first().fill('http://policy.privacytrace.test/policy/host');
    await page.getByRole('button', { name: '添加政策来源', exact: true }).click();
    await page.getByLabel('来源名称', { exact: true }).nth(1).fill('受控第三方政策');
    await page.getByLabel('来源类型', { exact: true }).nth(1).selectOption('SDK_POLICY');
    await page.getByLabel('政策网址', { exact: true }).nth(1).fill('http://policy.privacytrace.test/policy/sdk');
    await page.getByRole('button', { name: '添加政策来源', exact: true }).click();
    await page.getByLabel('来源名称', { exact: true }).nth(2).fill('失败来源保留');
    await page.getByLabel('政策网址', { exact: true }).nth(2).fill('http://127.0.0.1/private');
    await shot('import');
    await page.getByRole('button', { name: '获取政策并检查候选', exact: true }).click();
    await page.getByRole('heading', { name: '检查政策候选', exact: true }).waitFor({ timeout: 180000 });
    await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'), null, { timeout: 240000 });
    const draftId = await page.evaluate(() => localStorage.getItem('privacytrace.live.draft.v1'));
    const read = () => fetch(api + '/api/v1/web/drafts/' + draftId).then(r => r.json());
    draft = await read();
    assert.equal(draft.sources.filter(s => s.status === 'ready').length, 2);
    assert.equal(draft.sources[2].status, 'failed');
    assert(draft.sources.slice(0, 2).every(s => s.model_audit?.attempts > 0));
    assert(draft.candidates.length > 0);
    await page.locator('.source-tabs button').first().click();
    await page.locator('.candidate-item').first().click();
    await shot('candidates');
    await page.getByRole('button', { name: '定位原句', exact: true }).click();
    assert(await page.locator('#candidate-quote-mark').evaluate(e => document.activeElement === e));
    await shot('quote', '.candidate-grid');
    // Preserve actual model semantics; the edit makes a known authored condition more concise.
    const locationCandidate = draft.candidates.find(c => c.source_id === draft.sources[0].id && c.data_type === 'PRECISE_LOCATION');
    if (locationCandidate) {
      await page.locator('.candidate-item').filter({ hasText: locationCandidate.excerpt }).first().click();
      await page.getByLabel('条件', { exact: true }).fill('使用位置查询时');
      await shot('edit', '.candidate-grid');
      await page.getByRole('button', { name: '保存候选', exact: true }).click();
      await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'));
    }
    for (const source of draft.sources.slice(0, 2)) {
      await page.locator('.source-tabs button').filter({ hasText: source.title }).click();
      const items = page.locator('.candidate-item');
      for (let i = 0; i < await items.count(); i++) {
        await items.nth(i).click();
        await page.getByRole('button', { name: '保存候选', exact: true }).click();
        await page.waitForFunction(() => !document.querySelector('.candidate-grid')?.hasAttribute('inert'));
      }
      if (source.id === draft.sources[1].id) await shot('third-party', '.candidate-grid');
    }
    draft = await read(); assert(draft.candidates.every(c => c.checked));
    await page.getByRole('button', { name: '保存候选并开始分析', exact: true }).click();
    await page.getByRole('heading', { name: '分析进度', exact: true }).waitFor();
    await shot('progress');
    await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 180000 });
    draft = await read(); const run = draft.jobs.at(-1);
    job = await fetch(api + '/api/v1/jobs/' + run.job_id).then(r => r.json());
    assert.equal(job.state, 'SUCCEEDED', job.error);
    report = await fetch(api + '/api/v1/jobs/' + job.id + '/report').then(r => r.json());
    assert.equal(report.policy_documents.length, 2);
    assert(report.policy_documents.every(d => d.review_status === 'UNREVIEWED' && d.completeness === 'PARTIAL' && d.attachments_status === 'NOT_CHECKED'));
    const isolation = JSON.parse(fs.readFileSync(report.tools.isolation_receipt, 'utf8'));
    assert(isolation.container_created && isolation.input_removed && isolation.cleanup_verified);
    await shot('complete');
    await page.getByRole('button', { name: '查看报告', exact: true }).click();
    await page.getByRole('heading', { name: /^DEX 处理范围/ }).waitFor();
    await shot('report');
    const apiIssueIndex = report.result.issues.findIndex(i => i.evidence_ids.some(id => report.evidence.find(e => e.id === id)?.api_call));
    assert(apiIssueIndex >= 0, 'Actual report must contain an API evidence issue');
    await page.locator('.evidence-button').nth(apiIssueIndex).click();
    await page.locator('#evidence-panel').waitFor();
    await shot('evidence', '#evidence-panel');
    assert((await page.locator('#evidence-panel').innerText()).includes('getLastKnownLocation'));
    const fullPolicy = page.getByRole('button', { name: /全文与适用边界|完整政策与适用边界/ }).first();
    await fullPolicy.click(); await shot('source', '.provenance > article:first-of-type');
    proof.job_id = job.id; proof.draft_revision = draft.revision;
    proof.sources = draft.sources.map(s => ({ title: s.title, status: s.status, sha256: s.sha256, captured_at: s.captured_at, model_audit: s.model_audit }));
    proof.candidates = draft.candidates.map(c => ({ data_type: c.data_type, polarity: c.polarity, subject: c.subject, excerpt: c.excerpt, condition: c.condition, checked: c.checked }));
    proof.events = run.events; proof.isolation = { container_created: isolation.container_created, input_removed: isolation.input_removed, cleanup_verified: isolation.cleanup_verified };
    proof.api_evidence = report.evidence.filter(e => e.api_call).map(e => ({ id: e.id, source: e.source, locator: e.locator, target: e.api_call.target_descriptor }));
    proof.result_states = report.result.issues.map(i => ({ data_type: i.data_type, status: i.status }));
    assert.equal(errors.length, 0); proof.passed = true;
    fs.writeFileSync(path.join(__dirname, 'capture-provenance.json'), JSON.stringify(proof, null, 2) + '\n');
    console.log(JSON.stringify({ passed: true, shots: captures.length, candidate_count: draft.candidates.length, result_states: proof.result_states, isolation: proof.isolation }));
  } finally {
    fs.writeFileSync(path.join(work, 'capture-result.json'), JSON.stringify(proof, null, 2));
    if (browser) await browser.close();
    const survivors = await stopChildren(children);
    if (survivors.length) throw Error('Owned capture services still running; private store preserved');
    // Keep original APK and full report private in the ignored run directory for verification.
  }
}
main().catch(e => { console.error(e.message); process.exitCode = 1; });
