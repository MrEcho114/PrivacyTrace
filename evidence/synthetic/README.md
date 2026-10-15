# PT-907 Synthetic User-Study Evidence

Status: **SYNTHETIC ONLY**.

The CSV files in this directory are generated rehearsal fixtures for
`scripts/metrics-user-study.py` and the dataset builder. Participant IDs are
anonymous synthetic identifiers; all answers, durations, misconceptions, and
timestamps are fictional.

`condition` records the reading order (`baseline_first` / `report_first`);
`material` records which material that answer was given against (`baseline` /
`privacyTrace`). Each synthetic participant answers the first six questions
against the first material and the last six against the second one. The fixture
is deliberately not tuned to produce a material effect: it exercises the
grouping, the effect logic is covered by unit tests.

This is not real evidence. It must not be cited, merged into `evidence/` as a
completed study, or used to close Issue #23. Regenerate with
`python scripts/generate-synthetic-pt907.py`.
