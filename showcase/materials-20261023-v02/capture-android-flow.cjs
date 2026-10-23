/* Batch 20261023-v02: capture the Android app frontend (production MobileApp.vue
 * with a harness native bridge) at 390x844, as stills and a real operation video.
 * This is a Chromium viewport simulation, not a device capture. */
const { chromium } = require('playwright');
const fs = require('fs');
const path = require('path');
const { execFileSync } = require('child_process');

const ROOT = path.resolve(__dirname, '..', '..');
const BASE = process.env.PRIVACYTRACE_FRONTEND_URL || 'http://127.0.0.1:6173/';
const API = process.env.PRIVACYTRACE_API_ORIGIN || 'http://127.0.0.1:8123';
const OUT = process.env.MATERIALS_OUT || path.join(ROOT, 'tmp/materials-v02/capture/out');
fs.mkdirSync(OUT, { recursive: true });

function bridge(options) {
  globalThis.isTauri = true;
  const context = { origin: 'https://analysis.example/', draft: 'm'.repeat(32), state: 'SERVER_CONFIRMED', cleanupPending: false };
  const job = { ...options.report.job, id: 'm'.repeat(32), state: 'QUEUED', error: null };
  const draft = {
    id: context.draft, name: options.report.sample.name, uploaded: true, revision: 1, apk_sha256: options.report.sample.apk_sha256,
    sources: (options.report.policy_documents || []).map((doc, index) => ({ id: 'source-' + index, title: doc.title, url: 'https://example.com/policy', source_type: doc.source_type, text: doc.artifact?.text || '', status: 'ready', version: doc.version || 'UNKNOWN', provenance: 'EXTERNAL_CHAT_EXPORT' })),
    candidates: [{ id: 'candidate-1', source_id: 'source-0', excerpt: (options.report.policy_documents?.[0]?.artifact?.text || '').slice(0, 24), data_type: (options.taxonomy.data_types[0] || {}).id || 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }],
    jobs: [],
  };
  let configured = false, jobReads = 0; const events = [];
  function advanceJob() { jobReads += 1; job.state = jobReads === 1 ? 'STATIC_ANALYSIS' : 'SUCCEEDED'; events.push({ state: job.state, at: new Date().toISOString() }); if (draft.jobs[0]) draft.jobs[0].events = [...events]; return job; }
  globalThis.__TAURI_INTERNALS__ = { invoke: async (command, args = {}) => {
    const method = command.split('|')[1];
    if (method === 'model_status') return { configured, endpoint: null };
    if (method === 'configure_model') { configured = true; return { configured, endpoint: null }; }
    if (method === 'upload_selected' || method === 'refresh_upload') return context;
    if (method === 'delete_upload') return { ...context, state: 'DELETED' };
    if (method === 'cancel') return;
    if (method === 'collect_policy') return { text: '' };
    if (method !== 'workflow') throw new Error('Unexpected native method ' + method);
    const action = args.action, input = JSON.parse(args.payload);
    let data = draft;
    if (action === 'taxonomy') data = options.taxonomy;
    else if (['read', 'discover', 'fetch'].includes(action)) data = draft;
    else if (action === 'extract') { draft.candidates = [{ id: 'candidate-1', source_id: draft.sources[0]?.id || 'source-0', excerpt: (draft.sources[0]?.text || '').slice(0, 24), data_type: (options.taxonomy.data_types[0] || {}).id || 'LOCATION', polarity: 'AFFIRMATIVE', subject: 'HOST_APP', checked: false, action: 'ACCESS' }]; draft.revision++; }
    else if (action === 'candidates') { draft.candidates = input.candidates; draft.revision++; }
    else if (action === 'start') { draft.jobs.push({ job_id: job.id, request_id: input.request_id, revision: draft.revision, events: [{ state: 'QUEUED', at: new Date().toISOString() }] }); draft.revision++; }
    else if (action === 'job') data = { ...advanceJob() };
    else if (action === 'report') data = { ...options.report, job: { ...job }, demo: false, delivery_mode: 'PERSISTED_REPLAY', result: { ...options.report.result, job_id: job.id } };
    else throw new Error('Unexpected workflow action ' + action);
    return { json: JSON.stringify({ origin: context.origin, draft: context.draft, data }) };
  } };
}

