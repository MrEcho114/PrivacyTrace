# PrivacyTrace Issue #81 (PT-SRV-102) E2E Test Infrastructure Specification

**Document Version:** 1.0.0  
**Author:** test_writer_e2e_1 (E2E Testing Track)  
**Date:** 2026-10-20  
**Target:** Issue #81 (PT-SRV-102), R1–R4, Features F1–F39  
**Execution Root:** `tests/e2e/`  

---

## 1. Test Architecture & Philosophy

The PrivacyTrace E2E test suite adheres to an **opaque-box, requirement-driven, deterministic** testing methodology. It tests system behavior against documented interface contracts and architectural boundaries without reliance on implementation internals or external cloud resources.

### 1.1 Core Principles
1. **Deterministic & Isolated**: Every test creates its own isolated sandbox (using `tmp_path`, ephemeral SQLite/file stores, or mocked services), executes independently of test execution order, and cleans up all generated artifacts.
2. **Self-Contained Fixtures**: Real Android binary XML (AXML) and Dalvik executable (DEX) bytecode are assembled in-memory using `apk_fixture_builder.py` without requiring the Android SDK, Java Development Kit, or live Android Virtual Devices.
3. **Defense-in-Depth Verification**: Validates both the happy paths and defensive perimeter: strict capability token hashing, reverse proxy header stripping, rate limiting, RLS multi-tenant barriers, container sandboxing, monotonic lease fencing, and sensitive credential redaction.
4. **Standardized Test Runner**: Runs cleanly using the project's standard virtual environment and package manager:
   ```bash
   uv run --project apps/api --locked --extra worker pytest tests/e2e -v
   ```

### 1.2 Test Execution Harness Components

```
+----------------------------------------------------------------------------------------------------+
|                                    TEST HARNESS ARCHITECTURE                                       |
|                                                                                                    |
|  [ Test Client: FastAPI TestClient / HTTPX ]                                                       |
|       |                                                                                            |
|       | 1. HTTP / HTTPS Requests (Headers, Bearer Tokens, Multipart Streams, Chunked Bodies)       |
|       v                                                                                            |
|  +----------------------------------------------------------------------------------------------+  |
|  | Caddy / API Boundary Harness                                                                  |  |
|  | - Strips Forwarded / X-Forwarded-* headers; enforces SNI and HSTS                             |  |
|  | - Enforces Pre-Body size limits (150 MiB APK, 8 MiB draft, 512 KiB JSON)                      |  |
|  | - Sliding-window IP rate limiter (60 req/min/IP with Retry-After: 60)                        |  |
|  | - Remote transport security: rejects X-PrivacyTrace-Local, shields /jobs & /web/settings      |  |
|  +----------------------------------------------------------------------------------------------+  |
|       |                                                                                            |
|       | 2. Intake & Package Validation                                                             |
|       v                                                                                            |
|  +----------------------------------------------------------------------------------------------+  |
|  | In-Memory APK / Package Set Builder (`apk_fixture_builder.py` & `conftest.py`)               |  |
|  | - Generates valid binary AXML and DEX with classes, methods, permissions                     |  |
|  | - Generates Base APK + Split APK packages (split_name, dependencies, package homogeneity)    |  |
|  | - Injects corruption: zip bombs, mismatched version_codes, empty files, size quota overruns |  |
|  +----------------------------------------------------------------------------------------------+  |
|       |                                                                                            |
|       | 3. Storage & Outbox Dispatch Pipeline                                                      |
|       v                                                                                            |
|  +----------------------------------------------------------------------------------------------+  |
|  | Transactional Outbox & Execution Lease Harness                                               |  |
|  | - Atomic insert: Job (QUEUED) + snapshot + Outbox event (PENDING)                            |  |
|  | - Claim with SKIP LOCKED, 5-field JSON payload verification                                  |  |
|  | - Monotonic execution fencing (attempt++, fence++, 300s deadline)                            |  |
|  | - Simulated broker failure & exponential backoff retry                                       |  |
|  +----------------------------------------------------------------------------------------------+  |
|       |                                                                                            |
|       | 4. Runner & Scanner Isolation Harness                                                      |
|       v                                                                                            |
|  +----------------------------------------------------------------------------------------------+  |
|  | Dedicated Runner & Docker Sandboxing Simulator                                               |  |
|  | - Validates container inspect parameters: network=none, read_only=true, cap_drop=[ALL]       |  |
|  | - Short-lived HMAC permit ticket (<=300s, re-verified every 1s, revoked upon draft deletion) |  |
|  | - BoundedSemaphore(1) single-concurrency enforcement & backpressure simulation               |  |
|  +----------------------------------------------------------------------------------------------+  |
|       |                                                                                            |
|       | 5. Disaster Recovery & Audit Harness                                                        |
|       v                                                                                            |
|  +----------------------------------------------------------------------------------------------+  |
|  | Backup / Restore & Redaction Harness                                                         |  |
|  | - Atomic PTBACKUP1 HMAC-SHA256 binary container format validation                           |  |
|  | - Deletion journal (deletions.jsonl) replay across restore to prevent data resurrection     |  |
|  | - Log audit: verifies TokenRedactionFilter masks pt_cap_*** across all logging levels        |  |
|  +----------------------------------------------------------------------------------------------+  |
+----------------------------------------------------------------------------------------------------+
```

