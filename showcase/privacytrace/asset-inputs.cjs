const fs = require('node:fs');
const path = require('node:path');
function assertAssetTree(directory) {
  const stat = fs.lstatSync(directory);
  if (stat.isSymbolicLink() || !stat.isDirectory()) throw Error('Assets must be regular directories without links');
  for (const name of fs.readdirSync(directory)) {
    const file = path.join(directory, name), child = fs.lstatSync(file);
    if (child.isSymbolicLink()) throw Error('Assets must be regular files without links');
    if (child.isDirectory()) assertAssetTree(file);
    else if (!child.isFile()) throw Error('Assets must be regular files without links');
  }
}
module.exports = { assertAssetTree };
