# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""The SHA-256 an SBOM states for a file on disk
(:func:`~pitloom.core.file_hash.stated_sha256_hex`) against every route that
states one, and the raw-bytes comparisons that must not take it.

See also: tests/id_registry/test_registry_lfs_pointer.py (the registry's use);
tests/test_lfs_pointer_surfaces.py (the routes' digests).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from pitloom.core._models_wheel import _same_bytes
from pitloom.core._models_wheel_types import IncludedFile
from pitloom.core.file_hash import file_digests, sha256_digest, stated_sha256_hex
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectFile, digest_fields
from pitloom.id_registry import sha256_file
from tests._lfs import lfs_pointer_bytes, pointers, tree, write_project


def _files(root: Path, *, bytes_as_is: bool = False) -> dict[str, ProjectFile]:
    _, files, _ = get_wheel_files(root, bytes_as_is=bytes_as_is)
    return {f.distribution_path: f for f in files}


def test_every_route_states_the_same_sha256_for_a_file_on_disk(tmp_path: Path) -> None:
    """One rule: the helper, the registry's hash, ``digest_fields`` and a
    directory scan agree on every file of the tree; a hook or build scan
    (``bytes_as_is``) keeps the pointer text's digest but still reports the
    ``oid`` as its stated one."""
    contents, stated_pointers = tree(), pointers()
    root = write_project(tmp_path, contents)
    checkout, as_is = _files(root), _files(root, bytes_as_is=True)
    for name in contents:
        path = root / name
        stated = stated_sha256_hex(path)
        assert sha256_file(path) == stated
        assert digest_fields(file_digests(path))["digest_sha256"] == stated
        assert checkout[name].digest_sha256 == stated
        archived = as_is[name].lfs_pointer
        assert (archived.oid if archived else as_is[name].digest_sha256) == stated
        if name in stated_pointers:
            assert stated == stated_pointers[name].oid
            # Non-vacuous: the raw digest and the archive record differ.
            assert sha256_digest(path).hex() != stated
            assert as_is[name].digest_sha256 == sha256_digest(path).hex()
        else:
            assert stated == sha256_digest(path).hex()


def test_a_pulled_file_states_the_pointers_sha256(tmp_path: Path) -> None:
    content = b"model weights\n"
    path = tmp_path / "w.bin"
    path.write_bytes(lfs_pointer_bytes(content))
    before = stated_sha256_hex(path)
    path.write_bytes(content)
    assert stated_sha256_hex(path) == before


def test_the_registry_copy_match_compares_raw_bytes(tmp_path: Path) -> None:
    """Two pointers of one ``oid`` in different line endings state one
    SHA-256 but are not the same bytes: ``_same_bytes`` says no."""
    lf, crlf, again = (tmp_path / n for n in ("lf", "crlf", "again"))
    lf.write_bytes(lfs_pointer_bytes(b"x"))
    crlf.write_bytes(lfs_pointer_bytes(b"x", eol="\r\n"))
    again.write_bytes(lf.read_bytes())
    assert stated_sha256_hex(lf) == stated_sha256_hex(crlf)
    digest = sha256_digest(lf)
    assert not _same_bytes(IncludedFile(str(crlf), "crlf", built=True), digest)
    assert _same_bytes(IncludedFile(str(again), "again", built=True), digest)


def test_an_unreadable_path_raises_as_the_raw_reader_does(tmp_path: Path) -> None:
    with pytest.raises(OSError):
        stated_sha256_hex(tmp_path / "missing")
    with pytest.raises(OSError):
        stated_sha256_hex(tmp_path)
