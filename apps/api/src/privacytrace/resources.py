"""Load versioned resources from the source checkout (deployment packaging is pending)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


# Keep prior snapshots registered when advancing the active version.
ACTIVE_RULESET_VERSION = "0.3.0"
TAXONOMY_FILES = {"0.3.0": "rules/taxonomy.v0.3.json"}


def taxonomy(version: str | None = None) -> dict:
    selected = ACTIVE_RULESET_VERSION if version is None else version
    path = TAXONOMY_FILES.get(selected)
    if path is None:
        raise ValueError("Unsupported ruleset version")
    rules = read_json(path)
    if rules["version"] != selected:
        raise ValueError("Taxonomy snapshot version mismatch")
    return rules


# PT-401: the sourced seed replaces the synthetic demo entry. The earlier
# sdk-signatures.v0.1.json stays on disk as the superseded synthetic snapshot.
ACTIVE_SDK_SIGNATURES_VERSION = "1.0.0"
SDK_SIGNATURE_FILES = {"1.0.0": "rules/sdk-signatures.v1.0.json"}


def sdk_signatures(version: str | None = None) -> dict:
    selected = ACTIVE_SDK_SIGNATURES_VERSION if version is None else version
    path = SDK_SIGNATURE_FILES.get(selected)
    if path is None:
        raise ValueError("Unsupported SDK signature ruleset version")
    rules = read_json(path)
    if rules["version"] != selected:
        raise ValueError("SDK signature snapshot version mismatch")
    return rules
