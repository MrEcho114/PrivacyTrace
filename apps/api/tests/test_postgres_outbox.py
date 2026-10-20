"""Real PostgreSQL outbox transactions, isolation and delivery ownership.

Protocol-only cases run without a database. Database cases require disposable
*_test URLs and separate runtime/migration roles, as the existing storage suite.
"""

import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
import sqlalchemy as sa
from test_postgres_storage import migration, queued
from test_postgres_storage import postgres_urls as postgres_urls
from test_postgres_storage import store as store

from privacytrace.postgres_outbox import MAX_ATTEMPTS, PostgresOutbox, decode_message
from privacytrace.postgres_schema import outbox
from privacytrace.postgres_store import PostgresJobStore


@pytest.fixture
def events(store):
    return PostgresOutbox(store)


def sibling(store):
    return PostgresJobStore(store.engine.url, store.instance_id, store.root.parent.parent)


def expire(store, event_id, field="claimed_until"):
    assert field in {"claimed_until", "available_at"}
    with store._transaction() as conn:
        conn.execute(
            outbox.update()
            .where(
                outbox.c.instance_id == store.instance_id,
                outbox.c.event_id == event_id,
            )
            .values({field: sa.func.clock_timestamp() - sa.text("INTERVAL '1 second'")})
        )


def event_count(store):
    with store._transaction() as conn:
        return conn.scalar(
            sa.select(sa.func.count())
            .select_from(outbox)
            .where(
                outbox.c.instance_id == store.instance_id,
            )
        )


def test_job_and_event_commit_together_and_replay_is_stable(store, events):
    job = queued()
    event = events.register(job, "a" * 64)
    assert store.get(job.id) == job
    assert event.state == "PENDING" and event.attempts == 0
    assert events.enqueue(job.id).event_id == event.event_id
    other = sibling(store)
    try:
        restored = PostgresOutbox(other).get(str(event.event_id))
        assert restored == event
        assert other.get_token_digest(job.id) == "a" * 64
    finally:
        other.close()
    assert set(event.message) == {"version", "event_type", "instance_id", "job_id", "event_id"}
    assert decode_message(json.dumps(event.message)) == event.message
    assert "a" * 64 not in json.dumps(event.message)
    assert event_count(store) == 1


def test_existing_registration_does_not_implicitly_enqueue(store):
    store.create_if_absent(queued())
    assert event_count(store) == 0


def test_outer_transaction_hides_both_records_until_commit(store, events):
    job = queued()
    with store._transaction():
        event = events.register(job)
        with store.engine.begin() as independent:
            independent.execute(
                sa.text("SELECT set_config('privacytrace.instance_id', :instance, true)"),
                {"instance": store.instance_id},
            )
            assert independent.scalar(sa.text("SELECT count(*) FROM privacytrace.jobs")) == 0
            assert independent.scalar(sa.select(sa.func.count()).select_from(outbox)) == 0
    assert events.get(str(event.event_id)).state == "PENDING"


def test_outer_rollback_removes_job_event_and_registration_audit(store, events):
    job = queued()
    with pytest.raises(RuntimeError, match="abort"):
        with store._transaction():
            events.register(job)
            raise RuntimeError("abort")
    with pytest.raises(KeyError):
        store.get(job.id)
    assert event_count(store) == 0
    assert events.claim() == []
    with store._transaction() as conn:
        assert conn.scalar(sa.text("SELECT count(*) FROM privacytrace.audit_events")) == 0


def test_delivery_cannot_escape_an_uncommitted_outer_transaction(store, events):
    with pytest.raises(RuntimeError, match="abort"):
        with store._transaction():
            events.register(queued())
            with pytest.raises(ValueError, match="standalone transaction"):
                events.claim()
            raise RuntimeError("abort")
    assert event_count(store) == 0
    assert events.claim() == []


@pytest.mark.parametrize("operation", ["acknowledge", "fail"])
def test_delivery_settlement_requires_its_own_commit(store, events, operation):
    events.register(queued())
    event = events.claim()[0]
    kwargs = {"code": "BROKER_UNAVAILABLE"} if operation == "fail" else {}
    with store._transaction():
        with pytest.raises(ValueError, match="standalone transaction"):
            getattr(events, operation)(str(event.event_id), str(event.claim_token), **kwargs)
    assert events.get(str(event.event_id)).state == "CLAIMED"


