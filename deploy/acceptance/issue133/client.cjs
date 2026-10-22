// Lane E's actual-client driver. Shared H collectors are deliberately untouched.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { connect } = require('../mobile/cdp.cjs');
const ui = require('../mobile/adb-ui.cjs');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const expected = require('./fixture/expected.json');

const STATE_LABELS = {
  '等待处理': 'QUEUED',
  '核对材料': 'INTAKE',
  '静态扫描': 'STATIC_ANALYSIS',
  '装载政策': 'POLICY_PARSING',
  '规则对照': 'EVALUATING',
  '生成报告': 'REPORTING',
  '报告已生成': 'SUCCEEDED',
  '分析未完成': 'FAILED',
  '分析已取消': 'CANCELLED',
};

async function waitBody(cdp, predicate, description, budget = 120000) {
  const until = Date.now() + budget;
  let last = '';
  while (Date.now() < until) {
    last = await cdp.bodyText();
    if (predicate(last)) return last;
    await pause(250);
  }
  throw new Error(`UI_TIMEOUT:${description}:${String(last).slice(-200)}`);
}
async function click(cdp, text) {
  const until = Date.now() + 20000;
  while (Date.now() < until) {
    if (await cdp.evaluate(`(() => {
      const b = [...document.querySelectorAll('button')].find(b => (b.innerText || b.textContent || '').trim().includes(${JSON.stringify(text)}) && !b.disabled);
      if (!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;
    })()`)) return;
    await pause(150);
  }
  throw new Error(`BUTTON_UNAVAILABLE:${text}`);
}
async function clickExact(cdp, text) {
  const until = Date.now() + 20000;
  while (Date.now() < until) {
    if (await cdp.evaluate(`(() => {
      const b = [...document.querySelectorAll('button')].find(b => (b.innerText || '').trim() === ${JSON.stringify(text)} && !b.disabled);
      if (!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;
    })()`)) return;
    await pause(150);
  }
  throw new Error(`BUTTON_UNAVAILABLE_EXACT:${text}`);
}
async function originDialog(title, origin) {
  ui.waitText(title, { timeoutMs: 30000 });
  ui.clearAndType(origin);
  ui.tapText('检查并继续');
}
async function prepare(cdp, options) {
  const packageName = options.packageName || expected.package_name;
  const collection = { version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: {
    id: 'lane-e-policy', title: 'Lane E synthetic fixture policy', source_type: 'OFFICIAL_WEB_POLICY',
    text: expected.policy_quote, package_name: packageName, version: 'UNKNOWN', region: '', product: '',
  } }] };
  await cdp.evaluate(`document.querySelector('details.policy-assist').setAttribute('open','')`);
  await cdp.evaluate(`(() => { const e=document.querySelector('#collector-result'); e.value=${JSON.stringify(JSON.stringify(collection))}; e.dispatchEvent(new Event('input',{bubbles:true})); })()`);
  await pause(300);
  await click(cdp, '检查回填内容');
  await waitBody(cdp, b => b.includes('确认来源类型后补入当前材料'), 'policy-preview');
  await click(cdp, '确认并补入材料');
  await waitBody(cdp, b => b.includes('来源和未检查候选已补入'), 'policy-import');
  await click(cdp, '自动准备政策并继续');
  await waitBody(cdp, b => b.includes('保存候选并开始分析'), 'candidates');
  await click(cdp, 'Lane E synthetic fixture policy');
  await click(cdp, '添加候选');
  await cdp.evaluate(`(() => {
    const fields = [['#candidate-quote', ${JSON.stringify(expected.policy_quote)}, 'input'], ['#candidate-type', ${JSON.stringify(expected.data_type)}, 'change'], ['#candidate-subject','APP','change'], ['#candidate-action','ACCESS','change']];
    for(const [s,v,event] of fields) { const e=document.querySelector(s); if(!e) throw Error('CANDIDATE_FIELD'); e.value=v; e.dispatchEvent(new Event(event,{bubbles:true})); }
  })()`);
  await pause(300);
  await click(cdp, '保存候选');
  await waitBody(cdp, b => b.includes('候选声明 1'), 'candidate-saved');
}

