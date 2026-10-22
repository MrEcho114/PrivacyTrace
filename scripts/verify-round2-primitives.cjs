#!/usr/bin/env node
/**
 * Issue #142 round 2 — Android portrait Pioneer tokens and primitives.
 *
 * Static checks only. This verifies the contract values in
 * `.scratch/round2/lead/docs/design/frontend-round2-android-pioneer.md` §3
 * (tokens, UiSheet, UiIcon, pioneer-design.json, evidence files). It does not
 * replace the browser fixture screenshots or the TypeScript build.
 *
 * Run from the repository root: `node scripts/verify-round2-primitives.cjs`
 */
const fs = require('node:fs')
const path = require('node:path')

const root = path.resolve(__dirname, '..')
const read = (rel) => fs.readFileSync(path.join(root, rel), 'utf8')

const failures = []
const checks = []
function check(name, run) {
  try {
    run()
    checks.push(name)
  } catch (error) {
    failures.push(`${name}: ${error.message}`)
  }
}
function equal(actual, expected, label) {
  if (actual !== expected) throw new Error(`${label ?? 'value'} expected ${JSON.stringify(expected)}, got ${JSON.stringify(actual)}`)
}
function ok(condition, message) {
  if (!condition) throw new Error(message)
}
function deepEqual(actual, expected, label) {
  const a = JSON.stringify(actual)
  const e = JSON.stringify(expected)
  if (a !== e) throw new Error(`${label} expected ${e}, got ${a}`)
}

// ---------------------------------------------------------------- theme.css
const theme = read('apps/web/src/theme.css')
const rootBlock = theme.slice(theme.indexOf(':root {'), theme.indexOf('\n}', theme.indexOf(':root {')))
const tokens = new Map()
for (const match of rootBlock.matchAll(/--([a-z0-9-]+)\s*:\s*([^;]+);/g)) {
  tokens.set(match[1], match[2].replace(/\s+/g, ' ').trim())
}

// Existing round-1 variables must keep their names and values (no renaming).
const existingTokens = {
  canvas: '#f6f5f1', surface: '#fdfcfa', 'surface-muted': '#eeedea',
  ink: '#2c3547', muted: '#64696f', navy: '#333c50', border: '#d9d7d2',
  control: '#858d92', mint: '#dce9df', success: '#35644b', slate: '#dde2e9',
  notice: '#ede4d6', rose: '#ebdada', error: '#934342',
  'navy-hover': '#212a3b', danger: '#b25352', gold: '#c6af94',
  'on-action': '#f9f9f9', overlay: 'rgba(44, 53, 71, .3)',
  radius: '8px', 'radius-panel': '12px',
  'space-4': '4px', 'space-8': '8px', 'space-12': '12px',
  'space-16': '16px', 'space-24': '24px', 'space-32': '32px',
  'font-body': "'Noto Sans SC', 'Microsoft YaHei', system-ui, sans-serif",
  'font-display': "'Noto Serif SC', SimSun, serif",
  'font-code': "Consolas, 'Courier New', monospace",
}
check('theme.css keeps round-1 tokens', () => {
  for (const [name, value] of Object.entries(existingTokens)) equal(tokens.get(name), value, `--${name}`)
})

// Exact §3 Android portrait token block.
const mobileTokens = {
  'm-touch': '48px',
  'm-appbar-height': '56px',
  'm-actionbar-min-height': '64px',
  'm-gutter': '16px',
  'm-card-radius': '12px',
  'm-sheet-radius': '20px',
  'm-font-title': '1.25rem',
  'm-font-section': '1rem',
  'm-body': '0.875rem',
  'm-caption': '0.75rem',
  'm-line-body': '1.65',
  'm-state-hover': 'rgba(44, 53, 71, .06)',
  'm-state-press': 'rgba(44, 53, 71, .12)',
  'm-state-selected': 'rgba(51, 60, 80, .08)',
  'm-scrim': 'rgba(44, 53, 71, .42)',
  'm-shadow-bar': '0 1px 2px rgba(44, 53, 71, .08)',
  'm-shadow-sheet': '0 -8px 32px rgba(44, 53, 71, .18)',
}
check(`theme.css has the ${Object.keys(mobileTokens).length} §3 mobile tokens`, () => {
  for (const [name, value] of Object.entries(mobileTokens)) equal(tokens.get(name), value, `--${name}`)
})

