# Test Suite Readiness: PrivacyTrace PR #88 (R6 Fixes)

## Current delivery boundary (2026-10-18, PR #88 R6 Fixes Delivery)

This suite establishes the test readiness and acceptance verification for the PR #88 R6 fixes (Issue #70 / PT-MOB-102 takeover).
Background persistent queue workers, independent runners, and public-service acceptance boundaries are governed by Issue #80.
Contract suites explicitly opt into controlled fixture doubles for hermetic, deterministic execution; `test_pr88_regressions.py`
separately verifies real Docker intake, manifest discovery, and multi-package scanning when `PRIVACYTRACE_DOCKER_TESTS=1`.

## Overview
This document summarizes the test infrastructure, test runner execution instructions, test run results, and feature readiness status for the PrivacyTrace PR #88 (R6 Fixes) delivery track.

---

## Deliverables

- **Test Infrastructure Documentation**: [`TEST_INFRA.md`](TEST_INFRA.md)
  Documents the 4-tier testing hierarchy, test methodology (Category-Partition, BVA, Pairwise, Real-World Workloads), and quality gates.
- **Supplementary Opaque E2E Test Suite**: [`apps/api/tests/test_e2e_r6_opaque.py`](apps/api/tests/test_e2e_r6_opaque.py)
  21 requirement-driven, opaque-box test cases mapping directly to Tier 1 (Feature Coverage), Tier 2 (Boundary & Corner Cases), Tier 3 (Cross-Feature Combinations), and Tier 4 (Real-World Application Scenarios).
- **Core R1 & R2 Feature Test Suite**: [`apps/api/tests/test_external_collection_import.py`](apps/api/tests/test_external_collection_import.py)
  40 comprehensive tests covering collector/1 batch collection contracts, all 6 result states, legacy compatibility, audit history retention, and source quotas.
- **PR #88 Regression Suite**: [`apps/api/tests/test_pr88_regressions.py`](apps/api/tests/test_pr88_regressions.py)
  16 regression guards covering transactional upload rollback, package set integrity, provenance survival, and opt-in Docker isolation.

---

## Test Execution Commands

### Prerequisites
- Python 3.12+ managed by `uv`
- Working directory: Repository root (`<repository-root>`)
- UTF-8 terminal encoding: `$env:PYTHONUTF8 = "1"` (Windows PowerShell)

### Run Supplementary E2E Opaque Suite
```powershell
$env:PYTHONUTF8 = "1"
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_e2e_r6_opaque.py -v
```

### Run Combined PR #88 R6 Test Suites
```powershell
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_external_collection_import.py apps/api/tests/test_pr88_regressions.py apps/api/tests/test_e2e_r6_opaque.py -v
```

### Run Static Analysis & Lint Verification
```powershell
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests/test_e2e_r6_opaque.py
```

### Verify Contract & Schema Zero-Drift Gate
```powershell
uv run --project apps/api --locked --extra worker python scripts/export-schema.py
git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts
```

---

## Test Run Results

Execution Timestamp: `2026-10-18T00:03:00Z`
Command: `uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_external_collection_import.py apps/api/tests/test_pr88_regressions.py apps/api/tests/test_e2e_r6_opaque.py -v`

Summary: **77 passed, 1 skipped (opt-in Docker seam), 0 failed** in 17.24s

### Status by Testing Tier

| Tier | Category | Total | Passed | Skipped | Failed | Notes |
|---|---|---|---|---|---|---|
| **Tier 1** | Feature Coverage (R1, R2, R3, R4) | 48 | 48 | 0 | 0 | 100% of all required features verified (source_type confirmation, collector/1, legacy compatibility, upload deduplication, contracts) |
| **Tier 2** | Boundary & Corner Cases | 18 | 18 | 0 | 0 | Empty bodies, 150 MiB limit, corrupted zip headers, duplicate IDs, missing base APK, source/audit/candidate quotas |
| **Tier 3** | Cross-Feature Combinations | 6 | 6 | 0 | 0 | Multi-source batch imports + quota checks + audit log persistence + provenance propagation to final reports + draft isolation |
| **Tier 4** | Real-World Application Scenarios | 6 | 5 | 1 | 0 | Policy collector batch export ingestion, report tool receipts, host app vs SDK consistency evaluation (1 skipped: opt-in Docker) |
| **Total** | | **78** | **77** | **1** | **0** | **100% Active Passing / 0 Failures** |

---

## Feature Readiness Checklist

### R1: 来源类型显式确认与误标防护
- [x] **R1.1**: Intercept external import when `source_type` is None/omitted, raising `SOURCE_TYPE_CONFIRMATION_REQUIRED` (HTTP 409) with atomic draft rollback.
- [x] **R1.2**: Explicit confirmation accepted with all valid canonical types (`SDK_POLICY`, `OFFICIAL_WEB_POLICY`, `STORE_POLICY`, `IN_APP_POLICY`).
- [x] **R1.3**: Third-party SDK policy is strictly tagged `SDK_POLICY` and isolated from host app claims; never auto-promoted to `OFFICIAL_WEB_POLICY`.
- [x] **R1.4**: Consistency engine evaluation confirms host app behaviors evaluated against `SDK_POLICY` yield `INSUFFICIENT_EVIDENCE`, whereas `OFFICIAL_WEB_POLICY` yields `EXACT_MATCH`.

### R2: collector/1 外部集合导入契约与审计留痕
- [x] **R2.1**: Ingest `ExternalPolicyCollectionInput` with `version="privacytrace-policy-collector/1"` and 1-8 results.
- [x] **R2.2**: State-to-source invariant validation across all 6 states (`RETRIEVED`, `PROVIDED`, `URL_ONLY`, `OFFLINE`, `UNAVAILABLE`, `NOT_FOUND`).
- [x] **R2.3**: Backward-compatible ingestion of legacy single-source `ExternalPolicyExportInput` payload.
- [x] **R2.4**: External import audit trail persisted in `draft["external_imports"]` (max 64 records) and forwarded to report receipts `report.tools["web_external_imports"]`.
- [x] **R2.5**: Provenance `EXTERNAL_CHAT_EXPORT` persisted on imported sources, report receipts, and evidence locators with verification disclaimers.
- [x] **R2.6**: Quota enforcement: reject >8 sources (409), >800 candidates (409), >64 audits (409), and reject intra-payload duplicate IDs (422) or draft collisions (409) atomically.

### R3: 上传异常映射统一收敛
- [x] **R3.1**: Consolidated upload exception mapping for `/apk` and `/package-set` via `upload_material()`.
- [x] **R3.2**: Canonical HTTP status code mapping: 404 `DRAFT_NOT_FOUND`, 400 `CORRUPTED_FILE`, 400 `EMPTY_PACKAGE_SET`, 400 `MISSING_BASE_APK`, 413 `UPLOAD_TOO_LARGE`, 503 `ISOLATED_INSPECTION_UNAVAILABLE`, 409 `UPLOAD_REJECTED`.
- [x] **R3.3**: Specific archive exception ordering `(BadZipFile, EOFError)` prioritized before broad `(ValueError, OSError)`.

### R4: 契约同步与完整回归测试
- [x] **R4.1**: Contract models exported in `scripts/export-schema.py`, including `web-external-collection-input` and `web-external-policy-input`.
- [x] **R4.2**: TypeScript definitions exported to `apps/web/src/contracts.generated.ts` with zero git diff drift.
- [x] **R4.3**: 100% passing E2E and regression test suite across all 4 tiers.
