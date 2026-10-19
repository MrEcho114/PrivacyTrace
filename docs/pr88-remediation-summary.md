# Technical Resolution Summary: PrivacyTrace PR #88 Code Review Repairs

> **Context**: PR #88 (PT-MOB-102: Multi-package sets intake and remote task lifecycle)
> **Review Reference**: Collaborator Fenghaji Review (`#pullrequestreview-5559133466`)
> **Authoritative References**: Issue #70, `docs/stages/s1-acceptance-20261009.md`, `GLOSSARY.md`, TheMasterplan
> **Target Branch**: `fix_pr_eighty_eight`

---

## 1. Executive Overview

PrivacyTrace PR #88 delivers the foundation for PT-MOB-102 (multi-package set intake, feature split APK attribution, and remote analysis job lifecycle). During review, collaborator Fenghaji issued a "Changes Requested" review (`#pullrequestreview-5559133466`). The feedback focused on three main categories:
1. **Core Review Blockers**: Rationale and semantics of candidate check relaxation in `_register_start` (Issue #70), along with disposition of root test documentation files (`TEST_READY.md` and `TEST_INFRA.md`).
2. **Concurrency, Safety & Exception Boundaries (P2)**: Upload staging deletion races during service start, transaction lock granularity during file operations, 101-package set boundary early exits, ARSC string pool exception isolation, behavior budget deduplication, and `WebSource.provenance` typing.
3. **Frontend Consistency & Test Falsifiability**: Inconsistent `url_only` status rendering in `App.vue:388`, false-green unit tests, and 404 test skip escape hatches in `test_e2e_pt_mob_102.py`.

This document summarizes the comprehensive technical resolution of each review item, confirming alignment with project boundaries and authoritative specifications.

---

## 2. Review Resolution by Category

### 2.1 Core Review Blockers & Fact Semantics

#### 2.1.1 Candidate Gate Relaxation & UNREVIEWED Semantics (`web_intake.py:1210`)
- **Review Finding**: `captures(draft, require_checked=False)` was relaxed from the earlier `require_checked=True` gate without documentation or explicit test verification of `UNREVIEWED` semantics.
- **Authoritative Decision**:
  - Issue #70 (User Story 8 & Implementation Decisions): *"取消强制逐条检查候选的启动门，保留用户主动修正；不自动填写人工检查记录或提升政策复核状态。"*
  - S1 Acceptance (`docs/stages/s1-acceptance-20261009.md`): Revocation of manual A/B checklist gates does not imply policy verification. Policies remain `PARTIAL` / `UNREVIEWED` / `NOT_CHECKED`, and rules missing evidence evaluate to `INSUFFICIENT_EVIDENCE`.
- **Implementation**:
  - In `web_intake.py:_register_start`: Clarified via docstring and comments that unreviewed candidates yield `review_status="UNREVIEWED"`, `completeness="PARTIAL"`, `attachments_status="NOT_CHECKED"`, and `human_review_gate="NOT_REQUIRED_BY_WORKFLOW"`.
  - In `test_e2e_pt_mob_102.py:test_r3_f29_non_blocking_unreviewed_candidate_start`: Added explicit test asserting that starting an analysis with unreviewed candidates successfully returns HTTP 200, generates a job, and the resulting report document strictly retains `review_status == "UNREVIEWED"`.

#### 2.1.2 Root Documentation Disposition
- **Review Finding**: Root directory contained ephemeral execution reports (`TEST_READY.md`) and valuable architecture documentation placed in the root with unexpanded placeholders (`TEST_INFRA.md`).
- **Implementation**:
  - `TEST_READY.md`: Completely removed from the repository root. Useful tier definitions and test verification commands converged into this summary and the PR description.
  - `TEST_INFRA.md`: Migrated to `docs/test-infra.md`. Line 9 placeholder (`<repository-root>`) replaced with documentation metadata; unverified/absolute claims removed; Docker daemon requirements and container test boundaries explicitly documented.

---

### 2.2 Concurrency, Quotas & Exception Boundaries

#### 2.2.1 Active Upload Staging Protection (`web_intake.py:460, 1105`)
- **Review Finding**: `start_service()` cleans up stale `upload.pending*` and `packages.pending*` files on service startup/restart. Concurrent in-flight uploads could have their staging directories removed if `start_service()` executed mid-upload.
- **Implementation**:
  - Wrapped `_upload_reserved` in `with self._draft_activity(draft_id):`, ensuring in-flight uploads increment `self.active_drafts[draft_id]`.
  - Updated `start_service()` cleanup loop to inspect `if self.active_drafts.get(directory.name, 0): continue`, safely skipping active upload directories.

#### 2.2.2 Lock Granularity Optimization (`web_intake.py:534`)
- **Review Finding**: `_finish_upload` held `self.data_store._transaction()` during disk operations (`rmtree`, `os.replace`, and `shutil.copyfile` up to 150 MiB), unnecessarily blocking other draft API requests.
- **Implementation**:
  - Moved directory renaming (`os.replace`) and file copying (`shutil.copyfile`) outside of the database transaction.
  - Reduced the `_transaction()` block to an atomic read-modify-write that verifies draft upload state, updates draft metadata (`uploaded=True`, `package_set=...`), and saves the revision snapshot.
  - Rollback handler ensures any disk files published prior to an aborted transaction are cleaned up.

#### 2.2.3 101-Package Set Boundary Early Exit (`package_set.py:329, 346`, `web_intake.py:390`)
- **Review Finding**: Archives with >101 APKs were unpacked and sequentially processed, timing out after 180s and returning HTTP 503 rather than an immediate 4xx client rejection.
- **Implementation**:
  - In `package_set.py:validate_package_set`, added immediate boundary check: `if len(files) > 101:` raises `PackageSetIntegrityError("PACKAGE_SET_TOO_LARGE", ..., http_status=413)`.
  - In `web_intake.py:_finish_upload`, added pre-validation check on unpacked APK paths before invoking containerized package inspectors.

#### 2.2.4 ARSC Resource String Resolution Fault Isolation (`apk_worker.py:848, 915`)
- **Review Finding**: `_manifest_resource_strings` lacked exception guards around ARSC parsing, allowing malformed resource pools or cyclic references to bubble up, abort the inspection worker, and discard all discovered manifest URLs.
- **Implementation**:
  - Wrapped `_manifest_resource_strings` in `try...except Exception: return []`.
  - In `inspect_package_metadata`, isolated `ARSCParser` creation and string resolution so corrupted resource pools do not prevent parsing direct manifest URL strings or remaining valid resources.

#### 2.2.5 Behavior Budget & Split Deduplication (`apk_worker.py:662, 899`)
- **Review Finding**: Duplicate permissions in split APKs prematurely consumed entries against the 500-behavior limit; split tools were overwritten by base tools; discovered URLs exceeding 8 were dropped silently.
- **Implementation**:
  - Deduplicated split manifest permissions against base permissions before counting against the 500-behavior limit.
  - Merged split tools (`unmapped_android_invokes`, `inventory_scope`) into `merged_tools`.
  - Added truncation notice to `result["coverage"]["limitations"]` when discovered policy URLs exceed 8.

#### 2.2.6 WebSource Provenance Typing & Contract Zero-Drift (`web_models.py:10, 50`)
- **Review Finding**: `WebSource.provenance` was an untyped optional string without enum constraints or disclaimer documentation.
- **Implementation**:
  - Defined `PolicySourceProvenance = Literal["MANIFEST_METADATA", "EXTERNAL_CHAT_EXPORT", "DIRECT_WEB_FETCH", "MANUAL_INPUT"]`.
  - Documented `provenance` field as technical acquisition origin that does not imply official verification.
  - Re-exported schema via `scripts/export-schema.py` and updated `contracts.generated.ts` with zero schema drift.

---

### 2.3 Frontend Consistency & Test Falsifiability

#### 2.3.1 Frontend Status Rendering Fix (`App.vue:388`, `types.ts`)
- **Review Finding**: `App.vue:388` rendered `url_only` as `'已获取正文'`, misleading users that text had been retrieved.
- **Implementation**:
  - Consolidated status labels into `sourceStatusLabels` dictionary in `types.ts`.
  - Updated `App.vue:388` to reference `sourceStatusLabels[item.status] ?? '未知状态'`, correctly displaying `'url_only'` as 「仅有链接，尚无正文」.

#### 2.3.2 Unit Test Falsifiability (`apps/web/tests/source-status.test.ts`)
- **Review Finding**: `source-status.test.ts` suffered from inverted argument order in `emptySource('probe')` and lacked Vue component template assertions.
- **Implementation**:
  - Rewrote `source-status.test.ts` into a genuine component integration test using `@vue/compiler-sfc` and `@vue/server-renderer`.
  - Validates `sourceStatusLabels` dictionary completeness across all statuses.
  - Mounts `App.vue` with real report fixtures and asserts SSR output matches `官网隐私政策链接 · 仅有链接，尚无正文`, while strictly failing if `已获取正文` or `已获取网页正文` is rendered.

#### 2.3.3 E2E Test Suite Hardening (`apps/api/tests/test_e2e_pt_mob_102.py`)
- **Review Finding**: `test_e2e_pt_mob_102.py` contained 29 `check_unwired_route` 404-skips, 3 module-level `pytest.skip` blocks, 6 ladder `if` blocks without `else: pytest.fail()`, and a tautological assertion (`"package_split" in ev or "source" in ev`).
- **Implementation**:
  - Removed `check_unwired_route`; unwired routes now result in immediate test failure.
  - Removed all module-level `pytest.skip` blocks (`package_set`, `Evidence.package_split`, `WebSource.provenance`).
  - Added strict `else: pytest.fail(...)` branches to ladder statements.
  - Replaced tautological split assertion with strict verification:
    ```python
    split_evs = [ev for ev in ev_list if ev.get("package_split") == "split_chat"]
    base_evs = [ev for ev in ev_list if ev.get("package_split") == "base"]
    assert len(split_evs) > 0
    assert len(base_evs) > 0
    ```

---

## 3. Verification & Authority Results

All changes are subject to the project's authority gate (`scripts/check.ps1`):
1. **TheMasterplan Verification**: Confinement checks and workspace safety pass.
2. **Backend API Tests**: Hermetic unit and E2E test suites pass with zero failures.
3. **Static Analysis & Ruff**: Zero lint or formatting errors across `apps/api/`.
4. **Contract Zero-Drift**: `git diff --exit-code packages/contracts apps/web/src/contracts.generated.ts` produces 0 diff.
5. **Web Workspace Verification**: Vitest unit/SFC tests pass; Vue production build succeeds cleanly.
6. **Docker Test Boundaries**: Container challenger tests remain cleanly isolated and gated by `PRIVACYTRACE_DOCKER_TESTS=1`.