def test_skip_locked_claim_does_not_wait_for_an_independently_locked_event(store, events):
    locked = events.register(queued())
    ready = events.register(queued())
    with store.engine.begin() as independent:
        independent.execute(
            sa.text("SELECT set_config('privacytrace.instance_id', :i, true)"),
            {"i": store.instance_id},
        )
        independent.execute(
            sa.select(outbox).where(outbox.c.event_id == locked.event_id).with_for_update()
        ).all()
        claimed = events.claim()
        assert [e.event_id for e in claimed] == [ready.event_id]
    assert [e.event_id for e in events.claim()] == [locked.event_id]


def test_real_server_commit_rejection_rolls_back_job_and_consumable_event(
    store,
    events,
    postgres_urls,
):
    # The server, not an exception spy, rejects COMMIT via a deferred FK.
    parent, child = "pt80_parent_" + uuid4().hex, "pt80_child_" + uuid4().hex
    owner = sa.create_engine(postgres_urls[1], hide_parameters=True)
    role = store.engine.url.username
    with owner.begin() as conn:
        conn.execute(sa.text(f"CREATE TABLE privacytrace.{parent} (id int PRIMARY KEY)"))
        conn.execute(
            sa.text(
                f"CREATE TABLE privacytrace.{child} (id int REFERENCES privacytrace.{parent} "
                "DEFERRABLE INITIALLY DEFERRED)"
            )
        )
        conn.execute(sa.text(f'GRANT INSERT ON privacytrace.{child} TO "{role}"'))
    job = queued()
    try:
        with pytest.raises(ValueError, match="PostgreSQL storage rejected") as rejected:
            with store._transaction() as conn:
                events.register(job)
                conn.execute(sa.text(f"INSERT INTO privacytrace.{child} VALUES (1)"))
        assert rejected.value.__context__.orig.sqlstate == "23503"
        with pytest.raises(KeyError):
            store.get(job.id)
        assert event_count(store) == 0
        assert events.claim() == []
    finally:
        with owner.begin() as conn:
            conn.execute(sa.text(f"DROP TABLE privacytrace.{child}"))
            conn.execute(sa.text(f"DROP TABLE privacytrace.{parent}"))
        owner.dispose()


def test_concurrent_registration_and_duplicate_enqueue_do_not_duplicate(store):
    job, barrier = queued(), Barrier(2)

    def register(_):
        other = sibling(store)
        try:
            barrier.wait(timeout=10)
            try:
                return PostgresOutbox(other).register(job).event_id
            except ValueError:
                return None
        finally:
            other.close()

    with ThreadPoolExecutor(2) as pool:
        created = list(pool.map(register, range(2)))
    assert sum(e is not None for e in created) == 1

    def enqueue(_):
        other = sibling(store)
        try:
            return PostgresOutbox(other).enqueue(job.id).event_id
        finally:
            other.close()

    with ThreadPoolExecutor(4) as pool:
        assert len(set(pool.map(enqueue, range(8)))) == 1
    assert event_count(store) == 1


def test_concurrent_connections_claim_each_event_once(store, events):
    for _ in range(12):
        events.register(queued())
    barrier = Barrier(4)

    def claim(_):
        other = sibling(store)
        try:
            barrier.wait(timeout=10)
            return PostgresOutbox(other).claim(limit=3)
        finally:
            other.close()

    with ThreadPoolExecutor(4) as pool:
        claimed = [event for batch in pool.map(claim, range(4)) for event in batch]
    assert len(claimed) == len({e.event_id for e in claimed}) == 12
    assert all(e.attempts == 1 and e.claim_token for e in claimed)
    assert events.claim() == []


def test_expired_claim_recovers_and_old_owner_cannot_ack_or_fail(store, events):
    event = events.register(queued())
    old = events.claim()[0]
    expire(store, event.event_id)
    assert not events.acknowledge(str(old.event_id), str(old.claim_token))
    other = sibling(store)
    try:
        current = PostgresOutbox(other).claim()[0]
    finally:
        other.close()
    assert current.event_id == old.event_id and current.claim_token != old.claim_token
    assert current.attempts == 2
    assert not events.acknowledge(str(old.event_id), str(old.claim_token))
    assert not events.fail(str(old.event_id), str(old.claim_token), code="BROKER_UNAVAILABLE")
    assert events.acknowledge(str(current.event_id), str(current.claim_token))
    assert not events.acknowledge(str(current.event_id), str(current.claim_token))
    assert events.get(str(event.event_id)).state == "DELIVERED"


