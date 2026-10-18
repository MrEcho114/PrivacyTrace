# PrivacyTrace PR #88 Test Infrastructure & Quality Gates

> Evidence boundary: These fixtures and contract tests verify the repair track for PR #88 (Issue #70 / PT-MOB-102 multi-package sets intake and task lifecycle).
> Runtime background queue delivery, runner integration, and public-service acceptance boundaries are governed by
> Issue #80. Parser doubles in contract suites are separate from the opt-in real Docker regression in `apps/api/tests/test_pr88_regressions.py`.

> **Authoritative Specification**: PR #88 Takeover (Issue #70 Candidate Semantics, Upload Staging Protection, 101-Package Limits, ARSC Fault Isolation, Behavior Budget Deduplication, WebSource Provenance, Frontend Source Status Labels, Test Falsifiability)
> **Status**: Active / Maintained
> **Scope**: Test architecture, test hierarchy, and execution guidelines for PR #88 repairs and multi-package intake
> **Location**: `docs/test-infra.md`

---

## 1. Test Architecture & Foundations

The PrivacyTrace PR #88 test suite (`apps/api/tests/test_e2e_pt_mob_102.py`, `apps/api/tests/test_e2e_r6_opaque.py`, `apps/api/tests/test_external_collection_import.py`, `apps/api/tests/test_pr88_regressions.py`, and `apps/web/tests/source-status.test.ts`) provides requirement-driven verification across all PR #88 repair areas.

### 1.1 Architecture & Layers

```
+-------------------------------------------------------------------------+
|                          HTTP Client Layer                              |
|         fastapi.testclient.TestClient (transport, headers, streams)     |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Security & Middleware Seam Layer                       |
|   draft_access auth: Local header / Capability token verification       |
|   Streaming size quota: 150 MiB MAX_INPUT enforcement                   |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                      Application Services Layer                         |
|   web_api.py:   Uniform upload_material exception mapping (404, 400,    |
|                 409, 413, 503), /import-external routing                |
|   web_intake.py: Draft sessions, BoundedSemaphore concurrency,          |
|                 ExternalPolicyCollectionInput & ExportInput validation, |
|                 external_imports audit history & provenance tagging,    |
|                 active upload staging guard, granular file locks        |
|   package_set.py: 10 integrity rules, single base APK, split names,     |
|                 101-package set boundary early exit                     |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     Storage & Persistence Seam                          |
|   JobStore / Draft file storage (atomic save, revision snapshots)       |
|   Zero external database dependency in local/test profile               |
+-------------------------------------------------------------------------+
```

### 1.2 Fixture Synthesis Architecture

1. **Deterministic Bytecode & AXML Synthesizer**:
   - `apk()` / `manifest()`: Synthesizes valid unsigned APKs with binary AXML and DEX entries without external Android SDK or JVM dependencies.
   - `package_set_archive()`: Packages base APK and feature split APKs into `.zip` archives with custom compression headers and manifest configurations.
2. **Policy Collection & Legacy Export Synthesizer**:
   - `make_collection()`: Produces `ExternalPolicyCollectionInput` payloads conforming to version `privacytrace-policy-collector/1` with valid collection states (`RETRIEVED`, `PROVIDED`, `URL_ONLY`, `OFFLINE`, `UNAVAILABLE`, `NOT_FOUND`).
   - `make_source()`: Produces source objects with configurable `source_type` (`SDK_POLICY`, `OFFICIAL_WEB_POLICY`, `STORE_POLICY`, `IN_APP_POLICY`), text, URL, and metadata.
   - `ExternalPolicyExportInput`: Produces legacy single-source export payloads with `source`, `claims`, and `summary`.

---

## 2. Test Methodology

### 2.1 Category-Partition (CP) Method

