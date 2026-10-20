"""Redaction and receipt-integrity tests for the acceptance harness.

These tests use synthetic placeholders only. Any string that looks like a live
credential in this file is deliberately fake and is never a working secret.
"""

import json
import sys
import tempfile
import unittest
from pathlib import Path

# ``unittest discover -s deploy/tests`` only puts deploy/tests on sys.path, so the
# package siblings (deploy/acceptance) are added explicitly, as test_deployment does.
DEPLOY = Path(__file__).resolve().parents[1]
if str(DEPLOY) not in sys.path:
    sys.path.insert(0, str(DEPLOY))

from acceptance.receipt import (  # noqa: E402
    FAIL,
    NOT_TESTED,
    PASS,
    SKIP,
    Check,
    CheckRecorder,
    Receipt,
    RedactionLeak,
    conclusion,
    is_evidence_free,
    render_summary,
    summarize,
    utc_now,
)
from acceptance.redaction import (  # noqa: E402
    MASK,
    PRIVATE_HOME_MASK,
    PRIVATE_KEY_MASK,
    PRIVATE_PATH_MASK,
    find_secret_markers,
    is_clean,
    redact_text,
    redact_value,
)


class RedactionTests(unittest.TestCase):
    def test_capability_token_is_masked_everywhere(self):
        synthetic = "pt_cap_" + "A" * 40
        text = f"Authorization: Bearer {synthetic}\nlog line token={synthetic}"
        redacted = redact_text(text)
        self.assertNotIn(synthetic, redacted)
        self.assertNotIn("A" * 40, redacted)
        # Both the bearer value and the raw token are masked; the assignment key stays.
        self.assertGreaterEqual(redacted.count(MASK), 2)
        self.assertIn("token=" + MASK, redacted)

    def test_database_password_in_dsn_is_masked_but_host_kept(self):
        text = "postgresql+psycopg://privacytrace_runtime:synthetic-pw@postgres:5432/privacytrace"
        redacted = redact_text(text)
        self.assertNotIn("synthetic-pw", redacted)
        self.assertIn("postgres:5432/privacytrace", redacted)
        self.assertIn("postgresql+psycopg://", redacted)

    def test_redis_and_amqp_credentials_are_masked(self):
        for url, secret in (
            ("redis://:synthetic-broker-pw@redis:6379/1", "synthetic-broker-pw"),
            ("amqp://user:synthetic-amqp-pw@broker:5672/vhost", "synthetic-amqp-pw"),
        ):
            with self.subTest(url=url):
                redacted = redact_text(url)
                self.assertNotIn(secret, redacted)
                self.assertIn(MASK, redacted)

    def test_private_key_block_is_replaced_whole(self):
        block = (
            "-----BEGIN OPENSSH PRIVATE KEY-----\n"
            "syntheticbodyline\n"
            "-----END OPENSSH PRIVATE KEY-----"
        )
        redacted = redact_text(f"key file:\n{block}\ndone")
        self.assertIn(PRIVATE_KEY_MASK, redacted)
        self.assertNotIn("syntheticbodyline", redacted)
        self.assertIn("done", redacted)

    def test_private_home_paths_are_masked_on_every_platform(self):
        for path in (
            "/home/oasis/projects/privacytrace",
            "/Users/someone/Private/work",
            "C:\\Users\\Oasis\\Documents\\secrets",
            "/root/.ssh/id_ed25519",
        ):
            with self.subTest(path=path):
                redacted = redact_text(f"reading {path}/file.txt")
                self.assertIn(PRIVATE_HOME_MASK, redacted)
                self.assertNotIn("oasis", redacted.lower())
                self.assertNotIn("someone", redacted.lower())

    def test_inline_password_assignment_is_masked(self):
        redacted = redact_text("config: password = synthetic-value-123\n")
        self.assertNotIn("synthetic-value-123", redacted)
        self.assertIn("password", redacted)

    def test_extra_paths_are_masked_with_both_separators(self):
        path = "/srv/private/acceptance-run"
        redacted = redact_text(
            f"working in {path} and later C:\\srv\\private\\acceptance-run",
            extra_paths=[path],
        )
        self.assertIn(PRIVATE_PATH_MASK, redacted)
        self.assertNotIn("/srv/private/acceptance-run", redacted)

    def test_ordinary_operational_text_survives_untouched(self):
        samples = [
            "GET /api/v1/web/drafts returned HTTP 200 in 0.012s",
            "PT_SECRETS_DIR=/etc/privacytrace/secrets",
            "PRIVACYTRACE_DATABASE_URL_FILE=/run/secrets/runtime_database_url",
            "image postgres:17.9-alpine@sha256:" + "a" * 64,
            "scope_id=0163a8b5-3eed-481a-bfb0-31fd3fe523dc",
            "compose --profile reclamation run --rm --no-deps reclaim",
            "/var/lib/privacytrace/jobs and /var/lib/privacytrace-deletions",
            "result_digest=sha256:0123456789abcdef",
            "Host: privacytrace.test:443",
            "www-authenticate: Basic realm=synthetic",
        ]
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertEqual(redact_text(sample), sample)

    def test_redaction_is_idempotent(self):
        text = "pt_cap_" + "B" * 30 + " postgres://u:p@db/x"
        once = redact_text(text)
        self.assertEqual(redact_text(once), once)

    def test_recursive_value_redaction_covers_nested_structures(self):
        token = "pt_cap_" + "C" * 30
        document = {
            "checks": [{"notes": f"used {token}"}],
            "paths": ("/home/oasis/private",),
            "count": 3,
            "flag": True,
            "empty": None,
        }
        redacted = redact_value(document)
        self.assertNotIn(token, json.dumps(redacted))
        self.assertIn(PRIVATE_HOME_MASK, json.dumps(redacted))
        self.assertEqual(redacted["count"], 3)
        self.assertIs(redacted["flag"], True)
        self.assertIsNone(redacted["empty"])

    def test_marker_scan_reports_counts_not_matches(self):
        text = "pt_cap_" + "D" * 30 + " and postgres://u:p@db/x"
        found = find_secret_markers(text)
        self.assertEqual(found.get("capability-token"), 1)
        self.assertEqual(found.get("url-credentials"), 1)
        self.assertNotIn("D" * 30, json.dumps(found))
        self.assertFalse(is_clean(text))
        self.assertTrue(is_clean("nothing sensitive here"))

    def test_source_scan_ignores_documented_path_assignments(self):
        text = "PT_SECRETS_DIR=/etc/privacytrace/secrets\n"
        self.assertEqual(
            find_secret_markers(
                text,
                categories=("capability-token", "private-key-block", "url-credentials"),
            ),
            {},
        )


