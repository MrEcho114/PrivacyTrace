"""Allowlisted controlled-only replay package, no APKs, private reports or credentials."""

import argparse
import html
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path

from privacytrace.controlled import SUITE, Features
from privacytrace.job_store import JobStore
from privacytrace.policy_intake import digest, read_safe
from privacytrace.resources import taxonomy

ROOT = Path(__file__).resolve().parents[1]

SCENARIOS = {f"C0{i}" for i in range(1, 7)}
SCHEMES = {"permission_keyword", "api_flat", "privacytrace"}


def _material_digest(report):
    """Reproduce the benchmark's input-only material fingerprint, not its expected labels."""
    material = {
        "bundle": {
            key: report[key]
            for key in ("job", "evidence", "behaviors", "policy_documents", "policy_claims")
        },
        "permissions": report["sample"]["permissions"],
    }
    return digest(json.dumps(material, ensure_ascii=True, sort_keys=True).encode())


def validate_replay_set(comparison, reports, truth_digest, build_digest):
    """Refuse partial/duplicated or unrelated reports before constructing a package."""
    if (
        not isinstance(comparison, dict)
        or comparison.get("truth_sha256") != truth_digest
        or not isinstance(comparison.get("protocol"), dict)
        or not isinstance(comparison["protocol"].get("scenarios"), dict)
        or set(comparison["protocol"]["scenarios"]) != SCENARIOS
        or not isinstance(comparison.get("rows"), list)
        or len(comparison["rows"]) != len(SCENARIOS) * len(SCHEMES)
        or len(reports) != len(SCENARIOS)
    ):
        raise ValueError("Incomplete or invalid controlled replay comparison")

    scenario_reports = {}
    for job_id, report in reports.items():
        if not isinstance(report, dict):
            raise ValueError("Malformed controlled replay report")
        job = report.get("job")
        tools = report.get("tools")
        if not isinstance(job, dict) or not isinstance(tools, dict):
            raise ValueError("Controlled replay report is missing identity")
        scenario = tools.get("controlled_scenario")
        if (
            scenario not in SCENARIOS
            or scenario in scenario_reports
            or job.get("id") != job_id
            or job.get("sample_id") != scenario
            or job.get("state") != "SUCCEEDED"
            or job.get("input_mode") != "CONTROLLED_APK"
            or job.get("source_origin") != "CONTROLLED"
            or tools.get("controlled_build_sha256") != build_digest
        ):
            raise ValueError("Duplicated or untrusted controlled replay scenario")
        scenario_reports[scenario] = report
    if set(scenario_reports) != SCENARIOS:
        raise ValueError("Controlled replay requires one report per scenario")

    material_hashes = {
        scenario: _material_digest(report)
        for scenario, report in scenario_reports.items()
    }
    pairs = set()
    for row in comparison["rows"]:
        if not isinstance(row, dict):
            raise ValueError("Malformed comparison row")
        scenario, scheme = row.get("scenario_id"), row.get("scheme")
        key = (scenario, scheme)
        if (
            scenario not in SCENARIOS
            or scheme not in SCHEMES
            or key in pairs
            or row.get("expected")
            != comparison["protocol"]["scenarios"][scenario].get("expected")
            or row.get("material_sha256") != material_hashes[scenario]
        ):
            raise ValueError("Duplicate, missing, or inconsistent comparison row")
        pairs.add(key)
    if pairs != {(scenario, scheme) for scenario in SCENARIOS for scheme in SCHEMES}:
        raise ValueError("Controlled replay comparison is incomplete")


