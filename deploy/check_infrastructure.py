"""Disposable DB/broker packaging checks, not #80 task-dispatch acceptance."""

import json
import secrets
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def execute(command, *, input=None, check=True):
    return subprocess.run(
        command, input=input, check=check, capture_output=True, text=True, timeout=120
    )


def check_infrastructure():
    with tempfile.TemporaryDirectory(prefix="privacytrace-infra-") as temporary:
        directory = Path(temporary)
        password = secrets.token_urlsafe(32)
        broker_password = secrets.token_urlsafe(32)
        (directory / "postgres_password").write_text(password + "\n", encoding="ascii")
        (directory / "runtime_database_url").write_text(
            "unused-synthetic-fixture", encoding="ascii"
        )
        (directory / "redis.conf").write_text(
            f"bind 0.0.0.0\nprotected-mode yes\nrequirepass {broker_password}\n"
            "dir /data\nappendonly yes\nappendfsync everysec\n"
            "maxmemory 128mb\nmaxmemory-policy noeviction\n",
            encoding="ascii",
        )
        # Synthetic credentials only. Parent is private; bind-mounted service files
        # must be readable by the distinct image UIDs, without changing host users.
        for path in directory.iterdir():
            path.chmod(0o444)
        digest = "0" * 64  # API/web roles are never started or pulled in this test.
        env_file = directory / "config.env"
        env_file.write_text(
            f"PT_API_IMAGE=example.invalid/api@sha256:{digest}\n"
            f"PT_WEB_IMAGE=example.invalid/web@sha256:{digest}\n"
            "PT_PUBLIC_HOST=privacytrace.test\n"
            "PT_INSTANCE_ID=0163a8b5-3eed-481a-bfb0-31fd3fe523dc\n"
        "PT_RUNNER_URL=https://172.29.98.1:8444\n"
        "PT_RUNNER_IMAGE_ID=sha256:aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa\n"
        "PT_GATEWAY_PEERS=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb\n"
        "PT_GATEWAY_CONTAINER_IP=172.29.98.10\n"
        "PT_CONTROL_SUBNET=172.29.98.0/24\n"
        "PT_CONTROL_GATEWAY_IP=172.29.98.1\n"
        "PT_GATEWAY_HOST_IP=10.77.0.10\n"
            f"PT_SECRETS_DIR={directory.as_posix()}\n",
            encoding="utf-8",
        )
        override = directory / "test.json"
        override.write_text(
            json.dumps(
                {
                    "services": {
                        "postgres": {
                            "environment": {"POSTGRES_DB": "privacytrace_test"},
                            "healthcheck": {
                                "test": [
                                    "CMD",
                                    "pg_isready",
                                    "-U",
                                    "privacytrace_bootstrap",
                                    "-d",
                                    "privacytrace_test",
                                ]
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )
        command = [
            "docker",
            "compose",
            "--project-name",
            "privacytrace-deployment-infra-test",
            "--env-file",
            str(env_file),
            "-f",
            str(ROOT / "deploy/compose.yaml"),
            "-f",
            str(override),
        ]

        def sql(query, *, authenticated=True):
            # Password enters only the short-lived psql environment inside this
            # disposable DB container; no password in Docker argv/env or outputs.
            script = (
                'export PGPASSWORD="$(cat /run/secrets/postgres_password)"; '
                if authenticated
                else ""
            )
            # Use the bridge address, matching API connections. Image initdb may
            # deliberately trust loopback independently of its network auth rule.
            script += "exec psql -w -h postgres -U privacytrace_bootstrap "
            script += '-d privacytrace_test -Atc "$1"'
            return execute(
                command + ["exec", "-T", "postgres", "sh", "-c", script, "psql-probe", query],
                check=authenticated,
            )

        def redis(*arguments):
            # --askpass reads stdin; credentials never become a command argument.
            return execute(
                command + ["exec", "-T", "redis", "redis-cli", "--raw", "--askpass", *arguments],
                input=broker_password + "\n",
            )

        try:
            execute(
                command + ["up", "--detach", "--wait", "--wait-timeout", "90", "postgres", "redis"]
            )
            assert sql("SELECT current_database()").stdout.strip() == "privacytrace_test"
            assert sql("SELECT 1", authenticated=False).returncode != 0
            cluster = sql("SELECT system_identifier FROM pg_control_system()").stdout.strip()
            assert cluster.isdigit()
            unauthenticated = execute(command + ["exec", "-T", "redis", "redis-cli", "ping"])
            assert "NOAUTH" in unauthenticated.stdout and "PONG" not in unauthenticated.stdout
            assert redis("PING").stdout.strip() == "PONG"
            assert (
                redis("CONFIG", "GET", "maxmemory-policy").stdout.splitlines()[-1] == "noeviction"
            )
            assert redis("CONFIG", "GET", "appendonly").stdout.splitlines()[-1] == "yes"
            assert redis("SET", "deployment-sentinel", "synthetic").stdout.strip() == "OK"
            execute(
                command
                + [
                    "up",
                    "--detach",
                    "--force-recreate",
                    "--wait",
                    "--wait-timeout",
                    "90",
                    "postgres",
                    "redis",
                ]
            )
            assert (
                sql("SELECT system_identifier FROM pg_control_system()").stdout.strip() == cluster
            )
            assert redis("GET", "deployment-sentinel").stdout.strip() == "synthetic"
            inspected = {}
            for role, user in (("postgres", "70:70"), ("redis", "999:999")):
                container = execute(command + ["ps", "-q", role]).stdout.strip()
                details = json.loads(execute(["docker", "inspect", container]).stdout)[0]
                assert details["Config"]["User"] == user
                assert details["HostConfig"]["ReadonlyRootfs"]
                assert not details["HostConfig"]["Privileged"]
                assert "ALL" in details["HostConfig"]["CapDrop"]
                assert not any(details["NetworkSettings"]["Ports"].values())
                assert not any("docker.sock" in m.get("Source", "") for m in details["Mounts"])
                # Do not publish raw inspect, env, file content or server logs.
                inspected[role] = {
                    "user": user,
                    "read_only": True,
                    "socket": False,
                    "image_id": details["Image"],
                    "ports_published": False,
                }
            return {
                "infrastructure_packaging": "pass",
                "postgres_authentication": "pass",
                "postgres_cluster_volume_recreate": "pass",
                "redis_authentication": "pass",
                "redis_aof_sentinel_recreate": "pass",
                "infrastructure_containers": inspected,
                "scope": "Empty test database and synthetic Redis sentinel only; no #80 dispatch",
            }
        except subprocess.SubprocessError:
            # Commands/server errors may contain data; never echo captured outputs.
            raise RuntimeError("Disposable DB/broker packaging check failed") from None
        finally:
            execute(command + ["down", "--volumes", "--remove-orphans"])


if __name__ == "__main__":
    result = check_infrastructure()
    print(json.dumps(result, indent=2))
