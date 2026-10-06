# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract.project._field_agreement`.

See also: test_installed_reconcile.py and test_setuptools_merge_license.py,
its two callers' tests.
"""

from __future__ import annotations

import pytest

from pitloom.core.project import ConflictCandidate, ProjectMetadata
from pitloom.extract.project._field_agreement import add_conflict, values_agree


@pytest.mark.parametrize(
    ("field", "a", "b", "agree"),
    [
        ("version", "1.0", "1.0.0", True),  # PEP 440, not SemVer
        ("version", "2.0", "1.0", False),
        ("requires_python", ">=3.9", ">= 3.9", True),
        ("requires_python", ">=3.9", ">=3.10", False),
        # never raise on an unparseable specifier: stripped strings compared
        ("requires_python", " not-a-specifier ", "not-a-specifier", True),
        ("requires_python", "not-a-specifier", "also-not-one", False),
        ("requires_python", None, "", True),
        ("license_name", "MIT License", "MIT", True),
        ("license_name", "UNKNOWN", "Apache-2.0", True),  # weak agrees
        ("license_name", "NONE", "MIT", False),  # NONE is a statement
        ("license_name", "MIT", "Apache-2.0", False),
        ("license_name", None, "MIT", False),
        ("license_name", None, " ", True),
    ],
)
def test_values_agree(field: str, a: str | None, b: str | None, agree: bool) -> None:
    assert values_agree(field, a, b) is agree


def _candidate(value: str, source: str) -> ConflictCandidate:
    return {"value": value, "role": "declared", "source": source}


def test_add_conflict_keeps_earlier_and_records_each_once() -> None:
    """A second producer adds after the first; a candidate both name is
    recorded once; the shared list of a shallow copy is not changed."""
    first = [_candidate("MIT", "a"), _candidate("Apache-2.0", "b")]
    original = ProjectMetadata(name="p", field_conflicts={"license": first})
    copy = original.replace_with_fresh_containers()
    add_conflict(copy, "license", [_candidate("MIT", "a"), _candidate("BSD", "c")])
    assert copy.field_conflicts["license"] == [*first, _candidate("BSD", "c")]
    assert original.field_conflicts["license"] == first
    assert len(first) == 2
