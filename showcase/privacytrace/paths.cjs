const fs = require('node:fs');
const path = require('node:path');
const root = __dirname, repository = path.resolve(root, '../..');
const inRepository = fs.existsSync(path.join(repository, 'scripts/lib/process-control.cjs')) && fs.existsSync(path.join(repository, 'apps/web/package.json'));
const work = process.env.FILM_OUTPUT_DIR ? path.resolve(process.env.FILM_OUTPUT_DIR) : inRepository ? path.join(repository, 'tmp/issue45-film') : path.join(root, 'output');
module.exports = { root, work, inRepository };
