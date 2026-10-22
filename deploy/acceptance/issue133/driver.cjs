#!/usr/bin/env node
// Lane E canonical variant driver: device actions, server observations,
// persistent-state assertions and per-case UTC evidence.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const HERE = __dirname;
function toWslPath(winPath) {
  const match = /^([A-Za-z]):[\\/](.*)$/.exec(winPath);
  if (!match) return winPath.replaceAll('\\', '/');
  return `/mnt/${match[1].toLowerCase()}/${match[2].replaceAll('\\', '/')}`;
}
const CLIENT = path.join(HERE, 'client.cjs');
const CONTROL = path.posix.join(toWslPath(HERE), 'control.sh');
const MATRIX = JSON.parse(fs.readFileSync(path.join(HERE, 'matrix.json'), 'utf8'));
const TICKET_SOURCE = '42088231db0817e385b64f7a0809e31010b3e81e';
const EXPECTED_CLIENT_APK = '0be49358bc20128f66eb1a5a386d42dd130eec8846f8c363aa0fc7880a7b8c17';
const EXPECTED_FIXTURE_APK = '65047dbcf0b3ef4876d422b68e5bde777a13dd84f59bd946c66c1279921ab981';
const CANDIDATE_BUTTON = '\u4fdd\u5b58\u5019\u9009\u5e76\u5f00\u59cb\u5206\u6790';
const RESTORE_BUTTON = '\u6062\u590d\u5f53\u524d\u5b9e\u4f8b\u6750\u6599';

const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const now = () => new Date().toISOString();
const sha256 = buffer => crypto.createHash('sha256').update(buffer).digest('hex');
const sha256File = file => sha256(fs.readFileSync(file));
const readJson = file => JSON.parse(fs.readFileSync(file, 'utf8').replace(/^\uFEFF/, ''));

function parseJsonOutput(text) {
  const trimmed = String(text || '').trim();
  if (!trimmed) throw new Error('empty JSON output');
  try { return JSON.parse(trimmed); } catch { /* collect complete objects below */ }
  const candidates = [];
  let depth = 0, start = -1, inString = false, escaped = false;
  for (let index = 0; index < trimmed.length; index += 1) {
    const character = trimmed[index];
    if (inString) {
      if (escaped) escaped = false;
      else if (character === '\\') escaped = true;
      else if (character === '"') inString = false;
      continue;
    }
    if (character === '"') inString = true;
    else if (character === '{') { if (depth === 0) start = index; depth += 1; }
    else if (character === '}') {
      depth -= 1;
      if (depth === 0 && start >= 0) { candidates.push(trimmed.slice(start, index + 1)); start = -1; }
    }
  }
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    try { return JSON.parse(candidates[index]); } catch { /* older object */ }
  }
  throw new Error(`no JSON object in output: ${trimmed.slice(-300)}`);
}

class CaseFailure extends Error {
  constructor(message, classification = 'PRODUCT_ASSERTION') {
    super(message);
    this.classification = classification;
  }
}

