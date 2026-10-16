# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""An sdist member's ``physical_path`` is project-relative: its top
directory (the one holding the first root-level ``PKG-INFO``) is dropped.

See also: tests/extract/project/test_sdist_member_names.py.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.extract.project.sdist import read_sdist
from tests._raw_archive import write_raw_tar, write_raw_zip

_INFO = b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0.0\n"
_PYPROJECT = b'[project]\nname = "demo"\nversion = "1.0.0"\n'

#: members -> {distribution_path: physical_path}
_CASES = {
    "nested": (
        {"a-1/PKG-INFO": _INFO, "a-1/src/demo/x.py": b"x", "a-1/LICENSE": b"L"},
        {
            "a-1/PKG-INFO": "PKG-INFO",
            "a-1/src/demo/x.py": "src/demo/x.py",
            "a-1/LICENSE": "LICENSE",
        },
    ),
    "stray": (
        {"a-1/PKG-INFO": _INFO, "stray.txt": b"s"},
        {"a-1/PKG-INFO": "PKG-INFO", "stray.txt": "stray.txt"},
    ),
    "two-dirs": (
        {"b-2/x.py": b"b", "a-1/PKG-INFO": _INFO, "a-1/y.py": b"y"},
        {"b-2/x.py": "b-2/x.py", "a-1/PKG-INFO": "PKG-INFO", "a-1/y.py": "y.py"},
    ),
    "no-pkg-info": (
        {"a-1/pyproject.toml": _PYPROJECT, "a-1/x.py": b"x"},
        {"a-1/pyproject.toml": "a-1/pyproject.toml", "a-1/x.py": "a-1/x.py"},
    ),
    "dot-prefix": (
        {"./a-1/PKG-INFO": _INFO, "./a-1/src/x.py": b"x"},
        {"a-1/PKG-INFO": "PKG-INFO", "a-1/src/x.py": "src/x.py"},
    ),
}


@pytest.mark.parametrize("kind", ["zip", "tar"])
@pytest.mark.parametrize("case", _CASES, ids=list(_CASES))
def test_physical_path_drops_top_directory(
    tmp_path: Path, case: str, kind: str
) -> None:
    """Top directory dropped; a stray or other-directory member, and an
    sdist with no ``PKG-INFO`` root, are left unchanged."""
    members, expected = _CASES[case]
    if kind == "zip":
        sdist = write_raw_zip(tmp_path / "a-1.zip", members)
    else:
        sdist = write_raw_tar(tmp_path / "a-1.tar.gz", members)
    contents = read_sdist(sdist, read_config=False)
    assert {f.distribution_path: f.physical_path for f in contents.files} == expected
