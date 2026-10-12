"""Clone controlled CLI jobs and add UI lifecycle fixtures, outside evaluation denominators."""

import argparse
from datetime import datetime, timezone
from pathlib import Path

from privacytrace.job_store import JobStore
from privacytrace.models import AnalysisJob
from privacytrace.policy_intake import read_safe
from privacytrace.resources import taxonomy

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    jobs = JobStore(args.store_dir).list()
    if len(jobs) != 6 or any(job.input_mode != "CONTROLLED_APK" for job in jobs):
        raise ValueError("Browser validation requires six controlled CLI jobs")
    args.output.mkdir(parents=True, exist_ok=False)
    for job in jobs:
        (args.output / (job.id + ".json")).write_bytes(
            read_safe(args.store_dir / (job.id + ".json"))
        )
    store = JobStore(args.output)
    for suffix, state, error in [
        ("queued", "QUEUED", None),
        ("failed", "FAILED", "UI_VALIDATION_FAILURE: test fixture"),
    ]:
        store.create_if_absent(
            AnalysisJob(
                id="ui-validation-" + suffix,
                sample_id="UI fixture " + suffix,
                input_mode="APK",
                source_origin="CONTROLLED",
                state=state,
                error=error,
                ruleset_version=taxonomy()["version"],
                created_at=datetime.now(timezone.utc),
            )
        )