class Context {
  constructor(caseId, config) {
    this.caseId = caseId;
    this.config = config;
    this.dir = path.join(config.evidenceRoot, caseId);
    fs.mkdirSync(this.dir, { recursive: true });
    this.timeline = [];
    this.checks = [];
    this.commands = [];
    this.track = {
      drafts: [], deletedDrafts: [], jobAliases: [], jobsByDraft: {},
      workerStopped: false, workerPaused: false, scannerDelayed: false, offline: false,
    };
    this.clientConfigPath = path.join(this.dir, 'client-config.json');
    fs.writeFileSync(this.clientConfigPath, JSON.stringify({
      origin: config.origin,
      port: config.port,
      cdpPort: config.cdpPort,
      serial: config.serial,
      appLabel: config.appLabel,
      packageName: config.packageName,
      clientPackage: config.clientPackage || 'org.privacytrace.mobile',
      output: this.dir,
      runId: caseId,
      backgroundSeconds: config.backgroundSeconds || 40,
      mumuManager: config.mumuManager,
      vmIndex: config.vmIndex,
    }, null, 2), 'utf8');
  }
  event(phase, data = {}) {
    const item = { at_utc: now(), phase, ...data };
    this.timeline.push(item);
    return item;
  }
  check(name, pass, expected, actual, classification = 'PRODUCT_ASSERTION') {
    const item = { name, pass: Boolean(pass), expected, actual, classification };
    this.checks.push(item);
    if (!pass) throw new CaseFailure(`${name}: expected=${JSON.stringify(expected)} actual=${JSON.stringify(actual)}`, classification);
    return item;
  }
  writeJson(name, value) {
    const file = path.join(this.dir, name);
    fs.writeFileSync(file, JSON.stringify(value, null, 2), 'utf8');
    return file;
  }
  control(action, args = [], { quiet = false } = {}) {
    const started = Date.now();
    const envArgs = ['env', `PT133E_LAB_STATE=${this.config.labState}`];
    if (this.config.controller) envArgs.push(`PT133E_CONTROLLER=${this.config.controller}`);
    const result = spawnSync('wsl.exe', [
      '-d', this.config.wslDistro, '-u', 'root', '--', ...envArgs,
      'bash', CONTROL, action, ...args,
    ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 600000 });
    const elapsed = Date.now() - started;
    this.commands.push({ at_utc: now(), kind: 'control', action, args, status: result.status, elapsed_ms: elapsed });
    if (result.status !== 0) {
      throw new CaseFailure(`control ${action} failed (${result.status}): ${String(result.stderr || '').slice(-400)}`, 'ENVIRONMENT');
    }
    const value = parseJsonOutput(result.stdout);
    if (!quiet) this.writeJson(`control-${action}-${Date.now()}.json`, value);
    return value;
  }
  client(action) {
    const started = Date.now();
    const result = spawnSync(process.execPath, [CLIENT, action, this.clientConfigPath], {
      encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 900000,
      env: {
        ...process.env,
        PT_ADB: this.config.adb,
        PT_ADB_SERIAL: this.config.serial,
        ...(this.config.adbServerPort ? { ANDROID_ADB_SERVER_PORT: String(this.config.adbServerPort) } : {}),
      },
    });
    const elapsed = Date.now() - started;
    this.commands.push({ at_utc: now(), kind: 'client', action, status: result.status, elapsed_ms: elapsed });
    if (result.status !== 0) {
      const detail = `${String(result.stderr || '').slice(-300)} ${String(result.stdout || '').slice(-300)}`;
      throw new CaseFailure(`client ${action} failed (${result.status}): ${detail}`, 'DRIVER');
    }
    let value;
    try { value = parseJsonOutput(result.stdout); }
    catch (error) { throw new CaseFailure(`client ${action} output was not JSON: ${String(result.stdout || '').slice(-300)}`, 'DRIVER'); }
    this.writeJson(`client-${action}-${Date.now()}.json`, value);
    return value;
  }
  scope(alias, opts) { return this.control('scope', ['--scope', alias], opts); }
  layers(alias, jobAliases = [], opts) {
    const args = ['--scope', alias];
    for (const item of jobAliases) args.push('--job-alias', item);
    return this.control('material-layers', args, opts);
  }
  observe(opts) { return this.control('observe', [], opts); }
  rememberJob(draftAlias, jobAlias) {
    this.track.jobAliases.push(jobAlias);
    if (!this.track.jobsByDraft[draftAlias]) this.track.jobsByDraft[draftAlias] = [];
    this.track.jobsByDraft[draftAlias].push(jobAlias);
  }
  jobAliasesFor(draftAlias) { return this.track.jobsByDraft[draftAlias] || []; }
  async waitJob(alias, predicate, description, timeoutMs = 180000) {
    const deadline = Date.now() + timeoutMs;
    let last = null;
    while (Date.now() < deadline) {
      // Prefer the persistent read model: the HTTP observer shares the API rate
      // budget and a 429 must not be mistaken for "no job".
      last = await this.layers(alias, this.jobAliasesFor(alias), { quiet: true });
      if (predicate(last.jobs || [])) return last;
      await sleep(1000);
    }
    throw new CaseFailure(`${description}; last=${JSON.stringify(last && last.jobs)}`);
  }
  async cleanup() {
    const notes = [];
    if (this.track.workerPaused) {
      try { await this.control('unpause-worker'); notes.push('unpaused worker'); } catch (e) { notes.push(`unpause failed: ${e.message}`); }
      this.track.workerPaused = false;
    }
    if (this.track.workerStopped) {
      try { await this.control('start-worker'); notes.push('started worker'); } catch (e) { notes.push(`start-worker failed: ${e.message}`); }
      this.track.workerStopped = false;
    }
    if (this.track.scannerDelayed) {
      try { await this.control('restore-scanner'); notes.push('restored scanner image'); } catch (e) { notes.push(`restore-scanner failed: ${e.message}`); }
      this.track.scannerDelayed = false;
    }
    if (this.track.offline) {
      try { await this.client('net-unblock'); notes.push('device network path restored'); } catch (e) { notes.push(`net-unblock failed: ${e.message}`); }
      this.track.offline = false;
    }
    for (const alias of this.track.drafts) {
      if (this.track.deletedDrafts.includes(alias)) continue;
      try {
        const result = await this.control('delete-scope', ['--scope', alias]);
        let tombstone = null;
        try { tombstone = await this.control('wait-tombstone', ['--scope', alias, '--timeout', '60']); }
        catch (e) { notes.push(`tombstone wait failed for ${alias}: ${e.message}`); }
        notes.push(`cleanup delete ${alias} status=${result.delete_status} tombstone=${Boolean(tombstone)}`);
      } catch (e) { notes.push(`cleanup delete failed for ${alias}: ${e.message}`); }
    }
    this.event('cleanup', { notes });
    return notes;
  }
}

async function ensureIdentity(ctx) {
  const cache = path.join(ctx.config.evidenceRoot, 'identity.json');
  if (fs.existsSync(cache) && !ctx.config.refreshIdentity) return readJson(cache);
  const identity = ctx.client('identity');
  fs.writeFileSync(cache, JSON.stringify(identity, null, 2), 'utf8');
  return identity;
}
const latestJob = scope => (scope.jobs || [])[(scope.jobs || []).length - 1] || null;
const jobAliasForId = id => crypto.createHash('sha256').update(id).digest('hex').slice(0, 12);

async function prepareCase(ctx) {
  ctx.event('case-start', { case_id: ctx.caseId });
  const identity = await ensureIdentity(ctx);
  ctx.identity = identity;
  const clientApk = (identity.client_installed?.paths || []).find(item => item.sha256);
  const fixtureApk = (identity.installed?.paths || []).find(item => item.sha256);
  ctx.writeJson('identity-used.json', identity);
  const expectedClient = ctx.config.expectedClientApkSha || EXPECTED_CLIENT_APK;
  const expectedFixture = ctx.config.expectedFixtureApkSha || EXPECTED_FIXTURE_APK;
  ctx.check('client-apk-sha256', clientApk && clientApk.sha256 === expectedClient, expectedClient, clientApk && clientApk.sha256, 'IDENTITY');
  ctx.check('fixture-apk-sha256', fixtureApk && fixtureApk.sha256 === expectedFixture, expectedFixture, fixtureApk && fixtureApk.sha256, 'IDENTITY');
  if (ctx.config.expectedDeviceSerial) {
    ctx.check('device-serial', identity.serial === ctx.config.expectedDeviceSerial, ctx.config.expectedDeviceSerial, identity.serial, 'IDENTITY');
  }
  await ctx.control('health');
  const scopes = await ctx.control('scope-list');
  for (const item of (scopes.scopes || []).filter(entry => !entry.tombstone)) {
    try { await ctx.control('delete-scope', ['--scope', item.alias]); ctx.event('stale-scope-deleted', { alias: item.alias }); }
    catch (error) { ctx.event('stale-scope-cleanup-failed', { alias: item.alias, error: error.message }); }
  }
  return identity;
}

async function listScopes(ctx) { return ctx.control('scope-list', [], { quiet: true }); }

