# PR #88: R9 intake cancellation and inspection deadlines

Repair base: `40ea2d70757610cf639e40d16b9dad7233fefd9d`.
Specification: Issue #70, including its 2026-10-18 development/acceptance split.
R8 and earlier records retain their original candidates and validation receipts.

## Inspection budget

Package uploads recheck the shared inspection deadline after each metadata worker,
before publishing package files or the legacy input path, and inside the draft
transaction before saving the upload. Late worker results cannot register an
expired package set. An expiration after a filesystem publication follows the
existing compensation path: remove only this request's published material, leave
the draft unchanged, release its reservation and allow another upload attempt.
The HTTP error remains `503 ISOLATED_INSPECTION_UNAVAILABLE`.

The separate streaming timeout remains `408 UPLOAD_TIMEOUT`. Worker preflight,
cleanup and owned disk I/O must finish before their files can safely be removed;
the deadline does not promise that cleanup ends at the same wall-clock instant.

## Cancellation ownership

Upload writes, flush/fsync, upload inspection/commit and source discovery use one
worker-wait helper. Its executor future is shielded from native asyncio task
cancellation, and its wait is shielded from AnyIO cancellation scopes. A cancelled
caller continues waiting for its already-started synchronous operation, including
after repeated native cancellation. The helper consumes the worker's result or
exception and then propagates any native caller cancellation. It copies context
variables to preserve the previous worker-call behavior. Cancellation checkpoints
before starting work and after leaving the shield deliver pending AnyIO cancellation
before returning either a worker result or an error.

Inspection admission, active-draft protection, file handles and staging paths
remain owned until that wait finishes. The default asyncio executor is separate
from the two analysis workers; the existing two inspection slots continue to
bound uploads and discovery across requests.

Cancellation during streaming or flushing rolls back the incomplete upload.
Cancellation during a synchronous inspection/commit waits for that operation to
commit or roll back before propagating; a caller can read the draft to learn the
stored outcome. This does not change analysis-job cancellation or deletion rules.

## Regression evidence and limits

The first eight added cases failed against the repair base while the previous
fourteen cases passed. Two later AnyIO cancellation-delivery cases also failed
before adding the post-shield checkpoint. The repaired intake suite has 26 passing
cases, including disk-I/O and AnyIO cancellation-delivery coverage:

- Single and split-package uploads expire after the final inspection or after
  linking the base input; both reject, remove owned material and permit a retry.
- Discovery preserves admission under AnyIO cancellation, native cancellation and
  repeated native cancellation.
- Cancelled uploads preserve admission and staging until inspection completes;
  both worker success and worker failure retain cancellation and a consistent
  stored outcome.
- Cancelled writes and fsync keep their file handle and reservation until the
  operation finishes; request context variables reach the disk worker.
- AnyIO cancellation is delivered after both successful and failed discovery
  workers, rather than being lost to a returned result or a caught worker error.

These regressions use constructed bytes and explicitly selected fixture metadata
parsing. Real Docker isolation is checked separately by the authoritative
`PRIVACYTRACE_DOCKER_TESTS=1 pwsh -NoProfile -File scripts/check.ps1` run. Final
validation and delivery-SHA CI receipts belong in PR #88.

No public schema or policy/evidence semantics change. Persistent queues, dedicated
runners, cross-instance recovery acceptance, Issue #70 closure, merge and deployment
remain outside this repair. The optional scanner-context maintenance suggestion
is deferred.
