// #167 copy contract: the copy module is the single definition of the adopted
// names. This test fails if a key becomes unreachable (dead copy), if a retired
// key returns, if a nine-stage name is re-typed outside copy.ts, or if the
// unified policy state line starts inferring review from text availability.
import test from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { copy, frontendCopy, policyStateLine } from '../src/copy.ts'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const srcDir = path.resolve(__dirname, '../src')
const copyFile = path.join(srcDir, 'copy.ts')

// The design examples are deliberately excluded: they are a separate foundation
// entry that shares the copy module but is not part of the product UI contract.
function sourceFiles(dir = srcDir, collected: string[] = []): string[] {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    const full = path.join(dir, entry.name)
    const relative = path.relative(srcDir, full).replaceAll('\\', '/')
    if (entry.isDirectory()) {
      if (relative === 'design' || relative.startsWith('design/')) continue
      sourceFiles(full, collected)
    } else if (/\.(vue|ts|css)$/.test(entry.name) && relative !== 'copy.ts') {
      collected.push(full)
    }
  }
  return collected
}
const files = sourceFiles()
const sourceText = files.map((file) => fs.readFileSync(file, 'utf8')).join('\n')

// A reference is a real `copy.<key>` / `copy['<key>']` use, not a comment-only
// mention of the key name.
function referencedInCode(pattern: RegExp): boolean {
  for (const file of files) {
    for (const line of fs.readFileSync(file, 'utf8').split('\n')) {
      if (/^\s*(\/\/|\*|<!--)/.test(line)) continue
      if (pattern.test(line)) return true
    }
  }
  return false
}

test('every flat copy key is referenced by product source (copy.ts and design/ excluded)', () => {
  const keys = Object.keys(copy)
  assert.ok(keys.length > 0, 'copy must export at least one key')
  const unreferenced = keys.filter((key) =>
    !referencedInCode(new RegExp(`copy\\.${key}\\b`)) &&
    !sourceText.includes(`copy['${key}']`) &&
    !sourceText.includes(`copy["${key}"]`))
  assert.deepEqual(unreferenced, [], 'unreferenced copy keys must be deleted instead of lingering')
})

test('every frontendCopy display key is referenced by product source', () => {
  const displayKeys = [
    'steps', 'brandSubtitle', 'comparisonTitle', 'reportTitle', 'reportScope',
    'comparisonScope', 'demoBadge', 'stages', 'stageOrder',
  ]
  for (const key of displayKeys) {
    assert.equal(referencedInCode(new RegExp(`frontendCopy\\.${key}\\b`)), true, `frontendCopy.${key} is never rendered`)
  }
  for (const key of ['import', 'candidates', 'progress', 'report', 'reports']) {
    assert.equal(referencedInCode(new RegExp(`pageTitles\\.${key}\\b`)), true, `frontendCopy.pageTitles.${key} is never rendered`)
  }
  for (const key of ['dataType', 'evidence']) {
    assert.equal(referencedInCode(new RegExp(`table\\.${key}\\b`)), true, `frontendCopy.table.${key} is never rendered`)
  }
  for (const key of Object.keys(frontendCopy.facts)) {
    assert.equal(referencedInCode(new RegExp(`facts\\.${key}\\b`)), true, `frontendCopy.facts.${key} is never rendered`)
  }
  // reportTitleParts is an input to reportTitle, not a separately rendered
  // display key: design/ (excluded above) consumes the parts, so pin the
  // derivation instead of counting a reference the product UI cannot have.
  assert.ok(frontendCopy.reportTitleParts.length >= 2)
  assert.equal(frontendCopy.reportTitle, frontendCopy.reportTitleParts.join(' '))
})

