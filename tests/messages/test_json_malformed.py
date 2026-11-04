# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A Croissant file that does not read raises a ``ValueError`` carrying its
code, through both library entry points (``read_croissant`` and a loom
dataset's ``croissant=``): ``json-malformed`` (not JSON, not an object),
``over-cap`` (nesting), ``file-unreadable`` (a directory, a file the system
refuses). An absent file and a URL that cannot be fetched carry none yet.

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
from pitloom.messages import (
    FILE_UNREADABLE,
    JSON_MALFORMED,
    OVER_CAP,
    Message,
    code_of,
)
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

_CASES = {
    "not-json": ("c.json", b"{not json", JSON_MALFORMED, "'c.json': not valid JSON; "),
    "a-list": ("c.json", b"[1, 2]", JSON_MALFORMED, "'c.json': not a JSON object"),
    "too-deep": (
        "c.json",
        b"[" * 100,
        OVER_CAP,
        "'c.json': larger than the 64-level Croissant-nesting cap; not read",
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
    assert str(raised.value).startswith(text)
    assert raised_as(raised.value, message)


@pytest.mark.parametrize("entry", sorted(_ENTRIES))
def test_an_absent_croissant_carries_no_code(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, entry: str
) -> None:
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError, match="^Cannot read Croissant source 'a.json'"):
        _ENTRIES[entry]("a.json")


def test_a_url_that_cannot_be_fetched_carries_no_code() -> None:
    with patch("urllib.request.urlopen", side_effect=URLError("refused")):
        with pytest.raises(
            ValueError, match="^Cannot read Croissant source "
        ) as raised:
            read_croissant("https://example.org/c.json")
    assert code_of(raised.value) is None


def test_every_entry_is_raised_as_an_error_line() -> None:
    """Each entry the cases raise has an ``ERROR`` line (the reference
    lists it)."""
    entries: set[Message] = {case[2] for case in _CASES.values()}
    assert all("ERROR" in entry.levels for entry in entries)
