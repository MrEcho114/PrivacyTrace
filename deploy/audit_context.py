"""Fail the real BuildKit context audit without disclosing unexpected filenames."""

import sys
from pathlib import Path

EXACT = {
    "package.json",
    "package-lock.json",
    "apps/api/pyproject.toml",
    "apps/api/uv.lock",
    "apps/api/alembic.ini",
    "apps/web/package.json",
    "apps/web/index.html",
    "apps/web/design.html",
    "apps/web/tsconfig.json",
    "apps/web/vite.config.ts",
    "rules/taxonomy.v0.3.json",
    "rules/sdk-signatures.v1.0.json",
    "samples/demo/evaluation-input.json",
    "deploy/Dockerfile",
    "deploy/serve.py",
    "deploy/probe.py",
    "deploy/bootstrap.py",
    "deploy/runtime-contract.json",
    "deploy/audit_context.py",
    "deploy/Caddyfile",
    "deploy/Caddyfile.common",
    "apps/web/public/fonts/NotoSansSC-Variable.woff2",
    "apps/web/public/fonts/NotoSerifSC-Variable.woff2",
    "apps/web/public/fonts/licenses/NotoSansSC-OFL.txt",
    "apps/web/public/fonts/licenses/NotoSerifSC-OFL.txt",
}


def audit(root):
    count = 0
    for path in root.rglob("*"):
        if path.is_symlink():
            raise ValueError("Symlinks forbidden in deployment context")
        if not path.is_file():
            continue
        name = path.relative_to(root).as_posix()
        allowed = (
            name in EXACT
            or name.startswith("apps/api/src/privacytrace/")
            and path.suffix == ".py"
            or name.startswith("apps/api/migrations/")
            and path.suffix == ".py"
            or name.startswith("apps/web/src/")
            and path.suffix in {".ts", ".vue", ".css", ".svg"}
        )
        if not allowed:
            raise ValueError("Unexpected file in deployment context")
        count += 1
    if not count:
        raise ValueError("Empty build context")
    return count


if __name__ == "__main__":
    context_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    if context_path is None:
        print(f"Context audit ready; tracking {len(EXACT)} exact assets")
    else:
        try:
            count = audit(context_path)
        except (OSError, ValueError):
            raise SystemExit("Deployment context rejected") from None
        print(f"Audited {count} non-private build inputs")