def test_failure_backoff_and_bounded_delivery_attempts(store, events):
    event = events.register(queued())
    for attempt in range(1, MAX_ATTEMPTS + 1):
        delivery = events.claim()[0]
        assert delivery.attempts == attempt
        assert events.fail(
            str(delivery.event_id),
            str(delivery.claim_token),
            code="BROKER_UNAVAILABLE",
            retry_delay_seconds=60,
        )
        assert events.claim() == []
        if attempt < MAX_ATTEMPTS:
            assert events.get(str(event.event_id)).state == "PENDING"
            expire(store, event.event_id, "available_at")
    failed = events.get(str(event.event_id))
    assert failed.state == "FAILED" and failed.last_error_code == "BROKER_UNAVAILABLE"
    assert events.enqueue(event.job_id).event_id == event.event_id
    assert events.claim() == []  # Re-enqueue cannot reset the retry budget.


def test_last_delivery_crash_exhausts_budget_without_another_claim(store, events):
    event = events.register(queued())
    for _ in range(MAX_ATTEMPTS):
        assert len(events.claim()) == 1
        expire(store, event.event_id)
    assert events.claim() == []
    assert events.get(str(event.event_id)).state == "FAILED"
    assert events.get(str(event.event_id)).last_error_code == "DELIVERY_TIMEOUT"


@pytest.mark.parametrize("action", ["cancel", "delete"])
@pytest.mark.parametrize("claimed", [False, True])
def test_cancel_delete_and_tombstone_cannot_be_bypassed(store, events, action, claimed):
    event = events.register(queued())
    delivery = events.claim()[0] if claimed else None
    getattr(store, action)(event.job_id)
    if delivery:
        assert not events.acknowledge(str(delivery.event_id), str(delivery.claim_token))
        assert not events.fail(
            str(delivery.event_id), str(delivery.claim_token), code="DELIVERY_REJECTED"
        )
    assert events.claim() == []
    assert events.get(str(event.event_id)).state == "DISCARDED"
    with pytest.raises((KeyError, ValueError)):
        events.enqueue(event.job_id)
    assert (
        store.is_tombstoned(event.job_id)
        if action == "delete"
        else (store.get(event.job_id).state == "CANCELLED")
    )


def test_cross_instance_same_job_identifier_is_isolated(store, events, tmp_path):
    event = events.register(queued("same-job"))
    other = PostgresJobStore(store.engine.url, str(uuid4()), tmp_path / "other")
    try:
        isolated = PostgresOutbox(other)
        assert isolated.claim() == []
        with pytest.raises(KeyError):
            isolated.get(str(event.event_id))
        other_event = isolated.register(queued("same-job"))
        assert other_event.event_id != event.event_id
        assert len(isolated.claim()) == 1
        with other._transaction() as conn:
            assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 1
            with pytest.raises(sa.exc.DBAPIError) as rejected:
                conn.execute(
                    outbox.insert().values(
                        instance_id=store.instance_id,
                        event_id=uuid4(),
                        job_id=event.job_id,
                        event_type=event.event_type,
                        version=1,
                        state="PENDING",
                        attempts=0,
                        available_at=sa.func.now(),
                        created_at=sa.func.now(),
                    )
                )
            assert rejected.value.orig.sqlstate == "42501"
    finally:
        other.close()


def test_runtime_cannot_bypass_rls_or_remove_history(store, events):
    events.register(queued())
    with store.engine.begin() as conn:
        assert conn.scalar(sa.select(sa.func.count()).select_from(outbox)) == 0
    for operation in [
        "DELETE FROM privacytrace.outbox_events",
        "TRUNCATE privacytrace.outbox_events",
        "CREATE TABLE privacytrace.forbidden_outbox_test (id int)",
    ]:
        with store.engine.begin() as conn, pytest.raises(sa.exc.DBAPIError) as rejected:
            conn.execute(sa.text(operation))
        assert rejected.value.orig.sqlstate == "42501"


def test_invalid_failure_details_and_foreign_claim_do_not_change_delivery(events):
    events.register(queued())
    event = events.claim()[0]
    with pytest.raises(ValueError, match="^Invalid delivery failure code$"):
        events.fail(str(event.event_id), str(event.claim_token), code="secret/password/path")
    with pytest.raises(ValueError, match="permitted range"):
        events.fail(
            str(event.event_id),
            str(event.claim_token),
            code="BROKER_UNAVAILABLE",
            retry_delay_seconds=3601,
        )
    assert not events.acknowledge(str(event.event_id), str(uuid4()))
    assert events.get(str(event.event_id)) == event


def test_outbox_force_rls_is_enabled(store):
    with store.engine.begin() as conn:
        assert conn.execute(
            sa.text(
                "SELECT relrowsecurity, relforcerowsecurity FROM pg_class "
                "WHERE oid = 'privacytrace.outbox_events'::regclass"
            )
        ).one() == (True, True)


