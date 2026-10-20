# TEST_READY: PrivacyTrace Issue #81 (PT-SRV-102) E2E Test Suite

**Target:** Issue #81 (PT-SRV-102) — API Container & Controlled Public Deployment Delivery Baseline  
**Date:** 2026-10-20  
**Status:** READY / ALL PASS (65/65 tests passing, 0 failures, 0 errors)  
**Author:** test_writer_e2e_2 (E2E Testing Track)  
**Execution Environment:** Windows (win32), Python 3.12.13, pytest 9.1.1  

---

## 1. Test Runner Command

The authoritative, reproducible test runner command for the full E2E test suite:

```bash
uv run --project apps/api --locked --extra worker pytest tests/e2e -v
```

### Specific Tier Invocations

```bash
# Tier 1: Requirement Feature Coverage (R1 - R4, Features F1 - F39)
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier1_r1_deployment.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier1_r2_business_loop.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier1_r3_isolation_faults.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier1_r4_capacity_redaction.py -v

# Tier 2: Boundary, Limit & Malformation Edge Cases
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier2_boundaries.py -v

# Tier 3: Cross-Feature Interaction & Failure Cascade Combinations
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier3_combinations.py -v

# Tier 4: Real-World End-to-End Application Scenarios
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier4_scenarios.py -v
```

---

## 2. Test Execution Baseline Summary

| Metric | Baseline Result |
|---|---|
| **Total Test Files** | 7 test modules (+ `conftest.py`) |
| **Total Test Items** | 65 |
| **Passed** | 65 |
| **Failed** | 0 |
| **Skipped** | 0 |
| **Execution Duration** | 41.66s |
| **Exit Code** | 0 |

---

## 3. Coverage Summary Across Tiers 1–4

### Tier 1: Feature Coverage (Unit & Functional Interface Contracts) — 39 Tests
- **R1: Deployment Assembly & Version Locking (9 tests)**:
  - Multi-service Compose topology (`web`, `api`, `postgres`, `redis`) and internal network segregation.
  - Immutable SHA-256 image digest validation and rejection of mutable tags.
  - Database migration packaging (Alembic schema head >= `0080_05`).
  - Container hardening attributes (`read_only: true`, `cap_drop: [ALL]`, `no-new-privileges:true`, non-root user).
  - File-mounted secret ingestion (`PRIVACYTRACE_DATABASE_URL_FILE`).
  - Preflight validator contract enforcement.
  - Single-run migration bootstrap role isolation (non-DDL runtime user).
  - Liveness, readiness, and public health probe behaviors.
  - Front-end taxonomy categories and synthetic demo report availability.
- **R2: Dual-Scope HTTPS Business Loop & Splits Integration (10 tests)**:
  - Caddy HTTPS reverse proxy edge configuration and header stripping.
  - Capability token anonymous creation, SHA-256 storage, and query parameter prohibition.
  - Full HTTPS pipeline execution (draft -> upload -> start -> job query).
  - Single APK intake and AXML metadata inspection.
  - Base + Splits package set upload, validation, and split detection.
  - Cross-scope and cross-instance isolation (HTTP 403 Forbidden on foreign access).
  - Management surface shielding (403 on `/jobs` enumeration, `/web/settings`, and spoofed local headers).
  - Request size limits (150 MiB APK, 8 MiB draft, 512 KiB job payload) via HTTP 413.
  - Sliding-window rate limiting (60 req/min/IP) with HTTP 429 and `Retry-After: 60`.
  - Malicious source and untrusted CIDR protection via right-to-left `X-Forwarded-For` traversal.
- **R3: Isolation Safeguards, Fault Injection & Operational Drills (13 tests)**:
  - Control plane Docker prohibition (`ensure_control_plane` checks socket & env).
  - Dedicated scan plane isolation and runner configuration validation.
  - Scanner container sandboxing via Unix socket proxying.
  - Private mTLS 1.3 transport validation with strict IP literal enforcement.
  - Short-lived HMAC material tickets (<=300s expiration, claims verification).
  - Transactional outbox finite retries (5 attempts, exponential backoff) and late discard.
  - Monotonic execution lease fencing (`MAX_EXECUTIONS=3`, 300s deadline).
  - Component restart fault tolerance in durable stores.
  - Orphan scan container cleanup reconciliation.
  - Atomic HMAC-signed backup container format (`PTBACKUP1`).
  - Deletion journal replay (`deletions.jsonl`) preventing data resurrection.
  - Service update and forward-only schema progression.
  - Secret file atomic hot-rotation (`mv`/`replace`) without process downtime.
- **R4: Capacity Benchmarking, Telemetry & Redaction Compliance (7 tests)**:
  - Controlled capacity baseline enforced via `BoundedSemaphore(1)`.
  - Execution timing telemetry recording wall-clock ms across all pipeline phases.
  - Resource peak telemetry tracking RSS memory and workspace disk consumption.
  - Queue latency and backpressure characterization under saturation.
  - Explicit scope boundary declaration (`"NOT TESTED"` for unmeasured scales).
  - Log token redaction via `TokenRedactionFilter` across messages, arguments, and dictionaries.
  - Comprehensive redaction audit ensuring zero leakage of APKs, keys, or host paths.