async function freshDraft(ctx, { prepare = true } = {}) {
  const before = new Set((await listScopes(ctx)).scopes.map(item => item.alias));
  await ctx.client('reset');
  const upload = await ctx.client('upload');
  const after = await listScopes(ctx);
  const created = (after.scopes || []).filter(item => !before.has(item.alias));
  ctx.check('one-new-scope', created.length === 1, 1, created.map(item => item.alias));
  const scope = created[0];
  ctx.check('scope-token-captured', scope.has_captured_token, true, scope.has_captured_token);
  ctx.track.drafts.push(scope.alias);
  ctx.track.alias = scope.alias;
  ctx.track.draftAlias = scope.draft_alias;
  ctx.event('draft-created', { alias: scope.alias, draft_alias: scope.draft_alias, upload_at: upload.at_utc });
  if (prepare) {
    const prepared = await ctx.client('prepare');
    const statusText = (prepared.status_texts || []).join(' ');
    ctx.check('candidate-page', statusText.includes('\u5df2\u68c0\u67e5') || (prepared.buttons || []).some(button => button.text.includes(CANDIDATE_BUTTON)), 'candidate page', prepared.status_texts);
    ctx.track.prepared = true;
  }
  return scope;
}

async function beginJob(ctx) {
  // Upload/prepare plus the previous case can approach the product's 60/min
  // client-IP budget; let the sliding window drain before the paid start.
  await sleep(61000);
  const snap = await ctx.client('begin');
  const knownBefore = new Set(ctx.jobAliasesFor(ctx.track.alias));
  const scope = await ctx.waitJob(ctx.track.alias, jobs => jobs.some(job => !knownBefore.has(job.job_alias)), 'job row after start', 120000);
  const job = (scope.jobs || []).find(item => !knownBefore.has(item.job_alias)) || latestJob(scope);
  ctx.check('job-row-created', Boolean(job), true, Boolean(job));
  ctx.rememberJob(ctx.track.alias, job.job_alias);
  ctx.track.jobAlias = job.job_alias;
  let jobId = snap.visible_job_id || null;
  if (!jobId) {
    for (const item of snap.visible_scope_ids || []) {
      if (jobAliasForId(item) === job.job_alias) jobId = item;
    }
  }
  ctx.track.jobId = jobId;
  ctx.event('job-started', { job_alias: job.job_alias, state: job.state, job_id: jobId, ui_job_id: snap.visible_job_id });
  return { ...job, job_id: jobId };
}

async function retryJob(ctx, expectedJobCount) {
  // The retry is a second paid submission in the same case; drain the window.
  await sleep(61000);
  const knownBefore = new Set(ctx.jobAliasesFor(ctx.track.alias));
  const snap = await ctx.client('retry');
  const scope = await ctx.waitJob(ctx.track.alias, jobs => jobs.some(job => !knownBefore.has(job.job_alias)) && jobs.length === expectedJobCount, 'retry job row', 120000);
  const job = (scope.jobs || []).find(item => !knownBefore.has(item.job_alias)) || latestJob(scope);
  ctx.check('retry-new-job-row', Boolean(job), true, Boolean(job));
  ctx.rememberJob(ctx.track.alias, job.job_alias);
  ctx.track.jobAlias = job.job_alias;
  ctx.track.jobId = snap.visible_job_id || null;
  const enriched = layerJob(await ctx.layers(ctx.track.alias, [job.job_alias]), job.job_alias) || {};
  ctx.event('job-retried', { job_alias: job.job_alias, retry_of_alias: enriched.retry_of_alias || null, ui_job_id: snap.visible_job_id });
  return { ...job, retry_of_alias: enriched.retry_of_alias || null };
}

async function countNativeRequests(ctx, routeSuffix, scopeAlias) {
  const observation = await ctx.observe({ quiet: true });
  return {
    count: (observation.requests || []).filter(item => item.actor === 'ANDROID_NATIVE' && item.route.endsWith(routeSuffix) && item.scope_alias === scopeAlias).length,
    observed_at: observation.at_utc,
  };
}
const layerJob = (layers, alias) => (layers.jobs || []).find(item => item.job_alias === alias) || null;

async function cancelJob(ctx, { jobAlias = ctx.track.jobAlias } = {}) {
  const known = ctx.jobAliasesFor(ctx.track.alias);
  const beforeLayers = await ctx.layers(ctx.track.alias, known);
  const before = layerJob(beforeLayers, jobAlias);
  ctx.check('cancel-before-job', Boolean(before), true, Boolean(before));
  const snap = await ctx.client('cancel');
  ctx.check('cancel-ui-confirmed', snap.shows_cancelled || snap.job_state === 'CANCELLED', true, snap.job_state);
  await ctx.waitJob(ctx.track.alias, jobs => jobs.some(item => item.job_alias === jobAlias && item.state === 'CANCELLED'), 'job CANCELLED', 120000);
  const afterLayers = await ctx.layers(ctx.track.alias, known);
  const after = layerJob(afterLayers, jobAlias);
  ctx.check('cancel-job-state', after && after.state === 'CANCELLED', 'CANCELLED', after && after.state);
  ctx.check('cancel-execution-revoked', after && after.execution_state === 'REVOKED', 'REVOKED', after && after.execution_state);
  ctx.check('cancel-fence-advanced', after && Number(after.fence) > Number(before.fence), `>${before.fence}`, after && after.fence);
  ctx.check('cancel-no-report', after && !after.has_report, false, after && after.has_report);
  ctx.check('cancel-report-zero', (afterLayers.reports || []).length === 0, 0, (afterLayers.reports || []).length);
  ctx.event('job-cancelled', { job_alias: jobAlias, fence_before: before.fence, fence_after: after.fence, ui_at: snap.at_utc });
  return { before, after, layers: afterLayers, snap };
}

async function waitNoResurrection(ctx, jobAlias, { milliseconds = 15000, deleted = false } = {}) {
  await sleep(milliseconds);
  await ctx.control('wait-runner-idle', ['--timeout', '120']);
  const known = ctx.jobAliasesFor(ctx.track.alias);
  const layers = await ctx.layers(ctx.track.alias, known);
  const job = layerJob(layers, jobAlias);
  if (deleted) {
    ctx.check('late-no-scope-revive', Boolean((layers.scope_row || {}).tombstone), true, layers.scope_row && layers.scope_row.tombstone);
    ctx.check('late-no-report', !job || !job.has_report, false, job && job.has_report);
    if (job) ctx.check('late-no-execution-revive', job.execution_state === 'REVOKED', 'REVOKED', job.execution_state);
  } else {
    ctx.check('late-still-cancelled', job && job.state === 'CANCELLED', 'CANCELLED', job && job.state);
    ctx.check('late-no-report', job && !job.has_report, false, job && job.has_report);
    ctx.check('late-execution-revoked', job && job.execution_state === 'REVOKED', 'REVOKED', job && job.execution_state);
  }
  const scopeNow = await ctx.layers(ctx.track.alias, known, { quiet: true });
  ctx.check('late-job-count', (scopeNow.jobs || []).length === known.length, known.length, (scopeNow.jobs || []).length);
  return layers;
}

