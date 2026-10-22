#!/usr/bin/env node
// Read back every lane E case result/hash, then write MANIFEST.md and index.json.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { spawnSync } = require('node:child_process');

const HERE = __dirname;
const evidenceRoot = process.argv[2] ? path.resolve(process.argv[2]) : path.resolve(process.cwd(), '.scratch', 'issue133-evidence-20261022');
const labConfig = JSON.parse(fs.readFileSync(path.join(evidenceRoot, 'lab.json'), 'utf8').replace(/^\uFEFF/, ''));
const sha256 = buffer => crypto.createHash('sha256').update(buffer).digest('hex');
const cases = fs.readdirSync(evidenceRoot, { withFileTypes: true })
  .filter(entry => entry.isDirectory() && !entry.name.startsWith('_'))
  .map(entry => entry.name)
  .filter(name => fs.existsSync(path.join(evidenceRoot, name, 'result.json')))
  .sort();

function lastJson(text) {
  const source = String(text || '');
  const candidates = [];
  let depth = 0, start = -1, inString = false, escaped = false;
  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
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
      if (depth === 0 && start >= 0) { candidates.push(source.slice(start, index + 1)); start = -1; }
    }
  }
  for (let index = candidates.length - 1; index >= 0; index -= 1) {
    try { return JSON.parse(candidates[index]); } catch { /* older object */ }
  }
  throw new Error(`no JSON in control output: ${source.slice(-300)}`);
}

function control(action, args = []) {
  const result = spawnSync('wsl.exe', [
    '-d', labConfig.wslDistro, '-u', 'root', '--', 'env',
    `PT133E_LAB_STATE=${labConfig.labState}`, `PT133E_CONTROLLER=${labConfig.controller}`,
    'bash', path.posix.join(labConfig.repoWsl, 'deploy/acceptance/issue133/control.sh'), action, ...args,
  ], { encoding: 'utf8', maxBuffer: 64 * 1024 * 1024, timeout: 600000 });
  if (result.status !== 0) throw new Error(`control ${action} failed: ${String(result.stderr).slice(-300)}`);
  const trimmed = String(result.stdout).trim();
  if (trimmed.startsWith('[')) return JSON.parse(trimmed);
  return lastJson(trimmed);
}

function verifyCase(caseId) {
  const dir = path.join(evidenceRoot, caseId);
  const result = JSON.parse(fs.readFileSync(path.join(dir, 'result.json'), 'utf8'));
  const issues = [];
  for (const item of result.evidence || []) {
    if (item.path === 'result.json') continue; // self-referential final write
    const candidate = path.resolve(dir, item.path);
    if (!candidate.startsWith(path.resolve(dir))) issues.push(`escape:${item.path}`);
    else if (sha256(fs.readFileSync(candidate)) !== item.sha256) issues.push(`hash:${item.path}`);
  }
  const sums = fs.readFileSync(path.join(dir, 'SHA256SUMS'), 'utf8').trim().split(/\r?\n/).filter(Boolean);
  if (sums.length !== (result.evidence || []).length) issues.push('sums-count');
  if (result.status !== 'PASSED') issues.push(`status:${result.status}`);
  if (result.checks.some(item => !item.pass)) issues.push('failed-check');
  return { caseId, result, issues };
}

