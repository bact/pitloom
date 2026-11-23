# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Saying an ID registry save: a failure is the line of what stopped it,
an ``ERROR`` for ``loom id`` and its coded ``WARNING`` twin for a run whose
SBOM is written (:func:`say_save_failure`); a registry with no file
(``registry-file-missing``); the save's summaries.

See also: tests/cli/test_cli_id_failed_save.py (every CLI surface),
tests/id_registry/test_persist_registry_save.py (the library).
"""

from __future__ import annotations

import errno
import logging
import os
from pathlib import PureWindowsPath

import pytest

from pitloom.core.internal_error import InternalError
from pitloom.logging_config import CODE_ATTR
from pitloom.messages import (
    SUMMARIES,
    CodedValueError,
    Message,
    trusted_message,
)
from pitloom.messages.files import (
    FILE_UNREADABLE,
    FILE_UNREADABLE_NOT_UTF8,
    FILE_UNWRITABLE,
    OVER_CAP,
    REGISTRY_USE,
    SOURCE_LINE,
    Cap,
    file_unreadable_error,
)
from pitloom.messages.id_registry import (
    ADDED_IDS,
    CONFIG_HINT_ADD,
    CONFIG_HINT_CHANGE,
    ENTITY_STORED_AS,
    HOLDS_IDS,
    MINT_LINE,
    NO_RELATIVE_ROOT_LINE,
    REGISTRY_FILE_MISSING,
    REGISTRY_MALFORMED,
    REGISTRY_UNKNOWN_KEY,
    REGISTRY_UNUSABLE,
    REGISTRY_WRONG_FORMAT,
    STALE_UPDATED,
    UNKNOWN_TOP_KEY_LINE,
    say_save_failure,
    warn_no_registry_file,
)
from pitloom.messages.targets import (
    INPUT_NOT_FILE_LINE,
    INPUT_NOT_FOUND,
    SBOM_GRAPH_NOT_LIST_LINE,
    SBOM_INVALID,
    input_not_found,
)
from pitloom.messages.text import JSON_MALFORMED
from pitloom.messages.url_credentials import (
    CREDENTIALS_UNSAFE_REGISTRY,
    registry_file_refused_error,
)

pytestmark = pytest.mark.platform  # a Windows path through the file writer

_LOG = logging.getLogger("pitloom.test_registry_save")
_FILE = "./x/../ids.json"

#: One coded error each save can meet, with the entry it says.
_CODED = {
    "unusable": (
        CodedValueError(
            REGISTRY_UNUSABLE,
            line=NO_RELATIVE_ROOT_LINE,
            file=_FILE,
            path="/p",
            failure=ValueError("path is on mount 'C:', start on mount 'D:'"),
        ),
        REGISTRY_UNUSABLE,
    ),
    "malformed": (
        CodedValueError(
            REGISTRY_MALFORMED, line=MINT_LINE, file=_FILE, name="File", namespace="u"
        ),
        REGISTRY_MALFORMED,
    ),
    "unknown-key": (
        CodedValueError(
            REGISTRY_UNKNOWN_KEY, line=UNKNOWN_TOP_KEY_LINE, file=_FILE, name="'x'"
        ),
        REGISTRY_UNKNOWN_KEY,
    ),
    "wrong-format": (
        CodedValueError(REGISTRY_WRONG_FORMAT, file=_FILE, value="3"),
        REGISTRY_WRONG_FORMAT,
    ),
    "json": (
        CodedValueError(
            JSON_MALFORMED, file=_FILE, use=REGISTRY_USE, failure=ValueError("x")
        ),
        JSON_MALFORMED,
    ),
    "unreadable": (
        CodedValueError(
            FILE_UNREADABLE,
            file=_FILE,
            use=REGISTRY_USE,
            failure=OSError(errno.EACCES, "Permission denied"),
        ),
        FILE_UNREADABLE,
    ),
    "gone": (
        input_not_found("ID registry file", _FILE),
        INPUT_NOT_FOUND,
    ),
    "not-a-file": (
        CodedValueError(
            INPUT_NOT_FOUND,
            line=INPUT_NOT_FILE_LINE,
            input="ID registry file",
            path=_FILE,
        ),
        INPUT_NOT_FOUND,
    ),
    "not-utf8": (
        file_unreadable_error(
            UnicodeDecodeError("utf-8", b"\xff", 0, 1, "invalid start byte"),
            file=_FILE,
            use=REGISTRY_USE,
        ),
        FILE_UNREADABLE_NOT_UTF8,
    ),
    "credentials": (
        registry_file_refused_error(_FILE, "https://u:pw@h/m"),
        CREDENTIALS_UNSAFE_REGISTRY,
    ),
    "over-cap": (
        CodedValueError(
            OVER_CAP,
            line=SOURCE_LINE,
            file=_FILE,
            use=REGISTRY_USE,
            **Cap(1024, "byte", "JSON-document").reason_values(),
        ),
        OVER_CAP,
    ),
}


def _said(caplog: pytest.LogCaptureFixture) -> tuple[str, str, object]:
    (record,) = caplog.records
    return record.levelname, record.getMessage(), getattr(record, CODE_ATTR, None)


@pytest.mark.parametrize("fatal", [True, False], ids=["error", "warning"])
@pytest.mark.parametrize("kind", list(_CODED))
def test_a_coded_failure_says_its_own_line_at_the_level(
    caplog: pytest.LogCaptureFixture, kind: str, fatal: bool
) -> None:
    """The inner line alone, its code kept at either level (each has a
    ``WARNING`` twin): no wrapper, the file named once."""
    exc, entry = _CODED[kind]
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        say_save_failure(_LOG, exc, file="other.json", fatal=fatal)

    level, text, code = _said(caplog)
    assert (level, text, code) == (
        "ERROR" if fatal else "WARNING",
        str(exc),
        entry.code,
    )
    assert trusted_message(f"{level}: {text} [{code}]") is entry
    assert "other.json" not in text and "failed to save" not in text
    assert text.count("ID registry: ") <= 1


@pytest.mark.parametrize("fatal", [True, False], ids=["error", "warning"])
@pytest.mark.parametrize(
    ("file", "shown"),
    [
        (_FILE, _FILE),
        (PureWindowsPath(r"C:\p\ids.json"), r"C:\p\ids.json"),
        ("ids\n.json", "'ids\\n.json'"),
    ],
    ids=["typed", "windows", "newline"],
)
def test_a_refused_write_is_file_unwritable(
    caplog: pytest.LogCaptureFixture, fatal: bool, file: object, shown: str
) -> None:
    """The file as typed, escaped when it holds a control character; the
    system's own reason, never the temporary file it names."""
    exc = OSError(errno.EACCES, os.strerror(errno.EACCES), "/d/.ids.json.1f.tmp")
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        say_save_failure(_LOG, exc, file=file, fatal=fatal)  # type: ignore[arg-type]

    level, text, code = _said(caplog)
    assert (level, code) == ("ERROR" if fatal else "WARNING", "file-unwritable")
    assert text == (
        f"FILE={shown}: could not write for the ID registry; "
        f"{os.strerror(errno.EACCES)}"
    )
    assert trusted_message(f"{level}: {text} [{code}]") is FILE_UNWRITABLE