---

## 2. 4-Tier Test Case Design Methodology

The test suite is structured into four distinct, cumulative testing tiers:

### Tier 1: Feature Coverage (Unit / Functional Interface Contracts)
- **Objective**: Verify that every individual feature (F1 through F39 across R1–R4) operates according to its specification.
- **Coverage**: At least 5 distinct test cases per major requirement area (R1, R2, R3, R4), covering:
  - R1: Multi-service compose, immutable image digests, database migration head `>= 0080_05`, container hardening, secret-file loading, preflight checks, migration bootstrapping, health probes, and static assets.
  - R2: Caddy HTTPS edge rules, capability token generation/storage, single APK flow, base+splits flow, cross-scope/instance isolation, management shielding, request size limits, rate limiting, and trusted CIDR routing.
  - R3: Control plane Docker prohibition, dedicated runner isolation, scanner container sandboxing, private mTLS 1.3, HMAC tickets, outbox finite retries, fenced leases, restart recovery, orphan container cleanup, atomic backups, deletion replay, service updates, and credential rotation.
  - R4: Concurrency 1 capacity benchmarking, execution timing telemetry, resource peak telemetry, backpressure characterization, "NOT TESTED" scope declarations, and log token redaction.

### Tier 2: Boundary & Corner Cases (Limits, Stress & Malformations)
- **Objective**: Push parameters to extreme boundaries and invalid combinations to verify fail-closed security and precise HTTP error codes.
- **Scenarios**:
  - Exact 150 MiB limit: 157,286,400 bytes accepted, 157,286,401 bytes rejected with HTTP 413.
  - Empty split APK (0 bytes) and oversized split (>150 MiB) rejected with HTTP 400/413.
  - Zero splits vs. >100 splits (101 splits rejected with HTTP 400).
  - Execution timeouts: 180s scanner timeout, 300s hard lease timeout, 300s material ticket expiration.
  - Zip bomb defense: uncompressed size > 512 MiB, > 20,000 zip entries, compression ratio > 100x rejected.
  - Malformed capability tokens: missing `pt_cap_` prefix, invalid characters, base64 padding errors, SQL injection payloads (`' OR 1=1 --`), null bytes, control characters.
  - Disrupted network streams: client disconnects mid-upload, gateway disconnects during download.
  - Header attacks: spoofed `X-PrivacyTrace-Local`, untrusted `X-Forwarded-For`, missing Host, invalid IPv6.

### Tier 3: Cross-Feature Combinations (Pairwise Interaction Stress)
- **Objective**: Test asynchronous race conditions, failover cascades, and multi-component state interactions.
- **Scenarios**:
  - **Splits + Broker Failure & Retry**: Base+splits package set intake during Redis broker downtime; verified outbox exponential backoff; clean delivery and split attribution once broker recovers.
  - **Outbox Monotonic Fencing + Worker Crash Race**: Worker 1 leases job with fence=1; Worker 1 halts; lease expires; Worker 2 recovers job with fence=2; Worker 1 resumes and attempts report commit; Worker 1 receives `LeaseLost`; Worker 2 successfully completes.
  - **Capability Token Scoping + Sliding-Window Rate Limiting**: Token-authenticated calls subjected to 60 req/min limit; verified 429 Retry-After response; verified tokens are never leaked in rate-limiting logs or headers.
  - **Runner Sandboxing + Material Revocation Mid-Flight**: Draft deletion executed while scan container is running; HMAC ticket is revoked; runner material re-verification fails; late results discarded.
  - **Deletion Journal Replay + Backup Restore + Active Leases**: Snapshot backup taken; user deletes draft; backup restored; deletion journal replayed; draft confirmed deleted; active leases invalidated.
  - **Secret Rotation + Active Pipeline Execution**: Database credentials rotated on disk while jobs are processing; pool reconnects seamlessly without dropping in-flight executions.

