"""Unit tests for the bounded SDK attribution collector.

The collector is the guard that keeps SDK attribution output bounded: a DEX can
reference an attacker-controlled number of classes, so holding every match and
truncating afterwards would let one APK drive unbounded memory. These tests drive
the collector directly, without building large APKs, so the memory bound, the
per-SDK fairness guarantee and the determinism guarantee are each pinned.
"""

import pytest

from privacytrace.sdk_attribution import SdkAttributionCollector, SdkMatch
from privacytrace.sdk_ruleset import SdkSignature


def segment(signature_id: str) -> str:
    """A package segment the ruleset contract accepts (identifiers only)."""
    return signature_id.replace("-", "_")


def signature(signature_id: str) -> SdkSignature:
    """A minimal valid signature; only the id matters to the collector."""
    return SdkSignature(
        id=signature_id,
        name="name-" + signature_id,
        vendor="vendor-" + signature_id,
        package_prefixes=["com.example." + segment(signature_id)],
        potential_data_types=["LOCATION"],
        source="fixture source",
        source_url="https://example.invalid/source",
        license="Proprietary",
        verified_at="2026-10-11",
        note="fixture",
    )


def class_name(signature_id: str, leaf: str) -> str:
    return f"com.example.{segment(signature_id)}.{leaf}"


def match(signature_id: str, leaf: str, dex: str = "classes.dex") -> SdkMatch:
    return SdkMatch(
        signature=signature(signature_id),
        prefix="com.example." + segment(signature_id),
        class_name=class_name(signature_id, leaf),
        dex=dex,
    )


def collector(capacity: int = 500, **kwargs) -> SdkAttributionCollector:
    return SdkAttributionCollector(capacity=capacity, **kwargs)


def test_retained_candidates_never_exceed_capacity():
    """The whole point: a hostile APK cannot grow the retained set past the cap."""
    subject = collector(capacity=500)
    for index in range(100_000):
        subject.add(match("sdk-a", f"C{index}"))
    assert subject.retained == 500
    assert subject.signature_count == 1
    assert subject.observed == 100_000
    assert subject.capped
    assert len(subject.selected()) == 500


def test_representatives_never_exceed_the_signature_count():
    subject = collector(capacity=10)
    for index in range(50):
        subject.add(match(f"sdk-{index}", "C"))
    # 50 distinct signatures were seen, so 50 representatives are held: bounded by
    # the ruleset, not by the number of classes.
    assert subject.signature_count == 50
    assert subject.retained <= 10


def test_a_flooding_sdk_cannot_evict_another_sdks_representative():
    """One SDK with 10,000 classes must not push a second SDK out of the report."""
    subject = collector(capacity=500)
    for index in range(10_000):
        subject.add(match("sdk-flood", f"C{index}"))
    subject.add(match("sdk-rare", "Only"))

    selected = subject.selected()
    assert len(selected) <= 500
    assert {item.signature.id for item in selected} == {"sdk-flood", "sdk-rare"}


def test_the_same_class_is_recorded_once():
    subject = collector(capacity=10)
    for _ in range(3):
        subject.add(match("sdk-a", "C"))

    selected = subject.selected()
    assert len(selected) == 1
    # Duplicates are still counted as observed events, which is exactly why
    # `observed` must not be reported as a unique class total.
    assert subject.observed == 3


def test_one_class_in_two_dexes_stays_one_attribution():
    """Identity is (label, class); the DEX is a locator detail, not part of it."""
    subject = collector(capacity=10)
    subject.add(match("sdk-a", "C", dex="classes.dex"))
    subject.add(match("sdk-a", "C", dex="classes2.dex"))

    selected = subject.selected()
    assert len(selected) == 1
    assert len({item.evidence_id for item in selected}) == 1


def test_selected_ids_are_unique():
    subject = collector(capacity=50)
    for signature_id in ("sdk-a", "sdk-b", "sdk-c"):
        for index in range(100):
            subject.add(match(signature_id, f"C{index}"))

    selected = subject.selected()
    assert len(selected) <= 50
    assert len({item.evidence_id for item in selected}) == len(selected)


def test_selection_is_identical_for_repeated_runs():
    def build() -> list[tuple[str, str]]:
        subject = collector(capacity=50)
        for signature_id in ("sdk-a", "sdk-b", "sdk-c"):
            for index in range(100):
                subject.add(match(signature_id, f"C{index}"))
        return [(item.evidence_id, item.class_name) for item in subject.selected()]

    assert build() == build()


def test_selection_does_not_depend_on_insertion_order():
    """The retained set is chosen by stable key, so traversal order cannot leak."""
    forward = collector(capacity=3)
    backward = collector(capacity=3)
    for index in range(10):
        forward.add(match("sdk-a", f"C{index:02d}"))
        backward.add(match("sdk-a", f"C{9 - index:02d}"))

    assert [item.class_name for item in forward.selected()] == [
        item.class_name for item in backward.selected()
    ]


def test_exactly_enough_slots_for_one_representative_each():
    """500 signatures in 500 slots: the floor is exactly payable."""
    subject = collector(capacity=500)
    for index in range(500):
        subject.add(match(f"sdk-{index:03d}", "C"))

    assert subject.per_sdk_floor_is_achievable()
    selected = subject.selected()
    assert len(selected) == 500
    assert {item.signature.id for item in selected} == {f"sdk-{i:03d}" for i in range(500)}


def test_more_signatures_than_slots_is_reported_not_hidden():
    """The floor is unpayable here, and the collector must say so."""
    subject = collector(capacity=2)
    for index in range(5):
        subject.add(match(f"sdk-{index}", "C"))

    assert not subject.per_sdk_floor_is_achievable()
    assert len(subject.selected()) == 2


def test_no_quota_is_handed_out_when_it_cannot_be_honoured():
    scarce = collector(capacity=2, max_representatives=1)
    for index in range(5):
        scarce.add(match(f"sdk-{index}", "C"))
    assert scarce._quota() == 0


def test_quota_is_capped_by_max_representatives():
    """A single SDK cannot claim the whole budget through the reserved pass."""
    subject = collector(capacity=500, max_representatives=3)
    for index in range(100):
        subject.add(match("sdk-a", f"C{index:03d}"))
    assert subject._quota() == 3


@pytest.mark.parametrize("capacity", [1, 2, 7, 500])
def test_capacity_floor_is_respected_for_any_budget(capacity):
    subject = collector(capacity=capacity)
    for index in range(capacity * 4):
        subject.add(match("sdk-a", f"C{index:03d}"))
    selected = subject.selected()
    assert 0 < len(selected) <= capacity
    assert subject.retained <= capacity


def test_zero_capacity_is_rejected():
    with pytest.raises(ValueError):
        SdkAttributionCollector(capacity=0)


def test_empty_collector_selects_nothing():
    subject = collector(capacity=10)
    assert subject.selected() == []
    assert subject.per_sdk_floor_is_achievable()
    assert not subject.capped