class StatusAccountingTests(unittest.TestCase):
    def _check(self, status, ticket="R2"):
        recorder = CheckRecorder("check", "command", ticket=ticket)
        if status == PASS:
            return recorder.pass_("ok")
        if status == FAIL:
            return recorder.fail("bad")
        if status == SKIP:
            return recorder.skip("missing topology")
        return recorder.not_tested("scale not measured")

    def test_skip_and_not_tested_never_become_pass(self):
        checks = [
            self._check(PASS),
            self._check(FAIL),
            self._check(SKIP),
            self._check(NOT_TESTED),
        ]
        summary = summarize(checks)
        self.assertEqual(summary["pass"], 1)
        self.assertEqual(summary["fail"], 1)
        self.assertEqual(summary["skip"], 1)
        self.assertEqual(summary["not_tested"], 1)
        self.assertEqual(summary["total"], 4)
        # PASS rate is over the checks that actually ran, not over all checks.
        self.assertEqual(summary["verified"], 2)
        self.assertEqual(summary["pass_rate_of_verified"], 0.5)

    def test_all_skipped_round_is_evidence_free_without_a_rate(self):
        summary = summarize([self._check(SKIP), self._check(SKIP), self._check(NOT_TESTED)])
        self.assertEqual(summary["conclusion"], "NO_REAL_EVIDENCE")
        self.assertIsNone(summary["pass_rate_of_verified"])
        self.assertTrue(is_evidence_free(summary))

    def test_all_pass_round_is_all_pass(self):
        summary = summarize([self._check(PASS), self._check(PASS)])
        self.assertEqual(summary["conclusion"], "ALL_PASS")
        self.assertEqual(summary["pass_rate_of_verified"], 1.0)
        self.assertFalse(is_evidence_free(summary))

    def test_failure_dominates_partial_and_evidence(self):
        summary = summarize([self._check(PASS), self._check(SKIP), self._check(FAIL)])
        self.assertEqual(summary["conclusion"], "FAILURES")
        self.assertFalse(is_evidence_free(summary))

    def test_per_ticket_counts_stay_separated(self):
        summary = summarize(
            [
                self._check(PASS, ticket="R2"),
                self._check(SKIP, ticket="R4"),
                self._check(NOT_TESTED, ticket="R6"),
            ]
        )
        self.assertEqual(summary["by_ticket"]["R2"]["pass"], 1)
        self.assertEqual(summary["by_ticket"]["R4"]["skip"], 1)
        self.assertEqual(summary["by_ticket"]["R6"]["not_tested"], 1)

    def test_conclusion_matrix_is_explicit(self):
        self.assertEqual(conclusion({PASS: 0, FAIL: 0, SKIP: 3, NOT_TESTED: 0}), "NO_REAL_EVIDENCE")
        self.assertEqual(conclusion({PASS: 1, FAIL: 1, SKIP: 0, NOT_TESTED: 0}), "FAILURES")
        self.assertEqual(conclusion({PASS: 1, FAIL: 0, SKIP: 1, NOT_TESTED: 0}), "PARTIAL")
        self.assertEqual(conclusion({PASS: 2, FAIL: 0, SKIP: 0, NOT_TESTED: 0}), "ALL_PASS")

    def test_unknown_status_is_rejected(self):
        with self.assertRaises(ValueError):
            Check(
                name="x",
                status="PASSED",
                command="c",
                started_at=utc_now(),
                duration_s=0.0,
                result_digest="sha256:0",
            )
        with self.assertRaises(ValueError):
            summarize([{"status": "OK"}])


