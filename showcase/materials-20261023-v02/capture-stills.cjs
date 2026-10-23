/* Batch 20261023-v02: capture the three interface stills from the frozen main worktree.
 * Requires a dev server on PRIVACYTRACE_FRONTEND_URL and an API with fixture store
 * (see README.md in this directory). Chromium/Edge comes from Playwright. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');

const ROOT = path.resolve(__dirname, '..', '..');
const BASE = process.env.PRIVACYTRACE_FRONTEND_URL || 'http://127.0.0.1:6173/';
const OUT = process.env.MATERIALS_OUT || path.join(ROOT, 'tmp/materials-v02/capture/out');
fs.mkdirSync(OUT, { recursive: true });

async function fonts(page) { await page.evaluate(() => document.fonts.ready); }

async function openArchive(page) {
  await page.goto(BASE, { waitUntil: 'networkidle' }).catch(() => {});
  const nav = page.getByRole('button', { name: '已有报告', exact: true });
  const link = page.getByRole('link', { name: '已有报告', exact: true });
  if (await nav.count()) await nav.first().click();
  else if (await link.count()) await link.first().click();
  else await page.goto(BASE + '#reports');
  await page.locator('#report-source option[value="job:gkd-s1-first"]').waitFor({ state: 'attached', timeout: 20000 });
  await page.locator('#report-source').selectOption('job:gkd-s1-first');
  await page.locator('.report-table tbody tr').first().waitFor({ timeout: 20000 });
  await fonts(page);
  await page.waitForTimeout(500);
}

(async () => {
  const browser = await chromium.launch({ channel: 'msedge', headless: true });

  // 1. Import page at 1920x1080 after the fixed demo materials are loaded.
  const desk = await browser.newContext({ viewport: { width: 1920, height: 1080 }, deviceScaleFactor: 1 });
  const p1 = await desk.newPage();
  await p1.goto(BASE, { waitUntil: 'networkidle' }).catch(() => {});
  await p1.getByRole('button', { name: '体验示例', exact: true }).click();
  await p1.locator('text=纸舟地图隐私政策').first().waitFor({ timeout: 15000 });
  await fonts(p1);
  await p1.waitForTimeout(600);
  await p1.screenshot({ path: path.join(OUT, 'ui-import.png') });
  console.log('ui-import', fs.statSync(path.join(OUT, 'ui-import.png')).size);

  // 2. Persisted real-scan report (gkd-s1-first fixture) at 1440 full page.
  const wide = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const p2 = await wide.newPage();
  await openArchive(p2);
  const wideMeta = await p2.evaluate(() => ({ scrollW: document.documentElement.scrollWidth, scrollH: document.documentElement.scrollHeight }));
  await p2.screenshot({ path: path.join(OUT, 'report-desktop.png'), fullPage: true });
  console.log('report-desktop', fs.statSync(path.join(OUT, 'report-desktop.png')).size, wideMeta);

  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