### Tier 4: Real-World Application Scenarios (End-to-End User Journeys)
- **Objective**: Simulate end-to-end, multi-stage, real-world user journeys mirroring production workflows.
- **Scenarios**:
  1. **Realistic Single APK Analysis Journey**: Draft creation -> single APK upload -> privacy policy attachment -> start analysis -> outbox dispatch -> runner scan -> report retrieval -> verification of findings.
  2. **Realistic Base + Feature Splits Multi-Package Journey**: Draft creation -> base + 3 feature splits upload -> DAG and homogeneity validation -> unified analysis -> attribution of findings to specific split origins in report.
  3. **End-to-End Worker Crash Recovery Journey**: In-flight scan interrupted by sudden worker failure -> lease expiration detection -> automatic retry rescheduling -> second worker execution -> successful completion.
  4. **Multi-Tenant Zero-Leakage Scope Isolation Journey**: Two concurrent unauthenticated tenants (Tenant A and Tenant B) creating drafts, uploading APKs, and polling reports -> all cross-tenant access attempts receive 403 Forbidden or 404 Not Found -> zero cross-talk in logs.
  5. **Capacity Saturation & Ordered Backpressure Journey**: 4 concurrent jobs submitted under `concurrency=1` -> Job 1 executes while Jobs 2-4 queue -> FIFO execution completion -> telemetry logs verify queue delay and peak resource tracking.

---

## 3. Requirement-to-Test Mapping Matrix (F1 to F39)