class RecorderTests(unittest.TestCase):
    def test_skip_requires_a_reason(self):
        with self.assertRaises(ValueError):
            CheckRecorder("check", "command").skip("   ")

    def test_not_tested_requires_a_scope(self):
        with self.assertRaises(ValueError):
            CheckRecorder("check", "command").not_tested("")

    def test_check_carries_every_required_field(self):
        recorder = CheckRecorder("r2.example", "GET /api/v1/health", ticket="R2")
        check = recorder.pass_("observed", status=200)
        for field in (
            "name",
            "status",
            "command",
            "started_at",
            "duration_s",
            "result_digest",
            "notes",
        ):
            self.assertIn(field, check.as_dict())
        self.assertEqual(check.as_dict()["ticket"], "R2")
        self.assertEqual(check.detail["status"], 200)
        self.assertTrue(check.result_digest.startswith("sha256:"))
        self.assertGreaterEqual(check.duration_s, 0.0)

    def test_run_returns_skip_for_expected_precondition_miss(self):
        class Missing(RuntimeError):
            pass

        recorder = CheckRecorder("check", "command")
        check = recorder.run(
            lambda: (_ for _ in ()).throw(Missing("no topology")), failures=(Missing,)
        )
        self.assertEqual(check.status, SKIP)
        self.assertIn("no topology", check.notes)

    def test_run_returns_fail_for_unexpected_error(self):
        recorder = CheckRecorder("check", "command")
        check = recorder.run(lambda: (_ for _ in ()).throw(ValueError("boom")))
        self.assertEqual(check.status, FAIL)


class ReceiptTests(unittest.TestCase):
    def _receipt(self):
        receipt = Receipt(scope="unit-test", source_sha="0" * 40)
        receipt.environment = {"os": "test", "cpu_count": 1, "memory_bytes": 1024}
        recorder = CheckRecorder("r2.example", "GET /api/v1/health", ticket="R2")
        receipt.add(recorder.pass_("ok"))
        receipt.untested_scope("concurrency 2 never measured")
        receipt.finished_at = utc_now()
        return receipt

    def test_receipt_document_has_the_required_top_level_keys(self):
        document = self._receipt().to_dict()
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
        self.assertEqual(document["untested"], ["concurrency 2 never measured"])
        self.assertIsInstance(document["summary"], dict)
        check = document["checks"][0]
        for key in (
            "name",
            "status",
            "command",
            "started_at",
            "duration_s",
            "result_digest",
            "notes",
        ):
            self.assertIn(key, check)

    def test_receipt_never_contains_a_capability_token(self):
        receipt = self._receipt()
        token = "pt_cap_" + "E" * 32
        recorder = CheckRecorder("r2.token", "POST /api/v1/web/drafts", ticket="R2")
        receipt.add(recorder.pass_(f"issued {token}", token_hint=token))
        text = receipt.to_json()
        self.assertNotIn(token, text)
        self.assertIn(MASK, text)

    def test_receipt_write_refuses_leftover_credentials(self):
        receipt = self._receipt()
        leaking = "dsn postgres://user:synthetic-secret@db/x"
        # Neutering the masker proves the writer keeps its own final guard: a
        # defect in redaction must fail the run, not publish a credential.
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "receipt.json"
            original = receipt.to_json
            receipt.to_json = lambda: leaking  # type: ignore[method-assign]
            try:
                with self.assertRaises(RedactionLeak):
                    receipt.write(target)
            finally:
                receipt.to_json = original  # type: ignore[method-assign]
            self.assertFalse(target.exists())

    def test_receipt_writes_valid_utf8_json(self):
        receipt = self._receipt()
        with tempfile.TemporaryDirectory() as directory:
            target = receipt.write(Path(directory) / "receipt.json")
            document = json.loads(target.read_text(encoding="utf-8"))
            self.assertEqual(document["scope"], "unit-test")

    def test_render_summary_states_no_real_evidence(self):
        receipt = Receipt(scope="skipped", source_sha="0" * 40)
        receipt.add(CheckRecorder("x", "c").skip("no topology"))
        text = render_summary(receipt.summary(), scope="skipped", source_sha="0" * 40)
        self.assertIn("NO_REAL_EVIDENCE", text)
        self.assertIn("SKIP         : 1", text)
        self.assertIn("PASS         : 0", text)


if __name__ == "__main__":
    unittest.main()
