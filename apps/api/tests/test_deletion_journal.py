"""Real filesystem durability boundaries; no database/OS power-loss claim."""

import os
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest

from privacytrace.deletion_journal import DeletionJournal


def test_concurrent_intents_are_authenticated_ordered_and_idempotent(tmp_path):
    instance, key = str(uuid4()), os.urandom(32)
    root = tmp_path / "journal"

    def append(index):
        return DeletionJournal(root, instance, key).append("JOB", "job-" + str(index))

    with ThreadPoolExecutor(4) as pool:
        entries = list(pool.map(append, [0, 1, 2, 3, 0, 2]))
    assert len({item["sequence"] for item in entries}) == 4
    journal = DeletionJournal(root, instance, key)
    assert [item["sequence"] for item in journal.entries()] == [1, 2, 3, 4]
    assert len(journal.entries()) == 4
    with pytest.raises(ValueError, match="integrity"):
        DeletionJournal(root, instance, os.urandom(32)).entries()


def test_torn_unacknowledged_tail_is_preserved_only_after_prefix_authentication(tmp_path):
    instance, key = str(uuid4()), os.urandom(32)
    journal = DeletionJournal(tmp_path / "journal", instance, key)
    journal.append("JOB", "kept")
    before = journal.path.read_bytes()
    tail = b'{"incomplete-unacknowledged-intent":'
    with journal.path.open("ab") as output:
        output.write(tail)
    with pytest.raises(ValueError):
        DeletionJournal(journal.root, instance, os.urandom(32)).entries()
    assert journal.path.read_bytes() == before + tail, "Wrong signing key must not repair files"
    assert len(journal.entries()) == 1
    assert journal.path.read_bytes() == before
    assert next(journal.root.glob("torn-*.partial")).read_bytes() == tail
    journal.append("DRAFT", uuid4().hex)
    assert len(journal.entries()) == 2


def test_complete_record_corruption_or_missing_chain_is_fail_closed(tmp_path):
    journal = DeletionJournal(tmp_path / "journal", str(uuid4()), os.urandom(32))
    journal.append("JOB", "first")
    journal.append("JOB", "second")
    before = journal.path.read_bytes()
    for corrupted in [before.replace(b'"first"', b'"other"'), before.splitlines(keepends=True)[1]]:
        journal.path.write_bytes(corrupted)
        with pytest.raises(ValueError, match="integrity"):
            journal.entries()
        assert journal.path.read_bytes() == corrupted
    journal.path.write_bytes(before)
    assert len(journal.entries()) == 2
