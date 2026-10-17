# PrivacyTrace PT-MOB-102 (Issue #70) Test Infrastructure & Quality Gates

> **Authoritative Specification**: PT-MOB-102 (Multi-Package APK Set Intake, Remote Task Lifecycle & Access Protection, and Policy Auto-Discovery & Thin Adaptation)  
> **Status**: Active / Test-Ready  
> **Target Worktree**: `C:\Users\Oasis\.gemini\antigravity\worktrees\PrivacyTrace\issue_70`

---

## 1. Test Architecture & Foundations

The PrivacyTrace PT-MOB-102 E2E test suite (`apps/api/tests/test_e2e_pt_mob_102.py`) provides opaque-box, requirement-driven verification of Android multi-package APK set intake, capability-scoped task lifecycle protection, in-app policy auto-discovery, and external chat policy import (#79).

### 1.1 Architecture & Layers

```
+-------------------------------------------------------------------------+
|                          HTTP Client Layer                              |
|         fastapi.testclient.TestClient (transport & header control)       |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                  Security & Middleware Seam Layer                       |
|   JobWriteBoundsMiddleware: 150 MiB set quota, pre-body auth, token auth  |
|   SecuritySeam: pt_cap_* validation, query-param leak block, tombstones |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                      Application Services Layer                         |
|   web_api.py / web_intake.py: Draft sessions, PackageSet intake,       |
|                               policy discovery, #79 chat import         |
|   main.py / job_store.py:     AnalysisJob lifecycle, cancel, retry,    |
|                               evidence drilldown, human reviews         |
|   apk_worker.py:              Base & Split DEX/manifest scanning,       |
|                               evidence attribution (package_split)      |
+-------------------------------------------------------------------------+
                                     |
                                     v
+-------------------------------------------------------------------------+
|                     Storage & Persistence Seam                          |
|   JobStorageProtocol (MemoryJobStore / FileJobStore)                    |
|   Zero external database / runner dependencies (#80 abstract boundary) |
+-------------------------------------------------------------------------+
```

### 1.2 Fixture Synthesis Architecture

1. **Deterministic Bytecode & AXML Synthesizer**:
   - `build_axml_manifest()`: Generates binary Android XML without Android SDK or JVM. Supports custom `package_name`, `version_code`, `version_name`, `split_name`, `<uses-permission>` tags, and `<meta-data>` policy URLs.
   - `dex()`: Generates binary Dalvik Executable bytecode with realistic API invokes (`Camera.open()`, `LocationManager.getLastKnownLocation()`, `ContentResolver.query()`).
2. **Multi-Package Archive Synthesizer**:
   - Assembles valid `.apks` or `.zip` archives containing `base.apk` and multiple split APKs (`split_config.apk`, `split_feature.apk`).
   - Supports adversarial mutations: missing base APK, package name mismatch, version code discrepancy, duplicate split names, corrupt ZIP signatures, and synthetic >150 MiB stream simulation.
3. **External #79 Chat Export Generator**:
   - Synthesizes external chat policy collections with verbatim source text, character-offset verified quotes, `model_audit` AI summary separation, and offline statuses (`url_only`, `not_found`, `failed`).

---

## 2. Test Methodology

The test suite applies four formal verification methodologies to ensure high coverage and defect detection:

### 2.1 Category-Partition (CP) Method

Inputs and environmental conditions are formally partitioned into equivalence classes:

| Input Domain | Partitions |
| :--- | :--- |
| **Package Set Composition** | Single APK, Base + 1 Split, Base + Multiple Splits, Only Splits (No Base), Multiple Bases |
| **Package Identity** | Homogeneous package name across all parts, Mismatched split package name |
| **Version Code** | Identical version code across all parts, Mismatched split version code |
| **Split Identification** | Unique split names, Duplicate split names, Empty split string |
| **Set Size** | 0 bytes (empty), Normal (<150 MiB), Exact boundary (150 MiB), Exceeded (>150 MiB) |
| **Digest Integrity** | Matching SHA-256 for all parts, Tampered bytes with mismatched SHA-256 |
| **Token Transport** | `Authorization: Bearer <token>`, `X-PrivacyTrace-Token: <token>`, Query param `?token=...` (Prohibited) |
| **Token Validity** | Valid token matching job, Unmatched token from another job, Forged token, Tombstoned job token |
| **Candidate Review State**| Unreviewed (`checked: False`), Reviewed (`checked: True`), Mismatched quote string |
| **External Policy Source**| Verbatim text with quotes, AI summary only (no policy text), Offline/failed URL |

### 2.2 Boundary Value Analysis (BVA)

Critical numerical and protocol boundaries are evaluated:
- **Set Quota Boundary**: `0 bytes` (rejected), `1 byte` (valid minimum), `150 * 1024 * 1024` bytes (maximum allowed), `150 * 1024 * 1024 + 1` bytes (rejected with HTTP 413).
- **Split Count Boundary**: `0 splits` (valid single APK backward compatibility), `1 split` (minimal split set), `10 splits` (multi-feature set).
- **Version Code Boundary**: `version_code = 1` vs `version_code = 2` between base and split (must match strictly).
- **Token String Boundary**: Empty string (401), Malformed prefix (401), Valid `pt_cap_[A-Za-z0-9_-]{20,}` (200), Query parameter injection (400).

### 2.3 Pairwise (Combinatorial) Testing

Interactions between independent features are exercised across key pairs:
- **Package Set Ingestion x Explicit Retry**: A multi-split job that fails or completes can be retried with preserved split evidence and lineage.
- **Package Set Ingestion x Unreviewed Policy Claims**: A multi-split app analyzed against unreviewed auto-discovered and imported policy claims.
- **Draft Quota x Multi-Package Archive Streaming**: Archive streaming within pre-body middleware authentication limits.
- **Single APK Fallback x New Lifecycle Routes**: Single APK jobs work transparently with `/evidence/{id}` and `/retry`.
- **Cancelled Task x Retry Attempt**: Cancelled multi-package task can be explicitly retried into a new task without reviving the cancelled task.
- **Tombstoned Task x Evidence / Retry**: Deleted job rejects retry and evidence drilldown with HTTP 404.

### 2.4 Real-World Workload Simulation

Simulates complete production user and client journeys:
- Multi-split app (Base APK + Split Config + Split Feature) with distinct DEX entrypoints.
- In-app policy auto-discovery extracting privacy policy URLs from manifest metadata and string resources.
- External #79 chat policy claim import merged into draft revision.
- Non-blocking analysis submission with unreviewed claims.
- Progress polling, full report retrieval, evidence drilldown with `package_split` attribution.
- Auditor review note submission.
- Explicit retry spawning new linked task with `retry_of` lineage.
- Irreversible deletion with tombstone verification.

---

## 3. Four-Tier Test Hierarchy & Requirements Coverage

The test suite in `apps/api/tests/test_e2e_pt_mob_102.py` is organized into 4 distinct tiers:

```
+---------------------------------------------------------------------+
| Tier 4: Real-World Workload Scenarios                               |
|   - Full End-to-End Multi-Split Analysis Workflow (Base + 2 Splits) |
|   - Policy Discovery, Consistency Evaluation, Evidence Drilldown,   |
|     Review Notes, Explicit Retry Lineage & Irreversible Tombstone   |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 3: Cross-Feature Combinations (Pairwise)                       |
|   - Package Set Upload + Explicit Retry Lineage                     |
|   - Package Set Ingestion + Unreviewed Policy Claims Consistency     |
|   - Single-APK Compatibility + New Evidence & Retry Routes          |
|   - Auto-Discovered + #79 Imported Sources Ingestion                |
|   - Cancelled Task + Retry Spawn (No Resurrection)                  |
|   - Tombstoned Task + Retry Rejection (404)                         |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 2: Boundary & Corner Cases (Adversarial / Stress)              |
|   - Missing Base APK (400)          - Split Package Mismatch (400)  |
|   - Split Version Mismatch (400)    - Duplicate Split Name (400)    |
|   - Empty Archive (400)             - Corrupted ZIP Archive (400)   |
|   - Quota Exceeded >150 MiB (413)   - Token in Query Param (400)    |
|   - Cross-Task Token Access (403)   - Post-Cancel Late Write (Drop) |
|   - Post-Delete Tombstone (404)     - Retry on Running Job (409)    |
|   - Unreviewed Start (Allowed)      - Quote Mismatch (409)          |
|   - External AI Summary Only (Safe)                                 |
+---------------------------------------------------------------------+
                                   ^
+---------------------------------------------------------------------+
| Tier 1: Feature Coverage (Core Functional Requirements)             |
|   - R1: Multi-Package APK Set Intake & Integrity (Features 1-11)    |
|   - R2: Task Lifecycle & Capability Access Protection (F12-26)      |
|   - R3: Policy Auto-Discovery & Thin Adaptation (#79) (F27-33)      |
+---------------------------------------------------------------------+
```

---

## 4. Feature Inventory & Coverage Mapping

| Req | # | Feature | Test Function / Tier in `test_e2e_pt_mob_102.py` |
| :--- | :--- | :--- | :--- |
| **R1** | 1 | Standalone Single APK Ingestion | `test_r1_f1_single_apk_intake_backward_compatibility` (Tier 1) |
| **R1** | 2 | Package Set Manifest Contract | `test_r1_f2_package_set_manifest_contract` (Tier 1) |
| **R1** | 3 | Package Set Archive Streaming | `test_r1_f3_package_set_archive_streaming` (Tier 1) |
| **R1** | 4 | Base APK Presence Validation | `test_r1_f4_base_apk_presence_validation` (Tier 1), `test_t2_missing_base_apk` (Tier 2) |
| **R1** | 5 | Package Name Homogeneity | `test_r1_f5_package_name_homogeneity` (Tier 1), `test_t2_split_package_mismatch` (Tier 2) |
| **R1** | 6 | Version Code Consistency | `test_r1_f6_version_code_consistency` (Tier 1), `test_t2_split_version_mismatch` (Tier 2) |
| **R1** | 7 | Split Identification Uniqueness | `test_r1_f7_split_name_uniqueness` (Tier 1), `test_t2_duplicate_split_name` (Tier 2) |
| **R1** | 8 | Per-File & Set SHA-256 Check | `test_r1_f8_sha256_verification` (Tier 1), `test_t2_sha256_mismatch` (Tier 2) |
| **R1** | 9 | Cumulative 150 MiB Quota | `test_r1_f9_cumulative_set_size_quota` (Tier 1), `test_t2_quota_exceeded_150mib` (Tier 2) |
| **R1** | 10 | Evidence Split Attribution | `test_r1_f10_evidence_split_attribution` (Tier 1) |
| **R1** | 11 | Split DEX Coverage Aggregation | `test_r1_f11_split_dex_coverage_aggregation` (Tier 1) |
| **R2** | 12 | Anonymous Draft Token Issuance | `test_r2_f12_anonymous_draft_token_issuance` (Tier 1) |
| **R2** | 13 | Token Digest One-Way Storage | `test_r2_f13_token_digest_one_way_storage` (Tier 1) |
| **R2** | 14 | Query Param Token Prohibition | `test_r2_f14_query_param_token_prohibition` (Tier 1), `test_t2_token_in_query_param` (Tier 2) |
| **R2** | 15 | Pre-Body Capability Auth | `test_r2_f15_pre_body_capability_auth` (Tier 1) |
| **R2** | 16 | Idempotent Task Submission | `test_r2_f16_idempotent_task_submission` (Tier 1) |
| **R2** | 17 | Job Token Digest Inheritance | `test_r2_f17_job_token_inheritance` (Tier 1) |
| **R2** | 18 | Job Status & Progress Polling | `test_r2_f18_job_status_and_progress_polling` (Tier 1) |
| **R2** | 19 | Report Retrieval Access Guard | `test_r2_f19_report_retrieval_access_guard` (Tier 1) |
| **R2** | 20 | Granular Evidence Drilldown | `test_r2_f20_granular_evidence_drilldown` (Tier 1) |
| **R2** | 21 | Review & Note Submission | `test_r2_f21_review_note_submission` (Tier 1) |
| **R2** | 22 | Irreversible Cancellation | `test_r2_f22_irreversible_cancellation` (Tier 1), `test_t2_post_cancel_late_write_discarded` (Tier 2) |
| **R2** | 23 | Explicit Retry with Lineage | `test_r2_f23_explicit_retry_with_lineage` (Tier 1), `test_t2_retry_on_running_job_rejected` (Tier 2) |
| **R2** | 24 | Irreversible Tombstone Delete | `test_r2_f24_tombstone_deletion` (Tier 1), `test_t2_post_delete_tombstone_access_rejected` (Tier 2) |
| **R2** | 25 | Global Job Listing Blocked | `test_r2_f25_global_job_listing_blocked` (Tier 1) |
| **R2** | 26 | Admin Settings Isolated | `test_r2_f26_admin_settings_isolated` (Tier 1) |
| **R3** | 27 | In-App Policy Auto-Discovery | `test_r3_f27_in_app_policy_auto_discovery` (Tier 1) |
| **R3** | 28 | Discovery Provenance Retained | `test_r3_f28_discovery_provenance_retention` (Tier 1) |
| **R3** | 29 | Non-Blocking Unreviewed Start | `test_r3_f29_non_blocking_unreviewed_candidate_start` (Tier 1), `test_t2_unreviewed_candidate_start_succeeds` (Tier 2) |
| **R3** | 30 | Review Audit Integrity | `test_r3_f30_review_audit_integrity_unreviewed` (Tier 1) |
| **R3** | 31 | #79 External Chat Ingestion | `test_r3_f31_external_chat_export_ingest` (Tier 1) |
| **R3** | 32 | AI Summary / Text Separation | `test_r3_f32_ai_summary_text_separation` (Tier 1), `test_t2_external_chat_ai_summary_only` (Tier 2) |
| **R3** | 33 | External Offline Status Map | `test_r3_f33_external_offline_status_mapping` (Tier 1) |
| **R4** | 34 | Contract Sync & Hygiene | Verified by `scripts/export-schema.py` and `ruff check` |

---

## 5. Quality Gates & Thresholds

| Quality Gate | Requirement | Verification Command | Threshold |
| :--- | :--- | :--- | :--- |
| **Code Style & Linting** | Python 3.11+, Ruff check | `uv run --project apps/api --locked --extra worker ruff check apps/api/src apps/api/tests scripts/export-schema.py` | 0 errors, 0 warnings |
| **Contract Synchronization**| Pydantic to TypeScript Sync | `uv run --project apps/api --locked --extra worker python scripts/export-schema.py && git diff --exit-code -- packages/contracts apps/web/src/contracts.generated.ts` | 0 diff |
| **Test Suite Execution** | Complete test suite passes | `$env:PYTHONUTF8="1"; uv run --project apps/api --locked --extra worker pytest apps/api/tests/test_e2e_pt_mob_102.py -q -p no:cacheprovider` | 100% pass across all implemented features |
| **Regression Safety** | Existing tests pass | `$env:PYTHONUTF8="1"; uv run --project apps/api --locked --extra worker pytest apps/api/tests -q -p no:cacheprovider` | Zero regression on existing 981 tests |
| **Token Safety Gate** | Zero token plaintext on disk | Automated assertion in `test_r2_f13_token_digest_one_way_storage` | 0 plaintext `pt_cap_*` strings |
| **Quota Enforcement Gate** | >150 MiB rejected pre-write | Automated assertion in `test_r1_f9_cumulative_set_size_quota` | HTTP 413, 0 bytes buffered |
| **Tombstone Enforcement Gate**| Deleted jobs cannot revive | Automated assertion in `test_r2_f24_tombstone_deletion` | HTTP 404 on all subsequent calls |
