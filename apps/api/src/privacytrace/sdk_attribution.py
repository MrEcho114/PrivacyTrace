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

import hashlib
import heapq
from dataclasses import dataclass

from .sdk_ruleset import SdkSignature, SdkSignatureRuleset

PREFIX = "L"


@dataclass(frozen=True)
class SdkMatch:
    """One attribution plus the exact prefix that produced it.

    A signature may publish several prefixes (``com.umeng.analytics`` and
    ``com.umeng.commonsdk``). Reporting the signature alone would let a caller
    guess ``package_prefixes[0]`` and publish a prefix the class never touched,
    so the matched prefix travels with the label.
    """

    signature: SdkSignature
    prefix: str
    class_name: str
    dex: str = ""

    @property
    def key(self) -> tuple[str, str]:
        """Identity of one attribution: the label plus the class it was found on.

        Deliberately excludes ``dex``: the same class appearing in more than one
        DEX is one attribution, and a key that included the DEX would emit two
        records sharing one evidence id.
        """
        return (self.signature.id, self.class_name)

    @property
    def evidence_id(self) -> str:
        """Deterministic evidence id, derived from the label and the class path."""
        digest = hashlib.sha256(
            (self.signature.id + "\x00" + self.class_name).encode()
        ).hexdigest()[:24]
        return "ev-sdk-" + digest

    @property
    def order_key(self) -> tuple[str, str]:
        """Stable selection key. Never depends on object identity or hash order."""
        return self.key


class SdkAttributionCollector:
    """Bounded-memory collector for SDK attribution matches.

    A DEX can reference far more classes than a report can list, and the number is
    attacker-controlled. Collecting every match and truncating afterwards would let
    a single APK drive unbounded memory; this keeps two bounded structures instead:

    * **representatives** — the lowest-ordered match per signature, so the cap can
      never drop a flagged SDK from the report entirely. Bounded by the number of
      signatures in the ruleset, which the contract caps at 500.
    * **candidates** — the ``capacity`` lowest-ordered matches overall, held in a
      max-heap so the retained set is independent of traversal order and each
      insert costs ``O(log capacity)``.

    Memory is therefore ``O(signatures + capacity)`` regardless of how many classes
    the APK contains. Neither structure is a full seen-set, so ``observed`` counts
    match *events* (duplicates included) and must not be reported as a unique class
    total; ``capped`` is the honest signal that the report is a subset.
    """

    def __init__(
        self,
        capacity: int,
        min_representatives: int = 1,
        max_representatives: int = 100,
    ):
        if capacity < 1:
            raise ValueError("capacity must be at least 1")
        self.capacity = capacity
        self.min_representatives = min_representatives
        self.max_representatives = max_representatives
        self.observed = 0
        self.capped = False
        self._representatives: dict[str, SdkMatch] = {}
        self._candidates: dict[tuple[str, str], SdkMatch] = {}
        self._worst_first: list[_Reversed] = []

    def add(self, match: SdkMatch) -> None:
        """Record one match. Never grows past the bounds; discards or evicts instead."""
        self.observed += 1
        current = self._representatives.get(match.signature.id)
        if current is None or match.order_key < current.order_key:
            self._representatives[match.signature.id] = match
        key = match.order_key
        if key in self._candidates:
            return
        if len(self._candidates) >= self.capacity:
            worst = self._peek_worst()
            # Keeping the lowest-ordered candidates only works if a worse arrival
            # is dropped rather than displacing a better one. Evicting blindly
            # would make the retained set depend on insertion order.
            if worst is None or key >= worst:
                self.capped = True
                return
            self._drop_worst()
        self._candidates[key] = match
        heapq.heappush(self._worst_first, _Reversed(key))

    def _peek_worst(self) -> tuple[str, str] | None:
        """The largest retained order key, skipping entries already evicted."""
        while self._worst_first:
            key = self._worst_first[0].value
            if key in self._candidates:
                return key
            heapq.heappop(self._worst_first)
        return None

    def _drop_worst(self) -> None:
        """Evict the retained candidate with the largest order key."""
        key = self._peek_worst()
        if key is not None:
            del self._candidates[key]
            self.capped = True

    @property
    def signature_count(self) -> int:
        return len(self._representatives)

    @property
    def retained(self) -> int:
        """Class-level candidates currently held. Never exceeds ``capacity``."""
        return len(self._candidates)

    def per_sdk_floor_is_achievable(self) -> bool:
        """Whether every flagged signature can keep a representative inside the cap."""
        return self.signature_count * self.min_representatives <= self.capacity

    def _quota(self) -> int:
        """Slots each signature may take in the reserved pass, 0 when it cannot pay."""
        if not self.signature_count:
            return 0
        share = self.capacity // self.signature_count
        if share < self.min_representatives:
            # More signatures than slots: the floor cannot be honoured, so don't
            # hand out a share that pretends otherwise.
            return 0
        return min(self.max_representatives, share)

    def selected(self) -> list[SdkMatch]:
        """The report set: one representative per signature, then class detail.

        Deterministic for any insertion order, so the report never drifts.
        """
        chosen: dict[tuple[str, str], SdkMatch] = {}
        # 1. Every flagged signature keeps a representative, or as many as fit.
        for signature_id in sorted(self._representatives):
            if len(chosen) >= self.capacity:
                break
            match = self._representatives[signature_id]
            chosen[match.order_key] = match
        # 2. Each signature may add detail up to its share of the budget.
        quota = self._quota()
        if quota > 1 and len(chosen) < self.capacity:
            by_signature: dict[str, list[SdkMatch]] = {}
            for match in self._candidates.values():
                by_signature.setdefault(match.signature.id, []).append(match)
            for signature_id in sorted(by_signature):
                for match in sorted(by_signature[signature_id], key=_by_order)[:quota]:
                    if len(chosen) >= self.capacity:
                        break
                    chosen.setdefault(match.order_key, match)
        # 3. Remaining budget goes to class-level detail in stable order.
        for key in sorted(self._candidates):
            if len(chosen) >= self.capacity:
                break
            chosen.setdefault(key, self._candidates[key])
        return sorted(chosen.values(), key=_by_order)


def _by_order(match: SdkMatch) -> tuple[str, str]:
    return match.order_key


class _Reversed:
    """Wraps an order key so ``heapq`` (a min-heap) pops the *largest* first."""

    __slots__ = ("value",)

    def __init__(self, value: tuple[str, str]):
        self.value = value

    def __lt__(self, other: "_Reversed") -> bool:
        return self.value > other.value


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

    def match_prefix(self, class_name: str) -> SdkMatch | None:
        """Return the label plus the exact matching prefix, or ``None``."""
        if not class_name or _is_excluded(class_name, self.excluded):
            return None
        for prefix, signature in self._index:
            if _matches_prefix(class_name, prefix):
                return SdkMatch(signature=signature, prefix=prefix, class_name=class_name)
        return None

    def match(self, class_name: str) -> SdkSignature | None:
        """Return the attribution label for a class name, or ``None``."""
        found = self.match_prefix(class_name)
        return found.signature if found is not None else None

    def match_descriptor_with_prefix(self, descriptor: str) -> SdkMatch | None:
        class_name = descriptor_to_class(descriptor)
        if class_name is None:
            return None
        return self.match_prefix(class_name)

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
