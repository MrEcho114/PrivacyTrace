import test from 'node:test'
import assert from 'node:assert'
import {
  SDK_PAGE_SIZE,
  clampSdkPage,
  getSdkEvidence,
  sdkPageCount,
  sdkPageSlice,
} from '../src/sdkEvidence.ts'
import type { Evidence } from '../src/types.ts'

function evidence(id: string, kind: Evidence['kind']): Evidence {
  return {
    id,
    kind,
    status: 'STATIC_POTENTIAL',
    source: kind === 'SDK' ? 'classes.dex' : 'AndroidManifest.xml',
    locator: 'apk_sha256=deadbeef;class=' + id,
    excerpt: id + ' matches published package prefix com.example of example SDK',
  }
}

test('SDK evidence is selectable without any matching issue', () => {
  // The point of the panel: no issue cites SDK evidence, so the privacy
  // comparison can never surface it.
  const report = [evidence('ev-sdk-a', 'SDK')]
  assert.strictEqual(getSdkEvidence(report).length, 1)
  assert.deepStrictEqual(getSdkEvidence(report).map((item) => item.id), ['ev-sdk-a'])
})

test('only SDK evidence is selected from a mixed report', () => {
  const mixed = [
    evidence('ev-sdk-a', 'SDK'),
    evidence('ev-manifest-b', 'MANIFEST'),
    evidence('ev-api-c', 'API'),
    evidence('ev-sdk-d', 'SDK'),
    evidence('ev-policy-e', 'POLICY_SENTENCE'),
    evidence('ev-doc-f', 'POLICY_DOCUMENT'),
  ]
  const sdk = getSdkEvidence(mixed)
  assert.deepStrictEqual(sdk.map((item) => item.id), ['ev-sdk-a', 'ev-sdk-d'])
  assert.ok(sdk.every((item) => item.kind === 'SDK'))
})

test('zero SDK hits is an empty selection, not an error', () => {
  // The template keys its "未命中当前有限规则集" message off this being empty.
  const none = getSdkEvidence([evidence('ev-manifest-b', 'MANIFEST')])
  assert.deepStrictEqual(none, [])
  assert.strictEqual(none.length, 0)
})

test('page count always offers at least one page', () => {
  assert.strictEqual(sdkPageCount(0), 1)
  assert.strictEqual(sdkPageCount(1), 1)
  assert.strictEqual(sdkPageCount(SDK_PAGE_SIZE), 1)
  assert.strictEqual(sdkPageCount(SDK_PAGE_SIZE + 1), 2)
  assert.strictEqual(sdkPageCount(SDK_PAGE_SIZE * 4), 4)
})

test('paging covers every entry exactly once', () => {
  const total = SDK_PAGE_SIZE * 3 + 7
  const all = Array.from({ length: total }, (_, i) => evidence(`ev-sdk-${i}`, 'SDK'))
  const seen: string[] = []
  for (let page = 0; page < sdkPageCount(total); page++) {
    seen.push(...sdkPageSlice(all, page).map((item) => item.id))
  }
  assert.strictEqual(seen.length, total, 'no omissions')
  assert.strictEqual(new Set(seen).size, total, 'no duplicates')
  assert.deepStrictEqual(seen, all.map((item) => item.id))
})

test('a page never exceeds the page size', () => {
  const all = Array.from({ length: 500 }, (_, i) => evidence(`ev-sdk-${i}`, 'SDK'))
  for (let page = 0; page <= sdkPageCount(all.length); page++) {
    assert.ok(sdkPageSlice(all, page).length <= SDK_PAGE_SIZE)
  }
})

test('an out-of-range page is clamped rather than returning nothing', () => {
  const all = Array.from({ length: SDK_PAGE_SIZE + 1 }, (_, i) =>
    evidence(`ev-sdk-${i}`, 'SDK'),
  )
  const last = sdkPageCount(all.length) - 1
  assert.strictEqual(clampSdkPage(99, all.length), last)
  assert.strictEqual(clampSdkPage(-5, all.length), 0)
  assert.strictEqual(clampSdkPage(Number.NaN, all.length), 0)
  // A shrinking report must not strand the viewer on an empty page.
  assert.ok(sdkPageSlice(all, 99).length > 0)
})

test('an empty report yields one empty page, never an undefined page', () => {
  assert.strictEqual(sdkPageCount(0), 1)
  assert.deepStrictEqual(sdkPageSlice([], 0), [])
  assert.deepStrictEqual(sdkPageSlice([], 3), [])
})

test('selection preserves worker order so the panel matches the report', () => {
  const ordered = [
    evidence('ev-sdk-1', 'SDK'),
    evidence('ev-manifest-x', 'MANIFEST'),
    evidence('ev-sdk-2', 'SDK'),
    evidence('ev-sdk-3', 'SDK'),
  ]
  assert.deepStrictEqual(getSdkEvidence(ordered).map((item) => item.id), [
    'ev-sdk-1',
    'ev-sdk-2',
    'ev-sdk-3',
  ])
})

test('the panel renders only fields the worker already provides', () => {
  // No regex parsing of excerpt: the selected records are handed to the template
  // as-is, so the panel cannot drift from the worker's wording.
  const records = getSdkEvidence([evidence('ev-sdk-a', 'SDK')])
  assert.deepStrictEqual(Object.keys(records[0]).sort(), [
    'excerpt',
    'id',
    'kind',
    'locator',
    'source',
    'status',
  ])
})
