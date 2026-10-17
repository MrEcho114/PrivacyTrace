import test from 'node:test'
import assert from 'node:assert/strict'
import { sourceStatusLabels, emptySource } from '../src/workflow.ts'
import type { WebSource } from '../src/contracts.generated.ts'
import type { PolicySource } from '../src/workflow.ts'

test('API source states remain valid in the editor and URL-only sources do not claim a body', () => {
  const statuses: NonNullable<WebSource['status']>[] = ['ready', 'manual', 'empty', 'failed', 'url_only']
  for (const status of statuses) {
    const source: PolicySource = { ...emptySource(status), status }
    assert.equal(typeof sourceStatusLabels[source.status], 'string')
  }
  assert.equal(sourceStatusLabels.url_only, '仅有链接，尚无正文')
  assert.notEqual(sourceStatusLabels.url_only, sourceStatusLabels.ready)
})
