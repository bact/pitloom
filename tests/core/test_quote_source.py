# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""`pitloom.core.quote_source.quote_source`: a path or file name as it is
written, quoted, on one line, whatever it holds."""

from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

import pytest

from pitloom.core.quote_source import quote_source


@pytest.mark.parametrize(
    ("source", "expected"),
    [
        ("plain/path.txt", "'plain/path.txt'"),
        ("caf\u00e9", "'caf\u00e9'"),
        ("a\nWARNING: x", "'a\\nWARNING: x'"),
        ("a\r\tb", "'a\\r\\tb'"),
        ("a\x1b[0m", "'a\\x1b[0m'"),
        ("a\u202eb", "'a\\u202eb'"),
        ("a\u2028b\u2029c", "'a\\u2028b\\u2029c'"),
        ("lone\ud800", "'lone\\ud800'"),
        ("C:\\Users\\x", "'C:\\Users\\x'"),
        (Path("a/b"), "'" + str(Path("a/b")) + "'"),
        (PureWindowsPath("C:/a/b"), "'C:\\a\\b'"),
        (b"bytes\xff", "'bytes\\udcff'"),
    ],
    ids=lambda v: repr(v)[:30],
)
def test_quote_source(source: object, expected: str) -> None:
    """Quoted as written (single backslashes), the parts that could split or
    reorder a line escaped, a path object by its text."""
    assert quote_source(source) == expected  # type: ignore[arg-type]
    assert len(quote_source(source).splitlines()) == 1  # type: ignore[arg-type]


def test_a_path_like_that_is_not_a_path_is_its_text() -> None:
    class Like:
        def __fspath__(self) -> str:
            return "x/y"

    assert os.fspath(Like()) == "x/y"
    assert quote_source(Like()) == "'x/y'"
