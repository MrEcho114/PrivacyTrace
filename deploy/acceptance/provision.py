"""Disposable Linux deployment, with a real broker, worker and Docker scanner.

This single-daemon laboratory is explicitly NOT a dedicated scan-host receipt.
Only resources carrying this invocation's random Compose project are removed.
All credentials stay in the private state directory, never in command arguments.
"""

import argparse
import hashlib
import ipaddress
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import tempfile
import time
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[2]


def execute(argv, *, input=None, timeout=180):
    result = subprocess.run(argv, input=input, capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        # stderr can contain SQL, credentials or private paths. Keep it local.
        error = RuntimeError(f"deployment command failed ({result.returncode}): {argv[0]}")
        error.stderr = result.stderr
        error.stdout = result.stdout
        raise error
    return result.stdout.strip()


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def available_subnet():
    identifiers = execute(["docker", "network", "ls", "-q"]).splitlines()
    networks = json.loads(execute(["docker", "network", "inspect", *identifiers]))
    occupied = [
        ipaddress.ip_network(item["Subnet"])
        for network in networks
        for item in (network.get("IPAM", {}).get("Config") or [])
        if item.get("Subnet")
    ]
    for _ in range(200):
        prefix = f"10.{secrets.randbelow(40) + 200}.{secrets.randbelow(250)}"
        candidate = ipaddress.ip_network(prefix + ".0/24")
        if all(
            candidate.version != item.version or not candidate.overlaps(item) for item in occupied
        ):
            return prefix
    raise RuntimeError("no nonoverlapping laboratory subnet found")


class Laboratory:
    def __init__(self, directory):
        self.root = Path(directory).resolve()
        self.state = json.loads((self.root / "owner.json").read_text())
        self.project = self.state["project"]
        if self.root.name != self.project or not re.fullmatch(r"pt81-[0-9a-f]{12}", self.project):
            raise ValueError("laboratory ownership mismatch")
        self.compose = [
            "docker",
            "compose",
            "--project-name",
            self.project,
            "--env-file",
            str(self.root / "deployment.env"),
            "-f",
            str(ROOT / "deploy/compose.yaml"),
        ]
        if self.state.get("reset_ports"):
            self.compose += ["-f", str(self.root / "ports.yaml")]
        self.compose += ["-f", str(self.root / "laboratory.json")]

    def run(self, *args, input=None, timeout=180):
        return execute([*self.compose, *args], input=input, timeout=timeout)

    def python(self, source, service="api"):
        return self.run("exec", "-T", service, "/opt/venv/bin/python", "-c", source)

    def ready(self, expected=200, timeout=120):
        until = time.monotonic() + timeout
        while time.monotonic() < until:
            try:
                status = self.python(
                    "import urllib.request,urllib.error;\n"
                    "try: print(urllib.request.urlopen('http://127.0.0.1:8000/_health/ready',"
                    "timeout=4).status)\n"
                    "except urllib.error.HTTPError as e: print(e.code)"
                )
                if status == str(expected):
                    return
            except (RuntimeError, subprocess.TimeoutExpired):
                pass
            time.sleep(1)
        raise RuntimeError(f"readiness did not reach {expected}")

    def stop(self):
        # Compose scopes removal by the random project label. Runner belongs to
        # the same project and is in the override; never use global prune.
        self.run("down", "--volumes", "--remove-orphans", timeout=180)

    def purge(self):
        if self.root.parent != Path("/var/tmp") or self.root.is_symlink():
            raise ValueError("refusing to purge outside the owned temporary test root")
        self.stop()
        volumes = execute(
            [
                "docker",
                "volume",
                "ls",
                "-q",
                "--filter",
                f"label=com.docker.compose.project={self.project}",
            ]
        ).splitlines()
        for volume in volumes:
            if not volume.startswith(self.project + "_"):
                raise ValueError("unexpected owned volume name")
            execute(["docker", "volume", "rm", volume])
        shutil.rmtree(self.root)


def create(api_image, web_image, runner_image, scanner_image):
    if os.name != "posix" or os.geteuid() != 0:
        raise ValueError("Linux root is required only to provision private file owners")
    project = "pt81-" + uuid4().hex[:12]
    directory = Path(tempfile.mkdtemp(prefix=project + "-", dir="/var/tmp"))
    # The exact project marker is also the final directory name.
    root = directory.with_name(project)
    directory.rename(root)
    try:
        return _populate(root, project, api_image, web_image, runner_image, scanner_image)
    except BaseException:
        if (root / "owner.json").is_file():
            # The owner marker lets the calling harness safely purge partial
            # Compose resources as well as generated credentials.
            print(f"FAILED_LAB={root}", flush=True)
        else:
            # No Docker resources or credentials precede the owner marker.
            shutil.rmtree(root)
        raise


def _populate(root, project, api_image, web_image, runner_image, scanner_image):
    instance = str(uuid4())
    subnet = available_subnet()
    gateway, runner_ip = subnet + ".10", subnet + ".40"
    image_ids = {
        name: execute(["docker", "image", "inspect", image, "--format", "{{.Id}}"])
        for name, image in {
            "api": api_image,
            "web": web_image,
            "runner": runner_image,
            "scanner": scanner_image,
        }.items()
    }
    state = {
        "project": project,
        "instance_id": instance,
        "images": image_ids,
        "source_sha": os.environ.get("PT_ACCEPTANCE_SOURCE_SHA")
        or execute(["git", "-C", str(ROOT), "rev-parse", "HEAD"]),
        "https_port": free_port(),
        "scan_host_separate": False,
    }
    (root / "owner.json").write_text(json.dumps(state))
    private = root / "secrets"
    private.mkdir(mode=0o700)
    runner_root = root / "runner"
    runner_root.mkdir(mode=0o700)
    os.chown(runner_root, 10001, 10001)
    # The Runner and daemon MUST resolve the same absolute mount source.
    root.chmod(0o711)

    def write(name, value, uid=10001, mode=0o400):
        path = private / name
        path.write_bytes(value if isinstance(value, bytes) else value.encode())
        os.chown(path, uid, uid)
        path.chmod(mode)
        return path

    pki = root / "pki"
    pki.mkdir(mode=0o700)
    execute(
        [
            "openssl",
            "req",
            "-x509",
            "-newkey",
            "rsa:2048",
            "-nodes",
            "-days",
            "2",
            "-subj",
            "/CN=PrivacyTrace disposable laboratory CA",
            "-keyout",
            str(pki / "ca.key"),
            "-out",
            str(pki / "ca.pem"),
            "-addext",
            "basicConstraints=critical,CA:TRUE",
        ]
    )
    for name, addresses in {
        "control": "DNS:control",
        "runner": f"IP:{runner_ip}",
        "gateway": f"IP:{gateway}",
        "web": "DNS:privacytrace.test,IP:127.0.0.1",
    }.items():
        execute(
            [
                "openssl",
                "req",
                "-newkey",
                "rsa:2048",
                "-nodes",
                "-subj",
                f"/CN={name}",
                "-keyout",
                str(pki / (name + ".key")),
                "-out",
                str(pki / (name + ".csr")),
            ]
        )
        (pki / "leaf.ext").write_text(
            "basicConstraints=critical,CA:FALSE\n"
            "extendedKeyUsage=serverAuth,clientAuth\n"
            f"subjectAltName={addresses}\n"
        )
        execute(
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                str(pki / (name + ".csr")),
                "-CA",
                str(pki / "ca.pem"),
                "-CAkey",
                str(pki / "ca.key"),
                "-CAcreateserial",
                "-days",
                "2",
                "-extfile",
                str(pki / "leaf.ext"),
                "-out",
                str(pki / (name + ".pem")),
            ]
        )

    def fingerprint(name):
        der = subprocess.check_output(
            ["openssl", "x509", "-in", str(pki / (name + ".pem")), "-outform", "DER"]
        )
        return hashlib.sha256(der).hexdigest()

    for name in ("control", "gateway", "runner", "web"):
        write(name + "_ca.pem", (pki / "ca.pem").read_bytes())
        write(name + "_cert.pem", (pki / (name + ".pem")).read_bytes())
        write(name + "_key.pem", (pki / (name + ".key")).read_bytes())
    passwords = {
        name: secrets.token_hex(24) for name in ("postgres", "migrator", "runtime", "redis")
    }
    write("postgres_password", passwords["postgres"], uid=70)
    write("material.key", secrets.token_bytes(32))
    for role in ("runtime", "migration"):
        account = "migrator" if role == "migration" else "runtime"
        write(
            role + "_database_url",
            "postgresql+psycopg://privacytrace_"
            + account
            + ":"
            + passwords[account]
            + "@postgres:5432/privacytrace",
        )
    broker = f"redis://app:{passwords['redis']}@redis:6379/0"
    write("runtime_broker_url", broker)
    write("runtime_health_url", broker)
    prefix = f"pt80:{instance}:"
    write(
        "redis.conf",
        "bind 0.0.0.0\nprotected-mode yes\ndir /data\nappendonly yes\n"
        "appendfsync always\nmaxmemory 128mb\nmaxmemory-policy noeviction\nuser default off\n"
        f"user app on >{passwords['redis']} ~{prefix}* &{prefix}* "
        "+@read +@write +@connection +@pubsub +@scripting +@transaction "
        "-@admin -@dangerous +eval +evalsha +script|load +client|setname\n",
        uid=999,
    )
    env = {
        "PT_API_IMAGE": image_ids["api"],
        "PT_WEB_IMAGE": image_ids["web"],
        "PT_DEPLOY_MODE": "isolated",
        "PT_PUBLIC_BIND_IP": "127.0.0.1",
        "PT_PUBLIC_HOST": "privacytrace.test",
        "PT_INSTANCE_ID": instance,
        "PT_RUNNER_URL": f"https://{runner_ip}:8444",
        "PT_RUNNER_IMAGE_ID": image_ids["scanner"],
        "PT_GATEWAY_PEERS": fingerprint("runner"),
        "PT_GATEWAY_CONTAINER_IP": gateway,
        "PT_GATEWAY_HOST_IP": "127.0.0.1",
        "PT_CONTROL_SUBNET": subnet + ".0/24",
        "PT_CONTROL_GATEWAY_IP": subnet + ".1",
        "PT_SECRETS_DIR": str(private),
    }
    (root / "deployment.env").write_text("\n".join(f"{k}={v}" for k, v in env.items()) + "\n")
    caddy = root / "Caddyfile"
    caddy.write_text(
        "{\n admin off\n auto_https off\n log {\n output discard\n }\n}\n"
        "https://privacytrace.test:8443 {\n"
        " tls /run/secrets/web_cert /run/secrets/web_key\n"
        " import /etc/caddy/Caddyfile.common\n}\n"
    )
    caddy.chmod(0o444)
    override = {
        "services": {
            "web": {
                "ports": [f"127.0.0.1:{state['https_port']}:8443"],
                "volumes": [
                    {
                        "type": "bind",
                        "source": str(caddy),
                        "target": "/etc/caddy/Caddyfile",
                        "read_only": True,
                    }
                ],
                "secrets": ["web_cert", "web_key"],
            },
            "gateway": {"ports": []},
            "redis": {
                "healthcheck": {
                    "test": ["CMD-SHELL", "redis-cli ping 2>/dev/null | grep -q '^NOAUTH'"]
                }
            },
            "runner": {
                "image": image_ids["runner"],
                "user": "10001:10001",
                "group_add": [str(Path("/var/run/docker.sock").stat().st_gid)],
                "read_only": True,
                "cap_drop": ["ALL"],
                "security_opt": ["no-new-privileges:true"],
                "pids_limit": 256,
                "mem_limit": "1g",
                "cpus": 2,
                "init": True,
                "healthcheck": {"disable": True},
                "networks": {"control": {"ipv4_address": runner_ip}},
                "tmpfs": ["/tmp:rw,noexec,nosuid,size=64m,uid=10001,gid=10001"],
                "volumes": [
                    f"{runner_root}:{runner_root}",
                    "/var/run/docker.sock:/var/run/docker.sock",
                ],
                "environment": {
                    "PRIVACYTRACE_INSTANCE_ID": instance,
                    "PRIVACYTRACE_RUNNER_IMAGE_ID": image_ids["scanner"],
                    "PRIVACYTRACE_RUNNER_ROOT": str(runner_root),
                    "PRIVACYTRACE_RUNNER_BIND": runner_ip,
                    "PRIVACYTRACE_RUNNER_PORT": "8444",
                    "PRIVACYTRACE_RUNNER_PEERS": fingerprint("control"),
                    "PRIVACYTRACE_RUNNER_TLS_CA": "/run/secrets/runner_ca",
                    "PRIVACYTRACE_RUNNER_TLS_CERT": "/run/secrets/runner_cert",
                    "PRIVACYTRACE_RUNNER_TLS_KEY": "/run/secrets/runner_key",
                    "PRIVACYTRACE_GATEWAY_URL": f"https://{gateway}:8443",
                    "PRIVACYTRACE_RUNNER_GATEWAY_TLS_CA": "/run/secrets/runner_ca",
                    "PRIVACYTRACE_RUNNER_GATEWAY_TLS_CERT": "/run/secrets/runner_cert",
                    "PRIVACYTRACE_RUNNER_GATEWAY_TLS_KEY": "/run/secrets/runner_key",
                },
                "secrets": ["runner_ca", "runner_cert", "runner_key"],
            },
        },
        "secrets": {
            name: {"file": str(private / file)}
            for name, file in {
                "web_cert": "web_cert.pem",
                "web_key": "web_key.pem",
                "runner_ca": "runner_ca.pem",
                "runner_cert": "runner_cert.pem",
                "runner_key": "runner_key.pem",
            }.items()
        },
    }
    # Compose merges port sequences by key; !override is unavailable in JSON.
    # Reset web ports in an initial YAML override, then add our ephemeral port.
    (root / "ports.yaml").write_text(
        "services:\n  web:\n    ports: !reset []\n  gateway:\n    ports: !reset []\n"
    )
    (root / "laboratory.json").write_text(json.dumps(override))
    lab = Laboratory(root)
    lab.compose[-2:-2] = ["-f", str(root / "ports.yaml")]
    # Persist the override list so reopen/cleanup uses the identical topology.
    state["reset_ports"] = True
    (root / "owner.json").write_text(json.dumps(state))
    lab.run("up", "-d", "--wait", "postgres", "redis")
    sql = (
        f"CREATE ROLE privacytrace_migrator LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOINHERIT NOBYPASSRLS PASSWORD '{passwords['migrator']}';\n"
        f"CREATE ROLE privacytrace_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE "
        f"NOINHERIT NOBYPASSRLS PASSWORD '{passwords['runtime']}';\n"
        "ALTER DATABASE privacytrace OWNER TO privacytrace_migrator;\n"
        "REVOKE ALL ON DATABASE privacytrace FROM PUBLIC;\n"
        "GRANT CONNECT ON DATABASE privacytrace "
        "TO privacytrace_migrator,privacytrace_runtime;\n"
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC;\n"
    )
    lab.run(
        "exec",
        "-T",
        "postgres",
        "psql",
        "-v",
        "ON_ERROR_STOP=1",
        "-U",
        "privacytrace_bootstrap",
        "-d",
        "privacytrace",
        input=sql,
    )
    lab.run("--profile", "migration", "run", "--rm", "migrate")
    lab.run("up", "-d", "--no-deps", "gateway", "dispatcher", "worker", "api", "runner")
    lab.ready()
    lab.run("up", "-d", "--no-deps", "web")
    # Only public CA leaves the private PKI directory.
    shutil.copyfile(pki / "ca.pem", root / "public-ca.pem")
    return lab


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("up", "down"))
    parser.add_argument("--state", type=Path)
    parser.add_argument(
        "--purge", action="store_true", help="remove only the owned /var/tmp test root"
    )
    parser.add_argument("--api-image", default="privacytrace-api:issue81-test")
    parser.add_argument("--web-image", default="privacytrace-web:issue81-test")
    parser.add_argument("--runner-image", default="privacytrace-runner:issue81-test")
    parser.add_argument("--scanner-image", default="privacytrace-worker:s1")
    args = parser.parse_args()
    if args.operation == "down":
        if args.state is None:
            parser.error("down requires --state")
        lab = Laboratory(args.state)
        lab.purge() if args.purge else lab.stop()
    else:
        lab = create(args.api_image, args.web_image, args.runner_image, args.scanner_image)
        print(f"LAB_STATE={lab.root}")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        raise SystemExit(f"laboratory provisioning failed: {type(error).__name__}") from None
