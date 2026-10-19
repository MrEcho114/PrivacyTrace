# PR #88: R12 full-PR review repairs

Review fixed point: `origin/main` = `6f2b0892fd195b02b37aca5c79644815f3ce9979`
(merge-base `96e597e`); reviewed HEAD = `361c1d2`; 25 PR commits, 54 files.
Specification: Issue #70 / PT-MOB-102, fetched from the issue tracker.
R8-R11 records retain their original candidates and validation receipts.

## Review findings

The full-PR Standards and Spec axes found no hard documented-standard
violations. The accepted repairs are:

- **Collector-retrieved bodies were presented as manual text.** A
  `collector/1 RETRIEVED` source was stored with `status="manual"`, so the
  source panel said “手动补入正文” and `captures` could only choose
  `DIRECT_WEB_FETCH` or `EXTERNAL_CHAT_EXPORT` by status. `RETRIEVED` now keeps
  `status="ready"`; the acquisition is `EXTERNAL_CHAT_EXPORT` until the backend
  replaces the text with a fetched capture, identified by `final_url`. A
  `PROVIDED` body remains `status="manual"`. The persisted import audit is
  unchanged. The import, draft and report source panels now show the provenance
  label (Manifest 发现 / 外部导入 / 后端抓取 / 手动输入), so a collector body is
  not confused with a backend fetch. New/updated tests cover draft status,
  report acquisition and the rendered labels.
- **The web start flow still enforced the per-item candidate check.** The
  server start gate was already relaxed (`captures(require_checked=False)`), but
  `LiveWorkflow.begin` rejected any unchecked candidate. The UI gate is removed;
  a compiled-component test starts with `checked=false` and verifies that
  `saveCandidates` receives it and `startScan` is called. The candidate-page
  instruction and the Issue 44 design record now say unchecked candidates may be
  kept as UNREVIEWED instead of requiring per-item checking.
- **The 101-file boundary did not fit the inspection budget.** A real isolated
  metadata pass over 101 APKs took **254.02 s** on this host; the 180 s budget
  would reject a valid maximal set with 503. The total inspection budget is now
  600 s (the per-worker cap remains 120 s), with the measurement recorded in
  `docs/architecture.md`. The streaming upload budget remains 180 s.
- **Production test seam.** `pipeline.run(..., scanner=None)` was removed; the
  regression now monkeypatches `pipeline.scan_isolated`.
- **Low-risk Standards cleanups.** Removed the redundant per-split manifest
  dedupe (the scan context already de-duplicates), restored the copy-loop
  `INPUT_TOO_LARGE` branch (still an internal guard; upload size is bounded
  earlier), centralized the “already uploaded” message, routed upload error
  mapping through `web_error`, removed the unused `inspect_axml` wrapper, named
  the source-type wire code, and replaced the “10 integrity rules” count with
  count-free wording in `docs/test-infra.md`, the validator docstring and the
  test headers.

## Deferred

- **24 h remote-draft cleanup.** `DRAFT_TTL_SECONDS`/`_cleanup_expired_drafts`
  predate this PR and still purge inactive remote drafts, including uploaded
  material. Issue #70 asks for long-term retention until active deletion and
  “不暗改为短期到期”. Changing this is a product/retention decision, not a
  mechanical repair: either disclose the TTL as an explicit capacity policy or
  remove material drafts from the purge and add an explicit draft-delete
  contract. No behavior change was made here; this remains an Issue #70
  acceptance item.
- **Refactors that are not material:** split-name validation is still repeated
  at four call sites and `DUPLICATE_SPLIT_NAME` still covers several reasons;
  the ZIP-entry safety loop remains duplicated between the archive reader and
  `_unpack_package_set`; `parse_package_input` is used only by tests; and
  `merged_limits` still dispatches on string keys. These are judgement calls
  with API/behavior churn, not defects.
- **Intentional intake semantics:** legacy `/apk` auto-detects a multi-APK ZIP
  as a package set, and a standalone base declaring required splits now fails
  its job instead of publishing a PARTIAL report. Both are recorded in
  `docs/architecture.md`; no spec line asks for a change.

## Verification

`PRIVACYTRACE_DOCKER_TESTS=1` authoritative check through the Git Bash entry
point (worker image rebuilt from this tree): API **1426 passed / 60 skipped /
3 warnings**; Web **53 passed / 0 skipped**; ruff, generated-contract drift,
user-study pack, `vue-tsc` and Vite build passed; exit 0.

The 101-file measurement used real `inspect_package_isolated` runs, not a stub:
101 constructed APKs, 254.02 s total, below the new 600 s budget. The new UI
test fails if the candidate gate is restored; the collector test fails if
`RETRIEVED` is stored as `manual` or the report acquisition is `DIRECT_WEB_FETCH`.

## Limits

These remain constructed APK/metadata fixtures and controlled fetch responses;
they do not prove third-party app behaviour, policy authenticity, full Android
installability or runtime collection. The 101-file measurement is host-specific
and is not a production SLA. Persistent queues, dedicated runners and
cross-instance recovery remain Issue #80. This record does not authorize merge,
deployment or Issue #70 closure.
