export type MatchStatus =
  | 'EXACT_MATCH' | 'CATEGORY_MATCH' | 'NOT_DECLARED'
  | 'POLICY_SOURCE_CONFLICT' | 'AMBIGUOUS_DISCLOSURE' | 'INSUFFICIENT_EVIDENCE'

export interface Evidence {
  id: string
  kind: 'MANIFEST' | 'API' | 'SDK' | 'POLICY_DOCUMENT' | 'POLICY_SENTENCE'
  status: 'STATIC_POTENTIAL' | 'DECLARED'
  source: string
  locator: string
  excerpt: string
  document_id: string | null
}

export interface PrivacyIssue {
  id: string
  behavior_id: string
  data_type: string
  status: MatchStatus
  evidence_status: 'STATIC_POTENTIAL'
  evidence_ids: string[]
  explanation: string
  policy_document_ids: string[]
}

export interface PolicyDocument {
  id: string
  source_type: string
  title: string
  version: string
  captured_at: string
  sha256: string
}

export interface DemoReport {
  demo: true
  sample: { name: string; package_name: string; version: string }
  job: { id: string; ruleset_version: string; input_mode: 'SYNTHETIC' }
  result: { issues: PrivacyIssue[] }
  evidence: Evidence[]
  policy_documents: PolicyDocument[]
}

export interface Taxonomy {
  version: string
  data_types: { id: string; label: string; parent: string | null }[]
}
