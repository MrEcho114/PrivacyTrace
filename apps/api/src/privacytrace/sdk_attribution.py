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

The ruleset shape is owned by :mod:`privacytrace.sdk_ruleset`; this module only
consumes a validated instance.
"""

from __future__ import annotations

from .sdk_ruleset import SdkSignature, SdkSignatureRuleset

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


def _is_excluded(class_name: str, excluded: tuple[str, ...]) -> bool:
    return any(class_name == item or class_name.startswith(item + ".") for item in excluded)


def _matches_prefix(class_name: str, prefix: str) -> bool:
    return class_name == prefix or class_name.startswith(prefix + ".")


class SdkIndex:
    """Immutable lookup built once per scan from a validated ruleset."""

    def __init__(self, rules: SdkSignatureRuleset):
        self.version = rules.version
        self.signatures = tuple(rules.signatures)
        self.excluded = tuple(sorted(rules.excluded_namespaces))
        # Longest prefix first: a more specific range wins over a broader one.
        self._index: list[tuple[str, SdkSignature]] = sorted(
            (
                (prefix, signature)
                for signature in rules.signatures
                for prefix in signature.package_prefixes
            ),
            key=lambda item: len(item[0]),
            reverse=True,
        )

    def match(self, class_name: str) -> SdkSignature | None:
        """Return the attribution label for a class name, or ``None``."""
        if not class_name or _is_excluded(class_name, self.excluded):
            return None
        for prefix, signature in self._index:
            if _matches_prefix(class_name, prefix):
                return signature
        return None

    def match_descriptor(self, descriptor: str) -> SdkSignature | None:
        class_name = descriptor_to_class(descriptor)
        if class_name is None:
            return None
        return self.match(class_name)


def load_index(rules: dict | SdkSignatureRuleset) -> SdkIndex:
    """Validate the ruleset through its contract model, then index it."""
    validated = (
        rules
        if isinstance(rules, SdkSignatureRuleset)
        else SdkSignatureRuleset.model_validate(rules)
    )
    return SdkIndex(validated)