test('the ten retired keys do not exist in the copy module or in product source', () => {
  const retired = ['homeTitle', 'homeDescription', 'scopeHelp', 'demoTitle', 'candidateDescription', 'modelHelp', 'sourceRecovered', 'unsavedText', 'sampleOnly', 'realInputHelp']
  const copySource = fs.readFileSync(copyFile, 'utf8')
  for (const key of retired) {
    assert.equal(new RegExp(`\\b${key}\\b`).test(copySource), false, `${key} must not return to copy.ts`)
    assert.equal(referencedInCode(new RegExp(`copy\\.${key}\\b`)), false, `${key} must not be referenced by source`)
  }
})

test('the nine stage names are defined only in copy.ts', () => {
  const stages = frontendCopy.stages
  assert.equal(frontendCopy.stageOrder.length, 9, 'the adopted stage order has nine states')
  assert.deepEqual([...frontendCopy.stageOrder].sort(), Object.keys(stages).sort(), 'stageOrder must enumerate exactly the stage map')
  assert.deepEqual(frontendCopy.stageOrder.map((stage) => stages[stage]), ['等待处理', '核对材料', '隔离扫描 APK', '装载政策原文', '规则对照', '生成报告', '报告已生成', '分析失败', '已取消'])
  for (const name of Object.values(stages)) {
    const quoted = new RegExp(`(['"\`])${name.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\1`)
    const offenders = files.filter((file) => quoted.test(fs.readFileSync(file, 'utf8')))
    assert.deepEqual(offenders.map((file) => path.relative(srcDir, file).replaceAll('\\', '/')), [], `stage name ${name} must not be re-typed outside copy.ts`)
  }
})

test('the adopted page, table and marker names stay literal', () => {
  assert.deepEqual(frontendCopy.steps, ['APK 与政策材料', '核对政策声明', '扫描与对照进度', '对照报告'])
  assert.equal(frontendCopy.pageTitles.import, frontendCopy.steps[0])
  assert.equal(frontendCopy.pageTitles.candidates, frontendCopy.steps[1])
  assert.equal(frontendCopy.pageTitles.progress, frontendCopy.steps[2])
  assert.equal(frontendCopy.pageTitles.report, 'APP 隐私收集越权报告')
  assert.equal(frontendCopy.pageTitles.reports, '本机存档报告')
  assert.deepEqual(frontendCopy.table, { dataType: '数据类型', evidence: '证据' })
  assert.equal(frontendCopy.comparisonTitle, '数据类型与政策声明对照')
  assert.equal(frontendCopy.demoBadge, '示例体验 · 固定材料')
  assert.equal(frontendCopy.brandSubtitle, '隐私权限使用与隐私声明对照')
})

test('policyStateLine keeps missing, unknown and partial values unknown', () => {
  const unknownLine = '来源复核状态未知 · 正文完整度未知 · 附件状态未知'
  assert.equal(policyStateLine({}), unknownLine)
  assert.equal(policyStateLine({ review_status: null, completeness: null, attachments_status: null }), unknownLine)
  // A future/unknown enum value must stay unknown instead of being rounded up.
  assert.equal(policyStateLine({ review_status: 'FUTURE' as never, completeness: 'FUTURE' as never, attachments_status: 'FUTURE' as never }), unknownLine)
  // Fetching a full body never implies review; partial facts stay partial.
  assert.equal(policyStateLine({ completeness: 'COMPLETE' }), '来源复核状态未知 · 正文完整 · 附件状态未知')
  assert.equal(policyStateLine({ review_status: 'UNREVIEWED', completeness: 'PARTIAL', attachments_status: 'NOT_CHECKED' }), '来源未复核 · 正文不完整 · 附件未检查')
  assert.equal(policyStateLine({ review_status: 'REVIEWED', completeness: 'COMPLETE', attachments_status: 'COMPLETE' }), '来源已复核 · 正文完整 · 附件齐全')
  assert.equal(policyStateLine({ attachments_status: 'MISSING' }), '来源复核状态未知 · 正文完整度未知 · 附件缺失')
  assert.doesNotMatch(policyStateLine({ review_status: null, completeness: 'COMPLETE' }), /已复核/, 'body availability must not upgrade review')
})