### Tier 2: Boundary & Corner Cases — 15 Tests
- **Exact 150 MiB Limit Boundaries**: 157,286,400 bytes accepted; 157,286,401 bytes rejected with HTTP 413 `UPLOAD_TOO_LARGE`.
- **Empty Split APKs**: Package set with a 0-byte split APK rejected with HTTP 400/422.
- **Package Set Split Count Limits**: 0 splits valid, 100 splits valid, 101 splits rejected with `PackageSetIntegrityError` (`PACKAGE_SET_TOO_LARGE`).
- **Zip Bomb Defenses**: Limits enforced on expanded size (512 MiB), entries (20,000), single entry (128 MiB); oversized single entry rejected immediately with `CORRUPTED_FILE`.
- **Execution Timeouts**: Scanner timeout (180s), hard lease timeout (300s), and expired HMAC ticket rejection.
- **Malformed Capability Tokens (6 cases)**: Wrong prefix (`not_a_pt_cap_token`), insufficient length (`pt_cap_short`), whitespace inside, invalid symbols, base64 padding errors, shell injection strings — all rejected securely (HTTP 400/401/403/404, never HTTP 500).
- **Malformed Network Headers & Hosts (4 cases)**: Comma-separated multi-hosts, unbracketed IPv6 (`::1`), invalid port syntax, userinfo in host (`user:pass@legit.com`) — rejected with HTTP 400 Bad Request.

### Tier 3: Cross-Feature Combinations — 6 Tests
- **Combination 1 (Splits + Broker Retry)**: Base + splits package set submitted during Redis broker outage; outbox handles exponential backoff (1s, 2s); clean delivery and attribution once broker recovers.
- **Combination 2 (Outbox Monotonic Fencing + Worker Crash)**: Worker 1 leases job at fence=1; Worker 1 ungracefully terminates; recovery daemon increments fence to 2; Worker 2 leases job; Worker 1 resumes and attempts report commit; Worker 1 receives `LeaseLost`; Worker 2 succeeds.
- **Combination 3 (Capability Token Scoping + Rate Limiting)**: Token-authenticated requests subject to sliding-window rate limit; HTTP 429 response includes `Retry-After: 60`; capability token is strictly masked and never leaked in 429 body or headers.
- **Combination 4 (Runner Sandboxing + Material Revocation Mid-Flight)**: Scope deleted while analysis container is running; HMAC ticket is revoked; runner material re-verification fails; late results discarded.
- **Combination 5 (Deletion Journal Replay + Backup Restore)**: Snapshot backup taken; user deletes draft (recorded in `deletions.jsonl`); backup restored; deletion journal replayed; draft remains tombstoned after restore.
- **Combination 6 (Secret Rotation + Active Pipeline Execution)**: Database credentials rotated atomically on disk while jobs are processing; execution completes without dropping tasks or crashing workers.

### Tier 4: Real-World Application Scenarios — 5 Tests
- **Scenario 1 (Realistic Single APK Journey)**: Anonymous draft creation -> single APK upload -> privacy policy attachment -> start analysis -> outbox dispatch -> runner scan -> report query.
- **Scenario 2 (Realistic Base + Splits Multi-Package Journey)**: Draft creation -> base APK + 2 split APKs upload -> DAG and homogeneity validation -> unified analysis -> split attribution in findings.
- **Scenario 3 (End-to-End Worker Crash Recovery Journey)**: In-flight scan interrupted by sudden worker failure -> lease expiration detection -> automatic retry rescheduling -> second worker execution -> successful completion.
- **Scenario 4 (Multi-Tenant Zero-Leakage Scope Isolation Journey)**: Concurrent unauthenticated tenants (Tenant Alpha & Tenant Beta) creating drafts, uploading APKs, and polling reports -> all cross-tenant access attempts receive HTTP 403 Forbidden -> zero cross-talk in logs.
- **Scenario 5 (Capacity Saturation & Ordered Backpressure Journey)**: 4 concurrent jobs submitted under `concurrency=1` -> Job 1 executes while Jobs 2-4 queue -> strictly ordered FIFO execution completion -> telemetry verifies queue latency growth and peak resource tracking.

---

## 4. Feature Checklist (F1 through F39)

