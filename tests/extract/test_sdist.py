# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Tests for sdist archive metadata extraction."""

# pylint: disable=redefined-outer-name

from __future__ import annotations

import io
import tarfile
import zipfile
from pathlib import Path

import pytest

from pitloom.extract._sdist import read_sdist
from pitloom.extract.project import read_project


@pytest.fixture
def sample_pkg_info() -> str:
    return (
        "Metadata-Version: 2.1\n"
        "Name: demo-sdist-pkg\n"
        "Version: 1.2.3\n"
        "Summary: A demo package for sdist testing\n"
        "Author: Alice Developer\n"
        "Author-email: alice@example.com\n"
        "License: Apache-2.0\n"
        "Requires-Dist: requests>=2.28.0\n"
    )


def test_read_tar_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.tar.gz"

    with tarfile.open(sdist_path, "w:gz") as tf:
        # PKG-INFO
        pkg_bytes = sample_pkg_info.encode("utf-8")
        ti = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

        # pyproject.toml
        pyproj_bytes = b'[project]\nname = "demo-sdist-pkg"\nversion = "1.2.3"\n'
        ti2 = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/pyproject.toml")
        ti2.size = len(pyproj_bytes)
        tf.addfile(ti2, io.BytesIO(pyproj_bytes))

        # source file
        src_bytes = b'print("hello from sdist")\n'
        ti3 = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/src/main.py")
        ti3.size = len(src_bytes)
        tf.addfile(ti3, io.BytesIO(src_bytes))

    metadata, files = read_sdist(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    assert metadata.description == "A demo package for sdist testing"
    assert metadata.authors == [{"name": "Alice Developer"}]
    assert metadata.dependencies == ["requests>=2.28.0"]
    assert len(files) == 3


def test_read_zip_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.zip"

    with zipfile.ZipFile(sdist_path, "w") as zf:
        zf.writestr("demo-sdist-pkg-1.2.3/PKG-INFO", sample_pkg_info)
        zf.writestr("demo-sdist-pkg-1.2.3/src/main.py", 'print("hello zip")\n')

    metadata, files = read_sdist(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    assert len(files) == 2


def test_read_project_with_sdist(tmp_path: Path, sample_pkg_info: str) -> None:
    sdist_path = tmp_path / "demo-sdist-pkg-1.2.3.tar.gz"

    with tarfile.open(sdist_path, "w:gz") as tf:
        pkg_bytes = sample_pkg_info.encode("utf-8")
        ti = tarfile.TarInfo(name="demo-sdist-pkg-1.2.3/PKG-INFO")
        ti.size = len(pkg_bytes)
        tf.addfile(ti, io.BytesIO(pkg_bytes))

    metadata, _, path_used = read_project(sdist_path)
    assert metadata.name == "demo-sdist-pkg"
    assert metadata.version == "1.2.3"
    assert path_used == sdist_path


def test_read_sdist_not_found(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        read_sdist(tmp_path / "non_existent.tar.gz")
