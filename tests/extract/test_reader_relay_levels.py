# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The level boundaries of a reader's record said again: the frame from
``WARNING`` up only, the code from ``INFO`` up, a record's own text
escaped, and the note that a line was said as read at ``DEBUG`` only.

See also: :mod:`tests.extract.test_reader_relay`.
"""

# pylint: disable=missing-function-docstring

from __future__ import annotations

import logging

import pytest

from pitloom.extract._reader_relay import relay
from pitloom.logging_config import CODE_ATTR

_LOG = logging.getLogger("pitloom.test_reader_relay_levels")
_INFO_TEXT = "disabled; skipping SBOM generation"  # hook-no-effect, INFO
_MALFORMED = "FILE=m: lone surrogates written as \\uXXXX"  # text-malformed


def _record(level: int, text: str, code: str | None) -> logging.LogRecord:
    record = logging.LogRecord("x", level, "x", 1, text, None, None)
    if code is not None:
        setattr(record, CODE_ATTR, code)
    return record


def test_a_coded_info_record_is_not_framed(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The frame is for ``WARNING`` and up, even where the catalogue would
    allow it at ``INFO``."""
    frame = "Pitloom build hook: "  # allowed at INFO for hook-no-effect
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        relay(
            _LOG, _record(logging.INFO, _INFO_TEXT, "hook-no-effect"), _INFO_TEXT, frame
        )
    (record,) = caplog.records
    assert record.getMessage() == _INFO_TEXT


@pytest.mark.parametrize(
    ("level", "text", "code"),
    [
        (logging.INFO, _INFO_TEXT, "hook-no-effect"),
        (logging.WARNING, _MALFORMED, "text-malformed"),
    ],
    ids=["info", "warning"],
)
def test_a_coded_record_from_info_up_keeps_its_code(
    caplog: pytest.LogCaptureFixture, level: int, text: str, code: str
) -> None:
    """Both ends of the range: exactly ``INFO``, and above it."""
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        relay(_LOG, _record(level, text, code), text, "")
    (record,) = caplog.records
    assert record.levelno == level
    assert getattr(record, CODE_ATTR) == code


def test_a_record_said_as_read_is_one_escaped_line(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Its own text, a newline and an escape in it: written as escapes."""
    text = "FILE=m\n\x1b: lone surrogates written as \\uXXXX"
    broken = "\x1b" + text  # not the line: the as-read fallback is reached
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        relay(_LOG, _record(logging.WARNING, text, "text-malformed"), broken, "x ")
    (said,) = caplog.records
    assert getattr(said, CODE_ATTR) == "text-malformed"
    assert said.getMessage() == "FILE=m\\n\\x1b: lone surrogates written as \\uXXXX"


@pytest.mark.parametrize(
    ("capture", "noted"), [(logging.INFO, False), (logging.DEBUG, True)]
)
def test_the_as_read_note_is_for_debug_only(
    caplog: pytest.LogCaptureFixture, capture: int, noted: bool
) -> None:
    broken = "\x1b" + _MALFORMED
    with caplog.at_level(capture, logger=_LOG.name):
        relay(
            _LOG, _record(logging.WARNING, _MALFORMED, "text-malformed"), broken, "x "
        )
    notes = [r for r in caplog.records if "not renamed" in r.getMessage()]
    assert [r.levelno for r in notes] == ([logging.DEBUG] if noted else [])
    assert [r.getMessage() for r in caplog.records if r.levelno > logging.DEBUG] == [
        _MALFORMED
    ]