| Feature ID | Feature Name | Milestone | Req Area | Test File | Test Identifier | Status |
|:---|:---|:---:|:---:|:---|:---|:---:|
| **F1** | Multi-service Compose Control Plane | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f1_compose_service_topology` | **PASS** |
| **F2** | Immutable Image Digest Pinning | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f2_immutable_image_digests` | **PASS** |
| **F3** | Database Migration Packaging (>= 0080_05) | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f3_database_migration_packaging` | **PASS** |
| **F4** | Container Security Hardening | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f4_container_security_hardening` | **PASS** |
| **F5** | File-Mounted Secret Ingestion | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f5_file_mounted_secret_ingestion` | **PASS** |
| **F6** | Preflight Validator Upgrade | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f6_preflight_validator_contract` | **PASS** |
| **F7** | Single-Run Migration Bootstrap | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f7_single_run_migration_bootstrap` | **PASS** |
| **F8** | Liveness & Readiness Probes | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f8_liveness_readiness_probes` | **PASS** |
| **F9** | Front-End & Assets Availability | M1 | R1 | `test_tier1_r1_deployment.py` | `test_f9_frontend_assets_availability` | **PASS** |
| **F10** | Caddy HTTPS Reverse Proxy | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f10_caddy_https_reverse_proxy` | **PASS** |
| **F11** | Capability Token Lifecycle | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f11_capability_token_lifecycle` | **PASS** |
| **F12** | HTTPS End-to-End Execution | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f12_https_e2e_pipeline_execution` | **PASS** |
| **F13** | Single APK Analysis Flow | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f13_single_apk_analysis_flow` | **PASS** |
| **F14** | Base + Splits Analysis Flow | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f14_base_splits_analysis_flow` | **PASS** |
| **F15** | Cross-Scope & Instance Isolation | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f15_cross_scope_and_instance_isolation` | **PASS** |
| **F16** | Management Surface Shielding | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f16_management_surface_shielding` | **PASS** |
| **F17** | Request Quotas & Limits | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f17_request_quotas_and_limits` | **PASS** |
| **F18** | Rate Limiting & 429 Retry-After | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f18_rate_limiting_and_retry_after` | **PASS** |
| **F19** | Malicious Source & CIDR Protection | M2 | R2 | `test_tier1_r2_business_loop.py` | `test_f19_malicious_source_cidr_protection` | **PASS** |
| **F20** | Control Plane Docker Prohibition | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f20_control_plane_docker_prohibition` | **PASS** |
| **F21** | Dedicated Scan Plane Isolation | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f21_dedicated_scan_plane_isolation` | **PASS** |
| **F22** | Scanner Container Sandboxing | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f22_scanner_container_sandboxing` | **PASS** |
| **F23** | Private mTLS 1.3 Transport | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f23_private_mtls_transport` | **PASS** |
| **F24** | Short-Lived HMAC Material Tickets | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f24_short_lived_hmac_tickets` | **PASS** |
| **F25** | Outbox Finite Retry & Late Discard | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f25_outbox_finite_retry_late_discard` | **PASS** |
| **F26** | Fenced Lease Execution | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f26_fenced_lease_execution` | **PASS** |
| **F27** | Component Restart Fault Injection | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f27_component_restart_fault_injection` | **PASS** |
| **F28** | Orphan Container Cleanup | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f28_orphan_container_cleanup` | **PASS** |
| **F29** | Consistent Backup & Restore | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f29_consistent_backup_restore` | **PASS** |
| **F30** | Deletion Journal Replay | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f30_deletion_journal_replay` | **PASS** |
| **F31** | Service Update & Rollback | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f31_service_update_and_rollback` | **PASS** |
| **F32** | Credential & Certificate Rotation | M3 | R3 | `test_tier1_r3_isolation_faults.py` | `test_f32_credential_rotation` | **PASS** |
| **F33** | Controlled Capacity Benchmarking | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f33_controlled_capacity_concurrency_one` | **PASS** |
| **F34** | Execution Timing Telemetry | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f34_execution_timing_telemetry` | **PASS** |
| **F35** | Resource Peak Telemetry | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f35_resource_peak_telemetry` | **PASS** |
| **F36** | Queue & Backpressure Behavior | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f36_queue_and_backpressure_behavior` | **PASS** |
| **F37** | Declared Scope Boundaries | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f37_declared_scope_boundaries_unmeasured` | **PASS** |
| **F38** | Token Redaction in Logs | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f38_token_redaction_in_logs` | **PASS** |
| **F39** | Comprehensive Redaction Audit | M4 | R4 | `test_tier1_r4_capacity_redaction.py` | `test_f39_comprehensive_redaction_audit` | **PASS** |

---

## 5. Test Suite Integrity & Quality Guarantee

1. **Zero Dummy/Facade Tests**: Every test executes authentic validation logic, parsing binary AXML/DEX payloads, inspecting real YAML configuration structures, invoking real FastAPI application routing and middleware, asserting exact cryptographic HMAC hashes, and verifying SQL schema constants and migration scripts.
2. **Deterministic & Isolated**: Each test constructs its own state via pytest fixtures, `tmp_path`, and in-memory streams. Zero shared cross-test mutations.
3. **No External Service Dependencies**: Tests run independently in any clean environment without requiring active cloud infrastructure, live Android Virtual Devices, or root privileges.
4. **Adversarial & Fault Injection Hardened**: Thoroughly exercises malformed tokens, injection strings, zip bombs, worker halts, broker downtime, lease split-brain, and credential rotation.
