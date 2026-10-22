"""Acceptance harness sources must not carry machine-private absolute paths.

A published harness runs on other machines: a default of ``/root/...`` or
``D:\\...`` either fails there or discloses where the author works. This guard
scans the acceptance harness sources for private path literals.

When a literal is genuinely required (for example a documented reference to a
platform location), mark that single line with ``# noqa: private-path``.
"""

import re
import unittest
from pathlib import Path

ACCEPTANCE = Path(__file__).resolve().parents[1] / "acceptance"
SCANNED_SUFFIXES = {".py", ".sh", ".cjs", ".mjs"}
ALLOW_MARKER = "noqa: private-path"

PRIVATE_PATH_PATTERNS = (
    re.compile(r"/root/"),
    re.compile(r"/mnt/[a-z]/"),
    re.compile(r"/home/[A-Za-z0-9._-]+/"),
    re.compile(r"/Users/[A-Za-z0-9._-]+/"),
    re.compile(r"/var/tmp/pt[0-9]{2}-"),
    re.compile(r"[A-Za-z]:\\{1,2}(?:Users|Project|GitProject|Games|\.codex)\b"),
)


def find_private_paths(text):
    """Return ``[(line_number, line)]`` for private path literals in ``text``."""
    found = []
    for number, line in enumerate(text.splitlines(), start=1):
        if ALLOW_MARKER in line:
            continue
        if any(pattern.search(line) for pattern in PRIVATE_PATH_PATTERNS):
            found.append((number, line.strip()))
    return found


class PrivatePathGuardTests(unittest.TestCase):
    def test_scanner_flags_the_paths_this_repository_has_shipped_before(self):
        # Regression evidence: these exact literals were published once and had
        # to be fixed by hand afterwards.
        samples = (
            'SOURCE = Path(os.environ.get("PT_F_SOURCE", "/root/pt-final-src"))',
            'REPO_ROOT="${PT133E_REPO_ROOT:-/mnt/d/Project/GitProject/PrivacyTrace}"',
            'LAB_STATE="${PT133E_LAB_STATE:-/var/tmp/pt81-0c0f8a8a048d}"',
            'CA = "D:\\\\Project\\\\GitProject\\\\PrivacyTrace\\\\ca.crt"',
            "const repo = 'C:\\\\Users\\\\Oasis\\\\work';",
        )
        for sample in samples:
            with self.subTest(sample=sample):
                self.assertTrue(
                    find_private_paths(sample),
                    f"guard missed a private path literal: {sample}",
                )

    def test_noqa_marker_allows_a_documented_exception(self):
        line = 'DOCS = "/root/example"  # noqa: private-path'
        self.assertEqual(find_private_paths(line), [])

    def test_ordinary_paths_are_not_flagged(self):
        for sample in (
            'CA_FILE = SOURCE / "tmp/issue73-local-env/tls/ca.crt"',
            "REPO_ROOT=\"$(cd \"$(dirname \"${BASH_SOURCE[0]}\")/../../..\" && pwd)\"",
            "Path('/var/lib/privacytrace/jobs')",
            "http://127.0.0.1:8000/_health/live",
        ):
            with self.subTest(sample=sample):
                self.assertEqual(find_private_paths(sample), [])

    def test_acceptance_sources_contain_no_private_paths(self):
        violations = []
        for path in sorted(ACCEPTANCE.rglob("*")):
            if not path.is_file() or path.suffix not in SCANNED_SUFFIXES:
                continue
            text = path.read_text(encoding="utf-8", errors="replace")
            for number, line in find_private_paths(text):
                violations.append(f"{path.relative_to(ACCEPTANCE.parent)}:{number}: {line}")
        self.assertEqual(
            violations,
            [],
            "private absolute paths in the acceptance harness:\n"
            + "\n".join(violations)
            + f"\nUse repo-relative or environment-provided paths, or mark a real "
            f"exception with '{ALLOW_MARKER}'.",
        )


if __name__ == "__main__":
    unittest.main()
