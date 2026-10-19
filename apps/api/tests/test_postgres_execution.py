"""Real PostgreSQL execution races, revocation and crash recovery.

Report payloads use the existing controlled contract fixture, not an APK scan.
Database tests require separate roles and an explicit disposable *_test database.
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_capability_tokens import controlled_bundle
from test_postgres_storage import migration, queued
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import store as store

from privacytrace.postgres_execution import MAX_EXECUTIONS, LeaseLost, PostgresExecution
from privacytrace.postgres_outbox import MAX_ATTEMPTS, PostgresOutbox
from privacytrace.postgres_schema import audit, executions, outbox
from privacytrace.postgres_store import PostgresJobStore


def ready(store, *, delivered=False):
    events = PostgresOutbox(store)
    event = events.register(queued(), "a" * 64)
    claimed = next(value for value in events.claim() if value.event_id == event.event_id)
    if delivered:
        assert events.acknowledge(str(event.event_id), str(claimed.claim_token))
    return event


def sibling(store, instance=None):
    return PostgresJobStore(
        store.engine.url, instance or store.instance_id, store.root.parent.parent
    )


def due(store, job_id, *, expire=False):
    with store._transaction() as conn:
        past = sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'")
        conn.execute(
            executions.update()
            .where(executions.c.job_id == job_id)
            .values({"leased_until" if expire else "available_at": past})
        )
        if not expire:
            conn.execute(outbox.update().where(outbox.c.job_id == job_id).values(available_at=past))


def report_input(store, job_id):
    bundle = controlled_bundle()
    bundle.job = store.get(job_id).model_copy(
        deep=True, update={"state": "SUCCEEDED", "error": None}
    )
    metadata = dict(
        name="contract fixture",
        package_name="org.privacytrace.demo",
        version_name="1",
        version_code=1,
        apk_sha256="a" * 64,
        permissions=[],
        dex_entries=["classes.dex"],
    )
    coverage = dict(status="COMPLETE", limitations=[], scanned_dex=["classes.dex"], failed_dex=[])
    return bundle, metadata, coverage, {"scanner": "CONTROLLED_CONTRACT_FACTS_ONLY"}


def test_registration_rolls_back_execution_together_with_job_and_event(store):
    job = queued()
    with pytest.raises(RuntimeError):
        with store._transaction():
            event = PostgresOutbox(store).register(job)
            assert PostgresExecution(store).status(job.id)["event_id"] == event.event_id
            raise RuntimeError("abort")
    with pytest.raises(KeyError):
        PostgresExecution(store).status(job.id)
    with pytest.raises(KeyError):
        store.get(job.id)


def test_only_registered_claimed_event_can_acquire_and_duplicate_cannot(store):
    executions_api = PostgresExecution(store)
    event = PostgresOutbox(store).register(queued())
    assert executions_api.acquire(event.message) is None  # Not published/claimed yet.
    PostgresOutbox(store).claim()
    for changed in [{"job_id": queued().id}, {"event_id": str(uuid4())}]:
        assert executions_api.acquire({**event.message, **changed}) is None
    lease = executions_api.acquire(event.message)
    assert lease.attempt == lease.fence == 1
    assert executions_api.acquire(event.message) is None
    other = sibling(store)
    try:
        assert PostgresExecution(other).acquire(event.message) is None
        PostgresExecution(other).checkpoint(lease)
    finally:
        other.close()


def test_parallel_independent_connections_grant_exactly_one_owner(store):
    event, barrier = ready(store), Barrier(4)

    def acquire(_):
        other = sibling(store)
        try:
            barrier.wait(timeout=10)
            return PostgresExecution(other).acquire(event.message)
        finally:
            other.close()

    with ThreadPoolExecutor(4) as pool:
        leases = list(pool.map(acquire, range(4)))
    assert len([value for value in leases if value is not None]) == 1
    assert PostgresExecution(store).status(event.job_id)["attempt"] == 1


def test_advancing_pipeline_does_not_discard_inflight_delivery_ack(store):
    event = ready(store)
    api = PostgresExecution(store)
    lease = api.acquire(event.message)
    job = store.get(event.job_id)
    job.state = "STATIC_ANALYSIS"
    api.fenced_store(lease).save_job(job)
    claimed = PostgresOutbox(store).get(str(event.event_id))
    assert PostgresOutbox(store).acknowledge(str(event.event_id), str(claimed.claim_token))
    assert PostgresOutbox(store).get(str(event.event_id)).state == "DELIVERED"
    assert api.acquire(event.message) is None


def test_heartbeat_uses_database_clock_and_never_resurrects_expired_owner(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message, lease_seconds=5)
    updated = api.heartbeat(lease, lease_seconds=60)
    assert updated.leased_until > lease.leased_until
    assert updated.owner == lease.owner and updated.fence == lease.fence
    due(store, event.job_id, expire=True)
    for operation in [lambda: api.heartbeat(lease), lambda: api.checkpoint(lease)]:
        with pytest.raises(LeaseLost):
            operation()


def test_heartbeat_does_not_extend_beyond_total_attempt_deadline(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    with store._transaction() as conn:
        conn.execute(
            executions.update()
            .where(executions.c.job_id == event.job_id)
            .values(started_at=sa.func.clock_timestamp() - sa.text("INTERVAL '299 seconds'"))
        )
    updated = api.heartbeat(lease, lease_seconds=300)
    with store._transaction() as conn:
        remaining = (updated.leased_until - api._now(conn)).total_seconds()
    assert 0 < remaining < 2


@pytest.mark.parametrize("action", ["cancel", "delete"])
def test_revocation_and_fence_change_commit_atomically_and_reject_late_results(store, action):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    payload = report_input(store, event.job_id)
    getattr(store, action)(event.job_id)
    state = api.status(event.job_id)
    assert state["state"] == "REVOKED" and state["fence"] > lease.fence
    assert state["owner"] is None and state["leased_until"] is None
    for operation in [
        lambda: api.checkpoint(lease),
        lambda: api.heartbeat(lease),
    ]:
        with pytest.raises(LeaseLost):
            operation()
    with pytest.raises(LeaseLost):
        api.fenced_store(lease).save(*payload)
    assert api.recover() == {"retried": 0, "failed": 0}
    assert api.acquire(event.message) is None
    assert (
        store.is_tombstoned(event.job_id)
        if action == "delete"
        else store.get(event.job_id).state == "CANCELLED"
    )


def test_report_and_success_are_atomic_and_duplicate_identical_submission_is_read_only(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    fenced = api.fenced_store(lease)
    payload = report_input(store, event.job_id)
    first = fenced.save(*payload)
    with store._transaction() as conn:
        count = conn.scalar(sa.select(sa.func.count()).select_from(audit))
    replay = fenced.save(*payload)
    assert first.result == replay.result and replay.job.state == "SUCCEEDED"
    assert store.get_token_digest(event.job_id) == "a" * 64
    assert api.status(event.job_id)["state"] == "SUCCEEDED"
    with store._transaction() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == count
    for altered in [
        replace(lease, owner=uuid4()),
        replace(lease, fence=lease.fence + 1),
        replace(lease, event_id=uuid4()),
        replace(lease, attempt=2),
    ]:
        with pytest.raises(LeaseLost):
            api.fenced_store(altered).save(*payload)
    with pytest.raises(LeaseLost):
        api.fenced_store(replace(lease, instance_id=str(uuid4())))
    with pytest.raises(LeaseLost):
        fenced.save(*payload[:3], {"scanner": "different-result"})
    assert api.acquire(event.message) is None
    store.delete(event.job_id)
    with pytest.raises(LeaseLost):
        fenced.save(*payload)


def test_real_commit_rejection_rolls_back_report_execution_and_audit(store, postgres_urls):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    payload = report_input(store, event.job_id)
    parent, child = "pt80_parent_" + uuid4().hex, "pt80_child_" + uuid4().hex
    owner = sa.create_engine(postgres_urls[1], hide_parameters=True)
    with owner.begin() as conn:
        conn.execute(sa.text(f"CREATE TABLE privacytrace.{parent} (id int PRIMARY KEY)"))
        conn.execute(
            sa.text(
                f"CREATE TABLE privacytrace.{child} (id int REFERENCES privacytrace.{parent} "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
        )
        conn.execute(
            sa.text(f'GRANT INSERT ON privacytrace.{child} TO "{store.engine.url.username}"')
        )
    with store._transaction() as conn:
        before = conn.scalar(sa.select(sa.func.count()).select_from(audit))
    try:
        with pytest.raises(ValueError, match="PostgreSQL storage rejected") as error:
            with store._transaction() as conn:
                api.fenced_store(lease).save(*payload)
                conn.execute(sa.text(f"INSERT INTO privacytrace.{child} VALUES (1)"))
        assert error.value.__context__.orig.sqlstate == "23503"
        assert api.status(event.job_id)["state"] == "RUNNING"
        assert store.get(event.job_id).state == "QUEUED"
        with pytest.raises(ValueError, match="not available"):
            store.report(event.job_id)
        with store._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(audit)) == before
        api.fenced_store(lease).save(*payload)  # Same token is usable after the rollback.
    finally:
        with owner.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE privacytrace.{child}"))
            conn.execute(sa.text(f"DROP TABLE privacytrace.{parent}"))
        owner.dispose()


def test_internal_retry_retains_job_and_budget_and_old_fence_cannot_publish(store):
    api, event = PostgresExecution(store), ready(store, delivered=True)
    lease = api.acquire(event.message)
    payload = report_input(store, event.job_id)
    for attempt in range(1, MAX_EXECUTIONS + 1):
        assert lease.attempt == attempt
        if attempt == MAX_EXECUTIONS:
            assert not api.retry(lease, code="RUNNER_UNAVAILABLE", delay_seconds=0)
            break
        assert api.retry(lease, code="RUNNER_UNAVAILABLE", delay_seconds=0)
        assert json.loads(store.get(event.job_id).error)["code"] == "INTERNAL_RETRY"
        assert store.get(event.job_id).retry_of is None
        assert len(store.list()) == 1
        with pytest.raises(LeaseLost):
            api.fenced_store(lease).save(*payload)
        claimed = PostgresOutbox(store).claim()[0]
        assert claimed.event_id == event.event_id and claimed.attempts == attempt + 1
        current = api.acquire(event.message)
        assert current.fence > lease.fence and current.owner != lease.owner
        lease = current
    assert store.get(event.job_id).state == "FAILED"
    assert api.status(event.job_id)["state"] == "FAILED"
    assert api.acquire(event.message) is None
    assert PostgresOutbox(store).claim() == []


def test_failed_pipeline_is_terminal_and_explicit_retry_creates_a_new_job(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    job = store.get(event.job_id)
    job.state, job.error = "FAILED", json.dumps({"code": "CONTAINER_OOM"})
    api.fenced_store(lease).save_job(job)
    assert api.status(job.id)["state"] == "FAILED"
    assert api.acquire(event.message) is None
    assert api.recover() == {"retried": 0, "failed": 0}
    retry = queued()
    retry.retry_of = job.id
    store.create_retry(retry, "a" * 64)
    PostgresOutbox(store).enqueue(retry.id)
    assert len(store.list()) == 2 and store.get(retry.id).retry_of == job.id
    assert api.status(retry.id)["attempt"] == 0


def test_expiry_recovery_invalidates_owner_and_cannot_be_starved_by_ready_jobs(store):
    api = PostgresExecution(store)
    for _ in range(3):
        PostgresOutbox(store).register(queued())
    event = ready(store, delivered=True)
    lease = api.acquire(event.message)
    due(store, event.job_id, expire=True)
    assert api.recover(limit=1) == {"retried": 1, "failed": 0}
    assert api.status(event.job_id)["fence"] > lease.fence
    with pytest.raises(LeaseLost):
        api.checkpoint(lease)
    due(store, event.job_id)
    next_lease = api.acquire(event.message)
    assert next_lease.attempt == 2 and next_lease.fence > lease.fence


def test_lost_broker_message_is_redriven_with_same_event_and_finite_publication_budget(store):
    api, event = PostgresExecution(store), ready(store, delivered=True)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        with store._transaction() as conn:
            conn.execute(
                outbox.update()
                .where(outbox.c.event_id == event.event_id)
                .values(delivered_at=sa.func.clock_timestamp() - sa.text("INTERVAL '301 seconds'"))
            )
        result = api.recover()
        assert result == (
            {"retried": 1, "failed": 0} if attempt < MAX_ATTEMPTS else {"retried": 0, "failed": 1}
        )
        if attempt < MAX_ATTEMPTS:
            due(store, event.job_id)
            delivery = PostgresOutbox(store).claim()[0]
            assert delivery.attempts == attempt + 1
            assert PostgresOutbox(store).acknowledge(str(event.event_id), str(delivery.claim_token))
    assert json.loads(store.get(event.job_id).error)["code"] == "DELIVERY_EXHAUSTED"
    assert api.status(event.job_id)["attempt"] == 0
    assert api.acquire(event.message) is None


def test_exhausted_delivery_becomes_observable_job_failure(store):
    api, event = PostgresExecution(store), ready(store)
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delivery = PostgresOutbox(store).get(str(event.event_id))
        assert PostgresOutbox(store).fail(
            str(event.event_id), str(delivery.claim_token), code="BROKER_UNAVAILABLE"
        )
        if attempt < MAX_ATTEMPTS:
            PostgresOutbox(store).claim()
    assert api.recover() == {"retried": 0, "failed": 1}
    assert store.get(event.job_id).state == "FAILED"


def test_actual_worker_process_exit_recovers_after_real_database_lease_timeout(store):
    api, event = PostgresExecution(store), ready(store)
    result = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import json,os
from pathlib import Path
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.postgres_execution import PostgresExecution
store=PostgresJobStore(os.environ['PRIVACYTRACE_TEST_DATABASE_URL'],os.environ['PT_INSTANCE'],Path(os.environ['PT_ROOT']))
lease=PostgresExecution(store).acquire(json.loads(os.environ['PT_MESSAGE']),lease_seconds=5)
assert lease is not None
os._exit(17)
""",
        ],
        env={
            **os.environ,
            "PT_INSTANCE": store.instance_id,
            "PT_ROOT": str(store.root.parent.parent),
            "PT_MESSAGE": json.dumps(event.message),
        },
        capture_output=True,
        timeout=30,
    )
    assert result.returncode == 17
    abandoned = api.status(event.job_id)
    with store._transaction() as conn:
        now = api._now(conn)
    time.sleep(max(0, (abandoned["leased_until"] - now).total_seconds()) + 0.03)
    assert api.recover() == {"retried": 1, "failed": 0}
    due(store, event.job_id)
    current = api.acquire(event.message)
    assert current.attempt == 2 and current.fence > abandoned["fence"]
    assert current.owner != abandoned["owner"]


