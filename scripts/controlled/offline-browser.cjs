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
    for (const value of options) {
      await page.locator('#report-source').selectOption(value);
      await page.getByRole('table').waitFor();
      assert((await page.locator('[aria-label="报告生成来源"]').innerText()).includes('回放包生成时点'));
    }
    assert.deepEqual(errors, []);
    fs.writeFileSync('/output/offline-dom.html', await page.content());
    console.log(JSON.stringify({ browser: browser.version(), six_sources: true, page_errors: errors }));
  } finally { await browser.close(); }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
