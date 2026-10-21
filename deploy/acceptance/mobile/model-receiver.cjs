// Controlled HTTPS Chat Completions receiver for the phone-model acceptance lane.
//
// It is deliberately not a general model gateway: it accepts one configured
// endpoint path, one one-time key, and a fixed assistant content file. The log
// is the external observation for key destination and input minimization, so it
// records the request body and a key fingerprint but never the key itself.
const https = require('node:https');
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');

const PORT = Number(process.env.PT_MODEL_PORT || 19544);
const KEY = process.env.PT_MODEL_KEY || '';
const CERT = process.env.PT_MODEL_CERT || '';
const KEY_FILE = process.env.PT_MODEL_KEY_FILE || '';
const RESPONSE_FILE = process.env.PT_MODEL_RESPONSE_FILE || '';
const LOG = process.env.PT_MODEL_LOG || path.join(__dirname, 'evidence', 'model-requests.jsonl');
const HOST = process.env.PT_MODEL_HOST || '127.0.0.1';

if (!KEY) throw new Error('PT_MODEL_KEY is required');
if (!CERT || !KEY_FILE) throw new Error('PT_MODEL_CERT and PT_MODEL_KEY_FILE are required');
if (!RESPONSE_FILE) throw new Error('PT_MODEL_RESPONSE_FILE is required');

const assistant = fs.readFileSync(RESPONSE_FILE, 'utf8').trim();
if (!assistant) throw new Error('model response file is empty');
fs.mkdirSync(path.dirname(LOG), { recursive: true });

function fingerprint(value) {
  return crypto.createHash('sha256').update(value).digest('hex').slice(0, 16);
}

function record(entry) {
  fs.appendFileSync(LOG, JSON.stringify(entry) + '\n', 'utf8');
}

function sendJson(res, status, payload) {
  const body = Buffer.from(JSON.stringify(payload), 'utf8');
  res.writeHead(status, {
    'Content-Type': 'application/json',
    'Content-Length': body.length,
    'Cache-Control': 'no-store',
  });
  res.end(body);
}

function handle(req, res) {
  const started = new Date().toISOString();
  if (req.method !== 'POST' || req.url !== '/v1/chat/completions') {
    record({ at: started, method: req.method, path: req.url, accepted: false, reason: 'PATH' });
    sendJson(res, 404, { error: 'not_found' });
    return;
  }
  const chunks = [];
  let size = 0;
  req.on('data', chunk => {
    size += chunk.length;
    if (size > 256 * 1024) {
      req.destroy();
      return;
    }
    chunks.push(chunk);
  });
  req.on('end', () => {
    const raw = Buffer.concat(chunks);
    const bodyText = raw.toString('utf8');
    let body = null;
    try { body = JSON.parse(bodyText); } catch { body = null; }
    const auth = req.headers.authorization || '';
    const bearer = auth.startsWith('Bearer ') ? auth.slice(7) : '';
    const keyOk = bearer.length > 0 && crypto.timingSafeEqual(
      Buffer.from(crypto.createHash('sha256').update(bearer).digest('hex')),
      Buffer.from(crypto.createHash('sha256').update(KEY).digest('hex')),
    );
    const messages = Array.isArray(body && body.messages) ? body.messages : [];
    const prompt = messages.length === 1 && messages[0] && messages[0].role === 'user'
      ? String(messages[0].content || '') : '';
    const entry = {
      at: started,
      method: req.method,
      path: req.url,
      accepted: keyOk,
      authorization_present: Boolean(auth),
      key_fingerprint: bearer ? fingerprint(bearer) : null,
      expected_key_fingerprint: fingerprint(KEY),
      body_bytes: raw.length,
      body_sha256: crypto.createHash('sha256').update(raw).digest('hex'),
      body: bodyText,
      prompt_chars: prompt.length,
      prompt_has_apk_magic: raw.includes(Buffer.from('PK\u0003\u0004', 'binary')),
      prompt_has_bearer: /Bearer\s+\S+/i.test(prompt),
      prompt_has_task_token: /(?:draft|capability|token)[=:\s]+[A-Za-z0-9_-]{16,}/i.test(prompt),
      model: body && body.model,
      stream: body && body.stream,
      max_tokens: body && body.max_tokens,
      message_count: messages.length,
    };
    record(entry);
    if (!keyOk) {
      sendJson(res, 401, { error: 'invalid_api_key' });
      return;
    }
    sendJson(res, 200, {
      id: 'chatcmpl-pt131-controlled',
      object: 'chat.completion',
      created: Math.floor(Date.now() / 1000),
      model: (body && body.model) || 'controlled-chat',
      choices: [{
        index: 0,
        message: { role: 'assistant', content: assistant },
        finish_reason: 'stop',
      }],
    });
  });
}

const server = https.createServer(
  { cert: fs.readFileSync(CERT), key: fs.readFileSync(KEY_FILE) },
  handle,
);
server.listen(PORT, HOST, () => {
  console.log(`MODEL_RECEIVER_READY ${HOST}:${PORT} key=${fingerprint(KEY)} log=${LOG}`);
});
