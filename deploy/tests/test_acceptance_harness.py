"""Entry-point and collector-gating tests: the harness must never fake a PASS."""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

DEPLOY = Path(__file__).resolve().parents[1]
ROOT = DEPLOY.parent
for entry in (str(DEPLOY), str(ROOT)):
    if entry not in sys.path:
        sys.path.insert(0, entry)

from acceptance import (  # noqa: E402  # noqa: E402
    r2_business_loop,
    r4_fault_recovery,
    r5_backup_recovery,
    r6_capacity_audit,
)
from acceptance import run as harness  # noqa: E402
from acceptance.receipt import SKIP, summarize  # noqa: E402
from acceptance.topology import ENVIRONMENT_VARIABLES, HttpResult, Topology  # noqa: E402

#: Every PT_ACCEPTANCE_* variable, so a test can start from a clean environment.
ACCEPTANCE_ENV = tuple(ENVIRONMENT_VARIABLES)


def clean_environment(**overrides):
    """A patched environment with no topology configured unless overridden."""
    values = {name: "" for name in ACCEPTANCE_ENV}
    values.update(overrides)
    return patch.dict(os.environ, values, clear=False)


class ArgumentTests(unittest.TestCase):
    def test_only_accepts_comma_lists_and_repeats(self):
        self.assertEqual(harness.parse_only(["r2,r4"]), ["r2", "r4"])
        self.assertEqual(harness.parse_only(["r2", "r5,r2"]), ["r2", "r5"])

    def test_only_rejects_unknown_collectors(self):
        with self.assertRaises(ValueError):
            harness.parse_only(["r7"])
        with self.assertRaises(ValueError):
            harness.parse_only([","])

    def test_list_checks_documents_every_variable(self):
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer):
            self.assertEqual(harness.main(["--list-checks"]), 0)
        output = buffer.getvalue()
        for name in ENVIRONMENT_VARIABLES:
            self.assertIn(name, output)


class NoTopologyRoundTests(unittest.TestCase):
    """The default round must be a clean, non-lying SKIP everywhere."""

    def _run(self, argv):
        buffer = io.StringIO()
        with clean_environment(), contextlib.redirect_stdout(buffer):
            code = harness.main(argv)
        return code, buffer.getvalue()

    def test_default_round_is_incomplete_without_deployment_evidence(self):
        code, output = self._run(["--no-write"])
        self.assertEqual(code, 2)
        self.assertIn("FAIL         : 0", output)
        self.assertIn("SKIP", output)

    def test_each_single_collector_survives_without_a_topology(self):
        for collector in ("r2", "r4", "r5", "r6"):
            with self.subTest(collector=collector):
                code, output = self._run(["--only", collector, "--no-write"])
                self.assertEqual(code, 2)
                self.assertIn(f"[{collector.upper()}]", output)

    def test_skip_counts_are_never_promoted_to_pass(self):
        receipt = r2_business_loop.run()
        summary = summarize(receipt.checks)
        self.assertEqual(summary["pass"], 0)
        self.assertEqual(summary["fail"], 0)
        self.assertGreater(summary["skip"], 0)
        self.assertTrue(receipt.summary()["evidence_free"])

    def test_receipt_written_to_disk_is_redacted_and_complete(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            buffer = io.StringIO()
            with clean_environment(), contextlib.redirect_stdout(buffer):
                code = harness.main(["--only", "r2", "--receipt-dir", str(target)])
            self.assertEqual(code, 2)
            files = sorted(target.glob("*.json"))
            self.assertTrue(files, "expected at least one receipt")
            names = {path.name for path in files}
            self.assertTrue(any(name.startswith("acceptance-summary-") for name in names))
            summary = next(path for path in files if path.name.startswith("acceptance-summary-"))
            text = summary.read_text(encoding="utf-8")
            # R2 has no topology: nothing ran, so the summary must say so loudly.
            self.assertIn('"no_pass_claimed": true', text)
            self.assertIn('"evidence_free": true', text)
            self.assertNotIn("pt_cap_", text)

    def test_receipt_written_to_disk_has_every_documented_field(self):
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory)
            buffer = io.StringIO()
            with clean_environment(), contextlib.redirect_stdout(buffer):
                harness.main(["--only", "r2", "--receipt-dir", str(target)])
            receipt = next(
                path
                for path in sorted(target.glob("*.json"))
                if not path.name.startswith("acceptance-summary-")
            )
            document = json.loads(receipt.read_text(encoding="utf-8"))
            for key in (
                "source_sha",
                "started_at",
                "finished_at",
                "environment",
                "checks",
                "untested",
                "summary",
            ):
                self.assertIn(key, document)
            self.assertEqual(len(document["source_sha"]), 40)
            self.assertTrue(document["environment"]["cpu_count"])
            self.assertTrue(document["untested"])
            self.assertTrue(document["checks"])
            for check in document["checks"]:
                self.assertIn(check["status"], {"PASS", "FAIL", "SKIP", "NOT_TESTED"})
                self.assertTrue(check["result_digest"].startswith("sha256:"))


