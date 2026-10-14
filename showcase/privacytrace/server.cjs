const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const types = { '.html': 'text/html; charset=utf-8', '.js': 'text/javascript; charset=utf-8', '.mjs': 'text/javascript; charset=utf-8', '.json': 'application/json; charset=utf-8', '.png': 'image/png', '.woff2': 'font/woff2', '.m4a': 'audio/mp4', '.mp4': 'video/mp4', '.txt': 'text/plain; charset=utf-8' };
function createServer({ root = __dirname, video } = {}) {
  return http.createServer((req, res) => {
    if (!['GET', 'HEAD'].includes(req.method)) { res.writeHead(405, { Allow: 'GET, HEAD' }).end(); return; }
    let relative;
    try { relative = decodeURIComponent(new URL(req.url, 'http://localhost').pathname).slice(1) || 'index.html'; } catch { res.writeHead(400).end(); return; }
    const base = path.resolve(root), candidate = path.resolve(base, relative);
    if (!candidate.startsWith(base + path.sep) || relative.includes('\\')) { res.writeHead(403).end(); return; }
    let file = candidate, allowedBase = fs.realpathSync(base), exactException = false;
    // Development uses the already licensed project fonts. Portable packages
    // contain their own copies at the same URLs, and never need this fallback.
    if (!fs.existsSync(file) && ['assets/fonts/NotoSansSC-Variable.woff2', 'assets/fonts/NotoSerifSC-Variable.woff2'].includes(relative)) {
      file = path.resolve(__dirname, '../../apps/web/public/fonts', relative.slice('assets/fonts/'.length));
      if (fs.existsSync(file)) allowedBase = fs.realpathSync(path.dirname(file));
    }
    if (relative === 'preview.mp4' && video) { file = path.resolve(video); exactException = true; }
    if (!fs.existsSync(file) || !fs.statSync(file).isFile()) { res.writeHead(404).end(); return; }
    file = fs.realpathSync(file);
    if (!exactException && !file.startsWith(allowedBase + path.sep)) { res.writeHead(403).end(); return; }
    const size = fs.statSync(file).size; const headers = { 'Content-Type': types[path.extname(file)] || 'application/octet-stream', 'Accept-Ranges': 'bytes', 'Cache-Control': 'no-store' };
    let start = 0, end = size - 1, status = 200;
    if (req.headers.range) {
      const match = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range);
      if (!match || (!match[1] && !match[2])) { res.writeHead(416, { 'Content-Range': `bytes */${size}` }).end(); return; }
      if (!match[1]) start = Math.max(0, size - Number(match[2]));
      else { start = Number(match[1]); if (match[2]) end = Math.min(end, Number(match[2])); }
      if (start > end || start >= size) { res.writeHead(416, { 'Content-Range': `bytes */${size}` }).end(); return; }
      status = 206; headers['Content-Range'] = `bytes ${start}-${end}/${size}`;
    }
    headers['Content-Length'] = end - start + 1; res.writeHead(status, headers);
    if (req.method === 'HEAD' || size === 0) res.end(); else { const stream = fs.createReadStream(file, { start, end }); stream.on('error', () => res.destroy()); stream.pipe(res); }
  });
}
module.exports = { createServer };
if (require.main === module) {
  const server = createServer({ video: process.env.FILM_VIDEO });
  server.listen(Number(process.env.PORT || 5375), '127.0.0.1', () => console.log(`PrivacyTrace film: http://127.0.0.1:${server.address().port}/`));
  server.on('error', error => { console.error(error.message); process.exitCode = 1; });
}
