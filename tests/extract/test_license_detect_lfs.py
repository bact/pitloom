# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""A licence source of a directory that is a Git LFS pointer is no licence
text (the sdist route skips it the same way); a normal file, and a long file
that only opens like a pointer, are read.

See also: tests/test_lfs_pointer_surfaces.py (the sdist case).
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest
from pyproject_metadata import License

from pitloom.assemble import generate_project_sbom
from pitloom.extract._license_detect import (
    collect_license_candidates,
    read_license_members,
)
from pitloom.extract.project._pyproject_license import stated_pyproject_license
from tests._lfs import lfs_pointer_bytes

_MIT = b"MIT License\n\nPermission is hereby granted, free of charge.\n"
_LOOK_ALIKE = b"version https://git-lfs.github.com/spec/v1\n" + b"x" * 1024
_FILES = {
    "pointer": (lfs_pointer_bytes(_MIT), False),
    "text": (_MIT, True),
    "look-alike": (_LOOK_ALIKE, True),
    "malformed": (b"version https://git-lfs.github.com/spec/v1\noid sha256:00\n", True),
}
_PYPROJECT = (
    '[project]\nname = "demo"\nversion = "1.0"\n{}\n[build-system]\nrequires = []\n'
)
_STATED = {
    "license-files": 'license-files = ["LICENSE"]',
    "license-table": 'license = {file = "LICENSE"}',
}


@pytest.mark.parametrize("kind", _FILES)
def test_a_pointer_licence_file_is_not_read(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, kind: str
) -> None:
    data, read = _FILES[kind]
    (tmp_path / "LICENSE").write_bytes(data)
    with caplog.at_level(logging.DEBUG):
        members = read_license_members(tmp_path)
    assert members == ({"LICENSE": data} if read else {})
    assert bool(collect_license_candidates(tmp_path)) is read
    # Said at DEBUG only, and only for the pointer.
    assert [r.levelno for r in caplog.records] == ([] if read else [logging.DEBUG])


@pytest.mark.parametrize("stated", _STATED)
def test_a_project_naming_a_pointer_licence_file_is_read_quietly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture, stated: str
) -> None:
    """``license-files`` or ``license = {file = ...}`` naming a pointer
    outside the package files: no crash, no warning, and nothing of the
    pointer's text in the SBOM (``pyproject-metadata`` reads the table's
    file as its ``text``)."""
    (tmp_path / "pyproject.toml").write_text(
        _PYPROJECT.format(_STATED[stated]), encoding="utf-8"
    )
    (tmp_path / "LICENSE").write_bytes(_FILES["pointer"][0])
    with caplog.at_level(logging.WARNING):
        sbom = generate_project_sbom(tmp_path, offline=True)
    assert not caplog.records
    assert "git-lfs.github.com" not in sbom


@pytest.mark.parametrize(
    ("kind", "with_file", "with_dir", "expected"),
    [
        ("pointer", True, True, "LICENSE"),  # the unreadable-file fallback
        ("pointer", True, False, None),
        ("pointer", False, True, None),
        ("text", False, True, "MIT"),
        ("look-alike", False, True, _LOOK_ALIKE.decode()),
    ],
    ids=["pointer-file", "pointer-no-dir", "pointer-text", "text", "look-alike"],
)
def test_a_licence_text_that_is_a_pointer_is_no_licence_text(
    tmp_path: Path, kind: str, with_file: bool, with_dir: bool, expected: str | None
) -> None:
    """``pyproject-metadata`` turns ``file`` into ``text``: a whole pointer
    there is the unreadable file, as :func:`read_license_file` treats it."""
    text = "MIT" if kind == "text" else _FILES[kind][0].decode()
    (tmp_path / "LICENSE").write_bytes(_FILES["pointer"][0])
    table = License(text, tmp_path / "LICENSE" if with_file else None)
    result = stated_pyproject_license(table, [], tmp_path if with_dir else None)
    assert result == (expected, None)
