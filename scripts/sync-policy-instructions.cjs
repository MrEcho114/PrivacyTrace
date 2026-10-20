// Packaging mirror only: #79 remains the canonical instruction source.
const fs = require('node:fs')
const path = require('node:path')
const root = path.resolve(__dirname, '..')
const source = path.join(root, 'skills/privacytrace-policy-collector/COPY.txt')
const target = path.join(root, 'apps/web/src/policyCollector.generated.ts')
const canonical = fs.readFileSync(source, 'utf8').replaceAll('\r\n', '\n')
const generated = '// Generated from skills/privacytrace-policy-collector/COPY.txt; do not edit.\nexport default ' + JSON.stringify(canonical) + '\n'
if (process.argv.includes('--check')) {
  if (!fs.existsSync(target) || fs.readFileSync(target, 'utf8').replaceAll('\r\n', '\n') !== generated) {
    console.error('Policy instruction resource drifted; run node scripts/sync-policy-instructions.cjs.')
    process.exitCode = 1
  }
} else fs.writeFileSync(target, generated, 'utf8')
