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
  result: EvaluationResult
  evidence: Evidence[]
  behaviors: PrivacyBehavior[]
  policy_documents: PolicyDocument[]
}

export interface Taxonomy {
  version: string
  data_types: { id: string; label: string; parent: string | null }[]
}
