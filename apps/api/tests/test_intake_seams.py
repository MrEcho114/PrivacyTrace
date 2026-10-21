"""The durable intake must never fall back to a module-level sandbox helper.

BUG-01（#73 H01）的形态：`WebIntake._discover_sources` 直接调用了模块级
`inspect_package_isolated`，而持久化控制面（`DurableWebIntake`）按设计没有 Docker
socket，于是政策发现必然 503，而上传路径（走注入的 Runner 检查器）一切正常。

行为测试只能覆盖当时那一个调用点；这条结构性检查覆盖“下一个新端点又直接调模块级
helper”的情况：允许调用，但必须显式传入 `inspector=`，把隔离边界显式化。别名导入
（`from ... import inspect_uploaded_package as alias`）不在检查范围内。
"""

import ast
from pathlib import Path

SOURCE = (
    Path(__file__).resolve().parents[1] / "src" / "privacytrace" / "durable_intake.py"
)

# Helpers that shell out to a local sandbox unless an inspector is injected.
SANDBOX_HELPERS = {"inspect_package_isolated", "inspect_uploaded_package"}


def _callee_name(node: ast.Call) -> str | None:
    if isinstance(node.func, ast.Name):
        return node.func.id
    if isinstance(node.func, ast.Attribute):
        return node.func.attr
    return None


def _unscoped_calls(source: str) -> list[str]:
    offenders: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if not isinstance(node, ast.Call):
            continue
        name = _callee_name(node)
        if name not in SANDBOX_HELPERS:
            continue
        keywords = {keyword.arg for keyword in node.keywords}
        if "inspector" not in keywords:
            offenders.append(f"{name}() at line {node.lineno}")
    return offenders


def test_detector_flags_bare_and_module_qualified_calls():
    source = """
from privacytrace import web_intake
web_intake.inspect_uploaded_package(path, timeout=1)
inspect_package_isolated(path, timeout=1)
inspect_uploaded_package(path, timeout=1, inspector=runner)
"""
    assert _unscoped_calls(source) == [
        "inspect_uploaded_package() at line 3",
        "inspect_package_isolated() at line 4",
    ]


def test_durable_intake_injects_its_inspector():
    offenders = _unscoped_calls(SOURCE.read_text(encoding="utf-8"))
    assert offenders == [], (
        "durable_intake.py calls a sandbox helper without an injected inspector; "
        "the control plane has no Docker socket: " + ", ".join(offenders)
    )
