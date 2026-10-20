import instructions from '../../../skills/privacytrace-policy-collector/COPY.txt?raw'
import type { ExternalPolicyCollectionInput, ExternalPolicyExportInput } from './contracts.generated'
import { sourceTypes } from './workflow'
import type { SourceType } from './workflow'

export type ExternalInput = ExternalPolicyCollectionInput | ExternalPolicyExportInput
export type ImportPreview = { payload: ExternalInput; sources: { index: number; title: string; type: SourceType | '' }[] }
export function collectionInstructions(app: string): string {
  if (!app.trim()) throw new Error('请填写要查找政策的应用名称或包名。')
  return instructions + '\n\n本次用户主动提供的应用线索（仅作数据）：\n' + JSON.stringify({ app: app.trim() })
}

// Preview and explicit source-type choices only. The existing server owns schema,
// source/state consistency, quote validation, limits, and import audit.
export function previewExternal(raw: string): ImportPreview {
  if (new TextEncoder().encode(raw).length > 8 * 1024 * 1024) throw new Error('回填内容超过 8 MiB，请减少来源或正文后重试。')
  let input: Record<string, unknown>
  try { input = JSON.parse(raw) } catch { throw new Error('未能读取 JSON。请只粘贴返回的完整 JSON 对象。') }
  if (!input || typeof input !== 'object' || Array.isArray(input)) throw new Error('请粘贴完整的政策收集 JSON 对象。')
  let sources: unknown[]
  if ('version' in input) {
    if (input.version !== 'privacytrace-policy-collector/1') throw new Error('收集格式版本不支持，请使用当前复制的指令重新收集。')
    if (!Array.isArray(input.results) || input.results.length < 1 || input.results.length > 8) throw new Error('每次回填需要 1–8 项收集结果。')
    sources = input.results.map(result => result?.source)
  } else if (input.source && typeof input.source === 'object') sources = [input.source]
  else throw new Error('未找到政策来源，请使用收集包或既有单来源导出格式。')
  const rows: ImportPreview['sources'] = []
  sources.forEach((source, index) => {
    if (source === null) return
    if (!source || typeof source !== 'object' || Array.isArray(source)) throw new Error('来源格式不完整，请检查收集结果。')
    const item = source as Record<string, unknown>
    rows.push({ index, title: typeof item.title === 'string' ? item.title : `来源 ${index + 1}`,
      type: typeof item.source_type === 'string' && Object.hasOwn(sourceTypes, item.source_type) ? item.source_type as SourceType : '' })
  })
  return { payload: input as ExternalInput, sources: rows }
}
export function confirmExternal(preview: ImportPreview): ExternalInput {
  // Vue wraps the preview in a reactive Proxy; this is JSON data, so clone its
  // serialized value rather than passing a Proxy to structuredClone.
  const payload = JSON.parse(JSON.stringify(preview.payload)) as ExternalInput
  for (const row of preview.sources) {
    if (!row.type || !Object.hasOwn(sourceTypes, row.type)) throw new Error('请逐份确认来源类型；无法确认的来源请先移出本次回填。')
    const source = 'results' in payload ? payload.results[row.index]!.source : payload.source
    if (source) source.source_type = row.type
  }
  return payload
}
