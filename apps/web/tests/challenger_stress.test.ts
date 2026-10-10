import test from 'node:test'
import assert from 'node:assert'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { parseSource, serializeSource, type ReportSource } from '../src/types.ts'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const srcDir = path.resolve(__dirname, '../src')
const rootDir = path.resolve(__dirname, '..')

// ---------------------------------------------------------------------------
// 1. Static Security & DOM Injection Analysis
// ---------------------------------------------------------------------------
test('R2 Security: Zero v-html and Zero innerHTML across entire web source', () => {
  const files = fs.readdirSync(srcDir, { recursive: true }) as string[]
  for (const file of files) {
    const fullPath = path.join(srcDir, file)
    if (fs.statSync(fullPath).isFile() && (file.endsWith('.vue') || file.endsWith('.ts') || file.endsWith('.js'))) {
      const content = fs.readFileSync(fullPath, 'utf-8')
      assert(!content.includes('v-html'), `Disallowed v-html found in ${file}`)
      assert(!content.includes('innerHTML'), `Disallowed innerHTML found in ${file}`)
      assert(!content.includes('outerHTML'), `Disallowed outerHTML found in ${file}`)
      assert(!content.includes('document.write'), `Disallowed document.write found in ${file}`)
    }
  }
})

test('R2 Security: Strict CSP meta tag configured in index.html', () => {
  const indexPath = path.join(rootDir, 'index.html')
  const html = fs.readFileSync(indexPath, 'utf-8')
  assert(html.includes('http-equiv="Content-Security-Policy"'), 'CSP meta tag must exist in index.html')
  assert(html.includes("default-src 'self'"), "CSP must enforce default-src 'self'")
  assert(html.includes("script-src 'self'"), "CSP must enforce script-src 'self'")
  assert(!html.includes("'unsafe-eval'"), "CSP must NOT allow 'unsafe-eval'")
})

// ---------------------------------------------------------------------------
// 2. sentenceContext Pure Logic & Boundary Analysis
// ---------------------------------------------------------------------------
// Replicates exact implementation from App.vue:94-105 for pure algorithmic verification
function sentenceContext(
  text: string | undefined,
  start_offset: number | null | undefined,
  end_offset: number | null | undefined
) {
  if (!text || start_offset == null || end_offset == null) return null
  const points = Array.from(text)
  const start = Math.max(0, start_offset)
  const end = Math.max(start, Math.min(points.length, end_offset))
  return {
    before: points.slice(Math.max(0, start - 100), start).join(''),
    sentence: points.slice(start, end).join(''),
    after: points.slice(end, Math.min(points.length, end + 100)).join(''),
  }
}

test('R1 Boundary: sentenceContext handles negative offsets safely', () => {
  const text = '这是测试政策文本的一段内容。'
  const res = sentenceContext(text, -5, -2)
  assert.notStrictEqual(res, null)
  assert.strictEqual(res!.sentence, '')
  assert.strictEqual(res!.before, '')
  assert(res!.after.startsWith('这是测试政策'))
})

test('R1 Boundary: sentenceContext handles inverted offsets safely (start > end)', () => {
  const text = 'abcdefghijklmnopqrstuvwxyz'
  const res = sentenceContext(text, 10, 5)
  assert.notStrictEqual(res, null)
  // end is clamped to start (10), so sentence is empty
  assert.strictEqual(res!.sentence, '')
  assert.strictEqual(res!.before, 'abcdefghij')
  assert.strictEqual(res!.after, 'klmnopqrstuvwxyz')
})

test('R1 Boundary: sentenceContext handles massive out-of-bounds offsets', () => {
  const text = 'Hello world'
  const res = sentenceContext(text, 50000, 60000)
  assert.notStrictEqual(res, null)
  assert.strictEqual(res!.sentence, '')
  assert.strictEqual(res!.before, '')
  assert.strictEqual(res!.after, '')
})

test('R1 Boundary: sentenceContext handles astral plane Unicode surrogate pairs correctly', () => {
  // Emojis: 👩‍💻 (surrogate pairs + ZWJ), 🎉, 𠮷 (rare CJK surrogate pair)
  const text = '前缀文本🎉位置信息𠮷后缀文本'
  const points = Array.from(text)

  // Verify points array contains exact codepoints rather than split UTF-16 code units
  assert.strictEqual(points[4], '🎉')
  assert.strictEqual(points[9], '𠮷')

  // Target the 🎉 emoji at index 4..5
  const resEmoji = sentenceContext(text, 4, 5)
  assert.notStrictEqual(resEmoji, null)
  assert.strictEqual(resEmoji!.sentence, '🎉')
  assert.strictEqual(resEmoji!.before, '前缀文本')
  assert.strictEqual(resEmoji!.after, '位置信息𠮷后缀文本')

  // Target rare CJK surrogate pair 𠮷 at index 9..10
  const resCjk = sentenceContext(text, 9, 10)
  assert.notStrictEqual(resCjk, null)
  assert.strictEqual(resCjk!.sentence, '𠮷')
  assert.strictEqual(resCjk!.before, '前缀文本🎉位置信息')
  assert.strictEqual(resCjk!.after, '后缀文本')
})

