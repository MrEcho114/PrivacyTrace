// Actual persisted HTTP and Chromium evidence checks for every PT-907 target.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE_PATH || 'playwright');
const sha = bytes => crypto.createHash('sha256').update(bytes).digest('hex');

async function main() {
  const comparisonBytes = fs.readFileSync(process.argv[2]);
  const comparison = JSON.parse(comparisonBytes);
  const output = process.argv[3];
  fs.mkdirSync(output, { recursive: true });
  const expected = Object.keys(comparison.protocol.scenarios).sort();
  assert.equal(expected.length, 12);
  const response = await fetch('http://127.0.0.1:8000/api/v1/jobs');
  assert.equal(response.status, 200);
  const jobs = (await response.json()).jobs;
  assert.deepEqual(jobs.map(job => job.sample_id).sort(), expected);
  const browser = await chromium.launch({ headless: true,
    args: ['--no-sandbox', '--disable-dev-shm-usage'],
    ...(process.env.PRIVACYTRACE_CHROMIUM ? { executablePath: process.env.PRIVACYTRACE_CHROMIUM } : {}) });
  const errors = [], checks = [];
  try {
    const page = await browser.newPage({ viewport: { width: 1280, height: 1000 } });
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:5173/#reports');
    for (const scenario of expected) {
      const job = jobs.find(item => item.sample_id === scenario);
      const reportResponse = await fetch(`http://127.0.0.1:8000/api/v1/jobs/${job.id}/report`);
      assert.equal(reportResponse.status, 200);
      const bytes = Buffer.from(await reportResponse.arrayBuffer());
      const report = JSON.parse(bytes);
      assert.equal(report.job.input_mode, 'CONTROLLED_APK');
      assert.equal(report.job.source_origin, 'CONTROLLED');
      assert.equal(report.delivery_mode, 'PERSISTED_REPLAY');
      const target = comparison.protocol.scenarios[scenario];
      const behavior = report.behaviors.find(item => item.data_type === target.data_type && item.action === target.action);
      assert(behavior);
      const issues = report.result.issues.filter(item => item.behavior_id === behavior.id);
      assert.deepEqual([...new Set(issues.map(item => item.status))], [target.expected]);
      await page.locator('#report-source').selectOption(`job:${job.id}`);
      await page.getByRole('heading', { name: scenario, exact: true }).waitFor();
      await page.getByText('CONTROLLED_APK · 自建受控场景', { exact: true }).waitFor();
      // The report table preserves the persisted issue order, including extra capabilities.
      const row = page.locator('tbody tr').nth(report.result.issues.indexOf(issues[0]));
      const labels = { EXACT_MATCH: '具体类型已声明', CATEGORY_MATCH: '声明粒度不足',
        NOT_DECLARED: '未找到对应声明', AMBIGUOUS_DISCLOSURE: '相关声明不够清楚',
        INSUFFICIENT_EVIDENCE: '证据不足' };
      assert((await row.innerText()).includes(labels[target.expected]));
      await row.getByRole('button').click();
      const panel = page.locator('#evidence-panel');
      await panel.waitFor();
      const panelText = await panel.innerText();
      const refs = new Set(issues.flatMap(item => item.evidence_ids));
      const evidence = report.evidence.filter(item => refs.has(item.id));
      for (const item of evidence.filter(item => item.api_call)) {
        assert(panelText.includes(item.locator), `${scenario}: missing code locator`);
        assert(panelText.includes(item.api_call.target_descriptor));
      }
      for (const item of evidence.filter(item => item.kind === 'POLICY_SENTENCE')) {
        const doc = report.policy_documents.find(doc => doc.id === item.document_id);
        assert.equal(Array.from(doc.artifact.text).slice(item.start_offset, item.end_offset).join(''), item.excerpt);
        assert(panelText.includes(item.excerpt), `${scenario}: missing policy span`);
      }
      assert.equal(report.coverage.status, 'COMPLETE');
      const screenshot = `${scenario}.png`;
      await page.screenshot({ path: path.join(output, screenshot), fullPage: true });
      checks.push({ scenario_id: scenario, state: report.job.state, status: target.expected,
        http_report_sha256: sha(bytes), api_evidence_count: evidence.filter(e => e.api_call).length,
        policy_span_count: evidence.filter(e => e.kind === 'POLICY_SENTENCE').length,
        source_checked: true, code_locators_checked: true, policy_spans_checked: true,
        screenshot, screenshot_sha256: sha(fs.readFileSync(path.join(output, screenshot))) });
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync(path.join(output, 'browser-proof.json'), JSON.stringify({ passed: true,
      browser: browser.version(), comparison_sha256: sha(comparisonBytes), scenario_count: checks.length,
      checks, page_errors: errors }, null, 2));
    process.stdout.write(JSON.stringify({ passed: true, scenario_count: checks.length, page_errors: errors }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
