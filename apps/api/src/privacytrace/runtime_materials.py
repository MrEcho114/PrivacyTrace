"""Short-lived, scope-bound transfer tickets over private mTLS, never broker input."""

import base64
import hashlib
import hmac
import json
import os
import re
from datetime import timedelta
from pathlib import Path
from uuid import UUID, uuid4

import sqlalchemy as sa

from .postgres_execution import ExecutionLease, LeaseLost, PostgresExecution
from .postgres_schema import runner_materials, runtime_inputs
from .runner_protocol import MAX_INPUT, canonical_uuid, file_name
from .runtime_tls import json_value, private_file

TICKET_KEYS = frozenset(
    {"version", "instance_id", "material_id", "scope_id", "owner", "fence", "expires", "mode"}
)


def encode(raw):
    return base64.urlsafe_b64encode(raw).decode().rstrip("=")


def decode(value):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_-]+", value):
        raise ValueError("Invalid material ticket")
    return base64.b64decode(value + "=" * (-len(value) % 4), altchars=b"-_", validate=True)


def ticket_claims(value):
    try:
        if type(value) is not str or not 1 <= len(value) <= 2048:
            raise ValueError
        payload, signature = value.split(".")
        claims = json_value(decode(payload))
        if type(claims) is not dict or set(claims) != TICKET_KEYS or len(decode(signature)) != 32:
            raise ValueError
        if type(claims["version"]) is not int or claims["version"] != 1:
            raise ValueError
        canonical_uuid(claims["instance_id"])
        canonical_uuid(claims["material_id"])
        if type(claims["scope_id"]) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", claims["scope_id"]
        ):
            raise ValueError
        if (
            type(claims["fence"]) is not int
            or type(claims["expires"]) is not int
            or claims["expires"] <= 0
        ):
            raise ValueError
        if claims["mode"] == "scan":
            canonical_uuid(claims["owner"])
            if not 1 <= claims["fence"] < 2**63:
                raise ValueError
        elif claims["mode"] != "inspect" or claims["owner"] is not None or claims["fence"] != 0:
            raise ValueError
        return claims
    except (ValueError, TypeError, KeyError, UnicodeError):
        raise ValueError("Invalid material ticket") from None