async function assertDeleted(ctx, { alias = ctx.track.alias, jobAliases = null, restartApi = false } = {}) {
  jobAliases = jobAliases || ctx.jobAliasesFor(alias);
  const tombstoneArgs = ['--scope', alias];
  for (const item of jobAliases) tombstoneArgs.push('--job-alias', item);
  tombstoneArgs.push('--timeout', '120');
  await ctx.control('wait-tombstone', tombstoneArgs);
  let layers = await ctx.layers(alias, jobAliases);
  const scopeRow = layers.scope_row || {};
  ctx.check('delete-scope-row', Boolean(layers.scope_row), true, Boolean(layers.scope_row));
  ctx.check('delete-scope-tombstone', scopeRow.tombstone === true, true, scopeRow.tombstone);
  ctx.check('delete-token-revoked', scopeRow.has_token_digest === false, false, scopeRow.has_token_digest);
  ctx.check('delete-job-count', (layers.jobs || []).length === jobAliases.length, jobAliases.length, (layers.jobs || []).length);
  for (const job of layers.jobs || []) {
    ctx.check(`delete-${job.job_alias}-execution-revoked`, job.execution_state === 'REVOKED', 'REVOKED', job.execution_state);
    ctx.check(`delete-${job.job_alias}-no-report`, !job.has_report, false, job.has_report);
  }
  ctx.check('delete-documents-zero', (layers.documents || []).length === 0, 0, (layers.documents || []).length);
  ctx.check('delete-runtime-inputs-zero', (layers.runtime_inputs || []).length === 0, 0, (layers.runtime_inputs || []).length);
  ctx.check('delete-runner-materials-zero', (layers.runner_materials || []).length === 0, 0, (layers.runner_materials || []).length);
  ctx.check('delete-uploads-zero', (layers.uploads || []).length === 0, 0, (layers.uploads || []).length);
  ctx.check('delete-reports-zero', (layers.reports || []).length === 0, 0, (layers.reports || []).length);
  ctx.check('delete-draft-dir-gone', !layers.draft_dir || layers.draft_dir.exists === false, false, layers.draft_dir && layers.draft_dir.exists);
  ctx.check('delete-object-refs-intact', layers.objects && layers.objects.referenced_missing === 0, 0, layers.objects && layers.objects.referenced_missing);
  const deletedScopes = new Set((layers.deletions || []).map(item => item.scope_alias));
  ctx.check('delete-intent-draft', deletedScopes.has(layers.draft_alias), true, [...deletedScopes]);
  for (const aliasItem of jobAliases) ctx.check(`delete-intent-${aliasItem}`, deletedScopes.has(aliasItem), true, [...deletedScopes]);
  const auditActions = new Set((layers.audit || []).filter(item => item.scope_alias !== layers.draft_alias).map(item => item.action));
  ctx.check('delete-audit-job-delete', auditActions.has('JOB_DELETE'), true, [...auditActions]);
  for (const row of layers.outbox || []) {
    ctx.check(`delete-outbox-${row.job_alias}`, ['DELIVERED', 'DISCARDED'].includes(row.state), 'DELIVERED|DISCARDED', row.state);
  }
  await ctx.control('wait-runner-idle', ['--timeout', '120']);
  const replay = await ctx.control('replay-deleted', ['--scope', alias]);
  ctx.check('delete-old-access-rejected', replay.all_rejected === true, true, replay.old_access);
  await sleep(10000);
  const persisted = await ctx.layers(alias, jobAliases);
  ctx.check('delete-persists-after-grace', persisted.scope_row && persisted.scope_row.tombstone === true, true, persisted.scope_row && persisted.scope_row.tombstone);
  if (restartApi) {
    await ctx.control('restart-api');
    await sleep(3000);
    const afterRestart = await ctx.layers(alias, jobAliases);
    ctx.check('delete-persists-after-api-restart', afterRestart.scope_row && afterRestart.scope_row.tombstone === true, true, afterRestart.scope_row && afterRestart.scope_row.tombstone);
    const replay2 = await ctx.control('replay-deleted', ['--scope', alias]);
    ctx.check('delete-old-access-rejected-after-restart', replay2.all_rejected === true, true, replay2.old_access);
    layers = afterRestart;
  }
  return { layers, replay };
}

async function deleteDraft(ctx, { alias = ctx.track.alias, jobAliases = null, restartApi = false } = {}) {
  jobAliases = jobAliases || ctx.jobAliasesFor(alias);
  await ctx.scope(alias);
  const before = await ctx.layers(alias, jobAliases);
  const snap = await ctx.client('delete');
  ctx.check('delete-ui-confirmed', snap.deleted_confirmation === true || String((snap.notices || []).join(' ')).includes('\u5220\u9664'), true, snap.notices);
  ctx.event('draft-delete-confirmed', { alias, at_utc: snap.at_utc, notices: snap.notices });
  const result = await assertDeleted(ctx, { alias, jobAliases, restartApi });
  ctx.track.deletedDrafts.push(alias);
  ctx.event('draft-deleted', { alias, before: before.counts, after: result.layers.counts });
  return result;
}

async function dropDraftViaApi(ctx, alias) {
  await ctx.control('delete-scope', ['--scope', alias]);
  await ctx.control('wait-tombstone', ['--scope', alias, '--timeout', '120']);
  ctx.track.deletedDrafts.push(alias);
}

async function readReportViaRestart(ctx, expectedJobId) {
  const current = await ctx.client('snapshot');
  if (expectedJobId && current.visible_job_id === expectedJobId && current.shows_report_button) {
    const report = await ctx.client('report');
    ctx.check('report-visible-direct', report.report_visible === true, true, report.report_visible);
    return report;
  }
  await ctx.client('force-stop');
  await ctx.client('resume');
  const restored = await ctx.client('restore');
  ctx.check('report-restore-job-id', !expectedJobId || restored.visible_job_id === expectedJobId, expectedJobId, restored.visible_job_id);
  const report = await ctx.client('report');
  ctx.check('report-visible-after-restore', report.report_visible === true, true, report.report_visible);
  ctx.event('report-read-via-restart', { job_id: expectedJobId, restored_state: restored.job_state });
  return report;
}

