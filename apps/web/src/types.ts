import type {
  AnalysisJob, EvaluationResult, Evidence, PolicyDocument, PrivacyBehavior,
} from './contracts.generated'

export type * from './contracts.generated'

// Demo envelope matches main.demo_report; nested contracts are generated.
export interface DemoReport {
  demo: true
  sample: {
    name: string
    package_name: string
    version: string
    input_mode: 'SYNTHETIC'
  }
  job: AnalysisJob
  // The demo envelope is assembled per response, so it is always a live
  // generation rather than a replay from persisted storage.
  delivery_mode: 'LIVE_GENERATED'
  result: EvaluationResult
  evidence: Evidence[]
  behaviors: PrivacyBehavior[]
  policy_documents: PolicyDocument[]
}

export interface Taxonomy {
  version: string
  data_types: { id: string; label: string; parent: string | null }[]
}

export type ReportSource =
  | { kind: 'demo' }
  | { kind: 'job'; id: string }

export function serializeSource(source: ReportSource): string {
  return source.kind === 'demo' ? 'demo:synthetic' : `job:${source.id}`
}

export function parseSource(val: string): ReportSource {
  if (val === 'demo:synthetic' || val === 'demo') {
    return { kind: 'demo' }
  }
  if (val.startsWith('job:')) {
    return { kind: 'job', id: val.slice(4) }
  }
  return { kind: 'job', id: val }
}
