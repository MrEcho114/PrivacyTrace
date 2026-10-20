// Browser driver lives in the validation image; the deliverable viewer needs Python stdlib only.
const { chromium } = require('/verify_modules/playwright');
const fs = require('node:fs');
const assert = require('node:assert/strict');
async function main() {
  const browser = await chromium.launch({ executablePath: '/browser/chrome-linux64/chrome',
    headless: true, args: ['--no-sandbox', '--disable-dev-shm-usage'] });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto('http://127.0.0.1:8765');
    await page.getByText('OFFLINE REPLAY · 离线回放', { exact: true }).waitFor();
    await page.getByText('CONTROLLED_APK · 自建受控场景', { exact: true }).waitFor();
    await page.getByText(/回放包生成时点/).waitFor();
    assert.equal(await page.locator('.review-panel').count(), 0);
    const options = await page.locator('#report-source option').evaluateAll(items => items.map(item => item.value));
    assert.equal(options.length, 6);
    let codeEvidenceExpanded = false;
    let policyQuoteExpanded = false;
    let fullPolicyExpanded = false;
    for (const value of options) {
      await page.locator('#report-source').selectOption(value);
      await page.getByRole('table').waitFor();
      assert((await page.locator('[aria-label="报告生成来源"]').innerText()).includes('回放包生成时点'));
      const id = value.slice(4);
      const saved = await (await page.request.get(`http://127.0.0.1:8765/api/v1/jobs/${id}/report`)).json();
      assert((await page.locator('[aria-label="报告生成来源"]').innerText()).includes(saved.tools.analysis_generated_at));
      if (saved.job.sample_id === 'C02') {
        const issue = saved.result.issues.find(item => item.status === 'EXACT_MATCH');
        assert(issue);
        const api = saved.evidence.find(item => item.kind === 'API' && issue.evidence_ids.includes(item.id));
        const quote = saved.evidence.find(item => item.kind === 'POLICY_SENTENCE' && issue.evidence_ids.includes(item.id));
        assert(api && quote);
        const document = saved.policy_documents.find(item => item.id === quote.document_id);
        assert(document);
        assert.equal(Array.from(document.artifact.text).slice(quote.start_offset, quote.end_offset).join(''), quote.excerpt);
        await page.getByRole('row').filter({ hasText: '具体类型已声明' }).getByRole('button').click();
        const cards = page.locator('#evidence-panel .evidence-grid').first().locator('article');
        const apiCard = cards.filter({ hasText: api.id });
        await apiCard.waitFor();
        const codeText = await apiCard.innerText();
        assert(codeText.includes(api.locator) && codeText.includes(api.api_call.target_descriptor));
        assert(codeText.includes(api.excerpt));
        codeEvidenceExpanded = true;
        const quoteCard = cards.filter({ hasText: quote.id });
        await quoteCard.locator('mark').waitFor();
        assert.equal(await quoteCard.locator('mark').textContent(), quote.excerpt);
        policyQuoteExpanded = true;
        await quoteCard.getByRole('button', { name: '完整政策与适用边界', exact: true }).click();
        const fullPolicy = page.locator('.provenance pre');
        await fullPolicy.waitFor();
        assert.equal(await fullPolicy.textContent(), document.artifact.text);
        fullPolicyExpanded = true;
        await page.screenshot({ path: '/output/offline-evidence-c02.png', fullPage: true });
      }
    }
    assert(codeEvidenceExpanded && policyQuoteExpanded && fullPolicyExpanded);
    assert.deepEqual(errors, []);
    fs.writeFileSync('/output/offline-dom.html', await page.content());
    console.log(JSON.stringify({ browser: browser.version(), six_sources: true, page_errors: errors,
      evidence_drilldown_scenario: 'C02', code_evidence_expanded: codeEvidenceExpanded,
      policy_quote_expanded: policyQuoteExpanded, full_policy_expanded: fullPolicyExpanded }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