async function caseN12Restore(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  await ctx.control('stop-worker');
  ctx.track.workerStopped = true;
  const job = await beginJob(ctx);
  ctx.check('restore-job-id-visible', Boolean(ctx.track.jobId), true, ctx.track.jobId);
  const startBefore = await countNativeRequests(ctx, '/start', draft.draft_alias);
  ctx.event('start-count-before', startBefore);

  await sleep(35000);
  const pollObs = await ctx.client('snapshot');
  const serverWhilePolling = await ctx.layers(draft.alias, ctx.jobAliasesFor(draft.alias));
  ctx.event('background-poll-observation', {
    at_utc: pollObs.at_utc, error_text: pollObs.error_text, job_state: pollObs.job_state,
    visible_job_id: pollObs.visible_job_id, server_jobs: serverWhilePolling.jobs,
  });

  const bg = await ctx.client('background-wait');
  ctx.event('background-wait', bg);
  const resumed = await ctx.client('resume');
  ctx.check('background-same-job-id', !ctx.track.jobId || resumed.visible_job_id === ctx.track.jobId, ctx.track.jobId, resumed.visible_job_id);
  await ctx.client('snapshot');
  const backgroundScope = await ctx.layers(draft.alias, ctx.jobAliasesFor(draft.alias));
  ctx.check('background-one-job', (backgroundScope.jobs || []).length === 1, 1, (backgroundScope.jobs || []).length);
  const startAfterBackground = await countNativeRequests(ctx, '/start', draft.draft_alias);
  ctx.check('background-no-duplicate-start', startAfterBackground.count === startBefore.count, startBefore.count, startAfterBackground.count);

  await ctx.client('force-stop');
  const cold = await ctx.client('resume');
  ctx.check('cold-start-import-page', (cold.buttons || []).some(item => item.text.includes(RESTORE_BUTTON)), true, (cold.buttons || []).map(item => item.text));
  const restored = await ctx.client('restore');
  ctx.check('force-stop-same-job-id', !ctx.track.jobId || restored.visible_job_id === ctx.track.jobId, ctx.track.jobId, restored.visible_job_id);
  ctx.check('force-stop-job-state-visible', restored.job_state === job.state || !job.state, job.state, restored.job_state);
  const restoredScope = await ctx.layers(draft.alias, ctx.jobAliasesFor(draft.alias));
  ctx.check('restore-one-job', (restoredScope.jobs || []).length === 1, 1, (restoredScope.jobs || []).length);
  const startAfterRestore = await countNativeRequests(ctx, '/start', draft.draft_alias);
  ctx.check('restore-no-duplicate-start', startAfterRestore.count === startBefore.count, startBefore.count, startAfterRestore.count);

  const busyText = `${pollObs.error_text || ''} ${restored.error_text || ''}`;
  const busySeen = busyText.includes('BUSY_OR_INACTIVE');
  const recovered = Boolean(ctx.track.jobId) && restored.visible_job_id === ctx.track.jobId && !restored.error_text;
  ctx.event('busy_or_inactive', {
    observed: busySeen, text: busyText.trim(), first_observed_at_utc: pollObs.at_utc,
    server_state_at_observation: (serverWhilePolling.jobs || []).map(item => item.state),
    recovered_after_force_stop_restore: recovered,
    classification: busySeen ? (recovered ? 'EXECUTOR_OR_NATIVE_READ_RACE' : 'PRODUCT_GATE_PERMANENT_CANDIDATE') : 'NOT_OBSERVED',
    boundary: 'Single device/APK; force-stop is the process-death injection, not natural LMKD/OEM reclaim.',
  });
  ctx.check('busy-not-permanent', !busySeen || recovered, 'same job readable after restart', { busySeen, recovered });

  const beforeCancel = await ctx.layers(draft.alias, ctx.jobAliasesFor(draft.alias));
  await ctx.client('cancel');
  await ctx.waitJob(draft.alias, jobs => jobs.some(item => item.job_alias === job.job_alias && item.state === 'CANCELLED'), 'cancelled after restore', 120000);
  const afterCancel = await ctx.layers(draft.alias, ctx.jobAliasesFor(draft.alias));
  const beforeJob = layerJob(beforeCancel, job.job_alias);
  const afterJob = layerJob(afterCancel, job.job_alias);
  ctx.check('restore-cancel-revoked', afterJob && afterJob.execution_state === 'REVOKED', 'REVOKED', afterJob && afterJob.execution_state);
  ctx.check('restore-cancel-fence', afterJob && Number(afterJob.fence) > Number(beforeJob.fence), `>${beforeJob.fence}`, afterJob && afterJob.fence);
  await ctx.control('start-worker');
  ctx.track.workerStopped = false;
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 12000 });
  await deleteDraft(ctx);
}

