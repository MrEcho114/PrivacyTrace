# PT-907 Synthetic Rehearsal Pack

Status: **SYNTHETIC ONLY**.

This directory and `evidence/synthetic/` contain deterministic rehearsal fixture
data for the Issue #23 tooling. App names, package names, URLs, hashes,
timestamps, policies, runs, traces, and participant answers are all fictional.

Use cases:
- Validate the PT-907 scripts end to end.
- Rehearse the real-data workflow before actual acquisition.
- Provide a clearly labeled `Refs #23` technical-side PR smoke fixture.

Must NOT do:
- Present this as real sample analysis.
- Present this as a real privacy policy or real user test.
- Use this to close Issue #23 or to claim its acceptance criteria were met.
- Run `scripts/verify-real-samples.py` against this directory; no APK files exist.

The generator is deterministic: `python scripts/generate-synthetic-pt907.py`.
