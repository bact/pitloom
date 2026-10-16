# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Unit tests for :func:`pitloom.core.project.is_sdist_archive`.

See also: :mod:`tests.core.test_build_options`, which covers
:meth:`~pitloom.core.build_options.BuildOptions.settle_target`'s use of
this predicate.
"""

from __future__ import annotations

import dataclasses
from pathlib import Path

import pytest

from pitloom.core._models_wheel import _build_project_file_entry
from pitloom.core._models_wheel_types import FileScanConfig, IncludedFile
from pitloom.core.document import DocumentModel
from pitloom.core.project import (
    FilesOrigin,
    ProjectFile,
    ProjectMetadata,
    is_sdist_archive,
)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("demo-1.0.0.tar.gz", True),
        ("demo-1.0.0.tgz", True),
        ("demo-1.0.0.tar.bz2", True),
        ("demo-1.0.0.tar.xz", True),
        ("demo-1.0.0.zip", True),
        ("demo-1.0.0.ZIP", True),
        ("demo-1.0.0-py3-none-any.whl", False),
        ("notes.txt", False),
    ],
)
def test_is_sdist_archive_existing_file(
    tmp_path: Path, name: str, expected: bool
) -> None:
    target = tmp_path / name
    target.write_text("x\n", encoding="utf-8")
    assert is_sdist_archive(target) is expected


def test_is_sdist_archive_directory_with_archive_name_is_false(
    tmp_path: Path,
) -> None:
    """A directory named like an archive is not one: the file check must
    gate the extension match, so ``os.path.isfile`` (not
    ``os.path.exists``) is the correct predicate."""
    target = tmp_path / "demo-1.0.0.tar.gz"
    target.mkdir()
    assert is_sdist_archive(target) is False


def test_is_sdist_archive_missing_path_is_false(tmp_path: Path) -> None:
    target = tmp_path / "demo-1.0.0.tar.gz"
    assert is_sdist_archive(target) is False


@pytest.mark.parametrize("built", [True, False], ids=["built", "source"])
def test_built_threads_from_included_file(tmp_path: Path, built: bool) -> None:
    """``IncludedFile.built`` reaches the ``ProjectFile``, and survives
    ``dataclasses.replace``."""
    source = tmp_path / "x.py"
    source.write_bytes(b"x = 1\n")
    config = FileScanConfig(None, None, (), "magika")
    entry, _ = _build_project_file_entry(
        source,
        IncludedFile(str(source), "pkg/x.py", built=built),
        tmp_path,
        need_bytes=True,
        skip_merkle_root=False,
        scan_config=config,
    )
    assert entry.built is built
    assert dataclasses.replace(entry, copyright_text="c").built is built


def test_defaults_built_and_files_origin() -> None:
    """A fresh ``ProjectFile`` is not built; a fresh ``DocumentModel``
    names no file origin."""
    assert not ProjectFile("a", "a").built
    assert DocumentModel(project=ProjectMetadata(name="n")).files_origin == (
        FilesOrigin(None, False)
    )
