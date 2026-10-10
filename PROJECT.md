# Project: PrivacyTrace Architecture Baseline & M1 Decomposition

## Architecture
- **Overall Purpose**: App privacy health check and compliance verification tool for everyday Android users.
- **Data Flow**:
  1. Low-level Evidence Extraction (Androguard for Manifest & DEX bytecode, JADX for code locator and excerpt).
  2. Multi-source Policy Snapshot & LLM Extraction (In-app, App store, Official web, SDK policy -> text chunks -> structured PolicyClaims with strict snapshot SHA-256 validation).
  3. Unified Privacy Taxonomy Mapping (14 hierarchical data types in DAG, 5 permission mappings, API signatures, 12 policy phrase mappings).
  4. Standard Evidence Model Assembly (Strict separation: Fact is `STATIC_POTENTIAL` with `purpose="UNKNOWN"`; Declaration is `DECLARED` with policy text excerpt and document ID).
  5. Deterministic Consistency Engine (6 deterministic match states: `EXACT_MATCH`, `CATEGORY_MATCH`, `AMBIGUOUS_DISCLOSURE`, `NOT_DECLARED`, `POLICY_SOURCE_CONFLICT`, `INSUFFICIENT_EVIDENCE`).
  6. Explainable Report & 2-Step Drill-down (Plain-language cards -> Consistency matrix -> Drill-down panel to raw code line & policy sentence).

## Feature Inventory
| # | Feature | Description | Milestone | Source |
|---|---------|-------------|-----------|--------|
| 1 | Architecture Baseline & Plain-language Briefing | Comprehensive "人话白话速读指南" and open-source tool boundary matrix in `docs/development-plan.md` | M1 | ORIGINAL_REQUEST R1 |
| 2 | Open-source Tool Decoupling & Boundary Definition | Complete technical boundary analysis for Androguard, JADX, FlowDroid, MobSF preventing simple wrapping | M1 | ORIGINAL_REQUEST R1, R2 |
| 3 | Core Self-developed Asset Protection | Clarify & preserve Taxonomy, Evidence Model, Consistency Engine, and Drill-down Layer as independent proprietary assets | M1 | ORIGINAL_REQUEST R2 |
| 4 | M1 10-Issue End-to-End Breakdown | 10 GitHub Issues adhering to `.github/ISSUE_TEMPLATE/task.yml` and `docs/milestone-1.md` | M2 | ORIGINAL_REQUEST R3 |
| 5 | Task Issue Persistence | Update `docs/development-plan.md` and/or generate issue task templates for PT-101 ~ PT-807 | M2 | ORIGINAL_REQUEST R3 |
| 6 | Automated Regression Suite (35 tests) | Maintain 100% pass rate (`uv run --project apps/api --locked pytest`) | M3 | ORIGINAL_REQUEST R4 |
| 7 | Contract Synchronization Verification | Execute `scripts/export-schema.py` and ensure JSON Schema sync with frontend models | M3 | ORIGINAL_REQUEST R4 |

## Milestones
| # | Name | Scope | Dependencies | Status |
|---|------|-------|-------------|--------|
| 1 | M1: Architecture & Development Plan (`docs/development-plan.md`) | Solidify architecture baseline, plain-language briefing ("人话白话速读指南"), tool boundary matrix (Androguard, JADX, FlowDroid, MobSF), core asset decoupling in `docs/development-plan.md` | Survey completed | PLANNED |
| 2 | M2: Milestone 1 10-Issue Task Decomposition | Embed the 10 structured task issues (PT-101, PT-104, PT-301, PT-503, PT-506, PT-203, PT-306, PT-701, PT-708, PT-807) conforming to `.github/ISSUE_TEMPLATE/task.yml` and `docs/milestone-1.md` into `docs/development-plan.md` and project task docs | M1 | PLANNED |
| 3 | M3: Quality Assurance & Contract Sync | Run full backend regression (35 pytest tests pass) and run `scripts/export-schema.py` to ensure zero contract drift | M1, M2 | PLANNED |

## Interface Contracts
### Raw Reverse-Engineering ↔ Evidence Model
- Androguard / JADX output transformed into `Evidence(kind="API"/"MANIFEST", status="STATIC_POTENTIAL", locator="...", excerpt="...")`.
- No direct dependency or import of Androguard/JADX in `consistency.py`.

### Policy Snapshot ↔ Policy Claim
- Policy snapshot hashed with SHA-256 (`PolicyDocument.sha256`).
- Policy claims link to sentences: `sentence.excerpt in document.text`.

### Evaluation Input ↔ Consistency Engine
- Signature: `evaluate(bundle: EvaluationInput) -> EvaluationResult`.
- Pure deterministic function outputting 6 states.

## Code Layout
- `docs/development-plan.md`: Comprehensive development plan, plain-language briefing, tool boundary matrix, M1 10-issue task list.
- `docs/milestone-1.md`: Milestone 1 real-world sample acceptance criteria.
- `apps/api/src/privacytrace/`: Backend models, consistency engine, API routes.
- `apps/api/tests/`: Pytest test suite (35 tests).
- `packages/contracts/`: JSON Schemas exported by `scripts/export-schema.py`.
- `apps/web/`: Frontend Vue 3 application.