| Feature ID | Description | Milestone | Test File | Test Identifier |
|---|---|---|---|---|
| **F1** | Multi-service Compose Control Plane | M1 | `test_tier1_r1_deployment.py` | `test_f1_compose_service_topology` |
| **F2** | Immutable Image Digest Pinning | M1 | `test_tier1_r1_deployment.py` | `test_f2_immutable_image_digests` |
| **F3** | Database Migration Packaging (>= 0080_05) | M1 | `test_tier1_r1_deployment.py` | `test_f3_database_migration_packaging` |
| **F4** | Container Security Hardening | M1 | `test_tier1_r1_deployment.py` | `test_f4_container_security_hardening` |
| **F5** | File-Mounted Secret Ingestion | M1 | `test_tier1_r1_deployment.py` | `test_f5_file_mounted_secret_ingestion` |
| **F6** | Preflight Validator Upgrade | M1 | `test_tier1_r1_deployment.py` | `test_f6_preflight_validator_contract` |
| **F7** | Single-Run Migration Bootstrap | M1 | `test_tier1_r1_deployment.py` | `test_f7_single_run_migration_bootstrap` |
| **F8** | Liveness & Readiness Probes | M1 | `test_tier1_r1_deployment.py` | `test_f8_liveness_readiness_probes` |
| **F9** | Front-End & Assets Availability | M1 | `test_tier1_r1_deployment.py` | `test_f9_frontend_assets_availability` |
| **F10** | Caddy HTTPS Reverse Proxy | M2 | `test_tier1_r2_business_loop.py` | `test_f10_caddy_https_reverse_proxy` |
| **F11** | Capability Token Lifecycle | M2 | `test_tier1_r2_business_loop.py` | `test_f11_capability_token_lifecycle` |
| **F12** | HTTPS End-to-End Execution | M2 | `test_tier1_r2_business_loop.py` | `test_f12_https_e2e_pipeline_execution` |
| **F13** | Single APK Analysis Flow | M2 | `test_tier1_r2_business_loop.py` | `test_f13_single_apk_analysis_flow` |
| **F14** | Base + Splits Analysis Flow | M2 | `test_tier1_r2_business_loop.py` | `test_f14_base_splits_analysis_flow` |
| **F15** | Cross-Scope & Instance Isolation | M2 | `test_tier1_r2_business_loop.py` | `test_f15_cross_scope_and_instance_isolation` |
| **F16** | Management Surface Shielding | M2 | `test_tier1_r2_business_loop.py` | `test_f16_management_surface_shielding` |
| **F17** | Request Quotas & Limits | M2 | `test_tier1_r2_business_loop.py` | `test_f17_request_quotas_and_limits` |
| **F18** | Rate Limiting & 429 Retry-After | M2 | `test_tier1_r2_business_loop.py` | `test_f18_rate_limiting_and_retry_after` |
| **F19** | Malicious Source & CIDR Protection | M2 | `test_tier1_r2_business_loop.py` | `test_f19_malicious_source_cidr_protection` |
| **F20** | Control Plane Docker Prohibition | M3 | `test_tier1_r3_isolation_faults.py` | `test_f20_control_plane_docker_prohibition` |
| **F21** | Dedicated Scan Plane Isolation | M3 | `test_tier1_r3_isolation_faults.py` | `test_f21_dedicated_scan_plane_isolation` |
| **F22** | Scanner Container Sandboxing | M3 | `test_tier1_r3_isolation_faults.py` | `test_f22_scanner_container_sandboxing` |
| **F23** | Private mTLS 1.3 Transport | M3 | `test_tier1_r3_isolation_faults.py` | `test_f23_private_mtls_transport` |
| **F24** | Short-Lived HMAC Material Tickets | M3 | `test_tier1_r3_isolation_faults.py` | `test_f24_short_lived_hmac_tickets` |
| **F25** | Outbox Finite Retry & Late Discard | M3 | `test_tier1_r3_isolation_faults.py` | `test_f25_outbox_finite_retry_late_discard` |
| **F26** | Fenced Lease Execution | M3 | `test_tier1_r3_isolation_faults.py` | `test_f26_fenced_lease_execution` |
| **F27** | Component Restart Fault Injection | M3 | `test_tier1_r3_isolation_faults.py` | `test_f27_component_restart_fault_injection` |
| **F28** | Orphan Container Cleanup | M3 | `test_tier1_r3_isolation_faults.py` | `test_f28_orphan_container_cleanup` |
| **F29** | Consistent Backup & Restore | M3 | `test_tier1_r3_isolation_faults.py` | `test_f29_consistent_backup_restore` |
| **F30** | Deletion Journal Replay | M3 | `test_tier1_r3_isolation_faults.py` | `test_f30_deletion_journal_replay` |
| **F31** | Service Update & Rollback | M3 | `test_tier1_r3_isolation_faults.py` | `test_f31_service_update_and_rollback` |
| **F32** | Credential & Certificate Rotation | M3 | `test_tier1_r3_isolation_faults.py` | `test_f32_credential_rotation` |
| **F33** | Controlled Capacity Benchmarking | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f33_controlled_capacity_concurrency_one` |
| **F34** | Execution Timing Telemetry | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f34_execution_timing_telemetry` |
| **F35** | Resource Peak Telemetry | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f35_resource_peak_telemetry` |
| **F36** | Queue & Backpressure Behavior | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f36_queue_and_backpressure_behavior` |
| **F37** | Declared Scope Boundaries | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f37_declared_scope_boundaries_unmeasured` |
| **F38** | Token Redaction in Logs | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f38_token_redaction_in_logs` |
| **F39** | Comprehensive Redaction Audit | M4 | `test_tier1_r4_capacity_redaction.py` | `test_f39_comprehensive_redaction_audit` |

---

## 4. Test File Structure & Execution

The test suite files are organized cleanly under `tests/e2e/`:

```
tests/e2e/
├── __init__.py
├── conftest.py
├── test_tier1_r1_deployment.py          # Features F1 - F9 (>=9 tests)
├── test_tier1_r2_business_loop.py        # Features F10 - F19 (>=10 tests)
├── test_tier1_r3_isolation_faults.py     # Features F20 - F32 (>=13 tests)
├── test_tier1_r4_capacity_redaction.py   # Features F33 - F39 (>=7 tests)
├── test_tier2_boundaries.py              # Tier 2 Boundary, Limit & Malformed Tests
├── test_tier3_combinations.py            # Tier 3 Cross-Feature Interaction & Stress Tests
└── test_tier4_scenarios.py               # Tier 4 Realistic End-to-End User Scenarios
```

To run all E2E tests:
```bash
uv run --project apps/api --locked --extra worker pytest tests/e2e -v
```

To run a specific tier:
```bash
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier1_r1_deployment.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier2_boundaries.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier3_combinations.py -v
uv run --project apps/api --locked --extra worker pytest tests/e2e/test_tier4_scenarios.py -v
```