// ---------------------------------------------------------------------------
// 3. Source Classification & Timestamp Edge Cases
// ---------------------------------------------------------------------------
// Replicates the App.vue sourceInfo rule: provenance is read from the explicit
// backend `source_origin` field. sample_id naming is never consulted.
type Origin = 'SYNTHETIC' | 'CONTROLLED' | 'OFFLINE_REPLAY' | 'REAL_SCAN'

function getSourceInfo(report: { demo: boolean; job?: { sample_id?: string; source_origin?: string } } | null) {
  if (!report) return null
  const origin: string | undefined = report.demo ? 'SYNTHETIC' : report.job?.source_origin
  if (!origin) return { type: 'UNKNOWN', badge: '来源未标注', label: '来源未标注' }
  const labels: Record<string, { badge: string; label: string }> = {
    SYNTHETIC: { badge: '人工示例 · SYNTHETIC', label: 'SYNTHETIC · 人工构造示例' },
    CONTROLLED: { badge: '受控评测 · CONTROLLED', label: 'CONTROLLED · 受控测试输入' },
    OFFLINE_REPLAY: { badge: '离线回放 · OFFLINE_REPLAY', label: 'OFFLINE_REPLAY · 真实 APK 静态报告' },
    REAL_SCAN: { badge: '本机扫描 · REAL_SCAN', label: 'REAL_SCAN · 本机真实 APK 静态扫描' },
  }
  const known = labels[origin]
  if (!known) return { type: origin, badge: `未识别来源 · ${origin}`, label: `未识别来源 · ${origin}` }
  return { type: origin, ...known }
}

test('R4 Source classification: demo envelope is always SYNTHETIC', () => {
  assert.strictEqual(getSourceInfo({ demo: true, job: { id: 'demo' } })?.type, 'SYNTHETIC')
  assert.strictEqual(getSourceInfo({ demo: true, job: { sample_id: 'com.example.real', source_origin: 'REAL_SCAN' } })?.type, 'SYNTHETIC')
})

test('R4 Source classification follows source_origin, not sample_id naming', () => {
  // A real scan whose sample_id looks controlled must stay REAL_SCAN.
  const realJobNamedControlled = { demo: false, job: { id: 'a', sample_id: 'CONTROLLED-LOOKALIKE', source_origin: 'REAL_SCAN' } }
  assert.strictEqual(getSourceInfo(realJobNamedControlled)?.type, 'REAL_SCAN')

  // A controlled fixture whose sample_id is literally "demo" must stay CONTROLLED.
  const controlledJobNamedDemo = { demo: false, job: { id: 'b', sample_id: 'demo', source_origin: 'CONTROLLED' } }
  assert.strictEqual(getSourceInfo(controlledJobNamedDemo)?.type, 'CONTROLLED')

  // A plain offline replay is classified from the field alone.
  const replay = { demo: false, job: { id: 'c', sample_id: 'gkd-s1-first', source_origin: 'OFFLINE_REPLAY' } }
  assert.strictEqual(getSourceInfo(replay)?.type, 'OFFLINE_REPLAY')
})

test('R4 Source classification: missing or unknown origin is never silently mislabelled', () => {
  // No origin recorded: report it as unannotated instead of assuming a replay.
  assert.strictEqual(getSourceInfo({ demo: false, job: { sample_id: 'CONTROLLED-1' } })?.type, 'UNKNOWN')
  assert.strictEqual(getSourceInfo({ demo: false, job: {} })?.type, 'UNKNOWN')
  // An unrecognised origin surfaces verbatim rather than degrading to a real-APK label.
  const unknown = getSourceInfo({ demo: false, job: { sample_id: 'x', source_origin: 'MADE_UP' } })
  assert.strictEqual(unknown?.type, 'MADE_UP')
  assert(unknown!.badge.includes('未识别来源'))
})