def test_cross_instance_same_job_and_event_access_cannot_bypass_rls(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    other = sibling(store, str(uuid4()))
    try:
        with pytest.raises(ValueError, match="instance"):
            PostgresExecution(other).acquire(event.message)
        with pytest.raises(LeaseLost):
            PostgresExecution(other).checkpoint(lease)
        with pytest.raises(KeyError):
            PostgresExecution(other).status(event.job_id)
        with other._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(executions)) == 0
        PostgresOutbox(other).register(queued(event.job_id))
        with (
            pytest.raises(ValueError, match="PostgreSQL storage rejected"),
            other._transaction() as conn,
        ):
            conn.execute(executions.update().values(instance_id=store.instance_id))
    finally:
        other.close()


def test_runtime_has_force_rls_and_cannot_delete_truncate_or_change_schema(store):
    ready(store)
    with store.engine.begin() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(executions)) == 0
        assert conn.execute(
            sa.text(
                "SELECT relrowsecurity,relforcerowsecurity FROM pg_class "
                "WHERE oid='privacytrace.job_executions'::regclass"
            )
        ).one() == (True, True)
    for statement in [
        "DELETE FROM privacytrace.job_executions",
        "TRUNCATE privacytrace.job_executions",
        "ALTER TABLE privacytrace.job_executions DISABLE ROW LEVEL SECURITY",
    ]:
        with store.engine.begin() as conn, pytest.raises(sa.exc.DBAPIError) as error:
            conn.execute(sa.text(statement))
        assert error.value.orig.sqlstate == "42501"