check('theme.css links the round-2 contract plus Figma/Android sources', () => {
  for (const fragment of ['frontend-round2-android-pioneer.md §3', 'figma.com/design/EQis9ep9ZQsEenrUVXwlFU', 'developer.android.com']) {
    ok(theme.includes(fragment), `missing source reference: ${fragment}`)
  }
})

// ------------------------------------------------------- pioneer-design.json
const designRaw = read('scripts/fixtures/pioneer-design.json')
const design = JSON.parse(designRaw)
const expectedDesign = {
  roles: {
    canvas: '#f6f5f1', surface: '#fdfcfa', 'surface-muted': '#eeedea',
    ink: '#2c3547', muted: '#64696f', navy: '#333c50', border: '#d9d7d2',
    control: '#858d92', mint: '#dce9df', success: '#35644b', slate: '#dde2e9',
    notice: '#ede4d6', rose: '#ebdada', error: '#934342',
  },
  body: { fontFamily: 'Noto Sans SC', fontSize: '14px' },
  heading: { fontFamily: 'Noto Serif SC', fontSize: '28px', lineHeight: '40px' },
  mobileHeading: { fontSize: '24px', lineHeight: '34px' },
  button: { fontFamily: 'Noto Sans SC', fontSize: '14px', borderRadius: '8px', minHeight: '36px' },
  mobileButton: { maxWidth: 560, minHeight: 44 },
  field: { fontFamily: 'Noto Sans SC', fontSize: '14px', borderRadius: '8px', minHeight: '40px' },
}
check('pioneer-design.json keeps every existing key/value', () => {
  equal(design.source, 'docs/design/issue-44-provenance.md')
  for (const [key, value] of Object.entries(expectedDesign)) deepEqual(design[key], value, key)
})
check('pioneer-design.json mobile mirrors §3', () => {
  deepEqual(design.mobile, {
    touchTarget: 48, appBarHeight: 56, actionBarMinHeight: 64, inputFontSize: 16, sheetRadius: 20,
  }, 'mobile')
  deepEqual(Object.keys(design).sort(), ['body', 'button', 'field', 'heading', 'mobile', 'mobileButton', 'mobileHeading', 'roles', 'source'])
})

// ------------------------------------------------------------------ UiIcon
const icon = read('apps/web/src/components/UiIcon.vue')
check('UiIcon keeps the four round-1 names and adds six mobile icons', () => {
  for (const name of ['plus', 'report', 'file', 'arrow-right', 'back', 'close', 'settings', 'chevron-right', 'refresh', 'check']) {
    ok(icon.includes(`'${name}'`) || new RegExp(`\\b${name}\\s*:`).test(icon), `missing icon: ${name}`)
  }
})
check('UiIcon is 24px, 24 viewBox, currentColor, stroke 1.5, aria-hidden', () => {
  for (const fragment of ['width="24"', 'height="24"', 'viewBox="0 0 24 24"', 'stroke="currentColor"', 'stroke-width="1.5"', 'aria-hidden="true"', 'focusable="false"']) {
    ok(icon.includes(fragment), `missing: ${fragment}`)
  }
})