| Input Domain | Partitions |
| :--- | :--- |
| **Source Type Declaration** | Explicitly declared (`SDK_POLICY`, `OFFICIAL_WEB_POLICY`, `STORE_POLICY`, `IN_APP_POLICY`), Missing/Omitted (`None`), Invalid string |
| **Collection Envelope** | Valid `version="privacytrace-policy-collector/1"`, Unsupported version, 0 results (empty), 1-8 results, >8 results |
| **Collection Result States**| `RETRIEVED` (with text + URL), `PROVIDED` (with text), `URL_ONLY` (URL + empty text), `OFFLINE` (optional source), `UNAVAILABLE` (empty text + error code), `NOT_FOUND` (no source) |
| **Upload Payload Format** | Standalone single APK (`/apk`), Multi-package archive (`/package-set`), Corrupted ZIP header, Truncated ZIP, Non-ZIP bytes, >101 APKs archive |
| **Upload Exception Mapping**| Missing draft (404), BadZipFile/EOFError (400), UploadTooLarge (413), ScanError (503), PackageSetIntegrityError (exc.http_status: 400 or 413), ValueError/OSError (409) |
| **Draft Quotas** | Source count <= 8 (valid) vs >8 (409), Candidates <= 800 (valid) vs >800 (409), Audits <= 64 (valid) vs >64 (409) |
| **Policy Provenance** | Auto-discovered (`MANIFEST_METADATA`), Externally imported (`EXTERNAL_CHAT_EXPORT`), Manual (`MANUAL_INPUT`), Direct fetch (`DIRECT_WEB_FETCH`) |
| **Candidate Start Semantics** | Unchecked candidates (`checked=False`) accepted without 409; resulting document retains `review_status="UNREVIEWED"` |

### 2.2 Boundary Value Analysis (BVA)

- **Upload Stream Size Boundary**: `0 bytes` (rejected with 409 on `/apk` or 400 on `/package-set`), `150 * 1024 * 1024` bytes (maximum allowed), `> 150 MiB` (rejected with HTTP 413 `UPLOAD_TOO_LARGE`).
- **Package Set Entry Boundary**: `101 APKs` (1 base + 100 splits, maximum allowed), `102 APKs` (rejected immediately in intake with HTTP 413 `TOO_MANY_PACKAGES`).
- **Collection Results Boundary**: `0 results` (rejected with 422), `1 result` (minimal valid collection), `8 results` (maximum allowed collection size), `9 results` (rejected with 422).
- **Draft Source Capacity Boundary**: `7 existing + 1 added = 8` (allowed), `8 existing + 1 added = 9` (rejected with 409).
- **External Import History Boundary**: `64 audit entries` (maximum allowed), `65th import` (rejected with 409).

### 2.3 Pairwise Combinations

- **Collector Batch Ingestion x Legacy Export Ingestion**: Seamless coexistence of modern collector/1 batch imports and legacy single-source exports in the same draft.
- **Batch Ingest x Quota Overflow Rollback**: When a batch import would push total draft sources beyond quota, the entire batch is atomically rolled back without partial ingestion.
- **Multi-Source Ingest x Package Set Scan x Report Generation**: External sources with `provenance="EXTERNAL_CHAT_EXPORT"` correctly propagate to report tools receipts (`web_external_imports`, `web_policy_sources`) and evidence locators.
- **Concurrent Draft Isolation**: Independent drafts with distinct capability tokens maintain strict isolation without state or audit leakage.
- **Concurrent Upload x Service Cleanup**: In-flight uploads registered in `active_drafts` are protected while `start_service` safely purges stale pending uploads.

### 2.4 Real-World Workload Simulation

- **Policy Collector Batch Export Pipeline**: Full-cycle import of realistic batch outputs from policy collectors, containing mixed states (retrieved, provided, url_only, offline, not_found), combined with package set upload and analysis.
- **Consistency Engine Seam Verification**: Verifying that `SDK_POLICY` (third-party SDK disclosure) evaluated against host app behavior produces `INSUFFICIENT_EVIDENCE`, whereas `OFFICIAL_WEB_POLICY` produces `EXACT_MATCH`, validating R1 mislabeling protection end-to-end.

---

## 3. Four-Tier Test Hierarchy & Requirements Coverage

