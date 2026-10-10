"""Heuristic third-party attribution from DEX package paths.

This module answers one narrow question: does a class descriptor fall inside a
package range for which a vendor has published a package name? It never claims
that the SDK collected anything, and its output is a reference label only.

Two rules keep the heuristic honest:

* Prefixes match on package-segment boundaries, so ``com.amap.api.location``
  covers ``com.amap.api.location.core.L`` but never ``com.amap.api.locationx.L``.
* Platform and language-runtime namespaces are excluded outright, so a custom
  class under ``androidx`` or a reimplementation under ``com.android`` is never
  attributed to a vendor.
"""

from __future__ import annotations

PREFIX = "L"


def descriptor_to_class(descriptor: str) -> str | None:
    """Convert a JVM descriptor to a dot-separated class name.

    Accepts object descriptors (``Lcom/foo/Bar;``) and array descriptors
    (``[Lcom/foo/Bar;``). Returns ``None`` for primitives and malformed input.
    """
    if not descriptor:
        return None
    value = descriptor
    while value.startswith("["):
        value = value[1:]
    if not value.startswith(PREFIX) or not value.endswith(";"):
        return None
    body = value[1:-1]
    if not body or "/" not in body:
        return None
    return body.replace("/", ".")


def _package_of(class_name: str) -> str:
    return class_name.rsplit(".", 1)[0] if "." in class_name else ""


def _is_excluded(class_name: str, excluded: tuple[str, ...]) -> bool:
    return any(class_name == item or class_name.startswith(item + ".") for item in excluded)


def _matches_prefix(class_name: str, prefix: str) -> bool:
    return class_name == prefix or class_name.startswith(prefix + ".")


class SdkIndex:
    """Immutable lookup built once per scan from a validated ruleset."""

    def __init__(self, rules: dict):
        self.version = rules["version"]
        self.signatures = rules["signatures"]
        self.excluded = tuple(sorted(rules.get("excluded_namespaces", ())))
        # Longest prefix first: a more specific range wins over a broader one.
        self._index: list[tuple[str, dict]] = sorted(
            (
                (prefix, signature)
                for signature in self.signatures
                for prefix in signature["package_prefixes"]
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def match(self, class_name: str) -> dict | None:
        """Return the attribution label for a class name, or ``None``."""
        if not class_name or _is_excluded(class_name, self.excluded):
            return None
        for prefix, signature in self._index:
            if _matches_prefix(class_name, prefix):
                return signature
        return None

    def match_descriptor(self, descriptor: str) -> dict | None:
        class_name = descriptor_to_class(descriptor)
        if class_name is None:
            return None
        return self.match(class_name)


def load_index(rules: dict) -> SdkIndex:
    """Validate the essential structure before trusting a ruleset."""
    for signature in rules.get("signatures", ()):
        for field in ("id", "vendor", "package_prefixes", "potential_data_types"):
            if not signature.get(field):
                raise ValueError(f"SDK signature {signature.get('id')!r} lacks {field}")
        for prefix in signature["package_prefixes"]:
            if prefix != prefix.strip(".") or ".." in prefix or not prefix:
                raise ValueError(f"Malformed package prefix {prefix!r}")
    excluded = rules.get("excluded_namespaces", ())
    if not isinstance(excluded, list) or not excluded:
        raise ValueError("A ruleset must declare excluded_namespaces")
    return SdkIndex(rules)


def package_of(class_name: str) -> str:
    """Expose the containing package for evidence locators."""
    return _package_of(class_name)