async function caseN12OfflineRetry(ctx) {
  await prepareCase(ctx);
  const baseline = await freshDraft(ctx, { prepare: true });
  const first = await beginJob(ctx);
  await ctx.waitJob(baseline.alias, jobs => jobs.some(item => item.job_alias === first.job_alias && item.state === 'SUCCEEDED'), 'baseline SUCCEEDED', 300000);
  const baselineLayers = await ctx.layers(baseline.alias, ctx.jobAliasesFor(baseline.alias));
  const baselineJob = layerJob(baselineLayers, first.job_alias);
  const baselineReport = (baselineLayers.reports || []).find(item => item.job_alias === first.job_alias);
  ctx.check('baseline-report', baselineJob && baselineJob.has_report && Boolean(baselineReport), true, Boolean(baselineReport));
  const baselineHash = baselineReport && baselineReport.report_content_sha256;
  ctx.check('baseline-report-hash', Boolean(baselineHash), true, Boolean(baselineHash));
  const baselineUi = await readReportViaRestart(ctx, ctx.track.jobId);
  ctx.check('baseline-report-ui', baselineUi.report_visible === true, true, baselineUi.report_visible);
  ctx.event('baseline-ready', { alias: baseline.alias, job_alias: first.job_alias, report_sha256: baselineHash });

  const target = await freshDraft(ctx, { prepare: true });
  await ctx.control('stop-worker');
  ctx.track.workerStopped = true;
  const second = await beginJob(ctx);
  await ctx.waitJob(target.alias, jobs => jobs.some(item => item.job_alias === second.job_alias && item.state === 'QUEUED'), 'second QUEUED', 120000);
  const startCountBefore = await countNativeRequests(ctx, '/start', target.draft_alias);

  await ctx.client('net-block');
  ctx.track.offline = true;
  const offlineRead = await ctx.client('refresh');
  ctx.check('offline-read-shows-error', Boolean(offlineRead.error_text), 'visible error', offlineRead.error_text);
  const queuedAfterRead = await ctx.layers(target.alias, ctx.jobAliasesFor(target.alias));
  const queuedJobAfterRead = layerJob(queuedAfterRead, second.job_alias);
  ctx.check('offline-read-server-unchanged', queuedJobAfterRead && queuedJobAfterRead.state === 'QUEUED', 'QUEUED', queuedJobAfterRead && queuedJobAfterRead.state);
  ctx.event('offline-read', { ui_error: offlineRead.error_text, server_job: queuedJobAfterRead });

  const offlineCancel = await ctx.client('cancel-offline');
  ctx.check('offline-cancel-shows-error', Boolean(offlineCancel.error_text), 'visible error', offlineCancel.error_text);
  const queuedAfterCancel = await ctx.layers(target.alias, ctx.jobAliasesFor(target.alias));
  const queuedJobAfterCancel = layerJob(queuedAfterCancel, second.job_alias);
  ctx.check('offline-cancel-server-unchanged', queuedJobAfterCancel && queuedJobAfterCancel.state === 'QUEUED', 'QUEUED', queuedJobAfterCancel && queuedJobAfterCancel.state);
  ctx.event('offline-cancel', { ui_error: offlineCancel.error_text, server_job: queuedJobAfterCancel });

  await ctx.client('net-unblock');
  ctx.track.offline = false;
  await sleep(800);
  await ctx.client('refresh');
  await cancelJob(ctx, { jobAlias: second.job_alias });

  await ctx.client('net-block');
  ctx.track.offline = true;
  const offlineRetry = await ctx.client('retry-offline');
  ctx.check('offline-retry-shows-error', Boolean(offlineRetry.error_text), 'visible error', offlineRetry.error_text);
  const afterOfflineRetry = await ctx.layers(target.alias, ctx.jobAliasesFor(target.alias));
  ctx.check('offline-retry-no-new-job', (afterOfflineRetry.jobs || []).length === 1, 1, (afterOfflineRetry.jobs || []).length);
  ctx.event('offline-retry', { ui_error: offlineRetry.error_text, server_jobs: afterOfflineRetry.jobs });

  await ctx.client('net-unblock');
  ctx.track.offline = false;
  await sleep(800);
  await ctx.client('refresh');
  const retried = await retryJob(ctx, 2);
  ctx.check('retry-new-id', retried.job_alias !== second.job_alias, `!=${second.job_alias}`, retried.job_alias);
  ctx.check('retry-of-link', retried.retry_of_alias === second.job_alias, second.job_alias, retried.retry_of_alias);
  const oldAfterRetry = layerJob(await ctx.layers(target.alias, ctx.jobAliasesFor(target.alias)), second.job_alias);
  ctx.check('old-job-still-cancelled', oldAfterRetry && oldAfterRetry.state === 'CANCELLED', 'CANCELLED', oldAfterRetry && oldAfterRetry.state);
  const preservedLayers = await ctx.layers(baseline.alias, ctx.jobAliasesFor(baseline.alias));
  const preservedJob = layerJob(preservedLayers, first.job_alias);
  const preservedReport = (preservedLayers.reports || []).find(item => item.job_alias === first.job_alias);
  ctx.check('old-job-still-succeeded', preservedJob && preservedJob.state === 'SUCCEEDED', 'SUCCEEDED', preservedJob && preservedJob.state);
  ctx.check('old-report-still-readable', Boolean(preservedReport) && Boolean(preservedJob && preservedJob.has_report), true, Boolean(preservedReport));
  ctx.check('old-report-hash-preserved', preservedReport && preservedReport.report_content_sha256 === baselineHash, baselineHash, preservedReport && preservedReport.report_content_sha256);
  ctx.event('retry-created', { old_job_alias: second.job_alias, new_job_alias: retried.job_alias, old_report_sha256: preservedReport && preservedReport.report_content_sha256 });

  const targetLayersAfterRetry = await ctx.layers(target.alias, ctx.jobAliasesFor(target.alias));
  const startAfter = await countNativeRequests(ctx, '/start', target.draft_alias);
  // The device-side REJECT path does not reset the proxy log, so a new start
  // request would still appear; the retry must create a job without one.
  ctx.check('retry-no-new-start', startAfter.count === startCountBefore.count, startCountBefore.count, startAfter.count);
  ctx.check('retry-job-count', (targetLayersAfterRetry.jobs || []).length === 2, 2, (targetLayersAfterRetry.jobs || []).length);
  ctx.check('retry-runtime-inputs', (targetLayersAfterRetry.runtime_inputs || []).length === 2, 2, (targetLayersAfterRetry.runtime_inputs || []).length);
  ctx.check('retry-outbox-events', (targetLayersAfterRetry.outbox || []).length === 2, 2, (targetLayersAfterRetry.outbox || []).length);
  const retryCount = await countNativeRequests(ctx, '/retry', second.job_alias);
  ctx.event('retry-request-counts', {
    start_before: startCountBefore.count,
    start_after: startAfter.count,
    retry_requests: retryCount.count,
    offline_attempts_not_logged: true,
  });

  await cancelJob(ctx, { jobAlias: retried.job_alias });
  await ctx.control('start-worker');
  ctx.track.workerStopped = false;
  await waitNoResurrection(ctx, retried.job_alias, { milliseconds: 10000 });
  await deleteDraft(ctx, { alias: target.alias, jobAliases: ctx.jobAliasesFor(target.alias) });
  await dropDraftViaApi(ctx, baseline.alias);
}

