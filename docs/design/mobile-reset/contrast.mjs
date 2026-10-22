#!/usr/bin/env node
/**
 * PrivacyTrace mobile token contract — WCAG 2.1 contrast audit.
 *
 * Reads ./mobile-design.tokens.json (same directory), recomputes every
 * contrast[] pair from its fg/bg values with the WCAG 2.1 relative-luminance
 * formula, and prints the table as JSON on stdout.
 *
 * Exit code:
 *   0 — contract is self-consistent: every stored ratio equals the computed
 *       ratio at two decimals, every stored pass equals the computed pass, and
 *       every fg/bg value is a declared token. WCAG failures are still reported
 *       in summary.failed / failures[], because a failing pair may legitimately
 *       be recorded in the contract pending a design decision.
 *   1 — JSON unreadable, malformed entry, undeclared color, or drift between
 *       the stored ratio/pass and the computed value.
 *
 * Offline by design: Node built-ins only, no network.
 * Run from the repository root:
 *   node docs/design/mobile-reset/contrast.mjs
 */
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { dirname, join } from 'node:path'

const here = dirname(fileURLToPath(import.meta.url))
const tokensPath = join(here, 'mobile-design.tokens.json')

function fail(message) {
  console.error(`contrast.mjs: ${message}`)
  process.exit(1)
}

let tokens
try {
  tokens = JSON.parse(readFileSync(tokensPath, 'utf8').replace(/^\uFEFF/, ''))
} catch (error) {
  fail(`cannot read ${tokensPath}: ${error.message}`)
}

function parseColor(input, label) {
  const value = String(input).trim().toLowerCase()
  const hex = value.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/)
  if (hex) {
    const digits = hex[1].length === 3
      ? hex[1].split('').map(character => character + character).join('')
      : hex[1]
    return {
      r: Number.parseInt(digits.slice(0, 2), 16),
      g: Number.parseInt(digits.slice(2, 4), 16),
      b: Number.parseInt(digits.slice(4, 6), 16),
      a: 1,
    }
  }
  const rgb = value.match(/^rgba?\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*,\s*([0-9.]+)(?:\s*,\s*([0-9.]+))?\s*\)$/)
  if (!rgb) fail(`${label}: unsupported color ${JSON.stringify(input)} (use #rgb, #rrggbb, rgb() or rgba())`)
  const r = Number(rgb[1])
  const g = Number(rgb[2])
  const b = Number(rgb[3])
  const a = rgb[4] === undefined ? 1 : Number(rgb[4])
  if ([r, g, b].some(part => !Number.isFinite(part) || part < 0 || part > 255) || !Number.isFinite(a) || a < 0 || a > 1) {
    fail(`${label}: invalid color ${JSON.stringify(input)}`)
  }
  return { r, g, b, a }
}

function composite(foreground, background) {
  return {
    r: foreground.r * foreground.a + background.r * (1 - foreground.a),
    g: foreground.g * foreground.a + background.g * (1 - foreground.a),
    b: foreground.b * foreground.a + background.b * (1 - foreground.a),
    a: 1,
  }
}

function channel(value) {
  const c = value / 255
  return c <= 0.04045 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4
}

function luminance({ r, g, b }) {
  return 0.2126 * channel(r) + 0.7152 * channel(g) + 0.0722 * channel(b)
}

function contrastRatio(foreground, background) {
  const first = luminance(foreground)
  const second = luminance(background)
  const lighter = Math.max(first, second)
  const darker = Math.min(first, second)
  return (lighter + 0.05) / (darker + 0.05)
}

const round2 = value => Math.round((value + Number.EPSILON) * 100) / 100

if (!tokens.colors || typeof tokens.colors !== 'object' || Array.isArray(tokens.colors)) {
  fail('tokens.colors must be an object of token name -> color value')
}
const declaredColors = new Map()
for (const [name, value] of Object.entries(tokens.colors)) {
  declaredColors.set(String(value).trim().toLowerCase(), name)
}
if (!Array.isArray(tokens.contrast) || tokens.contrast.length === 0) {
  fail('tokens.contrast must be a non-empty array')
}

const results = []
const failures = []
const mismatches = []

for (const [index, entry] of tokens.contrast.entries()) {
  const where = `contrast[${index}]`
  for (const key of ['fg', 'bg', 'ratio', 'min', 'pass', 'usage']) {
    if (!(key in entry)) fail(`${where}: missing ${key}`)
  }
  if (typeof entry.ratio !== 'number' || !Number.isFinite(entry.ratio)) fail(`${where}: ratio must be a finite number`)
  if (typeof entry.min !== 'number' || !Number.isFinite(entry.min) || entry.min <= 0 || entry.min > 21) fail(`${where}: min must be a number in (0, 21]`)
  if (typeof entry.pass !== 'boolean') fail(`${where}: pass must be a boolean`)

  const foreground = parseColor(entry.fg, `${where}.fg`)
  const background = parseColor(entry.bg, `${where}.bg`)
  if (background.a < 1) fail(`${where}: bg must be opaque; got ${entry.bg}`)
  const effectiveForeground = foreground.a < 1 ? composite(foreground, background) : foreground

  const exact = contrastRatio(effectiveForeground, background)
  const ratio = round2(exact)
  const pass = exact >= entry.min
  const ratioMatches = Math.abs(ratio - entry.ratio) < 1e-9
  const passMatches = pass === entry.pass
  const declared = declaredColors.has(String(entry.fg).trim().toLowerCase()) && declaredColors.has(String(entry.bg).trim().toLowerCase())

  const record = {
    fg: entry.fg,
    bg: entry.bg,
    ratio,
    min: entry.min,
    pass,
    usage: entry.usage,
    storedRatio: entry.ratio,
    ratioMatches,
    passMatches,
    declaredColors: declared,
  }
  results.push(record)
  if (!pass) failures.push(record)
  if (!ratioMatches || !passMatches || !declared) {
    mismatches.push({
      index,
      where,
      storedRatio: entry.ratio,
      computedRatio: ratio,
      storedPass: entry.pass,
      computedPass: pass,
      undeclaredColors: declared ? [] : [entry.fg, entry.bg].filter(value => !declaredColors.has(String(value).trim().toLowerCase())),
    })
  }
}

const output = {
  meta: {
    name: tokens.meta?.name ?? null,
    version: tokens.meta?.version ?? null,
    baseline: tokens.meta?.baseline ?? null,
    scope: tokens.meta?.scope ?? null,
    standard: 'WCAG 2.1 relative luminance',
    rounding: 2,
    tokensFile: 'docs/design/mobile-reset/mobile-design.tokens.json',
    generatedAt: new Date().toISOString(),
  },
  summary: {
    total: results.length,
    passed: results.length - failures.length,
    failed: failures.length,
    mismatches: mismatches.length,
  },
  results,
  failures,
  mismatchDetails: mismatches,
}

console.log(JSON.stringify(output, null, 2))
if (mismatches.length > 0) process.exitCode = 1