class GatingTests(unittest.TestCase):
    """Write/destructive flags must gate the checks, not silently pass them."""

    def test_r2_skips_the_business_loop_without_write_permission(self):
        topology = Topology.from_env()
        self.assertFalse(topology.allow_writes)
        checks = r2_business_loop.collect(topology)
        # Without a configured topology the collector stops at the health probe.
        self.assertEqual(len(checks), 1)
        self.assertEqual(checks[0].status, SKIP)
        self.assertIn("topology not configured", checks[0].notes)

    def test_r2_skips_writes_and_rejections_without_write_permission(self):
        with clean_environment(
            PT_ACCEPTANCE_BASE_URL="https://privacytrace.test",
            PT_ACCEPTANCE_HOST="privacytrace.test",
            PT_ACCEPTANCE_INSTANCE_ID="0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
        ):
            topology = Topology.from_env()
        # No server is listening, so the transport probe SKIPs; the point of this
        # test is that every later section is gated rather than faked.
        checks = r2_business_loop.collect(topology)
        statuses = {check.status for check in checks}
        self.assertLessEqual(statuses, {"PASS", "FAIL", "SKIP"})
        self.assertNotIn("PASS", statuses)

    def test_r4_skips_every_injection_without_destructive_permission(self):
        with clean_environment():
            checks = r4_fault_recovery.collect()
        injection = [check for check in checks if check.name.startswith("r4.restart")]
        self.assertEqual(len(injection), 4)
        for check in injection:
            self.assertEqual(check.status, SKIP)
            self.assertIn("ALLOW_DESTRUCTIVE", check.notes)

    def test_r5_never_counts_an_unexecuted_backup_plan_as_evidence(self):
        with clean_environment():
            receipt = r5_backup_recovery.run()
        phases = [check for check in receipt.checks if check.name.startswith("r5.")]
        self.assertEqual(len(phases), 4)
        for check in phases:
            self.assertIn(check.status, {"SKIP", "NOT_TESTED"})
        self.assertEqual(receipt.summary()["pass"], 0)

    def test_r6_capacity_rows_are_not_tested_not_passed(self):
        table = r6_capacity_audit.collect()[1]["capacity_table"]
        for scale in r6_capacity_audit.DECLARED_SCALES:
            self.assertEqual(table[scale]["status"], "NOT_TESTED")

    def test_r6_secret_audit_runs_without_a_topology(self):
        check = r6_capacity_audit._secret_audit()
        self.assertIn(check.status, {"PASS", "FAIL", "SKIP"})
        if check.status == "FAIL":
            self.fail(f"tracked source tripped the secret audit: {check.detail}")


class ScopeReleaseTests(unittest.TestCase):
    """Released scopes must not hold a client draft-quota slot or be deleted twice."""

    def test_release_forgets_the_scope_so_cleanup_does_not_repeat_the_delete(self):
        topology = Topology.from_env()
        scope = r2_business_loop.Scope(
            name="released", draft_id="released-draft", token="capability", revision=1
        )
        before = list(r2_business_loop.CREATED_SCOPES)
        r2_business_loop.CREATED_SCOPES.append((topology, scope))
        calls = []

        def fake_request(topology, path, **kwargs):
            calls.append((path, kwargs.get("method", "GET")))
            return HttpResult(method="DELETE", path=path, status=200, duration_s=0.01)

        try:
            with patch.object(r2_business_loop, "request", fake_request):
                self.assertEqual(r2_business_loop.release_scope(topology, scope), 200)
                self.assertNotIn((topology, scope), r2_business_loop.CREATED_SCOPES)
                self.assertEqual(r2_business_loop.cleanup_created_scopes(), [])
        finally:
            r2_business_loop.CREATED_SCOPES[:] = before
        self.assertEqual(calls, [(f"/api/v1/web/drafts/{scope.draft_id}", "DELETE")])