async function caseF05Queued(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  await ctx.control('stop-worker');
  ctx.track.workerStopped = true;
  const job = await beginJob(ctx);
  await ctx.waitJob(draft.alias, jobs => jobs.some(item => item.job_alias === job.job_alias && item.state === 'QUEUED'), 'QUEUED', 120000);
  const result = await cancelJob(ctx, { jobAlias: job.job_alias });
  await ctx.control('start-worker');
  ctx.track.workerStopped = false;
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 15000 });
  const startCount = await countNativeRequests(ctx, '/start', draft.draft_alias);
  const cancelCount = await countNativeRequests(ctx, '/cancel', job.job_alias);
  ctx.event('queued-cancel-counts', { start: startCount.count, cancel: cancelCount.count, fence_before: result.before.fence, fence_after: result.after.fence });
  await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias] });
}

async function caseF05Scanning(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  await ctx.control('delay-scanner', ['--delay-seconds', '80']);
  ctx.track.scannerDelayed = true;
  const job = await beginJob(ctx);
  const active = await ctx.control('wait-scan');
  ctx.event('scan-running', { job_alias: job.job_alias, active_scanners: active.active_scanners, running: active.runner.filter(item => item.state === 'RUNNING') });
  const result = await cancelJob(ctx, { jobAlias: job.job_alias });
  await ctx.control('wait-runner-idle', ['--timeout', '120']);
  const ledger = await ctx.control('runner-ledger');
  ctx.event('scan-late-ledger', { done_operations: ledger.filter(item => item.state === 'DONE').length });
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 15000 });
  const state = (await ctx.scope(draft.alias)).jobs.find(item => item.job_alias === job.job_alias);
  ctx.check('scanning-cancelled-stays', state.state === 'CANCELLED', 'CANCELLED', state.state);
  ctx.event('scanning-cancel-result', { fence_before: result.before.fence, fence_after: result.after.fence });
  await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias] });
}

async function caseF05Precommit(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  // Keep the paused-worker window below the 60s execution lease: 80s would
  // expire the lease and turn the deliberately-late result into CANCELLED.
  await ctx.control('delay-scanner', ['--delay-seconds', '20']);
  ctx.track.scannerDelayed = true;
  const job = await beginJob(ctx);
  const active = await ctx.control('wait-scan');
  ctx.event('scan-running', { job_alias: job.job_alias, active_scanners: active.active_scanners });
  await ctx.control('pause-worker');
  ctx.track.workerPaused = true;
  const completed = await ctx.control('wait-result');
  ctx.check('precommit-real-result', completed.has_actual_scan_result === true, true, completed.has_actual_scan_result);
  const result = await cancelJob(ctx, { jobAlias: job.job_alias });
  await ctx.control('unpause-worker');
  ctx.track.workerPaused = false;
  const ledgerAfter = await ctx.control('runner-ledger');
  ctx.event('precommit-late-result', {
    completed_sha256: completed.completed_output_sha256,
    genuine_done_operations: ledgerAfter.filter(item => item.state === 'DONE' && item.has_result).length,
    revoke_fence: result.after.fence,
  });
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 15000 });
  const report = (await ctx.scope(draft.alias)).jobs.find(item => item.job_alias === job.job_alias);
  ctx.check('precommit-no-report', report.report_status >= 400, '>=400', report.report_status);
  await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias] });
}

async function caseF06Queued(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  await ctx.control('stop-worker');
  ctx.track.workerStopped = true;
  const job = await beginJob(ctx);
  await ctx.waitJob(draft.alias, jobs => jobs.some(item => item.job_alias === job.job_alias && item.state === 'QUEUED'), 'QUEUED', 120000);
  const before = await ctx.scope(draft.alias);
  ctx.event('queued-before-delete', { jobs: before.jobs });
  const deleted = await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias], restartApi: false });
  await ctx.control('start-worker');
  ctx.track.workerStopped = false;
  await ctx.control('wait-runner-idle', ['--timeout', '120']);
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 15000, deleted: true });
  const replay = await ctx.control('replay-deleted', ['--scope', draft.alias]);
  ctx.check('queued-late-delivery-no-revive', replay.all_rejected === true, true, replay.old_access);
  ctx.event('queued-late-delivery', { tombstone: deleted.layers.scope_row, old_access: replay.old_access });
}

async function caseF06Scanning(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  await ctx.control('delay-scanner', ['--delay-seconds', '80']);
  ctx.track.scannerDelayed = true;
  const job = await beginJob(ctx);
  const active = await ctx.control('wait-scan');
  ctx.event('scan-running', { job_alias: job.job_alias, active_scanners: active.active_scanners });
  const deleted = await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias] });
  await ctx.control('wait-runner-idle', ['--timeout', '120']);
  const ledger = await ctx.control('runner-ledger');
  ctx.event('scanning-delete-ledger', { done: ledger.filter(item => item.state === 'DONE').length });
  await sleep(30000);
  const persisted = await ctx.layers(draft.alias, [job.job_alias]);
  ctx.check('scanning-delete-persists', persisted.scope_row && persisted.scope_row.tombstone === true, true, persisted.scope_row && persisted.scope_row.tombstone);
  ctx.check('scanning-delete-no-report', (persisted.reports || []).length === 0, 0, (persisted.reports || []).length);
  const replay = await ctx.control('replay-deleted', ['--scope', draft.alias]);
  ctx.check('scanning-delete-old-access', replay.all_rejected === true, true, replay.old_access);
  ctx.event('scanning-delete-final', { deletion: deleted.layers.scope_row, replay: replay.old_access });
}

