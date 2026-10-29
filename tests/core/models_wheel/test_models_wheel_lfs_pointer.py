# SPDX-FileContributor: Arthit Suriyawongkul
# SPDX-FileCopyrightText: 2026-present Arthit Suriyawongkul
# SPDX-FileType: SOURCE
# SPDX-License-Identifier: Apache-2.0

"""get_wheel_files() on a checkout with Git LFS pointers: what is a
pointer, and that its text is never scanned as the content.

See also: tests/test_lfs_pointer_surfaces.py (every route flags the same
pointers); tests/core/test_lfs_pointer.py (the grammar).
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from pitloom.core.content_type_config import ContentTypeOverride
from pitloom.core.models import get_wheel_files
from pitloom.core.project import ProjectFile
from pitloom.extract import _file_headers
from tests._lfs import lfs_pointer_bytes, write_project
from tests._lfs import tree as demo_tree

_POINTER = lfs_pointer_bytes(b"real content")
_OPENING, _OID_LINE, _SIZE_LINE = _POINTER.splitlines(keepends=True)


def _scan(tmp_path: Path, tree: dict[str, bytes], **kwargs: Any) -> list[ProjectFile]:
    _, files, _ = get_wheel_files(write_project(tmp_path, tree), **kwargs)
    return files


def _file(files: list[ProjectFile], name: str) -> ProjectFile:
    return next(f for f in files if f.distribution_path == name)


@pytest.mark.parametrize(
    "data",
    [
        _OPENING + b"oid sha256:" + b"0" * 63 + b"\n" + _SIZE_LINE,
        b"version https://git-lfs.github.com/spec/v2\n" + _OID_LINE + _SIZE_LINE,
        _OPENING + b"x" * 1024,
    ],
    ids=["bad-oid", "bad-version", "1k-opening"],
)
def test_a_near_pointer_is_hashed_as_it_is(tmp_path: Path, data: bytes) -> None:
    """Only a whole pointer takes its ``oid``: a valid opening with a bad
    oid, a valid oid under another version line, or a 1 KiB file that
    opens like one is content, with both its own digests."""
    found = _file(
        _scan(tmp_path, {"demo/f.dat": data, "demo/p.dat": _POINTER}), "demo/f.dat"
    )
    assert found.lfs_pointer is None
    assert (found.digest_sha256, found.digest_sha512) == (
        hashlib.sha256(data).hexdigest(),
        hashlib.sha512(data).hexdigest(),
    )


@pytest.mark.parametrize("skip_merkle_root", [False, True], ids=["hashed", "unhashed"])
def test_pointer_text_is_not_scanned_as_content(
    tmp_path: Path, skip_merkle_root: bool
) -> None:
    """A pointer named ``LICENSE`` or ``tool.py`` is never handed to the
    header parser and gets no detected content type, hashed or not; a
    config override still names its type; the real ``.py`` is scanned."""
    tree = {
        "demo/__init__.py": b"# SPDX-License-Identifier: MIT\nx = 1\n",
        "demo/LICENSE": _POINTER,
        "demo/tool.py": _POINTER,
        "demo/data.bin": _POINTER,
    }
    override = ContentTypeOverride("demo/data.bin", "application/x-parquet")
    with mock.patch.object(
        _file_headers, "parse_file_header", wraps=_file_headers.parse_file_header
    ) as parse:
        files = _scan(
            tmp_path,
            tree,
            scan_file_headers=True,
            detect_content_type=True,
            content_type_method="extension",
            content_type_overrides=(override,),
            skip_merkle_root=skip_merkle_root,
        )
    assert [c.args[0] for c in parse.call_args_list] == [tree["demo/__init__.py"]]
    real = _file(files, "demo/__init__.py")
    assert (real.spdx_license_identifier, real.content_type) == ("MIT", "text/x-python")
    for name in ("demo/LICENSE", "demo/tool.py"):
        pointer = _file(files, name)
        assert pointer.content_type is None and pointer.content_type_method is None
        assert pointer.spdx_license_identifier is None
        assert pointer.copyright_text is None and pointer.file_type is None
        assert (pointer.lfs_pointer is None) is skip_merkle_root
    overridden = _file(files, "demo/data.bin")
    assert (overridden.content_type, overridden.content_type_method) == (
        "application/x-parquet",
        "config_override",
    )


def test_a_checkout_with_pointers_scans_deterministically(tmp_path: Path) -> None:
    """Two scans of one tree give the same root and the same files."""
    first = get_wheel_files(write_project(tmp_path, demo_tree()))[:2]
    assert first[0] is not None
    assert get_wheel_files(tmp_path)[:2] == first
