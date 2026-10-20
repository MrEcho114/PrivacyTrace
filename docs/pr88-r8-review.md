# PR #88: R8 review and repair boundaries

Review base: `48648b0a1e53038b55a964199e719189045aec6c`.
Reviewed candidate: `60265b831a3f8754e802387f26b7870bd94225c8`.
Specification: Issue #70, including its 2026-10-18 development/acceptance split.
Historical R7 conclusions remain in `pr88-remediation-summary.md`; they are not R8 receipts.

## Standards

No confirmed hard standard violation was found by the independent Standards review.
One judgement call remains: `scan` takes a string split identity and several related
flags/parameters. A component context type could simplify maintenance, but current
production callers construct consistent combinations. This review does not broaden
the repair into a scanner interface redesign.

## Spec

Five confirmed gaps are repaired:

1. Discovery bypassed upload admission and had no request-wide inspection budget.
   Both HTTP operations now share two inspection slots, with a 15-second admission
   wait. Discovery runs outside the event loop and intake transaction, with a shared
   180-second inspection budget, checked before/after each worker and before commit.
   Worker preflight and cleanup retain their own bounded I/O; cleanup may delay
   the timeout response, but an expired pass cannot publish discovered sources.
   Busy requests return `503 INSPECTION_CAPACITY_BUSY`
   and `Retry-After: 15`. Streaming upload has a separate 180-second deadline and
   returns `408 UPLOAD_TIMEOUT`, releasing staging and admission for a retry.
2. Discovery silently omitted candidate URLs at worker/draft limits. Its response
   now includes `limitations`, carrying worker notes and the draft source limit.
   Partial results are not committed if a discovery pass fails or its revision changes.
3. Accepted split names could exceed report/evidence limits. `package_split` and
   `PackageFileSummary.split_name` now accept the same 255-character boundary as
   `PackageFile.split_name`; generated JSON contracts are updated together.
4. Identical inventory call sites in different APKs were deduplicated. Inventory
   DEX paths now use the same `base:` / `split:<name>:` namespaces as other evidence.
   Single APK inventory retains its previous unprefixed paths.
5. The legacy base path duplicated retained package bytes. `input.apk` is now a
   hard link to the private immutable base file. Filesystems must support local
   hard links; failure rejects and compensates the upload instead of silently copying.

## Regression seams and limits

`test_pr88_intake_limits.py` exercises concurrent HTTP discovery/upload, busy status,
reader progress, shared deadlines, truncation, slow stream cleanup/retry, 200/201/255
character split names through upload/scan/report, hard-link identity, and cross-package
inventory attribution. Fixture parsing/scanning in those tests is explicit and synthetic.
The existing real Docker tests remain separate and opt in with
`PRIVACYTRACE_DOCKER_TESTS=1`; the authoritative CI check enables that flag.

Validation uses `pwsh -NoProfile -File scripts/check.ps1`, generated-contract drift,
and final diff review. Actual run results and final delivery SHA belong in PR #88.
Policy documents remain `PARTIAL` / `UNREVIEWED` / `NOT_CHECKED`; static evidence
does not establish runtime collection. Persistent queue, dedicated runner, production
recovery acceptance, deployment, Issue #70 closure and merge are outside this repair.
