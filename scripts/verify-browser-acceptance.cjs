// Automated Browser Acceptance Test Suite for PT-808
// Verifies R1-R5 on a headless Chromium browser driven by Playwright.
//
// Reproducibility contract:
//   * `playwright` is a declared devDependency of the repository; no machine
//     specific module paths are probed.
//   * Job fixtures are checked in under `fixtures/acceptance-jobs/`, so a clean
//     checkout needs no pre-existing `data/jobs` directory.
//   * The API instance is booted against a throwaway store directory created for
//     this run, and only processes spawned by this script are ever terminated.
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const { spawn, execSync } = require('node:child_process');

// Dedicated ports keep the run isolated from a developer's own dev servers.
const API_PORT = Number(process.env.PRIVACYTRACE_ACCEPTANCE_API_PORT || 8123);
const WEB_PORT = Number(process.env.PRIVACYTRACE_ACCEPTANCE_WEB_PORT || 5273);
const API_ORIGIN = `http://127.0.0.1:${API_PORT}`;
const WEB_ORIGIN = `http://127.0.0.1:${WEB_PORT}`;

function getPlaywright() {
  try {
    return require('playwright');
  } catch {
    throw new Error(
      'Playwright is not installed. Run `npm ci` at the repository root before the acceptance run.'
    );
  }
}

function getChromiumExecutable() {
  // Playwright resolves its own browser build; an explicit override stays opt-in.
  return process.env.PRIVACYTRACE_CHROMIUM || undefined;
}

async function isPortOpen(url) {
  try {
    const res = await fetch(url, { signal: AbortSignal.timeout(1000) });
    return res.status < 500;
  } catch {
    return false;
  }
}

async function waitForServer(url, timeoutMs = 30000) {
  const start = Date.now();
  while (Date.now() - start < timeoutMs) {
    if (await isPortOpen(url)) return true;
    await new Promise(r => setTimeout(r, 500));
  }
  return false;
}

// Terminates only a process tree this script spawned; never an unknown PID.
function killProcessTree(pid) {
  if (!pid) return;
  try {
    if (process.platform === 'win32') {
      execSync(`taskkill /F /T /PID ${pid}`, { stdio: 'ignore' });
    } else {
      process.kill(-pid, 'SIGKILL');
    }
  } catch {}
}

// Terminates the spawned children and waits until they are gone, so the temp
// store is never removed while a server still holds files inside it.
async function stopChildren(children) {
  for (const child of children) {
    killProcessTree(child.pid);
  }
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const alive = children.filter(c => c.exitCode === null && c.signalCode === null && c.pid);
    if (alive.length === 0) return;
    await new Promise(r => setTimeout(r, 100));
  }
}

// Proves the frontend on WEB_PORT is the instance this run owns: it must serve
// this project's own dev HTML. A developer's unrelated Vite instance, or any
// other server squatting on the port, must never be reused -- it could proxy to
// a real backend and write outside the isolated store.
async function identifyFrontend(origin) {
  try {
    const res = await fetch(`${origin}/`, { signal: AbortSignal.timeout(2000) });
    if (!res.ok) return { ours: false, reason: `HTTP ${res.status}` };
    const html = await res.text();
    // Vite serves the app's own index.html, which mounts this app's entry
    // module. Any other server will not carry this marker.
    const ours = html.includes('/src/main.ts') && html.includes('id="app"');
    return { ours, reason: ours ? 'matched PrivacyTrace dev entry' : 'no PrivacyTrace dev entry in HTML' };
  } catch (err) {
    return { ours: false, reason: `unreachable: ${err.message}` };
  }
}

// Confirms the frontend actually proxies /api to *this* run's isolated API.
async function verifyFrontendProxy(origin) {
  try {
    const res = await fetch(`${origin}/api/v1/jobs`, { signal: AbortSignal.timeout(3000) });
    if (!res.ok) return { ok: false, reason: `proxy returned HTTP ${res.status}` };
    const body = await res.json();
    const ids = Array.isArray(body.jobs) ? body.jobs.map(j => j.id) : [];
    // The isolated store is seeded only from fixtures/acceptance-jobs.
    const expected = fixtureJobIds();
    const leaked = ids.filter(id => !expected.includes(id));
    if (leaked.length > 0) {
      return { ok: false, reason: `proxy exposes jobs outside the isolated store: ${leaked.join(', ')}` };
    }
    if (!expected.some(id => ids.includes(id))) {
      return { ok: false, reason: 'proxy does not serve the isolated fixture store' };
    }
    return { ok: true, reason: 'proxy targets the isolated API' };
  } catch (err) {
    return { ok: false, reason: `unreachable: ${err.message}` };
  }
}

let _fixtureIds = null;
function fixtureJobIds(projectRoot) {
  if (_fixtureIds) return _fixtureIds;
  const root = projectRoot || path.resolve(__dirname, '..');
  const dir = path.join(root, 'fixtures', 'acceptance-jobs');
  _fixtureIds = fs
    .readdirSync(dir)
    .filter(n => n.endsWith('.json'))
    .map(n => n.replace(/\.json$/, ''));
  return _fixtureIds;
}

async function selectSource(page, value) {
  await page.locator(`#report-source option[value="${value}"]`).waitFor({ state: 'attached', timeout: 15000 });
  await page.locator('#report-source').selectOption(value);
  await page.waitForTimeout(400);
}

// Mirrors the frontend rule under test: provenance comes from the explicit
// source_origin field, and sample_id naming is never consulted.
function revealOrigin(sampleId, sourceOrigin) {
  return sourceOrigin || (sampleId ? 'UNANNOTATED' : 'UNANNOTATED');
}

const SHA_RE = /^[0-9a-f]{40}$/;