class RuntimeMaterials:
    MAX_REFERENCES = 1000

    def __init__(self, store, key_file):
        self.store = store
        self.root = store.root / "web"
        self.execution = PostgresExecution(store)
        self._key = private_file(key_file, secret=True).read_bytes()
        if len(self._key) != 32:
            raise ValueError("Material signing key must contain exactly 32 private bytes")

    @classmethod
    def from_env(cls, store):
        try:
            return cls(store, os.environ["PRIVACYTRACE_MATERIAL_KEY_FILE"])
        except (KeyError, OSError):
            raise ValueError("Private material signing configuration required") from None

    def path(self, path_key, draft_id):
        if type(path_key) is not str or not re.fullmatch(r"[a-f0-9]{32}", draft_id):
            raise ValueError("Invalid private material reference")
        parts = path_key.split("/")
        if (
            not 2 <= len(parts) <= 3
            or parts[0] != draft_id
            or any(p in {"", ".", ".."} for p in parts)
            or any("\\" in p or ":" in p or "\x00" in p for p in parts)
        ):
            raise ValueError("Invalid private material reference")
        if len(parts) == 2:
            if parts[1] not in {"input.apk", "upload.pending"}:
                raise ValueError("Invalid private material reference")
        else:
            if parts[1] != "packages" and not re.fullmatch(
                r"packages\.pending\.[a-f0-9]{32}", parts[1]
            ):
                raise ValueError("Invalid private material reference")
            file_name(parts[2])
        path = self.root.joinpath(*parts).absolute()
        if len(path_key) > 300 or not path.is_relative_to(self.root.absolute()):
            raise ValueError("Invalid private material reference")
        for part in (path, *path.parents):
            if part.is_symlink() or getattr(part, "is_junction", lambda: False)():
                raise ValueError("Linked private material rejected")
        if not path.is_file():
            raise ValueError("Private material file unavailable")
        return path

    @staticmethod
    def digest(path):
        size, digest = 0, hashlib.sha256()
        with path.open("rb") as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                if size > MAX_INPUT:
                    raise ValueError("Private material exceeds input limit")
                digest.update(chunk)
        if not size:
            raise ValueError("Private material is empty")
        return digest.hexdigest(), size

    def register(self, path, *, draft_id, lease=None, expected_sha256=None):
        self.execution.events._standalone()
        path_key = Path(path).absolute().relative_to(self.root.absolute()).as_posix()
        path = self.path(path_key, draft_id)
        digest, size = self.digest(path)  # No long DB transaction while reading bytes.
        if expected_sha256 is not None and digest != expected_sha256:
            raise ValueError("Registered private input digest changed")
        scope_id = lease.job_id if lease is not None else draft_id
        with self.store._transaction() as conn:
            now = self.execution._now(conn)
            draft_scope = self.store._scope(draft_id)
            if not draft_scope or draft_scope["kind"] != "DRAFT" or draft_scope["tombstone"]:
                raise PermissionError("Private material scope unavailable")
            if lease is not None:
                self.execution._guard(conn, lease)
                input_draft = conn.scalar(
                    sa.select(runtime_inputs.c.draft_id).where(
                        runtime_inputs.c.instance_id == self.store.instance_id,
                        runtime_inputs.c.job_id == lease.job_id,
                    )
                )
                if input_draft != draft_id:
                    raise PermissionError("Private material scope unavailable")
            conn.execute(
                runner_materials.delete().where(
                    runner_materials.c.instance_id == self.store.instance_id,
                    runner_materials.c.expires_at <= now,
                )
            )
            count = conn.scalar(
                sa.select(sa.func.count())
                .select_from(runner_materials)
                .where(runner_materials.c.instance_id == self.store.instance_id)
            )
            if count >= self.MAX_REFERENCES:
                raise ValueError("Private transfer capacity reached")
            reference, until = uuid4(), now + timedelta(seconds=300)
            claims = {
                "version": 1,
                "instance_id": self.store.instance_id,
                "material_id": str(reference),
                "scope_id": scope_id,
                "owner": str(lease.owner) if lease else None,
                "fence": lease.fence if lease else 0,
                "expires": int(until.timestamp()),
                "mode": "scan" if lease else "inspect",
            }
            conn.execute(
                runner_materials.insert().values(
                    instance_id=self.store.instance_id,
                    material_id=reference,
                    scope_id=scope_id,
                    draft_id=draft_id,
                    path_key=path_key,
                    sha256=digest,
                    byte_count=size,
                    mode=claims["mode"],
                    owner=lease.owner if lease else None,
                    fence=claims["fence"],
                    expires_at=until,
                )
            )
            raw = json.dumps(claims, sort_keys=True, separators=(",", ":")).encode()
            signature = hmac.digest(self._key, b"privacytrace.material.v1\0" + raw, "sha256")
            return {
                "name": file_name(path.name) if path.name.lower().endswith(".apk") else "input.apk",
                "sha256": digest,
                "size": size,
                "ticket": encode(raw) + "." + encode(signature),
            }

    def verify(self, ticket):
        try:
            claims = ticket_claims(ticket)
            payload, signature = ticket.split(".")
            expected = hmac.digest(
                self._key, b"privacytrace.material.v1\0" + decode(payload), "sha256"
            )
            if (
                not hmac.compare_digest(expected, decode(signature))
                or claims["instance_id"] != self.store.instance_id
            ):
                raise ValueError
            with self.store._transaction() as conn:
                now = self.execution._now(conn)
                row = (
                    conn.execute(
                        sa.select(runner_materials).where(
                            runner_materials.c.instance_id == self.store.instance_id,
                            runner_materials.c.material_id == UUID(claims["material_id"]),
                        )
                    )
                    .mappings()
                    .one_or_none()
                )
                if (
                    row is None
                    or row["expires_at"] <= now
                    or claims["expires"] <= now.timestamp()
                    or claims["expires"] > now.timestamp() + 301
                    or row["scope_id"] != claims["scope_id"]
                    or row["mode"] != claims["mode"]
                    or row["fence"] != claims["fence"]
                    or (str(row["owner"]) if row["owner"] else None) != claims["owner"]
                ):
                    raise ValueError
                scope = self.store._scope(row["draft_id"])
                if not scope or scope["tombstone"] or scope["kind"] != "DRAFT":
                    raise ValueError
                if row["mode"] == "scan":
                    execution = self.execution._row(conn, row["scope_id"])
                    if execution is None:
                        raise ValueError
                    lease = ExecutionLease(
                        self.store.instance_id,
                        row["scope_id"],
                        execution["event_id"],
                        row["owner"],
                        row["fence"],
                        execution["attempt"],
                        execution["leased_until"],
                    )
                    self.execution._guard(conn, lease)
                return dict(row)
        except (ValueError, TypeError, KeyError, LeaseLost):
            raise PermissionError("Private material permit unavailable") from None
