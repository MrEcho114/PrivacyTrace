"""Strict version-one runner manifest; every executable option is server-owned."""

import re
from uuid import UUID

MAX_INPUT = 150 * 1024 * 1024


def canonical_uuid(value):
    if type(value) is not str or str(UUID(value)) != value:
        raise ValueError("Invalid runtime identifier")
    return value


def file_name(value):
    if (
        type(value) is not str
        or not 1 <= len(value) <= 128
        or value in {".", ".."}
        or value.startswith("-")
        or any(c in value for c in "/\\:\x00")
        or not value.lower().endswith(".apk")
        or any(ord(c) < 32 for c in value)
    ):
        raise ValueError("Invalid runtime input name")
    return value


def manifest(value):
    try:
        if type(value) is not dict or set(value) != {
            "version",
            "operation",
            "request_id",
            "instance_id",
            "scope_id",
            "owner",
            "fence",
            "package_set",
            "files",
        }:
            raise ValueError
        if (
            type(value["version"]) is not int
            or value["version"] != 1
            or value["operation"] not in {"inspect", "scan"}
        ):
            raise ValueError
        canonical_uuid(value["request_id"])
        canonical_uuid(value["instance_id"])
        if type(value["package_set"]) is not bool or (
            value["operation"] == "inspect" and value["package_set"]
        ):
            raise ValueError
        if type(value["scope_id"]) is not str or not re.fullmatch(
            r"[A-Za-z0-9][A-Za-z0-9_-]{0,99}", value["scope_id"]
        ):
            raise ValueError
        if type(value["fence"]) is not int or not 0 <= value["fence"] < 2**63:
            raise ValueError
        if value["operation"] == "scan":
            canonical_uuid(value["owner"])
            if value["fence"] == 0:
                raise ValueError
        elif value["owner"] is not None or value["fence"] != 0:
            raise ValueError
        files = value["files"]
        if type(files) is not list or not 1 <= len(files) <= (
            1 if value["operation"] == "inspect" else 101
        ):
            raise ValueError
        if not value["package_set"] and len(files) != 1:
            raise ValueError
        names, size = set(), 0
        for item in files:
            if type(item) is not dict or set(item) != {"name", "sha256", "size", "ticket"}:
                raise ValueError
            name = file_name(item["name"])
            if name in names or type(item["size"]) is not int or not 1 <= item["size"] <= MAX_INPUT:
                raise ValueError
            names.add(name)
            size += item["size"]
            if type(item["sha256"]) is not str or not re.fullmatch(r"[a-f0-9]{64}", item["sha256"]):
                raise ValueError
            if (
                type(item["ticket"]) is not str
                or not 1 <= len(item["ticket"]) <= 2048
                or any(c.isspace() for c in item["ticket"])
            ):
                raise ValueError
        if size > MAX_INPUT:
            raise ValueError
        return value
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValueError("Invalid fixed runner manifest") from None