function main() {
  const checked = cases.map(verifyCase);
  const observe = control('observe');
  const scopes = control('scope-list');
  const runner = control('runner-ledger');
  const net = spawnSync(labConfig.mumuManager, ['sh', '-v', String(labConfig.vmIndex), '-c', `iptables -L OUTPUT -n | grep 55483 || true`], { encoding: 'utf8' });
  fs.writeFileSync(path.join(evidenceRoot, 'observe-final.json'), JSON.stringify(observe, null, 2));
  fs.writeFileSync(path.join(evidenceRoot, 'scope-list-final.json'), JSON.stringify(scopes, null, 2));
  fs.writeFileSync(path.join(evidenceRoot, 'runner-ledger-final.json'), JSON.stringify(runner, null, 2));
  const liveScopes = (scopes.scopes || []).filter(item => !item.tombstone);
  const activeScanners = observe.active_scanners || [];
  const runningOperations = (runner || []).filter(item => item.state === 'RUNNING');
  const residualNetwork = String(net.stdout || '').trim();
  const allPassed = checked.every(item => item.issues.length === 0);
  const cleanupOk = liveScopes.length === 0 && activeScanners.length === 0 && runningOperations.length === 0 && !residualNetwork;
  const index = {
    format: 'privacytrace-issue133-canonical-20261022/1',
    generated_at_utc: new Date().toISOString(),
    source_sha: labConfig.sourceSha || '42088231db0817e385b64f7a0809e31010b3e81e',
    server_source_sha: labConfig.serverSourceSha || labConfig.sourceSha || null,
    lab: { project: labConfig.labProject, instance_id: labConfig.instanceId, origin: labConfig.origin, lab_state: labConfig.labState },
    device: { serial: labConfig.serial, client_apk_sha256: labConfig.expectedClientApkSha, fixture_apk_sha256: labConfig.expectedFixtureApkSha },
    cases: checked.map(({ caseId, result, issues }) => ({
      case_id: caseId,
      status: result.status,
      checks: result.checks.length,
      started_at: result.started_at,
      ended_at: result.ended_at,
      result_sha256: sha256(fs.readFileSync(path.join(evidenceRoot, caseId, 'result.json'))),
      evidence_files: (result.evidence || []).length,
      cleanup_notes: result.cleanup ? result.cleanup.notes : [],
      readback_issues: issues,
    })),
    final_readback: {
      live_scopes: liveScopes.length,
      active_scanners: activeScanners.length,
      running_runner_operations: runningOperations.length,
      residual_device_reject_rules: residualNetwork ? residualNetwork.split(/\r?\n/) : [],
      all_cases_passed: allPassed,
      cleanup_ok: cleanupOk,
    },
    canonical_case_count: checked.length,
  };
  fs.writeFileSync(path.join(evidenceRoot, 'index.json'), JSON.stringify(index, null, 2));
  const lines = [
    '# Issue #133 canonical evidence manifest',
    '',
    `Generated (UTC): ${index.generated_at_utc}`,
    '',
    `- Source: \`${index.source_sha}\``,
    `- Lab: \`${index.lab.project}\` / instance \`${index.lab.instance_id}\` / origin \`${index.lab.origin}\``,
    `- Device: \`${index.device.serial}\`; client APK \`${index.device.client_apk_sha256}\`; fixture APK \`${index.device.fixture_apk_sha256}\``,
    `- Final readback: live scopes=${liveScopes.length}, active scanners=${activeScanners.length}, running runner ops=${runningOperations.length}, residual device reject rules=${residualNetwork ? 'PRESENT' : 'none'}`,
    `- All canonical cases passed: ${allPassed}; cleanup OK: ${cleanupOk}`,
    '',
    '| Case | Status | Checks | Evidence files | Result SHA256 |',
    '| --- | --- | ---: | ---: | --- |',
  ];
  for (const item of index.cases) {
    lines.push(`| ${item.case_id} | ${item.status} | ${item.checks} | ${item.evidence_files} | \`${item.result_sha256}\` |`);
  }
  lines.push('', 'Each case directory contains its own `result.json`, `SHA256SUMS`, UTC timeline, client snapshots (txt/png), adb/device JSON, control observations and persistent-state readbacks. Raw capabilities and private report bodies remain only in the private lab root.');
  fs.writeFileSync(path.join(evidenceRoot, 'MANIFEST.md'), lines.join('\n') + '\n');
  console.log(JSON.stringify({ allPassed, cleanupOk, liveScopes: liveScopes.length, activeScanners: activeScanners.length, runningOperations: runningOperations.length, residualNetwork: Boolean(residualNetwork), issues: checked.flatMap(item => item.issues) }, null, 2));
}

main();