test('R4 Every known origin maps to a distinct badge', () => {
  const origins: Origin[] = ['SYNTHETIC', 'CONTROLLED', 'OFFLINE_REPLAY', 'REAL_SCAN']
  const badges = origins.map(o => getSourceInfo({ demo: false, job: { source_origin: o } })?.badge)
  assert.strictEqual(new Set(badges).size, origins.length, 'Each origin needs a unique badge')
})

// Replicates exact implementation from App.vue:118-126
function formatTimestamp(ts?: string) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return isNaN(d.getTime()) ? ts : d.toLocaleString('zh-CN', { hour12: false })
  } catch {
    return ts
  }
}

test('R4 Edge Case: Non-standard timestamp formats in created_at', () => {
  // 1. Standard ISO with microsecond
  const isoMicro = '2026-10-03T12:48:35.211974Z'
  const resMicro = formatTimestamp(isoMicro)
  assert(resMicro.includes('2026'), 'Standard ISO should format')

  // 2. Non-standard space format
  const spaceFormat = '2026-10-10 01:33:43'
  const resSpace = formatTimestamp(spaceFormat)
  assert(resSpace.includes('2026'), 'Space format should be parsed or returned safely')

  // 3. Corrupted / invalid timestamp string should fall back gracefully without throwing
  const corrupt = 'corrupt-timestamp-string'
  assert.strictEqual(formatTimestamp(corrupt), corrupt)

  // 4. Empty and undefined
  assert.strictEqual(formatTimestamp(''), '')
  assert.strictEqual(formatTimestamp(undefined), '')
})

// ---------------------------------------------------------------------------
// 4. Candidate Clauses Pagination Mathematics
// ---------------------------------------------------------------------------
test('R1 Boundary: Candidate pagination counts for 0, 1, 20, 21, 2000 claims', () => {
  const PAGE_SIZE = 20

  const calculatePages = (total: number) => Math.ceil(total / PAGE_SIZE)
  const getSlice = (items: number[], page: number) => items.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE)

  // 0 claims (empty state)
  const items0: number[] = []
  assert.strictEqual(calculatePages(items0.length), 0)
  assert.strictEqual(getSlice(items0, 0).length, 0)

  // 1 claim
  const items1 = [1]
  assert.strictEqual(calculatePages(items1.length), 1)
  assert.strictEqual(getSlice(items1, 0).length, 1)

  // 20 claims (single page boundary)
  const items20 = Array.from({ length: 20 }, (_, i) => i)
  assert.strictEqual(calculatePages(items20.length), 1)
  assert.strictEqual(getSlice(items20, 0).length, 20)

  // 21 claims (boundary crossing into page 2)
  const items21 = Array.from({ length: 21 }, (_, i) => i)
  assert.strictEqual(calculatePages(items21.length), 2)
  assert.strictEqual(getSlice(items21, 0).length, 20)
  assert.strictEqual(getSlice(items21, 1).length, 1)

  // 2,000 claims (100 pages)
  const items2000 = Array.from({ length: 2000 }, (_, i) => i)
  assert.strictEqual(calculatePages(items2000.length), 100)
  assert.strictEqual(getSlice(items2000, 0).length, 20)
  assert.strictEqual(getSlice(items2000, 99).length, 20)
})

// ---------------------------------------------------------------------------
// 5. Structured Error Parsing for activeJob
// ---------------------------------------------------------------------------
// Replicates exact implementation from App.vue:162-180
function parseJobError(rawError: string | null | undefined) {
  if (!rawError) return null
  try {
    const obj = JSON.parse(rawError)
    if (typeof obj === 'object' && obj !== null) {
      return {
        code: String(obj.code || obj.error_code || 'ERROR'),
        message: String(obj.message || obj.detail || rawError),
        primary_error: obj.primary_error ? String(obj.primary_error) : undefined,
        raw: rawError,
      }
    }
  } catch {}
  return {
    code: 'ERROR',
    message: rawError,
    raw: rawError,
  }
}

test('R3 Boundary: Error parsing handles XSS payloads and malformed inputs', () => {
  // XSS inside error JSON
  const xssJson = JSON.stringify({
    code: '<script>alert(1)</script>',
    message: '<img src=x onerror=alert(2)>',
  })
  const parsed = parseJobError(xssJson)
  assert.strictEqual(parsed?.code, '<script>alert(1)</script>')
  assert.strictEqual(parsed?.message, '<img src=x onerror=alert(2)>')

  // Malformed JSON falls back gracefully
  const malformed = 'Error 500: Server encountered unexpected state'
  const fallback = parseJobError(malformed)
  assert.strictEqual(fallback?.code, 'ERROR')
  assert.strictEqual(fallback?.message, malformed)
})