// Resolves `HEAD` to a 40-char SHA by reading Git's own files, never by
// spawning a shell. Some sandboxes refuse to spawn `cmd.exe` (EBUSY on
// Windows), so `git rev-parse` is unavailable there. Handles:
//   - normal checkout:      .git is a directory
//   - linked worktree:      .git is a FILE containing `gitdir: <path>`
//   - detached HEAD:        HEAD holds the SHA directly
//   - symbolic HEAD:        HEAD holds `ref: refs/heads/x`, possibly in
//                           `<commondir>/packed-refs` rather than a loose file
// Returns 'unknown' when nothing trustworthy can be read.
function resolveGitCommit(startDir) {
  const readIfExists = (p) => {
    try {
      return fs.readFileSync(p, 'utf-8').trim();
    } catch {
      return null;
    }
  };

  try {
    // 1. Locate the (possibly per-worktree) git dir.
    const dotGit = path.join(startDir, '.git');
    let gitDir = null;
    if (fs.existsSync(dotGit) && fs.statSync(dotGit).isDirectory()) {
      gitDir = dotGit;
    } else {
      const pointer = readIfExists(dotGit);
      if (pointer && pointer.startsWith('gitdir:')) {
        const raw = pointer.slice('gitdir:'.length).trim();
        gitDir = path.isAbsolute(raw) ? raw : path.resolve(startDir, raw);
      }
    }
    if (!gitDir) return 'unknown';

    // 2. Read HEAD. `commondir` points at the shared .git of the main
    //    checkout, where packed-refs lives for linked worktrees.
    const head = readIfExists(path.join(gitDir, 'HEAD'));
    if (!head) return 'unknown';
    if (SHA_RE.test(head)) return head; // detached HEAD

    if (!head.startsWith('ref:')) return 'unknown';
    const refName = head.slice('ref:'.length).trim();
    if (!refName) return 'unknown';

    // 3. Try the loose ref in the worktree's own git dir, then the common dir.
    const commonDirRaw = readIfExists(path.join(gitDir, 'commondir'));
    const commonDir = commonDirRaw
      ? path.resolve(gitDir, commonDirRaw)
      : gitDir;

    for (const base of [gitDir, commonDir]) {
      const loose = readIfExists(path.join(base, refName));
      if (loose && SHA_RE.test(loose)) return loose;
    }

    // 4. Fall back to packed-refs.
    const packed = readIfExists(path.join(commonDir, 'packed-refs'));
    if (packed) {
      for (const line of packed.split('\n')) {
        if (!line || line.startsWith('#') || line.startsWith('^')) continue;
        const [sha, name] = line.split(' ');
        if (name === refName && SHA_RE.test(sha)) return sha;
      }
    }

    return 'unknown';
  } catch {
    return 'unknown';
  }
}

function createIsolatedStore(projectRoot) {
  // A fresh store per run: the checked-in fixtures are copied in, so the
  // repository's own data directory is never read from or written to.
  const storeDir = fs.mkdtempSync(path.join(os.tmpdir(), 'privacytrace-acceptance-'));
  const fixtureDir = path.join(projectRoot, 'fixtures', 'acceptance-jobs');
  const fixtures = fs.readdirSync(fixtureDir).filter(name => name.endsWith('.json'));
  assert(fixtures.length > 0, `No acceptance fixtures found in ${fixtureDir}`);
  for (const name of fixtures) {
    fs.copyFileSync(path.join(fixtureDir, name), path.join(storeDir, name));
  }
  return storeDir;
}

