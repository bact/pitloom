# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Croissant file that does not read raises a ``ValueError`` carrying its
code, through both library entry points (``read_croissant`` and a loom
dataset's ``croissant=``): ``json-malformed`` (not JSON, not an object),
``over-cap`` (nesting), ``file-unreadable`` (a directory, a file the system
refuses), ``input-not-found`` (an absent file); a URL that cannot be fetched
carries ``download-network-failed``.

See also: tests/extract/test_extract_utils.py (the reader, its byte cap
and its URL branch).
"""

from __future__ import annotations

import contextlib
from collections.abc import Callable
from pathlib import Path
from unittest.mock import patch
from urllib.error import URLError

import pytest

from pitloom import loom
from pitloom.extract.dataset import read_croissant
from pitloom.messages import Message
from pitloom.messages.files import FILE_UNREADABLE, OVER_CAP
from pitloom.messages.network import DOWNLOAD_FAILED
from pitloom.messages.targets import INPUT_NOT_FOUND
from pitloom.messages.text import JSON_MALFORMED
from tests._message_drift import raised_as
from tests._unreadable import deny


def _read(name: str) -> None:
    read_croissant(name)


def _declare(name: str) -> None:
    with loom.run("out.json"):
        loom.add_dataset("t.txt", croissant=name)


_ENTRIES: dict[str, Callable[[str], None]] = {
    "read_croissant": _read,
    "loom-dataset": _declare,
}

_DOC = "for the Croissant document"
_CASES = {
    "not-json": (
        "c.json",
        b"{not json",
        JSON_MALFORMED,
        f"FILE=c.json: not valid JSON {_DOC}; Expecting property name",
    ),
    "a-list": (
        "c.json",
        b"[1, 2]",
        JSON_MALFORMED,
        f"FILE=c.json: not a JSON object {_DOC}",
    ),
    "too-deep": (
        "c.json",
        b"[" * 100,
        OVER_CAP,
        f"FILE=c.json: larger than the 64-level Croissant-nesting cap {_DOC}; not read",
    ),
    "directory": (
        "d",
        None,
        FILE_UNREADABLE,
        "FILE=d: could not read for the Croissant document; not a regular file",
    ),
    "denied": (
        "c.json",
        b'{"name": "x"}',
        FILE_UNREADABLE,
        "FILE=c.json: could not read for the Croissant document; Permission denied",
    ),
}


@pytest.mark.parametrize("entry", sorted(_ENTRIES))
@pytest.mark.parametrize("case", sorted(_CASES))
def test_a_croissant_that_does_not_read_raises_its_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str, case: str
) -> None:
    monkeypatch.chdir(tmp_path)
    name, body, message, text = _CASES[case]
    if body is None:
        (tmp_path / name).mkdir()
    else:
        (tmp_path / name).write_bytes(body)
    denied = deny(tmp_path / name, "open", monkeypatch) if case == "denied" else None
    with denied or contextlib.nullcontext(), pytest.raises(ValueError) as raised:
        _ENTRIES[entry](name)
    said = str(raised.value)
    # The parser's own text ends the not-JSON line.
    assert said.startswith(text) if case == "not-json" else said == text
    assert raised_as(raised.value, message)


@pytest.mark.parametrize("entry", sorted(_ENTRIES))
def test_an_absent_croissant_is_input_not_found(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError) as raised:
        _ENTRIES[entry]("a.json")
    assert str(raised.value) == "Croissant document not found: 'a.json'"
    assert raised_as(raised.value, INPUT_NOT_FOUND)


def test_a_url_that_cannot_be_fetched_is_a_download_failure() -> None:
    with patch("urllib.request.urlopen", side_effect=URLError("refused")):
        with pytest.raises(ValueError) as raised:
            read_croissant("https://example.org/c.json")
    assert str(raised.value) == (
        "URL=https://example.org/c.json: <urlopen error refused>; not read"
    )
    assert raised_as(raised.value, DOWNLOAD_FAILED)


def test_every_entry_is_raised_as_an_error_line() -> None:
    """Each entry the cases raise has an ``ERROR`` line (the reference
    lists it)."""
    entries: set[Message] = {case[2] for case in _CASES.values()}
    assert all("ERROR" in entry.levels for entry in entries)
