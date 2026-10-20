# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An archive with no ``PKG-INFO``: its metadata from ``pyproject.toml``,
whose ``dynamic`` fields only a build computes.

See also: tests/extract/project/test_sdist.py (the ``PKG-INFO`` read).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from pitloom.extract.project.sdist import read_sdist
from tests.assemble.conftest import _make_sdist

_PROJECT = '[project]\nname = "demo"\n'


@pytest.mark.parametrize(
    ("tail", "fields"),
    [
        (
            'dynamic = ["readme", "dependencies", "version"]\n',
            "version, dependencies",
        ),
        ('version = "1"\ndynamic = ["readme"]\n', None),
        ('version = "1"\ndynamic = "version"\n', None),
        ('version = "1"\n', None),
    ],
    ids=["dynamic-read-fields", "dynamic-other", "not-a-list", "none"],
)
def test_dynamic_fields_warn_without_pkg_info(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, tail: str, fields: str | None
) -> None:
    """A ``dynamic`` field the fallback reads is reported, not left unset
    silently (a real sdist's ``PKG-INFO`` carries it, built). One ``WARNING:``
    names each."""
    sdist = _make_sdist(
        tmp_path,
        members={"PKG-INFO": None, "pyproject.toml": (_PROJECT + tail).encode()},
    )

    with caplog.at_level(logging.WARNING):
        read_sdist(sdist, read_config=False)

    assert caplog.messages == (
        [
            f"{sdist}:pyproject.toml: dynamic field(s) not resolved without"
            f" PKG-INFO | Field(s) affected (skipped): {fields}"
        ]
        if fields
        else []
    )
