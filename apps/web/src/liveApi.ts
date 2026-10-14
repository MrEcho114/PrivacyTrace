import type { AnalysisJob } from './types'
import type { WebCandidate, WebSource, DraftInput, CandidateInput, StartInput, ModelSettings } from './contracts.generated'

export type ModelStatus = Omit<ModelSettings, 'api_key'> & { key_configured: boolean; max_apk_bytes: number }
export function displaySourceUrl(value: string | null | undefined): string {
  if (!value) return ''
  try {
    const url = new URL(value)
    url.username = ''; url.password = ''; url.hash = ''
    const keys: string[] = []
    url.searchParams.forEach((_, key) => keys.push(key))
    for (const key of keys) url.searchParams.set(key, 'REDACTED')
    return url.toString()
  } catch { return '网址格式无效' }
}
export type LiveDraft = {
  id: string; revision: number; name: string; uploaded: boolean; apk_sha256: string | null
  sources: WebSource[]; candidates: WebCandidate[]
  jobs: { job_id: string; request_id: string; revision: number; events: { state: string; at: string }[] }[]
}
const messages: Record<string, string> = {
  MODEL_NOT_CONFIGURED: '模型尚未配置。请打开项目设置，或手动添加候选。',
  INPUT_OR_VERSION_REJECTED: '输入未通过检查、版本已变化或本机存储已满。请重新读取材料，检查候选原句后重试。',
  UPLOAD_REJECTED: '上传未完成。请选择非空、150 MiB 以内的 APK；更换文件请新建材料。',
  UPLOAD_TOO_LARGE: 'APK 超过 150 MiB，请选择更小的文件。',
  DRAFT_NOT_FOUND: '本机材料记录不存在，请重新导入。',
  INPUT_VALIDATION_FAILED: '输入格式不符合要求，请检查来源、原句和字段。',
}
export async function liveRequest<T>(path: string, signal: AbortSignal, body?: object | File): Promise<T> {
  const response = await fetch('/api/v1/web/' + path, {
    signal, ...(body ? {
      method: 'POST', headers: { 'X-PrivacyTrace-Local': '1', 'Content-Type': body instanceof File ? 'application/octet-stream' : 'application/json' },
      body: body instanceof File ? body : JSON.stringify(body),
    } : {}),
  })
  if (!response.ok) {
    const detail = await response.json().catch(() => ({}))
    throw new Error(messages[detail.detail] || `服务返回 ${response.status}。检查本机服务后重试。`)
  }
  return response.json() as Promise<T>
}
export const createDraft = (input: DraftInput, signal: AbortSignal) => liveRequest<LiveDraft>('drafts', signal, input)
export const readDraft = (id: string, signal: AbortSignal) => liveRequest<LiveDraft>(`drafts/${id}`, signal)
export const uploadApk = (id: string, file: File, signal: AbortSignal) => liveRequest<LiveDraft>(`drafts/${id}/apk`, signal, file)
export const fetchSource = (id: string, source: string, revision: number, signal: AbortSignal) => liveRequest<LiveDraft>(`drafts/${id}/sources/${source}/fetch`, signal, { revision })
export const extractSource = (id: string, source: string, revision: number, signal: AbortSignal) => liveRequest<LiveDraft>(`drafts/${id}/sources/${source}/extract`, signal, { revision })
export const saveCandidates = (id: string, input: CandidateInput, signal: AbortSignal) => liveRequest<LiveDraft>(`drafts/${id}/candidates`, signal, input)
export const startScan = (id: string, input: StartInput, signal: AbortSignal) => liveRequest<AnalysisJob>(`drafts/${id}/start`, signal, input)
