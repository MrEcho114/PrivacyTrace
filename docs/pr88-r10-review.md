# PR #88: R10 evidence origins and explicit split dependencies

Repair base: `9720f2f86486ab7be32a62a8d26e5ba422d439ca`.
Specification: Issue #70 / PT-MOB-102, under its development/acceptance split.
Earlier receipts retain their original SHA and validation results.

## Policy source integrity

Draft creation derives the material state from supplied text. Client provenance
labels cannot establish discovery, external import or a backend fetch. Manifest
URL discoveries have a server-owned source-ID record; external origins require
the existing import audit. Read, capture and report paths derive origins from
these records. An old label without its corresponding record is insufficient;
published historical reports are not rewritten.

The report distinguishes the discovery origin of a URL from acquisition of its
text. A discovered URL fetched by the backend records `DIRECT_WEB_FETCH` for text
and `MANIFEST_METADATA` for discovery. Imported text remains
`EXTERNAL_CHAT_EXPORT`; fetching replacement text records `DIRECT_WEB_FETCH`
while retaining the original import audit. All remain `UNREVIEWED`, `PARTIAL`
and `NOT_CHECKED` for review, completeness and attachments respectively.

A failed refresh retains an existing manual or fetched capture, its hash/time,
model audit and candidates, with the fetch error shown alongside the material.
The UI stops automatic extraction after that failure. A successful refresh
replaces the text and invalidates candidates tied to the previous text.

## Package integrity

The isolated metadata parser now carries manifest split declarations into the
shared package-set validator. It rejects missing feature dependencies, missing
configuration targets, invalid configuration targets, dependency cycles,
unsatisfied `requiredSplitTypes` and a lone base declaring `isSplitRequired`.
Missing requirements return `MISSING_REQUIRED_SPLIT`; malformed relationships
return `INVALID_SPLIT_DEPENDENCY`. Failed uploads leave the draft unchanged,
remove owned staging files and permit a complete-set retry.

Feature `uses-split` dependencies require an existing target. Configuration
splits default to base, or explicitly depend on an existing feature. Split types
use comma-separated declarations and package-wide required/offered sets. These
rules follow the Android parser and installer:

- [ApkLite manifest parsing](https://android.googlesource.com/platform/frameworks/base/+/refs/heads/main/core/java/android/content/pm/parsing/ApkLiteParseUtils.java)
- [SplitDependencyLoader dependency graph](https://android.googlesource.com/platform/frameworks/base/+/master/core/java/android/content/pm/PackageParser.java)
- [PackageInstallerSession split-type matching](https://android.googlesource.com/platform/frameworks/base/+/f5dc436da142b73af178e01fc17da2aecf0bc983/services/core/java/com/android/server/pm/PackageInstallerSession.java)

Worker directory scans enforce the same rules. The legacy single-APK upload
retains its asynchronous validation boundary: a base requiring absent splits
produces a failed analysis task with the specific dependency error. Ordinary
standalone APKs still work; standalone split analysis remains explicitly partial.

`ComponentScanContext` groups component identity, prior behavior count and seen
manifest excerpts. Base identity is distinct from a split named `base`, including
direct scanner calls; missing direct-call split names retain the `unknown`
namespace. The collection-wide 500-behavior cap and permission deduplication
retain their existing regression coverage.

## Regression evidence

The first regression run produced 16 expected assertion failures before repairs:
client/legacy origin spoofing, discovery versus acquisition, missing/invalid split
dependencies and HTTP rollback. Further pre-fix tests reproduced failed refresh
loss, inconsistent client status and direct-call namespace regressions.

`test_pr88_evidence_integrity.py` covers the status/origin matrix, persisted report
receipts, external-import refresh transitions, accepted and rejected dependency
sets, rollback/retry and standalone-base checks. Two opt-in tests exercise real
Docker metadata/scan boundaries, including HTTP task error propagation. The four
compiled Vue component cases in `live-source-retry.test.cjs` check that failed
refreshes preserve candidates while successful refreshes still extract new text.

Authoritative validation uses
`PRIVACYTRACE_DOCKER_TESTS=1 pwsh -NoProfile -File scripts/check.ps1`.
The PR execution record carries the final result and delivery-SHA CI receipts.
The generated draft schema and collector source-hash record are refreshed.

## Limits

These are constructed APK fixtures and controlled fetch responses. They do not
prove third-party app behavior, policy authenticity, runtime collection or full
Android installability. Only explicitly declared split requirements can be
validated; `DEX_ENTRIES` coverage does not prove an entire installed application
was supplied. Persistent queues, dedicated runners and cross-instance recovery
remain Issue #80 work and a final Issue #70 acceptance boundary. This repair does
not authorize merge, deployment or Issue #70 closure.
