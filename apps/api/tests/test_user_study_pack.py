"""Regression tests for scripts/verify-user-study-pack.py (Issue #62 items 3/4).

Every case builds a self-contained minimal pack inside tmp_path, so the suite
never depends on the real evidence/** contents: only scripts/ is read from the
repository (the dataset digest is recomputed with the real
scripts/build-dataset.py over the temporary samples/synthetic fixture).
"""

import csv
import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]


def _load(name, filename):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / filename)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


pack = _load("pt907_user_study_pack", "verify-user-study-pack.py")

OBSERVATION_HEADER = [
    "participant_id",
    "condition",
    "material",
    "sample_id",
    "question_id",
    "answer",
    "is_correct",
    "notes",
]

RECORDS_TEMPLATE = "evidence/user-study.template.csv"
RECORDS_HEADER = [
    "participant_id",
    "background",
    "condition",
    "material",
    "sample_id",
    "ground_truth_version",
    "question_id",
    "answer",
    "is_correct",
    "evidence_loc_seconds",
    "misconception",
    "start_time",
    "end_time",
    "subjective_understanding",
    "evidence_located",
    "git_commit",
    "notes",
]


def _write_csv(path, header, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(header)
        writer.writerows(rows)


def _bank_rows():
    return [
        ["q01", "权限范围", "set-1", "该应用声明了哪些权限类别？", ""],
        ["q02", "证据位置", "set-1", "报告中未知项如何标注？", ""],
    ]


def _key_rows(evidence_location_baseline="baseline.md#p1", evidence_location_report="report.md#p2"):
    return [
        [
            "syn-app-v1",
            "q01",
            "set-1",
            "true",
            "A",
            evidence_location_baseline,
            evidence_location_report,
            "答对记 1 分",
        ],
        ["syn-app-v1", "q02", "set-1", "false", "", "", "", "不计分"],
    ]


def _assignment_rows():
    return [
        ["p01", "baseline_first", "baseline;privacyTrace", "set-1", ""],
        ["p02", "report_first", "privacyTrace;baseline", "set-1", ""],
    ]


def _observation_rows():
    return [
        [
            "p01", "baseline_first", "baseline", "syn-app-v1",
            "q01", "A", "true", "SYNTHETIC_REHEARSAL",
        ],
        ["p01", "baseline_first", "privacyTrace", "syn-app-v1", "q02", "", "", ""],
        ["p02", "report_first", "privacyTrace", "syn-app-v1", "q01", "B", "false", ""],
        ["p02", "report_first", "baseline", "syn-app-v1", "q02", "", "", ""],
    ]


def _write_dataset_fixture(root):
    _write_csv(
        root / "samples/synthetic/manifest.csv",
        ["sample_id", "package_name", "version_name", "version_code", "apk_sha256"],
        [["syn-app-v1", "com.example.syn", "1.0", "1", "a" * 64]],
    )
    _write_csv(
        root / "samples/synthetic/runs.csv",
        [
            "run_id",
            "sample_id",
            "job_id",
            "report_sha256",
            "outcome",
            "limitations",
            "scanned_at",
            "evidence_count",
            "behavior_count",
            "claim_count",
            "notes",
        ],
        [
            [
                "run-syn-1",
                "syn-app-v1",
                "job-syn-1",
                "b" * 64,
                "partial",
                "加固",
                "2026-10-10T01:00:00Z",
                "1",
                "",
                "",
                "",
            ]
        ],
    )
    trace_dir = root / "samples/synthetic/trace"
    trace_dir.mkdir(parents=True, exist_ok=True)
    lines = [
        {
            "ts": "2026-10-10T01:00:00Z",
            "sample_id": "syn-app-v1",
            "job_id": "job-syn-1",
            "stage": "dex",
            "event": "evidence",
            "status": "ok",
            "evidence_ref": "ev-1",
            "data_type": "定位",
            "location": "com.example.Syn:onCreate",
        },
        {
            "ts": "2026-10-10T01:00:01Z",
            "sample_id": "syn-app-v1",
            "job_id": "job-syn-1",
            "stage": "consistency",
            "event": "conclusion",
            "status": "partial",
            "detail": "政策适用信息不全",
        },
    ]
    (trace_dir / "trace.jsonl").write_text(
        "\n".join(json.dumps(line, ensure_ascii=False) for line in lines) + "\n",
        encoding="utf-8",
    )


def _build_pack(
    root,
    *,
    bank_rows=None,
    key_rows=None,
    assignment_rows=None,
    observation_rows=None,
    template_rows=True,
):
    bank = _bank_rows() if bank_rows is None else bank_rows
    key = _key_rows() if key_rows is None else key_rows
    assignment = _assignment_rows() if assignment_rows is None else assignment_rows
    observations = _observation_rows() if observation_rows is None else observation_rows
    template = [] if not template_rows else None
    _write_csv(
        root / pack.QUESTION_BANK_FILES[0],
        pack.QUESTION_HEADER,
        bank if template is None else template,
    )
    _write_csv(root / pack.QUESTION_BANK_FILES[1], pack.QUESTION_HEADER, bank)
    _write_csv(
        root / pack.ANSWER_KEY_FILES[0],
        pack.ANSWER_HEADER,
        key if template is None else template,
    )
    _write_csv(root / pack.ANSWER_KEY_FILES[1], pack.ANSWER_HEADER, key)
    _write_csv(
        root / pack.ASSIGNMENT_FILES[0],
        pack.ASSIGNMENT_HEADER,
        assignment if template is None else template,
    )
    _write_csv(root / pack.ASSIGNMENT_FILES[1], pack.ASSIGNMENT_HEADER, assignment)
    observations_path = root / pack.OBSERVATIONS
    _write_csv(observations_path, OBSERVATION_HEADER, observations)
    observations_path.write_bytes(b"# synthetic rehearsal sheet\n" + observations_path.read_bytes())
    _write_dataset_fixture(root)
    # Include all mandatory frozen materials so isolated tmp_path packs exercise
    # the same coverage guarantees as the actual repository.
    for rel in pack.REQUIRED_MANIFEST_PATHS:
        target = root / rel
        if target.is_file():
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if rel.startswith("scripts/"):
            shutil.copyfile(ROOT / rel, target)
        elif rel == RECORDS_TEMPLATE:
            _write_csv(target, RECORDS_HEADER, [])
        else:
            target.write_text("synthetic test contract fixture\n", encoding="utf-8")
    return root


def _seed_manifest(root):
    """Write the manifest skeleton the rehearsal walkthrough step creates."""
    manifest = {
        "kind": "user-study-pack-freeze",
        "schema_version": "1.0.0",
        "synthetic_only": True,
        "hash_normalization": "crlf-to-lf",
        "dataset_schema_version": "0.3.0",
        "dataset_sha256": "0" * 64,
        "covered_globs": list(pack.DEFAULT_COVERED_GLOBS),
        "excluded": list(pack.DEFAULT_EXCLUDED),
        "files": [],
    }
    path = root / pack.MANIFEST
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _rewrite_manifest(root, mutate):
    path = root / pack.MANIFEST
    manifest = json.loads(path.read_text(encoding="utf-8"))
    mutate(manifest)
    path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )


