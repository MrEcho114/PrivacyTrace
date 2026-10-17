"""Build a portable policy skill from the existing source contracts and prompt helpers."""

import argparse
import ast
import builtins
import hashlib
import json
import symtable
from pathlib import Path

from privacytrace.resources import ACTIVE_RULESET_VERSION, TAXONOMY_FILES
from privacytrace.web_models import WebSource

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "skills/privacytrace-policy-collector"
VERSION = "privacytrace-policy-collector/1"
INPUT_FIELDS = (
    "id", "title", "url", "source_type", "text", "version", "region", "product",
    "package_name", "version_code",
)
SOURCE_PATHS = (
    "apps/api/src/privacytrace/policy_llm_extractor.py",
    "apps/api/src/privacytrace/web_models.py",
    "apps/api/src/privacytrace/models.py",
    TAXONOMY_FILES[ACTIVE_RULESET_VERSION],
)

PREPARE_MAIN = '''
def main():
    parser = argparse.ArgumentParser(description="Prepare one source; no model or network calls")
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--text-file", type=Path, required=True)
    args = parser.parse_args()
    if re.fullmatch(SOURCE_ID_PATTERN, args.source_id) is None:
        parser.error("Invalid source ID")
    try:
        with args.text_file.open("r", encoding="utf-8", newline="") as handle:
            text = handle.read(MAX_TEXT_LENGTH + 1)
    except (OSError, UnicodeError):
        parser.error("Cannot read UTF-8 policy text")
    if not text.strip() or len(text) > MAX_TEXT_LENGTH:
        parser.error("Policy text must be nonempty and within the source length bound")
    print(json.dumps({"source_id": args.source_id, "messages": [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": build_user_prompt(text)},
    ]}, ensure_ascii=True))

if __name__ == "__main__":
    main()
'''


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def validate_helper_dependencies(helpers, exported_names):
    """Require review when copied helpers outgrow the portable environment."""
    source = "\n\n".join(helpers)
    message = "The source prompt helper dependencies changed; review the package builder"
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) for node in ast.walk(ast.parse(source))):
        raise ValueError(message + " (new imports)")
    available = set(vars(builtins)) | exported_names | {"re"}
    pending = [symtable.symtable(source, "prompt_helpers", "exec")]
    missing = set()
    while pending:
        scope = pending.pop()
        missing.update(
            symbol.get_name() for symbol in scope.get_symbols()
            if symbol.is_referenced() and symbol.is_global() and symbol.get_name() not in available
        )
        pending.extend(scope.get_children())
    if missing:
        raise ValueError(message + ": " + ", ".join(sorted(missing)))


def render():
    source = (ROOT / SOURCE_PATHS[0]).read_text(encoding="utf-8")
    syntax = ast.parse(source)
    names = {"PROMPT_VERSION", "SYSTEM_PROMPT", "UNTRUSTED_OPEN", "UNTRUSTED_CLOSE"}
    constants = {
        target.id: ast.literal_eval(node.value)
        for node in syntax.body if isinstance(node, ast.Assign)
        for target in node.targets if isinstance(target, ast.Name) and target.id in names
    }
    helpers = [
        ast.get_source_segment(source, node)
        for node in syntax.body if isinstance(node, ast.FunctionDef)
        and node.name in {"sanitize_untrusted_text", "build_user_prompt"}
    ]
    if len(helpers) != 2 or constants.keys() != names:
        raise ValueError("The source prompt interface changed; review the package builder")
    validate_helper_dependencies(helpers, names | {"sanitize_untrusted_text", "build_user_prompt"})
    schema = WebSource.model_json_schema()
    properties = schema["properties"]
    fields = "\n".join(
        f"- `{name}`（{'必填' if name in schema['required'] else '可省略'}）: "
        f"`{json.dumps(properties[name], ensure_ascii=False, sort_keys=True)}`"
        for name in INPUT_FIELDS
    )
    template = (PACKAGE / "instructions.template.md").read_text(encoding="utf-8")
    instructions = template.replace("{{SOURCE_FIELDS}}", fields).replace(
        "{{EXTRACTION_PROMPT}}", constants["SYSTEM_PROMPT"],
    ).replace("{{VERSIONS}}", (
        f"{VERSION}，prompt {constants['PROMPT_VERSION']}，ruleset {ACTIVE_RULESET_VERSION}"
    ))
    frontmatter = (
        "---\nname: privacytrace-policy-collector\n"
        "description: 收集选定 Android App 的政策网址或原文供 PrivacyTrace 使用；"
        "也可从已选单个来源抽取候选。支持整份复制到网页聊天，不进行 APK 扫描或合规判断。\n---\n\n"
    )
    helper_script = (
        '"""Generated from PrivacyTrace prompt helpers; standard library only."""\n'
        "import argparse\nimport json\nimport re\nfrom pathlib import Path\n\n"
        + "\n".join(f"{name} = {value!r}" for name, value in constants.items())
        + f"\nMAX_TEXT_LENGTH = {properties['text']['maxLength']}"
        + f"\nSOURCE_ID_PATTERN = {properties['id']['pattern']!r}\n\n"
        + "\n\n".join(helpers) + "\n\n" + PREPARE_MAIN
    )
    files = {"SKILL.md": frontmatter + instructions, "COPY.txt": instructions,
             "scripts/prepare-extraction.py": helper_script}
    provenance = {
        "version": VERSION, "prompt_version": constants["PROMPT_VERSION"],
        "ruleset_version": ACTIVE_RULESET_VERSION, "hash_encoding": "UTF-8/LF",
        "source_sha256": {
            name: sha((ROOT / name).read_text(encoding="utf-8")) for name in SOURCE_PATHS
        },
        "template_sha256": sha(template),
        "output_sha256": {name: sha(text) for name, text in files.items()},
    }
    files["provenance.json"] = json.dumps(provenance, indent=2, sort_keys=True) + "\n"
    return files


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for name, content in render().items():
        target = PACKAGE / name
        if args.check:
            if not target.is_file() or target.read_text(encoding="utf-8") != content:
                stale.append(name)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(content, encoding="utf-8", newline="\n")
    if stale:
        parser.exit(1, "Rebuild stale policy package: " + ", ".join(stale) + "\n")
    print("Policy package is current." if args.check else "Policy package built.")


if __name__ == "__main__":
    main()
