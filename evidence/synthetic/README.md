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

Three of the files carry the independent reference the answers are graded
against: `user-study-question-bank.csv` (12 questions, six `equivalent_set`
pairs), `user-study-answer-key.csv` (one row per observed
`(sample_id, question_id)` with the synthetic `expected_answer` and the
synthetic evidence pointers in both materials) and `user-study-assignment.csv`
(six participants, balanced 1/1 inside each assigned set). `answer` and
`is_correct` in `user-study.csv` are derived from that key, so every row
satisfies `is_correct == (answer == expected_answer)`. The `#`-prefixed first
line of the three reference files marks them as synthetic and is not part of
the CSV header.

This is not real evidence. It must not be cited, merged into `evidence/` as a
completed study, or used to close Issue #23. Regenerate with
`python scripts/generate-synthetic-pt907.py`.
