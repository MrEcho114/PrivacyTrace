import type { AnalysisJob, DemoReport, JobsResponse, Report, ReviewRequest, Taxonomy } from './types'

export type RequestFailure = Error & { status?: number; path?: string }
export const jobPath = (id: string) => `/api/v1/jobs/${encodeURIComponent(id)}`
export const jobReportPath = (id: string) => `${jobPath(id)}/report`
export function isNotFoundFor(cause: unknown, path: string): boolean {
  return cause instanceof Error && (cause as RequestFailure).status === 404 && (cause as RequestFailure).path === path
}

// A transport failure has no HTTP status; the browser's own string is English
// and names nothing the reader can act on. Say what failed and what to check.
const offline = '无法连接本机服务。确认服务已启动后重试。'
async function send(path: string, init: RequestInit, signal: AbortSignal): Promise<Response> {
  try {
    return await fetch(path, { ...init, signal })
  } catch (cause) {
    if (cause instanceof Error && cause.name === 'AbortError') throw cause
    throw new Error(offline)
  }
}

async function request<T>(path: string, signal: AbortSignal, body?: ReviewRequest): Promise<T> {
  const response = await send(path, body ? {
    method: 'POST', headers: { 'Content-Type': 'application/json', 'X-PrivacyTrace-Local': '1' }, body: JSON.stringify(body),
  } : {}, signal)
  if (!response.ok) {
    const failure = new Error(`请求失败（HTTP ${response.status}）。请稍后重试。`) as RequestFailure
    failure.status = response.status
    failure.path = path
    throw failure
  }
  return response.json() as Promise<T>
}

export const loadReport = (signal: AbortSignal) => request<DemoReport>('/api/v1/demo/report', signal)
export const loadTaxonomy = (signal: AbortSignal) => request<Taxonomy>('/api/v1/taxonomy', signal)
export const loadJobs = (signal: AbortSignal) => request<JobsResponse>('/api/v1/jobs', signal)
export const loadJob = (id: string, signal: AbortSignal) => request<AnalysisJob>(jobPath(id), signal)
export const loadJobReport = (id: string, signal: AbortSignal) => request<Report>(jobReportPath(id), signal)
export const submitReview = (id: string, body: ReviewRequest, signal: AbortSignal) => request<Report>(`${jobPath(id)}/reviews`, signal, body)
export async function cancelJob(id: string, signal: AbortSignal): Promise<AnalysisJob> {
  const response = await send(`${jobPath(id)}/cancel`, { method: 'POST', headers: { 'X-PrivacyTrace-Local': '1' } }, signal)
  if (!response.ok) throw new Error(`取消失败（HTTP ${response.status}）。请稍后重试。`)
  return response.json() as Promise<AnalysisJob>
}
// Retry never re-opens the old job: the API creates a new one and links it via retry_of.
export async function retryJob(id: string, signal: AbortSignal): Promise<AnalysisJob> {
  const response = await send(`${jobPath(id)}/retry`, { method: 'POST', headers: { 'X-PrivacyTrace-Local': '1' } }, signal)
  if (response.status === 409) throw new Error('原始材料已不可用，无法重试。重新选择应用后再开始。')
  if (!response.ok) throw new Error(`重试失败（HTTP ${response.status}）。请稍后重试。`)
  return response.json() as Promise<AnalysisJob>
}
export type DeleteJobResult = { status: string; job_id: string }
export async function deleteJob(id: string, signal: AbortSignal): Promise<DeleteJobResult> {
  const response = await send(jobPath(id), { method: 'DELETE', headers: { 'X-PrivacyTrace-Local': '1' } }, signal)
  if (response.status === 404) throw new Error('任务已删除。')
  if (!response.ok) throw new Error(`删除失败（HTTP ${response.status}）。请稍后重试。`)
  return response.json() as Promise<DeleteJobResult>
}