```
+---------------------------------------------------------------------+
| Tier 4: Real-World Workload Scenarios                               |
|   - Policy Collector Batch Export End-to-End Pipeline               |
|   - Host App vs SDK Consistency Evaluation Seam (Mislabel Defense)   |
|   - Report Tool Receipt Generation & Provenance Audit Trail         |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 3: Cross-Feature Combinations                                  |
|   - Multi-Source Imports + Quota Enforcement + Atomic Rollback      |
|   - Multi-Source Ingest + Package Set Upload + Report Receipts      |
|   - Independent Draft Isolation & Capability Scoping                |
|   - Active Upload Protection during Service Startup                 |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 2: Boundary & Corner Cases                                     |
|   - Empty Upload Body (409 on /apk, 400 on /package-set, 422 JSON)   |
|   - 150 MiB Stream Boundary Enforcement (HTTP 413 UPLOAD_TOO_LARGE)  |
|   - 101-Package Limit Immediate Rejection (HTTP 413)                |
|   - Corrupted ZIP Headers & Central Directory (HTTP 400)            |
|   - Malformed ARSC Resource String Pool Fault Isolation             |
|   - Intra-Payload Duplicate Source IDs (422) & Draft Collision (409)|
|   - Package Set Missing Base APK (HTTP 400 MISSING_BASE_APK)        |
|   - Source Quota (>8), Candidate Quota (>800), Audit Quota (>64)    |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 1: Feature Coverage                                            |
|   - Candidate Unchecked Start Acceptance with UNREVIEWED Semantics   |
|   - Source Type Confirmation Interception (HTTP 409)                |
|   - Source Type Valid Types Accepted (SDK/OFFICIAL/STORE/IN_APP)     |
|   - collector/1 Batch Collection Contract (All 6 States)            |
|   - Legacy Compatibility (ExternalPolicyExportInput)                |
|   - WebSource Provenance Enum & Description Typing                  |
|   - Frontend Source Status Label Rendering (url_only, etc.)         |
|   - Upload Exception Deduplication (/apk and /package-set)          |
|   - Contract Serialization Integrity & Zero Schema Drift            |
+---------------------------------------------------------------------+
```

---

## 4. Test Suite Mapping

| Suite | File Path | Focus | Execution Profile |
|---|---|---|---|
| **PT-MOB-102 E2E Suite** | `apps/api/tests/test_e2e_pt_mob_102.py` | Full E2E multi-package intake, split attribution, start gates | Hermetic / Fast |
| **E2E Opaque Suite** | `apps/api/tests/test_e2e_r6_opaque.py` | 4-Tier Opaque-box E2E Verification for R1, R2, R3, R4 | Hermetic / Fast |
| **External Collection Import** | `apps/api/tests/test_external_collection_import.py` | R1 & R2 Backend Verification, Invariants & Persistence | Hermetic / Fast |
| **PR #88 Regressions** | `apps/api/tests/test_pr88_regressions.py` | Upload Rollback, Package Set Limits, Provenance, Docker | Hermetic (Docker opt-in) |
| **Web Source Status SFC Test** | `apps/web/tests/source-status.test.ts` | Frontend Vue component status label rendering & dictionary | Node / Vitest |
| **Web Report Source Test** | `apps/web/tests/report-source.test.cjs` | Web contract and CJS sandbox compatibility | Node / Vitest |

---

## 5. Docker Test Boundaries & Environment Requirements

- **Hermetic Contract & Unit Suites**: Standard unit, contract, and mock-based tests run in local environments without Docker daemon dependencies.
- **Containerized Analysis & Challenger Tests**: Real container extraction and analysis verification (such as `test_challenger_manifest.py`, `test_challenger_dex.py`, and real container runs in `test_pr88_regressions.py`) interact with the Docker daemon and require:
  - Docker daemon running on the host system.
  - Environment variable `PRIVACYTRACE_DOCKER_TESTS=1`.
- **Skip Semantics**: Local runs skip opt-in container cases when `PRIVACYTRACE_DOCKER_TESTS` is unset or `0`. The authoritative `scripts/check.sh` forces it to `1` when `CI=true`, builds the worker image and executes these cases against Docker. The separately scheduled browser `challenger` job has its own event condition; its `SKIPPED` status on a pull request does not describe the central Check job's Docker coverage.

---

## 6. Quality Gates & Execution Commands

### Test Execution
```powershell
uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_external_collection_import.py apps/api/tests/test_pr88_regressions.py apps/api/tests/test_e2e_r6_opaque.py apps/api/tests/test_e2e_pt_mob_102.py -v
```

### Static Analysis & Lint
```powershell
uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests
```

### Contract & Schema Zero-Drift Gate
```powershell
uv run --project apps/api --locked --extra worker python scripts/export-schema.py
git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts
```

### Full Authority Gate
```powershell
powershell -NoProfile -File scripts/check.ps1
```