SAFE_TOOLS = {
    "androguard",
    "sdk_signatures",
    "worker_image",
    "jadx",
    "analysis_generated_at",
    "controlled_scenario",
    "controlled_features_sha256",
    "controlled_build_sha256",
    "policy_preparation",
}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    comparison = json.loads(read_safe(args.run / "comparison.json"))
    generated = datetime.now(timezone.utc).isoformat()
    build_receipt = read_safe(args.run.parent / "build-a" / "build-receipt.json")
    truth_digest = digest(read_safe(SUITE / "ground-truth.json"))
    build_digest = digest(build_receipt)
    reports = {}
    store = JobStore(args.run / "jobs")
    inputs = json.loads(read_safe(SUITE / "inputs.lock.json"))
    artifacts = json.loads(read_safe(SUITE / "artifacts.lock.json"))
    for job in store.list():
        if job.input_mode != "CONTROLLED_APK":
            raise ValueError("Only authored controlled reports may be distributed")
        if job.state != "SUCCEEDED":
            continue  # Failures stay in the comparison artifact, never removed from denominator.
        report = store.report(job.id).model_dump(mode="json")
        scenario = report["tools"].get("controlled_scenario")
        if scenario not in inputs["features"] or job.sample_id != scenario:
            raise ValueError("Export requires a known authored controlled scenario")
        feature = Features.model_validate_json(
            read_safe(SUITE / "features" / (scenario + ".json"))
        )
        if (
            report["job"]["id"] != job.id
            or report["job"]["sample_id"] != scenario
            or report["job"]["input_mode"] != "CONTROLLED_APK"
            or report["job"]["source_origin"] != "CONTROLLED"
            or report["sample"]["apk_sha256"] != artifacts["apks"][scenario]
            or report["sample"]["package_name"] != feature.package_name
            or report["tools"].get("controlled_features_sha256")
            != inputs["features"][scenario]
            or len(report["policy_documents"]) != 1
            or any(
                doc["source_type"] != "CONTROLLED_POLICY"
                or doc["artifact"]["sha256"] != feature.policy_sha256
                for doc in report["policy_documents"]
            )
        ):
            raise ValueError(
                "Export materials do not match the authored fixture hashes"
            )
        report["tools"] = {
            key: value for key, value in report["tools"].items() if key in SAFE_TOOLS
        }
        report["tools"].update(
            presentation_mode="OFFLINE_REPLAY", offline_package_built_at=generated
        )
        report[
            "reviews"
        ] = []  # Local user names/notes never belong in this authored package.
        reports[job.id] = report
    # The comparison and six successful trusted reports must form one exact replay.
    # This check happens before any output directory or manifest is created.
    validate_replay_set(comparison, reports, truth_digest, build_digest)
    args.output.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT / "apps/web/dist", args.output / "web")
    index = args.output / "web/index.html"
    index.write_text(
        index.read_text(encoding="utf-8").replace(
            "<head>", '<head><meta name="privacytrace-presentation" content="offline">'
        ),
        encoding="utf-8",
    )
    shutil.copyfile(ROOT / "scripts/offline-viewer.py", args.output / "viewer.py")
    for name, value in [
        ("reports.json", reports),
        ("taxonomy.json", taxonomy()),
        ("comparison.json", comparison),
    ]:
        (args.output / name).write_text(
            json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(row.get(key))) + "</td>"
            for key in (
                "scenario_id",
                "scheme",
                "expected",
                "actual",
                "agreement",
                "api_mapping_and_locator_checked",
                "elapsed_seconds",
                "errors",
            )
        )
        + "</tr>"
        for row in comparison["rows"]
    )
    page = """<!doctype html><html lang="zh-CN"><meta charset="utf-8">
<title>PrivacyTrace 六场景公平比较</title><style>body{font:16px sans-serif;margin:2rem}
td,th{border:1px solid #999;padding:.5rem}table{border-collapse:collapse}</style>
<h1>OFFLINE REPLAY · 六场景三方案比较</h1><p>六个自建小样本；基线输出仅作实验记录。
静态调用不证明实际采集、违法或安全。不报告自动政策抽取准确率或商业应用全局召回。</p>
<table><thead><tr><th>场景</th><th>方案</th><th>预期</th><th>实际</th><th>一致</th>
<th>API定位核对</th><th>秒（同材料端到端，共享扫描）</th><th>失败</th></tr></thead><tbody>"""
    page += (
        rows
        + "</tbody></table><h2>方案使用材料与限制</h2><pre>"
        + html.escape(
            json.dumps(comparison["scheme_inputs"], ensure_ascii=False, indent=2)
        )
        + "</pre></html>"
    )
    (args.output / "web/comparison.html").write_text(page, encoding="utf-8")
    (args.output / "README.txt").write_text(
        "PrivacyTrace authored controlled replay. Requires Python 3.11+ only; no model key.\n"
        "Run: python viewer.py --port 8765\nOpen http://127.0.0.1:8765\n"
        "Six source-built scenarios. No APK, private policy, local review or credentials.\n"
        "Internal verification package only. Project source license is not yet decided.\n"
        "Viewer verifies exact package file set and SHA256 before serving.\n",
        encoding="utf-8",
    )
    (args.output / "DISTRIBUTION.txt").write_text(
        "INTERNAL VERIFICATION ONLY. Project source license is pending team decision.\n"
        "This task grants no public release or competition-submission authorization.\n"
        "Only agent-authored controlled policies are included. No real APK/policy is distributed.\n"
        "The bundle uses Vue runtime and Vite preload helper; their license texts follow.\n",
        encoding="utf-8",
    )
    for name, path in [
        ("Vue-LICENSE", ROOT / "node_modules/vue/LICENSE"),
        ("Vite-LICENSE", ROOT / "node_modules/vite/LICENSE.md"),
    ]:
        shutil.copyfile(path, args.output / name)
    files = {
        path.relative_to(args.output).as_posix(): digest(path.read_bytes())
        for path in sorted(args.output.rglob("*"))
        if path.is_file()
    }
    (args.output / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "built_at": generated,
                "kind": "CONTROLLED_OFFLINE_REPLAY",
                "files": files,
            },
            indent=2,
        ),
        encoding="utf-8",
    )
    print(
        json.dumps({"status": "EXPORTED", "files": len(files), "reports": len(reports)})
    )


if __name__ == "__main__":
    main()
