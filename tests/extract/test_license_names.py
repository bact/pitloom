# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for :mod:`pitloom.extract._license_names`: a deprecated id's List
name that ``licenseid`` does not read is that id, and the table of those
names is held to the SPDX License List packaged with ``licenseid``.

See also: tests/extract/project/test_field_agreement.py and
tests/assemble/test_deps_license.py (the two callers).
"""

from __future__ import annotations

import gzip
import json
from importlib.resources import files
from typing import Any

import pytest
from licenseid import resolve

from pitloom.extract._license_names import UNREAD_LISTED_NAMES, same_licence

#: Each (List name, id) pair of the table, with short test ids.
NAME_PAIRS = [
    pytest.param(name, license_id, id=license_id)
    for name, license_id in sorted(UNREAD_LISTED_NAMES.items())
]


def _packaged_licences() -> list[dict[str, Any]]:
    """The licences of the SPDX License List bundle in the ``licenseid`` wheel."""
    bundle = files("licenseid") / "data" / "spdx-bundle.json.gz"
    data: dict[str, Any] = json.loads(gzip.decompress(bundle.read_bytes()))
    licences: list[dict[str, Any]] = data["licenses"]
    return licences


@pytest.mark.parametrize(("name", "license_id"), NAME_PAIRS)
def test_a_deprecated_id_is_its_list_name_in_any_case_and_order(
    name: str, license_id: str
) -> None:
    assert same_licence(name, license_id)
    assert same_licence(license_id, f" {name.upper()} ")


@pytest.mark.parametrize(
    ("one", "other"),
    [
        ("GNU Free Documentation License v1.3", "GFDL-1.2"),  # another version
        ("GNU Free Documentation License v1.3", "GFDL-1.3-only"),  # not narrowed
        ("wxWindows Library License", "WxWindows-exception-3.1"),
        ("GNU Free Documentation License v1.3", "GNU Free Documentation License"),
        ("MIT License", "Apache-2.0"),
    ],
    ids=["version", "narrowed", "successor", "two-names", "other"],
)
def test_a_name_of_another_licence_is_not_the_same(one: str, other: str) -> None:
    assert not same_licence(one, other)
    assert not same_licence(other, one)


def test_the_table_is_every_listed_name_licenseid_does_not_read() -> None:
    """Drift guard: a name ``licenseid`` starts reading leaves the table, a
    new one it does not read joins it, and each is a deprecated id's name as
    the packaged List spells it."""
    unread = {}
    for licence in _packaged_licences():
        if resolve(licence["name"], source="packaged")["expression"] is None:
            assert licence["isDeprecatedLicenseId"], licence["licenseId"]
            unread[licence["name"].casefold()] = licence["licenseId"]
    assert unread == dict(UNREAD_LISTED_NAMES)
