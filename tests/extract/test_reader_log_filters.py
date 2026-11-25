# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A record of a thread that is not capturing goes on to the parent logger
as that logger's own ``handle`` takes it: its filters apply.

See also: :mod:`tests.extract.test_reader_log`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging
import threading

import pytest

from pitloom.extract._reader_log import capture_reader_logs

_NAME = "pitloom.extract.ai_model.fake"
_PARENT = "pitloom.extract"


# pylint: disable-next=too-few-public-methods
class _Refuse(logging.Filter):
    """A filter on the parent that says no, and counts how often it was asked."""

    def __init__(self) -> None:
        super().__init__()
        self.asked: list[str] = []

    def filter(self, record: logging.LogRecord) -> bool:
        self.asked.append(record.getMessage())
        return False


class _Collect(logging.Handler):
    def __init__(self) -> None:
        super().__init__(level=logging.NOTSET)
        self.said: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.said.append(record.getMessage())


def _log_while_another_thread_captures() -> None:
    """Log once from this thread, a capture open in another one."""
    entered, leave = threading.Event(), threading.Event()

    def capturing() -> None:
        with capture_reader_logs():
            entered.set()
            leave.wait(10)

    worker = threading.Thread(target=capturing, daemon=True)
    worker.start()
    try:
        assert entered.wait(10)
        logging.getLogger(_NAME).warning("from the main thread")
    finally:
        leave.set()
        worker.join(10)


@pytest.mark.uncoded_output(r"^WARNING: from the main thread$")
@pytest.mark.parametrize("refuse", [True, False], ids=["filtered", "passed"])
def test_the_parent_s_filters_apply_to_a_passed_on_record(refuse: bool) -> None:
    parent = logging.getLogger(_PARENT)
    handler, flt = _Collect(), _Refuse()
    parent.addHandler(handler)
    if refuse:
        parent.addFilter(flt)
    try:
        _log_while_another_thread_captures()
    finally:
        parent.removeHandler(handler)
        parent.removeFilter(flt)
    assert flt.asked == (["from the main thread"] if refuse else [])
    assert handler.said == ([] if refuse else ["from the main thread"])
