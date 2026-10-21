"""Actual snapshot, fresh restore and independent deletion replay evidence."""

import os

from .provision import ROOT, Laboratory
from .r2_business_loop import cleanup_created_scopes
from .receipt import CheckRecorder, Receipt, read_source_sha, utc_now
from .topology import Topology


def run():
    receipt = Receipt(scope="r5-backup-recovery-drills", source_sha=read_source_sha(ROOT))
    state = os.environ.get("PT_ACCEPTANCE_LAB_STATE")
    topology = Topology.from_env()
    recorder = CheckRecorder(
        "r5.snapshot_restore_deletion_replay",
        "quiesce -> snapshot -> delete -> fresh migrated DB/volume -> restore/readback",
        ticket="R5",
    )
    if not state or not topology.allow_destructive or not topology.allow_writes:
        receipt.checks.append(recorder.skip("an owned provision.py laboratory is required"))
    else:
        from .backup_drill import drill

        try:
            result = drill(Laboratory(state), topology)
            receipt.checks.append(
                recorder.pass_("snapshot and deletion replay read back", **result)
            )
        except Exception as error:
            receipt.checks.append(recorder.fail(type(error).__name__))
    if state and topology.allow_destructive and topology.allow_writes:
        cleanup = cleanup_created_scopes()
        if cleanup:
            receipt.checks.append(
                CheckRecorder("r5.cleanup", "delete owned canaries", ticket="R5").fail(
                    "cleanup failed", statuses=cleanup
                )
            )
    for name in ("credential_rotation", "disk_full", "upgrade_rollback"):
        recorder = CheckRecorder("r5." + name, "separate deployment drill", ticket="R5")
        if not state or not topology.allow_destructive or not topology.allow_writes:
            receipt.checks.append(recorder.skip("an owned provision.py laboratory is required"))
            continue
        from . import operations_drills as ops

        lab = Laboratory(state)
        try:
            if name == "credential_rotation":
                result = {
                    **ops.rotate_database_and_broker(lab, topology),
                    **ops.rotate_control_identity(lab),
                }
            elif name == "disk_full":
                result = ops.disk_full(lab, topology)
            else:
                previous = os.environ.get("PT_ACCEPTANCE_PREVIOUS_API_IMAGE")
                if not previous:
                    receipt.checks.append(recorder.skip("explicit previous API image is required"))
                    continue
                result = ops.upgrade_rollback(lab, topology, previous)
            receipt.checks.append(recorder.pass_("actual deployment drill completed", **result))
        except Exception as error:
            import traceback

            frame = traceback.extract_tb(error.__traceback__)[-1]
            receipt.checks.append(
                recorder.fail(type(error).__name__, function=frame.name, line=frame.lineno)
            )
        finally:
            failures = cleanup_created_scopes()
            if failures:
                receipt.checks.append(
                    CheckRecorder("r5.cleanup", "delete owned canaries", ticket="R5").fail(
                        "cleanup failed", statuses=failures
                    )
                )
    receipt.finished_at = utc_now()
    return receipt
