import test from 'node:test'
import assert from 'node:assert/strict'
import { policyStateLine } from '../src/copy.ts'

test('missing source facts remain unknown in the reader-facing status line', () => {
  assert.equal(policyStateLine({}), '来源复核状态未知 · 正文完整度未知 · 附件状态未知')
})

test('complete text does not mark the source as reviewed or attachments checked', () => {
  assert.equal(policyStateLine({ completeness: 'COMPLETE', review_status: 'UNREVIEWED', attachments_status: 'NOT_CHECKED' }), '来源未复核 · 正文完整 · 附件未检查')
})

test('review, text completeness and missing attachments remain independent facts', () => {
  assert.equal(policyStateLine({ review_status: 'REVIEWED', completeness: 'PARTIAL', attachments_status: 'MISSING' }), '来源已复核 · 正文不完整 · 附件缺失')
})