def test_incremental_execution_migration_preserves_jobs_events_and_resumes_scope_locally(
    store, postgres_urls
):
    event = ready(store, delivered=True)
    migration(postgres_urls[1], "check")
    migration(postgres_urls[1], "downgrade", "0080_02")
    try:
        with pytest.raises(ValueError, match="schema version"):
            sibling(store)
    finally:
        migration(postgres_urls[1])
    assert PostgresOutbox(store).get(str(event.event_id)).state == "DELIVERED"
    assert store.get_token_digest(event.job_id) == "a" * 64
    api = PostgresExecution(store)
    api.recover()
    assert api.status(event.job_id)["state"] == "READY"
    assert api.acquire(event.message).attempt == 1
    migration(postgres_urls[1], "check")


def test_delivery_lease_and_retry_operations_cannot_escape_outer_transaction(store):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    for operation in [
        lambda: api.acquire(event.message),
        lambda: api.heartbeat(lease),
        lambda: api.retry(lease, code="WORKER_LOST"),
        lambda: api.recover(),
    ]:
        with store._transaction(), pytest.raises(ValueError, match="standalone"):
            operation()
    for value in [True, 4, 301, "60"]:
        with pytest.raises(ValueError):
            api.heartbeat(lease, lease_seconds=value)
    with pytest.raises(ValueError, match="Invalid runtime retry"):
        api.retry(lease, code="secret path / token")


