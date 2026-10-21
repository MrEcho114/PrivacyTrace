"""The capacity drill must drive real identities and never print a token as evidence."""

import json
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

from acceptance import capacity_drill, client_probe  # noqa: E402


class _Lab:
    project = "pt81-0123456789ab"
    state = {"images": {"api": "sha256:api-image"}}


class _Topology:
    host = "privacytrace.test"


class ProbeTests(unittest.TestCase):
    def _drive(self, steps, replies):
        seen = []

        def fake(base_url, host, method, path, *, body=None, token="", timeout=120):
            seen.append({"method": method, "path": path, "body": body, "token": token})
            return replies.pop(0)

        with tempfile.NamedTemporaryFile(suffix=".apk", delete=False) as handle:
            handle.write(b"apk-bytes")
        plan = {
            "base_url": "http://api:8000",
            "host": "privacytrace.test",
            "apk": handle.name,
            "steps": steps,
        }
        with patch.object(client_probe, "call", fake), patch.object(
            client_probe.socket, "gethostbyname", lambda name: "10.200.0.4"
        ):
            result = client_probe.run(plan)
        Path(handle.name).unlink()
        return result, seen

    def test_one_identity_walks_draft_upload_start_and_state(self):
        result, seen = self._drive(
            [
                {"op": "draft", "draft": "a", "name": "a"},
                {"op": "upload", "draft": "a"},
                {"op": "start", "draft": "a"},
                {"op": "state", "draft": "a"},
            ],
            [
                {"status": 200, "code": None, "retry_after": None,
                 "json": {"id": "d-1", "capability_token": "cap-1", "revision": 1},
                 "body_bytes": 2},
                {"status": 200, "code": None, "retry_after": None,
                 "json": {"revision": 2}, "body_bytes": 2},
                {"status": 200, "code": None, "retry_after": None,
                 "json": {"id": "job-1"}, "body_bytes": 2},
                {"status": 200, "code": None, "retry_after": None,
                 "json": {"state": "QUEUED"}, "body_bytes": 2},
            ],
        )

        self.assertEqual(
            [item["path"] for item in seen],
            [
                "/api/v1/web/drafts",
                "/api/v1/web/drafts/d-1/apk",
                "/api/v1/web/drafts/d-1/start",
                "/api/v1/jobs/job-1",
            ],
        )
        self.assertEqual(seen[1]["body"], b"apk-bytes")
        self.assertEqual(seen[1]["token"], "cap-1")
        # The start contract requires a 32-hex idempotency key, not the draft
        # label: a label is accepted by the body model but rejected as input.
        self.assertEqual(seen[2]["body"]["revision"], 2)
        self.assertRegex(seen[2]["body"]["request_id"], r"^[a-f0-9]{32}$")
        self.assertEqual(result["peer_ip"], "10.200.0.4")
        self.assertEqual(result["steps"][2]["job_id"], "job-1")
        self.assertEqual(result["steps"][3]["state"], "QUEUED")
        self.assertNotIn("json", result["steps"][0])

    def test_a_refused_draft_is_recorded_not_raised(self):
        result, seen = self._drive(
            [{"op": "draft", "draft": "a", "name": "a"}],
            [
                {"status": 429, "code": "CLIENT_DRAFT_QUOTA_REACHED", "retry_after": "5",
                 "json": {"detail": "CLIENT_DRAFT_QUOTA_REACHED"}, "body_bytes": 29},
            ],
        )

        step = result["steps"][0]
        self.assertEqual(step["status"], 429)
        self.assertEqual(step["code"], "CLIENT_DRAFT_QUOTA_REACHED")
        self.assertEqual(step["retry_after"], "5")
        self.assertNotIn("draft_id", step)
        self.assertEqual(len(seen), 1)

    def test_an_unknown_step_is_a_programming_error(self):
        with self.assertRaises(ValueError):
            self._drive([{"op": "explode"}], [])


class DrillTests(unittest.TestCase):
    def test_scopes_join_draft_and_job_identity(self):
        scopes = capacity_drill._scopes(
            {
                "steps": [
                    {"op": "draft", "draft": "a", "draft_id": "d-1", "token": "cap-1"},
                    {"op": "start", "draft": "a", "job_id": "job-1"},
                    {"op": "draft", "draft": "b", "status": 429, "code": "DRAFT_QUOTA_REACHED"},
                ]
            }
        )

        self.assertEqual(scopes, {"a": {"draft_id": "d-1", "token": "cap-1", "job_id": "job-1"}})

    def test_identity_runs_a_read_only_helper_and_parses_its_last_line(self):
        calls = []

        def fake(argv, **kwargs):
            calls.append((argv, kwargs))
            return 'compose noise\n{"peer_ip": "10.200.0.4", "steps": []}\n'

        with patch.object(capacity_drill, "execute", fake):
            result = capacity_drill._identity(
                _Lab(),
                _Topology(),
                Path("/var/tmp/lab/probe"),
                [{"op": "draft", "name": "a", "draft": "a"}],
            )

        self.assertEqual(result["peer_ip"], "10.200.0.4")
        argv, kwargs = calls[0]
        self.assertEqual(argv[:4], ["docker", "run", "--rm", f"--network={_Lab.project}_api"])
        self.assertIn("--entrypoint", argv)
        self.assertIn("/opt/venv/bin/python", argv)
        self.assertNotIn("--ip", " ".join(argv))
        self.assertIn("/var/tmp/lab/probe:/probe:ro", " ".join(argv).replace("\\", "/"))
        self.assertIn("sha256:api-image", argv)
        self.assertEqual(argv[argv.index("sha256:api-image") + 1], "/probe/client_probe.py")
        plan = json.loads(argv[argv.index("sha256:api-image") + 2])
        self.assertEqual(plan["base_url"], "http://api:8000")
        self.assertEqual(plan["host"], "privacytrace.test")
        self.assertEqual(plan["apk"], "/probe/fixture.apk")
        self.assertEqual(kwargs["timeout"], 600)

    def test_identity_can_claim_a_specific_address(self):
        calls = []

        def fake(argv, **kwargs):
            calls.append(argv)
            return '{"peer_ip": "10.200.0.99", "steps": []}\n'

        with patch.object(capacity_drill, "execute", fake):
            capacity_drill._identity(
                _Lab(),
                _Topology(),
                Path("/var/tmp/lab/probe"),
                [{"op": "draft", "name": "a", "draft": "a"}],
                address="10.200.0.99",
            )

        self.assertIn("--ip=10.200.0.99", calls[0])


if __name__ == "__main__":
    unittest.main()
