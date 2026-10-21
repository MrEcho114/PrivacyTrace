// Drive N01/N02 negative package-input variants on the real Android client.
const fs = require('node:fs');
const path = require('node:path');
const ui = require('./adb-ui.cjs');
const { connect } = require('./cdp.cjs');

const OUT = process.env.PT_EVIDENCE_DIR || '.';
const ORIGIN = process.env.PT_N_ORIGIN || 'https://localhost:29443';
const DEVICE_PORT = Number(process.env.PT_N_DEVICE_PORT || 29443);
const HOST_PORT = Number(process.env.PT_N_HOST_PORT || 28443);
const APP = 'org.privacytrace.probe.fixture';
const APP_LABEL = 'Controlled split fixture';
const MODE = process.argv[2] || 'n01a';

function log(message) {
  console.log(`[n] ${message}`);
}

async function main() {
  fs.mkdirSync(OUT, { recursive: true });
  ui.run(['shell', 'am', 'force-stop', 'org.privacytrace.mobile']);
  ui.run(['shell', 'pm', 'clear', 'org.privacytrace.mobile']);
  ui.reverse(DEVICE_PORT, HOST_PORT);
  ui.run(['shell', 'am', 'start', '-n', 'org.privacytrace.mobile/.MainActivity']);
  ui.sleep(9000);
  const pid = ui.forwardDevtools(9222);
  log(`webview pid=${pid}`);
  const cdp = await connect(9222);
  await cdp.clickText('选择应用并上传');
  ui.waitText('选择上传实例', { timeoutMs: 30000 });
  ui.clearAndType(ORIGIN);
  ui.tapText('检查并继续');
  ui.waitText('选择要读取的应用', { timeoutMs: 90000 });
  log('app list visible');

  if (MODE === 'n01a') {
    ui.tapText('取消', { exact: true });
    ui.sleep(1000);
    ui.waitText('选择应用并上传', { timeoutMs: 30000 });
    ui.screencap(path.join(OUT, 'n01a-after-cancel.png'));
    fs.writeFileSync(path.join(OUT, 'n01a-body.txt'), await cdp.bodyText(), 'utf8');
    log('cancelled before selecting an app');
  } else if (MODE === 'n01b') {
    ui.tapText(APP_LABEL);
    ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
    log('confirmation dialog visible');
    ui.run(['shell', 'input', 'keyevent', '4']);
    ui.sleep(1500);
    ui.screencap(path.join(OUT, 'n01b-after-back.png'));
    fs.writeFileSync(path.join(OUT, 'n01b-body.txt'), await cdp.bodyText(), 'utf8');
    // The client must be back on the material page, not on a progress page.
    ui.waitText('选择应用并上传', { timeoutMs: 30000 });
    log('cancelled at confirmation');
  } else if (MODE === 'n02') {
    ui.tapText(APP_LABEL);
    ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
    log('confirmation dialog visible; uninstalling target package');
    ui.run(['uninstall', APP]);
    ui.sleep(1200);
    ui.tapText('确认上传');
    ui.sleep(5000);
    ui.screencap(path.join(OUT, 'n02-after-confirm.png'));
    fs.writeFileSync(path.join(OUT, 'n02-body.txt'), await cdp.bodyText(), 'utf8');
    const { nodes } = ui.dump();
    fs.writeFileSync(path.join(OUT, 'n02-ui.txt'), JSON.stringify(nodes.map(n => n.text).filter(Boolean), null, 2), 'utf8');
    log('confirmed after uninstall; collected UI state');
  } else if (MODE === 'n01c') {
    ui.tapText('取消', { exact: true });
    ui.sleep(1000);
    await cdp.clickText('选择应用并上传');
    ui.waitText('选择上传实例', { timeoutMs: 30000 });
    ui.clearAndType(ORIGIN);
    ui.tapText('检查并继续');
    ui.waitText('选择要读取的应用', { timeoutMs: 90000 });
    ui.tapText('取消', { exact: true });
    ui.sleep(1000);
    await cdp.clickText('选择应用并上传');
    ui.waitText('选择上传实例', { timeoutMs: 30000 });
    fs.writeFileSync(path.join(OUT, 'n01c-body.txt'), await cdp.bodyText(), 'utf8');
    log('reselect after cancel works');
  } else if (MODE === 'n02v') {
    ui.tapText(APP_LABEL);
    ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
    log('confirmation dialog visible; installing version 2 over the selected v1');
    ui.run(['install', '-r', process.env.PT_N_BASE_V2]);
    ui.sleep(1500);
    ui.tapText('确认上传');
    ui.sleep(5000);
    ui.screencap(path.join(OUT, 'n02v-after-confirm.png'));
    fs.writeFileSync(path.join(OUT, 'n02v-body.txt'), await cdp.bodyText(), 'utf8');
    const { nodes } = ui.dump();
    fs.writeFileSync(path.join(OUT, 'n02v-ui.txt'), JSON.stringify(nodes.map(n => n.text).filter(Boolean), null, 2), 'utf8');
    log('confirmed after version change; collected UI state');
  } else if (MODE === 'n02u') {
    ui.tapText(APP_LABEL);
    ui.waitText('确认上传所选应用', { timeoutMs: 90000 });
    const pmOut = ui.run(['shell', 'pm', 'path', APP]);
    const apkPath = pmOut.split('\n').map(line => line.trim())
      .filter(line => line.startsWith('package:'))
      .map(line => line.slice('package:'.length))[0];
    log(`chmod 000 ${apkPath}`);
    ui.run(['shell', 'chmod', '000', apkPath]);
    ui.tapText('确认上传');
    ui.sleep(5000);
    ui.screencap(path.join(OUT, 'n02u-after-confirm.png'));
    fs.writeFileSync(path.join(OUT, 'n02u-body.txt'), await cdp.bodyText(), 'utf8');
    const { nodes } = ui.dump();
    fs.writeFileSync(path.join(OUT, 'n02u-ui.txt'), JSON.stringify(nodes.map(n => n.text).filter(Boolean), null, 2), 'utf8');
    ui.run(['shell', 'chmod', '644', apkPath]);
    log('confirmed while package file was unreadable; restored mode');
  } else {
    throw new Error(`unknown mode ${MODE}`);
  }

  await cdp.close();
}

main().catch(error => {
  console.error('N_CASE_FAILED', error.stack || error.message);
  process.exit(1);
});

