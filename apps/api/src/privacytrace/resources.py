"""Load versioned resources from the source checkout (deployment packaging is pending)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def _load_versioned(files: dict[str, str], active: str, kind: str, version: str | None) -> dict:
    """Resolve a version string to its snapshot and verify the file agrees.

    Every versioned resource follows the same contract: an explicit active
    version, a registry of on-disk snapshots, and a file whose own ``version``
    field must match the key it was filed under.
    """
    selected = active if version is None else version
    path = files.get(selected)
    if path is None:
        raise ValueError(f"Unsupported {kind} version")
    rules = read_json(path)
    if rules["version"] != selected:
        raise ValueError(f"{kind} snapshot version mismatch")
    return rules


# Keep prior snapshots registered when advancing the active version.
ACTIVE_RULESET_VERSION = "0.3.0"
TAXONOMY_FILES = {"0.3.0": "rules/taxonomy.v0.3.json"}


def taxonomy(version: str | None = None) -> dict:
    return _load_versioned(TAXONOMY_FILES, ACTIVE_RULESET_VERSION, "ruleset", version)


# PT-401: the sourced seed replaces the synthetic demo entry. The earlier
# sdk-signatures.v0.1.json stays on disk as the superseded synthetic snapshot.
ACTIVE_SDK_SIGNATURES_VERSION = "1.0.0"
SDK_SIGNATURE_FILES = {"1.0.0": "rules/sdk-signatures.v1.0.json"}


def sdk_signatures(version: str | None = None) -> dict:
    return _load_versioned(
        SDK_SIGNATURE_FILES, ACTIVE_SDK_SIGNATURES_VERSION, "SDK signature ruleset", version
    )