async function caseF06Precommit(ctx) {
  await prepareCase(ctx);
  const draft = await freshDraft(ctx, { prepare: true });
  // Keep the paused-worker window below the 60s execution lease.
  await ctx.control('delay-scanner', ['--delay-seconds', '20']);
  ctx.track.scannerDelayed = true;
  const job = await beginJob(ctx);
  const active = await ctx.control('wait-scan');
  ctx.event('scan-running', { job_alias: job.job_alias, active_scanners: active.active_scanners });
  await ctx.control('pause-worker');
  ctx.track.workerPaused = true;
  const completed = await ctx.control('wait-result');
  ctx.check('precommit-real-result', completed.has_actual_scan_result === true, true, completed.has_actual_scan_result);
  const before = await ctx.layers(draft.alias, [job.job_alias]);
  ctx.check('precommit-before-materials', (before.runtime_inputs || []).length === 1, 1, (before.runtime_inputs || []).length);
  const deleted = await deleteDraft(ctx, { alias: draft.alias, jobAliases: [job.job_alias] });
  await ctx.control('unpause-worker');
  ctx.track.workerPaused = false;
  const ledgerAfter = await ctx.control('runner-ledger');
  ctx.event('precommit-late-result', {
    completed_sha256: completed.completed_output_sha256,
    genuine_done_operations: ledgerAfter.filter(item => item.state === 'DONE' && item.has_result).length,
  });
  await waitNoResurrection(ctx, job.job_alias, { milliseconds: 15000, deleted: true });
  const replay = await ctx.control('replay-deleted', ['--scope', draft.alias]);
  ctx.check('precommit-old-access', replay.all_rejected === true, true, replay.old_access);
  const layers = await ctx.layers(draft.alias, [job.job_alias]);
  ctx.check('precommit-storage-layers', (layers.documents || []).length === 0 && (layers.runtime_inputs || []).length === 0 && (layers.runner_materials || []).length === 0, 'all zero', layers.counts);
  ctx.event('precommit-final', { deletion: deleted.layers.scope_row, layers: layers.counts });
}

const CASES = {
  'N12-offline-retry': caseN12OfflineRetry,
  'N12-restore': caseN12Restore,
  'F05-queued': caseF05Queued,
  'F05-scanning': caseF05Scanning,
  'F05-precommit': caseF05Precommit,
  'F06-queued': caseF06Queued,
  'F06-scanning': caseF06Scanning,
  'F06-precommit': caseF06Precommit,
};

function hashEvidence(dir) {
  const files = [];
  const walk = current => {
    for (const entry of fs.readdirSync(current, { withFileTypes: true })) {
      const full = path.join(current, entry.name);
      if (entry.isDirectory()) walk(full);
      else if (entry.isFile() && entry.name !== 'SHA256SUMS') {
        files.push({ path: path.relative(dir, full).replaceAll('\\', '/'), sha256: sha256File(full), bytes: fs.statSync(full).size });
      }
    }
  };
  walk(dir);
  return files;
}
function writeSums(dir) {
  const files = hashEvidence(dir);
  fs.writeFileSync(path.join(dir, 'SHA256SUMS'), files.map(item => `${item.sha256}  ${item.path}`).join('\n') + '\n', 'utf8');
  return files;
}

async function runCase(caseId, config) {
  const definition = MATRIX.cases.find(item => item.id === caseId);
  if (!definition || !CASES[caseId]) throw new Error(`unknown case ${caseId}`);
  const ctx = new Context(caseId, config);
  const started = now();
  let status = 'PASSED';
  let failure = null;
  try { await CASES[caseId](ctx); }
  catch (error) {
    failure = { message: error.message, classification: error.classification || 'PRODUCT_ASSERTION', at_utc: now() };
    status = ['IDENTITY', 'ENVIRONMENT'].includes(failure.classification) ? 'BLOCKED' : 'FAILED';
    ctx.event('case-failure', failure);
  }
  try { await ctx.cleanup(); }
  catch (error) {
    ctx.event('cleanup-failure', { message: error.message });
    if (status === 'PASSED') { status = 'FAILED'; failure = failure || { message: `cleanup failed: ${error.message}`, classification: 'DRIVER', at_utc: now() }; }
  }
  const ended = now();
  const files = writeSums(ctx.dir);
  const result = {
    case_id: caseId, title: definition.title, variants: definition.variants,
    status, variant_passed: status === 'PASSED', started_at: started, ended_at: ended,
    source_sha: config.sourceSha || TICKET_SOURCE,
    combination: {
      client_source_sha: config.sourceSha || TICKET_SOURCE,
      server_source_sha: config.serverSourceSha || null,
    },
    lab: { project: config.labProject || null, instance_id: config.instanceId || null, origin: config.origin, port: config.port, lab_state: config.labState },
    device: {
      serial: config.serial, adb: config.adb,
      client_apk_sha256: (ctx.identity?.client_installed?.paths || []).find(item => item.sha256)?.sha256 || null,
      fixture_apk_sha256: (ctx.identity?.installed?.paths || []).find(item => item.sha256)?.sha256 || null,
    },
    checks: ctx.checks, timeline: ctx.timeline, commands: ctx.commands,
    first_failure: failure, evidence: files,
    cleanup: ctx.timeline.filter(item => item.phase === 'cleanup').slice(-1)[0] || null,
    case_passed: false,
  };
  fs.writeFileSync(path.join(ctx.dir, 'result.json'), JSON.stringify(result, null, 2), 'utf8');
  return result;
}

function parseArgs(argv) {
  const args = {};
  for (let index = 2; index < argv.length; index += 1) {
    const item = argv[index];
    if (!item.startsWith('--')) continue;
    const key = item.slice(2);
    const value = argv[index + 1] && !argv[index + 1].startsWith('--') ? argv[++index] : true;
    args[key] = value;
  }
  return args;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.config) throw new Error('--config <lab.json> is required');
  const config = readJson(args.config);
  config.evidenceRoot = config.evidenceRoot || path.join(process.cwd(), '.scratch', 'issue133-evidence-20261022');
  if (args.list) { for (const item of MATRIX.cases) console.log(`${item.id}\t${item.title}`); return; }
  if (args.identity) {
    const context = new Context('identity', config);
    const identity = await ensureIdentity(context);
    console.log(JSON.stringify(identity, null, 2));
    return;
  }
  const requested = args.case ? String(args.case).split(',').map(item => item.trim()).filter(Boolean)
    : (args.all ? MATRIX.cases.map(item => item.id) : []);
  if (!requested.length) throw new Error('use --case <id[,id]> or --all');
  const results = [];
  for (const caseId of requested) {
    try {
      const result = await runCase(caseId, config);
      results.push(result);
      console.log(JSON.stringify({ case_id: caseId, status: result.status, checks: result.checks.length, first_failure: result.first_failure }));
    } catch (error) {
      results.push({ case_id: caseId, status: 'BLOCKED', error: error.message });
      console.log(JSON.stringify({ case_id: caseId, status: 'BLOCKED', error: error.message }));
    }
  }
  fs.writeFileSync(path.join(config.evidenceRoot, 'driver-summary.json'), JSON.stringify({ at_utc: now(), results }, null, 2), 'utf8');
}

main().catch(error => { console.error('DRIVER_FAILED', error.stack || error.message); process.exitCode = 1; });