function serial() {
  if (!process.env.PT_ADB_SERIAL) throw new Error('PT_ADB_SERIAL is required');
  return process.env.PT_ADB_SERIAL;
}
function mumuShell(options, command) {
  const manager = options.mumuManager;
  const index = options.vmIndex;
  if (!manager || index === undefined) throw new Error('MUMU_MANAGER_CONFIG_REQUIRED');
  return execFileSync(manager, ['sh', '-v', String(index), '-c', command], { encoding: 'utf8' });
}
function networkRule(options, action) {
  const port = String(options.port);
  const operation = action === 'net-block' ? '-A' : '-D';
  const rules = [
    `iptables ${operation} OUTPUT -p tcp -d 127.0.0.1 --dport ${port} -j REJECT`,
    `ip6tables ${operation} OUTPUT -p tcp -d ::1 --dport ${port} -j REJECT`,
  ];
  const commands = rules.map(command => {
    try { return { command, ok: true, output: mumuShell(options, command).trim() }; }
    catch (error) { return { command, ok: false, error: String(error.message || error).slice(-300) }; }
  });
  let readback = '';
  try { readback = mumuShell(options, `iptables -L OUTPUT -n | grep ${port} || true`); }
  catch (error) { readback = `readback failed: ${error.message}`; }
  return { action, at_utc: new Date().toISOString(), commands, readback: readback.trim().split(/\r?\n/).filter(Boolean) };
}
function tryRun(args) {
  try { return { ok: true, out: ui.run(args) }; }
  catch (error) { return { ok: false, out: String(error.message || error) }; }
}

