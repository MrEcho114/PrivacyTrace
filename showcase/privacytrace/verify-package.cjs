const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { execFileSync } = require('node:child_process');
const { pathToFileURL } = require('node:url');
const { chromium } = require('playwright');
const { work } = require('./paths.cjs');
const digest = value => crypto.createHash('sha256').update(value).digest('hex');
async function main() {
  const delivery = path.join(__dirname, 'delivery');
  const manifest = JSON.parse(fs.readFileSync(path.join(delivery, 'manifest.json')));
  for (const file of manifest.artifacts) assert.equal(digest(fs.readFileSync(path.join(delivery, file.file))), file.sha256);
  const unpacked = fs.mkdtempSync(path.join(work, 'unpacked-'));
  execFileSync(process.env.FILM_PYTHON || 'python', ['-c',
    'import sys,zipfile;from pathlib import Path;z=zipfile.ZipFile(sys.argv[1]);r=Path(sys.argv[2]).resolve();assert all((r/n).resolve().is_relative_to(r) for n in z.namelist());z.extractall(r)',
    path.join(delivery, 'PrivacyTrace-Source.zip'), unpacked], { windowsHide: true });
  const files = JSON.parse(fs.readFileSync(path.join(unpacked, 'files.json')));
  const secrets = [...new Set([process.env.DEEPSEEK_API_KEY, process.env.PRIVACYTRACE_LLM_API_KEY].filter(Boolean))];
  let checked = 0;
  for (const file of files) {
    const target = path.resolve(unpacked, file.path); assert(target.startsWith(unpacked + path.sep));
    const bytes = fs.readFileSync(target); assert.equal(digest(bytes), file.sha256);
    assert(secrets.every(secret => !bytes.includes(Buffer.from(secret))), 'Credential found in source package');
    if (/\.(json|js|cjs|mjs|py|md|txt|html)$/.test(file.path)) assert(!/[CD]:[\\/]/.test(bytes.toString('utf8')), 'Private local path found in source package');
    checked++;
  }
  const source = require(path.join(unpacked, 'render.cjs')).sourceHash();
  assert.equal(source.sha256, manifest.visual_source_sha256);
  const browser = await chromium.launch({ headless: true, args: ['--autoplay-policy=no-user-gesture-required'] });
  const errors = [], external = [];
  try {
    const context = await browser.newContext({ offline: true, viewport: { width: 1440, height: 900 } });
    const page = await context.newPage();
    page.on('pageerror', e => errors.push(e.message)); page.on('request', r => { if (/^https?:/.test(r.url())) external.push(r.url()); });
    await page.goto(pathToFileURL(path.join(unpacked, 'index.html')).href); await page.waitForFunction(() => window.__ready, null, { timeout: 60000 });
    await page.getByRole('button', { name: '播放', exact: true }).click(); await page.waitForFunction(() => window.__inspect().time > .3, null, { timeout: 10000 });
    await page.getByRole('button', { name: '暂停', exact: true }).click();
    for (const t of [5, 48, 66, 74, 107, 158, 168, 176]) { await page.evaluate(t => window.__seek(t), t); assert.equal(await page.evaluate(() => window.__inspect().time), t); }
    assert.equal(errors.length, 0); assert.equal(external.length, 0);
    await page.screenshot({ path: path.join(work, 'qa/unpacked-preview.png') });
  } finally { await browser.close(); }
  const result = { passed: true, source_zip_sha256: manifest.artifacts.find(a => a.file.endsWith('.zip')).sha256, visual_source_sha256: source.sha256,
    file_hashes_checked: checked, actual_offline_relocated_preview: true, credential_values_checked: secrets.length, credential_matches: 0, private_local_path_matches: 0, errors, external_requests: external };
  fs.writeFileSync(path.join(work, 'qa/package.json'), JSON.stringify(result, null, 2)); console.log(JSON.stringify(result));
}
main().catch(e => { console.error(e.stack); process.exitCode = 1; });