@pytest.mark.parametrize("action", ["cancel", "delete"])
def test_revocation_rollback_retains_original_lease(store, action):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    with pytest.raises(RuntimeError):
        with store._transaction():
            getattr(store, action)(event.job_id)
            assert api.status(event.job_id)["state"] == "REVOKED"
            raise RuntimeError("abort")
    api.checkpoint(lease)
    assert api.status(event.job_id)["fence"] == lease.fence
    assert store.get(event.job_id).state == "QUEUED"


@pytest.mark.parametrize("action", ["cancel", "delete"])
def test_concurrent_result_and_revocation_are_serialized_across_connections(store, action):
    api, event = PostgresExecution(store), ready(store)
    lease = api.acquire(event.message)
    payload = report_input(store, event.job_id)
    barrier = Barrier(2)

    def mutate(operation):
        other = sibling(store)
        try:
            barrier.wait(timeout=10)
            if operation == "report":
                try:
                    PostgresExecution(other).fenced_store(lease).save(*payload)
                    return "published"
                except LeaseLost:
                    return "revoked"
            try:
                getattr(other, action)(event.job_id)
                return action
            except ValueError:
                return "already-terminal"
        finally:
            other.close()

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(mutate, ["report", action]))
    if action == "delete":
        assert results[1] == "delete" and store.is_tombstoned(event.job_id)
        with pytest.raises(KeyError):
            store.report(event.job_id)
    elif results[1] == "cancel":
        assert results[0] == "revoked" and store.get(event.job_id).state == "CANCELLED"
        with pytest.raises(ValueError, match="not available"):
            store.report(event.job_id)
    else:
        assert results == ["published", "already-terminal"]
        assert store.report(event.job_id).job.state == "SUCCEEDED"


@pytest.mark.parametrize(
    "values",
    [
        {"attempt": 4},
        {"fence": -1},
        {"state": "RUNNING"},
        {"state": "SUCCEEDED"},
        {"last_error_code": "secret"},
    ],
)
def test_database_constraints_reject_invalid_execution_ledger_records(store, values):
    event = ready(store)
    with (
        pytest.raises(ValueError, match="PostgreSQL storage rejected"),
        store._transaction() as conn,
    ):
        conn.execute(
            executions.update().where(executions.c.job_id == event.job_id).values(**values)
        )
    assert PostgresExecution(store).status(event.job_id)["state"] == "READY"
