"""Load versioned resources from the source checkout (deployment packaging is pending)."""

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]


def read_json(relative_path: str) -> dict:
    return json.loads((ROOT / relative_path).read_text(encoding="utf-8"))


def taxonomy() -> dict:
    return read_json("rules/taxonomy.v0.3.json")
