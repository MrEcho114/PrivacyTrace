# Test Suite Readiness: PT-MOB-102 (Issue #70)

## Overview
This document summarizes the test infrastructure, test runner execution instructions, test results, and feature readiness status for the PrivacyTrace Multi-Package APK Set & Remote Lifecycle project (PT-MOB-102 / Issue #70).

---

## Deliverables
- **Test Architecture Documentation**: [`TEST_INFRA.md`](TEST_INFRA.md)
  Documents the 4-tier testing hierarchy, test methodology (Category-Partition, BVA, Pairwise, Real-World Workloads), and quality gates.
- **End-to-End Test Suite**: [`apps/api/tests/test_e2e_pt_mob_102.py`](apps/api/tests/test_e2e_pt_mob_102.py)
  55 deterministic, opaque-box, requirement-driven test cases covering Tier 1 (Features F1–F33), Tier 2 (Boundary & Adversarial Cases), Tier 3 (Pairwise Feature Combinations), and Tier 4 (Real-World Application Workflows).
- **Core Production Modules**:
  - `apps/api/src/privacytrace/package_set.py`: 10-rule package set validation, AXML split detection, reserved split name `"base"` rejection (`DUPLICATE_SPLIT_NAME`), split regex validation (`^[a-zA-Z0-9_.-]+$`), and atomic rollback.
  - `apps/api/src/privacytrace/web_intake.py`: Streamed ZIP/APKS upload, handles corrupted central directory headers with HTTP 400 (`CORRUPTED_FILE`), policy auto-discovery (`discover_sources`), external chat policy import (`import_external`), and non-blocking candidate submission.
  - `apps/api/src/privacytrace/apk_worker.py`: Namespaces DEX files (`base:classes.dex`, `split:<name>:classes.dex`) and attributes evidence to originating split.
  - `apps/api/src/privacytrace/job_store.py`: Task lifecycle with irreversible cancellation, explicit retry with lineage (`retry_of`), and tombstone deletion.
  - `apps/api/src/privacytrace/main.py` & `web_api.py`: Evidence drilldown route (`GET /api/v1/jobs/{job_id}/evidence/{evidence_id}`), retry route (`POST /api/v1/jobs/{job_id}/retry`), source discovery (`POST /api/v1/web/drafts/{draft_id}/sources/discover`), and external chat export ingest (`POST /api/v1/web/drafts/{draft_id}/import-external`).
  - `apps/api/src/privacytrace/models.py` & `runtime_models.py` & `web_models.py`: Schema extensions with `Evidence.package_split`, `AnalysisJob.retry_of`, `SampleMetadata.package_set`, `WebSource.provenance`, `WebSource.status` (`url_only`), and `ExternalPolicyExportInput`.

---

## Test Execution Commands

### Prerequisites
- Python 3.12+ managed by `uv`
- Working directory: Repository root (`C:\Users\Oasis\.gemini\antigravity\worktrees\PrivacyTrace\issue_70`)
- UTF-8 terminal encoding: `$env:PYTHONUTF8 = "1"` (Windows PowerShell)

### Run PT-MOB-102 Test Suite
```powershell
$env:PYTHONUTF8 = "1"
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_e2e_pt_mob_102.py -v -p no:cacheprovider
```

### Run Combined Milestone Test Suites
```powershell
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_package_set_intake.py apps/api/tests/test_package_set_challenge.py apps/api/tests/test_challenger_m1_2_split_dex.py apps/api/tests/test_e2e_pt_mob_102.py -v -p no:cacheprovider
```

### Run Lint & Style Verification
```powershell
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests scripts/export-schema.py
```

### Export Schemas & Contracts
```powershell
uv run --project apps/api --locked --extra worker python scripts/export-schema.py
git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts
```

---

## Test Run Results
Execution Timestamp: `2026-10-17T09:14:00Z`
Command: `pytest apps/api/tests/test_e2e_pt_mob_102.py`
Summary: **55 passed, 0 skipped, 0 failed** in 7.10s
Combined Milestones Summary: **140 passed, 0 skipped, 0 failed** in 20.39s

### Status by Testing Tier

| Tier | Category | Total | Passed | Skipped | Failed | Notes |
|---|---|---|---|---|---|---|
| **Tier 1** | Feature Coverage (F1–F33) | 33 | 33 | 0 | 0 | 100% of all required features implemented and validated |
| **Tier 2** | Boundary & Corner Cases | 15 | 15 | 0 | 0 | Validates quotas (>150 MiB), missing base, package/version mismatch, duplicate split, corrupted zip, query-param token injection, cross-task auth, post-cancel late write, tombstone rejection, quote mismatch |
| **Tier 3** | Pairwise Combinations | 5 | 5 | 0 | 0 | Cross-checks multi-package upload with retry, cancellation, tombstoning, source merging, and single-APK backward compatibility |
| **Tier 4** | Real-World Workloads | 2 | 2 | 0 | 0 | Full end-to-end multi-split app lifecycle and adversarial tamper/recovery scenarios verified |
| **Total** | | **55** | **55** | **0** | **0** | **100% Passing / 0 Skipped / 0 Failed** |

---

## Feature Readiness Checklist

### R1: Multi-Package APK Set Input & Integrity Verification
- [x] **F1**: Single-APK intake backward compatibility (`POST /api/v1/web/drafts/{id}/apk`)
- [x] **F2**: Package set manifest contract (`package_name`, `version_code`, `split_configs`, `total_size_bytes`)
- [x] **F3**: Package set archive streaming upload (`POST /api/v1/web/drafts/{id}/package-set`)
- [x] **F4**: Base APK presence validation (rejects missing base APK)
- [x] **F5**: Package name homogeneity (rejects split with mismatched `package_name`)
- [x] **F6**: Version code consistency (rejects split with mismatched `version_code`)
- [x] **F7**: Split name uniqueness (rejects duplicate split identifiers)
- [x] **F8**: SHA-256 integrity verification across all uploaded APK constituents
- [x] **F9**: Cumulative package set quota enforcement (<= 150 MiB total limit)
- [x] **F10**: Split attribution in granular evidence (`Evidence.package_split`)
- [x] **F11**: Cross-split DEX coverage aggregation and namespacing (`base:classes.dex`, `split_feature:classes.dex`)

### R2: Remote Task Lifecycle & Scoped Capability Access Protection
- [x] **F12**: Anonymous draft creation issues unprivileged `pt_cap_*` token
- [x] **F13**: Token digest one-way persistence (`token_digest` stored, plaintext discarded)
- [x] **F14**: Token in URL query parameters strictly prohibited (immediate HTTP 400)
- [x] **F15**: Pre-body middleware authenticates token before reading streaming bodies
- [x] **F16**: Idempotent task submission with client-provided `request_id`
- [x] **F17**: Analysis job inherits capability digest from draft upon start
- [x] **F18**: Polling job status and progress with task token (`GET /api/v1/jobs/{id}`)
- [x] **F19**: Report retrieval access guard (`GET /api/v1/jobs/{id}/report`)
- [x] **F20**: Granular evidence drilldown (`GET /api/v1/jobs/{id}/evidence/{ev_id}`)
- [x] **F21**: Review note submission (`POST /api/v1/jobs/{id}/reviews`)
- [x] **F22**: Irreversible cancellation of in-flight jobs (`POST /api/v1/jobs/{id}/cancel`)
- [x] **F23**: Explicit task retry with lineage (`POST /api/v1/jobs/{id}/retry`)
- [x] **F24**: Tombstone deletion (`DELETE /api/v1/jobs/{id}`) returns HTTP 404 on subsequent access
- [x] **F25**: Global job listing blocked in remote mode (`GET /api/v1/jobs` returns 403)
- [x] **F26**: Admin settings endpoints isolated from public remote callers

### R3: Policy Auto-Discovery & External Thin Adaptation (#79)
- [x] **F27**: In-app policy auto-discovery (`POST /api/v1/web/drafts/{id}/sources/discover`)
- [x] **F28**: Discovery provenance retention (`WebSource.provenance = "MANIFEST_METADATA"`)
- [x] **F29**: Non-blocking unreviewed candidate start (`checked=False` allowed to start)
- [x] **F30**: Review audit integrity with unreviewed sources (`PolicyDocument.review_status = "UNREVIEWED"`)
- [x] **F31**: External chat export ingest (`POST /api/v1/web/drafts/{id}/import-external`)
- [x] **F32**: AI summary text separation (stored in `model_audit["external_summary"]`, never in policy text)
- [x] **F33**: External offline status mapping (`url_only`/empty text mapped to `"empty"` or `"failed"`)
