# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Drift guard: every expression Pitloom accepts as a licence also parses with
``py-spdx-license``, the independent implementation of the SPDX grammar.

Two implementations of one operation can disagree later without a test failing
(CLAUDE.md, "Reuse/dedup"). Today the second one is Pitloom's own parsing
around the library; after Pitloom reads declared values through ``licenseid``
0.7.0 (adoption plan, T13) it is ``licenseid``. This test runs unchanged on
both: its input is the answer, not the code that produced it.

The library lacks two forms of the grammar (``Foo+`` and ``AdditionRef-``);
those terms are reduced to the part it has before parsing.

See also: tests/extract/license_classify_cases.py.
"""

from __future__ import annotations

import re

import pytest
from py_spdx_license import get_exception, get_license
from py_spdx_license import parse as spdx_parse

from pitloom.extract._license_classify import classify_license
from tests.extract.license_classify_cases import CASES

#: Valid expressions beyond the table: nesting, ``WITH``, references, repeats.
_EXTRA = [
    "MIT OR (Apache-2.0 AND BSD-3-Clause)",
    "(MIT OR Apache-2.0) AND GPL-2.0-only WITH Classpath-exception-2.0",
    "LicenseRef-a AND DocumentRef-d:LicenseRef-b",
    "Apache-2.0 WITH LLVM-exception OR MIT",
    "GPL-3.0-or-later OR LGPL-3.0-only OR MIT OR Apache-2.0",
    "MIT OR ISC OR MIT OR ISC",
]
_VALUES = sorted({c[0] for c in CASES if c[1] == "expression" and c[0]} | set(_EXTRA))
_ADDITION_REF = re.compile(r"\s+WITH\s+AdditionRef-\S+")
_PLUS = re.compile(r"(?<=[\w.])\+")
_WORDS = frozenset({"AND", "OR", "WITH"})
_REFERENCES = ("LicenseRef-", "DocumentRef-")


def _library_part(expression: str) -> str:
    """*expression* without the forms the library's grammar lacks."""
    return _PLUS.sub("", _ADDITION_REF.sub("", expression))


@pytest.mark.parametrize("raw", _VALUES, ids=lambda raw: repr(raw)[:40])
def test_an_accepted_answer_parses_with_the_library(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None and got.kind == "expression"

    spdx_parse(_library_part(got.value))  # raises ParseError on drift


def _unknown_ids(expression: str) -> list[str]:
    """The ids and exceptions of *expression* that the library's List lacks."""
    unknown: list[str] = []
    previous = ""
    for token in re.findall(r"[^\s()]+", _library_part(expression)):
        if token not in _WORDS and not token.startswith(_REFERENCES):
            listed = get_exception if previous == "WITH" else get_license
            if listed(token) is None:
                unknown.append(token)
        previous = token
    return unknown


@pytest.mark.parametrize("raw", _VALUES, ids=lambda raw: repr(raw)[:40])
def test_an_accepted_answer_names_only_listed_ids(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None

    unknown = _unknown_ids(got.value)
    assert not unknown, unknown


def test_the_guard_sees_an_id_the_library_lacks() -> None:
    assert _unknown_ids("MIT OR Foo-1.0 WITH Bar-exception") == [
        "Foo-1.0",
        "Bar-exception",
    ]
