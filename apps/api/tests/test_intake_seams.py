"""The durable intake must never fall back to a module-level sandbox helper.

BUG-01（#73 H01）的形态：`DurableWebIntake` 子类里直接调用了模块级
`inspect_package_isolated`，而持久化控制面按设计没有 Docker socket，于是政策发现
必然 503，而上传路径（走注入的 Runner 检查器）一切正常。

行为测试只能覆盖当时那一个调用点；这条结构性检查覆盖“下一个新端点又直接调模块级
helper”的情况：允许调用，但必须显式传入 `inspector=`，把隔离边界显式化。
"""

import ast
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "privacytrace" / "durable_intake.py"
)

# Helpers that shell out to a local sandbox unless an inspector is injected.
SANDBOX_HELPERS = {"inspect_package_isolated", "inspect_uploaded_package"}


def _unscoped_calls(source: str) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Name):
            continue
        if node.func.id not in SANDBOX_HELPERS:
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        if "inspector" not in keywords:
            offenders.append(f"{node.func.id}() at line {node.lineno}")
    return offenders


def test_durable_intake_injects_its_inspector():
    offenders = _unscoped_calls(SOURCE.read_text(encoding="utf-8"))
    assert offenders == [], (
        "durable_intake.py calls a sandbox helper without an injected inspector; "
        "the control plane has no Docker socket: " + ", ".join(offenders)
    )
