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

    def test_docker_refusal_keeps_the_first_stderr_line_that_names_the_cause(self):
        class _StateLab:
            project = "pt81-0123456789ab"
            root = Path("/var/tmp/pt81-0123456789ab")

        refusal = RuntimeError("deployment command failed (125): docker")
        refusal.stderr = (
            "docker: invalid reference format.\n"
            "Run 'docker run --help' for more information.\n"
        )

        with patch.object(capacity_drill, "execute", side_effect=refusal):
            with self.assertRaises(RuntimeError) as caught:
                capacity_drill._docker(_StateLab(), ["docker", "run"], what="client container")

        message = str(caught.exception)
        self.assertIn("invalid reference format", message)
        self.assertIn("client container refused", message)


class AddressTests(unittest.TestCase):
    def _bridge(self, *subnets, containers=None):
        address = "10.200.0.40/24"
        return {
            "Name": "pt81-0123456789ab_api",
            "IPAM": {"Config": [{"Subnet": subnet} for subnet in subnets]},
            "Containers": containers
            if containers is not None
            else {"existing": {"IPv4Address": address}},
        }

    def test_a_dual_stack_bridge_yields_ipv4_addresses_from_the_ipv4_subnet(self):
        bridge = self._bridge("fd00:1::/64", "10.200.0.0/24")

        addresses = capacity_drill._addresses(bridge, 3)

        self.assertEqual(len(set(addresses)), 3)
        for address in addresses:
            self.assertRegex(address, r"^10\.200\.0\.\d+$")
        self.assertNotIn("10.200.0.40", addresses)

    def test_a_bridge_without_ipv4_room_is_refused_with_the_subnets_named(self):
        bridge = self._bridge("fd00:1::/64")

        with self.assertRaises(RuntimeError) as caught:
            capacity_drill._addresses(bridge, 3)

        self.assertIn("no IPv4 subnet", str(caught.exception))
        self.assertIn("fd00:1::/64", str(caught.exception))


class _RunLab:
    def __init__(self):
        self.calls = []

    def run(self, *argv):
        self.calls.append(argv)


class _Sampler:
    def __init__(self, lab):
        self.lab = lab

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def result(self):
        return {"scanner_sampled_peak_concurrency": 1}


def _identity_steps(name, *, start_status=200, start_code=None, draft_id=None):
    steps = [{"op": "draft", "draft": name, "status": 200}]
    if draft_id:
        steps[0]["draft_id"] = draft_id
        steps[0]["token"] = "cap-" + draft_id
    steps.append({"op": "upload", "draft": name, "status": 200})
    started = {"op": "start", "draft": name, "status": start_status}
    if start_code:
        started["code"] = start_code
    else:
        started["job_id"] = "job-" + name
    steps.append(started)
    steps.append({"op": "state", "draft": name, "status": 200, "state": "QUEUED"})
    return {"steps": steps}


class CleanupTests(unittest.TestCase):
    """A refused drill must not leave a draft behind: it spends the next run's quota."""

    def _patch(self, plans, lab):
        deleted = []

        def fake_request(topology, path, **kwargs):
            if kwargs.get("method") == "DELETE":
                deleted.append(path)
            return None

        stack = [
            patch.object(capacity_drill, "_prepare", lambda _lab: Path("probe")),
            patch.object(
                capacity_drill,
                "_api_network",
                lambda _lab: {"Name": "net", "IPAM": {"Config": [{"Subnet": "10.200.0.0/24"}]}},
            ),
            patch.object(
                capacity_drill,
                "_addresses",
                lambda api, count: [f"10.200.0.{40 + i}" for i in range(count)],
            ),
            patch.object(capacity_drill, "_identity", lambda *args, **kwargs: plans.pop(0)),
            patch.object(capacity_drill, "_wait", lambda *args, **kwargs: "SUCCEEDED"),
            patch.object(capacity_drill, "Sampler", _Sampler),
            patch.object(capacity_drill, "request", fake_request),
        ]
        for item in stack:
            item.start()
            self.addCleanup(item.stop)
        return deleted

    def test_the_refused_identity_has_the_draft_it_created_deleted(self):
        plans = [_identity_steps(f"q{index}", draft_id=f"d{index}") for index in range(4)]
        plans.append(
            _identity_steps(
                "q4", start_status=429, start_code="ADMISSION_CAPACITY_REACHED", draft_id="d4"
            )
        )
        deleted = self._patch(plans, _RunLab())

        result = capacity_drill.queue(_RunLab(), _Topology())

        self.assertEqual(result["accepted_queue_depth"], 4)
        self.assertEqual(result["queued_states"], ["QUEUED"] * 4)
        self.assertEqual(result["terminal_states"], ["SUCCEEDED"] * 4)
        self.assertIn("/api/v1/web/drafts/d4", deleted)
        self.assertEqual(len(deleted), 5)

    def test_a_failed_admission_assertion_still_deletes_the_created_draft(self):
        plans = [
            {
                "steps": [
                    {"op": "draft", "draft": "a", "draft_id": "d-1", "token": "c1", "status": 200},
                    {"op": "draft", "draft": "b", "status": 500},
                    {"op": "draft", "draft": "c", "draft_id": "d-2", "token": "c2", "status": 200},
                    {"op": "draft", "draft": "d", "status": 429, "code": "CLIENT_QUOTA"},
                ]
            }
        ]
        deleted = self._patch(plans, _RunLab())

        with self.assertRaises(AssertionError):
            capacity_drill.admission(_RunLab(), _Topology())

        self.assertEqual(
            sorted(deleted), ["/api/v1/web/drafts/d-1", "/api/v1/web/drafts/d-2"]
        )


if __name__ == "__main__":
    unittest.main()
