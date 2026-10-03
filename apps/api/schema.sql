-- Design baseline only. No runtime persistence is wired in v0.1.
PRAGMA foreign_keys = ON;
CREATE TABLE IF NOT EXISTS sample_app (
    id TEXT PRIMARY KEY,
    package_name TEXT,
    version_name TEXT,
    version_code INTEGER,
    apk_sha256 TEXT,
    official_source_url TEXT,
    acquired_at TEXT,
    input_mode TEXT NOT NULL CHECK (input_mode IN ('APK', 'SYNTHETIC'))
);
CREATE TABLE IF NOT EXISTS analysis_job (
    id TEXT PRIMARY KEY,
    sample_id TEXT NOT NULL REFERENCES sample_app(id),
    state TEXT NOT NULL CHECK (state IN ('QUEUED','INTAKE','STATIC_ANALYSIS','POLICY_PARSING',
        'EVALUATING','REPORTING','SUCCEEDED','FAILED','CANCELLED')),
    ruleset_version TEXT NOT NULL,
    created_at TEXT NOT NULL,
    error TEXT,
    package_name TEXT,
    version_code INTEGER CHECK (version_code >= 0),
    region TEXT,
    product_scope TEXT
);
CREATE TABLE IF NOT EXISTS policy_artifact (
    sha256 TEXT PRIMARY KEY CHECK (length(sha256) = 64),
    text TEXT NOT NULL CHECK (length(text) BETWEEN 1 AND 200000),
    normalization TEXT NOT NULL CHECK (normalization = 'NONE')
);
CREATE TABLE IF NOT EXISTS policy_document (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES analysis_job(id),
    source_type TEXT NOT NULL CHECK (source_type IN
        ('IN_APP_POLICY','STORE_POLICY','OFFICIAL_WEB_POLICY','SDK_POLICY')),
    version TEXT NOT NULL,
    captured_at TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL REFERENCES policy_artifact(sha256),
    completeness TEXT NOT NULL CHECK (completeness IN ('COMPLETE','PARTIAL')),
    extraction_status TEXT NOT NULL DEFAULT 'NOT_STARTED'
        CHECK (extraction_status IN ('NOT_STARTED','SUCCEEDED','PARTIAL','FAILED')),
    review_status TEXT NOT NULL DEFAULT 'UNREVIEWED'
        CHECK (review_status IN ('UNREVIEWED','REVIEWED')),
    attachments_status TEXT NOT NULL DEFAULT 'NOT_CHECKED'
        CHECK (attachments_status IN ('NOT_CHECKED','COMPLETE','MISSING')),
    applicability_json TEXT NOT NULL,
    snapshot_path TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES analysis_job(id),
    kind TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('STATIC_POTENTIAL','DECLARED')),
    source TEXT NOT NULL,
    locator TEXT NOT NULL,
    excerpt TEXT NOT NULL,
    document_id TEXT REFERENCES policy_document(id),
    artifact_sha256 TEXT REFERENCES policy_artifact(sha256),
    start_offset INTEGER,
    end_offset INTEGER,
    api_call_json TEXT,
    CHECK ((kind = 'POLICY_SENTENCE' AND start_offset IS NOT NULL
            AND end_offset IS NOT NULL AND start_offset >= 0 AND end_offset > start_offset)
        OR (kind != 'POLICY_SENTENCE' AND start_offset IS NULL AND end_offset IS NULL))
);
-- The JSON payloads follow the Pydantic/JSON Schema contracts; repository methods are pending.
CREATE TABLE IF NOT EXISTS privacy_behavior (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES analysis_job(id),
    data_type TEXT NOT NULL,
    facts_json TEXT NOT NULL,
    contextual_hints_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS policy_claim (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES policy_document(id),
    data_type TEXT NOT NULL,
    declarations_json TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS privacy_issue (
    id TEXT PRIMARY KEY,
    job_id TEXT NOT NULL REFERENCES analysis_job(id),
    behavior_id TEXT NOT NULL REFERENCES privacy_behavior(id),
    status TEXT NOT NULL,
    evidence_status TEXT NOT NULL,
    explanation TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS issue_evidence (
    issue_id TEXT NOT NULL REFERENCES privacy_issue(id),
    evidence_id TEXT NOT NULL REFERENCES evidence(id),
    PRIMARY KEY (issue_id, evidence_id)
);