async function snapshot(cdp, options, action) {
  const body = await cdp.bodyText();
  const prefix = path.join(options.output, `${options.runId}-${action}-${Date.now()}`);
  fs.writeFileSync(`${prefix}.txt`, body);
  await cdp.screenshot(`${prefix}.png`);
  try { ui.screencap(`${prefix}-device.png`); } catch { /* evidence remains from CDP */ }
  const details = await cdp.evaluate(`(() => {
    const out = {};
    const card = document.querySelector('.m-status-card .hash');
    out.status_hash = card ? (card.textContent || '').trim() : '';
    const idNode = [...document.querySelectorAll('dt')].find(n => (n.textContent || '').includes('材料标识'));
    out.draft_hash = idNode && idNode.nextElementSibling ? (idNode.nextElementSibling.textContent || '').trim() : '';
    const alert = document.querySelector('[role="alert"]');
    out.error_text = alert ? (alert.textContent || '').trim() : '';
    const statuses = [...document.querySelectorAll('[role="status"]')].map(n => (n.textContent || '').trim()).filter(Boolean);
    out.status_texts = statuses;
    out.notice = [...document.querySelectorAll('.m-notice')].map(n => (n.textContent || '').trim()).filter(Boolean);
    out.buttons = [...document.querySelectorAll('button')].map(n => ({ text: (n.innerText || '').trim(), disabled: !!n.disabled })).filter(n => n.text);
    return out;
  })()`);
  const ids = [...new Set(body.match(/\b[a-f0-9]{32}\b/g) || [])];
  const visibleJob = /^[a-f0-9]{32}$/.test(details.status_hash) ? details.status_hash : null;
  const visibleDraft = /^[a-f0-9]{32}$/.test(details.draft_hash) ? details.draft_hash : null;
  const stateLabel = (details.status_texts || []).map(text => Object.keys(STATE_LABELS).find(label => text.includes(label))).find(Boolean)
    || Object.keys(STATE_LABELS).find(label => body.includes(label)) || '';
  const result = {
    action,
    at_utc: new Date().toISOString(),
    body_sha256: crypto.createHash('sha256').update(body).digest('hex'),
    driver_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),
    visible_scope_ids: ids,
    visible_job_id: visibleJob,
    visible_draft_id: visibleDraft,
    state_label: stateLabel,
    job_state: STATE_LABELS[stateLabel] || null,
    error_text: details.error_text,
    status_texts: details.status_texts,
    notices: details.notice,
    buttons: details.buttons,
    shows_report_button: body.includes('查看报告'),
    report_visible: body.includes('隐私声明对照'),
    deleted_confirmation: body.includes('已确认删除') || body.includes('服务器已确认删除') || body.includes('访问已撤销'),
    shows_cancelled: body.includes('分析已取消'),
    shows_error: Boolean(details.error_text),
    evidence: path.basename(prefix),
    status: 'OBSERVED',
    case_passed: false,
  };
  fs.writeFileSync(`${prefix}.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  return result;
}

function deviceState() {
  const pid = tryRun(['shell', 'pidof', 'org.privacytrace.mobile']);
  const reverse = tryRun(['reverse', '--list']);
  const airplane = tryRun(['shell', 'settings', 'get', 'global', 'airplane_mode_on']);
  const wifi = tryRun(['shell', 'dumpsys', 'wifi']);
  const model = tryRun(['shell', 'getprop', 'ro.product.model']);
  const avd = tryRun(['emu', 'avd', 'name']);
  return {
    at_utc: new Date().toISOString(),
    serial: serial(),
    adb: ui.ADB,
    model: model.ok ? model.out.trim() : '',
    avd_name: avd.ok ? avd.out.trim() : null,
    avd_error: avd.ok ? null : avd.out,
    pid: pid.ok ? pid.out.trim() : null,
    reverse_list: reverse.ok ? reverse.out.split(/\r?\n/).filter(Boolean) : [],
    airplane_mode: airplane.ok ? airplane.out.trim() : null,
    wifi_summary: wifi.ok
      ? wifi.out.split(/\r?\n/).filter(line => /mWifiInfo|Wi-Fi is|WifiState|current SSID|NetworkInfo/.test(line)).slice(0, 8)
      : null,
  };
}

function installedIdentity(packageName) {
  const pm = tryRun(['shell', 'pm', 'path', packageName]);
  const paths = pm.ok ? pm.out.split(/\r?\n/).map(line => line.replace(/^package:/, '').trim()).filter(Boolean) : [];
  const hashes = paths.map(item => {
    try {
      const raw = execFileSync(ui.ADB, ['-s', serial(), 'exec-out', 'cat', item], { maxBuffer: 512 * 1024 * 1024 });
      return { path: item, sha256: crypto.createHash('sha256').update(raw).digest('hex'), bytes: raw.length };
    } catch (error) {
      return { path: item, error: String(error.message || error) };
    }
  });
  const packageDump = tryRun(['shell', 'dumpsys', 'package', packageName]);
  const lines = packageDump.ok
    ? packageDump.out.split(/\r?\n/).filter(line => /versionCode|versionName|firstInstallTime|lastUpdateTime/.test(line)).slice(0, 8)
    : [];
  return { package_name: packageName, paths: hashes, package_fields: lines };
}

async function connectUi(options) {
  const devtoolsDeadline = Date.now() + 45000;
  while (true) {
    try { ui.forwardDevtools(options.cdpPort); break; }
    catch (cause) { if (Date.now() >= devtoolsDeadline) throw cause; await pause(250); }
  }
  const cdp = await connect(options.cdpPort);
  // A cold WebView can expose the debugger before document.body exists.
  const rawBodyText = cdp.bodyText.bind(cdp);
  cdp.bodyText = async () => {
    try { return await rawBodyText(); }
    catch (error) {
      if (/Cannot read properties of null/.test(String(error.message || ''))) return '';
      throw error;
    }
  };
  return cdp;
}

async function resetApp(options) {
  ui.run(['shell', 'am', 'force-stop', 'org.privacytrace.mobile']);
  ui.run(['shell', 'pm', 'clear', 'org.privacytrace.mobile']);
  ui.openApp();
  const cdp = await connectUi(options);
  try {
    await waitBody(cdp, b => b.includes('选择应用并上传'), 'fresh client', 90000);
    return await snapshot(cdp, options, 'reset');
  } finally { await cdp.close(); }
}

async function main() {
  const [action, config] = process.argv.slice(2);
  if (!action || !config) throw new Error('Require action and config file');
  const options = JSON.parse(fs.readFileSync(config, 'utf8').replace(/^\uFEFF/, ''));
  if (!options.output || !/^[A-Za-z0-9_-]+$/.test(options.runId) || !Number.isInteger(options.cdpPort)) throw new Error('Invalid lane E config');
  if (options.serial && serial() !== options.serial) throw new Error('ADB_SERIAL_MISMATCH');
  fs.mkdirSync(options.output, {recursive: true});
  if (action === 'identity') {
    const fixture = options.packageName || 'org.privacytrace.probe.fixture';
    const result = {
      ...deviceState(),
      installed: installedIdentity(fixture),
      client_installed: installedIdentity(options.clientPackage || 'org.privacytrace.mobile'),
    };
    fs.writeFileSync(path.join(options.output, `${options.runId}-identity-${Date.now()}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    return;
  }
  if (action === 'device') { console.log(JSON.stringify(deviceState())); return; }
  if (action === 'reset') { await resetApp(options); return; }
  if (['net-block', 'net-unblock'].includes(action)) {
    const result = networkRule(options, action);
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-${Date.now()}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    return;
  }
  if (['radio-off', 'radio-on'].includes(action)) {
    const commands = action === 'radio-off'
      ? [['shell', 'svc', 'wifi', 'disable'], ['shell', 'svc', 'data', 'disable'], ['shell', 'cmd', 'connectivity', 'airplane-mode', 'enable']]
      : [['shell', 'svc', 'wifi', 'enable'], ['shell', 'svc', 'data', 'enable'], ['shell', 'cmd', 'connectivity', 'airplane-mode', 'disable']];
    const results = commands.map(argv => ({ argv: argv.join(' '), ...tryRun(argv) }));
    await pause(1500);
    const state = deviceState();
    const result = { action, at_utc: new Date().toISOString(), commands: results, device: state };
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-${Date.now()}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    return;
  }
  if (['offline', 'online', 'offline-full', 'online-full'].includes(action)) {
    const full = action.endsWith('-full');
    const goingOffline = action.startsWith('offline');
    const results = [];
    if (goingOffline) {
      results.push({ argv: `adb reverse --remove tcp:${options.port}`, ...tryRun(['reverse', '--remove', `tcp:${options.port}`]) });
      if (full) {
        for (const argv of [['shell', 'svc', 'wifi', 'disable'], ['shell', 'svc', 'data', 'disable'], ['shell', 'cmd', 'connectivity', 'airplane-mode', 'enable']]) {
          results.push({ argv: argv.join(' '), ...tryRun(argv) });
        }
      }
    } else {
      results.push({ argv: `adb reverse tcp:${options.port} tcp:${options.port}`, ...tryRun(['reverse', `tcp:${options.port}`, `tcp:${options.port}`]) });
      if (full) {
        for (const argv of [['shell', 'svc', 'wifi', 'enable'], ['shell', 'svc', 'data', 'enable'], ['shell', 'cmd', 'connectivity', 'airplane-mode', 'disable']]) {
          results.push({ argv: argv.join(' '), ...tryRun(argv) });
        }
      }
    }
    await pause(800);
    const result = { action, at_utc: new Date().toISOString(), effective: goingOffline ? 'adb-reverse-removed' : 'adb-reverse-restored', commands: results, device: deviceState() };
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-${Date.now()}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    return;
  }
  if (['background-wait', 'abandon'].includes(action)) {
    const before = tryRun(['shell', 'pidof', 'org.privacytrace.mobile']);
    ui.run(['shell', 'input', 'keyevent', 'KEYCODE_HOME']);
    let after = null;
    if (action === 'abandon') {
      ui.run(['shell', 'am', 'force-stop', 'org.privacytrace.mobile']);
    } else {
      await pause((options.backgroundSeconds || 35) * 1000);
    }
    after = tryRun(['shell', 'pidof', 'org.privacytrace.mobile']);
    const result = {
      action, at_utc: new Date().toISOString(),
      pid_before: before.ok ? before.out.trim() : null,
      pid_after: after.ok ? after.out.trim() : null,
      process_alive: after.ok,
      background_seconds: action === 'background-wait' ? (options.backgroundSeconds || 35) : null,
      device: deviceState(),
    };
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-${Date.now()}.json`), JSON.stringify(result, null, 2));
    console.log(JSON.stringify(result));
    return;
  }
  if (action === 'resume') {
    ui.openApp();
    await pause(1500);
    const cdp = await connectUi(options);
    try {
      await waitBody(cdp, b => b.includes('选择应用并上传') || b.includes('分析进度') || b.includes('隐私声明对照') || b.includes('政策来源'), 'resume-page', 90000);
      await snapshot(cdp, options, action);
    } finally { await cdp.close(); }
    return;
  }
  if (['reclaim', 'force-stop'].includes(action)) {
    const before = ui.run(['shell','pidof','org.privacytrace.mobile']).trim();
    if (!/^\d+$/.test(before)) throw new Error('SINGLE_OWNED_APP_PID_REQUIRED');
    ui.run(['shell','input','keyevent','KEYCODE_HOME']);
    if (action === 'reclaim') {
      // Target only this debug app's UID/PID. This reproduces process death,
      // without setting force-stop's stopped-package flag or touching other apps.
      ui.run(['shell','run-as','org.privacytrace.mobile','kill','-9',before]);
    }
    if (action === 'force-stop') ui.run(['shell','am','force-stop','org.privacytrace.mobile']);
    await pause(1500);
    const after = tryRun(['shell','pidof','org.privacytrace.mobile']);
    const result = {at_utc:new Date().toISOString(),action,pid_before:before,pid_after:after.ok?after.out.trim():null,process_changed:!after.ok||after.out.trim()!==before,injection:action==='reclaim'?'DEBUG_APP_UID_SIGKILL':action,device:deviceState()};
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-process-${Date.now()}.json`), JSON.stringify(result, null, 2));
    if (after.ok && after.out.trim() === before) throw new Error('PROCESS_NOT_REPLACED');
    console.log(JSON.stringify(result));
    return;
  }
  const cdp = await connectUi(options);
  try {
    if (['upload','upload-pending'].includes(action)) {
      await click(cdp, '选择应用并上传'); await originDialog('选择上传实例', options.origin);
      ui.waitText('选择要读取的应用', {timeoutMs:60000}); ui.tapText(options.appLabel || 'Controlled split fixture');
      ui.waitText('确认上传所选应用', {timeoutMs:60000}); ui.tapText('确认上传');
      if (action === 'upload-pending') {
        ui.waitText('正在传输完整包集合',{timeoutMs:30000});
        ui.screencap(path.join(options.output, `${options.runId}-upload-pending-${Date.now()}-native.png`));
      } else await waitBody(cdp, b=>b.includes('政策来源') && !b.includes('正在处理当前请求'), 'upload-confirmed', 300000);
    } else if (action === 'stop-upload' || action === 'stop-request') {
      const label = action === 'stop-upload' ? '停止当前操作' : '停止本次请求';
      const clicked = await cdp.evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').includes(${JSON.stringify(label)})); if(!b) return false; b.click(); return true; })()`);
      if (!clicked) ui.tapText(label);
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'request-cancelled',120000);
    } else if (action === 'restore') {
      await click(cdp, '恢复当前实例材料'); await originDialog('刷新上传确认', options.origin);
      await waitBody(cdp, b=>b.includes('分析进度') && !b.includes('正在处理当前请求'), 'restored', 180000);
    } else if (action === 'restore-any') {
      await click(cdp, '恢复当前实例材料'); await originDialog('刷新上传确认', options.origin);
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'restored-any', 180000);
    } else if (action === 'restore-pending') {
      await click(cdp, '恢复当前实例材料'); await originDialog('刷新上传确认', options.origin);
      await waitBody(cdp,b=>!b.includes('正在处理当前请求') && b.includes('服务器尚未确认完整上传'),'incomplete-restore',120000);
    } else if (action === 'prepare') await prepare(cdp, options);
    else if (action === 'begin') { await click(cdp,'保存候选并开始分析'); await waitBody(cdp,b=>b.includes('分析进度'),'job-started'); }
    else if (action === 'cancel') { await click(cdp,'取消分析'); await waitBody(cdp,b=>b.includes('分析已取消') || b.includes('访问已撤销'),'cancel-confirmed',120000); }
    else if (['cancel-offline','retry-offline'].includes(action)) {
      await click(cdp,action==='cancel-offline'?'取消分析':'重试为新的分析');
      // The busy banner and the alert render on separate frames; wait for a
      // visible alert after the request has settled instead of sampling early.
      await pause(1200);
      const deadline = Date.now() + 30000;
      let alertText = '';
      while (Date.now() < deadline) {
        const body = await cdp.bodyText();
        alertText = await cdp.evaluate(`document.querySelector('[role="alert"]')?.textContent?.trim() || ''`);
        if (alertText && !body.includes('正在处理当前请求')) break;
        await pause(300);
      }
      if (!alertText) throw new Error('OFFLINE_FAILURE_NOT_VISIBLE');
    }
    else if (action === 'retry') { await click(cdp,'重试为新的分析'); await waitBody(cdp,b=>b.includes('分析进度'),'retry-returned',120000); }
    else if (action === 'refresh') {
      await click(cdp,'刷新进度');
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'refresh-complete',120000);
    }
    else if (action === 'expect-error') {
      await waitBody(cdp, b => {
        const alert = b.includes('错误') || b.includes('失败') || b.includes('无法') || b.includes('暂时') || b.includes('未完成');
        return alert && !b.includes('正在处理当前请求');
      }, 'visible-error', 120000);
    }
    else if (action === 'wait-terminal') {
      await waitBody(cdp, b => b.includes('查看报告') || b.includes('分析已取消') || b.includes('分析未完成'), 'terminal-state', 420000);
    }
    else if (action === 'report') { await waitBody(cdp,b=>b.includes('查看报告'),'job-succeeded',600000); await click(cdp,'查看报告'); await waitBody(cdp,b=>b.includes('隐私声明对照'),'report',120000); }
    else if (action === 'delete') {
      let found = await cdp.evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim().includes('删除远端材料') && !x.disabled); if(!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true; })()`);
      if (!found) {
        await cdp.evaluate(`(() => { const b=document.querySelector('button[aria-label="服务与存储设置"]'); if(b){b.click(); return true;} return false; })()`);
        await pause(800);
        found = await cdp.evaluate(`(() => { const b=[...document.querySelectorAll('button')].find(x=>(x.innerText||'').trim().includes('删除远端材料') && !x.disabled); if(!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true; })()`);
      }
      if (!found) throw new Error('DELETE_BUTTON_UNAVAILABLE');
      await originDialog('删除远端材料', options.origin);
      ui.waitText('主动删除远端材料',{timeoutMs:60000}); ui.tapText('确认删除');
      await waitBody(cdp,b=>b.includes('服务器已确认删除') || b.includes('已确认删除') || b.includes('访问已撤销'),'deleted',120000);
    } else if (action === 'watch') await pause(35000);
    else if (!['snapshot','background','reclaim','force-stop'].includes(action)) throw new Error('UNKNOWN_ACTION');
    const observed = await snapshot(cdp,options,action);
    if (action === 'watch' && observed.shows_error) throw new Error('POLLING_STOPPED_WITH_VISIBLE_ERROR');
  } finally { await cdp.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode=1; });
