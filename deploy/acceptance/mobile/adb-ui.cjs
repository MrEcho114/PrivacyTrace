const { execFileSync } = require('node:child_process');
const fs = require('node:fs');

const ADB = process.env.PT_ADB || 'adb';
const SERIAL = process.env.PT_ADB_SERIAL || '';

function run(args, options = {}) {
  const prefix = SERIAL ? ['-s', SERIAL] : [];
  return execFileSync(ADB, [...prefix, ...args], { encoding: 'utf8', ...options });
}

function sleep(ms) {
  Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, ms);
}

function dump() {
  let lastError;
  for (let attempt = 0; attempt < 8; attempt++) {
    // uiautomator exits 139 after writing the dump on this image; the file is
    // still complete, so the exit code is deliberately ignored. A crashed dump
    // can leave the previous file behind, so delete it first and never accept a
    // stale hierarchy as the current screen.
    const path = `/sdcard/pt73-ui-${process.pid}.xml`;
    try {
      run(['shell', 'rm', '-f', path]);
    } catch (error) {
      lastError = error;
    }
    try {
      run(['shell', 'uiautomator', 'dump', '--compressed', path]);
    } catch (error) {
      lastError = error;
    }
    for (let read = 0; read < 3; read++) {
      try {
        const xml = run(['exec-out', 'cat', path]);
        if (xml.includes('<hierarchy')) return parseXml(xml);
      } catch (error) {
        lastError = error;
      }
      sleep(250);
    }
    sleep(400);
  }
  throw new Error(`uiautomator dump failed: ${lastError && lastError.message}`);
}

function parseXml(xml) {
  const nodes = [];
  for (const match of xml.matchAll(/<node\b([^>]*?)\/?>/g)) {
    const attrs = {};
    for (const attr of match[1].matchAll(/([\w-]+)="([^"]*)"/g)) attrs[attr[1]] = attr[2];
    const bounds = (attrs.bounds || '').match(/\[(\d+),(\d+)\]\[(\d+),(\d+)\]/);
    if (!bounds) continue;
    nodes.push({
      text: attrs.text || '',
      hint: attrs.hint || '',
      cls: attrs.class || '',
      clickable: attrs.clickable === 'true',
      bounds: bounds.slice(1).map(Number),
      center: [
        Math.round((Number(bounds[1]) + Number(bounds[3])) / 2),
        Math.round((Number(bounds[2]) + Number(bounds[4])) / 2),
      ],
    });
  }
  return { xml, nodes };
}

function tap(x, y) {
  run(['shell', 'input', 'tap', String(x), String(y)]);
}

function tapText(text, { exact = false, timeoutMs = 30000 } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { nodes } = dump();
    const candidates = nodes.filter(node => (exact ? node.text === text : node.text.includes(text)));
    // Dialog titles can contain the button label; prefer the clickable node.
    const hit = candidates.find(node => node.clickable) || candidates[0];
    if (hit) {
      tap(...hit.center);
      return hit;
    }
    sleep(300);
  }
  throw new Error(`tapText timeout: ${text}`);
}

function editTexts() {
  const { nodes } = dump();
  return nodes.filter(node => node.cls.includes('EditText'));
}

function clearAndTypeAt(index, text) {
  const fields = editTexts();
  const field = fields[index];
  if (!field) throw new Error(`no EditText at index ${index} (found ${fields.length})`);
  tap(...field.center);
  sleep(600);
  run(['shell', 'input', 'keyevent', '123']);
  for (let i = 0; i < 90; i++) run(['shell', 'input', 'keyevent', '67']);
  run(['shell', 'input', 'text', text]);
  sleep(400);
  // The IME can swallow the first keystrokes right after the field appears;
  // confirm the field actually holds the value instead of trusting the tap.
  for (let attempt = 0; attempt < 3; attempt++) {
    const current = editTexts()[index];
    if (current && current.text.includes(text)) return;
    tap(...field.center);
    sleep(400);
    run(['shell', 'input', 'keyevent', '123']);
    for (let i = 0; i < 90; i++) run(['shell', 'input', 'keyevent', '67']);
    run(['shell', 'input', 'text', text]);
    sleep(400);
  }
  throw new Error(`failed to type into EditText ${index}: ${text}`);
}

function clearAndType(text) {
  clearAndTypeAt(0, text);
}

function waitText(text, { timeoutMs = 60000, absent = false } = {}) {
  const deadline = Date.now() + timeoutMs;
  while (Date.now() < deadline) {
    const { nodes } = dump();
    const found = nodes.some(node => node.text.includes(text));
    if (absent ? !found : found) return true;
    sleep(500);
  }
  throw new Error(`waitText timeout: ${text} absent=${absent}`);
}

function screencap(path) {
  const data = execFileSync(ADB, ['-s', SERIAL, 'exec-out', 'screencap', '-p']);
  fs.writeFileSync(path, data);
}

function openApp() {
  run(['shell', 'am', 'start', '-n', 'org.privacytrace.mobile/.MainActivity']);
}

function webviewSocket() {
  const out = run(['shell', 'cat', '/proc/net/unix']);
  const match = out.match(/@webview_devtools_remote_(\d+)/);
  if (!match) throw new Error('webview devtools socket not found');
  return { socket: `localabstract:webview_devtools_remote_${match[1]}`, pid: match[1] };
}

function forwardDevtools(port = 9222) {
  const { socket, pid } = webviewSocket();
  run(['forward', `tcp:${port}`, socket]);
  return pid;
}

function reverse(devicePort, hostPort = devicePort) {
  run(['reverse', `tcp:${devicePort}`, `tcp:${hostPort}`]);
}

module.exports = {
  run, sleep, dump, tap, tapText, editTexts, clearAndType, clearAndTypeAt,
  waitText, screencap, openApp, forwardDevtools, reverse, ADB, SERIAL,
};