async function waitTitle(page, title, timeout = 20000) {
  await page.waitForFunction(expected => document.getElementById('page-title')?.textContent?.trim() === expected, title, { timeout });
}

(async () => {
  const report = await (await fetch(`${API}/api/v1/jobs/gkd-s1-first/report`)).json();
  const taxonomy = await (await fetch(`${API}/api/v1/taxonomy`)).json();
  const videoDir = path.join(OUT, 'android-video');
  fs.rmSync(videoDir, { recursive: true, force: true });
  fs.mkdirSync(videoDir, { recursive: true });

  const browser = await chromium.launch({ channel: 'msedge', headless: true });
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 2,
    isMobile: true,
    hasTouch: true,
    recordVideo: { dir: videoDir, size: { width: 390, height: 844 } },
  });
  const page = await context.newPage();
  await page.addInitScript(bridge, { report, taxonomy });
  const errors = [];
  page.on('pageerror', e => errors.push(e.message));
  await page.goto(BASE, { waitUntil: 'domcontentloaded' });
  await waitTitle(page, 'APK 与政策材料');
  await page.waitForTimeout(1000);
  await page.screenshot({ path: path.join(OUT, 'android-import.png') });

  await page.getByRole('button', { name: '恢复当前材料', exact: true }).click();
  await page.getByRole('heading', { name: '政策来源', exact: true }).waitFor({ timeout: 20000 });
  await page.waitForTimeout(2200);
  await page.screenshot({ path: path.join(OUT, 'android-import.png') });

  await page.getByRole('button', { name: '准备政策', exact: true }).click();
  await waitTitle(page, '核对政策声明');
  const firstSource = page.locator('.source-tabs button').first();
  if (await firstSource.count()) {
    await firstSource.click();
    await page.waitForTimeout(900);
  }
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, 'android-candidates.png') });

  await page.getByRole('button', { name: '保存并分析', exact: true }).click();
  await waitTitle(page, '扫描与对照进度');
  await page.waitForTimeout(2000);
  await page.screenshot({ path: path.join(OUT, 'android-progress.png') });

  await page.getByRole('button', { name: '查看报告', exact: true }).waitFor({ timeout: 30000 });
  await page.getByRole('button', { name: '查看报告', exact: true }).click();
  await waitTitle(page, 'APP 隐私收集越权报告');
  await page.evaluate(() => document.fonts.ready);
  await page.waitForTimeout(2400);
  await page.screenshot({ path: path.join(OUT, 'android-report.png') });
  await page.screenshot({ path: path.join(OUT, 'android-report-full.png'), fullPage: true });

  const evidence = page.locator('.m-issue-list .evidence-button').first();
  if (await evidence.count()) {
    await evidence.click();
    await page.locator('.report-evidence-inline #evidence-panel').waitFor({ timeout: 8000 }).catch(() => {});
    await page.waitForTimeout(2200);
  }
  await page.screenshot({ path: path.join(OUT, 'android-evidence.png') });
  await page.screenshot({ path: path.join(OUT, 'android-evidence-full.png'), fullPage: true });

  await page.waitForTimeout(600);
  const video = page.video();
  await context.close();
  const webm = await video.path();
  const mp4 = path.join(OUT, 'android-flow.mp4');
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', webm, '-r', '30', '-pix_fmt', 'yuv420p', mp4]);
  const frames = path.join(OUT, 'android-rec');
  fs.rmSync(frames, { recursive: true, force: true });
  fs.mkdirSync(frames, { recursive: true });
  execFileSync('ffmpeg', ['-hide_banner', '-loglevel', 'error', '-y', '-i', mp4, '-vf', 'fps=10', '-q:v', '3', path.join(frames, 'f_%04d.jpg')]);
  console.log(JSON.stringify({
    stills: ['android-import.png', 'android-candidates.png', 'android-progress.png', 'android-report.png', 'android-report-full.png', 'android-evidence.png', 'android-evidence-full.png'],
    video: mp4,
    videoBytes: fs.statSync(mp4).size,
    frames: fs.readdirSync(frames).length,
    errors,
  }));
  await browser.close();
})().catch(e => { console.error('FATAL', e); process.exit(1); });