class TopologyEnvironmentTests(unittest.TestCase):
    def test_missing_variables_are_named(self):
        with clean_environment():
            topology = Topology.from_env()
        self.assertFalse(topology.configured)
        self.assertEqual(
            topology.missing(),
            [
                "PT_ACCEPTANCE_BASE_URL",
                "PT_ACCEPTANCE_HOST",
                "PT_ACCEPTANCE_INSTANCE_ID",
            ],
        )

    def test_operator_commands_are_composed_from_environment_only(self):
        with clean_environment(
            PT_ACCEPTANCE_BASE_URL="https://privacytrace.test",
            PT_ACCEPTANCE_HOST="privacytrace.test",
            PT_ACCEPTANCE_INSTANCE_ID="0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
            PT_ACCEPTANCE_ENV_FILE="/etc/privacytrace/deployment.env",
            PT_ACCEPTANCE_COMPOSE_FILES="/opt/privacytrace/deploy/compose.yaml",
            PT_ACCEPTANCE_COMPOSE_PROJECT="privacytrace",
            PT_ACCEPTANCE_ALLOW_WRITES="1",
        ):
            topology = Topology.from_env()
        self.assertTrue(topology.configured)
        command = topology.compose_command("ps")
        self.assertEqual(command[:2], ["docker", "compose"])
        self.assertIn("privacytrace", command)
        # Path normalisation is platform-specific, so compare resolved paths.
        self.assertIn(str(Path("/opt/privacytrace/deploy/compose.yaml")), command)
        self.assertIn(str(Path("/etc/privacytrace/deployment.env")), command)
        self.assertTrue(topology.allow_writes)
        self.assertFalse(topology.allow_destructive)

    def test_docker_wrapper_is_split_into_argv(self):
        with clean_environment(PT_ACCEPTANCE_DOCKER="wsl -d Ubuntu-24.04 -- bash -lc"):
            topology = Topology.from_env()
        self.assertEqual(
            topology.docker_command("version"),
            ["wsl", "-d", "Ubuntu-24.04", "--", "bash", "-lc", "version"],
        )