@pytest.mark.parametrize(
    "exc",
    [ValueError("No path given"), RuntimeError("x")],
    ids=["value-error", "other"],
)
def test_an_uncoded_failure_other_than_a_write_is_internal(
    caplog: pytest.LogCaptureFixture, exc: Exception
) -> None:
    """No input of a user reaches a save with one: a programming error,
    said nowhere."""
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        with pytest.raises(InternalError) as caught:
            say_save_failure(_LOG, exc, file=_FILE, fatal=False)
    assert caught.value.__cause__ is exc
    assert not caplog.records


def test_a_coded_failure_with_no_line_at_the_level_is_internal(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """A coded error whose entry has no ``WARNING`` twin is never said
    uncoded: the gap fails loudly."""
    exc = CodedValueError(SBOM_INVALID, line=SBOM_GRAPH_NOT_LIST_LINE, file=_FILE)
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        say_save_failure(_LOG, exc, file=_FILE, fatal=True)
        with pytest.raises(InternalError, match="sbom-invalid: no WARNING line"):
            say_save_failure(_LOG, exc, file=_FILE, fatal=False)
    assert [r.levelname for r in caplog.records] == ["ERROR"]


def test_a_registry_with_no_file_is_coded(caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        warn_no_registry_file(_LOG)
    assert _said(caplog) == (
        "WARNING",
        "ID registry: no file to save to; the ids this run added are not saved",
        "registry-file-missing",
    )
    assert REGISTRY_FILE_MISSING.actor == "caller"


def test_every_run_without_a_registry_file_says_it(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """The line is not once-per-process: a second run in one process (a
    long-lived library caller, a second ``loom.Run``) loses its ids too, and
    must say so."""
    with caplog.at_level(logging.INFO, logger=_LOG.name):
        warn_no_registry_file(_LOG)
        warn_no_registry_file(_LOG)
    assert [r.levelname for r in caplog.records] == ["WARNING", "WARNING"]


def test_the_save_summaries_are_catalogued() -> None:
    """Each a summary of the catalogue, so the ratchet leaves its call out."""
    saves = {
        HOLDS_IDS,
        ADDED_IDS,
        STALE_UPDATED,
        ENTITY_STORED_AS,
        CONFIG_HINT_ADD,
        CONFIG_HINT_CHANGE,
    }
    assert saves <= set(SUMMARIES)
    assert all(s.template.startswith("ID registry: ") for s in saves)


@pytest.mark.parametrize(
    "entry",
    [
        REGISTRY_MALFORMED,
        REGISTRY_UNKNOWN_KEY,
        REGISTRY_WRONG_FORMAT,
        REGISTRY_UNUSABLE,
    ],
    ids=lambda e: e.code,
)
def test_every_registry_error_line_has_its_warning_twin(entry: Message) -> None:
    errors = [ln.template for ln in entry.lines if ln.level == "ERROR"]
    warnings = [ln.template for ln in entry.lines if ln.level == "WARNING"]
    assert errors and errors == warnings


def test_the_version_line_gives_no_advice() -> None:
    """The advice is the entry's, by version: a newer file is never to be
    deleted."""
    (line, _) = REGISTRY_WRONG_FORMAT.lines
    assert line.template.endswith("(no migration support)")
    assert "delete" not in line.template


def test_no_did_text_says_the_save_line_is_uncoded() -> None:
    for entry in (REGISTRY_MALFORMED, REGISTRY_UNUSABLE, JSON_MALFORMED):
        assert "failed to save" not in entry.did
        assert "build hook" not in entry.did.partition("As a WARNING")[2]
