import type { AnalysisJob, DemoReport, JobsResponse, Report, ReviewRequest, Taxonomy } from './types'

async function request<T>(path: string, signal: AbortSignal, body?: ReviewRequest): Promise<T> {
  const response = await fetch(path, { signal, ...(body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-PrivacyTrace-Local': '1' }, body: JSON.stringify(body),
  } : {}) })
  if (!response.ok) throw new Error(`服务返回 ${response.status}，请确认后端正在运行。`)
  return response.json() as Promise<T>
}

export const loadReport = (signal: AbortSignal) => request<DemoReport>('/api/v1/demo/report', signal)
export const loadTaxonomy = (signal: AbortSignal) => request<Taxonomy>('/api/v1/taxonomy', signal)
export const loadJobs = (signal: AbortSignal) => request<JobsResponse>('/api/v1/jobs', signal)
export const loadJob = (id: string, signal: AbortSignal) => request<AnalysisJob>(`/api/v1/jobs/${encodeURIComponent(id)}`, signal)
export const loadJobReport = (id: string, signal: AbortSignal) => request<Report>(`/api/v1/jobs/${encodeURIComponent(id)}/report`, signal)
export const submitReview = (id: string, body: ReviewRequest, signal: AbortSignal) => request<Report>(`/api/v1/jobs/${encodeURIComponent(id)}/reviews`, signal, body)
export async function cancelJob(id: string, signal: AbortSignal): Promise<AnalysisJob> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}/cancel`, {
    method: 'POST', signal, headers: { 'X-PrivacyTrace-Local': '1' },
  })
  if (!response.ok) throw new Error(`取消失败：服务返回 ${response.status}。`)
  return response.json() as Promise<AnalysisJob>
}
// Retry never re-opens the old job: the API creates a new one and links it via retry_of.
export async function retryJob(id: string, signal: AbortSignal): Promise<AnalysisJob> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}/retry`, {
    method: 'POST', signal, headers: { 'X-PrivacyTrace-Local': '1' },
  })
  if (response.status === 409) throw new Error('原始材料已不可用，无法重试。')
  if (!response.ok) throw new Error(`重试失败：服务返回 ${response.status}。`)
  return response.json() as Promise<AnalysisJob>
}
export type DeleteJobResult = { status: string; job_id: string }
export async function deleteJob(id: string, signal: AbortSignal): Promise<DeleteJobResult> {
  const response = await fetch(`/api/v1/jobs/${encodeURIComponent(id)}`, {
    method: 'DELETE', signal, headers: { 'X-PrivacyTrace-Local': '1' },
  })
  if (response.status === 404) throw new Error('任务已删除。')
  if (!response.ok) throw new Error(`删除失败：服务返回 ${response.status}。`)
  return response.json() as Promise<DeleteJobResult>
}
