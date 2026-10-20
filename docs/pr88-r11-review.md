# PR #88: R11 discovered-source identity and input-error boundaries

Repair base: `a753a633c74b4899f389d0c6099ffa017b615a1a`.
Specification: Issue #70 / PT-MOB-102, under its development/acceptance split.
R8-R10 records retain their original candidates and validation receipts.

## Independent review findings

A Standards pass and a Spec pass reviewed the R10 candidate separately. Three
confirmed defects and three coverage/record gaps were found:

1. Auto-discovered sources took their package scope from a draft key that does
   not exist. `package_name` was always empty and `version_code` always `None`,
   so discovered policy documents evaluated as `UNKNOWN` applicability instead
   of the uploaded package. The fix derives the scope from the registered
   package set, falling back to the isolated worker's `package_file` metadata
   for the legacy single-APK lane. Client-supplied source fields remain
   untouched; only newly discovered server sources receive the derived scope.
2. A malformed split dependency reached `POST /package-set` as HTTP 503
   `ISOLATED_INSPECTION_UNAVAILABLE` through the real worker. The worker
   serialises `INVALID_SPLIT_DEPENDENCY`; the intake remapped only three other
   structured codes. The same fault reached the legacy `/apk` discovery lane
   because `/apk` accepts the manifest unparsed and the discovery endpoint
   classified every `ScanError` as a service fault. Both lanes now use one
   structured input-code set (and the in-process `PackageSetIntegrityError`
   shape) before falling back to 503; genuine transport/isolation faults remain
   503.
3. The report and live source panels rendered an empty label for a source status
   outside the current union. Both now fall back to `未知状态`, restoring the
   documented behaviour; the component test renders an unknown status.

Coverage and record repairs:

- The R10 registered-versus-scanned package-set identity guard had no test that
  failed when the guard was removed. A tampered registered split hash now
  produces a failed job with `INPUT_DIGEST_MISMATCH`, while an untouched set
  still succeeds.
- The two-APK discovery budget was only exercised on its expiry path. A
  controlled clock now proves the second APK receives the remaining budget
  (`[10, 8]` seconds) rather than a fresh allowance.
- `docs/test-infra.md` now names the real admission primitive and package-set
  error code; `docs/pr88-remediation-summary.md` cites the existing F29 test;
  `docs/architecture.md` records the PT-MOB-102 endpoints and boundaries; and
  `GLOSSARY.md` defines package set, package split and source provenance.

## Regression evidence

New cases in `test_pr88_evidence_integrity.py`:

- discovered-source identity for a single APK and for a package set, both
  inspected through the real metadata fixture rather than a shape the worker
  never emits;
- stubbed isolated `INVALID_SPLIT_DEPENDENCY` rejection with no draft change or
  staging residue, for both the package-set upload and the single-APK discovery
  lane;
- the in-process fixture parser's `PackageSetIntegrityError` maps to the same
  4xx classification on discovery;
- opt-in real-worker malformed-dependency uploads returning 400 on both lanes;
- registered package-set identity: falsified control when the guard was forced
  to accept (the tampered case then succeeded, so the assertion failed), and
  restored when the guard ran.

`test_pr88_intake_limits.py` adds the successful shared-budget case. The new
cases fail against the R10 candidate where the defect applies: discovery identity
and unknown-status rendering fail on the old code, restoring the old three-code
remap reproduces the real-worker 503, and forcing the identity guard open makes
the tampered-set case publish instead of failing.

Authoritative validation used
`PRIVACYTRACE_DOCKER_TESTS=1 pwsh -NoProfile -File scripts/check.ps1` semantics
through the same Git Bash entry point: 1425 tests passed, 60 skipped, the web
suite passed 52/52, and the production web build succeeded. The worker image was
rebuilt from this candidate before the Docker-gated cases ran.

## Main history reattribution

Upstream `main` was rewritten with an identical tree while this review was in
progress. The PR branch was replayed onto the rewritten main so the pull request
diffs only its own changes; the resulting tree equals the validated R11
candidate `9cb45d0`. No code or evidence semantics changed.

## Limits

These remain constructed APK/metadata fixtures and controlled fetch responses;
they do not prove third-party app behaviour, policy authenticity, full Android
installability or runtime collection. Package-set identity binds only the files
supplied in the upload. Persistent queues, dedicated runners and cross-instance
recovery remain Issue #80. This record does not authorize merge, deployment or
Issue #70 closure.
