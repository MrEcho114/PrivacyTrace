// External observations only: production page, HTTP reports and real Chromium interactions.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');

async function main() {
  const output = process.argv[2] || 'tmp/browser-proof';
  fs.mkdirSync(output, { recursive: true });
  const browser = await chromium.launch({ headless: true,
    ...(process.env.PRIVACYTRACE_CHROMIUM ? { executablePath: process.env.PRIVACYTRACE_CHROMIUM } : {}) });
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  const errors = [];
  page.on('pageerror', error => errors.push(error.message));
  const checks = [];
  const jobs = (await (await fetch('http://127.0.0.1:8000/api/v1/jobs')).json()).jobs;
  const c02 = jobs.find(job => job.sample_id === 'C02');
  const c06 = jobs.find(job => job.sample_id === 'C06');
  assert(c02 && c06);
  const report = await (await fetch(`http://127.0.0.1:8000/api/v1/jobs/${c02.id}/report`)).json();
  const reportUrl = `**/api/v1/jobs/${c02.id}/report`;
  try {
    await page.goto('http://127.0.0.1:5173');
    await page.locator(`option[value="job:${c02.id}"]`).waitFor({ state: 'attached' });
    await page.locator('#report-source').selectOption(`job:${c02.id}`);
    await page.getByText('CONTROLLED_APK · 自建受控场景', { exact: true }).waitFor();
    await page.getByRole('row').filter({ hasText: '具体类型已声明' }).waitFor();
    await page.getByRole('row').filter({ hasText: '具体类型已声明' }).getByRole('button').click();
    const panel = page.locator('#evidence-panel');
    await panel.getByText(/getLastKnownLocation/).first().waitFor();
    assert((await panel.innerText()).includes('offset'));
    assert((await panel.innerText()).includes('我们访问精确位置。'));
    await panel.getByRole('button', { name: '完整政策与适用边界' }).first().click();
    await page.locator('.provenance pre').waitFor();
    assert((await page.locator('.provenance pre').innerText()).includes('无附件。'));
    checks.push('CLI actual APK -> persisted HTTP -> browser exact-match code/quote/full-policy drill-down');
    await page.screenshot({ path: path.join(output, 'controlled-c02.png'), fullPage: true });
    await page.locator('#report-source').selectOption(`job:${c06.id}`);
    await page.getByRole('heading', { name: 'C06', exact: true }).waitFor();
    assert.equal(await page.locator('#evidence-panel').count(), 0);
    assert((await page.locator('table').innerText()).includes('证据不足'));
    await page.locator('#report-source').selectOption('demo:synthetic');
    await page.getByRole('complementary').getByText('SYNTHETIC · 人工构造示例', { exact: true }).waitFor();
    checks.push('C06 cautious result, source switching resets drill-down, synthetic source distinct');

    const long = structuredClone(report);
    const original = long.policy_documents[0].artifact.text;
    long.policy_documents[0].artifact.text = original + '\n长文本🙂<img src=x onerror="window.injected=1">'.repeat(3500);
    long.policy_documents[0].artifact.sha256 = crypto.createHash('sha256')
      .update(long.policy_documents[0].artifact.text).digest('hex');
    const snapshot = long.evidence.find(item => item.kind === 'POLICY_DOCUMENT');
    snapshot.artifact_sha256 = long.policy_documents[0].artifact.sha256;
    long.policy_claims = Array.from({ length: 2000 }, (_, index) => ({ ...long.policy_claims[0], id: `ui-${index}` }));
    await page.route(reportUrl, route => route.fulfill({ json: long }));
    await page.locator('#report-source').selectOption(`job:${c02.id}`);
    await page.getByRole('row').filter({ hasText: '具体类型已声明' }).getByRole('button').click();
    await page.getByText(/共 2000 条/).waitFor();
    assert.equal(await page.locator('.candidate-clauses article').count(), 20);
    assert.equal(await page.locator('.provenance pre').count(), 0);
    await page.getByRole('button', { name: '下一页' }).click();
    await page.getByText(/第 2 \/ 100 页/).waitFor();
    await page.locator('#evidence-panel').getByRole('button', { name: '完整政策与适用边界' }).first().click();
    await page.locator('.provenance pre').waitFor();
    assert.equal(await page.locator('.provenance pre').count(), 1);
    assert.equal(await page.locator('.provenance img').count(), 0);
    assert.equal(await page.evaluate(() => window.injected), undefined);
    await page.setViewportSize({ width: 390, height: 844 });
    await page.screenshot({ path: path.join(output, 'long-text-mobile.png'), fullPage: true });
    assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth + 1));
    checks.push('UI fixture: 2000 candidates paginated, long policy lazy once, HTML rendered as text, 390px viewport');
    await page.screenshot({ path: path.join(output, 'long-text-mobile.png'), fullPage: true });
    await page.unroute(reportUrl);
    await page.route(reportUrl, route => route.fulfill({ status: 409, json: { detail: 'Rejected corrupted report' } }));
    await page.getByRole('button', { name: '刷新任务与报告' }).click();
    await page.getByRole('alert').waitFor();
    assert((await page.getByRole('alert').innerText()).includes('409'));
    checks.push('abnormal HTTP report rejected with visible retry');
    await page.unroute(reportUrl);
    await page.getByRole('button', { name: '重试', exact: true }).click();
    await page.getByRole('heading', { name: 'C02', exact: true }).waitFor();

    // A delayed response allows cancellation and source-switch races to be observed.
    await page.route(reportUrl, async route => {
      await new Promise(resolve => setTimeout(resolve, 1200));
      await route.fulfill({ json: report }).catch(() => {});
    });
    await page.getByRole('button', { name: '刷新任务与报告' }).click();
    await page.getByRole('button', { name: '停止本次请求' }).click();
    await page.getByRole('alert').filter({ hasText: '取消' }).waitFor();
    await page.locator('#report-source').selectOption(`job:${c06.id}`);
    await page.getByRole('heading', { name: 'C06', exact: true }).waitFor();
    await page.waitForTimeout(1400);
    assert.equal(await page.getByRole('heading', { name: 'C02', exact: true }).count(), 0);
    await page.unroute(reportUrl);
    checks.push('request cancellation, delayed old report cannot overwrite new source');

    await page.locator('#report-source').selectOption('job:ui-validation-failed');
    await page.locator('.job-state').getByText(/UI_VALIDATION_FAILURE/).waitFor();
    assert.equal(await page.locator('table').count(), 0);
    await page.locator('#report-source').selectOption('job:ui-validation-queued');
    await page.getByRole('button', { name: '取消任务', exact: true }).click();
    await page.locator('.job-state').getByText(/已取消/).waitFor();
    const cancelledJob = await (await fetch('http://127.0.0.1:8000/api/v1/jobs/ui-validation-queued')).json();
    assert.equal(cancelledJob.state, 'CANCELLED');
    checks.push('separate UI fixtures: failed job visible without report, actual HTTP cancel persisted CANCELLED');

    await page.setViewportSize({ width: 1280, height: 900 });
    await page.goto('http://127.0.0.1:8765');
    await page.getByText('OFFLINE REPLAY · 离线回放', { exact: true }).waitFor();
    assert.equal(await page.locator('.review-panel').count(), 0);
    assert.equal(await page.locator('option[value="demo:synthetic"]').count(), 0);
    for (const job of jobs.filter(item => item.input_mode === 'CONTROLLED_APK')) {
      await page.locator('#report-source').selectOption(`job:${job.id}`);
      await page.getByRole('heading', { name: job.sample_id, exact: true }).waitFor();
      assert((await page.getByLabel('报告生成来源').innerText()).includes('回放包生成时点'));
      const saved = await (await fetch(`http://127.0.0.1:8000/api/v1/jobs/${job.id}/report`)).json();
      assert((await page.getByLabel('报告生成来源').innerText()).includes(saved.tools.analysis_generated_at));
    }
    const rejected = await fetch(`http://127.0.0.1:8765/api/v1/jobs/${c02.id}/reviews`, { method: 'POST' });
    assert.equal(rejected.status, 405);
    await page.goto('http://127.0.0.1:8765/comparison.html');
    assert.equal(await page.locator('tbody tr').count(), 18);
    checks.push('offline six-source viewing, analysis/package timestamps, no writable controls, POST405, 18 comparison rows');
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'browser-proof.json'), JSON.stringify({ passed: true,
      browser: browser.version(), checks, page_errors: errors,
      ui_fixtures_are_not_evaluation_samples: true }, null, 2));
    console.log(JSON.stringify({ passed: true, checks, page_errors: errors }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
