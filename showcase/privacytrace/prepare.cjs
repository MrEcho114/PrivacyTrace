// Prepare a self-contained directory. Classic local scripts work from file://
// with Chromium actually offline; no service worker, CDN, fetch or web server.
const fs = require('node:fs');
const path = require('node:path');
const { assertAssetTree } = require('./asset-inputs.cjs');
const root = __dirname;
function prepare(destination = root) {
  fs.mkdirSync(destination, { recursive: true });
  assertAssetTree(path.join(root, 'assets'));
  const story = JSON.parse(fs.readFileSync(path.join(root, 'storyboard.json')));
  const sources = JSON.parse(fs.readFileSync(path.join(root, 'capture-provenance.json')));
  if (destination !== root) {
    for (const name of ['index.html', 'film.mjs', 'storyboard.json', 'copy-provenance.json', 'capture-provenance.json', 'audio-provenance.json', 'README.md', 'ASSETS.md', 'asset-inputs.cjs', 'server.cjs', 'paths.cjs', 'package.json', 'prepare.cjs', 'package.py', 'render.cjs', 'verify.cjs', 'verify-package.cjs', 'verify-server.cjs', 'verify-media.py', 'soundtrack.py', 'capture.cjs', 'capture_app.py'])
      if (fs.existsSync(path.join(root, name))) fs.copyFileSync(path.join(root, name), path.join(destination, name));
    fs.cpSync(path.join(root, 'assets'), path.join(destination, 'assets'), { recursive: true });
  }
  const fontRoot = path.join(destination, 'assets/fonts'); fs.mkdirSync(fontRoot, { recursive: true });
  for (const name of ['NotoSansSC-Variable.woff2', 'NotoSerifSC-Variable.woff2']) {
    const local = path.join(root, 'assets/fonts', name), project = path.resolve(root, '../../apps/web/public/fonts', name);
    const source = fs.existsSync(local) ? local : project;
    if (path.resolve(source) !== path.resolve(fontRoot, name)) fs.copyFileSync(source, path.join(fontRoot, name));
  }
  const licenseRoot = path.join(fontRoot, 'licenses'); fs.mkdirSync(licenseRoot, { recursive: true });
  for (const name of ['NotoSansSC-OFL.txt', 'NotoSerifSC-OFL.txt']) {
    const local = path.join(root, 'assets/fonts/licenses', name), project = path.resolve(root, '../../apps/web/public/fonts/licenses', name);
    if (path.resolve(fs.existsSync(local) ? local : project) !== path.resolve(licenseRoot, name)) fs.copyFileSync(fs.existsSync(local) ? local : project, path.join(licenseRoot, name));
  }
  fs.writeFileSync(path.join(destination, 'data.js'), 'window.filmData = ' + JSON.stringify({ story, sources }) + ';\n');
  return destination;
}
module.exports = { prepare };
if (require.main === module) console.log(prepare(process.argv[2] ? path.resolve(process.argv[2]) : root));
