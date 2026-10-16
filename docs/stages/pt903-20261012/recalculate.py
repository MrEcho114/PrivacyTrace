"""Recalculate the archived PT-903 report; never run or modify evaluated algorithms."""

import argparse
import hashlib
import json
import math
import subprocess
from collections import Counter
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent
ROOT = BASE.parents[2]
SHA = "323780c9a77d7de2bb1857b1b67b4f05fd94a525"
COMPARISON_HASH = "630b3af1feddf1014f3b738d89c5ee5c2e3810464bffe5389ae67dd101adf8d1"
RECEIPT_HASH = "62f8f60fad12467370f09c67bc088aad49221231a735619f2318882a57c652e6"
ZIP_HASH = "cd68b9802b8d0d9fe500991d62cda64cc0179533621836ce9e4a7cd0e820b480"
SCHEMES = ("permission_keyword", "api_flat", "privacytrace")
CASES = tuple(f"C0{i}" for i in range(1, 7))
STATES = (
    "EXACT_MATCH",
    "CATEGORY_MATCH",
    "NOT_DECLARED",
    "AMBIGUOUS_DISCLOSURE",
    "INSUFFICIENT_EVIDENCE",
)
FAILURE = "FAILED_OR_NO_STATUS"


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def encoded(value):
    return (json.dumps(value, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def git_bytes(path):
    return subprocess.check_output(["git", "show", f"{SHA}:{path}"], cwd=ROOT)


def git_json(path):
    return json.loads(git_bytes(path))


def original(name, expected_hash):
    raw = (BASE / "evidence" / name).read_bytes()
    require(digest(raw) == expected_hash, f"Archived evidence changed: {name}")
    return json.loads(raw)


def is_failure(row):
    return row["actual"] is None or bool(row["errors"])


def calculate():
    receipt = original("integration-receipt.json", RECEIPT_HASH)
    comparison = original("comparison.json", COMPARISON_HASH)
    require(receipt["commit_sha"] == SHA, "Receipt SHA mismatch")
    require(receipt["passed"] and not receipt["dirty_checkout"], "Invalid execution receipt")
    require(len(receipt["stages"]) == 11, "Missing execution stages")
    require(all(s["exit_code"] == 0 for s in receipt["stages"]), "Execution stage failed")
    evidence_names = {
        "build-a/build-receipt.json": "build-a.json",
        "build-b/build-receipt.json": "build-b.json",
        "evaluation/comparison.json": "comparison.json",
        "browser-proof/browser-proof.json": "browser-proof.json",
        "offline-proof/offline-proof.json": "offline-proof.json",
    }
    evidence = {
        path: original(name, receipt["evidence_sha256"][path])
        for path, name in evidence_names.items()
    }
    build = evidence["build-a/build-receipt.json"]
    require(build == evidence["build-b/build-receipt.json"], "Build receipts differ")
    locks = git_json("benchmarks/controlled/inputs.lock.json")
    artifact_lock = git_json("benchmarks/controlled/artifacts.lock.json")
    require(
        build["source_hashes"] == locks["sources"] == artifact_lock["source_hashes"],
        "Source locks differ",
    )
    require(build["apks"] == artifact_lock["apks"], "APK receipt hashes differ")
    require(
        build["toolchain"] == git_json("benchmarks/controlled/toolchain.lock.json"),
        "Toolchain lock changed",
    )
    for path, expected in locks["sources"].items():
        require(digest(git_bytes("benchmarks/controlled/" + path)) == expected, path)
    for path, expected in comparison["implementation_hashes"].items():
        require(digest(git_bytes(path)) == expected, path)
    truth_raw = git_bytes("benchmarks/controlled/ground-truth.json")
    truth = json.loads(truth_raw)
    require(
        digest(truth_raw)
        == comparison["truth_sha256"]
        == git_bytes("benchmarks/controlled/ground-truth.sha256").decode().strip(),
        "Ground truth digest differs",
    )
    require(truth == comparison["protocol"], "Protocol differs from frozen truth")
    require(
        truth["inputs_lock_sha256"] == digest(git_bytes("benchmarks/controlled/inputs.lock.json")),
        "Input lock differs",
    )
    require(
        datetime.fromisoformat(truth["frozen_at"])
        < datetime.fromisoformat(comparison["generated_at"]),
        "Freeze must precede results",
    )
    rows = comparison["rows"]
    require(
        Counter((r["scenario_id"], r["scheme"]) for r in rows)
        == Counter((c, s) for c in CASES for s in SCHEMES),
        "Require all 18 unique rows",
    )
    cases = {}
    for case in CASES:
        part = [r for r in rows if r["scenario_id"] == case]
        require(len({r["material_sha256"] for r in part}) == 1, "Unequal scheme materials")
        require(len({r["elapsed_seconds"] for r in part}) == 1, "Unequal shared timing")
        require(all(r["coverage"] == part[0]["coverage"] for r in part), "Unequal coverage")
        for row in part:
            require(row["expected"] == truth["scenarios"][case]["expected"], "Label changed")
            require(row["actual"] in STATES or row["actual"] is None, "Unknown state")
            require(
                row["agreement"] == (not is_failure(row) and row["actual"] == row["expected"]),
                "Wrong agreement",
            )
            for field in ("elapsed_seconds", "scheme_elapsed_seconds"):
                value = row[field]
                require(value is None or (math.isfinite(value) and value >= 0), "Invalid time")
        feature_raw = git_bytes(f"benchmarks/controlled/features/{case}.json")
        require(digest(feature_raw) == locks["features"][case], "Feature changed")
        feature = json.loads(feature_raw)
        policy_raw = git_bytes("benchmarks/controlled/policies/" + feature["policy_file"])
        require(digest(policy_raw) == feature["policy_sha256"], "Policy changed")
        text = policy_raw.decode("utf-8")
        spans = []
        for candidate in feature["candidates"]:
            excerpt = candidate["excerpt"]
            require(text.count(excerpt) == 1, "Candidate excerpt is not unique")
            start = text.index(excerpt)
            spans.append({**candidate, "start": start, "end": start + len(excerpt)})
        cases[case] = {
            "frozen_target": truth["scenarios"][case],
            "apk_sha256_from_verified_build_receipts": build["apks"][case],
            "feature_sha256": digest(feature_raw),
            "policy_sha256": digest(policy_raw),
            "material_sha256_from_prediction_worker": part[0]["material_sha256"],
            "scope_known": feature["scope_known"],
            "policy_complete": feature["policy_complete"],
            "candidate_spans_codepoints_half_open": spans,
            "shared_elapsed_seconds": part[0]["elapsed_seconds"],
            "coverage": part[0]["coverage"],
            "api_mapping_and_locator_checked": all(
                r["api_mapping_and_locator_checked"] for r in part
            ),
            "policy_spans_validated": all(r["policy_spans_validated"] for r in part),
        }
    summaries = {}
    for scheme in SCHEMES:
        part = [r for r in rows if r["scheme"] == scheme]
        counts = {
            "total": len(part),
            "status_agreement": sum(r["agreement"] for r in part),
            "failures": sum(is_failure(r) for r in part),
            "abstentions": sum(
                not is_failure(r) and r["actual"] == "INSUFFICIENT_EVIDENCE" for r in part
            ),
            "predicted": sum(not is_failure(r) for r in part),
        }
        require(counts == comparison["summaries"][scheme], "Stored summary differs")
        matrix = {state: {p: 0 for p in (*STATES, FAILURE)} for state in STATES}
        for row in part:
            matrix[row["expected"]][FAILURE if is_failure(row) else row["actual"]] += 1
        summaries[scheme] = {
            **counts,
            "state_mismatches": counts["predicted"] - counts["status_agreement"],
            "decisions_excluding_abstention": counts["predicted"] - counts["abstentions"],
            "agreement_denominator": len(part),
            "coverage_status_counts": dict(
                sorted(
                    Counter(
                        r["coverage"]["status"] if r["coverage"] else "UNKNOWN" for r in part
                    ).items()
                )
            ),
            "confusion_expected_rows_actual_columns": matrix,
            "scheme_elapsed_seconds_sum": sum(r["scheme_elapsed_seconds"] for r in part),
        }
    row_refs = [
        {
            "original_row_index_zero_based": i,
            "scenario_id": r["scenario_id"],
            "scheme": r["scheme"],
            "expected": r["expected"],
            "actual": r["actual"],
            "errors": r["errors"],
            "evidence_ids": r["evidence_ids"],
            "derived_row_sha256": digest(
                json.dumps(r, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ),
        }
        for i, r in enumerate(rows)
    ]
    historical = git_json("docs/stages/s1-pr29-real-verification-20261009.json")
    browser = evidence["browser-proof/browser-proof.json"]
    offline = evidence["offline-proof/offline-proof.json"]
    return {
        "schema_version": 1,
        "report_date": "2026-10-12",
        "issue": 25,
        "evaluation_sha": SHA,
        "original_generated_at": comparison["generated_at"],
        "origin": {
            "run_url": "https://github.com/MrEcho114/PrivacyTrace/actions/runs/38215788997",
            "artifact_id": 11731418196,
            "artifact_zip_sha256": ZIP_HASH,
            "artifact_expires_at": "2026-10-26T07:09:32Z",
            "comparison_sha256": COMPARISON_HASH,
            "integration_receipt_sha256": RECEIPT_HASH,
            "evidence_sha256": receipt["evidence_sha256"],
            "new_scan_or_build_performed_for_this_report": False,
            "original_prediction_records_retained_in_artifact": False,
            "original_prediction_record_hashes": None,
            "row_digest_encoding": (
                "UTF-8 JSON; ensure_ascii=False, sort_keys=True, separators=(',',':')"
            ),
            "row_digest_kind": "Derived in this report; not a hash of original predictor stdout",
        },
        "frozen_protocol": truth,
        "scheme_inputs": comparison["scheme_inputs"],
        "implementation_hashes": comparison["implementation_hashes"],
        "source_hashes": locks["sources"],
        "cases": cases,
        "row_references": row_refs,
        "summaries": summaries,
        "timing": {
            "measurement_method": "Existing runner/worker time.perf_counter() wall intervals",
            "shared_scenario_elapsed_seconds_sum_once": sum(
                c["shared_elapsed_seconds"] for c in cases.values()
            ),
            "runner_stage_elapsed_seconds": next(
                s["elapsed_seconds"] for s in receipt["stages"] if s["stage"] == "six-scenarios"
            ),
            "integration_stages": receipt["stages"],
            "repeats_for_performance": None,
            "confidence_interval": None,
            "cpu_seconds": None,
            "peak_rss_bytes": None,
            "io_bytes": None,
            "resource_observation_method": (
                "NOT_MEASURED: no stats/profiler resource samples retained"
            ),
            "prediction_container_memory_limit": "256m (configuration, not consumption)",
            "human_preparation_seconds": truth["human_preparation_seconds"],
            "preparation_actor": truth["preparation_actor"],
        },
        "pr_f1": {
            "status": "NOT_APPLICABLE_TO_FROZEN_TARGET",
            "TP": None,
            "FP": None,
            "FN": None,
            "precision": None,
            "recall": None,
            "f1": None,
            "reason": truth["pr_f1"],
            "formula_if_applicable": (
                "P=TP/(TP+FP); R=TP/(TP+FN); F1=2PR/(P+R); zero denominator=N/A"
            ),
        },
        "environment": {
            "build_receipt": build,
            "androguard": "4.1.3",
            "taxonomy": "0.3.0",
            "sdk_rules": "1.0.0",
            "ci_runner_selector": "ubuntu-latest",
            "ci_host_os_version": None,
            "browser_proof": browser,
            "offline_proof": offline,
        },
        "unmeasured": {
            "global_behavior_recall": None,
            "runtime_collection": None,
            "automatic_policy_extraction_accuracy": None,
            "held_out_generalization": None,
            "report_truncation_per_full_job": None,
            "C07_conflict": None,
            "C08_multidex": None,
            "independent_human_semantic_signoff": None,
            "complete_offline_package_retained_in_source_artifact": False,
        },
        "historical_real_case": {
            "name": "GKD 1.12.1 / versionCode 92",
            "date": historical["date"],
            "implementation_sha": historical["implementation_sha"],
            "apk_sha256": historical["apk_sha256"],
            "semantic_report_sha256": historical["semantic_report_sha256"],
            "counts": historical["counts"],
            "statuses": historical["statuses"],
            "policy": historical["policy"],
            "rerun_for_this_report": False,
            "included_in_controlled_denominator": False,
        },
    }


def table(headers, rows):
    return "\n".join(
        [
            "| " + " | ".join(headers) + " |",
            "| " + " | ".join("---" for _ in headers) + " |",
            *("| " + " | ".join(map(str, row)) + " |" for row in rows),
        ]
    )


def tables(result):
    summaries = result["summaries"]
    text = [
        "# PT-903 可复算表\n",
        f"评测 SHA：`{SHA}`。由 recalculate.py 生成。\n",
        "## 状态、失败、弃判与处理覆盖\n",
    ]
    text.append(
        table(
            ["方案", "状态一致/分母", "状态错误", "执行失败", "弃判", "DEX COMPLETE"],
            [
                [
                    s,
                    f"{summaries[s]['status_agreement']}/6",
                    summaries[s]["state_mismatches"],
                    summaries[s]["failures"],
                    summaries[s]["abstentions"],
                    f"{summaries[s]['coverage_status_counts'].get('COMPLETE', 0)}/6",
                ]
                for s in SCHEMES
            ],
        )
    )
    text.append("\n状态一致、失败、弃判和覆盖是不同统计；正确弃判也可计状态一致。\n")
    text.append("## 全部18行\n")
    text.append(
        table(
            ["场景", "冻结目标", *SCHEMES],
            [
                [
                    c,
                    result["cases"][c]["frozen_target"]["expected"],
                    *[
                        next(
                            r["actual"]
                            for r in result["row_references"]
                            if r["scenario_id"] == c and r["scheme"] == s
                        )
                        for s in SCHEMES
                    ],
                ]
                for c in CASES
            ],
        )
    )
    text.append("\n## 状态混淆\n\n行是冻结预期，列是实际状态。失败单列；未删除样本。\n")
    for s in SCHEMES:
        matrix = summaries[s]["confusion_expected_rows_actual_columns"]
        text.append(f"### {s}\n")
        text.append(
            table(
                ["expected / actual", *STATES, FAILURE],
                [[state, *[matrix[state][col] for col in (*STATES, FAILURE)]] for state in STATES],
            )
        )
        text.append("")
    text.append("## 计时（秒）\n\n共享场景耗时每场景仅计一次；方案耗时为同次worker中的计算区间。\n")
    original_rows = json.loads((BASE / "evidence/comparison.json").read_bytes())["rows"]
    scheme_times = {
        (r["scenario_id"], r["scheme"]): r["scheme_elapsed_seconds"] for r in original_rows
    }
    text.append(
        table(
            ["场景", "共享端到端", *SCHEMES],
            [
                [
                    c,
                    f"{result['cases'][c]['shared_elapsed_seconds']:.9f}",
                    *[f"{scheme_times[c, s]:.9f}" for s in SCHEMES],
                ]
                for c in CASES
            ]
            + [
                [
                    "合计",
                    f"{result['timing']['shared_scenario_elapsed_seconds_sum_once']:.9f}",
                    *[f"{summaries[s]['scheme_elapsed_seconds_sum']:.9f}" for s in SCHEMES],
                ]
            ],
        )
    )
    text.append(
        f"\nrunner六场景阶段实测：{result['timing']['runner_stage_elapsed_seconds']:.9f} 秒。"
        "两个计时边界不同，不补造差额分解；不是性能基准。\n"
    )
    text.append("## 既有执行阶段\n")
    text.append(
        table(
            ["阶段", "退出码", "耗时秒"],
            [
                [
                    s["stage"],
                    s["exit_code"],
                    f"{s['elapsed_seconds']:.9f}" if "elapsed_seconds" in s else "未测",
                ]
                for s in result["timing"]["integration_stages"]
            ],
        )
    )
    return ("\n".join(text) + "\n").encode("utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Verify saved outputs without writing")
    parser.add_argument("--output-dir", type=Path, default=BASE)
    args = parser.parse_args()
    result = calculate()
    outputs = {"results.json": encoded(result), "tables.md": tables(result)}
    for name, raw in outputs.items():
        path = args.output_dir / name
        if args.check:
            require(path.read_bytes() == raw, f"Recalculated output differs: {name}")
        else:
            args.output_dir.mkdir(parents=True, exist_ok=True)
            path.write_bytes(raw)
    print(
        json.dumps(
            {
                "evaluation_sha": SHA,
                "rows": len(result["row_references"]),
                "status_agreement": [result["summaries"][s]["status_agreement"] for s in SCHEMES],
                "output_sha256": {k: digest(v) for k, v in outputs.items()},
                "check": args.check,
            },
            ensure_ascii=True,
        )
    )


if __name__ == "__main__":
    main()