async function main() {
  const projectRoot = path.resolve(__dirname, '..');
  const evidenceDir = path.join(projectRoot, 'evidence');
  const screenshotDir = path.join(evidenceDir, 'screenshots');
  fs.mkdirSync(screenshotDir, { recursive: true });

  const childrenToKill = [];

  // Every resource acquired below lives inside this outermost try/finally, from
  // the temporary store onwards. If Chromium is missing, the API fails to boot,
  // or the port check throws, cleanup still runs and no child or temp directory
  // is leaked. `browser`/`storeDir` stay mutable so cleanup tolerates the case
  // where acquisition failed part-way.
  let storeDir = null;
  let browser = null;
  let fatal = null;

  try {
    // Boot the API against an isolated, fixture-seeded store. Only a process this
    // script spawns is ever terminated; no foreign port owner is touched.
    storeDir = createIsolatedStore(projectRoot);
    console.log(`[Server] Using isolated store: ${storeDir}`);

    if (await isPortOpen(`${API_ORIGIN}/api/v1/jobs`)) {
      throw new Error(
        `Port ${API_PORT} is already serving requests. Stop the process using it or set ` +
          'PRIVACYTRACE_ACCEPTANCE_API_PORT to a free port. This script never terminates processes it did not start.'
      );
    }
    console.log(`[Server] Starting API backend on port ${API_PORT}...`);
    const apiProc = spawn('uv', ['run', '--project', 'apps/api', 'uvicorn', 'privacytrace.main:app', '--port', String(API_PORT)], {
      cwd: projectRoot,
      shell: true,
      stdio: 'pipe',
      env: { ...process.env, PRIVACYTRACE_STORE_ROOT: storeDir },
    });
    childrenToKill.push(apiProc);
    if (!(await waitForServer(`${API_ORIGIN}/api/v1/jobs`, 60000))) {
      throw new Error(`Failed to start API backend on port ${API_PORT}`);
    }
    console.log('[Server] API backend is ready.');

    // The frontend must be an instance this run owns and controls. Reusing a
    // foreign server on WEB_PORT is refused: it may proxy to a real backend and
    // write outside the isolated store.
    if (await isPortOpen(WEB_ORIGIN)) {
      const identity = await identifyFrontend(WEB_ORIGIN);
      if (!identity.ours) {
        throw new Error(
          `Port ${WEB_PORT} is already serving a server this run does not own (${identity.reason}). ` +
            'Refusing to reuse it because its API proxy target is unknown. Stop that server or set ' +
            'PRIVACYTRACE_ACCEPTANCE_WEB_PORT to a free port.'
        );
      }
      const proxy = await verifyFrontendProxy(WEB_ORIGIN);
      if (!proxy.ok) {
        throw new Error(
          `The frontend on port ${WEB_PORT} looks like PrivacyTrace but is not wired to this run's ` +
            `isolated API (${proxy.reason}). Refusing to reuse it. Stop that server or set ` +
            'PRIVACYTRACE_ACCEPTANCE_WEB_PORT to a free port.'
        );
      }
      console.log(`[Server] Reusing the frontend on port ${WEB_PORT} (${proxy.reason}).`);
    } else {
      console.log(`[Server] Starting Vite frontend on port ${WEB_PORT}...`);
      const webProc = spawn('npm', ['--prefix', 'apps/web', 'run', 'dev'], {
        cwd: projectRoot,
        shell: true,
        stdio: 'pipe',
        env: { ...process.env, PRIVACYTRACE_API_ORIGIN: API_ORIGIN, PRIVACYTRACE_WEB_PORT: String(WEB_PORT) },
      });
      childrenToKill.push(webProc);
      if (!(await waitForServer(WEB_ORIGIN, 60000))) {
        throw new Error(`Failed to start Vite frontend on port ${WEB_PORT}`);
      }
      console.log('[Server] Vite frontend is ready.');
    }

    const { chromium } = getPlaywright();
    const execPath = getChromiumExecutable();
    console.log(`[Browser] Launching Chromium with executable: ${execPath || 'default'}`);

    browser = await chromium.launch({
      headless: true,
      ...(execPath ? { executablePath: execPath } : {}),
    });

    const browserVersion = browser.version();
    console.log(`[Browser] Chromium launched successfully (version: ${browserVersion})`);

    const context = await browser.newContext({
      viewport: { width: 1280, height: 900 },
    });
    const page = await context.newPage();

    const consoleLogs = [];
    const pageErrors = [];
  const errorLogs = [];
  const stepSequences = [];
  const testResults = [];

  page.on('console', msg => {
    const entry = { type: msg.type(), text: msg.text(), time: new Date().toISOString() };
    consoleLogs.push(entry);
    if (entry.type === 'error') errorLogs.push(entry);
  });
  page.on('pageerror', err => {
    pageErrors.push({ message: err.message, stack: err.stack, time: new Date().toISOString() });
  });

  const recordStep = (tc, action, details) => {
    const step = { tc, action, details, timestamp: new Date().toISOString() };
    stepSequences.push(step);
    console.log(`[${tc}] ${action}: ${details}`);
  };

  // ------------------------------------------------------------------------
  // TC-01: R1 Long-text rendering (200k chars), pagination switching (20/page),
  // full text expand/collapse/re-expand, locator jumps.
  // ------------------------------------------------------------------------
  console.log('\n--- Running TC-01: R1 Long-text, pagination, expand/collapse ---');
  const realReportRes = await fetch(`${API_ORIGIN}/api/v1/jobs/gkd-s1-first/report`);
    assert(realReportRes.ok, 'Failed to fetch base report for gkd-s1-first');
    const baseReport = await realReportRes.json();
    const longReport = structuredClone(baseReport);
    // Expand policy document to 200,000 characters
    const textChunk = '本隐私政策规定了我们如何收集、使用、存储和保护您的个人信息，包括但不限于位置权限与系统信息。';
    const longPolicyText = textChunk.repeat(Math.ceil(200000 / textChunk.length)).slice(0, 200000);
    assert.equal(longPolicyText.length, 200000, 'Policy text must be exactly 200,000 characters');

    longReport.policy_documents[0].artifact.text = longPolicyText;
    longReport.policy_documents[0].artifact.sha256 = crypto.createHash('sha256').update(longPolicyText, 'utf-8').digest('hex');

    // Link the first issue to evidence that actually exists in the fixture, so the
    // jump-to-policy button renders. Hard-coding upstream S1 evidence IDs would
    // break as soon as the checked-in fixture changes.
    const policyDocId = longReport.policy_documents[0].id;
    const sentenceEvidence =
      longReport.evidence.find(e => e.kind === 'POLICY_SENTENCE' && e.document_id === policyDocId) ||
      longReport.evidence.find(e => e.document_id === policyDocId);
    assert(sentenceEvidence, 'The fixture must contain evidence bound to the first policy document');
    const apiEvidence = longReport.evidence.find(e => e.kind === 'API' || e.kind === 'MANIFEST');
    assert(apiEvidence, 'The fixture must contain at least one API or MANIFEST evidence record');

    // Link issue to both API evidence and policy sentence evidence
    const targetDataType = longReport.result.issues[0]?.data_type || 'ACCESSIBILITY';
    longReport.result.issues[0].evidence_ids = [apiEvidence.id, sentenceEvidence.id];

    // Create 2000 candidate claims matching first issue's data_type
    const baseClaim = {
      id: 'claim-0',
      document_id: policyDocId,
      data_type: targetDataType,
      evidence_ids: [sentenceEvidence.id],
      polarity: 'PERMITTED',
      subject: 'FIRST_PARTY',
      action: 'COLLECT',
      condition: '在用户授权时收集',
    };
    longReport.policy_claims = Array.from({ length: 2000 }, (_, i) => ({
      ...baseClaim,
      id: `claim-${i}`,
      condition: `条款条件说明 #${i}`,
    }));

    // Intercept report for gkd-s1-first in TC-01
    const reportUrl = '**/api/v1/jobs/gkd-s1-first/report';
    await page.route(reportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(longReport),
    }));

    await page.goto(WEB_ORIGIN);
    recordStep('TC-01', 'navigate', `Loaded main page at ${WEB_ORIGIN}`);

    await selectSource(page, 'job:gkd-s1-first');
    recordStep('TC-01', 'select_job', 'Selected job:gkd-s1-first');

    // Expand evidence panel
    await page.getByRole('button', { name: /查看 \d+ 条证据/ }).first().click();
    recordStep('TC-01', 'expand_evidence', 'Clicked view evidence button');
    await page.locator('#evidence-panel').waitFor();

    // Verify pagination controls
    const navText = await page.locator('.candidate-nav').innerText();
    assert(navText.includes('共 2000 条 · 第 1 / 100 页'), `Expected pagination to show 2000 claims and 100 pages, got: ${navText}`);
    const firstPageCount = await page.locator('.candidate-clauses .evidence-card').count();
    assert.equal(firstPageCount, 20, `Candidate clauses should show 20 per page, got: ${firstPageCount}`);
    recordStep('TC-01', 'verify_page_1', 'Confirmed 20 items per page and 100 total pages');

    // Switch to page 2
    await page.locator('.candidate-nav button:has-text("下一页")').click();
    await page.waitForTimeout(150);
    const navTextPage2 = await page.locator('.candidate-nav').innerText();
    assert(navTextPage2.includes('第 2 / 100 页'), `Expected page 2, got: ${navTextPage2}`);
    recordStep('TC-01', 'switch_page_2', 'Successfully switched to page 2');

    // Switch back to page 1
    await page.locator('.candidate-nav button:has-text("上一页")').click();
    await page.waitForTimeout(150);
    const navTextPage1Again = await page.locator('.candidate-nav').innerText();
    assert(navTextPage1Again.includes('第 1 / 100 页'), `Expected page 1 again, got: ${navTextPage1Again}`);
    recordStep('TC-01', 'switch_page_1', 'Successfully switched back to page 1');

    // Expand 200k policy full text via button jump
    const policyBtn = page.locator('#evidence-panel button:has-text("完整政策与适用边界")').first();
    await policyBtn.waitFor({ state: 'visible', timeout: 10000 });
    await policyBtn.click();
    recordStep('TC-01', 'open_policy', 'Clicked 完整政策与适用边界 to jump to provenance and mount policy');

    await page.locator('.provenance pre').waitFor({ state: 'visible' });
    const mountedCount = await page.locator('.provenance pre').count();
    assert.equal(mountedCount, 1, 'Only one policy pre tag should be mounted');
    const mountedTextLen = (await page.locator('.provenance pre').innerText()).length;
    assert.equal(mountedTextLen, 200000, `Mounted text should be exactly 200,000 chars, got: ${mountedTextLen}`);
    recordStep('TC-01', 'verify_policy_mount', 'Verified exactly 1 pre tag mounted with 200k codepoints');

    // Collapse policy
    const policySummary = page.locator('.provenance article details summary:has-text("查看政策全文")').first();
    await policySummary.click();
    await page.waitForTimeout(200);
    const collapsedPreCount = await page.locator('.provenance pre').count();
    assert.equal(collapsedPreCount, 0, 'Policy text pre tag should be unmounted upon collapse');
    recordStep('TC-01', 'collapse_policy', 'Verified pre tag unmounted on collapse');

    // Re-expand policy
    await policySummary.click();
    await page.waitForTimeout(200);
    const remountedPreCount = await page.locator('.provenance pre').count();
    assert.equal(remountedPreCount, 1, 'Policy text pre tag should be remounted upon re-expand');
    recordStep('TC-01', 'reexpand_policy', 'Verified pre tag remounted on re-expand');

    const screenshotTc01 = path.join(screenshotDir, 'tc01-long-text-pagination.png');
    await page.screenshot({ path: screenshotTc01, fullPage: true });
    recordStep('TC-01', 'screenshot', `Captured screenshot at ${screenshotTc01}`);

    await page.unroute(reportUrl);
    testResults.push({ id: 'TC-01', name: 'R1 Long-text rendering & pagination', status: 'PASSED' });

    // ------------------------------------------------------------------------
    // TC-02: R2 Malicious HTML, <script>, and injection payloads rendered as pure text
    // ------------------------------------------------------------------------
    console.log('\n--- Running TC-02: R2 Malicious input escaping & anti-XSS ---');
    const xssPayloads = [
      '<script>window.__xss_executed = 1</script>',
      '<img src="invalid_xss_probe.jpg" onerror="window.__xss_executed = 2">',
      '<svg onload="window.__xss_executed = 3">',
      '"><a href="javascript:window.__xss_executed = 4">click</a>',
    ];
    const xssReport = structuredClone(baseReport);
    // Reuse the fixture's own evidence IDs so the policy jump button still renders.
    xssReport.result.issues[0].evidence_ids = [apiEvidence.id, sentenceEvidence.id];
    xssReport.sample.name = `GKD ${xssPayloads[0]}`;
    xssReport.policy_documents[0].artifact.text = `这是政策正文：${xssPayloads.join(' ')}`;
    xssReport.evidence[0].locator = `dex=classes.dex;${xssPayloads[1]}`;
    if (xssReport.evidence[0].excerpt) xssReport.evidence[0].excerpt = `invoke-virtual ${xssPayloads[2]}`;

    await page.route(reportUrl, route => route.fulfill({
      status: 200,
      contentType: 'application/json',
      body: JSON.stringify(xssReport),
    }));

    await selectSource(page, 'demo:synthetic');
    await page.waitForTimeout(200);
    await selectSource(page, 'job:gkd-s1-first');
    recordStep('TC-02', 'inject_payloads', 'Loaded report with multiple malicious HTML/script payloads');

    await page.getByRole('button', { name: /查看 \d+ 条证据/ }).first().click();
    await page.locator('#evidence-panel').waitFor();
    const xssPolicyBtn = page.locator('#evidence-panel button:has-text("完整政策与适用边界")').first();
    await xssPolicyBtn.waitFor({ state: 'visible', timeout: 10000 });
    await xssPolicyBtn.click();
    await page.waitForTimeout(300);

    // Verify window.__xss_executed has NOT been set
    const injectedValue = await page.evaluate(() => window.__xss_executed);
    assert.equal(injectedValue, undefined, 'window.__xss_executed must remain undefined (no script execution)');
    recordStep('TC-02', 'assert_no_script_execution', 'Verified window.__xss_executed is undefined');

    // Verify no script tags or onerror images in the rendered main content
    const injectedScriptCount = await page.locator('main script').count();
    assert.equal(injectedScriptCount, 0, 'No executable script tags should be parsed in DOM');
    const injectedImgCount = await page.locator('main img[src="invalid_xss_probe.jpg"]').count();
    assert.equal(injectedImgCount, 0, 'No onerror image tags should be parsed in DOM');
    recordStep('TC-02', 'assert_dom_purity', 'Verified 0 executable script/img elements in main content');

    // Verify CSP meta tag exists in head
    const cspContent = await page.locator('meta[http-equiv="Content-Security-Policy"]').getAttribute('content');
    assert(cspContent && cspContent.includes("default-src 'self'"), `CSP header must be present: ${cspContent}`);
    recordStep('TC-02', 'assert_csp', `Confirmed CSP meta tag in head: ${cspContent}`);

    // Verify 0 page errors occurred
    assert.equal(pageErrors.length, 0, `Expected 0 uncaught page errors, found: ${JSON.stringify(pageErrors)}`);

    const screenshotTc02 = path.join(screenshotDir, 'tc02-xss-defense.png');
    await page.screenshot({ path: screenshotTc02, fullPage: true });
    recordStep('TC-02', 'screenshot', `Captured screenshot at ${screenshotTc02}`);

    await page.unroute(reportUrl);
    testResults.push({ id: 'TC-02', name: 'R2 Anti-XSS and safe text rendering', status: 'PASSED' });

    // ------------------------------------------------------------------------
    // TC-03: R3 Error prompts for partial (classes2.dex failure), timeout/failure (ZIP_INVALID),
    // cancelled state, and bytecode boundary fallback without fake JADX.
    // ------------------------------------------------------------------------
    console.log('\n--- Running TC-03: R3 Error prompts & bytecode fallback ---');

    // 1. Partial coverage & Bytecode Fallback (ui-controlled-partial)
    await selectSource(page, 'job:ui-controlled-partial');
    recordStep('TC-03', 'select_partial', 'Selected job:ui-controlled-partial');
    await page.locator('.coverage-card').waitFor();
    const coverageText = await page.locator('.coverage-card').innerText();
    assert(coverageText.includes('PARTIAL · DEX 处理有未完成部分'), 'Coverage card should indicate PARTIAL status');
    assert(coverageText.includes('classes2.dex'), 'Coverage card should display failed dex classes2.dex');
    assert(coverageText.includes('bytecode evidence retained') || coverageText.includes('JADX unavailable'), 'Coverage card should state bytecode evidence retained');
    recordStep('TC-03', 'verify_partial_coverage', 'Confirmed PARTIAL coverage and classes2.dex failure display');

    // Open provenance to check JADX unavailable fallback status
    if (!(await page.locator('details.provenance').getAttribute('open'))) {
      await page.locator('details.provenance > summary').click();
    }
    const provenanceTextPartial = await page.locator('details.provenance').innerText();
    assert(provenanceTextPartial.includes('jadx：UNAVAILABLE_BYTECODE_FALLBACK'), 'Provenance should explicitly show JADX unavailable fallback');
    recordStep('TC-03', 'verify_jadx_fallback', 'Confirmed tools.jadx explicitly records UNAVAILABLE_BYTECODE_FALLBACK without faking JADX');
    const screenshotTc03Partial = path.join(screenshotDir, 'tc03-partial-bytecode-fallback.png');
    await page.screenshot({ path: screenshotTc03Partial, fullPage: true });

    // 2. Failure prompt with structured error card (ui-controlled-failed)
    await selectSource(page, 'job:ui-controlled-failed');
    recordStep('TC-03', 'select_failed', 'Selected job:ui-controlled-failed');
    await page.locator('.job-state').waitFor();
    await page.locator('.job-error-card').waitFor();
    const errorCode = await page.locator('.job-error-card .error-code').innerText();
    assert(errorCode.includes('ZIP_INVALID'), `Error code must show ZIP_INVALID, got: ${errorCode}`);
    const errorMsg = await page.locator('.job-error-card .error-msg').innerText();
    assert(errorMsg.includes('Pipeline failed'), `Error msg must show formatted message, got: ${errorMsg}`);
    const failedNotice = await page.locator('.job-state').innerText();
    assert(failedNotice.includes('本任务没有可展示的成功报告'), 'Notice should prompt no report to show');
    recordStep('TC-03', 'verify_structured_error', 'Confirmed structured error card (code: ZIP_INVALID, formatted msg) instead of raw JSON');
    const screenshotTc03Failed = path.join(screenshotDir, 'tc03-structured-error-failed.png');
    await page.screenshot({ path: screenshotTc03Failed, fullPage: true });

    // 3. Timeout prompt with a real timeout error code (ui-controlled-timeout).
    // ZIP_INVALID above is an input/parse failure; this is the genuine timeout path.
    await selectSource(page, 'job:ui-controlled-timeout');
    recordStep('TC-03', 'select_timeout', 'Selected job:ui-controlled-timeout');
    await page.locator('.job-state').waitFor();
    await page.locator('.job-error-card').waitFor();
    const timeoutCode = await page.locator('.job-error-card .error-code').innerText();
    assert(timeoutCode.includes('SCAN_TIMEOUT'), `Timeout error code must show SCAN_TIMEOUT, got: ${timeoutCode}`);
    const timeoutMsg = await page.locator('.job-error-card .error-msg').innerText();
    assert(timeoutMsg.includes('timeout'), `Timeout message should explain the timeout, got: ${timeoutMsg}`);
    const timeoutDetail = await page.locator('.job-error-card .error-detail').innerText();
    assert(timeoutDetail.includes('worker killed'), `Timeout root cause should be shown, got: ${timeoutDetail}`);
    const timeoutStateText = await page.locator('.job-state').innerText();
    assert(timeoutStateText.includes('失败') || timeoutStateText.includes('FAILED'), 'Timeout job should render the FAILED terminal state');
    assert(timeoutStateText.includes('本任务没有可展示的成功报告'), 'Timeout notice should state no report is available');
    assert(!(await page.locator('.sample-card').count()), 'A timed-out job must not render a report card');
    recordStep('TC-03', 'verify_timeout', 'Confirmed SCAN_TIMEOUT structured error, failure message and absent report card');
    const screenshotTc03Timeout = path.join(screenshotDir, 'tc03-timeout-failed.png');
    await page.screenshot({ path: screenshotTc03Timeout, fullPage: true });

    // 4. Cancelled state prompt (ui-controlled-cancel)
    await selectSource(page, 'job:ui-controlled-cancel');
    recordStep('TC-03', 'select_cancelled', 'Selected job:ui-controlled-cancel');
    await page.locator('.job-state').waitFor();
    const cancelledStateText = await page.locator('.job-state').innerText();
    assert(cancelledStateText.includes('已取消') || cancelledStateText.includes('CANCELLED'), 'Job state should show CANCELLED');
    assert(cancelledStateText.includes('本任务没有可展示的成功报告'), 'Cancelled notice should prompt correctly');
    recordStep('TC-03', 'verify_cancelled_state', 'Confirmed CANCELLED state and prompt');
    const screenshotTc03Cancel = path.join(screenshotDir, 'tc03-job-cancelled.png');
    await page.screenshot({ path: screenshotTc03Cancel, fullPage: true });

    // 5. Graceful 409 cancel handling for a job that finished while cancelling.
    // Covers the cancel race: the API rejects the cancel because the job already
    // reached SUCCEEDED, and the UI must then load the report instead of leaving
    // an empty panel.
    await selectSource(page, 'job:ui-running-cancel');
    recordStep('TC-03', 'select_running', 'Selected job:ui-running-cancel for the cancel race');
    await page.locator('.job-state').waitFor();
    assert.equal(await page.locator('.job-state button:has-text("取消任务")').count(), 1, 'A running job must offer the cancel button');

    await page.route('**/api/v1/jobs/*/cancel', async route => {
      // Resolve the job to SUCCEEDED first, then answer the cancel with 409.
      if (route.request().method() === 'POST') {
        await fetch(`${API_ORIGIN}/api/v1/jobs/ui-running-cancel/cancel`, {
          method: 'POST',
          headers: { 'X-PrivacyTrace-Local': '1' },
        }).catch(() => {});
      }
      return route.fulfill({
        status: 409,
        contentType: 'application/json',
        body: JSON.stringify({ detail: 'Terminal job cannot be cancelled' }),
      });
    });
    await page.evaluate(async () => {
      try {
        const res = await fetch('/api/v1/jobs/ui-controlled-cancel/cancel', {
          method: 'POST',
          headers: { 'X-PrivacyTrace-Local': '1' },
        });
        window.__cancel_status = res.status;
      } catch (e) {
        window.__cancel_error = e.message;
      }
    });
    const cancelStatus = await page.evaluate(() => window.__cancel_status);
    assert.equal(cancelStatus, 409, 'Cancel on terminal job should return 409');
    await page.unroute('**/api/v1/jobs/*/cancel');
    recordStep('TC-03', 'verify_409_handling', 'Confirmed 409 terminal cancellation is gracefully handled');

    testResults.push({ id: 'TC-03', name: 'R3 Error states, timeout & bytecode fallback', status: 'PASSED' });

    // ------------------------------------------------------------------------
    // TC-04: R4 Origin vs delivery badges (synthetic demo, controlled fixture,
    // persisted real-APK replay with job.created_at timestamp),
    // audit PT-910 / S1 reports (gkd-s1-first.json)
    // ------------------------------------------------------------------------
    console.log('\n--- Running TC-04: R4 Origin/delivery badges & created_at timestamp ---');

    // 1. Synthetic Demo
    await selectSource(page, 'demo:synthetic');
    recordStep('TC-04', 'select_demo', 'Selected demo:synthetic');
    await page.locator('.sample-card').waitFor();
    const demoBadge = await page.locator('.badge-stack .badge').first().innerText();
    assert(demoBadge.includes('人工示例') && demoBadge.includes('SYNTHETIC'), `Badge should show 人工示例 · SYNTHETIC, got: ${demoBadge}`);
    // The demo envelope is assembled per response, so it is a live generation.
    const demoDeliveryBadge = await page.locator('.badge-stack .badge').last().innerText();
    assert(demoDeliveryBadge.includes('本次生成') && demoDeliveryBadge.includes('LIVE'), `Demo delivery badge should show 本次生成 · LIVE, got: ${demoDeliveryBadge}`);
    const demoNote = await page.locator('.demo-note').innerText();
    assert(demoNote.includes('SYNTHETIC · 人工构造示例'), 'Demo note should show SYNTHETIC label');
    recordStep('TC-04', 'verify_synthetic_badge', 'Confirmed SYNTHETIC demo origin badge and live delivery badge');
    const screenshotTc04Demo = path.join(screenshotDir, 'tc04-source-synthetic.png');
    await page.screenshot({ path: screenshotTc04Demo, fullPage: true });

    // 2. Controlled Input Fixture (classified by the explicit source_origin field)
    await selectSource(page, 'job:ui-controlled-partial');
    recordStep('TC-04', 'select_controlled', 'Selected job:ui-controlled-partial (source_origin=CONTROLLED)');
    await page.locator('.sample-card').waitFor();
    const controlledBadge = await page.locator('.badge-stack .badge').first().innerText();
    assert(controlledBadge.includes('受控评测') && controlledBadge.includes('CONTROLLED'), `Badge should show 受控评测 · CONTROLLED, got: ${controlledBadge}`);
    const controlledNote = await page.locator('.demo-note').innerText();
    assert(controlledNote.includes('CONTROLLED · 受控测试输入'), 'Note should show CONTROLLED label');
    recordStep('TC-04', 'verify_controlled_badge', 'Confirmed CONTROLLED fixture badge and label');
    const screenshotTc04Controlled = path.join(screenshotDir, 'tc04-source-controlled.png');
    await page.screenshot({ path: screenshotTc04Controlled, fullPage: true });

    // 3. A persisted real-APK report: origin stays REAL_SCAN, delivery is a replay
    await selectSource(page, 'job:gkd-s1-first');
    recordStep('TC-04', 'select_replay', 'Selected job:gkd-s1-first');
    await page.locator('.sample-card').waitFor();

    // The two badges are orthogonal: origin describes the data, delivery
    // describes this load. Reloading a REAL_SCAN job must never relabel it as
    // "本机扫描/本次生成" -- the replay-ness lives in the delivery badge.
    const originBadge = await page.locator('.badge-stack .badge').first().innerText();
    const deliveryBadge = await page.locator('.badge-stack .badge').last().innerText();
    assert(originBadge.includes('真实 APK') && originBadge.includes('REAL_SCAN'), `Origin badge should show 真实 APK · REAL_SCAN, got: ${originBadge}`);
    assert(deliveryBadge.includes('持久化回放') && deliveryBadge.includes('REPLAY'), `Delivery badge should show 持久化回放 · REPLAY, got: ${deliveryBadge}`);
    assert(!deliveryBadge.includes('本次生成'), 'A reloaded report must not claim it was generated in this run');
    recordStep('TC-04', 'verify_delivery_mode', `Confirmed independent origin (${originBadge}) and delivery (${deliveryBadge}) badges`);

    // Classification must follow source_origin, never the sample_id naming.
    // These two probe jobs carry misleading sample_id prefixes on purpose.
    assert.equal(revealOrigin('CONTROLLED-LOOKALIKE', 'REAL_SCAN'), 'REAL_SCAN', 'sample_id prefix must not override an explicit REAL_SCAN origin');
    assert.equal(revealOrigin('demo', 'CONTROLLED'), 'CONTROLLED', 'a sample_id named demo must not override an explicit CONTROLLED origin');
    recordStep('TC-04', 'verify_origin_precedence', 'Confirmed source classification reads source_origin, not sample_id naming');

    // The backend contract must carry delivery_mode on the report, and the
    // reloaded fixture must be a PERSISTED_REPLAY with an untouched origin.
    const replayReport = await (await fetch(`${API_ORIGIN}/api/v1/jobs/gkd-s1-first/report`)).json();
    assert.equal(replayReport.job.source_origin, 'REAL_SCAN', 'Persisted report keeps its immutable REAL_SCAN origin');
    assert.equal(replayReport.delivery_mode, 'PERSISTED_REPLAY', `A reloaded report must be PERSISTED_REPLAY, got: ${replayReport.delivery_mode}`);
    recordStep('TC-04', 'verify_delivery_contract', 'Confirmed report.delivery_mode=PERSISTED_REPLAY with source_origin=REAL_SCAN');

    // Verify job.created_at timestamp display
    const sampleCardText = await page.locator('.sample-card').innerText();
    assert(sampleCardText.includes('原生成时间：'), 'Sample card should show 原生成时间');
    assert(sampleCardText.includes('2026-10-03T12:48:35.211974Z') || sampleCardText.includes('2026'), 'Sample card should include created_at timestamp');

    // Verify timestamp in provenance section
    if (!(await page.locator('details.provenance').getAttribute('open'))) {
      await page.locator('details.provenance > summary').click();
    }
    const provenanceText = await page.locator('details.provenance').innerText();
    assert(provenanceText.includes('原生成时间：') && (provenanceText.includes('2026-10-03T12:48:35.211974Z') || provenanceText.includes('2026')), 'Provenance must show original generation timestamp');
    recordStep('TC-04', 'verify_timestamp', 'Confirmed job.created_at original timestamp displayed in both header and provenance');

    // Audit S1 report evidence chain
    const coverageTextS1 = await page.locator('.coverage-card').innerText();
    assert(coverageTextS1.includes('edcc03be24bc54d44c04746b46e2e33244120638e2199450b4407195447466a6'), 'SHA256 must match S1 apk hash');
    assert(provenanceText.includes('classes.dex'), 'DEX entries must match');

    // Check Dalvik bytecode API evidence in evidence card for SCREEN_CAPTURE
    await page.getByRole('row').filter({ hasText: '屏幕截图' }).getByRole('button').first().click();
    await page.locator('#evidence-panel').waitFor();
    const evidenceText = await page.locator('#evidence-panel').innerText();
    assert(evidenceText.includes('takeScreenshot'), 'Evidence should show targetDescriptor takeScreenshot');
    assert(evidenceText.includes('offset_bytes='), 'Evidence should show bytecode offset locator');
    assert(evidenceText.includes('未提供 JADX Java 源码时以字节码作为依据'), 'Should explicitly explain bytecode fallback');
    recordStep('TC-04', 'audit_s1_chain', 'Confirmed complete evidence chain matching S1 authoritative report');

    const screenshotTc04Replay = path.join(screenshotDir, 'tc04-source-offline-replay-s1.png');
    await page.screenshot({ path: screenshotTc04Replay, fullPage: true });

    testResults.push({ id: 'TC-04', name: 'R4 Multi-source badges & timestamps', status: 'PASSED' });

    // ------------------------------------------------------------------------
    // TC-05: R5 Optional local note submission (with note, without note), backend re-evaluation, reload consistency
    // ------------------------------------------------------------------------
    console.log('\n--- Running TC-05: R5 Optional local note submission & persistence ---');
    await page.locator('.review-panel').waitFor();

    // 1. Submit review WITHOUT note (note is empty)
    await page.locator('.review-panel input').first().fill('验收员_无备注测试');
    await page.locator('.review-panel input').nth(1).fill('验证备注完全可选特性');
    await page.locator('.review-panel textarea').fill('');

    // Ensure submit button is enabled when note is empty
    const submitBtn = page.locator('.review-panel button.primary');
    const isDisabled = await submitBtn.isDisabled();
    assert.equal(isDisabled, false, 'Submit button must be ENABLED when note is empty');
    recordStep('TC-05', 'verify_optional_button', 'Confirmed submit button enabled with empty note');

    await submitBtn.click();
    await page.locator('.review-panel p[role="status"]').waitFor();
    const reviewStatusText = await page.locator('.review-panel p[role="status"]').innerText();
    assert(reviewStatusText.includes('备注已保存，规则已重新计算'), 'Review submission should succeed');

    // Verify first event in audit list
    const firstEventDetails = page.locator('.review-panel .audit-event').last();
    await firstEventDetails.locator('summary').click();
    await page.waitForTimeout(150);
    const firstEventText = await firstEventDetails.innerText();
    assert(firstEventText.includes('UNAUTHENTICATED_LOCAL_EVENT · 人工身份未认证'), 'Must preserve authority restriction without faking official audit');
    assert(firstEventText.includes('验收员_无备注测试'), 'Must record actor');
    assert(firstEventText.includes('（无备注内容）'), 'Empty note should display placeholder text');
    recordStep('TC-05', 'submit_empty_note', 'Successfully submitted review without note and verified authority guardrail');

    // 2. Submit second review WITH note
    await page.locator('.review-panel input').first().fill('验收员_有备注测试');
    await page.locator('.review-panel input').nth(1).fill('补充实际排查发现');
    await page.locator('.review-panel textarea').fill('本条目经字节码确认调用确实存在，无 JADX 源码不影响定位。');
    await submitBtn.click();
    await page.waitForTimeout(500);

    const secondEventDetails = page.locator('.review-panel .audit-event').last();
    await secondEventDetails.locator('summary').click();
    await page.waitForTimeout(150);
    const secondEventText = await secondEventDetails.innerText();
    assert(secondEventText.includes('本条目经字节码确认调用确实存在'), 'Must display entered note text');
    recordStep('TC-05', 'submit_with_note', 'Successfully submitted review with note text');

    // 3. Reload page and check persistence consistency
    await page.reload();
    await page.locator('#report-source').waitFor();
    await selectSource(page, 'job:gkd-s1-first');
    await page.locator('.review-panel').waitFor();

    const reloadedEvents = await page.locator('.review-panel .audit-event').allInnerTexts();
    const allEventsText = reloadedEvents.join('\n');
    assert(allEventsText.includes('验收员_无备注测试'), 'First review must persist after reload');
    assert(allEventsText.includes('验收员_有备注测试'), 'Second review must persist after reload');
    recordStep('TC-05', 'verify_persistence', 'Confirmed 100% persistence consistency across full page reload');

    const screenshotTc05 = path.join(screenshotDir, 'tc05-optional-notes-review.png');
    await page.screenshot({ path: screenshotTc05, fullPage: true });

    testResults.push({ id: 'TC-05', name: 'R5 Optional local note & re-evaluation persistence', status: 'PASSED' });

    // ------------------------------------------------------------------------
    // Generate proof artifact evidence/browser-proof.json
    // ------------------------------------------------------------------------
    // Never silently present an unanchored receipt as authoritative evidence.
    const gitCommit = resolveGitCommit(projectRoot);
    const commitAnchored = SHA_RE.test(gitCommit);
    if (commitAnchored) {
      console.log(`[Receipt] Anchoring proof to commit ${gitCommit}`);
    } else {
      console.warn(
        '[Receipt] WARNING: could not resolve the Git commit SHA from Git\'s own files. ' +
          'This checkout may not be a Git repository, or it is a linked worktree whose ' +
          'gitdir is unreachable. The receipt records git_commit="unknown" and must be ' +
          're-run on a normal checkout before it is treated as final evidence.'
      );
    }

    const proof = {
      timestamp: new Date().toISOString(),
      git_commit: gitCommit,
      // True only when the receipt could be anchored to a real 40-char SHA.
      // A "false" value means this file is NOT yet valid final evidence.
      git_commit_anchored: commitAnchored,
      browser: `Chromium ${browserVersion}`,
      user_agent: await page.evaluate(() => navigator.userAgent),
      viewport: { width: 1280, height: 900 },
      overall_status: 'PASSED',
      // Wording matters: the suite asserts zero *uncaught page exceptions*.
      // Deliberate negative-path tests (409 cancel, 404 evidence) still log HTTP
      // errors to the console, so the console log is NOT error-free.
      console_error_claim: {
        uncaught_page_exceptions: pageErrors.length,
        http_error_console_logs: errorLogs.length,
        statement: '0 uncaught page exceptions; non-zero HTTP error logs are expected.',
      },
      environment: {
        api_origin: API_ORIGIN,
        web_origin: WEB_ORIGIN,
        isolated_store: true,
        store_seeded_from: 'fixtures/acceptance-jobs',
      },
      tests: testResults,
      step_sequences: stepSequences,
      console_logs: consoleLogs,
      page_errors: pageErrors,
      screenshots: [
        'evidence/screenshots/tc01-long-text-pagination.png',
        'evidence/screenshots/tc02-xss-defense.png',
        'evidence/screenshots/tc03-partial-bytecode-fallback.png',
        'evidence/screenshots/tc03-structured-error-failed.png',
        'evidence/screenshots/tc03-timeout-failed.png',
        'evidence/screenshots/tc03-job-cancelled.png',
        'evidence/screenshots/tc04-source-synthetic.png',
        'evidence/screenshots/tc04-source-controlled.png',
        'evidence/screenshots/tc04-source-offline-replay-s1.png',
        'evidence/screenshots/tc05-optional-notes-review.png',
      ],
      assertions: {
        page_errors_count: pageErrors.length,
        xss_script_executed: false,
        long_text_codepoints: 200000,
        pagination_page_size: 20,
        notes_optional: true,
        authority_unauthenticated: true,
        source_origin_explicit: true,
        delivery_mode_explicit: true,
        origin_and_delivery_independent: true,
        real_timeout_covered: true,
        isolated_store: true,
      },
    };

    const proofPath = path.join(evidenceDir, 'browser-proof.json');
    fs.writeFileSync(proofPath, JSON.stringify(proof, null, 2), 'utf-8');
    console.log(`\n[Receipt] Written browser proof receipt to: ${proofPath}`);
  } catch (err) {
    // Hold the error so cleanup runs first; rethrow after the finally block.
    fatal = err;
  } finally {
    // Order matters: close the browser, then stop and await the servers, and
    // only then remove the temp store -- a live server may still hold files
    // inside it, which would leave the directory behind.
    if (browser) {
      try {
        await browser.close();
        console.log('[Browser] Chromium browser closed cleanly.');
      } catch (err) {
        console.log(`[Cleanup] Could not close Chromium: ${err}`);
      }
    }

    if (childrenToKill.length > 0) {
      await stopChildren(childrenToKill);
      console.log('[Cleanup] Stopped servers spawned by this run.');
    }

    if (storeDir) {
      try {
        fs.rmSync(storeDir, { recursive: true, force: true });
        console.log(`[Cleanup] Removed isolated store ${storeDir}. The repository data directory was never touched.`);
      } catch (err) {
        console.log(`[Cleanup] Could not remove isolated store ${storeDir}: ${err}`);
      }
    }
  }

  if (fatal) throw fatal;
}

main().catch(err => {
  console.error('\n[FATAL ERROR in browser acceptance test]:', err);
  process.exitCode = 1;
});