class DeploymentRegressionTests(unittest.TestCase):
    def test_provision_failure_before_owner_marker_removes_allocated_root(self):
        from types import SimpleNamespace

        from acceptance import provision

        with tempfile.TemporaryDirectory() as parent:
            allocated = Path(parent) / "allocated"
            allocated.mkdir()
            with (
                patch.object(provision, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)),
                patch.object(provision.tempfile, "mkdtemp", return_value=str(allocated)),
                patch.object(provision, "_populate", side_effect=RuntimeError("missing image")),
                self.assertRaises(RuntimeError),
            ):
                provision.create("api", "web", "runner", "scanner")
            self.assertEqual(list(Path(parent).iterdir()), [])

    def test_provision_failure_after_owner_marker_reports_only_cleanup_location(self):
        from types import SimpleNamespace

        from acceptance import provision

        def fail_after_marker(root, *_args):
            (root / "owner.json").write_text("{}")
            (root / "private-canary").write_text("synthetic-sensitive-value")
            raise RuntimeError("failed initialization")

        with tempfile.TemporaryDirectory() as parent:
            allocated = Path(parent) / "allocated"
            allocated.mkdir()
            output = io.StringIO()
            with (
                patch.object(provision, "os", SimpleNamespace(name="posix", geteuid=lambda: 0)),
                patch.object(provision.tempfile, "mkdtemp", return_value=str(allocated)),
                patch.object(provision, "_populate", side_effect=fail_after_marker),
                contextlib.redirect_stdout(output),
                self.assertRaises(RuntimeError),
            ):
                provision.create("api", "web", "runner", "scanner")
            roots = list(Path(parent).iterdir())
            self.assertEqual(len(roots), 1)
            self.assertEqual(output.getvalue().strip(), f"FAILED_LAB={roots[0]}")
            self.assertNotIn("synthetic-sensitive-value", output.getvalue())

    @unittest.skipUnless(sys.platform.startswith("linux"), "native Linux cleanup contract")
    def test_shell_cleanup_registers_failed_lab_and_removes_own_build_directory(self):
        script = (DEPLOY / "check_acceptance.sh").read_text()
        cleanup = (
            "cleanup() {" + script.split("cleanup() {", 1)[1].split("\ntrap cleanup EXIT", 1)[0]
        )
        with tempfile.TemporaryDirectory() as logs:
            temporary = Path(tempfile.mkdtemp(prefix="pt81-build-", dir="/var/tmp"))
            commands = Path(logs) / "commands"
            (temporary / "up-1.log").write_text("FAILED_LAB=/var/tmp/pt81-000000000000\n")
            (temporary / "docker").write_text("synthetic CLI copy")
            source = (
                "set -euo pipefail\n"
                'temporary="$PT_BUILD_ROOT"\nstates=()\n'
                'python3() { printf "%s\\n" "$*" >> "$PT_CLEANUP_COMMANDS"; }\n'
                + cleanup
                + "\ncleanup\n"
            )
            try:
                result = subprocess.run(
                    ["bash", "-c", source],
                    capture_output=True,
                    text=True,
                    timeout=10,
                    env={
                        **os.environ,
                        "PT_BUILD_ROOT": str(temporary),
                        "PT_CLEANUP_COMMANDS": str(commands),
                    },
                )
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertFalse(temporary.exists())
                self.assertIn(
                    "down --state /var/tmp/pt81-000000000000 --purge", commands.read_text()
                )
            finally:
                if temporary.exists():
                    import shutil

                    shutil.rmtree(temporary)

    def test_metadata_inspections_cannot_replace_actual_scan_isolation_evidence(self):
        from types import SimpleNamespace

        from acceptance.r3_isolation import scan_examples

        metadata = {
            "error": None,
            "receipt": {"image_id": "scanner"},
            "result": {
                "tools": {},
                "package_file": {"package_name": "single"},
                "apk_sha256": "hash",
            },
        }
        fixtures = SimpleNamespace(single_package="single", single_sha256="hash", set_package="set")
        with self.assertRaises(AssertionError):
            scan_examples([metadata, metadata], "scanner", fixtures)

    def test_declared_length_probe_uses_system_trust_when_custom_ca_is_absent(self):
        from acceptance.topology import declared_length_rejection

        topology = Topology("https://privacytrace.test", "privacytrace.test", "instance")
        with (
            patch("acceptance.topology.ssl.create_default_context") as context,
            patch("acceptance.topology.http.client.HTTPSConnection") as connection,
        ):
            connection.return_value.getresponse.return_value.status = 413
            self.assertEqual(declared_length_rejection(topology, "/upload", 1000), 413)
        context.assert_called_once_with(cafile=None)

    def test_orphan_disappearing_during_inspection_is_not_a_drill_failure(self):
        from types import SimpleNamespace

        from acceptance.fault_drill import _owned_scanners

        disappeared = RuntimeError("deployment command failed")
        disappeared.stderr = "error: no such object: removed-container\n"
        disappeared.stdout = "[]"
        with patch(
            "acceptance.fault_drill.execute", side_effect=["removed-container", disappeared]
        ):
            self.assertEqual(_owned_scanners(SimpleNamespace(root=Path("/owned"))), [])

    def test_orphan_inspection_does_not_hide_daemon_failures(self):
        from types import SimpleNamespace

        from acceptance.fault_drill import _owned_scanners

        unavailable = RuntimeError("daemon unavailable")
        unavailable.stderr = "Cannot connect to the Docker daemon"
        with patch("acceptance.fault_drill.execute", side_effect=["container", unavailable]):
            with self.assertRaises(RuntimeError):
                _owned_scanners(SimpleNamespace(root=Path("/owned")))

    def test_fault_override_handles_roles_inherited_from_base_compose(self):
        from acceptance.fault_drill import scanner_override

        original = {"services": {"runner": {"environment": {"EXISTING": "preserved"}}}}
        candidate = scanner_override(original, "sha256:controlled")
        self.assertNotIn("api", original["services"])
        self.assertNotIn("worker", original["services"])
        for role in ("api", "worker", "runner"):
            self.assertEqual(
                candidate["services"][role]["environment"]["PRIVACYTRACE_RUNNER_IMAGE_ID"],
                "sha256:controlled",
            )
        self.assertEqual(candidate["services"]["runner"]["environment"]["EXISTING"], "preserved")

    def test_capacity_table_uses_scanner_memory_instead_of_consumer_memory(self):
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from acceptance.receipt import CheckRecorder

        sample = r6_capacity_audit.CapacitySample("concurrency_1_single_apk", peak_memory_bytes=20)
        check = CheckRecorder("memory", "sample").pass_("observed")
        sampler = MagicMock()
        sampler.__enter__.return_value = sampler
        sampler.result.return_value = {"scanner_sampled_peak_memory_bytes": 900}
        with (
            patch.dict(os.environ, {"PT_ACCEPTANCE_LAB_STATE": "/var/tmp/owned"}),
            patch("acceptance.provision.Laboratory"),
            patch("acceptance.metrics.Sampler", return_value=sampler),
            patch.object(r6_capacity_audit, "_measure_round", return_value=(check, sample)),
        ):
            result, measured = r6_capacity_audit._measure(
                SimpleNamespace(allow_writes=True), sample.scale, repetitions=3, budget_s=20
            )
        self.assertEqual(measured.peak_memory_bytes, 900)
        self.assertEqual(result.detail["table"]["peak_memory_bytes"], 900)
        self.assertEqual(result.detail["worker_peak_memory_bytes"], 20)


if __name__ == "__main__":
    unittest.main()
