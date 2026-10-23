// Read-only extractor: direct dependency versions from local lock files.
const fs = require('fs');
const path = require('path');

const root = process.argv[2] || '.';

function npmRow(lockPath, pkg) {
  try {
    const lock = JSON.parse(fs.readFileSync(lockPath, 'utf8'));
    const e = lock.packages && lock.packages['node_modules/' + pkg];
    return e ? { version: e.version, license: e.license || '(no license field)' } : null;
  } catch (err) {
    return { error: String(err.message) };
  }
}

function pipRows(lockPath) {
  const text = fs.readFileSync(lockPath, 'utf8');
  const rows = [];
  for (const block of text.split('[[package]]')) {
    const name = block.match(/^\s*name = "([^"]+)"/m);
    const ver = block.match(/^\s*version = "([^"]+)"/m);
    if (name && ver) rows.push({ name: name[1], version: ver[1] });
  }
  return rows;
}

function cargoRows(lockPath) {
  const text = fs.readFileSync(lockPath, 'utf8');
  const rows = [];
  for (const block of text.split('[[package]]')) {
    const name = block.match(/^\s*name = "([^"]+)"/m);
    const ver = block.match(/^\s*version = "([^"]+)"/m);
    if (name && ver) rows.push({ name: name[1], version: ver[1] });
  }
  return rows;
}

const out = {};

out.npmRoot = {};
for (const pkg of ['vue', 'vite', 'typescript', 'vue-tsc', '@vitejs/plugin-vue', 'reka-ui', '@tauri-apps/api', 'playwright']) {
  out.npmRoot[pkg] = npmRow(path.join(root, 'package-lock.json'), pkg);
}

out.npmMobile = {};
for (const pkg of ['@tauri-apps/cli']) {
  out.npmMobile[pkg] = npmRow(path.join(root, 'apps/mobile/package-lock.json'), pkg);
}

const wantPip = ['fastapi', 'pydantic', 'uvicorn', 'sqlalchemy', 'alembic', 'psycopg', 'psycopg-binary', 'androguard', 'celery', 'pytest', 'httpx', 'ruff'];
const pipAll = pipRows(path.join(root, 'apps/api/uv.lock'));
out.pip = pipAll.filter((r) => wantPip.includes(r.name));

const cargoAll = cargoRows(path.join(root, 'apps/mobile/src-tauri/Cargo.lock'));
out.cargo = cargoAll.filter((r) => ['tauri', 'tauri-build', 'tauri-plugin-package-probe'].includes(r.name));

console.log(JSON.stringify(out, null, 2));