def test_incremental_migration_retains_existing_jobs_and_has_no_drift(store, events, postgres_urls):
    event = events.register(queued(), "a" * 64)
    migration(postgres_urls[1], "check")
    migration(postgres_urls[1], "downgrade", "0080_01")
    try:
        with store.engine.begin() as conn:
            conn.execute(
                sa.text("SELECT set_config('privacytrace.instance_id', :i, true)"),
                {"i": store.instance_id},
            )
            assert conn.scalar(sa.text("SELECT count(*) FROM privacytrace.jobs")) == 1
        with pytest.raises(ValueError, match="schema version"):
            sibling(store)
    finally:
        migration(postgres_urls[1])
    assert store.get_token_digest(event.job_id) == "a" * 64
    assert store.get(event.job_id).state == "QUEUED"
    migration(postgres_urls[1], "check")


def test_independent_process_reads_committed_envelope(store, events):
    event = events.register(queued())
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import json, os
from pathlib import Path
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.postgres_outbox import PostgresOutbox
store = PostgresJobStore(os.environ['PRIVACYTRACE_TEST_DATABASE_URL'],
                        os.environ['PT_INSTANCE'], Path(os.environ['PT_ROOT']))
try:
    print(json.dumps(PostgresOutbox(store).get(os.environ['PT_EVENT']).message))
finally:
    store.close()
""",
        ],
        env={
            **os.environ,
            "PT_INSTANCE": store.instance_id,
            "PT_ROOT": str(store.root.parent.parent),
            "PT_EVENT": str(event.event_id),
        },
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=True,
    )
    assert json.loads(child.stdout) == event.message


def test_claiming_process_crash_recovers_after_real_visibility_timeout(store, events):
    event = events.register(queued())
    child = subprocess.run(
        [
            sys.executable,
            "-B",
            "-c",
            """
import os
from pathlib import Path
from privacytrace.postgres_store import PostgresJobStore
from privacytrace.postgres_outbox import PostgresOutbox
store = PostgresJobStore(os.environ['PRIVACYTRACE_TEST_DATABASE_URL'],
                        os.environ['PT_INSTANCE'], Path(os.environ['PT_ROOT']))
assert len(PostgresOutbox(store).claim(limit=1, visibility_seconds=1)) == 1
os._exit(17)  # Abrupt exit without settlement or closing the connection pool.
""",
        ],
        env={
            **os.environ,
            "PT_INSTANCE": store.instance_id,
            "PT_ROOT": str(store.root.parent.parent),
        },
        capture_output=True,
        timeout=30,
    )
    assert child.returncode == 17
    abandoned = events.get(str(event.event_id))
    with store._transaction() as conn:
        now = conn.scalar(sa.select(sa.func.clock_timestamp()))
    time.sleep(max(0, (abandoned.claimed_until - now).total_seconds()) + 0.02)
    other = sibling(store)
    try:
        recovered = PostgresOutbox(other).claim()[0]
        assert recovered.event_id == event.event_id
        assert recovered.attempts == 2 and recovered.claim_token != abandoned.claim_token
        assert not events.acknowledge(str(event.event_id), str(abandoned.claim_token))
        assert PostgresOutbox(other).acknowledge(str(event.event_id), str(recovered.claim_token))
    finally:
        other.close()


@pytest.mark.parametrize(
    "change",
    [
        {"version": True},
        {"version": 2},
        {"event_type": "os.system"},
        {"job_id": "../../private"},
        {"instance_id": str(uuid4()).upper()},
        {"event_id": "not-a-uuid"},
        {"apk": "secret-apk"},
        {"token": "secret-token"},
        {"path": "/private/input.apk"},
        {"command": "arbitrary command"},
    ],
)
def test_message_rejects_unapproved_fields_versions_and_execution_input(change):
    value = {
        "version": 1,
        "event_type": "privacytrace.job.ready",
        "job_id": "safe-job",
        "instance_id": str(uuid4()),
        "event_id": str(uuid4()),
    }
    value.update(change)
    with pytest.raises(ValueError, match="^Invalid outbox message$"):
        decode_message(value)


def test_message_rejects_duplicate_json_keys_and_oversize_input():
    for value in ['{"version":1,"version":1}', b"x" * 1025, b"\xff", "[]"]:
        with pytest.raises(ValueError, match="^Invalid outbox message$"):
            decode_message(value)


@pytest.mark.parametrize(
    "options",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"visibility_seconds": 0},
        {"visibility_seconds": 301},
        {"visibility_seconds": "30"},
    ],
)
def test_claim_parameters_are_bounded_before_database_access(options):
    with pytest.raises(ValueError, match="permitted range"):
        PostgresOutbox(None).claim(**options)
