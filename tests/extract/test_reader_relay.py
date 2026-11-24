# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A reader's record said again by the scanner: the file it names, and the
code it keeps.

See also: :mod:`tests.extract.scanner.test_scanner_reader_logs` (through a
scan).
"""

from __future__ import annotations

import logging

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.extract._reader_relay import named_stably, relay
from pitloom.logging_config import CODE_ATTR
from pitloom.messages.datasets import DATASET_METADATA_PREFIX

_LOG = logging.getLogger("pitloom.test_reader_relay")
_SOURCE = f"{DATASET_METADATA_PREFIX}SOURCE="


def _record(level: int, text: str, code: str | None) -> logging.LogRecord:
    record = logging.LogRecord("x", level, "x", 1, text, None, None)
    if code is not None:
        setattr(record, CODE_ATTR, code)
    return record


@pytest.mark.parametrize(
    ("text", "renamed"),
    [
        ("FILE=0.gguf: x", "FILE=demo/m.gguf: x"),
        (f"{_SOURCE}'0.gguf' FIELD=f: x", f"{_SOURCE}'demo/m.gguf' FIELD=f: x"),
        ("FORMAT=gguf FILE=0.gguf: x", "FORMAT=gguf FILE=demo/m.gguf: x"),
        ("FILE=0.gguf", "FILE=demo/m.gguf"),
        ("FILE=10.gguf: x", "FILE=10.gguf: x"),  # another name
        ("XFILE=0.gguf: x", "XFILE=0.gguf: x"),  # another key
        ("FILE=0.gguf.bak: x", "FILE=0.gguf.bak: x"),  # a longer value
        ("tensor '0.gguf' read", "tensor '0.gguf' read"),  # no key
        # A model's own text holding the key, after a space: not the subject.
        ("FILE=m: key a FILE=0.gguf b", "FILE=m: key a FILE=0.gguf b"),
        ("FILE=0.gguf: a FILE=0.gguf b", "FILE=demo/m.gguf: a FILE=0.gguf b"),
        ("a: SOURCE='0.gguf' FIELD=f: x", "a: SOURCE='0.gguf' FIELD=f: x"),
        ("FORMAT=a b FILE=0.gguf: x", "FORMAT=a b FILE=0.gguf: x"),
    ],
    ids=[
        "file",
        "source",
        "after-format",
        "at-end",
        "name",
        "key",
        "longer",
        "unkeyed",
        "in-free-text",
        "subject-only",
        "source-unprefixed",
        "format-not-a-word",
    ],
)
def test_only_a_whole_file_value_is_renamed(text: str, renamed: str) -> None:
    assert named_stably(text, "0.gguf", "demo/m.gguf") == renamed


def test_a_hostile_stable_path_is_written_by_the_field_s_writer() -> None:
    """Escaped as the line's own writer escapes it: one line, a quote in a
    quoted value escaped."""
    out = named_stably(f"{_SOURCE}'0.gguf' FIELD=f: x", "0.gguf", "d/'\n.gguf")
    assert "\n" not in out and "SOURCE='d/'" not in out
    assert "0.gguf" not in out  # renamed


_FRAME = "FORMAT=gguf FILE=demo/m.gguf: "


@pytest.mark.parametrize(
    ("text", "code", "framed"),
    [
        ("FILE=m: lone surrogates written as \\uXXXX", "text-malformed", True),
        (
            "FILE=m: Git LFS pointer, content not read; run 'git lfs pull' "
            "for the content",
            "lfs-pointer",
            False,
        ),
    ],
    ids=["framed", "unframed"],
)
def test_a_coded_record_keeps_its_code(
    caplog: pytest.LogCaptureFixture, text: str, code: str, framed: bool
) -> None:
    """Framed when the frame allows the code, else unframed: never uncoded."""
    with caplog.at_level(logging.WARNING, logger=_LOG.name):
        relay(_LOG, _record(logging.WARNING, text, code), text, _FRAME)
    (record,) = caplog.records
    assert getattr(record, CODE_ATTR) == code
    assert record.getMessage() == (_FRAME + text if framed else text)


def test_an_uncoded_or_debug_record_is_said_uncoded(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        relay(_LOG, _record(logging.WARNING, "plain", None), "plain", "F: ")
        relay(_LOG, _record(logging.DEBUG, "d", "lfs-pointer"), "d", "F: ")
    assert [(r.getMessage(), getattr(r, CODE_ATTR, None)) for r in caplog.records] == [
        ("F: plain", None),
        ("d", None),
    ]


@pytest.mark.parametrize("code", ["lfs-pointer", "no-such-code"])
def test_a_coded_record_that_is_not_its_line_is_an_internal_error(
    caplog: pytest.LogCaptureFixture, code: str
) -> None:
    """Never said with its code dropped."""
    with pytest.raises(InternalError, match=code):
        relay(_LOG, _record(logging.WARNING, "not its line", code), "x", "F: ")
    assert not caplog.records


def test_a_coded_record_its_rewriting_broke_is_said_as_read_with_its_code(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Unframed, the record's own text, never uncoded nor an error."""
    text = "FILE=m: lone surrogates written as \\uXXXX"
    broken = "\x1b" + text  # what a rewriting may leave: not the line
    with caplog.at_level(logging.DEBUG, logger=_LOG.name):
        relay(_LOG, _record(logging.WARNING, text, "text-malformed"), broken, "x ")
    debug, said = caplog.records
    assert "not renamed" in debug.getMessage()
    assert (said.getMessage(), getattr(said, CODE_ATTR)) == (text, "text-malformed")