def _codes(root):
    issues, _summary = pack.verify_root(root)
    return {issue.code for issue in issues}


def test_script_matches_the_frozen_contract():
    assert pack.QUESTION_BANK_FILES == (
        "evidence/user-study-question-bank.template.csv",
        "evidence/synthetic/user-study-question-bank.csv",
    )
    assert pack.ANSWER_KEY_FILES == (
        "evidence/user-study-answer-key.template.csv",
        "evidence/synthetic/user-study-answer-key.csv",
    )
    assert pack.ASSIGNMENT_FILES == (
        "evidence/user-study-assignment.template.csv",
        "evidence/synthetic/user-study-assignment.csv",
    )
    assert pack.OBSERVATIONS == "evidence/synthetic/user-study.csv"
    assert pack.MANIFEST == "evidence/synthetic/freeze-manifest.json"
    assert pack.QUESTION_HEADER == [
        "question_id",
        "dimension",
        "equivalent_set",
        "stem",
        "notes",
    ]
    assert pack.ANSWER_HEADER == [
        "sample_id",
        "question_id",
        "equivalent_set",
        "scorable",
        "expected_answer",
        "evidence_location_baseline",
        "evidence_location_report",
        "scoring",
    ]
    assert pack.ASSIGNMENT_HEADER == [
        "participant_id",
        "condition",
        "material_order",
        "equivalent_set",
        "notes",
    ]
    assert pack.MANIFEST_FIELDS[0] == ("kind", "user-study-pack-freeze", "manifest-kind")
    assert pack.DEFAULT_EXCLUDED == [
        "evidence/synthetic/freeze-manifest.json",
        "evidence/synthetic/rehearsal-walkthrough.md",
    ]
    assert RECORDS_TEMPLATE in pack.DEFAULT_COVERED_GLOBS
    assert RECORDS_TEMPLATE in pack.REQUIRED_MANIFEST_PATHS
    assert "evidence/user-study-*.template.*" in pack.DEFAULT_COVERED_GLOBS


