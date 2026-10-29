# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""Every route that lists a project's files flags the same Git LFS
pointers: a checkout records each one's ``oid`` as its SHA-256 (no
SHA-512); an archive, a build-extracted file and the build hook keep the
pointer text's own digests.

See also: tests/core/models_wheel/test_models_wheel_lfs_pointer.py (the
directory scan's own cases);
tests/extract/project/test_hatch_hook_lfs_pointer.py (the hook's SBOM);
tests/core/test_lfs_pointer.py (the grammar).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from unittest import mock

import pytest

from pitloom.core import _models_wheel
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.lfs_pointer import LfsPointer
from pitloom.core.models import get_wheel_files, merkle_root_of_files
from pitloom.core.project import ProjectFile
from pitloom.extract.project.sdist import read_sdist
from pitloom.extract.wheel import read_wheel
from tests._lfs import POINTERS, TREE, lfs_pointer_bytes, write_project
from tests._raw_archive import write_raw_tar, write_raw_zip


def _directory(tmp_path: Path, *, bytes_as_is: bool = False) -> list[ProjectFile]:
    _, files, _ = get_wheel_files(
        write_project(tmp_path, TREE), bytes_as_is=bytes_as_is
    )
    return [f for f in files if f.distribution_path != "pyproject.toml"]


def _built(tmp_path: Path) -> list[ProjectFile]:
    write_project(tmp_path / "out", TREE)
    included = [
        IncludedFile(str(tmp_path / "out" / name), name, built=True) for name in TREE
    ]
    with mock.patch.object(
        _models_wheel,
        "_discover_included_files",
        autospec=True,
        return_value=(included, lambda: None),
    ):
        _, files, _ = get_wheel_files(write_project(tmp_path / "src", {}))
    return files


def _wheel(tmp_path: Path) -> list[ProjectFile]:
    info = "demo-1.0.dist-info/"
    members = {
        **TREE,
        f"{info}METADATA": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
        f"{info}WHEEL": b"Wheel-Version: 1.0\n",
        f"{info}RECORD": b"",
    }
    return read_wheel(write_raw_zip(tmp_path / "demo-1.0-py3-none-any.whl", members))[1]


def _sdist(tmp_path: Path) -> list[ProjectFile]:
    members = {
        f"demo-1.0/{name}": data
        for name, data in {
            "PKG-INFO": b"Metadata-Version: 2.1\nName: demo\nVersion: 1.0\n",
            **TREE,
        }.items()
    }
    files = read_sdist(write_raw_tar(tmp_path / "demo-1.0.tar.gz", members)).files
    return [f for f in files if f.physical_path != "PKG-INFO"]


_ROUTES = {
    "directory": _directory,
    "hook": lambda tmp_path: _directory(tmp_path, bytes_as_is=True),
    "built": _built,
    "wheel": _wheel,
    "sdist": _sdist,
}


def _key(project_file: ProjectFile) -> str:
    return project_file.distribution_path.removeprefix("demo-1.0/")


@pytest.mark.parametrize("route", _ROUTES)
def test_every_route_flags_the_same_pointers(tmp_path: Path, route: str) -> None:
    """Each route lists the tree and flags exactly its pointers; only the
    checkout takes the ``oid``, every other file is hashed as it is."""
    files = {_key(f): f for f in _ROUTES[route](tmp_path)}
    assert sorted(files) == sorted(TREE)
    flagged = {name: f.lfs_pointer for name, f in files.items() if f.lfs_pointer}
    assert flagged == POINTERS and len(flagged) == 5
    for name, project_file in files.items():
        pointer = POINTERS.get(name)
        expected: tuple[str, str | None]
        if route == "directory" and pointer is not None:
            expected = (pointer.oid, None)
        else:
            expected = (
                hashlib.sha256(TREE[name]).hexdigest(),
                hashlib.sha512(TREE[name]).hexdigest(),
            )
        assert (project_file.digest_sha256, project_file.digest_sha512) == expected
        assert project_file.stated_sha256() == (
            expected[0] if pointer is None else pointer.oid
        )


def test_a_pulled_pointer_keeps_its_sha256_and_root(tmp_path: Path) -> None:
    """``git lfs pull`` replaces a pointer by its content: the file's
    SHA-256 and the Merkle root stay, a SHA-512 appears, the flag goes."""
    content = b"\x00real parquet bytes\n" * 100
    pointer_tree = {
        "demo/__init__.py": b"",
        "demo/d.parquet": lfs_pointer_bytes(content),
    }
    root, before, _ = get_wheel_files(write_project(tmp_path / "a", pointer_tree))
    pulled = {**pointer_tree, "demo/d.parquet": content}
    assert pulled != pointer_tree
    root_after, after, _ = get_wheel_files(write_project(tmp_path / "b", pulled))
    assert root == root_after == merkle_root_of_files(before)
    old, new = (
        next(f for f in files if f.distribution_path == "demo/d.parquet")
        for files in (before, after)
    )
    assert old.lfs_pointer == LfsPointer(hashlib.sha256(content).hexdigest(), 2000)
    assert (old.digest_sha256, old.digest_sha512) == (new.digest_sha256, None)
    assert new.digest_sha512 == hashlib.sha512(content).hexdigest()
    assert new.lfs_pointer is None


def test_a_pointer_in_an_sdist_is_not_read_as_its_licence(tmp_path: Path) -> None:
    """An sdist's licence source that is a pointer is not kept for licence
    detection; the same name holding text is."""
    # pylint: disable-next=import-outside-toplevel
    from pitloom.extract.project._sdist_scan import scan_archive

    def licences(data: bytes, name: str) -> dict[str, bytes]:
        members = {"demo-1.0/PKG-INFO": b"Name: demo\n", "demo-1.0/LICENSE": data}
        return scan_archive(write_raw_tar(tmp_path / name, members)).licence

    assert licences(b"MIT License\n", "a.tar.gz") == {"LICENSE": b"MIT License\n"}
    assert not licences(lfs_pointer_bytes(b"MIT License\n"), "b.tar.gz")
