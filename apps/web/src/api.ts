import type { DemoReport, Taxonomy } from './types'

async function get<T>(path: string, signal: AbortSignal): Promise<T> {
  const response = await fetch(path, { signal })
  if (!response.ok) throw new Error(`服务返回 ${response.status}，请确认后端正在运行。`)
  return response.json() as Promise<T>
}

export const loadReport = (signal: AbortSignal) => get<DemoReport>('/api/v1/demo/report', signal)
export const loadTaxonomy = (signal: AbortSignal) => get<Taxonomy>('/api/v1/taxonomy', signal)