def test_records_template_is_frozen_by_the_manifest(tmp_path):
    root = _build_pack(tmp_path)
    _write_csv(root / RECORDS_TEMPLATE, RECORDS_HEADER, [])
    _seed_manifest(root)
    pack.write_manifest(root)
    manifest = json.loads((root / pack.MANIFEST).read_text(encoding="utf-8"))
    assert RECORDS_TEMPLATE in [entry["path"] for entry in manifest["files"]]
    assert pack.verify_root(root)[0] == []
    assert set(pack.REQUIRED_MANIFEST_PATHS) <= {
        item["path"] for item in manifest["files"]
    }


def test_write_manifest_repairs_stale_covered_globs(tmp_path):
    root = _build_pack(tmp_path)
    _write_csv(root / RECORDS_TEMPLATE, RECORDS_HEADER, [])
    _seed_manifest(root)

    def drop_glob(manifest):
        manifest["covered_globs"] = [
            item for item in manifest["covered_globs"] if item != RECORDS_TEMPLATE
        ]

    _rewrite_manifest(root, drop_glob)
    assert pack.main(["--root", str(root), "--write-manifest"]) == 0
    manifest = json.loads((root / pack.MANIFEST).read_text(encoding="utf-8"))
    assert RECORDS_TEMPLATE in manifest["covered_globs"]
    assert RECORDS_TEMPLATE in [entry["path"] for entry in manifest["files"]]
    assert pack.verify_root(root)[0] == []


def test_rejects_manifest_omitting_a_pack_material(tmp_path):
    root = _build_pack(tmp_path)
    _write_csv(root / RECORDS_TEMPLATE, RECORDS_HEADER, [])
    _seed_manifest(root)
    pack.write_manifest(root)

    def drop_entry(manifest):
        manifest["covered_globs"] = [
            item for item in manifest["covered_globs"] if item != RECORDS_TEMPLATE
        ]
        manifest["files"] = [
            entry for entry in manifest["files"] if entry["path"] != RECORDS_TEMPLATE
        ]

    _rewrite_manifest(root, drop_entry)
    issues, _summary = pack.verify_root(root)
    assert [issue.path for issue in issues] == [RECORDS_TEMPLATE]
    assert issues[0].code == "manifest-required-uncovered"


