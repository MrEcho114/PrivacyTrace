// Minimal CDP client for an Android WebView. Node 24 provides global fetch/WebSocket.
async function connect(port = 9222) {
  const response = await fetch(`http://127.0.0.1:${port}/json`);
  const targets = await response.json();
  const page = targets.find(t => t.type === 'page');
  if (!page) throw new Error('no page target');
  const socket = new WebSocket(page.webSocketDebuggerUrl);
  await new Promise((resolve, reject) => {
    socket.onopen = resolve;
    socket.onerror = error => reject(new Error('websocket error'));
  });
  let sequence = 0;
  const pending = new Map();
  socket.onmessage = event => {
    const message = JSON.parse(event.data);
    if (message.id && pending.has(message.id)) {
      const { resolve, reject } = pending.get(message.id);
      pending.delete(message.id);
      if (message.error) reject(new Error(`${message.error.code}: ${message.error.message}`));
      else resolve(message.result);
    }
  };
  function send(method, params = {}) {
    const id = ++sequence;
    return new Promise((resolve, reject) => {
      pending.set(id, { resolve, reject });
      socket.send(JSON.stringify({ id, method, params }));
    });
  }
  async function evaluate(expression) {
    const result = await send('Runtime.evaluate', {
      expression,
      awaitPromise: true,
      returnByValue: true,
      userGesture: true,
    });
    if (result.exceptionDetails) {
      throw new Error(result.exceptionDetails.exception?.description || result.exceptionDetails.text);
    }
    return result.result?.value;
  }
  async function clickText(text, selector = 'button, a, summary, [role="button"], label, input') {
    const clicked = await evaluate(`(() => {
      const nodes = [...document.querySelectorAll(${JSON.stringify(selector)})];
      const target = nodes.find(node => (node.innerText || node.textContent || node.value || '').trim().includes(${JSON.stringify(text)}));
      if (!target) return false;
      target.scrollIntoView({block: 'center'});
      target.click();
      return true;
    })()`);
    if (!clicked) throw new Error(`text not found: ${text}`);
  }
  async function bodyText() {
    return evaluate('document.body.innerText');
  }
  async function waitText(text, timeoutMs = 60000) {
    const deadline = Date.now() + timeoutMs;
    while (Date.now() < deadline) {
      const body = await bodyText();
      if (body.includes(text)) return body;
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    throw new Error(`timeout waiting for ${text}`);
  }
  async function screenshot(path) {
    const result = await send('Page.captureScreenshot', { format: 'png' });
    require('node:fs').writeFileSync(path, Buffer.from(result.data, 'base64'));
  }
  return { page, send, evaluate, clickText, bodyText, waitText, screenshot, close: () => socket.close() };
}

module.exports = { connect };