// ----------------------------------------------------------------- UiSheet
const sheet = read('apps/web/src/components/UiSheet.vue')
check('UiSheet is built on the Reka UI 2.11.0 Dialog family', () => {
  ok(/from 'reka-ui'/.test(sheet), 'does not import from reka-ui')
  for (const part of ['DialogRoot', 'DialogPortal', 'DialogOverlay', 'DialogContent', 'DialogTitle', 'DialogDescription', 'DialogClose']) {
    ok(sheet.includes(part), `missing Reka primitive: ${part}`)
  }
  ok(!sheet.includes('reka-ui/dist'), 'must consume the public package, not copied dist source')
  const deps = JSON.parse(read('apps/web/package.json')).dependencies
  equal(deps['reka-ui'], '2.11.0', 'reka-ui')
  deepEqual(Object.keys(deps).sort(), ['@tauri-apps/api', 'reka-ui', 'vue'])
})
check('UiSheet exposes title/description?/initialFocus? and emits close', () => {
  for (const prop of ['title', 'description', 'initialFocus']) ok(sheet.includes(prop), `missing prop: ${prop}`)
  ok(/defineEmits<\{\s*close:\s*\[\]\s*\}>/.test(sheet), 'missing close emit')
  ok(/@update:open[\s\S]*?emit\('close'\)/.test(sheet), 'close emit is not wired to the dialog state')
})
check('UiSheet has default and close slots', () => {
  ok(sheet.includes('<slot name="close">'), 'missing close slot')
  ok(sheet.includes('<slot />'), 'missing default slot')
})
check('UiSheet renders the contracted DOM classes', () => {
  for (const name of ['ui-sheet-overlay', 'ui-sheet-handle', 'ui-sheet-head', 'ui-sheet-body', 'ui-sheet-close']) {
    ok(sheet.includes(name), `missing class: ${name}`)
  }
  ok(/class="ui-sheet"/.test(sheet), 'missing class: ui-sheet')
})
check('UiSheet is a safe-area bottom sheet with contained scrolling', () => {
  ok(sheet.includes('max-height: min(88dvh, 720px)'), 'missing bottom-sheet max-height')
  ok(sheet.includes('overscroll-behavior: contain'), 'missing overscroll-behavior: contain')
  ok(sheet.includes('env(safe-area-inset-bottom'), 'missing safe-area bottom padding')
  ok(sheet.includes('env(safe-area-inset-top'), 'missing detail safe-area top padding')
  ok(sheet.includes('ui-sheet--detail'), 'missing detail variant')
})
check('no transition: all in the round-2 primitives', () => {
  for (const [name, source] of [['theme.css', theme], ['UiSheet.vue', sheet], ['UiIcon.vue', icon]]) {
    ok(!/transition\s*:\s*all/.test(source), `${name} uses transition: all`)
  }
})

// --------------------------------------------------------------------- docs
const docPath = 'docs/design/issue142-theme-and-primitives.md'
const doc = read(docPath)
check('design doc has the round-2 token/component section and honest limits', () => {
  ok(doc.includes('第二轮'), 'missing round-2 heading')
  for (const fragment of ['--m-touch', 'UiSheet', 'Reka UI 2.11.0', 'Android', 'Material 3', 'NOT_RUN', '390×844', '1440×900', 'Chromium']) {
    ok(doc.includes(fragment), `doc missing: ${fragment}`)
  }
})
check('round-2 evidence files exist', () => {
  for (const file of [
    'docs/design/issue142/evidence/ui-sheet-bottom-390.png',
    'docs/design/issue142/evidence/ui-sheet-bottom-1440.png',
    'docs/design/issue142/evidence/ui-sheet-detail-390.png',
    'docs/design/issue142/evidence/ui-sheet-metrics.json',
  ]) {
    ok(fs.existsSync(path.join(root, file)), `missing evidence: ${file}`)
  }
})

for (const name of checks) console.log(`ok ${name}`)
if (failures.length) {
  console.error(`\n${failures.length} round-2 primitive check(s) failed:`)
  for (const failure of failures) console.error(`FAIL ${failure}`)
  process.exit(1)
}
console.log(`\nround-2 primitives: ${checks.length}/${checks.length} checks passed`)
