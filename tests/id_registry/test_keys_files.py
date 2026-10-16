# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""``keys.file_lookup_key``: the one key rule for a ``software_File`` on
every surface.

See also: test_keys.py (path keys and layout aliases),
test_surfaces_path_keys.py (the surfaces end to end).
"""

from __future__ import annotations

import tempfile
import unicodedata
from pathlib import Path

import pytest

from pitloom.core.project import FilesOrigin, ProjectFile
from pitloom.id_registry.keys import Alias, LookupKey, file_lookup_key

_WHEEL = FilesOrigin(archive=True)
_SDIST = FilesOrigin(archive=True, sdist=True)
_PROJECT = FilesOrigin(project_dir=Path("proj"))
#: An extraction directory path, absolute on the running platform.
_TEMP = Path(tempfile.gettempdir(), "pitloom-build-and-read-x").as_posix()
_NFC = "caf\u00e9.py"
_NFD = unicodedata.normalize("NFD", _NFC)


def _file(physical: str, dist: str, *, built: bool = False) -> ProjectFile:
    return ProjectFile(physical_path=physical, distribution_path=dist, built=built)


@pytest.mark.parametrize(
    ("pf", "origin", "prefix", "expected"),
    [
        (_file("demo/x.py", "demo/x.py"), _WHEEL, None, ("demo/x.py", "layout")),
        (
            _file("d-1.data/scripts/run", "d-1.data/scripts/run"),
            _WHEEL,
            "",
            ("d-1.data/scripts/run", "none"),
        ),
        (
            _file(f"demo/{_NFD}", f"demo/{_NFD}"),
            _WHEEL,
            None,
            (f"demo/{_NFC}", "layout"),
        ),
        # An embed's project below the registry root: joined to its prefix.
        (
            _file("demo/x.py", "demo/x.py"),
            _WHEEL,
            "pkgs/demo",
            ("pkgs/demo/demo/x.py", "layout", "pkgs/demo"),
        ),
        (
            _file("d-1.data/scripts/run", "d-1.data/scripts/run"),
            _WHEEL,
            "pkgs/demo",
            ("pkgs/demo/d-1.data/scripts/run", "none", "pkgs/demo"),
        ),
        (
            _file("demo/x.py", "demo/x.py"),
            _WHEEL,
            "",
            ("demo/x.py", "layout"),
        ),
        (
            _file("../../../x.py", "../../../x.py"),
            _WHEEL,
            "pkgs/demo",
            ("../../../x.py", "layout"),
        ),
        (
            _file("src/demo/x.py", "demo-1.0/src/demo/x.py"),
            _SDIST,
            None,
            ("src/demo/x.py", "canonical"),
        ),
        # No top directory cut: its first part is no `src/`, so no alias.
        (
            _file("demo-1.0/x/y.py", "demo-1.0/x/y.py"),
            _SDIST,
            None,
            ("demo-1.0/x/y.py", "none"),
        ),
        # An sdist's --project-dir below the registry root: joined to its
        # prefix, as a wheel member is.
        (
            _file("src/demo/x.py", "demo-1.0/src/demo/x.py"),
            _SDIST,
            "pkgs/demo",
            ("pkgs/demo/src/demo/x.py", "canonical", "pkgs/demo"),
        ),
        (
            _file("demo-1.0/x/y.py", "demo-1.0/x/y.py"),
            _SDIST,
            "pkgs/demo",
            ("pkgs/demo/demo-1.0/x/y.py", "none", "pkgs/demo"),
        ),
        (
            _file(f"{_TEMP}/demo/x.py", "demo/x.py", built=True),
            _PROJECT,
            "",
            ("demo/x.py", "layout"),
        ),
        (
            _file(f"{_TEMP}/demo/x.py", "demo/x.py", built=True),
            _PROJECT,
            "pkgs/demo",
            ("pkgs/demo/demo/x.py", "layout", "pkgs/demo"),
        ),
        (
            _file(f"{_TEMP}/demo/x.py", "demo/x.py", built=True),
            _PROJECT,
            None,
            ("demo/x.py", "layout"),
        ),
        (
            _file(
                f"{_TEMP}/d-1.data/purelib/x.py", "d-1.data/purelib/x.py", built=True
            ),
            _PROJECT,
            "",
            ("d-1.data/purelib/x.py", "none"),
        ),
        (
            _file(
                f"{_TEMP}/d-1.data/purelib/x.py", "d-1.data/purelib/x.py", built=True
            ),
            _PROJECT,
            "pkgs/demo",
            ("pkgs/demo/d-1.data/purelib/x.py", "none", "pkgs/demo"),
        ),
        # A dist path that does not join: as is, unprefixed.
        (
            _file(f"{_TEMP}/x.py", "../../../x.py", built=True),
            _PROJECT,
            "pkgs/demo",
            ("../../../x.py", "layout"),
        ),
        (
            _file("src/demo/x.py", "demo/x.py"),
            _PROJECT,
            "",
            ("src/demo/x.py", "canonical"),
        ),
        (
            _file("src/demo/x.py", "demo/x.py"),
            _PROJECT,
            "pkgs/demo",
            ("pkgs/demo/src/demo/x.py", "canonical", "pkgs/demo"),
        ),
        (
            _file("../shared/x.py", "shared/x.py"),
            _PROJECT,
            "pkgs/demo",
            ("pkgs/shared/x.py", "canonical", "pkgs/demo"),
        ),
    ],
    ids=[
        "wheel",
        "wheel-data",
        "wheel-nfc",
        "wheel-prefix",
        "wheel-data-prefix",
        "wheel-root-prefix",
        "wheel-no-join",
        "sdist",
        "sdist-uncut",
        "sdist-prefix",
        "sdist-uncut-prefix",
        "built",
        "built-prefix",
        "built-outside-root",
        "built-data",
        "built-data-prefix",
        "built-no-join",
        "project-root",
        "project-prefix",
        "project-shared",
    ],
)
def test_path_keys(
    pf: ProjectFile,
    origin: FilesOrigin,
    prefix: str | None,
    expected: tuple[str, ...],
) -> None:
    """Each key with its alias, below the project *prefix* (``base``) when
    joined to it."""
    key, alias, *base = expected
    want = LookupKey(key, Alias(alias), True, *base)
    assert file_lookup_key(pf, origin, prefix) == want


@pytest.mark.parametrize(
    ("pf", "prefix", "key"),
    [
        # Project outside the registry's root: the physical path as is.
        (_file("src/demo/x.py", "demo/x.py"), None, "src/demo/x.py"),
        # Leads outside the root: as is.
        (_file("../../x.py", "x.py"), "demo", "../../x.py"),
        # A force-included file outside the project: no project path.
        (_file(f"{_TEMP}/x.py", "demo/x.py"), "", "demo/x.py"),
    ],
    ids=["outside-root", "above-root", "absolute"],
)
def test_project_keys_without_join_have_no_alias(
    pf: ProjectFile, prefix: str | None, key: str
) -> None:
    assert file_lookup_key(pf, _PROJECT, prefix) == LookupKey(key)


@pytest.mark.parametrize("prefix", [None, "pkgs/demo"])
def test_sdist_member_that_does_not_join_keeps_its_name(prefix: str | None) -> None:
    pf = _file("../../../x.py", "x.py")
    assert file_lookup_key(pf, _SDIST, prefix) == LookupKey("../../../x.py")


def test_default_origin_is_a_project_file() -> None:
    """A document naming no origin keys a file by its physical path."""
    pf = _file("src/demo/x.py", "demo/x.py")
    assert file_lookup_key(pf, FilesOrigin(), None) == LookupKey("src/demo/x.py")
