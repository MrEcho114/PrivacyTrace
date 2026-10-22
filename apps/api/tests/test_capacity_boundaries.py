"""A spent capacity budget is a boundary, not an input rejection.

Operators need the refusal code and, where the product can estimate a wait, a
retry hint; the caller must also be able to tell a byte budget from a full disk.
"""

import errno
import shutil
import types

import pytest

from privacytrace.capacity import CapacityRefused
from privacytrace.material_lifecycle import MaterialLifecycle
from privacytrace.web_api import web_error


def test_capacity_refusal_maps_to_429_with_retry_hint():
    response = web_error(
        CapacityRefused(
            "ADMISSION_CAPACITY_REACHED", "Durable task admission capacity reached", retry_after=5
        )
    )

    assert response.status_code == 429
    assert response.detail == "ADMISSION_CAPACITY_REACHED"
    assert response.headers == {"Retry-After": "5"}


@pytest.mark.parametrize(
    "code", ["DRAFT_QUOTA_REACHED", "CLIENT_DRAFT_QUOTA_REACHED", "MATERIAL_BUDGET_REACHED"]
)
def test_capacity_refusal_without_hint_maps_to_429_without_header(code):
    response = web_error(CapacityRefused(code, "budget spent"))

    assert response.status_code == 429
    assert response.detail == code
    assert response.headers is None


def test_capacity_refusal_stays_catchable_as_a_value_error():
    # Legacy seams still translate ValueError; the new type narrows nothing.
    assert isinstance(CapacityRefused("DRAFT_QUOTA_REACHED", "budget"), ValueError)


def test_a_full_material_volume_is_storage_exhaustion_not_a_waitable_budget():
    # The caller cannot wait this one out: the operator has to free the volume, so a
    # Retry-After hint would be a lie.
    response = web_error(
        CapacityRefused("MATERIAL_DISK_SPACE_REACHED", "Private material disk space exhausted")
    )

    assert response.status_code == 507
    assert response.detail == "MATERIAL_DISK_SPACE_REACHED"
    assert response.headers is None


@pytest.mark.parametrize("code", [errno.ENOSPC, errno.EDQUOT])
def test_exhausted_private_material_disk_maps_to_507(code):
    response = web_error(OSError(code, "no space"))

    assert response.status_code == 507
    assert response.detail == "PRIVATE_MATERIAL_DISK_FULL"


def test_unrelated_os_error_is_not_reported_as_a_full_disk():
    response = web_error(OSError(errno.EACCES, "denied"))

    assert response.status_code == 409
    assert response.detail == "INPUT_OR_VERSION_REJECTED"


class _Intake:
    def __init__(self, root):
        self.root = root

    def _safe(self, path):
        return path


def _lifecycle(root):
    return MaterialLifecycle(store=None, intake=_Intake(root))


def test_byte_budget_refusal_names_the_budget(tmp_path):
    (tmp_path / "material.bin").write_bytes(b"x" * 32)
    lifecycle = _lifecycle(tmp_path)
    lifecycle.MAX_BYTES = 32

    with pytest.raises(CapacityRefused) as refused:
        lifecycle.admit_upload(1)

    assert refused.value.code == "MATERIAL_BUDGET_REACHED"


def test_free_space_refusal_names_the_disk(tmp_path, monkeypatch):
    lifecycle = _lifecycle(tmp_path)
    monkeypatch.setattr(
        shutil, "disk_usage", lambda root: types.SimpleNamespace(total=1024, used=1024, free=0)
    )

    with pytest.raises(CapacityRefused) as refused:
        lifecycle.admit_upload(1)

    assert refused.value.code == "MATERIAL_DISK_SPACE_REACHED"
