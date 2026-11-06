# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Guard: every expression Pitloom records is one LicenseID reads back as
itself, as written, with nothing decided: a recorded value is canonical, so a
second reading (a merge, an enrichment fragment, a later run on the SBOM)
cannot change it or credit a resolver with it.

LicenseID is the only reader of a declared value; this test holds its
answers to the one property Pitloom relies on, with no second parser.

See also: tests/extract/license_classify_cases.py.
"""

from __future__ import annotations

import pytest

from pitloom.extract._license_classify import (
    classify_license,
    tag_license_normalization,
)
from pitloom.extract._license_resolve import resolve_value
from tests.extract.license_classify_cases import CASES

#: Valid expressions beyond the table: nesting, ``WITH``, references, repeats.
_EXTRA = [
    "MIT OR (Apache-2.0 AND BSD-3-Clause)",
    "(MIT OR Apache-2.0) AND GPL-2.0-only WITH Classpath-exception-2.0",
    "LicenseRef-a AND DocumentRef-d:LicenseRef-b",
    "Apache-2.0 WITH LLVM-exception OR MIT",
    "GPL-3.0-or-later OR LGPL-3.0-only OR MIT OR Apache-2.0",
    "MIT OR ISC OR MIT OR ISC",
    "GPL-2.0 OR MIT",
]
_VALUES = sorted({c[0] for c in CASES if c[1] == "expression" and c[0]} | set(_EXTRA))


@pytest.mark.parametrize("raw", _VALUES, ids=lambda raw: repr(raw)[:40])
def test_a_recorded_expression_reads_back_as_itself(raw: str) -> None:
    got = classify_license(raw, warn=False)
    assert got is not None and got.kind == "expression"

    again = resolve_value(got.value)
    assert again is not None
    assert again.expression == got.value
    assert not again.decided
    assert not again.expansions
    assert tag_license_normalization("P", got.value, again.expression) == "P"
