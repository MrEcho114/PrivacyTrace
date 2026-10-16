"""Export existing policy instructions and source constraints; no network or model calls."""

import argparse
import ast
import hashlib
import json
from pathlib import Path

from privacytrace.resources import ACTIVE_RULESET_VERSION, TAXONOMY_FILES
from privacytrace.web_models import WebSource

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/privacytrace-policy-collection"
FORMAT_VERSION = "privacytrace-policy-collection/1"
SOURCE_FIELDS = (
    "id", "title", "url", "source_type", "text", "version", "region", "product",
    "package_name", "version_code",
)
SOURCES = (
    "apps/api/src/privacytrace/policy_llm_extractor.py",
    "apps/api/src/privacytrace/web_models.py",
    "apps/api/src/privacytrace/models.py",
    "apps/api/src/privacytrace/resources.py",
    TAXONOMY_FILES[ACTIVE_RULESET_VERSION],
)


def digest(path):
    # Git may check out CRLF on Windows; provenance hashes describe canonical UTF-8/LF.
    return hashlib.sha256(path.read_text(encoding="utf-8").encode("utf-8")).hexdigest()


def render():
    module = ast.parse((ROOT / SOURCES[0]).read_text(encoding="utf-8"))
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in module.body if isinstance(node, ast.Assign)
        for target in node.targets
        if isinstance(target, ast.Name) and target.id in {"PROMPT_VERSION", "SYSTEM_PROMPT"}
    }
    schema = WebSource.model_json_schema()
    fields = ["id 与 title 必填；其余字段按既有默认值处理。空字符串与 null 的规则沿用原模型。", ""]
    for name in SOURCE_FIELDS:
        constraints = {k: v for k, v in schema["properties"][name].items() if k != "title"}
        fields.append(f"- `{name}`: `{json.dumps(constraints, ensure_ascii=False, sort_keys=True)}`")
    versions = (
        f"{FORMAT_VERSION}；prompt {constants['PROMPT_VERSION']}；"
        f"ruleset {ACTIVE_RULESET_VERSION}"
    )
    template = PACKAGE / "assets/collection-instructions.template.md"
    instructions = template.read_text(encoding="utf-8").replace(
        "{{SOURCE_FIELDS}}", "\n".join(fields),
    ).replace("{{VERSIONS}}", versions)
    files = {
        "references/collection-instructions.md": instructions,
        "references/extraction-prompt.txt": constants["SYSTEM_PROMPT"],
    }
    manifest = {
        "format_version": FORMAT_VERSION,
        "prompt_version": constants["PROMPT_VERSION"],
        "ruleset_version": ACTIVE_RULESET_VERSION,
        "hash_normalization": "UTF-8/LF",
        "source_files": {name: digest(ROOT / name) for name in SOURCES},
        "template_sha256": digest(template),
        "generated_files": {
            name: hashlib.sha256(text.encode("utf-8")).hexdigest()
            for name, text in files.items()
        },
    }
    files["references/manifest.json"] = json.dumps(
        manifest, ensure_ascii=False, indent=2, sort_keys=True,
    ) + "\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail on stale exports without writing")
    args = parser.parse_args()
    stale = []
    for name, text in render().items():
        path = PACKAGE / name
        if args.check:
            if not path.exists() or path.read_text(encoding="utf-8") != text:
                stale.append(name)
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8", newline="\n")
    if stale:
        parser.exit(1, "Stale policy collection exports: " + ", ".join(stale) + "\n")
    print("Policy collection exports checked." if args.check else "Policy collection exports written.")


if __name__ == "__main__":
    main()
