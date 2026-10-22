// Lane E's actual-client driver. Shared H collectors are deliberately untouched.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const { connect } = require('../mobile/cdp.cjs');
const ui = require('../mobile/adb-ui.cjs');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const expected = require('./fixture/expected.json');

async function waitBody(cdp, predicate, description, budget = 120000) {
  const until = Date.now() + budget;
  while (Date.now() < until) {
    if (predicate(await cdp.bodyText())) return;
    await pause(250);
  }
  throw new Error(`UI_TIMEOUT:${description}`);
}
async function click(cdp, text) {
  const until = Date.now() + 20000;
  while (Date.now() < until) {
    if (await cdp.evaluate(`(() => {
      const b = [...document.querySelectorAll('button')].find(b => b.innerText.trim() === ${JSON.stringify(text)} && !b.disabled);
      if (!b) return false; b.scrollIntoView({block:'center'}); b.click(); return true;
    })()`)) return;
    await pause(150);
  }
  throw new Error(`BUTTON_UNAVAILABLE:${text}`);
}
async function originDialog(title, origin) {
  ui.waitText(title, { timeoutMs: 30000 });
  ui.clearAndType(origin);
  ui.tapText('检查并继续');
}
async function prepare(cdp) {
  const collection = { version: 'privacytrace-policy-collector/1', results: [{ state: 'PROVIDED', source: {
    id: 'lane-e-policy', title: 'Lane E synthetic fixture policy', source_type: 'OFFICIAL_WEB_POLICY',
    text: expected.policy_quote, package_name: expected.package_name, version: 'UNKNOWN', region: '', product: '',
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
async function snapshot(cdp, options, action) {
  const body = await cdp.bodyText();
  const prefix = path.join(options.output, `${options.runId}-${action}-${Date.now()}`);
  fs.writeFileSync(`${prefix}.txt`, body);
  await cdp.screenshot(`${prefix}.png`);
  const result = { action, at_utc: new Date().toISOString(), body_sha256: crypto.createHash('sha256').update(body).digest('hex'),
    driver_sha256: crypto.createHash('sha256').update(fs.readFileSync(__filename)).digest('hex'),
    visible_scope_ids: [...new Set(body.match(/\b[a-f0-9]{32}\b/g) || [])],
    shows_report_button: body.includes('查看报告'), shows_cancelled: body.includes('分析已取消'),
    shows_error: !!await cdp.evaluate(`document.querySelector('[role="alert"]')?.textContent?.trim()`),
    evidence: path.basename(prefix), status: 'OBSERVED', case_passed: false };
  fs.writeFileSync(`${prefix}.json`, JSON.stringify(result, null, 2));
  console.log(JSON.stringify(result));
  return result;
}
async function main() {
  const [action, config] = process.argv.slice(2);
  if (!action || !config || !process.env.PT_ADB_SERIAL) throw new Error('Require action, config file and explicit PT_ADB_SERIAL');
  const options = JSON.parse(fs.readFileSync(config, 'utf8'));
  if (!options.output || !/^[A-Za-z0-9-]+$/.test(options.runId) || !Number.isInteger(options.cdpPort)) throw new Error('Invalid lane E config');
  // Destructive lifecycle actions may target only the explicitly named owned AVD.
  if (ui.run(['emu', 'avd', 'name']).split(/\r?\n/)[0].trim() !== options.avdName || options.avdName !== 'privacytrace-issue133-e') throw new Error('OWNED_AVD_REQUIRED');
  fs.mkdirSync(options.output, {recursive:true});
  if (action === 'offline') { ui.run(['reverse','--remove',`tcp:${options.port}`]); console.log('lane E transport disconnected'); return; }
  if (action === 'online') { ui.reverse(options.port); console.log('lane E transport reconnected'); return; }
  if (['background','reclaim','force-stop'].includes(action)) {
    const before = ui.run(['shell','pidof','org.privacytrace.mobile']).trim();
    if (!/^\d+$/.test(before)) throw new Error('SINGLE_OWNED_APP_PID_REQUIRED');
    ui.run(['shell','input','keyevent','KEYCODE_HOME']);
    if (action === 'reclaim') {
      // Target only this debug app's UID/PID. This reproduces process death,
      // without setting force-stop's stopped-package flag or touching other apps.
      ui.run(['shell','run-as','org.privacytrace.mobile','kill','-9',before]);
    }
    if (action === 'force-stop') ui.run(['shell','am','force-stop','org.privacytrace.mobile']);
    await pause(1000); ui.openApp(); await pause(1500);
    const after = ui.run(['shell','pidof','org.privacytrace.mobile']).trim();
    if (action !== 'background' && after === before) throw new Error('PROCESS_NOT_REPLACED');
    fs.writeFileSync(path.join(options.output, `${options.runId}-${action}-process-${Date.now()}.json`), JSON.stringify({at_utc:new Date().toISOString(),action,process_changed:after!==before,injection:action==='reclaim'?'DEBUG_APP_UID_SIGKILL':action}));
  }
  // A cold WebView can expose its socket after the activity has already started.
  const devtoolsDeadline = Date.now() + 30000;
  while (true) {
    try { ui.forwardDevtools(options.cdpPort); break; }
    catch (cause) { if (Date.now() >= devtoolsDeadline) throw cause; await pause(250); }
  }
  const cdp = await connect(options.cdpPort);
  try {
    if (['upload','upload-pending'].includes(action)) {
      await click(cdp, '选择应用并上传'); await originDialog('选择上传实例', options.origin);
      ui.waitText('选择要读取的应用', {timeoutMs:60000}); ui.tapText('Issue 133 controlled fixture');
      ui.waitText('确认上传所选应用', {timeoutMs:60000}); ui.tapText('确认上传');
      if (action === 'upload-pending') {
        ui.waitText('正在传输完整包集合',{timeoutMs:30000});
        ui.screencap(path.join(options.output, `${options.runId}-upload-pending-${Date.now()}-native.png`));
      } else await waitBody(cdp, b=>b.includes('政策来源') && !b.includes('正在处理当前请求'), 'upload-confirmed');
    } else if (action === 'stop-upload') {
      ui.tapText('停止当前操作');
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'upload-cancelled');
    } else if (['restore','restore-pending','restore-offline'].includes(action)) {
      await click(cdp, '恢复当前实例材料'); await originDialog('刷新上传确认', options.origin);
      if (action === 'restore') await waitBody(cdp, b=>b.includes('分析进度') && !b.includes('正在处理当前请求'), 'restored');
      else await waitBody(cdp,b=>!b.includes('正在处理当前请求') && b.includes(action==='restore-pending'?'服务器尚未确认完整上传':'SERVER_'),'incomplete-restore');
    } else if (action === 'prepare') await prepare(cdp);
    else if (action === 'begin') { await click(cdp,'保存候选并开始分析'); await waitBody(cdp,b=>b.includes('分析进度'),'job-started'); }
    else if (action === 'cancel') { await click(cdp,'取消分析'); await waitBody(cdp,b=>b.includes('分析已取消') || b.includes('访问已撤销'),'cancel-confirmed'); }
    else if (['cancel-offline','retry-offline'].includes(action)) {
      await click(cdp,action==='cancel-offline'?'取消分析':'重试为新的分析');
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'offline-control-complete');
      if (!await cdp.evaluate(`document.querySelector('[role="alert"]')?.textContent?.trim()`)) throw new Error('OFFLINE_FAILURE_NOT_VISIBLE');
    }
    else if (action === 'retry') { await click(cdp,'重试为新的分析'); await waitBody(cdp,b=>b.includes('分析进度'),'retry-returned'); }
    else if (action === 'refresh') {
      await click(cdp,'刷新进度');
      await waitBody(cdp,b=>!b.includes('正在处理当前请求'),'refresh-complete');
    }
    else if (action === 'report') { await waitBody(cdp,b=>b.includes('查看报告'),'job-succeeded'); await click(cdp,'查看报告'); await waitBody(cdp,b=>b.includes('隐私声明对照'),'report'); }
    else if (action === 'delete') {
      await click(cdp,'删除远端材料'); await originDialog('删除远端材料',options.origin);
      ui.waitText('主动删除远端材料',{timeoutMs:60000}); ui.tapText('确认删除');
      await waitBody(cdp,b=>b.includes('服务器已确认删除') || b.includes('访问已撤销'),'deleted');
    } else if (action === 'watch') await pause(35000);
    else if (!['snapshot','background','reclaim','force-stop'].includes(action)) throw new Error('UNKNOWN_ACTION');
    const observed = await snapshot(cdp,options,action);
    if (action === 'watch' && observed.shows_error) throw new Error('POLLING_STOPPED_WITH_VISIBLE_ERROR');
  } finally { await cdp.close(); }
}
main().catch(error => { console.error(error.message); process.exitCode=1; });
