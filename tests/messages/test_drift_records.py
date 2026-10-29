# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard at run time: any log record carrying a ``pitloom_code`` has a
catalogued code, a level its entry is said at and a text one of its patterns
matches. ``tests/conftest.py`` applies :func:`tests._message_drift
.record_problem` to every record of every test; this file tests the check.

See also: tests/messages/test_drift_sources.py (the source says only what
the catalogue knows), tests/messages/test_drift_quotes.py (docs and skills).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.core.lfs_pointer import warn_pointers_not_read
from pitloom.logging_config import CODE_ATTR
from tests._message_drift import record_problem


def _record(
    level: int, msg: str, code: object, *args: object, name: str = "pitloom.x"
) -> logging.LogRecord:
    record = logging.LogRecord(name, level, __file__, 1, msg, args or None, None)
    if code is not None:
        setattr(record, CODE_ATTR, code)
    return record


@pytest.mark.parametrize(
    ("record", "fragment"),
    [
        (
            _record(
                logging.WARNING,
                "FILE=%s: Git LFS pointer, content not read; "
                "run 'git lfs pull' for the content",
                "lfs-pointer",
                "a\nb",
            ),
            None,
        ),
        (_record(logging.WARNING, "no code here", None), None),
        (_record(logging.WARNING, "any text", "git.too-large"), "uncatalogued"),
        (_record(logging.WARNING, "any text", 404), "uncatalogued"),
        (_record(logging.WARNING, "FILE=a: another text", "lfs-pointer"), "not the"),
        (
            _record(
                logging.INFO,
                "FILE=%s: Git LFS pointer shipped; the build did not pull LFS content",
                "lfs-pointer.shipped",
                "a",
            ),
            "not the",
        ),
        (
            _record(logging.WARNING, "odd", "lfs-pointer", name="pitloom.test_x"),
            None,
        ),
    ],
    ids=["valid", "no-code", "unknown", "not-a-str", "text", "level", "test-logger"],
)
def test_a_record_is_checked_against_its_entry(
    record: logging.LogRecord, fragment: str | None
) -> None:
    problem = record_problem(record)
    if fragment is None:
        assert problem is None
    else:
        assert problem is not None and fragment in problem


def test_the_records_of_a_real_emitter_pass_the_check(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A run's own warning, not a hand-made record."""
    with caplog.at_level(logging.WARNING, logger="pitloom"):
        warn_pointers_not_read(["m/a.bin", "m/b.bin"])
        warn_pointers_not_read(["w.bin"], archive=True)
    coded = [r for r in caplog.records if hasattr(r, CODE_ATTR)]
    assert [getattr(r, CODE_ATTR) for r in coded] == [
        "lfs-pointer",
        "lfs-pointer.shipped",
    ]
    assert [record_problem(r) for r in coded] == [None, None]


def test_the_check_is_hooked_on_every_record() -> None:
    """The autouse fixture of ``tests/conftest.py`` wraps ``Logger.handle``
    for the length of a test."""
    assert logging.Logger.handle.__name__ == "watching"
