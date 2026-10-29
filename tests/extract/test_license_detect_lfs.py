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

from pitloom.assemble import generate_project_sbom
from pitloom.extract._license_detect import (
    collect_license_candidates,
    read_license_members,
)
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
    '[project]\nname = "demo"\nversion = "1.0"\nlicense-files = ["LICENSE"]\n'
    "[build-system]\nrequires = []\n"
)


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


def test_a_project_naming_a_pointer_licence_file_is_read_quietly(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    """``license-files`` naming a pointer outside the package files: no
    crash, no warning, and nothing of the pointer's text in the SBOM."""
    (tmp_path / "pyproject.toml").write_text(_PYPROJECT, encoding="utf-8")
    (tmp_path / "LICENSE").write_bytes(_FILES["pointer"][0])
    with caplog.at_level(logging.WARNING):
        sbom = generate_project_sbom(tmp_path, offline=True)
    assert not caplog.records
    assert "git-lfs.github.com" not in sbom
