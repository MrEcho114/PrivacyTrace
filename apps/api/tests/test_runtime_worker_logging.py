"""Log-format contract for the fixed runtime diagnostic codes (#179).

Celery is an optional runtime extra and the authoritative local check installs
only the worker extra, so this module imports nothing but the plain format
strings. The contract therefore runs everywhere, including CI, while the
binding of those strings to ``app.conf`` stays covered in
``test_runtime_worker.py`` (which skips without celery).
"""

import logging

import pytest

from privacytrace.runtime_worker import (
    _DIAGNOSTIC_CODES,
    WORKER_LOG_FORMAT,
    WORKER_TASK_LOG_FORMAT,
)

FORMATS = [
    (WORKER_TASK_LOG_FORMAT, "[privacytrace runtime task WARNING]"),
    (WORKER_LOG_FORMAT, "[privacytrace runtime WARNING]"),
]


def _diagnostic_record(code):
    return logging.LogRecord(
        "privacytrace.runtime_worker",
        logging.WARNING,
        __file__,
        1,
        "privacytrace.worker.%s",
        (code,),
        None,
    )


@pytest.mark.parametrize(("template", "prefix"), FORMATS)
def test_log_format_keeps_the_message_body(template, prefix):
    # Without %(message)s the formatter renders the bracket prefix only and the
    # diagnostic code never reaches the container log.
    assert "%(message)s" in template
    assert logging.Formatter(template).format(_diagnostic_record("LEASE_LOST")) == (
        f"{prefix} privacytrace.worker.LEASE_LOST"
    )


@pytest.mark.parametrize("code", sorted(_DIAGNOSTIC_CODES))
@pytest.mark.parametrize(("template", "prefix"), FORMATS)
def test_every_fixed_diagnostic_code_survives_formatting(template, prefix, code):
    rendered = logging.Formatter(template).format(_diagnostic_record(code))
    assert rendered == f"{prefix} privacytrace.worker.{code}"