def test_valid_pack_passes(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    issues, summary = pack.verify_root(root)
    assert issues == []
    assert summary["question_bank_rows"] == 4
    assert summary["answer_key_rows"] == 4
    assert summary["observation_rows"] == 4
    assert summary["observation_rehearsal_rows"] == 1


def test_rehearsal_rows_are_checked_by_default(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    issues, summary = pack.verify_root(root)
    assert issues == []
    assert summary["observation_rows"] == 4
    assert summary["observation_rehearsal_rows"] == 1

    rows = _observation_rows()
    rows[0][6] = "false"
    _build_pack(tmp_path, observation_rows=rows)
    # Refresh valid checksums; semantic validation must still reject bad grading.
    pack.write_manifest(root)
    assert "observation-consistency" in _codes(root)


def test_header_only_template_skips_balance_check(tmp_path):
    root = _build_pack(tmp_path, template_rows=False)
    _seed_manifest(root)
    pack.write_manifest(root)
    assert _codes(root) == set()


def test_rejects_answer_key_missing_coverage(tmp_path):
    root = _build_pack(tmp_path, key_rows=_key_rows()[:1])
    assert "observation-uncovered" in _codes(root)


def test_rejects_empty_evidence_location(tmp_path):
    root = _build_pack(tmp_path, key_rows=_key_rows(evidence_location_report=""))
    assert "answer-key-field-empty" in _codes(root)


def test_rejects_unscorable_row_with_expected_answer(tmp_path):
    rows = _key_rows()
    rows[1][4] = "A"
    root = _build_pack(tmp_path, key_rows=rows)
    assert "answer-key-expected-not-empty" in _codes(root)


def test_rejects_scorable_row_without_expected_answer(tmp_path):
    rows = _key_rows()
    rows[0][4] = ""
    root = _build_pack(tmp_path, key_rows=rows)
    assert "answer-key-expected-invalid" in _codes(root)


def test_rejects_leaking_stem(tmp_path):
    rows = _bank_rows()
    rows[0][3] = "本题的正确答案是哪一个？"
    root = _build_pack(tmp_path, bank_rows=rows)
    assert "stem-leak" in _codes(root)


def test_rejects_condition_order_mismatch(tmp_path):
    rows = _assignment_rows()
    rows[0][2] = "baseline;baseline"
    root = _build_pack(tmp_path, assignment_rows=rows)
    assert "assignment-order-mismatch" in _codes(root)


def test_rejects_unbalanced_assignment(tmp_path):
    rows = _assignment_rows() + [
        ["p03", "baseline_first", "baseline;privacyTrace", "set-1", ""],
        ["p04", "baseline_first", "baseline;privacyTrace", "set-1", ""],
    ]
    root = _build_pack(tmp_path, assignment_rows=rows)
    assert "assignment-unbalanced" in _codes(root)


def test_rejects_duplicate_participant_id(tmp_path):
    rows = _assignment_rows()
    rows.append(["p01", "baseline_first", "baseline;privacyTrace", "set-1", ""])
    root = _build_pack(tmp_path, assignment_rows=rows)
    assert "assignment-participant-duplicate" in _codes(root)


def test_rejects_inconsistent_is_correct(tmp_path):
    rows = _observation_rows()
    rows[0][6] = "false"
    root = _build_pack(tmp_path, observation_rows=rows)
    assert "observation-consistency" in _codes(root)


def test_rejects_observation_not_scorable(tmp_path):
    rows = _observation_rows()
    rows[1][6] = "true"
    root = _build_pack(tmp_path, observation_rows=rows)
    assert "observation-not-scorable" in _codes(root)


def test_rejects_observation_order_mismatch(tmp_path):
    rows = _observation_rows()
    rows[0][2], rows[1][2] = "privacyTrace", "baseline"
    root = _build_pack(tmp_path, observation_rows=rows)
    assert "observation-order-mismatch" in _codes(root)


def test_rejects_missing_manifest(tmp_path):
    root = _build_pack(tmp_path)
    assert _codes(root) == {"manifest-missing"}


def test_rejects_manifest_hash_mismatch(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    bank = root / pack.QUESTION_BANK_FILES[1]
    bank.write_text(bank.read_text(encoding="utf-8") + "# tamper\n", encoding="utf-8")
    assert "manifest-hash-mismatch" in _codes(root)


def test_rejects_manifest_missing_file(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    manifest_path = root / pack.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"] = [
        entry
        for entry in manifest["files"]
        if entry["path"] != "evidence/synthetic/user-study.csv"
    ]
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert "manifest-missing-file" in _codes(root)


def test_rejects_manifest_extra_file(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    manifest_path = root / pack.MANIFEST
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["files"].append({"path": "evidence/ghost.csv", "sha256": "0" * 64, "bytes": 0})
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    assert "manifest-extra-file" in _codes(root)


def test_hash_normalization_survives_crlf(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    target = root / pack.OBSERVATIONS
    target.write_bytes(target.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
    assert _codes(root) == set()


def test_write_manifest_recomputes_hashes(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    target = root / pack.OBSERVATIONS
    target.write_text(target.read_text(encoding="utf-8") + "\n", encoding="utf-8")
    assert "manifest-hash-mismatch" in _codes(root)
    pack.write_manifest(root)
    assert _codes(root) == set()


def test_write_manifest_refuses_to_create(tmp_path):
    root = _build_pack(tmp_path)
    with pytest.raises(pack.UsageError):
        pack.write_manifest(root)


def test_cli_json_ok(tmp_path, capsys):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    assert pack.main(["--root", str(root), "--json"]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload == {"ok": True, "issues": []}


def test_cli_json_reports_issue_and_exit_code(tmp_path, capsys):
    root = _build_pack(tmp_path)
    assert pack.main(["--root", str(root), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert [issue["code"] for issue in payload["issues"]] == ["manifest-missing"]
    assert set(payload["issues"][0]) == {"code", "path", "detail"}


def test_cli_write_manifest_exit_codes(tmp_path, capsys):
    root = _build_pack(tmp_path)
    assert pack.main(["--root", str(root), "--write-manifest"]) == 2
    assert "freeze-manifest.json is missing" in capsys.readouterr().err
    _seed_manifest(root)
    assert pack.main(["--root", str(root), "--write-manifest"]) == 0
    assert "rewritten" in capsys.readouterr().out
    assert pack.main(["--root", str(root)]) == 0
    assert capsys.readouterr().out.rstrip().endswith("result: OK")


def test_cli_checks_rehearsal_by_default(tmp_path, capsys):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    rows = _observation_rows()
    rows[0][6] = "false"
    _build_pack(tmp_path, observation_rows=rows)
    pack.write_manifest(root)
    assert pack.main(["--root", str(root), "--json"]) == 1
    payload = json.loads(capsys.readouterr().out)
    assert {issue["code"] for issue in payload["issues"]} >= {
        "observation-consistency"
    }


def test_rejects_duplicate_observation_even_with_fresh_manifest(tmp_path):
    rows = _observation_rows()
    rows.append(rows[0].copy())
    root = _build_pack(tmp_path, observation_rows=rows)
    _seed_manifest(root)
    pack.write_manifest(root)
    assert "observation-duplicate" in _codes(root)


def test_allows_same_participant_and_question_across_different_samples():
    rows = [dict(zip(OBSERVATION_HEADER, row)) for row in _observation_rows()]
    different = dict(rows[0], sample_id="other-sample")
    answers = pack.answer_key_index(
        [
            {"sample_id": "syn-app-v1", "question_id": "q01",
             "scorable": "true", "expected_answer": "A"},
            {"sample_id": "syn-app-v1", "question_id": "q02",
             "scorable": "false", "expected_answer": ""},
            {"sample_id": "other-sample", "question_id": "q01",
             "scorable": "true", "expected_answer": "A"},
        ]
    )
    issues = pack.check_observation_rows(
        rows + [different], pack.OBSERVATIONS, answers,
        [dict(zip(pack.ASSIGNMENT_HEADER, row)) for row in _assignment_rows()],
    )
    assert not any(issue.code == "observation-duplicate" for issue in issues)


def test_freeze_rejects_core_tool_removed_from_globs_and_hashes(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    mandatory = "scripts/metrics-user-study.py"

    def remove_tool(manifest):
        manifest["covered_globs"] = [
            glob for glob in manifest["covered_globs"] if glob != mandatory
        ]
        manifest["files"] = [
            item for item in manifest["files"] if item["path"] != mandatory
        ]

    _rewrite_manifest(root, remove_tool)
    assert "manifest-required-uncovered" in _codes(root)


def test_freeze_rejects_excluded_mandatory_tool(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    _rewrite_manifest(
        root, lambda manifest: manifest["excluded"].append("scripts/build-dataset.py")
    )
    assert "manifest-required-excluded" in _codes(root)
    with pytest.raises(pack.UsageError, match="cannot exclude mandatory"):
        pack.write_manifest(root)


def test_freeze_rejects_missing_mandatory_tool(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)
    (root / "scripts/metrics-user-study.py").unlink()
    assert "file-missing" in _codes(root)


def test_freeze_rejects_removed_trace_entry_even_when_hashes_are_rewritten(tmp_path):
    root = _build_pack(tmp_path)
    _seed_manifest(root)
    pack.write_manifest(root)

    def remove_trace(manifest):
        manifest["covered_globs"] = [
            item for item in manifest["covered_globs"]
            if item != "samples/synthetic/**"
        ]
        manifest["files"] = [
            item for item in manifest["files"]
            if not item["path"].startswith("samples/synthetic/")
        ]

    _rewrite_manifest(root, remove_trace)
    assert "manifest-required-uncovered" in _codes(root)
